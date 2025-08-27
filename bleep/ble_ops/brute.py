"""bleep.ble_ops.brute – multi-read / brute-write helpers

These utilities iterate over the characteristic mapping returned by
`connect_and_enumerate__bluetooth__low_energy` (or existing Classic
enumerators) and perform bulk read / write actions.  They purposefully
*reuse* the high-level read/write methods already exposed by the device
wrapper – no direct D-Bus calls are introduced.

The helpers are designed for diagnostics / CTF exercises and are **opt-in**;
no existing workflows are altered.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple, Union, Optional

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.core import errors as _errors

__all__ = [
    "brute_read_all",
    "brute_write_all",
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def brute_read_all(
    device,
    mapping: Dict[str, Any] | None = None,
    *,
    delay: float = 0.05,
) -> Dict[str, Union[bytes, str]]:
    """Read *every* characteristic that is listed as readable.

    Parameters
    ----------
    device
        Connected BLE device wrapper (system_dbus__bluez_device__low_energy).
    mapping
        The characteristic mapping as returned by the *_enumerate* helper.  If
        *None*, the device's cached ``ble_device__mapping`` is used (which is
        populated after `services_resolved()`).
    delay
        Seconds to wait between consecutive reads to avoid overwhelming the
        controller.

    Returns
    -------
    dict
        ``{char_uuid_or_label: value_or_error_string}``
    """

    if mapping is None:
        mapping = getattr(device, "ble_device__mapping", {})
        if not mapping:
            # Fallback: trigger a shallow enumeration
            try:
                _ = device.services_resolved(deep=False)
                mapping = getattr(device, "ble_device__mapping", {})
            except Exception as exc:  # pragma: no cover – defensive
                raise _errors.FailedException(f"Failed to fetch mapping: {exc}")

    results: Dict[str, Union[bytes, str]] = {}

    for svc_uuid, svc_data in mapping.items():
        chars = svc_data.get("chars", {})
        for char_uuid, char_data in chars.items():
            label = char_data.get("label", char_uuid)
            if not char_data.get("properties", {}).get("read", False):
                continue  # skip non-readable
            try:
                val = device.read_characteristic(char_uuid)
                results[label] = val
                print_and_log(f"[brute-read] {label}: {val}", LOG__DEBUG)
            except Exception as exc:
                results[label] = f"ERROR: {exc}"
                print_and_log(f"[brute-read] {label}: ERROR {exc}", LOG__DEBUG)
            time.sleep(delay)

    return results


def brute_write_all(
    device,
    payload: Union[bytes, bytearray, str, int, List[int]],
    mapping: Dict[str, Any] | None = None,
    *,
    delay: float = 0.05,
) -> Dict[str, str]:
    """Attempt to write *payload* to every writable characteristic.

    The helper respects the existing write method on the device and silently
    skips characteristics lacking the *write* property.

    Returns a dict ``{char_uuid_or_label: "OK"|"ERROR: ..."}``.
    """

    from bleep.ble_ops.ctf import _to_bytearray  # reuse converter without duplication

    if mapping is None:
        mapping = getattr(device, "ble_device__mapping", {})
        if not mapping:
            try:
                _ = device.services_resolved(deep=False)
                mapping = getattr(device, "ble_device__mapping", {})
            except Exception as exc:  # pragma: no cover
                raise _errors.FailedException(f"Failed to fetch mapping: {exc}")

    results: Dict[str, str] = {}
    payload_bytes = _to_bytearray(payload)

    for svc_uuid, svc_data in mapping.items():
        chars = svc_data.get("chars", {})
        for char_uuid, char_data in chars.items():
            label = char_data.get("label", char_uuid)
            if not char_data.get("properties", {}).get("write", False):
                continue
            try:
                device.write_characteristic(char_uuid, payload_bytes)
                results[label] = "OK"
                print_and_log(f"[brute-write] {label}: OK", LOG__DEBUG)
            except Exception as exc:
                results[label] = f"ERROR: {exc}"
                print_and_log(f"[brute-write] {label}: ERROR {exc}", LOG__DEBUG)
            time.sleep(delay)

    return results 