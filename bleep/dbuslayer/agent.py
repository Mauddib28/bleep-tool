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


def ensure_default_pairing_agent(*, capabilities: str = "KeyboardDisplay", auto_accept: bool = True) -> None:
    """Register a global PairingAgent once per process.

    Intended to be called by connection helpers when they detect an
    AuthenticationRequired / NotAuthorized error.  If an agent is already
    registered the call is a cheap no-op.

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
    )
    print_and_log("[*] Default pairing agent registered", LOG__DEBUG)


class BlueZAgent(dbus.service.Object):
    """Base class for implementing a Bluetooth agent."""

    def __init__(self, bus, agent_path=AGENT_NAMESPACE):
        super().__init__(bus, agent_path)
        self._bus = bus
        self.agent_path = agent_path
        self._agent_manager = None
        self._setup_agent_manager()
        self._is_registered = False

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

    # Standard agent methods that can be overridden by subclasses
    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Release(self):
        """Release the agent."""
        print_and_log("[+] Agent released", LOG__DEBUG)
        self._is_registered = False

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        """Authorize a service before the device can use it."""
        raise RejectedException("Service authorization rejected")

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        """Request PIN code for pairing."""
        raise RejectedException("PIN code request rejected")

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        """Request passkey for pairing."""
        raise RejectedException("Passkey request rejected")

    @dbus.service.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        """Display passkey on agent."""
        print_and_log(f"[+] DisplayPasskey: {device} - {passkey} ({entered} digits entered)", LOG__DEBUG)

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        """Display PIN code on agent."""
        print_and_log(f"[+] DisplayPinCode: {device} - {pincode}", LOG__DEBUG)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        """Request confirmation of passkey."""
        raise RejectedException("Passkey confirmation rejected")

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        """Request authorization for pairing."""
        raise RejectedException("Pairing authorization rejected")

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Cancel(self):
        """Cancel any pending request."""
        print_and_log("[+] Request canceled", LOG__DEBUG)


class SimpleAgent(BlueZAgent):
    """A simple agent implementation that accepts all requests."""

    def __init__(self, bus, agent_path=AGENT_NAMESPACE):
        super().__init__(bus, agent_path)

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        """Always authorize service."""
        print_and_log(f"[+] Service {uuid} authorized for {device}", LOG__DEBUG)
        return

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        """Return a default PIN code."""
        print_and_log(f"[+] PIN code request for {device} - returning '0000'", LOG__DEBUG)
        return "0000"

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        """Return a default passkey."""
        print_and_log(f"[+] Passkey request for {device} - returning 0", LOG__DEBUG)
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        """Always confirm passkey."""
        print_and_log(f"[+] Passkey confirmation for {device} - {passkey} - accepting", LOG__DEBUG)
        return

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        """Always authorize pairing."""
        print_and_log(f"[+] Pairing authorization for {device} - accepting", LOG__DEBUG)
        return


class InteractiveAgent(BlueZAgent):
    """An agent implementation that prompts for user input."""

    def __init__(self, bus, agent_path=AGENT_NAMESPACE):
        super().__init__(bus, agent_path)

    def _get_device_info(self, device_path):
        """Get device information for display purposes."""
        try:
            obj = self._bus.get_object(BLUEZ_SERVICE_NAME, device_path)
            props = dbus.Interface(obj, DBUS_PROPERTIES)
            name = props.Get(DEVICE_INTERFACE, "Name")
            addr = props.Get(DEVICE_INTERFACE, "Address")
            return f"{name} ({addr})"
        except:
            return device_path

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        """Prompt for service authorization."""
        device_info = self._get_device_info(device)
        response = input(f"Authorize service {uuid} for {device_info}? (yes/no): ")
        if response.lower() != "yes":
            print_and_log(f"[-] Service {uuid} authorization rejected for {device_info}", LOG__GENERAL)
            raise RejectedException("Service authorization rejected by user")
        print_and_log(f"[+] Service {uuid} authorized for {device_info}", LOG__GENERAL)

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        """Prompt for PIN code."""
        device_info = self._get_device_info(device)
        pin = input(f"Enter PIN code for {device_info}: ")
        print_and_log(f"[+] PIN code entered for {device_info}", LOG__GENERAL)
        return pin

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        """Prompt for passkey."""
        device_info = self._get_device_info(device)
        passkey = input(f"Enter passkey for {device_info}: ")
        try:
            passkey_int = int(passkey)
            print_and_log(f"[+] Passkey entered for {device_info}: {passkey_int}", LOG__GENERAL)
            return dbus.UInt32(passkey_int)
        except ValueError:
            print_and_log(f"[-] Invalid passkey format for {device_info}", LOG__GENERAL)
            raise _errors.InvalidArgumentError("passkey", "Must be a number")

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        """Prompt for passkey confirmation."""
        device_info = self._get_device_info(device)
        response = input(f"Confirm passkey {passkey} for {device_info}? (yes/no): ")
        if response.lower() != "yes":
            print_and_log(f"[-] Passkey confirmation rejected for {device_info}", LOG__GENERAL)
            raise RejectedException("Passkey confirmation rejected by user")
        print_and_log(f"[+] Passkey confirmed for {device_info}", LOG__GENERAL)

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        """Prompt for pairing authorization."""
        device_info = self._get_device_info(device)
        response = input(f"Authorize pairing for {device_info}? (yes/no): ")
        if response.lower() != "yes":
            print_and_log(f"[-] Pairing authorization rejected for {device_info}", LOG__GENERAL)
            raise RejectedException("Pairing authorization rejected by user")
        print_and_log(f"[+] Pairing authorized for {device_info}", LOG__GENERAL)


class EnhancedAgent(BlueZAgent):
    """An enhanced agent implementation with configurable callbacks."""

    def __init__(self, bus, agent_path=AGENT_NAMESPACE):
        super().__init__(bus, agent_path)
        self.callbacks = {
            "authorize_service": None,
            "request_pin_code": None,
            "request_passkey": None,
            "display_passkey": None,
            "display_pin_code": None,
            "request_confirmation": None,
            "request_authorization": None,
            "cancel": None,
        }
        self.default_pin = "0000"
        self.default_passkey = 0
        self.auto_accept = True

    def set_callback(self, event_type, callback):
        """Set a callback for a specific event type."""
        if event_type in self.callbacks:
            self.callbacks[event_type] = callback
            return True
        return False

    def _get_device_info(self, device_path):
        """Get device information for display purposes."""
        try:
            obj = self._bus.get_object(BLUEZ_SERVICE_NAME, device_path)
            props = dbus.Interface(obj, DBUS_PROPERTIES)
            name = props.Get(DEVICE_INTERFACE, "Name")
            addr = props.Get(DEVICE_INTERFACE, "Address")
            return f"{name} ({addr})"
        except:
            return device_path

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        """Authorize a service with callback if provided."""
        device_info = self._get_device_info(device)
        
        if self.callbacks["authorize_service"]:
            result = self.callbacks["authorize_service"](device_info, uuid)
            if not result:
                print_and_log(f"[-] Service {uuid} authorization rejected for {device_info} by callback", LOG__DEBUG)
                raise RejectedException("Service authorization rejected by callback")
        elif not self.auto_accept:
            print_and_log(f"[-] Service {uuid} authorization rejected for {device_info} (auto-accept disabled)", LOG__DEBUG)
            raise RejectedException("Service authorization rejected (auto-accept disabled)")
            
        print_and_log(f"[+] Service {uuid} authorized for {device_info}", LOG__DEBUG)
        return

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        """Request PIN code with callback if provided."""
        device_info = self._get_device_info(device)
        
        if self.callbacks["request_pin_code"]:
            pin = self.callbacks["request_pin_code"](device_info)
            print_and_log(f"[+] PIN code provided by callback for {device_info}", LOG__DEBUG)
            return pin
            
        print_and_log(f"[+] Using default PIN code for {device_info}: {self.default_pin}", LOG__DEBUG)
        return self.default_pin

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        """Request passkey with callback if provided."""
        device_info = self._get_device_info(device)
        
        if self.callbacks["request_passkey"]:
            passkey = self.callbacks["request_passkey"](device_info)
            print_and_log(f"[+] Passkey provided by callback for {device_info}", LOG__DEBUG)
            return dbus.UInt32(passkey)
            
        print_and_log(f"[+] Using default passkey for {device_info}: {self.default_passkey}", LOG__DEBUG)
        return dbus.UInt32(self.default_passkey)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        """Display passkey with callback if provided."""
        device_info = self._get_device_info(device)
        
        if self.callbacks["display_passkey"]:
            self.callbacks["display_passkey"](device_info, passkey, entered)
        
        print_and_log(f"[+] DisplayPasskey: {device_info} - {passkey} ({entered} digits entered)", LOG__DEBUG)

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        """Display PIN code with callback if provided."""
        device_info = self._get_device_info(device)
        
        if self.callbacks["display_pin_code"]:
            self.callbacks["display_pin_code"](device_info, pincode)
        
        print_and_log(f"[+] DisplayPinCode: {device_info} - {pincode}", LOG__DEBUG)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        """Request confirmation with callback if provided."""
        device_info = self._get_device_info(device)
        
        if self.callbacks["request_confirmation"]:
            result = self.callbacks["request_confirmation"](device_info, passkey)
            if not result:
                print_and_log(f"[-] Passkey confirmation rejected for {device_info} by callback", LOG__DEBUG)
                raise RejectedException("Passkey confirmation rejected by callback")
        elif not self.auto_accept:
            print_and_log(f"[-] Passkey confirmation rejected for {device_info} (auto-accept disabled)", LOG__DEBUG)
            raise RejectedException("Passkey confirmation rejected (auto-accept disabled)")
            
        print_and_log(f"[+] Passkey confirmed for {device_info}: {passkey}", LOG__DEBUG)
        return

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        """Request authorization with callback if provided."""
        device_info = self._get_device_info(device)
        
        if self.callbacks["request_authorization"]:
            result = self.callbacks["request_authorization"](device_info)
            if not result:
                print_and_log(f"[-] Pairing authorization rejected for {device_info} by callback", LOG__DEBUG)
                raise RejectedException("Pairing authorization rejected by callback")
        elif not self.auto_accept:
            print_and_log(f"[-] Pairing authorization rejected for {device_info} (auto-accept disabled)", LOG__DEBUG)
            raise RejectedException("Pairing authorization rejected (auto-accept disabled)")
            
        print_and_log(f"[+] Pairing authorized for {device_info}", LOG__DEBUG)
        return

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Cancel(self):
        """Cancel the current request with callback if provided."""
        if self.callbacks["cancel"]:
            self.callbacks["cancel"]()
        
        print_and_log("[+] Request canceled", LOG__DEBUG)


class PairingAgent(EnhancedAgent):
    """An agent specifically designed for pairing operations with automatic trust management."""
    
    def __init__(self, bus, agent_path=AGENT_NAMESPACE):
        super().__init__(bus, agent_path)
        self.trust_manager = TrustManager(bus)
        self.pairing_callbacks = {
            "pairing_started": None,
            "pairing_succeeded": None,
            "pairing_failed": None,
            "device_trusted": None,
        }
        
    def set_pairing_callback(self, event_type, callback):
        """Set a callback for a specific pairing event."""
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
                        break
                except:
                    pass
                    
                time.sleep(1)
                
            if not paired:
                print_and_log(f"[-] Pairing with {device_info} timed out", LOG__GENERAL)
                if self.pairing_callbacks["pairing_failed"]:
                    self.pairing_callbacks["pairing_failed"](device_info, "Timeout")
                return False
                
            print_and_log(f"[+] Successfully paired with {device_info}", LOG__GENERAL)
            
            # Set trusted if requested
            if set_trusted:
                trusted = self.trust_manager.set_trusted(device_path, True)
                if trusted and self.pairing_callbacks["device_trusted"]:
                    self.pairing_callbacks["device_trusted"](device_info)
            
            # Notify pairing succeeded
            if self.pairing_callbacks["pairing_succeeded"]:
                self.pairing_callbacks["pairing_succeeded"](device_info)
                
            return True
            
        except dbus.exceptions.DBusException as e:
            error_name = e.get_dbus_name()
            error_msg = e.get_dbus_message()
            print_and_log(f"[-] Pairing failed: {error_name} - {error_msg}", LOG__GENERAL)
            
            if self.pairing_callbacks["pairing_failed"]:
                self.pairing_callbacks["pairing_failed"](device_info, f"{error_name}: {error_msg}")
                
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


def create_agent(bus, agent_type="simple", capabilities="NoInputNoOutput", default=True, auto_accept=True):
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
    
    AgentClass = agent_types.get(agent_type.lower(), SimpleAgent)
    agent = AgentClass(bus)
    
    if isinstance(agent, (EnhancedAgent, PairingAgent)):
        agent.auto_accept = auto_accept
    
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
