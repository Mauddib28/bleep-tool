"""Media Device interfaces for the BlueZ stack.

This module provides classes for interacting with Bluetooth media devices through
the BlueZ D-Bus interfaces:
- MediaControl1 (deprecated but supported)
- MediaEndpoint1
- MediaTransport1
- MediaPlayer1

These interfaces allow for control and interaction with media devices such as
speakers, headphones, and other A2DP devices.
"""

from __future__ import annotations

import time
from typing import Dict, Any, Optional, List, Tuple, Callable

import dbus
from dbus.mainloop.glib import DBusGMainLoop

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    DBUS_PROPERTIES,
    MEDIA_CONTROL_INTERFACE,
    MEDIA_ENDPOINT_INTERFACE,
    MEDIA_TRANSPORT_INTERFACE,
    MEDIA_PLAYER_INTERFACE,
    INTROSPECT_INTERFACE,
)
from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__USER
from bleep.core.errors import map_dbus_error, BLEEPError, NotSupportedError

__all__ = [
    "MediaControl",
    "MediaEndpoint",
    "MediaTransport",
    "MediaPlayer",
    "find_media_devices",
]


class MediaControl:
    """Wrapper for the org.bluez.MediaControl1 interface.
    
    Note: This interface is deprecated in recent BlueZ versions but is still
    supported for backward compatibility.
    """
    
    def __init__(self, device_path: str):
        """Initialize MediaControl interface for a device.
        
        Parameters
        ----------
        device_path : str
            D-Bus path to the device
        """
        self.device_path = device_path
        self._bus = dbus.SystemBus()
        
        try:
            self._object = self._bus.get_object(BLUEZ_SERVICE_NAME, device_path)
            self._interface = dbus.Interface(self._object, MEDIA_CONTROL_INTERFACE)
            self._properties = dbus.Interface(self._object, DBUS_PROPERTIES)
            self._introspection = self._interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] MediaControl interface not available: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
            
    def get_properties(self) -> Dict[str, Any]:
        """Get all properties of the MediaControl interface.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary of property names and values
        """
        try:
            props = self._properties.GetAll(MEDIA_CONTROL_INTERFACE)
            return dbus_to_python(props)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get MediaControl properties: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
    
    def is_connected(self) -> bool:
        """Check if the media control is connected.
        
        Returns
        -------
        bool
            True if connected, False otherwise
        """
        try:
            connected = self._properties.Get(MEDIA_CONTROL_INTERFACE, "Connected")
            return bool(connected)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Connected property: {str(e)}", LOG__DEBUG)
            return False
    
    def get_player(self) -> Optional[str]:
        """Get the associated player object path.
        
        Returns
        -------
        Optional[str]
            Object path to the player or None if not available
        """
        try:
            player = self._properties.Get(MEDIA_CONTROL_INTERFACE, "Player")
            return str(player) if player else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Player property: {str(e)}", LOG__DEBUG)
            return None


