#!/usr/bin/python3
"""Send a single Bluetooth Mesh Proxy Solicitation PDU via BlueZ.

This helper is intentionally minimal – it attaches to BlueZ's Mesh Management
API and transmits a Proxy Solicitation (opcode 0x00).  It requires BlueZ ≥5.56
built with mesh support and the *mesh* service running.

Example
-------
>>> from bleep.mesh.proxy_solicitation import send_proxy_solicitation
>>> send_proxy_solicitation("hci0")
"""
from __future__ import annotations

import dbus
from typing import Optional
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL

BLUEZ_MESH_SERVICE = "org.bluez.mesh"
MESH_MANAGEMENT_IFACE = "org.bluez.mesh.Management1"
MESH_NODE_IFACE = "org.bluez.mesh.Node1"


class MeshSolicitationError(RuntimeError):
    """Raised when sending the proxy solicitation fails."""


def _attach(bus: dbus.SystemBus, adapter: str) -> tuple[str, dbus.Interface]:
    """Attach to the mesh daemon on *adapter*.

    Returns (node_path, node_iface) where *node_iface* is a proxy implementing
    ``org.bluez.mesh.Node1``.
    """
    mngr = bus.get_object(BLUEZ_MESH_SERVICE, f"/org/bluez/{adapter}")
    mgmt = dbus.Interface(mngr, MESH_MANAGEMENT_IFACE)

    # Attach() returns the object path to the Node1 instance
    try:
        node_path = mgmt.Attach()
    except dbus.exceptions.DBusException as e:
        raise MeshSolicitationError(f"Attach() failed: {e.get_dbus_message()}")

    node_obj = bus.get_object(BLUEZ_MESH_SERVICE, node_path)
    node_iface = dbus.Interface(node_obj, MESH_NODE_IFACE)
    return node_path, node_iface


def send_proxy_solicitation(adapter: str = "hci0", net_key_index: int = 0) -> None:
    """Send a Mesh Proxy Solicitation PDU on *adapter*.

    Parameters
    ----------
    adapter : str, optional
        HCI adapter name (e.g. "hci0"), by default "hci0".
    net_key_index : int, optional
        Network Key Index to use (default 0 – primary NetKey).
    """
    bus = dbus.SystemBus()

    try:
        node_path, node = _attach(bus, adapter)
        print_and_log(f"[*] Attached to mesh node {node_path}", LOG__DEBUG)

        # Proxy Solicitation: 0x00 (Proxy Config opcode) + 0x00 (Solicitation PDU)
        pdu = bytes([0x00, 0x00])
        dst = 0x0000  # Mesh spec: send to provisioner (All Proxies) or 0x0000 when unknown
        ttl = 0x00    # Let stack choose default

        node.Send(dbus.UInt16(dst), dbus.UInt16(net_key_index), dbus.Byte(ttl), pdu)
        print_and_log("[+] Mesh Proxy Solicitation sent", LOG__GENERAL)
    except dbus.exceptions.DBusException as e:
        raise MeshSolicitationError(e.get_dbus_message()) 