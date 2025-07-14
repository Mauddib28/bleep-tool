"""
Core package initialisation for BLEEP.

Deliberately kept lightweight to avoid circular-import problems.  Heavy
sub-modules (scanner, device_management, etc.) are loaded lazily on first
attribute access via __getattr__.
"""

from importlib import import_module as _imp
from types import ModuleType as _ModuleType
from typing import Any as _Any

from bleep.core.errors import (
    BleepError,
    DeviceNotFoundError,
    ConnectionError,
)

__all__ = [
    "system_dbus__device_management_service",
    "system_dbus__scanner_service",
    "system_dbus__error_handling_service",
    "BleepError",
    "DeviceNotFoundError",
    "ConnectionError",
]

# Lazy attribute loader -------------------------------------------------------

_lazy_map = {
    "system_dbus__device_management_service": "bleep.core.device_management",
    "system_dbus__scanner_service": "bleep.core.scanner",
    "system_dbus__error_handling_service": "bleep.core.error_handling",
}


def __getattr__(name: str) -> _Any:  # noqa: D401
    """Load heavy sub-modules on demand to break circular dependencies."""
    if name in _lazy_map:
        module: _ModuleType = _imp(_lazy_map[name])
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(name)
