"""
Command-line interface for BLEEP.
"""

import argparse
import sys
import os

# Ensure logging subsystem (and legacy /tmp files) is initialised immediately
import bleep.core.log  # noqa: F401  # side-effect import creates symlinks/files

from . import __version__


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="BLEEP - Bluetooth Landscape Exploration & Enumeration Platform"
    )
    parser.add_argument("--version", action="version", version=f"BLEEP {__version__}")

    # Add subparsers for different modes
    subparsers = parser.add_subparsers(dest="mode", help="Operation mode")

    # Interactive mode (default)
    subparsers.add_parser("interactive", help="Interactive REPL console")

    # Scan mode
    scan_parser = subparsers.add_parser("scan", help="Passive BLE scan")
    scan_parser.add_argument("-d", "--device", help="Target MAC address to filter")
    scan_parser.add_argument("--timeout", type=int, default=10, help="Scan timeout")

    # Connect mode
    connect_parser = subparsers.add_parser("connect", help="Connect + GATT enumerate")
    connect_parser.add_argument("address", help="Target MAC address")

    # GATT enumeration (quick / deep)
    gatt_parser = subparsers.add_parser("gatt-enum", help="Connect and enumerate GATT database")
    gatt_parser.add_argument("address", help="Target MAC address")
    gatt_parser.add_argument("--deep", action="store_true", help="Perform deep enumeration (retry reads, descriptor probing)")
    gatt_parser.add_argument("--report", action="store_true", help="Print landmine & security reports instead of raw maps")

    # Media device enumeration
    media_parser = subparsers.add_parser("media-enum", help="Connect and enumerate media device capabilities")
    media_parser.add_argument("address", help="Target MAC address")
    media_parser.add_argument("--verbose", action="store_true", help="Include detailed track and transport information")
    media_parser.add_argument("--monitor", action="store_true", help="Monitor media status changes")
    media_parser.add_argument("--duration", type=int, default=30, help="Duration to monitor in seconds (with --monitor)")
    media_parser.add_argument("--interval", type=int, default=2, help="Polling interval in seconds (with --monitor)")

    # Agent mode
    agent_parser = subparsers.add_parser("agent", help="Run pairing agent")
    agent_parser.add_argument("--mode", choices=["simple", "interactive"], default="simple")

    # Explore mode
    explore_parser = subparsers.add_parser("explore", help="Scan & dump GATT db")
    explore_parser.add_argument("mac", help="Target MAC address")
    explore_parser.add_argument("--out", "--dump-json", dest="out", help="Output JSON file (default stdout)")
    explore_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose characteristic list even with handles")

    # Analysis mode
    analysis_parser = subparsers.add_parser("analyse", help="Post-process JSON dumps")
    analysis_parser.add_argument("files", nargs="+", help="JSON dump files to analyse")

    # AoI mode
    aoi_parser = subparsers.add_parser("aoi", help="Process Assets-of-Interest JSON list")
    aoi_parser.add_argument("files", nargs="+", help="AoI JSON files")
    aoi_parser.add_argument("--delay", type=float, default=4.0, help="Delay between devices")

    # Signal mode
    sig_parser = subparsers.add_parser("signal", help="Listen for notifications")
    sig_parser.add_argument("mac", help="Target MAC address")
    sig_parser.add_argument("char", help="Characteristic UUID or char handle")
    sig_parser.add_argument("--time", type=int, default=30, help="Listen duration seconds")

    return parser.parse_args(args)


