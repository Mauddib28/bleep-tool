"""GATT operations and notification callback for debug mode."""

from __future__ import annotations

import datetime
import json
import os
import re
import select
import struct
import time
from typing import Any, Dict, List

import dbus

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.bt_ref.utils import get_name_from_uuid
from bleep.modes.debug_utils import parse_value
from bleep.ble_ops.common.conversion import format_device_class, decode_appearance, decode_pnp_id
from bleep.ble_ops.common.modalias import format_modalias_info

from bleep.modes.debug_state import DebugState, DEVICE_PROMPT
from bleep.modes.debug_dbus import print_detailed_dbus_error

__all__ = [
    "show_properties",
    "get_handle_from_dict",
    "cmd_services",
    "cmd_chars",
    "cmd_char",
    "cmd_read",
    "cmd_write",
    "cmd_notify",
    "cmd_detailed",
]


# ---------------------------------------------------------------------------
# Property display helpers
# ---------------------------------------------------------------------------

def show_properties(props: Dict[str, Any], detailed: bool = False) -> None:
    """Format and print D-Bus properties."""
    for key, value in sorted(props.items()):
        formatted_value = value

        if key.lower().endswith('uuid') and isinstance(value, str):
            if detailed:
                uuid_name = get_name_from_uuid(value)
                if uuid_name != "Unknown":
                    formatted_value = f"{value} ({uuid_name})"
        elif isinstance(value, list) and key.lower().endswith('uuids'):
            if detailed:
                formatted_uuids = []
                for uuid in value:
                    uuid_name = get_name_from_uuid(uuid)
                    if uuid_name != "Unknown":
                        formatted_uuids.append(f"{uuid} ({uuid_name})")
                    else:
                        formatted_uuids.append(uuid)
                formatted_value = formatted_uuids
        elif key == "Class" and detailed:
            class_desc = format_device_class(value)
            formatted_value = f"Value: {value}         {class_desc}"
        elif key == "Appearance" and detailed:
            appearance_desc = decode_appearance(value)
            if appearance_desc:
                formatted_value = f"{value} ({appearance_desc})"
        elif key == "Modalias" and detailed and isinstance(value, str):
            formatted_value = format_modalias_info(value)

        if isinstance(formatted_value, (list, dict)):
            print(f"  {key}: {json.dumps(formatted_value, indent=2)}")
        else:
            print(f"  {key}: {formatted_value}")


# ---------------------------------------------------------------------------
# Handle extraction
# ---------------------------------------------------------------------------

def get_handle_from_dict(obj) -> int:
    """Extract handle from a service, characteristic, or descriptor.

    Tries direct attributes, dictionary keys, and path-based extraction.
    Returns -1 if no handle could be found.
    """
    if hasattr(obj, 'handle') and obj.handle is not None:
        return obj.handle
    if isinstance(obj, dict) and "handle" in obj:
        return obj["handle"]

    path = ""
    if hasattr(obj, 'path'):
        path = obj.path
    elif isinstance(obj, dict) and "path" in obj:
        path = obj["path"]

    if path:
        for prefix in ("char", "service", "desc"):
            if prefix in path:
                match = re.search(rf'{prefix}([0-9a-fA-F]{{4}})$', path)
                if match:
                    return int(match.group(1), 16)
    return -1


# ---------------------------------------------------------------------------
# GATT commands
# ---------------------------------------------------------------------------

