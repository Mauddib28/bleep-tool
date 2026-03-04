"""OBEX profile commands for debug mode.

Commands: copp (Object Push), cmap (Message Access), cftp (File Transfer),
          csync (IrMC Synchronization), cbip (Basic Imaging).

Split from ``debug_classic_data.py`` to keep file sizes manageable.
"""

from __future__ import annotations

import argparse
from typing import Any, List, Optional

from bleep.modes.debug_state import DebugState
from bleep.modes.debug_dbus import format_dbus_error


# ---------------------------------------------------------------------------
# OBEX error hints (shared by copp / cmap / cftp / csync / cbip)
# ---------------------------------------------------------------------------


def _print_obex_error_hints(exc: Exception) -> None:
    """Print common OBEX troubleshooting hints based on the error."""
    error_str = str(exc).lower()
    if "too short header" in error_str:
        print("[-] Stale OBEX state – restart the target device to clear buffers.")
    elif "obex" in error_str or "obexd" in error_str:
        print("[-] Ensure bluetooth-obexd is running:")
        print("    sudo systemctl start bluetooth-obexd")
    elif "not found" in error_str or "no service" in error_str:
        print("[-] Service not found. Ensure device is paired and trusted.")


# ---------------------------------------------------------------------------
# copp – Object Push Profile (send file / pull business card)
# ---------------------------------------------------------------------------


