#!/usr/bin/env python3
"""
Check Local BlueZ Network Capabilities

Thin CLI wrapper around the shared PAN enumeration ops
(``bleep.ble_ops.classic.pan.find_network_servers`` /
``find_network_devices``). It reports:

1. NetworkServer1 (PAN NAP/GN hosting) availability per adapter
2. Network1 interface presence and PAN role UUIDs per device
3. Live Network1 status for connected devices (``--verbose``)

Usage:
    python3 check_network_capabilities.py [--adapter hci0] [--verbose] [--json]

The enumeration itself lives in the BLEEP ops layer so that the CLI
``network-enum`` command, the device-class helpers, and this script all share a
single implementation (one ``GetManagedObjects`` fetch, no duplicated D-Bus or
UUID-matching logic).
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check local BlueZ network (PAN) capabilities"
    )
    parser.add_argument("--adapter", "-i", help="Adapter to check (e.g. hci0)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show live Network1 status for capable devices")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    try:
        from bleep.ble_ops.classic.pan import (
            find_network_servers,
            find_network_devices,
        )
    except Exception as exc:  # pragma: no cover - import/environment guard
        print(f"[-] Error importing BLEEP PAN ops: {exc}", file=sys.stderr)
        return 1

    adapters = find_network_servers(adapter=args.adapter)
    devices = find_network_devices(adapter=args.adapter)

    if args.json:
        import json
        print(json.dumps({
            "adapters": adapters,
            "network_capable_devices": devices,
        }, indent=2))
        return 0

    print("=" * 70)
    print("BlueZ Network Capabilities Check")
    print("=" * 70)

    print("\n[+] Adapters:")
    if not adapters:
        print("  No adapters found")
    for adapter in adapters:
        print(f"\n  Adapter: {adapter['name']} ({adapter['address']})")
        print(f"    Path: {adapter['path']}")
        print(f"    Powered: {adapter['powered']}")
        print(f"    NetworkServer Support: {'✓' if adapter['has_networkserver'] else '✗'}")
        if adapter["network_uuids"]:
            print(f"    Network UUIDs: {', '.join(adapter['network_uuids'])}")

    print("\n[+] Network-Capable Devices:")
    if not devices:
        print("  No devices with network capabilities found")
    else:
        print(f"  Found {len(devices)} device(s) with network capabilities:\n")
        for device in devices:
            print(f"  Device: {device['name']} ({device['address']})")
            print(f"    Network Interface: {'✓' if device['has_network_interface'] else '✗'}")
            if device["network_uuids"]:
                print(f"    Network Roles: {', '.join(device['network_uuids'])}")
            status = device.get("network_status")
            if args.verbose and status:
                print("    Network Status:")
                print(f"      Connected: {status.get('connected', False)}")
                if status.get("interface"):
                    print(f"      Interface: {status['interface']}")
                if status.get("uuid"):
                    print(f"      Role: {status['uuid']}")
            print()

    adapters_with_server = sum(1 for a in adapters if a["has_networkserver"])
    print("=" * 70)
    print("Summary:")
    print(f"  Adapters checked: {len(adapters)}")
    print(f"  Adapters with NetworkServer: {adapters_with_server}")
    print(f"  Network-capable devices: {len(devices)}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
