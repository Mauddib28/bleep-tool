"""Database connection, schema, and migration logic for the BLEEP observation DB.

This module is internal to the observations package. External code should
import from ``bleep.core.observations`` directly.
"""
from __future__ import annotations

import json as _json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core.time_utils import utc_now_iso

# ---------------------------------------------------------------------------
# Module-level state --------------------------------------------------------
# ---------------------------------------------------------------------------

# Reentrant so a ``_db_cursor`` opened while already holding the lock (e.g. lazy
# ``_init_db`` on first use, or nested helper calls) does not self-deadlock.
_DB_LOCK = threading.RLock()
_DB_CONN: sqlite3.Connection | None = None

def _get_db_path() -> Path:
    return Path(os.getenv("BLEEP_DB_PATH", Path.home() / ".bleep" / "observations.db"))

_DB_PATH = _get_db_path()

_SCHEMA_VERSION = 20  # v20: devices.enumerated_at (last successful GATT)

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
    notes TEXT,
    device_type TEXT,  -- 'unknown', 'classic', 'le', or 'dual'
    tx_power INT,             -- Added in schema v10
    modalias TEXT,            -- Added in schema v10
    icon TEXT,                -- Added in schema v10
    service_data JSON,        -- Added in schema v10
    advertising_data JSON,    -- Added in schema v10
    uuids JSON,               -- Added in schema v12: advertised UUID list
    paired BOOLEAN,           -- Added in schema v12: connection state
    trusted BOOLEAN,          -- Added in schema v12: connection state
    bonded BOOLEAN,           -- Added in schema v12: connection state
    sighting_count INT,       -- Added in schema v12: survey metadata
    fingerprint_changed BOOLEAN,  -- Added in schema v12: survey metadata
    lmp_version INT,          -- Added in schema v14: remote LMP version byte
    lmp_subversion INT,       -- Added in schema v14: remote LMP subversion
    bt_manufacturer INT,      -- Added in schema v14: remote controller manufacturer ID
    bt_spec_version TEXT,     -- Added in schema v14: human-readable spec (e.g. "Bluetooth 5.0")
    lmp_features TEXT,        -- Added in schema v14: JSON feature page hex strings
    version_queried_at DATETIME,  -- Added in schema v14: last version query timestamp
    firmware_revision TEXT,    -- Added in schema v15: DIS Firmware Revision String (0x2A26)
    software_revision TEXT,   -- Added in schema v15: DIS Software Revision String (0x2A28)
    model_number TEXT,        -- Added in schema v15: DIS Model Number String (0x2A24)
    dis_manufacturer_name TEXT, -- Added in schema v15: DIS Manufacturer Name (0x2A29)
    pnp_vendor_source INT,    -- Added in schema v15: PnP ID vendor source (1=BT SIG, 2=USB-IF)
    pnp_vendor_id INT,        -- Added in schema v15: PnP ID vendor ID
    pnp_product_id INT,       -- Added in schema v15: PnP ID product ID
    pnp_product_version INT,  -- Added in schema v15: PnP ID product version
    seen_by JSON,             -- Added in schema v19: adapters that observed this device
    enumerated_by TEXT,       -- Added in schema v19: adapter that last GATT-enumerated
    enumerated_at DATETIME    -- Added in schema v20: when GATT last succeeded
);

CREATE TABLE IF NOT EXISTS adv_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    ts DATETIME,
    rssi INT,
    data BLOB,
    decoded JSON,
    adapter TEXT              -- Added in schema v19: collecting adapter (hciN)
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
    is_primary BOOLEAN DEFAULT 1,  -- Added in schema v10
    includes TEXT,                  -- Added in schema v10 (JSON array of included service UUIDs)
    UNIQUE(mac,uuid)
 );

CREATE UNIQUE INDEX IF NOT EXISTS idx_services_mac_uuid ON services(mac,uuid);

-- Performance indexes for frequently queried fields
CREATE INDEX IF NOT EXISTS idx_devices_device_type ON devices(device_type);
CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen);
CREATE INDEX IF NOT EXISTS idx_adv_reports_mac ON adv_reports(mac);
CREATE INDEX IF NOT EXISTS idx_adv_reports_ts ON adv_reports(ts);

