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
from typing import TYPE_CHECKING

import dbus
import dbus.mainloop.glib  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from bleep.core.output import OutputContext

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__AGENT
from bleep.pairing import (
    find_device_path,
    resolve_device_for_pair,
    remove_stale_bond,
    register_pair_agent,
    check_pair_status,
    report_pair_status,
)

__all__ = ["run"]


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


def _do_probe(mac: str, timeout: int, adapter_name: str = "hci0") -> int:
    """Cycle IO capabilities to discover the device's auth requirements."""
    from bleep.dbuslayer.agent import attempt_downgrade_pair
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter

    # #6: an already-bonded device makes every capability attempt return
    # org.bluez.Error.AlreadyExists (workDir/bluez/src/error.c:btd_error_already_exists),
    # which the probe would misreport as "requires explicit auth". Short-circuit
    # with an accurate message instead of cycling capabilities against a live bond.
    _status = check_pair_status(mac)
    if _status.get("paired") or _status.get("fully_bonded"):
        print_and_log(
            f"[*] {mac} is already bonded (paired={_status.get('paired')}, "
            f"trusted={_status.get('trusted')}). Auth method cannot be probed "
            "against an existing bond — run 'pair --reset' first to re-probe.",
            LOG__GENERAL,
        )
        return 0

    adapter = Adapter(adapter_name)
    device_path = f"{adapter.adapter_path}/dev_{mac.replace(':', '_')}"

    print_and_log(f"[*] Probing auth method for {mac} (cycling capabilities)...", LOG__GENERAL)
    result = attempt_downgrade_pair(dbus.SystemBus(), device_path, timeout=timeout)

    print_and_log(f"\n{'='*60}", LOG__GENERAL)
    print_and_log(f"Auth Probe Results for {mac}", LOG__GENERAL)
    print_and_log(f"{'='*60}", LOG__GENERAL)
    for att in result["attempts"]:
        auth = att["auth_method"] or "none"
        print_and_log(f"  {att['capability']:<20}  {att['result']:<30}  auth={auth}", LOG__GENERAL)
    print_and_log(f"{'='*60}", LOG__GENERAL)

    # P2-B2: Persist probe result as pairing event with auth matrix
    try:
        from bleep.core import observations as _obs
        _obs.store_pairing_event(
            mac,
            method=result.get("auth_method"),
            result="success" if result["success"] else "failed",
            capabilities=result.get("capability"),
            auth_matrix={"attempts": result.get("attempts", [])},
        )
    except Exception:
        pass

    if result["success"]:
        print_and_log(f"[+] Paired successfully with '{result['capability']}' (auth: {result['auth_method']})", LOG__GENERAL)
        try:
            dev_iface = dbus.Interface(
                dbus.SystemBus().get_object("org.bluez", device_path),
                "org.bluez.Device1",
            )
            dev_iface.CancelPairing()
            print_and_log("[*] Pairing canceled (probe complete)", LOG__GENERAL)
        except dbus.exceptions.DBusException:
            pass
        return 0
    else:
        print_and_log("[-] No capability succeeded — device requires explicit auth", LOG__GENERAL)
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
            print_and_log(f"[-] PIN list file not found: {args.pin_list}", LOG__GENERAL)
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

    # P2-B2: Persist brute-force result
    try:
        from bleep.core import observations as _obs
        _obs.store_pairing_event(
            mac,
            method="brute_force",
            pin=result.pin if result.success and result.pin else (
                f"{result.passkey:06d}" if result.success and result.passkey is not None else None
            ),
            result="success" if result.success else "exhausted",
            capabilities=args.cap,
            brute_attempts=result.attempts,
            brute_duration=result.elapsed_seconds,
        )
    except Exception:
        pass

    if result.success:
        value = result.pin if result.pin is not None else f"{result.passkey:06d}"
        print_and_log(f"\n[+] FOUND: correct value for {mac} = {value}", LOG__GENERAL)
        print_and_log(f"[*] Discovered in {result.attempts} attempts ({result.elapsed_seconds:.1f}s)", LOG__GENERAL)
        print_and_log(f"[*] Use 'bleep pair {mac} --pin {value}' to pair with the discovered PIN", LOG__GENERAL)
        return 0
    else:
        if result.errors:
            for err in result.errors:
                print_and_log(f"[-] {err}", LOG__GENERAL)
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
            print_and_log("[*] Device is already fully bonded – nothing to do", LOG__GENERAL)
            print_and_log("[*] Use --reset to force-remove the existing bond and re-pair", LOG__GENERAL)
            return 0
        if not status["connected"]:
            print_and_log("[*] Device is already paired but not connected", LOG__GENERAL)
            print_and_log("[*] Use --reset to force-remove the existing bond and re-pair", LOG__GENERAL)
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

    # #5: defensive identity guard. A resolved BlueZ path encodes the device
    # MAC (``.../dev_AA_BB_CC_DD_EE_FF``). Refuse to pair if the resolved path
    # does not match the requested MAC — this prevents ever bonding a different
    # identity (e.g. a dual-mode peer's rotating LE resolvable-private address)
    # if resolution/rescan ever returns the wrong device.
    _expected_suffix = f"dev_{mac.replace(':', '_').upper()}"

    def _guard_identity(path: str) -> bool:
        if path and path.upper().endswith(_expected_suffix.upper()):
            return True
        _found = ""
        import re as _re
        _m = _re.search(r"dev_([0-9A-Fa-f_]{17})", path or "")
        if _m:
            _found = _m.group(1).replace("_", ":").upper()
        print_and_log(
            f"[-] Refusing to pair: requested {mac} but resolved a different "
            f"identity ({_found or path}). Aborting to avoid bonding the wrong device.",
            LOG__GENERAL,
        )
        return False

    adapter = Adapter(getattr(args, "adapter", None) or "hci0")
    device_path = resolve_device_for_pair(mac, adapter)
    if device_path is None:
        print_and_log(f"[-] Device {mac} not found. Ensure it is powered on and in range.", LOG__GENERAL)
        return 1
    if not _guard_identity(device_path):
        return 1

    if args.reset:
        device_path = remove_stale_bond(mac, device_path, adapter)
        if device_path is None:
            print_and_log(f"[-] Device {mac} not re-discovered after bond removal.", LOG__GENERAL)
            return 1
        if not _guard_identity(device_path):
            return 1

    agent = getattr(_agent_mod, "_DEFAULT_AGENT", None)
    if not isinstance(agent, PairingAgent):
        print_and_log("[-] Default agent is not a PairingAgent – cannot pair", LOG__GENERAL)
        return 1

    set_trusted = not args.no_trust
    success = agent.pair_device(device_path, set_trusted=set_trusted, timeout=args.timeout)

    # P2-B2: Persist pairing event
    try:
        from bleep.core import observations as _obs
        post_status = check_pair_status(mac) if success else None
        _obs.store_pairing_event(
            mac,
            method=agent.get_last_auth_type() if hasattr(agent, 'get_last_auth_type') else None,
            pin=getattr(args, 'pin', None) or getattr(args, 'passkey', None),
            result="success" if success else "failed",
            capabilities=getattr(args, 'cap', None),
            pre_pair_state=status if isinstance(status, dict) else None,
            post_pair_state=post_status,
        )
        if success:
            _obs.upsert_device(mac, paired=True, trusted=set_trusted)
    except Exception:
        pass

    if not success:
        print_and_log(f"[-] Pairing with {mac} failed (see logs for details)", LOG__GENERAL)
        return 1

    print_and_log(f"[+] Paired with {mac} successfully", LOG__GENERAL)

    if not args.no_connect:
        _post_pair_connect_cli(
            mac, device_path,
            activate_profiles=getattr(args, "activate_profiles", True),
            adapter_name=getattr(args, "adapter", None),
        )

    return 0


