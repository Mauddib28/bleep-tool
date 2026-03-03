# Agent D-Bus Communication Issue - Consolidated Analysis

**STATUS: RESOLVED (v2.6.2, 2026-02-28)** — All issues fixed.  Pairing works end-to-end.

## Problem Summary (Historical)

BLEEP's agent received `RequestPinCode` METHOD CALLs from BlueZ (verified via destination matching), but the Python agent methods were never invoked. This resulted in:
- No agent method entry point logs
- No IO handler logs  
- No METHOD RETURN sent to BlueZ
- BlueZ timeout (~7 seconds) followed by Cancel signal

## Root Cause: Methods Not Registered on D-Bus

### Evidence

1. **D-Bus Introspection Returns Empty XML**:
   ```bash
   $ python3 -c "import dbus; bus = dbus.SystemBus(); obj = bus.get_object('org.bluez', '/test/agent'); intro = dbus.Interface(obj, 'org.freedesktop.DBus.Introspectable'); print(intro.Introspect())"
   ```
   **Result**: `<node></node>` (EMPTY - no methods registered)

2. **Agent Methods Never Invoked**:
   - ✅ Unified monitoring captures `METHOD CALL: RequestPinCode` (via eavesdropping)
   - ✅ Destination verification confirms BlueZ is calling BLEEP's agent
   - ❌ Agent entry point logs never appear
   - ❌ IO handler logs never appear

3. **Test Confirms Issue**:
   Even minimal test script shows methods don't register, confirming this is a `dbus.service.Object` registration issue.

### Why Methods Aren't Registered

When `dbus.service.Object.__init__(bus, path)` is called, it should:
1. Register the object on D-Bus
2. Discover methods decorated with `@dbus.service.method`
3. Register methods with D-Bus
4. Generate introspection XML automatically

**This is NOT happening in BLEEP**, even though:
- `super().__init__(bus, agent_path)` is called correctly
- Methods are properly decorated with `@dbus.service.method`
- D-Bus mainloop is set before bus creation
- Bus is created after mainloop is set

**Test Results**: Even a minimal test agent (identical pattern to BlueZ scripts) shows methods don't register, suggesting this is a deeper D-Bus registration issue, not specific to BLEEP's implementation pattern.

## Comparison with BlueZ Reference Scripts

### BlueZ `simple-agent` (WORKING)

```python
# Line 134: Set mainloop FIRST
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Line 136: Create bus AFTER mainloop
bus = dbus.SystemBus()

# Line 155: Create agent (NO explicit __init__ - uses default)
agent = Agent(bus, path)

# Line 157: Create mainloop object
mainloop = GObject.MainLoop()

# Line 161: Register with BlueZ
manager.RegisterAgent(path, capability)

# Line 181: Run mainloop (KEEPS AGENT ALIVE)
mainloop.run()
```

**Key Points**:
- Agent class has NO `__init__` method - relies on default `dbus.service.Object.__init__()`
- Mainloop runs immediately after registration
- Agent object is kept alive by mainloop

### BLEEP Implementation (NOT WORKING)

```python
# Line 181: Set mainloop FIRST
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Line 183: Create bus AFTER mainloop
bus = dbus.SystemBus()

# Line 278: Create agent (via factory function)
agent = create_agent(...)
    # Inside: super().__init__(bus, agent_path) is called explicitly

# Line 346: Create mainloop (ONLY if args.default)
if args.default:
    loop = GLib.MainLoop()
    loop.run()
```

**Key Differences**:
- Agent class HAS explicit `__init__` with `super().__init__()` call
- Mainloop only runs if `args.default` is True (but user is using `--default`)
- Agent created via factory function instead of direct instantiation

### Other BlueZ Scripts

- `test-profile`: No `__init__` - relies on default `dbus.service.Object.__init__()`
- `simple-obex-agent`: Has explicit `__init__` with `dbus.service.Object.__init__(self, conn, obj_path)`
- `test-mesh`: Has explicit `__init__` with `dbus.service.Object.__init__(self, bus, self.path)`

**Conclusion**: Both patterns (with/without explicit `__init__`) exist in BlueZ scripts, so this is NOT the issue. Test results show even minimal agents following BlueZ patterns fail to register methods, suggesting a deeper D-Bus configuration or environment issue.

## Current Status

### Completed Diagnostic Enhancements

