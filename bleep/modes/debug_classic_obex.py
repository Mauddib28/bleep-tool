"""OBEX profile commands for debug mode.

Commands: copp (Object Push), cmapinfo (MAP version/features), cmap (Message Access),
          cftp (File Transfer), csync (IrMC Synchronization), cbip (Basic Imaging).

Split from ``debug_classic_data.py`` to keep file sizes manageable.
"""

from __future__ import annotations

import argparse
from typing import Any, List, Optional

import os
import shutil

from bleep.modes.debug_state import DebugState
from bleep.modes.debug_dbus import format_dbus_error
from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR


# ---------------------------------------------------------------------------
# OBEX error hints (shared by copp / cmap / cftp / csync / cbip)
# ---------------------------------------------------------------------------


def _print_obex_error_hints(exc: Exception, *, operation: str = "") -> None:
    """Print common OBEX troubleshooting hints based on the error."""
    error_str = str(exc).lower()
    if "not support opp pull" in error_str or "vcf transfer failed" in error_str:
        print("[-] The device accepted the OBEX connection but did not deliver")
        print("    a vCard.  Many older devices support receiving files (push)")
        print("    but cannot serve their own business card via OPP pull.")
        print("    Try 'copp send <file>' to confirm OPP push works.")
    elif "not supported by this version" in error_str:
        print("[-] This obexd build does not implement ExchangeBusinessCards.")
        print("    Use separate 'copp send' and 'copp pull' commands instead.")
    elif "transfer object removed" in error_str or "unknownobject" in error_str:
        if "map" in operation:
            print("[-] The MAP message handle was not found on the remote device.")
            print("    Ensure the handle is a valid numeric ID from 'cmap list <folder>'.")
        else:
            print("[-] Transfer was torn down by obexd — remote device rejected or")
            print("    failed the data transfer after accepting the OBEX connection.")
            if "pull" in operation:
                print("    Try 'copp send <file>' to verify basic OPP connectivity.")
    elif "bad request" in error_str:
        if "map" in operation:
            print("[-] OBEX Bad Request — the remote device rejected the MAP request.")
            print("    Common causes:")
            print("    • Listing messages at root (use a subfolder: telecom/msg/inbox)")
            print("    • Invalid folder path (use 'cmap folders' to browse hierarchy)")
        else:
            print("[-] OBEX Bad Request — the remote device rejected the request.")
    elif "too short header" in error_str:
        print("[-] Stale OBEX state – restart the target device to clear buffers.")
    elif "timed out" in error_str or "timeout" in error_str:
        print("[-] The remote device did not respond in time. Possible causes:")
        print("    1. Device screen is locked/asleep — wake the phone and retry")
        print("    2. Large folder (e.g. inbox) — the device needs time to build the listing")
        print("    3. Disconnect and reconnect: 'disconnect' then 'connect <MAC>'")
        print("    4. Restart the target device to clear stale OBEX state")
        print("    Tip: wake the target device before running MAP commands on large folders.")
    elif "no such property" in error_str:
        print("[-] The requested property is not available in this BlueZ/obexd version.")
    elif "not implemented" in error_str:
        print("[-] The remote device (or this BlueZ/obexd build) does not support")
        print("    this MAP operation.  This is a device/stack limitation, not a")
        print("    connectivity issue.")
    elif "unknownmethod" in error_str or "unknown method" in error_str:
        if "createsession" in error_str:
            print("[-] CreateSession failed — possible D-Bus signature mismatch.")
            print("    Ensure bluetooth-obexd is running and up to date:")
            print("    systemctl --user restart obex")
        else:
            print("[-] The requested D-Bus method is not available in this BlueZ version.")
    elif "service unavailable" in error_str:
        print("[-] The remote device rejected this operation (OBEX 'Service Unavailable').")
        if "map" in operation:
            print("    Possible causes:")
            print("    • readStatus change on a sent/draft message (only meaningful for inbox)")
            print("    • The device may not support this status operation on the current folder")
            print("    Try on an inbox message: cmap list telecom/msg/inbox, then cmap read <handle>")
    elif "noreply" in error_str or "did not receive a reply" in error_str:
        print("[-] D-Bus method call timed out (no reply from obexd).")
        if "map" in operation:
            print("    The device may be slow to respond for large folders (e.g. inbox).")
            print("    BLEEP uses extended timeouts (120s) for ListMessages — if this still")
            print("    times out, try a smaller folder or retry after the device has had time")
            print("    to process.  Check 'obexd' and 'btmon' logs for transfer activity.")
    elif "obex" in error_str or "obexd" in error_str:
        print("[-] Ensure bluetooth-obexd is running:")
        print("    systemctl --user start obex")
    elif "not found" in error_str or "no service" in error_str:
        if "map" in operation:
            print("[-] Folder or object not found on the remote device.")
            print("    Use 'cmap folders' to list available folders, then navigate with:")
            print("      cmap list telecom/msg/inbox")
        else:
            print("[-] Service not found. Ensure device is paired and trusted.")


# ---------------------------------------------------------------------------
# copp – Object Push Profile (send file / pull business card)
# ---------------------------------------------------------------------------


def _extract_opp_channel(mapping) -> Optional[int]:
    """Extract OPP RFCOMM channel from the Classic service mapping."""
    if not mapping:
        return None
    for key, entry in mapping.items():
        low = key.lower()
        if "1105" in low or "object push" in low or "opp" in low:
            if isinstance(entry, int):
                return entry
            if isinstance(entry, dict):
                return entry.get("channel")
    return None


def _resolve_opp_channel(mapping, mac: str) -> Optional[int]:
    """Resolve OPP RFCOMM channel: SDP cache first, then targeted sdptool search."""
    channel = _extract_opp_channel(mapping)
    if channel is not None:
        return channel
    try:
        from bleep.ble_ops.classic.sdp import discover_service_channel
        channel = discover_service_channel(mac, "0x1105")
        if channel is not None:
            print(f"[*] OPP RFCOMM channel {channel} discovered via sdptool search")
    except Exception:
        pass
    return channel


