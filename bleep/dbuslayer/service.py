"""Simple GATT Service abstraction used by system_dbus__bluez_device__low_energy.

Only provides signal-connect placeholders; real characteristic handling will be
added during Phase-5.
"""

from __future__ import annotations

import dbus
import re
from gi.repository import GLib
from typing import Optional, Dict, Any

from bleep.bt_ref.constants import (
    GATT_SERVICE_INTERFACE,
    GATT_CHARACTERISTIC_INTERFACE,
    DBUS_PROPERTIES,
    DEVICE_INTERFACE,
    GATT_DESCRIPTOR_INTERFACE,
    BLUEZ_SERVICE_NAME,
)
from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.dbuslayer.characteristic import Characteristic
from bleep.dbuslayer.descriptor import Descriptor

__all__ = ["Service"]


def _print_detailed_dbus_error(exc: Exception) -> None:
    """Print detailed information about a D-Bus exception.
    
    This function extracts and displays:
    - The full D-Bus error name (e.g., org.freedesktop.DBus.Error.InvalidArgs)
    - The error message and arguments
    - For InvalidArgs errors, it tries to extract the specific method, interface or property name
    """
    if isinstance(exc, dbus.exceptions.DBusException):
        error_name = exc.get_dbus_name()
        error_msg = str(exc)
        
        print_and_log(f"[-] D-Bus Error: {error_name}", LOG__DEBUG)
        print_and_log(f"[-] Message: {error_msg}", LOG__DEBUG)
        
        # Extract method/property name for InvalidArgs errors
        if error_name == "org.freedesktop.DBus.Error.InvalidArgs":
            # Try to extract the property or method name from the error message
            prop_match = re.search(r"property '([^']+)'", error_msg)
            method_match = re.search(r"method '([^']+)'", error_msg)
            iface_match = re.search(r"interface '([^']+)'", error_msg)
            
            if prop_match:
                print_and_log(f"[-] Invalid property: {prop_match.group(1)}", LOG__DEBUG)
            if method_match:
                print_and_log(f"[-] Invalid method: {method_match.group(1)}", LOG__DEBUG)
            if iface_match:
                print_and_log(f"[-] On interface: {iface_match.group(1)}", LOG__DEBUG)
    else:
        print_and_log(f"[-] Error: {exc}", LOG__DEBUG)
        print_and_log(f"[-] Type: {type(exc).__name__}", LOG__DEBUG)


class Service:  # noqa: N801 – keep simple name
    def __init__(self, bus_or_device, path: str, uuid: str, primary: bool = True):
        # Handle both device object and direct bus object
        if hasattr(bus_or_device, '_bus'):
            # It's a device object
            self.device = bus_or_device
            self.bus = bus_or_device._bus
        else:
            # It's a bus object directly
            self.device = None
            self.bus = bus_or_device
            
        self.path = path
        self.uuid = uuid
        self.primary = primary
        self.handle = None
        
        # Get the bus name to use for the object
        bus_name = BLUEZ_SERVICE_NAME
        if self.device and hasattr(self.device, '_device_iface') and hasattr(self.device._device_iface, 'bus_name'):
            bus_name = self.device._device_iface.bus_name
            
        self._props_iface = dbus.Interface(
            self.bus.get_object(bus_name, path), DBUS_PROPERTIES
        )
        self._signal = None
        self.characteristics: list[Characteristic] = []
        
        # Try to get the Handle property, if available
        try:
            self.handle = self.get_handle()
        except Exception as e:
            print_and_log(f"[-] Error getting handle: {e}", LOG__DEBUG)
            _print_detailed_dbus_error(e)

    # ------------------------------------------------------------------
    # Signal wiring (placeholders)
    # ------------------------------------------------------------------
    def _connect_signals(self):
        if self._signal is None:
            self._signal = self._props_iface.connect_to_signal(
                "PropertiesChanged", self._props_changed
            )

    def _disconnect_signals(self):
        if self._signal is not None:
            try:
                self._signal.remove()
            finally:
                self._signal = None

    # ------------------------------------------------------------------
    # Signal callbacks
    # ------------------------------------------------------------------
    def _props_changed(self, interface, changed, invalidated):
        print_and_log(
            f"[DEBUG] Service {self.uuid} properties changed: {dict(changed)}",
            LOG__DEBUG,
        )

    def discover_characteristics(self):
        """Populate `self.characteristics` with Characteristic objects."""
        if self.characteristics:
            return self.characteristics  # already populated
            
        if self.device is None:
            # If we don't have a device object, we can't use its object manager
            # Instead, we'll get managed objects directly from the bus
            obj_manager = dbus.Interface(
                self.bus.get_object(BLUEZ_SERVICE_NAME, "/"),
                "org.freedesktop.DBus.ObjectManager"
            )
            managed = obj_manager.GetManagedObjects()
        else:
            # Use the device's object manager
            managed = self.device._object_manager.GetManagedObjects()
            
        char_prefix = f"{self.path}/char"
        for path, interfaces in managed.items():
            if not path.startswith(char_prefix):
                continue
            if GATT_CHARACTERISTIC_INTERFACE not in interfaces:
                continue
            char_obj = Characteristic(self.bus, path, self.uuid)
            # Discover descriptors under this characteristic
            descs: list[Descriptor] = []
            desc_prefix = f"{path}/desc"
            for dpath, dintf in managed.items():
                if dpath.startswith(desc_prefix) and GATT_DESCRIPTOR_INTERFACE in dintf:
                    descs.append(Descriptor(self.bus, dpath, char_obj.uuid))
            char_obj.descriptors = descs  # type: ignore[attr-defined]
            self.characteristics.append(char_obj)
        return self.characteristics

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def get_handle(self):
        """Try to get the Handle property, if available"""
        try:
            return int(self._props_iface.Get(GATT_SERVICE_INTERFACE, "Handle"))
        except dbus.exceptions.DBusException as e:
            if e.get_dbus_name() == "org.freedesktop.DBus.Error.InvalidArgs":
                # Handle property not available, extract from path
                match = re.search(r"service([0-9a-f]{4})$", self.path, re.IGNORECASE)
                if match:
                    return int(match.group(1), 16)
                else:
                    return -1  # Default to -1 if no handle can be extracted
            else:
                raise
                
    def get_characteristics(self):
        """Get the characteristics for this service.
        
        Returns
        -------
        list
            List of Characteristic objects
        """
        # Ensure characteristics are discovered
        if not self.characteristics:
            self.discover_characteristics()
        return self.characteristics