1. **Destination Verification** ✅:
   - Logs bus unique name at agent creation and registration
   - Compares METHOD CALL destination with BLEEP's bus unique name
   - Confirmed: BlueZ IS calling BLEEP's agent (destination matches)

2. **Communication Type Logging** ✅:
   - Fixed D-Bus communication type labeling (METHOD CALL vs SIGNAL)
   - Added validation to ensure correct event type assignment

3. **Agent Method Invocation Tracking** ✅:
   - Added method invocation tracking in `BlueZAgent` class
   - Added capability validation warnings
   - Added expected methods logging

4. **Event Correlation** ✅:
   - Automatic RequestPinCode → Cancel correlation
   - Device connection state correlation
   - Root cause analysis summaries

5. **IO Handler Logging** ✅:
   - Added entry point logging to all IO handler methods
   - Added log flushing to prevent buffering
   - Enhanced exception handling

### Issue Resolution — Phase 1 (agent.py mode)

**Partial Root Cause**: The mainloop object (`GLib.MainLoop()`) must exist **before** agent creation and registration.  This matches the pattern used in all working BlueZ reference scripts (`simple-agent`, `test-profile`, `simple-obex-agent`).

**Solution Implemented (agent.py only)**: Modified `bleep/modes/agent.py` to create the mainloop object before agent creation and run it on the **main thread**.  This fixed pairing in `agent` mode.

### Issue Resolution — Phase 2 (debug.py mode — CONFIRMED FIX 2026-02-28)

**Full Root Cause Identified**: `dbus-python`'s `dbus.service.Object` method dispatch (the mechanism that routes incoming D-Bus METHOD CALLs to decorated Python methods) **only works when the GLib default `MainContext` is iterated on the main thread**.  Message filters (`bus.add_message_filter()`) use a different `libdbus` dispatch path and work on any thread, which is why BLEEP's signal monitoring correctly observed `RequestPinCode` arriving but the handler never fired.

**Evidence — Baseline Test**: Running BlueZ's `simple-agent` (which iterates the mainloop on the main thread) against target `D8:3A:DD:0B:69:B9` confirmed:
```
RequestPinCode (/org/bluez/hci0/dev_D8_3A_DD_0B_69_B9)
Enter PIN Code: 12345
Device paired
```
Pairing succeeded.  The system-level D-Bus configuration, PIN code, and BlueZ agent protocol all work correctly.

**Root Cause in debug.py**: `_cmd_pair()` called `_ensure_glib_mainloop()` which starts a **background daemon thread** running `GLib.MainLoop().run()`.  `pair_device()` then detected the background loop and entered a `time.sleep()` polling path, never iterating the GLib context on the main thread.  Result: `RequestPinCode` arrived at the process but was never dispatched to the Python handler.

**Fix Applied**: Two-line change in `bleep/modes/debug.py` → `_cmd_pair()`:
1. **Before agent creation**: call `_stop_glib_mainloop()` instead of `_ensure_glib_mainloop()`.  This stops the background loop and releases the GLib default `MainContext`.
2. **After `pair_device()` returns**: call `_ensure_glib_mainloop()` to restart the background loop for shell callback dispatch.

With the background loop stopped, `pair_device()` takes its `bg_loop_running = False` code path on the main thread.

### Issue Resolution — Phase 3 (context.iteration broken — PoC CONFIRMED 2026-02-28)

**Discovery**: After Phase 2, pairing still failed.  Log analysis showed message filters logged `RequestPinCode` arrival, but the `RequestPinCode` Python handler on the agent object **still** never executed.  The `context.iteration(False)` approach dispatches messages through `dbus_connection_add_filter()` callbacks but does **not** trigger `dbus.service.Object` object-path handlers.

**PoC Validation**: A standalone script using a temporary `GLib.MainLoop` with `GLib.timeout_add()` for controlled quitting successfully paired with `D8:3A:DD:0B:69:B9`:
```
[*] Agent registered, pairing with D8:3A:DD:0B:69:B9 using PIN 12345
[HANDLER] RequestPinCode(/org/bluez/hci0/dev_D8_3A_DD_0B_69_B9) -> returning '12345'
[+] Pair reply: SUCCESS
[+] PAIRED!
```

