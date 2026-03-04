"""RFCOMM data-exchange commands for debug mode.

Commands: copen, csend, crecv, craw.

Split from ``debug_classic_data.py`` to keep file sizes manageable.
"""

from __future__ import annotations

import argparse
import select
import threading
from typing import List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

from bleep.modes.debug_state import DebugState
from bleep.modes.debug_dbus import format_dbus_error
from bleep.modes.debug_utils import parse_value, hexdump, VALUE_FORMAT_HELP


# ---------------------------------------------------------------------------
# Channel resolution helper (shared by copen / craw)
# ---------------------------------------------------------------------------


def _resolve_rfcomm_channel(
    opts, state: DebugState
) -> Optional[int]:
    """Resolve an RFCOMM channel from *opts* (.channel / .svc / .first).

    Returns the channel number or ``None`` (with user-visible error printed).
    """
    if (getattr(opts, "first", False) or getattr(opts, "svc", None)) and not state.current_mapping:
        try:
            from bleep.ble_ops.classic_sdp import discover_services_sdp
            records = discover_services_sdp(state.current_device.mac_address)
            state.current_mapping = {
                (r["name"] or r["uuid"] or f"handle_{r.get('handle', 'unknown')}"): {
                    "uuid": r.get("uuid"), "name": r.get("name"),
                    "channel": r.get("channel"), "handle": r.get("handle"),
                    "service_version": r.get("service_version"),
                    "description": r.get("description"),
                    "profile_descriptors": r.get("profile_descriptors"),
                }
                for r in records
            }
        except Exception as exc:
            print(f"[-] SDP discovery failed: {format_dbus_error(exc)}")
            return None

    from bleep.modes.debug_classic import _ch

    channel: Optional[int] = None
    if getattr(opts, "channel", None):
        try:
            channel = int(opts.channel)
        except ValueError:
            print("[-] CHANNEL must be numeric")
            return None
    elif getattr(opts, "svc", None):
        key = opts.svc.lower()
        for name, entry in (state.current_mapping or {}).items():
            ch = _ch(entry)
            if key in name.lower() or (ch is not None and key in str(ch)):
                channel = ch
                break
        if channel is None:
            print("[-] Service not found – run 'cservices' first")
            return None
    elif getattr(opts, "first", False):
        if state.current_mapping:
            channel = _ch(next(iter(state.current_mapping.values())))
        else:
            print("[-] Service map empty – run 'cservices' or specify channel")
            return None

    if channel is None:
        print("[-] Could not resolve RFCOMM channel")
    return channel


def _ensure_classic_connected(state: DebugState, mac_token: Optional[str] = None) -> bool:
    """Ensure we have a Classic device connected. Returns True on success."""
    need_connect = (
        state.current_mode != "classic"
        or not state.current_device
        or (mac_token and state.current_device.mac_address.upper() != mac_token.upper())
    )
    if not need_connect:
        return True
    if not mac_token:
        print("[-] No Classic device connected – supply MAC or run cconnect first")
        return False
    print_and_log(f"[*] Quick connect to {mac_token}", LOG__GENERAL)
    try:
        from bleep.ble_ops import connect_and_enumerate__bluetooth__classic as _c_enum
        dev, svc_map = _c_enum(mac_token)
        state.current_device = dev
        state.current_mapping = svc_map
        state.current_mode = "classic"
        state.current_path = state.current_device._device_path
        return True
    except Exception as exc:
        print(f"[-] Connect failed: {format_dbus_error(exc)}")
        return False


# ---------------------------------------------------------------------------
# copen – open/close a dedicated data-exchange RFCOMM socket
# ---------------------------------------------------------------------------


