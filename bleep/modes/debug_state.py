"""Shared mutable state and GLib mainloop management for the debug shell.

All debug submodules receive a single ``DebugState`` instance that centralises
the session state previously held in module-level globals.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__DEBUG

try:
    import gi
    gi.require_version('GLib', '2.0')
    from gi.repository import GLib as _GLib
except ImportError:
    print_and_log("[-] Failed to import GLib - monitoring will not work", LOG__DEBUG)
    _GLib = None


# Prompt templates
PROMPT = "BLEEP-DEBUG> "
DEVICE_PROMPT = "BLEEP-DEBUG[{}]> "


@dataclass
class DebugState:
    """Centralised session state for the debug-mode shell."""

    current_device: Any = None
    current_mapping: Optional[Dict] = None
    current_mode: str = "ble"
    keepalive_sock: Any = None
    current_path: Optional[str] = None
    monitoring: bool = False
    monitor_thread: Optional[threading.Thread] = None
    monitor_stop_event: threading.Event = field(default_factory=threading.Event)
    notification_handlers: Dict = field(default_factory=dict)
    detailed_view: bool = False
    path_history: List[str] = field(default_factory=list)
    db_save_enabled: bool = True
    path_cache: Dict = field(default_factory=dict)
    glib_loop: Any = None
    glib_thread: Optional[threading.Thread] = None
    current_mine_map: Any = None
    current_perm_map: Any = None
    db_available: bool = False
    obs: Any = None


# ---------------------------------------------------------------------------
# GLib MainLoop management
# ---------------------------------------------------------------------------

def ensure_glib_mainloop(state: DebugState) -> None:
    """Start a GLib MainLoop in a daemon thread if one isn't already running.

    The background loop allows D-Bus agent callbacks (``RequestPinCode``, etc.)
    to be dispatched while the interactive prompt blocks on ``input()``.
    """
    if state.glib_thread is not None and state.glib_thread.is_alive():
        return

    if _GLib is None:
        print_and_log("[-] GLib not available – agent callbacks will not work", LOG__DEBUG)
        return

    state.glib_loop = _GLib.MainLoop()

    def _run():
        try:
            state.glib_loop.run()
        except Exception:
            pass

    state.glib_thread = threading.Thread(target=_run, daemon=True, name="glib-mainloop")
    state.glib_thread.start()
    print_and_log("[*] GLib MainLoop started (background thread)", LOG__DEBUG)


def stop_glib_mainloop(state: DebugState) -> None:
    """Stop the background GLib MainLoop if running."""
    if state.glib_loop is not None:
        try:
            state.glib_loop.quit()
        except Exception:
            pass
        state.glib_loop = None

    if state.glib_thread is not None:
        state.glib_thread.join(timeout=2.0)
        state.glib_thread = None
