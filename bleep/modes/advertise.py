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

from bleep.core.log import get_logger, print_and_log, LOG__GENERAL

logger = get_logger(__name__)

_output_ctx = None


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


def _validate_includes(includes, appearance, supported_includes):
    """Validate requested advertising ``Includes`` against the adapter.

    Pure decision helper (no I/O) so it can be unit-tested in isolation.

    Parameters
    ----------
    includes:
        The include features requested by the user (e.g. ``["appearance"]``).
    appearance:
        Explicit ``--appearance`` value, or ``None`` when not given.
    supported_includes:
        ``LEAdvertisingManager1.SupportedIncludes`` for the adapter (may be empty
        when the manager could not be queried — in which case the support check
        is skipped rather than emitting false warnings).

    Returns
    -------
    tuple[list[str], bool]
        ``(warnings, appearance_needs_value)`` where *warnings* are user-facing
        pre-registration messages and *appearance_needs_value* is ``True`` when
        ``appearance`` is requested via the include but no explicit value was
        supplied (drives the targeted post-failure hint).
    """
    includes = list(includes or [])
    supported = set(supported_includes or [])
    warnings: list[str] = []

    # [C] Requested an include the adapter does not advertise as supported.
    # Skip when SupportedIncludes is unavailable (empty) to avoid false alarms.
    if supported:
        for inc in includes:
            if inc not in supported:
                warnings.append(
                    f"adapter does not list '{inc}' in SupportedIncludes "
                    "(see 'advertise caps'); BlueZ may reject this advertisement."
                )

    # [A] 'appearance' include with no explicit value: BlueZ must source the
    # Appearance from the adapter/system value, which is frequently unset and
    # then fails with "Failed to register advertisement".
    appearance_needs_value = ("appearance" in includes) and (appearance is None)
    if appearance_needs_value:
        warnings.append(
            "--include-appearance asks BlueZ to source the Appearance from the "
            "adapter/system value, which is often unset (→ 'Failed to register "
            "advertisement'). Pass --appearance <value> for a self-contained value."
        )

    return warnings, appearance_needs_value


