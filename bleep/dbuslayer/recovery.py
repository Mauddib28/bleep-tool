"""
D-Bus Recovery Manager

This module provides automatic recovery strategies for D-Bus connection issues,
including staged recovery processes and state preservation.

Based on best practices from BlueZ documentation and example scripts.
"""

import os
import time
import subprocess
import threading
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Union, Tuple

import dbus
from gi.repository import GLib

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    BLUEZ_NAMESPACE,
    ADAPTER_INTERFACE,
    DEVICE_INTERFACE,
)
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER
from bleep.dbus.timeout_manager import DBusTimeout
from bleep.dbuslayer.bluez_monitor import get_monitor, register_stall_callback, register_restart_callback

# Type alias for recovery callbacks
RecoveryCallback = Callable[[str, str], None]


class RecoveryStage(Enum):
    """Enum representing stages in the recovery process."""
    DISCONNECT_RECONNECT = 1  # Simple disconnect/reconnect
    INTERFACE_RESET = 2       # Reinitialize D-Bus interfaces
    ADAPTER_RESET = 3         # Reset adapter via BlueZ
    CONTROLLER_RESET = 4      # Reset controller via hciconfig
    BLUETOOTHD_RESTART = 5    # Restart BlueZ service


class ConnectionResetManager:
    """
    Manages connection reset and recovery strategies for BlueZ D-Bus connections.
    
    This class implements a staged recovery process for connection issues,
    starting with simple disconnect/reconnect and escalating to more invasive
    measures if necessary.
    """
    
    def __init__(self):
        """Initialize the connection reset manager."""
        self._recovery_attempts: Dict[str, Dict[RecoveryStage, int]] = {}
        self._recovery_timeouts: Dict[str, Dict[RecoveryStage, float]] = {}
        self._max_attempts = {
            RecoveryStage.DISCONNECT_RECONNECT: 3,
            RecoveryStage.INTERFACE_RESET: 2,
            RecoveryStage.ADAPTER_RESET: 1,
            RecoveryStage.CONTROLLER_RESET: 1,
            RecoveryStage.BLUETOOTHD_RESTART: 1,
        }
        self._stage_timeouts = {
            RecoveryStage.DISCONNECT_RECONNECT: 60.0,  # 1 minute
            RecoveryStage.INTERFACE_RESET: 300.0,      # 5 minutes
            RecoveryStage.ADAPTER_RESET: 900.0,        # 15 minutes
            RecoveryStage.CONTROLLER_RESET: 1800.0,    # 30 minutes
            RecoveryStage.BLUETOOTHD_RESTART: 3600.0,  # 1 hour
        }
        self._recovery_callbacks: List[RecoveryCallback] = []
        self._lock = threading.RLock()
        
        # Register with BlueZ monitor
        register_stall_callback(self._on_bluez_stall)
        register_restart_callback(self._on_bluez_restart)
    
    def _on_bluez_stall(self) -> None:
        """Called when BlueZ service stalls."""
        print_and_log(
            "[!] BlueZ service stall detected, recovery may be needed",
            LOG__USER
        )
    
    def _on_bluez_restart(self) -> None:
        """Called when BlueZ service restarts."""
        print_and_log(
            "[*] BlueZ service restarted, clearing recovery state",
            LOG__GENERAL
        )
        with self._lock:
            self._recovery_attempts.clear()
            self._recovery_timeouts.clear()
    
    def register_recovery_callback(self, callback: RecoveryCallback) -> None:
        """
        Register a callback for recovery events.
        
        Parameters
        ----------
        callback : Callable[[str, str], None]
            Function to call when recovery actions are taken, with parameters
            (device_address, recovery_stage)
        """
        if callback not in self._recovery_callbacks:
            self._recovery_callbacks.append(callback)
    
    def unregister_recovery_callback(self, callback: RecoveryCallback) -> None:
        """
        Unregister a recovery callback.
        
        Parameters
        ----------
        callback : Callable[[str, str], None]
            Callback to unregister
        """
        if callback in self._recovery_callbacks:
            self._recovery_callbacks.remove(callback)
    
    def _notify_recovery(self, device_address: str, stage: RecoveryStage) -> None:
        """
        Notify all registered callbacks of a recovery action.
        
        Parameters
        ----------
        device_address : str
            MAC address of the device being recovered
        stage : RecoveryStage
            Recovery stage being executed
        """
        for callback in self._recovery_callbacks:
            try:
                callback(device_address, stage.name)
            except Exception as e:
                print_and_log(
                    f"[-] Error in recovery callback: {e}",
                    LOG__DEBUG
                )
    
    def _get_next_recovery_stage(self, device_address: str) -> RecoveryStage:
        """
        Determine the next recovery stage for a device.
        
        Parameters
        ----------
        device_address : str
            MAC address of the device
            
        Returns
        -------
        RecoveryStage
            Next recovery stage to try
        """
        with self._lock:
            # Initialize recovery state for this device if needed
            if device_address not in self._recovery_attempts:
                self._recovery_attempts[device_address] = {}
                self._recovery_timeouts[device_address] = {}
            
            # Check if we can retry any previous stage
            for stage in sorted([s for s in RecoveryStage]):
                if stage not in self._recovery_attempts[device_address]:
                    # This stage hasn't been tried yet
                    return stage
                
                attempts = self._recovery_attempts[device_address].get(stage, 0)
                last_attempt = self._recovery_timeouts[device_address].get(stage, 0)
                
                if attempts < self._max_attempts[stage]:
                    # We can retry this stage
                    return stage
                
                # Check if enough time has passed to retry this stage
                timeout = self._stage_timeouts[stage]
                if time.time() - last_attempt > timeout:
                    # Timeout has expired, reset attempts count
                    self._recovery_attempts[device_address][stage] = 0
                    return stage
            
            # If we've exhausted all stages, start from the beginning
            return RecoveryStage.DISCONNECT_RECONNECT
    
    def _record_recovery_attempt(self, device_address: str, stage: RecoveryStage) -> None:
        """
        Record a recovery attempt for a device and stage.
        
        Parameters
        ----------
        device_address : str
            MAC address of the device
        stage : RecoveryStage
            Recovery stage that was attempted
        """
        with self._lock:
            if device_address not in self._recovery_attempts:
                self._recovery_attempts[device_address] = {}
                self._recovery_timeouts[device_address] = {}
            
            current_attempts = self._recovery_attempts[device_address].get(stage, 0)
            self._recovery_attempts[device_address][stage] = current_attempts + 1
            self._recovery_timeouts[device_address][stage] = time.time()
    
    def _recover_disconnect_reconnect(self, device_interface: dbus.Interface) -> bool:
        """
        Simple disconnect/reconnect recovery.
        
        Parameters
        ----------
        device_interface : dbus.Interface
            D-Bus interface to the device
            
        Returns
        -------
        bool
            True if recovery was successful, False otherwise
        """
        try:
            # Try disconnecting first (no-op if not connected)
            try:
                device_interface.Disconnect()
            except dbus.exceptions.DBusException:
                # Ignore - device might not be connected
                pass
            
            time.sleep(1)  # Give BlueZ time to clean up
            
            # Try connecting
            device_interface.Connect()
            
            # Wait for connection to complete
            time.sleep(2)
            
            return True
        except Exception as e:
            print_and_log(
                f"[-] Disconnect/reconnect recovery failed: {e}",
                LOG__DEBUG
            )
            return False
    
    def _recover_interface_reset(self, bus: dbus.Bus, device_path: str) -> bool:
        """
        Reset D-Bus interfaces.
        
        Parameters
        ----------
        bus : dbus.Bus
            D-Bus connection
        device_path : str
            D-Bus path to the device
            
        Returns
        -------
        bool
            True if recovery was successful, False otherwise
        """
        try:
            # Create fresh interfaces
            device_object = bus.get_object(BLUEZ_SERVICE_NAME, device_path)
            device_interface = dbus.Interface(device_object, DEVICE_INTERFACE)
            
            # Try connecting with fresh interfaces
            device_interface.Connect()
            
            # Wait for connection to complete
            time.sleep(2)
            
            return True
        except Exception as e:
            print_and_log(
                f"[-] Interface reset recovery failed: {e}",
                LOG__DEBUG
            )
            return False
    
    def _recover_adapter_reset(self, bus: dbus.Bus, adapter_path: str) -> bool:
        """
        Reset adapter via BlueZ.
        
        Parameters
        ----------
        bus : dbus.Bus
            D-Bus connection
        adapter_path : str
            D-Bus path to the adapter
            
        Returns
        -------
        bool
            True if recovery was successful, False otherwise
        """
        try:
            # Get adapter interface
            adapter_object = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
            adapter_interface = dbus.Interface(adapter_object, ADAPTER_INTERFACE)
            
            # Turn adapter off and on
            print_and_log(
                "[*] Resetting Bluetooth adapter via BlueZ...",
                LOG__USER
            )
            try:
                adapter_interface.SetProperty("Powered", dbus.Boolean(False))
                time.sleep(1)
                adapter_interface.SetProperty("Powered", dbus.Boolean(True))
                time.sleep(2)
            except dbus.exceptions.DBusException as e:
                print_and_log(
                    f"[-] Adapter reset via BlueZ failed: {e}",
                    LOG__DEBUG
                )
                return False
            
            return True
        except Exception as e:
            print_and_log(
                f"[-] Adapter reset recovery failed: {e}",
                LOG__DEBUG
            )
            return False
    
    def _recover_controller_reset(self, adapter_name: str) -> bool:
        """
        Reset controller via hciconfig.
        
        Parameters
        ----------
        adapter_name : str
            Name of the adapter (e.g., 'hci0')
            
        Returns
        -------
        bool
            True if recovery was successful, False otherwise
        """
        try:
            print_and_log(
                f"[*] Resetting Bluetooth controller {adapter_name}...",
                LOG__USER
            )
            
            # Down/up controller using hciconfig (requires root/sudo)
            try:
                subprocess.run(["hciconfig", adapter_name, "down"], check=True, timeout=5)
                time.sleep(1)
                subprocess.run(["hciconfig", adapter_name, "up"], check=True, timeout=5)
                time.sleep(2)
            except subprocess.SubprocessError as e:
                print_and_log(
                    f"[-] Controller reset via hciconfig failed: {e}",
                    LOG__DEBUG
                )
                return False
            
            return True
        except Exception as e:
            print_and_log(
                f"[-] Controller reset recovery failed: {e}",
                LOG__DEBUG
            )
            return False
    
    def _recover_bluetoothd_restart(self) -> bool:
        """
        Restart BlueZ service.
        
        Returns
        -------
        bool
            True if recovery was successful, False otherwise
        """
        try:
            print_and_log(
                "[*] Attempting to restart BlueZ service...",
                LOG__USER
            )
            
            # Try systemctl first
            try:
                subprocess.run(["systemctl", "restart", "bluetooth.service"], check=True, timeout=10)
                time.sleep(3)
                return True
            except subprocess.SubprocessError:
                pass
            
            # Try service command next
            try:
                subprocess.run(["service", "bluetooth", "restart"], check=True, timeout=10)
                time.sleep(3)
                return True
            except subprocess.SubprocessError:
                pass
            
            print_and_log(
                "[-] BlueZ service restart failed: could not find suitable command",
                LOG__DEBUG
            )
            return False
        except Exception as e:
            print_and_log(
                f"[-] BlueZ service restart failed: {e}",
                LOG__DEBUG
            )
            return False
    
    def recover_connection(
        self, device_address: str, bus: dbus.Bus, 
        device_path: str, adapter_path: str, 
        device_interface: Optional[dbus.Interface] = None
    ) -> bool:
        """
        Attempt to recover a connection using staged recovery.
        
        Parameters
        ----------
        device_address : str
            MAC address of the device
        bus : dbus.Bus
            D-Bus connection
        device_path : str
            D-Bus path to the device
        adapter_path : str
            D-Bus path to the adapter
        device_interface : Optional[dbus.Interface]
            D-Bus interface to the device, if available
            
        Returns
        -------
        bool
            True if recovery was successful, False otherwise
        """
        with self._lock:
            # Determine next recovery stage
            stage = self._get_next_recovery_stage(device_address)
            
            # Record this attempt
            self._record_recovery_attempt(device_address, stage)
            
            # Log recovery attempt
            print_and_log(
                f"[*] Attempting connection recovery for {device_address} (stage: {stage.name})",
                LOG__GENERAL
            )
            
            # Notify callbacks
            self._notify_recovery(device_address, stage)
            
            # Extract adapter name from path
            adapter_name = adapter_path.split('/')[-1]
            
            # Execute recovery based on stage
            success = False
            
            if stage == RecoveryStage.DISCONNECT_RECONNECT and device_interface:
                success = self._recover_disconnect_reconnect(device_interface)
            
            elif stage == RecoveryStage.INTERFACE_RESET:
                success = self._recover_interface_reset(bus, device_path)
            
            elif stage == RecoveryStage.ADAPTER_RESET:
                success = self._recover_adapter_reset(bus, adapter_path)
            
            elif stage == RecoveryStage.CONTROLLER_RESET:
                success = self._recover_controller_reset(adapter_name)
            
            elif stage == RecoveryStage.BLUETOOTHD_RESTART:
                success = self._recover_bluetoothd_restart()
            
            # Log result
            status = "successful" if success else "failed"
            print_and_log(
                f"[{'*' if success else '-'}] Connection recovery {status} for {device_address} (stage: {stage.name})",
                LOG__GENERAL
            )
            
            return success