class MediaEndpoint:
    """Wrapper for the org.bluez.MediaEndpoint1 interface."""
    
    def __init__(self, endpoint_path: str):
        """Initialize MediaEndpoint interface.
        
        Parameters
        ----------
        endpoint_path : str
            D-Bus path to the media endpoint
        """
        self.endpoint_path = endpoint_path
        self._bus = dbus.SystemBus()
        
        try:
            self._object = self._bus.get_object(BLUEZ_SERVICE_NAME, endpoint_path)
            self._interface = dbus.Interface(self._object, MEDIA_ENDPOINT_INTERFACE)
            self._properties = dbus.Interface(self._object, DBUS_PROPERTIES)
            self._introspection = self._interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] MediaEndpoint interface not available: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
    
    def get_properties(self) -> Dict[str, Any]:
        """Get all properties of the MediaEndpoint interface.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary of property names and values
        """
        try:
            props = self._properties.GetAll(MEDIA_ENDPOINT_INTERFACE)
            return dbus_to_python(props)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get MediaEndpoint properties: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
    
    def get_uuid(self) -> Optional[str]:
        """Get the UUID of the endpoint.
        
        Returns
        -------
        Optional[str]
            UUID of the endpoint or None if not available
        """
        try:
            uuid = self._properties.Get(MEDIA_ENDPOINT_INTERFACE, "UUID")
            return str(uuid) if uuid else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get UUID property: {str(e)}", LOG__DEBUG)
            return None
    
    def get_codec(self) -> Optional[int]:
        """Get the codec of the endpoint.
        
        Returns
        -------
        Optional[int]
            Codec ID or None if not available
        """
        try:
            codec = self._properties.Get(MEDIA_ENDPOINT_INTERFACE, "Codec")
            return int(codec) if codec is not None else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Codec property: {str(e)}", LOG__DEBUG)
            return None
    
    def get_capabilities(self) -> Optional[bytes]:
        """Get the capabilities of the endpoint.
        
        Returns
        -------
        Optional[bytes]
            Capabilities as bytes or None if not available
        """
        try:
            capabilities = self._properties.Get(MEDIA_ENDPOINT_INTERFACE, "Capabilities")
            return bytes(capabilities) if capabilities else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Capabilities property: {str(e)}", LOG__DEBUG)
            return None
    
    def get_device(self) -> Optional[str]:
        """Get the device object path associated with this endpoint.
        
        Returns
        -------
        Optional[str]
            Object path to the device or None if not available
        """
        try:
            device = self._properties.Get(MEDIA_ENDPOINT_INTERFACE, "Device")
            return str(device) if device else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Device property: {str(e)}", LOG__DEBUG)
            return None