def cmd_copp(args: List[str], state: DebugState) -> None:
    """Send a file or pull a business card via Object Push Profile."""
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    if not args:
        print("Usage:")
        print("  copp send <filepath>         - Send a file via OPP")
        print("  copp pull [dest.vcf]         - Pull default business card")
        return

    subcmd = args[0].lower()
    mac = state.current_device.mac_address

    from bleep.ble_ops.classic_opp import detect_opp_service

    if not detect_opp_service(state.current_mapping):
        print("[!] OPP service (0x1105) not detected in service map – attempting anyway")

    if subcmd == "send":
        if len(args) < 2:
            print("Usage: copp send <filepath>")
            return
        filepath = args[1]
        try:
            from bleep.ble_ops.classic_opp import send_file
            result = send_file(mac, filepath)
            transferred = result.get("transferred", "?")
            size = result.get("size", "?")
            print(f"[+] OPP send complete: {transferred}/{size} bytes transferred")
        except FileNotFoundError as exc:
            print(f"[-] {exc}")
        except Exception as exc:
            print(f"[-] OPP send failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "pull":
        dest = args[1] if len(args) > 1 else f"/tmp/{mac.replace(':', '').lower()}_card.vcf"
        try:
            from bleep.ble_ops.classic_opp import pull_business_card
            result_path = pull_business_card(mac, dest)
            print(f"[+] Business card saved → {result_path}")
        except Exception as exc:
            print(f"[-] OPP pull failed: {exc}")
            _print_obex_error_hints(exc)

    else:
        print(f"[-] Unknown OPP sub-command: {subcmd}")
        print("    Use: copp send <file>  or  copp pull [dest]")


# ---------------------------------------------------------------------------
# cmap – Message Access Profile
# ---------------------------------------------------------------------------


def cmd_cmap(args: List[str], state: DebugState) -> None:
    """Interact with remote device messages via Message Access Profile."""
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    if not args:
        print("Usage:")
        print("  cmap folders                           - List message folders")
        print("  cmap list [folder]                     - List messages")
        print("  cmap get <handle> [dest.txt]           - Download a message")
        print("  cmap push <filepath> [folder]          - Push/send a message")
        print("  cmap inbox                             - Trigger inbox update")
        print("  cmap props <handle>                    - Message properties")
        print("  cmap read <handle> [true|false]        - Mark message read/unread")
        print("  cmap delete <handle> [true|false]      - Mark message deleted/undeleted")
        print("  cmap types                             - Supported message types")
        print("  cmap fields                            - Available filter fields")
        print("  cmap monitor start|stop                - MNS notification watch")
        print("  cmap instances                         - List MAS instances (SDP)")
        print("")
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

    from bleep.ble_ops.classic_map import detect_map_service

    if not detect_map_service(state.current_mapping):
        print("[!] MAP service (0x1132/0x1134) not detected in service map – attempting anyway")

    if subcmd == "folders":
        try:
            from bleep.ble_ops.classic_map import list_folders
            folders = list_folders(mac, instance=instance)
            if not folders:
                print("[*] No folders found")
                return
            print("\nMessage Folders:")
            for f in folders:
                print(f"  {f.get('Name', '(unnamed)')}/")
            print()
        except Exception as exc:
            print(f"[-] MAP list-folders failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "list":
        folder = args[1] if len(args) > 1 else ""
        try:
            from bleep.ble_ops.classic_map import list_messages
            messages = list_messages(mac, folder, instance=instance)
            if not messages:
                print(f"[*] No messages in '{folder or '(root)'}'")
                return
            print(f"\nMessages ({len(messages)}):")
            for m in messages:
                handle = m.get("path", "").rsplit("message", 1)[-1] if "path" in m else "?"
                subject = m.get("Subject", "(no subject)")
                sender = m.get("Sender", "")
                read_flag = "R" if m.get("Read", False) else " "
                print(f"  [{read_flag}] {handle:>6}  {sender:20}  {subject}")
            print()
        except Exception as exc:
            print(f"[-] MAP list-messages failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "get":
        if len(args) < 2:
            print("Usage: cmap get <handle> [dest.txt]")
            return
        handle = args[1]
        dest = args[2] if len(args) > 2 else f"/tmp/{mac.replace(':', '').lower()}_msg_{handle}.txt"
        try:
            from bleep.ble_ops.classic_map import get_message
            result = get_message(mac, handle, dest, instance=instance)
            print(f"[+] Message saved → {result}")
            if result.exists():
                content = result.read_text(errors="replace")
                if len(content) < 2000:
                    print(content)
        except Exception as exc:
            print(f"[-] MAP get-message failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "push":
        if len(args) < 2:
            print("Usage: cmap push <filepath> [folder]")
            return
        filepath = args[1]
        folder = args[2] if len(args) > 2 else "telecom/msg/outbox"
        try:
            from bleep.ble_ops.classic_map import push_message
            push_message(mac, filepath, folder, instance=instance)
            print("[+] Message pushed successfully")
        except FileNotFoundError as exc:
            print(f"[-] {exc}")
        except Exception as exc:
            print(f"[-] MAP push failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "inbox":
        try:
            from bleep.ble_ops.classic_map import update_inbox
            update_inbox(mac, instance=instance)
            print("[+] Inbox update requested")
        except Exception as exc:
            print(f"[-] MAP inbox-update failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "props":
        if len(args) < 2:
            print("Usage: cmap props <handle>")
            return
        handle = args[1]
        try:
            from bleep.dbuslayer.obex_map import MapSession
            with MapSession(mac, instance=instance) as sess:
                props = sess.get_message_properties(handle)
            for k, v in props.items():
                print(f"  {k}: {v}")
        except Exception as exc:
            print(f"[-] MAP get-properties failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "read":
        if len(args) < 2:
            print("Usage: cmap read <handle> [true|false]")
            return
        handle = args[1]
        flag = args[2].lower() != "false" if len(args) > 2 else True
        try:
            from bleep.dbuslayer.obex_map import MapSession
            with MapSession(mac, instance=instance) as sess:
                sess.set_message_read(handle, flag)
            print(f"[+] Message {handle} marked {'read' if flag else 'unread'}")
        except Exception as exc:
            print(f"[-] MAP set-read failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "delete":
        if len(args) < 2:
            print("Usage: cmap delete <handle> [true|false]")
            return
        handle = args[1]
        flag = args[2].lower() != "false" if len(args) > 2 else True
        try:
            from bleep.dbuslayer.obex_map import MapSession
            with MapSession(mac, instance=instance) as sess:
                sess.set_message_deleted(handle, flag)
            print(f"[+] Message {handle} marked {'deleted' if flag else 'undeleted'}")
        except Exception as exc:
            print(f"[-] MAP set-deleted failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "types":
        try:
            from bleep.ble_ops.classic_map import get_supported_types
            types = get_supported_types(mac, instance=instance)
            if not types:
                print("[*] No supported types reported")
            else:
                print("Supported message types:")
                for t in types:
                    print(f"  {t}")
        except Exception as exc:
            print(f"[-] MAP get-supported-types failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "fields":
        try:
            from bleep.ble_ops.classic_map import list_filter_fields
            fields = list_filter_fields(mac, instance=instance)
            if not fields:
                print("[*] No filter fields reported")
            else:
                print("Available filter fields:")
                for f in fields:
                    print(f"  {f}")
        except Exception as exc:
            print(f"[-] MAP list-filter-fields failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "monitor":
        action = args[1].lower() if len(args) > 1 else ""
        if action == "start":
            from bleep.ble_ops.classic_map import start_message_monitor

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
                print(f"[-] MAP monitor start failed: {exc}")
                _print_obex_error_hints(exc)

        elif action == "stop":
            from bleep.ble_ops.classic_map import stop_message_monitor
            try:
                stop_message_monitor(mac)
                print("[+] MNS monitor stopped")
            except Exception as exc:
                print(f"[-] MAP monitor stop failed: {exc}")

        else:
            print("Usage: cmap monitor start|stop")

    elif subcmd == "instances":
        try:
            from bleep.ble_ops.classic_map import list_mas_instances
            instances_list = list_mas_instances(mac)
            if not instances_list:
                print("[*] No MAS instances found via SDP")
                return
            print(f"\nMAS Instances on {mac}:")
            for inst in instances_list:
                print(f"  Channel {inst['channel']:>3}  {inst.get('name', '')}  (UUID {inst.get('uuid', '?')})")
            print("\nUse --instance <channel> to target a specific MAS.")
        except Exception as exc:
            print(f"[-] MAS instance discovery failed: {exc}")

    else:
        print(f"[-] Unknown MAP sub-command: {subcmd}")
        print("    Use: folders, list, get, push, inbox, props, read, delete,")
        print("         types, fields, monitor, instances")


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

    from bleep.ble_ops.classic_ftp import detect_ftp_service

    if not detect_ftp_service(state.current_mapping):
        print("[!] FTP service (0x1106) not detected in service map – attempting anyway")

    if subcmd == "ls":
        path = args[1] if len(args) > 1 else ""
        try:
            from bleep.ble_ops.classic_ftp import list_folder
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
        local = args[2] if len(args) > 2 else f"/tmp/{remote}"
        try:
            from bleep.ble_ops.classic_ftp import get_file
            result = get_file(mac, remote, local)
            print(f"[+] Downloaded → {result}")
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
            from bleep.ble_ops.classic_ftp import put_file
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
            from bleep.ble_ops.classic_ftp import create_folder
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
            from bleep.ble_ops.classic_ftp import delete_item
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
            from bleep.ble_ops.classic_ftp import copy_file
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
            from bleep.ble_ops.classic_ftp import move_file
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
        from bleep.ble_ops.classic_sync import get_phonebook
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
        from bleep.ble_ops.classic_sync import put_phonebook
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
        from bleep.ble_ops.classic_bip import get_properties
        try:
            props = get_properties(mac, parsed.handle, timeout=parsed.timeout)
            for i, entry in enumerate(props):
                print(f"  [{i}] {entry}")
        except Exception as exc:
            print(f"[-] BIP props failed: {exc}")
            _print_obex_error_hints(exc)

    elif subcmd == "get":
        from bleep.ble_ops.classic_bip import get_image
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
        from bleep.ble_ops.classic_bip import get_thumbnail
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
