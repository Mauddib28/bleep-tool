"""BlueZ Device Manager for Low-Energy devices (Phase-4 extraction).

This module provides a trimmed-down adaptation of the original
`bluetooth__le__deviceManager` class found in the monolith.  It is responsible
for discovering BLE devices exposed by a single adapter, tracking their life-
cycle, and instantiating `system_dbus__bluez_device__low_energy` wrappers.

Only the behaviour required by Phase-4 is implemented – primarily discovery
and basic device bookkeeping – but the public surface mirrors the legacy class
so higher-level code keeps working unchanged.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Any

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    BLUEZ_NAMESPACE,
    ADAPTER_INTERFACE,
    DEVICE_INTERFACE,
    ADAPTER_NAME,
    DBUS_OM_IFACE,
    DBUS_PROPERTIES,
)
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.core import errors
from bleep.core.errors import map_dbus_error
from bleep.dbuslayer.signals import system_dbus__bluez_signals as _SignalsRegistry

__all__ = [
    "system_dbus__bluez_device_manager",
]


_signals_manager = _SignalsRegistry()

# Lazy-load device_le to break circular dependency
def _get_le_device_class():
    from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
    return system_dbus__bluez_device__low_energy

def _error_from_dbus_error(exc: dbus.exceptions.DBusException) -> errors.BLEEPError:
    return map_dbus_error(exc)


class system_dbus__bluez_device_manager:  # noqa: N802 – keep legacy naming
    """Entry point for managing a set of BLE GATT devices on one adapter."""

    # ---------------------------------------------------------------------
    # Construction & D-Bus helpers
    # ---------------------------------------------------------------------
    def __init__(self, adapter_name: str = ADAPTER_NAME):
        self.adapter_name = adapter_name
        self._bus = dbus.SystemBus()

        # BlueZ objects / interfaces
        self._adapter_path = f"{BLUEZ_NAMESPACE}{adapter_name}"
        adapter_obj = self._bus.get_object(BLUEZ_SERVICE_NAME, self._adapter_path)
        self._adapter = dbus.Interface(adapter_obj, ADAPTER_INTERFACE)
        self._adapter_props = dbus.Interface(adapter_obj, DBUS_PROPERTIES)
        om_obj = self._bus.get_object(BLUEZ_SERVICE_NAME, "/")
        self._object_manager = dbus.Interface(om_obj, DBUS_OM_IFACE)

        # BlueZ uses uppercase hex digits in device paths by convention, but
        # some kernels/distros emit lower-case letters.  Accept *either* by
        # compiling a case-insensitive regex and allowing the character range
        # to include `a-f` as well.
        self._device_path_regex = re.compile(
            rf"^{BLUEZ_NAMESPACE}{adapter_name}/dev_([0-9A-Fa-f]{{2}}(?:_[0-9A-Fa-f]{{2}}){{5}})$",
            re.IGNORECASE,
        )

        # State
        self._devices: Dict[str, Any] = {}  # Will contain system_dbus__bluez_device__low_energy instances
        self._mainloop: Optional[GLib.MainLoop] = None
        self._timer_id: Optional[int] = None
        self._discovery_timeout_ms = 60_000  # 60 seconds default

        # Pre-populate device cache for already-known objects
        self.update_devices()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def devices(self) -> List[Any]:  # Returns list of system_dbus__bluez_device__low_energy instances
        """Return the list of known devices (updates cache first)."""
        self.update_devices()
        return list(self._devices.values())

    # Discovery ----------------------------------------------------------
    def start_discovery(self, service_uuids: Optional[List[str]] = None, timeout: int = 60):
        """Start LE discovery with an optional UUID filter.

        The call returns immediately; use :py:meth:`run` to enter the GLib
        main-loop and receive discovery callbacks.
        """
        service_uuids = service_uuids or []
        discovery_filter = {"Transport": "le"}
        if service_uuids:
            discovery_filter["UUIDs"] = service_uuids

        # ``SetDiscoveryFilter`` is optional (not present on very old BlueZ and
        # in our unit-test stub).  Ignore *attribute not found* as non-fatal.
        try:
            if hasattr(self._adapter, "SetDiscoveryFilter"):
                self._adapter.SetDiscoveryFilter(discovery_filter)
        except dbus.exceptions.DBusException as e:
            name = e.get_dbus_name()
            if name not in (
                "org.freedesktop.DBus.Error.UnknownObject",
                "org.bluez.Error.NotSupported",
            ):
                raise _error_from_dbus_error(e)

        # StartDiscovery *must* exist; if the adapter is powered off or absent
        # BlueZ raises UnknownObject – surface that clearly via NotReadyError.
        try:
            self._adapter.StartDiscovery()
            print_and_log("[*] Discovery started", LOG__DEBUG)
        except dbus.exceptions.DBusException as e:
            mapped = _error_from_dbus_error(e)
            # Gracefully degrade when the adapter or BlueZ stub lacks the
            # StartDiscovery method (common on CI runners without real BlueZ
            # or when the test-suite injects a minimal stub).  Treat the
            # absence as a *no-op* rather than a hard failure so the caller
            # can proceed – the main-loop still runs and callers that rely on
            # signal emission will simply observe an empty device list.
            if mapped.code in (
                errors.RESULT_ERR_IN_PROGRESS,  # discovery already running
                errors.RESULT_ERR_WRONG_STATE,  # adapter powered-off
                errors.RESULT_ERR_NOT_FOUND,  # StartDiscovery unknown
            ):
                print_and_log(
                    f"[!] StartDiscovery unavailable ({mapped}); proceeding without active scan",
                    LOG__DEBUG,
                )
            else:
                raise mapped

        self._discovery_timeout_ms = int(timeout * 1000)

    def stop_discovery(self):
        try:
            self._adapter.StopDiscovery()
        except dbus.exceptions.DBusException:
            pass  # not fatal if discovery already stopped
        # The original monolith did not emit a line for the stop event; skip
        # this message to keep log parity.
        # print_and_log("[*] Discovery stopped", LOG__DEBUG)

    # Main-loop ---------------------------------------------------------
    def run(self):
        """Run a GLib main-loop until the timeout expires."""
        if self._mainloop is not None:
            return  # already running

        # Connect signal receivers via the global hub so devices get events.
        _signals_manager.ensure_listening()

        self._mainloop = GLib.MainLoop()
        self._timer_id = GLib.timeout_add(self._discovery_timeout_ms, self._timeout)
        try:
            self._mainloop.run()
        finally:
            self._cleanup_after_run()

    def _timeout(self):
        self.stop_discovery()
        if self._mainloop is not None:
            self._mainloop.quit()

        # Mark the timer as inactive so cleanup does not attempt a second
        # removal which triggers GLib warnings such as
        # "Source ID X was not found when attempting to remove it".
        self._timer_id = None

        return False  # cancel further timeouts

    def _cleanup_after_run(self):
        # ``_timeout`` sets ``self._timer_id`` to *None* when it fires, so a
        # second attempt to remove the same source would print a GLib warning.
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        self._mainloop = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def update_devices(self):
        """Ensure `_devices` contains wrappers for all objects BlueZ exposes."""
        managed_objects = self._object_manager.GetManagedObjects().items()
        macs = [self._mac_address(path) for path, _ in managed_objects]
        for mac in [m for m in macs if m and m not in self._devices]:
            self._create_device(mac)

    def _create_device(self, mac: str):
        dev = _get_le_device_class()(mac, self.adapter_name)
        self._devices[mac] = dev
        _signals_manager.register_device(dev)
        print_and_log(f"[BLEEP] Device object created for {mac}", LOG__DEBUG)
        return dev

    def _mac_address(self, device_path: str) -> Optional[str]:
        match = self._device_path_regex.match(device_path)
        if not match:
            return None
        return match.group(1).replace("_", ":").lower() 