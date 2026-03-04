"""bleep.dbuslayer.obex_pbap – PBAP phone-book fetch via BlueZ *obexd* D-Bus API.

The helper connects to the *session* D-Bus (where *obexd* exposes
``org.bluez.obex``) and performs a synchronous ``PullPhoneBook`` call.
It blocks until the transfer completes or *timeout* expires.

Returned value is the *Path* to the downloaded file on local FS as reported by
BlueZ.  Callers may move/rename it as desired.

Raises *RuntimeError* for any failure (service not running, PBAP not
available, transfer error or timeout).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import dbus

from bleep.bt_ref.constants import (
    OBEX_SERVICE as _OBEX_SERVICE,
    OBEX_ROOT_PATH,
    OBEX_CLIENT_INTERFACE as _OBEX_CLIENT_IFACE,
    OBEX_PBAP_INTERFACE as _OBEX_PBAP_IFACE,
)

from bleep.dbuslayer._obex_common import poll_obex_transfer as _poll_transfer


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def pull_phonebook_vcf(
    mac_address: str,
    *,
    dest_folder: str | Path = ".",
    timeout: int = 60,
) -> Path:
    """Download *telecom/pb.vcf* from *mac_address* using PBAP.

    The file is saved where BlueZ chooses (usually `$XDG_DOWNLOAD_DIR`) and the
    path is returned.  Caller can move it afterwards.
    """

    mac_address = mac_address.strip().upper()
    bus = dbus.SessionBus()

    # 1. Get Client interface
    try:
        client_obj = bus.get_object(_OBEX_SERVICE, OBEX_ROOT_PATH)
        client = dbus.Interface(client_obj, _OBEX_CLIENT_IFACE)
    except dbus.exceptions.DBusException as exc:
        raise RuntimeError(
            "BlueZ obexd service not running or DBus error: {}: {}".format(
                exc.get_dbus_name(), exc.get_dbus_message() or ""
            )
        ) from exc

    # 2. Create PBAP session – first param destination, second param options dict
    try:
        session_path = client.CreateSession(mac_address, {"Target": "PBAP"})
    except dbus.exceptions.DBusException as exc:
        error_name = exc.get_dbus_name() or "unknown"
        error_msg = exc.get_dbus_message() or ""
        error_str = f"{error_name}: {error_msg}" if error_msg else error_name
        # Provide friendlier diagnostics for common obexd errors.
        if "NoReply" in error_msg or "Timed out waiting for response" in error_msg:
            raise RuntimeError(
                f"PBAP CreateSession failed (controller probably stuck). Work-around: in a *separate*"
                f" terminal run `bluetoothctl disconnect {mac_address} ` and retry, or toggle the phone's"
                f" Bluetooth. Full D-Bus error: {error_str}"
            ) from exc
        # Preserve D-Bus name and message in raised RuntimeError diagnostics
        raise RuntimeError(f"PBAP CreateSession failed: {error_str}") from exc

    # 3. Obtain PhonebookAccess1 interface on the session path
    pbap_obj = bus.get_object(_OBEX_SERVICE, session_path)
    pbap = dbus.Interface(pbap_obj, _OBEX_PBAP_IFACE)

    # Some PSEs require Select before any Pull operation
    try:
        pbap.Select("int", "pb")  # internal memory, main phonebook
    except dbus.exceptions.DBusException as exc:
        print("[DEBUG] PBAP Select failed: ", exc)
        # Ignore if not supported / already selected
        pass

    # 4. Start transfer – PullAll ensures full phonebook even if PB.vcf path unsupported
    # Note: "Too short header" error can also occur during PullAll (not just CreateSession).
    # SOLUTION CONFIRMED: Restarting the target device clears OBEX buffers and resolves this.
    try:
        transfer_path = pbap.PullAll("", {"Format": "vcard21"})
    except dbus.exceptions.DBusException as exc:
        error_name = exc.get_dbus_name() or "unknown"
        error_msg = exc.get_dbus_message() or ""
        error_str = f"{error_name}: {error_msg}" if error_msg else error_name
        if "Too short header" in error_msg:
            raise RuntimeError(
                f"Remote device signalled 'Too short header'. On many feature-phones this"
                f" indicates a stale OBEX state – power-cycle the phone and retry. D-Bus error: {error_str}"
            ) from exc
        # Preserve D-Bus name and message in raised RuntimeError diagnostics
        raise RuntimeError(f"PBAP PullAll failed: {error_str}") from exc

    result = _poll_transfer(bus, transfer_path, timeout, label="PBAP")

    filename = result.get("filename", "")
    if not filename:
        raise RuntimeError("BlueZ did not provide Filename for completed transfer")

    src = Path(filename)
    if not src.exists():
        raise RuntimeError("Transfer reported success but file not found: " + filename)

    dest_folder = Path(dest_folder)
    if dest_folder.is_dir():
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest_path = dest_folder / src.name
    else:
        # Caller passed a file path → save exactly there.
        dest_folder.parent.mkdir(parents=True, exist_ok=True)
        dest_path = dest_folder
    src.rename(dest_path)
    return dest_path 