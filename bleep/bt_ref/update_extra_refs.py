#!/usr/bin/python3
"""Generator for non-UUID SIG reference tables that need bespoke shaping.

Two families of Bluetooth SIG *assigned_numbers* tables do not fit the flat
``{id: name}`` codegen used by :mod:`bleep.bt_ref.update_ble_uuids` (which emits
``uuids.py``):

* **Class-of-Device** (`core/class_of_device.yaml`) — nested
  ``cod_services`` (bit list) + ``cod_device_class`` (major → minor list). This is
  the same data the historical `core/fhs.yaml` carried (the FHS packet embeds the
  CoD field); `fhs.yaml` no longer ships in the live SIG repo, so
  ``class_of_device.yaml`` is the canonical source. → ``bt_ref/cod.py``
* **Bluetooth Mesh** (`mesh/mesh_model_uuids.yaml`, `mesh/mesh_beacon_types.yaml`).
  → ``bt_ref/mesh_ids.py``

Keeping this separate from ``update_ble_uuids.py`` means ``uuids.py`` is **never
disturbed** by a mesh/CoD refresh (zero drift risk for the existing SIG tables).

Design mirrors ``update_ble_uuids``: network-best-effort with a committed
``yaml_cache`` fallback, so the package stays self-contained and offline-safe. A
failed fetch (and no cache) leaves the previously committed module untouched —
it never zeroes a table.

Usage:
    python -m bleep.bt_ref.update_extra_refs      # regenerate cod.py + mesh_ids.py
"""
from __future__ import annotations

import pprint
from datetime import datetime
from pathlib import Path

import yaml as _yaml

from bleep.bt_ref.constants import BT_SIG_BASE_UUID_SUFFIX
from bleep.bt_ref.update_ble_uuids import (
    _cache_yaml_file,
    _download_file,
    _load_cached_yaml,
    _SIG_ROOT,
)

_HERE = Path(__file__).parent
_COD_OUT = _HERE / "cod.py"
_MESH_OUT = _HERE / "mesh_ids.py"

_FILES = {
    "CLASS_OF_DEVICE": "assigned_numbers/core/class_of_device.yaml",
    "MESH_MODEL_UUIDS": "assigned_numbers/mesh/mesh_model_uuids.yaml",
    "MESH_BEACON_TYPES": "assigned_numbers/mesh/mesh_beacon_types.yaml",
}

_HDR = (
    "#!/usr/bin/python3\n\n"
    "# Auto-generated {title}\n"
    "# DO NOT EDIT - run `python -m bleep.bt_ref.update_extra_refs` (or `bleep refresh-refs`).\n"
    "# Generated: {ts}\n"
    "# Source: {src}\n\n"
)


# ---------------------------------------------------------------------------
# Fetch (network-best-effort → committed cache fallback)
# ---------------------------------------------------------------------------

def _fetch(key: str) -> dict | None:
    url = _SIG_ROOT + _FILES[key]
    print(f"[*] Fetching {key}: {url}")
    data = _download_file(url)
    if data:
        try:
            parsed = _yaml.safe_load(data)
            _cache_yaml_file(key, data)  # keep the committed cache fresh
            return parsed
        except Exception as e:  # pragma: no cover - defensive
            print(f"[!] Parse error for {key}: {e}")
    print(f"[*] Falling back to committed cache for {key}")
    return _load_cached_yaml(key)


def _as_int(value) -> int:
    s = str(value)
    return int(s, 16) if s.lower().startswith("0x") else int(s)


# ---------------------------------------------------------------------------
# Compilers
# ---------------------------------------------------------------------------

def _compile_cod(data: dict):
    """(services{bit:name}, majors{major:name}, minors{major:{value:name}},
    subminors{major:{value:name}})."""
    services: dict[int, str] = {}
    for e in (data.get("cod_services") or []):
        services[int(e["bit"])] = str(e["name"]).strip()

    majors: dict[int, str] = {}
    minors: dict[int, dict[int, str]] = {}
    subminors: dict[int, dict[int, str]] = {}
    for e in (data.get("cod_device_class") or []):
        mj = int(e["major"])
        majors[mj] = str(e["name"]).strip()
        mm: dict[int, str] = {}
        # ``minor`` holds the standard per-major minor list. For LAN/NAP (major 3)
        # these are the 3-bit utilisation levels; the decoder handles that split.
        for sub in (e.get("minor") or []):
            mm[_as_int(sub["value"])] = str(sub["name"]).strip()
        if mm:
            minors[mj] = mm
        # ``subminor`` is the low bit-field used by the split majors (e.g. LAN/NAP
        # sub-availability). Retained so the decoder sources its names here too.
        sm: dict[int, str] = {}
        for sub in (e.get("subminor") or []):
            sm[_as_int(sub["value"])] = str(sub["name"]).strip()
        if sm:
            subminors[mj] = sm
    return services, majors, minors, subminors


def _compile_mesh_models(data: dict) -> dict[str, str]:
    """{full 128-bit uppercase UUID: model name} so ``get_name_from_uuid`` matches."""
    out: dict[str, str] = {}
    for e in (data.get("mesh_model_uuids") or []):
        u16 = _as_int(e["uuid"])
        out[f"0000{u16:04X}{BT_SIG_BASE_UUID_SUFFIX}"] = str(e["name"]).strip()
    return out


def _compile_mesh_beacons(data: dict) -> dict[int, str]:
    out: dict[int, str] = {}
    for e in (data.get("mesh_beacon_types") or []):
        out[_as_int(e["value"])] = str(e["name"]).strip()
    return out


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------

def _emit(path: Path, title: str, src: str, blocks: list[tuple[str, dict]]) -> None:
    body = [_HDR.format(title=title, ts=datetime.now().isoformat(timespec="seconds"), src=src)]
    for var, val in blocks:
        body.append(f"{var} = " + pprint.pformat(val, indent=4, width=100, sort_dicts=True))
        body.append("")
    path.write_text("\n".join(body), encoding="utf-8")


def regenerate() -> None:
    """Regenerate ``cod.py`` and ``mesh_ids.py`` (both non-destructive on failure)."""
    cod = _fetch("CLASS_OF_DEVICE")
    if cod:
        services, majors, minors, subminors = _compile_cod(cod)
        _emit(
            _COD_OUT,
            "Class-of-Device tables (SIG core/class_of_device.yaml)",
            _FILES["CLASS_OF_DEVICE"],
            [
                ("COD_SERVICES", services),
                ("COD_MAJOR_DEVICE_CLASS", majors),
                ("COD_MINOR_DEVICE_CLASS", minors),
                ("COD_SUBMINOR_DEVICE_CLASS", subminors),
            ],
        )
        print(f"[+] Wrote {_COD_OUT.name} ({len(majors)} majors, {len(services)} service bits)")
    else:
        print("[!] Class-of-Device source unavailable; leaving cod.py untouched")

    models = _fetch("MESH_MODEL_UUIDS")
    beacons = _fetch("MESH_BEACON_TYPES")
    if models or beacons:
        _emit(
            _MESH_OUT,
            "Bluetooth Mesh assigned numbers (SIG mesh/*.yaml)",
            "mesh_model_uuids.yaml, mesh_beacon_types.yaml",
            [
                ("MESH_MODEL_UUIDS", _compile_mesh_models(models or {})),
                ("MESH_BEACON_TYPES", _compile_mesh_beacons(beacons or {})),
            ],
        )
        print(f"[+] Wrote {_MESH_OUT.name}")
    else:
        print("[!] Mesh sources unavailable; leaving mesh_ids.py untouched")


if __name__ == "__main__":
    regenerate()
