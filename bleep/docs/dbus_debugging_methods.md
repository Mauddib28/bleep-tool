# D-Bus + BlueZ API Debugging Methods

This document catalogs all **currently existing** methods in the BLEEP codebase that allow debugging of raw information being exchanged by the D-Bus + BlueZ API interactivity, excluding debug mode (which is documented separately in `debug_mode.md`).

## Summary

The BLEEP codebase provides multiple layers of debugging capabilities for D-Bus and BlueZ interactions:

1. **Signal Capture System** - Comprehensive signal monitoring and logging
2. **Signal Router** - Filter and process signals through configurable routes
3. **Logging Infrastructure** - Multiple log files for different event types
4. **BlueZ Service Monitor** - Service health monitoring and stall detection
5. **D-Bus Diagnostic Tools** - Health checks and performance monitoring
6. **Signal Mode** - Simple notification listener
7. **Connection Pool Logging** - Connection operation tracking

For debug mode capabilities, see [`debug_mode.md`](debug_mode.md).

---

## 1. Signal Capture System (`bleep/dbuslayer/signals.py`)

**Location**: `bleep/dbuslayer/signals.py`, `bleep/signals/`

**Purpose**: Comprehensive system for capturing, filtering, and processing D-Bus signals from BlueZ.

### Key Features:

#### Signal Capture
- **`SignalCapture`** class - Container for captured signal information
- Captures: `PropertiesChanged`, `InterfacesAdded`, `InterfacesRemoved`
- Tracks: interface, path, signal name, arguments, timestamp, source

#### Signal Correlation
- **`SignalCorrelator`** class - Correlates related signals from different sources
- Tracks signals within time windows (default: 1.0 second)
- Can find related signals by path relationships

#### Property Monitoring
- **`PropertyMonitor`** class - Monitors specific D-Bus properties for changes
- Maintains property history (last 10 values)
- Callback system for property changes

### Code References:

```31:39:bleep/dbuslayer/signals.py
@dataclass
class SignalCapture:
    """Container for captured signal information."""
    interface: str
    path: str
    signal_name: str
    args: Tuple[Any, ...]
    timestamp: float
    source: str = ""  # 'read', 'write', 'notification', 'property_change', etc.
```

```464:520:bleep/dbuslayer/signals.py
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
```

### Signal Registration Methods:

```197:229:bleep/dbuslayer/signals.py
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
```

---

## 2. Signal Router (`bleep/signals/router.py`)

**Location**: `bleep/signals/router.py`

**Purpose**: Routes captured signals through configurable filters and actions.

### Key Features:

#### Signal Filtering
- Filter by signal type, device MAC, service UUID, characteristic UUID
- Path pattern matching (regex)
- Property name filtering
- Value pattern matching (regex)
- Value length constraints

#### Signal Actions
- **LOG** - Log signals to console/files
- **SAVE** - Save signals to CSV/JSON files
- **CALLBACK** - Execute custom callbacks
- **DB_STORE** - Store signals in observation database
- **FORWARD** - Forward signals to external systems
- **TRANSFORM** - Transform signals before processing

### Code References:

```92:117:bleep/signals/router.py
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
```

---

## 3. Logging Infrastructure (`bleep/core/log.py`)

**Location**: `bleep/core/log.py`

**Purpose**: Centralized logging system with multiple log files for different event types.

### Log Files:

| Log Type | File Path | Purpose |
|----------|-----------|---------|
| `LOG__DEBUG` | `/tmp/bti__logging__debug.txt` | Debug-level messages |
| `LOG__GENERAL` | `/tmp/bti__logging__general.txt` | General messages |
| `LOG__ENUM` | `/tmp/bti__logging__enumeration.txt` | Enumeration operations |
| `LOG__USER` | `/tmp/bti__logging__usermode.txt` | User mode operations |
| `LOG__AGENT` | `/tmp/bti__logging__agent.txt` | Pairing agent operations |
| `LOG__DATABASE` | `/tmp/bti__logging__database.txt` | Database operations |

### Usage:

```python
from bleep.core.log import print_and_log, LOG__DEBUG

# Log to debug log
print_and_log("[DEBUG] D-Bus operation details", LOG__DEBUG)

# Log to general log (also prints to stdout)
print_and_log("[INFO] Operation completed", LOG__GENERAL)
```

### Code References:

```152:156:bleep/core/log.py
def print_and_log(output_string: str, log_type: str = LOG__GENERAL) -> None:
    """Print to stdout and log to the specified log type."""
    if log_type not in (LOG__DEBUG, LOG__ENUM):
        print(output_string)
    logging__log_event(log_type, output_string)
```

---

## 4. BlueZ Service Monitor (`bleep/dbuslayer/bluez_monitor.py`)

**Location**: `bleep/dbuslayer/bluez_monitor.py`

**Purpose**: Monitors BlueZ D-Bus service for availability, responsiveness, and restarts.

### Key Features:

#### Service Health Monitoring
- Heartbeat mechanism checking BlueZ service responsiveness
- Detects service stalls and restarts
- Tracks service availability changes
- Logs health check timing information

#### Callback System
- Register callbacks for service stalls
- Register callbacks for service restarts
- Register callbacks for availability changes

### Code References:

```146:183:bleep/dbuslayer/bluez_monitor.py
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
```

---

## 5. D-Bus Diagnostic Tool (`bleep/scripts/dbus_diagnostic.py`)

**Location**: `bleep/scripts/dbus_diagnostic.py`

**Purpose**: Diagnostic tool for testing and monitoring D-Bus reliability and performance.

