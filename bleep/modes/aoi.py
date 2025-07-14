"""BLEEP Assets-of-Interest (AoI) mode – iterate over lists of target MACs.

Port of legacy aoi_mode: reads one or more JSON files whose values are arrays
of MAC addresses, scans/enum each target sequentially.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum


_DEF_WAIT = 4.0  # seconds between targets


def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bleep-aoi", add_help=False)
    p.add_argument("files", nargs="+", metavar="FILE", help="JSON files containing AoI device lists")
    p.add_argument("--delay", type=float, default=_DEF_WAIT, help="Seconds to wait between devices")
    p.add_argument("--help", "-h", action="help")
    return p


def _iter_macs(obj) -> List[str]:
    """Return list of mac strings inside *obj* (supports nested dict format)."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        macs: List[str] = []
        for val in obj.values():
            macs.extend(_iter_macs(val))
        return macs
    return []


## TODO: Actions to perform or add to the AoI code
#   [ ] Incorporate enumerate__assets_of_interest
#
#
##########


def main(argv: list[str] | None = None):
    argv = argv or sys.argv[1:]
    args = _arg_parser().parse_args(argv)

    for file_path in args.files:
        path = Path(file_path).expanduser()
        if not path.exists():
            print_and_log(f"[-] File not found: {path}", LOG__GENERAL)
            continue
        print_and_log(f"[*] Processing AoI file {path}", LOG__GENERAL)
        with path.open() as f:
            try:
                data = json.load(f)
            except Exception as e:
                print_and_log(f"[-] Failed to parse {path}: {e}", LOG__GENERAL)
                continue
        for mac in _iter_macs(data):
            mac_up = mac.upper()
            print_and_log(f"[*] AoI connect+enum {mac_up}", LOG__GENERAL)
            try:
                _connect_enum(mac_up)
            except Exception as e:
                print_and_log(f"[-] Failed: {e}", LOG__GENERAL)
            time.sleep(args.delay)

    print_and_log("[+] AoI run complete", LOG__GENERAL)


if __name__ == "__main__":  # pragma: no cover
    main() 
