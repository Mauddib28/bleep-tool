"""
D-Bus Timeout Enforcement Layer

This module provides timeout enforcement for D-Bus method calls to prevent
operations from hanging indefinitely. It wraps standard D-Bus method calls
with configurable timeouts and proper error handling.

Based on best practices from BlueZ examples and documentation.
"""

import threading
import time
import functools
from typing import Any, Dict, Optional, Callable, Tuple, Union, TypeVar, cast

import dbus
import dbus.exceptions
import dbus.mainloop.glib
from gi.repository import GLib

from bleep.bt_ref.constants import (
    RESULT_ERR_NO_REPLY,
    RESULT_ERR_TIMEOUT,
)
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.core.errors import map_dbus_error
from bleep.core.error_handling import controller_stall_mitigation

# Type variables for better type hinting
T = TypeVar('T')
R = TypeVar('R')

# Initialize GLib mainloop for async operations if not already done
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Default timeouts for different operations (seconds)
DEFAULT_TIMEOUTS = {
    "connect": 15,
    "disconnect": 5,
    "pair": 30,
    "get_property": 5,
    "set_property": 5,
    "read": 10,
    "write": 10,
    "start_notify": 5,
    "stop_notify": 5,
    "default": 10,  # Default for any other method
}

class DBusTimeout(Exception):
    """Exception raised when a D-Bus method call times out."""
    
    def __init__(self, method_name: str, timeout: float, device_address: Optional[str] = None):
        self.method_name = method_name
        self.timeout = timeout
        self.device_address = device_address
        message = f"D-Bus method '{method_name}' timed out after {timeout} seconds"
        if device_address:
            message += f" on device {device_address}"
        super().__init__(message)


def with_timeout(
    timeout_category: str = "default",
    custom_timeout: Optional[float] = None,
    device_address: Optional[str] = None
) -> Callable[[Callable[..., R]], Callable[..., R]]:
    """
    Decorator to add timeout enforcement to D-Bus method calls.
    
    Parameters
    ----------
    timeout_category : str
        Category of operation for selecting timeout from DEFAULT_TIMEOUTS
    custom_timeout : Optional[float]
        Custom timeout in seconds, overrides category timeout if provided
    device_address : Optional[str]
        MAC address of the device for error reporting and recovery
    
    Returns
    -------
    Callable
        Decorator function that wraps the D-Bus method call with timeout
    
    Example
    -------
    @with_timeout("connect", device_address="00:11:22:33:44:55")
    def connect_device(device_iface):
        device_iface.Connect()
    """
    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> R:
            # Determine which timeout to use
            timeout = custom_timeout
            if timeout is None:
                timeout = DEFAULT_TIMEOUTS.get(timeout_category, DEFAULT_TIMEOUTS["default"])
            
            # For methods of classes, try to extract device address if available
            device_addr = device_address
            if not device_addr and args and hasattr(args[0], "mac_address"):
                device_addr = args[0].mac_address
            
            # Record method name for better error messages
            method_name = func.__name__
            
            print_and_log(
                f"[DEBUG] Executing {method_name} with {timeout}s timeout",
                LOG__DEBUG
            )
            
            # Create an event to signal completion
            complete_event = threading.Event()
            result: Dict[str, Any] = {"value": None, "error": None}
            
            # Create a thread to run the operation
            def run_operation() -> None:
                try:
                    result["value"] = func(*args, **kwargs)
                except Exception as e:
                    result["error"] = e
                finally:
                    complete_event.set()
            
            # Start operation thread
            operation_thread = threading.Thread(target=run_operation)
            operation_thread.daemon = True
            operation_thread.start()
            
            # Wait for completion or timeout
            if not complete_event.wait(timeout):
                # Operation timed out
                print_and_log(
                    f"[-] D-Bus method {method_name} timed out after {timeout}s"
                    + (f" on device {device_addr}" if device_addr else ""),
                    LOG__GENERAL
                )
                
                # Check if this might be a controller stall (NoReply)
                if device_addr:
                    controller_stall_mitigation(device_addr)
                
                # Raise timeout exception
                raise DBusTimeout(method_name, timeout, device_addr)
            
            # If operation completed but with an error, raise it
            if result["error"]:
                if isinstance(result["error"], dbus.exceptions.DBusException):
                    # Handle D-Bus errors with our error mapping
                    raise map_dbus_error(result["error"])
                else:
                    # Re-raise other exceptions
                    raise result["error"]
            
            # Return the result
            return cast(R, result["value"])
        
        return wrapper
    
    return decorator


