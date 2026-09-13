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
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bleep.core.output import OutputContext

from bleep.analysis.aoi_analyser import AOIAnalyser, BytesEncoder
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.ble_ops.le.enum_controller import EnumerationController
from bleep.bt_ref.utils import get_name_from_uuid

__all__ = ["run"]

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Device classification helper
# ---------------------------------------------------------------------------

_SEEDABLE_TYPES = ("le", "classic", "dual")


def _classify_device(mac: str, context: Optional[Dict[str, Any]] = None,
                     use_db: bool = True):
    """Classify a device's transport.

    Returns the full ``ClassificationResult`` (carrying ``device_type``,
    ``evidence_source`` and ``cached``) so callers can surface *how* the type
    was determined — heuristic vs measured vs cached — rather than just the
    bare type. Returns ``None`` if classification raised.
    """
    try:
        from bleep.analysis.device_type_classifier import DeviceTypeClassifier
        classifier = DeviceTypeClassifier()
        return classifier.classify_with_mode(
            mac, context or {}, scan_mode="passive", use_database_cache=use_db,
        )
    except Exception as exc:
        logger.debug("classification failed for %s: %s", mac, exc)
        return None


def _resolve_seeded_type(hint: Optional[str], mac: str, *,
                         use_db: bool = True) -> Optional[str]:
    """Return a trustworthy seeded transport (``le``/``classic``/``dual``) or ``None``.

    Prefers the explicit *hint* (e.g. a survey-JSON ``device_type``); if that is
    absent/unusable and *use_db* is set, falls back to the stored device record.
    Never returns ``unknown`` — a seed only exists to fill an inconclusive live
    classification.
    """
    if isinstance(hint, str) and hint.strip().lower() in _SEEDABLE_TYPES:
        return hint.strip().lower()
    if use_db:
        try:
            from bleep.core import observations as _obs
            detail = _obs.get_device_detail(mac)
            stored = ((detail or {}).get("device") or {}).get("device_type")
            if isinstance(stored, str) and stored.strip().lower() in _SEEDABLE_TYPES:
                return stored.strip().lower()
        except Exception as exc:
            logger.debug("seeded-type DB lookup failed for %s: %s", mac, exc)
    return None


def _resolve_device_type(live_type: str, seeded_type: Optional[str], mac: str, *,
                         use_db: bool = True) -> tuple[str, str]:
    """Reconcile a live classification with a survey/DB seed.

    A concrete live result (``le``/``classic``/``dual``) always wins and is never
    up- or down-graded by a seed.  Only when the live result is ``unknown`` do we
    adopt a trustworthy seed.  Returns ``(device_type, source)`` where *source* is
    ``"live"`` or ``"seed"``.
    """
    if live_type and live_type != "unknown":
        return live_type, "live"
    resolved = _resolve_seeded_type(seeded_type, mac, use_db=use_db)
    if resolved:
        return resolved, "seed"
    return "unknown", "live"


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

def _probe_pairing(mac: str, timeout: int = 15, adapter_name: str | None = None) -> Dict[str, Any]:
    """Attempt a JustWorks pair probe; returns a pairing-profile dict."""
    profile: Dict[str, Any] = {"attempted": False, "paired": False, "method": None, "error": None}
    try:
        from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic
        dev = (
            system_dbus__bluez_device__classic(mac, adapter_name=adapter_name)
            if adapter_name
            else system_dbus__bluez_device__classic(mac)
        )
        profile["attempted"] = True
        ok = dev.pair(timeout=timeout)
        profile["paired"] = ok
        profile["method"] = "JustWorks"
    except Exception as exc:
        profile["error"] = str(exc)
    return profile


