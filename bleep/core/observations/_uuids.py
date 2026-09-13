"""Observed-UUID catalogue aggregation (todo Item D, "Seen in the Wild").

Aggregates every UUID *actually observed* on scanned/enumerated devices across
the LE service tables and the Classic SDP tables into a single catalogue::

    {uuid: {"uuid", "names", "count", "sources", "first_seen", "last_seen",
            "sample_macs"}}

This is a provenance-preserving, *observed* tier — deliberately separate from the
authoritative SIG/custom tables in :mod:`bleep.bt_ref`. It never overwrites or
pollutes those sources; it only answers "have we seen this UUID before, and under
what name(s)?" so an operator can recognise a vendor/proprietary UUID that the
SIG registry does not know about.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._connection import _db_cursor

# BT SIG base UUID suffix used to expand 16/32-bit UUIDs to canonical 128-bit.
_BT_BASE_SUFFIX = "-0000-1000-8000-00805F9B34FB"


def _canonical_uuid(u: Optional[str]) -> Optional[str]:
    """Canonicalise any UUID form to the full dashed 128-bit representation.

    The DB stores UUIDs however the caller supplied them (short ``0X180A``, bare
    ``180A``, or full dashed), so short and long forms of the *same* logical UUID
    would otherwise split into separate catalogue entries and defeat cross-form
    lookups. Non-SIG / unrecognised inputs fall back to the uppercased original.
    """
    if not u:
        return None
    nodash = u.strip().upper().replace("0X", "").replace("-", "")
    if len(nodash) == 4:            # 16-bit SIG UUID
        return f"0000{nodash}{_BT_BASE_SUFFIX}"
    if len(nodash) == 8:            # 32-bit SIG UUID
        return f"{nodash}{_BT_BASE_SUFFIX}"
    if len(nodash) == 32:           # 128-bit (dashed or not)
        return f"{nodash[0:8]}-{nodash[8:12]}-{nodash[12:16]}-{nodash[16:20]}-{nodash[20:32]}"
    return u.strip().upper()

# One row per (uuid, name, mac, ts, origin) observation, unioned across every
# table that records a UUID. LE characteristics/descriptors carry no service
# name, so their name column is NULL (they still contribute count + provenance).
_CATALOGUE_UNION_SQL = """
SELECT uuid, name, mac, last_seen AS ts, 'le_service' AS origin
    FROM services WHERE uuid IS NOT NULL
UNION ALL
SELECT uuid, name, mac, ts, 'classic_service' AS origin
    FROM classic_services WHERE uuid IS NOT NULL
UNION ALL
SELECT uuid, name, mac, ts, 'sdp' AS origin
    FROM sdp_records WHERE uuid IS NOT NULL
UNION ALL
SELECT c.uuid, NULL AS name, s.mac, c.last_read AS ts, 'le_char' AS origin
    FROM characteristics c JOIN services s ON c.service_id = s.id
    WHERE c.uuid IS NOT NULL
UNION ALL
SELECT d.uuid, NULL AS name, s.mac, d.last_read AS ts, 'le_desc' AS origin
    FROM descriptors d
    JOIN characteristics c ON d.characteristic_id = c.id
    JOIN services s ON c.service_id = s.id
    WHERE d.uuid IS NOT NULL
