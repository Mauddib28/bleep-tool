#!/usr/bin/python3
"""Send a single Bluetooth Mesh Proxy Solicitation PDU via BlueZ.

This helper attaches to BlueZ's Mesh Network1/Node1 API and transmits a Proxy
Solicitation (opcode 0x00).  It requires BlueZ ≥5.56 built with mesh support
and the ``bluetooth-meshd`` service running.

The API signatures match ``workDir/bluez/doc/mesh-api.txt``:
- ``Network1.Attach(app_root, token)`` → ``(node_path, configuration)``
- ``Node1.Send(element_path, destination, key_index, options, data)``

Example
-------
>>> from bleep.mesh.proxy_solicitation import send_proxy_solicitation
>>> send_proxy_solicitation(app_root="/bleep/mesh/app", token=0)
"""
from __future__ import annotations

import dbus
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.mesh.constants import (
    BLEEP_MESH_APP_ROOT,
    BLEEP_MESH_ELEMENT_PREFIX,
    MESH_NODE_IFACE,
    MESH_ROOT_PATH,
    MESH_NETWORK_IFACE,
    MESH_SERVICE,
)
from bleep.mesh.errors import MeshError, map_mesh_dbus_error


class MeshSolicitationError(MeshError):
    """Raised when sending the proxy solicitation fails."""


def _attach(
    bus: dbus.SystemBus,
    app_root: str,
    token: int,
) -> tuple[str, dbus.Interface]:
    """Attach to the mesh daemon and return ``(node_path, node_iface)``.

    Calls ``Network1.Attach(app_root, token)`` on ``/org/bluez/mesh``.
    """
    obj = bus.get_object(MESH_SERVICE, MESH_ROOT_PATH)
    net = dbus.Interface(obj, MESH_NETWORK_IFACE)

    try:
        node_path, _config = net.Attach(
            dbus.ObjectPath(app_root),
            dbus.UInt64(token),
        )
    except dbus.exceptions.DBusException as exc:
        raise MeshSolicitationError(
            f"Attach() failed: {exc.get_dbus_message()}", dbus_name=exc.get_dbus_name(),
        ) from exc

    node_obj = bus.get_object(MESH_SERVICE, str(node_path))
    node_iface = dbus.Interface(node_obj, MESH_NODE_IFACE)
    return str(node_path), node_iface


def send_proxy_solicitation(
    app_root: str = BLEEP_MESH_APP_ROOT,
    token: int = 0,
    net_key_index: int = 0,
    element_path: str | None = None,
) -> None:
    """Send a Mesh Proxy Solicitation PDU.

    Parameters
    ----------
    app_root : str
        Application root path previously registered via ``Join`` or
        ``CreateNetwork``.
    token : int
        Token returned by ``JoinComplete`` or ``CreateNetwork``.
    net_key_index : int
        Network Key Index to use (default 0 — primary NetKey).
    element_path : str, optional
        Element path to send from.  Defaults to ``<BLEEP_MESH_ELEMENT_PREFIX>00``.
    """
    bus = dbus.SystemBus()
    ele = element_path or f"{BLEEP_MESH_ELEMENT_PREFIX}00"

    try:
        node_path, node = _attach(bus, app_root, token)
        print_and_log(f"[*] Attached to mesh node {node_path}", LOG__DEBUG)

        pdu = bytes([0x00, 0x00])
        dst = 0x0000

        node.Send(
            dbus.ObjectPath(ele),
            dbus.UInt16(dst),
            dbus.UInt16(net_key_index),
            dbus.Dictionary({}, signature="sv"),
            dbus.Array(pdu, signature="y"),
        )
        print_and_log("[+] Mesh Proxy Solicitation sent", LOG__GENERAL)
    except dbus.exceptions.DBusException as exc:
        raise MeshSolicitationError(
            exc.get_dbus_message() or str(exc),
            dbus_name=exc.get_dbus_name(),
        ) from exc