def _perform_deep_reenumeration(mac: str, device_type: str, *,
                                timeout: int = 30,
                                use_db: bool = True,
                                adapter_name: str | None = None) -> Dict[str, Any]:
    """Post-pair re-enumerate to capture delta (deep mode only).

    Uses pokey mode (write probes) to detect characteristics that became
    writable after pairing — provides richer delta data than passive.
    """
    delta: Dict[str, Any] = {"le_delta": None, "sdp_delta": None}
    if device_type in ("le", "dual"):
        try:
            ctrl = EnumerationController(mac, adapter_name=adapter_name)
            result = ctrl.enumerate(mode="pokey", rounds=2)
            if result.success and result.device:
                data = result.data or {}
                extra = data.pop("_variant_extra", {}) if isinstance(data, dict) else {}
                delta["le_delta"] = {
                    "services": (result.device.get_services()
                                 if hasattr(result.device, "get_services") else []),
                    "data": data,
                }
                if extra:
                    delta["le_delta"]["variant_extra"] = extra
        except Exception as exc:
            logger.debug("deep LE re-enum failed: %s", exc)
    if device_type in ("classic", "dual"):
        try:
            sdp = _discover_sdp(mac, timeout=timeout, use_db=use_db)
            delta["sdp_delta"] = sdp
        except Exception as exc:
            logger.debug("deep SDP re-enum failed: %s", exc)
    return delta


# ---------------------------------------------------------------------------
# MAC iterator
# ---------------------------------------------------------------------------

def _iter_macs(obj) -> List[Dict[str, Optional[str]]]:
    """Return list of ``{"mac", "name", "device_type"}`` dicts from *obj*.

    Survey JSON objects often carry ``name`` and ``device_type`` alongside the
    MAC address.  Extracting them here lets the caller seed the observation DB
    with survey-derived metadata before enumeration begins.
    """
    if isinstance(obj, list):
        entries: List[Dict[str, Optional[str]]] = []
        for item in obj:
            if isinstance(item, dict) and "address" in item:
                entries.append({
                    "mac": item["address"],
                    "name": item.get("name"),
                    "device_type": item.get("device_type"),
                })
            elif isinstance(item, str):
                entries.append({"mac": item, "name": None, "device_type": None})
            else:
                entries.extend(_iter_macs(item))
        return entries
    if isinstance(obj, dict):
        entries_d: List[Dict[str, Optional[str]]] = []
        if "address" in obj:
            entries_d.append({
                "mac": obj["address"],
                "name": obj.get("name"),
                "device_type": obj.get("device_type"),
            })
        for val in obj.values():
            entries_d.extend(_iter_macs(val))
        return entries_d
    return []


# ---------------------------------------------------------------------------
# Scan-target pipeline
# ---------------------------------------------------------------------------

