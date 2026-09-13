from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from bleep.core.output import OutputContext

from bleep.core.log import print_and_log, LOG__GENERAL

try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None


def _conn():
    # Access private connection for read-only ops
    return _obs._DB_CONN  # type: ignore[attr-defined]


def _valid_cols() -> list[str]:
    with _obs._db_cursor() as cur:  # type: ignore[attr-defined]
        return [c[1] for c in cur.execute("PRAGMA table_info(devices)")]


def list_devices(fields: list[str] | None = None, status: str | None = None,
                 limit: int = 100, offset: int = 0, name: str | None = None) -> None:
    """List devices with optional field, status, name, and pagination filters."""
    try:
        devices = _obs.get_devices(status=status, limit=limit, offset=offset, name=name)
        _print_device_rows(devices, fields, limit=limit, name=name, status=status)
    except Exception as e:
        print_and_log(f"Error listing devices: {e}")


def _print_device_rows(devices: list[dict], fields: list[str] | None = None,
                       *, limit: int = 100, name: str | None = None,
                       status: str | None = None) -> None:
    """Render an already-fetched device list as a columnar table.

    Extracted from :func:`list_devices` so the terminal renderer is shared by
    the legacy ``list_devices`` entry point and the ``db list`` handler's
    windowed/filtered selection (which fetches once and passes the rows here).
    """
    if not devices:
        filt = []
        if status:
            filt.append(f"status={status}")
        if name:
            filt.append(f"name~{name}")
        if filt:
            print_and_log(f"No devices found matching filter(s): {', '.join(filt)}")
        else:
            print_and_log("No devices found in database")
        return

    cols = fields or ["mac", "name", "first_seen", "last_seen"]
    valid = set(_valid_cols())
    bad = [c for c in cols if c not in valid]
    if bad:
        print_and_log(f"Invalid field(s): {', '.join(bad)} – valid: {', '.join(sorted(valid))}")
        return

    print_and_log("  ".join(c.upper() for c in cols))
    print_and_log("  ".join("-" * len(c) for c in cols))

    for device in devices:
        print_and_log("  ".join(str(device.get(c, "-")) if device.get(c) is not None else "-" for c in cols))

    # F1: when the page is exactly full, more rows may exist beyond this page.
    # RPA-rotating devices can inflate row counts, so make truncation explicit
    # rather than letting a capped list read as "these are all the devices".
    if len(devices) == limit:
        print_and_log(
            f"\n[note] Showing {len(devices)} device(s) (page limit {limit}); "
            f"more may exist — use --limit/--offset to page"
            + ("" if name else ", or --name <substr> to filter by name")
        )


def timeline(mac: str, service_uuid: str = None, char_uuid: str = None, limit: int = 50):
    """Display characteristic value timeline for a device."""
    try:
        history = _obs.get_characteristic_timeline(mac, service_uuid, char_uuid, limit)

        if not history:
            print_and_log(f"No characteristic history found for device {mac}")
            if service_uuid or char_uuid:
                filters = []
                if service_uuid:
                    filters.append(f"service_uuid={service_uuid}")
                if char_uuid:
                    filters.append(f"char_uuid={char_uuid}")
                print_and_log(f"Filters applied: {', '.join(filters)}")
            return

        print_and_log(f"Characteristic value history for {mac}:")
        if service_uuid:
            print_and_log(f"Service UUID filter: {service_uuid}")
        if char_uuid:
            print_and_log(f"Characteristic UUID filter: {char_uuid}")

        print_and_log(f"{'TIMESTAMP':<25} {'SERVICE UUID':<36} {'CHAR UUID':<36} {'VALUE'}")
        print_and_log("-" * 100)

        for entry in history:
            val = entry.get("value")
            if isinstance(val, bytes):
                val = val.hex()
            print_and_log(f"{entry['ts']:<25}  {entry['service_uuid']:<36} {entry['char_uuid']:<36}  {val}")

        print_and_log(f"\nShowing {len(history)} entries (limit: {limit})")
    except Exception as e:
        print_and_log(f"Error retrieving timeline data: {e}")


_SDP_TIMELINE_DIFF_FIELDS = (
    "name",
    "service_version",
    "service_description",
    "profile_descriptors",
    "protocol_descriptors",
    "mas_instance_id",
    "supported_message_types",
    "supported_features",
    "source",
)

_SHORT_UUID_RE = re.compile(r"0[xX]([0-9A-Fa-f]+)$")


def _canon_sdp_uuid(uuid: str | None) -> str | None:
    """Canonicalize an SDP UUID for display and grouping.

    Short 16/32-bit forms are normalized to a lowercase ``0x`` prefix with
    upper-case hex digits (``0X1108`` → ``0x1108``); dashed 128-bit forms are
    upper-cased. This folds legacy rows (stored with an upper-case ``0X``
    prefix) onto the canonical form for display only — stored data is untouched.
    """
    if not uuid:
        return uuid
    m = _SHORT_UUID_RE.match(uuid)
    if m:
        return "0x" + m.group(1).upper()
    return uuid.upper() if "-" in uuid else uuid


def timeline_sdp(mac: str, history: list) -> None:
    """Display Classic SDP record change history, grouped by (uuid, channel).

    Walks the append-only ``sdp_records`` snapshots (oldest-first) and prints,
    for each logical service, the first snapshot then only the fields that
    changed between consecutive snapshots — so an operator sees *what* mutated
    (e.g. a honeypot rotating its service name or handle) and when.
    """
    if not history:
        print_and_log(f"No SDP record history found for device {mac}")
        return

    print_and_log(f"SDP record change history for {mac}:")
    print_and_log("=" * 80)

    groups: dict = {}
    order: list = []
    for snap in history:
        key = (_canon_sdp_uuid(snap.get("uuid")), snap.get("channel"))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(snap)

    for key in order:
        uuid, channel = key
        snaps = groups[key]
        chan_str = f" ch={channel}" if channel is not None else ""
        print_and_log(f"\nService {uuid or '<unknown>'}{chan_str}  ({len(snaps)} snapshot(s))")
        prev = None
        for snap in snaps:
            if prev is None:
                fields = {f: snap.get(f) for f in _SDP_TIMELINE_DIFF_FIELDS if snap.get(f) is not None}
                summary = ", ".join(f"{k}={v}" for k, v in fields.items()) or "(no labelled fields)"
                print_and_log(f"  {snap['ts']}  [initial] handle={snap.get('service_record_handle')}  {summary}")
            else:
                changes = []
                for f in _SDP_TIMELINE_DIFF_FIELDS:
                    if prev.get(f) != snap.get(f):
                        changes.append(f"{f}: {prev.get(f)!r} -> {snap.get(f)!r}")
                if prev.get("service_record_handle") != snap.get("service_record_handle"):
                    changes.append(
                        f"handle: {prev.get('service_record_handle')} -> {snap.get('service_record_handle')}"
                    )
                change_str = "; ".join(changes) if changes else "(handle/formatting only)"
                print_and_log(f"  {snap['ts']}  [changed] {change_str}")
            prev = snap

    print_and_log("\n" + "=" * 80)


