"""
D-Bus interface functionality for BLEEP.
"""

# Avoid circular-import explosions by **lazy-loading** sub-modules on first
# attribute access instead of importing them eagerly at package initialisation
# time.  This allows callers to safely do
# `from bleep.dbus.device import system_dbus__bluez_device__low_energy` even
# while other modules inside *bleep.dbus* are still being initialised.

from importlib import import_module as _import_module
from types import ModuleType as _ModuleType
from typing import TYPE_CHECKING as _TYPE_CHECKING

__all__ = ["adapter", "device", "gatt", "timeout_manager"]


def __getattr__(name: str) -> _ModuleType:  # pragma: no cover – import meta-hook
    if name in __all__:
        module = _import_module(f"{__name__}.{name}")
        globals()[name] = module  # cache for subsequent look-ups
        return module
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# Help static analysers / type checkers resolve sub-modules without executing
# them at runtime.
if _TYPE_CHECKING:  # pragma: no cover – mypy/pylance only
    from . import adapter  # noqa: F401  (re-export for typing tools)
    from . import device   # noqa: F401
    from . import gatt     # noqa: F401
    from . import timeout_manager  # noqa: F401
