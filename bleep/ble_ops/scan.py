"""Passive BLE scan operation – native implementation only.

The function now relies exclusively on the refactored `bleep.dbuslayer` stack
and requires GI/PyGObject + BlueZ at runtime.  All legacy monolith fallback
code has been removed.

Scan *variants* implemented here (in increasing chattiness):

* passive_scan – BlueZ default: DuplicateData=True, respects interval hints.
* naggy_scan   – Same filter but DuplicateData=False so we get **every** adv.
* pokey_scan   – Repeated 1-second *naggy* scans (stop/start discovery) to
                  coerce extra advertising.  Optional Address filter hammers a
                  specific device (fewer HCI events, quicker).  Inspired by
                  behaviour in the golden-template monolith.
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
from bleep.core.constants import (
    BT_DEVICE_TYPE_UNKNOWN,
    BT_DEVICE_TYPE_CLASSIC, 
    BT_DEVICE_TYPE_LE,
    BT_DEVICE_TYPE_DUAL
)
from typing import Any, Dict


def _native_scan(device: str | None, timeout: int, transport: str = "auto", quiet: bool = False) -> int:
    """Perform a simple LE discovery using the refactored stack."""

    adapter = _Adapter()
    
    # Apply transport filter if explicitly requested
    if transport.lower() in {"le", "bredr"}:
        adapter.set_discovery_filter({"Transport": transport.lower()})
    
    manager = adapter.create_device_manager()

    # In this first rewrite we ignore *device* filtering; higher-level code
    # expects a *passive* broadcast scan.
    manager.start_discovery(timeout=timeout)
    manager.run()  # blocks until timeout expires

    raw = adapter.get_discovered_devices()

    # Only print output if not in quiet mode
    if not quiet:
        if not raw:
            print_and_log("[*] No BLE devices discovered", LOG__GENERAL)
        else:
            print_and_log(f"[*] Discovered {len(raw)} device(s)", LOG__GENERAL)

            for entry in raw:
                addr = entry.get("address", "??")
                name = entry.get("name") or entry.get("alias") or "?"
                rssi_val = entry.get("rssi")
                rssi_disp = rssi_val if rssi_val is not None else "?"
                rssi_display = f"{rssi_disp} dBm" if rssi_disp != "?" else "? dBm"
                print_and_log(f"  {addr} ({name}) - RSSI: {rssi_display}", LOG__GENERAL)
    
    # Always update observations if available
    if raw and _obs:
        for entry in raw:
            addr = entry.get("address", "??")
            name = entry.get("name") or entry.get("alias") or "?"
            rssi_val = entry.get("rssi")
            device_type = entry.get("type")
            
            # Extract device information
            addr_type = entry.get("address_type")
            device_type = entry.get("device_type", BT_DEVICE_TYPE_UNKNOWN)
            
            # Fallback logic if address_type is not available but device is LE
            if not addr_type and device_type == BT_DEVICE_TYPE_LE:
                addr_type = "random" if entry.get("address", "").startswith("random") else "public"
                
            try:
                # Store all device information in the database
                _obs.upsert_device(
                    addr, 
                    name=name, 
                    rssi_last=rssi_val, 
                    addr_type=addr_type,
                    device_type=device_type
                )
            except Exception:
                pass

    # Convert raw device list to dictionary format expected by higher-level code
    devices = {}
    for entry in raw:
        addr = entry.get("address", "??")
        if addr != "??":
            devices[addr] = entry
    
    print_and_log(f"[DEBUG] _native_scan returning {len(devices)} devices", LOG__GENERAL)
    
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

    # Apply transport filter if explicitly requested
    if transport.lower() in {"le", "bredr"}:
        adapter.set_discovery_filter({"Transport": transport.lower()})

    manager = adapter.create_device_manager()
    manager.start_discovery(timeout=timeout)
    manager.run()

    return adapter.get_discovered_devices()


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

from bleep.ble_ops.enum_helpers import multi_read_all, brute_write_range
from typing import Dict, Any

# Optional import of observation DB helper (may fail on minimal systems)
try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None


def _persist_mapping(mac: str, mapping: Dict[str, Any]):
    """Persist services & characteristics to observation DB (safe/no-crash)."""
    if not _obs:
        return
    try:
        svc_list = []
        for svc_uuid, svc_data in mapping.items():
            svc_list.append({
                "uuid": svc_uuid,
                "name": svc_data.get("name"),
                "handle_start": svc_data.get("start_handle"),
                "handle_end": svc_data.get("end_handle"),
            })
        uuid_to_id = _obs.upsert_services(mac, svc_list)  # type: ignore[attr-defined]
        # characteristics
        for svc_uuid, svc_data in mapping.items():
            sid = uuid_to_id.get(svc_uuid)
            if not sid:
                continue
            char_list = []
            for char_uuid, char_data in svc_data.get("chars", {}).items():
                char_list.append({
                    "uuid": char_uuid,
                    "handle": char_data.get("handle"),
                    "properties": list(char_data.get("properties", {}).keys()),
                    "value": char_data.get("value"),
                })
            if char_list:
                _obs.upsert_characteristics(sid, char_list)  # type: ignore[attr-defined]
    except Exception:
        pass


def _base_enum(target_bt_addr: str, *, deep: bool = False):
    """Connect & enumerate, return (device, mapping, mine_map, perm_map)."""
    from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
    device, mapping, mine_map, perm_map = _connect_enum(target_bt_addr, deep_enumeration=deep)
    # Persist to observation DB if available
    _persist_mapping(device.get_address(), mapping)
    if _obs:
        try:
            _obs.upsert_device(device.get_address(), name=device.get_name())
            svc_list = []
            for uuid, svc_data in mapping.items():
                svc_list.append({
                    "uuid": uuid,
                    "name": svc_data.get("name"),
                    "handle_start": svc_data.get("start_handle"),
                    "handle_end": svc_data.get("end_handle"),
                })
            _obs.upsert_services(device.get_address(), svc_list)
        except Exception:
            pass
    return device, mapping, mine_map, perm_map


def passive_enum(target_bt_addr: str, *, deep: bool = False):
    _, mapping, mine_map, perm_map = _base_enum(target_bt_addr, deep=deep)
    return {"mapping": mapping, "mine_map": mine_map, "perm_map": perm_map}


def naggy_enum(target_bt_addr: str, *, deep: bool = False):
    device, mapping, mine_map, perm_map = _base_enum(target_bt_addr, deep=deep)
    multi = multi_read_all(device, mapping=mapping, rounds=3)
    return {"multi_read": multi, "mine_map": mine_map, "perm_map": perm_map}


def pokey_enum(
    target_bt_addr: str,
    *,
    rounds: int = 3,
    verify: bool = False,
):
    """Enumerate with light write-probes (0/1) after each round."""
    results = {}
    device_obj: Any | None = None
    mine_map: Any | None = None
    perm_map: Any | None = None
    for r in range(rounds):
        print_and_log(f"[*] Pokey enum round {r+1}/{rounds}", LOG__GENERAL)
        device, mapping, mine_map, perm_map = _base_enum(target_bt_addr, deep=False)
        device_obj = device
        from bleep.ble_ops.enum_helpers import small_write_probe
        small_write_probe(device, mapping, verify=verify)
        results[r + 1] = mapping
    return device_obj, results, mine_map, perm_map


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
):
    device, mapping, mine_map, perm_map = _base_enum(target_bt_addr, deep=deep)

    from typing import Any
    from bleep.ble_ops.enum_helpers import build_payload_iterator

    payloads = build_payload_iterator(value_range=value_range, patterns=patterns, file_bytes=payload_file)
    from bleep.ble_ops.enum_helpers import multi_write_all

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

    return device, mapping, mine_map, perm_map

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


def passive_scan(device: str | None = None, timeout: int = 60, transport: str = "auto", quiet: bool = False):  # noqa: D401
    """Execute a passive BLE scan.

    Parameters
    ----------
    device
        Optional MAC address to target (ignored in native scan for now).
    timeout
        Duration in seconds for the discovery main-loop.
    transport
        Bluetooth transport filter: "auto" (default), "le" (Low Energy), or "bredr" (Classic).
    quiet
        If True, suppress console output during scanning.
    """

    if not _HAS_NATIVE_STACK:
        raise RuntimeError(
            "PyGObject/BlueZ bindings not available – passive_scan now requires "
            "a native environment after monolith fallback removal."
        )

    return _native_scan(device, timeout, transport, quiet)


# ---------------------------------------------------------------------------
# Extended scan modes (naggy / pokey / brute)
# ---------------------------------------------------------------------------


def naggy_scan(device: str | None = None, timeout: int = 60, transport: str = "auto"):
    """Active scan with *DuplicateData=False* (slightly more chatty)."""
    if not _HAS_NATIVE_STACK:
        raise RuntimeError("GI/BlueZ runtime missing – naggy_scan unavailable")

    # Set discovery filter once via adapter then delegate to native scan
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    _adapter = _Adapter()
    _adapter.set_discovery_filter({"DuplicateData": False})

    return _native_scan(device, timeout, transport)


def pokey_scan(
    target_mac: str | None = None,
    *,
    timeout: int = 30,
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
    When supplied we set `Address=<MAC>` filter once so only that device’s
    adverts are processed – reduces controller load & log spam when you’re
    investigating a single beacon.
    """
    if not _HAS_NATIVE_STACK:
        raise RuntimeError("GI/BlueZ runtime missing – pokey_scan unavailable")

    import time as _time
    end_time = _time.monotonic() + timeout
    rounds = 0

    # One-time filter setup when target specified
    if target_mac:
        from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
        _Adapter().set_discovery_filter({"Address": target_mac.upper()})

    while _time.monotonic() < end_time:
        rounds += 1
        print_and_log(f"[*] Pokey round {rounds}", LOG__DEBUG)
        naggy_scan(target_mac if target_mac else None, timeout=1)
    return 0


def brute_scan(timeout: int = 30):
    """Full BR/EDR + LE sweep (loudest)."""
    if not _HAS_NATIVE_STACK:
        raise RuntimeError("GI/BlueZ runtime missing – brute_scan unavailable")

    half = max(1, timeout // 2)
    print_and_log("[*] Brute scan – BR/EDR phase", LOG__GENERAL)
    _native_scan(None, half, transport="bredr")
    print_and_log("[*] Brute scan – LE active phase", LOG__GENERAL)
    naggy_scan(None, half, transport="le")
    return 0
