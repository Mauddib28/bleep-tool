"""BLEEP ``pair`` CLI mode — pair with a Bluetooth device from the command line.

Exposes the full pairing feature-set (PIN, passkey, interactive, brute-force,
probe, pre-pair check, forced bond reset) that was previously only available
inside the debug-mode shell.

Unlike the debug shell, there is no background GLib MainLoop running, so
``PairingAgent.pair_device()`` spins its own temporary loop for D-Bus
dispatch automatically.

Usage examples::

    bleep pair AA:BB:CC:DD:EE:FF
    bleep pair AA:BB:CC:DD:EE:FF --pin 12345
    bleep pair AA:BB:CC:DD:EE:FF --interactive
    bleep pair AA:BB:CC:DD:EE:FF --check
    bleep pair AA:BB:CC:DD:EE:FF --reset
    bleep pair AA:BB:CC:DD:EE:FF --brute --range 0000-9999
    bleep pair AA:BB:CC:DD:EE:FF --probe
"""

from __future__ import annotations

import argparse
import sys

import dbus
import dbus.mainloop.glib  # type: ignore[import-untyped]

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__AGENT
from bleep.pairing import (
    find_device_path,
    resolve_device_for_pair,
    remove_stale_bond,
    register_pair_agent,
    check_pair_status,
    report_pair_status,
)


# ---------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bleep pair", add_help=True,
                                description="Pair with a Bluetooth device")
    p.add_argument("address", help="Target Bluetooth MAC address")

    # Auth credentials
    p.add_argument("--pin", default=None,
                   help="PIN code to use for legacy pairing (default: 0000)")
    p.add_argument("--passkey", type=int, default=None,
                   help="Numeric passkey for SSP pairing (0–999999)")
    p.add_argument("--interactive", action="store_true",
                   help="Prompt for PIN / passkey / confirmation at runtime")

    # Behaviour modifiers
    p.add_argument("--check", action="store_true",
                   help="Check pairing state only – do not pair")
    p.add_argument("--reset", action="store_true",
                   help="Force-remove existing bond before pairing")
    p.add_argument("--no-connect", action="store_true",
                   help="Pair only – do not attempt a post-pair connection")
    p.add_argument("--no-trust", action="store_true",
                   help="Do not set the device as trusted after pairing")
    p.add_argument(
        "--no-profiles", dest="activate_profiles", action="store_false",
        default=True,
        help=(
            "Classic path only: skip the best-effort BlueZ "
            "Device1.Connect() after SDP enumeration."
        ),
    )

    # Brute-force
    p.add_argument("--brute", action="store_true",
                   help="Brute-force PIN codes")
    p.add_argument("--passkey-brute", action="store_true",
                   help="Brute-force numeric passkeys")
    p.add_argument("--range", default=None, dest="pin_range",
                   help="PIN/passkey range, e.g. 0000-9999 or 0-999999")
    p.add_argument("--pin-list", default=None,
                   help="File containing one PIN per line")
    p.add_argument("--delay", type=float, default=0.5,
                   help="Delay between brute-force attempts (s)")
    p.add_argument("--max-attempts", type=int, default=0,
                   help="Maximum brute-force attempts (0 = unlimited)")
    p.add_argument("--lockout-cooldown", type=float, default=60.0,
                   help="Cooldown after lockout detection (s)")
    p.add_argument("--max-lockout-retries", type=int, default=3,
                   help="Maximum retries after lockout")

    # Probe
    p.add_argument("--probe", action="store_true",
                   help="Discover auth method by cycling IO capabilities, then cancel")

    # Protocol tunables
    p.add_argument("--cap", default="KeyboardDisplay",
                   choices=["NoInputNoOutput", "DisplayOnly", "DisplayYesNo",
                            "KeyboardOnly", "KeyboardDisplay"],
                   help="BlueZ IO capability for the pairing agent")
    p.add_argument("--timeout", type=int, default=60,
                   help="Pairing timeout in seconds")
    p.add_argument("--adapter", default="hci0",
                   help="Bluetooth adapter name (default: hci0)")

    return p


# ---------------------------------------------------------------------
# Sub-handlers
# ---------------------------------------------------------------------

def _do_check(mac: str) -> int:
    """Report pairing state and exit."""
    status = check_pair_status(mac)
    report_pair_status(mac, status)
    return 0


