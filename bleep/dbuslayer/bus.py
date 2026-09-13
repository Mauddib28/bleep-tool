"""Connection ownership for D-Bus: which thread may call on which bus.

Background (2026-09-05 abort investigation)
-------------------------------------------
``dbus.SystemBus()`` is a **process-wide singleton** — every caller in BLEEP
received the *same* :class:`dbus.Bus` object (verified:
``dbus.SystemBus() is dbus.SystemBus()`` → ``True``).  That connection is
attached to ``DBusGMainLoop`` and is therefore read/dispatched by the
:mod:`~bleep.dbuslayer.loop_service` loop thread, which also mutates GLib's
watch/timeout source list on its behalf.

A dual-antenna survey had up to four threads issuing **blocking** calls on that
one connection at the same time:

* the orchestrator/collector thread (``StartDiscovery`` / ``GetManagedObjects``),
* the ``bleep-enumerator`` worker (proxy construction + GATT),
* ``bluez_monitor`` (a periodic ``get_name_owner`` health check),
* while the loop thread dispatched incoming messages on it.

That reproducibly aborted the process inside libdbus/GLib with
``malloc(): unaligned tcache chunk detected`` and
``malloc(): unaligned fastbin chunk detected``, always in
``call_blocking`` → ``get_name_owner``.  ``threads_init()`` is *not* missing
(``core/config.py:97``, dbus-python 1.4.0 / libdbus 1.16.2); the hazard is the
GLib main-loop integration, which is not safe against a second thread adding
and removing watches while the loop iterates them.

The rule this module enforces
-----------------------------
**One connection is touched by one thread.**

* The shared singleton keeps carrying every *signal match*, and the loop thread
  keeps dispatching it.  Signal delivery is therefore unchanged — the registry
  in :mod:`bleep.dbuslayer.signals` installs broad matches once
  (``signals.py:876-894``) and ``register_device()`` does no D-Bus I/O, so
  handlers such as ``_LEDevice._properties_changed`` still fire.
* The main thread also keeps the shared bus, so existing single-threaded flows
  and the collector path behave exactly as before.
* **Every other thread gets its own private connection** for blocking method
  calls, so worker threads at least stop sharing message queues and
  pending-call tables with the collector.

Callers do not choose: :func:`get_bus` decides from the calling thread.

.. warning::
   **This does not achieve isolation from the loop thread, and cannot.**
   Because ``core/config.py`` calls ``DBusGMainLoop(set_as_default=True)``,
   every connection dbus-python creates — including ``private=True`` ones — is
   attached to the **default GLib main context**, so the loop thread dispatches
   them too.  Verified 2026-09-06: an async call on a ``private=True`` bus was
   dispatched by a ``GLib.MainLoop`` running on another thread.
   ``dbus.set_default_main_loop(None)`` is rejected (requires a
   ``NativeMainLoop``), and binding a connection to a non-default GLib context
   is not exposed by dbus-python; pushing a thread-default ``GLib.MainContext``
   does not help either.

   The dual-antenna heap corruption therefore **still reproduces** with this
   module in place.  Under ``MALLOC_CHECK_=3`` it presents as a SIGSEGV in the
   loop thread while the enumerator is inside ``call_blocking`` constructing a
   ``DBusException`` from an error reply.  Fixing it requires the enumerator to
   live in a **separate process** (or the survey process to run no GLib loop at
   all).  See ``docs/mainloop_architecture.md`` → "Thread-safety
   constraint".

Note
----
``bleep.dbus.connection_pool`` looks like it does this but does not — its
``_create_connection()`` returns the singleton, so "pooled" connections are
aliases and ``PooledConnection.close()`` would close the process-wide bus.  It
is dormant (lazy ``__getattr__``; only ``scripts/dbus_diagnostic.py`` imports
it) and must not be used for isolation.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional

import dbus

__all__ = [
    "get_bus",
    "get_shared_bus",
    "uses_private_bus",
    "close_thread_bus",
    "thread_bus_count",
]

_LOCK = threading.RLock()
_THREAD_BUSES: Dict[int, dbus.Bus] = {}


def get_shared_bus() -> dbus.Bus:
    """Return the loop-attached shared system bus (signal matches live here)."""
    return dbus.SystemBus()


def _owns_shared_bus() -> bool:
    """True when the calling thread may use the shared connection directly.

    The main thread keeps the shared bus so existing flows are unchanged.  The
    loop thread is included because it *is* the connection's dispatcher.
    """
    current = threading.current_thread()
    if current is threading.main_thread():
        return True
    return current.name == "bleep-mainloop"


def uses_private_bus() -> bool:
    """True when :func:`get_bus` gives the calling thread a private connection.

    Objects built on a private bus are owned by the building thread; another
    thread (notably the loop thread inside a signal handler) must not issue
    blocking calls through them.
    """
    return not _owns_shared_bus()


def get_bus() -> dbus.Bus:
    """Return the bus this thread may safely make blocking calls on.

    Main / loop thread → the shared singleton.  Any other thread → a private
    connection created on first use and reused for that thread's lifetime.
    """
    if _owns_shared_bus():
        return dbus.SystemBus()

    ident = threading.get_ident()
    with _LOCK:
        bus = _THREAD_BUSES.get(ident)
        if bus is not None:
            return bus
        # private=True is what makes this a distinct connection; no mainloop is
        # attached on purpose (see module docstring).
        bus = dbus.SystemBus(private=True)
        _THREAD_BUSES[ident] = bus
        return bus


def close_thread_bus(ident: Optional[int] = None) -> bool:
    """Close and forget the private bus for *ident* (default: this thread).

    Worker threads should call this as they exit so the connection's socket is
    released rather than leaked for the life of the process.  Returns True when
    a connection was actually closed.
    """
    key = threading.get_ident() if ident is None else ident
    with _LOCK:
        bus = _THREAD_BUSES.pop(key, None)
    if bus is None:
        return False
    try:
        bus.close()
    except Exception:  # pragma: no cover - close is best-effort
        return False
    return True


def thread_bus_count() -> int:
    """Number of live private per-thread connections (diagnostics/tests)."""
    with _LOCK:
        return len(_THREAD_BUSES)
