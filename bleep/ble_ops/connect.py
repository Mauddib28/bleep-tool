from __future__ import annotations

"""bleep.ble_ops.connect – native connection + enumeration helpers.

This module finally replaces the *monolithic* `connect_and_enumerate__bluetooth__low_energy`
function that lived in several legacy files.  It uses the refactored
`bleep.dbuslayer` stack exclusively and therefore eliminates the last runtime
requirement for importing the historical `dbus__bleep.py` source.

A minimal subset of the original public contract is preserved so higher-level
modules (and tests) can switch over without modification:

    >>> from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy
    >>> dev, mapping, landmine_map, perm_map = connect_and_enumerate__bluetooth__low_energy("AA:BB:CC:DD:EE:FF")

Return types are *compatible* – the mapping dictionaries mirror the field
names produced by the monolith.  Permission / landmine maps are currently
simple aliases of the characteristic Flags set; these will be refined in a
later pass when fine-grained ATT permission inspection is added.
"""

import sys as _sys
import time as _time
from typing import Tuple, Dict, List, Optional, Callable, Any

import dbus

from bleep.core import errors as _errors
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.device_le import (
    system_dbus__bluez_device__low_energy as _LEDevice,
)
from bleep.core.error_handling import controller_stall_mitigation
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
from bleep.ble_ops.reconnect import ReconnectionMonitor, reconnect_check

# Public export list -----------------------------------------------------------------------------
__all__ = [
    "connect_and_enumerate__bluetooth__low_energy",
    "connect_with_monitoring",
]


# Helper -----------------------------------------------------------------------------------------

def _wait_for_services(device: _LEDevice, timeout: int = 15) -> bool:
    """Block until *ServicesResolved* is *True* or *timeout* seconds elapsed."""
    start = _time.monotonic()
    while _time.monotonic() - start < timeout:
        try:
            if device.is_services_resolved():
                return True
        except _errors.BLEEPError:
            # Device may disconnect briefly → retry until timeout
            pass
        _time.sleep(0.25)
    return False


# Public API -------------------------------------------------------------------------------------

