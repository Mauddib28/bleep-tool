# Network Capability Integration - Summary

## Overview

This document summarizes the plan to integrate Bluetooth Network (PAN) capability detection and enumeration into the BLEEP codebase. **Network capability is a service capability (like media), not a device type.** A device can be Classic, LE, or Dual-mode AND have network capabilities.

## Key Corrections

### Network is NOT a Device Type

- Network capability is **orthogonal** to device type classification (Classic/LE/Dual)
- Similar to how media playback is a capability, not a device type
- A device can be Classic/LE/Dual AND have network capabilities
- Focus is on **enumeration of Network interface properties, methods, and attributes**

### Network Profile Limitations

- **Classic Bluetooth profile**: Network (PAN) is only available on Classic devices
- **Dual-mode devices**: Can have network capabilities when using Classic bearer
- **Pure LE devices**: Cannot have Network interface (Classic-only profile)

## Implementation Strategy

### Following Media Capability Pattern

The implementation follows the existing media capability detection pattern:

1. **Interface Detection**: Check for `org.bluez.Network1` interface presence
2. **Wrapper Classes**: `NetworkClient` (per-device `Network1`) and `NetworkServer` (per-adapter `NetworkServer1`) in `bleep/dbuslayer/network.py`
3. **Enumeration**: Provide enumeration functions for network-capable devices
4. **Property Access**: Enumerate all Network interface properties and methods

### Network Interface Details (from BlueZ docs)

**Interface**: `org.bluez.Network1`  
**Object Path**: `/{hci0,hci1,...}/dev_XX_XX_XX_XX_XX_XX`

**Properties**:
- `Connected` (boolean, readonly): Connection status
- `Interface` (string, readonly, optional): Network interface name (e.g., "bnep0")
- `UUID` (string, readonly, optional): Connection role UUID

**Methods**:
- `Connect(string uuid)` → string: Connect to network, returns interface name
- `Disconnect()` → void: Disconnect from network

**Network Roles**:
- PANU: `00001115-0000-1000-8000-00805f9b34fb`
- NAP: `00001116-0000-1000-8000-00805f9b34fb`
- GN: `00001117-0000-1000-8000-00805f9b34fb`

## Implementation Status

> **Note (2026-04-01):** PAN networking was implemented in v2.7.9 via a different
> architecture than originally planned here.  The D-Bus wrappers were created as
> planned (Phase 1), but the higher-level integration took the form of the
> `classic-pan` CLI command and `cpan` debug command rather than the
> `network-enum` / device-class helper approach outlined in Phases 2-5.
> The remaining phases are retained as **optional future enhancements** if
> dedicated network enumeration separate from `classic-pan` proves useful.

### Phase 1: Network Interface Wrapper ✅ Complete
- Created `bleep/dbuslayer/network.py`
- Implemented `NetworkClient` class (wraps `org.bluez.Network1` per-device) with property accessors and `Connect()`/`Disconnect()` methods
- Implemented `NetworkServer` class (wraps `org.bluez.NetworkServer1` per-adapter) with `Register()`/`Unregister()` methods

### Phase 1b: Operations Layer + CLI ✅ Complete (v2.7.9)
- Created `bleep/ble_ops/classic/pan.py` — operations layer with `connect()`, `disconnect()`, `status()`, `register_server()`, `unregister_server()`
- Created `classic-pan` CLI command with `connect|disconnect|status|serve|unserve` actions
- Created `cpan` debug-mode command
- PAN constants (`NETWORK_INTERFACE`, `NETWORK_SERVER_INTERFACE`, PAN UUIDs) added to `bleep/bt_ref/constants.py`
- PAN service detection via `detect_pan_service()` for SDP integration
- Observation database integration (`upsert_pan_access` in `bleep/core/observations.py`)

### Phase 2: Device Capability Detection — Future Enhancement
- Add `get_network()` method to device classes
- Add `is_network_device()` method
- Add `get_network_roles()` method (from UUIDs property)
- Update `check_device_type()` to include network flag

### Phase 3: Network Enumeration — Future Enhancement
- Create `bleep/ble_ops/classic_network.py`
- Implement `enumerate_network_capable_devices()`
- Support property and UUID enumeration

### Phase 4: Dedicated Enumeration CLI — Future Enhancement
- Add `network-enum` command to `cli.py`
- Support verbose and JSON output modes
- Display Network interface properties

### Phase 5: Device Info Integration — Future Enhancement
- Add network capabilities to `get_device_info()`
- Include network status in device information

## Files

