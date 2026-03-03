"""BLEEP Amusica mode – automated Bluetooth audio target discovery and manipulation.

Provides CLI subcommands for the full Amusica workflow: scanning for
audio-capable devices, attempting JustWorks connections, performing audio
reconnaissance, and manipulating audio on connected targets (halt, inject,
record, control).

All heavy lifting delegates to existing BLEEP primitives in
``ble_ops.amusica``, ``ble_ops.audio_recon``, ``ble_ops.audio_tools``,
and ``modes.media``.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER

__all__ = ["main"]


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def _cmd_scan(args: argparse.Namespace) -> int:
    """Scan for audio-capable devices, attempt connections, report results."""
    from bleep.ble_ops.amusica import (
        scan_audio_targets,
        assess_targets,
        summarise_assessment,
    )

    targets = scan_audio_targets(
        timeout=args.timeout,
        adapter_name=getattr(args, "adapter", None),
    )

    if not targets:
        print_and_log("[!] No audio-capable devices discovered", LOG__USER)
        return 0

    if args.connect:
        targets = assess_targets(
            targets,
            do_recon=not args.no_recon,
            recon_test_file=getattr(args, "test_file", None),
            record_dir=getattr(args, "record_dir", "/tmp"),
            record_duration=getattr(args, "duration", 8),
        )

        summary = summarise_assessment(targets)
        print_and_log("\n[=] Amusica Assessment Summary", LOG__USER)
        print_and_log(f"  Scanned:           {summary['total_scanned']}", LOG__USER)
        print_and_log(f"  JustWorks OK:      {summary['justworks_accessible']}", LOG__USER)
        print_and_log(f"  Auth required:     {summary['auth_required']}", LOG__USER)
        print_and_log(f"  Failed:            {summary['failed']}", LOG__USER)
        print_and_log(f"  Vulnerable:        {len(summary['vulnerable'])}", LOG__USER)

        for v in summary["vulnerable"]:
            print_and_log(
                f"    {v['name']} ({v['address']}) – "
                f"{v['recordings_with_audio']} recording(s) with audio",
                LOG__USER,
            )
    else:
        print_and_log("\n[=] Audio-Capable Devices", LOG__USER)
        for t in targets:
            name = t.get("name") or t.get("alias") or t.get("address")
            rssi = t.get("rssi", "?")
            uuids_str = ", ".join(
                u["name"] for u in t.get("audio_uuids", [])
            )
            print_and_log(
                f"  {name} ({t['address']})  RSSI={rssi}  [{uuids_str}]",
                LOG__USER,
            )

    if args.out:
        _write_json(targets, args.out)

    return 0


def _cmd_halt(args: argparse.Namespace) -> int:
    """Halt all audio on a connected target device."""
    from bleep.ble_ops.audio_tools import AudioToolsHelper

    helper = AudioToolsHelper()
    result = helper.halt_audio_for_device(args.device)

    print_and_log(f"[*] Halt result for {args.device}:", LOG__USER)
    print_and_log(f"  Paused:       {result['paused']}", LOG__USER)
    print_and_log(f"  Volume zeroed:{result['volume_zeroed']}", LOG__USER)
    print_and_log(f"  Profile off:  {result['profile_off']}", LOG__USER)
    if result["errors"]:
        for e in result["errors"]:
            print_and_log(f"  [!] {e}", LOG__USER)

    return 0 if (result["paused"] or result["volume_zeroed"] or result["profile_off"]) else 1


def _cmd_control(args: argparse.Namespace) -> int:
    """Proxy to existing media control (play/pause/stop/next/prev/volume)."""
    from bleep.modes.media import control_media_device

    value = None
    if args.action == "volume" and args.value is not None:
        value = int(args.value)

    success = control_media_device(args.device, args.action, value)
    return 0 if success else 1


def _cmd_inject(args: argparse.Namespace) -> int:
    """Play an audio file into a target device's audio sink."""
    from bleep.ble_ops.audio_tools import AudioToolsHelper

    helper = AudioToolsHelper()

    if args.sink:
        sink_id = args.sink
    else:
        cards = helper.get_bluez_cards()
        sink_id = _find_sink_for_mac(helper, cards, args.device)
        if not sink_id:
            print_and_log(
                f"[-] No audio sink found for {args.device}. "
                "Use --sink to specify one explicitly.",
                LOG__USER,
            )
            return 1

    print_and_log(
        f"[*] Injecting {args.file} → {sink_id}",
        LOG__USER,
    )
    ok = helper.play_to_sink(sink_id, args.file, duration_sec=args.duration)
    if ok:
        print_and_log("[+] Injection complete", LOG__USER)
    else:
        print_and_log("[-] Injection failed", LOG__USER)
    return 0 if ok else 1


