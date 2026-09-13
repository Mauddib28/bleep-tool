"""MediaAssistant1 D-Bus wrapper (BZ-19).

Wraps the ``org.bluez.MediaAssistant1`` interface for LE Audio Broadcast
Assistant functionality.  The assistant manages the lifecycle of broadcast
audio streams on behalf of a remote Broadcast Sink device.

The interface is **experimental** in BlueZ and requires ``--experimental``.
Object paths follow the pattern:
``/org/bluez/{hci}/dev_{ADDR}/src_{ADDR}/sid#/bis#``

States: ``idle`` → ``pending`` → ``requesting`` → ``active``

Reference: ``workDir/BlueZDocs/org.bluez.MediaAssistant.rst``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import dbus
import dbus.exceptions

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    DBUS_OM_IFACE,
    DBUS_PROPERTIES,
    MEDIA_ASSISTANT_INTERFACE,
)
from bleep.core.errors import map_dbus_error
from bleep.core.log import print_and_log, LOG__DEBUG

__all__ = ["MediaAssistant"]


class MediaAssistant:
    """Proxy for a single ``MediaAssistant1`` object.

    Parameters
    ----------
    bus : dbus.SystemBus
        System bus connection.
    path : str
        D-Bus object path of the media assistant.
    """

    def __init__(self, bus: dbus.SystemBus, path: str):
        self._bus = bus
        self._path = path
        obj = bus.get_object(BLUEZ_SERVICE_NAME, path)
        self._iface = dbus.Interface(obj, MEDIA_ASSISTANT_INTERFACE)
        self._props = dbus.Interface(obj, DBUS_PROPERTIES)

    @property
    def path(self) -> str:
        return self._path

    def push(self, properties: Optional[Dict[str, Any]] = None) -> None:
        """Send stream information to the remote Broadcast Sink.

        Parameters
        ----------
        properties : dict, optional
            Stream properties (``Metadata``, ``QoS``).
        """
        props = dbus.Dictionary(properties or {}, signature="sv")
        try:
            self._iface.Push(props)
        except dbus.exceptions.DBusException as exc:
            raise map_dbus_error(exc) from exc

    def get_state(self) -> Optional[str]:
        """Return the assistant state (idle/pending/requesting/active)."""
        try:
            return str(self._props.Get(MEDIA_ASSISTANT_INTERFACE, "State"))
        except dbus.exceptions.DBusException:
            return None

    def get_metadata(self) -> Optional[bytes]:
        """Return stream metadata bytes (if available)."""
        try:
            raw = self._props.Get(MEDIA_ASSISTANT_INTERFACE, "Metadata")
            return bytes(raw)
        except dbus.exceptions.DBusException:
            return None

    def get_qos(self) -> Optional[Dict[str, Any]]:
        """Return stream QoS properties dict."""
        try:
            raw = self._props.Get(MEDIA_ASSISTANT_INTERFACE, "QoS")
            return dict(raw)
        except dbus.exceptions.DBusException:
            return None

    def get_info(self) -> Dict[str, Any]:
        """Return summary dict for display."""
        return {
            "path": self._path,
            "state": self.get_state(),
            "metadata": self.get_metadata(),
            "qos": self.get_qos(),
        }


def enumerate_media_assistants(
    bus: dbus.SystemBus,
) -> List[MediaAssistant]:
    """Discover all MediaAssistant1 objects on the system bus."""
    try:
        om = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE,
        )
        managed = om.GetManagedObjects()
    except dbus.exceptions.DBusException:
        return []

    assistants: List[MediaAssistant] = []
    for path, ifaces in managed.items():
        if MEDIA_ASSISTANT_INTERFACE in ifaces:
            assistants.append(MediaAssistant(bus, str(path)))
    return assistants
