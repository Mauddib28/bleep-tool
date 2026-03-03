"""
Audio recon runner: enumerate Bluetooth audio cards, profiles, sources/sinks,
optionally play test file and record from interfaces, analyse with sox.

Orchestrates AudioToolsHelper for backend detection, per-profile enumeration,
play/record, and sox analysis. Output is a structured result for tracking
and optional JSON export.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from bleep.ble_ops.audio_tools import AudioToolsHelper
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER

__all__ = ["run_audio_recon"]


# Default recording duration (seconds) per interface
DEFAULT_RECORD_DURATION = 8
# Default directory for temporary recordings (README: /tmp for space concerns)
DEFAULT_RECORD_DIR = "/tmp"


def run_audio_recon(
    mac_filter: Optional[str] = None,
    test_file: Optional[str] = None,
    do_play: bool = True,
    do_record: bool = True,
    record_duration_sec: int = DEFAULT_RECORD_DURATION,
    record_dir: Optional[str] = None,
    output_json_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run audio recon: enumerate BlueZ cards and profiles, optionally play/record, analyse with sox.

    Parameters
    ----------
    mac_filter : Optional[str]
        If set, only include cards that match this MAC (normalized comparison).
    test_file : Optional[str]
        Path to test audio file for playback. If None, playback is skipped.
    do_play : bool
        Whether to play test file to each sink (requires test_file).
    do_record : bool
        Whether to record from each source/sink interface to record_dir.
    record_duration_sec : int
        Duration per recording in seconds.
    record_dir : Optional[str]
        Directory for recording files. Defaults to /tmp.
    output_json_path : Optional[str]
        If set, write the full structured result to this path.

    Returns
    -------
    Dict[str, Any]
        Structured result with backend, cards, profiles, interfaces, recordings, sox results.
    """
    record_dir = record_dir or DEFAULT_RECORD_DIR
    helper = AudioToolsHelper()
    backend = helper.get_audio_backend()
    result: Dict[str, Any] = {
        "backend": backend,
        "cards": [],
        "bluealsa_pcms": [],
        "recordings": [],
        "errors": [],
    }

    def _norm(m: str) -> str:
        return (m or "").replace(":", "").replace("-", "").lower()

    # ---- BlueALSA path ------------------------------------------------
    # Run when BlueALSA is the sole backend OR when it is available
    # alongside another backend (supplementary enumeration).
    if backend == "bluealsa" or helper.is_bluealsa_running():
        _recon_bluealsa(
            helper, result, mac_filter, test_file,
            do_play, do_record, record_duration_sec, record_dir,
        )

    # ---- PipeWire native path (no PA compat) --------------------------
    if backend == "pipewire_native":
        _recon_pipewire_native(
            helper, result, mac_filter, test_file,
            do_play, do_record, record_duration_sec, record_dir,
        )

    # ---- PulseAudio / PipeWire-with-PA-compat path --------------------
    if backend in ("pulseaudio", "pipewire"):
        _recon_pulseaudio(
            helper, result, mac_filter, test_file,
            do_play, do_record, record_duration_sec, record_dir,
        )

    # If no data collected at all, note the gap
    if not result["cards"] and not result["bluealsa_pcms"]:
        if backend == "none":
            print_and_log("[!] No supported audio backend detected", LOG__USER)
            result["errors"].append("backend_not_supported")
        else:
            print_and_log("[!] No Bluetooth audio devices found", LOG__USER)
            result["errors"].append("no_bluez_devices")

    if output_json_path:
        _write_result(result, output_json_path)
        print_and_log(f"[+] Wrote recon result to {output_json_path}", LOG__USER)

    return result


# ------------------------------------------------------------------
# Internal recon helpers (one per backend family)
# ------------------------------------------------------------------

