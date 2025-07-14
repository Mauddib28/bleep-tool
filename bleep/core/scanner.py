#!/usr/bin/python3

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.bt_ref.utils import *
from bleep.core.errors import BleepError, DeviceNotFoundError, ConnectionError
from bleep.core.log import get_logger
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter

logger = get_logger(__name__)


class system_dbus__scanner_service:
    """Core service for Bluetooth scanning operations while maintaining compatibility
    with existing system_dbus__bluez_adapter scanning functions."""

    def __init__(self):
        self.mainloop = None
        self.adapter_manager = None
        self.timer_id = None
        self.timer__default_time__ms = (
            5000  # Maintaining exact variable name from adapter_hardware
        )
        self._initialize_dbus()

    def _initialize_dbus(self):
        """Initialize D-Bus connection and mainloop."""
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self.system_bus = dbus.SystemBus()
            self.mainloop = GLib.MainLoop()
        except Exception as e:
            logger.error(f"Failed to initialize D-Bus: {e}")
            raise BleepError("D-Bus initialization failed")

    def get_adapter(self, adapter_name=ADAPTER_NAME):
        """Get or create adapter manager instance."""
        try:
            if not self.adapter_manager:
                self.adapter_manager = system_dbus__bluez_adapter(adapter_name)
            return self.adapter_manager
        except Exception as e:
            logger.error(f"Failed to get adapter {adapter_name}: {e}")
            raise BleepError(f"Failed to get adapter {adapter_name}")

    def run_scan__basic(self):
        """Execute basic scan using existing adapter functionality."""
        try:
            adapter = self.get_adapter()
            return adapter.run_scan()
        except Exception as e:
            logger.error(f"Basic scan failed: {e}")
            raise BleepError("Basic scan failed")

    def run_scan__timed(self, timeout_ms=None):
        """Execute timed scan using existing adapter functionality."""
        try:
            adapter = self.get_adapter()
            if timeout_ms:
                adapter.timer__default_time__ms = timeout_ms
            return adapter.run_scan__timed()
        except Exception as e:
            logger.error(f"Timed scan failed: {e}")
            raise BleepError("Timed scan failed")

    def set_discovery_filter(self, discovery_filter):
        """Set discovery filter using existing adapter functionality."""
        try:
            adapter = self.get_adapter()
            return adapter.set_discovery_filter(discovery_filter)
        except Exception as e:
            logger.error(f"Failed to set discovery filter: {e}")
            raise BleepError("Failed to set discovery filter")

    def create_and_return__bluetooth_scan__discovered_devices(self):
        """Return discovered devices using existing adapter functionality."""
        try:
            adapter = self.get_adapter()
            return adapter.get_discovered_devices()
        except Exception as e:
            logger.error(f"Failed to get discovered devices: {e}")
            raise BleepError("Failed to get discovered devices")

    def create_and_return__bluetooth_scan__discovered_devices__specific_adapter(
        self, adapter_name=ADAPTER_NAME
    ):
        """Return discovered devices for specific adapter using existing adapter functionality."""
        try:
            adapter = self.get_adapter(adapter_name)
            return adapter.get_discovered_devices()
        except Exception as e:
            logger.error(
                f"Failed to get discovered devices for adapter {adapter_name}: {e}"
            )
            raise BleepError(
                f"Failed to get discovered devices for adapter {adapter_name}"
            )

    def run_and_detect__bluetooth_devices__with_filter(
        self, discovery_filter=None, timeout_ms=None
    ):
        """Run scan with filter and return discovered devices."""
        try:
            adapter = self.get_adapter()

            if discovery_filter:
                adapter.set_discovery_filter(discovery_filter)

            if timeout_ms:
                adapter.timer__default_time__ms = timeout_ms

            adapter.run_scan__timed()
            return self.create_and_return__bluetooth_scan__discovered_devices()
        except Exception as e:
            logger.error(f"Scan and detect failed: {e}")
            raise BleepError("Scan and detect failed")

    def run_and_detect__bluetooth_devices__with_filter__specific_adapter(
        self, adapter_name=ADAPTER_NAME, discovery_filter=None, timeout_ms=None
    ):
        """Run scan with filter on specific adapter and return discovered devices."""
        try:
            adapter = self.get_adapter(adapter_name)

            if discovery_filter:
                adapter.set_discovery_filter(discovery_filter)

            if timeout_ms:
                adapter.timer__default_time__ms = timeout_ms

            adapter.run_scan__timed()
            return self.create_and_return__bluetooth_scan__discovered_devices__specific_adapter(
                adapter_name
            )
        except Exception as e:
            logger.error(f"Scan and detect failed for adapter {adapter_name}: {e}")
            raise BleepError(f"Scan and detect failed for adapter {adapter_name}")
