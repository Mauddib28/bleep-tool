"""bleep.ble_ops.classic_pbap – Dump phone-book (PBAP) via RFCOMM.

Minimal helper that relies on:
• Existing *classic_connect_and_enumerate* to discover RFCOMM channel map.
• External *obexftp* binary for the OBEX GET transaction (avoids bundling an
  OBEX stack).  This keeps the implementation lightweight while still working
  out-of-the-box on most Linux distributions (bluez-utils / obexftp).

Returned structure::
    {
        "success": bool,
        "out_file": str | None,
        "channel": int | None,
        "cmd": str,               # executed command or diagnostic
    }

Raises *RuntimeError* on unrecoverable errors (missing obexftp, no PBAP svc,…).

**Known Issue - "Too short header in packet" Error:**
This OBEX error occurs when the device has stale OBEX state (e.g., from a previous
aborted transfer). SOLUTION CONFIRMED: Restarting the target device clears the OBEX
buffers and resolves this issue. The error handling in pbap_dump_async() provides
clear guidance when this occurs.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

# optional observation db
try:
    from bleep.core import observations as _obs  # type: ignore
except Exception:  # noqa: BLE001
    _obs = None
# First-choice helper (BlueZ obexd)
from bleep.dbuslayer.obex_pbap import pull_phonebook_vcf as _pbap_dbus

# Fallback code removed – we focus on BlueZ obexd only.

__all__ = [
    "dump_phonebook_pbap",
]

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------
# UUIDs of interest (16-bit)
_PBAP_PSE_UUID16 = "0x112f"  # Phonebook Access – PSE (server)
_PBAP_PSE_UUID128 = "0000112f-0000-1000-8000-00805f9b34fb"


def _locate_pbap_channel(svc_map: Dict[str, int]) -> Optional[int]:
    """Return RFCOMM channel providing PBAP, else *None*."""
    for key, ch in svc_map.items():
        low = key.lower()
        if (
            "phonebook" in low or "pbap" in low
            or low == _PBAP_PSE_UUID16
            or low == _PBAP_PSE_UUID128
        ):
            return ch
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dump_phonebook_pbap(
    mac_address: str,
    *,
    out_file: str | Path | None = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Fetch *telecom/pb.vcf* via PBAP.

    Parameters
    ----------
    mac_address
        Target BR/EDR device MAC address.
    out_file
        Path to save the downloaded VCF; defaults to ``<mac>_pb.vcf``.
    timeout
        Seconds to wait for the *obexftp* subprocess.
    """

    mac_address = mac_address.strip().upper()

    # --- Attempt BlueZ obexd D-Bus path (covers L2CAP PBAP) --------------
    try:
        if out_file is None:
            dest_vcf = _pbap_dbus(mac_address, timeout=timeout)
        else:
            dest_vcf = _pbap_dbus(mac_address, dest_folder=out_file, timeout=timeout)
        print_and_log(f"[+] Phone-book saved to {dest_vcf} via obexd", LOG__GENERAL)

        # persist metadata if DB available
        if _obs:
            try:
                import hashlib

                with open(dest_vcf, "rb") as _f:
                    vcf_bytes = _f.read()
                vcf_hash = hashlib.sha1(vcf_bytes).hexdigest()
                entries = vcf_bytes.count(b"BEGIN:VCARD")
                _obs.upsert_pbap_metadata(mac_address, "PB", entries, vcf_hash)  # type: ignore[attr-defined]
            except Exception:
                pass
        return {
            "success": True,
            "out_file": str(dest_vcf),
            "channel": None,
            "cmd": "dbus-pbap",
        }
    except Exception as exc:
        print_and_log("[*] obexd PBAP path failed – will try RFCOMM fallback", LOG__DEBUG)

    # If we reach here the D-Bus path failed earlier.
    raise RuntimeError("BlueZ obexd PBAP transfer failed; see logs for details") 


# ---------------------------------------------------------------------------
# Async PBAP dump helper (re-used from scripts/examples)
# ---------------------------------------------------------------------------

from gi.repository import GLib  # type: ignore
import dbus
import dbus.mainloop.glib
import os
import time as _time
from bleep.core.log import print_and_log, LOG__DEBUG

# Default repo list exported for callers
DEFAULT_PBAP_REPOS = (
    "PB",  # Phonebook
    "ICH", "OCH", "MCH", "CCH", "SPD", "FAV",
)

# ---------------------------------------------------------------------------
# bc-17 – minimal OBEX Agent for automatic authorisation
# ---------------------------------------------------------------------------


