"""AoI (Asset of Interest) analysis storage and retrieval."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core.time_utils import utc_now_iso

from ._connection import (
    _DB_LOCK,
    _db_cursor,
    _normalize_mac,
    _ensure_device_exists,
    json_dumps,
)


def store_aoi_analysis(mac: str, analysis: Dict[str, Any]) -> None:
    """
    Store AoI analysis results in the database (schema v11).
    
    Handles both ``analysis["summary"]`` sub-keys **and** top-level v11
    fields (``pairing_profile``, ``sdp_summary``, ``post_pair_delta``).
    
    Args:
        mac: Device MAC address
        analysis: Analysis dictionary from AOIAnalyser
    """
    mac = _normalize_mac(mac)
    if mac is None:
        print_and_log(f"store_aoi_analysis: rejected invalid MAC", LOG__DEBUG)
        return
    
    summary = analysis.get("summary", {})
    security_concerns = summary.get("security_concerns", [])
    unusual_characteristics = summary.get("unusual_characteristics", [])
    notable_services = summary.get("notable_services", [])
    recommendations = summary.get("recommendations", [])
    
    pairing_profile = analysis.get("pairing_profile")
    sdp_summary = analysis.get("sdp_summary")
    post_pair_delta = analysis.get("post_pair_delta")
    details = analysis.get("details")

    # Column values shared by the latest-row upsert and the history insert so the
    # two rows carry an identical timestamp/payload for a single store.
    values = (
        mac,
        utc_now_iso(),
        json_dumps(security_concerns),
        json_dumps(unusual_characteristics),
        json_dumps(notable_services),
        json_dumps(recommendations),
        json_dumps(pairing_profile) if pairing_profile else None,
        json_dumps(sdp_summary) if sdp_summary else None,
        json_dumps(post_pair_delta) if post_pair_delta else None,
        json_dumps(details) if details else None,
    )

    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        # Latest-only row (unchanged semantics: get_aoi_analysis returns this).
        cur.execute(
            """
            INSERT INTO aoi_analysis(mac, analysis_timestamp, security_concerns,
                                   unusual_characteristics, notable_services,
                                   recommendations, pairing_profile,
                                   sdp_summary, post_pair_delta, analysis_details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                analysis_timestamp=excluded.analysis_timestamp,
                security_concerns=excluded.security_concerns,
                unusual_characteristics=excluded.unusual_characteristics,
                notable_services=excluded.notable_services,
                recommendations=excluded.recommendations,
                pairing_profile=excluded.pairing_profile,
                sdp_summary=excluded.sdp_summary,
                post_pair_delta=excluded.post_pair_delta,
                analysis_details=excluded.analysis_details
            """,
            values,
        )
        # Append-only history row (schema v17) — one per store, for tracking
        # changes across re-scans (see get_aoi_analysis_history).
        cur.execute(
            """
            INSERT INTO aoi_analysis_history(mac, analysis_timestamp, security_concerns,
                                   unusual_characteristics, notable_services,
                                   recommendations, pairing_profile,
                                   sdp_summary, post_pair_delta, analysis_details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )

def _row_to_analysis(row) -> Dict[str, Any]:
    """Parse an ``aoi_analysis`` / ``aoi_analysis_history`` row into an analysis dict.

    Shared by :func:`get_aoi_analysis` (latest) and
    :func:`get_aoi_analysis_history` so both return an identical shape.
    """
    security_concerns = json.loads(row["security_concerns"]) if row["security_concerns"] else []
    unusual_characteristics = json.loads(row["unusual_characteristics"]) if row["unusual_characteristics"] else []
    notable_services = json.loads(row["notable_services"]) if row["notable_services"] else []
    recommendations = json.loads(row["recommendations"]) if row["recommendations"] else []

    result: Dict[str, Any] = {
        "timestamp": row["analysis_timestamp"],
        "summary": {
            "security_concerns": security_concerns,
            "unusual_characteristics": unusual_characteristics,
            "notable_services": notable_services,
            "recommendations": recommendations,
        },
    }
    for extra_col in ("pairing_profile", "sdp_summary", "post_pair_delta", "analysis_details"):
        raw = row[extra_col] if extra_col in row.keys() else None
        if raw:
            parsed = json.loads(raw)
            if extra_col == "analysis_details":
                result["details"] = parsed
            else:
                result[extra_col] = parsed
    return result


def get_aoi_analysis(mac: str) -> Optional[Dict[str, Any]]:
    """
    Get the latest AoI analysis results from the database.
    
    Args:
        mac: Device MAC address
        
    Returns:
        Analysis dictionary or None if not found
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return None
    
    try:
        with _db_cursor() as cur:
            row = cur.execute(
                "SELECT * FROM aoi_analysis WHERE mac = ?",
                (mac,)
            ).fetchone()
            
            if not row:
                return None
            return _row_to_analysis(row)
    except Exception as e:
        print_and_log(f"Error retrieving AoI analysis: {e}", LOG__DEBUG)
        return None


def get_aoi_analysis_history(mac: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get the full AoI analysis history for a device, newest first (schema v17).

    Each store of an analysis appends a timestamped row to ``aoi_analysis_history``
    (while ``aoi_analysis`` keeps only the latest). This returns every recorded
    analysis so re-scans can be compared over time.

    Args:
        mac: Device MAC address
        limit: Optional maximum number of (most-recent) entries to return

    Returns:
        List of analysis dictionaries (same shape as :func:`get_aoi_analysis`),
        ordered newest-first. Empty list if none / invalid MAC.
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return []

    try:
        with _db_cursor() as cur:
            query = "SELECT * FROM aoi_analysis_history WHERE mac = ? ORDER BY id DESC"
            params: tuple = (mac,)
            if limit is not None:
                query += " LIMIT ?"
                params = (mac, int(limit))
            rows = cur.execute(query, params).fetchall()
            return [_row_to_analysis(row) for row in rows]
    except Exception as e:
        print_and_log(f"Error retrieving AoI analysis history: {e}", LOG__DEBUG)
        return []

def has_aoi_analysis(mac: str) -> bool:
    """
    Check if a device has AoI analysis in the database.
    
    Args:
        mac: Device MAC address
        
    Returns:
        True if analysis exists, False otherwise
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return False
    
    with _db_cursor() as cur:
        row = cur.execute(
            "SELECT 1 FROM aoi_analysis WHERE mac = ?",
            (mac,)
        ).fetchone()
        
        return row is not None

def get_aoi_analyzed_devices() -> List[Dict[str, Any]]:
    """
    Get list of devices that have AoI analysis in the database.
    
    Returns:
        List of device dictionaries
    """
    try:
        with _db_cursor() as cur:
            rows = cur.execute("""
                SELECT d.*, a.analysis_timestamp
                FROM devices d
                JOIN aoi_analysis a ON d.mac = a.mac
                ORDER BY a.analysis_timestamp DESC
            """).fetchall()
            
            return [dict(row) for row in rows]
    except Exception as e:
        print_and_log(f"Error retrieving AoI analyzed devices: {e}", LOG__DEBUG)
        return []
