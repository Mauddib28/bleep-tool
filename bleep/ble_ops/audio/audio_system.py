"""System-tool audio playback and recording for Bluetooth devices.

Delegates to the host audio daemon (PulseAudio, PipeWire, BlueALSA) via
subprocess tools (``paplay``, ``pw-play``, ``aplay``, etc.) rather than
acquiring D-Bus ``MediaTransport1`` file descriptors directly.  This
mirrors how ``audio-recon`` operates and works **with** the audio daemon
instead of competing for transport ownership.
"""

from __future__ import annotations

import os
from typing import Optional

from bleep.ble_ops.audio.audio_tools import AudioToolsHelper
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER

__all__ = ["system_play", "system_record"]


def _norm_mac(mac: str) -> str:
    return (mac or "").replace(":", "").replace("-", "").upper()


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


# ------------------------------------------------------------------
# Backend-specific sink/source resolution
# ------------------------------------------------------------------

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
