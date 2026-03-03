# PIN Code Request Tracking Verification Guide

This guide explains how to manually verify that the PIN code request tracking capabilities are working correctly when attempting to connect to a device that performs a `PinCodeRequest`.

## Prerequisites

1. **Agent Registration**: The agent must be registered with unified D-Bus monitoring enabled
2. **Target Device**: A Bluetooth Classic device that requires PIN code pairing
3. **Log Files**: Access to BLEEP log files for review

## Verification Methods

### Method 1: Real-Time Log Monitoring

The agent log file captures all PIN code request events in real-time.

#### Step 1: Start Agent with Monitoring

```bash
bleep agent --mode=simple --cap=keyboard --default
```

**Expected Output:**
- `[+] Unified D-Bus monitoring enabled (signals, method calls, returns, errors)`
- `[+] Agent instance registered with signals manager: /test/agent`
- `[+] Agent registered successfully: path=/test/agent, capabilities=KeyboardOnly`

#### Step 2: Monitor Agent Log File

In a separate terminal, monitor the agent log:

```bash
tail -f ~/.local/share/bleep/logs/agent.log
# OR (legacy path)
tail -f /tmp/bti__logging__agent.txt
```

#### Step 3: Attempt Connection

In another terminal, attempt to connect to the target device:

```bash
bleep classic-enum D8:3A:DD:0B:69:B9
```

#### Step 4: Review Log Output

**What to Look For:**

1. **RequestPinCode Signal Capture:**
   ```
   [timestamp] SIGNAL: RequestPinCode (interface=org.bluez.Agent1, path=/org/bluez/agent, sender=:1.XX, destination=:1.YY)
   [!] PIN CODE REQUEST SIGNAL: BlueZ -> agent
   [!] Target device: /org/bluez/hci0/dev_D8_3A_DD_0B_69_B9
   ```

2. **RequestPinCode Method Call (if agent method is invoked):**
   ```
   [timestamp] METHOD CALL: RequestPinCode (interface=org.bluez.Agent1, path=/test/agent, sender=:1.XX, destination=:1.YY)
   [!] PIN CODE REQUEST: BlueZ (sender) -> agent (destination)
   [!] Target device: /org/bluez/hci0/dev_D8_3A_DD_0B_69_B9
   [+] Agent method RequestPinCode invoked: device=/org/bluez/hci0/dev_D8_3A_DD_0B_69_B9, agent_path=/test/agent
   ```

3. **Cancel Event (if pairing fails):**
   ```
   [timestamp] METHOD CALL: Cancel (interface=org.bluez.Agent1, path=/test/agent, sender=:1.XX, destination=:1.YY)
   [!] CANCEL: BlueZ -> agent
   ```

4. **Correlation Analysis (automatic):**
   ```
   [*] Correlating Cancel with recent RequestPinCode events...
   [*] Found recent RequestPinCode: timestamp=..., device=/org/bluez/hci0/dev_D8_3A_DD_0B_69_B9
   [*] Agent method invocation status:
       RequestPinCode invoked: True/False
       Cancel invoked: True/False
   [*] Device connection state at RequestPinCode: connected=False
   ```

5. **Root Cause Analysis Summary:**
   ```
   [*] PIN Code Request Failure Analysis:
       RequestPinCode timestamp: ...
       Cancel timestamp: ...
       Time difference: X.XX seconds
       Root cause: Agent method RequestPinCode was NOT invoked (capability mismatch or agent not registered)
       OR
       Root cause: Agent method RequestPinCode was invoked but returned None/empty PIN
   ```

### Method 2: Programmatic Event Query

You can query the unified D-Bus event aggregator programmatically to inspect captured events.

#### Python Script Example

Create a script `query_pincode_events.py`:

