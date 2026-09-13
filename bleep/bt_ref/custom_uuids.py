"""User-promoted custom UUID names overlay (todo Item D promotion path).

The observed-UUID catalogue (:mod:`bleep.core.observations`) records UUIDs seen
on real devices under vendor/proprietary names the SIG registry does not know.
An operator can *promote* such an observation into the authoritative custom tier
(:data:`bleep.bt_ref.constants.UUID_NAMES`) so future runs resolve it directly.

Promotions persist as a small JSON overlay (default ``~/.bleep/custom_uuids.json``,
overridable via ``BLEEP_CUSTOM_UUIDS``) which :mod:`bleep.bt_ref.constants` merges
into ``UUID_NAMES`` at import. This keeps the codebase self-contained (no source
edits, no external dir dependency) while remaining reversible — deleting the JSON
(or an entry) undoes a promotion.

This module intentionally does NOT import :mod:`constants` at top level so that
``constants`` may import it during its own initialisation without a cycle.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Tuple


def _overlay_path() -> Path:
    return Path(
        os.getenv("BLEEP_CUSTOM_UUIDS", str(Path.home() / ".bleep" / "custom_uuids.json"))
    )


def load_overlay() -> Dict[str, str]:
    """Return the persisted custom UUID→name overlay (upper-cased keys).

    Best-effort: a missing or malformed overlay yields an empty dict and never
    raises, so importing ``constants`` cannot be broken by a bad file.
    """
    path = _overlay_path()
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {
            str(k).strip().upper(): str(v)
            for k, v in data.items()
            if k and v
        }
    except Exception:  # noqa: BLE001 - overlay must never break import
        return {}


def promote_uuid(uuid: str, name: str) -> Tuple[str, str]:
    """Promote ``uuid`` → ``name`` into the persistent custom overlay.

    Also updates the in-memory :data:`constants.UUID_NAMES` so the promotion
    takes effect immediately in the current process. Returns the normalised
    ``(uuid, name)`` pair. Raises ``ValueError`` on empty input and
    ``RuntimeError`` if the overlay cannot be written.
    """
    if not uuid or not name:
        raise ValueError("promote_uuid requires a non-empty uuid and name")
    key = uuid.strip().upper()
    overlay = load_overlay()
    overlay[key] = name

    path = _overlay_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(overlay, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Could not persist custom UUID overlay to {path}: {exc}") from exc

    # Live update for the current process (lazy import avoids an import cycle).
    try:
        from . import constants
        constants.UUID_NAMES[key] = name
    except Exception:  # noqa: BLE001 - persistence already succeeded
        pass
    return key, name
