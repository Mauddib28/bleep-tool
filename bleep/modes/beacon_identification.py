"""Beacon identification — thin survey wrapper with post-filter scoring.

Reuses ``SurveyCensus`` / LE round helpers from survey mode. Does not create a
second discovery engine. See ``bleep/docs/beacon_identification.md`` (operator
guide, scoring model, output schema) and
``bleep/docs/archive/beacon_identification_plan.md`` (historical design record).
"""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import json
import signal
import sys
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bleep.core.output import OutputContext

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.core.errors import BLEEPError
from bleep.modes.survey import SurveyCensus, DeviceSighting, _run_le_round, _sighandler

__all__ = ["run", "score_candidate"]


def _oui_match(mac: str, oui: Optional[str]) -> bool:
    if not oui:
        return True
    prefix = oui.strip().upper().rstrip(":")
    return mac.upper().startswith(prefix)


def _name_match(name: Optional[str], pattern: Optional[str]) -> bool:
    if not pattern:
        return True
    if not name:
        return False
    return fnmatch.fnmatch(name, pattern)


def _rssi_bucket(rssi: Optional[int]) -> int:
    if rssi is None:
        return 0
    if rssi >= -50:
        return 10
    if rssi >= -65:
        return 7
    if rssi >= -80:
        return 4
    return 1


def _decode_sighting(s: DeviceSighting) -> Dict[str, Any]:
    from bleep.analysis.adv_dissect import dissect_advertisement

    return dissect_advertisement(
        manufacturer_data=s.manufacturer_data or None,
        service_data=s.service_data or None,
        service_uuids=sorted(s.uuids) or None,
    )


