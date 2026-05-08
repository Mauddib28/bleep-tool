"""Client wrapper for ``org.bluez.mesh.Management1``.

The Management1 interface shares the same object path as Node1
(``/org/bluez/mesh/node<uuid>``) and exposes provisioning operations
and key database management.

Reference: ``workDir/bluez/doc/mesh-api.txt`` lines 465–847.
"""

from __future__ import annotations

from typing import Any, Optional

import dbus

from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.mesh.constants import MESH_MANAGEMENT_IFACE, MESH_SERVICE
from bleep.mesh.errors import map_mesh_dbus_error


class MeshManagement:
    """Proxy for the ``org.bluez.mesh.Management1`` interface.

    Parameters
    ----------
    node_path : str
        D-Bus path of the node, e.g. ``/org/bluez/mesh/node<uuid>``.
    bus : dbus.SystemBus, optional
        Existing bus connection.
    """

    def __init__(self, node_path: str, bus: dbus.SystemBus | None = None):
        self._bus = bus or dbus.SystemBus()
        self._path = node_path
        obj = self._bus.get_object(MESH_SERVICE, node_path)
        self._iface = dbus.Interface(obj, MESH_MANAGEMENT_IFACE)

    # -- Scan / provisioning -----------------------------------------------

    def unprovisioned_scan(self, *, seconds: int = 0) -> None:
        """Start scanning for unprovisioned mesh devices.

        Results are delivered via ``Provisioner1.ScanResult`` callbacks.

        Parameters
        ----------
        seconds : int
            Scan duration in seconds (0 = indefinite until Cancel).
        """
        options: dict[str, Any] = {}
        if seconds:
            options["Seconds"] = dbus.UInt16(seconds)
        try:
            self._iface.UnprovisionedScan(
                dbus.Dictionary(options, signature="sv"),
            )
            print_and_log(
                f"[mesh-mgmt] Unprovisioned scan started (duration={seconds}s)",
                LOG__GENERAL,
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def unprovisioned_scan_cancel(self) -> None:
        """Stop an active unprovisioned scan."""
        try:
            self._iface.UnprovisionedScanCancel()
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def add_node(self, uuid: bytes, *, options: Optional[dict] = None) -> None:
        """Begin provisioning a remote device identified by *uuid*."""
        opts = dbus.Dictionary(options or {}, signature="sv")
        try:
            self._iface.AddNode(dbus.Array(uuid, signature="y"), opts)
            print_and_log(
                f"[mesh-mgmt] AddNode requested uuid={uuid.hex()}", LOG__GENERAL,
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    # -- Subnet management -------------------------------------------------

    def create_subnet(self, net_index: int) -> None:
        try:
            self._iface.CreateSubnet(dbus.UInt16(net_index))
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def import_subnet(self, net_index: int, net_key: bytes) -> None:
        try:
            self._iface.ImportSubnet(
                dbus.UInt16(net_index),
                dbus.Array(net_key, signature="y"),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def update_subnet(self, net_index: int) -> None:
        try:
            self._iface.UpdateSubnet(dbus.UInt16(net_index))
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def delete_subnet(self, net_index: int) -> None:
        try:
            self._iface.DeleteSubnet(dbus.UInt16(net_index))
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def set_key_phase(self, net_index: int, phase: int) -> None:
        try:
            self._iface.SetKeyPhase(dbus.UInt16(net_index), dbus.Byte(phase))
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    # -- AppKey management -------------------------------------------------

    def create_app_key(self, net_index: int, app_index: int) -> None:
        try:
            self._iface.CreateAppKey(
                dbus.UInt16(net_index), dbus.UInt16(app_index),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def import_app_key(
        self, net_index: int, app_index: int, app_key: bytes,
    ) -> None:
        try:
            self._iface.ImportAppKey(
                dbus.UInt16(net_index),
                dbus.UInt16(app_index),
                dbus.Array(app_key, signature="y"),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def update_app_key(self, app_index: int) -> None:
        try:
            self._iface.UpdateAppKey(dbus.UInt16(app_index))
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def delete_app_key(self, app_index: int) -> None:
        try:
            self._iface.DeleteAppKey(dbus.UInt16(app_index))
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    # -- Remote node management --------------------------------------------

    def import_remote_node(self, primary: int, count: int, device_key: bytes) -> None:
        try:
            self._iface.ImportRemoteNode(
                dbus.UInt16(primary),
                dbus.Byte(count),
                dbus.Array(device_key, signature="y"),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    def delete_remote_node(self, primary: int, count: int) -> None:
        try:
            self._iface.DeleteRemoteNode(
                dbus.UInt16(primary), dbus.Byte(count),
            )
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc

    # -- Export ------------------------------------------------------------

    def export_keys(self) -> dict:
        """Export the complete key database as a dictionary."""
        try:
            result = self._iface.ExportKeys()
            return dbus_to_python(result)
        except dbus.exceptions.DBusException as exc:
            raise map_mesh_dbus_error(exc) from exc
