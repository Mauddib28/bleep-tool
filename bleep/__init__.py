"""
BLEEP - Bluetooth Landscape Exploration & Enumeration Platform
"""

__version__ = "2.4.3"
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
# Legacy module-namespace shims removed for complete self-sufficiency.
# External scripts should migrate to: from bleep.bt_ref import constants, utils, uuids, exceptions
# ---------------------------------------------------------------------------
