from __future__ import annotations
"""BLEEP in-package documentation helper.

This sub-package exposes the markdown guides located alongside the code so they
are reachable from the Python REPL / `pydoc` without having to open the files
manually.

Example usage
-------------
>>> import bleep.docs as docs
>>> help(docs)                 # shows the README.md content
>>> print(docs.get('cli_usage'))

You may also run ``python -m pydoc bleep.docs.cli_usage`` thanks to the dynamic
module loader below.
"""

from importlib import resources as _res
import importlib
import importlib.abc  # ensure .abc submodule is loaded for Loader/MetaPathFinder
import importlib.machinery  # ensure ModuleSpec is available
from typing import Dict

# Mapping logical names ↔ markdown filenames (extend if new guides are added)
_DOCS: Dict[str, str] = {
    'README': 'README.md',
    'cli_usage': 'cli_usage.md',
    'debug_mode': 'debug_mode.md',
    'ble_ctf_mode': 'ble_ctf_mode.md',
    'user_mode': 'user_mode.md',
    'changelog': 'changelog.md',
    'todo_tracker': 'todo_tracker.md',
}


def _read_md(filename: str) -> str:
    """Return the raw markdown text bundled with this package."""
    with _res.files(__name__).joinpath(filename).open('r', encoding='utf-8') as f:
        return f.read()

# Populate package docstring from main README
__doc__ = _read_md(_DOCS['README'])


def get(name: str) -> str:
    """Return markdown text for *name* (e.g. ``'cli_usage'``)."""
    try:
        return _read_md(_DOCS[name])
    except KeyError as exc:
        raise ValueError(f"Unknown doc: {name!r}. Available: {list(_DOCS)}") from exc


# --- Dynamic sub-module loader -------------------------------------------------
# Allow ``import bleep.docs.<name>`` where <name> maps to a markdown file. This
# creates lightweight modules whose __doc__ is the markdown content so pydoc
# renders it nicely.

class _MarkdownLoader(importlib.abc.Loader):
    def __init__(self, name: str, md_file: str) -> None:
        self._fullname = name
        self._md_file = md_file

    def create_module(self, spec):  # noqa: D401 – required importlib API
        return None  # use default module creation semantics

    def exec_module(self, module):
        module.__doc__ = _read_md(self._md_file)


class _MarkdownFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):  # noqa: D401
        pkg_prefix = __name__ + '.'
        if not fullname.startswith(pkg_prefix):
            return None
        short_name = fullname[len(pkg_prefix):]
        if short_name in _DOCS and short_name != 'README':
            return importlib.machinery.ModuleSpec(
                fullname,
                _MarkdownLoader(fullname, _DOCS[short_name]),
                is_package=False,
            )
        return None


import sys as _sys
if _MarkdownFinder not in [type(f) for f in _sys.meta_path]:
    _sys.meta_path.insert(0, _MarkdownFinder()) 