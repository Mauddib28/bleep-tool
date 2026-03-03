"""D-Bus helpers, path navigation, and introspection commands for debug mode."""

from __future__ import annotations

import re
import threading
from typing import Any, Dict, List, Optional
from xml.dom import minidom

import dbus

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.core.errors import map_dbus_error
from bleep.bt_ref.utils import get_name_from_uuid

from bleep.modes.debug_state import DebugState, PROMPT, DEVICE_PROMPT


# ---------------------------------------------------------------------------
# D-Bus error formatting
# ---------------------------------------------------------------------------

def format_dbus_error(exc: Exception) -> str:
    """Format a D-Bus exception as 'name: message' for concise logging.

    If the exception is not a DBusException, returns str(exc).
    """
    if isinstance(exc, dbus.exceptions.DBusException):
        error_name = exc.get_dbus_name()
        error_msg = exc.get_dbus_message()

        msg_str = None
        if exc.args:
            if len(exc.args) >= 2:
                msg_str = str(exc.args[1]) if exc.args[1] is not None else None
                if not error_name and isinstance(exc.args[0], str) and exc.args[0].startswith("org."):
                    error_name = exc.args[0]
            elif len(exc.args) == 1:
                arg = exc.args[0]
                if isinstance(arg, str):
                    if arg.startswith("org."):
                        error_name = arg if not error_name else error_name
                    else:
                        msg_str = arg

        if msg_str is None and error_msg is not None:
            if isinstance(error_msg, str):
                if error_msg.startswith("(") and error_msg.endswith(")"):
                    import ast
                    try:
                        parsed = ast.literal_eval(error_msg)
                        if isinstance(parsed, tuple) and len(parsed) > 1:
                            msg_str = str(parsed[1]) if parsed[1] is not None else None
                            if not error_name and isinstance(parsed[0], str) and parsed[0].startswith("org."):
                                error_name = parsed[0]
                    except (ValueError, SyntaxError):
                        msg_str = error_msg
                else:
                    msg_str = error_msg
            elif isinstance(error_msg, tuple):
                if len(error_msg) > 1:
                    msg_str = str(error_msg[1]) if error_msg[1] is not None else None

        if msg_str is None:
            msg_str = str(exc)

        if error_name:
            return f"{error_name}: {msg_str}"
        return msg_str
    return str(exc)


