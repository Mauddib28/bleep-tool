"""Client wrapper for ``org.bluez.mesh.Node1``.

The Node1 interface lives at ``/org/bluez/mesh/node<uuid>`` and provides
message sending, key management, and node property introspection.

Reference: ``workDir/bluez/doc/mesh-api.txt`` lines 225–464.
"""

from __future__ import annotations

from typing import Any, Optional

import dbus

from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.mesh.constants import MESH_NODE_IFACE, MESH_SERVICE
from bleep.mesh.errors import map_mesh_dbus_error

DBUS_PROPERTIES = "org.freedesktop.DBus.Properties"


class MeshNode:
    """Proxy for the ``org.bluez.mesh.Node1`` interface.

    Parameters
    ----------
    node_path : str
        D-Bus object path, e.g. ``/org/bluez/mesh/node<uuid>``.
    bus : dbus.SystemBus, optional
        Existing bus connection.
    """

    def __init__(self, node_path: str, bus: dbus.SystemBus | None = None):
        self._bus = bus or dbus.SystemBus()
        self._path = node_path
        obj = self._bus.get_object(MESH_SERVICE, node_path)
        self._iface = dbus.Interface(obj, MESH_NODE_IFACE)
        self._props = dbus.Interface(obj, DBUS_PROPERTIES)

    # -- Message sending ---------------------------------------------------

    def send(
        self,
        element_path: str,
        destination: int,
        key_index: int,
        data: bytes,
        *,
        force_segmented: bool = False,
    ) -> None:
        """Send a mesh message via ``Node1.Send``.

        Parameters
        ----------
        element_path : str
            D-Bus path of the element originating the message.
        destination : int
            Unicast or group address.
        key_index : int
            Application key index.
        data : bytes
            Raw access-layer payload.
        force_segmented : bool
            If *True*, force segmentation regardless of payload length.
        """
        options: dict[str, Any] = {}
        if force_segmented:
            options["ForceSegmented"] = dbus.Boolean(True)
        try:
            self._iface.Send(
                dbus.ObjectPath(element_path),
                dbus.UInt16(destination),
                dbus.UInt16(key_index),
                dbus.Dictionary(options, signature="sv"),
                dbus.Array(data, signature="y"),
            )
            print_and_log(
                f"[mesh] Send dst=0x{destination:04x} key={key_index} len={len(data)}",
                LOG__DEBUG,
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def dev_key_send(
        self,
        element_path: str,
        destination: int,
        remote: bool,
        net_index: int,
        data: bytes,
        *,
        force_segmented: bool = False,
    ) -> None:
        """Send a device-key encrypted message via ``Node1.DevKeySend``."""
        options: dict[str, Any] = {}
        if force_segmented:
            options["ForceSegmented"] = dbus.Boolean(True)
        try:
            self._iface.DevKeySend(
                dbus.ObjectPath(element_path),
                dbus.UInt16(destination),
                dbus.Boolean(remote),
                dbus.UInt16(net_index),
                dbus.Dictionary(options, signature="sv"),
                dbus.Array(data, signature="y"),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def publish(
        self,
        element_path: str,
        model_id: int,
        data: bytes,
        *,
        vendor: Optional[int] = None,
        force_segmented: bool = False,
    ) -> None:
        """Publish a message via ``Node1.Publish``."""
        options: dict[str, Any] = {}
        if vendor is not None:
            options["Vendor"] = dbus.UInt16(vendor)
        if force_segmented:
            options["ForceSegmented"] = dbus.Boolean(True)
        try:
            self._iface.Publish(
                dbus.ObjectPath(element_path),
                dbus.UInt16(model_id),
                dbus.Dictionary(options, signature="sv"),
                dbus.Array(data, signature="y"),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def add_net_key(
        self,
        element_path: str,
        destination: int,
        subnet_index: int,
        net_index: int,
        update: bool,
    ) -> None:
        """Add or update a network key on a remote node."""
        try:
            self._iface.AddNetKey(
                dbus.ObjectPath(element_path),
                dbus.UInt16(destination),
                dbus.UInt16(subnet_index),
                dbus.UInt16(net_index),
                dbus.Boolean(update),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def add_app_key(
        self,
        element_path: str,
        destination: int,
        app_index: int,
        net_index: int,
        update: bool,
    ) -> None:
        """Add or update an application key on a remote node."""
        try:
            self._iface.AddAppKey(
                dbus.ObjectPath(element_path),
                dbus.UInt16(destination),
                dbus.UInt16(app_index),
                dbus.UInt16(net_index),
                dbus.Boolean(update),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    # -- Properties --------------------------------------------------------

    def _get_prop(self, name: str) -> Any:
        try:
            return dbus_to_python(self._props.Get(MESH_NODE_IFACE, name))
        except dbus.exceptions.DBusException:
            return None

    @property
    def features(self) -> dict:
        """Node feature flags: Friend, LowPower, Proxy, Relay."""
        return self._get_prop("Features") or {}

    @property
    def beacon(self) -> Optional[bool]:
        return self._get_prop("Beacon")

    @property
    def iv_update(self) -> Optional[bool]:
        return self._get_prop("IvUpdate")

    @property
    def iv_index(self) -> Optional[int]:
        return self._get_prop("IvIndex")

    @property
    def seconds_since_last_heard(self) -> Optional[int]:
        return self._get_prop("SecondsSinceLastHeard")

    @property
    def addresses(self) -> list[int]:
        return self._get_prop("Addresses") or []

    @property
    def sequence_number(self) -> Optional[int]:
        return self._get_prop("SequenceNumber")
