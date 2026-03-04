"""Connect, disconnect, and device-info commands for debug mode."""

from __future__ import annotations

import time
from typing import List

import dbus

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.bt_ref.utils import get_name_from_uuid
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
from bleep.ble_ops.conversion import format_device_class

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
    """Connect to a device by MAC address.

    Auto-detects transport type (BR/EDR vs BLE) and routes to the appropriate
    connection method.
    """
    if not args:
        print("Usage: connect <MAC>")
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

    transport = get_device_transport(device_path)
    print_and_log(f"[*] Detected transport: {transport}", LOG__DEBUG)

    if transport == "le":
        _connect_le(mac, device_path, state)
    else:
        _connect_classic(mac, device_path, state)


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
        print("[-] Connection failed – D-Bus exploration still available via 'interfaces', 'props'")


def _connect_classic(mac: str, device_path: str, state: DebugState) -> None:
    """Classic connect with profile fallback to SDP + keepalive."""
    try:
        from bleep.ble_ops import connect_and_enumerate__bluetooth__classic as _c_enum
        dev, svc_map = _c_enum(mac)
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
            mac = state.current_device.mac_address
            state.current_device.disconnect()
            print_and_log(f"[+] Disconnected from {mac}", LOG__GENERAL)
        except Exception as exc:
            print_and_log(f"[-] Disconnect failed: {exc}", LOG__DEBUG)

    state.current_device = None
    state.current_mapping = None
    state.current_path = None
    state.current_mode = "ble"


# ---------------------------------------------------------------------------
# Info command
# ---------------------------------------------------------------------------

def cmd_info(args: List[str], state: DebugState) -> None:
    """Show device information."""
    if not state.current_device and not state.current_path:
        print("[-] No device connected or paired in this session")
        return

    if state.current_device:
        if state.current_mode == "ble":
            device_path = state.current_device._device_path
            device_addr = state.current_device.mac_address
            device_name = getattr(state.current_device, "name", "Unknown")
            device_addr_type = getattr(state.current_device, "address_type", "Unknown")

            print(f"[+] Device: {device_name}")
            print(f"  Address: {device_addr} ({device_addr_type})")
            print(f"  Path: {device_path}")

            try:
                bus = dbus.SystemBus()
                obj = bus.get_object("org.bluez", device_path)
                props_iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
                props = props_iface.GetAll("org.bluez.Device1")
                print("[*] Device Properties:")
                from bleep.modes.debug_gatt import show_properties
                show_properties(props, state.detailed_view)
            except Exception as e:
                print(f"[-] Error getting additional info: {e}")
        else:
            info = state.current_device.get_device_info()
            print("[+] Classic Device Info:")
            for k, v in info.items():
                print(f"  {k}: {v}")
            if state.current_mapping:
                print(f"  SDP services: {len(state.current_mapping)} (use 'cservices' to list)")
    else:
        _info_from_dbus_path(state.current_path, state)


def _info_from_dbus_path(device_path: str, state: DebugState) -> None:
    """Display device properties directly from D-Bus when no device wrapper exists."""
    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", device_path)
        props_iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        props = props_iface.GetAll("org.bluez.Device1")

        name = str(props.get("Alias", props.get("Name", "Unknown")))
        addr = str(props.get("Address", "Unknown"))
        paired = bool(props.get("Paired", False))
        trusted = bool(props.get("Trusted", False))
        connected = bool(props.get("Connected", False))

        print(f"[+] Device: {name}")
        print(f"  Address:   {addr}")
        print(f"  Path:      {device_path}")
        print(f"  Paired:    {paired}")
        print(f"  Trusted:   {trusted}")
        print(f"  Connected: {connected}")

        addr_type = str(props.get("AddressType", ""))
        if addr_type:
            print(f"  AddrType:  {addr_type}")

        dev_class = props.get("Class")
        if dev_class is not None:
            class_str = format_device_class(int(dev_class))
            print(f"  Class:     0x{int(dev_class):06X} ({class_str})")

        rssi = props.get("RSSI")
        if rssi is not None:
            print(f"  RSSI:      {int(rssi)} dBm")

        uuids = [str(u) for u in props.get("UUIDs", [])]
        if uuids:
            print(f"  UUIDs:     {len(uuids)} service(s)")
            for u in uuids:
                label = get_name_from_uuid(u) or u
                print(f"    {label}")

        if not connected:
            print("\n[*] Device is paired but not connected.")
            print("    Use 'connect <MAC>' or 'ckeep <MAC> --first' to reconnect.")

    except dbus.exceptions.DBusException as exc:
        print(f"[-] Cannot read D-Bus properties: {format_dbus_error(exc)}")
    except Exception as exc:
        print(f"[-] Error reading device info: {exc}")
