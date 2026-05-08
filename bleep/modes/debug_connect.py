"""Connect, disconnect, and device-info commands for debug mode."""

from __future__ import annotations

import time
from typing import List

import dbus

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.bt_ref.utils import get_name_from_uuid
from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
from bleep.ble_ops.common.conversion import format_device_class

from bleep.modes.debug_state import DebugState
from bleep.modes.debug_dbus import format_dbus_error, print_detailed_dbus_error


# ---------------------------------------------------------------------------
# Transport detection
# ---------------------------------------------------------------------------

def get_device_transport(device_path: str) -> str:
    """Determine the transport type of a device from its D-Bus properties.

    Returns ``"br-edr"``, ``"le"``, or ``"dual"``.
    """
    try:
        bus = dbus.SystemBus()
        props = dbus.Interface(
            bus.get_object("org.bluez", device_path),
            "org.freedesktop.DBus.Properties",
        )
        all_props = props.GetAll("org.bluez.Device1")
        addr_type = str(all_props.get("AddressType", ""))
        has_gatt = bool(all_props.get("ServicesResolved", False))
        uuids = [str(u) for u in all_props.get("UUIDs", [])]
        classic_indicators = any(
            u.startswith("0000110") or u.startswith("0000111") or
            u.startswith("0000112") for u in uuids
        )
        le_indicators = has_gatt or addr_type == "random"
        if classic_indicators and le_indicators:
            return "dual"
        if le_indicators:
            return "le"
        return "br-edr"
    except dbus.exceptions.DBusException:
        return "br-edr"


def find_device_path(target_mac: str) -> str | None:
    """Find a Device1 object path by MAC from BlueZ's managed objects."""
    try:
        bus_local = dbus.SystemBus()
        om = dbus.Interface(
            bus_local.get_object("org.bluez", "/"),
            "org.freedesktop.DBus.ObjectManager",
        )
        for path, ifaces in om.GetManagedObjects().items():
            dev = ifaces.get("org.bluez.Device1")
            if dev and str(dev.get("Address", "")).upper() == target_mac:
                return str(path)
    except dbus.exceptions.DBusException:
        pass
    return None


# ---------------------------------------------------------------------------
# Connect / Disconnect
# ---------------------------------------------------------------------------

def cmd_connect(args: List[str], state: DebugState) -> None:
    """Connect to a BLE device by MAC address and enumerate GATT services.

    This command is BLE-only by design for directed LE testing in debug
    mode.  For Bluetooth Classic targets use ``cconnect`` instead.
    """
    if not args:
        print("Usage: connect <MAC>  (BLE only — use 'cconnect' for Classic)")
        return

    mac = args[0].upper()
    print_and_log(f"[*] Connecting to {mac}…", LOG__GENERAL)

    if state.current_device:
        try:
            if state.current_device.is_connected():
                state.current_device.disconnect()
        except Exception:
            pass
        state.current_device = None
        state.current_mapping = None

    device_path = find_device_path(mac)
    if device_path is None:
        print_and_log(f"[*] Device {mac} not cached – running discovery…", LOG__GENERAL)
        from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as Adapter
        adapter = Adapter()
        adapter.set_discovery_filter({"Transport": "auto"})
        adapter.run_scan__timed(duration=10)
        device_path = find_device_path(mac)
        if device_path is None:
            print(f"[-] Device {mac} not found")
            return

    _connect_le(mac, device_path, state)


def _connect_le(mac: str, device_path: str, state: DebugState) -> None:
    """BLE connect + GATT enumeration."""
    try:
        dev, mapping, _, _ = _connect_enum(mac)
        state.current_device = dev
        state.current_mapping = mapping
        state.current_mode = "ble"
        state.current_path = dev._device_path
        print_and_log(f"[+] Connected to {mac} (BLE)", LOG__GENERAL)
    except Exception as exc:
        print_and_log(f"[-] BLE connection failed: {exc}", LOG__DEBUG)
        state.current_path = device_path
        transport = get_device_transport(device_path)
        if transport in ("br-edr", "dual"):
            print(f"[-] BLE connection failed – device is {transport}; use 'cconnect {mac}' instead")
        else:
            print("[-] Connection failed – D-Bus exploration still available via 'interfaces', 'props'")


