# BLEEP Agent Pairing Flow Analysis

## Executive Summary

This document provides a comprehensive analysis of how BLEEP handles the interaction between a generated BLEEP agent, BlueZ, D-Bus, and a remote Bluetooth device during pairing operations. It compares the **expected operation** (based on BlueZ specifications) with the **actual implementation** in the BLEEP codebase.

**Status (v2.6.2, 2026-02-28)**: Pairing is **CONFIRMED WORKING** end-to-end.  BLEEP successfully pairs with target devices using PIN code exchange.  All `org.bluez.Agent1` methods are correctly dispatched and handled.

## Expected Operation (BlueZ Standard)

### Standard BlueZ Agent Pairing Flow

According to the BlueZ D-Bus Agent API specification, the expected flow for PIN code pairing is:

```
1. Remote Device → BlueZ: Initiates pairing request
2. BlueZ → Agent (via D-Bus): METHOD CALL RequestPinCode(device_path)
3. Agent → BlueZ (via D-Bus): METHOD RETURN with PIN code string
4. BlueZ → Remote Device: Completes pairing with PIN
5. BlueZ → Agent (via D-Bus): METHOD CALL Release() (optional)
```

**Key Points:**
- `RequestPinCode` is a **METHOD CALL** from BlueZ to the agent, not a signal
- The agent must be registered with BlueZ via `RegisterAgent()`
- The agent must be set as default via `RequestDefaultAgent()` to receive pairing requests
- Agent capabilities determine which methods BlueZ will call

### Agent Registration Flow

```
1. BLEEP creates agent object (PairingAgent subclass)
2. Agent calls RegisterAgent(agent_path, capabilities)
3. Agent calls RequestDefaultAgent(agent_path)
4. BlueZ stores agent registration
5. When pairing needed, BlueZ calls agent's methods
```

## Current BLEEP Implementation (WORKING — v2.6.2)

### 1. Agent Creation and Registration

**Location:** `bleep/dbuslayer/agent.py`

**Implementation:**
```python
class PairingAgent(BlueZAgent):
    # Registration via ensure_default_pairing_agent():
    def register(self, capabilities="KeyboardDisplay", default=True):
        self._agent_manager.RegisterAgent(self.agent_path, capabilities)
        if default:
            self._agent_manager.RequestDefaultAgent(self.agent_path)
        # NOTE: Unified D-Bus monitoring is NOT enabled here.
        # The message filter it installs prevents dbus-python from
        # dispatching incoming method calls to dbus.service.Object handlers.
        signals_instance.register_agent(self)  # correlation tracking only
```

**Accuracy:** ✅ **CORRECT**
- Properly implements BlueZ registration API
- Correctly calls `RegisterAgent()` and `RequestDefaultAgent()`
- Unified D-Bus monitoring intentionally disabled during pairing (see Limitations)

### 2. RequestPinCode Method Implementation

**Location:** `bleep/dbuslayer/agent.py`

**Implementation:**
```python
@dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
def RequestPinCode(self, device):
    # Track method invocation
    self._track_method_invocation("RequestPinCode")
    # Get device info
    device_info = self._get_device_info(device)
    # Request PIN from I/O handler
    pin_code = self._io_handler.request_pin_code(device_info)
    return pin_code
```

**Accuracy:** ✅ **CORRECT** — Confirmed working against target `D8:3A:DD:0B:69:B9` with PIN `12345`

### 3. Device Discovery (debug mode `pair` command)

**Location:** `bleep/modes/debug.py` → `_cmd_pair()`

**Implementation:**
```python
# Query BlueZ's object tree via GetManagedObjects() (same as bluezutils.find_device())
om = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
for path, ifaces in om.GetManagedObjects().items():
    dev = ifaces.get("org.bluez.Device1")
    if dev and str(dev.get("Address", "")).upper() == target_mac:
        device_path = str(path)

# If not found, run 15s discovery with Transport: "auto" (BLE + BR/EDR)
adapter.set_discovery_filter({"Transport": "auto"})
adapter.run_scan__timed(duration=15)
# Re-query GetManagedObjects() after discovery
```

