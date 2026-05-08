"""CLI mode for LE Advertisement management (BZ-6/7).

Wraps ``LEAdvertisement`` / ``LEAdvertisingManager`` to let users broadcast
custom BLE advertisement packets from the local adapter.

Sub-actions
-----------
* ``caps``  — query ``LEAdvertisingManager1`` capabilities (instances,
  includes, secondary channels, features).
* ``start`` — register an advertisement and broadcast until Ctrl-C or
  ``--duration`` expires.
"""

from __future__ import annotations

import signal
import sys
import time
from typing import Optional

import dbus
import dbus.mainloop.glib

from bleep.core.log import get_logger

logger = get_logger(__name__)


def _resolve_adapter_path(adapter: str) -> str:
    if adapter.startswith("/"):
        return adapter
    return f"/org/bluez/{adapter}"


def _parse_manufacturer_data(raw: str) -> tuple[int, bytes]:
    """Parse ``COMPANY_ID:HEX_DATA`` into (int, bytes)."""
    parts = raw.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Manufacturer data must be COMPANY_ID:HEX_DATA — got {raw!r}")
    return int(parts[0], 0), bytes.fromhex(parts[1])


def _parse_service_data(raw: str) -> tuple[str, bytes]:
    """Parse ``UUID:HEX_DATA`` into (str, bytes)."""
    parts = raw.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Service data must be UUID:HEX_DATA — got {raw!r}")
    return parts[0], bytes.fromhex(parts[1])


def _handle_caps(args) -> int:
    """``bleep advertise caps`` — show manager capabilities."""
    from bleep.dbuslayer.le_advertising import LEAdvertisingManager

    bus = dbus.SystemBus()
    adapter_path = _resolve_adapter_path(args.adapter)

    try:
        mgr = LEAdvertisingManager(bus, adapter_path)
    except dbus.exceptions.DBusException as e:
        print(f"[!] Cannot access LEAdvertisingManager1 on {adapter_path}: {e}",
              file=sys.stderr)
        return 1

    print(f"Adapter: {adapter_path}")
    print(f"  ActiveInstances ........... {mgr.get_active_instances()}")
    print(f"  SupportedInstances ........ {mgr.get_supported_instances()}")

    includes = mgr.get_supported_includes()
    print(f"  SupportedIncludes ......... {', '.join(includes) if includes else '(none)'}")

    channels = mgr.get_supported_secondary_channels()
    print(f"  SupportedSecondaryChannels  {', '.join(channels) if channels else '(none)'}")

    feats = mgr.get_supported_features()
    print(f"  SupportedFeatures ......... {', '.join(feats) if feats else '(none)'}")

    caps = mgr.get_supported_capabilities()
    if caps:
        print(f"  SupportedCapabilities:")
        for k, v in sorted(caps.items()):
            print(f"    {k}: {v}")

    return 0


def _handle_start(args) -> int:
    """``bleep advertise start`` — register an advertisement and broadcast."""
    from gi.repository import GLib
    from bleep.dbuslayer.le_advertising import (
        AdvertisementConfig,
        LEAdvertisement,
        LEAdvertisingManager,
    )

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter_path = _resolve_adapter_path(args.adapter)

    try:
        mgr = LEAdvertisingManager(bus, adapter_path)
    except dbus.exceptions.DBusException as e:
        print(f"[!] Cannot access LEAdvertisingManager1: {e}", file=sys.stderr)
        return 1

    avail = mgr.get_supported_instances()
    active = mgr.get_active_instances()
    if avail <= active:
        print(f"[!] No available advertising instances ({active}/{active + avail} in use)",
              file=sys.stderr)
        return 1

    # Build config from CLI args
    manufacturer_data = {}
    for raw in (args.manufacturer_data or []):
        try:
            cid, data = _parse_manufacturer_data(raw)
            manufacturer_data[cid] = data
        except ValueError as e:
            print(f"[!] {e}", file=sys.stderr)
            return 1

    service_data = {}
    for raw in (args.service_data or []):
        try:
            uuid, data = _parse_service_data(raw)
            service_data[uuid] = data
        except ValueError as e:
            print(f"[!] {e}", file=sys.stderr)
            return 1

    includes = []
    if args.include_tx_power:
        includes.append("tx-power")
    if args.include_appearance:
        includes.append("appearance")
    if args.include_name:
        includes.append("local-name")

    config = AdvertisementConfig(
        ad_type=args.type,
        service_uuids=args.uuid or None,
        manufacturer_data=manufacturer_data or None,
        service_data=service_data or None,
        local_name=args.name,
        includes=includes or None,
        appearance=args.appearance,
        discoverable=args.discoverable if args.discoverable is not None else None,
        tx_power=args.tx_power,
        min_interval=args.min_interval,
        max_interval=args.max_interval,
        secondary_channel=args.secondary_channel,
        timeout=args.duration,
    )

    released = False

    def _on_release():
        nonlocal released
        released = True
        print("[-] Advertisement released by BlueZ")
        loop.quit()

    adv = LEAdvertisement(bus, config, on_release=_on_release)

    ok = mgr.register(adv)
    if not ok:
        print("[!] Failed to register advertisement with BlueZ", file=sys.stderr)
        adv.remove_advertisement()
        return 1

    # Display what's being advertised
    print(f"[+] Advertisement registered at {adv.path}")
    print(f"    Type: {config.ad_type}")
    if config.local_name:
        print(f"    LocalName: {config.local_name}")
    if config.service_uuids:
        print(f"    ServiceUUIDs: {', '.join(config.service_uuids)}")
    if config.manufacturer_data:
        for cid, data in config.manufacturer_data.items():
            print(f"    ManufacturerData: 0x{cid:04X} → {data.hex()}")
    if config.service_data:
        for uuid, data in config.service_data.items():
            print(f"    ServiceData: {uuid} → {data.hex()}")
    if config.tx_power is not None:
        print(f"    TxPower: {config.tx_power} dBm")
    if config.min_interval or config.max_interval:
        print(f"    Interval: {config.min_interval or '?'}–{config.max_interval or '?'} ms")
    if config.timeout:
        print(f"    Timeout: {config.timeout}s (BlueZ auto-removes)")
    print()
    print("[*] Broadcasting — Ctrl-C to stop.")

    loop = GLib.MainLoop()

    def _on_sigint(*_a):
        loop.quit()

    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)

    if args.local_duration:
        GLib.timeout_add_seconds(args.local_duration, loop.quit)

    start_ts = time.monotonic()
    loop.run()
    elapsed = time.monotonic() - start_ts

    if not released:
        mgr.unregister(adv)
    adv.remove_advertisement()

    print(f"\n[*] Stopped after {elapsed:.1f}s")
    return 0


def handle_advertise(args) -> int:
    """Entry point called from cli.py dispatch."""
    action = getattr(args, "adv_action", None)
    if not action:
        print("Usage: bleep advertise {caps|start}", file=sys.stderr)
        print("  caps    Show LEAdvertisingManager1 capabilities")
        print("  start   Register an advertisement and broadcast")
        return 1

    if action == "caps":
        return _handle_caps(args)
    elif action == "start":
        return _handle_start(args)
    else:
        print(f"[!] Unknown advertise action: {action}", file=sys.stderr)
        return 1