```python
#!/usr/bin/env python3
"""Query PIN code request events from unified D-Bus event aggregator."""

from bleep.dbuslayer.signals import system_dbus__bluez_signals
from datetime import datetime

# Get signals instance
signals = system_dbus__bluez_signals()

# Check if unified monitoring is enabled
if not signals._unified_monitoring:
    print("[!] Unified D-Bus monitoring is not enabled")
    exit(1)

print("[+] Unified D-Bus monitoring is active\n")

# Query all RequestPinCode events (last 60 seconds)
print("=" * 80)
print("RequestPinCode Events (last 60 seconds):")
print("=" * 80)

pincode_events = signals.get_recent_events(
    event_type="method_call",
    interface="org.bluez.Agent1",
    time_window=60.0,
    limit=50
)

# Filter for RequestPinCode
request_pincode = [e for e in pincode_events if e.method_name == "RequestPinCode"]

if not request_pincode:
    print("No RequestPinCode method calls found")
else:
    for event in request_pincode:
        timestamp = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")
        print(f"\n[{timestamp}] RequestPinCode")
        print(f"  Path: {event.path}")
        print(f"  Device: {event.args[0] if event.args else 'N/A'}")
        print(f"  Sender: {event.sender}")
        print(f"  Destination: {event.destination}")
        print(f"  Serial: {event.serial}")
        
        # Get method call chain
        chain = signals.get_method_call_chain(event.serial)
        if len(chain) > 1:
            print(f"  Response: {chain[1].event_type} ({chain[1].interface})")
        
        # Correlate with related events
        related = signals.correlate_event(event, time_window=5.0)
        cancel_events = [e for e in related if e.method_name == "Cancel"]
        if cancel_events:
            print(f"  Cancel events: {len(cancel_events)}")
            for cancel in cancel_events:
                cancel_time = datetime.fromtimestamp(cancel.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")
                time_diff = cancel.timestamp - event.timestamp
                print(f"    Cancel at {cancel_time} (Δ {time_diff:.3f}s)")

# Query Cancel events
print("\n" + "=" * 80)
print("Cancel Events (last 60 seconds):")
print("=" * 80)

cancel_events = signals.get_recent_events(
    event_type="method_call",
    interface="org.bluez.Agent1",
    time_window=60.0,
    limit=50
)

cancel_calls = [e for e in cancel_events if e.method_name == "Cancel"]

if not cancel_calls:
    print("No Cancel method calls found")
else:
    for event in cancel_calls:
        timestamp = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")
        print(f"\n[{timestamp}] Cancel")
        print(f"  Path: {event.path}")
        print(f"  Sender: {event.sender}")
        print(f"  Destination: {event.destination}")

# Query all agent-related signals
print("\n" + "=" * 80)
print("Agent-Related Signals (last 60 seconds):")
print("=" * 80)

agent_signals = signals.get_recent_events(
    event_type="signal",
    interface="org.bluez.Agent1",
    time_window=60.0,
    limit=50
)

if not agent_signals:
    print("No agent-related signals found")
else:
    for event in agent_signals:
        timestamp = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")
        print(f"\n[{timestamp}] {event.signal_name}")
        print(f"  Path: {event.path}")
        print(f"  Sender: {event.sender}")
        if event.args:
            print(f"  Args: {event.args}")

# Query all events for the target device
print("\n" + "=" * 80)
print("All Events for Device D8:3A:DD:0B:69:B9 (last 60 seconds):")
print("=" * 80)

device_path = "/org/bluez/hci0/dev_D8_3A_DD_0B_69_B9"
device_events = signals.get_recent_events(
    path=device_path,
    time_window=60.0,
    limit=100
)

if not device_events:
    print(f"No events found for device {device_path}")
else:
    for event in device_events:
        timestamp = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")
        event_type_label = event.event_type.upper().replace("_", " ")
        print(f"\n[{timestamp}] {event_type_label}")
        if event.event_type == "signal":
            print(f"  Signal: {event.signal_name}")
        elif event.event_type == "method_call":
            print(f"  Method: {event.method_name}")
        print(f"  Interface: {event.interface}")
        print(f"  Path: {event.path}")
```

Run the script:

```bash
python3 query_pincode_events.py
```

### Method 3: Debug Mode Query (if available)

If debug mode has event query commands, you can use them interactively:

```bash
bleep -m debug --no-connect
```

Then in the debug shell, query events (if commands are available).

### Method 4: Check Agent Registration Status

Verify that the agent is properly registered and the signals manager has the agent instance:

