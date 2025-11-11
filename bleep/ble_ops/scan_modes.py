"""Advanced BLE scanning modes.

This module implements the four BLE scanning strategies from the original monolith:
1. Passive scan (single connection attempt)
2. Naggy scan (persistent connection attempts with exponential backoff)
3. Pokey scan (slow, thorough enumeration with extended timeouts)
4. Bruteforce scan (exhaustive characteristic testing trying all handles)

Each scan mode has different timeout, retry, and error handling behaviors
to address different scanning scenarios.
"""

from __future__ import annotations

import time
import random
from typing import Dict, List, Tuple, Optional, Set, Union

import dbus

from bleep.core import errors
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.device_le import (
    system_dbus__bluez_device__low_energy as LEDevice,
)
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
from bleep.dbuslayer.characteristic import Characteristic

# Optional Classic device wrapper – present in refactor Phase-8
try:
    from bleep.dbuslayer.device_classic import (
        system_dbus__bluez_device__classic as ClassicDevice,
    )
except ModuleNotFoundError:
    ClassicDevice = None  # Classic support not compiled on some platforms

# Public export list
__all__ = [
    "passive_scan_and_connect",
    "naggy_scan_and_connect",
    "pokey_scan_and_connect",
    "bruteforce_scan_and_connect",
]

# Constants for the different scanning modes
PASSIVE_MODE = "ble_passive"
NAGGY_MODE = "ble_naggy"
POKEY_MODE = "ble_pokey"
BRUTEFORCE_MODE = "ble_bruteforce"

# Common helper functions
def _wait_for_services(device, timeout: int = 15) -> bool:  # type: ignore[override]
    """Wait until *ServicesResolved* is True for LE devices.

    For Classic (BR/EDR) devices there is no GATT DB to resolve; we return
    *True* immediately to keep the calling code simple.
    """

    if not hasattr(device, "is_services_resolved"):
        return True  # Classic device – nothing to wait for

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            if device.is_services_resolved():
                return True
        except errors.BLEEPError:
            # Device may disconnect briefly → retry until timeout
            pass
        time.sleep(0.25)
    return False

def _get_adapter() -> Adapter:
    """Get adapter instance and verify it's ready."""
    adapter = Adapter()
    if not adapter.is_ready():
        raise errors.NotReadyError()
    return adapter

def _scan_until_visible(
    target_bt_addr: str,
    *,
    max_attempts: int = 3,
    timeout: int = 5,
    transport: str = "auto",
) -> bool:
    """Scan for the target device until it's found or max attempts reached."""
    target_bt_addr = target_bt_addr.strip().upper()
    adapter = _get_adapter()
    
    # Apply transport filter if explicitly requested.  BlueZ accepts
    # "auto", "le", or "bredr" – pass through unchanged.
    if transport.lower() in {"le", "bredr"}:
        adapter.set_discovery_filter({"Transport": transport.lower()})

    mgr = adapter.create_device_manager()
    
    def _target_visible() -> bool:
        return any(d.mac_address.upper() == target_bt_addr for d in mgr.devices())
    
    scan_attempts = 0
    while scan_attempts < max_attempts and not _target_visible():
        scan_attempts += 1
        print_and_log(
            f"[*] Scan attempt {scan_attempts}/{max_attempts} – searching for {target_bt_addr}",
            LOG__DEBUG,
        )
        try:
            mgr.start_discovery(timeout=timeout)
            mgr.run()
        except errors.NotReadyError:
            # Controller powered-off mid-test; propagate the error.
            raise
    
    return _target_visible()

