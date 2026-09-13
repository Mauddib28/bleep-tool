"""Service, characteristic, descriptor, and Classic profile upsert operations."""
from __future__ import annotations

from typing import Any, Dict, List

from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core.time_utils import utc_now_iso

from . import _connection
from ._connection import (
    _DB_LOCK,
    _db_cursor,
    _normalize_mac,
    _normalize_uuid,
    _ensure_device_exists,
    _ensure_service_exists,
    json_dumps,
)


def upsert_services(mac: str, svc_list: List[Dict[str, Any]]) -> Dict[str, int]:
    """Insert/UPSERT services and return a mapping uuid → row id.

    UUIDs are stored uppercase in the database, but the returned dict is keyed
    by the *original* (caller-supplied) UUID to preserve backward compatibility.
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return {}
    ids: Dict[str, int] = {}
    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        for svc in svc_list:
            original_uuid = svc["uuid"]
            norm_uuid = _normalize_uuid(original_uuid)
            is_primary = svc.get("is_primary")
            if is_primary is not None:
                is_primary = 1 if is_primary else 0

            includes_raw = svc.get("includes")
            if isinstance(includes_raw, (list, tuple)):
                includes_raw = json_dumps(includes_raw)

            cur.execute(
                """
                INSERT INTO services(mac,uuid,handle_start,handle_end,name,first_seen,last_seen,is_primary,includes)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(mac,uuid) DO UPDATE SET
                    last_seen=excluded.last_seen,
                    handle_start=COALESCE(excluded.handle_start, services.handle_start),
                    handle_end=COALESCE(excluded.handle_end, services.handle_end),
                    name=COALESCE(excluded.name, services.name),
                    is_primary=COALESCE(excluded.is_primary, services.is_primary),
                    includes=COALESCE(excluded.includes, services.includes)
                """,
                (
                    mac,
                    norm_uuid,
                    svc.get("handle_start"),
                    svc.get("handle_end"),
                    svc.get("name"),
                    utc_now_iso(),
                    utc_now_iso(),
                    is_primary,
                    includes_raw,
                ),
            )
            sid = cur.lastrowid
            if not sid:
                row = cur.execute(
                    "SELECT id FROM services WHERE mac=? AND uuid=?",
                    (mac, norm_uuid),
                ).fetchone()
                if row:
                    sid = row["id"]  # type: ignore[index]
            if sid:
                ids[original_uuid] = sid
    return ids


def upsert_characteristics(
    service_id: int,
    char_list: List[Dict[str, Any]],
    *,
    mac: str | None = None,
    service_uuid: str | None = None,
):
    """Insert/UPSERT characteristics for a service.

    When *mac* and *service_uuid* are supplied the function defensively
    guarantees the parent device and service rows exist before inserting,
    preventing FOREIGN KEY failures even when the caller's ``service_id``
    is stale or the service was never explicitly created.
    """
    with _DB_LOCK, _db_cursor() as cur:
        if mac and service_uuid:
            _ensure_device_exists(cur, mac)
            service_id = _ensure_service_exists(cur, mac, service_uuid)

        for ch in char_list:
            try:
                props = ch.get("properties", [])
                if isinstance(props, list):
                    props_str = ",".join(props)
                else:
                    props_str = str(props)

                raw_val = ch.get("value")
                if raw_val is None:
                    blob_val = None
                elif isinstance(raw_val, bytes):
                    blob_val = raw_val
                elif isinstance(raw_val, (list, tuple)):
                    blob_val = bytes(raw_val)
                elif isinstance(raw_val, str):
                    blob_val = raw_val.encode("utf-8", errors="replace")
                else:
                    blob_val = bytes(raw_val)

                perm_map = ch.get("permission_map")
                if isinstance(perm_map, dict):
                    perm_map = json_dumps(perm_map)

                mtu_val = ch.get("mtu") or ch.get("MTU")

                norm_uuid = _normalize_uuid(ch["uuid"])
                cur.execute(
                    """
                    INSERT INTO characteristics(service_id,uuid,handle,properties,value,last_read,permission_map,mtu)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(service_id,uuid) DO UPDATE SET
                        value=excluded.value,
                        last_read=excluded.last_read,
                        permission_map=COALESCE(excluded.permission_map, characteristics.permission_map),
                        mtu=COALESCE(excluded.mtu, characteristics.mtu)
                    """,
                    (
                        service_id,
                        norm_uuid,
                        ch.get("handle"),
                        props_str,
                        blob_val,
                        utc_now_iso(),
                        perm_map,
                        mtu_val,
                    ),
                )
            except Exception as e:
                print_and_log(f"[-] Error inserting characteristic {ch.get('uuid')}: {e}", LOG__DEBUG)


def get_characteristic_id(service_id: int, char_uuid: str) -> int | None:
    """Return the DB row id for a characteristic, or None if not found."""
    norm_uuid = _normalize_uuid(char_uuid)
    with _DB_LOCK, _db_cursor() as cur:
        row = cur.execute(
            "SELECT id FROM characteristics WHERE service_id=? AND uuid=?",
            (service_id, norm_uuid),
        ).fetchone()
        return row["id"] if row else None


def upsert_descriptors(
    characteristic_id: int,
    desc_list: List[Dict[str, Any]],
) -> None:
    """Insert/UPSERT descriptors for a characteristic."""
    with _DB_LOCK, _db_cursor() as cur:
        for desc in desc_list:
            try:
                raw_val = desc.get("value")
                if raw_val is None:
                    blob_val = None
                elif isinstance(raw_val, bytes):
                    blob_val = raw_val
                elif isinstance(raw_val, (list, tuple)):
                    blob_val = bytes(raw_val)
                elif isinstance(raw_val, str):
                    blob_val = raw_val.encode("utf-8", errors="replace")
                else:
                    blob_val = bytes(raw_val)

                flags = desc.get("flags")
                if isinstance(flags, list):
                    flags = ",".join(flags)

                norm_uuid = _normalize_uuid(desc["uuid"])
                cur.execute(
                    """
                    INSERT INTO descriptors(characteristic_id,uuid,handle,flags,value,last_read)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(characteristic_id,uuid) DO UPDATE SET
                        value=excluded.value,
                        last_read=excluded.last_read,
                        flags=COALESCE(excluded.flags, descriptors.flags),
                        handle=COALESCE(excluded.handle, descriptors.handle)
                    """,
                    (
                        characteristic_id,
                        norm_uuid,
                        desc.get("handle"),
                        flags,
                        blob_val,
                        utc_now_iso(),
                    ),
                )
            except Exception as e:
                print_and_log(f"[-] Error inserting descriptor {desc.get('uuid')}: {e}", LOG__DEBUG)


def upsert_classic_services(mac: str, services: List[Dict[str, Any]]):
    mac = _normalize_mac(mac)
    if mac is None:
        return
    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        for svc in services:
            cur.execute(
                """
                INSERT OR REPLACE INTO classic_services(mac,uuid,channel,name,ts)
                VALUES (?,?,?,?,?)
                """,
                (
                    mac,
                    _normalize_uuid(svc["uuid"]),
                    svc["channel"],
                    svc.get("name"),
                    utc_now_iso(),
                ),
            )
    if _connection._DB_CONN is not None:
        _connection._DB_CONN.commit()


def upsert_sdp_record(mac: str, record: Dict[str, Any]):
    """Store a full SDP record snapshot in the database.
    
    Parameters
    ----------
    mac : str
        Device MAC address
    record : Dict[str, Any]
        SDP record dictionary with keys:
        - handle (int): Service Record Handle (0x0000)
        - uuid (str): Service UUID
        - channel (int): RFCOMM channel (if applicable)
        - name (str): Service name
        - profile_descriptors (List[Dict]): Profile descriptor list with uuid and version
        - service_version (int): Service version (0x0300)
        - description (str): Service description (0x0101)
        - mas_instance_id (int): MAS Instance ID (0x0315) — MAP only
        - supported_message_types (int): Supported Message Types (0x0316) — MAP only
        - supported_features (int): MapSupportedFeatures bitmask (0x0317) — MAP only
        - raw (str): Full raw record (XML or text)
        
    Notes
    -----
    This function stores full SDP record snapshots with all attributes.
    The basic UUID/channel mapping is still stored separately in classic_services
    table for backward compatibility.
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return
    
    # Extract fields from record
    handle = record.get("handle")
    uuid = _normalize_uuid(record.get("uuid")) if record.get("uuid") else None
    channel = record.get("channel")
    name = record.get("name")
    profile_descriptors = record.get("profile_descriptors")
    service_version = record.get("service_version")
    description = record.get("description")
    raw_record = record.get("raw")
    
    # Convert profile_descriptors to JSON if present
    profile_descriptors_json = json_dumps(profile_descriptors) if profile_descriptors else None
    
    protocol_descriptors = record.get("protocol_descriptors")
    protocol_descriptors_json = json_dumps(protocol_descriptors) if protocol_descriptors else None

    mas_instance_id = record.get("mas_instance_id")
    supported_message_types = record.get("supported_message_types")
    supported_features = record.get("supported_features")
    # Provenance (schema v18): which discovery source produced this record.
    # Deliberately EXCLUDED from the change-detection tuple below so that
    # re-observing identical content from a different source does not create a
    # spurious history row; the first-stored source is retained for that snapshot.
    source = record.get("source")

    # Append-only / versioned write (schema v16). Rather than overwriting a prior
    # record in place (the old ON CONFLICT … DO UPDATE, which silently discarded
    # change history), we append a new timestamped snapshot *only when the service
    # content differs* from the latest stored snapshot for the same logical service.
    #
    # Logical identity = (mac, uuid, channel). The comparison deliberately EXCLUDES
    # the volatile ``service_record_handle`` (honeypots/servers rotate it without any
    # semantic change), ``ts`` (always changes) and ``raw_record`` (formatting-only
    # variance) so that identical re-observations do not accumulate noise rows, while
    # every genuine alteration is preserved as a distinct, queryable snapshot.
    new_snapshot = (
        name,
        profile_descriptors_json,
        service_version,
        description,
        protocol_descriptors_json,
        mas_instance_id,
        supported_message_types,
        supported_features,
    )
    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        # ``IS`` handles NULL uuid/channel correctly (NULL = NULL under IS).
        prev = cur.execute(
            """
            SELECT name, profile_descriptors, service_version, service_description,
                   protocol_descriptors, mas_instance_id, supported_message_types,
                   supported_features
            FROM sdp_records
            WHERE mac = ? AND uuid IS ? AND channel IS ?
            ORDER BY ts DESC, id DESC
            LIMIT 1
            """,
            (mac, uuid, channel),
        ).fetchone()

        if prev is not None and tuple(prev) == new_snapshot:
            return  # No change vs latest snapshot — skip (non-destructive, no bloat).

        cur.execute(
            """
            INSERT INTO sdp_records(
                mac, service_record_handle, uuid, channel, name,
                profile_descriptors, service_version, service_description,
                protocol_descriptors, raw_record, ts,
                mas_instance_id, supported_message_types, supported_features,
                source
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                mac,
                handle,
                uuid,
                channel,
                name,
                profile_descriptors_json,
                service_version,
                description,
                protocol_descriptors_json,
                raw_record,
                utc_now_iso(),
                mas_instance_id,
                supported_message_types,
                supported_features,
                source,
            ),
        )
    if _connection._DB_CONN is not None:
        _connection._DB_CONN.commit()


_SDP_TIMELINE_FIELDS = (
    "name",
    "service_version",
    "service_description",
    "profile_descriptors",
    "protocol_descriptors",
    "mas_instance_id",
    "supported_message_types",
    "supported_features",
)


def get_sdp_timeline(
    mac: str,
    uuid: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Return the append-only SDP snapshot history for a device, oldest-first.

    Reads the versioned ``sdp_records`` table (see :func:`upsert_sdp_record`),
    which already stores one row per genuine content change. Rows are ordered by
    ``(uuid, channel, ts, id)`` so a consumer can walk consecutive snapshots of
    the *same logical service* and diff them. Read-only.

    Parameters
    ----------
    mac : str
        Device MAC address.
    uuid : str, optional
        Restrict to a single service UUID (normalised like the writer).
    limit : int, optional
        Cap the number of snapshot rows returned (after ordering).
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return []
    want_uuid = _normalize_uuid(uuid) if uuid else None

    sql = (
        "SELECT id, service_record_handle, uuid, channel, name, profile_descriptors, "
        "service_version, service_description, protocol_descriptors, mas_instance_id, "
        "supported_message_types, supported_features, source, ts "
        "FROM sdp_records WHERE mac = ?"
    )
    params: list = [mac]
    if want_uuid is not None:
        sql += " AND uuid IS ?"
        params.append(want_uuid)
    # NULLs sort first under SQLite ASC; that is fine and deterministic.
    sql += " ORDER BY uuid ASC, channel ASC, ts ASC, id ASC"

    out: list[dict] = []
    with _db_cursor() as cur:
        try:
            rows = cur.execute(sql, params).fetchall()
        except Exception:  # noqa: BLE001 - tolerate very old schemas
            return []
        for row in rows:
            out.append({
                "id": row["id"],
                "service_record_handle": row["service_record_handle"],
                "uuid": row["uuid"],
                "channel": row["channel"],
                "name": row["name"],
                "service_version": row["service_version"],
                "service_description": row["service_description"],
                "profile_descriptors": row["profile_descriptors"],
                "protocol_descriptors": row["protocol_descriptors"],
                "mas_instance_id": row["mas_instance_id"],
                "supported_message_types": row["supported_message_types"],
                "supported_features": row["supported_features"],
                "source": row["source"],
                "ts": row["ts"],
            })
    if limit is not None:
        out = out[:limit]
    return out


def upsert_pan_access(
    mac: str,
    role: str,
    action: str,
    interface: str | None = None,
) -> None:
    """Record a PAN connect/disconnect event on a device.

    Updates ``last_seen`` and appends a timestamped note.
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return
    now = utc_now_iso()
    detail = f"PAN {action} role={role}"
    if interface:
        detail += f" iface={interface}"
    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        cur.execute("UPDATE devices SET last_seen=? WHERE mac=?", (now, mac))


def upsert_pbap_metadata(mac: str, repo: str, entries: int, vcf_hash: str):
    mac = _normalize_mac(mac)
    if mac is None:
        return
    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        cur.execute(
            """
            INSERT INTO pbap_metadata(mac,repo,entries,hash,ts)
            VALUES (?,?,?,?,?)
            ON CONFLICT(mac,repo) DO UPDATE SET entries=excluded.entries,hash=excluded.hash,ts=excluded.ts
            """,
            (mac, repo, entries, vcf_hash, utc_now_iso()),
        )
