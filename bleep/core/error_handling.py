#!/usr/bin/python3

import dbus
import dbus.exceptions
from typing import Dict, Optional, Tuple, Union

from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.bt_ref.utils import *
from bleep.core.log import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Rich BlueZ/DBus → RESULT_ERR mapping  (monolith table distilled)
# ---------------------------------------------------------------------------

_DBUS_ERROR_NAME_MAP = {
    # Generic failures ---------------------------------------------------
    "org.freedesktop.DBus.Error.NoReply": RESULT_ERR_NO_REPLY,
    "org.freedesktop.DBus.Error.UnknownObject": RESULT_ERR_UNKNOWN_OBJECT,
    "org.freedesktop.DBus.Error.UnknownMethod": RESULT_ERR_METHOD_SIGNATURE_NOT_EXIST,
    # BlueZ specific ------------------------------------------------------
    "org.bluez.Error.NotConnected": RESULT_ERR_NOT_CONNECTED,
    "org.bluez.Error.Failed": RESULT_ERR,
    "org.bluez.Error.NotPermitted": RESULT_ERR_NOT_PERMITTED,
    "org.bluez.Error.NotAuthorized": RESULT_ERR_NOT_AUTHORIZED,
    "org.bluez.Error.NotSupported": RESULT_ERR_NOT_SUPPORTED,
    "org.bluez.Error.InProgress": RESULT_ERR_ACTION_IN_PROGRESS,
    "org.bluez.Error.InvalidArguments": RESULT_ERR_BAD_ARGS,
    # GATT specific – BlueZ sometimes surfaces as InvalidArguments
    "org.bluez.Error.NotFound": RESULT_ERR_NOT_FOUND,
}

# Fallback substring search when name not present (BlueZ mixes English strings)
_DBUS_MESSAGE_MAP = {
    "Not Connected": RESULT_ERR_NOT_CONNECTED,
    "Connection Attempt Failed": RESULT_ERR_UNKNOWN_CONNECT_FAILURE,
    "Operation already in progress": RESULT_ERR_ACTION_IN_PROGRESS,
    "Authentication Failed": RESULT_ERR_ACCESS_DENIED,
    "Timeout": RESULT_ERR_NO_REPLY,
    # Heuristics for granular permissions (BlueZ error messages often include
    # the operation verb preceding "not permitted")
    "read not permitted": RESULT_ERR_READ_NOT_PERMITTED,
    "write not permitted": RESULT_ERR_WRITE_NOT_PERMITTED,
    "notify not permitted": RESULT_ERR_NOTIFY_NOT_PERMITTED,
    "indicate not permitted": RESULT_ERR_INDICATE_NOT_PERMITTED,
    "not permitted": RESULT_ERR_NOT_PERMITTED,  # fallback generic
}


def decode_dbus_error(exc: dbus.exceptions.DBusException) -> int:
    """Return RESULT_ERR_* constant matching *exc*.

    Follows the detailed mapping rules from the monolith.  Falls back to
    RESULT_ERR on unknown errors.
    """

    name = exc.get_dbus_name()
    if name in _DBUS_ERROR_NAME_MAP:
        return _DBUS_ERROR_NAME_MAP[name]

    msg = (exc.get_dbus_message() or "").lower()
    for substr, code in _DBUS_MESSAGE_MAP.items():
        if substr.lower() in msg:
            return code

    return RESULT_ERR


