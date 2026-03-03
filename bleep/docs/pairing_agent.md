# Pairing Agent

The enhanced pairing agent provides a powerful and flexible way to manage Bluetooth pairing and bonding operations within the BLEEP framework. This document covers the design, usage, and examples of the pairing agent system.

## Architecture

The pairing agent system consists of several interrelated components:

1. **Agent Classes**:
   - `BlueZAgent`: Base class for all agents, providing D-Bus interface implementation.
   - `SimpleAgent`: Auto-accepts all pairing requests.
   - `InteractiveAgent`: Prompts user via CLI for all decisions.
   - `EnhancedAgent`: Supports configurable callbacks for all operations.
   - `PairingAgent`: Enhanced agent with state machine and secure storage.

2. **I/O Handlers**:
   - `AgentIOHandler`: Abstract base class defining the interface.
   - `CliIOHandler`: Terminal-based user interaction.
   - `ProgrammaticIOHandler`: Callback-based programmatic control.
   - `AutoAcceptIOHandler`: Automatically accepts all requests.
   - `BruteForceIOHandler`: Iterates through candidate PINs/passkeys for brute-force pairing.

3. **Brute-Force Orchestrator**:
   - `PinBruteForcer`: Drives repeated pair/remove/re-pair cycles with candidate values.
   - `pin_range()`, `passkey_range()`, `pins_from_file()`: Iterator generators for search spaces.

4. **State Machine**:
   - `PairingStateMachine`: Manages states during the pairing process.
   - Tracks state transitions and ensures valid flows.
   - Provides callbacks for state changes and terminal states.

5. **Secure Storage**:
   - `SecureStorage`: Base class for secure data persistence.
   - `DeviceBondStore`: Manages bonding information.
   - `PairingCache`: In-memory cache for temporary pairing data.

## Using the Agent

### Command Line (Agent Mode)

The agent can be used from the command line via the `bleep agent` mode:

```bash
# Run a simple agent
bleep agent --mode=simple --cap=none

# Run an interactive agent with keyboard-display capabilities
bleep agent --mode=interactive --cap=kbdisp

# Run a pairing agent and pair with a specific device
bleep agent --mode=pairing --pair=00:11:22:33:44:55 --cap=yesno

# Set a device as trusted
bleep agent --trust=00:11:22:33:44:55

# List trusted devices
bleep agent --list-trusted

# List bonded devices (with stored keys)
bleep agent --list-bonded

# Remove bonding information for a device
bleep agent --remove-bond=00:11:22:33:44:55
```

### Programmatic API

#### Basic Usage

```python
import dbus
from bleep.dbuslayer.agent import create_agent, PairingAgent

# Create a system bus connection
bus = dbus.SystemBus()

# Create a simple auto-accepting agent
agent = create_agent(
    bus,
    agent_type="simple",
    capabilities="DisplayYesNo",
    default=True
)

# Or create a pairing agent for more control
pairing_agent = create_agent(
    bus,
    agent_type="pairing",
    capabilities="KeyboardDisplay",
    default=True,
    auto_accept=False  # Prompt for all interactions
)

# Pair with a device
success = pairing_agent.pair_device(
    device_path="/org/bluez/hci0/dev_00_11_22_33_44_55",
    set_trusted=True
)
```

#### Using Custom I/O Handler

```python
from bleep.dbuslayer.agent import create_agent
from bleep.dbuslayer.agent_io import create_io_handler

# Create a programmatic I/O handler with custom callbacks
io_handler = create_io_handler("programmatic")

# Set callbacks for specific operations
io_handler.set_callback("request_confirmation", lambda device_info, passkey: True)
io_handler.set_callback("request_authorization", lambda device_info: True)

# Create agent with the custom I/O handler
agent = create_agent(
    bus,
    agent_type="enhanced",
    io_handler=io_handler
)
```

#### Adding State Machine Callbacks

```python
from bleep.dbuslayer.agent import PairingAgent
from bleep.dbuslayer.pairing_state import PairingState

# Create pairing agent
agent = PairingAgent(bus)

# Add state machine callbacks
def on_state_change(old_state, new_state):
    print(f"State changed from {old_state.name} to {new_state.name}")

def on_pairing_complete(pairing_data):
    print(f"Pairing completed with: {pairing_data['device_info']}")
    # Save data to database or other storage

agent._state_machine.set_callback("on_state_change", on_state_change)
agent._state_machine.set_callback("on_complete", on_pairing_complete)
```

