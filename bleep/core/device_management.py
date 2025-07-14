#!/usr/bin/python3

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.bt_ref.utils import *
from bleep.core.errors import BleepError, DeviceNotFoundError, ConnectionError
from bleep.core.log import get_logger

logger = get_logger(__name__)

_GLOBAL_SIGNALS = None

def _get_global_signals():
    """Get the global signals manager instance.
    
    Returns
    -------
    system_dbus__bluez_signals
        The global signals manager instance
    """
    global _GLOBAL_SIGNALS
    if _GLOBAL_SIGNALS is None:
        from bleep.dbuslayer.signals import system_dbus__bluez_signals
        _GLOBAL_SIGNALS = system_dbus__bluez_signals()
    return _GLOBAL_SIGNALS

class system_dbus__device_management_service:
    """Core service for managing Bluetooth device operations while maintaining compatibility
    with existing system_dbus__bluez_adapter and system_dbus__bluez_device__low_energy classes.
    """

    def __init__(self):
        self.mainloop = None
        self.adapter_manager = None
        self._signals = None
        self._initialize_dbus()
        self._initialize_signals()

    def _initialize_dbus(self):
        """Initialize D-Bus connection and mainloop."""
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self.system_bus = dbus.SystemBus()
            self.mainloop = GLib.MainLoop()
        except Exception as e:
            logger.error(f"Failed to initialize D-Bus: {e}")
            raise BleepError("D-Bus initialization failed")

    def _initialize_signals(self):
        """Initialize the signals manager."""
        try:
            from bleep.dbuslayer.signals import system_dbus__bluez_signals
            self._signals = system_dbus__bluez_signals()
            
            # Also set as global for static access
            global _GLOBAL_SIGNALS
            _GLOBAL_SIGNALS = self._signals
            
            logger.debug("Signals manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize signals manager: {e}")

    def get_signals_manager(self):
        """Get the signals manager instance.
        
        Returns
        -------
        system_dbus__bluez_signals
            The signals manager instance
        """
        if not self._signals:
            self._initialize_signals()
        return self._signals

    def get_adapter(self, adapter_name=ADAPTER_NAME):
        """Get or create adapter manager instance."""
        try:
            if not self.adapter_manager:
                from bleep.dbuslayer.adapter import system_dbus__bluez_adapter

                self.adapter_manager = system_dbus__bluez_adapter(adapter_name)
            return self.adapter_manager
        except Exception as e:
            logger.error(f"Failed to get adapter {adapter_name}: {e}")
            raise BleepError(f"Failed to get adapter {adapter_name}")

    def discover_devices(self, timeout_ms=5000, transport_type="auto"):
        """Discover Bluetooth devices using existing adapter functionality."""
        try:
            adapter = self.get_adapter()
            discovery_filter = {"Transport": transport_type}
            return adapter.run_and_detect__bluetooth_devices__with_provided_filter__with_timeout(
                discovery_filter=discovery_filter, timeout_ms=timeout_ms
            )
        except Exception as e:
            logger.error(f"Device discovery failed: {e}")
            raise BleepError("Device discovery failed")

    def connect_device(self, device_address, timeout_ms=10000, device_type="auto"):
        """Connect to a Bluetooth device using existing connection handlers.
        
        Parameters
        ----------
        device_address : str
            MAC address of the device to connect to
        timeout_ms : int, optional
            Connection timeout in milliseconds, by default 10000
        device_type : str, optional
            Type of device to connect to: "auto", "le", or "classic", by default "auto"
            
        Returns
        -------
        device
            Connected device object
            
        Raises
        ------
        BleepError
            If connection fails
        """
        try:
            # Determine device type if auto
            if device_type == "auto":
                # Try to determine device type from adapter properties
                adapter = self.get_adapter()
                devices = adapter.get_devices()
                for device in devices:
                    if device["address"].lower() == device_address.lower():
                        # Check device type if available
                        if "type" in device:
                            if device["type"].lower() == "br/edr":
                                device_type = "classic"
                            elif device["type"].lower() == "le":
                                device_type = "le"
                            elif device["type"].lower() == "dual":
                                # For dual-mode devices, prefer LE
                                device_type = "le"
                        break
                
                # If still auto, default to LE
                if device_type == "auto":
                    device_type = "le"
            
            # Connect based on device type
            if device_type == "classic":
                from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic
                
                device = system_dbus__bluez_device__classic(
                    device_address, self.get_adapter().adapter_name
                )
                if not device.connect(wait_timeout=timeout_ms/1000):
                    raise ConnectionError(device_address, "connect failed")
                return device
            else:  # LE or default
                from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
                
                device = system_dbus__bluez_device__low_energy(
                    device_address, self.get_adapter().adapter_name
                )
                if not device.connect(wait_timeout=timeout_ms/1000):
                    raise ConnectionError(device_address, "connect failed")
                return device
        except Exception as e:
            logger.error(f"Failed to connect to device {device_address}: {e}")
            raise BleepError(f"Device connection failed: {e}")

    def disconnect_device(self, device_address):
        """Disconnect from a Bluetooth device."""
        try:
            from bleep.dbuslayer.device import system_dbus__bluez_device__low_energy

            device = system_dbus__bluez_device__low_energy(
                device_address, self.get_adapter().adapter_name
            )
            if not device.disconnect():
                raise ConnectionError(device_address, "disconnect failed")
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect device {device_address}: {e}")
            raise BleepError(f"Device disconnection failed: {e}")

    def get_device_info(self, device_address):
        """Get detailed information about a device."""
        try:
            from bleep.dbuslayer.device import system_dbus__bluez_device__low_energy

            device = system_dbus__bluez_device__low_energy(
                device_address, self.get_adapter().adapter_name
            )
            return {
                "address": device.mac_address,
                "name": device.alias(),
                "connected": device.is_connected(),
                "services_resolved": device.is_services_resolved(),
                "rssi": None,
                "tx_power": None,
            }
        except Exception as e:
            logger.error(f"Failed to get device info for {device_address}: {e}")
            raise BleepError(f"Failed to get device info: {e}")

    def enumerate_services(self, device_address):
        """Enumerate services for a connected device using existing enumeration logic."""
        try:
            from bleep.ble_ops.connect import (
                connect_and_enumerate__bluetooth__low_energy as _connect_enum,
            )

            device, mapping, landmine_map, perm_map = _connect_enum(device_address)

            return {
                "device": device,
                "mapping": mapping,
                "landmine_map": landmine_map,
                "permission_map": perm_map,
            }
        except Exception as e:
            logger.error(f"Service enumeration failed for {device_address}: {e}")
            raise BleepError(f"Service enumeration failed: {e}")
