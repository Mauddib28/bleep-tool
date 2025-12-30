"""
I/O handlers for Bluetooth pairing agents.

This module provides an abstract interface and concrete implementations for
handling user interaction during Bluetooth pairing operations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict, Any

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__USER, LOG__AGENT

__all__ = [
    "AgentIOHandler", 
    "CliIOHandler", 
    "ProgrammaticIOHandler", 
    "AutoAcceptIOHandler",
    "create_io_handler"
]


class AgentIOHandler(ABC):
    """Interface for handling I/O operations during pairing."""
    
    @abstractmethod
    def request_pin_code(self, device_info: str) -> str:
        """Request PIN code from user.
        
        Parameters
        ----------
        device_info : str
            Human-readable device information
            
        Returns
        -------
        str
            PIN code entered by user
        """
        pass
        
    @abstractmethod
    def display_pin_code(self, device_info: str, pincode: str) -> None:
        """Display PIN code to user.
        
        Parameters
        ----------
        device_info : str
            Human-readable device information
        pincode : str
            PIN code to display
        """
        pass
        
    @abstractmethod
    def request_passkey(self, device_info: str) -> int:
        """Request passkey from user.
        
        Parameters
        ----------
        device_info : str
            Human-readable device information
            
        Returns
        -------
        int
            Passkey entered by user (0-999999)
        """
        pass
        
    @abstractmethod
    def display_passkey(self, device_info: str, passkey: int, entered: int) -> None:
        """Display passkey to user.
        
        Parameters
        ----------
        device_info : str
            Human-readable device information
        passkey : int
            Passkey to display
        entered : int
            Number of digits already entered by remote device
        """
        pass
        
    @abstractmethod
    def request_confirmation(self, device_info: str, passkey: int) -> bool:
        """Request confirmation of passkey from user.
        
        Parameters
        ----------
        device_info : str
            Human-readable device information
        passkey : int
            Passkey to confirm
            
        Returns
        -------
        bool
            True if user confirms, False otherwise
        """
        pass
        
    @abstractmethod
    def request_authorization(self, device_info: str) -> bool:
        """Request authorization from user.
        
        Parameters
        ----------
        device_info : str
            Human-readable device information
            
        Returns
        -------
        bool
            True if user authorizes, False otherwise
        """
        pass
        
    @abstractmethod
    def authorize_service(self, device_info: str, uuid: str) -> bool:
        """Request service authorization from user.
        
        Parameters
        ----------
        device_info : str
            Human-readable device information
        uuid : str
            UUID of the service
            
        Returns
        -------
        bool
            True if user authorizes, False otherwise
        """
        pass
        
    @abstractmethod
    def cancel(self) -> None:
        """Notify that an ongoing request was cancelled."""
        pass
        
    @abstractmethod
    def notify_error(self, device_info: str, error_message: str) -> None:
        """Notify user of an error.
        
        Parameters
        ----------
        device_info : str
            Human-readable device information
        error_message : str
            Error message to display
        """
        pass
        
    @abstractmethod
    def notify_success(self, device_info: str, message: str) -> None:
        """Notify user of a success.
        
        Parameters
        ----------
        device_info : str
            Human-readable device information
        message : str
            Success message to display
        """
        pass


class CliIOHandler(AgentIOHandler):
    """IO Handler for CLI interaction."""
    
    def request_pin_code(self, device_info: str) -> str:
        """Request PIN code from user via CLI."""
        print_and_log(
            f"[*] CliIOHandler: PIN code request for {device_info} (handler_type=cli, auto_accept=False)",
            LOG__AGENT
        )
        pin = input("Enter PIN code: ")
        print_and_log(f"[+] PIN code entered: {pin}", LOG__AGENT)
        return pin
        
    def display_pin_code(self, device_info: str, pincode: str) -> None:
        """Display PIN code to user via CLI."""
        print_and_log(f"[*] PIN code for {device_info}: {pincode}", LOG__AGENT)
        print_and_log("[*] Enter this PIN code on the device when prompted.", LOG__AGENT)
        
    def request_passkey(self, device_info: str) -> int:
        """Request passkey from user via CLI."""
        print_and_log(
            f"[*] CliIOHandler: passkey request for {device_info} (handler_type=cli, auto_accept=False)",
            LOG__AGENT
        )
        while True:
            try:
                passkey = int(input("Enter passkey (0-999999): "))
                print_and_log(f"[+] Passkey entered: {passkey:06d}", LOG__AGENT)
                return passkey
            except ValueError:
                print_and_log("[-] Invalid passkey. Please enter a number.", LOG__AGENT)
        
    def display_passkey(self, device_info: str, passkey: int, entered: int) -> None:
        """Display passkey to user via CLI."""
        if entered > 0:
            print_and_log(f"[*] Passkey for {device_info}: {passkey:06d} ({entered} digits entered)", LOG__AGENT)
        else:
            print_and_log(f"[*] Passkey for {device_info}: {passkey:06d}", LOG__AGENT)
        print_and_log("[*] Enter this passkey on the device when prompted.", LOG__AGENT)
        
    def request_confirmation(self, device_info: str, passkey: int) -> bool:
        """Request confirmation of passkey from user via CLI."""
        print_and_log(
            f"[*] CliIOHandler: confirm passkey for {device_info} passkey={passkey:06d} (handler_type=cli, auto_accept=False)",
            LOG__AGENT
        )
        response = input("Confirm? (yes/no): ").lower()
        confirmed = response in ["yes", "y"]
        print_and_log(f"[{'+' if confirmed else '-'}] Passkey confirmation: {'accepted' if confirmed else 'rejected'}", LOG__AGENT)
        return confirmed
        
    def request_authorization(self, device_info: str) -> bool:
        """Request authorization from user via CLI."""
        print_and_log(
            f"[*] CliIOHandler: authorize pairing for {device_info} (handler_type=cli, auto_accept=False)",
            LOG__AGENT
        )
        response = input("Authorize pairing? (yes/no): ").lower()
        authorized = response in ["yes", "y"]
        print_and_log(f"[{'+' if authorized else '-'}] Pairing authorization: {'accepted' if authorized else 'rejected'}", LOG__AGENT)
        return authorized
        
    def authorize_service(self, device_info: str, uuid: str) -> bool:
        """Request service authorization from user via CLI."""
        print_and_log(f"[*] Service authorization request for {device_info}", LOG__USER)
        print_and_log(f"[*] Service UUID: {uuid}", LOG__USER)
        response = input("Authorize service? (yes/no): ").lower()
        return response in ["yes", "y"]
        
    def cancel(self) -> None:
        """Notify that an ongoing request was cancelled."""
        print_and_log("[*] Request cancelled", LOG__USER)
        
    def notify_error(self, device_info: str, error_message: str) -> None:
        """Notify user of an error via CLI."""
        print_and_log(f"[-] Error for {device_info}: {error_message}", LOG__USER)
        
    def notify_success(self, device_info: str, message: str) -> None:
        """Notify user of a success via CLI."""
        print_and_log(f"[+] Success for {device_info}: {message}", LOG__USER)


class ProgrammaticIOHandler(AgentIOHandler):
    """IO Handler for programmatic interaction via callbacks."""
    
    def __init__(self):
        """Initialize with empty callback dictionary."""
        self.callbacks = {
            "request_pin_code": None,
            "display_pin_code": None,
            "request_passkey": None,
            "display_passkey": None,
            "request_confirmation": None,
            "request_authorization": None,
            "authorize_service": None,
            "cancel": None,
            "notify_error": None,
            "notify_success": None,
        }
        self.default_pin = "0000"
        self.default_passkey = 0
        self.auto_accept = False
        
    def set_callback(self, event: str, callback: Callable) -> bool:
        """Set a callback for a specific event.
        
        Parameters
        ----------
        event : str
            Event name (method name in the interface)
        callback : callable
            Callback function to call for the event
            
        Returns
        -------
        bool
            True if the callback was set, False if the event name is invalid
        """
        if event in self.callbacks:
            self.callbacks[event] = callback
            return True
        return False
        
    def request_pin_code(self, device_info: str) -> str:
        """Request PIN code via callback if available."""
        if self.callbacks["request_pin_code"]:
            return self.callbacks["request_pin_code"](device_info)
            
        # Log default behavior
        print_and_log(
            f"[*] ProgrammaticIOHandler: default PIN for {device_info} (auto_accept={self.auto_accept}): {self.default_pin}",
            LOG__AGENT,
        )
        return self.default_pin
        
    def display_pin_code(self, device_info: str, pincode: str) -> None:
        """Display PIN code via callback if available."""
        if self.callbacks["display_pin_code"]:
            self.callbacks["display_pin_code"](device_info, pincode)
        else:
            # Log even if no callback
            print_and_log(f"[*] PIN code for {device_info}: {pincode}", LOG__AGENT)
        
    def request_passkey(self, device_info: str) -> int:
        """Request passkey via callback if available."""
        if self.callbacks["request_passkey"]:
            return self.callbacks["request_passkey"](device_info)
            
        # Log default behavior
        print_and_log(
            f"[*] ProgrammaticIOHandler: default passkey for {device_info} (auto_accept={self.auto_accept}): {self.default_passkey:06d}",
            LOG__AGENT,
        )
        return self.default_passkey
        
    def display_passkey(self, device_info: str, passkey: int, entered: int) -> None:
        """Display passkey via callback if available."""
        if self.callbacks["display_passkey"]:
            self.callbacks["display_passkey"](device_info, passkey, entered)
        else:
            # Log even if no callback
            if entered > 0:
                print_and_log(f"[*] Passkey for {device_info}: {passkey:06d} ({entered} digits entered)", LOG__AGENT)
            else:
                print_and_log(f"[*] Passkey for {device_info}: {passkey:06d}", LOG__AGENT)
        
    def request_confirmation(self, device_info: str, passkey: int) -> bool:
        """Request confirmation via callback if available."""
        if self.callbacks["request_confirmation"]:
            return self.callbacks["request_confirmation"](device_info, passkey)
            
        # Log default behavior
        print_and_log(
            f"[*] ProgrammaticIOHandler: confirmation for {device_info} passkey={passkey:06d} auto_accept={self.auto_accept}",
            LOG__AGENT,
        )
            
        return self.auto_accept
        
    def request_authorization(self, device_info: str) -> bool:
        """Request authorization via callback if available."""
        if self.callbacks["request_authorization"]:
            return self.callbacks["request_authorization"](device_info)
            
        # Log default behavior
        print_and_log(
            f"[*] ProgrammaticIOHandler: pairing authorization for {device_info} auto_accept={self.auto_accept}",
            LOG__AGENT,
        )
            
        return self.auto_accept
        
    def authorize_service(self, device_info: str, uuid: str) -> bool:
        """Request service authorization via callback if available."""
        if self.callbacks["authorize_service"]:
            return self.callbacks["authorize_service"](device_info, uuid)
            
        # Log default behavior
        if self.auto_accept:
            print_and_log(f"[*] Auto-authorizing service {uuid} for {device_info}", LOG__DEBUG)
        else:
            print_and_log(f"[*] Auto-rejecting service {uuid} for {device_info}", LOG__DEBUG)
            
        return self.auto_accept
        
    def cancel(self) -> None:
        """Notify cancellation via callback if available."""
        if self.callbacks["cancel"]:
            self.callbacks["cancel"]()
        else:
            # Log even if no callback
            print_and_log("[*] Request cancelled", LOG__DEBUG)
            
    def notify_error(self, device_info: str, error_message: str) -> None:
        """Notify error via callback if available."""
        if self.callbacks["notify_error"]:
            self.callbacks["notify_error"](device_info, error_message)
        else:
            # Log even if no callback
            print_and_log(f"[-] Error for {device_info}: {error_message}", LOG__DEBUG)
            
    def notify_success(self, device_info: str, message: str) -> None:
        """Notify success via callback if available."""
        if self.callbacks["notify_success"]:
            self.callbacks["notify_success"](device_info, message)
        else:
            # Log even if no callback
            print_and_log(f"[+] Success for {device_info}: {message}", LOG__DEBUG)


class AutoAcceptIOHandler(AgentIOHandler):
    """IO Handler that automatically accepts all pairing requests."""
    
    def __init__(self):
        """Initialize with default values."""
        self.default_pin = "0000"
        self.default_passkey = 0
        self.verbose = True  # Set to False to disable logging
        
    def request_pin_code(self, device_info: str) -> str:
        """Auto-accept PIN code request."""
        if self.verbose:
            print_and_log(
                f"[*] AutoAcceptIOHandler: PIN request for {device_info} default_pin='{self.default_pin}'",
                LOG__AGENT,
            )
        return self.default_pin
        
    def display_pin_code(self, device_info: str, pincode: str) -> None:
        """Log PIN code display."""
        if self.verbose:
            print_and_log(f"[*] PIN code for {device_info}: {pincode}", LOG__AGENT)
        
    def request_passkey(self, device_info: str) -> int:
        """Auto-accept passkey request."""
        if self.verbose:
            print_and_log(
                f"[*] AutoAcceptIOHandler: passkey request for {device_info} default_passkey={self.default_passkey:06d}",
                LOG__AGENT,
            )
        return self.default_passkey
        
    def display_passkey(self, device_info: str, passkey: int, entered: int) -> None:
        """Log passkey display."""
        if self.verbose:
            if entered > 0:
                print_and_log(f"[*] Passkey for {device_info}: {passkey:06d} ({entered} digits entered)", LOG__AGENT)
            else:
                print_and_log(f"[*] Passkey for {device_info}: {passkey:06d}", LOG__AGENT)
        
    def request_confirmation(self, device_info: str, passkey: int) -> bool:
        """Auto-confirm passkey."""
        if self.verbose:
            print_and_log(
                f"[*] AutoAcceptIOHandler: confirm passkey for {device_info} passkey={passkey:06d} (auto_accept=True)",
                LOG__AGENT,
            )
        return True
        
    def request_authorization(self, device_info: str) -> bool:
        """Auto-authorize pairing."""
        if self.verbose:
            print_and_log(
                f"[*] AutoAcceptIOHandler: authorize pairing for {device_info} (auto_accept=True)",
                LOG__AGENT,
            )
        return True
        
    def authorize_service(self, device_info: str, uuid: str) -> bool:
        """Auto-authorize service."""
        if self.verbose:
            print_and_log(f"[*] Auto-authorizing service {uuid} for {device_info}", LOG__DEBUG)
        return True
        
    def cancel(self) -> None:
        """Log cancellation."""
        if self.verbose:
            print_and_log("[*] Request cancelled", LOG__DEBUG)
            
    def notify_error(self, device_info: str, error_message: str) -> None:
        """Log error."""
        if self.verbose:
            print_and_log(f"[-] Error for {device_info}: {error_message}", LOG__DEBUG)
            
    def notify_success(self, device_info: str, message: str) -> None:
        """Log success."""
        if self.verbose:
            print_and_log(f"[+] Success for {device_info}: {message}", LOG__DEBUG)


def create_io_handler(handler_type: str = "cli", **kwargs) -> AgentIOHandler:
    """Create an IO handler of the specified type.
    
    Parameters
    ----------
    handler_type : str
        Type of IO handler to create: "cli", "programmatic", or "auto"
    **kwargs : dict
        Additional arguments to pass to the IO handler constructor
        
    Returns
    -------
    AgentIOHandler
        The created IO handler
        
    Raises
    ------
    ValueError
        If handler_type is invalid
    """
    if handler_type == "cli":
        return CliIOHandler()
    elif handler_type == "programmatic":
        handler = ProgrammaticIOHandler()
        
        # Configure callbacks
        for event, callback in kwargs.items():
            if event.startswith("on_"):  # Convert on_request_pin_code to request_pin_code
                event_name = event[3:]
                handler.set_callback(event_name, callback)
            elif event in handler.callbacks:
                handler.set_callback(event, callback)
        
        # Configure other options
        if "auto_accept" in kwargs:
            handler.auto_accept = kwargs["auto_accept"]
        if "default_pin" in kwargs:
            handler.default_pin = kwargs["default_pin"]
        if "default_passkey" in kwargs:
            handler.default_passkey = kwargs["default_passkey"]
            
        return handler
    elif handler_type == "auto":
        handler = AutoAcceptIOHandler()
        
        # Configure options
        if "default_pin" in kwargs:
            handler.default_pin = kwargs["default_pin"]
        if "default_passkey" in kwargs:
            handler.default_passkey = kwargs["default_passkey"]
        if "verbose" in kwargs:
            handler.verbose = kwargs["verbose"]
            
        return handler
    else:
        raise ValueError(f"Invalid IO handler type: {handler_type}")