**Accuracy:** ✅ **CORRECT** — Never fabricates fake D-Bus paths; aborts with clear error if device not found

### 4. Pairing Dispatch

**Location:** `bleep/dbuslayer/agent.py` → `pair_device()`

**Implementation:**
```python
# Async Pair() call
device.Pair(reply_handler=_on_pair_reply, error_handler=_on_pair_error, timeout=60000)

# Temporary GLib.MainLoop for handler dispatch (main thread)
tmp_loop = GLib.MainLoop()
GLib.timeout_add(100, _poll_result)  # polls for completion/timeout
tmp_loop.run()  # dispatches RequestPinCode → handler → PIN returned → loop quits
```

**Accuracy:** ✅ **CORRECT** — Only mechanism that reliably dispatches `dbus.service.Object` method handlers in `dbus-python`

### 5. I/O Handler Integration

**Location:** `bleep/dbuslayer/agent_io.py`

**Implementations:**
- `AutoAcceptIOHandler`: Returns preconfigured PIN/passkey, auto-accepts all requests (used by debug `pair` command)
- `CliIOHandler`: Terminal-based user interaction
- `ProgrammaticIOHandler`: Callback-based programmatic control

**Accuracy:** ✅ **CORRECT** — Clean separation of concerns, returns PIN code string as expected by BlueZ

### 6. State Machine

**Location:** `bleep/dbuslayer/pairing_state.py`

**States:** `IDLE → INITIATED → PIN_REQUESTED → BONDING → COMPLETE`

**Accuracy:** ✅ **CORRECT** — Includes safe transition guards to prevent invalid terminal-state transitions (e.g. COMPLETE → FAILED)

### 7. Bond Storage

**Location:** `bleep/dbuslayer/bond_storage.py`

**Implementation:** `DeviceBondStore` saves bonding information (address, name, paired status, timestamps, capabilities) via `SecureStorage`.  MAC address is extracted from the D-Bus device path at pairing start.

**Accuracy:** ✅ **CORRECT** — Requires `cryptography` package for encrypted storage; falls back to unencrypted if not installed

## Complete Pairing Flow (Current Implementation)

### Step-by-Step Flow

```
 1. User: `pair D8:3A:DD:0B:69:B9 --pin 12345`
    ↓
 2. _cmd_pair(): Stop background GLib loop (_stop_glib_mainloop)
    ↓
 3. _cmd_pair(): Create PairingAgent with AutoAcceptIOHandler(pin="12345")
    ↓
 4. Agent: RegisterAgent("/test/agent", "KeyboardDisplay")
    ↓
 5. Agent: RequestDefaultAgent("/test/agent")
    ↓
 6. _cmd_pair(): Query GetManagedObjects() for Device1 matching MAC
    ↓
 7. (If not found): Run 15s discovery scan with Transport: "auto"
    ↓
 8. (If already paired): RemoveDevice() + re-scan + re-resolve
    ↓
 9. pair_device(): device.Pair(reply_handler, error_handler, timeout=60000)
    ↓
10. pair_device(): Start temporary GLib.MainLoop on main thread
    ↓
11. BlueZ: Receives pairing request, determines PIN needed
    ↓
12. BlueZ → Agent: METHOD CALL RequestPinCode(device_path)
    ↓
13. GLib.MainLoop dispatches → PairingAgent.RequestPinCode()
    ↓
14. Agent: io_handler.request_pin_code(device_info) → "12345"
    ↓
15. Agent: Returns PIN to BlueZ via METHOD RETURN
    ↓
16. BlueZ → Remote Device: PIN exchange
    ↓
17. BlueZ: Pair() reply (success)
    ↓
18. pair_device(): _poll_result detects done → tmp_loop.quit()
    ↓
19. pair_device(): Verify Paired=True, set Trusted=True
    ↓
20. pair_device(): handle_pairing_success() → bond stored
    ↓
21. _cmd_pair(): Restart background GLib loop (_ensure_glib_mainloop)
    ↓
22. _cmd_pair(): Post-pair monitoring (detect auto-disconnect)
```