```python
from bleep.dbuslayer.signals import system_dbus__bluez_signals
from bleep.dbuslayer.agent import create_agent
import dbus

bus = dbus.SystemBus()
signals = system_dbus__bluez_signals()

# Check if unified monitoring is enabled
print(f"Unified monitoring enabled: {signals._unified_monitoring}")

# Create and register agent
agent = create_agent(bus, 'simple', 'KeyboardOnly', default=True)

# Check if agent is registered with signals manager
print(f"Agent instance registered: {signals._agent_instance is not None}")
if signals._agent_instance:
    print(f"Agent path: {signals._agent_instance.agent_path}")
    print(f"Agent capabilities: {signals._agent_instance._capabilities}")
    print(f"Agent registered: {signals._agent_instance._is_registered}")
```

## Expected Behavior During PIN Code Request

### Scenario 1: Agent Capability Supports PIN Code (KeyboardOnly)

1. **RequestPinCode Signal** → Captured and logged
2. **RequestPinCode Method Call** → Agent method is invoked, logged with device path
3. **Agent Returns PIN** → Method return captured
4. **Pairing Proceeds** → Connection established (or fails with different error)

### Scenario 2: Agent Capability Does NOT Support PIN Code (DisplayOnly)

1. **RequestPinCode Signal** → Captured and logged
2. **RequestPinCode Method Call** → **NOT invoked** (BlueZ rejects due to capability)
3. **Cancel Method Call** → Captured and logged
4. **Correlation Analysis** → Shows "Agent method RequestPinCode was NOT invoked (capability mismatch)"
5. **Root Cause Summary** → Explains capability mismatch

### Scenario 3: Agent Not Registered

1. **RequestPinCode Signal** → Captured and logged
2. **Warning** → "Agent not registered when RequestPinCode arrived"
3. **Cancel Method Call** → May or may not occur
4. **Correlation Analysis** → Shows agent not registered

## Key Indicators of Successful Tracking

✅ **Unified monitoring enabled** message in agent registration output  
✅ **Agent instance registered** message in logs  
✅ **RequestPinCode events** appear in logs (both signal and method call if invoked)  
✅ **Cancel events** are captured and correlated with RequestPinCode  
✅ **Root cause analysis** summary appears when Cancel follows RequestPinCode  
✅ **Device connection state** is tracked and reported  
✅ **Agent method invocation status** is clearly indicated  

## Troubleshooting

### No Events Captured

- Verify unified monitoring is enabled: Check for `[+] Unified D-Bus monitoring enabled` message
- Check agent registration: Verify agent is registered with `agent status` command (if available)
- Check permissions: Some D-Bus operations may require root or policy changes

### Events Captured But No Correlation

- Verify agent instance is registered: Check `signals._agent_instance is not None`
- Check time window: Correlation window is 5 seconds by default
- Verify Cancel follows RequestPinCode: Correlation only occurs if Cancel is received

### Agent Method Not Invoked

- Check agent capabilities: `KeyboardOnly` supports `RequestPinCode`, `DisplayOnly` does not
- Verify agent registration: Agent must be registered as default to receive requests
- Check BlueZ logs: BlueZ may reject the request before it reaches the agent

## Log File Locations

- **Agent Log**: `~/.local/share/bleep/logs/agent.log` (or `/tmp/bti__logging__agent.txt`)
- **Debug Log**: `~/.local/share/bleep/logs/debug.log` (or `/tmp/bti__logging__debug.txt`)
- **General Log**: `~/.local/share/bleep/logs/general.log` (or `/tmp/bti__logging__general.txt`)

## Additional Verification Commands

### Check Unified Monitoring Status

```python
from bleep.dbuslayer.signals import system_dbus__bluez_signals
signals = system_dbus__bluez_signals()
print(f"Unified monitoring: {signals._unified_monitoring}")
print(f"Event count: {len(signals._event_aggregator._events)}")
```

### List All Recent Events

```python
from bleep.dbuslayer.signals import system_dbus__bluez_signals
signals = system_dbus__bluez_signals()
events = signals.get_recent_events(limit=20)
for event in events:
    print(f"{event.event_type}: {event.interface} {event.path}")
```