"""

_MAX_SAMPLE_MACS = 5


def get_observed_uuid_catalogue(
    limit: Optional[int] = None,
    uuid: Optional[str] = None,
    max_sample_macs: int = _MAX_SAMPLE_MACS,
    include_seed: bool = False,
) -> List[Dict[str, Any]]:
    """Return the observed-UUID catalogue, most-observed first.

    Parameters
    ----------
    limit : int, optional
        Cap the number of catalogue entries returned (after count-desc sort).
    uuid : str, optional
        Restrict the catalogue to a single (normalised) UUID.
    max_sample_macs : int
        Maximum distinct device MACs to retain per UUID as evidence samples.
    include_seed : bool
        If True, union the curated non-SIG seed (:mod:`bleep.bt_ref.observed_seed`)
        into the catalogue, tagged ``source="curated_seed"``. Seed-only entries
        (never actually observed) carry ``count == 0``. Default False so the
        observed-only view is unchanged.
    """
    want = _canonical_uuid(uuid) if uuid else None
    agg: Dict[str, Dict[str, Any]] = {}
    with _db_cursor() as cur:
        try:
            rows = cur.execute(_CATALOGUE_UNION_SQL).fetchall()
        except Exception:  # noqa: BLE001 - missing tables on very old DBs
            return []
        for row in rows:
            u = _canonical_uuid(row["uuid"]) if row["uuid"] else None
            if not u or (want is not None and u != want):
                continue
            entry = agg.get(u)
            if entry is None:
                entry = {
                    "uuid": u,
                    "names": set(),
                    "count": 0,
                    "sources": set(),
                    "first_seen": None,
                    "last_seen": None,
                    "_macs": [],
                }
                agg[u] = entry
            entry["count"] += 1
            entry["sources"].add(row["origin"])
            name = row["name"]
            if name:
                entry["names"].add(name)
            ts = row["ts"]
            if ts:
                if entry["first_seen"] is None or ts < entry["first_seen"]:
                    entry["first_seen"] = ts
                if entry["last_seen"] is None or ts > entry["last_seen"]:
                    entry["last_seen"] = ts
            mac = row["mac"]
            if mac and mac not in entry["_macs"] and len(entry["_macs"]) < max_sample_macs:
                entry["_macs"].append(mac)

    if include_seed:
        # Curated non-SIG seed: merge names + provenance into observed entries,
        # or add count-0 reference entries for UUIDs never actually seen. Kept a
        # distinct tier ("curated_seed") so it never masquerades as a measurement.
        from bleep.bt_ref.observed_seed import OBSERVED_UUID_SEED

        for seed_uuid, meta in OBSERVED_UUID_SEED.items():
            u = _canonical_uuid(seed_uuid)
            if not u or (want is not None and u != want):
                continue
            entry = agg.get(u)
            if entry is None:
                entry = {
                    "uuid": u,
                    "names": set(),
                    "count": 0,
                    "sources": set(),
                    "first_seen": None,
                    "last_seen": None,
                    "_macs": [],
                }
                agg[u] = entry
            entry["sources"].add("curated_seed")
            for name in (meta.get("names") or []):
                entry["names"].add(name)

    catalogue: List[Dict[str, Any]] = []
    for entry in agg.values():
        catalogue.append({
            "uuid": entry["uuid"],
            "names": sorted(entry["names"]),
            "count": entry["count"],
            "sources": sorted(entry["sources"]),
            "first_seen": entry["first_seen"],
            "last_seen": entry["last_seen"],
            "sample_macs": entry["_macs"],
        })
    catalogue.sort(key=lambda e: (-e["count"], e["uuid"]))
    if limit is not None:
        catalogue = catalogue[:limit]
    return catalogue


# Which catalogue origins count as a *measured* observation of each kind. LE
# service/characteristic/descriptor rows are LE-measured; Classic service and SDP
# rows are Classic-measured. (Advertised-only UUIDs are not in these tables.)
_LE_MEASURED_TABLES = (("services", True), ("characteristics", False), ("descriptors", False))
_CLASSIC_MEASURED_TABLES = (("classic_services", True), ("sdp_records", True))


def get_observed_uuid_evidence(uuid: str) -> Dict[str, Any]:
    """Report which *kinds* of table a UUID was measured in, plus any names.

    Returns ``{"le_measured": bool, "classic_measured": bool, "le_names": [...],
    "classic_names": [...]}``. Used by the device-type classifier's opt-in
    observed-promotion path so an advertised UUID that was *measured* as an LE
    GATT service elsewhere can count as LE evidence (and Classic likewise). LE
    characteristic/descriptor tables carry no name column, so they contribute to
    ``le_measured`` without adding names.
    """
    want = _canonical_uuid(uuid) if uuid else None
    result: Dict[str, Any] = {
        "le_measured": False,
        "classic_measured": False,
        "le_names": [],
        "classic_names": [],
    }
    if not want:
        return result
    le_names: set = set()
    classic_names: set = set()
    with _db_cursor() as cur:
        def _scan(table: str, has_name: bool):
            cols = "uuid, name" if has_name else "uuid"
            try:
                rows = cur.execute(
                    f"SELECT DISTINCT {cols} FROM {table} WHERE uuid IS NOT NULL"
                ).fetchall()
            except Exception:  # noqa: BLE001 - tolerate missing tables
                return False, set()
            hit = False
            names: set = set()
            for row in rows:
                if _canonical_uuid(row["uuid"]) != want:
                    continue
                hit = True
                if has_name and row["name"]:
                    names.add(row["name"])
            return hit, names

        for table, has_name in _LE_MEASURED_TABLES:
            hit, names = _scan(table, has_name)
            result["le_measured"] = result["le_measured"] or hit
            le_names |= names
        for table, has_name in _CLASSIC_MEASURED_TABLES:
            hit, names = _scan(table, has_name)
            result["classic_measured"] = result["classic_measured"] or hit
            classic_names |= names
    result["le_names"] = sorted(le_names)
    result["classic_names"] = sorted(classic_names)
    return result


def get_observed_uuid_names(uuid: str) -> List[str]:
    """Return the distinct names a UUID has been *observed* under (may be empty).

    Lightweight helper for the resolver's optional observed tier — only queries
    the name-bearing tables (LE services, Classic services, SDP records).
    """
    want = _canonical_uuid(uuid) if uuid else None
    if not want:
        return []
    names: set = set()
    with _db_cursor() as cur:
        for table in ("services", "classic_services", "sdp_records"):
            try:
                # Canonicalise stored UUIDs in Python so short/long forms of the
                # same logical UUID all match, regardless of how they were stored.
                for row in cur.execute(
                    f"SELECT DISTINCT uuid, name FROM {table} "
                    f"WHERE uuid IS NOT NULL AND name IS NOT NULL"
                ).fetchall():
                    if _canonical_uuid(row["uuid"]) == want and row["name"]:
                        names.add(row["name"])
            except Exception:  # noqa: BLE001 - tolerate missing tables
                continue
    return sorted(names)
