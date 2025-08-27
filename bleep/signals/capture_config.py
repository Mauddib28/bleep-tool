"""Signal capture configuration for BLEEP.

This module provides classes and functions for configuring signal capture, 
filtering, and routing in a structured and persistent way.
"""

import enum
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Callable, Pattern
import re

from bleep.core.log import print_and_log, LOG__DEBUG

# Default location for signal configuration files
DEFAULT_CONFIG_DIR = os.path.expanduser("~/.bleep/signals")


class SignalType(enum.Enum):
    """Types of signals that can be captured."""
    NOTIFICATION = "notification"
    INDICATION = "indication"
    PROPERTY_CHANGE = "property_change"
    READ = "read"
    WRITE = "write"
    ANY = "any"


class ActionType(enum.Enum):
    """Types of actions that can be performed on captured signals."""
    LOG = "log"
    SAVE = "save"
    CALLBACK = "callback"
    DB_STORE = "db_store"
    FORWARD = "forward"
    TRANSFORM = "transform"


@dataclass
class SignalFilter:
    """Filter for signals based on various criteria."""
    signal_type: Optional[SignalType] = None
    device_mac: Optional[str] = None
    service_uuid: Optional[str] = None
    char_uuid: Optional[str] = None
    path_pattern: Optional[str] = None
    property_name: Optional[str] = None
    value_pattern: Optional[str] = None
    min_value_length: Optional[int] = None
    max_value_length: Optional[int] = None
    
    # Compiled regex patterns (not serialized)
    _path_regex: Optional[Pattern] = field(default=None, repr=False)
    _value_regex: Optional[Pattern] = field(default=None, repr=False)
    
    def __post_init__(self):
        """Compile regex patterns after initialization."""
        if self.path_pattern:
            self._path_regex = re.compile(self.path_pattern)
        if self.value_pattern:
            self._value_regex = re.compile(self.value_pattern)
    
    def matches(self, signal_type: SignalType, path: str, 
               interface: str = None, property_name: str = None,
               value: Any = None, device_mac: str = None,
               service_uuid: str = None, char_uuid: str = None) -> bool:
        """Check if a signal matches this filter.
        
        Args:
            signal_type: Type of signal
            path: D-Bus path of the object
            interface: D-Bus interface (optional)
            property_name: Name of the property (for property changes)
            value: Signal value
            device_mac: Device MAC address (optional)
            service_uuid: Service UUID (optional)
            char_uuid: Characteristic UUID (optional)
            
        Returns:
            True if the signal matches all specified criteria, False otherwise
        """
        # Check signal type
        if self.signal_type and self.signal_type != SignalType.ANY and self.signal_type != signal_type:
            return False
        
        # Check device MAC
        if self.device_mac and device_mac and self.device_mac.lower() != device_mac.lower():
            return False
        
        # Check service UUID
        if self.service_uuid and service_uuid and self.service_uuid.lower() != service_uuid.lower():
            return False
        
        # Check characteristic UUID
        if self.char_uuid and char_uuid and self.char_uuid.lower() != char_uuid.lower():
            return False
        
        # Check path pattern
        if self._path_regex and not self._path_regex.search(path):
            return False
        
        # Check property name
        if self.property_name and property_name and self.property_name != property_name:
            return False
        
        # Check value pattern and length constraints
        if value is not None:
            # Convert value to string for pattern matching if it's bytes
            value_str = value.hex() if isinstance(value, bytes) else str(value)
            
            if self._value_regex and not self._value_regex.search(value_str):
                return False
            
            if self.min_value_length is not None:
                if isinstance(value, bytes) and len(value) < self.min_value_length:
                    return False
                elif isinstance(value, str) and len(value) < self.min_value_length:
                    return False
            
            if self.max_value_length is not None:
                if isinstance(value, bytes) and len(value) > self.max_value_length:
                    return False
                elif isinstance(value, str) and len(value) > self.max_value_length:
                    return False
        
        # All checks passed
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        # Remove non-serializable fields
        result.pop('_path_regex', None)
        result.pop('_value_regex', None)
        # Convert enum to string
        if result['signal_type'] is not None:
            result['signal_type'] = result['signal_type'].value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SignalFilter':
        """Create from dictionary."""
        # Convert string to enum
        if 'signal_type' in data and data['signal_type'] is not None:
            data['signal_type'] = SignalType(data['signal_type'])
        return cls(**data)


@dataclass
class SignalAction:
    """Action to perform when a signal matches a filter."""
    action_type: ActionType
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        # Convert enum to string
        result['action_type'] = result['action_type'].value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SignalAction':
        """Create from dictionary."""
        # Convert string to enum
        if 'action_type' in data:
            data['action_type'] = ActionType(data['action_type'])
        return cls(**data)


@dataclass
class SignalRoute:
    """Route that connects a filter to one or more actions."""
    name: str
    description: str
    filter: SignalFilter
    actions: List[SignalAction]
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'description': self.description,
            'filter': self.filter.to_dict(),
            'actions': [action.to_dict() for action in self.actions],
            'enabled': self.enabled
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SignalRoute':
        """Create from dictionary."""
        filter_data = data.pop('filter')
        actions_data = data.pop('actions')
        
        return cls(
            **data,
            filter=SignalFilter.from_dict(filter_data),
            actions=[SignalAction.from_dict(action) for action in actions_data]
        )


