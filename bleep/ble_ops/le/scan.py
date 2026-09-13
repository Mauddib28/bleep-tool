"""Passive BLE scan operation – native implementation only.

The function now relies exclusively on the refactored `bleep.dbuslayer` stack
and requires GI/PyGObject + BlueZ at runtime.  All legacy monolith fallback
code has been removed.

Scan *variants* implemented here (in increasing chattiness):

* passive_scan – BlueZ default DuplicateData=false (duplicate suppression on).
* naggy_scan   – Merged filter with DuplicateData=true so BlueZ emits every
                  ManufacturerData/ServiceData change (when the controller allows).
* pokey_scan   – Repeated 1-second *naggy* scans (stop/start discovery) to
                  coerce extra advertising.  Optional colonized Pattern hammers a
                  specific device (fewer HCI events, quicker); client-side MAC
                  filtering remains authoritative.
* brute_scan   – Combination BR/EDR + LE phases – loudest footprint.
"""

from __future__ import annotations

# Attempt to import the new dbuslayer stack.  If *gi* bindings / BlueZ are not
# available we abort early – historic monolith fallback has been removed.

try:
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    _HAS_NATIVE_STACK = True
except Exception:  # noqa: BLE001 – missing GI bindings / BlueZ runtime
    _HAS_NATIVE_STACK = False

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.core.errors import NotSupportedError
from bleep.core.constants import (
    BT_DEVICE_TYPE_UNKNOWN,
    BT_DEVICE_TYPE_CLASSIC, 
    BT_DEVICE_TYPE_LE,
    BT_DEVICE_TYPE_DUAL
)
import json as _json
from typing import Any, Dict, Optional


def _colonize_pattern(value: str) -> str:
    """Normalize a MAC/OUI prefix for BlueZ ``Pattern`` (prefer colonized form)."""
    p = str(value).strip()
    if all(c in "0123456789abcdefABCDEF:" for c in p) and ":" in p:
        return p.upper()
    # Digits-only OUI/MAC fragments → insert colons every two hex digits when even length.
    hex_only = "".join(c for c in p if c in "0123456789abcdefABCDEF")
    if hex_only and len(hex_only) % 2 == 0 and len(hex_only) >= 2 and hex_only == p.replace(":", ""):
        return ":".join(hex_only[i : i + 2].upper() for i in range(0, len(hex_only), 2))
    return p


def _json_compact(obj: Any) -> str:
    """JSON-encode for DB storage — compact, no ASCII escapes."""
    try:
        return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return "{}"


