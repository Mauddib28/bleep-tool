"""Device CRUD operations for the BLEEP observation database."""
from __future__ import annotations

import json as _json
import traceback
from typing import Any, Dict, List

from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core.time_utils import utc_now_iso

from ._connection import (
    _DB_LOCK,
    _db_cursor,
    _normalize_mac,
    _normalize_uuid,
    _ensure_device_exists,
    json_dumps,
)


def upsert_device(mac: str, **cols):
    """
    Update or insert a device record in the database with enhanced device type classification.
    
    Args:
        mac: Device MAC address
        **cols: Column values to set
        
    Note on device_type classification:
    - 'unknown': Not enough information available
    - 'classic': Device has Classic identifiers (device_class) but no LE identifiers
    - 'le': Device has LE identifiers (addr_type) but no Classic identifiers
    - 'dual': Device has conclusive evidence of both Classic and LE capabilities
    """
    mac = _normalize_mac(mac)
    if mac is None:
        print_and_log(f"upsert_device: rejected invalid MAC", LOG__DEBUG)
        return
    now = utc_now_iso()
    
    # Always update last_seen timestamp
    cols.setdefault("last_seen", now)
    
    # Check if device already exists and get current device info
    with _DB_LOCK, _db_cursor() as cur:
        device_row = cur.execute(
            """SELECT device_type, device_class, addr_type, seen_by,
                  (SELECT COUNT(*) FROM services WHERE mac=?) as gatt_services,
                  (SELECT COUNT(*) FROM classic_services WHERE mac=?) as classic_services 
               FROM devices WHERE mac=?""", 
            (mac, mac, mac)
        ).fetchone()
        
        device_exists = device_row is not None
        
        # If device doesn't exist, set first_seen timestamp
        if not device_exists and "first_seen" not in cols:
            cols["first_seen"] = now
        
        # Only determine device_type if not explicitly provided
        if "device_type" not in cols:
            # Extract current values from database
            current_device_type = device_row["device_type"] if device_exists else "unknown"
            current_device_class = device_row["device_class"] if device_exists else None
            current_addr_type = device_row["addr_type"] if device_exists else None
            has_gatt = device_row["gatt_services"] > 0 if device_exists else False
            has_classic = device_row["classic_services"] > 0 if device_exists else False
            
            # Get updated values from current operation
            new_device_class = cols.get("device_class", current_device_class)
            new_addr_type = cols.get("addr_type", current_addr_type)
            
            # Apply enhanced classification logic
            if new_device_class and new_addr_type:
                # Strong evidence for dual-mode device (both Classic and LE identifiers)
                cols["device_type"] = "dual"
            elif has_gatt and has_classic:
                # Device has both GATT and Classic services, must be dual
                cols["device_type"] = "dual"
            elif current_device_type == "dual":
                # Preserve dual status if already established
                cols["device_type"] = "dual"
            elif new_device_class and not new_addr_type:
                # Classic device (has class but no LE address type)
                cols["device_type"] = "classic"
            elif new_addr_type and not new_device_class:
                # LE device (has address type but no Classic class)
                cols["device_type"] = "le"
            elif has_gatt and not has_classic:
                # Has GATT services but no Classic services
                cols["device_type"] = "le"
            elif has_classic and not has_gatt:
                # Has Classic services but no GATT services
                cols["device_type"] = "classic"
            elif current_device_type != "unknown":
                # Preserve any previously established non-unknown type
                cols["device_type"] = current_device_type
            else:
                # Not enough information to determine type
                cols["device_type"] = "unknown"
        
        if "uuids" in cols and isinstance(cols["uuids"], list):
            cols["uuids"] = [u.strip().upper() if isinstance(u, str) else u for u in cols["uuids"]]

        # Union-merge seen_by so a second antenna adds to the set rather than
        # replacing the first (schema v19). Last-writer-wins would drop
        # triangulation provenance.
        if "seen_by" in cols:
            incoming = cols["seen_by"]
            if isinstance(incoming, str):
                try:
                    incoming = _json.loads(incoming)
                except (TypeError, ValueError):
                    incoming = [incoming] if incoming else []
            if incoming is None:
                incoming = []
            if not isinstance(incoming, (list, tuple, set)):
                incoming = [incoming]
            existing: List[Any] = []
            if device_exists:
                raw = device_row["seen_by"] if "seen_by" in device_row.keys() else None
                if raw:
                    if isinstance(raw, str):
                        try:
                            existing = _json.loads(raw)
                        except (TypeError, ValueError):
                            existing = [raw]
                    elif isinstance(raw, (list, tuple)):
                        existing = list(raw)
            cols["seen_by"] = sorted(
                {str(x) for x in list(existing) + list(incoming) if x}
            )

        # Serialize list/dict fields to JSON for storage
        for json_col in ("uuids", "service_data", "advertising_data", "lmp_features", "seen_by"):
            if json_col in cols and isinstance(cols[json_col], (list, dict)):
                cols[json_col] = json_dumps(cols[json_col])

        _DEVICE_COLS = frozenset({
            "addr_type", "name", "appearance", "device_class",
            "manufacturer_id", "manufacturer_data", "rssi_last", "rssi_min",
            "rssi_max", "first_seen", "last_seen", "notes", "device_type",
            "tx_power", "modalias", "icon", "service_data", "advertising_data",
            "uuids", "paired", "trusted", "bonded",
            "sighting_count", "fingerprint_changed",
            "lmp_version", "lmp_subversion", "bt_manufacturer",
            "bt_spec_version", "lmp_features", "version_queried_at",
            "firmware_revision", "software_revision", "model_number",
            "dis_manufacturer_name", "pnp_vendor_source", "pnp_vendor_id",
            "pnp_product_id", "pnp_product_version",
            "seen_by", "enumerated_by", "enumerated_at",
        })
        cols = {k: v for k, v in cols.items() if k in _DEVICE_COLS}

        # Prepare SQL statement
        cols_keys = ",".join(cols.keys())
        placeholders = ",".join("?" for _ in cols)
        
        # Build per-column SET expressions for the ON CONFLICT clause.
        # - first_seen is never overwritten (preserve original observation time).
        # - rssi_min/rssi_max use SQL MIN/MAX to track the observed range.
        # - name: never downgrade a resolved name to a placeholder.
        _RSSI_RANGE_COLS = {
            "rssi_min": "MIN(COALESCE(devices.rssi_min, excluded.rssi_min), excluded.rssi_min)",
            "rssi_max": "MAX(COALESCE(devices.rssi_max, excluded.rssi_max), excluded.rssi_max)",
        }
        _PLACEHOLDER_NAMES = ("Unknown Device", "Unknown")
        update_parts = []
        for k in cols.keys():
            if k == "first_seen":
                continue
            if k in _RSSI_RANGE_COLS:
                update_parts.append(f"{k}={_RSSI_RANGE_COLS[k]}")
            elif k == "name":
                update_parts.append(
                    "name=CASE"
                    " WHEN devices.name IS NOT NULL"
                    "  AND devices.name NOT IN ('Unknown Device','Unknown')"
                    "  AND (excluded.name IS NULL"
                    "       OR excluded.name IN ('Unknown Device','Unknown'))"
                    " THEN devices.name"
                    " ELSE excluded.name"
                    " END"
                )
            else:
                update_parts.append(f"{k}=excluded.{k}")

        if update_parts:
            update_clause = f"ON CONFLICT(mac) DO UPDATE SET {','.join(update_parts)}"
        else:
            update_clause = "ON CONFLICT(mac) DO NOTHING"
        
        # Execute upsert
        cur.execute(
            f"INSERT INTO devices(mac,{cols_keys}) VALUES (? ,{placeholders}) {update_clause}",
            (mac, *cols.values()),
        )


