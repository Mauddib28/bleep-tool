"""
BlueZ Service Monitor

This module provides monitoring capabilities for BlueZ D-Bus services to detect
unresponsive services and service restarts. It implements a heartbeat mechanism
to continuously check BlueZ service health.

Based on best practices from BlueZ monitor-bluetooth script.
"""

import threading
import time
from typing import Dict, List, Set, Optional, Callable, Any, Union

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    BLUEZ_NAMESPACE,
    DBUS_OM_IFACE,
)
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL

# Initialize GLib mainloop for async operations if not already done
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Type alias for callback functions
MonitorCallback = Callable[[], None]


class BlueZServiceMonitor:
    """
    Monitors BlueZ D-Bus service for availability and responsiveness.
    
    This class implements a heartbeat mechanism to detect when BlueZ becomes
    unresponsive or when the service restarts.
    """
    
    def __init__(self, check_interval: float = 5.0):
        """
        Initialize the BlueZ service monitor.
        
        Parameters
        ----------
        check_interval : float
            Interval in seconds between service health checks
        """
        self._bus = dbus.SystemBus()
        self._check_interval = check_interval
        
        # Callbacks for different events
        self._stall_callbacks: List[MonitorCallback] = []
        self._restart_callbacks: List[MonitorCallback] = []
        self._availability_callbacks: Dict[bool, List[MonitorCallback]] = {
            True: [],   # Available callbacks
            False: [],  # Unavailable callbacks
        }
        
        # Monitor state
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._last_successful_check = 0.0
        self._service_available = False
        self._name_owner_watch = None
        
        # Set up name owner changed signal
        self._setup_name_owner_watch()
    
    def _setup_name_owner_watch(self) -> None:
        """Set up signal watch for BlueZ service name owner changes."""
        def name_owner_changed(name: str, old_owner: str, new_owner: str) -> None:
            """Called when BlueZ service ownership changes (restart/stop)."""
            if name == BLUEZ_SERVICE_NAME:
                was_available = bool(old_owner)
                is_available = bool(new_owner)
                
                # Service restart detection
                if was_available and is_available and old_owner != new_owner:
                    print_and_log(
                        f"[*] BlueZ service restarted (owner changed: {old_owner} -> {new_owner})",
                        LOG__GENERAL
                    )
                    self._trigger_restart_callbacks()
                
                # Service availability change
                if was_available != is_available:
                    self._service_available = is_available
                    status_str = "available" if is_available else "unavailable"
                    print_and_log(
                        f"[{'*' if is_available else '!'} BlueZ service is now {status_str}",
                        LOG__GENERAL
                    )
                    self._trigger_availability_callbacks(is_available)
        
        # Watch for name owner changes
        self._bus.add_signal_receiver(
            name_owner_changed,
            signal_name="NameOwnerChanged",
            dbus_interface="org.freedesktop.DBus",
            arg0=BLUEZ_SERVICE_NAME
        )
        
        # Check current service availability
        try:
            owner = self._bus.get_name_owner(BLUEZ_SERVICE_NAME)
            self._service_available = bool(owner)
        except dbus.exceptions.DBusException:
            self._service_available = False
    
    def _trigger_stall_callbacks(self) -> None:
        """Trigger all registered stall callbacks."""
        for callback in self._stall_callbacks:
            try:
                callback()
            except Exception as e:
                print_and_log(
                    f"[-] Error in stall callback: {e}",
                    LOG__DEBUG
                )
    
    def _trigger_restart_callbacks(self) -> None:
        """Trigger all registered restart callbacks."""
        for callback in self._restart_callbacks:
            try:
                callback()
            except Exception as e:
                print_and_log(
                    f"[-] Error in restart callback: {e}",
                    LOG__DEBUG
                )
    
    def _trigger_availability_callbacks(self, available: bool) -> None:
        """Trigger all registered availability callbacks."""
        for callback in self._availability_callbacks[available]:
            try:
                callback()
            except Exception as e:
                print_and_log(
                    f"[-] Error in availability callback: {e}",
                    LOG__DEBUG
                )
    
    def _check_service_health(self) -> bool:
        """
        Check if BlueZ service is responsive.
        
        Returns
        -------
        bool
            True if service is healthy, False otherwise
        """
        if not self._service_available:
            return False
        
        try:
            # Get a fresh connection to the Object Manager
            obj = self._bus.get_object(BLUEZ_SERVICE_NAME, "/")
            mgr = dbus.Interface(obj, DBUS_OM_IFACE)
            
            # Time the GetManagedObjects call
            start_time = time.time()
            mgr.GetManagedObjects()
            elapsed = time.time() - start_time
            
            # Log the elapsed time for performance monitoring
            print_and_log(
                f"[DEBUG] BlueZ health check: {elapsed:.3f}s",
                LOG__DEBUG
            )
            
            # Update last successful check time
            self._last_successful_check = time.time()
            return True
            
        except dbus.exceptions.DBusException as e:
            print_and_log(
                f"[-] BlueZ service health check failed: {e}",
                LOG__DEBUG
            )
            return False
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop that checks BlueZ service health."""
        last_stall_notification = 0.0
        stall_notification_interval = 60.0  # Only notify about stalls once per minute
        
        while self._monitoring:
            try:
                # Check service health
                healthy = self._check_service_health()
                
                # Detect service stalls
                if self._service_available and not healthy:
                    current_time = time.time()
                    
                    # Only trigger stall callbacks if we haven't notified recently
                    if current_time - last_stall_notification > stall_notification_interval:
                        print_and_log(
                            "[!] BlueZ service appears to be stalled",
                            LOG__GENERAL
                        )
                        self._trigger_stall_callbacks()
                        last_stall_notification = current_time
                
            except Exception as e:
                print_and_log(
                    f"[-] Error in BlueZ monitor loop: {e}",
                    LOG__DEBUG
                )
            
            # Sleep until next check
            time.sleep(self._check_interval)
    
    def start_monitoring(self) -> None:
        """Start monitoring BlueZ service health."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        print_and_log(
            "[*] BlueZ service monitoring started",
            LOG__DEBUG
        )
    
    def stop_monitoring(self) -> None:
        """Stop monitoring BlueZ service health."""
        if not self._monitoring:
            return
        
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
            self._monitor_thread = None
        
        print_and_log(
            "[*] BlueZ service monitoring stopped",
            LOG__DEBUG
        )
    
    def register_stall_callback(self, callback: MonitorCallback) -> None:
        """
        Register a callback to be called when BlueZ service stalls.
        
        Parameters
        ----------
        callback : Callable[[], None]
            Function to call when service stalls
        """
        if callback not in self._stall_callbacks:
            self._stall_callbacks.append(callback)
    
    def register_restart_callback(self, callback: MonitorCallback) -> None:
        """
        Register a callback to be called when BlueZ service restarts.
        
        Parameters
        ----------
        callback : Callable[[], None]
            Function to call when service restarts
        """
        if callback not in self._restart_callbacks:
            self._restart_callbacks.append(callback)
    
    def register_availability_callback(self, callback: MonitorCallback, available: bool) -> None:
        """
        Register a callback to be called when BlueZ service availability changes.
        
        Parameters
        ----------
        callback : Callable[[], None]
            Function to call when service availability changes
        available : bool
            Whether to call when service becomes available (True) or unavailable (False)
        """
        if callback not in self._availability_callbacks[available]:
            self._availability_callbacks[available].append(callback)
    
    def unregister_callback(self, callback: MonitorCallback) -> None:
        """
        Unregister a callback from all events.
        
        Parameters
        ----------
        callback : Callable[[], None]
            Callback to unregister
        """
        if callback in self._stall_callbacks:
            self._stall_callbacks.remove(callback)
        
        if callback in self._restart_callbacks:
            self._restart_callbacks.remove(callback)
        
        for available in [True, False]:
            if callback in self._availability_callbacks[available]:
                self._availability_callbacks[available].remove(callback)
    
    def is_service_available(self) -> bool:
        """
        Check if BlueZ service is currently available.
        
        Returns
        -------
        bool
            True if service is available, False otherwise
        """
        return self._service_available
    
    def get_last_successful_check_time(self) -> float:
        """
        Get timestamp of last successful health check.
        
        Returns
        -------
        float
            Timestamp of last successful check, or 0.0 if never checked
        """
        return self._last_successful_check


# Singleton instance for application-wide use
_monitor = BlueZServiceMonitor()


def get_monitor() -> BlueZServiceMonitor:
    """
    Get the singleton BlueZ monitor instance.
    
    Returns
    -------
    BlueZServiceMonitor
        Singleton monitor instance
    """
    return _monitor


def start_monitoring() -> None:
    """Start BlueZ service monitoring."""
    _monitor.start_monitoring()


def stop_monitoring() -> None:
    """Stop BlueZ service monitoring."""
    _monitor.stop_monitoring()


def is_bluez_available() -> bool:
    """
    Check if BlueZ service is currently available.
    
    Returns
    -------
    bool
        True if service is available, False otherwise
    """
    return _monitor.is_service_available()


def register_stall_callback(callback: MonitorCallback) -> None:
    """
    Register a callback to be called when BlueZ service stalls.
    
    Parameters
    ----------
    callback : Callable[[], None]
        Function to call when service stalls
    """
    _monitor.register_stall_callback(callback)


def register_restart_callback(callback: MonitorCallback) -> None:
    """
    Register a callback to be called when BlueZ service restarts.
    
    Parameters
    ----------
    callback : Callable[[], None]
        Function to call when service restarts
    """
    _monitor.register_restart_callback(callback)
