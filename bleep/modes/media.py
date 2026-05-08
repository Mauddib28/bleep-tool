"""BLEEP Media mode – provides a command-line interface for media device operations.

This module implements functionality for controlling media playback on Bluetooth
media devices such as speakers, headphones, and other A2DP devices.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Dict, Any, List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__USER

# Heavy D-Bus imports are deferred into functions to prevent circular imports
# when bleep.dbuslayer.device_le is still being initialised (see device_le.py
# module-level signals singleton and the bleep/__init__.py signal integration
# chain).  With ``from __future__ import annotations`` the type hints remain
# valid as strings.

# Optional observation DB persistence
try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None


def _get_device_le_class():
    from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
    return system_dbus__bluez_device__low_energy


def _get_media_helpers():
    from bleep.dbuslayer.media import find_media_devices, MediaPlayer, MediaTransport
    return find_media_devices, MediaPlayer, MediaTransport


def find_media_players() -> Dict[str, str]:
    """Find all available media players.
    
    Returns
    -------
    Dict[str, str]
        Dictionary mapping device paths to player paths
    """
    result = {}
    find_media_devices, _, _ = _get_media_helpers()
    media_devices = find_media_devices()
    
    for device_path, interfaces in media_devices.items():
        if "MediaPlayer" in interfaces:
            result[device_path] = interfaces["MediaPlayer"]
    
    return result


def search_media_device(mac_address: str) -> Optional[system_dbus__bluez_device__low_energy]:
    """Search for a media-capable device by MAC address (passive, no connection).

    Returns the device object when it has *any* evidence of media capability —
    either live D-Bus media objects (connected) or cached audio UUIDs from
    a prior discovery scan.  This makes the function suitable for both active
    and passive (security-assessment) workflows.

    Parameters
    ----------
    mac_address : str
        MAC address of the device to search for

    Returns
    -------
    Optional[system_dbus__bluez_device__low_energy]
        Device object if media-capable, ``None`` if unknown or not media.
    """
    try:
        _LEDevice = _get_device_le_class()
        device = _LEDevice(mac_address)
        if device.is_media_device() or device.has_media_uuids():
            return device
        return None
    except Exception as e:
        print_and_log(f"[-] Error searching for media device: {str(e)}", LOG__DEBUG)
        return None


# -- Role inference helpers --------------------------------------------------

_SINK_UUIDS: frozenset[str] = frozenset()  # populated lazily
_SOURCE_UUIDS: frozenset[str] = frozenset()


def _get_role_uuid_sets():
    """Return (sink_uuids, source_uuids) lazily."""
    global _SINK_UUIDS, _SOURCE_UUIDS  # noqa: PLW0603
    if not _SINK_UUIDS:
        from bleep.bt_ref.constants import (
            A2DP_SINK_UUID, HFP_HANDS_FREE_UUID, HSP_HEADSET_UUID,
            A2DP_SOURCE_UUID, HFP_AUDIO_GATEWAY_UUID, HSP_AUDIO_GATEWAY_UUID,
        )
        _SINK_UUIDS = frozenset({A2DP_SINK_UUID, HFP_HANDS_FREE_UUID, HSP_HEADSET_UUID})
        _SOURCE_UUIDS = frozenset({A2DP_SOURCE_UUID, HFP_AUDIO_GATEWAY_UUID, HSP_AUDIO_GATEWAY_UUID})
    return _SINK_UUIDS, _SOURCE_UUIDS


def _infer_likely_role(uuids: List[str]) -> str:
    """Infer a device's likely audio role from its advertised UUIDs."""
    sink_uuids, source_uuids = _get_role_uuid_sets()
    lower = {u.lower() for u in uuids}
    is_sink = bool(lower & sink_uuids)
    is_source = bool(lower & source_uuids)
    if is_sink and is_source:
        return "audio_sink_and_source"
    if is_sink:
        return "audio_sink"
    if is_source:
        return "audio_source"
    return "unknown"


# -- Passive assessment ------------------------------------------------------

