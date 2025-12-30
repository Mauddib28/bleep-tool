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
import dbus.lowlevel
import dbus.mainloop.glib
from gi.repository import GLib

from bleep.bt_ref.constants import (
    DBUS_PROPERTIES,
    GATT_CHARACTERISTIC_INTERFACE,
    DBUS_OM_IFACE,
    DEVICE_INTERFACE,
    AGENT_INTERFACE,
    MANAGER_INTERFACE,
)
from bleep.core.constants import (
    DBUS_MESSAGE_SIGNAL,
    DBUS_MESSAGE_METHOD_CALL,
    DBUS_MESSAGE_METHOD_RETURN,
    DBUS_MESSAGE_ERROR,
)
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__AGENT


@dataclass
class SignalCapture:
    """Container for captured signal information.
    
    **DEPRECATED**: Use `DBusEventCapture` for new code. This class is retained
    for backward compatibility with existing signal correlation code.
    """
    interface: str
    path: str
    signal_name: str
    args: Tuple[Any, ...]
    timestamp: float
    source: str = ""  # 'read', 'write', 'notification', 'property_change', etc.


@dataclass
class MethodCallCapture:
    """Container for captured D-Bus method call information.
    
    **DEPRECATED**: Use `DBusEventCapture` for new code. This class is retained
    for backward compatibility.
    
    Preserves original message details for detailed analysis while providing
    structured access to method call information.
    """
    interface: str
    path: str
    method_name: str
    args: Tuple[Any, ...]
    timestamp: float
    sender: str = ""
    destination: str = ""
    serial: int = 0
    signature: str = ""
    # Preserve original message for detailed analysis
    original_message: Optional[Any] = None  # dbus.lowlevel.Message, but using Any for compatibility


@dataclass
class DBusEventCapture:
    """Unified container for all D-Bus event types.
    
    Represents signals, method calls, method returns, and errors in a single
    structure that enables correlation across all event types. This is the
    preferred structure for new code.
    
    Parameters
    ----------
    event_type : str
        Type of event: 'signal', 'method_call', 'method_return', 'error'
    interface : str
        D-Bus interface name
    path : str
        D-Bus object path
    timestamp : float
        Event timestamp
    sender : str
        D-Bus sender name
    destination : str
        D-Bus destination name
    serial : int
        D-Bus message serial number
    reply_serial : int, optional
        Reply serial for method returns/errors (links to original method call)
    signal_name : str, optional
        Signal name (for signal events)
    method_name : str, optional
        Method name (for method call/return events)
    error_name : str, optional
        Error name (for error events)
    error_message : str, optional
        Error message (for error events)
    args : Tuple[Any, ...]
        Message arguments
    signature : str
        D-Bus signature string
    source : str
        Source identifier for categorization
    original_message : Any, optional
        Original D-Bus message (dbus.lowlevel.Message) preserved for detailed analysis
    """
    # Common fields
    event_type: str  # 'signal', 'method_call', 'method_return', 'error'
    interface: str
    path: str
    timestamp: float
    sender: str = ""
    destination: str = ""
    serial: int = 0
    reply_serial: Optional[int] = None  # For returns/errors
    
    # Type-specific fields
    signal_name: Optional[str] = None  # For signals
    method_name: Optional[str] = None  # For method calls/returns
    error_name: Optional[str] = None  # For errors
    error_message: Optional[str] = None  # For errors
    
    # Message content
    args: Tuple[Any, ...] = ()
    signature: str = ""
    
    # Metadata
    source: str = ""  # 'read', 'write', 'notification', 'property_change', 'agent', etc.
    
    # Preserve original message for detailed analysis
    original_message: Optional[Any] = None  # dbus.lowlevel.Message, but using Any for compatibility


class SignalCorrelator:
    """Correlates related signals from different sources.
    
    **DEPRECATED**: For new code, use `DBusEventAggregator` which provides
    unified correlation across all D-Bus event types. This class is retained
    for backward compatibility.
    """
    
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


