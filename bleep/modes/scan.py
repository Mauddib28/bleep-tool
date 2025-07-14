from __future__ import annotations

"""bleep.modes.scan – simple wrapper around passive_scan.

Intended to replace the legacy `Modules/scan_mode.py`.  Provides a *main()*
function so other tools or the CLI can invoke the mode via
`python -m bleep.modes.scan --help`.
"""

import argparse
from bleep.ble_ops.scan import passive_scan


def _build_parser():
    p = argparse.ArgumentParser(description="Passive BLE device scan")
    p.add_argument("-t", "--timeout", type=int, default=10, help="scan duration (seconds)")
    p.add_argument("--transport", type=str, choices=["auto", "le", "bredr"], default="auto",
                  help="transport type: auto (default), le (Low Energy), or bredr (Classic)")
    return p


def main(argv: list[str] | None = None):  # noqa: D401 – entry point
    args = _build_parser().parse_args(argv)
    return passive_scan(timeout=args.timeout, transport=args.transport)


if __name__ == "__main__":
    raise SystemExit(main()) 