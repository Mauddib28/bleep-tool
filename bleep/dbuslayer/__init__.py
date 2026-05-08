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
    # Core D-Bus interfaces
    "system_dbus__bluez_adapter",
    "system_dbus__bluez_device__low_energy",
    "system_dbus__bluez_signals",
    "system_dbus__bluez_generic_agent",
    "system_dbus__bluez_agent_user_interface",
    "Characteristic",
    "Descriptor",
    # LE Advertising (BZ-6/7)
    "le_advertising",
    # Advertisement monitor (BZ-11/12)
    "adv_monitor",
    # Reliability components
    "bluez_monitor",
    "recovery",
    # Pairing agent components
    "agent_io",
    "pairing_state",
    "bond_storage",
]

_LAZY_MODULES = {
    "system_dbus__bluez_device__low_energy": ".device",
    "le_advertising": ".le_advertising",
    "adv_monitor": ".adv_monitor",
    "bluez_monitor": ".bluez_monitor",
    "recovery": ".recovery",
    "agent_io": ".agent_io",
    "pairing_state": ".pairing_state",
    "bond_storage": ".bond_storage",
}


def __getattr__(name):
    if name in _LAZY_MODULES:
        import importlib
        module = importlib.import_module(_LAZY_MODULES[name], __name__)
        value = getattr(module, name, module)
        globals()[name] = value
        return value
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
