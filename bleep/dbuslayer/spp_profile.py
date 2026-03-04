"""D-Bus layer for SPP (Serial Port Profile) via BlueZ ProfileManager1.

Registers a custom ``org.bluez.Profile1`` object that receives incoming
RFCOMM connections.  When a remote device connects, ``NewConnection``
delivers a file descriptor that can be wrapped into a Python socket for
bidirectional data exchange.

Reference docs
--------------
* ``workDir/BlueZDocs/org.bluez.ProfileManager.rst``
* ``workDir/BlueZDocs/org.bluez.Profile.rst``
* ``workDir/BlueZScripts/test-profile``
"""

from __future__ import annotations

import os
import socket
import threading
from typing import Any, Callable, Dict, Optional

import dbus
import dbus.service

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    PROFILE_MANAGER_INTERFACE as _PM_IFACE,
    PROFILE_INTERFACE as _PROFILE_IFACE,
    SPP_UUID,
)
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL

try:
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    _HAS_GLIB = True
except ImportError:
    _HAS_GLIB = False

_DEFAULT_PROFILE_PATH = "/bleep/spp/profile"


class SppProfile(dbus.service.Object):
    """``org.bluez.Profile1`` implementation for SPP.

    *on_connect* is called with ``(device_path, socket, fd_properties)``
    when a remote device connects.

    *on_disconnect* is called with ``(device_path,)`` when the remote
    side requests disconnection.

    *on_release* is called (no args) when BlueZ unregisters the profile.
    """

    def __init__(
        self,
        bus: dbus.Bus,
        path: str = _DEFAULT_PROFILE_PATH,
        *,
        on_connect: Optional[Callable] = None,
        on_disconnect: Optional[Callable] = None,
        on_release: Optional[Callable] = None,
    ):
        super().__init__(bus, path)
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._on_release = on_release
        self._fd: int = -1

    @dbus.service.method(
        _PROFILE_IFACE, in_signature="", out_signature="",
    )
    def Release(self) -> None:
        print_and_log("[SPP] Profile released by BlueZ", LOG__DEBUG)
        if self._on_release:
            self._on_release()

    @dbus.service.method(
        _PROFILE_IFACE, in_signature="oha{sv}", out_signature="",
    )
    def NewConnection(self, device: str, fd: Any, properties: Dict[str, Any]) -> None:
        self._fd = fd.take()
        props_str = ", ".join(f"{k}={v}" for k, v in properties.items())
        print_and_log(
            f"[SPP] NewConnection: device={device} fd={self._fd} [{props_str}]",
            LOG__GENERAL,
        )
        sock = socket.socket(fileno=os.dup(self._fd))
        if self._on_connect:
            self._on_connect(device, sock, dict(properties))

    @dbus.service.method(
        _PROFILE_IFACE, in_signature="o", out_signature="",
    )
    def RequestDisconnection(self, device: str) -> None:
        print_and_log(f"[SPP] RequestDisconnection: device={device}", LOG__GENERAL)
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = -1
        if self._on_disconnect:
            self._on_disconnect(device)


class SppManager:
    """Register / unregister an SPP profile with BlueZ.

    Usage::

        mgr = SppManager(on_connect=my_callback)
        mgr.register()          # profile is now visible to remote devices
        # ... wait for connections ...
        mgr.unregister()        # clean up
    """

    def __init__(
        self,
        *,
        uuid: str = SPP_UUID,
        channel: Optional[int] = None,
        name: str = "BLEEP SPP",
        role: str = "server",
        require_auth: bool = True,
        auto_connect: bool = False,
        profile_path: str = _DEFAULT_PROFILE_PATH,
        on_connect: Optional[Callable] = None,
        on_disconnect: Optional[Callable] = None,
        on_release: Optional[Callable] = None,
    ):
        if not _HAS_GLIB:
            raise RuntimeError(
                "PyGObject (python3-gi) is required for SPP profile registration"
            )

        self._uuid = uuid
        self._channel = channel
        self._name = name
        self._role = role
        self._require_auth = require_auth
        self._auto_connect = auto_connect
        self._profile_path = profile_path
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._on_release = on_release

        self._registered = False
        self._profile: Optional[SppProfile] = None
        self._loop: Optional[Any] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._bus: Optional[dbus.Bus] = None

    @property
    def registered(self) -> bool:
        return self._registered

    def register(self) -> None:
        """Register the SPP profile with BlueZ ``ProfileManager1``."""
        if self._registered:
            raise RuntimeError("SPP profile already registered")

        DBusGMainLoop(set_as_default=True)
        self._bus = dbus.SystemBus()

        self._profile = SppProfile(
            self._bus,
            self._profile_path,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            on_release=self._handle_release,
        )

        opts: Dict[str, Any] = {
            "AutoConnect": self._auto_connect,
            "Name": self._name,
            "Role": self._role,
            "RequireAuthentication": self._require_auth,
        }
        if self._channel is not None:
            opts["Channel"] = dbus.UInt16(self._channel)

        manager_obj = self._bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez")
        manager = dbus.Interface(manager_obj, _PM_IFACE)

        print_and_log(
            f"[SPP] Registering profile: uuid={self._uuid} role={self._role} "
            f"name={self._name} channel={self._channel or 'auto'}",
            LOG__GENERAL,
        )
        try:
            manager.RegisterProfile(self._profile_path, self._uuid, opts)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"SPP RegisterProfile failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

        self._registered = True

        self._loop = GLib.MainLoop()
        self._loop_thread = threading.Thread(
            target=self._loop.run, daemon=True, name="spp-glib-loop",
        )
        self._loop_thread.start()
        print_and_log("[SPP] Profile registered – waiting for connections", LOG__GENERAL)

    def unregister(self) -> None:
        """Unregister the SPP profile from BlueZ."""
        if not self._registered:
            return

        if self._loop is not None:
            try:
                self._loop.quit()
            except Exception:
                pass
            self._loop = None

        if self._bus is not None:
            try:
                manager_obj = self._bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez")
                manager = dbus.Interface(manager_obj, _PM_IFACE)
                manager.UnregisterProfile(self._profile_path)
            except dbus.exceptions.DBusException:
                pass

        self._registered = False
        self._profile = None
        print_and_log("[SPP] Profile unregistered", LOG__GENERAL)

    def _handle_release(self) -> None:
        self._registered = False
        if self._on_release:
            self._on_release()

    def status(self) -> Dict[str, Any]:
        """Return current SPP profile registration status."""
        return {
            "registered": self._registered,
            "uuid": self._uuid,
            "name": self._name,
            "role": self._role,
            "channel": self._channel,
            "profile_path": self._profile_path,
        }