### Key Features:

#### Health Checks
- BlueZ service health verification
- Device connection testing
- Connection pool testing
- Stress testing (multiple concurrent connections)

#### Monitoring
- Real-time BlueZ service monitoring
- Performance metrics collection
- Recovery strategy testing

### Usage:

```bash
# Check BlueZ health
python -m bleep.scripts.dbus_diagnostic --check-bluez

# Monitor BlueZ service
python -m bleep.scripts.dbus_diagnostic --monitor

# Test connection pool
python -m bleep.scripts.dbus_diagnostic --pool-test

# Stress test
python -m bleep.scripts.dbus_diagnostic --stress-test

# Test device connection
python -m bleep.scripts.dbus_diagnostic --device CC:50:E3:B6:BC:A6

# Run all diagnostics
python -m bleep.scripts.dbus_diagnostic --all
```

---

## 6. Signal Mode (`bleep/modes/signal.py`)

**Location**: `bleep/modes/signal.py`

**Purpose**: Simple notification listener for a given characteristic.

### Key Features:

- Connects to device and enumerates GATT
- Subscribes to notifications from a specific characteristic
- Logs all notifications with hex values
- Runs for a specified duration

### Usage:

```bash
python -m bleep.modes.signal CC:50:E3:B6:BC:A6 0000ff0b-0000-1000-8000-00805f9b34fb --time 30
```

### Code References:

```38:40:bleep/modes/signal.py
    def _notify_cb(uuid, value: bytes):  # type: ignore
        print_and_log(f"[NOTIFY] {uuid}: {value.hex()}", LOG__GENERAL)
```

---

## 7. D-Bus Connection Pool Logging (`bleep/dbus/connection_pool.py`)

**Location**: `bleep/dbus/connection_pool.py`

**Purpose**: Connection pooling with detailed logging of connection operations.

### Key Features:

- Logs connection creation timing
- Logs connection pool statistics
- Logs connection health checks
- Logs proxy cache operations

### Code References:

```218:224:bleep/dbus/connection_pool.py
            elapsed = time.time() - start_time
            record_operation("dbus_connection_create", elapsed, True)
            
            print_and_log(
                f"[+] Created new D-Bus connection for {bus_type} ({elapsed:.3f}s)",
                LOG__DEBUG
            )
```

```305:309:bleep/dbus/connection_pool.py
                    # Report stats
                    stats = self._get_connection_stats()
                    print_and_log(
                        f"[DEBUG] D-Bus connection pool stats: {stats}",
                        LOG__DEBUG
                    )
```

---

## Summary of Available Debugging Methods

| Method | Location | Purpose | Raw D-Bus Access |
|--------|----------|---------|------------------|
| **Debug Mode** | `bleep/modes/debug.py` | Interactive shell with introspection | ✅ Yes - Full access (see [`debug_mode.md`](debug_mode.md)) |
| **Signal Capture** | `bleep/dbuslayer/signals.py` | Capture all D-Bus signals | ✅ Yes - Signal level |
| **Signal Router** | `bleep/signals/router.py` | Filter and process signals | ✅ Yes - Via filters |
| **Logging System** | `bleep/core/log.py` | Multiple log files | ✅ Yes - Via logging |
| **BlueZ Monitor** | `bleep/dbuslayer/bluez_monitor.py` | Service health monitoring | ✅ Yes - Health checks |
| **D-Bus Diagnostic** | `bleep/scripts/dbus_diagnostic.py` | Diagnostic tooling | ✅ Yes - Testing |
| **Signal Mode** | `bleep/modes/signal.py` | Notification listener | ✅ Yes - Via callbacks |
| **Connection Pool** | `bleep/dbus/connection_pool.py` | Connection logging | ✅ Yes - Connection level |

---

## Recommended Usage Patterns

### For Comprehensive Signal Logging:

1. **Use Signal Capture System** for automated logging:
   - Signals are automatically captured via `SignalCapture` class
   - Configure routes in `bleep/signals/capture_config.py`
   - View logs in `/tmp/bti__logging__debug.txt`

2. **Use Signal Router** for filtering and processing:
   - Filter signals by device, service, characteristic, path patterns
   - Route signals to multiple actions (LOG, SAVE, DB_STORE, CALLBACK)
   - Transform signals before processing

### For Performance Debugging:

1. **Use D-Bus Diagnostic Tool**:
   ```bash
   python -m bleep.scripts.dbus_diagnostic --all
   ```

2. **Check Connection Pool Stats**:
   - Stats are logged to `LOG__DEBUG` automatically
   - View in `/tmp/bti__logging__debug.txt`

### For Signal Correlation:

1. **Use SignalCorrelator**:
   ```python
   from bleep.dbuslayer.signals import system_dbus__bluez_signals
   
   signals = system_dbus__bluez_signals()
   # Signals are automatically correlated
   # Access via get_related_signals()
   ```

### For Simple Notification Monitoring:

1. **Use Signal Mode**:
   ```bash
   python -m bleep.modes.signal CC:50:E3:B6:BC:A6 <char-uuid> --time 30
   ```

---

## Notes

- All debugging output goes to log files in `/tmp/bti__logging__*.txt`
- Signal capture system provides the most automated logging
- External `dbus-monitor` tool can be used alongside BLEEP for complete visibility:
  ```bash
  sudo dbus-monitor --system "destination='org.bluez'" "sender='org.bluez'"
  ```
- For interactive D-Bus exploration, use debug mode (see [`debug_mode.md`](debug_mode.md))
