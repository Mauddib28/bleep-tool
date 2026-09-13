"""
Assets-of-Interest (AoI) analysis module.

This module provides functionality to analyze Bluetooth device data collected during
enumeration and generate actionable reports based on the findings. It processes device
mappings, service/characteristic information, and security-related metadata to identify
notable items of interest.
"""

import json
import logging
import os
import functools
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

from bleep.core.errors import BLEEPError
from bleep.core.time_utils import utc_now_iso
from bleep.bt_ref.utils import get_name_from_uuid
from bleep.ble_ops.common.conversion import format_uuid_display
from bleep.core import observations

__all__ = [
    "BytesEncoder",
    "safe_db_operation",
    "DEFAULT_AOI_DIR",
    "AOIAnalyser",
    "analyse_aoi_data",
]

# Well-known vendor firmware-update / OTA / DFU *service* UUIDs (F8). These are
# custom 128-bit UUIDs (or SIG-member 16-bit forms) that carry no descriptive
# SIG name, so name-substring heuristics miss them. Keyed by the canonical
# 128-bit uppercase form (see :func:`_canonical_uuid`).
_OTA_DFU_SERVICE_UUIDS: Dict[str, str] = {
    # Nordic Semiconductor
    "00001530-1212-EFDE-1523-785FEABCD123": "Nordic Legacy DFU",
    "0000FE59-0000-1000-8000-00805F9B34FB": "Nordic Secure DFU",
    "8EC90001-F315-4F60-9FB8-838830DAEA50": "Nordic Buttonless DFU",
    "8EC90003-F315-4F60-9FB8-838830DAEA50": "Nordic Buttonless DFU",
    # Texas Instruments OAD (Over-the-Air Download)
    "F000FFC0-0451-4000-B000-000000000000": "TI OAD",
    "F000FFD0-0451-4000-B000-000000000000": "TI OAD Reset",
    # Silicon Labs
    "1D14D6EE-FD63-4FA1-BFA4-8F47B42119F0": "Silicon Labs OTA",
    # Zephyr / mcumgr SMP (MCUboot firmware upload)
    "8D53DC1D-1DB7-4CD3-868B-8A527460AA84": "MCUmgr SMP (MCUboot)",
}


def _canonical_uuid(uuid: Any) -> str:
    """Normalise a UUID to the SIG 128-bit uppercase form for set membership.

    Accepts full 128-bit UUIDs (any case) and 16-/32-bit short forms
    (``"FE59"``, ``"0xFE59"``, ``"0000FE59"``), expanding short forms into the BT
    SIG base template. Non-UUID input is returned upper-cased/stripped so callers
    can still compare safely.
    """
    if not isinstance(uuid, str):
        return ""
    u = uuid.strip().upper()
    if u.startswith("0X"):
        u = u[2:]
    hex_only = u.replace("-", "")
    if len(hex_only) in (4, 8) and all(c in "0123456789ABCDEF" for c in hex_only):
        return f"{hex_only.zfill(8)}-0000-1000-8000-00805F9B34FB"
    return u


def _resolve_identity(device_data: Dict[str, Any]) -> Tuple[str, str]:
    """Resolve device address and name from either flat (file) or nested (DB) shapes.

    File-based data uses top-level ``address`` / ``name`` keys.
    DB-based data from ``get_device_detail()`` nests them under a ``device`` sub-dict
    with ``mac`` / ``name`` keys.

    Returns ``(address, name)`` with safe fallbacks.
    """
    address = device_data.get("address")
    name = device_data.get("name")

    if not address or not name:
        nested = device_data.get("device")
        if isinstance(nested, dict):
            address = address or nested.get("mac", "Unknown")
            name = name or nested.get("name", "Unnamed Device")

    return (address or "Unknown", name or "Unnamed Device")


