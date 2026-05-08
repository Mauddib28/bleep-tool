"""bleep.dbuslayer.obex_map – Message Access Profile via BlueZ *obexd* D-Bus API.

Uses the session D-Bus where *obexd* exposes ``org.bluez.obex``.
Provides synchronous wrappers around ``MessageAccess1`` methods.

Prerequisites:
  - ``bluetooth-obexd`` must be running.
  - Target device must be paired and trusted.
  - Device must advertise MAP-MSE (UUID 0x1132) or MAP (UUID 0x1134).

Limitations (future expansion):
  - No multi-instance MAP support (MAS instance selection).
  - ``PushMessage`` sends to ``telecom/msg/outbox`` by default.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import dbus

from bleep.core.log import print_and_log, LOG__DEBUG

from bleep.bt_ref.constants import (
    OBEX_SERVICE as _OBEX_SERVICE,
    OBEX_ROOT_PATH,
    OBEX_CLIENT_INTERFACE as _OBEX_CLIENT_IFACE,
    OBEX_MAP_INTERFACE as _OBEX_MAP_IFACE,
    OBEX_MAP_MESSAGE_INTERFACE as _OBEX_MSG_IFACE,
    DBUS_PROPERTIES,
)

from bleep.dbuslayer._obex_common import (
    poll_obex_transfer as _poll_transfer_common,
    unwrap_dbus as _unwrap,
)

try:
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    _HAS_GLIB = True
except ImportError:
    _HAS_GLIB = False


class MapSession:
    """Manage a single MAP client session against a remote device.

    *instance* selects a specific MAS instance by RFCOMM channel number
    (passed as the ``Channel`` byte to ``CreateSession``).  When ``None``
    (default), BlueZ connects to the first available MAS.
    """

    def __init__(
        self,
        mac_address: str,
        *,
        timeout: int = 30,
        instance: Optional[int] = None,
    ):
        self.mac = mac_address.strip().upper()
        self._timeout = timeout
        self._instance = instance
        self._bus = dbus.SessionBus()

        try:
            client_obj = self._bus.get_object(_OBEX_SERVICE, OBEX_ROOT_PATH)
            self._client = dbus.Interface(client_obj, _OBEX_CLIENT_IFACE)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"BlueZ obexd not running or D-Bus error: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

        session_args = dbus.Dictionary({"Target": "map"}, signature="sv")
        if instance is not None:
            session_args["Channel"] = dbus.Byte(instance)

        label = f"[MAP] Creating session → {self.mac}"
        if instance is not None:
            label += f" (channel {instance})"
        print_and_log(label, LOG__DEBUG)

        try:
            self._session_path = self._client.CreateSession(
                self.mac, session_args
            )
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"MAP CreateSession failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

        session_obj = self._bus.get_object(_OBEX_SERVICE, self._session_path)
        self._map = dbus.Interface(session_obj, _OBEX_MAP_IFACE)

    def close(self) -> None:
        if getattr(self, "_mns_loop", None) is not None:
            self.stop_notification_watch()
        try:
            self._client.RemoveSession(self._session_path)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- folder navigation ---------------------------------------------------

    def set_folder(self, folder: str) -> None:
        self._map.SetFolder(folder)

    def list_folders(self) -> List[Dict[str, Any]]:
        raw = self._map.ListFolders(
            dbus.Dictionary({}, signature="sv"), timeout=self._timeout,
        )
        return [dict(item) for item in raw]

    def walk_folder_tree(self, max_depth: int = 10) -> List[Dict[str, Any]]:
        """Recursively enumerate the MAP folder hierarchy from the current position.

        Returns a nested structure:
        ``[{"name": "telecom", "children": [{"name": "msg", "children": [...]}]}]``

        *max_depth* prevents runaway recursion on pathological devices.
        """
        tree: List[Dict[str, Any]] = []
        try:
            folders = self.list_folders()
        except dbus.exceptions.DBusException as exc:
            print_and_log(
                f"[MAP] ListFolders failed during tree walk: {exc}", LOG__DEBUG,
            )
            return tree
        for entry in folders:
            name = entry.get("Name", "")
            if not name:
                continue
            node: Dict[str, Any] = {"name": name, "children": []}
            if max_depth > 0:
                try:
                    self.set_folder(name)
                    node["children"] = self.walk_folder_tree(max_depth - 1)
                    self.set_folder("..")
                except dbus.exceptions.DBusException as exc:
                    print_and_log(
                        f"[MAP] Cannot descend into '{name}': {exc}", LOG__DEBUG,
                    )
            tree.append(node)
        return tree

    # -- message access ------------------------------------------------------

    def list_messages(
        self, folder: str = "", filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        filt = dbus.Dictionary(filters or {}, signature="sv")
        print_and_log(
            f"[MAP] D-Bus ListMessages(folder='{folder}', filter={filters})",
            LOG__DEBUG,
        )
        raw = self._map.ListMessages(folder, filt, timeout=self._timeout * 4)
        print_and_log(
            f"[MAP] ListMessages returned {type(raw).__name__} "
            f"(len={len(raw) if hasattr(raw, '__len__') else 'N/A'})",
            LOG__DEBUG,
        )

        messages: List[Dict[str, Any]] = []
        # a{oa{sv}} is represented as dbus.Dictionary by the Python dbus library.
        if isinstance(raw, dbus.Dictionary):
            for path, props in raw.items():
                messages.append(
                    {"path": str(path),
                     **{str(k): _unwrap(v) for k, v in props.items()}}
                )
        elif isinstance(raw, dbus.Array):
            # Fallback: some BlueZ versions may return an array of structs.
            for item in raw:
                if isinstance(item, (tuple, list)) and len(item) == 2:
                    path, props = item
                    messages.append(
                        {"path": str(path),
                         **{str(k): _unwrap(v) for k, v in props.items()}}
                    )
                elif isinstance(item, dict):
                    messages.append(
                        {str(k): _unwrap(v) for k, v in item.items()}
                    )
                else:
                    print_and_log(
                        f"[MAP] Unexpected item in ListMessages array: "
                        f"{type(item).__name__}",
                        LOG__DEBUG,
                    )
        else:
            print_and_log(
                f"[MAP] ListMessages returned unexpected type: "
                f"{type(raw).__name__}",
                LOG__DEBUG,
            )
            raise TypeError(
                f"ListMessages returned unexpected type: {type(raw).__name__}"
            )

        return messages

    def _populate_message_objects(self, folder: str) -> None:
        """Navigate to *folder* and call ``ListMessages`` to create message
        D-Bus objects within this session.  The reference BlueZ ``map-client``
        does this before every ``Get``, ``GetAll``, or ``SetProperty`` call.
        """
        if folder:
            self.set_folder(folder)
        self._map.ListMessages(
            "", dbus.Dictionary({}, signature="sv"),
            timeout=self._timeout * 4,
        )

    def get_message(
        self, handle: str, dest: str,
        *, attachment: bool = True, folder: str = "",
    ) -> Path:
        """Download message *handle* to *dest* file path.

        *folder* must be the MAP folder that contains the message (e.g.
        ``telecom/msg/inbox``).  ``ListMessages`` is called within this
        session to materialise the message D-Bus object before access.
        """
        if folder:
            self._populate_message_objects(folder)
        dest = os.path.abspath(dest)
        path = f"{self._session_path}/message{handle}"
        obj = self._bus.get_object(_OBEX_SERVICE, path)
        msg = dbus.Interface(obj, _OBEX_MSG_IFACE)

        transfer_path, transfer_props = msg.Get(dest, attachment)
        self._poll_transfer(transfer_path)

        result = Path(dest)
        if not result.exists():
            fname = transfer_props.get("Filename")
            if fname:
                result = Path(str(fname))
        return result

    def push_message(
        self, filepath: str, folder: str = "telecom/msg/outbox"
    ) -> None:
        filepath = os.path.abspath(filepath)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        transfer_path, _ = self._map.PushMessage(
            filepath, folder, dbus.Dictionary({}, signature="sv")
        )
        self._poll_transfer(transfer_path)

    def update_inbox(self) -> None:
        self._map.UpdateInbox(timeout=self._timeout)

    # -- metadata queries ----------------------------------------------------

    def get_supported_types(self) -> List[str]:
        """Return ``SupportedTypes`` property from ``MessageAccess1``.

        Possible values: ``EMAIL``, ``SMS_GSM``, ``SMS_CDMA``, ``MMS``, ``IM``.

        Returns an empty list when the property is unavailable (e.g.
        BlueZ 5.64 does not expose ``SupportedTypes``).
        """
        try:
            session_obj = self._bus.get_object(_OBEX_SERVICE, self._session_path)
            props = dbus.Interface(session_obj, DBUS_PROPERTIES)
            raw = props.Get(_OBEX_MAP_IFACE, "SupportedTypes")
            return [str(t) for t in raw]
        except dbus.exceptions.DBusException as exc:
            print_and_log(
                f"[MAP] SupportedTypes unavailable: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}",
                LOG__DEBUG,
            )
            return []

    def list_filter_fields(self) -> List[str]:
        """Return all field names usable in ``ListMessages`` ``Fields`` filter."""
        raw = self._map.ListFilterFields(timeout=self._timeout)
        return [str(f) for f in raw]

    # -- MNS notification monitoring -----------------------------------------

    def start_notification_watch(
        self,
        callback: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        """Begin monitoring ``PropertiesChanged`` signals on ``Message1`` objects.

        *callback* is invoked as ``callback(object_path, changed_props)`` on
        every property change for any ``Message1`` object within this session.
        The callback runs on a background GLib MainLoop thread.

        Requires ``dbus.mainloop.glib`` and ``gi.repository.GLib``.
        Call :meth:`stop_notification_watch` to tear down.
        """
        if not _HAS_GLIB:
            raise RuntimeError(
                "GLib mainloop not available – install PyGObject "
                "(apt install python3-gi gir1.2-glib-2.0)"
            )
        if getattr(self, "_mns_loop", None) is not None:
            raise RuntimeError("Notification watch already running")

        DBusGMainLoop(set_as_default=True)
        self._mns_callback = callback
        self._mns_loop = GLib.MainLoop()

        session_prefix = str(self._session_path) + "/"

        def _on_props_changed(interface, changed, invalidated, path=None):
            if path and str(path).startswith(session_prefix):
                props = {str(k): _unwrap(v) for k, v in changed.items()}
                try:
                    self._mns_callback(str(path), props)
                except Exception:
                    pass

        self._mns_signal_match = self._bus.add_signal_receiver(
            _on_props_changed,
            signal_name="PropertiesChanged",
            dbus_interface="org.freedesktop.DBus.Properties",
            bus_name=_OBEX_SERVICE,
            path_keyword="path",
        )

        self._mns_thread = threading.Thread(
            target=self._mns_loop.run, daemon=True, name="map-mns-watch",
        )
        self._mns_thread.start()
        print_and_log("[MAP] MNS notification watch started", LOG__DEBUG)

    def stop_notification_watch(self) -> None:
        """Stop the MNS notification watch started by :meth:`start_notification_watch`."""
        match = getattr(self, "_mns_signal_match", None)
        if match is not None:
            match.remove()
            self._mns_signal_match = None

        loop = getattr(self, "_mns_loop", None)
        if loop is not None and loop.is_running():
            loop.quit()
        self._mns_loop = None
        self._mns_thread = None
        self._mns_callback = None
        print_and_log("[MAP] MNS notification watch stopped", LOG__DEBUG)

    # -- message properties --------------------------------------------------

    def get_message_properties(
        self, handle: str, *, folder: str = "",
    ) -> Dict[str, Any]:
        if folder:
            self._populate_message_objects(folder)
        path = f"{self._session_path}/message{handle}"
        obj = self._bus.get_object(_OBEX_SERVICE, path)
        props = dbus.Interface(obj, DBUS_PROPERTIES)
        raw = props.GetAll(_OBEX_MSG_IFACE)
        return {str(k): _unwrap(v) for k, v in raw.items()}

    def set_message_read(
        self, handle: str, read: bool = True, *, folder: str = "",
    ) -> None:
        if folder:
            self._populate_message_objects(folder)
        path = f"{self._session_path}/message{handle}"
        obj = self._bus.get_object(_OBEX_SERVICE, path)
        props = dbus.Interface(obj, DBUS_PROPERTIES)
        props.Set(
            _OBEX_MSG_IFACE, "Read",
            dbus.Boolean(read, variant_level=1),
        )

    def set_message_deleted(
        self, handle: str, deleted: bool = True, *, folder: str = "",
    ) -> None:
        if folder:
            self._populate_message_objects(folder)
        path = f"{self._session_path}/message{handle}"
        obj = self._bus.get_object(_OBEX_SERVICE, path)
        props = dbus.Interface(obj, DBUS_PROPERTIES)
        props.Set(
            _OBEX_MSG_IFACE, "Deleted",
            dbus.Boolean(deleted, variant_level=1),
        )

    # -- internal ------------------------------------------------------------

    def _poll_transfer(self, transfer_path: str) -> None:
        _poll_transfer_common(
            self._bus, transfer_path, self._timeout, label="MAP"
        )
