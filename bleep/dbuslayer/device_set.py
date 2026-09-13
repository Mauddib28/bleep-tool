"""DeviceSet1 D-Bus wrapper (BZ-15).

Wraps the ``org.bluez.DeviceSet1`` interface for coordinated device sets
(e.g. TWS earbuds).  Provides ``connect()``/``disconnect()`` on the set and
read access to set properties (``Adapter``, ``AutoConnect``, ``Devices``,
``Size``).

The interface is **experimental** in BlueZ and requires ``--experimental``.
Object paths follow the pattern ``/org/bluez/hci0/set_{sirk}``.

Reference: ``workDir/BlueZDocs/org.bluez.DeviceSet.rst``.
"""

from __future__ import annotations

from typing import Any, List, Optional

import dbus
import dbus.exceptions

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    DBUS_PROPERTIES,
    DEVICE_SET_INTERFACE,
)
from bleep.core.errors import map_dbus_error
from bleep.core.log import print_and_log, LOG__DEBUG

__all__ = ["DeviceSet"]


class DeviceSet:
    """Proxy for a single ``DeviceSet1`` object.

    Parameters
    ----------
    bus : dbus.SystemBus
        System bus connection.
    set_path : str
        D-Bus object path of the device set.
    """

    def __init__(self, bus: dbus.SystemBus, set_path: str):
        self._bus = bus
        self._path = set_path
        obj = bus.get_object(BLUEZ_SERVICE_NAME, set_path)
        self._iface = dbus.Interface(obj, DEVICE_SET_INTERFACE)
        self._props = dbus.Interface(obj, DBUS_PROPERTIES)

    @property
    def path(self) -> str:
        return self._path

    # -- Methods -----------------------------------------------------------

    def connect(self) -> None:
        """Connect all member devices in sequence."""
        try:
            self._iface.Connect()
        except dbus.exceptions.DBusException as exc:
            raise map_dbus_error(exc) from exc

    def disconnect(self) -> None:
        """Disconnect all member devices in sequence."""
        try:
            self._iface.Disconnect()
        except dbus.exceptions.DBusException as exc:
            raise map_dbus_error(exc) from exc

    # -- Properties --------------------------------------------------------

    def get_adapter(self) -> Optional[str]:
        """Return the adapter object path this set belongs to."""
        try:
            return str(self._props.Get(DEVICE_SET_INTERFACE, "Adapter"))
        except dbus.exceptions.DBusException:
            return None

    def get_auto_connect(self) -> Optional[bool]:
        """Return whether auto-connect is enabled for set members."""
        try:
            return bool(self._props.Get(DEVICE_SET_INTERFACE, "AutoConnect"))
        except dbus.exceptions.DBusException:
            return None

    def set_auto_connect(self, enabled: bool) -> None:
        """Toggle auto-connect for the device set."""
        try:
            self._props.Set(
                DEVICE_SET_INTERFACE, "AutoConnect", dbus.Boolean(enabled),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_dbus_error(exc) from exc

    def get_devices(self) -> List[str]:
        """Return list of member device object paths."""
        try:
            raw = self._props.Get(DEVICE_SET_INTERFACE, "Devices")
            return [str(p) for p in raw]
        except dbus.exceptions.DBusException:
            return []

    def get_size(self) -> int:
        """Return the expected number of members in the set."""
        try:
            return int(self._props.Get(DEVICE_SET_INTERFACE, "Size"))
        except dbus.exceptions.DBusException:
            return 0

    def get_info(self) -> dict[str, Any]:
        """Return a dict summarizing the set for display."""
        return {
            "path": self._path,
            "adapter": self.get_adapter(),
            "auto_connect": self.get_auto_connect(),
            "devices": self.get_devices(),
            "size": self.get_size(),
        }


def enumerate_device_sets(
    bus: dbus.SystemBus, adapter_path: str = "/org/bluez/hci0",
) -> List[DeviceSet]:
    """Discover all DeviceSet1 objects under *adapter_path*."""
    from bleep.bt_ref.constants import DBUS_OM_IFACE

    try:
        om = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE,
        )
        managed = om.GetManagedObjects()
    except dbus.exceptions.DBusException:
        return []

    sets: List[DeviceSet] = []
    prefix = adapter_path + "/set_"
    for path, ifaces in managed.items():
        path_str = str(path)
        if path_str.startswith(prefix) and DEVICE_SET_INTERFACE in ifaces:
            sets.append(DeviceSet(bus, path_str))
    return sets
