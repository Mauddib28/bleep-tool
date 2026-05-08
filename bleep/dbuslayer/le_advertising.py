"""LE Advertising D-Bus layer (BZ-6/7).

Implements the client side of the BlueZ ``LEAdvertisement1`` and
``LEAdvertisingManager1`` interfaces.  This enables BLEEP to **broadcast**
custom BLE advertisement packets — service UUIDs, manufacturer data, local
name, appearance, etc. — from the local adapter.

Architecture
~~~~~~~~~~~~
* **LEAdvertisement** — ``dbus.service.Object`` exposing advertisement
  properties (Type, ServiceUUIDs, ManufacturerData, LocalName, …) and a
  ``Release()`` callback invoked by bluetoothd when the advert is removed.
* **LEAdvertisingManager** — thin wrapper that discovers the manager interface
  on the adapter and exposes ``register``/``unregister``/capability queries.

Reference: ``workDir/BlueZDocs/org.bluez.LEAdvertisement.rst``,
``workDir/BlueZDocs/org.bluez.LEAdvertisingManager.rst``,
``workDir/BlueZScripts/example-advertisement``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import dbus
import dbus.service

from bleep.bt_ref.constants import (
    ADVERTISEMENT_INTERFACE,
    ADVERTISING_MANAGER_INTERFACE,
    BLUEZ_SERVICE_NAME,
    DBUS_PROPERTIES,
    LE_ADVERTISEMENT_BASE_PATH,
)
from bleep.core.log import print_and_log, LOG__DEBUG

__all__ = [
    "LEAdvertisement",
    "LEAdvertisingManager",
    "AdvertisementConfig",
]


@dataclass
class AdvertisementConfig:
    """Configuration for a single LE advertisement.

    All optional fields that are ``None`` are omitted from the D-Bus
    properties, meaning they won't appear in the advertising data.
    """
    ad_type: str = "peripheral"
    service_uuids: Optional[List[str]] = None
    manufacturer_data: Optional[Dict[int, bytes]] = None
    solicit_uuids: Optional[List[str]] = None
    service_data: Optional[Dict[str, bytes]] = None
    local_name: Optional[str] = None
    includes: Optional[List[str]] = None
    appearance: Optional[int] = None
    discoverable: Optional[bool] = None
    discoverable_timeout: Optional[int] = None
    duration: Optional[int] = None
    timeout: Optional[int] = None
    tx_power: Optional[int] = None
    min_interval: Optional[int] = None
    max_interval: Optional[int] = None
    secondary_channel: Optional[str] = None
    data: Optional[Dict[int, bytes]] = None


class LEAdvertisement(dbus.service.Object):
    """A single LE advertisement registered with BlueZ.

    bluetoothd reads properties via ``GetAll`` and invokes ``Release()``
    when the advertisement is removed (adapter down, instance limit, etc.).
    """

    _next_id = 0

    def __init__(
        self,
        bus: dbus.SystemBus,
        config: AdvertisementConfig,
        on_release: Optional[Callable[[], None]] = None,
        adv_id: Optional[int] = None,
    ):
        if adv_id is None:
            adv_id = LEAdvertisement._next_id
            LEAdvertisement._next_id += 1

        self.path = f"{LE_ADVERTISEMENT_BASE_PATH}{adv_id}"
        self.bus = bus
        self.config = config
        self._on_release = on_release

        super().__init__(bus, self.path)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def _build_properties(self) -> Dict[str, Any]:
        c = self.config
        props: Dict[str, Any] = {"Type": dbus.String(c.ad_type)}

        if c.service_uuids:
            props["ServiceUUIDs"] = dbus.Array(c.service_uuids, signature="s")

        if c.manufacturer_data:
            props["ManufacturerData"] = dbus.Dictionary(
                {
                    dbus.UInt16(k): dbus.Array([dbus.Byte(b) for b in v], signature="y")
                    for k, v in c.manufacturer_data.items()
                },
                signature="qv",
            )

        if c.solicit_uuids:
            props["SolicitUUIDs"] = dbus.Array(c.solicit_uuids, signature="s")

        if c.service_data:
            props["ServiceData"] = dbus.Dictionary(
                {
                    dbus.String(k): dbus.Array([dbus.Byte(b) for b in v], signature="y")
                    for k, v in c.service_data.items()
                },
                signature="sv",
            )

        if c.local_name is not None:
            props["LocalName"] = dbus.String(c.local_name)

        if c.includes:
            props["Includes"] = dbus.Array(c.includes, signature="s")

        if c.appearance is not None:
            props["Appearance"] = dbus.UInt16(c.appearance)

        if c.discoverable is not None:
            props["Discoverable"] = dbus.Boolean(c.discoverable)

        if c.discoverable_timeout is not None:
            props["DiscoverableTimeout"] = dbus.UInt16(c.discoverable_timeout)

        if c.duration is not None:
            props["Duration"] = dbus.UInt16(c.duration)

        if c.timeout is not None:
            props["Timeout"] = dbus.UInt16(c.timeout)

        if c.tx_power is not None:
            props["TxPower"] = dbus.Int16(c.tx_power)

        if c.min_interval is not None:
            props["MinInterval"] = dbus.UInt32(c.min_interval)

        if c.max_interval is not None:
            props["MaxInterval"] = dbus.UInt32(c.max_interval)

        if c.secondary_channel is not None:
            props["SecondaryChannel"] = dbus.String(c.secondary_channel)

        if c.data:
            props["Data"] = dbus.Dictionary(
                {
                    dbus.Byte(k): dbus.Array([dbus.Byte(b) for b in v], signature="y")
                    for k, v in c.data.items()
                },
                signature="yv",
            )

        return props

    def remove_advertisement(self) -> None:
        self.remove_from_connection()

    # -- Methods invoked BY bluetoothd --------------------------------------

    @dbus.service.method(DBUS_PROPERTIES, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str) -> Dict[str, Any]:
        if interface != ADVERTISEMENT_INTERFACE:
            return {}
        return self._build_properties()

    @dbus.service.method(ADVERTISEMENT_INTERFACE, in_signature="", out_signature="")
    def Release(self) -> None:
        print_and_log(f"[-] Advertisement {self.path} released by BlueZ", LOG__DEBUG)
        if self._on_release:
            self._on_release()


class LEAdvertisingManager:
    """Wrapper around ``LEAdvertisingManager1`` on the adapter.

    Discovers the manager, reads capabilities/instances, and
    registers/unregisters :class:`LEAdvertisement` objects.
    """

    def __init__(self, bus: dbus.SystemBus, adapter_path: str = "/org/bluez/hci0"):
        self.bus = bus
        self.adapter_path = adapter_path
        self._mgr_iface = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
            ADVERTISING_MANAGER_INTERFACE,
        )
        self._props_iface = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
            DBUS_PROPERTIES,
        )

    # -- Capabilities -------------------------------------------------------

    def _read_prop(self, name: str) -> Any:
        try:
            return self._props_iface.Get(ADVERTISING_MANAGER_INTERFACE, name)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[WARN] Cannot read {name}: {e}", LOG__DEBUG)
            return None

    def get_active_instances(self) -> int:
        val = self._read_prop("ActiveInstances")
        return int(val) if val is not None else 0

    def get_supported_instances(self) -> int:
        val = self._read_prop("SupportedInstances")
        return int(val) if val is not None else 0

    def get_supported_includes(self) -> List[str]:
        val = self._read_prop("SupportedIncludes")
        return [str(v) for v in val] if val else []

    def get_supported_secondary_channels(self) -> List[str]:
        val = self._read_prop("SupportedSecondaryChannels")
        return [str(v) for v in val] if val else []

    def get_supported_features(self) -> List[str]:
        val = self._read_prop("SupportedFeatures")
        return [str(v) for v in val] if val else []

    def get_supported_capabilities(self) -> Dict[str, Any]:
        val = self._read_prop("SupportedCapabilities")
        if not val:
            return {}
        return {str(k): (int(v) if isinstance(v, (dbus.Byte, dbus.Int16, dbus.UInt16)) else v)
                for k, v in val.items()}

    # -- Registration -------------------------------------------------------

    def register(self, adv: LEAdvertisement, options: Optional[Dict] = None) -> bool:
        """Register *adv* with bluetoothd.  Returns True on success."""
        success: Optional[bool] = None

        def _ok():
            nonlocal success
            success = True

        def _err(error):
            nonlocal success
            print_and_log(f"[-] RegisterAdvertisement failed: {error}", LOG__DEBUG)
            success = False

        self._mgr_iface.RegisterAdvertisement(
            adv.get_path(),
            dbus.Dictionary(options or {}, signature="sv"),
            reply_handler=_ok,
            error_handler=_err,
        )

        import time
        deadline = time.monotonic() + 5.0
        while success is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if success is None:
            print_and_log("[-] RegisterAdvertisement timed out", LOG__DEBUG)
            return False
        return success

    def unregister(self, adv: LEAdvertisement) -> bool:
        """Unregister *adv*.  Returns True on success."""
        success: Optional[bool] = None

        def _ok():
            nonlocal success
            success = True

        def _err(error):
            nonlocal success
            print_and_log(f"[-] UnregisterAdvertisement failed: {error}", LOG__DEBUG)
            success = False

        self._mgr_iface.UnregisterAdvertisement(
            adv.get_path(),
            reply_handler=_ok,
            error_handler=_err,
        )

        import time
        deadline = time.monotonic() + 5.0
        while success is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if success is None:
            print_and_log("[-] UnregisterAdvertisement timed out", LOG__DEBUG)
            return False
        return success