def cmd_services(args: List[str], state: DebugState) -> None:
    """List GATT services of the current device."""
    if not state.current_device:
        print("[-] No device connected")
        return

    force_refresh = "--refresh" in args

    try:
        # Use cached mapping when available (unless --refresh)
        if state.current_mapping and not force_refresh:
            services = state.current_device.services_resolved(skip_device_type_check=True)
        else:
            # If services aren't resolved, try reconnect + poll
            if not state.current_device.is_services_resolved():
                if not state.current_device.is_connected():
                    print("[*] Device disconnected — reconnecting…")
                    state.current_device.connect()

                import time as _time
                print("[*] Waiting for services to resolve…")
                for _ in range(20):
                    if state.current_device.is_services_resolved():
                        break
                    _time.sleep(0.5)

            services = state.current_device.services_resolved(skip_device_type_check=True)
            if services and state.current_mapping is None:
                state.current_mapping = services

        if not services:
            print("\nNo GATT services found on device")
            print("This may be because:")
            print("  1. The device doesn't expose any GATT services")
            print("  2. Services haven't been resolved yet")
            print("  3. There was an error during service discovery")
            print("\nTry: 'services --refresh' or 'call org.bluez.Device1 Connect'")
            print()
            return

        print("\nGATT Services:")
        for service in services:
            uuid = service.uuid
            path = service.path
            handle = get_handle_from_dict(service)

            if state.detailed_view:
                uuid_name = get_name_from_uuid(uuid)
                print(f"  {uuid} - {uuid_name} - [0x{handle:04x} - {handle} - Service]")
                print(f"    Path: {path}")
            else:
                print(f"  [0x{handle:04x}] {uuid}")
            print(f"    Path: {path}")

            characteristics = service.get_characteristics()
            print(f"    ({len(characteristics)} characteristics)")
            if characteristics:
                print("    Characteristics:")
                for char in characteristics:
                    char_uuid = char.uuid
                    char_flags = ", ".join(char.flags)
                    char_handle = char.handle if char.handle is not None else -1

                    if state.detailed_view:
                        char_uuid_name = get_name_from_uuid(char_uuid)
                        print(f"      {char_uuid} - {char_uuid_name} - [0x{char_handle:04x} - {char_handle} - Characteristic]")
                    else:
                        print(f"      [0x{char_handle:04x}] {char_uuid}")
                    print(f"        Flags: {char_flags}")

                    descriptors = char.descriptors
                    if descriptors:
                        print("        Descriptors:")
                        for desc in descriptors:
                            desc_uuid = desc.uuid
                            desc_handle = desc.handle if desc.handle is not None else -1

                            if state.detailed_view:
                                desc_uuid_name = get_name_from_uuid(desc_uuid)
                                print(f"          {desc_uuid} - {desc_uuid_name} - [0x{desc_handle:04x} - {desc_handle} - Descriptor]")
                            else:
                                print(f"          [0x{desc_handle:04x}] {desc_uuid}")
        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving services: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def cmd_chars(args: List[str], state: DebugState) -> None:
    """List characteristics for a service."""
    if not state.current_device:
        print("[-] No device connected")
        return
    if not args:
        print("Usage: chars <service_uuid>")
        return

    service_uuid = args[0]
    try:
        if not state.current_device.services_resolved():
            print("[-] Services not yet resolved. Try connecting first.")
            return

        service = state.current_device._find_service(service_uuid)
        if not service:
            print(f"[-] Service with UUID {service_uuid} not found")
            return

        characteristics = service.get_characteristics()
        if not characteristics:
            print("[-] No characteristics found for this service")
            return

        print(f"\nCharacteristics for service {service_uuid}")
        if state.detailed_view:
            uuid_name = get_name_from_uuid(service_uuid)
            if uuid_name != "Unknown":
                print(f"  ↳ {uuid_name}")

        for char in characteristics:
            uuid = char.get_uuid()
            handle = char.get_handle()
            props = char.get_flags()

            print(f"\n  Characteristic: {uuid}")
            if state.detailed_view:
                uuid_name = get_name_from_uuid(uuid)
                if uuid_name != "Unknown":
                    print(f"    ↳ {uuid_name}")
            print(f"    Handle: {handle}")
            print(f"    Properties: {', '.join(props)}")

            descriptors = char.get_descriptors()
            if descriptors:
                print("    Descriptors:")
                for desc in descriptors:
                    desc_uuid = desc.get_uuid()
                    desc_handle = desc.get_handle()
                    print(f"      Descriptor: {desc_uuid}")
                    if state.detailed_view:
                        uuid_name = get_name_from_uuid(desc_uuid)
                        if uuid_name != "Unknown":
                            print(f"        ↳ {uuid_name}")
                    print(f"        Handle: {desc_handle}")
        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving characteristics: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def cmd_char(args: List[str], state: DebugState) -> None:
    """Show detailed information about a specific characteristic."""
    if not state.current_device:
        print("[-] No device connected")
        return
    if not args:
        print("Usage: char <characteristic_uuid>")
        return

    char_uuid = args[0]
    try:
        if not state.current_device.services_resolved():
            print("[-] Services not yet resolved. Try connecting first.")
            return

        char = state.current_device._find_characteristic(char_uuid)
        if not char:
            print(f"[-] Characteristic with UUID {char_uuid} not found")
            return

        print(f"\nCharacteristic Details for {char_uuid}")
        if state.detailed_view:
            uuid_name = get_name_from_uuid(char_uuid)
            if uuid_name != "Unknown":
                print(f"  ↳ {uuid_name}")

        print(f"  Handle: {char.get_handle()}")
        print(f"  Properties: {', '.join(char.get_flags())}")
        print(f"  Path: {char.path}")
        print(f"  Parent Service UUID: {char.parent_service_uuid}")

        descriptors = char.get_descriptors()
        if descriptors:
            print("\n  Descriptors:")
            for desc in descriptors:
                desc_uuid = desc.get_uuid()
                desc_handle = desc.get_handle()
                print(f"    Descriptor: {desc_uuid}")
                if state.detailed_view:
                    uuid_name = get_name_from_uuid(desc_uuid)
                    if uuid_name != "Unknown":
                        print(f"      ↳ {uuid_name}")
                print(f"      Handle: {desc_handle}")
                try:
                    value = desc.read_value()
                    hex_str = " ".join([f"{b:02x}" for b in value])
                    print(f"      Value (HEX): {hex_str}")
                    try:
                        ascii_str = value.decode('ascii')
                        if all(32 <= ord(c) <= 126 for c in ascii_str):
                            print(f"      Value (ASCII): \"{ascii_str}\"")
                    except UnicodeDecodeError:
                        pass
                except Exception as e:
                    print(f"      Value: <Error reading: {str(e)}>")
        else:
            print("\n  No descriptors found for this characteristic")
        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving characteristic details: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def _resolve_char_uuid(char_id: str, state: DebugState) -> str | None:
    """Resolve a handle or UUID string to a characteristic UUID.

    Returns None and prints an error if resolution fails.
    """
    if char_id.isdigit() or (char_id.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in char_id[2:])):
        handle = int(char_id, 0) if char_id.startswith("0x") else int(char_id)
        if not state.current_mapping:
            print("[-] No characteristic mapping available")
            return None
        handle_to_uuid = {v: k for k, v in state.current_mapping.items()}
        if handle not in handle_to_uuid:
            print(f"[-] No characteristic found with handle {handle}")
            return None
        return handle_to_uuid[handle]
    return char_id


