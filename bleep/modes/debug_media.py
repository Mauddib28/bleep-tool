"""Media and audio commands for debug mode.

Commands: mediaenum, mediactrl, mediaprops, audiorecon, audioplay, audiorec,
          audiocfg.

Wraps existing ``bleep.modes.media``, ``bleep.dbuslayer.media``,
``bleep.ble_ops.audio`` implementations for interactive debug-shell use.
"""

from __future__ import annotations

import argparse
import os
from typing import List, Optional

from bleep.modes.debug_state import DebugState
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__USER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_device(state: DebugState) -> bool:
    """Return True if a device is connected, else print guidance."""
    if state.current_device is None:
        print("[-] No device connected. Use 'connect <MAC>' or 'cconnect <MAC>' first.")
        return False
    return True


def _device_mac(state: DebugState) -> Optional[str]:
    if state.current_device is None:
        return None
    return state.current_device.mac_address


def _print_contention_report(
    profile_uuid: str,
    *,
    mac: Optional[str] = None,
    deep_probe: bool = False,
) -> None:
    """Render :func:`check_endpoint_contention` output to the debug shell.

    Shared between ``audiocfg`` and ``mediaenum`` so both surfaces render the
    same structured diagnostic format.
    """

    from bleep.core.preflight import check_endpoint_contention
    from bleep.bt_ref.constants import get_profile_name

    report = check_endpoint_contention(
        profile_uuid, device_mac=mac, deep_probe=deep_probe,
    )

    print()
    print("[+] Endpoint contention:")
    complement_name = get_profile_name(report.complement_uuid) or "<unknown>"
    print(f"    complement role: {complement_name} ({report.complement_uuid})")
    print(f"    severity:        {report.severity}")
    print(f"    probe:           {'deep' if report.deep_probe_run else 'primary'}")

    if not report.competitors:
        print("    competitors:     (none)")
    else:
        print("    competitors:")
        for owner in report.competitors:
            tag = "inferred" if owner.inferred else "observed"
            proc = f" pid={owner.pid}" if owner.pid else ""
            cmd = f" ({owner.cmdline})" if owner.cmdline else ""
            path = f" {owner.object_path}" if owner.object_path else ""
            print(f"      - {owner.backend}{proc}{cmd}{path} [{tag}]")

    if report.warnings:
        print("    warnings:")
        for w in report.warnings:
            print(f"      - {w}")

    if report.severity == "block":
        print("    Note: audioplay/audiorec will be gated. Use "
              "'--force-endpoint' to bypass, or '--direct' to acquire the")
        print("          existing transport owned by the competing daemon.")


# ---------------------------------------------------------------------------
# mediaenum – list D-Bus media objects for the connected device
# ---------------------------------------------------------------------------

def cmd_mediaenum(args: List[str], state: DebugState) -> None:
    """List media D-Bus objects (MediaControl, MediaPlayer, transports, endpoints)."""
    from bleep.dbuslayer.media import (
        find_media_devices,
        MediaPlayer,
        MediaTransport,
        get_managed_objects,
    )
    from bleep.bt_ref.constants import (
        MEDIA_CONTROL_INTERFACE,
        MEDIA_PLAYER_INTERFACE,
        MEDIA_ENDPOINT_INTERFACE,
        MEDIA_TRANSPORT_INTERFACE,
        A2DP_SINK_UUID,
        get_codec_name,
        get_profile_name,
    )

    parser = argparse.ArgumentParser(prog="mediaenum", add_help=False)
    parser.add_argument("--endpoints", action="store_true")
    parser.add_argument("--profile", default=A2DP_SINK_UUID)

    try:
        opts = parser.parse_args(args)
    except SystemExit:
        print("Usage: mediaenum [--endpoints] [--profile <UUID>]")
        return

    managed = get_managed_objects()
    if not managed:
        print("[-] No BlueZ managed objects found on D-Bus")
        return

    mac = _device_mac(state)
    dev_path_fragment = None
    if mac:
        dev_path_fragment = f"dev_{mac.replace(':', '_')}"

    found = False
    for path, ifaces in managed.items():
        if dev_path_fragment and dev_path_fragment not in path:
            continue

        media_ifaces = []
        if MEDIA_CONTROL_INTERFACE in ifaces:
            media_ifaces.append("MediaControl1")
        if MEDIA_PLAYER_INTERFACE in ifaces:
            media_ifaces.append("MediaPlayer1")
        if MEDIA_ENDPOINT_INTERFACE in ifaces:
            media_ifaces.append("MediaEndpoint1")
        if MEDIA_TRANSPORT_INTERFACE in ifaces:
            media_ifaces.append("MediaTransport1")

        if not media_ifaces:
            continue

        found = True
        print(f"[+] {path}")
        for iface_name in media_ifaces:
            print(f"    [{iface_name}]")
            props = ifaces.get(f"org.bluez.{iface_name}", {})
            if not props:
                continue
            for k, v in props.items():
                if k == "Codec" and isinstance(v, int):
                    print(f"      {k}: {v} ({get_codec_name(v)})")
                elif k == "UUID":
                    name = get_profile_name(str(v)) if v else None
                    print(f"      {k}: {v}" + (f" ({name})" if name else ""))
                else:
                    print(f"      {k}: {v}")

    if not found:
        target = f" for {mac}" if mac else ""
        print(f"[!] No media interfaces found{target}")
        print("    Possible causes:")
        print("    - No audio daemon (PulseAudio/PipeWire/BlueALSA) handling BT profiles")
        print("    - Device not connected via an A2DP/AVRCP profile")
        print("    Run 'audiocfg' to check the host audio backend status")

    if opts.endpoints:
        _print_contention_report(
            opts.profile, mac=mac, deep_probe=True,
        )


