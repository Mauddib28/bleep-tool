"""Pairing event persistence for the BLEEP observation database."""
from __future__ import annotations

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


def store_pairing_event(
    mac: str,
    method: Optional[str] = None,
    pin: Optional[str] = None,
    result: Optional[str] = None,
    capabilities: Optional[str] = None,
    auth_matrix: Optional[Dict[str, Any]] = None,
    brute_attempts: Optional[int] = None,
    brute_duration: Optional[float] = None,
    pre_pair_state: Optional[Dict[str, Any]] = None,
    post_pair_state: Optional[Dict[str, Any]] = None,
) -> None:
    """Store a pairing workflow event in the database.

    Captures the full pairing attempt including method, PIN/passkey,
    result, IO capabilities, auth probe matrix, and brute-force stats.

    Args:
        mac: Device MAC address
        method: Pairing method (e.g., 'just_works', 'passkey', 'pin_code', 'oob')
        pin: PIN or passkey used (if any)
        result: Outcome (e.g., 'success', 'failed', 'rejected', 'timeout')
        capabilities: IO capabilities string (e.g., 'DisplayYesNo')
        auth_matrix: Authentication probe matrix dict
        brute_attempts: Number of brute-force attempts (if applicable)
        brute_duration: Duration of brute-force phase in seconds
        pre_pair_state: Device state snapshot before pairing
        post_pair_state: Device state snapshot after pairing
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return
    now = utc_now_iso()

    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        cur.execute("""
            INSERT INTO pairing_events
            (mac, ts, method, pin, result, capabilities,
             auth_matrix, brute_attempts, brute_duration,
             pre_pair_state, post_pair_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mac, now, method, pin, result, capabilities,
            json_dumps(auth_matrix) if auth_matrix else None,
            brute_attempts, brute_duration,
            json_dumps(pre_pair_state) if pre_pair_state else None,
            json_dumps(post_pair_state) if post_pair_state else None,
        ))


def get_pairing_events(mac: str) -> List[Dict[str, Any]]:
    """Retrieve all pairing events for a device, newest first.

    Args:
        mac: Device MAC address

    Returns:
        List of pairing event dictionaries
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return []

    try:
        with _DB_LOCK, _db_cursor() as cur:
            cur.execute(
                "SELECT * FROM pairing_events WHERE mac=? ORDER BY ts DESC",
                (mac,),
            )
            import json
            results = []
            for row in cur.fetchall():
                rec = dict(row)
                for field in ("auth_matrix", "pre_pair_state", "post_pair_state"):
                    if rec.get(field):
                        try:
                            rec[field] = json.loads(rec[field])
                        except (json.JSONDecodeError, TypeError):
                            pass
                results.append(rec)
            return results
    except Exception as e:
        print_and_log(f"Error retrieving pairing events for {mac}: {e}", LOG__DEBUG)
        return []
