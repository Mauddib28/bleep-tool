"""Interactive and user subparsers."""

import argparse


def register(subparsers, _subparser_map):
    subparsers.add_parser("interactive", help="Interactive REPL console")

    user_parser = subparsers.add_parser("user", help="User-friendly interface for Bluetooth exploration")
    user_parser.add_argument("--device", type=str, help="MAC address of device to connect to")
    user_parser.add_argument("--scan", type=int, help="Run a scan for the specified number of seconds before starting")
    user_parser.add_argument("--menu", action="store_true", help="Start in menu mode (default is interactive shell)")
