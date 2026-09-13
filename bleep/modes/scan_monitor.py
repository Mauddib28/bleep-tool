"""``bleep scan --monitor`` — AdvertisementMonitor scan (BZ-12e).

Uses BlueZ ``AdvertisementMonitor1`` instead of (or alongside) ``StartDiscovery``.
Empty patterns are illegal; with no ``-p`` this injects the Flags-OR overlay
(one monitor, GAP Flags ``00,02,04,05,06,18,1A``). That is not a BlueZ
match-all. Completeness for survey remains Device1 harvest.

If ``--device`` is given, Found callbacks are filtered to that MAC after
Flags-OR matching.

Requires BlueZ ``-E`` experimental mode.
"""

from __future__ import annotations

import signal
import sys
import time

from bleep.core.log import get_logger, print_and_log, LOG__GENERAL, LOG__DEBUG

logger = get_logger(__name__)


def _device_path_to_mac(path: str) -> str:
    if "/dev_" not in path:
        return path
    mac_part = path.rsplit("/dev_", 1)[-1]
    return mac_part.replace("_", ":").upper()


def run_monitor_scan(args) -> int:
    """Execute a scan via AdvertisementMonitor (``bleep scan --monitor``)."""
    try:
        import dbus
        import dbus.mainloop.glib
        from gi.repository import GLib
    except ImportError as exc:
        print(f"[!] Missing dependency for --monitor mode: {exc}", file=sys.stderr)
        return 1

    from bleep.dbuslayer.adv_monitor import MonitorCallbacks, RSSIConfig
    from bleep.dbuslayer.adv_collector import register_listen_monitors

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter = getattr(args, "adapter", "hci0")
    adapter_path = f"/org/bluez/{adapter}" if not adapter.startswith("/") else adapter

    target_mac = getattr(args, "device", None)
    if target_mac:
        target_mac = target_mac.upper().replace("-", ":")

    timeout = getattr(args, "timeout", 10)
    found_devices: dict[str, int] = {}
    start_ts = time.monotonic()

    def _on_found(device_path: str) -> None:
        mac = _device_path_to_mac(device_path)
        if target_mac and mac != target_mac:
            return
        found_devices[mac] = found_devices.get(mac, 0) + 1
        elapsed = time.monotonic() - start_ts
        tag = "NEW " if found_devices[mac] == 1 else "    "
        print_and_log(f"  [{elapsed:6.1f}s] {tag} {mac}", LOG__GENERAL)

    def _on_lost(device_path: str) -> None:
        mac = _device_path_to_mac(device_path)
        if target_mac and mac != target_mac:
            return
        elapsed = time.monotonic() - start_ts
        print_and_log(f"  [{elapsed:6.1f}s] LOST {mac}", LOG__GENERAL)

    cbs = MonitorCallbacks(
        on_activate=lambda: print_and_log("[+] Monitor activated — listening for devices", LOG__GENERAL),
        on_release=lambda: print_and_log("[-] Monitor released by BlueZ", LOG__GENERAL),
        on_device_found=_on_found,
        on_device_lost=_on_lost,
    )

    try:
        app, mgr, nmon, _ = register_listen_monitors(
            bus,
            adapter_path,
            callbacks=cbs,
            rssi=RSSIConfig(sampling_period=255),
            sampling_period=255,
        )
    except dbus.exceptions.DBusException as exc:
        print_and_log(
            f"[!] Cannot access AdvertisementMonitorManager1 on {adapter_path}: {exc}\n"
            "    Ensure BlueZ is running with --experimental (-E) flag.",
            LOG__GENERAL,
        )
        return 1
    except RuntimeError as exc:
        print_and_log(f"[!] {exc}", LOG__GENERAL)
        return 1

    filt = f" (filtering for {target_mac})" if target_mac else ""
    print_and_log(
        f"[+] Monitor scan started{filt} — {nmon} monitors, {timeout}s timeout (Ctrl-C to stop)",
        LOG__GENERAL,
    )

    loop = GLib.MainLoop()

    def _quit(*_a):
        loop.quit()

    signal.signal(signal.SIGINT, _quit)
    signal.signal(signal.SIGTERM, _quit)

    if timeout and timeout > 0:
        GLib.timeout_add_seconds(timeout, loop.quit)

    loop.run()

    mgr.unregister(app)
    app.remove_all()

    elapsed = time.monotonic() - start_ts
    unique = len(found_devices)
    print_and_log(
        f"\n[*] Monitor scan complete: {unique} unique device(s) in {elapsed:.1f}s",
        LOG__GENERAL,
    )
    return 0
