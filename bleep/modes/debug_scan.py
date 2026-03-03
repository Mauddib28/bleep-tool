"""Scan and enumeration commands for debug mode."""

from __future__ import annotations

import argparse
from typing import Any, Dict, List, Tuple

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__ENUM
from bleep.ble_ops.scan import passive_scan
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
from bleep.ble_ops.enum_helpers import multi_read_all, small_write_probe, build_payload_iterator, brute_write_range

from bleep.modes.debug_state import DebugState
from bleep.modes.debug_dbus import print_detailed_dbus_error


# ---------------------------------------------------------------------------
# Scan variants
# ---------------------------------------------------------------------------

def cmd_scan(args: List[str], state: DebugState) -> None:
    """Scan for nearby BLE devices."""
    print_and_log("[*] Scanning for devices...", LOG__GENERAL)
    passive_scan(timeout=10)


def cmd_scann(args: List[str], state: DebugState) -> None:
    """Naggy scan (DuplicateData off)."""
    from bleep.ble_ops.scan import naggy_scan
    print_and_log("[*] Naggy scan (active) …", LOG__GENERAL)
    naggy_scan(timeout=10)


def cmd_scanp(args: List[str], state: DebugState) -> None:
    """Pokey scan (spam active 1-s scans)."""
    from bleep.ble_ops.scan import pokey_scan
    if not args:
        print("Usage: scanp <MAC>")
        return
    pokey_scan(args[0], timeout=10)


def cmd_scanb(args: List[str], state: DebugState) -> None:
    """Brute scan (BR/EDR + LE)."""
    from bleep.ble_ops.scan import brute_scan
    print_and_log("[*] Brute scan …", LOG__GENERAL)
    brute_scan(timeout=20)


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------

def _safe_count_characteristics(mapping: Dict[str, Any]) -> Tuple[int, int]:
    """Count services and characteristics, handling multiple mapping formats."""
    if not isinstance(mapping, dict):
        print_and_log(
            f"[DEBUG] Unexpected mapping type: {type(mapping).__name__}, expected dict",
            LOG__DEBUG,
        )
        return 0, 0

    svc_cnt = len(mapping)
    char_cnt = 0
    for svc_uuid, svc_data in mapping.items():
        if not isinstance(svc_data, dict):
            print_and_log(
                f"[DEBUG] Non-dictionary service data for {svc_uuid}: "
                f"{type(svc_data).__name__}={svc_data!r}",
                LOG__DEBUG,
            )
            continue
        chars_data = svc_data.get("chars") or svc_data.get("Characteristics")
        if chars_data and isinstance(chars_data, dict):
            char_cnt += len(chars_data)
        elif chars_data is not None:
            print_and_log(
                f"[DEBUG] Unexpected characteristic data type for {svc_uuid}: "
                f"{type(chars_data).__name__}",
                LOG__DEBUG,
            )
    return svc_cnt, char_cnt


