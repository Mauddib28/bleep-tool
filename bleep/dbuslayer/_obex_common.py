"""Shared helpers for OBEX profile D-Bus layers.

Consolidates transfer-polling logic that was duplicated across
``obex_opp.py``, ``obex_map.py``, and ``obex_pbap.py``.
"""

from __future__ import annotations

import time
from typing import Any, Dict

import dbus

from bleep.bt_ref.constants import (
    OBEX_SERVICE as _OBEX_SERVICE,
    OBEX_TRANSFER_INTERFACE as _OBEX_TRANSFER_IFACE,
    DBUS_PROPERTIES,
)


def poll_obex_transfer(
    bus: dbus.Bus,
    transfer_path: str,
    timeout: int,
    *,
    label: str = "OBEX",
) -> Dict[str, Any]:
    """Block until the ``Transfer1`` at *transfer_path* reaches a terminal state.

    Returns a dict with ``status``, and optionally ``transferred``, ``size``,
    and ``filename`` keys on success.

    When the transfer object is removed by obexd before the poller can read
    its status (fast-completion race), returns ``{"status": "removed"}``.
    This is **not** necessarily a failure — obexd removes transfer objects
    immediately after completion, and on fast devices the transfer finishes
    before the first poll.  Callers must verify the actual outcome (e.g.
    file existence for pull, assume success for send).

    Raises :class:`~bleep.core.errors.TimeoutError` on timeout and
    :class:`~bleep.core.errors.BLEEPError` on ``error`` status.
    """
    from bleep.core.log import print_and_log, LOG__DEBUG
    from bleep.core.errors import BLEEPError, TimeoutError as _BleepTimeout
    from bleep.bt_ref.constants import RESULT_ERR

    obj = bus.get_object(_OBEX_SERVICE, transfer_path)
    props = dbus.Interface(obj, DBUS_PROPERTIES)

    start = time.time()
    while True:
        try:
            status = str(props.Get(_OBEX_TRANSFER_IFACE, "Status")).lower()
        except dbus.exceptions.DBusException:
            print_and_log(
                f"[{label}] Transfer object removed before status could be read "
                f"(fast-completion race) — caller will verify outcome",
                LOG__DEBUG,
            )
            return {"status": "removed"}
        if status in ("complete", "error"):
            break
        if (time.time() - start) > timeout:
            raise _BleepTimeout(f"{label} transfer")
        time.sleep(0.3)

    result: Dict[str, Any] = {"status": status}
    for prop in ("Transferred", "Size", "Filename"):
        try:
            val = props.Get(_OBEX_TRANSFER_IFACE, prop)
            key = prop.lower()
            result[key] = int(val) if prop != "Filename" else str(val)
        except Exception:
            pass

    if status != "complete":
        raise BLEEPError(f"{label} transfer failed (Status={status})", RESULT_ERR)
    return result


# Profile → the on-device sharing toggle a user typically must enable for the
# OBEX session to be authorised. Used to make CreateSession diagnostics actionable.
_SHARE_FEATURE = {
    "PBAP": "Contact Sharing",
    "MAP": "Message Access (SMS/message sharing)",
    "OPP": "file receiving",
    "FTP": "file sharing",
    "SYNC": "IrMC synchronisation / contact sharing",
    "BIP": "image sharing",
}

# Profile-specific advice appended to the *unknown-variant* diagnostic. BIP's
# ``Image1`` interface is [experimental] in BlueZ, so the most common cause of a
# generic CreateSession failure is obexd not running with ``--experimental``.
_EXTRA_HINT = {
    "BIP": "note: BIP requires obexd to run with --experimental",
}