CREATE TABLE IF NOT EXISTS characteristics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INT REFERENCES services(id) ON DELETE CASCADE,
    uuid TEXT,
    handle INT,
    properties TEXT,
    value BLOB,
    last_read DATETIME,
    permission_map TEXT,
    mtu INT,
    UNIQUE(service_id,uuid)
 );

CREATE TABLE IF NOT EXISTS descriptors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    characteristic_id INT REFERENCES characteristics(id) ON DELETE CASCADE,
    uuid TEXT,
    handle INT,
    flags TEXT,
    value BLOB,
    last_read DATETIME,
    UNIQUE(characteristic_id,uuid)
);

CREATE INDEX IF NOT EXISTS idx_descriptors_char_id ON descriptors(characteristic_id);

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
    value BLOB,
    source TEXT DEFAULT 'unknown'
);

-- Performance indexes for char_history table (added in schema v5)
CREATE INDEX IF NOT EXISTS idx_char_history_mac_service_char ON char_history(mac, service_uuid, char_uuid);
CREATE INDEX IF NOT EXISTS idx_char_history_ts ON char_history(ts);
CREATE INDEX IF NOT EXISTS idx_char_history_source ON char_history(source);

-- sdp_records table (added in schema v7) - Full SDP record snapshots with all attributes
CREATE TABLE IF NOT EXISTS sdp_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    service_record_handle INT,
    uuid TEXT,
    channel INT,
    name TEXT,
    profile_descriptors JSON,
    service_version INT,
    service_description TEXT,
    protocol_descriptors JSON,
    raw_record TEXT,
    ts DATETIME,
    mas_instance_id INT,          -- Added in schema v12: MAP-specific
    supported_message_types TEXT,  -- Added in schema v12: MAP-specific
    supported_features TEXT,       -- Added in schema v12: MAP-specific
    source TEXT                    -- Added in schema v18: provenance of the record
                                   --   ("dbus"|"browse"|"xml"|"records" or "a+b" when merged)
    -- NOTE (schema v16): no UNIQUE(mac, service_record_handle). sdp_records is
    -- append-only/versioned: each genuine change is a new timestamped snapshot so
    -- change-over-time history is preserved (see upsert_sdp_record). The
    -- (mac, service_record_handle) index below is non-unique for query speed only.
);

CREATE INDEX IF NOT EXISTS idx_sdp_records_mac ON sdp_records(mac);
CREATE INDEX IF NOT EXISTS idx_sdp_records_uuid ON sdp_records(uuid);
CREATE INDEX IF NOT EXISTS idx_sdp_records_ts ON sdp_records(ts);
CREATE INDEX IF NOT EXISTS idx_sdp_records_mac_handle ON sdp_records(mac, service_record_handle);

CREATE TABLE IF NOT EXISTS media_transports (
    path TEXT PRIMARY KEY,
    mac TEXT,
    transport_state TEXT,  -- Renamed from 'state' to avoid Python module name conflict
    volume INT,
    codec INT,
    ts DATETIME
);

CREATE TABLE IF NOT EXISTS aoi_analysis (
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    analysis_timestamp DATETIME,
    security_concerns JSON,
    unusual_characteristics JSON,
    notable_services JSON,
    recommendations JSON,
    pairing_profile JSON,
    sdp_summary JSON,
    post_pair_delta JSON,
    analysis_details JSON,
    PRIMARY KEY (mac)
);

-- Append-only history of every stored AoI analysis (schema v17). `aoi_analysis`
-- above remains the single latest row per device (so get_aoi_analysis /
-- has_aoi_analysis are unchanged); this table records each analysis over time so
-- re-scans can be compared. See store_aoi_analysis / get_aoi_analysis_history.
CREATE TABLE IF NOT EXISTS aoi_analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    analysis_timestamp DATETIME,
    security_concerns JSON,
    unusual_characteristics JSON,
    notable_services JSON,
    recommendations JSON,
    pairing_profile JSON,
    sdp_summary JSON,
    post_pair_delta JSON,
    analysis_details JSON
);

