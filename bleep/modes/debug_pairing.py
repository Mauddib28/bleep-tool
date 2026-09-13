"""Pairing and agent commands for debug mode."""

from __future__ import annotations

import time
from typing import List

import dbus

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__AGENT
from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
from bleep.pairing import (
    find_device_path,
    resolve_device_for_pair,
    remove_stale_bond,
    register_pair_agent,
    check_pair_status,
    report_pair_status,
)

from bleep.modes.debug_state import DebugState, ensure_glib_mainloop, stop_glib_mainloop
from bleep.modes.debug_dbus import format_dbus_error
from bleep.modes.debug_connect import get_device_transport


# ---------------------------------------------------------------------------
# Post-pair helpers (debug-mode specific — they update DebugState)
# ---------------------------------------------------------------------------

def _post_pair_monitor(mac: str, device_path: str, connect_time: float) -> None:
    """Monitor a freshly paired device for auto-disconnect."""
    try:
        bus = dbus.SystemBus()
        props = dbus.Interface(
            bus.get_object("org.bluez", device_path),
            "org.freedesktop.DBus.Properties",
        )
        connected = bool(props.Get("org.bluez.Device1", "Connected"))
    except Exception:
        connected = False

    if not connected:
        print(f"[*] Device {mac} is paired but not connected")
        return

    print(f"[*] Device {mac} connected – monitoring for auto-disconnect…")
    print("[*] (Press Ctrl+C to stop monitoring and return to debug shell)")

    try:
        while True:
            time.sleep(2)
            try:
                still_connected = bool(props.Get("org.bluez.Device1", "Connected"))
            except Exception:
                still_connected = False

            if not still_connected:
                elapsed = time.time() - connect_time
                if 45 < elapsed < 75:
                    print(
                        f"[*] Device {mac} disconnected after {elapsed:.0f}s "
                        f"– consistent with target auto-disconnect timer (~60s)"
                    )
                else:
                    print(f"[!] Device {mac} disconnected after {elapsed:.0f}s")
                break
    except KeyboardInterrupt:
        print("\n[*] Monitoring stopped")


def _post_pair_connect(mac: str, device_path: str, state: DebugState) -> None:
    """After successful pairing, connect and set up the debug shell session."""
    transport = get_device_transport(device_path)
    print_and_log(f"[*] Device transport: {transport}", LOG__GENERAL)

    if transport in ("br-edr", "dual"):
        post_pair_connect_classic(mac, device_path, state)
    else:
        _post_pair_connect_le(mac, state)


def post_pair_connect_classic(mac: str, device_path: str, state: DebugState) -> None:
    """Attempt classic connection after pairing: SDP + keepalive socket."""
    from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic
    from bleep.ble_ops.classic.sdp import discover_services_sdp, build_svc_map
    from bleep.ble_ops.classic.connect import classic_rfccomm_open

    dev = system_dbus__bluez_device__classic(mac)

    svc_map: dict = {}
    try:
        records = discover_services_sdp(mac)
        svc_map = build_svc_map(records)
        rfcomm_count = sum(1 for v in svc_map.values() if v.get("channel") is not None)
        if svc_map:
            print_and_log(
                f"[+] SDP enumeration: {len(svc_map)} service(s) ({rfcomm_count} with RFCOMM)",
                LOG__GENERAL,
            )
    except Exception as exc:
        print_and_log(f"[*] SDP enumeration unavailable: {exc}", LOG__DEBUG)

    keepalive_ok = False
    candidates = []
    for entry in svc_map.values():
        ch = entry.get("channel") if isinstance(entry, dict) else entry
        if ch is not None and ch not in candidates:
            candidates.append(ch)

    last_err = None
    for ch in candidates:
        try:
            state.keepalive_sock = classic_rfccomm_open(mac, ch, timeout=5.0)
            keepalive_ok = True
            print_and_log(f"[+] Keep-alive socket opened on RFCOMM channel {ch}", LOG__GENERAL)
            break
        except Exception as exc:
            print_and_log(f"[*] Keep-alive socket failed (channel {ch}): {exc}", LOG__DEBUG)
            last_err = exc

    if not keepalive_ok and candidates and last_err is not None:
        print_and_log(
            f"[*] All {len(candidates)} RFCOMM channel(s) failed — last error: {last_err}",
            LOG__GENERAL,
        )

    state.current_device = dev
    state.current_mapping = svc_map if svc_map else None
    state.current_mode = "classic"
    state.current_path = device_path

    if keepalive_ok:
        print(f"[+] Connected to {mac} – ready for exploration (use 'ckeep --close' when done)")
    elif svc_map:
        print(f"[+] Paired with {mac} – SDP services found but keepalive failed")
        print(f"    Use 'ckeep {mac} <channel>' to try a specific channel")
    else:
        print(f"[+] Paired with {mac} – D-Bus exploration available")
        print("    Use 'info', 'interfaces', 'props' to inspect the device")