def _do_probe(mac: str, timeout: int) -> int:
    """Cycle IO capabilities to discover the device's auth requirements."""
    from bleep.dbuslayer.agent import attempt_downgrade_pair
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter

    adapter = Adapter()
    device_path = f"{adapter.adapter_path}/dev_{mac.replace(':', '_')}"

    print(f"[*] Probing auth method for {mac} (cycling capabilities)...")
    result = attempt_downgrade_pair(dbus.SystemBus(), device_path, timeout=timeout)

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
                dbus.SystemBus().get_object("org.bluez", device_path),
                "org.bluez.Device1",
            )
            dev_iface.CancelPairing()
            print("[*] Pairing canceled (probe complete)")
        except dbus.exceptions.DBusException:
            pass
        return 0
    else:
        print("[-] No capability succeeded — device requires explicit auth")
        return 1


def _do_brute(mac: str, args) -> int:
    """Run brute-force pairing."""
    from bleep.dbuslayer.pin_brute import (
        PinBruteForcer, pin_range, passkey_range, pins_from_file,
    )

    bus = dbus.SystemBus()
    bruteforcer = PinBruteForcer(
        bus, delay=args.delay, max_attempts=args.max_attempts,
        timeout_per_attempt=args.timeout,
        lockout_cooldown=args.lockout_cooldown,
        max_lockout_retries=args.max_lockout_retries,
    )

    if args.passkey_brute:
        if args.pin_range:
            parts = args.pin_range.split("-")
            start, end = int(parts[0]), int(parts[1])
        else:
            start, end = 0, 999999
        print_and_log(
            f"[*] Brute-force passkey: {mac}  range: {start:06d}-{end:06d}  "
            f"delay: {args.delay}s  cap: {args.cap}", LOG__GENERAL,
        )
        result = bruteforcer.run_passkey_brute(mac, passkey_range(start, end), capabilities=args.cap)
    elif args.pin_list:
        print_and_log(
            f"[*] Brute-force PIN from file: {mac}  file: {args.pin_list}  "
            f"delay: {args.delay}s  cap: {args.cap}", LOG__GENERAL,
        )
        try:
            result = bruteforcer.run_pin_brute(mac, pins_from_file(args.pin_list), capabilities=args.cap)
        except FileNotFoundError:
            print(f"[-] PIN list file not found: {args.pin_list}", file=sys.stderr)
            return 1
    else:
        if args.pin_range:
            parts = args.pin_range.split("-")
            start, end = parts[0], parts[1]
        else:
            start, end = "0000", "9999"
        print_and_log(
            f"[*] Brute-force PIN: {mac}  range: {start}-{end}  "
            f"delay: {args.delay}s  cap: {args.cap}", LOG__GENERAL,
        )
        result = bruteforcer.run_pin_brute(mac, pin_range(start, end), capabilities=args.cap)

    if result.success:
        value = result.pin if result.pin is not None else f"{result.passkey:06d}"
        print(f"\n[+] FOUND: correct value for {mac} = {value}")
        print(f"[*] Discovered in {result.attempts} attempts ({result.elapsed_seconds:.1f}s)")
        print(f"[*] Use 'bleep pair {mac} --pin {value}' to pair with the discovered PIN")
        return 0
    else:
        if result.errors:
            for err in result.errors:
                print(f"[-] {err}", file=sys.stderr)
        return 1