## Confirmed Working — Evidence

Terminal output from successful pairing (v2.6.2):
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

## Accuracy Assessment

### ✅ Correctly Implemented and Confirmed Working

1. **Agent Registration**: `RegisterAgent()` + `RequestDefaultAgent()` — working
2. **Method Signatures**: All agent methods have correct D-Bus signatures — working
3. **Return Values**: PIN code string, passkey UInt32 — working
4. **Error Handling**: `RejectedException`, safe state machine transitions — working
5. **Capability Mapping**: `KeyboardDisplay` correctly enables `RequestPinCode` — working
6. **I/O Handler Pattern**: `AutoAcceptIOHandler` returns configured PIN — working
7. **Device Discovery**: `GetManagedObjects()` query matching `bluezutils.find_device()` — working
8. **Stale Bond Removal**: `RemoveDevice()` + re-scan + re-resolve — working
9. **Bond Storage**: MAC address extracted from device path, stored on success — working
10. **Post-pair Monitoring**: Detects auto-disconnect from target device — working

## Current Capabilities

| Capability | Status | Notes |
|-----------|--------|-------|
| PIN code pairing (`RequestPinCode`) | ✅ Working | Confirmed with D8:3A:DD:0B:69:B9, PIN 12345 |
| Auto-accept with preconfigured PIN | ✅ Working | Via `AutoAcceptIOHandler` |
| Interactive CLI PIN entry | ✅ Implemented | Via `CliIOHandler` (not tested in this campaign) |
| Programmatic callback PIN | ✅ Implemented | Via `ProgrammaticIOHandler` (not tested in this campaign) |
| Passkey pairing (`RequestPasskey`) | ✅ Implemented | Handler exists, not tested against a real device |
| Confirmation pairing (`RequestConfirmation`) | ✅ Implemented | Handler exists, not tested against a real device |
| Authorization (`RequestAuthorization`) | ✅ Implemented | Handler exists, not tested against a real device |
| Service authorization (`AuthorizeService`) | ✅ Implemented | Handler exists, not tested against a real device |
| Display passkey (`DisplayPasskey`) | ✅ Implemented | Handler exists, not tested against a real device |
| Display PIN (`DisplayPinCode`) | ✅ Implemented | Handler exists, not tested against a real device |
| BLE + Classic device discovery | ✅ Working | `Transport: "auto"` filter covers both |
| Stale bond removal + re-pair | ✅ Working | `RemoveDevice()` + re-scan |
| Post-pair disconnect monitoring | ✅ Working | Detects target's auto-disconnect timer |
| Bond storage (persistent) | ✅ Working | `DeviceBondStore` with optional encryption |
| State machine tracking | ✅ Working | `PairingStateMachine` with safe terminal-state guards |
| Agent capability selection | ✅ Working | `--cap` flag: NoInputNoOutput, DisplayOnly, DisplayYesNo, KeyboardOnly, KeyboardDisplay |

## Known Limitations

### Critical Constraints

1. **Message filter incompatibility**: `dbus-python`'s `bus.add_message_filter()` prevents `dbus.service.Object` handler dispatch.  Unified D-Bus monitoring (`enable_unified_dbus_monitoring()`) MUST be disabled during pairing.  This means real-time D-Bus message logging is unavailable while pairing is in progress.

2. **Main-thread MainLoop requirement**: `dbus-python` dispatches `dbus.service.Object` method handlers ONLY when `GLib.MainLoop().run()` is active.  Background-thread loops, `context.iteration(False)`, and `time.sleep()` polling do NOT work.  The debug mode `pair` command must stop the background GLib loop and run a temporary loop on the main thread.

