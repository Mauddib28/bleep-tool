"""
Agent D-Bus Interface
Provides the system_dbus__bluez_generic_agent and system_dbus__bluez_agent_user_interface classes from the original codebase.
"""

# Ensure type annotations that reference classes defined later do not fail at
# import-time.  (Python 3.11 does *not* enable PEP 563 by default.)
from __future__ import annotations

import time
import threading
from typing import Optional, Dict, Any, Callable

import dbus
import dbus.service

from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
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

    if os.getenv("BLEEP_NO_AUTO_PAIR", "0") not in {"0", "false", "False", ""}:
        return

    global _DEFAULT_AGENT
    if _DEFAULT_AGENT is not None and _DEFAULT_AGENT.is_registered():
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
    print_and_log("[*] Default pairing agent registered", LOG__DEBUG)


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
            raise _errors.FailedException(f"Failed to setup agent manager: {str(e)}")

    def register(self, capabilities="NoInputNoOutput", default=False):
        """Register the agent with BlueZ."""
        try:
            self._agent_manager.RegisterAgent(self.agent_path, capabilities)
            if default:
                self._agent_manager.RequestDefaultAgent(self.agent_path)
            self._is_registered = True
            print_and_log(f"[+] Agent registered with capabilities: {capabilities}", LOG__DEBUG)
        except dbus.exceptions.DBusException as e:
            raise _errors.FailedException(f"Failed to register agent: {str(e)}")

    def unregister(self):
        """Unregister the agent from BlueZ."""
        if not self._is_registered:
            return
            
        try:
            self._agent_manager.UnregisterAgent(self.agent_path)
            self._is_registered = False
            print_and_log("[+] Agent unregistered", LOG__DEBUG)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to unregister agent: {str(e)}", LOG__DEBUG)

    def is_registered(self):
        """Check if the agent is registered."""
        return self._is_registered
        
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
        print_and_log("[+] Agent released", LOG__DEBUG)
        self._is_registered = False

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        """Authorize a service before the device can use it."""
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
        device_info = self._get_device_info(device)
        
        try:
            pin_code = self._io_handler.request_pin_code(device_info)
            print_and_log(f"[+] PIN code provided for {device_info}", LOG__DEBUG)
            return pin_code
        except Exception as e:
            print_and_log(f"[-] PIN code request error: {str(e)}", LOG__DEBUG)
            raise RejectedException("PIN code request rejected")

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        """Request passkey for pairing."""
        device_info = self._get_device_info(device)
        
        try:
            passkey = self._io_handler.request_passkey(device_info)
            print_and_log(f"[+] Passkey provided for {device_info}", LOG__DEBUG)
            return dbus.UInt32(passkey)
        except Exception as e:
            print_and_log(f"[-] Passkey request error: {str(e)}", LOG__DEBUG)
            raise RejectedException("Passkey request rejected")

    @dbus.service.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        """Display passkey on agent."""
        device_info = self._get_device_info(device)
        
        try:
            self._io_handler.display_passkey(device_info, int(passkey), int(entered))
        except Exception as e:
            print_and_log(f"[-] Display passkey error: {str(e)}", LOG__DEBUG)
        
        # Fallback logging in case IO handler doesn't log
        print_and_log(f"[+] DisplayPasskey: {device_info} - {passkey} ({entered} digits entered)", LOG__DEBUG)

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        """Display PIN code on agent."""
        device_info = self._get_device_info(device)
        
        try:
            self._io_handler.display_pin_code(device_info, pincode)
        except Exception as e:
            print_and_log(f"[-] Display PIN code error: {str(e)}", LOG__DEBUG)
        
        # Fallback logging in case IO handler doesn't log
        print_and_log(f"[+] DisplayPinCode: {device_info} - {pincode}", LOG__DEBUG)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        """Request confirmation of passkey."""
        device_info = self._get_device_info(device)
        
        try:
            result = self._io_handler.request_confirmation(device_info, int(passkey))
            if not result:
                print_and_log(f"[-] Passkey confirmation rejected for {device_info}", LOG__DEBUG)
                raise RejectedException("Passkey confirmation rejected by user")
            print_and_log(f"[+] Passkey confirmed for {device_info}: {passkey}", LOG__DEBUG)
        except Exception as e:
            print_and_log(f"[-] Passkey confirmation error: {str(e)}", LOG__DEBUG)
            if not isinstance(e, RejectedException):
                raise RejectedException("Passkey confirmation rejected")
            raise

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        """Request authorization for pairing."""
        device_info = self._get_device_info(device)
        
        try:
            result = self._io_handler.request_authorization(device_info)
            if not result:
                print_and_log(f"[-] Pairing authorization rejected for {device_info}", LOG__DEBUG)
                raise RejectedException("Pairing authorization rejected by user")
            print_and_log(f"[+] Pairing authorized for {device_info}", LOG__DEBUG)
        except Exception as e:
            print_and_log(f"[-] Pairing authorization error: {str(e)}", LOG__DEBUG)
            if not isinstance(e, RejectedException):
                raise RejectedException("Pairing authorization rejected")
            raise

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Cancel(self):
        """Cancel any pending request."""
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
        try:
            # Get device properties
            device_info = self._get_device_info(device_path)
            print_and_log(f"[*] Attempting to pair with {device_info}", LOG__GENERAL)
            
            # Notify pairing started
            if self.pairing_callbacks["pairing_started"]:
                self.pairing_callbacks["pairing_started"](device_info)
                
            # Initialize state machine
            self._state_machine.start_pairing(device_path, device_info)
            
            # Attempt to use D-Bus timeout handling if available
            try:
                from bleep.dbus.timeout_manager import call_method_with_timeout
                from bleep.core.metrics import MetricsCollector
                
                # Create metrics collector if not already exists
                metrics = MetricsCollector("pairing_agent")
                
                # Get device interface
                device = dbus.Interface(
                    self._bus.get_object(BLUEZ_SERVICE_NAME, device_path),
                    DEVICE_INTERFACE
                )
                
                # Call Pair method with timeout
                metrics.record_operation("pair_begin")
                call_method_with_timeout(device.Pair, timeout=timeout)
                metrics.record_operation("pair_success")
                
            except ImportError:
                # Fall back to standard approach if timeout module not available
                # Get device interface
                device = dbus.Interface(
                    self._bus.get_object(BLUEZ_SERVICE_NAME, device_path),
                    DEVICE_INTERFACE
                )
                
                # Pair with the device
                device.Pair()
            
            # Wait for pairing to complete
            start_time = time.time()
            paired = False
            
            while time.time() - start_time < timeout:
                props = dbus.Interface(
                    self._bus.get_object(BLUEZ_SERVICE_NAME, device_path),
                    DBUS_PROPERTIES
                )
                
                try:
                    paired = props.Get(DEVICE_INTERFACE, "Paired")
                    if paired:
                        self._state_machine.handle_bonding_start()
                        break
                except:
                    pass
                    
                time.sleep(1)
                
            if not paired:
                print_and_log(f"[-] Pairing with {device_info} timed out", LOG__GENERAL)
                error = Exception("Pairing timed out")
                self._state_machine.handle_pairing_failed(error)
                return False
                
            print_and_log(f"[+] Successfully paired with {device_info}", LOG__GENERAL)
            
            # Set trusted if requested
            if set_trusted:
                trusted = self.trust_manager.set_trusted(device_path, True)
                if trusted and self.pairing_callbacks["device_trusted"]:
                    self.pairing_callbacks["device_trusted"](device_info)
            
            # Complete the pairing in the state machine
            self._state_machine.handle_pairing_success()
                
            return True
            
        except dbus.exceptions.DBusException as e:
            error_name = e.get_dbus_name()
            error_msg = e.get_dbus_message()
            print_and_log(f"[-] Pairing failed: {error_name} - {error_msg}", LOG__GENERAL)
            
            try:
                metrics.record_operation("pair_failed")
            except (NameError, AttributeError):
                pass
                
            # Update state machine
            error = Exception(f"{error_name}: {error_msg}")
            self._state_machine.handle_pairing_failed(error)
                
            return False
        except Exception as e:
            print_and_log(f"[-] Pairing failed with unexpected error: {str(e)}", LOG__GENERAL)
            
            # Update state machine
            self._state_machine.handle_pairing_failed(e)
            
            return False


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
