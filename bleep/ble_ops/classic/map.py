"""bleep.ble_ops.classic_map – Message Access Profile operations.

Thin wrapper around ``bleep.dbuslayer.obex_map.MapSession`` that adds
BLEEP-standard logging, optional observation-database storage, and service
detection from SDP records (UUIDs ``0x1132``, ``0x1134``).

Prerequisites: same as ``obex_map`` (``bluetooth-obexd``, paired/trusted).

Limitations / future expansion:
  - Multi-instance MAS is supported via ``list_mas_instances()`` and the
    ``instance`` parameter on all session-based operations.
  - ``push_message`` targets ``telecom/msg/outbox`` by default.
  - BIP-related features (image thumbnails in messages) are not handled.
  - SMS-only; MMS attachment download is not implemented beyond what
    ``Message1.Get`` with ``attachment=True`` provides.
"""

from __future__ import annotations

import os as _os
import re as _re
import tempfile as _tempfile
import time as _time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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
    """Return True if the service map contains a MAP entry.

    Keys produced by ``build_svc_map`` may be the human-readable service
    name (e.g. ``SMS/MMS``) rather than a UUID string, so we also match
    on ``sms`` and ``mms``.
    """
    if not service_map:
        return False
    for key in service_map:
        low = key.lower()
        if (
            "1132" in low
            or "1134" in low
            or "message" in low
            or "map" in low
            or "sms" in low
            or "mms" in low
        ):
            return True
    return False


