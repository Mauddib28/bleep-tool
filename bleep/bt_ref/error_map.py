"""
Error mapping and handling for BLEEP.

This module provides centralized error handling, mapping, and recovery strategies
for Bluetooth operations. It maps low-level D-Bus and BlueZ errors to BLEEP's
error codes and provides recovery mechanisms where possible.
"""

from typing import Dict, Optional, Tuple, Callable
import dbus
from bleep.bt_ref.exceptions import *
from bleep.bt_ref.constants import *
from bleep.core.log import logging__debug_log as debug_log

# Error categories
ERR_CAT_PERMISSION = "permission"
ERR_CAT_CONNECTION = "connection"
ERR_CAT_PROTOCOL = "protocol"
ERR_CAT_RESOURCE = "resource"
ERR_CAT_STATE = "state"
ERR_CAT_UNKNOWN = "unknown"

# Map D-Bus error names to BLEEP result codes
DBUS_ERROR_MAP: Dict[str, int] = {
    "org.freedesktop.DBus.Error.AccessDenied": RESULT_ERR_ACCESS_DENIED,
    "org.freedesktop.DBus.Error.InvalidArgs": RESULT_ERR_BAD_ARGS,
    "org.freedesktop.DBus.Error.NoReply": RESULT_ERR_NO_REPLY,
    "org.freedesktop.DBus.Error.ServiceUnknown": RESULT_ERR_UNKNOWN_SERVCE,
    "org.freedesktop.DBus.Error.UnknownObject": RESULT_ERR_UNKNOWN_OBJECT,
    "org.freedesktop.DBus.Error.Failed": RESULT_ERR,
    "org.bluez.Error.NotSupported": RESULT_ERR_NOT_SUPPORTED,
    "org.bluez.Error.NotPermitted": RESULT_ERR_ACCESS_DENIED,
    "org.bluez.Error.InvalidValueLength": RESULT_ERR_BAD_ARGS,
    "org.bluez.Error.Failed": RESULT_ERR,
    "org.bluez.Error.InProgress": RESULT_ERR_ACTION_IN_PROGRESS,
    "org.bluez.Error.AlreadyConnected": RESULT_ERR_WRONG_STATE,
    "org.bluez.Error.NotConnected": RESULT_ERR_NOT_CONNECTED,
    "org.bluez.Error.NotAvailable": RESULT_ERR_NOT_FOUND,
    "org.bluez.Error.DoesNotExist": RESULT_ERR_NOT_FOUND,
}

# Map error codes to categories for grouping similar errors
ERROR_CATEGORIES: Dict[int, str] = {
    RESULT_ERR_ACCESS_DENIED: ERR_CAT_PERMISSION,
    RESULT_ERR_NOT_PERMITTED: ERR_CAT_PERMISSION,
    RESULT_ERR_NOT_AUTHORIZED: ERR_CAT_PERMISSION,
    RESULT_ERR_NOT_CONNECTED: ERR_CAT_CONNECTION,
    RESULT_ERR_REMOTE_DISCONNECT: ERR_CAT_CONNECTION,
    RESULT_ERR_NO_BR_CONNECT: ERR_CAT_CONNECTION,
    RESULT_ERR_NO_REPLY: ERR_CAT_PROTOCOL,
    RESULT_ERR_METHOD_CALL_FAIL: ERR_CAT_PROTOCOL,
    RESULT_ERR_NOT_FOUND: ERR_CAT_RESOURCE,
    RESULT_ERR_NO_DEVICES_FOUND: ERR_CAT_RESOURCE,
    RESULT_ERR_UNKNOWN_SERVCE: ERR_CAT_RESOURCE,
    RESULT_ERR_UNKNOWN_OBJECT: ERR_CAT_RESOURCE,
    RESULT_ERR_WRONG_STATE: ERR_CAT_STATE,
    RESULT_ERR_ACTION_IN_PROGRESS: ERR_CAT_STATE,
    RESULT_ERR_SERVICES_NOT_RESOLVED: ERR_CAT_STATE,
    RESULT_ERR: ERR_CAT_UNKNOWN,
    RESULT_EXCEPTION: ERR_CAT_UNKNOWN,
}


# Recovery strategies for different error categories
def _retry_with_delay(delay_ms: int = 1000) -> None:
    """Basic retry after delay strategy."""
    from time import sleep

    sleep(delay_ms / 1000.0)


def _reconnect_device(device) -> None:
    """Attempt to reconnect a disconnected device."""
    try:
        device.Connect()
    except dbus.exceptions.DBusException as e:
        debug_log(f"Reconnection attempt failed: {e}")
        raise


def _resolve_services(device) -> None:
    """Wait for services to be resolved."""
    try:
        device.check_and_wait__services_resolved()
    except dbus.exceptions.DBusException as e:
        debug_log(f"Service resolution failed: {e}")
        raise


# Map error categories to recovery strategies
RECOVERY_STRATEGIES: Dict[str, Callable] = {
    ERR_CAT_CONNECTION: _reconnect_device,
    ERR_CAT_STATE: _resolve_services,
    ERR_CAT_PROTOCOL: _retry_with_delay,
}


def map_dbus_error(error: dbus.exceptions.DBusException) -> Tuple[int, str]:
    """
    Map a D-Bus exception to a BLEEP result code and error category.

    Args:
        error: The D-Bus exception to map

    Returns:
        Tuple of (result_code, error_category)
    """
    error_name = error.get_dbus_name()
    result_code = DBUS_ERROR_MAP.get(error_name, RESULT_EXCEPTION)
    category = ERROR_CATEGORIES.get(result_code, ERR_CAT_UNKNOWN)

    debug_log(f"Mapped D-Bus error {error_name} to result {result_code} ({category})")
    return result_code, category


def get_recovery_strategy(error_category: str) -> Optional[Callable]:
    """
    Get the recovery strategy for an error category if one exists.

    Args:
        error_category: The error category to get strategy for

    Returns:
        Recovery strategy function or None if no strategy exists
    """
    return RECOVERY_STRATEGIES.get(error_category)


def handle_error(error: Exception, device=None) -> Tuple[int, bool]:
    """
    Handle an error by mapping it and attempting recovery if possible.

    Args:
        error: The exception to handle
        device: Optional device object for device-specific recovery

    Returns:
        Tuple of (result_code, recovered)
        where recovered is True if recovery was successful
    """
    if isinstance(error, dbus.exceptions.DBusException):
        result_code, category = map_dbus_error(error)
    else:
        result_code = RESULT_EXCEPTION
        category = ERR_CAT_UNKNOWN

    debug_log(f"Handling error {type(error).__name__}: {str(error)}")

    # Attempt recovery if we have a strategy
    recovery_fn = get_recovery_strategy(category)
    if recovery_fn and device:
        try:
            recovery_fn(device)
            return result_code, True
        except Exception as e:
            debug_log(f"Recovery failed: {e}")

    return result_code, False
