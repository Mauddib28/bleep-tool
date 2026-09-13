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

from bleep.core.log import get_logger, print_and_log, LOG__GENERAL, LOG__DEBUG

logger = get_logger(__name__)

_output_ctx = None

# Lazy imports — heavy D-Bus and GLib work happens inside handler functions.


def _resolve_adapter_path(adapter: str) -> str:
    if adapter.startswith("/"):
        return adapter
    return f"/org/bluez/{adapter}"


def _device_path_to_mac(path: str) -> str:
    if "/dev_" not in path:
        return path
    return path.rsplit("/dev_", 1)[-1].replace("_", ":").upper()


def _handle_caps(args) -> int:
    """``bleep advertise-monitor caps`` — show manager capabilities."""
    from bleep.dbuslayer.adv_monitor import AdvMonitorManager

    bus = dbus.SystemBus()
    adapter_path = _resolve_adapter_path(args.adapter)

    try:
        mgr = AdvMonitorManager(bus, adapter_path)
    except dbus.exceptions.DBusException as e:
        print_and_log(
            f"[!] Cannot access AdvertisementMonitorManager1 on {adapter_path}: {e}",
            LOG__GENERAL,
        )
        print_and_log(
            "[*] Hint: ensure BlueZ was built with --enable-experimental "
            "and bluetoothd is running with -E flag.",
            LOG__GENERAL,
        )
        return 1

    types = mgr.get_supported_types()
    feats = mgr.get_supported_features()

    print_and_log(f"Adapter: {adapter_path}", LOG__GENERAL)
    print_and_log(f"  SupportedMonitorTypes .. {', '.join(types) if types else '(none)'}", LOG__GENERAL)
    print_and_log(f"  SupportedFeatures ..... {', '.join(feats) if feats else '(none)'}", LOG__GENERAL)

    if _output_ctx and _output_ctx.is_json:
        _output_ctx.emit_result({
            "event": "monitor_caps",
            "adapter": adapter_path,
            "supported_types": list(types),
            "supported_features": list(feats),
        })
    return 0