def _binary_to_hex(obj: Any) -> Any:
    """Recursively convert bytes to hex strings for JSON serialization."""
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, dict):
        return {k: _binary_to_hex(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_binary_to_hex(i) for i in obj]
    return obj


def _attach_adv_dissection(device_info: dict) -> None:
    """Enrich a ``get_device_detail`` dict with an ``adv_dissection`` block (G-7.5).

    Prefer the latest ``adv_reports.decoded.adv_dissection`` (or rebuild from its
    multi-key manufacturer/service maps) so rotating multi-CID payloads are not
    collapsed to the single devices-row manufacturer pair. Fall back to
    ``dissect_persisted_record`` on the device row for historical records.
    No-op when no advertisement data exists; never raises.
    """
    try:
        from bleep.analysis.adv_dissect import (
            dissect_advertisement,
            dissect_persisted_record,
        )
        from bleep.core import observations as _obs

        mac = None
        if isinstance(device_info.get("device"), dict):
            mac = device_info["device"].get("mac")
        mac = mac or device_info.get("mac")
        if mac:
            try:
                detail = _obs.get_device_detail(mac)
                # export_device_data path already attaches reports; for show we
                # query the latest row directly when absent.
                reports = detail.get("adv_reports") if isinstance(detail, dict) else None
                if not reports:
                    # Lightweight latest-report fetch without full export.
                    conn = getattr(_obs, "_DB_CONN", None)
                    if conn is not None:
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT decoded FROM adv_reports WHERE mac=? "
                            "ORDER BY rowid DESC LIMIT 1",
                            (mac,),
                        )
                        row = cur.fetchone()
                        if row and row[0]:
                            import json as _json
                            decoded = _json.loads(row[0]) if isinstance(row[0], str) else row[0]
                            if isinstance(decoded, dict):
                                if decoded.get("adv_dissection"):
                                    device_info["adv_dissection"] = decoded["adv_dissection"]
                                    return
                                mfr = {}
                                for k, v in (decoded.get("manufacturer_data") or {}).items():
                                    try:
                                        mfr[int(k)] = bytes.fromhex(v) if isinstance(v, str) else bytes(v)
                                    except (TypeError, ValueError):
                                        continue
                                svc = {}
                                for k, v in (decoded.get("service_data") or {}).items():
                                    try:
                                        svc[str(k)] = bytes.fromhex(v) if isinstance(v, str) else bytes(v)
                                    except (TypeError, ValueError):
                                        continue
                                uuids = decoded.get("uuids") or []
                                if mfr or svc or uuids:
                                    device_info["adv_dissection"] = dissect_advertisement(
                                        manufacturer_data=mfr or None,
                                        service_data=svc or None,
                                        service_uuids=uuids or None,
                                    )
                                    return
            except Exception:  # noqa: BLE001
                pass

        dissection = dissect_persisted_record(device_info)
        if dissection:
            device_info["adv_dissection"] = dissection
    except Exception:  # noqa: BLE001 - display enrichment must not break show
        pass


def _render_adv_dissection_text(dissection: dict) -> list[str]:
    """Render an ``adv_dissection`` block as indented plain-text CLI lines.

    Mirrors the AoI markdown renderer (``aoi_analyser._render_adv_dissection``)
    but in ``show_device``'s indented ``  Section:`` style. Every entry keeps its
    raw hex *and* printable ASCII so no captured advertisement byte is dropped.
    """
    summary = dissection.get("summary", {})
    vendors = summary.get("vendors") or []
    protocols = summary.get("protocols") or []
    mfr = dissection.get("manufacturer_data", [])
    svc = dissection.get("service_data", [])
    adv = dissection.get("advertising_data", [])
    if not (vendors or protocols or mfr or svc or adv):
        return []

    lines: list[str] = ["\n  Advertisement Dissection:"]
    if vendors:
        lines.append(f"    Vendors  : {', '.join(vendors)}")
    if protocols:
        lines.append(f"    Protocols: {', '.join(protocols)}")

    for e in mfr:
        company = e.get("company") or "Unknown vendor"
        lines.append(f"    Manufacturer {e['company_id_hex']} ({company}):")
        if e.get("vendor_hints"):
            lines.append(f"      hints  : {', '.join(e['vendor_hints'])}")
        lines.append(f"      hex    : {e['raw_hex']}")
        lines.append(f"      ascii  : {e['ascii']}")
        if e.get("decoded"):
            lines.append(f"      decoded: {json.dumps(e['decoded'], ensure_ascii=False)}")

    for e in svc:
        title = e.get("name") or e.get("protocol") or e["uuid"]
        lines.append(f"    Service Data {e['uuid']} ({title}):")
        if e.get("protocol"):
            lines.append(f"      protocol: {e['protocol']}")
        if e.get("vendor_hints"):
            lines.append(f"      hints   : {', '.join(e['vendor_hints'])}")
        lines.append(f"      hex     : {e['raw_hex']}")
        lines.append(f"      ascii   : {e['ascii']}")
        if e.get("decoded"):
            lines.append(f"      decoded : {json.dumps(e['decoded'], ensure_ascii=False)}")

    if adv:
        lines.append("    Advertising Data:")
        for e in adv:
            name = e.get("name") or "Unknown"
            lines.append(f"      {e['ad_type_hex']} ({name}): hex {e['raw_hex']} / ascii {e['ascii']}")

    return lines


def show_device(mac: str, full: bool = False) -> None:
    """Show detailed information about a device.

    When *full* is True the complete ``get_device_detail()`` dict is emitted as
    formatted JSON.  Otherwise a human-readable summary with expanded
    characteristic, classic-service and SDP-record sections is printed.
    """
    try:
        device_info = _obs.get_device_detail(mac)

        if not device_info.get('device'):
            print_and_log(f"Device {mac} not found in database")
            return

        # G-7.5: attach the attributed, lossless advertisement dissection so it
        # is surfaced in both the --full JSON dump and the human summary below.
        _attach_adv_dissection(device_info)

        if full:
            print_and_log(json.dumps(_binary_to_hex(device_info), indent=2, ensure_ascii=False))
            return

        dev = device_info['device']
        print_and_log(f"Device: {dev.get('name', 'Unknown')} ({dev.get('mac', mac)})")
        print_and_log(f"  First seen : {dev.get('first_seen', '-')}")
        print_and_log(f"  Last seen  : {dev.get('last_seen', '-')}")
        if dev.get('device_type'):
            print_and_log(f"  Type       : {dev['device_type']}")
        if dev.get('rssi') is not None:
            print_and_log(f"  RSSI       : {dev['rssi']} dBm")

        # Names are frequently stored NULL during enumeration; resolve on display
        # via the canonical translator (16/32/128-bit aware, None-safe).
        from bleep.bt_ref.uuid_translator import get_uuid_name

        def _name_for(row, *keys):
            for k in keys:
                v = row.get(k)
                if v:
                    return v
            for k in ("uuid", "service_uuid"):
                u = row.get(k)
                if u:
                    return get_uuid_name(u)
            return ""

        services = device_info.get('services', [])
        if services:
            print_and_log(f"\n  Services ({len(services)}):")
            for svc in services:
                print_and_log(f"    {svc.get('uuid', '?')}  {_name_for(svc, 'name')}")

        chars = device_info.get('characteristics', [])
        if chars:
            print_and_log(f"\n  Characteristics ({len(chars)}):")
            for ch in chars:
                props = ch.get('properties', '')
                has_val = 'yes' if ch.get('value') else 'no'
                print_and_log(f"    {ch.get('uuid', '?')}  {_name_for(ch, 'name')}  handle={ch.get('handle', '?')}  props={props}  value={has_val}")

        classic = device_info.get('classic_services', [])
        if classic:
            print_and_log(f"\n  Classic Services ({len(classic)}):")
            for cs in classic:
                print_and_log(f"    {cs.get('uuid', '?')}  ch={cs.get('channel', '?')}  {_name_for(cs, 'name')}")

        sdp = device_info.get('sdp_records', [])
        if sdp:
            # Rows arrive newest-first (get_device_detail: ORDER BY ts DESC). A device
            # that rotates its SDP service-record handle defeats the (mac, handle)
            # upsert dedup and accumulates stale snapshots — collapse to the most
            # recent record per (uuid, channel) for display.
            seen: set = set()
            latest = []
            for rec in sdp:
                key = (rec.get('uuid') or rec.get('service_uuid'), rec.get('channel'))
                if key in seen:
                    continue
                seen.add(key)
                latest.append(rec)
            print_and_log(f"\n  SDP Records ({len(latest)}):")
            for rec in latest:
                uuid = rec.get('uuid') or rec.get('service_uuid') or '?'
                print_and_log(f"    {uuid}  {_name_for(rec, 'name', 'service_name')}  ch={rec.get('channel', '?')}")

        # G-7.5: attributed, lossless advertisement dissection (beacon/vendor
        # payloads, decoded protocols, raw hex + ASCII).
        dissection = device_info.get('adv_dissection')
        if dissection:
            for line in _render_adv_dissection_text(dissection):
                print_and_log(line)

    except Exception as e:
        print_and_log(f"Error retrieving device details: {e}")


