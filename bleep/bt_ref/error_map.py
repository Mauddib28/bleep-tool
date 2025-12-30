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
# **DEPRECATED as primary source of truth**: This table is now only used as a
# refinement fallback when core.decode_dbus_error() returns generic RESULT_ERR.
# The canonical decoder is bleep.core.error_handling.decode_dbus_error().
# TODO (B5): After full parity validation, consider removing this table entirely
# and relying solely on core decode + bt_ref-local category normalization.
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
    # Granular GATT permission errors (core decode can surface these via message heuristics)
    RESULT_ERR_READ_NOT_PERMITTED: ERR_CAT_PERMISSION,
    RESULT_ERR_WRITE_NOT_PERMITTED: ERR_CAT_PERMISSION,
    RESULT_ERR_NOTIFY_NOT_PERMITTED: ERR_CAT_PERMISSION,
    RESULT_ERR_INDICATE_NOT_PERMITTED: ERR_CAT_PERMISSION,
    RESULT_ERR_NOT_CONNECTED: ERR_CAT_CONNECTION,
    RESULT_ERR_REMOTE_DISCONNECT: ERR_CAT_CONNECTION,
    RESULT_ERR_NO_BR_CONNECT: ERR_CAT_CONNECTION,
    RESULT_ERR_NO_REPLY: ERR_CAT_PROTOCOL,
    RESULT_ERR_TIMEOUT: ERR_CAT_PROTOCOL,
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
        res = device.Connect()
        # Some legacy interfaces return (code, success) instead of raising.
        if isinstance(res, tuple) and len(res) >= 2:
            if not bool(res[1]):
                raise RuntimeError(f"Reconnect failed (code={res[0]})")
    except dbus.exceptions.DBusException as e:
        debug_log(f"Reconnection attempt failed: {e}")
        raise
    except Exception as e:
        debug_log(f"Reconnection attempt failed: {e}")
        raise


def _resolve_services(device) -> None:
    """Wait for services to be resolved."""
    try:
        res = device.check_and_wait__services_resolved()
        # Some legacy interfaces return bool/tuple; treat False as failure.
        if isinstance(res, tuple) and len(res) >= 2:
            if not bool(res[1]):
                raise RuntimeError(f"Service resolution failed (code={res[0]})")
        elif res is False:
            raise RuntimeError("Service resolution failed (returned False)")
    except dbus.exceptions.DBusException as e:
        debug_log(f"Service resolution failed: {e}")
        raise
    except Exception as e:
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

    # Core-first decode (single source of truth for name/message mapping).
    # Local import avoids introducing module import cycles with bt_ref consumers.
    from bleep.core.error_handling import decode_dbus_error  # local import by design

    result_code = decode_dbus_error(error)

    # bt_ref-local refinement: if core returns generic RESULT_ERR but bt_ref has a
    # more specific name-level mapping for this error, prefer the specific code.
    if result_code == RESULT_ERR:
        specific = DBUS_ERROR_MAP.get(error_name)
        if specific is not None and specific != RESULT_ERR:
            result_code = specific

    # ------------------------------------------------------------------
    # reporting_code vs category_code normalization
    # ------------------------------------------------------------------
    # We want to preserve the *most specific* reporting code we can (from core
    # decode + bt_ref refinement) while keeping recovery categorization stable.
    #
    # Example: core decode may return RESULT_ERR_NOT_PERMITTED; bt_ref historically
    # used RESULT_ERR_ACCESS_DENIED for org.bluez.Error.NotPermitted. Both are
    # "permission" in category terms, but we retain the precise reporting code
    # and allow category derivation to use a compatibility alias when needed.
    category_code = result_code

    # Normalize coarse permission buckets for categorization only.
    if category_code == RESULT_ERR_NOT_PERMITTED:
        category_code = RESULT_ERR_ACCESS_DENIED
    elif category_code in (
        RESULT_ERR_READ_NOT_PERMITTED,
        RESULT_ERR_WRITE_NOT_PERMITTED,
        RESULT_ERR_NOTIFY_NOT_PERMITTED,
        RESULT_ERR_INDICATE_NOT_PERMITTED,
    ):
        category_code = RESULT_ERR_ACCESS_DENIED

    # Category derivation drives recovery behavior.
    category = ERROR_CATEGORIES.get(category_code, ERR_CAT_UNKNOWN)

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


def attempt_operation_with_recovery(
    operation: Callable[[], object],
    *,
    device=None,
    retries: int = 2,
    delay_s: float = 0.7,
) -> Tuple[int, bool]:
    """Run *operation* with bt_ref error mapping + disciplined retries.

    This helper exists to avoid ad-hoc retry loops sprinkled across the codebase.
    It is intentionally conservative to reduce "busy"/InProgress amplification on
    fragile devices:
    - Uses a **fixed delay** between attempts (default 0.7s)
    - Caps retries (default 2)
    - Never retries permission or bad-argument failures

    Returns
    -------
    Tuple[int, bool]
        (result_code, success) where success indicates the operation eventually
        completed without raising.
    """
    from time import sleep

    if retries < 0:
        retries = 0
    if delay_s < 0:
        delay_s = 0.0

    last_code = RESULT_ERR

    for attempt in range(retries + 1):
        try:
            operation()
            return RESULT_OK, True
        except Exception as exc:  # noqa: BLE001
            # Map + attempt recovery (if applicable).
            code, recovered = handle_error(exc, device)
            last_code = code

            # Do not retry on deterministic failures.
            if code in (
                RESULT_ERR_BAD_ARGS,
                RESULT_ERR_ACCESS_DENIED,
                RESULT_ERR_NOT_AUTHORIZED,
                RESULT_ERR_NOT_PERMITTED,
                RESULT_ERR_READ_NOT_PERMITTED,
                RESULT_ERR_WRITE_NOT_PERMITTED,
                RESULT_ERR_NOTIFY_NOT_PERMITTED,
                RESULT_ERR_INDICATE_NOT_PERMITTED,
                RESULT_ERR_NOT_SUPPORTED,
            ):
                return code, False

            # Last attempt exhausted.
            if attempt >= retries:
                return code, False

            # Apply fixed delay before retrying regardless of whether recovery ran.
            sleep(delay_s)
