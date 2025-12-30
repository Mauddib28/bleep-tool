"""Central constants for new BLEEP code.

This module wraps the legacy `bluetooth_constants` so new code can do:
    from bleep.core import constants as C
while legacy code continues to import the original file unchanged.

Only *new* constants that do not belong in the Bluetooth spec helper
should be declared here.
"""

from bleep.bt_ref.constants import *  # import from internal refactored module

# Place any **new** constants below; keep the namespace clean.

# Pretty-print column width used by several utilities
PRETTY_PRINT__GATT__FORMAT_LEN_NEW = 7

# Bluetooth device type enumeration
BT_DEVICE_TYPE_UNKNOWN = "unknown"  # Not enough information to determine type
BT_DEVICE_TYPE_CLASSIC = "classic"  # BR/EDR (Classic Bluetooth) device
BT_DEVICE_TYPE_LE = "le"            # Bluetooth Low Energy device
BT_DEVICE_TYPE_DUAL = "dual"        # Dual-mode device supporting both Classic and LE

# D-Bus Message Type Constants
# These are integer values returned by message.get_type() in dbus-python
DBUS_MESSAGE_SIGNAL = 1          # Signal message type
DBUS_MESSAGE_METHOD_CALL = 2      # Method call message type
DBUS_MESSAGE_METHOD_RETURN = 4    # Method return message type
DBUS_MESSAGE_ERROR = 3            # Error message type