def _obex_staging_path(filename: str) -> str:
    """Return a staging path inside obexd's AppArmor-safe write area."""
    return str(OBEX_STAGING_DIR / filename)


def _stage_and_move(staging_path: str, final_dir=None) -> str:
    """Move a file from the obexd staging area to the final receive directory.

    obexd writes to ``~/.cache/obexd/`` (AppArmor-safe).  After a
    successful transfer, BLEEP moves the file to the user's receive dir
    (``/tmp/bleep_received/`` by default) for auto-cleanup on reboot.

    Returns the final file path.
    """
    dest_dir = final_dir or OBEX_RECEIVE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = str(dest_dir / os.path.basename(staging_path))
    if os.path.exists(staging_path):
        shutil.move(staging_path, dest)
    return dest


def _default_pull_dest(mac: str) -> tuple:
    """Return (staging_path, final_path) for ``copp pull``.

    Stage 1: obexd writes to ``OBEX_STAGING_DIR`` (AppArmor-safe).
    Stage 2: BLEEP moves to ``OBEX_RECEIVE_DIR`` after transfer.
    """
    filename = f"{mac.replace(':', '').upper()}_card.vcf"
    staging = _obex_staging_path(filename)
    final = str(OBEX_RECEIVE_DIR / filename)
    return staging, final


def cmd_copp(args: List[str], state: DebugState) -> None:
    """Send a file, pull a business card, or exchange cards via OPP.

    OPP (Object Push Profile) supports push and pull of simple objects
    such as vCards.  It does **not** support remote file listing — use
    ``cftp`` (FTP profile, UUID 0x1106) for directory browsing.
    """
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    if not args:
        print("Usage:")
        print("  copp send <filepath>         - Send a file via OPP")
        print("  copp pull [dest.vcf]         - Pull default business card")
        print("  copp exchange <local.vcf> [dest.vcf] - Exchange business cards")
        print()
        print("Note: OPP has no file listing. Use 'cftp' for directory browsing.")
        return

    subcmd = args[0].lower()
    mac = state.current_device.mac_address

    from bleep.ble_ops.classic.opp import detect_opp_service

    if not detect_opp_service(state.current_mapping):
        print("[!] OPP service (0x1105) not detected in service map – attempting anyway")

    opp_channel = _resolve_opp_channel(state.current_mapping, mac)
    if opp_channel:
        print(f"[*] Using OPP RFCOMM channel {opp_channel}")

    if subcmd == "send":
        if len(args) < 2:
            print("Usage: copp send <filepath>")
            return
        filepath = args[1]
        try:
            from bleep.ble_ops.classic.opp import send_file
            result = send_file(mac, filepath, channel=opp_channel)
            transferred = result.get("transferred", "?")
            size = result.get("size", "?")
            print(f"[+] OPP send complete: {transferred}/{size} bytes transferred")
        except FileNotFoundError as exc:
            print(f"[-] {exc}")
        except Exception as exc:
            print(f"[-] OPP send failed: {exc}")
            _print_obex_error_hints(exc, operation="send")

    elif subcmd == "pull":
        if len(args) > 1:
            dest = args[1]
        else:
            staging, _ = _default_pull_dest(mac)
            dest = staging
        try:
            from bleep.ble_ops.classic.opp import pull_business_card
            result_path = pull_business_card(mac, dest, channel=opp_channel)
            size = result_path.stat().st_size if result_path.exists() else 0
            final = _stage_and_move(str(result_path)) if len(args) <= 1 else str(result_path)
            print(f"[+] Business card saved → {final} ({size} bytes)")
        except Exception as exc:
            print(f"[-] OPP pull failed: {exc}")
            _print_obex_error_hints(exc, operation="pull")

    elif subcmd == "exchange":
        if len(args) < 2:
            print("Usage: copp exchange <local_vcard.vcf> [dest.vcf]")
            return
        client_vcf = args[1]
        if len(args) > 2:
            dest = args[2]
        else:
            staging, _ = _default_pull_dest(mac)
            dest = staging
        try:
            from bleep.ble_ops.classic.opp import exchange_business_cards
            result_path = exchange_business_cards(
                mac, client_vcf, dest, channel=opp_channel,
            )
            final = _stage_and_move(str(result_path)) if len(args) <= 2 else str(result_path)
            print(f"[+] Exchange complete — remote card saved → {final}")
        except FileNotFoundError as exc:
            print(f"[-] {exc}")
        except Exception as exc:
            print(f"[-] OPP exchange failed: {exc}")
            _print_obex_error_hints(exc, operation="exchange")

    else:
        print(f"[-] Unknown OPP sub-command: {subcmd}")
        print("    Use: copp send <file> | copp pull [dest] | copp exchange <local> [dest]")


# ---------------------------------------------------------------------------
# cmap – Message Access Profile
# ---------------------------------------------------------------------------


def _print_folder_tree(tree: list, indent: int = 0) -> None:
    """Render a MAP folder tree with indentation."""
    for node in tree:
        print(f"{' ' * indent}{node['name']}/")
        if node.get("children"):
            _print_folder_tree(node["children"], indent + 2)


def _collect_leaf_paths(tree: list, prefix: str = "") -> List[str]:
    """Flatten a folder tree into a sorted list of leaf-node paths.

    Delegates to :func:`bleep.ble_ops.classic.map.collect_leaf_paths`.
    """
    from bleep.ble_ops.classic.map import collect_leaf_paths
    return collect_leaf_paths(tree, prefix)


def _suggest_map_leaf_folders(mac: str, instance: Optional[int]) -> None:
    """On error, try to enumerate the MAP tree and suggest valid message folders."""
    try:
        from bleep.ble_ops.classic.map import list_folder_tree
        tree = list_folder_tree(mac, instance=instance)
        if not tree:
            return
        leaves = _collect_leaf_paths(tree)
        if leaves:
            print("\n[*] Available message folders on this device:")
            for p in sorted(leaves):
                print(f"      cmap list {p}")
    except Exception:
        pass


