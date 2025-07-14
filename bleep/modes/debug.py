#!/usr/bin/env python3
"""Debug Mode for BLEEP.

This mode provides an interactive debug shell for inspecting Bluetooth devices,
accessing low-level D-Bus interfaces, monitoring properties in real-time, and
manually invoking methods.

Usage:
  python -m bleep -m debug [options]

Options:
  --device <mac>     MAC address of device to connect to
  --no-connect       Start debug shell without connecting to a device
  --monitor          Enable real-time property monitoring
  --timeout <sec>    Monitor timeout (default: 60 seconds)
"""

import argparse
import shlex
import time
import threading
import dbus
import re
from typing import Dict, List, Any, Optional, Tuple
import struct
from xml.dom import minidom
import json

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
from bleep.ble_ops.scan import passive_scan
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
from bleep.core.errors import map_dbus_error, BLEEPError
from bleep.bt_ref.utils import get_name_from_uuid
from bleep.ble_ops.uuid_utils import identify_uuid
from bleep.ble_ops.conversion import format_device_class, decode_appearance

try:
    import gi
    gi.require_version('GLib', '2.0')
    from gi.repository import GLib as gobject
except ImportError:
    print_and_log("[-] Failed to import GLib - monitoring will not work", LOG__DEBUG)
    gobject = None

try:
    import readline
except ImportError:
    # readline not available on Windows
    pass

# Constants
_PROMPT = "BLEEP-DEBUG> "
_DEVICE_PROMPT = "BLEEP-DEBUG[{}]> "

# Global state
_current_device = None
_current_mapping = None
_current_path = None    # Current D-Bus object path
_monitoring = False
_monitor_thread = None
_monitor_stop_event = threading.Event()
_notification_handlers = {}
_detailed_view = False  # Flag to control detailed view mode
_path_history = []      # Stack of previously visited paths
_path_cache = {}        # Cache of introspection results by path


def _print_detailed_dbus_error(exc: Exception) -> None:
    """Print detailed information about a D-Bus exception.

    This function extracts and displays:
    - The full D-Bus error name (e.g., org.freedesktop.DBus.Error.InvalidArgs)
    - The error message and arguments
    - For InvalidArgs errors, it tries to extract the specific method, interface or property name
    - Shows how the error maps to the BLEEP error system
    """
    print("\n[!] D-Bus Error Details:")

    if isinstance(exc, dbus.exceptions.DBusException):
        error_name = exc.get_dbus_name()
        error_msg = str(exc)

        print(f"[-] D-Bus Error: {error_name}")
        print(f"[-] Message: {error_msg}")

        # Extract method/property name for InvalidArgs errors
        if error_name == "org.freedesktop.DBus.Error.InvalidArgs":
            # Try to extract the property or method name from the error message
            prop_match = re.search(r"property '([^']+)'", error_msg)
            method_match = re.search(r"method '([^']+)'", error_msg)
            iface_match = re.search(r"interface '([^']+)'", error_msg)

            if prop_match:
                print(f"[-] Invalid property: {prop_match.group(1)}")
            if method_match:
                print(f"[-] Invalid method: {method_match.group(1)}")
            if iface_match:
                print(f"[-] On interface: {iface_match.group(1)}")

        # Map to BLEEP error system
        try:
            bleep_error = map_dbus_error(exc)
            print(f"[-] Maps to BLEEP error: {type(bleep_error).__name__}")
        except Exception as e:
            print(f"[-] Could not map to BLEEP error: {e}")
    else:
        print(f"[-] Error: {exc}")
        print(f"[-] Type: {type(exc).__name__}")

# TODO: Flesh out the functions below


def _resolve_path(path, current_path=None):
    """Resolve a relative or absolute path to a full D-Bus object path.

    Parameters:
    ----------
    path : str
        The path to resolve
    current_path : str, optional
        The current path to use as a base for relative paths

    Returns:
    -------
    str
        The resolved path
    """
    if not current_path:
        current_path = _current_path or "/org/bluez"

    # If path starts with /, it's absolute
    if path.startswith('/'):
        return path

    # Handle . and ..
    if path == '.':
        return current_path
    elif path == '..':
        # Go up one level
        if current_path == '/':
            return '/'
        return '/'.join(current_path.split('/')[:-1]) or '/'
    elif not path:  # Empty path
        return current_path

    # Relative path - append to current path
    if current_path.endswith('/'):
        return current_path + path
    else:
        return current_path + '/' + path


def _get_object_at_path(path):
    """Get D-Bus object at the specified path.

    Parameters:
    ----------
    path : str
        The path to get the object at

    Returns:
    -------
    dbus.Interface
        The D-Bus interface for the object at the specified path
    """
    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        return obj
    except Exception as e:
        print_and_log(f"[-] Error accessing path {path}: {e}", LOG__DEBUG)
        return None


def _get_interfaces_at_path(path):
    """Get available interfaces at the specified path.

    Parameters:
    ----------
    path : str
        The path to get the interfaces at

    Returns:
    -------
    list
        A list of interface names available at the specified path
    """
    try:
        obj = _get_object_at_path(path)
        if not obj:
            return []
            
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        interfaces = []
        for iface in root.findall("interface"):
            interfaces.append(iface.get("name"))

        return interfaces
    except Exception as e:
        print_and_log(f"[-] Error getting interfaces at {path}: {e}", LOG__DEBUG)
        return []


def _get_child_nodes_at_path(path):
    """Get child nodes at the specified path.

    Parameters:
    ----------
    path : str
        The path to get child nodes from

    Returns:
    -------
    tuple
        A tuple of (directories, interfaces) at the path
    """
    try:
        obj = _get_object_at_path(path)
        if not obj:
            return [], []
            
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        dirs = []
        for node in root.findall("node"):
            node_name = node.get("name")
            if node_name:
                dirs.append(node_name)

        interfaces = _get_interfaces_at_path(path)

        return dirs, interfaces
    except Exception as e:
        print_and_log(f"[-] Error getting child nodes at {path}: {e}", LOG__DEBUG)
        return [], []


def _cmd_ls(args: List[str]) -> None:
    """List contents of the current path or specified path."""
    global _current_path

    # Default to current path if not specified
    if not _current_path:
        if _current_device:
            _current_path = _current_device._device_path
        else:
            _current_path = "/org/bluez"

    # Resolve path if provided
    target_path = _current_path
    if args:
        try:
            target_path = _resolve_path(args[0])
        except Exception as e:
            print(f"[-] Invalid path: {e}")
            return

    try:
        # Verify the path exists
        obj = _get_object_at_path(target_path)
        if not obj:
            print(f"[-] Path does not exist: {target_path}")
            return

        dirs, interfaces = _get_child_nodes_at_path(target_path)

        # Display directories first
        for d in sorted(dirs):
            print(f"[DIR] {d}/")

        # Then interfaces
        for i in sorted(interfaces):
            print(f"[IF]  {i}")

        # Add an empty line at the end
        if dirs or interfaces:
            print()
    except Exception as e:
        print(f"[-] Error listing path {target_path}: {e}")
        print_and_log(f"[-] Error in ls command: {e}", LOG__DEBUG)