import dbus.service


class _SimpleObexAgent(dbus.service.Object):
    """An in-process OBEX Agent that auto-accepts all requests.

    It is only registered for the lifetime of a PBAP dump when the caller
    passes *auto_auth=True*.  Works around phones that insist on OBEX auth.
    """

    AGENT_IFACE = "org.bluez.obex.Agent1"

    def __init__(self, bus: dbus.Bus):
        super().__init__(bus, "/bleep/ObexAgent")

    # ---- Agent1 methods ------------------------------------------------

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method(AGENT_IFACE, in_signature="oa{sv}", out_signature="")
    def AuthorizePush(self, transfer, properties):  # noqa: D401
        # Always allow push
        return

    @dbus.service.method(AGENT_IFACE, in_signature="oa{sv}", out_signature="")
    def Authorize(self, session, properties):
        return

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPassword(self, session):
        # Return default empty password – many devices accept that.
        return ""

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Cancel(self):
        pass


class _Transfer:
    def __init__(self, cb):
        self.cb = cb
        self.path: str | None = None
        self.filename: str | None = None


class _PbapClientAsync:
    """BlueZ obexd asynchronous PBAP wrapper (signal-driven)."""

    BUS = "org.bluez.obex"
    SESSION_IFACE = "org.bluez.obex.Session1"
    PBAP_IFACE = "org.bluez.obex.PhonebookAccess1"
    TRANSFER_IFACE = "org.bluez.obex.Transfer1"

    def __init__(self, session_path: str):
        self._bus = dbus.SessionBus()
        obj = self._bus.get_object(self.BUS, session_path)
        self.session = dbus.Interface(obj, self.SESSION_IFACE)
        self.pbap = dbus.Interface(obj, self.PBAP_IFACE)

        self._pending = 0
        self._flush_cb = None
        self._transfers: dict[str, _Transfer] = {}

        self._bus.add_signal_receiver(
            self._properties_changed,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path_keyword="path",
        )

    # ---------------- internal helpers ----------------
    def _properties_changed(self, iface, props, _inv, path: str):
        tr = self._transfers.get(path)
        if not tr:
            return
        status = props.get("Status")
        if status == "complete":
            self._complete(path)
        elif status == "error":
            self._error(path)

    def _register_transfer(self, path: str, properties: dict, tr: _Transfer):
        tr.path = path
        tr.filename = properties["Filename"]
        self._transfers[path] = tr
        print_and_log(f"Transfer created {path} → {tr.filename}", LOG__GENERAL)

    def _complete(self, path: str):
        tr = self._transfers.pop(path, None)
        self._pending -= 1
        if not tr:
            return
        try:
            with open(tr.filename, "rb") as fh:
                raw = fh.read()
            # Attempt UTF-8 first, fall back to latin-1 with replacement.
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1", errors="replace")
            lines = [ln + "\n" for ln in text.splitlines()]  # re-add newline
            os.remove(tr.filename)
            tr.cb(lines)
        except Exception as exc:
            print_and_log(f"Error reading file {tr.filename}: {exc}", LOG__DEBUG)
            self._error(path)
        self._maybe_flush()

    def _error(self, path: str):
        self._transfers.pop(path, None)
        self._pending -= 1
        self._maybe_flush()

    def _maybe_flush(self):
        if self._pending == 0 and self._flush_cb:
            cb, self._flush_cb = self._flush_cb, None
            cb()

    # ---------------- public API ----------------------
    def interface(self):
        return self.pbap

    def pull_all(self, params: dbus.Dictionary, cb):
        tr = _Transfer(cb)
        self.pbap.PullAll("", params,
                          reply_handler=lambda o, p: self._register_transfer(o, p, tr),
                          error_handler=lambda err: self._error(tr.path or ""))
        self._pending += 1

    def flush(self, cb):
        if self._pending == 0:
            cb()
        else:
            self._flush_cb = cb


# ---------------------------------------------------------------------------
# Public async helper
# ---------------------------------------------------------------------------