# 1. Passive Scan Implementation
def passive_scan_and_connect(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    *,
    transport: str = "auto",
    timeout: int = 10,  # Add timeout parameter with default of 10 seconds
) -> Tuple[LEDevice, Dict[int, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Basic scan with a single connection attempt.
    
    This is a simple, fast method that works well for devices that 
    connect reliably on the first try. It has no retry mechanism and 
    will fail quickly if there are connection issues.
    
    Parameters
    ----------
    target_bt_addr: str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF"). Case-insensitive.
    landmine_mapping / security_mapping: dict | None
        Legacy parameters kept for compatibility but not used internally.
    transport: str
        Bluetooth transport filter applied via BlueZ ``SetDiscoveryFilter``.
        Accepts "auto" (default – BlueZ decides), "le" (Low-Energy only) or
        "bredr" (Classic BR/EDR only).  This parameter controls *only* the
        discovery filter and the choice of wrapper class once the device is
        found; it is **not** related to the scan-mode algorithm itself.
    timeout: int
        Total timeout in seconds for the entire scan, connect, and service resolution process.
        Default is 10 seconds. The timeout is distributed between scanning (50%), 
        connection (25%), and service resolution (25%), with minimum values for each stage.
    
    Returns
    -------
    tuple
        (device, mapping, landmine_map, perm_map)
    """
    print_and_log(f"[*] passive_scan_and_connect::target = {target_bt_addr}", LOG__DEBUG)
    
    # Normalize address
    target_bt_addr = target_bt_addr.strip().upper()
    
    # Check adapter
    adapter = _get_adapter()
    
    # Scan for device using the provided timeout
    print_and_log(f"[*] Using scan timeout of {timeout} seconds", LOG__GENERAL)
    
    # Use half the timeout for scanning and half for connection+service resolution
    scan_timeout = max(timeout // 2, 5)  # At least 5 seconds for scanning
    connect_timeout = max(timeout // 4, 3)  # At least 3 seconds for connection
    services_timeout = max(timeout // 4, 5)  # At least 5 seconds for service resolution
    
    # Increase max_attempts to 3 for better reliability
    if not _scan_until_visible(
        target_bt_addr, max_attempts=3, timeout=scan_timeout, transport=transport
    ):
        raise errors.DeviceNotFoundError(target_bt_addr)
    
    # Create device wrapper based on *transport*
    if transport.lower() == "bredr":
        if ClassicDevice is None:
            raise errors.BLEEPError("Classic device support not available")
        device_wrapper = ClassicDevice
    else:
        device_wrapper = LEDevice

    device = device_wrapper(target_bt_addr)  # type: ignore[call-arg]
    
    try:
        print_and_log(f"[*] Connecting with timeout of {connect_timeout} seconds (retry=1)", LOG__GENERAL)
        # Add retry=1 for better reliability
        if not device.connect(retry=1, wait_timeout=connect_timeout):
            raise errors.ConnectionError(target_bt_addr, "connect failed")
    except dbus.exceptions.DBusException as exc:
        raise errors.map_dbus_error(exc) from exc
    
    # Wait for GATT services only for LE devices
    if isinstance(device, LEDevice):
        print_and_log(f"[*] Resolving services with timeout of {services_timeout} seconds", LOG__GENERAL)
        if not _wait_for_services(device, timeout=services_timeout):
            raise errors.ServicesNotResolvedError(target_bt_addr)
    
    # Trigger enumeration and build compatibility maps
    _ = device.services_resolved()
    
    # Perform device type classification with passive mode
    # (passive_scan_and_connect is fast, single-attempt scan)
    try:
        if hasattr(device, "get_device_type"):
            device_type = device.get_device_type(scan_mode="passive")
            if device_type:
                print_and_log(f"[*] Device type: {device_type}", LOG__GENERAL)
    except Exception as e:
        print_and_log(f"[*] Device type classification: {e}", LOG__DEBUG)
    
    # Log device type information for user visibility
    if hasattr(device, "device_type_flags"):
        types = device.device_type_flags
        type_str = ", ".join(k for k, v in types.items() if v)
        print_and_log(f"[*] Device types detected: {type_str}", LOG__GENERAL)
    
    # Return tuple in monolith order
    return (
        device,
        getattr(device, "ble_device__mapping", {}),
        getattr(device, "ble_device__mine_mapping", {}),
        getattr(device, "ble_device__permission_mapping", {}),
    )

# 2. Naggy Scan Implementation
def naggy_scan_and_connect(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    max_retries: int = 10,
    *,
    transport: str = "auto",
) -> Tuple[LEDevice, Dict[int, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Persistent scan with multiple connection attempts and exponential backoff.
    
    This mode is designed for unreliable devices or environments with 
    interference. It will repeatedly try to connect with increasing delays
    between attempts.
    
    Parameters
    ----------
    target_bt_addr: str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF"). Case-insensitive.
    landmine_mapping / security_mapping: dict | None
        Legacy parameters kept for compatibility but not used internally.
    max_retries: int
        Maximum number of connection attempts (default 10).
    transport: str
        Bluetooth transport filter ("auto", "le", "bredr") as described in
        ``passive_scan_and_connect``. Controls discovery filter only.
    
    Returns
    -------
    tuple
        (device, mapping, landmine_map, perm_map)
    """
    print_and_log(f"[*] naggy_scan_and_connect::target = {target_bt_addr}", LOG__DEBUG)
    print_and_log(f"[*] Using naggy mode - will persistently attempt connections", LOG__GENERAL)
    
    # Normalize address
    target_bt_addr = target_bt_addr.strip().upper()
    
    # Check adapter
    adapter = _get_adapter()
    
    # Scan for device with more attempts
    if not _scan_until_visible(
        target_bt_addr, max_attempts=5, timeout=8, transport=transport
    ):
        raise errors.DeviceNotFoundError(target_bt_addr)
    
    # Create device
    if transport.lower() == "bredr":
        device = ClassicDevice(target_bt_addr)
    else:
        device = LEDevice(target_bt_addr)
    
    # Attempt to connect with exponential backoff
    attempt = 0
    last_error = None
    
    while attempt < max_retries:
        try:
            print_and_log(f"[*] Connection attempt {attempt + 1}/{max_retries}", LOG__GENERAL)
            
            # Add jitter to avoid exact collision patterns
            backoff_time = min(0.5 * (2 ** attempt) + random.uniform(0, 0.5), 30)
            
            if attempt > 0:
                print_and_log(f"[*] Waiting {backoff_time:.2f} seconds before retry", LOG__GENERAL)
                time.sleep(backoff_time)
            
            if device.connect(retry=2, wait_timeout=5):
                # Connection succeeded, now wait for services
                print_and_log(f"[*] Connection established, resolving services...", LOG__GENERAL)
                
                # Wait longer for services in naggy mode
                if _wait_for_services(device, timeout=20):
                    # Services resolved successfully
                    _ = device.services_resolved()
                    
                    # Perform device type classification with naggy mode
                    # (naggy_scan_and_connect uses persistent connection attempts)
                    try:
                        if hasattr(device, "get_device_type"):
                            device_type = device.get_device_type(scan_mode="naggy")
                            if device_type:
                                print_and_log(f"[*] Device type: {device_type}", LOG__GENERAL)
                        elif hasattr(device, "check_device_type"):
                            # LE device - check_device_type is called internally
                            device.check_device_type()
                    except Exception as e:
                        print_and_log(f"[*] Device type classification: {e}", LOG__DEBUG)
                    
                    print_and_log(f"[+] Services resolved successfully after {attempt + 1} attempts", LOG__GENERAL)
                    return (
                        device,
                        getattr(device, "ble_device__mapping", {}),
                        getattr(device, "ble_device__mine_mapping", {}),
                        getattr(device, "ble_device__permission_mapping", {}),
                    )
                else:
                    print_and_log(f"[-] Failed to resolve services", LOG__GENERAL)
            else:
                print_and_log(f"[-] Connection attempt failed", LOG__GENERAL)
                
        except dbus.exceptions.DBusException as exc:
            error = errors.map_dbus_error(exc)
            last_error = error
            error_name = exc.get_dbus_name()
            print_and_log(f"[-] D-Bus error: {error_name}", LOG__GENERAL)
            
            # For some specific errors, we might want to try again immediately
            if "InProgress" in error_name or "Failed" in error_name:
                # Reduce backoff for these common errors
                attempt -= 1  # Don't count this as a full attempt
                time.sleep(1)  # Just wait a second and retry
        
        attempt += 1
    
    # If we reach here, all retries failed
    if last_error:
        raise last_error
    else:
        raise errors.ConnectionError(target_bt_addr, f"Failed after {max_retries} connection attempts")

# 3. Pokey Scan Implementation
def pokey_scan_and_connect(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    *,
    transport: str = "auto",
) -> Tuple[LEDevice, Dict[int, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Slow, thorough enumeration with extended timeouts.
    
    This mode is designed for complex devices with many services or slow
    response times. It takes longer but is more thorough in enumeration.
    
    Parameters
    ----------
    target_bt_addr: str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF"). Case-insensitive.
    landmine_mapping / security_mapping: dict | None
        Legacy parameters kept for compatibility but not used internally.
    transport: str
        Bluetooth transport filter ("auto", "le", "bredr") as described in
        ``passive_scan_and_connect``. Controls discovery filter only.
    
    Returns
    -------
    tuple
        (device, mapping, landmine_map, perm_map)
    """
    print_and_log(f"[*] pokey_scan_and_connect::target = {target_bt_addr}", LOG__DEBUG)
    print_and_log(f"[*] Using pokey mode - slow, thorough enumeration with extended timeouts", LOG__GENERAL)
    
    # Normalize address
    target_bt_addr = target_bt_addr.strip().upper()
    
    # Check adapter
    adapter = _get_adapter()
    
    # Longer scan with more attempts
    print_and_log("[*] Performing extended scan...", LOG__GENERAL)
    if not _scan_until_visible(
        target_bt_addr, max_attempts=3, timeout=10, transport=transport
    ):
        raise errors.DeviceNotFoundError(target_bt_addr)
    
    # Create device
    if transport.lower() == "bredr":
        device = ClassicDevice(target_bt_addr)
    else:
        device = LEDevice(target_bt_addr)
    
    print_and_log("[*] Establishing connection with extended timeout...", LOG__GENERAL)
    try:
        # Allow more retries and longer wait times
        if not device.connect(retry=5, wait_timeout=10):
            raise errors.ConnectionError(target_bt_addr, "connect failed")
    except dbus.exceptions.DBusException as exc:
        raise errors.map_dbus_error(exc) from exc
    
    # Wait much longer for services to resolve
    print_and_log("[*] Waiting for service resolution (extended timeout)...", LOG__GENERAL)
    if _wait_for_services(device, timeout=30):
        print_and_log("[*] Performing deep enumeration of characteristics...", LOG__GENERAL)
        
        # Trigger enumeration and build compatibility maps
        services_json = device.services_resolved()
        
        # Perform device type classification with pokey mode
        # (pokey_scan_and_connect uses extended timeouts and thorough enumeration)
        try:
            if hasattr(device, "get_device_type"):
                device_type = device.get_device_type(scan_mode="pokey")
                if device_type:
                    print_and_log(f"[*] Device type: {device_type}", LOG__GENERAL)
            elif hasattr(device, "check_device_type"):
                # LE device - check_device_type is called internally
                device.check_device_type()
        except Exception as e:
            print_and_log(f"[*] Device type classification: {e}", LOG__DEBUG)
        
        # In pokey mode, we read value/properties of each characteristic 
        # to ensure maximum information gathering
        error_count = 0
        
        for service in device._services:
            for char in service.characteristics:
                try:
                    # Try to read the characteristic value with a longer timeout
                    try:
                        value = char.read_value(timeout=10)
                        print_and_log(f"[+] Read value for {char.uuid}: {value.hex()}", LOG__DEBUG)
                    except Exception as e:
                        print_and_log(f"[-] Could not read {char.uuid}: {str(e)}", LOG__DEBUG)
                        
                    # Record all properties of the characteristic
                    for prop_name in char._properties():
                        try:
                            _ = char.get_property(prop_name)
                        except Exception:
                            pass
                    
                    # If there are descriptors, try to read them too
                    for desc in getattr(char, "descriptors", []):
                        try:
                            _ = desc.read_value()
                        except Exception as e:
                            print_and_log(f"[-] Could not read descriptor {desc.uuid}: {str(e)}", LOG__DEBUG)
                            
                except Exception as e:
                    error_count += 1
                    print_and_log(f"[-] Error during deep enumeration: {str(e)}", LOG__DEBUG)
                
        print_and_log(f"[*] Deep enumeration complete. Encountered {error_count} errors.", LOG__GENERAL)
        
        # Return tuple in monolith order
        return (
            device,
            getattr(device, "ble_device__mapping", {}),
            getattr(device, "ble_device__mine_mapping", {}),
            getattr(device, "ble_device__permission_mapping", {}),
        )
    else:
        raise errors.ServicesNotResolvedError(target_bt_addr)

# 4. Bruteforce Scan Implementation
def bruteforce_scan_and_connect(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    start_handle: int = 0x0001,
    end_handle: int = 0xFFFF,
) -> Tuple[LEDevice, Dict[int, str], Dict[str, List[str]], Dict[str, List[str]]]:
    """Exhaustive characteristic testing trying all possible handle values.
    
    This mode attempts to access every possible handle value, ignoring
    permission errors, to map all accessible characteristics. This is the
    most aggressive and thorough scanning mode.
    
    Parameters
    ----------
    target_bt_addr: str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF"). Case-insensitive.
    landmine_mapping / security_mapping: dict | None
        Legacy parameters kept for compatibility but not used internally.
    start_handle: int
        First handle value to check (default 0x0001)
    end_handle: int
        Last handle value to check (default 0xFFFF)
    
    Returns
    -------
    tuple
        (device, mapping, landmine_map, perm_map)
    """
    print_and_log(f"[*] bruteforce_scan_and_connect::target = {target_bt_addr}", LOG__DEBUG)
    print_and_log(f"[*] Using bruteforce mode - attempting all possible handles regardless of permissions", LOG__GENERAL)
    
    # First use pokey mode to establish a connection and get the standard enumeration
    device, mapping, mine_map, perm_map = pokey_scan_and_connect(
        target_bt_addr, 
        landmine_mapping,
        security_mapping
    )
    
    # Now perform additional bruteforce enumeration of possible handles
    # even if they weren't discovered through standard methods
    print_and_log(f"[*] Starting bruteforce handle scan from 0x{start_handle:04x} to 0x{end_handle:04x}", LOG__GENERAL)
    
    # Store discovered handles that weren't in the original mapping
    bruteforce_discovered = {}
    bruteforce_errors = {}
    
    # Create a set of already known handles to avoid duplicates
    known_handles = set(mapping.keys())
    
    # Limit the range to be reasonable and avoid extremely long scans
    # Cap at 0x00FF (255) for general usage, unless specifically overridden
    if end_handle > 0x00FF and end_handle == 0xFFFF:
        end_handle = 0x00FF
        print_and_log("[*] Limiting handle range to 0x00FF for reasonable scan time", LOG__GENERAL)
    
    total_handles = end_handle - start_handle + 1
    check_increment = max(1, total_handles // 100)  # Print progress every 1%
    
    for handle in range(start_handle, end_handle + 1):
        if handle % check_increment == 0:
            progress = ((handle - start_handle) / total_handles) * 100
            print_and_log(f"[*] Bruteforce progress: {progress:.1f}% (handle 0x{handle:04x})", LOG__GENERAL)
        
        # Skip handles we already know about
        if handle in known_handles:
            continue
            
        # Try to read the handle directly
        try:
            # We don't have a direct handle read method in the refactored version,
            # so we create a temporary char_path for reading by handle
            for service in device._services:
                try:
                    # Attempt to create a temporary Characteristic with this handle
                    # This is a hack for bruteforce exploration only
                    temp_char = Characteristic(
                        service, 
                        f"{service.path}/char{handle:04x}",
                        "00000000-0000-0000-0000-000000000000"  # Placeholder UUID
                    )
                    temp_char.handle = handle
                    
                    # Try to read value and write common test values
                    value = temp_char.read_value(timeout=5)
                    
                    # If we get here, the handle exists and is readable!
                    print_and_log(f"[+] Bruteforce discovered readable handle 0x{handle:04x}: {value.hex()}", LOG__GENERAL)
                    bruteforce_discovered[handle] = f"unknown-{handle:04x}"
                    
                    # Try to write a test value
                    try:
                        # Try to write different values with different flags
                        for test_value, flags in [
                            (bytes([0x00]), {}),  # Simple zero
                            (bytes([0x01]), {}),  # Simple one
                            (bytes([handle & 0xFF]), {}),  # Handle's low byte
                            (bytes([0x00]), {"type": "command"}),  # Command write
                            (bytes([0x01]), {"type": "request"}),  # Request write
                        ]:
                            temp_char.write_value(test_value, flags)
                            print_and_log(f"[+] Successfully wrote {test_value.hex()} to handle 0x{handle:04x}", LOG__DEBUG)
                    except Exception as e:
                        # Not writable, that's fine
                        print_and_log(f"[-] Handle 0x{handle:04x} not writable: {str(e)}", LOG__DEBUG)
                    
                    break  # No need to try other services
                except Exception:
                    continue
        except Exception as e:
            # Record the error for this handle
            error_type = type(e).__name__
            error_msg = str(e)
            bruteforce_errors[handle] = f"{error_type}: {error_msg}"
            
            # Don't log normal permission errors to avoid spam
            if not (isinstance(e, errors.PermissionDeniedError) or "NotPermitted" in error_msg or "NotAuthorized" in error_msg):
                print_and_log(f"[-] Handle 0x{handle:04x} error: {error_msg}", LOG__DEBUG)
    
    # Update the mapping with our bruteforce discoveries
    mapping.update(bruteforce_discovered)
    
    # Update landmine/security maps for newly discovered characteristics
    for handle, uuid in bruteforce_discovered.items():
        mine_map[uuid] = ["read"]  # At minimum it's readable
        perm_map[uuid] = ["read"]
    
    print_and_log(f"[+] Bruteforce scan complete. Discovered {len(bruteforce_discovered)} additional handles", LOG__GENERAL)
    
    # Perform device type classification with bruteforce mode
    # (bruteforce_scan_and_connect uses exhaustive characteristic testing)
    try:
        if hasattr(device, "get_device_type"):
            device_type = device.get_device_type(scan_mode="bruteforce")
            if device_type:
                print_and_log(f"[*] Device type: {device_type}", LOG__GENERAL)
        elif hasattr(device, "check_device_type"):
            # LE device - check_device_type is called internally
            device.check_device_type()
    except Exception as e:
        print_and_log(f"[*] Device type classification: {e}", LOG__DEBUG)
    
    # Return tuple in monolith order
    return device, mapping, mine_map, perm_map

# Utility function to select appropriate scan mode
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
    target_bt_addr: str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF"). Case-insensitive.
    mode: str
        Scan mode: "ble_passive", "ble_naggy", "ble_pokey", or "ble_bruteforce"
    landmine_mapping / security_mapping: dict | None
        Legacy parameters kept for compatibility but not used internally.
    **kwargs:
        Additional parameters passed to the specific scan function.
    
    Returns
    -------
    tuple
        (device, mapping, landmine_map, perm_map)
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