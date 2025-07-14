"""Low-Energy Device abstractions for the BlueZ stack.

Phase-4 extraction: first functional slice of the original monolith's BLE device
handling code.  Only common happy-path operations are implemented for now –
connections, basic property access, and service-resolution detection.  Advanced
characteristic helpers and notification routing will arrive in Phase-5.
"""

#!/usr/bin/python3

from __future__ import annotations

import re
import time
from typing import Dict, Any, Optional, List

import dbus
from gi.repository import GLib

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    BLUEZ_NAMESPACE,
    ADAPTER_NAME,
    DEVICE_INTERFACE,
    DBUS_PROPERTIES,
    GATT_SERVICE_INTERFACE,
    DBUS_OM_IFACE,
    RESULT_ERR_UNKNOWN_OBJECT,
)
from bleep.bt_ref.utils import dbus_to_python, device_address_to_path, handle_int_to_hex, handle_hex_to_int
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__USER
from bleep.core import errors
from bleep.core.errors import map_dbus_error, BLEEPError
from bleep.dbuslayer.service import Service
from bleep.dbuslayer.characteristic import Characteristic
from bleep.dbuslayer.descriptor import Descriptor
from bleep.dbuslayer.signals import system_dbus__bluez_signals as _SignalsRegistry
from bleep.dbuslayer.media import MediaControl, MediaEndpoint, MediaTransport, MediaPlayer, find_media_devices
from bleep.ble_ops.uuid_utils import identify_uuid

__all__ = [
    "system_dbus__bluez_device__low_energy",
]

# Create a singleton signals manager
_signals_manager = _SignalsRegistry()


