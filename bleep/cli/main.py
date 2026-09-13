"""BLEEP CLI entry point — argument parsing, global flags, and mode dispatch."""

import argparse
import signal
import sys

import bleep.core.log  # noqa: F401  # side-effect import

from bleep import __version__
from bleep.cli.parsers import build_parser
from bleep.cli.dispatch import dispatch


def _rebuild_debug_argv(args) -> list:
    """Translate the parsed 'debug' subcommand namespace back into the argv
    form that ``bleep.modes.debug.parse_args()`` expects, so that module
    keeps a single source of truth for its CLI surface."""
    argv: list = []
    if getattr(args, "monitor", False):
        argv.append("--monitor")
    if getattr(args, "no_connect", False):
        argv.append("--no-connect")
    if getattr(args, "detailed", False):
        argv.append("--detailed")
    device = getattr(args, "device", None)
    if device:
        argv.append(device)
    return argv


def main(args=None):
    """Main entry point for BLEEP."""
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    args, _subparsers = build_parser(args)

    # Normalize MAC address arguments to uppercase for DB/D-Bus consistency
    for _mac_attr in ("address", "target", "device", "mac",
                       "pair", "trust", "untrust", "remove_bond",
                       "source", "sink"):
        _val = getattr(args, _mac_attr, None)
        if isinstance(_val, str) and ":" in _val:
            setattr(args, _mac_attr, _val.upper())

    # Handle --check-env flag
    if args.check_env:
        from bleep.core.preflight import run_preflight_checks, print_preflight_summary
        report = run_preflight_checks(use_cache=False)
        print_preflight_summary(report)
        return 0

    # Handle --diagnose-audio flag
    if getattr(args, "diagnose_audio", False):
        from bleep.core.preflight import diagnose_audio
        diagnose_audio()
        return 0

    import logging as _logging, os as _os

    _lvl = _os.getenv("BLEEP_LOG_LEVEL")
    if _lvl:
        _logging.getLogger("bleep").setLevel(_lvl.upper())

    # Adapter guard for all Bluetooth-dependent modes
    _non_bt_modes = {"db", "uuid-translate", "uuid-lookup", "refresh-refs", None}
    if args.mode not in _non_bt_modes:
        from bleep.core.preflight import require_adapter
        if not require_adapter():
            return 1

    from bleep.banner import print_banner
    print_banner(args.mode, output_mode=args.output_mode)

    try:
        return dispatch(args, _subparsers)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
