"""Debug-shell thin adapters over one-shot CLI cores (CDU-M3).

Each verb here is a stateless port of an existing CLI subcommand: it does **no**
new work, it only builds the argument ``Namespace`` and calls the same core the
CLI dispatch calls (`bleep/cli/dispatch.py`).  Parity is guaranteed by parsing
the debug tokens through the *real* CLI subparser (`parse_as_cli`), so a debug
verb can never accept a different option set than its CLI twin.

Verbs (CLI twin → core):
    uuidtr      uuid-translate  → bleep.modes.uuid_translate.main
    adaptercfg  adapter-config  → bleep.modes.adapter_config.handle_adapter_config
    netenum     network-enum    → bleep.modes.classic_profiles.run_network_enum
    cping       classic-ping    → bleep.ble_ops.classic.ping.classic_l2ping
    db          db              → bleep.modes.db.run (terminal OutputContext)
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.modes.debug_state import DebugState


def parse_as_cli(cli_name: str, tokens: List[str]) -> Optional[argparse.Namespace]:
    """Parse *tokens* using the real CLI subparser for *cli_name*.

    Returns the same ``Namespace`` the CLI dispatch would receive, or ``None``
    when argparse raised ``SystemExit`` (parse error or ``--help``) — which is
    caught here so it can never tear down the interactive shell.

    Shared by the M3 stateless adapters (below) and the M4 stateful adapters
    (:mod:`bleep.modes.debug_stateful_adapters`); this is the single anti-drift
    seam guaranteeing debug verbs accept exactly their CLI twin's options.
    """
    from bleep.cli.parsers import build_argument_parser

    parser, _subparsers, _map = build_argument_parser()
    try:
        return parser.parse_args([cli_name, *tokens])
    except SystemExit:
        return None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def cmd_uuidtr(args: List[str], state: DebugState) -> None:
    """``uuidtr <uuid...> [--json] [--verbose] [--include-unknown]``."""
    if not args:
        print_and_log(
            "Usage: uuidtr <uuid> [uuid...] [--json] [--verbose] [--include-unknown]",
            LOG__GENERAL,
        )
        return
    from bleep.modes.uuid_translate import main as _uuid_main

    # main() self-parses and may raise SystemExit on --help/bad input; contain it.
    try:
        _uuid_main(list(args))
    except SystemExit:
        return


def cmd_adaptercfg(args: List[str], state: DebugState) -> None:
    """``adaptercfg [show|get <prop>|set <prop> <val...>] [--adapter hciX]``."""
    ns = parse_as_cli("adapter-config", args)
    if ns is None:
        return
    from bleep.modes.adapter_config import handle_adapter_config

    handle_adapter_config(ns)


# ---------------------------------------------------------------------------
# Classic (BR/EDR)
# ---------------------------------------------------------------------------

def cmd_netenum(args: List[str], state: DebugState) -> None:
    """``netenum [--adapter hciX] [--all-devices] [--json]`` — PAN capability."""
    ns = parse_as_cli("network-enum", args)
    if ns is None:
        return
    from bleep.modes.classic_profiles import run_network_enum

    run_network_enum(ns)


def cmd_cping(args: List[str], state: DebugState) -> None:
    """``cping <MAC> [--count N] [--timeout N] [--adapter hciX]`` — l2ping."""
    ns = parse_as_cli("classic-ping", args)
    if ns is None:
        return
    from bleep.ble_ops.classic.ping import classic_l2ping

    rtt, err = classic_l2ping(ns.address, count=ns.count, timeout=ns.timeout)
    if rtt is None:
        print_and_log(f"[!] l2ping failed - {err}", LOG__GENERAL)
        return
    print_and_log(f"Average RTT {rtt:.1f} ms", LOG__GENERAL)


# ---------------------------------------------------------------------------
# Observation database
# ---------------------------------------------------------------------------

def cmd_db(args: List[str], state: DebugState) -> None:
    """``db <list|show|timeline|export|uuids|maintain> [...]`` — full DB surface.

    Broader than the session-scoped ``dbsave``/``dbexport`` helpers: this is the
    same query/maintenance surface as the CLI ``bleep db`` (terminal output).
    """
    if not args:
        print_and_log(
            "Usage: db <list|show|timeline|export|uuids|maintain> [MAC] [options]",
            LOG__GENERAL,
        )
        return
    ns = parse_as_cli("db", args)
    if ns is None:
        return
    from bleep.modes.db import run as _db_run

    # No OutputContext → db.run builds the default terminal one and emits via
    # print_and_log (JSON path is only taken for is_json/is_quiet), so no shim.
    _db_run(ns)