# ---------------------------------------------------------------------------
# mediactrl – AVRCP-style media player control
# ---------------------------------------------------------------------------

_MEDIACTRL_SUBCMDS = (
    "play", "pause", "stop", "next", "prev", "previous",
    "volume", "info", "press",
)


def cmd_mediactrl(args: List[str], state: DebugState) -> None:
    """Control media playback: play, pause, stop, next, prev, volume, info, press."""
    if not args:
        print(f"Usage: mediactrl <{'|'.join(_MEDIACTRL_SUBCMDS)}> [value]")
        return

    subcmd = args[0].lower()
    if subcmd == "prev":
        subcmd = "previous"

    if subcmd not in _MEDIACTRL_SUBCMDS and subcmd != "previous":
        print(f"[-] Unknown mediactrl action: {args[0]}")
        print(f"    Valid actions: {', '.join(_MEDIACTRL_SUBCMDS)}")
        return

    mac = _device_mac(state)
    if not mac:
        if len(args) >= 2 and ":" in args[1]:
            mac = args[1]
        else:
            if not _require_device(state):
                return

    value = None
    if subcmd in ("volume", "press") and len(args) >= 2:
        try:
            raw = args[-1]
            value = int(raw, 16) if raw.startswith("0x") else int(raw)
        except ValueError:
            print(f"[-] Invalid value: {args[-1]}")
            return

    from bleep.modes.media import control_media_device
    control_media_device(mac, subcmd, value=value)


# ---------------------------------------------------------------------------
# mediaprops – show all media interface properties
# ---------------------------------------------------------------------------

def cmd_mediaprops(args: List[str], state: DebugState) -> None:
    """Show properties for MediaControl1, MediaPlayer1, and MediaTransport1."""
    if not _require_device(state):
        return

    device = state.current_device

    from bleep.dbuslayer.media import MediaControl, MediaPlayer, MediaTransport

    sections = []

    mc = device.get_media_control()
    if mc:
        sections.append(("MediaControl1", {
            "Connected": mc.is_connected(),
            "Player": mc.get_player(),
        }))

    player = device.get_media_player()
    if player:
        sections.append(("MediaPlayer1", {
            "Status": player.get_status(),
            "Track": player.get_track(),
            "Position": player.get_position(),
            "Shuffle": player.get_shuffle(),
            "Repeat": player.get_repeat(),
            "Type": player.get_type(),
            "Browsable": player.is_browsable(),
            "Searchable": player.is_searchable(),
        }))

    transports = device.get_media_transports() or []
    for i, tr in enumerate(transports):
        from bleep.bt_ref.constants import get_codec_name, get_profile_name
        sections.append((f"MediaTransport1 #{i+1}", {
            "Path": tr.transport_path,
            "UUID": tr.get_uuid(),
            "Codec": tr.get_codec(),
            "CodecName": get_codec_name(tr.get_codec() or 0),
            "State": tr.get_state(),
            "Volume": tr.get_volume(),
            "Delay": tr.get_delay(),
        }))

    if not sections:
        print("[!] No media interfaces found on the connected device")
        print("    Run 'mediaenum' for a D-Bus object scan or 'audiocfg' to check the host audio stack")
        return

    for title, props in sections:
        print(f"[+] {title}:")
        for k, v in props.items():
            print(f"    {k}: {v}")
        print()


# ---------------------------------------------------------------------------
# audiorecon – run audio reconnaissance
# ---------------------------------------------------------------------------

