"""BLEEP observation database helper (SQLite).

The module is imported lazily from scan/enum paths; any failure to create or
open the DB is swallowed – BLEEP must *never* crash because persistence is
unavailable on the host system.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

__all__ = [
    "upsert_device",
    "insert_adv",
    "upsert_services",
    "upsert_characteristics",
    "snapshot_media_player",
    "snapshot_media_transport",
    "get_devices",
    "get_device_detail",
    "get_characteristic_timeline",
    "export_device_data",
]

_DB_LOCK = threading.Lock()
_DB_CONN: sqlite3.Connection | None = None

_DB_PATH = Path(os.getenv("BLEEP_DB_PATH", Path.home() / ".bleep" / "observations.db"))

_SCHEMA_VERSION = 2  # Updated to reflect renamed columns

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);

CREATE TABLE IF NOT EXISTS devices (
    mac TEXT PRIMARY KEY,
    addr_type TEXT,
    name TEXT,
    appearance INT,
    device_class INT,  -- Renamed from 'class' to avoid Python keyword
    manufacturer_id INT,
    manufacturer_data BLOB,
    rssi_last INT,
    rssi_min INT,
    rssi_max INT,
    first_seen DATETIME,
    last_seen  DATETIME,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS adv_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    ts DATETIME,
    rssi INT,
    data BLOB,
    decoded JSON
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    uuid TEXT,
    handle_start INT,
    handle_end INT,
    name TEXT,
    first_seen DATETIME,
    last_seen DATETIME,
    UNIQUE(mac,uuid)
 );

CREATE UNIQUE INDEX IF NOT EXISTS idx_services_mac_uuid ON services(mac,uuid);

CREATE TABLE IF NOT EXISTS characteristics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INT REFERENCES services(id) ON DELETE CASCADE,
    uuid TEXT,
    handle INT,
    properties TEXT,
    value BLOB,
    last_read DATETIME,
    permission_map TEXT,
    UNIQUE(service_id,uuid)
 );

CREATE TABLE IF NOT EXISTS media_players (
    path TEXT PRIMARY KEY,
    mac TEXT,
    name TEXT,
    subtype TEXT,
    status TEXT,
    position INT,
    metadata JSON,
    ts DATETIME
);

CREATE TABLE IF NOT EXISTS classic_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    uuid TEXT,
    channel INT,
    name TEXT,
    ts DATETIME,
    UNIQUE(mac,uuid,channel)
);

CREATE TABLE IF NOT EXISTS pbap_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    repo TEXT,
    entries INT,
    hash TEXT,
    ts DATETIME,
    UNIQUE(mac,repo)
);

CREATE TABLE IF NOT EXISTS char_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    service_uuid TEXT,
    char_uuid TEXT,
    ts DATETIME,
    value BLOB
);

CREATE TABLE IF NOT EXISTS media_transports (
    path TEXT PRIMARY KEY,
    mac TEXT,
    transport_state TEXT,  -- Renamed from 'state' to avoid Python module name conflict
    volume INT,
    codec INT,
    ts DATETIME
);
"""


def _init_db() -> None:
    """Initialize the database using v2 schema."""
    global _DB_CONN
    if _DB_CONN is not None:
        return

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    with conn:
        # Create tables with v2 schema
        conn.executescript(_SCHEMA_SQL)

        # Set or update version
        ver_row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if not ver_row:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (_SCHEMA_VERSION,))
        elif ver_row["version"] != _SCHEMA_VERSION:
            conn.execute("UPDATE schema_version SET version = ?", (_SCHEMA_VERSION,))
    
    _DB_CONN = conn

# Migration code removed as we now use v2 schema exclusively


@contextmanager
def _db_cursor():
    """Context manager yielding a DB cursor with automatic commit."""
    try:
        if _DB_CONN is None:
            _init_db()
        cursor = _DB_CONN.cursor()  # type: ignore[union-attr]
        yield cursor
        _DB_CONN.commit()  # type: ignore[union-attr]
    except Exception as e:
        # Log the exception but don't swallow it - we need to know about failures
        print(f"DB Error: {e}")
        import traceback
        print(traceback.format_exc())
        # Reraise to prevent silent failures
        raise


# ---------------------------------------------------------------------------
# Public helper functions ----------------------------------------------------
# ---------------------------------------------------------------------------

def upsert_device(mac: str, **cols):
    """
    Update or insert a device record in the database.
    
    Args:
        mac: Device MAC address
        **cols: Column values to set
    """
    now = datetime.utcnow().isoformat()
    cols.setdefault("last_seen", now)
        
    cols_keys = ",".join(cols.keys())
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{k}=excluded.{k}" for k in cols.keys())
    
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(
            f"INSERT INTO devices(mac,{cols_keys}) VALUES (? ,{placeholders}) "
            f"ON CONFLICT(mac) DO UPDATE SET {updates}",
            (mac, *cols.values()),
        )


