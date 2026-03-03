"""
CLI mode for Bluetooth adapter configuration.

Provides ``show``, ``get``, and ``set`` sub-actions for viewing and modifying
local adapter properties.  Properties reachable via D-Bus are accessed natively;
kernel-management-only properties (Class, local-name, SSP, …) are handled via
``bluetoothctl mgmt.*`` subprocess calls.
"""

from __future__ import annotations

import configparser
import sys
from pathlib import Path

from bleep.core.log import get_logger

logger = get_logger(__name__)

MAIN_CONF_PATH = Path("/etc/bluetooth/main.conf")

# Map of CLI property names → (D-Bus property name | None, is_writable_via_dbus)
_DBUS_PROPERTY_MAP: dict[str, tuple[str, bool]] = {
    "address":              ("Address", False),
    "address-type":         ("AddressType", False),
    "name":                 ("Name", False),
    "alias":                ("Alias", True),
    "class":                ("Class", False),
    "powered":              ("Powered", True),
    "discoverable":         ("Discoverable", True),
    "discoverable-timeout": ("DiscoverableTimeout", True),
    "pairable":             ("Pairable", True),
    "pairable-timeout":     ("PairableTimeout", True),
    "connectable":          ("Connectable", True),
    "discovering":          ("Discovering", False),
    "uuids":                ("UUIDs", False),
    "modalias":             ("Modalias", False),
    "roles":                ("Roles", False),
}

# Properties only reachable via bluetoothctl mgmt
_MGMT_ONLY_PROPERTIES = {
    "local-name", "ssp", "sc", "le", "bredr",
    "privacy", "fast-conn", "linksec", "wbs",
}

_BOOL_TRUTHY = {"on", "true", "1", "yes"}
_BOOL_FALSY = {"off", "false", "0", "no"}


def _parse_bool(value: str) -> bool:
    v = value.strip().lower()
    if v in _BOOL_TRUTHY:
        return True
    if v in _BOOL_FALSY:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}  (use on/off, true/false, 1/0)")


def read_main_conf() -> dict[str, dict[str, str]]:
    """Parse ``/etc/bluetooth/main.conf`` and return section→key→value dict.

    Returns an empty dict if the file is missing or unreadable.
    """
    if not MAIN_CONF_PATH.is_file():
        return {}
    try:
        cp = configparser.ConfigParser(allow_no_value=True)
        cp.read(str(MAIN_CONF_PATH))
        result: dict[str, dict[str, str]] = {}
        for section in cp.sections():
            result[section] = dict(cp.items(section))
        return result
    except Exception as e:
        logger.debug(f"Failed to parse {MAIN_CONF_PATH}: {e}")
        return {}


def _format_class(value: int) -> str:
    """Pretty-print a 24-bit Class of Device value."""
    major = (value >> 8) & 0x1F
    minor = (value >> 2) & 0x3F
    service = (value >> 13) & 0x7FF
    major_names = {
        0: "Miscellaneous", 1: "Computer", 2: "Phone",
        3: "LAN/Network", 4: "Audio/Video", 5: "Peripheral",
        6: "Imaging", 7: "Wearable", 8: "Toy",
        9: "Health", 31: "Uncategorized",
    }
    name = major_names.get(major, "Unknown")
    return f"0x{value:06X}  (Major: {major} [{name}], Minor: {minor}, Service: 0x{service:03X})"


