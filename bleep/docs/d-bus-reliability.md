# D-Bus Reliability System

## Overview

The BLEEP D-Bus Reliability System provides comprehensive tools for improving the reliability, robustness, and performance of BlueZ D-Bus operations. The system addresses common issues such as method call timeouts, signal delivery problems, controller stalls, and error propagation failures.

## Key Features

- **Timeout Enforcement**: Prevent operations from hanging indefinitely
- **Service Monitoring**: Detect BlueZ service stalls and restarts
- **Performance Metrics**: Track operation latency and error rates
- **Automatic Recovery**: Implement graduated recovery strategies
- **Connection Pooling**: Optimize connection usage and reliability
- **State Preservation**: Maintain device state across reconnections
- **Comprehensive Documentation**: Best practices and usage patterns

## Architecture

The reliability system consists of several integrated components:

```
                  +---------------------------+
                  |    D-Bus Timeout Layer    |
                  +---------------------------+
                             |
                             v
+------------------+  +-------------------+  +-------------------+
| BlueZ Monitor    |  | Connection Pool   |  | Recovery Manager  |
+------------------+  +-------------------+  +-------------------+
          |                   |                      |
          v                   v                      v
+------------------+  +-------------------+  +-------------------+
| Health Metrics   |  | Proxy Cache       |  | State Tracker     |
+------------------+  +-------------------+  +-------------------+
                             |
                             v
                  +---------------------------+
                  |       Core D-Bus API      |
                  +---------------------------+
```

## Components

### 1. Timeout Enforcement Layer (`bleep/dbus/timeout_manager.py`)

Prevents D-Bus operations from hanging indefinitely by enforcing timeouts. Provides:

- Decorator-based timeout enforcement
- Function-based timeout wrapping
- Timeout Properties interface
- Default timeouts by operation type

```python
from bleep.dbus.timeout_manager import with_timeout

@with_timeout("connect", device_address="00:11:22:33:44:55")
def connect_device(device_interface):
    device_interface.Connect()
```

**Consumers of `call_method_with_timeout()`**:

