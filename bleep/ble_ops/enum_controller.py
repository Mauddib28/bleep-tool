"""
Enumeration controller for multi-attempt device enumeration.

This module orchestrates enumeration attempts with proper error handling,
using existing BLEEP components (ReconnectionMonitor, ConnectionResetManager,
landmine mapping) to provide structured enumeration results.
"""

from __future__ import annotations

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.core.errors import (
    BLEEPError,
    ConnectionError,
    NotAuthorizedError,
    DeviceNotFoundError,
    ServicesNotResolvedError,
)
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy

__all__ = ["EnumerationController", "EnumerationResult", "ErrorAction"]


class ErrorAction(Enum):
    """Action to take based on error type."""
    RECONNECT = "reconnect"  # Timeout, disconnect - retry connection
    ANNOTATE_AND_CONTINUE = "annotate_continue"  # Auth rejection - log and retry
    GIVE_UP = "give_up"  # Agent required, repeated failures - stop trying


@dataclass
class ConnectionAnnotation:
    """Annotation for a connection attempt error."""
    timestamp: float
    error_type: str  # 'auth_required', 'rejected', 'timeout', 'disconnect', 'unknown'
    details: str
    attempted_solution: Optional[str]  # 'reconnect', 'agent_required', None


@dataclass
class EnumerationResult:
    """Result of enumeration attempt(s)."""
    success: bool
    data: Optional[Dict[str, Any]] = None  # Service/characteristic data
    annotations: List[ConnectionAnnotation] = field(default_factory=list)
    error_summary: Optional[str] = None
    attempts: int = 0
    device: Optional[Any] = None  # Device object if successful
    landmine_map: Optional[Dict[str, Any]] = None
    permission_map: Optional[Dict[str, Any]] = None