def _print_show(adapter_name: str) -> int:
    """``adapter-config show`` — dump all adapter properties + boot defaults."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter

    try:
        adapter = system_dbus__bluez_adapter(adapter_name)
    except Exception as e:
        print(f"[!] Cannot access adapter {adapter_name}: {e}", file=sys.stderr)
        return 1

    info = adapter.get_adapter_info()
    if not info:
        print("[!] No properties returned from adapter", file=sys.stderr)
        return 1

    print(f"Adapter: /org/bluez/{adapter_name}")
    print("=" * 56)

    display_order = [
        "Address", "AddressType", "Name", "Alias", "Class",
        "Powered", "Connectable", "Discoverable", "DiscoverableTimeout",
        "Pairable", "PairableTimeout", "Discovering",
    ]
    printed = set()
    for key in display_order:
        if key in info:
            val = info[key]
            if key == "Class" and isinstance(val, int):
                val = _format_class(val)
            print(f"  {key:.<28s} {val}")
            printed.add(key)

    for key in sorted(info.keys()):
        if key in printed:
            continue
        val = info[key]
        if isinstance(val, list) and len(val) > 3:
            val = f"[{len(val)} entries]"
        print(f"  {key:.<28s} {val}")

    print()
    print("Writable properties (D-Bus):")
    for cli_name, (dbus_name, writable) in sorted(_DBUS_PROPERTY_MAP.items()):
        if writable:
            print(f"  {cli_name:<24s}  (D-Bus: {dbus_name})")

    print()
    print("Writable properties (mgmt — requires root/CAP_NET_ADMIN):")
    for prop in sorted(_MGMT_ONLY_PROPERTIES):
        print(f"  {prop}")
    # Also include 'class' since it's mgmt-only for writes
    print(f"  class")

    # Boot defaults from main.conf
    conf = read_main_conf()
    if conf:
        print()
        print(f"Boot defaults ({MAIN_CONF_PATH}):")
        print("-" * 56)
        for section, kvs in conf.items():
            active = {k: v for k, v in kvs.items() if v is not None}
            if active:
                print(f"  [{section}]")
                for k, v in active.items():
                    print(f"    {k} = {v}")
    else:
        print()
        print(f"Boot defaults: {MAIN_CONF_PATH} not found or empty")

    return 0


def _print_get(adapter_name: str, prop_name: str) -> int:
    """``adapter-config get <property>``."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter

    prop_lower = prop_name.lower()
    if prop_lower not in _DBUS_PROPERTY_MAP:
        print(f"[!] Unknown property: {prop_name}", file=sys.stderr)
        print(f"    Valid properties: {', '.join(sorted(_DBUS_PROPERTY_MAP))}", file=sys.stderr)
        return 1

    dbus_name, _ = _DBUS_PROPERTY_MAP[prop_lower]
    try:
        adapter = system_dbus__bluez_adapter(adapter_name)
    except Exception as e:
        print(f"[!] Cannot access adapter {adapter_name}: {e}", file=sys.stderr)
        return 1

    value = adapter._get_property(dbus_name)
    if value is None:
        print(f"[!] Property '{dbus_name}' returned None (may not be supported)", file=sys.stderr)
        return 1

    if dbus_name == "Class" and isinstance(value, int):
        print(_format_class(value))
    else:
        print(value)
    return 0


def _do_set(adapter_name: str, prop_name: str, values: list[str]) -> int:
    """``adapter-config set <property> <value...>``."""
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter

    prop_lower = prop_name.lower()

    try:
        adapter = system_dbus__bluez_adapter(adapter_name)
    except Exception as e:
        print(f"[!] Cannot access adapter {adapter_name}: {e}", file=sys.stderr)
        return 1

    # --- D-Bus writable properties ---
    if prop_lower in _DBUS_PROPERTY_MAP:
        dbus_name, writable = _DBUS_PROPERTY_MAP[prop_lower]
        if not writable and prop_lower != "class":
            print(f"[!] Property '{prop_name}' is read-only on D-Bus", file=sys.stderr)
            return 1

        # 'class' is readonly on D-Bus — route to mgmt
        if prop_lower == "class":
            return _set_via_mgmt(adapter, prop_lower, values)

        val = " ".join(values)
        if dbus_name in ("Powered", "Discoverable", "Pairable", "Connectable"):
            try:
                ok = adapter._set_property(
                    dbus_name, _parse_bool(val),
                    __import__("dbus").Boolean,
                )
            except ValueError as ve:
                print(f"[!] {ve}", file=sys.stderr)
                return 1
        elif dbus_name in ("DiscoverableTimeout", "PairableTimeout"):
            try:
                ok = adapter._set_property(
                    dbus_name, int(val),
                    __import__("dbus").UInt32,
                )
            except ValueError:
                print(f"[!] Value must be an integer (seconds)", file=sys.stderr)
                return 1
        elif dbus_name == "Alias":
            ok = adapter.set_alias(val)
        else:
            print(f"[!] No setter implemented for '{prop_name}'", file=sys.stderr)
            return 1

        if ok:
            print(f"[+] {dbus_name} set to: {val}")
            return 0
        else:
            print(f"[!] Failed to set {dbus_name}", file=sys.stderr)
            return 1

    # --- Mgmt-only properties ---
    if prop_lower in _MGMT_ONLY_PROPERTIES:
        return _set_via_mgmt(adapter, prop_lower, values)

    print(f"[!] Unknown property: {prop_name}", file=sys.stderr)
    all_props = sorted(
        set(_DBUS_PROPERTY_MAP.keys()) | _MGMT_ONLY_PROPERTIES | {"class"}
    )
    print(f"    Valid properties: {', '.join(all_props)}", file=sys.stderr)
    return 1


