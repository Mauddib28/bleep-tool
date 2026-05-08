"""Scan and enumeration commands for debug mode."""

from __future__ import annotations

import argparse
from typing import Any, Dict, List, Tuple

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__ENUM
from bleep.ble_ops.le.scan import passive_scan
from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
from bleep.ble_ops.le.enum_helpers import multi_read_all, small_write_probe, build_payload_iterator, brute_write_range

from bleep.modes.debug_state import DebugState
from bleep.modes.debug_dbus import print_detailed_dbus_error


# ---------------------------------------------------------------------------
# Scan variants
# ---------------------------------------------------------------------------

def cmd_scan(args: List[str], state: DebugState) -> None:
    """Scan for nearby BLE devices."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    adapter = _Adapter()
    if not adapter.is_ready():
        print("[-] Bluetooth adapter not ready")
        return

    print_and_log("[*] Scanning for devices...", LOG__GENERAL)
    passive_scan(timeout=10)


def cmd_scann(args: List[str], state: DebugState) -> None:
    """Naggy scan (DuplicateData off)."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    adapter = _Adapter()
    if not adapter.is_ready():
        print("[-] Bluetooth adapter not ready")
        return

    from bleep.ble_ops.le.scan import naggy_scan
    print_and_log("[*] Naggy scan (active) …", LOG__GENERAL)
    naggy_scan(timeout=10)


def cmd_scanp(args: List[str], state: DebugState) -> None:
    """Pokey scan (spam active 1-s scans)."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    if not args:
        print("Usage: scanp <MAC>")
        return

    adapter = _Adapter()
    if not adapter.is_ready():
        print("[-] Bluetooth adapter not ready")
        return

    from bleep.ble_ops.le.scan import pokey_scan
    pokey_scan(args[0].upper(), timeout=10)


def cmd_scanb(args: List[str], state: DebugState) -> None:
    """Brute scan (BR/EDR + LE)."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    adapter = _Adapter()
    if not adapter.is_ready():
        print("[-] Bluetooth adapter not ready")
        return

    from bleep.ble_ops.le.scan import brute_scan
    print_and_log("[*] Brute scan …", LOG__GENERAL)
    brute_scan(timeout=20)


def cmd_dscan(args: List[str], state: DebugState) -> None:
    """Dual scan — single combined LE + BR/EDR discovery session.

    Unlike ``scanb`` (sequential phases), ``dscan`` uses ``Transport: auto``
    for a single interleaved discovery session that is less intrusive.
    """
    parser = argparse.ArgumentParser(prog="dscan", add_help=False)
    parser.add_argument("--timeout", "-t", type=int, default=15)
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    from bleep.core.preflight import require_adapter
    if not require_adapter():
        return

    print_and_log(f"[*] Dual scan (LE + BR/EDR) for {opts.timeout}s…", LOG__GENERAL)
    passive_scan(None, opts.timeout, transport="auto")


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


def _count_map_uuids(mapping: Dict[str, Any]) -> int:
    """Count total UUIDs across all categories in a mine or permission map."""
    if not mapping:
        return 0
    total = 0
    for cat_data in mapping.values():
        if isinstance(cat_data, dict):
            for uuid_list in cat_data.values():
                if isinstance(uuid_list, list):
                    total += len(uuid_list)
    return total


def _enum_common(mac: str, variant: str, state: DebugState, **opts) -> None:
    """Run enumeration variant and update debug-shell context."""
    try:
        device, mapping, mine_map, perm_map = _connect_enum(mac)

        if state.db_available and state.db_save_enabled:
            try:
                state.obs.upsert_device(
                    device.get_address(), name=device.get_name(), device_type="le",
                )
                from bleep.ble_ops.le.scan import _persist_mapping
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
        f"landmines={_count_map_uuids(mine_map)} permissions={_count_map_uuids(perm_map)}",
        LOG__GENERAL,
    )
    print_and_log(str(mapping), LOG__ENUM)


def cmd_mines(args: List[str], state: DebugState) -> None:
    """Display the landmine and permission maps from the last enumeration."""
    mine_map = state.current_mine_map
    perm_map = state.current_perm_map

    if not mine_map and not perm_map:
        print("[-] No enumeration data available. Run enum/enumn/enump/enumb first.")
        return

    def _print_map(label: str, mapping: Dict[str, Any]) -> None:
        if not mapping:
            print(f"\n{label}: (empty)")
            return
        cats = [k for k in mapping if k != "in_review"]
        review = mapping.get("in_review", {})
        total = sum(
            len(v) for cat in mapping.values() if isinstance(cat, dict)
            for v in cat.values() if isinstance(v, list)
        )
        print(f"\n{label} ({total} UUID(s) across {len(mapping)} category/ies):")
        for cat in cats:
            entries = mapping[cat]
            if not isinstance(entries, dict):
                continue
            print(f"  {cat.replace('_', ' ').title()}:")
            for issue, uuids in entries.items():
                if isinstance(uuids, list) and uuids:
                    print(f"    {issue}: {', '.join(str(u) for u in uuids)}")
        if review:
            uncategorized = review.get("uncategorized", [])
            if uncategorized:
                print(f"  In Review:")
                print(f"    uncategorized: {', '.join(str(u) for u in uncategorized)}")

    _print_map("Landmine Map", mine_map or {})
    _print_map("Permission Map", perm_map or {})

    dev = state.current_device
    if dev and hasattr(dev, "get_landmine_report"):
        report = dev.get_landmine_report()
        sec = dev.get_security_report()
        if report or sec:
            print("\nDetailed Device Reports:")
        if report:
            print("  Landmine Report:")
            for category, entries in report.items():
                print(f"    {category}:")
                for entry in entries:
                    print(f"      {entry['uuid']}: {entry['details']}")
        if sec:
            print("  Security Report:")
            for requirement, entries in sec.items():
                print(f"    {requirement}:")
                for entry in entries:
                    print(f"      {entry['uuid']}: {entry['details']}")
    print()


def cmd_enum(args: List[str], state: DebugState) -> None:
    """Run passive enumeration."""
    if not args:
        print("Usage: enum <MAC>")
        return
    _enum_common(args[0].upper(), "passive", state)


def cmd_enumn(args: List[str], state: DebugState) -> None:
    """Run naggy enumeration."""
    if not args:
        print("Usage: enumn <MAC>")
        return
    _enum_common(args[0].upper(), "naggy", state)


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

    _enum_common(opts.mac.upper(), "pokey", state, rounds=opts.rounds, verify=opts.verify)


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
        opts.mac.upper(), "brute", state,
        char=opts.char, range=range_tuple, patterns=patterns_lst,
        file_bytes=file_bytes, force=opts.force, verify=opts.verify,
    )
