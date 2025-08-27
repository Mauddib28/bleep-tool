#!/usr/bin/python3

import dbus
import dbus.exceptions
import functools
from typing import Dict, Optional, Tuple, Union, Callable, Any

from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.bt_ref.utils import *
from bleep.core.log import get_logger, print_and_log, LOG__GENERAL, LOG__DEBUG

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Controller-stall mitigation helper
# ---------------------------------------------------------------------------

def controller_stall_mitigation(mac: str) -> None:
    """Attempt to recover from a controller stall indicated by DBus *NoReply*.

    If environment variable ``BLEEP_AUTO_FIX_STALL`` is set to *1* / *true*,
    a best-effort call to ``bluetoothctl disconnect <MAC>`` is issued.  Any
    failure is logged at DEBUG level and otherwise ignored.  When the env var
    is not set, emit a user-facing message suggesting the manual command.
    """

    import os, subprocess, shlex

    if not mac:
        return

    auto = os.getenv("BLEEP_AUTO_FIX_STALL", "0").lower() in {"1", "true", "yes"}

    if auto:
        cmd = ["bluetoothctl", "disconnect", mac]
        print_and_log(f"[*] Controller stall – running: {' '.join(map(shlex.quote, cmd))}", LOG__GENERAL)
        try:
            subprocess.run(cmd, capture_output=True, check=False, timeout=5)
        except Exception as exc:
            print_and_log(f"[DEBUG] bluetoothctl disconnect failed: {exc}", LOG__DEBUG)
    else:
        print_and_log(
            f"[!] Controller stall detected. Run 'bluetoothctl disconnect {mac}' and retry, or set BLEEP_AUTO_FIX_STALL=1 to automate.",
            LOG__GENERAL,
        )

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


# ---------------------------------------------------------------------------
# Enhanced Error Handling System
# ---------------------------------------------------------------------------

