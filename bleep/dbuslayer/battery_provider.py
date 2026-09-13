"""BatteryProvider1 D-Bus wrapper (BZ-9/10).

Enables BLEEP to feed custom battery level data to BlueZ so it appears
on the standard ``org.bluez.Battery1`` interface.  Useful for devices
that report battery via non-standard GATT characteristics or Classic
AT commands that BlueZ's built-in parser cannot decode.

Architecture
~~~~~~~~~~~~
* **BatteryProviderApp** — ``dbus.service.Object`` implementing
  ``org.freedesktop.DBus.ObjectManager``.  Root of the battery provider
  hierarchy registered with ``BatteryProviderManager1.RegisterBatteryProvider()``.
* **BatteryProviderObject** — a single battery object exposing
  ``Percentage``, ``Source``, and ``Device`` properties via
  ``org.bluez.BatteryProvider1``.
* **BatteryProviderManager** — thin wrapper around
  ``BatteryProviderManager1`` on the adapter.

Reference: ``workDir/BlueZDocs/org.bluez.BatteryProvider.rst``,
``workDir/BlueZDocs/org.bluez.BatteryProviderManager.rst``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import dbus
import dbus.exceptions
import dbus.service

from bleep.bt_ref.constants import (
    BATTERY_PROVIDER_BASE_PATH,
    BATTERY_PROVIDER_INTERFACE,
    BATTERY_PROVIDER_MANAGER_INTERFACE,
    BLUEZ_SERVICE_NAME,
    DBUS_OM_IFACE,
    DBUS_PROPERTIES,
)
from bleep.core.log import print_and_log, LOG__DEBUG

__all__ = [
    "BatteryProviderApp",
    "BatteryProviderObject",
    "BatteryProviderManager",
]


class BatteryProviderObject(dbus.service.Object):
    """A single battery level exposed via ``BatteryProvider1``.

    Parameters
    ----------
    bus : dbus.SystemBus
        System bus connection.
    index : int
        Numeric index for this battery object (sets D-Bus path).
    device_path : str
        Object path of the device this battery belongs to
        (e.g. ``/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF``).
    percentage : int
        Battery level 0-100.
    source : str, optional
        Freeform string describing where the value came from
        (e.g. ``"GATT BAS"``, ``"HFP AT+IPHONEACCEV"``).
    """

    def __init__(
        self,
        bus: dbus.SystemBus,
        index: int,
        device_path: str,
        percentage: int,
        source: Optional[str] = None,
    ):
        self.path = f"{BATTERY_PROVIDER_BASE_PATH}/bat{index}"
        self.bus = bus
        self._device_path = device_path
        self._percentage = max(0, min(100, percentage))
        self._source = source
        super().__init__(bus, self.path)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def get_properties(self) -> Dict[str, Dict[str, Any]]:
        props: Dict[str, Any] = {
            "Percentage": dbus.Byte(self._percentage),
            "Device": dbus.ObjectPath(self._device_path),
        }
        if self._source is not None:
            props["Source"] = dbus.String(self._source)
        return {BATTERY_PROVIDER_INTERFACE: props}

    def update_percentage(self, percentage: int) -> None:
        """Update battery level and emit PropertiesChanged."""
        self._percentage = max(0, min(100, percentage))
        self.PropertiesChanged(
            BATTERY_PROVIDER_INTERFACE,
            {"Percentage": dbus.Byte(self._percentage)},
            [],
        )

    @dbus.service.method(DBUS_PROPERTIES, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str) -> Dict[str, Any]:
        if interface != BATTERY_PROVIDER_INTERFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs",
            )
        return self.get_properties()[BATTERY_PROVIDER_INTERFACE]

    @dbus.service.signal(DBUS_PROPERTIES, signature="sa{sv}as")
    def PropertiesChanged(
        self, interface: str, changed: Dict[str, Any], invalidated: List[str],
    ) -> None:
        pass


class BatteryProviderApp(dbus.service.Object):
    """ObjectManager root for battery provider objects.

    Register with ``BatteryProviderManager1.RegisterBatteryProvider()``
    so bluetoothd discovers child ``BatteryProviderObject`` instances.
    """

    def __init__(self, bus: dbus.SystemBus):
        self.path = BATTERY_PROVIDER_BASE_PATH
        self.bus = bus
        self.batteries: List[BatteryProviderObject] = []
        super().__init__(bus, self.path)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def add_battery(self, battery: BatteryProviderObject) -> None:
        self.batteries.append(battery)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        objects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for bat in self.batteries:
            objects[bat.get_path()] = bat.get_properties()
        return objects

    def remove_all(self) -> None:
        """Remove all battery objects from the connection."""
        for bat in self.batteries:
            bat.remove_from_connection()
        self.batteries.clear()


class BatteryProviderManager:
    """Wrapper around ``BatteryProviderManager1`` on the adapter.

    Registers/unregisters :class:`BatteryProviderApp` objects with bluetoothd.
    """

    def __init__(self, bus: dbus.SystemBus, adapter_path: str = "/org/bluez/hci0"):
        self.bus = bus
        self.adapter_path = adapter_path
        self._mgr_iface = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
            BATTERY_PROVIDER_MANAGER_INTERFACE,
        )

    def register(self, app: BatteryProviderApp) -> bool:
        """Register *app* with bluetoothd.  Returns True on success."""
        try:
            self._mgr_iface.RegisterBatteryProvider(app.get_path())
            print_and_log(
                f"[+] BatteryProvider registered at {app.get_path()}", LOG__DEBUG,
            )
            return True
        except dbus.exceptions.DBusException as exc:
            print_and_log(
                f"[-] RegisterBatteryProvider failed: {exc}", LOG__DEBUG,
            )
            return False

    def unregister(self, app: BatteryProviderApp) -> bool:
        """Unregister *app*.  Returns True on success."""
        try:
            self._mgr_iface.UnregisterBatteryProvider(app.get_path())
            print_and_log(
                f"[+] BatteryProvider unregistered at {app.get_path()}", LOG__DEBUG,
            )
            return True
        except dbus.exceptions.DBusException as exc:
            print_and_log(
                f"[-] UnregisterBatteryProvider failed: {exc}", LOG__DEBUG,
            )
            return False
