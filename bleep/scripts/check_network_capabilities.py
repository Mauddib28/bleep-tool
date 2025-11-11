#!/usr/bin/env python3
"""
Check Local BlueZ Network Capabilities

This script examines the local BlueZ installation to determine:
1. NetworkServer interface availability on adapters
2. Network-related interfaces on discovered devices
3. Network UUIDs in adapter and device properties

Usage:
    python3 check_network_capabilities.py [--adapter hci0] [--verbose]
"""

from __future__ import annotations

import sys
import argparse
from typing import Dict, List, Any, Optional

try:
    import dbus
except ImportError:
    print("[-] Error: dbus-python not installed. Install with: pip install dbus-python")
    sys.exit(1)

# BlueZ D-Bus constants
BLUEZ_SERVICE = "org.bluez"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROPERTIES = "org.freedesktop.DBus.Properties"
ADAPTER_INTERFACE = "org.bluez.Adapter1"
DEVICE_INTERFACE = "org.bluez.Device1"
NETWORK_INTERFACE = "org.bluez.Network1"
NETWORK_SERVER_INTERFACE = "org.bluez.NetworkServer1"

# Network UUIDs
NETWORK_UUIDS = {
    "00001115-0000-1000-8000-00805f9b34fb": "PANU",
    "00001116-0000-1000-8000-00805f9b34fb": "NAP",
    "00001117-0000-1000-8000-00805f9b34fb": "GN",
}


def get_managed_objects() -> Dict[str, Dict[str, Any]]:
    """Get all managed objects from BlueZ."""
    try:
        bus = dbus.SystemBus()
        obj_manager = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE, "/"),
            DBUS_OM_IFACE
        )
        return obj_manager.GetManagedObjects()
    except dbus.exceptions.DBusException as e:
        print(f"[-] Failed to get managed objects: {e}")
        return {}


def check_adapter_networkserver(adapter_path: str, managed_objects: Dict[str, Dict[str, Any]]) -> bool:
    """Check if adapter has NetworkServer interface."""
    if adapter_path not in managed_objects:
        return False
    interfaces = managed_objects[adapter_path]
    return NETWORK_SERVER_INTERFACE in interfaces


def check_device_network_interface(device_path: str, managed_objects: Dict[str, Dict[str, Any]]) -> bool:
    """Check if device has Network1 interface."""
    if device_path not in managed_objects:
        return False
    interfaces = managed_objects[device_path]
    return NETWORK_INTERFACE in interfaces


def get_network_uuids_from_properties(properties: Dict[str, Any]) -> List[str]:
    """Extract network UUIDs from device/adapter properties."""
    uuids = properties.get("UUIDs", [])
    network_uuids = []
    for uuid in uuids:
        uuid_str = str(uuid).lower()
        if uuid_str in NETWORK_UUIDS:
            network_uuids.append(NETWORK_UUIDS[uuid_str])
    return network_uuids


def check_adapter_capabilities(adapter_name: Optional[str] = None, verbose: bool = False) -> Dict[str, Any]:
    """Check network capabilities of adapters."""
    managed_objects = get_managed_objects()
    if not managed_objects:
        return {"error": "Failed to get managed objects"}
    
    adapters = []
    for path, interfaces in managed_objects.items():
        if ADAPTER_INTERFACE not in interfaces:
            continue
        
        # Filter by adapter name if specified
        if adapter_name:
            if not path.endswith(f"/{adapter_name}"):
                continue
        
        props = interfaces[ADAPTER_INTERFACE]
        adapter_info = {
            "path": str(path),
            "name": props.get("Name", "Unknown"),
            "address": props.get("Address", "Unknown"),
            "powered": props.get("Powered", False),
            "has_networkserver": check_adapter_networkserver(str(path), managed_objects),
            "network_uuids": get_network_uuids_from_properties(props),
        }
        
        if verbose and adapter_info["has_networkserver"]:
            # Get NetworkServer properties if available
            try:
                bus = dbus.SystemBus()
                server_obj = bus.get_object(BLUEZ_SERVICE, str(path))
                server_props = dbus.Interface(server_obj, DBUS_PROPERTIES)
                # NetworkServer doesn't have properties, but we can check methods via introspection
                adapter_info["networkserver_available"] = True
            except Exception as e:
                if verbose:
                    adapter_info["networkserver_error"] = str(e)
        
        adapters.append(adapter_info)
    
    return {"adapters": adapters}