### Agent Capabilities

The agent can be registered with different capability levels:

- `NoInputNoOutput`: Agent cannot display or request input.
- `DisplayOnly`: Agent can display PINs/passkeys but not accept input.
- `KeyboardOnly`: Agent can accept input but not display.
- `DisplayYesNo`: Agent can display and accept yes/no input.
- `KeyboardDisplay`: Agent can both display and accept input (most flexible).

Choose the capability level appropriate for your use case. Most flexible is `KeyboardDisplay`, but this requires a UI capable of both displaying information and accepting input.

### Secure Storage

The pairing agent can store bonding information securely:

```python
from bleep.dbuslayer.bond_storage import DeviceBondStore

# Create bond store
bond_store = DeviceBondStore()

# Get list of bonded devices
devices = bond_store.list_bonded_devices()

# Check if a device is bonded
is_bonded = bond_store.is_device_bonded_by_address("00:11:22:33:44:55")

# Load bonding data for a device
bond_info = bond_store.load_device_bond_by_address("00:11:22:33:44:55")

# Delete bonding data
bond_store.delete_device_bond(device_path)
```

## Integration Notes

### GLib MainLoop Requirement

The pairing agent requires `GLib.MainLoop().run()` on the main thread during `pair_device()`.  This is a fundamental `dbus-python` constraint — `dbus.service.Object` method handlers are only dispatched when the mainloop is running.  The `pair_device()` method handles this automatically by creating a temporary MainLoop if no background loop is detected.

### Message Filter Incompatibility

Do NOT call `bus.add_message_filter()` before or during pairing.  The `dbus-python` message filter mechanism interferes with object-path handler dispatch, preventing `RequestPinCode` and other agent methods from firing.  If you need D-Bus monitoring, enable it only after pairing completes.

### Debug Mode Integration

In debug mode, the `pair` command stops the background GLib loop before pairing and restarts it after.  This is handled automatically by `_cmd_pair()` in `bleep/modes/debug.py`.

The debug `pair` command supports three pairing modes:

#### Mode 1: Hardcoded PIN/Passkey

```bash
pair D8:3A:DD:0B:69:B9 --pin 12345        # BR/EDR classic PIN
pair D8:3A:DD:0B:69:B9 --passkey 123456   # LE passkey
```

Uses `AutoAcceptIOHandler` to return the specified value on every
`RequestPinCode` or `RequestPasskey` callback.

#### Mode 2: Interactive Prompt

```bash
pair D8:3A:DD:0B:69:B9 --interactive
```

Uses `CliIOHandler` so the agent prompts the user for the PIN or passkey
within the debug shell terminal when BlueZ fires `RequestPinCode`.  This
mirrors BlueZ's own `simple-agent` example and works because `input()`
runs inside the D-Bus method handler on the main thread.

#### Mode 3: Brute-Force Discovery

```bash
pair D8:3A:DD:0B:69:B9 --brute                         # PIN 0000-9999
pair D8:3A:DD:0B:69:B9 --brute --range 00000-99999     # custom range
pair D8:3A:DD:0B:69:B9 --brute --passkey-brute          # passkey 000000-999999
pair D8:3A:DD:0B:69:B9 --brute --pin-list pins.txt     # dictionary attack
pair D8:3A:DD:0B:69:B9 --brute --delay 1.0              # rate limiting
pair D8:3A:DD:0B:69:B9 --brute --max-attempts 500       # cap attempts
```

Uses `PinBruteForcer` to orchestrate repeated pair/remove/re-pair cycles.
Each attempt registers a fresh `BruteForceIOHandler` with the next candidate
value.  On success, the correct value is reported and the pairing is removed
so the user can verify manually.

## Best Practices

1. **Choose the Right Agent Type**:
   - Use `SimpleAgent` for unattended operation.
   - Use `InteractiveAgent` for CLI applications.
   - Use `EnhancedAgent` for GUI applications.
   - Use `PairingAgent` when you need state machine and secure storage.