def _validate_bmsg_length(text: str, raw: bytes) -> None:
    """Warn if the bMessage has LF-only line endings or a LENGTH mismatch.

    The MAP spec defines LENGTH as the byte count from
    ``BEGIN:MSG\\r\\n`` through ``END:MSG\\r\\n`` (inclusive) and
    mandates CRLF line endings throughout the bMessage.

    When issues are detected, a warning is printed.  The operations-layer
    ``push_message()`` auto-normalizes before sending, so the push will
    still succeed — the warning is informational.
    """
    import re

    bbody_start = raw.find(b"BEGIN:BBODY")
    if bbody_start < 0:
        return
    bbody_section = raw[bbody_start:]
    has_bare_lf = b"\n" in bbody_section and b"\r\n" not in bbody_section
    if has_bare_lf:
        print("[!] bMessage uses LF line endings; MAP spec requires CRLF.")
        print("    BLEEP will auto-normalize before pushing.")

    length_m = re.search(r"(?i)^LENGTH:\s*(\d+)", text, re.MULTILINE)
    if not length_m:
        return
    declared = int(length_m.group(1))
    upper = text.upper()
    begin_idx = upper.find("BEGIN:MSG")
    end_idx = upper.find("END:MSG")
    if begin_idx < 0 or end_idx < 0:
        return
    end_idx = upper.find("\n", end_idx)
    if end_idx < 0:
        end_idx = len(text)
    else:
        end_idx += 1
    actual = len(raw[begin_idx:end_idx])
    if declared != actual:
        print(f"[!] Warning: bMessage LENGTH field is {declared} but actual")
        print(f"    content (BEGIN:MSG … END:MSG) is {actual} bytes.")
        print(f"    BLEEP will auto-normalize LENGTH before pushing.")


_last_map_folder: Optional[str] = None


def _require_map_folder(explicit: Optional[str]) -> Optional[str]:
    """Return the MAP folder to use for handle-based operations.

    Prefers *explicit* (user-provided), falls back to ``_last_map_folder``
    (set by a prior ``cmap list``).  Returns ``None`` if neither is available
    and prints guidance.
    """
    if explicit:
        return explicit
    if _last_map_folder:
        return _last_map_folder
    print("[-] No folder context — run 'cmap list <folder>' first so BLEEP")
    print("    can materialise message handles within an OBEX session.")
    return None


def cmd_cmapinfo(args: List[str], state: DebugState) -> None:
    """Query SDP for MAP-MSE version, features, and BlueZ compatibility info."""
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    mac = state.current_device.mac_address

    from bleep.ble_ops.classic.sdp import discover_services_sdp
    from bleep.bt_ref.constants import (
        MAP_MSE_UUID_SHORT, MAP_UUID_SHORT,
        MAP_SDP_ATTR_SUPPORTED_FEATURES, MAP_SDP_ATTR_SUPPORTED_MESSAGE_TYPES,
        MAP_SDP_ATTR_MAS_INSTANCE_ID,
        decode_map_supported_features, decode_map_message_types,
    )

    _MAP_SHORTS = (MAP_MSE_UUID_SHORT.lower(), MAP_UUID_SHORT.lower(), "1132", "1134")

    print(f"[*] Querying SDP records for MAP services on {mac}...")
    try:
        records = discover_services_sdp(mac)
    except Exception as exc:
        print(f"[-] SDP discovery failed: {exc}")
        return

    map_records = []
    for rec in records:
        uuid_str = (rec.get("uuid") or "").lower()
        name_str = (rec.get("name") or "").lower()
        if any(s in uuid_str for s in _MAP_SHORTS) or "message" in name_str:
            map_records.append(rec)

    if not map_records:
        print("[!] No MAP service records found on remote device")
        return

    print(f"[+] Found {len(map_records)} MAP service record(s):\n")

    for i, rec in enumerate(map_records, 1):
        print(f"--- MAP Record #{i} ---")
        print(f"  Name:    {rec.get('name', 'N/A')}")
        print(f"  UUID:    {rec.get('uuid', 'N/A')}")
        print(f"  Channel: {rec.get('channel', 'N/A')}")
        if rec.get("handle") is not None:
            print(f"  Handle:  0x{rec['handle']:04x}")

        if rec.get("mas_instance_id") is not None:
            print(f"  MAS Instance ID: {rec['mas_instance_id']}")

        profile_ver = None
        if rec.get("profile_descriptors"):
            for pd in rec["profile_descriptors"]:
                pd_uuid = (pd.get("uuid") or "").lower()
                if any(s in pd_uuid for s in _MAP_SHORTS):
                    ver = pd.get("version")
                    if ver is not None:
                        major = (ver >> 8) & 0xFF
                        minor = ver & 0xFF
                        profile_ver = f"{major}.{minor}"
                        print(f"  MAP Profile Version: {profile_ver} (0x{ver:04x})")

        if rec.get("supported_message_types") is not None:
            mt = rec["supported_message_types"]
            names = decode_map_message_types(mt)
            print(f"  Supported Message Types: 0x{mt:02x} ({', '.join(names) if names else 'none'})")

        if rec.get("supported_features") is not None:
            sf = rec["supported_features"]
            names = decode_map_supported_features(sf)
            print(f"  MapSupportedFeatures: 0x{sf:08x}")
            for name in names:
                print(f"    - {name}")
        else:
            print("  MapSupportedFeatures: not advertised in SDP")

        print()

    print("=" * 60)
    print("BlueZ MAP Compatibility Notes:")
    print("-" * 60)
    print("  BlueZ obexd acts as a MAP 1.0 client (MCE).")
    print("  It does NOT send MapSupportedFeatures in the OBEX Connect")
    print("  request, nor does it negotiate MAP version with the MSE.")
    print()
    print("  Android devices running MAP >= 1.2 may detect the absence")
    print("  of the MapSupportedFeatures header and trigger a 'Remote")
    print("  Message Access Feature Downgrade' notification on the phone.")
    print()
    print("  This is a BlueZ/obexd limitation, not a BLEEP issue.")
    print("  MAP operations (folder listing, message retrieval) still")
    print("  work under the downgraded (MAP 1.0) feature set.")
    print()
    if any(r.get("supported_features") is not None for r in map_records):
        print("  The remote device advertises MapSupportedFeatures,")
        print("  confirming it expects MAP >= 1.2 negotiation.")
    print("=" * 60)


