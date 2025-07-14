from __future__ import annotations

"""bleep.ble_ops.structural – Small helper factories used across BLE-ops modules.

These helpers were previously defined inside the enormous
`Functions/structural_functions.py` file from the monolithic code-base.  They
are now provided here as lightweight, dependency-free factories so that other
refactored modules (e.g. :pymod:`bleep.ble_ops.ctf`) can import them directly
without relying on the legacy *Functions/* tree.
"""

__all__ = [
    "create_and_return__gatt__service_json",
    "create_and_return__gatt__characteristic_json",
    "create_and_return__gatt__descriptor_json",
]


def create_and_return__gatt__service_json() -> dict:
    """Return an empty GATT *service* JSON skeleton matching BlueZ output."""
    return {
        "UUID": "",  # str
        "Primary": None,  # bool | None
        "Includes": None,  # list | None
        "Handle": None,  # int | None (uint16)
        "Value": None,  # list[int] | None – present only after explicit ReadValue
        "Device": None,  # object path | None – owning BlueZ Device
        "Characteristics": {},
    }


def create_and_return__gatt__characteristic_json() -> dict:
    """Return an empty GATT *characteristic* JSON skeleton."""
    return {
        "UUID": "",  # str
        "Service": None,  # object path | None
        "Value": None,  # list[int] | None (byte array)
        "WriteAcquired": None,  # bool | None
        "NotifyAcquired": None,  # bool | None
        "Notifying": None,  # bool | None – active notify/indicate status
        "Notify": None,  # bool | None – legacy name kept for backward compat
        "Flags": None,  # list[str] | None
        "Handle": None,  # int | None (uint16)
        "MTU": None,  # int | None (uint16)
        "Descriptors": {},
    }


def create_and_return__gatt__descriptor_json() -> dict:
    """Return an empty GATT *descriptor* JSON skeleton."""
    return {
        "UUID": "",  # str
        "Characteristic": None,  # object path | None
        "Value": None,  # list[int] | None (byte array)
        "Flags": None,  # list[str] | None
        "Handle": None,  # int | None (uint16)
    } 