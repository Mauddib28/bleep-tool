"""BLEEP observation database helper (SQLite).

The module is imported lazily from scan/enum paths; any failure to create or
open the DB is swallowed – BLEEP must *never* crash because persistence is
unavailable on the host system.

This package was refactored from a single ``observations.py`` module into
submodules for maintainability.  All public symbols are re-exported here
so that existing imports (``from bleep.core.observations import ...`` and
``from bleep.core import observations``) continue to work unchanged.
"""
from __future__ import annotations

# Re-export connection internals used by test fixtures
from . import _connection
from ._connection import (
    _DB_LOCK,
    _DB_PATH,
    _init_db,
    _SCHEMA_VERSION,
    _SCHEMA_SQL,
    _db_cursor,
    _normalize_mac,
    _normalize_uuid,
    _ensure_device_exists,
    _ensure_service_exists,
    json_dumps,
)

# On (re-)import, reset connection so _init_db() picks up new BLEEP_DB_PATH.
# This matches the original single-file behavior where `_DB_CONN = None` ran on reload.
_connection._DB_CONN = None


def __getattr__(name: str):
    """Proxy mutable connection state reads to _connection module."""
    if name == "_DB_CONN":
        return _connection._DB_CONN
    if name == "_DB_PATH":
        return _connection._DB_PATH
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Re-export device functions
from ._devices import (
    upsert_device,
    get_devices,
    get_device_detail,
    get_enumeration_stamp,
    export_device_data,
    get_sdp_inventory,
    get_characteristic_values,
)

# Re-export service/characteristic functions
from ._services import (
    upsert_services,
    upsert_characteristics,
    get_characteristic_id,
    upsert_descriptors,
    upsert_classic_services,
    upsert_sdp_record,
    get_sdp_timeline,
    upsert_pan_access,
    upsert_pbap_metadata,
)

# Re-export observed-UUID catalogue functions
from ._uuids import (
    get_observed_uuid_catalogue,
    get_observed_uuid_evidence,
    get_observed_uuid_names,
)

# Re-export history/advertisement functions
from ._history import (
    insert_adv,
    insert_char_history,
    get_characteristic_timeline,
)

# Re-export media functions
from ._media import (
    snapshot_media_player,
    snapshot_media_transport,
    store_media_enumeration,
    get_media_enumerations,
    store_audio_recon,
    get_audio_recon,
)

# Re-export AoI functions
from ._aoi import (
    store_aoi_analysis,
    get_aoi_analysis,
    get_aoi_analysis_history,
    has_aoi_analysis,
    get_aoi_analyzed_devices,
)

# Re-export signal capture
from ._signals import store_signal_capture

# Re-export device type evidence and security map functions
from ._evidence import (
    store_device_type_evidence,
    get_device_type_evidence,
    get_device_evidence_signature,
    store_security_maps,
    get_security_maps,
)

# Re-export pairing event functions
from ._pairing import (
    store_pairing_event,
    get_pairing_events,
)

# Re-export maintenance functions
from ._maintenance import (
    maintain_database,
    explain_query,
)

__all__ = [
    "upsert_device",
    "insert_adv",
    "upsert_services",
    "upsert_characteristics",
    "get_characteristic_id",
    "upsert_descriptors",
    "upsert_classic_services",
    "upsert_sdp_record",
    "get_sdp_timeline",
    "upsert_pan_access",
    "upsert_pbap_metadata",
    "insert_char_history",
    "snapshot_media_player",
    "snapshot_media_transport",
    "get_devices",
    "get_device_detail",
    "get_enumeration_stamp",
    "get_characteristic_timeline",
    "export_device_data",
    "get_sdp_inventory",
    "get_characteristic_values",
    "store_signal_capture",
    # AoI Database Integration
    "store_aoi_analysis",
    "get_aoi_analysis",
    "get_aoi_analysis_history",
    "has_aoi_analysis",
    "get_aoi_analyzed_devices",
    # Device Type Classification Evidence
    "store_device_type_evidence",
    "get_device_type_evidence",
    "get_device_evidence_signature",
    # Security Maps (Phase 2)
    "store_security_maps",
    "get_security_maps",
    # Pairing Events (Phase 2)
    "store_pairing_event",
    "get_pairing_events",
    # Media Enumeration (Phase 2)
    "store_media_enumeration",
    "get_media_enumerations",
    # Audio Recon (Phase 2)
    "store_audio_recon",
    "get_audio_recon",
    # Observed-UUID catalogue ("Seen in the Wild")
    "get_observed_uuid_catalogue",
    "get_observed_uuid_evidence",
    "get_observed_uuid_names",
    # Database Maintenance and Performance
    "maintain_database",
    "explain_query",
]
