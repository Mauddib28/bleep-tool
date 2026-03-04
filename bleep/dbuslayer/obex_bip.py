"""D-Bus layer for OBEX Basic Imaging Profile via BlueZ *obexd*.

Uses the session D-Bus where *obexd* exposes ``org.bluez.obex``.
Provides synchronous wrappers around the **experimental** ``Image1`` methods.

Session target: ``"bip-avrcp"`` (per ``org.bluez.obex.Client.rst``).

Prerequisites:
  - ``bluetooth-obexd`` must be running **with the experimental flag**
    (``--experimental`` or ``NOINIT=1`` + manual launch).
  - Target device must be paired and trusted.
  - Device must advertise a BIP service (UUID 0x111A / 0x111B).

D-Bus reference: ``org.bluez.obex.Image.rst``
  - ``Get(targetfile, handle, description)``  → (transfer_path, properties)
  - ``Properties(handle)``                    → array of dicts
  - ``GetThumbnail(targetfile, handle)``      → (transfer_path, properties)

.. warning::
   ``Image1`` is marked **[experimental]** in BlueZ.  It may change or be
   removed without notice.  A ``RuntimeError`` is raised at session creation
   if the interface is unavailable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import dbus

from bleep.core.log import print_and_log, LOG__DEBUG

from bleep.bt_ref.constants import (
    OBEX_SERVICE as _OBEX_SERVICE,
    OBEX_ROOT_PATH,
    OBEX_CLIENT_INTERFACE as _OBEX_CLIENT_IFACE,
    OBEX_IMAGE_INTERFACE as _OBEX_IMAGE_IFACE,
)

from bleep.dbuslayer._obex_common import (
    poll_obex_transfer as _poll_transfer,
    unwrap_dbus as _unwrap,
)


class BipSession:
    """Manage a single OBEX BIP session against a remote device.

    Use as a context manager::

        with BipSession("AA:BB:CC:DD:EE:FF") as bip:
            props = bip.properties("1000001")
            bip.get_thumbnail("/tmp/thumb.jpg", "1000001")
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

        print_and_log(f"[BIP] Creating session → {self.mac}", LOG__DEBUG)
        try:
            self._session_path = self._client.CreateSession(
                self.mac, {"Target": "bip-avrcp"}
            )
        except dbus.exceptions.DBusException as exc:
            msg = exc.get_dbus_message() or ""
            raise RuntimeError(
                f"BIP CreateSession failed (is obexd running with "
                f"--experimental?): {exc.get_dbus_name()}: {msg}"
            ) from exc

        session_obj = self._bus.get_object(_OBEX_SERVICE, self._session_path)
        try:
            self._image = dbus.Interface(session_obj, _OBEX_IMAGE_IFACE)
        except dbus.exceptions.DBusException as exc:
            self._cleanup_session()
            raise RuntimeError(
                f"Image1 interface not available (experimental flag "
                f"required): {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

    def _cleanup_session(self) -> None:
        try:
            self._client.RemoveSession(self._session_path)
        except Exception:
            pass

    def close(self) -> None:
        self._cleanup_session()

    def __enter__(self) -> "BipSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- Image1 methods --

    def properties(self, handle: str) -> List[Dict[str, Any]]:
        """Retrieve image properties for a given handle.

        Returns a list of dicts: first is handle/name (mandatory), second is
        native description (mandatory), followed by optional variant
        descriptions.
        """
        print_and_log(f"[BIP] Properties({handle})", LOG__DEBUG)
        try:
            raw = self._image.Properties(handle)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"BIP Properties failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc
        return _unwrap(raw)

    def get_image(
        self,
        target_file: str,
        handle: str,
        description: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[int] = None,
    ) -> Path:
        """Download an image by handle.

        *description*: one of the descriptions returned by ``properties()``.
        Pass an empty dict ``{}`` to retrieve the native image.

        Returns the ``Path`` to the saved file.
        """
        timeout = timeout or self._timeout
        desc = description if description is not None else dbus.Dictionary({}, signature="sv")
        print_and_log(
            f"[BIP] Get({target_file}, {handle}, ...)", LOG__DEBUG,
        )
        try:
            transfer_path, transfer_props = self._image.Get(
                target_file, handle, desc,
            )
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"BIP Get failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

        result = _poll_transfer(self._bus, transfer_path, timeout, label="BIP")
        filename = result.get("filename", target_file)
        return Path(str(filename))

    def get_thumbnail(
        self,
        target_file: str,
        handle: str,
        *,
        timeout: Optional[int] = None,
    ) -> Path:
        """Download an image thumbnail by handle.

        Returns the ``Path`` to the saved thumbnail file.
        """
        timeout = timeout or self._timeout
        print_and_log(
            f"[BIP] GetThumbnail({target_file}, {handle})", LOG__DEBUG,
        )
        try:
            transfer_path, transfer_props = self._image.GetThumbnail(
                target_file, handle,
            )
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"BIP GetThumbnail failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

        result = _poll_transfer(self._bus, transfer_path, timeout, label="BIP")
        filename = result.get("filename", target_file)
        return Path(str(filename))
