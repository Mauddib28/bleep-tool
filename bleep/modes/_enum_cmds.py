"""Enumeration command helpers for BLEEP Debug shell (Patch D-3 / P1).

This module factors out the enumeration dispatcher so we can import the four
CLI handlers into *modes/debug.py* without inflating its size further.
"""
from __future__ import annotations

from typing import List

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.ble_ops.connect import (
    connect_and_enumerate__bluetooth__low_energy as _connect_enum,
)
from bleep.ble_ops.enum_helpers import (
    multi_read_all,
    small_write_probe,
    build_payload_iterator,
    brute_write_range,
)

__all__ = [
    "_cmd_enum",
    "_cmd_enumn",
    "_cmd_enump",
    "_cmd_enumb",
]


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _enum_common(shell_globals: dict, variant: str, args: List[str]) -> None:  # noqa: C901 – accept complexity
    """Shared enumeration handler.

    *shell_globals* – pass ``globals()`` from caller so we can update the
    session state without circular imports.
    """
    _current_device = shell_globals.get("_current_device")
    _current_mapping = shell_globals.get("_current_mapping")

    if not args:
        usage = {
            "passive": "Usage: enum <MAC>",
            "naggy": "Usage: enumn <MAC>",
            "pokey": "Usage: enump <MAC> [rounds]",
            "brute": "Usage: enumb <MAC> <CHAR_UUID>",
        }
        print(usage[variant])
        return

    mac = args[0].strip().upper()
    extra = args[1:]

    try:
        device, mapping, mine_map, perm_map = _connect_enum(mac)
    except Exception as exc:
        print_and_log(f"[-] Enumeration connect failed: {exc}", LOG__DEBUG)
        return

    try:
        if variant == "naggy":
            multi_read_all(device, mapping=mapping, rounds=3)
        elif variant == "pokey":
            rounds = int(extra[0]) if extra else 3
            for _ in range(rounds):
                small_write_probe(device, mapping, verify=False)
        elif variant == "brute":
            if not extra:
                print("enumb <MAC> <CHAR_UUID>")
                return
            char_uuid = extra[0]
            payloads = build_payload_iterator(value_range=(0x00, 0x02))
            brute_write_range(
                device,
                char_uuid,
                payloads=payloads,
                force=True,
                verify=False,
                respect_roeng=False,
                landmine_map=mine_map,
            )
    except Exception as exc:
        print_and_log(f"[-] Enumeration extension failed: {exc}", LOG__DEBUG)

    # Update shell globals – disconnect previous device cleanly
    if _current_device and getattr(_current_device, "is_connected", lambda: False)():
        try:
            _current_device.disconnect()
        except Exception:
            pass

    shell_globals["_current_device"] = device
    shell_globals["_current_mapping"] = mapping
    shell_globals["_current_mode"] = "ble"
    shell_globals["_current_path"] = device._device_path

    print_and_log(
        f"[+] {variant.capitalize()} enumeration complete – services: {len(mapping)}",
        LOG__GENERAL,
    )


# ---------------------------------------------------------------------------
# Public CLI wrappers – these will be imported directly into *debug.py*
# ---------------------------------------------------------------------------

def _cmd_enum(args: List[str]) -> None:
    _enum_common(globals(), "passive", args)


def _cmd_enumn(args: List[str]) -> None:
    _enum_common(globals(), "naggy", args)


def _cmd_enump(args: List[str]) -> None:
    _enum_common(globals(), "pokey", args)


def _cmd_enumb(args: List[str]) -> None:
    _enum_common(globals(), "brute", args) 