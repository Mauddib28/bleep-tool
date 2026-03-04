#!/usr/bin/env python3
"""Debug Mode for BLEEP.

This mode provides an interactive debug shell for inspecting Bluetooth devices,
accessing low-level D-Bus interfaces, monitoring properties in real-time, and
manually invoking methods.

The shell is organised into focused submodules:

- ``debug_state``     – DebugState dataclass, GLib mainloop management
- ``debug_dbus``      – D-Bus helpers, navigation (ls/cd/pwd), introspection
- ``debug_connect``   – connect / disconnect / info
- ``debug_gatt``      – GATT operations, notification callback
- ``debug_classic``   – Classic BT discovery (cscan, csdp, pbap, …)
- ``debug_classic_data`` – Classic data exchange (copen, csend, crecv, craw, copp, cmap, cftp, csync, cbip)
- ``debug_pairing``   – Pairing / agent commands
- ``debug_scan``      – Scan / enumeration commands
- ``debug_aoi``       – AOI analysis and database commands
- ``debug_multiread`` – Multi-read and brute-write commands

Usage:
  python -m bleep -m debug [options]

Options:
  --device <mac>     MAC address of device to connect to
  --no-connect       Start debug shell without connecting to a device
  --monitor          Enable real-time property monitoring
  --detailed         Show detailed information including decoded UUIDs
"""

import argparse
import shlex

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum

try:
    import readline  # noqa: F401 – enables arrow-key editing in input()
except ImportError:
    pass

# Import observations for database integration
try:
    from bleep.core import observations as _obs_module
    _DB_AVAILABLE = True
except ImportError:
    _obs_module = None
    _DB_AVAILABLE = False

# ---------------------------------------------------------------------------
# Shared state & submodule imports
# ---------------------------------------------------------------------------

from bleep.modes.debug_state import (
    DebugState, PROMPT, DEVICE_PROMPT,
    ensure_glib_mainloop, stop_glib_mainloop,
)
from bleep.modes.debug_dbus import (
    cmd_ls, cmd_cd, cmd_pwd, cmd_back,
    cmd_interfaces, cmd_props, cmd_methods, cmd_signals,
    cmd_call, cmd_monitor, cmd_introspect,
    print_detailed_dbus_error,
)
from bleep.modes.debug_connect import cmd_connect, cmd_disconnect, cmd_info
from bleep.modes.debug_gatt import (
    cmd_services, cmd_chars, cmd_char,
    cmd_read, cmd_write, cmd_notify, cmd_detailed,
)
from bleep.modes.debug_classic import (
    cmd_cscan, cmd_cconnect, cmd_cservices, cmd_ckeep,
    cmd_csdp, cmd_pbap,
)
from bleep.modes.debug_classic_data import (
    cmd_copen, cmd_csend, cmd_crecv, cmd_craw,
    cmd_copp, cmd_cmap, cmd_cftp, cmd_cpan, cmd_cspp, cmd_csync, cmd_cbip,
)
from bleep.modes.debug_pairing import cmd_agent, cmd_pair
from bleep.modes.debug_scan import (
    cmd_scan, cmd_scann, cmd_scanp, cmd_scanb,
    cmd_enum, cmd_enumn, cmd_enump, cmd_enumb,
)
from bleep.modes.debug_aoi import cmd_aoi, cmd_dbsave, cmd_dbexport
from bleep.modes.debug_multiread import cmd_multiread, cmd_multiread_all, cmd_brutewrite


# ---------------------------------------------------------------------------
# Help command
# ---------------------------------------------------------------------------