* `bleep.core.preflight.check_endpoint_contention(deep_probe=True)` — walks
  every registered D-Bus bus name and introspects it for
  `org.bluez.MediaEndpoint1` interfaces (then resolves owners via
  `GetConnectionUnixProcessID` + `/proc/<pid>/comm`).  A congested or
  malicious bus name cannot stall the pre-flight because each D-Bus
  method call (`ListNames`, `Introspect`, `GetNameOwner`,
  `GetConnectionUnixProcessID`, `Properties.Get`) is guarded
  individually (default 3 s each).  Used by `MediaStreamManager` to
  block audio acquire before cycling the device when BlueALSA owns the
  competing endpoint, and by the `audiocfg --endpoints` /
  `mediaenum --endpoints` debug surfaces.  See
  [audio_recon.md](audio_recon.md#troubleshooting-mediaendpoint1-contention-transport-timeout-on-audioplay--audiorec).

### 2. BlueZ Service Monitor (`bleep/dbuslayer/bluez_monitor.py`)

Monitors the health and availability of BlueZ services. Features:

- Background health checks
- Service stall detection
- Service restart notification
- Callback registration

```python
from bleep.dbuslayer.bluez_monitor import register_stall_callback

def on_bluez_stall():
    print("BlueZ service appears stalled!")

register_stall_callback(on_bluez_stall)
```

### 3. Health Metrics (`bleep/core/metrics.py`)

Collects and analyzes performance metrics for D-Bus operations. Includes:

- Latency tracking with percentiles
- Error rate monitoring
- Automatic issue detection
- Comprehensive logging

```python
from bleep.core.metrics import record_operation, log_metrics_summary

start_time = time.time()
success = False
try:
    device_interface.Connect()
    success = True
except Exception:
    pass
elapsed = time.time() - start_time
record_operation("connect", elapsed, success)

# Later
log_metrics_summary()
```

### 4. Connection Reset Manager (`bleep/dbuslayer/recovery.py`)

Implements automated recovery strategies for connection issues. Features:

- Staged recovery with progressive escalation
- Automatic backoff for repeated attempts
- Detailed recovery history
- Callback notifications

```python
from bleep.dbuslayer.recovery import recover_connection

recover_connection(
    device_address,
    bus,
    device_path,
    adapter_path,
    device_interface
)
```

### 5. State Preservation (`bleep/dbuslayer/recovery.py`)

Maintains device state information for recovery purposes. Supports:

- State snapshot creation
- Custom state attributes
- State restoration after recovery

```python
from bleep.dbuslayer.recovery import save_device_state, get_device_state

# Save state
save_device_state(device)

# Later, retrieve state
state = get_device_state(device.get_address())
```

### 6. Connection Pool (`bleep/dbus/connection_pool.py`)

Optimizes D-Bus connection usage with pooling and reuse. Provides:

- Connection reuse and recycling
- Connection health checking
- Proxy object caching
- Context manager API

```python
from bleep.dbus.connection_pool import connection_manager, get_proxy

# Use connection from pool
with connection_manager() as bus:
    obj = bus.get_object("org.bluez", "/org/bluez/hci0")
    # Do something with obj

# Get cached proxy
adapter_interface = get_proxy(
    dbus.Bus.SYSTEM,
    "org.bluez",
    "/org/bluez/hci0",
    "org.bluez.Adapter1"
)
```

## Integration

The reliability components are designed to be easily integrated with existing code. The modular design allows you to:

1. **Use directly**: Utilize specific components as needed
2. **Integrate gradually**: Apply reliability features incrementally
3. **Adopt holistically**: Implement the full reliability system

## Best Practices

For detailed guidance on using the reliability system effectively, refer to:

- [D-Bus Best Practices Guide](dbus_best_practices.md)
- Diagnostic tool: `bleep/scripts/dbus_diagnostic.py` (run via `python -m bleep.scripts.dbus_diagnostic --all`)

## Troubleshooting

The diagnostic tool (`bleep/scripts/dbus_diagnostic.py`) provides comprehensive testing and reporting for the reliability system. Run it with:

```bash
python -m bleep.scripts.dbus_diagnostic --all
```

See the diagnostic tool's help output for more options:

```bash
python -m bleep.scripts.dbus_diagnostic --help
```

## Known unresolved failure: the ~42-minute collector ceiling

A survey process stops collecting after roughly **80 harvest rounds (~2500s)**.
The adapter's `Adapter1` interface then answers nothing — `Powered` and
`Discovering` both return `NoReply` — and no D-Bus-level recovery clears it.
The failure ends when the process exits; a fresh process collects normally from
t=0. Recorded here because it looks like a D-Bus reliability problem and will
be encountered by anyone debugging this layer.

Reproduced five consecutive times (`todo_tracker.md` B.19-B.23 records the closure):
rounds 79, 79, 83, 81, 83. **Round count is the tightest invariant** — elapsed
time (2490–2670s) and RSS (197–208 MB) vary more.

Ruled out by direct measurement, so do not re-investigate these:

| Hypothesis | Measurement | Verdict |
|---|---|---|
| Adapter/controller fault | wedges identically with the collector on `hci1` | not hardware |
| Concurrent enumeration | wedges with **no enumerator at all** | not the enumerator |
| Long-lived discovery session | wedges with discovery torn down every round | not session age |
| GLib main loop | all five runs were `--no-mainloop` | not the loop |
| `max_match_rules_per_connection` (512) | `matches` pinned at **5** every sample | not match rules |
| `max_replies_per_connection` (128) / unread inbound | `sock_rx` steady at **~37 kB** for 3200s | not backpressure |
| Signals-registry retention | `sig_devs` constant at **1** | not the registry |
| BlueZ device-object accumulation | `bluez_devs` **oscillates 14–145** (pruned on `TemporaryTimeout`); read 15 at the wedge; r=+0.20 vs RSS | not BlueZ objects |

Note that BlueZ object counts **cannot be measured after the fact** — the
recovery power-cycle flushes BlueZ's device cache. Sample in-flight via
`--metrics-interval`, which records `manager.LAST_HARVEST` without issuing a
second `GetManagedObjects` that would block on the wedged connection.

**Mitigation in place, not a fix:** runs longer than one segment are split into
consecutive processes and merged — see "Segmented long runs" in
`survey_mode.md`. The stall ladder additionally makes a single over-long run
degrade honestly rather than silently (`survey_mode.md`, "Collector stall
detection").

## Further Reading

- [BlueZ D-Bus API Documentation](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc)
- [D-Bus Specification](https://dbus.freedesktop.org/doc/dbus-specification.html)
- [Python D-Bus Tutorial](https://dbus.freedesktop.org/doc/dbus-python/tutorial.html)