def _connect_classic(mac: str, device_path: str, state: DebugState) -> None:
    """Classic connect with profile fallback to SDP + keepalive."""
    try:
        from bleep.ble_ops import connect_and_enumerate__bluetooth__classic as _c_enum
        dev, svc_map = _c_enum(mac, debug_state=state)
        state.current_device = dev
        state.current_mapping = svc_map
        state.current_mode = "classic"
        state.current_path = dev._device_path
        print_and_log(f"[+] Connected to {mac} (Classic) – {len(svc_map)} RFCOMM services", LOG__GENERAL)
        return
    except Exception as exc:
        print_and_log(f"[*] Classic profile connect failed: {exc}", LOG__DEBUG)

    from bleep.modes.debug_pairing import post_pair_connect_classic
    post_pair_connect_classic(mac, device_path, state)


def cmd_disconnect(args: List[str], state: DebugState) -> None:
    """Disconnect from the current device and close any keepalive socket."""
    if not state.current_device and not state.current_path:
        print("[-] No device connected")
        return

    if state.keepalive_sock:
        try:
            state.keepalive_sock.close()
        except Exception:
            pass
        state.keepalive_sock = None

    if state.current_device:
        try:
            state.current_device.disconnect()
        except Exception as exc:
            print_and_log(f"[-] Disconnect failed: {exc}", LOG__DEBUG)

    state.current_device = None
    state.current_mapping = None
    state.current_path = None
    state.current_mode = "ble"


# ---------------------------------------------------------------------------
# Unified property formatting
# ---------------------------------------------------------------------------

_BOOL_KEYS = {"Blocked", "Connected", "LegacyPairing", "Paired", "Trusted",
              "ServicesResolved"}

_KEY_LABELS = {
    "AddressType":      "Address Type",
    "LegacyPairing":    "Legacy Pairing",
    "ServicesResolved":  "Services Resolved",
    "ServiceData":       "Service Data",
    "TxPower":           "TX Power",
    "ManufacturerData":  "Manufacturer Data",
}


def _format_bool(val, detailed: bool = False) -> str:
    """Format a boolean value.

    With *detailed* the numeric equivalent is appended: ``True (1)``.
    Without it only the word is returned: ``True``.
    """
    b = bool(val)
    if detailed:
        return f"{b} ({1 if b else 0})"
    return str(b)


def _print_unified_props(props: dict, detailed: bool = False) -> None:
    """Print device properties in a uniform format.

    Boolean properties show both human-readable and numeric forms.
    Property labels are Title Case.  Raw captured data (ServiceData,
    UUIDs, ManufacturerData) is printed verbatim.
    """
    import json as _json
    from bleep.bt_ref.utils import get_name_from_uuid

    skip = {"Address", "Adapter", "Alias", "Name"}
    for key in sorted(props.keys()):
        if key in skip:
            continue

        label = _KEY_LABELS.get(key, key)
        value = props[key]

        if key in _BOOL_KEYS:
            print(f"  {label + ':':<20s} {_format_bool(value, detailed)}")
            continue

        if key == "Class":
            if detailed:
                class_str = format_device_class(int(value))
                print(f"  {label + ':':<20s} 0x{int(value):06X} ({class_str})")
            else:
                print(f"  {label + ':':<20s} 0x{int(value):06X}")
            continue

        if key == "RSSI":
            print(f"  {label + ':':<20s} {int(value)} dBm")
            continue
        if key == "TxPower":
            print(f"  {label + ':':<20s} {int(value)} dBm")
            continue

        if key == "UUIDs":
            uuid_list = [str(u) for u in value]
            print(f"  {label + ':':<20s} {len(uuid_list)} service(s)")
            if detailed:
                for u in uuid_list:
                    name = get_name_from_uuid(u) or u
                    print(f"    {u} ({name})" if name != u else f"    {u}")
            else:
                for u in uuid_list:
                    print(f"    {u}")
            continue

        if isinstance(value, (list, dict)):
            print(f"  {label + ':':<20s} {_json.dumps(value, indent=2)}")
        else:
            print(f"  {label + ':':<20s} {value}")


# ---------------------------------------------------------------------------
# Info command
# ---------------------------------------------------------------------------

def cmd_info(args: List[str], state: DebugState) -> None:
    """Show device information with a unified format for BLE and Classic."""
    if not state.current_device and not state.current_path:
        print("[-] No device connected or paired in this session")
        return

    if state.current_device:
        if state.current_mode == "ble":
            _info_ble(state)
        else:
            _info_classic(state)
    else:
        _info_from_dbus_path(state.current_path, state)


