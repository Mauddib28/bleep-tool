"""Exploration mode for Bluetooth LE devices.

This mode provides a command-line interface for using the different 
BLE scanning strategies to connect to and explore devices.
"""

from __future__ import annotations

import sys
import argparse
import json
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy as LEDevice
from bleep.core import observations as _obs
from bleep.ble_ops.scan_modes import (
    passive_scan_and_connect,
    naggy_scan_and_connect,
    pokey_scan_and_connect,
    bruteforce_scan_and_connect,
    scan_and_connect,
    PASSIVE_MODE,
    NAGGY_MODE,
    POKEY_MODE,
    BRUTEFORCE_MODE,
)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="BLE Explorer - Connect to and explore Bluetooth LE devices"
    )
    
    parser.add_argument(
        "-d", "--device", 
        help="MAC address of the target BLE device", 
        required=True
    )
    
    parser.add_argument(
        "-m", "--mode",
        help="Scan mode to use",
        choices=["passive", "naggy", "pokey", "bruteforce"],
        default="passive"
    )
    
    parser.add_argument(
        "-t", "--timeout",
        help="Scan timeout in seconds",
        type=int,
        default=10
    )
    
    parser.add_argument(
        "-r", "--retries",
        help="Number of connection retries (for naggy mode)",
        type=int,
        default=3
    )
    
    parser.add_argument(
        "-s", "--start-handle",
        help="Starting handle for bruteforce mode (hex)",
        default="0x0001"
    )
    
    parser.add_argument(
        "-e", "--end-handle",
        help="Ending handle for bruteforce mode (hex)",
        default="0x00FF"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        help="Show detailed characteristic information",
        action="store_true"
    )
    
    parser.add_argument(
        "-o", "--out",
        help="Write enumeration results to JSON file",
        metavar="FILE"
    )
    
    parser.add_argument(
        "--dump-json",
        help="Alias for --out",
        metavar="FILE"
    )
    
    return parser.parse_args()


def mode_to_constant(mode_str: str) -> str:
    """Convert user-friendly mode name to internal constant."""
    mode_map = {
        "passive": PASSIVE_MODE,
        "naggy": NAGGY_MODE,
        "pokey": POKEY_MODE,
        "bruteforce": BRUTEFORCE_MODE,
    }
    return mode_map.get(mode_str, PASSIVE_MODE)


def print_service_info(device: LEDevice, verbose: bool = False) -> Dict[str, Any]:
    """Print information about services and characteristics and return as dict."""
    # Use get_name() method instead of accessing .name directly
    device_name = device.get_name() or device.get_alias() or "Unknown"
    
    result = {
        "device": {
            "address": device.mac_address,
            "name": device_name,
            "services": []
        }
    }
    
    print_and_log(f"\n[*] Device: {device_name} ({device.mac_address})", LOG__GENERAL)
    print_and_log(f"[*] Services resolved: {device.is_services_resolved()}", LOG__GENERAL)
    
    service_count = 0
    char_count = 0
    
    # Get the services from device
    for svc in device._services:
        service_count += 1
        service_info = {
            "uuid": svc.uuid,
            "path": svc.path,
            "characteristics": []
        }
        
        print_and_log(f"\n[*] Service: {svc.uuid}", LOG__GENERAL)
        
        # Enumerate characteristics
        for char in svc.characteristics:
            char_count += 1
            char_info = {
                "uuid": char.uuid,
                "path": char.path,
                "handle": char.handle,
                "flags": list(char.flags),
                "descriptors": []
            }
            
            # Only print details if verbose or less than 20 characteristics total
            if verbose or char_count < 20:
                handle_str = f"(Handle: 0x{char.handle:04x})" if char.handle >= 0 else ""
                print_and_log(f"  [*] Characteristic: {char.uuid} {handle_str}", LOG__GENERAL)
                print_and_log(f"      Flags: {', '.join(char.flags)}", LOG__GENERAL)
                
                # Try to read value if 'read' is in flags
                if "read" in char.flags:
                    try:
                        value = char.read_value()
                        hex_value = value.hex()
                        ascii_value = "".join(chr(b) if 32 <= b <= 126 else "." for b in value)
                        char_info["value"] = {
                            "hex": hex_value,
                            "ascii": ascii_value
                        }
                        if verbose:
                            print_and_log(f"      Value: {hex_value} (ASCII: {ascii_value})", LOG__GENERAL)
                    except Exception as e:
                        char_info["read_error"] = str(e)
                        if verbose:
                            print_and_log(f"      Read error: {str(e)}", LOG__GENERAL)
            
            # Descriptors
            for desc in getattr(char, "descriptors", []):
                desc_info = {
                    "uuid": desc.uuid,
                    "path": desc.path
                }
                char_info["descriptors"].append(desc_info)
                
                if verbose:
                    print_and_log(f"      [*] Descriptor: {desc.uuid}", LOG__GENERAL)
                    
                    # Try to read descriptor value
                    try:
                        desc_value = desc.read_value()
                        desc_info["value"] = {
                            "hex": desc_value.hex(),
                            "ascii": "".join(chr(b) if 32 <= b <= 126 else "." for b in desc_value)
                        }
                        if verbose:
                            print_and_log(f"          Value: {desc_value.hex()}", LOG__GENERAL)
                    except Exception as e:
                        desc_info["read_error"] = str(e)
                        if verbose:
                            print_and_log(f"          Read error: {str(e)}", LOG__GENERAL)
            
            service_info["characteristics"].append(char_info)
            
        result["device"]["services"].append(service_info)
    
    print_and_log(f"\n[*] Summary: {service_count} services, {char_count} characteristics", LOG__GENERAL)
    
    # Add mappings
    result["mappings"] = {
        "handle_to_uuid": {str(h): u for h, u in device.ble_device__mapping.items()},
        "landmine_map": {u: f for u, f in device.ble_device__mine_mapping.items()},
        "permission_map": {u: p for u, p in device.ble_device__permission_mapping.items()}
    }
    
    # Add security and landmine information if available
    if hasattr(device, "_landmine_categories"):
        result["landmines"] = {category: chars for category, chars in device._landmine_categories.items() if chars}
        
    if hasattr(device, "_security_mapping"):
        result["security"] = {level: chars for level, chars in device._security_mapping.items() if chars}
    
    return result


