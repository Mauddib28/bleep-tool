"""AoI and analysis subparsers."""

import argparse

# Canonical set of AoI subcommands recognised on the flat ``aoi`` parser. When
# the first positional token matches one of these it selects the subcommand;
# otherwise the tokens are treated as scan input files (implicit ``scan``).
AOI_SUBCOMMANDS = ("scan", "analyze", "list", "report", "export", "db")


def _add_aoi_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add the canonical ``aoi`` flag/positional set to *parser*.

    Single source of truth shared by the integrated-CLI subparser
    (:func:`register`) and the standalone ``bleep.modes.aoi.main`` entry point,
    so the two parsers can never drift.  (Previously the flat production parser
    and a separate nested parser in ``modes/aoi.py`` were maintained
    independently — the production one was even missing the ``--timeout`` /
    ``--format`` defaults.)
    """
    parser.add_argument("files", nargs="*",
                        help="First argument can be a subcommand (scan, analyze, list, report, export, db) followed by files or options")
    parser.add_argument("-f", "--file", dest="test_file", help="AoI test file to scan")
    parser.add_argument("--delay", type=float, default=4.0, help="Delay between devices (for scan subcommand)")
    parser.add_argument("--address", "-a", help="MAC address for analyze/report/export subcommands")
    parser.add_argument("--all", action="store_true", dest="report_all", help="Generate aggregate report for all AoI devices (for report subcommand)")
    parser.add_argument("--include-synthetic", action="store_true", help="Include seeded/test-fixture MACs (e.g. AA:BB:CC:DD:EE:*) in list/report output (default: excluded)")
    parser.add_argument("--deep", action="store_true", help="Perform deeper analysis: pairing + post-pair re-enum (for scan and analyze subcommands)")
    parser.add_argument("--analyze", action="store_true", dest="analyze_inline", help="After scanning each target, immediately run analysis on it (scan subcommand)")
    parser.add_argument("--timeout", type=int, default=30, help="Per-device timeout in seconds; bounds the LE connect/service-resolution phase as well as SDP/pairing (scan and analyze subcommands)")
    parser.add_argument("--format", choices=["markdown", "json", "text"], default="markdown", help="Report format (for report subcommand)")
    parser.add_argument("--output", "-o", help="Output file/directory (for report/export subcommands)")
    parser.add_argument("--db-only", action="store_true", help="Use only database for storage, skip file-based AoI directory")
    parser.add_argument("--no-db", action="store_true", help="Disable database integration entirely")
    parser.add_argument("--connectionless", action="store_true", help="Use connectionless SDP (l2ping + sdptool) for Classic enumeration")
    parser.add_argument("--refresh-scan", type=int, default=0, metavar="SECS", help="Before enumerating, run a SECS-second discovery scan to repopulate the adapter cache (helps stale RPAs from an earlier survey); 0=off (scan subcommand)")
    parser.add_argument("--adapter", default="hci0", help="Bluetooth adapter for connect/enumerate/pair (default: hci0)")
    return parser


def apply_aoi_subcommand(args: argparse.Namespace) -> bool:
    """Resolve the AoI subcommand from the flat positional list, in place.

    If the first positional token is a known subcommand it becomes
    ``args.command`` (and is stripped from ``args.files``); otherwise the tokens
    (plus any ``-f/--file`` value) are treated as scan input files and the
    command defaults to ``scan``.  Returns ``True`` when an explicit subcommand
    was matched, ``False`` for the implicit-scan fallback — letting callers
    distinguish "no arguments at all" from an explicit but empty subcommand.
    """
    files = list(getattr(args, "files", None) or [])
    if files and files[0] in AOI_SUBCOMMANDS:
        args.command = files[0]
        args.files = files[1:]
        return True
    test_file = getattr(args, "test_file", None)
    if test_file:
        files = files + [test_file]
    args.files = files
    args.command = "scan"
    return False


def register(subparsers, _subparser_map):
    aoi_parser = subparsers.add_parser("aoi", help="Process Assets-of-Interest JSON list (supports multiple subcommands)")
    _add_aoi_arguments(aoi_parser)

    analysis_parser = subparsers.add_parser("analyse", help="Post-process JSON dumps", aliases=["analyze"])
    analysis_parser.add_argument("files", nargs="+", help="JSON dump files to analyse")
    analysis_parser.add_argument("--detailed", "-d", action="store_true", help="Show detailed analysis including characteristics")
