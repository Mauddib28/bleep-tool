"""Explore subparser."""

import argparse


def register(subparsers, _subparser_map):
    explore_parser = subparsers.add_parser("explore", help="Scan & dump GATT database to JSON for offline analysis")
    explore_parser.add_argument("mac", help="Target MAC address")
    explore_parser.add_argument("--out", "--dump-json", dest="out", help="Output JSON file (default stdout)")
    explore_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose characteristic list even with handles")
    explore_parser.add_argument("--connection-mode", "--conn-mode", dest="connection_mode", choices=["passive", "naggy"], default="passive",
                                help="Connection mode: 'passive' (single attempt, default) or 'naggy' (with retries)")
    explore_parser.add_argument("--timeout", type=int, default=10, help="Scan timeout in seconds (default: 10)")
    explore_parser.add_argument("--retries", type=int, default=3, help="Number of connection retries in naggy mode (default: 3)")
    explore_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