def _post_pair_connect_le(mac: str, state: DebugState) -> None:
    """Attempt BLE connection and GATT enumeration after pairing."""
    try:
        dev, mapping, _, _ = _connect_enum(mac)
        state.current_device = dev
        state.current_mapping = mapping
        state.current_mode = "ble"
        state.current_path = dev._device_path
        print(f"[+] Connected to {mac} – GATT services enumerated")
    except Exception as exc:
        print_and_log(f"[*] BLE connect/enumerate failed: {exc}", LOG__DEBUG)
        state.current_path = find_device_path(mac)
        print(f"[+] Paired with {mac} – BLE connect failed, D-Bus exploration available")
        print("    Use 'interfaces', 'props' to inspect the device")


# ---------------------------------------------------------------------------
# Agent command
# ---------------------------------------------------------------------------

# Debug agent management subcommands → CLI `agent` flag form (CDU-M7b). Each
# delegates to the same bleep.modes.agent.run the CLI uses; these flags run as
# one-shot ops that return before the agent loop (bleep/modes/agent.py).
_AGENT_MGMT = {
    "trust":        ("--trust", True),
    "untrust":      ("--untrust", True),
    "remove-bond":  ("--remove-bond", True),
    "list-trusted": ("--list-trusted", False),
    "list-bonded":  ("--list-bonded", False),
}


def _cmd_agent_management(args: List[str]) -> None:
    """Handle ``agent <trust|untrust|remove-bond|list-trusted|list-bonded> [MAC]``."""
    verb = args[0]
    flag, needs_mac = _AGENT_MGMT[verb]
    if needs_mac:
        if len(args) < 2:
            print_and_log(f"Usage: agent {verb} <MAC>", LOG__GENERAL)
            return
        cli_tokens = [flag, args[1]]
    else:
        cli_tokens = [flag]

    from bleep.modes.debug_cli_adapters import parse_as_cli

    ns = parse_as_cli("agent", cli_tokens)
    if ns is None:
        return
    from bleep.modes.agent import run as _agent_run

    _agent_run(ns)


