"""BLEEP Agent mode – provides a minimal CLI for registering a pairing agent.

This replaces the historical *Modules/agent_mode.py* functionality.  The new
implementation relies exclusively on the refactored `bleep.dbuslayer.agent`
classes and therefore removes the last runtime dependency on the legacy
monolith for agent handling.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from typing import Literal, Optional, Dict, Any

import dbus
from gi.repository import GLib

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.agent import (
    SimpleAgent, 
    InteractiveAgent, 
    EnhancedAgent,
    PairingAgent,
    TrustManager,
    create_agent
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_CAPABILITIES: dict[str, str] = {
    "none": "NoInputNoOutput",
    "display": "DisplayOnly",
    "yesno": "DisplayYesNo",
    "keyboard": "KeyboardOnly",
    "kbdisp": "KeyboardDisplay",
}

_AGENT_CLASSES: dict[str, str] = {
    "simple": "simple",
    "interactive": "interactive",
    "enhanced": "enhanced",
    "pairing": "pairing",
}


def _build_arg_parser() -> argparse.ArgumentParser:  # noqa: D401 – cli helper
    p = argparse.ArgumentParser(prog="bleep-agent", add_help=False)
    p.add_argument("--mode", choices=_AGENT_CLASSES.keys(), default="simple",
                  help="Agent mode: simple, interactive, enhanced, or pairing")
    p.add_argument("--cap", choices=_CAPABILITIES.keys(), default="none",
                  help="Agent capabilities: none, display, yesno, keyboard, kbdisp")
    p.add_argument("--default", action="store_true", help="RequestDefaultAgent")
    p.add_argument("--auto-accept", action="store_true", default=True,
                  help="Auto-accept pairing requests (for enhanced and pairing agents)")
    p.add_argument("--pair", metavar="MAC", help="Pair with a device (only in pairing mode)")
    p.add_argument("--trust", metavar="MAC", help="Set a device as trusted")
    p.add_argument("--untrust", metavar="MAC", help="Set a device as untrusted")
    p.add_argument("--list-trusted", action="store_true", help="List all trusted devices")
    p.add_argument("--list-bonded", action="store_true", help="List all bonded devices (with stored keys)")
    p.add_argument("--remove-bond", metavar="MAC", help="Remove bonding information for a device")
    p.add_argument("--storage-path", help="Path to store bonding information")
    p.add_argument("--timeout", type=int, default=30, 
                  help="Timeout for pairing operations (seconds)")
    p.add_argument("-h", "--help", action="help")
    return p


def _get_device_path(bus, mac_address: str) -> str:
    """Get the D-Bus path for a device by its MAC address."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
    
    adapter = Adapter()
    devices = adapter.get_devices()
    
    for device in devices:
        if device.get("Address", "").lower() == mac_address.lower():
            return device.get("path")
            
    # If device not found, try to discover it
    print_and_log(f"[*] Device {mac_address} not found, attempting discovery...", LOG__GENERAL)
    adapter.start_discovery()
    
    # Wait for discovery
    for _ in range(5):
        time.sleep(1)
        devices = adapter.get_devices()
        for device in devices:
            if device.get("Address", "").lower() == mac_address.lower():
                adapter.stop_discovery()
                return device.get("path")
    
    adapter.stop_discovery()
    raise ValueError(f"Device {mac_address} not found")


