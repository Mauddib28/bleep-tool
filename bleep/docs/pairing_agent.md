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

3. **State Machine**:
   - `PairingStateMachine`: Manages states during the pairing process.
   - Tracks state transitions and ensures valid flows.
   - Provides callbacks for state changes and terminal states.

4. **Secure Storage**:
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

## Integration with D-Bus Reliability Framework

The pairing agent integrates with the D-Bus reliability framework to provide robust operation:

- Timeout enforcement ensures pairing operations don't hang.
- Connection pooling allows efficient use of D-Bus connections.
- Recovery mechanisms handle BlueZ service stalls or restarts.
- Metrics collection helps identify issues with pairing operations.

When using the pairing agent in production environments, consider enabling the reliability features:

```python
from bleep.dbus.timeout_manager import with_timeout
from bleep.dbuslayer.bluez_monitor import BlueZMonitor
from bleep.core.metrics import MetricsCollector

# Create metrics collector
metrics = MetricsCollector("pairing_agent")

# Create agent
agent = create_agent(bus, agent_type="pairing")

# Set up BlueZ monitor
monitor = BlueZMonitor(bus)
monitor.add_callback("stalled", lambda: print("BlueZ service stalled"))

# Use with_timeout decorator on critical methods
pair_device_with_timeout = with_timeout(agent.pair_device, timeout=30)
success = pair_device_with_timeout(device_path, set_trusted=True)
```

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

## Common Issues and Solutions

### Agent Registration Fails

If registering an agent fails with "AlreadyExists" error:
- Another agent might be registered already.
- Try unregistering the existing agent or using a different path.

### Pairing Timeouts

If pairing times out:
- The device might be out of range or powered off.
- The device might have too strict security requirements.
- Try increasing the timeout or simplifying the security requirements.

### Device Not Found

If a device is not found when trying to pair:
- Ensure the device is discoverable.
- Try running discovery before pairing.
- Check that the address is correct (case-sensitive).

## Related Documentation

- [BlueZ D-Bus API](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc/agent-api.txt): Official BlueZ agent API documentation.
- [D-Bus Reliability Framework](./d-bus-reliability.md): Documentation on D-Bus reliability features.
