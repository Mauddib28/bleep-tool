#!/usr/bin/env python3
"""Scratch Mode for BLEEP.

This mode processes data from a file (/tmp/processed_data.txt by default)
and performs batch operations on devices based on the file content.

Usage:
  python -m bleep -m scratch [options]

Options:
  --input <file>     Input file to process (default: /tmp/processed_data.txt)
  --output <file>    Output file for results (default: /tmp/scratch_results.txt)
  --format <fmt>     Input file format: text, json, csv (default: text)
  --timeout <sec>    Operation timeout in seconds (default: 30)
  --dry-run          Show what would be done without executing operations
"""

import argparse
import sys
import os
import json
import csv
import time
from typing import Dict, List, Any, Optional, Tuple

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
from bleep.ble_ops.scan import passive_scan
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum

# Default file paths
DEFAULT_INPUT_FILE = "/tmp/processed_data.txt"
DEFAULT_OUTPUT_FILE = "/tmp/scratch_results.txt"

class DeviceOperation:
    """Class representing an operation to perform on a device."""
    
    def __init__(self, device_mac: str, operation_type: str, params: Dict[str, Any] = None):
        self.device_mac = device_mac
        self.operation_type = operation_type
        self.params = params or {}
        self.result = None
        self.error = None
        self.executed = False
    
    def execute(self, dry_run: bool = False, timeout: int = 30) -> bool:
        """Execute the operation on the device."""
        if dry_run:
            print_and_log(f"[DRY RUN] Would execute {self.operation_type} on {self.device_mac} with params: {self.params}", LOG__GENERAL)
            self.result = "DRY RUN"
            return True
        
        print_and_log(f"[*] Executing {self.operation_type} on {self.device_mac}...", LOG__GENERAL)
        
        try:
            # Connect to device
            device, mapping, _, _ = _connect_enum(self.device_mac, timeout=timeout)
            
            # Execute operation based on type
            if self.operation_type == "read":
                self.result = self._execute_read(device, mapping)
            elif self.operation_type == "write":
                self.result = self._execute_write(device, mapping)
            elif self.operation_type == "connect":
                self.result = "Connected successfully"
            elif self.operation_type == "pair":
                self.result = self._execute_pair(device)
            elif self.operation_type == "trust":
                self.result = self._execute_trust(device)
            elif self.operation_type == "info":
                self.result = self._execute_info(device)
            else:
                raise ValueError(f"Unknown operation type: {self.operation_type}")
            
            # Disconnect from device
            try:
                device.disconnect()
            except:
                pass
            
            self.executed = True
            print_and_log(f"[+] Operation {self.operation_type} on {self.device_mac} completed successfully", LOG__GENERAL)
            return True
        
        except Exception as exc:
            self.error = str(exc)
            print_and_log(f"[-] Operation {self.operation_type} on {self.device_mac} failed: {exc}", LOG__DEBUG)
            return False
    
    def _execute_read(self, device, mapping) -> Any:
        """Execute a read operation."""
        char_uuid = self.params.get("uuid")
        if not char_uuid:
            raise ValueError("No UUID specified for read operation")
        
        char = device._find_characteristic(char_uuid, mapping)
        if not char:
            raise ValueError(f"Characteristic not found: {char_uuid}")
        
        value = char.ReadValue({})
        
        # Convert to a readable format
        raw_bytes = bytes(value)
        hex_str = " ".join([f"{b:02x}" for b in raw_bytes])
        
        try:
            ascii_str = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            ascii_str = "".join([chr(b) if 32 <= b <= 126 else '.' for b in raw_bytes])
        
        return {
            "raw": list(raw_bytes),
            "hex": hex_str,
            "ascii": ascii_str
        }
    
    def _execute_write(self, device, mapping) -> Any:
        """Execute a write operation."""
        char_uuid = self.params.get("uuid")
        value = self.params.get("value")
        
        if not char_uuid:
            raise ValueError("No UUID specified for write operation")
        
        if value is None:
            raise ValueError("No value specified for write operation")
        
        char = device._find_characteristic(char_uuid, mapping)
        if not char:
            raise ValueError(f"Characteristic not found: {char_uuid}")
        
        # Convert value to bytes
        if isinstance(value, str):
            if value.startswith("0x"):
                # Hex string
                byte_array = bytearray.fromhex(value[2:])
            else:
                # ASCII string
                byte_array = value.encode('utf-8')
        elif isinstance(value, list):
            # List of integers
            byte_array = bytearray(value)
        else:
            raise ValueError(f"Unsupported value type: {type(value)}")
        
        # Write the value
        char.WriteValue(byte_array, {})
        
        return "Write successful"
    
    def _execute_pair(self, device) -> Any:
        """Execute a pair operation."""
        if device.is_paired():
            return "Device already paired"
        
        device.pair()
        return "Pairing successful"
    
    def _execute_trust(self, device) -> Any:
        """Execute a trust operation."""
        if device.is_trusted():
            return "Device already trusted"
        
        device.trust()
        return "Trust successful"
    
    def _execute_info(self, device) -> Any:
        """Execute an info operation."""
        return {
            "name": device.get_name(),
            "alias": device.get_alias(),
            "address_type": device.get_address_type(),
            "rssi": device.get_rssi(),
            "connected": device.is_connected(),
            "paired": device.is_paired(),
            "trusted": device.is_trusted(),
            "blocked": device.is_blocked(),
            "services_resolved": device.services_resolved()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the operation to a dictionary."""
        return {
            "device_mac": self.device_mac,
            "operation_type": self.operation_type,
            "params": self.params,
            "result": self.result,
            "error": self.error,
            "executed": self.executed
        }

def parse_text_file(file_path: str) -> List[DeviceOperation]:
    """Parse a text file into device operations.
    
    Expected format:
    <device_mac> <operation_type> [param1=value1] [param2=value2] ...
    """
    operations = []
    
    with open(file_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            parts = line.split()
            if len(parts) < 2:
                print_and_log(f"[-] Line {line_num}: Invalid format, skipping", LOG__DEBUG)
                continue
            
            device_mac = parts[0]
            operation_type = parts[1].lower()
            
            # Parse parameters
            params = {}
            for param in parts[2:]:
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
                else:
                    # If no '=', treat as a flag parameter
                    params[param] = True
            
            operations.append(DeviceOperation(device_mac, operation_type, params))
    
    return operations

def parse_json_file(file_path: str) -> List[DeviceOperation]:
    """Parse a JSON file into device operations.
    
    Expected format:
    [
        {
            "device_mac": "00:11:22:33:44:55",
            "operation_type": "read",
            "params": {
                "uuid": "00002a00-0000-1000-8000-00805f9b34fb"
            }
        },
        ...
    ]
    """
    operations = []
    
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        raise ValueError("JSON file must contain a list of operations")
    
    for item in data:
        if not isinstance(item, dict):
            print_and_log(f"[-] Invalid item format in JSON, skipping: {item}", LOG__DEBUG)
            continue
        
        device_mac = item.get("device_mac")
        operation_type = item.get("operation_type")
        params = item.get("params", {})
        
        if not device_mac or not operation_type:
            print_and_log(f"[-] Missing required fields in JSON item, skipping: {item}", LOG__DEBUG)
            continue
        
        operations.append(DeviceOperation(device_mac, operation_type, params))
    
    return operations

def parse_csv_file(file_path: str) -> List[DeviceOperation]:
    """Parse a CSV file into device operations.
    
    Expected format:
    device_mac,operation_type,param1,value1,param2,value2,...
    """
    operations = []
    
    with open(file_path, 'r', newline='') as f:
        reader = csv.reader(f)
        
        # Skip header row if present
        first_row = next(reader, None)
        if first_row and first_row[0].lower() == "device_mac" and first_row[1].lower() == "operation_type":
            pass  # Header row, already skipped
        else:
            # Not a header row, process it
            process_csv_row(first_row, operations)
        
        # Process remaining rows
        for row in reader:
            process_csv_row(row, operations)
    
    return operations

def process_csv_row(row, operations):
    """Process a CSV row and add to operations list."""
    if not row or len(row) < 2:
        return
    
    device_mac = row[0]
    operation_type = row[1].lower()
    
    # Parse parameters
    params = {}
    for i in range(2, len(row), 2):
        if i + 1 < len(row):
            params[row[i]] = row[i + 1]
    
    operations.append(DeviceOperation(device_mac, operation_type, params))

def parse_input_file(file_path: str, file_format: str) -> List[DeviceOperation]:
    """Parse an input file based on its format."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")
    
    if file_format == "text":
        return parse_text_file(file_path)
    elif file_format == "json":
        return parse_json_file(file_path)
    elif file_format == "csv":
        return parse_csv_file(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_format}")