class DeviceStateTracker:
    """
    Tracks device state for recovery purposes.
    
    This class maintains state information about devices to allow restoring
    connections and state after recovery actions.
    """
    
    def __init__(self):
        """Initialize the device state tracker."""
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
    
    def save_state(self, device_address: str, state: Dict[str, Any]) -> None:
        """
        Save device state information.
        
        Parameters
        ----------
        device_address : str
            MAC address of the device
        state : Dict[str, Any]
            State information to save
        """
        with self._lock:
            self._states[device_address] = state.copy()
    
    def get_state(self, device_address: str) -> Optional[Dict[str, Any]]:
        """
        Get saved state for a device.
        
        Parameters
        ----------
        device_address : str
            MAC address of the device
            
        Returns
        -------
        Optional[Dict[str, Any]]
            Saved state information, or None if not found
        """
        with self._lock:
            return self._states.get(device_address)
    
    def update_state(self, device_address: str, **updates) -> None:
        """
        Update specific state fields for a device.
        
        Parameters
        ----------
        device_address : str
            MAC address of the device
        **updates : Any
            Key-value pairs to update in the state
        """
        with self._lock:
            if device_address not in self._states:
                self._states[device_address] = {}
            
            for key, value in updates.items():
                self._states[device_address][key] = value
    
    def clear_state(self, device_address: str) -> None:
        """
        Clear saved state for a device.
        
        Parameters
        ----------
        device_address : str
            MAC address of the device
        """
        with self._lock:
            if device_address in self._states:
                del self._states[device_address]
    
    def snapshot_device_state(self, device: Any) -> Dict[str, Any]:
        """
        Create a snapshot of current device state.
        
        Parameters
        ----------
        device : Any
            Device object with state information
            
        Returns
        -------
        Dict[str, Any]
            Snapshot of device state
        """
        state = {
            'address': device.get_address(),
            'name': device.get_name(),
            'timestamp': time.time(),
        }
        
        # Collect additional state if available
        try:
            state['connected'] = device.is_connected()
        except (AttributeError, Exception):
            pass
        
        try:
            state['services_resolved'] = device.services_resolved()
        except (AttributeError, Exception):
            pass
        
        try:
            state['trusted'] = device.is_trusted()
        except (AttributeError, Exception):
            pass
        
        # Save device type flags if available
        if hasattr(device, 'device_type_flags'):
            state['device_type_flags'] = device.device_type_flags.copy()
        
        return state


