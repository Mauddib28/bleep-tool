"""CLI mode for Advertisement Monitor management (BZ-11/12).

Wraps the ``AdvMonitorApp`` / ``AdvMonitorManager`` D-Bus layer to let users
create kernel-offloaded pattern-match monitors with RSSI thresholds, without
needing an active ``StartDiscovery`` session.

Sub-actions
-----------
* ``caps``   — query ``AdvertisementMonitorManager1`` capabilities.
* ``start``  — register a monitor app with pattern / RSSI criteria and stream
  ``DeviceFound`` / ``DeviceLost`` events until Ctrl-C.
"""

from __future__ import annotations

import signal
import sys
import time
from typing import Optional

import dbus
import dbus.mainloop.glib

from bleep.core.log import get_logger, print_and_log, LOG__DEBUG

logger = get_logger(__name__)

# Lazy imports — heavy D-Bus and GLib work happens inside handler functions.


def _resolve_adapter_path(adapter: str) -> str:
    if adapter.startswith("/"):
        return adapter
    return f"/org/bluez/{adapter}"


def _parse_pattern_arg(raw: str):
    """Parse ``offset:ad_type:hex_content`` into a MonitorPattern."""
    from bleep.dbuslayer.adv_monitor import MonitorPattern

    parts = raw.split(":", 2)
    if len(parts) != 3:
        raise ValueError(
            f"Pattern must be offset:ad_type:hex_content — got {raw!r}"
        )
    return MonitorPattern(
        start_pos=int(parts[0]),
        ad_type=int(parts[1], 0),
        content=bytes.fromhex(parts[2]),
    )


def _device_path_to_mac(path: str) -> str:
    if "/dev_" not in path:
        return path
    return path.rsplit("/dev_", 1)[-1].replace("_", ":").upper()


def _handle_caps(args) -> int:
    """``bleep monitor caps`` — show manager capabilities."""
    from bleep.dbuslayer.adv_monitor import AdvMonitorManager

    bus = dbus.SystemBus()
    adapter_path = _resolve_adapter_path(args.adapter)

    try:
        mgr = AdvMonitorManager(bus, adapter_path)
    except dbus.exceptions.DBusException as e:
        print(
            f"[!] Cannot access AdvertisementMonitorManager1 on {adapter_path}: {e}",
            file=sys.stderr,
        )
        print(
            "[*] Hint: ensure BlueZ was built with --enable-experimental "
            "and bluetoothd is running with -E flag.",
            file=sys.stderr,
        )
        return 1

    types = mgr.get_supported_types()
    feats = mgr.get_supported_features()

    print(f"Adapter: {adapter_path}")
    print(f"  SupportedMonitorTypes .. {', '.join(types) if types else '(none)'}")
    print(f"  SupportedFeatures ..... {', '.join(feats) if feats else '(none)'}")
    return 0


def _handle_start(args) -> int:
    """``bleep monitor start`` — register monitor(s) and stream events."""
    from gi.repository import GLib
    from bleep.dbuslayer.adv_monitor import (
        AdvMonitorApp,
        AdvMonitorManager,
        MonitorCallbacks,
        MonitorPattern,
        RSSIConfig,
    )

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter_path = _resolve_adapter_path(args.adapter)

    try:
        mgr = AdvMonitorManager(bus, adapter_path)
    except dbus.exceptions.DBusException as e:
        print(f"[!] Cannot access AdvMonitorManager1: {e}", file=sys.stderr)
        return 1

    app = AdvMonitorApp(bus)

    # Build patterns
    patterns: list[MonitorPattern] = []
    for raw in (args.patterns or []):
        try:
            patterns.append(_parse_pattern_arg(raw))
        except ValueError as e:
            print(f"[!] {e}", file=sys.stderr)
            return 1

    rssi = RSSIConfig(
        high_threshold=args.rssi_high if args.rssi_high is not None else 127,
        high_timeout=args.rssi_high_timeout,
        low_threshold=args.rssi_low if args.rssi_low is not None else 127,
        low_timeout=args.rssi_low_timeout,
        sampling_period=args.sampling_period,
    )

    found_count = 0
    lost_count = 0
    start_ts = time.monotonic()

    def _on_found(device_path: str) -> None:
        nonlocal found_count
        found_count += 1
        mac = _device_path_to_mac(device_path)
        elapsed = time.monotonic() - start_ts
        print(f"[{elapsed:7.1f}s] FOUND  {mac}")

    def _on_lost(device_path: str) -> None:
        nonlocal lost_count
        lost_count += 1
        mac = _device_path_to_mac(device_path)
        elapsed = time.monotonic() - start_ts
        print(f"[{elapsed:7.1f}s] LOST   {mac}")

    cbs = MonitorCallbacks(
        on_activate=lambda: print("[+] Monitor activated by BlueZ"),
        on_release=lambda: print("[-] Monitor released by BlueZ"),
        on_device_found=_on_found,
        on_device_lost=_on_lost,
    )

    mid = app.add_monitor(
        monitor_type="or_patterns",
        rssi=rssi,
        patterns=patterns,
        callbacks=cbs,
    )

    ok = mgr.register(app)
    if not ok:
        print("[!] Failed to register monitor app with BlueZ", file=sys.stderr)
        app.remove_all()
        return 1

    print(f"[+] Monitor registered (id={mid}).  Streaming events — Ctrl-C to stop.")
    if patterns:
        for p in patterns:
            print(f"     pattern: offset={p.start_pos} ad_type=0x{p.ad_type:02X} content={p.content.hex()}")
    if rssi.high_threshold != 127 or rssi.low_threshold != 127:
        print(f"     RSSI: high={rssi.high_threshold} dBm (timeout {rssi.high_timeout}s), "
              f"low={rssi.low_threshold} dBm (timeout {rssi.low_timeout}s)")
    print()

    loop = GLib.MainLoop()

    def _on_sigint(*_a):
        loop.quit()

    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)

    if args.duration:
        GLib.timeout_add_seconds(args.duration, loop.quit)

    loop.run()

    # Cleanup
    mgr.unregister(app)
    app.remove_all()

    elapsed = time.monotonic() - start_ts
    print(f"\n[*] Stopped after {elapsed:.1f}s — {found_count} found, {lost_count} lost events")
    return 0


def handle_monitor(args) -> int:
    """Entry point called from cli.py dispatch."""
    action = getattr(args, "monitor_action", None)
    if not action:
        print("Usage: bleep monitor {caps|start}", file=sys.stderr)
        print("  caps    Show AdvertisementMonitorManager1 capabilities")
        print("  start   Register monitors and stream DeviceFound/Lost events")
        return 1

    if action == "caps":
        return _handle_caps(args)
    elif action == "start":
        return _handle_start(args)
    else:
        print(f"[!] Unknown monitor action: {action}", file=sys.stderr)
        return 1
