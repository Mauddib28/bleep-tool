"""BLEEP Analysis mode – post-process enumeration JSON dumps.

A lightweight replacement for legacy *Modules/analysis_mode.py*.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bleep.core.log import print_and_log, LOG__GENERAL


def _arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bleep-analyse", add_help=False)
    p.add_argument("files", nargs="+", metavar="FILE", help="JSON file(s) generated by exploration mode")
    p.add_argument("--help", "-h", action="help")
    return p


def _summarise(data: dict):
    svcs = data.get("Services", {})
    print_and_log(f"  Services: {len(svcs)}", LOG__GENERAL)
    char_total = sum(len(v.get("Characteristics", {})) for v in svcs.values())
    print_and_log(f"  Characteristics: {char_total}", LOG__GENERAL)


def main(argv: list[str] | None = None):  # noqa: D401 – CLI entry
    argv = argv or sys.argv[1:]
    args = _arg_parser().parse_args(argv)

    for file_path in args.files:
        path = Path(file_path).expanduser()
        if not path.exists():
            print_and_log(f"[-] File not found: {path}", LOG__GENERAL)
            continue
        with path.open() as f:
            try:
                data = json.load(f)
            except Exception as e:
                print_and_log(f"[-] Failed to parse {path}: {e}", LOG__GENERAL)
                continue
        print_and_log(f"[*] Summary for {path}", LOG__GENERAL)
        _summarise(data)


if __name__ == "__main__":  # pragma: no cover
    main() 