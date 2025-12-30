#!/usr/bin/python3

"""Core error classes for the BLEEP (Bluetooth Landscape Exploration & Enumeration Platform) project."""

from __future__ import annotations

import dbus.exceptions
import re
import time
from bleep.bt_ref.constants import *
from typing import Optional
from bleep.core import log as _core_log

# Regex to pull method & interface names from D-Bus error strings (best-effort)
_METHOD_CALL_INTERFACE_RX = re.compile(
    r"method '(?P<method>[^']+)'[\s\S]*interface '(?P<iface>[^']+)'"
)

# ---------------------------------------------------------------------------
# Compatibility constants expected by legacy tests / helpers
# ---------------------------------------------------------------------------
# The monolith used RESULT_ERR_IN_PROGRESS whereas the constants module
# defines RESULT_ERR_ACTION_IN_PROGRESS (value 16).  Provide an alias so
# external references continue to resolve without altering the upstream
# constant list.
try:
    RESULT_ERR_IN_PROGRESS  # type: ignore[name-defined]
except NameError:  # pragma: no cover – define only if missing
    RESULT_ERR_IN_PROGRESS = RESULT_ERR_ACTION_IN_PROGRESS  # type: ignore


class BLEEPError(Exception):
    """Base exception all legacy code raises.

    The `.code` attribute maps to bluetooth_constants RESULT_* values so the
    rest of the system can keep using integer status codes until refactor is
    finished.
    """

    def __init__(self, message: str, code: int = RESULT_ERR):
        super().__init__(message)
        self.code = code


class DeviceNotFoundError(BLEEPError):
    """Raised when a Bluetooth device cannot be found."""

    def __init__(self, device_address: str):
        super().__init__(f"Device {device_address} not found", RESULT_ERR_NOT_FOUND)
        self.device_address = device_address


class ConnectionError(BLEEPError):
    """Raised when a connection to a Bluetooth device fails."""

    def __init__(self, device_address: str, reason: Optional[str] = None):
        msg = f"Failed to connect to device {device_address}"
        if reason:
            msg += f": {reason}"
        super().__init__(msg, RESULT_ERR_NOT_CONNECTED)
        self.device_address = device_address
        self.reason = reason


class ServiceNotFoundError(BLEEPError):
    """Raised when a service cannot be found on a device."""

    def __init__(self, device_address: str, service_uuid: str):
        super().__init__(
            f"Service {service_uuid} not found on device {device_address}",
            RESULT_ERR_UNKNOWN_SERVCE,
        )
        self.device_address = device_address
        self.service_uuid = service_uuid


class ServicesNotResolvedError(BLEEPError):
    """Raised when services have not been resolved for a device."""

    def __init__(self, device_address: str):
        super().__init__(
            f"Services not resolved for device {device_address}",
            RESULT_ERR_SERVICES_NOT_RESOLVED,
        )
        self.device_address = device_address


class OperationInProgressError(BLEEPError):
    """Raised when an operation is already in progress."""

    def __init__(self, operation: str):
        super().__init__(
            f"Operation already in progress: {operation}", RESULT_ERR_ACTION_IN_PROGRESS
        )
        self.operation = operation


class PermissionError(BLEEPError):
    """Raised when an operation is not permitted."""

    def __init__(self, operation: str, reason: str = None):
        message = f"Operation not permitted: {operation}"
        if reason:
            message += f" ({reason})"
        super().__init__(message, RESULT_ERR_ACCESS_DENIED)
        self.operation = operation
        self.reason = reason


class NotSupportedError(BLEEPError):
    """Raised when an operation is not supported."""

    def __init__(self, operation: str):
        super().__init__(
            f"Operation not supported: {operation}", RESULT_ERR_NOT_SUPPORTED
        )
        self.operation = operation


class TimeoutError(BLEEPError):
    """Raised when an operation times out."""

    def __init__(self, operation: str):
        super().__init__(f"Operation timed out: {operation}", RESULT_ERR_NO_REPLY)
        self.operation = operation


class InvalidArgumentError(BLEEPError):
    """Raised when invalid arguments are provided."""

    def __init__(self, argument: str, reason: str = None):
        message = f"Invalid argument: {argument}"
        if reason:
            message += f" ({reason})"
        super().__init__(message, RESULT_ERR_BAD_ARGS)
        self.argument = argument
        self.reason = reason


class NotReadyError(BLEEPError):
    """Raised when the Bluetooth adapter is powered off or not initialised."""

    def __init__(self):
        super().__init__(
            "Bluetooth adapter not ready. Power on the adapter or enable it via bluetoothctl.",
            RESULT_ERR_WRONG_STATE,
        )


class NotAuthorizedError(BLEEPError):
    """Raised when an operation requires authorization."""

    def __init__(self, operation: str = "Bluetooth operation", reason: str | None = None):
        msg = f"{operation} requires authorization or pairing"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg, RESULT_ERR_ACCESS_DENIED)
        self.operation = operation
        self.reason = reason


