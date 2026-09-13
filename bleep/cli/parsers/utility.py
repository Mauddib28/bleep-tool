"""Utility subparsers: uuid-translate, adapter-config, advertise-monitor,
advertise, signal, signal-config, device-sets, mesh, ctf."""

import argparse


def _add_advertise_monitor_start_arguments(parser):
    """Shared option builder for the Advertisement Monitor ``start`` action.

    Consumed by both the CLI ``advertise-monitor start`` subparser and the debug
    shell ``advertise-monitor start`` adapter (``bleep.modes.debug_advmon``) so
    the two surfaces cannot drift on pattern / RSSI / duration options (CDU-M2).
    """
    parser.add_argument("-p", "--pattern", dest="patterns", action="append", metavar="OFF:AD:HEX",
                        help="Pattern offset:ad_type:hex_content (repeatable). "
                             "Omit to inject Flags-OR overlay (one monitor, GAP Flags "
                             "00/02/04/05/06/18/1A; not a BlueZ match-all)")
    parser.add_argument("--manufacturer", dest="manufacturers", action="append",
                        metavar="CID[:HEX]",
                        help="Manufacturer AD (0xFF) filter: company id, optional payload "
                             "hex prefix (repeatable). CID decimal or 0x-hex, little-endian "
                             "on the wire. With no -p, replaces Flags-OR")
    parser.add_argument("--mfr-string", dest="mfr_strings", action="append",
                        metavar="TEXT",
                        help="UTF-8 string in manufacturer payload after the 2-byte CID "
                             "(AD 0xFF offset 2, repeatable). With no -p, replaces Flags-OR")
    parser.add_argument("--rssi-high", type=int, default=None, help="RSSI high threshold dBm (-127..20)")
    parser.add_argument("--rssi-high-timeout", type=int, default=0, help="Seconds device must exceed high threshold (1-300)")
    parser.add_argument("--rssi-low", type=int, default=None, help="RSSI low threshold dBm (-127..20)")
    parser.add_argument("--rssi-low-timeout", type=int, default=0, help="Seconds device must stay below low threshold (1-300)")
    parser.add_argument("--sampling-period", type=int, default=0, help="RSSI sampling period (0=report all)")
    parser.add_argument("--duration", type=int, default=None, help="Auto-stop after N seconds (default: run until Ctrl-C)")
    parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
    return parser


