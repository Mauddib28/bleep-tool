"""Adapter sessions & registry for multi-antenna operation (D1.5).

An :class:`AdapterSession` binds a single BlueZ adapter (``hciN``) to a *role*
(collector vs. enumerator) and a *transport* (``le``/``bredr``/``both``).  It is
the unit that makes adding another antenna a one-liner: construct a session and
register it.  Collector sessions drive **non-blocking** discovery on the shared
main-loop (see :mod:`bleep.dbuslayer.loop_service`) and harvest only the devices
seen on *their* adapter (BlueZ ``GetManagedObjects`` is global, so results are
filtered by the ``/org/bluez/<adapter>/`` object-path prefix).

This module is intentionally thin: it composes the existing
``system_dbus__bluez_adapter`` / ``system_dbus__bluez_device_manager`` rather
than reimplementing discovery.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "ROLE_COLLECTOR",
    "ROLE_ENUMERATOR",
    "AdapterSession",
    "AdapterSessionRegistry",
    "session_registry",
]

ROLE_COLLECTOR = "collector"
ROLE_ENUMERATOR = "enumerator"


@dataclass
class AdapterSession:
    """Binds one ``hciN`` adapter to a role + transport for coordinated use."""

    adapter_name: str
    transport: str = "le"  # le | bredr | both
    role: str = ROLE_COLLECTOR
    _adapter: Any = field(default=None, repr=False, compare=False)

    # -- lazy BlueZ objects -------------------------------------------------
    @property
    def adapter(self) -> Any:
        if self._adapter is None:
            from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

            self._adapter = _Adapter(self.adapter_name)
        return self._adapter

    @property
    def manager(self) -> Any:
        return self.adapter.create_device_manager()

    @property
    def _path_prefix(self) -> str:
        return f"/org/bluez/{self.adapter_name}/"

    # -- non-blocking collection --------------------------------------------
    def begin(self, timeout: int = 60, *, dbus_timeout: Optional[float] = None) -> None:
        """Start non-blocking discovery on this adapter (shared-loop model).

        *dbus_timeout* bounds the D-Bus **reply** wait (not the scan window).
        Left ``None`` on the normal path; the stall re-arm supplies a short
        value so a wedged bluetoothd is detected in seconds rather than costing
        the dbus-python 25s default per attempt.
        """
        self.manager.begin_discovery(
            timeout=timeout, transport=self.transport, dbus_timeout=dbus_timeout
        )

    def harvest(self) -> Dict[str, Dict[str, Any]]:
        """Return ``{MAC: device_dict}`` for devices seen on **this** adapter.

        Uses the manager pre-stop / in-session snapshot (R1) so non-connectable
        beacons are retained. Filters by adapter object-path so concurrent
        sessions never double-count each other's sightings.
        """
        out: Dict[str, Dict[str, Any]] = {}
        manager = self.manager
        try:
            discovered = manager.snapshot_discovered_devices()
        except Exception:
            discovered = self.adapter.get_discovered_devices()
        for dev in discovered:
            path = dev.get("path") or ""
            if not path.startswith(self._path_prefix):
                continue
            addr = (dev.get("address") or "").upper()
            if addr:
                # fingerprint_rotated_in_round is attached by snapshot_discovered_devices
                out[addr] = dev
        return out

    def end(self) -> None:
        """Stop discovery started by :py:meth:`begin` (never raises)."""
        try:
            self.manager.end_discovery()
        except Exception:  # pragma: no cover - defensive
            pass

    def connect_device(
        self,
        address: str,
        address_type: Optional[str] = None,
        timeout: float = 15.0,
    ) -> bool:
        """Connect *address* on this adapter (enumerator path; see enumerator.py)."""
        from bleep.dbuslayer.enumerator import connect_on_session

        return connect_on_session(
            self, address, address_type=address_type, timeout=timeout
        )

    def pair_device(self, address: str, timeout: int = 30) -> bool:
        """Pair on this adapter's Device1.  Refuses collector role."""
        from bleep.dbuslayer.enumerator import pair_on_session

        return pair_on_session(self, address, timeout=timeout)

    def enumerate_device(self, address: str, mode: str = "passive", **kwargs):
        """GATT-enumerate *address* on this adapter via EnumerationController."""
        from bleep.dbuslayer.enumerator import enumerate_on_session

        return enumerate_on_session(self, address, mode=mode, **kwargs)

    def disconnect_device(self, address: str) -> None:
        """Best-effort disconnect of Device1 on this adapter."""
        from bleep.dbuslayer.enumerator import disconnect_on_session

        disconnect_on_session(self, address)


class AdapterSessionRegistry:
    """Thread-safe map of ``adapter_name -> AdapterSession``."""

    def __init__(self) -> None:
        self._sessions: Dict[str, AdapterSession] = {}
        self._lock = threading.RLock()

    def add(self, session: AdapterSession) -> AdapterSession:
        with self._lock:
            self._sessions[session.adapter_name] = session
        return session

    def get(self, adapter_name: str) -> Optional[AdapterSession]:
        with self._lock:
            return self._sessions.get(adapter_name)

    def remove(self, adapter_name: str) -> None:
        with self._lock:
            self._sessions.pop(adapter_name, None)

    def all(self) -> List[AdapterSession]:
        with self._lock:
            return list(self._sessions.values())

    def by_role(self, role: str) -> List[AdapterSession]:
        with self._lock:
            return [s for s in self._sessions.values() if s.role == role]

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


# Process-wide registry (optional convenience; orchestrators may also keep their
# own local registry instance).
session_registry = AdapterSessionRegistry()