def _cmd_record(args: argparse.Namespace) -> int:
    """Record audio from a target device's source/sink interfaces."""
    from bleep.ble_ops.audio_tools import AudioToolsHelper

    helper = AudioToolsHelper()

    if args.source:
        source_id = args.source
    else:
        cards = helper.get_bluez_cards()
        source_id = _find_source_for_mac(helper, cards, args.device)
        if not source_id:
            print_and_log(
                f"[-] No audio source found for {args.device}. "
                "Use --source to specify one explicitly.",
                LOG__USER,
            )
            return 1

    print_and_log(
        f"[*] Recording from {source_id} → {args.output} ({args.duration}s)",
        LOG__USER,
    )
    ok = helper.record_from_source(source_id, args.output, duration_sec=args.duration)
    if ok:
        has_audio = helper.check_audio_file_has_content(args.output)
        print_and_log(
            f"[+] Recording saved – audio content: {'yes' if has_audio else 'no'}",
            LOG__USER,
        )
    else:
        print_and_log("[-] Recording failed", LOG__USER)
    return 0 if ok else 1


def _cmd_status(args: argparse.Namespace) -> int:
    """Show current audio state of a connected target."""
    from bleep.ble_ops.audio_tools import AudioToolsHelper
    from bleep.modes.media import control_media_device

    helper = AudioToolsHelper()

    cards = helper.get_bluez_cards()
    mac_norm = args.device.replace(":", "").lower()

    card_found = False
    for card in cards:
        card_mac = helper.extract_mac_from_alsa_device(card.get("name", ""))
        if not card_mac or card_mac.replace(":", "").lower() != mac_norm:
            continue
        card_found = True
        card_index = card.get("index", "")
        print_and_log(f"[+] Card: {card.get('name')} (index {card_index})", LOG__USER)

        profiles = helper.get_profiles_for_card(card_index)
        print_and_log(f"    Profiles: {', '.join(profiles) if profiles else 'none'}", LOG__USER)

        ss = helper.get_sources_and_sinks_for_card_profile(card_index)
        for s in ss.get("sources", []):
            print_and_log(f"    Source: {s.get('name')} (role={s.get('role')})", LOG__USER)
        for s in ss.get("sinks", []):
            print_and_log(f"    Sink:   {s.get('name')} (role={s.get('role')})", LOG__USER)

    if not card_found:
        print_and_log(f"[!] No audio card found for {args.device}", LOG__USER)

    control_media_device(args.device, "info")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_sink_for_mac(
    helper: "AudioToolsHelper",
    cards: list,
    mac: str,
) -> Optional[str]:
    """Return the first sink name that belongs to *mac*, or None."""
    mac_norm = mac.replace(":", "").lower()
    for card in cards:
        card_mac = helper.extract_mac_from_alsa_device(card.get("name", ""))
        if not card_mac or card_mac.replace(":", "").lower() != mac_norm:
            continue
        ss = helper.get_sources_and_sinks_for_card_profile(card.get("index", ""))
        for s in ss.get("sinks", []):
            if s.get("name"):
                return s["name"]
    return None