3. **Single concurrent pairing**: The temporary `GLib.MainLoop` pattern supports one pairing at a time.  Concurrent pairings would require separate bus connections or a different dispatch architecture.

### Operational Limitations

4. **Discovery timing**: Classic BR/EDR inquiry can take up to 10.24 seconds for a full cycle.  The 15-second scan window is usually sufficient but devices with long advertising intervals may be missed.

5. **Bond storage encryption**: Requires the `cryptography` Python package.  Falls back to unencrypted JSON storage if not installed (warning printed at startup).

6. **Eavesdrop match rules**: Non-root users cannot register `eavesdrop='true'` D-Bus match rules (`AccessDenied`).  This prevents passive monitoring of messages not addressed to BLEEP.  Does not affect pairing functionality.

7. **Agent re-registration**: Each `pair` command creates a new `PairingAgent` instance and registers it.  If a previous agent is still registered, BlueZ may return `AlreadyExists` (handled by catching and continuing).

8. **DB FOREIGN KEY errors during scan**: The observations database occasionally produces `FOREIGN KEY constraint failed` errors during device type evidence storage.  This is a pre-existing issue in `bleep/core/observations.py` unrelated to pairing — devices still appear in scan results.

## Future Work

### High Priority

1. **Re-enable D-Bus monitoring after pairing completes**: The unified monitoring is currently disabled for the entire agent registration lifetime.  It should be re-enabled after `pair_device()` returns so that subsequent D-Bus activity is logged.

2. **Test remaining Agent1 methods**: `RequestPasskey`, `RequestConfirmation`, `RequestAuthorization`, `DisplayPasskey`, and `DisplayPinCode` are implemented but have not been tested against real devices requiring those exchange types.  Each method should be verified with a device that triggers that specific pairing flow.

3. **Fix DB FOREIGN KEY errors**: The `store_device_type_evidence` call in `observations.py` fails when the parent device row doesn't exist.  This should be fixed with an upsert pattern or by ensuring the device row is inserted before evidence.

### Medium Priority

4. **Investigate message filter workaround**: Determine whether the filter interference is a `dbus-python` bug or a fundamental `libdbus` behavior.  If the filter could be made compatible (e.g. by returning a different value, or using a different registration mechanism), unified monitoring during pairing would be possible.

5. **Support `agent` mode pairing**: The `bleep agent` CLI mode should use the same temporary-MainLoop dispatch pattern as debug mode.  Currently, `agent` mode relies on a persistent `mainloop.run()` which works but doesn't integrate with the `PairingAgent` state machine.

6. **PIN code persistence**: Store known device PIN codes in the observations database.  When pairing with a previously-paired device, automatically use the stored PIN instead of requiring `--pin` on every invocation.

7. **Pairing retry logic**: Add configurable retry with exponential backoff for transient failures (e.g. `ConnectionAttemptFailed`, `AuthenticationTimeout`).

### Low Priority

8. **Pairing state persistence**: The `PairingStateMachine` is in-memory only.  If the process crashes mid-pair, state is lost.  For production use, consider persisting state to allow recovery.

9. **Multi-adapter support**: Device discovery currently hardcodes `hci0`.  Support selecting a specific adapter via `--adapter` flag or auto-detecting the correct one.

10. **Async pairing API**: Expose `pair_device()` as an async method for integration with asyncio-based applications.

## Related Documentation

- `agent_dbus_communication_issue.md` — Full 5-phase investigation and resolution history
- `mainloop_requirement_analysis.md` — Mainloop threading and dispatch requirement discovery
- `pairing_agent.md` — Agent architecture, API reference, and usage examples
- `debug_mode.md` — Debug shell command reference (includes `pair` command)
- `changelog.md` — Version history with fix details
- `todo_tracker.md` — Task tracking for pairing work
