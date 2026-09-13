"""Classic Bluetooth subparsers."""

import argparse


def _add_classic_scan_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Attach the canonical Classic-scan option set to *parser*.

    Single source of truth shared by the CLI ``classic-scan`` subparser
    (:func:`register`) and the debug-shell ``cscan`` command
    (``bleep.modes.debug_classic.cmd_cscan``, which parses via ``parse_as_cli``
    and delegates to the same ``classic_scan.run``) so the two cannot drift on
    the discovery-filter / timeout / adapter options (CDU-M7a).
    """
    parser.add_argument("--timeout", type=int, default=10, help="Scan timeout seconds")
    parser.add_argument(
        "--uuid",
        help="Comma-separated list of UUID filters (e.g. 112f,110b). BlueZ will only report devices advertising at least one of them.",
    )
    parser.add_argument("--rssi", type=int, help="RSSI threshold: ignore devices weaker than this (dBm)")
    parser.add_argument("--pathloss", type=int, help="Path-loss threshold in dB (BlueZ >=5.59)")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable verbose debug output")
    parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
    return parser


def _add_pbap_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Attach the canonical PBAP option set to *parser*.

    Single source of truth shared by the CLI ``classic-pbap`` subparser
    (:func:`register`) and the debug-shell ``pbap`` command
    (``bleep.modes.debug_classic.cmd_pbap``) so the two cannot drift.  The
    canonical ``--watchdog`` default is **30 s** (the safe CLI value; the debug
    shell previously used 8 s, which silently aborted long phonebook pulls).

    The target MAC is surface-specific — CLI positional ``address`` vs. the
    debug shell's connected-device context — and is intentionally NOT added
    here.
    """
    parser.add_argument("--out", default=None,
                        help="Output VCF path (single PB repo only)")
    parser.add_argument("--repos", default="PB",
                        help="Comma-separated repo list (PB,ICH,…) or ALL")
    parser.add_argument("--format", choices=["vcard21", "vcard30"],
                        default="vcard21", help="vCard format")
    parser.add_argument("--auto-auth", action="store_true",
                        help="Register temporary OBEX agent that auto-accepts "
                             "authentication/prompts")
    parser.add_argument("--watchdog", type=int, default=30,
                        help="Watchdog seconds before aborting stalled transfer "
                             "(0 to disable)")
    return parser


