"""
Command-line interface for BLEEP.
"""

import argparse
import signal
import shutil
import sys
import os

# Ensure logging subsystem (and legacy /tmp files) is initialised immediately
import bleep.core.log  # noqa: F401  # side-effect import creates symlinks/files

from . import __version__


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="BLEEP - Bluetooth Landscape Exploration & Enumeration Platform"
    )
    parser.add_argument("--version", action="version", version=f"BLEEP {__version__}")
    parser.add_argument("--check-env", action="store_true", 
                       help="Check environment capabilities (tools, configs, dependencies)")
    parser.add_argument("--diagnose-audio", action="store_true",
                       help="Run detailed audio stack diagnostic and show install guidance")

    # Add subparsers for different modes
    subparsers = parser.add_subparsers(dest="mode", help="Operation mode")

    # Interactive mode (default)
    subparsers.add_parser("interactive", help="Interactive REPL console")

    # Debug mode (interactive low-level shell)
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

    # Scan mode
    scan_parser = subparsers.add_parser("scan", help="Passive BLE scan")
    scan_parser.add_argument("-d", "--device", help="Target MAC address to filter")
    scan_parser.add_argument("--timeout", type=int, default=10, help="Scan duration (s)")
    scan_parser.add_argument("--variant", choices=["passive", "naggy", "pokey", "brute"], default="passive", help="Scan variant")
    scan_parser.add_argument("--transport", choices=["auto", "le", "bredr"], default="auto",
                             help="Transport type: auto (LE+BR/EDR), le, bredr (default: auto)")
    scan_parser.add_argument("--target", help="Target MAC for pokey mode", default=None)
    scan_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # Connect mode
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

    # GATT enumeration (quick / deep)
    gatt_parser = subparsers.add_parser("gatt-enum", help="Connect and enumerate GATT database")
    gatt_parser.add_argument("address", help="Target MAC address")
    gatt_parser.add_argument("--deep", action="store_true", help="Perform deep enumeration (retry reads, descriptor probing)")
    gatt_parser.add_argument("--report", action="store_true", help="Print landmine & security reports instead of raw maps")
    gatt_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # Enumeration scan variants
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
    enum_scan.add_argument("--controlled", action="store_true", help="Use EnumerationController for structured multi-attempt enumeration with error annotations")
    enum_scan.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # Media device enumeration
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

    # Media control
    media_ctrl = subparsers.add_parser("media-ctrl", help="Control AVRCP playback and volume")
    media_ctrl.add_argument("address", help="Target MAC address")
    media_ctrl.add_argument("action", choices=["play", "pause", "stop", "next", "previous", "volume", "info", "press"], help="Control action")
    media_ctrl.add_argument("--value", help="Value for commands: volume (0-127) or press (key code, can be hex with 0x prefix)")

    # Audio profile identification
    audio_profiles = subparsers.add_parser("audio-profiles", help="List Bluetooth audio profiles via ALSA correlation")
    audio_profiles.add_argument("--device", help="Filter by device MAC address")

    # Audio playback
    audio_play = subparsers.add_parser("audio-play", help="Play audio file to Bluetooth device")
    audio_play.add_argument("device", help="Target device MAC address")
    audio_play.add_argument("file", help="Audio file path")
    audio_play.add_argument("--volume", type=int, help="Volume (0-127)")
    audio_play.add_argument("--codec", choices=["SBC", "MP3", "AAC"], help="Codec preference (if supported)")
    audio_play.add_argument("--direct", action="store_true", help="Acquire an existing transport directly instead of registering a BLEEP-owned endpoint (requires audio daemon stopped)")
    audio_play.add_argument("--system", action="store_true", help="Play via system audio tools (paplay/pw-play/aplay) through the host audio daemon — no D-Bus transport acquisition needed")
    audio_play.add_argument("--force-endpoint", action="store_true", help="Bypass the MediaEndpoint1 contention pre-flight (use when a competing daemon is known to release the endpoint during the cycle)")

    # Audio recording
    audio_record = subparsers.add_parser("audio-record", help="Record audio from Bluetooth device")
    audio_record.add_argument("device", help="Source device MAC address")
    audio_record.add_argument("output", help="Output file path")
    audio_record.add_argument("--duration", type=int, help="Duration in seconds")
    audio_record.add_argument("--direct", action="store_true", help="Acquire an existing transport directly instead of registering a BLEEP-owned endpoint (requires audio daemon stopped)")
    audio_record.add_argument("--system", action="store_true", help="Record via system audio tools (parecord/pw-record/arecord) through the host audio daemon — no D-Bus transport acquisition needed")
    audio_record.add_argument("--force-endpoint", action="store_true", help="Bypass the MediaEndpoint1 contention pre-flight (use when a competing daemon is known to release the endpoint during the cycle)")

    # Audio recon (enumerate cards/profiles, play/record, sox analysis)
    audio_recon = subparsers.add_parser("audio-recon", help="Audio recon: enumerate BlueZ cards/profiles, play test file, record, analyse with sox")
    audio_recon.add_argument("--device", help="Filter by device MAC address")
    audio_recon.add_argument("--test-file", help="Path to test audio file for playback to sinks")
    audio_recon.add_argument("--no-play", action="store_true", help="Skip playing test file to sinks")
    audio_recon.add_argument("--no-record", action="store_true", help="Skip recording from sources/sinks")
    audio_recon.add_argument("--out", dest="output_json", help="Write structured result to JSON file")
    audio_recon.add_argument("--record-dir", default="/tmp", help="Directory for recordings (default: /tmp)")
    audio_recon.add_argument("--duration", type=int, default=8, help="Recording duration per interface in seconds (default: 8)")

    # Amusica – audio target discovery & manipulation
    amusica_parser = subparsers.add_parser(
        "amusica", help="Amusica: scan, connect, recon, and manipulate Bluetooth audio targets",
    )
    amusica_parser.add_argument(
        "amusica_args", nargs=argparse.REMAINDER,
        help="Subcommand and arguments (scan, halt, control, inject, record, status). Use 'bleep amusica --help' for details.",
    )

    # Agent mode
    agent_parser = subparsers.add_parser("agent", help="Run pairing agent")
    agent_parser.add_argument("--mode", choices=["simple", "interactive", "enhanced", "pairing"], 
                             default="simple", help="Agent mode: simple, interactive, enhanced, or pairing")
    agent_parser.add_argument("--cap", choices=["none", "display", "yesno", "keyboard", "kbdisp"], 
                             default="none", help="Agent capabilities: none, display, yesno, keyboard, kbdisp")
    agent_parser.add_argument("--default", action="store_true", 
                             help="Request as default agent")
    agent_parser.add_argument("--auto-accept", action="store_true", default=True,
                             help="Auto-accept pairing requests (for enhanced and pairing agents)")
    agent_parser.add_argument("--pair", metavar="MAC", 
                             help="Pair with a device (only in pairing mode)")
    agent_parser.add_argument("--trust", metavar="MAC", 
                             help="Set a device as trusted")
    agent_parser.add_argument("--untrust", metavar="MAC", 
                             help="Set a device as untrusted")
    agent_parser.add_argument("--list-trusted", action="store_true", 
                             help="List all trusted devices")
    agent_parser.add_argument("--list-bonded", action="store_true", 
                             help="List all bonded devices (with stored keys)")
    agent_parser.add_argument("--remove-bond", metavar="MAC", 
                             help="Remove bonding information for a device")
    agent_parser.add_argument("--storage-path", 
                             help="Path to store bonding information")
    agent_parser.add_argument("--timeout", type=int, default=30,
                             help="Timeout for pairing operations (seconds)")
    agent_parser.add_argument("--status", action="store_true",
                             help="Check BLEEP agent registration status")
    agent_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # Pair mode
    pair_parser = subparsers.add_parser("pair", help="Pair with a Bluetooth device")
    pair_parser.add_argument("address", help="Target Bluetooth MAC address")
    pair_parser.add_argument("--pin", default=None,
                             help="PIN code for legacy pairing (default: 0000)")
    pair_parser.add_argument("--passkey", type=int, default=None,
                             help="Numeric passkey for SSP pairing (0–999999)")
    pair_parser.add_argument("--interactive", action="store_true",
                             help="Prompt for PIN / passkey / confirmation at runtime")
    pair_parser.add_argument("--check", action="store_true",
                             help="Check pairing state only – do not pair")
    pair_parser.add_argument("--reset", action="store_true",
                             help="Force-remove existing bond before pairing")
    pair_parser.add_argument("--no-connect", action="store_true",
                             help="Pair only – do not attempt a post-pair connection")
    pair_parser.add_argument("--no-trust", action="store_true",
                             help="Do not set the device as trusted after pairing")
    pair_parser.add_argument("--brute", action="store_true",
                             help="Brute-force PIN codes")
    pair_parser.add_argument("--passkey-brute", action="store_true",
                             help="Brute-force numeric passkeys")
    pair_parser.add_argument("--range", default=None, dest="pin_range",
                             help="PIN/passkey range, e.g. 0000-9999 or 0-999999")
    pair_parser.add_argument("--pin-list", default=None,
                             help="File containing one PIN per line")
    pair_parser.add_argument("--delay", type=float, default=0.5,
                             help="Delay between brute-force attempts (s)")
    pair_parser.add_argument("--max-attempts", type=int, default=0,
                             help="Maximum brute-force attempts (0 = unlimited)")
    pair_parser.add_argument("--lockout-cooldown", type=float, default=60.0,
                             help="Cooldown after lockout detection (s)")
    pair_parser.add_argument("--max-lockout-retries", type=int, default=3,
                             help="Maximum retries after lockout")
    pair_parser.add_argument("--probe", action="store_true",
                             help="Discover auth method by cycling IO capabilities")
    pair_parser.add_argument("--cap", default="KeyboardDisplay",
                             choices=["NoInputNoOutput", "DisplayOnly", "DisplayYesNo",
                                      "KeyboardOnly", "KeyboardDisplay"],
                             help="BlueZ IO capability for the pairing agent")
    pair_parser.add_argument("--timeout", type=int, default=60,
                             help="Pairing timeout in seconds")
    pair_parser.add_argument("--adapter", default="hci0",
                             help="Adapter name (default: hci0)")

    # Explore mode
    explore_parser = subparsers.add_parser("explore", help="Scan & dump GATT database to JSON for offline analysis")
    explore_parser.add_argument("mac", help="Target MAC address")
    explore_parser.add_argument("--out", "--dump-json", dest="out", help="Output JSON file (default stdout)")
    explore_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose characteristic list even with handles")
    explore_parser.add_argument("--connection-mode", "--conn-mode", dest="connection_mode", choices=["passive", "naggy"], default="passive", 
                             help="Connection mode: 'passive' (single attempt, default) or 'naggy' (with retries)")
    explore_parser.add_argument("--timeout", type=int, default=10, help="Scan timeout in seconds (default: 10)")
    explore_parser.add_argument("--retries", type=int, default=3, help="Number of connection retries in naggy mode (default: 3)")
    explore_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # DB (observation) commands
    db_parser = subparsers.add_parser("db", help="Query local observation database")
    db_parser.add_argument("action", choices=["list", "show", "export", "timeline"], help="Action to perform")
    db_parser.add_argument("mac", nargs="?", help="Target MAC for show/export/timeline")
    db_parser.add_argument("--out", dest="out", help="Output file for export")
    db_parser.add_argument("--status", help="Filter devices by status: recent,ble,classic,media (comma-separated)")
    db_parser.add_argument("--fields", help="Comma-separated list of device fields to print (for list action)")
    db_parser.add_argument("--service", help="Filter timeline by service UUID")
    db_parser.add_argument("--char", help="Filter timeline by characteristic UUID")
    db_parser.add_argument("--limit", type=int, default=50, help="Maximum entries to show in timeline (default: 50)")

    # Analysis mode
    analysis_parser = subparsers.add_parser("analyse", help="Post-process JSON dumps", aliases=["analyze"])
    analysis_parser.add_argument("files", nargs="+", help="JSON dump files to analyse")
    analysis_parser.add_argument("--detailed", "-d", action="store_true", help="Show detailed analysis including characteristics")

    # AoI mode
    aoi_parser = subparsers.add_parser("aoi", help="Process Assets-of-Interest JSON list (supports multiple subcommands)")
    aoi_parser.add_argument("files", nargs="*", 
        help="First argument can be a subcommand (scan, analyze, list, report, export) followed by files or options")
    aoi_parser.add_argument("-f", "--file", dest="test_file", help="AoI test file to scan")
    aoi_parser.add_argument("--delay", type=float, default=4.0, help="Delay between devices (for scan subcommand)")
    # Options for analyze/report/export subcommands
    aoi_parser.add_argument("--address", "-a", help="MAC address for analyze/report/export subcommands")
    aoi_parser.add_argument("--deep", action="store_true", help="Perform deeper analysis (for analyze subcommand)")
    aoi_parser.add_argument("--timeout", type=int, help="Analysis timeout in seconds (for analyze subcommand)")
    aoi_parser.add_argument("--format", choices=["markdown", "json", "text"], help="Report format (for report subcommand)")
    aoi_parser.add_argument("--output", "-o", help="Output file/directory (for report/export subcommands)")

    # Signal mode
    sig_parser = subparsers.add_parser("signal", help="Listen for notifications")
    sig_parser.add_argument("mac", help="Target MAC address")
    sig_parser.add_argument("char", help="Characteristic UUID or char handle")
    sig_parser.add_argument("--time", type=int, default=30, help="Listen duration seconds")
    sig_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
    
    # User mode
    user_parser = subparsers.add_parser("user", help="User-friendly interface for Bluetooth exploration")
    user_parser.add_argument("--device", type=str, help="MAC address of device to connect to")
    user_parser.add_argument("--scan", type=int, help="Run a scan for the specified number of seconds before starting")
    user_parser.add_argument("--menu", action="store_true", help="Start in menu mode (default is interactive shell)")

    # Signal configuration mode
    sigconf_parser = subparsers.add_parser("signal-config", help="Manage signal capture configurations")
    sigconf_parser.add_argument("command", nargs="?", help="Sub-command (if omitted, shows help)")
    sigconf_parser.add_argument("args", nargs=argparse.REMAINDER, help="Command arguments")

    # UUID translation mode
    uuid_parser = subparsers.add_parser("uuid-translate", help="Translate UUID(s) to human-readable format", aliases=["uuid-lookup"])
    uuid_parser.add_argument("uuids", nargs="+", help="UUID(s) to translate (16-bit, 32-bit, or 128-bit format)")
    uuid_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    uuid_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed information including source databases")
    uuid_parser.add_argument("--include-unknown", action="store_true", help="Include 'Unknown' entries in results")

    # Classic scan
    cscan_parser = subparsers.add_parser("classic-scan", help="Passive Classic (BR/EDR) scan")
    cscan_parser.add_argument("--timeout", type=int, default=10, help="Scan timeout seconds")
    cscan_parser.add_argument(
        "--uuid",
        help="Comma-separated list of UUID filters (e.g. 112f,110b). BlueZ will only report devices advertising at least one of them.",
    )
    cscan_parser.add_argument("--rssi", type=int, help="RSSI threshold: ignore devices weaker than this (dBm)")
    cscan_parser.add_argument("--pathloss", type=int, help="Path-loss threshold in dB (BlueZ >=5.59)")
    cscan_parser.add_argument("--debug", "-d", action="store_true", help="Enable verbose debug output")
    cscan_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # Classic enumerate
    cen_parser = subparsers.add_parser("classic-enum", help="Enumerate Classic RFCOMM services")
    cen_parser.add_argument("address", help="Target MAC address")
    cen_parser.add_argument("--debug", "-d", action="store_true", help="Enable verbose debug output")
    cen_parser.add_argument("--connectionless", action="store_true", help="Verify device reachability via l2ping before SDP query (faster failure detection)")
    cen_parser.add_argument("--version-info", action="store_true", help="Display Bluetooth version information (HCI/LMP versions, vendor/product IDs, profile versions)")
    cen_parser.add_argument("--analyze", action="store_true", help="Perform comprehensive SDP analysis (protocol analysis, version inference, anomaly detection)")
    cen_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # Classic connect (SDP + RFCOMM — bypasses Device1.Connect profile requirement)
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
    # Phonebook dump
    pbap_parser = subparsers.add_parser(
        "classic-pbap",
        help="Download phone-book via PBAP (RFCOMM) and save to VCF",
    )
    pbap_parser.add_argument("address", help="Target MAC address")
    pbap_parser.add_argument("--out", help="Output VCF path (single PB repo only)", default=None)
    pbap_parser.add_argument("--repos", help="Comma-separated repo list (PB,ICH,…) or ALL", default="PB")
    pbap_parser.add_argument("--format", choices=["vcard21", "vcard30"], default="vcard21", help="vCard format")
    pbap_parser.add_argument("--auto-auth", action="store_true", help="Register temporary OBEX agent that auto-accepts authentication/prompts")
    pbap_parser.add_argument("--watchdog", type=int, default=30, help="Watchdog seconds before aborting stalled transfer (0 to disable)")

    # OPP CLI
    opp_parser = subparsers.add_parser(
        "classic-opp",
        help="Send a file or pull a business card via Object Push Profile",
    )
    opp_parser.add_argument("address", help="Target MAC address")
    opp_parser.add_argument("--save-dir", default=None, help="Override default receive directory for downloaded files")
    opp_sub = opp_parser.add_subparsers(dest="action", help="OPP action")
    opp_send = opp_sub.add_parser("send", help="Send a file to the remote device")
    opp_send.add_argument("file", help="Local file path to send")
    opp_send.add_argument("--timeout", type=int, default=120, help="Transfer timeout in seconds")
    opp_pull = opp_sub.add_parser("pull", help="Pull the default business card")
    opp_pull.add_argument("--out", default=None, help="Destination VCF path")
    opp_pull.add_argument("--timeout", type=int, default=60, help="Transfer timeout in seconds")
    opp_exchange = opp_sub.add_parser("exchange", help="Push local vCard, pull remote card")
    opp_exchange.add_argument("file", help="Local vCard file to push")
    opp_exchange.add_argument("--out", default=None, help="Destination path for remote card")
    opp_exchange.add_argument("--timeout", type=int, default=120, help="Transfer timeout in seconds")

    # MAP CLI
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
    map_folders = map_sub.add_parser("folders", help="List message folders")
    map_list = map_sub.add_parser("list", help="List messages in a folder")
    map_list.add_argument("folder", nargs="?", default="inbox", help="Folder name (default: inbox)")
    map_list.add_argument("--type", dest="msg_type", default=None, help="Filter by type (e.g. SMS, MMS)")
    map_list.add_argument("-v", "--verbose", dest="map_verbose", action="store_true",
                          help="Show additional message fields (Sender, DateTime, Type)")
    map_get = map_sub.add_parser("get", help="Download a message by handle")
    map_get.add_argument("handle", help="Message handle")
    map_get.add_argument("--out", default=None, help="Destination file path")
    map_push = map_sub.add_parser("push", help="Push/send a message file")
    map_push.add_argument("file", help="Local bMessage file path")
    map_push.add_argument("folder", nargs="?", default="telecom/msg/outbox", help="Target folder")
    map_inbox = map_sub.add_parser("inbox", help="Trigger inbox update on remote device")
    map_sub.add_parser("types", help="List supported message types")
    map_sub.add_parser("fields", help="List available filter fields")
    map_monitor = map_sub.add_parser("monitor", help="Monitor incoming message notifications (MNS)")
    map_monitor.add_argument("--timeout", type=int, default=300, help="Session timeout in seconds")
    map_sub.add_parser("instances", help="Discover MAS instances via SDP")

    # FTP CLI
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

    # PAN CLI
    pan_parser = subparsers.add_parser(
        "classic-pan",
        help="Personal Area Networking – connect, disconnect, or serve PAN profiles",
    )
    pan_sub = pan_parser.add_subparsers(dest="action", help="PAN action")
    pan_connect = pan_sub.add_parser("connect", help="Connect to a remote PAN device")
    pan_connect.add_argument("address", help="Target MAC address")
    pan_connect.add_argument("--role", default="nap", choices=["nap", "panu", "gn"],
                             help="PAN role (default: nap)")
    pan_disconnect = pan_sub.add_parser("disconnect", help="Disconnect from a PAN device")
    pan_disconnect.add_argument("address", help="Target MAC address")
    pan_status = pan_sub.add_parser("status", help="Show Network1 properties for a device")
    pan_status.add_argument("address", help="Target MAC address")
    pan_serve = pan_sub.add_parser("serve", help="Register a local PAN server")
    pan_serve.add_argument("--role", default="nap", choices=["nap", "panu", "gn"],
                           help="PAN role (default: nap)")
    pan_serve.add_argument("--bridge", default="pan0",
                           help="Bridge interface name (default: pan0)")
    pan_unserve = pan_sub.add_parser("unserve", help="Unregister a local PAN server")
    pan_unserve.add_argument("--role", default="nap", choices=["nap", "panu", "gn"],
                             help="PAN role (default: nap)")

    # SPP CLI
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

    # Connect/Disconnect a specific profile by UUID
    prof_parser = subparsers.add_parser(
        "connect-profile",
        help="Connect or disconnect a specific Bluetooth profile by UUID",
    )
    prof_parser.add_argument("address", help="Target MAC address")
    prof_parser.add_argument("uuid", help="Profile UUID to connect/disconnect")
    prof_parser.add_argument("--disconnect", action="store_true",
                             help="Disconnect the profile instead of connecting")
    prof_parser.add_argument("--adapter", default=None, help="Bluetooth adapter (e.g. hci0)")

    # IrMC Synchronization CLI
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

    # Basic Imaging Profile CLI (experimental)
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

    # Classic ping
    cping_parser = subparsers.add_parser("classic-ping", help="L2CAP echo (l2ping) reachability test")
    cping_parser.add_argument("address", help="Target MAC address")
    cping_parser.add_argument("--count", type=int, default=3, help="Echo count")
    cping_parser.add_argument("--timeout", type=int, default=13, help="Seconds before aborting l2ping command")
    cping_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # Classic RFCOMM enumeration & probing
    crfcomm_parser = subparsers.add_parser("classic-rfcomm", help="Enumerate and optionally probe RFCOMM channels via SDP")
    crfcomm_parser.add_argument("address", help="Target MAC address")
    crfcomm_parser.add_argument("--probe", action="store_true", help="Probe each RFCOMM channel for terminal/serial/SSH endpoints")
    crfcomm_parser.add_argument("--bind", type=int, metavar="CHANNEL", default=None, help="Bind /dev/rfcomm0 to the specified RFCOMM channel")
    crfcomm_parser.add_argument("--device-id", type=int, default=0, help="Device index N for /dev/rfcommN (default: 0)")
    crfcomm_parser.add_argument("--timeout", type=float, default=4.0, help="Per-channel probe timeout (seconds, default: 4.0)")
    crfcomm_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
    
    # Adapter configuration
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

    # Advertisement Monitor (BZ-11/12)
    mon_parser = subparsers.add_parser("monitor", help="Advertisement Monitor: kernel-offloaded pattern scanning")
    mon_sub = mon_parser.add_subparsers(dest="monitor_action", help="Monitor action")

    mon_caps = mon_sub.add_parser("caps", help="Show AdvertisementMonitorManager1 capabilities")
    mon_caps.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    mon_start = mon_sub.add_parser("start", help="Register monitors and stream DeviceFound/Lost events")
    mon_start.add_argument("-p", "--pattern", dest="patterns", action="append", metavar="OFF:AD:HEX",
                           help="Pattern in offset:ad_type:hex_content format (repeatable)")
    mon_start.add_argument("--rssi-high", type=int, default=None, help="RSSI high threshold dBm (-127..20)")
    mon_start.add_argument("--rssi-high-timeout", type=int, default=0, help="Seconds device must exceed high threshold (1-300)")
    mon_start.add_argument("--rssi-low", type=int, default=None, help="RSSI low threshold dBm (-127..20)")
    mon_start.add_argument("--rssi-low-timeout", type=int, default=0, help="Seconds device must stay below low threshold (1-300)")
    mon_start.add_argument("--sampling-period", type=int, default=0, help="RSSI sampling period (0=report all)")
    mon_start.add_argument("--duration", type=int, default=None, help="Auto-stop after N seconds (default: run until Ctrl-C)")
    mon_start.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # LE Advertising (BZ-6/7)
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
    adv_start.add_argument("--appearance", type=int, default=None, help="GAP Appearance value (uint16)")
    adv_start.add_argument("--discoverable", type=lambda v: v.lower() in ("true", "1", "yes"),
                           default=None, help="Advertise as general discoverable (true/false)")
    adv_start.add_argument("--tx-power", type=int, default=None, help="Requested TX power in dBm (-127..20)")
    adv_start.add_argument("--min-interval", type=int, default=None, help="Min advertising interval in ms (20-10485000)")
    adv_start.add_argument("--max-interval", type=int, default=None, help="Max advertising interval in ms (20-10485000)")
    adv_start.add_argument("--secondary-channel", choices=["1M", "2M", "Coded"], default=None,
                           help="Secondary advertising channel PHY")
    adv_start.add_argument("--include-tx-power", action="store_true", help="Include tx-power in advertisement")
    adv_start.add_argument("--include-appearance", action="store_true", help="Include appearance in advertisement")
    adv_start.add_argument("--include-name", action="store_true", help="Include local-name in advertisement")
    adv_start.add_argument("--duration", type=int, default=None,
                           help="BlueZ-level advertisement timeout in seconds (auto-removes)")
    adv_start.add_argument("--local-duration", type=int, default=None,
                           help="Local stop timer in seconds (default: run until Ctrl-C)")
    adv_start.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")

    # Audio ALSA configuration
    audo_conf = subparsers.add_parser("audio-config", help="Manage ALSA/BlueALSA configuration for Bluetooth audio")
    audo_sub = audo_conf.add_subparsers(dest="action", help="Configuration action")

    audo_show = audo_sub.add_parser("show", help="Show current ALSA config entries")
    audo_show.add_argument("--path", default=None, help="Override config file path")

    audo_add = audo_sub.add_parser("add", help="Add a BlueALSA PCM device entry")
    audo_add.add_argument("address", help="Bluetooth MAC (00:00:00:00:00:00 for most-recent)")
    audo_add.add_argument("--type", dest="device_type", default="sink", choices=["sink", "source"], help="Device type (default: sink)")
    audo_add.add_argument("--path", default=None, help="Override config file path")

    audo_rm = audo_sub.add_parser("remove", help="Remove BlueALSA entries for a MAC")
    audo_rm.add_argument("address", help="Bluetooth MAC to remove")
    audo_rm.add_argument("--path", default=None, help="Override config file path")

    audo_tunnel = audo_sub.add_parser("tunnel", help="Create audio tunnel between two BT devices")
    audo_tunnel.add_argument("source", help="Source device MAC")
    audo_tunnel.add_argument("sink", help="Sink device MAC")
    audo_tunnel.add_argument("--path", default=None, help="Override config file path")

    audo_backup = audo_sub.add_parser("backup", help="Backup current ALSA config")
    audo_backup.add_argument("--path", default=None, help="Override config file path")

    audo_restore = audo_sub.add_parser("restore", help="Restore ALSA config from latest backup")
    audo_restore.add_argument("--path", default=None, help="Override config file path")

    # BLE CTF mode
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

    _subparser_map = {
        "classic-opp": opp_parser,
        "classic-map": map_parser,
        "classic-ftp": ftp_parser,
        "classic-pan": pan_parser,
        "classic-spp": spp_parser,
        "classic-sync": sync_parser,
        "classic-bip": bip_parser,
        "connect-profile": prof_parser,
    }

    # HID Info CLI
    hid_parser = subparsers.add_parser(
        "hid-info",
        help="Classify a device as a Human Interface Device (keyboard, mouse, etc.)",
    )
    hid_parser.add_argument("address", help="Target MAC address")
    hid_parser.add_argument("--adapter", default=None, help="Bluetooth adapter (e.g. hci0)")
    _subparser_map["hid-info"] = hid_parser

    # Audio Intercept CLI
    aint_parser = subparsers.add_parser(
        "audio-intercept",
        help="Capture and optionally transcribe audio from a Bluetooth device",
    )
    aint_parser.add_argument("address", help="Source device MAC address")
    aint_parser.add_argument("--duration", type=int, default=10, help="Capture duration in seconds (default: 10)")
    aint_parser.add_argument("--output-dir", default="/tmp", help="Directory for captured WAV (default: /tmp)")
    aint_parser.add_argument("--pcm", default=None, help="ALSA PCM device (auto-derived if omitted)")
    aint_parser.add_argument("--no-transcribe", action="store_true", help="Skip transcription step")
    aint_parser.add_argument("--engine", choices=["whisper", "vosk"], default=None,
                             help="Force transcription engine")
    _subparser_map["audio-intercept"] = aint_parser

    return parser.parse_args(args), _subparser_map


