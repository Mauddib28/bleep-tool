"""D-Bus service implementing ``org.bluez.mesh.Element1``.

Elements are the addressable entities within a mesh node.  The daemon calls
``MessageReceived`` / ``DevKeyMessageReceived`` on them to deliver incoming
mesh messages.

Reference: ``workDir/bluez/doc/mesh-api.txt`` lines 927–1064.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import dbus
import dbus.service

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.mesh.constants import MESH_ELEMENT_IFACE


class MeshElement(dbus.service.Object):
    """Skeleton ``Element1`` that receives mesh messages from the daemon.

    Subclass and override :meth:`on_message` / :meth:`on_dev_key_message` for
    application-layer logic.

    Parameters
    ----------
    bus : dbus.SystemBus
        Bus to register on.
    path : str
        Element object path (e.g. ``/bleep/mesh/app/ele00``).
    index : int
        Element index (0-based).
    models : list[tuple[int, dict]]
        SIG model list: ``[(model_id, options_dict), ...]``.
    vendor_models : list[tuple[int, int, dict]]
        Vendor model list: ``[(vendor_id, model_id, options_dict), ...]``.
    location : int, optional
        GATT Namespace Description value.
    """

    def __init__(
        self,
        bus: dbus.SystemBus,
        path: str,
        index: int = 0,
        models: Optional[List[Tuple[int, dict]]] = None,
        vendor_models: Optional[List[Tuple[int, int, dict]]] = None,
        location: Optional[int] = None,
    ):
        super().__init__(bus, path)
        self.path = path
        self._index = index
        self._models = models or []
        self._vendor_models = vendor_models or []
        self._location = location

    def get_properties_dict(self) -> Dict[str, Dict[str, Any]]:
        """Return a dict suitable for ``GetManagedObjects``."""
        props: Dict[str, Any] = {
            "Index": dbus.Byte(self._index),
            "Models": dbus.Array(
                [
                    dbus.Struct(
                        (dbus.UInt16(mid), dbus.Dictionary(opts, signature="sv")),
                        signature="qa{sv}",
                    )
                    for mid, opts in self._models
                ],
                signature="(qa{sv})",
            ),
            "VendorModels": dbus.Array(
                [
                    dbus.Struct(
                        (
                            dbus.UInt16(vid),
                            dbus.UInt16(mid),
                            dbus.Dictionary(opts, signature="sv"),
                        ),
                        signature="qqa{sv}",
                    )
                    for vid, mid, opts in self._vendor_models
                ],
                signature="(qqa{sv})",
            ),
        }
        if self._location is not None:
            props["Location"] = dbus.UInt16(self._location)
        return {MESH_ELEMENT_IFACE: props}

    # -- Element1 methods (daemon → element) -------------------------------

    @dbus.service.method(MESH_ELEMENT_IFACE, in_signature="qqvay")
    def MessageReceived(
        self,
        source: dbus.UInt16,
        key_index: dbus.UInt16,
        destination: Any,
        data: dbus.Array,
    ) -> None:
        src = int(source)
        ki = int(key_index)
        payload = bytes(data)
        print_and_log(
            f"[mesh-ele] MessageReceived src=0x{src:04x} key={ki} len={len(payload)}",
            LOG__DEBUG,
        )
        self.on_message(src, ki, destination, payload)

    @dbus.service.method(MESH_ELEMENT_IFACE, in_signature="qbqay")
    def DevKeyMessageReceived(
        self,
        source: dbus.UInt16,
        remote: dbus.Boolean,
        net_index: dbus.UInt16,
        data: dbus.Array,
    ) -> None:
        payload = bytes(data)
        self.on_dev_key_message(int(source), bool(remote), int(net_index), payload)

    @dbus.service.method(MESH_ELEMENT_IFACE, in_signature="qa{sv}")
    def UpdateModelConfiguration(
        self,
        model_id: dbus.UInt16,
        config: dbus.Dictionary,
    ) -> None:
        self.on_model_config_update(int(model_id), dict(config))

    # -- Hooks for subclasses ----------------------------------------------

    def on_message(
        self, source: int, key_index: int, destination: Any, data: bytes,
    ) -> None:
        """Override to handle incoming mesh messages."""

    def on_dev_key_message(
        self, source: int, remote: bool, net_index: int, data: bytes,
    ) -> None:
        """Override to handle incoming device-key messages."""

    def on_model_config_update(self, model_id: int, config: dict) -> None:
        """Override to handle model configuration updates from the daemon."""
