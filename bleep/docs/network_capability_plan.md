# Network Capability Detection and Enumeration Plan

## Overview

This plan outlines the integration of Bluetooth Network (PAN) capability detection and enumeration into the BLEEP codebase. Network capability is a **service capability** (like media), not a device type. A device can be Classic, LE, or Dual-mode AND have network capabilities.

## Objectives

1. **Recognize devices with Network capabilities** by detecting `org.bluez.Network1` interface presence
2. **Enumerate Network interface properties, methods, and attributes** following BlueZ documentation
3. **Provide Network capability helpers** similar to existing media capability helpers
4. **Leverage existing patterns** (media capability detection, D-Bus wrappers, device helpers)

## Network Profile Overview

### BlueZ Network Interface

**Interface**: `org.bluez.Network1`  
**Object Path**: `/{hci0,hci1,...}/dev_XX_XX_XX_XX_XX_XX`  
**Availability**: Classic Bluetooth devices (or dual-mode devices using Classic bearer)

### Network Interface Properties (from BlueZ docs)

- **`Connected`** (boolean, readonly): Indicates if the device is connected
- **`Interface`** (string, readonly, optional): Network interface name when available (e.g., "bnep0")
- **`UUID`** (string, readonly, optional): Connection role UUID when available

### Network Interface Methods (from BlueZ docs)

- **`Connect(string uuid)`** → string: Connects to network device, returns interface name
  - UUID values: "panu", "nap", "gn" or full UUIDs
  - Returns: Network interface name (e.g., "bnep0")
  - Errors: InvalidArguments, NotSupported, InProgress, Failed

- **`Disconnect()`** → void: Disconnects from network device
  - Errors: Failed, NotConnected

### Network Roles (UUIDs)

- **PANU** (Personal Area Network User): `0x1115` / `00001115-0000-1000-8000-00805f9b34fb`
- **NAP** (Network Access Point): `0x1116` / `00001116-0000-1000-8000-00805f9b34fb`
- **GN** (Group Network): `0x1117` / `00001117-0000-1000-8000-00805f9b34fb`

### Important Limitations

- **Classic-only profile**: Network (PAN) is a Classic Bluetooth profile, not available on pure LE devices
- **Dual-mode devices**: Can have network capabilities when using Classic bearer
- **Interface presence**: `org.bluez.Network1` interface appears on device paths when device supports networking
- **UUIDs property**: Device's UUIDs property may contain network UUIDs indicating supported roles

## Implementation Plan

### Phase 1: Network Interface Wrapper

#### 1.1 Create Network Wrapper Class

**File**: `bleep/dbuslayer/network.py` (new file)

Create wrapper class following the pattern of `media.py`:

