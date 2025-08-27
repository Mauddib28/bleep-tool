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
import time
from pathlib import Path
from typing import Optional

import dbus

# BlueZ obex constants -------------------------------------------------------
_OBEX_SERVICE = "org.bluez.obex"
_OBEX_CLIENT_IFACE = "org.bluez.obex.Client1"
_OBEX_PBAP_IFACE = "org.bluez.obex.PhonebookAccess1"
_OBEX_TRANSFER_IFACE = "org.bluez.obex.Transfer1"


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
        client_obj = bus.get_object(_OBEX_SERVICE, "/org/bluez/obex")
        client = dbus.Interface(client_obj, _OBEX_CLIENT_IFACE)
    except dbus.exceptions.DBusException as exc:
        raise RuntimeError("BlueZ obexd service not running or DBus error: " + str(exc)) from exc

    # 2. Create PBAP session – first param destination, second param options dict
    try:
        session_path = client.CreateSession(mac_address, {"Target": "PBAP"})
    except dbus.exceptions.DBusException as exc:
        msg = str(exc)
        # Provide friendlier diagnostics for common obexd errors.
        if "NoReply" in msg or "Timed out waiting for response" in msg:
            raise RuntimeError(
                "PBAP CreateSession failed (controller probably stuck). Work-around: in a *separate*"
                " terminal run `bluetoothctl disconnect {} ` and retry, or toggle the phone’s"
                " Bluetooth.  Full DBus error: {}".format(mac_address, msg)
            ) from exc
        raise

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
    try:
        transfer_path = pbap.PullAll("", {"Format": "vcard21"})
    except dbus.exceptions.DBusException as exc:
        msg = str(exc)
        if "Too short header" in msg:
            raise RuntimeError(
                "Remote device signalled 'Too short header'. On many feature-phones this"
                " indicates a stale OBEX state – power-cycle the phone and retry."
            ) from exc
        raise

    transfer_obj = bus.get_object(_OBEX_SERVICE, transfer_path)
    props_iface = dbus.Interface(transfer_obj, "org.freedesktop.DBus.Properties")

    start = time.time()
    while True:
        status = str(props_iface.Get(_OBEX_TRANSFER_IFACE, "Status"))
        if status.lower() in {"complete", "error"}:
            break
        if (time.time() - start) > timeout:
            raise RuntimeError("PBAP transfer timed out")
        time.sleep(0.2)

    if status.lower() != "complete":
        raise RuntimeError("PBAP transfer failed (Status=" + status + ")")

    # Get Filename property – may be empty depending on obexd version
    filename = str(props_iface.Get(_OBEX_TRANSFER_IFACE, "Filename"))
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