"""BLEEP Survey Mode — long-duration passive device discovery.

Alternates LE and BR/EDR discovery rounds over a configurable duration,
deduplicates across rounds, tracks per-device RSSI history and sighting
counts, and writes a filtered device census to file or stdout in any of
the three AoI-accepted JSON formats (``simple``, ``objects``, ``grouped``).

The output feeds directly into ``bleep aoi scan <file>`` as a separate
pipeline step. GATT/SDP analysis stays with AoI unless ``--enumerator``
drains devices on a second adapter during the survey.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
import hashlib

if TYPE_CHECKING:
    from bleep.core.output import OutputContext

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__USER
from bleep.core.errors import BLEEPError, NotReadyError

__all__ = ["run"]

_stop = False
_bluez_warning: Optional[str] = None


def _sighandler(sig, frame):
    global _stop
    _stop = True
    print(
        "\n[survey] Interrupted — writing output with data collected so far...",
        file=sys.stderr,
    )


def _on_bluez_stall():
    global _bluez_warning
    _bluez_warning = "BlueZ service stall detected — scan results may be incomplete"


def _on_bluez_unavailable():
    global _bluez_warning
    _bluez_warning = "BlueZ service unavailable — skipping round"


def _start_health_monitor() -> bool:
    """Start BlueZServiceMonitor if D-Bus bindings are available. Returns True on success."""
    try:
        from bleep.dbuslayer.bluez_monitor import (
            get_monitor,
            start_monitoring,
            register_stall_callback,
        )
        monitor = get_monitor()
        monitor.register_availability_callback(_on_bluez_unavailable, available=False)
        register_stall_callback(_on_bluez_stall)
        start_monitoring()
        return True
    except Exception:
        return False


def _stop_health_monitor():
    try:
        from bleep.dbuslayer.bluez_monitor import stop_monitoring, get_monitor
        monitor = get_monitor()
        monitor.unregister_callback(_on_bluez_stall)
        monitor.unregister_callback(_on_bluez_unavailable)
        stop_monitoring()
    except Exception:
        pass


def _interruptible_sleep(seconds: float) -> None:
    """Sleep up to *seconds*, in <=1s slices, honouring a pending ``_stop``.

    A skipped round (adapter not ready) fails fast, so the loop must pace itself
    to avoid a busy-loop for the remaining duration.  Slicing the wait keeps the
    survey responsive to SIGINT/SIGTERM, which set ``_stop`` without raising.
    """
    end = time.monotonic() + seconds
    while not _stop:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(1.0, remaining))


def _attempt_adapter_recovery(adapter_name: str) -> bool:
    """Best-effort in-run adapter power recovery (opt-in via ``--auto-recover``).

    Reuses the existing adapter power helpers rather than introducing a new
    mechanism: first re-assert ``Powered``, then fall back to a full
    power-cycle if the controller is still not ready.  Returns ``True`` when the
    adapter is ready after the attempt.  Never raises — a failed recovery simply
    returns ``False`` so the caller falls back to skip-and-backoff.
    """
    try:
        from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
        adapter = _Adapter(adapter_name)
    except Exception as exc:  # noqa: BLE001 - missing bindings / D-Bus init failure
        print_and_log(f"[survey] Adapter recovery unavailable: {exc}", LOG__DEBUG)
        return False
    try:
        if adapter.is_ready():
            return True
        adapter.set_powered(True)
        time.sleep(1.0)
        if adapter.is_ready():
            return True
        adapter.power_cycle()
        time.sleep(1.0)
        return adapter.is_ready()
    except Exception as exc:  # noqa: BLE001 - recovery is best-effort
        print_and_log(f"[survey] Adapter recovery attempt failed: {exc}", LOG__DEBUG)
        return False


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DeviceSighting:
    """Per-device statistics accumulated across survey rounds."""

    mac: str
    name: Optional[str] = None
    device_type: str = "unknown"
    first_seen: float = 0.0
    last_seen: float = 0.0
    sighting_count: int = 0
    rssi_min: Optional[int] = None
    rssi_max: Optional[int] = None
    rssi_sum: int = 0
    rssi_count: int = 0
    addr_type: Optional[str] = None
    device_class: Optional[int] = None
    manufacturer_id: Optional[int] = None
    uuids: set = field(default_factory=set)
    _seen_transports: set = field(default_factory=set)
    # Phase 6A — Beacon fingerprinting
    manufacturer_data: Dict[int, bytes] = field(default_factory=dict)
    service_data: Dict[str, bytes] = field(default_factory=dict)
    tx_power: Optional[int] = None
    appearance: Optional[int] = None
    fingerprint_changed: bool = False
    # Phase 5 — Cached device provenance
    is_cached: bool = False
    # D2 — adapters (antennas) that observed this device across the run
    seen_by: set = field(default_factory=set)
    # Dual-antenna: enumerator radio that GATT-succeeded (not attempts)
    enumerated_by: Optional[str] = None
    enumerated_at: Optional[str] = None
    # Phase 4d — AdvMonitor DeviceFound tagged this Device1
    advmon_seen: bool = False
    advertising_flags: Optional[bytes] = None
    # S0b+ — per-round advertisement snapshots (non-cumulative) + last signature
    payload_history: List[Dict[str, Any]] = field(default_factory=list)
    last_signature: Optional[str] = None
    _last_round_mfr: Dict[int, bytes] = field(default_factory=dict, repr=False)
    _last_round_svc: Dict[str, bytes] = field(default_factory=dict, repr=False)

    @property
    def rssi_avg(self) -> Optional[int]:
        if self.rssi_count == 0:
            return None
        return round(self.rssi_sum / self.rssi_count)


_TYPE_RANK = {"unknown": 0, "le": 1, "classic": 1, "dual": 2}

_CLASSIFIER_TYPE_MAP = {"br/edr": "classic", "le": "le", "dual": "dual", "classic": "classic"}


def _resolve_device_type(entry: Dict[str, Any], transport_label: str) -> str:
    """Derive device_type from the adapter classifier result, falling back to transport label."""
    classifier_type = entry.get("type", "").lower()
    return _CLASSIFIER_TYPE_MAP.get(classifier_type, transport_label)


class SurveyCensus:
    """In-memory accumulator for device sightings across survey rounds."""

    def __init__(self) -> None:
        self._sightings: Dict[str, DeviceSighting] = {}
        # Guards mutation/iteration so multiple collector threads (one per
        # adapter, D2) can merge concurrently into a single census.
        self._lock = threading.RLock()

    @property
    def device_count(self) -> int:
        with self._lock:
            return len(self._sightings)

    @staticmethod
    def _merge_mfr_data(
        existing: Dict[int, bytes], incoming: Dict,
    ) -> bool:
        """Union-merge manufacturer_data; keep longest payload per key.

        Returns True if an existing key's payload changed (fingerprint change):
        either a strictly longer payload replaced it, or a same-length payload with
        differing bytes (e.g. iBeacon/Eddystone rotation) superseded it. Shorter
        payloads never replace (avoids truncated-advert regressions).
        """
        changed = False
        for k, v in incoming.items():
            key = int(k)
            payload = v if isinstance(v, bytes) else bytes(v) if isinstance(v, (list, bytearray)) else v
            if key in existing:
                if isinstance(payload, bytes) and (
                    len(payload) > len(existing[key])
                    or (len(payload) == len(existing[key]) and payload != existing[key])
                ):
                    existing[key] = payload
                    changed = True
            else:
                existing[key] = payload if isinstance(payload, bytes) else payload
        return changed

    @staticmethod
    def _merge_svc_data(
        existing: Dict[str, bytes], incoming: Dict,
    ) -> bool:
        """Union-merge service_data; keep longest payload per UUID key.

        Returns True if an existing key's payload changed (fingerprint change):
        either a strictly longer payload replaced it, or a same-length payload with
        differing bytes (e.g. a rotating status byte) superseded it. Shorter payloads
        never replace (avoids truncated-advert regressions).
        """
        changed = False
        for k, v in incoming.items():
            key = str(k)
            payload = v if isinstance(v, bytes) else bytes(v) if isinstance(v, (list, bytearray)) else v
            if key in existing:
                if isinstance(payload, bytes) and (
                    len(payload) > len(existing[key])
                    or (len(payload) == len(existing[key]) and payload != existing[key])
                ):
                    existing[key] = payload
                    changed = True
            else:
                existing[key] = payload if isinstance(payload, bytes) else payload
        return changed

    @staticmethod
    def _coerce_mfr_map(incoming: Optional[Dict]) -> Dict[int, bytes]:
        out: Dict[int, bytes] = {}
        for k, v in (incoming or {}).items():
            try:
                key = int(k)
            except (TypeError, ValueError):
                continue
            if isinstance(v, bytes):
                out[key] = v
            elif isinstance(v, (list, bytearray)):
                out[key] = bytes(v)
            else:
                continue
        return out

    @staticmethod
    def _coerce_svc_map(incoming: Optional[Dict]) -> Dict[str, bytes]:
        out: Dict[str, bytes] = {}
        for k, v in (incoming or {}).items():
            key = str(k)
            if isinstance(v, bytes):
                out[key] = v
            elif isinstance(v, (list, bytearray)):
                out[key] = bytes(v)
            else:
                continue
        return out

    @staticmethod
    def _signature_maps(
        incoming_mfr: Dict[int, bytes],
        incoming_svc: Dict[str, bytes],
        prev_mfr: Dict[int, bytes],
        prev_svc: Dict[str, bytes],
    ) -> tuple[Dict[int, bytes], Dict[str, bytes]]:
        """Build per-round maps for signature comparison.

        Keys present this round are included. Same-key truncated (strictly shorter)
        payloads reuse the previous round value so truncated adverts do not look
        like rotation. Absent keys (vs previous) are omissions and change the set.
        """
        mfr: Dict[int, bytes] = {}
        for key, payload in incoming_mfr.items():
            prev = prev_mfr.get(key)
            if prev is not None and len(payload) < len(prev):
                mfr[key] = prev
            else:
                mfr[key] = payload
        svc: Dict[str, bytes] = {}
        for key, payload in incoming_svc.items():
            prev = prev_svc.get(key)
            if prev is not None and len(payload) < len(prev):
                svc[key] = prev
            else:
                svc[key] = payload
        return mfr, svc

    @staticmethod
    def _round_signature(
        manufacturer_data: Dict[int, bytes],
        service_data: Dict[str, bytes],
        uuids: Optional[List[str]] = None,
    ) -> str:
        """Deterministic SHA-256 of this round's advertisement snapshot."""
        try:
            from bleep.analysis.adv_dissect import dissect_advertisement
            protocols = dissect_advertisement(
                manufacturer_data=manufacturer_data or None,
                service_data=service_data or None,
                service_uuids=list(uuids or []),
            )["summary"]["protocols"]
        except Exception:  # noqa: BLE001 - signature must never break merge
            protocols = []
        payload = {
            "mfr": {str(k): manufacturer_data[k].hex() for k in sorted(manufacturer_data)},
            "svc": {k: service_data[k].hex() for k in sorted(service_data)},
            "protocols": list(protocols),
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _merge_entry(
        self,
        mac: str,
        entry: Dict[str, Any],
        transport_label: str,
        adapter: Optional[str] = None,
        round_num: Optional[int] = None,
    ) -> None:
        mac_up = mac.upper()
        now = time.time()
        rssi = entry.get("rssi")
        if rssi is None:
            rssi = entry.get("rssi_last")

        resolved_type = _resolve_device_type(entry, transport_label)

        # A cached re-read is a device BlueZ still lists in GetManagedObjects but
        # that did not advertise this round: no fresh RSSI *and* paired/bonded (so it
        # persists as a managed object). RSSI alone is not a reliable liveness signal
        # under passive scanning (volatile; ~96% capture — see LR-1b/LR-6), so we key
        # on the same predicate as ``is_cached`` rather than raw RSSI. Unpaired
        # advertisers with a transiently-missing RSSI are still counted.
        is_cached_reread = rssi is None and bool(
            entry.get("paired", False) or entry.get("bonded", False)
        )
        from_advmon = bool(entry.get("advmon"))

        if mac_up in self._sightings:
            s = self._sightings[mac_up]
            if adapter:
                s.seen_by.add(adapter)
            if from_advmon:
                s.advmon_seen = True
            if not is_cached_reread and not from_advmon:
                s.sighting_count += 1
            s.last_seen = now
            if entry.get("name") or entry.get("alias"):
                s.name = entry.get("name") or entry.get("alias") or s.name
            if rssi is not None:
                s.rssi_min = min(s.rssi_min, rssi) if s.rssi_min is not None else rssi
                s.rssi_max = max(s.rssi_max, rssi) if s.rssi_max is not None else rssi
                s.rssi_sum += rssi
                s.rssi_count += 1
                if s.is_cached:
                    s.is_cached = False
            s.uuids |= set(entry.get("uuids") or [])
            if entry.get("manufacturer_data"):
                fp_changed = self._merge_mfr_data(s.manufacturer_data, entry["manufacturer_data"])
                if fp_changed:
                    s.fingerprint_changed = True
                for mfr_key in entry["manufacturer_data"]:
                    s.manufacturer_id = int(mfr_key)
                    break
            if entry.get("service_data"):
                fp_changed = self._merge_svc_data(s.service_data, entry["service_data"])
                if fp_changed:
                    s.fingerprint_changed = True
            if entry.get("tx_power") is not None:
                s.tx_power = int(entry["tx_power"])
            if entry.get("appearance") is not None:
                s.appearance = int(entry["appearance"])
            if entry.get("advertising_flags"):
                flags = entry["advertising_flags"]
                s.advertising_flags = flags if isinstance(flags, bytes) else bytes(flags)
            s._seen_transports.add(resolved_type)
            if len(s._seen_transports) > 1:
                s.device_type = "dual"
            elif _TYPE_RANK.get(resolved_type, 0) > _TYPE_RANK.get(s.device_type, 0):
                s.device_type = resolved_type
        else:
            mfr = {}
            if entry.get("manufacturer_data"):
                for k, v in entry["manufacturer_data"].items():
                    mfr[int(k)] = v if isinstance(v, bytes) else bytes(v) if isinstance(v, (list, bytearray)) else v
            svc = {}
            if entry.get("service_data"):
                for k, v in entry["service_data"].items():
                    svc[str(k)] = v if isinstance(v, bytes) else bytes(v) if isinstance(v, (list, bytearray)) else v
            ds = DeviceSighting(
                mac=mac_up,
                name=entry.get("name") or entry.get("alias"),
                device_type=resolved_type,
                first_seen=now,
                last_seen=now,
                sighting_count=0 if is_cached_reread else 1,
                addr_type=entry.get("addr_type") or entry.get("address_type"),
                device_class=entry.get("device_class"),
                uuids=set(entry.get("uuids") or []),
                _seen_transports={resolved_type},
                manufacturer_data=mfr,
                service_data=svc,
                tx_power=int(entry["tx_power"]) if entry.get("tx_power") is not None else None,
                appearance=int(entry["appearance"]) if entry.get("appearance") is not None else None,
                is_cached=is_cached_reread,
                seen_by={adapter} if adapter else set(),
                advmon_seen=from_advmon,
                advertising_flags=(
                    entry["advertising_flags"]
                    if isinstance(entry.get("advertising_flags"), bytes)
                    else bytes(entry["advertising_flags"])
                    if entry.get("advertising_flags")
                    else None
                ),
            )
            if rssi is not None:
                ds.rssi_min = rssi
                ds.rssi_max = rssi
                ds.rssi_sum = rssi
                ds.rssi_count = 1
            if entry.get("manufacturer_data"):
                for mfr_key in entry["manufacturer_data"]:
                    ds.manufacturer_id = int(mfr_key)
                    break
            self._sightings[mac_up] = ds

        # S0b+: compare consecutive live-round advertisement signatures. Cached
        # rereads are not advertisement snapshots and must not invent rotation.
        # AdvMonitor Found is a Device1 overlay, not a new discovery round —
        # tagging advmon_seen must not treat a sparse GetAll as payload rotation.
        s = self._sightings[mac_up]
        if not is_cached_reread and not from_advmon and (
            entry.get("manufacturer_data")
            or entry.get("service_data")
            or entry.get("uuids")
            or round_num is not None
        ):
            round_mfr = self._coerce_mfr_map(entry.get("manufacturer_data"))
            round_svc = self._coerce_svc_map(entry.get("service_data"))
            # Only record a history snapshot when this round carried advertisement
            # payload fields or an explicit round number from the survey loop.
            if round_mfr or round_svc or entry.get("uuids") or round_num is not None:
                sig_mfr, sig_svc = self._signature_maps(
                    round_mfr, round_svc, s._last_round_mfr, s._last_round_svc
                )
                # Key removal: previous keys absent from this round change the set.
                # Represent removals by signing only this round's (truncation-stable) maps.
                sig = self._round_signature(
                    sig_mfr, sig_svc, list(entry.get("uuids") or [])
                )
                if s.last_signature is not None and sig != s.last_signature:
                    s.fingerprint_changed = True
                if round_num is not None and (round_mfr or round_svc or entry.get("uuids")):
                    try:
                        from bleep.analysis.adv_dissect import dissect_advertisement
                        protocols = dissect_advertisement(
                            manufacturer_data=round_mfr or None,
                            service_data=round_svc or None,
                            service_uuids=list(entry.get("uuids") or []),
                        )["summary"]["protocols"]
                    except Exception:  # noqa: BLE001
                        protocols = []
                    s.payload_history.append(
                        {
                            "round": int(round_num),
                            "ts": datetime.datetime.fromtimestamp(
                                now, tz=datetime.timezone.utc
                            ).isoformat(),
                            "signature": sig,
                            "manufacturer_data": self._hex_encode_bytes(round_mfr),
                            "service_data": self._hex_encode_bytes(round_svc),
                            "protocols": list(protocols),
                        }
                    )
                s.last_signature = sig
                s._last_round_mfr = dict(sig_mfr)
                s._last_round_svc = dict(sig_svc)

        # LR-2c: OR-in a sub-round advertisement-fingerprint rotation detected on the
        # per-advert signal stream. Additive to the snapshot-based detection above
        # (_merge_svc_data/_merge_mfr_data); it can only *set* the flag, never clear it.
        if entry.get("fingerprint_rotated_in_round"):
            self._sightings[mac_up].fingerprint_changed = True

    def merge_le_results(
        self,
        devices: Dict[str, Dict],
        adapter: Optional[str] = None,
        round_num: Optional[int] = None,
    ) -> None:
        with self._lock:
            for mac, entry in devices.items():
                self._merge_entry(
                    mac, entry, "le", adapter=adapter, round_num=round_num
                )

    def merge_classic_results(
        self,
        devices: List[Dict],
        adapter: Optional[str] = None,
        round_num: Optional[int] = None,
    ) -> None:
        with self._lock:
            for entry in devices:
                mac = entry.get("address")
                if mac and mac != "??":
                    self._merge_entry(
                        mac, entry, "classic", adapter=adapter, round_num=round_num
                    )

    def filter(
        self,
        min_rssi: Optional[int] = None,
        min_sightings: int = 1,
        exclude_cached: bool = False,
    ) -> List[DeviceSighting]:
        with self._lock:
            result = []
            for s in self._sightings.values():
                if exclude_cached and s.is_cached:
                    continue
                if s.sighting_count < min_sightings:
                    continue
                if min_rssi is not None and s.rssi_avg is not None and s.rssi_avg < min_rssi:
                    continue
                result.append(s)
        result.sort(key=lambda d: d.mac)
        return result

    # -- Output formatters ---------------------------------------------------

    @staticmethod
    def format_simple(filtered: List[DeviceSighting]) -> List[str]:
        return [s.mac for s in filtered]

    @staticmethod
    def _hex_encode_bytes(data: Dict) -> Dict[str, str]:
        """Convert a dict with bytes values to hex-encoded strings for JSON."""
        return {str(k): (v.hex() if isinstance(v, bytes) else str(v)) for k, v in data.items()}

    @staticmethod
    def format_objects(
        filtered: List[DeviceSighting],
        *,
        full_payloads: bool = False,
    ) -> List[Dict[str, Any]]:
        out = []
        for s in filtered:
            obj: Dict[str, Any] = {
                "address": s.mac,
                "name": s.name,
                "device_type": s.device_type,
                "sightings": s.sighting_count,
                "rssi_avg": s.rssi_avg,
                "rssi_min": s.rssi_min,
                "rssi_max": s.rssi_max,
                "first_seen": datetime.datetime.fromtimestamp(
                    s.first_seen, tz=datetime.timezone.utc
                ).isoformat(),
                "last_seen": datetime.datetime.fromtimestamp(
                    s.last_seen, tz=datetime.timezone.utc
                ).isoformat(),
            }
            if s.uuids:
                obj["uuids"] = sorted(s.uuids)
            if s.manufacturer_data:
                obj["manufacturer_data"] = SurveyCensus._hex_encode_bytes(s.manufacturer_data)
            if s.service_data:
                obj["service_data"] = SurveyCensus._hex_encode_bytes(s.service_data)
            if s.tx_power is not None:
                obj["tx_power"] = s.tx_power
            if s.appearance is not None:
                obj["appearance"] = s.appearance
            if s.fingerprint_changed:
                obj["fingerprint_changed"] = True
            if full_payloads and s.payload_history:
                obj["payload_history"] = list(s.payload_history)
            if s.is_cached:
                obj["is_cached"] = True
            if s.seen_by:
                obj["seen_by"] = sorted(s.seen_by)
            if s.enumerated_by:
                obj["enumerated_by"] = s.enumerated_by
            if s.advmon_seen:
                obj["advmon_seen"] = True
            if s.advertising_flags:
                obj["advertising_flags"] = s.advertising_flags.hex()
            out.append(obj)
        return out

    @staticmethod
    def group_objects(obj_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Bucket ``format_objects`` output by transport.

        Split out from :meth:`format_grouped` so the segment merger can regroup
        already-formatted devices without a census to re-derive them from — see
        :mod:`bleep.modes.survey_segments`.
        """
        groups: Dict[str, List[Dict[str, Any]]] = {
            "le_devices": [],
            "classic_devices": [],
            "dual_devices": [],
        }
        for obj in obj_list:
            dtype = obj.get("device_type", "unknown")
            if dtype == "classic":
                groups["classic_devices"].append(obj)
            elif dtype == "dual":
                groups["dual_devices"].append(obj)
            else:
                groups["le_devices"].append(obj)
        return {k: {"devices": v} for k, v in groups.items()}

    @staticmethod
    def format_grouped(
        filtered: List[DeviceSighting],
        *,
        full_payloads: bool = False,
    ) -> Dict[str, Any]:
        return SurveyCensus.group_objects(
            SurveyCensus.format_objects(filtered, full_payloads=full_payloads)
        )

    def seed_from_db(self) -> int:
        """Pre-seed the census with devices from the BLEEP observation database.

        Seeded devices get ``sighting_count=0`` so the ``--min-sightings``
        filter (default 1) will exclude them unless they are re-seen during
        the live scan.  Returns the number of devices loaded.
        """
        try:
            from bleep.core import observations as _obs
        except Exception:
            return 0

        loaded = 0
        page, page_size = 0, 500
        while True:
            rows = _obs.get_devices(limit=page_size, offset=page * page_size)
            if not rows:
                break
            for row in rows:
                mac = row.get("mac")
                if not mac or mac == "??":
                    continue
                mac_up = mac.upper()
                if mac_up in self._sightings:
                    continue

                # Convert ISO timestamp to epoch float
                first_ts = 0.0
                last_ts = 0.0
                if row.get("first_seen"):
                    try:
                        first_ts = datetime.datetime.fromisoformat(
                            str(row["first_seen"])
                        ).timestamp()
                    except (ValueError, TypeError):
                        pass
                if row.get("last_seen"):
                    try:
                        last_ts = datetime.datetime.fromisoformat(
                            str(row["last_seen"])
                        ).timestamp()
                    except (ValueError, TypeError):
                        pass

                dtype = row.get("device_type") or "unknown"
                transports: set = set()
                if dtype in ("le", "dual"):
                    transports.add("le")
                if dtype in ("classic", "dual"):
                    transports.add("classic")
                if not transports:
                    transports.add(dtype)

                mfr: Dict[int, bytes] = {}
                if row.get("manufacturer_data"):
                    md = row["manufacturer_data"]
                    if isinstance(md, bytes):
                        mid = row.get("manufacturer_id")
                        if mid is not None:
                            mfr[int(mid)] = md
                    elif isinstance(md, dict):
                        for k, v in md.items():
                            mfr[int(k)] = v if isinstance(v, bytes) else bytes.fromhex(v) if isinstance(v, str) else v

                svc: Dict[str, bytes] = {}
                if row.get("service_data"):
                    sd = row["service_data"]
                    if isinstance(sd, str):
                        try:
                            sd = json.loads(sd)
                        except (json.JSONDecodeError, TypeError):
                            sd = {}
                    if isinstance(sd, dict):
                        for k, v in sd.items():
                            svc[str(k)] = v if isinstance(v, bytes) else bytes.fromhex(v) if isinstance(v, str) else v

                rssi_last = row.get("rssi_last")
                rssi_min = row.get("rssi_min")
                rssi_max = row.get("rssi_max")

                ds = DeviceSighting(
                    mac=mac_up,
                    name=row.get("name"),
                    device_type=dtype,
                    first_seen=first_ts,
                    last_seen=last_ts,
                    sighting_count=0,
                    addr_type=row.get("addr_type"),
                    device_class=row.get("device_class"),
                    manufacturer_id=row.get("manufacturer_id"),
                    uuids=set(),
                    _seen_transports=transports,
                    manufacturer_data=mfr,
                    service_data=svc,
                    tx_power=int(row["tx_power"]) if row.get("tx_power") is not None else None,
                    appearance=int(row["appearance"]) if row.get("appearance") is not None else None,
                    is_cached=True,
                    enumerated_by=row.get("enumerated_by"),
                    enumerated_at=row.get("enumerated_at"),
                )
                if rssi_last is not None:
                    ds.rssi_min = rssi_min if rssi_min is not None else rssi_last
                    ds.rssi_max = rssi_max if rssi_max is not None else rssi_last
                    ds.rssi_sum = rssi_last
                    ds.rssi_count = 1

                self._sightings[mac_up] = ds
                loaded += 1

            if len(rows) < page_size:
                break
            page += 1

        return loaded

    def summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {"le": 0, "classic": 0, "dual": 0, "unknown": 0}
        with self._lock:
            for s in self._sightings.values():
                key = s.device_type if s.device_type in counts else "unknown"
                counts[key] += 1
            counts["total"] = len(self._sightings)
        return counts

    def progress_counters(self) -> Tuple[int, int]:
        """``(total_sightings, total_rssi_reports)`` — the collector liveness pair.

        Both totals advance **only** when a device actually reports: a cached
        ``Device1`` re-read (``is_cached_reread``) bumps neither
        ``sighting_count`` nor ``rssi_count``.  So a discovery that has silently
        died freezes both of these while ``Adapter1.Discovering`` still reads
        ``true`` — which is exactly the failure that invalidated the 2026-09-06
        Run A (11 devices, stalled at 240s) and degraded Run C.  The collector
        health check watches this pair instead of the flag.

        Device *count* alone is not usable: a static environment legitimately
        plateaus, whereas these keep climbing as long as adverts arrive.
        """
        sightings = 0
        reports = 0
        with self._lock:
            for s in self._sightings.values():
                sightings += s.sighting_count
                reports += s.rssi_count
        return sightings, reports


# ---------------------------------------------------------------------------
# Scan round helpers
# ---------------------------------------------------------------------------

def _run_le_round(
    timeout: int,
    quiet: bool = True,
    *,
    variant: str = "passive",
) -> Dict[str, Dict]:
    """Execute a single LE scan round (passive or naggy)."""
    if variant == "naggy":
        from bleep.ble_ops.le.scan import naggy_scan
        result = naggy_scan(device=None, timeout=timeout, transport="le")
    else:
        from bleep.ble_ops.le.scan import passive_scan
        result = passive_scan(device=None, timeout=timeout, transport="le", quiet=quiet)
    return result if isinstance(result, dict) else {}


def _run_classic_round(
    timeout: int, adapter_name: str = "hci0", persist_db: bool = True,
) -> List[Dict]:
    """Execute a single BR/EDR inquiry round.

    Replicates the adapter inquiry pattern from ``cli.py`` classic-scan handler
    without duplicating BlueZ interaction code.
    """
    try:
        from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
    except Exception:
        print_and_log(
            "[survey] Classic scan unavailable (missing D-Bus bindings)", LOG__DEBUG
        )
        return []

    try:
        adapter = _Adapter(adapter_name)
        if not adapter.is_ready():
            print_and_log("[survey] Adapter not ready for Classic scan", LOG__DEBUG)
            # Surface not-ready to the caller (was a silent ``[]``) so the survey
            # loop can distinguish "adapter down" from "ready but zero devices"
            # and pace/recover accordingly instead of busy-looping.
            raise NotReadyError()

        adapter.set_discovery_filter({"Transport": "bredr"})
        if not adapter.run_scan__timed(duration=timeout):
            print_and_log("[survey] Classic timed scan returned no results", LOG__DEBUG)
            return []
        # Keep devices the BR/EDR inquiry can legitimately account for: pure
        # Classic (mapped to "br/edr") *and* dual-mode devices (BR/EDR + LE).
        # ``le``/``unknown`` are excluded so LE-only devices cached from prior
        # rounds are not miscounted as Classic sightings.
        devices = [
            d
            for d in adapter.get_discovered_devices()
            if d.get("type", "").lower() in ("br/edr", "dual")
        ]

        if persist_db:
            try:
                from bleep.core import observations as _obs
                for d in devices:
                    addr = d.get("address")
                    if not addr or addr == "??":
                        continue
                    info: Dict[str, Any] = {
                        "name": d.get("name") or d.get("alias"),
                        "rssi_last": d.get("rssi"),
                        "device_class": d.get("device_class"),
                        "addr_type": d.get("address_type"),
                        # Persist the actual transport: "br/edr"->classic,
                        # "dual"->dual.  Hardcoding "classic" would downgrade a
                        # dual device (upsert_device honours an explicit type and
                        # bypasses its own "preserve dual" merge).
                        "device_type": _CLASSIFIER_TYPE_MAP.get(
                            d.get("type", "").lower(), "classic"
                        ),
                    }
                    if d.get("tx_power") is not None:
                        info["tx_power"] = int(d["tx_power"])
                    if d.get("appearance") is not None:
                        info["appearance"] = int(d["appearance"])
                    if d.get("modalias"):
                        info["modalias"] = str(d["modalias"])
                    if d.get("icon"):
                        info["icon"] = str(d["icon"])
                    if d.get("uuids"):
                        info["uuids"] = d["uuids"]
                    if d.get("paired") is not None:
                        info["paired"] = bool(d["paired"])
                    if d.get("trusted") is not None:
                        info["trusted"] = bool(d["trusted"])
                    if d.get("bonded") is not None:
                        info["bonded"] = bool(d["bonded"])
                    _obs.upsert_device(addr, **info)
            except Exception as db_exc:
                print_and_log(f"[survey] Classic DB persistence warning: {db_exc}", LOG__DEBUG)

        return devices
    except NotReadyError:
        # Propagate the not-ready signal; the broad handler below must not
        # re-swallow it back into an empty result.
        raise
    except Exception as exc:
        print_and_log(f"[survey] Classic scan error: {exc}", LOG__DEBUG)
        return []


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    from bleep.cli.parsers.survey import _add_survey_arguments

    p = argparse.ArgumentParser(
        prog="bleep-survey",
        description="Long-duration passive survey for Bluetooth device discovery",
    )
    _add_survey_arguments(p)
    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _format_survey_output(census: "SurveyCensus", args: argparse.Namespace):
    """Filter + format the census per the caller's args.

    Shared by the final write and the SR-G1 periodic checkpoint so both emit an
    identical structure. Returns ``(formatted, filtered)``.
    """
    filtered = census.filter(
        min_rssi=args.min_rssi,
        min_sightings=args.min_sightings,
        exclude_cached=args.exclude_cached,
    )
    full_payloads = bool(getattr(args, "full_payloads", False))
    if args.out_format == "simple":
        formatted = census.format_simple(filtered)
    elif args.out_format == "grouped":
        formatted = census.format_grouped(filtered, full_payloads=full_payloads)
    else:
        formatted = census.format_objects(filtered, full_payloads=full_payloads)
    return formatted, filtered


def _write_survey_checkpoint(census: "SurveyCensus", args: argparse.Namespace,
                             output: OutputContext) -> None:
    """SR-G1: atomically write the current census to ``<output>.partial``.

    No-op without ``-o/--output``. A late crash (OOM/power/kill -9) otherwise
    loses the whole in-memory census/RSSI aggregation — DB rows survive but the
    formatted census does not. Failures are logged and swallowed so a bad disk
    write never aborts an in-progress survey.
    """
    if not args.output:
        return
    try:
        formatted, _ = _format_survey_output(census, args)
        partial = f"{args.output}.partial"
        tmp = f"{partial}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(formatted, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, partial)  # atomic on POSIX
        output.emit_progress(f"[survey] Checkpoint written to {partial}")
    except Exception as exc:  # pragma: no cover - defensive
        print_and_log(f"[survey] Checkpoint warning: {exc}", LOG__DEBUG)


def _then_aoi_argv(
    output_file: str,
    output: "OutputContext",
    adapter: Optional[str] = None,
) -> List[str]:
    """Build the ``bleep aoi scan`` argv used by ``--then-aoi``."""
    aoi_cmd = [sys.executable, "-m", "bleep"]
    if output.mode == "json":
        aoi_cmd.append("--json")
    elif output.mode == "quiet":
        aoi_cmd.append("--quiet")
    aoi_cmd.extend(["aoi", "scan", output_file])
    if adapter:
        aoi_cmd.extend(["--adapter", adapter])
    return aoi_cmd


def run(args: argparse.Namespace, output: OutputContext | None = None) -> int:
    """Execute survey with parsed args and optional OutputContext.

    This is the canonical entry point for Phase 3+ callers that pass a
    pre-parsed ``argparse.Namespace`` and an ``OutputContext``.  The older
    ``main(argv)`` wrapper remains for backward compatibility.
    """
    from bleep.core.output import OutputContext
    from bleep.core.log import set_output_mode

    if output is None:
        output = OutputContext()

    set_output_mode(output.mode)

    # A run longer than one segment is executed as consecutive fresh processes
    # and merged: a single process stops collecting after ~80 rounds (~42 min).
    # Decided before any adapter or D-Bus setup so the parent stays a thin
    # orchestrator that never opens a controller of its own.
    from bleep.modes.survey_segments import plan_segments, run_segmented

    if (getattr(args, "segment_time", None) or 0) < 0:
        print_and_log(
            "[-] --segment-time must be >= 0 (0 = never split)", LOG__USER
        )
        return 2

    segment_plan = plan_segments(
        getattr(args, "duration", None), getattr(args, "segment_time", None)
    )
    if segment_plan is not None:
        return run_segmented(args, output, segment_plan)

    global _stop, _bluez_warning
    _stop = False
    _bluez_warning = None
    prev_sigint = signal.getsignal(signal.SIGINT)
    prev_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, _sighandler)
    signal.signal(signal.SIGTERM, _sighandler)

    persist_db = not args.no_db
    monitoring = _start_health_monitor()

    census = SurveyCensus()

    if args.resume_db:
        seeded = census.seed_from_db()
        output.emit_progress(f"[survey] Resumed {seeded} device(s) from database")

    from bleep.modes.survey_multi import parse_collectors, run_multi_collector
    from bleep.modes.survey_enum import parse_enumerator
    from bleep.core.preflight import require_adapter

    duration = args.duration
    round_time = args.round_time
    transport = args.transport
    collectors = parse_collectors(getattr(args, "collector", None))
    try:
        enumerator = parse_enumerator(getattr(args, "enumerator", None))
    except ValueError as exc:
        signal.signal(signal.SIGINT, prev_sigint)
        signal.signal(signal.SIGTERM, prev_sigterm)
        if monitoring:
            _stop_health_monitor()
        output.emit_progress(f"[survey] {exc}")
        return 1

    if enumerator and not collectors:
        collectors = [(args.adapter, transport)]
    listen_monitor = bool(getattr(args, "listen_monitor", False))
    raw_listen_pats = getattr(args, "listen_patterns", None) or []
    raw_listen_mfr = getattr(args, "listen_manufacturers", None) or []
    raw_listen_str = getattr(args, "listen_mfr_strings", None) or []
    if (raw_listen_pats or raw_listen_mfr or raw_listen_str) and not listen_monitor:
        signal.signal(signal.SIGINT, prev_sigint)
        signal.signal(signal.SIGTERM, prev_sigterm)
        if monitoring:
            _stop_health_monitor()
        output.emit_progress(
            "[survey] --listen-pattern / --listen-manufacturer / "
            "--listen-mfr-string require --listen-monitor"
        )
        return 1
    if raw_listen_pats or raw_listen_mfr or raw_listen_str:
        from bleep.dbuslayer.adv_patterns import PatternError, parse_listen_extras

        try:
            parse_listen_extras(
                patterns=raw_listen_pats,
                manufacturers=raw_listen_mfr,
                mfr_strings=raw_listen_str,
            )
        except PatternError as exc:
            signal.signal(signal.SIGINT, prev_sigint)
            signal.signal(signal.SIGTERM, prev_sigterm)
            if monitoring:
                _stop_health_monitor()
            output.emit_progress(f"[survey] listen extras: {exc}")
            return 1
    if listen_monitor:
        listen_targets = collectors if collectors else [(args.adapter, transport)]
        if all(t == "bredr" for _name, t in listen_targets):
            signal.signal(signal.SIGINT, prev_sigint)
            signal.signal(signal.SIGTERM, prev_sigterm)
            if monitoring:
                _stop_health_monitor()
            output.emit_progress(
                "[survey] --listen-monitor is LE-only; use --transport le|both "
                "or a --collector with le|both"
            )
            return 1
    if listen_monitor and not collectors:
        collectors = [(args.adapter, transport)]
    if enumerator:
        enum_name, _enum_mode = enumerator
        collector_names = {name for name, _t in collectors}
        if enum_name in collector_names:
            signal.signal(signal.SIGINT, prev_sigint)
            signal.signal(signal.SIGTERM, prev_sigterm)
            if monitoring:
                _stop_health_monitor()
            output.emit_progress(
                f"[survey] enumerator {enum_name} must be distinct from collectors "
                f"({', '.join(sorted(collector_names))})"
            )
            return 1
        if not require_adapter(enum_name):
            signal.signal(signal.SIGINT, prev_sigint)
            signal.signal(signal.SIGTERM, prev_sigterm)
            if monitoring:
                _stop_health_monitor()
            return 1
        for name, _t in collectors:
            if not require_adapter(name):
                signal.signal(signal.SIGINT, prev_sigint)
                signal.signal(signal.SIGTERM, prev_sigterm)
                if monitoring:
                    _stop_health_monitor()
                return 1

    adaptive = args.adaptive
    adaptive_min = args.adaptive_min
    adaptive_max = args.adaptive_max
    dynamic_rt = round_time

    if collectors:
        mode_label = (
            f"duration={duration}s, round_time={round_time}s, "
            f"antennas={len(collectors)}"
        )
    else:
        mode_label = (
            f"duration={duration}s, round_time={round_time}s, transport={transport}"
        )
        if adaptive:
            mode_label += f", adaptive=[{adaptive_min}s\u2013{adaptive_max}s]"
    # --no-mainloop: refuse the combinations it would silently break, then warn
    # about the rest.  Must run before run_multi_collector, which acquires the
    # loop.  See docs/todo_tracker.md B.19-B.23 (accepted policies).
    stall_rounds = getattr(args, "stall_rounds", None)
    if stall_rounds is not None and stall_rounds < 0:
        print_and_log(
            "[-] --stall-rounds must be >= 0 (0 = never re-arm)", LOG__USER
        )
        return 2

    # Bound live enumeration device objects (default 10, see device_pool).
    from bleep.dbuslayer.device_pool import apply_capacity

    pool_ok, pool_msg = apply_capacity(getattr(args, "max_enum_devices", None))
    if pool_msg:
        print_and_log(pool_msg, LOG__USER)
    if not pool_ok:
        return 2

    if getattr(args, "no_mainloop", False):
        from bleep.dbuslayer.loop_service import (
            suppress_mainloop,
            warn_mainloop_suppressed,
        )

        conflicts = []
        if getattr(args, "listen_monitor", False):
            conflicts.append(
                "--listen-monitor (AdvMonitor would register but never receive "
                "Activate/DeviceFound/Release)"
            )
        if getattr(args, "variant", None) == "pair" or getattr(
            args, "enumerator_mode", None
        ) == "pair":
            conflicts.append(
                "pair mode (the pairing agent could not answer RequestPasskey/"
                "RequestConfirmation)"
            )
        if conflicts:
            print_and_log(
                "[-] --no-mainloop cannot be combined with:", LOG__USER
            )
            for conflict in conflicts:
                print_and_log(f"[-]   - {conflict}", LOG__USER)
            print_and_log(
                "[-] Drop --no-mainloop, or drop the conflicting option.",
                LOG__USER,
            )
            return 2

        suppress_mainloop(True)
        warn_mainloop_suppressed()

    output.emit_progress(f"[survey] Starting: {mode_label}")

    round_num = 0
    elapsed = 0.0
    prev_count = census.device_count
    t_start = time.monotonic()

    # Multi-antenna path (D2): concurrent per-adapter collection on the shared
    # main-loop.  Fills the same census, then falls through to the shared
    # persist/format/write tail below (the single-adapter loop is skipped).
    if collectors:
        round_num, elapsed = run_multi_collector(
            census, collectors, args, output, persist_db, enumerator=enumerator
        )

    # SR-G1: periodic census checkpointing (0 = disabled).
    checkpoint_interval = getattr(args, "checkpoint_interval", 0) or 0
    last_checkpoint = t_start

    # Adapter-drop resilience: a round that cannot scan because the controller
    # went not-ready must neither crash the run nor busy-loop.  Track skipped
    # rounds for the final summary and bound in-run recovery attempts so a hard
    # rfkill/hardware fault cannot loop forever.
    auto_recover = getattr(args, "auto_recover", False)
    skipped_rounds = 0
    recovery_attempts = 0
    _MAX_RECOVERY_ATTEMPTS = 3

    while elapsed < duration and not _stop and not collectors:
        round_num += 1

        if _bluez_warning:
            output.emit_progress(f"[survey] WARNING: {_bluez_warning}")
            _bluez_warning = None

        productive = False
        round_error: Optional[BLEEPError] = None
        scan_quiet = True

        if transport in ("le", "both"):
            remaining = duration - elapsed
            rt = min(dynamic_rt, max(1, int(remaining)))
            try:
                census.merge_le_results(
                    _run_le_round(
                        rt,
                        quiet=scan_quiet,
                        variant=getattr(args, "variant", "passive") or "passive",
                    ),
                    round_num=round_num,
                )
                productive = True
            except BLEEPError as exc:
                round_error = exc
            elapsed = time.monotonic() - t_start
            if _stop:
                break

        if transport in ("bredr", "both") and elapsed < duration and not _stop:
            remaining = duration - elapsed
            rt = min(dynamic_rt, max(1, int(remaining)))
            try:
                census.merge_classic_results(
                    _run_classic_round(
                        rt, adapter_name=args.adapter, persist_db=persist_db,
                    ),
                    round_num=round_num,
                )
                productive = True
            except BLEEPError as exc:
                round_error = exc
            elapsed = time.monotonic() - t_start

        # A non-productive round means every attempted transport raised (the
        # adapter is not ready).  Surface it, optionally attempt recovery, then
        # pace the loop so we neither spin (100% CPU) nor spam warnings.
        if not productive and not _stop:
            skipped_rounds += 1
            detail = f" ({round_error})" if round_error is not None else ""
            output.emit_progress(
                f"[survey] WARNING: adapter not ready — skipped round "
                f"{round_num}{detail}"
            )

            if auto_recover and recovery_attempts < _MAX_RECOVERY_ATTEMPTS:
                recovery_attempts += 1
                output.emit_progress(
                    f"[survey] Attempting adapter recovery "
                    f"({recovery_attempts}/{_MAX_RECOVERY_ATTEMPTS})\u2026"
                )
                if _attempt_adapter_recovery(args.adapter):
                    output.emit_progress("[survey] Adapter recovered — resuming")
                    recovery_attempts = 0
                    elapsed = time.monotonic() - t_start
                    continue

            remaining = duration - elapsed
            if remaining > 0:
                _interruptible_sleep(max(1, min(dynamic_rt, int(remaining))))
                elapsed = time.monotonic() - t_start
        elif productive:
            recovery_attempts = 0

        if adaptive:
            new_devices = census.device_count - prev_count
            prev_count = census.device_count
            if new_devices == 0:
                dynamic_rt = max(adaptive_min, dynamic_rt // 2)
            elif new_devices >= 3:
                dynamic_rt = min(adaptive_max, dynamic_rt + 10)

        if args.live:
            s = census.summary()
            if not productive:
                health = " | BlueZ: adapter not ready"
            elif monitoring:
                health = " | BlueZ: OK"
            else:
                health = ""
            rt_label = f" | rt={dynamic_rt}s" if adaptive else ""
            output.emit_progress(
                f"[survey] round {round_num} | {s['total']} devices "
                f"({s['le']} LE, {s['classic']} Classic, {s['dual']} Dual) | "
                f"elapsed {int(elapsed)}s/{duration}s{rt_label}{health}"
            )

        if checkpoint_interval and args.output:
            now = time.monotonic()
            if now - last_checkpoint >= checkpoint_interval:
                _write_survey_checkpoint(census, args, output)
                last_checkpoint = now

    # Restore original signal handlers and stop health monitoring
    signal.signal(signal.SIGINT, prev_sigint)
    signal.signal(signal.SIGTERM, prev_sigterm)
    if monitoring:
        _stop_health_monitor()

    # P2-B9: Persist survey-specific metadata to DB
    if persist_db:
        try:
            from bleep.core import observations as _obs
            for sighting in census._sightings.values():
                extras: Dict[str, Any] = {}
                if sighting.sighting_count > 0:
                    extras["sighting_count"] = sighting.sighting_count
                if sighting.fingerprint_changed:
                    extras["fingerprint_changed"] = True
                if sighting.uuids:
                    extras["uuids"] = sorted(sighting.uuids)
                if sighting.seen_by:
                    extras["seen_by"] = sorted(sighting.seen_by)
                if extras:
                    _obs.upsert_device(sighting.mac, **extras)
        except Exception as db_exc:
            print_and_log(f"[survey] DB metadata persistence warning: {db_exc}", LOG__DEBUG)

    # Filter + format (shared with the SR-G1 checkpoint path)
    formatted, filtered = _format_survey_output(census, args)

    json_str = json.dumps(formatted, indent=2, ensure_ascii=False)

    # Write output
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str + "\n")
        output.emit_progress(f"[survey] Output written to {args.output}")
        # Collection health goes to a sidecar, not into the census: the objects
        # /grouped/simple payloads are top-level *lists* consumed by
        # ``bleep aoi scan``, so adding a metadata wrapper would be a breaking
        # schema change. Written whenever collectors ran, so its absence is not
        # ambiguous. See docs/survey_mode.md.
        health = getattr(census, "collection_health", None)
        if health:
            try:
                with open(f"{args.output}.health.json", "w", encoding="utf-8") as f:
                    f.write(json.dumps(health, indent=2) + "\n")
                if health.get("degraded"):
                    output.emit_progress(
                        f"[survey] DEGRADED COVERAGE recorded in "
                        f"{args.output}.health.json"
                    )
            except Exception as exc:  # pragma: no cover - defensive
                print_and_log(f"[survey] health sidecar failed: {exc}", LOG__DEBUG)
        # SR-G1: the complete census is now on disk; drop any stale checkpoint.
        try:
            partial = f"{args.output}.partial"
            if os.path.exists(partial):
                os.remove(partial)
        except OSError:
            pass
    elif output.is_json:
        output.emit_result(formatted)
    else:
        print(json_str)

    # Final summary
    s = census.summary()
    excluded = census.device_count - len(filtered)
    output.emit_progress(
        f"[survey] Complete: {s['total']} unique devices in {round_num} round(s) "
        f"over {int(elapsed)}s"
    )
    filters_desc = []
    if args.exclude_cached:
        filters_desc.append("exclude_cached")
    if args.min_rssi is not None:
        filters_desc.append(f"min_rssi={args.min_rssi}")
    if args.min_sightings > 1:
        filters_desc.append(f"min_sightings={args.min_sightings}")
    if excluded and not filters_desc:
        filters_desc.append(f"min_sightings={args.min_sightings}")
    filter_note = f" (filtered out {excluded}: {', '.join(filters_desc)})" if excluded else ""
    output.emit_progress(f"[survey] Output: {len(filtered)} devices written{filter_note}")

    if skipped_rounds:
        output.emit_progress(
            f"[survey] WARNING: {skipped_rounds}/{round_num} round(s) skipped — "
            f"the Bluetooth adapter was not ready. Output reflects only data "
            f"collected while the adapter was up."
        )
        output.emit_progress(
            "[survey]   Fix: keep the controller powered — 'rfkill unblock "
            "bluetooth', set 'AutoEnable=true' in /etc/bluetooth/main.conf, "
            "check 'dmesg' for controller resets, or re-run with --auto-recover."
        )

    if args.then_aoi:
        if not args.output:
            output.emit_progress("[survey] --then-aoi requires -o/--output to specify a file")
            return 1
        if not filtered:
            output.emit_progress("[survey] --then-aoi: no devices to scan, skipping AoI")
            return 0
        aoi_adapter = enumerator[0] if enumerator else getattr(args, "adapter", None)
        aoi_cmd = _then_aoi_argv(args.output, output, adapter=aoi_adapter)
        output.emit_progress(f"[survey] Launching: {' '.join(aoi_cmd)}")
        import subprocess as _sp
        result = _sp.run(
            aoi_cmd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return result.returncode

    return 0


def main(argv: list[str] | None = None) -> int:
    """Backward-compatible entry point that parses argv and delegates to run()."""
    args = _build_parser().parse_args(argv)
    return run(args)
