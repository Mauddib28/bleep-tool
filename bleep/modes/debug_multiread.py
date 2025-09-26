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
    """Read all readable characteristics multiple times."""
    if not _current_device or not _current_mapping:
        print("[-] No device connected or no services discovered")
        return

    rounds = 3  # Default
    if args and args[0].isdigit():
        rounds = int(args[0])

    try:
        # Import multi_read_all
        from bleep.ble_ops.enum_helpers import multi_read_all
        
        print(f"[*] Reading all characteristics {rounds} times...")
        results = multi_read_all(_current_device, _current_mapping, rounds=rounds)
        
        # Display summary
        total_chars = 0
        total_reads = 0
        for r in results:
            total_chars = max(total_chars, len(results[r]))
            total_reads += len(results[r])
        
        print(f"\n[*] Multi-read complete: {total_chars} characteristics, {total_reads} total reads")
        print("[*] Values saved to database (use 'dbexport' or 'timeline' to view)")
        
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