def export_device(mac: str, out: Path | None, char_limit: int = 500,
                  adv_limit: int = 100) -> None:
    """Export all data for a device to JSON (DB-5: ``0`` limit = full history)."""
    try:
        data = _obs.export_device_data(mac, char_limit=char_limit, adv_limit=adv_limit)

        if not data.get('device'):
            print_and_log(f"Device {mac} not found in database")
            return

        text = json.dumps(data, indent=2, ensure_ascii=False)

        if out:
            out.write_text(text, encoding="utf-8")
            print_and_log(f"Exported device data to {out}")
        else:
            print_and_log(text)
    except Exception as e:
        print_and_log(f"Error exporting device data: {e}")


def _resolve_window(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Resolve ``--since/--until/--tz`` into naive-UTC ISO bounds (DB-1/DB-6).

    Returns ``(since_iso, until_iso)`` where ``until_iso`` is the exclusive
    upper bound (inclusive end date + 1 day). Either may be ``None`` for an
    open-ended bound. Raises ``ValueError`` on an unparseable date.
    """
    since = getattr(args, "since", None)
    until = getattr(args, "until", None)
    tz = getattr(args, "tz", "UTC") or "UTC"
    if not since and not until:
        return None, None
    from bleep.core.time_utils import local_date_range_to_utc

    try:
        return local_date_range_to_utc(since, until, tz)
    except ValueError as e:
        raise ValueError(f"invalid --since/--until date ({e})") from e


def _target_entry(device: dict) -> dict:
    """Project a device row into an AoI-ingestable target object (DB-3).

    The ``address`` key is what ``bleep.modes.aoi._iter_macs`` consumes; the
    remaining fields seed the observation DB with survey-style metadata.
    """
    return {
        "address": device.get("mac"),
        "name": device.get("name"),
        "device_type": device.get("device_type"),
        "first_seen": device.get("first_seen"),
        "last_seen": device.get("last_seen"),
    }


def _write_target_list(devices: list[dict], path: Path, output) -> int:
    """Write *devices* as a JSON target list to *path* (DB-3)."""
    targets = [_target_entry(d) for d in devices if d.get("mac")]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(targets, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print_and_log(f"Error writing target list to {path}: {e}", LOG__GENERAL)
        return 1
    if output.is_json or output.is_quiet:
        output.emit_result({"target_list": str(path), "count": len(targets)})
    else:
        print_and_log(f"[+] Wrote {len(targets)} target(s) to {path}", LOG__GENERAL)
    return 0


def _identity_summary(devices: list[dict], strategy: str) -> dict:
    """Collapse *devices* into identity clusters with provenance (DB-4)."""
    from bleep.analysis.identity import collapse_identities

    return collapse_identities(devices, strategy=strategy)


def _emit_identity_clusters(devices: list[dict], strategy: str, output) -> int:
    """Render heuristic identity clusters for ``db list --group-identity`` (DB-4)."""
    summary = _identity_summary(devices, strategy)
    if output.is_json or output.is_quiet:
        output.emit_result(summary)
        return 0

    clusters = summary["clusters"]
    print_and_log(
        f"Identity clusters (strategy={summary['strategy']}, method=heuristic, no IRK): "
        f"raw {summary['raw_count']} -> collapsed {summary['collapsed_count']} "
        f"({summary['multi_member_count']} multi-member)",
        LOG__GENERAL,
    )
    print_and_log("-" * 80, LOG__GENERAL)
    for c in clusters:
        span = f"{(c['first_seen'] or '?')[:19]} .. {(c['last_seen'] or '?')[:19]}"
        types = ",".join(c["device_types"]) or "-"
        head = f"[{c['size']:>4}x] {c['identity']}  ({types})  {span}"
        if c["ungrouped"]:
            head += "  [no stable anchor]"
        print_and_log(head, LOG__GENERAL)
        if c["size"] > 1:
            preview = ", ".join(c["members"][:6])
            more = "" if c["size"] <= 6 else f", +{c['size'] - 6} more"
            print_and_log(f"        {preview}{more}", LOG__GENERAL)
    return 0


def _full_device_record(mac: str) -> dict:
    """Return the complete collected record for *mac* (DB-8).

    Reuses ``export_device_data`` with the DB-5 uncapped path (``char_limit=0``,
    ``adv_limit=0``) so *all* characteristic history and advertisement reports are
    included, then attaches the same attributed ``adv_dissection`` block that
    ``db show`` surfaces. Best-effort — dissection never blocks the export.
    """
    data = _obs.export_device_data(mac, char_limit=0, adv_limit=0)
    try:
        detail = _obs.get_device_detail(mac)
        _attach_adv_dissection(detail)
        if detail.get("adv_dissection"):
            data["adv_dissection"] = detail["adv_dissection"]
    except Exception:  # noqa: BLE001 - enrichment must never break the audit
        pass
    return data


def _name_summary(detail: dict) -> dict:
    """Compact high-level view of a device's collected data (DB-8).

    Derived from a ``get_device_detail`` dict with ``adv_dissection`` attached —
    advertisement vendors/protocols plus GATT/SDP/classic surface counts and the
    exposed SDP profile names.
    """
    dev = detail.get("device") or {}
    diss = detail.get("adv_dissection") or {}
    summ = diss.get("summary") or {}
    sdp = detail.get("sdp_records") or []
    profiles = sorted({r.get("name") for r in sdp if r.get("name")})
    return {
        "mac": dev.get("mac"),
        "device_type": dev.get("device_type"),
        "rssi": dev.get("rssi"),
        "tx_power": dev.get("tx_power"),
        "companies": summ.get("vendors") or [],
        "protocols": summ.get("protocols") or [],
        "gatt_services": len(detail.get("services") or []),
        "classic_services": len(detail.get("classic_services") or []),
        "sdp_records": len(sdp),
        "sdp_profiles": profiles,
    }


def _name_audit(devices: list[dict], args: argparse.Namespace) -> dict:
    """Classify *devices* by name into the four DB-8 buckets with detail.

    Buckets (see :func:`bleep.analysis.identity.classify_name`):

    * ``placeholder`` — MAC-shaped name == own MAC (BlueZ default alias); a sample
      of ``--name-sample`` rows is retained.
    * ``real`` — genuine names; grouped by name, each group carrying a compact
      ``summary`` and — for the first ``--name-detail-limit`` groups (0 = all) —
      the **full collected record** per member (``devices``).
    * ``empty`` — NULL/blank names; full per-device detail.
    * ``foreign_mac`` — MAC-shaped name != own MAC (anomaly); full per-device
      detail. Always surfaced by the callers.
    """
    from bleep.analysis.identity import classify_name, normalize_mac

    sample_n = max(0, getattr(args, "name_sample", 10) or 0)
    detail_limit = getattr(args, "name_detail_limit", 50)
    if detail_limit is None:
        detail_limit = 50

    counts = {"placeholder": 0, "real": 0, "empty": 0, "foreign_mac": 0}
    real_groups: dict[str, dict] = {}
    empty_rows: list[dict] = []
    foreign_rows: list[dict] = []
    placeholder_sample: list[dict] = []

    for d in devices:
        mac = d.get("mac")
        name = d.get("name")
        cls = classify_name(name, mac)
        counts[cls] += 1

        if cls == "placeholder":
            if len(placeholder_sample) < sample_n:
                placeholder_sample.append({
                    "mac": mac, "name": name,
                    "first_seen": d.get("first_seen"), "last_seen": d.get("last_seen"),
                })
        elif cls == "empty":
            empty_rows.append({
                "mac": mac, "device_type": d.get("device_type"),
                "first_seen": d.get("first_seen"), "last_seen": d.get("last_seen"),
                "rssi": d.get("rssi"),
            })
        elif cls == "foreign_mac":
            foreign_rows.append({
                "mac": mac, "name": name, "name_normalized": normalize_mac(name),
                "device_type": d.get("device_type"),
                "first_seen": d.get("first_seen"), "last_seen": d.get("last_seen"),
                "reason": "MAC-shaped name does not match device address",
            })
        else:  # real
            g = real_groups.get(name)
            if g is None:
                g = {
                    "name": name, "macs": [], "device_count": 0,
                    "first_seen": d.get("first_seen"), "last_seen": d.get("last_seen"),
                    "device_types": set(), "_rep": d,
                }
                real_groups[name] = g
            g["macs"].append(mac)
            g["device_count"] += 1
            if d.get("device_type"):
                g["device_types"].add(d["device_type"])
            fs, ls = d.get("first_seen"), d.get("last_seen")
            if fs and (g["first_seen"] is None or fs < g["first_seen"]):
                g["first_seen"] = fs
            if ls and (g["last_seen"] is None or ls > g["last_seen"]):
                g["last_seen"] = ls
            # Representative = latest-seen member (for the compact summary).
            if ls and (g["_rep"].get("last_seen") is None or ls > g["_rep"]["last_seen"]):
                g["_rep"] = d

    ordered = sorted(real_groups.values(),
                     key=lambda g: (-g["device_count"], str(g["name"])))

    enrich_all = (detail_limit == 0)
    real_out: list[dict] = []
    for idx, g in enumerate(ordered):
        rep_mac = g["_rep"].get("mac")
        try:
            rep_detail = _obs.get_device_detail(rep_mac)
            _attach_adv_dissection(rep_detail)
            summary = _name_summary(rep_detail)
        except Exception:  # noqa: BLE001 - summary is best-effort
            summary = {"mac": rep_mac}
        entry = {
            "name": g["name"], "device_count": g["device_count"], "macs": g["macs"],
            "first_seen": g["first_seen"], "last_seen": g["last_seen"],
            "device_types": sorted(g["device_types"]), "summary": summary,
        }
        if enrich_all or idx < detail_limit:
            entry["devices"] = [_full_device_record(m) for m in g["macs"]]
        real_out.append(entry)

    truncated = (not enrich_all) and (len(ordered) > detail_limit)

    return {
        "counts": {**counts, "total": len(devices)},
        "real": real_out,
        "empty": empty_rows,
        "foreign_mac": foreign_rows,
        "placeholder_sample": placeholder_sample,
        "placeholder_total": counts["placeholder"],
        "enrich_truncated": truncated,
        "enrich_limit": detail_limit,
        "method": "heuristic-name-grouping",
    }


def _ts(value) -> str:
    return (value or "?")[:19] if isinstance(value, str) else "?"


def _print_name_audit(audit: dict, output) -> None:
    """Render a name audit for the terminal (``db list --name-audit``)."""
    c = audit["counts"]
    print_and_log(f"Name audit over {c['total']} device(s) in selection:", LOG__GENERAL)
    print_and_log(f"  placeholder (name == own MAC) ......... {c['placeholder']}", LOG__GENERAL)
    print_and_log(f"  real (non-MAC names) ................. {c['real']}", LOG__GENERAL)
    print_and_log(f"  empty (NULL/blank) .................. {c['empty']}", LOG__GENERAL)
    print_and_log(f"  foreign_mac (name != own MAC) ....... {c['foreign_mac']}   <-- anomaly", LOG__GENERAL)

    anomalies = audit["foreign_mac"]
    if anomalies:
        print_and_log("", LOG__GENERAL)
        print_and_log(
            f"[!] ANOMALY: {len(anomalies)} device(s) advertise a MAC-shaped name that "
            f"does NOT match their own address:", LOG__GENERAL)
        for a in anomalies:
            print_and_log(
                f"      device={a['mac']}  name={a['name']}  (norm {a['name_normalized']})  "
                f"type={a.get('device_type') or '-'}  {_ts(a['first_seen'])} .. {_ts(a['last_seen'])}",
                LOG__GENERAL)

    real = audit["real"]
    print_and_log("", LOG__GENERAL)
    print_and_log(f"Real (interesting) names — {len(real)} distinct:", LOG__GENERAL)
    for entry in real:
        s = entry.get("summary") or {}
        types = ",".join(entry["device_types"]) or "-"
        print_and_log(
            f"  {entry['name']}    {entry['device_count']} dev  ({types})  "
            f"{_ts(entry['first_seen'])} .. {_ts(entry['last_seen'])}", LOG__GENERAL)
        companies = ", ".join(s.get("companies") or []) or "-"
        protocols = ", ".join(s.get("protocols") or []) or "-"
        print_and_log(
            f"      adv: companies=[{companies}]  protocols=[{protocols}]  "
            f"tx_power={s.get('tx_power')}  rssi={s.get('rssi')}", LOG__GENERAL)
        sdp_profiles = ", ".join(s.get("sdp_profiles") or []) or "-"
        print_and_log(
            f"      gatt_services={s.get('gatt_services', 0)}  "
            f"classic_services={s.get('classic_services', 0)}  "
            f"sdp={s.get('sdp_records', 0)} [{sdp_profiles}]", LOG__GENERAL)
        # Answer #3: full collected data for each named device (human dump).
        if "devices" in entry:
            for mac in entry["macs"]:
                print_and_log(f"      --- full record for {mac} ---", LOG__GENERAL)
                show_device(mac)
    if audit["enrich_truncated"]:
        print_and_log(
            f"  (full records shown for first {audit['enrich_limit']} name(s); "
            f"use --name-detail-limit 0 for all)", LOG__GENERAL)

    empty = audit["empty"]
    if empty:
        print_and_log("", LOG__GENERAL)
        print_and_log(f"Empty / unnamed — {len(empty)} device(s):", LOG__GENERAL)
        for e in empty:
            print_and_log(
                f"  {e['mac']}  type={e.get('device_type') or '-'}  rssi={e.get('rssi')}  "
                f"{_ts(e['first_seen'])} .. {_ts(e['last_seen'])}", LOG__GENERAL)

    sample = audit["placeholder_sample"]
    if audit["placeholder_total"]:
        print_and_log("", LOG__GENERAL)
        print_and_log(
            f"Default-alias sample (name == own MAC) — {len(sample)} of "
            f"{audit['placeholder_total']}:", LOG__GENERAL)
        for p in sample:
            print_and_log(
                f"  {p['mac']}  ({p['name']})  {_ts(p['first_seen'])} .. {_ts(p['last_seen'])}",
                LOG__GENERAL)


def _render_name_audit_md(audit: dict) -> str:
    """Render a name audit as a Markdown ``## Name Audit`` section (for reports)."""
    c = audit["counts"]
    lines = [
        "## Name Audit",
        "",
        "| Bucket | Count |",
        "|---|---|",
        f"| placeholder (name == own MAC) | {c['placeholder']} |",
        f"| real (non-MAC names) | {c['real']} |",
        f"| empty (NULL/blank) | {c['empty']} |",
        f"| foreign_mac (name != own MAC) — anomaly | {c['foreign_mac']} |",
        f"| **total** | {c['total']} |",
        "",
        "### Anomalies — MAC-shaped names that do not match the device address",
    ]
    if audit["foreign_mac"]:
        for a in audit["foreign_mac"]:
            lines.append(
                f"- `{a['mac']}` name=`{a['name']}` (norm `{a['name_normalized']}`) "
                f"type={a.get('device_type') or '-'} seen {_ts(a['first_seen'])} .. {_ts(a['last_seen'])}")
    else:
        lines.append("- None.")

    lines += ["", f"### Real (interesting) names — {len(audit['real'])} distinct"]
    for entry in audit["real"]:
        s = entry.get("summary") or {}
        types = ", ".join(entry["device_types"]) or "-"
        lines.append(
            f"- **{entry['name']}** — {entry['device_count']} device(s) ({types}); "
            f"seen {_ts(entry['first_seen'])} .. {_ts(entry['last_seen'])}")
        companies = ", ".join(s.get("companies") or []) or "-"
        protocols = ", ".join(s.get("protocols") or []) or "-"
        sdp_profiles = ", ".join(s.get("sdp_profiles") or []) or "-"
        lines.append(
            f"  - adv: companies=[{companies}] protocols=[{protocols}] "
            f"tx_power={s.get('tx_power')} rssi={s.get('rssi')}")
        lines.append(
            f"  - gatt_services={s.get('gatt_services', 0)} "
            f"classic_services={s.get('classic_services', 0)} "
            f"sdp={s.get('sdp_records', 0)} [{sdp_profiles}]")
        lines.append(f"  - MACs: {', '.join(entry['macs'])}")
    if audit["enrich_truncated"]:
        lines.append(
            f"\n_Full per-device records available via `--json` (name_audit.real[].devices) "
            f"or `db export`; summaries above cover the first {audit['enrich_limit']} name(s)._")

    if audit["empty"]:
        lines += ["", f"### Empty / unnamed — {len(audit['empty'])} device(s)"]
        for e in audit["empty"]:
            lines.append(
                f"- `{e['mac']}` type={e.get('device_type') or '-'} rssi={e.get('rssi')} "
                f"seen {_ts(e['first_seen'])} .. {_ts(e['last_seen'])}")

    if audit["placeholder_total"]:
        lines += ["", f"### Default-alias sample (name == own MAC) — "
                       f"{len(audit['placeholder_sample'])} of {audit['placeholder_total']}"]
        for p in audit["placeholder_sample"]:
            lines.append(f"- `{p['mac']}` ({p['name']}) seen {_ts(p['first_seen'])} .. {_ts(p['last_seen'])}")

    return "\n".join(lines)


def _emit_name_audit(devices: list[dict], args: argparse.Namespace, output) -> int:
    """``db list --name-audit`` — classify names and render/emit the audit (DB-8)."""
    audit = _name_audit(devices, args)
    if output.is_json or output.is_quiet:
        output.emit_result(audit)
        return 0
    _print_name_audit(audit, output)
    return 0


def _lcp_hex(hexes: list[str]) -> str:
    """Longest common (whole-byte) prefix across hex strings — the shared pattern."""
    present = [h for h in hexes if h]
    if not present:
        return ""
    lo, hi = min(present), max(present)
    i = 0
    while i < len(lo) and i < len(hi) and lo[i] == hi[i]:
        i += 1
    return lo[: i - (i % 2)]  # trim to whole bytes


def _summarize_payloads(meta: dict, payloads, devices: set) -> dict:
    """Fold a payload Counter + device set into a hex-comparison summary (DB-9)."""
    hexes = list(payloads)
    return {
        **meta,
        "device_count": len(devices),
        "unique_payloads": len(hexes),
        "common_prefix": _lcp_hex(hexes),
        "top_payloads": [{"hex": h, "count": c} for h, c in payloads.most_common(5)],
        # Identical payload seen across >=2 devices → possible static/identity leak.
        "repeated_payloads": [{"hex": h, "count": c}
                              for h, c in payloads.most_common() if c >= 2][:10],
    }


def _classify_address(mac: str, addr_type) -> tuple[str, str | None]:
    """Return ``(kind, random_subtype)`` for an address (DB-9).

    ``kind`` ∈ {``public``, ``random``, ``unknown``}. For random addresses the
    subtype is derived from the two most-significant bits of the first octet:
    ``11`` = static, ``01`` = rpa (resolvable), ``00`` = nrpa (non-resolvable).
    """
    at = (addr_type or "").strip().lower()
    if at == "public":
        return "public", None
    if at == "random":
        try:
            top = int(mac[:2], 16) >> 6
        except (ValueError, TypeError, IndexError):
            return "random", "unknown"
        return "random", {0b11: "static", 0b01: "rpa", 0b00: "nrpa"}.get(top, "reserved")
    return "unknown", None


def _recon_oui(devices: list[dict]) -> dict:
    """OUI + address-type breakdown (DB-9).

    Public addresses are tallied by 24-bit OUI and vendor-decoded (graceful
    unknown); random addresses are sub-classified (RPA/static/NRPA) and *not*
    vendor-decoded — their OUI is a privacy address, not a manufacturer.
    """
    from collections import Counter
    from bleep.ble_ops.common.conversion import resolve_oui

    public = Counter()
    random_sub = Counter()
    unknown_addr = 0
    for d in devices:
        mac = d.get("mac") or ""
        kind, sub = _classify_address(mac, d.get("addr_type"))
        if kind == "public":
            public[mac[:8]] += 1
        elif kind == "random":
            random_sub[sub] += 1
        else:
            unknown_addr += 1

    ouis = [{"oui": oui, "count": n, "vendor": resolve_oui(oui)}
            for oui, n in public.most_common()]
    return {
        "public": {"distinct": len(public), "total": sum(public.values()), "ouis": ouis},
        "random": {
            "total": sum(random_sub.values()),
            "rpa": random_sub.get("rpa", 0),
            "static": random_sub.get("static", 0),
            "nrpa": random_sub.get("nrpa", 0),
            "reserved": random_sub.get("reserved", 0),
            "unknown": random_sub.get("unknown", 0),
        },
        "unknown_addr_type": unknown_addr,
    }


def _recon_adv(devices: list[dict], macs: list[str], include_chars: bool) -> dict:
    """Pattern/decode analysis across all collected hex payloads (DB-9).

    Reuses ``dissect_persisted_record`` (the single decode source shared with
    ``db show``) to aggregate manufacturer data (grouped by company id), service
    data (grouped by UUID) and advertising-data AD structures over the selection.
    With *include_chars*, also folds in characteristic-value hex grouped by
    characteristic UUID (decoded via ``decode_characteristic_value``).
    """
    from collections import Counter
    from bleep.analysis.adv_dissect import dissect_persisted_record

    mfr: dict = {}
    svc: dict = {}
    ad_types = Counter()
    ad_names: dict = {}

    for d in devices:
        try:
            diss = dissect_persisted_record(d)
        except Exception:  # noqa: BLE001
            diss = None
        if not diss:
            continue
        mac = d.get("mac")
        for e in diss.get("manufacturer_data") or []:
            cid = e.get("company_id")
            g = mfr.setdefault(cid, {
                "meta": {"company_id": cid, "company_id_hex": e.get("company_id_hex"),
                         "company": e.get("company"), "decoded": None, "vendor_hints": set()},
                "payloads": Counter(), "devices": set()})
            g["payloads"][e.get("raw_hex") or ""] += 1
            g["devices"].add(mac)
            if not g["meta"]["decoded"] and e.get("decoded"):
                g["meta"]["decoded"] = e["decoded"]
            for h in e.get("vendor_hints") or []:
                g["meta"]["vendor_hints"].add(h)
        for e in diss.get("service_data") or []:
            uuid = e.get("uuid")
            g = svc.setdefault(uuid, {
                "meta": {"uuid": uuid, "name": e.get("name"), "protocol": e.get("protocol"),
                         "decoded": None},
                "payloads": Counter(), "devices": set()})
            g["payloads"][e.get("raw_hex") or ""] += 1
            g["devices"].add(mac)
            if not g["meta"]["decoded"] and e.get("decoded"):
                g["meta"]["decoded"] = e["decoded"]
        for e in diss.get("advertising_data") or []:
            t = e.get("ad_type_hex")
            ad_types[t] += 1
            ad_names[t] = e.get("name")

    def _finalize(groups: dict) -> list:
        out = []
        for g in groups.values():
            meta = dict(g["meta"])
            if isinstance(meta.get("vendor_hints"), set):
                meta["vendor_hints"] = sorted(meta["vendor_hints"])
            out.append(_summarize_payloads(meta, g["payloads"], g["devices"]))
        out.sort(key=lambda x: -x["device_count"])
        return out

    result = {
        "manufacturer": _finalize(mfr),
        "service": _finalize(svc),
        "ad_structures": [{"ad_type": t, "name": ad_names.get(t), "count": n}
                          for t, n in ad_types.most_common()],
    }

    if include_chars:
        chars: dict = {}
        try:
            from bleep.ble_ops.common.gatt_profile_decode import decode_characteristic_value
        except Exception:  # noqa: BLE001
            decode_characteristic_value = None
        for r in _obs.get_characteristic_values(macs):
            cu = r.get("char_uuid")
            g = chars.setdefault(cu, {"meta": {"char_uuid": cu, "service_uuid": r.get("service_uuid"),
                                               "decoded": None},
                                      "payloads": Counter(), "devices": set()})
            hx = r.get("value_hex") or ""
            g["payloads"][hx] += 1
            g["devices"].add(r.get("mac"))
            if decode_characteristic_value and not g["meta"]["decoded"] and hx:
                try:
                    dec = decode_characteristic_value(cu, bytes.fromhex(hx))
                    if dec:
                        g["meta"]["decoded"] = dec
                except Exception:  # noqa: BLE001
                    pass
        result["characteristics"] = _finalize(chars)

    return result


def _recon_analytics(devices: list[dict], macs: list[str], *, include_chars: bool = False) -> dict:
    """Umbrella reconnaissance analytics over the selection (DB-9).

    Composed of modular per-analytic builders (SDP inventory / OUI / advertisement
    hex analysis) so individual analytics can later be exposed behind granular
    flags without refactoring. Read-only.
    """
    return {
        "device_count": len(devices),
        "detail": include_chars,
        "sdp_inventory": _obs.get_sdp_inventory(macs),
        "oui": _recon_oui(devices),
        "advertisement": _recon_adv(devices, macs, include_chars),
    }


# Consistent top-N cap applied to the explodable recon inventories (OUI / SDP).
# The full, uncapped set always remains in the JSON ``recon`` block.
_RECON_TOP_N = 50
_RECON_JSON_NOTE = "(full set in the JSON `recon` block)"


def _n(value) -> str:
    """Format an integer count with thousands separators for readability."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _render_payload_group_md(g: dict, label: str) -> list[str]:
    """Render one manufacturer/service/characteristic hex group as markdown bullets.

    Primary line follows the unified ``<unique entry> : <count>`` convention; the
    richer pattern/decode detail is demoted to sub-bullets so the section scans as
    an inventory rather than dense prose.
    """
    lines = [f"- **{label}** : {_n(g['device_count'])} device(s)"]
    detail = f"unique payload(s): {_n(g['unique_payloads'])}"
    if g.get("common_prefix"):
        detail += f" · common-prefix `{g['common_prefix']}`"
    lines.append(f"  - {detail}")
    if g.get("decoded"):
        lines.append(f"  - decoded: `{json.dumps(g['decoded'], ensure_ascii=False)}`")
    if g.get("vendor_hints"):
        lines.append(f"  - vendor hints: {', '.join(g['vendor_hints'])}")
    for p in g.get("repeated_payloads", []):
        lines.append(f"  - [!] repeated `{p['hex']}` ×{_n(p['count'])} (possible static/identity leak)")
    return lines


def _render_recon_md(recon: dict, *, as_table: bool = True) -> str:
    """Render the top-level ``## Reconnaissance Analytics`` report section (DB-9).

    All count-bearing inventories follow the unified ``<unique entry> : <count>``
    notation. The explodable SDP and OUI inventories render as markdown tables by
    default for scan-ability; pass ``as_table=False`` (``--report-bullets``) for
    the bullet form. Both are capped at ``_RECON_TOP_N`` with a pointer to the
    complete JSON set.
    """
    from bleep.ble_ops.common.conversion import format_uuid_display

    lines = ["## Reconnaissance Analytics", "",
             f"Aggregated across {_n(recon['device_count'])} device(s) in the report selection.", ""]

    sdp = recon["sdp_inventory"]
    lines.append(f"### SDP Inventory (aggregate) — {_n(len(sdp))} unique item(s)")
    if not sdp:
        lines.append("- None.")
    else:
        shown = sdp[:_RECON_TOP_N]
        if as_table:
            lines.append("")
            lines.append("| Service | UUID | Devices |")
            lines.append("|---------|------|---------|")
            for e in shown:
                lines.append(
                    f"| {e['name']} | `{format_uuid_display(e['uuid'])}` | {_n(e['device_count'])} |")
        else:
            for e in shown:
                lines.append(f"- {e['name']} ({format_uuid_display(e['uuid'])}) : {_n(e['device_count'])}")
        if len(sdp) > _RECON_TOP_N:
            lines.append(f"- … {_n(len(sdp) - _RECON_TOP_N)} more item(s) {_RECON_JSON_NOTE}")
    lines.append("")

    oui = recon["oui"]
    pub = oui["public"]
    rnd = oui["random"]
    lines.append("### OUI / Address-Type Breakdown")
    lines.append(f"Public ({_n(pub['total'])} device(s), {_n(pub['distinct'])} distinct OUI(s); OUI = vendor):")
    if not pub["ouis"]:
        lines.append("- None.")
    else:
        shown = pub["ouis"][:_RECON_TOP_N]
        if as_table:
            lines.append("")
            lines.append("| Vendor | OUI | Count |")
            lines.append("|--------|-----|-------|")
            for o in shown:
                lines.append(f"| {o['vendor'] or 'unknown'} | `{o['oui']}` | {_n(o['count'])} |")
        else:
            for o in shown:
                lines.append(f"- {o['vendor'] or 'unknown'} ({o['oui']}) : {_n(o['count'])}")
        if len(pub["ouis"]) > _RECON_TOP_N:
            lines.append(f"- … {_n(len(pub['ouis']) - _RECON_TOP_N)} more OUI(s) {_RECON_JSON_NOTE}")
    lines.append(f"Random ({_n(rnd['total'])} device(s); OUI is a privacy address, NOT a vendor):")
    random_rows = [
        ("RPA (resolvable)", rnd["rpa"]),
        ("Static-random", rnd["static"]),
        ("NRPA (non-resolvable)", rnd["nrpa"]),
    ]
    if rnd["reserved"]:
        random_rows.append(("Reserved", rnd["reserved"]))
    if rnd["unknown"]:
        random_rows.append(("Unparsed", rnd["unknown"]))
    for label, count in random_rows:
        lines.append(f"- {label} : {_n(count)}")
    if oui["unknown_addr_type"]:
        lines.append(f"- Unknown addr_type : {_n(oui['unknown_addr_type'])}")
    lines.append("")

    adv = recon["advertisement"]
    lines.append("### Advertisement Data Analysis")
    lines.append("**Manufacturer Data** (by company):")
    if adv["manufacturer"]:
        for g in adv["manufacturer"]:
            label = f"{g.get('company') or 'Unknown vendor'} ({g.get('company_id_hex') or '?'})"
            lines.extend(_render_payload_group_md(g, label))
    else:
        lines.append("- None.")
    lines.append("**Service Data** (by UUID):")
    if adv["service"]:
        for g in adv["service"]:
            uuid_disp = format_uuid_display(g.get("uuid"))
            label = f"{g.get('name') or g.get('protocol') or uuid_disp} ({uuid_disp})"
            lines.extend(_render_payload_group_md(g, label))
    else:
        lines.append("- None.")
    lines.append("**Other AD structures:**")
    if adv["ad_structures"]:
        for a in adv["ad_structures"]:
            lines.append(f"- {a['ad_type']} ({a.get('name') or 'Unknown'}) : {_n(a['count'])}")
    else:
        lines.append("- None.")

    if "characteristics" in adv:
        lines.append("")
        lines.append("### Characteristic Values (detail)")
        if adv["characteristics"]:
            for g in adv["characteristics"]:
                lines.extend(_render_payload_group_md(g, format_uuid_display(g.get("char_uuid") or "?")))
        else:
            lines.append("- None.")

    return "\n".join(lines)


def _run_report(args: argparse.Namespace, output) -> int:
    """``bleep db report`` — batch, date-scoped aggregate report (DB-2).

    Selects the windowed/filtered device set via ``get_devices`` (DB-1) then
    delegates rendering to the existing ``AOIAnalyser.generate_aggregate_report``
    engine, which already loads advert-only devices and separates reachable from
    not-reachable targets. Optionally contrasts raw vs identity-collapsed counts
    (DB-4).
    """
    try:
        since, until = _resolve_window(args)
    except ValueError as e:
        print_and_log(f"Error: {e}", LOG__GENERAL)
        return 1

    status_filter = getattr(args, "status", None)
    name_filter = getattr(args, "name", None)
    seen_basis = getattr(args, "seen_basis", "last") or "last"
    all_in_window = getattr(args, "all_in_window", False)
    report_format = getattr(args, "report_format", "markdown") or "markdown"
    group_strategy = getattr(args, "group_identity", None)
    contrast = getattr(args, "identity_contrast", False)
    if contrast and not group_strategy:
        group_strategy = "name"

    # DB-2 scale guard: an unbounded window can match tens of thousands of RPA
    # rows, so cap unless the operator explicitly opts into the full set.
    default_cap = 500
    if all_in_window:
        limit = 10_000_000
    else:
        limit = getattr(args, "limit", None) or default_cap

    devices = _obs.get_devices(
        status=status_filter, limit=limit, offset=0, name=name_filter,
        since=since, until=until, seen_basis=seen_basis,
    )
    if not devices:
        print_and_log("No devices matched the report window/filters", LOG__GENERAL)
        return 1

    capped = (not all_in_window) and len(devices) == limit
    if capped and not (output.is_json or output.is_quiet):
        print_and_log(
            f"[note] Report capped at {limit} device(s); more match the window. "
            f"Use --all-in-window for the full set, or narrow with --status/--name.",
            LOG__GENERAL,
        )

    addrs = [d["mac"] for d in devices if d.get("mac")]

    try:
        from bleep.analysis.aoi_analyser import AOIAnalyser
    except Exception as e:  # noqa: BLE001
        print_and_log(f"Error: AoI analyser unavailable: {e}", LOG__GENERAL)
        return 1

    report_bullets = getattr(args, "report_bullets", False)

    analyzer = AOIAnalyser(use_db=True)
    try:
        report = analyzer.generate_aggregate_report(
            addrs, format=report_format, bullets=report_bullets)
    except Exception as e:  # noqa: BLE001
        print_and_log(f"Error generating report: {e}", LOG__GENERAL)
        return 1

    contrast_summary = None
    if group_strategy:
        contrast_summary = _identity_summary(devices, group_strategy)

    # DB-8: optional name-bucket audit over the same selection.
    name_audit = _name_audit(devices, args) if getattr(args, "name_audit", False) else None

    # DB-9: optional reconnaissance analytics (SDP inventory / OUI / hex patterns).
    # --recon-detail implies --recon and additionally folds in characteristic hex.
    recon_detail = getattr(args, "recon_detail", False)
    recon = (_recon_analytics(devices, addrs, include_chars=recon_detail)
             if getattr(args, "recon", False) or recon_detail else None)

    if output.is_json or output.is_quiet:
        payload: dict = {
            "format": report_format,
            "device_count": len(addrs),
            "capped": capped,
            "report": report,
        }
        if contrast_summary is not None:
            payload["identity_contrast"] = contrast_summary
        if name_audit is not None:
            payload["name_audit"] = name_audit
        if recon is not None:
            payload["recon"] = recon
        output.emit_result(payload)
        return 0

    # Terminal mode: print the contrast banner (if requested) then persist the
    # report file via the analyser's own reports directory or an explicit --out.
    if contrast_summary is not None:
        print_and_log(
            f"[identity-contrast] raw {contrast_summary['raw_count']} devices -> "
            f"collapsed {contrast_summary['collapsed_count']} identities "
            f"(strategy={contrast_summary['strategy']}, heuristic, no IRK; "
            f"{contrast_summary['multi_member_count']} multi-member)",
            LOG__GENERAL,
        )

    # DB-8: append the name audit to the report body (markdown/text) and always
    # surface any foreign-MAC anomalies on the terminal for operator awareness.
    if name_audit is not None:
        nc = name_audit["counts"]
        print_and_log(
            f"[name-audit] placeholder {nc['placeholder']} / real {nc['real']} / "
            f"empty {nc['empty']} / foreign_mac {nc['foreign_mac']}", LOG__GENERAL)
        for a in name_audit["foreign_mac"]:
            print_and_log(
                f"[!] ANOMALY: device={a['mac']} advertises MAC-shaped name={a['name']} "
                f"(norm {a['name_normalized']}) that does not match its own address", LOG__GENERAL)
        if report_format in ("markdown", "text"):
            report = f"{report}\n\n{_render_name_audit_md(name_audit)}\n"

    # DB-9: append the reconnaissance analytics section and surface repeated
    # payloads (possible static/identity leaks) on the terminal for awareness.
    if recon is not None:
        oui = recon["oui"]
        print_and_log(
            f"[recon] {recon['device_count']} device(s): "
            f"{len(recon['sdp_inventory'])} SDP item(s), "
            f"{oui['public']['distinct']} public OUI(s), "
            f"{oui['random']['total']} random address(es)"
            + (" (+char hex)" if recon['detail'] else ""), LOG__GENERAL)
        for g in recon["advertisement"]["manufacturer"]:
            for p in g.get("repeated_payloads", []):
                print_and_log(
                    f"[!] recon: manufacturer {g.get('company') or g.get('company_id_hex')} "
                    f"payload `{p['hex']}` repeated across {p['count']} device(s) "
                    f"(possible static/identity leak)", LOG__GENERAL)
        if report_format in ("markdown", "text"):
            report = f"{report}\n\n{_render_recon_md(recon, as_table=not report_bullets)}\n"

    out_path = getattr(args, "out", None)
    ext = "json" if report_format == "json" else ("md" if report_format == "markdown" else "txt")
    if out_path:
        report_path = analyzer.save_report(report, filename=str(out_path))
    else:
        import datetime as _dt
        fname = f"db_report_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        report_path = analyzer.save_report(report, filename=fname)
    print_and_log(f"[+] Report ({report_format}, {len(addrs)} device(s)) saved to {report_path}", LOG__GENERAL)
    return 0


def run(args: argparse.Namespace, output: OutputContext | None = None) -> int:
    """Execute db mode with parsed args and optional OutputContext.

    Accepts the Namespace from cli.py's global parser directly (uses
    ``args.action`` for the sub-command). The older ``main(argv)`` wrapper
    remains for backward compatibility.
    """
    from bleep.core.output import OutputContext
    from bleep.core.log import set_output_mode

    if output is None:
        output = OutputContext()

    set_output_mode(output.mode)

    if _obs is None:
        print_and_log("Error: Observation database module unavailable (sqlite3 or dependencies missing)", LOG__GENERAL)
        return 1

    cmd = getattr(args, "action", None) or getattr(args, "cmd", None)

    if cmd == "list":
        fields_raw = getattr(args, "fields", None)
        fields = fields_raw.split(',') if fields_raw else None
        status_filter = getattr(args, "status", None)
        name_filter = getattr(args, "name", None)
        limit = getattr(args, "limit", None) or 100
        offset = getattr(args, "offset", 0) or 0
        seen_basis = getattr(args, "seen_basis", "last") or "last"
        try:
            since, until = _resolve_window(args)
        except ValueError as e:
            print_and_log(f"Error: {e}", LOG__GENERAL)
            return 1
        group_strategy = getattr(args, "group_identity", None)
        export_targets = getattr(args, "export_targets", None)

        devices = _obs.get_devices(
            status=status_filter, limit=limit, offset=offset, name=name_filter,
            since=since, until=until, seen_basis=seen_basis,
        )

        # DB-3: write the (filtered) selection as an AoI-ingestable target list.
        if export_targets:
            return _write_target_list(devices, Path(export_targets), output)

        # DB-4: opt-in heuristic identity collapse (raw view is the default).
        if group_strategy:
            return _emit_identity_clusters(devices, group_strategy, output)

        # DB-8: opt-in name classification/audit (raw table is the default).
        if getattr(args, "name_audit", False):
            return _emit_name_audit(devices, args, output)

        if output.is_json or output.is_quiet:
            if fields:
                devices = [{k: d.get(k) for k in fields} for d in devices]
            output.emit_result(devices or [])
        else:
            _print_device_rows(devices, fields, limit=limit, name=name_filter)
        return 0

    if cmd == "report":
        return _run_report(args, output)

    if cmd == "show":
        full = getattr(args, "full", False)
        if output.is_json or output.is_quiet:
            device_info = _obs.get_device_detail(args.mac)
            if not device_info.get("device"):
                output.emit_result(None)
            else:
                _attach_adv_dissection(device_info)
                output.emit_result(_binary_to_hex(device_info))
        elif full:
            show_device(args.mac, full=True)
        else:
            show_device(args.mac)
        return 0

    if cmd == "export":
        out_path = getattr(args, "out", None)
        if out_path and not isinstance(out_path, Path):
            out_path = Path(out_path)
        char_limit = getattr(args, "max_history", 500)
        adv_limit = getattr(args, "max_adv", 100)
        if output.is_json or output.is_quiet:
            data = _obs.export_device_data(args.mac, char_limit=char_limit, adv_limit=adv_limit)
            if out_path:
                out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            output.emit_result(data)
        else:
            export_device(args.mac, out_path, char_limit=char_limit, adv_limit=adv_limit)
        return 0

    if cmd == "timeline":
        service = getattr(args, "service", None)
        char = getattr(args, "char", None)
        limit = getattr(args, "limit", None) or 50
        if getattr(args, "sdp", False):
            uuid_filter = getattr(args, "uuid", None)
            history = _obs.get_sdp_timeline(args.mac, uuid_filter, limit)
            if output.is_json or output.is_quiet:
                output.emit_result(history or [])
            else:
                timeline_sdp(args.mac, history)
            return 0
        if output.is_json or output.is_quiet:
            history = _obs.get_characteristic_timeline(args.mac, service, char, limit)
            output.emit_result(history or [])
        else:
            timeline(args.mac, service, char, limit)
        return 0

    if cmd == "maintain":
        from bleep.core.observations import maintain_database
        results = maintain_database(vacuum=True, analyze=True)
        if output.is_json or output.is_quiet:
            output.emit_result(results)
        else:
            if results.get("success"):
                for op in results.get("operations", []):
                    print_and_log(f"[+] {op['operation']}: {op.get('duration_seconds', 0):.2f}s", LOG__GENERAL)
                print_and_log("[+] Database maintenance complete", LOG__GENERAL)
            else:
                print_and_log(f"[-] Maintenance failed: {results.get('error', 'unknown')}", LOG__GENERAL)
                return 1
        return 0

    if cmd == "uuids":
        return _run_uuids(args, output)

    print_and_log("Error: No valid sub-command. Use: list, show, export, report, timeline, maintain, uuids", LOG__GENERAL)
    return 1


def _run_uuids(args: argparse.Namespace, output) -> int:
    """`db uuids` — observed-UUID catalogue + optional promotion (Item D)."""
    from bleep.bt_ref.uuid_translator import get_uuid_name

    uuid_filter = getattr(args, "uuid", None)
    promote_name = getattr(args, "promote", None)
    limit = getattr(args, "limit", None) or 200

    # Promotion path: fold an observed (or explicitly named) UUID into the
    # authoritative custom tier so future resolutions return it directly.
    if promote_name:
        if not uuid_filter:
            print_and_log("Error: --promote requires --uuid <UUID>", LOG__GENERAL)
            return 1
        from bleep.bt_ref.custom_uuids import promote_uuid
        key, name = promote_uuid(uuid_filter, promote_name)
        if output.is_json or output.is_quiet:
            output.emit_result({"promoted": {"uuid": key, "name": name}})
        else:
            print_and_log(f"[+] Promoted {key} -> '{name}' into custom UUID names", LOG__GENERAL)
        return 0

    include_seed = getattr(args, "seed", False)
    catalogue = _obs.get_observed_uuid_catalogue(limit=limit, uuid=uuid_filter, include_seed=include_seed)

    if output.is_json or output.is_quiet:
        output.emit_result(catalogue)
        return 0

    if not catalogue:
        print_and_log("No observed UUIDs in database.", LOG__GENERAL)
        return 0

    print(f"\nObserved UUID catalogue ({len(catalogue)} distinct UUID(s)):")
    print("=" * 80)
    for entry in catalogue:
        authoritative = get_uuid_name(entry["uuid"]) or "Unknown"
        print(f"\n{entry['uuid']}  (x{entry['count']})")
        print(f"  Resolved (authoritative): {authoritative}")
        if entry["names"]:
            print(f"  Observed name(s): {', '.join(entry['names'])}")
        print(f"  Sources: {', '.join(entry['sources'])}")
        if entry["first_seen"] or entry["last_seen"]:
            print(f"  Seen: {entry['first_seen']} … {entry['last_seen']}")
        if entry["sample_macs"]:
            print(f"  Sample devices: {', '.join(entry['sample_macs'])}")
    print("\n" + "=" * 80)
    return 0


def main(argv: list[str]) -> int:
    """Run db mode standalone (``python -m bleep.modes.db <action> …``).

    Uses the same canonical argument definitions as the integrated CLI
    (:func:`bleep.cli.parsers.db._add_db_arguments`) so the standalone entry
    point and ``bleep db …`` can never diverge.
    """
    if _obs is None:
        print_and_log("Error: Observation database module unavailable (sqlite3 or dependencies missing)", LOG__GENERAL)
        return 1

    from bleep.cli.parsers.db import _add_db_arguments

    p = argparse.ArgumentParser("bleep db", description="BLEEP observation DB utilities")
    _add_db_arguments(p)
    args = p.parse_args(argv)
    return run(args)