def _rebuild_debug_argv(args) -> list:
    """Translate the parsed 'debug' subcommand namespace back into the argv
    form that ``bleep.modes.debug.parse_args()`` expects, so that module
    keeps a single source of truth for its CLI surface."""
    argv: list = []
    if getattr(args, "monitor", False):
        argv.append("--monitor")
    if getattr(args, "no_connect", False):
        argv.append("--no-connect")
    if getattr(args, "detailed", False):
        argv.append("--detailed")
    device = getattr(args, "device", None)
    if device:
        argv.append(device)
    return argv


def main(args=None):
    """Main entry point for BLEEP."""
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    args, _subparsers = parse_args(args)

    # Normalize MAC address arguments to uppercase for DB/D-Bus consistency
    for _mac_attr in ("address", "target", "device", "mac",
                       "pair", "trust", "untrust", "remove_bond",
                       "source", "sink"):
        _val = getattr(args, _mac_attr, None)
        if isinstance(_val, str) and ":" in _val:
            setattr(args, _mac_attr, _val.upper())

    # Handle --check-env flag
    if args.check_env:
        from bleep.core.preflight import run_preflight_checks, print_preflight_summary
        report = run_preflight_checks(use_cache=False)
        print_preflight_summary(report)
        return 0

    # Handle --diagnose-audio flag
    if getattr(args, "diagnose_audio", False):
        from bleep.core.preflight import diagnose_audio
        diagnose_audio()
        return 0
    
    # Optional: honour BLEEP_LOG_LEVEL env var so users can tweak verbosity
    import logging as _logging, os as _os

    _lvl = _os.getenv("BLEEP_LOG_LEVEL")
    if _lvl:
        _logging.getLogger("bleep").setLevel(_lvl.upper())

    # Adapter guard for all Bluetooth-dependent modes
    _non_bt_modes = {"db", None}
    if args.mode not in _non_bt_modes:
        from bleep.core.preflight import require_adapter
        if not require_adapter():
            return 1

    from bleep.banner import print_banner
    print_banner(args.mode)

    try:
        if args.mode == "scan":
            from bleep.ble_ops.le import scan as _scan_mod

            variant = args.variant.lower()
            timeout = args.timeout
            target = args.target

            if variant == "pokey" and not target:
                print("[ERROR] --target <MAC> required for pokey scan variant", file=sys.stderr)
                return 1

            transport = args.transport

            dispatch = {
                "passive": lambda: _scan_mod.passive_scan(target, timeout, transport=transport),
                "naggy": lambda: _scan_mod.naggy_scan(target, timeout, transport=transport),
                "pokey": lambda: _scan_mod.pokey_scan(target, timeout=timeout),
                "brute": lambda: _scan_mod.brute_scan(timeout),
            }

            dispatch[variant]()
            return 0

        elif args.mode == "enum-scan":
            from bleep.ble_ops.le import scan as _scan_mod
            
            # Use EnumerationController if --controlled flag is set
            if args.controlled:
                from bleep.ble_ops.le.enum_controller import EnumerationController
                controller = EnumerationController(args.address)
                result = controller.enumerate(mode=args.variant.lower())
                
                if result.success:
                    print(f"[+] Enumeration successful: {args.address}")
                    if result.data:
                        import json
                        print(json.dumps(result.data, indent=2))
                    return 0
                else:
                    print(f"[-] Enumeration failed: {args.address}", file=sys.stderr)
                    if result.error_summary:
                        print(f"    {result.error_summary}", file=sys.stderr)
                    for annotation in result.annotations:
                        print(f"    [{annotation.error_type}] {annotation.details}", file=sys.stderr)
                    return 1

            var = args.variant.lower()
            if var == "passive":
                res = _scan_mod.passive_enum(args.address)
            elif var == "naggy":
                res = _scan_mod.naggy_enum(args.address)
            elif var == "pokey":
                res = _scan_mod.pokey_enum(args.address, rounds=args.rounds)
            elif var == "brute":
                if not args.write_char:
                    print("[!] --write-char required for brute enumeration", file=sys.stderr)
                    return 1
                vr = None
                if args.range:
                    try:
                        start_hex, end_hex = args.range.split("-")
                        vr = (int(start_hex, 16), int(end_hex, 16))
                    except ValueError:
                        print("[!] Invalid --range format, expected AA-BB", file=sys.stderr)
                        return 1

                patterns = [p.strip() for p in args.patterns.split(",") if p.strip()] if args.patterns else None

                file_bytes = None
                if args.payload_file:
                    try:
                        with open(args.payload_file, "rb") as f:
                            file_bytes = f.read()
                    except Exception as exc:
                        print(f"[!] Failed to read payload file: {exc}", file=sys.stderr)
                        return 1

                res = _scan_mod.brute_enum(
                    args.address,
                    write_char=args.write_char,
                    value_range=vr,
                    patterns=patterns,
                    payload_file=file_bytes,
                    force=args.force,
                    verify=args.verify,
                )
            
            if _obs := getattr(_scan_mod, "_obs", None):
                try:
                    _scan_mod._persist_mapping(args.address, res)
                except Exception as e:
                    from bleep.core.log import print_and_log as _pal, LOG__DEBUG as _LD
                    _pal(f"Database persistence warning: {e}", _LD)

            # Tree-formatted output for enum-scan results
            res_mapping = res.get("mapping") if isinstance(res, dict) else None
            if res_mapping:
                from bleep.ble_ops.common.conversion import format_gatt_tree
                print(format_gatt_tree(
                    res_mapping,
                    res.get("mine_map"),
                    res.get("perm_map"),
                    mac=args.address,
                    changed_chars=res.get("changed_chars"),
                    device_props=res.get("device_props"),
                ))
            else:
                print(res)
            return 0

        elif args.mode == "connect":
            # Auto-route Classic/dual devices unless --ble-only
            if not getattr(args, "ble_only", False):
                from bleep.pairing import find_device_path
                _conn_dev_path = find_device_path(args.address.strip().upper())
                if _conn_dev_path is not None:
                    from bleep.modes.debug_connect import get_device_transport
                    _conn_transport = get_device_transport(_conn_dev_path)
                    if _conn_transport in ("br-edr", "dual"):
                        from bleep.modes.classic_connect import main as _cc_main
                        cc_argv = [args.address]
                        if not getattr(args, "activate_profiles", True):
                            cc_argv.append("--no-profiles")
                        return _cc_main(cc_argv) or 0

            # BLE connection path
            try:
                from bleep.ble_ops.le.connect import (
                    connect_and_enumerate__bluetooth__low_energy as _connect_enum,
                )
                from bleep.core.errors import (
                    DeviceNotFoundError,
                    ConnectionError,
                    NotReadyError,
                    NotAuthorizedError,
                    ServicesNotResolvedError,
                )

                device, mapping, mine_map, perm_map = _connect_enum(args.address)
                print(f"[+] Successfully connected to {args.address}", file=sys.stdout)

                # Persist enumeration data to observation DB
                try:
                    from bleep.ble_ops.le.scan import _collect_device_props, _persist_mapping, _enrich_device_info_from_props
                    from bleep.core import observations as _obs_connect
                    addr = device.get_address() if hasattr(device, 'get_address') else args.address.upper()
                    name = device.get_name() if hasattr(device, 'get_name') else None
                    device_props = _collect_device_props(device)
                    device_info = {'name': name}
                    _enrich_device_info_from_props(device_info, device_props)
                    _obs_connect.upsert_device(addr, **device_info)
                    _persist_mapping(addr, mapping)
                    from bleep.analysis.device_type_classifier import DeviceTypeClassifier
                    classifier = DeviceTypeClassifier()
                    ctx = {
                        "device_class": device_info.get("device_class"),
                        "address_type": device_info.get("addr_type"),
                        "uuids": [str(u) for u in device_props.get("UUIDs", [])],
                        "connected": True,
                    }
                    cls_result = classifier.classify_with_mode(
                        mac=addr, context=ctx, scan_mode="naggy", use_database_cache=True,
                    )
                    _obs_connect.upsert_device(addr, device_type=cls_result.device_type)
                except Exception:
                    pass  # DB persistence is best-effort; connection itself succeeded

                return 0
            except DeviceNotFoundError as exc:
                print(
                    f"[!] Device {args.address} not found during scan",
                    file=sys.stderr,
                )
                print(
                    "[*] Suggestions: Ensure the device is powered on, in range, and advertising.",
                    file=sys.stderr,
                )
                print(
                    "[*] Try running 'bleep scan' first to verify the device is discoverable.",
                    file=sys.stderr,
                )
                return 1
            except NotReadyError as exc:
                print(
                    "[!] Bluetooth adapter not ready",
                    file=sys.stderr,
                )
                print(
                    "[*] Ensure the adapter is powered on: 'bluetoothctl power on'",
                    file=sys.stderr,
                )
                return 1
            except NotAuthorizedError as exc:
                print(
                    f"[!] Connection requires pairing/authorization: {exc}",
                    file=sys.stderr,
                )
                print(
                    "[*] The device may require pairing. Try pairing first or use 'bleep agent' mode.",
                    file=sys.stderr,
                )
                return 1
            except ConnectionError as exc:
                print(
                    f"[!] Connection failed: {exc}",
                    file=sys.stderr,
                )
                return 1
            except ServicesNotResolvedError as exc:
                print(
                    f"[!] Services not resolved for device {args.address}",
                    file=sys.stderr,
                )
                print(
                    "[*] The device connected but GATT services did not resolve in time.",
                    file=sys.stderr,
                )
                print(
                    "[*] This may indicate the device is slow to respond or has connectivity issues.",
                    file=sys.stderr,
                )
                return 1
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[!] Connection error: {exc}",
                    file=sys.stderr,
                )
                import traceback
                from bleep.core.log import print_and_log, LOG__DEBUG
                print_and_log(f"Traceback:\n{traceback.format_exc()}", LOG__DEBUG)
                return 1

        elif args.mode == "gatt-enum":
            from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
            from bleep.ble_ops.le import scan as _scan_mod

            device, mapping, mine_map, perm_map = _connect_enum(
                args.address,
                deep_enumeration=args.deep,
            )
            import json

            def _dump(obj):
                """Return a JSON-formatted string with sane defaults."""
                def _compact(o):
                    """Recursively convert long integer lists to a single-line string list."""
                    if isinstance(o, list):
                        # If list consists solely of byte-sized ints, render on one line for readability
                        if o and all(isinstance(x, int) and 0 <= x < 256 for x in o):
                            return "[" + ", ".join(str(x) for x in o) + "]"
                        return [_compact(v) for v in o]
                    elif isinstance(o, dict):
                        return {k: _compact(v) for k, v in o.items()}
                    return o

                compact_obj = _compact(obj)
                return json.dumps(compact_obj, indent=2, ensure_ascii=False, sort_keys=False)

            # Persist device + services/chars/descriptors to observation DB
            if not args.report and _scan_mod._obs:
                try:
                    # Persist device metadata
                    _ge_props = _scan_mod._collect_device_props(device)
                    _ge_dev_info = {"name": device.get_name() if hasattr(device, "get_name") else None}
                    _scan_mod._enrich_device_info_from_props(_ge_dev_info, _ge_props)
                    _scan_mod._obs.upsert_device(args.address.upper(), **_ge_dev_info)

                    # Persist GATT mapping (services, characteristics, descriptors)
                    _scan_mod._persist_mapping(args.address.upper(), mapping)
                    
                except Exception as e:
                    from bleep.core.log import print_and_log as _pal, LOG__DEBUG as _LD
                    _pal(f"Database persistence error: {e}", _LD)

            if args.report:
                print(
                    _dump(
                        {
                            "landmine_report": device.get_landmine_report(),
                            "security_report": device.get_security_report(),
                        }
                    )
                )
            else:
                from bleep.ble_ops.common.conversion import format_gatt_tree
                from bleep.ble_ops.le.scan import _collect_device_props
                dev_name = device.get_name() if hasattr(device, 'get_name') else getattr(device, 'name', None)
                device_props = _collect_device_props(device)
                print(format_gatt_tree(
                    mapping, mine_map, perm_map,
                    device_name=dev_name,
                    mac=args.address,
                    device_props=device_props,
                ))
            return 0
            
        elif args.mode == "media-enum":
            import json
            import time

            # Passive recon — no connection, cache-only assessment
            if getattr(args, "passive", False):
                from bleep.modes.media import enumerate_media_passive
                report = enumerate_media_passive(args.address, verbose=getattr(args, "verbose", False))
                if report:
                    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=False))
                return 0 if report else 1

            from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy as _LEDeviceCls
            from bleep.dbuslayer.media import get_player_properties_verbose, pretty_print_track_info

            connect_via = getattr(args, "connect_via", "auto")

            def _media_enum_connect_error(exc, device):
                """Print contextual error for media-enum connection failures."""
                err = str(exc).lower()
                if "br-connection-profile-unavailable" in err:
                    print(f"[-] Connection failed: br-connection-profile-unavailable")
                    print("    No host audio daemon is handling A2DP/HFP/HSP profiles.")
                    print("    Install bluez-alsa-utils, or enable PulseAudio/PipeWire")
                    print("    Bluetooth support, then retry.")
                    if device.has_media_uuids():
                        print(f"    Device advertises: {', '.join(device.get_media_uuid_names())}")
                else:
                    print(f"[-] Connection failed: {exc}")

            if connect_via == "ble":
                from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
                print(f"[*] BLE-connect to {args.address} (GATT-oriented path)")
                device, _, _, _ = _connect_enum(args.address)
                print(f"[+] Connected to {args.address}")
            else:
                label = "Classic-connect" if connect_via == "classic" else "Attempting connection"
                print(f"[*] {label} to {args.address} (Device1.Connect)")
                device = _LEDeviceCls(args.address)
                if not device.is_connected():
                    try:
                        device.connect()
                    except Exception as exc:
                        _media_enum_connect_error(exc, device)
                        return 1
                print(f"[+] Connected to {args.address}")

            if not device.is_media_device():
                if device.has_media_uuids():
                    names = device.get_media_uuid_names()
                    print(f"[!] {args.address} advertises media UUIDs ({', '.join(names)})")
                    print("    but no D-Bus media objects are present.")
                    print("    This usually means no host audio daemon is running.")
                    if connect_via == "auto":
                        print("    Try: bleep media-enum --connect-via classic " + args.address)
                        print("    Or install an audio daemon (bluez-alsa-utils / PulseAudio / PipeWire)")
                else:
                    print(f"[!] {args.address} is not a media device")
                return 1
                
            def _dump(obj):
                """Return a JSON-formatted string with sane defaults."""
                def _compact(o):
                    """Recursively convert long integer lists to a single-line string list."""
                    if isinstance(o, list):
                        # If list consists solely of byte-sized ints, render on one line for readability
                        if o and all(isinstance(x, int) and 0 <= x < 256 for x in o):
                            return "[" + ", ".join(str(x) for x in o) + "]"
                        return [_compact(v) for v in o]
                    elif isinstance(o, dict):
                        return {k: _compact(v) for k, v in o.items()}
                    return o

                compact_obj = _compact(obj)
                return json.dumps(compact_obj, indent=2, ensure_ascii=False, sort_keys=False)
                
            # Collect media device information
            media_info = {
                "device_info": {
                    "address": device.get_address(),
                    "name": device.get_name() or device.get_alias() or "Unknown",
                    "is_connected": device.is_connected(),
                },
                "media_capabilities": {
                    "has_media_control": device.get_media_control() is not None,
                    "has_media_player": device.get_media_player() is not None,
                    "has_media_endpoints": len(device.get_media_endpoints()) > 0,
                    "has_media_transports": len(device.get_media_transports()) > 0,
                }
            }
            
            # Get media player details if available
            player = device.get_media_player()
            if player:
                if args.verbose:
                    media_info["player"] = get_player_properties_verbose(player)
                else:
                    media_info["player"] = {
                        "name": player.get_name(),
                        "status": player.get_status(),
                        "type": player.get_type(),
                        "subtype": player.get_subtype(),
                        "position": player.get_position(),
                        "repeat": player.get_repeat(),
                        "shuffle": player.get_shuffle(),
                        "browsable": player.is_browsable(),
                        "searchable": player.is_searchable(),
                        "track": player.get_track(),
                    }
            
            # Get media transport details if available
            from bleep.bt_ref.constants import (
                get_profile_name as _get_profile_name,
                get_codec_name as _get_codec_name,
                PROFILE_UUID_COMPLEMENTS,
            )

            transports = device.get_media_transports()
            if transports:
                media_info["transports"] = []
                for transport in transports:
                    tp_uuid = transport.get_uuid()
                    tp_codec = transport.get_codec()
                    tp_cfg = transport.get_configuration()
                    transport_info = {
                        "path": transport.transport_path,
                        "uuid": tp_uuid,
                        "uuid_name": _get_profile_name(tp_uuid) if tp_uuid else None,
                        "role": "local",
                        "codec": tp_codec,
                        "codec_name": _get_codec_name(tp_codec) if tp_codec is not None else None,
                        "state": transport.get_state(),
                        "volume": transport.get_volume(),
                        "configuration": list(tp_cfg) if tp_cfg else None,
                        "parent_endpoint": transport.transport_path.rsplit("/", 1)[0]
                            if "/fd" in transport.transport_path else None,
                    }

                    if args.verbose:
                        transport_info["properties"] = transport.get_properties()

                    media_info["transports"].append(transport_info)

            # Get media endpoints if available
            endpoints = device.get_media_endpoints()
            if endpoints:
                media_info["endpoints"] = []
                for endpoint in endpoints:
                    ep_uuid = endpoint.get_uuid()
                    ep_codec = endpoint.get_codec()
                    ep_caps = endpoint.get_capabilities()
                    expected_transport_uuid = (
                        PROFILE_UUID_COMPLEMENTS.get(ep_uuid) if ep_uuid else None
                    )
                    endpoint_info = {
                        "path": endpoint.endpoint_path,
                        "uuid": ep_uuid,
                        "uuid_name": _get_profile_name(ep_uuid) if ep_uuid else None,
                        "role": "remote",
                        "codec": ep_codec,
                        "codec_name": _get_codec_name(ep_codec) if ep_codec is not None else None,
                        "capabilities": list(ep_caps) if ep_caps else None,
                        "delay_reporting": endpoint.supports_delay_reporting(),
                        "expected_transport_uuid": expected_transport_uuid,
                        "expected_transport_role": (
                            _get_profile_name(expected_transport_uuid)
                            if expected_transport_uuid else None
                        ),
                    }

                    if args.verbose:
                        endpoint_info["properties"] = endpoint.get_properties()

                    media_info["endpoints"].append(endpoint_info)
            
            # Full D-Bus media object tree (verbose only)
            if args.verbose:
                try:
                    from bleep.dbuslayer.media import find_media_objects
                    media_info["media_objects"] = find_media_objects()
                except Exception:
                    pass

            # Top-level folder listing (--browse)
            if args.browse and player and player.is_browsable():
                try:
                    from bleep.dbuslayer.media_browse import MediaFolder
                    playlist_path = player.get_playlist()
                    if playlist_path:
                        folder = MediaFolder(playlist_path)
                        items = folder.list_items()
                        media_info["browse"] = {
                            "folder_path": playlist_path,
                            "folder_name": folder.get_name(),
                            "number_of_items": folder.get_number_of_items(),
                            "items": [
                                {"path": p, "properties": props}
                                for p, props in items
                            ],
                        }
                except Exception:
                    pass

            # Persist device metadata to observation DB
            try:
                from bleep.ble_ops.le.scan import _collect_device_props, _enrich_device_info_from_props
                from bleep.core import observations as _obs_media
                _me_addr = device.get_address()
                _me_props = _collect_device_props(device)
                _me_dev: Dict[str, Any] = {"name": device.get_name() or device.get_alias()}
                _enrich_device_info_from_props(_me_dev, _me_props)
                _obs_media.upsert_device(_me_addr, **_me_dev)
            except Exception:
                pass

            # Monitor mode - poll for changes in media status
            if args.monitor:
                print(f"[*] Monitoring media status for {args.duration} seconds (Ctrl+C to stop)...")
                end_time = time.time() + args.duration
                
                try:
                    while time.time() < end_time:
                        if player:
                            status = player.get_status()
                            track = player.get_track()
                            
                            print(f"\r[*] Status: {status} | Track: {pretty_print_track_info(track)}", end="")
                            sys.stdout.flush()
                        
                        time.sleep(args.interval)
                    print("\n[+] Monitoring complete")
                except KeyboardInterrupt:
                    print("\n[*] Monitoring stopped by user")
            else:
                # Print the media device information as JSON
                print(_dump(media_info))
                
            return 0

        elif args.mode == "media-ctrl":
            from bleep.modes.media import control_media_device as _ctrl
            
            # Convert value based on the action type
            value = None
            if args.value is not None:
                try:
                    if args.action == "volume":
                        value = int(args.value)
                    elif args.action == "press":
                        # Handle hex values with 0x prefix
                        if args.value.lower().startswith("0x"):
                            value = int(args.value, 16)
                        else:
                            value = int(args.value)
                except ValueError as e:
                    print(f"Error parsing value: {e}", file=sys.stderr)
                    return 1
            
            success = _ctrl(args.address, args.action, value)
            return 0 if success else 1

        elif args.mode == "audio-profiles":
            from bleep.ble_ops.audio.audio_profile_correlator import AudioProfileCorrelator
            import json
            
            correlator = AudioProfileCorrelator()
            
            if args.device:
                # Get profiles for specific device
                profile_info = correlator.identify_profiles_for_device(args.device)
                print(json.dumps(profile_info, indent=2, ensure_ascii=False))
            else:
                # List all Bluetooth audio devices and their profiles
                from bleep.ble_ops.audio.audio_tools import AudioToolsHelper
                audio_tools = AudioToolsHelper()
                all_profiles = audio_tools.identify_bluetooth_profiles_from_alsa()
                
                result = {
                    "devices": {}
                }
                
                # Group by device MAC
                for profile_uuid, devices in all_profiles.items():
                    for device in devices:
                        mac = device.get("mac_address")
                        if mac:
                            if mac not in result["devices"]:
                                result["devices"][mac] = {
                                    "mac_address": mac,
                                    "profiles": []
                                }
                            result["devices"][mac]["profiles"].append({
                                "uuid": profile_uuid,
                                "profile_name": device.get("profile_name"),
                                "backend": device.get("backend"),
                                "sink_name": device.get("sink_name"),
                                "source_name": device.get("source_name"),
                            })
                
                print(json.dumps(result, indent=2, ensure_ascii=False))
            
            return 0

        elif args.mode == "audio-play":
            if getattr(args, "system", False):
                from bleep.ble_ops.audio.audio_system import system_play
                success = system_play(args.device, args.file)
                return 0 if success else 1

            from bleep.dbuslayer.media_stream import MediaStreamManager

            direct = getattr(args, "direct", False)
            force_endpoint = getattr(args, "force_endpoint", False)
            stream_manager = MediaStreamManager(
                args.device, direct=direct, force_endpoint=force_endpoint,
            )
            codec_pref = getattr(args, "codec", None)
            success = stream_manager.play_audio_file(
                args.file, volume=args.volume, codec_preference=codec_pref,
            )
            return 0 if success else 1

        elif args.mode == "audio-record":
            if getattr(args, "system", False):
                from bleep.ble_ops.audio.audio_system import system_record
                duration = getattr(args, "duration", None) or 8
                success = system_record(args.device, args.output, duration)
                return 0 if success else 1

            from bleep.dbuslayer.media_stream import MediaStreamManager
            from bleep.bt_ref.constants import A2DP_SOURCE_UUID

            direct = getattr(args, "direct", False)
            force_endpoint = getattr(args, "force_endpoint", False)
            stream_manager = MediaStreamManager(
                args.device,
                profile_uuid=A2DP_SOURCE_UUID,
                direct=direct,
                force_endpoint=force_endpoint,
            )
            success = stream_manager.record_audio(args.output, duration=args.duration)
            return 0 if success else 1

        elif args.mode == "audio-recon":
            from bleep.ble_ops.audio.audio_recon import run_audio_recon
            run_audio_recon(
                mac_filter=getattr(args, "device", None),
                test_file=getattr(args, "test_file", None),
                do_play=not getattr(args, "no_play", False),
                do_record=not getattr(args, "no_record", False),
                record_duration_sec=getattr(args, "duration", 8),
                record_dir=getattr(args, "record_dir", "/tmp"),
                output_json_path=getattr(args, "output_json", None),
            )
            return 0

        elif args.mode == "amusica":
            from bleep.modes.amusica import main as _amusica_main
            return _amusica_main(args.amusica_args)

        elif args.mode == "db":
            from bleep.modes import db as _db_mode
            subargv = [args.action]
            if args.mac:
                subargv.append(args.mac)
            if args.out:
                subargv += ["--out", args.out]
            if args.action == "list":
                if getattr(args, "status", None):
                    subargv += ["--status", args.status]
                if getattr(args, "fields", None):
                    subargv += ["--fields", args.fields]
            elif args.action == "timeline":
                if getattr(args, "service", None):
                    subargv += ["--service", args.service]
                if getattr(args, "char", None):
                    subargv += ["--char", args.char]
                if getattr(args, "limit", None):
                    subargv += ["--limit", str(args.limit)]
            return _db_mode.main(subargv)

        elif len(sys.argv) > 1 and sys.argv[1] == "agent":
            from bleep.modes.agent import main as _agent_main
            agent_args = sys.argv[2:] if len(sys.argv) > 2 else []
            return _agent_main(agent_args) or 0

        elif len(sys.argv) > 1 and sys.argv[1] == "pair":
            from bleep.modes.pair import main as _pair_main
            pair_args = sys.argv[2:] if len(sys.argv) > 2 else []
            return _pair_main(pair_args) or 0

        elif len(sys.argv) > 1 and sys.argv[1] == "classic-connect":
            from bleep.modes.classic_connect import main as _cc_main
            cc_args = sys.argv[2:] if len(sys.argv) > 2 else []
            return _cc_main(cc_args) or 0

        elif args.mode == "user":
            from bleep.modes.user import main as _user_main
            
            opts = []
            if args.device:
                opts += ["--device", args.device]
            if args.scan:
                opts += ["--scan", str(args.scan)]
            if args.menu:
                opts.append("--menu")
                
            return _user_main(opts) or 0

        elif args.mode == "explore":
            # For the explore command, we need to override sys.argv
            #import sys
            original_argv = sys.argv
            
            # Build new argv for the exploration module
            new_argv = ["bleep-explore"]
            new_argv.extend(["-d", args.mac])
            
            # Set timeout parameter (defaults to 10 seconds)
            timeout = getattr(args, "timeout", 10)
            new_argv.extend(["-t", str(timeout)])
            
            # Use specified connection mode and retries
            connection_mode = getattr(args, "connection_mode", "passive")
            new_argv.extend(["-m", connection_mode])
            
            if connection_mode == "naggy":
                retries = getattr(args, "retries", 3)
                new_argv.extend(["-r", str(retries)])
            
            if args.out:
                new_argv.extend(["--out", args.out])
            if args.verbose:
                new_argv.append("--verbose")
            
            # Override sys.argv temporarily
            sys.argv = new_argv
            
            # Import and run the exploration main function
            try:
                from bleep.modes.exploration import main as _exp_main
                result = _exp_main() or 0
            finally:
                # Restore original sys.argv
                sys.argv = original_argv
                
            return result

        elif args.mode in ["analyse", "analyze"]:
            from bleep.modes.analysis import main as _an_main
            
            # Build arguments list for the analysis module
            analysis_args = args.files.copy()
            if args.detailed:
                analysis_args.append("--detailed")
            
            return _an_main(analysis_args) or 0

        elif args.mode == "aoi":
            from bleep.modes.aoi import main as _aoi_main
            #import sys  # Ensure sys is available in this scope

            # Check if the first argument is a recognized subcommand
            known_subcommands = ["scan", "analyze", "list", "report", "export", "db"]
            
            # Initialize opts list for arguments to pass to _aoi_main
            opts = []
            
            # Process AOI subcommands
            if args.files and args.files[0] in known_subcommands:
                # Use the first argument as the subcommand
                subcommand = args.files[0]
                opts = [subcommand] + list(args.files[1:])
                
                # Add appropriate options based on subcommand
                if subcommand == "scan" and hasattr(args, 'delay'):
                    opts += ["--delay", str(args.delay)]
                
                # For analyze subcommand, pass the address and other options
                if subcommand == "analyze" and args.address:
                    opts += ["--address", args.address]
                    if args.deep:
                        opts += ["--deep"]
                    if args.timeout:
                        opts += ["--timeout", str(args.timeout)]
                
                # For report subcommand
                if subcommand == "report" and args.address:
                    opts += ["--address", args.address]
                    if args.format:
                        opts += ["--format", args.format]
                    if args.output:
                        opts += ["--output", args.output]
                        
                # For export subcommand
                if subcommand == "export" and args.address:
                    opts += ["--address", args.address]
                    if args.output:
                        opts += ["--output", args.output]
            else:
                # Combine positional files and file parameter
                files_list = list(args.files)
                if args.test_file:
                    files_list.append(args.test_file)
                    
                if not files_list:
                    print("Error: No files specified or valid subcommand provided.", file=sys.stderr)
                    print("Available subcommands: scan, analyze, list, report, export", file=sys.stderr)
                    return 1
                    
                # The AOI module expects a subcommand first, so we add "scan" as the default subcommand when files are provided
                opts = ["scan"] + files_list
                if hasattr(args, 'delay'):
                    opts += ["--delay", str(args.delay)]
            
            # Pass all arguments to the AOI main function
            return _aoi_main(opts) or 0

        elif args.mode == "signal":
            from bleep.modes.signal import main as _sig_main

            opts = [args.mac, args.char, "--time", str(args.time)]
            return _sig_main(opts) or 0
            
        elif args.mode == "signal-config":
            from bleep.signals.cli import main as _sigconf_main
            
            # If no command provided, show help
            if not args.command:
                return _sigconf_main(["--help"])
            
            # Pass the command and args
            opts = [args.command] + args.args
            return _sigconf_main(opts) or 0

        elif args.mode in ["uuid-translate", "uuid-lookup"]:
            from bleep.modes.uuid_translate import main as _uuid_translate_main
            
            # Build arguments list
            uuid_opts = list(args.uuids)
            if args.json:
                uuid_opts.append("--json")
            if args.verbose:
                uuid_opts.append("--verbose")
            if getattr(args, "include_unknown", False):
                uuid_opts.append("--include-unknown")
            
            return _uuid_translate_main(uuid_opts) or 0

        elif args.mode == "classic-scan":
            # Use the adapter directly to avoid pulling in BLE-specific
            # device-manager wrappers (which cause a circular import during
            # classic-only operations).
            from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
            from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
            import dbus

            adapter = _Adapter()
            if not adapter.is_ready():
                print("[!] Bluetooth adapter not ready", file=sys.stderr)
                return 1

            # Enable debug output if requested
            debug_mode = getattr(args, "debug", False)
            if debug_mode:
                print_and_log("[classic-scan] Debug mode enabled", LOG__GENERAL)
                print_and_log("[classic-scan] Using adapter: " + adapter.adapter_path, LOG__GENERAL)

            # Build discovery filter dict
            _f = {"Transport": "bredr"}
            if getattr(args, "uuid", None):
                uuids = [u.strip().lower() for u in args.uuid.split(",") if u.strip()]
                if uuids:
                    _f["UUIDs"] = dbus.Array(uuids, signature="s")  # type: ignore[name-defined]
                    if debug_mode:
                        print_and_log(f"[classic-scan] Filtering for UUIDs: {', '.join(uuids)}", LOG__GENERAL)
            if args.rssi is not None:
                _f["RSSI"] = dbus.Int16(args.rssi)  # type: ignore[name-defined]
                if debug_mode:
                    print_and_log(f"[classic-scan] RSSI threshold set to: {args.rssi} dBm", LOG__GENERAL)
            if args.pathloss is not None:
                _f["Pathloss"] = dbus.UInt16(args.pathloss)  # type: ignore[name-defined]
                if debug_mode:
                    print_and_log(f"[classic-scan] Pathloss threshold set to: {args.pathloss} dB", LOG__GENERAL)

            try:
                adapter.set_discovery_filter(_f)
                log_level = LOG__GENERAL if debug_mode else LOG__DEBUG
                print_and_log("[classic-scan] Applied discovery filter: " + str(_f), log_level)
            except Exception as exc:
                # Older BlueZ versions may lack SetDiscoveryFilter – continue but log.
                log_level = LOG__GENERAL if debug_mode else LOG__DEBUG
                print_and_log(
                    f"[classic-scan] SetDiscoveryFilter failed ({exc.__class__.__name__}: {exc}); proceeding without filter",
                    log_level,
                )

            if debug_mode:
                print_and_log(f"[classic-scan] Starting scan for {args.timeout} seconds...", LOG__GENERAL)

            # Timed discovery using the adapter's built-in helper.
            adapter.run_scan__timed(duration=args.timeout)

            if debug_mode:
                print_and_log("[classic-scan] Scan completed, processing results...", LOG__GENERAL)

            devices = [d for d in adapter.get_discovered_devices() if d["type"].lower() == "br/edr"]

            if not devices:
                print("No Classic devices found")
            else:
                if debug_mode:
                    print_and_log(f"[classic-scan] Found {len(devices)} Classic BR/EDR devices", LOG__GENERAL)
                
                for d in devices:
                    name = d["name"] or d["alias"] or "(unknown)"
                    rssi = d.get("rssi")
                    rssi_str = f"RSSI={rssi}" if rssi is not None else "RSSI=?"
                    print(f"{d['address']}  Name={name}  {rssi_str}")
                    
                    # Print additional details in debug mode
                    if debug_mode:
                        # Print device class if available
                        if d.get("device_class"):
                            try:
                                from bleep.ble_ops.common.conversion import format_device_class
                                class_info = format_device_class(d["device_class"])
                                print(f"  Class: 0x{d['device_class']:06x} ({class_info})")
                            except Exception:
                                print(f"  Class: 0x{d['device_class']:06x}")
                        
                        # Print UUIDs if available
                        if "uuids" in d and d["uuids"]:
                            print(f"  UUIDs: {', '.join(d['uuids'])}")
                            
                        # Print services if available
                        if "services" in d and d["services"]:
                            print(f"  Services: {len(d['services'])}")
                            
                        print()  # Add a blank line between devices for readability

            # Persist discovered Classic devices to observation DB
            if devices:
                try:
                    from bleep.core import observations as _obs_cscan
                    for d in devices:
                        addr = d.get("address")
                        if not addr or addr == "??":
                            continue
                        _cscan_info = {
                            "name": d.get("name") or d.get("alias"),
                            "rssi_last": d.get("rssi"),
                            "device_class": d.get("device_class"),
                            "addr_type": d.get("address_type"),
                            "device_type": "classic",
                        }
                        if d.get("tx_power") is not None:
                            _cscan_info["tx_power"] = int(d["tx_power"])
                        if d.get("appearance") is not None:
                            _cscan_info["appearance"] = int(d["appearance"])
                        if d.get("modalias"):
                            _cscan_info["modalias"] = str(d["modalias"])
                        if d.get("icon"):
                            _cscan_info["icon"] = str(d["icon"])
                        _obs_cscan.upsert_device(addr, **_cscan_info)
                except Exception as db_exc:
                    print_and_log(f"[classic-scan] DB persistence warning: {db_exc}", LOG__DEBUG)

            return 0

        elif args.mode == "classic-enum":
            from bleep.ble_ops import connect_and_enumerate__bluetooth__classic as _c_enum
            from bleep.ble_ops.classic.sdp import discover_services_sdp
            from bleep.ble_ops.classic.version import (
                query_hci_version,
                map_lmp_version_to_spec,
                map_profile_version_to_spec,
            )
            from bleep.analysis.sdp_analyzer import SDPAnalyzer, analyze_sdp_records
            from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic
            from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
            from typing import Dict, Any
            import json
            
            # Enable debug output if requested
            debug_mode = getattr(args, "debug", False)
            version_info_mode = getattr(args, "version_info", False)
            analyze_mode = getattr(args, "analyze", False)
            if debug_mode:
                print_and_log("[classic-enum] Debug mode enabled", LOG__GENERAL)
                print_and_log(f"[classic-enum] Enumerating SDP records for {args.address}", LOG__GENERAL)
                # Set logging level to DEBUG for this session
                import logging
                logging.getLogger("bleep").setLevel(logging.DEBUG)
                # Also enable DEBUG messages to print to stdout
                print("[*] Debug output enabled - check /tmp/bti__logging__debug.txt for detailed logs")
            
            # Get version information if requested
            version_info_data: Dict[str, Any] = {}
            if version_info_mode:
                try:
                    # Get device version info from D-Bus
                    device = system_dbus__bluez_device__classic(args.address)
                    version_info_data = device.get_device_version_info()
                    
                    # Query local HCI adapter version (for reference)
                    hci_info = query_hci_version()
                    if hci_info:
                        version_info_data["local_adapter"] = {
                            "hci_version": hci_info.get("hci_version"),
                            "hci_revision": hci_info.get("hci_revision"),
                            "lmp_version": hci_info.get("lmp_version"),
                            "lmp_subversion": hci_info.get("lmp_subversion"),
                            "manufacturer": hci_info.get("manufacturer"),
                            "lmp_spec": map_lmp_version_to_spec(hci_info.get("lmp_version")),
                        }
                except Exception as ver_exc:
                    if debug_mode:
                        print_and_log(f"[classic-enum] Version info collection failed: {ver_exc}", LOG__GENERAL)
                    version_info_data["error"] = str(ver_exc)
            
            # Display Device Information block (parity with BLE gatt-enum/enum-scan)
            try:
                import dbus as _dbus_cenum
                _bus_cenum = _dbus_cenum.SystemBus()
                from bleep.bt_ref.utils import device_address_to_path
                from bleep.bt_ref.constants import BLUEZ_NAMESPACE, ADAPTER_NAME
                _dev_path = device_address_to_path(args.address.upper(), f"{BLUEZ_NAMESPACE}{ADAPTER_NAME}")
                _obj_cenum = _bus_cenum.get_object("org.bluez", _dev_path)
                _pi_cenum = _dbus_cenum.Interface(_obj_cenum, "org.freedesktop.DBus.Properties")
                _cenum_props = dict(_pi_cenum.GetAll("org.bluez.Device1"))
                # Merge Battery1 / Input1 if available
                for _aux_iface, _aux_key in [("org.bluez.Battery1", "_Battery1"), ("org.bluez.Input1", "_Input1")]:
                    try:
                        _aux = dict(_pi_cenum.GetAll(_aux_iface))
                        if _aux:
                            _cenum_props[_aux_key] = _aux
                    except Exception:
                        pass
                from bleep.ble_ops.common.conversion import format_device_info_block
                _cenum_name = str(_cenum_props.get("Name", "")) or str(_cenum_props.get("Alias", ""))
                print(format_device_info_block(_cenum_props, device_name=_cenum_name or None, mac=args.address.upper()))
                print()

                # Persist full device metadata to observation DB
                try:
                    from bleep.ble_ops.le.scan import _enrich_device_info_from_props
                    from bleep.core import observations as _obs_cenum
                    _cenum_dev_info: Dict[str, Any] = {"name": _cenum_name or None}
                    _enrich_device_info_from_props(_cenum_dev_info, _cenum_props)
                    _obs_cenum.upsert_device(args.address.upper(), **_cenum_dev_info)
                except Exception as _db_cenum_exc:
                    if debug_mode:
                        print_and_log(f"[classic-enum] DB device upsert warning: {_db_cenum_exc}", LOG__DEBUG)
            except Exception as _props_exc:
                if debug_mode:
                    print_and_log(f"[classic-enum] Device info block unavailable: {_props_exc}", LOG__DEBUG)

            # Get SDP records with enhanced attributes (connectionless - works without full connection)
            records = []
            connectionless_mode = getattr(args, "connectionless", False)
            try:
                records = discover_services_sdp(args.address, connectionless=connectionless_mode)
                
                if records:
                    print_and_log(f"[+] Found {len(records)} SDP record(s) for {args.address}", LOG__GENERAL)
                    print("\nSDP Records:")
                    print("=" * 80)
                    for idx, rec in enumerate(records, 1):
                        print(f"\nRecord {idx}:")
                        if rec.get("name"):
                            print(f"  Name: {rec['name']}")
                        if rec.get("uuid"):
                            print(f"  UUID: {rec['uuid']}")
                        if rec.get("channel") is not None:
                            print(f"  RFCOMM Channel: {rec['channel']}")
                        if rec.get("handle") is not None:
                            print(f"  Service Record Handle: 0x{rec['handle']:04X}")
                        if rec.get("service_version") is not None:
                            print(f"  Service Version: 0x{rec['service_version']:04X}")
                        if rec.get("description"):
                            print(f"  Description: {rec['description']}")
                        if rec.get("profile_descriptors"):
                            print("  Profile Descriptors:")
                            for p in rec["profile_descriptors"]:
                                uuid = p.get("uuid", "Unknown")
                                ver = p.get("version")
                                if ver is not None:
                                    spec_hint = map_profile_version_to_spec(ver) if version_info_mode else None
                                    ver_str = f"0x{ver:04X}"
                                    if spec_hint:
                                        ver_str += f" (~{spec_hint})"
                                    print(f"    {uuid}: Version {ver_str}")
                                else:
                                    print(f"    {uuid}: Version unknown")
                    print("\n" + "=" * 80)

                    # Show service map summary (bc-53 collision-safe)
                    from bleep.ble_ops.classic.sdp import build_svc_map
                    svc_map_sdp = build_svc_map(records)
                    rfcomm_n = sum(1 for v in svc_map_sdp.values() if v.get("channel") is not None)
                    if svc_map_sdp:
                        print(f"\nService Map ({len(svc_map_sdp)} service(s), {rfcomm_n} with RFCOMM):")
                        for svc, entry in svc_map_sdp.items():
                            ch = entry.get("channel")
                            ch_str = f"-> ch {ch}" if ch is not None else "(no RFCOMM)"
                            print(f"  {svc:25} {ch_str}")
                        print()
                
                # Display version information if requested (before connection attempt)
                if version_info_mode:
                    print("\n=== Version Information ===")
                    if version_info_data.get("error"):
                        print(f"Error collecting version info: {version_info_data['error']}")
                    else:
                        if version_info_data.get("vendor") is not None:
                            print(f"Vendor ID: 0x{version_info_data['vendor']:04X}")
                        if version_info_data.get("product") is not None:
                            print(f"Product ID: 0x{version_info_data['product']:04X}")
                        if version_info_data.get("version") is not None:
                            print(f"Version: 0x{version_info_data['version']:04X}")
                        if version_info_data.get("modalias"):
                            print(f"Modalias: {version_info_data['modalias']}")
                        
                        # Show profile versions from SDP records
                        if records:
                            print("\nProfile Versions (from SDP):")
                            profile_specs: Dict[str, list] = {}
                            for rec in records:
                                if rec.get('profile_descriptors'):
                                    for p in rec.get('profile_descriptors', []):
                                        uuid = p.get('uuid', 'Unknown')
                                        ver = p.get('version')
                                        if ver is not None:
                                            spec_hint = map_profile_version_to_spec(ver)
                                            if uuid not in profile_specs:
                                                profile_specs[uuid] = []
                                            profile_specs[uuid].append({
                                                "version": ver,
                                                "spec_hint": spec_hint,
                                            })
                            
                            for uuid, vers in profile_specs.items():
                                for v_info in vers:
                                    ver_str = f"0x{v_info['version']:04X}"
                                    if v_info['spec_hint']:
                                        ver_str += f" (~Bluetooth {v_info['spec_hint']})"
                                    print(f"  {uuid}: {ver_str}")
                        
                        # Show local adapter info (for reference)
                        if version_info_data.get("local_adapter"):
                            local = version_info_data["local_adapter"]
                            print("\nLocal Adapter (for reference):")
                            if local.get("lmp_version") is not None:
                                lmp_spec = local.get("lmp_spec", "Unknown")
                                print(f"  LMP Version: {local['lmp_version']} ({lmp_spec})")
                            if local.get("hci_version") is not None:
                                print(f"  HCI Version: {local['hci_version']}")
                            if local.get("manufacturer") is not None:
                                print(f"  Manufacturer ID: {local['manufacturer']}")
                        
                        # Show raw properties if available (for offline analysis)
                        if version_info_data.get("raw_properties"):
                            print("\nRaw Properties (for analysis):")
                            for key, value in version_info_data["raw_properties"].items():
                                print(f"  {key}: {value}")
                    
                    print("=" * 28 + "\n")
                
                # Perform comprehensive SDP analysis if requested
                if analyze_mode and records:
                    try:
                        analyzer = SDPAnalyzer(records)
                        analysis = analyzer.analyze()
                        report = analyzer.generate_report()
                        print(report)
                        
                        # Also show detailed analysis in JSON if debug mode
                        if debug_mode:
                            print("\n=== Detailed Analysis (JSON) ===")
                            print(json.dumps(analysis, indent=2, default=str))
                            print("=" * 35 + "\n")
                    except Exception as analysis_exc:
                        if debug_mode:
                            print_and_log(f"[classic-enum] SDP analysis failed: {analysis_exc}", LOG__GENERAL)
                            import traceback
                            traceback.print_exc()
            
            except Exception as sdp_exc:
                if debug_mode:
                    print_and_log(f"[classic-enum] SDP discovery failed: {sdp_exc}", LOG__GENERAL)
                # Continue to try connection-based enumeration
            
            # Try to connect and enumerate (requires full connection)
            try:
                _, svc_map = _c_enum(args.address)
                if debug_mode:
                    print_and_log(f"[+] Connection-based enumeration: {len(svc_map)} services", LOG__GENERAL)
                return 0
            except Exception as conn_exc:
                if records:
                    print_and_log(
                        f"[!] Connection failed ({conn_exc}), but SDP enumeration succeeded",
                        LOG__GENERAL,
                    )
                    return 0

                import sys as _sys_module
                print(f"Error: {conn_exc}", file=_sys_module.stderr)
                if debug_mode:
                    import traceback
                    traceback.print_exc(file=_sys_module.stderr)
                return 1

        elif args.mode == "classic-pbap":
            repos_arg = (args.repos or "PB").upper()
            from bleep.ble_ops.classic.pbap import pbap_dump_async, DEFAULT_PBAP_REPOS
            repos = DEFAULT_PBAP_REPOS if repos_arg == "ALL" else tuple(r.strip().upper() for r in repos_arg.split(",") if r.strip())

            try:
                result = pbap_dump_async(
                    args.address,
                    repos=repos,
                    vcard_format=args.format,
                    auto_auth=args.auto_auth,
                    watchdog=args.watchdog,
                )
            except Exception as exc:
                import sys as _sys_module
                print(f"Error: {exc}", file=_sys_module.stderr)
                return 1

            base = args.address.replace(":", "").upper()
            single_custom_out = args.out and len(repos) == 1

            for repo, lines in result["data"].items():
                if single_custom_out:
                    path = args.out
                else:
                    path = f"/tmp/{base}_{repo}.vcf"
                try:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.writelines(lines)
                    print(f"[+] Saved {repo} → {path} ({len(lines)} lines)")
                except Exception as exc:
                    print(f"[!] Failed to write {path}: {exc}", file=sys.stderr)
            return 0

        elif args.mode == "classic-opp":
            if not args.action:
                _subparsers["classic-opp"].print_help()
                return 0

            mac = args.address

            if args.action == "send":
                from bleep.ble_ops.classic.opp import send_file
                try:
                    result = send_file(mac, args.file, timeout=args.timeout)
                    transferred = result.get("transferred", "?")
                    size = result.get("size", "?")
                    print(f"[+] OPP send complete: {transferred}/{size} bytes transferred")
                except FileNotFoundError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "pull":
                from bleep.ble_ops.classic.opp import pull_business_card
                from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
                from pathlib import Path
                if args.out:
                    dest = args.out
                    use_staging = False
                else:
                    filename = f"{mac.replace(':', '').upper()}_card.vcf"
                    dest = str(OBEX_STAGING_DIR / filename)
                    use_staging = True
                try:
                    result_path = pull_business_card(mac, dest, timeout=args.timeout)
                    size = result_path.stat().st_size if result_path.exists() else 0
                    if use_staging:
                        final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                        final_dir.mkdir(parents=True, exist_ok=True)
                        final = str(final_dir / os.path.basename(str(result_path)))
                        if result_path.exists():
                            shutil.move(str(result_path), final)
                        print(f"[+] Business card saved → {final} ({size} bytes)")
                    else:
                        print(f"[+] Business card saved → {result_path} ({size} bytes)")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "exchange":
                from bleep.ble_ops.classic.opp import exchange_business_cards
                from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
                from pathlib import Path
                if args.out:
                    dest = args.out
                    use_staging = False
                else:
                    filename = f"{mac.replace(':', '').upper()}_card.vcf"
                    dest = str(OBEX_STAGING_DIR / filename)
                    use_staging = True
                try:
                    result_path = exchange_business_cards(
                        mac, args.file, dest, timeout=args.timeout,
                    )
                    if use_staging:
                        final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                        final_dir.mkdir(parents=True, exist_ok=True)
                        final = str(final_dir / os.path.basename(str(result_path)))
                        if os.path.exists(str(result_path)):
                            shutil.move(str(result_path), final)
                        print(f"[+] Exchange complete — remote card saved → {final}")
                    else:
                        print(f"[+] Exchange complete — remote card saved → {result_path}")
                except FileNotFoundError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            return 0

        elif args.mode == "classic-map":
            if not args.action:
                _subparsers["classic-map"].print_help()
                return 0

            mac = args.address
            inst = args.instance

            if args.action == "folders":
                from bleep.ble_ops.classic.map import list_folder_tree, collect_leaf_paths
                try:
                    tree = list_folder_tree(mac, instance=inst)
                    if not tree:
                        print("[*] No folders found")
                    else:
                        def _render_tree(nodes, depth=0):
                            for node in nodes:
                                print(f"{'  ' * depth}{node['name']}/")
                                if node.get("children"):
                                    _render_tree(node["children"], depth + 1)
                        _render_tree(tree)
                        leaves = collect_leaf_paths(tree)
                        if leaves:
                            print(f"\nMessage folders: {', '.join(sorted(leaves))}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "list":
                from bleep.ble_ops.classic.map import list_messages
                try:
                    filters = {}
                    if args.msg_type:
                        filters["Type"] = args.msg_type
                    msgs = list_messages(
                        mac, args.folder,
                        filters=filters if filters else None,
                        instance=inst,
                    )
                    if not msgs:
                        print(f"[*] No messages in {args.folder}")
                    else:
                        verbose = getattr(args, "map_verbose", False)
                        for m in msgs:
                            handle = (
                                m.get("path", "").rsplit("message", 1)[-1]
                                if "path" in m else "?"
                            )
                            subject = m.get("Subject", "(no subject)")
                            status = m.get("Status", "")
                            if verbose:
                                sender = m.get("Sender", m.get("SenderAddress", ""))
                                dt = m.get("Timestamp", m.get("DateTime", ""))
                                mtype = m.get("Type", "")
                                extra = "  ".join(
                                    f for f in [mtype, sender, dt] if f
                                )
                                print(f"  {handle}  {subject}  [{status}]  {extra}")
                            else:
                                print(f"  {handle}  {subject}  [{status}]")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    if "bad request" in str(exc).lower():
                        try:
                            from bleep.ble_ops.classic.map import (
                                list_folder_tree, collect_leaf_paths,
                            )
                            tree = list_folder_tree(mac, instance=inst)
                            leaves = collect_leaf_paths(tree)
                            if leaves:
                                print(
                                    f"\n[*] '{args.folder}' is not a message folder."
                                    " Available message folders:",
                                    file=sys.stderr,
                                )
                                for lf in sorted(leaves):
                                    print(
                                        f"    classic-map {mac} list {lf}",
                                        file=sys.stderr,
                                    )
                        except Exception:
                            pass
                    return 1

            elif args.action == "get":
                from bleep.ble_ops.classic.map import get_message
                from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
                from pathlib import Path
                filename = f"map_msg_{args.handle}.txt"
                if args.out:
                    dest = args.out
                    use_staging = False
                else:
                    dest = str(OBEX_STAGING_DIR / filename)
                    use_staging = True
                try:
                    result = get_message(mac, args.handle, dest, instance=inst)
                    if use_staging:
                        final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                        final_dir.mkdir(parents=True, exist_ok=True)
                        final = str(final_dir / os.path.basename(str(result)))
                        if os.path.exists(str(result)):
                            shutil.move(str(result), final)
                        print(f"[+] Message saved → {final}")
                    else:
                        print(f"[+] Message saved → {result}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "push":
                from bleep.ble_ops.classic.map import push_message
                try:
                    push_message(mac, args.file, args.folder, instance=inst)
                    print(f"[+] Message pushed to {args.folder}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "inbox":
                from bleep.ble_ops.classic.map import update_inbox
                try:
                    update_inbox(mac, instance=inst)
                    print("[+] Inbox update requested")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "types":
                from bleep.ble_ops.classic.map import get_supported_types
                try:
                    types = get_supported_types(mac, instance=inst)
                    if not types:
                        print("[*] No supported types reported")
                    else:
                        print("Supported message types:")
                        for t in types:
                            print(f"  {t}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "fields":
                from bleep.ble_ops.classic.map import list_filter_fields
                try:
                    fields = list_filter_fields(mac, instance=inst)
                    if not fields:
                        print("[*] No filter fields reported")
                    else:
                        print("Available filter fields:")
                        for f in fields:
                            print(f"  {f}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "monitor":
                import signal as _signal
                from bleep.ble_ops.classic.map import start_message_monitor, stop_message_monitor

                def _mns_print(path: str, props: dict) -> None:
                    print(f"[MNS] {path}")
                    for k, v in props.items():
                        print(f"      {k}: {v}")

                try:
                    start_message_monitor(mac, _mns_print, timeout=args.timeout, instance=inst)
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

                print("[+] MNS monitor active – press Ctrl+C to stop")
                try:
                    _signal.pause()
                except KeyboardInterrupt:
                    pass
                finally:
                    stop_message_monitor(mac)
                    print("\n[+] MNS monitor stopped")

            elif args.action == "instances":
                from bleep.ble_ops.classic.map import list_mas_instances
                try:
                    instances_list = list_mas_instances(mac)
                    if not instances_list:
                        print("[*] No MAS instances found via SDP")
                    else:
                        print(f"MAS Instances on {mac}:")
                        for mi in instances_list:
                            print(f"  Channel {mi['channel']:>3}  {mi.get('name', '')}  (UUID {mi.get('uuid', '?')})")
                        print("\nUse --instance <channel> to target a specific MAS.")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            return 0

        elif args.mode == "classic-ftp":
            if not args.action:
                _subparsers["classic-ftp"].print_help()
                return 0

            mac = args.address

            if args.action == "ls":
                from bleep.ble_ops.classic.ftp import list_folder
                try:
                    entries = list_folder(mac, args.path)
                    if not entries:
                        print("[*] Folder is empty")
                    else:
                        print(f"\n{'Type':<8} {'Size':>10}  Name")
                        print("-" * 40)
                        for e in entries:
                            etype = e.get("Type", "?")
                            esize = e.get("Size", "")
                            ename = e.get("Name", "(unnamed)")
                            if etype == "folder":
                                print(f"{'dir':<8} {'':>10}  {ename}/")
                            else:
                                print(f"{'file':<8} {esize:>10}  {ename}")
                        print()
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "get":
                from bleep.ble_ops.classic.ftp import get_file
                from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
                from pathlib import Path
                if args.out:
                    dest = args.out
                    use_staging = False
                else:
                    dest = str(OBEX_STAGING_DIR / args.remote)
                    use_staging = True
                try:
                    result = get_file(
                        mac, args.remote, dest,
                        remote_path=args.remote_path, timeout=args.timeout,
                    )
                    if use_staging:
                        final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                        final_dir.mkdir(parents=True, exist_ok=True)
                        final = str(final_dir / os.path.basename(str(result)))
                        if os.path.exists(str(result)):
                            shutil.move(str(result), final)
                        print(f"[+] Downloaded → {final}")
                    else:
                        print(f"[+] Downloaded → {result}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "put":
                from bleep.ble_ops.classic.ftp import put_file
                try:
                    result = put_file(
                        mac, args.file, args.name,
                        remote_path=args.remote_path, timeout=args.timeout,
                    )
                    transferred = result.get("transferred", "?")
                    size = result.get("size", "?")
                    print(f"[+] Uploaded: {transferred}/{size} bytes")
                except FileNotFoundError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "mkdir":
                from bleep.ble_ops.classic.ftp import create_folder
                try:
                    create_folder(mac, args.name, remote_path=args.remote_path)
                    print(f"[+] Created folder: {args.name}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "rm":
                from bleep.ble_ops.classic.ftp import delete_item
                try:
                    delete_item(mac, args.name, remote_path=args.remote_path)
                    print(f"[+] Deleted: {args.name}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            return 0

        elif args.mode == "classic-pan":
            if not args.action:
                _subparsers["classic-pan"].print_help()
                return 0

            if args.action == "connect":
                from bleep.ble_ops.classic.pan import connect as pan_connect
                try:
                    iface = pan_connect(args.address, args.role)
                    print(f"[+] PAN connected – interface {iface}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "disconnect":
                from bleep.ble_ops.classic.pan import disconnect as pan_disconnect
                try:
                    pan_disconnect(args.address)
                    print("[+] PAN disconnected")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "status":
                from bleep.ble_ops.classic.pan import status as pan_status
                try:
                    info = pan_status(args.address)
                    print(f"  Connected : {info.get('connected', False)}")
                    print(f"  Interface : {info.get('interface', '(none)')}")
                    print(f"  UUID/Role : {info.get('uuid', '(none)')}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "serve":
                import signal as _signal
                from bleep.dbuslayer.network import NetworkServer
                try:
                    server = NetworkServer()
                    server.register(args.role, args.bridge)
                    print(f"[+] PAN server registered (role={args.role}, bridge={args.bridge})")
                    print("[*] Keeping process alive — press Ctrl+C to unregister and exit")
                    try:
                        _signal.pause()
                    except KeyboardInterrupt:
                        pass
                    finally:
                        try:
                            server.unregister(args.role)
                            print(f"\n[+] PAN server unregistered (role={args.role})")
                        except Exception:
                            pass
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "unserve":
                from bleep.ble_ops.classic.pan import unregister_server
                try:
                    unregister_server(args.role)
                    print(f"[+] PAN server unregistered (role={args.role})")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            return 0

        elif args.mode == "classic-spp":
            if not args.action:
                _subparsers["classic-spp"].print_help()
                return 0

            if args.action == "register":
                import signal as _signal
                from bleep.ble_ops.classic.spp import register as spp_register, unregister as spp_unregister

                def _on_connect(device_path: str, sock, fd_props: dict) -> None:
                    print(f"[SPP] Connection from {device_path}")
                    print(f"[SPP] Socket fd={sock.fileno()} – reading data...")
                    try:
                        while True:
                            data = sock.recv(1024)
                            if not data:
                                break
                            sys.stdout.buffer.write(data)
                            sys.stdout.buffer.flush()
                    except (OSError, KeyboardInterrupt):
                        pass
                    finally:
                        sock.close()
                        print("\n[SPP] Connection closed")

                req_auth = not getattr(args, "no_auth", False)
                try:
                    spp_register(
                        channel=args.channel, name=args.name, role=args.role,
                        require_auth=req_auth,
                        on_connect=_on_connect,
                    )
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

                print("[+] SPP profile registered – press Ctrl+C to stop")
                try:
                    _signal.pause()
                except KeyboardInterrupt:
                    pass
                finally:
                    spp_unregister()
                    print("\n[+] SPP profile unregistered")

            elif args.action == "unregister":
                from bleep.ble_ops.classic.spp import unregister as spp_unregister
                try:
                    spp_unregister()
                    print("[+] SPP profile unregistered")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "status":
                from bleep.ble_ops.classic.spp import status as spp_status
                info = spp_status()
                if not info.get("registered"):
                    print("[*] SPP profile not registered")
                else:
                    print(f"  Registered : True")
                    print(f"  UUID       : {info.get('uuid', '?')}")
                    print(f"  Name       : {info.get('name', '?')}")
                    print(f"  Role       : {info.get('role', '?')}")
                    print(f"  Channel    : {info.get('channel') or 'auto'}")

            return 0

        elif args.mode == "connect-profile":
            mac = args.address
            uuid = args.uuid
            adapter_name = getattr(args, "adapter", None)
            try:
                from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic as ClassicDevice
                from bleep.bt_ref.utils import get_name_from_uuid
                device = ClassicDevice(mac, bluetooth_adapter=adapter_name)
                name = get_name_from_uuid(uuid) or uuid
                if args.disconnect:
                    device.disconnect_profile(uuid)
                    print(f"[+] Disconnected profile: {name}")
                else:
                    device.connect_profile(uuid)
                    print(f"[+] Connected profile: {name}")
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        elif args.mode == "hid-info":
            mac = args.address
            adapter_name = getattr(args, "adapter", None)
            try:
                from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic as ClassicDevice
                from bleep.analysis.device_type_classifier import classify_hid
                device = ClassicDevice(mac, bluetooth_adapter=adapter_name)
                context: dict = {}
                try:
                    context["device_class"] = device.get_device_class()
                except Exception:
                    pass
                try:
                    context["uuids"] = device.get_supported_profiles()
                except Exception:
                    context["uuids"] = []
                hid = classify_hid(context)
                if hid is None:
                    print(f"[*] {mac} does not appear to be a HID device")
                else:
                    print(f"[+] HID Classification for {mac}:")
                    print(f"    Type:            {hid.hid_type}")
                    print(f"    Subclass:        {hid.subclass_label}")
                    if hid.reconnect_mode:
                        print(f"    Reconnect Mode:  {hid.reconnect_mode}")
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        elif args.mode == "audio-intercept":
            from bleep.ble_ops.audio.audio_transcribe import run_audio_intercept
            result = run_audio_intercept(
                args.address,
                duration=args.duration,
                output_dir=args.output_dir,
                pcm_device=args.pcm,
                transcribe=not args.no_transcribe,
                engine=args.engine,
            )
            if result.error:
                print(f"Error: {result.error}", file=sys.stderr)
                return 1
            print(f"[+] Captured: {result.wav_path}")
            print(f"    Duration:    {result.duration_seconds}s")
            print(f"    Has content: {result.has_content}")
            if result.transcript:
                print(f"    Engine:      {result.engine}")
                print(f"    Transcript:  {result.transcript[:200]}")
            elif result.has_content:
                print("    (no transcription engine available)")
            return 0

        elif args.mode == "classic-sync":
            if not args.action:
                _subparsers["classic-sync"].print_help()
                return 0

            if args.action == "get":
                from bleep.ble_ops.classic.sync import get_phonebook
                from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
                from pathlib import Path
                if args.output:
                    dest = args.output
                    use_staging = False
                else:
                    dest = str(OBEX_STAGING_DIR / f"sync_{args.address.replace(':', '').upper()}.vcf")
                    use_staging = True
                try:
                    result = get_phonebook(
                        args.address, dest,
                        location=args.location, timeout=args.timeout,
                    )
                    if use_staging:
                        final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                        final_dir.mkdir(parents=True, exist_ok=True)
                        final = str(final_dir / os.path.basename(str(result)))
                        if os.path.exists(str(result)):
                            shutil.move(str(result), final)
                        print(f"[+] Phonebook saved → {final}")
                    else:
                        print(f"[+] Phonebook saved → {result}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "put":
                from bleep.ble_ops.classic.sync import put_phonebook
                try:
                    put_phonebook(
                        args.address, args.file,
                        location=args.location, timeout=args.timeout,
                    )
                    print("[+] Phonebook uploaded OK")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            return 0

        elif args.mode == "classic-bip":
            if not args.action:
                _subparsers["classic-bip"].print_help()
                return 0

            if args.action == "list":
                print(
                    "BlueZ's experimental Image1 interface does not provide an\n"
                    "image-listing method.  To discover handles you can:\n"
                    "  1. Use AVRCP media browsing (if the device is an A2DP source)\n"
                    "     to enumerate cover-art handles exposed via bip-avrcp.\n"
                    "  2. Start from handle '0' or '1000001' and iterate with\n"
                    "     'classic-bip props <handle>' until the device returns an\n"
                    "     error, incrementing by 1 each time.\n"
                    "  3. Use 'classic-map list' or 'classic-ftp ls' to locate\n"
                    "     image attachments whose handles can be passed to BIP."
                )
                return 0

            elif args.action == "props":
                from bleep.ble_ops.classic.bip import get_properties
                try:
                    props = get_properties(
                        args.address, args.handle, timeout=args.timeout,
                    )
                    for i, entry in enumerate(props):
                        print(f"  [{i}] {entry}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "get":
                from bleep.ble_ops.classic.bip import get_image
                from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
                from pathlib import Path
                if args.output:
                    dest = args.output
                    use_staging = False
                else:
                    dest = str(OBEX_STAGING_DIR / f"bip_{args.handle}")
                    use_staging = True
                try:
                    result = get_image(
                        args.address, dest, args.handle,
                        timeout=args.timeout,
                    )
                    if use_staging:
                        final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                        final_dir.mkdir(parents=True, exist_ok=True)
                        final = str(final_dir / os.path.basename(str(result)))
                        if os.path.exists(str(result)):
                            shutil.move(str(result), final)
                        print(f"[+] Image saved → {final}")
                    else:
                        print(f"[+] Image saved → {result}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            elif args.action == "thumb":
                from bleep.ble_ops.classic.bip import get_thumbnail
                from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
                from pathlib import Path
                if args.output:
                    dest = args.output
                    use_staging = False
                else:
                    dest = str(OBEX_STAGING_DIR / f"bip_thumb_{args.handle}")
                    use_staging = True
                try:
                    result = get_thumbnail(
                        args.address, dest, args.handle,
                        timeout=args.timeout,
                    )
                    if use_staging:
                        final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                        final_dir.mkdir(parents=True, exist_ok=True)
                        final = str(final_dir / os.path.basename(str(result)))
                        if os.path.exists(str(result)):
                            shutil.move(str(result), final)
                        print(f"[+] Thumbnail saved → {final}")
                    else:
                        print(f"[+] Thumbnail saved → {result}")
                except Exception as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1

            return 0

        elif args.mode == "classic-ping":
            from bleep.ble_ops.classic.ping import classic_l2ping

            rtt, err = classic_l2ping(args.address, count=args.count, timeout=args.timeout)
            if rtt is None:
                print(f"[!] l2ping failed – {err}", file=sys.stderr)
                return 1
            print(f"Average RTT {rtt:.1f} ms")
            return 0

        elif args.mode == "classic-rfcomm":
            from bleep.ble_ops.classic.sdp import discover_services_sdp, build_svc_map
            from bleep.ble_ops.classic.rfcomm import probe_rfcomm_channel

            mac = args.address.strip().upper()
            print(f"[*] Discovering SDP services for {mac}...")
            try:
                records = discover_services_sdp(mac)
            except Exception as exc:
                print(f"[!] SDP discovery failed: {exc}", file=sys.stderr)
                return 1
            svc_map = build_svc_map(records)

            rfcomm_entries = []
            for name, entry in svc_map.items():
                ch = entry.get("channel") if isinstance(entry, dict) else entry
                if ch is not None:
                    svc_name = entry.get("name", name) if isinstance(entry, dict) else name
                    uuid = entry.get("uuid", "") if isinstance(entry, dict) else ""
                    rfcomm_entries.append((ch, svc_name, uuid))

            if not rfcomm_entries:
                print(f"[!] No RFCOMM channels found for {mac}")
                return 1

            rfcomm_entries.sort(key=lambda e: e[0])
            print(f"\n[+] RFCOMM Channels ({len(rfcomm_entries)} found):\n")
            print(f"  {'Ch':>3}  {'Service':<30}  {'UUID'}")
            print(f"  {'---':>3}  {'-'*30}  {'-'*36}")
            for ch, svc_name, uuid in rfcomm_entries:
                print(f"  {ch:>3}  {svc_name:<30}  {uuid}")

            if args.probe:
                print(f"\n[*] Probing {len(rfcomm_entries)} RFCOMM channel(s)...\n")
                for ch, svc_name, _ in rfcomm_entries:
                    result = probe_rfcomm_channel(mac, ch, timeout=args.timeout)
                    status = result.classification.upper()
                    extra = ""
                    if result.raw_response:
                        preview = result.raw_response[:60]
                        try:
                            extra = f" → {preview.decode('utf-8', errors='replace').strip()!r}"
                        except Exception:
                            extra = f" → {preview.hex()}"
                    elif result.error:
                        extra = f" → {result.error}"
                    print(f"  ch {ch:>2} ({svc_name}): [{status}]{extra}  ({result.latency_ms:.0f}ms)")

            if args.bind is not None:
                from bleep.ble_ops.classic.rfcomm import bind_rfcomm_channel
                try:
                    dev_path = bind_rfcomm_channel(
                        mac, args.bind, device_id=args.device_id,
                    )
                    print(f"\n[+] Bound {mac} ch {args.bind} → {dev_path}")
                except Exception as exc:
                    print(f"\n[-] Bind failed: {exc}", file=sys.stderr)
                    return 1

            return 0
            
        elif args.mode == "ctf":
            from bleep.ble_ops.le.ctf import ble_ctf__scan_and_enumeration
            from bleep.ble_ops.le.ctf_discovery import discover_flags, auto_solve_flags, generate_flag_visualization
            from bleep.modes.blectf import main as _blectf_main
            
            device_mac = args.device
            
            if args.interactive:
                # Run the interactive CTF shell
                return _blectf_main() or 0
            
            try:
                # Connect to the device
                print(f"[*] Connecting to BLE CTF device ({device_mac})...")
                device, _ = ble_ctf__scan_and_enumeration()
                print(f"[+] Connected to {device_mac}")
                
                # Process command line options
                if args.discover:
                    print("[*] Discovering and analyzing flags...")
                    discover_flags(device)
                
                if args.solve:
                    print("[*] Automatically solving flags...")
                    auto_solve_flags(device)
                
                if args.visualize:
                    print("[*] Generating flag visualization...")
                    visualization = generate_flag_visualization(device)
                    print(visualization)
                
                # If no specific action was requested, run in interactive mode
                if not (args.discover or args.solve or args.visualize):
                    return _blectf_main() or 0
                
                return 0
            except Exception as e:
                print(f"[!] BLE CTF error: {e}", file=sys.stderr)
                return 1

        elif args.mode == "adapter-config":
            from bleep.modes.adapter_config import handle_adapter_config
            return handle_adapter_config(args)

        elif args.mode == "monitor":
            from bleep.modes.monitor import handle_monitor
            return handle_monitor(args)

        elif args.mode == "advertise":
            from bleep.modes.advertise import handle_advertise
            return handle_advertise(args)

        elif args.mode == "audio-config":
            from bleep.ble_ops.audio.alsa_config import (
                read_asound_conf, configure_bluealsa_device, remove_bluealsa_device,
                create_audio_tunnel, backup_and_restore,
            )
            action = args.action
            if not action:
                print("Usage: bleep audio-config {show|add|remove|tunnel|backup|restore}")
                return 1
            if action == "show":
                entries = read_asound_conf(args.path)
                if not entries:
                    print("[*] No ALSA config entries found")
                else:
                    for name, entry in entries.items():
                        mac_str = f"  MAC: {entry.mac}" if entry.mac else ""
                        print(f"  {name}{mac_str}")
                        for line in entry.body.splitlines():
                            print(f"    {line.strip()}")
            elif action == "add":
                configure_bluealsa_device(args.address, args.device_type, config_path=args.path)
                print(f"[+] Added BlueALSA {args.device_type} for {args.address}")
            elif action == "remove":
                if remove_bluealsa_device(args.address, config_path=args.path):
                    print(f"[+] Removed entries for {args.address}")
                else:
                    print(f"[-] No entries found for {args.address}")
            elif action == "tunnel":
                tc = create_audio_tunnel(args.source, args.sink, config_path=args.path)
                print(f"[+] Tunnel: {tc.source_pcm} → {tc.loopback_device} → {tc.sink_pcm}")
            elif action == "backup":
                bak = backup_and_restore("backup", args.path)
                if bak:
                    print(f"[+] Backup: {bak}")
            elif action == "restore":
                backup_and_restore("restore", args.path)
                print("[+] Restored")
            return 0

        elif args.mode == "debug":
            from bleep.modes.debug import main as _debug_main

            return _debug_main(_rebuild_debug_argv(args)) or 0

        else:  # interactive (default)
            from bleep.modes.interactive import main as _interactive_main

            return _interactive_main() or 0

    except KeyboardInterrupt:
        #import sys  # Ensure sys is available in this scope
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        #import sys  # Ensure sys is available in this scope
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
