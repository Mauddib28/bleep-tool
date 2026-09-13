"""
Adapter D-Bus Interface
Provides the system_dbus__bluez_adapter class from the original codebase.
"""

from bleep.core.constants import (
    BT_DEVICE_TYPE_UNKNOWN,
    BT_DEVICE_TYPE_CLASSIC,
    BT_DEVICE_TYPE_LE,
    BT_DEVICE_TYPE_DUAL,
)

import dbus
import dbus.mainloop.glib
from gi.repository import GLib
import shutil
import subprocess
import time
from enum import Enum
from typing import Optional

from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import get_logger
from bleep.core.errors import BleepError
from bleep.dbuslayer.bus import get_bus as _get_bus
from bleep.dbuslayer.manager import (
    system_dbus__bluez_device_manager as _DeviceManager,
)

logger = get_logger(__name__)

# B-2: bound Adapter1.ConnectDevice at the D-Bus layer.
#
# dbus-python defaults blocking calls to DBUS_TIMEOUT_USE_DEFAULT
# (``timeout=-1.0`` in ``dbus/connection.py::call_blocking``), which libdbus
# resolves to 25 s.  ``ConnectDevice`` does not reply until BlueZ finishes
# scanning/paging, so an unreachable target burnt a full 25 s
# ``org.freedesktop.DBus.Error.NoReply`` before the caller regained control
# (measured 2026-09-05: 25 s per unreachable survey target).  Pass an explicit
# timeout instead, mirroring ``obex_opp._DBUS_CALL_TIMEOUT_S``.
_CONNECT_DEVICE_DBUS_TIMEOUT_S = 10.0


class ConnectDeviceOutcome(Enum):
    """Why an ``Adapter1.ConnectDevice`` attempt ended the way it did.

    A timeout means *this transport did not answer*, which is **not** the same
    as the method being unavailable and **not** the same as "device absent".
    A BR/EDR-only device will never answer an LE connect and vice versa, so
    callers must not collapse these into a single failure
    (``AddressType`` "public" is inconclusive for transport — see
    ``docs/device_type_classification.md``).
    """

    CONNECTED = "connected"      # Device1 for the target exists on this adapter
    UNSUPPORTED = "unsupported"  # ConnectDevice missing (non-experimental BlueZ)
    NO_ANSWER = "no-answer"      # NoReply/timeout — transport did not answer
    NO_DEVICE = "no-device"      # call accepted, Device1 never appeared
    ERROR = "error"              # other D-Bus failure (already logged)