def get_enumeration_stamp(mac: str) -> tuple:
    """Return ``(enumerated_by, enumerated_at)`` for *mac*, or ``(None, None)``."""
    mac = _normalize_mac(mac)
    if mac is None:
        return None, None
    try:
        with _db_cursor() as cur:
            row = cur.execute(
                "SELECT enumerated_by, enumerated_at FROM devices WHERE mac=?",
                (mac,),
            ).fetchone()
        if row is None:
            return None, None
        return row["enumerated_by"], row["enumerated_at"]
    except Exception as exc:
        print_and_log(f"get_enumeration_stamp: {exc}", LOG__DEBUG)
        return None, None


_SEEN_BASIS_COLUMN = {"first": "first_seen", "last": "last_seen"}


def get_devices(status: str = None, limit: int = 100, offset: int = 0,
                name: str = None, since: str = None, until: str = None,
                seen_basis: str = "last") -> List[Dict[str, Any]]:
    """
    Get list of devices from the database with pagination support.
    
    Args:
        status: Optional filter for device status (comma-separated)
          'recent' - Devices seen in the last 24 hours
          'ble' - Bluetooth Low Energy devices
          'classic' - Bluetooth Classic devices
          'dual' - Dual-mode devices (both Classic and BLE)
          'unknown' - Devices with unknown type
          'media' - Devices with media capabilities
        limit: Maximum number of devices to return (default: 100)
        offset: Number of records to skip for pagination (default: 0)
        name: Optional case-insensitive substring filter on the device name
          (``name LIKE %value%``). Useful for enumerating every RPA identity of a
          single named device without heuristic identity merging (F1).
        since: Optional inclusive lower bound (naive-UTC ISO string) for the
          date window (DB-1). Compared against the column selected by
          *seen_basis*. ``None`` leaves the lower bound open.
        until: Optional **exclusive** upper bound (naive-UTC ISO string) for the
          date window. Callers wanting an inclusive end date pass the following
          midnight (see :func:`bleep.core.time_utils.local_date_range_to_utc`).
          ``None`` leaves the upper bound open.
        seen_basis: Which timestamp the *since*/*until* window applies to:
          ``'last'`` (default) filters ``last_seen`` (indexed via
          ``idx_devices_last_seen``); ``'first'`` filters ``first_seen``;
          ``'any'`` matches devices whose observation span overlaps the window
          (``first_seen < until AND last_seen >= since``). Unknown values fall
          back to ``'last'``.
        
    Returns:
        List of device dictionaries (empty list if error occurs)
    """
    try:
        # Build the query using v2 schema column names
        query = "SELECT * FROM devices"
        params = []

        where_clauses: List[str] = []
        
        if status:
            status_filters = []
            for s in status.split(','):
                s = s.strip().lower()
                if s == 'recent':
                    # Devices seen in the last 24 hours
                    status_filters.append("last_seen > datetime('now', '-1 day')")
                elif s == 'ble':
                    # Use the explicit device_type field for more accurate filtering
                    # This includes both BLE-only and dual-mode devices
                    status_filters.append("(device_type = 'le' OR device_type = 'dual')")
                elif s == 'classic':
                    # Use the explicit device_type field for more accurate filtering
                    # This includes both Classic-only and dual-mode devices
                    status_filters.append("(device_type = 'classic' OR device_type = 'dual')")
                elif s == 'dual':
                    # Filter for dual-mode devices
                    status_filters.append("device_type = 'dual'")
                elif s == 'unknown':
                    # Filter for devices with unknown type
                    status_filters.append("device_type = 'unknown' OR device_type IS NULL")
                elif s == 'media':
                    query = """
                    SELECT DISTINCT d.* FROM devices d
                    INNER JOIN media_players mp ON d.mac = mp.mac
                    """
                    
            if status_filters:
                # Grouped so the OR-set does not swallow later AND-ed predicates.
                where_clauses.append("(" + " OR ".join(status_filters) + ")")

        # Column names are qualified with the ``d.`` alias when the 'media' status
        # rebuilt the query with a ``devices d`` JOIN, to avoid ambiguity.
        aliased = "FROM devices d" in query
        col = (lambda c: f"d.{c}") if aliased else (lambda c: c)

        # Optional name substring filter (F1). ANDed with any status group.
        if name:
            where_clauses.append(f"{col('name')} LIKE ?")
            params.append(f"%{name}%")

        # Date-range window (DB-1). ``until`` is exclusive so an inclusive end
        # date maps cleanly to ``< next_midnight``. ``seen_basis`` chooses which
        # timestamp anchors the window; ``any`` selects the overlap of the
        # device's [first_seen, last_seen] observation span with the window.
        basis = (seen_basis or "last").strip().lower()
        if basis == "any" and (since or until):
            if until:
                where_clauses.append(f"{col('first_seen')} < ?")
                params.append(until)
            if since:
                where_clauses.append(f"{col('last_seen')} >= ?")
                params.append(since)
        else:
            window_col = _SEEN_BASIS_COLUMN.get(basis, "last_seen")
            if since:
                where_clauses.append(f"{col(window_col)} >= ?")
                params.append(since)
            if until:
                where_clauses.append(f"{col(window_col)} < ?")
                params.append(until)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        # Add pagination with LIMIT and OFFSET
        query += " ORDER BY last_seen DESC LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)
        
        # Execute the query
        with _DB_LOCK, _db_cursor() as cur:
            cur.execute(query, params)
            result = [dict(row) for row in cur.fetchall()]
            
            # No need for backward compatibility mapping - only using v2 schema
                    
            return result
    except Exception as e:
        print(f"Error in get_devices: {e}")
        import traceback
        print(traceback.format_exc())
        return []  # Return empty list instead of None to prevent TypeErrors


