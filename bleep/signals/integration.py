"""Integration between the new signal capture system and the existing BlueZ signals.

This module provides hooks to connect the existing BlueZ signal handling system
with the new structured signal capture and routing system.
"""

from typing import Any, Dict, Optional

from bleep.dbuslayer.signals import SignalCapture, system_dbus__bluez_signals
from bleep.signals import (
    SignalType,
    process_signal,
    process_signal_capture,
    get_router,
)


def integrate_with_bluez_signals(signals_instance: Optional[system_dbus__bluez_signals] = None) -> None:
    """Integrate the signal capture system with the existing BlueZ signals.
    
    This function hooks into the existing signal handling system to route signals
    through the new signal capture system.
    
    Args:
        signals_instance: Optional instance of system_dbus__bluez_signals. If None,
                         a new instance will be created.
    """
    # Get or create signals instance
    if signals_instance is None:
        signals_instance = system_dbus__bluez_signals()
    
    # Hook into PropertiesChanged signal
    def _properties_changed_hook(interface: str, changed: Dict[str, Any], 
                                invalidated: Dict[str, Any], path: str) -> None:
        """Hook for PropertiesChanged signal.
        
        Args:
            interface: D-Bus interface
            changed: Changed properties
            invalidated: Invalidated properties
            path: D-Bus path
        """
        # Process each changed property as a separate signal
        for prop_name, value in changed.items():
            process_signal(
                signal_type=SignalType.PROPERTY_CHANGE,
                path=path,
                interface=interface,
                property_name=prop_name,
                value=value
            )
    
    # Hook into notification handling
    def _notification_hook(path: str, value: bytes) -> None:
        """Hook for notification signals.
        
        Args:
            path: D-Bus path of the characteristic
            value: Notification value
        """
        process_signal(
            signal_type=SignalType.NOTIFICATION,
            path=path,
            value=value
        )
    
    # Hook into read events
    def _read_hook(path: str, value: bytes) -> None:
        """Hook for read events.
        
        Args:
            path: D-Bus path of the characteristic
            value: Read value
        """
        process_signal(
            signal_type=SignalType.READ,
            path=path,
            value=value
        )
    
    # Hook into write events
    def _write_hook(path: str, value: bytes) -> None:
        """Hook for write events.
        
        Args:
            path: D-Bus path of the characteristic
            value: Written value
        """
        process_signal(
            signal_type=SignalType.WRITE,
            path=path,
            value=value
        )
    
    # Register the hooks
    # For PropertiesChanged, we need to monkey patch the _properties_changed method
    original_properties_changed = signals_instance._properties_changed
    
    def _patched_properties_changed(interface, changed, invalidated, path=None):
        # Call the original method
        result = original_properties_changed(interface, changed, invalidated, path)
        
        # Call our hook
        if path is not None:
            _properties_changed_hook(interface, changed, invalidated, path)
        
        return result
    
    # Apply the monkey patch
    signals_instance._properties_changed = _patched_properties_changed
    
    # Register notification, read, and write hooks
    for path in signals_instance._notification_callbacks:
        signals_instance.register_notification_callback(path, _notification_hook)
    
    # Monkey patch the handle_read_event and handle_write_event methods
    original_handle_read = signals_instance.handle_read_event
    original_handle_write = signals_instance.handle_write_event
    
    def _patched_handle_read(char_path, value):
        # Call the original method
        original_handle_read(char_path, value)
        
        # Call our hook
        _read_hook(char_path, value)
    
    def _patched_handle_write(char_path, value):
        # Call the original method
        original_handle_write(char_path, value)
        
        # Call our hook
        _write_hook(char_path, value)
    
    # Apply the monkey patches
    signals_instance.handle_read_event = _patched_handle_read
    signals_instance.handle_write_event = _patched_handle_write


def patch_signal_capture_class() -> None:
    """Patch the SignalCapture class to automatically route captures.
    
    This function monkey patches the SignalCapture.__init__ method to automatically
    route new signal captures through the signal capture system.
    """
    original_init = SignalCapture.__init__
    
    def _patched_init(self, *args, **kwargs):
        # Call the original __init__
        original_init(self, *args, **kwargs)
        
        # Process the signal capture
        process_signal_capture(self)
    
    # Apply the monkey patch
    SignalCapture.__init__ = _patched_init

