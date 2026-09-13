"""Opt-in, non-merging LE identity correlation (issue #2).

A dual-mode peer frequently exposes its GATT database **only** under an LE
resolvable-private address (RPA), while its BR/EDR public address resolves no
GATT attributes.  Without the peer's IRK (exchanged only during bonding) the two
addresses cannot be *soundly* linked, so this module offers a deliberately
opt-in, heuristic correlation using the non-address attributes BlueZ exposes on
``org.bluez.Device1`` (``Name`` / ``Icon`` / ``Class``).

It is a **presentational hint only**: it never merges or mutates observation
data.  Because a ``Name`` can be a factory default (e.g. ``DESKTOP-1APRSIB`` is a
default Windows hostname), a Name-only match is reported as *low* confidence and
corroboration by Icon / Class / a random address type raises it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__DEBUG


def _norm(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def correlate_le_identity(target_mac: str, *, adapter: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Return LE addresses likely belonging to the same device as *target_mac*.

    Candidates are ranked by a heuristic confidence score built from matching
    ``Name`` (required), corroborated by ``Icon``, ``Class`` and a ``random``
    address type.  Reuses :meth:`get_discovered_devices` (BlueZ managed objects)
    so no extra D-Bus traffic is generated.  Read-only and non-merging.

    Returns an empty list when the target is unknown, exposes no ``Name`` to
    match on, or no other known device matches.
    """
    if adapter is None:
        from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
        adapter = _Adapter()

    try:
        devices = adapter.get_discovered_devices()
    except Exception as exc:  # pragma: no cover - defensive
        print_and_log(f"[correlate] device enumeration failed: {exc}", LOG__DEBUG)
        return []

    tmac = target_mac.upper()
    target = next((d for d in devices if str(d.get("address", "")).upper() == tmac), None)
    if target is None:
        return []

    t_name = _norm(target.get("name") or target.get("alias"))
    t_icon = _norm(target.get("icon"))
    t_class = _norm(target.get("device_class"))
    if not t_name:
        # No shared, non-address attribute to correlate on — refuse to guess.
        return []

    candidates: List[Dict[str, Any]] = []
    for dev in devices:
        addr = str(dev.get("address", "")).upper()
        if not addr or addr == tmac:
            continue
        if _norm(dev.get("name") or dev.get("alias")) != t_name:
            continue

        matched = ["name"]
        score = 1
        if t_icon and _norm(dev.get("icon")) == t_icon:
            score += 1
            matched.append("icon")
        if t_class and _norm(dev.get("device_class")) == t_class:
            score += 1
            matched.append("class")
        if _norm(dev.get("address_type")) == "random":
            score += 1
            matched.append("random-addr")
        has_uuids = bool(dev.get("uuids"))
        if has_uuids:
            matched.append("gatt-uuids")

        confidence = "high" if score >= 3 else ("medium" if score == 2 else "low")
        candidates.append(
            {
                "address": addr,
                "name": dev.get("name") or dev.get("alias"),
                "address_type": dev.get("address_type"),
                "has_gatt_uuids": has_uuids,
                "matched_on": matched,
                "score": score,
                "confidence": confidence,
            }
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates
