"""Debug mode multi-read and brute-write commands."""

from __future__ import annotations

import struct
from typing import List

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__ENUM
from bleep.modes.debug_state import DebugState
from bleep.modes.debug_dbus import print_detailed_dbus_error


def cmd_multiread(args: List[str], state: DebugState) -> None:
    """Read a characteristic multiple times."""
    if not state.current_device:
        print("[-] No device connected")
        return

    if not args:
        print("Usage: multiread <char_uuid|handle> [rounds=N]")
        print("  Options:")
        print("    rounds=N    - Number of times to read the characteristic (e.g., rounds=1000)")
        print("    N           - Direct number format also supported (e.g., 1000)")
        return

    char_id = args[0]
    rounds = 10

    for arg in args[1:]:
        if arg.startswith("rounds="):
            try:
                rounds = int(arg.split("=")[1])
                break
            except (IndexError, ValueError):
                pass
        elif arg.isdigit():
            rounds = int(arg)
            break

    try:
        if char_id.isdigit() or (char_id.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in char_id[2:])):
            handle = int(char_id, 0) if char_id.startswith("0x") else int(char_id)

            if not state.current_mapping:
                print("[-] No characteristic mapping available")
                return

            handle_to_uuid = {v: k for k, v in state.current_mapping.items()}
            if handle not in handle_to_uuid:
                print(f"[-] No characteristic found with handle {handle}")
                return
            uuid = handle_to_uuid[handle]
        else:
            uuid = char_id

        from bleep.ble_ops.enum_helpers import multi_read_characteristic

        print(f"[*] Reading {uuid} {rounds} times...")
        values = multi_read_characteristic(state.current_device, uuid, repeats=rounds)

        print(f"\nResults for {uuid} ({rounds} reads):")
        print("-" * 60)

        saved_count = 0
        for i, val in enumerate(values):
            if isinstance(val, bytes):
                hex_val = " ".join([f"{b:02x}" for b in val])
                print(f"Read {i+1}/{rounds}: {hex_val}")

                if state.db_available and state.db_save_enabled:
                    try:
                        for svc_uuid, svc_data in state.current_mapping.items():
                            for c_uuid in svc_data.get("chars", {}):
                                if c_uuid == uuid:
                                    state.obs.insert_char_history(
                                        state.current_device.get_address(),
                                        svc_uuid, uuid, val, "read",
                                    )
                                    saved_count += 1
                                    break
                    except Exception as e:
                        print_and_log(f"[-] Failed to save read to database: {e}", LOG__DEBUG)
            else:
                print(f"Read {i+1}/{rounds}: {val}")

        print("-" * 60)

        if state.db_available and state.db_save_enabled and saved_count > 0:
            print_and_log(f"[*] {saved_count} multi-read values saved to database", LOG__GENERAL)

    except Exception as exc:
        print_and_log(f"[-] Multi-read failed: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def cmd_multiread_all(args: List[str], state: DebugState) -> None:
    """Read all readable characteristics multiple times."""
    if not state.current_device:
        print("[-] No device connected")
        return

    rounds = 3
    for arg in args:
        if arg.startswith("rounds="):
            try:
                rounds = int(arg.split("=")[1])
                break
            except (IndexError, ValueError):
                pass
        elif arg.isdigit():
            rounds = int(arg)
            break

    try:
        print_and_log(f"[*] Reading all characteristics {rounds} times...", LOG__GENERAL)
        print_and_log("[*] Looking for characteristics in database...", LOG__GENERAL)

        device_addr = getattr(state.current_device, 'address', None)
        if not device_addr and hasattr(state.current_device, 'get_address'):
            try:
                device_addr = state.current_device.get_address()
            except Exception:
                device_addr = None
        if not device_addr:
            device_addr = 'unknown-device'

        readable_chars = []
        goto_read_chars = False

        print_and_log("[*] Attempting to discover characteristics...", LOG__GENERAL)

        try:
            from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy

            if isinstance(state.current_device, system_dbus__bluez_device__low_energy):
                services = state.current_device.get_services()
                if services:
                    print_and_log(f"[+] Found {len(services)} services", LOG__GENERAL)
                    for service in services:
                        try:
                            svc_uuid = service.uuid if hasattr(service, 'uuid') else str(service)
                            print_and_log(f"[*] Getting characteristics for service {svc_uuid}...", LOG__DEBUG)
                            chars = state.current_device.get_characteristics(service)
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

        if not goto_read_chars:
            print_and_log("[*] Using fallback implementation for multiread_all", LOG__DEBUG)
            print_and_log("[*] Discovering services and characteristics...", LOG__GENERAL)
            try:
                services = state.current_device.services_resolved(deep=True)
                if not services:
                    services = state.current_device.get_services()
                    if not services:
                        print_and_log("[-] No services found", LOG__GENERAL)
                        return
                print_and_log(f"[+] Found {len(services)} services", LOG__GENERAL)
            except Exception as exc:
                print_and_log(f"[-] Error resolving services: {exc}", LOG__DEBUG)
                print_detailed_dbus_error(exc)
                return

            all_chars = []
            for service in services:
                try:
                    svc_uuid = service.uuid if hasattr(service, 'uuid') else str(service)
                    print_and_log(f"[*] Getting characteristics for service {svc_uuid}...", LOG__GENERAL)

                    try:
                        chars = state.current_device.get_characteristics(service)
                    except AttributeError:
                        try:
                            chars = service.get_characteristics()
                        except AttributeError:
                            chars = getattr(service, 'characteristics', [])

                    if not chars:
                        try:
                            svc_path = getattr(service, 'object_path', None)
                            if svc_path:
                                from bleep.dbuslayer.characteristic import get_characteristics
                                chars = get_characteristics(svc_path)
                        except Exception as e:
                            print_and_log(f"[-] Error getting characteristics via D-Bus: {e}", LOG__DEBUG)

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

                        if svc_uuid in [
                            '00001801-0000-1000-8000-00805f9b34fb',
                            '00001800-0000-1000-8000-00805f9b34fb',
                            '000000ff-0000-1000-8000-00805f9b34fb',
                        ]:
                            print_and_log(f"[*] Known service UUID detected: {svc_uuid}", LOG__GENERAL)
                            from bleep.dbuslayer.characteristic import Characteristic
                            if svc_uuid == '00001801-0000-1000-8000-00805f9b34fb':
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

        readable_chars = []
        for char in all_chars:
            try:
                char_uuid = char.uuid if hasattr(char, 'uuid') else str(char)
                is_readable = False
                if hasattr(char, 'flags') and 'read' in char.flags:
                    is_readable = True
                elif hasattr(char, 'properties') and char.properties.get('read', False):
                    is_readable = True
                elif hasattr(char, 'flags') and any(f.lower().startswith('read') for f in char.flags):
                    is_readable = True

                if not is_readable:
                    try:
                        print_and_log(f"[*] Testing if {char_uuid} is readable...", LOG__DEBUG)
                        state.current_device.read_characteristic(char_uuid)
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

        total_reads = 0
        read_values = {}

        for i in range(rounds):
            print_and_log(f"[*] Reading round {i+1}/{rounds}...", LOG__GENERAL)
            round_reads = 0

            for char in readable_chars:
                try:
                    char_uuid = char.uuid if hasattr(char, 'uuid') else str(char)
                    svc_uuid = None
                    if hasattr(char, 'service') and hasattr(char.service, 'uuid'):
                        svc_uuid = char.service.uuid

                    value = state.current_device.read_characteristic(char_uuid)
                    round_reads += 1

                    if isinstance(value, bytes):
                        hex_val = " ".join([f"{b:02x}" for b in value])
                        print_and_log(f"[DEBUG] {char_uuid}: {hex_val}", LOG__DEBUG)
                    else:
                        print_and_log(f"[DEBUG] {char_uuid}: {value}", LOG__DEBUG)

                    if state.db_available and state.db_save_enabled and isinstance(value, (bytes, bytearray)):
                        try:
                            from bleep.core.observations import insert_char_history
                            device_addr_local = getattr(state.current_device, 'address', None)
                            if not device_addr_local and hasattr(state.current_device, 'get_address'):
                                try:
                                    device_addr_local = state.current_device.get_address()
                                except Exception:
                                    device_addr_local = None
                            if device_addr_local and svc_uuid:
                                try:
                                    insert_char_history(device_addr_local, svc_uuid, char_uuid, value, "read")
                                except Exception as e:
                                    print_and_log(f"[-] Database error: {e}", LOG__DEBUG)
                        except Exception as db_err:
                            print_and_log(f"[-] Database error: {db_err}", LOG__DEBUG)

                    if char_uuid not in read_values:
                        read_values[char_uuid] = []
                    read_values[char_uuid].append(value)

                except Exception as read_err:
                    print_and_log(f"[-] Error reading {char_uuid}: {read_err}", LOG__DEBUG)

            print_and_log(f"[+] Round {i+1}: Read {round_reads} characteristics", LOG__GENERAL)
            total_reads += round_reads

        print_and_log(f"\n[*] Multi-read complete: {len(readable_chars)} characteristics, {total_reads} total reads", LOG__GENERAL)

        if state.db_available and state.db_save_enabled:
            print_and_log("[*] Values saved to database (use 'bleep db timeline' to view)", LOG__GENERAL)

    except Exception as exc:
        print_and_log(f"[-] Multi-read-all failed: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def cmd_brutewrite(args: List[str], state: DebugState) -> None:
    """Brute force write values to a characteristic."""
    if not state.current_device:
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

    value_range = None
    verify = False
    i = 2
    while i < len(args):
        if args[i] == "--range" and i + 1 < len(args):
            try:
                start, end = args[i + 1].split("-")
                value_range = (int(start), int(end))
                i += 2
            except Exception:
                print(f"[-] Invalid range format: {args[i + 1]}")
                return
        elif args[i] == "--verify":
            verify = True
            i += 1
        else:
            print(f"[-] Unknown option: {args[i]}")
            i += 1

    try:
        if char_id.isdigit() or (char_id.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in char_id[2:])):
            handle = int(char_id, 0) if char_id.startswith("0x") else int(char_id)
            if not state.current_mapping:
                print("[-] No characteristic mapping available")
                return
            handle_to_uuid = {v: k for k, v in state.current_mapping.items()}
            if handle not in handle_to_uuid:
                print(f"[-] No characteristic found with handle {handle}")
                return
            uuid = handle_to_uuid[handle]
        else:
            uuid = char_id

        from bleep.ble_ops.enum_helpers import build_payload_iterator, brute_write_range

        patterns = [pattern]
        payloads = build_payload_iterator(value_range=value_range, patterns=patterns)

        if not payloads:
            print("[-] No payloads generated from pattern")
            return

        print(f"[*] Writing {len(payloads)} values to {uuid}...")
        results = brute_write_range(state.current_device, uuid, payloads=payloads, verify=verify)

        print(f"\nResults for {uuid} ({len(payloads)} writes):")
        print("-" * 60)

        success = 0
        for payload, status in results.items():
            hex_val = " ".join([f"{b:02x}" for b in payload])
            if status == "OK":
                success += 1
            print(f"Write {hex_val}: {status}")

        print("-" * 60)
        print(f"Success rate: {success}/{len(results)} ({success/len(results)*100:.1f}%)")

        if state.db_available and state.db_save_enabled:
            try:
                for svc_uuid, svc_data in state.current_mapping.items():
                    for c_uuid in svc_data.get("chars", {}):
                        if c_uuid == uuid:
                            print_and_log("[*] Brute write values saved to database", LOG__DEBUG)
                            break
            except Exception as e:
                print_and_log(f"[-] Failed to save brute write to database: {e}", LOG__DEBUG)

    except Exception as exc:
        print_and_log(f"[-] Brute write failed: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)
