"""
GATT profile handling functionality for BLEEP.

Note: GATT service/characteristic/descriptor wrappers currently live in
``bleep.dbuslayer`` (``service.py``, ``characteristic.py``, ``descriptor.py``).
This package is a placeholder for future migration into a dedicated namespace.
"""

# Planned future modules — guarded so the package loads cleanly before
# they are migrated here from bleep.dbuslayer.
try:
    from . import service  # noqa: F401
except ImportError:
    service = None  # type: ignore[assignment,misc]

try:
    from . import characteristic  # noqa: F401
except ImportError:
    characteristic = None  # type: ignore[assignment,misc]

try:
    from . import descriptor  # noqa: F401
except ImportError:
    descriptor = None  # type: ignore[assignment,misc]

__all__ = ["service", "characteristic", "descriptor"]
