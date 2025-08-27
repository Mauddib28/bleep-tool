"""
D-Bus Layer for BLEEP (Bluetooth Landscape Exploration & Enumeration Platform)
Provides abstraction for D-Bus operations related to Bluetooth functionality.
"""

from .adapter import system_dbus__bluez_adapter
# Use lazy import for device classes to avoid circular imports
# from .device import system_dbus__bluez_device__low_energy
from .signals import system_dbus__bluez_signals
from .agent import (
    system_dbus__bluez_generic_agent,
    system_dbus__bluez_agent_user_interface,
)
from .characteristic import Characteristic
from .descriptor import Descriptor

__version__ = "0.1.0"

__all__ = [
    "system_dbus__bluez_adapter",
    "system_dbus__bluez_device__low_energy",
    "system_dbus__bluez_signals",
    "system_dbus__bluez_generic_agent",
    "system_dbus__bluez_agent_user_interface",
    "Characteristic",
    "Descriptor",
]

# Lazy-load device classes to break circular dependencies
def __getattr__(name):
    if name == "system_dbus__bluez_device__low_energy":
        from .device import system_dbus__bluez_device__low_energy
        return system_dbus__bluez_device__low_energy
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
