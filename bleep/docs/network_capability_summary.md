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

The plan follows the existing media capability detection pattern:

1. **Interface Detection**: Check for `org.bluez.Network1` interface presence
2. **Wrapper Class**: Create `Network` wrapper (like `MediaControl`, `MediaPlayer`)
3. **Device Helpers**: Add `is_network_device()`, `get_network()` methods
4. **Enumeration**: Provide enumeration functions for network-capable devices
5. **Property Access**: Enumerate all Network interface properties and methods

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

## Implementation Phases

### Phase 1: Network Interface Wrapper ✅ Planned
- Create `bleep/dbuslayer/network.py`
- Implement `Network` class with property accessors
- Implement `Connect()` and `Disconnect()` methods
- Create `find_network_devices()` helper

### Phase 2: Device Capability Detection ✅ Planned
- Add `get_network()` method to device classes
- Add `is_network_device()` method
- Add `get_network_roles()` method (from UUIDs property)
- Update `check_device_type()` to include network flag

### Phase 3: Network Enumeration ✅ Planned
- Create `bleep/ble_ops/classic_network.py`
- Implement `enumerate_network_capable_devices()`
- Support property and UUID enumeration

### Phase 4: CLI Integration ✅ Planned
- Add `network-enum` command to `cli.py`
- Support verbose and JSON output modes
- Display Network interface properties

### Phase 5: Device Info Integration ✅ Planned
- Add network capabilities to `get_device_info()`
- Include network status in device information

## Files Created

1. **`bleep/docs/network_capability_plan.md`** - Detailed implementation plan (revised)
2. **`bleep/scripts/check_network_capabilities.py`** - Local BlueZ capability checker

## Files to Create/Modify

### New Files (to be created)
- `bleep/dbuslayer/network.py` - Network D-Bus wrapper (similar to `media.py`)
- `bleep/ble_ops/classic_network.py` - Network enumeration operations

### Modified Files (to be updated)
- `bleep/dbuslayer/device_le.py` - Add network capability methods
- `bleep/dbuslayer/device_classic.py` - Add network capability methods
- `bleep/cli.py` - Add network enumeration command

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

## Next Steps

1. Review and approve the revised implementation plan
2. Begin Phase 1: Create Network wrapper class
3. Test Network wrapper with known network devices
4. Proceed through remaining phases incrementally
5. Add comprehensive tests at each phase

## References

- **BlueZ Documentation**: `workDir/BlueZDocs/org.bluez.Network.5`
- **BlueZ Scripts**: `workDir/BlueZScripts/test-network`, `test-nap`
- **Existing Patterns**: `bleep/dbuslayer/media.py` (media capability pattern)
- **Device Helpers**: `bleep/dbuslayer/device_le.py` (media methods as reference)