def _native_scan(
    device: str | None,
    timeout: int,
    transport: str = "auto",
    quiet: bool = False,
    *,
    filter_record: bool = False,
    duplicate_data: Optional[bool] = None,
    pattern: Optional[str] = None,
    adapter_name: str | None = None,
) -> int:
    """Perform a simple LE discovery using the refactored stack.

    When *device* is supplied, results are filtered client-side to that MAC
    (BlueZ ``SetDiscoveryFilter`` has no address key, so filtering must be applied
    to results — see ``org.bluez.Adapter``). The filter always narrows console
    output and the returned dict; database persistence is narrowed only when
    *filter_record* is True (otherwise all discovered devices are still recorded).

    Discovery uses exactly one merged ``SetDiscoveryFilter`` via the device
    manager (Transport plus optional DuplicateData/Pattern).

    *adapter_name* selects the BlueZ controller (e.g. ``"hci1"``); ``None`` keeps
    the default (``ADAPTER_NAME``). Callers that need adapter readiness surfaced
    with a non-zero exit should pre-check via ``core.preflight.require_adapter``
    (the CLI ``scan`` dispatch does this) — this function binds the manager to
    the requested adapter but does not itself gate on readiness.
    """

    adapter = _Adapter(adapter_name) if adapter_name else _Adapter()
    manager = adapter.create_device_manager()

    # BlueZ performs a broadcast discovery (its SetDiscoveryFilter has no address
    # key); any ``device`` narrowing is applied client-side to the results below.
    # Optional Pattern is an optimization only — client filter remains authoritative.
    manager.start_discovery(
        timeout=timeout,
        transport=transport,
        duplicate_data=duplicate_data,
        pattern=pattern,
    )
    manager.run()  # blocks until timeout; _timeout harvests before StopDiscovery (R1)
    raw = manager.take_last_harvest()

    # Client-side address filtering. ``view`` drives console output and the
    # returned dict; ``persist_src`` drives DB recording (full set unless the
    # caller explicitly narrows persistence via ``filter_record``).
    if device:
        _want = device.strip().upper()
        view = [e for e in raw if str(e.get("address", "")).upper() == _want]
    else:
        view = raw
    persist_src = view if (device and filter_record) else raw

    # Only print output if not in quiet mode
    if not quiet:
        if not view:
            # F5: distinguish "nothing was in range" from "devices were seen but
            # none matched the -d/--device filter" so an empty result under a filter
            # is not misread as a dead scan.
            if device:
                print_and_log(
                    f"[*] No device matching {device} found "
                    f"({len(raw)} other device(s) discovered)",
                    LOG__GENERAL,
                )
            else:
                print_and_log("[*] No BLE devices discovered", LOG__GENERAL)
        else:
            print_and_log(f"[*] Discovered {len(view)} device(s)", LOG__GENERAL)

            for entry in view:
                addr = entry.get("address", "??")
                name = entry.get("name") or entry.get("alias") or "?"
                rssi_val = entry.get("rssi")
                # #12: surface BlueZ's reported address type — LE peers are
                # frequently 'random' (resolvable-private) addresses, and
                # showing it helps explain identity churn across scans.
                atype = entry.get("address_type")
                atype_disp = f" [{atype}]" if atype else ""
                # N4: BlueZ reports ``Address`` as the *Identity Address after
                # pairing* (org.bluez.Device.rst:226), so a bonded device seen via
                # a resolvable-private address yields a second D-Bus object whose
                # path encodes the RPA but whose ``Address`` equals the identity.
                # That makes two distinct objects print as an identical line.
                # Rather than de-dupe (which would hide the RPA↔identity linkage),
                # surface the path/adv MAC when it differs from the resolved Address.
                _path = entry.get("path") or ""
                _path_mac = _path.rsplit("/dev_", 1)[-1].replace("_", ":").upper() if "/dev_" in _path else ""
                ident_disp = (
                    f" [identity; adv/RPA {_path_mac}]"
                    if _path_mac and _path_mac != str(addr).upper()
                    else ""
                )
                beacon_disp = ""
                try:
                    from bleep.analysis.adv_dissect import (
                        dissect_advertisement,
                        format_beacon_summary,
                    )
                    _summary = format_beacon_summary(
                        dissect_advertisement(
                            manufacturer_data=entry.get("manufacturer_data"),
                            service_data=entry.get("service_data"),
                            service_uuids=entry.get("uuids") or [],
                            advertising_data=entry.get("advertising_data"),
                        )
                    )
                    if _summary:
                        beacon_disp = f" {_summary}"
                except Exception:  # noqa: BLE001 - display enrichment must not break scanning
                    beacon_disp = ""
                # #10/#11: a missing RSSI means BlueZ has the device cached but it
                # is not advertising right now — tag it (and note any existing
                # bond) so it isn't mistaken for a freshly-seen device whose RSSI
                # read merely failed.
                if rssi_val is not None:
                    print_and_log(
                        f"  {addr} ({name}){atype_disp}{ident_disp} - RSSI: {rssi_val} dBm{beacon_disp}",
                        LOG__GENERAL,
                    )
                else:
                    tag = "bonded, cached" if (entry.get("bonded") or entry.get("paired")) else "cached, not advertising"
                    print_and_log(
                        f"  {addr} ({name}){atype_disp}{ident_disp} - RSSI: n/a [{tag}]{beacon_disp}",
                        LOG__GENERAL,
                    )
    
    # Always update observations if available
    if persist_src and _obs:
        from bleep.analysis.device_type_classifier import DeviceTypeClassifier
        classifier = DeviceTypeClassifier()  # Create once, reuse for all devices
        
        for entry in persist_src:
            addr = entry.get("address", "??")
            if addr == "??":
                continue
                
            name = entry.get("name") or entry.get("alias") or "?"
            rssi_val = entry.get("rssi")
            addr_type = entry.get("address_type")
            device_class = entry.get("device_class")
            
            try:
                device_info = {
                    'name': name,
                    'rssi_last': rssi_val,
                    'addr_type': addr_type,
                }

                # Seed rssi_min/rssi_max so the DB can track the observed range
                if rssi_val is not None:
                    device_info['rssi_min'] = rssi_val
                    device_info['rssi_max'] = rssi_val

                if device_class is not None:
                    device_info['device_class'] = device_class

                # v10 enrichment from adapter discovery data
                if entry.get("tx_power") is not None:
                    device_info['tx_power'] = int(entry["tx_power"])
                if entry.get("appearance") is not None:
                    device_info['appearance'] = int(entry["appearance"])
                if entry.get("modalias"):
                    device_info['modalias'] = str(entry["modalias"])
                if entry.get("icon"):
                    device_info['icon'] = str(entry["icon"])
                if entry.get("manufacturer_data"):
                    # Pick the entry with the longest payload (most informative)
                    best_key, best_val = None, b''
                    for mfr_key, mfr_val in entry["manufacturer_data"].items():
                        val_bytes = bytes(mfr_val)
                        if len(val_bytes) >= len(best_val):
                            best_key, best_val = mfr_key, val_bytes
                    if best_key is not None:
                        device_info['manufacturer_id'] = int(best_key)
                        device_info['manufacturer_data'] = best_val
                if entry.get("service_data"):
                    device_info['service_data'] = _json_compact(
                        {k: v.hex() if isinstance(v, bytes) else str(v)
                         for k, v in entry["service_data"].items()}
                    )
                if entry.get("advertising_data"):
                    device_info['advertising_data'] = _json_compact(
                        {str(k): v.hex() if isinstance(v, bytes) else str(v)
                         for k, v in entry["advertising_data"].items()}
                    )

                # P2-B10: persist advertised UUIDs
                adv_uuids = entry.get("uuids", [])
                if adv_uuids:
                    device_info['uuids'] = adv_uuids

                # P2-B11: persist connection state booleans when available
                if entry.get("paired") is not None:
                    device_info['paired'] = bool(entry["paired"])
                if entry.get("trusted") is not None:
                    device_info['trusted'] = bool(entry["trusted"])
                if entry.get("bonded") is not None:
                    device_info['bonded'] = bool(entry["bonded"])

                _obs.upsert_device(addr, **device_info)

                # P2-B8: persist raw advertisement report
                if rssi_val is not None:
                    adv_raw = entry.get("advertising_data") or {}
                    adv_blob = b''
                    if adv_raw:
                        for _ad_type, _ad_val in adv_raw.items():
                            adv_blob += bytes(_ad_val) if isinstance(_ad_val, (bytes, bytearray)) else b''
                    decoded = {}
                    if adv_uuids:
                        decoded["uuids"] = adv_uuids
                    if entry.get("manufacturer_data"):
                        decoded["manufacturer_data"] = {
                            str(k): bytes(v).hex() for k, v in entry["manufacturer_data"].items()
                        }
                    if entry.get("service_data"):
                        decoded["service_data"] = {
                            k: bytes(v).hex() if isinstance(v, (bytes, bytearray)) else str(v)
                            for k, v in entry["service_data"].items()
                        }
                    if entry.get("tx_power") is not None:
                        decoded["tx_power"] = entry["tx_power"]
                    # G-7.5: structured, attributed, lossless dissection of the
                    # advertisement fields. Additive only — never blocks the scan.
                    try:
                        from bleep.analysis.adv_dissect import dissect_advertisement
                        dissection = dissect_advertisement(
                            manufacturer_data=entry.get("manufacturer_data"),
                            service_data=entry.get("service_data"),
                            service_uuids=adv_uuids,
                            advertising_data=entry.get("advertising_data"),
                        )
                        if any(dissection.get(k) for k in
                               ("manufacturer_data", "service_data", "service_uuids", "advertising_data")):
                            decoded["adv_dissection"] = dissection
                    except Exception:  # noqa: BLE001 - enrichment must not break scanning
                        pass
                    _obs.insert_adv(addr, rssi_val, adv_blob, decoded, adapter=adapter_name)

                # STEP 2: NOW perform classification with database cache enabled
                # Device exists in DB, so foreign key constraints will be satisfied
                context = {
                    "device_class": device_class,
                    "address_type": addr_type,
                    "uuids": adv_uuids,
                    "connected": entry.get("connected", False),
                    "service_data": entry.get("service_data", {}),
                    "advertising_data": entry.get("advertising_data", {}),
                    "manufacturer_data": entry.get("manufacturer_data", {}),
                }
                
                result = classifier.classify_with_mode(
                    mac=addr,
                    context=context,
                    scan_mode="passive",
                    use_database_cache=True
                )
                
                # STEP 3: Update device with classified device_type
                _obs.upsert_device(addr, device_type=result.device_type)
                
            except Exception as e:
                # Preserve behavior (continue scanning) but include structured
                # D-Bus diagnostics when applicable.
                if hasattr(e, "get_dbus_name") and hasattr(e, "get_dbus_message"):
                    print_and_log(
                        f"[-] Error processing device {addr}: {e.get_dbus_name()}: {e.get_dbus_message() or ''}",
                        LOG__DEBUG,
                    )
                else:
                    print_and_log(f"[-] Error processing device {addr}: {e}", LOG__DEBUG)

    # Convert filtered device list to dictionary format expected by higher-level code
    devices = {}
    for entry in view:
        addr = entry.get("address", "??")
        if addr != "??":
            # LR-2c: fingerprint_rotated_in_round is attached during manager harvest
            # (R1). Retain a best-effort pop for legacy GMO fallback paths.
            if "fingerprint_rotated_in_round" not in entry:
                try:
                    _p = entry.get("path") or ""
                    pop_mac = (
                        _p.rsplit("/dev_", 1)[-1].replace("_", ":").upper()
                        if "/dev_" in _p
                        else str(addr).upper()
                    )
                    entry["fingerprint_rotated_in_round"] = manager.pop_fingerprint_rotated(pop_mac)
                except Exception:  # noqa: BLE001 - enrichment must never break scanning
                    pass
            devices[addr] = entry
    
    print_and_log(f"[DEBUG] _native_scan returning {len(devices)} devices", LOG__DEBUG)
    
    return devices


