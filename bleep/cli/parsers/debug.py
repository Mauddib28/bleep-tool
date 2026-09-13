"""Debug subparser."""

import argparse


def register(subparsers, _subparser_map):
    debug_parser = subparsers.add_parser(
        "debug",
        help="Interactive debug shell (low-level D-Bus, GATT, media, classic)",
    )
    debug_parser.add_argument(
        "device", nargs="?", help="MAC address of device to connect to"
    )
    debug_parser.add_argument(
        "-m", "--monitor", action="store_true",
        help="Monitor device properties in real-time",
    )
    debug_parser.add_argument(
        "-n", "--no-connect", action="store_true",
        help="Don't connect to device (just open the shell)",
    )
    debug_parser.add_argument(
        "-d", "--detailed", action="store_true",
        help="Show detailed information including decoded UUIDs and handle information",
    )
