"""High-level run-modes for the BLEEP CLI.

Only a minimal *interactive* mode is provided for now; other historical modes
(user/scan/exploration/agent…) will be re-implemented incrementally once their
specific features are required.

Modes are imported lazily via ``__getattr__`` so that ``python -m
bleep.modes.<mode>`` does not trigger a ``RuntimeWarning`` (the previous
eager ``import_module`` placed the submodule into ``sys.modules`` before
``runpy`` could execute it as ``__main__``).
"""

__all__ = ["interactive", "scan", "agent", "exploration", "analysis", "aoi", "signal", "blectf",
           "debug", "test", "picow", "scratch", "amusica"]


def __getattr__(name: str):
    if name in __all__:
        from importlib import import_module
        mod = import_module(f"bleep.modes.{name}")
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")