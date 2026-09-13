"""Heuristic device-identity collapse for RPA-rotating BLE devices (DB-4).

Bluetooth LE privacy uses Resolvable Private Addresses (RPAs) that rotate on a
timer, so a single physical device is recorded in the observation DB as many
distinct ``devices`` rows (one per address it advertised).  *True* RPA
resolution requires the device's Identity Resolving Key (IRK), which is only
available after bonding and is **not stored** by BLEEP — so this module offers
only *heuristic* grouping by stable advertisement attributes.

Design constraints (see ``docs/todo_tracker.md`` DB-4):

* **Non-destructive / read-only.** Nothing here touches the database or mutates
  the input rows; it returns a grouped *view* the caller may render.
* **Opt-in.** Callers default to the raw, non-collapsed view.  Collapse exists
  to *contrast* with the raw counts, never to replace them — the delta between
  ``raw_count`` and ``collapsed_count`` is itself the analytical signal (a small
  delta means address rotation co-occurs with payload/name rotation and defeats
  fingerprinting).
* **Honest provenance.** The result carries ``method="heuristic"`` and
  ``irk_resolved=False`` so a grouped identity is never mistaken for a
  cryptographically resolved one.

Reuse: the ``payload`` strategy derives its protocol signature from
``bleep.analysis.adv_dissect.dissect_advertisement`` — the same primitive
``bleep.modes.survey``'s ``_round_signature`` uses — rather than duplicating any
advertisement-parsing logic.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

__all__ = [
    "STRATEGIES",
    "collapse_identities",
    "NAME_CLASSES",
    "is_mac_shaped",
    "normalize_mac",
    "classify_name",
]

STRATEGIES = ("name", "name_mfr", "payload")

_PLACEHOLDER_NAMES = frozenset({"", "unknown", "unknown device"})

# A device *name* that is itself a MAC address (BlueZ's default alias). Six hex
# octets separated by ``:``, ``-`` or ``_`` — anchored so only whole-string MACs
# match (an embedded MAC substring such as ``"Cam-AA-BB-..."`` is a real name).
NAME_CLASSES = ("placeholder", "real", "empty", "foreign_mac")

_MAC_SHAPED_RE = re.compile(r"^[0-9A-Fa-f]{2}(?:[:\-_][0-9A-Fa-f]{2}){5}$")


def normalize_mac(value: Any) -> str:
    """Return *value* with ``:``/``-``/``_`` separators stripped, upper-cased.

    Placeholder names use ``-`` separators while the stored ``mac`` column uses
    ``:`` — normalising both is required before comparing a MAC-shaped name to a
    device's own address.
    """
    if not isinstance(value, str):
        return ""
    return re.sub(r"[:\-_]", "", value).upper()


def is_mac_shaped(name: Any) -> bool:
    """True when *name* is a whole-string MAC address (any separator)."""
    return bool(isinstance(name, str) and _MAC_SHAPED_RE.match(name.strip()))


def classify_name(name: Any, mac: Any) -> str:
    """Classify a device *name* relative to the device's own *mac*.

    Returns one of :data:`NAME_CLASSES`:

    * ``"empty"`` — ``None`` / blank.
    * ``"placeholder"`` — a MAC-shaped name that normalises to the device's own
      MAC (BlueZ default alias; a "variation of the MAC").
    * ``"foreign_mac"`` — a MAC-shaped name that normalises to a MAC **other**
      than the device's own address (anomaly worth surfacing).
    * ``"real"`` — a genuine, non-MAC name.
    """
    if not isinstance(name, str) or not name.strip():
        return "empty"
    if is_mac_shaped(name):
        return "placeholder" if normalize_mac(name) == normalize_mac(mac) else "foreign_mac"
    return "real"


def _get(device: Dict[str, Any], *keys: str) -> Any:
    """Fetch the first present key from a flat row or a nested ``device`` dict."""
    for k in keys:
        if k in device and device[k] is not None:
            return device[k]
    nested = device.get("device")
    if isinstance(nested, dict):
        for k in keys:
            if k in nested and nested[k] is not None:
                return nested[k]
    return None


def _clean_name(name: Any) -> Optional[str]:
    """Return a trimmed device name, or ``None`` for placeholder/empty values."""
    if not isinstance(name, str):
        return None
    stripped = name.strip()
    if not stripped or stripped.lower() in _PLACEHOLDER_NAMES:
        return None
    return stripped


def _as_bytes_hex(value: Any) -> str:
    """Best-effort hex rendering of a manufacturer_data BLOB / string."""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return str(value)


def _payload_signature(device: Dict[str, Any]) -> Optional[str]:
    """Stable SHA-256 signature of a device's advertised payload, or ``None``.

    Combines manufacturer data, service data, advertised UUIDs and the
    dissected protocol set (via :func:`dissect_advertisement`).  Returns ``None``
    when the device carries no payload signal at all (so such rows stay
    ungroupable singletons rather than collapsing into one meaningless bucket).
    """
    mfr_hex = _as_bytes_hex(_get(device, "manufacturer_data"))
    mfr_id = _get(device, "manufacturer_id")
    svc_raw = _get(device, "service_data")
    uuids_raw = _get(device, "uuids")

    svc = svc_raw if isinstance(svc_raw, str) else (json.dumps(svc_raw, sort_keys=True) if svc_raw else "")
    uuids = uuids_raw if isinstance(uuids_raw, str) else (json.dumps(uuids_raw, sort_keys=True) if uuids_raw else "")

    if not (mfr_hex or svc or uuids or mfr_id is not None):
        return None

    protocols: List[str] = []
    try:
        from bleep.analysis.adv_dissect import dissect_advertisement

        mfr_map = {int(mfr_id): bytes.fromhex(mfr_hex)} if (mfr_id is not None and mfr_hex) else None
        parsed_uuids = None
        if uuids:
            try:
                loaded = json.loads(uuids) if isinstance(uuids_raw, str) else uuids_raw
                if isinstance(loaded, list):
                    parsed_uuids = [str(u) for u in loaded]
            except (TypeError, ValueError):
                parsed_uuids = None
        protocols = dissect_advertisement(
            manufacturer_data=mfr_map,
            service_uuids=parsed_uuids,
        )["summary"]["protocols"]
    except Exception:  # noqa: BLE001 - signature must never break grouping
        protocols = []

    blob = json.dumps(
        {"m_id": mfr_id, "m": mfr_hex, "s": svc, "u": uuids, "p": sorted(protocols)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _fingerprint(device: Dict[str, Any], strategy: str) -> Optional[Any]:
    """Return a grouping key for *device* under *strategy*, or ``None``.

    ``None`` marks a device that carries no stable anchor under the chosen
    strategy; the caller keeps it as its own singleton (never merged blindly).
    """
    name = _clean_name(_get(device, "name"))
    if strategy == "name":
        return ("name", name) if name else None
    if strategy == "name_mfr":
        if name is None:
            return None
        return ("name_mfr", name, _get(device, "manufacturer_id"))
    if strategy == "payload":
        sig = _payload_signature(device)
        if sig is not None:
            return ("payload", sig)
        # Fall back to name so a payload-less but named device is still anchored.
        return ("name", name) if name else None
    raise ValueError(f"unknown identity strategy: {strategy!r}")


def _min_ts(values: List[Any]) -> Optional[str]:
    present = [v for v in values if v]
    return min(present) if present else None


def _max_ts(values: List[Any]) -> Optional[str]:
    present = [v for v in values if v]
    return max(present) if present else None


def collapse_identities(devices: List[Dict[str, Any]],
                        strategy: str = "name") -> Dict[str, Any]:
    """Group *devices* into heuristic identity clusters (DB-4).

    Args:
        devices: Device row dicts (flat ``get_devices`` rows or nested
          ``get_device_detail`` shapes); each must expose a ``mac``.
        strategy: One of :data:`STRATEGIES` — ``"name"`` (default; stable
          advertised name), ``"name_mfr"`` (name + manufacturer id), or
          ``"payload"`` (manufacturer/service/UUID/protocol signature, name
          fallback).

    Returns:
        A dict with:
          * ``clusters`` — list of ``{identity, members:[mac...], size,
            first_seen, last_seen, device_types, addr_types, ungrouped}``,
            sorted by descending ``size`` then identity.  ``ungrouped`` is True
            for singletons with no stable anchor under *strategy*.
          * ``raw_count`` — number of input device rows.
          * ``collapsed_count`` — number of clusters.
          * ``multi_member_count`` — clusters with more than one member (the
            rows actually folded by collapse).
          * ``strategy`` / ``method`` (``"heuristic"``) / ``irk_resolved``
            (``False``) — provenance so a grouped identity is never mistaken for
            a cryptographically resolved one.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown identity strategy: {strategy!r} (expected one of {STRATEGIES})")

    buckets: Dict[Any, List[Dict[str, Any]]] = {}
    order: List[Any] = []
    anon_seq = 0

    for dev in devices:
        mac = _get(dev, "mac")
        key = _fingerprint(dev, strategy)
        ungrouped = key is None
        if ungrouped:
            # Unique key per anchor-less device so it stays a singleton.
            key = ("__ungrouped__", mac, anon_seq)
            anon_seq += 1
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(dev)

    clusters: List[Dict[str, Any]] = []
    for key in order:
        members = buckets[key]
        macs = [_get(m, "mac") for m in members]
        names = [n for n in (_clean_name(_get(m, "name")) for m in members) if n]
        is_ungrouped = isinstance(key, tuple) and key[0] == "__ungrouped__"
        identity = names[0] if names else "(anonymous)"
        clusters.append({
            "identity": identity,
            "members": macs,
            "size": len(members),
            "first_seen": _min_ts([_get(m, "first_seen") for m in members]),
            "last_seen": _max_ts([_get(m, "last_seen") for m in members]),
            "device_types": sorted({t for m in members if (t := _get(m, "device_type"))}),
            "addr_types": sorted({t for m in members if (t := _get(m, "addr_type"))}),
            "ungrouped": is_ungrouped,
        })

    clusters.sort(key=lambda c: (-c["size"], str(c["identity"])))

    return {
        "clusters": clusters,
        "raw_count": len(devices),
        "collapsed_count": len(clusters),
        "multi_member_count": sum(1 for c in clusters if c["size"] > 1),
        "strategy": strategy,
        "method": "heuristic",
        "irk_resolved": False,
    }
