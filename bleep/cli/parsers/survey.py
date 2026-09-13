"""Survey subparser."""

import argparse


def _add_survey_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Attach the canonical survey flag set to *parser*.

    Single source of truth shared by the main CLI subparser (:func:`register`),
    the standalone ``python -m bleep.modes.survey`` parser
    (``bleep.modes.survey._build_parser``) and the debug-shell ``survey`` command
    (``bleep.modes.debug_survey.cmd_survey``) so the three cannot drift.
    """
    parser.add_argument("--duration", type=int, default=120, help="Listen/admission window in seconds (default: 120). With --enumerator, GATT continues after this until the queue is empty.")
    parser.add_argument("--round-time", type=int, default=30, help="Duration of each scan round in seconds (default: 30)")
    parser.add_argument("--segment-time", type=int, default=1800, help="Maximum listen seconds per process (default: 1800 = 30 min). A --duration longer than this is split into consecutive segments in fresh processes and merged, because a single process stops collecting after ~42 min. 0 disables splitting.")
    parser.add_argument("--transport", choices=["le", "bredr", "both"], default="both", help="Scan transport (default: both)")
    parser.add_argument("-o", "--output", help="Output file for AoI-compatible JSON (default: stdout)")
    parser.add_argument("--format", choices=["simple", "objects", "grouped"], default="objects", dest="out_format", help="Output format (default: objects)")
    parser.add_argument("--min-rssi", type=int, default=None, help="Minimum RSSI threshold to include a device")
    parser.add_argument("--min-sightings", type=int, default=1, help="Minimum sightings to include a device (default: 1)")
    parser.add_argument("--no-db", action="store_true", help="Skip Classic-round DB persistence (LE scan always persists via core infra)")
    parser.add_argument("--live", action="store_true", help="Show live round progress to stderr")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-device scan output")
    parser.add_argument("--adapter", default="hci0", help="Bluetooth adapter name for single-adapter survey (default: hci0)")
    parser.add_argument(
        "--collector",
        action="append",
        metavar="hciN[:TRANSPORT]",
        help=(
            "Enable multi-antenna collection: repeat to add adapters "
            "(e.g. --collector hci0:le --collector hci1:bredr). TRANSPORT is "
            "le|bredr|both. Bare adapters (no :TRANSPORT) use the default "
            "transport-split profile (LE/BR-EDR round-robin across adapters); "
            "giving the same transport to multiple adapters is a spatial profile. "
            "Overrides --adapter/--transport when present."
        ),
    )
    parser.add_argument(
        "--enumerator",
        default=None,
        metavar="hciN[:MODE]",
        help=(
            "Secondary antenna for concurrent enumeration while collectors stay "
            "in discovery. MODE is passive|naggy|pokey|pair (default: passive). "
            "Requires a distinct adapter from --collector/--adapter. "
            "Example: --collector hci0:le --enumerator hci1:passive"
        ),
    )
    parser.add_argument(
        "--enum-cooldown",
        type=int,
        default=3600,
        metavar="SEC",
        help=(
            "Skip GATT for a device successfully enumerated within SEC seconds "
            "(default: 3600). 0 disables the DB cooldown; this-run successes "
            "are never re-queued from collector re-sights. Requires --enumerator."
        ),
    )
    parser.add_argument("--then-aoi", action="store_true", help="After survey, run 'bleep aoi scan' on the output file (requires -o)")
    parser.add_argument("--resume-db", action="store_true", help="Pre-seed survey census with previously observed devices from the DB")
    parser.add_argument("--adaptive", action="store_true", help="Auto-adjust round time based on device discovery rate")
    parser.add_argument("--adaptive-min", type=int, default=10, help="Minimum round time when adaptive is enabled (default: 10s)")
    parser.add_argument("--adaptive-max", type=int, default=60, help="Maximum round time when adaptive is enabled (default: 60s)")
    parser.add_argument("--exclude-cached", action="store_true", help="Exclude cached/bonded devices not actively seen during this scan")
    parser.add_argument("--checkpoint-interval", type=int, default=0, help="Periodically write the partial census to <output>.partial every N seconds (0=off, requires -o)")
    parser.add_argument("--auto-recover", action="store_true", help="If the adapter goes not-ready mid-survey, attempt to power-cycle it (mutates host BT power state; off by default)")
    parser.add_argument(
        "--variant",
        choices=["passive", "naggy"],
        default="passive",
        help="LE discovery variant (default: passive; naggy uses DuplicateData=true via merged filter)",
    )
    parser.add_argument(
        "--full-payloads",
        action="store_true",
        help="Include per-round payload_history snapshots in objects/grouped JSON output",
    )
    parser.add_argument(
        "--metrics-interval",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Sample RSS/threads/fds/census/pool every N seconds to "
            "<output>.metrics.csv (0=off, requires -o). Sampled in-process, so "
            "unlike an external sampler it cannot miss the run."
        ),
    )
    parser.add_argument(
        "--stall-rounds",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Re-arm discovery after N consecutive rounds in which no device "
            "reported, even while BlueZ still claims Discovering=true "
            "(default: 3, 0 = never re-arm). Guards against a silently dead "
            "collector consuming the run."
        ),
    )
    parser.add_argument(
        "--no-mainloop",
        action="store_true",
        help=(
            "Run without a GLib main loop. Avoids the heap corruption that "
            "aborts dual collector+enumerator runs (docs/mainloop_architecture.md). "
            "Collection and GATT enumeration are unaffected (both poll), but "
            "AdvMonitor callbacks, pairing agent requests and GATT "
            "notifications are DISABLED - a warning is printed listing them. "
            "Rejected with --listen-monitor and --variant pair."
        ),
    )
    parser.add_argument(
        "--max-enum-devices",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Cap live enumeration device objects; the least-recently-used is "
            "torn down beyond the cap (default: 10, 0 = unlimited). Bounds "
            "long-run memory. BLEEP_MAX_ENUM_DEVICES sets the same cap for "
            "entry points without this flag. See docs/survey_mode.md."
        ),
    )
    parser.add_argument(
        "--listen-monitor",
        action="store_true",
        help=(
            "Register a Flags-OR AdvertisementMonitor overlay on LE collectors "
            "(one monitor, GAP Flags 00/02/04/05/06/18/1A; same adapter as "
            "StartDiscovery). Census is the union of Device1 harvest and "
            "DeviceFound. Not --variant passive."
        ),
    )
    parser.add_argument(
        "--listen-pattern",
        dest="listen_patterns",
        action="append",
        metavar="OFF:AD:HEX",
        help="Extra AdvMonitor pattern (repeatable) OR-appended onto Flags-OR with --listen-monitor",
    )
    parser.add_argument(
        "--listen-manufacturer",
        dest="listen_manufacturers",
        action="append",
        metavar="CID[:HEX]",
        help=(
            "Extra manufacturer AD filter (repeatable) OR-appended with "
            "--listen-monitor. CID decimal or 0x-hex; optional :HEX payload "
            "prefix after the little-endian company id"
        ),
    )
    parser.add_argument(
        "--listen-mfr-string",
        dest="listen_mfr_strings",
        action="append",
        metavar="TEXT",
        help=(
            "Extra UTF-8 string in manufacturer payload (repeatable) OR-appended "
            "with --listen-monitor. Matches AD 0xFF at offset 2 (after company id)"
        ),
    )
    return parser


def register(subparsers, _subparser_map):
    survey_parser = subparsers.add_parser("survey", help="Long-duration passive survey for device discovery")
    _add_survey_arguments(survey_parser)
