"""
Device D-Bus Interface
Provides the system_dbus__bluez_device__low_energy class from the original codebase.
"""

import dbus
from bleep.bt_ref.constants import *
from bleep.bt_ref.exceptions import *
from bleep.bt_ref.utils import dbus_to_python

# Import updated classes from refactored modules
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic

# Re-export the classes
__all__ = [
    "system_dbus__bluez_device__low_energy",
    "system_dbus__bluez_device__classic"
]
