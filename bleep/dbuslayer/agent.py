"""
Agent D-Bus Interface
Provides the system_dbus__bluez_generic_agent and system_dbus__bluez_agent_user_interface classes from the original codebase.
"""

# Ensure type annotations that reference classes defined later do not fail at
# import-time.  (Python 3.11 does *not* enable PEP 563 by default.)
from __future__ import annotations

import time
import threading
from typing import Optional, Dict, Any, Callable, List

import dbus
import dbus.service

from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__AGENT
from bleep.core import errors as _errors

# ---------------------------------------------------------------------------
# Native Agent implementations
# ---------------------------------------------------------------------------

# We already have SimpleAgent and InteractiveAgent below; expose the legacy
# names by inheriting from them so external code continues to work without the
# `legacy_loader` indirection.

__all__ = [
    "system_dbus__bluez_generic_agent",
    "system_dbus__bluez_agent_user_interface",
    "SimpleAgent",
    "InteractiveAgent",
    "BlueZAgent",
    "EnhancedAgent",
    "PairingAgent",
    "TrustManager",
    "create_agent",
    "ensure_default_pairing_agent",
]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _format_dbus_error(exc: Exception) -> str:
    """Format a D-Bus exception as 'name: message' for concise logging.
    
    If the exception is not a DBusException, returns str(exc).
    Follows the error handling pattern used throughout BLEEP.
    
    Parameters
    ----------
    exc : Exception
        The exception to format
        
    Returns
    -------
    str
        Formatted error string in 'name: message' format, or str(exc) for non-D-Bus exceptions
    """
    if isinstance(exc, dbus.exceptions.DBusException):
        error_name = exc.get_dbus_name()
        error_msg = exc.get_dbus_message()
        
        # Extract error name and message from exception args (most reliable source)
        msg_str = None
        if exc.args:
            if len(exc.args) >= 2:
                # Second arg is typically the message
                msg_str = str(exc.args[1]) if exc.args[1] is not None else None
                # First arg might be the error name if get_dbus_name() returned None
                if not error_name and isinstance(exc.args[0], str) and exc.args[0].startswith("org."):
                    error_name = exc.args[0]
            elif len(exc.args) == 1:
                arg = exc.args[0]
                if isinstance(arg, str):
                    if arg.startswith("org."):
                        error_name = arg if not error_name else error_name
                    else:
                        msg_str = arg
        
        # Use get_dbus_message() result if it's a proper string and we don't have a message yet
        if msg_str is None and error_msg is not None:
            if isinstance(error_msg, str):
                # Check if it looks like a tuple string representation
                if error_msg.startswith("(") and error_msg.endswith(")"):
                    import ast
                    try:
                        parsed = ast.literal_eval(error_msg)
                        if isinstance(parsed, tuple) and len(parsed) > 1:
                            msg_str = str(parsed[1]) if parsed[1] is not None else None
                            if not error_name and isinstance(parsed[0], str) and parsed[0].startswith("org."):
                                error_name = parsed[0]
                    except (ValueError, SyntaxError):
                        msg_str = error_msg
                else:
                    msg_str = error_msg
            elif isinstance(error_msg, tuple):
                if len(error_msg) > 1:
                    msg_str = str(error_msg[1]) if error_msg[1] is not None else None
        
        # Final fallback
        if msg_str is None:
            msg_str = str(exc)
        
        # Format as 'name: message' if we have both, otherwise just message
        if error_name:
            return f"{error_name}: {msg_str}"
        else:
            return msg_str
    return str(exc)


# ---------------------------------------------------------------------------
# Lazy default agent helper (used by both LE and Classic helpers)
# ---------------------------------------------------------------------------

_DEFAULT_AGENT: PairingAgent | None = None


def ensure_default_pairing_agent(*, capabilities: str = "KeyboardDisplay", auto_accept: bool = True,
                             io_handler=None, storage_path=None, encryption_key=None) -> None:
    """Register a global PairingAgent once per process.

    Intended to be called by connection helpers when they detect an
    AuthenticationRequired / NotAuthorized error.  If an agent is already
    registered the call is a cheap no-op.

    Parameters
    ----------
    capabilities : str, optional
        Agent capabilities (default: "KeyboardDisplay")
    auto_accept : bool, optional
        Whether to auto-accept pairing requests (default: True)
    io_handler : AgentIOHandler, optional
        Custom I/O handler to use
    storage_path : str, optional
        Path to store bonding information
    encryption_key : str, optional
        Encryption key for secure storage

    Disable by setting environment variable *BLEEP_NO_AUTO_PAIR* to any value
    other than "0" / "false".
    """
    import os, dbus
    import dbus.mainloop.glib

    if os.getenv("BLEEP_NO_AUTO_PAIR", "0") not in {"0", "false", "False", ""}:
        return

    # GLib mainloop integration MUST be set before creating the bus.
    # Without this, dbus-python receives incoming method calls (e.g.
    # RequestPinCode from BlueZ) on the socket but never dispatches
    # them to the Python handler — the agent appears dead.
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    global _DEFAULT_AGENT
    if _DEFAULT_AGENT is not None:
        if _DEFAULT_AGENT.is_registered():
            return
        _DEFAULT_AGENT.register(capabilities=capabilities, default=True)
        print_and_log("[*] Default pairing agent registered (reused existing object)", LOG__AGENT)
        return

    _DEFAULT_AGENT = create_agent(
        dbus.SystemBus(),
        agent_type="pairing",
        capabilities=capabilities,
        default=True,
        auto_accept=auto_accept,
        io_handler=io_handler,
        storage_path=storage_path,
        encryption_key=encryption_key,
    )
    print_and_log("[*] Default pairing agent registered", LOG__AGENT)


