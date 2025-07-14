"""
BlueZ D-Bus device interface implementation.

This module provides the core device class for interacting with Bluetooth devices
via the BlueZ D-Bus interface. It handles device operations like connecting,
pairing, and GATT operations.
"""

import dbus
from typing import Optional, Dict, Any, Tuple

from bleep.bt_ref.constants import *
from bleep.bt_ref.error_map import handle_error, map_dbus_error
from bleep.core.log import logging__debug_log as debug_log


class system_dbus__bluez_device__low_energy:
    """
    Interface for interacting with a Bluetooth Low Energy device via BlueZ D-Bus.

    This class provides a high-level interface for device operations while handling
    errors and recovery strategies internally.
    """

    def __init__(self, ble_device_address: str, bluetooth_adapter: str = ADAPTER_NAME):
        """
        Initialize device interface.

        Args:
            ble_device_address: Device MAC address
            bluetooth_adapter: Bluetooth adapter name (default: "hci0")
        """
        self._bus = dbus.SystemBus()
        self._address = ble_device_address
        self._adapter = bluetooth_adapter
        self._device_path = None
        self._device_object = None
        self._device_interface = None
        self._device_properties = None

        self._setup_device()

    def _setup_device(self) -> None:
        """Set up the device D-Bus interfaces."""
        try:
            # Get device path
            self._device_path = (
                f"/org/bluez/{self._adapter}/dev_{self._address.replace(':', '_')}"
            )

            # Get device object
            self._device_object = self._bus.get_object(
                BLUEZ_SERVICE_NAME, self._device_path
            )

            # Get device interface
            self._device_interface = dbus.Interface(
                self._device_object, DEVICE_INTERFACE
            )

            # Get device properties
            self._device_properties = dbus.Interface(
                self._device_object, DBUS_PROPERTIES
            )

        except dbus.exceptions.DBusException as e:
            result_code, _ = map_dbus_error(e)
            debug_log(f"Device setup failed with result {result_code}")
            raise

    def Connect(self) -> Tuple[int, bool]:
        """
        Connect to the device.

        Returns:
            Tuple of (result_code, success)
        """
        try:
            self._device_interface.Connect()
            return RESULT_OK, True
        except Exception as e:
            return handle_error(e, self)

    def Disconnect(self) -> Tuple[int, bool]:
        """
        Disconnect from the device.

        Returns:
            Tuple of (result_code, success)
        """
        try:
            self._device_interface.Disconnect()
            return RESULT_OK, True
        except Exception as e:
            return handle_error(e, self)

    def Pair(self) -> Tuple[int, bool]:
        """
        Pair with the device.

        Returns:
            Tuple of (result_code, success)
        """
        try:
            self._device_interface.Pair()
            return RESULT_OK, True
        except Exception as e:
            return handle_error(e, self)

    def find_and_get__device_property(self, property_name: str) -> Any:
        """
        Get a device property value.

        Args:
            property_name: Name of property to get

        Returns:
            Property value

        Raises:
            DBusException if property doesn't exist
        """
        try:
            return self._device_properties.Get(DEVICE_INTERFACE, property_name)
        except dbus.exceptions.DBusException as e:
            result_code, _ = map_dbus_error(e)
            debug_log(
                f"Failed to get property {property_name} with result {result_code}"
            )
            raise

    def find_and_get__all_device_properties(self) -> Dict[str, Any]:
        """
        Get all device properties.

        Returns:
            Dictionary of property names to values

        Raises:
            DBusException if properties interface fails
        """
        try:
            return self._device_properties.GetAll(DEVICE_INTERFACE)
        except dbus.exceptions.DBusException as e:
            result_code, _ = map_dbus_error(e)
            debug_log(f"Failed to get all properties with result {result_code}")
            raise

    def check_and_wait__services_resolved(self, timeout_ms: int = 5000) -> bool:
        """
        Wait for device services to be resolved.

        Args:
            timeout_ms: Maximum time to wait in milliseconds

        Returns:
            True if services resolved, False if timed out
        """
        from time import time, sleep

        start = time()
        while (time() - start) * 1000 < timeout_ms:
            try:
                resolved = self.find_and_get__device_property("ServicesResolved")
                if resolved:
                    return True
                sleep(0.1)
            except Exception as e:
                debug_log(f"Error checking services resolved: {e}")
                return False

        return False

    @property
    def address(self) -> str:
        """Get device address."""
        return self._address

    @property
    def adapter(self) -> str:
        """Get adapter name."""
        return self._adapter

    @property
    def connected(self) -> bool:
        """Check if device is connected."""
        try:
            return bool(self.find_and_get__device_property("Connected"))
        except:
            return False

    @property
    def paired(self) -> bool:
        """Check if device is paired."""
        try:
            return bool(self.find_and_get__device_property("Paired"))
        except:
            return False

    @property
    def services_resolved(self) -> bool:
        """Check if device services are resolved."""
        try:
            return bool(self.find_and_get__device_property("ServicesResolved"))
        except:
            return False
