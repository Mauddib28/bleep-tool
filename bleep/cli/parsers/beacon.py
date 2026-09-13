"""Beacon-identification subparser."""

import argparse


def _add_beacon_identification_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Attach beacon-identification flags (shared by CLI registration)."""
    parser.add_argument("--oui", help="Address OUI/prefix filter (client-side; e.g. 10:20:BA)")
    parser.add_argument("--name", help="Local-name glob filter (client-side; e.g. '*Beacon*')")
    parser.add_argument("--ibeacon-uuid", dest="ibeacon_uuid", help="Filter decoded iBeacon UUID")
    parser.add_argument("--eddystone-url", dest="eddystone_url", help="Filter decoded Eddystone URL substring")
    parser.add_argument("--major", type=int, help="Filter iBeacon major")
    parser.add_argument("--minor", type=int, help="Filter iBeacon minor")
    parser.add_argument("--duration", type=int, default=300, help="Total identification duration in seconds (default: 300)")
    parser.add_argument("--round-time", type=int, default=15, help="Survey round length in seconds (default: 15)")
    parser.add_argument("--transport", choices=["le"], default="le", help="Transport (default: le)")
    parser.add_argument("--min-rssi", type=int, default=None, help="Minimum RSSI threshold")
    parser.add_argument("-o", "--output", help="JSON output path (default: stdout)")
    parser.add_argument("--live", action="store_true", help="Live progress to stderr")
    parser.add_argument("--quiet", action="store_true", help="Suppress human candidate table")
    return parser


def register(subparsers, _subparser_map):
    parser = subparsers.add_parser(
        "beacon-identification",
        help="Discover and identify rotating BLE beacons by OUI/name/decoded fields",
    )
    _add_beacon_identification_arguments(parser)
