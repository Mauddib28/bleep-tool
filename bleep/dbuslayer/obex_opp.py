"""bleep.dbuslayer.obex_opp – Object Push Profile via BlueZ *obexd* D-Bus API.

Uses the session D-Bus where *obexd* exposes ``org.bluez.obex``.
Provides synchronous wrappers around ``ObjectPush1.SendFile`` and
``ObjectPush1.PullBusinessCard``.

Prerequisites:
  - ``bluetooth-obexd`` must be running.
  - Target device must be paired and trusted.
  - Device must advertise OPP (UUID 0x1105).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

import dbus

from bleep.core.log import print_and_log, LOG__DEBUG

from bleep.bt_ref.constants import (
    OBEX_SERVICE as _OBEX_SERVICE,
    OBEX_ROOT_PATH,
    OBEX_CLIENT_INTERFACE as _OBEX_CLIENT_IFACE,
    OBEX_OPP_INTERFACE as _OBEX_OPP_IFACE,
)

from bleep.dbuslayer._obex_common import poll_obex_transfer as _poll_transfer


def _get_client() -> dbus.Interface:
    """Return the ``Client1`` interface on the session bus."""
    bus = dbus.SessionBus()
    try:
        obj = bus.get_object(_OBEX_SERVICE, OBEX_ROOT_PATH)
        return dbus.Interface(obj, _OBEX_CLIENT_IFACE)
    except dbus.exceptions.DBusException as exc:
        raise RuntimeError(
            f"BlueZ obexd not running or D-Bus error: "
            f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
        ) from exc


def opp_send_file(
    mac_address: str,
    filepath: str,
    *,
    timeout: int = 120,
) -> Dict:
    """Send *filepath* to *mac_address* via Object Push Profile.

    Returns a dict with transfer metadata on success.
    Raises ``RuntimeError`` on failure.
    """
    mac_address = mac_address.strip().upper()
    filepath = os.path.abspath(filepath)
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    client = _get_client()
    bus = dbus.SessionBus()

    print_and_log(f"[OPP] Creating session → {mac_address}", LOG__DEBUG)
    try:
        session_path = client.CreateSession(mac_address, {"Target": "OPP"})
    except dbus.exceptions.DBusException as exc:
        raise RuntimeError(
            f"OPP CreateSession failed: {exc.get_dbus_name()}: "
            f"{exc.get_dbus_message() or ''}"
        ) from exc

    session_obj = bus.get_object(_OBEX_SERVICE, session_path)
    opp = dbus.Interface(session_obj, _OBEX_OPP_IFACE)

    print_and_log(f"[OPP] SendFile: {filepath}", LOG__DEBUG)
    try:
        transfer_path, transfer_props = opp.SendFile(filepath)
    except dbus.exceptions.DBusException as exc:
        raise RuntimeError(
            f"OPP SendFile failed: {exc.get_dbus_name()}: "
            f"{exc.get_dbus_message() or ''}"
        ) from exc

    try:
        result = _poll_transfer(bus, transfer_path, timeout, label="OPP")
    finally:
        try:
            client.RemoveSession(session_path)
        except Exception:
            pass

    return result


def opp_pull_business_card(
    mac_address: str,
    dest: str = "business_card.vcf",
    *,
    timeout: int = 60,
) -> Path:
    """Pull the default business card from *mac_address* via OPP.

    Returns the local ``Path`` to the downloaded file.
    Raises ``RuntimeError`` on failure.
    """
    mac_address = mac_address.strip().upper()
    dest = os.path.abspath(dest)

    client = _get_client()
    bus = dbus.SessionBus()

    print_and_log(f"[OPP] Creating session → {mac_address}", LOG__DEBUG)
    try:
        session_path = client.CreateSession(mac_address, {"Target": "OPP"})
    except dbus.exceptions.DBusException as exc:
        raise RuntimeError(
            f"OPP CreateSession failed: {exc.get_dbus_name()}: "
            f"{exc.get_dbus_message() or ''}"
        ) from exc

    session_obj = bus.get_object(_OBEX_SERVICE, session_path)
    opp = dbus.Interface(session_obj, _OBEX_OPP_IFACE)

    print_and_log(f"[OPP] PullBusinessCard → {dest}", LOG__DEBUG)
    try:
        transfer_path, transfer_props = opp.PullBusinessCard(dest)
    except dbus.exceptions.DBusException as exc:
        raise RuntimeError(
            f"OPP PullBusinessCard failed: {exc.get_dbus_name()}: "
            f"{exc.get_dbus_message() or ''}"
        ) from exc

    try:
        _poll_transfer(bus, transfer_path, timeout, label="OPP")
    finally:
        try:
            client.RemoveSession(session_path)
        except Exception:
            pass

    result_path = Path(dest)
    if not result_path.exists():
        filename = transfer_props.get("Filename")
        if filename:
            result_path = Path(str(filename))
    return result_path