# ---------------------------------------------------------------------------
# Legacy monolith loader *removed* – the following helpers have been deleted:
#   * _load_monolith()
#   * _legacy_scan()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Back-compat helper wrappers – thin shims around *passive_scan*
# ---------------------------------------------------------------------------

def create_and_return__bluetooth_scan__discovered_devices(
    *, timeout: int = 10, adapter_name: str | None = None, transport: str = "auto"
) -> list[dict]:
    """Return the list of discovered device dictionaries (address, name, rssi,…).

    This preserves the public contract of the legacy helper while relying solely
    on the refactored *dbuslayer* stack.  **No monolith code is imported.**
    """
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    adapter = _Adapter(adapter_name) if adapter_name else _Adapter()
    manager = adapter.create_device_manager()
    manager.start_discovery(timeout=timeout, transport=transport)
    manager.run()
    return manager.take_last_harvest()


def create_and_return__bluetooth_scan__discovered_devices__specific_adapter(
    bluetooth_adapter: str, *, timeout: int = 10, transport: str = "auto"
) -> list[dict]:
    """Explicit adapter variant kept for callers that pass *hciX* manually."""
    return create_and_return__bluetooth_scan__discovered_devices(
        timeout=timeout,
        adapter_name=bluetooth_adapter,
        transport=transport,
    )


# ---------------------------------------------------------------------------
# Enumeration wrappers (passive_enum / naggy_enum / pokey_enum / brute_enum)
# ---------------------------------------------------------------------------

from bleep.ble_ops.le.enum_helpers import multi_read_all, brute_write_range
from typing import Dict, Any

# Optional import of observation DB helper (may fail on minimal systems)
try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None


def _enrich_device_info_from_props(device_info: Dict[str, Any], props: dict) -> None:
    """Merge v10 device columns from a Device1 D-Bus property dict (CamelCase keys)."""
    if not props:
        return
    if "RSSI" in props and "rssi_last" not in device_info:
        device_info["rssi_last"] = int(props["RSSI"])
    if "AddressType" in props and "addr_type" not in device_info:
        device_info["addr_type"] = str(props["AddressType"])
    if "Class" in props and "device_class" not in device_info:
        device_info["device_class"] = int(props["Class"])
    if "Appearance" in props and "appearance" not in device_info:
        device_info["appearance"] = int(props["Appearance"])
    if "TxPower" in props:
        device_info["tx_power"] = int(props["TxPower"])
    if "Modalias" in props:
        device_info["modalias"] = str(props["Modalias"])
    if "Icon" in props:
        device_info["icon"] = str(props["Icon"])
    if "ManufacturerData" in props and "manufacturer_id" not in device_info:
        for mfr_key in props["ManufacturerData"]:
            device_info["manufacturer_id"] = int(mfr_key)
            device_info["manufacturer_data"] = bytes(props["ManufacturerData"][mfr_key])
            break
    if "ServiceData" in props:
        device_info["service_data"] = _json_compact(
            {str(k): bytes(v).hex() for k, v in props["ServiceData"].items()}
        )
    if "AdvertisingData" in props:
        device_info["advertising_data"] = _json_compact(
            {str(k): bytes(v).hex() for k, v in props["AdvertisingData"].items()}
        )
    # P2-B11: connection state booleans
    if "Paired" in props:
        device_info["paired"] = bool(props["Paired"])
    if "Trusted" in props:
        device_info["trusted"] = bool(props["Trusted"])
    if "Bonded" in props:
        device_info["bonded"] = bool(props["Bonded"])
    if "UUIDs" in props and "uuids" not in device_info:
        device_info["uuids"] = [str(u) for u in props["UUIDs"]]


