"""Operations layer for SPP (Serial Port Profile) registration.

Wraps :mod:`bleep.dbuslayer.spp_profile` with logging and lifecycle
management.  The SPP profile is registered via BlueZ ``ProfileManager1``
and delivers incoming RFCOMM connections as Python sockets.
"""

from __future__ import annotations

import socket
from typing import Any, Callable, Dict, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.spp_profile import SppManager

_manager: Optional[SppManager] = None


def register(
    *,
    channel: Optional[int] = None,
    name: str = "BLEEP SPP",
    role: str = "server",
    on_connect: Optional[Callable] = None,
    on_disconnect: Optional[Callable] = None,
) -> None:
    """Register the SPP profile with BlueZ.

    *on_connect(device_path, sock, fd_properties)* is called when a
    remote device connects.  The *sock* is a ready-to-use Python socket
    for bidirectional data exchange.
    """
    global _manager
    if _manager is not None and _manager.registered:
        raise RuntimeError("SPP profile already registered")

    print_and_log(f"[SPP] Registering profile (role={role}, channel={channel or 'auto'})", LOG__GENERAL)
    _manager = SppManager(
        channel=channel,
        name=name,
        role=role,
        on_connect=on_connect,
        on_disconnect=on_disconnect,
    )
    _manager.register()


def unregister() -> None:
    """Unregister the SPP profile from BlueZ."""
    global _manager
    if _manager is None:
        print_and_log("[SPP] No profile registered", LOG__DEBUG)
        return
    _manager.unregister()
    _manager = None
    print_and_log("[SPP] Profile unregistered", LOG__GENERAL)


def status() -> Dict[str, Any]:
    """Return current SPP profile status."""
    if _manager is None:
        return {"registered": False}
    return _manager.status()


def is_registered() -> bool:
    return _manager is not None and _manager.registered
