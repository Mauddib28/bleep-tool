"""Classic Bluetooth commands for debug mode.

Discovery / connection: cscan, cconnect, cservices, ckeep, csdp, pbap.
Data-exchange / OBEX:   see ``debug_classic_data.py`` (copen, csend, crecv,
                        craw, copp, cmap).
"""

from __future__ import annotations

import argparse
from typing import Dict, List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

from bleep.modes.debug_state import DebugState
from bleep.modes.debug_dbus import format_dbus_error, print_detailed_dbus_error


def cmd_cscan(args: List[str], state: DebugState) -> None:
    """Scan for BR/EDR devices using BlueZ discovery."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    adapter = _Adapter()
    if not adapter.is_ready():
        print("[-] Bluetooth adapter not ready")
        return

    print_and_log("[*] Scanning for Classic devices…", LOG__GENERAL)
    try:
        try:
            adapter.set_discovery_filter({"Transport": "bredr"})
        except Exception:
            pass

        adapter.run_scan__timed(duration=10)

        def _is_classic(dev: dict) -> bool:
            if "type" in dev:
                try:
                    return dev["type"].lower() == "br/edr"
                except Exception:
                    return False
            return dev.get("device_class") is not None

        raw_devices = adapter.get_discovered_devices()
        devices = [d for d in raw_devices if _is_classic(d)]

        if not devices:
            print("No Classic devices found")
            return

        print("\nAddress              Name (RSSI)")
        for d in devices:
            name = d["name"] or d["alias"] or "(unknown)"
            rssi = d.get("rssi", "?")
            print(f"{d['address']:17}  {name} ({rssi})")
        print()
    except Exception as exc:
        print_and_log(f"[-] Classic scan failed: {exc}", LOG__DEBUG)


def cmd_cconnect(args: List[str], state: DebugState) -> None:
    """Connect to a Classic device and enumerate RFCOMM services."""
    if not args:
        print("Usage: cconnect <MAC>")
        return

    mac = args[0]
    try:
        from bleep.ble_ops import connect_and_enumerate__bluetooth__classic as _c_enum
        print_and_log(f"[*] Classic connect {mac}…", LOG__GENERAL)
        dev, svc_map = _c_enum(mac)
    except Exception as exc:
        print_and_log(f"[-] Classic connect failed: {exc}", LOG__DEBUG)
        return

    if state.current_device and state.current_device.is_connected():
        try:
            state.current_device.disconnect()
        except Exception:
            pass

    state.current_device = dev
    state.current_mapping = svc_map
    state.current_mode = "classic"
    state.current_path = state.current_device._device_path

    print_and_log(f"[+] Connected to {mac} – {len(svc_map)} RFCOMM services", LOG__GENERAL)


def cmd_cservices(args: List[str], state: DebugState) -> None:
    """List RFCOMM service→channel map for connected Classic device."""
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected")
        return
    if not state.current_mapping:
        print("[-] No service map available (enumeration may have failed)")
        return

    print("\nRFCOMM Services (service → channel):")
    for svc, ch in state.current_mapping.items():
        print(f"  {svc:25} → {ch}")
    print()


def cmd_ckeep(args: List[str], state: DebugState) -> None:
    """Open/close keep-alive RFCOMM socket to prevent Classic ACL drop."""
    mac_token = None
    if args and not args[0].startswith("-") and ":" in args[0]:
        mac_token = args[0].strip()
        args = args[1:]

    parser = argparse.ArgumentParser(prog="ckeep", add_help=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("channel", nargs="?", help="RFCOMM channel number")
    group.add_argument("--first", action="store_true")
    group.add_argument("--svc")
    group.add_argument("--close", action="store_true")
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    if opts.close:
        if state.keepalive_sock:
            try:
                state.keepalive_sock.close()
            except Exception:
                pass
            state.keepalive_sock = None
            print("[+] Keep-alive socket closed")
        else:
            print("[*] No keep-alive socket open")
        return

    need_connect = (
        state.current_mode != "classic" or not state.current_device or
        (mac_token and state.current_device.mac_address.upper() != mac_token.upper())
    )
    if need_connect:
        if not mac_token:
            print("[-] No Classic device connected – supply MAC or run cconnect first")
            return
        print_and_log(f"[*] Quick connect to {mac_token} for keep-alive", LOG__GENERAL)
        try:
            from bleep.ble_ops import connect_and_enumerate__bluetooth__classic as _c_enum
            dev, svc_map = _c_enum(mac_token)
            state.current_device = dev
            state.current_mapping = svc_map
            state.current_mode = "classic"
            state.current_path = state.current_device._device_path
        except Exception as exc:
            error_str = format_dbus_error(exc)
            print(f"[-] Connect failed: {error_str}")
            print_and_log(f"[-] Connect failed: {error_str}", LOG__DEBUG)
            return

    if state.keepalive_sock:
        print("[*] Keep-alive already active – use 'ckeep --close' first")
        return

    if (opts.first or opts.svc) and not state.current_mapping:
        try:
            from bleep.ble_ops.classic_sdp import discover_services_sdp
            records = discover_services_sdp(state.current_device.mac_address)
            state.current_mapping = {
                (r["name"] or r["uuid"]): r["channel"]
                for r in records if r.get("channel")
            }
        except Exception as exc:
            error_str = format_dbus_error(exc)
            print(f"[-] SDP discovery failed: {error_str}")
            print_and_log(f"[-] SDP discovery failed: {error_str}", LOG__DEBUG)
            return

    channel: Optional[int] = None
    if opts.channel:
        try:
            channel = int(opts.channel)
        except ValueError:
            print("[-] CHANNEL must be numeric")
            return
    elif opts.svc:
        key = opts.svc.lower()
        for name, ch in state.current_mapping.items():
            if key in name.lower() or key in str(ch):
                channel = ch
                break
        if channel is None:
            print("[-] Service not found – run 'cservices' first")
            return
    elif opts.first:
        if state.current_mapping:
            channel = next(iter(state.current_mapping.values()))
        else:
            print("[-] Service map empty – run 'cservices' or specify channel")
            return

    if channel is None:
        print("[-] Could not resolve RFCOMM channel")
        return

    from bleep.ble_ops.classic_connect import classic_rfccomm_open
    try:
        state.keepalive_sock = classic_rfccomm_open(
            state.current_device.mac_address, channel, timeout=5.0,
        )
        print(f"[+] Keep-alive socket opened on RFCOMM channel {channel}")
    except Exception as exc:
        error_str = format_dbus_error(exc)
        print(f"[-] Failed to open keep-alive socket: {error_str}")
        print_and_log(f"[-] Failed to open keep-alive socket: {error_str}", LOG__DEBUG)
        state.keepalive_sock = None


def cmd_csdp(args: List[str], state: DebugState) -> None:
    """Perform SDP discovery on a Classic device."""
    if not args:
        print("Usage: csdp <MAC> [--connectionless] [--l2ping-count N] [--l2ping-timeout N]")
        return

    parser = argparse.ArgumentParser(prog="csdp", description="SDP discovery for Classic device")
    parser.add_argument("mac", help="Target MAC address")
    parser.add_argument("--connectionless", action="store_true")
    parser.add_argument("--l2ping-count", type=int, default=3)
    parser.add_argument("--l2ping-timeout", type=int, default=13)

    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    mac = opts.mac.strip().upper()

    try:
        from bleep.ble_ops.classic_sdp import discover_services_sdp, discover_services_sdp_connectionless

        if opts.connectionless:
            print_and_log(f"[*] Performing connectionless SDP discovery for {mac}...", LOG__GENERAL)
            print_and_log(
                f"[*] Checking reachability via l2ping (count={opts.l2ping_count}, timeout={opts.l2ping_timeout}s)...",
                LOG__DEBUG,
            )
            try:
                records = discover_services_sdp_connectionless(
                    mac, timeout=30,
                    l2ping_count=opts.l2ping_count, l2ping_timeout=opts.l2ping_timeout,
                )
            except RuntimeError as exc:
                error_str = str(exc)
                if "not reachable" in error_str.lower() or "unreachable" in error_str.lower():
                    print(f"[-] Device {mac} is not reachable: {error_str}")
                    print("[-] SDP query skipped. Ensure device is powered on and in range.")
                else:
                    print(f"[-] Connectionless SDP discovery failed: {exc}")
                print_and_log(f"[-] Connectionless SDP failed: {exc}", LOG__DEBUG)
                return
        else:
            print_and_log(f"[*] Performing SDP discovery for {mac}...", LOG__GENERAL)
            records = discover_services_sdp(mac, timeout=30, connectionless=False)

        if not records:
            print(f"[-] No SDP records found for {mac}")
            return

        print_and_log(f"[+] Found {len(records)} SDP record(s)", LOG__GENERAL)

        print("\nSDP Records:")
        print("=" * 80)
        for i, rec in enumerate(records, 1):
            print(f"\nRecord {i}:")
            if rec.get("name"):
                print(f"  Name: {rec['name']}")
            if rec.get("uuid"):
                print(f"  UUID: {rec['uuid']}")
            if rec.get("channel") is not None:
                print(f"  RFCOMM Channel: {rec['channel']}")
            if rec.get("handle") is not None:
                print(f"  Service Record Handle: 0x{rec['handle']:04X}")
            if rec.get("service_version") is not None:
                print(f"  Service Version: 0x{rec['service_version']:04X}")
            if rec.get("description"):
                print(f"  Description: {rec['description']}")
            if rec.get("profile_descriptors"):
                print("  Profile Descriptors:")
                for p in rec["profile_descriptors"]:
                    uuid = p.get("uuid", "Unknown")
                    ver = p.get("version")
                    if ver is not None:
                        print(f"    {uuid}: Version 0x{ver:04X}")
                    else:
                        print(f"    {uuid}: Version unknown")

        print("\n" + "=" * 80)

        svc_map: Dict[str, int] = {}
        for rec in records:
            if rec.get("channel") is not None:
                name = rec.get("name") or rec.get("uuid") or f"Service-{rec.get('handle', 'unknown')}"
                svc_map[name] = rec["channel"]

        if svc_map:
            print(f"\nService Map ({len(svc_map)} service(s)):")
            for svc, ch in svc_map.items():
                print(f"  {svc:25} → {ch}")

            if not state.current_device:
                print_and_log("[*] No device connected - service map not stored globally", LOG__DEBUG)
                print("[*] Use 'cconnect <MAC>' to connect and store service map")
            elif state.current_device.mac_address.upper() == mac:
                state.current_mapping = svc_map
                print_and_log(f"[*] Updated service map for connected device {mac}", LOG__DEBUG)

        print()

    except ImportError as exc:
        print(f"[-] Failed to import SDP module: {exc}")
        print_and_log(f"[-] Import error: {exc}", LOG__DEBUG)
    except Exception as exc:
        print(f"[-] SDP discovery failed: {exc}")
        print_and_log(f"[-] SDP discovery error: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def cmd_pbap(args: List[str], state: DebugState) -> None:
    """Dump phonebook via PBAP from connected Classic device."""
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    parser = argparse.ArgumentParser(prog="pbap", description="Dump phonebook via PBAP")
    parser.add_argument("--repos", default="PB")
    parser.add_argument("--format", choices=["vcard21", "vcard30"], default="vcard21")
    parser.add_argument("--auto-auth", action="store_true")
    parser.add_argument("--watchdog", type=int, default=8)
    parser.add_argument("--out")

    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    mac = state.current_device.mac_address

    pbap_channel = None
    if state.current_mapping:
        for key, ch in state.current_mapping.items():
            low = key.lower()
            if ("phonebook" in low or "pbap" in low
                    or low == "0x112f" or low == "112f"
                    or low == "0000112f-0000-1000-8000-00805f9b34fb"):
                pbap_channel = ch
                break

    if not pbap_channel:
        try:
            from bleep.ble_ops.classic_sdp import discover_services_sdp
            print_and_log("[*] PBAP not in service map, checking SDP records...", LOG__DEBUG)
            records = discover_services_sdp(mac, timeout=10)
            for rec in records:
                uuid = rec.get("uuid", "").lower()
                if "112f" in uuid or "pbap" in rec.get("name", "").lower():
                    pbap_channel = rec.get("channel")
                    if pbap_channel:
                        break
        except Exception as exc:
            print_and_log(f"[*] SDP check failed: {exc}", LOG__DEBUG)

    if not pbap_channel:
        print("[-] PBAP service not found on device. Run 'cservices' to check available services")
        return

    print_and_log(f"[*] PBAP channel found: {pbap_channel}", LOG__DEBUG)

    repos_arg = opts.repos.upper()
    try:
        from bleep.ble_ops.classic_pbap import pbap_dump_async, DEFAULT_PBAP_REPOS
        repos_tuple = DEFAULT_PBAP_REPOS if repos_arg == "ALL" else tuple(
            r.strip().upper() for r in repos_arg.split(",") if r.strip()
        )
    except ImportError as exc:
        print(f"[-] Failed to import PBAP module: {exc}")
        return

    try:
        print_and_log(
            f"[*] Starting PBAP dump for {mac} (repos: {', '.join(repos_tuple)}, format: {opts.format})...",
            LOG__GENERAL,
        )
        result = pbap_dump_async(mac, repos=repos_tuple, vcard_format=opts.format,
                                 auto_auth=opts.auto_auth, watchdog=opts.watchdog)

        if result.get("success"):
            print_and_log("[+] PBAP dump successful", LOG__GENERAL)
            data = result.get("data", {})
            if not data:
                print("[-] No data returned from PBAP dump")
                return

            single_repo = len(repos_tuple) == 1
            custom_out = opts.out and single_repo

            for repo, lines in data.items():
                if custom_out:
                    output_path = opts.out
                else:
                    base = mac.replace(":", "").lower()
                    output_path = f"/tmp/{base}_{repo}.vcf"

                try:
                    with open(output_path, "w", encoding="utf-8") as fh:
                        fh.writelines(lines)
                    entry_count = sum(1 for line in lines if "BEGIN:VCARD" in line)
                    print(f"[+] Saved {repo} → {output_path} ({len(lines)} lines, {entry_count} entries)")

                    if state.db_available and state.db_save_enabled and state.obs:
                        try:
                            import hashlib
                            with open(output_path, "rb") as fh:
                                vcf_bytes = fh.read()
                            vcf_hash = hashlib.sha1(vcf_bytes).hexdigest()
                            state.obs.upsert_pbap_metadata(mac, repo, entry_count, vcf_hash)
                            print_and_log("[*] PBAP metadata saved to database", LOG__DEBUG)
                        except Exception as db_exc:
                            print_and_log(f"[-] Failed to save PBAP metadata to database: {db_exc}", LOG__DEBUG)
                except Exception as file_exc:
                    print(f"[-] Failed to write {output_path}: {file_exc}")
                    print_and_log(f"[-] File write error: {file_exc}", LOG__DEBUG)
        else:
            error_msg = result.get("error", "Unknown error")
            print(f"[-] PBAP dump failed: {error_msg}")
            print_and_log(f"[-] PBAP dump failed: {error_msg}", LOG__DEBUG)

    except Exception as exc:
        print_and_log(f"[-] PBAP command failed: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)
        error_str = str(exc).lower()
        if "too short header" in error_str:
            print("[-] OBEX 'Too short header' error detected.")
            print("    This indicates stale OBEX state on the device.")
            print("    Restart the target device to clear OBEX buffers.")
            print("    Alternative: Disconnect and reconnect via 'bluetoothctl disconnect <MAC>'")
        elif "obex" in error_str or "obexd" in error_str:
            print("[-] OBEX service not available. Ensure bluetooth-obexd is running:")
            print("    sudo systemctl start bluetooth-obexd")
        elif "not found" in error_str or "no service" in error_str:
            print("[-] PBAP service not found. Ensure device is paired and trusted.")
