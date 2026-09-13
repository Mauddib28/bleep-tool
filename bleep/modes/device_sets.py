"""CLI mode for ``bleep device-sets`` (BZ-15c).

Lists, connects, disconnects, and inspects coordinated device sets
(e.g. TWS earbuds) using the ``DeviceSet1`` D-Bus interface.
"""

from __future__ import annotations

import json
import sys

import dbus
import dbus.mainloop.glib

from bleep.dbuslayer.device_set import DeviceSet, enumerate_device_sets


def _get_bus() -> dbus.SystemBus:
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    return dbus.SystemBus()


def _adapter_path(args) -> str:
    adapter = getattr(args, "adapter", "hci0")
    return f"/org/bluez/{adapter}"


def handle_device_sets(args) -> int:
    """Dispatch ``bleep device-sets <action>``."""
    action = getattr(args, "ds_action", None)
    if not action:
        print("Usage: bleep device-sets {list,connect,disconnect,info}", file=sys.stderr)
        return 1

    bus = _get_bus()

    if action == "list":
        return _do_list(bus, args)
    elif action == "connect":
        return _do_connect(bus, args)
    elif action == "disconnect":
        return _do_disconnect(bus, args)
    elif action == "info":
        return _do_info(bus, args)
    else:
        print(f"[!] Unknown action: {action}", file=sys.stderr)
        return 1


def _do_list(bus: dbus.SystemBus, args) -> int:
    sets = enumerate_device_sets(bus, _adapter_path(args))
    if not sets:
        print("[*] No device sets found.")
        return 0

    print(f"[*] Found {len(sets)} device set(s):\n")
    for ds in sets:
        info = ds.get_info()
        print(f"  Path:        {info['path']}")
        print(f"  Size:        {info['size']}")
        print(f"  AutoConnect: {info['auto_connect']}")
        print(f"  Members:     {', '.join(info['devices']) or '(none)'}")
        print()
    return 0


def _do_connect(bus: dbus.SystemBus, args) -> int:
    ds = DeviceSet(bus, args.set_path)
    try:
        ds.connect()
        print(f"[+] Connect issued for set {args.set_path}")
        return 0
    except Exception as exc:
        print(f"[!] Connect failed: {exc}", file=sys.stderr)
        return 1


def _do_disconnect(bus: dbus.SystemBus, args) -> int:
    ds = DeviceSet(bus, args.set_path)
    try:
        ds.disconnect()
        print(f"[+] Disconnect issued for set {args.set_path}")
        return 0
    except Exception as exc:
        print(f"[!] Disconnect failed: {exc}", file=sys.stderr)
        return 1


def _do_info(bus: dbus.SystemBus, args) -> int:
    ds = DeviceSet(bus, args.set_path)
    info = ds.get_info()
    print(json.dumps(info, indent=2))
    return 0
