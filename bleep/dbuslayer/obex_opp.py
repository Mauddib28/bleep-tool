"""bleep.dbuslayer.obex_opp – Object Push Profile via BlueZ *obexd* D-Bus API.

Uses the session D-Bus where *obexd* exposes ``org.bluez.obex``.
Provides synchronous wrappers around ``ObjectPush1.SendFile``,
``ObjectPush1.PullBusinessCard``, and ``ObjectPush1.ExchangeBusinessCards``.

BlueZ reference: ``org.bluez.obex.ObjectPush(5)``

Prerequisites:
  - ``bluetooth-obexd`` must be running (``systemctl --user start obex``).
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

from bleep.dbuslayer._obex_common import (
    poll_obex_transfer as _poll_transfer,
    obex_session_error as _obex_session_error,
)
from bleep.core.errors import BLEEPError, NotSupportedError, map_dbus_error
from bleep.bt_ref.constants import RESULT_ERR, RESULT_ERR_WRONG_STATE

# dbus-python timeout for synchronous method calls (seconds).  Prevents
# indefinite blocking when obexd stalls on a dead RFCOMM channel.
_DBUS_CALL_TIMEOUT_S = 90


def _get_client() -> dbus.Interface:
    """Return the ``Client1`` interface on the session bus."""
    bus = dbus.SessionBus()
    try:
        obj = bus.get_object(_OBEX_SERVICE, OBEX_ROOT_PATH)
        return dbus.Interface(obj, _OBEX_CLIENT_IFACE)
    except dbus.exceptions.DBusException as exc:
        raise BLEEPError(
            f"BlueZ obexd not running or D-Bus error: "
            f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}",
            RESULT_ERR_WRONG_STATE,
        ) from exc


def _build_session_opts(channel: Optional[int] = None) -> Dict:
    """Build the ``CreateSession`` options dict, optionally with a Channel hint."""
    opts: Dict = {"Target": "OPP"}
    if channel is not None:
        opts["Channel"] = dbus.Byte(channel)
    return opts


def opp_send_file(
    mac_address: str,
    filepath: str,
    *,
    timeout: int = 120,
    channel: Optional[int] = None,
) -> Dict:
    """Send *filepath* to *mac_address* via Object Push Profile.

    Parameters
    ----------
    channel
        RFCOMM channel for OPP on the target (from prior SDP).  When given,
        obexd skips its own SDP lookup — critical for older devices where a
        redundant SDP query during an active keep-alive causes a timeout.

    Returns a dict with transfer metadata on success.
    Raises :class:`~bleep.core.errors.BLEEPError` on failure.
    """
    mac_address = mac_address.strip().upper()
    filepath = os.path.abspath(filepath)
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    client = _get_client()
    bus = dbus.SessionBus()

    opts = _build_session_opts(channel)
    print_and_log(f"[OPP] Creating session → {mac_address} (opts={dict(opts)})", LOG__DEBUG)
    try:
        session_path = client.CreateSession(mac_address, opts)
    except dbus.exceptions.DBusException as exc:
        raise _obex_session_error(
            exc, mac_address, profile="OPP", service_hint="OPP (0x1105)",
        ) from exc

    try:
        session_obj = bus.get_object(_OBEX_SERVICE, session_path)
        opp = dbus.Interface(session_obj, _OBEX_OPP_IFACE)
    except dbus.exceptions.DBusException as exc:
        try:
            client.RemoveSession(session_path)
        except Exception:
            pass
        raise map_dbus_error(exc) from exc

    print_and_log(f"[OPP] SendFile: {filepath}", LOG__DEBUG)
    try:
        transfer_path, transfer_props = opp.SendFile(
            filepath, timeout=_DBUS_CALL_TIMEOUT_S,
        )
    except dbus.exceptions.DBusException as exc:
        raise map_dbus_error(exc) from exc

    try:
        result = _poll_transfer(bus, transfer_path, timeout, label="OPP")
    finally:
        try:
            client.RemoveSession(session_path)
        except Exception:
            pass

    if result.get("status") == "removed":
        # obexd completed and removed the transfer before the poller read it.
        # For SendFile this is almost always a success — the remote device
        # accepted the connection and obexd delivered the payload.
        print_and_log(
            "[OPP] Transfer object removed (fast completion) — send likely succeeded",
            LOG__DEBUG,
        )
        result["status"] = "complete"
        for key in ("size", "transferred"):
            if key not in result and key.capitalize() in (transfer_props or {}):
                result[key] = int(transfer_props[key.capitalize()])

    return result


def opp_pull_business_card(
    mac_address: str,
    dest: str = "business_card.vcf",
    *,
    timeout: int = 60,
    channel: Optional[int] = None,
) -> Path:
    """Pull the default business card from *mac_address* via OPP.

    Parameters
    ----------
    channel
        RFCOMM channel for OPP on the target (from prior SDP).  When given,
        obexd skips its own SDP lookup — critical for older devices where a
        redundant SDP query during an active keep-alive causes a timeout.

    Returns the local ``Path`` to the downloaded file.
    Raises :class:`~bleep.core.errors.BLEEPError` on failure.
    """
    mac_address = mac_address.strip().upper()
    dest = os.path.abspath(dest)

    client = _get_client()
    bus = dbus.SessionBus()

    opts = _build_session_opts(channel)
    print_and_log(f"[OPP] Creating session → {mac_address} (opts={dict(opts)})", LOG__DEBUG)
    try:
        session_path = client.CreateSession(mac_address, opts)
    except dbus.exceptions.DBusException as exc:
        raise _obex_session_error(
            exc, mac_address, profile="OPP", service_hint="OPP (0x1105)",
        ) from exc

    try:
        session_obj = bus.get_object(_OBEX_SERVICE, session_path)
        opp = dbus.Interface(session_obj, _OBEX_OPP_IFACE)
    except dbus.exceptions.DBusException as exc:
        try:
            client.RemoveSession(session_path)
        except Exception:
            pass
        raise map_dbus_error(exc) from exc

    print_and_log(f"[OPP] PullBusinessCard → {dest}", LOG__DEBUG)
    try:
        transfer_path, transfer_props = opp.PullBusinessCard(
            dest, timeout=_DBUS_CALL_TIMEOUT_S,
        )
    except dbus.exceptions.DBusException as exc:
        try:
            client.RemoveSession(session_path)
        except Exception:
            pass
        raise map_dbus_error(exc) from exc

    try:
        result = _poll_transfer(bus, transfer_path, timeout, label="OPP")
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

    if result.get("status") == "removed":
        print_and_log(
            "[OPP] Transfer object removed (fast completion) — "
            "verifying file outcome",
            LOG__DEBUG,
        )

    # obexd removes the file on failed GET transfers (transfer.c), so
    # file existence with non-zero size is a reliable success indicator
    # regardless of whether status was "complete" or "removed".
    if result_path.exists() and result_path.stat().st_size > 0:
        size = result_path.stat().st_size
        print_and_log(
            f"[OPP] Pull verified: {result_path} ({size} bytes)",
            LOG__DEBUG,
        )
        return result_path

    raise BLEEPError(
        "OPP PullBusinessCard: remote device accepted the OBEX "
        "connection but no vCard was received — the device may "
        "not support OPP pull (OBEX GET), or obexd could not write "
        f"to {dest}",
        RESULT_ERR,
    )


def opp_exchange_business_cards(
    mac_address: str,
    client_vcf: str,
    dest: str = "business_card.vcf",
    *,
    timeout: int = 120,
    channel: Optional[int] = None,
) -> Path:
    """Push *client_vcf* to *mac_address* then pull the remote business card.

    Wraps ``ObjectPush1.ExchangeBusinessCards`` per
    ``org.bluez.obex.ObjectPush(5)``.

    Parameters
    ----------
    client_vcf
        Local vCard file to push to the remote device.
    dest
        Local path to save the remote device's business card.
    channel
        RFCOMM channel for OPP on the target (from prior SDP).

    Returns the local ``Path`` to the downloaded remote card.
    Raises :class:`~bleep.core.errors.BLEEPError` on failure.
    """
    mac_address = mac_address.strip().upper()
    client_vcf = os.path.abspath(client_vcf)
    if not os.path.isfile(client_vcf):
        raise FileNotFoundError(f"Client vCard not found: {client_vcf}")
    dest = os.path.abspath(dest)

    client = _get_client()
    bus = dbus.SessionBus()

    opts = _build_session_opts(channel)
    print_and_log(
        f"[OPP] Creating session → {mac_address} (opts={dict(opts)})", LOG__DEBUG,
    )
    try:
        session_path = client.CreateSession(mac_address, opts)
    except dbus.exceptions.DBusException as exc:
        raise _obex_session_error(
            exc, mac_address, profile="OPP", service_hint="OPP (0x1105)",
        ) from exc

    try:
        session_obj = bus.get_object(_OBEX_SERVICE, session_path)
        opp = dbus.Interface(session_obj, _OBEX_OPP_IFACE)
    except dbus.exceptions.DBusException as exc:
        try:
            client.RemoveSession(session_path)
        except Exception:
            pass
        raise map_dbus_error(exc) from exc

    print_and_log(
        f"[OPP] ExchangeBusinessCards: push={client_vcf} pull→{dest}", LOG__DEBUG,
    )
    try:
        transfer_path, transfer_props = opp.ExchangeBusinessCards(
            client_vcf, dest, timeout=_DBUS_CALL_TIMEOUT_S,
        )
    except dbus.exceptions.DBusException as exc:
        try:
            client.RemoveSession(session_path)
        except Exception:
            pass
        dbus_msg = (exc.get_dbus_message() or "").lower()
        if "not implemented" in dbus_msg:
            raise NotSupportedError(
                "OPP ExchangeBusinessCards (unsupported by this obexd build; "
                "in Debug Mode use 'copp send' and 'copp pull' as separate steps)"
            ) from exc
        raise map_dbus_error(exc) from exc

    try:
        result = _poll_transfer(bus, transfer_path, timeout, label="OPP")
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

    if result.get("status") == "removed":
        if result_path.exists() and result_path.stat().st_size > 0:
            print_and_log(
                f"[OPP] Transfer object removed (fast completion) — "
                f"exchange succeeded, file written to {result_path}",
                LOG__DEBUG,
            )
        else:
            raise BLEEPError(
                "OPP ExchangeBusinessCards: transfer object removed before "
                "status could be read and no file was written — the device "
                "may not fully support business card exchange",
                RESULT_ERR,
            )

    return result_path