def cmd_audiorecon(args: List[str], state: DebugState) -> None:
    """Run audio recon: detect backend, enumerate BT audio cards, play/record test."""
    from bleep.ble_ops.audio.audio_recon import run_audio_recon

    mac = _device_mac(state)
    test_file = None
    do_play = True
    do_record = True
    output_json = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--file" and i + 1 < len(args):
            test_file = args[i + 1]
            i += 2
        elif a == "--no-play":
            do_play = False
            i += 1
        elif a == "--no-record":
            do_record = False
            i += 1
        elif a == "--json" and i + 1 < len(args):
            output_json = args[i + 1]
            i += 2
        elif a == "--mac" and i + 1 < len(args):
            mac = args[i + 1]
            i += 2
        else:
            i += 1

    result = run_audio_recon(
        mac_filter=mac,
        test_file=test_file,
        do_play=do_play,
        do_record=do_record,
        output_json_path=output_json,
    )

    if result.get("errors"):
        for err in result["errors"]:
            print(f"[!] {err}")


# ---------------------------------------------------------------------------
# audioplay – play audio to connected device
# ---------------------------------------------------------------------------

def cmd_audioplay(args: List[str], state: DebugState) -> None:
    """Play an audio file to the connected BT device (--system for daemon path)."""
    parser = argparse.ArgumentParser(prog="audioplay", add_help=False)
    parser.add_argument("file", nargs="?", default="")
    parser.add_argument("--system", action="store_true")
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--force-endpoint", action="store_true")
    parser.add_argument("--volume", type=int, default=None)

    usage = (
        "Usage: audioplay <file> [--system] [--volume N] [--direct] "
        "[--force-endpoint]"
    )
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        print(usage)
        return

    if not opts.file:
        print(usage)
        return

    file_path = os.path.expandvars(os.path.expanduser(opts.file))
    use_system = opts.system
    use_direct = opts.direct
    force_endpoint = opts.force_endpoint
    volume = opts.volume

    mac = _device_mac(state)
    if not mac:
        if not _require_device(state):
            return

    if use_system:
        from bleep.ble_ops.audio.audio_system import system_play
        success = system_play(mac, file_path)
    else:
        from bleep.dbuslayer.media_stream import MediaStreamManager
        mgr = MediaStreamManager(
            mac, direct=use_direct, force_endpoint=force_endpoint,
        )
        success = mgr.play_audio_file(file_path, volume=volume)

    if success:
        print("[+] Playback completed")
    else:
        print("[-] Playback failed")


# ---------------------------------------------------------------------------
# audiorec – record audio from connected device
# ---------------------------------------------------------------------------

def cmd_audiorec(args: List[str], state: DebugState) -> None:
    """Record audio from the connected BT device (--system for daemon path)."""
    parser = argparse.ArgumentParser(prog="audiorec", add_help=False)
    parser.add_argument("file", nargs="?", default="")
    parser.add_argument("--system", action="store_true")
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--force-endpoint", action="store_true")
    parser.add_argument("--duration", type=int, default=8)

    usage = (
        "Usage: audiorec <output_file> [--system] [--duration N] [--direct] "
        "[--force-endpoint]"
    )
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        print(usage)
        return

    if not opts.file:
        print(usage)
        return

    output_file = os.path.expandvars(os.path.expanduser(opts.file))
    use_system = opts.system
    use_direct = opts.direct
    force_endpoint = opts.force_endpoint
    duration = opts.duration

    mac = _device_mac(state)
    if not mac:
        if not _require_device(state):
            return

    if use_system:
        from bleep.ble_ops.audio.audio_system import system_record
        success = system_record(mac, output_file, duration)
    else:
        from bleep.dbuslayer.media_stream import MediaStreamManager
        from bleep.bt_ref.constants import A2DP_SOURCE_UUID
        mgr = MediaStreamManager(
            mac,
            profile_uuid=A2DP_SOURCE_UUID,
            direct=use_direct,
            force_endpoint=force_endpoint,
        )
        success = mgr.record_audio(output_file, duration=duration)

    if success:
        print(f"[+] Recording saved to {output_file}")
    else:
        print("[-] Recording failed")


# ---------------------------------------------------------------------------
# audiocfg – show audio backend configuration and readiness
# ---------------------------------------------------------------------------

