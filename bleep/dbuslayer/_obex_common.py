"""Shared helpers for OBEX profile D-Bus layers.

Consolidates transfer-polling logic that was duplicated across
``obex_opp.py``, ``obex_map.py``, and ``obex_pbap.py``.
"""

from __future__ import annotations

import time
from typing import Any, Dict

import dbus

from bleep.bt_ref.constants import (
    OBEX_SERVICE as _OBEX_SERVICE,
    OBEX_TRANSFER_INTERFACE as _OBEX_TRANSFER_IFACE,
    DBUS_PROPERTIES,
)


def poll_obex_transfer(
    bus: dbus.Bus,
    transfer_path: str,
    timeout: int,
    *,
    label: str = "OBEX",
) -> Dict[str, Any]:
    """Block until the ``Transfer1`` at *transfer_path* reaches a terminal state.

    Returns a dict with ``status``, and optionally ``transferred``, ``size``,
    and ``filename`` keys on success.

    Raises ``RuntimeError`` on timeout or ``error`` status.
    """
    obj = bus.get_object(_OBEX_SERVICE, transfer_path)
    props = dbus.Interface(obj, DBUS_PROPERTIES)

    start = time.time()
    while True:
        status = str(props.Get(_OBEX_TRANSFER_IFACE, "Status")).lower()
        if status in ("complete", "error"):
            break
        if (time.time() - start) > timeout:
            raise RuntimeError(f"{label} transfer timed out")
        time.sleep(0.3)

    result: Dict[str, Any] = {"status": status}
    for prop in ("Transferred", "Size", "Filename"):
        try:
            val = props.Get(_OBEX_TRANSFER_IFACE, prop)
            key = prop.lower()
            result[key] = int(val) if prop != "Filename" else str(val)
        except Exception:
            pass

    if status != "complete":
        raise RuntimeError(f"{label} transfer failed (Status={status})")
    return result


def cancel_obex_transfer(bus: dbus.Bus, transfer_path: str) -> None:
    """Request cancellation of an in-progress ``Transfer1``."""
    obj = bus.get_object(_OBEX_SERVICE, transfer_path)
    transfer = dbus.Interface(obj, _OBEX_TRANSFER_IFACE)
    transfer.Cancel()


def unwrap_dbus(val: Any) -> Any:
    """Recursively unwrap D-Bus types to native Python types."""
    if isinstance(val, dbus.String):
        return str(val)
    if isinstance(val, (dbus.Int16, dbus.Int32, dbus.Int64,
                        dbus.UInt16, dbus.UInt32, dbus.UInt64, dbus.Byte)):
        return int(val)
    if isinstance(val, dbus.Boolean):
        return bool(val)
    if isinstance(val, dbus.Double):
        return float(val)
    if isinstance(val, dbus.Array):
        return [unwrap_dbus(item) for item in val]
    if isinstance(val, dbus.Dictionary):
        return {str(k): unwrap_dbus(v) for k, v in val.items()}
    return val