def _do_pair(mac: str, args) -> int:
    """Execute a single pairing attempt."""
    from bleep.dbuslayer.agent import PairingAgent
    from bleep.dbuslayer.agent_io import create_io_handler
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
    import bleep.dbuslayer.agent as _agent_mod

    # Pre-pair status check
    status = check_pair_status(mac)
    if status["paired"] and not args.reset:
        report_pair_status(mac, status)
        if status["fully_bonded"]:
            print("[*] Device is already fully bonded – nothing to do")
            print("[*] Use --reset to force-remove the existing bond and re-pair")
            return 0
        if not status["connected"]:
            print("[*] Device is already paired but not connected")
            print("[*] Use --reset to force-remove the existing bond and re-pair")
        return 0

    # Build IO handler
    if args.interactive:
        print_and_log(
            f"[*] Pair target: {mac}  mode: interactive  capability: {args.cap}  timeout: {args.timeout}s",
            LOG__GENERAL,
        )
        io_handler = create_io_handler("cli")
    else:
        pin = args.pin if args.pin is not None else "0000"
        if args.passkey is not None:
            print_and_log(
                f"[*] Pair target: {mac}  passkey: {args.passkey:06d}  capability: {args.cap}  timeout: {args.timeout}s",
                LOG__GENERAL,
            )
            io_handler = create_io_handler("auto", default_pin=pin, default_passkey=args.passkey)
        else:
            print_and_log(
                f"[*] Pair target: {mac}  PIN: {pin}  capability: {args.cap}  timeout: {args.timeout}s",
                LOG__GENERAL,
            )
            io_handler = create_io_handler("auto", default_pin=pin)

    if not register_pair_agent(io_handler, args.cap):
        return 1

    adapter = Adapter()
    device_path = resolve_device_for_pair(mac, adapter)
    if device_path is None:
        print(f"[-] Device {mac} not found. Ensure it is powered on and in range.", file=sys.stderr)
        return 1

    if args.reset:
        device_path = remove_stale_bond(mac, device_path, adapter)
        if device_path is None:
            print(f"[-] Device {mac} not re-discovered after bond removal.", file=sys.stderr)
            return 1

    agent = getattr(_agent_mod, "_DEFAULT_AGENT", None)
    if not isinstance(agent, PairingAgent):
        print("[-] Default agent is not a PairingAgent – cannot pair", file=sys.stderr)
        return 1

    set_trusted = not args.no_trust
    success = agent.pair_device(device_path, set_trusted=set_trusted, timeout=args.timeout)

    if not success:
        print(f"[-] Pairing with {mac} failed (see logs for details)", file=sys.stderr)
        return 1

    print(f"[+] Paired with {mac} successfully")

    if not args.no_connect:
        _post_pair_connect_cli(
            mac, device_path,
            activate_profiles=getattr(args, "activate_profiles", True),
        )

    return 0


def _post_pair_connect_cli(
    mac: str,
    device_path: str,
    *,
    activate_profiles: bool = True,
) -> None:
    """Best-effort post-pair connection report for CLI mode.

    Unlike the debug shell, the CLI does not maintain a persistent session,
    so we verify the connection state and run SDP for Classic devices.

    For Classic / dual-mode devices, when *activate_profiles* is True
    (default) and the SDP map advertises an audio service UUID, a
    best-effort ``Device1.Connect()`` is issued so BlueZ attaches its
    audio profile handlers and the device appears in
    ``bleep audio-profiles`` without needing a subsequent status probe.
    """
    from bleep.modes.debug_connect import get_device_transport

    transport = get_device_transport(device_path)
    print_and_log(f"[*] Device transport: {transport}", LOG__GENERAL)

    if transport in ("br-edr", "dual"):
        try:
            from bleep.ble_ops.classic.sdp import discover_services_sdp, build_svc_map
            records = discover_services_sdp(mac)
            svc_map = build_svc_map(records)
            rfcomm_count = sum(1 for v in svc_map.values() if v.get("channel") is not None)
            if svc_map:
                print_and_log(
                    f"[+] SDP enumeration: {len(svc_map)} service(s) ({rfcomm_count} with RFCOMM)",
                    LOG__GENERAL,
                )
            if activate_profiles:
                from bleep.pairing import (
                    _svc_map_has_audio_uuid, _activate_bluez_profiles,
                )
                from bleep.dbuslayer.device_classic import (
                    system_dbus__bluez_device__classic as _ClassicDevice,
                )
                if _svc_map_has_audio_uuid(svc_map):
                    _activate_bluez_profiles(_ClassicDevice(mac), mac)
        except Exception as exc:
            print_and_log(f"[*] SDP enumeration unavailable: {exc}", LOG__DEBUG)
    else:
        try:
            from bleep.ble_ops.le.connect import (
                connect_and_enumerate__bluetooth__low_energy as _connect_enum,
            )
            device, mapping, _, _ = _connect_enum(mac)
            svc_count = len(mapping) if mapping else 0
            print_and_log(f"[+] Connected to {mac} – {svc_count} GATT service(s) enumerated", LOG__GENERAL)
        except Exception as exc:
            print_and_log(f"[*] BLE connect/enumerate failed: {exc}", LOG__DEBUG)


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Run the ``bleep pair`` CLI mode."""
    argv = argv or sys.argv[2:]
    args = _build_arg_parser().parse_args(argv)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    mac = args.address.strip().upper()

    if args.check:
        return _do_check(mac)

    if args.probe:
        return _do_probe(mac, args.timeout)

    if args.brute or args.passkey_brute:
        return _do_brute(mac, args)

    return _do_pair(mac, args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
