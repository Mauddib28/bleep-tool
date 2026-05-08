"""BLEEP ``classic-connect`` CLI mode — connect to a Bluetooth Classic device.

BlueZ ``Device1.Connect()`` requires a registered profile handler for at
least one of the remote services.  For devices that only expose raw RFCOMM
services (no A2DP, HFP, etc.), it fails with
``br-connection-profile-unavailable``.

This mode takes the proven alternative path:

1. Ensure the target is paired (auto-pair with sensible defaults).
2. SDP discovery — enumerate services and RFCOMM channels.
3. Open a raw RFCOMM socket — implicitly creates the ACL link.

Usage examples::

    bleep classic-connect AA:BB:CC:DD:EE:FF
    bleep classic-connect AA:BB:CC:DD:EE:FF --keep
    bleep classic-connect AA:BB:CC:DD:EE:FF --channel 3
    bleep classic-connect AA:BB:CC:DD:EE:FF --check
    bleep classic-connect AA:BB:CC:DD:EE:FF --no-pair
"""

from __future__ import annotations

import argparse
import signal
import sys

import dbus
import dbus.mainloop.glib  # type: ignore[import-untyped]

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.pairing import (
    find_device_path,
    resolve_device_for_pair,
    check_pair_status,
    report_pair_status,
    register_pair_agent,
    classic_connect_sdp_rfcomm,
)


# ---------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bleep classic-connect",
        add_help=True,
        description="Connect to a Bluetooth Classic device via SDP + RFCOMM",
    )
    p.add_argument("address", help="Target Bluetooth MAC address")
    p.add_argument(
        "--check", action="store_true",
        help="Check pair/connection status only — do not connect",
    )
    p.add_argument(
        "--no-pair", action="store_true",
        help="Skip auto-pair — fail if device is not already paired",
    )
    p.add_argument(
        "--channel", type=int, default=None,
        help="Specific RFCOMM channel to connect (default: first from SDP)",
    )
    p.add_argument(
        "--keep", action="store_true",
        help="Hold the RFCOMM socket open (blocks until Ctrl+C)",
    )
    p.add_argument(
        "--timeout", type=int, default=60,
        help="Pairing timeout in seconds (default: 60)",
    )
    p.add_argument(
        "--adapter", default="hci0",
        help="Bluetooth adapter name (default: hci0)",
    )
    p.add_argument(
        "--no-profiles", dest="activate_profiles", action="store_false",
        default=True,
        help=(
            "Skip the best-effort BlueZ Device1.Connect() that attaches "
            "profile handlers after RFCOMM bring-up.  Use when the "
            "target is a raw-RFCOMM device that should not incur "
            "br-connection-profile-unavailable noise."
        ),
    )
    return p


# ---------------------------------------------------------------------
# Auto-pair helper
# ---------------------------------------------------------------------

def _ensure_paired(mac: str, timeout: int) -> bool:
    """Pair with the device if not already paired.  Returns True on success."""
    from bleep.dbuslayer.agent import PairingAgent
    from bleep.dbuslayer.agent_io import create_io_handler
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
    import bleep.dbuslayer.agent as _agent_mod

    io_handler = create_io_handler("auto", default_pin="0000")
    if not register_pair_agent(io_handler, "KeyboardDisplay"):
        return False

    adapter = Adapter()
    device_path = resolve_device_for_pair(mac, adapter)
    if device_path is None:
        print(f"[-] Device {mac} not found", file=sys.stderr)
        return False

    agent = getattr(_agent_mod, "_DEFAULT_AGENT", None)
    if not isinstance(agent, PairingAgent):
        print("[-] Default agent is not a PairingAgent", file=sys.stderr)
        return False

    success = agent.pair_device(device_path, set_trusted=True, timeout=timeout)
    if success:
        print_and_log(f"[+] Paired with {mac}", LOG__GENERAL)
    else:
        print(f"[-] Pairing with {mac} failed", file=sys.stderr)
    return success


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Run the ``bleep classic-connect`` CLI mode."""
    argv = argv if argv is not None else sys.argv[2:]
    args = _build_arg_parser().parse_args(argv)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    mac = args.address.strip().upper()

    # --check: report status and exit
    if args.check:
        status = check_pair_status(mac)
        report_pair_status(mac, status)
        return 0

    # Ensure device is paired
    status = check_pair_status(mac)
    if not status.get("paired"):
        if args.no_pair:
            print(f"[-] Device {mac} is not paired (use 'bleep pair' first or remove --no-pair)")
            return 1
        print_and_log(f"[*] Device {mac} not paired — auto-pairing…", LOG__GENERAL)
        if not _ensure_paired(mac, args.timeout):
            return 1

    # SDP + RFCOMM connect
    result = classic_connect_sdp_rfcomm(
        mac,
        channel=args.channel,
        open_keepalive=True,
        activate_profiles=args.activate_profiles,
    )
    svc_map = result["svc_map"]
    sock = result["sock"]
    if result.get("profiles_activated"):
        print("[+] BlueZ audio profile handlers activated")

    if not svc_map:
        print(f"[*] No SDP services found for {mac}")
        print("[*] Device may be out of range or not exposing services")
        return 1

    # Print service summary
    rfcomm_count = sum(1 for v in svc_map.values() if v.get("channel") is not None)
    print(f"\n[+] Classic connect to {mac} — {len(svc_map)} services ({rfcomm_count} with RFCOMM)")

    if sock and result["channel"] is not None:
        print(f"[+] RFCOMM channel {result['channel']} connected")
    elif rfcomm_count > 0:
        print("[*] RFCOMM keepalive could not be established")
        print("[*] Profile commands (classic-pbap, classic-map, etc.) create their own sessions")

    if not args.keep:
        if sock:
            sock.close()
        return 0

    # --keep: hold the socket open until Ctrl+C
    if not sock:
        print("[-] No RFCOMM socket to keep alive — exiting")
        return 1

    print(f"[*] Holding RFCOMM keepalive on channel {result['channel']} — Ctrl+C to disconnect")

    def _sigint_handler(sig, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sigint_handler)
    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[*] Closing keepalive socket")
        try:
            sock.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
