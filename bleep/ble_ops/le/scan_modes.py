"""Advanced BLE scanning modes.

This module implements the four BLE scanning strategies:
1. Passive scan (single scan; one bounded connect+resolve retry)
2. Naggy scan (persistent connection attempts with exponential backoff)
3. Pokey scan (slow, thorough enumeration with extended timeouts)
4. Bruteforce scan (exhaustive characteristic testing trying all handles)

Each mode is a thin wrapper around the canonical
``connect_and_enumerate__bluetooth__low_energy`` primitive in
``bleep.ble_ops.le.connect``, passing mode-specific parameters for scan
attempts, connect retries, timeouts, and backoff.  Post-connect behaviour
unique to a mode (pokey deep reads, bruteforce handle sweep) is handled
locally.

Classic (BR/EDR) device support is maintained via ``_classic_connect``.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import dbus

from bleep.core import errors
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.device_le import (
    system_dbus__bluez_device__low_energy as LEDevice,
)
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
from bleep.dbuslayer.characteristic import Characteristic
from bleep.ble_ops.le.connect import (
    connect_and_enumerate__bluetooth__low_energy as _connect_enum,
)

try:
    from bleep.dbuslayer.device_classic import (
        system_dbus__bluez_device__classic as ClassicDevice,
    )
except ModuleNotFoundError:
    ClassicDevice = None  # type: ignore[assignment,misc]

__all__ = [
    "passive_scan_and_connect",
    "naggy_scan_and_connect",
    "pokey_scan_and_connect",
    "bruteforce_scan_and_connect",
]

PASSIVE_MODE = "ble_passive"
NAGGY_MODE = "ble_naggy"
POKEY_MODE = "ble_pokey"
BRUTEFORCE_MODE = "ble_bruteforce"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _classic_connect(
    target_bt_addr: str,
    transport: str = "bredr",
    adapter_name: str | None = None,
) -> Tuple:
    """Scan, connect, and return a Classic (BR/EDR) device.

    Classic devices have no GATT database so the mapping dicts are empty.
    """
    if ClassicDevice is None:
        raise errors.BLEEPError("Classic device support not available")

    target_bt_addr = target_bt_addr.strip().upper()
    adapter = Adapter(adapter_name) if adapter_name else Adapter()
    if not adapter.is_ready():
        raise errors.NotReadyError()

    mgr = adapter.create_device_manager()

    def _visible() -> bool:
        return any(d.mac_address.upper() == target_bt_addr for d in mgr.devices())

    _count = 0
    while _count < 3 and not _visible():
        _count += 1
        print_and_log(
            f"[*] Classic scan attempt {_count}/3 – searching for {target_bt_addr}",
            LOG__DEBUG,
        )
        try:
            mgr.start_discovery(timeout=5, transport="bredr")
            mgr.run()
        except errors.NotReadyError:
            raise

    if not _visible():
        raise errors.DeviceNotFoundError(target_bt_addr)

    device = ClassicDevice(target_bt_addr, adapter_name=adapter_name) if adapter_name else ClassicDevice(target_bt_addr)
    try:
        if not device.connect(retry=3, wait_timeout=10):
            raise errors.ConnectionError(target_bt_addr, "Classic connect failed")
    except dbus.exceptions.DBusException as exc:
        raise errors.map_dbus_error(exc) from exc

    return device, {}, {}, {}


def _classify_device(device, mode: str, *, log_flags: bool = False) -> None:
    """Run device-type classification (best-effort, never raises)."""
    try:
        if hasattr(device, "get_device_type"):
            dtype = device.get_device_type(scan_mode=mode)
            if dtype:
                print_and_log(f"[*] Device type: {dtype}", LOG__GENERAL)
        elif hasattr(device, "check_device_type"):
            device.check_device_type()
    except Exception as exc:
        print_and_log(f"[*] Device type classification: {exc}", LOG__DEBUG)

    if log_flags and hasattr(device, "device_type_flags"):
        types = device.device_type_flags
        type_str = ", ".join(k for k, v in types.items() if v)
        print_and_log(f"[*] Device types detected: {type_str}", LOG__GENERAL)


def _pokey_deep_read(device) -> None:
    """Read every characteristic value, property, and descriptor.

    This is the unique post-connect behaviour of pokey mode – it gathers
    maximum information from the GATT database at the cost of time.
    """
    error_count = 0
    print_and_log("[*] Performing deep enumeration of characteristics...", LOG__GENERAL)

    for service in device._services:
        for char in service.characteristics:
            try:
                try:
                    value = char.read_value(timeout=10)
                    print_and_log(
                        f"[+] Read value for {char.uuid}: {value.hex()}", LOG__DEBUG,
                    )
                except Exception as exc:
                    if isinstance(exc, dbus.exceptions.DBusException):
                        print_and_log(
                            f"[-] Could not read {char.uuid}: "
                            f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}",
                            LOG__DEBUG,
                        )
                    else:
                        print_and_log(
                            f"[-] Could not read {char.uuid}: {exc}", LOG__DEBUG,
                        )

                for prop_name in char._properties():
                    try:
                        _ = char.get_property(prop_name)
                    except Exception:
                        pass

                for desc in getattr(char, "descriptors", []):
                    try:
                        _ = desc.read_value()
                    except Exception as exc:
                        if isinstance(exc, dbus.exceptions.DBusException):
                            print_and_log(
                                f"[-] Could not read descriptor {desc.uuid}: "
                                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}",
                                LOG__DEBUG,
                            )
                        else:
                            print_and_log(
                                f"[-] Could not read descriptor {desc.uuid}: {exc}",
                                LOG__DEBUG,
                            )

            except Exception as exc:
                error_count += 1
                if isinstance(exc, dbus.exceptions.DBusException):
                    print_and_log(
                        f"[-] Error during deep enumeration: "
                        f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}",
                        LOG__DEBUG,
                    )
                else:
                    print_and_log(
                        f"[-] Error during deep enumeration: {exc}", LOG__DEBUG,
                    )

    print_and_log(
        f"[*] Deep enumeration complete. Encountered {error_count} errors.",
        LOG__GENERAL,
    )


# ---------------------------------------------------------------------------
# 1. Passive Scan
# ---------------------------------------------------------------------------

def passive_scan_and_connect(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    *,
    transport: str = "auto",
    timeout: int = 10,
    adapter_name: str | None = None,
) -> Tuple[LEDevice, Dict[int, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Basic scan with a single discovery pass and a bounded connect/resolve retry.

    Parameters
    ----------
    target_bt_addr : str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF").  Case-insensitive.
    landmine_mapping / security_mapping : dict | None
        Legacy parameters kept for compatibility.
    transport : str
        BlueZ discovery filter – ``"auto"``, ``"le"``, or ``"bredr"``.
    timeout : int
        Discovery budget in seconds.  The connect wait scales from it
        (``max(timeout // 4, 5)``) while service resolution uses a fixed
        floor of 15 s (``max(timeout, 15)``) because it is the slowest phase
        on rich GATT servers and must not be starved by a small scan budget.

    Returns
    -------
    tuple
        ``(device, mapping, landmine_map, perm_map)``
    """
    print_and_log(f"[*] passive_scan_and_connect::target = {target_bt_addr}", LOG__DEBUG)

    if transport.lower() == "bredr":
        return _classic_connect(target_bt_addr, transport, adapter_name=adapter_name)

    print_and_log(f"[*] Using scan timeout of {timeout} seconds", LOG__GENERAL)

    scan_t = max(timeout // 2, 5)
    connect_t = max(timeout // 4, 5)
    # Service resolution is the slowest phase on multi-service peripherals
    # (robotics, audio, wearables); a 5 s window spuriously raised
    # ServicesNotResolved on devices that merely resolve slowly.  Give it the
    # same 15 s floor the rest of the stack uses (connect/gatt-enum defaults)
    # and allow one bounded connect+resolve retry so a transient first-attempt
    # miss is absorbed — matching the robustness of the gatt-enum/AoI paths
    # without turning passive into the aggressive naggy mode.
    services_t = max(timeout, 15)

    device, mapping, mine, perm = _connect_enum(
        target_bt_addr,
        scan_attempts=3,
        scan_timeout=scan_t,
        connect_retries=1,
        connect_wait_timeout=float(connect_t),
        timeout_services=services_t,
        transport=transport,
        max_attempts=2,
        backoff_base=0.5,
        backoff_max=5.0,
        backoff_jitter=0.5,
        adapter_name=adapter_name,
    )

    _classify_device(device, "passive", log_flags=True)
    return device, mapping, mine, perm


# ---------------------------------------------------------------------------
# 2. Naggy Scan
# ---------------------------------------------------------------------------

def naggy_scan_and_connect(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    max_retries: int = 10,
    *,
    transport: str = "auto",
    adapter_name: str | None = None,
) -> Tuple[LEDevice, Dict[int, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Persistent scan with multiple attempts and exponential backoff.

    Parameters
    ----------
    target_bt_addr : str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF").  Case-insensitive.
    landmine_mapping / security_mapping : dict | None
        Legacy parameters kept for compatibility.
    max_retries : int
        Maximum outer connect+resolve attempts (default 10).
    transport : str
        BlueZ discovery filter – ``"auto"``, ``"le"``, or ``"bredr"``.

    Returns
    -------
    tuple
        ``(device, mapping, landmine_map, perm_map)``
    """
    print_and_log(f"[*] naggy_scan_and_connect::target = {target_bt_addr}", LOG__DEBUG)
    print_and_log("[*] Using naggy mode - will persistently attempt connections", LOG__GENERAL)

    if transport.lower() == "bredr":
        return _classic_connect(target_bt_addr, transport, adapter_name=adapter_name)

    device, mapping, mine, perm = _connect_enum(
        target_bt_addr,
        scan_attempts=5,
        scan_timeout=8,
        connect_retries=2,
        connect_wait_timeout=5.0,
        timeout_services=20,
        transport=transport,
        max_attempts=max_retries,
        backoff_base=0.5,
        backoff_max=30.0,
        backoff_jitter=0.5,
        adapter_name=adapter_name,
    )

    _classify_device(device, "naggy")
    return device, mapping, mine, perm


# ---------------------------------------------------------------------------
# 3. Pokey Scan
# ---------------------------------------------------------------------------

def pokey_scan_and_connect(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    *,
    transport: str = "auto",
    adapter_name: str | None = None,
) -> Tuple[LEDevice, Dict[int, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Slow, thorough enumeration with extended timeouts.

    Parameters
    ----------
    target_bt_addr : str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF").  Case-insensitive.
    landmine_mapping / security_mapping : dict | None
        Legacy parameters kept for compatibility.
    transport : str
        BlueZ discovery filter – ``"auto"``, ``"le"``, or ``"bredr"``.

    Returns
    -------
    tuple
        ``(device, mapping, landmine_map, perm_map)``
    """
    print_and_log(f"[*] pokey_scan_and_connect::target = {target_bt_addr}", LOG__DEBUG)
    print_and_log(
        "[*] Using pokey mode - slow, thorough enumeration with extended timeouts",
        LOG__GENERAL,
    )

    if transport.lower() == "bredr":
        return _classic_connect(target_bt_addr, transport, adapter_name=adapter_name)

    print_and_log("[*] Performing extended scan...", LOG__GENERAL)

    device, mapping, mine, perm = _connect_enum(
        target_bt_addr,
        scan_attempts=3,
        scan_timeout=10,
        connect_retries=5,
        connect_wait_timeout=10.0,
        timeout_services=30,
        transport=transport,
        deep_enumeration=False,
        adapter_name=adapter_name,
    )

    _pokey_deep_read(device)
    _classify_device(device, "pokey")
    return device, mapping, mine, perm


# ---------------------------------------------------------------------------
# 4. Bruteforce Scan
# ---------------------------------------------------------------------------

def bruteforce_scan_and_connect(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    start_handle: int = 0x0001,
    end_handle: int = 0xFFFF,
    adapter_name: str | None = None,
) -> Tuple[LEDevice, Dict[int, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Exhaustive characteristic testing trying all possible handle values.

    Parameters
    ----------
    target_bt_addr : str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF").  Case-insensitive.
    landmine_mapping / security_mapping : dict | None
        Legacy parameters kept for compatibility.
    start_handle : int
        First handle value to probe (default ``0x0001``).
    end_handle : int
        Last handle value to probe (default ``0xFFFF``).

    Returns
    -------
    tuple
        ``(device, mapping, landmine_map, perm_map)``
    """
    print_and_log(f"[*] bruteforce_scan_and_connect::target = {target_bt_addr}", LOG__DEBUG)
    print_and_log(
        "[*] Using bruteforce mode - attempting all possible handles regardless of permissions",
        LOG__GENERAL,
    )

    device, mapping, mine_map, perm_map = pokey_scan_and_connect(
        target_bt_addr, landmine_mapping, security_mapping,
        adapter_name=adapter_name,
    )

    print_and_log(
        f"[*] Starting bruteforce handle scan from 0x{start_handle:04x} to 0x{end_handle:04x}",
        LOG__GENERAL,
    )

    bruteforce_discovered: Dict[int, str] = {}
    bruteforce_errors: Dict[int, str] = {}
    known_handles = set(mapping.keys())

    if end_handle > 0x00FF and end_handle == 0xFFFF:
        end_handle = 0x00FF
        print_and_log("[*] Limiting handle range to 0x00FF for reasonable scan time", LOG__GENERAL)

    total_handles = end_handle - start_handle + 1
    check_increment = max(1, total_handles // 100)

    for handle in range(start_handle, end_handle + 1):
        if handle % check_increment == 0:
            progress = ((handle - start_handle) / total_handles) * 100
            print_and_log(
                f"[*] Bruteforce progress: {progress:.1f}% (handle 0x{handle:04x})",
                LOG__GENERAL,
            )

        if handle in known_handles:
            continue

        try:
            for service in device._services:
                try:
                    temp_char = Characteristic(
                        service,
                        f"{service.path}/char{handle:04x}",
                        "00000000-0000-0000-0000-000000000000",
                    )
                    temp_char.handle = handle

                    value = temp_char.read_value(timeout=5)

                    print_and_log(
                        f"[+] Bruteforce discovered readable handle 0x{handle:04x}: {value.hex()}",
                        LOG__GENERAL,
                    )
                    bruteforce_discovered[handle] = f"unknown-{handle:04x}"

                    try:
                        for test_value, flags in [
                            (bytes([0x00]), {}),
                            (bytes([0x01]), {}),
                            (bytes([handle & 0xFF]), {}),
                            (bytes([0x00]), {"type": "command"}),
                            (bytes([0x01]), {"type": "request"}),
                        ]:
                            temp_char.write_value(test_value, flags)
                            print_and_log(
                                f"[+] Successfully wrote {test_value.hex()} to handle 0x{handle:04x}",
                                LOG__DEBUG,
                            )
                    except Exception as exc:
                        if isinstance(exc, dbus.exceptions.DBusException):
                            print_and_log(
                                f"[-] Handle 0x{handle:04x} not writable: "
                                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}",
                                LOG__DEBUG,
                            )
                        else:
                            print_and_log(
                                f"[-] Handle 0x{handle:04x} not writable: {exc}",
                                LOG__DEBUG,
                            )

                    break
                except Exception:
                    continue
        except Exception as exc:
            error_type = type(exc).__name__
            error_msg = (
                exc.get_dbus_message() or str(exc)
                if isinstance(exc, dbus.exceptions.DBusException)
                else str(exc)
            )
            bruteforce_errors[handle] = f"{error_type}: {error_msg}"

            if not (
                isinstance(exc, errors.PermissionDeniedError)
                or "NotPermitted" in error_msg
                or "NotAuthorized" in error_msg
            ):
                print_and_log(
                    f"[-] Handle 0x{handle:04x} error: {error_msg}", LOG__DEBUG,
                )

    mapping.update(bruteforce_discovered)

    for handle, uuid in bruteforce_discovered.items():
        mine_map[uuid] = ["read"]
        perm_map[uuid] = ["read"]

    print_and_log(
        f"[+] Bruteforce scan complete. Discovered {len(bruteforce_discovered)} additional handles",
        LOG__GENERAL,
    )

    _classify_device(device, "bruteforce")
    return device, mapping, mine_map, perm_map


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def scan_and_connect(
    target_bt_addr: str,
    mode: str = PASSIVE_MODE,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    **kwargs,
) -> Tuple[LEDevice, Dict[int, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Select and execute the appropriate scan mode.

    Parameters
    ----------
    target_bt_addr : str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF").  Case-insensitive.
    mode : str
        One of ``PASSIVE_MODE``, ``NAGGY_MODE``, ``POKEY_MODE``,
        ``BRUTEFORCE_MODE``.
    landmine_mapping / security_mapping : dict | None
        Legacy parameters kept for compatibility.
    **kwargs
        Forwarded to the selected mode function.

    Returns
    -------
    tuple
        ``(device, mapping, landmine_map, perm_map)``
    """
    print_and_log(f"[*] scan_and_connect using mode: {mode}", LOG__GENERAL)

    if mode == PASSIVE_MODE:
        return passive_scan_and_connect(target_bt_addr, landmine_mapping, security_mapping, **kwargs)
    elif mode == NAGGY_MODE:
        return naggy_scan_and_connect(target_bt_addr, landmine_mapping, security_mapping, **kwargs)
    elif mode == POKEY_MODE:
        return pokey_scan_and_connect(target_bt_addr, landmine_mapping, security_mapping, **kwargs)
    elif mode == BRUTEFORCE_MODE:
        return bruteforce_scan_and_connect(target_bt_addr, landmine_mapping, security_mapping, **kwargs)
    else:
        print_and_log(f"[!] Unknown scan mode '{mode}', falling back to passive mode", LOG__GENERAL)
        return passive_scan_and_connect(target_bt_addr, landmine_mapping, security_mapping, **kwargs)
