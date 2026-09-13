"""Advertisement and characteristic history recording."""
from __future__ import annotations

import json as _json
from typing import Any, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core.time_utils import utc_now_iso

from . import _connection
from ._connection import (
    _DB_LOCK,
    _db_cursor,
    _normalize_mac,
    _normalize_uuid,
    _ensure_device_exists,
    json_dumps,
)


def _as_blob_bytes(value: Any) -> bytes:
    """Normalize an advert raw-payload value to ``bytes`` for stable comparison."""
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    return value


def _decoded_matches(stored: Any, decoded: Dict[str, Any], decoded_json: str) -> bool:
    """True when a previously-stored decoded blob equals ``decoded``.

    Tries the fast exact-string path first, then falls back to a key-order-independent
    structural comparison of the parsed JSON. ``json_dumps`` does not sort keys, so two
    structurally-identical decoded dicts serialized in a different key order would
    otherwise be treated as a change and emit a redundant adv_reports row. A parse
    failure is treated as "not a match" so the sample is persisted rather than lost.
    """
    if stored == decoded_json:
        return True
    try:
        return _json.loads(stored) == decoded
    except (TypeError, ValueError):
        return False


def insert_adv(
    mac: str, rssi: int, data: bytes, decoded: Dict[str, Any],
    adapter: Optional[str] = None,
):
    mac = _normalize_mac(mac)
    if mac is None:
        return
    decoded_json = json_dumps(decoded)
    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        # Coalesce consecutive identical samples: BlueZ's GetManagedObjects re-reports
        # the same advert payload every survey round, so an unconditional INSERT floods
        # adv_reports with duplicates. Only persist when the (data, decoded, adapter)
        # triple differs from the most recent row for this device on this antenna.
        # RSSI-only changes are intentionally not persisted here — RSSI aggregates
        # live on the devices row.
        if adapter:
            cur.execute(
                "SELECT data, decoded FROM adv_reports "
                "WHERE mac=? AND adapter=? ORDER BY rowid DESC LIMIT 1",
                (mac, adapter),
            )
        else:
            cur.execute(
                "SELECT data, decoded FROM adv_reports "
                "WHERE mac=? AND adapter IS NULL ORDER BY rowid DESC LIMIT 1",
                (mac,),
            )
        prev = cur.fetchone()
        if (
            prev is not None
            and _as_blob_bytes(prev[0]) == _as_blob_bytes(data)
            and _decoded_matches(prev[1], decoded, decoded_json)
        ):
            return
        cur.execute(
            "INSERT INTO adv_reports(mac,ts,rssi,data,decoded,adapter) VALUES (?,?,?,?,?,?)",
            (
                mac,
                utc_now_iso(),
                rssi,
                data,
                decoded_json,
                adapter,
            ),
        )


def insert_char_history(mac: str, service_uuid: str, char_uuid: str, value: bytes, source: str = "unknown"):
    """
    Insert a characteristic value into the history table.
    
    Args:
        mac: Device MAC address
        service_uuid: Service UUID
        char_uuid: Characteristic UUID
        value: Characteristic value
        source: Source of the value (read, write, notification)
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return
    service_uuid = _normalize_uuid(service_uuid)
    char_uuid = _normalize_uuid(char_uuid)
    
    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        cur.execute(
            "INSERT INTO char_history(mac,service_uuid,char_uuid,ts,value,source) VALUES (?,?,?,?,?,?)",
            (
                mac,
                service_uuid,
                char_uuid,
                utc_now_iso(),
                value,
                source,
            ),
        )
    
    if _connection._DB_CONN is not None:
        _connection._DB_CONN.commit()


def get_characteristic_timeline(mac: str, service_uuid: str = None, char_uuid: str = None, 
                               limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get characteristic value timeline for a device.
    
    Args:
        mac: Device MAC address
        service_uuid: Optional service UUID filter
        char_uuid: Optional characteristic UUID filter
        limit: Maximum number of timeline entries to return
        
    Returns:
        List of characteristic value history entries
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return []

    query = "SELECT * FROM char_history WHERE mac=?"
    params = [mac]
    
    if service_uuid:
        query += " AND service_uuid=?"
        params.append(_normalize_uuid(service_uuid))
        
    if char_uuid:
        query += " AND char_uuid=?"
        params.append(_normalize_uuid(char_uuid))
    
    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
