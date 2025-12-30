# Unified D-Bus Event Aggregator

## Overview

The Unified D-Bus Event Aggregator provides comprehensive visibility into all D-Bus communications between BlueZ, agents, and devices. It captures signals, method calls, method returns, and errors in a single unified system that enables correlation and analysis of Bluetooth operations.

## Architecture

The Unified D-Bus Event Aggregator consists of three main components:

1. **`DBusEventCapture`**: A unified dataclass that represents all D-Bus event types (signals, method calls, method returns, errors) in a single structure
2. **`DBusEventAggregator`**: A centralized storage and correlation engine that maintains a history of events and provides query capabilities
3. **`system_dbus__bluez_signals`**: The main signals manager that integrates the aggregator with D-Bus message filtering

## Key Features

- **Complete Coverage**: Captures all D-Bus message types (signals, method calls, returns, errors)
- **Event Correlation**: Automatically correlates method calls with their returns/errors via serial numbers
- **Path-Based Correlation**: Finds related events on the same D-Bus object paths
- **Query API**: Powerful filtering and query capabilities for accessing captured events
- **Human-Readable Logging**: Follows error handling pattern with summary + detailed information
- **Original Message Preservation**: Preserves full D-Bus message objects for detailed analysis
- **Graceful Degradation**: Handles permission issues gracefully without crashing
- **Backward Compatibility**: Maintains compatibility with existing signal capture code

## API Reference

### DBusEventCapture

Unified dataclass for all D-Bus event types.

```python
@dataclass
class DBusEventCapture:
    event_type: str  # 'signal', 'method_call', 'method_return', 'error'
    interface: str
    path: str
    timestamp: float
    sender: str = ""
    destination: str = ""
    serial: int = 0
    reply_serial: Optional[int] = None
    signal_name: Optional[str] = None
    method_name: Optional[str] = None
    error_name: Optional[str] = None
    error_message: Optional[str] = None
    args: Tuple[Any, ...] = ()
    signature: str = ""
    source: str = ""
    original_message: Optional[dbus.Message] = None
```

### DBusEventAggregator

Centralized event storage and correlation.

```python
class DBusEventAggregator:
    def __init__(self, max_events: int = 1000)
    def add_event(self, event: DBusEventCapture) -> None
    def get_events(self, event_type: Optional[str] = None,
                   interface: Optional[str] = None,
                   path: Optional[str] = None,
                   time_window: Optional[float] = None,
                   limit: int = 100) -> List[DBusEventCapture]
    def correlate_events(self, event: DBusEventCapture,
                         time_window: float = 2.0) -> List[DBusEventCapture]
    def get_method_call_chain(self, method_call_serial: int) -> List[DBusEventCapture]
    def clear(self) -> None
```

### system_dbus__bluez_signals

Main signals manager with unified monitoring.

```python
class system_dbus__bluez_signals:
    def enable_unified_dbus_monitoring(self, enabled: bool = True,
                                       filters: Optional[Dict[str, Any]] = None) -> None
    def get_recent_events(self, event_type: Optional[str] = None,
                         interface: Optional[str] = None,
                         path: Optional[str] = None,
                         time_window: Optional[float] = None,
                         limit: int = 100) -> List[DBusEventCapture]
    def correlate_event(self, event: DBusEventCapture,
                       time_window: float = 2.0) -> List[DBusEventCapture]
    def get_method_call_chain(self, method_call_serial: int) -> List[DBusEventCapture]
```

## Usage Examples

### Basic Usage

```python
from bleep.dbuslayer.signals import system_dbus__bluez_signals

# Create signals instance
signals = system_dbus__bluez_signals()

# Enable unified monitoring
signals.enable_unified_dbus_monitoring(True)

# Query recent events
recent_events = signals.get_recent_events(limit=10)
for event in recent_events:
    print(f"{event.event_type}: {event.interface} on {event.path}")
```

### Filtering Events

```python
# Get only signals
signals = signals_instance.get_recent_events(event_type="signal", limit=20)

# Get Agent1 method calls
agent_calls = signals_instance.get_recent_events(
    event_type="method_call",
    interface="org.bluez.Agent1",
    limit=10
)

# Get events on a specific device path
device_events = signals_instance.get_recent_events(
    path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
    limit=50
)

# Get events within last 5 seconds
recent = signals_instance.get_recent_events(
    time_window=5.0,
    limit=100
)
```

### Event Correlation

```python
# Get method call chain (call → return/error)
call_event = signals_instance.get_recent_events(
    event_type="method_call",
    limit=1
)[0]

chain = signals_instance.get_method_call_chain(call_event.serial)
# chain contains: [method_call, method_return/error]

# Find related events
related = signals_instance.correlate_event(call_event, time_window=2.0)
# related contains events correlated by serial number or path
```

### Agent Integration

The Unified D-Bus Event Aggregator is automatically enabled when an agent is registered:

```python
from bleep.dbuslayer.agent import create_agent

# Create and register agent
agent = create_agent("KeyboardDisplay", auto_accept=True)
agent.register(capabilities="KeyboardDisplay", default=True)

# Unified monitoring is now enabled automatically
# All agent method calls, returns, and errors are captured
```

### Accessing Original D-Bus Messages

```python
event = signals_instance.get_recent_events(limit=1)[0]

if event.original_message:
    # Access full D-Bus message for detailed analysis
    msg_type = event.original_message.get_type()
    full_args = event.original_message.get_args_list()
    # ... detailed analysis
```

