from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bleep.core import observations as _obs


def _conn():
    # Access private connection for read-only ops
    return _obs._DB_CONN  # type: ignore[attr-defined]


def _valid_cols() -> list[str]:
    with _obs._db_cursor() as cur:  # type: ignore[attr-defined]
        return [c[1] for c in cur.execute("PRAGMA table_info(devices)")]


def list_devices(fields: list[str] | None = None, status: str | None = None) -> None:
    """List devices with optional field and status filters."""
    try:
        # Get devices with optional status filter
        devices = _obs.get_devices(status=status)
        
        # If no devices found
        if not devices:
            if status:
                print(f"No devices found matching status filter: {status}")
            else:
                print("No devices found in database")
            return
            
        # Filter fields if specified
        cols = fields or ["mac", "name", "first_seen", "last_seen"]
        valid = set(_valid_cols())
        bad = [c for c in cols if c not in valid]
        if bad:
            print(f"Invalid field(s): {', '.join(bad)} – valid: {', '.join(sorted(valid))}")
            return
            
        # Print header
        print("  ".join(c.upper() for c in cols))
        print("  ".join("-" * len(c) for c in cols))
        
        # Print devices
        for device in devices:
            print("  ".join(str(device.get(c, "-")) if device.get(c) is not None else "-" for c in cols))
    except Exception as e:
        print(f"Error listing devices: {e}")


def timeline(mac: str, service_uuid: str = None, char_uuid: str = None, limit: int = 50):
    """Display characteristic value timeline for a device."""
    try:
        # Get characteristic history with optional filters
        history = _obs.get_characteristic_timeline(mac, service_uuid, char_uuid, limit)
        
        if not history:
            print(f"No characteristic history found for device {mac}")
            if service_uuid or char_uuid:
                filters = []
                if service_uuid:
                    filters.append(f"service_uuid={service_uuid}")
                if char_uuid:
                    filters.append(f"char_uuid={char_uuid}")
                print(f"Filters applied: {', '.join(filters)}")
            return
            
        # Print header
        print(f"Characteristic value history for {mac}:")
        if service_uuid:
            print(f"Service UUID filter: {service_uuid}")
        if char_uuid:
            print(f"Characteristic UUID filter: {char_uuid}")
            
        print(f"{'TIMESTAMP':<25} {'SERVICE UUID':<36} {'CHAR UUID':<36} {'VALUE'}")
        print("-" * 100)
        
        # Print timeline entries
        for entry in history:
            val = entry.get("value")
            if isinstance(val, bytes):
                val = val.hex()
            print(f"{entry['ts']:<25}  {entry['service_uuid']:<36} {entry['char_uuid']:<36}  {val}")
            
        # Show total count
        print(f"\nShowing {len(history)} entries (limit: {limit})")
    except Exception as e:
        print(f"Error retrieving timeline data: {e}")


def show_device(mac: str) -> None:
    """Show detailed information about a device."""
    try:
        # Get device details
        device_info = _obs.get_device_detail(mac)
        
        if not device_info.get('device'):
            print(f"Device {mac} not found in database")
            return
            
        # Prepare output
        output = {
            **device_info['device'],
            'services': [],
            'characteristics_count': len(device_info['characteristics']),
            'classic_services_count': len(device_info['classic_services']),
        }
        
        # Add services summary
        for service in device_info['services']:
            output['services'].append({
                'uuid': service['uuid'],
                'name': service['name']
            })
            
        # Print formatted JSON
        print(json.dumps(output, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error retrieving device details: {e}")


def export_device(mac: str, out: Path | None) -> None:
    """Export all data for a device to JSON."""
    try:
        # Get complete device data
        data = _obs.export_device_data(mac)
        
        if not data.get('device'):
            print(f"Device {mac} not found in database")
            return
            
        # Format as JSON
        text = json.dumps(data, indent=2, ensure_ascii=False)
        
        # Write to file or stdout
        if out:
            out.write_text(text, encoding="utf-8")
            print(f"Exported device data to {out}")
        else:
            print(text)
    except Exception as e:
        print(f"Error exporting device data: {e}")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser("bleep db", description="BLEEP observation DB utilities")
    sub = p.add_subparsers(dest="cmd")

    list_p = sub.add_parser("list", help="List devices in DB")
    list_p.add_argument("--fields", help="Comma-separated list of device fields to print", default=None)
    list_p.add_argument("--status", help="Filter devices by status: recent,ble,classic,media (comma-separated)", default=None)
    
    show_p = sub.add_parser("show", help="Show single device as JSON")
    show_p.add_argument("mac", help="Device MAC address")
    
    exp_p = sub.add_parser("export", help="Export full device record to JSON file")
    exp_p.add_argument("mac", help="Device MAC address")
    exp_p.add_argument("--out", type=Path, help="Output file path (default: stdout)")
    
    tl_p = sub.add_parser("timeline", help="Show chronological characteristic history")
    tl_p.add_argument("mac", help="Device MAC address")
    tl_p.add_argument("--service", help="Filter by service UUID")
    tl_p.add_argument("--char", help="Filter by characteristic UUID")
    tl_p.add_argument("--limit", type=int, default=50, help="Maximum entries to show (default: 50)")

    args = p.parse_args(argv)
    if args.cmd == "list":
        fields = args.fields.split(',') if args.fields else None
        list_devices(fields, args.status); return 0
        
    if args.cmd == "show":
        show_device(args.mac); return 0
        
    if args.cmd == "export":
        export_device(args.mac, args.out); return 0
        
    if args.cmd == "timeline":
        timeline(args.mac, args.service, args.char, args.limit); return 0
        
    p.print_help(); return 1
