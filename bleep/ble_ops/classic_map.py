"""bleep.ble_ops.classic_map – Message Access Profile operations.

Thin wrapper around ``bleep.dbuslayer.obex_map.MapSession`` that adds
BLEEP-standard logging, optional observation-database storage, and service
detection from SDP records (UUIDs ``0x1132``, ``0x1134``).

Prerequisites: same as ``obex_map`` (``bluetooth-obexd``, paired/trusted).

Limitations / future expansion:
  - No multi-instance MAS support (only the default instance is used).
  - ``push_message`` targets ``telecom/msg/outbox`` by default.
  - BIP-related features (image thumbnails in messages) are not handled.
  - SMS-only; MMS attachment download is not implemented beyond what
    ``Message1.Get`` with ``attachment=True`` provides.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None

from bleep.dbuslayer.obex_map import MapSession

from bleep.bt_ref.constants import (
    MAP_MSE_UUID_SHORT,
    MAP_UUID_SHORT,
    MAP_MSE_UUID as MAP_MSE_UUID_FULL,
    MAP_UUID as MAP_UUID_FULL,
)

# MAP-MSE service class UUID short forms for SDP filtering
_MAP_MSE_SHORTS = {"0x1132", "1132"}
_MAP_SHORTS = {"0x1132", "0x1134", "1132", "1134"}


def detect_map_service(service_map: Optional[Dict[str, int]]) -> bool:
    """Return True if the service map contains a MAP entry."""
    if not service_map:
        return False
    for key in service_map:
        low = key.lower()
        if "1132" in low or "1134" in low or "message" in low or "map" in low:
            return True
    return False


def list_mas_instances(mac_address: str) -> List[Dict[str, Any]]:
    """Discover MAP-MSE instances via SDP and return their RFCOMM channels.

    Each entry contains ``name``, ``channel``, ``uuid``, and the raw SDP
    record fields.  Use the ``channel`` value as the ``instance`` parameter
    to other MAP operations to target a specific MAS.
    """
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Discovering MAS instances on {mac_address}", LOG__GENERAL)
    try:
        from bleep.ble_ops.classic_sdp import discover_services_sdp
        records = discover_services_sdp(mac_address)
    except Exception as exc:
        print_and_log(f"[MAP] SDP discovery failed: {exc}", LOG__DEBUG)
        return []

    instances: List[Dict[str, Any]] = []
    for rec in records:
        uuid_str = (rec.get("uuid") or "").lower()
        name_str = (rec.get("name") or "").lower()
        is_map = any(s in uuid_str for s in _MAP_SHORTS) or "message" in name_str
        if is_map and rec.get("channel") is not None:
            instances.append({
                "name": rec.get("name", "MAP"),
                "channel": rec["channel"],
                "uuid": rec.get("uuid"),
            })

    print_and_log(f"[MAP] Found {len(instances)} MAS instance(s)", LOG__DEBUG)
    return instances


def _session(mac: str, timeout: int, instance: Optional[int]) -> MapSession:
    return MapSession(mac, timeout=timeout, instance=instance)


def list_folders(
    mac_address: str, *, timeout: int = 30, instance: Optional[int] = None,
) -> List[Dict[str, Any]]:
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Listing folders on {mac_address}", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        return sess.list_folders()


def list_messages(
    mac_address: str,
    folder: str = "",
    *,
    filters: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    instance: Optional[int] = None,
) -> List[Dict[str, Any]]:
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Listing messages in '{folder}' on {mac_address}", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        if folder:
            sess.set_folder(folder)
        return sess.list_messages(folder, filters=filters)


def get_message(
    mac_address: str,
    handle: str,
    dest: str,
    *,
    timeout: int = 60,
    instance: Optional[int] = None,
) -> Path:
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Downloading message {handle} from {mac_address}", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        result = sess.get_message(handle, dest)

    if _obs:
        try:
            _obs.upsert_map_access(mac_address, handle, "get")
        except Exception:
            pass

    return result


def push_message(
    mac_address: str,
    filepath: str,
    folder: str = "telecom/msg/outbox",
    *,
    timeout: int = 60,
    instance: Optional[int] = None,
) -> None:
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Pushing message to {mac_address} ({folder})", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        sess.push_message(filepath, folder)
    print_and_log("[MAP] Message pushed successfully", LOG__GENERAL)

    if _obs:
        try:
            _obs.upsert_map_access(mac_address, filepath, "push")
        except Exception:
            pass


def update_inbox(
    mac_address: str, *, timeout: int = 30, instance: Optional[int] = None,
) -> None:
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] UpdateInbox on {mac_address}", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        sess.update_inbox()
    print_and_log("[MAP] Inbox update requested", LOG__GENERAL)


# -- metadata queries --------------------------------------------------------


def get_supported_types(
    mac_address: str, *, timeout: int = 30, instance: Optional[int] = None,
) -> List[str]:
    """Return the list of message types supported by the remote MAS."""
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Querying SupportedTypes on {mac_address}", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        return sess.get_supported_types()


def list_filter_fields(
    mac_address: str, *, timeout: int = 30, instance: Optional[int] = None,
) -> List[str]:
    """Return available field names for ``ListMessages`` filtering."""
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Querying ListFilterFields on {mac_address}", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        return sess.list_filter_fields()


# -- MNS notification monitoring --------------------------------------------

_active_monitors: Dict[str, MapSession] = {}


def start_message_monitor(
    mac_address: str,
    callback: Callable[[str, Dict[str, Any]], None],
    *,
    timeout: int = 300,
    instance: Optional[int] = None,
) -> None:
    """Start monitoring MAP message notifications for *mac_address*.

    *callback(object_path, changed_props)* is called for every
    ``PropertiesChanged`` signal on ``Message1`` objects within the session.

    The session stays open until :func:`stop_message_monitor` is called.
    """
    mac_address = mac_address.strip().upper()
    if mac_address in _active_monitors:
        raise RuntimeError(f"Monitor already active for {mac_address}")

    print_and_log(f"[MAP] Starting MNS monitor for {mac_address}", LOG__GENERAL)
    sess = MapSession(mac_address, timeout=timeout, instance=instance)
    try:
        sess.start_notification_watch(callback)
    except Exception:
        sess.close()
        raise
    _active_monitors[mac_address] = sess
    print_and_log(f"[MAP] MNS monitor active for {mac_address}", LOG__GENERAL)


def stop_message_monitor(mac_address: str) -> None:
    """Stop the MAP message notification monitor for *mac_address*."""
    mac_address = mac_address.strip().upper()
    sess = _active_monitors.pop(mac_address, None)
    if sess is None:
        print_and_log(f"[MAP] No active monitor for {mac_address}", LOG__DEBUG)
        return
    sess.close()
    print_and_log(f"[MAP] MNS monitor stopped for {mac_address}", LOG__GENERAL)
