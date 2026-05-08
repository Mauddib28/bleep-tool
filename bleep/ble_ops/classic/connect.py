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

    >>> from bleep.ble_ops.classic.connect import connect_and_enumerate__bluetooth__classic
    >>> dev, svc_map = connect_and_enumerate__bluetooth__classic("AA:BB:CC:DD:EE:FF")

Returned tuple:
    (device_wrapper, service_channel_map)

Where *service_channel_map* is ``{name_or_uuid: channel_int}``.
"""

from typing import TYPE_CHECKING, Tuple, Dict, Any, Optional, List

if TYPE_CHECKING:
    from bleep.modes.debug_state import DebugState
import time as _time
import dbus
import socket

from bleep.core import errors as _errors
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
from bleep.dbuslayer.device_classic import (
    system_dbus__bluez_device__classic as _ClassicDevice,
)
from bleep.ble_ops.classic.sdp import discover_services_sdp, build_svc_map

# optional observation DB
try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None
from bleep.dbuslayer.agent import ensure_default_pairing_agent  # type: ignore
from bleep.core.error_handling import controller_stall_mitigation

# GLib stop/restart helpers — imported lazily to avoid hard dependency on debug mode
_glib_helpers_loaded = False
_stop_glib: Any = None
_ensure_glib: Any = None

def _load_glib_helpers():
    global _glib_helpers_loaded, _stop_glib, _ensure_glib
    if _glib_helpers_loaded:
        return
    try:
        from bleep.modes.debug_state import stop_glib_mainloop, ensure_glib_mainloop
        _stop_glib = stop_glib_mainloop
        _ensure_glib = ensure_glib_mainloop
    except ImportError:
        pass
    _glib_helpers_loaded = True

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
    debug_state: Optional["DebugState"] = None,
) -> Tuple[_ClassicDevice, Dict[str, int]]:
    """Connect to a BR/EDR device and obtain an RFCOMM service->channel map.

    Parameters
    ----------
    target_bt_addr : str
        MAC address (case-insensitive).
    timeout_connect : int, optional
        Seconds to wait for BlueZ connection procedure.
    timeout_scan_attempts : int, optional
        Number of 5-second discovery cycles before giving up if the target is
        not initially visible.
    debug_state : DebugState, optional
        When called from the debug shell, pass the session state so the GLib
        MainLoop can be stopped/restarted for reliable agent dispatch during
        auto-pair (mirrors the ``pair --interactive`` pattern).

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

    print_and_log(f"[*] Scanning for {target_bt_addr}…", LOG__GENERAL)
    if not _target_visible(adapter, target_bt_addr, timeout_scan_attempts):
        raise _errors.DeviceNotFoundError(target_bt_addr)

    device = _ClassicDevice(target_bt_addr)

    print_and_log(f"[*] Connecting to {target_bt_addr}…", LOG__GENERAL)
    connected = device.connect(retry=5, wait_timeout=timeout_connect)
    if not connected:
        already_paired = False
        try:
            already_paired = device.is_paired()
        except Exception:
            pass
        if already_paired:
            print_and_log(
                "[*] Device paired but Device1.Connect() failed "
                "(no profile handler) — proceeding with SDP",
                LOG__GENERAL,
            )
        else:
            print_and_log("[*] Pairing required — invoking agent…", LOG__GENERAL)
            _do_auto_pair(device, target_bt_addr, timeout_connect, debug_state)

    print_and_log(f"[*] Running SDP discovery on {target_bt_addr}…", LOG__GENERAL)
    records = discover_services_sdp(target_bt_addr)
    svc_map = build_svc_map(records)
    svc_items = [
        {"uuid": v["uuid"], "channel": v["channel"], "name": v.get("name")}
        for v in svc_map.values()
        if v.get("channel") is not None
    ]

    rfcomm_count = sum(1 for v in svc_map.values() if v.get("channel") is not None)
    print_and_log(
        f"[+] Classic enumeration complete – {len(svc_map)} services ({rfcomm_count} with RFCOMM)",
        LOG__GENERAL,
    )

    try:
        device_type = device.get_device_type(scan_mode="pokey")
        if device_type:
            print_and_log(f"[*] Device type: {device_type}", LOG__GENERAL)
    except Exception as e:
        print_and_log(f"[*] Device type classification: {e}", LOG__DEBUG)

    if _obs:
        try:
            dev_info = device.get_device_info()
            upsert_kwargs = {
                "name": dev_info.get("name"),
                "rssi_last": dev_info.get("rssi"),
                "device_class": dev_info.get("device_class"),
                "device_type": dev_info.get("device_type") or "classic",
            }
            if dev_info.get("tx_power") is not None:
                upsert_kwargs["tx_power"] = int(dev_info["tx_power"])
            _obs.upsert_device(target_bt_addr, **upsert_kwargs)
            if svc_items:
                _obs.upsert_classic_services(target_bt_addr, svc_items)
        except Exception:
            pass
    return device, svc_map


def _do_auto_pair(
    device: _ClassicDevice,
    mac: str,
    timeout_connect: int,
    debug_state: Optional["DebugState"],
) -> None:
    """Auto-pair helper that uses the GLib stop/restart pattern when in debug mode.

    When *debug_state* is provided, mirrors the proven ``pair --interactive``
    pattern from ``debug_pairing._cmd_pair_single``:
    1. Stop background GLib MainLoop (free the default MainContext)
    2. Register a PairingAgent and call ``pair_device()`` (runs a temp loop)
    3. Restart background GLib MainLoop

    Without *debug_state*, falls back to the simple ``ensure_default_pairing_agent``
    + ``device.pair()`` path (adequate for CLI-mode where no background loop runs).
    """
    if debug_state is not None:
        _load_glib_helpers()
        if _stop_glib:
            _stop_glib(debug_state)

        try:
            from bleep.dbuslayer.agent import PairingAgent
            from bleep.dbuslayer.agent_io import create_io_handler
            from bleep.pairing import register_pair_agent, find_device_path
            import bleep.dbuslayer.agent as _agent_mod

            io_handler = create_io_handler("auto", default_pin="0000")
            register_pair_agent(io_handler, "KeyboardDisplay")

            agent = getattr(_agent_mod, "_DEFAULT_AGENT", None)
            if isinstance(agent, PairingAgent):
                device_path = find_device_path(mac)
                if device_path:
                    success = agent.pair_device(device_path, set_trusted=True, timeout=30)
                    if not success:
                        raise _errors.ConnectionError(mac, "pairing failed (agent)")
                else:
                    raise _errors.ConnectionError(mac, "device path not found for pairing")
            else:
                device.pair(timeout=30)
                device.set_trusted(True)
        except _errors.BLEEPError:
            raise
        except Exception as exc:
            raise _errors.ConnectionError(mac, "pairing failed") from exc
        finally:
            if _ensure_glib:
                _ensure_glib(debug_state)
    else:
        ensure_default_pairing_agent()
        try:
            device.pair(timeout=30)
            device.set_trusted(True)
        except Exception as exc:
            print_and_log("[-] Auto-pair failed", LOG__DEBUG)
            raise _errors.ConnectionError(mac, "pairing failed") from exc

    if not device.is_connected():
        print_and_log(f"[*] Re-connecting to {mac} after pairing…", LOG__GENERAL)
        if not device.connect(retry=3, wait_timeout=timeout_connect * 2):
            raise _errors.ConnectionError(mac, "connect failed after pairing")