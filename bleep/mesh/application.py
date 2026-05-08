"""D-Bus service implementing ``org.bluez.mesh.Application1``.

The mesh daemon calls methods on this object to signal join completion or
failure.  The application must also export ``org.freedesktop.DBus.ObjectManager``
so the daemon can discover elements.

Reference: ``workDir/bluez/doc/mesh-api.txt`` lines 848–924.
"""

from __future__ import annotations

from typing import Any, Dict, List

import dbus
import dbus.service

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.mesh.constants import (
    BLEEP_MESH_APP_ROOT,
    MESH_APPLICATION_IFACE,
)


class MeshApplication(dbus.service.Object):
    """Skeleton ``Application1`` that the mesh daemon calls back into.

    Subclass and override :meth:`on_join_complete` / :meth:`on_join_failed`
    to react to provisioning outcomes.

    Parameters
    ----------
    bus : dbus.SystemBus
        The bus connection to register on.
    path : str
        Object path for this application root.
    company_id : int
        Bluetooth SIG Company ID (16-bit).
    product_id : int
        Product identifier (16-bit).
    version_id : int
        Version identifier (16-bit).
    """

    def __init__(
        self,
        bus: dbus.SystemBus,
        path: str = BLEEP_MESH_APP_ROOT,
        company_id: int = 0x05F1,
        product_id: int = 0x0001,
        version_id: int = 0x0001,
    ):
        super().__init__(bus, path)
        self._path = path
        self._elements: List[Any] = []
        self._company_id = company_id
        self._product_id = product_id
        self._version_id = version_id
        self._token: int | None = None

    # -- ObjectManager (required by bluetooth-meshd) -----------------------

    @dbus.service.method(
        "org.freedesktop.DBus.ObjectManager",
        out_signature="a{oa{sa{sv}}}",
    )
    def GetManagedObjects(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        objects: Dict[str, Dict[str, Dict[str, Any]]] = {}
        objects[self._path] = {
            MESH_APPLICATION_IFACE: {
                "CompanyID": dbus.UInt16(self._company_id),
                "ProductID": dbus.UInt16(self._product_id),
                "VersionID": dbus.UInt16(self._version_id),
            }
        }
        for element in self._elements:
            objects[element.path] = element.get_properties_dict()
        return objects

    # -- Application1 methods (daemon → app) -------------------------------

    @dbus.service.method(MESH_APPLICATION_IFACE, in_signature="t")
    def JoinComplete(self, token: dbus.UInt64) -> None:
        self._token = int(token)
        print_and_log(f"[mesh-app] JoinComplete token={self._token:#018x}", LOG__GENERAL)
        self.on_join_complete(self._token)

    @dbus.service.method(MESH_APPLICATION_IFACE, in_signature="s")
    def JoinFailed(self, reason: str) -> None:
        print_and_log(f"[mesh-app] JoinFailed reason={reason}", LOG__GENERAL)
        self.on_join_failed(str(reason))

    # -- Hooks for subclasses ----------------------------------------------

    def on_join_complete(self, token: int) -> None:
        """Override to handle successful join."""

    def on_join_failed(self, reason: str) -> None:
        """Override to handle join failure."""

    def add_element(self, element: Any) -> None:
        """Register a :class:`MeshElement` with this application."""
        self._elements.append(element)