**Root Cause (refined)**: `GLib.MainContext.default().iteration(False)` only processes GLib event sources (IO watches, timeouts) and `dbus_connection_add_filter()` callbacks.  It does NOT trigger the full `dbus_connection_dispatch()` → object-tree lookup → `dbus.service.Object._message_cb()` chain.  Only `GLib.MainLoop().run()` drives the complete dispatch path.

**Fix Applied to `pair_device()` in `bleep/dbuslayer/agent.py`**: Replaced the `context.iteration(False)` loop with a temporary `GLib.MainLoop`:
```python
tmp_loop = GLib.MainLoop()

def _poll_result():
    nonlocal next_log
    if pair_result["done"]:
        tmp_loop.quit()
        return False
    # ... timeout and logging checks ...
    return True

GLib.timeout_add(100, _poll_result)
tmp_loop.run()
```

The `GLib.timeout_add(100, _poll_result)` callback checks every 100ms for completion or timeout and quits the loop.  This is the same dispatch mechanism used by `simple-agent` and the PoC, and is the only reliable way to dispatch `dbus.service.Object` method handlers in `dbus-python`.

**Combined fix summary (debug.py + agent.py)**:
1. `_cmd_pair()` stops the background GLib loop (`_stop_glib_mainloop()`)
2. `pair_device()` detects no background loop → creates a temporary `GLib.MainLoop` → runs it
3. `MainLoop.run()` dispatches all D-Bus events including object-path handlers
4. `_poll_result()` quits the loop when pairing completes or times out
5. `_cmd_pair()` restarts the background loop (`_ensure_glib_mainloop()`)

### Issue Resolution — Phase 4 (message filter interference — CONFIRMED 2026-02-28)

**Discovery**: After Phase 3 fix was integrated into BLEEP, pairing still failed with `RequestPinCode` arriving at the process (logged by message filters) but the Python handler never executing.  A diagnostic PoC script (`poc_pair_diag.py`) was created to systematically test hypotheses.

**Hypotheses tested and results**:

| Hypothesis | Test | Result |
|-----------|------|--------|
| `sudo` required for `Agent1` response | Non-root PoC without filter | **Handler fired, pairing succeeded** — `sudo` NOT required |
| `eavesdrop='true'` match rules interfere | Non-root + eavesdrop rules | `AccessDenied` — rules silently fail for non-root, never active in BLEEP |
| Generic message filter (`_on_dbus_message`) blocks dispatch | Non-root + message filter active | Handler did NOT fire — **confirmed** |

**Root cause**: `enable_unified_dbus_monitoring()` in `bleep/dbuslayer/signals.py` calls `bus.add_message_filter(_on_dbus_message)`.  Despite the filter returning `None` (which should mean `DBUS_HANDLER_RESULT_NOT_YET_HANDLED`), its presence interferes with `dbus-python`'s object-path handler dispatch chain.  This is a `dbus-python` behavioral quirk: when a message filter is registered, the `libdbus` dispatch pipeline processes the filter first, and the subsequent object-path dispatch does not reliably trigger `dbus.service.Object._message_cb()`.

**Fix applied to `bleep/dbuslayer/agent.py`**: In `ensure_default_pairing_agent()`, disabled `enable_unified_dbus_monitoring(True)`.  Only `signals_instance.register_agent(self)` is called for correlation tracking.  Monitoring can be re-enabled after pairing completes if needed.

### Issue Resolution — Phase 5 (device discovery + bond storage — CONFIRMED 2026-02-28)

**Discovery**: After Phase 4 fix, BLEEP returned `UnknownObject: Method "Pair" with signature "" on interface "org.bluez.Device1" doesn't exist`.  The `RequestPinCode` handler dispatch issue was resolved but never reached because `Pair()` was called on a non-existent D-Bus object.

**Root cause (device discovery)**: When the target device was not in BlueZ's object tree (removed by prior `RemoveDevice` calls), `_cmd_pair()` fell through to a "last resort" code path that fabricated a D-Bus path from the MAC address: `/org/bluez/hci0/dev_D8_3A_DD_0B_69_B9`.  This path had no `Device1` interface because the object didn't exist.  The BlueZ reference `bluezutils.find_device()` explicitly avoids this pattern — it queries `GetManagedObjects()` and raises an exception if the device isn't found.