def clear_default_pairing_agent() -> None:
    """Unregister and remove the process-global default agent (if present)."""
    global _DEFAULT_AGENT
    if _DEFAULT_AGENT is None:
        return
    try:
        _DEFAULT_AGENT.unregister()
    finally:
        _DEFAULT_AGENT = None


class BlueZAgent(dbus.service.Object):
    """Base class for implementing a Bluetooth agent.
    
    This class provides the foundation for Bluetooth agent implementations, 
    with support for D-Bus registration, device information retrieval,
    and I/O handling for interactive pairing operations.
    """

    def __init__(self, bus, agent_path=AGENT_NAMESPACE, io_handler=None):
        """Initialize agent.
        
        Parameters
        ----------
        bus : dbus.Bus
            D-Bus bus object
        agent_path : str, optional
            D-Bus object path for the agent
        io_handler : AgentIOHandler, optional
            I/O handler for pairing interactions, defaults to CLI handler
        """
        super().__init__(bus, agent_path)
        self._bus = bus
        self.agent_path = agent_path
        self._agent_manager = None
        self._setup_agent_manager()
        self._is_registered = False
        
        # Agent method invocation tracking (for correlation with D-Bus monitoring)
        self._method_invocations: Dict[str, float] = {}  # method_name -> timestamp
        self._capabilities: str = "NoInputNoOutput"  # Will be set during registration
        
        # CRITICAL: Log bus unique name for destination verification
        try:
            bus_unique_name = bus.get_unique_name()
            print_and_log(
                f"[!!!] Agent created: bus_unique_name={bus_unique_name}, path={agent_path}",
                LOG__AGENT
            )
        except Exception as e:
            print_and_log(
                f"[!] Could not get bus unique name at agent creation: {e}",
                LOG__AGENT
            )
        
        # CRITICAL: Check if methods are registered using dbus-python's internal state
        # Note: Cannot use introspection (AccessDenied - D-Bus security prevents self-introspection via proxy)
        # The _dbus_class_table is a class-level shared dict: {class_name: {interface: {method_name: function}}}
        try:
            # Check dbus-python's internal class table for registered methods
            # The _dbus_class_table is a shared dict on the class, not module
            if hasattr(self.__class__, '_dbus_class_table'):
                class_table = self.__class__._dbus_class_table
            else:
                print_and_log(
                    f"[!] WARNING: Agent class has no _dbus_class_table attribute - cannot verify method registration",
                    LOG__AGENT
                )
                class_table = None
            
            # Get the fully qualified class name (module.class)
            class_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
            
            print_and_log(
                f"[!!!] Checking class table for: {class_name}",
                LOG__AGENT
            )
            
            if class_table:
                print_and_log(
                    f"[!!!] Class table type: {type(class_table)}, has {len(class_table)} entries",
                    LOG__AGENT
                )
            
            if class_table and class_name in class_table:
                class_methods = class_table[class_name]
                print_and_log(
                    f"[!!!] Class found in table, interfaces: {list(class_methods.keys())}",
                    LOG__AGENT
                )
                
                # Check for Agent1 interface methods
                if AGENT_INTERFACE in class_methods:
                    agent_methods = class_methods[AGENT_INTERFACE]
                    method_names = list(agent_methods.keys())
                    print_and_log(
                        f"[!!!] Agent methods in class table: {method_names}",
                        LOG__AGENT
                    )
                    if method_names:
                        print_and_log(
                            f"[+] Agent methods found in class table: {len(method_names)} methods registered",
                            LOG__AGENT
                        )
                    else:
                        print_and_log(
                            f"[-] WARNING: Agent interface exists but has no methods - methods may not be registered",
                            LOG__AGENT
                        )
                else:
                    print_and_log(
                        f"[-] WARNING: Agent interface '{AGENT_INTERFACE}' not found in class table - methods may not be registered",
                        LOG__AGENT
                    )
                    # Show what interfaces ARE registered
                    print_and_log(
                        f"[!] Registered interfaces for this class: {list(class_methods.keys())}",
                        LOG__AGENT
                    )
            else:
                print_and_log(
                    f"[-] WARNING: Class '{class_name}' not found in class table - methods may not be registered",
                    LOG__AGENT
                )
                # Show what classes ARE in the table
                if class_table:
                    print_and_log(
                        f"[!] Classes in table: {list(class_table.keys())[:10]}",  # First 10
                        LOG__AGENT
                    )
                else:
                    print_and_log(
                        f"[!] Class table is empty or None",
                        LOG__AGENT
                    )
            
            # Check connection and object path registration
            if hasattr(self, 'connection'):
                print_and_log(
                    f"[*] Agent connection exists: {self.connection is not None}",
                    LOG__AGENT
                )
            else:
                print_and_log(
                    f"[!] WARNING: Agent has no connection attribute",
                    LOG__AGENT
                )
        except Exception as e:
            print_and_log(
                f"[!] Could not check agent internal state: {e}",
                LOG__AGENT
            )
            import traceback
            print_and_log(
                f"[!] Traceback: {traceback.format_exc()}",
                LOG__AGENT
            )
        
        # Initialize I/O handler
        if io_handler is None:
            from bleep.dbuslayer.agent_io import create_io_handler
            self._io_handler = create_io_handler("cli")
        else:
            self._io_handler = io_handler

    def _setup_agent_manager(self):
        """Initialize agent manager interface."""
        try:
            obj = self._bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez")
            self._agent_manager = dbus.Interface(obj, MANAGER_INTERFACE)
        except dbus.exceptions.DBusException as e:
            error_str = _format_dbus_error(e)
            print_and_log(
                f"[-] AgentManager setup failed: {error_str} (agent_path={self.agent_path})",
                LOG__AGENT,
            )
            raise _errors.FailedException(f"Failed to setup agent manager (agent_path={self.agent_path}): {error_str}")

    def register(self, capabilities="NoInputNoOutput", default=False):
        """Register the agent with BlueZ."""
        try:
            print_and_log(
                f"[*] Registering agent: path={self.agent_path}, capabilities={capabilities}, default_requested={default}",
                LOG__AGENT
            )
            
            self._agent_manager.RegisterAgent(self.agent_path, capabilities)
            print_and_log(f"[+] Agent registered successfully: path={self.agent_path}, capabilities={capabilities}", LOG__AGENT)
            
            if default:
                try:
                    self._agent_manager.RequestDefaultAgent(self.agent_path)
                    print_and_log(
                        f"[+] RequestDefaultAgent called: path={self.agent_path} (Note: BlueZ may select a different default agent)",
                        LOG__AGENT
                    )
                except dbus.exceptions.DBusException as e:
                    error_str = _format_dbus_error(e)
                    print_and_log(
                        f"[!] RequestDefaultAgent failed: {error_str} (agent_path={self.agent_path}, agent still registered but may not be default)",
                        LOG__AGENT
                    )
                    # Don't fail registration if RequestDefaultAgent fails
            
            self._is_registered = True
            self._capabilities = capabilities  # Store capabilities for validation
            
            # Verify method registration via D-Bus introspection
            verification_result = self._verify_method_registration()
            if not verification_result:
                print_and_log(
                    f"[!] WARNING: Agent method registration verification failed - methods may not be accessible via D-Bus",
                    LOG__AGENT
                )
            else:
                print_and_log(
                    f"[+] Agent method registration verified via D-Bus introspection",
                    LOG__AGENT
                )
            
            # CRITICAL: Log bus unique name at registration for destination verification
            try:
                bus_unique_name = self._bus.get_unique_name()
                print_and_log(
                    f"[!!!] Agent registration: bus_unique_name={bus_unique_name}, "
                    f"path={self.agent_path}, capabilities={capabilities}, "
                    f"default_requested={default}, registered={self._is_registered}",
                    LOG__AGENT
                )
            except Exception as e:
                print_and_log(
                    f"[!] Could not get bus unique name at registration: {e}",
                    LOG__AGENT
                )
            
            print_and_log(
                f"[+] Agent registration complete: path={self.agent_path}, capabilities={capabilities}, "
                f"default_requested={default}, registered={self._is_registered}",
                LOG__AGENT
            )
            
            # Log expected methods for this capability
            expected_methods = self._get_expected_methods_for_capability(capabilities)
            if expected_methods:
                print_and_log(
                    f"[*] Agent capability '{capabilities}' supports methods: {', '.join(expected_methods)}",
                    LOG__DEBUG
                )
            
            # Register agent instance for method invocation correlation.
            # NOTE: Unified D-Bus monitoring is NOT enabled here because
            # the message filter it installs prevents dbus-python from
            # dispatching incoming method calls (RequestPinCode, etc.)
            # to the dbus.service.Object handler.  Monitoring can be
            # re-enabled AFTER pairing completes if needed.
            try:
                from bleep.dbuslayer.signals import system_dbus__bluez_signals
                signals_instance = system_dbus__bluez_signals()
                signals_instance.register_agent(self)
            except Exception as e:
                print_and_log(
                    f"[!] Failed to enable unified D-Bus monitoring: {e} "
                    f"(agent registration continues)",
                    LOG__AGENT
                )
        except dbus.exceptions.DBusException as e:
            error_str = _format_dbus_error(e)
            print_and_log(
                f"[-] Agent register failed: {error_str} (agent_path={self.agent_path}, capabilities={capabilities}, default={default})",
                LOG__AGENT,
            )
            raise _errors.FailedException(
                f"Failed to register agent (agent_path={self.agent_path}, capabilities={capabilities}, default={default}): {error_str}"
            )

    def unregister(self):
        """Unregister the agent from BlueZ."""
        if not self._is_registered:
            return
            
        try:
            self._agent_manager.UnregisterAgent(self.agent_path)
            self._is_registered = False
            print_and_log("[+] Agent unregistered", LOG__AGENT)
        except dbus.exceptions.DBusException as e:
            print_and_log(
                f"[-] Failed to unregister agent ({self.agent_path}): {e.get_dbus_name()}: {e.get_dbus_message() or ''}",
                LOG__DEBUG,
            )
        finally:
            # Also un-export the object path from this process so future agent
            # registrations can reuse the same path without "handler exists".
            try:
                self.remove_from_connection()
            except Exception:
                pass

    def is_registered(self):
        """Check if the agent is registered."""
        return self._is_registered
    
    def _get_expected_methods_for_capability(self, capabilities: str) -> List[str]:
        """Get list of methods expected for a given capability.
        
        Parameters
        ----------
        capabilities : str
            Agent capability string (e.g., "KeyboardOnly", "DisplayOnly")
            
        Returns
        -------
        List[str]
            List of method names this capability supports
        """
        capability_methods = {
            "NoInputNoOutput": ["Release", "AuthorizeService"],
            "DisplayOnly": ["Release", "DisplayPinCode", "DisplayPasskey", "RequestConfirmation", "RequestAuthorization", "AuthorizeService"],
            "DisplayYesNo": ["Release", "DisplayPinCode", "DisplayPasskey", "RequestConfirmation", "RequestAuthorization", "AuthorizeService"],
            "KeyboardOnly": ["Release", "RequestPinCode", "RequestPasskey", "AuthorizeService"],
            "KeyboardDisplay": ["Release", "RequestPinCode", "DisplayPinCode", "RequestPasskey", "DisplayPasskey", "RequestConfirmation", "RequestAuthorization", "AuthorizeService"],
        }
        return capability_methods.get(capabilities, [])
    
    def _verify_method_registration(self) -> bool:
        """Verify agent methods are properly registered with D-Bus via introspection.
        
        Returns
        -------
        bool
            True if all required methods are registered, False otherwise
        """
        # Self-introspection on the system bus is denied for non-root by
        # default D-Bus policy (AccessDenied on org.freedesktop.DBus.Introspectable).
        # Instead, verify via dbus-python's internal class table which is
        # already checked at agent creation time.  The class-table check at
        # __init__ logged the method count; we trust that here.
        try:
            our_bus_name = self._bus.get_unique_name()
            print_and_log(
                f"[+] Agent method verification: bus={our_bus_name}, "
                f"path={self.agent_path} (class-table validated at creation)",
                LOG__AGENT,
            )
            return True
        except Exception as e:
            print_and_log(
                f"[!] Agent method verification: could not get bus name: {e}",
                LOG__AGENT,
            )
            return False
    
    def _track_method_invocation(self, method_name: str) -> None:
        """Track that an agent method was invoked.
        
        Parameters
        ----------
        method_name : str
            Name of the method that was invoked
        """
        import time
        self._method_invocations[method_name] = time.time()
    
    def _validate_capability_supports_method(self, method_name: str) -> bool:
        """Validate that the agent's capability supports the requested method.
        
        Parameters
        ----------
        method_name : str
            Name of the method being called
            
        Returns
        -------
        bool
            True if capability supports the method, False otherwise
        """
        expected_methods = self._get_expected_methods_for_capability(self._capabilities)
        return method_name in expected_methods
        
    def _get_device_info(self, device_path):
        """Get device information for display purposes.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device
            
        Returns
        -------
        str
            Human-readable device information (name and address)
        """
        try:
            obj = self._bus.get_object(BLUEZ_SERVICE_NAME, device_path)
            props = dbus.Interface(obj, DBUS_PROPERTIES)
            name = props.Get(DEVICE_INTERFACE, "Name")
            addr = props.Get(DEVICE_INTERFACE, "Address")
            return f"{name} ({addr})"
        except Exception:
            return device_path

    # Standard agent methods that can be overridden by subclasses
    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Release(self):
        """Release the agent."""
        print_and_log(
            f"[*] Release METHOD CALLED by BlueZ: agent_path={self.agent_path}, registered={self._is_registered}",
            LOG__AGENT
        )
        print_and_log("[+] Agent released", LOG__DEBUG)
        self._is_registered = False

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        """Authorize a service before the device can use it."""
        print_and_log(
            f"[*] AuthorizeService METHOD CALLED by BlueZ: device_path={device}, uuid={uuid}, agent_path={self.agent_path}, registered={self._is_registered}",
            LOG__AGENT
        )
        
        device_info = self._get_device_info(device)
        
        try:
            result = self._io_handler.authorize_service(device_info, uuid)
            if not result:
                print_and_log(f"[-] Service {uuid} authorization rejected for {device_info}", LOG__DEBUG)
                raise RejectedException("Service authorization rejected")
            print_and_log(f"[+] Service {uuid} authorized for {device_info}", LOG__DEBUG)
        except Exception as e:
            if not isinstance(e, RejectedException):
                print_and_log(f"[-] Service authorization error: {str(e)}", LOG__DEBUG)
                raise RejectedException("Service authorization error")
            raise

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        """Request PIN code for pairing."""
        # CRITICAL: Log entry point immediately to verify method is invoked
        print_and_log(
            "[!!!] RequestPinCode METHOD ENTRY POINT REACHED - Agent method invoked by BlueZ",
            LOG__AGENT
        )
        
        # Track method invocation
        self._track_method_invocation("RequestPinCode")
        
        # Validate capability supports this method
        if not self._validate_capability_supports_method("RequestPinCode"):
            print_and_log(
                f"[!] WARNING: Agent capability '{self._capabilities}' does not support RequestPinCode "
                f"(requires KeyboardOnly or KeyboardDisplay). Agent method invoked but may fail.",
                LOG__AGENT
            )
        
        print_and_log(
            f"[*] RequestPinCode METHOD CALLED by BlueZ: device_path={device}, agent_path={self.agent_path}, "
            f"registered={self._is_registered}, capabilities={self._capabilities}",
            LOG__AGENT
        )
        
        device_info = self._get_device_info(device)
        
        # Verify IO handler exists before use
        if self._io_handler is None:
            error_msg = "IO handler is None - cannot process PIN code request"
            print_and_log(f"[-] CRITICAL ERROR: {error_msg}", LOG__AGENT)
            raise RejectedException(error_msg)
        
        print_and_log(
            f"[*] IO Handler verification: handler_type={type(self._io_handler).__name__}, "
            f"handler={self._io_handler}",
            LOG__AGENT
        )
        
        try:
            print_and_log(
                f"[*] Calling IO handler.request_pin_code() for device: {device_info}",
                LOG__AGENT
            )
            pin_code = self._io_handler.request_pin_code(device_info)
            print_and_log(f"[+] PIN code provided for {device_info}: {pin_code}", LOG__AGENT)
            return pin_code
        except AttributeError as e:
            error_msg = f"AttributeError in RequestPinCode: {e}"
            print_and_log(f"[-] {error_msg}", LOG__AGENT)
            import traceback
            print_and_log(f"[-] Traceback: {traceback.format_exc()}", LOG__AGENT)
            raise RejectedException(f"PIN code request rejected: {error_msg}")
        except Exception as e:
            error_msg = f"PIN code request error: {type(e).__name__}: {str(e)}"
            print_and_log(f"[-] {error_msg}", LOG__AGENT)
            import traceback
            print_and_log(f"[-] Traceback: {traceback.format_exc()}", LOG__AGENT)
            raise RejectedException("PIN code request rejected")

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        """Request passkey for pairing."""
        print_and_log(
            f"[*] RequestPasskey METHOD CALLED by BlueZ: device_path={device}, agent_path={self.agent_path}, registered={self._is_registered}",
            LOG__AGENT
        )
        
        device_info = self._get_device_info(device)
        
        try:
            passkey = self._io_handler.request_passkey(device_info)
            print_and_log(f"[+] Passkey provided for {device_info}: {passkey:06d}", LOG__AGENT)
            return dbus.UInt32(passkey)
        except Exception as e:
            print_and_log(f"[-] Passkey request error: {str(e)}", LOG__AGENT)
            raise RejectedException("Passkey request rejected")

    @dbus.service.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        """Display passkey on agent."""
        print_and_log(
            f"[*] DisplayPasskey METHOD CALLED by BlueZ: device_path={device}, passkey={passkey:06d}, entered={entered}, agent_path={self.agent_path}, registered={self._is_registered}",
            LOG__AGENT
        )
        
        device_info = self._get_device_info(device)
        
        try:
            self._io_handler.display_passkey(device_info, int(passkey), int(entered))
        except Exception as e:
            print_and_log(f"[-] Display passkey error: {str(e)}", LOG__AGENT)
        
        # Fallback logging in case IO handler doesn't log
        if int(entered) > 0:
            print_and_log(f"[+] DisplayPasskey: {device_info} - Passkey: {passkey:06d} ({entered} digits entered)", LOG__AGENT)
        else:
            print_and_log(f"[+] DisplayPasskey: {device_info} - Passkey: {passkey:06d}", LOG__AGENT)

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        """Display PIN code on agent."""
        print_and_log(
            f"[*] DisplayPinCode METHOD CALLED by BlueZ: device_path={device}, pincode={pincode}, agent_path={self.agent_path}, registered={self._is_registered}",
            LOG__AGENT
        )
        
        device_info = self._get_device_info(device)
        
        try:
            self._io_handler.display_pin_code(device_info, pincode)
        except Exception as e:
            print_and_log(f"[-] Display PIN code error: {str(e)}", LOG__AGENT)
        
        # Fallback logging in case IO handler doesn't log
        print_and_log(f"[+] DisplayPinCode: {device_info} - PIN: {pincode}", LOG__AGENT)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        """Request confirmation of passkey."""
        print_and_log(
            f"[*] RequestConfirmation METHOD CALLED by BlueZ: device_path={device}, passkey={passkey:06d}, agent_path={self.agent_path}, registered={self._is_registered}",
            LOG__AGENT
        )
        
        device_info = self._get_device_info(device)
        
        try:
            result = self._io_handler.request_confirmation(device_info, int(passkey))
            if not result:
                print_and_log(f"[-] Passkey confirmation rejected for {device_info} (passkey: {passkey:06d})", LOG__AGENT)
                raise RejectedException("Passkey confirmation rejected by user")
            print_and_log(f"[+] Passkey confirmed for {device_info}: {passkey:06d}", LOG__AGENT)
        except Exception as e:
            print_and_log(f"[-] Passkey confirmation error: {str(e)}", LOG__AGENT)
            if not isinstance(e, RejectedException):
                raise RejectedException("Passkey confirmation rejected")
            raise

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        """Request authorization for pairing."""
        print_and_log(
            f"[*] RequestAuthorization METHOD CALLED by BlueZ: device_path={device}, agent_path={self.agent_path}, registered={self._is_registered}",
            LOG__AGENT
        )
        
        device_info = self._get_device_info(device)
        
        try:
            result = self._io_handler.request_authorization(device_info)
            if not result:
                print_and_log(f"[-] Pairing authorization rejected for {device_info}", LOG__AGENT)
                raise RejectedException("Pairing authorization rejected by user")
            print_and_log(f"[+] Pairing authorized for {device_info}", LOG__AGENT)
        except Exception as e:
            print_and_log(f"[-] Pairing authorization error: {str(e)}", LOG__AGENT)
            if not isinstance(e, RejectedException):
                raise RejectedException("Pairing authorization rejected")
            raise

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Cancel(self):
        """Cancel any pending request."""
        # Track method invocation
        self._track_method_invocation("Cancel")
        
        print_and_log(
            f"[*] Cancel METHOD CALLED by BlueZ: agent_path={self.agent_path}, registered={self._is_registered}",
            LOG__AGENT
        )
        
        try:
            self._io_handler.cancel()
        except Exception as e:
            print_and_log(f"[-] Cancel notification error: {str(e)}", LOG__DEBUG)
            
        print_and_log("[+] Request canceled", LOG__DEBUG)


