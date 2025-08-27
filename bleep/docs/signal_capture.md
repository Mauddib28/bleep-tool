# Signal Capture System

The Signal Capture System provides a structured approach to capturing, filtering, and processing Bluetooth signals (notifications, indications, property changes) with configurable routing and persistent storage of configurations.

## Overview

The Signal Capture System consists of:

1. **Configuration** - Define what signals to capture and what actions to perform
2. **Routing** - Route signals to appropriate actions based on filters
3. **Actions** - Execute actions on captured signals (logging, saving, callbacks)
4. **Integration** - Integration with the existing BlueZ signals system
5. **CLI** - Command-line interface for managing configurations

## Signal Types

The system can capture the following types of signals:

- **Notifications** - GATT characteristic notifications
- **Indications** - GATT characteristic indications
- **Property Changes** - D-Bus property changes
- **Read Events** - Characteristic read operations
- **Write Events** - Characteristic write operations

## Configuration

Signal capture configurations are defined using a hierarchical structure:

1. **SignalCaptureConfig** - Top-level configuration containing routes
2. **SignalRoute** - Route connecting a filter to one or more actions
3. **SignalFilter** - Filter for signals based on various criteria
4. **SignalAction** - Action to perform when a signal matches a filter

### Example Configuration

```python
from bleep.signals import (
    SignalCaptureConfig, SignalRoute, SignalFilter, SignalAction,
    SignalType, ActionType
)

# Create a filter for battery level notifications
battery_filter = SignalFilter(
    signal_type=SignalType.NOTIFICATION,
    service_uuid="180f",  # Battery Service
    char_uuid="2a19"      # Battery Level Characteristic
)

# Create actions for logging and saving
log_action = SignalAction(
    action_type=ActionType.LOG,
    name="log_battery_levels"
)

save_action = SignalAction(
    action_type=ActionType.SAVE,
    name="save_battery_levels",
    parameters={"file": "battery_levels.csv", "format": "csv"}
)

# Create a route connecting the filter to the actions
battery_route = SignalRoute(
    name="battery_monitoring",
    description="Monitor battery level notifications",
    filter=battery_filter,
    actions=[log_action, save_action]
)

# Create the configuration
config = SignalCaptureConfig(
    name="Battery Monitoring",
    description="Configuration for monitoring battery levels"
)
config.add_route(battery_route)

# Save the configuration
from bleep.signals import save_config
save_config(config)
```

## Filtering

Signals can be filtered based on various criteria:

- **Signal Type** - Type of signal (notification, indication, property change, read, write)
- **Device MAC** - MAC address of the device
- **Service UUID** - UUID of the service
- **Characteristic UUID** - UUID of the characteristic
- **Path Pattern** - Regular expression pattern for D-Bus path
- **Property Name** - Name of the property (for property changes)
- **Value Pattern** - Regular expression pattern for signal value
- **Value Length** - Minimum and maximum length of the signal value

## Actions

The following actions can be performed on captured signals:

- **LOG** - Log the signal to the console
- **SAVE** - Save the signal to a file (CSV or JSON)
- **CALLBACK** - Call a registered callback function
- **DB_STORE** - Store the signal in the observation database
- **FORWARD** - Forward the signal to another system
- **TRANSFORM** - Transform the signal and perform another action

## CLI Usage

The Signal Capture System provides a command-line interface for managing configurations:

```bash
# List available configurations
python -m bleep.cli signal-config list

# Create a new configuration
python -m bleep.cli signal-config create my-config --description "My signal configuration"

# Create a default configuration with example routes
python -m bleep.cli signal-config create my-config --default

# Show a configuration
python -m bleep.cli signal-config show my-config.json

# Add a route to a configuration
python -m bleep.cli signal-config add-route my-config.json battery-monitor \
    --signal-type notification \
    --service-uuid 180f \
    --char-uuid 2a19 \
    --action log \
    --action-name log_battery_levels

# Remove a route from a configuration
python -m bleep.cli signal-config remove-route my-config.json battery-monitor

# Enable/disable a route
python -m bleep.cli signal-config enable-route my-config.json battery-monitor
python -m bleep.cli signal-config disable-route my-config.json battery-monitor

# Import/export configurations
python -m bleep.cli signal-config export my-config.json my-config-export.json
python -m bleep.cli signal-config import my-config-export.json --name imported-config
```

## Programmatic Usage

The Signal Capture System can also be used programmatically:

```python
from bleep.signals import (
    get_router, process_signal, SignalType, register_callback
)

# Process a signal
process_signal(
    signal_type=SignalType.NOTIFICATION,
    path="/org/bluez/hci0/dev_00_11_22_33_44_55/service0001/char0002",
    value=b"\x01\x02\x03",
    device_mac="00:11:22:33:44:55",
    service_uuid="180f",
    char_uuid="2a19"
)

# Register a callback
def my_callback(signal_data):
    print(f"Received signal: {signal_data}")

register_callback("my_callback", my_callback)
```

## Integration with Existing System

The Signal Capture System integrates with the existing BlueZ signals system:

```python
from bleep.signals import integrate_with_bluez_signals
from bleep.dbuslayer.signals import system_dbus__bluez_signals

# Create a signals instance
signals = system_dbus__bluez_signals()

# Integrate with the Signal Capture System
integrate_with_bluez_signals(signals)
```

### Legacy Method Support

For backward compatibility, the Signal Capture System includes support for the legacy `capture_and_act__emittion__gatt_characteristic` method:

```python
from bleep.dbuslayer.signals import system_dbus__bluez_signals

# Create a signals instance
signals = system_dbus__bluez_signals()

# Define a callback function
def notification_callback(path, value):
    print(f"Received notification from {path}: {value.hex()}")

# Set up notification capture
signals.capture_and_act__emittion__gatt_characteristic(device, "2a19", notification_callback)
```

