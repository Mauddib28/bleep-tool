"""System-tool audio playback and recording for Bluetooth devices.

Delegates to the host audio daemon (PulseAudio, PipeWire, BlueALSA) via
subprocess tools (``paplay``, ``pw-play``, ``aplay``, etc.) rather than
acquiring D-Bus ``MediaTransport1`` file descriptors directly.  This
mirrors how ``audio-recon`` operates and works **with** the audio daemon
instead of competing for transport ownership.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from bleep.ble_ops.audio.audio_tools import AudioToolsHelper
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER

__all__ = ["system_play", "system_record", "system_record_hfp"]

# Card-profile name fragments (PulseAudio/PipeWire) that expose the remote
# microphone as a SCO *source*.  A2DP profiles are output-only, so the mic
# only appears once the card is switched to one of these.  Ordered by
# preference: HFP (wideband-capable, modern) before legacy HSP.
_HFP_PROFILE_HINTS = (
    "handsfree-head-unit",   # HFP, we act as Hands-Free (device = AG)
    "headset-head-unit",     # HSP/HFP head-unit (common PA/PW name)
    "handsfree-audio-gateway",
    "headset-audio-gateway",
)


def _norm_mac(mac: str) -> str:
    return (mac or "").replace(":", "").replace("-", "").upper()


def _is_hfp_profile(profile: Optional[str]) -> bool:
    """True when a PA/PipeWire card-profile name denotes an HFP/HSP (SCO) mode.

    Matches both hyphenated PipeWire names (``headset-head-unit``) and any
    legacy underscore variants by normalising separators before comparison.
    """
    if not profile:
        return False
    norm = profile.lower().replace("_", "-")
    return any(hint in norm for hint in _HFP_PROFILE_HINTS)


def system_play(
    device_mac: str,
    file_path: str,
    duration_sec: int = 30,
) -> bool:
    """Play an audio file to a Bluetooth device via system audio tools.

    Resolves the device MAC to a sink identifier using the same
    backend-specific enumeration that ``audio-recon`` uses, then
    delegates playback to the appropriate tool.

    Returns ``True`` on success.
    """
    if not os.path.isfile(file_path):
        print_and_log(f"[-] Audio file not found: {file_path}", LOG__USER)
        return False

    helper = AudioToolsHelper()
    backend = helper.get_audio_backend()

    if backend == "none":
        print_and_log(
            "[-] No supported audio backend detected. Install "
            "PulseAudio, PipeWire, or BlueALSA.",
            LOG__USER,
        )
        return False

    print_and_log(
        f"[*] System playback: backend={backend}, "
        f"device={device_mac}, file={file_path}",
        LOG__GENERAL,
    )

    # BlueALSA path
    if backend == "bluealsa" or helper.is_bluealsa_running():
        sink_dev = _find_bluealsa_sink(helper, device_mac)
        if sink_dev:
            print_and_log(
                f"[*] Playing via BlueALSA: {sink_dev}", LOG__USER,
            )
            ok = helper.play_to_bluealsa_pcm(sink_dev, file_path, duration_sec)
            if ok:
                print_and_log("[+] Playback complete", LOG__USER)
            else:
                print_and_log("[-] Playback failed", LOG__USER)
            return ok

    # PipeWire native path (no PA compat)
    if backend == "pipewire_native":
        node_id = _find_pw_native_sink(helper, device_mac)
        if node_id:
            print_and_log(
                f"[*] Playing via PipeWire native: node {node_id}",
                LOG__USER,
            )
            ok = helper.play_to_sink(node_id, file_path, duration_sec)
            if ok:
                print_and_log("[+] Playback complete", LOG__USER)
            else:
                print_and_log("[-] Playback failed", LOG__USER)
            return ok

    # PulseAudio / PipeWire-with-PA-compat path
    if backend in ("pulseaudio", "pipewire"):
        sink_name = _find_pa_sink(helper, device_mac)
        if sink_name:
            print_and_log(
                f"[*] Playing via {backend}: {sink_name}", LOG__USER,
            )
            ok = helper.play_to_sink(sink_name, file_path, duration_sec)
            if ok:
                print_and_log("[+] Playback complete", LOG__USER)
            else:
                print_and_log("[-] Playback failed", LOG__USER)
            return ok

    print_and_log(
        f"[-] No audio sink found for device {device_mac}. "
        f"Ensure the device is connected and the audio daemon "
        f"recognises it (check with 'audio-recon --device {device_mac}').",
        LOG__USER,
    )
    return False


def system_record(
    device_mac: str,
    output_path: str,
    duration_sec: int = 8,
) -> bool:
    """Record audio from a Bluetooth device via system audio tools.

    Resolves the device MAC to a source identifier using the same
    backend-specific enumeration that ``audio-recon`` uses, then
    delegates recording to the appropriate tool.

    Returns ``True`` on success.
    """
    helper = AudioToolsHelper()
    backend = helper.get_audio_backend()

    if backend == "none":
        print_and_log(
            "[-] No supported audio backend detected. Install "
            "PulseAudio, PipeWire, or BlueALSA.",
            LOG__USER,
        )
        return False

    print_and_log(
        f"[*] System record: backend={backend}, "
        f"device={device_mac}, output={output_path}",
        LOG__GENERAL,
    )

    # BlueALSA path
    if backend == "bluealsa" or helper.is_bluealsa_running():
        source_dev = _find_bluealsa_source(helper, device_mac)
        if source_dev:
            print_and_log(
                f"[*] Recording via BlueALSA: {source_dev}", LOG__USER,
            )
            ok = helper.record_from_bluealsa_pcm(
                source_dev, output_path, duration_sec,
            )
            if ok:
                print_and_log(f"[+] Recording saved: {output_path}", LOG__USER)
            else:
                print_and_log("[-] Recording failed", LOG__USER)
            return ok

    # PipeWire native path
    if backend == "pipewire_native":
        node_id = _find_pw_native_source(helper, device_mac)
        if node_id:
            print_and_log(
                f"[*] Recording via PipeWire native: node {node_id}",
                LOG__USER,
            )
            ok = helper.record_from_source(node_id, output_path, duration_sec)
            if ok:
                print_and_log(f"[+] Recording saved: {output_path}", LOG__USER)
            else:
                print_and_log("[-] Recording failed", LOG__USER)
            return ok

    # PulseAudio / PipeWire-with-PA-compat path
    if backend in ("pulseaudio", "pipewire"):
        source_name = _find_pa_source(helper, device_mac)
        if source_name:
            print_and_log(
                f"[*] Recording via {backend}: {source_name}", LOG__USER,
            )
            ok = helper.record_from_source(
                source_name, output_path, duration_sec,
            )
            if ok:
                print_and_log(f"[+] Recording saved: {output_path}", LOG__USER)
            else:
                print_and_log("[-] Recording failed", LOG__USER)
            return ok

    print_and_log(
        f"[-] No audio source found for device {device_mac}. "
        f"Ensure the device is connected and the audio daemon "
        f"recognises it (check with 'audio-recon --device {device_mac}').",
        LOG__USER,
    )
    return False


def system_record_hfp(
    device_mac: str,
    output_path: str,
    duration_sec: int = 8,
    *,
    restore_profile: bool = True,
) -> bool:
    """Capture the HFP/HSP microphone (SCO source) from a Bluetooth device.

    Unlike :func:`system_record` (which records whatever source the device's
    *current* profile exposes — nothing, for an output-only A2DP profile), this
    explicitly targets the remote **microphone**.  The mic is only exposed as a
    ``sco`` source once the card is switched to an HFP/HSP profile
    (``handsfree-head-unit`` / ``headset-head-unit``).  This helper:

    1. Locates the device's audio card / SCO PCM for the active backend.
    2. Switches the card to an HFP/HSP profile if it is not already on one
       (PulseAudio / PipeWire-PA-compat).  BlueALSA exposes ``sco`` PCMs
       directly and needs no switch.
    3. Records from the resulting SCO source via the host audio tools.
    4. Restores the original card profile (unless ``restore_profile=False``).

    Returns ``True`` on success.

    Notes
    -----
    HFP audio is narrow/wideband voice (CVSD 8 kHz / mSBC 16 kHz), so the
    captured WAV is mono voice-grade — this is the microphone path, distinct
    from the A2DP music path in :class:`~bleep.dbuslayer.media_stream.MediaStreamManager`.
    """
    helper = AudioToolsHelper()
    backend = helper.get_audio_backend()

    if backend == "none":
        print_and_log(
            "[-] No supported audio backend detected. Install "
            "PulseAudio, PipeWire, or BlueALSA.",
            LOG__USER,
        )
        return False

    print_and_log(
        f"[*] HFP microphone capture: backend={backend}, "
        f"device={device_mac}, output={output_path}",
        LOG__GENERAL,
    )

    # ---- BlueALSA: SCO source PCM is addressable directly (no profile switch)
    if backend == "bluealsa" or helper.is_bluealsa_running():
        sco_source = _find_bluealsa_sco_source(helper, device_mac)
        if sco_source:
            print_and_log(
                f"[*] Recording HFP mic via BlueALSA: {sco_source}", LOG__USER,
            )
            ok = helper.record_from_bluealsa_pcm(
                sco_source, output_path, duration_sec,
            )
            if ok:
                print_and_log(f"[+] Recording saved: {output_path}", LOG__USER)
            else:
                print_and_log("[-] Recording failed", LOG__USER)
            return ok
        print_and_log(
            f"[-] No BlueALSA SCO (HFP/HSP) source for {device_mac}. The device "
            f"may not expose a microphone, or HFP is not negotiated.",
            LOG__USER,
        )
        return False

    # ---- PulseAudio / PipeWire-PA-compat: switch card profile, then record
    if backend in ("pulseaudio", "pipewire", "pipewire_native"):
        return _record_hfp_via_card_profile(
            helper, device_mac, output_path, duration_sec, restore_profile,
        )

    print_and_log(
        f"[-] HFP capture unsupported for backend '{backend}'.", LOG__USER,
    )
    return False


def _record_hfp_via_card_profile(
    helper: "AudioToolsHelper",
    device_mac: str,
    output_path: str,
    duration_sec: int,
    restore_profile: bool,
) -> bool:
    """Switch a PA/PipeWire card to an HFP/HSP profile and record its SCO source.

    Restores the previous profile afterwards unless ``restore_profile`` is
    False.  Returns ``True`` on a successful recording.
    """
    norm = _norm_mac(device_mac)
    card_index: Optional[str] = None
    for card in helper.get_bluez_cards():
        if _norm_mac(helper.extract_mac_from_alsa_device(card.get("name", ""))) == norm:
            card_index = card.get("index", "")
            break

    if not card_index:
        print_and_log(
            f"[-] No audio card found for {device_mac}. Ensure it is connected "
            f"and the audio daemon recognises it (try 'audio-recon --device "
            f"{device_mac}').",
            LOG__USER,
        )
        return False

    previous_profile = helper.get_active_profile_for_card(card_index)
    switched = False

    if not _is_hfp_profile(previous_profile):
        target = next(
            (p for p in helper.get_profiles_for_card(card_index) if _is_hfp_profile(p)),
            None,
        )
        if not target:
            print_and_log(
                f"[-] Device {device_mac} exposes no HFP/HSP card profile — it "
                f"likely has no microphone (A2DP-only sink).",
                LOG__USER,
            )
            return False
        print_and_log(
            f"[*] Switching card {card_index} to HFP/HSP profile '{target}' "
            f"(was '{previous_profile or 'unknown'}')",
            LOG__USER,
        )
        if not helper.set_card_profile(card_index, target):
            print_and_log(
                f"[-] Failed to switch card {card_index} to '{target}'.",
                LOG__USER,
            )
            return False
        switched = True
        # BlueZ needs a moment to bring up the SCO transport after the switch.
        time.sleep(1.5)

    try:
        source_name = _find_sco_source_for_card(helper, card_index)
        if not source_name:
            print_and_log(
                f"[-] HFP/HSP profile active but no SCO microphone source "
                f"appeared for card {card_index}.",
                LOG__USER,
            )
            return False
        print_and_log(
            f"[*] Recording HFP mic from source: {source_name}", LOG__USER,
        )
        ok = helper.record_from_source(source_name, output_path, duration_sec)
        if ok:
            print_and_log(f"[+] Recording saved: {output_path}", LOG__USER)
        else:
            print_and_log("[-] Recording failed", LOG__USER)
        return ok
    finally:
        if switched and restore_profile and previous_profile:
            print_and_log(
                f"[*] Restoring card {card_index} profile to "
                f"'{previous_profile}'",
                LOG__DEBUG,
            )
            helper.set_card_profile(card_index, previous_profile)


def _find_sco_source_for_card(
    helper: "AudioToolsHelper", card_index: str,
) -> Optional[str]:
    """Return the SCO (microphone) source name for a card on an HFP/HSP profile.

    Prefers an explicit microphone-role source; falls back to any non-monitor
    source name the card profile exposes.
    """
    ss = helper.get_sources_and_sinks_for_card_profile(card_index)
    sources = ss.get("sources", [])
    # Prefer a mic-role / bluez_source node; skip monitor sources.
    for src in sources:
        name = src.get("name") or ""
        if not name or name.endswith(".monitor"):
            continue
        if src.get("role") == "microphone" or "source" in name.lower() or "sco" in name.lower():
            return name
    for src in sources:
        name = src.get("name") or ""
        if name and not name.endswith(".monitor"):
            return name
    return None


# ------------------------------------------------------------------
# Backend-specific sink/source resolution
# ------------------------------------------------------------------

def _find_bluealsa_sco_source(
    helper: AudioToolsHelper, device_mac: str,
) -> Optional[str]:
    """Find a BlueALSA SCO (HFP/HSP) source PCM device string for *device_mac*."""
    norm = _norm_mac(device_mac)
    for pcm in helper.list_bluealsa_pcms():
        if (pcm.get("profile") or "").lower() != "sco":
            continue
        if (pcm.get("direction") or "").lower() != "source":
            continue
        if _norm_mac(pcm.get("mac_address", "")) == norm:
            return pcm.get("alsa_device")
    return None

def _find_bluealsa_sink(
    helper: AudioToolsHelper, device_mac: str,
) -> Optional[str]:
    """Find a BlueALSA PCM sink device string for *device_mac*."""
    norm = _norm_mac(device_mac)
    for pcm in helper.list_bluealsa_pcms():
        if pcm.get("direction") != "sink":
            continue
        if _norm_mac(pcm.get("mac_address", "")) == norm:
            return pcm.get("alsa_device")
    return None


def _find_bluealsa_source(
    helper: AudioToolsHelper, device_mac: str,
) -> Optional[str]:
    """Find a BlueALSA PCM source device string for *device_mac*."""
    norm = _norm_mac(device_mac)
    for pcm in helper.list_bluealsa_pcms():
        if pcm.get("direction") != "source":
            continue
        if _norm_mac(pcm.get("mac_address", "")) == norm:
            return pcm.get("alsa_device")
    return None


def _find_pw_native_sink(
    helper: AudioToolsHelper, device_mac: str,
) -> Optional[str]:
    """Find a PipeWire node ID for a Bluetooth sink matching *device_mac*."""
    norm = _norm_mac(device_mac)
    ss = helper._get_pipewire_sources_and_sinks()
    for sink in ss.get("sinks", []):
        if _norm_mac(sink.get("mac_address", "")) == norm:
            return str(sink.get("node_id", ""))
    return None


def _find_pw_native_source(
    helper: AudioToolsHelper, device_mac: str,
) -> Optional[str]:
    """Find a PipeWire node ID for a Bluetooth source matching *device_mac*."""
    norm = _norm_mac(device_mac)
    ss = helper._get_pipewire_sources_and_sinks()
    for source in ss.get("sources", []):
        if _norm_mac(source.get("mac_address", "")) == norm:
            return str(source.get("node_id", ""))
    return None


def _find_pa_sink(
    helper: AudioToolsHelper, device_mac: str,
) -> Optional[str]:
    """Find a PA/PipeWire-PA-compat sink name for *device_mac*.

    Uses the card-centric enumeration that ``audio-recon`` relies on:
    ``get_bluez_cards()`` → filter by MAC → ``get_sources_and_sinks_for_card_profile()``.
    """
    norm = _norm_mac(device_mac)
    for card in helper.get_bluez_cards():
        card_mac = helper.extract_mac_from_alsa_device(
            card.get("name", ""),
        )
        if _norm_mac(card_mac) != norm:
            continue
        card_index = card.get("index", "")
        if not card_index:
            continue
        ss = helper.get_sources_and_sinks_for_card_profile(card_index)
        for sink in ss.get("sinks", []):
            name = sink.get("name")
            if name:
                return name
    return None


def _find_pa_source(
    helper: AudioToolsHelper, device_mac: str,
) -> Optional[str]:
    """Find a PA/PipeWire-PA-compat source name for *device_mac*.

    Checks both sources and sink monitor sources from the card's
    active profile.
    """
    norm = _norm_mac(device_mac)
    for card in helper.get_bluez_cards():
        card_mac = helper.extract_mac_from_alsa_device(
            card.get("name", ""),
        )
        if _norm_mac(card_mac) != norm:
            continue
        card_index = card.get("index", "")
        if not card_index:
            continue
        ss = helper.get_sources_and_sinks_for_card_profile(card_index)
        for source in ss.get("sources", []):
            name = source.get("name")
            if name:
                return name
        for sink in ss.get("sinks", []):
            name = sink.get("name")
            if name:
                return name
    return None
