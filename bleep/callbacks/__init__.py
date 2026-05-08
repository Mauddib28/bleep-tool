"""User callback discovery and registration.

On import, :func:`load_callbacks` scans the user callback directory
(default ``~/.config/bleep/callbacks/``) for ``.py`` files containing
:class:`~bleep.callbacks.base.BleepCallback` subclasses and registers
them with the signal router.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from bleep.callbacks.base import BleepCallback
from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.signals.capture_config import SignalType

DEFAULT_CALLBACK_DIR = os.path.expanduser("~/.config/bleep/callbacks")

_loaded: Dict[str, BleepCallback] = {}


def load_callbacks(directory: Optional[str] = None) -> List[BleepCallback]:
    """Discover and register user callbacks from *directory*.

    Returns the list of successfully loaded callback instances.
    """
    cb_dir = Path(directory or DEFAULT_CALLBACK_DIR)
    if not cb_dir.is_dir():
        return []

    loaded: List[BleepCallback] = []
    for py_file in sorted(cb_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            instances = _load_module_callbacks(py_file)
            loaded.extend(instances)
        except Exception as exc:
            print_and_log(f"[callbacks] Failed to load {py_file.name}: {exc}", LOG__DEBUG)

    if loaded:
        _register_all(loaded)
    return loaded


def _load_module_callbacks(path: Path) -> List[BleepCallback]:
    """Import a single .py file and return instances of BleepCallback subclasses."""
    module_name = f"bleep_user_cb_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        return []
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)

    instances: List[BleepCallback] = []
    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if (
            isinstance(obj, type)
            and issubclass(obj, BleepCallback)
            and obj is not BleepCallback
            and getattr(obj, "name", "")
        ):
            inst = obj()
            instances.append(inst)
    return instances


def _register_all(callbacks: List[BleepCallback]) -> None:
    """Register loaded callbacks with the signal router."""
    from bleep.signals.router import register_callback

    for cb in callbacks:
        def _make_handler(callback: BleepCallback):
            def handler(**kwargs):
                if callback.trigger != SignalType.ANY:
                    sig = kwargs.get("signal_type")
                    if sig is not None and sig != callback.trigger:
                        return
                callback.execute(kwargs)
            return handler

        register_callback(cb.name, _make_handler(cb))
        _loaded[cb.name] = cb
        cb.on_load()
        print_and_log(
            f"[callbacks] Registered '{cb.name}' (trigger={cb.trigger.value})",
            LOG__DEBUG,
        )


def get_loaded() -> Dict[str, BleepCallback]:
    """Return a copy of currently loaded callbacks."""
    return dict(_loaded)