2. **Select Appropriate Capabilities**:
   - Match agent capabilities to your UI capabilities.
   - Default to `KeyboardDisplay` when in doubt.

3. **Handle State Transitions**:
   - Register callbacks for state changes to update UIs.
   - Handle terminal states (complete, failed, cancelled).

4. **Secure Bonding Information**:
   - Store bonding information securely using `DeviceBondStore`.
   - Periodically clean up old/unused bonds.

5. **Error Handling**:
   - Catch and handle `DBusException` errors during pairing.
   - Provide user-friendly error messages.
   - Implement retry logic for transient failures.

## Current Status (v2.7.1, 2026-03-01)

**Pairing is CONFIRMED WORKING** end-to-end.  BLEEP successfully pairs with target `D8:3A:DD:0B:69:B9` using PIN `12345` via the debug mode `pair` command.  The `RequestPinCode` handler fires, `AutoAcceptIOHandler` returns the configured PIN, BlueZ accepts the pairing, the device is set as trusted, and bond information is stored.

### Verified Working

- PIN code pairing with `KeyboardDisplay` capability
- `AutoAcceptIOHandler` with preconfigured PIN via `--pin` flag
- Device discovery via `GetManagedObjects()` (BLE + BR/EDR classic)
- Stale bond removal (`RemoveDevice()`) + re-discovery + re-pair
- Post-pair auto-connect with SDP enumeration and RFCOMM keepalive (BR/EDR)
- Post-pair BLE connect with GATT enumeration
- `--test` flag for PoC disconnect monitoring
- Bond storage with MAC address extraction from device path
- State machine tracking with safe terminal-state guards

### New in v2.7.1

- **Operational pair mode** (default): pairs, then auto-detects transport and connects the device for immediate shell exploration
- **`--test` flag**: preserves the original PoC pair + disconnect monitor behavior
- **Smart `connect` command**: auto-detects BR/EDR vs BLE transport, routes to appropriate connection method, falls back to SDP + keepalive for classic devices
- **Enhanced `info` command**: works with paired-but-disconnected devices via D-Bus path, showing properties, UUIDs, and connection status
- **Enhanced `disconnect` command**: cleans up keepalive sockets and all session state
- Post-pair classic flow: SDP enumeration → RFCOMM keepalive → session device state
- Transport detection from D-Bus `Device1` properties (AddressType, UUIDs, ServicesResolved)
- **Lockout-aware brute-force**: distinguishes `AuthenticationFailed` (wrong PIN) from `AuthenticationRejected` (device lockout), pauses for configurable cooldown, retries the rejected candidate
- **`--lockout-cooldown`**: configures pause duration when lockout is detected (default: 60s)
- **`--max-lockout-retries`**: limits lockout-retry cycles per candidate (default: 3)
- **`PairingAgent.last_pair_error`**: exposes D-Bus error name for precise failure classification by callers

### New in v2.7.0

- Three pairing modes: hardcoded, interactive, and brute-force
- `BruteForceIOHandler` for automated PIN/passkey iteration
- `PinBruteForcer` orchestrator with rate limiting and blocking detection
- Passkey support (`--passkey` flag) for LE devices
- Dictionary attack from file (`--pin-list`)
- Configurable brute-force range, delay, and max attempts
- Enhanced `agent status` with PIN/passkey display and invocation history
- MainLoop architecture design document for future optimization

## Common Issues and Solutions

### Agent Registration Fails

If registering an agent fails with "AlreadyExists" error:
- Another agent might be registered already (e.g. from a previous `pair` command or bluetoothctl).
- BLEEP handles this automatically by catching the error and continuing.
- If issues persist, restart the BlueZ service: `sudo systemctl restart bluetooth`

### Pairing Timeouts

If pairing times out:
- The device might be out of range or powered off.
- The device might require a different capability (e.g. `DisplayYesNo` instead of `KeyboardDisplay`).
- Try increasing the timeout: `pair MAC --pin PIN --timeout 120`
- Check BlueZ system logs: `journalctl -u bluetooth -f`

### Device Not Found