def assess_media_device(
    mac_address: str,
    verbose: bool = False,
    *,
    _device: Optional[system_dbus__bluez_device__low_energy] = None,
) -> Dict[str, Any]:
    """Passively assess a device's media capabilities from cached BlueZ data.

    This reads only Device1 properties that BlueZ stores after discovery or
    pairing — **no connection is initiated**.  Useful for silent security
    reconnaissance where alerting the target is undesirable.

    Parameters
    ----------
    mac_address : str
        Target MAC address (must already be known to BlueZ).
    verbose : bool
        Include extended properties (manufacturer data, RSSI, appearance, …).
    _device : optional
        Pre-constructed device object to avoid a redundant D-Bus lookup.  When
        ``None`` (the default) a new instance is created from *mac_address*.

    Returns
    -------
    Dict[str, Any]
        JSON-serialisable assessment report.
    """
    if _device is None:
        _LEDevice = _get_device_le_class()
        _device = _LEDevice(mac_address)
    device = _device

    addr = device.get_address() or mac_address
    name = device.get_name() or device.get_alias() or "Unknown"

    # -- Device identity -----------------------------------------------------
    report: Dict[str, Any] = {
        "mode": "passive",
        "device_info": {
            "address": addr,
            "name": name,
            "icon": device.get_device_icon(),
            "modalias": device.get_modalias(),
            "is_connected": device.is_connected(),
            "is_paired": device.is_paired(),
            "is_trusted": device.is_trusted(),
            "is_bonded": device.is_bonded(),
        },
    }

    # -- Media assessment ----------------------------------------------------
    uuids = device.get_uuids() or []
    profile_names = device.get_media_uuid_names()
    has_active = device.is_media_device()

    assessment: Dict[str, Any] = {
        "advertised_profiles": profile_names,
        "likely_role": _infer_likely_role(uuids) if profile_names else "none",
        "has_active_media_objects": has_active,
    }

    # Decode Class of Device if available
    cod_raw = device.get_device_class()
    if cod_raw is not None:
        from bleep.ble_ops.common.conversion import (
            decode_class_of_device,
            extract__class_of_device__service_and_class_info,
        )
        svc, major, minor, _fb = decode_class_of_device(int(cod_raw))
        svc_s, major_s, minor_s = extract__class_of_device__service_and_class_info(
            svc, major, minor, _fb,
        )
        assessment["device_class"] = {
            "major_services": svc,
            "major_device": major_s,
            "minor_device": minor_s,
        }

    # Contextual note
    if not profile_names and not has_active:
        assessment["notes"] = "No audio profile UUIDs or D-Bus media objects found."
    elif has_active:
        assessment["notes"] = (
            "Device is connected with live media objects. "
            "Use 'media-enum' (without --passive) for full enumeration."
        )
    elif device.is_connected():
        assessment["notes"] = (
            "Device is connected but no D-Bus media objects are present. "
            "An audio daemon (bluez-alsa / PulseAudio / PipeWire) may be needed."
        )
    else:
        assessment["notes"] = (
            "Device advertises audio profiles but is not connected. "
            "Connect to access MediaControl1/MediaPlayer1."
        )

    report["media_assessment"] = assessment

    # -- Verbose extras ------------------------------------------------------
    if verbose:
        extras: Dict[str, Any] = {}
        extras["raw_uuids"] = uuids

        rssi = device.get_rssi()
        if rssi is not None:
            extras["rssi"] = rssi

        tx = device.get_tx_power()
        if tx is not None:
            extras["tx_power"] = tx

        appearance = device.get_device_appearance()
        if appearance is not None:
            extras["appearance"] = int(appearance)
            try:
                from bleep.ble_ops.common.conversion import decode_appearance
                extras["appearance_name"] = decode_appearance(int(appearance))
            except Exception:
                pass

        mfr = device.get_manufacturer_data()
        if mfr:
            extras["manufacturer_data"] = {
                str(k): list(bytes(v)) for k, v in mfr.items()
            }

        svc_data = device.get_service_data()
        if svc_data:
            extras["service_data"] = {
                str(k): list(bytes(v)) for k, v in svc_data.items()
            }

        extras["address_type"] = device.get_address_type()
        extras["is_blocked"] = device.is_blocked()
        extras["is_services_resolved"] = device.is_services_resolved()

        report["verbose"] = extras

    return report


