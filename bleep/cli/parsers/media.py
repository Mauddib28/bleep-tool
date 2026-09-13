"""Media enumeration and media control subparsers."""

import argparse


def register(subparsers, _subparser_map):
    media_parser = subparsers.add_parser("media-enum", help="Connect and enumerate media device capabilities")
    media_parser.add_argument("address", help="Target MAC address")
    media_parser.add_argument("--connect-via", choices=["auto", "ble", "classic"], default="auto",
                              help="Connection strategy: 'auto' selects based on device type, "
                                   "'ble' forces the GATT-oriented path (works for Classic devices "
                                   "when host audio stack is present), 'classic' forces a BR/EDR "
                                   "Device1.Connect() path (default: auto)")
    media_parser.add_argument("--verbose", action="store_true", help="Include detailed track and transport information")
    media_parser.add_argument("--browse", action="store_true", help="List top-level folder contents if player is browsable")
    media_parser.add_argument("--passive", action="store_true",
                              help="Passive recon only: assess media capabilities from "
                                   "cached Device1 properties without connecting")
    media_parser.add_argument("--monitor", action="store_true", help="Monitor media status changes")
    media_parser.add_argument("--duration", type=int, default=30, help="Duration to monitor in seconds (with --monitor)")
    media_parser.add_argument("--interval", type=int, default=2, help="Polling interval in seconds (with --monitor)")

    media_ctrl = subparsers.add_parser("media-ctrl", help="Control AVRCP playback and volume")
    media_ctrl.add_argument("address", help="Target MAC address")
    media_ctrl.add_argument("action", choices=["play", "pause", "stop", "next", "previous", "volume", "info", "press"], help="Control action")
    media_ctrl.add_argument("--value", help="Value for commands: volume (0-127) or press (key code, can be hex with 0x prefix)")