def _handle_caps(args) -> int:
    """``bleep advertise caps`` — show manager capabilities."""
    from bleep.dbuslayer.le_advertising import LEAdvertisingManager

    bus = dbus.SystemBus()
    adapter_path = _resolve_adapter_path(args.adapter)

    try:
        mgr = LEAdvertisingManager(bus, adapter_path)
    except dbus.exceptions.DBusException as e:
        print_and_log(f"[!] Cannot access LEAdvertisingManager1 on {adapter_path}: {e}", LOG__GENERAL)
        return 1

    active_inst = mgr.get_active_instances()
    supported_inst = mgr.get_supported_instances()
    includes = mgr.get_supported_includes()
    channels = mgr.get_supported_secondary_channels()
    feats = mgr.get_supported_features()
    caps = mgr.get_supported_capabilities()

    print_and_log(f"Adapter: {adapter_path}", LOG__GENERAL)
    print_and_log(f"  ActiveInstances ........... {active_inst}", LOG__GENERAL)
    print_and_log(f"  SupportedInstances ........ {supported_inst}", LOG__GENERAL)
    print_and_log(f"  SupportedIncludes ......... {', '.join(includes) if includes else '(none)'}", LOG__GENERAL)
    print_and_log(f"  SupportedSecondaryChannels  {', '.join(channels) if channels else '(none)'}", LOG__GENERAL)
    print_and_log(f"  SupportedFeatures ......... {', '.join(feats) if feats else '(none)'}", LOG__GENERAL)

    if caps:
        print_and_log("  SupportedCapabilities:", LOG__GENERAL)
        for k, v in sorted(caps.items()):
            print_and_log(f"    {k}: {v}", LOG__GENERAL)

    if _output_ctx and _output_ctx.is_json:
        _output_ctx.emit_result({
            "event": "advertise_caps",
            "adapter": adapter_path,
            "active_instances": active_inst,
            "supported_instances": supported_inst,
            "supported_includes": list(includes),
            "supported_secondary_channels": list(channels),
            "supported_features": list(feats),
            "supported_capabilities": dict(caps) if caps else {},
        })

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
        print_and_log(f"[!] Cannot access LEAdvertisingManager1: {e}", LOG__GENERAL)
        return 1

    avail = mgr.get_supported_instances()
    active = mgr.get_active_instances()
    if avail <= active:
        print_and_log(f"[!] No available advertising instances ({active}/{active + avail} in use)", LOG__GENERAL)
        return 1

    # Build config from CLI args
    manufacturer_data = {}
    for raw in (args.manufacturer_data or []):
        try:
            cid, data = _parse_manufacturer_data(raw)
            manufacturer_data[cid] = data
        except ValueError as e:
            print_and_log(f"[!] {e}", LOG__GENERAL)
            return 1

    service_data = {}
    for raw in (args.service_data or []):
        try:
            uuid, data = _parse_service_data(raw)
            service_data[uuid] = data
        except ValueError as e:
            print_and_log(f"[!] {e}", LOG__GENERAL)
            return 1

    includes = []
    if args.include_tx_power:
        includes.append("tx-power")
    if args.include_appearance:
        includes.append("appearance")
    if args.include_name:
        includes.append("local-name")

    include_warnings, appearance_needs_value = _validate_includes(
        includes, args.appearance, mgr.get_supported_includes()
    )
    for _w in include_warnings:
        print_and_log(f"[!] {_w}", LOG__GENERAL)

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
        print_and_log("[-] Advertisement released by BlueZ", LOG__GENERAL)
        if _output_ctx and _output_ctx.is_json:
            _output_ctx.emit_result({"event": "adv_released"})
        loop.quit()

    adv = LEAdvertisement(bus, config, on_release=_on_release)

    ok = mgr.register(adv)
    if not ok:
        print_and_log("[!] Failed to register advertisement with BlueZ", LOG__GENERAL)
        if appearance_needs_value:
            print_and_log(
                "    Hint: this is likely the appearance include with no value — "
                "pass --appearance <value> (self-contained) instead of, or in "
                "addition to, --include-appearance.",
                LOG__GENERAL,
            )
        else:
            print_and_log(
                "    See the BlueZ error above. Common causes: an --include-* the "
                "adapter cannot fulfil, unsupported payload fields, or no free "
                "advertising instance (check 'advertise caps').",
                LOG__GENERAL,
            )
        adv.remove_advertisement()
        return 1

    print_and_log(f"[+] Advertisement registered at {adv.path}", LOG__GENERAL)
    print_and_log(f"    Type: {config.ad_type}", LOG__GENERAL)
    if config.local_name:
        print_and_log(f"    LocalName: {config.local_name}", LOG__GENERAL)
    if config.service_uuids:
        print_and_log(f"    ServiceUUIDs: {', '.join(config.service_uuids)}", LOG__GENERAL)
    if config.manufacturer_data:
        for cid, data in config.manufacturer_data.items():
            print_and_log(f"    ManufacturerData: 0x{cid:04X} → {data.hex()}", LOG__GENERAL)
    if config.service_data:
        for uuid, data in config.service_data.items():
            print_and_log(f"    ServiceData: {uuid} → {data.hex()}", LOG__GENERAL)
    if config.tx_power is not None:
        print_and_log(f"    TxPower: {config.tx_power} dBm", LOG__GENERAL)
    if config.min_interval or config.max_interval:
        print_and_log(f"    Interval: {config.min_interval or '?'}–{config.max_interval or '?'} ms", LOG__GENERAL)
    if config.timeout:
        print_and_log(f"    Timeout: {config.timeout}s (BlueZ auto-removes)", LOG__GENERAL)
    print_and_log("", LOG__GENERAL)
    print_and_log("[*] Broadcasting — Ctrl-C to stop.", LOG__GENERAL)

    if _output_ctx and _output_ctx.is_json:
        _output_ctx.emit_result({
            "event": "adv_started",
            "path": adv.path,
            "type": config.ad_type,
            "local_name": config.local_name,
            "service_uuids": config.service_uuids,
        })

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

    print_and_log(f"\n[*] Stopped after {elapsed:.1f}s", LOG__GENERAL)
    if _output_ctx and _output_ctx.is_json:
        _output_ctx.emit_result({"event": "adv_stopped", "elapsed_s": round(elapsed, 1)})
    return 0


def run(args, output=None) -> int:
    """Execute advertise mode with parsed args and optional OutputContext."""
    global _output_ctx
    from bleep.core.output import OutputContext
    from bleep.core.log import set_output_mode

    if output is None:
        output = OutputContext()

    _output_ctx = output
    set_output_mode(output.mode)

    return handle_advertise(args)


def handle_advertise(args) -> int:
    """Entry point called from cli.py dispatch."""
    action = getattr(args, "adv_action", None)
    if not action:
        print_and_log("Usage: bleep advertise {caps|start}", LOG__GENERAL)
        print_and_log("  caps    Show LEAdvertisingManager1 capabilities", LOG__GENERAL)
        print_and_log("  start   Register an advertisement and broadcast", LOG__GENERAL)
        return 1

    if action == "caps":
        return _handle_caps(args)
    elif action == "start":
        return _handle_start(args)
    else:
        print_and_log(f"[!] Unknown advertise action: {action}", LOG__GENERAL)
        return 1
