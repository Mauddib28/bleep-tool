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
    scan_parser.add_argument("--timeout", type=int, default=10, help="Scan duration (s)")
    scan_parser.add_argument("--variant", choices=["passive", "naggy", "pokey", "brute"], default="passive", help="Scan variant")
    scan_parser.add_argument("--target", help="Target MAC for pokey mode", default=None)

    # Connect mode
    connect_parser = subparsers.add_parser("connect", help="Connect + GATT enumerate")
    connect_parser.add_argument("address", help="Target MAC address")

    # GATT enumeration (quick / deep)
    gatt_parser = subparsers.add_parser("gatt-enum", help="Connect and enumerate GATT database")
    gatt_parser.add_argument("address", help="Target MAC address")
    gatt_parser.add_argument("--deep", action="store_true", help="Perform deep enumeration (retry reads, descriptor probing)")
    gatt_parser.add_argument("--report", action="store_true", help="Print landmine & security reports instead of raw maps")

    # Enumeration scan variants
    enum_scan = subparsers.add_parser("enum-scan", help="Run enumeration helpers with variant")
    enum_scan.add_argument("address", help="Target MAC address")
    enum_scan.add_argument("--variant", choices=["passive", "naggy", "pokey", "brute"], default="passive")
    enum_scan.add_argument("--rounds", type=int, default=3, help="Rounds for pokey variant")
    enum_scan.add_argument("--write-char", help="Characteristic UUID for brute variant")
    enum_scan.add_argument("--range", help="Hex start-end (e.g. 00-FF) for brute payload range")
    enum_scan.add_argument("--patterns", help="Comma patterns: ascii,inc,alt,repeat:<byte>:<len>,hex:<hex>")
    enum_scan.add_argument("--payload-file", help="Binary payload file path")
    enum_scan.add_argument("--force", action="store_true", help="Ignore landmine/permission map for brute writes")
    enum_scan.add_argument("--verify", action="store_true", help="Read back after each brute write")

    # Media device enumeration
    media_parser = subparsers.add_parser("media-enum", help="Connect and enumerate media device capabilities")
    media_parser.add_argument("address", help="Target MAC address")
    media_parser.add_argument("--verbose", action="store_true", help="Include detailed track and transport information")
    media_parser.add_argument("--monitor", action="store_true", help="Monitor media status changes")
    media_parser.add_argument("--duration", type=int, default=30, help="Duration to monitor in seconds (with --monitor)")
    media_parser.add_argument("--interval", type=int, default=2, help="Polling interval in seconds (with --monitor)")

    # Media control
    media_ctrl = subparsers.add_parser("media-ctrl", help="Control AVRCP playback and volume")
    media_ctrl.add_argument("address", help="Target MAC address")
    media_ctrl.add_argument("action", choices=["play", "pause", "stop", "next", "previous", "volume", "info"], help="Control action")
    media_ctrl.add_argument("--value", type=int, help="Volume value (0-127) when action is 'volume')")

    # Agent mode
    agent_parser = subparsers.add_parser("agent", help="Run pairing agent")
    agent_parser.add_argument("--mode", choices=["simple", "interactive"], default="simple")

    # Explore mode
    explore_parser = subparsers.add_parser("explore", help="Scan & dump GATT db")
    explore_parser.add_argument("mac", help="Target MAC address")
    explore_parser.add_argument("--out", "--dump-json", dest="out", help="Output JSON file (default stdout)")
    explore_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose characteristic list even with handles")

    # DB (observation) commands
    db_parser = subparsers.add_parser("db", help="Query local observation database")
    db_parser.add_argument("action", choices=["list", "show", "export"], help="Action to perform")
    db_parser.add_argument("mac", nargs="?", help="Target MAC for show/export")
    db_parser.add_argument("--out", dest="out", help="Output file for export")

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
    
    # User mode
    user_parser = subparsers.add_parser("user", help="User-friendly interface for Bluetooth exploration")
    user_parser.add_argument("--device", type=str, help="MAC address of device to connect to")
    user_parser.add_argument("--scan", type=int, help="Run a scan for the specified number of seconds before starting")
    user_parser.add_argument("--menu", action="store_true", help="Start in menu mode (default is interactive shell)")

    # Signal configuration mode
    sigconf_parser = subparsers.add_parser("signal-config", help="Manage signal capture configurations")
    sigconf_parser.add_argument("command", nargs="?", help="Sub-command (if omitted, shows help)")
    sigconf_parser.add_argument("args", nargs=argparse.REMAINDER, help="Command arguments")

    # Classic scan
    cscan_parser = subparsers.add_parser("classic-scan", help="Passive Classic (BR/EDR) scan")
    cscan_parser.add_argument("--timeout", type=int, default=10, help="Scan timeout seconds")
    cscan_parser.add_argument(
        "--uuid",
        help="Comma-separated list of UUID filters (e.g. 112f,110b). BlueZ will only report devices advertising at least one of them.",
    )
    cscan_parser.add_argument("--rssi", type=int, help="RSSI threshold: ignore devices weaker than this (dBm)")
    cscan_parser.add_argument("--pathloss", type=int, help="Path-loss threshold in dB (BlueZ >=5.59)")

    # Classic enumerate
    cen_parser = subparsers.add_parser("classic-enum", help="Enumerate Classic RFCOMM services")
    cen_parser.add_argument("address", help="Target MAC address")
    # Phonebook dump
    pbap_parser = subparsers.add_parser(
        "classic-pbap",
        help="Download phone-book via PBAP (RFCOMM) and save to VCF",
    )
    pbap_parser.add_argument("address", help="Target MAC address")
    pbap_parser.add_argument("--out", help="Output VCF path (single PB repo only)", default=None)
    pbap_parser.add_argument("--repos", help="Comma-separated repo list (PB,ICH,…) or ALL", default="PB")
    pbap_parser.add_argument("--format", choices=["vcard21", "vcard30"], default="vcard21", help="vCard format")
    pbap_parser.add_argument("--auto-auth", action="store_true", help="Register temporary OBEX agent that auto-accepts authentication/prompts")
    pbap_parser.add_argument("--watchdog", type=int, default=8, help="Watchdog seconds before aborting stalled transfer (0 to disable)")

    # Classic ping
    cping_parser = subparsers.add_parser("classic-ping", help="L2CAP echo (l2ping) reachability test")
    cping_parser.add_argument("address", help="Target MAC address")
    cping_parser.add_argument("--count", type=int, default=3, help="Echo count")
    cping_parser.add_argument("--timeout", type=int, default=13, help="Seconds before aborting l2ping command")

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
            from bleep.ble_ops import scan as _scan_mod

            variant = args.variant.lower()
            timeout = args.timeout
            target = args.target

            if variant == "pokey" and not target:
                print("[ERROR] --target <MAC> required for pokey scan variant", file=sys.stderr)
                return 1

            dispatch = {
                "passive": lambda: _scan_mod.passive_scan(target, timeout),
                "naggy": lambda: _scan_mod.naggy_scan(target, timeout),
                "pokey": lambda: _scan_mod.pokey_scan(target, timeout=timeout),
                "brute": lambda: _scan_mod.brute_scan(timeout),
            }

            dispatch[variant]()
            return 0

        elif args.mode == "enum-scan":
            from bleep.ble_ops import scan as _scan_mod

            var = args.variant.lower()
            if var == "passive":
                res = _scan_mod.passive_enum(args.address)
            elif var == "naggy":
                res = _scan_mod.naggy_enum(args.address)
            elif var == "pokey":
                res = _scan_mod.pokey_enum(args.address, rounds=args.rounds)
            elif var == "brute":
                if not args.write_char:
                    print("[!] --write-char required for brute enumeration", file=sys.stderr)
                    return 1
                vr = None
                if args.range:
                    try:
                        start_hex, end_hex = args.range.split("-")
                        vr = (int(start_hex, 16), int(end_hex, 16))
                    except ValueError:
                        print("[!] Invalid --range format, expected AA-BB", file=sys.stderr)
                        return 1

                patterns = [p.strip() for p in args.patterns.split(",") if p.strip()] if args.patterns else None

                file_bytes = None
                if args.payload_file:
                    try:
                        with open(args.payload_file, "rb") as f:
                            file_bytes = f.read()
                    except Exception as exc:
                        print(f"[!] Failed to read payload file: {exc}", file=sys.stderr)
                        return 1

                res = _scan_mod.brute_enum(
                    args.address,
                    write_char=args.write_char,
                    value_range=vr,
                    patterns=patterns,
                    payload_file=file_bytes,
                    force=args.force,
                    verify=args.verify,
                )
            print(res)
            return 0

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
                    # Get basic player properties; TODO: Expand TO ALL 
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
                    transport_info = {          # TODO: Expand TO ALL
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

        elif args.mode == "media-ctrl":
            from bleep.modes.media import control_media_device as _ctrl
            success = _ctrl(args.address, args.action, args.value)
            return 0 if success else 1

        elif args.mode == "db":
            from bleep.modes import db as _db_mode
            subargv = [args.action]
            if args.mac:
                subargv.append(args.mac)
            if args.out:
                subargv += ["--out", args.out]
            return _db_mode.main(subargv)

        elif args.mode == "agent":
            from bleep.modes.agent import main as _agent_main

            return _agent_main(["--mode", args.mode]) or 0
            
        elif args.mode == "user":
            from bleep.modes.user import main as _user_main
            
            opts = []
            if args.device:
                opts += ["--device", args.device]
            if args.scan:
                opts += ["--scan", str(args.scan)]
            if args.menu:
                opts.append("--menu")
                
            return _user_main(opts) or 0

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
            
        elif args.mode == "signal-config":
            from bleep.signals.cli import main as _sigconf_main
            
            # If no command provided, show help
            if not args.command:
                return _sigconf_main(["--help"])
            
            # Pass the command and args
            opts = [args.command] + args.args
            return _sigconf_main(opts) or 0

        elif args.mode == "classic-scan":
            # Use the adapter directly to avoid pulling in BLE-specific
            # device-manager wrappers (which cause a circular import during
            # classic-only operations).
            from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
            from bleep.core.log import print_and_log, LOG__DEBUG
            import dbus

            adapter = _Adapter()
            if not adapter.is_ready():
                print("[!] Bluetooth adapter not ready", file=sys.stderr)
                return 1

            # Build discovery filter dict
            _f = {"Transport": "bredr"}
            if getattr(args, "uuid", None):
                uuids = [u.strip().lower() for u in args.uuid.split(",") if u.strip()]
                if uuids:
                    _f["UUIDs"] = dbus.Array(uuids, signature="s")  # type: ignore[name-defined]
            if args.rssi is not None:
                _f["RSSI"] = dbus.Int16(args.rssi)  # type: ignore[name-defined]
            if args.pathloss is not None:
                _f["Pathloss"] = dbus.UInt16(args.pathloss)  # type: ignore[name-defined]

            try:
                adapter.set_discovery_filter(_f)
                print_and_log("[classic-scan] Applied discovery filter: " + str(_f), LOG__DEBUG)
            except Exception as exc:
                # Older BlueZ versions may lack SetDiscoveryFilter – continue but log.
                print_and_log(
                    f"[classic-scan] SetDiscoveryFilter failed ({exc.__class__.__name__}: {exc}); proceeding without filter",
                    LOG__DEBUG,
                )

            # Timed discovery using the adapter's built-in helper.
            adapter.run_scan__timed(duration=args.timeout)

            devices = [d for d in adapter.get_discovered_devices() if d["type"].lower() == "br/edr"]

            if not devices:
                print("No Classic devices found")
            else:
                for d in devices:
                    name = d["name"] or d["alias"] or "(unknown)"
                    rssi = d.get("rssi")
                    rssi_str = f"RSSI={rssi}" if rssi is not None else "RSSI=?"
                    print(f"{d['address']}  Name={name}  {rssi_str}")
            return 0

        elif args.mode == "classic-enum":
            from bleep.ble_ops import connect_and_enumerate__bluetooth__classic as _c_enum
            try:
                _, svc_map = _c_enum(args.address)
                import json
                print(json.dumps(svc_map, indent=2))
                return 0
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

        elif args.mode == "classic-pbap":
            repos_arg = (args.repos or "PB").upper()
            from bleep.ble_ops.classic_pbap import pbap_dump_async, DEFAULT_PBAP_REPOS
            repos = DEFAULT_PBAP_REPOS if repos_arg == "ALL" else tuple(r.strip().upper() for r in repos_arg.split(",") if r.strip())

            try:
                result = pbap_dump_async(
                    args.address,
                    repos=repos,
                    vcard_format=args.format,
                    auto_auth=args.auto_auth,
                    watchdog=args.watchdog,
                )
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

            base = args.address.replace(":", "").lower()
            single_custom_out = args.out and len(repos) == 1

            for repo, lines in result["data"].items():
                if single_custom_out:
                    path = args.out
                else:
                    path = f"/tmp/{base}_{repo}.vcf"
                try:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.writelines(lines)
                    print(f"[+] Saved {repo} → {path} ({len(lines)} lines)")
                except Exception as exc:
                    print(f"[!] Failed to write {path}: {exc}", file=sys.stderr)
            return 0

        elif args.mode == "classic-ping":
            from bleep.ble_ops.classic_ping import classic_l2ping

            rtt, err = classic_l2ping(args.address, count=args.count, timeout=args.timeout)
            if rtt is None:
                print(f"[!] l2ping failed – {err}", file=sys.stderr)
                return 1
            print(f"Average RTT {rtt:.1f} ms")
            return 0

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