@dataclass
class SignalCaptureConfig:
    """Configuration for signal capture system."""
    name: str
    description: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0"
    routes: List[SignalRoute] = field(default_factory=list)
    
    def add_route(self, route: SignalRoute) -> None:
        """Add a route to the configuration."""
        self.routes.append(route)
        self.updated_at = datetime.now().isoformat()
    
    def remove_route(self, route_name: str) -> bool:
        """Remove a route from the configuration.
        
        Args:
            route_name: Name of the route to remove
            
        Returns:
            True if the route was found and removed, False otherwise
        """
        initial_count = len(self.routes)
        self.routes = [r for r in self.routes if r.name != route_name]
        
        if len(self.routes) < initial_count:
            self.updated_at = datetime.now().isoformat()
            return True
        return False
    
    def get_route(self, route_name: str) -> Optional[SignalRoute]:
        """Get a route by name.
        
        Args:
            route_name: Name of the route to get
            
        Returns:
            The route if found, None otherwise
        """
        for route in self.routes:
            if route.name == route_name:
                return route
        return None
    
    def enable_route(self, route_name: str) -> bool:
        """Enable a route.
        
        Args:
            route_name: Name of the route to enable
            
        Returns:
            True if the route was found and enabled, False otherwise
        """
        route = self.get_route(route_name)
        if route and not route.enabled:
            route.enabled = True
            self.updated_at = datetime.now().isoformat()
            return True
        return False
    
    def disable_route(self, route_name: str) -> bool:
        """Disable a route.
        
        Args:
            route_name: Name of the route to disable
            
        Returns:
            True if the route was found and disabled, False otherwise
        """
        route = self.get_route(route_name)
        if route and route.enabled:
            route.enabled = False
            self.updated_at = datetime.now().isoformat()
            return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'version': self.version,
            'routes': [route.to_dict() for route in self.routes]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SignalCaptureConfig':
        """Create from dictionary."""
        routes_data = data.pop('routes', [])
        
        config = cls(**data)
        config.routes = [SignalRoute.from_dict(route) for route in routes_data]
        
        return config


def _ensure_config_dir() -> str:
    """Ensure the configuration directory exists.
    
    Returns:
        Path to the configuration directory
    """
    os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)
    return DEFAULT_CONFIG_DIR


def save_config(config: SignalCaptureConfig, filename: Optional[str] = None) -> str:
    """Save a configuration to a file.
    
    Args:
        config: Configuration to save
        filename: Optional filename (without path). If not provided, a name is generated
                 from the configuration name.
                 
    Returns:
        Path to the saved file
    """
    config_dir = _ensure_config_dir()
    
    if filename is None:
        # Generate filename from config name
        safe_name = config.name.lower().replace(' ', '_')
        filename = f"{safe_name}.json"
    
    filepath = os.path.join(config_dir, filename)
    
    # Update the timestamp
    config.updated_at = datetime.now().isoformat()
    
    with open(filepath, 'w') as f:
        json.dump(config.to_dict(), f, indent=2)
    
    print_and_log(f"[*] Saved signal configuration to {filepath}", LOG__DEBUG)
    return filepath


def load_config(filename: str) -> SignalCaptureConfig:
    """Load a configuration from a file.
    
    Args:
        filename: Name of the file to load (can be with or without path)
        
    Returns:
        Loaded configuration
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file contains invalid JSON or configuration
    """
    # Check if the filename includes a path
    if os.path.dirname(filename):
        filepath = filename
    else:
        config_dir = _ensure_config_dir()
        filepath = os.path.join(config_dir, filename)
    
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Configuration file not found: {filepath}")
    
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        return SignalCaptureConfig.from_dict(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")
    except Exception as e:
        raise ValueError(f"Error loading configuration: {e}")


def list_configs() -> List[str]:
    """List available configuration files.
    
    Returns:
        List of configuration filenames
    """
    config_dir = _ensure_config_dir()
    return [f for f in os.listdir(config_dir) if f.endswith('.json')]


def create_default_config() -> SignalCaptureConfig:
    """Create a default configuration with some example routes.
    
    Returns:
        Default configuration
    """
    config = SignalCaptureConfig(
        name="Default Signal Configuration",
        description="Default configuration with example routes"
    )
    
    # Example route 1: Log all notifications
    filter1 = SignalFilter(signal_type=SignalType.NOTIFICATION)
    action1 = SignalAction(action_type=ActionType.LOG, name="log_notifications")
    route1 = SignalRoute(
        name="log_all_notifications",
        description="Log all notification signals",
        filter=filter1,
        actions=[action1]
    )
    config.add_route(route1)
    
    # Example route 2: Save battery level changes
    filter2 = SignalFilter(
        signal_type=SignalType.PROPERTY_CHANGE,
        property_name="Battery",
        path_pattern=r"/org/bluez/hci\d+/dev_[A-F0-9_]+$"
    )
    action2 = SignalAction(
        action_type=ActionType.SAVE,
        name="save_battery_levels",
        parameters={"file": "battery_levels.csv"}
    )
    route2 = SignalRoute(
        name="monitor_battery_levels",
        description="Save battery level changes to CSV",
        filter=filter2,
        actions=[action2]
    )
    config.add_route(route2)
    
    return config


