"""Debug command for HID device identification.

Command: chid — show HID classification for the connected device.
"""

from __future__ import annotations

from typing import List

from bleep.modes.debug_state import DebugState


def cmd_chid(args: List[str], state: DebugState) -> None:
    """Display HID classification for the connected Classic or LE device."""
    device = state.current_device
    if not device:
        print("[-] No device connected. Use 'connect <mac>' or 'cconnect <mac>' first")
        return

    from bleep.analysis.device_type_classifier import classify_hid

    context: dict = {}

    if state.current_mode == "classic":
        try:
            context["device_class"] = device.get_device_class()
        except Exception:
            pass
        try:
            context["uuids"] = device.get_supported_profiles()
        except Exception:
            context["uuids"] = []
    else:
        try:
            props = device.get_properties()
            context.update(props)
        except Exception:
            pass

    hid = classify_hid(context)
    if hid is None:
        print("[*] This device does not appear to be a HID")
        return

    print(f"[+] HID Classification for {device.mac_address}:")
    print(f"    Type:            {hid.hid_type}")
    print(f"    Subclass:        {hid.subclass_label}")
    if hid.reconnect_mode:
        print(f"    Reconnect Mode:  {hid.reconnect_mode}")
