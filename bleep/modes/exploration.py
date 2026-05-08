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

# Heavy D-Bus and scan-mode imports are deferred into the functions that need
# them to prevent circular imports through the bleep.dbuslayer.device_le
# module-level singleton initialisation chain.  ``from __future__ import
# annotations`` (line 7) keeps type hints valid as strings.

# Scan-mode constants are lightweight (str values) — safe to import eagerly so
# they can be used in the parse/mode-map helpers at the top of the module.
from bleep.ble_ops.le.scan_modes import (
    PASSIVE_MODE,
    NAGGY_MODE,
    POKEY_MODE,
    BRUTEFORCE_MODE,
)

try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None


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
    """Collect GATT data from device and print summary. Always reads all readable
    characteristics for DB fidelity; display verbosity is controlled separately."""
    device_name = device.get_name() or device.get_alias() or "Unknown"

    result: Dict[str, Any] = {
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
    show_detail_threshold = 20

    for svc in device._services:
        service_count += 1
        service_info: Dict[str, Any] = {
            "uuid": svc.uuid,
            "path": svc.path,
            "characteristics": []
        }

        print_and_log(f"\n[*] Service: {svc.uuid}", LOG__GENERAL)

        for char in svc.characteristics:
            char_count += 1
            char_info: Dict[str, Any] = {
                "uuid": char.uuid,
                "path": char.path,
                "handle": char.handle,
                "flags": list(char.flags),
                "descriptors": []
            }

            should_print = verbose or char_count < show_detail_threshold

            if should_print:
                handle_str = f"(Handle: 0x{char.handle:04x})" if char.handle >= 0 else ""
                print_and_log(f"  [*] Characteristic: {char.uuid} {handle_str}", LOG__GENERAL)
                print_and_log(f"      Flags: {', '.join(char.flags)}", LOG__GENERAL)

            # Always read values for DB storage regardless of display threshold
            if "read" in char.flags:
                try:
                    value = char.read_value()
                    hex_value = value.hex()
                    ascii_value = "".join(chr(b) if 32 <= b <= 126 else "." for b in value)
                    char_info["value"] = {"hex": hex_value, "ascii": ascii_value}
                    if should_print and verbose:
                        print_and_log(f"      Value: {hex_value} (ASCII: {ascii_value})", LOG__GENERAL)
                except Exception as e:
                    char_info["read_error"] = str(e)
                    if should_print and verbose:
                        print_and_log(f"      Read error: {e}", LOG__GENERAL)

            # Always collect descriptors; read values for DB storage
            for desc in getattr(char, "descriptors", []):
                desc_info: Dict[str, Any] = {"uuid": desc.uuid, "path": desc.path}
                try:
                    desc_value = desc.read_value()
                    desc_info["value"] = {
                        "hex": desc_value.hex(),
                        "ascii": "".join(chr(b) if 32 <= b <= 126 else "." for b in desc_value)
                    }
                except Exception as e:
                    desc_info["read_error"] = str(e)

                char_info["descriptors"].append(desc_info)

                if should_print and verbose:
                    print_and_log(f"      [*] Descriptor: {desc.uuid}", LOG__GENERAL)
                    if "value" in desc_info:
                        print_and_log(f"          Value: {desc_info['value']['hex']}", LOG__GENERAL)
                    elif "read_error" in desc_info:
                        print_and_log(f"          Read error: {desc_info['read_error']}", LOG__GENERAL)

            service_info["characteristics"].append(char_info)

        result["device"]["services"].append(service_info)

    print_and_log(f"\n[*] Summary: {service_count} services, {char_count} characteristics", LOG__GENERAL)

    result["mappings"] = {
        "handle_to_uuid": {str(h): u for h, u in device.ble_device__mapping.items()},
        "landmine_map": {u: f for u, f in device.ble_device__mine_mapping.items()},
        "permission_map": {u: p for u, p in device.ble_device__permission_mapping.items()}
    }

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


def save_to_database(
    data: Dict[str, Any],
    mapping: Dict[str, Any] | None = None,
    device_props: Dict[str, Any] | None = None,
) -> None:
    """Save exploration data to the observation database.

    Parameters
    ----------
    data
        Result dict from ``print_service_info``.
    mapping
        GATT mapping from ``scan_and_connect`` (provides service handle ranges).
    device_props
        Raw Device1 D-Bus properties (provides RSSI, addr_type, etc.).
    """
    if _obs is None:
        print_and_log("[-] Observation DB unavailable – skipping save", LOG__GENERAL)
        return

    try:
        if not data.get("device"):
            print_and_log("[-] No device data to save to database", LOG__GENERAL)
            return

        device = data["device"]
        mac = device["address"]
        name = device["name"]
        perm_map = data.get("mappings", {}).get("permission_map", {})

        device_info: Dict[str, Any] = {"name": name}

        if device_props:
            try:
                from bleep.ble_ops.le.scan import _enrich_device_info_from_props
                _enrich_device_info_from_props(device_info, device_props)
            except ImportError:
                pass

        # Step 1: Insert device WITHOUT device_type so classifier can work
        _obs.upsert_device(mac, **device_info)

        # Step 2: Classify device type instead of hardcoding "le"
        try:
            from bleep.analysis.device_type_classifier import DeviceTypeClassifier
            classifier = DeviceTypeClassifier()
            context = {
                "device_class": device_info.get("device_class"),
                "address_type": device_info.get("addr_type"),
                "uuids": [str(u) for u in device_props.get("UUIDs", [])] if device_props else [],
                "connected": True,
            }
            result = classifier.classify_with_mode(
                mac=mac, context=context, scan_mode="naggy", use_database_cache=True,
            )
            _obs.upsert_device(mac, device_type=result.device_type)
        except Exception as cls_err:
            print_and_log(f"[-] Device type classification fallback to 'le': {cls_err}", LOG__DEBUG)
            _obs.upsert_device(mac, device_type="le")

        # --- Services (Gap 5: include handle ranges from mapping) ---
        services = []
        for service in device.get("services", []):
            svc_uuid = service["uuid"]
            svc_entry: Dict[str, Any] = {"uuid": svc_uuid}

            if mapping and isinstance(mapping.get(svc_uuid), dict):
                svc_data = mapping[svc_uuid]
                svc_entry["handle_start"] = svc_data.get("start_handle")
                svc_entry["handle_end"] = svc_data.get("end_handle")
                svc_entry["name"] = svc_data.get("name")
            services.append(svc_entry)

        if services:
            service_ids = _obs.upsert_services(mac, services)

            for service in device.get("services", []):
                service_uuid = service["uuid"]
                service_id = service_ids.get(service_uuid)
                if not service_id:
                    continue

                chars = []
                for char in service.get("characteristics", []):
                    value = None
                    if isinstance(char.get("value"), dict):
                        value_hex = char["value"].get("hex")
                        if value_hex:
                            try:
                                value = bytes.fromhex(value_hex)
                            except ValueError:
                                pass

                    # Gap 4: include permission_map for this characteristic
                    char_perm = perm_map.get(char["uuid"])

                    chars.append({
                        "uuid": char["uuid"],
                        "handle": char.get("handle"),
                        "properties": char.get("flags", []),
                        "value": value,
                        "permission_map": char_perm,
                    })

                    # Gap 6: record value in char_history for audit trail
                    if value is not None:
                        try:
                            _obs.insert_char_history(
                                mac, service_uuid, char["uuid"], value, source="explore",
                            )
                        except Exception:
                            pass

                if chars:
                    _obs.upsert_characteristics(service_id, chars, mac=mac, service_uuid=service_uuid)

                    # Persist descriptors for each characteristic
                    for char in service.get("characteristics", []):
                        if not char.get("descriptors"):
                            continue
                        try:
                            char_id = _obs.get_characteristic_id(service_id, char["uuid"])
                            if char_id:
                                descs = []
                                for d in char["descriptors"]:
                                    d_val = None
                                    if isinstance(d.get("value"), dict) and d["value"].get("hex"):
                                        try:
                                            d_val = bytes.fromhex(d["value"]["hex"])
                                        except ValueError:
                                            pass
                                    descs.append({"uuid": d["uuid"], "value": d_val})
                                if descs:
                                    _obs.upsert_descriptors(char_id, descs)
                        except Exception:
                            pass

        print_and_log(f"[+] Saved exploration data to database for device {mac}", LOG__GENERAL)
    except Exception as e:
        print_and_log(f"[-] Error saving to database: {e}", LOG__GENERAL)


def main() -> int:
    """Main function for exploration mode."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
    from bleep.ble_ops.le.scan_modes import scan_and_connect

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

        if mode == PASSIVE_MODE:
            kwargs["timeout"] = args.timeout

        device, mapping, landmine_map, perm_map = scan_and_connect(
            args.device,
            mode=mode,
            **kwargs
        )

        # Collect Device1 D-Bus properties for DB enrichment and display
        try:
            from bleep.ble_ops.le.scan import _collect_device_props
            device_props = _collect_device_props(device)
        except Exception:
            device_props = {}

        result = print_service_info(device, args.verbose)

        # Always save to database with full context
        save_to_database(result, mapping=mapping, device_props=device_props)

        if output_file:
            save_to_json(result, output_file)

        return 0
    except Exception as e:
        print_and_log(f"[-] Error: {e}", LOG__GENERAL)
        return 1


if __name__ == "__main__":
    sys.exit(main()) 