def _post_pair_connect_cli(
    mac: str,
    device_path: str,
    *,
    activate_profiles: bool = True,
    adapter_name: str | None = None,
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
                    _activate_bluez_profiles(_ClassicDevice(mac, adapter_name=adapter_name) if adapter_name else _ClassicDevice(mac), mac)
        except Exception as exc:
            print_and_log(f"[*] SDP enumeration unavailable: {exc}", LOG__DEBUG)
    else:
        try:
            from bleep.ble_ops.le.connect import (
                connect_and_enumerate__bluetooth__low_energy as _connect_enum,
            )
            device, mapping, _, _ = _connect_enum(mac, adapter_name=adapter_name)
            svc_count = len(mapping) if mapping else 0
            print_and_log(f"[+] Connected to {mac} – {svc_count} GATT service(s) enumerated", LOG__GENERAL)
        except Exception as exc:
            print_and_log(f"[*] BLE connect/enumerate failed: {exc}", LOG__DEBUG)


# ---------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------

def run(args: argparse.Namespace, output: "OutputContext | None" = None) -> int:
    """Execute pair mode with parsed args and optional OutputContext.

    This is the canonical entry point for Phase 3+ callers that pass a
    pre-parsed ``argparse.Namespace`` and an ``OutputContext``.  The older
    ``main(argv)`` wrapper remains for backward compatibility.
    """
    from bleep.core.output import OutputContext
    from bleep.core.log import set_output_mode

    if output is None:
        output = OutputContext()

    set_output_mode(output.mode)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    mac = args.address.strip().upper()

    if args.check:
        return _do_check(mac)

    if args.probe:
        return _do_probe(mac, args.timeout, getattr(args, "adapter", "hci0"))

    if args.brute or args.passkey_brute:
        return _do_brute(mac, args)

    return _do_pair(mac, args)


def main(argv: list[str] | None = None) -> int:
    """Run the ``bleep pair`` CLI mode (backward-compatible wrapper)."""
    argv = argv or sys.argv[2:]
    args = _build_arg_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
