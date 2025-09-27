"""
BLEEP - Bluetooth Landscape Exploration & Enumeration Platform
"""

__version__ = "2.2.1"
__author__ = "Paul A. Wortman"

# Functional Debug Mode - 2025/07/09
# Refactor vs Monolith Gap Analysis - Initial Complete - 2025/07/09
# Next Steps: Create User Mode (more stream-lined)

# ---------------------------------------------------------------------------
# Initialise logging on *package import* so every code path (even when the
# CLI is not used) has the legacy /tmp/bti__logging__*.txt files available.
# This is a no-op if the module was already imported.
# ---------------------------------------------------------------------------
import importlib as _importlib

_importlib.import_module("bleep.core.log")  # noqa: F401 – side-effect import

# ---------------------------------------------------------------------------
# Initialize signal capture system
# ---------------------------------------------------------------------------
from bleep.signals import integrate_with_bluez_signals, patch_signal_capture_class

# Initialize signal capture and routing system
integrate_with_bluez_signals()
patch_signal_capture_class()

# ---------------------------------------------------------------------------
# Legacy module-namespace shims ------------------------------------------------
# ---------------------------------------------------------------------------
# The monolith exposed top-level modules named *bluetooth_constants* / *bluetooth_utils*
# etc.  Until every external script switches to *bleep.bt_ref.* we register
# read-only aliases that forward to the refactored variants.  This removes the
# last runtime dependency on the legacy files without changing their import path.
# ---------------------------------------------------------------------------

import sys as _sys
from types import ModuleType as _ModuleType

from bleep.bt_ref import (
    constants as _bt_constants,
    bluetooth_utils as _bt_utils,
    bluetooth_uuids as _bt_uuids,
    bluetooth_exceptions as _bt_excs,
)

_shims: dict[str, _ModuleType] = {
    "bluetooth_constants": _bt_constants,
    "bluetooth_utils": _bt_utils,
    "bluetooth_uuids": _bt_uuids,
    "bluetooth_exceptions": _bt_excs,
}

for _name, _mod in _shims.items():
    _sys.modules.setdefault(_name, _mod)
