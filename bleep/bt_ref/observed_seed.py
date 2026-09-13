#!/usr/bin/python3
"""Curated seed of well-known **non-SIG** UUIDs for the observed-UUID catalogue.

The observed-UUID catalogue (:func:`bleep.core.observations.get_observed_uuid_catalogue`)
answers "have we seen this UUID before, and under what name(s)?". Out of the box a
fresh database has seen nothing, so a vendor/proprietary UUID that the SIG registry
does not know about resolves to nothing useful. This module ships a small, curated
set of *widely documented* non-SIG UUIDs (vendor-base 128-bit) so recognition works
before the operator has personally observed a device.

Design constraints:

* **Non-SIG only.** SIG 16/32-bit UUIDs already resolve via ``bt_ref.uuids``; adding
  them here would be redundant and risk drift. Every entry is a full 128-bit,
  vendor-base UUID with a documented public origin.
* **Separate tier.** The catalogue tags these ``source="curated_seed"`` so the
  SIG / custom-overlay / observed / curated tiers stay visually distinct and the
  seed never masquerades as a first-party measurement.
* **Not fed to the classifier.** Kept deliberately out of the device-type
  classifier's observed-promotion path (see docs/device_type_classification.md);
  it is a naming aid only.
* **Easily expandable.** Add an entry as ``UUID: {"names": [...], "note": "..."}``.
  Keys must be upper-case dashed 128-bit UUIDs.
"""
from __future__ import annotations

from typing import Dict, List

# {canonical 128-bit UPPER-dashed UUID: {"names": [...], "note": "public origin"}}
OBSERVED_UUID_SEED: Dict[str, Dict[str, object]] = {
    "6E400001-B5A3-F393-E0A9-E50E24DCCA9E": {
        "names": ["Nordic UART Service (NUS)"],
        "note": "Nordic Semiconductor UART-over-BLE service base (nRF SDK).",
    },
    "6E400002-B5A3-F393-E0A9-E50E24DCCA9E": {
        "names": ["Nordic UART RX Characteristic"],
        "note": "Nordic UART service: host→peripheral write characteristic.",
    },
    "6E400003-B5A3-F393-E0A9-E50E24DCCA9E": {
        "names": ["Nordic UART TX Characteristic"],
        "note": "Nordic UART service: peripheral→host notify characteristic.",
    },
    "A82EFA21-AE5C-3DDE-9BBC-F16DA7B16C5A": {
        "names": ["Google Nearby / Fast Pair (vendor base)"],
        "note": "Google Nearby Share / Fast Pair vendor-base UUID (non-SIG).",
    },
}


def get_seed_names(uuid_128_upper: str) -> List[str]:
    """Return curated seed name(s) for a canonical 128-bit UUID (may be empty)."""
    entry = OBSERVED_UUID_SEED.get(uuid_128_upper)
    if not entry:
        return []
    names = entry.get("names") or []
    return list(names)