class BlueZErrorHandler:
    """Centralized error handling for BlueZ D-Bus interactions.
    
    This class provides consistent error handling patterns across the codebase,
    with human-friendly error messages, retry mechanics, and context-aware
    error reporting.
    """
    
    # Maps D-Bus error names to user-friendly messages
    ERROR_MESSAGES = {
        "org.bluez.Error.Failed": "Operation failed",
        "org.bluez.Error.InProgress": "Operation already in progress",
        "org.bluez.Error.NotAuthorized": "Not authorized",
        "org.bluez.Error.NotAvailable": "Not available",
        "org.bluez.Error.NotConnected": "Device not connected",
        "org.bluez.Error.NotSupported": "Operation not supported",
        "org.bluez.Error.NotPermitted": "Operation not permitted",
        "org.bluez.Error.InvalidValueLength": "Invalid value length",
        "org.freedesktop.DBus.Error.NoReply": "Controller stalled - try 'bluetoothctl disconnect <MAC>'",
        "org.freedesktop.DBus.Error.UnknownObject": "Object not found",
        "org.freedesktop.DBus.Error.InvalidArgs": "Invalid arguments",
        "org.freedesktop.DBus.Error.UnknownMethod": "Method not found",
    }
    
    # Maps operation types to more specific error messages
    OPERATION_CONTEXT = {
        "read_characteristic": {
            "org.bluez.Error.Failed": "Failed to read characteristic - device may be unavailable or the characteristic might require authentication",
            "org.bluez.Error.NotPermitted": "Reading this characteristic is not permitted - may require pairing or higher privileges",
        },
        "write_characteristic": {
            "org.bluez.Error.Failed": "Failed to write characteristic - device may be unavailable or the characteristic might be read-only",
            "org.bluez.Error.NotPermitted": "Writing to this characteristic is not permitted - may require pairing or higher privileges",
        },
        "start_notify": {
            "org.bluez.Error.Failed": "Failed to enable notifications - characteristic may not support notifications",
            "org.bluez.Error.NotPermitted": "Notifications are not permitted on this characteristic",
        },
        "connect": {
            "org.bluez.Error.Failed": "Failed to connect to device - device may be out of range or unavailable",
            "org.bluez.Error.InProgress": "Connection already in progress - please wait",
        },
    }
    
    @classmethod
    def handle_dbus_error(cls, error, operation=None, device=None, raise_error=False):
        """
        Handle D-Bus exceptions with consistent messaging and logging.
        
        Args:
            error: The caught D-Bus exception
            operation: String describing the attempted operation
            device: Optional device information (MAC or name)
            raise_error: Whether to re-raise the exception after handling
            
        Returns:
            None if error handled, raises exception if raise_error=True
            
        Example:
            try:
                device.connect()
            except dbus.exceptions.DBusException as e:
                BlueZErrorHandler.handle_dbus_error(e, operation="connect", device=device.address)
        """
        error_str = str(error)
        error_name = getattr(error, "get_dbus_name", lambda: "unknown")()
        context = f" during {operation}" if operation else ""
        device_info = f" on device {device}" if device else ""
        
        # If we have a specific message for this operation + error combination, use it
        if (operation and error_name in cls.OPERATION_CONTEXT.get(operation, {})):
            message = cls.OPERATION_CONTEXT[operation][error_name]
            logger.error(f"{message}{device_info}")
            logger.debug(f"Original error: {error_str}")
            
            # Special case for NoReply which might indicate a controller stall
            if error_name == "org.freedesktop.DBus.Error.NoReply" and device:
                controller_stall_mitigation(device)
                
            if raise_error:
                raise error
            
            # Map to BLEEP error code
            error_code = decode_dbus_error(error)
            return error_code
        
        # Otherwise fall back to general error type mapping
        for error_code, message in cls.ERROR_MESSAGES.items():
            if error_code in error_str:
                logger.error(f"{message}{context}{device_info}")
                logger.debug(f"Original error: {error_str}")
                
                # Special case for NoReply which might indicate a controller stall
                if "NoReply" in error_code and device:
                    controller_stall_mitigation(device)
                    
                if raise_error:
                    raise error
                
                # Map to BLEEP error code
                return decode_dbus_error(error)
        
        # If no specific handler found
        logger.error(f"Unexpected D-Bus error{context}{device_info}: {error_str}")
        if raise_error:
            raise error
        
        return RESULT_ERR
    
    @classmethod
    def connection_check(cls, func):
        """
        Decorator to handle connection-related errors consistently.
        
        Automatically attempts to reconnect once if a NotConnected error occurs,
        and provides standardized error handling.
        
        Usage:
            @BlueZErrorHandler.connection_check
            def some_device_method(self, *args, **kwargs):
                # Method implementation
        """
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except dbus.exceptions.DBusException as e:
                if "org.bluez.Error.NotConnected" in str(e):
                    logger.warning(f"Device not connected - attempting to reconnect")
                    try:
                        if hasattr(self, 'connect') and callable(self.connect):
                            self.connect()
                            # Retry the original function
                            return func(self, *args, **kwargs)
                        else:
                            logger.error(f"Cannot reconnect - object doesn't have connect method")
                    except Exception as reconnect_error:
                        cls.handle_dbus_error(
                            reconnect_error, 
                            operation="reconnect attempt", 
                            device=getattr(self, 'address', None)
                        )
                else:
                    cls.handle_dbus_error(
                        e, 
                        operation=func.__name__, 
                        device=getattr(self, 'address', None)
                    )
                # Map to BLEEP error code
                return decode_dbus_error(e)
            except Exception as e:
                logger.error(f"Non-DBus error in {func.__name__}: {e}")
                return RESULT_EXCEPTION
        return wrapper
        
    @classmethod
    def safe_property_access(cls, func):
        """
        Decorator to safely handle property access on potentially disconnected devices.
        
        Adds defensive checks before accessing device properties to avoid errors
        when the device is disconnected or unavailable.
        
        Usage:
            @BlueZErrorHandler.safe_property_access
            def get_device_property(self, property_name):
                # Method implementation
        """
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not hasattr(self, '_obj') or self._obj is None:
                logger.warning(f"Cannot access properties - device object is None")
                return None
                
            try:
                return func(self, *args, **kwargs)
            except dbus.exceptions.DBusException as e:
                cls.handle_dbus_error(
                    e, 
                    operation=f"property access in {func.__name__}", 
                    device=getattr(self, 'address', None)
                )
                return None
            except Exception as e:
                logger.error(f"Error accessing property in {func.__name__}: {e}")
                return None
        return wrapper
    
    @classmethod
    def get_user_friendly_message(cls, error):
        """
        Convert technical error message to user-friendly version.
        
        Args:
            error: D-Bus exception or error message string
            
        Returns:
            User-friendly error message
        """
        if isinstance(error, dbus.exceptions.DBusException):
            error_name = error.get_dbus_name()
            error_message = str(error)
        else:
            error_name = "unknown"
            error_message = str(error)
            
        # Check specific error names first
        for error_code, message in cls.ERROR_MESSAGES.items():
            if error_code in error_message or error_code == error_name:
                return message
                
        # Check for common patterns in message
        if "not permitted" in error_message.lower():
            if "read" in error_message.lower():
                return "You don't have permission to read this data. You may need to pair with the device first."
            elif "write" in error_message.lower():
                return "You don't have permission to write to this device. You may need to pair with the device first."
            else:
                return "Permission denied. You may need higher privileges or to pair with the device."
                
        if "timeout" in error_message.lower():
            return "The operation timed out. The device might be out of range or unresponsive."
            
        if "authentication" in error_message.lower():
            return "Authentication failed. You may need to pair or provide the correct PIN/passkey."
        
        # Generic fallback
        return f"An error occurred: {error_message}"