CREATE INDEX IF NOT EXISTS idx_aoi_analysis_history_mac ON aoi_analysis_history(mac);
CREATE INDEX IF NOT EXISTS idx_aoi_analysis_history_ts ON aoi_analysis_history(analysis_timestamp);

CREATE TABLE IF NOT EXISTS device_type_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    evidence_type TEXT NOT NULL,
    evidence_weight TEXT NOT NULL,
    source TEXT NOT NULL,
    value TEXT,
    metadata TEXT,
    ts DATETIME NOT NULL,
    UNIQUE(mac, evidence_type, source)
);

CREATE INDEX IF NOT EXISTS idx_device_type_evidence_mac ON device_type_evidence(mac);
CREATE INDEX IF NOT EXISTS idx_device_type_evidence_type ON device_type_evidence(evidence_type);
CREATE INDEX IF NOT EXISTS idx_device_type_evidence_ts ON device_type_evidence(ts);

-- pairing_events table (added in schema v12) - Full pairing workflow per attempt
CREATE TABLE IF NOT EXISTS pairing_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    ts DATETIME NOT NULL,
    method TEXT,
    pin TEXT,
    result TEXT,
    capabilities TEXT,
    auth_matrix JSON,
    brute_attempts INT,
    brute_duration REAL,
    pre_pair_state JSON,
    post_pair_state JSON
);

CREATE INDEX IF NOT EXISTS idx_pairing_events_mac ON pairing_events(mac);
CREATE INDEX IF NOT EXISTS idx_pairing_events_ts ON pairing_events(ts);

-- security_maps table (added in schema v12) - Per-enumeration security analysis
CREATE TABLE IF NOT EXISTS security_maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    ts DATETIME NOT NULL,
    landmine_map JSON,
    permission_map JSON,
    enumeration_annotations JSON,
    source TEXT
);

CREATE INDEX IF NOT EXISTS idx_security_maps_mac ON security_maps(mac);
CREATE INDEX IF NOT EXISTS idx_security_maps_ts ON security_maps(ts);

-- media_enumerations table (added in schema v12) - Full media-enum snapshots
CREATE TABLE IF NOT EXISTS media_enumerations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    ts DATETIME NOT NULL,
    players JSON,
    transports JSON,
    endpoints JSON,
    browse_tree JSON,
    capabilities JSON
);

CREATE INDEX IF NOT EXISTS idx_media_enumerations_mac ON media_enumerations(mac);
CREATE INDEX IF NOT EXISTS idx_media_enumerations_ts ON media_enumerations(ts);

-- audio_recon table (added in schema v12) - Host-level audio recon (mac is NULL)
CREATE TABLE IF NOT EXISTS audio_recon (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts DATETIME NOT NULL,
    backend TEXT,
    cards JSON,
    pcms JSON,
    recordings JSON,
    sox_analysis JSON,
    contention JSON
);

