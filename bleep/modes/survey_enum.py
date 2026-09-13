"""Concurrent enumerator for multi-antenna survey (Phase B).

Collector radios stay in discovery on the orchestrator thread. A worker
thread GATT-enumerates census devices in priority order and will not
re-pick a MAC that already succeeded (or was attempted) this run, even
when collectors keep incrementing ``sighting_count``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Set, Tuple

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.core.time_utils import utc_now, utc_now_iso

__all__ = [
    "parse_enumerator",
    "EnumeratorState",
    "pick_next",
    "queue_depth",
    "enumerate_one",
    "enumerator_worker",
    "DEFAULT_ENUM_COOLDOWN_S",
]

_ENUM_MODES = ("passive", "naggy", "pokey", "brute", "pair")
DEFAULT_ENUM_COOLDOWN_S = 3600
_CONNECT_WAIT_S = 15.0


def parse_enumerator(token: Optional[str]) -> Optional[Tuple[str, str]]:
    """Parse ``--enumerator hciN[:MODE]`` into ``(adapter_name, mode)``.

    Bare ``hciN`` defaults to ``passive``. ``brute`` is mapped to ``pokey``
    because survey enumeration has no ``--write-char`` payload set.
    """
    if not token:
        return None
    raw = token.strip()
    if not raw:
        return None
    if ":" in raw:
        name, _, mode = raw.partition(":")
        mode = (mode or "passive").strip().lower()
        name = name.strip()
    else:
        name, mode = raw, "passive"
    if mode not in _ENUM_MODES:
        raise ValueError(
            f"Invalid enumerator mode '{mode}' in '{token}' "
            f"(expected {'|'.join(_ENUM_MODES)})"
        )
    if mode == "brute":
        print_and_log(
            "[survey] enumerator mode 'brute' mapped to 'pokey' "
            "(no write-char payload in survey)",
            LOG__GENERAL,
        )
        mode = "pokey"
    if not name:
        raise ValueError(f"Invalid enumerator token '{token}'")
    return name, mode


@dataclass
class EnumeratorState:
    """Shared by the listen loop and the enumerator worker."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    done: Set[str] = field(default_factory=set)
    ok: Set[str] = field(default_factory=set)
    inflight: Optional[str] = None
    listen_over: bool = False
    stop: bool = False


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _recently_enumerated(
    sighting: Any,
    done: Set[str],
    ok: Set[str],
    inflight: Optional[str],
    cooldown_s: int,
    persist_db: bool,
) -> bool:
    """True if this MAC must not be picked (in-run or DB cooldown)."""
    mac = sighting.mac.upper()
    if mac in done or mac in ok or mac == inflight:
        return True
    at = getattr(sighting, "enumerated_at", None)
    if persist_db and cooldown_s > 0 and not at:
        try:
            from bleep.core.observations import get_enumeration_stamp

            _, at = get_enumeration_stamp(mac)
            if at:
                sighting.enumerated_at = at
        except Exception:
            at = None
    if persist_db and cooldown_s > 0 and at:
        parsed = _parse_iso(str(at) if not isinstance(at, str) else at)
        if parsed is not None and utc_now() - parsed < timedelta(seconds=cooldown_s):
            return True
    return False


def _eligible(
    census: Any,
    min_sightings: int,
    min_rssi: Optional[int],
) -> List[Any]:
    """Return live LE/dual sightings that meet census filters (no skip sets)."""
    out: List[Any] = []
    with census._lock:
        sightings = list(census._sightings.values())
    for s in sightings:
        if getattr(s, "is_cached", False):
            continue
        if s.sighting_count < min_sightings:
            continue
        if min_rssi is not None:
            avg = s.rssi_avg
            if avg is None or avg < min_rssi:
                continue
        if getattr(s, "device_type", None) == "classic":
            continue
        out.append(s)
    return out


def _sort_key(s: Any) -> Tuple:
    rssi = s.rssi_avg
    rssi_key = (1, 0) if rssi is None else (0, -int(rssi))
    return (-int(s.sighting_count or 0), -float(s.last_seen or 0.0), rssi_key)


def pick_next(
    census: Any,
    args: Any,
    state: EnumeratorState,
    persist_db: bool,
) -> Optional[Any]:
    """Highest-priority sighting that is not recently enumerated / in-flight."""
    min_sightings = getattr(args, "min_sightings", 1) or 1
    min_rssi = getattr(args, "min_rssi", None)
    cooldown = getattr(args, "enum_cooldown", DEFAULT_ENUM_COOLDOWN_S)
    if cooldown is None:
        cooldown = DEFAULT_ENUM_COOLDOWN_S
    with state.lock:
        done = set(state.done)
        ok = set(state.ok)
        inflight = state.inflight
    candidates = [
        s
        for s in _eligible(census, min_sightings, min_rssi)
        if not _recently_enumerated(s, done, ok, inflight, int(cooldown), persist_db)
    ]
    if not candidates:
        return None
    candidates.sort(key=_sort_key)
    return candidates[0]


