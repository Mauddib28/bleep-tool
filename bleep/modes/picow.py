#!/usr/bin/env python3
"""PicoW Mode for BLEEP.

This mode provides specialized handling for Raspberry Pi Pico W devices,
including custom characteristic interactions and specialized enumeration.

Usage:
  python -m bleep -m picow [options]

Options:
  --device <mac>     MAC address of Pico W device
  --scan             Scan for Pico W devices
  --timeout <sec>    Scan timeout in seconds (default: 10)
  --read <uuid>      Read from characteristic
  --write <uuid>     Write to characteristic
  --value <value>    Value to write (used with --write)
  --monitor          Monitor notifications from device
  --time <sec>       Time to monitor notifications (default: 30)
"""

import argparse
import time
import sys
import re
from typing import Dict, List, Any, Optional, Tuple

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
from bleep.ble_ops.scan import passive_scan
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum

# Pico W specific constants
PICOW_NAME_PATTERN = re.compile(r'(?i)pico|raspberry')
PICOW_SERVICE_UUID = "00000001-1234-1000-8000-00805f9b34fb"  # Example service UUID
PICOW_CHAR_UUID_PREFIX = "0000"  # Example characteristic UUID prefix

# Pico W specific characteristic UUIDs (examples)
PICOW_LED_CHAR_UUID = "00000002-1234-1000-8000-00805f9b34fb"
PICOW_BUTTON_CHAR_UUID = "00000003-1234-1000-8000-00805f9b34fb"
PICOW_TEMP_CHAR_UUID = "00000004-1234-1000-8000-00805f9b34fb"

class PicoWDevice:
    """Class for interacting with Pico W devices."""
    
    def __init__(self, device, mapping):
        self.device = device
        self.mapping = mapping
        self.mac_address = device.mac_address
        self._notification_callbacks = {}
    
    @staticmethod
    def is_picow_device(device_name: Optional[str]) -> bool:
        """Check if a device name indicates a Pico W device."""
        if not device_name:
            return False
        
        return bool(PICOW_NAME_PATTERN.search(device_name))
    
    def get_characteristics(self) -> Dict[str, Dict]:
        """Get all characteristics from the device."""
        characteristics = {}
        
        for service_uuid, service_info in self.mapping.items():
            for char_uuid, char_info in service_info.get("Characteristics", {}).items():
                characteristics[char_uuid] = char_info
        
        return characteristics
    
    def read_characteristic(self, char_uuid: str) -> Tuple[bytes, str, str]:
        """Read a characteristic value and return raw bytes, hex string, and ASCII representation."""
        try:
            char = self.device._find_characteristic(char_uuid, self.mapping)
            
            if not char:
                raise ValueError(f"Characteristic not found: {char_uuid}")
            
            value = char.ReadValue({})
            
            # Convert to bytes
            raw_bytes = bytes(value)
            
            # Convert to hex string
            hex_str = " ".join([f"{b:02x}" for b in raw_bytes])
            
            # Try to convert to ASCII
            try:
                ascii_str = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                ascii_str = "".join([chr(b) if 32 <= b <= 126 else '.' for b in raw_bytes])
            
            return raw_bytes, hex_str, ascii_str
        
        except Exception as exc:
            print_and_log(f"[-] Error reading characteristic: {exc}", LOG__DEBUG)
            raise
    
    def write_characteristic(self, char_uuid: str, value: str) -> None:
        """Write a value to a characteristic."""
        try:
            char = self.device._find_characteristic(char_uuid, self.mapping)
            
            if not char:
                raise ValueError(f"Characteristic not found: {char_uuid}")
            
            # Convert value to bytes
            if value.startswith("0x"):
                # Hex string
                byte_array = bytearray.fromhex(value[2:])
            else:
                # ASCII string
                byte_array = value.encode('utf-8')
            
            # Write the value
            char.WriteValue(byte_array, {})
            print_and_log(f"[+] Value written to {char_uuid}", LOG__GENERAL)
        
        except Exception as exc:
            print_and_log(f"[-] Error writing to characteristic: {exc}", LOG__DEBUG)
            raise
    
    def register_notification(self, char_uuid: str, callback) -> None:
        """Register for notifications from a characteristic."""
        try:
            char = self.device._find_characteristic(char_uuid, self.mapping)
            
            if not char:
                raise ValueError(f"Characteristic not found: {char_uuid}")
            
            # Start notifications
            char.StartNotify()
            
            # Register callback
            char.register_notify_callback(callback)
            
            # Store callback for later cleanup
            self._notification_callbacks[char_uuid] = callback
            
            print_and_log(f"[+] Notifications enabled for {char_uuid}", LOG__GENERAL)
        
        except Exception as exc:
            print_and_log(f"[-] Error enabling notifications: {exc}", LOG__DEBUG)
            raise
    
    def unregister_notification(self, char_uuid: str) -> None:
        """Unregister from notifications."""
        try:
            char = self.device._find_characteristic(char_uuid, self.mapping)
            
            if not char:
                raise ValueError(f"Characteristic not found: {char_uuid}")
            
            # Stop notifications
            char.StopNotify()
            
            # Remove callback
            if char_uuid in self._notification_callbacks:
                del self._notification_callbacks[char_uuid]
            
            print_and_log(f"[+] Notifications disabled for {char_uuid}", LOG__GENERAL)
        
        except Exception as exc:
            print_and_log(f"[-] Error disabling notifications: {exc}", LOG__DEBUG)
            raise
    
    def cleanup(self) -> None:
        """Clean up resources."""
        # Stop all notifications
        for char_uuid in list(self._notification_callbacks.keys()):
            try:
                self.unregister_notification(char_uuid)
            except:
                pass
        
        # Disconnect from device
        try:
            self.device.disconnect()
        except:
            pass

