"""Debug command for HID device identification.

Command: ``chid [MAC]`` — HID classification for either the connected device
(connected variant) or a given MAC without a live session (connectionless
variant, mirroring the CLI ``hid-info`` default). Both variants share the
CLI's evidence builder (:mod:`bleep.ble_ops.hid`) so they cannot drift.
"""

from __future__ import annotations

from typing import List

from bleep.modes.debug_state import DebugState


def cmd_chid(args: List[str], state: DebugState) -> None:
    """Display HID classification for a connected device or an explicit MAC."""
    from bleep.analysis.device_type_classifier import classify_hid
    from bleep.ble_ops.hid import build_hid_context, context_from_device

    mac_arg = args[0].strip() if args and args[0].strip() else None

    if mac_arg:
        # Connectionless variant (mirrors CLI `hid-info <MAC>`); works with no
        # live session.
        label = mac_arg.upper()
        context = build_hid_context(label, connect=False)
    else:
        device = state.current_device
        if not device:
            print("[-] No device connected and no MAC given. "
                  "Use 'connect <mac>'/'cconnect <mac>' first, or 'chid <MAC>'")
            return
        mode = "classic" if state.current_mode == "classic" else "le"
        context = context_from_device(device, mode=mode)
        label = device.mac_address

    hid = classify_hid(context)
    if hid is None:
        print(f"[*] {label} does not appear to be a HID")
        return

    print(f"[+] HID Classification for {label}:")
    print(f"    Type:            {hid.hid_type}")
    print(f"    Subclass:        {hid.subclass_label}")
    if hid.reconnect_mode:
        print(f"    Reconnect Mode:  {hid.reconnect_mode}")
