"""Signal routing and processing for BLEEP.

This module provides classes for routing signals based on configured filters
and executing the associated actions.
"""

import csv
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.dbuslayer.signals import SignalCapture
from bleep.signals.capture_config import (
    SignalCaptureConfig,
    SignalFilter,
    SignalRoute,
    SignalAction,
    SignalType,
    ActionType,
)


class ActionExecutor:
    """Executes actions on captured signals."""
    
    def __init__(self, output_dir: Optional[str] = None):
        """Initialize the action executor.
        
        Args:
            output_dir: Directory for saving output files. Defaults to ~/.bleep/signals/output
        """
        self.output_dir = output_dir or os.path.expanduser("~/.bleep/signals/output")
        os.makedirs(self.output_dir, exist_ok=True)
        
        # File handles for persistent output
        self._file_handles: Dict[str, Any] = {}
        self._csv_writers: Dict[str, csv.writer] = {}
        
        # Registered callbacks
        self._callbacks: Dict[str, Callable] = {}
        
        # Lock for thread safety
        self._lock = threading.Lock()
    
    def register_callback(self, name: str, callback: Callable) -> None:
        """Register a callback function.
        
        Args:
            name: Name of the callback
            callback: Function to call when an action with this name is executed
        """
        with self._lock:
            self._callbacks[name] = callback
    
    def unregister_callback(self, name: str) -> None:
        """Unregister a callback function.
        
        Args:
            name: Name of the callback to unregister
        """
        with self._lock:
            self._callbacks.pop(name, None)
    
    def execute(self, action: SignalAction, signal_data: Dict[str, Any]) -> None:
        """Execute an action on a signal.
        
        Args:
            action: Action to execute
            signal_data: Signal data to act on
        """
        try:
            if action.action_type == ActionType.LOG:
                self._execute_log(action, signal_data)
            elif action.action_type == ActionType.SAVE:
                self._execute_save(action, signal_data)
            elif action.action_type == ActionType.CALLBACK:
                self._execute_callback(action, signal_data)
            elif action.action_type == ActionType.DB_STORE:
                self._execute_db_store(action, signal_data)
            elif action.action_type == ActionType.FORWARD:
                self._execute_forward(action, signal_data)
            elif action.action_type == ActionType.TRANSFORM:
                self._execute_transform(action, signal_data)
        except Exception as e:
            print_and_log(f"[ERROR] Action execution failed: {e}", LOG__DEBUG)
    
    def _execute_log(self, action: SignalAction, signal_data: Dict[str, Any]) -> None:
        """Execute a LOG action.
        
        Args:
            action: Action to execute
            signal_data: Signal data to log
        """
        level = action.parameters.get('level', 'GENERAL')
        log_level = LOG__DEBUG if level == 'DEBUG' else LOG__GENERAL
        
        # Format the log message
        signal_type = signal_data.get('signal_type', 'UNKNOWN')
        path = signal_data.get('path', '')
        value = signal_data.get('value', None)
        
        if isinstance(value, bytes):
            value_str = value.hex()
        else:
            value_str = str(value)
        
        # Truncate long values
        if len(value_str) > 100:
            value_str = value_str[:97] + '...'
        
        message = f"[SIGNAL] {signal_type} on {path}: {value_str}"
        print_and_log(message, log_level)
    
    def _execute_save(self, action: SignalAction, signal_data: Dict[str, Any]) -> None:
        """Execute a SAVE action.
        
        Args:
            action: Action to execute
            signal_data: Signal data to save
        """
        file_format = action.parameters.get('format', 'csv')
        filename = action.parameters.get('file', f"signals_{datetime.now().strftime('%Y%m%d')}.{file_format}")
        filepath = os.path.join(self.output_dir, filename)
        
        with self._lock:
            if file_format == 'csv':
                self._save_csv(filepath, signal_data)
            elif file_format == 'json':
                self._save_json(filepath, signal_data)
    
    def _save_csv(self, filepath: str, signal_data: Dict[str, Any]) -> None:
        """Save signal data to a CSV file.
        
        Args:
            filepath: Path to the CSV file
            signal_data: Signal data to save
        """
        # Convert value to string if it's bytes
        value = signal_data.get('value', None)
        if isinstance(value, bytes):
            signal_data['value'] = value.hex()
        
        # Add timestamp if not present
        if 'timestamp' not in signal_data:
            signal_data['timestamp'] = datetime.now().isoformat()
        
        # Get or create CSV writer
        if filepath not in self._csv_writers:
            # Check if file exists to determine if we need to write headers
            file_exists = os.path.exists(filepath)
            
            # Open file in append mode
            f = open(filepath, 'a', newline='')
            self._file_handles[filepath] = f
            writer = csv.writer(f)
            self._csv_writers[filepath] = writer
            
            # Write headers if new file
            if not file_exists:
                headers = ['timestamp', 'signal_type', 'path', 'interface', 
                          'property_name', 'value', 'device_mac', 
                          'service_uuid', 'char_uuid']
                writer.writerow(headers)
        
        # Get writer
        writer = self._csv_writers[filepath]
        
        # Write data row
        row = [
            signal_data.get('timestamp', datetime.now().isoformat()),
            signal_data.get('signal_type', ''),
            signal_data.get('path', ''),
            signal_data.get('interface', ''),
            signal_data.get('property_name', ''),
            signal_data.get('value', ''),
            signal_data.get('device_mac', ''),
            signal_data.get('service_uuid', ''),
            signal_data.get('char_uuid', '')
        ]
        writer.writerow(row)
        self._file_handles[filepath].flush()
    
    def _save_json(self, filepath: str, signal_data: Dict[str, Any]) -> None:
        """Save signal data to a JSON file.
        
        Args:
            filepath: Path to the JSON file
            signal_data: Signal data to save
        """
        # Convert value to string if it's bytes
        value = signal_data.get('value', None)
        if isinstance(value, bytes):
            signal_data['value'] = value.hex()
        
        # Add timestamp if not present
        if 'timestamp' not in signal_data:
            signal_data['timestamp'] = datetime.now().isoformat()
        
        # Load existing data if file exists
        data = []
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                # File exists but is not valid JSON, start fresh
                data = []
        
        # Append new data
        data.append(signal_data)
        
        # Write back to file
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _execute_callback(self, action: SignalAction, signal_data: Dict[str, Any]) -> None:
        """Execute a CALLBACK action.
        
        Args:
            action: Action to execute
            signal_data: Signal data to pass to the callback
        """
        callback_name = action.name
        
        with self._lock:
            if callback_name in self._callbacks:
                try:
                    self._callbacks[callback_name](signal_data)
                except Exception as e:
                    print_and_log(f"[ERROR] Callback '{callback_name}' failed: {e}", LOG__DEBUG)
    
    def _execute_db_store(self, action: SignalAction, signal_data: Dict[str, Any]) -> None:
        """Execute a DB_STORE action.
        
        Args:
            action: Action to execute
            signal_data: Signal data to store in the database
        """
        # Import here to avoid circular imports
        from bleep.core.observations import store_signal_capture
        
        try:
            store_signal_capture(signal_data)
        except Exception as e:
            print_and_log(f"[ERROR] Failed to store signal in database: {e}", LOG__DEBUG)
    
    def _execute_forward(self, action: SignalAction, signal_data: Dict[str, Any]) -> None:
        """Execute a FORWARD action.
        
        Args:
            action: Action to execute
            signal_data: Signal data to forward
        """
        # This would typically forward the signal to another system
        # For now, just log that we would forward it
        target = action.parameters.get('target', 'unknown')
        print_and_log(f"[FORWARD] Would forward signal to {target}", LOG__DEBUG)
    
    def _execute_transform(self, action: SignalAction, signal_data: Dict[str, Any]) -> None:
        """Execute a TRANSFORM action.
        
        Args:
            action: Action to execute
            signal_data: Signal data to transform
        """
        # This would typically transform the signal and then perform another action
        # For now, just log that we would transform it
        transform_type = action.parameters.get('type', 'unknown')
        print_and_log(f"[TRANSFORM] Would apply {transform_type} transformation", LOG__DEBUG)
    
    def close(self) -> None:
        """Close all open file handles."""
        with self._lock:
            for f in self._file_handles.values():
                try:
                    f.close()
                except Exception:
                    pass
            self._file_handles.clear()
            self._csv_writers.clear()


