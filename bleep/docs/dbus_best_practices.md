# BlueZ D-Bus Reliability Best Practices

This document provides guidelines and best practices for reliable BlueZ D-Bus operations in the BLEEP codebase. These practices are derived from extensive testing, the BlueZ documentation, reference scripts, and community knowledge.

## Overview

BlueZ provides a rich D-Bus API for interacting with Bluetooth adapters and devices. While powerful, this API can sometimes be unpredictable, especially when dealing with unreliable Bluetooth connections. This guide aims to help you write robust code that can handle common D-Bus issues.

## Table of Contents

1. [Common D-Bus Issues](#common-d-bus-issues)
2. [Using the Reliability Framework](#using-the-reliability-framework)
3. [Timeout Management](#timeout-management)
4. [Error Handling](#error-handling)
5. [Recovery Strategies](#recovery-strategies)
6. [Connection Pooling](#connection-pooling)
7. [Metrics and Monitoring](#metrics-and-monitoring)
8. [Debugging Techniques](#debugging-techniques)

## Common D-Bus Issues

BlueZ D-Bus operations can encounter various issues:

### 1. Method Call Timeouts

BlueZ D-Bus methods (especially those involving device connections) can stall indefinitely, leaving your code waiting forever for a response.

```python
# Problematic code - may hang indefinitely
device_interface.Connect()  # No timeout!
```

### 2. Signal Delivery Problems

Signal delivery via D-Bus can be unreliable, leading to missed events or delayed notifications.

```python
# Problematic code - may miss signals or react too slowly
def property_changed(*args):
    # This might not get called in a timely manner
    pass

bus.add_signal_receiver(property_changed, ...)
```

### 3. Error Propagation Failures

Some D-Bus errors are not properly propagated, making it difficult to determine the root cause of issues.

```python
# Problematic code - catches too broadly
try:
    device_interface.Connect()
except dbus.exceptions.DBusException as e:
    # All errors look the same - can't determine exact cause
    print(f"Error: {e}")
```

### 4. State Inconsistency

D-Bus properties might not reflect the actual state of BlueZ or the Bluetooth adapter.

```python
# Problematic code - trusts properties too much
props = props_interface.GetAll("org.bluez.Device1")
is_connected = props.get("Connected", False)  # May be stale or incorrect
```

### 5. Controller Stalls

The Bluetooth controller can stall, causing all D-Bus operations to hang.

```python
# Problematic code - no detection of controller stalls
def enumerate_device(device):
    # If controller stalls, this whole function hangs indefinitely
    services = device.GetServices()
    for service in services:
        characteristics = service.GetCharacteristics()
        # ...
```

## Using the Reliability Framework

BLEEP provides a comprehensive reliability framework for D-Bus operations. Here's how to use it:

### 1. Timeout Management

Use the timeout enforcement layer to prevent operations from hanging indefinitely:

```python
from bleep.dbus.timeout_manager import with_timeout, call_method_with_timeout, TimeoutProperties

# Method 1: Use the decorator
@with_timeout("connect", device_address="00:11:22:33:44:55")
def connect_device(device_interface):
    device_interface.Connect()

# Method 2: Use the utility function
call_method_with_timeout(
    device_interface,
    "Connect",
    timeout=15.0,
    device_address="00:11:22:33:44:55"
)

# Method 3: Use the wrapped properties interface
props = TimeoutProperties(props_interface, timeout=5.0, device_address="00:11:22:33:44:55")
value = props.Get("org.bluez.Device1", "Connected")
```

### 2. BlueZ Service Monitoring

Monitor the health of BlueZ services to detect issues early:

```python
from bleep.dbuslayer.bluez_monitor import register_stall_callback, register_restart_callback

def on_bluez_stall():
    print("BlueZ service appears stalled!")

def on_bluez_restart():
    print("BlueZ service has been restarted")

register_stall_callback(on_bluez_stall)
register_restart_callback(on_bluez_restart)
```

### 3. Connection Reset Management

Implement automatic recovery strategies for connection issues:

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

### 4. Connection Pooling

Use the connection pool for high-volume operations:

```python
from bleep.dbus.connection_pool import connection_manager, get_proxy

# Method 1: Use the connection manager
with connection_manager() as bus:
    obj = bus.get_object("org.bluez", "/org/bluez/hci0")
    # Do something with obj

# Method 2: Use the proxy cache
adapter_interface = get_proxy(
    dbus.Bus.SYSTEM,
    "org.bluez",
    "/org/bluez/hci0",
    "org.bluez.Adapter1"
)
```

## Timeout Management

### Best Practices

1. **Always Use Timeouts**: Never call D-Bus methods without a timeout.
2. **Choose Appropriate Timeout Values**:
   - `Connect()`: 15-30 seconds
   - `Disconnect()`: 5-10 seconds
   - Property reads: 5 seconds
   - Characteristic reads: 10 seconds
   - Service discovery: 20-30 seconds
3. **Add Timeout Logging**: Log when operations take longer than expected.
4. **Implement Graceful Fallbacks**: Have a plan for when operations time out.

### Default Timeout Values

The BLEEP framework provides these default timeout values, which you can override:

| Operation | Default Timeout |
|-----------|----------------|
| connect | 15 seconds |
| disconnect | 5 seconds |
| pair | 30 seconds |
| get_property | 5 seconds |
| set_property | 5 seconds |
| read | 10 seconds |
| write | 10 seconds |
| start_notify | 5 seconds |
| stop_notify | 5 seconds |
| default | 10 seconds |

## Error Handling

### Best Practices

1. **Use Specific Error Mapping**: Map D-Bus errors to specific application exceptions.
2. **Check Error Names**: Inspect `e.get_dbus_name()` for accurate error classification.
3. **Look for Patterns in Error Messages**: Some errors are only distinguishable by their message text.
4. **Implement Retry Logic**: Many operations can succeed after a retry.
5. **Log Error Details**: Include as much context as possible in error logs.

### Common BlueZ Errors

| D-Bus Error Name | Common Causes | Recommended Action |
|------------------|---------------|-------------------|
| org.freedesktop.DBus.Error.NoReply | Controller stall or timeout | Attempt recovery |
| org.freedesktop.DBus.Error.UnknownObject | Invalid or non-existent path | Check path validity |
| org.bluez.Error.NotConnected | Operation requires connection | Reconnect first |
| org.bluez.Error.Failed | Generic operation failure | Check device state |
| org.bluez.Error.NotPermitted | Permission denied | Check device pairing status |
| org.bluez.Error.NotAuthorized | Authentication required | Implement authentication |
| org.bluez.Error.InvalidArguments | Incorrect parameters | Validate inputs |
| org.bluez.Error.InProgress | Operation already in progress | Wait for completion |

## Recovery Strategies

BLEEP implements a staged recovery process with increasing levels of intervention:

### 1. Disconnect/Reconnect

Simplest recovery strategy, suitable for transient issues:

```python
try:
    device_interface.Disconnect()  # Clean up first
    time.sleep(1)  # Give BlueZ time to clean up
    device_interface.Connect()  # Try connecting again
except Exception:
    # Move to next recovery stage
    pass
```

### 2. Interface Reset

Re-create D-Bus interfaces for a clean state:

```python
try:
    device_object = bus.get_object(BLUEZ_SERVICE_NAME, device_path)
    device_interface = dbus.Interface(device_object, DEVICE_INTERFACE)
    device_interface.Connect()
except Exception:
    # Move to next recovery stage
    pass
```

### 3. Adapter Reset via BlueZ

Turn the adapter off and on through BlueZ:

```python
try:
    adapter_interface.SetProperty("Powered", dbus.Boolean(False))
    time.sleep(1)
    adapter_interface.SetProperty("Powered", dbus.Boolean(True))
    time.sleep(2)
except Exception:
    # Move to next recovery stage
    pass
```

### 4. Controller Reset via hciconfig

Use system commands to reset the Bluetooth controller:

```python
try:
    subprocess.run(["hciconfig", adapter_name, "down"], check=True)
    time.sleep(1)
    subprocess.run(["hciconfig", adapter_name, "up"], check=True)
    time.sleep(2)
except Exception:
    # Move to next recovery stage
    pass
```

### 5. BlueZ Service Restart

Last resort - restart the entire BlueZ service:

```python
try:
    subprocess.run(["systemctl", "restart", "bluetooth.service"], check=True)
    time.sleep(3)
except Exception:
    # Recovery failed, notify user
    print("Could not recover Bluetooth functionality")
```

## Connection Pooling

Connection pooling helps optimize D-Bus performance and reliability:

### Benefits

1. **Reduced Connection Overhead**: Reusing connections avoids the overhead of creating new ones.
2. **Connection Health Checking**: Automatically validates connections before use.
3. **Automatic Connection Replacement**: Stale or unhealthy connections are replaced.
4. **Proxy Object Caching**: Frequently used proxy objects are cached for better performance.

### When to Use Connection Pooling

Use connection pooling when:
1. Making many D-Bus calls in rapid succession
2. Creating multiple connections to the same service
3. Working with multiple Bluetooth devices simultaneously
4. Implementing long-running services that need persistent connections

### When NOT to Use Connection Pooling

Connection pooling may not be beneficial when:
1. Making only a few D-Bus calls
2. Running short-lived scripts
3. Memory constraints are significant

## Metrics and Monitoring

BLEEP's metrics system helps track D-Bus operation performance and reliability:

### Available Metrics

1. **Latency Statistics**:
   - `min`, `max`, `avg`: Minimum, maximum, and average latency
   - `p90`, `p95`, `p99`: Percentile latency values
   - `count`: Number of samples
   
2. **Error Rates**:
   - Error percentage over time window
   - Total operation count
   - Failed operation count

### Using Metrics

```python
from bleep.core.metrics import record_operation, get_metrics, detect_issues, log_metrics_summary

# Record operation metrics
start_time = time.time()
success = False
try:
    device_interface.Connect()
    success = True
except Exception:
    pass
elapsed = time.time() - start_time
record_operation("connect", elapsed, success)

# Get metrics for an operation type
metrics = get_metrics("connect")
print(f"Connect latency: avg={metrics['latency']['avg']:.3f}s, p95={metrics['latency']['p95']:.3f}s")
print(f"Connect error rate: {metrics['error_rate'][0]:.1%}")

# Check for potential issues
issues = detect_issues()
if issues:
    print(f"Detected issues: {issues}")

# Log a summary of all metrics
log_metrics_summary()
```

## Debugging Techniques

### 1. Enable Verbose Logging

```python
from bleep.core.log import set_debug_level, LOG__DEBUG
set_debug_level(LOG__DEBUG)
```

### 2. Monitor D-Bus Traffic

Use `dbus-monitor` to see real-time D-Bus traffic:

```bash
dbus-monitor --system "interface='org.bluez.Device1'"
```

### 3. Check BlueZ Service Status

```bash
systemctl status bluetooth.service
```

### 4. Review Controller Status

```bash
hciconfig -a
```

### 5. Use the Recovery Tools Directly

```python
from bleep.dbuslayer.recovery import recover_connection
success = recover_connection(device_address, bus, device_path, adapter_path)
```

### 6. Analyze Operation Metrics

```python
from bleep.core.metrics import get_metrics, log_metrics_summary
metrics = get_metrics()
print(f"D-Bus operation metrics: {metrics}")
log_metrics_summary()
```

### 7. Check Signal Delivery

```python
from bleep.dbuslayer.signals import system_dbus__bluez_signals
signals_instance = system_dbus__bluez_signals()
signals_instance.set_debug(True)
```

### 8. Test Connection Health

```python
from bleep.dbuslayer.bluez_monitor import get_monitor
monitor = get_monitor()
is_available = monitor.is_service_available()
print(f"BlueZ service available: {is_available}")
```

## Conclusion

Following these best practices will help you build more reliable Bluetooth applications with BLEEP and BlueZ. The framework provides comprehensive tools for handling common issues, but understanding the underlying principles is still important.

Remember these key points:
1. Always use timeouts for D-Bus operations
2. Implement proper error handling and recovery strategies
3. Use the provided reliability tools for complex operations
4. Monitor and log metrics to detect issues early
5. Test your code with a variety of Bluetooth devices to uncover edge cases