```python
"""Network Device interface for the BlueZ stack.

This module provides classes for interacting with Bluetooth Network devices through
the BlueZ D-Bus interface org.bluez.Network1.

This interface allows for network connection management with devices that support
the Personal Area Network (PAN) profile.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
import dbus

from bleep.bt_ref.constants import BLUEZ_SERVICE_NAME, DBUS_PROPERTIES
from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core.errors import map_dbus_error, BLEEPError

NETWORK_INTERFACE = "org.bluez.Network1"

# Network role UUIDs
NETWORK_ROLES = {
    "panu": "00001115-0000-1000-8000-00805f9b34fb",
    "nap": "00001116-0000-1000-8000-00805f9b34fb",
    "gn": "00001117-0000-1000-8000-00805f9b34fb",
}


class Network:
    """Wrapper for the org.bluez.Network1 interface."""
    
    def __init__(self, device_path: str):
        """Initialize Network interface for a device.
        
        Parameters
        ----------
        device_path : str
            D-Bus path to the device
            
        Raises
        ------
        BLEEPError
            If Network interface is not available on the device
        """
        self.device_path = device_path
        self._bus = dbus.SystemBus()
        
        try:
            self._object = self._bus.get_object(BLUEZ_SERVICE_NAME, device_path)
            self._interface = dbus.Interface(self._object, NETWORK_INTERFACE)
            self._properties = dbus.Interface(self._object, DBUS_PROPERTIES)
        except dbus.exceptions.DBusException as e:
            print_and_log(
                f"[-] Network interface not available on {device_path}: {str(e)}",
                LOG__DEBUG
            )
            raise map_dbus_error(e)
    
    def get_properties(self) -> Dict[str, Any]:
        """Get all properties of the Network interface.
        
        Returns
        -------
        Dict[str, Any]
            Dictionary containing:
            - Connected (bool): Connection status
            - Interface (str, optional): Network interface name
            - UUID (str, optional): Connection role UUID
        """
        try:
            props = self._properties.GetAll(NETWORK_INTERFACE)
            return dbus_to_python(props)
        except dbus.exceptions.DBusException as e:
            print_and_log(
                f"[-] Failed to get Network properties: {str(e)}",
                LOG__DEBUG
            )
            raise map_dbus_error(e)
    
    def is_connected(self) -> bool:
        """Check if the network is connected.
        
        Returns
        -------
        bool
            True if connected, False otherwise
        """
        try:
            connected = self._properties.Get(NETWORK_INTERFACE, "Connected")
            return bool(connected)
        except dbus.exceptions.DBusException as e:
            print_and_log(
                f"[-] Failed to get Connected property: {str(e)}",
                LOG__DEBUG
            )
            return False
    
    def get_interface_name(self) -> Optional[str]:
        """Get the network interface name.
        
        Returns
        -------
        Optional[str]
            Network interface name (e.g., "bnep0") or None if not available
        """
        try:
            iface = self._properties.Get(NETWORK_INTERFACE, "Interface")
            return str(iface) if iface else None
        except (dbus.exceptions.DBusException, KeyError):
            return None
    
    def get_role(self) -> Optional[str]:
        """Get the current connection role UUID.
        
        Returns
        -------
        Optional[str]
            Role UUID (e.g., "00001115-0000-1000-8000-00805f9b34fb") or None
        """
        try:
            uuid = self._properties.Get(NETWORK_INTERFACE, "UUID")
            return str(uuid) if uuid else None
        except (dbus.exceptions.DBusException, KeyError):
            return None
    
    def connect(self, role: str = "panu") -> str:
        """Connect to the network device.
        
        Parameters
        ----------
        role : str
            Network role: "panu", "nap", "gn", or full UUID
            
        Returns
        -------
        str
            Network interface name (e.g., "bnep0")
            
        Raises
        ------
        BLEEPError
            If connection fails
        """
        # Normalize role to UUID if needed
        uuid = NETWORK_ROLES.get(role.lower(), role)
        
        try:
            interface_name = self._interface.Connect(uuid)
            print_and_log(
                f"[+] Network connected via {interface_name} (role: {role})",
                LOG__DEBUG
            )
            return str(interface_name)
        except dbus.exceptions.DBusException as e:
            print_and_log(
                f"[-] Network Connect failed: {str(e)}",
                LOG__DEBUG
            )
            raise map_dbus_error(e)
    
    def disconnect(self) -> bool:
        """Disconnect from the network device.
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        try:
            self._interface.Disconnect()
            print_and_log("[+] Network disconnected", LOG__DEBUG)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(
                f"[-] Network Disconnect failed: {str(e)}",
                LOG__DEBUG
            )
            return False


def find_network_devices() -> Dict[str, Dict[str, Any]]:
    """Find all devices with Network interface.
    
    Returns
    -------
    Dict[str, Dict[str, Any]]
        Dictionary mapping device paths to Network interface information
    """
    result = {}
    
    try:
        bus = dbus.SystemBus()
        obj_manager = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, "/"),
            "org.freedesktop.DBus.ObjectManager"
        )
        objects = obj_manager.GetManagedObjects()
        
        for path, interfaces in objects.items():
            if NETWORK_INTERFACE in interfaces:
                device_path = str(path)
                props = interfaces[NETWORK_INTERFACE]
                result[device_path] = {
                    "path": device_path,
                    "connected": props.get("Connected", False),
                    "interface": props.get("Interface", ""),
                    "uuid": props.get("UUID", ""),
                }
    except Exception as e:
        print_and_log(
            f"[-] Failed to find network devices: {str(e)}",
            LOG__DEBUG
        )
    
    return result
```

### Phase 2: Device Capability Detection

#### 2.1 Add Network Helpers to Device Classes

**File**: `bleep/dbuslayer/device_le.py` and `bleep/dbuslayer/device_classic.py`

Add network capability methods following the pattern of media methods:

