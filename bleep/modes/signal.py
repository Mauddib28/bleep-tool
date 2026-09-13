"""BLEEP Signal mode – simple notification listener for a given characteristic.

Legacy *Modules/signal_mode.py* distilled into a minimal, CLI-driven helper.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import dbus
from gi.repository import GLib

if TYPE_CHECKING:
    from bleep.core.output import OutputContext

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.dbuslayer.signals import system_dbus__bluez_signals as _Signals
from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum

__all__ = ["run"]


def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bleep-signal", add_help=False)
    p.add_argument("mac", metavar="MAC", help="Target BLE MAC address")
    p.add_argument("char", metavar="CHAR", help="Characteristic UUID or char00xx handle")
    p.add_argument("--time", type=int, default=30, help="Listen duration (s)")
    p.add_argument("--help", "-h", action="help")
    return p


def run(args: argparse.Namespace, output: OutputContext | None = None, device=None) -> int:
    """Execute signal mode with parsed args and optional OutputContext.

    ``device`` lets a caller (e.g. the debug shell's ``signal`` verb) pass an
    already-connected/enumerated device so the listener reuses the live session
    instead of reconnecting. When ``None`` (the CLI path) the target MAC is
    connected and enumerated here as before.
    """
    from bleep.core.output import OutputContext
    from bleep.core.log import set_output_mode

    if output is None:
        output = OutputContext()

    set_output_mode(output.mode)

    target = args.mac.upper()
    if device is None:
        device, _mapping, _m1, _m2 = _connect_enum(target)

    sigs = _Signals()

    try:
        from bleep.core import observations as _obs
    except Exception:
        _obs = None  # type: ignore[assignment]

    def _notify_cb(char_path, value: bytes):  # type: ignore
        if output.is_json or output.is_quiet:
            output.emit_result({
                "ts": datetime.now(timezone.utc).isoformat(),
                "uuid": dev_uuid,
                "char_path": char_path,
                "value_hex": value.hex(),
                "length": len(value),
            })
        else:
            print_and_log(f"[NOTIFY] {char_path}: {value.hex()}", LOG__GENERAL)
        if _obs and dev_uuid:
            try:
                _obs.insert_char_history(target, "", dev_uuid, value, "notification")
            except Exception:
                pass

    dev_uuid = None
    from bleep.ble_ops.common.conversion import handle_hex_to_int

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
        dev_uuid = args.char.upper()

    if not dev_uuid:
        print_and_log("[-] Characteristic not found", LOG__GENERAL)
        return 1

    sigs.capture_and_act__emittion__gatt_characteristic(device, dev_uuid, _notify_cb)

    output.emit_progress(f"[*] Listening for notifications ({args.time} s)… Ctrl+C to stop")

    loop = GLib.MainLoop()

    def _sigint(_s, _f):
        loop.quit()

    signal.signal(signal.SIGINT, _sigint)

    GLib.timeout_add_seconds(args.time, loop.quit)
    loop.run()

    output.emit_progress("[*] Done")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run signal mode (backward-compatible wrapper)."""
    argv = argv or sys.argv[1:]
    args = _arg_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main()) 