def _scan_target(mac: str, analyzer: AOIAnalyser, *,
                 deep: bool = False, timeout: int = 30,
                 use_db: bool = True, connectionless: bool = False,
                 seeded_type: Optional[str] = None,
                 adapter_name: Optional[str] = None) -> None:
    """Full AoI scan pipeline for a single target MAC.

    *seeded_type* is an optional survey/DB-supplied transport hint. When live
    classification is inconclusive (``unknown``), a trustworthy seed is adopted
    so a device the survey already typed does not regress to ``unknown`` and
    does not get probed on an irrelevant transport. A concrete live result is
    never overridden by a seed.
    """
    normalized = _validate_mac(mac)
    if not normalized:
        print_and_log(f"[-] Invalid MAC, skipping: {mac}", LOG__GENERAL)
        return

    print_and_log(f"[*] AoI target: {normalized}", LOG__GENERAL)

    # 1. Classify device type (seed-aware: live result wins; seed only fills unknown)
    live_result = _classify_device(normalized, use_db=use_db)
    live_type = live_result.device_type if live_result else "unknown"
    device_type, type_source = _resolve_device_type(
        live_type, seeded_type, normalized, use_db=use_db,
    )
    if type_source == "seed":
        print_and_log(
            f"    type={device_type} (live classification unknown; adopted seeded type)",
            LOG__GENERAL,
        )
    else:
        print_and_log(f"    type={device_type}", LOG__GENERAL)

    # 2. LE/Dual: GATT enumeration
    le_result = None
    device_data: Dict[str, Any] = {
        "address": normalized,
        "device_type": device_type,
        "device_type_source": type_source,
        # G-7.4: expose how the live classification was reached so a cached or
        # merely-heuristic verdict is never mistaken for an SDP/GATT-measured one.
        "device_type_evidence_source": (
            live_result.evidence_source if live_result else "heuristic"
        ),
        "device_type_cached": bool(live_result.cached) if live_result else False,
        "scan_timestamp": time.time(),
        "enumerated_by": adapter_name,
    }

    if device_type in ("le", "dual", "unknown"):
        try:
            controller = EnumerationController(normalized, adapter_name=adapter_name)
            enum_mode = "pokey" if deep else "passive"
            enum_kwargs: Dict[str, Any] = {}
            if deep:
                enum_kwargs["rounds"] = 2
            # SR-N3: honor the per-device --timeout on the LE connect path and
            # cap seeded ``dual`` targets to a single LE attempt — the Classic
            # half will not answer an LE connect, so 3 attempts just burn
            # ~3×page-timeout before SDP. Pure LE / unknown keep full retries.
            le_max_attempts = 1 if device_type == "dual" else None
            le_result = controller.enumerate(
                mode=enum_mode, timeout=timeout,
                max_attempts=le_max_attempts, **enum_kwargs,
            )
            if le_result.success and le_result.device:
                dev = le_result.device
                data = le_result.data or {}
                extra = data.pop("_variant_extra", {}) if isinstance(data, dict) else {}
                device_data.update({
                    "name": (getattr(dev, "get_name", lambda: None)()
                             or getattr(dev, "name", "Unknown")),
                    "services": dev.get_services() if hasattr(dev, "get_services") else [],
                    "services_mapping": data,
                    "landmine_map": le_result.landmine_map or {},
                    "permission_map": le_result.permission_map or {},
                    "enumeration_annotations": le_result.serialized_annotations,
                })
                if extra:
                    device_data["variant_extra"] = extra
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

    # 4. Pairing probe — only in deep mode. Pairing performs a real bond and
    #    mutates adapter/device bonding state, so it must never be triggered by
    #    a plain (non-deep) enumeration scan. Auth-related findings are still
    #    captured non-invasively via enumeration annotations above.
    pairing_profile: Dict[str, Any] = {"attempted": False}
    if deep:
        pairing_profile = _probe_pairing(normalized, timeout=timeout, adapter_name=adapter_name)
        device_data["pairing_profile"] = pairing_profile
        if pairing_profile.get("paired"):
            print_and_log(f"    Paired ({pairing_profile.get('method', '?')})", LOG__GENERAL)

    # 5. Deep: post-pair re-enumeration
    if deep and pairing_profile.get("paired"):
        delta = _perform_deep_reenumeration(
            normalized, device_type, timeout=timeout, use_db=use_db,
            adapter_name=adapter_name,
        )
        device_data["post_pair_delta"] = delta
        print_and_log("    Post-pair re-enum done", LOG__GENERAL)

    # 6. Persist
    analyzer.save_device_data(normalized, device_data)

    # Persist security maps + annotations from enumeration
    if use_db and le_result:
        le_result.persist_security_maps(normalized, source="aoi")
    if use_db and adapter_name and le_result is not None and getattr(le_result, "success", False):
        try:
            from bleep.core import observations as _obs_enum
            from bleep.core.time_utils import utc_now_iso

            _obs_enum.upsert_device(
                normalized,
                enumerated_by=adapter_name,
                enumerated_at=utc_now_iso(),
            )
        except Exception:
            pass

    print_and_log(f"[+] Device data saved for {normalized}", LOG__GENERAL)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace, output: "OutputContext | None" = None) -> int:
    """Execute AoI mode with parsed args and optional OutputContext."""
    from bleep.core.output import OutputContext
    from bleep.core.log import set_output_mode

    if output is None:
        output = OutputContext()

    set_output_mode(output.mode)

    return _run_impl(args)


