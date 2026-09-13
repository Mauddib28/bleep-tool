"""Shared HID-evidence assembly for :func:`classify_hid` (CDU-M1.6).

A single builder used by *both* surfaces — the CLI ``hid-info`` command and the
debug-shell ``chid`` command — so connectionless and connected HID
classification assemble their evidence dict identically and cannot drift.

``classify_hid`` (``bleep/analysis/device_type_classifier.py``) is a pure
function over an evidence dict; the two variants differ only in *which* evidence
is obtainable:

* **Connectionless** (no link): Class-of-Device + advertised profile UUIDs, read
  from BlueZ's cached discovery properties. Cannot read
  ``org.bluez.Input1.ReconnectMode`` (BlueZ instantiates ``Input1`` only for a
  connected/bonded HID) and usually lacks LE ``Appearance``.
* **Connected**: additionally LE ``Appearance`` and, when present,
  ``Input1.ReconnectMode`` (richer typing incl. reconnect behaviour).
"""

from __future__ import annotations

from typing import Any, Dict, Optional


_INPUT1_INTERFACE = "org.bluez.Input1"


def context_from_classic(device) -> Dict[str, Any]:
    """Evidence from a Classic device object: Class-of-Device + profile UUIDs.

    These are available even connectionless (cached discovery props), so this is
    both the CLI ``hid-info`` default and the debug ``chid`` Classic path.
    """
    context: Dict[str, Any] = {}
    try:
        context["device_class"] = device.get_device_class()
    except Exception:
        pass
    try:
        context["uuids"] = device.get_supported_profiles()
    except Exception:
        context["uuids"] = []
    return context


def context_from_le(device) -> Dict[str, Any]:
    """Evidence from an LE device object: appearance, UUIDs, Class, Input1.

    Uses the LE accessors (``get_device_appearance`` / ``get_uuids`` /
    ``get_device_class``) plus ``Input1.ReconnectMode`` when the peer is
    connected/bonded. (Fixes the previous debug path, which called a
    non-existent ``get_properties`` and therefore always yielded no evidence.)
    """
    context: Dict[str, Any] = {}

    try:
        appearance = device.get_device_appearance()
    except Exception:
        appearance = None
    if appearance is not None:
        context["appearance"] = int(appearance)

    try:
        uuids = device.get_uuids()
    except Exception:
        uuids = None
    context["uuids"] = list(uuids) if uuids else []

    try:
        device_class = device.get_device_class()
    except Exception:
        device_class = None
    if device_class is not None:
        context["device_class"] = int(device_class)

    reconnect = None
    getter = getattr(device, "_get_optional_property", None)
    if callable(getter):
        try:
            reconnect = getter("ReconnectMode", _INPUT1_INTERFACE)
        except Exception:
            reconnect = None
    if reconnect is not None:
        context["_Input1"] = {"ReconnectMode": str(reconnect)}

    return context


def context_from_device(device, *, mode: str = "classic") -> Dict[str, Any]:
    """Assemble the :func:`classify_hid` evidence dict from a live device object.

    ``mode="classic"`` uses the Classic accessors; any other value
    (``"le"``/``"ble"``) uses the LE accessors. Used by the debug shell's
    connected path (``chid`` with a live ``state.current_device``).
    """
    if mode == "classic":
        return context_from_classic(device)
    return context_from_le(device)


def build_hid_context(
    mac: str,
    *,
    connect: bool = False,
    adapter_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble HID evidence for a Classic MAC address (no live session needed).

    * ``connect=False`` (CLI ``hid-info`` default; debug ``chid <MAC>``):
      connectionless — read only the cached discovery props.
    * ``connect=True`` (CLI ``hid-info --connect``): bring the link up so
      ``org.bluez.Input1`` becomes queryable, then fold in ``ReconnectMode``.
    """
    from bleep.dbuslayer.device_classic import (
        system_dbus__bluez_device__classic as ClassicDevice,
    )

    device = (
        ClassicDevice(mac, adapter_name=adapter_name)
        if adapter_name
        else ClassicDevice(mac)
    )

    if connect:
        try:
            if not device.is_connected():
                device.connect()
        except Exception:
            pass

    context = context_from_classic(device)

    if connect:
        props_iface = getattr(device, "_props_iface", None)
        if props_iface is not None:
            try:
                reconnect = props_iface.Get(_INPUT1_INTERFACE, "ReconnectMode")
                context["_Input1"] = {"ReconnectMode": str(reconnect)}
            except Exception:
                pass

    return context
