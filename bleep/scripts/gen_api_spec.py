#!/usr/bin/env python3
"""Generate the authoritative package-hierarchy tree and ``__all__`` symbol
census for ``docs/api_specification.md``.

The generator is **static** — it parses each module's ``__all__`` with the
:mod:`ast` module rather than importing :mod:`bleep`, so it runs without the
runtime dependencies (D-Bus, GLib, PyYAML, …) and has no import side effects.

Run it as a **standalone file**, not via ``-m``: it is deliberately
dependency-free (stdlib only) so it never imports the ``bleep`` package (which
has D-Bus/logging import side effects).  ``python -m bleep.scripts.gen_api_spec``
would force the parent-package import and defeat that.

Usage
-----
    # Print the generated markdown blocks to stdout (review):
    python bleep/scripts/gen_api_spec.py

    # Rewrite the AUTOGEN-delimited blocks in docs/api_specification.md in place:
    python bleep/scripts/gen_api_spec.py --write

The doc must contain matching marker pairs, e.g.::

    <!-- AUTOGEN:hierarchy START (python bleep/scripts/gen_api_spec.py --write) -->
    ...generated content...
    <!-- AUTOGEN:hierarchy END -->

and likewise for ``AUTOGEN:census``.  Everything outside the markers (curated
prose, per-symbol description tables) is left untouched.
"""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Repository layout: this file is bleep/scripts/gen_api_spec.py, so the package
# root is two parents up (…/bleep) and the doc lives under …/bleep/docs.
_PKG_ROOT = Path(__file__).resolve().parents[1]
_DOC_PATH = _PKG_ROOT / "docs" / "api_specification.md"
_PKG_NAME = _PKG_ROOT.name  # "bleep"

# Directories excluded from the API tree/census. ``gatt`` and ``protocols`` are
# intentionally *kept* (they are real shipped packages) so the tree stays honest.
# ``scripts`` holds standalone CLI tools (no ``__init__.py``, not importable API),
# so it is excluded from the API-surface inventory.
_SKIP_DIRS = {"__pycache__", "docs", "scripts"}


def _parse_all(py_file: Path) -> Optional[List[str]]:
    """Return the list of names in a module's literal ``__all__``.

    Returns ``None`` when the module has no ``__all__`` or when it is not a
    plain literal list/tuple of string constants (e.g. built dynamically).
    """
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.target is not None:
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        value = node.value
        if isinstance(value, (ast.List, ast.Tuple)):
            names = [
                el.value
                for el in value.elts
                if isinstance(el, ast.Constant) and isinstance(el.value, str)
            ]
            # Only trust it if every element was a string constant.
            if len(names) == len(value.elts):
                return names
        return None  # __all__ present but not a plain literal
    return None


def _iter_modules() -> List[Tuple[Path, bool]]:
    """Yield ``(path, is_package)`` for every package dir and module file under
    the package root, sorted for stable output."""
    out: List[Tuple[Path, bool]] = []
    for path in sorted(_PKG_ROOT.rglob("*")):
        rel_parts = path.relative_to(_PKG_ROOT).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        if path.is_dir():
            if (path / "__init__.py").exists():
                out.append((path, True))
        elif path.suffix == ".py":
            out.append((path, False))
    return out


def _dotted(path: Path) -> str:
    rel = path.relative_to(_PKG_ROOT)
    if path.is_dir():
        return _PKG_NAME + ("." + ".".join(rel.parts) if rel.parts else "")
    parts = rel.with_suffix("").parts
    return ".".join((_PKG_NAME, *parts))