def register(subparsers, _subparser_map):
    # #16: OBEX --save-dir was only accepted *before* the action token because
    # it lived on the profile's parent parser; once argparse consumed the
    # sub-action (e.g. `pull`) it routed remaining flags to the sub-action
    # parser, which rejected --save-dir. This shared parent lets the flag be
    # given *after* the action too. default=SUPPRESS means it never clobbers a
    # value already set on the parent parser (so both orderings work).
    _savedir_parent = argparse.ArgumentParser(add_help=False)
    _savedir_parent.add_argument(
        "--save-dir", dest="save_dir", default=argparse.SUPPRESS,
        help="Override default receive directory for downloaded files",
    )

    # classic-scan
    cscan_parser = subparsers.add_parser("classic-scan", help="Passive Classic (BR/EDR) scan")
    _add_classic_scan_arguments(cscan_parser)

    # classic-enum
    cen_parser = subparsers.add_parser("classic-enum", help="Enumerate Classic RFCOMM services")
    cen_parser.add_argument("address", help="Target MAC address")
    cen_parser.add_argument("--debug", "-d", action="store_true", help="Enable verbose debug output")
    cen_parser.add_argument("--connectionless", action="store_true", help="Verify device reachability via l2ping before SDP query (faster failure detection)")
    cen_parser.add_argument("--version-info", action="store_true", help="Display Bluetooth version information (HCI/LMP versions, vendor/product IDs, profile versions)")
    cen_parser.add_argument("--analyze", action="store_true", help="Perform comprehensive SDP analysis (protocol analysis, version inference, anomaly detection); combine with --version-info for LMP cross-validation")
    cen_parser.add_argument(
        "--sdp-source",
        choices=["auto", "dbus", "browse", "xml", "records", "merge", "all"],
        default="auto",
        help=(
            "SDP discovery source (default: auto = first-success chain, "
            "unchanged behaviour). 'merge'/'all' query every source and union "
            "records with per-field provenance + source_discrepancy anomalies"
        ),
    )
    cen_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # classic-connect
    ccon_parser = subparsers.add_parser("classic-connect", help="Connect to a Classic device via SDP + RFCOMM")
    ccon_parser.add_argument("address", help="Target Bluetooth MAC address")
    ccon_parser.add_argument("--check", action="store_true", help="Check pair/connection status only")
    ccon_parser.add_argument("--no-pair", action="store_true", help="Skip auto-pair — fail if not paired")
    ccon_parser.add_argument("--channel", type=int, default=None, help="Specific RFCOMM channel (default: first from SDP)")
    ccon_parser.add_argument("--keep", action="store_true", help="Hold RFCOMM socket open (blocks until Ctrl+C)")
    ccon_parser.add_argument("--timeout", type=int, default=60, help="Pairing timeout in seconds")
    ccon_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
    ccon_parser.add_argument(
        "--no-profiles", dest="activate_profiles", action="store_false",
        default=True,
        help=(
            "Skip the best-effort BlueZ Device1.Connect() that attaches "
            "profile handlers after RFCOMM bring-up."
        ),
    )

    # classic-pbap
    pbap_parser = subparsers.add_parser(
        "classic-pbap",
        help="Download phone-book via PBAP (RFCOMM) and save to VCF",
    )
    pbap_parser.add_argument("address", help="Target MAC address")
    _add_pbap_arguments(pbap_parser)

    # classic-opp
    opp_parser = subparsers.add_parser(
        "classic-opp",
        help="Send a file or pull a business card via Object Push Profile",
    )
    opp_parser.add_argument("address", help="Target MAC address")
    opp_parser.add_argument("--save-dir", default=None, help="Override default receive directory for downloaded files")
    opp_sub = opp_parser.add_subparsers(dest="action", help="OPP action")
    opp_send = opp_sub.add_parser("send", help="Send a file to the remote device", parents=[_savedir_parent])
    opp_send.add_argument("file", help="Local file path to send")
    opp_send.add_argument("--timeout", type=int, default=120, help="Transfer timeout in seconds")
    opp_pull = opp_sub.add_parser("pull", help="Pull the default business card", parents=[_savedir_parent])
    opp_pull.add_argument("--out", default=None, help="Destination VCF path")
    opp_pull.add_argument("--timeout", type=int, default=60, help="Transfer timeout in seconds")
    opp_exchange = opp_sub.add_parser("exchange", help="Push local vCard, pull remote card", parents=[_savedir_parent])
    opp_exchange.add_argument("file", help="Local vCard file to push")
    opp_exchange.add_argument("--out", default=None, help="Destination path for remote card")
    opp_exchange.add_argument("--timeout", type=int, default=120, help="Transfer timeout in seconds")
    _subparser_map["classic-opp"] = opp_parser

    # classic-map
    map_parser = subparsers.add_parser(
        "classic-map",
        help="Browse and manage SMS/MMS via Message Access Profile",
    )
    map_parser.add_argument("address", help="Target MAC address")
    map_parser.add_argument("--save-dir", default=None, help="Override default receive directory for downloaded files")
    map_parser.add_argument(
        "--instance", type=int, default=None,
        help="RFCOMM channel of a specific MAS instance (use 'instances' to discover)",
    )
    map_sub = map_parser.add_subparsers(dest="action", help="MAP action")
    map_sub.add_parser("folders", help="List message folders")
    map_list = map_sub.add_parser("list", help="List messages in a folder")
    map_list.add_argument("folder", nargs="?", default="inbox", help="Folder name (default: inbox)")
    map_list.add_argument("--type", dest="msg_type", default=None, help="Filter by type (e.g. SMS, MMS)")
    map_list.add_argument("-v", "--verbose", dest="map_verbose", action="store_true",
                          help="Show additional message fields (Sender, DateTime, Type)")
    map_get = map_sub.add_parser("get", help="Download a message by handle")
    map_get.add_argument("handle", help="Message handle")
    map_get.add_argument("--out", default=None, help="Destination file path")
    map_get.add_argument(
        "--folder", default="",
        help="Folder containing the message (e.g. telecom/msg/inbox); required "
             "so obexd can materialise the message object before download",
    )
    map_push = map_sub.add_parser("push", help="Push/send a message file")
    map_push.add_argument("file", help="Local bMessage file path")
    map_push.add_argument("folder", nargs="?", default="telecom/msg/outbox", help="Target folder")
    map_sub.add_parser("inbox", help="Trigger inbox update on remote device")
    map_sub.add_parser("types", help="List supported message types")
    map_sub.add_parser("fields", help="List available filter fields")
    map_monitor = map_sub.add_parser("monitor", help="Monitor incoming message notifications (MNS)")
    map_monitor.add_argument("--timeout", type=int, default=300, help="Session timeout in seconds")
    map_sub.add_parser("instances", help="Discover MAS instances via SDP")
    _subparser_map["classic-map"] = map_parser

    # classic-ftp
    ftp_parser = subparsers.add_parser(
        "classic-ftp",
        help="Browse and transfer files via OBEX File Transfer Profile",
    )
    ftp_parser.add_argument("address", help="Target MAC address")
    ftp_parser.add_argument("--save-dir", default=None, help="Override default receive directory for downloaded files")
    ftp_sub = ftp_parser.add_subparsers(dest="action", help="FTP action")
    ftp_ls = ftp_sub.add_parser("ls", help="List remote folder contents")
    ftp_ls.add_argument("path", nargs="?", default="", help="Remote folder path")
    ftp_get = ftp_sub.add_parser("get", help="Download a file from the remote device")
    ftp_get.add_argument("remote", help="Remote file name")
    ftp_get.add_argument("--out", default=None, help="Local destination path")
    ftp_get.add_argument("--path", dest="remote_path", default="", help="Remote folder to navigate to first")
    ftp_get.add_argument("--timeout", type=int, default=120, help="Transfer timeout in seconds")
    ftp_put = ftp_sub.add_parser("put", help="Upload a file to the remote device")
    ftp_put.add_argument("file", help="Local file path to upload")
    ftp_put.add_argument("--name", default="", help="Remote file name (default: same as local)")
    ftp_put.add_argument("--path", dest="remote_path", default="", help="Remote folder to navigate to first")
    ftp_put.add_argument("--timeout", type=int, default=120, help="Transfer timeout in seconds")
    ftp_mkdir = ftp_sub.add_parser("mkdir", help="Create a folder on the remote device")
    ftp_mkdir.add_argument("name", help="Folder name to create")
    ftp_mkdir.add_argument("--path", dest="remote_path", default="", help="Remote folder to navigate to first")
    ftp_rm = ftp_sub.add_parser("rm", help="Delete a file or folder on the remote device")
    ftp_rm.add_argument("name", help="File or folder name to delete")
    ftp_rm.add_argument("--path", dest="remote_path", default="", help="Remote folder to navigate to first")
    _subparser_map["classic-ftp"] = ftp_parser

    # classic-pan
    pan_parser = subparsers.add_parser(
        "classic-pan",
        help="Personal Area Networking – connect, disconnect, or host (server-reg) PAN profiles",
    )
    pan_sub = pan_parser.add_subparsers(dest="action", help="PAN action")
    pan_connect = pan_sub.add_parser("connect", help="Connect to a remote PAN device")
    pan_connect.add_argument("address", help="Target MAC address")
    pan_connect.add_argument("--role", default="nap", choices=["nap", "panu", "gn"],
                             help="PAN role (default: nap)")
    pan_connect.add_argument("--no-preflight", action="store_true",
                             help="Skip the PAN prerequisite check (bnep module, adapter)")
    pan_connect.add_argument("--trust", action="store_true",
                             help="Mark the device Trusted during the pre-connect check")
    pan_connect.add_argument("--no-fallback", action="store_true",
                             help="Do not fall back to Device1.ConnectProfile on NotSupported")
    pan_disconnect = pan_sub.add_parser("disconnect", help="Disconnect from a PAN device")
    pan_disconnect.add_argument("address", help="Target MAC address")
    pan_status = pan_sub.add_parser("status", help="Show Network1 properties for a device")
    pan_status.add_argument("address", help="Target MAC address")
    pan_monitor = pan_sub.add_parser(
        "monitor",
        help="Live-stream Network1 state changes (event-driven, no polling)",
    )
    pan_monitor.add_argument("address", help="Target MAC address")
    pan_monitor.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
    pan_monitor.add_argument("--timeout", type=float, default=None,
                             help="Stop after N seconds (default: run until Ctrl-C)")
    # CDU-M1.5: hard rename serve/unserve -> server-reg/server-unreg (no alias)
    # for reader clarity; uniform with the debug shell's `cpan server-reg`.
    pan_serve = pan_sub.add_parser("server-reg", help="Register a local PAN server (one or more roles)")
    pan_serve.add_argument("--role", action="append", choices=["nap", "panu", "gn"],
                           default=None,
                           help="PAN role; repeat to host several (default: nap)")
    pan_serve.add_argument("--all", dest="all_roles", action="store_true",
                           help="Host all PAN roles (nap, gn, panu) on the bridge")
    pan_serve.add_argument("--bridge", default="pan0",
                           help="Bridge interface name (default: pan0)")
    pan_serve.add_argument("--no-preflight", action="store_true",
                           help="Skip the PAN prerequisite check (bnep module, adapter, bridge)")
    pan_serve.add_argument("--authorize", action="store_true",
                           help="Register a default agent to observe/authorize inbound "
                                "BNEP clients while hosting (runs a GLib loop)")
    pan_unserve = pan_sub.add_parser("server-unreg", help="Unregister a local PAN server (one or more roles)")
    pan_unserve.add_argument("--role", action="append", choices=["nap", "panu", "gn"],
                             default=None,
                             help="PAN role; repeat to remove several (default: nap)")
    pan_unserve.add_argument("--all", dest="all_roles", action="store_true",
                             help="Unregister all PAN roles (nap, gn, panu)")
    _subparser_map["classic-pan"] = pan_parser

    # network-enum
    nenum_parser = subparsers.add_parser(
        "network-enum",
        help="Enumerate PAN network capability across adapters and devices",
    )
    nenum_parser.add_argument("--adapter", default=None,
                              help="Restrict to a single adapter (e.g. hci0)")
    nenum_parser.add_argument("--json", action="store_true", help="Output as JSON")
    nenum_parser.add_argument("--all-devices", action="store_true",
                              help="Include devices without network capability")
    _subparser_map["network-enum"] = nenum_parser

    # classic-spp
    spp_parser = subparsers.add_parser(
        "classic-spp",
        help="Register an SPP serial port profile and wait for connections",
    )
    spp_sub = spp_parser.add_subparsers(dest="action", help="SPP action")
    spp_register = spp_sub.add_parser("register", help="Register SPP profile and block for connections")
    spp_register.add_argument("--channel", type=int, default=None,
                              help="RFCOMM channel (default: auto-assigned)")
    spp_register.add_argument("--name", default="BLEEP SPP", help="Profile name")
    spp_register.add_argument("--role", default="server", choices=["server", "client"],
                              help="Profile role (default: server)")
    spp_register.add_argument("--auth", action="store_true", default=True,
                              help="Require authentication (default)")
    spp_register.add_argument("--no-auth", action="store_true", default=False,
                              help="Do not require authentication")
    spp_sub.add_parser("unregister", help="Unregister SPP profile")
    spp_sub.add_parser("status", help="Show SPP profile status")
    _subparser_map["classic-spp"] = spp_parser

    # classic-sync
    sync_parser = subparsers.add_parser(
        "classic-sync",
        help="IrMC Synchronization – download or upload phonebook (OBEX Sync)",
    )
    sync_parser.add_argument("address", help="Target MAC address")
    sync_parser.add_argument("--save-dir", default=None, help="Override default receive directory for downloaded files")
    sync_sub = sync_parser.add_subparsers(dest="action", help="Sync action")
    sync_get = sync_sub.add_parser("get", help="Download phonebook from device")
    sync_get.add_argument("--output", default="", help="Local file path (default: auto)")
    sync_get.add_argument("--location", default="int",
                          help="Object store: 'int' (internal, default) or 'sim1', 'sim2', …")
    sync_get.add_argument("--timeout", type=int, default=60, help="Transfer timeout in seconds")
    sync_put = sync_sub.add_parser("put", help="Upload phonebook to device")
    sync_put.add_argument("file", help="Local VCF file to upload")
    sync_put.add_argument("--location", default="int",
                          help="Object store: 'int' (internal, default) or 'sim1', 'sim2', …")
    sync_put.add_argument("--timeout", type=int, default=60, help="Transfer timeout in seconds")
    _subparser_map["classic-sync"] = sync_parser

    # classic-bip
    bip_parser = subparsers.add_parser(
        "classic-bip",
        help="Basic Imaging Profile – image properties / download / thumbnail [experimental]",
    )
    bip_parser.add_argument("address", help="Target MAC address")
    bip_parser.add_argument("--save-dir", default=None, help="Override default receive directory for downloaded files")
    bip_sub = bip_parser.add_subparsers(dest="action", help="BIP action")
    bip_sub.add_parser("list", help="How to discover image handles (informational)")
    bip_props = bip_sub.add_parser("props", help="Get image properties for a handle")
    bip_props.add_argument("handle", help="Image handle (e.g. '1000001')")
    bip_props.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")
    bip_get = bip_sub.add_parser("get", help="Download full image by handle")
    bip_get.add_argument("handle", help="Image handle")
    bip_get.add_argument("--output", default="", help="Local file path (default: auto)")
    bip_get.add_argument("--timeout", type=int, default=60, help="Transfer timeout in seconds")
    bip_thumb = bip_sub.add_parser("thumb", help="Download image thumbnail by handle")
    bip_thumb.add_argument("handle", help="Image handle")
    bip_thumb.add_argument("--output", default="", help="Local file path (default: auto)")
    bip_thumb.add_argument("--timeout", type=int, default=60, help="Transfer timeout in seconds")
    _subparser_map["classic-bip"] = bip_parser

    # classic-ping
    cping_parser = subparsers.add_parser("classic-ping", help="L2CAP echo (l2ping) reachability test")
    cping_parser.add_argument("address", help="Target MAC address")
    cping_parser.add_argument("--count", type=int, default=3, help="Echo count")
    cping_parser.add_argument("--timeout", type=int, default=13, help="Seconds before aborting l2ping command")
    cping_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # classic-rfcomm
    crfcomm_parser = subparsers.add_parser("classic-rfcomm", help="Enumerate and optionally probe RFCOMM channels via SDP")
    crfcomm_parser.add_argument("address", help="Target MAC address")
    crfcomm_parser.add_argument("--probe", action="store_true", help="Probe each RFCOMM channel for terminal/serial/SSH endpoints")
    crfcomm_parser.add_argument("--bind", type=int, metavar="CHANNEL", default=None, help="Bind /dev/rfcomm0 to the specified RFCOMM channel")
    crfcomm_parser.add_argument("--device-id", type=int, default=0, help="Device index N for /dev/rfcommN (default: 0)")
    crfcomm_parser.add_argument("--timeout", type=float, default=4.0, help="Per-channel probe timeout (seconds, default: 4.0)")
    crfcomm_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # hid-info
    hid_parser = subparsers.add_parser(
        "hid-info",
        help="Classify a device as a Human Interface Device (keyboard, mouse, etc.)",
    )
    hid_parser.add_argument("address", help="Target MAC address")
    hid_parser.add_argument("--adapter", default=None, help="Bluetooth adapter (e.g. hci0)")
    hid_parser.add_argument("--connect", action="store_true",
                            help="Connect first to harvest richer evidence "
                                 "(Input1.ReconnectMode); default is connectionless "
                                 "classification from cached discovery props")
    _subparser_map["hid-info"] = hid_parser
