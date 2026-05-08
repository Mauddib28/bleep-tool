# D-Bus Reliability Documentation Index

This document serves as a central reference for all documentation related to the D-Bus Reliability Framework implemented in BLEEP.

## Overview

The D-Bus Reliability Framework provides comprehensive tools and patterns for improving the reliability, robustness, and performance of BlueZ D-Bus operations. It addresses common issues such as hanging method calls, signal delivery problems, connection failures, and performance bottlenecks.

## Documentation

### Primary Documents

1. **[D-Bus Reliability System Overview](d-bus-reliability.md)**
   - System architecture and component interactions
   - Feature overview
   - Integration points
   - Usage examples

2. **[D-Bus Best Practices Guide](dbus_best_practices.md)**
   - Common D-Bus issues and solutions
   - Error handling strategies
   - Recovery patterns
   - Performance optimization
   - Debugging techniques

### Implementation Files

1. **Timeout Enforcement Layer**
   - Location: `bleep/dbus/timeout_manager.py`
   - Purpose: Prevent D-Bus operations from hanging indefinitely

2. **BlueZ Service Monitor**
   - Location: `bleep/dbuslayer/bluez_monitor.py`
   - Purpose: Detect BlueZ service stalls and restarts

3. **Controller Health Metrics**
   - Location: `bleep/core/metrics.py`
   - Purpose: Track D-Bus operation performance and reliability

4. **Connection Reset Manager**
   - Location: `bleep/dbuslayer/recovery.py`
   - Purpose: Implement recovery strategies for connection issues

5. **D-Bus Connection Pool**
   - Location: `bleep/dbus/connection_pool.py`
   - Purpose: Optimize D-Bus connection usage

6. **Diagnostic Tool**
   - Location: `bleep/scripts/dbus_diagnostic.py`
   - Purpose: Test and demonstrate D-Bus reliability features

### Verification & Testing

The diagnostic tool (`bleep/scripts/dbus_diagnostic.py`) can be used to verify
reliability features are working correctly:

```bash
python -m bleep.scripts.dbus_diagnostic --all
```

Key verification areas:
- **Timeout enforcement** — Confirm that hung D-Bus calls are interrupted after the configured timeout.
- **BlueZ monitoring** — Verify stall/restart detection via `bluez_monitor.py`.
- **Connection recovery** — Test reconnection strategies after simulated failures.
- **Metrics collection** — Inspect latency/success-rate statistics via `LatencyTracker`.

## Integration with BLEEP

The D-Bus Reliability Framework is designed to integrate seamlessly with existing BLEEP code. The primary integration points are:

1. **Timeout Enforcement**
   - Can be applied to any D-Bus method call via decorators or direct function calls
   - Works with any D-Bus interface, not just BlueZ

2. **Connection Pooling**
   - Can be used wherever D-Bus connections are needed
   - Especially useful for high-volume operations

3. **BlueZ Monitoring**
   - Can be integrated with any code that interacts with BlueZ services
   - Provides early warning for potential issues

4. **Metrics Collection**
   - Can be used to track performance of any operation, not just D-Bus calls
   - Helps identify bottlenecks and issues

## Usage Examples

### Basic Timeout Enforcement

```python
from bleep.dbus.timeout_manager import with_timeout

@with_timeout("connect", device_address="00:11:22:33:44:55")
def connect_device(device_interface):
    device_interface.Connect()
```

### Connection Pooling

```python
from bleep.dbus.connection_pool import connection_manager

with connection_manager() as bus:
    obj = bus.get_object("org.bluez", "/org/bluez/hci0")
    adapter = dbus.Interface(obj, "org.bluez.Adapter1")
    adapter.StartDiscovery()
```

### Recovery Strategies

```python
from bleep.dbuslayer.recovery import recover_connection

# When a connection fails
if not success:
    recover_connection(
        device_address,
        bus,
        device_path,
        adapter_path,
        device_interface
    )
```

### Metrics Collection

```python
from bleep.core.metrics import record_operation

# Record operation metrics
start_time = time.time()
success = False
try:
    # Perform operation
    success = True
except Exception:
    pass
elapsed = time.time() - start_time
record_operation("operation_name", elapsed, success)
```

## Related: D-Bus Client Lifetime Analysis

Not all BlueZ D-Bus interfaces behave identically with respect to caller
lifetime.  A detailed audit of the BlueZ C source code revealed that some
interfaces install a `g_dbus_add_disconnect_watch()` on the calling D-Bus
client (tearing down the resource when the caller exits the bus), while others
do not.  See **[PAN connection analysis](pan_connection_analysis.md)** §2 for
the full findings — particularly the table in §2.3 showing which BlueZ
interfaces track the caller and which do not.  This is essential reading for
any new D-Bus wrapper development.

## Conclusion

The D-Bus Reliability Framework significantly enhances the robustness of BLEEP's Bluetooth operations. By addressing common issues with D-Bus communication, it ensures more reliable connections, better error handling, and improved performance.

For questions or issues, refer to the documentation or open an issue in the project repository.
