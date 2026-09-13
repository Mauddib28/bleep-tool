"""CLI mode for ``bleep mesh`` (BZ-24c).

Provides commands for mesh network join, device provisioning, and
re-provisioning via the ``bluetooth-meshd`` daemon.
"""

from __future__ import annotations

import sys

import dbus
import dbus.mainloop.glib

__all__ = ["handle_mesh"]


def _get_bus() -> dbus.SystemBus:
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    return dbus.SystemBus()


def handle_mesh(args) -> int:
    """Dispatch ``bleep mesh <action>``."""
    action = getattr(args, "mesh_action", None)
    if not action:
        print("Usage: bleep mesh {join,provision,reprovision}", file=sys.stderr)
        return 1

    if action == "join":
        return _do_join(args)
    elif action == "provision":
        return _do_provision(args)
    elif action == "reprovision":
        return _do_reprovision(args)
    else:
        print(f"[!] Unknown mesh action: {action}", file=sys.stderr)
        return 1


def _do_join(args) -> int:
    try:
        uuid_bytes = bytes.fromhex(args.uuid)
        if len(uuid_bytes) != 16:
            print("[!] UUID must be 32 hex characters (16 bytes).", file=sys.stderr)
            return 1
    except ValueError:
        print("[!] Invalid UUID hex string.", file=sys.stderr)
        return 1

    bus = _get_bus()

    from bleep.mesh.interactive_provision_agent import (
        InteractiveProvisionAgent,
        create_mesh_io_handler,
    )
    from bleep.mesh.constants import BLEEP_MESH_AGENT_PATH

    io_handler = create_mesh_io_handler(args.io)
    agent = InteractiveProvisionAgent(
        bus, BLEEP_MESH_AGENT_PATH, io_handler=io_handler,
    )

    from bleep.mesh.network import MeshNetwork
    from bleep.mesh.constants import MESH_ROOT_PATH

    net = MeshNetwork(bus=bus)
    try:
        print(f"[*] Joining mesh network with UUID {args.uuid}...")
        token = net.join(BLEEP_MESH_AGENT_PATH, uuid_bytes)
        print(f"[+] Join initiated, token: {token}")
        return 0
    except Exception as exc:
        print(f"[!] Mesh join failed: {exc}", file=sys.stderr)
        return 1


def _do_provision(args) -> int:
    try:
        uuid_bytes = bytes.fromhex(args.uuid)
        if len(uuid_bytes) != 16:
            print("[!] UUID must be 32 hex characters (16 bytes).", file=sys.stderr)
            return 1
    except ValueError:
        print("[!] Invalid UUID hex string.", file=sys.stderr)
        return 1

    bus = _get_bus()

    from bleep.mesh.management import MeshManagement

    print(f"[*] Provisioning device with UUID {args.uuid}...")
    print("[*] Use 'bleep mesh join' first to establish local node.")
    print("[!] Provisioning requires an active mesh node — see mesh-api.txt.", file=sys.stderr)
    return 1


def _do_reprovision(args) -> int:
    bus = _get_bus()

    from bleep.mesh.management import MeshManagement

    try:
        mgmt = MeshManagement(args.node_path, bus=bus)
        print(f"[*] Re-provisioning node at unicast 0x{args.unicast:04x}...")
        mgmt.reprovision(args.unicast)
        print(f"[+] Reprovision request sent for unicast 0x{args.unicast:04x}")
        return 0
    except Exception as exc:
        print(f"[!] Reprovision failed: {exc}", file=sys.stderr)
        return 1
