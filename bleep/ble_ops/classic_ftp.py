"""bleep.ble_ops.classic_ftp – File Transfer Profile operations.

Thin wrapper around ``bleep.dbuslayer.obex_ftp`` that adds BLEEP-standard
logging, optional observation-database storage, and service detection from
SDP records (UUID ``0x1106``).

Prerequisites: same as ``obex_ftp`` (``bluetooth-obexd``, paired/trusted).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None

from bleep.dbuslayer.obex_ftp import FtpSession

from bleep.bt_ref.constants import FTP_UUID_SHORT


def detect_ftp_service(service_map: Optional[Dict[str, int]]) -> bool:
    """Return True if the service map contains an FTP entry."""
    if not service_map:
        return False
    for key in service_map:
        low = key.lower()
        if "1106" in low or "file transfer" in low or "ftp" in low:
            return True
    return False


def list_folder(
    mac_address: str,
    path: str = "",
    *,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """List a folder on the remote device.

    If *path* is non-empty, navigate to it first (from root).
    Returns a list of entry dicts (``Name``, ``Type``, ``Size``, etc.).
    """
    mac_address = mac_address.strip().upper()
    print_and_log(f"[FTP] Listing folder on {mac_address} path={path!r}", LOG__GENERAL)

    with FtpSession(mac_address, timeout=timeout) as ftp:
        if path:
            for segment in path.strip("/").split("/"):
                ftp.change_folder(segment)
        entries = ftp.list_folder()

    print_and_log(f"[FTP] {len(entries)} entries returned", LOG__DEBUG)
    return entries


def get_file(
    mac_address: str,
    remote_file: str,
    local_dest: str,
    *,
    remote_path: str = "",
    timeout: int = 120,
) -> Path:
    """Download *remote_file* from the remote device.

    *remote_path* optionally navigates to a subfolder first.
    Returns the ``Path`` to the downloaded file.
    """
    mac_address = mac_address.strip().upper()
    local_dest = os.path.abspath(local_dest)
    print_and_log(
        f"[FTP] GetFile {remote_file!r} → {local_dest!r} from {mac_address}",
        LOG__GENERAL,
    )

    with FtpSession(mac_address, timeout=timeout) as ftp:
        if remote_path:
            for segment in remote_path.strip("/").split("/"):
                ftp.change_folder(segment)
        result = ftp.get_file(remote_file, local_dest, timeout=timeout)

    print_and_log(f"[FTP] Downloaded → {result}", LOG__GENERAL)

    if _obs:
        try:
            _obs.upsert_ftp_transfer(
                mac_address, remote_file, "get",
                result.stat().st_size if result.exists() else 0,
            )
        except Exception:
            pass

    return result


def put_file(
    mac_address: str,
    local_file: str,
    remote_name: str = "",
    *,
    remote_path: str = "",
    timeout: int = 120,
) -> Dict[str, Any]:
    """Upload *local_file* to the current (or specified) remote folder.

    Returns the poll result dict (``status``, ``transferred``, ``size``).
    """
    mac_address = mac_address.strip().upper()
    local_file = os.path.abspath(local_file)
    print_and_log(
        f"[FTP] PutFile {local_file!r} → {mac_address}", LOG__GENERAL,
    )

    with FtpSession(mac_address, timeout=timeout) as ftp:
        if remote_path:
            for segment in remote_path.strip("/").split("/"):
                ftp.change_folder(segment)
        result = ftp.put_file(local_file, remote_name, timeout=timeout)

    print_and_log(
        f"[FTP] Upload complete: {result.get('transferred', '?')}B", LOG__GENERAL,
    )

    if _obs:
        try:
            _obs.upsert_ftp_transfer(
                mac_address,
                remote_name or os.path.basename(local_file),
                "put",
                result.get("size", 0),
            )
        except Exception:
            pass

    return result


def create_folder(
    mac_address: str,
    folder_name: str,
    *,
    remote_path: str = "",
    timeout: int = 30,
) -> None:
    """Create a folder on the remote device."""
    mac_address = mac_address.strip().upper()
    print_and_log(f"[FTP] CreateFolder {folder_name!r} on {mac_address}", LOG__GENERAL)

    with FtpSession(mac_address, timeout=timeout) as ftp:
        if remote_path:
            for segment in remote_path.strip("/").split("/"):
                ftp.change_folder(segment)
        ftp.create_folder(folder_name)

    print_and_log(f"[FTP] Folder created", LOG__DEBUG)


def delete_item(
    mac_address: str,
    name: str,
    *,
    remote_path: str = "",
    timeout: int = 30,
) -> None:
    """Delete a file or folder on the remote device."""
    mac_address = mac_address.strip().upper()
    print_and_log(f"[FTP] Delete {name!r} on {mac_address}", LOG__GENERAL)

    with FtpSession(mac_address, timeout=timeout) as ftp:
        if remote_path:
            for segment in remote_path.strip("/").split("/"):
                ftp.change_folder(segment)
        ftp.delete(name)

    print_and_log(f"[FTP] Deleted", LOG__DEBUG)


def copy_file(
    mac_address: str,
    source: str,
    target: str,
    *,
    timeout: int = 30,
) -> None:
    """Copy *source* to *target* on the remote device."""
    mac_address = mac_address.strip().upper()
    print_and_log(f"[FTP] CopyFile {source!r} → {target!r} on {mac_address}", LOG__GENERAL)

    with FtpSession(mac_address, timeout=timeout) as ftp:
        ftp.copy_file(source, target)


def move_file(
    mac_address: str,
    source: str,
    target: str,
    *,
    timeout: int = 30,
) -> None:
    """Move *source* to *target* on the remote device."""
    mac_address = mac_address.strip().upper()
    print_and_log(f"[FTP] MoveFile {source!r} → {target!r} on {mac_address}", LOG__GENERAL)

    with FtpSession(mac_address, timeout=timeout) as ftp:
        ftp.move_file(source, target)