def _cmd_help(args, state):
    """Display available commands."""
    print("\nAvailable commands:")
    print("  help                       - Show this help")
    print("  scan                       - Passive BLE scan (10 s)")
    print("  scann                      - Naggy scan (DuplicateData off)")
    print("  scanp <MAC>                - Pokey scan (spam active 1-s scans)")
    print("  scanb                      - Brute scan (BR/EDR + LE)")
    print("  cscan                      - Classic (BR/EDR) passive scan")
    print("  connect <mac>              - Connect to a device")
    print("  cconnect <mac>             - Connect to a Classic device & enumerate RFCOMM")
    print("  disconnect                 - Disconnect from current device")
    print("  cservices                  - List RFCOMM service→channel map for Classic device")
    print("  ckeep [--first|--svc NAME|CHANNEL]|--close - Open/close keep-alive RFCOMM socket")
    print("  copen [--first|--svc NAME|CHANNEL]|--close|--status - Open/close RFCOMM data socket")
    print("  csend <hex:XX|str:XX|file:PATH|data>       - Send data over RFCOMM")
    print("  crecv [--timeout N] [--size N] [--hex] [--save FILE] - Receive from RFCOMM")
    print("  craw [channel|--svc NAME|--first] [--hex]  - Interactive RFCOMM send/recv session")
    print("  copp send <file> | pull [dest.vcf]         - Object Push Profile (send/pull)")
    print("  cmap folders|list|get|push|inbox|props|read|delete - Message Access Profile")
    print("  cftp ls|cd|get|put|mkdir|rm|cp|mv           - File Transfer Profile (browse/transfer)")
    print("  cpan connect|disconnect|status|server       - Personal Area Networking (PAN)")
    print("  cspp register|unregister|status             - SPP serial port profile")
    print("  csync get|put [--location int|sim1]         - IrMC Synchronization (phonebook)")
    print("  cbip props|get|thumb <handle>               - Basic Imaging Profile [experimental]")
    print("  agent status|register|unregister - Pairing agent visibility/control (debug)")
    print("  pair <MAC> [--pin CODE] [--cap CAP] [--timeout SEC] - Pair with device (default: KeyboardDisplay)")
    print("  csdp <mac> [--connectionless] [--l2ping-count N] [--l2ping-timeout N] - SDP discovery")
    print("  pbap [--repos PB,ICH] [--format vcard21] [--auto-auth] [--watchdog 8] [--out /path/to/file.vcf] - Dump phonebook via PBAP")
    print("  info                       - Show device information")
    print("  interfaces                 - List available D-Bus interfaces")
    print("  props [interface]          - List properties for an interface")
    print("  methods <interface>        - List methods for an interface")
    print("  signals <interface>        - List signals for an interface")
    print("  call <interface> <method> [args...] - Call a method")
    print("  monitor [start|stop]       - Monitor device properties")
    print("  introspect [path]          - Introspect a D-Bus object")
    print("  services                   - List GATT services")
    print("  chars [service_uuid]       - List characteristics")
    print("  char <char_uuid>           - Show detailed characteristic info")
    print("  read <char_uuid|handle>    - Read characteristic value")
    print("  write <char_uuid|handle> <value> - Write to characteristic")
    print("  notify <char_uuid|handle> [on|off] - Subscribe/unsubscribe to notifications")
    print("  detailed [on|off]          - Toggle detailed view mode with UUID decoding")
    print("  enum <MAC>                - Passive enumeration (no writes)")
    print("  enumn <MAC>               - Naggy enumeration (multi-read only)")
    print("  enump <MAC> [--rounds N] [--verify]    - Pokey enumeration with 0/1 write probes")
    print("  enumb <MAC> <CHAR_UUID> [--range a-b] [--patterns ...] [--payload-file FILE] [--force] [--verify] - Brute enumeration")
    print("  aoi [--save] [MAC]        - Assets-of-Interest analysis and reporting")
    print("\nAdvanced read/write commands:")
    print("  multiread <char_uuid|handle> [rounds=N]   - Read a characteristic multiple times (e.g., rounds=1000)")
    print("  multiread_all [rounds=3]                  - Read all readable characteristics multiple times")
    print("  brutewrite <char_uuid|handle> <pattern> [--range start-end] [--verify]  - Brute force write values")
    print("\nNavigation commands:")
    print("  ls [path]                  - List objects at current or specified path")
    print("  cd <path>                  - Change to specified D-Bus path")
    print("  pwd                        - Show current D-Bus path")
    print("  back                       - Go back to previous path")
    print("\nDatabase commands:")
    print("  dbsave [on|off]           - Toggle database saving")
    print("  dbexport [--save]         - Export device data from database")
    print("\nOther commands:")
    print("  quit                       - Exit debug mode")
    print()


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