def build_hierarchy() -> str:
    """Return a tree view of all subpackages, annotating each with its direct
    ``.py`` module-file count so no shipped package is silently omitted."""
    dirs = sorted(
        {p.relative_to(_PKG_ROOT) for p, is_pkg in _iter_modules() if is_pkg},
        key=lambda p: p.parts,
    )
    # Count .py module files directly inside each package dir.
    module_counts: Dict[Path, int] = {}
    for p, is_pkg in _iter_modules():
        if not is_pkg:
            rel_parent = p.parent.relative_to(_PKG_ROOT)
            module_counts[rel_parent] = module_counts.get(rel_parent, 0) + 1

    def _is_last_sibling(d: Path) -> bool:
        parent = d.parent
        siblings = [x for x in dirs if x.parent == parent]
        return siblings[-1] == d

    lines: List[str] = [f"{_PKG_NAME}/"]
    root_mods = module_counts.get(Path("."), 0)
    lines.append(f"├── ({root_mods} top-level module files, incl. __init__.py, __main__.py)")
    for d in dirs:
        depth = len(d.parts) - 1
        indent = "    " * depth
        connector = "└──" if _is_last_sibling(d) else "├──"
        n = module_counts.get(d, 0)
        suffix = f"  ({n} module file{'s' if n != 1 else ''})" if n else "  (no module files)"
        lines.append(f"{indent}{connector} {d.parts[-1]}/{suffix}")
    return "```\n" + "\n".join(lines) + "\n```"


def build_census() -> str:
    """Return a concise per-top-level-package census table.

    For each top-level package under ``bleep/`` (subpackages folded in) it
    reports the number of ``.py`` module files and the total number of names
    exported via a literal ``__all__`` across that subtree, plus grand totals.
    """
    # group key -> [module_file_count, exported_name_total]
    groups: Dict[str, List[int]] = {}
    total_modules = 0
    total_symbols = 0

    for path, is_pkg in _iter_modules():
        rel = path.relative_to(_PKG_ROOT)
        top = rel.parts[0] if (len(rel.parts) > 1 or path.is_dir()) else "(root)"
        # A top-level module file (e.g. banner.py) groups under "(root)".
        if not is_pkg and len(rel.parts) == 1:
            top = "(root)"
        groups.setdefault(top, [0, 0])
        if is_pkg:
            names = _parse_all(path / "__init__.py")
        else:
            names = _parse_all(path)
            groups[top][0] += 1
            total_modules += 1
        if names is not None:
            groups[top][1] += len(names)
            total_symbols += len(names)

    ordered = ["(root)"] + sorted(k for k in groups if k != "(root)")
    header = (
        "| Top-level package | Module files | Exported names (Σ `__all__`) |\n"
        "|-------------------|-------------:|-----------------------------:|\n"
    )
    body_lines = []
    for k in ordered:
        if k not in groups:
            continue
        mods, syms = groups[k]
        label = k if k == "(root)" else f"`bleep.{k}`"
        body_lines.append(f"| {label} | {mods} | {syms} |")
    body = "\n".join(body_lines)
    footer = (
        f"\n\n**Totals:** {total_modules} `.py` module files; "
        f"**{total_symbols}** names exported via a literal `__all__`. "
        f"(Modules that build exports dynamically or omit `__all__` contribute 0 "
        f"to the count but are included in the module-file tally.)"
    )
    return header + body + footer


_MARKER_RE = (
    r"(<!--\s*AUTOGEN:{name}\s+START[^>]*-->)(.*?)(<!--\s*AUTOGEN:{name}\s+END\s*-->)"
)


def _replace_block(text: str, name: str, content: str) -> str:
    pattern = re.compile(_MARKER_RE.format(name=re.escape(name)), re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(
            f"[gen_api_spec] marker pair for AUTOGEN:{name} not found in {_DOC_PATH}"
        )
    return pattern.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--write",
        action="store_true",
        help="Rewrite the AUTOGEN blocks in docs/api_specification.md in place.",
    )
    args = ap.parse_args()

    hierarchy = build_hierarchy()
    census = build_census()

    if not args.write:
        print("=== AUTOGEN:hierarchy ===\n")
        print(hierarchy)
        print("\n=== AUTOGEN:census ===\n")
        print(census)
        return 0

    text = _DOC_PATH.read_text(encoding="utf-8")
    text = _replace_block(text, "hierarchy", hierarchy)
    text = _replace_block(text, "census", census)
    _DOC_PATH.write_text(text, encoding="utf-8")
    print(f"[gen_api_spec] updated {_DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
