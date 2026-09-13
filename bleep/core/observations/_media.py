"""Media player, transport, enumeration, and audio recon persistence."""
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


def snapshot_media_player(player):  # type: ignore[valid-type]
    try:
        props = player.get_properties()
        raw_mac = props.get("Device") or player.get_device() or "UNKNOWN"
        norm_mac = _normalize_mac(raw_mac)
        if norm_mac is None:
            return
        row = {
            "path": player.player_path,
            "mac": norm_mac,
            "name": props.get("Name"),
            "subtype": props.get("Subtype"),
            "status": props.get("Status"),
            "position": props.get("Position"),
            "metadata": json_dumps(props.get("Track", {})),
            "ts": utc_now_iso(),
        }
    except Exception:
        return
    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, row["mac"])
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
        raw_mac = transport.get_device() or "UNKNOWN"
        norm_mac = _normalize_mac(raw_mac)
        if norm_mac is None:
            return
        row = {
            "path": transport.transport_path,
            "mac": norm_mac,
            "transport_state": transport.get_state(),
            "volume": transport.get_volume(),
            "codec": transport.get_codec(),
            "ts": utc_now_iso(),
        }
    except Exception:
        return

    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, row["mac"])
        cols = ",".join(row.keys())
        ph = ",".join("?" for _ in row)
        updates = ",".join(f"{k}=excluded.{k}" for k in row.keys())
        cur.execute(
            f"INSERT INTO media_transports({cols}) VALUES ({ph}) ON CONFLICT(path) DO UPDATE SET {updates}",
            tuple(row.values()),
        )


def store_media_enumeration(
    mac: str,
    players: Optional[List[Dict[str, Any]]] = None,
    transports: Optional[List[Dict[str, Any]]] = None,
    endpoints: Optional[List[Dict[str, Any]]] = None,
    browse_tree: Optional[Dict[str, Any]] = None,
    capabilities: Optional[Dict[str, Any]] = None,
) -> None:
    """Store a full media enumeration snapshot for a device.

    Args:
        mac: Device MAC address
        players: List of media player info dicts
        transports: List of transport state dicts
        endpoints: List of endpoint info dicts
        browse_tree: Media browsing tree structure
        capabilities: Device media capabilities
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return
    now = utc_now_iso()

    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        cur.execute("""
            INSERT INTO media_enumerations
            (mac, ts, players, transports, endpoints, browse_tree, capabilities)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            mac, now,
            json_dumps(players) if players else None,
            json_dumps(transports) if transports else None,
            json_dumps(endpoints) if endpoints else None,
            json_dumps(browse_tree) if browse_tree else None,
            json_dumps(capabilities) if capabilities else None,
        ))


def get_media_enumerations(mac: str) -> List[Dict[str, Any]]:
    """Retrieve all media enumeration snapshots for a device, newest first.

    Args:
        mac: Device MAC address

    Returns:
        List of media enumeration dictionaries with parsed JSON fields
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return []

    try:
        import json
        with _DB_LOCK, _db_cursor() as cur:
            cur.execute(
                "SELECT * FROM media_enumerations WHERE mac=? ORDER BY ts DESC",
                (mac,),
            )
            results = []
            for row in cur.fetchall():
                rec = dict(row)
                for field in ("players", "transports", "endpoints", "browse_tree", "capabilities"):
                    if rec.get(field):
                        try:
                            rec[field] = json.loads(rec[field])
                        except (json.JSONDecodeError, TypeError):
                            pass
                results.append(rec)
            return results
    except Exception as e:
        print_and_log(f"Error retrieving media enumerations for {mac}: {e}", LOG__DEBUG)
        return []


def store_audio_recon(
    backend: Optional[str] = None,
    cards: Optional[List[Dict[str, Any]]] = None,
    pcms: Optional[List[Dict[str, Any]]] = None,
    recordings: Optional[List[Dict[str, Any]]] = None,
    sox_analysis: Optional[Dict[str, Any]] = None,
    contention: Optional[Dict[str, Any]] = None,
) -> None:
    """Store a host-level audio recon snapshot.

    Audio recon is host-level (not per-device), so mac is not required.

    Args:
        backend: Active audio backend name (e.g., 'pipewire', 'pulseaudio', 'bluealsa')
        cards: List of audio card info dicts
        pcms: List of PCM device info dicts
        recordings: List of recording session info dicts
        sox_analysis: Sox audio analysis results
        contention: Endpoint contention report
    """
    now = utc_now_iso()

    with _DB_LOCK, _db_cursor() as cur:
        cur.execute("""
            INSERT INTO audio_recon
            (ts, backend, cards, pcms, recordings, sox_analysis, contention)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            now, backend,
            json_dumps(cards) if cards else None,
            json_dumps(pcms) if pcms else None,
            json_dumps(recordings) if recordings else None,
            json_dumps(sox_analysis) if sox_analysis else None,
            json_dumps(contention) if contention else None,
        ))


def get_audio_recon(limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve recent audio recon snapshots, newest first.

    Args:
        limit: Maximum number of records to return

    Returns:
        List of audio recon dictionaries with parsed JSON fields
    """
    try:
        import json
        with _DB_LOCK, _db_cursor() as cur:
            cur.execute(
                "SELECT * FROM audio_recon ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
            results = []
            for row in cur.fetchall():
                rec = dict(row)
                for field in ("cards", "pcms", "recordings", "sox_analysis", "contention"):
                    if rec.get(field):
                        try:
                            rec[field] = json.loads(rec[field])
                        except (json.JSONDecodeError, TypeError):
                            pass
                results.append(rec)
            return results
    except Exception as e:
        print_and_log(f"Error retrieving audio recon records: {e}", LOG__DEBUG)
        return []
