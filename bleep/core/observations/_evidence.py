"""Device type classification evidence storage and retrieval."""
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


def store_device_type_evidence(
    mac: str,
    evidence_type: str,
    evidence_weight: str,
    source: str,
    value: Any = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Store device type classification evidence in the database for audit/debugging.
    
    **Note:** This function is for audit trail purposes only. Evidence stored here
    is NOT used for classification decisions - classification is stateless and based
    only on current device properties.
    
    Args:
        mac: Device MAC address
        evidence_type: Type of evidence (e.g., 'classic_device_class', 'le_addr_random')
        evidence_weight: Weight of evidence ('conclusive', 'strong', 'weak', 'inconclusive')
        source: Source of evidence (e.g., 'dbus_property', 'sdp_query', 'gatt_enumeration')
        value: Evidence value (will be converted to string/JSON)
        metadata: Optional metadata dictionary (will be stored as JSON)
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return
    now = utc_now_iso()
    
    # Convert value to string representation
    if value is not None:
        if isinstance(value, (dict, list)):
            value_str = json_dumps(value)
        else:
            value_str = str(value)
    else:
        value_str = None
    
    # Convert metadata to JSON string
    metadata_str = json_dumps(metadata) if metadata else None
    
    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        cur.execute("""
            INSERT OR REPLACE INTO device_type_evidence 
            (mac, evidence_type, evidence_weight, source, value, metadata, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (mac, evidence_type, evidence_weight, source, value_str, metadata_str, now))


def get_device_type_evidence(mac: str) -> List[Dict[str, Any]]:
    """
    Retrieve all device type classification evidence for a device.
    
    **Note:** This is for audit/debugging purposes only. Evidence retrieved here
    is NOT used for classification decisions.
    
    Args:
        mac: Device MAC address
        
    Returns:
        List of evidence dictionaries, ordered by timestamp (newest first)
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return []
    
    try:
        with _DB_LOCK, _db_cursor() as cur:
            cur.execute("""
                SELECT * FROM device_type_evidence
                WHERE mac = ?
                ORDER BY ts DESC
            """, (mac,))
            
            rows = cur.fetchall()
            evidence_list = []
            for row in rows:
                evidence = dict(row)
                # Parse JSON metadata if present
                if evidence.get('metadata'):
                    try:
                        evidence['metadata'] = json.loads(evidence['metadata'])
                    except (json.JSONDecodeError, TypeError):
                        pass
                evidence_list.append(evidence)
            
            return evidence_list
    except Exception as e:
        print_and_log(
            f"Error retrieving device type evidence for {mac}: {e}",
            LOG__DEBUG
        )
        return []


def store_security_maps(
    mac: str,
    landmine_map: Optional[Dict[str, Any]] = None,
    permission_map: Optional[Dict[str, Any]] = None,
    enumeration_annotations: Optional[List[Dict[str, Any]]] = None,
    source: Optional[str] = None,
) -> None:
    """Store per-enumeration security analysis maps for a device.

    Args:
        mac: Device MAC address
        landmine_map: Map of characteristics flagged as dangerous/risky
        permission_map: Map of characteristic permissions (read/write/notify outcomes)
        enumeration_annotations: Typed error/annotation records from enumeration
        source: Origin of the security map (e.g., 'exploration', 'aoi', 'gatt-enum')
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return
    now = utc_now_iso()

    with _DB_LOCK, _db_cursor() as cur:
        _ensure_device_exists(cur, mac)
        cur.execute("""
            INSERT INTO security_maps
            (mac, ts, landmine_map, permission_map, enumeration_annotations, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            mac, now,
            json_dumps(landmine_map) if landmine_map else None,
            json_dumps(permission_map) if permission_map else None,
            json_dumps(enumeration_annotations) if enumeration_annotations else None,
            source,
        ))


def get_security_maps(mac: str) -> List[Dict[str, Any]]:
    """Retrieve all security maps for a device, newest first.

    Args:
        mac: Device MAC address

    Returns:
        List of security map dictionaries with parsed JSON fields
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return []

    try:
        with _DB_LOCK, _db_cursor() as cur:
            cur.execute(
                "SELECT * FROM security_maps WHERE mac=? ORDER BY ts DESC",
                (mac,),
            )
            results = []
            for row in cur.fetchall():
                rec = dict(row)
                for field in ("landmine_map", "permission_map", "enumeration_annotations"):
                    if rec.get(field):
                        try:
                            rec[field] = json.loads(rec[field])
                        except (json.JSONDecodeError, TypeError):
                            pass
                results.append(rec)
            return results
    except Exception as e:
        print_and_log(f"Error retrieving security maps for {mac}: {e}", LOG__DEBUG)
        return []


def get_device_evidence_signature(mac: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the most recent evidence signature for a device.
    
    This is used for database-first caching in the classifier. The signature
    represents a snapshot of device properties at classification time.
    
    **Note:** This signature is used for performance optimization (caching) only.
    Classification decisions are still stateless and based on current device state.
    
    Args:
        mac: Device MAC address
        
    Returns:
        Dictionary with signature data (device_class, address_type, uuid_hash, etc.)
        or None if no signature exists
    """
    mac = _normalize_mac(mac)
    if mac is None:
        return None
    
    try:
        evidence_list = get_device_type_evidence(mac)
        if not evidence_list:
            return None
        
        # Build signature from evidence
        signature = {
            'device_class': None,
            'address_type': None,
            'has_classic_uuids': False,
            'has_le_uuids': False,
            'uuid_hash': None,
        }
        
        # Extract signature components from evidence
        for evidence in evidence_list:
            ev_type = evidence.get('evidence_type', '')
            ev_value = evidence.get('value', '')
            ev_metadata = evidence.get('metadata', {})
            
            if ev_type == 'classic_device_class' and ev_value:
                try:
                    signature['device_class'] = int(ev_value)
                except (ValueError, TypeError):
                    pass
            
            if ev_type in ['le_address_type_random', 'le_address_type_public']:
                signature['address_type'] = 'random' if 'random' in ev_type else 'public'
            
            if ev_type == 'classic_service_uuids' and ev_metadata:
                signature['has_classic_uuids'] = ev_metadata.get('uuid_count', 0) > 0
            
            if ev_type == 'le_service_uuids' and ev_metadata:
                signature['has_le_uuids'] = ev_metadata.get('uuid_count', 0) > 0
        
        # Check if signature has meaningful data
        if any(v is not None and v is not False for v in signature.values()):
            return signature
        
        return None
        
    except Exception as e:
        print_and_log(
            f"Error retrieving evidence signature for {mac}: {e}",
            LOG__DEBUG
        )
        return None