### Implemented
- **`bleep/dbuslayer/network.py`** — Network D-Bus wrapper (`NetworkClient` + `NetworkServer`)
- **`bleep/ble_ops/classic/pan.py`** — Operations layer
- **`bleep/cli.py`** — `classic-pan` subcommand
- **`bleep/modes/debug_classic_profiles.py`** — `cpan` debug command
- **`bleep/bt_ref/constants.py`** — PAN-related constants

### Documentation
- **`bleep/docs/network_capability_plan.md`** — Original detailed plan (Phases 2-5 are future work)
- **`bleep/docs/bl_classic_mode.md`** — User-facing PAN docs (Section 2.9)
- **`bleep/scripts/check_network_capabilities.py`** — Local BlueZ capability checker

## Key Design Principles

1. **Capability, not Type**: Network is a capability like media, not a device type
2. **Interface-Based Detection**: Use `org.bluez.Network1` interface presence as definitive indicator
3. **Property Enumeration**: Enumerate all Network interface properties (Connected, Interface, UUID)
4. **Method Access**: Provide access to Network methods (Connect, Disconnect)
5. **Role Detection**: Extract network roles from device UUIDs property
6. **Classic Limitation**: Acknowledge that Network is Classic-only profile

## Usage Examples (After Implementation)

### Check Local Capabilities
```bash
python3 bleep/scripts/check_network_capabilities.py
python3 bleep/scripts/check_network_capabilities.py --verbose
```

### Enumerate Network Devices (Planned)
```bash
bleep network-enum
bleep network-enum --adapter hci0
bleep network-enum --verbose  # Show Network interface properties
bleep network-enum --json
```

### Programmatic Usage (Planned)
```python
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
from bleep.ble_ops.classic_network import enumerate_network_capable_devices

# Check device network capability
device = system_dbus__bluez_device__low_energy("AA:BB:CC:DD:EE:FF")
if device.is_network_device():
    network = device.get_network()
    print(f"Roles: {device.get_network_roles()}")
    print(f"Connected: {network.is_connected()}")
    print(f"Interface: {network.get_interface_name()}")
    print(f"Role UUID: {network.get_role()}")
    
    # Connect to network
    iface = network.connect("panu")
    print(f"Connected via {iface}")

# Enumerate all network-capable devices
devices = enumerate_network_capable_devices()
for device in devices:
    print(f"{device['name']}: {device['network_roles']}")
    if device.get('network_properties'):
        props = device['network_properties']
        print(f"  Connected: {props['connected']}")
        print(f"  Interface: {props.get('interface', 'N/A')}")
```

## Testing Strategy

1. **Unit Tests**: Mock Network interface and test wrapper class
2. **Integration Tests**: Test with real network-capable devices
3. **Property Tests**: Verify all properties are accessible
4. **Method Tests**: Test Connect/Disconnect methods
5. **Enumeration Tests**: Test enumeration across device types
6. **Error Handling**: Test with non-network devices

## Current Status

PAN client/server D-Bus wrappers and CLI/debug commands are **implemented** via
`classic-pan` CLI and `cpan` debug command (v2.7.9+).  End-to-end operation
(BNEP session establishment, `bnep0` interface creation) depends on the remote
device accepting the PAN role — testing has shown that the BNEP transport layer
may fail immediately even when BlueZ returns a nominal success from
`Network1.Connect()`.  A post-connect verification step now detects this.
Server registration (`classic-pan serve`) requires the CLI process to stay alive
(uses `signal.pause()`); Ctrl-C cleanly unregisters.

The Phases 2-5 enumeration enhancements are optional future work — they would add
convenience methods and a dedicated `network-enum` CLI but are not required for
PAN connectivity.

## References

- **[PAN connection analysis](pan_connection_analysis.md)** — BlueZ source code audit of D-Bus client lifetime, BNEP transport failure root-cause analysis, Agent Pairing comparison, and requirements checklist for a working NAP connection
- **BlueZ Documentation**: `workDir/BlueZDocs/org.bluez.Network.rst`, `workDir/BlueZDocs/org.bluez.NetworkServer.rst`
- **BlueZ Source**: `workDir/bluez/profiles/network/connection.c` (client), `workDir/bluez/profiles/network/server.c` (server)
- **BlueZ Scripts**: `workDir/BlueZScripts/test-network`, `test-nap`
- **Existing Patterns**: `bleep/dbuslayer/media.py` (media capability pattern)
- **Device Helpers**: `bleep/dbuslayer/device_le.py` (media methods as reference)