def enumerate_media_passive(mac_address: str, verbose: bool = False) -> Dict[str, Any]:
    """High-level entry point for passive media enumeration.

    Wraps :func:`assess_media_device` with user-facing logging and optional
    observation-DB persistence.

    Parameters
    ----------
    mac_address : str
        Target MAC address.
    verbose : bool
        Include extended properties in the report.

    Returns
    -------
    Dict[str, Any]
        The assessment report (JSON-serialisable).
    """
    _LEDevice = _get_device_le_class()
    try:
        device = _LEDevice(mac_address)
    except Exception as e:
        print_and_log(f"[-] Device {mac_address} not found in BlueZ cache: {e}", LOG__USER)
        return {}

    report = assess_media_device(mac_address, verbose=verbose, _device=device)

    if not report:
        return report

    # Persist to observation DB (same pattern as active media-enum)
    if _obs:
        try:
            from bleep.ble_ops.le.scan import _collect_device_props, _enrich_device_info_from_props
            props = _collect_device_props(device)
            dev_info: Dict[str, Any] = {"name": device.get_name() or device.get_alias()}
            _enrich_device_info_from_props(dev_info, props)
            _obs.upsert_device(device.get_address() or mac_address, **dev_info)
        except Exception:
            pass

    return report


def list_media_devices() -> None:
    """List all available media devices."""
    find_media_devices, MediaPlayer, MediaTransport = _get_media_helpers()
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
            _LEDevice = _get_device_le_class()
            device = _LEDevice(mac_address)
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
    # Connect first — BlueZ only exposes media D-Bus objects (MediaControl1,
    # MediaPlayer1, endpoints, transports) while the audio profile is active.
    # Checking is_media_device() before connecting would always fail for a
    # disconnected device even if it fully supports A2DP/AVRCP.
    _LEDevice = _get_device_le_class()
    try:
        device = _LEDevice(mac_address)
    except Exception as e:
        print_and_log(f"[-] Device {mac_address} not found in BlueZ: {e}", LOG__USER)
        return False

    if not device.is_connected():
        print_and_log(f"[*] Connecting to {mac_address}...", LOG__USER)
        try:
            device.connect()
        except Exception as e:
            print_and_log(f"[-] Failed to connect to {mac_address}: {str(e)}", LOG__USER)
            return False

    if not device.is_media_device():
        if device.has_media_uuids():
            names = device.get_media_uuid_names()
            print_and_log(
                f"[!] {mac_address} advertises media UUIDs ({', '.join(names)}) "
                "but no D-Bus media objects are present.",
                LOG__USER,
            )
            print_and_log(
                "    Install bluez-alsa-utils, or enable PulseAudio/PipeWire BT support.",
                LOG__USER,
            )
        else:
            print_and_log(f"[-] {mac_address} is not a media device", LOG__USER)
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
    
    elif command == "press" and value is not None:
        # Get player object directly
        player = device.get_media_player()
        if not player:
            print_and_log(f"[-] No media player available on {mac_address}", LOG__USER)
            return False
            
        # Send the key press command
        result = player.press(value)
        if result:
            print_and_log(f"[+] Sent key code 0x{value:02x} to {mac_address}", LOG__USER)
        else:
            print_and_log(f"[-] Failed to send key code to {mac_address}", LOG__USER)
            
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
        if command == "press" and value is None:
            print_and_log(f"[-] Press command requires a key code value (--value=<code>)", LOG__USER)
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
    _LEDevice = _get_device_le_class()
    try:
        device = _LEDevice(mac_address)
    except Exception as e:
        print_and_log(f"[-] Device {mac_address} not found in BlueZ: {e}", LOG__USER)
        return

    if not device.is_connected():
        print_and_log(f"[*] Connecting to {mac_address}...", LOG__USER)
        try:
            device.connect()
        except Exception as e:
            print_and_log(f"[-] Failed to connect to {mac_address}: {str(e)}", LOG__USER)
            return

    if not device.is_media_device():
        if device.has_media_uuids():
            names = device.get_media_uuid_names()
            print_and_log(
                f"[!] {mac_address} advertises media UUIDs ({', '.join(names)}) "
                "but no D-Bus media objects are present.",
                LOG__USER,
            )
            print_and_log(
                "    Install bluez-alsa-utils, or enable PulseAudio/PipeWire BT support.",
                LOG__USER,
            )
        else:
            print_and_log(f"[-] {mac_address} is not a media device", LOG__USER)
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
