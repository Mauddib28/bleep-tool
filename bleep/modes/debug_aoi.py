"""AOI analysis and database commands for debug mode."""

from __future__ import annotations

import datetime
import json
from typing import List

from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.bt_ref.utils import get_name_from_uuid
from bleep.analysis.aoi_analyser import AOIAnalyser, analyse_aoi_data

from bleep.modes.debug_state import DebugState


def cmd_aoi(args: List[str], state: DebugState) -> None:
    """Analyze AOI data for a connected device or specified MAC address."""
    save_flag = "--save" in args
    if save_flag:
        args = [arg for arg in args if arg != "--save"]

    mac = None
    if args:
        mac = args[0]
    elif state.current_device:
        mac = state.current_device.mac_address

    if not mac:
        print("Error: No device connected and no MAC address provided")
        print("Usage: aoi [--save] [MAC]")
        return

    if save_flag:
        if not state.current_device or not state.current_mapping:
            print("Error: No device mapping available to save")
            return

        data = {
            "device_mac": state.current_device.mac_address,
            "timestamp": datetime.datetime.now().isoformat(),
            "services": {},
            "characteristics": {},
            "landmine_map": state.current_mine_map or {},
            "permission_map": state.current_perm_map or {},
        }

        for svc_uuid, chars in state.current_mapping.items():
            service_info = {
                "uuid": svc_uuid,
                "name": get_name_from_uuid(svc_uuid),
                "characteristics": [c[0] for c in chars],
            }
            data["services"][svc_uuid] = service_info

            for char_uuid, _, _ in chars:
                char_info = {}
                try:
                    if state.current_device:
                        properties = state.current_device.get_characteristic_properties(svc_uuid, char_uuid)
                        char_info["properties"] = properties
                except Exception as e:
                    print(f"Warning: Could not read properties for {char_uuid}: {str(e)}")

                data["characteristics"][char_uuid] = {
                    "uuid": char_uuid,
                    "name": get_name_from_uuid(char_uuid),
                    **char_info,
                }

        try:
            analyser = AOIAnalyser()
            filepath = analyser.save_device_data(mac, data)
            print(f"[+] Device data saved to {filepath}")
        except Exception as e:
            print(f"[-] Failed to save device data: {str(e)}")

    try:
        report = analyse_aoi_data(mac)

        print("\n[*] AOI Analysis Report")
        print(f"Device: {mac}")
        print(f"Timestamp: {report['timestamp']}")

        print("\n[*] Security Concerns:")
        if report["summary"]["security_concerns"]:
            for concern in report["summary"]["security_concerns"]:
                print(f" - {concern['name']} ({concern['uuid']}): {concern['reason']}")
        else:
            print(" - None identified")

        print("\n[*] Unusual Characteristics:")
        if report["summary"]["unusual_characteristics"]:
            for unusual in report["summary"]["unusual_characteristics"]:
                print(f" - {unusual['name']} ({unusual['uuid']}): {unusual['reason']}")
        else:
            print(" - None identified")

        print("\n[*] Notable Services:")
        if report["summary"]["notable_services"]:
            for service in report["summary"]["notable_services"]:
                print(f" - {service['name']} ({service['uuid']}): {service['reason']}")
        else:
            print(" - None identified")

        acc = report["summary"]["accessibility"]
        print("\n[*] Accessibility:")
        print(f" - Total characteristics: {acc['total_characteristics']}")
        print(f" - Blocked: {acc['blocked_characteristics']}")
        print(f" - Protected: {acc['protected_characteristics']}")
        print(f" - Score: {acc['accessibility_score']:.2%}")

        print("\n[*] Recommendations:")
        for rec in report["summary"]["recommendations"]:
            print(f" - {rec}")

    except FileNotFoundError:
        print(f"[-] No AOI data found for device {mac}")
        if state.current_device and state.current_device.mac_address == mac:
            print("[*] Hint: Use 'aoi --save' to save current device data")
    except Exception as e:
        print(f"[-] AOI analysis failed: {str(e)}")


def cmd_dbsave(args: List[str], state: DebugState) -> None:
    """Toggle database saving on/off."""
    if not state.db_available:
        print("[-] Database module not available")
        return

    if args and args[0].lower() in ("on", "true", "1", "yes"):
        state.db_save_enabled = True
        print("[*] Database saving enabled")
    elif args and args[0].lower() in ("off", "false", "0", "no"):
        state.db_save_enabled = False
        print("[*] Database saving disabled")
    else:
        state.db_save_enabled = not state.db_save_enabled
        print(f"[*] Database saving {'enabled' if state.db_save_enabled else 'disabled'}")


def cmd_dbexport(args: List[str], state: DebugState) -> None:
    """Export device data from database."""
    if not state.db_available:
        print("[-] Database module not available")
        return
    if not state.current_device:
        print("[-] No device connected")
        return

    try:
        mac = state.current_device.get_address()
        data = state.obs.export_device_data(mac)

        if not data.get('device'):
            print(f"[-] No data found for device {mac}")
            return

        print(f"[*] Device: {data['device'].get('name', 'Unknown')}")
        print(f"[*] MAC: {data['device'].get('mac', 'Unknown')}")
        print(f"[*] Services: {len(data['services'])}")
        print(f"[*] Characteristics: {len(data['characteristics'])}")
        print(f"[*] Characteristic history entries: {len(data.get('characteristic_history', []))}")

        if args and args[0].lower() == "--save":
            filename = f"bleep_debug_export_{mac.replace(':', '')}.json"
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"[*] Exported data to {filename}")

    except Exception as e:
        print(f"[-] Export failed: {e}")
