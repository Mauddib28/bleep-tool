"""Shared helper to invoke an asynchronous D-Bus method and block for its result.

BlueZ manager registrations (``RegisterAdvertisement`` / ``RegisterApplication``
/ ``RegisterMonitor``) are asynchronous: their ``reply_handler`` /
``error_handler`` callbacks are dispatched only while a GLib main loop iterates.
During the registration handshake BlueZ also calls *back* into the
locally-exported objects (``GetAll`` / ``GetManagedObjects`` / ``ReadValue``), so
a loop must run for the handshake to complete at all — a plain ``time.sleep()``
busy-wait deadlocks and always times out.

This helper runs a temporary :class:`GLib.MainLoop` when no background loop is
already iterating the default context (mirroring the established pattern in
:mod:`bleep.dbuslayer.agent`), surfacing the real error on failure.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from gi.repository import GLib

from bleep.core.log import print_and_log, LOG__GENERAL

__all__ = ["call_async_await", "DEFAULT_WAIT_TIMEOUT"]

# Default seconds to wait for an async reply.  Exposed as a module attribute so
# it can be tuned (e.g. lowered in tests) without touching call sites.
DEFAULT_WAIT_TIMEOUT = 10.0


def call_async_await(
    method: Callable[..., Any],
    *args: Any,
    label: str = "D-Bus call",
    error_log_level: int = LOG__GENERAL,
    wait_timeout: Optional[float] = None,
    **kwargs: Any,
) -> bool:
    """Invoke *method* asynchronously and block until it completes.

    Parameters
    ----------
    method:
        A bound :class:`dbus.Interface` method that accepts ``reply_handler``
        and ``error_handler`` keyword arguments.
    *args, **kwargs:
        Arguments forwarded to *method*.
    label:
        Human-readable operation name used in failure/timeout log lines.
    error_log_level:
        Log level for the failure/timeout message (default: user-visible).
    wait_timeout:
        Maximum seconds to wait before giving up (defaults to
        :data:`DEFAULT_WAIT_TIMEOUT`).

    Returns
    -------
    bool
        ``True`` if the remote method replied successfully; ``False`` on a
        reported error or timeout (the cause is logged).
    """
    if wait_timeout is None:
        wait_timeout = DEFAULT_WAIT_TIMEOUT

    state: Dict[str, Any] = {"done": False, "error": None}
    holder: Dict[str, Any] = {"loop": None}

    def _quit_loop() -> None:
        loop = holder["loop"]
        if loop is not None and loop.is_running():
            loop.quit()

    def _on_reply(*_reply: Any) -> None:
        state["done"] = True
        _quit_loop()

    def _on_error(error: Exception) -> None:
        state["error"] = error
        state["done"] = True
        _quit_loop()

    method(*args, reply_handler=_on_reply, error_handler=_on_error, **kwargs)

    if not state["done"]:
        # If another thread already owns the default context it runs a loop that
        # dispatches our handlers; otherwise we must iterate one ourselves.
        context = GLib.MainContext.default()
        background_loop_running = not context.acquire()
        if not background_loop_running:
            context.release()

        if background_loop_running:
            deadline = time.monotonic() + wait_timeout
            while not state["done"] and time.monotonic() < deadline:
                time.sleep(0.02)
        else:
            loop = GLib.MainLoop()
            holder["loop"] = loop
            timer_fired = {"v": False}

            def _on_deadline() -> bool:
                timer_fired["v"] = True
                _quit_loop()
                return False

            # GLib's timer uses its own monotonic clock, so the loop always
            # terminates within wait_timeout regardless of external state.
            timer = GLib.timeout_add(int(wait_timeout * 1000), _on_deadline)
            if not state["done"]:
                loop.run()
            if not timer_fired["v"]:
                GLib.source_remove(timer)

    if state["error"] is not None:
        print_and_log(f"[-] {label} failed: {state['error']}", error_log_level)
        return False
    if not state["done"]:
        print_and_log(
            f"[-] {label} timed out after {wait_timeout:.0f}s", error_log_level
        )
        return False
    return True