def call_method_with_timeout(
    proxy: dbus.proxies.Interface,
    method_name: str,
    args: Tuple = (),
    timeout: float = DEFAULT_TIMEOUTS["default"],
    device_address: Optional[str] = None
) -> Any:
    """
    Call a D-Bus method with timeout enforcement.
    
    Parameters
    ----------
    proxy : dbus.proxies.Interface
        D-Bus interface proxy object
    method_name : str
        Name of the method to call
    args : Tuple
        Arguments to pass to the method
    timeout : float
        Timeout in seconds
    device_address : Optional[str]
        MAC address of the device for error reporting and recovery
    
    Returns
    -------
    Any
        Result of the method call
    
    Raises
    ------
    DBusTimeout
        If the method call times out
    Exception
        Any exception raised by the method call
    """
    # Create GLib main loop
    loop = GLib.MainLoop()
    result: Dict[str, Any] = {"completed": False, "value": None, "error": None}
    
    # Callback for method completion
    def method_cb(proxy_obj, res, user_data):
        try:
            result["value"] = getattr(proxy_obj, f"{method_name}_finish")(res)
        except Exception as e:
            result["error"] = e
        result["completed"] = True
        loop.quit()
    
    # Start method call asynchronously
    method_async = getattr(proxy, f"{method_name}_async", None)
    if method_async:
        method_async(*args, reply_handler=method_cb, error_handler=lambda e: None)
    else:
        # Fallback for proxies without async methods
        def run_sync():
            try:
                method = getattr(proxy, method_name)
                result["value"] = method(*args)
            except Exception as e:
                result["error"] = e
            finally:
                result["completed"] = True
                loop.quit()
        
        GLib.idle_add(run_sync)
    
    # Set up timeout
    timeout_id = GLib.timeout_add_seconds(int(timeout), lambda: loop.quit())
    
    # Run loop until completion or timeout
    loop.run()
    
    # Clean up timeout source
    GLib.source_remove(timeout_id)
    
    # Handle result
    if not result["completed"]:
        # Operation timed out
        print_and_log(
            f"[-] D-Bus method {method_name} timed out after {timeout}s"
            + (f" on device {device_address}" if device_address else ""),
            LOG__GENERAL
        )
        
        # Check if this might be a controller stall (NoReply)
        if device_address:
            controller_stall_mitigation(device_address)
        
        # Raise timeout exception
        raise DBusTimeout(method_name, timeout, device_address)
    
    # If operation completed but with an error, raise it
    if result["error"]:
        if isinstance(result["error"], dbus.exceptions.DBusException):
            # Handle D-Bus errors with our error mapping
            raise map_dbus_error(result["error"])
        else:
            # Re-raise other exceptions
            raise result["error"]
    
    # Return the result
    return result["value"]


class TimeoutProperties:
    """
    Wrapper for D-Bus Properties interface with timeout enforcement.
    
    This class wraps a standard dbus.Interface(obj, "org.freedesktop.DBus.Properties")
    interface and adds timeout enforcement to Get/Set/GetAll methods.
    """
    def __init__(self, props_interface: dbus.Interface, timeout: float = DEFAULT_TIMEOUTS["get_property"], 
                 device_address: Optional[str] = None):
        """
        Initialize with a D-Bus Properties interface.
        
        Parameters
        ----------
        props_interface : dbus.Interface
            D-Bus Properties interface
        timeout : float
            Default timeout for property operations
        device_address : Optional[str]
            MAC address of the device for error reporting and recovery
        """
        self._props = props_interface
        self._timeout = timeout
        self._device_address = device_address
    
    def Get(self, interface: str, prop: str, timeout: Optional[float] = None) -> Any:
        """Get a property value with timeout enforcement."""
        actual_timeout = timeout if timeout is not None else self._timeout
        return call_method_with_timeout(
            self._props, 
            "Get", 
            (interface, prop), 
            timeout=actual_timeout,
            device_address=self._device_address
        )
    
    def Set(self, interface: str, prop: str, value: Any, timeout: Optional[float] = None) -> None:
        """Set a property value with timeout enforcement."""
        actual_timeout = timeout if timeout is not None else self._timeout
        return call_method_with_timeout(
            self._props, 
            "Set", 
            (interface, prop, value), 
            timeout=actual_timeout,
            device_address=self._device_address
        )
    
    def GetAll(self, interface: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Get all properties with timeout enforcement."""
        actual_timeout = timeout if timeout is not None else self._timeout
        return call_method_with_timeout(
            self._props, 
            "GetAll", 
            (interface,), 
            timeout=actual_timeout,
            device_address=self._device_address
        )


class TimeoutDBusInterface:
    """
    Wrapper for D-Bus Interface with timeout enforcement.
    
    This class wraps a standard dbus.Interface and adds timeout enforcement
    to method calls.
    """
    def __init__(self, interface: dbus.Interface, default_timeout: float = DEFAULT_TIMEOUTS["default"],
                 device_address: Optional[str] = None):
        """
        Initialize with a D-Bus interface.
        
        Parameters
        ----------
        interface : dbus.Interface
            D-Bus interface to wrap
        default_timeout : float
            Default timeout for method calls
        device_address : Optional[str]
            MAC address of the device for error reporting and recovery
        """
        self._interface = interface
        self._default_timeout = default_timeout
        self._device_address = device_address
    
    def __getattr__(self, name: str) -> Callable[..., Any]:
        """
        Dynamically create wrapper methods for interface methods.
        
        Parameters
        ----------
        name : str
            Name of the method to call
        
        Returns
        -------
        Callable
            Wrapped method with timeout enforcement
        """
        # Get the original method
        orig_method = getattr(self._interface, name)
        
        # Only wrap callables
        if not callable(orig_method):
            return orig_method
        
        # Choose appropriate timeout based on method name
        timeout_category = "default"
        for category in DEFAULT_TIMEOUTS:
            if category.lower() in name.lower():
                timeout_category = category
                break
        
        @functools.wraps(orig_method)
        def wrapped_method(*args: Any, **kwargs: Any) -> Any:
            # Extract timeout from kwargs if provided
            timeout = kwargs.pop("timeout", None)
            if timeout is None:
                timeout = DEFAULT_TIMEOUTS.get(timeout_category, self._default_timeout)
            
            print_and_log(
                f"[DEBUG] Calling D-Bus method {name} with {timeout}s timeout",
                LOG__DEBUG
            )
            
            try:
                return call_method_with_timeout(
                    self._interface,
                    name,
                    args,
                    timeout=timeout,
                    device_address=self._device_address
                )
            except Exception as e:
                print_and_log(
                    f"[-] D-Bus method {name} failed: {str(e)}",
                    LOG__DEBUG
                )
                raise
        
        return wrapped_method