CREATE INDEX IF NOT EXISTS idx_audio_recon_ts ON audio_recon(ts);
"""


# ---------------------------------------------------------------------------
# Initialization and migration ----------------------------------------------
# ---------------------------------------------------------------------------
# Migration pattern: sequential `if current_version == N:` blocks.
# For ALTER TABLE additions, wrap each in individual try/except pass to handle
# the case where a column already exists (SQLite cannot do IF NOT EXISTS on
# ALTER TABLE). This pattern is established and proven across v2→v11.
# Next migration (v12) for Phase 2 should follow the same structure.
# ---------------------------------------------------------------------------

def _init_db():
    """Initialize the database using latest schema."""
    global _DB_CONN, _DB_PATH
    if _DB_CONN is not None:
        return

    _DB_PATH = _get_db_path()
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    with conn:
        conn.executescript(_SCHEMA_SQL)

        ver_row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        stored_version = ver_row["version"] if ver_row else 0
        current_version = stored_version
        
        # Migration from v2 to v3 - Add device_type column
        if current_version == 2:
            try:
                conn.execute("ALTER TABLE devices ADD COLUMN device_type TEXT DEFAULT 'unknown'")
                conn.execute("""
                    UPDATE devices SET device_type = 
                    CASE
                        WHEN device_class IS NOT NULL AND addr_type IS NULL THEN 'classic'
                        WHEN addr_type IS NOT NULL AND device_class IS NULL THEN 'le'
                        WHEN device_class IS NOT NULL AND addr_type IS NOT NULL THEN 'dual'
                        ELSE 'unknown'
                    END
                """)
                current_version = 3
            except Exception as e:
                print(f"Migration v2 to v3 failed: {e}")
                
        # Migration from v3 to v4 - Add aoi_analysis table
        if current_version == 3:
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS aoi_analysis (
                        mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
                        analysis_timestamp DATETIME,
                        security_concerns JSON,
                        unusual_characteristics JSON,
                        notable_services JSON,
                        recommendations JSON,
                        PRIMARY KEY (mac)
                    )
                """)
                current_version = 4
            except Exception as e:
                print(f"Migration v3 to v4 failed: {e}")
                
        # Migration from v4 to v5 - Add performance indexes
        if current_version == 4:
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_device_type ON devices(device_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_adv_reports_mac ON adv_reports(mac)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_adv_reports_ts ON adv_reports(ts)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_char_history_mac_service_char ON char_history(mac, service_uuid, char_uuid)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_char_history_ts ON char_history(ts)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_char_history_source ON char_history(source)")
                
                print("[+] Database indexes created for improved performance")
                current_version = 5
            except Exception as e:
                print(f"Migration v4 to v5 failed: {e}")
        
        # Migration from v5 to v6 - Add device_type_evidence table
        if current_version == 5:
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS device_type_evidence (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
                        evidence_type TEXT NOT NULL,
                        evidence_weight TEXT NOT NULL,
                        source TEXT NOT NULL,
                        value TEXT,
                        metadata TEXT,
                        ts DATETIME NOT NULL,
                        UNIQUE(mac, evidence_type, source)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_device_type_evidence_mac ON device_type_evidence(mac)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_device_type_evidence_type ON device_type_evidence(evidence_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_device_type_evidence_ts ON device_type_evidence(ts)")
                
                print("[+] Database schema v6: device_type_evidence table created for classification audit trail")
                current_version = 6
            except Exception as e:
                print(f"Migration v5 to v6 failed: {e}")

        # Migration from v6 to v7 - Add sdp_records table
        if current_version == 6:
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sdp_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
                        service_record_handle INT,
                        uuid TEXT,
                        channel INT,
                        name TEXT,
                        profile_descriptors JSON,
                        service_version INT,
                        service_description TEXT,
                        protocol_descriptors JSON,
                        raw_record TEXT,
                        ts DATETIME,
                        UNIQUE(mac, service_record_handle)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sdp_records_mac ON sdp_records(mac)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sdp_records_uuid ON sdp_records(uuid)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sdp_records_ts ON sdp_records(ts)")
                
                print("[+] Database schema v7: sdp_records table created for full SDP record snapshots")
                current_version = 7
            except Exception as e:
                print(f"Migration v6 to v7 failed: {e}")

        # Migration from v7 to v8 — Normalize all MAC addresses to uppercase
        if current_version == 7:
            try:
                _mac_tables = [
                    ("devices", "mac"),
                    ("adv_reports", "mac"),
                    ("services", "mac"),
                    ("classic_services", "mac"),
                    ("pbap_metadata", "mac"),
                    ("char_history", "mac"),
                    ("sdp_records", "mac"),
                    ("media_players", "mac"),
                    ("media_transports", "mac"),
                    ("aoi_analysis", "mac"),
                    ("device_type_evidence", "mac"),
                ]
                for tbl, col in _mac_tables:
                    conn.execute(f"UPDATE {tbl} SET {col} = UPPER({col}) WHERE {col} IS NOT NULL AND {col} != UPPER({col})")
                print("[+] Database schema v8: MAC addresses normalised to uppercase")
                current_version = 8
            except Exception as e:
                print(f"Migration v7 to v8 failed: {e}")

        # Migration from v8 to v9 — Normalize all UUIDs to uppercase
        if current_version == 8:
            try:
                _uuid_tables = [
                    ("services", "uuid"),
                    ("characteristics", "uuid"),
                    ("classic_services", "uuid"),
                    ("sdp_records", "uuid"),
                    ("char_history", "service_uuid"),
                    ("char_history", "char_uuid"),
                ]
                for tbl, col in _uuid_tables:
                    conn.execute(
                        f"UPDATE {tbl} SET {col} = UPPER({col}) "
                        f"WHERE {col} IS NOT NULL AND {col} != UPPER({col})"
                    )
                print("[+] Database schema v9: UUIDs normalised to uppercase")
                current_version = 9
            except Exception as e:
                print(f"Migration v8 to v9 failed: {e}")

        # Migration from v9 to v10 — descriptors, device enrichment, service metadata
        if current_version == 9:
            try:
                for col_def in [
                    "tx_power INT",
                    "modalias TEXT",
                    "icon TEXT",
                    "service_data JSON",
                    "advertising_data JSON",
                ]:
                    try:
                        conn.execute(f"ALTER TABLE devices ADD COLUMN {col_def}")
                    except Exception:
                        pass

                for col_def in [
                    "is_primary BOOLEAN DEFAULT 1",
                    "includes TEXT",
                ]:
                    try:
                        conn.execute(f"ALTER TABLE services ADD COLUMN {col_def}")
                    except Exception:
                        pass

                try:
                    conn.execute("ALTER TABLE characteristics ADD COLUMN mtu INT")
                except Exception:
                    pass

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS descriptors (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        characteristic_id INT REFERENCES characteristics(id) ON DELETE CASCADE,
                        uuid TEXT,
                        handle INT,
                        flags TEXT,
                        value BLOB,
                        last_read DATETIME,
                        UNIQUE(characteristic_id,uuid)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_descriptors_char_id ON descriptors(characteristic_id)")

                print("[+] Database schema v10: descriptors table, device/service/char enrichment columns")
                current_version = 10
            except Exception as e:
                print(f"Migration v9 to v10 failed: {e}")

        # Migration from v10 to v11 — AoI augmentation columns
        if current_version == 10:
            try:
                for col_def in [
                    "pairing_profile JSON",
                    "sdp_summary JSON",
                    "post_pair_delta JSON",
                ]:
                    try:
                        conn.execute(f"ALTER TABLE aoi_analysis ADD COLUMN {col_def}")
                    except Exception:
                        pass
                print("[+] Database schema v11: AoI pairing_profile, sdp_summary, post_pair_delta columns")
                current_version = 11
            except Exception as e:
                print(f"Migration v10 to v11 failed: {e}")

        # Migration from v11 to v12 — Phase 2 persistence gap closure
        if current_version == 11:
            try:
                # New columns on devices table
                for col_def in [
                    "uuids JSON",
                    "paired BOOLEAN",
                    "trusted BOOLEAN",
                    "bonded BOOLEAN",
                    "sighting_count INT",
                    "fingerprint_changed BOOLEAN",
                ]:
                    try:
                        conn.execute(f"ALTER TABLE devices ADD COLUMN {col_def}")
                    except Exception:
                        pass

                # New columns on sdp_records table
                for col_def in [
                    "mas_instance_id INT",
                    "supported_message_types TEXT",
                    "supported_features TEXT",
                ]:
                    try:
                        conn.execute(f"ALTER TABLE sdp_records ADD COLUMN {col_def}")
                    except Exception:
                        pass

                # New tables
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pairing_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
                        ts DATETIME NOT NULL,
                        method TEXT,
                        pin TEXT,
                        result TEXT,
                        capabilities TEXT,
                        auth_matrix JSON,
                        brute_attempts INT,
                        brute_duration REAL,
                        pre_pair_state JSON,
                        post_pair_state JSON
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_pairing_events_mac ON pairing_events(mac)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_pairing_events_ts ON pairing_events(ts)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS security_maps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
                        ts DATETIME NOT NULL,
                        landmine_map JSON,
                        permission_map JSON,
                        enumeration_annotations JSON,
                        source TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_security_maps_mac ON security_maps(mac)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_security_maps_ts ON security_maps(ts)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS media_enumerations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
                        ts DATETIME NOT NULL,
                        players JSON,
                        transports JSON,
                        endpoints JSON,
                        browse_tree JSON,
                        capabilities JSON
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_media_enumerations_mac ON media_enumerations(mac)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_media_enumerations_ts ON media_enumerations(ts)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS audio_recon (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts DATETIME NOT NULL,
                        backend TEXT,
                        cards JSON,
                        pcms JSON,
                        recordings JSON,
                        sox_analysis JSON,
                        contention JSON
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_recon_ts ON audio_recon(ts)")

                print("[+] Database schema v12: pairing_events, security_maps, media_enumerations, audio_recon tables; device/sdp columns")
                current_version = 12
            except Exception as e:
                print(f"Migration v11 to v12 failed: {e}")

        # Migration from v12 to v13 — analysis_details column on aoi_analysis
        if current_version == 12:
            try:
                try:
                    conn.execute("ALTER TABLE aoi_analysis ADD COLUMN analysis_details JSON")
                except Exception:
                    pass
                print("[+] Database schema v13: aoi_analysis.analysis_details column")
                current_version = 13
            except Exception as e:
                print(f"Migration v12 to v13 failed: {e}")

        # Migration from v13 to v14 — remote BT version columns on devices
        if current_version == 13:
            try:
                for col_def in [
                    "lmp_version INT",
                    "lmp_subversion INT",
                    "bt_manufacturer INT",
                    "bt_spec_version TEXT",
                    "lmp_features TEXT",
                    "version_queried_at DATETIME",
                ]:
                    try:
                        conn.execute(f"ALTER TABLE devices ADD COLUMN {col_def}")
                    except Exception:
                        pass
                print("[+] Database schema v14: remote BT version columns on devices")
                current_version = 14
            except Exception as e:
                print(f"Migration v13 to v14 failed: {e}")

        # Migration from v14 to v15 — DIS version columns on devices
        if current_version == 14:
            try:
                for col_def in [
                    "firmware_revision TEXT",
                    "software_revision TEXT",
                    "model_number TEXT",
                    "dis_manufacturer_name TEXT",
                    "pnp_vendor_source INT",
                    "pnp_vendor_id INT",
                    "pnp_product_id INT",
                    "pnp_product_version INT",
                ]:
                    try:
                        conn.execute(f"ALTER TABLE devices ADD COLUMN {col_def}")
                    except Exception:
                        pass
                print("[+] Database schema v15: DIS version columns on devices")
                current_version = 15
            except Exception as e:
                print(f"Migration v14 to v15 failed: {e}")

        # Migration from v15 to v16 — sdp_records becomes append-only/versioned.
        # SQLite cannot drop a table constraint in place, so rebuild the table
        # without UNIQUE(mac, service_record_handle), preserving every existing row.
        # A non-unique (mac, service_record_handle) index replaces the old constraint
        # for query performance. See upsert_sdp_record for the append-only write path.
        if current_version == 15:
            try:
                _sdp_cols = (
                    "id, mac, service_record_handle, uuid, channel, name, "
                    "profile_descriptors, service_version, service_description, "
                    "protocol_descriptors, raw_record, ts, mas_instance_id, "
                    "supported_message_types, supported_features"
                )
                conn.execute("ALTER TABLE sdp_records RENAME TO sdp_records_v15")
                conn.execute("""
                    CREATE TABLE sdp_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
                        service_record_handle INT,
                        uuid TEXT,
                        channel INT,
                        name TEXT,
                        profile_descriptors JSON,
                        service_version INT,
                        service_description TEXT,
                        protocol_descriptors JSON,
                        raw_record TEXT,
                        ts DATETIME,
                        mas_instance_id INT,
                        supported_message_types TEXT,
                        supported_features TEXT
                    )
                """)
                conn.execute(
                    f"INSERT INTO sdp_records ({_sdp_cols}) "
                    f"SELECT {_sdp_cols} FROM sdp_records_v15"
                )
                conn.execute("DROP TABLE sdp_records_v15")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sdp_records_mac ON sdp_records(mac)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sdp_records_uuid ON sdp_records(uuid)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sdp_records_ts ON sdp_records(ts)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sdp_records_mac_handle ON sdp_records(mac, service_record_handle)")
                print("[+] Database schema v16: sdp_records rebuilt append-only (UNIQUE(mac,handle) dropped)")
                current_version = 16
            except Exception as e:
                print(f"Migration v15 to v16 failed: {e}")

        # Migration from v16 to v17 — add append-only AoI analysis history.
        # aoi_analysis stays latest-only; a new aoi_analysis_history table records
        # every analysis over time. The table itself is created by _SCHEMA_SQL
        # above (IF NOT EXISTS); here we backfill the existing latest row so it
        # becomes the first history entry (no data lost). Runs once (version-gated).
        if current_version == 16:
            try:
                conn.execute(
                    """
                    INSERT INTO aoi_analysis_history(
                        mac, analysis_timestamp, security_concerns,
                        unusual_characteristics, notable_services, recommendations,
                        pairing_profile, sdp_summary, post_pair_delta, analysis_details)
                    SELECT mac, analysis_timestamp, security_concerns,
                           unusual_characteristics, notable_services, recommendations,
                           pairing_profile, sdp_summary, post_pair_delta, analysis_details
                    FROM aoi_analysis
                    """
                )
                print("[+] Database schema v17: aoi_analysis_history added (existing analyses backfilled)")
                current_version = 17
            except Exception as e:
                print(f"Migration v16 to v17 failed: {e}")

        # Migration from v17 to v18 — add sdp_records.source provenance column.
        # Additive/backward-compatible: existing rows get NULL source (unknown
        # provenance, exactly as before). New writes record which discovery source
        # (D-Bus / browse / xml / records, or a merged "a+b") produced the record.
        if current_version == 17:
            try:
                try:
                    conn.execute("ALTER TABLE sdp_records ADD COLUMN source TEXT")
                except Exception:
                    pass  # column may already exist on freshly-created v18 schema
                print("[+] Database schema v18: sdp_records.source provenance column")
                current_version = 18
            except Exception as e:
                print(f"Migration v17 to v18 failed: {e}")

        # Migration from v18 to v19 — multi-antenna provenance.
        # Additive: devices.seen_by (JSON list of hciN, union-merged on upsert),
        # devices.enumerated_by (last radio that GATT-enumerated), adv_reports.adapter
        # (collecting antenna; included in consecutive-identical dedup key).
        if current_version == 18:
            try:
                for stmt in (
                    "ALTER TABLE devices ADD COLUMN seen_by JSON",
                    "ALTER TABLE devices ADD COLUMN enumerated_by TEXT",
                    "ALTER TABLE adv_reports ADD COLUMN adapter TEXT",
                ):
                    try:
                        conn.execute(stmt)
                    except Exception:
                        pass  # column may already exist on freshly-created v19 schema
                print("[+] Database schema v19: devices.seen_by/enumerated_by, adv_reports.adapter")
                current_version = 19
            except Exception as e:
                print(f"Migration v18 to v19 failed: {e}")

        # Migration from v19 to v20 — last-successful GATT timestamp so survey
        # will not immediately re-enumerate a device the collectors keep seeing.
        if current_version == 19:
            try:
                try:
                    conn.execute(
                        "ALTER TABLE devices ADD COLUMN enumerated_at DATETIME"
                    )
                except Exception:
                    pass
                print("[+] Database schema v20: devices.enumerated_at")
                current_version = 20
            except Exception as e:
                print(f"Migration v19 to v20 failed: {e}")

        # Idempotent fixup: normalize devices.uuids JSON column to uppercase
        # (7B-5c) — safe to run on every init; only touches rows with lowercase
        try:
            conn.execute(
                "UPDATE devices SET uuids = UPPER(uuids) "
                "WHERE uuids IS NOT NULL AND uuids != UPPER(uuids)"
            )
        except Exception:
            pass

        # Persist schema version
        if not ver_row:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (_SCHEMA_VERSION,))
        elif stored_version != _SCHEMA_VERSION:
            conn.execute("UPDATE schema_version SET version = ?", (_SCHEMA_VERSION,))
    
    _DB_CONN = conn


@contextmanager
def _db_cursor():
    """Context manager yielding a DB cursor with automatic commit.

    Serialized by ``_DB_LOCK``: the observation DB uses a single shared
    ``sqlite3`` connection opened with ``check_same_thread=False``, which is not
    safe for concurrent use across threads.  Holding the lock for the whole
    cursor→commit window lets multiple collector threads (one per adapter, D2)
    persist sightings without interleaving cursors/commits on that connection.
    """
    with _DB_LOCK:
        try:
            if _DB_CONN is None:
                _init_db()
            cursor = _DB_CONN.cursor()  # type: ignore[union-attr]
            yield cursor
            _DB_CONN.commit()  # type: ignore[union-attr]
        except Exception as e:
            if _DB_CONN is not None:
                _DB_CONN.rollback()
            print_and_log(f"DB Error: {e}", LOG__DEBUG)
            raise


# ---------------------------------------------------------------------------
# Shared helper functions ---------------------------------------------------
# ---------------------------------------------------------------------------

_MAC_FMT_RE = re.compile(r'^[0-9A-Fa-f]{2}([:\-])[0-9A-Fa-f]{2}(?:\1[0-9A-Fa-f]{2}){4}$')
_DBUS_PATH_MAC_RE = re.compile(
    r'dev_([0-9A-Fa-f]{2}_[0-9A-Fa-f]{2}_[0-9A-Fa-f]{2}'
    r'_[0-9A-Fa-f]{2}_[0-9A-Fa-f]{2}_[0-9A-Fa-f]{2})$',
    re.IGNORECASE,
)


def _normalize_mac(mac: str) -> Optional[str]:
    """Normalize MAC address to uppercase colon-separated format.

    Returns ``None`` for empty, incomplete, or unparseable input.
    """
    if not mac or not isinstance(mac, str):
        return None
    mac = mac.strip()
    if not mac:
        return None
    if _MAC_FMT_RE.match(mac):
        return mac.replace('-', ':').upper()
    m = _DBUS_PATH_MAC_RE.search(mac)
    if m:
        return m.group(1).replace('_', ':').upper()
    return None


def _normalize_uuid(uuid_str: str) -> str:
    """Normalize a UUID string to uppercase for consistent DB storage."""
    return uuid_str.strip().upper() if uuid_str else uuid_str


def _ensure_device_exists(cur, mac: str) -> Optional[str]:
    """Defensively create a stub device row if none exists.

    Returns the normalized MAC, or ``None`` if the MAC is invalid.
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return None
    now = utc_now_iso()
    cur.execute(
        "INSERT OR IGNORE INTO devices(mac, first_seen, last_seen) VALUES (?, ?, ?)",
        (mac, now, now),
    )
    return mac


def _ensure_service_exists(cur, mac: str, service_uuid: str) -> Optional[int]:
    """Defensively create a stub service row if none exists.

    Returns the service_id, or ``None`` when the MAC is invalid.
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return None
    service_uuid = _normalize_uuid(service_uuid)
    now = utc_now_iso()
    cur.execute(
        "INSERT OR IGNORE INTO services(mac, uuid, first_seen, last_seen) VALUES (?, ?, ?, ?)",
        (mac, service_uuid, now, now),
    )
    row = cur.execute(
        "SELECT id FROM services WHERE mac=? AND uuid=?",
        (mac, service_uuid),
    ).fetchone()
    return row["id"]


def json_dumps(obj: Any) -> str:
    """Compact JSON serialization with fallback to empty object."""
    try:
        return _json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return "{}"
