"""Process-level GLib main-loop service (multi-adapter scalability, D1.4).

A single :class:`GLib.MainLoop` is run on one dedicated daemon thread so that
several adapter sessions (one per ``hciN``) can collect concurrently without
each blocking a caller thread on its own loop.  D-Bus signals
(``PropertiesChanged`` / ``InterfacesAdded``) are delivered on this loop thread
to the shared :class:`~bleep.dbuslayer.signals.system_dbus__bluez_signals`
handlers, while collectors issue their (thread-safe) BlueZ method calls —
``StartDiscovery`` / ``GetManagedObjects`` / ``StopDiscovery`` — from the
orchestrator thread.  ``dbus.mainloop.glib.threads_init()`` (invoked at import
time in :mod:`bleep.core.config`) makes those cross-thread calls safe.

The service is **reference-counted**: each collector/orchestrator calls
:py:meth:`acquire` on entry and :py:meth:`release` on exit; the loop starts on
the first acquire and stops when the last holder releases.  Nested/independent
users therefore share one loop.

Feasibility note — thread-per-collector (deferred)
---------------------------------------------------
An alternative to one shared loop is to give **each** collector its own
:class:`GLib.MainContext` (via ``GLib.MainContext.new()`` + ``push_thread_default``)
and its own loop on a dedicated thread.  That removes any single-loop
serialization but is harder to get right: dbus-python binds signal matches to
the *default* context, so each thread would need its own bus connection and
explicit ``add_signal_receiver`` on a per-context bus, and BlueZ
``ObjectManager`` signals would be received once per connection (dedup needed).
The shared-loop model is simpler, sufficient for the expected handful of
adapters, and keeps a single signal-routing path.  Revisit thread-per-collector
only if profiling shows the shared loop thread saturating (e.g. very high
advertising rates across many adapters); the :func:`run_on_loop` helper and the
reference-counted lifecycle here are the seam where that change would land.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Optional

from gi.repository import GLib

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__USER

__all__ = [
    "loop_service",
    "MainLoopService",
    "mainloop_suppressed",
    "suppress_mainloop",
    "warn_mainloop_suppressed",
    "MAINLOOP_SUPPRESSED_LOSSES",
]

#: What stops working without a loop thread dispatching the connection.  Used
#: verbatim in the user-facing warning so the list cannot drift from reality.
MAINLOOP_SUPPRESSED_LOSSES = (
    "AdvMonitor callbacks (Activate/DeviceFound/Release) — --listen-monitor "
    "registers but goes inert",
    "pairing agent requests (RequestPasskey/RequestConfirmation) — pairing "
    "cannot complete",
    "GATT notifications and indications (StartNotify delivers nothing)",
    "GATT server and advertise modes (inbound method calls unanswered)",
)

# Set by --no-mainloop; the env var remains as an override for diagnostics.
_SUPPRESS_REQUESTED = False
_WARNED = False


def suppress_mainloop(enabled: bool = True) -> None:
    """Request a loop-free process (the ``--no-mainloop`` CLI flag).

    ``BLEEP_NO_MAINLOOP`` does the same thing and still wins if set, so
    existing diagnostic invocations keep working.
    """
    global _SUPPRESS_REQUESTED
    _SUPPRESS_REQUESTED = bool(enabled)


def mainloop_suppressed() -> bool:
    """True when this process should run without a GLib main loop.

    Set by :func:`suppress_mainloop` (``--no-mainloop``) or the
    ``BLEEP_NO_MAINLOOP`` environment variable.

    Rationale (docs/mainloop_architecture.md 'Thread-safety constraint'): the dual-antenna heap
    corruption needs a GLib loop dispatching a connection on one thread while
    another blocks in ``call_blocking``.  Without a loop thread that pair
    cannot form — a 2h loop-free survey ran clean where the same command with
    the loop aborted at 54.7 min.  Collectors harvest by polling
    ``GetManagedObjects`` and enumeration waits on the ``ServicesResolved``
    *property*, so neither needs signal delivery; everything in
    :data:`MAINLOOP_SUPPRESSED_LOSSES` does.
    """
    if _SUPPRESS_REQUESTED:
        return True
    return os.environ.get("BLEEP_NO_MAINLOOP", "") not in ("", "0", "false", "False")


def warn_mainloop_suppressed(force: bool = False) -> bool:
    """Emit the user-visible loop-free warning once.  Returns True if emitted.

    Deliberately ``LOG__USER`` rather than ``LOG__DEBUG``: the degradation is
    silent (AdvMonitor still registers, collection barely moves) so a debug-only
    notice — which is what shipped first and never appeared in any run's output
    — is not good enough.
    """
    global _WARNED
    if not mainloop_suppressed():
        return False
    if _WARNED and not force:
        return False
    _WARNED = True
    print_and_log(
        "[!] Running WITHOUT a GLib main loop (--no-mainloop). No thread "
        "dispatches inbound D-Bus traffic, so the following are DISABLED:",
        LOG__USER,
    )
    for loss in MAINLOOP_SUPPRESSED_LOSSES:
        print_and_log(f"[!]   - {loss}", LOG__USER)
    print_and_log(
        "[!] Survey collection and GATT enumeration are unaffected (both poll). "
        "Omit --no-mainloop if you need any of the above.",
        LOG__USER,
    )
    return True


class MainLoopService:
    """Reference-counted owner of a single shared :class:`GLib.MainLoop`."""

    def __init__(self) -> None:
        self._loop: Optional[GLib.MainLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._refcount = 0
        self._lock = threading.RLock()

    # -- lifecycle ----------------------------------------------------------
    def acquire(self) -> None:
        """Increment the hold count, starting the loop thread on first use."""
        if mainloop_suppressed():
            warn_mainloop_suppressed()
            print_and_log("[*] Main-loop service suppressed", LOG__DEBUG)
            return
        with self._lock:
            self._refcount += 1
            if self._thread is not None and self._thread.is_alive():
                return
            self._loop = GLib.MainLoop()
            self._thread = threading.Thread(
                target=self._run, name="bleep-mainloop", daemon=True
            )
            self._thread.start()
            print_and_log("[*] Shared main-loop service started", LOG__DEBUG)

    def release(self) -> None:
        """Decrement the hold count, stopping the loop when it reaches zero."""
        if mainloop_suppressed():
            return
        with self._lock:
            if self._refcount > 0:
                self._refcount -= 1
            if self._refcount > 0 or self._loop is None:
                return
            loop = self._loop
            self._loop = None
            self._thread = None
        # Quit on the loop thread; idle_add is thread-safe.
        GLib.idle_add(loop.quit)
        print_and_log("[*] Shared main-loop service stopped", LOG__DEBUG)

    def _run(self) -> None:
        loop = self._loop
        if loop is None:
            return
        try:
            loop.run()
        except Exception as exc:  # pragma: no cover - defensive
            print_and_log(f"[!] Shared main-loop crashed: {exc}", LOG__DEBUG)

    # -- helpers ------------------------------------------------------------
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def run_on_loop(self, callback: Callable[[], None]) -> None:
        """Schedule *callback* to execute once on the loop thread (thread-safe)."""

        def _once() -> bool:
            try:
                callback()
            except Exception as exc:  # pragma: no cover - defensive
                print_and_log(f"[!] run_on_loop callback error: {exc}", LOG__DEBUG)
            return False  # GLib: do not repeat

        GLib.idle_add(_once)


# Process-wide singleton.
loop_service = MainLoopService()