def cmd_audiocfg(args: List[str], state: DebugState) -> None:
    """Show host audio backend status and Bluetooth audio stack readiness."""
    from bleep.ble_ops.audio.audio_tools import AudioToolsHelper
    from bleep.bt_ref.constants import A2DP_SINK_UUID

    parser = argparse.ArgumentParser(prog="audiocfg", add_help=False)
    parser.add_argument("--endpoints", action="store_true")
    parser.add_argument("--profile", default=A2DP_SINK_UUID)

    try:
        opts = parser.parse_args(args)
    except SystemExit:
        print("Usage: audiocfg [--endpoints] [--profile <UUID>]")
        return

    helper = AudioToolsHelper()
    backend = helper.get_audio_backend()

    print(f"[+] Detected audio backend: {backend}")

    from bleep.core.preflight import (
        _check_bluetooth_audio_stack_detailed,
        _detect_audio_stack_conflicts,
        _check_audio_tools,
    )

    detailed = _check_bluetooth_audio_stack_detailed()

    print("[+] Bluetooth audio profile handlers:")

    bluealsa = detailed.get("bluealsa", {})
    ba_bits: List[str] = []
    if bluealsa.get("present"):
        ba_bits.append("tooling=installed")
    else:
        ba_bits.append("tooling=absent")
    ba_bits.append(
        "daemon=running" if bluealsa.get("running") else "daemon=not running"
    )
    print(f"    bluealsa:      status={bluealsa.get('status', 'absent')} "
          f"({', '.join(ba_bits)})")

    pulse = detailed.get("pulseaudio_bt", {})
    pa_bits: List[str] = []
    pa_bits.append("pactl=present" if pulse.get("present") else "pactl=absent")
    pa_bits.append(
        "module=loaded" if pulse.get("loaded") else "module=not loaded"
    )
    print(f"    pulseaudio_bt: status={pulse.get('status', 'absent')} "
          f"({', '.join(pa_bits)})")

    pw = detailed.get("pipewire_bt", {})
    pw_bits: List[str] = []
    pw_bits.append("pw-cli=present" if pw.get("present") else "pw-cli=absent")
    pw_bits.append(
        "plugin=installed" if pw.get("plugin_installed") else "plugin=not installed"
    )
    pw_bits.append(
        "plugin=loaded" if pw.get("plugin_loaded") else "plugin=not loaded"
    )
    print(f"    pipewire_bt:   status={pw.get('status', 'absent')} "
          f"({', '.join(pw_bits)})")

    warnings = _detect_audio_stack_conflicts(detailed)
    if warnings:
        print()
        print("[!] Backend conflicts / gaps detected:")
        for w in warnings:
            print(f"    - {w}")

    active_backends = [
        name for name, info in detailed.items()
        if info.get("status") == "active"
    ]
    installed_only = [
        name for name, info in detailed.items()
        if info.get("status") == "installed"
    ]

    if not active_backends:
        print()
        print("[!] No Bluetooth audio backend is actively handling BlueZ endpoints.")
        print("    BlueZ Device1.Connect() may fail with "
              "'br-connection-profile-unavailable' for devices advertising")
        print("    audio profiles (A2DP, HFP, HSP) until a handler is active.")
        if installed_only:
            print()
            print("    Installed but inactive handlers:")
            for name in installed_only:
                print(f"      - {name}")
            print("    Options (pick whichever matches your deployment; BLEEP")
            print("    does not prescribe one):")
            if "bluealsa" in installed_only:
                print("      * Start BlueALSA:  sudo systemctl start bluealsa")
            if "pulseaudio_bt" in installed_only:
                print("      * Start PulseAudio with module-bluetooth-*:")
                print("          pulseaudio --start   (user session)")
            if "pipewire_bt" in installed_only:
                print("      * Start PipeWire + wireplumber:")
                print("          systemctl --user start pipewire.socket "
                      "pipewire.service wireplumber.service")
        else:
            print()
            print("    No Bluetooth audio handler tooling is installed. Install one")
            print("    of BlueALSA (bluez-alsa-utils), PulseAudio with")
            print("    pulseaudio-module-bluetooth, or PipeWire + libspa-0.2-bluetooth.")
    elif warnings:
        print()
        print("    Remediation options (pick one; BLEEP does not prescribe):")
        if any("BlueALSA" in w for w in warnings):
            print("      * Keep BlueALSA, disable the competing backend:")
            print("          systemctl --user stop pipewire.service "
                  "wireplumber.service   # PipeWire")
            print("          systemctl --user stop pulseaudio.service          "
                  "            # PulseAudio")
            print("      * Keep PulseAudio/PipeWire, stop BlueALSA:")
            print("          sudo systemctl stop bluealsa")
        if any("plugin is not being loaded" in w for w in warnings):
            print("      * Ensure wireplumber is running and has the bluez5")
            print("        monitor enabled, and that no other backend owns the")
            print("        BlueZ endpoints.")

    tools = _check_audio_tools()
    print()
    print("[+] Audio tools:")
    for name, avail in tools.items():
        status = "available" if avail else "missing"
        print(f"    {name}: {status}")

    # Endpoint contention section — opt-in for the deep D-Bus probe; the
    # fast path reads only the structured backend status we already have.
    _print_contention_report(
        opts.profile, mac=_device_mac(state), deep_probe=opts.endpoints,
    )