def scan_for_picow_devices(timeout: int = 10) -> List[Dict[str, Any]]:
    """Scan for Pico W devices."""
    print_and_log(f"[*] Scanning for Pico W devices (timeout: {timeout}s)...", LOG__GENERAL)
    
    # Run a passive scan
    devices = passive_scan(timeout=timeout, return_devices=True)
    
    # Filter for Pico W devices
    picow_devices = []
    
    for device in devices:
        name = device.get("name", "")
        if PicoWDevice.is_picow_device(name):
            picow_devices.append(device)
    
    print_and_log(f"[+] Found {len(picow_devices)} Pico W devices", LOG__GENERAL)
    
    return picow_devices

def connect_to_picow(mac_address: str) -> Optional[PicoWDevice]:
    """Connect to a Pico W device."""
    print_and_log(f"[*] Connecting to Pico W device {mac_address}...", LOG__GENERAL)
    
    try:
        device, mapping, _, _ = _connect_enum(mac_address)
        print_and_log(f"[+] Connected to {mac_address}", LOG__GENERAL)
        
        # Check if it's a Pico W device
        name = device.get_name() or device.get_alias() or ""
        if not PicoWDevice.is_picow_device(name):
            print_and_log(f"[!] Warning: Device {mac_address} may not be a Pico W device", LOG__GENERAL)
        
        return PicoWDevice(device, mapping)
    
    except Exception as exc:
        print_and_log(f"[-] Connection failed: {exc}", LOG__DEBUG)
        return None

def notification_handler(value):
    """Handle notifications from Pico W device."""
    # Convert to bytes
    raw_bytes = bytes(value)
    
    # Convert to hex string
    hex_str = " ".join([f"{b:02x}" for b in raw_bytes])
    
    # Try to convert to ASCII
    try:
        ascii_str = raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        ascii_str = "".join([chr(b) if 32 <= b <= 126 else '.' for b in raw_bytes])
    
    print(f"\n[NOTIFICATION] Value received:")
    print(f"  Hex: {hex_str}")
    print(f"  ASCII: {ascii_str}")
    print(f"  Raw bytes: {raw_bytes}")

