"""Enumerator-role operations for dual-antenna AdapterSession (Phase B).

Connect, pair, enumerate, and disconnect on a session whose role is
``ROLE_ENUMERATOR``.  Collector sessions refuse Pair() so a live discovery
radio is never bonded against.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from bleep.core.errors import BleepError
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL

__all__ = [
    "connect_on_session",
    "pair_on_session",
    "enumerate_on_session",
    "disconnect_on_session",
    "disconnect_connected_on_session",
]


def connect_on_session(
    session: Any,
    address: str,
    address_type: Optional[str] = None,
    timeout: float = 15.0,
) -> bool:
    """Create/connect Device1 on *session*'s adapter without touching collectors.

    Prefers ``Adapter1.ConnectDevice``.  Falls back to a short discovery on
    **this** adapter only when ConnectDevice is unavailable.
    """
    from bleep.dbuslayer.adapter import ConnectDeviceOutcome
    from bleep.dbuslayer.adapter_session import ROLE_COLLECTOR

    address = address.strip().upper()
    adapter = session.adapter
    outcome = adapter.connect_device_ex(
        address, address_type=address_type, timeout=timeout
    )
    if outcome is ConnectDeviceOutcome.CONNECTED:
        return True

    # B-2: only a genuinely unavailable ConnectDevice justifies the discovery
    # fallback.  A NoReply/timeout means the target did not answer on this
    # transport within the call budget; re-scanning for it on the same radio
    # just pays the cost twice.  NO_DEVICE means the call was accepted but no
    # Device1 materialised, which discovery will not fix either.
    if outcome is not ConnectDeviceOutcome.UNSUPPORTED:
        print_and_log(
            f"[*] ConnectDevice {outcome.value} for {address} on "
            f"{session.adapter_name}",
            LOG__DEBUG,
        )
        return False

    print_and_log(
        f"[*] ConnectDevice unavailable on {session.adapter_name}; "
        "short enumerator-local discovery fallback",
        LOG__DEBUG,
    )
    if session.role == ROLE_COLLECTOR:
        print_and_log(
            "[!] Refusing discovery fallback on a collector session "
            "(would interrupt live listening)",
            LOG__GENERAL,
        )
        return False
    from bleep.dbuslayer.loop_service import loop_service
    from bleep.pairing import find_device_path

    mgr = None
    held_loop = False
    try:
        mgr = session.manager
        transport = session.transport if session.transport != "both" else "le"
        if not loop_service.is_running():
            loop_service.acquire()
            held_loop = True
        mgr.begin_discovery(timeout=max(1, int(timeout)), transport=transport)
        deadline = time.monotonic() + max(1.0, float(timeout))
        while time.monotonic() < deadline:
            if find_device_path(address, adapter=session.adapter_name):
                break
            time.sleep(0.2)
    except Exception as exc:
        print_and_log(
            f"[!] Enumerator discovery fallback failed: {exc}", LOG__DEBUG
        )
        return False
    finally:
        if mgr is not None:
            try:
                mgr.end_discovery()
            except Exception:
                pass
        if held_loop:
            loop_service.release()

    return find_device_path(address, adapter=session.adapter_name) is not None


def pair_on_session(session: Any, address: str, timeout: int = 30) -> bool:
    """Pair on this adapter's Device1 only.  Refuses collector sessions."""
    from bleep.dbuslayer.adapter_session import ROLE_COLLECTOR
    from bleep.dbuslayer.device_le import (
        system_dbus__bluez_device__low_energy as _LEDevice,
    )
    from bleep.pairing import find_device_path

    if session.role == ROLE_COLLECTOR:
        raise BleepError(
            "Pair() refused on collector session; pair on the enumerator radio"
        )
    address = address.strip().upper()
    path = find_device_path(address, adapter=session.adapter_name)
    if path is None or not path.startswith(session._path_prefix):
        raise BleepError(
            f"No Device1 for {address} on enumerator {session.adapter_name}"
        )
    device = _LEDevice(address, adapter_name=session.adapter_name)
    return bool(device.Pair(timeout=timeout))


def enumerate_on_session(
    session: Any,
    address: str,
    mode: str = "passive",
    *,
    skip_scan: bool = True,
    **kwargs,
) -> Any:
    """Run EnumerationController on this session's adapter."""
    from bleep.ble_ops.le.enum_controller import EnumerationController

    ctrl = EnumerationController(
        address, adapter_name=session.adapter_name, skip_scan=skip_scan
    )
    return ctrl.enumerate(mode=mode, **kwargs)


def disconnect_on_session(session: Any, address: str) -> None:
    """Best-effort disconnect of Device1 on this adapter (never raises)."""
    try:
        from bleep.dbuslayer.device_le import (
            system_dbus__bluez_device__low_energy as _LEDevice,
        )

        device = _LEDevice(address.strip().upper(), adapter_name=session.adapter_name)
        device.disconnect()
    except Exception as exc:
        print_and_log(
            f"[*] Enumerator disconnect {address} on {session.adapter_name}: {exc}",
            LOG__DEBUG,
        )


def disconnect_connected_on_session(session: Any) -> int:
    """Disconnect every still-Connected Device1 under *session*'s adapter.

    Survey ``finally`` uses this so a leftover ACL does not make the next
    ``enum-scan --adapter hciN`` skip-connect a stale link. Never raises.
    """
    from bleep.bt_ref.constants import DEVICE_INTERFACE

    n = 0
    prefix = f"/org/bluez/{session.adapter_name}/"
    try:
        managed = session.adapter.get_managed_objects() or {}
    except Exception as exc:
        print_and_log(
            f"[*] Enumerator Connected sweep {session.adapter_name}: {exc}",
            LOG__DEBUG,
        )
        return 0
    for path, ifaces in managed.items():
        if not str(path).startswith(prefix):
            continue
        dev = ifaces.get(DEVICE_INTERFACE) or {}
        if not bool(dev.get("Connected")):
            continue
        addr = str(dev.get("Address", "")).upper()
        if not addr:
            continue
        disconnect_on_session(session, addr)
        n += 1
    if n:
        print_and_log(
            f"[*] Enumerator {session.adapter_name}: disconnected {n} leftover Device1(s)",
            LOG__GENERAL,
        )
    return n