def pbap_dump_async(
    mac_address: str,
    *,
    repos: tuple[str, ...] = DEFAULT_PBAP_REPOS,
    vcard_format: str = "vcard21",
    watchdog: int = 8,
    session_timeout: int = 120,
    auto_auth: bool = False,
) -> dict:
    """Fetch multiple PBAP repositories asynchronously.

    Returns a mapping ``{repo_name: list[str]}`` where each list contains the
    raw VCF lines for that repository.
    """
    mac_address = mac_address.strip().upper()

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    client = dbus.Interface(bus.get_object("org.bluez.obex", "/org/bluez/obex"),
                            "org.bluez.obex.Client1")

    agent: _SimpleObexAgent | None = None
    mgr = None
    if auto_auth:
        try:
            agent = _SimpleObexAgent(bus)
            mgr = dbus.Interface(bus.get_object("org.bluez.obex", "/org/bluez/obex"), "org.bluez.obex.AgentManager1")
            from bleep.core.log import print_and_log, LOG__DEBUG
            print_and_log("[pbap_dump_async] Registering auto-auth OBEX agent", LOG__DEBUG)
            mgr.RegisterAgent(dbus.ObjectPath(agent.object_path), {})
        except Exception:
            agent = None  # Ignore agent errors; continue without auth helper

    # Create PBAP session with error handling
    # Note: "Too short header in packet" error indicates stale OBEX state on the device.
    # Manual testing confirmed: RESTARTING THE TARGET DEVICE resolves this issue.
    # This clears the device's OBEX buffers and allows a fresh session to be established.
    try:
        session_path = client.CreateSession(mac_address, {"Target": "PBAP"})
    except dbus.exceptions.DBusException as exc:
        msg = str(exc)
        from bleep.core.log import print_and_log, LOG__GENERAL
        
        # Handle "Too short header" error - indicates stale OBEX state on device
        # SOLUTION CONFIRMED: Restarting the target device clears OBEX buffers and resolves this.
        if "Too short header" in msg or "too short header" in msg.lower():
            print_and_log(
                f"[-] OBEX CreateSession failed: 'Too short header in packet'\n"
                f"    This indicates stale OBEX state on the device.\n"
                f"    SOLUTION: Restart the target device to clear OBEX buffers.\n"
                f"    Alternative: Disconnect and reconnect via 'bluetoothctl disconnect {mac_address}'",
                LOG__GENERAL
            )
            raise RuntimeError(
                f"OBEX CreateSession failed: Too short header in packet. "
                f"This indicates stale OBEX state on device {mac_address}. "
                f"SOLUTION: Restart the target device to clear OBEX buffers and retry."
            ) from exc
        
        # Handle other common OBEX errors
        if "NoReply" in msg or "Timed out" in msg:
            print_and_log(
                f"[-] OBEX CreateSession failed: Device not responding\n"
                f"    Solutions:\n"
                f"    1. Ensure device is in range and Bluetooth is enabled\n"
                f"    2. Disconnect and reconnect: bluetoothctl disconnect {mac_address}\n"
                f"    3. Restart the target device",
                LOG__GENERAL
            )
            raise RuntimeError(
                f"OBEX CreateSession failed: Device not responding. "
                f"Ensure {mac_address} is in range and Bluetooth is enabled."
            ) from exc
        
        # Re-raise other errors
        raise
    pbap = _PbapClientAsync(session_path)
    loop = GLib.MainLoop()
    last_activity = _time.time()

    def _kick_watchdog(*_a):
        nonlocal last_activity
        last_activity = _time.time()
        return False

    results: dict[str, list[str]] = {}

    def _iterate(seq):
        if not seq:
            loop.quit()
            return
        current = seq[0]
        try:
            pbap.interface().Select("int", current)
        except Exception:
            _iterate(seq[1:])
            return
        params = dbus.Dictionary({"Format": vcard_format})
        pbap.pull_all(params, lambda lines, repo=current: (results.setdefault(repo, []).extend(lines), _kick_watchdog()))
        pbap.flush(lambda: _iterate(seq[1:]))

    _iterate(list(repos))

    # watchdog timer
    def _watchdog_cb():
        if watchdog and (_time.time() - last_activity) > watchdog:
            print_and_log(f"[pbap_dump_async] watchdog {watchdog}s expired – aborting", LOG__DEBUG)
            loop.quit()
            return False
        return True

    GLib.timeout_add_seconds(1, _watchdog_cb)

    GLib.timeout_add_seconds(session_timeout, loop.quit)
    loop.run()

    try:
        client.RemoveSession(session_path)
    except Exception:
        pass

    # Unregister agent if it was registered
    if auto_auth and agent and mgr:
        try:
            print_and_log("[pbap_dump_async] Unregistering auto-auth OBEX agent", LOG__DEBUG)
            mgr.UnregisterAgent(dbus.ObjectPath(agent.object_path))
        except Exception:
            pass

    return {"success": True, "data": results}

__all__.append("pbap_dump_async") 