def _build_dispatch_table(state: DebugState):
    """Build the command → handler mapping, binding *state* to every handler."""

    def _wrap(fn):
        """Wrap a two-arg handler(args, state) into a one-arg handler(args)."""
        return lambda args: fn(args, state)

    return {
        "help":          _wrap(_cmd_help),
        "scan":          _wrap(cmd_scan),
        "scann":         _wrap(cmd_scann),
        "scanp":         _wrap(cmd_scanp),
        "scanb":         _wrap(cmd_scanb),
        "cscan":         _wrap(cmd_cscan),
        "connect":       _wrap(cmd_connect),
        "cconnect":      _wrap(cmd_cconnect),
        "disconnect":    _wrap(cmd_disconnect),
        "cservices":     _wrap(cmd_cservices),
        "ckeep":         _wrap(cmd_ckeep),
        "copen":         _wrap(cmd_copen),
        "csend":         _wrap(cmd_csend),
        "crecv":         _wrap(cmd_crecv),
        "craw":          _wrap(cmd_craw),
        "copp":          _wrap(cmd_copp),
        "cmap":          _wrap(cmd_cmap),
        "cftp":          _wrap(cmd_cftp),
        "cpan":          _wrap(cmd_cpan),
        "cspp":          _wrap(cmd_cspp),
        "csync":         _wrap(cmd_csync),
        "cbip":          _wrap(cmd_cbip),
        "agent":         _wrap(cmd_agent),
        "pair":          _wrap(cmd_pair),
        "csdp":          _wrap(cmd_csdp),
        "pbap":          _wrap(cmd_pbap),
        "info":          _wrap(cmd_info),
        "interfaces":    _wrap(cmd_interfaces),
        "props":         _wrap(cmd_props),
        "methods":       _wrap(cmd_methods),
        "signals":       _wrap(cmd_signals),
        "call":          _wrap(cmd_call),
        "monitor":       _wrap(cmd_monitor),
        "introspect":    _wrap(cmd_introspect),
        "services":      _wrap(cmd_services),
        "chars":         _wrap(cmd_chars),
        "char":          _wrap(cmd_char),
        "read":          _wrap(cmd_read),
        "write":         _wrap(cmd_write),
        "notify":        _wrap(cmd_notify),
        "detailed":      _wrap(cmd_detailed),
        "enum":          _wrap(cmd_enum),
        "enumn":         _wrap(cmd_enumn),
        "enump":         _wrap(cmd_enump),
        "enumb":         _wrap(cmd_enumb),
        "aoi":           _wrap(cmd_aoi),
        "dbsave":        _wrap(cmd_dbsave),
        "dbexport":      _wrap(cmd_dbexport),
        "multiread":     _wrap(cmd_multiread),
        "multiread_all": _wrap(cmd_multiread_all),
        "brutewrite":    _wrap(cmd_brutewrite),
        "ls":            _wrap(cmd_ls),
        "cd":            _wrap(cmd_cd),
        "pwd":           _wrap(cmd_pwd),
        "back":          _wrap(cmd_back),
        "quit":          lambda _: None,
        "exit":          lambda _: None,
    }


# ---------------------------------------------------------------------------
# Interactive shell
# ---------------------------------------------------------------------------

def debug_shell(state: DebugState) -> None:
    """Run the interactive debug shell."""
    print_and_log("[*] BLEEP Debug Mode - Type 'help' for commands, 'quit' to exit", LOG__GENERAL)

    ensure_glib_mainloop(state)
    cmds = _build_dispatch_table(state)

    while True:
        try:
            if state.current_device:
                if state.current_path and state.current_path != state.current_device._device_path:
                    path_display = state.current_path.replace(state.current_device._device_path, '')
                    prompt = DEVICE_PROMPT.format(state.current_device.mac_address + ":" + path_display)
                else:
                    prompt = DEVICE_PROMPT.format(state.current_device.mac_address)
            elif state.current_path:
                prompt = f"BLEEP-DEBUG[{state.current_path}]> "
            else:
                prompt = PROMPT

            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        parts = shlex.split(line)
        if not parts:
            continue

        cmd, *rest = parts

        if cmd.lower() in ("quit", "exit"):
            if state.keepalive_sock:
                try:
                    state.keepalive_sock.close()
                except Exception:
                    pass
            if state.monitoring:
                state.monitor_stop_event.set()
                if state.monitor_thread:
                    state.monitor_thread.join(timeout=1.0)
            if state.current_device:
                try:
                    state.current_device.disconnect()
                except Exception:
                    pass
            stop_glib_mainloop(state)
            break

        handler = cmds.get(cmd.lower())
        if not handler:
            print("Unknown command - type 'help' for available commands")
            continue

        try:
            handler(rest)
        except Exception as exc:
            print_and_log(f"[-] Command failed: {exc}", LOG__DEBUG)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BLEEP Debug Mode")
    parser.add_argument("device", nargs="?", help="MAC address of device to connect to")
    parser.add_argument("-m", "--monitor", action="store_true",
                        help="Monitor device properties in real-time")
    parser.add_argument("-n", "--no-connect", action="store_true",
                        help="Don't connect to device (just scan)")
    parser.add_argument("-d", "--detailed", action="store_true",
                        help="Show detailed information including decoded UUIDs and handle information")
    return parser.parse_args(args)


def main(args=None) -> int:
    """Main entry point for Debug Mode."""
    parsed_args = parse_args(args)

    state = DebugState()
    state.detailed_view = parsed_args.detailed

    # Wire up the database module
    state.db_available = _DB_AVAILABLE
    state.obs = _obs_module

    if parsed_args.device and not parsed_args.no_connect:
        try:
            print_and_log(f"[*] Connecting to {parsed_args.device}...", LOG__GENERAL)
            dev, mapping, _, _ = _connect_enum(parsed_args.device)
            state.current_device = dev
            state.current_mapping = mapping
            print_and_log(f"[+] Connected to {parsed_args.device}", LOG__GENERAL)

            if parsed_args.monitor:
                from bleep.modes.debug_dbus import cmd_monitor
                cmd_monitor(["start"], state)
        except Exception as exc:
            print_and_log(f"[-] Connection failed: {exc}", LOG__DEBUG)
            print_detailed_dbus_error(exc)
            return 1

    try:
        debug_shell(state)
    except Exception as exc:
        print_and_log(f"[-] Debug shell error: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