class system_dbus__bluez_device__low_energy:  # noqa: N802 – preserve legacy name
    """Wrapper around a single LE device exposed by BlueZ.

    The class intentionally mirrors the public surface of the historic
    `bluetooth__le__device` so existing higher-level modules continue to work.
    """

    def __init__(self, mac_address: str, adapter_name: str = ADAPTER_NAME):
        self.mac_address = mac_address.lower()
        self.adapter_name = adapter_name

        self._bus = dbus.SystemBus()
        self._object_manager = dbus.Interface(
            self._bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE
        )

        self._device_path: str = device_address_to_path(
            self.mac_address.upper(), f"{BLUEZ_NAMESPACE}{adapter_name}"
        )
        try:
            self._device_object = self._bus.get_object(BLUEZ_SERVICE_NAME, self._device_path)
            self._device_iface = dbus.Interface(self._device_object, DEVICE_INTERFACE)
            self._props_iface = dbus.Interface(self._device_object, DBUS_PROPERTIES)
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)

        # Signal bookkeeping
        self._properties_signal = None
        self._connect_retry_attempt = 0
        self._services: list[Service] = []
        
        # Reconnection monitor - will be set by connect_with_monitoring
        self._reconnection_monitor = None
        
        # Landmine and permission mapping (enhanced from golden template)
        self._landmine_map = {}  # Category -> {uuid: details}
        self._security_map = {}  # Requirement -> {uuid: details}
        
        # Legacy compatibility for old mappings
        self.ble_device__mapping = {}  # Handle -> UUID
        self.ble_device__mine_mapping = {}
        self.ble_device__permission_mapping = {}

        # Device type detection cache (updated after service resolution)
        self.device_type_flags: Dict[str, bool] = {
            "is_gatt_server": False,
            "is_media_device": False,
            "is_mesh_device": False,
            "is_classic_device": False,
            "is_le_device": True,
        }
        
        # Flag to prevent recursion between services_resolved and check_device_type
        self._in_device_type_check = False

        # Register with global signals manager
        _signals_manager.register_device(self)

        # ------------------------------------------------------------------
        # Legacy-compat: expose *device_address* attribute used heavily in old
        # helper code and current test-suite.  Implemented as a read-write
        # property that simply proxies to *mac_address* to avoid divergence.
        # ------------------------------------------------------------------

    # ---------------------------------------------------------------------
    # Pairing & Trust Management
    # ---------------------------------------------------------------------
    def Pair(self, timeout: int = 30):
        """Pair with the device.
        
        Parameters
        ----------
        timeout
            Seconds to wait for pairing to complete before timing out.
        
        Returns
        -------
        bool
            True if pairing was successful, False otherwise.
        
        Raises
        ------
        Exception
            If pairing fails due to a non-timeout error.
        """
        print_and_log(f"[*] Attempting to pair with {self.mac_address}", LOG__USER)
        try:
            self._device_iface.Pair(timeout=dbus.UInt32(timeout))
            print_and_log(f"[+] Successfully paired with {self.mac_address}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Pairing failed: {str(e)}", LOG__GENERAL)
            raise map_dbus_error(e)

    def set_trusted(self, trusted: bool = True):
        """Set the device as trusted or untrusted.
        
        Parameters
        ----------
        trusted
            Whether to trust (True) or untrust (False) the device.
            
        Returns
        -------
        bool
            True if the operation was successful, False otherwise.
        """
        try:
            self._props_iface.Set(DEVICE_INTERFACE, "Trusted", dbus.Boolean(trusted))
            trust_status = "trusted" if trusted else "untrusted"
            print_and_log(f"[*] Device {self.mac_address} set as {trust_status}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Setting trust failed: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)

    # ---------------------------------------------------------------------
    # Connection helpers
    # ---------------------------------------------------------------------
    def connect(self, retry: int = 3, *, wait_timeout: float = 10.0):
        """Synchronous connect with limited retry loop.

        Parameters
        ----------
        retry
            How many times to attempt the connection before giving up.
        wait_timeout
            Seconds to wait for *Connected* property to become *True* after
            each *Connect()* call.  Some BLE stacks need >5 s when bonding.
        """
        print_and_log(f"[*] Attempting connection to {self.mac_address}", LOG__USER)
        self._connect_retry_attempt = 0
        self._attach_property_signal()

        while self._connect_retry_attempt < retry:
            try:
                # ----------------------------------------------------------
                # BlueZ sometimes keeps an old lingering device object when a
                # previous connection aborted mid-handshake.  Explicitly call
                # *Disconnect()* first – it is a no-op if the device is not
                # connected but guarantees a clean slate for the next attempt.
                # ----------------------------------------------------------
                try:
                    self._device_iface.Disconnect()
                except dbus.exceptions.DBusException:
                    # Ignore – the device was simply not connected.
                    pass

                self._connect_retry_attempt += 1
                print_and_log(
                    f"[*] Connect attempt {self._connect_retry_attempt}/{retry}",
                    LOG__DEBUG,
                )

                self._device_iface.Connect()

                # Wait until Connected == True (polling every 100 ms)
                waited = 0.0
                while waited < wait_timeout:
                    if self.is_connected():
                        break
                    time.sleep(0.1)
                    waited += 0.1

                if not self.is_connected():
                    raise errors.ConnectionError(self.mac_address, "timeout")

                print_and_log(f"[+] Connected to {self.mac_address}", LOG__GENERAL)
                return True

            except dbus.exceptions.DBusException as e:
                mapped = map_dbus_error(e)
                print_and_log(
                    f"[-] Connection attempt {self._connect_retry_attempt} failed: {mapped}",
                    LOG__DEBUG,
                )

                # Software-abort is transient on many controllers – treat like
                # *InProgress* and retry after a brief exponential back-off.
                transient = (
                    isinstance(mapped, errors.OperationInProgressError)
                    or "Software caused connection abort" in str(e)
                )

                if transient and self._connect_retry_attempt < retry:
                    # Exponential back-off up to 1.6 s (0.2, 0.4, 0.8, 1.6 …)
                    delay = min(0.2 * (2 ** (self._connect_retry_attempt - 1)), 1.6)
                    time.sleep(delay)
                    continue

                # Propagate the *last* failure when retries exhausted
                if self._connect_retry_attempt >= retry:
                    raise mapped

        return False

    def disconnect(self):
        """Disconnect from the device."""
        print_and_log(f"[*] Disconnecting from {self.mac_address}", LOG__USER)
        try:
            # Stop reconnection monitoring if active
            if hasattr(self, "_reconnection_monitor") and self._reconnection_monitor:
                self._reconnection_monitor.stop_monitoring()
                
            self._device_iface.Disconnect()
            print_and_log(f"[+] Disconnected from {self.mac_address}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Disconnect failed: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)

    # ------------------------------------------------------------------
    # Properties & state helpers
    # ------------------------------------------------------------------
    def is_connected(self) -> bool:
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "Connected"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
        
    def is_paired(self) -> bool:
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "Paired"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
        
    def is_trusted(self) -> bool:
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "Trusted"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
        
    def is_bonded(self) -> bool:
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "Bonded"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
        
    def is_blocked(self) -> bool:
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "Blocked"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
        
    def is_services_resolved(self) -> bool:
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "ServicesResolved"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
        
    def is_wake_allowed(self) -> bool:
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "WakeAllowed"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
        
    def is_legacy_pairing(self) -> bool:
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "LegacyPairing"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
        
    def is_cable_pairing(self) -> bool:
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "CablePairing"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)
        
    def get_adapter_path(self) -> str:
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "Adapter"))
        except dbus.exceptions.DBusException as e:
            raise map_dbus_error(e)

    def get_alias(self) -> Optional[str]:
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "Alias"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the Alias
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_name(self) -> Optional[str]:
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "Name"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the Alias
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_address(self) -> str:
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "Address"))
        except dbus.exceptions.DBusException as e:
            return None

    def get_address_type(self) -> Optional[str]:
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "AddressType"))
        except dbus.exceptions.DBusException as e:
            return None
        
    def get_device_icon(self) -> Optional[str]:
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "Icon"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the Icon
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_device_class(self) -> Optional[dbus.UInt32]:
        try:
            return dbus.UInt32(self._props_iface.Get(DEVICE_INTERFACE, "Class"))
            ## Note: This is a 32-bit integer, so we need to convert it to a string
            #    -> Use the existing function decode__class_of_device() from the monolith code
        except dbus.exceptions.DBusException as e:
            return None
        
    def get_device_appearance(self) -> Optional[dbus.UInt16]:
        try:
            return dbus.UInt16(self._props_iface.Get(DEVICE_INTERFACE, "Appearance"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the Appearance
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_uuids(self) -> Optional[list[str]]:
        try:
            return list(self._props_iface.Get(DEVICE_INTERFACE, "UUIDs"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the UUIDs
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_modalias(self) -> Optional[str]:
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "Modalias"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the Modalias
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_rssi(self) -> Optional[int]:
        try:
            return int(self._props_iface.Get(DEVICE_INTERFACE, "RSSI"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the RSSI
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_tx_power(self) -> Optional[int]:
        try:
            return int(self._props_iface.Get(DEVICE_INTERFACE, "TxPower"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the TxPower
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_manufacturer_data(self) -> Optional[dict[str, bytes]]:
        try:
            return dict(self._props_iface.Get(DEVICE_INTERFACE, "ManufacturerData"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the ManufacturerData
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_service_data(self) -> Optional[dict[str, bytes]]:
        try:
            return dict(self._props_iface.Get(DEVICE_INTERFACE, "ServiceData"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the ServiceData
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_advertising_flags(self) -> Optional[list[bytes]]:
        try:
            return dbus.UInt16(self._props_iface.Get(DEVICE_INTERFACE, "AdvertisingFlags"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the AdvertisingFlags
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_advertising_data(self) -> Optional[dict[str, bytes]]:
        try:
            return dict(self._props_iface.Get(DEVICE_INTERFACE, "AdvertisingData"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the AdvertisingData
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_device_sets(self) -> Optional[list[object, dict]]:
        try:
            return list(self._props_iface.Get(DEVICE_INTERFACE, "Sets"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the DeviceSets
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_preferred_bearer(self) -> Optional[str]:
        try:
            return str(self._props_iface.Get(DEVICE_INTERFACE, "PreferredBearer"))
        except dbus.exceptions.DBusException as e:
            # BlueZ sometimes deletes the object before we grab the PreferredBearer
            mapped = map_dbus_error(e)
            if mapped.code == RESULT_ERR_UNKNOWN_OBJECT:
                return None
            raise mapped
        
    def get_manufacturer(self) -> Optional[str]:
        # Note: Can only be extracted IF the manufacturer data exists
        manufacturer_data = self.get_manufacturer_data()
        if manufacturer_data:
            return manufacturer_data.get(0x0000, b"").decode("utf-8")
        return None

    # ------------------------------------------------------------------
    # Service enumeration
    # ------------------------------------------------------------------
    def services_resolved(self, *, deep: bool = False, skip_device_type_check: bool = False):
        """Return a list of services and characteristics for this device.

        This is a blocking call that will wait for services to be resolved.
        
        Parameters
        ----------
        deep : bool
            If True, perform a deep enumeration of characteristics and descriptors.
            This includes retry logic for failed reads and additional error classification.
        skip_device_type_check : bool
            If True, skip the device type check. This is useful when called from
            check_device_type to avoid infinite recursion.
        
        Returns
        -------
        list
            A list of Service objects.
        """
        if not self.is_services_resolved():
            print_and_log(
                f"[!] Services not resolved for {self.mac_address}", LOG__GENERAL
            )
            return []

        # Clear any previous services
        self._services = []
        
        # Fetch all objects from BlueZ
        managed_objects = self._object_manager.GetManagedObjects()

        # Collect all services for this device
        service_paths = []
        for path, interfaces in managed_objects.items():
            if GATT_SERVICE_INTERFACE in interfaces:
                if path.startswith(self._device_path):
                    service_paths.append(path)

        # Sort service paths to ensure consistent ordering
        service_paths.sort()

        # Create Service objects
        for path in service_paths:
            service_obj = self._bus.get_object(BLUEZ_SERVICE_NAME, path)
            service_props = dbus.Interface(service_obj, DBUS_PROPERTIES)
            
            # Get service properties
            uuid = str(service_props.Get(GATT_SERVICE_INTERFACE, "UUID"))
            primary = bool(service_props.Get(GATT_SERVICE_INTERFACE, "Primary"))
            
            # Create Service object
            service = Service(self._bus, path, uuid, primary)
            self._services.append(service)

        # Build mapping of handles to UUIDs for legacy compatibility
        self.ble_device__mapping = {}
        
        # Populate the services with their characteristics
        for service in self._services:
            service.discover_characteristics()
            
            # Add characteristics to mapping
            for char in service.characteristics:
                handle = char.handle
                if handle is not None:
                    # Use handle_int_to_hex for consistent hex representation
                    self.ble_device__mapping[handle_int_to_hex(handle)] = char.uuid

                # Add descriptors to mapping
                for desc in char.descriptors:
                    desc_handle = desc.handle
                    if desc_handle is not None:
                        # Use handle_int_to_hex for consistent hex representation
                        self.ble_device__mapping[handle_int_to_hex(desc_handle)] = desc.uuid

        # Perform deep enumeration if requested
        if deep:
            self._deep_enumerate_gatt()
            
        # Check device type if not skipped
        if not skip_device_type_check:
            self.check_device_type(skip_device_type_check=True)
            
        return self._services

    # ------------------------------------------------------------------
    # Phase-5: full characteristic/descriptor probing -------------------
    # ------------------------------------------------------------------
    def _deep_enumerate_gatt(self) -> None:
        """Run the exhaustive service→characteristic→descriptor probe.

        Updated for gatt_parity_9:
        • All read/descriptor errors are first aggregated per-UUID and left *in_review*.
        • After enumeration finishes, aggregated error codes are analysed **once** to
          decide whether the UUID belongs to the *permission* or *landmine* maps so
          duplicates between the two are avoided.
        • Multiple distinct error codes for the same UUID are supported.
        """
        from bleep.bt_ref import constants as _C
        from bleep.ble_ops.conversion import convert__hex_to_ascii
        
        # ------------------------------------------------------------------
        # Step-0  Reset state ------------------------------------------------
        # ------------------------------------------------------------------
        self.ble_device__mapping = {"Services": {}}
        self.ble_device__mine_mapping = {"in_review": {"uncategorized": []}}
        self.ble_device__permission_mapping = {"in_review": {"uncategorized": []}}

        # Keep a temporary aggregation of error codes per UUID so we can decide
        # on the *final* classification after the full walk completes.
        agg_errors: dict[str, list[int]] = {}

        # ------------------------------------------------------------------
        # Step-1  Walk services → characteristics → descriptors -------------
        # ------------------------------------------------------------------
        for svc in self._services:
            svc_entry: dict[str, Any] = {"Characteristics": {}}
            self.ble_device__mapping["Services"][svc.uuid] = svc_entry

            for char in svc.get_characteristics():
                char_map: dict[str, Any] = {
                    "Handle": handle_int_to_hex(char.handle) if char.handle is not None else None,
                    "Flags": char.flags,
                    "Value": None,
                    "Raw": None,
                    "Descriptors": {},
                }

                should_probe = any(flag in char.flags for flag in ("read", "write"))
                if should_probe:
                    value, err_code = char.safe_read_with_retry()
                    if err_code is None and value is not None:
                        ascii_val = convert__hex_to_ascii(value)
                        if not ascii_val.strip() or "\ufffd" in ascii_val:
                            ascii_val = None
                        char_map["Value"] = ascii_val
                        char_map["Raw"] = list(value)
                    else:
                        # Aggregate error for later classification
                        if err_code is not None:
                            agg_errors.setdefault(char.uuid, []).append(err_code)

                svc_entry["Characteristics"][char.uuid] = char_map

                # --- Descriptor probe ------------------------------------
                for desc in char.descriptors:
                    d_val, d_err = desc.safe_read_with_retry()
                    desc_entry: dict[str, Any] = {
                        "Handle": handle_int_to_hex(desc.handle) if desc.handle is not None else None,
                        "Flags": getattr(desc, "flags", []),
                        "Value": convert__hex_to_ascii(d_val) if d_val else None,
                        "Raw": list(d_val) if d_val else None,
                    }
                    char_map["Descriptors"][desc.uuid] = desc_entry
                    if d_err is not None:
                        agg_errors.setdefault(desc.uuid, []).append(d_err)

        # ------------------------------------------------------------------
        # Step-2  Classify aggregated errors -------------------------------
        # ------------------------------------------------------------------
        def _classify_errors(err_list: list[int], *, obj_type: str) -> tuple[str | None, str | None]:
            """Return (permission_category, landmine_category) based on *err_list* and object type."""
            perm_cat: str | None = None
            mine_cat: str | None = None

            # --------------------- Permission categories ------------------
            if _C.RESULT_ERR_READ_NOT_PERMITTED in err_list:
                perm_cat = "read_not_permitted"
            elif _C.RESULT_ERR_NOT_AUTHORIZED in err_list:
                perm_cat = "requires_authentication"
            elif _C.RESULT_ERR_NOT_SUPPORTED in err_list:
                perm_cat = "not_supported"
            elif _C.RESULT_ERR_WRITE_NOT_PERMITTED in err_list:
                perm_cat = "write_not_permitted"
            elif _C.RESULT_ERR_NOTIFY_NOT_PERMITTED in err_list:
                perm_cat = "notify_not_permitted"
            elif _C.RESULT_ERR_INDICATE_NOT_PERMITTED in err_list:
                perm_cat = "indicate_not_permitted"
            elif _C.RESULT_ERR_NOT_PERMITTED in err_list:
                # Generic fallback – guess based on object type; keep previous
                # heuristic for backward compatibility.
                perm_cat = "notify_not_permitted" if obj_type == "descriptor" else "write_not_permitted"

            # ------------------------ Landmine categories ------------------
            if _C.RESULT_ERR_NO_REPLY in err_list:
                mine_cat = "no_reply"
            elif _C.RESULT_ERR_REMOTE_DISCONNECT in err_list:
                mine_cat = "remote_disconnect"
            elif _C.RESULT_ERR_UNKNOWN_CONNECT_FAILURE in err_list:
                mine_cat = "unknown_failure"
            elif _C.RESULT_ERR_ACTION_IN_PROGRESS in err_list:
                mine_cat = "action_in_progress"
            elif _C.RESULT_ERR in err_list:
                mine_cat = "other_error"

            return perm_cat, mine_cat

        # Build quick lookup set of characteristic UUIDs to detect descriptor vs characteristic
        _char_uuids = {c.uuid for s in self._services for c in s.characteristics}

        for uuid, errs in agg_errors.items():
            obj_t = "characteristic" if uuid in _char_uuids else "descriptor"
            perm, mine = _classify_errors(errs, obj_type=obj_t)

            if perm:
                self.update_permission_mapping(uuid, perm, obj_type=obj_t)
            else:
                self.ble_device__permission_mapping = self.device_map__update_in_review(
                    self.ble_device__permission_mapping, uuid
                )

            if mine:
                self.update_mine_mapping(uuid, mine, obj_type=obj_t)
            else:
                self.ble_device__mine_mapping = self.device_map__update_in_review(
                    self.ble_device__mine_mapping, uuid
                )

        # Finally, ensure maps are cleaned to remove empty placeholders
        self.ble_device__permission_mapping = self.device_map__clean_map(
            self.ble_device__permission_mapping
        )
        self.ble_device__mine_mapping = self.device_map__clean_map(
            self.ble_device__mine_mapping
        )

        print_and_log(
            f"[*] Deep enumeration completed. Landmine map: {self.ble_device__mine_mapping}; "
            f"Permission map: {self.ble_device__permission_mapping}",
            LOG__DEBUG,
        )
        # No return value – maps updated in-place

    # ------------------------------------------------------------------
    # Landmine and permission mapping methods
    # ------------------------------------------------------------------
    def record_landmine(self, char_uuid: str, category: str, details: str = ""):
        """Record a landmine (problematic characteristic) in the device's landmine map.
        
        Parameters
        ----------
        char_uuid : str
            UUID of the problematic characteristic
        category : str
            Category of landmine, e.g., 'timeout', 'crash', 'other_error'
        details : str
            Additional details about the landmine
        """
        category = category.lower()
        if category not in self._landmine_map:
            self._landmine_map[category] = {}
        
        # Store information about this characteristic
        self._landmine_map[category][char_uuid] = details
        
        # Also update legacy mapping for compatibility
        self.update_mine_mapping(char_uuid, category)
        
        print_and_log(
            f"[*] Recorded landmine: {char_uuid} ({category}): {details}", LOG__DEBUG
        )
        return True

    def record_security_requirement(self, char_uuid: str, requirement: str, details: str = ""):
        """Record a security requirement for a characteristic.
        
        Parameters
        ----------
        char_uuid : str
            UUID of the characteristic with security requirement
        requirement : str
            Type of security requirement, e.g., 'requires_authentication', 'requires_encryption'
        details : str
            Additional details about the security requirement
        """
        requirement = requirement.lower()
        if requirement not in self._security_map:
            self._security_map[requirement] = {}
        
        # Store information about this characteristic
        self._security_map[requirement][char_uuid] = details
        
        # Also update legacy mapping for compatibility
        self.update_permission_mapping(char_uuid, requirement)
        
        print_and_log(
            f"[*] Recorded security requirement: {char_uuid} ({requirement}): {details}", LOG__DEBUG
        )
        return True

    def get_landmine_report(self):
        """Get a structured report of all recorded landmines.
        
        Returns
        -------
        dict
            A dictionary mapping landmine categories to lists of entries
        """
        report = {}
        for category, entries in self._landmine_map.items():
            if entries:
                report[category] = [
                    {"uuid": uuid, "details": details} 
                    for uuid, details in entries.items()
                ]
        return report

    def get_security_report(self):
        """Get a structured report of all security requirements.
        
        Returns
        -------
        dict
            A dictionary mapping security requirement types to lists of entries
        """
        report = {}
        for requirement, entries in self._security_map.items():
            if entries:
                report[requirement] = [
                    {"uuid": uuid, "details": details}
                    for uuid, details in entries.items()
                ]
        return report

    def check_characteristic_safety(self, uuid: str):
        """Check if a characteristic has any known landmines or security requirements.
        
        Parameters
        ----------
        uuid : str
            UUID of the characteristic to check
            
        Returns
        -------
        tuple
            (is_safe, issues) where is_safe is a boolean and issues is a dict
            of any problems found
        """
        issues = {}
        
        # Check landmines
        for category, entries in self._landmine_map.items():
            if uuid in entries:
                if "landmines" not in issues:
                    issues["landmines"] = {}
                issues["landmines"][category] = entries[uuid]
        
        # Check security requirements
        for requirement, entries in self._security_map.items():
            if uuid in entries:
                if "security" not in issues:
                    issues["security"] = {}
                issues["security"][requirement] = entries[uuid]
        
        # Also check legacy mappings
        is_mine, is_security, details = self.evaluate__known_mine_check(uuid)
        if is_mine and "landmines" not in issues:
            issues["landmines"] = {"legacy": details}
        if is_security and "security" not in issues:
            issues["security"] = {"legacy": details}
        
        # Characteristic is safe if there are no issues
        is_safe = not issues
        
        return is_safe, issues

    def device_map__entry_check(self, mapping: dict, entry: str) -> bool:
        """Check if an entry exists in any of the mapping categories.
        
        Parameters
        ----------
        mapping : dict
            The mapping dictionary to check
        entry : str
            The entry to look for
            
        Returns
        -------
        bool
            True if entry exists, False otherwise
        """
        if not mapping or not isinstance(mapping, dict):
            return False
        
        # Check if entry exists in any category
        for category in mapping:
            if category in mapping and entry in mapping[category]:
                return True
                
        # Check if there's an in_review section
        if "in_review" in mapping:
            for category in mapping["in_review"]:
                if entry in mapping["in_review"][category]:
                    return True
        
        return False

    def device_map__update_in_review(self, mapping: dict, entry: str) -> dict:
        """Add an entry to the in_review section of a mapping.
        
        Parameters
        ----------
        mapping : dict
            The mapping dictionary to update
        entry : str
            The entry to add to in_review
            
        Returns
        -------
        dict
            The updated mapping
        """
        if not mapping or not isinstance(mapping, dict):
            mapping = {}
            
        # Create in_review section if it doesn't exist
        if "in_review" not in mapping:
            mapping["in_review"] = {}
            
        # Create uncategorized section if it doesn't exist
        if "uncategorized" not in mapping["in_review"]:
            mapping["in_review"]["uncategorized"] = []
            
        # Add entry to uncategorized if not already present
        if entry not in mapping["in_review"]["uncategorized"]:
            mapping["in_review"]["uncategorized"].append(entry)
            
        return mapping

    def device_map__set_from_in_review(self, mapping: dict, entry: str, category: str) -> dict:
        """Move an entry from in_review to a specific category.
        
        Parameters
        ----------
        mapping : dict
            The mapping dictionary to update
        entry : str
            The entry to move
        category : str
            The category to move the entry to
            
        Returns
        -------
        dict
            The updated mapping
        """
        if not mapping or not isinstance(mapping, dict):
            mapping = {}
            
        # Check if the entry exists in in_review
        if "in_review" in mapping:
            # Search through all categories in in_review
            for in_review_cat in mapping["in_review"]:
                if entry in mapping["in_review"][in_review_cat]:
                    # Remove from in_review
                    mapping["in_review"][in_review_cat].remove(entry)
                    
                    # Clean up empty categories
                    if not mapping["in_review"][in_review_cat]:
                        del mapping["in_review"][in_review_cat]
                    if not mapping["in_review"]:
                        del mapping["in_review"]
                    break
        
        # Create target category if it doesn't exist
        if category not in mapping:
            mapping[category] = []
            
        # Add entry to target category if not already present
        if entry not in mapping[category]:
            mapping[category].append(entry)
            
        return mapping

    def device_map__clean_map(self, mapping: dict) -> dict:
        """Clean up a mapping by removing empty categories.
        
        Parameters
        ----------
        mapping : dict
            The mapping dictionary to clean
            
        Returns
        -------
        dict
            The cleaned mapping
        """
        if not mapping or not isinstance(mapping, dict):
            return {}
            
        # Create a new mapping with only non-empty categories
        cleaned_mapping = {}
        
        for category, entries in mapping.items():
            if entries:  # Not empty
                if category == "in_review":
                    # Special handling for in_review
                    cleaned_in_review = {}
                    for sub_cat, sub_entries in entries.items():
                        if sub_entries:  # Not empty
                            cleaned_in_review[sub_cat] = sub_entries
                            
                    if cleaned_in_review:  # Not empty
                        cleaned_mapping["in_review"] = cleaned_in_review
                else:
                    cleaned_mapping[category] = entries
                    
        return cleaned_mapping

    def evaluate__known_mine_check(self, reference_entry: str) -> tuple:
        """Check if an entry is in any of the mine or permission mappings.
        
        Parameters
        ----------
        reference_entry : str
            The entry to check
            
        Returns
        -------
        tuple
            (is_mine, is_security, details) where is_mine and is_security are 
            booleans and details is a string describing any found issues
        """
        # Check if entry is in any mine mapping category
        is_mine = False
        is_security = False
        details = ""
        
        # Check mine mapping
        if self.device_map__entry_check(self.ble_device__mine_mapping, reference_entry):
            is_mine = True
            # Find the specific category
            for category, entries in self.ble_device__mine_mapping.items():
                if category != "in_review" and reference_entry in entries:
                    details += f"Landmine: {category}. "
            
            # Check in_review section
            if "in_review" in self.ble_device__mine_mapping:
                for category, entries in self.ble_device__mine_mapping["in_review"].items():
                    if reference_entry in entries:
                        details += f"Potential landmine in review ({category}). "
        
        # Check permission mapping
        if self.device_map__entry_check(self.ble_device__permission_mapping, reference_entry):
            is_security = True
            # Find the specific requirement
            for requirement, entries in self.ble_device__permission_mapping.items():
                if requirement != "in_review" and reference_entry in entries:
                    details += f"Security: {requirement}. "
            
            # Check in_review section
            if "in_review" in self.ble_device__permission_mapping:
                for category, entries in self.ble_device__permission_mapping["in_review"].items():
                    if reference_entry in entries:
                        details += f"Potential security requirement in review ({category}). "
        
        # Also check the enhanced mapping (if entry is a UUID)
        for category, entries in self._landmine_map.items():
            if reference_entry in entries:
                is_mine = True
                detail = entries[reference_entry]
                details += f"Landmine: {category} - {detail}. "
                
        for requirement, entries in self._security_map.items():
            if reference_entry in entries:
                is_security = True
                detail = entries[reference_entry]
                details += f"Security: {requirement} - {detail}. "
        
        return is_mine, is_security, details

    def update_mine_mapping(self, characteristic_uuid: str, issue_type: str = "other_error", *, obj_type: str = "characteristic") -> None:
        """Update the landmine (mine) mapping with a problematic UUID.

        Parameters
        ----------
        characteristic_uuid : str
            UUID of the problematic attribute
        issue_type : str
            Category of landmine: 'crash', 'timeout', 'remote_disconnect',
            'no_reply', 'value_error', 'unknown_failure', 'action_in_progress',
            or 'other_error'.
        obj_type : str, optional
            Object granularity – 'service', 'characteristic', or 'descriptor'.
            The old monolith stored separate top-level buckets for each.
        """
        # Normalise ----------------------------------------------
        issue_type = issue_type.lower()
        obj_type = obj_type.lower()
        if obj_type not in {"service", "characteristic", "descriptor"}:
            obj_type = "characteristic"
        valid_types = {
            "crash",
            "timeout",
            "remote_disconnect",
            "no_reply",
            "value_error",
            "unknown_failure",
            "action_in_progress",
            "other_error",
        }
        if issue_type not in valid_types:
            issue_type = "other_error"

        # Ensure object-type bucket exists ------------------------
        if obj_type not in self.ble_device__mine_mapping:
            self.ble_device__mine_mapping[obj_type] = {}
        # Same for permission map in case caller mis-routes -------

        # Ensure category list exists ----------------------------
        bucket = self.ble_device__mine_mapping[obj_type].setdefault(issue_type, [])
        if characteristic_uuid not in bucket:
            bucket.append(characteristic_uuid)

        # Remove from any in_review slots ------------------------
        self.ble_device__mine_mapping = self.device_map__clean_map(self.ble_device__mine_mapping)

        print_and_log(
            f"[*] Landmine map ++ {obj_type}/{issue_type} <- {characteristic_uuid}",
            LOG__DEBUG,
        )

        # ------------------------------------------------------------------
        # Keep _landmine_map (used by get_landmine_report) in sync ----------
        # ------------------------------------------------------------------
        # Use the *issue_type* as the top-level category just like
        # record_landmine(); store an empty string as details because the deep
        # enumerator doesn't have per-error text at this point.

        if issue_type not in self._landmine_map:
            self._landmine_map[issue_type] = {}

        # Do not overwrite if another call (e.g. record_landmine) already
        # inserted a more descriptive entry.
        self._landmine_map[issue_type].setdefault(characteristic_uuid, "")

    def update_permission_mapping(self, characteristic_uuid: str, requirement: str = "access_rejected", *, obj_type: str = "characteristic") -> None:
        """Update the permission/security mapping.

        Parameters
        ----------
        characteristic_uuid : str
            UUID requiring special security handling
        requirement : str
            Requirement category: 'requires_encryption', 'requires_authentication',
            'requires_authorization', 'requires_secure_connection',
            'read_not_permitted', 'access_rejected', 'no_response'.
        obj_type : str, optional
            'service', 'characteristic', or 'descriptor'
        """
        requirement = requirement.lower()
        obj_type = obj_type.lower()
        if obj_type not in {"service", "characteristic", "descriptor"}:
            obj_type = "characteristic"
        valid_reqs = {
            "requires_encryption",
            "requires_authentication",
            "requires_authorization",
            "requires_secure_connection",
            "read_not_permitted",
            "access_rejected",
            "no_response",
            "write_not_permitted",
            "notify_not_permitted",
            "indicate_not_permitted",
            "not_supported",
        }
        if requirement not in valid_reqs:
            requirement = "access_rejected"

        if obj_type not in self.ble_device__permission_mapping:
            self.ble_device__permission_mapping[obj_type] = {}

        bucket = self.ble_device__permission_mapping[obj_type].setdefault(requirement, [])
        if characteristic_uuid not in bucket:
            bucket.append(characteristic_uuid)

        self.ble_device__permission_mapping = self.device_map__clean_map(self.ble_device__permission_mapping)

        print_and_log(
            f"[*] Permission map ++ {obj_type}/{requirement} <- {characteristic_uuid}",
            LOG__DEBUG,
        )

        # ------------------------------------------------------------------
        # Keep _security_map (used by get_security_report) in sync -----------
        # ------------------------------------------------------------------
        if requirement not in self._security_map:
            self._security_map[requirement] = {}

        self._security_map.setdefault(requirement, {}).setdefault(characteristic_uuid, "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _attach_property_signal(self):
        if self._properties_signal is None:
            self._properties_signal = self._props_iface.connect_to_signal(
                "PropertiesChanged", self._properties_changed
            )

    def _properties_changed(self, interface, changed, invalidated):  # noqa: D401
        """Handle PropertiesChanged signal."""
        if interface != DEVICE_INTERFACE:
            return

        if "Connected" in changed:
            if not changed["Connected"]:
                print_and_log(f"[*] Device {self.mac_address} disconnected", LOG__DEBUG)
                # If we have a reconnection monitor and it's not already handling this,
                # trigger reconnection
                if (hasattr(self, "_reconnection_monitor") and 
                        self._reconnection_monitor and 
                        self._reconnection_monitor._monitoring):
                    # The monitor will handle this in its thread
                    pass
            else:
                print_and_log(f"[*] Device {self.mac_address} connected", LOG__DEBUG)

        if "ServicesResolved" in changed:
            if changed["ServicesResolved"]:
                print_and_log(f"[+] Services resolved for {self.mac_address}", LOG__DEBUG)
                self.services_resolved()

    def _detach_property_signal(self):
        if self._properties_signal is not None:
            try:
                self._properties_signal.remove()
            finally:
                self._properties_signal = None

    # ------------------------------------------------------------------
    # Legacy-API compatibility stubs (Phase-4 TODOs)
    # ------------------------------------------------------------------

    # These helpers mirror the public surface of the original
    # `bluetooth__le__device`.  Most of them are thin wrappers or no-ops for
    # now – they will be fully implemented once the corresponding
    # functionality is migrated in Phase-5/6.  Having them present already
    # avoids import errors during incremental refactor.

    # Advertisement callback ------------------------------------------------
    def advertised(self):  # noqa: D401
        """Called by manager when a scan advert matches this device."""
        # The monolith only logged the event; preserve behaviour.
        print_and_log(f"[ADV] Device {self.mac_address} advertised", LOG__DEBUG)

    # Registration helpers --------------------------------------------------
    def is_registered(self):
        # Registration concept tied to higher-level manager logic – always
        # return True for now until manager is ported.
        return True

    def register(self):  # pragma: no cover – semantics pending
        # Placeholder to satisfy external calls; real registration handled by
        # manager update_devices.
        pass

    # Connection signalling stubs ------------------------------------------
    def _connect_signals(self):
        # Already handled via `_attach_property_signal` in new design.  Keep
        # alias for legacy callers.
        self._attach_property_signal()
        self._connect_service_signals()

    def _connect_service_signals(self):
        for svc in self._services:
            svc._connect_signals()  # type: ignore[attr-defined]

    def connect_succeeded(self):
        print_and_log(f"[+] Connect succeeded ({self.mac_address})", LOG__GENERAL)

    def connect_failed(self, error: Exception):
        print_and_log(f"[-] Connect failed ({self.mac_address}): {error}", LOG__GENERAL)
        self._detach_property_signal()

    # Disconnection signalling ---------------------------------------------
    def disconnect_succeeded(self):
        print_and_log(f"[*] Disconnected from {self.mac_address}", LOG__GENERAL)
        self._services.clear()
        self._detach_property_signal()

    def _disconnect_signals(self):
        self._detach_property_signal()
        self._disconnect_service_signals()

    def _disconnect_service_signals(self):
        for svc in self._services:
            svc._disconnect_signals()  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Convenience helpers for higher-level code (service access)
    # ------------------------------------------------------------------

    def _find_service(self, uuid: str) -> Optional[Service]:
        """Return the *first* service whose UUID matches ``uuid``.

        The search is case-insensitive and ignores dashes so callers may pass
        either the canonical 128-bit form or the short 16-bit slice.
        
        Parameters
        ----------
        uuid : str
            The UUID of the service to find
            
        Returns
        -------
        Optional[Service]
            The service if found, None otherwise
        """
        # Use the identify_uuid utility function to get all possible canonical forms
        canonical_targets = identify_uuid(uuid)
        
        # Debug log the targets we're looking for
        print_and_log(f"[DEBUG] Looking for service with UUID targets: {canonical_targets}", LOG__DEBUG)
        
        # Debug log all available services
        service_uuids = [svc.uuid.replace("-", "").lower() for svc in self._services]
        print_and_log(f"[DEBUG] Available services: {service_uuids}", LOG__DEBUG)

        # First try exact matches
        for svc in self._services:
            su = svc.uuid.replace("-", "").lower()
            if su in canonical_targets:
                return svc
        
        # Then try partial matches for short UUIDs
        for svc in self._services:
            su = svc.uuid.replace("-", "").lower()
            # Check if any of our short UUID forms match
            for target in canonical_targets:
                if len(target) == 4:  # This is a short UUID
                    if su[4:8] == target:
                        return svc
        
        return None

    # ------------------------------------------------------------------
    # Convenience helpers for higher-level code (characteristic access)
    # ------------------------------------------------------------------

    def _find_characteristic(self, uuid: str) -> Optional[Characteristic]:
        """Return the *first* characteristic whose UUID matches ``uuid``.

        The search is case-insensitive and ignores dashes so callers may pass
        either the canonical 128-bit form or the short 16-bit slice.
        """
        # Use the identify_uuid utility function to get all possible canonical forms
        canonical_targets = identify_uuid(uuid)
        
        # Debug log the targets we're looking for
        print_and_log(f"[DEBUG] Looking for characteristic with UUID targets: {canonical_targets}", LOG__DEBUG)

        # First try exact matches
        for svc in self._services:
            for char in svc.characteristics:
                cu = char.uuid.replace("-", "").lower()
                if cu in canonical_targets:
                    return char
        
        # Then try partial matches for short UUIDs
        for svc in self._services:
            for char in svc.characteristics:
                cu = char.uuid.replace("-", "").lower()
                # Check if any of our short UUID forms match
                for target in canonical_targets:
                    if len(target) == 4:  # This is a short UUID
                        if cu[4:8] == target:
                            return char
        
        return None

    # Public wrappers -----------------------------------------------------

    def get_characteristic(self, uuid: str) -> Characteristic | None:
        """Expose characteristic lookup to external callers."""
        return self._find_characteristic(uuid)

    def read_characteristic(self, uuid: str, offset: int = 0) -> bytes:
        """Read a characteristic value by UUID.
        
        Parameters
        ----------
        uuid : str
            The UUID of the characteristic to read
        offset : int
            Offset to read from (default: 0)
            
        Returns
        -------
        bytes
            The value read from the characteristic
        """
        char = self._find_characteristic(uuid)
        if not char:
            raise ValueError(f"Characteristic {uuid} not found")
        
        try:
            value = char.read_value(offset)
            
            # Check if there's a signal manager to trigger read events
            try:
                # Try global signals manager first
                from bleep.core.device_management import _get_global_signals
                signals = _get_global_signals()
                signals.handle_read_event(char.path, value)
            except (ImportError, AttributeError):
                # Fall back to local signal manager
                global _signals_manager
                if _signals_manager:
                    _signals_manager.handle_read_event(char.path, value)
            
            return value
        except dbus.exceptions.DBusException as e:
            # Record as a landmine if it fails
            self.record_landmine(uuid, "read_error", str(e))
            self.update_mine_mapping(uuid, "value_error")
            
            # Rethrow the exception
            raise map_dbus_error(e)

    def write_characteristic(
        self,
        uuid: str,
        value: bytes | bytearray | list[int],
        without_response: bool = False,
    ) -> None:
        """Write a value to a characteristic.
        
        Parameters
        ----------
        uuid : str
            The UUID of the characteristic to write to
        value : bytes | bytearray | list[int]
            The value to write
        without_response : bool
            Whether to write without expecting a response
        """
        char = self._find_characteristic(uuid)
        if not char:
            raise ValueError(f"Characteristic {uuid} not found")
        
        # Convert value to bytes if needed
        if isinstance(value, list):
            value = bytes(value)
        elif not isinstance(value, (bytes, bytearray)):
            raise TypeError("Value must be bytes, bytearray, or list of integers")
        
        try:
            if without_response:
                char.write_value(value, {"type": "command"})
            else:
                char.write_value(value)
            
            # Check if there's a signal manager to trigger write events
            try:
                # Try global signals manager first
                from bleep.core.device_management import _get_global_signals
                signals = _get_global_signals()
                signals.handle_write_event(char.path, value)
            except (ImportError, AttributeError):
                # Fall back to local signal manager
                global _signals_manager
                if _signals_manager:
                    _signals_manager.handle_write_event(char.path, value)
                
        except dbus.exceptions.DBusException as e:
            # Record as a landmine if it fails
            self.record_landmine(uuid, "write_error", str(e))
            self.update_mine_mapping(uuid, "value_error")
            
            # Check if it's a permission issue
            error_name = e.get_dbus_name()
            if "NotPermitted" in error_name or "NotAuthorized" in error_name:
                self.record_security_requirement(uuid, "access_rejected", str(e))
                self.update_permission_mapping(uuid, "access_rejected")
            
            # Rethrow the exception
            raise map_dbus_error(e)

    def enable_notifications(self, uuid: str, callback) -> None:
        """Enable notifications for a characteristic.
        
        Parameters
        ----------
        uuid : str
            The UUID of the characteristic
        callback
            Function to call when notifications are received
        """
        char = self._find_characteristic(uuid)
        if not char:
            raise ValueError(f"Characteristic {uuid} not found")
        
        # Start notifications on the characteristic
        char.start_notify(callback)
        
        # Check if we have signals manager in the device manager
        from bleep.dbuslayer.signals import system_dbus__bluez_signals
        device_manager = getattr(self, "_device_manager", None)
        signals_manager = None
        
        if device_manager:
            signals_manager = getattr(device_manager, "_signals", None)
        
        # Try global instance if not found in device_manager
        if not signals_manager:
            try:
                from bleep.core.device_management import _get_global_signals
                signals_manager = _get_global_signals()
            except (ImportError, AttributeError):
                pass
            
        # Register the callback with the signals manager
        if signals_manager and isinstance(signals_manager, system_dbus__bluez_signals):
            # Create a wrapper that converts the path to the characteristic
            def notification_wrapper(path, value):
                # Only call if path matches our characteristic path
                if path == char.path:
                    callback(value)
                
            # Register the wrapper
            signals_manager.register_notification_callback(char.path, notification_wrapper)
            
            # Store the wrapper on the characteristic for later removal
            if not hasattr(char, "_notification_callbacks"):
                char._notification_callbacks = []
            char._notification_callbacks.append(notification_wrapper)

    def disable_notifications(self, uuid: str) -> None:
        """Disable notifications for a characteristic.
        
        Parameters
        ----------
        uuid : str
            The UUID of the characteristic
        """
        char = self._find_characteristic(uuid)
        if not char:
            raise ValueError(f"Characteristic {uuid} not found")
        
        # Stop notifications on the characteristic
        char.stop_notify()
        
        # Check if we have signals manager in the device manager
        from bleep.dbuslayer.signals import system_dbus__bluez_signals
        device_manager = getattr(self, "_device_manager", None)
        signals_manager = None
        
        if device_manager:
            signals_manager = getattr(device_manager, "_signals", None)
        
        # Try global instance if not found in device_manager
        if not signals_manager:
            try:
                from bleep.core.device_management import _get_global_signals
                signals_manager = _get_global_signals()
            except (ImportError, AttributeError):
                pass
            
        # Unregister callbacks from the signals manager
        if signals_manager and isinstance(signals_manager, system_dbus__bluez_signals) and hasattr(char, "_notification_callbacks"):
            for callback in char._notification_callbacks:
                signals_manager.unregister_notification_callback(char.path, callback)
            char._notification_callbacks = []

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def __repr__(self):  # pragma: no cover – debugging aid
        return f"<BLEDevice {self.mac_address} connected={self.is_connected()}>"

    # ------------------------------------------------------------------
    # D-Bus lifecycle signal hooks – called by system_dbus__bluez_signals
    # ------------------------------------------------------------------
    def interfaces_added(self, object_path: str, interfaces: dict):  # noqa: D401
        """Placeholder callback invoked when the global signal hub sees a new interface.

        A full implementation will update the service/characteristic caches once
        the remaining enumeration helpers have been migrated.  For now we only
        log the event so behaviour parity with the monolith is preserved.
        """
        print_and_log(
            f"[DEBUG] Device {self.mac_address} InterfacesAdded for {object_path}",
            LOG__DEBUG,
        )

    def interfaces_removed(self, object_path: str, interfaces: list[str]):  # noqa: D401
        print_and_log(
            f"[DEBUG] Device {self.mac_address} InterfacesRemoved for {object_path}",
            LOG__DEBUG,
        )
        # Remove any cached service/characteristic that disappeared so caches stay fresh
        self._services = [
            svc for svc in self._services if not object_path.startswith(svc.path)
        ]

    # ------------------------------------------------------------------
    # Global notification hook called by signals manager
    # ------------------------------------------------------------------
    def characteristic_value_updated(self, characteristic: Characteristic, value: bytes):  # noqa: D401
        """Handle characteristic value update.

        Called by the signals manager when a characteristic value changes.
        """
        print_and_log(
            f"[*] Characteristic value updated: {characteristic.uuid} = {value.hex()}",
            LOG__DEBUG,
        )
        
    # ---------------------------------------------------------------------
    # Media device support
    # ---------------------------------------------------------------------
    def get_media_control(self) -> Optional[MediaControl]:
        """Get the MediaControl interface for this device.
        
        Returns
        -------
        Optional[MediaControl]
            MediaControl interface or None if not available
        """
        try:
            return MediaControl(self._device_path)
        except BLEEPError:
            return None
    
    def get_media_player(self, player_path: Optional[str] = None) -> Optional[MediaPlayer]:
        """Get the MediaPlayer interface for this device.
        
        Parameters
        ----------
        player_path : Optional[str]
            Path to the player object. If None, it will be determined automatically.
        
        Returns
        -------
        Optional[MediaPlayer]
            MediaPlayer interface or None if not available
        """
        if player_path is None:
            # Try to get player path from MediaControl interface
            media_control = self.get_media_control()
            if media_control:
                player_path = media_control.get_player()
            
            # If still None, try to find player by pattern
            if player_path is None:
                # Look for player0 under the device path
                player_path = f"{self._device_path}/player0"
        
        if player_path:
            try:
                return MediaPlayer(player_path)
            except BLEEPError:
                return None
        return None
    
    def get_media_endpoints(self) -> List[MediaEndpoint]:
        """Get all MediaEndpoint interfaces for this device.
        
        Returns
        -------
        List[MediaEndpoint]
            List of MediaEndpoint interfaces
        """
        endpoints = []
        
        # Find all media devices and check if any match our device path
        media_devices = find_media_devices()
        if self._device_path in media_devices and "MediaEndpoints" in media_devices[self._device_path]:
            for endpoint_path in media_devices[self._device_path]["MediaEndpoints"]:
                try:
                    endpoints.append(MediaEndpoint(endpoint_path))
                except BLEEPError:
                    pass
        
        return endpoints
    
    def get_media_transports(self) -> List[MediaTransport]:
        """Get all MediaTransport interfaces for this device.
        
        Returns
        -------
        List[MediaTransport]
            List of MediaTransport interfaces
        """
        transports = []
        
        # Find all media devices and check if any match our device path
        media_devices = find_media_devices()
        if self._device_path in media_devices and "MediaTransports" in media_devices[self._device_path]:
            for transport_path in media_devices[self._device_path]["MediaTransports"]:
                try:
                    transports.append(MediaTransport(transport_path))
                except BLEEPError:
                    pass
        
        return transports
    
    def is_media_device(self) -> bool:
        """Check if this device supports media interfaces.
        
        Returns
        -------
        bool
            True if the device has any media interfaces, False otherwise
        """
        return (
            self.get_media_control() is not None or 
            self.get_media_player() is not None or 
            len(self.get_media_endpoints()) > 0 or 
            len(self.get_media_transports()) > 0
        )
    
    def play_media(self) -> bool:
        """Start media playback.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        player = self.get_media_player()
        if player:
            return player.play()
        return False
    
    def pause_media(self) -> bool:
        """Pause media playback.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        player = self.get_media_player()
        if player:
            return player.pause()
        return False
    
    def stop_media(self) -> bool:
        """Stop media playback.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        player = self.get_media_player()
        if player:
            return player.stop()
        return False
    
    def next_track(self) -> bool:
        """Skip to the next track.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        player = self.get_media_player()
        if player:
            return player.next()
        return False
    
    def previous_track(self) -> bool:
        """Skip to the previous track.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        player = self.get_media_player()
        if player:
            return player.previous()
        return False
    
    def get_track_info(self) -> Dict[str, Any]:
        """Get information about the current track.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary of track metadata or empty dict if not available
        """
        player = self.get_media_player()
        if player:
            return player.get_track()
        return {}
    
    def get_playback_status(self) -> Optional[str]:
        """Get the current playback status.
        
        Returns
        -------
        Optional[str]
            Status of the player (e.g., "playing", "paused", "stopped") or None if not available
        """
        player = self.get_media_player()
        if player:
            return player.get_status()
        return None
    
    def set_volume(self, volume: int) -> bool:
        """Set the volume of the media transport.
        
        Parameters
        ----------
        volume : int
            Volume level (0-127)
            
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        transports = self.get_media_transports()
        if transports:
            # Try to set volume on all transports, return True if any succeed
            return any(transport.set_volume(volume) for transport in transports)
        return False
    
    def get_volume(self) -> Optional[int]:
        """Get the volume of the media transport.
        
        Returns
        -------
        Optional[int]
            Volume level (0-127) or None if not available
        """
        transports = self.get_media_transports()
        if transports:
            # Return volume of the first transport that has a volume
            for transport in transports:
                volume = transport.get_volume()
                if volume is not None:
                    return volume
        return None

    # ------------------------------------------------------------------
    # Service re-resolution
    # ------------------------------------------------------------------
    def force_service_resolution(self, timeout: float = 10.0) -> bool:
        """Force re-resolution of device services.
        
        This method clears the cached services and forces BlueZ to re-discover
        all services and characteristics. This is useful when services change
        or when initial resolution was incomplete.
        
        Parameters
        ----------
        timeout : float
            Maximum time to wait for services to be resolved, in seconds
            
        Returns
        -------
        bool
            True if services were successfully re-resolved, False otherwise
            
        Raises
        ------
        BLEEPError
            If re-resolution fails with an error
        """
        print_and_log(f"[*] Forcing service re-resolution for {self.mac_address}", LOG__USER)
        
        try:
            # Clear cached services
            self._services = []
            
            # First try using the BlueZ RefreshServices method if available
            try:
                self._device_iface.RefreshServices()
                print_and_log("[+] RefreshServices method called successfully", LOG__DEBUG)
            except (dbus.exceptions.DBusException, AttributeError) as e:
                # RefreshServices not available, fall back to disconnect/reconnect
                print_and_log(f"[*] RefreshServices not available: {str(e)}", LOG__DEBUG)
                print_and_log("[*] Falling back to disconnect/reconnect method", LOG__DEBUG)
                
                # Disconnect
                if self.is_connected():
                    self.disconnect()
                    time.sleep(1)  # Give BlueZ time to clean up
                
                # Reconnect
                self.connect()
            
            # Wait for services to be resolved
            waited = 0.0
            while waited < timeout:
                if self.is_services_resolved():
                    print_and_log("[+] Services successfully re-resolved", LOG__GENERAL)
                    # Force a refresh of our internal service cache
                    self.services_resolved(skip_device_type_check=True)
                    return True
                time.sleep(0.5)
                waited += 0.5
            
            print_and_log("[-] Service re-resolution timed out", LOG__DEBUG)
            return False
            
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Service re-resolution failed: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)
    
    def is_services_resolved(self) -> bool:
        """Check if services have been resolved.
        
        Returns
        -------
        bool
            True if services are resolved, False otherwise
        """
        try:
            return bool(self._props_iface.Get(DEVICE_INTERFACE, "ServicesResolved"))
        except (dbus.exceptions.DBusException, KeyError):
            return False
    
    # ------------------------------------------------------------------
    # Device type detection
    # ------------------------------------------------------------------
    def check_device_type(self, skip_device_type_check=False) -> Dict[str, bool]:
        """Check the type and capabilities of the device.
        
        This method analyzes the device's interfaces, services, and characteristics
        to determine its type and capabilities.
        
        Parameters
        ----------
        skip_device_type_check : bool
            If True, don't call services_resolved() to prevent recursion
            
        Returns
        -------
        Dict[str, bool]
            Dictionary with device type flags:
            - is_gatt_server: True if device exposes GATT services
            - is_media_device: True if device supports media interfaces
            - is_mesh_device: True if device supports Bluetooth Mesh
            - is_classic_device: True if device supports Bluetooth Classic
            - is_le_device: True if device supports Bluetooth LE
        """
        # Prevent recursion with a flag
        if self._in_device_type_check:
            print_and_log("[*] Already in device type check, returning cached flags", LOG__DEBUG)
            return self.device_type_flags.copy()
            
        # Set recursion prevention flag
        self._in_device_type_check = True
        
        # Set a timeout to prevent infinite loops
        start_time = time.time()
        max_time = 5.0  # 5 seconds maximum
        
        try:
            result = {
                "is_gatt_server": False,
                "is_media_device": False,
                "is_mesh_device": False,
                "is_classic_device": False,
                "is_le_device": True,  # This is a LE device by definition
            }
            
            # Check if device exposes GATT services
            if skip_device_type_check:
                # Use existing services if we're skipping the check
                result["is_gatt_server"] = len(self._services) > 0
            else:
                # Get services but don't trigger another device type check
                services = self.services_resolved(skip_device_type_check=True)
                result["is_gatt_server"] = len(services) > 0
            
            # Check device type from BlueZ
            try:
                device_type = self._props_iface.Get(DEVICE_INTERFACE, "Type")
                if str(device_type) in ["br/edr", "dual"]:
                    result["is_classic_device"] = True
            except (dbus.exceptions.DBusException, KeyError) as e:
                print_and_log(f"[*] Could not determine device type: {e}", LOG__DEBUG)
            
            # Check for media interfaces
            try:
                # Use a timeout to prevent blocking indefinitely
                if time.time() - start_time > max_time:
                    print_and_log("[!] Device type check timeout reached", LOG__DEBUG)
                    raise TimeoutError("Device type check timeout")
                    
                objects = self._object_manager.GetManagedObjects()
                for path, interfaces in objects.items():
                    if path.startswith(self._device_path):
                        if "org.bluez.MediaTransport1" in interfaces:
                            result["is_media_device"] = True
                            break
                        if "org.bluez.MediaPlayer1" in interfaces:
                            result["is_media_device"] = True
                            break
            except Exception as e:
                print_and_log(f"[*] Error checking media interfaces: {e}", LOG__DEBUG)
            
            # Check for mesh support
            try:
                # Use a timeout to prevent blocking indefinitely
                if time.time() - start_time > max_time:
                    print_and_log("[!] Device type check timeout reached", LOG__DEBUG)
                    raise TimeoutError("Device type check timeout")
                    
                uuids = self._props_iface.Get(DEVICE_INTERFACE, "UUIDs")
                for uuid in uuids:
                    if str(uuid).lower() == "00001827-0000-1000-8000-00805f9b34fb":  # Mesh Provisioning
                        result["is_mesh_device"] = True
                        break
                    if str(uuid).lower() == "00001828-0000-1000-8000-00805f9b34fb":  # Mesh Proxy
                        result["is_mesh_device"] = True
                        break
            except Exception as e:
                print_and_log(f"[*] Error checking mesh support: {e}", LOG__DEBUG)
                
            return result
            
        except Exception as e:
            print_and_log(f"[-] Error checking device type: {str(e)}", LOG__DEBUG)
            # Return default flags on error
            return self.device_type_flags.copy()
        finally:
            # Always reset recursion flag when done
            self._in_device_type_check = False
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive information about the device.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary with device information
        """
        info = {
            "address": self.mac_address,
            "name": self.get_name(),
            "alias": self.get_alias(),
            "address_type": self.get_address_type(),
            "rssi": self.get_rssi(),
            "tx_power": self.get_tx_power(),
            "connected": self.is_connected(),
            "paired": self.is_paired(),
            "trusted": self.is_trusted(),
            "bonded": self.is_bonded(),
            "blocked": self.is_blocked(),
            "legacy_pairing": self.is_legacy_pairing(),
            "cable_pairing": self.is_cable_pairing(),       ## Note: Search for this out in the wild (2025/07/07 - without enforcing encryption)
            "services_resolved": self.is_services_resolved(),
            "device_types": self.check_device_type(),
            "device_class": self.get_device_class(),
            "device_icon": self.get_device_icon(),
            "device_appearance": self.get_device_appearance(),
            "wake_allowed": self.is_wake_allowed(),
            "adapter_path": self.get_adapter_path(),
            "modalias": self.get_modalias(),
            "device_manufacturer_data": self.get_manufacturer_data(),
            "device_service_data": self.get_service_data(),
            "device_uuids": self.get_uuids(),
            "advertising_flags": self.get_advertising_flags(),
            "advertising_data": self.get_advertising_data(),
            "device_sets": self.get_device_sets(),
            "device_preferred_bearer": self.get_preferred_bearer(),
            "device_manufacturer": self.get_manufacturer(),  # Note: Can only be extracted IF the manufacturer data exists
        }
        
        # Add additional properties if available
        try:
            info["rssi"] = self._props_iface.Get(DEVICE_INTERFACE, "RSSI")
        except (dbus.exceptions.DBusException, KeyError):
            info["rssi"] = None
            
        try:
            info["tx_power"] = self._props_iface.Get(DEVICE_INTERFACE, "TxPower")
        except (dbus.exceptions.DBusException, KeyError):
            info["tx_power"] = None
            
        try:
            info["paired"] = bool(self._props_iface.Get(DEVICE_INTERFACE, "Paired"))
        except (dbus.exceptions.DBusException, KeyError):
            info["paired"] = None
            
        try:
            info["trusted"] = bool(self._props_iface.Get(DEVICE_INTERFACE, "Trusted"))
        except (dbus.exceptions.DBusException, KeyError):
            info["trusted"] = None
            
        try:
            info["blocked"] = bool(self._props_iface.Get(DEVICE_INTERFACE, "Blocked"))
        except (dbus.exceptions.DBusException, KeyError):
            info["blocked"] = None
            
        try:
            info["services_count"] = len(self.services_resolved(skip_device_type_check=True))
        except:
            info["services_count"] = 0
            
        return info

# Legacy device_address property implementation
def _get_dev_addr(self):  # type: ignore[override]
    """Legacy getter for device_address."""
    return self.mac_address

def _set_dev_addr(self, value: str):  # type: ignore[override]
    """Legacy setter for device_address."""
    self.mac_address = value

# Add the property to the class
system_dbus__bluez_device__low_energy.device_address = property(_get_dev_addr, _set_dev_addr)