This method is provided for backward compatibility with existing code that uses the legacy monolith implementation. For new code, it's recommended to use the new Signal Capture System API.

## Common Signal Capture Patterns

### 1. Battery Level Monitoring

Monitor battery level notifications from devices:

```python
from bleep.signals import (
    SignalCaptureConfig, SignalRoute, SignalFilter, SignalAction,
    SignalType, ActionType, save_config
)

# Create a filter for battery level notifications
battery_filter = SignalFilter(
    signal_type=SignalType.NOTIFICATION,
    service_uuid="180f",  # Battery Service
    char_uuid="2a19"      # Battery Level Characteristic
)

# Create actions for logging and saving
log_action = SignalAction(
    action_type=ActionType.LOG,
    name="log_battery_levels"
)

save_action = SignalAction(
    action_type=ActionType.SAVE,
    name="save_battery_levels",
    parameters={"file": "battery_levels.csv", "format": "csv"}
)

# Create a route connecting the filter to the actions
battery_route = SignalRoute(
    name="battery_monitoring",
    description="Monitor battery level notifications",
    filter=battery_filter,
    actions=[log_action, save_action]
)

# Create the configuration
config = SignalCaptureConfig(
    name="Battery Monitoring",
    description="Configuration for monitoring battery levels"
)
config.add_route(battery_route)

# Save the configuration
save_config(config)
```

### 2. Device Connection State Monitoring

Monitor device connection state changes:

```python
# Create a filter for device connection state changes
connection_filter = SignalFilter(
    signal_type=SignalType.PROPERTY_CHANGE,
    property_name="Connected",
    path_pattern=r"/org/bluez/hci\d+/dev_[A-F0-9_]+"
)

# Create an action for logging
log_action = SignalAction(
    action_type=ActionType.LOG,
    name="log_connection_changes"
)

# Create a route
connection_route = SignalRoute(
    name="connection_monitoring",
    description="Monitor device connection state changes",
    filter=connection_filter,
    actions=[log_action]
)

# Add to configuration
config.add_route(connection_route)
```

### 3. Heart Rate Monitoring

Monitor heart rate measurements:

```python
# Create a filter for heart rate measurements
hr_filter = SignalFilter(
    signal_type=SignalType.NOTIFICATION,
    service_uuid="180d",  # Heart Rate Service
    char_uuid="2a37"      # Heart Rate Measurement Characteristic
)

# Create actions for logging and database storage
log_action = SignalAction(
    action_type=ActionType.LOG,
    name="log_heart_rate"
)

db_action = SignalAction(
    action_type=ActionType.DB_STORE,
    name="store_heart_rate"
)

# Create a route
hr_route = SignalRoute(
    name="heart_rate_monitoring",
    description="Monitor heart rate measurements",
    filter=hr_filter,
    actions=[log_action, db_action]
)

# Add to configuration
config.add_route(hr_route)
```

### 4. Debugging All Signals

Capture all signals for debugging:

```python
# Create a filter for all signals
debug_filter = SignalFilter(
    signal_type=SignalType.ANY
)

# Create an action for logging
log_action = SignalAction(
    action_type=ActionType.LOG,
    name="log_all_signals",
    parameters={"level": "DEBUG"}
)

# Create a route
debug_route = SignalRoute(
    name="debug_all",
    description="Debug all signals",
    filter=debug_filter,
    actions=[log_action]
)

# Add to configuration
config.add_route(debug_route)
```

### 5. Custom Signal Processing

Process signals with a custom callback:

```python
# Register a callback
from bleep.signals import register_callback

def process_heart_rate(signal_data):
    # Extract heart rate value from the notification
    value = signal_data.get("value")
    if isinstance(value, bytes) and len(value) >= 2:
        # Heart Rate Measurement format: flags (1 byte) + heart rate (1 byte)
        flags = value[0]
        if flags & 0x01:  # Heart rate value format bit (0 = uint8, 1 = uint16)
            hr = int.from_bytes(value[1:3], byteorder="little")
        else:
            hr = value[1]
        print(f"Heart rate: {hr} bpm")

register_callback("process_heart_rate", process_heart_rate)

# Create a filter for heart rate measurements
hr_filter = SignalFilter(
    signal_type=SignalType.NOTIFICATION,
    service_uuid="180d",  # Heart Rate Service
    char_uuid="2a37"      # Heart Rate Measurement Characteristic
)

# Create a callback action
callback_action = SignalAction(
    action_type=ActionType.CALLBACK,
    name="process_heart_rate"
)

# Create a route
hr_route = SignalRoute(
    name="heart_rate_processing",
    description="Process heart rate measurements",
    filter=hr_filter,
    actions=[callback_action]
)

# Add to configuration
config.add_route(hr_route)
```

## Best Practices

1. **Use Specific Filters** - Be as specific as possible in your filters to avoid capturing unnecessary signals.
2. **Limit Actions** - Avoid performing too many actions on each signal, especially for high-frequency signals.
3. **Use Appropriate Storage** - Choose the appropriate storage format (CSV, JSON, database) based on your needs.
4. **Monitor Performance** - Monitor the performance of your signal capture system, especially when capturing high-frequency signals.
5. **Disable Unused Routes** - Disable routes that are not currently needed to improve performance.
6. **Use Callbacks for Complex Processing** - Use callbacks for complex processing rather than trying to do everything in the action.
7. **Organize Configurations** - Organize your configurations by device type, signal type, or use case.
8. **Document Configurations** - Document your configurations with clear names and descriptions.