def queue_depth(
    census: Any,
    args: Any,
    state: EnumeratorState,
    persist_db: bool,
) -> int:
    """Count MACs the worker would still pick (for ``--live``)."""
    min_sightings = getattr(args, "min_sightings", 1) or 1
    min_rssi = getattr(args, "min_rssi", None)
    cooldown = getattr(args, "enum_cooldown", DEFAULT_ENUM_COOLDOWN_S) or 0
    with state.lock:
        done = set(state.done)
        ok = set(state.ok)
        inflight = state.inflight
    n = 0
    for s in _eligible(census, min_sightings, min_rssi):
        if not _recently_enumerated(s, done, ok, inflight, int(cooldown), persist_db):
            n += 1
    return n


def enumerate_one(
    sighting: Any,
    session: Any,
    mode: str,
    persist_db: bool,
    state: EnumeratorState,
) -> bool:
    """Connect + GATT-enumerate one census device. Returns GATT success."""
    mac = sighting.mac.upper()
    addr_type = getattr(sighting, "addr_type", None)
    print_and_log(
        f"[survey] enumerator {session.adapter_name}:{mode} → {mac}",
        LOG__GENERAL,
    )
    with state.lock:
        state.inflight = mac
    connected = False
    try:
        connected = session.connect_device(
            mac, address_type=addr_type, timeout=_CONNECT_WAIT_S
        )
    except Exception as exc:
        print_and_log(f"[survey] ConnectDevice {mac}: {exc}", LOG__DEBUG)
    if not connected:
        print_and_log(
            f"[survey] no Device1 for {mac} on {session.adapter_name}",
            LOG__DEBUG,
        )
    enum_mode = "passive" if mode == "pair" else mode
    result = None
    success = False
    try:
        if mode == "pair":
            try:
                session.pair_device(mac)
            except Exception as exc:
                print_and_log(f"[survey] pair {mac}: {exc}", LOG__GENERAL)
        result = session.enumerate_device(mac, mode=enum_mode, skip_scan=True)
        success = bool(result is not None and getattr(result, "success", False))
        if success:
            stamp = utc_now_iso()
            sighting.enumerated_by = session.adapter_name
            sighting.enumerated_at = stamp
            with state.lock:
                state.ok.add(mac)
            if persist_db:
                try:
                    from bleep.core import observations as _obs

                    cols: dict = {
                        "enumerated_by": session.adapter_name,
                        "enumerated_at": stamp,
                    }
                    seen = sorted(getattr(sighting, "seen_by", None) or [])
                    if seen:
                        cols["seen_by"] = seen
                    _obs.upsert_device(mac, **cols)
                    if getattr(result, "persist_security_maps", None):
                        result.persist_security_maps(mac, source="survey-enum")
                except Exception as exc:
                    print_and_log(f"[survey] persist {mac}: {exc}", LOG__DEBUG)
        elif persist_db:
            try:
                from bleep.core import observations as _obs

                seen = sorted(getattr(sighting, "seen_by", None) or [])
                if seen:
                    _obs.upsert_device(mac, seen_by=seen)
            except Exception as exc:
                print_and_log(f"[survey] persist {mac}: {exc}", LOG__DEBUG)
    except Exception as exc:
        print_and_log(f"[survey] enumerate {mac}: {exc}", LOG__GENERAL)
    finally:
        session.disconnect_device(mac)
        with state.lock:
            state.done.add(mac)
            state.inflight = None
    return success


def enumerator_worker(
    census: Any,
    session: Any,
    mode: str,
    args: Any,
    state: EnumeratorState,
    persist_db: bool,
) -> None:
    """Pull priority targets until listen ends and the queue is empty."""
    from bleep.modes import survey as _survey

    try:
        while True:
            if state.stop or _survey._stop:
                break
            sighting = pick_next(census, args, state, persist_db)
            if sighting is None:
                with state.lock:
                    over = state.listen_over
                if over or state.stop or _survey._stop:
                    break
                time.sleep(0.4)
                continue
            enumerate_one(sighting, session, mode, persist_db, state)
    finally:
        # Release this thread's private D-Bus connection rather than leaking the
        # socket for the life of the process (see bleep.dbuslayer.bus).
        try:
            from bleep.dbuslayer.bus import close_thread_bus

            close_thread_bus()
        except Exception:
            pass