def cmd_read(args: List[str], state: DebugState) -> None:
    """Read a characteristic value.

    Usage: read [--stream] <char_uuid|handle>

    With ``--stream``, uses AcquireNotify fd-based streaming (BZ-1e) to
    continuously read incoming data until Ctrl-C.  Falls back to standard
    ReadValue if the characteristic does not support AcquireNotify.
    """
    if not state.current_device:
        print("[-] No device connected")
        return
    if not args:
        print("Usage: read [--stream] <char_uuid|handle>")
        return

    stream = "--stream" in args
    filtered = [a for a in args if a != "--stream"]
    if not filtered:
        print("Usage: read [--stream] <char_uuid|handle>")
        return

    uuid = _resolve_char_uuid(filtered[0], state)
    if uuid is None:
        return

    if stream:
        _stream_read(uuid, state)
        return

    try:
        value = state.current_device.read_characteristic(uuid)

        if state.db_available and state.db_save_enabled and state.current_mapping:
            try:
                for svc_uuid, svc_data in state.current_mapping.items():
                    for c_uuid in svc_data.get("chars", {}):
                        if c_uuid == uuid:
                            state.obs.insert_char_history(
                                state.current_device.get_address(),
                                svc_uuid, uuid, value, "read",
                            )
                            print_and_log("[*] Read value saved to database", LOG__DEBUG)
                            break
            except Exception as e:
                print_and_log(f"[-] Failed to save read to database: {e}", LOG__DEBUG)

        try:
            ascii_str = value.decode('ascii')
            if all(32 <= ord(c) <= 126 for c in ascii_str):
                print(f"\nValue (ASCII): \"{ascii_str}\"")
            else:
                raise ValueError
        except (UnicodeDecodeError, ValueError):
            pass

        try:
            utf8_str = value.decode('utf-8')
            print(f"Value (UTF-8): \"{utf8_str}\"")
        except UnicodeDecodeError:
            pass

        hex_str = " ".join([f"{b:02x}" for b in value])
        print(f"Value (HEX): {hex_str}")

        if uuid == "00002A50-0000-1000-8000-00805F9B34FB" and len(value) == 7 and state.detailed_view:
            pnp_info = decode_pnp_id(value)
            print(f"Value (PnP ID): {pnp_info}")

        profile_decoded = _try_profile_decode(uuid, value)
        if profile_decoded:
            print(f"Value (Profile): {profile_decoded}")

        _print_numeric_interpretations(value)
        print()
    except Exception as exc:
        print_and_log(f"[-] Read failed: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def _stream_read(uuid: str, state: DebugState) -> None:
    """Stream data from a characteristic via AcquireNotify fd (BZ-1e)."""
    char = state.current_device.get_characteristic(uuid)
    if char is None:
        print(f"[-] Characteristic {uuid} not found")
        return

    try:
        fd, mtu = char.acquire_notify()
    except dbus.exceptions.DBusException as exc:
        print(f"[-] AcquireNotify not supported for {uuid}: {exc}")
        print(f"[*] Use 'notify {uuid}' for D-Bus PropertiesChanged notifications instead")
        return

    print(f"[+] Streaming from fd={fd}, mtu={mtu}  (Ctrl-C to stop)")
    count = 0
    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 2.0)
            if not ready:
                continue
            data = os.read(fd, mtu or 512)
            if not data:
                print("[*] Stream closed by remote")
                break
            count += 1
            hex_str = " ".join(f"{b:02x}" for b in data)
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"  [{ts}] #{count:>5d}  ({len(data):>3d} B)  {hex_str}")

            if state.db_available and state.db_save_enabled and state.current_mapping:
                try:
                    for svc_uuid, svc_data in state.current_mapping.items():
                        for c_uuid in svc_data.get("chars", {}):
                            if c_uuid == uuid:
                                state.obs.insert_char_history(
                                    state.current_device.get_address(),
                                    svc_uuid, uuid, data, "notification",
                                )
                                break
                except Exception:
                    pass
    except KeyboardInterrupt:
        print(f"\n[*] Stream stopped after {count} packets")
    finally:
        char.release_acquired()


def _try_profile_decode(uuid: str, value: bytes) -> str | None:
    """Try profile-specific decode for known GATT characteristics."""
    try:
        from bleep.ble_ops.common.gatt_profile_decode import decode_characteristic_value
        return decode_characteristic_value(uuid, value)
    except Exception:
        return None


def _print_numeric_interpretations(value: bytes) -> None:
    """Print integer/float interpretations when the byte length matches."""
    if len(value) not in (1, 2, 4, 8):
        return
    try:
        if len(value) == 1:
            print(f"Value (uint8): {value[0]}")
            print(f"Value (int8): {struct.unpack('b', value)[0]}")
        elif len(value) == 2:
            print(f"Value (uint16, little-endian): {struct.unpack('<H', value)[0]}")
            print(f"Value (int16, little-endian): {struct.unpack('<h', value)[0]}")
            print(f"Value (uint16, big-endian): {struct.unpack('>H', value)[0]}")
            print(f"Value (int16, big-endian): {struct.unpack('>h', value)[0]}")
        elif len(value) == 4:
            print(f"Value (uint32, little-endian): {struct.unpack('<I', value)[0]}")
            print(f"Value (int32, little-endian): {struct.unpack('<i', value)[0]}")
            print(f"Value (uint32, big-endian): {struct.unpack('>I', value)[0]}")
            print(f"Value (int32, big-endian): {struct.unpack('>i', value)[0]}")
            try:
                print(f"Value (float, little-endian): {struct.unpack('<f', value)[0]}")
                print(f"Value (float, big-endian): {struct.unpack('>f', value)[0]}")
            except Exception:
                pass
        elif len(value) == 8:
            print(f"Value (uint64, little-endian): {struct.unpack('<Q', value)[0]}")
            print(f"Value (int64, little-endian): {struct.unpack('<q', value)[0]}")
            print(f"Value (uint64, big-endian): {struct.unpack('>Q', value)[0]}")
            print(f"Value (int64, big-endian): {struct.unpack('>q', value)[0]}")
            try:
                print(f"Value (double, little-endian): {struct.unpack('<d', value)[0]}")
                print(f"Value (double, big-endian): {struct.unpack('>d', value)[0]}")
            except Exception:
                pass
    except Exception as e:
        print(f"Value (numeric conversions): Error - {e}")


