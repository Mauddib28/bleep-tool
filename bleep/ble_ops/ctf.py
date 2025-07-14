from __future__ import annotations

"""bleep.ble_ops.ctf – native BLE-CTF helpers

This module replaces the temporary proxy that patched the legacy
`Functions.ble_ctf_functions` implementation.  The new version relies solely
on the refactored *bleep* stack:

* device discovery / connection   →  bleep.ble_ops.scan / connect
* GATT operations                 →  bleep.dbuslayer.device_le

Only the subset required by the current test-suite is implemented:

    • ble_ctf__scan_and_enumeration()
    • ble_ctf__read_characteristic()
    • ble_ctf__write_flag()          (and internal write helper)
    • BLE_CTF__CHARACTERISTIC_FLAGS  constant

Further legacy helpers will be ported iteratively as the need arises.
"""

import re as _re
from typing import Tuple, Dict, List, Optional
import dbus

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.ble_ops.connect import (
    connect_and_enumerate__bluetooth__low_energy as _connect_enum,
)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

BLE_CTF__CHARACTERISTIC_FLAGS: Dict[str, str] = {
    # Mapping reproduced verbatim from the monolith.  The *char00xx* entries
    # represent the BlueZ characteristic suffix used in object paths, i.e. the
    # handle value in hexadecimal without the leading "0x".  These names are
    # kept so that existing write-ups and documentation remain valid.
    "Flag-01": "Given",
    "Flag-02": "char002d",
    "Flag-03": "char002f",
    "Flag-04": "char0015",         # Note: This flag involves reading GATT Service extra device attributes
    "Flag-05": "char0031",
    "Flag-06": "char0033",
    "Flag-07": "char0035",
    "Flag-08": "char0037",
    "Flag-09": "char003b",
    "Flag-10": "char003d",
    "Flag-11": "char003f",
    "Flag-12": "char0041",
    "Flag-13": "char0045",
    "Flag-14": "char0047",
    "Flag-15": "char004b",
    "Flag-16": "char004d",
    "Flag-17": "char0049",
    "Flag-18": "char0051",
    "Flag-19": "char0053",
    "Flag-20": "char0055",
    "Flag-Score": "char0029",
    "Flag-Write": "char002b",
}