def write_results_to_file(operations: List[DeviceOperation], file_path: str) -> None:
    """Write operation results to a file in JSON format."""
    results = [op.to_dict() for op in operations]
    
    with open(file_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print_and_log(f"[+] Results written to {file_path}", LOG__GENERAL)

def print_results_summary(operations: List[DeviceOperation]) -> None:
    """Print a summary of operation results."""
    total = len(operations)
    executed = sum(1 for op in operations if op.executed)
    failed = sum(1 for op in operations if op.error is not None)
    
    print("\nOperation Results Summary:")
    print(f"  Total operations: {total}")
    print(f"  Executed: {executed}")
    print(f"  Failed: {failed}")
    print(f"  Success rate: {(executed - failed) / total * 100:.1f}% ({executed - failed}/{total})")
    
    if failed > 0:
        print("\nFailed operations:")
        for op in operations:
            if op.error is not None:
                print(f"  {op.device_mac} - {op.operation_type}: {op.error}")
    
    print()

def parse_args(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BLEEP Scratch Mode")
    parser.add_argument("--input", default=DEFAULT_INPUT_FILE,
                      help=f"Input file to process (default: {DEFAULT_INPUT_FILE})")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE,
                      help=f"Output file for results (default: {DEFAULT_OUTPUT_FILE})")
    parser.add_argument("--format", choices=["text", "json", "csv"], default="text",
                      help="Input file format (default: text)")
    parser.add_argument("--timeout", type=int, default=30,
                      help="Operation timeout in seconds (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                      help="Show what would be done without executing operations")
    return parser.parse_args(args)

def main(args=None) -> int:
    """Main entry point for Scratch Mode."""
    parsed_args = parse_args(args)
    
    print_and_log("[*] BLEEP Scratch Mode", LOG__GENERAL)
    
    try:
        # Parse input file
        print_and_log(f"[*] Parsing input file: {parsed_args.input} (format: {parsed_args.format})", LOG__GENERAL)
        operations = parse_input_file(parsed_args.input, parsed_args.format)
        print_and_log(f"[+] Parsed {len(operations)} operations", LOG__GENERAL)
        
        if not operations:
            print_and_log("[-] No operations to execute", LOG__GENERAL)
            return 1
        
        # Execute operations
        for i, operation in enumerate(operations):
            print_and_log(f"[*] Operation {i+1}/{len(operations)}: {operation.operation_type} on {operation.device_mac}", LOG__GENERAL)
            operation.execute(parsed_args.dry_run, parsed_args.timeout)
        
        # Write results to file
        write_results_to_file(operations, parsed_args.output)
        
        # Print summary
        print_results_summary(operations)
        
        # Return success if all operations succeeded
        return 0 if all(op.error is None for op in operations) else 1
    
    except Exception as exc:
        print_and_log(f"[-] Error: {exc}", LOG__DEBUG)
        return 1

if __name__ == "__main__":
    sys.exit(main())