def cmd_write(args: List[str], state: DebugState) -> None:
    """Write to a characteristic.

    Usage: write [--stream] <char_uuid|handle> <value>

    With ``--stream``, uses AcquireWrite fd-based streaming (BZ-1e) to
    bypass per-packet D-Bus overhead.  Falls back to standard WriteValue
    if the characteristic does not support AcquireWrite.
    """
    if not state.current_device:
        print("[-] No device connected")
        return

    stream = "--stream" in args
    filtered = [a for a in args if a != "--stream"]

    if len(filtered) < 2:
        print("Usage: write [--stream] <char_uuid|handle> <value>")
        print("  --stream            Use AcquireWrite fd (lower overhead)")
        print("  Value formats:")
        print("    hex:[01ab23cd]    - Interpret as hex bytes")
        print("    str:hello         - Interpret as ASCII/UTF-8 string")
        print("    uint8:123         - 8-bit unsigned integer")
        print("    int8:-123         - 8-bit signed integer")
        print("    uint16:12345      - 16-bit unsigned integer (little-endian)")
        print("    int16:-12345      - 16-bit signed integer (little-endian)")
        print("    uint16be:12345    - 16-bit unsigned integer (big-endian)")
        print("    int16be:-12345    - 16-bit signed integer (big-endian)")
        print("    uint32:123456     - 32-bit unsigned integer (little-endian)")
        print("    int32:-123456     - 32-bit signed integer (little-endian)")
        print("    uint32be:123456   - 32-bit unsigned integer (big-endian)")
        print("    int32be:-123456   - 32-bit signed integer (big-endian)")
        print("    float:123.456     - 32-bit float (little-endian)")
        print("    floatbe:123.456   - 32-bit float (big-endian)")
        print("    double:123.456    - 64-bit double (little-endian)")
        print("    doublebe:123.456  - 64-bit double (big-endian)")
        return

    uuid = _resolve_char_uuid(filtered[0], state)
    if uuid is None:
        return

    value_str = filtered[1]

    try:
        value, err = parse_value(value_str)
        if err:
            print(f"[-] {err}")
            return

        if stream:
            char = state.current_device.get_characteristic(uuid)
            if char is None:
                print(f"[-] Characteristic {uuid} not found")
                return
            written = char.write_value_fd(value)
            print(f"\n[+] Streamed {written} bytes to {uuid} via AcquireWrite fd")
        else:
            state.current_device.write_characteristic(uuid, value)
            print(f"\n[+] Successfully wrote to characteristic {uuid}")

        if state.db_available and state.db_save_enabled and state.current_mapping:
            try:
                for svc_uuid, svc_data in state.current_mapping.items():
                    for c_uuid in svc_data.get("chars", {}):
                        if c_uuid == uuid:
                            state.obs.insert_char_history(
                                state.current_device.get_address(),
                                svc_uuid, uuid, value, "write",
                            )
                            print_and_log("[*] Write value saved to database", LOG__DEBUG)
                            break
            except Exception as e:
                print_and_log(f"[-] Failed to save write to database: {e}", LOG__DEBUG)

        print()
    except Exception as exc:
        print_and_log(f"[-] Write failed: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def cmd_notify(args: List[str], state: DebugState) -> None:
    """Subscribe or unsubscribe to notifications from a characteristic."""
    if not state.current_device or not state.current_mapping:
        print("[-] No device connected or no services discovered")
        return
    if not args:
        print("Usage: notify <char_uuid|handle> [on|off]")
        return

    uuid = _resolve_char_uuid(args[0], state)
    if uuid is None:
        return

    action = "on"
    if len(args) > 1:
        action = args[1].lower()
        if action not in ("on", "off"):
            print("Action must be 'on' or 'off'")
            return

    try:
        char = state.current_device._find_characteristic(uuid)
        if not char:
            print(f"[-] Characteristic not found: {uuid}")
            return
        if "notify" not in char.flags:
            print(f"[-] Characteristic does not support notifications. Flags: {', '.join(char.flags)}")
            return

        callback = _make_notification_callback(state)
        if action == "on":
            state.current_device.enable_notifications(uuid, callback)
            print(f"[+] Notifications enabled for {uuid}")
        else:
            state.current_device.disable_notifications(uuid)
            print(f"[+] Notifications disabled for {uuid}")
    except Exception as exc:
        print_and_log(f"[-] Error with notifications: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def cmd_detailed(args: List[str], state: DebugState) -> None:
    """Toggle detailed view mode."""
    if args and args[0].lower() in ("on", "off"):
        state.detailed_view = args[0].lower() == "on"
    else:
        state.detailed_view = not state.detailed_view
    print(f"[*] Detailed view mode: {'ON' if state.detailed_view else 'OFF'}")
    print("[*] Use 'services' or 'chars' commands to see the effect")


# ---------------------------------------------------------------------------
# Notification callback factory
# ---------------------------------------------------------------------------

# Module-level signal history shared across callbacks
_signal_history: List[dict] = []


def _make_notification_callback(state: DebugState):
    """Return a notification callback bound to *state*."""

    def callback(value, path=None, interface=None, signal_name=None, timestamp=None):
        _notification_callback_impl(value, path, interface, signal_name, timestamp, state)

    return callback


def _notification_callback_impl(
    value, path, interface, signal_name, timestamp, state: DebugState,
) -> None:
    """Comprehensive callback for debugging notification signals."""
    global _signal_history

    if state.db_available and state.db_save_enabled and state.current_device and state.current_mapping:
        try:
            char_uuid = None
            if path and "/char" in path:
                for part in path.split("/"):
                    if len(part) >= 32:
                        char_uuid = part
                        break
            if char_uuid:
                for svc_uuid, svc_data in state.current_mapping.items():
                    for c_uuid in svc_data.get("chars", {}):
                        if c_uuid == char_uuid:
                            state.obs.insert_char_history(
                                state.current_device.get_address(),
                                svc_uuid, char_uuid,
                                value if isinstance(value, bytes) else bytes(str(value), 'utf-8'),
                                "notification",
                            )
                            print_and_log("[*] Notification saved to database", LOG__DEBUG)
                            break
        except Exception as e:
            print_and_log(f"[-] Failed to save notification to database: {e}", LOG__DEBUG)

    if timestamp is None:
        timestamp = time.time()

    signal_type = "NOTIFICATION"
    if interface and signal_name:
        if interface == "org.freedesktop.DBus.Properties" and signal_name == "PropertiesChanged":
            signal_type = "PROPERTY_CHANGE"
        elif signal_name == "InterfacesAdded":
            signal_type = "INTERFACE_ADDED"
        elif signal_name == "InterfacesRemoved":
            signal_type = "INTERFACE_REMOVED"

    if hasattr(value, '__class__') and 'dbus' in str(value.__class__):
        try:
            from bleep.bt_ref.utils import dbus_to_python
            value = dbus_to_python(value)
        except (ImportError, Exception):
            if isinstance(value, dbus.Array):
                value = bytes(value)
            elif isinstance(value, dbus.Dictionary):
                value = dict(value)
            elif isinstance(value, (dbus.Int16, dbus.Int32, dbus.Int64, dbus.UInt16, dbus.UInt32, dbus.UInt64)):
                value = int(value)
            elif isinstance(value, dbus.String):
                value = str(value)
            elif isinstance(value, dbus.Boolean):
                value = bool(value)

    original_value = value
    if isinstance(value, dict) and "Value" in value:
        value = value["Value"]

    timestamp_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

    print(f"\n[{timestamp_str}] {signal_type} RECEIVED:")
    if path:
        print(f"  Path: {path}")
    if interface:
        print(f"  Interface: {interface}")
    if signal_name:
        print(f"  Signal: {signal_name}")

    uuid_val = None
    handle = None
    if path:
        uuid_match = re.search(r'char([0-9a-fA-F]{4})$', path)
        if uuid_match:
            char_id = uuid_match.group(1)
            handle = int(char_id, 16)
            if state.current_mapping:
                handle_to_uuid = {v: k for k, v in state.current_mapping.items()}
                if handle in handle_to_uuid:
                    uuid_val = handle_to_uuid[handle]
        if uuid_val:
            try:
                uuid_name = get_name_from_uuid(uuid_val)
                print(f"  UUID: {uuid_val} ({uuid_name})")
            except Exception:
                print(f"  UUID: {uuid_val}")
            print(f"  Handle: 0x{handle:04x} ({handle})")

    if value is None:
        print("  Value: None")
    elif isinstance(value, (bytes, bytearray, list)):
        if isinstance(value, list):
            try:
                value = bytes(value)
            except Exception:
                pass
        try:
            hex_str = " ".join([f"{b:02x}" for b in value])
            print(f"  Value (HEX): {hex_str}")
        except Exception as e:
            print(f"  Value (HEX): Error converting to hex - {e}")
        try:
            ascii_str = "".join([chr(b) if 32 <= b <= 126 else '.' for b in value])
            print(f"  Value (ASCII): \"{ascii_str}\"")
        except Exception as e:
            print(f"  Value (ASCII): Error converting to ASCII - {e}")
        try:
            utf8_str = value.decode('utf-8', errors='replace')
            print(f"  Value (UTF-8): \"{utf8_str}\"")
        except Exception as e:
            print(f"  Value (UTF-8): Error converting to UTF-8 - {e}")

        if isinstance(value, (bytes, bytearray)) and len(value) in (1, 2, 4, 8):
            _print_numeric_interpretations(value)
    elif isinstance(value, dict):
        print("  Value (Dictionary):")
        for k, v in value.items():
            print(f"    {k}: {v}")
    else:
        print(f"  Value ({type(value).__name__}): {value}")

    if isinstance(original_value, dict) and len(original_value) > 1:
        print("  Additional Properties:")
        for k, v in original_value.items():
            if k != "Value":
                print(f"    {k}: {v}")

    signal_record = {
        "timestamp": timestamp, "type": signal_type, "path": path,
        "interface": interface, "signal_name": signal_name, "value": value,
    }
    _signal_history.append(signal_record)
    if len(_signal_history) > 20:
        _signal_history.pop(0)

    related = [
        r for r in _signal_history[:-1]
        if abs(r["timestamp"] - timestamp) <= 1.0
        and path and r["path"]
        and (path.startswith(r["path"]) or r["path"].startswith(path))
    ]
    if related:
        print("\n  Related Signals:")
        for idx, rec in enumerate(related):
            rel_time = rec["timestamp"] - timestamp
            print(f"    [{idx+1}] {rec['type']} at {rel_time:.3f}s ({rec['path']})")

    log_message = f"[NOTIFICATION] {signal_type} received at {timestamp_str}"
    if path:
        log_message += f"\n  Path: {path}"
    if interface:
        log_message += f"\n  Interface: {interface}"
    if signal_name:
        log_message += f"\n  Signal: {signal_name}"
    if isinstance(value, (bytes, bytearray)):
        log_message += f"\n  Value (HEX): {' '.join([f'{b:02x}' for b in value])}"
    else:
        log_message += f"\n  Value: {value}"
    print_and_log(log_message, LOG__DEBUG)

    if state.current_device:
        print(DEVICE_PROMPT.format(state.current_device.mac_address), end="", flush=True)