class DBusEventAggregator:
    """Aggregates and correlates all D-Bus events (signals, method calls, returns, errors).
    
    Provides a unified view of all D-Bus communications for comprehensive monitoring
    and analysis. Replaces separate signal/method call capture systems.
    """
    
    def __init__(self, max_events: int = 1000):
        """Initialize the aggregator.
        
        Parameters
        ----------
        max_events : int
            Maximum number of events to keep in memory (default: 1000)
        """
        self._events: List[DBusEventCapture] = []
        self._lock = threading.Lock()
        self._max_events = max_events
        
    def add_event(self, event: DBusEventCapture) -> None:
        """Add an event to the aggregator.
        
        Parameters
        ----------
        event : DBusEventCapture
            Event to add
        """
        with self._lock:
            self._events.append(event)
            # Trim old events
            if len(self._events) > self._max_events:
                self._events.pop(0)
    
    def get_events(self, 
                   event_type: Optional[str] = None,
                   interface: Optional[str] = None,
                   path: Optional[str] = None,
                   time_window: Optional[float] = None,
                   limit: int = 100) -> List[DBusEventCapture]:
        """Query events with optional filters.
        
        Parameters
        ----------
        event_type : str, optional
            Filter by event type ('signal', 'method_call', 'method_return', 'error')
        interface : str, optional
            Filter by D-Bus interface
        path : str, optional
            Filter by D-Bus path (exact match or prefix)
        time_window : float, optional
            Filter by time window in seconds (events within this time from now)
        limit : int
            Maximum number of events to return (default: 100)
            
        Returns
        -------
        List[DBusEventCapture]
            List of matching events, most recent first
        """
        with self._lock:
            events = self._events.copy()
        
        # Apply filters
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if interface:
            events = [e for e in events if e.interface == interface]
        if path:
            events = [e for e in events if e.path == path or e.path.startswith(path)]
        if time_window:
            now = time.time()
            events = [e for e in events if now - e.timestamp <= time_window]
        
        # Return most recent first
        return sorted(events, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    def correlate_events(self, event: DBusEventCapture, 
                        time_window: float = 2.0) -> List[DBusEventCapture]:
        """Find events related to the given event.
        
        Correlates by:
        - Serial number (method call → return/error)
        - Path relationships
        - Time window
        
        Parameters
        ----------
        event : DBusEventCapture
            Event to find related events for
        time_window : float
            Time window in seconds for correlation (default: 2.0)
            
        Returns
        -------
        List[DBusEventCapture]
            List of related events, sorted by timestamp
        """
        with self._lock:
            related = []
            for e in self._events:
                if e is event:
                    continue
                
                # Check time window
                if abs(e.timestamp - event.timestamp) > time_window:
                    continue
                
                # Correlate by serial (method call → return/error)
                if (event.event_type == "method_call" and 
                    e.reply_serial is not None and
                    e.reply_serial == event.serial):
                    related.append(e)
                elif (e.event_type == "method_call" and 
                      event.reply_serial is not None and
                      event.reply_serial == e.serial):
                    related.append(e)
                
                # Correlate by path
                elif (e.path.startswith(event.path) or 
                      event.path.startswith(e.path)):
                    related.append(e)
            
            return sorted(related, key=lambda x: x.timestamp)
    
    def get_method_call_chain(self, method_call_serial: int) -> List[DBusEventCapture]:
        """Get the complete chain for a method call (call → return/error).
        
        Parameters
        ----------
        method_call_serial : int
            Serial number of the method call to trace
            
        Returns
        -------
        List[DBusEventCapture]
            Complete chain: [method_call, return/error], sorted by timestamp
        """
        with self._lock:
            events = self._events.copy()
        
        # Find the method call
        call_event = None
        for event in events:
            if (event.event_type == "method_call" and 
                event.serial == method_call_serial):
                call_event = event
                break
        
        if not call_event:
            return []
        
        # Find related return/error
        chain = [call_event]
        related = self.correlate_events(call_event, time_window=5.0)
        for event in related:
            if event.event_type in ("method_return", "error"):
                chain.append(event)
        
        return sorted(chain, key=lambda x: x.timestamp)
    
    def clear(self) -> None:
        """Clear all events."""
        with self._lock:
            self._events.clear()


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
        
        # Method call monitoring (deprecated - use unified monitoring)
        self._method_call_captures: List[MethodCallCapture] = []
        self._method_call_monitoring = False
        self._method_call_filter: Optional[Callable] = None
        
        # Unified D-Bus event aggregator
        self._event_aggregator = DBusEventAggregator()
        self._unified_monitoring = False
        self._unified_message_filter: Optional[Callable] = None
        
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

    def has_any_connected_device(self) -> bool:
        """Check if any registered device is currently connected.
        
        Returns
        -------
        bool
            True if any device is connected, False otherwise
        """
        with self._lock:
            for device in self._devices.values():
                try:
                    if hasattr(device, 'is_connected') and device.is_connected():
                        return True
                except Exception:
                    # Skip devices that can't be checked
                    continue
            return False

    def get_connected_devices(self) -> List[object]:
        """Get list of all currently connected devices.
        
        Returns
        -------
        List[object]
            List of connected device objects
        """
        connected = []
        with self._lock:
            for device in self._devices.values():
                try:
                    if hasattr(device, 'is_connected') and device.is_connected():
                        connected.append(device)
                except Exception:
                    continue
        return connected

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
        # Also detach method call listeners if they were attached (deprecated)
        if self._method_call_monitoring:
            self._detach_method_call_listeners()
        # Also detach unified listeners if they were attached
        if self._unified_monitoring:
            self._detach_unified_listeners()

    # ------------------------------------------------------------------
    # Unified D-Bus Event Monitoring
    # ------------------------------------------------------------------
    def enable_unified_dbus_monitoring(self, enabled: bool = True, 
                                       filters: Optional[Dict[str, Any]] = None) -> None:
        """Enable unified monitoring of all D-Bus message types.
        
        When enabled, captures signals, method calls, method returns, and errors
        for comprehensive BlueZ/Agent/AgentManager monitoring. This provides a
        general catch-all watcher for all D-Bus communications.
        
        Parameters
        ----------
        enabled : bool
            Whether to enable unified monitoring (default: True)
        filters : dict, optional
            Optional filters for interfaces, paths, etc. (not yet implemented)
        """
        if enabled == self._unified_monitoring:
            return
        
        self._unified_monitoring = enabled
        
        if enabled:
            self._attach_unified_listeners(filters)
            print_and_log(
                "[+] Unified D-Bus monitoring enabled (signals, method calls, returns, errors)",
                LOG__AGENT
            )
        else:
            self._detach_unified_listeners()
            print_and_log(
                "[*] Unified D-Bus monitoring disabled",
                LOG__AGENT
            )

    def _attach_unified_listeners(self, filters: Optional[Dict[str, Any]] = None) -> None:
        """Attach unified message filter for all D-Bus message types."""
        try:
            # Use match strings to catch all relevant messages
            # Match messages from/to BlueZ service and Agent interfaces
            # Note: Some match strings use eavesdrop='true' which requires permissions
            match_strings = [
                # Signals from BlueZ paths (path-based matching is more reliable than sender)
                "type='signal',path_namespace='/org/bluez'",
                # ObjectManager signals (BlueZ uses this for device lifecycle)
                "type='signal',interface='org.freedesktop.DBus.ObjectManager'",
                # Method calls to BlueZ service
                "type='method_call',destination='org.bluez'",
                # Method calls to Agent interfaces (with eavesdrop for monitoring)
                "type='method_call',interface='org.bluez.Agent1',eavesdrop='true'",
                "type='method_call',interface='org.bluez.AgentManager1',eavesdrop='true'",
                # Method returns from BlueZ (more specific than broad eavesdrop)
                "type='method_return',sender='org.bluez'",
                # Errors from BlueZ (more specific than broad eavesdrop)
                "type='error',sender='org.bluez'",
                # Method returns/errors for Agent interfaces (with eavesdrop)
                "type='method_return',interface='org.bluez.Agent1',eavesdrop='true'",
                "type='method_return',interface='org.bluez.AgentManager1',eavesdrop='true'",
                "type='error',interface='org.bluez.Agent1',eavesdrop='true'",
                "type='error',interface='org.bluez.AgentManager1',eavesdrop='true'",
            ]
            
            for match_str in match_strings:
                try:
                    match = self.bus.add_match_string(match_str)
                    self._matches.append(match)
                except dbus.exceptions.DBusException:
                    # Some matches may require permissions; continue with others
                    pass
            
            # Add unified message filter
            self._unified_message_filter = self._on_dbus_message
            self.bus.add_message_filter(self._unified_message_filter)
            
            print_and_log(
                "[DEBUG] Unified D-Bus listeners attached",
                LOG__DEBUG
            )
            
        except dbus.exceptions.DBusException as e:
            name = getattr(e, "get_dbus_name", lambda: None)() or "unknown"
            msg = getattr(e, "get_dbus_message", lambda: None)() or ""
            print_and_log(
                f"[!] Failed to attach unified listeners: {name}: {msg}",
                LOG__AGENT
            )
            print_and_log(
                "[*] Note: Eavesdropping may require root or D-Bus policy changes. "
                "Monitoring will continue with available message types.",
                LOG__AGENT
            )
            self._unified_monitoring = False

    def _detach_unified_listeners(self) -> None:
        """Detach unified message filter."""
        try:
            # Remove message filter
            if self._unified_message_filter:
                if hasattr(self.bus, 'remove_message_filter'):
                    self.bus.remove_message_filter(self._unified_message_filter)
                self._unified_message_filter = None
        except Exception:
            pass
        
        # Note: Match strings are removed in _detach_bus_listeners()
        # which is called automatically when _matches is cleared

    def _on_dbus_message(self, bus: dbus.Bus, message: Any) -> None:  # message is dbus.lowlevel.Message
        """
        Unified handler for all D-Bus message types.
        
        Captures signals, method calls, method returns, and errors for
        comprehensive monitoring and correlation.
        
        Parameters
        ----------
        bus : dbus.Bus
            D-Bus bus object
        message : Any
            D-Bus message object (dbus.lowlevel.Message, preserved for detailed analysis)
        """
        if not self._unified_monitoring:
            return None
        
        try:
            msg_type = message.get_type()
            timestamp = time.time()
            
            # Extract common fields
            interface = message.get_interface() or ""
            path = message.get_path() or ""
            sender = message.get_sender() or ""
            destination = message.get_destination() or ""
            serial = message.get_serial()
            
            # Filter for BlueZ/Agent related messages
            if not self._is_relevant_message(interface, path, sender, destination):
                return None
            
            event = None
            
            # Message type constants: SIGNAL=1, METHOD_CALL=2, METHOD_RETURN=4, ERROR=3
            if msg_type == DBUS_MESSAGE_SIGNAL:
                event = self._capture_signal(message, timestamp, interface, path, sender, destination, serial)
            
            elif msg_type == DBUS_MESSAGE_METHOD_CALL:
                event = self._capture_method_call(message, timestamp, interface, path, sender, destination, serial)
            
            elif msg_type == DBUS_MESSAGE_METHOD_RETURN:
                event = self._capture_method_return(message, timestamp, interface, path, sender, destination, serial)
            
            elif msg_type == DBUS_MESSAGE_ERROR:
                event = self._capture_error(message, timestamp, interface, path, sender, destination, serial)
            
            if event:
                # Add to aggregator
                self._event_aggregator.add_event(event)
                
                # Log with human-readable + detailed format
                self._log_event(event)
                
                # Add to legacy correlator for backward compatibility
                if msg_type == DBUS_MESSAGE_SIGNAL:
                    signal_capture = SignalCapture(
                        interface=event.interface,
                        path=event.path,
                        signal_name=event.signal_name or "",
                        args=event.args,
                        timestamp=event.timestamp,
                        source=event.source
                    )
                    self._signal_correlator.add_capture(signal_capture)
        
        except Exception as exc:
            # Log exception type and message transparently for debugging
            error_type = type(exc).__name__
            error_msg = str(exc)
            print_and_log(
                f"[-] Error processing D-Bus message: {error_type}: {error_msg}",
                LOG__DEBUG
            )
        
        return None  # Allow message to continue

    def _is_relevant_message(self, interface: str, path: str, 
                            sender: str, destination: str) -> bool:
        """Check if message is relevant to BlueZ/Agent monitoring.
        
        Parameters
        ----------
        interface : str
            D-Bus interface name
        path : str
            D-Bus object path
        sender : str
            D-Bus sender name
        destination : str
            D-Bus destination name
            
        Returns
        -------
        bool
            True if message is relevant to BlueZ/Agent monitoring
        """
        # BlueZ service name (exact match)
        if sender == "org.bluez" or destination == "org.bluez":
            return True
        
        # Agent interfaces (always relevant)
        if interface in ("org.bluez.Agent1", "org.bluez.AgentManager1"):
            return True
        
        # BlueZ device/service paths (always relevant)
        if path.startswith("/org/bluez/"):
            return True
        
        # ObjectManager signals at root path (BlueZ uses this for device lifecycle)
        if path == "/" and interface == "org.freedesktop.DBus.ObjectManager":
            return True
        
        # For signals with null destination, check path and interface
        # Signals often have destination="(null destination)" or empty string
        if not destination or destination == "(null destination)":
            # Signals from BlueZ paths are relevant
            if path.startswith("/org/bluez/"):
                return True
            # ObjectManager signals are relevant (BlueZ uses these)
            if interface == "org.freedesktop.DBus.ObjectManager":
                return True
        
        # For method calls/returns/errors, check if they're related to BlueZ paths
        # Bus names like :1.149 are dynamic and can't be reliably matched by name
        # Instead, rely on path and interface matching (already checked above)
        # Additional check: if path is BlueZ-related, it's relevant
        if path.startswith("/org/bluez/"):
            return True
        
        return False

    def _capture_signal(self, message: Any, timestamp: float,  # message is dbus.lowlevel.Message
                       interface: str, path: str, sender: str, 
                       destination: str, serial: int) -> DBusEventCapture:
        """Capture a D-Bus signal message."""
        signal_name = message.get_member()
        args = message.get_args_list()
        signature = message.get_signature()
        
        # Determine source
        source = "signal"
        if interface == "org.freedesktop.DBus.Properties" and signal_name == "PropertiesChanged":
            source = "property_change"
        elif signal_name == "InterfacesAdded":
            source = "interface_added"
        elif signal_name == "InterfacesRemoved":
            source = "interface_removed"
        
        return DBusEventCapture(
            event_type="signal",
            interface=interface,
            path=path,
            timestamp=timestamp,
            sender=sender,
            destination=destination,
            serial=serial,
            signal_name=signal_name,
            args=args,
            signature=signature,
            source=source,
            original_message=message
        )

    def _capture_method_call(self, message: Any, timestamp: float,  # message is dbus.lowlevel.Message
                            interface: str, path: str, sender: str,
                            destination: str, serial: int) -> DBusEventCapture:
        """Capture a D-Bus method call message."""
        method_name = message.get_member()
        args = message.get_args_list()
        signature = message.get_signature()
        
        # Determine source
        source = "method_call"
        if interface in ("org.bluez.Agent1", "org.bluez.AgentManager1"):
            source = "agent_method_call"
        elif interface == "org.bluez.Device1":
            source = "device_method_call"
        
        return DBusEventCapture(
            event_type="method_call",
            interface=interface,
            path=path,
            timestamp=timestamp,
            sender=sender,
            destination=destination,
            serial=serial,
            method_name=method_name,
            args=args,
            signature=signature,
            source=source,
            original_message=message
        )

    def _capture_method_return(self, message: Any, timestamp: float,  # message is dbus.lowlevel.Message
                              interface: str, path: str, sender: str,
                              destination: str, serial: int) -> DBusEventCapture:
        """Capture a D-Bus method return message."""
        reply_serial = message.get_reply_serial()
        args = message.get_args_list()
        signature = message.get_signature()
        
        return DBusEventCapture(
            event_type="method_return",
            interface=interface,
            path=path,
            timestamp=timestamp,
            sender=sender,
            destination=destination,
            serial=serial,
            reply_serial=reply_serial,
            args=args,
            signature=signature,
            source="method_return",
            original_message=message
        )

    def _capture_error(self, message: Any, timestamp: float,  # message is dbus.lowlevel.Message
                      interface: str, path: str, sender: str,
                      destination: str, serial: int) -> DBusEventCapture:
        """Capture a D-Bus error message."""
        reply_serial = message.get_reply_serial()
        error_name = message.get_error_name()
        args_list = message.get_args_list()
        error_message = args_list[0] if args_list else ""
        
        return DBusEventCapture(
            event_type="error",
            interface=interface,
            path=path,
            timestamp=timestamp,
            sender=sender,
            destination=destination,
            serial=serial,
            reply_serial=reply_serial,
            error_name=error_name,
            error_message=error_message,
            args=args_list,
            source="error",
            original_message=message
        )

    def _log_event(self, event: DBusEventCapture) -> None:
        """Log event with human-readable + detailed format.
        
        Follows error handling pattern: human-readable summary + detailed information.
        """
        timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(event.timestamp))
        
        if event.event_type == "signal":
            # Human-readable
            print_and_log(
                f"[{timestamp_str}] SIGNAL: {event.signal_name} "
                f"(interface={event.interface}, path={event.path})",
                LOG__AGENT
            )
            # Detailed
            args_str = self._format_method_args(event.args)
            print_and_log(
                f"[DETAIL] {event.signal_name}: interface={event.interface}, "
                f"path={event.path}, sender={event.sender}, serial={event.serial}, "
                f"signature={event.signature}, args={args_str}",
                LOG__AGENT
            )
        
        elif event.event_type == "method_call":
            # Human-readable
            print_and_log(
                f"[{timestamp_str}] METHOD CALL: {event.method_name} "
                f"(interface={event.interface}, path={event.path}, "
                f"sender={event.sender}, destination={event.destination})",
                LOG__AGENT
            )
            # Detailed
            args_str = self._format_method_args(event.args)
            print_and_log(
                f"[DETAIL] {event.method_name}: interface={event.interface}, "
                f"path={event.path}, sender={event.sender}, destination={event.destination}, "
                f"serial={event.serial}, signature={event.signature}, args={args_str}",
                LOG__AGENT
            )
            
            # Special highlighting
            if event.interface == "org.bluez.Agent1" and event.method_name == "RequestPinCode":
                print_and_log(
                    f"[!] PIN CODE REQUEST: BlueZ ({event.sender}) -> agent ({event.destination})",
                    LOG__AGENT
                )
                if event.args:
                    device_path = event.args[0] if isinstance(event.args[0], str) else str(event.args[0])
                    print_and_log(
                        f"[!] Target device: {device_path}",
                        LOG__AGENT
                    )
        
        elif event.event_type == "method_return":
            # Human-readable
            args_str = self._format_method_args(event.args)
            print_and_log(
                f"[{timestamp_str}] METHOD RETURN: reply_serial={event.reply_serial} "
                f"(sender={event.sender}, destination={event.destination}, args={args_str})",
                LOG__AGENT
            )
            # Detailed
            print_and_log(
                f"[DETAIL] METHOD RETURN: interface={event.interface}, path={event.path}, "
                f"sender={event.sender}, destination={event.destination}, serial={event.serial}, "
                f"reply_serial={event.reply_serial}, signature={event.signature}, args={args_str}",
                LOG__AGENT
            )
        
        elif event.event_type == "error":
            # Human-readable (follows error handling pattern: name: msg)
            print_and_log(
                f"[{timestamp_str}] ERROR: {event.error_name}: {event.error_message} "
                f"(reply_serial={event.reply_serial}, sender={event.sender}, destination={event.destination})",
                LOG__AGENT
            )
            # Detailed
            print_and_log(
                f"[DETAIL] ERROR: error_name={event.error_name}, error_message={event.error_message}, "
                f"interface={event.interface}, path={event.path}, sender={event.sender}, "
                f"destination={event.destination}, serial={event.serial}, reply_serial={event.reply_serial}",
                LOG__AGENT
            )
            
            # Special highlighting for authentication errors
            if event.error_name and "Authentication" in event.error_name:
                print_and_log(
                    f"[!] AUTHENTICATION ERROR: {event.error_name}: {event.error_message}",
                    LOG__AGENT
                )

    def get_recent_events(self, event_type: Optional[str] = None,
                         interface: Optional[str] = None,
                         path: Optional[str] = None,
                         time_window: Optional[float] = None,
                         limit: int = 100) -> List[DBusEventCapture]:
        """Get recent D-Bus events with optional filters.
        
        Parameters
        ----------
        event_type : str, optional
            Filter by event type ('signal', 'method_call', 'method_return', 'error')
        interface : str, optional
            Filter by D-Bus interface
        path : str, optional
            Filter by D-Bus path (exact match or prefix)
        time_window : float, optional
            Filter by time window in seconds (events within this time from now)
        limit : int
            Maximum number of events to return (default: 100)
            
        Returns
        -------
        List[DBusEventCapture]
            List of matching events, most recent first
        """
        return self._event_aggregator.get_events(
            event_type=event_type,
            interface=interface,
            path=path,
            time_window=time_window,
            limit=limit
        )

    def correlate_event(self, event: DBusEventCapture, 
                       time_window: float = 2.0) -> List[DBusEventCapture]:
        """Find events related to the given event.
        
        Parameters
        ----------
        event : DBusEventCapture
            Event to find related events for
        time_window : float
            Time window in seconds for correlation (default: 2.0)
            
        Returns
        -------
        List[DBusEventCapture]
            List of related events, sorted by timestamp
        """
        return self._event_aggregator.correlate_events(event, time_window)

    def get_method_call_chain(self, method_call_serial: int) -> List[DBusEventCapture]:
        """Get the complete chain for a method call (call → return/error).
        
        Parameters
        ----------
        method_call_serial : int
            Serial number of the method call to trace
            
        Returns
        -------
        List[DBusEventCapture]
            Complete chain: [method_call, return/error], sorted by timestamp
        """
        return self._event_aggregator.get_method_call_chain(method_call_serial)

    # ------------------------------------------------------------------
    # Method Call Monitoring (Deprecated - use unified monitoring)
    # ------------------------------------------------------------------
    def enable_agent_method_call_monitoring(self, enabled: bool = True) -> None:
        """Enable or disable monitoring of Agent1 and AgentManager1 method calls.
        
        **DEPRECATED**: Use `enable_unified_dbus_monitoring()` instead, which
        captures method calls, returns, errors, and signals.
        
        This method is retained for backward compatibility and now delegates
        to the unified monitoring system.
        """
        # Delegate to unified monitoring
        self.enable_unified_dbus_monitoring(enabled)

    def _attach_method_call_listeners(self) -> None:
        """Attach D-Bus message filters for method call monitoring."""
        try:
            # Monitor method calls to Agent1 interface
            match_agent = self.bus.add_match_string(
                "type='method_call',"
                "interface='org.bluez.Agent1',"
                "eavesdrop='true'"
            )
            self._matches.append(match_agent)
            
            # Monitor method calls to AgentManager1 interface
            match_manager = self.bus.add_match_string(
                "type='method_call',"
                "interface='org.bluez.AgentManager1',"
                "eavesdrop='true'"
            )
            self._matches.append(match_manager)
            
            # Add message filter to process method calls
            self._method_call_filter = self._on_method_call
            self.bus.add_message_filter(self._method_call_filter)
            
            print_and_log(
                "[DEBUG] Method call listeners attached (Agent1, AgentManager1)",
                LOG__DEBUG
            )
            
        except dbus.exceptions.DBusException as e:
            name = getattr(e, "get_dbus_name", lambda: None)() or "unknown"
            msg = getattr(e, "get_dbus_message", lambda: None)() or ""
            print_and_log(
                f"[!] Failed to attach method call listeners: {name}: {msg}",
                LOG__AGENT
            )
            print_and_log(
                "[*] Note: Eavesdropping may require root or D-Bus policy changes. "
                "Monitoring will continue without method call visibility.",
                LOG__AGENT
            )
            # Don't fail - continue without method call monitoring
            self._method_call_monitoring = False

    def _detach_method_call_listeners(self) -> None:
        """Detach D-Bus message filters for method call monitoring."""
        try:
            # Remove message filter
            if self._method_call_filter:
                if hasattr(self.bus, 'remove_message_filter'):
                    self.bus.remove_message_filter(self._method_call_filter)
                self._method_call_filter = None
        except Exception:
            pass
        
        # Note: Match strings are removed in _detach_bus_listeners()
        # which is called automatically when _matches is cleared

    def _on_method_call(self, bus: dbus.Bus, message: Any) -> None:  # message is dbus.lowlevel.Message
        """
        Handle D-Bus method call messages for Agent1 and AgentManager1.
        
        Provides human-readable logging while preserving original message details
        for detailed analysis. Format follows error handling pattern: human-readable
        summary + detailed information.
        
        Parameters
        ----------
        bus : dbus.Bus
            D-Bus bus object
        message : Any
            D-Bus message object (dbus.lowlevel.Message, preserved for detailed analysis)
        """
        if not self._method_call_monitoring:
            return None  # Allow message to continue
        
        try:
            # Only process method_call messages
            if message.get_type() != DBUS_MESSAGE_METHOD_CALL:
                return None
            
            interface = message.get_interface()
            
            # Filter for Agent1 and AgentManager1 interfaces only
            if interface not in ("org.bluez.Agent1", "org.bluez.AgentManager1"):
                return None
            
            # Extract message details
            method_name = message.get_member()
            path = message.get_path()
            sender = message.get_sender()
            destination = message.get_destination()
            serial = message.get_serial()
            signature = message.get_signature()
            args = message.get_args_list()
            timestamp = time.time()
            
            # Create capture for correlation/analysis
            capture = MethodCallCapture(
                interface=interface,
                path=path,
                method_name=method_name,
                args=args,
                timestamp=timestamp,
                sender=sender,
                destination=destination,
                serial=serial,
                signature=signature,
                original_message=message  # Preserve for detailed analysis
            )
            
            # Add to captures list (with size limit)
            with self._lock:
                self._method_call_captures.append(capture)
                # Keep last 100 captures
                if len(self._method_call_captures) > 100:
                    self._method_call_captures.pop(0)
            
            # Format human-readable log message
            timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
            
            # Human-readable summary (like error handling pattern)
            if interface == "org.bluez.Agent1":
                # Format args for readability
                args_str = self._format_method_args(args)
                
                # Human-readable summary
                print_and_log(
                    f"[{timestamp_str}] Agent1 METHOD CALL: {method_name} "
                    f"(path={path}, sender={sender}, destination={destination})",
                    LOG__AGENT
                )
                
                # Detailed information (preserved for analysis)
                print_and_log(
                    f"[DETAIL] {method_name}: interface={interface}, path={path}, "
                    f"sender={sender}, destination={destination}, serial={serial}, "
                    f"signature={signature}, args={args_str}",
                    LOG__AGENT
                )
                
                # Special highlighting for PIN code requests
                if method_name == "RequestPinCode":
                    print_and_log(
                        f"[!] PIN CODE REQUEST DETECTED: BlueZ ({sender}) calling agent "
                        f"at {destination} on path {path}",
                        LOG__AGENT
                    )
                    # Log device path if present in args
                    if args:
                        device_path = args[0] if isinstance(args[0], str) else str(args[0])
                        print_and_log(
                            f"[!] Target device: {device_path}",
                            LOG__AGENT
                        )
            
            elif interface == "org.bluez.AgentManager1":
                args_str = self._format_method_args(args)
                
                # Human-readable summary
                print_and_log(
                    f"[{timestamp_str}] AgentManager1 METHOD CALL: {method_name} "
                    f"(path={path}, sender={sender})",
                    LOG__AGENT
                )
                
                # Detailed information
                print_and_log(
                    f"[DETAIL] {method_name}: interface={interface}, path={path}, "
                    f"sender={sender}, serial={serial}, signature={signature}, args={args_str}",
                    LOG__AGENT
                )
                
                # Special handling for registration events
                if method_name in ("RegisterAgent", "RequestDefaultAgent"):
                    agent_path = args[0] if args else "unknown"
                    print_and_log(
                        f"[!] Agent registration event: {method_name} -> agent_path={agent_path}",
                        LOG__AGENT
                    )
            
            # Add to signal correlator for correlation with signals
            # (Convert to SignalCapture-like format for correlation)
            signal_capture = SignalCapture(
                interface=interface,
                path=path,
                signal_name=f"METHOD_CALL:{method_name}",
                args=args,
                timestamp=timestamp,
                source="method_call"
            )
            self._signal_correlator.add_capture(signal_capture)
            
        except Exception as exc:
            print_and_log(
                f"[-] Error processing method call message: {exc}",
                LOG__DEBUG
            )
        
        # Return None to allow message to continue to destination
        return None

    def _format_method_args(self, args: Tuple[Any, ...]) -> str:
        """Format method call arguments for human-readable logging.
        
        Preserves original values while making them readable.
        
        Parameters
        ----------
        args : Tuple[Any, ...]
            Method call arguments
            
        Returns
        -------
        str
            Formatted string representation
        """
        if not args:
            return "[]"
        
        formatted = []
        for arg in args:
            # Convert D-Bus types to Python types for readability
            if isinstance(arg, (dbus.String, dbus.ObjectPath)):
                formatted.append(f'"{str(arg)}"')
            elif isinstance(arg, (dbus.UInt32, dbus.Int32, dbus.UInt16, dbus.Int16,
                                  dbus.UInt64, dbus.Int64)):
                formatted.append(str(int(arg)))
            elif isinstance(arg, dbus.Boolean):
                formatted.append(str(bool(arg)))
            elif isinstance(arg, dbus.Array):
                # Format arrays
                arr_items = []
                for item in arg:
                    # Recursively format array items
                    if isinstance(item, (dbus.String, dbus.ObjectPath)):
                        arr_items.append(f'"{str(item)}"')
                    elif isinstance(item, (dbus.UInt32, dbus.Int32, dbus.UInt16, dbus.Int16,
                                          dbus.UInt64, dbus.Int64)):
                        arr_items.append(str(int(item)))
                    elif isinstance(item, dbus.Boolean):
                        arr_items.append(str(bool(item)))
                    else:
                        arr_items.append(repr(item))
                formatted.append(f"[{', '.join(arr_items)}]")
            elif isinstance(arg, dbus.Dictionary):
                # Format dictionaries
                dict_items = []
                for k, v in arg.items():
                    key_str = f'"{k}"' if isinstance(k, str) else str(k)
                    val_str = f'"{v}"' if isinstance(v, str) else str(v)
                    dict_items.append(f"{key_str}: {val_str}")
                formatted.append(f"{{{', '.join(dict_items)}}}")
            else:
                # Preserve original representation
                formatted.append(repr(arg))
        
        return f"[{', '.join(formatted)}]"

    def get_recent_method_calls(self, interface: Optional[str] = None, 
                               limit: int = 10) -> List[MethodCallCapture]:
        """Get recent method call captures.
        
        Parameters
        ----------
        interface : str, optional
            Filter by interface (e.g., "org.bluez.Agent1")
        limit : int
            Maximum number of captures to return
            
        Returns
        -------
        List[MethodCallCapture]
            List of recent method call captures
        """
        with self._lock:
            captures = self._method_call_captures.copy()
        
        if interface:
            captures = [c for c in captures if c.interface == interface]
        
        # Return most recent first
        return sorted(captures, key=lambda x: x.timestamp, reverse=True)[:limit]

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
