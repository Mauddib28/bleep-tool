# Signal Capture System

The Signal Capture System is a powerful feature of BLEEP (v3.0.0) that allows comprehensive tracking and processing of Bluetooth events, particularly characteristic operations (reads, writes, notifications). It enables full timeline tracking of all characteristic interactions. This document explains how the system works and how it integrates with the observation database.

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
- `DEVICE_CONNECT` - Device connection events (v3.0.0)
- `DEVICE_DISCONNECT` - Device disconnection events (v3.0.0)
- `PAIR_START` - Pairing initiated events (v3.0.0)
- `PAIR_COMPLETE` - Pairing completed events (v3.0.0)
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

The Signal Capture System integrates with BlueZ signals through two functions,
with **different lifecycles**:

1. `patch_signal_capture_class()` - Patches the `SignalCapture` dataclass so all
   signal captures are processed. Runs **eagerly** on package import
   (`bleep/__init__.py` ~34); it is safe to run early because it does not touch
   D-Bus.
2. `integrate_with_bluez_signals()` - Hooks into live BlueZ D-Bus signal
   handling. This does **not** run at startup. It is deferred (lazy) and invoked
   exactly once on first actual D-Bus device use via `_ensure_bluez_signals()`
   (`bleep/__init__.py` ~39-45, called from `bleep/dbuslayer/device_le.py` ~60).
   The deferral avoids a circular-import problem caused by `dbus.SystemBus()`
   running while `device_le.py` is still being imported.

## Database Integration

When a characteristic operation occurs:

1. The operation is captured as a signal
2. The signal is processed through the router
3. If a route with a `DB_STORE` action matches, the signal is stored in the database
4. The `store_signal_capture()` function in `bleep/core/observations/_signals.py` handles the database insertion
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
4. Check if the device MAC address is correctly normalized (uppercase)
5. Ensure the service and characteristic UUIDs are correctly formatted

## User Callbacks (v3.0.0)

The `BleepCallback` system lets users create custom callbacks that can be
registered with the signal router.

> **Callbacks are NOT auto-loaded.** `load_callbacks()` is defined and exported
> in `bleep/callbacks/__init__.py`, but it is **never called anywhere** in the
> package — nothing invokes it on import or startup. To register your callbacks
> you must call `load_callbacks()` yourself (e.g. from a script or an
> interactive session). Only then are the callbacks discovered and wired to the
> router.

### Architecture

- **Base class**: `bleep/callbacks/base.py` — `BleepCallback` ABC with `name`, `trigger` (a `SignalType`), `execute(context)`, `on_load()`, `on_unload()`.
- **Loader (opt-in, manual)**: `bleep/callbacks/__init__.py` — `load_callbacks(directory)` scans `~/.config/bleep/callbacks/` (`DEFAULT_CALLBACK_DIR`, default) for `.py` files containing `BleepCallback` subclasses, instantiates each, and registers a handler with the signal router via `register_callback()` (`_register_all`). If `trigger` is not `ANY`, only matching `signal_type` events are dispatched. This function must be **called explicitly** — it does not run on its own.
- **Example callbacks**: `bleep/callbacks/examples/log_all_notifications.py` (logs all BLE notifications), `pair_event_logger.py` (logs `PAIR_START`/`PAIR_COMPLETE` events).

### Creating a Callback

Place a `.py` file in `~/.config/bleep/callbacks/`:

```python
from bleep.callbacks.base import BleepCallback
from bleep.signals.capture_config import SignalType

class MyCallback(BleepCallback):
    name = "my_callback"
    trigger = SignalType.NOTIFICATION  # or ANY for all events

    def execute(self, context):
        print(f"Got: {context}")
```

Then load and register it explicitly (it is not picked up automatically):

```python
from bleep.callbacks import load_callbacks

load_callbacks()                       # scans DEFAULT_CALLBACK_DIR
# or: load_callbacks("/path/to/callbacks")
```

## Future Enhancements

Custom signal-filter/route creation via the CLI is **already implemented** —
see `bleep signal-config add-route` (filters for `--signal-type`, `--device-mac`,
`--service-uuid`, `--char-uuid`, `--path-pattern`, value length, etc.).

Planned improvements to the Signal Capture System:

1. Real-time signal visualization
2. Enhanced signal transformation capabilities (the `TRANSFORM` router action is currently a stub)
3. Integration with external analysis tools (the `FORWARD` router action is currently a stub)
4. Improved performance for high-volume signals