__all__ = [
    "BLE_CTF__CHARACTERISTIC_FLAGS",
    "ble_ctf__scan_and_enumeration",
    "ble_ctf__read_characteristic",
    "ble_ctf__write_flag",
    "ble_ctf__read_descriptor",
    "ble_ctf__write_descriptor",
    "ble_ctf__start_notify",
    "ble_ctf__stop_notify",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CHAR_RX = _re.compile(r"char(?P<hex>[0-9a-f]{4})", _re.IGNORECASE)


def _handle_from_char_name(name: str) -> Optional[int]:
    """Return numeric handle (int) extracted from a *char00xx* placeholder."""
    m = _CHAR_RX.match(name)
    if not m:
        return None
    return int(m.group("hex"), 16)


def _uuid_from_char_name(device, name: str) -> Optional[str]:
    """Translate a *char00xx* label into its 128-bit UUID using the device map."""
    handle = _handle_from_char_name(name)
    if handle is not None and handle in device.ble_device__mapping:
        return device.ble_device__mapping[handle]

    # Fallback: search by DBus object path suffix (works even without Handle property)
    suffix = f"/{name.lower()}"
    for svc in getattr(device, "_services", []):
        for c in getattr(svc, "characteristics", []):
            if c.path.lower().endswith(suffix):
                return c.uuid

    # Some constant entries (e.g. "Given") are not char names → return None
    return None


def _to_bytearray(value) -> bytes:
    """Convert *value* (int | str | bytes | bytearray | list[int]) to bytes."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, int):
        return value.to_bytes(1, "little")
    if isinstance(value, list):
        return bytes(value)
    if isinstance(value, str):
        # Accept either plain ascii or hex-string (e.g. "01 02 03")
        try:
            return bytes.fromhex(value)
        except ValueError:
            return value.encode()
    raise TypeError(f"Unsupported write value type: {type(value)}")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ble_ctf__scan_and_enumeration() -> Tuple["_LEDevice", Dict[int, str]]:  # type: ignore[name-defined]
    """Connect to the BLE-CTF peripheral, resolve services and return mapping.

    The target MAC address is fixed in the CTF lab material.  If it ever
    changes an environment variable **BLE_CTF_MAC** can override it.
    
    Note: The BLE-CTF device has a fixed set of characteristics with specific
    UUIDs. This function ensures the mapping contains the correct UUIDs for
    the CTF characteristics regardless of what BlueZ reports.
    """
    import os

    target_mac = os.getenv("BLE_CTF_MAC", "CC:50:E3:B6:BC:A6")
    print_and_log(
        f"[*] BLE-CTF scan & enumeration – target={target_mac}", LOG__GENERAL
    )

    device, mapping, _, _ = _connect_enum(target_mac)
    
    # The BLE-CTF device has a fixed set of characteristics with known UUIDs
    # Ensure our mapping contains these regardless of what BlueZ reports
    ctf_uuids = {
        0x0029: "0000ff01-0000-1000-8000-00805f9b34fb",  # Flag-Score
        0x002b: "0000ff02-0000-1000-8000-00805f9b34fb",  # Flag-Write
    }
    
    # Update mapping with known UUIDs
    for handle, uuid in ctf_uuids.items():
        if handle not in mapping:
            mapping[handle] = uuid
            print_and_log(f"[*] Added known CTF UUID for handle 0x{handle:04x}: {uuid}", LOG__DEBUG)
    
    return device, mapping


def ble_ctf__read_characteristic(
    characteristic_name: str,
    user_device,
    user_device__internals_map=None,  # kept for signature compat – ignored
):
    """Read characteristic designated by *characteristic_name*.

    The *characteristic_name* can be a *char00xx* label or a full UUID.  The
    function returns the ASCII representation if the value is printable;
    otherwise the raw bytes are returned.
    
    For the BLE-CTF device, this function will use direct handle-based access
    if the characteristic is not found by UUID. This is necessary because the
    CTF device may not properly advertise all characteristic UUIDs.
    """
    if characteristic_name.lower().startswith("char"):
        # For CTF device, always try direct handle access first for char#### names
        handle = _handle_from_char_name(characteristic_name)
        if handle is not None:
            try:
                # Use raw D-Bus access to read by handle
                print_and_log(f"[*] Attempting direct handle read for {characteristic_name} (0x{handle:04x})", LOG__DEBUG)
                
                # Find a service to use as base for the handle operation
                if not hasattr(user_device, "_services") or not user_device._services:
                    user_device.services_resolved()  # Force service resolution
                
                if not user_device._services:
                    raise ValueError(f"No services found on device, cannot read {characteristic_name}")
                
                # Try each service until we find one that works
                for service in user_device._services:
                    try:
                        # Create D-Bus path for the characteristic
                        char_path = f"{service.path}/{characteristic_name.lower()}"
                        
                        # Get D-Bus object and interface
                        char_obj = user_device.bus.get_object("org.bluez", char_path)
                        char_iface = dbus.Interface(char_obj, "org.bluez.GattCharacteristic1")
                        
                        # Read value
                        raw = bytes(char_iface.ReadValue({}))
                        print_and_log(f"[+] Direct handle read successful for {characteristic_name}", LOG__DEBUG)
                        try:
                            return raw.decode()
                        except Exception:
                            return raw
                    except Exception as e:
                        print_and_log(f"[-] Direct handle read failed on service {service.uuid}: {e}", LOG__DEBUG)
                        continue
                
                # If we get here, all services failed
                raise ValueError(f"Failed to read {characteristic_name} from any service")
            except Exception as e:
                print_and_log(f"[-] All direct handle read attempts failed: {e}", LOG__DEBUG)
                
                # Fall back to UUID method
                uuid = _uuid_from_char_name(user_device, characteristic_name)
                if uuid is None:
                    raise ValueError(f"Unable to translate {characteristic_name} to UUID and direct handle access failed")
        else:
            # Not a handle-based name, try UUID lookup
            uuid = _uuid_from_char_name(user_device, characteristic_name)
            if uuid is None:
                raise ValueError(f"Unable to translate {characteristic_name} to UUID")
    else:
        # Direct UUID provided
        uuid = characteristic_name
    
    # Try standard characteristic read by UUID
    try:
        raw = user_device.read_characteristic(uuid)
        try:
            return raw.decode()
        except Exception:
            return raw
    except ValueError as e:
        print_and_log(f"[-] Standard read failed: {e}", LOG__DEBUG)
        raise


def _ble_ctf__write_characteristic(
    value,
    characteristic_name: str,
    user_device,
):
    """Internal helper to write to a characteristic by name or UUID.
    
    This function will attempt to use the standard write method first, but if
    that fails due to UUID translation, it will fall back to direct handle access.
    """
    if characteristic_name.lower().startswith("char"):
        # For CTF device, always try direct handle access first for char#### names
        handle = _handle_from_char_name(characteristic_name)
        if handle is not None:
            try:
                # Use raw D-Bus access to write by handle
                print_and_log(f"[*] Attempting direct handle write for {characteristic_name} (0x{handle:04x})", LOG__DEBUG)
                
                # Find a service to use as base for the handle operation
                if not hasattr(user_device, "_services") or not user_device._services:
                    user_device.services_resolved()  # Force service resolution
                
                if not user_device._services:
                    raise ValueError(f"No services found on device, cannot write to {characteristic_name}")
                
                # Try each service until we find one that works
                for service in user_device._services:
                    try:
                        # Create D-Bus path for the characteristic
                        char_path = f"{service.path}/{characteristic_name.lower()}"
                        
                        # Get D-Bus object and interface
                        char_obj = user_device.bus.get_object("org.bluez", char_path)
                        char_iface = dbus.Interface(char_obj, "org.bluez.GattCharacteristic1")
                        
                        # Convert value to bytes if needed
                        byte_value = _to_bytearray(value)
                        
                        # Write value
                        char_iface.WriteValue(dbus.Array(byte_value), {})
                        print_and_log(f"[+] Direct handle write successful for {characteristic_name}", LOG__DEBUG)
                        return
                    except Exception as e:
                        print_and_log(f"[-] Direct handle write failed on service {service.uuid}: {e}", LOG__DEBUG)
                        continue
                
                # If we get here, all services failed
                raise ValueError(f"Failed to write to {characteristic_name} on any service")
            except Exception as e:
                print_and_log(f"[-] All direct handle write attempts failed: {e}", LOG__DEBUG)
                
                # Fall back to UUID method
                uuid = _uuid_from_char_name(user_device, characteristic_name)
                if uuid is None:
                    raise ValueError(f"Unable to translate {characteristic_name} to UUID and direct handle access failed")
        else:
            # Not a handle-based name, try UUID lookup
            uuid = _uuid_from_char_name(user_device, characteristic_name)
            if uuid is None:
                raise ValueError(f"Unable to translate {characteristic_name} to UUID")
    else:
        # Direct UUID provided
        uuid = characteristic_name
    
    # Try standard characteristic write by UUID
    try:
        user_device.write_characteristic(uuid, _to_bytearray(value))
    except ValueError as e:
        print_and_log(f"[-] Standard write failed: {e}", LOG__DEBUG)
        raise


def ble_ctf__write_flag(
    write_value,
    user_device,
    user_device__internals_map=None,  # kept for signature compat – ignored
):
    """Submit *write_value* to the CTF **Flag-Write** characteristic."""
    flag_char = BLE_CTF__CHARACTERISTIC_FLAGS["Flag-Write"]
    _ble_ctf__write_characteristic(write_value, flag_char, user_device)
    print_and_log("[+] Flag submitted", LOG__DEBUG)


def ble_ctf__read_descriptor(
    descriptor_path: str,
    user_device,
    user_device__internals_map=None,  # kept for signature compat – ignored
):
    """Read a descriptor by its D-Bus object path.
    
    Parameters
    ----------
    descriptor_path
        The D-Bus object path of the descriptor to read
    user_device
        The connected BLE device
    user_device__internals_map
        Legacy parameter, ignored
        
    Returns
    -------
    str or bytes
        The descriptor value, decoded to ASCII if possible
    """
    raw = user_device.read_descriptor(descriptor_path)
    try:
        return raw.decode()
    except Exception:
        return raw


def ble_ctf__write_descriptor(
    value,
    descriptor_path: str,
    user_device,
    user_device__internals_map=None,  # kept for signature compat – ignored
):
    """Write a value to a descriptor by its D-Bus object path.
    
    Parameters
    ----------
    value
        The value to write (str, bytes, int, list[int], or bytearray)
    descriptor_path
        The D-Bus object path of the descriptor to write to
    user_device
        The connected BLE device
    user_device__internals_map
        Legacy parameter, ignored
    """
    user_device.write_descriptor(descriptor_path, _to_bytearray(value))
    print_and_log(f"[+] Descriptor write successful: {descriptor_path}", LOG__DEBUG)


def ble_ctf__start_notify(
    characteristic_uuid: str,
    callback,
    user_device,
    user_device__internals_map=None,  # kept for signature compat – ignored
):
    """Enable notifications for a characteristic.
    
    Parameters
    ----------
    characteristic_uuid
        The UUID of the characteristic to enable notifications for
    callback
        Function to call when a notification is received
    user_device
        The connected BLE device
    user_device__internals_map
        Legacy parameter, ignored
    """
    # If characteristic_uuid is a char00xx label, translate it to a UUID
    if characteristic_uuid.lower().startswith("char"):
        uuid = _uuid_from_char_name(user_device, characteristic_uuid)
        if uuid is None:
            raise ValueError(f"Unable to translate {characteristic_uuid} to UUID")
        characteristic_uuid = uuid
        
    user_device.start_notify(characteristic_uuid, callback)
    print_and_log(f"[+] Notifications enabled for {characteristic_uuid}", LOG__DEBUG)


def ble_ctf__stop_notify(
    characteristic_uuid: str,
    user_device,
    user_device__internals_map=None,  # kept for signature compat – ignored
):
    """Disable notifications for a characteristic.
    
    Parameters
    ----------
    characteristic_uuid
        The UUID of the characteristic to disable notifications for
    user_device
        The connected BLE device
    user_device__internals_map
        Legacy parameter, ignored
    """
    # If characteristic_uuid is a char00xx label, translate it to a UUID
    if characteristic_uuid.lower().startswith("char"):
        uuid = _uuid_from_char_name(user_device, characteristic_uuid)
        if uuid is None:
            raise ValueError(f"Unable to translate {characteristic_uuid} to UUID")
        characteristic_uuid = uuid
        
    user_device.stop_notify(characteristic_uuid)
    print_and_log(f"[+] Notifications disabled for {characteristic_uuid}", LOG__DEBUG)

# ---------------------------------------------------------------------------
# Legacy import-path shim – keeps old modules that still import
# `Functions.ble_ctf_functions` from crashing even though the implementation
# is now native.
# ---------------------------------------------------------------------------

import sys as _sys, types as _types

_sys.modules.setdefault("Functions.ble_ctf_functions", _types.ModuleType("Functions.ble_ctf_functions")) 