"""
Bluetooth reference data and constants.
"""

from . import constants
from . import exceptions
# utils / uuids may be temporarily broken while the update script regenerates
# them.  Avoid hard-crashing the entire *bleep.bt_ref* package when they raise
# a syntax error (e.g. incomplete file write).
try:
    from . import utils  # noqa: F401 – re-export
    from . import uuids  # noqa: F401 – re-export
except (SyntaxError, IndentationError):
    # Provide minimal stub modules so that other imports (e.g. legacy helpers)
    # do not explode while the update process is running.  They expose only
    # the attributes required by those scripts (an empty *UUID_NAMES* dict).

    import types as _types
    import warnings as _warn

    _stub_utils = _types.ModuleType("bleep.bt_ref.utils")
    _stub_utils.get_name_from_uuid = lambda _u: "Unknown"

    _stub_uuids = _types.ModuleType("bleep.bt_ref.uuids")
    _stub_uuids.SPEC_UUID_NAMES__SERV = {}

    globals()["utils"] = _stub_utils
    globals()["uuids"] = _stub_uuids
    import sys as _s
    _s.modules["bleep.bt_ref.utils"] = _stub_utils
    _s.modules["bleep.bt_ref.uuids"] = _stub_uuids

    _warn.warn(
        "bleep.bt_ref: Falling back to stub utils/uuids – run the UUID updater "
        "then restart to restore full functionality."
    )

__all__ = ["constants", "exceptions", "utils", "uuids"]

# Export UUID translator if available
try:
    from . import uuid_translator  # noqa: F401
    __all__.append("uuid_translator")
except (ImportError, SyntaxError):
    pass

