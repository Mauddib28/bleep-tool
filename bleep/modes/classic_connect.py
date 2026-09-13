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
from typing import TYPE_CHECKING

import dbus
import dbus.mainloop.glib  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from bleep.core.output import OutputContext

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

def _ensure_paired(mac: str, timeout: int, adapter_name: str = "hci0") -> bool:
    """Pair with the device if not already paired.  Returns True on success."""
    from bleep.dbuslayer.agent import PairingAgent
    from bleep.dbuslayer.agent_io import create_io_handler
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
    import bleep.dbuslayer.agent as _agent_mod

    io_handler = create_io_handler("auto", default_pin="0000")
    if not register_pair_agent(io_handler, "KeyboardDisplay"):
        return False

    adapter = Adapter(adapter_name)
    device_path = resolve_device_for_pair(mac, adapter)
    if device_path is None:
        print_and_log(f"[-] Device {mac} not found", LOG__GENERAL)
        return False

    agent = getattr(_agent_mod, "_DEFAULT_AGENT", None)
    if not isinstance(agent, PairingAgent):
        print_and_log("[-] Default agent is not a PairingAgent", LOG__GENERAL)
        return False

    success = agent.pair_device(device_path, set_trusted=True, timeout=timeout)
    if success:
        print_and_log(f"[+] Paired with {mac}", LOG__GENERAL)
    else:
        print_and_log(f"[-] Pairing with {mac} failed", LOG__GENERAL)
    return success


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------

def run(args: argparse.Namespace, output: OutputContext | None = None) -> int:
    """Execute classic-connect with parsed args and optional OutputContext.

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
        status = check_pair_status(mac)
        report_pair_status(mac, status)
        return 0

    status = check_pair_status(mac)
    if not status.get("paired"):
        if args.no_pair:
            print_and_log(f"[-] Device {mac} is not paired (use 'bleep pair' first or remove --no-pair)", LOG__GENERAL)
            return 1
        print_and_log(f"[*] Device {mac} not paired — auto-pairing…", LOG__GENERAL)
        if not _ensure_paired(mac, args.timeout, getattr(args, "adapter", "hci0")):
            return 1

    result = classic_connect_sdp_rfcomm(
        mac,
        channel=args.channel,
        open_keepalive=True,
        activate_profiles=args.activate_profiles,
        adapter_name=getattr(args, "adapter", None),
    )
    svc_map = result["svc_map"]
    sock = result["sock"]
    if result.get("profiles_activated"):
        print_and_log("[+] BlueZ audio profile handlers activated", LOG__GENERAL)

    if not svc_map:
        print_and_log(f"[*] No SDP services found for {mac}", LOG__GENERAL)
        print_and_log("[*] Device may be out of range or not exposing services", LOG__GENERAL)
        return 1

    rfcomm_count = sum(1 for v in svc_map.values() if v.get("channel") is not None)
    # N3: distinguish services-advertising-RFCOMM from the distinct channel
    # numbers actually attempted (multiple services often share one channel),
    # so this count aligns with the "distinct RFCOMM channel(s) attempted"
    # failure message and the keep-alive loop's de-duplicated candidate list.
    _distinct_channels = len({
        v.get("channel") for v in svc_map.values()
        if isinstance(v, dict) and v.get("channel") is not None
    })
    print_and_log(
        f"\n[+] Classic connect to {mac} — {len(svc_map)} services "
        f"({rfcomm_count} advertising RFCOMM across {_distinct_channels} distinct channel(s))",
        LOG__GENERAL,
    )

    if sock and result["channel"] is not None:
        print_and_log(f"[+] RFCOMM channel {result['channel']} connected", LOG__GENERAL)
    elif rfcomm_count > 0:
        print_and_log("[*] RFCOMM keepalive could not be established", LOG__GENERAL)
        print_and_log("[*] Profile commands (classic-pbap, classic-map, etc.) create their own sessions", LOG__GENERAL)

    if not args.keep:
        if sock:
            sock.close()
            return 0
        # #13: SDP advertised RFCOMM channel(s) but none could be opened — the
        # connection attempt failed, so do not report success. (A device with
        # no RFCOMM channels at all is not a failure of this RFCOMM path.)
        if rfcomm_count > 0:
            print_and_log(
                f"[-] {mac}: {_distinct_channels} distinct RFCOMM channel(s) attempted "
                f"(from {rfcomm_count} advertising service(s)) — none connectable",
                LOG__GENERAL,
            )
            return 1
        return 0

    if not sock:
        print_and_log("[-] No RFCOMM socket to keep alive — exiting", LOG__GENERAL)
        return 1

    print_and_log(f"[*] Holding RFCOMM keepalive on channel {result['channel']} — Ctrl+C to disconnect", LOG__GENERAL)

    def _sigint_handler(sig, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sigint_handler)
    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        print_and_log("\n[*] Closing keepalive socket", LOG__GENERAL)
        try:
            sock.close()
        except Exception:
            pass

    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the ``bleep classic-connect`` CLI mode (backward-compatible wrapper)."""
    argv = argv if argv is not None else sys.argv[2:]
    args = _build_arg_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