def _run_impl(args: argparse.Namespace) -> int:
    """Core AoI implementation shared by run() and main()."""

    # Determine database usage
    use_db = True
    db_only = getattr(args, "db_only", False)
    if hasattr(args, "no_db") and args.no_db:
        use_db = False
        print_and_log("[*] Database integration disabled by --no-db flag", LOG__GENERAL)

    analyzer = AOIAnalyser(use_db=use_db, db_only=db_only)

    command = getattr(args, "command", None)

    # ---------------------------------------------------------------
    # SCAN
    # ---------------------------------------------------------------
    if command == "scan" or not command:
        if not hasattr(args, "files") or not args.files:
            print_and_log("[-] No files specified for scanning", LOG__GENERAL)
            return 1

        deep = getattr(args, "deep", False)
        timeout = getattr(args, "timeout", 30)
        connectionless = getattr(args, "connectionless", False)
        filter_addr = getattr(args, "address", None)
        analyze_inline = getattr(args, "analyze_inline", False)
        refresh_scan = getattr(args, "refresh_scan", 0) or 0
        adapter_name = getattr(args, "adapter", None)
        if adapter_name:
            from bleep.core.preflight import require_adapter
            if not require_adapter(adapter_name):
                return 1

        # SR-N2: optional pre-enum discovery. Passive survey → AoI can run hours
        # later, by which time LE RPAs have rotated and the seeded addresses are
        # unreachable (DeviceNotFoundError → immediate give-up). A short refresh
        # scan repopulates BlueZ's object cache before we enumerate. Opt-in.
        if refresh_scan > 0:
            print_and_log(
                f"[*] Refresh discovery scan ({refresh_scan}s) to repopulate adapter cache",
                LOG__GENERAL,
            )
            try:
                from bleep.ble_ops.le.scan import passive_scan
                passive_scan(timeout=refresh_scan, quiet=True, adapter_name=adapter_name)
            except Exception as exc:
                print_and_log(f"[-] Refresh scan failed (continuing): {exc}", LOG__GENERAL)

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
            for entry in _iter_macs(data):
                mac = entry["mac"]
                if filter_addr and mac.upper() != filter_addr.upper():
                    continue
                if use_db and (entry.get("name") or entry.get("device_type")):
                    try:
                        from bleep.core import observations as _obs_pre
                        seed_cols: Dict[str, Any] = {}
                        if entry.get("name"):
                            seed_cols["name"] = entry["name"]
                        if entry.get("device_type"):
                            seed_cols["device_type"] = entry["device_type"]
                        _obs_pre.upsert_device(mac, **seed_cols)
                    except Exception:
                        pass
                _scan_target(
                    mac, analyzer,
                    deep=deep, timeout=timeout,
                    use_db=use_db, connectionless=connectionless,
                    seeded_type=entry.get("device_type"),
                    adapter_name=adapter_name,
                )
                # SR-G2: optional inline analysis so a single `aoi scan
                # --analyze` produces reports without a separate analyze pass.
                # Analyses whatever was persisted (incl. Classic SDP/pairing),
                # not just LE-successful targets.
                if analyze_inline:
                    try:
                        analyzer.analyse_device(mac)
                        print_and_log(f"[+] Inline analysis complete for {mac}", LOG__GENERAL)
                    except Exception as exc:
                        print_and_log(f"[-] Inline analysis failed for {mac}: {exc}", LOG__GENERAL)
                time.sleep(args.delay)

        print_and_log("[+] AoI scan complete", LOG__GENERAL)

    # ---------------------------------------------------------------
    # ANALYZE
    # ---------------------------------------------------------------
    elif command == "analyze":
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
            pp = _probe_pairing(mac_up, timeout=args.timeout, adapter_name=getattr(args, "adapter", None))
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
    elif command == "list":
        devices = analyzer.list_devices(
            include_synthetic=getattr(args, "include_synthetic", False))
        if not devices:
            print_and_log("[*] No AoI devices found", LOG__GENERAL)
            return 0

        print_and_log(f"[*] Found {len(devices)} AoI devices:", LOG__GENERAL)
        for i, address in enumerate(devices, 1):
            device_data = analyzer.load_device_data(address)
            # DB-hydrated records nest the name under ``device.name``; file
            # records carry it at the top level.
            name = (device_data.get("name")
                    or (device_data.get("device") or {}).get("name")
                    or "Unknown")
            status = "Analyzed" if "analysis" in device_data else "Not analyzed"
            print_and_log(f"{i}. {address} - {name} ({status})", LOG__GENERAL)

    # ---------------------------------------------------------------
    # REPORT
    # ---------------------------------------------------------------
    elif command == "report":
        if getattr(args, "report_all", False):
            all_addrs = analyzer.list_devices(
                include_synthetic=getattr(args, "include_synthetic", False))
            if not all_addrs:
                # SR-G4: distinguish "no devices at all" from "devices were
                # scanned but never analysed" (common with --db-only when the
                # user ran `aoi scan` without `--analyze`). An empty aggregate
                # otherwise looks like a silent no-op.
                scanned = 0
                if use_db:
                    try:
                        from bleep.core import observations as _obs
                        scanned = len(_obs.get_devices(limit=1000))
                    except Exception:
                        scanned = 0
                if scanned:
                    print_and_log(
                        f"[-] No analysed devices, but {scanned} device(s) are present "
                        f"in the database. Run 'bleep aoi analyze --address <mac>' "
                        f"(or 'bleep aoi scan <file> --analyze') first.",
                        LOG__GENERAL,
                    )
                else:
                    print_and_log("[-] No AoI-analyzed devices found", LOG__GENERAL)
                return 1
            print_and_log(
                f"[*] Generating aggregate {args.format} report for {len(all_addrs)} device(s)",
                LOG__GENERAL,
            )
            try:
                report = analyzer.generate_aggregate_report(all_addrs, format=args.format)
                if args.output:
                    analyzer.save_report(report, filename=args.output)
                    print_and_log(f"[+] Aggregate report saved to {args.output}", LOG__GENERAL)
                else:
                    report_path = analyzer.save_report(
                        report,
                        filename=f"aggregate_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        f".{'json' if args.format == 'json' else 'md' if args.format == 'markdown' else 'txt'}",
                    )
                    print_and_log(f"[+] Aggregate report saved to {report_path}", LOG__GENERAL)
            except Exception as e:
                print_and_log(f"[-] Error generating aggregate report: {e}", LOG__GENERAL)
                return 1
        elif args.address:
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
        else:
            print_and_log("[-] report requires --address or --all", LOG__GENERAL)
            return 1

    # ---------------------------------------------------------------
    # EXPORT
    # ---------------------------------------------------------------
    elif command == "export":
        import os

        if args.address:
            print_and_log(f"[*] Exporting data for device: {args.address}", LOG__GENERAL)
            device_data = analyzer.load_device_data(args.address)
            if not device_data:
                print_and_log(f"[-] No data found for device {args.address}", LOG__GENERAL)
                return 1
            output_dir = args.output or "."
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
            output_dir = args.output or "."
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
    elif command == "db":
        from bleep.core import observations

        if not getattr(args, "action", None):
            if getattr(args, "files", None):
                args.action = args.files[0]
                args.files = list(args.files[1:])
            else:
                print_and_log("[-] Missing db action. Use: list, import, export, sync", LOG__GENERAL)
                return 1

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
                    analyzer._persist_device_to_db(device_mac, device_data)
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
                    analyzer._persist_device_to_db(fm, fd)
                    f_ok += 1
                except Exception as e:
                    print_and_log(f"[-] Error importing {fm}: {e}", LOG__GENERAL)
            print_and_log(f"[+] File to database sync: {f_ok}/{len(file_devs)} devices", LOG__GENERAL)
            print_and_log(f"[+] Synchronization complete: {db_ok + f_ok} devices total", LOG__GENERAL)

        else:
            print_and_log(f"[-] Unknown database action: {args.action}. Use: list, import, export, sync", LOG__GENERAL)
            return 1

    else:
        print_and_log("[-] Unknown command. Use --help for usage information.", LOG__GENERAL)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    """Run AoI mode standalone (``python -m bleep.modes.aoi <subcommand> …``).

    Uses the same canonical argument definitions as the integrated CLI
    (``bleep.cli.parsers.aoi``) so the standalone entry point and
    ``bleep aoi …`` can never diverge.
    """
    from bleep.cli.parsers.aoi import _add_aoi_arguments, apply_aoi_subcommand

    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        prog="bleep-aoi",
        description="Assets-of-Interest scan, analysis, reporting and database operations",
    )
    _add_aoi_arguments(parser)
    args = parser.parse_args(argv)
    apply_aoi_subcommand(args)
    return _run_impl(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main() or 0)
