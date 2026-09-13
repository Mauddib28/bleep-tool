"""In-process resource sampling for long survey runs.

Why in-process
--------------
The 2026-09-08 2h validation run (docs/todo_tracker.md B.22) was sampled by an
external shell loop that died after a single sample and reported nothing.  The
run itself was fine; the *measurement* was lost, and with it the answer to the
open memory question (docs/d-bus-reliability.md).  An external sampler has to guess the PID, races
process startup, and fails silently.

Sampling from inside the process removes all three failure modes and lets the
sample carry state no external observer can see — the census size and the
enumeration device-pool occupancy — which is what makes an RSS curve
interpretable rather than merely alarming.

The sampler is a daemon thread doing nothing but reading ``/proc/self`` and
appending a CSV row, so it adds no D-Bus traffic and is safe under
``--no-mainloop``.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional, Tuple

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__USER

__all__ = ["MetricsSampler", "sample_row", "CSV_HEADER"]

CSV_HEADER = (
    "ts,elapsed_s,rss_kb,vm_kb,threads,fds,devices,pool,rounds,phase,"
    "matches,sock_rx,sig_devs,bluez_objs,bluez_devs"
)


def _proc_self() -> dict:
    """RSS/VmSize/thread count from ``/proc/self/status``.  Never raises."""
    out = {"rss_kb": "", "vm_kb": "", "threads": ""}
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    out["rss_kb"] = line.split()[1]
                elif line.startswith("VmSize:"):
                    out["vm_kb"] = line.split()[1]
                elif line.startswith("Threads:"):
                    out["threads"] = line.split()[1]
    except Exception:  # pragma: no cover - /proc always present on Linux
        pass
    return out


def _fd_count() -> str:
    try:
        return str(len(os.listdir("/proc/self/fd")))
    except Exception:  # pragma: no cover - defensive
        return ""


def _match_count() -> str:
    """Signal matches registered on the shared bus.

    ``dbus-daemon`` caps a connection at 512 match rules and 128 outstanding
    replies (both defaults, unset in ``/usr/share/dbus-1/system.conf``).
    Exceeding either makes the daemon refuse the connection's traffic, which
    would present exactly as the collector wedge in d-bus-reliability.md: every call
    returning ``NoReply`` while bluetoothd itself is healthy, recovering the
    moment the process exits.  Counting the rules is how we tell that apart
    from a wedged daemon.
    """
    try:
        from bleep.dbuslayer.bus import get_shared_bus

        bus = get_shared_bus()
        total = 0
        by_path = getattr(bus, "_signal_recipients_by_object_path", None) or {}
        for by_iface in by_path.values():
            for recipients in (by_iface or {}).values():
                total += len(recipients)
        total += len(getattr(bus, "_signal_sender_matches", None) or {})
        return str(total)
    except Exception:
        return ""


def _socket_backlog() -> str:
    """Largest unread byte count across our socket fds — the D-Bus one in practice.

    dbus-python exposes no pending-call or dispatch-queue counter, so this is
    the honest proxy: with no main loop nothing dispatches inbound traffic, so
    a backlog that climbs is the signature of subscribing to signals we never
    consume — the leading candidate for the ~2.1 MB/round retention (d-bus-reliability.md).
    """
    try:
        import fcntl
        import struct
        import termios

        worst = 0
        for entry in os.listdir("/proc/self/fd"):
            try:
                if not os.readlink(f"/proc/self/fd/{entry}").startswith("socket:["):
                    continue
                packed = fcntl.ioctl(
                    int(entry), termios.FIONREAD, struct.pack("I", 0)
                )
            except (OSError, ValueError):
                continue
            worst = max(worst, struct.unpack("I", packed)[0])
        return str(worst)
    except Exception:
        return ""


def _bluez_objects() -> Tuple[str, str]:
    """Objects in BlueZ's most recent harvest reply: ``(total, dev_*)``.

    Recorded by the harvest itself (``manager.LAST_HARVEST``) so sampling costs
    no extra D-Bus traffic and cannot block on a wedged connection.
    """
    try:
        from bleep.dbuslayer.manager import LAST_HARVEST

        return str(LAST_HARVEST.get("objects", "")), str(
            LAST_HARVEST.get("devices", "")
        )
    except Exception:
        return "", ""


def _registry_devices() -> str:
    """Devices pinned by the signals registry — never evicted (todo_tracker B.19-B.23)."""
    try:
        from bleep.dbuslayer.manager import _signals_manager

        return str(len(getattr(_signals_manager, "_devices", None) or {}))
    except Exception:
        return ""


def sample_row(census: Any, started: float, state: Optional[Any] = None) -> str:
    """Build one CSV row.  Never raises — a sampling failure must not end a run."""
    proc = _proc_self()

    devices = ""
    try:
        devices = str(census.device_count)
    except Exception:
        pass

    pool = ""
    try:
        from bleep.dbuslayer.device_pool import enumerator_device_pool

        pool = str(len(enumerator_device_pool))
    except Exception:
        pass

    rounds = ""
    phase = ""
    if state is not None:
        rounds = str(getattr(state, "round_num", "") or "")
        phase = str(getattr(state, "phase", "") or "")

    return ",".join(
        [
            f"{time.time():.0f}",
            f"{time.monotonic() - started:.0f}",
            proc["rss_kb"],
            proc["vm_kb"],
            proc["threads"],
            _fd_count(),
            devices,
            pool,
            rounds,
            phase,
            _match_count(),
            _socket_backlog(),
            _registry_devices(),
            *_bluez_objects(),
        ]
    )


class _State:
    """Mutable round/phase carrier the survey loop updates as it goes."""

    __slots__ = ("round_num", "phase")

    def __init__(self) -> None:
        self.round_num = 0
        self.phase = ""


class MetricsSampler:
    """Append a resource sample to *path* every *interval* seconds.

    Use as a context manager.  Sampling errors are logged once at DEBUG and
    never propagate: losing a measurement is acceptable, losing a 2h run is not.
    """

    def __init__(self, path: str, interval: int, census: Any) -> None:
        self.path = path
        self.interval = max(1, int(interval))
        self._census = census
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = time.monotonic()
        self._samples = 0
        self.state = _State()

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> "MetricsSampler":
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write(CSV_HEADER + "\n")
        except OSError as exc:
            print_and_log(
                f"[survey] metrics disabled ({self.path}: {exc})", LOG__USER
            )
            return self
        self._thread = threading.Thread(
            target=self._run, name="bleep-metrics", daemon=True
        )
        self._thread.start()
        print_and_log(
            f"[survey] sampling resources every {self.interval}s to {self.path}",
            LOG__USER,
        )
        return self

    def stop(self) -> int:
        """Stop sampling, take a final sample, return total samples written."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self.interval + 2)
        self._write(sample_row(self._census, self._started, self.state))
        return self._samples

    def __enter__(self) -> "MetricsSampler":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()

    # -- internals ----------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            self._write(sample_row(self._census, self._started, self.state))
            self._stop.wait(self.interval)

    def _write(self, row: str) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(row + "\n")
            self._samples += 1
        except Exception as exc:  # pragma: no cover - defensive
            print_and_log(f"[survey] metrics write failed: {exc}", LOG__DEBUG)
