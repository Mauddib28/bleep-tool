"""Declarative CLI ↔ Debug Mode capability registry (CDU-M0).

Single source of truth mapping every BLEEP *capability* to the command name(s)
it exposes on each surface:

* the **CLI** (``bleep <subcommand>``, registered in ``bleep/cli/parsers/*``), and
* the **Debug shell** (interactive ``cmd_*`` verbs bound in
  ``bleep/modes/debug.py::_build_dispatch_table``).

The registry exists so parity is *machine-checkable*: the guard test
``tests/test_cli_debug_parity.py`` asserts that (a) every reachable command on
both surfaces is declared here, and (b) each row's ``parity`` classification is
internally consistent with which surfaces it lists.  As the later uniformity
milestones (CDU-M2..M6, see ``bleep/docs/todo_tracker.md``) land, ``cli-only`` /
``debug-only`` rows flip to ``full`` and their command tuples gain the new verb.

A capability may own **multiple** command names on a surface (1:N) — e.g. the
BLE-scan capability owns the single CLI ``scan`` subcommand but the debug verbs
``scan``/``scann``/``scanp``/``scanb``/``dscan``.  Both ``cli_command`` and
``debug_command`` are therefore tuples.

This module has **no runtime side effects** and imports nothing from the rest of
the package, so it is safe to import from tests and tooling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


PARITY_VALUES = ("full", "partial", "cli-only", "debug-only")


@dataclass(frozen=True)
class Capability:
    """One BLEEP capability and the command names that expose it per surface.

    Attributes:
        name: Stable capability identifier (kebab-case).
        cli_command: CLI subcommand name(s) (incl. argparse aliases) owning this
            capability.  Empty when the capability is not reachable from the CLI.
        debug_command: Debug-shell command name(s) owning this capability.  Empty
            when not reachable from the debug shell.
        shared_impl: Dotted path to the single shared implementation both surfaces
            delegate to (the anti-duplication anchor).
        parity: One of :data:`PARITY_VALUES`.
        rationale: Why the capability is single-surface, or which milestone will
            close the gap.  Required for non-``full`` rows.
        shared_args: Optional dotted path to the ``_add_*_arguments`` builder that
            both surfaces consume, when option sets are shared.
    """

    name: str
    cli_command: Tuple[str, ...] = ()
    debug_command: Tuple[str, ...] = ()
    shared_impl: str = ""
    parity: str = "full"
    rationale: str = ""
    shared_args: str | None = None


# ---------------------------------------------------------------------------
# The registry.  Every CLI subcommand (``bleep/cli/parsers/*``) and every debug
# dispatch key (``bleep/modes/debug.py::_build_dispatch_table``) must appear in
# exactly one row's command tuple.  Keep grouped by domain for readability.
# ---------------------------------------------------------------------------

CAPABILITIES: Tuple[Capability, ...] = (
    # ----- Scanning / enumeration -----------------------------------------
    Capability(
        "ble-scan",
        cli_command=("scan",),
        debug_command=("scan", "scann", "scanp", "scanb", "dscan"),
        shared_impl="bleep.ble_ops.le.scan",
        parity="full",
    ),
    Capability(
        "ble-enum",
        cli_command=("enum-scan",),
        debug_command=("enum", "enumn", "enump", "enumb", "mines"),
        shared_impl="bleep.ble_ops.le.enum_helpers",
        parity="full",
    ),
    Capability(
        "gatt-enum",
        cli_command=("gatt-enum",),
        debug_command=(),
        shared_impl="bleep.modes.gatt_enum.run",
        parity="cli-only",
        rationale="Single-pass GATT enum; debug offers connected-session variants "
                  "via the 'enum*' family (see ble-enum).",
    ),
    Capability(
        "explore",
        cli_command=("explore",),
        debug_command=("explore",),
        shared_impl="bleep.modes.exploration.run",
        parity="full",
        rationale="CDU-M4: debug 'explore' thin-adapts exploration.run; MAC "
                  "defaults to state.current_device when omitted.",
    ),
    Capability(
        "classic-scan",
        cli_command=("classic-scan",),
        debug_command=("cscan",),
        shared_impl="bleep.modes.classic_scan.run",
        shared_args="bleep.cli.parsers.classic._add_classic_scan_arguments",
        parity="full",
        rationale="CDU-M7a: debug 'cscan' now delegates to classic_scan.run via "
                  "parse_as_cli (shared _add_classic_scan_arguments builder), gaining "
                  "the CLI UUID/RSSI/pathloss/timeout/adapter filters + DB persistence.",
    ),

    # ----- Connection ------------------------------------------------------
    Capability(
        "connect",
        cli_command=("connect",),
        debug_command=("connect", "disconnect", "info"),
        shared_impl="bleep.ble_ops.le.connect",
        parity="full",
    ),
    Capability(
        "classic-connect",
        cli_command=("classic-connect",),
        debug_command=("cconnect", "cservices"),
        shared_impl="bleep.modes.classic_connect.run",
        parity="full",
    ),
    Capability(
        "connect-profile",
        cli_command=("connect-profile",),
        debug_command=("cprofile",),
        shared_impl="bleep.dbuslayer.device_classic",
        parity="full",
    ),
    Capability(
        "list-profiles",
        cli_command=(),
        debug_command=("cprofiles",),
        shared_impl="bleep.dbuslayer.device_classic",
        parity="debug-only",
        rationale="Lists advertised Device1.UUIDs on the connected device; "
                  "interactive-only inspection.",
    ),

    # ----- Classic profiles / SDP -----------------------------------------
    Capability(
        "classic-enum",
        cli_command=("classic-enum",),
        debug_command=("cenum", "csdp"),
        shared_impl="bleep.analysis.sdp_analyzer",
        parity="full",
        rationale="CDU-M5: debug 'cenum' thin-adapts the same classic_enum.run "
                  "(--version-info/--analyze/--sdp-source SDP analysis); the "
                  "separate 'csdp' verb keeps its raw socket-oriented SDP-browse "
                  "semantics.",
    ),
    Capability(
        "classic-pbap",
        cli_command=("classic-pbap",),
        debug_command=("pbap",),
        shared_impl="bleep.ble_ops.classic.pbap",
        parity="full",
        shared_args="bleep.cli.parsers.classic._add_pbap_arguments",
    ),
    Capability(
        "classic-opp",
        cli_command=("classic-opp",),
        debug_command=("copp",),
        shared_impl="bleep.ble_ops.classic.opp",
        parity="full",
    ),
    Capability(
        "classic-map",
        cli_command=("classic-map",),
        debug_command=("cmap", "cmapinfo"),
        shared_impl="bleep.ble_ops.classic.map",
        parity="full",
    ),
    Capability(
        "classic-ftp",
        cli_command=("classic-ftp",),
        debug_command=("cftp",),
        shared_impl="bleep.ble_ops.classic.ftp",
        parity="full",
    ),
    Capability(
        "classic-pan",
        cli_command=("classic-pan",),
        debug_command=("cpan",),
        shared_impl="bleep.modes.classic_profiles.run_pan",
        parity="full",
        rationale="CDU-M1.5 done: server verbs unified to server-reg/server-unreg "
                  "on both surfaces via pan.resolve_pan_server_verb (debug retains "
                  "the 'server register|unregister' two-token alias).",
    ),
    Capability(
        "classic-spp",
        cli_command=("classic-spp",),
        debug_command=("cspp",),
        shared_impl="bleep.ble_ops.classic.spp",
        parity="full",
    ),
    Capability(
        "classic-sync",
        cli_command=("classic-sync",),
        debug_command=("csync",),
        shared_impl="bleep.ble_ops.classic.sync",
        parity="full",
    ),
    Capability(
        "classic-bip",
        cli_command=("classic-bip",),
        debug_command=("cbip",),
        shared_impl="bleep.ble_ops.classic.bip",
        parity="full",
    ),
    Capability(
        "classic-rfcomm",
        cli_command=("classic-rfcomm",),
        debug_command=("crfcomm", "cbind"),
        shared_impl="bleep.ble_ops.classic.rfcomm",
        parity="full",
    ),
    Capability(
        "rfcomm-raw",
        cli_command=(),
        debug_command=("copen", "csend", "crecv", "craw", "ckeep"),
        shared_impl="bleep.ble_ops.classic.rfcomm",
        parity="debug-only",
        rationale="Interactive/stateful RFCOMM socket I/O; meaningless as a "
                  "one-shot CLI verb.",
    ),
    Capability(
        "network-enum",
        cli_command=("network-enum",),
        debug_command=("netenum",),
        shared_impl="bleep.modes.classic_profiles.run_network_enum",
        parity="full",
        rationale="CDU-M3: debug 'netenum' thin-adapts the same run_network_enum "
                  "(parsed via the real CLI subparser).",
    ),
    Capability(
        "classic-ping",
        cli_command=("classic-ping",),
        debug_command=("cping",),
        shared_impl="bleep.ble_ops.classic.ping.classic_l2ping",
        parity="full",
        rationale="CDU-M3: debug 'cping' thin-adapts the same classic_l2ping.",
    ),
    Capability(
        "hid",
        cli_command=("hid-info",),
        debug_command=("chid",),
        shared_impl="bleep.ble_ops.hid.build_hid_context",
        parity="full",
        rationale="CDU-M1.6 done: both connected and connectionless classification "
                  "on both surfaces via the shared bleep.ble_ops.hid evidence "
                  "builder (CLI hid-info --connect; debug chid <MAC>).",
    ),

    # ----- Media & audio ---------------------------------------------------
    Capability(
        "media-enum",
        cli_command=("media-enum",),
        debug_command=("mediaenum", "mediaprops"),
        shared_impl="bleep.dbuslayer.media",
        parity="full",
    ),
    Capability(
        "media-ctrl",
        cli_command=("media-ctrl",),
        debug_command=("mediactrl",),
        shared_impl="bleep.modes.media.control_media_device",
        parity="full",
    ),
    Capability(
        "audio-recon",
        cli_command=("audio-recon",),
        debug_command=("audiorecon",),
        shared_impl="bleep.ble_ops.audio.audio_recon.run_audio_recon",
        parity="full",
    ),
    Capability(
        "audio-play",
        cli_command=("audio-play",),
        debug_command=("audioplay",),
        shared_impl="bleep.dbuslayer.media_stream.MediaStreamManager",
        parity="full",
    ),
    Capability(
        "audio-record",
        cli_command=("audio-record",),
        debug_command=("audiorec",),
        shared_impl="bleep.dbuslayer.media_stream.MediaStreamManager",
        parity="full",
    ),
    Capability(
        "audio-config",
        cli_command=("audio-config",),
        debug_command=("audiocfg",),
        shared_impl="bleep.ble_ops.audio.alsa_config",
        parity="full",
        rationale="CDU-M5: debug 'audiocfg' keeps its no-arg read-only "
                  "diagnostics and gains the show/add/remove/tunnel/backup/restore "
                  "write sub-surface delegating to the same run_audio_config core.",
    ),
    Capability(
        "audio-profiles",
        cli_command=("audio-profiles",),
        debug_command=(),
        shared_impl="bleep.modes.audio.run_audio_profiles",
        parity="cli-only",
        rationale="ALSA/BlueZ profile correlation listing; no session state needed.",
    ),
    Capability(
        "audio-intercept",
        cli_command=("audio-intercept",),
        debug_command=("audiointercept",),
        shared_impl="bleep.ble_ops.audio.audio_transcribe.run_audio_intercept",
        parity="full",
        rationale="CDU-M4: debug 'audiointercept' thin-adapts run_audio_intercept; "
                  "MAC defaults to state.current_device when omitted.",
    ),
    Capability(
        "amusica",
        cli_command=("amusica",),
        debug_command=(),
        shared_impl="bleep.modes.amusica.main",
        parity="cli-only",
        rationale="Self-contained audio-manipulation sub-CLI (own arg surface).",
    ),

    # ----- Pairing & agent -------------------------------------------------
    Capability(
        "pair",
        cli_command=("pair",),
        debug_command=("pair",),
        shared_impl="bleep.pairing",
        parity="full",
        shared_args="bleep.cli.parsers.pairing._add_pair_arguments",
    ),
    Capability(
        "agent",
        cli_command=("agent",),
        debug_command=("agent",),
        shared_impl="bleep.dbuslayer.agent",
        parity="full",
        rationale="CDU-M7b: debug 'agent' keeps its session status/register/"
                  "unregister verbs and gains trust/untrust/remove-bond/list-trusted/"
                  "list-bonded management delegating to the shared bleep.modes.agent.run "
                  "(one-shot ops that return before the agent loop).",
    ),

    # ----- Data / analysis / DB -------------------------------------------
    Capability(
        "db",
        cli_command=("db",),
        debug_command=("db", "dbsave", "dbexport"),
        shared_impl="bleep.modes.db.run",
        parity="full",
        rationale="CDU-M3: debug 'db' thin-adapts the full CLI 'bleep db' surface "
                  "(list/show/report/timeline/export/uuids/maintain) via bleep.modes.db.run; "
                  "dbsave/dbexport remain as session-scoped convenience helpers.",
    ),
    Capability(
        "aoi",
        cli_command=("aoi",),
        debug_command=("aoi",),
        shared_impl="bleep.analysis.aoi_analyser",
        parity="full",
        rationale="CDU-M7c: debug 'aoi' keeps its live single-device helper "
                  "(aoi [--save] [MAC]) and, when the first token is a CLI AoI "
                  "subcommand (scan/analyze/list/report/export/db), delegates to the "
                  "same aoi.run pipeline via parse_as_cli.",
        shared_args="bleep.cli.parsers.aoi._add_aoi_arguments",
    ),
    Capability(
        "analyse",
        cli_command=("analyse", "analyze"),
        debug_command=(),
        shared_impl="bleep.modes.analysis.main",
        parity="cli-only",
        rationale="Offline post-processing of JSON dumps; no live session.",
    ),
    Capability(
        "survey",
        cli_command=("survey",),
        debug_command=("survey", "survey-status"),
        shared_impl="bleep.modes.survey",
        parity="full",
        shared_args="bleep.cli.parsers.survey._add_survey_arguments",
    ),
    Capability(
        "beacon-identification",
        cli_command=("beacon-identification",),
        debug_command=(),
        shared_impl="bleep.modes.beacon_identification.run",
        parity="cli-only",
        rationale="Targeted beacon discovery/scoring; wraps survey census with post-filter.",
        shared_args="bleep.cli.parsers.beacon._add_beacon_identification_arguments",
    ),

    # ----- Signals ---------------------------------------------------------
    Capability(
        "signal",
        cli_command=("signal",),
        debug_command=("signal",),
        shared_impl="bleep.modes.signal.run",
        parity="full",
        rationale="CDU-M4: timed 'signal' debug verb reuses the live "
                  "state.current_device (signal.run(device=...), no reconnect); "
                  "distinct from the lightweight 'notify' subscribe.",
    ),
    Capability(
        "signal-config",
        cli_command=("signal-config",),
        debug_command=(),
        shared_impl="bleep.signals.cli.main",
        parity="cli-only",
        rationale="Signal-capture configuration management.",
    ),

    # ----- GATT interaction (interactive, debug-only) ---------------------
    Capability(
        "gatt-interact",
        cli_command=(),
        debug_command=("services", "chars", "char", "read", "write", "notify",
                       "detailed"),
        shared_impl="bleep.ble_ops.le",
        parity="debug-only",
        rationale="Interactive per-characteristic GATT operations on the live "
                  "connected device.",
    ),
    Capability(
        "gatt-advanced",
        cli_command=(),
        debug_command=("multiread", "multiread_all", "brutewrite"),
        shared_impl="bleep.ble_ops.le.enum_helpers",
        parity="debug-only",
        rationale="Interactive multi-read / brute-write against the live device.",
    ),

    # ----- D-Bus inspection (interactive, debug-only) ---------------------
    Capability(
        "dbus-navigate",
        cli_command=(),
        debug_command=("ls", "cd", "pwd", "back"),
        shared_impl="bleep.modes.debug_dbus",
        parity="debug-only",
        rationale="Interactive D-Bus object-tree navigation.",
    ),
    Capability(
        "dbus-introspect",
        cli_command=(),
        debug_command=("interfaces", "props", "methods", "signals", "call",
                       "introspect"),
        shared_impl="bleep.modes.debug_dbus",
        parity="debug-only",
        rationale="Low-level D-Bus introspection and direct method invocation.",
    ),
    Capability(
        "dbus-property-monitor",
        cli_command=(),
        debug_command=("monitor",),
        shared_impl="bleep.modes.debug_dbus",
        parity="debug-only",
        rationale="Live PropertiesChanged device monitor (distinct from the CLI "
                  "Advertisement Monitor; see advertisement-monitor).",
    ),

    # ----- One-shot / maintenance modes (CLI-only) ------------------------
    Capability(
        "gatt-server",
        cli_command=("gatt-server",),
        debug_command=("gattserver",),
        shared_impl="bleep.modes.gatt_server.run",
        parity="full",
        rationale="CDU-M4: debug 'gattserver' thin-adapts gatt_server.run inside "
                  "foreground_loop_handoff (core runs its own GLib loop).",
    ),
    Capability(
        "advertise",
        cli_command=("advertise",),
        debug_command=("advertise",),
        shared_impl="bleep.modes.advertise.run",
        parity="full",
        rationale="CDU-M4: debug 'advertise' thin-adapts advertise.run inside "
                  "foreground_loop_handoff (core runs its own GLib loop).",
    ),
    Capability(
        "advertisement-monitor",
        cli_command=("advertise-monitor",),
        debug_command=("advertise-monitor",),
        shared_impl="bleep.modes.monitor.run",
        shared_args="bleep.cli.parsers.utility._add_advertise_monitor_start_arguments",
        parity="full",
        rationale="CDU-M2: hard-renamed CLI 'monitor' -> 'advertise-monitor' (no "
                  "alias) and added the matching 'advertise-monitor' debug verb "
                  "(bleep.modes.debug_advmon) delegating to the same monitor.run; "
                  "distinct from the debug property monitor (dbus-property-monitor).",
    ),
    Capability(
        "device-sets",
        cli_command=("device-sets",),
        debug_command=("devicesets",),
        shared_impl="bleep.modes.device_sets.handle_device_sets",
        parity="full",
        rationale="CDU-M4: debug 'devicesets' thin-adapts handle_device_sets.",
    ),
    Capability(
        "mesh",
        cli_command=("mesh",),
        debug_command=("mesh",),
        shared_impl="bleep.modes.mesh_provision.handle_mesh",
        parity="full",
        rationale="CDU-M4: debug 'mesh' thin-adapts handle_mesh (accepted 2026-07-29).",
    ),
    Capability(
        "ctf",
        cli_command=("ctf",),
        debug_command=("ctf",),
        shared_impl="bleep.modes.blectf.run",
        parity="full",
        rationale="CDU-M4: optional 'ctf' debug verb as a secondary BLE-CTF "
                  "interaction path (accepted 2026-07-29).",
    ),
    Capability(
        "uuid-translate",
        cli_command=("uuid-translate", "uuid-lookup"),
        debug_command=("uuidtr",),
        shared_impl="bleep.modes.uuid_translate.main",
        parity="full",
        rationale="CDU-M3: debug 'uuidtr' passes tokens straight to the same "
                  "uuid_translate.main.",
    ),
    Capability(
        "adapter-config",
        cli_command=("adapter-config",),
        debug_command=("adaptercfg",),
        shared_impl="bleep.modes.adapter_config.handle_adapter_config",
        parity="full",
        rationale="CDU-M3: debug 'adaptercfg' thin-adapts the same "
                  "handle_adapter_config (parsed via the real CLI subparser).",
    ),
    Capability(
        "refresh-refs",
        cli_command=("refresh-refs",),
        debug_command=(),
        shared_impl="bleep.modes.refresh_refs.run",
        parity="cli-only",
        rationale="Intentionally CLI-only: batch reference-data regeneration, no "
                  "session value (accepted 2026-07-29).",
    ),

    # ----- Shells / REPLs --------------------------------------------------
    Capability(
        "debug-shell",
        cli_command=("debug",),
        debug_command=(),
        shared_impl="bleep.modes.debug.main",
        parity="cli-only",
        rationale="Entry point that launches the Debug Mode shell itself.",
    ),
    Capability(
        "interactive-repl",
        cli_command=("interactive",),
        debug_command=(),
        shared_impl="bleep.modes.interactive.main",
        parity="cli-only",
        rationale="Separate high-level REPL console.",
    ),
    Capability(
        "user-explorer",
        cli_command=("user",),
        debug_command=(),
        shared_impl="bleep.modes.user.run",
        parity="cli-only",
        rationale="Guided user-friendly explorer; separate UX from the debug shell.",
    ),

    # ----- Debug session meta ---------------------------------------------
    Capability(
        "session-meta",
        cli_command=(),
        debug_command=("help", "quit", "exit"),
        shared_impl="bleep.modes.debug",
        parity="debug-only",
        rationale="Debug shell meta commands (help / exit).",
    ),
)


def cli_command_names() -> set:
    """All CLI command names (incl. aliases) declared across the registry."""
    names: set = set()
    for cap in CAPABILITIES:
        names.update(cap.cli_command)
    return names


def debug_command_names() -> set:
    """All debug-shell command names declared across the registry."""
    names: set = set()
    for cap in CAPABILITIES:
        names.update(cap.debug_command)
    return names