def _persist_mapping(mac: str, mapping: Dict[str, Any]):
    """Persist services & characteristics to observation DB (safe/no-crash)."""
    if not _obs:
        return
    try:
        svc_list = []
        
        # Support different mapping structures (original and gatt-enum format)
        if "Services" in mapping:  # Handle gatt-enum JSON format
            mapping = mapping.get("Services", {})
            
        # Support format from enum-scan functions where the mapping is inside "mapping" key
        elif "mapping" in mapping:
            mapping = mapping.get("mapping", {})
            
        for svc_uuid, svc_data in mapping.items():
            if not isinstance(svc_data, dict):
                # Log the unexpected service data type for debugging
                print_and_log(
                    f"[DEBUG] Non-dictionary service data for {svc_uuid}: {type(svc_data).__name__}={svc_data!r}",
                    LOG__DEBUG
                )
                svc_list.append({
                    "uuid": svc_uuid,
                    "name": None,
                    "handle_start": None,
                    "handle_end": None,
                })
            else:
                svc_entry = {
                    "uuid": svc_uuid,
                    "name": svc_data.get("name"),
                    "handle_start": svc_data.get("start_handle"),
                    "handle_end": svc_data.get("end_handle"),
                }
                if "Primary" in svc_data:
                    svc_entry["is_primary"] = svc_data["Primary"]
                if "Includes" in svc_data:
                    svc_entry["includes"] = svc_data["Includes"]
                svc_list.append(svc_entry)
        
        uuid_to_id = _obs.upsert_services(mac, svc_list)  # type: ignore[attr-defined]
        
        # characteristics
        characteristic_count = 0
        for svc_uuid, svc_data in mapping.items():
            sid = uuid_to_id.get(svc_uuid)
            if not sid:
                continue
            
            char_list = []
            
            # Check if svc_data is a dictionary
            if not isinstance(svc_data, dict):
                # Already logged above, skip this service
                continue
                
            # Support multiple formats of characteristic data
            chars_data = None
            
            # Standard format with "chars" key
            if "chars" in svc_data:
                chars_data = svc_data.get("chars", {})
            
            # gatt-enum format with "Characteristics" key
            elif "Characteristics" in svc_data:
                chars_data = svc_data.get("Characteristics", {})
            
            # For enum-scan format, the characteristic UUID might be directly stored as the value
            elif isinstance(svc_data, str):
                # For this format, we can only store the UUID, not properties or values
                chars_data = {svc_data: {}}
            
            # If no characteristics found in any format
            if not chars_data:
                continue
                
            for char_uuid, char_data in chars_data.items():
                # Add type checking before accessing dictionary methods
                if not isinstance(char_data, dict):
                    # Log the unexpected characteristic data type for debugging
                    char_list.append({
                        "uuid": char_uuid,
                        "handle": None,
                        "properties": [],
                        "value": None,
                    })
                else:
                    # Support both property formats (legacy and gatt-enum)
                    props = []
                    if "properties" in char_data:
                        props = list(char_data.get("properties", {}).keys())
                    elif "Flags" in char_data:
                        props = char_data.get("Flags", [])
                        
                    # Support both handle formats
                    handle = None
                    if "handle" in char_data:
                        handle = char_data.get("handle")
                    elif "Handle" in char_data:
                        # Handle format conversion from hex string to integer if needed
                        handle_val = char_data.get("Handle")
                        if isinstance(handle_val, str) and handle_val.startswith("0x"):
                            try:
                                handle = int(handle_val, 16)
                            except ValueError:
                                handle = None
                        else:
                            handle = handle_val
                        
                    # Support both value formats
                    value = None
                    if "value" in char_data:
                        value = char_data.get("value")
                    elif "Value" in char_data:
                        value = char_data.get("Value")
                        # If value is a string but Raw data is available, use Raw instead
                        if isinstance(value, str) and "Raw" in char_data:
                            raw_val = char_data.get("Raw")
                            # Try to convert Raw from string representation of a list to bytes
                            if isinstance(raw_val, str) and raw_val.startswith("[") and raw_val.endswith("]"):
                                try:
                                    # Parse the string representation of a list into actual bytes
                                    raw_list = eval(raw_val)
                                    if isinstance(raw_list, list):
                                        value = bytes(raw_list)
                                except Exception:
                                    # If parsing fails, keep the original Value
                                    pass
                    
                    char_entry = {
                        "uuid": char_uuid,
                        "handle": handle,
                        "properties": props,
                        "value": value,
                    }
                    mtu = char_data.get("MTU") or char_data.get("mtu") if isinstance(char_data, dict) else None
                    if mtu is not None:
                        char_entry["mtu"] = mtu
                    char_list.append(char_entry)
                    characteristic_count += 1

            if char_list:
                _obs.upsert_characteristics(sid, char_list, mac=mac, service_uuid=svc_uuid)  # type: ignore[attr-defined]

                # Persist descriptors for each characteristic if present
                for char_uuid_d, char_data_d in chars_data.items():
                    if not isinstance(char_data_d, dict):
                        continue
                    desc_data = char_data_d.get("Descriptors") or char_data_d.get("descriptors")
                    if not desc_data or not isinstance(desc_data, dict):
                        continue
                    char_id = _obs.get_characteristic_id(sid, char_uuid_d)
                    if not char_id:
                        continue
                    desc_list = []
                    for desc_uuid, desc_entry in desc_data.items():
                        d_info = {"uuid": desc_uuid}
                        if isinstance(desc_entry, dict):
                            d_info["value"] = desc_entry.get("Value") or desc_entry.get("value")
                            d_info["handle"] = desc_entry.get("Handle") or desc_entry.get("handle")
                            d_info["flags"] = desc_entry.get("Flags") or desc_entry.get("flags")
                        desc_list.append(d_info)
                    if desc_list:
                        _obs.upsert_descriptors(char_id, desc_list)
                
        # Ensure changes are committed to database
        if hasattr(_obs, "_DB_CONN") and _obs._DB_CONN is not None:
            _obs._DB_CONN.commit()
            
    except Exception as e:
        if hasattr(e, "get_dbus_name") and hasattr(e, "get_dbus_message"):
            print_and_log(
                f"[-] Error saving to database: {e.get_dbus_name()}: {e.get_dbus_message() or ''}",
                LOG__DEBUG,
            )
        else:
            print_and_log(f"[-] Error saving to database: {e}", LOG__DEBUG)
        import traceback
        print_and_log(f"[-] Traceback: {traceback.format_exc()}", LOG__DEBUG)


# DIS (Device Information Service) characteristic UUIDs — 128-bit canonical form
_DIS_SVC_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
_DIS_FIRMWARE_REV_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
_DIS_SOFTWARE_REV_UUID = "00002a28-0000-1000-8000-00805f9b34fb"
_DIS_PNP_ID_UUID = "00002a50-0000-1000-8000-00805f9b34fb"
_DIS_MODEL_NUMBER_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
_DIS_MANUFACTURER_UUID = "00002a29-0000-1000-8000-00805f9b34fb"