def _radio_provenance(device_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(enumerated_by, seen_by_display)`` from flat or nested DB shapes."""
    nested = device_data.get("device")
    nested = nested if isinstance(nested, dict) else {}
    enum_by = device_data.get("enumerated_by") or nested.get("enumerated_by")
    seen = device_data.get("seen_by")
    if seen is None:
        seen = nested.get("seen_by")
    if isinstance(seen, str):
        try:
            seen = json.loads(seen)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    if isinstance(seen, (list, tuple)):
        seen_disp = ", ".join(str(x) for x in seen if x) or None
    elif seen:
        seen_disp = str(seen)
    else:
        seen_disp = None
    return (str(enum_by) if enum_by else None, seen_disp)


# SR-N4: MACs used only by the test-suite / seeded fixtures. These pollute
# aggregate reports and dilute the average risk score when they leak into a
# real DB. The ``AA:BB:CC:DD:EE:*`` /40 prefix is the canonical documentation
# fixture range (sequential test devices); ``11:22:33:44:55:66`` and the
# all-zero address are the other seeded fixtures observed. This set is
# deliberately narrow — it must never match a legitimate random/private RPA.
_SYNTHETIC_MAC_PREFIXES = ("AA:BB:CC:DD:EE:",)
_SYNTHETIC_MAC_EXACT = frozenset({"11:22:33:44:55:66", "00:00:00:00:00:00"})


def _is_synthetic_mac(mac: Optional[str]) -> bool:
    """Return True for known test-fixture / seeded MAC addresses."""
    if not mac:
        return False
    m = str(mac).upper()
    if m in _SYNTHETIC_MAC_EXACT:
        return True
    return any(m.startswith(p) for p in _SYNTHETIC_MAC_PREFIXES)


def _dedup_concerns(vulnerabilities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """SR-N5: collapse identical ``(name, description, risk)`` concerns.

    A device with N indistinguishable characteristics (e.g. 21 custom
    write-without-response chars) previously rendered N identical lines with no
    identifier. This groups them into one line while collecting the distinct
    characteristic identifiers (``uuid`` or ``uuid#handle``) so the finding is
    both concise and attributable. First-seen order is preserved.
    """
    groups: Dict[tuple, Dict[str, Any]] = {}
    for v in vulnerabilities:
        desc = v.get("description") or v.get("reason", "")
        key = (v.get("name"), desc, v.get("risk", "low"))
        g = groups.get(key)
        if g is None:
            g = {"risk": key[2], "name": key[0], "desc": desc, "ids": [], "count": 0}
            groups[key] = g
        g["count"] += 1
        uuid = v.get("uuid")
        if uuid:
            ident = str(uuid)
            handle = v.get("handle")
            if handle is not None:
                ident = f"{ident}#{handle}"
            if ident not in g["ids"]:
                g["ids"].append(ident)
    return list(groups.values())


def _concern_id_suffix(group: Dict[str, Any], *, backtick: bool = True) -> str:
    """Render the UUID/handle + duplicate-count suffix for a concern group."""
    ids = group.get("ids") or []
    count = group.get("count", 1)

    def _fmt(i: str) -> str:
        return f"`{i}`" if backtick else i

    if count > 1:
        if ids:
            return f" (×{count}: {', '.join(_fmt(i) for i in ids)})"
        return f" (×{count})"
    if ids:
        return f" [{_fmt(ids[0])}]"
    return ""


def _assign_concern_risk(concern: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Attach a ``risk`` level to a security concern dict if not already present.

    Risk classification:
    - **high**: writable auth/key/password characteristics, JustWorks pairing
    - **medium**: exposed Classic profiles (OBEX, FTP, PBAP, SPP, etc.),
      default/weak pairing PINs, spec-version mismatches
    - **low**: informational or unusual-but-not-dangerous findings
    """
    if "risk" in concern:
        return concern

    reason = (concern.get("reason") or concern.get("security_reason") or "").lower()
    name_lower = (concern.get("name") or "").lower()

    if any(kw in reason for kw in ("write without response", "justworks", "no mitm")):
        concern["risk"] = "high"
    elif any(kw in reason for kw in ("outdated bluetooth", "knob", "bias")):
        concern["risk"] = "high"
    elif any(kw in name_lower for kw in ("pairing",)) and "error" in reason:
        concern["risk"] = "medium"
    elif any(kw in reason for kw in ("pairing pin", "weak pin", "default/weak")):
        concern["risk"] = "medium"
    elif any(kw in reason for kw in ("obex", "ftp", "pbap", "map", "spp", "opp", "serial", "classic profile")):
        concern["risk"] = "medium"
    elif any(kw in reason for kw in ("version mismatch", "claims profile version")):
        concern["risk"] = "medium"
    elif source == "characteristic":
        concern["risk"] = "high"
    else:
        concern["risk"] = "low"

    concern.setdefault("description", concern.get("reason", ""))
    return concern


def _render_adv_dissection(device_data: Dict[str, Any]) -> List[str]:
    """Render the "Advertisement Dissection" markdown section (G-7.5).

    Reconstructs dissector inputs from the persisted advertisement fields and
    surfaces attributed, lossless (raw hex + ASCII) entries. Returns an empty
    list when no advertisement data is present; never raises.
    """
    from bleep.analysis.adv_dissect import dissect_persisted_record

    # Reconstruction of dissector inputs from persisted fields lives in the
    # dissector module (single source of truth, shared with the CLI ``db show``
    # renderer) so the two cannot drift. Returns None when no adv data present.
    d = dissect_persisted_record(device_data)
    if not d:
        return []

    lines: List[str] = ["## Advertisement Dissection", ""]
    body_start = len(lines)
    summary = d.get("summary", {})
    if summary.get("vendors"):
        lines.append(f"- **Vendors/Products:** {', '.join(summary['vendors'])}")
    if summary.get("protocols"):
        lines.append(f"- **Protocols:** {', '.join(summary['protocols'])}")
    if summary.get("vendors") or summary.get("protocols"):
        lines.append("")

    for e in d.get("manufacturer_data", []):
        company = e.get("company") or "Unknown vendor"
        lines.append(f"### Manufacturer Data — {e['company_id_hex']} ({company})")
        if e.get("vendor_hints"):
            lines.append(f"- Vendor hints: {', '.join(e['vendor_hints'])}")
        lines.append(f"- Hex: `{e['raw_hex']}`")
        lines.append(f"- ASCII: `{_ascii_from_hex(e['raw_hex'])}`")
        if e.get("decoded"):
            lines.append(f"- Decoded: `{json.dumps(e['decoded'], ensure_ascii=False)}`")
        lines.append("")

    for e in d.get("service_data", []):
        uuid_disp = format_uuid_display(e["uuid"])
        title = e.get("name") or e.get("protocol") or uuid_disp
        lines.append(f"### Service Data — {uuid_disp} ({title})")
        if e.get("protocol"):
            lines.append(f"- Protocol: {e['protocol']}")
        if e.get("vendor_hints"):
            lines.append(f"- Vendor hints: {', '.join(e['vendor_hints'])}")
        lines.append(f"- Hex: `{e['raw_hex']}`")
        lines.append(f"- ASCII: `{_ascii_from_hex(e['raw_hex'])}`")
        if e.get("decoded"):
            lines.append(f"- Decoded: `{json.dumps(e['decoded'], ensure_ascii=False)}`")
        lines.append("")

    adv = d.get("advertising_data", [])
    if adv:
        lines.append("### Advertising Data (AD structures)")
        for e in adv:
            name = e.get("name") or "Unknown"
            lines.append(
                f"- {e['ad_type_hex']} ({name}): Hex `{e['raw_hex']}` / "
                f"ASCII `{_ascii_from_hex(e['raw_hex'])}`")
        lines.append("")

    # The dissector can return a truthy record with no renderable structures
    # (e.g. only bare UUIDs): keep the section but show an explicit ``None``.
    if len(lines) == body_start:
        lines.append("- None.")

    return lines


def _hydrate_db_device_data(device_data: Dict[str, Any]) -> Dict[str, Any]:
    """Transform DB-shaped device data into the format ``analyse_device()`` expects.

    ``get_device_detail()`` returns relational lists::

        services:        [{id, uuid, mac, handle_start, …}]
        characteristics: [{id, service_id, uuid, handle, properties(csv), value(blob), …}]
        descriptors:     [{id, characteristic_id, uuid, handle, flags, value, …}]
        security_maps:   [{landmine_map(json), permission_map(json), …}]

    This function converts them in-place to:

    * ``characteristics`` dict keyed by UUID (properties as list, value as hex)
    * Top-level ``landmine_map`` / ``permission_map`` from latest ``security_maps`` row
    """
    chars_raw = device_data.get("characteristics", [])
    services_raw = device_data.get("services", [])

    if isinstance(chars_raw, list) and chars_raw:
        chars_dict: Dict[str, Any] = {}
        for ch in chars_raw:
            if not isinstance(ch, dict):
                continue
            char_uuid = ch.get("uuid", "")
            if not char_uuid:
                continue

            props = ch.get("properties", "")
            if isinstance(props, str):
                props = [p.strip() for p in props.split(",") if p.strip()]

            val = ch.get("value")
            if isinstance(val, bytes):
                val = val.hex()

            char_info: Dict[str, Any] = {"properties": props}
            if val is not None:
                char_info["value"] = val
            if ch.get("handle") is not None:
                char_info["handle"] = ch["handle"]

            pmap = ch.get("permission_map")
            if isinstance(pmap, str):
                try:
                    pmap = json.loads(pmap)
                except (json.JSONDecodeError, TypeError):
                    pass
            if pmap:
                char_info["permission_map"] = pmap

            chars_dict[char_uuid] = char_info

        device_data["characteristics"] = chars_dict

        # Also build services_mapping for richer grouped analysis
        if isinstance(services_raw, list) and services_raw:
            svc_id_to_uuid: Dict[int, str] = {}
            for svc in services_raw:
                if isinstance(svc, dict) and svc.get("id") is not None:
                    svc_id_to_uuid[svc["id"]] = svc.get("uuid", "unknown")

            svc_mapping: Dict[str, Dict] = {}
            for ch in chars_raw:
                if not isinstance(ch, dict):
                    continue
                svc_id = ch.get("service_id")
                svc_uuid = svc_id_to_uuid.get(svc_id, "unknown")
                char_uuid = ch.get("uuid", "")
                if char_uuid and char_uuid in chars_dict:
                    svc_mapping.setdefault(svc_uuid, {"chars": {}})["chars"][char_uuid] = chars_dict[char_uuid]

            if svc_mapping:
                device_data["services_mapping"] = svc_mapping

    # Hydrate landmine_map and permission_map from security_maps
    sec_maps = device_data.get("security_maps", [])
    if isinstance(sec_maps, list) and sec_maps:
        latest = sec_maps[0]  # Already ordered by ts DESC in get_device_detail()
        if isinstance(latest, dict):
            for key in ("landmine_map", "permission_map"):
                if key not in device_data or not device_data[key]:
                    raw_val = latest.get(key)
                    if isinstance(raw_val, str):
                        try:
                            raw_val = json.loads(raw_val)
                        except (json.JSONDecodeError, TypeError):
                            raw_val = {}
                    if isinstance(raw_val, dict):
                        device_data[key] = raw_val

    # SR-N1: Map Classic SDP + pairing history into the keys analyse_device()
    # reads. get_device_detail() returns these under ``sdp_records`` /
    # ``classic_services`` / ``pairing_events``, but the analyzer gates SDP on
    # ``sdp_summary`` and pairing on ``pairing_profile``. Without this bridge,
    # every Classic/dual device analysed *from the DB* scored 0/10 with no SDP
    # or pairing findings. Additive only — never override a key the caller
    # (e.g. live file-sourced data) already populated.
    if not device_data.get("sdp_summary"):
        sdp_recs = device_data.get("sdp_records") or device_data.get("classic_services")
        if isinstance(sdp_recs, list) and sdp_recs:
            device_data["sdp_summary"] = list(sdp_recs)

    if not device_data.get("pairing_profile"):
        pairing_events = device_data.get("pairing_events")
        if isinstance(pairing_events, list) and pairing_events:
            latest_pair = pairing_events[0]  # ORDER BY ts DESC in get_device_detail()
            if isinstance(latest_pair, dict):
                device_data["pairing_profile"] = _pairing_event_to_profile(latest_pair)

    return device_data


def _pairing_event_to_profile(event: Dict[str, Any]) -> Dict[str, Any]:
    """Derive an ``analyse_pairing_profile``-shaped dict from a DB pairing row.

    DB ``pairing_events`` rows carry ``method`` (e.g. ``RequestConfirmation``),
    ``pin``, ``result`` (``success``/…), ``capabilities`` and JSON
    ``pre_pair_state`` / ``post_pair_state`` blobs. ``paired`` is inferred from a
    successful result or a ``fully_bonded`` post-pair state.
    """
    result = (event.get("result") or "").lower()
    paired = result == "success"

    post_state = event.get("post_pair_state")
    if isinstance(post_state, str):
        try:
            post_state = json.loads(post_state)
        except (json.JSONDecodeError, TypeError):
            post_state = None
    if isinstance(post_state, dict) and post_state.get("fully_bonded"):
        paired = True

    return {
        "attempted": True,
        "paired": paired,
        "method": event.get("method"),
        "pin": event.get("pin"),
        "capabilities": event.get("capabilities"),
        "result": event.get("result"),
    }


def _try_profile_decode(char_uuid: str, raw) -> str | None:
    """Try profile-specific decode for known GATT characteristics."""
    try:
        from bleep.ble_ops.common.gatt_profile_decode import decode_characteristic_value
        if isinstance(raw, (list, tuple)):
            raw = bytes(raw)
        return decode_characteristic_value(char_uuid, raw)
    except Exception:
        return None


class BytesEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles bytes objects by converting them to hex strings."""
    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.hex()
        return super().default(obj)


def safe_db_operation(func):
    """
    Decorator for safely handling database operations with proper error handling.
    
    Args:
        func: The function to wrap
        
    Returns:
        Wrapped function with error handling
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Check for foreign key constraint failure
            if hasattr(e, '__module__') and e.__module__ == 'sqlite3' and 'FOREIGN KEY constraint failed' in str(e):
                logger.error(f"Database foreign key constraint error: {e}")
                
                # Try to extract device MAC from arguments
                device_mac = None
                if len(args) > 1 and isinstance(args[1], str):
                    device_mac = args[1]
                elif 'device_mac' in kwargs:
                    device_mac = kwargs['device_mac']
                elif 'mac' in kwargs:
                    device_mac = kwargs['mac']
                
                # If we found a MAC address, try to create the device
                if device_mac:
                    try:
                        logger.info(f"Creating missing device entry for {device_mac}")
                        observations.upsert_device(
                            device_mac,
                            name=f"Device {device_mac}",
                            addr_type="unknown",
                            device_class=0,
                            device_type="unknown"
                        )
                        # Retry the operation
                        return func(*args, **kwargs)
                    except Exception as inner_e:
                        logger.error(f"Failed to create device entry: {inner_e}")
            
            logger.error(f"Database operation failed: {e}")
            return None
    return wrapper

# Configure logger
logger = logging.getLogger(__name__)

# Default location for AoI JSON dumps
DEFAULT_AOI_DIR = os.path.expanduser("~/.bleep/aoi")


def _aggregate_sdp_inventory(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse per-device SDP records into a readable service inventory.

    Groups the (snapshot-heavy) ``sdp_records`` list by ``(name, uuid, channel)``
    and counts occurrences, mirroring the aggregate DB-9 recon SDP inventory but
    at single-device granularity. The RFCOMM ``channel`` is part of the key so the
    same service class exposed on different channels stays distinct. Returns rows
    ``{name, uuid, channel, count}`` sorted by descending count, then name/uuid.
    """
    from collections import Counter

    counts: "Counter[tuple]" = Counter()
    for rec in records or []:
        name = rec.get("name") or "(unnamed)"
        uuid = rec.get("uuid") or "-"
        channel = rec.get("channel")
        counts[(name, uuid, channel)] += 1
    inventory = [
        {"name": name, "uuid": uuid, "channel": channel, "count": count}
        for (name, uuid, channel), count in counts.items()
    ]
    inventory.sort(key=lambda e: (-e["count"], str(e["name"]), str(e["uuid"])))
    return inventory


def _format_sdp_inventory_row(entry: Dict[str, Any]) -> str:
    """Render one inventory row as ``Name (UUID[, ch N]) : count``."""
    locus = format_uuid_display(entry.get("uuid") or "-")
    channel = entry.get("channel")
    if channel not in (None, ""):
        locus += f", ch {channel}"
    return f"{entry.get('name') or '(unnamed)'} ({locus}) : {entry.get('count', 0):,}"


def _render_sdp_inventory_md(inventory: List[Dict[str, Any]], *, as_table: bool) -> List[str]:
    """Render a per-device SDP service inventory as a markdown table or bullets.

    Follows the unified ``<unique entry> : <count>`` convention. Default is a
    table (``| Service | UUID | Ch | Records |``) for scan-ability; bullet form is
    selected via ``--report-bullets`` (``as_table=False``).
    """
    total = sum(e.get("count", 0) for e in inventory)
    header = f"**Service inventory ({len(inventory):,} unique of {total:,} records):**"
    if not as_table:
        return [header] + [f"- {_format_sdp_inventory_row(e)}" for e in inventory]
    lines = [header, "", "| Service | UUID | Ch | Records |", "|---------|------|----|---------|"]
    for e in inventory:
        channel = e.get("channel")
        ch = str(channel) if channel not in (None, "") else "-"
        lines.append(
            f"| {e.get('name') or '(unnamed)'} | `{format_uuid_display(e.get('uuid') or '-')}` "
            f"| {ch} | {e.get('count', 0):,} |")
    return lines


def _collapse_counted(items: List[Any]) -> List[tuple]:
    """Collapse a list of repeated entries into ``[(value, count)]``.

    Sorted by descending count then value — the unified ``<entry> : <count>``
    convention. Snapshot-heavy devices repeat the identical SDP security flag once
    per record, so this deduplicates them for display. Skips ``None``/empty.
    """
    from collections import Counter

    counts = Counter(i for i in (items or []) if i not in (None, ""))
    return sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))


def _collapse_anomalies(anomalies: List[Dict[str, Any]]) -> List[tuple]:
    """Collapse SDP anomalies into ``[(severity, description, count)]``.

    Grouped by ``(severity, description)`` with occurrence counts, sorted by
    descending count then severity/description — mirrors ``_collapse_counted`` for
    the richer anomaly shape.
    """
    from collections import Counter

    counts: "Counter[tuple]" = Counter()
    for a in anomalies or []:
        sev = str(a.get("severity", "low")).upper()
        desc = a.get("description", a.get("type", ""))
        counts[(sev, desc)] += 1
    return [(sev, desc, n) for (sev, desc), n in
            sorted(counts.items(), key=lambda kv: (-kv[1], kv[0][0], str(kv[0][1])))]


def _render_flags_enrichment_md(flags: List[str], protocols: List[str],
                                spec: Any, anomalies: List[Dict[str, Any]],
                                *, as_table: bool) -> List[str]:
    """Render the per-device SDP ``Flags & enrichment`` block (markdown).

    Security flags and SDP anomalies are collapsed to unique-entry ``: count`` rows
    (the same convention as the service inventory) so a snapshot-heavy device no
    longer repeats one identical flag per SDP record. Rendered as markdown tables
    by default; ``as_table=False`` (``--report-bullets``) uses bullet lists.
    Protocols and the spec hint stay inline (small, unique, count-free).
    """
    if not (flags or protocols or spec or anomalies):
        return []
    lines = ["", "**Flags & enrichment:**"]
    if protocols:
        lines.append(f"- Protocols: {', '.join(protocols)}")
    if spec:
        lines.append(f"- SDP-inferred spec hint: ~{spec} (profile versions, not the core spec)")
    flag_rows = _collapse_counted(flags)
    if flag_rows:
        if as_table:
            lines += ["", "| Security flag | Count |", "|---------------|-------|"]
            lines += [f"| {value} | {count:,} |" for value, count in flag_rows]
        else:
            lines += [f"- **{value}** : {count:,}" for value, count in flag_rows]
    anomaly_rows = _collapse_anomalies(anomalies)
    if anomaly_rows:
        if as_table:
            lines += ["", "| Severity | SDP anomaly | Count |", "|----------|-------------|-------|"]
            lines += [f"| {sev} | {desc} | {count:,} |" for sev, desc, count in anomaly_rows]
        else:
            lines += [f"- **SDP anomaly [{sev}]:** {desc} : {count:,}"
                      for sev, desc, count in anomaly_rows]
    return lines


def _render_flags_enrichment_text(flags: List[str], protocols: List[str],
                                  spec: Any, anomalies: List[Dict[str, Any]]) -> List[str]:
    """Plain-text counterpart of ``_render_flags_enrichment_md`` (bullets only)."""
    if not (flags or protocols or spec or anomalies):
        return []
    lines = ["Flags & enrichment:"]
    if protocols:
        lines.append(f"- Protocols: {', '.join(protocols)}")
    if spec:
        lines.append(f"- SDP-inferred spec hint: ~{spec} (profile versions, not the core spec)")
    for value, count in _collapse_counted(flags):
        lines.append(f"- {value} : {count:,}")
    for sev, desc, count in _collapse_anomalies(anomalies):
        lines.append(f"- SDP anomaly [{sev}]: {desc} : {count:,}")
    return lines


def _ascii_from_hex(raw_hex: str) -> str:
    """Render a hex payload as its ASCII gloss using the hexdump convention.

    Printable bytes (0x20–0x7E) render as their character; every other byte
    (control/high/NUL) renders as ``.`` — exactly how ``hexdump -C`` shows the
    ASCII column — so noisy binary no longer produces replacement-character mojibake
    in reports. Returns ``""`` for empty/unparseable input; never raises.
    """
    try:
        data = bytes.fromhex(raw_hex or "")
    except (ValueError, TypeError):
        return ""
    return "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in data)


class AOIAnalyser:
    """
    Analyser for Assets-of-Interest data collected from Bluetooth devices.
    
    This class processes device data collected during enumeration and generates
    actionable reports highlighting security concerns, unusual characteristics,
    and other notable findings.
    """
    
    def __init__(self, aoi_dir: Optional[str] = None, use_db: bool = True,
                 db_only: bool = False):
        """
        Initialize the AOI Analyser.
        
        Args:
            aoi_dir: Directory where AoI JSON dumps are stored. Defaults to ~/.bleep/aoi/
            use_db: Whether to use the database for storage/retrieval
            db_only: If True, skip file writes (database only)
        """
        self.aoi_dir = Path(aoi_dir or DEFAULT_AOI_DIR)
        self._ensure_aoi_dir()
        self.reports = {}
        self.use_db = use_db
        self.db_only = db_only
        
    def _prepare_data_for_json(self, data):
        """
        Convert non-serializable types in data structure to serializable ones.
        
        Args:
            data: Any data structure that might contain non-serializable types
            
        Returns:
            Data structure with all non-serializable types converted to serializable ones
        """
        if isinstance(data, bytes):
            return data.hex()
        elif isinstance(data, dict):
            return {k: self._prepare_data_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._prepare_data_for_json(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self._prepare_data_for_json(item) for item in data)
        else:
            return data
        
    def _ensure_aoi_dir(self) -> None:
        """Ensure the AoI directory exists."""
        os.makedirs(self.aoi_dir, exist_ok=True)
    
    def list_devices(self, include_synthetic: bool = False) -> List[str]:
        """
        List all devices that have data in the AOI storage (file or database).

        Args:
            include_synthetic: When ``False`` (default), well-known test/fixture
                MACs (see :func:`_is_synthetic_mac`) are excluded so aggregate
                reports and listings are not polluted by seeded test data.

        Returns:
            List of normalized MAC addresses (with colons)
        """
        def _finalize(macs) -> List[str]:
            if include_synthetic:
                return list(macs)
            return [m for m in macs if not _is_synthetic_mac(m)]

        if self.use_db:
            # Try database first
            try:
                # Get devices from database
                devices = observations.get_aoi_analyzed_devices()
                if devices:
                    return _finalize([device["mac"].upper() for device in devices])

                # If no devices found in database, fall back to files
                logger.info("No AoI devices found in database, falling back to files")
            except Exception as e:
                logger.error(f"Error accessing database, falling back to files: {str(e)}")
        
        # Fall back to file-based lookup
        # Ensure directory exists
        self._ensure_aoi_dir()
        
        # Get all JSON files in the directory
        json_files = list(self.aoi_dir.glob("*.json"))
        
        # Extract device MAC addresses from filenames
        devices = set()
        for file_path in json_files:
            # Extract the MAC part from the filename (before the timestamp)
            filename = file_path.stem  # Get filename without extension
            if "_" in filename:
                mac = filename.split("_")[0]  # Get the part before the first underscore
                # Convert to standard MAC format with colons
                normalized = ":".join([mac[i:i+2] for i in range(0, len(mac), 2)]).upper()
                devices.add(normalized)
        
        return _finalize(devices)
        
    def load_device_data(self, device_mac: str) -> Dict[str, Any]:
        """
        Load AoI data for a specific device from either database or file.
        
        Args:
            device_mac: MAC address of the device
            
        Returns:
            Dictionary of device data
            
        Raises:
            FileNotFoundError: If no data exists for this device
            BLEEPError: If data exists but is corrupted or incompatible
        """
        # Try to load from database if enabled
        if self.use_db:
            try:
                # Get device details from database
                device_data = observations.get_device_detail(device_mac)
                if device_data and device_data.get("device"):
                    _hydrate_db_device_data(device_data)
                    aoi_analysis = observations.get_aoi_analysis(device_mac)
                    if aoi_analysis:
                        device_data["analysis"] = aoi_analysis
                    return device_data
                
                logger.info("DB returned empty shell for %s, falling through to file lookup", device_mac)
            except Exception as e:
                logger.warning("DB access failed for %s, falling back to files: %s", device_mac, e)
        
        # Fall back to file-based lookup
        # Normalize MAC address format
        device_mac_norm = device_mac.replace(':', '').upper()
        
        # Find the most recent file for this device
        device_files = list(self.aoi_dir.glob(f"{device_mac_norm}*.json"))
        if not device_files:
            raise FileNotFoundError(f"No AoI data found for device {device_mac}")
            
        # Sort by modification time (most recent first)
        device_files.sort(key=os.path.getmtime, reverse=True)
        latest_file = device_files[0]
        
        try:
            with open(latest_file, 'r') as f:
                data = json.load(f)
            return data
        except json.JSONDecodeError as e:
            raise BLEEPError(f"Invalid JSON in {latest_file}: {str(e)}")
        except Exception as e:
            raise BLEEPError(f"Error loading {latest_file}: {str(e)}")
    
    def _persist_device_to_db(self, device_mac: str, data: Dict[str, Any]) -> None:
        """Persist device info, services, GATT characteristics/descriptors and
        analysis to the observation DB.

        This is the **single** DB-write implementation shared by
        :meth:`save_device_data` and the ``aoi db import``/``sync`` commands, so
        every write path handles the nested ``services_mapping`` GATT structure
        identically.  Callers are responsible for their own error handling.
        """
        if not isinstance(device_mac, str):
            device_mac = str(device_mac)

        # Extract basic device information — only include name if the caller
        # supplied a meaningful one.  Placeholder names like "Unknown Device"
        # must NOT overwrite a previously-resolved name.
        device_info: Dict[str, Any] = {"last_seen": utc_now_iso()}
        raw_name = data.get("name")
        if raw_name and raw_name not in ("Unknown Device", "Unknown"):
            device_info["name"] = raw_name
        if "device_type" in data:
            device_info["device_type"] = data["device_type"]
        if "addr_type" in data:
            device_info["addr_type"] = data["addr_type"]
        if "device_class" in data:
            device_info["device_class"] = data["device_class"]

        observations.upsert_device(device_mac, **device_info)

        # Save services if present
        if "services" in data:
            services = []
            if isinstance(data["services"], dict):
                for svc_uuid, svc_info in data["services"].items():
                    if isinstance(svc_info, dict):
                        svc_info["uuid"] = svc_uuid
                        services.append(svc_info)
                    else:
                        services.append({"uuid": svc_uuid})
            else:
                # List elements may be plain UUID strings (file/enumeration
                # shape) or ``{"uuid": …}`` row dicts (DB-export shape).
                for svc in data["services"]:
                    if isinstance(svc, dict):
                        svc_uuid = svc.get("uuid") or svc.get("UUID")
                        if svc_uuid:
                            entry = {"uuid": str(svc_uuid)}
                            for _k in ("handle_start", "handle_end", "name", "is_primary", "includes"):
                                if svc.get(_k) is not None:
                                    entry[_k] = svc[_k]
                            services.append(entry)
                    elif svc is not None:
                        services.append({"uuid": str(svc)})

            service_ids = observations.upsert_services(device_mac, services)

            # Persist chars/descriptors from the full GATT mapping structure
            if "services_mapping" in data and service_ids:
                svc_map = data["services_mapping"]
                for svc_uuid, svc_id in service_ids.items():
                    svc_data = svc_map.get(svc_uuid)
                    if not isinstance(svc_data, dict):
                        continue
                    chars_data = svc_data.get("chars") or svc_data.get("Characteristics")
                    if not chars_data or not isinstance(chars_data, dict):
                        continue
                    char_list = []
                    for char_uuid, char_info in chars_data.items():
                        if not isinstance(char_info, dict):
                            char_list.append({"uuid": char_uuid})
                            continue
                        char_entry = {
                            "uuid": char_uuid,
                            "handle": char_info.get("handle"),
                            "properties": list(char_info.get("properties", {}).keys()) if isinstance(char_info.get("properties"), dict) else char_info.get("properties", []),
                            "value": char_info.get("value"),
                        }
                        if char_info.get("mtu") is not None:
                            char_entry["mtu"] = char_info["mtu"]
                        char_list.append(char_entry)
                    if char_list:
                        observations.upsert_characteristics(svc_id, char_list, mac=device_mac, service_uuid=svc_uuid)
                    # Persist descriptors
                    for char_uuid, char_info in chars_data.items():
                        if not isinstance(char_info, dict):
                            continue
                        desc_data = char_info.get("Descriptors") or char_info.get("descriptors")
                        if not desc_data or not isinstance(desc_data, dict):
                            continue
                        char_id = observations.get_characteristic_id(svc_id, char_uuid)
                        if not char_id:
                            continue
                        desc_list = []
                        for d_uuid, d_entry in desc_data.items():
                            d_info = {"uuid": d_uuid}
                            if isinstance(d_entry, dict):
                                d_info["value"] = d_entry.get("Value") or d_entry.get("value")
                                d_info["handle"] = d_entry.get("Handle") or d_entry.get("handle")
                                d_info["flags"] = d_entry.get("Flags") or d_entry.get("flags")
                            desc_list.append(d_info)
                        if desc_list:
                            observations.upsert_descriptors(char_id, desc_list)

        # If analysis exists, merge v11 fields and persist
        if "analysis" in data:
            merged_analysis = dict(data["analysis"])
            for v11_key in ("pairing_profile", "sdp_summary", "post_pair_delta"):
                if v11_key in data and v11_key not in merged_analysis:
                    merged_analysis[v11_key] = data[v11_key]
            observations.store_aoi_analysis(device_mac, merged_analysis)

    @safe_db_operation
    def save_device_data(self, device_mac: str, data: Dict[str, Any]) -> str:
        """
        Save device data to storage (database and/or file).
        
        Args:
            device_mac: MAC address of the device
            data: Dictionary of device data to save
            
        Returns:
            Path to the saved file (if file storage is used)
        """
        # Ensure device_mac is a string
        if not isinstance(device_mac, str):
            device_mac = str(device_mac)
            
        # Save to database if enabled
        if self.use_db:
            try:
                self._persist_device_to_db(device_mac, data)
                logger.info(f"Saved AoI data to database for {device_mac}")
            except Exception as e:
                logger.error(f"Error saving to database: {str(e)}")
                # Continue with file save even if database save fails
        
        if self.db_only:
            return ""

        # Normalize MAC address format
        device_mac_norm = device_mac.replace(':', '').upper()
        
        # Create timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create filename
        filename = f"{device_mac_norm}_{timestamp}.json"
        filepath = self.aoi_dir / filename
        
        # Prepare data for serialization
        serializable_data = self._prepare_data_for_json(data)
        
        with open(filepath, 'w') as f:
            json.dump(serializable_data, f, indent=2, cls=BytesEncoder)
        
        logger.info(f"Saved AoI data to {filepath}")
        return str(filepath)
    
    def analyse_device(self, device_mac: str, data: Optional[Dict[str, Any]] = None,
                       *, persist: bool = True) -> Dict[str, Any]:
        """
        Analyze device data and generate a report.
        
        Args:
            device_mac: MAC address of the device
            data: Optional device data dictionary. If None, data will be loaded from file
            persist: When ``True`` (default) the analysis is written to the
                observation DB. Rendering paths (``generate_report``) pass
                ``False`` so that merely *viewing* a report never mutates
                persistent state.
            
        Returns:
            Analysis report dictionary
        """
        # Ensure device_mac is a string
        if not isinstance(device_mac, str):
            device_mac = str(device_mac)
            
        # Load data if not provided
        if data is None:
            data = self.load_device_data(device_mac)
            
        # Handle case where data is None or not a dictionary
        if not data or not isinstance(data, dict):
            logger.error(f"Invalid device data for {device_mac}")
            data = {}
        
        # Initialize report structure
        report = {
            "device_mac": device_mac,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "security_concerns": [],
                "unusual_characteristics": [],
                "notable_services": [],
                "accessibility": {},
                "recommendations": [],
            },
            "details": {
                "services": [],
                "characteristics": [],
                "landmine_map": {},
                "permission_map": {},
            }
        }
        
        # Extract service and characteristic information
        services_data = data.get("services", {})
        characteristics = data.get("characteristics", {})
        landmine_map = data.get("landmine_map", {})
        permission_map = data.get("permission_map", {})
        
        # Handle different service data formats
        if isinstance(services_data, list):
            for elem in services_data:
                svc_uuid = elem.get("uuid", elem.get("UUID", "")) if isinstance(elem, dict) else str(elem)
                service_info = {"uuid": svc_uuid}
                service_report = self._analyse_service(svc_uuid, service_info)
                if service_report:
                    report["details"]["services"].append(service_report)
                    if service_report.get("is_notable", False):
                        report["summary"]["notable_services"].append({
                            "uuid": svc_uuid,
                            "name": service_report.get("name", "Unknown Service"),
                            "reason": service_report.get("notable_reason", ""),
                        })
        # If services is a dictionary
        elif isinstance(services_data, dict):
            for uuid, service_info in services_data.items():
                service_report = self._analyse_service(uuid, service_info)
                if service_report:
                    report["details"]["services"].append(service_report)
                    
                    # Check for notable services
                    if service_report.get("is_notable", False):
                        report["summary"]["notable_services"].append({
                            "uuid": uuid,
                            "name": service_report.get("name", "Unknown Service"),
                            "reason": service_report.get("notable_reason", ""),
                        })
        
        # Extract characteristics from the full GATT mapping structure
        if not characteristics and "services_mapping" in data:
            svc_map = data.get("services_mapping", {})
            for _svc_uuid, svc_data in svc_map.items():
                if not isinstance(svc_data, dict):
                    continue
                chars_data = svc_data.get("chars") or svc_data.get("Characteristics") or {}
                if not isinstance(chars_data, dict):
                    continue
                for char_uuid, char_info in chars_data.items():
                    if not isinstance(char_info, dict):
                        char_info = {}
                    char_info_copy = dict(char_info)
                    char_info_copy["uuid"] = char_uuid
                    char_report = self._analyse_characteristic(char_uuid, char_info_copy)
                    if char_report:
                        report["details"]["characteristics"].append(char_report)

                        if char_report.get("security_concern", False):
                            report["summary"]["security_concerns"].append(
                                self._char_concern_from_report(char_uuid, char_report))

                        if char_report.get("is_unusual", False):
                            report["summary"]["unusual_characteristics"].append({
                                "uuid": char_uuid,
                                "name": char_report.get("name", "Unknown Characteristic"),
                                "reason": char_report.get("unusual_reason", ""),
                            })
        # Process normal characteristics dictionary
        elif isinstance(characteristics, dict):
            for uuid, char_info in characteristics.items():
                char_report = self._analyse_characteristic(uuid, char_info)
                if char_report:
                    report["details"]["characteristics"].append(char_report)
                    
                    if char_report.get("security_concern", False):
                        report["summary"]["security_concerns"].append(
                            self._char_concern_from_report(uuid, char_report))
                    
                    if char_report.get("is_unusual", False):
                        report["summary"]["unusual_characteristics"].append({
                            "uuid": uuid,
                            "name": char_report.get("name", "Unknown Characteristic"),
                            "reason": char_report.get("unusual_reason", ""),
                        })
        # Defensive fallback: DB-shaped flat list of characteristic row dicts
        elif isinstance(characteristics, list):
            for ch in characteristics:
                if not isinstance(ch, dict):
                    continue
                char_uuid = ch.get("uuid", "")
                if not char_uuid:
                    continue
                props = ch.get("properties", "")
                if isinstance(props, str):
                    props = [p.strip() for p in props.split(",") if p.strip()]
                val = ch.get("value")
                if isinstance(val, bytes):
                    val = val.hex()
                char_info = dict(ch, properties=props)
                if val is not None:
                    char_info["value"] = val
                char_report = self._analyse_characteristic(char_uuid, char_info)
                if char_report:
                    report["details"]["characteristics"].append(char_report)

                    if char_report.get("security_concern", False):
                        report["summary"]["security_concerns"].append(
                            self._char_concern_from_report(char_uuid, char_report))

                    if char_report.get("is_unusual", False):
                        report["summary"]["unusual_characteristics"].append({
                            "uuid": char_uuid,
                            "name": char_report.get("name", "Unknown Characteristic"),
                            "reason": char_report.get("unusual_reason", ""),
                        })
        
        # Analyze permission and landmine maps
        report["details"]["landmine_map"] = self._analyse_landmine_map(landmine_map)
        report["details"]["permission_map"] = self._analyse_permission_map(permission_map)
        
        # Generate accessibility summary
        report["summary"]["accessibility"] = self._generate_accessibility_summary(
            report["details"]["landmine_map"], 
            report["details"]["permission_map"]
        )
        
        # Analyse v11 fields if present
        if "sdp_summary" in data:
            sdp_analysis = self._analyse_sdp_records(data["sdp_summary"])
            report["sdp_summary"] = sdp_analysis
            for flag in sdp_analysis.get("security_flags", []):
                report["summary"]["security_concerns"].append(
                    _assign_concern_risk({"name": "Classic Profile", "reason": flag},
                                         source="sdp"))

        if "pairing_profile" in data:
            pp_analysis = self._analyse_pairing_profile(data["pairing_profile"])
            report["pairing_profile"] = pp_analysis
            for c in pp_analysis.get("concerns", []):
                report["summary"]["security_concerns"].append(
                    _assign_concern_risk({"name": "Pairing", "reason": c},
                                         source="pairing"))

        if "post_pair_delta" in data:
            ppd = self._analyse_post_pair_delta(data["post_pair_delta"])
            report["post_pair_delta"] = ppd

        # RV-3c: Check remote Bluetooth version for security concerns
        lmp_version = (
            data.get("lmp_version")
            or (data.get("device") or {}).get("lmp_version")
        )
        if lmp_version is not None:
            try:
                lmp_int = int(lmp_version)
                from bleep.ble_ops.classic.version import map_lmp_version_to_spec
                spec_str = map_lmp_version_to_spec(lmp_int) or f"LMP {lmp_int}"
                if lmp_int < 6:
                    report["summary"]["security_concerns"].append(
                        _assign_concern_risk({
                            "name": "Bluetooth Version",
                            "reason": (
                                f"Outdated Bluetooth version ({spec_str}) — pre-4.0, "
                                "lacks LE Secure Connections and modern encryption"
                            ),
                        }, source="version"))
                elif lmp_int < 8:
                    report["summary"]["security_concerns"].append(
                        _assign_concern_risk({
                            "name": "Bluetooth Version",
                            "reason": (
                                f"Outdated Bluetooth version ({spec_str}) — pre-4.2, "
                                "vulnerable to KNOB/BIAS attacks, lacks Secure Connections"
                            ),
                        }, source="version"))
            except (TypeError, ValueError):
                pass

        # RV-3c/3d: Cross-validate LMP against SDP profile versions
        sdp_records = data.get("sdp_summary") or data.get("sdp_records") or []
        if lmp_version is not None and sdp_records:
            try:
                from bleep.analysis.sdp_analyzer import SDPAnalyzer
                sdp_xval = SDPAnalyzer(sdp_records)
                sdp_xval.analyze()
                xval_result = sdp_xval.cross_validate_lmp(int(lmp_version))
                if xval_result:
                    report["summary"]["security_concerns"].append(
                        _assign_concern_risk({
                            "name": "Version Mismatch",
                            "reason": xval_result["description"],
                        }, source="sdp"))
            except Exception:
                pass

        # Generate recommendations
        report["summary"]["recommendations"] = self._generate_recommendations(report)
        
        report = self._prepare_data_for_json(report)
        
        # Store the report
        self.reports[device_mac] = report
        
        # Store in database if enabled (skipped for read-only rendering paths)
        if persist and self.use_db:
            try:
                # Ensure device exists in database before storing analysis
                try:
                    device_exists = observations.get_device_detail(device_mac) is not None
                    if not device_exists:
                        logger.info(f"Creating device entry for {device_mac} before storing analysis")
                        observations.upsert_device(
                            device_mac,
                            name=f"Device {device_mac}",
                            addr_type="unknown",
                            device_class=0,
                            device_type="unknown"
                        )
                except Exception as e:
                    logger.error(f"Error checking device existence: {str(e)}")
                
                merged_report = dict(report)
                for v11_key in ("pairing_profile", "sdp_summary", "post_pair_delta"):
                    if v11_key in data and v11_key not in merged_report:
                        merged_report[v11_key] = data[v11_key]
                observations.store_aoi_analysis(device_mac, merged_report)
                logger.info(f"Saved analysis to database for {device_mac}")
            except Exception as e:
                logger.error(f"Error saving analysis to database: {str(e)}")
                
        return report
    
    def _analyse_service(self, uuid: str, service_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a service and generate a report.
        
        Args:
            uuid: Service UUID
            service_info: Service information dictionary
            
        Returns:
            Service analysis report
        """
        # Basic service report
        service_report = {
            "uuid": uuid,
            "name": get_name_from_uuid(uuid),
            "is_primary": service_info.get("is_primary", False),
            "is_notable": False,
            "characteristics": service_info.get("characteristics", []),
        }
        
        # Check for notable services
        name_l = service_report["name"].lower()
        if uuid in ["00001800-0000-1000-8000-00805F9B34FB", "00001801-0000-1000-8000-00805F9B34FB"]:  # GAP and GATT
            service_report["is_notable"] = True
            service_report["notable_reason"] = "Core BLE service"
        elif _canonical_uuid(uuid) in _OTA_DFU_SERVICE_UUIDS:
            # Vendor OTA/DFU service with a custom (non-SIG-named) UUID (F8).
            vendor = _OTA_DFU_SERVICE_UUIDS[_canonical_uuid(uuid)]
            service_report["is_notable"] = True
            service_report["notable_reason"] = f"Firmware update / OTA service ({vendor})"
        elif "OTA" in service_report["name"] or "dfu" in name_l or "firmware" in name_l:
            # "OTA" kept as a case-sensitive acronym match to avoid false
            # positives on substrings like "toyota"/"iota"/"quota".
            service_report["is_notable"] = True
            service_report["notable_reason"] = "Firmware update service"
        elif "auth" in name_l or "security" in name_l:
            service_report["is_notable"] = True
            service_report["notable_reason"] = "Authentication/security service"
        
        return service_report
    
    def _analyse_characteristic(self, uuid: str, char_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a characteristic and generate a report.
        
        Args:
            uuid: Characteristic UUID
            char_info: Characteristic information dictionary
            
        Returns:
            Characteristic analysis report
        """
        # Basic characteristic report
        char_report = {
            "uuid": uuid,
            "name": get_name_from_uuid(uuid),
            "properties": char_info.get("properties", []),
            "security_concern": False,
            "is_unusual": False,
        }
        
        # Check properties
        properties = char_info.get("properties", [])
        props_l = [str(p).lower() for p in properties]
        writable = "write-without-response" in props_l or "write" in props_l

        # Resolve an effective name: SIG-derived name, else any explicit
        # name/description carried on the characteristic (custom UUIDs).
        sig_name = char_report["name"]
        eff_name = sig_name
        if sig_name in ("Unknown", "Unknown Characteristic"):
            for alt_key in ("name", "description", "user_description"):
                alt = char_info.get(alt_key)
                if isinstance(alt, str) and alt.strip():
                    eff_name = alt
                    break
        name_l = eff_name.lower()

        # High-signal: a named authentication/credential characteristic that is
        # writable (covers custom UUIDs that expose a meaningful name).
        auth_kw = ("auth", "password", "passphrase", "key", "pin", "token", "credential")
        if writable and any(kw in name_l for kw in auth_kw):
            char_report["security_concern"] = True
            char_report["security_reason"] = (
                f"Authentication-related characteristic '{eff_name}' allows write without response"
                if "write-without-response" in props_l
                else f"Authentication-related characteristic '{eff_name}' is writable"
            )
        # Medium-signal: a custom/unknown characteristic that accepts
        # write-without-response with no authenticated/signed write requirement —
        # an unauthenticated write surface worth investigating.
        elif ("write-without-response" in props_l
              and "authenticated-signed-writes" not in props_l
              and sig_name in ("Unknown", "Unknown Characteristic")):
            char_report["security_concern"] = True
            char_report["security_reason"] = (
                "Custom characteristic accepts write-without-response with no "
                "authenticated/signed-write requirement (unauthenticated write surface)"
            )
            char_report["security_risk"] = "medium"
        
        # Check for unusual characteristics (F8: refined, case-insensitive). A
        # characteristic that is both writable *and* pushes data (notify/indicate)
        # is a bidirectional control channel — the meaningful signal, independent
        # of the (previously arbitrary) total property count.
        notifies = "notify" in props_l or "indicate" in props_l
        if writable and notifies:
            char_report["is_unusual"] = True
            char_report["unusual_reason"] = "Writable and notify/indicate — bidirectional control channel"

        # A long hex default value can indicate an embedded blob. 40 hex chars
        # ≈ 20 bytes; require a hex-like string so short human-readable defaults
        # are not flagged.
        value = char_info.get("value")
        if (isinstance(value, str) and len(value) > 40
                and all(c in "0123456789abcdefABCDEF" for c in value)):
            char_report["is_unusual"] = True
            char_report["unusual_reason"] = "Contains unusually long default value (possible embedded data)"

        raw = char_info.get("Raw") or char_info.get("raw")
        if raw is not None:
            decoded = _try_profile_decode(uuid, raw)
            if decoded:
                char_report["decoded_value"] = decoded

        return char_report

    def _char_concern_from_report(self, uuid: str, char_report: Dict[str, Any]) -> Dict[str, Any]:
        """Build a risk-classified security-concern dict from a characteristic report.

        Honours an explicit ``security_risk`` hint from
        :meth:`_analyse_characteristic`; otherwise defers to
        :func:`_assign_concern_risk`.  Shared by every characteristic-analysis
        branch in :meth:`analyse_device` so risk assignment stays consistent.
        """
        concern: Dict[str, Any] = {
            "uuid": uuid,
            "name": char_report.get("name", "Unknown Characteristic"),
            "reason": char_report.get("security_reason", ""),
        }
        risk = char_report.get("security_risk")
        if risk:
            concern["risk"] = risk
        return _assign_concern_risk(concern, source="characteristic")
    
    @staticmethod
    def _normalize_security_map(raw: Any) -> Dict[str, str]:
        """Flatten a landmine/permission map to ``{uuid: status}`` for analysis.

        Live GATT enumeration emits a **nested** structure keyed by object type
        and issue type (``{obj_type: {issue_type: [uuid, …]}}``, plus an
        ``in_review`` bucket — see ``dbuslayer/device_le.py``), whereas
        synthetic and DB-hydrated inputs use a **flat** ``{uuid: status}`` dict.
        This normaliser accepts *both* shapes so downstream per-UUID analysis is
        correct regardless of source:

        * a **nested** map is flattened, keying each UUID to its ``issue_type``;
        * an already-**flat** map is returned unchanged (legacy/test contract).

        An empty or non-dict input yields ``{}``.
        """
        if not isinstance(raw, dict) or not raw:
            return {}

        # Nested iff any value is itself a dict (issue_type → uuid-list mapping).
        # A flat map's values are status strings, so this reliably distinguishes
        # the two shapes without misclassifying the legacy contract.
        if not any(isinstance(v, dict) for v in raw.values()):
            return dict(raw)

        flat: Dict[str, str] = {}
        for issues in raw.values():
            if not isinstance(issues, dict):
                continue
            for issue_type, uuids in issues.items():
                if not isinstance(uuids, (list, tuple, set)):
                    continue
                for uuid in uuids:
                    flat[str(uuid)] = issue_type
        return flat

    def _analyse_landmine_map(self, landmine_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the landmine map.
        
        Args:
            landmine_map: Landmine map from device data (flat or nested shape)
            
        Returns:
            Processed landmine map with additional analysis
        """
        result = {}
        for uuid, status in self._normalize_security_map(landmine_map).items():
            result[uuid] = {
                "status": status,
                "is_critical": self._is_critical_uuid(uuid),
            }
        return result
    
    def _analyse_permission_map(self, permission_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the permission map.
        
        Args:
            permission_map: Permission map from device data (flat or nested shape)
            
        Returns:
            Processed permission map with additional analysis
        """
        result = {}
        for uuid, status in self._normalize_security_map(permission_map).items():
            result[uuid] = {
                "status": status,
                "is_critical": self._is_critical_uuid(uuid),
            }
        return result
    
    def _is_critical_uuid(self, uuid: str) -> bool:
        """
        Determine if a UUID is for a critical characteristic.
        
        Args:
            uuid: Characteristic UUID
            
        Returns:
            True if the UUID is critical, False otherwise
        """
        # Get UUID name and convert to lowercase
        name = get_name_from_uuid(uuid).lower()
        
        # Check for critical keywords
        critical_keywords = ["auth", "password", "key", "firmware", "dfu", "ota", "security"]
        return any(keyword in name for keyword in critical_keywords)
    
    def _generate_accessibility_summary(self, landmine_map: Dict[str, Any], 
                                       permission_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a summary of device accessibility.
        
        Args:
            landmine_map: Processed landmine map
            permission_map: Processed permission map
            
        Returns:
            Accessibility summary
        """
        total_chars = len(set(landmine_map.keys()).union(set(permission_map.keys())))
        blocked_chars = sum(1 for _, info in landmine_map.items() if info["status"] != "OK")
        protected_chars = sum(1 for _, info in permission_map.items() if info["status"] != "OK")
        
        return {
            "total_characteristics": total_chars,
            "blocked_characteristics": blocked_chars,
            "protected_characteristics": protected_chars,
            "accessibility_score": (total_chars - blocked_chars - protected_chars) / total_chars if total_chars else 0,
        }
    
    def _analyse_sdp_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyse SDP records for security-relevant services.
        
        Returns a summary dict with ``services_found``, ``security_flags``,
        and ``raw_count``.
        """
        security_flags: List[str] = []
        svc_names: List[str] = []
        for rec in records:
            name = rec.get("name") or ""
            svc_names.append(name or rec.get("uuid", "unknown"))
            lower = name.lower()
            if any(kw in lower for kw in ("obex", "ftp", "opp", "pbap", "map", "spp", "serial")):
                security_flags.append(f"Classic profile exposed: {name}")
        summary: Dict[str, Any] = {
            "raw_count": len(records),
            "services_found": svc_names,
            # Readable, de-duplicated inventory grouped by (name, uuid, channel)
            # with occurrence counts — mirrors the DB-9 aggregate SDP inventory so
            # snapshot-heavy record sets stay legible. `services_found` is retained
            # unchanged for JSON/back-compat.
            "services_inventory": _aggregate_sdp_inventory(records),
            "security_flags": security_flags,
        }

        # F9: enrich with the comprehensive SDPAnalyzer (protocols, anomalies,
        # inferred spec) instead of only the shallow substring scan above. This is
        # additive — the shallow summary and its `security_flags` are preserved for
        # backward compatibility, and any analyzer failure leaves them untouched.
        if records:
            try:
                from bleep.analysis.sdp_analyzer import SDPAnalyzer
                analysis = SDPAnalyzer(records).analyze()
                protocols = analysis.get("protocol_analysis", {})
                if protocols.get("protocols_found"):
                    summary["protocols"] = protocols["protocols_found"]
                if protocols.get("rfcomm_channels"):
                    summary["rfcomm_channels"] = protocols["rfcomm_channels"]
                anomalies = analysis.get("anomalies") or []
                if anomalies:
                    summary["anomalies"] = anomalies
                inferred = (analysis.get("version_inference") or {}).get("inferred_version")
                if inferred:
                    summary["inferred_spec_version"] = inferred
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(f"SDPAnalyzer enrichment skipped: {exc}")

        return summary

    def _analyse_pairing_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Analyse a pairing-profile dict for security concerns."""
        concerns: List[str] = []
        if profile.get("paired") and profile.get("method") == "JustWorks":
            concerns.append("Device paired via JustWorks (no MITM protection)")
        # SR-N1: surface default/weak legacy PINs (e.g. 0000/1234) captured
        # during a bond. Only flag when a PIN was actually observed.
        pin = profile.get("pin")
        if pin is not None and self._is_weak_pin(str(pin)):
            concerns.append(f"Default/weak pairing PIN observed ({pin})")
        if profile.get("error") and "rejected" not in str(profile["error"]).lower():
            concerns.append(f"Pairing error: {profile['error']}")
        return {
            "concerns": concerns,
            "method": profile.get("method"),
            "paired": profile.get("paired", False),
            "pin": pin,
        }

    @staticmethod
    def _is_weak_pin(pin: str) -> bool:
        """Return True for well-known default or trivially-weak numeric PINs."""
        pin = pin.strip()
        if not pin:
            return False
        if pin in {"0000", "1234", "1111", "0000000", "00000000", "123456"}:
            return True
        # All-identical digits (e.g. 2222) or short numeric PINs (< 6 digits).
        if pin.isdigit() and (len(set(pin)) == 1 or len(pin) < 6):
            return True
        return False

    def _analyse_post_pair_delta(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """Analyse changes revealed by post-pair re-enumeration."""
        findings: List[str] = []
        if delta.get("le_delta"):
            le = delta["le_delta"]
            svc_count = len(le.get("services", []))
            findings.append(f"Post-pair LE enum revealed {svc_count} service(s)")
        if delta.get("sdp_delta"):
            findings.append(f"Post-pair SDP revealed {len(delta['sdp_delta'])} record(s)")
        return {"findings": findings}

    def _generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """
        Generate recommendations based on the report.
        
        Args:
            report: Device analysis report
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Check security concerns
        if report["summary"]["security_concerns"]:
            recommendations.append(
                f"Investigate {len(report['summary']['security_concerns'])} security concerns including "
                f"{report['summary']['security_concerns'][0]['name']}."
            )
        
        # Check unusual characteristics
        if report["summary"]["unusual_characteristics"]:
            recommendations.append(
                f"Examine {len(report['summary']['unusual_characteristics'])} unusual characteristics including "
                f"{report['summary']['unusual_characteristics'][0]['name']}."
            )
        
        accessibility = report.get("summary", {}).get("accessibility", {})
        acc_score = accessibility.get("accessibility_score", 0) if isinstance(accessibility, dict) else 0
        if acc_score > 0.8:
            recommendations.append(
                f"Device is highly accessible ({acc_score:.2%}). "
                "Consider detailed enumeration of all characteristics."
            )
        elif acc_score < 0.3 and acc_score != 0:
            recommendations.append(
                f"Device has limited accessibility ({acc_score:.2%}). "
                "Consider authentication/pairing options."
            )
        
        # Default recommendation
        if not recommendations:
            recommendations.append("No specific concerns found. Continue with standard enumeration.")
        
        return recommendations
        
    def analyze_device_data(self, device_data: Dict[str, Any],
                            *, persist: bool = True) -> Dict[str, Any]:
        """
        Analyze device data without requiring a device_mac.
        This method serves as a bridge between generate_report and analyse_device.
        
        Args:
            device_data: Device data dictionary
            persist: Forwarded to :meth:`analyse_device`. Rendering callers pass
                ``False`` to keep report generation read-only.
            
        Returns:
            Analysis report dictionary
        """
        address, _ = _resolve_identity(device_data)
        device_mac = address if address != "Unknown" else device_data.get("device_mac", "unknown")
        return self.analyse_device(device_mac, device_data, persist=persist)
    
    def generate_report(self, device_address: str = None, device_data: Dict = None, 
                       format: str = "markdown") -> str:
        """
        Generate a security report for the specified device.
        
        Args:
            device_address: MAC address of the device
            device_data: Device data if already loaded
            format: Report format ("markdown", "json", "text")
            
        Returns:
            Report content as string
        """
        # Load device data if not provided
        if not device_data and device_address:
            device_data = self.load_device_data(device_address)
            
        if not device_data:
            raise BLEEPError("No device data available for report generation")
            
        # Analyze the device data if not already analyzed. Rendering a report is
        # read-only: never persist analysis as a side effect of viewing it.
        if "analysis" not in device_data:
            analysis = self.analyze_device_data(device_data, persist=False)
        else:
            analysis = device_data["analysis"]
            
        # Calculate security score
        security_score = self._calculate_security_score(analysis)
            
        # Generate report based on format
        if format == "json":
            return self._generate_json_report(device_data, analysis, security_score)
        elif format == "text":
            return self._generate_text_report(device_data, analysis, security_score)
        else:  # markdown is default
            return self._generate_markdown_report(device_data, analysis, security_score)
    
    def _calculate_security_score(self, analysis: Dict) -> int:
        """Calculate a 0-10 risk score (higher = more risk).

        A fully clean device (no security concerns) scores **0**. Each concern
        adds by severity — ``high`` = 3, ``medium`` = 2, ``low`` = 1 — and the
        total is capped at 10 (F5). Integer weights keep the score exact (no
        truncation). Handles both new-style concerns (with a ``risk`` field) and
        legacy concerns (only ``reason``), the latter classified via
        ``_assign_concern_risk`` first.
        """
        score = 0

        if "summary" in analysis and "security_concerns" in analysis["summary"]:
            concerns = analysis["summary"]["security_concerns"]
            for c in concerns:
                if "risk" not in c:
                    _assign_concern_risk(c, source="unknown")

            high_risk = sum(1 for c in concerns if c.get("risk") == "high")
            medium_risk = sum(1 for c in concerns if c.get("risk") == "medium")
            low_risk = sum(1 for c in concerns if c.get("risk") == "low")

            score = high_risk * 3 + medium_risk * 2 + low_risk * 1

        return min(max(score, 0), 10)
    
    def _generate_markdown_report(self, device_data: Dict, analysis: Dict, security_score: int) -> str:
        """Generate a markdown report."""
        address, name = _resolve_identity(device_data)
        
        report = [
            f"# Security Report: {name} ({address})",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**BLEEP Version:** {self._get_version()}",
            "",
            "## Device Information",
            "",
            f"- **Address:** {address}",
            f"- **Name:** {name}",
        ]
        
        # Transport type + provenance (G-7.4): show WHETHER the type was
        # SDP/GATT-measured, merely heuristic (advertised UUIDs / beacons), or a
        # cached DB signature — so an advertised-only guess is never read as a
        # confirmed capability.
        dtype = device_data.get("device_type")
        if dtype:
            annotations = []
            src = device_data.get("device_type_evidence_source")
            if src:
                annotations.append(str(src))
            if device_data.get("device_type_cached"):
                annotations.append("cached")
            tsrc = device_data.get("device_type_source")
            if tsrc and tsrc != "live":
                annotations.append(f"source: {tsrc}")
            suffix = f" ({'; '.join(annotations)})" if annotations else ""
            report.append(f"- **Device Type:** {dtype}{suffix}")

        # Add RSSI if available
        if "rssi" in device_data:
            report.append(f"- **RSSI:** {device_data['rssi']} dBm")
            
        # Add device class if available
        if "device_class" in device_data:
            report.append(f"- **Device Class:** {device_data['device_class']}")

        enum_by, seen_by = _radio_provenance(device_data)
        if enum_by:
            report.append(f"- **Enumerated via:** {enum_by}")
        if seen_by:
            report.append(f"- **Seen by:** {seen_by}")

        # G-7.5: structured advertisement dissection (attributed, lossless).
        adv_lines = _render_adv_dissection(device_data)
        if adv_lines:
            report.append("")
            report.extend(adv_lines)

        report.extend([
            "",
            "## Security Analysis",
            "",
            f"**Risk Score:** {security_score}/10 (higher = more risk)",
            "",
        ])
        
        # Add vulnerabilities section
        vulnerabilities = []
        if "summary" in analysis and "security_concerns" in analysis["summary"]:
            vulnerabilities = analysis["summary"]["security_concerns"]
            
        if vulnerabilities:
            report.append("### Vulnerabilities")
            report.append("")

            for grp in _dedup_concerns(vulnerabilities):
                risk_emoji = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(grp["risk"], "⚪")
                suffix = _concern_id_suffix(grp)
                report.append(f"{risk_emoji} **{grp['name']}:** {grp['desc']}{suffix}")

            report.append("")
        
        if "services" in device_data:
            report.extend(["## Services", ""])
            if not device_data["services"]:
                report.extend(["- None.", ""])
            for service in device_data["services"]:
                if isinstance(service, dict):
                    uuid = service.get("uuid", "Unknown")
                    name = service.get("name") or get_name_from_uuid(uuid) or uuid
                elif isinstance(service, str):
                    uuid = service
                    name = get_name_from_uuid(uuid) or uuid
                else:
                    continue
                report.append(f"### {name}")
                report.append(f"- UUID: `{uuid}`")
                if isinstance(service, dict):
                    chars = service.get("characteristics", [])
                    if chars:
                        report.append("- **Characteristics:**")
                        for char in chars:
                            char_uuid = char.get("uuid", "Unknown")
                            char_name = char.get("name", get_name_from_uuid(char_uuid) or char_uuid)
                            flags = ", ".join(char.get("flags", []))
                            report.append(f"  - {char_name} (`{char_uuid}`): {flags}")
                            for vuln in vulnerabilities:
                                if vuln.get("uuid") == char_uuid:
                                    vdesc = vuln.get("description") or vuln.get("reason", "")
                                    report.append(f"    - ⚠️ {vdesc}")
                report.append("")
        
        # SDP summary section
        sdp_info = analysis.get("sdp_summary") or device_data.get("sdp_summary")
        if sdp_info:
            report.extend(["## SDP Discovery", ""])
            as_table = not getattr(self, "_report_bullets", False)
            if isinstance(sdp_info, dict):
                inventory = sdp_info.get("services_inventory")
                if inventory:
                    report.extend(_render_sdp_inventory_md(inventory, as_table=as_table))
                else:
                    for svc in sdp_info.get("services_found", []):
                        report.append(f"- {svc}")
                # F9: SDPAnalyzer enrichment kept distinct from the service
                # inventory above under an explicit sub-label, with repeated flags
                # collapsed to unique "<flag> : count" rows (table by default).
                report.extend(_render_flags_enrichment_md(
                    sdp_info.get("security_flags") or [],
                    sdp_info.get("protocols") or [],
                    sdp_info.get("inferred_spec_version"),
                    sdp_info.get("anomalies") or [],
                    as_table=as_table))
            elif isinstance(sdp_info, list):
                report.extend(_render_sdp_inventory_md(_aggregate_sdp_inventory(sdp_info), as_table=as_table))
            report.append("")

        # Pairing profile section
        pp = analysis.get("pairing_profile") or device_data.get("pairing_profile")
        if pp and pp.get("attempted", pp.get("paired", False)):
            report.extend(["## Pairing Profile", ""])
            report.append(f"- **Method:** {pp.get('method', 'N/A')}")
            report.append(f"- **Paired:** {'Yes' if pp.get('paired') else 'No'}")
            for c in pp.get("concerns", []):
                report.append(f"- {c}")
            report.append("")

        ppd = analysis.get("post_pair_delta") or device_data.get("post_pair_delta")
        if ppd:
            findings = ppd.get("findings", [])
            if not findings:
                findings = []
                if ppd.get("le_delta"):
                    le = ppd["le_delta"]
                    cnt = len(le.get("services", []))
                    findings.append(f"Post-pair LE enum revealed {cnt} service(s)")
                if ppd.get("sdp_delta"):
                    findings.append(f"Post-pair SDP revealed {len(ppd['sdp_delta'])} record(s)")
            if findings:
                report.extend(["## Post-Pair Delta", ""])
                for f in findings:
                    report.append(f"- {f}")
                report.append("")

        # Recommendations
        recommendations = self._generate_recommendations(analysis)
        if recommendations:
            report.extend(["## Recommendations", ""])
            for i, rec in enumerate(recommendations, 1):
                report.append(f"{i}. {rec}")
                
        return "\n".join(report)
    
    def _generate_text_report(self, device_data: Dict, analysis: Dict, security_score: int) -> str:
        """Generate a plain text report."""
        address, name = _resolve_identity(device_data)
        
        # Convert markdown to plain text
        report = [
            f"SECURITY REPORT: {name} ({address})",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"BLEEP Version: {self._get_version()}",
            "",
            "DEVICE INFORMATION",
            f"Address: {address}",
            f"Name: {name}",
        ]
        
        # Add RSSI if available
        if "rssi" in device_data:
            report.append(f"RSSI: {device_data['rssi']} dBm")
            
        # Add device class if available
        if "device_class" in device_data:
            report.append(f"Device Class: {device_data['device_class']}")

        enum_by, seen_by = _radio_provenance(device_data)
        if enum_by:
            report.append(f"Enumerated via: {enum_by}")
        if seen_by:
            report.append(f"Seen by: {seen_by}")
            
        report.extend([
            "",
            "SECURITY ANALYSIS",
            f"Risk Score: {security_score}/10 (higher = more risk)",
            "",
        ])
        
        # Add vulnerabilities section
        vulnerabilities = []
        if "summary" in analysis and "security_concerns" in analysis["summary"]:
            vulnerabilities = analysis["summary"]["security_concerns"]
            
        if vulnerabilities:
            report.append("VULNERABILITIES")

            for grp in _dedup_concerns(vulnerabilities):
                risk = grp["risk"].upper()
                suffix = _concern_id_suffix(grp, backtick=False)
                report.append(f"[{risk}] {grp['name']}: {grp['desc']}{suffix}")

            report.append("")
        
        # SDP summary
        sdp_info = analysis.get("sdp_summary") or device_data.get("sdp_summary")
        if sdp_info:
            report.append("SDP DISCOVERY")
            if isinstance(sdp_info, dict):
                inventory = sdp_info.get("services_inventory")
                if inventory:
                    total = sum(e.get("count", 0) for e in inventory)
                    report.append(f"Service inventory ({len(inventory):,} unique of {total:,} records):")
                    for e in inventory:
                        report.append(f"- {_format_sdp_inventory_row(e)}")
                else:
                    for svc in sdp_info.get("services_found", []):
                        report.append(f"- {svc}")
                report.extend(_render_flags_enrichment_text(
                    sdp_info.get("security_flags") or [],
                    sdp_info.get("protocols") or [],
                    sdp_info.get("inferred_spec_version"),
                    sdp_info.get("anomalies") or []))
            elif isinstance(sdp_info, list):
                inventory = _aggregate_sdp_inventory(sdp_info)
                total = sum(e.get("count", 0) for e in inventory)
                report.append(f"Service inventory ({len(inventory):,} unique of {total:,} records):")
                for e in inventory:
                    report.append(f"- {_format_sdp_inventory_row(e)}")
            report.append("")

        # Pairing profile
        pp = analysis.get("pairing_profile") or device_data.get("pairing_profile")
        if pp and pp.get("attempted", pp.get("paired", False)):
            report.append("PAIRING PROFILE")
            report.append(f"Method: {pp.get('method', 'N/A')}")
            report.append(f"Paired: {'Yes' if pp.get('paired') else 'No'}")
            report.append("")

        recommendations = self._generate_recommendations(analysis)
        if recommendations:
            report.append("RECOMMENDATIONS")
            for i, rec in enumerate(recommendations, 1):
                report.append(f"{i}. {rec}")
                
        return "\n".join(report)
    
    @staticmethod
    def _sanitize_for_json(obj: Any) -> Any:
        """Recursively convert bytes and other non-serializable types for JSON output."""
        if isinstance(obj, bytes):
            return obj.hex()
        elif isinstance(obj, dict):
            return {k: AOIAnalyser._sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [AOIAnalyser._sanitize_for_json(item) for item in obj]
        elif isinstance(obj, set):
            return sorted(AOIAnalyser._sanitize_for_json(item) for item in obj)
        return obj

    def _generate_json_report(self, device_data: Dict, analysis: Dict, security_score: int) -> str:
        """Generate a JSON report."""
        # Extract vulnerabilities
        vulnerabilities = []
        if "summary" in analysis and "security_concerns" in analysis["summary"]:
            vulnerabilities = analysis["summary"]["security_concerns"]
            
        # Extract recommendations
        recommendations = self._generate_recommendations(analysis)
        
        report = {
            "device": device_data,
            "analysis": {
                "timestamp": datetime.now().isoformat(),
                "security_score": security_score,
                "vulnerabilities": vulnerabilities,
                "recommendations": recommendations,
            },
            "metadata": {
                "version": self._get_version(),
                "generator": "BLEEP AOI Analyzer",
            },
        }
        for v11_key in ("sdp_summary", "pairing_profile", "post_pair_delta"):
            val = analysis.get(v11_key) or device_data.get(v11_key)
            if val:
                report["analysis"][v11_key] = val

        return json.dumps(self._sanitize_for_json(report), indent=2)
    
    def generate_aggregate_report(
        self,
        addresses: List[str],
        format: str = "markdown",
        bullets: bool = False,
    ) -> str:
        """Generate a combined report covering multiple AoI-analyzed devices.

        ``bullets=True`` renders the per-device SDP service inventory as bullet
        lists instead of the default markdown table (mirrors ``--report-bullets``).
        """
        self._report_bullets = bullets
        per_device: List[Dict[str, Any]] = []
        for addr in addresses:
            try:
                data = self.load_device_data(addr)
                if not data:
                    continue
                if "analysis" not in data:
                    data["analysis"] = self.analyze_device_data(data, persist=False)
                per_device.append(data)
            except Exception as exc:
                logger.warning("Skipping %s in aggregate report: %s", addr, exc)

        if not per_device:
            raise BLEEPError("No device data available for aggregate report")

        if format == "json":
            return self._generate_aggregate_json(per_device)
        elif format == "text":
            return self._generate_aggregate_text(per_device)
        return self._generate_aggregate_markdown(per_device)

    @staticmethod
    def _device_was_enumerated(dev: Dict[str, Any]) -> bool:
        """True when a device produced an analysis surface worth aggregating.

        Aggregate averages/tables should reflect devices we actually reached — not
        LE targets whose (often rotating/stale RPA) advertisement was captured but
        that never yielded a GATT/SDP enumeration. A device counts as reachable when
        it exposes GATT services, Classic SDP/pairing data, enumerated
        characteristics, or any raised security concern; a load-only 0/10 row with no
        such surface is treated as "not reachable" so it neither dilutes the average
        nor pads the analyzed table.
        """
        if dev.get("services") or dev.get("sdp_summary") or dev.get("pairing_profile"):
            return True
        analysis = dev.get("analysis") or {}
        if analysis.get("sdp_summary") or analysis.get("pairing_profile"):
            return True
        details = analysis.get("details") or {}
        if details.get("services") or details.get("characteristics"):
            return True
        if (analysis.get("summary") or {}).get("security_concerns"):
            return True
        return False

    def _generate_aggregate_markdown(self, devices: List[Dict[str, Any]]) -> str:
        total = len(devices)
        reached = [d for d in devices if self._device_was_enumerated(d)]
        not_reached = [d for d in devices if not self._device_was_enumerated(d)]
        scores = [self._calculate_security_score(d.get("analysis", {})) for d in reached]
        avg_score = round(sum(scores) / len(reached), 1) if reached else 0

        lines = [
            "# Aggregate Security Report",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**BLEEP Version:** {self._get_version()}",
            f"**Devices Loaded:** {total}",
            f"**Devices Analyzed:** {len(reached)}",
            f"**Not Reachable (no GATT/SDP enumerated):** {len(not_reached)}",
            f"**Average Risk Score:** {avg_score}/10 (analyzed only; higher = more risk)",
            "",
            "## Device Summary",
            "",
            "| # | Address | Name | Score | High | Med | Low |",
            "|---|---------|------|-------|------|-----|-----|",
        ]

        for i, dev in enumerate(reached, 1):
            addr, dev_name = _resolve_identity(dev)
            analysis = dev.get("analysis", {})
            score = self._calculate_security_score(analysis)
            concerns = (analysis.get("summary") or {}).get("security_concerns", [])
            high = sum(1 for c in concerns if c.get("risk") == "high")
            med = sum(1 for c in concerns if c.get("risk") == "medium")
            low = sum(1 for c in concerns if c.get("risk") == "low")
            lines.append(f"| {i} | `{addr}` | {dev_name} | {score}/10 | {high} | {med} | {low} |")

        if not_reached:
            lines.extend([
                "",
                "## Not Reachable (no GATT/SDP enumerated)",
                "",
                "These devices were observed/loaded but produced no enumeration surface, so they are excluded from the average above.",
                "",
                "| # | Address | Name |",
                "|---|---------|------|",
            ])
            for i, dev in enumerate(not_reached, 1):
                addr, dev_name = _resolve_identity(dev)
                lines.append(f"| {i} | `{addr}` | {dev_name} |")

        lines.extend(["", "---", ""])

        for dev in reached:
            analysis = dev.get("analysis", {})
            score = self._calculate_security_score(analysis)
            report_str = self._generate_markdown_report(dev, analysis, score)
            lines.append(report_str)
            lines.extend(["", "---", ""])

        return "\n".join(lines)

    def _generate_aggregate_text(self, devices: List[Dict[str, Any]]) -> str:
        reached = [d for d in devices if self._device_was_enumerated(d)]
        not_reached = [d for d in devices if not self._device_was_enumerated(d)]
        parts = [
            "AGGREGATE SECURITY REPORT",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"BLEEP Version: {self._get_version()}",
            f"Devices Loaded: {len(devices)}",
            f"Devices Analyzed: {len(reached)}",
            f"Not Reachable (no GATT/SDP enumerated): {len(not_reached)}",
            "",
            "=" * 60,
        ]
        for dev in reached:
            analysis = dev.get("analysis", {})
            score = self._calculate_security_score(analysis)
            parts.append(self._generate_text_report(dev, analysis, score))
            parts.extend(["", "=" * 60, ""])
        if not_reached:
            parts.append("NOT REACHABLE (no GATT/SDP enumerated):")
            for dev in not_reached:
                addr, dev_name = _resolve_identity(dev)
                parts.append(f"  - {addr}  {dev_name}")
            parts.extend(["", "=" * 60, ""])
        return "\n".join(parts)

    def _generate_aggregate_json(self, devices: List[Dict[str, Any]]) -> str:
        reports = []
        for dev in devices:
            analysis = dev.get("analysis", {})
            score = self._calculate_security_score(analysis)
            concerns = (analysis.get("summary") or {}).get("security_concerns", [])
            recs = self._generate_recommendations(analysis)
            entry: Dict[str, Any] = {
                "device": dev,
                "analysis": {
                    "timestamp": datetime.now().isoformat(),
                    "security_score": score,
                    "vulnerabilities": concerns,
                    "recommendations": recs,
                },
            }
            for v11_key in ("sdp_summary", "pairing_profile", "post_pair_delta"):
                val = analysis.get(v11_key) or dev.get(v11_key)
                if val:
                    entry["analysis"][v11_key] = val
            entry["reachable"] = self._device_was_enumerated(dev)
            reports.append(entry)

        # Average only over devices that produced an enumeration surface so stale/
        # unreachable LE targets don't drag the aggregate toward 0/10.
        reached_scores = [r["analysis"]["security_score"] for r in reports if r["reachable"]]
        not_reachable_count = sum(1 for r in reports if not r["reachable"])
        aggregate = {
            "metadata": {
                "version": self._get_version(),
                "generator": "BLEEP AOI Analyzer",
                "timestamp": datetime.now().isoformat(),
                "device_count": len(reports),
                "analyzed_count": len(reached_scores),
                "not_reachable_count": not_reachable_count,
                "avg_security_score": round(sum(reached_scores) / len(reached_scores), 1) if reached_scores else 0,
            },
            "devices": reports,
        }
        return json.dumps(self._sanitize_for_json(aggregate), indent=2)

    def save_report(self, report_content: str, filename: str = None, device_address: str = None) -> str:
        """
        Save a report to disk.
        
        Args:
            report_content: Content of the report
            filename: Custom filename
            device_address: Device address to use in filename
            
        Returns:
            Path to saved report
        """
        if not filename:
            if device_address:
                safe_addr = device_address.replace(':', '')
                filename = f"report_{safe_addr}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            else:
                filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                
        # Create reports subdirectory in the AOI directory
        report_dir = Path(self.aoi_dir) / "reports"
        os.makedirs(report_dir, exist_ok=True)
        
        # Save the report
        report_path = report_dir / filename
        with open(report_path, 'w') as f:
            f.write(report_content)
            
        logger.info(f"Report saved to {report_path}")
        return str(report_path)
    
    def _get_version(self) -> str:
        """Get BLEEP version."""
        try:
            from bleep import __version__
            return __version__
        except (ImportError, AttributeError):
            return "Unknown"


def analyse_aoi_data(device_mac: str, data: Optional[Dict[str, Any]] = None, 
                    aoi_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to analyze AoI data for a device.
    
    Args:
        device_mac: Device MAC address
        data: Optional device data. If None, data will be loaded from file
        aoi_dir: Directory where AoI JSON dumps are stored
        
    Returns:
        Analysis report
    """
    analyser = AOIAnalyser(aoi_dir=aoi_dir)
    return analyser.analyse_device(device_mac, data)
