"""Central constants for new BLEEP code.

This module wraps the legacy `bluetooth_constants` so new code can do:
    from bleep.core import constants as C
while legacy code continues to import the original file unchanged.

Only *new* constants that do not belong in the Bluetooth spec helper
should be declared here.
"""

from bluetooth_constants import *  # re-export everything so we stay source-compatible

# Place any **new** constants below; keep the namespace clean.

# Pretty-print column width used by several utilities
PRETTY_PRINT__GATT__FORMAT_LEN_NEW = 7
