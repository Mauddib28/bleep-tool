#!/usr/bin/env python3
"""Debug Mode for BLEEP.

This mode provides an interactive debug shell for inspecting Bluetooth devices,
accessing low-level D-Bus interfaces, monitoring properties in real-time, and
manually invoking methods.

The shell is organised into focused submodules:

- ``debug_state``     – DebugState dataclass, GLib mainloop management
- ``debug_dbus``      – D-Bus helpers, navigation (ls/cd/pwd), introspection
- ``debug_connect``   – connect / disconnect / info
- ``debug_gatt``      – GATT operations, notification callback
- ``debug_classic``   – Classic BT discovery (cscan, csdp, pbap, …)
- ``debug_classic_data`` – Classic data exchange (copen, csend, crecv, craw, copp, cmap, cftp, csync, cbip)
- ``debug_pairing``   – Pairing / agent commands
- ``debug_scan``      – Scan / enumeration commands
- ``debug_aoi``       – AOI analysis and database commands
- ``debug_multiread`` – Multi-read and brute-write commands
- ``debug_media``     – Media/audio commands (mediaenum, mediactrl, audioplay, …)

Usage (equivalent — both supported):
  bleep debug [options] [device]
  python -m bleep.modes.debug [options] [device]

Options:
  device                  MAC address of device to connect to (positional)
  -n, --no-connect        Start debug shell without connecting to a device
  -m, --monitor           Enable real-time property monitoring
  -d, --detailed          Show detailed information including decoded UUIDs
"""

import argparse
import shlex

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum

try:
    import readline  # noqa: F401 – enables arrow-key editing in input()
except ImportError:
    pass

# Import observations for database integration
try:
    from bleep.core import observations as _obs_module
    _DB_AVAILABLE = True
except ImportError:
    _obs_module = None
    _DB_AVAILABLE = False

# ---------------------------------------------------------------------------
# Shared state & submodule imports
# ---------------------------------------------------------------------------

from bleep.modes.debug_state import (
    DebugState, PROMPT, DEVICE_PROMPT,
    ensure_glib_mainloop, stop_glib_mainloop,
)
from bleep.modes.debug_dbus import (
    cmd_ls, cmd_cd, cmd_pwd, cmd_back,
    cmd_interfaces, cmd_props, cmd_methods, cmd_signals,
    cmd_call, cmd_monitor, cmd_introspect,
    print_detailed_dbus_error,
)
from bleep.modes.debug_connect import cmd_connect, cmd_disconnect, cmd_info
from bleep.modes.debug_gatt import (
    cmd_services, cmd_chars, cmd_char,
    cmd_read, cmd_write, cmd_notify, cmd_detailed,
)
from bleep.modes.debug_classic import (
    cmd_cscan, cmd_cconnect, cmd_cservices, cmd_ckeep,
    cmd_csdp, cmd_pbap,
)
from bleep.modes.debug_classic_data import (
    cmd_copen, cmd_csend, cmd_crecv, cmd_craw, cmd_crfcomm,
    cmd_copp, cmd_cmapinfo, cmd_cmap, cmd_cftp, cmd_cpan, cmd_cspp, cmd_csync, cmd_cbip,
)
from bleep.modes.debug_classic_profiles import cmd_cprofiles, cmd_cprofile
from bleep.modes.debug_hid import cmd_chid
from bleep.modes.debug_classic_rfcomm import cmd_cbind
from bleep.modes.debug_pairing import cmd_agent, cmd_pair
from bleep.modes.debug_scan import (
    cmd_scan, cmd_scann, cmd_scanp, cmd_scanb, cmd_dscan,
    cmd_enum, cmd_enumn, cmd_enump, cmd_enumb, cmd_mines,
)
from bleep.modes.debug_aoi import cmd_aoi, cmd_dbsave, cmd_dbexport
from bleep.modes.debug_multiread import cmd_multiread, cmd_multiread_all, cmd_brutewrite
from bleep.modes.debug_media import (
    cmd_mediaenum, cmd_mediactrl, cmd_mediaprops,
    cmd_audiorecon, cmd_audioplay, cmd_audiorec, cmd_audiocfg,
)


