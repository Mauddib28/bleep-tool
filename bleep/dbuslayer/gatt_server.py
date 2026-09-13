"""GATT Server D-Bus layer (BZ-4, BZ-5).

Implements the server side of the BlueZ GATT interfaces, enabling BLEEP to
**publish** local GATT services that remote devices can discover, read, write,
and subscribe to.  Also provides ``GattProfileSkeleton`` (BZ-5) for GATT
client auto-connect profile registration.

Architecture
~~~~~~~~~~~~
* **GattApplication** — ``dbus.service.Object`` implementing
  ``org.freedesktop.DBus.ObjectManager``.  Root of the D-Bus hierarchy
  registered with ``GattManager1.RegisterApplication()``.
* **GattServiceSkeleton** — a single GATT service (UUID, primary flag).
* **GattCharacteristicSkeleton** — a single characteristic with
  ``ReadValue``/``WriteValue``/``StartNotify``/``StopNotify``/``Confirm``
  callbacks that subclasses override.
* **GattDescriptorSkeleton** — a single descriptor with
  ``ReadValue``/``WriteValue`` callbacks.
* **GattProfileSkeleton** — a GATT client profile (BZ-5) declaring interest
  in specific service UUIDs for auto-connect.
* **GattServerManager** — thin wrapper around ``GattManager1`` on the adapter
  for ``register_application``/``unregister_application``.

Reference: ``workDir/BlueZDocs/org.bluez.GattManager.rst``,
``workDir/BlueZDocs/org.bluez.GattCharacteristic.rst`` (Server section),
``workDir/BlueZDocs/org.bluez.GattProfile.rst``,
``workDir/BlueZScripts/example-gatt-server``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import dbus
import dbus.exceptions
import dbus.service

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    DBUS_OM_IFACE,
    DBUS_PROPERTIES,
    GATT_APP_BASE_PATH,
    GATT_CHARACTERISTIC_INTERFACE,
    GATT_DESCRIPTOR_INTERFACE,
    GATT_MANAGER_INTERFACE,
    GATT_PROFILE_INTERFACE,
    GATT_SERVICE_INTERFACE,
)
from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.dbuslayer._dbus_wait import call_async_await

__all__ = [
    "GattApplication",
    "GattProfileSkeleton",
    "GattServiceSkeleton",
    "GattCharacteristicSkeleton",
    "GattDescriptorSkeleton",
    "GattServerManager",
]


# ---------------------------------------------------------------------------
# D-Bus error types that BlueZ expects from server callbacks
# ---------------------------------------------------------------------------

class InvalidArgsError(dbus.exceptions.DBusException):
    _dbus_error_name = "org.freedesktop.DBus.Error.InvalidArgs"


class NotSupportedError(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotSupported"


class NotPermittedError(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotPermitted"


class InvalidValueLengthError(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.InvalidValueLength"


class FailedError(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.Failed"


# ---------------------------------------------------------------------------
# GattDescriptorSkeleton
# ---------------------------------------------------------------------------

class GattDescriptorSkeleton(dbus.service.Object):
    """Base class for a local GATT descriptor.

    Subclass and override :meth:`ReadValue` / :meth:`WriteValue` to provide
    custom behaviour.  Default implementations raise ``NotSupportedError``.
    """

    def __init__(
        self,
        bus: dbus.SystemBus,
        index: int,
        uuid: str,
        flags: List[str],
        characteristic: "GattCharacteristicSkeleton",
    ):
        self.path = f"{characteristic.path}/desc{index}"
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.characteristic = characteristic
        super().__init__(bus, self.path)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def get_properties(self) -> Dict[str, Dict[str, Any]]:
        return {
            GATT_DESCRIPTOR_INTERFACE: {
                "Characteristic": self.characteristic.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
            }
        }

    @dbus.service.method(DBUS_PROPERTIES, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str) -> Dict[str, Any]:
        if interface != GATT_DESCRIPTOR_INTERFACE:
            raise InvalidArgsError()
        return self.get_properties()[GATT_DESCRIPTOR_INTERFACE]

    @dbus.service.method(
        GATT_DESCRIPTOR_INTERFACE, in_signature="a{sv}", out_signature="ay"
    )
    def ReadValue(self, options: Dict[str, Any]) -> bytes:
        raise NotSupportedError()

    @dbus.service.method(GATT_DESCRIPTOR_INTERFACE, in_signature="aya{sv}")
    def WriteValue(self, value: Any, options: Dict[str, Any]) -> None:
        raise NotSupportedError()


# ---------------------------------------------------------------------------
# GattCharacteristicSkeleton
# ---------------------------------------------------------------------------

class GattCharacteristicSkeleton(dbus.service.Object):
    """Base class for a local GATT characteristic.

    Subclass and override :meth:`ReadValue`, :meth:`WriteValue`,
    :meth:`StartNotify`, :meth:`StopNotify` to provide custom behaviour.
    Use :meth:`send_notification` to push a value change to subscribed
    clients via ``PropertiesChanged``.
    """

    def __init__(
        self,
        bus: dbus.SystemBus,
        index: int,
        uuid: str,
        flags: List[str],
        service: "GattServiceSkeleton",
    ):
        self.path = f"{service.path}/char{index}"
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.service = service
        self.descriptors: List[GattDescriptorSkeleton] = []
        self.notifying = False
        super().__init__(bus, self.path)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def get_properties(self) -> Dict[str, Dict[str, Any]]:
        return {
            GATT_CHARACTERISTIC_INTERFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
                "Descriptors": dbus.Array(
                    [d.get_path() for d in self.descriptors], signature="o"
                ),
            }
        }

    def add_descriptor(self, descriptor: GattDescriptorSkeleton) -> None:
        self.descriptors.append(descriptor)

    # -- D-Bus methods invoked by bluetoothd --------------------------------

    @dbus.service.method(DBUS_PROPERTIES, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str) -> Dict[str, Any]:
        if interface != GATT_CHARACTERISTIC_INTERFACE:
            raise InvalidArgsError()
        return self.get_properties()[GATT_CHARACTERISTIC_INTERFACE]

    @dbus.service.method(
        GATT_CHARACTERISTIC_INTERFACE, in_signature="a{sv}", out_signature="ay"
    )
    def ReadValue(self, options: Dict[str, Any]) -> bytes:
        raise NotSupportedError()

    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE, in_signature="aya{sv}")
    def WriteValue(self, value: Any, options: Dict[str, Any]) -> None:
        raise NotSupportedError()

    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE)
    def StartNotify(self) -> None:
        if self.notifying:
            return
        self.notifying = True
        print_and_log(
            f"[DEBUG] Notifications started for {self.uuid}", LOG__DEBUG
        )

    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE)
    def StopNotify(self) -> None:
        if not self.notifying:
            return
        self.notifying = False
        print_and_log(
            f"[DEBUG] Notifications stopped for {self.uuid}", LOG__DEBUG
        )

    @dbus.service.method(GATT_CHARACTERISTIC_INTERFACE)
    def Confirm(self) -> None:
        """Acknowledge an indication delivery (BZ-3)."""
        print_and_log(
            f"[DEBUG] Indication confirmed for {self.uuid}", LOG__DEBUG
        )

    # -- Notification helper ------------------------------------------------

    @dbus.service.signal(DBUS_PROPERTIES, signature="sa{sv}as")
    def PropertiesChanged(
        self, interface: str, changed: Dict[str, Any], invalidated: List[str]
    ) -> None:
        pass

    def send_notification(self, value: bytes) -> None:
        """Push *value* to subscribed clients via ``PropertiesChanged``."""
        if not self.notifying:
            return
        self.PropertiesChanged(
            GATT_CHARACTERISTIC_INTERFACE,
            {"Value": dbus.Array([dbus.Byte(b) for b in value], signature="y")},
            [],
        )


# ---------------------------------------------------------------------------
# GattServiceSkeleton
# ---------------------------------------------------------------------------

class GattServiceSkeleton(dbus.service.Object):
    """A single local GATT service."""

    def __init__(
        self,
        bus: dbus.SystemBus,
        index: int,
        uuid: str,
        primary: bool = True,
    ):
        self.path = f"{GATT_APP_BASE_PATH}/service{index}"
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics: List[GattCharacteristicSkeleton] = []
        super().__init__(bus, self.path)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def get_properties(self) -> Dict[str, Dict[str, Any]]:
        return {
            GATT_SERVICE_INTERFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    [c.get_path() for c in self.characteristics], signature="o"
                ),
            }
        }

    def add_characteristic(self, char: GattCharacteristicSkeleton) -> None:
        self.characteristics.append(char)

    @dbus.service.method(DBUS_PROPERTIES, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str) -> Dict[str, Any]:
        if interface != GATT_SERVICE_INTERFACE:
            raise InvalidArgsError()
        return self.get_properties()[GATT_SERVICE_INTERFACE]


# ---------------------------------------------------------------------------
# GattProfileSkeleton (BZ-5)
# ---------------------------------------------------------------------------

class GattProfileSkeleton(dbus.service.Object):
    """GATT client profile for auto-connect (BZ-5).

    Registering a ``GattProfile1`` object with ``GattManager1`` tells bluetoothd
    to automatically connect to devices advertising the specified GATT service
    UUIDs.  bluetoothd calls :meth:`Release` when the profile is unregistered.

    Reference: ``workDir/BlueZDocs/org.bluez.GattProfile.rst``.
    """

    def __init__(
        self,
        bus: dbus.SystemBus,
        uuids: List[str],
        path: str = f"{GATT_APP_BASE_PATH}/profile0",
    ):
        self.path = path
        self.bus = bus
        self.uuids = uuids
        self._released = False
        super().__init__(bus, self.path)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def get_properties(self) -> Dict[str, Dict[str, Any]]:
        return {
            GATT_PROFILE_INTERFACE: {
                "UUIDs": dbus.Array(self.uuids, signature="s"),
            }
        }

    @dbus.service.method(DBUS_PROPERTIES, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str) -> Dict[str, Any]:
        if interface != GATT_PROFILE_INTERFACE:
            raise InvalidArgsError()
        return self.get_properties()[GATT_PROFILE_INTERFACE]

    @dbus.service.method(GATT_PROFILE_INTERFACE)
    def Release(self) -> None:
        """Called by bluetoothd when the profile is unregistered."""
        self._released = True
        print_and_log("[gatt-profile] Released by bluetoothd", LOG__DEBUG)
        self.on_release()

    def on_release(self) -> None:
        """Override to handle profile release cleanup."""


# ---------------------------------------------------------------------------
# GattApplication
# ---------------------------------------------------------------------------

class GattApplication(dbus.service.Object):
    """Root of the local GATT service hierarchy.

    Implements ``org.freedesktop.DBus.ObjectManager`` so bluetoothd can
    introspect all services, characteristics, descriptors, and profiles via
    ``GetManagedObjects``.
    """

    def __init__(self, bus: dbus.SystemBus):
        self.path = GATT_APP_BASE_PATH
        self.bus = bus
        self.services: List[GattServiceSkeleton] = []
        self.profiles: List[GattProfileSkeleton] = []
        super().__init__(bus, self.path)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def add_service(self, service: GattServiceSkeleton) -> None:
        self.services.append(service)

    def add_profile(self, profile: GattProfileSkeleton) -> None:
        self.profiles.append(profile)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        objects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for svc in self.services:
            objects[svc.get_path()] = svc.get_properties()
            for char in svc.characteristics:
                objects[char.get_path()] = char.get_properties()
                for desc in char.descriptors:
                    objects[desc.get_path()] = desc.get_properties()
        for prof in self.profiles:
            objects[prof.get_path()] = prof.get_properties()
        return objects

    def remove_all(self) -> None:
        """Remove all D-Bus objects from the connection."""
        for svc in self.services:
            for char in svc.characteristics:
                for desc in char.descriptors:
                    desc.remove_from_connection()
                char.remove_from_connection()
            svc.remove_from_connection()
        for prof in self.profiles:
            prof.remove_from_connection()
        self.services.clear()
        self.profiles.clear()


# ---------------------------------------------------------------------------
# GattServerManager — register / unregister with GattManager1
# ---------------------------------------------------------------------------

class GattServerManager:
    """Wrapper around ``GattManager1`` on the adapter.

    Registers/unregisters :class:`GattApplication` objects with bluetoothd.
    """

    def __init__(self, bus: dbus.SystemBus, adapter_path: str = "/org/bluez/hci0"):
        self.bus = bus
        self.adapter_path = adapter_path
        self._mgr_iface = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
            GATT_MANAGER_INTERFACE,
        )

    def register_application(
        self, app: GattApplication, options: Optional[Dict] = None
    ) -> bool:
        """Register *app* with bluetoothd.  Returns True on success."""
        return call_async_await(
            self._mgr_iface.RegisterApplication,
            app.get_path(),
            dbus.Dictionary(options or {}, signature="sv"),
            label="RegisterApplication",
        )

    def unregister_application(self, app: GattApplication) -> bool:
        """Unregister *app*.  Returns True on success."""
        return call_async_await(
            self._mgr_iface.UnregisterApplication,
            app.get_path(),
            label="UnregisterApplication",
            error_log_level=LOG__DEBUG,
        )
