"""BLEEP Audio mode – provides audio playback and recording capabilities.

This module implements functionality for playing audio files to Bluetooth devices
and recording audio from Bluetooth devices using ALSA/PulseAudio/PipeWire
enumeration and BlueZ D-Bus media transports.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, Any, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__USER
from bleep.ble_ops.audio_profile_correlator import AudioProfileCorrelator
from bleep.dbuslayer.media_stream import MediaStreamManager

__all__ = ["list_audio_profiles", "play_audio_file", "record_audio", "main"]


def list_audio_profiles(mac_address: Optional[str] = None) -> None:
    """
    List Bluetooth audio profiles identified via ALSA correlation.
    
    Parameters
    ----------
    mac_address : Optional[str]
        Optional MAC address to filter results. If None, lists all devices.
    """
    correlator = AudioProfileCorrelator()
    
    if mac_address:
        # Get profiles for specific device
        profile_info = correlator.identify_profiles_for_device(mac_address)
        
        print_and_log(f"[+] Audio profiles for {mac_address}:", LOG__USER)
        
        if not profile_info.get("profiles"):
            print_and_log("[!] No audio profiles found", LOG__USER)
            return
        
        for profile_uuid, profile_data in profile_info["profiles"].items():
            print_and_log(
                f"  Profile: {profile_data.get('profile_name', 'Unknown')} ({profile_uuid})",
                LOG__USER,
            )
            
            if profile_data.get("codec_name"):
                print_and_log(f"    Codec: {profile_data['codec_name']}", LOG__USER)
            
            if profile_data.get("state"):
                print_and_log(f"    State: {profile_data['state']}", LOG__USER)
            
            if profile_data.get("transport_path"):
                print_and_log(f"    Transport: {profile_data['transport_path']}", LOG__USER)
            
            alsa_devices = profile_data.get("alsa_devices", [])
            if alsa_devices:
                print_and_log(f"    ALSA Devices: {len(alsa_devices)}", LOG__USER)
                for alsa_dev in alsa_devices:
                    if alsa_dev.get("sink_name"):
                        print_and_log(f"      Sink: {alsa_dev['sink_name']}", LOG__USER)
                    if alsa_dev.get("source_name"):
                        print_and_log(f"      Source: {alsa_dev['source_name']}", LOG__USER)
    else:
        # List all Bluetooth audio devices
        from bleep.ble_ops.audio_tools import AudioToolsHelper
        audio_tools = AudioToolsHelper()
        all_profiles = audio_tools.identify_bluetooth_profiles_from_alsa()
        
        if not all_profiles:
            print_and_log("[!] No Bluetooth audio devices found", LOG__USER)
            return
        
        print_and_log(f"[+] Found Bluetooth audio devices:", LOG__USER)
        
        # Group by device MAC
        devices_dict: Dict[str, Dict[str, Any]] = {}
        for profile_uuid, devices in all_profiles.items():
            for device in devices:
                mac = device.get("mac_address")
                if mac:
                    if mac not in devices_dict:
                        devices_dict[mac] = {
                            "mac_address": mac,
                            "profiles": []
                        }
                    devices_dict[mac]["profiles"].append({
                        "uuid": profile_uuid,
                        "profile_name": device.get("profile_name"),
                        "backend": device.get("backend"),
                    })
        
        for mac, device_info in devices_dict.items():
            print_and_log(f"  Device: {mac}", LOG__USER)
            for profile in device_info["profiles"]:
                print_and_log(
                    f"    - {profile['profile_name']} ({profile['uuid']})",
                    LOG__USER,
                )


def play_audio_file(mac_address: str, file_path: str, **kwargs) -> bool:
    """
    Play audio file to Bluetooth device.
    
    Parameters
    ----------
    mac_address : str
        MAC address of target Bluetooth device
    file_path : str
        Path to audio file (MP3, WAV, FLAC, etc.)
    **kwargs
        Additional options:
        - volume: Volume level (0-127)
        - profile_uuid: Profile UUID (defaults to A2DP Sink)
    
    Returns
    -------
    bool
        True if playback succeeded, False otherwise
    """
    profile_uuid = kwargs.get("profile_uuid")
    volume = kwargs.get("volume")
    
    stream_manager = MediaStreamManager(mac_address, profile_uuid=profile_uuid)
    return stream_manager.play_audio_file(file_path, volume=volume)


def record_audio(mac_address: str, output_path: str, **kwargs) -> bool:
    """
    Record audio from Bluetooth device.
    
    Parameters
    ----------
    mac_address : str
        MAC address of source Bluetooth device
    output_path : str
        Path to output audio file
    **kwargs
        Additional options:
        - duration: Recording duration in seconds (None = until stopped)
        - profile_uuid: Profile UUID (defaults to A2DP Source)
    
    Returns
    -------
    bool
        True if recording succeeded, False otherwise
    """
    from bleep.bt_ref.constants import A2DP_SOURCE_UUID
    profile_uuid = kwargs.get("profile_uuid", A2DP_SOURCE_UUID)
    duration = kwargs.get("duration")
    
    stream_manager = MediaStreamManager(mac_address, profile_uuid=profile_uuid)
    return stream_manager.record_audio(output_path, duration=duration)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.
    
    Returns
    -------
    argparse.Namespace
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="BLEEP Audio Operations")
    
    # Main commands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List profiles command
    list_parser = subparsers.add_parser("list", help="List Bluetooth audio profiles")
    list_parser.add_argument("--device", help="Filter by device MAC address")
    
    # Play command
    play_parser = subparsers.add_parser("play", help="Play audio file to Bluetooth device")
    play_parser.add_argument("device", help="Target device MAC address")
    play_parser.add_argument("file", help="Audio file path")
    play_parser.add_argument("--volume", type=int, help="Volume (0-127)")
    play_parser.add_argument("--profile", help="Profile UUID (defaults to A2DP Sink)")
    
    # Record command
    record_parser = subparsers.add_parser("record", help="Record audio from Bluetooth device")
    record_parser.add_argument("device", help="Source device MAC address")
    record_parser.add_argument("output", help="Output file path")
    record_parser.add_argument("--duration", type=int, help="Duration in seconds")
    record_parser.add_argument("--profile", help="Profile UUID (defaults to A2DP Source)")
    
    # Recon command (enumerate profiles/sources/sinks, optional play/record, sox analysis)
    recon_parser = subparsers.add_parser("recon", help="Audio recon: enumerate BlueZ cards/profiles, play test file, record, analyse with sox")
    recon_parser.add_argument("--device", help="Filter by device MAC address")
    recon_parser.add_argument("--test-file", help="Path to test audio file for playback to sinks")
    recon_parser.add_argument("--no-play", action="store_true", help="Skip playing test file to sinks")
    recon_parser.add_argument("--no-record", action="store_true", help="Skip recording from sources/sinks")
    recon_parser.add_argument("--out", dest="output_json", help="Write structured result to JSON file")
    recon_parser.add_argument("--record-dir", default="/tmp", help="Directory for recordings (default: /tmp)")
    recon_parser.add_argument("--duration", type=int, default=8, help="Recording duration per interface in seconds (default: 8)")
    
    return parser.parse_args()


def main() -> int:
    """Main entry point for the audio mode.
    
    Returns
    -------
    int
        Exit code
    """
    args = parse_args()
    
    if args.command == "list":
        list_audio_profiles(args.device)
        return 0
    
    elif args.command == "play":
        success = play_audio_file(
            args.device,
            args.file,
            volume=args.volume,
            profile_uuid=args.profile,
        )
        return 0 if success else 1
    
    elif args.command == "record":
        success = record_audio(
            args.device,
            args.output,
            duration=args.duration,
            profile_uuid=args.profile,
        )
        return 0 if success else 1
    
    elif args.command == "recon":
        from bleep.ble_ops.audio_recon import run_audio_recon
        run_audio_recon(
            mac_filter=getattr(args, "device", None),
            test_file=getattr(args, "test_file", None),
            do_play=not getattr(args, "no_play", False),
            do_record=not getattr(args, "no_record", False),
            record_duration_sec=getattr(args, "duration", 8),
            record_dir=getattr(args, "record_dir", "/tmp"),
            output_json_path=getattr(args, "output_json", None),
        )
        return 0
    
    else:
        print_and_log("[-] No command specified. Use --help for usage information.", LOG__USER)
        return 1


if __name__ == "__main__":
    sys.exit(main())
