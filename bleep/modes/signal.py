"""BLEEP Signal mode – simple notification listener for a given characteristic.

Legacy *Modules/signal_mode.py* distilled into a minimal, CLI-driven helper.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time

import dbus
from gi.repository import GLib

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.dbuslayer.signals import system_dbus__bluez_signals as _Signals
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum


def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bleep-signal", add_help=False)
    p.add_argument("mac", metavar="MAC", help="Target BLE MAC address")
    p.add_argument("char", metavar="CHAR", help="Characteristic UUID or char00xx handle")
    p.add_argument("--time", type=int, default=30, help="Listen duration (s)")
    p.add_argument("--help", "-h", action="help")
    return p


def main(argv: list[str] | None = None):
    argv = argv or sys.argv[1:]
    args = _arg_parser().parse_args(argv)

    target = args.mac.upper()
    device, _mapping, _m1, _m2 = _connect_enum(target)

    sigs = _Signals()

    # Connect callback
    def _notify_cb(uuid, value: bytes):  # type: ignore
        print_and_log(f"[NOTIFY] {uuid}: {value.hex()}", LOG__GENERAL)

    dev_uuid = None
    from bleep.ble_ops.conversion import handle_hex_to_int

    if args.char.lower().startswith("char"):
        # User supplied *char00xx* notation → extract hex suffix
        handle = int(args.char[4:], 16)
        dev_uuid = device.ble_device__mapping.get(handle)
    elif args.char.lower().startswith("0x"):
        # Direct hex handle (e.g. 0x0029)
        handle = handle_hex_to_int(args.char)
        dev_uuid = device.ble_device__mapping.get(handle)
    elif args.char.isdigit():
        # Decimal handle string
        dev_uuid = device.ble_device__mapping.get(int(args.char))
    else:
        # Assume full UUID supplied
        dev_uuid = args.char.lower()

    if not dev_uuid:
        print_and_log("[-] Characteristic not found", LOG__GENERAL)
        return 1

    sigs.capture_and_act__emittion__gatt_characteristic(device, dev_uuid, _notify_cb)

    print_and_log(f"[*] Listening for notifications ({args.time} s)… Ctrl+C to stop", LOG__GENERAL)

    loop = GLib.MainLoop()

    def _sigint(_s, _f):
        loop.quit()

    signal.signal(signal.SIGINT, _sigint)

    GLib.timeout_add_seconds(args.time, loop.quit)
    loop.run()

    print_and_log("[*] Done", LOG__GENERAL)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main()) 