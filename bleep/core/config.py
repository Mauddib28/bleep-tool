"""
Core configuration settings for BLEEP.
"""

import os
import logging
from pathlib import Path

# Base paths
BLEEP_ROOT = Path(__file__).parent.parent
DATA_DIR = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share")) / "bleep"
CACHE_DIR = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "bleep"
CONFIG_DIR = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "bleep"

# Ensure directories exist
for directory in [DATA_DIR, CACHE_DIR, CONFIG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Logging configuration
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Legacy logging paths (for backward compatibility)
general_logging = "/tmp/bti__logging__general.txt"
debug_logging = "/tmp/bti__logging__debug.txt"
enumerate_logging = "/tmp/bti__logging__enumeration.txt"
usermode_logging = "/tmp/bti__logging__usermode.txt"
agent_logging = "/tmp/bti__logging__agent.txt"
database_logging = "/tmp/bti__logging__database.txt"

# Log types
LOG__GENERAL = "GENERAL"
LOG__DEBUG = "DEBUG"
LOG__ENUM = "ENUMERATE"
LOG__USER = "USERMODE"
LOG__AGENT = "AGENT"
LOG__DATABASE = "DATABASE"

# Debug flag
dbg = 0

# Default adapter
DEFAULT_ADAPTER = "hci0"

# D-Bus configuration
DBUS_SERVICE = "org.bluez"
DBUS_NAMESPACE = "/org/bluez/"
DBUS_PROPERTIES = "org.freedesktop.DBus.Properties"
DBUS_OBJECT_MANAGER = "org.freedesktop.DBus.ObjectManager"

# Agent paths
AGENT_PATH = "/test/agent"
MESH_AGENT_PATH = "/mesh/test/agent"

# GATT Structure Properties
GATT__SERVICE__PROPERTIES = [
    "UUID",
    "Primary",
    "Device",
    "Includes",
    "Handle",
    "Characteristics",
]
GATT__CHARACTERISTIC__PROPERTIES = [
    "UUID",
    "Service",
    "Value",
    "WriteAcquired",
    "NotifyAcquired",
    "Notifying",
    "Flags",
    "Handle",
    "MTU",
]
GATT__DESCRIPTOR__PROPERTIES = ["UUID", "Characteristic", "Value", "Flags", "Handle"]

# Pretty Printing Variables
PRETTY_PRINT__GATT__FORMAT_LEN = 7

# Default timeout values
TIMEOUT_LIMIT_IN_SECONDS = 120  # 2 minutes
TIMEWAIT_IN_PROGRESS = 0.200  # 200 milliseconds

## D-Bus Configurations

# Import D-Bus
import dbus

# Ensure the GLib main-loop helper is loaded so that the attribute
# dbus.mainloop.glib.DBusGMainLoop exists even when the parent module
# was imported before the gi / gobject bindings were available.
try:
    import dbus.mainloop.glib  # noqa: F401 – side-effect import
except ImportError as _err:  # pragma: no cover – environment specific
    # Defer the failure until runtime code first uses D-Bus so that unit tests
    # which mock D-Bus can still import the package.
    import warnings

    warnings.warn(
        f"GLib main-loop bindings not available: {_err}. "
        "Bluetooth functionality will be disabled.",
        RuntimeWarning,
        stacklevel=2,
    )

# Initialise the GLib main-loop for D-Bus if available.
if hasattr(dbus, "mainloop") and hasattr(dbus.mainloop, "glib"):
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    # Make sure threading helpers are ready (no-op if compiled without thread support)
    if hasattr(dbus.mainloop.glib, "threads_init"):
        dbus.mainloop.glib.threads_init()

## Logging and Debugging Variables

## Constants for BlueZ (Make local, then bring in larger bluetooth_constants)
# BLE CTF Variables
BLE_CTF_ADDR = "CC:50:E3:B6:BC:A6"
INTROSPECT_INTERFACE = "org.freedesktop.DBus.Introspectable"
INTROSPECT_SERVICE_STRING = "service"
INTROSPECT_CHARACTERISTIC_STRING = "char"
INTROSPECT_DESCRIPTOR_STRING = "desc"

# Known Bluetooth Low Energy IDs
ARDUINO_BLE__BLE_UUID__MASK = "XXXXXXXX-0000-1000-8000-00805f9b34fb"
BLE__GATT__SERVICE__GENERIC_ACCESS_PROFILE = "00001800-0000-1000-8000-00805f9b34fb"
BLE__GATT__DEVICE_NAME = "00002a00-0000-1000-8000-00805f9b34fb"

# Details for GATT Structure Properties
GATT__SERVICE__PROPERTIES = [
    "UUID",
    "Primary",
    "Device",
    "Includes",
    "Handle",
    "Characteristics",
    "Value",
]
GATT__CHARACTERISTIC__PROPERTIES = [
    "UUID",
    "Service",
    "Value",
    "WriteAcquired",
    "NotifyAcquired",
    "Notifying",
    "Flags",
    "Handle",
    "MTU",
    "Notify",
    "Descriptors",
]
GATT__DESCRIPTOR__PROPERTIES = ["UUID", "Characteristic", "Value", "Flags", "Handle"]
# Note: The above are running lists of property values seen when exploring devices via user mode

# Pretty Printing Variables
PRETTY_PRINT__GATT__FORMAT_LEN = 7

# Default Variables for Use with Mapping
UNKNOWN_VALUE = "-=!=- UNKNOWN -=!=-"