# Singleton instances for application-wide use
_reset_manager = ConnectionResetManager()
_state_tracker = DeviceStateTracker()


def get_reset_manager() -> ConnectionResetManager:
    """
    Get the singleton connection reset manager.
    
    Returns
    -------
    ConnectionResetManager
        Singleton reset manager instance
    """
    return _reset_manager


def get_state_tracker() -> DeviceStateTracker:
    """
    Get the singleton device state tracker.
    
    Returns
    -------
    DeviceStateTracker
        Singleton state tracker instance
    """
    return _state_tracker


def recover_connection(
    device_address: str, bus: dbus.Bus, 
    device_path: str, adapter_path: str,
    device_interface: Optional[dbus.Interface] = None
) -> bool:
    """
    Attempt to recover a connection.
    
    Parameters
    ----------
    device_address : str
        MAC address of the device
    bus : dbus.Bus
        D-Bus connection
    device_path : str
        D-Bus path to the device
    adapter_path : str
        D-Bus path to the adapter
    device_interface : Optional[dbus.Interface]
        D-Bus interface to the device, if available
        
    Returns
    -------
    bool
        True if recovery was successful, False otherwise
    """
    return _reset_manager.recover_connection(
        device_address, bus, device_path, adapter_path, device_interface
    )


def save_device_state(device: Any) -> None:
    """
    Save state information for a device.
    
    Parameters
    ----------
    device : Any
        Device object with state information
    """
    state = _state_tracker.snapshot_device_state(device)
    _state_tracker.save_state(device.get_address(), state)


def get_device_state(device_address: str) -> Optional[Dict[str, Any]]:
    """
    Get saved state for a device.
    
    Parameters
    ----------
    device_address : str
        MAC address of the device
        
    Returns
    -------
    Optional[Dict[str, Any]]
        Saved state information, or None if not found
    """
    return _state_tracker.get_state(device_address)


def update_device_state(device_address: str, **updates) -> None:
    """
    Update specific state fields for a device.
    
    Parameters
    ----------
    device_address : str
        MAC address of the device
    **updates : Any
        Key-value pairs to update in the state
    """
    _state_tracker.update_state(device_address, **updates)


def clear_device_state(device_address: str) -> None:
    """
    Clear saved state for a device.
    
    Parameters
    ----------
    device_address : str
        MAC address of the device
    """
    _state_tracker.clear_state(device_address)