# Map D-Bus exceptions to BLEEP exceptions
DBUS_ERROR_MAP = {
    "org.freedesktop.DBus.Error.InvalidArgs": InvalidArgumentError,
    "org.bluez.Error.NotSupported": NotSupportedError,
    "org.bluez.Error.NotPermitted": PermissionError,
    "org.bluez.Error.NotAuthorized": NotAuthorizedError,
    "org.bluez.Error.InvalidValueLength": InvalidArgumentError,
    "org.bluez.Error.Failed": BLEEPError,
}


def map_dbus_error(exc: dbus.exceptions.DBusException) -> BLEEPError:
    """Return a BLEEPError instance for the given D-Bus exception.
    
    This function maps D-Bus exceptions to BLEEP exceptions based on the error name
    and message. It uses the decode_dbus_error function from error_handling.py to
    get the appropriate error code.
    
    Parameters
    ----------
    exc : dbus.exceptions.DBusException
        The D-Bus exception to map
        
    Returns
    -------
    BLEEPError
        A BLEEPError instance with the appropriate error code and message
    """
    name = exc.get_dbus_name()
    msg = exc.get_dbus_message() or ""

    # Import here to avoid circular imports
    from bleep.core.error_handling import decode_dbus_error
    error_code = decode_dbus_error(exc)

    # Fast path mappings using error name
    if name == "org.bluez.Error.NotPermitted":
        # Preserve message payload to distinguish policy/authorization causes.
        return PermissionError("D-Bus operation", msg or str(exc))
    if name == "org.bluez.Error.NotAuthorized":
        # Preserve message payload when present (some BlueZ builds include it).
        return NotAuthorizedError("D-Bus operation", reason=msg or None)
    if name == "org.freedesktop.DBus.Error.NoReply":
        return TimeoutError("D-Bus operation")
    if name == "org.freedesktop.DBus.Error.ServiceUnknown":
        # Preserve payload; BlueZ/DBus often includes the missing service/bus name in msg.
        return ServiceNotFoundError("D-Bus operation", msg or exc.get_dbus_name())
    if name == "org.bluez.Error.InProgress":
        return OperationInProgressError(msg or "D-Bus operation")
    if name == "org.bluez.Error.Failed":
        # Preserve BlueZ's message payload (e.g. "br-connection-unknown") so
        # callers can diagnose controller/state-machine failures.
        if "Not connected" in msg:
            return ConnectionError("D-Bus operation", msg or str(exc))
        if "ATT error" in msg:
            return BLEEPError("D-Bus operation", error_code)
        # Generic org.bluez.Error.Failed: include message text if present
        if msg:
            return BLEEPError(f"D-Bus operation: {name}: {msg}", error_code)
    if name == "org.freedesktop.DBus.Error.UnknownObject":
        # Preserve payload; UnknownObject is not always a "device not found".
        if msg:
            return BLEEPError(f"D-Bus operation: {name}: {msg}", error_code)
        return BLEEPError(f"D-Bus operation: {name}", error_code)

    # Method-call signature error regex
    m = _METHOD_CALL_INTERFACE_RX.search(msg)
    if m:
        return InvalidArgumentError(
            f"Method:{m.group('method')} Interface:{m.group('iface')}",
            f"D-Bus call: {msg}",
        )

    # Default fall-back
    # Preserve message payload for diagnostics (agent/media/connect errors often
    # carry the actionable reason in the message).
    # Include get_dbus_message() in default fall-through mapping for all cases
    if msg:
        return BLEEPError(f"D-Bus operation: {name}: {msg}", error_code)
    return BLEEPError(f"D-Bus operation: {name}", error_code)


def handle_dbus_exception(exc: dbus.exceptions.DBusException):
    err = map_dbus_error(exc)
    _core_log.logging__debug_log(f"[BLEEPError] code={getattr(err, 'code', RESULT_ERR)} msg={exc}")
    if getattr(err, "code", None) == RESULT_ERR_ACTION_IN_PROGRESS:
        time.sleep(0.2)
    raise err


# ---------------------------------------------------------------------------
# Modern aliases expected by refactored services (minimal, no extra logic)
# ---------------------------------------------------------------------------

# Maintain the new camel-case name without breaking old UPPER-CASE usages
BleepError = BLEEPError

# Backwards-compatibility alias used in legacy files
NotReady = NotReadyError

__all__ = [
    "BLEEPError",
    "BleepError",
    "DeviceNotFoundError",
    "ConnectionError",
    "ServiceNotFoundError",
    "ServicesNotResolvedError",
    "OperationInProgressError",
    "PermissionError",
    "NotSupportedError",
    "TimeoutError",
    "InvalidArgumentError",
    "NotReadyError",
    "NotReady",
    "NotAuthorizedError",
    "map_dbus_error",
    "handle_dbus_exception",
]