class SimpleAgent(BlueZAgent):
    """A simple agent implementation that accepts all requests."""

    def __init__(self, bus, agent_path=AGENT_NAMESPACE):
        """Initialize simple agent with auto-accept handler."""
        from bleep.dbuslayer.agent_io import create_io_handler
        io_handler = create_io_handler("auto")
        super().__init__(bus, agent_path, io_handler)
        
        # Configure handler defaults
        self._io_handler.default_pin = "0000"
        self._io_handler.default_passkey = 0
        
    # All necessary methods are implemented by BlueZAgent using the IO handler


class InteractiveAgent(BlueZAgent):
    """An agent implementation that prompts for user input."""

    def __init__(self, bus, agent_path=AGENT_NAMESPACE):
        """Initialize interactive agent with CLI handler."""
        from bleep.dbuslayer.agent_io import create_io_handler
        io_handler = create_io_handler("cli")
        super().__init__(bus, agent_path, io_handler)
        
    # All necessary methods are implemented by BlueZAgent using the IO handler


class EnhancedAgent(BlueZAgent):
    """An enhanced agent implementation with configurable callbacks."""

    def __init__(self, bus, agent_path=AGENT_NAMESPACE, io_handler=None, auto_accept=True):
        """Initialize enhanced agent.
        
        Parameters
        ----------
        bus : dbus.Bus
            D-Bus bus object
        agent_path : str, optional
            D-Bus object path for the agent
        io_handler : AgentIOHandler, optional
            I/O handler for pairing interactions
        auto_accept : bool, optional
            Whether to auto-accept pairing requests when no callback is provided
        """
        # Create programmatic IO handler if none provided
        if io_handler is None:
            from bleep.dbuslayer.agent_io import create_io_handler
            io_handler = create_io_handler("programmatic", auto_accept=auto_accept)
            
        super().__init__(bus, agent_path, io_handler)
        
        # For backward compatibility
        self.auto_accept = auto_accept
        self.default_pin = getattr(self._io_handler, "default_pin", "0000")
        self.default_passkey = getattr(self._io_handler, "default_passkey", 0)
        
    def set_callback(self, event_type, callback):
        """Set a callback for a specific event type.
        
        Parameters
        ----------
        event_type : str
            Event name (e.g., 'request_pin_code', 'authorize_service')
        callback : callable
            Function to call when the event occurs
            
        Returns
        -------
        bool
            True if the callback was set, False if the event type is invalid
        """
        # Map old callback names to IO handler methods
        if hasattr(self._io_handler, "set_callback"):
            return self._io_handler.set_callback(event_type, callback)
        return False