class EnumerationController:
    """
    Orchestrates multi-attempt enumeration with proper error handling.
    
    Uses existing BLEEP components (ReconnectionMonitor, ConnectionResetManager,
    landmine mapping) to provide structured enumeration results with annotations.
    """
    
    MAX_ATTEMPTS = 3
    
    def __init__(self, target_mac: str):
        """
        Initialize enumeration controller.
        
        Parameters
        ----------
        target_mac : str
            Target device MAC address
        """
        self.target_mac = target_mac.upper()
        self.attempts = 0
        self.annotations: List[ConnectionAnnotation] = []
    
    def enumerate(self, mode: str = 'passive') -> EnumerationResult:
        """
        Perform enumeration with up to MAX_ATTEMPTS attempts.
        
        Parameters
        ----------
        mode : str
            Enumeration mode ('passive', 'naggy', 'pokey', 'bruteforce')
            Currently only 'passive' is fully supported
        
        Returns
        -------
        EnumerationResult
            Result containing data or error annotations
        """
        print_and_log(
            f"[*] Starting enumeration controller for {self.target_mac} (max {self.MAX_ATTEMPTS} attempts)",
            LOG__GENERAL
        )
        
        while self.attempts < self.MAX_ATTEMPTS:
            self.attempts += 1
            print_and_log(
                f"[*] Enumeration attempt {self.attempts}/{self.MAX_ATTEMPTS} for {self.target_mac}",
                LOG__GENERAL
            )
            
            try:
                # Attempt connection and enumeration
                device, mapping, landmine_map, perm_map = connect_and_enumerate__bluetooth__low_energy(
                    self.target_mac,
                    deep_enumeration=(mode in ['pokey', 'bruteforce']),
                )
                
                # Success - return result
                print_and_log(
                    f"[+] Enumeration successful for {self.target_mac} on attempt {self.attempts}",
                    LOG__GENERAL
                )
                
                return EnumerationResult(
                    success=True,
                    data=mapping,
                    annotations=self.annotations.copy(),
                    attempts=self.attempts,
                    device=device,
                    landmine_map=landmine_map,
                    permission_map=perm_map,
                )
                
            except Exception as e:
                # Handle error and determine action
                error_action = self._handle_error(e)
                
                # Annotate the error
                annotation = self._create_annotation(e, error_action)
                self.annotations.append(annotation)
                
                # Determine if we should continue
                if error_action == ErrorAction.GIVE_UP:
                    print_and_log(
                        f"[-] Giving up enumeration for {self.target_mac} after {self.attempts} attempts",
                        LOG__GENERAL
                    )
                    break
                elif error_action == ErrorAction.RECONNECT:
                    print_and_log(
                        f"[*] Will retry connection for {self.target_mac}",
                        LOG__DEBUG
                    )
                    # Brief delay before retry
                    time.sleep(1.0)
                elif error_action == ErrorAction.ANNOTATE_AND_CONTINUE:
                    print_and_log(
                        f"[*] Annotated error, will retry for {self.target_mac}",
                        LOG__DEBUG
                    )
                    # Brief delay before retry
                    time.sleep(0.5)
        
        # All attempts exhausted or gave up
        error_summary = self._generate_error_summary()
        
        return EnumerationResult(
            success=False,
            annotations=self.annotations.copy(),
            error_summary=error_summary,
            attempts=self.attempts,
        )
    
    def _handle_error(self, error: Exception) -> ErrorAction:
        """
        Determine action based on error type.
        
        Parameters
        ----------
        error : Exception
            The error that occurred
        
        Returns
        -------
        ErrorAction
            Action to take
        """
        # Timeout or connection errors - retry
        if isinstance(error, (ConnectionError, ServicesNotResolvedError)):
            return ErrorAction.RECONNECT
        
        # Authorization errors - annotate and continue (up to limit)
        if isinstance(error, NotAuthorizedError):
            if self.attempts >= 2:
                # After 2 attempts, likely need agent
                return ErrorAction.GIVE_UP
            return ErrorAction.ANNOTATE_AND_CONTINUE
        
        # Device not found - give up (won't appear by retrying)
        if isinstance(error, DeviceNotFoundError):
            return ErrorAction.GIVE_UP
        
        # Check for timeout/disconnect in error message
        error_str = str(error).lower()
        if any(keyword in error_str for keyword in ['timeout', 'disconnect', 'connection']):
            return ErrorAction.RECONNECT
        
        # Check for auth/rejection in error message
        if any(keyword in error_str for keyword in ['auth', 'reject', 'not authorized', 'permission']):
            if self.attempts >= 2:
                return ErrorAction.GIVE_UP
            return ErrorAction.ANNOTATE_AND_CONTINUE
        
        # Unknown error - give up after first attempt to avoid infinite loops
        if self.attempts >= 2:
            return ErrorAction.GIVE_UP
        
        return ErrorAction.RECONNECT
    
    def _create_annotation(self, error: Exception, action: ErrorAction) -> ConnectionAnnotation:
        """
        Create annotation from error.
        
        Parameters
        ----------
        error : Exception
            The error that occurred
        action : ErrorAction
            Action determined for this error
        
        Returns
        -------
        ConnectionAnnotation
            Annotation object
        """
        error_type = "unknown"
        if isinstance(error, ConnectionError):
            error_type = "disconnect"
        elif isinstance(error, NotAuthorizedError):
            error_type = "auth_required"
        elif isinstance(error, ServicesNotResolvedError):
            error_type = "timeout"
        elif isinstance(error, DeviceNotFoundError):
            error_type = "not_found"
        
        attempted_solution = None
        if action == ErrorAction.RECONNECT:
            attempted_solution = "reconnect"
        elif action == ErrorAction.GIVE_UP:
            attempted_solution = "agent_required" if isinstance(error, NotAuthorizedError) else "max_attempts"
        
        return ConnectionAnnotation(
            timestamp=time.time(),
            error_type=error_type,
            details=str(error),
            attempted_solution=attempted_solution,
        )
    
    def _generate_error_summary(self) -> str:
        """
        Generate human-readable error summary.
        
        Returns
        -------
        str
            Summary of errors encountered
        """
        if not self.annotations:
            return "No errors recorded"
        
        error_counts: Dict[str, int] = {}
        for annotation in self.annotations:
            error_counts[annotation.error_type] = error_counts.get(annotation.error_type, 0) + 1
        
        summary_parts = [f"Failed after {self.attempts} attempt(s)"]
        
        for error_type, count in error_counts.items():
            summary_parts.append(f"{error_type}: {count}")
        
        # Add recommendations
        if any(a.error_type == "auth_required" for a in self.annotations):
            summary_parts.append("Recommendation: Agent may be required for pairing")
        
        if any(a.error_type == "timeout" for a in self.annotations):
            summary_parts.append("Recommendation: Device may be out of range or unresponsive")
        
        return "; ".join(summary_parts)
    
    def _should_continue(self) -> bool:
        """
        Check if enumeration should continue.
        
        Returns
        -------
        bool
            True if should continue, False otherwise
        """
        return self.attempts < self.MAX_ATTEMPTS