If a device is not found when trying to pair:
- Ensure the device is powered on and in discoverable/advertising mode.
- Run `scan` first to populate BlueZ's object tree.
- The `pair` command runs a 15-second auto-discovery scan with `Transport: "auto"` (BLE + BR/EDR) if the device isn't already cached.
- Classic BR/EDR inquiry requires up to 10.24 seconds — ensure the device is discoverable for at least that long.

### RequestPinCode Handler Not Firing

This issue was resolved in v2.6.2.  If encountered again, verify:
- The background GLib loop is stopped before pairing (`_stop_glib_mainloop()`)
- No message filters are registered via `bus.add_message_filter()` — they block handler dispatch
- `GLib.MainLoop().run()` is active on the main thread during pairing

### Bond Storage Error

If `Bond info must include device address` appears:
- This was fixed in v2.6.2.  Update to the latest version.
- The fix extracts the MAC address from the device path at pairing start.

## Known Limitations

1. **No unified D-Bus monitoring during pairing**: `bus.add_message_filter()` interferes with `dbus-python` handler dispatch.  Real-time D-Bus message logging is unavailable while pairing is active.

2. **Main-thread MainLoop requirement**: Agent method handlers only fire when `GLib.MainLoop().run()` is active on the main thread.  Background threads, `context.iteration()`, and polling do not work.

3. **Single concurrent pairing**: The temporary MainLoop pattern supports one pairing at a time per bus connection.

4. **Encrypted bond storage requires `cryptography` package**: Falls back to unencrypted JSON if not installed.

5. **Only `RequestPinCode` tested against real hardware**: `RequestPasskey` is now exposed via `--passkey` and `--passkey-brute` flags but not yet verified against real LE devices.  Other Agent1 methods (`RequestConfirmation`, `DisplayPasskey`, `RequestAuthorization`, `AuthorizeService`) are implemented but not yet verified.

6. **No automatic PIN persistence**: Known device PINs are not stored between sessions.  The `--pin` flag must be provided on each invocation.

7. **Brute-force rate depends on target device**: Some devices impose pairing lockout after consecutive failures, returning `AuthenticationRejected` instead of `AuthenticationFailed`.  The brute forcer now detects this transition and pauses for `--lockout-cooldown` seconds (default 60) before retrying, but the optimal cooldown duration varies by device.

## Future Work

- **MainLoop inversion**: Move GLib MainLoop to the main thread and `input()` to a worker thread, eliminating the stop/restart cycle.  See [MainLoop Architecture](./mainloop_architecture.md) for the full design.
- **Re-enable D-Bus monitoring after pairing**: Restore unified monitoring after `pair_device()` returns for subsequent D-Bus activity logging.
- **Test all Agent1 methods**: Verify `RequestPasskey`, `RequestConfirmation`, `DisplayPasskey`, etc. against devices that trigger those pairing flows.
- **PIN code persistence**: Store known PINs in the observations database for automatic reuse.
- **Multi-adapter support**: Support selecting a specific Bluetooth adapter instead of hardcoding `hci0`.
- **Async pairing API**: Expose `pair_device()` for asyncio-based applications.
- **Investigate `dbus-python` filter behavior**: Determine if the message filter interference is a bug or architectural limitation, and whether a workaround exists.
- **Profile-level connect retry**: After failed `Connect()`, attempt specific `ConnectProfile()` calls for individual UUIDs advertised by the device.
- **Keepalive socket auto-recovery**: Detect dropped keepalive sockets and re-open automatically.

## Related Documentation

- [Agent D-Bus Communication Issue](./agent_dbus_communication_issue.md): Full 5-phase investigation and resolution history
- [Mainloop Requirement Analysis](./mainloop_requirement_analysis.md): Mainloop threading and dispatch requirement discovery
- [MainLoop Architecture](./mainloop_architecture.md): Future MainLoop design — Option A (worker thread) vs Option B (stdin watch)
- [Agent Pairing Flow Analysis](./agent_pairing_flow_analysis.md): Expected vs actual pairing flow with capabilities table
- [Debug Mode](./debug_mode.md): Debug shell command reference (includes `pair` command)
- [BlueZ D-Bus API](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc/agent-api.txt): Official BlueZ agent API documentation