def insert_adv(mac: str, rssi: int, data: bytes, decoded: Dict[str, Any]):
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(
            "INSERT INTO adv_reports(mac,ts,rssi,data,decoded) VALUES (?,?,?,?,?)",
            (
                mac,
                datetime.utcnow().isoformat(),
                rssi,
                data,
                json_dumps(decoded),
            ),
        )


def upsert_services(mac: str, svc_list: List[Dict[str, Any]]) -> Dict[str, int]:
    """Insert/UPSERT services and return a mapping uuid → row id."""
    ids: Dict[str, int] = {}
    with _DB_LOCK, _db_cursor() as cur:
        for svc in svc_list:
            cur.execute(
                """
                INSERT INTO services(mac,uuid,handle_start,handle_end,name,first_seen,last_seen)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(mac,uuid) DO UPDATE SET last_seen=excluded.last_seen
                """,
                (
                    mac,
                    svc["uuid"],
                    svc.get("handle_start"),
                    svc.get("handle_end"),
                    svc.get("name"),
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )
            # Retrieve id (whether newly inserted or existing)
            sid = cur.lastrowid
            if not sid:
                row = cur.execute(
                    "SELECT id FROM services WHERE mac=? AND uuid=?",
                    (mac, svc["uuid"]),
                ).fetchone()
                if row:
                    sid = row["id"]  # type: ignore[index]
            if sid:
                ids[svc["uuid"]] = sid
    return ids


def upsert_characteristics(service_id: int, char_list: List[Dict[str, Any]]):
    with _DB_LOCK, _db_cursor() as cur:
        for ch in char_list:
            cur.execute(
                """
                INSERT INTO characteristics(service_id,uuid,handle,properties,value,last_read)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(service_id,uuid) DO UPDATE SET value=excluded.value,last_read=excluded.last_read
                """,
                (
                    service_id,
                    ch["uuid"],
                    ch.get("handle"),
                    ",".join(ch.get("properties", [])),
                    ch.get("value"),
                    datetime.utcnow().isoformat(),
                ),
            )


def snapshot_media_player(player):  # type: ignore[valid-type]
    try:
        row = {
            "path": player.player_path,
            "mac": player.get_device() or "UNKNOWN",
            "name": player.get_name(),
            "subtype": player.get_subtype() if hasattr(player, "get_subtype") else None,
            "status": player.get_status(),
            "position": player.get_position(),
            "metadata": json_dumps(player.get_track()),
            "ts": datetime.utcnow().isoformat(),
        }
    except Exception:
        return
    with _DB_LOCK, _db_cursor() as cur:
        cols = ",".join(row.keys())
        ph = ",".join("?" for _ in row)
        updates = ",".join(f"{k}=excluded.{k}" for k in row.keys())
        cur.execute(
            f"INSERT INTO media_players({cols}) VALUES ({ph}) ON CONFLICT(path) DO UPDATE SET {updates}",
            tuple(row.values()),
        )


def snapshot_media_transport(transport):  # type: ignore[valid-type]
    """
    Create a snapshot of media transport state in the database.
    
    Args:
        transport: Media transport object
    """
    try:
        row = {
            "path": transport.transport_path,
            "mac": transport.get_device() or "UNKNOWN",
            "transport_state": transport.get_state(),  # Updated column name
            "volume": transport.get_volume(),
            "codec": transport.get_codec(),
            "ts": datetime.utcnow().isoformat(),
        }
    except Exception:
        return

    with _DB_LOCK, _db_cursor() as cur:
        cols = ",".join(row.keys())
        ph = ",".join("?" for _ in row)
        updates = ",".join(f"{k}=excluded.{k}" for k in row.keys())
        cur.execute(
            f"INSERT INTO media_transports({cols}) VALUES ({ph}) ON CONFLICT(path) DO UPDATE SET {updates}",
            tuple(row.values()),
        )


def upsert_classic_services(mac: str, services: List[Dict[str, Any]]):
    with _DB_LOCK, _db_cursor() as cur:
        for svc in services:
            cur.execute(
                """
                INSERT OR REPLACE INTO classic_services(mac,uuid,channel,name,ts)
                VALUES (?,?,?,?,?)
                """,
                (
                    mac,
                    svc["uuid"],
                    svc["channel"],
                    svc.get("name"),
                    datetime.utcnow().isoformat(),
                ),
            )
    # ensure visibility for external readers
    if _DB_CONN is not None:
        _DB_CONN.commit()


def insert_char_history(mac: str, service_uuid: str, char_uuid: str, value: bytes):
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(
            "INSERT INTO char_history(mac,service_uuid,char_uuid,ts,value) VALUES (?,?,?,?,?)",
            (
                mac,
                service_uuid,
                char_uuid,
                datetime.utcnow().isoformat(),
                value,
            ),
        )


def upsert_pbap_metadata(mac: str, repo: str, entries: int, vcf_hash: str):
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO pbap_metadata(mac,repo,entries,hash,ts)
            VALUES (?,?,?,?,?)
            ON CONFLICT(mac,repo) DO UPDATE SET entries=excluded.entries,hash=excluded.hash,ts=excluded.ts
            """,
            (mac, repo, entries, vcf_hash, datetime.utcnow().isoformat()),
        )


# ---------------------------------------------------------------------------
# Helpers -------------------------------------------------------------------
# ---------------------------------------------------------------------------

import json as _json

def json_dumps(obj: Any) -> str:
    try:
        return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return "{}"

# ---------------------------------------------------------------------------
# Data retrieval functions --------------------------------------------------
# ---------------------------------------------------------------------------

def get_devices(status: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get list of devices from the database.
    
    Args:
        status: Optional filter for device status (comma-separated)
          'recent' - Devices seen in the last 24 hours
          'ble' - Bluetooth Low Energy devices
          'classic' - Bluetooth Classic devices
          'media' - Devices with media capabilities
        limit: Maximum number of devices to return
        
    Returns:
        List of device dictionaries (empty list if error occurs)
    """
    try:
        # Build the query using v2 schema column names
        query = "SELECT * FROM devices"
        params = []
        
        if status:
            status_filters = []
            for s in status.split(','):
                s = s.strip().lower()
                if s == 'recent':
                    # Devices seen in the last 24 hours
                    status_filters.append("last_seen > datetime('now', '-1 day')")
                elif s == 'ble':
                    status_filters.append("addr_type IS NOT NULL")
                elif s == 'classic':
                    status_filters.append("device_class IS NOT NULL")
                elif s == 'media':
                    # Join with media_players to filter devices with media capabilities
                    query = """
                    SELECT d.* FROM devices d
                    INNER JOIN media_players mp ON d.mac = mp.mac
                    """
                    
            if status_filters:
                query += " WHERE " + " OR ".join(status_filters)
        
        query += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)
        
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
    result = {
        'device': None,
        'services': [],
        'characteristics': [],
        'classic_services': [],
        'pbap_metadata': [],
        'media_players': [],
        'media_transports': []
    }
    
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
            
            # Get characteristics for each service
            for svc in services:
                cur.execute(
                    "SELECT * FROM characteristics WHERE service_id=? ORDER BY handle", 
                    (svc['id'],)
                )
                chars = [dict(row) for row in cur.fetchall()]
                result['characteristics'].extend(chars)
            
            # Get classic services
            cur.execute("SELECT * FROM classic_services WHERE mac=?", (mac,))
            result['classic_services'] = [dict(row) for row in cur.fetchall()]
            
            # Get PBAP metadata
            cur.execute("SELECT * FROM pbap_metadata WHERE mac=?", (mac,))
            result['pbap_metadata'] = [dict(row) for row in cur.fetchall()]
            
            # Get media players
            cur.execute("SELECT * FROM media_players WHERE mac=?", (mac,))
            result['media_players'] = [dict(row) for row in cur.fetchall()]
            
            # Get media transports
            cur.execute("SELECT * FROM media_transports WHERE mac=?", (mac,))
            result['media_transports'] = [dict(row) for row in cur.fetchall()]
            
    return result


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
    query = "SELECT * FROM char_history WHERE mac=?"
    params = [mac]
    
    if service_uuid:
        query += " AND service_uuid=?"
        params.append(service_uuid)
        
    if char_uuid:
        query += " AND char_uuid=?"
        params.append(char_uuid)
    
    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def export_device_data(mac: str) -> Dict[str, Any]:
    """
    Export all data for a device in a format suitable for JSON export.
    
    Args:
        mac: Device MAC address
        
    Returns:
        Dictionary with all device data
    """
    device_detail = get_device_detail(mac)
    
    # Get characteristic history
    with _DB_LOCK, _db_cursor() as cur:
        cur.execute(
            "SELECT * FROM char_history WHERE mac=? ORDER BY ts DESC LIMIT 500", 
            (mac,)
        )
        device_detail['characteristic_history'] = [dict(row) for row in cur.fetchall()]
        
        # Get advertisement reports
        cur.execute(
            "SELECT * FROM adv_reports WHERE mac=? ORDER BY ts DESC LIMIT 100", 
            (mac,)
        )
        device_detail['adv_reports'] = [dict(row) for row in cur.fetchall()]
    
    return device_detail