# ---------------------------------------------------------------------------
# public entrypoint – matches other modes signature
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None):  # noqa: D401 – CLI entry
    """Run the Agent mode CLI."""
    argv = argv or sys.argv[1:]
    args = _build_arg_parser().parse_args(argv)

    # Setup D-Bus mainloop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)  # type: ignore[attr-defined]

    bus = dbus.SystemBus()
    
    # Handle trust management operations
    if args.trust or args.untrust or args.list_trusted:
        trust_manager = TrustManager(bus)
        
        if args.list_trusted:
            trusted_devices = trust_manager.get_trusted_devices()
            print_and_log("[*] Trusted devices:", LOG__GENERAL)
            for path, name, address in trusted_devices:
                print_and_log(f"    {name} ({address})", LOG__GENERAL)
            
            if not trusted_devices:
                print_and_log("[*] No trusted devices found", LOG__GENERAL)
                
        if args.trust:
            try:
                device_path = _get_device_path(bus, args.trust)
                if trust_manager.set_trusted(device_path, True):
                    print_and_log(f"[+] Device {args.trust} set as trusted", LOG__GENERAL)
                else:
                    print_and_log(f"[-] Failed to set device {args.trust} as trusted", LOG__GENERAL)
            except Exception as e:
                print_and_log(f"[-] Error setting device as trusted: {str(e)}", LOG__GENERAL)
                
        if args.untrust:
            try:
                device_path = _get_device_path(bus, args.untrust)
                if trust_manager.set_trusted(device_path, False):
                    print_and_log(f"[+] Device {args.untrust} set as untrusted", LOG__GENERAL)
                else:
                    print_and_log(f"[-] Failed to set device {args.untrust} as untrusted", LOG__GENERAL)
            except Exception as e:
                print_and_log(f"[-] Error setting device as untrusted: {str(e)}", LOG__GENERAL)
    
    # Handle bond management operations
    if args.list_bonded or args.remove_bond:
        from bleep.dbuslayer.bond_storage import DeviceBondStore
        bond_store = DeviceBondStore(args.storage_path)
        
        if args.list_bonded:
            bonded_devices = bond_store.list_bonded_devices()
            print_and_log("[*] Bonded devices with stored keys:", LOG__GENERAL)
            for device in bonded_devices:
                name = device.get("name", "Unknown")
                addr = device.get("address", "Unknown")
                timestamp = device.get("timestamps", {}).get("last_paired", "Unknown")
                print_and_log(f"    {name} ({addr}) - Last paired: {timestamp}", LOG__GENERAL)
            
            if not bonded_devices:
                print_and_log("[*] No bonded devices found", LOG__GENERAL)
                
        if args.remove_bond:
            try:
                # First try to look up by address directly
                result = bond_store.load_device_bond_by_address(args.remove_bond)
                if result and result.get("device_path"):
                    if bond_store.delete_device_bond(result["device_path"]):
                        print_and_log(f"[+] Bond information deleted for {args.remove_bond}", LOG__GENERAL)
                    else:
                        print_and_log(f"[-] Failed to delete bond for {args.remove_bond}", LOG__GENERAL)
                else:
                    print_and_log(f"[-] No bond found for {args.remove_bond}", LOG__GENERAL)
            except Exception as e:
                print_and_log(f"[-] Error removing bond: {str(e)}", LOG__GENERAL)
                
    # If only trust/bond operations were requested, exit
    if not args.pair and (args.trust or args.untrust or args.list_trusted or args.list_bonded or args.remove_bond):
        return 0

    # Create and register agent
    agent_type = args.mode
    cap = _CAPABILITIES[args.cap]
    
    try:
        # Create appropriate I/O handler based on flags
        io_handler = None
        if agent_type == "pairing":
            from bleep.dbuslayer.agent_io import create_io_handler
            if args.auto_accept:
                io_handler = create_io_handler("auto")
            else:
                io_handler = create_io_handler("cli")
        elif agent_type == "interactive":
            from bleep.dbuslayer.agent_io import create_io_handler
            io_handler = create_io_handler("cli")
        elif agent_type == "enhanced":
            from bleep.dbuslayer.agent_io import create_io_handler
            io_handler = create_io_handler("programmatic", auto_accept=args.auto_accept)
        
        # Create the agent
            agent = create_agent(
                bus, 
                agent_type=agent_type, 
                capabilities=cap, 
                default=args.default,
                auto_accept=args.auto_accept,
                io_handler=io_handler,
                storage_path=args.storage_path
            )
        
        print_and_log(f"[*] Agent registered ({agent.__class__.__name__}, cap={cap})", LOG__GENERAL)
        
        # Handle pairing if requested
        if args.pair and isinstance(agent, PairingAgent):
            try:
                device_path = _get_device_path(bus, args.pair)
                
                # Setup pairing callbacks
                def on_pairing_started(device_info):
                    print_and_log(f"[*] Pairing started with {device_info}", LOG__GENERAL)
                    
                def on_pairing_succeeded(device_info):
                    print_and_log(f"[+] Pairing succeeded with {device_info}", LOG__GENERAL)
                    
                def on_pairing_failed(device_info, reason):
                    print_and_log(f"[-] Pairing failed with {device_info}: {reason}", LOG__GENERAL)
                    
                def on_device_trusted(device_info):
                    print_and_log(f"[+] Device {device_info} set as trusted", LOG__GENERAL)
                
                agent.set_pairing_callback("pairing_started", on_pairing_started)
                agent.set_pairing_callback("pairing_succeeded", on_pairing_succeeded)
                agent.set_pairing_callback("pairing_failed", on_pairing_failed)
                agent.set_pairing_callback("device_trusted", on_device_trusted)
                
                # Attempt pairing
                success = agent.pair_device(device_path, set_trusted=True, timeout=args.timeout)
                
                if success:
                    print_and_log(f"[+] Successfully paired with {args.pair}", LOG__GENERAL)
                else:
                    print_and_log(f"[-] Failed to pair with {args.pair}", LOG__GENERAL)
                    
                # If only pairing was requested, exit
                if not args.default:
                    agent.unregister()
                    return 0 if success else 1
                    
            except Exception as e:
                print_and_log(f"[-] Error during pairing: {str(e)}", LOG__GENERAL)
                if not args.default:
                    agent.unregister()
                    return 1
        elif args.pair:
            print_and_log(f"[-] Pairing requires 'pairing' agent mode, current mode is '{agent_type}'", LOG__GENERAL)
            agent.unregister()
            return 1
    
        # Run the main loop if default agent is requested
        if args.default:
            loop = GLib.MainLoop()
            
            def _sigint(_sig, _frm):
                print_and_log("[!] SIGINT received – unregistering agent", LOG__GENERAL)
                try:
                    agent.unregister()
                finally:
                    loop.quit()
            
            signal.signal(signal.SIGINT, _sigint)
            
            try:
                print_and_log("[*] Agent running, press Ctrl+C to exit", LOG__GENERAL)
                loop.run()
            finally:
                print_and_log("[*] Agent loop exited", LOG__GENERAL)
                
    except Exception as e:
        print_and_log(f"[-] Agent error: {str(e)}", LOG__GENERAL)
        return 1
        
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main()) 