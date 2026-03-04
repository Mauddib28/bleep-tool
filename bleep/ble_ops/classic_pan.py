"""Operations layer for Bluetooth Classic PAN (Personal Area Networking).

Wraps :mod:`bleep.dbuslayer.network` with logging, service detection,
and observation-database integration.

Supported PAN roles
-------------------
* ``nap`` – Network Access Point (internet sharing)
* ``panu`` – Personal Area Network User
* ``gn`` – Group Network
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None

from bleep.dbuslayer.network import NetworkClient, NetworkServer

from bleep.bt_ref.constants import (
    PAN_PANU_UUID_SHORT,
    PAN_NAP_UUID_SHORT,
    PAN_GN_UUID_SHORT,
    ADAPTER_NAME,
)

_PAN_SHORTS = {"0x1115", "0x1116", "0x1117", "1115", "1116", "1117"}


def detect_pan_service(service_map: Optional[Dict[str, int]]) -> bool:
    """Return True if the service map contains a PAN entry (PANU/NAP/GN)."""
    if not service_map:
        return False
    for key in service_map:
        low = key.lower()
        if any(s in low for s in _PAN_SHORTS) or "network" in low or "pan" in low:
            return True
    return False


# ---------------------------------------------------------------------------
# Client operations (Network1)
# ---------------------------------------------------------------------------

def connect(
    mac_address: str,
    role: str = "nap",
    *,
    adapter: str = ADAPTER_NAME,
) -> str:
    """Connect to a remote PAN device.

    Returns the local network interface name (e.g. ``bnep0``).
    """
    mac_address = mac_address.strip().upper()
    print_and_log(f"[PAN] Connecting to {mac_address} as {role}", LOG__GENERAL)
    client = NetworkClient(mac_address, adapter=adapter)
    iface = client.connect(role)
    print_and_log(f"[PAN] Connected – interface {iface}", LOG__GENERAL)

    if _obs:
        try:
            _obs.upsert_pan_access(mac_address, role, "connect", iface)
        except Exception:
            pass

    return iface


def disconnect(
    mac_address: str,
    *,
    adapter: str = ADAPTER_NAME,
) -> None:
    """Disconnect from a remote PAN device."""
    mac_address = mac_address.strip().upper()
    print_and_log(f"[PAN] Disconnecting from {mac_address}", LOG__GENERAL)
    client = NetworkClient(mac_address, adapter=adapter)
    client.disconnect()
    print_and_log(f"[PAN] Disconnected from {mac_address}", LOG__GENERAL)

    if _obs:
        try:
            _obs.upsert_pan_access(mac_address, "", "disconnect")
        except Exception:
            pass


def status(
    mac_address: str,
    *,
    adapter: str = ADAPTER_NAME,
) -> Dict[str, Any]:
    """Return the current Network1 property snapshot for a device."""
    mac_address = mac_address.strip().upper()
    client = NetworkClient(mac_address, adapter=adapter)
    return client.status()


# ---------------------------------------------------------------------------
# Server operations (NetworkServer1)
# ---------------------------------------------------------------------------

def register_server(
    role: str = "nap",
    bridge: str = "pan0",
    *,
    adapter: str = ADAPTER_NAME,
) -> None:
    """Register a PAN server so remote devices can connect."""
    print_and_log(f"[PAN] Registering server role={role} bridge={bridge}", LOG__GENERAL)
    server = NetworkServer(adapter=adapter)
    server.register(role, bridge)
    print_and_log(f"[PAN] Server registered (role={role}, bridge={bridge})", LOG__GENERAL)


def unregister_server(
    role: str = "nap",
    *,
    adapter: str = ADAPTER_NAME,
) -> None:
    """Unregister a previously registered PAN server."""
    print_and_log(f"[PAN] Unregistering server role={role}", LOG__GENERAL)
    server = NetworkServer(adapter=adapter)
    server.unregister(role)
    print_and_log(f"[PAN] Server unregistered (role={role})", LOG__GENERAL)
