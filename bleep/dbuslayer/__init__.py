"""
D-Bus Layer for BLEEP (Bluetooth Landscape Exploration & Enumeration Platform)
Provides abstraction for D-Bus operations related to Bluetooth functionality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .adapter import system_dbus__bluez_adapter
from .signals import system_dbus__bluez_signals
from .agent import (
    system_dbus__bluez_generic_agent,
    system_dbus__bluez_agent_user_interface,
)
from .characteristic import Characteristic
from .descriptor import Descriptor

if TYPE_CHECKING:
    from .device import system_dbus__bluez_device__low_energy as system_dbus__bluez_device__low_energy  # noqa: F811
    from .device_classic import system_dbus__bluez_device__classic as system_dbus__bluez_device__classic  # noqa: F811
    from . import le_advertising as le_advertising  # noqa: F811
    from . import adv_monitor as adv_monitor  # noqa: F811
    from . import gatt_server as gatt_server  # noqa: F811
    from . import device_set as device_set  # noqa: F811
    from . import battery_provider as battery_provider  # noqa: F811
    from . import media_assistant as media_assistant  # noqa: F811
    from . import bluez_monitor as bluez_monitor  # noqa: F811
    from . import recovery as recovery  # noqa: F811
    from . import agent_io as agent_io  # noqa: F811
    from . import pairing_state as pairing_state  # noqa: F811
    from . import bond_storage as bond_storage  # noqa: F811

__version__ = "0.1.0"

__all__ = [
    # Core D-Bus interfaces
    "system_dbus__bluez_adapter",
    "system_dbus__bluez_device__low_energy",
    "system_dbus__bluez_device__classic",
    "system_dbus__bluez_signals",
    "system_dbus__bluez_generic_agent",
    "system_dbus__bluez_agent_user_interface",
    "Characteristic",
    "Descriptor",
    # LE Advertising (BZ-6/7)
    "le_advertising",
    # Advertisement monitor (BZ-11/12)
    "adv_monitor",
    # GATT server (BZ-4/5)
    "gatt_server",
    # Device sets (BZ-15)
    "device_set",
    # Battery provider (BZ-9/10)
    "battery_provider",
    # Media assistant (BZ-19)
    "media_assistant",
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
    "system_dbus__bluez_device__classic": ".device_classic",
    "le_advertising": ".le_advertising",
    "adv_monitor": ".adv_monitor",
    "gatt_server": ".gatt_server",
    "device_set": ".device_set",
    "battery_provider": ".battery_provider",
    "media_assistant": ".media_assistant",
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