class SignalRouter:
    """Routes signals based on configured filters to appropriate actions."""
    
    def __init__(self, config: Optional[SignalCaptureConfig] = None):
        """Initialize the signal router.
        
        Args:
            config: Signal capture configuration. If None, a default config is created.
        """
        from bleep.signals.capture_config import create_default_config
        
        self.config = config or create_default_config()
        self.action_executor = ActionExecutor()
        
        # Active routes (enabled routes from config)
        self.active_routes = [r for r in self.config.routes if r.enabled]
        
        # Lock for thread safety
        self._lock = threading.Lock()
    
    def reload_config(self, config: SignalCaptureConfig) -> None:
        """Reload the configuration.
        
        Args:
            config: New configuration to use
        """
        with self._lock:
            self.config = config
            self.active_routes = [r for r in self.config.routes if r.enabled]
    
    def register_callback(self, name: str, callback: Callable) -> None:
        """Register a callback function.
        
        Args:
            name: Name of the callback
            callback: Function to call when an action with this name is executed
        """
        self.action_executor.register_callback(name, callback)
    
    def process_signal(self, signal_type: SignalType, path: str, 
                      interface: Optional[str] = None, 
                      property_name: Optional[str] = None,
                      value: Any = None, 
                      device_mac: Optional[str] = None,
                      service_uuid: Optional[str] = None, 
                      char_uuid: Optional[str] = None) -> None:
        """Process a signal through the router.
        
        Args:
            signal_type: Type of signal
            path: D-Bus path of the object
            interface: D-Bus interface (optional)
            property_name: Name of the property (for property changes)
            value: Signal value
            device_mac: Device MAC address (optional)
            service_uuid: Service UUID (optional)
            char_uuid: Characteristic UUID (optional)
        """
        # Prepare signal data dictionary
        signal_data = {
            'signal_type': signal_type.value,
            'path': path,
            'interface': interface,
            'property_name': property_name,
            'value': value,
            'device_mac': device_mac,
            'service_uuid': service_uuid,
            'char_uuid': char_uuid,
            'timestamp': datetime.now().isoformat()
        }
        
        # Find matching routes
        matching_routes = []
        with self._lock:
            for route in self.active_routes:
                if route.filter.matches(
                    signal_type=signal_type,
                    path=path,
                    interface=interface,
                    property_name=property_name,
                    value=value,
                    device_mac=device_mac,
                    service_uuid=service_uuid,
                    char_uuid=char_uuid
                ):
                    matching_routes.append(route)
        
        # Execute actions for matching routes
        for route in matching_routes:
            for action in route.actions:
                self.action_executor.execute(action, signal_data)
    
    def process_signal_capture(self, capture: SignalCapture) -> None:
        """Process a SignalCapture object.
        
        Args:
            capture: Signal capture object
        """
        # Extract signal type
        if capture.source == 'notification':
            signal_type = SignalType.NOTIFICATION
        elif capture.source == 'read':
            signal_type = SignalType.READ
        elif capture.source == 'write':
            signal_type = SignalType.WRITE
        elif capture.signal_name == 'PropertiesChanged':
            signal_type = SignalType.PROPERTY_CHANGE
        else:
            signal_type = SignalType.ANY
        
        # Extract value and property name
        value = None
        property_name = None
        
        if signal_type == SignalType.PROPERTY_CHANGE and len(capture.args) >= 2:
            # PropertiesChanged args: (interface, changed_properties, invalidated)
            changed_props = capture.args[1]
            # Use first property found
            if changed_props and isinstance(changed_props, dict):
                for prop_name, prop_value in changed_props.items():
                    property_name = prop_name
                    value = prop_value
                    break
        elif len(capture.args) > 0:
            # For other signals, use the first argument as the value
            value = capture.args[0]
        
        # Process the signal
        self.process_signal(
            signal_type=signal_type,
            path=capture.path,
            interface=capture.interface,
            property_name=property_name,
            value=value
        )
    
    def close(self) -> None:
        """Close the router and release resources."""
        self.action_executor.close()