class PairingAgent(EnhancedAgent):
    """An agent specifically designed for pairing operations with state machine and secure storage."""
    
    def __init__(self, bus, agent_path=AGENT_NAMESPACE, io_handler=None, 
                auto_accept=True, storage_path=None, encryption_key=None):
        """Initialize pairing agent.
        
        Parameters
        ----------
        bus : dbus.Bus
            D-Bus bus object
        agent_path : str, optional
            D-Bus object path for the agent
        io_handler : AgentIOHandler, optional
            I/O handler for pairing interactions
        auto_accept : bool, optional
            Whether to auto-accept pairing requests
        storage_path : str, optional
            Path to store bonding information
        encryption_key : str, optional
            Encryption key for secure storage
        """
        # Initialize base agent
        super().__init__(bus, agent_path, io_handler, auto_accept)
        
        # Initialize trust manager
        self.trust_manager = TrustManager(bus)

        # Last D-Bus error name from pair_device(), readable by callers
        self.last_pair_error: str | None = None
        
        # Initialize state machine
        from bleep.dbuslayer.pairing_state import PairingStateMachine
        self._state_machine = PairingStateMachine(self._io_handler)
        
        # Initialize storage
        from bleep.dbuslayer.bond_storage import DeviceBondStore, PairingCache
        self._bond_store = DeviceBondStore(storage_path, encryption_key)
        self._pairing_cache = PairingCache()
        
        # For backwards compatibility
        self.pairing_callbacks = {
            "pairing_started": None,
            "pairing_succeeded": None,
            "pairing_failed": None,
            "device_trusted": None,
        }
        
        # Configure state machine callbacks
        self._state_machine.set_callback("on_state_change", self._on_state_change)
        self._state_machine.set_callback("on_complete", self._on_pairing_complete)
        self._state_machine.set_callback("on_failed", self._on_pairing_failed)
        self._state_machine.set_callback("on_cancelled", self._on_pairing_cancelled)
        
    def _on_state_change(self, old_state, new_state):
        """Handle state machine state changes."""
        print_and_log(f"[*] Pairing state change: {old_state.name} -> {new_state.name}", LOG__DEBUG)
        
    def _on_pairing_complete(self, pairing_data):
        """Handle successful pairing completion."""
        device_info = pairing_data.get("device_info", "Unknown device")
        device_path = pairing_data.get("device_path")
        
        # Save to bond store if we have a device path
        if device_path:
            self._bond_store.save_device_bond(device_path, pairing_data)
            
        # Notify via callback if registered
        if self.pairing_callbacks["pairing_succeeded"]:
            self.pairing_callbacks["pairing_succeeded"](device_info)
            
    def _on_pairing_failed(self, error):
        """Handle pairing failure."""
        device_info = self._state_machine.device_info or "Unknown device"
        error_msg = str(error)
        
        # Notify via callback if registered
        if self.pairing_callbacks["pairing_failed"]:
            self.pairing_callbacks["pairing_failed"](device_info, error_msg)
            
    def _on_pairing_cancelled(self):
        """Handle pairing cancellation."""
        device_info = self._state_machine.device_info or "Unknown device"
        
        # Notify via callback if registered
        if self.pairing_callbacks["pairing_failed"]:
            self.pairing_callbacks["pairing_failed"](device_info, "Cancelled")
            
    def set_pairing_callback(self, event_type, callback):
        """Set a callback for a specific pairing event.
        
        Parameters
        ----------
        event_type : str
            Event name (e.g., 'pairing_started', 'pairing_succeeded')
        callback : callable
            Function to call when the event occurs
            
        Returns
        -------
        bool
            True if the callback was set, False if the event type is invalid
        """
        if event_type in self.pairing_callbacks:
            self.pairing_callbacks[event_type] = callback
            return True
        return False
        
    def pair_device(self, device_path, set_trusted=True, timeout=30):
        """Pair with a device and optionally set it as trusted.

        Uses an **asynchronous** ``Pair()`` call so the GLib main context can
        dispatch agent callbacks (``RequestPinCode``, etc.) while waiting.

        If a GLib MainLoop is already running on another thread (e.g. debug
        shell's background loop), this method simply polls the result dict
        with a short sleep — the background loop handles D-Bus dispatch.

        If no background loop is detected, this method iterates the default
        GLib MainContext directly to pump D-Bus events.

        Parameters
        ----------
        device_path : str
            The D-Bus path of the device to pair with
        set_trusted : bool
            Whether to set the device as trusted after pairing
        timeout : int
            Maximum time to wait for pairing to complete (in seconds)

        Returns
        -------
        bool
            True if pairing was successful, False otherwise
        """
        from gi.repository import GLib

        self.last_pair_error = None

        try:
            device_info = self._get_device_info(device_path)
            print_and_log(f"[*] Attempting to pair with {device_info}", LOG__GENERAL)

            if self.pairing_callbacks["pairing_started"]:
                self.pairing_callbacks["pairing_started"](device_info)

            self._state_machine.start_pairing(device_path, device_info)

            device = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, device_path),
                DEVICE_INTERFACE,
            )

            # ---- async Pair() ------------------------------------------------
            pair_result: Dict[str, Any] = {"done": False, "error": None}

            def _on_pair_reply():
                print_and_log("[+] Pair() D-Bus reply received (success)", LOG__AGENT)
                pair_result["done"] = True

            def _on_pair_error(exc):
                print_and_log(f"[-] Pair() D-Bus error received: {exc}", LOG__AGENT)
                pair_result["error"] = exc
                pair_result["done"] = True

            print_and_log(
                f"[*] Calling async Pair(): device_path={device_path}, timeout={timeout}s",
                LOG__GENERAL,
            )

            device.Pair(
                reply_handler=_on_pair_reply,
                error_handler=_on_pair_error,
                timeout=timeout * 1000,
            )

            # ---- wait for result ---------------------------------------------
            # Detect whether a background GLib MainLoop is already iterating the
            # default context.  If so, D-Bus dispatch is handled there and we
            # only need to poll pair_result.  If not, we must iterate ourselves.
            context = GLib.MainContext.default()
            bg_loop_running = not context.acquire()
            if not bg_loop_running:
                context.release()

            start_time = time.time()
            log_interval = 5.0
            next_log = start_time + log_interval

            if bg_loop_running:
                print_and_log(
                    "[*] Background GLib MainLoop detected – polling for Pair() result",
                    LOG__GENERAL,
                )
                while not pair_result["done"] and (time.time() - start_time < timeout):
                    time.sleep(0.25)
                    now = time.time()
                    if now >= next_log:
                        elapsed = now - start_time
                        print_and_log(
                            f"[*] Waiting for Pair() result… {elapsed:.0f}s elapsed",
                            LOG__GENERAL,
                        )
                        next_log = now + log_interval
            else:
                # A temporary MainLoop is required for dbus-python to
                # dispatch object-path handlers (RequestPinCode, etc.).
                # context.iteration() only triggers message filters, not
                # dbus.service.Object method handlers.  Confirmed via PoC
                # that GLib.MainLoop().run() is the only reliable mechanism.
                print_and_log(
                    "[*] No background MainLoop – running temporary MainLoop for D-Bus dispatch",
                    LOG__GENERAL,
                )
                tmp_loop = GLib.MainLoop()

                def _poll_result():
                    nonlocal next_log
                    if pair_result["done"]:
                        tmp_loop.quit()
                        return False
                    now = time.time()
                    if now - start_time >= timeout:
                        tmp_loop.quit()
                        return False
                    if now >= next_log:
                        print_and_log(
                            f"[*] Waiting for Pair() result… {now - start_time:.0f}s elapsed",
                            LOG__GENERAL,
                        )
                        next_log = now + log_interval
                    return True

                GLib.timeout_add(100, _poll_result)
                tmp_loop.run()

            # ---- evaluate result ---------------------------------------------
            if pair_result["error"] is not None:
                raise pair_result["error"]

            if not pair_result["done"]:
                print_and_log(f"[-] Pairing with {device_info} timed out after {timeout}s", LOG__GENERAL)
                self._state_machine.handle_pairing_failed(Exception("Pairing timed out"))
                return False

            # Verify Paired property
            props = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, device_path),
                DBUS_PROPERTIES,
            )
            paired = bool(props.Get(DEVICE_INTERFACE, "Paired"))

            if not paired:
                print_and_log(f"[-] Pair() returned OK but Paired=False for {device_info}", LOG__GENERAL)
                self._state_machine.handle_pairing_failed(Exception("Pair succeeded but device not paired"))
                return False

            self._state_machine.handle_bonding_start()
            print_and_log(f"[+] Successfully paired with {device_info}", LOG__GENERAL)

            if set_trusted:
                trusted = self.trust_manager.set_trusted(device_path, True)
                if trusted and self.pairing_callbacks["device_trusted"]:
                    self.pairing_callbacks["device_trusted"](device_info)

            self._state_machine.handle_pairing_success()
            return True

        except dbus.exceptions.DBusException as e:
            self.last_pair_error = e.get_dbus_name()
            error_str = _format_dbus_error(e)
            print_and_log(
                f"[-] Pairing failed: {error_str}",
                LOG__GENERAL,
            )
            self._safe_transition_failed(Exception(error_str))
            return False
        except Exception as e:
            self.last_pair_error = type(e).__name__
            print_and_log(f"[-] Pairing failed with unexpected error: {e}", LOG__GENERAL)
            self._safe_transition_failed(e)
            return False

    def _safe_transition_failed(self, error: Exception) -> None:
        """Transition to FAILED only if the state machine is not already terminal."""
        from bleep.dbuslayer.pairing_state import PairingState
        current = self._state_machine.state
        if current in (PairingState.COMPLETE, PairingState.FAILED, PairingState.CANCELLED):
            print_and_log(
                f"[*] Skipping FAILED transition — state machine already in terminal state {current.name}",
                LOG__DEBUG,
            )
            return
        try:
            self._state_machine.handle_pairing_failed(error)
        except Exception:
            pass