## Integration Examples

### Debugging Pairing Issues

```python
# Enable unified monitoring
signals = system_dbus__bluez_signals()
signals.enable_unified_dbus_monitoring(True)

# Register agent
agent = create_agent("KeyboardDisplay", auto_accept=True)
agent.register(capabilities="KeyboardDisplay", default=True)

# Perform pairing operation
# ... pairing code ...

# Query for pairing-related events
pairing_events = signals.get_recent_events(
    interface="org.bluez.Agent1",
    time_window=10.0
)

# Find method call chains
for event in pairing_events:
    if event.event_type == "method_call":
        chain = signals.get_method_call_chain(event.serial)
        print(f"Method call chain: {[e.event_type for e in chain]}")
```

### Monitoring Device Connections

```python
signals = system_dbus__bluez_signals()
signals.enable_unified_dbus_monitoring(True)

# Monitor device connection signals
device_signals = signals.get_recent_events(
    event_type="signal",
    interface="org.freedesktop.DBus.Properties",
    path="/org/bluez/hci0",
    time_window=30.0
)

for signal in device_signals:
    if signal.signal_name == "PropertiesChanged":
        # Check for Connected property changes
        print(f"Properties changed on {signal.path}")
```

### Error Analysis

```python
# Get all errors
errors = signals.get_recent_events(event_type="error", limit=20)

for error in errors:
    print(f"Error: {error.error_name}: {error.error_message}")
    
    # Find the method call that caused this error
    if error.reply_serial:
        chain = signals.get_method_call_chain(error.reply_serial)
        if chain:
            print(f"  Caused by: {chain[0].method_name}")
```

## Logging

The Unified D-Bus Event Aggregator logs all events in a human-readable format with detailed information:

```
[2025-01-15 10:30:45] METHOD CALL: RequestPinCode (interface=org.bluez.Agent1, path=/org/bluez/agent, sender=:1.123, destination=org.bluez)
[DETAIL] RequestPinCode: interface=org.bluez.Agent1, path=/org/bluez/agent, sender=:1.123, destination=org.bluez, serial=100, signature=o, args=('/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF',)
[!] PIN CODE REQUEST: BlueZ (:1.123) -> agent (org.bluez)
[!] Target device: /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF
```

Special events are highlighted:
- **PIN Code Requests**: Highlighted with `[!] PIN CODE REQUEST`
- **Authentication Errors**: Highlighted with `[!] AUTHENTICATION ERROR`
- **Agent Registration Events**: Logged with full context

Logs are written to `LOG__AGENT` (`/tmp/bti__logging__agent.txt` or `~/.bleep/logs/agent.log`).

## Performance Considerations

- **Memory Usage**: Default maximum of 1000 events in memory (configurable via `DBusEventAggregator(max_events=...)`)
- **Thread Safety**: All operations are thread-safe using locks
- **Event Trimming**: Old events are automatically trimmed when limit is reached
- **Query Performance**: Filtering is done in-memory, so queries are fast for typical event counts

## Permission Requirements

Some D-Bus message types require special permissions:

- **Signals**: No special permissions required
- **Method Calls (non-eavesdrop)**: No special permissions required
- **Method Calls (eavesdrop)**: May require root or D-Bus policy changes
- **Method Returns/Errors (eavesdrop)**: May require root or D-Bus policy changes

The system gracefully handles permission issues:
- If eavesdrop matches fail, monitoring continues with available message types
- Agent registration succeeds even if monitoring fails
- Errors are logged but don't crash the system

## Troubleshooting

### No Events Captured

1. **Check if monitoring is enabled**: `signals._unified_monitoring` should be `True`
2. **Check permissions**: Some message types may require root or D-Bus policy changes
3. **Check BlueZ is running**: `systemctl status bluetooth`
4. **Check log files**: Look for error messages in `LOG__AGENT`

### Missing Method Returns

1. **Check reply_serial**: Method returns link to calls via `reply_serial`
2. **Check time_window**: Correlation uses time windows; increase if needed
3. **Check permissions**: Eavesdrop permissions may be required for some returns

### High Memory Usage

1. **Reduce max_events**: Lower `DBusEventAggregator(max_events=...)`
2. **Clear events periodically**: Call `aggregator.clear()` when done
3. **Use time_window filters**: Query only recent events

## Backward Compatibility

The Unified D-Bus Event Aggregator maintains full backward compatibility:

- **`SignalCapture`**: Still works (deprecated but functional)
- **`MethodCallCapture`**: Still works (deprecated but functional)
- **`enable_agent_method_call_monitoring()`**: Delegates to unified monitoring
- **Existing code**: Continues to work without changes

## Best Practices

1. **Enable monitoring early**: Enable unified monitoring before performing operations
2. **Use time_window filters**: Query only events you need to reduce memory usage
3. **Clear when done**: Clear the aggregator when finished with analysis
4. **Check permissions**: Be aware of permission requirements for full functionality
5. **Use correlation**: Leverage correlation to find related events
6. **Preserve original messages**: Use `original_message` for detailed analysis when needed

## Related Documentation

- [Agent Mode](agent_mode.md) - Agent registration and usage
- [Pairing Agent](pairing_agent.md) - Pairing agent implementation
- [Signal Capture](signal_capture.md) - Signal capture system (legacy)
- [D-Bus Best Practices](dbus_best_practices.md) - D-Bus interaction guidelines