def cmd_agent(args: List[str], state: DebugState) -> None:
    """Agent visibility/control for debug mode.

    Native session verbs: ``status`` / ``register`` / ``unregister``. Device
    management verbs (``trust``/``untrust``/``remove-bond``/``list-trusted``/
    ``list-bonded``) delegate to the shared CLI ``agent`` core (CDU-M7b).
    """
    import argparse
    from bleep.dbuslayer.agent import ensure_default_pairing_agent, clear_default_pairing_agent

    if args and args[0] in _AGENT_MGMT:
        _cmd_agent_management(args)
        return

    parser = argparse.ArgumentParser(prog="agent", add_help=False)
    sub = parser.add_subparsers(dest="subcmd", required=True)

    sub.add_parser("status", add_help=False)
    p_register = sub.add_parser("register", add_help=False)
    p_register.add_argument("--cap", default="kbdisp",
                            choices=["none", "display", "yesno", "keyboard", "kbdisp"])
    p_register.add_argument("--default", action="store_true")
    mode = p_register.add_mutually_exclusive_group()
    mode.add_argument("--interactive", action="store_true")
    mode.add_argument("--auto", action="store_true")
    sub.add_parser("unregister", add_help=False)

    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    if opts.subcmd == "status":
        try:
            from bleep.dbuslayer import agent as _agent_mod
            a = getattr(_agent_mod, "_DEFAULT_AGENT", None)
            if a is None:
                print("[*] Default pairing agent: not created")
                print("[*] Use 'agent register' to create and register an agent")
            else:
                agent_path = getattr(a, 'agent_path', 'unknown')
                is_registered = a.is_registered()
                agent_class = a.__class__.__name__

                capabilities = getattr(a, '_capabilities', 'unknown')
                default_requested = getattr(a, '_default_requested', False)
                auto_accept = getattr(a, '_auto_accept', 'unknown')
                io_handler_type = 'unknown'
                if hasattr(a, '_io_handler'):
                    io_handler = a._io_handler
                    io_handler_type = io_handler.__class__.__name__
                    if hasattr(io_handler, 'auto_accept'):
                        auto_accept = io_handler.auto_accept

                print("[*] Default pairing agent status:")
                print(f"    class: {agent_class}")
                print(f"    path: {agent_path}")
                print(f"    registered: {is_registered}")
                print(f"    capabilities: {capabilities}")
                print(f"    default_requested: {default_requested}")
                print(f"    auto_accept: {auto_accept}")
                print(f"    io_handler: {io_handler_type}")

                if hasattr(a, '_io_handler') and a._io_handler is not None:
                    handler = a._io_handler
                    if hasattr(handler, 'default_pin'):
                        print(f"    default_pin: {handler.default_pin}")
                    if hasattr(handler, 'default_passkey'):
                        print(f"    default_passkey: {handler.default_passkey:06d}")

                invocations = getattr(a, '_method_invocations', {})
                if invocations:
                    print("    recent_invocations:")
                    for method, ts in sorted(invocations.items(), key=lambda x: x[1], reverse=True):
                        age = time.time() - ts
                        print(f"      {method}: {age:.0f}s ago")

                if not is_registered:
                    print("[*] Agent exists but is not registered with BlueZ")
                    print("[*] Use 'agent register' to register the agent")
        except Exception as exc:
            error_str = format_dbus_error(exc) if isinstance(exc, dbus.exceptions.DBusException) else str(exc)
            print(f"[-] Agent status failed: {error_str}")
        return

    if opts.subcmd == "register":
        cap_map = {
            "none": "NoInputNoOutput", "display": "DisplayOnly",
            "yesno": "DisplayYesNo", "keyboard": "KeyboardOnly",
            "kbdisp": "KeyboardDisplay",
        }
        cap = cap_map[opts.cap]

        from bleep.dbuslayer.agent_io import create_io_handler
        if opts.interactive:
            io_handler = create_io_handler("cli")
            auto_accept = False
        else:
            io_handler = create_io_handler("auto")
            auto_accept = True

        ensure_default_pairing_agent(capabilities=cap, auto_accept=auto_accept, io_handler=io_handler)

        from bleep.dbuslayer import agent as _agent_mod
        a = getattr(_agent_mod, "_DEFAULT_AGENT", None)
        agent_path = getattr(a, 'agent_path', 'unknown') if a else 'unknown'
        agent_class = a.__class__.__name__ if a else 'unknown'
        io_handler_type = io_handler.__class__.__name__

        print_and_log(
            f"[+] Default pairing agent registered: agent_type={agent_class}, capabilities={cap}, "
            f"default={opts.default}, auto_accept={auto_accept}, agent_path={agent_path}, "
            f"io_handler={io_handler_type}",
            LOG__AGENT,
        )
        return

    if opts.subcmd == "unregister":
        try:
            clear_default_pairing_agent()
            print("[+] Default pairing agent cleared")
        except Exception as exc:
            print(f"[-] Agent unregister failed: {exc}")


# ---------------------------------------------------------------------------
# Pair command
# ---------------------------------------------------------------------------

def cmd_pair(args: List[str], state: DebugState) -> None:
    """Pair with a device using hardcoded PIN, interactive prompt, or brute-force."""
    import argparse as _ap

    parser = _ap.ArgumentParser(prog="pair", add_help=False)
    parser.add_argument("mac")
    # Shared canonical pairing option set (single source of truth with the CLI
    # `pair` subparser) — this is how the debug shell gains --no-connect /
    # --no-trust parity. The debug-only --test PoC flag is added afterwards.
    from bleep.cli.parsers.pairing import _add_pair_arguments
    _add_pair_arguments(parser)
    parser.add_argument("--test", action="store_true")

    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    mac = opts.mac.upper()
    cap = opts.cap

    # --check: report pairing state only
    if opts.check:
        status = check_pair_status(mac)
        report_pair_status(mac, status)
        return

    if opts.probe:
        _cmd_pair_probe(mac, opts.timeout, state)
    elif opts.brute:
        _cmd_pair_brute(mac, opts, cap, state)
    elif opts.interactive:
        _cmd_pair_single(mac, cap, opts.timeout, "cli",
                         test_mode=opts.test, reset=opts.reset,
                         no_connect=opts.no_connect, no_trust=opts.no_trust,
                         state=state)
    else:
        pin = opts.pin if opts.pin is not None else "0000"
        _cmd_pair_single(mac, cap, opts.timeout, "auto", pin=pin, passkey=opts.passkey,
                         test_mode=opts.test, reset=opts.reset,
                         no_connect=opts.no_connect, no_trust=opts.no_trust,
                         state=state)