def _cmd_cd(args: List[str]) -> None:
    """Change the current D-Bus path."""
    global _current_path, _path_history

    if not _current_path:
        if _current_device:
            _current_path = _current_device._device_path
        else:
            _current_path = "/org/bluez"

    if not args:
        # Default to root or device path
        if _current_device:
            new_path = _current_device._device_path
        else:
            new_path = "/org/bluez"
    else:
        # Resolve the provided path
        target_path = args[0]

        # Special case for absolute paths
        if target_path.startswith('/'):
            new_path = target_path
        else:
            # Handle special cases for relative navigation
            if target_path == '..':
                # Go up one level
                if _current_path == '/':
                    new_path = '/'
                else:
                    new_path = '/'.join(_current_path.split('/')[:-1]) or '/'
            elif target_path == '.':
                # Stay in current directory
                new_path = _current_path
            else:
                # Check if target is a valid child directory
                dirs, _ = _get_child_nodes_at_path(_current_path)
                if target_path not in dirs:
                    print(f"[-] No such directory: {target_path}")
                    return

                # Append to current path
                if _current_path.endswith('/'):
                    new_path = _current_path + target_path
                else:
                    new_path = _current_path + '/' + target_path

    # Check if path exists as a valid D-Bus object
    try:
        obj = _get_object_at_path(new_path)
        if not obj:
            print(f"[-] Path does not exist: {new_path}")
            return

        # Verify it's a valid directory by checking if we can introspect it
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        # Store current path in history before changing
        if _current_path and _current_path != new_path:
            _path_history.append(_current_path)

        # Update current path
        _current_path = new_path
    except Exception as e:
        print(f"[-] Cannot navigate to {new_path}: {e}")
        return


def _cmd_pwd(args: List[str]) -> None:
    """Print current D-Bus path."""
    global _current_path

    if not _current_path:
        if _current_device:
            _current_path = _current_device._device_path
        else:
            _current_path = "/org/bluez"

    print(f"Current path: {_current_path}")


def _cmd_back(args: List[str]) -> None:
    """Navigate back to the previous path."""
    global _current_path, _path_history

    if not _path_history:
        print("[-] No previous path in history")
        return

    # Pop the last path from history
    _current_path = _path_history.pop()


def _cmd_help(_: List[str]) -> None:
    """Display available commands."""
    print("\nAvailable commands:")
    print("  help                       - Show this help")
    print("  scan                       - Scan for BLE devices")
    print("  connect <mac>              - Connect to a device")
    print("  disconnect                 - Disconnect from current device")
    print("  info                       - Show device information")
    print("  interfaces                 - List available D-Bus interfaces")
    print("  props [interface]          - List properties for an interface")
    print("  methods <interface>        - List methods for an interface")
    print("  signals <interface>        - List signals for an interface")
    print("  call <interface> <method> [args...] - Call a method")
    print("  monitor [start|stop]       - Monitor device properties")
    print("  introspect [path]          - Introspect a D-Bus object")
    print("  services                   - List GATT services")
    print("  chars [service_uuid]       - List characteristics")
    print("  char <char_uuid>           - Show detailed characteristic info")
    print("  read <char_uuid|handle>    - Read characteristic value")
    print("  write <char_uuid|handle> <value> - Write to characteristic")
    print("  notify <char_uuid|handle> [on|off] - Subscribe/unsubscribe to notifications")
    print("  detailed [on|off]          - Toggle detailed view mode with UUID decoding")
    print("\nNavigation commands:")
    print("  ls [path]                  - List objects at current or specified path")
    print("  cd <path>                  - Change to specified D-Bus path")
    print("  pwd                        - Show current D-Bus path")
    print("  back                       - Go back to previous path")
    print("\nOther commands:")
    print("  quit                       - Exit debug mode")
    print()


def _cmd_scan(_: List[str]) -> None:
    """Scan for nearby BLE devices."""
    print_and_log("[*] Scanning for devices...", LOG__GENERAL)
    passive_scan(timeout=10)


def _cmd_connect(args: List[str]) -> None:
    """Connect to a device by MAC address."""
    global _current_device, _current_mapping, _current_path

    if not args:
        print("Usage: connect <MAC>")
        return

    mac = args[0]
    try:
        print_and_log(f"[*] Connecting to {mac}…", LOG__GENERAL)

        # First perform the connection / enumeration and *only* commit the
        # globals if it succeeds.  This prevents half-initialised state when
        # an exception bubbles up after the low-level connect step.
        dev, mapping, _, _ = _connect_enum(mac)

    except Exception as exc:
        # Underlying helpers already logged detailed errors; emit concise msg
        print_and_log(f"[-] Connection failed: {exc}", LOG__DEBUG)
        return

    # ------------------------------------------------------------------
    # Success – update global session state
    # ------------------------------------------------------------------

    global _current_device, _current_mapping, _current_path

    # Disconnect any previous device to avoid contention
    if _current_device and _current_device.is_connected():
        try:
            _current_device.disconnect()
        except Exception:
            pass

    _current_device = dev
    _current_mapping = mapping
    _current_path = _current_device._device_path

    print_and_log(f"[+] Connected to {mac}", LOG__GENERAL)


def _cmd_disconnect(_: List[str]) -> None:
    """Disconnect from the current device."""
    global _current_device, _current_mapping

    if not _current_device:
        print("[-] No device connected")
        return

    try:
        mac = _current_device.mac_address
        _current_device.disconnect()
        print_and_log(f"[+] Disconnected from {mac}", LOG__GENERAL)
        _current_device = None
        _current_mapping = None
    except Exception as exc:
        print_and_log(f"[-] Disconnect failed: {exc}", LOG__DEBUG)


def _cmd_info(args: List[str]) -> None:
    """Show device information."""
    global _current_device, _detailed_view

    if not _current_device:
        print("[-] No device connected")
        return

    # Get device info
    device_path = _current_device._device_path
    device_addr = _current_device.mac_address
    device_name = _current_device.name if hasattr(_current_device, 'name') else "Unknown"
    device_addr_type = _current_device.address_type if hasattr(_current_device, 'address_type') else "Unknown"
    
    # Print device information
    print(f"[+] Device: {device_name}")
    print(f"  Address: {device_addr} ({device_addr_type})")
    print(f"  Path: {device_path}")

    # Try to get extra properties
    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", device_path)
        props_iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")

        # Get common device properties
        try:
            props = props_iface.GetAll("org.bluez.Device1")
            print("[*] Device Properties:")
            _show_properties(props, _detailed_view)
        except dbus.exceptions.DBusException:
            pass
    except Exception as e:
        print(f"[-] Error getting additional info: {e}")