def _handle_start(args) -> int:
    """``bleep advertise-monitor start`` — register monitor(s) and stream events."""
    from gi.repository import GLib
    from bleep.dbuslayer.adv_monitor import MonitorCallbacks, RSSIConfig
    from bleep.dbuslayer.adv_collector import register_listen_monitors
    from bleep.dbuslayer.adv_patterns import PatternError, parse_listen_extras

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter_path = _resolve_adapter_path(args.adapter)

    try:
        user_patterns = parse_listen_extras(
            patterns=getattr(args, "patterns", None),
            manufacturers=getattr(args, "manufacturers", None),
            mfr_strings=getattr(args, "mfr_strings", None),
        )
    except (ValueError, PatternError) as e:
        print_and_log(f"[!] {e}", LOG__GENERAL)
        return 1

    catch_all = not user_patterns
    sampling = args.sampling_period
    if not getattr(args, "patterns", None) and not sampling:
        sampling = 255

    rssi = RSSIConfig(
        high_threshold=args.rssi_high if args.rssi_high is not None else 127,
        high_timeout=args.rssi_high_timeout,
        low_threshold=args.rssi_low if args.rssi_low is not None else 127,
        low_timeout=args.rssi_low_timeout,
        sampling_period=sampling,
    )

    found_count = 0
    lost_count = 0
    unique_found: set = set()
    start_ts = time.monotonic()

    def _on_found(device_path: str) -> None:
        nonlocal found_count
        found_count += 1
        mac = _device_path_to_mac(device_path)
        elapsed = time.monotonic() - start_ts
        first = mac not in unique_found
        unique_found.add(mac)
        if first or not catch_all:
            print_and_log(f"[{elapsed:7.1f}s] FOUND  {mac}", LOG__GENERAL)
        if _output_ctx and _output_ctx.is_json:
            _output_ctx.emit_result({"event": "device_found", "mac": mac, "elapsed_s": round(elapsed, 1)})

    def _on_lost(device_path: str) -> None:
        nonlocal lost_count
        lost_count += 1
        mac = _device_path_to_mac(device_path)
        elapsed = time.monotonic() - start_ts
        print_and_log(f"[{elapsed:7.1f}s] LOST   {mac}", LOG__GENERAL)
        if _output_ctx and _output_ctx.is_json:
            _output_ctx.emit_result({"event": "device_lost", "mac": mac, "elapsed_s": round(elapsed, 1)})

    cbs = MonitorCallbacks(
        on_activate=lambda: print_and_log("[+] Monitor activated by BlueZ", LOG__GENERAL),
        on_release=lambda: print_and_log("[-] Monitor released by BlueZ", LOG__GENERAL),
        on_device_found=_on_found,
        on_device_lost=_on_lost,
    )

    try:
        app, mgr, nmon, _ = register_listen_monitors(
            bus,
            adapter_path,
            user_patterns=user_patterns or None,
            rssi=rssi,
            callbacks=cbs,
            sampling_period=sampling,
        )
    except dbus.exceptions.DBusException as e:
        print_and_log(f"[!] Cannot access AdvMonitorManager1: {e}", LOG__GENERAL)
        print_and_log(
            "[*] Hint: bluetoothd -E or Experimental=true in /etc/bluetooth/main.conf",
            LOG__GENERAL,
        )
        return 1
    except (RuntimeError, ValueError, PatternError) as e:
        print_and_log(f"[!] {e}", LOG__GENERAL)
        return 1

    print_and_log(
        f"[+] Monitor registered ({nmon} children).  Streaming events — Ctrl-C to stop.",
        LOG__GENERAL,
    )
    if user_patterns:
        for p in user_patterns:
            print_and_log(
                f"     pattern: offset={p.start_pos} ad_type=0x{p.ad_type:02X} "
                f"content={p.content.hex()}",
                LOG__GENERAL,
            )
    if rssi.high_threshold != 127 or rssi.low_threshold != 127:
        print_and_log(
            f"     RSSI: high={rssi.high_threshold} dBm (timeout {rssi.high_timeout}s), "
            f"low={rssi.low_threshold} dBm (timeout {rssi.low_timeout}s)",
            LOG__GENERAL,
        )
    print_and_log("", LOG__GENERAL)

    loop = GLib.MainLoop()

    def _on_sigint(*_a):
        loop.quit()

    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)

    if args.duration:
        GLib.timeout_add_seconds(args.duration, loop.quit)

    loop.run()

    mgr.unregister(app)
    app.remove_all()

    elapsed = time.monotonic() - start_ts
    print_and_log(
        f"\n[*] Stopped after {elapsed:.1f}s — {found_count} found, "
        f"{len(unique_found)} unique, {lost_count} lost events",
        LOG__GENERAL,
    )
    if _output_ctx and _output_ctx.is_json:
        _output_ctx.emit_result({
            "event": "monitor_stopped",
            "elapsed_s": round(elapsed, 1),
            "found_count": found_count,
            "unique_count": len(unique_found),
            "lost_count": lost_count,
        })
    return 0


def run(args, output=None) -> int:
    """Execute monitor mode with parsed args and optional OutputContext."""
    global _output_ctx
    from bleep.core.output import OutputContext
    from bleep.core.log import set_output_mode

    if output is None:
        output = OutputContext()

    _output_ctx = output
    set_output_mode(output.mode)

    return handle_monitor(args)


def handle_monitor(args) -> int:
    """Entry point called from cli.py dispatch."""
    action = getattr(args, "monitor_action", None)
    if not action:
        print_and_log("Usage: bleep advertise-monitor {caps|start}", LOG__GENERAL)
        print_and_log("  caps    Show AdvertisementMonitorManager1 capabilities", LOG__GENERAL)
        print_and_log("  start   Register monitors and stream DeviceFound/Lost events", LOG__GENERAL)
        return 1

    if action == "caps":
        return _handle_caps(args)
    elif action == "start":
        return _handle_start(args)
    else:
        print_and_log(f"[!] Unknown monitor action: {action}", LOG__GENERAL)
        return 1
