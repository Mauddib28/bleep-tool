"""
Adapter D-Bus Interface
Provides the system_dbus__bluez_adapter class from the original codebase.
"""

#!/usr/bin/python3

import dbus
import dbus.mainloop.glib
from gi.repository import GLib
import time

from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import get_logger
from bleep.dbuslayer.manager import (
    system_dbus__bluez_device_manager as _DeviceManager,
)

logger = get_logger(__name__)


class system_dbus__bluez_adapter:
    """Core adapter class for Bluetooth operations."""

    def __init__(self, bluetooth_adapter=ADAPTER_NAME):
        self.adapter_name = bluetooth_adapter
        self.adapter_path = f"/org/bluez/{bluetooth_adapter}"
        self.mainloop = None
        self.timer_id = None
        self.timer__default_time__ms = 5000
        self._device_manager: _DeviceManager | None = None
        self._initialize_dbus()

    def _initialize_dbus(self):
        """Initialize D-Bus connection and mainloop."""
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self.system_bus = dbus.SystemBus()
            self.mainloop = GLib.MainLoop()

            self.adapter_object = self.system_bus.get_object(
                BLUEZ_SERVICE_NAME, self.adapter_path
            )
            self.adapter_interface = dbus.Interface(
                self.adapter_object, ADAPTER_INTERFACE
            )
            self.adapter_properties = dbus.Interface(
                self.adapter_object, DBUS_PROPERTIES
            )

        except Exception as e:
            logger.error(f"Failed to initialize D-Bus: {e}")
            raise BleepError("D-Bus initialization failed")

    def run_scan(self):
        """Execute basic scan."""
        try:
            self.adapter_interface.StartDiscovery()
            return True
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return False

    def run_scan__timed(self, duration: int | None = None):
        """Execute a scan that stops automatically after *duration* seconds.

        If *duration* is omitted the adapter's ``timer__default_time__ms``
        (5 s) is used – kept for backward compatibility with the monolith.
        """
        timeout_ms = int(duration * 1000) if duration else self.timer__default_time__ms
        try:
            self.adapter_interface.StartDiscovery()
            self.timer_id = GLib.timeout_add(timeout_ms, self._discovery_timeout)
            self.mainloop.run()
            return True
        except Exception as e:
            logger.error(f"Timed scan failed: {e}")
            return False

    def _discovery_timeout(self):
        """Handle discovery timeout."""
        try:
            self.adapter_interface.StopDiscovery()
            self.mainloop.quit()
            GLib.source_remove(self.timer_id)
            return False
        except Exception as e:
            logger.error(f"Discovery timeout handling failed: {e}")
            return False

    def set_discovery_filter(self, discovery_filter):
        """Set discovery filter."""
        try:
            self.adapter_interface.SetDiscoveryFilter(discovery_filter)
            return True
        except Exception as e:
            logger.error(f"Failed to set discovery filter: {e}")
            return False

    def get_managed_objects(self):
        """Get all managed objects."""
        try:
            object_manager = dbus.Interface(
                self.system_bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE
            )
            return object_manager.GetManagedObjects()
        except Exception as e:
            logger.error(f"Failed to get managed objects: {e}")
            return None

    def get_discovered_devices(self):
        """Get list of discovered devices."""
        try:
            managed_objects = self.get_managed_objects()
            if not managed_objects:
                return []

            devices = []
            for path, interfaces in managed_objects.items():
                if DEVICE_INTERFACE not in interfaces:
                    continue

                properties = interfaces[DEVICE_INTERFACE]
                devices.append(
                    {
                        "path": path,
                        "address": properties.get("Address", ""),
                        "name": properties.get("Name", ""),
                        "rssi": properties.get("RSSI") if "RSSI" in properties else None,
                        "alias": properties.get("Alias", ""),
                        "type": (
                            "LE"
                            if properties.get("AddressType") == "random"
                            else "BR/EDR"
                        ),
                    }
                )

            return devices
        except Exception as e:
            logger.error(f"Failed to get discovered devices: {e}")
            return []

    def create_device_manager(self) -> _DeviceManager:
        """Return (or lazily create) a device manager bound to this adapter."""
        if self._device_manager is None:
            self._device_manager = _DeviceManager(self.adapter_name)
        return self._device_manager

    # Convenience pass-throughs ------------------------------------------
    def start_discovery(self, uuids: list[str] | None = None, timeout: int = 60):
        """Start LE discovery via the underlying device manager."""
        self.create_device_manager().start_discovery(uuids, timeout)

    def stop_discovery(self):
        """Stop discovery if a manager is present."""
        if self._device_manager:
            self._device_manager.stop_discovery()

    def devices(self):
        """Return the list of known devices (empties list if manager not yet created)."""
        if self._device_manager:
            return self._device_manager.devices()
        return []

    # ------------------------------------------------------------------
    # Adapter power helpers (new in Phase-8)
    # ------------------------------------------------------------------

    def power_cycle(self, off_delay: float = 0.5):
        """Toggle *Powered* property OFF → ON to reset the controller."""
        try:
            self.adapter_properties.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(False))
            time.sleep(off_delay)
            self.adapter_properties.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(True))
            logger.debug("Adapter power-cycled successfully")
            return True
        except Exception as e:
            logger.error(f"Adapter power-cycle failed: {e}")
            return False

    def is_ready(self) -> bool:
        """Return True when the adapter object exists and *Powered* is True.

        This mirrors the monolith's initial guard clause which aborted early
        when no Bluetooth controller was present or it was soft-blocked.
        """

        try:
            powered = self.adapter_properties.Get(ADAPTER_INTERFACE, "Powered")
            return bool(powered)
        except Exception:
            return False


# Re-export the class
__all__ = ["system_dbus__bluez_adapter"]