def main(args=None):
    """Main entry point for BLEEP."""
    args = parse_args(args)

    # Optional: honour BLEEP_LOG_LEVEL env var so users can tweak verbosity
    import logging as _logging, os as _os

    _lvl = _os.getenv("BLEEP_LOG_LEVEL")
    if _lvl:
        _logging.getLogger("bleep").setLevel(_lvl.upper())

    try:
        if args.mode == "scan":
            try:
                from bleep.ble_ops.scan import passive_scan

                sys.exit(passive_scan(args.device, args.timeout))
            except FileNotFoundError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        elif args.mode == "connect":
            # Native path first – falls back to monolith only on explicit failure
            try:
                from bleep.ble_ops.connect import (
                    connect_and_enumerate__bluetooth__low_energy as _connect_enum,
                )

                _connect_enum(args.address)
                return 0
            except Exception as exc:  # noqa: BLE001 – any native failure triggers fallback
                print(
                    f"[!] Native connect failed ({exc}); attempting legacy monolith fallback…",
                    file=sys.stderr,
                )
                try:
                    from bleep.ble_ops.scan import _load_monolith  # reuse loader

                    mono = _load_monolith()
                    mono.connect_and_enumerate__bluetooth__low_energy(args.address)
                    return 0
                except Exception as e:  # noqa: BLE001
                    print(f"Legacy fallback also failed: {e}", file=sys.stderr)
                return 1

        elif args.mode == "gatt-enum":
            from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum

            device, mapping, mine_map, perm_map = _connect_enum(
                args.address,
                deep_enumeration=args.deep,
            )
            import json

            def _dump(obj):
                """Return a JSON-formatted string with sane defaults."""
                def _compact(o):
                    """Recursively convert long integer lists to a single-line string list."""
                    if isinstance(o, list):
                        # If list consists solely of byte-sized ints, render on one line for readability
                        if o and all(isinstance(x, int) and 0 <= x < 256 for x in o):
                            return "[" + ", ".join(str(x) for x in o) + "]"
                        return [_compact(v) for v in o]
                    elif isinstance(o, dict):
                        return {k: _compact(v) for k, v in o.items()}
                    return o

                compact_obj = _compact(obj)
                return json.dumps(compact_obj, indent=2, ensure_ascii=False, sort_keys=False)

            if args.report:
                print(
                    _dump(
                        {
                            "landmine_report": device.get_landmine_report(),
                            "security_report": device.get_security_report(),
                        }
                    )
                )
            else:
                print(
                    _dump(
                        {
                            "mapping": mapping,
                            "mine_map": mine_map,
                            "permission_map": perm_map,
                        }
                    )
                )
            return 0
            
        elif args.mode == "media-enum":
            from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
            from bleep.dbuslayer.media import get_player_properties_verbose, pretty_print_track_info
            import json
            import time
            
            # Connect to the device
            print(f"[*] Attempting connection to {args.address}")
            device, _, _, _ = _connect_enum(args.address)
            print(f"[+] Connected to {args.address}")
            
            # Check if it's a media device
            if not device.is_media_device():
                print(f"[!] {args.address} is not a media device")
                return 1
                
            def _dump(obj):
                """Return a JSON-formatted string with sane defaults."""
                def _compact(o):
                    """Recursively convert long integer lists to a single-line string list."""
                    if isinstance(o, list):
                        # If list consists solely of byte-sized ints, render on one line for readability
                        if o and all(isinstance(x, int) and 0 <= x < 256 for x in o):
                            return "[" + ", ".join(str(x) for x in o) + "]"
                        return [_compact(v) for v in o]
                    elif isinstance(o, dict):
                        return {k: _compact(v) for k, v in o.items()}
                    return o

                compact_obj = _compact(obj)
                return json.dumps(compact_obj, indent=2, ensure_ascii=False, sort_keys=False)
                
            # Collect media device information
            media_info = {
                "device_info": {
                    "address": device.get_address(),
                    "name": device.get_name() or device.get_alias() or "Unknown",
                    "is_connected": device.is_connected(),
                },
                "media_capabilities": {
                    "has_media_control": device.get_media_control() is not None,
                    "has_media_player": device.get_media_player() is not None,
                    "has_media_endpoints": len(device.get_media_endpoints()) > 0,
                    "has_media_transports": len(device.get_media_transports()) > 0,
                }
            }
            
            # Get media player details if available
            player = device.get_media_player()
            if player:
                if args.verbose:
                    # Get detailed player properties including track info
                    media_info["player"] = get_player_properties_verbose(player)
                else:
                    # Get basic player properties
                    media_info["player"] = {
                        "name": player.get_name(),
                        "status": player.get_status(),
                        "track": player.get_track()
                    }
            
            # Get media transport details if available
            transports = device.get_media_transports()
            if transports:
                media_info["transports"] = []
                for transport in transports:
                    transport_info = {
                        "path": transport.transport_path,
                        "state": transport.get_state(),
                        "volume": transport.get_volume()
                    }
                    
                    if args.verbose:
                        # Add all transport properties
                        transport_info["properties"] = transport.get_properties()
                        
                    media_info["transports"].append(transport_info)
            
            # Get media endpoints if available
            endpoints = device.get_media_endpoints()
            if endpoints:
                media_info["endpoints"] = []
                for endpoint in endpoints:
                    endpoint_info = {
                        "path": endpoint.endpoint_path,
                        "uuid": endpoint.get_uuid(),
                        "codec": endpoint.get_codec()
                    }
                    
                    if args.verbose:
                        # Add all endpoint properties
                        endpoint_info["properties"] = endpoint.get_properties()
                        
                    media_info["endpoints"].append(endpoint_info)
            
            # Monitor mode - poll for changes in media status
            if args.monitor:
                print(f"[*] Monitoring media status for {args.duration} seconds (Ctrl+C to stop)...")
                end_time = time.time() + args.duration
                
                try:
                    while time.time() < end_time:
                        if player:
                            status = player.get_status()
                            track = player.get_track()
                            
                            print(f"\r[*] Status: {status} | Track: {pretty_print_track_info(track)}", end="")
                            sys.stdout.flush()
                        
                        time.sleep(args.interval)
                    print("\n[+] Monitoring complete")
                except KeyboardInterrupt:
                    print("\n[*] Monitoring stopped by user")
            else:
                # Print the media device information as JSON
                print(_dump(media_info))
                
            return 0

        elif args.mode == "agent":
            from bleep.modes.agent import main as _agent_main

            return _agent_main(["--mode", args.mode]) or 0

        elif args.mode == "explore":
            from bleep.modes.exploration import main as _exp_main

            opts = ["--target", args.mac]
            if args.out:
                opts += ["--out", args.out]
            if args.verbose:
                opts.append("--verbose")
            return _exp_main(opts) or 0

        elif args.mode == "analyse":
            from bleep.modes.analysis import main as _an_main

            return _an_main(args.files) or 0

        elif args.mode == "aoi":
            from bleep.modes.aoi import main as _aoi_main

            opts = args.files + ["--delay", str(args.delay)]
            return _aoi_main(opts) or 0

        elif args.mode == "signal":
            from bleep.modes.signal import main as _sig_main

            opts = [args.mac, args.char, "--time", str(args.time)]
            return _sig_main(opts) or 0

        else:  # interactive (default)
            from bleep.modes.interactive import main as _interactive_main

            return _interactive_main() or 0

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
