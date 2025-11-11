from __future__ import annotations

"""Simple text-based interactive mode replacing legacy user_mode.

Current capabilities:
• scan – list nearby BLE devices (LE) with address & name
• connect <MAC> – connect + enumerate, then allow characteristic read/write via ble_ctf helper shortcuts
• quit – exit

The mode intentionally avoids complex menus; advanced features will be added
as needed.
"""

import shlex
from typing import List

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.ble_ops.scan import passive_scan
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
from bleep.ble_ops import ctf as _ctf

_PROMPT = "BLEEP> "


def _cmd_scan(_: List[str]):
    print_and_log("[*] Scanning…", LOG__GENERAL)
    passive_scan(timeout=10)


def _cmd_connect(args: List[str]):
    if not args:
        print("Usage: connect <MAC>")
        return
    mac = args[0]
    try:
        dev, _map, *_ = _connect_enum(mac)
        print(f"[+] Connected to {mac}. You can now read/write using read <UUID|charXXXX> / write <UUID|charXXXX> <value>")
        _repl_device(dev, _map)
    except Exception as exc:
        print(f"[-] Connect failed: {exc}")


def _cmd_uuid(args: List[str]):
    """Translate UUID(s) to human-readable format."""
    if not args:
        print("Usage: uuid <UUID> [UUID2 ...]")
        print("Example: uuid 180a")
        print("Example: uuid 0000180a-0000-1000-8000-00805f9b34fb")
        return
    
    from bleep.bt_ref.uuid_translator import translate_uuid
    from bleep.modes.uuid_translate import format_text_output
    
    for uuid_input in args:
        try:
            result = translate_uuid(uuid_input)
            output = format_text_output(result, verbose=False)
            print(output)
            if len(args) > 1 and uuid_input != args[-1]:
                print()  # Add spacing between multiple UUIDs
        except Exception as exc:
            print(f"[-] Error translating UUID '{uuid_input}': {exc}")


def _repl_device(dev, mapping):
    while True:
        try:
            line = input(f"{dev.mac_address}> ")
        except (EOFError, KeyboardInterrupt):
            print()
            dev.disconnect()
            break
        parts = shlex.split(line)
        if not parts:
            continue
        cmd, *rest = parts
        if cmd in {"quit", "exit"}:
            dev.disconnect()
            break
        elif cmd == "read":
            if not rest:
                print("read <UUID|charXXXX>")
                continue
            try:
                val = _ctf.ble_ctf__read_characteristic(rest[0], dev, mapping)
                print(f"Value: {val}")
            except Exception as exc:
                print(f"Read failed: {exc}")
        elif cmd == "write":
            if len(rest) < 2:
                print("write <UUID|charXXXX> <value>")
                continue
            try:
                _ctf._ble_ctf__write_characteristic(rest[1], rest[0], dev)  # type: ignore
            except Exception as exc:
                print(f"Write failed: {exc}")
        else:
            print("Unknown device cmd")


_CMDS = {
    "scan": _cmd_scan,
    "connect": _cmd_connect,
    "uuid": _cmd_uuid,
}


def main():  # entry point for CLI
    print("[*] BLEEP interactive mode – type 'help' for commands, 'quit' to exit")
    while True:
        try:
            line = input(_PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        parts = shlex.split(line)
        if not parts:
            continue
        cmd, *rest = parts
        if cmd in {"quit", "exit"}:
            break
        if cmd == "help":
            print("Available commands: scan | connect <MAC> | uuid <UUID> | quit")
            continue
        handler = _CMDS.get(cmd)
        if not handler:
            print("Unknown command – type 'help'")
            continue
        handler(rest)


if __name__ == "__main__":
    main() 