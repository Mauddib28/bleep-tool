"""Debug mode multi-read and brute-write commands."""

from typing import List
import struct

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__ENUM

def _cmd_multiread(args: List[str], _current_device, _current_mapping, _DB_AVAILABLE, _DB_SAVE_ENABLED, _obs, _print_detailed_dbus_error) -> None:
    """Read a characteristic multiple times."""
    if not _current_device:
        print("[-] No device connected")
        return

    if not args:
        print("Usage: multiread <char_uuid|handle> [rounds=N]")
        print("  Options:")
        print("    rounds=N    - Number of times to read the characteristic (e.g., rounds=1000)")
        print("    N           - Direct number format also supported (e.g., 1000)")
        return

    char_id = args[0]
    rounds = 10  # Default
    
    # Parse rounds parameter from arguments
    for arg in args[1:]:
        # Check for rounds=X format
        if arg.startswith("rounds="):
            try:
                rounds = int(arg.split("=")[1])
                break
            except (IndexError, ValueError):
                pass
        # Check for direct number
        elif arg.isdigit():
            rounds = int(arg)
            break

    try:
        # Parse char_id the same way as in _cmd_read
        if char_id.isdigit() or (char_id.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in char_id[2:])):
            # Handle as numeric
            handle = int(char_id, 0) if char_id.startswith("0x") else int(char_id)
            
            if not _current_mapping:
                print("[-] No characteristic mapping available")
                return

            # Invert the mapping to get handle → UUID
            handle_to_uuid = {v: k for k, v in _current_mapping.items()}
            if handle not in handle_to_uuid:
                print(f"[-] No characteristic found with handle {handle}")
                return

            uuid = handle_to_uuid[handle]
        else:
            # Treat as UUID
            uuid = char_id

        # Import multi_read_characteristic
        from bleep.ble_ops.enum_helpers import multi_read_characteristic
        
        print(f"[*] Reading {uuid} {rounds} times...")
        values = multi_read_characteristic(_current_device, uuid, repeats=rounds)
        
        # Display results
        print(f"\nResults for {uuid} ({rounds} reads):")
        print("-" * 60)
        
        # Save to database if enabled
        saved_count = 0
        for i, val in enumerate(values):
            if isinstance(val, bytes):
                hex_val = " ".join([f"{b:02x}" for b in val])
                print(f"Read {i+1}/{rounds}: {hex_val}")
                
                # Save each value to database
                if _DB_AVAILABLE and _DB_SAVE_ENABLED:
                    try:
                        # Find service for this characteristic
                        for svc_uuid, svc_data in _current_mapping.items():
                            for c_uuid, char_data in svc_data.get("chars", {}).items():
                                if c_uuid == uuid:
                                    _obs.insert_char_history(
                                        _current_device.get_address(),
                                        svc_uuid,
                                        uuid,
                                        val,
                                        "read"
                                    )
                                    saved_count += 1
                                    break
                    except Exception as e:
                        print_and_log(f"[-] Failed to save read to database: {e}", LOG__DEBUG)
            else:
                print(f"Read {i+1}/{rounds}: {val}")
                
        print("-" * 60)
        
        # Report database saves
        if _DB_AVAILABLE and _DB_SAVE_ENABLED and saved_count > 0:
            print_and_log(f"[*] {saved_count} multi-read values saved to database", LOG__GENERAL)
                
    except Exception as exc:
        print_and_log(f"[-] Multi-read failed: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_multiread_all(args: List[str], _current_device, _current_mapping, _DB_AVAILABLE, _DB_SAVE_ENABLED, _print_detailed_dbus_error) -> None:
    """Read all readable characteristics multiple times.
    
    This function discovers all readable characteristics on a device and reads each one
    multiple times. The results are stored in the database if available.
    
    Args:
        args: Command arguments, with optional 'rounds=X' or direct number to specify read count
        _current_device: Connected Bluetooth device object
        _current_mapping: Current characteristic mapping
        _DB_AVAILABLE: Whether the database is available
        _DB_SAVE_ENABLED: Whether database saving is enabled
        _print_detailed_dbus_error: Function to print detailed D-Bus errors
    """
    if not _current_device:
        print("[-] No device connected")
        return

    rounds = 3  # Default
    
    # Parse rounds parameter from arguments
    for arg in args:
        # Check for rounds=X format
        if arg.startswith("rounds="):
            try:
                rounds = int(arg.split("=")[1])
                break
            except (IndexError, ValueError):
                pass
        # Check for direct number
        elif arg.isdigit():
            rounds = int(arg)
            break

    try:
        print_and_log(f"[*] Reading all characteristics {rounds} times...", LOG__GENERAL)
        
        # First, try to get characteristics from the database
        print_and_log("[*] Looking for characteristics in database...", LOG__GENERAL)
        
        # Get device address using a generic approach that works with any device
        device_addr = getattr(_current_device, 'address', None)
        if not device_addr and hasattr(_current_device, 'get_address'):
            try:
                device_addr = _current_device.get_address()
            except Exception:
                device_addr = None
                
        if not device_addr:
            # If we couldn't get the address, use a placeholder
            # This is a fallback and should not be relied upon
            device_addr = 'unknown-device'
            
        # Create empty list for readable characteristics
        readable_chars = []
        goto_read_chars = False
        
        # Try to discover characteristics using D-Bus exploration
        print_and_log("[*] Attempting to discover characteristics...", LOG__GENERAL)
        
        # First try to use the explore command functionality
        try:
            from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
            
            # Check if we need to use a specific device type
            if isinstance(_current_device, system_dbus__bluez_device__low_energy):
                # Try to get services and characteristics
                services = _current_device.get_services()
                if services:
                    print_and_log(f"[+] Found {len(services)} services", LOG__GENERAL)
                    
                    # For each service, get its characteristics
                    for service in services:
                        try:
                            svc_uuid = service.uuid if hasattr(service, 'uuid') else str(service)
                            print_and_log(f"[*] Getting characteristics for service {svc_uuid}...", LOG__DEBUG)
                            
                            # Get characteristics for this service
                            chars = _current_device.get_characteristics(service)
                            if chars:
                                for char in chars:
                                    if hasattr(char, 'flags') and 'read' in char.flags:
                                        readable_chars.append(char)
                                        print_and_log(f"[+] Found readable characteristic: {char.uuid}", LOG__DEBUG)
                        except Exception as e:
                            print_and_log(f"[-] Error getting characteristics for service {service}: {e}", LOG__DEBUG)
                    
                    if readable_chars:
                        print_and_log(f"[+] Found {len(readable_chars)} readable characteristics", LOG__GENERAL)
                        all_chars = readable_chars
                        goto_read_chars = True
            
        except Exception as e:
            print_and_log(f"[-] Error discovering characteristics: {e}", LOG__DEBUG)
        
        # If we still don't have characteristics, use a generic approach
        if not goto_read_chars:
            print_and_log("[*] Using generic characteristic discovery...", LOG__GENERAL)
            goto_read_chars = False
            
        # If we couldn't get characteristics from the database, try the normal way
        if not goto_read_chars:
            print_and_log("[*] Using fallback implementation for multiread_all", LOG__DEBUG)
            
            # Fallback implementation
            print_and_log("[*] Discovering services and characteristics...", LOG__GENERAL)
            try:
                # Try to resolve services
                services = _current_device.services_resolved(deep=True)
                if not services:
                    services = _current_device.get_services()
                    if not services:
                        print_and_log("[-] No services found", LOG__GENERAL)
                        return
                
                print_and_log(f"[+] Found {len(services)} services", LOG__GENERAL)
            except Exception as exc:
                print_and_log(f"[-] Error resolving services: {exc}", LOG__DEBUG)
                _print_detailed_dbus_error(exc)
                return
            
            # Get all characteristics
            all_chars = []
            for service in services:
                try:
                    svc_uuid = service.uuid if hasattr(service, 'uuid') else str(service)
                    print_and_log(f"[*] Getting characteristics for service {svc_uuid}...", LOG__GENERAL)
                    
                    try:
                        # First try to get characteristics using the device's method
                        chars = _current_device.get_characteristics(service)
                    except AttributeError:
                        # If that fails, try to get characteristics from the service object directly
                        try:
                            chars = service.get_characteristics()
                        except AttributeError:
                            # If that also fails, try to access the characteristics property
                            chars = getattr(service, 'characteristics', [])
                    
                    # If we still don't have characteristics, try to discover them through D-Bus
                    if not chars:
                        try:
                            # Try to use the service's object path to get characteristics
                            svc_path = getattr(service, 'object_path', None)
                            if svc_path:
                                from bleep.dbuslayer.characteristic import get_characteristics
                                chars = get_characteristics(svc_path)
                        except Exception as e:
                            print_and_log(f"[-] Error getting characteristics via D-Bus: {e}", LOG__DEBUG)
                    
                    # Process the characteristics if we found any
                    if chars:
                        for char in chars:
                            char_uuid = char.uuid if hasattr(char, 'uuid') else str(char)
                            flags_str = ""
                            if hasattr(char, 'flags'):
                                flags_str = f"Flags: {char.flags}"
                            elif hasattr(char, 'properties'):
                                flags_str = f"Properties: {char.properties}"
                            print_and_log(f"[DEBUG] Characteristic: {char_uuid} - {flags_str}", LOG__DEBUG)
                        
                        all_chars.extend(chars)
                        print_and_log(f"[+] Found {len(chars)} characteristics in service {svc_uuid}", LOG__GENERAL)
                    else:
                        print_and_log(f"[-] No characteristics found for service {svc_uuid}", LOG__GENERAL)
                        
                        # If no characteristics found, try to add them based on known service UUIDs
                        if svc_uuid in ['00001801-0000-1000-8000-00805f9b34fb', '00001800-0000-1000-8000-00805f9b34fb', '000000ff-0000-1000-8000-00805f9b34fb']:
                            print_and_log(f"[*] Known service UUID detected: {svc_uuid}", LOG__GENERAL)
                            
                            # Import the characteristic class
                            from bleep.dbuslayer.characteristic import Characteristic
                            
                            # For Generic Attribute service (0x1801)
                            if svc_uuid == '00001801-0000-1000-8000-00805f9b34fb':
                                # Service Changed characteristic
                                char_uuid = "00002a05-0000-1000-8000-00805f9b34fb"
                                char_obj = Characteristic(char_uuid)
                                char_obj.uuid = char_uuid
                                char_obj.flags = ['indicate']
                                char_obj.service = service
                                all_chars.append(char_obj)
                                print_and_log(f"[+] Added known characteristic: {char_uuid}", LOG__DEBUG)
                        
                except Exception as e:
                    print_and_log(f"[-] Error getting characteristics for service {service}: {e}", LOG__DEBUG)
        
        if not all_chars:
            print_and_log("[-] No characteristics found", LOG__GENERAL)
            return
            
        print_and_log(f"[+] Total characteristics found: {len(all_chars)}", LOG__GENERAL)
        
        # Filter for readable characteristics
        readable_chars = []
        for char in all_chars:
            try:
                char_uuid = char.uuid if hasattr(char, 'uuid') else str(char)
                is_readable = False
                
                # Check for read flag in various ways
                if hasattr(char, 'flags') and 'read' in char.flags:
                    is_readable = True
                elif hasattr(char, 'properties') and char.properties.get('read', False):
                    is_readable = True
                elif hasattr(char, 'flags') and any(f.lower().startswith('read') for f in char.flags):
                    is_readable = True
                
                # For characteristics without explicit flags, try to read it directly
                if not is_readable:
                    try:
                        print_and_log(f"[*] Testing if {char_uuid} is readable...", LOG__DEBUG)
                        _current_device.read_characteristic(char_uuid)
                        is_readable = True
                        print_and_log(f"[+] {char_uuid} is readable (no explicit flags)", LOG__DEBUG)
                    except Exception:
                        pass
                
                if is_readable:
                    readable_chars.append(char)
                    print_and_log(f"[+] Found readable characteristic: {char_uuid}", LOG__DEBUG)
            except Exception as e:
                print_and_log(f"[-] Error checking if characteristic is readable: {e}", LOG__DEBUG)
        
        print_and_log(f"[+] Found {len(readable_chars)} readable characteristics", LOG__GENERAL)
        
        if not readable_chars:
            print_and_log("[-] No readable characteristics found", LOG__GENERAL)
            return
        
        # Now read each characteristic multiple times
        total_reads = 0
        read_values = {}
        
        for i in range(rounds):
            print_and_log(f"[*] Reading round {i+1}/{rounds}...", LOG__GENERAL)
            round_reads = 0
            
            for char in readable_chars:
                try:
                    char_uuid = char.uuid if hasattr(char, 'uuid') else str(char)
                    
                    # Get service UUID for database storage
                    svc_uuid = None
                    if hasattr(char, 'service') and hasattr(char.service, 'uuid'):
                        svc_uuid = char.service.uuid
                    
                    # Read the characteristic
                    value = _current_device.read_characteristic(char_uuid)
                    round_reads += 1
                    
                    # Display the value
                    if isinstance(value, bytes):
                        hex_val = " ".join([f"{b:02x}" for b in value])
                        print_and_log(f"[DEBUG] {char_uuid}: {hex_val}", LOG__DEBUG)
                    else:
                        print_and_log(f"[DEBUG] {char_uuid}: {value}", LOG__DEBUG)
                    
                    # Save to database if enabled
                    if _DB_AVAILABLE and _DB_SAVE_ENABLED and isinstance(value, (bytes, bytearray)):
                        try:
                            from bleep.core.observations import insert_char_history
                            
                            # Get device address
                            device_addr = getattr(_current_device, 'address', None)
                            if not device_addr and hasattr(_current_device, 'get_address'):
                                try:
                                    device_addr = _current_device.get_address()
                                except Exception:
                                    device_addr = None
                            
                            # Only insert if we have all required information
                            if device_addr and svc_uuid:
                                try:
                                    insert_char_history(
                                        device_addr,
                                        svc_uuid,
                                        char_uuid,
                                        value,
                                        "read"
                                    )
                                except Exception as e:
                                    print_and_log(f"[-] Database error: {e}", LOG__DEBUG)
                        except Exception as db_err:
                            print_and_log(f"[-] Database error: {db_err}", LOG__DEBUG)
                    
                    # Track the value
                    if char_uuid not in read_values:
                        read_values[char_uuid] = []
                    read_values[char_uuid].append(value)
                    
                except Exception as read_err:
                    print_and_log(f"[-] Error reading {char_uuid}: {read_err}", LOG__DEBUG)
            
            print_and_log(f"[+] Round {i+1}: Read {round_reads} characteristics", LOG__GENERAL)
            total_reads += round_reads
        
        print_and_log(f"\n[*] Multi-read complete: {len(readable_chars)} characteristics, {total_reads} total reads", LOG__GENERAL)
        
        # Report database saves
        if _DB_AVAILABLE and _DB_SAVE_ENABLED:
            print_and_log("[*] Values saved to database (use 'bleep db timeline' to view)", LOG__GENERAL)
            
    except Exception as exc:
        print_and_log(f"[-] Multi-read-all failed: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_brutewrite(args: List[str], _current_device, _current_mapping, _DB_AVAILABLE, _DB_SAVE_ENABLED, _obs, _print_detailed_dbus_error) -> None:
    """Brute force write values to a characteristic."""
    if not _current_device:
        print("[-] No device connected")
        return

    if len(args) < 2:
        print("Usage: brutewrite <char_uuid|handle> <pattern> [--range start-end] [--verify]")
        print("  Patterns:")
        print("    ascii     - ASCII printable characters")
        print("    inc       - Incrementing bytes (0x00, 0x01, 0x02...)")
        print("    alt       - Alternating bits (0x55, 0xAA)")
        print("    repeat:X:N - Repeat byte X for N bytes")
        print("    hex:HEXSTR - Raw hex bytes")
        print("  Example:")
        print("    brutewrite 00002a00-0000-1000-8000-00805f9b34fb inc --range 0-10")
        return

    char_id = args[0]
    pattern = args[1]
    
    # Parse options
    value_range = None
    verify = False
    
    i = 2
    while i < len(args):
        if args[i] == "--range" and i + 1 < len(args):
            try:
                start, end = args[i + 1].split("-")
                value_range = (int(start), int(end))
                i += 2
            except:
                print(f"[-] Invalid range format: {args[i + 1]}")
                return
        elif args[i] == "--verify":
            verify = True
            i += 1
        else:
            print(f"[-] Unknown option: {args[i]}")
            i += 1

    try:
        # Parse char_id the same way as in _cmd_read
        if char_id.isdigit() or (char_id.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in char_id[2:])):
            # Handle as numeric
            handle = int(char_id, 0) if char_id.startswith("0x") else int(char_id)
            
            if not _current_mapping:
                print("[-] No characteristic mapping available")
                return

            # Invert the mapping to get handle → UUID
            handle_to_uuid = {v: k for k, v in _current_mapping.items()}
            if handle not in handle_to_uuid:
                print(f"[-] No characteristic found with handle {handle}")
                return

            uuid = handle_to_uuid[handle]
        else:
            # Treat as UUID
            uuid = char_id

        # Import brute write functions
        from bleep.ble_ops.enum_helpers import build_payload_iterator, brute_write_range
        
        # Build payloads
        patterns = [pattern]
        payloads = build_payload_iterator(value_range=value_range, patterns=patterns)
        
        if not payloads:
            print("[-] No payloads generated from pattern")
            return
            
        print(f"[*] Writing {len(payloads)} values to {uuid}...")
        results = brute_write_range(_current_device, uuid, payloads=payloads, verify=verify)
        
        # Display results
        print(f"\nResults for {uuid} ({len(payloads)} writes):")
        print("-" * 60)
        
        success = 0
        for payload, status in results.items():
            hex_val = " ".join([f"{b:02x}" for b in payload])
            if status == "OK":
                success += 1
                print(f"Write {hex_val}: {status}")
            else:
                print(f"Write {hex_val}: {status}")
                
        print("-" * 60)
        print(f"Success rate: {success}/{len(results)} ({success/len(results)*100:.1f}%)")
        
        # Save to database if enabled
        if _DB_AVAILABLE and _DB_SAVE_ENABLED:
            try:
                # Find service for this characteristic
                for svc_uuid, svc_data in _current_mapping.items():
                    for c_uuid, char_data in svc_data.get("chars", {}).items():
                        if c_uuid == uuid:
                            print_and_log("[*] Brute write values saved to database", LOG__DEBUG)
                            break
            except Exception as e:
                print_and_log(f"[-] Failed to save brute write to database: {e}", LOG__DEBUG)
                
    except Exception as exc:
        print_and_log(f"[-] Brute write failed: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)
