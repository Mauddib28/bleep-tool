"""BLEEP Assets-of-Interest (AoI) mode – iterate over lists of target MACs and analyze them.

This mode provides functionality to:
1. Scan multiple devices from JSON files containing MAC addresses
2. Analyze device data for security concerns and unusual characteristics
3. Generate security reports in various formats (markdown, JSON, text)
4. Store device data for offline analysis
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
from bleep.bt_ref.utils import get_name_from_uuid


_DEF_WAIT = 4.0  # seconds between targets


def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bleep-aoi", add_help=False)
    
    # Create subparsers for different commands
    subparsers = p.add_subparsers(dest="command", help="AOI command to execute")
    
    # Scan command (original functionality)
    scan_parser = subparsers.add_parser("scan", help="Scan and enumerate devices from AoI files")
    scan_parser.add_argument("files", nargs="+", metavar="FILE", help="JSON files containing AoI device lists")
    scan_parser.add_argument("--delay", type=float, default=_DEF_WAIT, help="Seconds to wait between devices")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a specific device")
    analyze_parser.add_argument("--address", "-a", required=True, help="MAC address of the device to analyze")
    analyze_parser.add_argument("--deep", action="store_true", help="Perform deeper analysis (more comprehensive)")
    analyze_parser.add_argument("--timeout", type=int, default=30, help="Analysis timeout in seconds")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all saved AoI devices")
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate a report for a device")
    report_parser.add_argument("--address", "-a", required=True, help="MAC address of the device")
    report_parser.add_argument("--format", "-f", choices=["markdown", "json", "text"], 
                              default="markdown", help="Report format")
    report_parser.add_argument("--output", "-o", help="Output file (defaults to auto-generated)")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export device data")
    export_parser.add_argument("--address", "-a", help="MAC address to export (omit for all devices)")
    export_parser.add_argument("--output", "-o", default=".", help="Output directory")
    
    p.add_argument("--help", "-h", action="help")
    return p


def _iter_macs(obj) -> List[str]:
    """Return list of mac strings inside *obj* (supports nested dict format)."""
    if isinstance(obj, list):
        macs = []
        for item in obj:
            if isinstance(item, dict) and "address" in item:
                macs.append(item["address"])
            elif isinstance(item, str):
                macs.append(item)
            else:
                macs.extend(_iter_macs(item))
        return macs
    if isinstance(obj, dict):
        macs: List[str] = []
        # Check if this dict is a device object with an address
        if "address" in obj:
            macs.append(obj["address"])
        # Otherwise recurse through values
        for val in obj.values():
            macs.extend(_iter_macs(val))
        return macs
    return []


def _generate_markdown_report(device_data: Dict[str, Any]) -> str:
    """Generate a detailed Markdown report from device data."""
    address = device_data.get("address", "Unknown")
    name = device_data.get("name", "Unknown Device")
    scan_time = datetime.datetime.fromtimestamp(device_data.get("scan_timestamp", 0)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Start with device header
    report = f"# Device Report: {name} ({address})\n\n"
    report += f"**Scan Date:** {scan_time}\n\n"
    
    # Add services section
    services = device_data.get("services", [])
    report += f"## Services ({len(services)})\n\n"
    
    for service_uuid in services:
        service_name = get_name_from_uuid(service_uuid) or "Unknown Service"
        report += f"- **{service_uuid}** - {service_name}\n"
    
    report += "\n"
    
    # Add analysis section if available
    if "analysis" in device_data:
        analysis = device_data["analysis"]
        report += "## Security Analysis\n\n"
        
        # Security concerns
        security_concerns = analysis.get("summary", {}).get("security_concerns", [])
        report += f"### Security Concerns ({len(security_concerns)})\n\n"
        if security_concerns:
            for concern in security_concerns:
                report += f"- **{concern.get('name', 'Unknown')}**: {concern.get('reason', 'No details')}\n"
        else:
            report += "No security concerns detected.\n"
        
        report += "\n"
        
        # Unusual characteristics
        unusual_chars = analysis.get("summary", {}).get("unusual_characteristics", [])
        report += f"### Unusual Characteristics ({len(unusual_chars)})\n\n"
        if unusual_chars:
            for char in unusual_chars:
                report += f"- **{char.get('name', 'Unknown')}**: {char.get('reason', 'No details')}\n"
        else:
            report += "No unusual characteristics detected.\n"
    
    return report


def _generate_json_report(device_data: Dict[str, Any]) -> str:
    """Generate a JSON report from device data."""
    # Create a report structure
    report = {
        "device": {
            "address": device_data.get("address", "Unknown"),
            "name": device_data.get("name", "Unknown Device"),
            "scan_timestamp": device_data.get("scan_timestamp", 0),
        },
        "services": device_data.get("services", []),
        "analysis": device_data.get("analysis", {})
    }
    
    # Convert to JSON string
    return json.dumps(report, indent=2)


def _generate_text_report(device_data: Dict[str, Any]) -> str:
    """Generate a plain text report from device data."""
    address = device_data.get("address", "Unknown")
    name = device_data.get("name", "Unknown Device")
    scan_time = datetime.datetime.fromtimestamp(device_data.get("scan_timestamp", 0)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Start with device header
    report = f"Device Report: {name} ({address})\n"
    report += f"Scan Date: {scan_time}\n\n"
    
    # Add services section
    services = device_data.get("services", [])
    report += f"Services ({len(services)}):\n"
    
    for service_uuid in services:
        service_name = get_name_from_uuid(service_uuid) or "Unknown Service"
        report += f"- {service_uuid} - {service_name}\n"
    
    report += "\n"
    
    # Add analysis section if available
    if "analysis" in device_data:
        analysis = device_data["analysis"]
        report += "Security Analysis:\n\n"
        
        # Security concerns
        security_concerns = analysis.get("summary", {}).get("security_concerns", [])
        report += f"Security Concerns ({len(security_concerns)}):\n"
        if security_concerns:
            for concern in security_concerns:
                report += f"- {concern.get('name', 'Unknown')}: {concern.get('reason', 'No details')}\n"
        else:
            report += "No security concerns detected.\n"
        
        report += "\n"
        
        # Unusual characteristics
        unusual_chars = analysis.get("summary", {}).get("unusual_characteristics", [])
        report += f"Unusual Characteristics ({len(unusual_chars)}):\n"
        if unusual_chars:
            for char in unusual_chars:
                report += f"- {char.get('name', 'Unknown')}: {char.get('reason', 'No details')}\n"
        else:
            report += "No unusual characteristics detected.\n"
    
    return report


## TODO: Actions to perform or add to the AoI code
#   [ ] Incorporate enumerate__assets_of_interest
#
#
##########


def main(argv: list[str] | None = None):
    argv = argv or sys.argv[1:]
    args = _arg_parser().parse_args(argv)

    # Initialize AOI analyzer
    from bleep.analysis.aoi_analyser import AOIAnalyser
    analyzer = AOIAnalyser()
    
    # Handle different commands
    if args.command == "scan" or not args.command:
        # Original scan functionality
        if not hasattr(args, 'files') or not args.files:
            print_and_log("[-] No files specified for scanning", LOG__GENERAL)
            return 1
            
        for file_path in args.files:
            path = Path(file_path).expanduser()
            if not path.exists():
                print_and_log(f"[-] File not found: {path}", LOG__GENERAL)
                continue
            print_and_log(f"[*] Processing AoI file {path}", LOG__GENERAL)
            with path.open() as f:
                try:
                    data = json.load(f)
                except Exception as e:
                    print_and_log(f"[-] Failed to parse {path}: {e}", LOG__GENERAL)
                    continue
            for mac in _iter_macs(data):
                mac_up = mac.upper()
                normalized = mac_up.replace("-", ":")
                print_and_log(f"[*] AoI connect+enum {mac_up}", LOG__GENERAL)
                try:
                    device, services_mapping, landmine_map, permission_map = _connect_enum(mac_up)
                    
                    # Save device data for later analysis
                    if device:
                        device_data = {
                            "address": normalized,
                            "name": getattr(device, "get_name", lambda: getattr(device, "name", "Unknown"))() or getattr(device, "name", "Unknown"),
                            "services": device.get_services() if hasattr(device, 'get_services') else [],
                            "services_mapping": services_mapping,
                            "landmine_map": landmine_map,
                            "permission_map": permission_map,
                            "scan_timestamp": time.time()
                        }
                        analyzer.save_device_data(normalized, device_data)
                        print_and_log(f"[+] Device data saved for {normalized}", LOG__GENERAL)
                        
                except Exception as e:
                    print_and_log(f"[-] Failed: {e}", LOG__GENERAL)
                time.sleep(args.delay)
                
        print_and_log("[+] AoI scan complete", LOG__GENERAL)
    
    elif args.command == "analyze":
        # Analyze a specific device
        print_and_log(f"[*] Analyzing device: {args.address}", LOG__GENERAL)
        try:
            device_data = analyzer.load_device_data(args.address)
        except FileNotFoundError:
            print_and_log(f"No data found for device {args.address}", LOG__GENERAL)
            return 1
        except Exception as e:
            print_and_log(f"[-] Error loading device data: {e}", LOG__GENERAL)
            return 1
        
        if not device_data:
            print_and_log(f"[-] No data found for device {args.address}", LOG__GENERAL)
            return 1
            
        # Perform analysis
        analysis = {}
        if hasattr(analyzer, 'analyze_device_data'):
            analysis = analyzer.analyze_device_data(device_data)
        else:
            # Fallback to basic analysis if the method doesn't exist
            analysis = {
                "summary": {
                    "security_concerns": [],
                    "unusual_characteristics": [],
                    "notable_services": [],
                    "accessibility": {"read": [], "write": [], "notify": []},
                    "recommendations": []
                },
                "details": {
                    "services": [],
                    "characteristics": [],
                    "landmine_map": {},
                    "permission_map": {}
                }
            }
            # Basic service analysis
            if "services" in device_data and device_data["services"]:
                for service_uuid in device_data["services"]:
                    analysis["details"]["services"].append({
                        "uuid": service_uuid,
                        "name": "Unknown Service",
                        "is_notable": False
                    })
            
            # Add services mapping to details
            if "services_mapping" in device_data:
                analysis["details"]["services_mapping"] = device_data["services_mapping"]
            
        # Save analysis results back to device data
        device_data["analysis"] = analysis
        analyzer.save_device_data(args.address, device_data)
        
        # Print summary
        print_and_log(f"[+] Analysis complete for {args.address}", LOG__GENERAL)
        if "summary" in analysis:
            summary = analysis["summary"]
            if "security_concerns" in summary:
                print_and_log(f"[!] Found {len(summary['security_concerns'])} security concerns", LOG__GENERAL)
            if "unusual_characteristics" in summary:
                print_and_log(f"[!] Found {len(summary['unusual_characteristics'])} unusual characteristics", LOG__GENERAL)
                
        print_and_log("[*] Use 'bleep aoi report --address <mac>' to generate a detailed report", LOG__GENERAL)
    
    elif args.command == "list":
        # List all saved devices
        devices = analyzer.list_devices()
        
        if not devices:
            print_and_log("[*] No AoI devices found", LOG__GENERAL)
            return 0
            
        print_and_log(f"[*] Found {len(devices)} AoI devices:", LOG__GENERAL)
        for i, address in enumerate(devices, 1):
            device_data = analyzer.load_device_data(address)
            name = device_data.get("name", "Unknown")
            analyzed = "analysis" in device_data
            status = "Analyzed" if analyzed else "Not analyzed"
            print_and_log(f"{i}. {address} - {name} ({status})", LOG__GENERAL)
    
    elif args.command == "report":
        # Generate a report for a device
        print_and_log(f"[*] Generating {args.format} report for device: {args.address}", LOG__GENERAL)
        
        try:
            # Load device data
            device_data = analyzer.load_device_data(args.address)
            if not device_data:
                print_and_log(f"[-] No data found for device {args.address}", LOG__GENERAL)
                return 1
            
            # Generate report based on format
            if args.format == "markdown":
                report = _generate_markdown_report(device_data)
            elif args.format == "json":
                report = _generate_json_report(device_data)
            else:  # text format
                report = _generate_text_report(device_data)
            
            if args.output:
                # Save to specified file
                with open(args.output, 'w') as f:
                    f.write(report)
                print_and_log(f"[+] Report saved to {args.output}", LOG__GENERAL)
            else:
                # Save to auto-generated file
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_addr = args.address.replace(":", "").lower()
                output_file = f"{safe_addr}_report_{timestamp}.{args.format}"
                output_path = analyzer.aoi_dir / output_file
                
                with open(output_path, 'w') as f:
                    f.write(report)
                print_and_log(f"[+] Report saved to {output_path}", LOG__GENERAL)
                
        except Exception as e:
            print_and_log(f"[-] Error generating report: {e}", LOG__GENERAL)
            return 1
    
    elif args.command == "export":
        # Export device data
        import os
        
        if args.address:
            # Export single device
            print_and_log(f"[*] Exporting data for device: {args.address}", LOG__GENERAL)
            device_data = analyzer.load_device_data(args.address)
            
            if not device_data:
                print_and_log(f"[-] No data found for device {args.address}", LOG__GENERAL)
                return 1
                
            output_dir = args.output
            os.makedirs(output_dir, exist_ok=True)
            
            safe_addr = args.address.replace(':', '')
            output_file = os.path.join(output_dir, f"aoi_export_{safe_addr}.json")
            
            with open(output_file, 'w') as f:
                json.dump(device_data, f, indent=2)
                
            print_and_log(f"[+] Device data exported to {output_file}", LOG__GENERAL)
        else:
            # Export all devices
            print_and_log("[*] Exporting data for all devices", LOG__GENERAL)
            devices = analyzer.list_devices()
            
            if not devices:
                print_and_log("[*] No AoI devices found", LOG__GENERAL)
                return 0
                
            output_dir = args.output
            os.makedirs(output_dir, exist_ok=True)
            
            # Use consistent naming pattern to match the test expectations
            output_file = os.path.join(output_dir, f"aoi_export_all_{int(time.time())}.json")
            
            export_data = {}
            for device_address in devices:
                device_data = analyzer.load_device_data(device_address)
                if device_data:
                    export_data[device_address] = device_data
            
            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2)
                
            print_and_log(f"[+] All device data exported to {output_file}", LOG__GENERAL)
    
    else:
        print_and_log("[-] Unknown command. Use --help for usage information.", LOG__GENERAL)
        return 1
        
    return 0


if __name__ == "__main__":  # pragma: no cover
    main() 
