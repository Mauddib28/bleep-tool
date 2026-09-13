from __future__ import annotations

"""bleep.ble_ops.connect – native connection + enumeration helpers.

This module finally replaces the *monolithic* `connect_and_enumerate__bluetooth__low_energy`
function that lived in several legacy files.  It uses the refactored
`bleep.dbuslayer` stack exclusively and therefore eliminates the last runtime
requirement for importing the historical `dbus__bleep.py` source.

A minimal subset of the original public contract is preserved so higher-level
modules (and tests) can switch over without modification:

    >>> from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy
    >>> dev, mapping, landmine_map, perm_map = connect_and_enumerate__bluetooth__low_energy("AA:BB:CC:DD:EE:FF")

Return types are *compatible* – the mapping dictionaries mirror the field
names produced by the monolith.  Permission / landmine maps are currently
simple aliases of the characteristic Flags set; these will be refined in a
later pass when fine-grained ATT permission inspection is added.
"""

import random as _random
import threading as _threading
import time as _time
from typing import Tuple, Dict, List, Optional, Callable, Any

import dbus

from bleep.core import errors as _errors
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.device_le import (
    system_dbus__bluez_device__low_energy as _LEDevice,
)
from bleep.core.error_handling import controller_stall_mitigation
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
from bleep.dbuslayer.device_pool import (
    track_enumeration_device as _track_enumeration_device,
)
from bleep.ble_ops.le.reconnect import ReconnectionMonitor, reconnect_check

# B-1: reuse one adapter per ``hciN`` across calls.
#
# ``create_device_manager()`` already memoises its ``_DeviceManager`` on the
# adapter instance, but this module used to build a fresh ``_Adapter`` on every
# call, which defeated that cache.  Each rebuilt manager runs
# ``update_devices()`` -> ``_create_device()`` for *every* device BlueZ exposes,
# and each ``_LEDevice.__init__`` issues two ``bus.get_object`` calls plus a
# signal registration.  Under the survey enumerator that was O(devices) proxy
# churn per enumerated target (102k+ "Device object created" log lines), and it
# is where the 2026-09-05 glibc heap abort surfaced.
#
# The cache records the class it built with so monkeypatched ``_Adapter``
# replacements in tests are honoured instead of returning a stale real adapter.
_ADAPTER_CACHE: Dict[Optional[str], tuple] = {}
_ADAPTER_CACHE_LOCK = _threading.Lock()


def _get_cached_adapter(adapter_name: Optional[str] = None):
    """Return a reused adapter instance for *adapter_name* (None = default)."""
    with _ADAPTER_CACHE_LOCK:
        cached = _ADAPTER_CACHE.get(adapter_name)
        if cached is not None and cached[0] is _Adapter:
            return cached[1]
        instance = _Adapter(adapter_name) if adapter_name else _Adapter()
        _ADAPTER_CACHE[adapter_name] = (_Adapter, instance)
        return instance


def _reset_adapter_cache() -> None:
    """Drop all cached adapters (test hook / adapter hot-plug recovery)."""
    with _ADAPTER_CACHE_LOCK:
        _ADAPTER_CACHE.clear()

# Public export list -----------------------------------------------------------------------------
__all__ = [
    "connect_and_enumerate__bluetooth__low_energy",
    "connect_with_monitoring",
]


# Helper -----------------------------------------------------------------------------------------

def _wait_for_services(device: _LEDevice, timeout: int = 15) -> bool:
    """Block until *ServicesResolved* is *True* or *timeout* seconds elapsed."""
    start = _time.monotonic()
    while _time.monotonic() - start < timeout:
        try:
            if device.is_services_resolved():
                return True
        except _errors.BLEEPError:
            # Device may disconnect briefly → retry until timeout
            pass
        _time.sleep(0.25)
    return False


def _log_disconnect_reason(device_path: str) -> None:
    """Print the BlueZ disconnect reason for *device_path* if captured (BZ-8f)."""
    try:
        from bleep.core.device_management import _get_global_signals
        info = _get_global_signals().get_disconnect_reason(device_path)
        if not info:
            from bleep.dbuslayer.device_le import _signals_manager
            if _signals_manager is not None:
                info = _signals_manager.get_disconnect_reason(device_path)
        if info:
            label = info.get("human") or info.get("reason", "Unknown")
            msg = f"[*] Disconnect reason: {label}"
            if info.get("message"):
                msg += f" ({info['reason']} — {info['message']})"
            print_and_log(msg, LOG__GENERAL)
    except Exception:
        pass


