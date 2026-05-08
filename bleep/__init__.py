"""
BLEEP - Bluetooth Landscape Exploration & Enumeration Platform
"""

__version__ = "2.8.4"
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
# patch_signal_capture_class() is safe to run eagerly – it patches the
# SignalCapture dataclass __init__ and does not touch D-Bus.
# integrate_with_bluez_signals() instantiates system_dbus__bluez_signals()
# which calls dbus.SystemBus(); this triggers the circular-import problem if
# device_le.py is still being loaded.  Defer it to first actual D-Bus usage.
# ---------------------------------------------------------------------------
from bleep.signals import patch_signal_capture_class

patch_signal_capture_class()

_bluez_signals_integrated = False


def _ensure_bluez_signals():
    """Lazily run integrate_with_bluez_signals() once on first need."""
    global _bluez_signals_integrated
    if not _bluez_signals_integrated:
        from bleep.signals import integrate_with_bluez_signals
        integrate_with_bluez_signals()
        _bluez_signals_integrated = True

# ---------------------------------------------------------------------------
# Legacy module-namespace shims removed for complete self-sufficiency.
# External scripts should migrate to: from bleep.bt_ref import constants, utils, uuids, exceptions
# ---------------------------------------------------------------------------
