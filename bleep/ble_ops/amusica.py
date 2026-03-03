"""
Amusica – automated Bluetooth audio target discovery and manipulation.

Orchestrates UUID-filtered scanning, JustWorks connection attempts, audio
reconnaissance, and target assessment.  Higher-level CLI entry points live
in ``bleep.modes.amusica``; this module exposes the composable primitives.

"Prevent people from enjoying music; thereby preventing them from feeling
patriotic fervor for their anthems" – Century Rain, Alastair Reynolds
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from bleep.bt_ref.constants import (
    AUDIO_SERVICE_UUIDS,
    AUDIO_PROFILE_NAMES,
)
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER

__all__ = [
    "scan_audio_targets",
    "attempt_justworks_connect",
    "assess_targets",
]


# ---------------------------------------------------------------------------
# Scan helpers
# ---------------------------------------------------------------------------

def _device_has_audio_uuids(device_info: Dict[str, Any]) -> bool:
    """Return True if *device_info* advertises at least one audio service UUID."""
    uuids = device_info.get("uuids") or device_info.get("UUIDs") or []
    for u in uuids:
        if str(u).lower() in AUDIO_SERVICE_UUIDS:
            return True
    return False


def _audio_uuids_for_device(device_info: Dict[str, Any]) -> List[str]:
    """Return the subset of advertised UUIDs that match known audio services."""
    uuids = device_info.get("uuids") or device_info.get("UUIDs") or []
    return [str(u) for u in uuids if str(u).lower() in AUDIO_SERVICE_UUIDS]


def scan_audio_targets(
    timeout: int = 15,
    adapter_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Scan for Bluetooth devices that advertise audio service UUIDs.

    Uses the existing BLEEP scan infrastructure with a post-filter for
    audio-related service class UUIDs (A2DP, HFP, HSP, AVRCP).

    Parameters
    ----------
    timeout : int
        Scan duration in seconds.
    adapter_name : Optional[str]
        HCI adapter name override (e.g. ``"hci1"``).

    Returns
    -------
    List[Dict[str, Any]]
        Each entry mirrors the adapter ``get_discovered_devices()`` dict with
        an added ``audio_uuids`` key listing the matched UUIDs and their
        human-readable names.
    """
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    adapter = _Adapter(adapter_name) if adapter_name else _Adapter()
    if not adapter.is_ready():
        print_and_log("[!] Adapter not ready", LOG__USER)
        return []

    print_and_log(
        f"[*] Amusica: scanning for audio-capable devices ({timeout}s)…",
        LOG__USER,
    )

    try:
        adapter.set_discovery_filter({"Transport": "auto"})
    except Exception:
        pass

    adapter.run_scan__timed(duration=timeout)
    devices = adapter.get_discovered_devices()

    targets: List[Dict[str, Any]] = []
    for dev in devices:
        if not _device_has_audio_uuids(dev):
            continue
        matched = _audio_uuids_for_device(dev)
        dev["audio_uuids"] = [
            {"uuid": u, "name": AUDIO_PROFILE_NAMES.get(u.lower(), u)}
            for u in matched
        ]
        targets.append(dev)

    print_and_log(
        f"[+] Amusica: {len(targets)} audio-capable device(s) found "
        f"(of {len(devices)} total)",
        LOG__USER,
    )
    return targets


# ---------------------------------------------------------------------------
# JustWorks connection
# ---------------------------------------------------------------------------