def _set_via_mgmt(adapter, prop_lower: str, values: list[str]) -> int:
    """Dispatch a set operation to the appropriate bluetoothctl mgmt method."""
    val = " ".join(values)

    dispatch: dict[str, tuple] = {
        "class":      ("set_class", lambda: (int(values[0]), int(values[1]))),
        "local-name": ("set_local_name", lambda: (values[0], values[1] if len(values) > 1 else None)),
        "ssp":        ("set_ssp", lambda: (_parse_bool(val),)),
        "sc":         ("set_secure_connections", lambda: (val,)),
        "le":         ("set_le", lambda: (_parse_bool(val),)),
        "bredr":      ("set_bredr", lambda: (_parse_bool(val),)),
        "privacy":    ("set_privacy", lambda: (_parse_bool(val),)),
        "fast-conn":  ("set_fast_connectable", lambda: (_parse_bool(val),)),
        "linksec":    ("set_link_security", lambda: (_parse_bool(val),)),
        "wbs":        ("set_wideband_speech", lambda: (_parse_bool(val),)),
    }

    if prop_lower not in dispatch:
        print(f"[!] No mgmt setter for '{prop_lower}'", file=sys.stderr)
        return 1

    method_name, args_fn = dispatch[prop_lower]

    if prop_lower == "class" and len(values) < 2:
        print("[!] Usage: adapter-config set class <major> <minor>", file=sys.stderr)
        print("    Example: adapter-config set class 1 4  (Computer/Desktop)", file=sys.stderr)
        return 1

    try:
        call_args = args_fn()
    except (ValueError, IndexError) as e:
        print(f"[!] Invalid arguments: {e}", file=sys.stderr)
        return 1

    print(f"[*] Setting {prop_lower} via bluetoothctl mgmt (may require root)...")
    method = getattr(adapter, method_name)
    ok = method(*call_args)

    if ok:
        print(f"[+] {prop_lower} set successfully")
        return 0
    else:
        print(f"[!] Failed to set {prop_lower} (check permissions — may need sudo)", file=sys.stderr)
        return 1


def handle_adapter_config(args) -> int:
    """Entry point called from cli.py dispatch."""
    if not args.action:
        print("Usage: bleep adapter-config {show|get|set} ...", file=sys.stderr)
        print("  show               Show all adapter properties and boot defaults")
        print("  get <property>     Get a single property value")
        print("  set <prop> <val>   Set a property value")
        return 1

    if args.action == "show":
        return _print_show(args.adapter)
    elif args.action == "get":
        return _print_get(args.adapter, args.property)
    elif args.action == "set":
        return _do_set(args.adapter, args.property, args.values)
    else:
        print(f"[!] Unknown action: {args.action}", file=sys.stderr)
        return 1