def connect_and_enumerate__bluetooth__low_energy(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    *,
    timeout_connect: int = 10,
    timeout_services: int = 15,
    enable_monitoring: bool = False,
    deep_enumeration: bool = False,
    reconnect_callback: Optional[Callable[[bool, str], None]] = None,
):
    """Connect to *target_bt_addr* and enumerate its GATT database.

    Parameters
    ----------
    target_bt_addr: str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF").  Case-insensitive.
    landmine_mapping / security_mapping: dict | None
        Back-compat parameters kept so callers do not break.  Ignored for now –
        the function *returns* freshly generated maps so callers expecting the
        tuple can keep functioning.
    timeout_connect / timeout_services: int
        Seconds before aborting the connect-phase / service-resolution phase.
    enable_monitoring: bool
        If True, start a background thread to monitor the connection and 
        automatically reconnect if the device disconnects.
    reconnect_callback: Optional[Callable[[bool, str], None]]
        Callback function to call when reconnection occurs. The function will be
        called with a boolean indicating success and a message string.

    Returns
    -------
    tuple
        *(device, mapping, landmine_map, perm_map)* – mirrors the monolith in
        order and structure.
    """

    print_and_log(f"[*] connect_and_enumerate::target = {target_bt_addr}", LOG__DEBUG)

    # Normalise/uppercase the input address for BlueZ path computation.
    target_bt_addr = target_bt_addr.strip().upper()

    # ------------------------------------------------------------------
    # PRE-FLIGHT 0 – ensure adapter exists & powered
    # ------------------------------------------------------------------

    _adapter = _Adapter()
    if not _adapter.is_ready():
        raise _errors.NotReadyError()

    _mgr = _adapter.create_device_manager()

    # ------------------------------------------------------------------
    # PRE-FLIGHT 1 – passive scan until the target becomes visible
    # ------------------------------------------------------------------

    def _target_visible() -> bool:
        return any(d.mac_address.upper() == target_bt_addr for d in _mgr.devices())

    scan_attempts = 0
    max_scan_attempts = 3
    while scan_attempts < max_scan_attempts and not _target_visible():
        scan_attempts += 1
        print_and_log(
            f"[*] Scan attempt {scan_attempts}/{max_scan_attempts} – searching for {target_bt_addr}",
            LOG__DEBUG,
        )
        try:
            _mgr.start_discovery(timeout=5)
            _mgr.run()
        except _errors.NotReadyError:
            # Controller powered-off mid-test; propagate the error.
            raise

    if not _target_visible():
        raise _errors.DeviceNotFoundError(target_bt_addr)

    # Instantiate LE device wrapper (does *not* trigger D-Bus calls yet).
    device = _LEDevice(target_bt_addr)

    # ------------------------------------------------------------------
    # 1. Connect (with retry)
    # ------------------------------------------------------------------
    from bleep.dbuslayer.agent import ensure_default_pairing_agent  # inline import to avoid cycles

    try:
        if not device.connect(retry=5):
            raise _errors.ConnectionError(target_bt_addr, "connect failed")
    except (_errors.NotAuthorizedError, _errors.PermissionError):
        # Likely needs pairing – attempt once with auto-agent
        print_and_log("[*] Connection requires pairing – attempting auto-pair", LOG__GENERAL)
        ensure_default_pairing_agent()
        try:
            device.pair(timeout=30)
            device.set_trusted(True)
            if not device.connect(retry=3):
                raise _errors.ConnectionError(target_bt_addr, "connect failed after pairing")
        except dbus.exceptions.DBusException as exc:
            raise _errors.map_dbus_error(exc) from exc
    except dbus.exceptions.DBusException as exc:
        if exc.get_dbus_name() == "org.freedesktop.DBus.Error.NoReply":
            print_and_log("[!] Controller appears stalled (NoReply)", LOG__GENERAL)
            controller_stall_mitigation(target_bt_addr)
            # one-shot retry
            try:
                if device.connect(retry=3):
                    print_and_log("[+] Recovered after stall workaround", LOG__GENERAL)
                else:
                    raise _errors.ConnectionError(target_bt_addr, "connect failed after stall workaround")
            except Exception:
                raise _errors.map_dbus_error(exc) from exc
        else:
            raise _errors.map_dbus_error(exc) from exc

    # ------------------------------------------------------------------
    # 2. Wait for service resolution
    # ------------------------------------------------------------------
    if not _wait_for_services(device, timeout_services):
        raise _errors.ServicesNotResolvedError(target_bt_addr)

    # Trigger enumeration and build compatibility maps
    _ = device.services_resolved(deep=deep_enumeration)

    mapping = device.ble_device__mapping
    mine_map = device.ble_device__mine_mapping
    perm_map = device.ble_device__permission_mapping
    
    # ------------------------------------------------------------------
    # 3. Start connection monitoring if requested
    # ------------------------------------------------------------------
    if enable_monitoring:
        monitor = ReconnectionMonitor(
            device,
            max_attempts=5,
            callback=reconnect_callback,
        )
        monitor.start_monitoring()
        # Store the monitor on the device for later reference
        device._reconnection_monitor = monitor

    # ------------------------------------------------------------------
    # 4. Return tuple in monolith order
    # ------------------------------------------------------------------
    return device, mapping, mine_map, perm_map


def connect_with_monitoring(
    target_bt_addr: str,
    max_reconnect_attempts: int = 5,
    reconnect_callback: Optional[Callable[[bool, str], None]] = None,
) -> Tuple[_LEDevice, Dict[str, Any], Dict[str, List[str]], Dict[str, List[str]]]:
    """Connect to a BLE device with automatic reconnection monitoring.
    
    This is a convenience wrapper around connect_and_enumerate__bluetooth__low_energy
    that enables reconnection monitoring by default.
    
    Parameters
    ----------
    target_bt_addr: str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF").  Case-insensitive.
    max_reconnect_attempts: int
        Maximum number of reconnection attempts, by default 5
    reconnect_callback: Optional[Callable[[bool, str], None]]
        Callback function to call when reconnection occurs
        
    Returns
    -------
    tuple
        *(device, mapping, landmine_map, perm_map)* – mirrors the monolith in
        order and structure.
    """
    return connect_and_enumerate__bluetooth__low_energy(
        target_bt_addr,
        enable_monitoring=True,
        reconnect_callback=reconnect_callback,
    )