def attempt_justworks_connect(
    mac_address: str,
    *,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """Attempt a connect-only (no pair) connection to the target.

    A successful connection with no authentication prompt indicates the
    device accepts JustWorks / unauthenticated connections.

    Parameters
    ----------
    mac_address : str
        Target device MAC.
    timeout : float
        Seconds to wait for the connection attempt.

    Returns
    -------
    Dict[str, Any]
        ``{"connected": bool, "error": Optional[str], "auth_required": bool}``
    """
    result: Dict[str, Any] = {
        "connected": False,
        "error": None,
        "auth_required": False,
    }

    try:
        import dbus
        from bleep.dbuslayer.device_classic import (
            system_dbus__bluez_device__classic as _ClassicDevice,
        )

        device = _ClassicDevice(mac_address)

        if device.is_connected():
            result["connected"] = True
            return result

        connected = device.connect(retry=1, wait_timeout=timeout)
        result["connected"] = connected

    except Exception as exc:
        err_str = str(exc).lower()
        if "authenticationfailed" in err_str or "authenticationrejected" in err_str:
            result["auth_required"] = True
            result["error"] = "authentication_required"
        elif "rejected" in err_str:
            result["auth_required"] = True
            result["error"] = "connection_rejected"
        else:
            result["error"] = str(exc)

    return result


# ---------------------------------------------------------------------------
# Full assessment pipeline
# ---------------------------------------------------------------------------

def assess_targets(
    targets: List[Dict[str, Any]],
    *,
    do_recon: bool = True,
    recon_test_file: Optional[str] = None,
    record_dir: str = "/tmp",
    record_duration: int = 8,
) -> List[Dict[str, Any]]:
    """Run JustWorks connection + optional audio recon on each target.

    Parameters
    ----------
    targets : List[Dict[str, Any]]
        Device dicts as returned by :func:`scan_audio_targets`.
    do_recon : bool
        Run ``audio_recon`` on successfully connected targets.
    recon_test_file : Optional[str]
        Path to an audio file for playback testing during recon.
    record_dir : str
        Directory for recordings (default ``/tmp``).
    record_duration : int
        Duration per recording in seconds.

    Returns
    -------
    List[Dict[str, Any]]
        Each target dict augmented with ``connection`` and optionally
        ``recon`` result dicts.
    """
    for target in targets:
        mac = target.get("address", "")
        name = target.get("name") or target.get("alias") or mac
        print_and_log(f"\n[*] Amusica: assessing {name} ({mac})", LOG__USER)

        conn_result = attempt_justworks_connect(mac)
        target["connection"] = conn_result

        if conn_result["auth_required"]:
            print_and_log(
                f"  [!] {mac}: authentication required – skipping",
                LOG__USER,
            )
            continue

        if not conn_result["connected"]:
            print_and_log(
                f"  [-] {mac}: connection failed – {conn_result.get('error', 'unknown')}",
                LOG__USER,
            )
            continue

        print_and_log(f"  [+] {mac}: JustWorks connection successful", LOG__USER)

        if do_recon:
            from bleep.ble_ops.audio_recon import run_audio_recon
            recon = run_audio_recon(
                mac_filter=mac,
                test_file=recon_test_file,
                do_play=recon_test_file is not None,
                do_record=True,
                record_duration_sec=record_duration,
                record_dir=record_dir,
            )
            target["recon"] = recon

            ifaces = (
                sum(len(c.get("profiles", [])) for c in recon.get("cards", []))
                + len(recon.get("bluealsa_pcms", []))
            )
            recs_with_audio = sum(
                1 for r in recon.get("recordings", []) if r.get("has_audio")
            )
            print_and_log(
                f"  [+] Recon: {ifaces} interface(s), "
                f"{len(recon.get('recordings', []))} recording(s), "
                f"{recs_with_audio} with audio content",
                LOG__USER,
            )

    return targets


def summarise_assessment(targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Produce a summary report from assessed targets.

    Parameters
    ----------
    targets : List[Dict[str, Any]]
        Output of :func:`assess_targets`.

    Returns
    -------
    Dict[str, Any]
        Summary with ``total_scanned``, ``justworks_accessible``,
        ``auth_required``, ``failed``, and ``vulnerable`` (list of MACs
        that connected and have audio interfaces).
    """
    summary: Dict[str, Any] = {
        "total_scanned": len(targets),
        "justworks_accessible": 0,
        "auth_required": 0,
        "failed": 0,
        "vulnerable": [],
    }

    for t in targets:
        conn = t.get("connection", {})
        if conn.get("auth_required"):
            summary["auth_required"] += 1
        elif conn.get("connected"):
            summary["justworks_accessible"] += 1
            recon = t.get("recon", {})
            has_interfaces = bool(
                recon.get("cards") or recon.get("bluealsa_pcms")
            )
            if has_interfaces:
                summary["vulnerable"].append({
                    "address": t.get("address"),
                    "name": t.get("name") or t.get("alias"),
                    "audio_uuids": t.get("audio_uuids", []),
                    "recordings_with_audio": sum(
                        1 for r in recon.get("recordings", [])
                        if r.get("has_audio")
                    ),
                })
        else:
            summary["failed"] += 1

    return summary
