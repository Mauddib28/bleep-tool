"""AdvMonitor listen overlay: catch-all (or user) patterns on a live adapter.

Registers AdvertisementMonitor children on the shared GLib loop, buffers
``DeviceFound`` Device1 property snapshots, and never calls StartDiscovery /
StopDiscovery. Survey unions the buffer with R1 harvest so neither channel
is an inclusion gate.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import dbus

from bleep.bt_ref.constants import BLUEZ_SERVICE_NAME, DBUS_PROPERTIES, DEVICE_INTERFACE
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.dbuslayer.adv_monitor import (
    AdvMonitorApp,
    AdvMonitorManager,
    MonitorCallbacks,
    MonitorPattern,
    RSSIConfig,
)
from bleep.dbuslayer.adv_patterns import (
    MSFT_PATTERNS_PER_MONITOR,
    catch_all_pattern_groups,
    catch_all_summary,
    chunk_patterns,
    validate_pattern,
)
from bleep.dbuslayer.manager import build_discovered_device_dict

__all__ = [
    "AdvMonitorOverlay",
    "device_entry_from_path",
    "register_listen_monitors",
]


def _app_id_for_adapter(adapter: str) -> int:
    digits = "".join(c for c in adapter if c.isdigit())
    return 50 + (int(digits) if digits else 0)


def device_entry_from_path(bus: dbus.SystemBus, path: str) -> Optional[Dict[str, Any]]:
    """Map a BlueZ Device1 object path to the harvest dict (protocol appearance)."""
    try:
        props_iface = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, path), DBUS_PROPERTIES
        )
        raw = dict(props_iface.GetAll(DEVICE_INTERFACE))
    except dbus.exceptions.DBusException as exc:
        print_and_log(f"[advmon] GetAll {path}: {exc}", LOG__DEBUG)
        return None
    entry = build_discovered_device_dict(str(path), raw)
    entry["advmon"] = True
    return entry


def register_listen_monitors(
    bus: dbus.SystemBus,
    adapter_path: str,
    *,
    user_patterns: Optional[Sequence[MonitorPattern]] = None,
    extra_patterns: Optional[Sequence[MonitorPattern]] = None,
    rssi: Optional[RSSIConfig] = None,
    callbacks: Optional[MonitorCallbacks] = None,
    app_id: int = 0,
    sampling_period: int = 255,
    log_catch_all: bool = True,
) -> Tuple[AdvMonitorApp, AdvMonitorManager, int, bool]:
    """Register catch-all or *user_patterns* monitors. Returns (app, mgr, n, catch_all).

    *user_patterns* replaces catch-all (explicit ``-p`` / manufacturer-only
    start). *extra_patterns* are OR-appended onto Flags-OR (survey
    ``--listen-pattern`` / ``--listen-manufacturer`` / ``--listen-mfr-string``).
    """
    mgr = AdvMonitorManager(bus, adapter_path)
    feats = mgr.get_supported_features()
    offload = "controller-patterns" in feats
    catch_all = not user_patterns
    if user_patterns:
        groups = [list(user_patterns)]
    else:
        groups = [list(g) for g in catch_all_pattern_groups(offload=offload)]
        if extra_patterns:
            extras = [validate_pattern(p) for p in extra_patterns]
            # Own child: mixing AD types onto the Flags-OR monitor
            # NoReply-killed software AdvMonitor on this host (2026-09-04).
            groups.extend(chunk_patterns(extras, MSFT_PATTERNS_PER_MONITOR))
        if log_catch_all:
            print_and_log(
                f"[*] AdvMonitor {catch_all_summary(offload=offload)} on {adapter_path}",
                LOG__GENERAL,
            )
            print_and_log(
                "[*] AdvMonitor is a Flags-OR overlay, not a BlueZ match-all. "
                "Devices without matching Flags are still collected via StartDiscovery.",
                LOG__GENERAL,
            )
            if extra_patterns:
                print_and_log(
                f"[*] AdvMonitor extras: {len(extra_patterns)} pattern(s) on a "
                "separate or_patterns child (not mixed with Flags)",
                    LOG__GENERAL,
                )
                for pat in extra_patterns:
                    print_and_log(
                        f"     extra: offset={pat.start_pos} "
                        f"ad_type=0x{int(pat.ad_type):02X} "
                        f"content={bytes(pat.content).hex()}",
                        LOG__GENERAL,
                    )

    rssi = rssi or RSSIConfig(sampling_period=sampling_period)
    app = AdvMonitorApp(bus, app_id=app_id)
    n = 0
    for group in groups:
        for pat in group:
            validate_pattern(pat)
        app.add_monitor(
            monitor_type="or_patterns",
            rssi=rssi,
            patterns=list(group),
            callbacks=callbacks,
        )
        n += 1
    if n == 0:
        raise RuntimeError("no AdvertisementMonitor children to register")
    ok = mgr.register(app)
    if not ok:
        app.remove_all()
        raise RuntimeError(
            f"RegisterMonitor failed on {adapter_path} "
            "(NoReply/daemon restart, missing AdvertisementMonitorManager1, "
            "or rejected patterns). See the log line above; "
            "'bleep --check-env' reports whether -E is actually missing."
        )
    return app, mgr, n, catch_all


class AdvMonitorOverlay:
    """Per-adapter Found/Lost buffer for survey union-merge."""

    def __init__(self, adapter_name: str):
        self.adapter_name = adapter_name
        self._lock = threading.Lock()
        self._found: Dict[str, Dict[str, Any]] = {}
        self._app: Optional[AdvMonitorApp] = None
        self._mgr: Optional[AdvMonitorManager] = None
        self._bus: Optional[dbus.SystemBus] = None

    def start(
        self,
        bus: Optional[dbus.SystemBus] = None,
        extra_patterns: Optional[Sequence[MonitorPattern]] = None,
    ) -> int:
        self._bus = bus or dbus.SystemBus()
        adapter_path = (
            self.adapter_name
            if self.adapter_name.startswith("/")
            else f"/org/bluez/{self.adapter_name}"
        )
        cbs = MonitorCallbacks(
            on_device_found=self._on_found,
            on_device_lost=lambda _p: None,
            on_release=lambda: print_and_log(
                f"[-] AdvMonitor overlay released on {self.adapter_name}",
                LOG__DEBUG,
            ),
        )
        self._app, self._mgr, n, _ = register_listen_monitors(
            self._bus,
            adapter_path,
            extra_patterns=list(extra_patterns) if extra_patterns else None,
            callbacks=cbs,
            app_id=_app_id_for_adapter(self.adapter_name),
            sampling_period=255,
        )
        print_and_log(
            f"[+] AdvMonitor overlay registered on {self.adapter_name} ({n} monitors)",
            LOG__GENERAL,
        )
        return n

    def _on_found(self, device_path: str) -> None:
        if self._bus is None:
            return
        entry = device_entry_from_path(self._bus, device_path)
        if not entry:
            return
        mac = (entry.get("address") or "").upper()
        if not mac:
            return
        with self._lock:
            self._found[mac] = entry

    def take_found(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            out = self._found
            self._found = {}
        return out

    def stop(self) -> None:
        if self._mgr is not None and self._app is not None:
            try:
                self._mgr.unregister(self._app)
            except Exception as exc:
                print_and_log(f"[advmon] unregister {self.adapter_name}: {exc}", LOG__DEBUG)
            try:
                self._app.remove_all()
            except Exception:
                pass
        self._app = None
        self._mgr = None