class system_dbus__error_handling_service:
    """Core service for handling Bluetooth errors while maintaining compatibility
    with existing error handling patterns."""

    def __init__(self):
        self.error_buffer = []
        self.error_mapping = {
            RESULT_OK: "Operation completed successfully",
            RESULT_ERR: "General error occurred",
            RESULT_ERR_NOT_CONNECTED: "Device not connected",
            RESULT_ERR_NOT_SUPPORTED: "Operation not supported",
            RESULT_ERR_SERVICES_NOT_RESOLVED: "Services not resolved",
            RESULT_ERR_WRONG_STATE: "Device in wrong state",
            RESULT_ERR_ACCESS_DENIED: "Access denied",
            RESULT_ERR_BAD_ARGS: "Invalid arguments provided",
            RESULT_ERR_NOT_FOUND: "Resource not found",
            RESULT_ERR_METHOD_SIGNATURE_NOT_EXIST: "Method signature does not exist",
            RESULT_ERR_NO_DEVICES_FOUND: "No devices found",
            RESULT_ERR_NO_BR_CONNECT: "BR/EDR connection failed",
            RESULT_ERR_READ_NOT_PERMITTED: "Read operation not permitted",
            RESULT_ERR_WRITE_NOT_PERMITTED: "Write operation not permitted",
            RESULT_ERR_NOTIFY_NOT_PERMITTED: "Notify operation not permitted",
            RESULT_ERR_INDICATE_NOT_PERMITTED: "Indicate operation not permitted",
            RESULT_ERR_NOT_PERMITTED: "Operation not permitted",
            RESULT_ERR_NOT_AUTHORIZED: "Not authorized to perform operation",
            RESULT_ERR_NO_REPLY: "No reply received",
            RESULT_ERR_DEVICE_FORGOTTEN: "Device has been forgotten",
            RESULT_ERR_ACTION_IN_PROGRESS: "Action already in progress",
            RESULT_ERR_UNKNOWN_SERVCE: "Unknown service",
            RESULT_ERR_UNKNOWN_OBJECT: "Unknown object",
            RESULT_ERR_REMOTE_DISCONNECT: "Remote device disconnected",
            RESULT_ERR_UNKNOWN_CONNECT_FAILURE: "Unknown connection failure",
            RESULT_ERR_METHOD_CALL_FAIL: "Method call failed",
        }

    def evaluate__error_code(self, error_code: int) -> Tuple[bool, str]:
        """Evaluate an error code and return success status and message."""
        if error_code == RESULT_OK:
            return True, self.error_mapping[RESULT_OK]
        return False, self.error_mapping.get(error_code, "Unknown error")

    def evaluate__dbus_error(
        self, error: dbus.exceptions.DBusException
    ) -> Tuple[int, str]:
        """Evaluate a D-Bus error and return appropriate error code and message."""
        error_name = error.get_dbus_name()
        error_message = error.get_dbus_message() or ""
        error_message_lower = error_message.lower()
        
        # First check for operation-specific permissions in the message
        if "write not permitted" in error_message_lower:
            return RESULT_ERR_WRITE_NOT_PERMITTED, "Write operation not permitted"
        elif "notify not permitted" in error_message_lower:
            return RESULT_ERR_NOTIFY_NOT_PERMITTED, "Notify operation not permitted"
        elif "indicate not permitted" in error_message_lower:
            return RESULT_ERR_INDICATE_NOT_PERMITTED, "Indicate operation not permitted"
        elif "read not permitted" in error_message_lower:
            return RESULT_ERR_READ_NOT_PERMITTED, "Read operation not permitted"
        
        # Then check for standard error names
        if error_name == "org.freedesktop.DBus.Error.InvalidArgs":
            return RESULT_ERR_BAD_ARGS, "Invalid arguments provided"
        elif error_name == "org.bluez.Error.NotSupported":
            return RESULT_ERR_NOT_SUPPORTED, "Operation not supported"
        elif error_name == "org.bluez.Error.NotPermitted":
            return RESULT_ERR_NOT_PERMITTED, "Operation not permitted"
        elif error_name == "org.bluez.Error.NotAuthorized":
            return RESULT_ERR_NOT_AUTHORIZED, "Not authorized"
        elif error_name == "org.bluez.Error.InvalidValueLength":
            return RESULT_ERR_BAD_ARGS, "Invalid value length"
        elif error_name == "org.bluez.Error.Failed":
            return RESULT_ERR, "Operation failed"

        return RESULT_EXCEPTION, f"Unhandled D-Bus error: {error_name}"

    def add_to__error_buffer(self, error_code: int, error_message: str) -> None:
        """Add error to the error buffer."""
        self.error_buffer.append(
            {
                "code": error_code,
                "message": error_message,
                "timestamp": get_current_timestamp(),
            }
        )

    def clear__error_buffer(self) -> None:
        """Clear the error buffer."""
        self.error_buffer = []

    def get__error_buffer(self) -> list:
        """Return the current error buffer."""
        return self.error_buffer

    def evaluate__device_error_buffer(
        self, device_class_object
    ) -> Tuple[bool, Optional[Dict]]:
        """Evaluate device error buffer using existing error handling patterns."""
        try:
            # Check if device has error buffer
            if not hasattr(device_class_object, "error_buffer"):
                return True, None

            # Get the error buffer
            error_buffer = device_class_object.error_buffer

            # If buffer is empty, return success
            if not error_buffer:
                return True, None

            # Process the most recent error
            latest_error = error_buffer[-1]
            success, message = self.evaluate__error_code(latest_error["code"])

            return success, {
                "code": latest_error["code"],
                "message": message,
                "timestamp": latest_error.get("timestamp", get_current_timestamp()),
            }
        except Exception as e:
            logger.error(f"Failed to evaluate device error buffer: {e}")
            return False, {
                "code": RESULT_EXCEPTION,
                "message": f"Error buffer evaluation failed: {str(e)}",
                "timestamp": get_current_timestamp(),
            }

    def handle__connection_error(
        self, device_address: str, error: Exception
    ) -> Tuple[int, str]:
        """Handle connection-related errors."""
        if isinstance(error, dbus.exceptions.DBusException):
            error_code, message = self.evaluate__dbus_error(error)
        elif isinstance(error, TimeoutError):
            error_code, message = RESULT_ERR_NO_REPLY, "Connection timed out"
        elif isinstance(error, NotSupportedException):
            error_code, message = (
                RESULT_ERR_NOT_SUPPORTED,
                "Connection type not supported",
            )
        else:
            error_code, message = (
                RESULT_ERR_UNKNOWN_CONNECT_FAILURE,
                f"Connection failed: {str(error)}",
            )

        self.add_to__error_buffer(error_code, f"Device {device_address}: {message}")
        return error_code, message

    def handle__service_error(
        self, device_address: str, service_uuid: str, error: Exception
    ) -> Tuple[int, str]:
        """Handle service-related errors."""
        if isinstance(error, dbus.exceptions.DBusException):
            error_code, message = self.evaluate__dbus_error(error)
        elif isinstance(error, NotSupportedException):
            error_code, message = RESULT_ERR_NOT_SUPPORTED, "Service not supported"
        else:
            error_code, message = (
                RESULT_ERR_UNKNOWN_SERVCE,
                f"Service error: {str(error)}",
            )

        self.add_to__error_buffer(
            error_code, f"Device {device_address}, Service {service_uuid}: {message}"
        )
        return error_code, message

    def handle__method_call_error(
        self, method_name: str, error: Exception
    ) -> Tuple[int, str]:
        """Handle method call errors."""
        if isinstance(error, dbus.exceptions.DBusException):
            error_code, message = self.evaluate__dbus_error(error)
        else:
            error_code, message = (
                RESULT_ERR_METHOD_CALL_FAIL,
                f"Method call failed: {str(error)}",
            )

        self.add_to__error_buffer(error_code, f"Method {method_name}: {message}")
        return error_code, message


def get_current_timestamp() -> float:
    """Return current timestamp."""
    from time import time

    return time()
