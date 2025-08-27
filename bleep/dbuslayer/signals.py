"""BlueZ signal helper abstractions.

Phase-4 temporary shim: re-export the legacy `system_dbus__bluez_signals` class
from the historical implementation inside `pybluez_dbus__now_with_classes.py`.
This keeps existing code importing `bleep.dbuslayer.signals` working while the
class is gradually extracted into smaller, testable components.
"""

#!/usr/bin/python3

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

from bleep.bt_ref.constants import (
    DBUS_PROPERTIES,
    GATT_CHARACTERISTIC_INTERFACE,
    DBUS_OM_IFACE,
    DEVICE_INTERFACE,
)
from bleep.core.log import print_and_log, LOG__DEBUG


@dataclass
class SignalCapture:
    """Container for captured signal information."""
    interface: str
    path: str
    signal_name: str
    args: Tuple[Any, ...]
    timestamp: float
    source: str = ""  # 'read', 'write', 'notification', 'property_change', etc.


class SignalCorrelator:
    """Correlates related signals from different sources."""
    
    def __init__(self):
        """Initialize the correlator."""
        self._captures: List[SignalCapture] = []
        self._lock = threading.Lock()
        
    def add_capture(self, capture: SignalCapture) -> None:
        """Add a signal capture to the correlation pool."""
        with self._lock:
            self._captures.append(capture)
            # Trim old captures (older than 30 seconds)
            now = time.time()
            self._captures = [c for c in self._captures if now - c.timestamp < 30]
    
    def get_related(self, capture: SignalCapture, 
                    time_window: float = 1.0) -> List[SignalCapture]:
        """Get captures related to the given capture within a time window."""
        with self._lock:
            related = []
            for c in self._captures:
                # Skip the input capture itself
                if c is capture:
                    continue
                    
                # Check if it's within the time window
                if abs(c.timestamp - capture.timestamp) <= time_window:
                    # Path-based relationship (same device/service/characteristic)
                    if c.path.startswith(capture.path) or capture.path.startswith(c.path):
                        related.append(c)
                        
            return related
    
    def clear(self) -> None:
        """Clear all captures."""
        with self._lock:
            self._captures.clear()


class PropertyMonitor:
    """Monitors specific D-Bus properties for changes."""
    
    def __init__(self):
        """Initialize the property monitor."""
        self._property_watchers: Dict[str, Dict[str, Set[Callable]]] = {}
        self._property_history: Dict[str, Dict[str, List[Tuple[float, Any]]]] = {}
        self._lock = threading.Lock()
    
    def watch_property(self, path: str, property_name: str, callback: Callable) -> None:
        """Add a callback for a specific property on a specific path."""
        with self._lock:
            if path not in self._property_watchers:
                self._property_watchers[path] = {}
                self._property_history[path] = {}
                
            if property_name not in self._property_watchers[path]:
                self._property_watchers[path][property_name] = set()
                self._property_history[path][property_name] = []
                
            self._property_watchers[path][property_name].add(callback)
    
    def unwatch_property(self, path: str, property_name: str, callback: Callable) -> None:
        """Remove a callback for a specific property."""
        with self._lock:
            if (path in self._property_watchers and 
                property_name in self._property_watchers[path]):
                self._property_watchers[path][property_name].discard(callback)
                
                # Clean up if no watchers remain
                if not self._property_watchers[path][property_name]:
                    del self._property_watchers[path][property_name]
                    
                if not self._property_watchers[path]:
                    del self._property_watchers[path]
                    
    def property_changed(self, path: str, interface: str, 
                         property_name: str, value: Any) -> None:
        """Handle a property change event."""
        with self._lock:
            now = time.time()
            
            # Record in history
            if path in self._property_history and property_name in self._property_history[path]:
                self._property_history[path][property_name].append((now, value))
                # Keep only the last 10 values
                if len(self._property_history[path][property_name]) > 10:
                    self._property_history[path][property_name].pop(0)
            
            # Notify watchers
            if path in self._property_watchers and property_name in self._property_watchers[path]:
                for callback in self._property_watchers[path][property_name]:
                    try:
                        callback(path, interface, property_name, value)
                    except Exception as e:
                        print_and_log(f"[ERROR] Property watcher callback error: {e}", LOG__DEBUG)
    
    def get_property_history(self, path: str, property_name: str) -> List[Tuple[float, Any]]:
        """Get the history of values for a property."""
        with self._lock:
            if path in self._property_history and property_name in self._property_history[path]:
                return self._property_history[path][property_name].copy()
            return []


