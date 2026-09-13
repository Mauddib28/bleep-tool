"""CLI dispatch handler for Classic Bluetooth scan mode."""

import sys

__all__ = ["run"]


def run(args, output=None) -> int:
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
    from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
    import dbus

    adapter_name = getattr(args, "adapter", None)
    adapter = _Adapter(adapter_name) if adapter_name else _Adapter()
    if not adapter.is_ready():
        print(f"[!] Bluetooth adapter not ready: {adapter_name or 'default'}", file=sys.stderr)
        return 1

    debug_mode = getattr(args, "debug", False)
    if debug_mode:
        print_and_log("[classic-scan] Debug mode enabled", LOG__GENERAL)
        print_and_log("[classic-scan] Using adapter: " + adapter.adapter_path, LOG__GENERAL)

    _f = {"Transport": "bredr"}
    if getattr(args, "uuid", None):
        uuids = [u.strip().upper() for u in args.uuid.split(",") if u.strip()]
        if uuids:
            _f["UUIDs"] = dbus.Array(uuids, signature="s")  # type: ignore[name-defined]
            if debug_mode:
                print_and_log(f"[classic-scan] Filtering for UUIDs: {', '.join(uuids)}", LOG__GENERAL)
    if args.rssi is not None:
        _f["RSSI"] = dbus.Int16(args.rssi)  # type: ignore[name-defined]
        if debug_mode:
            print_and_log(f"[classic-scan] RSSI threshold set to: {args.rssi} dBm", LOG__GENERAL)
    if args.pathloss is not None:
        _f["Pathloss"] = dbus.UInt16(args.pathloss)  # type: ignore[name-defined]
        if debug_mode:
            print_and_log(f"[classic-scan] Pathloss threshold set to: {args.pathloss} dB", LOG__GENERAL)

    try:
        adapter.set_discovery_filter(_f)
        log_level = LOG__GENERAL if debug_mode else LOG__DEBUG
        print_and_log("[classic-scan] Applied discovery filter: " + str(_f), log_level)
    except Exception as exc:
        log_level = LOG__GENERAL if debug_mode else LOG__DEBUG
        print_and_log(
            f"[classic-scan] SetDiscoveryFilter failed ({exc.__class__.__name__}: {exc}); proceeding without filter",
            log_level,
        )

    if debug_mode:
        print_and_log(f"[classic-scan] Starting scan for {args.timeout} seconds...", LOG__GENERAL)

    adapter.run_scan__timed(duration=args.timeout)

    if debug_mode:
        print_and_log("[classic-scan] Scan completed, processing results...", LOG__GENERAL)

    devices = [d for d in adapter.get_discovered_devices() if d["type"].lower() == "br/edr"]

    if not devices:
        print("No Classic devices found")
    else:
        if debug_mode:
            print_and_log(f"[classic-scan] Found {len(devices)} Classic BR/EDR devices", LOG__GENERAL)

        for d in devices:
            name = d["name"] or d["alias"] or "(unknown)"
            rssi = d.get("rssi")
            rssi_str = f"RSSI={rssi}" if rssi is not None else "RSSI=?"
            print(f"{d['address']}  Name={name}  {rssi_str}")

            if debug_mode:
                if d.get("device_class"):
                    try:
                        from bleep.ble_ops.common.conversion import format_device_class
                        class_info = format_device_class(d["device_class"])
                        print(f"  Class: 0x{d['device_class']:06x} ({class_info})")
                    except Exception:
                        print(f"  Class: 0x{d['device_class']:06x}")

                if "uuids" in d and d["uuids"]:
                    print(f"  UUIDs: {', '.join(d['uuids'])}")

                if "services" in d and d["services"]:
                    print(f"  Services: {len(d['services'])}")

                print()

    if devices:
        try:
            from bleep.core import observations as _obs_cscan
            for d in devices:
                addr = d.get("address")
                if not addr or addr == "??":
                    continue
                _cscan_info = {
                    "name": d.get("name") or d.get("alias"),
                    "rssi_last": d.get("rssi"),
                    "device_class": d.get("device_class"),
                    "addr_type": d.get("address_type"),
                    "device_type": "classic",
                }
                if d.get("tx_power") is not None:
                    _cscan_info["tx_power"] = int(d["tx_power"])
                if d.get("appearance") is not None:
                    _cscan_info["appearance"] = int(d["appearance"])
                if d.get("modalias"):
                    _cscan_info["modalias"] = str(d["modalias"])
                if d.get("icon"):
                    _cscan_info["icon"] = str(d["icon"])
                _obs_cscan.upsert_device(addr, **_cscan_info)
        except Exception as db_exc:
            print_and_log(f"[classic-scan] DB persistence warning: {db_exc}", LOG__DEBUG)

    return 0