def _cmd_interfaces(args: List[str]) -> None:
    """List available interfaces on the current object."""
    global _current_path

    # Use current path if available, otherwise use device path
    path = _current_path
    if not path and _current_device:
        path = _current_device._device_path

    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        # Get the D-Bus object for the path
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)

        # Get introspection data
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        # Parse XML to extract interfaces
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        print("\nAvailable interfaces:")
        for iface in root.findall("interface"):
            iface_name = iface.get("name")
            print(f"  {iface_name}")
        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving interfaces: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_props(args: List[str]) -> None:
    """Show properties of an interface."""
    global _current_path, _detailed_view
    
    if not args:
        print("Usage: props <interface>")
        return

    interface = args[0]

    # Use current path if available, otherwise use device path
    path = _current_path
    if not path and _current_device:
        path = _current_device._device_path

    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        # Get the D-Bus object for the path
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)

        # Try to get properties for the specified interface
        props_iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        props = props_iface.GetAll(interface)

        print(f"[*] Properties for {interface}:")
        _show_properties(props, _detailed_view)

    except dbus.exceptions.DBusException as e:
        error = map_dbus_error(e)
        print(f"[-] Error getting properties: {error}")
    except Exception as e:
        print(f"[-] Error: {e}")


def _cmd_methods(args: List[str]) -> None:
    """Show methods of an interface."""
    global _current_path

    if not args:
        print("Usage: methods <interface>")
        return

    interface_name = args[0]

    # Use current path if available, otherwise use device path
    path = _current_path
    if not path and _current_device:
        path = _current_device._device_path

    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        # Get the D-Bus object for the path
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)

        # Get introspection data
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        # Simple XML parsing to extract methods
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        # Find the requested interface
        print(f"\nMethods of {interface_name}:")
        methods_found = False

        for iface in root.findall("interface"):
            if iface.get("name") == interface_name:
                methods = iface.findall("method")
                if not methods:
                    print("  No methods found for this interface")
                    methods_found = False
                    break

                for method in methods:
                    methods_found = True
                    method_name = method.get("name")

                    # Get input arguments with types
                    args_in = []
                    for arg in method.findall("arg"):
                        if arg.get("direction") != "out":  # Default is "in" if not specified
                            arg_name = arg.get("name") or "arg"
                            arg_type = arg.get("type") or "unknown"
                            args_in.append(f"{arg_name}: {arg_type}")

                    # Get output arguments with types
                    args_out = []
                    for arg in method.findall("arg"):
                        if arg.get("direction") == "out":
                            arg_name = arg.get("name") or "result"
                            arg_type = arg.get("type") or "unknown"
                            args_out.append(f"{arg_name}: {arg_type}")

                    args_in_str = ", ".join(args_in) if args_in else ""
                    args_out_str = ", ".join(args_out) if args_out else "void"

                    print(f"  {method_name}({args_in_str}) -> {args_out_str}")

        if not methods_found:
            print(f"  Interface '{interface_name}' not found on object")

        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving methods: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_signals(args: List[str]) -> None:
    """List signals of an interface."""
    global _current_path

    if not args:
        print("Usage: signals <interface>")
        return

    interface_name = args[0]

    # Use current path if available, otherwise use device path
    path = _current_path
    if not path and _current_device:
        path = _current_device._device_path

    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        # Get the D-Bus object for the path
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)

        # Get introspection data
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect() 

        # Parse XML to extract signals
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        print(f"\nSignals of {interface_name}:")
        signals_found = False

        for iface in root.findall("interface"):
            if iface.get("name") == interface_name:
                signals = iface.findall("signal")
                if not signals:
                    print("  No signals found for this interface")
                    signals_found = False
                    break

                for signal in signals:
                    signals_found = True
                    signal_name = signal.get("name")

                    # Get input arguments with types; Note: There is no direction for signals, only a type to represent the signal type
                    args_in = []
                    for arg in signal.findall("arg"):
                        arg_name = arg.get("name") or "arg"
                        arg_type = arg.get("type") or "unknown"
                        args_in.append(f"{arg_name}: {arg_type}")

                    args_in_str = ", ".join(args_in) if args_in else ""
                    print(f"  {signal_name}({args_in_str})")

        if not signals_found:
            print(f"  Interface '{interface_name}' not found on object")

        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving signals: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_call(args: List[str]) -> None:
    """Call a method on an interface."""
    global _current_path

    if len(args) < 2:
        print("Usage: call <interface> <method> [args...]")
        return

    interface = args[0]
    method = args[1]
    method_args = args[2:] if len(args) > 2 else []

    # Use current path if available, otherwise use device path
    path = _current_path
    if not path and _current_device:
        path = _current_device._device_path

    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        # Get the D-Bus object for the path
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        iface = dbus.Interface(obj, interface)
        method_obj = getattr(iface, method)

        if method_args:
            result = method_obj(*method_args)
        else:
            result = method_obj()

        print(f"[+] Method call successful")
        print(f"Result: {result}")
    except Exception as exc:
        print_and_log(f"[-] Method call failed: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _monitor_properties(device_path: str, stop_event: threading.Event) -> None:
    """Monitor properties of a device in real-time."""
    try:
        bus = dbus.SystemBus()
        device_obj = bus.get_object("org.bluez", device_path)

        # Set up signal receiver for PropertiesChanged
        from dbus.mainloop.glib import DBusGMainLoop
        DBusGMainLoop(set_as_default=True)
        
        #from gi.repository import GObject as gobject
        from gi.repository import GLib as glib

        mainloop = glib.MainLoop()

        def properties_changed_cb(interface, changed, invalidated, path=None):
            if stop_event.is_set():
                mainloop.quit()
                return

            print("\n[MONITOR] Properties changed:")
            print(f"  Interface: {interface}")
            print(f"  Path: {path}")

            for prop, value in changed.items():
                print(f"  {prop}: {value}")

            if invalidated:
                print("  Invalidated properties:")
                for prop in invalidated:
                    print(f"    {prop}")
            
            print(_DEVICE_PROMPT.format(_current_device.mac_address), end="", flush=True)
        
        bus.add_signal_receiver(
            properties_changed_cb,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path=device_path,
            path_keyword="path"
        )

        # Run the mainloop until stopped
        def check_stop():
            if stop_event.is_set():
                mainloop.quit()
                return False
            return True

        glib.timeout_add(500, check_stop)
        print_and_log("[+] Property monitoring started", LOG__GENERAL)
        mainloop.run()

    except Exception as exc:
        print_and_log(f"[-] Monitoring error: {exc}", LOG__DEBUG)
    finally:
        print_and_log("[*] Property monitoring stopped", LOG__GENERAL)


def _cmd_monitor(args: List[str]) -> None:
    """Start or stop real-time property monitoring."""
    global _monitoring, _monitor_thread, _monitor_stop_event

    if not _current_device:
        print("[-] No device connected")
        return

    action = "start"
    if args:
        action = args[0].lower()

    if action == "start":
        if _monitoring:
            print("[-] Monitoring already active")
            return

        _monitor_stop_event = threading.Event()
        _monitor_thread = threading.Thread(
            target=_monitor_properties,
            args=(_current_device._device_path, _monitor_stop_event)
        )
        _monitor_thread.daemon = True
        _monitor_thread.start()
        _monitoring = True

    elif action == "stop":
        if not _monitoring:
            print("[-] Monitoring not active")
            return

        _monitor_stop_event.set()
        if _monitor_thread:
            _monitor_thread.join(timeout=1.0)
        _monitoring = False
        print_and_log("[*] Property monitoring stopped", LOG__GENERAL)

    else:
        print("Usage: monitor [start|stop]")


def _cmd_introspect(args: List[str]) -> None:
    """Introspect a D-Bus object."""
    global _current_path

    # Use provided path, current path, or device path in that order
    if args:
        path = _resolve_path(args[0])
    elif _current_path:
        path = _current_path
    elif _current_device:
        path = _current_device._device_path
    else:
        print("[-] No device connected and no current path")
        return

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()
        dom = minidom.parseString(xml)
        pretty_xml = dom.toprettyxml(indent="  ")

        # Remove empty lines with whitespace
        pretty_xml = re.sub(r'\n\s*\n', '\n', pretty_xml)

        print(f"\nIntrospection of {path}:\n")
        print(pretty_xml)
        print()
    except Exception as exc:
        print_and_log(f"[-] Introspection failed: {exc}", LOG__DEBUG)


def debugging_notification_callback(value, path=None, interface=None, signal_name=None, timestamp=None):
    """Comprehensive callback for debugging notification signals.

    This callback provides detailed analysis of notification data in multiple formats
    (hex, ASCII, UTF-8, integer representations, etc.) to assist in understanding
    the behavior of target devices. It tracks signal history for correlation and
    provides contextual information about the signal source.

    Parameters:
    ----------
    value : bytes, dbus.Array, or any
        The value received in the notification
    path : str, optional
        The D-Bus path of the object that sent the signal
    interface : str, optional
        The D-Bus interface that sent the signal
    signal_name : str, optional
        The name of the signal (e.g., "PropertiesChanged")
    timestamp : float, optional
        The time when the signal was received (defaults to current time)
    """
    # Initialize timestamp if not provided
    if timestamp is None:
        import time
        timestamp = time.time()

    # Determine signal type based on interface and signal name
    signal_type = "NOTIFICATION"
    if interface and signal_name:
        if interface == "org.freedesktop.DBus.Properties" and signal_name == "PropertiesChanged":
            signal_type = "PROPERTY_CHANGE"
        elif signal_name == "InterfacesAdded":
            signal_type = "INTERFACE_ADDED"
        elif signal_name == "InterfacesRemoved":
            signal_type = "INTERFACE_REMOVED"

    # Convert dbus.Array or other D-Bus types to Python types
    if hasattr(value, '__class__') and 'dbus' in str(value.__class__):
        try:
            from bleep.bt_ref.utils import dbus_to_python
            value = dbus_to_python(value)
        except (ImportError, Exception):
            # Fall back to manual conversion if dbus_to_python is not available
            if isinstance(value, dbus.Array):
                value = bytes(value)
            elif isinstance(value, dbus.Dictionary):
                value = dict(value)
            elif isinstance(value, (dbus.Int16, dbus.Int32, dbus.Int64, dbus.UInt16, dbus.UInt32, dbus.UInt64)):
                value = int(value)
            elif isinstance(value, dbus.String):
                value = str(value)
            elif isinstance(value, dbus.Boolean):
                value = bool(value)

    # Extract value from property change if applicable
    original_value = value
    if isinstance(value, dict) and "Value" in value:
        value = value["Value"]

    # Format header with timestamp and context
    import datetime
    timestamp_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    print(f"\n[{timestamp_str}] {signal_type} RECEIVED:")
    if path:
        print(f"  Path: {path}")
    if interface:
        print(f"  Interface: {interface}")
    if signal_name:
        print(f"  Signal: {signal_name}")

    # Try to get UUID and handle information from the path
    uuid = None
    handle = None
    if path:
        import re
        # Extract UUID from path if possible
        uuid_match = re.search(r'char([0-9a-fA-F]{4})$', path)
        if uuid_match:
            char_id = uuid_match.group(1)
            handle = int(char_id, 16)

            # Try to look up the full UUID from the mapping
            if _current_mapping:
                # Invert the mapping to get handle → UUID
                handle_to_uuid = {v: k for k, v in _current_mapping.items()}
                if handle in handle_to_uuid:
                    uuid = handle_to_uuid[handle]

        # If we found a UUID, try to get its name
        if uuid:
            try:
                from bleep.bt_ref.utils import get_name_from_uuid
                uuid_name = get_name_from_uuid(uuid)
                print(f"  UUID: {uuid} ({uuid_name})")
            except (ImportError, Exception):
                print(f"  UUID: {uuid}")
            print(f"  Handle: 0x{handle:04x} ({handle})")

    # Process the value based on its type
    if value is None:
        print("  Value: None")
    elif isinstance(value, (bytes, bytearray, list)):
        # Convert list to bytes if needed
        if isinstance(value, list):
            try:
                value = bytes(value)
            except Exception:
                pass

        # Format as different representations
        try:
            hex_str = " ".join([f"{b:02x}" for b in value])
            print(f"  Value (HEX): {hex_str}")
        except Exception as e:
            print(f"  Value (HEX): Error converting to hex - {e}")

        try:
            ascii_str = "".join([chr(b) if 32 <= b <= 126 else '.' for b in value])
            print(f"  Value (ASCII): \"{ascii_str}\"")
        except Exception as e:
            print(f"  Value (ASCII): Error converting to ASCII - {e}")

        try:
            utf8_str = value.decode('utf-8', errors='replace')
            print(f"  Value (UTF-8): \"{utf8_str}\"")
        except Exception as e:
            print(f"  Value (UTF-8): Error converting to UTF-8 - {e}")

        # Try to interpret as various integer types if length matches
        import struct
        if len(value) in (1, 2, 4, 8):
            try:
                if len(value) == 1:
                    print(f"  Value (uint8): {value[0]}")
                    print(f"  Value (int8): {struct.unpack('b', value)[0]}")
                elif len(value) == 2:
                    print(f"  Value (uint16, little-endian): {struct.unpack('<H', value)[0]}")
                    print(f"  Value (int16, little-endian): {struct.unpack('<h', value)[0]}")
                    print(f"  Value (uint16, big-endian): {struct.unpack('>H', value)[0]}")
                    print(f"  Value (int16, big-endian): {struct.unpack('>h', value)[0]}")
                elif len(value) == 4:
                    print(f"  Value (uint32, little-endian): {struct.unpack('<I', value)[0]}")
                    print(f"  Value (int32, little-endian): {struct.unpack('<i', value)[0]}")
                    print(f"  Value (uint32, big-endian): {struct.unpack('>I', value)[0]}")
                    print(f"  Value (int32, big-endian): {struct.unpack('>i', value)[0]}")
                    try:
                        print(f"  Value (float, little-endian): {struct.unpack('<f', value)[0]}")
                        print(f"  Value (float, big-endian): {struct.unpack('>f', value)[0]}")
                    except Exception:
                        pass
                elif len(value) == 8:
                    print(f"  Value (uint64, little-endian): {struct.unpack('<Q', value)[0]}")
                    print(f"  Value (int64, little-endian): {struct.unpack('<q', value)[0]}")
                    print(f"  Value (uint64, big-endian): {struct.unpack('>Q', value)[0]}")
                    print(f"  Value (int64, big-endian): {struct.unpack('>q', value)[0]}")
                    try:
                        print(f"  Value (double, little-endian): {struct.unpack('<d', value)[0]}")
                        print(f"  Value (double, big-endian): {struct.unpack('>d', value)[0]}")
                    except Exception:
                        pass
            except Exception as e:
                print(f"  Value (numeric conversions): Error - {e}")
    elif isinstance(value, dict):
        # For dictionary values, print each key-value pair
        print("  Value (Dictionary):")
        for k, v in value.items():
            print(f"    {k}: {v}")
    else:
        # For other types, just print the value
        print(f"  Value ({type(value).__name__}): {value}")

    # If we have the original dictionary with more than just Value, show the other keys
    if isinstance(original_value, dict) and len(original_value) > 1:
        print("  Additional Properties:")
        for k, v in original_value.items():
            if k != "Value":  # Skip Value as we've already processed it
                print(f"    {k}: {v}")

    # Record this notification in the signal history
    # This is a static variable to track recent notifications
    if not hasattr(debugging_notification_callback, "_signal_history"):
        debugging_notification_callback._signal_history = []

    # Add to history
    signal_record = {
        "timestamp": timestamp,
        "type": signal_type,
        "path": path,
        "interface": interface,
        "signal_name": signal_name,
        "value": value
    }
    debugging_notification_callback._signal_history.append(signal_record)

    # Keep only the last 20 signals
    if len(debugging_notification_callback._signal_history) > 20:
        debugging_notification_callback._signal_history.pop(0)

    # Look for related signals in the last 1 second
    related_signals = []
    for record in debugging_notification_callback._signal_history[:-1]:  # Skip the current signal
        if abs(record["timestamp"] - timestamp) <= 1.0:  # Within 1 second
            if path and record["path"] and (path.startswith(record["path"]) or record["path"].startswith(path)):
                related_signals.append(record)

    # Print related signals if any
    if related_signals:
        print("\n  Related Signals:")
        for idx, record in enumerate(related_signals):
            rel_time = record["timestamp"] - timestamp
            print(f"    [{idx+1}] {record['type']} at {rel_time:.3f}s ({record['path']})")
    
    # Log to debug log as well
    from bleep.core.log import print_and_log, LOG__DEBUG
    log_message = f"[NOTIFICATION] {signal_type} received at {timestamp_str}"
    if path:
        log_message += f"\n  Path: {path}"
    if interface:
        log_message += f"\n  Interface: {interface}"
    if signal_name:
        log_message += f"\n  Signal: {signal_name}"
    if isinstance(value, (bytes, bytearray)):
        log_message += f"\n  Value (HEX): {' '.join([f'{b:02x}' for b in value])}"
    else:
        log_message += f"\n  Value: {value}"

    print_and_log(log_message, LOG__DEBUG)

    # Print the prompt again to maintain interactive shell experience
    if '_current_device' in globals() and _current_device:
        print(_DEVICE_PROMPT.format(_current_device.mac_address), end="", flush=True)

def _get_handle_from_dict(obj_dict):
    """Extract handle from a service, characteristic, or descriptor dictionary.

    Tries multiple methods to get the handle:
    1. Direct 'handle' property if available
    2. Extracting from the object path using regex
    3. Computing based on service/characteristic offset

    Parameters
    ----------
    obj_dict : dict
        Dictionary representing a service, characteristic, or descriptor

    Returns
    -------
    int
        The handle value, or -1 if no handle could be extracted
    """
    # Try to get handle directly if available
    if "handle" in obj_dict:
        return obj_dict["handle"]

    # Try to extract from path
    path = obj_dict.get("path", "")
    if path:
        # Extract handle from path based on type
        if "char" in path:
            match = re.search(r'char([0-9a-fA-F]{4})$', path)
            if match:
                return int(match.group(1), 16)
        elif "service" in path:
            match = re.search(r'service([0-9a-fA-F]{4})$', path)
            if match:
                return int(match.group(1), 16)
        elif "desc" in path:
            match = re.search(r'desc([0-9a-fA-F]{4})$', path)
            if match:
                return int(match.group(1), 16)

    # If we get here, we couldn't find a handle
    return -1


def _cmd_services(_: List[str]) -> None:
    """List GATT services of the current device."""
    if not _current_device:
        print("[-] No device connected")
        return

    try:
        # Force a refresh of services to ensure we have the latest data
        services = _current_device.services_resolved(skip_device_type_check=True)
        
        if not services:
            print("\nNo GATT services found on device")
            print("This may be because:")
            print("  1. The device doesn't expose any GATT services")
            print("  2. Services haven't been resolved yet")
            print("  3. There was an error during service discovery")
            print("\nTry using 'call org.bluez.Device1 Connect' to reconnect and resolve services")
            print()
            return

        print("\nGATT Services:")
        for service in services:
            uuid = service.get("uuid", "Unknown")
            path = service.get("path", "Unknown")
            handle = _get_handle_from_dict(service)

            if _detailed_view:
                # Get decoded UUID name
                uuid_name = get_name_from_uuid(uuid)

                # Format the output as requested: <128-bit UUID> - <Decoded UUID String> - <Handle>
                print(f"  {uuid} - {uuid_name} - [0x{handle:04x} - {handle} - Service]")
                print(f"    Path: {path}")
            else:
                # Simple view
                print(f"  [0x{handle:04x}] {uuid}")
            print(f"    Path: {path}")

            # List characteristics for this service
            chars = service.get("characteristics", [])

            print(f"    ({len(chars)} characteristics)")
            if chars:
                print("    Characteristics:")
                for char in chars:
                    char_uuid = char.get("uuid", "Unknown")
                    char_flags = ", ".join(char.get("flags", []))
                    char_handle = _get_handle_from_dict(char)

                    if _detailed_view:
                        # Get decoded UUID name
                        char_uuid_name = get_name_from_uuid(char_uuid)

                        # Format the output as requested
                        print(f"      {char_uuid} - {char_uuid_name} - [0x{char_handle:04x} - {char_handle} - Characteristic]")
                    else:
                        # Simple view
                        print(f"      [0x{char_handle:04x}] {char_uuid}")

                    print(f"        Flags: {char_flags}")

                    # List descriptors if any
                    descriptors = char.get("descriptors", [])
                    if descriptors:
                        print("        Descriptors:")
                        for desc in descriptors:
                            desc_uuid = desc.get("uuid", "Unknown")
                            desc_handle = _get_handle_from_dict(desc)

                            if _detailed_view:
                                # Get decoded UUID name
                                desc_uuid_name = get_name_from_uuid(desc_uuid)

                                # Format the output as requested
                                print(f"          {desc_uuid} - {desc_uuid_name} - [0x{desc_handle:04x} - {desc_handle} - Descriptor]")
                            else:
                                # Simple view
                                print(f"          [0x{desc_handle:04x}] {desc_uuid}")
        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving services: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)