def _extract_dis_version_data(mac: str, mapping: Dict[str, Any]):
    """Extract version-related data from the GATT Device Information Service.

    If the DIS (0x180A) was discovered and characteristics read during BLE
    enumeration, persist firmware revision, software revision, and PnP ID
    to the device record in the observations DB.
    """
    if not _obs or not mapping:
        return

    # Locate DIS in the mapping (keys may be short or full 128-bit UUIDs)
    dis_data = None
    for svc_uuid, svc_data in mapping.items():
        if not isinstance(svc_data, dict):
            continue
        normalized = svc_uuid.lower().replace("_", "-")
        if normalized == _DIS_SVC_UUID or normalized == "0000180a" or normalized == "180a":
            dis_data = svc_data
            break

    if dis_data is None:
        return

    chars = dis_data.get("chars") or dis_data.get("Characteristics") or {}
    if not chars:
        return

    update_fields: Dict[str, Any] = {}

    for char_uuid, char_data in chars.items():
        if not isinstance(char_data, dict):
            continue
        normalized_char = char_uuid.lower().replace("_", "-")
        value = char_data.get("Value") or char_data.get("value")
        if not value:
            continue

        if normalized_char in (_DIS_FIRMWARE_REV_UUID, "00002a26", "2a26"):
            update_fields["firmware_revision"] = str(value).strip()
        elif normalized_char in (_DIS_SOFTWARE_REV_UUID, "00002a28", "2a28"):
            update_fields["software_revision"] = str(value).strip()
        elif normalized_char in (_DIS_PNP_ID_UUID, "00002a50", "2a50"):
            _parse_pnp_id(value, update_fields)
        elif normalized_char in (_DIS_MODEL_NUMBER_UUID, "00002a24", "2a24"):
            update_fields["model_number"] = str(value).strip()
        elif normalized_char in (_DIS_MANUFACTURER_UUID, "00002a29", "2a29"):
            update_fields["dis_manufacturer_name"] = str(value).strip()

    if update_fields:
        try:
            from bleep.core.time_utils import utc_now_iso
            update_fields["version_queried_at"] = utc_now_iso()
            _obs.upsert_device(mac, **update_fields)
        except Exception as exc:
            print_and_log(f"[-] DIS version persist failed: {exc}", LOG__DEBUG)


def _parse_pnp_id(value, fields: Dict[str, Any]):
    """Parse PnP ID characteristic value (7 bytes) into vendor/product/version."""
    try:
        if isinstance(value, str):
            raw = bytes.fromhex(value.replace(" ", "").replace(":", ""))
        elif isinstance(value, (list, tuple)):
            raw = bytes(value)
        elif isinstance(value, bytes):
            raw = value
        else:
            return

        if len(raw) < 7:
            return

        vendor_source = raw[0]
        vendor_id = int.from_bytes(raw[1:3], "little")
        product_id = int.from_bytes(raw[3:5], "little")
        product_version = int.from_bytes(raw[5:7], "little")

        fields["pnp_vendor_source"] = vendor_source
        fields["pnp_vendor_id"] = vendor_id
        fields["pnp_product_id"] = product_id
        fields["pnp_product_version"] = product_version
    except (ValueError, TypeError):
        pass


def _collect_device_props(device) -> dict:
    """Collect org.bluez.Device1 + auxiliary interface properties from D-Bus.

    Fetches Device1 props and also probes for Battery1 and Input1 interfaces
    on the same object path, merging them under reserved keys so downstream
    formatters can display battery level, reconnect mode, etc.
    """
    try:
        import dbus as _dbus
        bus = _dbus.SystemBus()
        obj = bus.get_object("org.bluez", device._device_path)
        pi = _dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        props = dict(pi.GetAll("org.bluez.Device1"))
    except Exception:
        return {}

    _AUX_INTERFACES = {
        "org.bluez.Battery1": "_Battery1",
        "org.bluez.Input1": "_Input1",
    }
    for iface, key in _AUX_INTERFACES.items():
        try:
            aux = dict(pi.GetAll(iface))
            if aux:
                props[key] = aux
        except Exception:
            pass

    return props


def _base_enum(target_bt_addr: str, *, deep: bool = False, adapter_name: str | None = None, skip_scan: bool = False):
    """Connect & enumerate, return (device, mapping, mine_map, perm_map, device_props).

    *adapter_name* selects the BlueZ controller (F5b); ``None`` keeps the default.
    *skip_scan* skips PRE-FLIGHT discovery when Device1 already exists on the adapter.
    """
    from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
    
    device, mapping, mine_map, perm_map = _connect_enum(
        target_bt_addr, deep_enumeration=deep, adapter_name=adapter_name, skip_scan=skip_scan
    )
    
    device_props = _collect_device_props(device)
    
    # Persist to observation DB if available
    if _obs:
        try:
            from bleep.analysis.device_type_classifier import DeviceTypeClassifier
            
            # Get device properties
            addr = device.get_address()
            name = device.get_name()
            addr_type = device.get_address_type() if hasattr(device, 'get_address_type') else None
            device_class = device.get_device_class() if hasattr(device, 'get_device_class') else None
            
            device_info: Dict[str, Any] = {
                'name': name,
                'addr_type': addr_type,
            }

            if device_class is not None:
                device_info['device_class'] = device_class

            # v10 enrichment from Device1 D-Bus properties
            _enrich_device_info_from_props(device_info, device_props)

            _obs.upsert_device(addr, **device_info)
            
            # STEP 2: Save services and characteristics (creates more classification evidence)
            _persist_mapping(addr, mapping)

            # STEP 2b: Extract Device Information Service version data if present
            _extract_dis_version_data(addr, mapping)
            
            # STEP 3: Perform classification with full context (including services)
            # Use 'naggy' mode since we just connected and enumerated
            classifier = DeviceTypeClassifier()
            
            # Get UUIDs from device if available
            uuids = []
            if hasattr(device, 'get_uuids'):
                try:
                    uuids = device.get_uuids() or []
                except Exception:
                    pass
            
            context = {
                "device_class": device_class,
                "address_type": addr_type,
                "uuids": uuids,
                "connected": True,
                "device": device,
                "gatt_services": list(mapping.keys()) if mapping else [],
                "service_data": device_props.get("ServiceData", {}),
                "advertising_data": device_props.get("AdvertisingData", {}),
                "manufacturer_data": device_props.get("ManufacturerData", {}),
            }
            
            result = classifier.classify_with_mode(
                mac=addr,
                context=context,
                scan_mode="naggy",  # More aggressive mode for connected devices
                use_database_cache=True
            )
            
            # STEP 4: Update with classified type
            _obs.upsert_device(addr, device_type=result.device_type)
            
        except Exception as e:
            if hasattr(e, "get_dbus_name") and hasattr(e, "get_dbus_message"):
                print_and_log(
                    f"[-] Error saving to database: {e.get_dbus_name()}: {e.get_dbus_message() or ''}",
                    LOG__DEBUG,
                )
            else:
                print_and_log(f"[-] Error saving to database: {e}", LOG__DEBUG)
    
    return device, mapping, mine_map, perm_map, device_props


