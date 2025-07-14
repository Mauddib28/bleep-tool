from __future__ import annotations

"""bleep.ble_ops.reconnect – Reconnection logic for BLE devices.

This module provides functionality for monitoring connection state and automatically
reconnecting to BLE devices when they disconnect. It implements the reconnection logic
that was present in the monolithic implementation.
"""

import time
import threading
from typing import Dict, Any, Optional, Callable, List, Tuple

import dbus

from bleep.core import errors as _errors
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy as _LEDevice

# Public export list -----------------------------------------------------------------------------
__all__ = [
    "ReconnectionMonitor",
    "reconnect_check",
]


class ReconnectionMonitor:
    """Monitor and automatically reconnect to a BLE device when it disconnects.
    
    This class implements the reconnection logic from the monolithic implementation,
    providing a way to monitor a device's connection state and automatically
    reconnect when it disconnects.
    
    Parameters
    ----------
    device : _LEDevice
        The BLE device to monitor
    max_attempts : int, optional
        Maximum number of reconnection attempts, by default 5
    backoff_factor : float, optional
        Factor to multiply the delay by after each attempt, by default 1.5
    initial_delay : float, optional
        Initial delay in seconds before first reconnection attempt, by default 1.0
    callback : Callable[[bool, str], None], optional
        Callback function to call with reconnection status and message
    """
    
    def __init__(
        self,
        device: _LEDevice,
        max_attempts: int = 5,
        backoff_factor: float = 1.5,
        initial_delay: float = 1.0,
        callback: Optional[Callable[[bool, str], None]] = None,
    ):
        self.device = device
        self.max_attempts = max_attempts
        self.backoff_factor = backoff_factor
        self.initial_delay = initial_delay
        self.callback = callback
        
        self._monitoring = False
        self._monitor_thread = None
        self._stop_event = threading.Event()
        
        # Connection statistics
        self.reconnection_attempts = 0
        self.successful_reconnections = 0
        self.last_disconnect_time = 0.0
        self.last_reconnect_time = 0.0
        self.connection_history: List[Tuple[float, str]] = []  # (timestamp, event)
    
    def start_monitoring(self):
        """Start monitoring the device's connection state."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_connection,
            daemon=True,
            name=f"ReconnectMonitor-{self.device.mac_address}"
        )
        self._monitor_thread.start()
        print_and_log(
            f"[+] Started reconnection monitoring for {self.device.mac_address}",
            LOG__DEBUG
        )
    
    def stop_monitoring(self):
        """Stop monitoring the device's connection state."""
        if not self._monitoring:
            return
        
        self._monitoring = False
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
        print_and_log(
            f"[+] Stopped reconnection monitoring for {self.device.mac_address}",
            LOG__DEBUG
        )
    
    def _monitor_connection(self):
        """Monitor the device's connection state and reconnect when disconnected."""
        while self._monitoring and not self._stop_event.is_set():
            try:
                if not self.device.is_connected():
                    self._handle_disconnect()
                time.sleep(1.0)  # Check connection state every second
            except Exception as e:
                print_and_log(
                    f"[-] Error in reconnection monitor: {str(e)}",
                    LOG__DEBUG
                )
                time.sleep(2.0)  # Wait longer on error
    
    def _handle_disconnect(self):
        """Handle device disconnection by attempting to reconnect."""
        now = time.time()
        self.last_disconnect_time = now
        self.connection_history.append((now, "disconnected"))
        
        print_and_log(
            f"[*] Device {self.device.mac_address} disconnected, attempting reconnection",
            LOG__GENERAL
        )
        
        # Reset reconnection attempts if it's been a while since the last attempt
        if self.last_reconnect_time > 0 and (now - self.last_reconnect_time) > 60:
            self.reconnection_attempts = 0
        
        # Attempt reconnection with exponential backoff
        attempt = 0
        while attempt < self.max_attempts and not self._stop_event.is_set():
            attempt += 1
            self.reconnection_attempts += 1
            
            delay = self.initial_delay * (self.backoff_factor ** (attempt - 1))
            print_and_log(
                f"[*] Reconnection attempt {attempt}/{self.max_attempts} "
                f"for {self.device.mac_address} (delay: {delay:.1f}s)",
                LOG__DEBUG
            )
            
            # Wait before attempting reconnection
            time.sleep(delay)
            
            try:
                # Attempt to reconnect
                if self.device.connect(retry=3):
                    self.last_reconnect_time = time.time()
                    self.successful_reconnections += 1
                    self.connection_history.append((time.time(), "reconnected"))
                    
                    print_and_log(
                        f"[+] Successfully reconnected to {self.device.mac_address}",
                        LOG__GENERAL
                    )
                    
                    # Wait for services to be resolved
                    services_resolved = False
                    for _ in range(10):  # Wait up to 5 seconds
                        if self.device.is_services_resolved():
                            services_resolved = True
                            break
                        time.sleep(0.5)
                    
                    if services_resolved:
                        print_and_log(
                            f"[+] Services resolved for {self.device.mac_address}",
                            LOG__DEBUG
                        )
                    else:
                        # Attempt explicit refresh if services not yet resolved
                        print_and_log(
                            f"[*] Forcing service re-resolution for {self.device.mac_address}",
                            LOG__DEBUG,
                        )
                        try:
                            if self.device.force_service_resolution(timeout=10):
                                print_and_log(
                                    f"[+] Services resolved after explicit refresh",
                                    LOG__GENERAL,
                                )
                            else:
                                print_and_log(
                                    f"[-] Service refresh timed-out",
                                    LOG__DEBUG,
                                )
                        except Exception as e:
                            print_and_log(
                                f"[-] Service refresh failed: {e}",
                                LOG__DEBUG,
                            )
                    
                    # Call the callback with success
                    if self.callback:
                        self.callback(True, "Reconnection successful")
                    
                    return True
            except dbus.exceptions.DBusException as e:
                error = _errors.map_dbus_error(e)
                print_and_log(
                    f"[-] Reconnection attempt {attempt} failed: {str(error)}",
                    LOG__DEBUG
                )
        
        # All reconnection attempts failed
        print_and_log(
            f"[-] Failed to reconnect to {self.device.mac_address} "
            f"after {self.max_attempts} attempts",
            LOG__GENERAL
        )
        
        # Call the callback with failure
        if self.callback:
            self.callback(False, f"Failed to reconnect after {self.max_attempts} attempts")
        
        return False
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary containing connection statistics
        """
        return {
            "device_address": self.device.mac_address,
            "reconnection_attempts": self.reconnection_attempts,
            "successful_reconnections": self.successful_reconnections,
            "last_disconnect_time": self.last_disconnect_time,
            "last_reconnect_time": self.last_reconnect_time,
            "connection_history": self.connection_history,
            "is_connected": self.device.is_connected(),
            "is_services_resolved": self.device.is_services_resolved(),
        }


def reconnect_check(
    device: _LEDevice,
    max_attempts: int = 5,
    callback: Optional[Callable[[bool, str], None]] = None,
) -> bool:
    """Check if device is connected and attempt to reconnect if not.
    
    This function implements the Reconnect_Check() functionality from the
    monolithic implementation.
    
    Parameters
    ----------
    device : _LEDevice
        The BLE device to check and reconnect
    max_attempts : int, optional
        Maximum number of reconnection attempts, by default 5
    callback : Callable[[bool, str], None], optional
        Callback function to call with reconnection status and message
        
    Returns
    -------
    bool
        True if device is connected or was successfully reconnected,
        False otherwise
    """
    if device.is_connected():
        return True
    
    print_and_log(
        f"[*] Device {device.mac_address} not connected, attempting reconnection",
        LOG__GENERAL
    )
    
    # Create a temporary monitor for reconnection
    monitor = ReconnectionMonitor(
        device,
        max_attempts=max_attempts,
        callback=callback,
    )
    
    # Attempt reconnection
    return monitor._handle_disconnect()
