"""BLEEP Assets-of-Interest (AoI) mode – iterate over lists of target MACs and analyze them.

This mode provides functionality to:
1. Scan multiple devices from JSON files containing MAC addresses
2. Classify device transport type (classic / le / dual / unknown)
3. Perform SDP enumeration for Classic/Dual targets
4. Probe pairing profile and (optionally) deep re-enumerate post-pair
5. Analyze device data for security concerns and unusual characteristics
6. Generate security reports in various formats (markdown, JSON, text)
7. Store device data for offline analysis (file + database)
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from bleep.analysis.aoi_analyser import AOIAnalyser, BytesEncoder
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
from bleep.ble_ops.le.enum_controller import EnumerationController
from bleep.bt_ref.utils import get_name_from_uuid

logger = logging.getLogger(__name__)

_DEF_WAIT = 4.0  # seconds between targets
_MAC_RE = re.compile(
    r'^[0-9A-Fa-f]{2}([:\-])[0-9A-Fa-f]{2}(?:\1[0-9A-Fa-f]{2}){4}$'
)


def _prepare_for_json(obj: Any) -> Any:
    """Convert non-serializable types (bytes, tuples) for JSON output."""
    if isinstance(obj, bytes):
        return obj.hex()
    elif isinstance(obj, dict):
        return {k: _prepare_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_prepare_for_json(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_prepare_for_json(item) for item in obj)
    return obj


def _validate_mac(mac: str) -> Optional[str]:
    """Return normalised ``AA:BB:CC:DD:EE:FF`` or *None* on invalid input."""
    if not mac or not isinstance(mac, str):
        return None
    stripped = mac.strip().upper().replace("-", ":")
    if _MAC_RE.match(stripped):
        return stripped
    return None


def _normalise_service_element(elem: Any) -> str:
    """Extract a UUID string from either a plain string or a ``{"uuid": …}`` dict."""
    if isinstance(elem, dict):
        return str(elem.get("uuid", elem.get("UUID", "")))
    return str(elem)


# ---------------------------------------------------------------------------
# Device classification helper
# ---------------------------------------------------------------------------

def _classify_device(mac: str, context: Optional[Dict[str, Any]] = None,
                     use_db: bool = True) -> str:
    """Return device type string: ``classic``, ``le``, ``dual``, or ``unknown``."""
    try:
        from bleep.analysis.device_type_classifier import DeviceTypeClassifier
        classifier = DeviceTypeClassifier()
        result = classifier.classify_with_mode(
            mac, context or {}, scan_mode="passive", use_database_cache=use_db,
        )
        return result.device_type if result else "unknown"
    except Exception as exc:
        logger.debug("classification failed for %s: %s", mac, exc)
        return "unknown"


# ---------------------------------------------------------------------------
# SDP discovery helper
# ---------------------------------------------------------------------------

def _discover_sdp(mac: str, *, connectionless: bool = False,
                  timeout: int = 30, use_db: bool = True) -> List[Dict[str, Any]]:
    """Run SDP discovery; returns a list of SDP records (may be empty)."""
    try:
        from bleep.ble_ops.classic.sdp import discover_services_sdp
        from bleep.core import observations as obs
        records = discover_services_sdp(
            mac, timeout=timeout, connectionless=connectionless,
        )
        if records and use_db:
            try:
                obs.upsert_classic_services(
                    mac,
                    [{"uuid": r.get("service_id", r.get("uuid", "")),
                      "channel": r.get("channel"),
                      "name": r.get("name", "")}
                     for r in records],
                )
            except Exception as db_exc:
                logger.debug("SDP DB store failed: %s", db_exc)
        return records
    except Exception as exc:
        print_and_log(f"[-] SDP discovery failed for {mac}: {exc}", LOG__DEBUG)
        return []


# ---------------------------------------------------------------------------
# Pairing probe helpers
# ---------------------------------------------------------------------------

def _probe_pairing(mac: str, timeout: int = 15) -> Dict[str, Any]:
    """Attempt a JustWorks pair probe; returns a pairing-profile dict."""
    profile: Dict[str, Any] = {"attempted": False, "paired": False, "method": None, "error": None}
    try:
        from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic
        dev = system_dbus__bluez_device__classic(mac)
        profile["attempted"] = True
        ok = dev.pair(timeout=timeout)
        profile["paired"] = ok
        profile["method"] = "JustWorks"
    except Exception as exc:
        profile["error"] = str(exc)
    return profile


def _perform_deep_reenumeration(mac: str, device_type: str, *,
                                timeout: int = 30,
                                use_db: bool = True) -> Dict[str, Any]:
    """Post-pair re-enumerate to capture delta (deep mode only)."""
    delta: Dict[str, Any] = {"le_delta": None, "sdp_delta": None}
    if device_type in ("le", "dual"):
        try:
            ctrl = EnumerationController(mac)
            result = ctrl.enumerate(mode="passive")
            if result.success and result.device:
                delta["le_delta"] = {
                    "services": (result.device.get_services()
                                 if hasattr(result.device, "get_services") else []),
                    "data": result.data,
                }
        except Exception as exc:
            logger.debug("deep LE re-enum failed: %s", exc)
    if device_type in ("classic", "dual"):
        try:
            sdp = _discover_sdp(mac, timeout=timeout, use_db=use_db)
            delta["sdp_delta"] = sdp
        except Exception as exc:
            logger.debug("deep SDP re-enum failed: %s", exc)
    return delta


def _has_auth_annotation(annotations: list) -> bool:
    """Return True if any annotation mentions authentication/pairing."""
    for a in annotations:
        details = getattr(a, "details", "") or ""
        if any(kw in details.lower() for kw in ("auth", "pair", "encrypt", "insufficient")):
            return True
    return False


# ---------------------------------------------------------------------------
# MAC iterator
# ---------------------------------------------------------------------------

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
        if "address" in obj:
            macs.append(obj["address"])
        for val in obj.values():
            macs.extend(_iter_macs(val))
        return macs
    return []


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bleep-aoi", add_help=False)
    subparsers = p.add_subparsers(dest="command", help="AOI command to execute")

    # --- scan ---
    scan_parser = subparsers.add_parser("scan", help="Scan and enumerate devices from AoI files")
    scan_parser.add_argument("files", nargs="+", metavar="FILE",
                             help="JSON files containing AoI device lists")
    scan_parser.add_argument("--delay", type=float, default=_DEF_WAIT,
                             help="Seconds to wait between devices")
    scan_parser.add_argument("--deep", action="store_true",
                             help="Enable deep mode (pairing + post-pair re-enum)")
    scan_parser.add_argument("--timeout", type=int, default=30,
                             help="Per-device timeout in seconds")
    scan_parser.add_argument("--db-only", action="store_true",
                             help="Use only database for storage (no files)")
    scan_parser.add_argument("--no-db", action="store_true",
                             help="Don't use database for storage")
    scan_parser.add_argument("--connectionless", action="store_true",
                             help="Use connectionless SDP (l2ping + sdptool)")
    scan_parser.add_argument("--address", "-a",
                             help="Scan only this MAC from the list")

    # --- analyze ---
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a specific device")
    analyze_parser.add_argument("--address", "-a", required=True,
                                help="MAC address of the device to analyze")
    analyze_parser.add_argument("--deep", action="store_true",
                                help="Invoke SDP + pairing probe during analysis")
    analyze_parser.add_argument("--timeout", type=int, default=30,
                                help="Analysis timeout in seconds")
    analyze_parser.add_argument("--db-only", action="store_true",
                                help="Use only database for storage (no files)")
    analyze_parser.add_argument("--no-db", action="store_true",
                                help="Don't use database for storage/retrieval")

    # --- list ---
    list_parser = subparsers.add_parser("list", help="List all saved AoI devices")
    list_parser.add_argument("--no-db", action="store_true",
                             help="Don't use database for listing devices")

    # --- report ---
    report_parser = subparsers.add_parser("report", help="Generate a report for a device")
    report_parser.add_argument("--address", "-a", required=True,
                               help="MAC address of the device")
    report_parser.add_argument("--format", "-f", choices=["markdown", "json", "text"],
                               default="markdown", help="Report format")
    report_parser.add_argument("--output", "-o", help="Output file (defaults to auto-generated)")
    report_parser.add_argument("--no-db", action="store_true",
                               help="Don't use database for retrieval")

    # --- export ---
    export_parser = subparsers.add_parser("export", help="Export device data")
    export_parser.add_argument("--address", "-a",
                               help="MAC address to export (omit for all devices)")
    export_parser.add_argument("--output", "-o", default=".", help="Output directory")
    export_parser.add_argument("--no-db", action="store_true",
                               help="Don't use database for retrieval")

    # --- db ---
    db_parser = subparsers.add_parser("db", help="Database operations")
    db_parser.add_argument("action", choices=["import", "export", "sync", "list"],
                           help="Database action")
    db_parser.add_argument("--address", "-a",
                           help="MAC address for operation (omit for all)")

    p.add_argument("--help", "-h", action="help")
    return p


# ---------------------------------------------------------------------------
# Scan-target pipeline
# ---------------------------------------------------------------------------

def _scan_target(mac: str, analyzer: AOIAnalyser, *,
                 deep: bool = False, timeout: int = 30,
                 use_db: bool = True, connectionless: bool = False) -> None:
    """Full AoI scan pipeline for a single target MAC."""
    normalized = _validate_mac(mac)
    if not normalized:
        print_and_log(f"[-] Invalid MAC, skipping: {mac}", LOG__GENERAL)
        return

    print_and_log(f"[*] AoI target: {normalized}", LOG__GENERAL)

    # 1. Classify device type
    device_type = _classify_device(normalized, use_db=use_db)
    print_and_log(f"    type={device_type}", LOG__GENERAL)

    # 2. LE/Dual: GATT enumeration
    le_result = None
    device_data: Dict[str, Any] = {
        "address": normalized,
        "device_type": device_type,
        "scan_timestamp": time.time(),
    }

    if device_type in ("le", "dual", "unknown"):
        try:
            controller = EnumerationController(normalized)
            le_result = controller.enumerate(mode="passive")
            if le_result.success and le_result.device:
                dev = le_result.device
                device_data.update({
                    "name": (getattr(dev, "get_name", lambda: None)()
                             or getattr(dev, "name", "Unknown")),
                    "services": dev.get_services() if hasattr(dev, "get_services") else [],
                    "services_mapping": le_result.data or {},
                    "landmine_map": le_result.landmine_map or {},
                    "permission_map": le_result.permission_map or {},
                    "enumeration_annotations": [
                        {"timestamp": a.timestamp, "error_type": a.error_type,
                         "details": a.details, "attempted_solution": a.attempted_solution}
                        for a in le_result.annotations
                    ],
                })
            else:
                print_and_log(f"[-] LE enum failed for {normalized}", LOG__GENERAL)
                if le_result.error_summary:
                    print_and_log(f"    {le_result.error_summary}", LOG__GENERAL)
        except Exception as exc:
            print_and_log(f"[-] LE enum error: {exc}", LOG__GENERAL)

    # 3. Classic/Dual: SDP discovery
    sdp_records: List[Dict[str, Any]] = []
    if device_type in ("classic", "dual", "unknown"):
        sdp_records = _discover_sdp(
            normalized, connectionless=connectionless,
            timeout=timeout, use_db=use_db,
        )
        if sdp_records:
            device_data["sdp_summary"] = sdp_records
            print_and_log(f"    SDP: {len(sdp_records)} record(s)", LOG__GENERAL)

    # 4. Pairing probe
    pairing_profile: Dict[str, Any] = {"attempted": False}
    needs_pair = deep
    if not needs_pair and le_result and _has_auth_annotation(le_result.annotations):
        needs_pair = True
    if needs_pair:
        pairing_profile = _probe_pairing(normalized, timeout=timeout)
        device_data["pairing_profile"] = pairing_profile
        if pairing_profile.get("paired"):
            print_and_log(f"    Paired ({pairing_profile.get('method', '?')})", LOG__GENERAL)

    # 5. Deep: post-pair re-enumeration
    if deep and pairing_profile.get("paired"):
        delta = _perform_deep_reenumeration(
            normalized, device_type, timeout=timeout, use_db=use_db,
        )
        device_data["post_pair_delta"] = delta
        print_and_log("    Post-pair re-enum done", LOG__GENERAL)

    # 6. Persist
    analyzer.save_device_data(normalized, device_data)
    print_and_log(f"[+] Device data saved for {normalized}", LOG__GENERAL)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None):
    argv = argv or sys.argv[1:]
    args = _arg_parser().parse_args(argv)

    # Determine database usage
    use_db = True
    db_only = getattr(args, "db_only", False)
    if hasattr(args, "no_db") and args.no_db:
        use_db = False
        print_and_log("[*] Database integration disabled by --no-db flag", LOG__GENERAL)

    analyzer = AOIAnalyser(use_db=use_db, db_only=db_only)

    # ---------------------------------------------------------------
    # SCAN
    # ---------------------------------------------------------------
    if args.command == "scan" or not args.command:
        if not hasattr(args, "files") or not args.files:
            print_and_log("[-] No files specified for scanning", LOG__GENERAL)
            return 1

        deep = getattr(args, "deep", False)
        timeout = getattr(args, "timeout", 30)
        connectionless = getattr(args, "connectionless", False)
        filter_addr = getattr(args, "address", None)

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
                if filter_addr and mac.upper() != filter_addr.upper():
                    continue
                _scan_target(
                    mac, analyzer,
                    deep=deep, timeout=timeout,
                    use_db=use_db, connectionless=connectionless,
                )
                time.sleep(args.delay)

        print_and_log("[+] AoI scan complete", LOG__GENERAL)

    # ---------------------------------------------------------------
    # ANALYZE
    # ---------------------------------------------------------------
    elif args.command == "analyze":
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

        # --deep on analyze: run SDP + pairing probe first
        if args.deep:
            mac_up = args.address.upper().replace("-", ":")
            dtype = device_data.get("device_type", "unknown")
            if dtype in ("classic", "dual", "unknown"):
                sdp = _discover_sdp(mac_up, timeout=args.timeout, use_db=use_db)
                if sdp:
                    device_data["sdp_summary"] = sdp
            pp = _probe_pairing(mac_up, timeout=args.timeout)
            device_data["pairing_profile"] = pp

        analysis = analyzer.analyze_device_data(device_data)

        device_data["analysis"] = analysis
        analyzer.save_device_data(args.address, device_data)

        print_and_log(f"[+] Analysis complete for {args.address}", LOG__GENERAL)
        if "summary" in analysis:
            s = analysis["summary"]
            if s.get("security_concerns"):
                print_and_log(f"[!] Found {len(s['security_concerns'])} security concerns", LOG__GENERAL)
            if s.get("unusual_characteristics"):
                print_and_log(f"[!] Found {len(s['unusual_characteristics'])} unusual characteristics", LOG__GENERAL)

        storage = "database and file storage" if analyzer.use_db else "file storage only"
        print_and_log(f"[+] Analysis saved to {storage}", LOG__GENERAL)
        print_and_log("[*] Use 'bleep aoi report --address <mac>' to generate a detailed report", LOG__GENERAL)

    # ---------------------------------------------------------------
    # LIST
    # ---------------------------------------------------------------
    elif args.command == "list":
        devices = analyzer.list_devices()
        if not devices:
            print_and_log("[*] No AoI devices found", LOG__GENERAL)
            return 0

        print_and_log(f"[*] Found {len(devices)} AoI devices:", LOG__GENERAL)
        for i, address in enumerate(devices, 1):
            device_data = analyzer.load_device_data(address)
            name = device_data.get("name", "Unknown")
            status = "Analyzed" if "analysis" in device_data else "Not analyzed"
            print_and_log(f"{i}. {address} - {name} ({status})", LOG__GENERAL)

    # ---------------------------------------------------------------
    # REPORT
    # ---------------------------------------------------------------
    elif args.command == "report":
        print_and_log(f"[*] Generating {args.format} report for device: {args.address}", LOG__GENERAL)
        try:
            device_data = analyzer.load_device_data(args.address)
            if not device_data:
                print_and_log(f"[-] No data found for device {args.address}", LOG__GENERAL)
                return 1

            report = analyzer.generate_report(
                device_address=args.address,
                device_data=device_data,
                format=args.format,
            )

            if args.output:
                analyzer.save_report(report, filename=args.output, device_address=args.address)
                print_and_log(f"[+] Report saved to {args.output}", LOG__GENERAL)
            else:
                report_path = analyzer.save_report(report, device_address=args.address)
                print_and_log(f"[+] Report saved to {report_path}", LOG__GENERAL)

        except Exception as e:
            print_and_log(f"[-] Error generating report: {e}", LOG__GENERAL)
            return 1

    # ---------------------------------------------------------------
    # EXPORT
    # ---------------------------------------------------------------
    elif args.command == "export":
        import os

        if args.address:
            print_and_log(f"[*] Exporting data for device: {args.address}", LOG__GENERAL)
            device_data = analyzer.load_device_data(args.address)
            if not device_data:
                print_and_log(f"[-] No data found for device {args.address}", LOG__GENERAL)
                return 1
            output_dir = args.output
            os.makedirs(output_dir, exist_ok=True)
            safe_addr = args.address.replace(":", "")
            output_file = os.path.join(output_dir, f"aoi_export_{safe_addr}.json")
            serializable = _prepare_for_json(device_data)
            with open(output_file, "w") as f:
                json.dump(serializable, f, indent=2, cls=BytesEncoder)
            print_and_log(f"[+] Device data exported to {output_file}", LOG__GENERAL)
        else:
            print_and_log("[*] Exporting data for all devices", LOG__GENERAL)
            devices = analyzer.list_devices()
            if not devices:
                print_and_log("[*] No AoI devices found", LOG__GENERAL)
                return 0
            output_dir = args.output
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"aoi_export_all_{int(time.time())}.json")
            export_data = {}
            for dev_addr in devices:
                dd = analyzer.load_device_data(dev_addr)
                if dd:
                    export_data[dev_addr] = dd
            serializable = _prepare_for_json(export_data)
            with open(output_file, "w") as f:
                json.dump(serializable, f, indent=2, cls=BytesEncoder)
            print_and_log(f"[+] All device data exported to {output_file}", LOG__GENERAL)

    # ---------------------------------------------------------------
    # DB
    # ---------------------------------------------------------------
    elif args.command == "db":
        from bleep.core import observations

        if args.action == "list":
            db_devices = observations.get_aoi_analyzed_devices()
            if not db_devices:
                print_and_log("[*] No AoI devices in database", LOG__GENERAL)
                return 0
            print_and_log(f"[*] {len(db_devices)} AoI device(s) in database:", LOG__GENERAL)
            for i, d in enumerate(db_devices, 1):
                print_and_log(f"{i}. {d['mac']} – {d.get('name', 'Unknown')}", LOG__GENERAL)
            return 0

        if args.action == "import":
            print_and_log("[*] Importing AoI data from files to database", LOG__GENERAL)
            devices = analyzer.list_devices()
            if not devices:
                print_and_log("[-] No AoI devices found in files", LOG__GENERAL)
                return 1
            if args.address:
                devices = [d for d in devices if d.upper() == args.address.upper()]
            if not devices:
                print_and_log(f"[-] Device {args.address} not found in files", LOG__GENERAL)
                return 1

            ok = 0
            for device_mac in devices:
                try:
                    print_and_log(f"[*] Importing {device_mac}...", LOG__GENERAL)
                    device_data = analyzer.load_device_data(device_mac)
                    observations.upsert_device(device_mac, name=device_data.get("name", "Unknown Device"),
                                               last_seen=datetime.datetime.now().isoformat())
                    if "services" in device_data:
                        svc_list = [{"uuid": _normalise_service_element(s)}
                                    for s in device_data["services"]]
                        svc_ids = observations.upsert_services(device_mac, svc_list)
                        if "services_mapping" in device_data and svc_ids:
                            for svc_uuid, svc_id in svc_ids.items():
                                chars = []
                                for uuid, handle in device_data["services_mapping"].items():
                                    if handle == svc_uuid:
                                        ci = {"uuid": uuid}
                                        if "characteristics" in device_data and uuid in device_data["characteristics"]:
                                            ci.update(device_data["characteristics"][uuid])
                                        chars.append(ci)
                                if chars:
                                    observations.upsert_characteristics(svc_id, chars, mac=device_mac, service_uuid=svc_uuid)
                    if "analysis" in device_data:
                        merged = dict(device_data["analysis"])
                        for v11_key in ("pairing_profile", "sdp_summary", "post_pair_delta"):
                            if v11_key in device_data and v11_key not in merged:
                                merged[v11_key] = device_data[v11_key]
                        observations.store_aoi_analysis(device_mac, merged)
                    ok += 1
                    print_and_log(f"[+] Successfully imported {device_mac}", LOG__GENERAL)
                except Exception as e:
                    print_and_log(f"[-] Error importing {device_mac}: {e}", LOG__GENERAL)
            print_and_log(f"[+] Import complete: {ok}/{len(devices)} devices imported", LOG__GENERAL)

        elif args.action == "export":
            print_and_log("[*] Exporting AoI data from database to files", LOG__GENERAL)
            devs = []
            if args.address:
                dd = observations.get_device_detail(args.address)
                if dd:
                    devs = [args.address]
                else:
                    print_and_log(f"[-] Device {args.address} not found in database", LOG__GENERAL)
                    return 1
            else:
                db_devs = observations.get_aoi_analyzed_devices()
                devs = [d["mac"] for d in db_devs]
            if not devs:
                print_and_log("[-] No AoI devices found in database", LOG__GENERAL)
                return 1

            ok = 0
            for device_mac in devs:
                try:
                    print_and_log(f"[*] Exporting {device_mac}...", LOG__GENERAL)
                    device_data = observations.get_device_detail(device_mac)
                    aoi = observations.get_aoi_analysis(device_mac)
                    if aoi:
                        device_data["analysis"] = aoi
                    analyzer.save_device_data(device_mac, device_data)
                    ok += 1
                    print_and_log(f"[+] Successfully exported {device_mac}", LOG__GENERAL)
                except Exception as e:
                    print_and_log(f"[-] Error exporting {device_mac}: {e}", LOG__GENERAL)
            print_and_log(f"[+] Export complete: {ok}/{len(devs)} devices exported", LOG__GENERAL)

        elif args.action == "sync":
            print_and_log("[*] Synchronizing database and files", LOG__GENERAL)

            # Step 1: DB → files
            print_and_log("[*] Step 1: Exporting database data to files", LOG__GENERAL)
            db_devices = observations.get_aoi_analyzed_devices()
            db_macs = [d["mac"] for d in db_devices]
            db_ok = 0
            for dm in db_macs:
                try:
                    dd = observations.get_device_detail(dm)
                    aoi = observations.get_aoi_analysis(dm)
                    if aoi:
                        dd["analysis"] = aoi
                    analyzer.save_device_data(dm, dd)
                    db_ok += 1
                except Exception as e:
                    print_and_log(f"[-] Error exporting {dm}: {e}", LOG__GENERAL)
            print_and_log(f"[+] Database to file sync: {db_ok}/{len(db_macs)} devices", LOG__GENERAL)

            # Step 2: files → DB (only new ones)
            print_and_log("[*] Step 2: Importing file data to database", LOG__GENERAL)
            file_devs = [d for d in analyzer.list_devices() if d not in db_macs]
            f_ok = 0
            for fm in file_devs:
                try:
                    fd = analyzer.load_device_data(fm)
                    observations.upsert_device(fm, name=fd.get("name", "Unknown Device"),
                                               last_seen=datetime.datetime.now().isoformat())
                    if "services" in fd:
                        svc_list = [{"uuid": _normalise_service_element(s)}
                                    for s in fd["services"]]
                        svc_ids = observations.upsert_services(fm, svc_list)
                        if "services_mapping" in fd and svc_ids:
                            for su, si in svc_ids.items():
                                chars = []
                                for uu, hh in fd["services_mapping"].items():
                                    if hh == su:
                                        ci = {"uuid": uu}
                                        if "characteristics" in fd and uu in fd["characteristics"]:
                                            ci.update(fd["characteristics"][uu])
                                        chars.append(ci)
                                if chars:
                                    observations.upsert_characteristics(si, chars, mac=fm, service_uuid=su)
                    if "analysis" in fd:
                        merged = dict(fd["analysis"])
                        for v11_key in ("pairing_profile", "sdp_summary", "post_pair_delta"):
                            if v11_key in fd and v11_key not in merged:
                                merged[v11_key] = fd[v11_key]
                        observations.store_aoi_analysis(fm, merged)
                    f_ok += 1
                except Exception as e:
                    print_and_log(f"[-] Error importing {fm}: {e}", LOG__GENERAL)
            print_and_log(f"[+] File to database sync: {f_ok}/{len(file_devs)} devices", LOG__GENERAL)
            print_and_log(f"[+] Synchronization complete: {db_ok + f_ok} devices total", LOG__GENERAL)

        else:
            print_and_log(f"[-] Unknown database action: {args.action}", LOG__GENERAL)
            return 1

    else:
        print_and_log("[-] Unknown command. Use --help for usage information.", LOG__GENERAL)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    main()
