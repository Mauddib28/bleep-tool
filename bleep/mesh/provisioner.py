"""D-Bus service implementing ``org.bluez.mesh.Provisioner1``.

The daemon calls methods on this object to deliver scan results and request
provisioning data.  The provisioner is registered alongside the Application1
object and discovered via ObjectManager.

Reference: ``workDir/bluez/doc/mesh-api.txt`` lines 1099–1238.
"""

from __future__ import annotations

from typing import Any, Tuple

import dbus
import dbus.service

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.mesh.constants import MESH_PROVISIONER_IFACE


class MeshProvisioner(dbus.service.Object):
    """Skeleton ``Provisioner1`` for receiving scan results and provisioning.

    Subclass and override the ``on_*`` hooks for application logic.
    """

    def __init__(self, bus: dbus.SystemBus, path: str):
        super().__init__(bus, path)
        self.path = path

    # -- Provisioner1 methods (daemon → provisioner) -----------------------

    @dbus.service.method(MESH_PROVISIONER_IFACE, in_signature="naya{sv}")
    def ScanResult(
        self,
        rssi: dbus.Int16,
        data: dbus.Array,
        options: dbus.Dictionary,
    ) -> None:
        self.on_scan_result(int(rssi), bytes(data), dict(options))

    @dbus.service.method(
        MESH_PROVISIONER_IFACE, in_signature="y", out_signature="qq",
    )
    def RequestProvData(self, count: dbus.Byte) -> Tuple[dbus.UInt16, dbus.UInt16]:
        net_index, unicast = self.on_request_prov_data(int(count))
        return dbus.UInt16(net_index), dbus.UInt16(unicast)

    @dbus.service.method(
        MESH_PROVISIONER_IFACE, in_signature="qy", out_signature="q",
    )
    def RequestReprovData(
        self, original: dbus.UInt16, count: dbus.Byte,
    ) -> dbus.UInt16:
        unicast = self.on_request_reprov_data(int(original), int(count))
        return dbus.UInt16(unicast)

    @dbus.service.method(MESH_PROVISIONER_IFACE, in_signature="ayqy")
    def AddNodeComplete(
        self, uuid: dbus.Array, unicast: dbus.UInt16, count: dbus.Byte,
    ) -> None:
        print_and_log(
            f"[mesh-prov] AddNodeComplete unicast=0x{int(unicast):04x}",
            LOG__GENERAL,
        )
        self.on_add_node_complete(bytes(uuid), int(unicast), int(count))

    @dbus.service.method(MESH_PROVISIONER_IFACE, in_signature="qyqy")
    def ReprovComplete(
        self,
        original: dbus.UInt16,
        nppi: dbus.Byte,
        unicast: dbus.UInt16,
        count: dbus.Byte,
    ) -> None:
        self.on_reprov_complete(int(original), int(nppi), int(unicast), int(count))

    @dbus.service.method(MESH_PROVISIONER_IFACE, in_signature="ays")
    def AddNodeFailed(self, uuid: dbus.Array, reason: str) -> None:
        print_and_log(
            f"[mesh-prov] AddNodeFailed uuid={bytes(uuid).hex()} reason={reason}",
            LOG__GENERAL,
        )
        self.on_add_node_failed(bytes(uuid), str(reason))

    @dbus.service.method(MESH_PROVISIONER_IFACE, in_signature="qs")
    def ReprovFailed(self, unicast: dbus.UInt16, reason: str) -> None:
        self.on_reprov_failed(int(unicast), str(reason))

    # -- Hooks for subclasses ----------------------------------------------

    def on_scan_result(self, rssi: int, data: bytes, options: dict) -> None:
        """Override to process unprovisioned device scan results."""

    def on_request_prov_data(self, count: int) -> Tuple[int, int]:
        """Override to return ``(net_index, unicast)`` for a new node.

        Must be implemented by subclass — there is no sensible default.
        """
        raise NotImplementedError("Subclass must implement on_request_prov_data")

    def on_request_reprov_data(self, original: int, count: int) -> int:
        """Override to return a new unicast address for re-provisioning."""
        raise NotImplementedError("Subclass must implement on_request_reprov_data")

    def on_add_node_complete(self, uuid: bytes, unicast: int, count: int) -> None:
        """Override to handle successful provisioning."""

    def on_reprov_complete(
        self, original: int, nppi: int, unicast: int, count: int,
    ) -> None:
        """Override to handle successful re-provisioning."""

    def on_add_node_failed(self, uuid: bytes, reason: str) -> None:
        """Override to handle provisioning failure."""

    def on_reprov_failed(self, unicast: int, reason: str) -> None:
        """Override to handle re-provisioning failure."""
