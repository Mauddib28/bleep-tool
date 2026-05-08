"""Advertisement Monitor D-Bus layer (BZ-11/12).

Implements the client side of the BlueZ ``AdvertisementMonitor1`` and
``AdvertisementMonitorManager1`` experimental interfaces.  This enables
kernel-offloaded pattern-based passive scanning with RSSI thresholds and
device found/lost callbacks — without requiring an active ``StartDiscovery``
session.

Architecture
~~~~~~~~~~~~
* **AdvMonitor** — per-monitor ``dbus.service.Object`` exposing properties
  (Type, RSSI thresholds, Patterns) and receiving ``Activate``, ``Release``,
  ``DeviceFound``, ``DeviceLost`` callbacks from bluetoothd.
* **AdvMonitorApp** — application root implementing ``ObjectManager``.
  Manages child monitors and registers with ``AdvertisementMonitorManager1``.
* **AdvMonitorManager** — thin wrapper that discovers the manager interface
  on the adapter and exposes ``register``/``unregister``/capability queries.

Reference: ``workDir/BlueZDocs/org.bluez.AdvertisementMonitor.rst``,
``workDir/BlueZDocs/org.bluez.AdvertisementMonitorManager.rst``,
``workDir/BlueZScripts/example-adv-monitor``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import dbus
import dbus.service

from bleep.bt_ref.constants import (
    ADV_MONITOR_APP_BASE_PATH,
    ADV_MONITOR_INTERFACE,
    ADV_MONITOR_MANAGER_INTERFACE,
    BLUEZ_SERVICE_NAME,
    DBUS_OM_IFACE,
    DBUS_PROPERTIES,
)
from bleep.core.log import print_and_log, LOG__DEBUG

__all__ = [
    "AdvMonitor",
    "AdvMonitorApp",
    "AdvMonitorManager",
    "MonitorPattern",
    "RSSIConfig",
]


# -- helpers ----------------------------------------------------------------

# Common AD type constants for convenience.
AD_TYPE_FLAGS = 0x01
AD_TYPE_UUID16_INCOMPLETE = 0x02
AD_TYPE_UUID16_COMPLETE = 0x03
AD_TYPE_UUID128_INCOMPLETE = 0x06
AD_TYPE_UUID128_COMPLETE = 0x07
AD_TYPE_SHORT_NAME = 0x08
AD_TYPE_COMPLETE_NAME = 0x09
AD_TYPE_TX_POWER = 0x0A
AD_TYPE_APPEARANCE = 0x19
AD_TYPE_MANUFACTURER = 0xFF


@dataclass
class MonitorPattern:
    """A single advertisement monitor pattern.

    Parameters
    ----------
    start_pos : int
        Byte offset within the AD field where matching starts.
    ad_type : int
        BLE AD data type (e.g. 0x09 for Complete Local Name).
    content : bytes
        Pattern bytes to match (max 31 bytes).
    """
    start_pos: int
    ad_type: int
    content: bytes

    def to_dbus(self) -> dbus.Struct:
        return dbus.Struct(
            (
                dbus.Byte(self.start_pos),
                dbus.Byte(self.ad_type),
                dbus.Array([dbus.Byte(b) for b in self.content], signature="y"),
            ),
            signature="yyay",
        )


@dataclass
class RSSIConfig:
    """RSSI threshold and timeout configuration for a monitor.

    All thresholds are in dBm (-127..20).  A value of 127 means *unset*.
    Timeouts are in seconds (1..300).  A value of 0 means *unset*.
    """
    high_threshold: int = 127
    high_timeout: int = 0
    low_threshold: int = 127
    low_timeout: int = 0
    sampling_period: int = 0


@dataclass
class MonitorCallbacks:
    """Callback set for advertisement monitor events."""
    on_activate: Optional[Callable[[], None]] = None
    on_release: Optional[Callable[[], None]] = None
    on_device_found: Optional[Callable[[str], None]] = None
    on_device_lost: Optional[Callable[[str], None]] = None


def _device_path_to_mac(path: str) -> str:
    """Extract ``XX:XX:XX:XX:XX:XX`` from a BlueZ device object path."""
    if "/dev_" not in path:
        return path
    mac_part = path.rsplit("/dev_", 1)[-1]
    return mac_part.replace("_", ":").upper()


# -- D-Bus objects ----------------------------------------------------------

class AdvMonitor(dbus.service.Object):
    """A single advertisement monitor registered with BlueZ.

    bluetoothd invokes ``Activate``, ``Release``, ``DeviceFound``,
    ``DeviceLost`` as D-Bus method calls on this object.
    """

    def __init__(
        self,
        bus: dbus.SystemBus,
        app_path: str,
        monitor_id: int,
        monitor_type: str,
        rssi: RSSIConfig,
        patterns: List[MonitorPattern],
        callbacks: Optional[MonitorCallbacks] = None,
    ):
        self.path = f"{app_path}/monitor{monitor_id}"
        self.bus = bus
        self.monitor_id = monitor_id
        self.monitor_type = monitor_type
        self.rssi = rssi
        self.patterns = patterns
        self.callbacks = callbacks or MonitorCallbacks()
        self.active = False

        super().__init__(bus, self.path)

    def get_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.path)

    def get_properties(self) -> Dict[str, Dict[str, Any]]:
        props: Dict[str, Any] = {
            "Type": dbus.String(self.monitor_type),
            "RSSIHighThreshold": dbus.Int16(self.rssi.high_threshold),
            "RSSIHighTimeout": dbus.UInt16(self.rssi.high_timeout),
            "RSSILowThreshold": dbus.Int16(self.rssi.low_threshold),
            "RSSILowTimeout": dbus.UInt16(self.rssi.low_timeout),
            "Patterns": dbus.Array(
                [p.to_dbus() for p in self.patterns], signature="(yyay)"
            ),
        }
        if self.rssi.sampling_period:
            props["RSSISamplingPeriod"] = dbus.UInt16(self.rssi.sampling_period)
        return {ADV_MONITOR_INTERFACE: props}

    def remove_monitor(self) -> None:
        self.remove_from_connection()

    # -- Methods invoked BY bluetoothd --------------------------------------

    @dbus.service.method(DBUS_PROPERTIES, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface: str) -> Dict[str, Any]:
        if interface != ADV_MONITOR_INTERFACE:
            return {}
        return self.get_properties()[ADV_MONITOR_INTERFACE]

    @dbus.service.method(ADV_MONITOR_INTERFACE, in_signature="", out_signature="")
    def Activate(self) -> None:
        self.active = True
        print_and_log(f"[+] Monitor {self.path} activated", LOG__DEBUG)
        if self.callbacks.on_activate:
            self.callbacks.on_activate()

    @dbus.service.method(ADV_MONITOR_INTERFACE, in_signature="", out_signature="")
    def Release(self) -> None:
        self.active = False
        print_and_log(f"[-] Monitor {self.path} released", LOG__DEBUG)
        if self.callbacks.on_release:
            self.callbacks.on_release()

    @dbus.service.method(ADV_MONITOR_INTERFACE, in_signature="o", out_signature="")
    def DeviceFound(self, device: str) -> None:
        mac = _device_path_to_mac(device)
        print_and_log(f"[+] Monitor {self.monitor_id}: device found {mac}", LOG__DEBUG)
        if self.callbacks.on_device_found:
            self.callbacks.on_device_found(device)

    @dbus.service.method(ADV_MONITOR_INTERFACE, in_signature="o", out_signature="")
    def DeviceLost(self, device: str) -> None:
        mac = _device_path_to_mac(device)
        print_and_log(f"[-] Monitor {self.monitor_id}: device lost {mac}", LOG__DEBUG)
        if self.callbacks.on_device_lost:
            self.callbacks.on_device_lost(device)


class AdvMonitorApp(dbus.service.Object):
    """Application root that manages a set of :class:`AdvMonitor` children.

    Implements ``org.freedesktop.DBus.ObjectManager`` so bluetoothd can
    discover child monitor objects.
    """

    def __init__(self, bus: dbus.SystemBus, app_id: int = 0):
        self.bus = bus
        self.app_path = f"{ADV_MONITOR_APP_BASE_PATH}{app_id}"
        self._monitors: Dict[int, AdvMonitor] = {}
        self._next_id = 0

        super().__init__(bus, self.app_path)

    def get_app_path(self) -> dbus.ObjectPath:
        return dbus.ObjectPath(self.app_path)

    # -- Monitor lifecycle --------------------------------------------------

    def add_monitor(
        self,
        monitor_type: str = "or_patterns",
        rssi: Optional[RSSIConfig] = None,
        patterns: Optional[List[MonitorPattern]] = None,
        callbacks: Optional[MonitorCallbacks] = None,
    ) -> int:
        """Create a child monitor and emit ``InterfacesAdded``.

        Returns the monitor id (int).
        """
        mid = self._next_id
        self._next_id += 1

        mon = AdvMonitor(
            self.bus,
            self.app_path,
            mid,
            monitor_type,
            rssi or RSSIConfig(),
            patterns or [],
            callbacks,
        )
        self._monitors[mid] = mon
        self.InterfacesAdded(mon.get_path(), mon.get_properties())
        print_and_log(f"[+] Added monitor {mid} at {mon.path}", LOG__DEBUG)
        return mid

    def remove_monitor(self, monitor_id: int) -> bool:
        mon = self._monitors.pop(monitor_id, None)
        if mon is None:
            return False
        self.InterfacesRemoved(mon.get_path(), list(mon.get_properties().keys()))
        mon.remove_monitor()
        print_and_log(f"[-] Removed monitor {monitor_id}", LOG__DEBUG)
        return True

    def remove_all(self) -> None:
        for mid in list(self._monitors):
            self.remove_monitor(mid)

    # -- ObjectManager interface --------------------------------------------

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        objects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for mon in self._monitors.values():
            objects[mon.get_path()] = mon.get_properties()
        return objects

    @dbus.service.signal(DBUS_OM_IFACE, signature="oa{sa{sv}}")
    def InterfacesAdded(self, object_path, interfaces_and_properties):
        pass  # signal emission handled by dbus-python

    @dbus.service.signal(DBUS_OM_IFACE, signature="oas")
    def InterfacesRemoved(self, object_path, interfaces):
        pass  # signal emission handled by dbus-python


class AdvMonitorManager:
    """Wrapper around ``AdvertisementMonitorManager1`` on the adapter.

    Discovers the manager, reads capabilities, and registers/unregisters
    :class:`AdvMonitorApp` instances.
    """

    def __init__(self, bus: dbus.SystemBus, adapter_path: str = "/org/bluez/hci0"):
        self.bus = bus
        self.adapter_path = adapter_path
        self._mgr_iface = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
            ADV_MONITOR_MANAGER_INTERFACE,
        )
        self._props_iface = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
            DBUS_PROPERTIES,
        )

    # -- Capabilities -------------------------------------------------------

    def get_supported_types(self) -> List[str]:
        try:
            raw = self._props_iface.Get(
                ADV_MONITOR_MANAGER_INTERFACE, "SupportedMonitorTypes"
            )
            return [str(t) for t in raw]
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[WARN] Cannot read SupportedMonitorTypes: {e}", LOG__DEBUG)
            return []

    def get_supported_features(self) -> List[str]:
        try:
            raw = self._props_iface.Get(
                ADV_MONITOR_MANAGER_INTERFACE, "SupportedFeatures"
            )
            return [str(f) for f in raw]
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[WARN] Cannot read SupportedFeatures: {e}", LOG__DEBUG)
            return []

    # -- Registration -------------------------------------------------------

    def register(self, app: AdvMonitorApp) -> bool:
        """Register *app* with bluetoothd.  Returns True on success."""
        success: Optional[bool] = None

        def _ok():
            nonlocal success
            success = True

        def _err(error):
            nonlocal success
            print_and_log(
                f"[-] RegisterMonitor failed: {error}", LOG__DEBUG
            )
            success = False

        self._mgr_iface.RegisterMonitor(
            app.get_app_path(),
            reply_handler=_ok,
            error_handler=_err,
        )
        # Spin until reply (runs on GLib main loop)
        import time
        deadline = time.monotonic() + 5.0
        while success is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if success is None:
            print_and_log("[-] RegisterMonitor timed out", LOG__DEBUG)
            return False
        return success

    def unregister(self, app: AdvMonitorApp) -> bool:
        """Unregister *app*.  Returns True on success."""
        success: Optional[bool] = None

        def _ok():
            nonlocal success
            success = True

        def _err(error):
            nonlocal success
            print_and_log(
                f"[-] UnregisterMonitor failed: {error}", LOG__DEBUG
            )
            success = False

        self._mgr_iface.UnregisterMonitor(
            app.get_app_path(),
            reply_handler=_ok,
            error_handler=_err,
        )
        import time
        deadline = time.monotonic() + 5.0
        while success is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if success is None:
            print_and_log("[-] UnregisterMonitor timed out", LOG__DEBUG)
            return False
        return success