def _cmd_pair_probe(mac: str, timeout: int, state: DebugState) -> None:
    """Discover auth method by cycling capabilities, then cancel pairing."""
    import dbus
    import dbus.mainloop.glib
    from bleep.dbuslayer.agent import attempt_downgrade_pair
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = Adapter()
    device_path = f"{adapter.adapter_path}/dev_{mac.replace(':', '_')}"

    print(f"[*] Probing auth method for {mac} (cycling capabilities)...")
    result = attempt_downgrade_pair(bus, device_path, timeout=timeout)

    print(f"\n{'='*60}")
    print(f"Auth Probe Results for {mac}")
    print(f"{'='*60}")
    for att in result["attempts"]:
        auth = att["auth_method"] or "none"
        print(f"  {att['capability']:<20}  {att['result']:<30}  auth={auth}")
    print(f"{'='*60}")

    if result["success"]:
        print(f"[+] Paired successfully with '{result['capability']}' (auth: {result['auth_method']})")
        try:
            dev_iface = dbus.Interface(
                bus.get_object("org.bluez", device_path), "org.bluez.Device1"
            )
            dev_iface.CancelPairing()
            print("[*] Pairing canceled (probe complete)")
        except dbus.exceptions.DBusException:
            pass
    else:
        print(f"[-] No capability succeeded — device requires explicit auth")


def _cmd_pair_single(
    mac: str, cap: str, timeout: int, io_mode: str,
    pin: str = "0000", passkey: int | None = None,
    test_mode: bool = False, reset: bool = False,
    no_connect: bool = False, no_trust: bool = False,
    *, state: DebugState,
) -> None:
    """Execute a single pairing attempt.

    ``no_connect`` skips the post-pair connection flow (pair only);
    ``no_trust`` leaves the device untrusted after a successful pair. Both
    mirror the CLI ``pair --no-connect`` / ``--no-trust`` semantics.
    """
    from bleep.dbuslayer.agent import PairingAgent
    from bleep.dbuslayer.agent_io import create_io_handler
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
    import bleep.dbuslayer.agent as _agent_mod

    # Pre-pair status check
    status = check_pair_status(mac)
    if status["paired"] and not reset:
        report_pair_status(mac, status)
        if status["connected"]:
            print("[*] Device is already paired and connected – skipping pairing")
            print("[*] Use --reset to force-remove the existing bond and re-pair")
            return
        if no_connect:
            print("[*] Device is already paired – --no-connect set, skipping connection")
            print("[*] Use --reset to force-remove the existing bond and re-pair")
            return
        print("[*] Device is already paired – attempting connection only")
        print("[*] Use --reset to force-remove the existing bond and re-pair")
        device_path = find_device_path(mac)
        if device_path:
            _post_pair_connect(mac, device_path, state)
        return

    if io_mode == "cli":
        print_and_log(f"[*] Pair target: {mac}  mode: interactive  capability: {cap}  timeout: {timeout}s", LOG__GENERAL)
        io_handler = create_io_handler("cli")
    else:
        if passkey is not None:
            print_and_log(f"[*] Pair target: {mac}  passkey: {passkey:06d}  capability: {cap}  timeout: {timeout}s", LOG__GENERAL)
            io_handler = create_io_handler("auto", default_pin=pin, default_passkey=passkey)
        else:
            print_and_log(f"[*] Pair target: {mac}  PIN: {pin}  capability: {cap}  timeout: {timeout}s", LOG__GENERAL)
            io_handler = create_io_handler("auto", default_pin=pin)

    stop_glib_mainloop(state)

    if not register_pair_agent(io_handler, cap):
        ensure_glib_mainloop(state)
        return

    adapter = Adapter()
    device_path = resolve_device_for_pair(mac, adapter)
    if device_path is None:
        print(f"[-] Device {mac} not found. Ensure it is powered on and in range.")
        ensure_glib_mainloop(state)
        return

    # Remove stale bond if --reset was requested or unconditionally (legacy behaviour)
    if reset:
        device_path = remove_stale_bond(mac, device_path, adapter)
        if device_path is None:
            print(f"[-] Device {mac} not re-discovered after bond removal.")
            ensure_glib_mainloop(state)
            return

    agent = getattr(_agent_mod, "_DEFAULT_AGENT", None)
    if not isinstance(agent, PairingAgent):
        print("[-] Default agent is not a PairingAgent – cannot pair")
        ensure_glib_mainloop(state)
        return

    connect_time = time.time()
    success = agent.pair_device(device_path, set_trusted=not no_trust, timeout=timeout)

    ensure_glib_mainloop(state)

    # P2-B2: Persist pairing event from debug shell
    try:
        from bleep.core import observations as _obs
        _obs.store_pairing_event(
            mac,
            method=agent.get_last_auth_type() if hasattr(agent, 'get_last_auth_type') else None,
            pin=pin,
            result="success" if success else "failed",
            capabilities=cap,
            pre_pair_state=status if isinstance(status, dict) else None,
            post_pair_state=check_pair_status(mac) if success else None,
        )
        if success:
            _obs.upsert_device(mac, paired=True, trusted=not no_trust)
    except Exception:
        pass

    if not success:
        print(f"[-] Pairing with {mac} failed (see logs for details)")
        return

    print(f"[+] Paired with {mac} successfully")

    if test_mode:
        _post_pair_monitor(mac, device_path, connect_time)
    elif no_connect:
        print("[*] --no-connect set – pairing complete, skipping post-pair connection")
    else:
        _post_pair_connect(mac, device_path, state)