def _emit_audio_stack_hint() -> None:
    """Print an actionable hint when profile-unavailable may be caused by
    a missing Bluetooth audio stack on the host."""
    try:
        from bleep.core.preflight import run_preflight_checks
        report = run_preflight_checks()
        if not report.has_bluetooth_audio_stack:
            print_and_log(
                "[!] Hint: No Bluetooth audio profile handlers detected on this host.\n"
                "    Install 'bluez-alsa-utils' (sudo apt-get install bluez-alsa-utils)\n"
                "    or ensure PulseAudio/PipeWire is running with Bluetooth support.\n"
                "    Run 'bleep --check-env' for details.",
                LOG__GENERAL,
            )
    except Exception:
        pass


# Public API -------------------------------------------------------------------------------------

def connect_and_enumerate__bluetooth__low_energy(
    target_bt_addr: str,
    landmine_mapping: Dict[str, List[str]] | None = None,
    security_mapping: Dict[str, List[str]] | None = None,
    *,
    timeout_connect: int = 10,
    timeout_services: int = 15,
    scan_attempts: int = 3,
    scan_timeout: int = 5,
    connect_retries: int = 5,
    connect_wait_timeout: float | None = None,
    transport: str = "auto",
    max_attempts: int = 1,
    backoff_base: float = 0.5,
    backoff_max: float = 30.0,
    backoff_jitter: float = 0.5,
    enable_monitoring: bool = False,
    deep_enumeration: bool = False,
    reconnect_callback: Optional[Callable[[bool, str], None]] = None,
    skip_pair_fallback: bool = False,
    adapter_name: str | None = None,
    skip_scan: bool = False,
):
    """Connect to *target_bt_addr* and enumerate its GATT database.

    Parameters
    ----------
    target_bt_addr : str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF").  Case-insensitive.
    landmine_mapping / security_mapping : dict | None
        Back-compat parameters kept so callers do not break.  Ignored –
        the function *returns* freshly generated maps.
    timeout_connect : int
        **Deprecated** – kept for backward compatibility.  When
        *connect_wait_timeout* is ``None`` (default) this value is used as
        the ``wait_timeout`` passed to ``device.connect()``.  Prefer
        *connect_wait_timeout* for new callers.
    timeout_services : int
        Seconds before aborting service resolution.
    scan_attempts : int
        Number of discovery-loop iterations before giving up (default 3).
    scan_timeout : int
        Per-attempt discovery timeout in seconds (default 5).
    connect_retries : int
        Passed to ``device.connect(retry=...)`` (default 5).
    connect_wait_timeout : float | None
        Passed to ``device.connect(wait_timeout=...)``.  When ``None``
        falls back to *timeout_connect* for backward compatibility.
    transport : str
        BlueZ discovery filter – ``"auto"`` (default), ``"le"``, or
        ``"bredr"``.  Applied via ``SetDiscoveryFilter`` before scanning.
    max_attempts : int
        Outer retry loop wrapping the entire connect + service-resolve
        cycle.  Default 1 (single attempt – legacy behaviour).
    backoff_base / backoff_max / backoff_jitter : float
        Exponential-backoff parameters for the outer retry loop:
        ``delay = min(base * 2**attempt + uniform(0, jitter), max)``.
    enable_monitoring : bool
        Start a background reconnection monitor thread.
    deep_enumeration : bool
        Perform deep GATT enumeration (extra descriptor reads).
    reconnect_callback : callable | None
        Called ``(success: bool, message: str)`` on reconnection events.
    skip_pair_fallback : bool
        If True, do not attempt automatic pairing on auth errors.
    adapter_name : str | None
        BlueZ controller to use (e.g. ``"hci1"``); ``None`` keeps the default
        (``ADAPTER_NAME``). Threaded from ``enum-scan --adapter`` (F5b).
        The Device1 object is constructed on this same adapter (Phase A).
    skip_scan : bool
        If True, skip PRE-FLIGHT discovery (the target is already a Device1 on
        this adapter, e.g. after ``Adapter1.ConnectDevice``). Default False.

    Returns
    -------
    tuple
        *(device, mapping, landmine_map, perm_map)*
    """

    # Resolve deprecated timeout_connect → connect_wait_timeout alias.
    if connect_wait_timeout is None:
        connect_wait_timeout = float(timeout_connect)

    print_and_log(f"[*] connect_and_enumerate::target = {target_bt_addr}", LOG__DEBUG)

    target_bt_addr = target_bt_addr.strip().upper()

    # ------------------------------------------------------------------
    # PRE-FLIGHT 0 – ensure adapter exists & powered
    # ------------------------------------------------------------------
    _adapter = _get_cached_adapter(adapter_name)
    if not _adapter.is_ready():
        raise _errors.NotReadyError()

    _mgr = _adapter.create_device_manager()
    resolved_adapter = adapter_name or getattr(_adapter, "adapter_name", None)

    # ------------------------------------------------------------------
    # PRE-FLIGHT 1 – passive scan until the target becomes visible
    # Skipped when the caller already created Device1 on this adapter
    # (enumerator ConnectDevice path).
    # ------------------------------------------------------------------
    def _target_visible() -> bool:
        return any(d.mac_address.upper() == target_bt_addr for d in _mgr.devices())

    if not skip_scan:
        _scan_count = 0
        while _scan_count < scan_attempts and not _target_visible():
            _scan_count += 1
            print_and_log(
                f"[*] Scan attempt {_scan_count}/{scan_attempts} – searching for {target_bt_addr}",
                LOG__DEBUG,
            )
            try:
                _mgr.start_discovery(timeout=scan_timeout, transport=transport.lower())
                _mgr.run()
            except _errors.NotReadyError:
                raise

        if not _target_visible():
            raise _errors.DeviceNotFoundError(target_bt_addr)

    try:
        device = (
            _LEDevice(target_bt_addr, adapter_name=resolved_adapter)
            if resolved_adapter
            else _LEDevice(target_bt_addr)
        )
    except Exception as exc:
        if skip_scan:
            raise _errors.DeviceNotFoundError(target_bt_addr) from exc
        raise

    # Bound how many enumeration device objects stay alive; the oldest beyond
    # the cap is released (signal registration + proxies + GATT caches dropped).
    # See bleep.dbuslayer.device_pool for why this is needed and why it is
    # scoped to the enumeration path only.
    _track_enumeration_device(device)

    # ------------------------------------------------------------------
    # CONNECT + SERVICE-RESOLVE (with optional outer retry loop)
    # ------------------------------------------------------------------
    attempt = 0
    while True:
        try:
            # ----------------------------------------------------------
            # 1. Connect (with retry + pair-fallback + stall mitigation)
            # ----------------------------------------------------------
            try:
                if not device.connect(retry=connect_retries, wait_timeout=connect_wait_timeout):
                    raise _errors.ConnectionError(target_bt_addr, "connect failed")
            except (_errors.NotAuthorizedError, _errors.PermissionError):
                if skip_pair_fallback:
                    print_and_log(
                        "[*] Connection requires pairing – skip_pair_fallback is set, re-raising",
                        LOG__GENERAL,
                    )
                    raise
                print_and_log("[*] Connection requires pairing – attempting explicit pair", LOG__GENERAL)
                try:
                    device.pair(timeout=30)
                    device.set_trusted(True)
                    if not device.connect(retry=3):
                        raise _errors.ConnectionError(target_bt_addr, "connect failed after pairing")
                except dbus.exceptions.DBusException as exc:
                    raise _errors.map_dbus_error(exc) from exc
            except dbus.exceptions.DBusException as exc:
                _inner_name = exc.get_dbus_name() or ""
                if max_attempts > 1 and (
                    "InProgress" in _inner_name or "Failed" in _inner_name
                ):
                    raise  # let the outer retry handler deal with transient states
                if _inner_name == "org.freedesktop.DBus.Error.NoReply":
                    print_and_log("[!] Controller appears stalled (NoReply)", LOG__GENERAL)
                    controller_stall_mitigation(target_bt_addr)
                    try:
                        if device.connect(retry=3):
                            print_and_log("[+] Recovered after stall workaround", LOG__GENERAL)
                        else:
                            raise _errors.ConnectionError(
                                target_bt_addr, "connect failed after stall workaround",
                            )
                    except Exception:
                        raise _errors.map_dbus_error(exc) from exc
                else:
                    _exc_msg = (exc.get_dbus_message() or str(exc)).lower()
                    if "profile" in _exc_msg and "unavailable" in _exc_msg:
                        _emit_audio_stack_hint()
                    raise _errors.map_dbus_error(exc) from exc

            # ----------------------------------------------------------
            # 2. Wait for service resolution
            # ----------------------------------------------------------
            if not _wait_for_services(device, timeout_services):
                _log_disconnect_reason(device._device_path)
                raise _errors.ServicesNotResolvedError(target_bt_addr)

            break  # success – exit retry loop

        except dbus.exceptions.DBusException as outer_exc:
            _err_name = outer_exc.get_dbus_name() or ""
            if "InProgress" in _err_name or "Failed" in _err_name:
                # Transient BlueZ state – don't count toward max_attempts.
                _time.sleep(1)
                continue
            attempt += 1
            if attempt < max_attempts:
                _delay = min(
                    backoff_base * (2 ** (attempt - 1))
                    + _random.uniform(0, backoff_jitter),
                    backoff_max,
                )
                print_and_log(
                    f"[*] Attempt {attempt}/{max_attempts} failed, retrying in {_delay:.1f}s",
                    LOG__GENERAL,
                )
                _time.sleep(_delay)
                continue
            raise

        except (_errors.ConnectionError, _errors.ServicesNotResolvedError):
            attempt += 1
            if attempt < max_attempts:
                _delay = min(
                    backoff_base * (2 ** (attempt - 1))
                    + _random.uniform(0, backoff_jitter),
                    backoff_max,
                )
                print_and_log(
                    f"[*] Attempt {attempt}/{max_attempts} failed, retrying in {_delay:.1f}s",
                    LOG__GENERAL,
                )
                _time.sleep(_delay)
                continue
            raise

    # ------------------------------------------------------------------
    # 3. Enumerate GATT database
    # ------------------------------------------------------------------
    _ = device.services_resolved(deep=deep_enumeration)

    mapping = device.ble_device__mapping
    mine_map = device.ble_device__mine_mapping
    perm_map = device.ble_device__permission_mapping

    # ------------------------------------------------------------------
    # 4. Start connection monitoring if requested
    # ------------------------------------------------------------------
    if enable_monitoring:
        monitor = ReconnectionMonitor(
            device,
            max_attempts=5,
            callback=reconnect_callback,
        )
        monitor.start_monitoring()
        device._reconnection_monitor = monitor

    return device, mapping, mine_map, perm_map


def connect_with_monitoring(
    target_bt_addr: str,
    max_reconnect_attempts: int = 5,
    reconnect_callback: Optional[Callable[[bool, str], None]] = None,
) -> Tuple[_LEDevice, Dict[str, Any], Dict[str, List[str]], Dict[str, List[str]]]:
    """Connect to a BLE device with automatic reconnection monitoring.
    
    This is a convenience wrapper around connect_and_enumerate__bluetooth__low_energy
    that enables reconnection monitoring by default.
    
    Parameters
    ----------
    target_bt_addr: str
        Bluetooth MAC address ("AA:BB:CC:DD:EE:FF").  Case-insensitive.
    max_reconnect_attempts: int
        Maximum number of reconnection attempts, by default 5
    reconnect_callback: Optional[Callable[[bool, str], None]]
        Callback function to call when reconnection occurs
        
    Returns
    -------
    tuple
        *(device, mapping, landmine_map, perm_map)* – mirrors the monolith in
        order and structure.
    """
    return connect_and_enumerate__bluetooth__low_energy(
        target_bt_addr,
        enable_monitoring=True,
        reconnect_callback=reconnect_callback,
    )
