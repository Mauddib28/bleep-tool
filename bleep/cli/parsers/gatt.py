"""GATT enumeration and GATT server subparsers."""

import argparse


def register(subparsers, _subparser_map):
    gatt_parser = subparsers.add_parser("gatt-enum", help="Connect and enumerate GATT database")
    gatt_parser.add_argument("address", help="Target MAC address")
    gatt_parser.add_argument("--deep", action="store_true", help="Perform deep enumeration (retry reads, descriptor probing)")
    gatt_parser.add_argument("--report", action="store_true", help="Print landmine & security reports instead of raw maps")
    gatt_parser.add_argument("--correlate", action="store_true",
                             help="If the target resolves no GATT (e.g. a dual-mode device whose "
                                  "GATT lives under an LE resolvable-private address), heuristically "
                                  "correlate by Name/Icon/Class to a candidate LE address and retry. "
                                  "Opt-in and non-merging: presented as a hint, never auto-merged.")
    gatt_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    gs_parser = subparsers.add_parser("gatt-server", help="GATT Server: publish local BLE services")
    gs_sub = gs_parser.add_subparsers(dest="gs_action", help="GATT server action")

    gs_start = gs_sub.add_parser("start", help="Register a GATT application and serve until Ctrl-C")
    gs_start.add_argument("--uuid", action="append", default=None,
                          help="Service UUID (repeatable; adds a primary service per UUID)")
    gs_start.add_argument("--name", default=None,
                          help="Device Name characteristic value for GAP service")
    gs_start.add_argument("--read-value", default=None,
                          help="Hex value returned by all read-capable characteristics")
    gs_start.add_argument("--duration", type=int, default=None,
                          help="Local stop timer in seconds (default: run until Ctrl-C)")
    gs_start.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