def _extract_ibeacon(dissection: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for entry in dissection.get("manufacturer_data") or []:
        decoded = entry.get("decoded") or {}
        if decoded.get("protocol") in ("ibeacon", "ibeacon_compact"):
            return {
                "major": decoded.get("major"),
                "minor": decoded.get("minor"),
                "tx_power": decoded.get("tx_power"),
                "uuid": decoded.get("uuid"),
                "protocol": decoded.get("protocol"),
            }
    return None


def _extract_eddystone(dissection: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for entry in dissection.get("service_data") or []:
        decoded = entry.get("decoded") or {}
        if decoded.get("protocol") == "eddystone":
            return {
                "frame": decoded.get("frame"),
                "url": decoded.get("url"),
                "confidence": "high",
            }
    for entry in dissection.get("service_uuids") or []:
        decoded = entry.get("decoded") or {}
        if decoded.get("frame") == "pending":
            return {
                "frame": "pending",
                "url": None,
                "confidence": "low",
            }
    return None


def score_candidate(
    s: DeviceSighting,
    *,
    oui: Optional[str],
    name_glob: Optional[str],
    major: Optional[int],
    minor: Optional[int],
    ibeacon_uuid: Optional[str],
    eddystone_url: Optional[str],
    max_sightings: int,
    dissection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute deterministic score and decoded fields for one sighting."""
    dissection = dissection or _decode_sighting(s)
    protocols = list((dissection.get("summary") or {}).get("protocols") or [])
    ibeacon = _extract_ibeacon(dissection)
    eddystone = _extract_eddystone(dissection)

    score = 0
    if oui and _oui_match(s.mac, oui):
        score += 20
    if name_glob and _name_match(s.name, name_glob):
        score += 25
    if ibeacon is not None:
        maj_ok = major is None or ibeacon.get("major") == major
        min_ok = minor is None or ibeacon.get("minor") == minor
        if maj_ok and min_ok and (major is not None or minor is not None):
            score += 40
        elif major is None and minor is None:
            # Decoded beacon evidence without an explicit major/minor filter.
            score += 40
        if ibeacon_uuid and ibeacon.get("uuid"):
            want = ibeacon_uuid.replace("-", "").lower()
            have = str(ibeacon["uuid"]).replace("-", "").lower()
            if want in have or have in want:
                score += 0  # uuid match folded into major/minor evidence; no extra weight in plan
    if eddystone is not None:
        if eddystone.get("frame") == "pending":
            score += 5
        elif eddystone_url and eddystone.get("url") and eddystone_url.lower() in str(eddystone["url"]).lower():
            score += 15
        elif eddystone.get("url"):
            score += 15 if not eddystone_url else 0
    if max_sightings > 0:
        score += round(10 * s.sighting_count / max_sightings)
    score += _rssi_bucket(s.rssi_avg)

    return {
        "address": s.mac,
        "name": s.name,
        "score": score,
        "sightings": s.sighting_count,
        "rssi_avg": s.rssi_avg,
        "rssi_min": s.rssi_min,
        "rssi_max": s.rssi_max,
        "protocols": protocols,
        "ibeacon": (
            {
                "major": ibeacon.get("major") if ibeacon else None,
                "minor": ibeacon.get("minor") if ibeacon else None,
                "tx_power": ibeacon.get("tx_power") if ibeacon else None,
                "uuid": ibeacon.get("uuid") if ibeacon else None,
            }
            if ibeacon
            else None
        ),
        "eddystone": eddystone,
        "fingerprint_changed": bool(s.fingerprint_changed) or None,
        "payload_history": list(s.payload_history) or None,
        "first_seen": datetime.datetime.fromtimestamp(
            s.first_seen, tz=datetime.timezone.utc
        ).isoformat(),
        "last_seen": datetime.datetime.fromtimestamp(
            s.last_seen, tz=datetime.timezone.utc
        ).isoformat(),
    }


def _passes_filters(
    candidate: Dict[str, Any],
    *,
    oui: Optional[str],
    name_glob: Optional[str],
    major: Optional[int],
    minor: Optional[int],
    ibeacon_uuid: Optional[str],
    eddystone_url: Optional[str],
) -> bool:
    if oui and not _oui_match(candidate["address"], oui):
        return False
    if name_glob and not _name_match(candidate.get("name"), name_glob):
        return False
    ibeacon = candidate.get("ibeacon") or {}
    if major is not None and ibeacon.get("major") != major:
        return False
    if minor is not None and ibeacon.get("minor") != minor:
        return False
    if ibeacon_uuid:
        have = (ibeacon.get("uuid") or "").replace("-", "").lower()
        want = ibeacon_uuid.replace("-", "").lower()
        if not have or (want not in have and have not in want):
            return False
    if eddystone_url:
        eddystone = candidate.get("eddystone") or {}
        url = (eddystone.get("url") or "").lower()
        if eddystone_url.lower() not in url:
            return False
    return True


def run(args: argparse.Namespace, output: "OutputContext | None" = None) -> int:
    """Execute beacon-identification with survey-backed LE rounds."""
    from bleep.core.output import OutputContext
    from bleep.core.log import set_output_mode

    if output is None:
        output = OutputContext()
    set_output_mode(output.mode)

    global _stop
    import bleep.modes.survey as _survey

    _survey._stop = False
    prev_sigint = signal.getsignal(signal.SIGINT)
    prev_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _sighandler)
    signal.signal(signal.SIGTERM, _sighandler)

    duration = int(getattr(args, "duration", 300) or 300)
    round_time = int(getattr(args, "round_time", 15) or 15)
    live = bool(getattr(args, "live", False))
    oui = getattr(args, "oui", None)
    name_glob = getattr(args, "name", None)
    major = getattr(args, "major", None)
    minor = getattr(args, "minor", None)
    ibeacon_uuid = getattr(args, "ibeacon_uuid", None)
    eddystone_url = getattr(args, "eddystone_url", None)
    min_rssi = getattr(args, "min_rssi", None)

    started = datetime.datetime.now(tz=datetime.timezone.utc)
    census = SurveyCensus()
    round_num = 0
    t_start = time.monotonic()
    elapsed = 0.0

    try:
        output.emit_progress(
            f"[beacon-identification] duration={duration}s round-time={round_time}s "
            f"oui={oui or '-'} name={name_glob or '-'}"
        )
        while elapsed < duration and not _survey._stop:
            round_num += 1
            remaining = duration - elapsed
            rt = min(round_time, max(1, int(remaining)))
            try:
                census.merge_le_results(_run_le_round(rt, quiet=True), round_num=round_num)
            except BLEEPError as exc:
                output.emit_progress(f"[beacon-identification] round {round_num} error: {exc}")
            elapsed = time.monotonic() - t_start
            if live:
                output.emit_progress(
                    f"[beacon-identification] round {round_num} | "
                    f"{census.device_count} devices | elapsed {int(elapsed)}s/{duration}s"
                )
    finally:
        signal.signal(signal.SIGINT, prev_sigint)
        signal.signal(signal.SIGTERM, prev_sigterm)

    filtered = census.filter(min_rssi=min_rssi, min_sightings=1)
    max_sightings = max((s.sighting_count for s in filtered), default=1)
    candidates: List[Dict[str, Any]] = []
    for s in filtered:
        scored = score_candidate(
            s,
            oui=oui,
            name_glob=name_glob,
            major=major,
            minor=minor,
            ibeacon_uuid=ibeacon_uuid,
            eddystone_url=eddystone_url,
            max_sightings=max_sightings,
        )
        if not _passes_filters(
            scored,
            oui=oui,
            name_glob=name_glob,
            major=major,
            minor=minor,
            ibeacon_uuid=ibeacon_uuid,
            eddystone_url=eddystone_url,
        ):
            continue
        clean = {k: v for k, v in scored.items() if v is not None}
        candidates.append(clean)

    candidates.sort(
        key=lambda c: (
            -int(c.get("score") or 0),
            -(c.get("rssi_avg") if c.get("rssi_avg") is not None else -999),
            -int(c.get("sightings") or 0),
            c.get("address") or "",
        )
    )

    completed = datetime.datetime.now(tz=datetime.timezone.utc)
    result = {
        "identification": {
            "duration_s": duration,
            "round_time_s": round_time,
            "filters": {
                k: v
                for k, v in {
                    "oui": oui,
                    "name": name_glob,
                    "major": major,
                    "minor": minor,
                    "ibeacon_uuid": ibeacon_uuid,
                    "eddystone_url": eddystone_url,
                    "min_rssi": min_rssi,
                }.items()
                if v is not None
            },
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
        },
        "candidates": candidates,
    }

    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    out_path = getattr(args, "output", None)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        output.emit_progress(f"[beacon-identification] wrote {out_path}")
    else:
        sys.stdout.write(text)

    if not getattr(args, "quiet", False):
        if not candidates:
            print_and_log("[beacon-identification] No matching candidates", LOG__GENERAL)
        else:
            print_and_log(
                f"[beacon-identification] {len(candidates)} candidate(s):",
                LOG__GENERAL,
            )
            for c in candidates[:20]:
                ib = c.get("ibeacon") or {}
                detail = ""
                if ib.get("major") is not None:
                    detail += f" m={ib.get('major')}/i={ib.get('minor')} tx={ib.get('tx_power')}"
                protos = ",".join(c.get("protocols") or [])
                print_and_log(
                    f"  {c.get('score'):3d}  {c.get('address')} ({c.get('name') or '?'}) "
                    f"rssi={c.get('rssi_avg')} [{protos}]{detail}",
                    LOG__GENERAL,
                )
    return 0
