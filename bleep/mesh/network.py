"""Client wrapper for ``org.bluez.mesh.Network1``.

The Network1 interface lives at ``/org/bluez/mesh`` and manages the lifecycle
of mesh nodes — join, attach, leave, create, and import.

Reference: ``workDir/bluez/doc/mesh-api.txt`` lines 4–224.
"""

from __future__ import annotations

from typing import Any, Tuple

import dbus

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.mesh.constants import MESH_ROOT_PATH, MESH_NETWORK_IFACE, MESH_SERVICE
from bleep.mesh.errors import MeshError, map_mesh_dbus_error


class MeshNetwork:
    """Proxy for the ``org.bluez.mesh.Network1`` interface.

    Parameters
    ----------
    bus : dbus.SystemBus, optional
        Existing bus connection.  A new SystemBus is created if *None*.
    """

    def __init__(self, bus: dbus.SystemBus | None = None):
        self._bus = bus or dbus.SystemBus()
        obj = self._bus.get_object(MESH_SERVICE, MESH_ROOT_PATH)
        self._iface = dbus.Interface(obj, MESH_NETWORK_IFACE)

    def join(self, app_root: str, uuid: bytes) -> None:
        """Request to join a mesh network.

        The daemon will call ``Application1.JoinComplete(token)`` on success or
        ``Application1.JoinFailed(reason)`` on failure.

        Parameters
        ----------
        app_root : str
            D-Bus object path of the application root (exports ObjectManager).
        uuid : bytes
            16-byte device UUID.
        """
        try:
            self._iface.Join(
                dbus.ObjectPath(app_root),
                dbus.Array(uuid, signature="y"),
            )
            print_and_log(f"[mesh] Join requested (app={app_root})", LOG__GENERAL)
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def cancel(self) -> None:
        """Cancel an outstanding Join request."""
        try:
            self._iface.Cancel()
            print_and_log("[mesh] Join cancelled", LOG__GENERAL)
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def attach(self, app_root: str, token: int) -> Tuple[str, list]:
        """Attach to an already-provisioned node.

        Returns
        -------
        tuple[str, list]
            ``(node_path, configuration)`` where *configuration* is a list of
            element/model descriptors returned by the daemon.
        """
        try:
            node_path, config = self._iface.Attach(
                dbus.ObjectPath(app_root),
                dbus.UInt64(token),
            )
            print_and_log(f"[mesh] Attached to {node_path}", LOG__GENERAL)
            return str(node_path), list(config)
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def leave(self, token: int) -> None:
        """Remove the node identified by *token* from the local daemon."""
        try:
            self._iface.Leave(dbus.UInt64(token))
            print_and_log("[mesh] Left mesh network", LOG__GENERAL)
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def create_network(self, app_root: str, uuid: bytes) -> None:
        """Create a new mesh network and become the primary provisioner.

        Parameters
        ----------
        app_root : str
            Application root path (exports ObjectManager).
        uuid : bytes
            16-byte device UUID for this node.
        """
        try:
            self._iface.CreateNetwork(
                dbus.ObjectPath(app_root),
                dbus.Array(uuid, signature="y"),
            )
            print_and_log(f"[mesh] CreateNetwork requested (app={app_root})", LOG__GENERAL)
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def import_node(
        self,
        app_root: str,
        uuid: bytes,
        dev_key: bytes,
        net_key: bytes,
        net_index: int,
        flags: dict[str, Any],
        iv_index: int,
        unicast: int,
    ) -> None:
        """Import an externally-provisioned node into the local mesh daemon."""
        try:
            self._iface.Import(
                dbus.ObjectPath(app_root),
                dbus.Array(uuid, signature="y"),
                dbus.Array(dev_key, signature="y"),
                dbus.Array(net_key, signature="y"),
                dbus.UInt16(net_index),
                dbus.Dictionary(flags, signature="sv"),
                dbus.UInt32(iv_index),
                dbus.UInt16(unicast),
            )
            print_and_log(
                f"[mesh] Import node unicast=0x{unicast:04x}", LOG__GENERAL,
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc
