"""
Bluetooth Classic device implementation for the BlueZ stack.

This module provides support for Bluetooth Classic (BR/EDR) devices, 
complementing the existing BLE support in the BLEEP framework.
"""

from __future__ import annotations

import dbus
import time
from typing import Dict, Any, Optional, List, Tuple

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    BLUEZ_NAMESPACE,
    ADAPTER_NAME,
    DEVICE_INTERFACE,
    DBUS_PROPERTIES,
    DBUS_OM_IFACE,
    RESULT_ERR_UNKNOWN_OBJECT,
)
from bleep.bt_ref.utils import dbus_to_python, device_address_to_path
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__USER
from bleep.core.errors import map_dbus_error, BLEEPError, ConnectionError

__all__ = [
    "system_dbus__bluez_device__classic",
]


class system_dbus__bluez_device__classic:
    """Wrapper around a single Bluetooth Classic device exposed by BlueZ."""
    
    def __init__(self, mac_address: str, adapter_name: str = ADAPTER_NAME):
        """Initialize a Bluetooth Classic device."""
        self.mac_address = mac_address.lower()
        self.adapter_name = adapter_name
        
        self._bus = dbus.SystemBus()
        self._object_manager = dbus.Interface(
            self._bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE
        )
        
        self._device_path: str = device_address_to_path(
            self.mac_address.upper(), f"{BLUEZ_NAMESPACE}{adapter_name}"
        )
        try:
            device_object = self._bus.get_object(BLUEZ_SERVICE_NAME, self._device_path)
            self._device_iface = dbus.Interface(device_object, DEVICE_INTERFACE)
            self._props_iface = dbus.Interface(device_object, DBUS_PROPERTIES)
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
            
        # Signal bookkeeping
        self._properties_signal = None
        self._connect_retry_attempt = 0
        
        # Profile tracking
        self._supported_profiles = []
        self._connected_profiles = []
    # ---------------------------------------------------------------------
    # Pairing & Trust Management
    # ---------------------------------------------------------------------
    def pair(self, timeout: int = 30) -> bool:
        """Pair with the device.
        
        Parameters
        ----------
        timeout : int, optional
            Seconds to wait for pairing to complete, by default 30
            
        Returns
        -------
        bool
            True if pairing was successful
            
        Raises
        ------
        BLEEPError
            If pairing fails
        """
        print_and_log(f"[*] Attempting to pair with {self.mac_address}", LOG__USER)
        try:
            self._device_iface.Pair(timeout=dbus.UInt32(timeout))
            print_and_log(f"[+] Successfully paired with {self.mac_address}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Pairing failed: {str(e)}", LOG__GENERAL)
            raise map_dbus_error(e)
            
    def set_trusted(self, trusted: bool = True) -> bool:
        """Set the device as trusted or untrusted.
        
        Parameters
        ----------
        trusted : bool, optional
            Whether to trust the device, by default True
            
        Returns
        -------
        bool
            True if the operation was successful
            
        Raises
        ------
        BLEEPError
            If setting trust failed
        """
        try:
            self._props_iface.Set(DEVICE_INTERFACE, "Trusted", dbus.Boolean(trusted))
            trust_status = "trusted" if trusted else "untrusted"
            print_and_log(f"[*] Device {self.mac_address} set as {trust_status}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Setting trust failed: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
            
    # ---------------------------------------------------------------------
    # Connection Management
    # ---------------------------------------------------------------------
    def connect(self, retry: int = 3, wait_timeout: float = 10.0) -> bool:
        """Connect to the device.
        
        Parameters
        ----------
        retry : int, optional
            Number of connection attempts, by default 3
        wait_timeout : float, optional
            Seconds to wait for connection to complete, by default 10.0
            
        Returns
        -------
        bool
            True if connection was successful
            
        Raises
        ------
        ConnectionError
            If connection fails
        """
        print_and_log(f"[*] Attempting connection to {self.mac_address}", LOG__USER)
        self._connect_retry_attempt = 0
        self._attach_property_signal()
        
        while self._connect_retry_attempt < retry:
            try:
                # Try to disconnect first to ensure clean slate
                try:
                    self._device_iface.Disconnect()
                except dbus.exceptions.DBusException:
                    # Ignore - device was not connected
                    pass
                    
                self._connect_retry_attempt += 1
                print_and_log(
                    f"[*] Connect attempt {self._connect_retry_attempt}/{retry}",
                    LOG__DEBUG,
                )
                
                self._device_iface.Connect()
                
                # Wait for connection to complete
                waited = 0.0
                while waited < wait_timeout:
                    if self.is_connected():
                        print_and_log(f"[+] Connected to {self.mac_address}", LOG__GENERAL)
                        self._update_profiles()
                        return True
                    time.sleep(0.1)
                    waited += 0.1
                    
                print_and_log(f"[-] Connection timed out", LOG__DEBUG)
                
            except dbus.exceptions.DBusException as e:
                print_and_log(f"[-] Connection failed: {str(e)}", LOG__DEBUG)
                if self._connect_retry_attempt >= retry:
                    error = map_dbus_error(e)
                    raise ConnectionError(self.mac_address, str(error))
                    
        return False
        
    def disconnect(self) -> bool:
        """Disconnect from the device.
        
        Returns
        -------
        bool
            True if disconnection was successful
            
        Raises
        ------
        BLEEPError
            If disconnection fails
        """
        try:
            if self.is_connected():
                print_and_log(f"[*] Disconnecting from {self.mac_address}", LOG__USER)
                self._device_iface.Disconnect()
                
                # Wait for disconnection to complete
                timeout = 5.0
                waited = 0.0
                while waited < timeout:
                    if not self.is_connected():
                        print_and_log(f"[+] Disconnected from {self.mac_address}", LOG__GENERAL)
                        self._connected_profiles = []
                        return True
                    time.sleep(0.1)
                    waited += 0.1
                    
                print_and_log(f"[-] Disconnection timed out", LOG__DEBUG)
                return False
            else:
                print_and_log(f"[*] Device {self.mac_address} already disconnected", LOG__DEBUG)
                return True
                
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Disconnection failed: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
            
    # ---------------------------------------------------------------------
    # Properties & State
    # ---------------------------------------------------------------------
    def is_connected(self) -> bool:
        """Check if the device is connected.
        
        Returns
        -------
        bool
            True if connected, False otherwise
        """
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "Connected"))
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Error checking connection status: {str(e)}", LOG__DEBUG)
            return False
            
    def alias(self) -> Optional[str]:
        """Get the device alias (friendly name).
        
        Returns
        -------
        Optional[str]
            Device alias or None if not available
        """
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "Alias"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the Alias
            error = map_dbus_error(e)
            if error.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise error
            
    def get_device_class(self) -> Optional[int]:
        """Get the device class code.
        
        Returns
        -------
        Optional[int]
            Device class code or None if not available
        """
        try:
            return int(self._props_iface.Get(DEVICE_INTERFACE, "Class"))
        except (dbus.exceptions.DBusException, KeyError, ValueError):
            return None
            
    def get_device_type(self) -> Optional[str]:
        """Get the device type.
        
        Returns
        -------
        Optional[str]
            Device type ('dual', 'br/edr', 'le') or None if not available
        """
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "Type"))
        except (dbus.exceptions.DBusException, KeyError):
            return None
            
    # ---------------------------------------------------------------------
    # Profile Management
    # ---------------------------------------------------------------------
    def _update_profiles(self) -> None:
        """Update the list of supported and connected profiles."""
        try:
            # Get UUIDs of supported profiles
            uuids = self._props_iface.Get(DEVICE_INTERFACE, "UUIDs")
            self._supported_profiles = [str(uuid) for uuid in uuids]
            
            # Determine connected profiles based on device properties
            # This is an approximation as BlueZ doesn't expose this directly
            self._connected_profiles = []
            
            # Check for common profile states
            if self.is_connected():
                # A2DP Sink profile
                if "0000110b-0000-1000-8000-00805f9b34fb" in self._supported_profiles:
                    try:
                        # Check if audio is connected
                        audio_connected = self._props_iface.Get(DEVICE_INTERFACE, "Connected")
                        if audio_connected:
                            self._connected_profiles.append("0000110b-0000-1000-8000-00805f9b34fb")
                    except (dbus.exceptions.DBusException, KeyError):
                        pass
                        
                # HFP Hands-Free profile
                if "0000111e-0000-1000-8000-00805f9b34fb" in self._supported_profiles:
                    try:
                        # Check if HFP is connected
                        hfp_connected = self._props_iface.Get(DEVICE_INTERFACE, "Connected")
                        if hfp_connected:
                            self._connected_profiles.append("0000111e-0000-1000-8000-00805f9b34fb")
                    except (dbus.exceptions.DBusException, KeyError):
                        pass
                        
        except (dbus.exceptions.DBusException, KeyError) as e:
            print_and_log(f"[-] Error updating profiles: {str(e)}", LOG__DEBUG)
            
    def get_supported_profiles(self) -> List[str]:
        """Get the list of profiles supported by the device.
        
        Returns
        -------
        List[str]
            List of profile UUIDs supported by the device
        """
        try:
            uuids = self._props_iface.Get(DEVICE_INTERFACE, "UUIDs")
            return [str(uuid) for uuid in uuids]
        except (dbus.exceptions.DBusException, KeyError):
            return []
            
    def get_connected_profiles(self) -> List[str]:
        """Get the list of currently connected profiles.
        
        Returns
        -------
        List[str]
            List of connected profile UUIDs
        """
        self._update_profiles()
        return self._connected_profiles
        
    def connect_profile(self, profile_uuid: str) -> bool:
        """Connect to a specific profile.
        
        Parameters
        ----------
        profile_uuid : str
            UUID of the profile to connect to
            
        Returns
        -------
        bool
            True if profile connection was successful
            
        Raises
        ------
        BLEEPError
            If profile connection fails
        """
        try:
            print_and_log(f"[*] Connecting profile {profile_uuid} on {self.mac_address}", LOG__USER)
            self._device_iface.ConnectProfile(profile_uuid)
            
            # Wait for profile to connect
            timeout = 5.0
            waited = 0.0
            while waited < timeout:
                self._update_profiles()
                if profile_uuid in self._connected_profiles:
                    print_and_log(f"[+] Profile {profile_uuid} connected", LOG__GENERAL)
                    return True
                time.sleep(0.5)
                waited += 0.5
                
            print_and_log(f"[-] Profile connection timed out", LOG__DEBUG)
            return False
            
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Profile connection failed: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
            
    def disconnect_profile(self, profile_uuid: str) -> bool:
        """Disconnect from a specific profile.
        
        Parameters
        ----------
        profile_uuid : str
            UUID of the profile to disconnect from
            
        Returns
        -------
        bool
            True if profile disconnection was successful
            
        Raises
        ------
        BLEEPError
            If profile disconnection fails
        """
        try:
            print_and_log(f"[*] Disconnecting profile {profile_uuid} on {self.mac_address}", LOG__USER)
            self._device_iface.DisconnectProfile(profile_uuid)
            
            # Wait for profile to disconnect
            timeout = 5.0
            waited = 0.0
            while waited < timeout:
                self._update_profiles()
                if profile_uuid not in self._connected_profiles:
                    print_and_log(f"[+] Profile {profile_uuid} disconnected", LOG__GENERAL)
                    return True
                time.sleep(0.5)
                waited += 0.5
                
            print_and_log(f"[-] Profile disconnection timed out", LOG__DEBUG)
            return False
            
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Profile disconnection failed: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
            
    # ---------------------------------------------------------------------
    # Device Information
    # ---------------------------------------------------------------------
    def get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive information about the device.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary with device information
        """
        info = {
            "address": self.mac_address,
            "name": self.alias(),
            "connected": self.is_connected(),
            "device_class": self.get_device_class(),
            "device_type": self.get_device_type(),
            "supported_profiles": self.get_supported_profiles(),
            "connected_profiles": self.get_connected_profiles(),
        }
        
        # Add additional properties if available
        try:
            info["rssi"] = self._props_iface.Get(DEVICE_INTERFACE, "RSSI")
        except (dbus.exceptions.DBusException, KeyError):
            info["rssi"] = None
            
        try:
            info["tx_power"] = self._props_iface.Get(DEVICE_INTERFACE, "TxPower")
        except (dbus.exceptions.DBusException, KeyError):
            info["tx_power"] = None
            
        try:
            info["paired"] = bool(self._props_iface.Get(DEVICE_INTERFACE, "Paired"))
        except (dbus.exceptions.DBusException, KeyError):
            info["paired"] = None
            
        try:
            info["trusted"] = bool(self._props_iface.Get(DEVICE_INTERFACE, "Trusted"))
        except (dbus.exceptions.DBusException, KeyError):
            info["trusted"] = None
            
        try:
            info["blocked"] = bool(self._props_iface.Get(DEVICE_INTERFACE, "Blocked"))
        except (dbus.exceptions.DBusException, KeyError):
            info["blocked"] = None
            
        try:
            info["legacy_pairing"] = bool(self._props_iface.Get(DEVICE_INTERFACE, "LegacyPairing"))
        except (dbus.exceptions.DBusException, KeyError):
            info["legacy_pairing"] = None
            
        return info
        
    # ---------------------------------------------------------------------
    # Signal Handling
    # ---------------------------------------------------------------------
    def _attach_property_signal(self) -> None:
        """Attach signal handler for property changes."""
        if self._properties_signal is None:
            self._properties_signal = self._bus.add_signal_receiver(
                self._properties_changed,
                bus_name=BLUEZ_SERVICE_NAME,
                dbus_interface=DBUS_PROPERTIES,
                signal_name="PropertiesChanged",
                path=self._device_path,
            )
            
    def _properties_changed(self, interface: str, changed: Dict[str, Any], invalidated: List[str]) -> None:
        """Handle property changes.
        
        Parameters
        ----------
        interface : str
            D-Bus interface that changed
        changed : Dict[str, Any]
            Dictionary of changed properties
        invalidated : List[str]
            List of invalidated properties
        """
        if interface != DEVICE_INTERFACE:
            return
            
        if "Connected" in changed:
            if changed["Connected"]:
                print_and_log(f"[*] Device {self.mac_address} connected", LOG__DEBUG)
                self._update_profiles()
            else:
                print_and_log(f"[*] Device {self.mac_address} disconnected", LOG__DEBUG)
                self._connected_profiles = []
                
    def _detach_property_signal(self) -> None:
        """Detach signal handler for property changes."""
        if self._properties_signal is not None:
            self._properties_signal.remove()
            self._properties_signal = None
            
    # ---------------------------------------------------------------------
    # Representation
    # ---------------------------------------------------------------------
    def __repr__(self) -> str:
        """String representation of the device.
        
        Returns
        -------
        str
            String representation
        """
        return f"<BTClassicDevice {self.mac_address} connected={self.is_connected()}>"