def list_mas_instances(
    mac_address: str,
    service_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Discover MAP-MSE instances and return their RFCOMM channels.

    When *service_map* (from ``state.current_mapping``) is provided the
    function extracts MAP entries from the cached data, avoiding a
    redundant ``sdptool`` invocation.  Falls back to a fresh SDP
    discovery when *service_map* is ``None`` or empty.

    Each entry contains ``name``, ``channel``, ``uuid``.
    """
    mac_address = mac_address.strip().upper()

    # -- fast path: use cached service map when available ----------------
    if service_map:
        instances: List[Dict[str, Any]] = []
        for _key, entry in service_map.items():
            if not isinstance(entry, dict):
                continue
            uuid_str = (entry.get("uuid") or "").lower()
            name_str = (entry.get("name") or "").lower()
            is_map = (
                any(s in uuid_str for s in _MAP_SHORTS)
                or "message" in name_str
                or "sms" in name_str
                or "mms" in name_str
            )
            if is_map and entry.get("channel") is not None:
                instances.append({
                    "name": entry.get("name", "MAP"),
                    "channel": entry["channel"],
                    "uuid": entry.get("uuid"),
                })
        if instances:
            print_and_log(
                f"[MAP] {len(instances)} MAS instance(s) from cached service map",
                LOG__DEBUG,
            )
            return instances

    # -- slow path: live SDP discovery -----------------------------------
    print_and_log(f"[MAP] Discovering MAS instances on {mac_address}", LOG__GENERAL)
    try:
        from bleep.ble_ops.classic.sdp import discover_services_sdp
        records = discover_services_sdp(mac_address)
    except Exception as exc:
        print_and_log(f"[MAP] SDP discovery failed: {exc}", LOG__DEBUG)
        return []

    instances = []
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


def list_folder_tree(
    mac_address: str, *, timeout: int = 30, instance: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Recursively enumerate the full MAP folder hierarchy.

    Returns a nested list of ``{"name": ..., "children": [...]}`` dicts.
    """
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Enumerating folder tree on {mac_address}", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        return sess.walk_folder_tree()


def collect_leaf_paths(tree: List[Dict[str, Any]], prefix: str = "") -> List[str]:
    """Flatten a MAP folder tree into a sorted list of leaf-node paths.

    *tree* is the nested structure returned by :func:`list_folder_tree`:
    ``[{"name": "telecom", "children": [...]}, ...]``
    """
    paths: List[str] = []
    for node in tree:
        path = f"{prefix}{node['name']}" if prefix else node["name"]
        if node.get("children"):
            paths.extend(collect_leaf_paths(node["children"], f"{path}/"))
        else:
            paths.append(path)
    return paths


def normalize_bmessage(raw: bytes) -> Tuple[bytes, bool]:
    """Normalize a bMessage payload for MAP spec compliance.

    1. Converts bare LF (``\\n`` not preceded by ``\\r``) to CRLF.
    2. Recalculates every ``LENGTH:`` field so it matches the byte span
       from ``BEGIN:MSG\\r\\n`` through ``END:MSG\\r\\n`` (inclusive).

    Returns ``(normalized_bytes, changed)`` where *changed* is ``True``
    when the content was modified.  Handles nested ``BENV`` blocks with
    multiple ``BBODY``/``LENGTH`` pairs.
    """
    # --- Step 1: fix bare LF → CRLF --------------------------------
    # Replace \r\n with a placeholder, convert remaining \n to \r\n,
    # then restore original \r\n.  This avoids doubling existing CRLFs.
    _PH = b"\x00\x01"
    work = raw.replace(b"\r\n", _PH)
    work = work.replace(b"\n", b"\r\n")
    work = work.replace(_PH, b"\r\n")

    # --- Step 2: recalculate each LENGTH field ----------------------
    text = work.decode("utf-8", errors="replace")
    upper = text.upper()

    begins = [m.start() for m in _re.finditer(r"BEGIN:MSG", upper)]
    ends = [m.start() for m in _re.finditer(r"END:MSG", upper)]

    # Pair each BEGIN:MSG with its closest following END:MSG
    pairs: List[Tuple[int, int]] = []
    used_ends: set = set()
    for b in begins:
        for e in ends:
            if e > b and e not in used_ends:
                pairs.append((b, e + len("END:MSG\r\n")))
                used_ends.add(e)
                break

    length_pat = _re.compile(r"(?im)^(LENGTH:)\s*\d+")
    lengths = list(length_pat.finditer(text))

    result = work
    offset_adj = 0
    for lm in lengths:
        # Find the BEGIN:MSG…END:MSG pair whose BEGIN follows this LENGTH
        lpos = lm.start() + offset_adj
        pair = next((p for p in pairs if p[0] > lm.start()), None)
        if pair is None:
            continue
        begin_byte = pair[0] + offset_adj
        end_byte = pair[1] + offset_adj
        actual = end_byte - begin_byte

        old_field = f"{lm.group(1)}{text[lm.start() + len(lm.group(1)):lm.end()]}"
        new_field = f"LENGTH:{actual}"
        old_bytes = old_field.encode("utf-8")
        new_bytes = new_field.encode("utf-8")
        # Replace at the precise byte offset
        field_byte_start = lpos
        field_byte_end = lm.end() + offset_adj
        result = result[:field_byte_start] + new_bytes + result[field_byte_end:]
        offset_adj += len(new_bytes) - len(old_bytes)
        # Update pair offsets for subsequent iterations
        pairs = [(s + (len(new_bytes) - len(old_bytes)) if s > field_byte_start else s,
                  e + (len(new_bytes) - len(old_bytes)) if e > field_byte_start else e)
                 for s, e in pairs]

    return result, result != raw


def _normalize_for_push(filepath: str) -> str:
    """Return a filepath whose content is MAP-spec-compliant bMessage.

    If the file already uses CRLF with correct LENGTH fields, returns the
    original path.  Otherwise writes normalized content to a temporary file
    and returns that path (caller must delete it).
    """
    with open(filepath, "rb") as fh:
        raw = fh.read()
    normalized, changed = normalize_bmessage(raw)
    if not changed:
        return filepath
    print_and_log(
        "[MAP] Normalizing bMessage (LF→CRLF / LENGTH recalc) before push",
        LOG__DEBUG,
    )
    fd, tmp_path = _tempfile.mkstemp(suffix=".bmsg", prefix="bleep_map_")
    try:
        _os.write(fd, normalized)
    finally:
        _os.close(fd)
    return tmp_path


def list_messages(
    mac_address: str,
    folder: str = "",
    *,
    filters: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    instance: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List messages in *folder* on the remote MAS.

    OBEX MAP semantics require ``SetFolder`` to navigate, then
    ``ListMessages("")`` to list at the *current* folder.  Passing the
    same folder to both would resolve as ``folder/folder``.

    Calling with an empty *folder* at the MAP root is also invalid
    because the root directory contains only folder metadata, not
    messages.  Path token validation (rejecting ``"."`` and ``".."``)
    is handled by the command layer.
    """
    folder = folder.strip().rstrip("/")

    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Listing messages in '{folder or '(root)'}' on {mac_address}", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        if folder:
            sess.set_folder(folder)
        # Always list at the current folder ("") to avoid double-folder.
        return sess.list_messages("", filters=filters)


def get_message(
    mac_address: str,
    handle: str,
    dest: str,
    *,
    folder: str = "",
    timeout: int = 60,
    instance: Optional[int] = None,
) -> Path:
    mac_address = mac_address.strip().upper()
    print_and_log(f"[MAP] Downloading message {handle} from {mac_address}", LOG__GENERAL)
    with _session(mac_address, timeout, instance) as sess:
        result = sess.get_message(handle, dest, folder=folder)

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
    effective = _normalize_for_push(filepath)
    try:
        with _session(mac_address, timeout, instance) as sess:
            sess.push_message(effective, folder)
    finally:
        if effective != filepath:
            try:
                _os.unlink(effective)
            except OSError:
                pass
    print_and_log("[MAP] Message pushed successfully", LOG__GENERAL)

    if _obs:
        try:
            _obs.upsert_map_access(mac_address, filepath, "push")
        except Exception:
            pass


def download_all_messages(
    mac_address: str,
    dest_dir: str,
    *,
    folders: Optional[List[str]] = None,
    max_count: Optional[int] = None,
    timeout: int = 120,
    instance: Optional[int] = None,
    progress_cb: Optional[Callable[[str, int, int, str], None]] = None,
) -> Dict[str, List[Path]]:
    """Download every message from the remote device into *dest_dir*.

    Parameters
    ----------
    folders : list of str, optional
        Restrict to these folder paths.  ``None`` → discover all leaf folders.
    max_count : int, optional
        ``MaxCount`` filter per folder to limit listing size.
    progress_cb : callable, optional
        ``progress_cb(folder, current_1based, total, dest_path)`` called
        after each successful download.

    Returns a mapping ``{folder: [Path, ...]}``.
    """
    import re
    import dbus as _dbus

    mac_address = mac_address.strip().upper()
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    if folders is None:
        tree = list_folder_tree(mac_address, timeout=timeout, instance=instance)
        folders = sorted(collect_leaf_paths(tree))

    print_and_log(
        f"[MAP] download-all: {len(folders)} folder(s) on {mac_address}", LOG__GENERAL,
    )

    results: Dict[str, List[Path]] = {}
    for folder in folders:
        short = re.sub(r"^telecom/msg/", "", folder)
        safe = short.replace("/", "_") or folder.replace("/", "_")

        filters: Optional[Dict[str, Any]] = None
        if max_count is not None:
            filters = {"MaxCount": _dbus.UInt16(max_count)}

        try:
            with _session(mac_address, timeout, instance) as sess:
                if folder:
                    sess.set_folder(folder)
                msgs = sess.list_messages("", filters=filters)

                if not msgs:
                    print_and_log(f"[MAP] {folder}: empty", LOG__DEBUG)
                    results[folder] = []
                    continue

                downloaded: List[Path] = []
                for idx, m in enumerate(msgs, 1):
                    handle = (
                        m.get("path", "").rsplit("message", 1)[-1]
                        if "path" in m
                        else None
                    )
                    if not handle:
                        continue

                    fname = f"{safe}_{handle}.bmsg"
                    file_dest = str(dest / fname)
                    try:
                        result_path = sess.get_message(
                            handle, file_dest, folder="",
                        )
                        downloaded.append(result_path)
                        if progress_cb:
                            progress_cb(folder, idx, len(msgs), str(result_path))
                    except Exception as exc:
                        print_and_log(
                            f"[MAP] download-all: get {handle} in {folder} "
                            f"failed: {exc}",
                            LOG__DEBUG,
                        )
                        if progress_cb:
                            progress_cb(folder, idx, len(msgs), f"FAILED: {exc}")

                    if _obs:
                        try:
                            _obs.upsert_map_access(mac_address, handle, "get")
                        except Exception:
                            pass

                results[folder] = downloaded
        except Exception as exc:
            print_and_log(
                f"[MAP] download-all: folder '{folder}' failed: {exc}", LOG__DEBUG,
            )
            results[folder] = []

    return results


_SESSION_RETRY_ERRORS = ("CreateSession", "Timed out", "Timeout")

_DEFAULT_PUSH_DELAY = 1.5  # seconds between consecutive pushes
_SESSION_RETRY_PAUSE = 3.0  # seconds before retrying a transient session failure


def push_all_messages(
    mac_address: str,
    filepaths: List[str],
    folder: str = "telecom/msg/outbox",
    *,
    timeout: int = 60,
    instance: Optional[int] = None,
    dry_run: bool = False,
    delay: float = _DEFAULT_PUSH_DELAY,
    progress_cb: Optional[Callable[[str, int, int, str], None]] = None,
) -> Dict[str, str]:
    """Push multiple bMessage files to the remote device sequentially.

    Parameters
    ----------
    dry_run : bool
        Validate files without actually pushing.
    delay : float
        Seconds to wait between consecutive pushes.  Gives ``obexd`` and
        the remote MAS time to tear down the previous OBEX session.
    progress_cb : callable, optional
        ``progress_cb(filepath, current_1based, total, status)`` called per file.

    Returns ``{filepath: "ok" | error_string}``.
    """
    mac_address = mac_address.strip().upper()
    print_and_log(
        f"[MAP] push-all: {len(filepaths)} file(s) → {mac_address} ({folder})",
        LOG__GENERAL,
    )

    results: Dict[str, str] = {}
    last_push_idx = 0
    for idx, fp in enumerate(filepaths, 1):
        basename = _os.path.basename(fp)
        if not _os.path.isfile(fp):
            status = "SKIP: file not found"
            results[fp] = status
            if progress_cb:
                progress_cb(fp, idx, len(filepaths), status)
            continue

        try:
            with open(fp, "rb") as fh:
                raw = fh.read()
            text = raw.decode("utf-8", errors="replace")
            if not text.lstrip().upper().startswith("BEGIN:BMSG"):
                status = "SKIP: not a valid bMessage (missing BEGIN:BMSG)"
                results[fp] = status
                if progress_cb:
                    progress_cb(fp, idx, len(filepaths), status)
                continue
        except Exception as exc:
            status = f"SKIP: read error: {exc}"
            results[fp] = status
            if progress_cb:
                progress_cb(fp, idx, len(filepaths), status)
            continue

        if dry_run:
            _, would_change = normalize_bmessage(raw)
            note = " (will normalize LF→CRLF)" if would_change else ""
            status = f"ok (dry-run){note}"
            results[fp] = status
            if progress_cb:
                progress_cb(fp, idx, len(filepaths), status)
            continue

        if delay > 0 and last_push_idx > 0:
            _time.sleep(delay)

        try:
            push_message(mac_address, fp, folder, timeout=timeout, instance=instance)
            status = "ok"
        except Exception as exc:
            err_str = str(exc)
            if any(tok in err_str for tok in _SESSION_RETRY_ERRORS):
                print_and_log(
                    f"[MAP] Session timeout for {basename}, retrying in "
                    f"{_SESSION_RETRY_PAUSE}s…",
                    LOG__GENERAL,
                )
                _time.sleep(_SESSION_RETRY_PAUSE)
                try:
                    push_message(
                        mac_address, fp, folder,
                        timeout=timeout, instance=instance,
                    )
                    status = "ok (retry)"
                except Exception as exc2:
                    status = f"FAILED: {exc2}"
            else:
                status = f"FAILED: {exc}"

        last_push_idx = idx
        results[fp] = status
        if progress_cb:
            progress_cb(fp, idx, len(filepaths), status)

    return results


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
