"""BLEEP CLI argument parser construction."""

import argparse
from bleep import __version__
from bleep.core.observations._connection import _SCHEMA_VERSION


def build_argument_parser():
    """Construct the root argument parser (without parsing).

    Returns ``(parser, subparsers, subparser_map)``.  Extracted from
    :func:`build_parser` so callers that need to *introspect* the CLI surface
    (e.g. the CLI↔Debug parity guard test) can enumerate the registered
    subcommands via ``subparsers.choices`` without side effects or argv
    consumption.  ``build_parser`` remains the canonical parse entry point and
    its behaviour is unchanged.
    """
    parser = argparse.ArgumentParser(
        description="BLEEP - Bluetooth Landscape Exploration & Enumeration Platform"
    )
    parser.add_argument("--version", action="version",
                        version=f"BLEEP {__version__} (DB schema v{_SCHEMA_VERSION})")
    parser.add_argument("--check-env", action="store_true",
                        help="Check environment capabilities (tools, configs, dependencies)")
    parser.add_argument("--diagnose-audio", action="store_true",
                        help="Run detailed audio stack diagnostic and show install guidance")

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json", dest="output_mode", action="store_const", const="json",
        help="Emit structured JSON output to stdout (suppresses banner)",
    )
    output_group.add_argument(
        "--quiet", "-q", dest="output_mode", action="store_const", const="quiet",
        help="Suppress banner and progress messages; only emit results",
    )
    parser.set_defaults(output_mode="terminal")

    subparsers = parser.add_subparsers(dest="mode", help="Operation mode")
    _subparser_map = {}

    from bleep.cli.parsers import (
        scan, explore, connect, gatt, classic, media, audio,
        pairing, db, survey, beacon, aoi, debug, utility, other,
    )
    scan.register(subparsers, _subparser_map)
    explore.register(subparsers, _subparser_map)
    connect.register(subparsers, _subparser_map)
    gatt.register(subparsers, _subparser_map)
    classic.register(subparsers, _subparser_map)
    media.register(subparsers, _subparser_map)
    audio.register(subparsers, _subparser_map)
    pairing.register(subparsers, _subparser_map)
    db.register(subparsers, _subparser_map)
    survey.register(subparsers, _subparser_map)
    beacon.register(subparsers, _subparser_map)
    aoi.register(subparsers, _subparser_map)
    debug.register(subparsers, _subparser_map)
    utility.register(subparsers, _subparser_map)
    other.register(subparsers, _subparser_map)

    return parser, subparsers, _subparser_map


def build_parser(args=None):
    """Build the argument parser and return (parsed_args, subparser_map)."""
    parser, _subparsers, _subparser_map = build_argument_parser()
    return parser.parse_args(args), _subparser_map


def iter_cli_subcommands():
    """Return the set of registered top-level CLI subcommand names.

    Includes argparse-registered aliases (e.g. ``uuid-lookup`` for
    ``uuid-translate``), since those are distinct keys in
    ``subparsers.choices``.  Used by the CLI↔Debug parity guard to assert that
    every reachable command is declared in the capability registry.
    """
    _parser, subparsers, _subparser_map = build_argument_parser()
    return set(subparsers.choices.keys())
