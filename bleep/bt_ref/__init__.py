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

from importlib import import_module as _imp
import sys as _sys

# List of legacy reference modules that must stay importable by their original names
_ref_names = (
    "bluetooth_constants",
    "bluetooth_exceptions",
    "bluetooth_utils",
    "bluetooth_uuids",
)

for _name in _ref_names:
    try:
        # 1. Try to import legacy module from top-level path (development checkout)
        _legacy_mod = _imp(_name)
    except ModuleNotFoundError:
        # 2. Fallback: load the standalone file from the project root (works
        #    when the package is installed editable or as a wheel that bundles
        #    the files alongside setup.py).
        from pathlib import Path as _Path
        import importlib.util as _ilu

        _root = _Path(__file__).resolve().parent.parent.parent  # repo root
        _file = _root / f"{_name}.py"
        if not _file.exists():
            raise  # cannot satisfy import – propagate

        _spec = _ilu.spec_from_file_location(_name, str(_file))
        if _spec is None or _spec.loader is None:
            raise ModuleNotFoundError(f"Unable to create spec for {_name}")

        _legacy_mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_legacy_mod)  # type: ignore[arg-type]

    # Expose inside this namespace so internal code can do
    # `from bleep.bt_ref import bluetooth_constants`.
    globals()[_name] = _legacy_mod

    # Preserve absolute import path for third-party scripts still doing
    # `import bluetooth_constants`.
    _sys.modules.setdefault(_name, _legacy_mod)

# Clean up internal names
del _imp, _sys, _ref_names