def passive_enum(target_bt_addr: str, *, deep: bool = False, adapter_name: str | None = None, skip_scan: bool = False):
    device, mapping, mine_map, perm_map, device_props = _base_enum(
        target_bt_addr, deep=deep, adapter_name=adapter_name, skip_scan=skip_scan
    )
    return {"device": device, "mapping": mapping, "mine_map": mine_map, "perm_map": perm_map,
            "device_props": device_props}


def naggy_enum(target_bt_addr: str, *, deep: bool = False, adapter_name: str | None = None, skip_scan: bool = False):
    device, mapping, mine_map, perm_map, device_props = _base_enum(
        target_bt_addr, deep=deep, adapter_name=adapter_name, skip_scan=skip_scan
    )
    multi = multi_read_all(device, mapping=mapping, rounds=3)

    # Update mapping with the most recent value from multi-read and detect changes
    changed_chars: set[str] = set()
    last_round = max(multi.keys()) if multi else 0
    if last_round:
        latest = multi[last_round]
        for svc_uuid, svc_data in mapping.items():
            chars = svc_data.get("chars", {})
            for char_uuid, char_data in chars.items():
                label = char_data.get("label", char_uuid)
                val = latest.get(label)
                if isinstance(val, (bytes, bytearray)):
                    from bleep.ble_ops.common.conversion import convert__hex_to_ascii
                    ascii_val = convert__hex_to_ascii(val)
                    if not ascii_val.strip() or "\ufffd" in ascii_val:
                        ascii_val = None
                    char_data["value"] = ascii_val
                    char_data["raw"] = list(val)

        # Detect changes across rounds
        for label in latest:
            values_across_rounds = []
            for r in sorted(multi.keys()):
                v = multi[r].get(label)
                if isinstance(v, (bytes, bytearray)):
                    values_across_rounds.append(v)
            if len(set(values_across_rounds)) > 1:
                changed_chars.add(label)

    return {
        "device": device,
        "mapping": mapping,
        "multi_read": multi,
        "mine_map": mine_map,
        "perm_map": perm_map,
        "changed_chars": changed_chars,
        "device_props": device_props,
    }


def pokey_enum(
    target_bt_addr: str,
    *,
    rounds: int = 3,
    verify: bool = False,
    adapter_name: str | None = None,
    skip_scan: bool = False,
):
    """Enumerate with light write-probes (0/1) after each round."""
    results = {}
    device_obj: Any | None = None
    mine_map: Any | None = None
    perm_map: Any | None = None
    device_props: dict = {}
    for r in range(rounds):
        print_and_log(f"[*] Pokey enum round {r+1}/{rounds}", LOG__GENERAL)
        device, mapping, mine_map, perm_map, device_props = _base_enum(
            target_bt_addr, deep=False, adapter_name=adapter_name, skip_scan=skip_scan
        )
        device_obj = device
        from bleep.ble_ops.le.enum_helpers import small_write_probe
        small_write_probe(device, mapping, verify=verify)
        results[r + 1] = mapping
    return {
        "device": device_obj,
        "mapping": results[max(results.keys())] if results else {},
        "rounds": results,
        "mine_map": mine_map,
        "perm_map": perm_map,
        "device_props": device_props,
    }


def brute_enum(
    target_bt_addr: str,
    *,
    write_char: str,
    value_range: tuple[int, int] | None = (0x00, 0xFF),
    patterns: list[str] | None = None,
    payload_file: bytes | None = None,
    force: bool = False,
    verify: bool = False,
    deep: bool = False,
    adapter_name: str | None = None,
    skip_scan: bool = False,
):
    device, mapping, mine_map, perm_map, device_props = _base_enum(
        target_bt_addr, deep=deep, adapter_name=adapter_name, skip_scan=skip_scan
    )

    from typing import Any
    from bleep.ble_ops.le.enum_helpers import build_payload_iterator

    payloads = build_payload_iterator(value_range=value_range, patterns=patterns, file_bytes=payload_file)
    from bleep.ble_ops.le.enum_helpers import multi_write_all

    if write_char.lower() == "all":
        write_result = multi_write_all(
            device,
            mapping,
            payloads=payloads,
            verify=verify,
            respect_roeng=not force,
            landmine_map=mine_map,
        )
    else:
        write_result = brute_write_range(
            device,
            write_char,
            payloads=payloads,
            verify=verify,
            respect_roeng=not force,
            landmine_map=mine_map,
        )

    return {
        "device": device,
        "mapping": mapping,
        "mine_map": mine_map,
        "perm_map": perm_map,
        "device_props": device_props,
    }

