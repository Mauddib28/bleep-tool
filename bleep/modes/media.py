"""BLEEP Media mode – provides a command-line interface for media device operations.

This module implements functionality for controlling media playback on Bluetooth
media devices such as speakers, headphones, and other A2DP devices.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Dict, Any, List, Optional

import dbus
from gi.repository import GLib

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__USER
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
from bleep.dbuslayer.media import find_media_devices, MediaPlayer, MediaTransport

# Optional observation DB persistence
try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None


def find_media_players() -> Dict[str, str]:
    """Find all available media players.
    
    Returns
    -------
    Dict[str, str]
        Dictionary mapping device paths to player paths
    """
    result = {}
    media_devices = find_media_devices()
    
    for device_path, interfaces in media_devices.items():
        if "MediaPlayer" in interfaces:
            result[device_path] = interfaces["MediaPlayer"]
    
    return result


def search_media_device(mac_address: str) -> Optional[system_dbus__bluez_device__low_energy]:
    """Search for a media device with the given MAC address.
    
    Parameters
    ----------
    mac_address : str
        MAC address of the device to search for
    
    Returns
    -------
    Optional[system_dbus__bluez_device__low_energy]
        Device object if found, None otherwise
    """
    try:
        device = system_dbus__bluez_device__low_energy(mac_address)
        if device.is_media_device():
            return device
        return None
    except Exception as e:
        print_and_log(f"[-] Error searching for media device: {str(e)}", LOG__DEBUG)
        return None


def list_media_devices() -> None:
    """List all available media devices."""
    media_devices = find_media_devices()
    
    if not media_devices:
        print_and_log("[!] No media devices found", LOG__USER)
        return
    
    print_and_log(f"[+] Found {len(media_devices)} media device(s):", LOG__USER)
    
    for device_path, interfaces in media_devices.items():
        # Extract MAC address from device path
        mac_address = device_path.split('_')[-1].replace('_', ':')
        
        # Try to get the device object
        try:
            device = system_dbus__bluez_device__low_energy(mac_address)
            device_name = device.alias() or mac_address
        except Exception:
            device_name = mac_address
        
        # Print device information
        print_and_log(f"  - Device: {device_name} ({mac_address})", LOG__USER)
        
        # List available interfaces
        if "MediaControl" in interfaces:
            print_and_log(f"    * Media Control: {interfaces['MediaControl']}", LOG__USER)
        
        if "MediaPlayer" in interfaces:
            print_and_log(f"    * Media Player: {interfaces['MediaPlayer']}", LOG__USER)
            
            # Try to get player status
            try:
                player = MediaPlayer(interfaces["MediaPlayer"])
                status = player.get_status()
                if status:
                    print_and_log(f"      Status: {status}", LOG__USER)
                
                track = player.get_track()
                if track:
                    title = track.get("Title", "Unknown")
                    artist = track.get("Artist", "Unknown")
                    album = track.get("Album", "Unknown")
                    print_and_log(f"      Now Playing: {title} - {artist} ({album})", LOG__USER)
            except Exception as e:
                print_and_log(f"      Error getting player info: {str(e)}", LOG__DEBUG)
        
        if "MediaTransports" in interfaces:
            for i, transport_path in enumerate(interfaces["MediaTransports"]):
                print_and_log(f"    * Media Transport #{i+1}: {transport_path}", LOG__USER)
                
                # Try to get transport status
                try:
                    transport = MediaTransport(transport_path)
                    state = transport.get_state()
                    volume = transport.get_volume()
                    
                    if state:
                        print_and_log(f"      State: {state}", LOG__USER)
                    if volume is not None:
                        print_and_log(f"      Volume: {volume}/127", LOG__USER)
                except Exception as e:
                    print_and_log(f"      Error getting transport info: {str(e)}", LOG__DEBUG)
        
        print_and_log("", LOG__USER)  # Empty line for better readability


def control_media_device(mac_address: str, command: str, value: Optional[int] = None) -> bool:
    """Control a media device.
    
    Parameters
    ----------
    mac_address : str
        MAC address of the device to control
    command : str
        Command to execute (play, pause, stop, next, previous, volume)
    value : Optional[int]
        Value for volume command (0-127)
    
    Returns
    -------
    bool
        True if successful, False otherwise
    """
    device = search_media_device(mac_address)
    if not device:
        print_and_log(f"[-] Media device {mac_address} not found", LOG__USER)
        return False
    
    if not device.is_connected():
        print_and_log(f"[*] Connecting to {mac_address}...", LOG__USER)
        try:
            device.connect()
        except Exception as e:
            print_and_log(f"[-] Failed to connect to {mac_address}: {str(e)}", LOG__USER)
            return False

    # snapshot to observation DB after a successful connection
    if _obs:
        try:
            player = device.get_media_player()
            if player:
                _obs.snapshot_media_player(player)  # type: ignore[attr-defined]
            for tr in device.get_media_transports() or []:
                _obs.snapshot_media_transport(tr)  # type: ignore[attr-defined]
        except Exception:
            pass
    
    result = False
    
    if command == "play":
        result = device.play_media()
        if result:
            print_and_log(f"[+] Started playback on {mac_address}", LOG__USER)
        else:
            print_and_log(f"[-] Failed to start playback on {mac_address}", LOG__USER)
    
    elif command == "pause":
        result = device.pause_media()
        if result:
            print_and_log(f"[+] Paused playback on {mac_address}", LOG__USER)
        else:
            print_and_log(f"[-] Failed to pause playback on {mac_address}", LOG__USER)
    
    elif command == "stop":
        result = device.stop_media()
        if result:
            print_and_log(f"[+] Stopped playback on {mac_address}", LOG__USER)
        else:
            print_and_log(f"[-] Failed to stop playback on {mac_address}", LOG__USER)
    
    elif command == "next":
        result = device.next_track()
        if result:
            print_and_log(f"[+] Skipped to next track on {mac_address}", LOG__USER)
        else:
            print_and_log(f"[-] Failed to skip to next track on {mac_address}", LOG__USER)
    
    elif command == "previous":
        result = device.previous_track()
        if result:
            print_and_log(f"[+] Skipped to previous track on {mac_address}", LOG__USER)
        else:
            print_and_log(f"[-] Failed to skip to previous track on {mac_address}", LOG__USER)
    
    elif command == "volume" and value is not None:
        if not 0 <= value <= 127:
            print_and_log(f"[-] Volume must be between 0 and 127", LOG__USER)
            return False
        
        result = device.set_volume(value)
        if result:
            print_and_log(f"[+] Set volume to {value} on {mac_address}", LOG__USER)
        else:
            print_and_log(f"[-] Failed to set volume on {mac_address}", LOG__USER)
    
    elif command == "info":
        # Get player status
        status = device.get_playback_status()
        if status:
            print_and_log(f"[+] Playback status: {status}", LOG__USER)
        
        # Get track info
        track_info = device.get_track_info()
        if track_info:
            title = track_info.get("Title", "Unknown")
            artist = track_info.get("Artist", "Unknown")
            album = track_info.get("Album", "Unknown")
            print_and_log(f"[+] Now Playing: {title} - {artist} ({album})", LOG__USER)
        
        # Get volume
        volume = device.get_volume()
        if volume is not None:
            print_and_log(f"[+] Volume: {volume}/127", LOG__USER)
        
        result = True
    
    else:
        print_and_log(f"[-] Unknown command: {command}", LOG__USER)
        return False
    
    return result


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.
    
    Returns
    -------
    argparse.Namespace
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="BLEEP Media Device Control")
    
    # Main commands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List available media devices")
    list_parser.add_argument("--objects", action="store_true", help="Show full media object tree (players, folders, items)")
    
    # Control command
    control_parser = subparsers.add_parser("control", help="Control a media device")
    control_parser.add_argument("mac_address", help="MAC address of the device to control")
    control_parser.add_argument("action", choices=["play", "pause", "stop", "next", "previous", "volume", "info"],
                               help="Action to perform")
    control_parser.add_argument("--value", type=int, help="Value for volume action (0-127)")
    
    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor media device status")
    monitor_parser.add_argument("mac_address", help="MAC address of the device to monitor")
    monitor_parser.add_argument("--interval", type=int, default=5, help="Polling interval in seconds")
    monitor_parser.add_argument("--duration", type=int, default=60, help="Monitoring duration in seconds")
    
    return parser.parse_args()


def monitor_media_device(mac_address: str, interval: int = 5, duration: int = 60) -> None:
    """Monitor a media device's status.
    
    Parameters
    ----------
    mac_address : str
        MAC address of the device to monitor
    interval : int
        Polling interval in seconds
    duration : int
        Monitoring duration in seconds
    """
    device = search_media_device(mac_address)
    if not device:
        print_and_log(f"[-] Media device {mac_address} not found", LOG__USER)
        return
    
    if not device.is_connected():
        print_and_log(f"[*] Connecting to {mac_address}...", LOG__USER)
        try:
            device.connect()
        except Exception as e:
            print_and_log(f"[-] Failed to connect to {mac_address}: {str(e)}", LOG__USER)
            return
    
    print_and_log(f"[*] Monitoring {mac_address} for {duration} seconds (polling every {interval} seconds)...", LOG__USER)
    
    start_time = time.time()
    last_track = {}
    last_status = None
    last_volume = None
    
    while time.time() - start_time < duration:
        # Get current status
        status = device.get_playback_status()
        track_info = device.get_track_info()
        volume = device.get_volume()
        
        # Check for changes
        if status != last_status:
            print_and_log(f"[*] Status changed: {status}", LOG__USER)
            last_status = status
        
        if track_info != last_track and track_info:
            title = track_info.get("Title", "Unknown")
            artist = track_info.get("Artist", "Unknown")
            album = track_info.get("Album", "Unknown")
            print_and_log(f"[*] Track changed: {title} - {artist} ({album})", LOG__USER)
            last_track = track_info
        
        if volume != last_volume and volume is not None:
            print_and_log(f"[*] Volume changed: {volume}/127", LOG__USER)
            last_volume = volume
        
        # Wait for next poll
        time.sleep(interval)
    
    print_and_log(f"[*] Monitoring completed for {mac_address}", LOG__USER)


def main() -> int:
    """Main entry point for the media mode.
    
    Returns
    -------
    int
        Exit code
    """
    args = parse_args()
    
    if args.command == "list":
        list_media_devices()  # legacy view

        if args.objects:
            print_and_log("\n[=] Full media object tree:", LOG__USER)
            from bleep.dbuslayer.media import find_media_objects  # local import to avoid overhead on normal path

            objs = find_media_objects()
            # Pretty-print
            for svc in objs["MediaServices"]:
                print_and_log(f"  Media1 service: {svc}", LOG__USER)

            for player, info in objs["Players"].items():
                print_and_log(f"  Player: {player} (Device={info['Device']})", LOG__USER)

            for folder, meta in objs["Folders"].items():
                print_and_log(f"    Folder: {folder} (Player={meta['Player']})", LOG__DEBUG)

            for item, meta in objs["Items"].items():
                print_and_log(f"    Item: {item} (Player={meta['Player']})", LOG__DEBUG)
        return 0
    
    elif args.command == "control":
        success = control_media_device(args.mac_address, args.action, args.value)
        return 0 if success else 1
    
    elif args.command == "monitor":
        monitor_media_device(args.mac_address, args.interval, args.duration)
        return 0
    
    else:
        print_and_log("[-] No command specified. Use --help for usage information.", LOG__USER)
        return 1


if __name__ == "__main__":
    sys.exit(main())