def get_device_detail(mac: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific device.
    
    Args:
        mac: Device MAC address
        
    Returns:
        Dictionary with device information including services and characteristics
    """
    mac = _normalize_mac(mac)
    
    result: Dict[str, Any] = {
        'device': None,
        'services': [],
        'characteristics': [],
        'descriptors': [],
        'classic_services': [],
        'sdp_records': [],
        'pbap_metadata': [],
        'media_players': [],
        'media_transports': [],
        'pairing_events': [],
        'security_maps': [],
        'media_enumerations': [],
    }
    if mac is None:
        return result
    
    with _DB_LOCK, _db_cursor() as cur:
        # Get device info
        cur.execute("SELECT * FROM devices WHERE mac=?", (mac,))
        device = cur.fetchone()
        if device:
            result['device'] = dict(device)
            
            # Get services
            cur.execute("SELECT * FROM services WHERE mac=? ORDER BY handle_start", (mac,))
            services = [dict(row) for row in cur.fetchall()]
            result['services'] = services
            
            # Get characteristics + descriptors for each service
            for svc in services:
                cur.execute(
                    "SELECT * FROM characteristics WHERE service_id=? ORDER BY handle",
                    (svc['id'],),
                )
                chars = [dict(row) for row in cur.fetchall()]
                result['characteristics'].extend(chars)
                for ch in chars:
                    cur.execute(
                        "SELECT * FROM descriptors WHERE characteristic_id=? ORDER BY handle",
                        (ch['id'],),
                    )
                    descs = [dict(row) for row in cur.fetchall()]
                    result['descriptors'].extend(descs)
            
            # Get classic services
            cur.execute("SELECT * FROM classic_services WHERE mac=?", (mac,))
            result['classic_services'] = [dict(row) for row in cur.fetchall()]
            
            # Get SDP records (full snapshots)
            cur.execute("SELECT * FROM sdp_records WHERE mac=? ORDER BY ts DESC", (mac,))
            sdp_rows = cur.fetchall()
            # Parse JSON fields for SDP records
            sdp_records = []
            for row in sdp_rows:
                rec = dict(row)
                # Parse JSON fields
                if rec.get('profile_descriptors'):
                    try:
                        rec['profile_descriptors'] = _json.loads(rec['profile_descriptors'])
                    except (TypeError, ValueError, KeyError):
                        pass
                if rec.get('protocol_descriptors'):
                    try:
                        rec['protocol_descriptors'] = _json.loads(rec['protocol_descriptors'])
                    except (TypeError, ValueError, KeyError):
                        pass
                sdp_records.append(rec)
            result['sdp_records'] = sdp_records
            
            # Get PBAP metadata
            cur.execute("SELECT * FROM pbap_metadata WHERE mac=?", (mac,))
            result['pbap_metadata'] = [dict(row) for row in cur.fetchall()]
            
            # Get media players
            cur.execute("SELECT * FROM media_players WHERE mac=?", (mac,))
            result['media_players'] = [dict(row) for row in cur.fetchall()]
            
            # Get media transports
            cur.execute("SELECT * FROM media_transports WHERE mac=?", (mac,))
            result['media_transports'] = [dict(row) for row in cur.fetchall()]

            # Get pairing events (Phase 2)
            cur.execute("SELECT * FROM pairing_events WHERE mac=? ORDER BY ts DESC", (mac,))
            result['pairing_events'] = [dict(row) for row in cur.fetchall()]

            # Get security maps (Phase 2)
            cur.execute("SELECT * FROM security_maps WHERE mac=? ORDER BY ts DESC", (mac,))
            result['security_maps'] = [dict(row) for row in cur.fetchall()]

            # Get media enumerations (Phase 2)
            cur.execute("SELECT * FROM media_enumerations WHERE mac=? ORDER BY ts DESC", (mac,))
            result['media_enumerations'] = [dict(row) for row in cur.fetchall()]

    return result


def _convert_binary_for_json(data: Any) -> Any:
    """
    Convert binary data to hex strings for JSON serialization.
    
    Args:
        data: Data to convert
        
    Returns:
        JSON-serializable data
    """
    if isinstance(data, bytes):
        return data.hex()
    elif isinstance(data, dict):
        return {k: _convert_binary_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_convert_binary_for_json(item) for item in data]
    else:
        return data


def export_device_data(mac: str, char_limit: int = 500,
                        adv_limit: int = 100) -> Dict[str, Any]:
    """
    Export all data for a device in a format suitable for JSON export.
    
    Args:
        mac: Device MAC address
        char_limit: Maximum characteristic-history rows to include, newest-first
          (default: 500). ``0`` or ``None`` disables the cap and exports the full
          history (DB-5) — use for chatty devices where the default truncates.
        adv_limit: Maximum advertisement-report rows to include, newest-first
          (default: 100). ``0`` or ``None`` disables the cap (DB-5).
        
    Returns:
        Dictionary with all device data including characteristic history,
        advertisement reports, AoI analysis results, and device type evidence.
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return {}
    
    device_detail = get_device_detail(mac)

    # 0/None means "no cap": omit the LIMIT clause entirely rather than binding a
    # sentinel, so SQLite returns the full ordered history for the device.
    char_clause = f" LIMIT {int(char_limit)}" if char_limit else ""
    adv_clause = f" LIMIT {int(adv_limit)}" if adv_limit else ""

    # Get characteristic history
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(
            f"SELECT * FROM char_history WHERE mac=? ORDER BY ts DESC{char_clause}",
            (mac,)
        )
        device_detail['characteristic_history'] = [dict(row) for row in cur.fetchall()]
        
        # Get advertisement reports
        cur.execute(
            f"SELECT * FROM adv_reports WHERE mac=? ORDER BY ts DESC{adv_clause}",
            (mac,)
        )
        device_detail['adv_reports'] = [dict(row) for row in cur.fetchall()]

    from bleep.core.observations._aoi import get_aoi_analysis
    from bleep.core.observations._evidence import get_device_type_evidence

    aoi = get_aoi_analysis(mac)
    if aoi:
        device_detail['aoi_analysis'] = aoi

    evidence = get_device_type_evidence(mac)
    if evidence:
        device_detail['device_type_evidence'] = evidence

    # Convert binary data to hex strings for JSON serialization
    return _convert_binary_for_json(device_detail)


def _mac_in_clause(macs: List[str]) -> tuple[str, List[str]]:
    """Build a ``mac IN (?, ?, …)`` fragment + normalized-uppercase params."""
    norm = [m for m in (_normalize_mac(x) for x in macs) if m]
    placeholders = ",".join("?" * len(norm))
    return placeholders, norm


def get_sdp_inventory(macs: List[str]) -> List[Dict[str, Any]]:
    """Aggregate distinct SDP service items across *macs* (DB-9).

    Single batched ``WHERE mac IN (…)`` query over ``sdp_records`` (no per-device
    ``get_device_detail`` loads). Returns a list of
    ``{name, uuid, device_count, record_count}`` sorted by descending
    ``device_count`` then name, where ``device_count`` counts distinct devices
    exposing that ``(name, uuid)`` service and ``record_count`` counts snapshots.
    """
    if not macs:
        return []
    placeholders, params = _mac_in_clause(macs)
    if not params:
        return []
    agg: Dict[tuple, Dict[str, Any]] = {}
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(
            f"SELECT mac, name, uuid FROM sdp_records WHERE mac IN ({placeholders})",
            params,
        )
        rows = cur.fetchall()
    for row in rows:
        r = dict(row)
        name = r.get("name")
        uuid = r.get("uuid")
        if not name and not uuid:
            continue
        key = (name or "(unnamed)", uuid or "-")
        entry = agg.get(key)
        if entry is None:
            entry = {"name": key[0], "uuid": key[1], "record_count": 0, "_macs": set()}
            agg[key] = entry
        entry["record_count"] += 1
        entry["_macs"].add(r.get("mac"))
    out = []
    for entry in agg.values():
        entry["device_count"] = len(entry.pop("_macs"))
        out.append(entry)
    out.sort(key=lambda e: (-e["device_count"], str(e["name"])))
    return out


def get_characteristic_values(macs: List[str]) -> List[Dict[str, Any]]:
    """Latest characteristic value per ``(mac, char_uuid)`` across *macs* (DB-9).

    Batched query over ``char_history`` (newest snapshot per characteristic per
    device). Returns ``{mac, service_uuid, char_uuid, value_hex}`` rows with the
    value rendered as a hex string (empty string when NULL). Used by the opt-in
    ``--recon-detail`` characteristic-hex analysis.
    """
    if not macs:
        return []
    placeholders, params = _mac_in_clause(macs)
    if not params:
        return []
    latest: Dict[tuple, Dict[str, Any]] = {}
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(
            f"SELECT mac, service_uuid, char_uuid, value, ts FROM char_history "
            f"WHERE mac IN ({placeholders}) ORDER BY ts ASC",
            params,
        )
        rows = cur.fetchall()
    for row in rows:
        r = dict(row)
        key = (r.get("mac"), r.get("char_uuid"))
        val = r.get("value")
        if isinstance(val, (bytes, bytearray, memoryview)):
            value_hex = bytes(val).hex()
        elif val is None:
            value_hex = ""
        else:
            value_hex = str(val)
        # ORDER BY ts ASC → last write wins = newest snapshot.
        latest[key] = {
            "mac": r.get("mac"),
            "service_uuid": r.get("service_uuid"),
            "char_uuid": r.get("char_uuid"),
            "value_hex": value_hex,
        }
    return list(latest.values())
