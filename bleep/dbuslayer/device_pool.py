"""Bounded pool of live ``_LEDevice`` objects for the enumerator.

Why
---
``system_dbus__bluez_device__low_energy.__init__`` registers itself with the
global signals manager, but ``signals.unregister_device()`` had **no callers**
anywhere in the tree.  Every device object ever built therefore stayed pinned
in ``signals._devices`` along with its D-Bus proxies and its entire resolved
GATT tree, and ``manager._devices`` never evicts either.  A long survey
accumulated device objects until the process died or the run ended — see
``docs/d-bus-reliability.md``, where a 2h run peaked at 206 MB.

This pool bounds how many enumeration-created device objects may be alive at
once.  When the cap is exceeded the least-recently-used entry is
:meth:`~bleep.dbuslayer.device_le.system_dbus__bluez_device__low_energy.release`\\ d
— unregistered from signal routing, proxies and GATT caches dropped — which
makes it collectable.

Scope
-----
Only devices built by the **enumeration** path are tracked (hooked at the one
construction site in :func:`bleep.ble_ops.le.connect.connect_and_enumerate__bluetooth__low_energy`).
Devices owned by :class:`~bleep.dbuslayer.manager.system_dbus__bluez_device_manager`
are deliberately **not** tracked: the collector keeps them in its own
``_devices`` map and would hand out torn-down objects if we released them
underneath it.  This mirrors the containment rule applied to the 10s
``ConnectDevice`` bound (docs/todo_tracker.md B.19-B.23) — bound the enumerator, never the shared
collector paths.

Note
----
Capping resources does **not** fix the heap corruption seen with a live GLib
main loop; that is a data race (see mainloop_architecture.md).  It bounds the blast radius and the
long-run footprint, which is what it is for.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Any, Optional, Tuple

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__USER

__all__ = [
    "LEDevicePool",
    "enumerator_device_pool",
    "DEFAULT_CAPACITY",
    "UNLIMITED",
    "capacity_from_env",
    "apply_capacity",
]

#: Maximum enumeration device objects alive at once.
DEFAULT_CAPACITY = 10

#: Capacity value disabling eviction entirely (diagnostic A/B).
UNLIMITED = 0

#: Tunes the cap for entry points without a CLI flag (enum-scan, explore,
#: gatt-enum, aoi, debug shell).  Same precedent as ``BLEEP_NO_MAINLOOP``.
CAPACITY_ENV_VAR = "BLEEP_MAX_ENUM_DEVICES"


def capacity_from_env(default: int = DEFAULT_CAPACITY) -> int:
    """Resolve the pool cap from :data:`CAPACITY_ENV_VAR`, else *default*.

    A malformed or negative value warns and falls back rather than raising —
    an env typo must not abort a long survey.
    """
    raw = os.environ.get(CAPACITY_ENV_VAR, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print_and_log(
            f"[!] {CAPACITY_ENV_VAR}={raw!r} is not an integer; "
            f"using {default}",
            LOG__USER,
        )
        return default
    if value < 0:
        print_and_log(
            f"[!] {CAPACITY_ENV_VAR}={value} is negative; using {default}",
            LOG__USER,
        )
        return default
    return value


class LEDevicePool:
    """LRU-bounded set of live device objects, releasing what it evicts.

    ``capacity=UNLIMITED`` (0) tracks without ever evicting, which exists to
    A/B the cap itself against a suspected fault.
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        if capacity < 0:
            raise ValueError("capacity must be >= 0 (0 = unlimited)")
        self._capacity = capacity
        self._lock = threading.RLock()
        # path -> device, ordered oldest-first.
        self._devices: "OrderedDict[str, Any]" = OrderedDict()

    # -- configuration ------------------------------------------------------
    @property
    def capacity(self) -> int:
        return self._capacity

    def set_capacity(self, capacity: int) -> None:
        """Change the cap, evicting immediately if the pool now overflows."""
        if capacity < 0:
            raise ValueError("capacity must be >= 0 (0 = unlimited)")
        with self._lock:
            self._capacity = capacity
            self._evict_locked()

    # -- tracking -----------------------------------------------------------
    def track(self, device: Any) -> None:
        """Register *device* as most-recently-used, evicting the oldest if full.

        A device already present is moved to the most-recent end rather than
        duplicated, so re-enumerating the same address does not evict it.
        """
        if device is None:
            return
        key = getattr(device, "_device_path", None)
        if not key:
            return
        with self._lock:
            if key in self._devices:
                self._devices.move_to_end(key)
                self._devices[key] = device
            else:
                self._devices[key] = device
            self._evict_locked()

    def release(self, device: Any) -> bool:
        """Release and forget *device*.  Returns True when it was tracked."""
        key = getattr(device, "_device_path", None)
        if not key:
            return False
        with self._lock:
            tracked = self._devices.pop(key, None)
        if tracked is None:
            return False
        self._release_one(tracked)
        return True

    def release_all(self) -> int:
        """Release every tracked device.  Returns how many were released."""
        with self._lock:
            devices = list(self._devices.values())
            self._devices.clear()
        for dev in devices:
            self._release_one(dev)
        return len(devices)

    # -- introspection ------------------------------------------------------
    def __len__(self) -> int:
        with self._lock:
            return len(self._devices)

    def addresses(self) -> list:
        """MACs of the currently tracked devices, oldest first (diagnostics)."""
        with self._lock:
            return [
                getattr(d, "mac_address", None) for d in self._devices.values()
            ]

    # -- internals ----------------------------------------------------------
    def _evict_locked(self) -> None:
        """Drop oldest entries until within capacity.  Caller holds the lock."""
        if self._capacity == UNLIMITED:
            return
        victims = []
        while len(self._devices) > self._capacity:
            _key, victim = self._devices.popitem(last=False)
            victims.append(victim)
        for victim in victims:
            self._release_one(victim)

    @staticmethod
    def _release_one(device: Any) -> None:
        mac = getattr(device, "mac_address", "?")
        try:
            device.release()
        except Exception as exc:  # pragma: no cover - best-effort teardown
            print_and_log(
                f"[!] Device pool: release {mac} failed: {exc}", LOG__DEBUG
            )
            return
        print_and_log(f"[*] Device pool: released {mac}", LOG__DEBUG)


#: Process-wide pool for the enumeration path.  Honours the env var at import
#: so entry points without a CLI flag are tunable too; ``survey`` overrides it
#: via ``--max-enum-devices``.
enumerator_device_pool = LEDevicePool(capacity_from_env())


def track_enumeration_device(device: Any) -> None:
    """Convenience hook used by the enumeration connect path."""
    enumerator_device_pool.track(device)


def apply_capacity(value: Optional[int]) -> Tuple[bool, Optional[str]]:
    """Validate and apply a requested ``--max-enum-devices`` capacity.

    Every entry point that accepts the flag routes through here so the
    validation, the unlimited warning and the confirmation cannot drift apart —
    they already had, the CLI warning that ``0`` grows without bound never
    reaching the debug shell.

    Returns ``(ok, message)``.  *message* is a fully prefixed operator-facing
    line, or ``None`` when there is nothing to say (``value is None`` leaves the
    current capacity untouched).
    """
    if value is None:
        return True, None
    if value < 0:
        return False, "[-] --max-enum-devices must be >= 0 (0 = unlimited)"

    enumerator_device_pool.set_capacity(value)
    if value == UNLIMITED:
        return True, (
            "[!] --max-enum-devices 0: enumeration device objects are "
            "UNLIMITED. Long runs will grow without bound."
        )
    return True, f"[*] Enumeration device pool capacity set to {value}"