# ---------------------------------------------------------------------------
# Help command
# ---------------------------------------------------------------------------

def _cmd_help(args, state):
    """Display available commands, grouped by purpose.

    When ``state.detailed_view`` is *True* the full usage synopsis and
    description is shown for every command.  When *False* a compact
    listing is printed instead.
    """
    verbose = state.detailed_view

    _GROUPS = [
        ("Scanning", [
            ("scan",     "scan",                                                           "Passive BLE scan (10 s)"),
            ("scann",    "scann",                                                          "Naggy scan (DuplicateData off)"),
            ("scanp",    "scanp <MAC>",                                                    "Pokey scan (spam active 1-s scans)"),
            ("scanb",    "scanb",                                                          "Brute scan (BR/EDR + LE, sequential)"),
            ("dscan",    "dscan [--timeout T]",                                            "Dual scan (LE + BR/EDR, single session)"),
            ("cscan",    "cscan",                                                          "Classic (BR/EDR) passive scan"),
        ]),
        ("Connection", [
            ("connect",    "connect <mac>",                                                "Connect to a device"),
            ("cconnect",   "cconnect <mac>",                                               "Connect to a Classic device & enumerate RFCOMM"),
            ("disconnect", "disconnect",                                                   "Disconnect from current device"),
        ]),
        ("Device Information", [
            ("info",     "info",                                                           "Show device information"),
            ("services", "services",                                                       "List GATT services"),
            ("chars",    "chars [service_uuid]",                                           "List characteristics"),
            ("char",     "char <char_uuid>",                                               "Show detailed characteristic info"),
            ("cservices","cservices",                                                       "List RFCOMM service/channel map for Classic device"),
            ("mines",    "mines",                                                          "Show landmine and permission maps from last enumeration"),
            ("detailed", "detailed [on|off]",                                              "Toggle detailed view mode with UUID decoding"),
        ]),
        ("BLE Enumeration", [
            ("enum",     "enum <MAC>",                                                     "Passive enumeration (no writes)"),
            ("enumn",    "enumn <MAC>",                                                    "Naggy enumeration (multi-read only)"),
            ("enump",    "enump <MAC> [--rounds N] [--verify]",                            "Pokey enumeration with 0/1 write probes"),
            ("enumb",    "enumb <MAC> <CHAR_UUID> [--range a-b] [--patterns ...] [--payload-file FILE] [--force] [--verify]", "Brute enumeration"),
        ]),
        ("BLE Read/Write", [
            ("read",     "read <char_uuid|handle>",                                        "Read characteristic value"),
            ("write",    "write <char_uuid|handle> <value>",                               "Write to characteristic"),
            ("notify",   "notify <char_uuid|handle> [on|off]",                             "Subscribe/unsubscribe to notifications"),
        ]),
        ("Advanced BLE Read/Write", [
            ("multiread",     "multiread <char_uuid|handle> [rounds=N]",                   "Read a characteristic multiple times (e.g., rounds=1000)"),
            ("multiread_all", "multiread_all [rounds=3]",                                  "Read all readable characteristics multiple times"),
            ("brutewrite",    "brutewrite <char_uuid|handle> <pattern> [--range start-end] [--verify]", "Brute force write values"),
        ]),
        ("BR/EDR Classic Profiles", [
            ("csdp",  "csdp <mac> [--connectionless] [--l2ping-count N] [--l2ping-timeout N]", "SDP discovery"),
            ("pbap",  "pbap [--repos PB,ICH] [--format vcard21] [--auto-auth] [--watchdog 8] [--out /path/to/file.vcf]", "Dump phonebook via PBAP"),
            ("ckeep", "ckeep [--first|--svc NAME|CHANNEL]|--close",                       "Open/close keep-alive RFCOMM socket"),
            ("copen", "copen [--first|--svc NAME|CHANNEL]|--close|--status",               "Open/close RFCOMM data socket"),
            ("csend", "csend <hex:XX|str:XX|file:PATH|data>",                              "Send data over RFCOMM"),
            ("crecv", "crecv [--timeout N] [--size N] [--hex] [--save FILE]",              "Receive from RFCOMM"),
            ("craw",  "craw [channel|--svc NAME|--first] [--hex]",                         "Interactive RFCOMM send/recv session"),
            ("crfcomm","crfcomm [--probe] [--timeout N]",                                    "List RFCOMM channels, optionally probe endpoints"),
            ("copp",  "copp send <file> | pull [dest] | exchange <local> [dest]",          "Object Push Profile"),
            ("cmapinfo","cmapinfo",                                                        "MAP version, features & BlueZ compat info"),
            ("cmap",  "cmap folders|list|get|push|inbox|props|read|delete",                "Message Access Profile"),
            ("cftp",  "cftp ls|cd|get|put|mkdir|rm|cp|mv",                                 "File Transfer Profile (browse/transfer)"),
            ("cpan",      "cpan connect|disconnect|status|server",                         "Personal Area Networking (PAN)"),
            ("cprofiles", "cprofiles",                                                     "List Device1.UUIDs (advertised profiles)"),
            ("cprofile",  "cprofile connect|disconnect <UUID>",                            "Connect/disconnect a specific profile"),
            ("chid",      "chid",                                                          "Show HID classification for connected device"),
            ("cspp",      "cspp register [--auth|--no-auth]|unregister|status",            "SPP serial port profile"),
            ("csync", "csync get|put [--location int|sim1]",                               "IrMC Synchronization (phonebook)"),
            ("cbip",  "cbip props|get|thumb <handle>",                                     "Basic Imaging Profile [experimental]"),
            ("cbind", "cbind <ch> [--device N] | release [N] | list",                       "Persistent RFCOMM /dev/rfcommN binding"),
        ]),
        ("Pairing & Security", [
            ("agent", "agent status|register|unregister",                                  "Pairing agent visibility/control (debug)"),
            ("pair",  "pair <MAC> [--pin CODE] [--cap CAP] [--timeout SEC] [--probe]",     "Pair with device (--probe: discover auth method)"),
        ]),
        ("D-Bus Inspection", [
            ("interfaces", "interfaces",                                                   "List available D-Bus interfaces"),
            ("props",      "props [interface]",                                            "List properties for an interface"),
            ("methods",    "methods <interface>",                                          "List methods for an interface"),
            ("signals",    "signals <interface>",                                          "List signals for an interface"),
            ("call",       "call <interface> <method> [args...]",                          "Call a method"),
            ("monitor",    "monitor [start|stop]",                                        "Monitor device properties"),
            ("introspect", "introspect [path]",                                           "Introspect a D-Bus object"),
        ]),
        ("Navigation", [
            ("ls",   "ls [path]",                                                          "List objects at current or specified path"),
            ("cd",   "cd <path>",                                                          "Change to specified D-Bus path"),
            ("pwd",  "pwd",                                                                "Show current D-Bus path"),
            ("back", "back",                                                               "Go back to previous path"),
        ]),
        ("Analysis & Database", [
            ("aoi",      "aoi [--save] [MAC]",                                             "Assets-of-Interest analysis and reporting"),
            ("dbsave",   "dbsave [on|off]",                                                "Toggle database saving"),
            ("dbexport", "dbexport [--save]",                                              "Export device data from database"),
        ]),
        ("Media & Audio", [
            ("mediaenum",  "mediaenum",                                                    "List media D-Bus objects for connected device"),
            ("mediactrl",  "mediactrl <play|pause|stop|next|prev|volume|info|press> [val]","AVRCP media player control"),
            ("mediaprops", "mediaprops",                                                   "Show MediaControl/Player/Transport properties"),
            ("audiorecon", "audiorecon [--mac MAC] [--file F] [--no-play] [--no-record]",  "Audio reconnaissance (backend, cards, play/rec)"),
            ("audioplay",  "audioplay <file> [--system] [--volume N] [--direct]",          "Play audio file to connected BT device"),
            ("audiorec",   "audiorec <output> [--system] [--duration N] [--direct]",       "Record audio from connected BT device"),
            ("audiocfg",   "audiocfg",                                                     "Show host audio backend and BT stack status"),
        ]),
        ("Session", [
            ("help", "help",                                                               "Show this help"),
            ("quit", "quit",                                                               "Exit debug mode"),
        ]),
    ]

    if verbose:
        print("\nAvailable commands (detailed):")
        for group_name, commands in _GROUPS:
            print(f"\n{group_name}:")
            for _cmd_name, usage, desc in commands:
                print(f"  {usage:<60s} - {desc}")
    else:
        print("\nAvailable commands (use 'detailed on' then 'help' for full usage):")
        for group_name, commands in _GROUPS:
            names = ", ".join(c[0] for c in commands)
            print(f"\n{group_name}:")
            print(f"  {names}")
    print()


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