# Public export list -----------------------------------------------------------------------------
__all__ = [
    "passive_scan",
    "naggy_scan",
    "pokey_scan",
    "brute_scan",
    "create_and_return__bluetooth_scan__discovered_devices",
    "create_and_return__bluetooth_scan__discovered_devices__specific_adapter",
]
__all__ += [
    "passive_enum",
    "naggy_enum",
    "pokey_enum",
    "brute_enum",
]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def passive_scan(device: str | None = None, timeout: int = 60, transport: str = "auto", quiet: bool = False, *, filter_record: bool = False, adapter_name: str | None = None):  # noqa: D401
    """Execute a passive BLE scan.

    Parameters
    ----------
    device
        Optional MAC address to filter results to (client-side; see ``_native_scan``).
    filter_record
        When True *and* *device* is set, restrict database recording to the target
        device as well (default records all discovered devices).
    timeout
        Duration in seconds for the discovery main-loop.
    transport
        Bluetooth transport filter: "auto" (default), "le" (Low Energy), or "bredr" (Classic).
    quiet
        If True, suppress console output during scanning.
    adapter_name
        Optional BlueZ controller name (e.g. ``"hci1"``); ``None`` keeps the
        default (``ADAPTER_NAME``).
    """

    if not _HAS_NATIVE_STACK:
        raise NotSupportedError(
            "passive_scan (PyGObject/BlueZ bindings not available – requires a "
            "native environment after monolith fallback removal)"
        )

    return _native_scan(device, timeout, transport, quiet, filter_record=filter_record, adapter_name=adapter_name)


# ---------------------------------------------------------------------------
# Extended scan modes (naggy / pokey / brute)
# ---------------------------------------------------------------------------


def naggy_scan(
    device: str | None = None,
    timeout: int = 60,
    transport: str = "auto",
    *,
    filter_record: bool = False,
    pattern: str | None = None,
    adapter_name: str | None = None,
):
    """Active scan with DuplicateData=true in one merged discovery filter.

    *adapter_name* selects the BlueZ controller; ``None`` keeps the default.
    """
    if not _HAS_NATIVE_STACK:
        raise NotSupportedError("naggy_scan (GI/BlueZ runtime missing)")

    return _native_scan(
        device,
        timeout,
        transport,
        filter_record=filter_record,
        duplicate_data=True,
        pattern=pattern,
        adapter_name=adapter_name,
    )


def pokey_scan(
    target_mac: str | None = None,
    *,
    timeout: int = 30,
    transport: str = "auto",
    adapter_name: str | None = None,
):
    """Rapid-fire active scan loop ("pokey mode").

    Rationale
    ---------
    • BlueZ emits *InterfacesAdded* only when discovery *stops*.
    • A long 30-s scan therefore gives you **one** event per device.
    • Restarting discovery every second forces BlueZ to flush its cache →
      many events per interval → *pokes* devices into revealing transient
      adverts (e.g. privacy-rotating MACs, button-triggered beacons).

    target_mac (optional)
    ---------------------
    When supplied, each naggy round merges a colonized BlueZ ``Pattern`` into
    the single discovery filter as an optimization. Client-side MAC filtering
    remains authoritative.

    *transport* and *adapter_name* are threaded into every inner naggy round so
    each round hits the same controller/transport (F5).
    """
    if not _HAS_NATIVE_STACK:
        raise NotSupportedError("pokey_scan (GI/BlueZ runtime missing)")

    import time as _time
    end_time = _time.monotonic() + timeout
    rounds = 0
    pattern = _colonize_pattern(target_mac) if target_mac else None

    while _time.monotonic() < end_time:
        rounds += 1
        print_and_log(f"[*] Pokey round {rounds}", LOG__DEBUG)
        naggy_scan(
            target_mac if target_mac else None,
            timeout=1,
            transport=transport,
            pattern=pattern,
            adapter_name=adapter_name,
        )
    return 0


def brute_scan(timeout: int = 30, *, adapter_name: str | None = None):
    """Full BR/EDR + LE sweep (loudest).

    Both phases run on the same controller when *adapter_name* is given (F5);
    ``None`` keeps the default. ``transport`` is intrinsic to brute (BR/EDR then
    LE) and is therefore not a parameter.
    """
    if not _HAS_NATIVE_STACK:
        raise NotSupportedError("brute_scan (GI/BlueZ runtime missing)")

    half = max(1, timeout // 2)
    print_and_log("[*] Brute scan – BR/EDR phase", LOG__GENERAL)
    _native_scan(None, half, transport="bredr", adapter_name=adapter_name)
    print_and_log("[*] Brute scan – LE active phase", LOG__GENERAL)
    naggy_scan(None, half, transport="le", adapter_name=adapter_name)
    return 0
