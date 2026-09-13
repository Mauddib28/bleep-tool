#!/usr/bin/env python3
"""
Scripted PAN peer — a controllable PANU client / NAP server for testing BLEEP.

This harness is intentionally **standalone**: it talks directly to BlueZ over
D-Bus (``org.bluez.Network1`` / ``NetworkServer1`` / ``Device1``) and does *not*
import BLEEP. Run it on a *second* Bluetooth host (or a second adapter, e.g.
``hci1``) to exercise the PAN capabilities BLEEP grew in Phase 4:

* ``connect`` — act as a **PANU client** connecting into a NAP (use this to give
  BLEEP's ``classic-pan serve --authorize`` a real inbound BNEP client to
  observe/authorize, and to test BLEEP's ``classic-pan monitor``).
* ``serve``   — act as a **NAP server** so BLEEP's ``classic-pan connect`` /
  ``monitor`` has a real peer to connect to and watch.
* ``monitor`` — subscribe to ``Network1`` ``PropertiesChanged`` for a device
  (a plain cross-check against BLEEP's own event-driven monitor).

Requirements: ``python3-dbus`` and ``python3-gi`` (PyGObject). Root (or the
``bluetooth`` group + a running ``bluetoothd``) is required for Connect/Register.

------------------------------------------------------------------------------
ORDER OF OPERATIONS
------------------------------------------------------------------------------

A. Test BLEEP as NAP host, peer as PANU client (exercises E7 --authorize):
   1. On the BLEEP host: ensure prerequisites, create the bridge, then run
        sudo modprobe bnep
        sudo ip link add pan0 type bridge 2>/dev/null; sudo ip link set pan0 up
        python3 -m bleep classic-pan serve --role nap --bridge pan0 --authorize
      (leave it running; it prints inbound-client authorizations)
   2. Find the BLEEP host's adapter MAC:  bluetoothctl show | grep 'Controller'
   3. On THIS peer host:
        sudo python3 bleep/scripts/pan_peer.py connect <BLEEP_ADAPTER_MAC> \
             --role panu --pair --hold
      → BLEEP logs "inbound BNEP client ... → authorized"; peer prints its bnepX.
   4. Ctrl-C the peer (auto-disconnect), then Ctrl-C BLEEP (auto-unregister).

B. Test BLEEP as PANU client, peer as NAP host (exercises E5 monitor + G8):
   1. On THIS peer host (needs a bridge, like any NAP):
        sudo modprobe bnep
        sudo ip link add pan1 type bridge 2>/dev/null; sudo ip link set pan1 up
        sudo python3 bleep/scripts/pan_peer.py serve --role nap --bridge pan1
      (leave running; peer becomes discoverable/pairable)
   2. Find THIS peer host's adapter MAC (bluetoothctl show).
   3. On the BLEEP host, in one terminal watch state:
        python3 -m bleep classic-pan monitor <PEER_ADAPTER_MAC>
      and in another connect:
        python3 -m bleep classic-pan connect <PEER_ADAPTER_MAC> --role panu --trust
      → BLEEP's monitor prints connected=True + interface; connect verifies via
        the PropertiesChanged signal (G8).
   4. Disconnect / Ctrl-C both sides.

Pairing note: PAN requires a bond+trust on at least one side. Use ``--pair`` on
``connect`` (or pair once with ``bluetoothctl``) before the first connection.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

BLUEZ = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
NETWORK_IFACE = "org.bluez.Network1"
NETSERVER_IFACE = "org.bluez.NetworkServer1"
PROPS_IFACE = "org.freedesktop.DBus.Properties"


def _adapter_path(adapter: str) -> str:
    return f"/{BLUEZ.replace('.', '/')}/{adapter}"  # /org/bluez/hciX


def _device_path(adapter: str, mac: str) -> str:
    return f"{_adapter_path(adapter)}/dev_{mac.upper().replace(':', '_')}"


def _bus() -> dbus.SystemBus:
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    return dbus.SystemBus()


def _props(bus, path, iface):
    return dbus.Interface(bus.get_object(BLUEZ, path), PROPS_IFACE)


def _power_on(bus, adapter: str) -> None:
    props = _props(bus, _adapter_path(adapter), PROPS_IFACE)
    if not bool(props.Get(ADAPTER_IFACE, "Powered")):
        props.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))
        print(f"[peer] powered on {adapter}")


def _ip_addr(iface: str) -> str:
    try:
        out = subprocess.run(
            ["ip", "-brief", "addr", "show", iface],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "(no address yet)"
    except Exception as exc:  # noqa: BLE001
        return f"(ip lookup failed: {exc})"


def cmd_connect(args) -> int:
    bus = _bus()
    _power_on(bus, args.adapter)
    dev_path = _device_path(args.adapter, args.address)
    print(f"[peer] target device path: {dev_path}")

    dev_obj = bus.get_object(BLUEZ, dev_path)
    device = dbus.Interface(dev_obj, DEVICE_IFACE)
    dprops = dbus.Interface(dev_obj, PROPS_IFACE)

    if args.pair:
        try:
            if not bool(dprops.Get(DEVICE_IFACE, "Paired")):
                print("[peer] pairing…")
                device.Pair()
        except dbus.exceptions.DBusException as exc:
            print(f"[peer] pair failed (continuing): {exc}", file=sys.stderr)
        try:
            dprops.Set(DEVICE_IFACE, "Trusted", dbus.Boolean(True))
        except dbus.exceptions.DBusException:
            pass

    net = dbus.Interface(dev_obj, NETWORK_IFACE)
    print(f"[peer] Network1.Connect(role={args.role}) …")
    try:
        iface = str(net.Connect(args.role))
    except dbus.exceptions.DBusException as exc:
        print(f"[peer] Connect failed: {exc.get_dbus_name()}: {exc.get_dbus_message()}",
              file=sys.stderr)
        return 1

    connected = bool(dprops.Get(NETWORK_IFACE, "Connected"))
    print(f"[peer] connected={connected} interface={iface}")
    print(f"[peer] {iface}: {_ip_addr(iface)}")

    if not args.hold:
        _disconnect(net)
        return 0

    print("[peer] holding connection — press Ctrl+C to disconnect")
    loop = GLib.MainLoop()
    try:
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, loop.quit)
    except Exception:  # noqa: BLE001
        pass
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        _disconnect(net)
    return 0


def _disconnect(net) -> None:
    try:
        net.Disconnect()
        print("\n[peer] disconnected")
    except dbus.exceptions.DBusException as exc:
        print(f"[peer] disconnect: {exc.get_dbus_message()}", file=sys.stderr)


def cmd_serve(args) -> int:
    bus = _bus()
    _power_on(bus, args.adapter)

    # Make discoverable/pairable so a fresh peer can bond+connect.
    try:
        aprops = _props(bus, _adapter_path(args.adapter), PROPS_IFACE)
        aprops.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(True))
        aprops.Set(ADAPTER_IFACE, "Pairable", dbus.Boolean(True))
    except dbus.exceptions.DBusException:
        pass

    server = dbus.Interface(
        bus.get_object(BLUEZ, _adapter_path(args.adapter)), NETSERVER_IFACE
    )
    print(f"[peer] NetworkServer1.Register(role={args.role}, bridge={args.bridge}) …")
    try:
        server.Register(args.role, args.bridge)
    except dbus.exceptions.DBusException as exc:
        print(f"[peer] Register failed: {exc.get_dbus_name()}: {exc.get_dbus_message()}",
              file=sys.stderr)
        print("[peer] hint: ensure the bnep module is loaded and the bridge exists:\n"
              "        sudo modprobe bnep\n"
              f"        sudo ip link add {args.bridge} type bridge; "
              f"sudo ip link set {args.bridge} up", file=sys.stderr)
        return 1

    print(f"[peer] hosting {args.role.upper()} on {args.bridge} — Ctrl+C to stop")
    loop = GLib.MainLoop()
    try:
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, loop.quit)
    except Exception:  # noqa: BLE001
        pass
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.Unregister(args.role)
            print(f"\n[peer] unregistered {args.role.upper()}")
        except dbus.exceptions.DBusException as exc:
            print(f"[peer] unregister: {exc.get_dbus_message()}", file=sys.stderr)
    return 0


def cmd_monitor(args) -> int:
    bus = _bus()
    dev_path = _device_path(args.adapter, args.address)
    state = {"Connected": None, "Interface": None, "UUID": None}

    try:
        raw = dict(_props(bus, dev_path, PROPS_IFACE).GetAll(NETWORK_IFACE))
        for k in state:
            if k in raw:
                state[k] = raw[k]
    except dbus.exceptions.DBusException:
        pass
    print(f"[peer][monitor] initial: {dict(state)}")

    def _changed(interface, changed, _invalidated):
        if str(interface) != NETWORK_IFACE:
            return
        upd = {str(k): (bool(v) if str(k) == "Connected" else str(v))
               for k, v in dict(changed).items()}
        state.update(upd)
        print(f"[peer][monitor] changed={upd} state={dict(state)}")

    bus.add_signal_receiver(
        _changed, dbus_interface=PROPS_IFACE, signal_name="PropertiesChanged",
        arg0=NETWORK_IFACE, path=dev_path,
    )
    print(f"[peer][monitor] watching {dev_path} — Ctrl+C to stop")
    loop = GLib.MainLoop()
    try:
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, loop.quit)
    except Exception:  # noqa: BLE001
        pass
    if args.timeout:
        GLib.timeout_add(int(args.timeout * 1000), lambda: (loop.quit(), False)[1])
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pan_peer.py",
        description="Scripted PANU client / NAP server peer for testing BLEEP PAN.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_conn = sub.add_parser("connect", help="Connect as a PANU/GN client into a NAP")
    p_conn.add_argument("address", help="Remote NAP adapter MAC")
    p_conn.add_argument("--role", default="panu", choices=["panu", "nap", "gn"],
                        help="Local PAN role to request (default: panu)")
    p_conn.add_argument("--adapter", default="hci0", help="Local adapter (default: hci0)")
    p_conn.add_argument("--pair", action="store_true", help="Pair + trust before connecting")
    p_conn.add_argument("--hold", action="store_true",
                        help="Keep the connection open until Ctrl+C")
    p_conn.set_defaults(func=cmd_connect)

    p_serve = sub.add_parser("serve", help="Host a NAP/GN so a remote can connect")
    p_serve.add_argument("--role", default="nap", choices=["nap", "gn", "panu"],
                         help="Role to host (default: nap)")
    p_serve.add_argument("--adapter", default="hci0", help="Local adapter (default: hci0)")
    p_serve.add_argument("--bridge", default="pan1", help="Bridge interface (default: pan1)")
    p_serve.set_defaults(func=cmd_serve)

    p_mon = sub.add_parser("monitor", help="Print Network1 PropertiesChanged for a device")
    p_mon.add_argument("address", help="Remote device MAC")
    p_mon.add_argument("--adapter", default="hci0", help="Local adapter (default: hci0)")
    p_mon.add_argument("--timeout", type=float, default=None, help="Stop after N seconds")
    p_mon.set_defaults(func=cmd_monitor)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
