# Signal Capture System

The Signal Capture System is a powerful feature introduced in BLEEP v2.2.0 that allows comprehensive tracking and processing of Bluetooth events, particularly characteristic operations (reads, writes, notifications). This major update enables full timeline tracking of all characteristic interactions. This document explains how the system works and how it integrates with the observation database.

## Overview

The Signal Capture System provides a structured way to:

1. Capture Bluetooth events (characteristic reads, writes, notifications, property changes)
2. Filter events based on various criteria (device, service, characteristic, etc.)
3. Process events through configurable routes (log, save to file, store in database)
4. Extend functionality through custom callbacks

## Architecture

The system consists of several key components:

### 1. Signal Types

Defined in `bleep/signals/capture_config.py`:
- `NOTIFICATION` - Characteristic notifications
- `INDICATION` - Characteristic indications
- `PROPERTY_CHANGE` - D-Bus property changes
- `READ` - Characteristic read operations
- `WRITE` - Characteristic write operations
- `ANY` - Matches any signal type

### 2. Signal Filters

Filters allow selecting specific signals based on criteria:
- Signal type
- Device MAC address
- Service UUID
- Characteristic UUID
- Path pattern (regex)
- Property name
- Value pattern (regex)
- Value length constraints

### 3. Signal Actions

Actions define what happens when a signal matches a filter:
- `LOG` - Log the signal to console
- `SAVE` - Save the signal to a file (CSV or JSON)
- `CALLBACK` - Call a registered function
- `DB_STORE` - Store the signal in the observation database
- `FORWARD` - Forward the signal to another system
- `TRANSFORM` - Transform the signal before further processing

### 4. Signal Routes

Routes connect filters to actions:
- Each route has a name, description, filter, and list of actions
- Routes can be enabled/disabled
- Multiple routes can match the same signal

### 5. Signal Router

The router manages the signal flow:
- Maintains active routes
- Processes incoming signals
- Executes actions for matching routes

## Integration with BlueZ

The Signal Capture System integrates with BlueZ signals through:

1. `integrate_with_bluez_signals()` - Hooks into BlueZ signal handling
2. `patch_signal_capture_class()` - Ensures all signal captures are processed

These functions are called during application startup in `bleep/__init__.py`.

## Database Integration

When a characteristic operation occurs:

1. The operation is captured as a signal
2. The signal is processed through the router
3. If a route with a `DB_STORE` action matches, the signal is stored in the database
4. The `store_signal_capture()` function in `bleep/core/observations.py` handles the database insertion
5. For characteristic operations, values are stored in the `char_history` table

## Default Configuration

The default configuration includes routes for:

1. Logging all notifications
2. Saving battery level changes to CSV
3. Storing all characteristic read operations in the database
4. Storing all characteristic write operations in the database
5. Storing all notifications in the database

## CTF Module Integration

The CTF module uses direct D-Bus access for some operations, which initially bypassed the signal system. This has been fixed by:

1. Manually emitting signals for read operations
2. Directly inserting into the database as a fallback mechanism
3. Adding robust error handling and debugging

## Usage Examples

### Viewing Characteristic History

To view the history of characteristic operations for a device:

```bash
bleep db timeline cc:50:e3:b6:bc:a6
```

This will show a timeline of all characteristic operations (reads, writes, notifications) for the specified device.

### Filtering by Service or Characteristic

To filter the timeline by service or characteristic UUID:

```bash
bleep db timeline cc:50:e3:b6:bc:a6 --service 000000ff-0000-1000-8000-00805f9b34fb
bleep db timeline cc:50:e3:b6:bc:a6 --char 0000ff0b-0000-1000-8000-00805f9b34fb
```

## Troubleshooting

If characteristic operations are not showing up in the timeline:

1. Ensure the signal system is properly initialized
2. Check if the operation is using direct D-Bus access (may need manual signal emission)
3. Verify the database connection is working correctly
4. Check if the device MAC address is correctly normalized (lowercase)
5. Ensure the service and characteristic UUIDs are correctly formatted

## Future Enhancements

Planned improvements to the Signal Capture System:

1. Custom signal filter creation via CLI
2. Real-time signal visualization
3. Enhanced signal transformation capabilities
4. Integration with external analysis tools
5. Improved performance for high-volume signals