def cmd_copen(args: List[str], state: DebugState) -> None:
    """Open or close a dedicated RFCOMM data socket for csend/crecv/craw."""
    mac_token = None
    if args and not args[0].startswith("-") and ":" in args[0]:
        mac_token = args[0].strip()
        args = args[1:]

    parser = argparse.ArgumentParser(prog="copen", add_help=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("channel", nargs="?", help="RFCOMM channel number")
    group.add_argument("--first", action="store_true")
    group.add_argument("--svc")
    group.add_argument("--close", action="store_true")
    group.add_argument("--status", action="store_true")
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    if opts.status:
        if state.rfcomm_sock:
            print("[+] RFCOMM data socket is open")
        else:
            print("[*] No RFCOMM data socket open")
        return

    if opts.close:
        if state.rfcomm_sock:
            try:
                state.rfcomm_sock.close()
            except Exception:
                pass
            state.rfcomm_sock = None
            print("[+] RFCOMM data socket closed")
        else:
            print("[*] No RFCOMM data socket open")
        return

    if not _ensure_classic_connected(state, mac_token):
        return

    if state.rfcomm_sock:
        print("[*] Data socket already open – use 'copen --close' first")
        return

    channel = _resolve_rfcomm_channel(opts, state)
    if channel is None:
        return

    from bleep.ble_ops.classic_connect import classic_rfccomm_open
    try:
        state.rfcomm_sock = classic_rfccomm_open(
            state.current_device.mac_address, channel, timeout=8.0,
        )
        print(f"[+] RFCOMM data socket opened on channel {channel}")
    except Exception as exc:
        print(f"[-] Failed to open data socket: {format_dbus_error(exc)}")
        state.rfcomm_sock = None


# ---------------------------------------------------------------------------
# csend – send data over the open RFCOMM socket
# ---------------------------------------------------------------------------


def cmd_csend(args: List[str], state: DebugState) -> None:
    """Send data over the open RFCOMM data socket."""
    if not args:
        print("Usage: csend <value>")
        print(VALUE_FORMAT_HELP)
        return

    sock = state.rfcomm_sock
    if sock is None:
        if state.keepalive_sock:
            print("[!] No data socket – falling back to keep-alive socket")
            sock = state.keepalive_sock
        else:
            print("[-] No RFCOMM socket open – use 'copen' first")
            return

    value_str = " ".join(args)
    data, err = parse_value(value_str)
    if err:
        print(f"[-] {err}")
        return
    if not data:
        print("[-] No data to send")
        return

    try:
        sent = sock.send(data)
        print(f"[+] Sent {sent} byte(s)")
        if sent < len(data):
            print(f"[!] Warning: only {sent}/{len(data)} bytes sent")
        print_and_log(f"[csend] {sent}B → {data[:64]!r}", LOG__DEBUG)
    except OSError as exc:
        print(f"[-] Send failed: {exc}")
        print_and_log(f"[-] csend error: {exc}", LOG__DEBUG)


# ---------------------------------------------------------------------------
# crecv – receive data from the open RFCOMM socket
# ---------------------------------------------------------------------------


def cmd_crecv(args: List[str], state: DebugState) -> None:
    """Receive data from the open RFCOMM data socket."""
    parser = argparse.ArgumentParser(prog="crecv", add_help=False)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--size", type=int, default=4096)
    parser.add_argument("--hex", action="store_true", dest="show_hex")
    parser.add_argument("--save", metavar="FILE")
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    sock = state.rfcomm_sock
    if sock is None:
        if state.keepalive_sock:
            print("[!] No data socket – falling back to keep-alive socket")
            sock = state.keepalive_sock
        else:
            print("[-] No RFCOMM socket open – use 'copen' first")
            return

    old_timeout = sock.gettimeout()
    try:
        sock.settimeout(opts.timeout)
        data = sock.recv(opts.size)
    except TimeoutError:
        print(f"[*] No data received within {opts.timeout}s")
        return
    except OSError as exc:
        print(f"[-] Receive failed: {exc}")
        return
    finally:
        try:
            sock.settimeout(old_timeout)
        except Exception:
            pass

    if not data:
        print("[*] Connection closed by remote (0 bytes)")
        return

    print(f"[+] Received {len(data)} byte(s)")
    print_and_log(f"[crecv] {len(data)}B ← {data[:64]!r}", LOG__DEBUG)

    if opts.show_hex or not data.isascii():
        print(hexdump(data))
    else:
        try:
            print(data.decode("utf-8", errors="replace"))
        except Exception:
            print(hexdump(data))

    if opts.save:
        try:
            with open(opts.save, "wb") as fh:
                fh.write(data)
            print(f"[+] Saved to {opts.save}")
        except OSError as exc:
            print(f"[-] Save failed: {exc}")


# ---------------------------------------------------------------------------
# craw – interactive RFCOMM send/receive session
# ---------------------------------------------------------------------------


def cmd_craw(args: List[str], state: DebugState) -> None:
    """Start an interactive raw RFCOMM session (send/receive loop)."""
    parser = argparse.ArgumentParser(prog="craw", add_help=False)
    parser.add_argument("channel", nargs="?")
    parser.add_argument("--svc")
    parser.add_argument("--first", action="store_true")
    parser.add_argument("--hex", action="store_true", dest="show_hex",
                        help="display incoming data as hex dump")
    try:
        opts = parser.parse_args(args)
    except SystemExit:
        return

    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected – run cconnect first")
        return

    sock = state.rfcomm_sock
    opened_here = False
    if sock is None:
        channel = _resolve_rfcomm_channel(opts, state)
        if channel is None:
            print("[-] Specify a channel, --svc, or --first, or use 'copen' beforehand")
            return
        from bleep.ble_ops.classic_connect import classic_rfccomm_open
        try:
            sock = classic_rfccomm_open(
                state.current_device.mac_address, channel, timeout=8.0,
            )
            state.rfcomm_sock = sock
            opened_here = True
            print(f"[+] Opened RFCOMM channel {channel}")
        except Exception as exc:
            print(f"[-] Failed to open RFCOMM: {format_dbus_error(exc)}")
            return

    stop_event = threading.Event()

    def _reader():
        """Background thread that prints incoming data."""
        while not stop_event.is_set():
            try:
                ready, _, _ = select.select([sock], [], [], 0.3)
                if not ready:
                    continue
                chunk = sock.recv(4096)
                if not chunk:
                    print("\n[*] Remote closed connection")
                    stop_event.set()
                    break
                if opts.show_hex or not chunk.isascii():
                    print(f"\n← {len(chunk)}B:\n{hexdump(chunk)}")
                else:
                    print(f"\n← {chunk.decode('utf-8', errors='replace')}", end="")
            except OSError:
                if not stop_event.is_set():
                    print("\n[*] Socket error – session ended")
                    stop_event.set()
                break

    reader_thread = threading.Thread(target=_reader, daemon=True, name="craw-reader")
    reader_thread.start()

    print("[*] Interactive RFCOMM session – type data to send, 'quit' to exit")
    print(f"[*] Value prefixes supported: hex: str: file:")

    try:
        while not stop_event.is_set():
            try:
                line = input("RFCOMM> ")
            except EOFError:
                break
            if not line:
                continue
            if line.strip().lower() in ("quit", "exit", "q"):
                break
            data, err = parse_value(line)
            if err:
                print(f"[-] {err}")
                continue
            if not data:
                continue
            try:
                sock.send(data)
                print(f"→ {len(data)}B sent")
            except OSError as exc:
                print(f"[-] Send failed: {exc}")
                break
    except KeyboardInterrupt:
        print("\n[*] Interrupted")
    finally:
        stop_event.set()
        reader_thread.join(timeout=2.0)
        if opened_here:
            try:
                sock.close()
            except Exception:
                pass
            state.rfcomm_sock = None
            print("[*] RFCOMM socket closed")
        else:
            print("[*] Session ended (socket kept open)")