def obex_session_error(
    exc: "dbus.exceptions.DBusException",
    mac_address: str,
    *,
    profile: str,
    service_hint: str | None = None,
    log: bool = True,
):
    """Map an obexd ``CreateSession`` D-Bus failure to a Convention-aligned error.

    Centralises the actionable diagnostics for the common OBEX session-time
    failure modes shared by PBAP / MAP / OPP / FTP, so each profile module does
    not re-implement them.  Returns a :class:`bleep.core.errors.BLEEPError`
    (never raises); callers do ``raise obex_session_error(...) from exc``.

    Known variants get a curated message + mapped ``RESULT_ERR_*`` code:
      * ``Too short header in packet``     → stale device OBEX state (restart)
      * ``Transport got disconnected``     → sharing toggle likely disabled
      * ``NoReply`` / ``Timed out``        → device asleep/locked or unauthorised
      * ``Unable to find service record``  → transient session-time SDP failure

    Anything else is delegated to the canonical
    :func:`bleep.core.errors.map_dbus_error` (which handles ``NotAuthorized``,
    ``NotReady``, ``NoReply``, signature errors, etc.).
    """
    from bleep.core.errors import BLEEPError, map_dbus_error
    from bleep.core.log import print_and_log, LOG__GENERAL
    from bleep.bt_ref.constants import (
        RESULT_ERR_WRONG_STATE,
        RESULT_ERR_NOT_CONNECTED,
        RESULT_ERR_NO_REPLY,
        RESULT_ERR_UNKNOWN_SERVCE,
    )

    name = exc.get_dbus_name()
    msg = exc.get_dbus_message() or str(exc)
    low = msg.lower()
    share = _SHARE_FEATURE.get(profile, "the relevant Bluetooth sharing option")
    svc = service_hint or profile

    def _log(*lines: str) -> None:
        if log:
            print_and_log("\n".join(lines), LOG__GENERAL)

    if "too short header" in low:
        _log(
            f"[-] OBEX CreateSession failed: 'Too short header in packet'",
            f"    This indicates stale OBEX state on the target device.",
            f"    SOLUTION: Restart the target device to clear OBEX buffers.",
            f"    Alternative: 'bluetoothctl disconnect {mac_address}' then reconnect.",
        )
        return BLEEPError(
            f"OBEX CreateSession failed: Too short header in packet. "
            f"This indicates stale OBEX state on device {mac_address}. "
            f"SOLUTION: Restart the target device to clear OBEX buffers and retry. "
            f"Full D-Bus error: {name}: {msg}",
            RESULT_ERR_WRONG_STATE,
        )

    if "transport got disconnected" in low or ("transport" in low and "disconnect" in low):
        _log(
            f"[-] OBEX transport disconnected during session creation.",
            f"    The target device may not have '{share}' enabled.",
            f"    Solutions:",
            f"    1. On the target, Bluetooth settings → enable '{share}'",
            f"    2. Accept the {profile} access prompt on the target if one appeared",
            f"    3. Restart the target device and retry",
        )
        return BLEEPError(
            f"OBEX transport disconnected — the target device may not have "
            f"'{share}' enabled (check Bluetooth settings on {mac_address}). "
            f"Full D-Bus error: {name}: {msg}",
            RESULT_ERR_NOT_CONNECTED,
        )

    if "noreply" in low or "no reply" in low or "timed out" in low or "timeout" in low:
        _log(
            f"[-] OBEX CreateSession failed: device not responding.",
            f"    Solutions:",
            f"    1. Wake/unlock the target device (screen locked blocks {profile})",
            f"    2. Ensure '{share}' is enabled and accept any on-device {profile} prompt",
            f"    3. Disconnect and reconnect: bluetoothctl disconnect {mac_address}",
            f"    4. Restart the target device",
        )
        return BLEEPError(
            f"OBEX CreateSession failed: device not responding. Ensure {mac_address} "
            f"is in range, awake/unlocked, and has '{share}' enabled; accept any "
            f"on-device {profile} prompt. Full D-Bus error: {name}: {msg}",
            RESULT_ERR_NO_REPLY,
        )

    if "unable to find service record" in low:
        _log(
            f"[-] OBEX CreateSession failed: obexd could not retrieve the {profile} "
            f"service record. Two possibilities:",
            f"    • {svc} is NOT advertised by this target — it may not support "
            f"{profile} (run 'classic-enum' or 'classic-map … instances' to check).",
            f"    • {svc} IS advertised but obexd's session-time SDP lookup transiently "
            f"failed (common on honeypot / flaky targets).",
            f"    If advertised: watch the target, accept any {profile} prompt, then "
            f"retry — or 'bluetoothctl disconnect {mac_address}' and reconnect; a device "
            f"restart also clears stale OBEX state.",
        )
        return BLEEPError(
            f"OBEX CreateSession failed: {profile} service record not retrievable at "
            f"session time on {mac_address} — either {svc} is not advertised (target may "
            f"not support {profile}) or the advertised record transiently failed obexd's "
            f"SDP lookup (accept any on-device prompt, then retry/reconnect). "
            f"Full D-Bus error: {name}: {msg}",
            RESULT_ERR_UNKNOWN_SERVCE,
        )

    # Unknown variant — defer to the canonical D-Bus→BLEEPError converter,
    # appending any profile-specific hint (e.g. BIP's --experimental note).
    mapped = map_dbus_error(exc)
    hint = _EXTRA_HINT.get(profile)
    if hint:
        _log(f"[-] {profile} CreateSession failed — {hint}.")
        return BLEEPError(f"{mapped.args[0]} ({hint})", getattr(mapped, "code", None) or 1)
    return mapped


def cancel_obex_transfer(bus: dbus.Bus, transfer_path: str) -> None:
    """Request cancellation of an in-progress ``Transfer1``."""
    obj = bus.get_object(_OBEX_SERVICE, transfer_path)
    transfer = dbus.Interface(obj, _OBEX_TRANSFER_IFACE)
    transfer.Cancel()


def unwrap_dbus(val: Any) -> Any:
    """Recursively unwrap D-Bus types to native Python types."""
    if isinstance(val, dbus.String):
        return str(val)
    if isinstance(val, (dbus.Int16, dbus.Int32, dbus.Int64,
                        dbus.UInt16, dbus.UInt32, dbus.UInt64, dbus.Byte)):
        return int(val)
    if isinstance(val, dbus.Boolean):
        return bool(val)
    if isinstance(val, dbus.Double):
        return float(val)
    if isinstance(val, dbus.Array):
        return [unwrap_dbus(item) for item in val]
    if isinstance(val, dbus.Dictionary):
        return {str(k): unwrap_dbus(v) for k, v in val.items()}
    return val
