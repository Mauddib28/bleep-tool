"""bleep.dbuslayer.obex_ftp – File Transfer Profile via BlueZ *obexd* D-Bus API.

Uses the session D-Bus where *obexd* exposes ``org.bluez.obex``.
Provides synchronous wrappers around ``FileTransfer1`` methods.

Session target: ``"ftp"`` (per ``org.bluez.obex.Client.rst``).

Prerequisites:
  - ``bluetooth-obexd`` must be running.
  - Target device must be paired and trusted.
  - Device must advertise OBEX-FTP (UUID 0x1106).

D-Bus reference: ``org.bluez.obex.FileTransfer.rst``
  - ``GetFile(targetfile, sourcefile)``  → target=local, source=remote
  - ``PutFile(sourcefile, targetfile)``  → source=local, target=remote
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import dbus

from bleep.core.log import print_and_log, LOG__DEBUG

from bleep.bt_ref.constants import (
    OBEX_SERVICE as _OBEX_SERVICE,
    OBEX_ROOT_PATH,
    OBEX_CLIENT_INTERFACE as _OBEX_CLIENT_IFACE,
    OBEX_FTP_INTERFACE as _OBEX_FTP_IFACE,
)

from bleep.dbuslayer._obex_common import (
    poll_obex_transfer as _poll_transfer,
    unwrap_dbus as _unwrap,
)


class FtpSession:
    """Manage a single OBEX FTP client session against a remote device.

    Use as a context manager::

        with FtpSession("AA:BB:CC:DD:EE:FF") as ftp:
            entries = ftp.list_folder()
    """

    def __init__(self, mac_address: str, *, timeout: int = 60):
        self.mac = mac_address.strip().upper()
        self._timeout = timeout
        self._bus = dbus.SessionBus()

        try:
            client_obj = self._bus.get_object(_OBEX_SERVICE, OBEX_ROOT_PATH)
            self._client = dbus.Interface(client_obj, _OBEX_CLIENT_IFACE)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"BlueZ obexd not running or D-Bus error: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

        print_and_log(f"[FTP] Creating session → {self.mac}", LOG__DEBUG)
        try:
            self._session_path = self._client.CreateSession(
                self.mac, {"Target": "ftp"}
            )
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"FTP CreateSession failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

        session_obj = self._bus.get_object(_OBEX_SERVICE, self._session_path)
        self._ftp = dbus.Interface(session_obj, _OBEX_FTP_IFACE)

    def close(self) -> None:
        try:
            self._client.RemoveSession(self._session_path)
        except Exception:
            pass

    def __enter__(self) -> "FtpSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- navigation -----------------------------------------------------------

    def change_folder(self, folder: str) -> None:
        """Change the current remote folder.

        Pass ``".."`` to go up one level, or ``""`` (empty string) to go to
        the root, per the OBEX specification.
        """
        try:
            self._ftp.ChangeFolder(folder)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"FTP ChangeFolder({folder!r}) failed: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

    def create_folder(self, folder: str) -> None:
        """Create a new folder on the remote device."""
        try:
            self._ftp.CreateFolder(folder)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"FTP CreateFolder({folder!r}) failed: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

    def list_folder(self) -> List[Dict[str, Any]]:
        """Return the current folder listing as a list of dicts.

        Each dict may contain: ``Name``, ``Type`` (``"folder"``/``"file"``),
        ``Size``, ``Permission``, ``Modified``, ``Accessed``, ``Created``.
        """
        try:
            raw = self._ftp.ListFolder()
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"FTP ListFolder failed: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc
        return [_unwrap(entry) for entry in raw]

    # -- file transfer --------------------------------------------------------

    def get_file(
        self, remote_file: str, local_dest: str, *, timeout: Optional[int] = None
    ) -> Path:
        """Download *remote_file* to *local_dest* (local filesystem path).

        Returns the ``Path`` to the downloaded file.
        """
        local_dest = os.path.abspath(local_dest)
        print_and_log(
            f"[FTP] GetFile {remote_file!r} → {local_dest!r}", LOG__DEBUG
        )
        try:
            transfer_path, _props = self._ftp.GetFile(local_dest, remote_file)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"FTP GetFile failed: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

        result = _poll_transfer(
            self._bus, transfer_path, timeout or self._timeout, label="FTP"
        )
        filename = result.get("filename", local_dest)
        return Path(filename)

    def put_file(
        self,
        local_file: str,
        remote_name: str = "",
        *,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Upload *local_file* to the current remote folder.

        *remote_name* defaults to the basename of *local_file* when empty.
        Returns the poll result dict (``status``, ``transferred``, ``size``).
        """
        local_file = os.path.abspath(local_file)
        if not os.path.isfile(local_file):
            raise FileNotFoundError(f"Local file not found: {local_file}")
        if not remote_name:
            remote_name = os.path.basename(local_file)

        print_and_log(
            f"[FTP] PutFile {local_file!r} → {remote_name!r}", LOG__DEBUG
        )
        try:
            transfer_path, _props = self._ftp.PutFile(local_file, remote_name)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"FTP PutFile failed: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

        return _poll_transfer(
            self._bus, transfer_path, timeout or self._timeout, label="FTP"
        )

    # -- remote file operations -----------------------------------------------

    def copy_file(self, source: str, target: str) -> None:
        """Copy *source* to *target* on the remote device."""
        try:
            self._ftp.CopyFile(source, target)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"FTP CopyFile({source!r} → {target!r}) failed: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

    def move_file(self, source: str, target: str) -> None:
        """Move *source* to *target* on the remote device."""
        try:
            self._ftp.MoveFile(source, target)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"FTP MoveFile({source!r} → {target!r}) failed: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

    def delete(self, name: str) -> None:
        """Delete a file or folder on the remote device."""
        try:
            self._ftp.Delete(name)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"FTP Delete({name!r}) failed: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc
