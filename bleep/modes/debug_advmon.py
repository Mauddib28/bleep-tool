"""Debug-shell adapter for the Advertisement Monitor (CDU-M2).

Thin wrapper exposing the CLI ``advertise-monitor`` capability inside the
interactive debug shell.  The real work lives in :mod:`bleep.modes.monitor`
(the same module the CLI ``advertise-monitor`` subcommand delegates to), so the
two surfaces cannot drift: this module only builds the argument
``Namespace`` and manages debug-shell-specific loop/signal handoff.

Distinct from the debug ``monitor`` verb (:func:`bleep.modes.debug_dbus.cmd_monitor`),
which is a live ``PropertiesChanged`` device-property monitor — see the parity
notes in ``bleep/docs/debug_mode.md``.
"""

from __future__ import annotations

from typing import List

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.modes.debug_state import DebugState, foreground_loop_handoff


def _print_usage() -> None:
    print_and_log("Usage: advertise-monitor {caps|start}", LOG__GENERAL)
    print_and_log("  caps    Show AdvertisementMonitorManager1 capabilities", LOG__GENERAL)
    print_and_log("  start   Register monitor(s) and stream DeviceFound/Lost events "
                  "(Ctrl-C to stop)", LOG__GENERAL)
    print_and_log("  Options (start): [-p OFF:AD:HEX ...] [--rssi-high N] "
                  "[--rssi-low N] [--duration N] [--adapter hciX]", LOG__GENERAL)


def cmd_advertise_monitor(args: List[str], state: DebugState) -> None:
    """``advertise-monitor caps|start`` — kernel-offloaded advertisement monitor.

    Parses through the real CLI ``advertise-monitor`` subparser (``parse_as_cli``,
    the shared anti-drift seam — CDU-M9) and delegates to
    :func:`bleep.modes.monitor.run` (terminal ``OutputContext``), the same core the
    CLI subcommand uses.  For ``start`` the shared implementation runs its own
    foreground GLib main loop and installs SIGINT/SIGTERM handlers, so the
    background debug loop is stopped for the duration and the shell's signal
    handlers are saved/restored via :func:`foreground_loop_handoff`.
    """
    from bleep.modes.debug_cli_adapters import parse_as_cli

    opts = parse_as_cli("advertise-monitor", args)
    if opts is None:
        _print_usage()
        return

    action = getattr(opts, "monitor_action", None)
    if not action:
        _print_usage()
        return

    from bleep.modes.monitor import run as monitor_run

    if action == "caps":
        monitor_run(opts)
        return

    # action == "start": monitor runs its own foreground GLib loop and installs
    # SIGINT/SIGTERM handlers — hand the default context off and restore Ctrl-C.
    with foreground_loop_handoff(state):
        monitor_run(opts)