class MediaTransport:
    """Wrapper for the org.bluez.MediaTransport1 interface."""
    
    def __init__(self, transport_path: str):
        """Initialize MediaTransport interface.
        
        Parameters
        ----------
        transport_path : str
            D-Bus path to the media transport
        """
        self.transport_path = transport_path
        self._bus = dbus.SystemBus()
        
        try:
            self._object = self._bus.get_object(BLUEZ_SERVICE_NAME, transport_path)
            self._interface = dbus.Interface(self._object, MEDIA_TRANSPORT_INTERFACE)
            self._properties = dbus.Interface(self._object, DBUS_PROPERTIES)
            self._introspection = self._interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] MediaTransport interface not available: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
    
    def get_properties(self) -> Dict[str, Any]:
        """Get all properties of the MediaTransport interface.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary of property names and values
        """
        try:
            props = self._properties.GetAll(MEDIA_TRANSPORT_INTERFACE)
            return dbus_to_python(props)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get MediaTransport properties: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
    
    def get_device(self) -> Optional[str]:
        """Get the device object path associated with this transport.
        
        Returns
        -------
        Optional[str]
            Object path to the device or None if not available
        """
        try:
            device = self._properties.Get(MEDIA_TRANSPORT_INTERFACE, "Device")
            return str(device) if device else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Device property: {str(e)}", LOG__DEBUG)
            return None
    
    def get_state(self) -> Optional[str]:
        """Get the state of the transport.
        
        Returns
        -------
        Optional[str]
            State of the transport (e.g., "idle", "pending", "active") or None if not available
        """
        try:
            state = self._properties.Get(MEDIA_TRANSPORT_INTERFACE, "State")
            return str(state) if state else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get State property: {str(e)}", LOG__DEBUG)
            return None
    
    def get_volume(self) -> Optional[int]:
        """Get the volume of the transport.
        
        Returns
        -------
        Optional[int]
            Volume level (0-127) or None if not available
        """
        try:
            volume = self._properties.Get(MEDIA_TRANSPORT_INTERFACE, "Volume")
            return int(volume) if volume is not None else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Volume property: {str(e)}", LOG__DEBUG)
            return None
    
    def set_volume(self, volume: int) -> bool:
        """Set the volume of the transport.
        
        Parameters
        ----------
        volume : int
            Volume level (0-127)
            
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        if not 0 <= volume <= 127:
            print_and_log(f"[-] Volume must be between 0 and 127", LOG__DEBUG)
            return False
            
        try:
            self._properties.Set(MEDIA_TRANSPORT_INTERFACE, "Volume", dbus.UInt16(volume))
            print_and_log(f"[+] Set volume to {volume}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to set Volume property: {str(e)}", LOG__DEBUG)
            return False
    
    def acquire(self) -> Tuple[int, int, int]:
        """Acquire the transport file descriptor and transport MTU for read/write.
        
        Returns
        -------
        Tuple[int, int, int]
            Tuple containing (fd, read_mtu, write_mtu)
            
        Raises
        ------
        BLEEPError
            If acquisition fails
        """
        try:
            fd, read_mtu, write_mtu = self._interface.Acquire()
            return int(fd), int(read_mtu), int(write_mtu)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to acquire transport: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
    
    def release(self) -> None:
        """Release the transport file descriptor.
        
        Raises
        ------
        BLEEPError
            If release fails
        """
        try:
            self._interface.Release()
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to release transport: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)


class MediaPlayer:
    """Wrapper for the org.bluez.MediaPlayer1 interface."""
    
    def __init__(self, player_path: str):
        """Initialize MediaPlayer interface.
        
        Parameters
        ----------
        player_path : str
            D-Bus path to the media player
        """
        self.player_path = player_path
        self._bus = dbus.SystemBus()
        
        try:
            self._object = self._bus.get_object(BLUEZ_SERVICE_NAME, player_path)
            self._interface = dbus.Interface(self._object, MEDIA_PLAYER_INTERFACE)
            self._properties = dbus.Interface(self._object, DBUS_PROPERTIES)
            self._introspection = self._interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] MediaPlayer interface not available: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
    
    def get_properties(self) -> Dict[str, Any]:
        """Get all properties of the MediaPlayer interface.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary of property names and values
        """
        try:
            props = self._properties.GetAll(MEDIA_PLAYER_INTERFACE)
            return dbus_to_python(props)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get MediaPlayer properties: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
    
    def get_name(self) -> Optional[str]:
        """Get the name of the player.
        
        Returns
        -------
        Optional[str]
            Name of the player or None if not available
        """
        try:
            name = self._properties.Get(MEDIA_PLAYER_INTERFACE, "Name")
            return str(name) if name else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Name property: {str(e)}", LOG__DEBUG)
            return None
    
    def get_status(self) -> Optional[str]:
        """Get the playback status of the player.
        
        Returns
        -------
        Optional[str]
            Status of the player (e.g., "playing", "paused", "stopped") or None if not available
        """
        try:
            status = self._properties.Get(MEDIA_PLAYER_INTERFACE, "Status")
            return str(status) if status else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Status property: {str(e)}", LOG__DEBUG)
            return None
    
    def get_track(self) -> Dict[str, Any]:
        """Get the current track information.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary of track metadata or empty dict if not available
        """
        try:
            track = self._properties.Get(MEDIA_PLAYER_INTERFACE, "Track")
            return dbus_to_python(track) if track else {}
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get Track property: {str(e)}", LOG__DEBUG)
            return {}
    
    def play(self) -> bool:
        """Start or resume playback.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        try:
            self._interface.Play()
            print_and_log(f"[+] Started playback", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to start playback: {str(e)}", LOG__DEBUG)
            return False
    
    def pause(self) -> bool:
        """Pause playback.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        try:
            self._interface.Pause()
            print_and_log(f"[+] Paused playback", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to pause playback: {str(e)}", LOG__DEBUG)
            return False
    
    def stop(self) -> bool:
        """Stop playback.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        try:
            self._interface.Stop()
            print_and_log(f"[+] Stopped playback", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to stop playback: {str(e)}", LOG__DEBUG)
            return False
    
    def next(self) -> bool:
        """Skip to the next track.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        try:
            self._interface.Next()
            print_and_log(f"[+] Skipped to next track", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to skip to next track: {str(e)}", LOG__DEBUG)
            return False
    
    def previous(self) -> bool:
        """Skip to the previous track.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        try:
            self._interface.Previous()
            print_and_log(f"[+] Skipped to previous track", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to skip to previous track: {str(e)}", LOG__DEBUG)
            return False
    
    def fast_forward(self) -> bool:
        """Fast-forward the current track.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        try:
            self._interface.FastForward()
            print_and_log(f"[+] Fast-forwarding", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to fast-forward: {str(e)}", LOG__DEBUG)
            return False
    
    def rewind(self) -> bool:
        """Rewind the current track.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        try:
            self._interface.Rewind()
            print_and_log(f"[+] Rewinding", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to rewind: {str(e)}", LOG__DEBUG)
            return False


def get_managed_objects() -> Dict[str, Any]:
    """Get all objects managed by BlueZ.
    
    Returns
    -------
    Dict[str, Any]
        Dictionary of object paths and their interfaces/properties
    """
    bus = dbus.SystemBus()
    manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, "/"),
        "org.freedesktop.DBus.ObjectManager"
    )
    return manager.GetManagedObjects()


def find_media_devices() -> Dict[str, Dict[str, Any]]:
    """Find all media devices and their interfaces.
    
    Returns
    -------
    Dict[str, Dict[str, Any]]
        Dictionary mapping device paths to their media interfaces
    """
    result = {}
    managed_objects = get_managed_objects()
    
    for path, interfaces in managed_objects.items():
        device_info = {}
        
        # Check for media-related interfaces
        if MEDIA_CONTROL_INTERFACE in interfaces:
            device_info["MediaControl"] = path
            
        if MEDIA_PLAYER_INTERFACE in interfaces:
            device_info["MediaPlayer"] = path
            
        # Look for MediaEndpoint1 and MediaTransport1 interfaces
        # These are typically under device paths with additional segments
        if path.startswith("/org/bluez/") and "/dev_" in path:
            base_device_path = path.split("/sep")[0].split("/fd")[0]
            
            # Store the base device path and any media-related interfaces
            if device_info and base_device_path not in result:
                result[base_device_path] = device_info
                
            # Check if this is an endpoint
            if MEDIA_ENDPOINT_INTERFACE in interfaces:
                if base_device_path not in result:
                    result[base_device_path] = {}
                if "MediaEndpoints" not in result[base_device_path]:
                    result[base_device_path]["MediaEndpoints"] = []
                result[base_device_path]["MediaEndpoints"].append(path)
                
            # Check if this is a transport
            if MEDIA_TRANSPORT_INTERFACE in interfaces:
                if base_device_path not in result:
                    result[base_device_path] = {}
                if "MediaTransports" not in result[base_device_path]:
                    result[base_device_path]["MediaTransports"] = []
                result[base_device_path]["MediaTransports"].append(path)
    
    return result


# ---------------------------------------------------------------------------
# Convenience helper functions (high-level wrappers) -------------------------
# ---------------------------------------------------------------------------


def pretty_print_track_info(track: Dict[str, Any]) -> str:
    """Return a human-readable multi-line summary of *track* metadata.

    Parameters
    ----------
    track : Dict[str, Any]
        Metadata dictionary as returned by ``MediaPlayer.get_track()``.

    Returns
    -------
    str
        Formatted string – lines are newline-separated for easy *print()*.
    """
    if not track:
        return "(no track playing)"

    parts: list[str] = []
    title = track.get("Title") or track.get("title")
    if title:
        parts.append(f"Title   : {title}")

    artist = track.get("Artist") or track.get("artist")
    if artist:
        parts.append(f"Artist  : {artist}")

    album = track.get("Album") or track.get("album")
    if album:
        parts.append(f"Album   : {album}")

    duration_us = track.get("Duration") or track.get("duration")
    if duration_us:
        # BlueZ reports micro-seconds – convert to mm:ss
        seconds = int(duration_us) // 1_000_000
        parts.append(f"Duration: {seconds // 60:02d}:{seconds % 60:02d}")

    indexed_fields = ("Genre", "NumberOfTracks", "TrackNumber")
    for field in indexed_fields:
        if field in track:
            parts.append(f"{field:10}: {track[field]}")

    return "\n".join(parts)


def get_player_properties_verbose(player: "MediaPlayer", include_track: bool = True) -> Dict[str, Any]:
    """Return all *MediaPlayer* properties in Python types with optional track.

    This is a thin wrapper that combines ``get_properties()`` and
    ``get_track()`` so callers don’t need two round-trips.
    """
    props = player.get_properties()
    if include_track:
        try:
            props["TrackMetadata"] = player.get_track()
        except NotSupportedError:
            # Some players do not implement GetTrack – ignore
            pass
    return props