def register(subparsers, _subparser_map):
    # uuid-translate
    uuid_parser = subparsers.add_parser("uuid-translate", help="Translate UUID(s) to human-readable format", aliases=["uuid-lookup"])
    uuid_parser.add_argument("uuids", nargs="+", help="UUID(s) to translate (16-bit, 32-bit, or 128-bit format)")
    uuid_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    uuid_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed information including source databases")
    uuid_parser.add_argument("--include-unknown", action="store_true", help="Include 'Unknown' entries in results")

    # adapter-config
    aconf_parser = subparsers.add_parser("adapter-config", help="View or modify local Bluetooth adapter configuration")
    aconf_sub = aconf_parser.add_subparsers(dest="action", help="Configuration action")

    aconf_show = aconf_sub.add_parser("show", help="Show all adapter properties and boot defaults")
    aconf_show.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    aconf_get = aconf_sub.add_parser("get", help="Get a single adapter property value")
    aconf_get.add_argument("property", help="Property name (e.g. alias, name, class, powered, discoverable)")
    aconf_get.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    aconf_set = aconf_sub.add_parser("set", help="Set an adapter property")
    aconf_set.add_argument("property", help="Property to set (alias, discoverable, pairable, connectable, "
                           "discoverable-timeout, pairable-timeout, class, local-name, ssp, sc, le, bredr, "
                           "privacy, fast-conn, linksec, wbs)")
    aconf_set.add_argument("values", nargs="+", help="Value(s) to set")
    aconf_set.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # advertise-monitor (CDU-M2: hard rename from `monitor`; no alias)
    mon_parser = subparsers.add_parser("advertise-monitor", help="Advertisement Monitor: kernel-offloaded pattern scanning")
    mon_sub = mon_parser.add_subparsers(dest="monitor_action", help="Advertisement Monitor action")

    mon_caps = mon_sub.add_parser("caps", help="Show AdvertisementMonitorManager1 capabilities")
    mon_caps.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    mon_start = mon_sub.add_parser("start", help="Register monitors and stream DeviceFound/Lost events")
    _add_advertise_monitor_start_arguments(mon_start)

    # advertise
    adv_parser = subparsers.add_parser("advertise", help="LE Advertising: broadcast custom BLE advertisements")
    adv_sub = adv_parser.add_subparsers(dest="adv_action", help="Advertise action")

    adv_caps = adv_sub.add_parser("caps", help="Show LEAdvertisingManager1 capabilities")
    adv_caps.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    adv_start = adv_sub.add_parser("start", help="Register an advertisement and broadcast")
    adv_start.add_argument("--type", choices=["peripheral", "broadcast"], default="peripheral",
                           help="Advertisement type (default: peripheral)")
    adv_start.add_argument("-u", "--uuid", action="append", metavar="UUID",
                           help="Service UUID to advertise (repeatable)")
    adv_start.add_argument("-m", "--manufacturer-data", action="append", metavar="CID:HEX",
                           help="Manufacturer data as COMPANY_ID:HEX_DATA (repeatable)")
    adv_start.add_argument("-s", "--service-data", action="append", metavar="UUID:HEX",
                           help="Service data as UUID:HEX_DATA (repeatable)")
    adv_start.add_argument("-n", "--name", default=None, help="Local name to advertise")
    adv_start.add_argument("--appearance", type=int, default=None,
                           help="GAP Appearance value (uint16) sent in the advertisement (self-contained)")
    adv_start.add_argument("--discoverable", type=lambda v: v.lower() in ("true", "1", "yes"),
                           default=None, help="Advertise as general discoverable (true/false)")
    adv_start.add_argument("--tx-power", type=int, default=None, help="Requested TX power in dBm (-127..20)")
    adv_start.add_argument("--min-interval", type=int, default=None, help="Min advertising interval in ms (20-10485000)")
    adv_start.add_argument("--max-interval", type=int, default=None, help="Max advertising interval in ms (20-10485000)")
    adv_start.add_argument("--secondary-channel", choices=["1M", "2M", "Coded"], default=None,
                           help="Secondary advertising channel PHY")
    adv_start.add_argument("--include-tx-power", action="store_true",
                           help="Ask BlueZ to include the adapter's TX power in the advertisement")
    adv_start.add_argument("--include-appearance", action="store_true",
                           help="Ask BlueZ to include the adapter/system Appearance (needs a system "
                                "value; use --appearance for a self-contained value)")
    adv_start.add_argument("--include-name", action="store_true",
                           help="Ask BlueZ to include the adapter alias as local-name (use --name for "
                                "a self-contained value)")
    adv_start.add_argument("--duration", type=int, default=None,
                           help="BlueZ-level advertisement timeout in seconds (auto-removes)")
    adv_start.add_argument("--local-duration", type=int, default=None,
                           help="Local stop timer in seconds (default: run until Ctrl-C)")
    adv_start.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # signal
    sig_parser = subparsers.add_parser("signal", help="Listen for notifications")
    sig_parser.add_argument("mac", help="Target MAC address")
    sig_parser.add_argument("char", help="Characteristic UUID or char handle")
    sig_parser.add_argument("--time", type=int, default=30, help="Listen duration seconds")
    sig_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # signal-config
    sigconf_parser = subparsers.add_parser("signal-config", help="Manage signal capture configurations")
    sigconf_parser.add_argument("command", nargs="?", help="Sub-command (if omitted, shows help)")
    sigconf_parser.add_argument("args", nargs=argparse.REMAINDER, help="Command arguments")

    # device-sets
    ds_parser = subparsers.add_parser("device-sets", help="DeviceSet1: manage coordinated device sets (TWS earbuds)")
    ds_sub = ds_parser.add_subparsers(dest="ds_action", help="Device set action")

    ds_list = ds_sub.add_parser("list", help="List discovered device sets")
    ds_list.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    ds_connect = ds_sub.add_parser("connect", help="Connect all members of a device set")
    ds_connect.add_argument("set_path", help="D-Bus path of the device set (e.g. /org/bluez/hci0/set_abcd)")
    ds_connect.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    ds_disconnect = ds_sub.add_parser("disconnect", help="Disconnect all members of a device set")
    ds_disconnect.add_argument("set_path", help="D-Bus path of the device set")
    ds_disconnect.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    ds_info = ds_sub.add_parser("info", help="Show details for a specific device set")
    ds_info.add_argument("set_path", help="D-Bus path of the device set")
    ds_info.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # mesh
    mesh_parser = subparsers.add_parser("mesh", help="Bluetooth Mesh provisioning (experimental)")
    mesh_sub = mesh_parser.add_subparsers(dest="mesh_action", help="Mesh action")

    mesh_join = mesh_sub.add_parser("join", help="Join a mesh network")
    mesh_join.add_argument("uuid", help="128-bit device UUID (hex, 32 chars)")
    mesh_join.add_argument("--io", default="cli", choices=["cli", "auto"], help="OOB IO handler (default: cli)")
    mesh_join.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    mesh_prov = mesh_sub.add_parser("provision", help="Provision a remote device")
    mesh_prov.add_argument("uuid", help="128-bit unprovisioned device UUID (hex, 32 chars)")
    mesh_prov.add_argument("--io", default="cli", choices=["cli", "auto"], help="OOB IO handler (default: cli)")
    mesh_prov.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    mesh_reprov = mesh_sub.add_parser("reprovision", help="Re-provision a remote node")
    mesh_reprov.add_argument("unicast", type=lambda x: int(x, 0), help="Unicast address (hex or decimal)")
    mesh_reprov.add_argument("--node-path", required=True, help="Node object path")
    mesh_reprov.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # refresh-refs
    refs_parser = subparsers.add_parser(
        "refresh-refs",
        help="Regenerate committed reference data (BT SIG assigned numbers, vendor/community "
             "adv specs, IEEE OUI + USB-IF registries)",
    )
    refs_group = refs_parser.add_mutually_exclusive_group()
    refs_group.add_argument("--sig-only", action="store_true",
                            help="Only refresh BT SIG assigned numbers (bt_ref/uuids.py)")
    refs_group.add_argument("--vendor-only", action="store_true",
                            help="Only refresh vendor/community adv specs (bt_ref/vendor_adv_specs.py)")
    refs_group.add_argument("--oui-only", action="store_true",
                            help="Only refresh the IEEE OUI vendor database (bt_ref/oui.py)")
    refs_group.add_argument("--usb-only", action="store_true",
                            help="Only refresh the USB-IF ID database (bt_ref/usb_ids.py)")
    refs_parser.add_argument("--local-path", default=None,
                             help="Bootstrap vendor specs from a local device-library checkout "
                                  "(dev only; default pulls from the public repo)")

    # ctf
    ctf_parser = subparsers.add_parser("ctf", help="BLE CTF challenge solver and analyzer")
    ctf_parser.add_argument("--device", type=str, default="CC:50:E3:B6:BC:A6",
                            help="MAC address of BLE CTF device (default: CC:50:E3:B6:BC:A6)")
    ctf_parser.add_argument("--discover", action="store_true",
                            help="Automatically discover and analyze flags")
    ctf_parser.add_argument("--solve", action="store_true",
                            help="Automatically solve all flags")
    ctf_parser.add_argument("--visualize", action="store_true",
                            help="Generate a visual representation of flag status")
    ctf_parser.add_argument("--interactive", action="store_true",
                            help="Start interactive CTF shell")