# Global router instance
_global_router: Optional[SignalRouter] = None


def get_router() -> SignalRouter:
    """Get the global signal router instance.
    
    Returns:
        Global signal router
    """
    global _global_router
    if _global_router is None:
        _global_router = SignalRouter()
    return _global_router


def set_router(router: SignalRouter) -> None:
    """Set the global signal router.
    
    Args:
        router: Signal router to use
    """
    global _global_router
    _global_router = router


def process_signal(signal_type: SignalType, path: str, 
                  interface: Optional[str] = None, 
                  property_name: Optional[str] = None,
                  value: Any = None, 
                  device_mac: Optional[str] = None,
                  service_uuid: Optional[str] = None, 
                  char_uuid: Optional[str] = None) -> None:
    """Process a signal using the global router.
    
    Args:
        signal_type: Type of signal
        path: D-Bus path of the object
        interface: D-Bus interface (optional)
        property_name: Name of the property (for property changes)
        value: Signal value
        device_mac: Device MAC address (optional)
        service_uuid: Service UUID (optional)
        char_uuid: Characteristic UUID (optional)
    """
    router = get_router()
    router.process_signal(
        signal_type=signal_type,
        path=path,
        interface=interface,
        property_name=property_name,
        value=value,
        device_mac=device_mac,
        service_uuid=service_uuid,
        char_uuid=char_uuid
    )


def process_signal_capture(capture: SignalCapture) -> None:
    """Process a SignalCapture object using the global router.
    
    Args:
        capture: Signal capture object
    """
    router = get_router()
    router.process_signal_capture(capture)


def register_callback(name: str, callback: Callable) -> None:
    """Register a callback with the global router.
    
    Args:
        name: Name of the callback
        callback: Function to call
    """
    router = get_router()
    router.register_callback(name, callback)