def save_to_json(data: Dict[str, Any], filename: str) -> None:
    """Save data to a JSON file."""
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        print_and_log(f"[+] Results saved to {filename}", LOG__GENERAL)
    except Exception as e:
        print_and_log(f"[-] Error saving results: {str(e)}", LOG__GENERAL)


def save_to_database(data: Dict[str, Any]) -> None:
    """Save exploration data to the observation database."""
    try:
        if not data.get("device"):
            print_and_log("[-] No device data to save to database", LOG__GENERAL)
            return
            
        device = data["device"]
        mac = device["address"]
        name = device["name"]
        
        # Update device in database
        _obs.upsert_device(
            mac=mac,
            name=name,
            # Set device_type based on available data
            device_type="le"  # Exploration mode is for BLE devices
        )
        
        # Prepare services list for batch insert
        services = []
        for service in device.get("services", []):
            services.append({
                "uuid": service["uuid"],
                "handle_start": None,  # Not available in exploration data
                "handle_end": None,    # Not available in exploration data
                "name": None           # Not available in exploration data
            })
        
        # Save all services in one batch operation
        if services:
            # This returns a mapping of service UUIDs to their database IDs
            service_ids = _obs.upsert_services(mac, services)
            
            # Now save characteristics for each service
            for service in device.get("services", []):
                service_uuid = service["uuid"]
                service_id = service_ids.get(service_uuid)
                
                if not service_id:
                    continue
                    
                # Prepare characteristics list for this service
                chars = []
                for char in service.get("characteristics", []):
                    # Convert value from exploration format to database format
                    value = None
                    if isinstance(char.get("value"), dict):
                        value_hex = char["value"].get("hex")
                        if value_hex:
                            try:
                                value = bytes.fromhex(value_hex)
                            except ValueError:
                                pass
                    
                    chars.append({
                        "uuid": char["uuid"],
                        "handle": char.get("handle"),
                        "properties": char.get("flags", []),
                        "value": value
                    })
                
                if chars:
                    _obs.upsert_characteristics(service_id, chars)
                
        print_and_log(f"[+] Saved exploration data to database for device {mac}", LOG__GENERAL)
    except Exception as e:
        print_and_log(f"[-] Error saving to database: {str(e)}", LOG__GENERAL)


def main() -> int:
    """Main function for exploration mode."""
    args = parse_arguments()
    
    # Get the output file if specified
    output_file = args.out or args.dump_json
    
    # Check if adapter is ready
    adapter = Adapter()
    if not adapter.is_ready():
        print_and_log("[-] Bluetooth adapter not ready or powered off", LOG__GENERAL)
        print_and_log("    Please turn on Bluetooth and try again", LOG__GENERAL)
        return 1
    
    # Convert mode string to constant
    mode = mode_to_constant(args.mode)
    
    # Prepare additional arguments based on the mode
    kwargs = {}
    if mode == NAGGY_MODE:
        kwargs["max_retries"] = args.retries
    elif mode == BRUTEFORCE_MODE:
        try:
            kwargs["start_handle"] = int(args.start_handle, 0)  # Parse hex or decimal
            kwargs["end_handle"] = int(args.end_handle, 0)
        except ValueError:
            print_and_log("[-] Invalid handle values. Use format 0x0001 or decimal", LOG__GENERAL)
            return 1
    
    # Connect to the device using the selected mode
    try:
        print_and_log(f"[*] Starting exploration with {args.timeout}s timeout in {args.mode} mode", LOG__GENERAL)
        
        # Only pass timeout parameter to passive mode
        if mode == PASSIVE_MODE:
            kwargs["timeout"] = args.timeout
        
        device, mapping, landmine_map, perm_map = scan_and_connect(
            args.device,
            mode=mode,
            **kwargs
        )
        
        # Print info and save to file if requested
        result = print_service_info(device, args.verbose)
        
        # Always save to database
        save_to_database(result)
        
        if output_file:
            save_to_json(result, output_file)
            
        return 0
    except Exception as e:
        print_and_log(f"[-] Error: {str(e)}", LOG__GENERAL)
        return 1


if __name__ == "__main__":
    sys.exit(main()) 