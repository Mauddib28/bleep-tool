from __future__ import annotations
"""bleep.ble_ops.classic_connect – Connect & enumerate Bluetooth Classic devices.

Design philosophy mirrors the BLE helper in ``bleep.ble_ops.connect`` but keeps
the code minimal by re-using:

• `dbuslayer.device_classic.system_dbus__bluez_device__classic` for the actual
  D-Bus calls (pair / connect / property helpers).
• `bleep.ble_ops.classic_sdp.discover_services_sdp` for deep service discovery
  (full SDP records → RFCOMM channel map).

The public contract intentionally mimics the BLE variant so higher-level code
or tests can simply switch the function name:

    >>> from bleep.ble_ops.classic_connect import connect_and_enumerate__bluetooth__classic
    >>> dev, svc_map = connect_and_enumerate__bluetooth__classic("AA:BB:CC:DD:EE:FF")

Returned tuple:
    (device_wrapper, service_channel_map)

Where *service_channel_map* is ``{name_or_uuid: channel_int}``.
"""

from typing import Tuple, Dict, Any, Optional, List
import time as _time
import dbus
import socket

from bleep.core import errors as _errors
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
from bleep.dbuslayer.device_classic import (
    system_dbus__bluez_device__classic as _ClassicDevice,
)
from bleep.ble_ops.classic_sdp import discover_services_sdp

# optional observation DB
try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None
from bleep.dbuslayer.agent import ensure_default_pairing_agent  # type: ignore
from bleep.core.error_handling import controller_stall_mitigation

# ---------------------------------------------------------------------------
# bc-16 – generic RFCOMM connector
# ---------------------------------------------------------------------------


def classic_rfccomm_open(mac_address: str, channel: int, *, timeout: float = 8.0) -> socket.socket:
    """Open an RFCOMM socket to *mac_address* on *channel*.

    Returns a connected ``socket.socket`` instance which the caller is
    responsible for closing.  Raises *OSError* on failure.  This helper keeps
    the rest of BLEEP free from raw socket logic and centralises logging.
    """

    from bleep.core.log import print_and_log, LOG__DEBUG

    mac_address = mac_address.strip().upper()
    print_and_log(
        f"[classic_rfccomm_open] Connecting RFCOMM → {mac_address}:{channel}", LOG__DEBUG
    )

    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(timeout)
    try:
        sock.connect((mac_address, channel))
        print_and_log("[classic_rfccomm_open] Connected", LOG__DEBUG)
        return sock
    except OSError as exc:
        print_and_log(
            f"[classic_rfccomm_open] connect failed: {exc}", LOG__DEBUG
        )
        sock.close()
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target_visible(adapter: _Adapter, mac: str, attempts: int = 3) -> bool:
    """Run BR/EDR discovery until *mac* becomes visible or *attempts* exhausted."""
    # BlueZ discovery filter to only look for BR/EDR transports → faster.
    try:
        adapter.set_discovery_filter({"Transport": "bredr"})
    except Exception:
        pass  # ignore unsupported method

    for i in range(1, attempts + 1):
        print_and_log(
            f"[*] Classic scan attempt {i}/{attempts} – searching for {mac}",
            LOG__DEBUG,
        )
        adapter.run_scan__timed(duration=5)
        devs = adapter.get_discovered_devices()
        if any(d["address"].upper() == mac for d in devs):
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def connect_and_enumerate__bluetooth__classic(
    target_bt_addr: str,
    *,
    timeout_connect: int = 10,
    timeout_scan_attempts: int = 3,
) -> Tuple[_ClassicDevice, Dict[str, int]]:
    """Connect to a BR/EDR device and obtain an RFCOMM service→channel map.

    Parameters
    ----------
    target_bt_addr : str
        MAC address (case-insensitive).
    timeout_connect : int, optional
        Seconds to wait for BlueZ connection procedure.
    timeout_scan_attempts : int, optional
        Number of 5-second discovery cycles before giving up if the target is
        not initially visible.

    Returns
    -------
    tuple(device, service_channel_map)
        *service_channel_map* keys are the service ``name`` if present else the
        UUID string; values are integers (RFCOMM channel numbers).
    """

    target_bt_addr = target_bt_addr.strip().upper()

    adapter = _Adapter()
    if not adapter.is_ready():
        raise _errors.NotReadyError()

    if not _target_visible(adapter, target_bt_addr, timeout_scan_attempts):
        raise _errors.DeviceNotFoundError(target_bt_addr)

    # Instantiate wrapper (does not connect yet)
    device = _ClassicDevice(target_bt_addr)

    # Attempt connect; if it fails due to Authentication/Authorization try pair+trust once.
    connected = device.connect(retry=5, wait_timeout=timeout_connect)
    if not connected:
        print_and_log("[*] Initial connect timed out – attempting auto-pair", LOG__GENERAL)
        ensure_default_pairing_agent()
        try:
            device.pair(timeout=30)
            device.set_trusted(True)
        except Exception as exc:
            print_and_log("[-] Auto-pair failed", LOG__DEBUG)
            raise _errors.ConnectionError(target_bt_addr, "pairing failed") from exc

        if not device.connect(retry=3, wait_timeout=timeout_connect * 2):
            raise _errors.ConnectionError(target_bt_addr, "connect failed after pairing")

    # Enumerate services via sdptool
    records = discover_services_sdp(target_bt_addr)
    svc_map: Dict[str, int] = {}
    svc_items = []
    for rec in records:
        if rec["channel"] is None:
            continue  # skip services without RFCOMM
        key = rec["name"] or rec["uuid"] or f"channel_{rec['channel']}"
        svc_map[key] = rec["channel"]
        svc_items.append({"uuid": rec["uuid"], "channel": rec["channel"], "name": rec.get("name")})

    print_and_log(
        f"[+] Classic enumeration complete – found {len(svc_map)} RFCOMM services",
        LOG__GENERAL,
    )

    # Perform device type classification with pokey mode
    # (classic_connect performs SDP enumeration, similar to pokey mode thoroughness)
    try:
        device_type = device.get_device_type(scan_mode="pokey")
        if device_type:
            print_and_log(f"[*] Device type: {device_type}", LOG__GENERAL)
    except Exception as e:
        print_and_log(f"[*] Device type classification: {e}", LOG__DEBUG)

    if _obs and svc_items:
        try:
            _obs.upsert_classic_services(target_bt_addr, svc_items)  # type: ignore[attr-defined]
        except Exception:
            pass
    return device, svc_map 