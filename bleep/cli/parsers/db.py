"""Database observation subparser."""

import argparse


def register(subparsers, _subparser_map):
    db_parser = subparsers.add_parser("db", help="Query and maintain local observation database")
    _add_db_arguments(db_parser)


def _add_db_arguments(db_parser):
    """Add the canonical ``db`` positional/flag set to *db_parser* (DB-1..DB-6).

    Single source of truth shared by the integrated CLI subparser
    (:func:`register`) and the standalone ``bleep.modes.db.main`` argparse, so
    the two can never drift.
    """
    db_parser.add_argument("action", choices=["list", "show", "export", "report", "timeline", "maintain", "uuids"], help="Action to perform")
    db_parser.add_argument("mac", nargs="?", help="Target MAC for show/export/timeline")
    db_parser.add_argument("--uuid", help="Restrict/select a single UUID (for uuids action)")
    db_parser.add_argument("--promote", metavar="NAME",
                           help="Promote --uuid into the custom UUID names using NAME (for uuids action)")
    db_parser.add_argument("--out", dest="out", help="Output file for export/report")
    db_parser.add_argument("--status", help="Filter devices by status: recent,ble,classic,media (comma-separated)")
    db_parser.add_argument("--name", help="Case-insensitive substring filter on device name (for list/report actions)")
    db_parser.add_argument("--fields", help="Comma-separated list of device fields to print (for list action)")
    db_parser.add_argument("--service", help="Filter timeline by service UUID")
    db_parser.add_argument("--char", help="Filter timeline by characteristic UUID")
    db_parser.add_argument("--sdp", action="store_true", default=False,
                           help="Timeline action: show Classic SDP record change history instead of "
                                "characteristics (filter with --uuid)")
    db_parser.add_argument("--seed", action="store_true", default=False,
                           help="uuids action: include the curated non-SIG UUID seed "
                                "(tagged source=curated_seed)")
    db_parser.add_argument("--limit", type=int, default=None,
                           help="Maximum entries to return (default: 50 for timeline, 100 for list, "
                                "500 for report)")
    db_parser.add_argument("--offset", type=int, default=0,
                           help="Number of records to skip for pagination (for list action, default: 0)")
    db_parser.add_argument("--full", action="store_true", default=False,
                           help="Show complete device detail as formatted JSON (for show action)")
    # DB-1/DB-6: date-window selection for list/report.
    db_parser.add_argument("--since", metavar="DATE",
                           help="Inclusive start of the collection window (YYYY-MM-DD, in --tz) "
                                "for list/report actions")
    db_parser.add_argument("--until", metavar="DATE",
                           help="Inclusive end of the collection window (YYYY-MM-DD, in --tz) "
                                "for list/report actions")
    db_parser.add_argument("--seen-basis", dest="seen_basis",
                           choices=["first", "last", "any"], default="last",
                           help="Which timestamp the window applies to: 'last' (default, indexed) "
                                "= last_seen; 'first' = first_seen; 'any' = observation span overlaps "
                                "the window")
    db_parser.add_argument("--tz", default="UTC",
                           help="Timezone for --since/--until dates (IANA name, e.g. America/New_York; "
                                "default: UTC, matching stored timestamps)")
    # DB-3: emit a survey/AoI-ingestable target list from the (filtered) selection.
    db_parser.add_argument("--export-targets", dest="export_targets", metavar="PATH",
                           help="list action: write the selected devices as an AoI-ingestable "
                                "JSON target list to PATH")
    # DB-4: opt-in heuristic identity/RPA collapse (OFF by default). The raw,
    # non-collapsed view is always available; collapse exists to contrast with it.
    db_parser.add_argument("--group-identity", dest="group_identity",
                           nargs="?", const="name", choices=["name", "name_mfr", "payload"],
                           default=None,
                           help="list/report actions: heuristically collapse RPA-rotating devices "
                                "into identity clusters (strategy default: name). Heuristic only — "
                                "no IRK resolution")
    db_parser.add_argument("--identity-contrast", dest="identity_contrast",
                           action="store_true", default=False,
                           help="report action: show BOTH raw and identity-collapsed summaries "
                                "for comparison (implies --group-identity)")
    db_parser.add_argument("--all-in-window", dest="all_in_window",
                           action="store_true", default=False,
                           help="report action: report every device matched by the window/filters "
                                "instead of capping at --limit (default 500)")
    db_parser.add_argument("--format", dest="report_format",
                           choices=["markdown", "json", "text"], default="markdown",
                           help="report action: output format (default: markdown)")
    # DB-5: uncap the per-device history in export (0 = all).
    db_parser.add_argument("--max-history", dest="max_history", type=int, default=500,
                           help="export action: max characteristic-history rows (0 = all; default: 500)")
    db_parser.add_argument("--max-adv", dest="max_adv", type=int, default=100,
                           help="export action: max advertisement-report rows (0 = all; default: 100)")
    # DB-8: classify observed device names into buckets (placeholder/own-MAC,
    # real, empty, foreign-MAC anomaly) with per-instance detail on the
    # real/empty/anomaly rows and a sample of the placeholder (default-alias) set.
    db_parser.add_argument("--name-audit", dest="name_audit",
                           action="store_true", default=False,
                           help="list/report actions: classify device names into "
                                "placeholder(own-MAC)/real/empty/foreign-MAC(anomaly) buckets. "
                                "Emits full collected data for real-named devices, full detail "
                                "for empty/anomaly devices, and a sample of placeholders. Always "
                                "surfaces MAC-shaped names that do not match the device address.")
    db_parser.add_argument("--name-sample", dest="name_sample", type=int, default=10,
                           help="name-audit: number of placeholder (default-alias) devices to "
                                "sample in the output (default: 10)")
    db_parser.add_argument("--name-detail-limit", dest="name_detail_limit", type=int, default=50,
                           help="name-audit: max real-named devices to expand with their full "
                                "collected record (0 = all; default: 50)")
    # DB-9: reconnaissance analytics — a single umbrella flag over modular
    # per-analytic builders (SDP inventory / OUI+address-type / advertisement hex
    # pattern-detection & decode) rendered under a top-level
    # "## Reconnaissance Analytics" section. Granular per-analytic flags can be
    # added later without changing the builders.
    db_parser.add_argument("--recon", dest="recon", action="store_true", default=False,
                           help="report action: add a Reconnaissance Analytics section — unique-SDP "
                                "inventory with counts, OUI/address-type breakdown with IEEE vendor "
                                "decode (graceful 'vendor unknown'), and manufacturer/service/AD hex "
                                "pattern-detection, comparison and decode across the selection.")
    db_parser.add_argument("--recon-detail", dest="recon_detail", action="store_true", default=False,
                           help="report action: implies --recon and additionally analyses "
                                "characteristic-value hex (heavier; per-characteristic unique-payload "
                                "tally + decode).")
    db_parser.add_argument("--report-bullets", dest="report_bullets", action="store_true", default=False,
                           help="report action: render count-bearing inventories (SDP service "
                                "inventory, OUI breakdown) as unified bullet lists instead of the "
                                "default markdown tables.")
