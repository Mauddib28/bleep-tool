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
from typing import Optional

from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import get_logger
from bleep.core.errors import BleepError
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
        """
        try:
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
                # Normalize MAC address to lowercase for cache lookup (cache stores lowercase)
                if rssi is None and self._device_manager is not None:
                    device_address_lower = device_address.lower() if device_address else ""
                    cached_rssi = self._device_manager.get_captured_rssi(device_address_lower)
                    if cached_rssi is not None:
                        rssi = cached_rssi
                
                # Determine device type using existing classification method
                device_type = self._determine_device_type(properties)
                # Map "classic" to "br/edr" for compatibility with classic-scan filter
                type_display = "br/edr" if device_type == BT_DEVICE_TYPE_CLASSIC else device_type
                
                devices.append(
                    {
                        "path": path,
                        "address": device_address,
                        "name": properties.get("Name", ""),
                        "rssi": rssi,
                        "alias": properties.get("Alias", ""),
                        # Store raw properties for later classification (after device is inserted)
                        "address_type": properties.get("AddressType"),
                        "device_class": properties.get("Class"),
                        "uuids": [str(uuid) for uuid in properties.get("UUIDs", [])] if properties.get("UUIDs") else [],
                        "connected": properties.get("Connected", False),
                        "type": type_display,  # Device type for filtering (e.g., classic-scan)
                    }
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
            
            # Build context from properties
            context = {
                "device_class": properties.get("Class"),
                "address_type": properties.get("AddressType"),
                "uuids": [str(uuid) for uuid in properties.get("UUIDs", [])],
                "connected": properties.get("Connected", False),
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


# Re-export the class
__all__ = ["system_dbus__bluez_adapter"]