def print_detailed_dbus_error(exc: Exception) -> None:
    """Print detailed information about a D-Bus exception."""
    print("\n[!] D-Bus Error Details:")

    if isinstance(exc, dbus.exceptions.DBusException):
        error_name = exc.get_dbus_name()
        error_msg = exc.get_dbus_message() or str(exc)

        print(f"[-] D-Bus Error: {error_name}")
        print(f"[-] Message: {error_msg}")

        if error_name == "org.freedesktop.DBus.Error.InvalidArgs":
            prop_match = re.search(r"property '([^']+)'", error_msg)
            method_match = re.search(r"method '([^']+)'", error_msg)
            iface_match = re.search(r"interface '([^']+)'", error_msg)

            if prop_match:
                print(f"[-] Invalid property: {prop_match.group(1)}")
            if method_match:
                print(f"[-] Invalid method: {method_match.group(1)}")
            if iface_match:
                print(f"[-] On interface: {iface_match.group(1)}")

        try:
            bleep_error = map_dbus_error(exc)
            print(f"[-] Maps to BLEEP error: {type(bleep_error).__name__}")
        except Exception as e:
            print(f"[-] Could not map to BLEEP error: {e}")
    else:
        print(f"[-] Error: {exc}")
        print(f"[-] Type: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# D-Bus path resolution helpers
# ---------------------------------------------------------------------------

def resolve_path(path: str, state: DebugState) -> str:
    """Resolve a relative or absolute path to a full D-Bus object path."""
    current_path = state.current_path or "/org/bluez"

    if path.startswith('/'):
        return path
    if path == '.':
        return current_path
    if path == '..':
        if current_path == '/':
            return '/'
        return '/'.join(current_path.split('/')[:-1]) or '/'
    if not path:
        return current_path

    if current_path.endswith('/'):
        return current_path + path
    return current_path + '/' + path


def get_object_at_path(path: str):
    """Get D-Bus object at the specified path."""
    try:
        bus = dbus.SystemBus()
        return bus.get_object("org.bluez", path)
    except Exception as e:
        print_and_log(f"[-] Error accessing path {path}: {e}", LOG__DEBUG)
        return None


def get_interfaces_at_path(path: str) -> list:
    """Get available interfaces at the specified path."""
    try:
        obj = get_object_at_path(path)
        if not obj:
            return []

        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        return [iface.get("name") for iface in root.findall("interface")]
    except Exception as e:
        print_and_log(f"[-] Error getting interfaces at {path}: {e}", LOG__DEBUG)
        return []


def get_child_nodes_at_path(path: str):
    """Get child nodes at the specified path.

    Returns (directories, interfaces).
    """
    try:
        obj = get_object_at_path(path)
        if not obj:
            return [], []

        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        dirs = [node.get("name") for node in root.findall("node") if node.get("name")]
        interfaces = get_interfaces_at_path(path)
        return dirs, interfaces
    except Exception as e:
        print_and_log(f"[-] Error getting child nodes at {path}: {e}", LOG__DEBUG)
        return [], []


# ---------------------------------------------------------------------------
# Navigation commands: ls, cd, pwd, back
# ---------------------------------------------------------------------------

def cmd_ls(args: List[str], state: DebugState) -> None:
    """List contents of the current path or specified path."""
    if not state.current_path:
        if state.current_device:
            state.current_path = state.current_device._device_path
        else:
            state.current_path = "/org/bluez"

    target_path = state.current_path
    if args:
        try:
            target_path = resolve_path(args[0], state)
        except Exception as e:
            print(f"[-] Invalid path: {e}")
            return

    try:
        obj = get_object_at_path(target_path)
        if not obj:
            print(f"[-] Path does not exist: {target_path}")
            return

        dirs, interfaces = get_child_nodes_at_path(target_path)

        for d in sorted(dirs):
            print(f"[DIR] {d}/")
        for i in sorted(interfaces):
            print(f"[IF]  {i}")
        if dirs or interfaces:
            print()
    except Exception as e:
        print(f"[-] Error listing path {target_path}: {e}")
        print_and_log(f"[-] Error in ls command: {e}", LOG__DEBUG)


def cmd_cd(args: List[str], state: DebugState) -> None:
    """Change the current D-Bus path."""
    if not state.current_path:
        if state.current_device:
            state.current_path = state.current_device._device_path
        else:
            state.current_path = "/org/bluez"

    if not args:
        new_path = state.current_device._device_path if state.current_device else "/org/bluez"
    else:
        target_path = args[0]
        if target_path.startswith('/'):
            new_path = target_path
        elif target_path == '..':
            if state.current_path == '/':
                new_path = '/'
            else:
                new_path = '/'.join(state.current_path.split('/')[:-1]) or '/'
        elif target_path == '.':
            new_path = state.current_path
        else:
            dirs, _ = get_child_nodes_at_path(state.current_path)
            if target_path not in dirs:
                print(f"[-] No such directory: {target_path}")
                return
            if state.current_path.endswith('/'):
                new_path = state.current_path + target_path
            else:
                new_path = state.current_path + '/' + target_path

    try:
        obj = get_object_at_path(new_path)
        if not obj:
            print(f"[-] Path does not exist: {new_path}")
            return

        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        introspect_iface.Introspect()

        if state.current_path and state.current_path != new_path:
            state.path_history.append(state.current_path)
        state.current_path = new_path
    except Exception as e:
        print(f"[-] Cannot navigate to {new_path}: {e}")


def cmd_pwd(args: List[str], state: DebugState) -> None:
    """Print current D-Bus path."""
    if not state.current_path:
        if state.current_device:
            state.current_path = state.current_device._device_path
        else:
            state.current_path = "/org/bluez"
    print(f"Current path: {state.current_path}")


def cmd_back(args: List[str], state: DebugState) -> None:
    """Navigate back to the previous path."""
    if not state.path_history:
        print("[-] No previous path in history")
        return
    state.current_path = state.path_history.pop()


# ---------------------------------------------------------------------------
# Introspection commands
# ---------------------------------------------------------------------------

def _get_path_for_cmd(state: DebugState) -> Optional[str]:
    """Return the best available path for introspection commands."""
    path = state.current_path
    if not path and state.current_device:
        path = state.current_device._device_path
    return path


def cmd_interfaces(args: List[str], state: DebugState) -> None:
    """List available interfaces on the current object."""
    path = _get_path_for_cmd(state)
    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        print("\nAvailable interfaces:")
        for iface in root.findall("interface"):
            print(f"  {iface.get('name')}")
        print()
    except Exception as exc:
        print_and_log(f"[-] Error retrieving interfaces: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def cmd_props(args: List[str], state: DebugState) -> None:
    """Show properties of an interface."""
    if not args:
        print("Usage: props <interface>")
        return

    interface = args[0]
    path = _get_path_for_cmd(state)
    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        props_iface = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        props = props_iface.GetAll(interface)

        print(f"[*] Properties for {interface}:")
        from bleep.modes.debug_gatt import show_properties
        show_properties(props, state.detailed_view)
    except dbus.exceptions.DBusException as e:
        error = map_dbus_error(e)
        print(f"[-] Error getting properties: {error}")
    except Exception as e:
        print(f"[-] Error: {e}")


def cmd_methods(args: List[str], state: DebugState) -> None:
    """Show methods of an interface."""
    if not args:
        print("Usage: methods <interface>")
        return

    interface_name = args[0]
    path = _get_path_for_cmd(state)
    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        print(f"\nMethods of {interface_name}:")
        methods_found = False

        for iface in root.findall("interface"):
            if iface.get("name") == interface_name:
                methods = iface.findall("method")
                if not methods:
                    print("  No methods found for this interface")
                    break

                for method in methods:
                    methods_found = True
                    method_name = method.get("name")

                    args_in = []
                    for arg in method.findall("arg"):
                        if arg.get("direction") != "out":
                            arg_name = arg.get("name") or "arg"
                            arg_type = arg.get("type") or "unknown"
                            args_in.append(f"{arg_name}: {arg_type}")

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
        print_detailed_dbus_error(exc)


def cmd_signals(args: List[str], state: DebugState) -> None:
    """List signals of an interface."""
    if not args:
        print("Usage: signals <interface>")
        return

    interface_name = args[0]
    path = _get_path_for_cmd(state)
    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        print(f"\nSignals of {interface_name}:")
        signals_found = False

        for iface in root.findall("interface"):
            if iface.get("name") == interface_name:
                signals = iface.findall("signal")
                if not signals:
                    print("  No signals found for this interface")
                    break

                for signal in signals:
                    signals_found = True
                    signal_name = signal.get("name")

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
        print_detailed_dbus_error(exc)


def cmd_call(args: List[str], state: DebugState) -> None:
    """Call a method on an interface."""
    if len(args) < 2:
        print("Usage: call <interface> <method> [args...]")
        return

    interface = args[0]
    method = args[1]
    method_args = args[2:] if len(args) > 2 else []

    path = _get_path_for_cmd(state)
    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        iface = dbus.Interface(obj, interface)
        method_obj = getattr(iface, method)

        result = method_obj(*method_args) if method_args else method_obj()
        print("[+] Method call successful")
        print(f"Result: {result}")
    except Exception as exc:
        print_and_log(f"[-] Method call failed: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)


def _monitor_properties(device_path: str, stop_event: threading.Event, state: DebugState) -> None:
    """Monitor properties of a device in real-time."""
    try:
        bus = dbus.SystemBus()
        bus.get_object("org.bluez", device_path)

        from dbus.mainloop.glib import DBusGMainLoop
        DBusGMainLoop(set_as_default=True)
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

            if state.current_device is not None:
                print(DEVICE_PROMPT.format(state.current_device.mac_address), end="", flush=True)
            else:
                print(PROMPT, end="", flush=True)

        bus.add_signal_receiver(
            properties_changed_cb,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path=device_path,
            path_keyword="path",
        )

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


def cmd_monitor(args: List[str], state: DebugState) -> None:
    """Start or stop real-time property monitoring."""
    if not state.current_device:
        print("[-] No device connected")
        return

    action = args[0].lower() if args else "start"

    if action == "start":
        if state.monitoring:
            print("[-] Monitoring already active")
            return

        state.monitor_stop_event = threading.Event()
        state.monitor_thread = threading.Thread(
            target=_monitor_properties,
            args=(state.current_device._device_path, state.monitor_stop_event, state),
        )
        state.monitor_thread.daemon = True
        state.monitor_thread.start()
        state.monitoring = True
    elif action == "stop":
        if not state.monitoring:
            print("[-] Monitoring not active")
            return

        state.monitor_stop_event.set()
        if state.monitor_thread:
            state.monitor_thread.join(timeout=1.0)
        state.monitoring = False
        print_and_log("[*] Property monitoring stopped", LOG__GENERAL)
    else:
        print("Usage: monitor [start|stop]")


def cmd_introspect(args: List[str], state: DebugState) -> None:
    """Introspect a D-Bus object."""
    if args:
        path = resolve_path(args[0], state)
    elif state.current_path:
        path = state.current_path
    elif state.current_device:
        path = state.current_device._device_path
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
        pretty_xml = re.sub(r'\n\s*\n', '\n', pretty_xml)

        print(f"\nIntrospection of {path}:\n")
        print(pretty_xml)
        print()
    except Exception as exc:
        print_and_log(f"[-] Introspection failed: {exc}", LOG__DEBUG)
