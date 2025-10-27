"""
State machine for Bluetooth pairing process.

This module provides a state machine for managing the complex state transitions
during Bluetooth pairing and bonding processes.
"""

from __future__ import annotations

import time
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable, Set

from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.dbuslayer.agent_io import AgentIOHandler

__all__ = ["PairingState", "PairingStateMachine", "InvalidTransitionError"]


class PairingState(Enum):
    """States in the Bluetooth pairing process."""
    
    # Initial state
    IDLE = auto()
    
    # Pairing process initiation
    INITIATED = auto()
    
    # Authentication states
    PIN_REQUESTED = auto()
    PASSKEY_REQUESTED = auto()
    DISPLAYING_PASSKEY = auto()
    CONFIRMATION_REQUESTED = auto()
    AUTHORIZATION_REQUESTED = auto()
    SERVICE_AUTHORIZATION = auto()
    
    # Bonding state (key exchange)
    BONDING = auto()
    
    # Terminal states
    COMPLETE = auto()
    FAILED = auto()
    CANCELLED = auto()


class InvalidTransitionError(Exception):
    """Error raised when an invalid state transition is attempted."""
    pass


class PairingStateMachine:
    """State machine for Bluetooth pairing process."""
    
    # Define valid state transitions
    _VALID_TRANSITIONS = {
        PairingState.IDLE: {PairingState.INITIATED},
        PairingState.INITIATED: {
            PairingState.PIN_REQUESTED, 
            PairingState.PASSKEY_REQUESTED,
            PairingState.DISPLAYING_PASSKEY,
            PairingState.CONFIRMATION_REQUESTED,
            PairingState.AUTHORIZATION_REQUESTED,
            PairingState.BONDING,
            PairingState.FAILED,
            PairingState.CANCELLED
        },
        PairingState.PIN_REQUESTED: {
            PairingState.BONDING,
            PairingState.FAILED,
            PairingState.CANCELLED
        },
        PairingState.PASSKEY_REQUESTED: {
            PairingState.BONDING,
            PairingState.FAILED,
            PairingState.CANCELLED
        },
        PairingState.DISPLAYING_PASSKEY: {
            PairingState.BONDING,
            PairingState.FAILED, 
            PairingState.CANCELLED
        },
        PairingState.CONFIRMATION_REQUESTED: {
            PairingState.BONDING,
            PairingState.FAILED,
            PairingState.CANCELLED
        },
        PairingState.AUTHORIZATION_REQUESTED: {
            PairingState.SERVICE_AUTHORIZATION,
            PairingState.BONDING,
            PairingState.FAILED,
            PairingState.CANCELLED
        },
        PairingState.SERVICE_AUTHORIZATION: {
            PairingState.BONDING,
            PairingState.FAILED,
            PairingState.CANCELLED
        },
        PairingState.BONDING: {
            PairingState.COMPLETE,
            PairingState.FAILED,
            PairingState.CANCELLED
        },
        PairingState.COMPLETE: {PairingState.IDLE},
        PairingState.FAILED: {PairingState.IDLE},
        PairingState.CANCELLED: {PairingState.IDLE}
    }
    
    def __init__(self, io_handler: AgentIOHandler):
        """Initialize the pairing state machine.
        
        Parameters
        ----------
        io_handler : AgentIOHandler
            Handler for I/O operations during pairing
        """
        self._state = PairingState.IDLE
        self._io_handler = io_handler
        self._device_path = None
        self._device_info = None
        self._error = None
        
        # Data for different pairing methods
        self._pin_code = None
        self._passkey = None
        self._entered_digits = 0
        self._service_uuid = None
        
        # State transition callbacks
        self._callbacks = {
            "on_state_change": None,
            "on_complete": None,
            "on_failed": None,
            "on_cancelled": None
        }
        
        # Pairing data to be stored on completion
        self._pairing_data = {}
        
    def set_callback(self, event: str, callback: Callable) -> bool:
        """Set a callback for a state machine event.
        
        Parameters
        ----------
        event : str
            Event name: "on_state_change", "on_complete", "on_failed", "on_cancelled"
        callback : callable
            Callback function
            
        Returns
        -------
        bool
            True if set successfully, False otherwise
        """
        if event in self._callbacks:
            self._callbacks[event] = callback
            return True
        return False
        
    @property
    def state(self) -> PairingState:
        """Get the current state.
        
        Returns
        -------
        PairingState
            Current state of the pairing process
        """
        return self._state
        
    @property
    def device_path(self) -> Optional[str]:
        """Get the device path.
        
        Returns
        -------
        str or None
            D-Bus path of the device being paired with
        """
        return self._device_path
        
    @property
    def device_info(self) -> Optional[str]:
        """Get the device info.
        
        Returns
        -------
        str or None
            Human-readable device information
        """
        return self._device_info
        
    @property
    def error(self) -> Optional[Exception]:
        """Get the last error.
        
        Returns
        -------
        Exception or None
            Last error that occurred during pairing
        """
        return self._error
        
    @property
    def pairing_data(self) -> Dict[str, Any]:
        """Get the pairing data.
        
        Returns
        -------
        dict
            Data collected during the pairing process
        """
        return self._pairing_data.copy()
        
    def transition(self, new_state: PairingState) -> None:
        """Transition to a new state.
        
        Parameters
        ----------
        new_state : PairingState
            New state to transition to
            
        Raises
        ------
        InvalidTransitionError
            If the transition is not valid
        """
        if new_state not in self._VALID_TRANSITIONS.get(self._state, set()):
            raise InvalidTransitionError(
                f"Invalid transition: {self._state} -> {new_state}"
            )
            
        old_state = self._state
        self._state = new_state
        
        # Log the transition
        print_and_log(
            f"[*] Pairing state transition: {old_state.name} -> {new_state.name}", 
            LOG__DEBUG
        )
        
        # Call state change callback
        if self._callbacks["on_state_change"]:
            self._callbacks["on_state_change"](old_state, new_state)
            
        # Call terminal state callbacks
        if new_state == PairingState.COMPLETE and self._callbacks["on_complete"]:
            self._callbacks["on_complete"](self._pairing_data)
        elif new_state == PairingState.FAILED and self._callbacks["on_failed"]:
            self._callbacks["on_failed"](self._error)
        elif new_state == PairingState.CANCELLED and self._callbacks["on_cancelled"]:
            self._callbacks["on_cancelled"]()
            
    def start_pairing(self, device_path: str, device_info: str) -> None:
        """Start the pairing process.
        
        Parameters
        ----------
        device_path : str
            D-Bus path of the device to pair with
        device_info : str
            Human-readable device information
        """
        if self._state != PairingState.IDLE:
            self.reset()
            
        self._device_path = device_path
        self._device_info = device_info
        self._pairing_data = {
            "device_path": device_path,
            "device_info": device_info,
            "timestamp": time.time()
        }
        
        self.transition(PairingState.INITIATED)
        
    def handle_pin_code_request(self) -> str:
        """Handle a PIN code request.
        
        Returns
        -------
        str
            PIN code to return to the requester
        """
        if self._state not in [PairingState.INITIATED, PairingState.PIN_REQUESTED]:
            raise InvalidTransitionError(
                f"Cannot handle PIN code request in state {self._state}"
            )
            
        self.transition(PairingState.PIN_REQUESTED)
        
        try:
            self._pin_code = self._io_handler.request_pin_code(self._device_info)
            self._pairing_data["pin_code"] = self._pin_code
            return self._pin_code
        except Exception as e:
            self._error = e
            self.transition(PairingState.FAILED)
            raise
            
    def handle_display_pin_code(self, pincode: str) -> None:
        """Handle displaying a PIN code.
        
        Parameters
        ----------
        pincode : str
            PIN code to display
        """
        self._pin_code = pincode
        self._pairing_data["pin_code"] = pincode
        
        if self._state == PairingState.IDLE:
            self.transition(PairingState.INITIATED)
            
        self.transition(PairingState.DISPLAYING_PASSKEY)
        
        try:
            self._io_handler.display_pin_code(self._device_info, pincode)
        except Exception as e:
            self._error = e
            self.transition(PairingState.FAILED)
            raise
            
    def handle_passkey_request(self) -> int:
        """Handle a passkey request.
        
        Returns
        -------
        int
            Passkey to return to the requester
        """
        if self._state not in [PairingState.INITIATED, PairingState.PASSKEY_REQUESTED]:
            raise InvalidTransitionError(
                f"Cannot handle passkey request in state {self._state}"
            )
            
        self.transition(PairingState.PASSKEY_REQUESTED)
        
        try:
            self._passkey = self._io_handler.request_passkey(self._device_info)
            self._pairing_data["passkey"] = self._passkey
            return self._passkey
        except Exception as e:
            self._error = e
            self.transition(PairingState.FAILED)
            raise
            
    def handle_display_passkey(self, passkey: int, entered: int) -> None:
        """Handle displaying a passkey.
        
        Parameters
        ----------
        passkey : int
            Passkey to display
        entered : int
            Number of digits already entered
        """
        self._passkey = passkey
        self._entered_digits = entered
        self._pairing_data["passkey"] = passkey
        
        if self._state == PairingState.IDLE:
            self.transition(PairingState.INITIATED)
            
        self.transition(PairingState.DISPLAYING_PASSKEY)
        
        try:
            self._io_handler.display_passkey(self._device_info, passkey, entered)
        except Exception as e:
            self._error = e
            self.transition(PairingState.FAILED)
            raise
            
    def handle_confirmation_request(self, passkey: int) -> None:
        """Handle a confirmation request.
        
        Parameters
        ----------
        passkey : int
            Passkey to confirm
            
        Raises
        ------
        Exception
            If the user rejects the confirmation
        """
        self._passkey = passkey
        self._pairing_data["passkey"] = passkey
        
        if self._state not in [PairingState.INITIATED, PairingState.CONFIRMATION_REQUESTED]:
            raise InvalidTransitionError(
                f"Cannot handle confirmation request in state {self._state}"
            )
            
        self.transition(PairingState.CONFIRMATION_REQUESTED)
        
        try:
            result = self._io_handler.request_confirmation(self._device_info, passkey)
            if not result:
                self.transition(PairingState.FAILED)
                self._error = Exception("Confirmation rejected by user")
                raise self._error
        except Exception as e:
            self._error = e
            self.transition(PairingState.FAILED)
            raise
            
    def handle_authorization_request(self) -> None:
        """Handle an authorization request.
        
        Raises
        ------
        Exception
            If the user rejects the authorization
        """
        if self._state not in [PairingState.INITIATED, PairingState.AUTHORIZATION_REQUESTED]:
            raise InvalidTransitionError(
                f"Cannot handle authorization request in state {self._state}"
            )
            
        self.transition(PairingState.AUTHORIZATION_REQUESTED)
        
        try:
            result = self._io_handler.request_authorization(self._device_info)
            if not result:
                self.transition(PairingState.FAILED)
                self._error = Exception("Authorization rejected by user")
                raise self._error
        except Exception as e:
            self._error = e
            self.transition(PairingState.FAILED)
            raise
            
    def handle_service_authorization(self, uuid: str) -> None:
        """Handle a service authorization request.
        
        Parameters
        ----------
        uuid : str
            Service UUID to authorize
            
        Raises
        ------
        Exception
            If the user rejects the service authorization
        """
        self._service_uuid = uuid
        self._pairing_data["service_uuid"] = uuid
        
        if self._state not in [PairingState.INITIATED, PairingState.AUTHORIZATION_REQUESTED, 
                              PairingState.SERVICE_AUTHORIZATION]:
            raise InvalidTransitionError(
                f"Cannot handle service authorization in state {self._state}"
            )
            
        self.transition(PairingState.SERVICE_AUTHORIZATION)
        
        try:
            result = self._io_handler.authorize_service(self._device_info, uuid)
            if not result:
                self.transition(PairingState.FAILED)
                self._error = Exception(f"Service {uuid} authorization rejected by user")
                raise self._error
        except Exception as e:
            self._error = e
            self.transition(PairingState.FAILED)
            raise
            
    def handle_bonding_start(self) -> None:
        """Handle the start of bonding (key exchange)."""
        if self._state not in [PairingState.INITIATED, PairingState.PIN_REQUESTED,
                              PairingState.PASSKEY_REQUESTED, PairingState.DISPLAYING_PASSKEY,
                              PairingState.CONFIRMATION_REQUESTED, PairingState.AUTHORIZATION_REQUESTED,
                              PairingState.SERVICE_AUTHORIZATION]:
            raise InvalidTransitionError(
                f"Cannot start bonding in state {self._state}"
            )
            
        self.transition(PairingState.BONDING)
        
    def handle_pairing_success(self) -> Dict[str, Any]:
        """Handle successful pairing completion.
        
        Returns
        -------
        dict
            Pairing data collected during the process
        """
        if self._state != PairingState.BONDING:
            raise InvalidTransitionError(
                f"Cannot complete pairing in state {self._state}"
            )
            
        self._pairing_data["success"] = True
        self._pairing_data["completion_time"] = time.time()
        
        self.transition(PairingState.COMPLETE)
        self._io_handler.notify_success(self._device_info, "Pairing completed successfully")
        
        return self.pairing_data
        
    def handle_pairing_failed(self, error: Exception) -> None:
        """Handle pairing failure.
        
        Parameters
        ----------
        error : Exception
            Error that caused the failure
        """
        self._error = error
        self._pairing_data["success"] = False
        self._pairing_data["error"] = str(error)
        
        self.transition(PairingState.FAILED)
        self._io_handler.notify_error(self._device_info, f"Pairing failed: {str(error)}")
        
    def handle_cancel(self) -> None:
        """Handle cancellation of the pairing process."""
        self.transition(PairingState.CANCELLED)
        self._io_handler.cancel()
        
    def reset(self) -> None:
        """Reset the state machine to idle state."""
        old_state = self._state
        self._state = PairingState.IDLE
        self._device_path = None
        self._device_info = None
        self._error = None
        self._pin_code = None
        self._passkey = None
        self._entered_digits = 0
        self._service_uuid = None
        self._pairing_data = {}
        
        # Call state change callback
        if self._callbacks["on_state_change"]:
            self._callbacks["on_state_change"](old_state, self._state)
            
        print_and_log("[*] Pairing state machine reset", LOG__DEBUG)