def _recon_bluealsa(
    helper: "AudioToolsHelper",
    result: Dict[str, Any],
    mac_filter: Optional[str],
    test_file: Optional[str],
    do_play: bool,
    do_record: bool,
    duration: int,
    record_dir: str,
) -> None:
    """Enumerate and optionally play/record via BlueALSA PCMs."""
    pcms = helper.list_bluealsa_pcms()
    if not pcms:
        return

    def _norm(m: str) -> str:
        return (m or "").replace(":", "").replace("-", "").lower()

    for pcm in pcms:
        mac = pcm.get("mac_address")
        if mac_filter and _norm(mac) != _norm(mac_filter):
            continue

        alsa_dev = pcm.get("alsa_device", "")
        direction = pcm.get("direction", "")
        profile = pcm.get("profile", "")
        pcm_entry: Dict[str, Any] = dict(pcm)
        result["bluealsa_pcms"].append(pcm_entry)

        if direction == "sink" and do_play and test_file and os.path.isfile(test_file):
            print_and_log(
                f"[*] BlueALSA: playing test file to {alsa_dev}",
                LOG__GENERAL,
            )
            pcm_entry["play_ok"] = helper.play_to_bluealsa_pcm(
                alsa_dev, test_file, duration,
            )

        if do_record and alsa_dev:
            safe = alsa_dev.replace(":", "_").replace(",", "_").replace("=", "_")[:60]
            out_path = os.path.join(record_dir, f"bleep_recon_ba_{safe}.wav")
            print_and_log(
                f"[*] BlueALSA: recording from {alsa_dev} -> {out_path}",
                LOG__GENERAL,
            )
            ok = helper.record_from_bluealsa_pcm(alsa_dev, out_path, duration)
            has_audio = (
                helper.check_audio_file_has_content(out_path)
                if ok and os.path.isfile(out_path) else False
            )
            result["recordings"].append({
                "interface": alsa_dev,
                "role": direction,
                "profile": profile,
                "card_index": "bluealsa",
                "output_path": out_path,
                "record_ok": ok,
                "has_audio": has_audio,
            })
            pcm_entry["record_path"] = out_path
            pcm_entry["record_ok"] = ok
            pcm_entry["has_audio"] = has_audio


def _recon_pipewire_native(
    helper: "AudioToolsHelper",
    result: Dict[str, Any],
    mac_filter: Optional[str],
    test_file: Optional[str],
    do_play: bool,
    do_record: bool,
    duration: int,
    record_dir: str,
) -> None:
    """Enumerate and optionally play/record via PipeWire native tools."""
    nodes = helper._get_pipewire_bluez_nodes()
    if not nodes:
        return

    def _norm(m: str) -> str:
        return (m or "").replace(":", "").replace("-", "").lower()

    # Group nodes by MAC to present them similarly to PA cards
    macs_seen: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        mac = node.get("mac_address")
        if mac_filter and _norm(mac) != _norm(mac_filter):
            continue
        if mac not in macs_seen:
            macs_seen[mac] = {
                "index": str(node.get("node_id", "")),
                "name": node.get("node_name", ""),
                "mac_address": mac,
                "profiles": [],
            }
            # Collect profile info from the first node
            pw_profiles = node.get("profiles", [])
            if pw_profiles:
                macs_seen[mac]["profiles"] = [
                    {"name": p.get("name", ""), "sources": [], "sinks": []}
                    for p in pw_profiles
                ]

    for mac, card_info in macs_seen.items():
        result["cards"].append(card_info)

    # Enumerate sources/sinks across all matching nodes
    ss = helper._get_pipewire_sources_and_sinks()
    for sink in ss.get("sinks", []):
        if mac_filter and _norm(sink.get("mac_address")) != _norm(mac_filter):
            continue
        node_id = str(sink.get("node_id", ""))
        sink_name = sink.get("name", node_id)

        if do_play and test_file and os.path.isfile(test_file):
            print_and_log(
                f"[*] PW-native: playing test file to {sink_name}",
                LOG__GENERAL,
            )
            sink["play_ok"] = helper.play_to_sink(
                node_id, test_file, duration,
            )

        if do_record:
            safe = sink_name.replace("/", "_").replace(".", "_")[:60]
            out_path = os.path.join(record_dir, f"bleep_recon_pw_{safe}.wav")
            print_and_log(
                f"[*] PW-native: recording from sink {sink_name} -> {out_path}",
                LOG__GENERAL,
            )
            ok = helper.record_from_source(node_id, out_path, duration)
            has_audio = (
                helper.check_audio_file_has_content(out_path)
                if ok and os.path.isfile(out_path) else False
            )
            result["recordings"].append({
                "interface": sink_name,
                "role": sink.get("role", "unknown"),
                "profile": "pw-native",
                "card_index": node_id,
                "output_path": out_path,
                "record_ok": ok,
                "has_audio": has_audio,
            })

    for source in ss.get("sources", []):
        if mac_filter and _norm(source.get("mac_address")) != _norm(mac_filter):
            continue
        node_id = str(source.get("node_id", ""))
        source_name = source.get("name", node_id)

        if do_record:
            safe = source_name.replace("/", "_").replace(".", "_")[:60]
            out_path = os.path.join(record_dir, f"bleep_recon_pw_{safe}.wav")
            print_and_log(
                f"[*] PW-native: recording from source {source_name} -> {out_path}",
                LOG__GENERAL,
            )
            ok = helper.record_from_source(node_id, out_path, duration)
            has_audio = (
                helper.check_audio_file_has_content(out_path)
                if ok and os.path.isfile(out_path) else False
            )
            result["recordings"].append({
                "interface": source_name,
                "role": source.get("role", "unknown"),
                "profile": "pw-native",
                "card_index": node_id,
                "output_path": out_path,
                "record_ok": ok,
                "has_audio": has_audio,
            })