def _cmd_pair_brute(mac: str, opts, cap: str, state: DebugState) -> None:
    """Execute brute-force pairing against a target device."""
    from bleep.dbuslayer.pin_brute import PinBruteForcer, pin_range, passkey_range, pins_from_file

    stop_glib_mainloop(state)

    bus = dbus.SystemBus()
    bruteforcer = PinBruteForcer(
        bus, delay=opts.delay, max_attempts=opts.max_attempts,
        timeout_per_attempt=opts.timeout,
        lockout_cooldown=opts.lockout_cooldown,
        max_lockout_retries=opts.max_lockout_retries,
    )

    if opts.passkey_brute:
        if opts.pin_range:
            parts = opts.pin_range.split("-")
            start, end = int(parts[0]), int(parts[1])
        else:
            start, end = 0, 999999
        print_and_log(
            f"[*] Brute-force passkey: {mac}  range: {start:06d}-{end:06d}  "
            f"delay: {opts.delay}s  cap: {cap}", LOG__GENERAL,
        )
        result = bruteforcer.run_passkey_brute(mac, passkey_range(start, end), capabilities=cap)
    elif opts.pin_list:
        print_and_log(
            f"[*] Brute-force PIN from file: {mac}  file: {opts.pin_list}  "
            f"delay: {opts.delay}s  cap: {cap}", LOG__GENERAL,
        )
        try:
            result = bruteforcer.run_pin_brute(mac, pins_from_file(opts.pin_list), capabilities=cap)
        except FileNotFoundError:
            print(f"[-] PIN list file not found: {opts.pin_list}")
            ensure_glib_mainloop(state)
            return
    else:
        if opts.pin_range:
            parts = opts.pin_range.split("-")
            start, end = parts[0], parts[1]
        else:
            start, end = "0000", "9999"
        print_and_log(
            f"[*] Brute-force PIN: {mac}  range: {start}-{end}  "
            f"delay: {opts.delay}s  cap: {cap}", LOG__GENERAL,
        )
        result = bruteforcer.run_pin_brute(mac, pin_range(start, end), capabilities=cap)

    ensure_glib_mainloop(state)

    if result.success:
        value = result.pin if result.pin is not None else f"{result.passkey:06d}"
        print(f"\n[+] FOUND: correct value for {mac} = {value}")
        print(f"[*] Discovered in {result.attempts} attempts ({result.elapsed_seconds:.1f}s)")
        print(f"[*] Use 'pair {mac} --pin {value}' to pair with the discovered PIN")
    else:
        if result.errors:
            for err in result.errors:
                print(f"[-] {err}")
