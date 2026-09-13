"""Connect and connect-profile subparsers."""

import argparse


def register(subparsers, _subparser_map):
    connect_parser = subparsers.add_parser("connect", help="Connect + GATT enumerate")
    connect_parser.add_argument("address", help="Target MAC address")
    connect_parser.add_argument("--ble-only", action="store_true",
                                help="Force BLE (GATT) connection even for Classic/dual devices")
    connect_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
    connect_parser.add_argument(
        "--no-profiles", dest="activate_profiles", action="store_false",
        default=True,
        help=(
            "Classic path only: skip the best-effort BlueZ profile "
            "activation after RFCOMM bring-up."
        ),
    )

    prof_parser = subparsers.add_parser(
        "connect-profile",
        help="Connect or disconnect a specific Bluetooth profile by UUID",
    )
    prof_parser.add_argument("address", help="Target MAC address")
    prof_parser.add_argument("uuid", help="Profile UUID to connect/disconnect")
    prof_parser.add_argument("--disconnect", action="store_true",
                             help="Disconnect the profile instead of connecting")
    prof_parser.add_argument("--adapter", default=None, help="Bluetooth adapter (e.g. hci0)")
    _subparser_map["connect-profile"] = prof_parser
