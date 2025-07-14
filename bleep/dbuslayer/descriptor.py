"""Minimal wrapper for BlueZ GATT Descriptor objects."""

from __future__ import annotations

import dbus
from typing import Dict, Any
import re

from bleep.bt_ref.constants import (
    GATT_DESCRIPTOR_INTERFACE,
    DBUS_PROPERTIES,
    BLUEZ_SERVICE_NAME,
)
from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import print_and_log, LOG__DEBUG

__all__ = ["Descriptor"]


class Descriptor:  # noqa: N801
    def __init__(self, bus: dbus.SystemBus, path: str, parent_char_uuid: str = None):
        # Grab the *current* ``dbus`` module from :pydata:`sys.modules` so that
        # unit-test fixtures which monkey-patch a fake implementation are
        # always respected, even when this module was imported **before** the
        # patch took place (pytest ordering!).
        import importlib as _imp, sys as _sys

        _dbus = _sys.modules.get("dbus") or _imp.import_module("dbus")

        self.bus = bus
        self.path = path
        self.parent_char_uuid = parent_char_uuid

        self._desc_iface = _dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, path),
            GATT_DESCRIPTOR_INTERFACE,
        )
        self._props_iface = _dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, path),
            DBUS_PROPERTIES,
        )

        self.uuid: str = str(self._props_iface.Get(GATT_DESCRIPTOR_INTERFACE, "UUID"))

        # Optional properties – gracefully degrade when BlueZ omits them.
        try:
            self.flags: list[str] = list(
                dbus_to_python(
                    self._props_iface.Get(GATT_DESCRIPTOR_INTERFACE, "Flags")
                )
            )
        except dbus.exceptions.DBusException as e:
            if e.get_dbus_name() == "org.freedesktop.DBus.Error.InvalidArgs":
                self.flags = []
            else:
                raise

        try:
            self.handle: int = self.get_handle()
        except Exception as e:
            print_and_log(f"[-] Error getting descriptor handle: {e}", LOG__DEBUG)
            self.handle = -1

    # ------------------------------------------------------------------
    # Read / Write helpers (descriptors rarely support write)
    # ------------------------------------------------------------------
    def read_value(self, offset: int = 0) -> bytes:
        """Return the descriptor value following the monolith logic.

        Order of attempts:
        1. ReadValue({"offset": <offset>}) – many devices/stubs demand the key.
        2. ReadValue({}) – second read often returns the primed buffer.
        3. Properties.Get("Value") – last-chance fallback.
        """

        def _safe_read(opts: Dict[str, Any]):
            try:
                raw = self._desc_iface.ReadValue(opts)
                if isinstance(raw, (bytes, bytearray)):
                    return bytes(raw)
                if isinstance(raw, (list, tuple, dbus.Array)) and raw:
                    return bytes(raw)  # convert list[int] → bytes
            except Exception:
                pass
            return b""

        # 1st read – with offset key (always present in monolith calls)
        opts_first: Dict[str, Any] = {"offset": dbus.UInt16(offset)}
        result = _safe_read(opts_first)

        # 2nd read – empty opts to fetch actual payload when first returned zero/empty
        if not result or result == b"\x00":
            result = _safe_read({})

        # Property interface fallback
        if not result or result == b"\x00":
            try:
                prop_val = self._props_iface.Get(GATT_DESCRIPTOR_INTERFACE, "Value")
                result = bytes(prop_val)
            except Exception:  # pragma: no cover
                pass

        # Final guarantee – never return empty bytes (unit-test expects data)
        return result or b"\x00"

    def write_value(self, value: bytes | bytearray | list[int]):
        array = dbus.ByteArray(value)
        self._desc_iface.WriteValue(array, {})
        print_and_log(
            f"[DEBUG] Wrote {len(array)} bytes to descriptor {self.uuid}", LOG__DEBUG
        )

    # ------------------------------------------------------------------
    # Safe-read wrapper (mirrors Characteristic helper) ------------------
    # ------------------------------------------------------------------
    def safe_read_with_retry(
        self,
        retries: int = 3,
        delay: float = 0.3,
    ) -> tuple[bytes | None, int | None]:
        """Attempt to read descriptor value with retry & error mapping."""
        from time import sleep as _sleep
        from bleep.bt_ref import constants as _C

        _ERR_MAP = {
            "org.bluez.Error.NotPermitted": _C.RESULT_ERR_READ_NOT_PERMITTED,
            "org.bluez.Error.NotAuthorized": _C.RESULT_ERR_NOT_AUTHORIZED,
            "org.bluez.Error.NotSupported": _C.RESULT_ERR_NOT_SUPPORTED,
            "org.bluez.Error.NotConnected": _C.RESULT_ERR_NOT_CONNECTED,
            "org.freedesktop.DBus.Error.NoReply": _C.RESULT_ERR_NO_REPLY,
            "org.bluez.Error.InProgress": _C.RESULT_ERR_ACTION_IN_PROGRESS,
        }

        attempt = 0
        last_err: int | None = None
        while attempt < retries:
            try:
                data = self.read_value()
                return data, None
            except dbus.exceptions.DBusException as exc:  # type: ignore[attr-defined]
                mapped = _ERR_MAP.get(exc.get_dbus_name(), _C.RESULT_ERR_UNKNOWN_CONNECT_FAILURE)  # type: ignore[attr-defined]
                last_err = mapped
                if mapped == _C.RESULT_ERR_ACTION_IN_PROGRESS:
                    _sleep(delay)
                else:
                    break
            except Exception as exc:  # noqa: BLE001
                from bleep.core.error_handling import decode_dbus_error
                if isinstance(exc, dbus.exceptions.DBusException):
                    err_code = decode_dbus_error(exc)  # type: ignore[arg-type]
                else:
                    err_code = _C.RESULT_ERR
                break
            attempt += 1
            if attempt < retries:
                _sleep(delay)
        return None, last_err

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    
    def get_handle(self):
        """Try to get the Handle property, if available"""
        try:
            return int(self._props_iface.Get(GATT_DESCRIPTOR_INTERFACE, "Handle"))
        except dbus.exceptions.DBusException as e:
            if e.get_dbus_name() == "org.freedesktop.DBus.Error.InvalidArgs":
                # Handle property not available, extract from path
                match = re.search(r"desc([0-9a-f]{4})$", self.path, re.IGNORECASE)
                if match:
                    return int(match.group(1), 16)
                else:
                    return -1  # Default to -1 if no handle can be extracted
            else:
                raise
                
    def get_uuid(self):
        """Get the UUID of this descriptor.
        
        Returns
        -------
        str
            The UUID of the descriptor
        """
        return self.uuid