def _info_ble(state: DebugState) -> None:
    """Unified BLE device info display."""
    device_path = state.current_device._device_path
    device_addr = state.current_device.mac_address

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", device_path)
        props_iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        props = props_iface.GetAll("org.bluez.Device1")
    except Exception as e:
        print(f"[-] Error getting device properties: {e}")
        return

    name = str(props.get("Alias", props.get("Name", "Unknown")))
    addr_type = str(props.get("AddressType", "Unknown"))

    print(f"[+] Device Info:")
    print(f"  {'Address:':<20s} {device_addr}")
    print(f"  {'Name:':<20s} {name}")
    print(f"  {'Type:':<20s} BLE")
    print(f"  {'Address Type:':<20s} {addr_type}")
    print(f"  {'Path:':<20s} {device_path}")
    _print_unified_props(props, state.detailed_view)


def _info_classic(state: DebugState) -> None:
    """Unified Classic device info display."""
    info = state.current_device.get_device_info()

    name = info.get("name", "Unknown")
    addr = info.get("address", "Unknown")

    d = state.detailed_view
    type_label = "Classic (BR/EDR)" if d else "Classic"

    print(f"[+] Device Info:")
    print(f"  {'Address:':<20s} {addr}")
    print(f"  {'Name:':<20s} {name}")
    print(f"  {'Type:':<20s} {type_label}")
    print(f"  {'Path:':<20s} {getattr(state.current_device, '_device_path', 'N/A')}")

    print(f"  {'Connected:':<20s} {_format_bool(info.get('connected'), d)}")
    print(f"  {'Paired:':<20s} {_format_bool(info.get('paired'), d)}")
    print(f"  {'Trusted:':<20s} {_format_bool(info.get('trusted'), d)}")
    print(f"  {'Blocked:':<20s} {_format_bool(info.get('blocked'), d)}")
    print(f"  {'Legacy Pairing:':<20s} {_format_bool(info.get('legacy_pairing'), d)}")

    dev_class = info.get("device_class")
    if dev_class is not None:
        if d:
            class_str = format_device_class(int(dev_class))
            print(f"  {'Device Class:':<20s} 0x{int(dev_class):06X} ({class_str})")
        else:
            print(f"  {'Device Class:':<20s} 0x{int(dev_class):06X}")

    rssi = info.get("rssi")
    if rssi is not None:
        print(f"  {'RSSI:':<20s} {rssi} dBm")
    tx = info.get("tx_power")
    if tx is not None:
        print(f"  {'TX Power:':<20s} {tx} dBm")

    profiles = info.get("supported_profiles", [])
    if profiles:
        print(f"  {'Profiles:':<20s} {len(profiles)} supported")
        if state.detailed_view:
            from bleep.bt_ref.utils import get_name_from_uuid
            for u in profiles:
                name_p = get_name_from_uuid(u) or u
                print(f"    {u} ({name_p})" if name_p != u else f"    {u}")
        else:
            for u in profiles:
                print(f"    {u}")

    connected_p = info.get("connected_profiles", [])
    if connected_p:
        print(f"  {'Active Profiles:':<20s} {', '.join(str(p) for p in connected_p)}")

    if state.current_mapping:
        print(f"  {'SDP Services:':<20s} {len(state.current_mapping)} (use 'cservices' to list)")


def _info_from_dbus_path(device_path: str, state: DebugState) -> None:
    """Display device properties directly from D-Bus when no device wrapper exists."""
    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", device_path)
        props_iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        props = props_iface.GetAll("org.bluez.Device1")

        name = str(props.get("Alias", props.get("Name", "Unknown")))
        addr = str(props.get("Address", "Unknown"))
        addr_type = str(props.get("AddressType", ""))
        connected = bool(props.get("Connected", False))

        print(f"[+] Device Info:")
        print(f"  {'Address:':<20s} {addr}")
        print(f"  {'Name:':<20s} {name}")
        print(f"  {'Type:':<20s} D-Bus Path (no active wrapper)")
        if addr_type:
            print(f"  {'Address Type:':<20s} {addr_type}")
        print(f"  {'Path:':<20s} {device_path}")
        _print_unified_props(props, state.detailed_view)

        if not connected:
            print("\n[*] Device is paired but not connected.")
            print("    Use 'connect <MAC>' or 'ckeep <MAC> --first' to reconnect.")

    except dbus.exceptions.DBusException as exc:
        print(f"[-] Cannot read D-Bus properties: {format_dbus_error(exc)}")
    except Exception as exc:
        print(f"[-] Error reading device info: {exc}")