class system_dbus__bluez_adapter:
    """Core adapter class for Bluetooth operations."""

    def __init__(self, bluetooth_adapter=ADAPTER_NAME):
        self.adapter_name = bluetooth_adapter
        self.adapter_path = f"/org/bluez/{bluetooth_adapter}"
        self.mainloop = None
        self.timer_id = None
        self.timer__default_time__ms = 5000
        self._device_manager: _DeviceManager | None = None
        # Diagnosability: last swallowed discovery-call failure (Step-3).
        # Populated by _note_discovery_error(); None while no failure seen.
        self._last_discovery_error: Optional[dict] = None
        self._initialize_dbus()

    def _initialize_dbus(self):
        """Initialize D-Bus connection and mainloop."""
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self.system_bus = _get_bus()
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

    def _note_discovery_error(self, method: str, exc: Exception) -> None:
        """Surface (do not swallow) a discovery-call failure.

        Records the failure on ``self._last_discovery_error`` for programmatic
        inspection and logs a WARNING carrying the exact D-Bus error name plus
        the adapter's current ``Discovering`` state. Diagnosability only — the
        caller's control flow and return value are unchanged (Step-3 evidence:
        swallowed StartDiscovery/StopDiscovery/SetDiscoveryFilter errors hide the
        LE<->Classic transition race on affected builds).
        """
        if isinstance(exc, dbus.exceptions.DBusException):
            err_name = exc.get_dbus_name() or "unknown"
            err_msg = exc.get_dbus_message() or ""
        else:
            err_name = exc.__class__.__name__
            err_msg = str(exc)
        try:
            discovering = self.get_discovering()
        except Exception:
            discovering = None
        self._last_discovery_error = {
            "method": method,
            "error_name": err_name,
            "error_message": err_msg,
            "discovering": discovering,
        }
        logger.warning(
            "[!] %s failed on %s: %s%s (Discovering=%s)",
            method,
            self.adapter_path,
            err_name,
            f": {err_msg}" if err_msg else "",
            discovering,
        )

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
        except Exception as e:
            self._note_discovery_error("StartDiscovery", e)
            return False
        try:
            self.timer_id = GLib.timeout_add(timeout_ms, self._discovery_timeout)
            self.mainloop.run()
            return True
        except Exception as e:
            logger.error(f"Timed scan failed: {e}")
            return False

    def _discovery_timeout(self):
        """Handle discovery timeout — always quit the mainloop."""
        try:
            self.adapter_interface.StopDiscovery()
        except Exception as e:
            self._note_discovery_error("StopDiscovery", e)
        try:
            if self.mainloop is not None and self.mainloop.is_running():
                self.mainloop.quit()
        except Exception:
            pass
        try:
            if self.timer_id is not None:
                GLib.source_remove(self.timer_id)
                self.timer_id = None
        except Exception:
            pass
        return False

    def set_discovery_filter(self, discovery_filter):
        """Set discovery filter."""
        try:
            self.adapter_interface.SetDiscoveryFilter(discovery_filter)
            return True
        except Exception as e:
            self._note_discovery_error("SetDiscoveryFilter", e)
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
        """Get list of discovered devices with device type classification.
        
        Device type is determined using evidence-based classification for immediate
        use by commands like classic-scan. Database persistence still uses separate
        classification logic in upsert_device().
        
        RSSI values are merged from multiple sources:
        1. GetManagedObjects() results (primary)
        2. DeviceManager RSSI cache (captured during discovery)
        3. Properties.Get() fallback for connected devices only
        
        Device type mapping:
        - "classic" -> "br/edr" (for compatibility with classic-scan filter)
        - "le", "dual", "unknown" -> unchanged

        Note: For LE discovery that must retain non-connectable beacons, prefer
        ``DeviceManager.take_last_harvest()`` / ``snapshot_discovered_devices()``
        (R1) — BlueZ removes unpaired non-connectable Device1 objects on
        ``StopDiscovery``.
        """
        try:
            from bleep.dbuslayer.manager import build_discovered_device_dict

            managed_objects = self.get_managed_objects()
            if not managed_objects:
                return []

            devices = []
            for path, interfaces in managed_objects.items():
                if DEVICE_INTERFACE not in interfaces:
                    continue

                properties = interfaces[DEVICE_INTERFACE]
                device_address = properties.get("Address", "")
                rssi = properties.get("RSSI") if "RSSI" in properties else None
                
                # Phase 2: Merge RSSI from DeviceManager cache if available
                if rssi is None and self._device_manager is not None:
                    device_address_upper = device_address.upper() if device_address else ""
                    cached_rssi = self._device_manager.get_captured_rssi(device_address_upper)
                    if cached_rssi is not None:
                        rssi = cached_rssi

                devices.append(
                    build_discovered_device_dict(str(path), properties, rssi=rssi)
                )

            # Phase 3: Properties.Get() fallback for connected devices only
            # Only query Properties.Get() for devices with None RSSI that are connected
            for device in devices:
                if device.get("rssi") is None and device.get("connected", False):
                    try:
                        props_iface = dbus.Interface(
                            self.system_bus.get_object(BLUEZ_SERVICE_NAME, device["path"]),
                            DBUS_PROPERTIES
                        )
                        rssi_value = props_iface.Get(DEVICE_INTERFACE, "RSSI")
                        if rssi_value is not None:
                            device["rssi"] = int(rssi_value)
                    except (dbus.exceptions.DBusException, KeyError, AttributeError, ValueError):
                        # RSSI not available even for connected device - keep as None (acceptable)
                        pass

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
    def start_discovery(
        self,
        uuids: list[str] | None = None,
        timeout: int = 60,
        transport: str = "le",
        *,
        duplicate_data: bool | None = None,
        pattern: str | None = None,
        rssi: int | None = None,
        pathloss: int | None = None,
    ):
        """Start discovery via the underlying device manager (one merged filter)."""
        self.create_device_manager().start_discovery(
            service_uuids=uuids,
            timeout=timeout,
            transport=transport,
            duplicate_data=duplicate_data,
            pattern=pattern,
            rssi=rssi,
            pathloss=pathloss,
        )

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
        """Toggle *Powered* property OFF → ON to reset the controller.

        The power-on is retried once and reported distinctly from the
        power-off, because a recovery routine that leaves the adapter dark is
        worse than the fault it was called for.  Survey Run E hit exactly that:
        the off succeeded, the on timed out against a wedged bluetoothd, and
        hci0 was still DOWN after the process exited with nothing in the log
        saying so (docs/todo_tracker.md B.19-B.23).
        """
        try:
            self.adapter_properties.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(False))
        except Exception as e:
            logger.error(f"Adapter power-cycle failed to power off: {e}")
            return False

        time.sleep(off_delay)

        last_error = None
        for attempt in (1, 2):
            try:
                self.adapter_properties.Set(ADAPTER_INTERFACE, "Powered", dbus.Boolean(True))
                logger.debug("Adapter power-cycled successfully")
                return True
            except Exception as e:
                last_error = e
                if attempt == 1:
                    time.sleep(off_delay)

        logger.error(
            f"Adapter power-cycle could not power {self.adapter_name} back on "
            f"({last_error}) — it is LEFT POWERED OFF"
        )
        return False

    def _determine_device_type(self, properties: dict) -> str:
        """
        Determine device type using evidence-based classification.
        
        **Fixed:** Replaced hardcoded UUID patterns with DeviceTypeClassifier.
        Now uses existing BLEEP constants and stateless evidence-based classification.
        
        Args:
            properties: Device properties from BlueZ
            
        Returns:
            Device type: 'unknown', 'classic', 'le', or 'dual'
        """
        try:
            from bleep.analysis.device_type_classifier import DeviceTypeClassifier
            
            # Extract MAC address from properties (required for classifier)
            mac = properties.get("Address", "")
            if not mac:
                return BT_DEVICE_TYPE_UNKNOWN
            
            # Build context from properties — include advertisement data
            # so LEAdvertisingDataCollector and service-data rules receive input
            context = {
                "device_class": properties.get("Class"),
                "address_type": properties.get("AddressType"),
                "uuids": [str(uuid).strip().upper() for uuid in properties.get("UUIDs", [])],
                "connected": properties.get("Connected", False),
                "service_data": dict(properties.get("ServiceData", {})),
                "advertising_data": dict(properties.get("AdvertisingData", {})),
                "manufacturer_data": dict(properties.get("ManufacturerData", {})),
                "appearance": properties.get("Appearance"),
            }
            
            # Use classifier to determine device type
            # Use 'passive' mode since we're just scanning/discovering
            classifier = DeviceTypeClassifier()
            result = classifier.classify_with_mode(
                mac=mac,
                context=context,
                scan_mode="passive",
                use_database_cache=True
            )
            
            return result.device_type
            
        except Exception as e:
            logger.debug(f"Error classifying device type: {e}")
            return BT_DEVICE_TYPE_UNKNOWN

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

    def get_connected_devices(self) -> list:
        """Return MAC addresses of devices currently connected to this adapter.

        Uses ``GetManagedObjects()`` and checks ``Connected`` property on each
        ``Device1`` object whose path is under this adapter's path.
        """
        try:
            bus = dbus.SystemBus()
            obj_mgr = dbus.Interface(
                bus.get_object("org.bluez", "/"),
                "org.freedesktop.DBus.ObjectManager",
            )
            managed = obj_mgr.GetManagedObjects()
        except dbus.exceptions.DBusException:
            return []

        connected = []
        prefix = self.adapter_path + "/"
        for path, ifaces in managed.items():
            if not str(path).startswith(prefix):
                continue
            dev_props = ifaces.get(DEVICE_INTERFACE)
            if dev_props and bool(dev_props.get("Connected", False)):
                addr = str(dev_props.get("Address", ""))
                if addr:
                    connected.append(addr.upper())
        return sorted(connected)

    @staticmethod
    def list_adapters() -> list:
        """Return a list of dicts describing each Bluetooth adapter on the system.

        Each dict contains ``name`` (e.g. ``"hci0"``), ``path``
        (``"/org/bluez/hci0"``), and ``powered`` (``bool``).  Returns an empty
        list when BlueZ is unreachable or no adapters are present.
        """
        try:
            bus = dbus.SystemBus()
            obj_mgr = dbus.Interface(
                bus.get_object("org.bluez", "/"),
                "org.freedesktop.DBus.ObjectManager",
            )
            managed = obj_mgr.GetManagedObjects()
        except dbus.exceptions.DBusException:
            return []

        adapters = []
        for path, ifaces in managed.items():
            if ADAPTER_INTERFACE not in ifaces:
                continue
            props = ifaces[ADAPTER_INTERFACE]
            name = str(path).rsplit("/", 1)[-1]
            powered = bool(props.get("Powered", False))
            adapters.append({"name": name, "path": str(path), "powered": powered})
        adapters.sort(key=lambda a: a["name"])
        return adapters

    # ------------------------------------------------------------------
    # Adapter configuration — D-Bus property accessors
    # ------------------------------------------------------------------

    def get_adapter_info(self) -> dict:
        """Return all adapter properties as a native Python dict.

        Keys match the BlueZ D-Bus property names (Address, Name, Alias,
        Class, Powered, Discoverable, etc.).  Values are converted from
        D-Bus types to native Python types.
        """
        try:
            props = self.adapter_properties.GetAll(ADAPTER_INTERFACE)
            return {str(k): dbus_to_python(v) for k, v in props.items()}
        except Exception as e:
            logger.error(f"Failed to get adapter info: {e}")
            return {}

    # --- Getters (readonly + readwrite) --------------------------------

    def _get_property(self, name: str):
        """Read a single adapter property, returning a native Python value."""
        try:
            return dbus_to_python(
                self.adapter_properties.Get(ADAPTER_INTERFACE, name)
            )
        except Exception as e:
            logger.error(f"Failed to get property '{name}': {e}")
            return None

    def get_alias(self) -> Optional[str]:
        return self._get_property("Alias")

    def get_name(self) -> Optional[str]:
        return self._get_property("Name")

    def get_address(self) -> Optional[str]:
        return self._get_property("Address")

    def get_address_type(self) -> Optional[str]:
        return self._get_property("AddressType")

    def get_class(self) -> Optional[int]:
        return self._get_property("Class")

    def get_powered(self) -> Optional[bool]:
        return self._get_property("Powered")

    def get_discoverable(self) -> Optional[bool]:
        return self._get_property("Discoverable")

    def get_pairable(self) -> Optional[bool]:
        return self._get_property("Pairable")

    def get_connectable(self) -> Optional[bool]:
        return self._get_property("Connectable")

    def get_discoverable_timeout(self) -> Optional[int]:
        return self._get_property("DiscoverableTimeout")

    def get_pairable_timeout(self) -> Optional[int]:
        return self._get_property("PairableTimeout")

    def get_discovering(self) -> Optional[bool]:
        return self._get_property("Discovering")

    def get_uuids(self) -> Optional[list]:
        return self._get_property("UUIDs")

    def get_modalias(self) -> Optional[str]:
        return self._get_property("Modalias")

    def get_roles(self) -> Optional[list]:
        return self._get_property("Roles")

    # --- Setters (D-Bus writable properties only) ----------------------

    def _set_property(self, name: str, value, dbus_type_fn) -> bool:
        """Write a single adapter property.  Returns True on success."""
        try:
            self.adapter_properties.Set(
                ADAPTER_INTERFACE, name, dbus_type_fn(value)
            )
            logger.debug(f"Adapter property '{name}' set to {value}")
            return True
        except dbus.exceptions.DBusException as e:
            logger.error(f"Failed to set property '{name}': {e}")
            return False

    def set_alias(self, alias: str) -> bool:
        """Set the adapter's friendly name.  Pass ``""`` to reset to system name."""
        return self._set_property("Alias", alias, dbus.String)

    def set_powered(self, enabled: bool) -> bool:
        return self._set_property("Powered", enabled, dbus.Boolean)

    def set_discoverable(self, enabled: bool) -> bool:
        return self._set_property("Discoverable", enabled, dbus.Boolean)

    def set_pairable(self, enabled: bool) -> bool:
        return self._set_property("Pairable", enabled, dbus.Boolean)

    def set_connectable(self, enabled: bool) -> bool:
        """Setting to False also forces Discoverable to False."""
        return self._set_property("Connectable", enabled, dbus.Boolean)

    def set_discoverable_timeout(self, seconds: int) -> bool:
        """0 disables the timeout (stay discoverable forever)."""
        return self._set_property("DiscoverableTimeout", seconds, dbus.UInt32)

    def set_pairable_timeout(self, seconds: int) -> bool:
        """0 disables the timeout (stay pairable forever)."""
        return self._set_property("PairableTimeout", seconds, dbus.UInt32)

    # ------------------------------------------------------------------
    # Adapter configuration — bluetoothctl mgmt (kernel management socket)
    #
    # These operations are *not* reachable through D-Bus Properties and
    # require the bluetoothctl ``mgmt`` submenu, which talks directly to
    # the kernel via the management socket.  CAP_NET_ADMIN or root is
    # required for most of these.
    # ------------------------------------------------------------------

    def _run_bluetoothctl_mgmt(self, *commands: str) -> tuple[bool, str]:
        """Execute one or more ``bluetoothctl`` commands via stdin.

        Multiple commands are fed line-by-line to a single bluetoothctl
        session so that stateful commands (e.g. ``mgmt.select``) persist
        across the sequence.

        Returns (success, combined_output).  Follows the subprocess pattern
        already established in ``bleep.core.error_handling``.
        """
        btctl = shutil.which("bluetoothctl")
        if not btctl:
            logger.error("bluetoothctl not found in PATH")
            return False, "bluetoothctl not found"

        stdin_text = "\n".join(commands) + "\n"
        logger.debug(f"bluetoothctl stdin: {commands}")
        try:
            result = subprocess.run(
                [btctl],
                input=stdin_text,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = (result.stdout + result.stderr).strip()
            success = result.returncode == 0
            if not success:
                logger.warning(f"bluetoothctl command failed: {output}")
            return success, output
        except subprocess.TimeoutExpired:
            logger.error(f"bluetoothctl command timed out: {commands}")
            return False, "command timed out"
        except Exception as e:
            logger.error(f"bluetoothctl subprocess error: {e}")
            return False, str(e)

    def _mgmt_index(self) -> str:
        """Return the numeric HCI index (e.g. ``"0"`` for ``hci0``)."""
        return self.adapter_name.replace("hci", "")

    def _mgmt_cmd(self, *cmd_parts: str) -> tuple[bool, str]:
        """Run a mgmt command, prepending ``mgmt.select`` for the adapter index."""
        select = f"mgmt.select {self._mgmt_index()}"
        return self._run_bluetoothctl_mgmt(select, " ".join(cmd_parts))

    def set_class(self, major: int, minor: int) -> bool:
        """Set the device class via the kernel management socket.

        Parameters
        ----------
        major : int
            Major device class (e.g. 1=Computer, 2=Phone, 4=Audio/Video).
        minor : int
            Minor device class within the major category.

        Requires CAP_NET_ADMIN or root.
        """
        ok, out = self._mgmt_cmd("mgmt.class", str(major), str(minor))
        if ok:
            logger.info(f"Device class set to major={major} minor={minor}")
        return ok

    def set_local_name(
        self, name: str, short_name: Optional[str] = None
    ) -> bool:
        """Set a temporary alias via the kernel management socket.

        Sends ``MGMT_OP_SET_LOCAL_NAME`` to the kernel.  The BlueZ daemon
        receives this via ``local_name_changed_callback`` and updates
        ``current_alias`` — a **temporary** alias that lasts only for the
        lifetime of the ``bluetoothd`` process.  The ``Name`` property
        (system hostname) is unchanged.  For a **persistent** name change,
        use :meth:`set_alias` instead.

        Requires CAP_NET_ADMIN or root.
        """
        parts = ["mgmt.name", name]
        if short_name:
            parts.append(short_name)
        ok, _ = self._mgmt_cmd(*parts)
        if ok:
            logger.info(f"Local name set to '{name}'")
        return ok

    def set_ssp(self, enabled: bool) -> bool:
        """Toggle Secure Simple Pairing via management socket."""
        ok, _ = self._mgmt_cmd("mgmt.ssp", "on" if enabled else "off")
        return ok

    def set_secure_connections(self, mode: str) -> bool:
        """Toggle Secure Connections.  ``mode`` must be 'on', 'off', or 'only'."""
        if mode not in ("on", "off", "only"):
            logger.error(f"Invalid SC mode: {mode!r} (must be on/off/only)")
            return False
        ok, _ = self._mgmt_cmd("mgmt.sc", mode)
        return ok

    def set_le(self, enabled: bool) -> bool:
        """Toggle LE transport support via management socket."""
        ok, _ = self._mgmt_cmd("mgmt.le", "on" if enabled else "off")
        return ok

    def set_bredr(self, enabled: bool) -> bool:
        """Toggle BR/EDR transport support via management socket."""
        ok, _ = self._mgmt_cmd("mgmt.bredr", "on" if enabled else "off")
        return ok

    def set_privacy(self, enabled: bool) -> bool:
        """Toggle LE privacy via management socket."""
        ok, _ = self._mgmt_cmd("mgmt.privacy", "on" if enabled else "off")
        return ok

    def set_fast_connectable(self, enabled: bool) -> bool:
        """Toggle fast connectable mode via management socket."""
        ok, _ = self._mgmt_cmd("mgmt.fast-conn", "on" if enabled else "off")
        return ok

    def set_link_security(self, enabled: bool) -> bool:
        """Toggle link-level security via management socket."""
        ok, _ = self._mgmt_cmd("mgmt.linksec", "on" if enabled else "off")
        return ok

    def set_wideband_speech(self, enabled: bool) -> bool:
        """Toggle wideband speech (HFP WBS) via management socket."""
        ok, _ = self._mgmt_cmd("mgmt.wbs", "on" if enabled else "off")
        return ok

    # -- Admin Policy (BZ-13/14) -------------------------------------------

    def set_service_allow_list(self, uuids: list[str]) -> bool:
        """Set the service allow list via ``AdminPolicySet1`` (BZ-13a).

        When set, bluetoothd blocks connections to services not in *uuids*.
        Pass an empty list to clear the filter.  Requires BlueZ
        ``--experimental`` flag.
        """
        try:
            policy_obj = self.system_bus.get_object(
                BLUEZ_SERVICE_NAME, self.adapter_path,
            )
            policy_iface = dbus.Interface(policy_obj, ADMIN_POLICY_SET_INTERFACE)
            policy_iface.SetServiceAllowList(
                dbus.Array(uuids, signature="s"),
            )
            logger.info(f"Service allow list set: {uuids}")
            return True
        except dbus.exceptions.DBusException as exc:
            logger.warning(f"SetServiceAllowList failed: {exc}")
            return False

    def get_service_allow_list(self) -> list[str] | None:
        """Read current service allow list from ``AdminPolicyStatus1`` (BZ-14).

        Returns ``None`` if the interface is unavailable (BlueZ built without
        ``--experimental``).
        """
        try:
            val = self.adapter_properties.Get(
                ADMIN_POLICY_STATUS_INTERFACE, "ServiceAllowList",
            )
            return [str(u) for u in val]
        except dbus.exceptions.DBusException:
            return None

    def connect_device_ex(
        self,
        address: str,
        address_type: str | None = None,
        timeout: float = 15.0,
        dbus_timeout: float | None = None,
    ) -> "ConnectDeviceOutcome":
        """Connect without General Discovery via Adapter1.ConnectDevice.

        Returns a :class:`ConnectDeviceOutcome` so callers can tell
        "unsupported method" from "this transport did not answer" — the two
        used to collapse into a single ``False``/raise, which made a BR/EDR-only
        device indistinguishable from a BlueZ without the experimental
        interface.

        *timeout* bounds the wait for the ``Device1`` object to appear.
        *dbus_timeout* bounds the blocking ``ConnectDevice`` call itself
        (defaults to ``_CONNECT_DEVICE_DBUS_TIMEOUT_S``); without it libdbus
        applies its 25 s default.
        """
        props: dict = {"Address": address.strip().upper()}
        if address_type:
            props["AddressType"] = str(address_type).lower()
        call_timeout = (
            _CONNECT_DEVICE_DBUS_TIMEOUT_S if dbus_timeout is None
            else float(dbus_timeout)
        )
        try:
            self.adapter_interface.ConnectDevice(props, timeout=call_timeout)
        except dbus.exceptions.DBusException as exc:
            name = exc.get_dbus_name() or ""
            blob = " ".join(
                p for p in (name, exc.get_dbus_message() or "", str(exc)) if p
            )
            if any(
                token in blob
                for token in (
                    "UnknownMethod",
                    "NotSupported",
                    "NotAvailable",
                    "NotPermitted",
                )
            ):
                logger.debug(
                    "ConnectDevice unavailable on %s: %s",
                    self.adapter_name,
                    blob,
                )
                return ConnectDeviceOutcome.UNSUPPORTED
            # NoReply/Timeout: BlueZ never finished scanning/paging within the
            # call budget.  Not fatal and not "unsupported" — the target simply
            # did not answer on this transport, so do not raise and do not let
            # the caller trigger an unsupported-method fallback.
            if "NoReply" in blob or "Timeout" in blob or "TimedOut" in blob:
                logger.debug(
                    "ConnectDevice no answer for %s on %s (%.1fs budget): %s",
                    address.strip().upper(),
                    self.adapter_name,
                    call_timeout,
                    blob,
                )
                return ConnectDeviceOutcome.NO_ANSWER
            # AlreadyExists / InProgress: Device1 may still appear.
            if "AlreadyExists" not in blob and "InProgress" not in blob:
                logger.debug(
                    "ConnectDevice error for %s on %s: %s",
                    address.strip().upper(),
                    self.adapter_name,
                    blob,
                )
                raise
        deadline = time.monotonic() + timeout
        prefix = f"/org/bluez/{self.adapter_name}/"
        target = address.strip().upper()
        while time.monotonic() < deadline:
            managed = self.get_managed_objects() or {}
            for path, ifaces in managed.items():
                if not str(path).startswith(prefix):
                    continue
                dev = ifaces.get(DEVICE_INTERFACE) or {}
                if str(dev.get("Address", "")).upper() == target:
                    return ConnectDeviceOutcome.CONNECTED
            time.sleep(0.2)
        return ConnectDeviceOutcome.NO_DEVICE

    def connect_device(
        self,
        address: str,
        address_type: str | None = None,
        timeout: float = 15.0,
        dbus_timeout: float | None = None,
    ) -> bool:
        """Boolean wrapper over :meth:`connect_device_ex` (legacy callers).

        True only when a ``Device1`` for *address* exists on this adapter.
        Callers that must distinguish *unsupported* from *no answer* should use
        :meth:`connect_device_ex` instead.
        """
        return (
            self.connect_device_ex(
                address,
                address_type=address_type,
                timeout=timeout,
                dbus_timeout=dbus_timeout,
            )
            is ConnectDeviceOutcome.CONNECTED
        )


# Re-export the class
__all__ = ["system_dbus__bluez_adapter"]