def _enum_common(mac: str, variant: str, state: DebugState, **opts) -> None:
    """Run enumeration variant and update debug-shell context."""
    try:
        device, mapping, mine_map, perm_map = _connect_enum(mac)

        if state.db_available and state.db_save_enabled:
            try:
                state.obs.upsert_device(
                    device.get_address(), name=device.get_name(), device_type="le",
                )
                from bleep.ble_ops.scan import _persist_mapping
                _persist_mapping(device.get_address(), mapping)
                print_and_log("[*] Device information saved to database", LOG__GENERAL)
            except Exception as e:
                print_and_log(f"[-] Failed to save to database: {e}", LOG__DEBUG)
    except Exception as exc:
        print_detailed_dbus_error(exc)
        return

    if variant == "naggy":
        multi_read_all(device, mapping=mapping, rounds=3)
    elif variant == "pokey":
        rounds = int(opts.get("rounds", 3))
        for _ in range(rounds):
            small_write_probe(device, mapping, verify=opts.get("verify", False))
    elif variant == "brute":
        char_uuid = opts.get("char")
        if not char_uuid:
            print("enumb <MAC> <CHAR_UUID> [flags]")
            return
        value_range = opts.get("range")
        patterns = opts.get("patterns")
        file_bytes = opts.get("file_bytes")
        if not any([value_range, patterns, file_bytes]):
            value_range = (0x00, 0x02)
        payloads = build_payload_iterator(
            value_range=value_range, patterns=patterns, file_bytes=file_bytes,
        )
        brute_write_range(
            device, char_uuid, payloads=payloads,
            force=opts.get("force", False), verify=opts.get("verify", False),
            respect_roeng=False, landmine_map=mine_map,
        )

    if state.current_device and getattr(state.current_device, "is_connected", lambda: False)():
        try:
            state.current_device.disconnect()
        except Exception:
            pass

    state.current_device = device
    state.current_mapping = mapping
    state.current_mine_map = mine_map
    state.current_perm_map = perm_map
    state.current_mode = "ble"
    state.current_path = device._device_path

    svc_cnt, char_cnt = _safe_count_characteristics(mapping)
    print_and_log(
        f"[enum-{variant}] services={svc_cnt} chars={char_cnt} "
        f"mine={len(mine_map)} perm={len(perm_map)}",
        LOG__GENERAL,
    )
    print_and_log(str(mapping), LOG__ENUM)


def cmd_enum(args: List[str], state: DebugState) -> None:
    """Run passive enumeration."""
    if not args:
        print("Usage: enum <MAC>")
        return
    _enum_common(args[0], "passive", state)


def cmd_enumn(args: List[str], state: DebugState) -> None:
    """Run naggy enumeration."""
    if not args:
        print("Usage: enumn <MAC>")
        return
    _enum_common(args[0], "naggy", state)


def cmd_enump(args: List[str], state: DebugState) -> None:
    """Run pokey enumeration."""
    if not args:
        print("Usage: enump <MAC> [rounds]")
        return

    parser = argparse.ArgumentParser(prog="enump", description="Pokey enumeration")
    parser.add_argument("mac")
    parser.add_argument("--rounds", "-r", type=int, default=3)
    parser.add_argument("--verify", action="store_true")

    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    _enum_common(opts.mac, "pokey", state, rounds=opts.rounds, verify=opts.verify)


def cmd_enumb(args: List[str], state: DebugState) -> None:
    """Run brute enumeration."""
    if len(args) < 2:
        print("Usage: enumb <MAC> <CHAR_UUID> [flags]")
        return

    parser = argparse.ArgumentParser(prog="enumb", description="Brute enumeration")
    parser.add_argument("mac")
    parser.add_argument("char")
    parser.add_argument("--range")
    parser.add_argument("--patterns")
    parser.add_argument("--payload-file")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verify", action="store_true")

    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    range_tuple = None
    if opts.range:
        try:
            start_s, end_s = opts.range.split("-", 1)
            start = int(start_s, 0)
            end = int(end_s, 0)
            if not (0 <= start <= 255 and 0 <= end <= 255 and start <= end):
                raise ValueError
            range_tuple = (start, end)
        except Exception:
            print("[enumb] Invalid --range; use e.g. 0-255 or 0x00-0xFF")
            return

    patterns_lst = (
        [p.strip() for p in opts.patterns.split(",") if p.strip()]
        if opts.patterns else None
    )

    file_bytes = None
    if opts.payload_file:
        try:
            with open(opts.payload_file, "rb") as fh:
                file_bytes = fh.read()
        except Exception as exc:
            print(f"[enumb] Cannot read payload file: {exc}")
            return

    _enum_common(
        opts.mac, "brute", state,
        char=opts.char, range=range_tuple, patterns=patterns_lst,
        file_bytes=file_bytes, force=opts.force, verify=opts.verify,
    )