def _build_dispatch_table(state: DebugState):
    """Build the command → handler mapping, binding *state* to every handler."""

    def _wrap(fn):
        """Wrap a two-arg handler(args, state) into a one-arg handler(args)."""
        return lambda args: fn(args, state)

    return {
        "help":          _wrap(_cmd_help),
        "scan":          _wrap(cmd_scan),
        "scann":         _wrap(cmd_scann),
        "scanp":         _wrap(cmd_scanp),
        "scanb":         _wrap(cmd_scanb),
        "dscan":         _wrap(cmd_dscan),
        "cscan":         _wrap(cmd_cscan),
        "connect":       _wrap(cmd_connect),
        "cconnect":      _wrap(cmd_cconnect),
        "disconnect":    _wrap(cmd_disconnect),
        "cservices":     _wrap(cmd_cservices),
        "ckeep":         _wrap(cmd_ckeep),
        "copen":         _wrap(cmd_copen),
        "csend":         _wrap(cmd_csend),
        "crecv":         _wrap(cmd_crecv),
        "craw":          _wrap(cmd_craw),
        "crfcomm":       _wrap(cmd_crfcomm),
        "copp":          _wrap(cmd_copp),
        "cmapinfo":      _wrap(cmd_cmapinfo),
        "cmap":          _wrap(cmd_cmap),
        "cftp":          _wrap(cmd_cftp),
        "cpan":          _wrap(cmd_cpan),
        "cprofiles":     _wrap(cmd_cprofiles),
        "cprofile":      _wrap(cmd_cprofile),
        "chid":          _wrap(cmd_chid),
        "cspp":          _wrap(cmd_cspp),
        "csync":         _wrap(cmd_csync),
        "cbip":          _wrap(cmd_cbip),
        "cbind":         _wrap(cmd_cbind),
        "agent":         _wrap(cmd_agent),
        "pair":          _wrap(cmd_pair),
        "csdp":          _wrap(cmd_csdp),
        "pbap":          _wrap(cmd_pbap),
        "info":          _wrap(cmd_info),
        "interfaces":    _wrap(cmd_interfaces),
        "props":         _wrap(cmd_props),
        "methods":       _wrap(cmd_methods),
        "signals":       _wrap(cmd_signals),
        "call":          _wrap(cmd_call),
        "monitor":       _wrap(cmd_monitor),
        "introspect":    _wrap(cmd_introspect),
        "services":      _wrap(cmd_services),
        "chars":         _wrap(cmd_chars),
        "char":          _wrap(cmd_char),
        "read":          _wrap(cmd_read),
        "write":         _wrap(cmd_write),
        "notify":        _wrap(cmd_notify),
        "detailed":      _wrap(cmd_detailed),
        "enum":          _wrap(cmd_enum),
        "enumn":         _wrap(cmd_enumn),
        "enump":         _wrap(cmd_enump),
        "enumb":         _wrap(cmd_enumb),
        "mines":         _wrap(cmd_mines),
        "aoi":           _wrap(cmd_aoi),
        "dbsave":        _wrap(cmd_dbsave),
        "dbexport":      _wrap(cmd_dbexport),
        "multiread":     _wrap(cmd_multiread),
        "multiread_all": _wrap(cmd_multiread_all),
        "brutewrite":    _wrap(cmd_brutewrite),
        "ls":            _wrap(cmd_ls),
        "cd":            _wrap(cmd_cd),
        "pwd":           _wrap(cmd_pwd),
        "back":          _wrap(cmd_back),
        "mediaenum":     _wrap(cmd_mediaenum),
        "mediactrl":     _wrap(cmd_mediactrl),
        "mediaprops":    _wrap(cmd_mediaprops),
        "audiorecon":    _wrap(cmd_audiorecon),
        "audioplay":     _wrap(cmd_audioplay),
        "audiorec":      _wrap(cmd_audiorec),
        "audiocfg":      _wrap(cmd_audiocfg),
        "quit":          lambda _: None,
        "exit":          lambda _: None,
    }