class system_dbus__bluez_signals:  # noqa: N801 – keep legacy-friendly name
    """Centralised BlueZ signal manager.

    Replaces the ad-hoc listeners in the monolith. Handles property changes,
    notifications, and other signal events for BlueZ devices.
    """

    def __init__(self):
        """Initialize the signals manager."""
        self.bus = dbus.SystemBus()
        self._matches: list[dbus.connection.SignalMatch] = []
        # Map device-path prefix -> device instance
        self._devices: dict[str, object] = {}
        
        # Enhanced signal handling components
        self._signal_correlator = SignalCorrelator()
        self._property_monitor = PropertyMonitor()
        
        # Notification tracking
        self._notification_callbacks: Dict[str, List[Callable]] = {}  # path -> callbacks
        self._read_triggers: Dict[str, List[Callable]] = {}  # path -> callbacks
        self._write_triggers: Dict[str, List[Callable]] = {}  # path -> callbacks
        
        # Timer handling
        self._mainloop = None
        self._timer_ids: List[int] = []
        
        # Thread safety
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def register_device(self, device):
        """Register *system_dbus__bluez_device__low_energy* instance for callbacks."""
        self._devices[device._device_path] = device  # type: ignore[attr-defined]
        if not self._matches:
            self._attach_bus_listeners()

    def unregister_device(self, device):
        """Unregister a device from signal handling."""
        self._devices.pop(device._device_path, None)  # type: ignore[attr-defined]
        if not self._devices:
            self._detach_bus_listeners()

    def ensure_listening(self):  # called by device_manager.run()
        """Attach D-Bus signal receivers if they are not already active."""
        if not self._matches:
            self._attach_bus_listeners()
    
    def register_notification_callback(self, char_path: str, callback: Callable) -> None:
        """Register a callback for notifications from a specific characteristic.
        
        Parameters
        ----------
        char_path
            The D-Bus path of the characteristic
        callback
            A function that will be called with (path, value) when a notification is received
        """
        with self._lock:
            if char_path not in self._notification_callbacks:
                self._notification_callbacks[char_path] = []
            self._notification_callbacks[char_path].append(callback)
    
    def unregister_notification_callback(self, char_path: str, callback: Callable) -> None:
        """Remove a notification callback for a characteristic.
        
        Parameters
        ----------
        char_path
            The D-Bus path of the characteristic
        callback
            The callback function to remove
        """
        with self._lock:
            if char_path in self._notification_callbacks:
                try:
                    self._notification_callbacks[char_path].remove(callback)
                except ValueError:
                    pass
                if not self._notification_callbacks[char_path]:
                    del self._notification_callbacks[char_path]
    
    def register_read_trigger(self, char_path: str, callback: Callable) -> None:
        """Register a callback to be called when a characteristic is read.
        
        Parameters
        ----------
        char_path
            The D-Bus path of the characteristic
        callback
            A function that will be called with (path, value) when the characteristic is read
        """
        with self._lock:
            if char_path not in self._read_triggers:
                self._read_triggers[char_path] = []
            self._read_triggers[char_path].append(callback)
    
    def register_write_trigger(self, char_path: str, callback: Callable) -> None:
        """Register a callback to be called when a characteristic is written to.
        
        Parameters
        ----------
        char_path
            The D-Bus path of the characteristic
        callback
            A function that will be called with (path, value) when the characteristic is written to
        """
        with self._lock:
            if char_path not in self._write_triggers:
                self._write_triggers[char_path] = []
            self._write_triggers[char_path].append(callback)
    
    def watch_property(self, path: str, property_name: str, callback: Callable) -> None:
        """Watch for changes to a specific property.
        
        Parameters
        ----------
        path
            The D-Bus path of the object
        property_name
            The name of the property to watch
        callback
            A function that will be called with (path, interface, property_name, value) 
            when the property changes
        """
        self._property_monitor.watch_property(path, property_name, callback)
    
    def unwatch_property(self, path: str, property_name: str, callback: Callable) -> None:
        """Stop watching a property.
        
        Parameters
        ----------
        path
            The D-Bus path of the object
        property_name
            The name of the property to stop watching
        callback
            The callback function to remove
        """
        self._property_monitor.unwatch_property(path, property_name, callback)
    
    def get_property_history(self, path: str, property_name: str) -> List[Tuple[float, Any]]:
        """Get the history of values for a property.
        
        Parameters
        ----------
        path
            The D-Bus path of the object
        property_name
            The name of the property
            
        Returns
        -------
        list
            List of (timestamp, value) tuples for the property
        """
        return self._property_monitor.get_property_history(path, property_name)
    
    def get_related_signals(self, capture: SignalCapture, 
                           time_window: float = 1.0) -> List[SignalCapture]:
        """Get signals related to the given capture.
        
        Parameters
        ----------
        capture
            The signal capture to find related signals for
        time_window
            Time window in seconds for correlation
            
        Returns
        -------
        list
            List of related signal captures
        """
        return self._signal_correlator.get_related(capture, time_window)
    
    def start_timed_capture(self, timeout_ms: int = 5000, 
                           callback: Optional[Callable] = None) -> None:
        """Start a timed signal capture.
        
        Parameters
        ----------
        timeout_ms
            Duration in milliseconds to capture signals
        callback
            Optional callback to call when the capture is complete
        """
        # Set up mainloop if needed
        if self._mainloop is None:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._mainloop = GLib.MainLoop()
        
        # Create timer callback
        def timer_callback():
            if callback:
                try:
                    callback()
                except Exception as e:
                    print_and_log(f"[ERROR] Signal capture callback error: {e}", LOG__DEBUG)
            
            # Don't quit mainloop if other timers are active
            if not self._timer_ids or len(self._timer_ids) <= 1:
                if self._mainloop and self._mainloop.is_running():
                    self._mainloop.quit()
            
            # Remove this timer ID
            with self._lock:
                if timer_id in self._timer_ids:
                    self._timer_ids.remove(timer_id)
            return False  # Don't repeat
        
        # Add timer
        timer_id = GLib.timeout_add(timeout_ms, timer_callback)
        with self._lock:
            self._timer_ids.append(timer_id)
        
        # Start mainloop if not already running
        if not self._mainloop.is_running():
            self._mainloop.run()
    
    def clear_all_timers(self) -> None:
        """Clear all active timers."""
        with self._lock:
            for timer_id in self._timer_ids:
                GLib.source_remove(timer_id)
            self._timer_ids.clear()
            
            # Quit mainloop if running
            if self._mainloop and self._mainloop.is_running():
                self._mainloop.quit()
                
    def capture_and_act__emittion__gatt_characteristic(self, device, characteristic_uuid, callback):
        """Legacy method for capturing notifications from a characteristic.
        
        This method sets up notification capture for a characteristic and calls the provided
        callback when notifications are received. It's provided for backward compatibility
        with the legacy monolith implementation.
        
        Parameters
        ----------
        device
            The device object containing the characteristic
        characteristic_uuid
            The UUID of the characteristic to monitor
        callback
            Function to call when notifications are received
        """
        print_and_log("[*] Setting up notification capture for characteristic", LOG__DEBUG)
        
        # Find the characteristic path
        char_path = None
        for svc in getattr(device, "_services", []):
            for char in getattr(svc, "characteristics", []):
                if getattr(char, "uuid", "").lower() == characteristic_uuid.lower():
                    char_path = getattr(char, "path", None)
                    break
            if char_path:
                break
                
        if not char_path:
            print_and_log(f"[-] Characteristic not found: {characteristic_uuid}", LOG__DEBUG)
            return
            
        # Register the callback
        self.register_notification_callback(char_path, callback)
        
        # Start notifications if not already started
        try:
            # Get the characteristic object
            char_obj = self.bus.get_object("org.bluez", char_path)
            char_iface = dbus.Interface(char_obj, GATT_CHARACTERISTIC_INTERFACE)
            
            # Start notifications
            char_iface.StartNotify()
            print_and_log(f"[+] Started notifications for {characteristic_uuid}", LOG__DEBUG)
        except Exception as e:
            print_and_log(f"[-] Failed to start notifications: {e}", LOG__DEBUG)

    # ------------------------------------------------------------------
    # D-Bus wiring
    # ------------------------------------------------------------------
    def _attach_bus_listeners(self):
        print_and_log("[DEBUG] Signals manager attaching bus listeners", LOG__DEBUG)
        # PropertiesChanged on GattCharacteristic1 – notification routing
        match_pc = self.bus.add_signal_receiver(
            self._properties_changed,
            dbus_interface=DBUS_PROPERTIES,
            signal_name="PropertiesChanged",
            path_keyword="path",
        )
        # InterfacesAdded/Removed on the ObjectManager – device/service lifecycle
        match_added = self.bus.add_signal_receiver(
            self._interfaces_added,
            dbus_interface=DBUS_OM_IFACE,
            signal_name="InterfacesAdded",
        )
        match_removed = self.bus.add_signal_receiver(
            self._interfaces_removed,
            dbus_interface=DBUS_OM_IFACE,
            signal_name="InterfacesRemoved",
        )
        self._matches.extend([match_pc, match_added, match_removed])

    def _detach_bus_listeners(self):
        for m in self._matches:
            try:
                m.remove()
            except Exception:
                pass
        self._matches.clear()
        self._signal_correlator.clear()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _properties_changed(
        self, interface, changed, invalidated, path: str | None = None
    ):
        """Handle properties changed signal.
        
        Processes notifications from characteristics and general property changes.
        """
        if path is None:
            return
            
        # Record this signal for correlation
        args = (interface, changed, invalidated)
        capture = SignalCapture(
            interface=interface,
            path=path,
            signal_name="PropertiesChanged",
            args=args,
            timestamp=time.time()
        )
        self._signal_correlator.add_capture(capture)
            
        # Process property changes for all properties
        for prop_name, value in changed.items():
            self._property_monitor.property_changed(path, interface, prop_name, value)
            
        # Handle GATT characteristic notifications specifically
        if interface == GATT_CHARACTERISTIC_INTERFACE and "Value" in changed:
            value = bytes(changed["Value"])
            source = "notification"
            capture.source = source
            
            # Process notification callbacks specific to this characteristic
            with self._lock:
                callbacks = self._notification_callbacks.get(path, [])
                for callback in callbacks:
                    try:
                        callback(path, value)
                    except Exception as e:
                        print_and_log(f"[ERROR] Notification callback error: {e}", LOG__DEBUG)
            
            # Find owning device (device path is prefix of characteristic path)
            for dev_path, device in self._devices.items():
                if not path.startswith(dev_path):
                    continue
                try:
                    # Navigate to characteristic instance
                    for svc in device._services:  # type: ignore[attr-defined]
                        for char in svc.characteristics:
                            if char.path == path:
                                char_value = value  # noqa: F841 – local alias for clarity
                                # Notify device & characteristic
                                if hasattr(device, "characteristic_value_updated"):
                                    device.characteristic_value_updated(char, value)  # type: ignore[attr-defined]
                                return
                except AttributeError:
                    # Device not fully initialised – ignore
                    return

    # ------------------------------------------------------------------
    # Callbacks – ObjectManager
    # ------------------------------------------------------------------
    def _interfaces_added(self, object_path: str, interfaces: dict):  # noqa: D401
        """Handle InterfaceAdded events from BlueZ.

        We are primarily interested in new GATT services/characteristics that
        belong to devices currently under management.  The event is forwarded
        to the owning *device* instance when applicable so it can refresh its
        internal caches.
        """
        # Record this signal for correlation
        capture = SignalCapture(
            interface=DBUS_OM_IFACE,
            path=object_path,
            signal_name="InterfacesAdded",
            args=(interfaces,),
            timestamp=time.time()
        )
        self._signal_correlator.add_capture(capture)
        
        # Fast-path: check device registry by prefix match
        for dev_path, device in self._devices.items():
            if not object_path.startswith(dev_path):
                continue
            if hasattr(device, "interfaces_added"):
                try:
                    device.interfaces_added(object_path, interfaces)  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001 – device code decides
                    pass
            return  # there can be only one owning device

    def _interfaces_removed(self, object_path: str, interfaces: list[str]):  # noqa: D401
        """Handle InterfaceRemoved events from BlueZ."""
        # Record this signal for correlation
        capture = SignalCapture(
            interface=DBUS_OM_IFACE,
            path=object_path,
            signal_name="InterfacesRemoved",
            args=(interfaces,),
            timestamp=time.time()
        )
        self._signal_correlator.add_capture(capture)
        
        for dev_path, device in self._devices.items():
            if not object_path.startswith(dev_path):
                continue
            if hasattr(device, "interfaces_removed"):
                try:
                    device.interfaces_removed(object_path, interfaces)  # type: ignore[attr-defined]
                except Exception:
                    pass
            return
    
    def handle_read_event(self, char_path: str, value: bytes) -> None:
        """Handle a characteristic read event.
        
        This should be called by characteristic read methods to trigger read callbacks.
        
        Parameters
        ----------
        char_path
            The D-Bus path of the characteristic
        value
            The value that was read
        """
        # Record signal for correlation
        capture = SignalCapture(
            interface=GATT_CHARACTERISTIC_INTERFACE,
            path=char_path,
            signal_name="ValueRead",
            args=(value,),
            timestamp=time.time(),
            source="read"
        )
        self._signal_correlator.add_capture(capture)
        
        # Process read callbacks
        with self._lock:
            callbacks = self._read_triggers.get(char_path, [])
            for callback in callbacks:
                try:
                    callback(char_path, value)
                except Exception as e:
                    print_and_log(f"[ERROR] Read callback error: {e}", LOG__DEBUG)
    
    def handle_write_event(self, char_path: str, value: bytes) -> None:
        """Handle a characteristic write event.
        
        This should be called by characteristic write methods to trigger write callbacks.
        
        Parameters
        ----------
        char_path
            The D-Bus path of the characteristic
        value
            The value that was written
        """
        # Record signal for correlation
        capture = SignalCapture(
            interface=GATT_CHARACTERISTIC_INTERFACE,
            path=char_path,
            signal_name="ValueWritten",
            args=(value,),
            timestamp=time.time(),
            source="write"
        )
        self._signal_correlator.add_capture(capture)
        
        # Process write callbacks
        with self._lock:
            callbacks = self._write_triggers.get(char_path, [])
            for callback in callbacks:
                try:
                    callback(char_path, value)
                except Exception as e:
                    print_and_log(f"[ERROR] Write callback error: {e}", LOG__DEBUG)


__all__ = ["system_dbus__bluez_signals"]

# ----------------------------------------------------------------------
# Back-compat shim: If legacy class exists, expose as LegacySignals so old
# imports keep working during migration.
# ----------------------------------------------------------------------

# Legacy monolith class is no longer needed; keep *LegacySignals* alias for
# import-compatibility but point it at the new implementation.

LegacySignals = system_dbus__bluez_signals  # type: ignore  # noqa: N801

__all__.append("LegacySignals")