def _find_source_for_mac(
    helper: "AudioToolsHelper",
    cards: list,
    mac: str,
) -> Optional[str]:
    """Return the first source name that belongs to *mac*, or None."""
    mac_norm = mac.replace(":", "").lower()
    for card in cards:
        card_mac = helper.extract_mac_from_alsa_device(card.get("name", ""))
        if not card_mac or card_mac.replace(":", "").lower() != mac_norm:
            continue
        ss = helper.get_sources_and_sinks_for_card_profile(card.get("index", ""))
        for s in ss.get("sources", []):
            if s.get("name"):
                return s["name"]
    return None


def _write_json(data: object, path: str) -> None:
    """Write *data* to *path* as indented JSON."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        print_and_log(f"[+] Wrote results to {path}", LOG__USER)
    except OSError as exc:
        print_and_log(f"[-] Failed to write {path}: {exc}", LOG__USER)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bleep amusica",
        description="Amusica – Bluetooth audio target discovery and manipulation",
    )
    sub = parser.add_subparsers(dest="command", help="Amusica subcommand")

    # scan
    sp_scan = sub.add_parser("scan", help="Scan for audio-capable Bluetooth devices")
    sp_scan.add_argument("--timeout", type=int, default=15, help="Scan duration in seconds (default: 15)")
    sp_scan.add_argument("--adapter", help="HCI adapter name (e.g. hci1)")
    sp_scan.add_argument("--connect", action="store_true", help="Attempt JustWorks connection to each target")
    sp_scan.add_argument("--no-recon", action="store_true", help="Skip audio recon on connected targets")
    sp_scan.add_argument("--test-file", help="Audio file for playback testing during recon")
    sp_scan.add_argument("--record-dir", default="/tmp", help="Directory for recordings (default: /tmp)")
    sp_scan.add_argument("--duration", type=int, default=8, help="Recording duration per interface (default: 8)")
    sp_scan.add_argument("--out", help="Write full results to JSON file")

    # halt
    sp_halt = sub.add_parser("halt", help="Halt all audio on a connected target")
    sp_halt.add_argument("device", help="Target device MAC address")

    # control
    sp_ctrl = sub.add_parser("control", help="Media playback control (play/pause/stop/next/prev/volume/info)")
    sp_ctrl.add_argument("device", help="Target device MAC address")
    sp_ctrl.add_argument("action", choices=["play", "pause", "stop", "next", "previous", "volume", "info"])
    sp_ctrl.add_argument("--value", help="Value for volume (0-127)")

    # inject
    sp_inj = sub.add_parser("inject", help="Play audio file into target device's audio sink")
    sp_inj.add_argument("device", help="Target device MAC address")
    sp_inj.add_argument("file", help="Audio file path")
    sp_inj.add_argument("--sink", help="Explicit sink name (auto-detected if omitted)")
    sp_inj.add_argument("--duration", type=int, default=30, help="Max playback duration in seconds (default: 30)")

    # record
    sp_rec = sub.add_parser("record", help="Record audio from target device")
    sp_rec.add_argument("device", help="Target device MAC address")
    sp_rec.add_argument("output", help="Output file path")
    sp_rec.add_argument("--source", help="Explicit source name (auto-detected if omitted)")
    sp_rec.add_argument("--duration", type=int, default=8, help="Recording duration in seconds (default: 8)")

    # status
    sp_st = sub.add_parser("status", help="Show audio state of a connected target")
    sp_st.add_argument("device", help="Target device MAC address")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    """Main entry point for the Amusica mode.

    Parameters
    ----------
    argv : Optional[list]
        Argument list (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "scan": _cmd_scan,
        "halt": _cmd_halt,
        "control": _cmd_control,
        "inject": _cmd_inject,
        "record": _cmd_record,
        "status": _cmd_status,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
