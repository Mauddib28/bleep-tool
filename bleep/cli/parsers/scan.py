"""Scan and enum-scan subparsers."""

import argparse


def register(subparsers, _subparser_map):
    scan_parser = subparsers.add_parser("scan", help="BLE scan (passive, naggy, pokey, or brute via --variant)")
    scan_parser.add_argument("-d", "--device",
                             help="Client-side filter: display and return only this MAC "
                                  "(BlueZ has no address-level discovery filter). All "
                                  "discovered devices are still recorded to the database "
                                  "unless --record-target-only is given.")
    scan_parser.add_argument("--record-target-only", action="store_true",
                             help="With -d/--device, also restrict database recording to "
                                  "the target (default records all discovered devices).")
    scan_parser.add_argument("--timeout", type=int, default=10, help="Scan duration (s)")
    scan_parser.add_argument("--variant", choices=["passive", "naggy", "pokey", "brute"], default="passive", help="Scan variant")
    scan_parser.add_argument("--transport", choices=["auto", "le", "bredr"], default="auto",
                             help="Transport type: auto (LE+BR/EDR), le, bredr (default: auto)")
    scan_parser.add_argument("--target", help="Target MAC for pokey mode", default=None)
    scan_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
    scan_parser.add_argument("--monitor", action="store_true",
                             help="AdvertisementMonitor Flags-OR overlay (one monitor, GAP Flags) "
                                  "instead of StartDiscovery; requires bluetoothd -E; not a BlueZ match-all")

    enum_scan = subparsers.add_parser("enum-scan", help="Run enumeration helpers with variant")
    enum_scan.add_argument("address", help="Target MAC address")
    enum_scan.add_argument("--variant", choices=["passive", "naggy", "pokey", "brute"], default="passive")
    enum_scan.add_argument("--rounds", type=int, default=3, help="Rounds for pokey variant")
    enum_scan.add_argument("--write-char", help="Characteristic UUID for brute variant")
    enum_scan.add_argument("--range", help="Hex start-end (e.g. 00-FF) for brute payload range")
    enum_scan.add_argument("--patterns", help="Comma patterns: ascii,inc,alt,repeat:<byte>:<len>,hex:<hex>")
    enum_scan.add_argument("--payload-file", help="Binary payload file path")
    enum_scan.add_argument("--force", action="store_true", help="Ignore landmine/permission map for brute writes")
    enum_scan.add_argument("--verify", action="store_true", help="Read back after each brute write")
    enum_scan.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