# ---------------------------------------------------------------------------
# Interactive shell
# ---------------------------------------------------------------------------

def debug_shell(state: DebugState) -> None:
    """Run the interactive debug shell."""
    print_and_log("[*] BLEEP Debug Mode - Type 'help' for commands, 'quit' to exit", LOG__GENERAL)

    ensure_glib_mainloop(state)
    cmds = _build_dispatch_table(state)

    while True:
        try:
            if state.current_device:
                if state.current_path and state.current_path != state.current_device._device_path:
                    path_display = state.current_path.replace(state.current_device._device_path, '')
                    prompt = DEVICE_PROMPT.format(state.current_device.mac_address + ":" + path_display)
                else:
                    prompt = DEVICE_PROMPT.format(state.current_device.mac_address)
            elif state.current_path:
                prompt = f"BLEEP-DEBUG[{state.current_path}]> "
            else:
                prompt = PROMPT

            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        parts = shlex.split(line)
        if not parts:
            continue

        cmd, *rest = parts

        if cmd.lower() in ("quit", "exit"):
            if state.keepalive_sock:
                try:
                    state.keepalive_sock.close()
                except Exception:
                    pass
            if state.monitoring:
                state.monitor_stop_event.set()
                if state.monitor_thread:
                    state.monitor_thread.join(timeout=1.0)
            if state.current_device:
                try:
                    state.current_device.disconnect()
                except Exception:
                    pass
            if state.rfcomm_bindings:
                from bleep.ble_ops.classic.rfcomm import release_rfcomm_channel
                for dev_id in list(state.rfcomm_bindings):
                    try:
                        release_rfcomm_channel(dev_id)
                    except Exception:
                        pass
                state.rfcomm_bindings.clear()
            stop_glib_mainloop(state)
            break

        handler = cmds.get(cmd.lower())
        if not handler:
            print("Unknown command - type 'help' for available commands")
            continue

        try:
            handler(rest)
        except Exception as exc:
            print_and_log(f"[-] Command failed: {exc}", LOG__DEBUG)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BLEEP Debug Mode")
    parser.add_argument("device", nargs="?", help="MAC address of device to connect to")
    parser.add_argument("-m", "--monitor", action="store_true",
                        help="Monitor device properties in real-time")
    parser.add_argument("-n", "--no-connect", action="store_true",
                        help="Don't connect to device (just scan)")
    parser.add_argument("-d", "--detailed", action="store_true",
                        help="Show detailed information including decoded UUIDs and handle information")
    return parser.parse_args(args)


def main(args=None) -> int:
    """Main entry point for Debug Mode."""
    parsed_args = parse_args(args)

    state = DebugState()
    state.detailed_view = parsed_args.detailed

    # Adapter guard — bail early if no BT hardware
    from bleep.core.preflight import require_adapter
    if not require_adapter():
        return 1

    # Wire up the database module
    state.db_available = _DB_AVAILABLE
    state.obs = _obs_module

    if parsed_args.device and not parsed_args.no_connect:
        parsed_args.device = parsed_args.device.upper()
        try:
            print_and_log(f"[*] Connecting to {parsed_args.device}...", LOG__GENERAL)
            dev, mapping, _, _ = _connect_enum(parsed_args.device)
            state.current_device = dev
            state.current_mapping = mapping
            print_and_log(f"[+] Connected to {parsed_args.device}", LOG__GENERAL)

            if parsed_args.monitor:
                from bleep.modes.debug_dbus import cmd_monitor
                cmd_monitor(["start"], state)
        except Exception as exc:
            print_and_log(f"[-] Connection failed: {exc}", LOG__DEBUG)
            print_detailed_dbus_error(exc)
            return 1

    try:
        debug_shell(state)
    except Exception as exc:
        print_and_log(f"[-] Debug shell error: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