```python
# In device_le.py and device_classic.py

def get_network(self) -> Optional[Network]:
    """Get Network interface for this device.
    
    Returns
    -------
    Optional[Network]
        Network interface object or None if not available
    """
    try:
        from bleep.dbuslayer.network import Network
        return Network(self._device_path)
    except BLEEPError:
        return None

def is_network_device(self) -> bool:
    """Check if this device supports Network interface.
    
    Returns
    -------
    bool
        True if the device has Network interface, False otherwise
    """
    try:
        objects = self._object_manager.GetManagedObjects()
        for path, interfaces in objects.items():
            if path == self._device_path:
                return NETWORK_INTERFACE in interfaces
        return False
    except Exception as e:
        print_and_log(
            f"[*] Error checking network interface: {e}",
            LOG__DEBUG
        )
        return False

def get_network_roles(self) -> List[str]:
    """Get available network roles from device UUIDs.
    
    Returns
    -------
    List[str]
        List of available network roles: ["panu", "nap", "gn"]
    """
    roles = []
    try:
        uuids = self._props_iface.Get(DEVICE_INTERFACE, "UUIDs")
        for uuid in uuids:
            uuid_str = str(uuid).lower()
            if uuid_str == "00001115-0000-1000-8000-00805f9b34fb":
                roles.append("panu")
            elif uuid_str == "00001116-0000-1000-8000-00805f9b34fb":
                roles.append("nap")
            elif uuid_str == "00001117-0000-1000-8000-00805f9b34fb":
                roles.append("gn")
    except Exception as e:
        print_and_log(
            f"[*] Error getting network roles: {e}",
            LOG__DEBUG
        )
    return roles
```

#### 2.2 Update Device Type Flags

**File**: `bleep/dbuslayer/device_le.py`

Add network capability flag to `check_device_type()`:

```python
# In check_device_type() method, add:
# Check for network interface
try:
    objects = self._object_manager.GetManagedObjects()
    for path, interfaces in objects.items():
        if path == self._device_path:
            if NETWORK_INTERFACE in interfaces:
                result["is_network_device"] = True
                break
except Exception as e:
    print_and_log(f"[*] Error checking network interface: {e}", LOG__DEBUG)
```

### Phase 3: Network Enumeration Functions

#### 3.1 Create Network Operations Module

**File**: `bleep/ble_ops/classic_network.py` (new file)

Create enumeration functions:

```python
"""Network capability enumeration operations.

Provides helpers for discovering and enumerating devices with Network capabilities.
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional
from bleep.dbuslayer.network import Network, find_network_devices
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter
from bleep.core.log import print_and_log, LOG__DEBUG

NETWORK_INTERFACE = "org.bluez.Network1"


def enumerate_network_capable_devices(
    adapter_name: Optional[str] = None,
    *,
    include_properties: bool = True,
    include_uuids: bool = True,
) -> List[Dict[str, Any]]:
    """Enumerate all devices with Network capabilities.
    
    Parameters
    ----------
    adapter_name : Optional[str]
        Adapter to check (default: first available)
    include_properties : bool
        Include Network interface properties in results
    include_uuids : bool
        Include network role UUIDs from device UUIDs property
        
    Returns
    -------
    List[Dict[str, Any]]
        List of devices with network capability information:
        {
            "address": str,
            "name": str,
            "path": str,
            "has_network_interface": bool,
            "network_roles": List[str],  # From UUIDs property
            "network_properties": Dict[str, Any],  # If include_properties
        }
    """
    devices = []
    
    try:
        adapter = system_dbus__bluez_adapter(adapter_name or "")
        managed_objects = adapter.get_managed_objects()
        
        if not managed_objects:
            return devices
        
        # Find all devices with Network interface
        network_devices = find_network_devices()
        
        for path, interfaces in managed_objects.items():
            if "org.bluez.Device1" not in interfaces:
                continue
            
            device_props = interfaces["org.bluez.Device1"]
            device_path = str(path)
            
            # Check if device has Network interface
            has_network = device_path in network_devices
            
            device_info = {
                "address": device_props.get("Address", "Unknown"),
                "name": device_props.get("Name") or device_props.get("Alias", "Unknown"),
                "path": device_path,
                "has_network_interface": has_network,
            }
            
            # Get network roles from UUIDs property
            if include_uuids:
                network_roles = []
                uuids = device_props.get("UUIDs", [])
                for uuid in uuids:
                    uuid_str = str(uuid).lower()
                    if uuid_str == "00001115-0000-1000-8000-00805f9b34fb":
                        network_roles.append("panu")
                    elif uuid_str == "00001116-0000-1000-8000-00805f9b34fb":
                        network_roles.append("nap")
                    elif uuid_str == "00001117-0000-1000-8000-00805f9b34fb":
                        network_roles.append("gn")
                device_info["network_roles"] = network_roles
            
            # Get Network interface properties
            if include_properties and has_network:
                device_info["network_properties"] = network_devices[device_path]
            
            if has_network or device_info.get("network_roles"):
                devices.append(device_info)
    
    except Exception as e:
        print_and_log(
            f"[-] Failed to enumerate network devices: {str(e)}",
            LOG__DEBUG
        )
    
    return devices
```

### Phase 4: CLI Integration

#### 4.1 Add Network Enumeration Command

**File**: `bleep/cli.py`

Add network enumeration command:

```python
# Add parser for network enumeration
network_parser = subparsers.add_parser(
    "network-enum",
    help="Enumerate devices with Network capabilities"
)
network_parser.add_argument(
    "--adapter", "-i",
    help="Adapter to use"
)
network_parser.add_argument(
    "--json",
    action="store_true",
    help="Output as JSON"
)
network_parser.add_argument(
    "--verbose",
    action="store_true",
    help="Show detailed Network interface properties"
)
```

Add handler in main():

```python
elif args.mode == "network-enum":
    from bleep.ble_ops.classic_network import enumerate_network_capable_devices
    
    devices = enumerate_network_capable_devices(
        adapter_name=args.adapter,
        include_properties=args.verbose,
        include_uuids=True
    )
    
    if args.json:
        import json
        print(json.dumps(devices, indent=2))
    else:
        print(f"\n[+] Found {len(devices)} device(s) with Network capabilities:\n")
        for device in devices:
            print(f"  {device['name']} ({device['address']})")
            print(f"    Network Interface: {'✓' if device['has_network_interface'] else '✗'}")
            if device.get('network_roles'):
                print(f"    Roles: {', '.join(device['network_roles'])}")
            if args.verbose and device.get('network_properties'):
                props = device['network_properties']
                print(f"    Connected: {props.get('connected', False)}")
                if props.get('interface'):
                    print(f"    Interface: {props['interface']}")
                if props.get('uuid'):
                    print(f"    Role UUID: {props['uuid']}")
            print()
```

### Phase 5: Update Device Info Methods

#### 5.1 Add Network Info to get_device_info()

**File**: `bleep/dbuslayer/device_le.py` and `bleep/dbuslayer/device_classic.py`

Add network information to `get_device_info()`:

```python
# In get_device_info() method, add:
info["network_capabilities"] = {
    "is_network_device": self.is_network_device(),
    "network_roles": self.get_network_roles(),
}

network = self.get_network()
if network:
    try:
        info["network_status"] = {
            "connected": network.is_connected(),
            "interface": network.get_interface_name(),
            "role": network.get_role(),
        }
    except Exception:
        pass
```

## Implementation Order

1. **Phase 1**: Network interface wrapper (`network.py`)
2. **Phase 2**: Device capability helpers (add to device classes)
3. **Phase 3**: Enumeration functions (`classic_network.py`)
4. **Phase 4**: CLI integration
5. **Phase 5**: Update device info methods

## Files to Create/Modify

### New Files
- `bleep/dbuslayer/network.py` - Network D-Bus wrapper
- `bleep/ble_ops/classic_network.py` - Network enumeration operations

### Modified Files
- `bleep/dbuslayer/device_le.py` - Add network capability methods
- `bleep/dbuslayer/device_classic.py` - Add network capability methods
- `bleep/cli.py` - Add network enumeration command

## Testing Strategy

1. **Unit Tests**: Test Network wrapper with mock D-Bus interfaces
2. **Integration Tests**: Test with real network-capable devices
3. **Enumeration Tests**: Test enumeration across multiple device types
4. **Error Handling**: Test with non-network devices
5. **Property Access**: Verify all properties are accessible
6. **Method Calls**: Test Connect/Disconnect methods

## Usage Examples

### Programmatic Usage

```python
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
from bleep.ble_ops.classic_network import enumerate_network_capable_devices

# Check if device has network capability
device = system_dbus__bluez_device__low_energy("AA:BB:CC:DD:EE:FF")
if device.is_network_device():
    network = device.get_network()
    print(f"Network roles: {device.get_network_roles()}")
    print(f"Connected: {network.is_connected()}")
    print(f"Interface: {network.get_interface_name()}")

# Enumerate all network-capable devices
devices = enumerate_network_capable_devices()
for device in devices:
    print(f"{device['name']}: {device['network_roles']}")
```

### CLI Usage

```bash
# Enumerate network-capable devices
bleep network-enum

# Verbose output with properties
bleep network-enum --verbose

# JSON output
bleep network-enum --json
```

## Notes

- Network capability is **orthogonal** to device type (Classic/LE/Dual)
- Network is a **Classic Bluetooth profile**, not available on pure LE devices
- Interface presence (`org.bluez.Network1`) is the **definitive** indicator of network capability
- UUIDs property can indicate **supported roles** before connection
- Properties are **readonly** and reflect current connection state
- Methods (`Connect`, `Disconnect`) require **active connection** to device

## References

- **BlueZ Documentation**: `workDir/BlueZDocs/org.bluez.Network.5`
- **BlueZ Scripts**: `workDir/BlueZScripts/test-network`, `test-nap`
- **Existing Patterns**: `bleep/dbuslayer/media.py`, `bleep/dbuslayer/device_le.py`