def cmd_cmap(args: List[str], state: DebugState) -> None:
    """Interact with remote device messages via Message Access Profile."""
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    if not args:
        print("Usage:")
        print("  cmap folders                           - List message folders")
        print("  cmap peek                              - Quick 1-msg probe of all folders")
        print("  cmap list <folder> [--count N] [--offset M]")
        print("                                         - List messages in folder")
        print("  cmap get <handle> [dest.txt]           - Download & display message contents")
        print("  cmap push <filepath> [folder]          - Push/send a message (bMessage format)")
        print("  cmap download-all [dest] [--folders f1,f2] [--count N]")
        print("                                         - Download all messages from device")
        print("  cmap push-all <dir|glob> [folder] [--dry-run] [--delay N]")
        print("                                         - Push all .bmsg files to device")
        print("  cmap inbox                             - Trigger inbox update")
        print("  cmap props <handle>                    - Message properties")
        print("  cmap read <handle> [true|false]        - Toggle read/unread status flag")
        print("  cmap delete <handle> [true|false]      - Toggle deleted/undeleted status flag")
        print("  cmap types                             - Supported message types")
        print("  cmap fields                            - Available filter fields")
        print("  cmap monitor start|stop                - MNS notification watch")
        print("  cmap instances                         - List MAS instances (SDP)")
        print("")
        print("  Note: 'get' downloads the full message; 'read' only toggles the read flag.")
        print("  Tip:  wake/unlock the target device before querying large folders.")
        print("        Use 'cmap peek' or 'cmap list <folder> --count N' to avoid timeouts")
        print("        on large folders (e.g. inbox).  BlueZ obexd must buffer the entire")
        print("        listing before responding; --count limits the MAS response size.")
        print("")
        print("  Handle commands (get/props/read/delete) use the folder from the last")
        print("  'cmap list' call.  Run 'cmap list <folder>' before accessing handles.")
        print("  All sub-commands accept --instance <channel> to target a specific MAS.")
        return

    instance: Optional[int] = None
    filtered_args: List[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--instance" and i + 1 < len(args):
            try:
                instance = int(args[i + 1])
            except ValueError:
                print(f"[-] Invalid instance channel: {args[i + 1]}")
                return
            i += 2
        else:
            filtered_args.append(args[i])
            i += 1
    args = filtered_args

    if not args:
        print("[-] Missing sub-command after --instance")
        return

    subcmd = args[0].lower()
    mac = state.current_device.mac_address

    from bleep.ble_ops.classic.map import detect_map_service

    if not detect_map_service(state.current_mapping):
        print("[!] MAP service (0x1132/0x1134) not detected in service map – attempting anyway")

    if subcmd == "folders":
        try:
            from bleep.ble_ops.classic.map import list_folder_tree
            tree = list_folder_tree(mac, instance=instance)
            if not tree:
                print("[*] No folders found")
                return
            print("\nMAP Folder Tree:")
            _print_folder_tree(tree, indent=2)
            print()
        except Exception as exc:
            print_and_log(
                f"[-] MAP list-folders failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP list-folders failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "peek":
        import dbus as _dbus
        from bleep.ble_ops.classic.map import list_folder_tree, list_messages
        try:
            tree = list_folder_tree(mac, instance=instance)
        except Exception as exc:
            print(f"[-] Cannot enumerate folders: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")
            return
        leaves = _collect_leaf_paths(tree)
        if not leaves:
            print("[*] No message folders found")
            return
        print(f"[MAP] Probing {len(leaves)} message folder(s) (MaxCount=1 each)…\n")
        ok_count = 0
        for leaf in sorted(leaves):
            try:
                msgs = list_messages(
                    mac, leaf,
                    filters={"MaxCount": _dbus.UInt16(1)},
                    instance=instance,
                )
                ok_count += 1
                if msgs:
                    m = msgs[0]
                    handle = (m.get("path", "").rsplit("message", 1)[-1]
                              if "path" in m else "?")
                    read_flag = "R" if m.get("Read", False) else " "
                    subject = (m.get("Subject") or "(no subject)")[:40]
                    print(f"  {leaf:<30} [{read_flag}] {handle}  {subject}")
                else:
                    print(f"  {leaf:<30} (empty)")
            except Exception as exc:
                err = format_dbus_error(exc)
                print(f"  {leaf:<30} ERROR: {err}")
        print(f"\n[+] {ok_count}/{len(leaves)} folders accessible")

    elif subcmd == "list":
        import dbus as _dbus
        global _last_map_folder

        folder = ""
        max_count: Optional[int] = None
        offset: Optional[int] = None
        j = 1
        while j < len(args):
            if args[j] == "--count" and j + 1 < len(args):
                try:
                    max_count = int(args[j + 1])
                except ValueError:
                    print(f"[-] Invalid --count value: {args[j + 1]}")
                    return
                j += 2
            elif args[j] == "--offset" and j + 1 < len(args):
                try:
                    offset = int(args[j + 1])
                except ValueError:
                    print(f"[-] Invalid --offset value: {args[j + 1]}")
                    return
                j += 2
            elif not folder:
                folder = args[j]
                j += 1
            else:
                print(f"[-] Unexpected argument: {args[j]}")
                return

        if not folder:
            print("[!] Cannot list messages at MAP root — the root contains only")
            print("    folder metadata, not messages.  Specify a message folder:")
            print("      cmap list telecom/msg/inbox")
            print("      cmap list telecom/msg/sent")
            print("    Use 'cmap folders' to browse the folder hierarchy.")
            return

        for token in folder.strip().rstrip("/").split("/"):
            if token in (".", ".."):
                print(f"[-] OBEX MAP does not support '{token}' path components —")
                print("    use an explicit folder path like 'telecom/msg/inbox'")
                return

        filters: Optional[dict] = None
        if max_count is not None or offset is not None:
            filters = {}
            if max_count is not None:
                filters["MaxCount"] = _dbus.UInt16(max_count)
            if offset is not None:
                filters["Offset"] = _dbus.UInt16(offset)

        try:
            from bleep.ble_ops.classic.map import list_messages
            messages = list_messages(
                mac, folder, filters=filters, instance=instance,
            )
            _last_map_folder = folder
            if not messages:
                print(f"[*] No messages in '{folder}'")
                return
            label = f"Messages ({len(messages)})"
            if max_count is not None or offset is not None:
                parts = []
                if offset is not None:
                    parts.append(f"offset={offset}")
                if max_count is not None:
                    parts.append(f"count={max_count}")
                label += f" [{', '.join(parts)}]"
            print(f"\n{label}:")
            for m in messages:
                handle = m.get("path", "").rsplit("message", 1)[-1] if "path" in m else "?"
                subject = m.get("Subject", "(no subject)")
                sender = m.get("Sender", "")
                read_flag = "R" if m.get("Read", False) else " "
                print(f"  [{read_flag}] {handle:>6}  {sender:20}  {subject}")
            print()
        except ValueError as exc:
            print_and_log(f"[-] MAP list-messages ValueError: {exc}", LOG__DEBUG)
            print(f"[-] {exc}")
        except Exception as exc:
            print_and_log(
                f"[-] MAP list-messages failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP list-messages failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")
            if "bad request" in str(exc).lower():
                _suggest_map_leaf_folders(mac, instance)

    elif subcmd == "get":
        if len(args) < 2:
            print("Usage: cmap get <handle> [dest.txt]")
            return
        handle = args[1]
        folder = _require_map_folder(None)
        if folder is None:
            return
        filename = f"{mac.replace(':', '').upper()}_msg_{handle}.txt"
        if len(args) > 2:
            dest = args[2]
            use_staging = False
        else:
            dest = _obex_staging_path(filename)
            use_staging = True
        try:
            from bleep.ble_ops.classic.map import get_message
            result = get_message(mac, handle, dest, folder=folder, instance=instance)
            final = _stage_and_move(str(result)) if use_staging else str(result)
            print(f"[+] Message saved → {final}")
            if result.exists():
                content = result.read_text(errors="replace")
                if len(content) < 2000:
                    print(content)
        except Exception as exc:
            print_and_log(
                f"[-] MAP get-message failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP get-message failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")
            err_lower = str(exc).lower()
            if "unknownobject" in err_lower or "does not exist" in err_lower:
                print(f"\n    Current folder context: '{folder}'")
                print("    Handle-based commands use the folder from the last 'cmap list'")
                print("    call.  If this handle belongs to a different folder, re-run:")
                print(f"      cmap list <correct_folder>")
                print(f"      cmap get {handle}")

    elif subcmd == "push":
        if len(args) < 2:
            print("Usage: cmap push <filepath> [folder]")
            return
        filepath = args[1]
        folder = args[2] if len(args) > 2 else "telecom/msg/outbox"
        if os.path.isfile(filepath):
            try:
                with open(filepath, "rb") as _f:
                    raw = _f.read()
                text = raw.decode("utf-8", errors="replace")
                if not text.lstrip().upper().startswith("BEGIN:BMSG"):
                    print("[!] Warning: file does not appear to be in bMessage format")
                    print("    (expected BEGIN:BMSG header per MAP spec / RFC 6474).")
                    print("    The OBEX transfer may succeed but the device is likely")
                    print("    to silently discard the content.")
                else:
                    _validate_bmsg_length(text, raw)
            except Exception:
                pass
        try:
            from bleep.ble_ops.classic.map import push_message
            push_message(mac, filepath, folder, instance=instance)
            print("[+] Message pushed successfully")
        except FileNotFoundError as exc:
            print(f"[-] {exc}")
        except Exception as exc:
            print_and_log(
                f"[-] MAP push failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP push failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "download-all":
        dest_dir: Optional[str] = None
        dl_folders: Optional[List[str]] = None
        dl_count: Optional[int] = None
        j = 1
        while j < len(args):
            if args[j] == "--folders" and j + 1 < len(args):
                dl_folders = [f.strip() for f in args[j + 1].split(",") if f.strip()]
                j += 2
            elif args[j] == "--count" and j + 1 < len(args):
                try:
                    dl_count = int(args[j + 1])
                except ValueError:
                    print(f"[-] Invalid --count value: {args[j + 1]}")
                    return
                j += 2
            elif dest_dir is None and not args[j].startswith("--"):
                dest_dir = args[j]
                j += 1
            else:
                print(f"[-] Unexpected argument: {args[j]}")
                return

        if dest_dir is None:
            mac_clean = mac.replace(":", "").upper()
            dest_dir = str(OBEX_RECEIVE_DIR / f"{mac_clean}_map_dump")

        try:
            from bleep.ble_ops.classic.map import download_all_messages

            def _dl_progress(folder: str, cur: int, total: int, path: str) -> None:
                short = folder.replace("telecom/msg/", "")
                print(f"  [{cur}/{total}] {short} → {path}")

            print(f"[MAP] Downloading all messages → {dest_dir}")
            results = download_all_messages(
                mac, dest_dir,
                folders=dl_folders,
                max_count=dl_count,
                instance=instance,
                progress_cb=_dl_progress,
            )
            total_msgs = 0
            total_bytes = 0
            print()
            for fld, paths in sorted(results.items()):
                fld_short = fld.replace("telecom/msg/", "") or fld
                fld_bytes = sum(p.stat().st_size for p in paths if p.exists())
                total_msgs += len(paths)
                total_bytes += fld_bytes
                if paths:
                    print(f"  {fld_short:<25} {len(paths):>4} msgs  {fld_bytes / 1024:>7.1f} KB")
                else:
                    print(f"  {fld_short:<25}    0 msgs")
            print(f"\n[+] Download complete: {total_msgs} messages ({total_bytes / 1024:.1f} KB)")
        except Exception as exc:
            print_and_log(
                f"[-] MAP download-all failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP download-all failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "push-all":
        if len(args) < 2:
            print("Usage: cmap push-all <dir_or_glob> [folder] [--dry-run] [--delay N]")
            return

        import glob as _glob

        push_path = args[1]
        push_folder = "telecom/msg/outbox"
        push_dry = False
        push_delay: Optional[float] = None
        j = 2
        while j < len(args):
            if args[j] == "--dry-run":
                push_dry = True
                j += 1
            elif args[j] == "--delay" and j + 1 < len(args):
                try:
                    push_delay = float(args[j + 1])
                except ValueError:
                    print(f"[-] --delay requires a number, got '{args[j + 1]}'")
                    return
                j += 2
            elif not args[j].startswith("--"):
                push_folder = args[j]
                j += 1
            else:
                print(f"[-] Unexpected argument: {args[j]}")
                return

        if os.path.isdir(push_path):
            files = sorted(_glob.glob(os.path.join(push_path, "*.bmsg")))
        else:
            files = sorted(_glob.glob(push_path))

        if not files:
            print(f"[*] No .bmsg files found matching '{push_path}'")
            return

        print(f"[MAP] Found {len(files)} .bmsg file(s)")
        if push_dry:
            print("[MAP] Dry-run mode — validating only, no pushes")

        from bleep.ble_ops.classic.map import push_all_messages

        def _push_progress(fp: str, cur: int, total: int, status: str) -> None:
            print(f"  [{cur}/{total}] {os.path.basename(fp)} → {status}")

        delay_kwargs: Dict[str, float] = {}
        if push_delay is not None:
            delay_kwargs["delay"] = push_delay

        try:
            results = push_all_messages(
                mac, files, push_folder,
                instance=instance,
                dry_run=push_dry,
                progress_cb=_push_progress,
                **delay_kwargs,
            )
            ok = sum(1 for s in results.values() if s.startswith("ok"))
            failed = sum(1 for s in results.values() if s.startswith("FAILED"))
            skipped = sum(1 for s in results.values() if s.startswith("SKIP"))
            label = "Dry-run" if push_dry else "Push"
            print(f"\n[+] {label} complete: {ok} succeeded, {failed} failed, {skipped} skipped")
        except Exception as exc:
            print_and_log(
                f"[-] MAP push-all failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP push-all failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "inbox":
        try:
            from bleep.ble_ops.classic.map import update_inbox
            update_inbox(mac, instance=instance)
            print("[+] Inbox update requested")
        except Exception as exc:
            print_and_log(
                f"[-] MAP inbox-update failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP inbox-update failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "props":
        if len(args) < 2:
            print("Usage: cmap props <handle>")
            print("  <handle> is a numeric message ID from 'cmap list <folder>'")
            return
        handle = args[1]
        if not handle.isalnum():
            print(f"[-] Invalid handle '{handle}' — expected a numeric message ID")
            print("    (e.g. '000001').  Use 'cmap list <folder>' to discover handles.")
            return
        folder = _require_map_folder(None)
        if folder is None:
            return
        try:
            from bleep.dbuslayer.obex_map import MapSession
            with MapSession(mac, instance=instance) as sess:
                props = sess.get_message_properties(handle, folder=folder)
            for k, v in props.items():
                print(f"  {k}: {v}")
        except Exception as exc:
            print_and_log(
                f"[-] MAP get-properties failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP get-properties failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "read":
        if len(args) < 2:
            print("Usage: cmap read <handle> [true|false]")
            return
        handle = args[1]
        folder = _require_map_folder(None)
        if folder is None:
            return
        flag = args[2].lower() != "false" if len(args) > 2 else True
        if folder and "inbox" not in folder.lower():
            print(f"[!] Warning: readStatus is typically only meaningful for inbox messages.")
            print(f"    Current folder context is '{folder}'.")
            print(f"    Some devices reject readStatus changes on sent/draft/outbox messages.")
        try:
            from bleep.dbuslayer.obex_map import MapSession
            with MapSession(mac, instance=instance) as sess:
                sess.set_message_read(handle, flag, folder=folder)
            print(f"[+] Message {handle} marked {'read' if flag else 'unread'}")
        except Exception as exc:
            print_and_log(
                f"[-] MAP set-read failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP set-read failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "delete":
        if len(args) < 2:
            print("Usage: cmap delete <handle> [true|false]")
            return
        handle = args[1]
        folder = _require_map_folder(None)
        if folder is None:
            return
        flag = args[2].lower() != "false" if len(args) > 2 else True
        try:
            from bleep.dbuslayer.obex_map import MapSession
            with MapSession(mac, instance=instance) as sess:
                sess.set_message_deleted(handle, flag, folder=folder)
            print(f"[+] Message {handle} marked {'deleted' if flag else 'undeleted'}")
        except Exception as exc:
            print_and_log(
                f"[-] MAP set-deleted failed: {format_dbus_error(exc)}", LOG__DEBUG,
            )
            print(f"[-] MAP set-deleted failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "types":
        try:
            from bleep.ble_ops.classic.map import get_supported_types
            types = get_supported_types(mac, instance=instance)
            if not types:
                print("[*] No supported types reported (property may not be"
                      " available in this BlueZ version)")
            else:
                print("Supported message types:")
                for t in types:
                    print(f"  {t}")
        except Exception as exc:
            print_and_log(
                f"[-] MAP get-supported-types failed: {format_dbus_error(exc)}",
                LOG__DEBUG,
            )
            print(f"[-] MAP get-supported-types failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "fields":
        try:
            from bleep.ble_ops.classic.map import list_filter_fields
            fields = list_filter_fields(mac, instance=instance)
            if not fields:
                print("[*] No filter fields reported")
            else:
                print("Available filter fields:")
                for f in fields:
                    print(f"  {f}")
        except Exception as exc:
            print_and_log(
                f"[-] MAP list-filter-fields failed: {format_dbus_error(exc)}",
                LOG__DEBUG,
            )
            print(f"[-] MAP list-filter-fields failed: {format_dbus_error(exc)}")
            _print_obex_error_hints(exc, operation="map")

    elif subcmd == "monitor":
        action = args[1].lower() if len(args) > 1 else ""
        if action == "start":
            from bleep.ble_ops.classic.map import start_message_monitor

            def _mns_print(path: str, props: dict) -> None:
                print(f"\n[MNS] {path}")
                for k, v in props.items():
                    print(f"      {k}: {v}")
                print()

            try:
                start_message_monitor(mac, _mns_print, instance=instance)
                print("[+] MNS monitor started – notifications will appear here")
                print("    Use 'cmap monitor stop' to stop")
            except Exception as exc:
                print_and_log(
                    f"[-] MAP monitor start failed: {format_dbus_error(exc)}",
                    LOG__DEBUG,
                )
                print(f"[-] MAP monitor start failed: {format_dbus_error(exc)}")
                _print_obex_error_hints(exc, operation="map")

        elif action == "stop":
            from bleep.ble_ops.classic.map import stop_message_monitor
            try:
                stop_message_monitor(mac)
                print("[+] MNS monitor stopped")
            except Exception as exc:
                print_and_log(f"[-] MAP monitor stop failed: {exc}", LOG__DEBUG)
                print(f"[-] MAP monitor stop failed: {exc}")

        else:
            print("Usage: cmap monitor start|stop")

    elif subcmd == "instances":
        try:
            from bleep.ble_ops.classic.map import list_mas_instances
            instances_list = list_mas_instances(mac, service_map=state.current_mapping)
            if not instances_list:
                print("[*] No MAS instances found via SDP")
                return
            print(f"\nMAS Instances on {mac}:")
            for inst in instances_list:
                print(f"  Channel {inst['channel']:>3}  {inst.get('name', '')}  (UUID {inst.get('uuid', '?')})")
            print("\nUse --instance <channel> to target a specific MAS.")
        except Exception as exc:
            print_and_log(f"[-] MAS instance discovery failed: {exc}", LOG__DEBUG)
            print(f"[-] MAS instance discovery failed: {exc}")

    else:
        print(f"[-] Unknown MAP sub-command: {subcmd}")
        print("    Use: folders, peek, list, get, push, download-all, push-all,")
        print("         inbox, props, read, delete, types, fields, monitor, instances")


# ---------------------------------------------------------------------------
# cftp – File Transfer Profile
# ---------------------------------------------------------------------------


def cmd_cftp(args: List[str], state: DebugState) -> None:
    """Browse and transfer files on a remote device via OBEX FTP."""
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    if not args:
        print("Usage:")
        print("  cftp ls [path]                        - List folder contents")
        print("  cftp cd <folder>                      - Change remote folder")
        print("  cftp get <remote> [local_dest]         - Download a file")
        print("  cftp put <local_file> [remote_name]    - Upload a file")
        print("  cftp mkdir <name>                      - Create remote folder")
        print("  cftp rm <name>                         - Delete file/folder")
        print("  cftp cp <source> <target>              - Copy on remote")
        print("  cftp mv <source> <target>              - Move on remote")
        return

    subcmd = args[0].lower()
    mac = state.current_device.mac_address

    from bleep.ble_ops.classic.ftp import detect_ftp_service

    if not detect_ftp_service(state.current_mapping):
        print("[!] FTP service (0x1106) not detected in service map – attempting anyway")

    if subcmd == "ls":
        path = args[1] if len(args) > 1 else ""
        try:
            from bleep.ble_ops.classic.ftp import list_folder
            entries = list_folder(mac, path)
            if not entries:
                print("[*] Folder is empty")
                return
            print(f"\n{'Type':<8} {'Size':>10}  Name")
            print("-" * 40)
            for e in entries:
                etype = e.get("Type", "?")
                esize = e.get("Size", "")
                ename = e.get("Name", "(unnamed)")
                if etype == "folder":
                    print(f"{'dir':<8} {'':>10}  {ename}/")
                else:
                    print(f"{'file':<8} {esize:>10}  {ename}")
            print()
        except Exception as exc:
            print(f"[-] FTP ls failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "cd":
        if len(args) < 2:
            print("Usage: cftp cd <folder>  (use '..' for parent, '' for root)")
            return
        folder = args[1]
        try:
            from bleep.dbuslayer.obex_ftp import FtpSession
            with FtpSession(mac) as ftp:
                ftp.change_folder(folder)
            print(f"[+] Changed folder → {folder!r}")
        except Exception as exc:
            print(f"[-] FTP cd failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "get":
        if len(args) < 2:
            print("Usage: cftp get <remote_file> [local_dest]")
            return
        remote = args[1]
        if len(args) > 2:
            local = args[2]
            use_staging = False
        else:
            local = _obex_staging_path(remote)
            use_staging = True
        try:
            from bleep.ble_ops.classic.ftp import get_file
            result = get_file(mac, remote, local)
            final = _stage_and_move(str(result)) if use_staging else str(result)
            print(f"[+] Downloaded → {final}")
        except Exception as exc:
            print(f"[-] FTP get failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "put":
        if len(args) < 2:
            print("Usage: cftp put <local_file> [remote_name]")
            return
        local = args[1]
        remote_name = args[2] if len(args) > 2 else ""
        try:
            from bleep.ble_ops.classic.ftp import put_file
            result = put_file(mac, local, remote_name)
            transferred = result.get("transferred", "?")
            size = result.get("size", "?")
            print(f"[+] Uploaded: {transferred}/{size} bytes")
        except FileNotFoundError as exc:
            print(f"[-] {exc}")
        except Exception as exc:
            print(f"[-] FTP put failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "mkdir":
        if len(args) < 2:
            print("Usage: cftp mkdir <folder_name>")
            return
        try:
            from bleep.ble_ops.classic.ftp import create_folder
            create_folder(mac, args[1])
            print(f"[+] Created folder: {args[1]}")
        except Exception as exc:
            print(f"[-] FTP mkdir failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "rm":
        if len(args) < 2:
            print("Usage: cftp rm <name>")
            return
        try:
            from bleep.ble_ops.classic.ftp import delete_item
            delete_item(mac, args[1])
            print(f"[+] Deleted: {args[1]}")
        except Exception as exc:
            print(f"[-] FTP rm failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "cp":
        if len(args) < 3:
            print("Usage: cftp cp <source> <target>")
            return
        try:
            from bleep.ble_ops.classic.ftp import copy_file
            copy_file(mac, args[1], args[2])
            print(f"[+] Copied: {args[1]} → {args[2]}")
        except Exception as exc:
            print(f"[-] FTP cp failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "mv":
        if len(args) < 3:
            print("Usage: cftp mv <source> <target>")
            return
        try:
            from bleep.ble_ops.classic.ftp import move_file
            move_file(mac, args[1], args[2])
            print(f"[+] Moved: {args[1]} → {args[2]}")
        except Exception as exc:
            print(f"[-] FTP mv failed: {exc}")
            _print_obex_error_hints(exc)

    else:
        print(f"[-] Unknown FTP sub-command: {subcmd}")
        print("    Use: ls, cd, get, put, mkdir, rm, cp, mv")


# ---------------------------------------------------------------------------
# csync – IrMC Synchronization
# ---------------------------------------------------------------------------


def cmd_csync(args: List[str], state: DebugState) -> None:
    """IrMC Synchronization profile commands.

    Sub-commands:
        get  [target_file] [--location int|sim1]   Download phonebook
        put  <source_file> [--location int|sim1]    Upload phonebook
    """
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    parser = argparse.ArgumentParser(prog="csync", add_help=False)
    parser.add_argument("subcmd", nargs="?", default="")
    parser.add_argument("file", nargs="?", default="")
    parser.add_argument("--location", default="int")
    parser.add_argument("--timeout", type=int, default=60)

    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print("Usage: csync get [target] [--location int|sim1]")
        print("       csync put <source> [--location int|sim1]")
        return

    subcmd = parsed.subcmd.lower()
    mac = state.current_device.mac_address

    if subcmd == "get":
        from bleep.ble_ops.classic.sync import get_phonebook
        target = parsed.file or ""
        try:
            result = get_phonebook(
                mac, target, location=parsed.location, timeout=parsed.timeout,
            )
            print(f"[+] Phonebook saved → {result}")
        except Exception as exc:
            print(f"[-] SYNC get failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "put":
        from bleep.ble_ops.classic.sync import put_phonebook
        if not parsed.file:
            print("[-] Must specify a source file: csync put <file>")
            return
        try:
            put_phonebook(
                mac, parsed.file, location=parsed.location, timeout=parsed.timeout,
            )
            print("[+] Phonebook uploaded OK")
        except Exception as exc:
            print(f"[-] SYNC put failed: {exc}")
            _print_obex_error_hints(exc)

    else:
        print(f"[-] Unknown SYNC sub-command: {subcmd}")
        print("Usage: csync get [target] [--location int|sim1]")
        print("       csync put <source> [--location int|sim1]")


# ---------------------------------------------------------------------------
# cbip – Basic Imaging Profile (experimental)
# ---------------------------------------------------------------------------


def cmd_cbip(args: List[str], state: DebugState) -> None:
    """Basic Imaging Profile commands (experimental).

    Sub-commands:
        props <handle>                     Image properties
        get   <handle> [target_file]       Download full image
        thumb <handle> [target_file]       Download thumbnail
    """
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    parser = argparse.ArgumentParser(prog="cbip", add_help=False)
    parser.add_argument("subcmd", nargs="?", default="")
    parser.add_argument("handle", nargs="?", default="")
    parser.add_argument("file", nargs="?", default="")
    parser.add_argument("--timeout", type=int, default=60)

    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print("Usage: cbip props <handle>")
        print("       cbip get <handle> [target_file]")
        print("       cbip thumb <handle> [target_file]")
        return

    subcmd = parsed.subcmd.lower()
    mac = state.current_device.mac_address

    if not parsed.handle and subcmd in ("props", "get", "thumb"):
        print(f"[-] Must specify an image handle: cbip {subcmd} <handle>")
        return

    if subcmd == "props":
        from bleep.ble_ops.classic.bip import get_properties
        try:
            props = get_properties(mac, parsed.handle, timeout=parsed.timeout)
            for i, entry in enumerate(props):
                print(f"  [{i}] {entry}")
        except Exception as exc:
            print(f"[-] BIP props failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "get":
        from bleep.ble_ops.classic.bip import get_image
        target = parsed.file or ""
        try:
            result = get_image(
                mac, target, parsed.handle, timeout=parsed.timeout,
            )
            print(f"[+] Image saved → {result}")
        except Exception as exc:
            print(f"[-] BIP get failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "thumb":
        from bleep.ble_ops.classic.bip import get_thumbnail
        target = parsed.file or ""
        try:
            result = get_thumbnail(
                mac, target, parsed.handle, timeout=parsed.timeout,
            )
            print(f"[+] Thumbnail saved → {result}")
        except Exception as exc:
            print(f"[-] BIP thumb failed: {exc}")
            _print_obex_error_hints(exc)

    else:
        print(f"[-] Unknown BIP sub-command: {subcmd}")
        print("Usage: cbip props <handle>")
        print("       cbip get <handle> [target_file]")
        print("       cbip thumb <handle> [target_file]")
        print()
        print("NOTE: Image1 is [experimental] – obexd must be started")
        print("      with --experimental for BIP to work.")