def interactive_mode(picow: PicoWDevice) -> None:
    """Run interactive mode for Pico W device."""
    print_and_log("[*] Entering interactive mode for Pico W device", LOG__GENERAL)
    print("\nAvailable commands:")
    print("  list                       - List all characteristics")
    print("  read <uuid>                - Read characteristic value")
    print("  write <uuid> <value>       - Write value to characteristic")
    print("  notify <uuid> [on|off]     - Enable/disable notifications")
    print("  led <on|off>               - Control onboard LED (if available)")
    print("  temp                       - Read temperature (if available)")
    print("  help                       - Show this help")
    print("  quit                       - Exit interactive mode")
    print()
    
    while True:
        try:
            cmd = input(f"PICOW[{picow.mac_address}]> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        
        parts = cmd.strip().split()
        if not parts:
            continue
        
        command = parts[0].lower()
        args = parts[1:]
        
        if command == "quit" or command == "exit":
            break
        
        elif command == "help":
            print("\nAvailable commands:")
            print("  list                       - List all characteristics")
            print("  read <uuid>                - Read characteristic value")
            print("  write <uuid> <value>       - Write value to characteristic")
            print("  notify <uuid> [on|off]     - Enable/disable notifications")
            print("  led <on|off>               - Control onboard LED (if available)")
            print("  temp                       - Read temperature (if available)")
            print("  help                       - Show this help")
            print("  quit                       - Exit interactive mode")
            print()
        
        elif command == "list":
            # List all characteristics
            characteristics = picow.get_characteristics()
            
            print("\nCharacteristics:")
            for uuid, info in characteristics.items():
                handle = info.get("Handle", "Unknown")
                props = ", ".join(info.get("Properties", []))
                print(f"  {uuid}")
                print(f"    Handle: {handle}")
                print(f"    Properties: {props}")
            print()
        
        elif command == "read":
            # Read characteristic value
            if not args:
                print("Usage: read <uuid>")
                continue
            
            char_uuid = args[0]
            
            try:
                raw_bytes, hex_str, ascii_str = picow.read_characteristic(char_uuid)
                
                print(f"\nValue for {char_uuid}:")
                print(f"  Hex: {hex_str}")
                print(f"  ASCII: {ascii_str}")
                print(f"  Raw bytes: {raw_bytes}")
                print()
            except Exception as exc:
                print(f"[-] Error: {exc}")
        
        elif command == "write":
            # Write value to characteristic
            if len(args) < 2:
                print("Usage: write <uuid> <value>")
                continue
            
            char_uuid = args[0]
            value = args[1]
            
            try:
                picow.write_characteristic(char_uuid, value)
                print(f"[+] Value written to {char_uuid}")
            except Exception as exc:
                print(f"[-] Error: {exc}")
        
        elif command == "notify":
            # Enable/disable notifications
            if not args:
                print("Usage: notify <uuid> [on|off]")
                continue
            
            char_uuid = args[0]
            action = "on"
            if len(args) > 1:
                action = args[1].lower()
            
            try:
                if action == "on":
                    picow.register_notification(char_uuid, notification_handler)
                    print(f"[+] Notifications enabled for {char_uuid}")
                elif action == "off":
                    picow.unregister_notification(char_uuid)
                    print(f"[+] Notifications disabled for {char_uuid}")
                else:
                    print("Usage: notify <uuid> [on|off]")
            except Exception as exc:
                print(f"[-] Error: {exc}")
        
        elif command == "led":
            # Control onboard LED
            if not args:
                print("Usage: led <on|off>")
                continue
            
            action = args[0].lower()
            
            try:
                if action == "on":
                    picow.write_characteristic(PICOW_LED_CHAR_UUID, "0x01")
                    print("[+] LED turned on")
                elif action == "off":
                    picow.write_characteristic(PICOW_LED_CHAR_UUID, "0x00")
                    print("[+] LED turned off")
                else:
                    print("Usage: led <on|off>")
            except Exception as exc:
                print(f"[-] Error: {exc}")
        
        elif command == "temp":
            # Read temperature
            try:
                raw_bytes, hex_str, ascii_str = picow.read_characteristic(PICOW_TEMP_CHAR_UUID)
                
                # Try to parse temperature value
                if len(raw_bytes) >= 4:
                    import struct
                    temp = struct.unpack("<f", raw_bytes[:4])[0]
                    print(f"\nTemperature: {temp:.1f}°C")
                else:
                    print(f"\nTemperature value:")
                    print(f"  Hex: {hex_str}")
                    print(f"  ASCII: {ascii_str}")
                    print(f"  Raw bytes: {raw_bytes}")
                print()
            except Exception as exc:
                print(f"[-] Error reading temperature: {exc}")
        
        else:
            print(f"Unknown command: {command}")
            print("Type 'help' for available commands")

def parse_args(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BLEEP PicoW Mode")
    parser.add_argument("--device", help="MAC address of Pico W device")
    parser.add_argument("--scan", action="store_true", help="Scan for Pico W devices")
    parser.add_argument("--timeout", type=int, default=10, help="Scan timeout in seconds")
    parser.add_argument("--read", help="Read from characteristic")
    parser.add_argument("--write", help="Write to characteristic")
    parser.add_argument("--value", help="Value to write (used with --write)")
    parser.add_argument("--monitor", action="store_true", help="Monitor notifications from device")
    parser.add_argument("--time", type=int, default=30, help="Time to monitor notifications")
    return parser.parse_args(args)

def main(args=None) -> int:
    """Main entry point for PicoW Mode."""
    parsed_args = parse_args(args)
    
    # Scan for devices if requested
    if parsed_args.scan:
        picow_devices = scan_for_picow_devices(parsed_args.timeout)
        
        if not picow_devices:
            print_and_log("[-] No Pico W devices found", LOG__GENERAL)
            return 1
        
        print("\nFound Pico W devices:")
        for i, device in enumerate(picow_devices):
            print(f"{i+1}. {device['address']} - {device.get('name', 'Unknown')}")
        print()
        
        # If no device specified and devices found, use the first one
        if not parsed_args.device and picow_devices:
            parsed_args.device = picow_devices[0]["address"]
            print_and_log(f"[*] Using first device: {parsed_args.device}", LOG__GENERAL)
    
    # Connect to device
    if not parsed_args.device:
        print_and_log("[-] No device specified. Use --device or --scan", LOG__GENERAL)
        return 1
    
    picow = connect_to_picow(parsed_args.device)
    
    if not picow:
        print_and_log("[-] Failed to connect to device", LOG__GENERAL)
        return 1
    
    try:
        # Handle specific operations
        if parsed_args.read:
            # Read characteristic
            try:
                raw_bytes, hex_str, ascii_str = picow.read_characteristic(parsed_args.read)
                
                print(f"\nValue for {parsed_args.read}:")
                print(f"  Hex: {hex_str}")
                print(f"  ASCII: {ascii_str}")
                print(f"  Raw bytes: {raw_bytes}")
                print()
            except Exception as exc:
                print_and_log(f"[-] Read failed: {exc}", LOG__DEBUG)
                return 1
        
        elif parsed_args.write:
            # Write to characteristic
            if not parsed_args.value:
                print_and_log("[-] No value specified. Use --value", LOG__GENERAL)
                return 1
            
            try:
                picow.write_characteristic(parsed_args.write, parsed_args.value)
                print_and_log(f"[+] Value written to {parsed_args.write}", LOG__GENERAL)
            except Exception as exc:
                print_and_log(f"[-] Write failed: {exc}", LOG__DEBUG)
                return 1
        
        elif parsed_args.monitor:
            # Monitor notifications
            print_and_log(f"[*] Monitoring notifications for {parsed_args.time} seconds...", LOG__GENERAL)
            
            # Find characteristics with notify property
            notify_chars = []
            for uuid, info in picow.get_characteristics().items():
                if "notify" in info.get("Properties", []) or "indicate" in info.get("Properties", []):
                    notify_chars.append(uuid)
            
            if not notify_chars:
                print_and_log("[-] No characteristics with notify property found", LOG__GENERAL)
                return 1
            
            # Register for notifications
            for uuid in notify_chars:
                try:
                    picow.register_notification(uuid, notification_handler)
                    print_and_log(f"[+] Registered for notifications from {uuid}", LOG__GENERAL)
                except Exception as exc:
                    print_and_log(f"[-] Failed to register for notifications from {uuid}: {exc}", LOG__DEBUG)
            
            # Wait for notifications
            try:
                time.sleep(parsed_args.time)
            except KeyboardInterrupt:
                print_and_log("[*] Monitoring stopped by user", LOG__GENERAL)
            
            # Unregister notifications
            for uuid in notify_chars:
                try:
                    picow.unregister_notification(uuid)
                except:
                    pass
        
        else:
            # Interactive mode
            interactive_mode(picow)
    
    finally:
        # Clean up
        if picow:
            picow.cleanup()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