def _cmd_chars(args: List[str]) -> None:
    """List characteristics for a service."""
    if not _current_device:
        print("[-] No device connected")
        return

    if not args:
        print("Usage: chars <service_uuid>")
        return

    service_uuid = args[0]

    try:
        if not _current_device.services_resolved():
            print("[-] Services not yet resolved. Try connecting first.")
            return

        # Find the service by UUID - no need to manually expand UUIDs here
        # as the _find_service method now uses identify_uuid internally
        service = _current_device._find_service(service_uuid)
        if not service:
            print(f"[-] Service with UUID {service_uuid} not found")
            return

        # Get characteristics for the service
        characteristics = service.get_characteristics()

        if not characteristics:
            print("[-] No characteristics found for this service")
            return

        print(f"\nCharacteristics for service {service_uuid}")
        if _detailed_view:
            uuid_name = get_name_from_uuid(service_uuid)
            if uuid_name != "Unknown":
                print(f"  ↳ {uuid_name}")

        for char in characteristics:
            uuid = char.get_uuid()
            handle = char.get_handle()
            props = char.get_flags()

            print(f"\n  Characteristic: {uuid}")
            if _detailed_view:
                uuid_name = get_name_from_uuid(uuid)
                if uuid_name != "Unknown":
                    print(f"    ↳ {uuid_name}")

            print(f"    Handle: {handle}")
            print(f"    Properties: {', '.join(props)}")

            # Get descriptors for this characteristic
            descriptors = char.get_descriptors()
            if descriptors:
                print("    Descriptors:")
                for desc in descriptors:
                    desc_uuid = desc.get_uuid()
                    desc_handle = desc.get_handle()

                    print(f"      Descriptor: {desc_uuid}")
                    if _detailed_view:
                        uuid_name = get_name_from_uuid(desc_uuid)
                        if uuid_name != "Unknown":
                            print(f"        ↳ {uuid_name}")
                    print(f"        Handle: {desc_handle}")

        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving characteristics: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_char(args: List[str]) -> None:
    """Show detailed information about a specific characteristic."""
    if not _current_device:
        print("[-] No device connected")
        return

    if not args:
        print("Usage: char <characteristic_uuid>")
        return

    char_uuid = args[0]

    try:
        if not _current_device.services_resolved():
            print("[-] Services not yet resolved. Try connecting first.")
            return

        # Find the characteristic by UUID - no need to manually expand UUIDs here
        # as the _find_characteristic method now uses identify_uuid internally
        char = _current_device._find_characteristic(char_uuid)
        if not char:
            print(f"[-] Characteristic with UUID {char_uuid} not found")
            return

        print(f"\nCharacteristic Details for {char_uuid}")
        if _detailed_view:
            uuid_name = get_name_from_uuid(char_uuid)
            if uuid_name != "Unknown":
                print(f"  ↳ {uuid_name}")

        print(f"  Handle: {char.get_handle()}")
        print(f"  Properties: {', '.join(char.get_flags())}")
        print(f"  Path: {char.path}")
        print(f"  Parent Service UUID: {char.parent_service_uuid}")

        # Get descriptors for this characteristic
        descriptors = char.get_descriptors()
        if descriptors:
            print("\n  Descriptors:")
            for desc in descriptors:
                desc_uuid = desc.get_uuid()
                desc_handle = desc.get_handle()

                print(f"    Descriptor: {desc_uuid}")
                if _detailed_view:
                    uuid_name = get_name_from_uuid(desc_uuid)
                    if uuid_name != "Unknown":
                        print(f"      ↳ {uuid_name}")
                print(f"      Handle: {desc_handle}")

                # Try to read the descriptor value if possible
                try:
                    value = desc.read_value()
                    hex_str = " ".join([f"{b:02x}" for b in value])
                    print(f"      Value (HEX): {hex_str}")

                    # Try to interpret as ASCII if printable
                    try:
                        ascii_str = value.decode('ascii')
                        if all(32 <= ord(c) <= 126 for c in ascii_str):  # Printable ASCII
                            print(f"      Value (ASCII): \"{ascii_str}\"")
                    except UnicodeDecodeError:
                        pass
                except Exception as e:
                    print(f"      Value: <Error reading: {str(e)}>")
        else:
            print("\n  No descriptors found for this characteristic")

        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving characteristic details: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_read(args: List[str]) -> None:
    """Read a characteristic value."""
    if not _current_device:
        print("[-] No device connected")
        return

    if not args:
        print("Usage: read <char_uuid|handle>")
        return

    char_id = args[0]

    try:
        # Check if we have a UUID or a handle
        if char_id.isdigit() or (char_id.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in char_id[2:])):
            # Handle as numeric
            handle = int(char_id, 0) if char_id.startswith("0x") else int(char_id)
            
            # Look up UUID from handle in mapping
            if not _current_mapping:
                print("[-] No characteristic mapping available")
                return

            # Invert the mapping to get handle → UUID
            handle_to_uuid = {v: k for k, v in _current_mapping.items()}
            if handle not in handle_to_uuid:
                print(f"[-] No characteristic found with handle {handle}")
                return

            uuid = handle_to_uuid[handle]
        else:
            # Treat as UUID
            uuid = char_id

        # Read the characteristic
        value = _current_device.read_characteristic(uuid)

        # Try to display in different formats
        try:
            ascii_str = value.decode('ascii')
            if all(32 <= ord(c) <= 126 for c in ascii_str):  # Printable ASCII
                print(f"\nValue (ASCII): \"{ascii_str}\"")
            else:
                raise ValueError("Not printable ASCII")
        except (UnicodeDecodeError, ValueError):
            pass

        try:
            utf8_str = value.decode('utf-8')
            print(f"Value (UTF-8): \"{utf8_str}\"")
        except UnicodeDecodeError:
            pass

        # Display as hex
        hex_str = " ".join([f"{b:02x}" for b in value])
        print(f"Value (HEX): {hex_str}")

        # Try to interpret as various integer types if length matches
        if len(value) in (1, 2, 4, 8):
            if len(value) == 1:
                print(f"Value (uint8): {value[0]}")
                print(f"Value (int8): {struct.unpack('b', value)[0]}")
            elif len(value) == 2:
                print(f"Value (uint16, little-endian): {struct.unpack('<H', value)[0]}")
                print(f"Value (int16, little-endian): {struct.unpack('<h', value)[0]}")
                print(f"Value (uint16, big-endian): {struct.unpack('>H', value)[0]}")
                print(f"Value (int16, big-endian): {struct.unpack('>h', value)[0]}")
            elif len(value) == 4:
                print(f"Value (uint32, little-endian): {struct.unpack('<I', value)[0]}")
                print(f"Value (int32, little-endian): {struct.unpack('<i', value)[0]}")
                print(f"Value (uint32, big-endian): {struct.unpack('>I', value)[0]}")
                print(f"Value (int32, big-endian): {struct.unpack('>i', value)[0]}")
                try:
                    print(f"Value (float, little-endian): {struct.unpack('<f', value)[0]}")
                    print(f"Value (float, big-endian): {struct.unpack('>f', value)[0]}")
                except:
                    pass
            elif len(value) == 8:
                print(f"Value (uint64, little-endian): {struct.unpack('<Q', value)[0]}")
                print(f"Value (int64, little-endian): {struct.unpack('<q', value)[0]}")
                print(f"Value (uint64, big-endian): {struct.unpack('>Q', value)[0]}")
                print(f"Value (int64, big-endian): {struct.unpack('>q', value)[0]}")
                try:
                    print(f"Value (double, little-endian): {struct.unpack('<d', value)[0]}")
                    print(f"Value (double, big-endian): {struct.unpack('>d', value)[0]}")
                except:
                    pass

        print()
    except Exception as exc:
        print_and_log(f"[-] Read failed: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_write(args: List[str]) -> None:
    """Write to a characteristic."""
    if not _current_device:
        print("[-] No device connected")
        return

    if len(args) < 2:
        print("Usage: write <char_uuid|handle> <value>")
        print("  Value formats:")
        print("    hex:[01ab23cd]    - Interpret as hex bytes")
        print("    str:hello         - Interpret as ASCII/UTF-8 string")
        print("    uint8:123         - 8-bit unsigned integer")
        print("    int8:-123         - 8-bit signed integer")
        print("    uint16:12345      - 16-bit unsigned integer (little-endian)")
        print("    int16:-12345      - 16-bit signed integer (little-endian)")
        print("    uint16be:12345    - 16-bit unsigned integer (big-endian)")
        print("    int16be:-12345    - 16-bit signed integer (big-endian)")
        print("    uint32:123456     - 32-bit unsigned integer (little-endian)")
        print("    int32:-123456     - 32-bit signed integer (little-endian)")
        print("    uint32be:123456   - 32-bit unsigned integer (big-endian)")
        print("    int32be:-123456   - 32-bit signed integer (big-endian)")
        print("    float:123.456     - 32-bit float (little-endian)")
        print("    floatbe:123.456   - 32-bit float (big-endian)")
        print("    double:123.456    - 64-bit double (little-endian)")
        print("    doublebe:123.456  - 64-bit double (big-endian)")
        return

    char_id = args[0]
    value_str = args[1]

    try:
        # Parse char_id the same way as in _cmd_read
        if char_id.isdigit() or (char_id.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in char_id[2:])):
            # Handle as numeric
            handle = int(char_id, 0) if char_id.startswith("0x") else int(char_id)
            
            if not _current_mapping:
                print("[-] No characteristic mapping available")
                return

            # Invert the mapping to get handle → UUID
            handle_to_uuid = {v: k for k, v in _current_mapping.items()}
            if handle not in handle_to_uuid:
                print(f"[-] No characteristic found with handle {handle}")
                return

            uuid = handle_to_uuid[handle]
        else:
            # Treat as UUID
            uuid = char_id

        # Parse the value based on the format
        if ':' in value_str:
            fmt, val = value_str.split(':', 1)
            fmt = fmt.lower()

            if fmt == 'hex':
                # Remove any non-hex characters
                clean_val = ''.join(c for c in val if c in '0123456789abcdefABCDEF')
                if len(clean_val) % 2 != 0:
                    clean_val = '0' + clean_val  # Pad with leading zero if odd length
                value = bytes.fromhex(clean_val)
            elif fmt == 'str':
                value = val.encode()
            elif fmt == 'uint8':
                value = struct.pack('B', int(val))
            elif fmt == 'int8':
                value = struct.pack('b', int(val))
            elif fmt == 'uint16':
                value = struct.pack('<H', int(val))
            elif fmt == 'int16':
                value = struct.pack('<h', int(val))
            elif fmt == 'uint16be':
                value = struct.pack('>H', int(val))
            elif fmt == 'int16be':
                value = struct.pack('>h', int(val))
            elif fmt == 'uint32':
                value = struct.pack('<I', int(val))
            elif fmt == 'int32':
                value = struct.pack('<i', int(val))
            elif fmt == 'uint32be':
                value = struct.pack('>I', int(val))
            elif fmt == 'int32be':
                value = struct.pack('>i', int(val))
            elif fmt == 'float':
                value = struct.pack('<f', float(val))
            elif fmt == 'floatbe':
                value = struct.pack('>f', float(val))
            elif fmt == 'double':
                value = struct.pack('<d', float(val))
            elif fmt == 'doublebe':
                value = struct.pack('>d', float(val))
            else:
                print(f"[-] Unknown format: {fmt}")
                return
        else:
            # Default to string
            value = value_str.encode()

        # Write the value
        _current_device.write_characteristic(uuid, value)
        print(f"\n[+] Successfully wrote to characteristic {uuid}\n")

    except Exception as exc:
        print_and_log(f"[-] Write failed: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_notify(args: List[str]) -> None:
    """Subscribe or unsubscribe to notifications from a characteristic."""
    if not _current_device or not _current_mapping:
        print("[-] No device connected or no services discovered")
        return

    if not args:
        print("Usage: notify <char_uuid|handle> [on|off]")
        return

    char_id = args[0]
    action = "on"  # Default to enabling notifications
    if len(args) > 1:
        action = args[1].lower()
        if action not in ["on", "off"]:
            print("Action must be 'on' or 'off'")
            return

    try:
        # Check if we have a UUID or a handle
        if char_id.isdigit() or (char_id.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in char_id[2:])):
            # Handle as numeric
            handle = int(char_id, 0) if char_id.startswith("0x") else int(char_id)
            
            # Look up UUID from handle in mapping
            if not _current_mapping:
                print("[-] No characteristic mapping available")
                return

            # Invert the mapping to get handle → UUID
            handle_to_uuid = {v: k for k, v in _current_mapping.items()}
            if handle not in handle_to_uuid:
                print(f"[-] No characteristic found with handle {handle}")
                return

            uuid = handle_to_uuid[handle]
        else:
            # Treat as UUID
            uuid = char_id

        # Find the characteristic
        char = _current_device._find_characteristic(uuid)
        if not char:
            print(f"[-] Characteristic not found: {uuid}")
            return

        # Check if the characteristic supports notifications
        if "notify" not in char.flags:
            print(f"[-] Characteristic does not support notifications. Flags: {', '.join(char.flags)}")
            return

        # Enable/disable notifications
        if action == "on":
            _current_device.enable_notifications(uuid, debugging_notification_callback)
            print(f"[+] Notifications enabled for {uuid}")
        else:
            _current_device.disable_notifications(uuid)
            print(f"[+] Notifications disabled for {uuid}")

    except Exception as exc:
        print_and_log(f"[-] Error with notifications: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)


def _cmd_detailed(args: List[str]) -> None:
    """Toggle detailed view mode."""
    global _detailed_view

    if args and args[0].lower() in ["on", "off"]:
        _detailed_view = args[0].lower() == "on"
    else:
        # Toggle the current state
        _detailed_view = not _detailed_view

    print(f"[*] Detailed view mode: {'ON' if _detailed_view else 'OFF'}")
    print("[*] Use 'services' or 'chars' commands to see the effect")


def _show_properties(props: Dict[str, Any], detailed: bool = False) -> None:
    """Format and print D-Bus properties.

    Parameters:
    -----------
    props : Dict[str, Any]
        The D-Bus properties dictionary
    detailed : bool, optional
        Whether to show detailed information, by default False
    """
    for key, value in sorted(props.items()):
        # Format special properties
        formatted_value = value

        # Format UUIDs
        if key.lower().endswith('uuid') and isinstance(value, str):
            if detailed:
                uuid_name = get_name_from_uuid(value)
                if uuid_name != "Unknown":
                    formatted_value = f"{value} ({uuid_name})"
            else:
                formatted_value = value

        # Format UUIDs in lists
        elif isinstance(value, list) and key.lower().endswith('uuids'):
            if detailed:
                formatted_uuids = []
                for uuid in value:
                    uuid_name = get_name_from_uuid(uuid)
                    if uuid_name != "Unknown":
                        formatted_uuids.append(f"{uuid} ({uuid_name})")
                    else:
                        formatted_uuids.append(uuid)
                formatted_value = formatted_uuids

        # Format device class
        elif key == "Class" and detailed:
            class_desc = format_device_class(value)
            formatted_value = f"Value: {value}         {class_desc}"

        # Format appearance
        elif key == "Appearance" and detailed:
            appearance_desc = decode_appearance(value)
            if appearance_desc:
                formatted_value = f"{value} ({appearance_desc})"

        # Format the output
        if isinstance(formatted_value, (list, dict)):
            print(f"  {key}: {json.dumps(formatted_value, indent=2)}")
        else:
            print(f"  {key}: {formatted_value}")


# Command mapping
_CMDS = {
    "help": _cmd_help,
    "scan": _cmd_scan,
    "connect": _cmd_connect,
    "disconnect": _cmd_disconnect,
    "info": _cmd_info,
    "interfaces": _cmd_interfaces,
    "props": _cmd_props,
    "methods": _cmd_methods,
    "signals": _cmd_signals,
    "call": _cmd_call,
    "monitor": _cmd_monitor,
    "introspect": _cmd_introspect,
    "services": _cmd_services,
    "chars": _cmd_chars,
    "char": _cmd_char,
    "read": _cmd_read,
    "write": _cmd_write,
    "notify": _cmd_notify,
    "detailed": _cmd_detailed,
    "ls": _cmd_ls,
    "cd": _cmd_cd,
    "pwd": _cmd_pwd,
    "back": _cmd_back,
    "quit": lambda _: None,
    "exit": lambda _: None,
}


def debug_shell() -> None:
    """Run the interactive debug shell."""
    print_and_log("[*] BLEEP Debug Mode - Type 'help' for commands, 'quit' to exit", LOG__GENERAL)
    
    while True:
        try:
            if _current_device:
                if _current_path and _current_path != _current_device._device_path:
                    # Show device and path
                    path_display = _current_path.replace(_current_device._device_path, '')
                    prompt = _DEVICE_PROMPT.format(_current_device.mac_address + ":" + path_display)
                else:
                    # Just show device
                    prompt = _DEVICE_PROMPT.format(_current_device.mac_address)
            else:
                if _current_path:
                    # Show path only
                    prompt = f"BLEEP-DEBUG[{_current_path}]> "
                else:
                    prompt = _PROMPT

            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        parts = shlex.split(line)
        if not parts:
            continue

        cmd, *rest = parts

        if cmd.lower() in {"quit", "exit"}:
            # Clean up before exiting
            if _monitoring:
                _monitor_stop_event.set()
                if _monitor_thread:
                    _monitor_thread.join(timeout=1.0)

            if _current_device:
                try:
                    _current_device.disconnect()
                except:
                    pass

            break

        handler = _CMDS.get(cmd.lower())
        if not handler:
            print("Unknown command - type 'help' for available commands")
            continue

        try:
            handler(rest)
        except Exception as exc:
            print_and_log(f"[-] Command failed: {exc}", LOG__DEBUG)


def parse_args(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BLEEP Debug Mode")
    parser.add_argument("device", nargs="?", help="MAC address of device to connect to")
    parser.add_argument(
        "-m", "--monitor", action="store_true", help="Monitor device properties in real-time"
    )
    parser.add_argument(
        "-n", "--no-connect", action="store_true", help="Don't connect to device (just scan)"
    )
    parser.add_argument(
        "-d", "--detailed", action="store_true",
        help="Show detailed information including decoded UUIDs and handle information"
    )
    return parser.parse_args(args)


def main(args=None) -> int:
    """Main entry point for Debug Mode."""
    global _current_device, _current_mapping, _monitoring, _detailed_view

    parsed_args = parse_args(args)

    # Set detailed view flag
    _detailed_view = parsed_args.detailed

    # Connect to device if specified
    if parsed_args.device and not parsed_args.no_connect:
        try:
            print_and_log(f"[*] Connecting to {parsed_args.device}...", LOG__GENERAL)
            _current_device, _current_mapping, _, _ = _connect_enum(parsed_args.device)
            print_and_log(f"[+] Connected to {parsed_args.device}", LOG__GENERAL)
            
            # Start monitoring if requested
            if parsed_args.monitor:
                _cmd_monitor(["start"])
        except Exception as exc:
            print_and_log(f"[-] Connection failed: {exc}", LOG__DEBUG)
            _print_detailed_dbus_error(exc)
            return 1

    # Run the debug shell
    try:
        debug_shell()
    except Exception as exc:
        print_and_log(f"[-] Debug shell error: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