def _recon_pulseaudio(
    helper: "AudioToolsHelper",
    result: Dict[str, Any],
    mac_filter: Optional[str],
    test_file: Optional[str],
    do_play: bool,
    do_record: bool,
    duration: int,
    record_dir: str,
) -> None:
    """Enumerate and optionally play/record via PulseAudio (or PipeWire PA-compat)."""

    def _norm(m: str) -> str:
        return (m or "").replace(":", "").replace("-", "").lower()

    cards = helper.get_bluez_cards()
    if not cards:
        return

    for card in cards:
        card_index = card.get("index", "")
        card_name = card.get("name", "")
        mac = helper.extract_mac_from_alsa_device(card_name)

        if mac_filter and _norm(mac) != _norm(mac_filter):
            continue

        profiles = helper.get_profiles_for_card(card_index)
        card_info: Dict[str, Any] = {
            "index": card_index,
            "name": card_name,
            "mac_address": mac,
            "profiles": [],
        }
        result["cards"].append(card_info)

        for profile_name in profiles:
            if profile_name.lower() == "off":
                continue
            if not helper.set_card_profile(card_index, profile_name):
                continue
            sources_sinks = helper.get_sources_and_sinks_for_card_profile(card_index)
            profile_info: Dict[str, Any] = {
                "name": profile_name,
                "sources": sources_sinks.get("sources", []),
                "sinks": sources_sinks.get("sinks", []),
            }
            card_info["profiles"].append(profile_info)

            if do_play and test_file and os.path.isfile(test_file):
                for sink in profile_info["sinks"]:
                    sink_name = sink.get("name")
                    if not sink_name:
                        continue
                    print_and_log(
                        f"[*] Playing test file to {sink_name} ({sink.get('role', 'unknown')})",
                        LOG__GENERAL,
                    )
                    ok = helper.play_to_sink(sink_name, test_file, duration_sec=duration)
                    sink["play_ok"] = ok

            if do_record:
                for _label, ifaces in [("sources", profile_info["sources"]),
                                        ("sinks", profile_info["sinks"])]:
                    for iface in ifaces:
                        iface_name = iface.get("name")
                        if not iface_name:
                            continue
                        role = iface.get("role", "unknown")
                        safe_name = iface_name.replace("/", "_").replace(".", "_")[:60]
                        out_path = os.path.join(
                            record_dir,
                            f"bleep_recon_{safe_name}_{profile_name}.wav",
                        )
                        print_and_log(
                            f"[*] Recording from {iface_name} ({role}) -> {out_path}",
                            LOG__GENERAL,
                        )
                        ok = helper.record_from_source(
                            iface_name, out_path, duration_sec=duration,
                        )
                        has_audio = (
                            helper.check_audio_file_has_content(out_path)
                            if ok and os.path.isfile(out_path) else False
                        )
                        result["recordings"].append({
                            "interface": iface_name,
                            "role": role,
                            "profile": profile_name,
                            "card_index": card_index,
                            "output_path": out_path,
                            "record_ok": ok,
                            "has_audio": has_audio,
                        })
                        iface["record_path"] = out_path
                        iface["record_ok"] = ok
                        iface["has_audio"] = has_audio

        if profiles:
            non_off = [p for p in profiles if p.lower() != "off"]
            if non_off and card_index:
                helper.set_card_profile(card_index, non_off[0])


def _write_result(result: Dict[str, Any], path: str) -> None:
    """Write result dict to JSON file."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print_and_log(f"[-] Failed to write {path}: {e}", LOG__USER)