def check_device_network_capabilities(adapter_name: Optional[str] = None, verbose: bool = False) -> Dict[str, Any]:
    """Check network capabilities of discovered devices."""
    managed_objects = get_managed_objects()
    if not managed_objects:
        return {"error": "Failed to get managed objects"}
    
    devices = []
    for path, interfaces in managed_objects.items():
        if DEVICE_INTERFACE not in interfaces:
            continue
        
        # Filter by adapter if specified
        if adapter_name:
            if not path.startswith(f"/org/bluez/{adapter_name}/"):
                continue
        
        props = interfaces[DEVICE_INTERFACE]
        device_path = str(path)
        
        # Check for network interface
        has_network_interface = check_device_network_interface(device_path, managed_objects)
        
        # Get network UUIDs from properties
        network_uuids = get_network_uuids_from_properties(props)
        
        # Get network interface properties if available
        network_info = None
        if has_network_interface and verbose:
            try:
                bus = dbus.SystemBus()
                network_obj = bus.get_object(BLUEZ_SERVICE, device_path)
                network_props_iface = dbus.Interface(network_obj, DBUS_PROPERTIES)
                network_props = network_props_iface.GetAll(NETWORK_INTERFACE)
                network_info = {
                    "connected": network_props.get("Connected", False),
                    "interface": network_props.get("Interface", ""),
                    "uuid": network_props.get("UUID", ""),
                }
            except Exception as e:
                if verbose:
                    network_info = {"error": str(e)}
        
        device_info = {
            "address": props.get("Address", "Unknown"),
            "name": props.get("Name") or props.get("Alias", "Unknown"),
            "has_network_interface": has_network_interface,
            "network_uuids": network_uuids,
            "has_network_capability": has_network_interface or len(network_uuids) > 0,
        }
        
        if network_info:
            device_info["network_status"] = network_info
        
        if device_info["has_network_capability"]:
            devices.append(device_info)
    
    return {"devices": devices}


def main():
    parser = argparse.ArgumentParser(
        description="Check local BlueZ network capabilities"
    )
    parser.add_argument(
        "--adapter", "-i",
        help="Adapter to check (e.g., hci0)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed information"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    # Check adapter capabilities
    adapter_info = check_adapter_capabilities(args.adapter, args.verbose)
    
    # Check device capabilities
    device_info = check_device_network_capabilities(args.adapter, args.verbose)
    
    if args.json:
        import json
        output = {
            "adapters": adapter_info.get("adapters", []),
            "network_capable_devices": device_info.get("devices", []),
        }
        print(json.dumps(output, indent=2))
        return
    
    # Human-readable output
    print("=" * 70)
    print("BlueZ Network Capabilities Check")
    print("=" * 70)
    
    # Adapter information
    print("\n[+] Adapters:")
    adapters = adapter_info.get("adapters", [])
    if not adapters:
        print("  No adapters found")
    else:
        for adapter in adapters:
            print(f"\n  Adapter: {adapter['name']} ({adapter['address']})")
            print(f"    Path: {adapter['path']}")
            print(f"    Powered: {adapter['powered']}")
            print(f"    NetworkServer Support: {'✓' if adapter['has_networkserver'] else '✗'}")
            if adapter['network_uuids']:
                print(f"    Network UUIDs: {', '.join(adapter['network_uuids'])}")
    
    # Device information
    print("\n[+] Network-Capable Devices:")
    devices = device_info.get("devices", [])
    if not devices:
        print("  No devices with network capabilities found")
    else:
        print(f"  Found {len(devices)} device(s) with network capabilities:\n")
        for device in devices:
            print(f"  Device: {device['name']} ({device['address']})")
            print(f"    Network Interface: {'✓' if device['has_network_interface'] else '✗'}")
            if device['network_uuids']:
                print(f"    Network Roles: {', '.join(device['network_uuids'])}")
            if args.verbose and device.get('network_status'):
                status = device['network_status']
                print(f"    Network Status:")
                print(f"      Connected: {status.get('connected', False)}")
                if status.get('interface'):
                    print(f"      Interface: {status['interface']}")
                if status.get('uuid'):
                    print(f"      Role: {status['uuid']}")
            print()
    
    # Summary
    print("=" * 70)
    print("Summary:")
    print(f"  Adapters checked: {len(adapters)}")
    adapters_with_server = sum(1 for a in adapters if a['has_networkserver'])
    print(f"  Adapters with NetworkServer: {adapters_with_server}")
    print(f"  Network-capable devices: {len(devices)}")
    print("=" * 70)


if __name__ == "__main__":
    main()


