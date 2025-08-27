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
    MEDIA_INTERFACE,
    MEDIA_FOLDER_INTERFACE,
    MEDIA_ITEM_INTERFACE,
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
    "find_media_objects",
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

    # ------------------------------------------------------------------
    # Deprecated AVRCP control helpers (still useful on legacy stacks) ---
    # ------------------------------------------------------------------

    def _call(self, method: str) -> bool:
        try:
            getattr(self._interface, method)()
            print_and_log(f"[+] MediaControl.{method}() executed", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] MediaControl.{method}() failed: {str(e)}", LOG__DEBUG)
            return False

    def play(self) -> bool:
        return self._call("Play")

    def pause(self) -> bool:
        return self._call("Pause")

    def stop(self) -> bool:
        return self._call("Stop")

    def next(self) -> bool:
        return self._call("Next")

    def previous(self) -> bool:
        return self._call("Previous")

    def fast_forward(self) -> bool:
        return self._call("FastForward")

    def rewind(self) -> bool:
        return self._call("Rewind")

    def volume_up(self) -> bool:
        return self._call("VolumeUp")

    def volume_down(self) -> bool:
        return self._call("VolumeDown")


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

    def _get_property(self, name: str):
        try:
            value = self._properties.Get(MEDIA_ENDPOINT_INTERFACE, name)
            return dbus_to_python(value)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get {name} property: {str(e)}", LOG__DEBUG)
            return None

    # Convenience getters -------------------------------------------------
    def get_vendor(self) -> Optional[int]:
        vendor = self._get_property("Vendor")
        return int(vendor) if vendor is not None else None

    def get_metadata(self) -> Optional[bytes]:
        data = self._get_property("Metadata")
        return bytes(data) if data else None

    def supports_delay_reporting(self) -> bool:
        return bool(self._get_property("DelayReporting"))

    def get_locations(self) -> Optional[int]:
        loc = self._get_property("Locations")
        return int(loc) if loc is not None else None

    def get_supported_context(self) -> Optional[int]:
        ctx = self._get_property("SupportedContext")
        return int(ctx) if ctx is not None else None

    def get_context(self) -> Optional[int]:
        ctx = self._get_property("Context")
        return int(ctx) if ctx is not None else None

    def get_qos(self):
        return self._get_property("QoS")


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
    
    # ------------------------------------------------------------------
    # Internal helpers ---------------------------------------------------
    # ------------------------------------------------------------------

    def _get_property(self, name: str):
        try:
            value = self._properties.Get(MEDIA_TRANSPORT_INTERFACE, name)
            return dbus_to_python(value)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get {name} property: {str(e)}", LOG__DEBUG)
            return None

    def _set_property(self, name: str, value) -> bool:
        try:
            self._properties.Set(MEDIA_TRANSPORT_INTERFACE, name, value)
            print_and_log(f"[+] Set {name} to {value}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to set {name} property: {str(e)}", LOG__DEBUG)
            return False

    # ------------------------------------------------------------------
    # Additional convenience wrappers -----------------------------------
    # ------------------------------------------------------------------

    def get_uuid(self) -> Optional[str]:
        return self._get_property("UUID")

    def get_codec(self) -> Optional[int]:
        codec = self._get_property("Codec")
        return int(codec) if codec is not None else None

    def get_configuration(self) -> Optional[bytes]:
        cfg = self._get_property("Configuration")
        return bytes(cfg) if cfg else None

    def get_delay(self) -> Optional[int]:
        delay = self._get_property("Delay")
        return int(delay) if delay is not None else None

    def set_delay(self, delay: int) -> bool:
        if delay < 0:
            print_and_log("[-] Delay cannot be negative", LOG__DEBUG)
            return False
        return self._set_property("Delay", dbus.UInt16(delay))

    def get_endpoint(self) -> Optional[str]:
        return self._get_property("Endpoint")

    def get_location(self) -> Optional[int]:
        loc = self._get_property("Location")
        return int(loc) if loc is not None else None

    def get_metadata(self) -> Optional[bytes]:
        data = self._get_property("Metadata")
        return bytes(data) if data else None

    def get_qos(self):
        return self._get_property("QoS")
    
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

    def get_position(self) -> int:
        """Get the current playback position in milliseconds
        
        Returns
        -------
        int
            Playback position in milliseconds

                - When the position is 0, is equates the track is starting
                - When the position is greater than or equal to the track's duration then the trac has ended
        """
        try:
            position = self._properties.Get(MEDIA_PLAYER_INTERFACE, "Position")
            return int(position) if position else None
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Falied to get Position property: {str(e)}", LOG__DEBUG)

    def set_position(self, position: int) -> bool:
        """Set the current playback position (in milliseconds)

        Parameters
        ----------
        position : int
            Playback position in milliseconds. Must be between 0 and the
            maximum value of an unsigned 32-bit integer (\(2^32 − 1\)).

            Note: Changing the position may generate additional events that will be sent to the remote device.
                - Even if duration is not available in metadata it is possible to signal its end by setting the position to the maximum value of an unsigned 32-bit integer.
        
        Raises
        ------
        BLEEPError
            If the position is negative
        BLEEPError
            If the position is greater than the maximum value of an unsigned 32-bit integer

        Returns
        -------
        bool
            True if the position was updated successfully, False otherwise.
        """
        # BlueZ expects an *unsigned* 32-bit value for Position.  Allow
        # callers to clamp to the valid range and guard against negatives.
        if position < 0:
            print_and_log("[-] Position cannot be negative", LOG__DEBUG)
            return False

        # Maximum representable value for the *uint32* Position field.
        MAX_U32 = 0xFFFFFFFF
        if position > MAX_U32:
            print_and_log(
                f"[!] Position capped to maximum uint32 value ({MAX_U32}) – signalling track end",  # noqa: E501
                LOG__DEBUG,
            )
            position = MAX_U32

        try:
            # Convert to dbus.UInt32 to satisfy the D-Bus signature.
            self._properties.Set(
                MEDIA_PLAYER_INTERFACE,
                "Position",
                dbus.UInt32(position),
            )
            print_and_log(f"[+] Set playback position to {position} ms", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            # Some players expose Position as read-only – map error and fall back.
            print_and_log(f"[-] Failed to set Position property: {str(e)}", LOG__DEBUG)
            return False
    
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

    # ------------------------------------------------------------------
    # Generic helpers (internal) ----------------------------------------
    # ------------------------------------------------------------------

    def _get_property(self, name: str):
        """Return *name* property converted to native Python or None on error."""
        try:
            value = self._properties.Get(MEDIA_PLAYER_INTERFACE, name)
            return dbus_to_python(value)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get {name} property: {str(e)}", LOG__DEBUG)
            return None

    def _set_property(self, name: str, value) -> bool:
        """Set *name* property – *value* must be D-Bus compatible."""
        try:
            self._properties.Set(MEDIA_PLAYER_INTERFACE, name, value)
            print_and_log(f"[+] Set {name} to {value}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to set {name} property: {str(e)}", LOG__DEBUG)
            return False

    # ------------------------------------------------------------------
    # Convenience properties (Equalizer / Repeat / Shuffle / Scan) ------
    # ------------------------------------------------------------------

    def get_equalizer(self) -> Optional[str]:
        return self._get_property("Equalizer")

    def set_equalizer(self, mode: str) -> bool:
        """Set Equalizer – valid modes: "off" | "on"""  # noqa: D401
        return self._set_property("Equalizer", dbus.String(mode))

    def get_repeat(self) -> Optional[str]:
        return self._get_property("Repeat")

    def set_repeat(self, mode: str) -> bool:
        """Set Repeat – modes: off | singletrack | alltracks | group"""
        return self._set_property("Repeat", dbus.String(mode))

    def get_shuffle(self) -> Optional[str]:
        return self._get_property("Shuffle")

    def set_shuffle(self, mode: str) -> bool:
        """Set Shuffle – modes: off | alltracks | group"""
        return self._set_property("Shuffle", dbus.String(mode))

    def get_scan(self) -> Optional[str]:
        return self._get_property("Scan")

    def set_scan(self, mode: str) -> bool:
        """Set Scan – modes: off | alltracks | group"""
        return self._set_property("Scan", dbus.String(mode))

    # ------------------------------------------------------------------
    # Additional read-only helpers --------------------------------------
    # ------------------------------------------------------------------

    def get_type(self) -> Optional[str]:
        return self._get_property("Type")

    def get_subtype(self) -> Optional[str]:
        return self._get_property("Subtype")

    def is_browsable(self) -> bool:
        return bool(self._get_property("Browsable"))

    def is_searchable(self) -> bool:
        return bool(self._get_property("Searchable"))

    def get_device(self) -> Optional[str]:
        return self._get_property("Device")

    def get_playlist(self) -> Optional[str]:
        return self._get_property("Playlist")

    def get_obex_port(self) -> Optional[int]:
        return self._get_property("ObexPort")

    # ------------------------------------------------------------------
    # Passthrough key operations ---------------------------------------
    # ------------------------------------------------------------------

    def _call(self, method: str, *args) -> bool:
        """Call *method* on the player interface, return success bool."""
        try:
            getattr(self._interface, method)(*args)
            print_and_log(f"[+] {method}() executed", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] {method}() failed: {str(e)}", LOG__DEBUG)
            return False

    def press(self, avc_key: int) -> bool:
        """Send *Press* passthrough key (see AVRCP spec for key codes)."""
        return self._call("Press", dbus.Byte(avc_key))

    def hold(self, avc_key: int) -> bool:
        """Send *Hold* passthrough key (caller must *release()* afterwards)."""
        return self._call("Hold", dbus.Byte(avc_key))

    def release_key(self) -> bool:
        """Release previously held key."""
        return self._call("Release")


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
# Extended enumeration helper (Phase-2) --------------------------------------
# ---------------------------------------------------------------------------


def find_media_objects() -> Dict[str, Any]:
    """Return a hierarchical view of all media-related BlueZ objects.

    The structure is intentionally simple so callers can iterate without deep
    knowledge of BlueZ path layout::

        {
            "MediaServices": [adapter_path, ...],
            "Players": {
                player_path: {"Device": dev_path | None},
            },
            "Folders": {
                folder_path: {"Player": player_path},
            },
            "Items": {
                item_path: {"Player": player_path},
            },
        }

    It does *not* resolve folder-inside-folder relationships – higher layers
    can follow the DBus paths for that detail.
    """

    managed_objects = get_managed_objects()

    media_services: list[str] = []
    players: dict[str, dict[str, Any]] = {}
    folders: dict[str, dict[str, Any]] = {}
    items: dict[str, dict[str, Any]] = {}

    for path, interfaces in managed_objects.items():
        # Adapter-level Media1 service
        if MEDIA_INTERFACE in interfaces:
            media_services.append(path)

        # Player objects
        if MEDIA_PLAYER_INTERFACE in interfaces:
            device_path = interfaces[MEDIA_PLAYER_INTERFACE].get("Device") if isinstance(interfaces[MEDIA_PLAYER_INTERFACE], dict) else None
            players[path] = {"Device": str(device_path) if device_path else None}

        # Folder objects
        if MEDIA_FOLDER_INTERFACE in interfaces:
            # player path is the segment before /folder or /nowplaying etc.
            base_player_path = path.split("/folder")[0].split("/NowPlaying")[0]
            folders[path] = {"Player": base_player_path}

        # Item objects
        if MEDIA_ITEM_INTERFACE in interfaces:
            base_player_path = path.split("/item")[0]
            items[path] = {"Player": base_player_path}

    return {
        "MediaServices": media_services,
        "Players": players,
        "Folders": folders,
        "Items": items,
    }


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
