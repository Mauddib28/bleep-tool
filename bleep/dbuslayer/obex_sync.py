"""D-Bus layer for OBEX IrMC Synchronization via BlueZ *obexd*.

Uses the session D-Bus where *obexd* exposes ``org.bluez.obex``.
Provides synchronous wrappers around ``Synchronization1`` methods.

Session target: ``"sync"`` (per ``org.bluez.obex.Client.rst``).

Prerequisites:
  - ``bluetooth-obexd`` must be running.
  - Target device must be paired and trusted.
  - Very few devices support IrMC Sync (UUID 0x1104).

D-Bus reference: ``org.bluez.obex.Synchronization.rst``
  - ``SetLocation(location)``         → ``"int"`` or ``"sim{#}"``
  - ``GetPhonebook(targetfile)``       → returns (transfer_path, properties)
  - ``PutPhonebook(sourcefile)``       → returns (transfer_path, properties)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import dbus

from bleep.core.log import print_and_log, LOG__DEBUG

from bleep.bt_ref.constants import (
    OBEX_SERVICE as _OBEX_SERVICE,
    OBEX_ROOT_PATH,
    OBEX_CLIENT_INTERFACE as _OBEX_CLIENT_IFACE,
    OBEX_SYNC_INTERFACE as _OBEX_SYNC_IFACE,
)

from bleep.dbuslayer._obex_common import (
    poll_obex_transfer as _poll_transfer,
    unwrap_dbus as _unwrap,
)


class SyncSession:
    """Manage a single OBEX IrMC Sync session against a remote device.

    Use as a context manager::

        with SyncSession("AA:BB:CC:DD:EE:FF") as sync:
            sync.set_location("int")
            result = sync.get_phonebook("/tmp/pb.vcf")
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

        print_and_log(f"[SYNC] Creating session → {self.mac}", LOG__DEBUG)
        try:
            self._session_path = self._client.CreateSession(
                self.mac, {"Target": "sync"}
            )
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"SYNC CreateSession failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

        session_obj = self._bus.get_object(_OBEX_SERVICE, self._session_path)
        self._sync = dbus.Interface(session_obj, _OBEX_SYNC_IFACE)

    def close(self) -> None:
        try:
            self._client.RemoveSession(self._session_path)
        except Exception:
            pass

    def __enter__(self) -> "SyncSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- Synchronization1 methods --

    def set_location(self, location: str = "int") -> None:
        """Set the phonebook object store location.

        *location*: ``"int"`` (internal, default) or ``"sim{#}"`` for SIM.
        """
        print_and_log(f"[SYNC] SetLocation({location})", LOG__DEBUG)
        try:
            self._sync.SetLocation(location)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"SYNC SetLocation failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

    def get_phonebook(
        self, target_file: str = "", *, timeout: Optional[int] = None,
    ) -> Path:
        """Retrieve the entire phonebook from the remote device.

        *target_file*: local file path to save to.  If empty, obexd
        auto-generates a temporary file name.

        Returns the ``Path`` to the downloaded file.
        """
        timeout = timeout or self._timeout
        print_and_log(f"[SYNC] GetPhonebook → {target_file or '(auto)'}", LOG__DEBUG)
        try:
            transfer_path, transfer_props = self._sync.GetPhonebook(target_file)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"SYNC GetPhonebook failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

        result = _poll_transfer(self._bus, transfer_path, timeout, label="SYNC")
        filename = result.get("filename", target_file)
        return Path(str(filename))

    def put_phonebook(
        self, source_file: str, *, timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send an entire phonebook to the remote device.

        *source_file*: local VCF file path to upload.

        Returns the transfer result dict.
        """
        timeout = timeout or self._timeout
        if not Path(source_file).is_file():
            raise FileNotFoundError(f"Source file not found: {source_file}")

        print_and_log(f"[SYNC] PutPhonebook ← {source_file}", LOG__DEBUG)
        try:
            transfer_path, transfer_props = self._sync.PutPhonebook(source_file)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"SYNC PutPhonebook failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

        return _poll_transfer(self._bus, transfer_path, timeout, label="SYNC")