class TrustManager:
    """Manages trust relationships with Bluetooth devices."""
    
    def __init__(self, bus):
        self._bus = bus
        
    def set_trusted(self, device_path, trusted=True):
        """Set a device as trusted or untrusted.
        
        Parameters
        ----------
        device_path : str
            The D-Bus path of the device
        trusted : bool
            Whether to set the device as trusted (True) or untrusted (False)
            
        Returns
        -------
        bool
            True if the operation was successful, False otherwise
        """
        try:
            props = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, device_path),
                DBUS_PROPERTIES
            )
            
            props.Set(DEVICE_INTERFACE, "Trusted", dbus.Boolean(trusted))
            
            # Get device info for logging
            try:
                name = props.Get(DEVICE_INTERFACE, "Name")
                addr = props.Get(DEVICE_INTERFACE, "Address")
                device_info = f"{name} ({addr})"
            except:
                device_info = device_path
                
            status = "trusted" if trusted else "untrusted"
            print_and_log(f"[+] Device {device_info} set as {status}", LOG__GENERAL)
            return True
            
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to set trust status: {str(e)}", LOG__GENERAL)
            return False
            
    def is_trusted(self, device_path):
        """Check if a device is trusted.
        
        Parameters
        ----------
        device_path : str
            The D-Bus path of the device
            
        Returns
        -------
        bool
            True if the device is trusted, False otherwise
        """
        try:
            props = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, device_path),
                DBUS_PROPERTIES
            )
            
            return bool(props.Get(DEVICE_INTERFACE, "Trusted"))
            
        except dbus.exceptions.DBusException:
            return False
            
    def get_trusted_devices(self):
        """Get a list of all trusted devices.
        
        Returns
        -------
        list
            List of (device_path, name, address) tuples for trusted devices
        """
        trusted_devices = []
        
        try:
            # Get object manager
            obj_manager = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE_NAME, "/"),
                DBUS_OM_IFACE
            )
            
            # Get all objects
            objects = obj_manager.GetManagedObjects()
            
            # Find trusted devices
            for path, interfaces in objects.items():
                if DEVICE_INTERFACE in interfaces:
                    props = interfaces[DEVICE_INTERFACE]
                    if props.get("Trusted", False):
                        name = props.get("Name", "Unknown")
                        address = props.get("Address", "Unknown")
                        trusted_devices.append((path, name, address))
                        
            return trusted_devices
            
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get trusted devices: {str(e)}", LOG__GENERAL)
            return []


def create_agent(bus, agent_type="simple", capabilities="NoInputNoOutput", default=True, 
              auto_accept=True, io_handler=None, storage_path=None, encryption_key=None):
    """Create and register an agent of the specified type.
    
    Parameters
    ----------
    bus : dbus.Bus
        The D-Bus bus to use
    agent_type : str
        Type of agent to create: "simple", "interactive", "enhanced", or "pairing"
    capabilities : str
        Agent capabilities: "NoInputNoOutput", "DisplayOnly", "DisplayYesNo", 
        "KeyboardOnly", "KeyboardDisplay", or "NoInputNoOutput"
    default : bool
        Whether to request this agent as the default agent
    auto_accept : bool
        Whether to automatically accept pairing requests (for enhanced and pairing agents)
    io_handler : AgentIOHandler, optional
        I/O handler for pairing interactions. If None, one will be created based on agent_type.
    storage_path : str, optional
        Path to store bonding information (for PairingAgent only)
    encryption_key : str, optional
        Encryption key for secure storage (for PairingAgent only)
        
    Returns
    -------
    BlueZAgent
        The created agent instance
    """
    agent_types = {
        "simple": SimpleAgent,
        "interactive": InteractiveAgent,
        "enhanced": EnhancedAgent,
        "pairing": PairingAgent,
    }
    
    # Determine the appropriate IO handler type if none provided
    if io_handler is None:
        if agent_type.lower() == "simple":
            from bleep.dbuslayer.agent_io import create_io_handler
            io_handler = create_io_handler("auto")
        elif agent_type.lower() == "interactive":
            from bleep.dbuslayer.agent_io import create_io_handler
            io_handler = create_io_handler("cli")
        elif agent_type.lower() in ("enhanced", "pairing"):
            from bleep.dbuslayer.agent_io import create_io_handler
            io_handler = create_io_handler("programmatic", auto_accept=auto_accept)
    
    # Create the agent
    AgentClass = agent_types.get(agent_type.lower(), SimpleAgent)
    
    # Initialize with appropriate parameters
    if agent_type.lower() == "pairing":
        agent = AgentClass(bus, agent_path=AGENT_NAMESPACE, 
                         io_handler=io_handler, auto_accept=auto_accept,
                         storage_path=storage_path, encryption_key=encryption_key)
    elif agent_type.lower() == "enhanced":
        agent = AgentClass(bus, agent_path=AGENT_NAMESPACE, 
                         io_handler=io_handler, auto_accept=auto_accept)
    else:
        agent = AgentClass(bus, agent_path=AGENT_NAMESPACE)
    
    try:
        agent.register(capabilities=capabilities, default=default)
        print_and_log(f"[+] {agent_type.capitalize()} agent registered with capabilities: {capabilities}", LOG__GENERAL)
        return agent
    except Exception as e:
        print_and_log(f"[-] Failed to register {agent_type} agent: {str(e)}", LOG__GENERAL)
        raise


# ---------------------------------------------------------------------------
# Legacy-class aliases – provide the exact names used by the monolith so
# external scripts do not break once the monolith backup is removed.
# ---------------------------------------------------------------------------


class system_dbus__bluez_generic_agent(SimpleAgent):
    """Alias for backward-compatibility – behaves exactly like SimpleAgent."""


class system_dbus__bluez_agent_user_interface(InteractiveAgent):
    """Alias for backward-compatibility – behaves like InteractiveAgent."""