**Fix applied to `bleep/modes/debug.py`**: Replaced internal cache lookup + path fabrication with `GetManagedObjects()` query (matching `bluezutils.find_device()` pattern).  Added `Transport: "auto"` discovery filter and 15-second scan covering both BLE and BR/EDR.  Clear error message on discovery failure.  Fixed post-`RemoveDevice` re-discovery with the same pattern.

**Root cause (bond storage)**: `PairingStateMachine.start_pairing()` initialized `_pairing_data` without an `"address"` key.  After successful pairing, `_on_pairing_complete` → `save_device_bond()` raised `ValueError("Bond info must include device address")`.  The pairing itself succeeded at the BlueZ level (device paired + trusted) but `pair_device()` returned `False` due to the exception.

**Fix applied to `bleep/dbuslayer/pairing_state.py`**: `start_pairing()` now extracts the MAC address from `device_path` and includes it in `_pairing_data`.

**CONFIRMED WORKING**: Terminal output shows successful end-to-end pairing:
```
[!!!] RequestPinCode METHOD ENTRY POINT REACHED - Agent method invoked by BlueZ
[*] AutoAcceptIOHandler: PIN request for DingoMan (D8:3A:DD:0B:69:B9) default_pin='12345'
[+] AutoAcceptIOHandler: Returning PIN code: '12345'
[+] Pair() D-Bus reply received (success)
[+] Successfully paired with DingoMan (D8:3A:DD:0B:69:B9)
[+] Device DingoMan (D8:3A:DD:0B:69:B9) set as trusted
```

### Final Confirmed Working Output (v2.6.2)

Clean end-to-end pairing with all fixes applied:
```
BLEEP-DEBUG> pair D8:3A:DD:0B:69:B9 --pin 12345
[*] Pair target: D8:3A:DD:0B:69:B9  PIN: 12345  capability: KeyboardDisplay  timeout: 60s
[*] Device D8:3A:DD:0B:69:B9 already paired – removing stale bond first
[*] Re-discovering D8:3A:DD:0B:69:B9 after bond removal…
[*] Attempting to pair with DingoMan (D8:3A:DD:0B:69:B9)
[!!!] RequestPinCode METHOD ENTRY POINT REACHED - Agent method invoked by BlueZ
[+] AutoAcceptIOHandler: Returning PIN code: '12345'
[+] Pair() D-Bus reply received (success)
[+] Successfully paired with DingoMan (D8:3A:DD:0B:69:B9)
[+] Device DingoMan (D8:3A:DD:0B:69:B9) set as trusted
[+] Paired with D8:3A:DD:0B:69:B9 successfully
[*] Device D8:3A:DD:0B:69:B9 connected – monitoring for auto-disconnect…
[!] Device D8:3A:DD:0B:69:B9 disconnected after 9s
```

## Resolution Summary

| Phase | Root Cause | Fix | Status |
|-------|-----------|-----|--------|
| 1 | Background-thread MainLoop doesn't dispatch handlers | Stop bg loop before pairing, restart after | ✅ Fixed |
| 2 | `context.iteration(False)` doesn't dispatch handlers | PoC confirmed temporary `MainLoop.run()` works | ✅ Fixed |
| 3 | Only `GLib.MainLoop().run()` drives full dispatch | Replaced `context.iteration()` with temp MainLoop in `pair_device()` | ✅ Fixed |
| 4 | `bus.add_message_filter()` blocks handler dispatch | Disabled unified monitoring during agent registration | ✅ Fixed |
| 5a | Fabricated device paths → `UnknownObject` error | `GetManagedObjects()` query + proper discovery scan | ✅ Fixed |
| 5b | Missing `address` in pairing data → bond storage error | Extract MAC from device path in `start_pairing()` | ✅ Fixed |
| 6 | `COMPLETE → FAILED` invalid state transition | `_safe_transition_failed()` guard in `pair_device()` | ✅ Fixed |

## Related Documentation

- `mainloop_requirement_analysis.md` - Mainloop threading and dispatch requirement discovery
- `agent_pairing_flow_analysis.md` - Current pairing flow with capabilities and limitations
- `pairing_agent.md` - Agent architecture, API reference, limitations, and future work
- `pincode_tracking_verification.md` - Manual verification procedures
- `unified_dbus_event_aggregator.md` - D-Bus monitoring system
- `debug_mode.md` - Debug shell command reference (includes `pair` command)
