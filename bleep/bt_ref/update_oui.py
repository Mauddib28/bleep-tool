#!/usr/bin/python3
"""IEEE OUI (MAC vendor) database updater for BLEEP.

Usage (CLI):
    python -m bleep.bt_ref.update_oui            # regenerates oui.py

Downloads the official IEEE MA-L (24-bit OUI) registry and converts it into a
static dictionary for vendor attribution of *public* Bluetooth/Ethernet MAC
addresses. The generated module is written to ``bleep/bt_ref/oui.py`` so regular
imports pick it up on next interpreter start.

This follows the same pattern as ``update_usb_ids.py`` / the BT SIG UUID updater,
keeping external reference-data handling consistent across ``bt_ref``.

Only the 24-bit MA-L registry is decoded. MA-M (28-bit) and MA-S (36-bit) blocks
share a 24-bit IEEE-owned prefix among many assignees, so decoding them by the
24-bit OUI would misattribute the vendor; those are intentionally left
unresolved (``get_oui_vendor`` returns ``None``) rather than reported wrongly.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.request as _url
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# Primary source: IEEE MA-L registry (CSV: Registry,Assignment,Organization Name,Address).
OUI_CSV_URL = "https://standards-oui.ieee.org/oui/oui.csv"
# Fallback: Wireshark's curated "manuf" file (TSV: prefix<TAB>short<TAB>long).
MANUF_URL = "https://www.wireshark.org/download/automated/data/manuf"

OUTPUT_PATH = Path(__file__).parent / "oui.py"

_HEX6_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
_MANUF_OUI_RE = re.compile(r"^([0-9A-Fa-f]{2}):([0-9A-Fa-f]{2}):([0-9A-Fa-f]{2})$")


def _pystr(value: str) -> str:
    """Render *value* as a safe double-quoted Python string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def download_oui_csv() -> Optional[str]:
    """Download the IEEE MA-L CSV; return text or ``None`` on failure."""
    try:
        with _url.urlopen(OUI_CSV_URL, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"IEEE OUI CSV download failed ({exc}); trying Wireshark manuf...")
        return None


def download_manuf() -> Optional[str]:
    try:
        with _url.urlopen(MANUF_URL, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"Wireshark manuf download failed ({exc})")
        return None


def parse_oui_csv(text: str) -> Dict[str, str]:
    """Parse IEEE MA-L CSV into ``{OUI_UPPER_HEX: organization}``."""
    out: Dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        assignment = (row.get("Assignment") or "").strip().upper()
        org = (row.get("Organization Name") or "").strip()
        if _HEX6_RE.match(assignment) and org:
            out[assignment] = org
    return out


def parse_manuf(text: str) -> Dict[str, str]:
    """Parse Wireshark ``manuf`` — keep only plain 24-bit OUIs (no mask)."""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        m = _MANUF_OUI_RE.match(parts[0].strip())
        if not m:
            continue  # masked (MA-M/MA-S) or malformed — skip
        oui = "".join(m.groups()).upper()
        # Prefer the long name (3rd column) when present, else the short name.
        name = (parts[2] if len(parts) >= 3 and parts[2].strip() else parts[1]).strip()
        if name:
            out[oui] = name
    return out


def generate_module_content(vendors: Dict[str, str], source: str) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = [
        "#!/usr/bin/python3",
        '"""IEEE OUI (MAC vendor) database for BLEEP.',
        "",
        f"Auto-generated from {source} on {timestamp}.",
        "Do not edit manually - run update_oui.py to regenerate.",
        "",
        "Maps 24-bit IEEE MA-L OUIs (upper-hex, no separators, e.g. 'FCFBFB') to the",
        "registered organization name. Only public/globally-administered addresses",
        "carry a meaningful OUI; random/private (RPA/NRPA/static) BLE addresses do not.",
        '"""',
        "from __future__ import annotations",
        "",
        "from typing import Optional",
        "",
        "# Dictionary mapping 24-bit OUIs (upper-hex, no separators) to organization names",
        "OUI_VENDORS = {",
    ]
    for oui, name in sorted(vendors.items()):
        content.append(f"    {_pystr(oui)}: {_pystr(name)},")
    content.append("}")
    content.append("")
    content.append('''
def get_oui_vendor(mac: str) -> Optional[str]:
    """Return the registered vendor for a MAC's 24-bit OUI, or ``None``.

    Accepts any separator (``:``/``-``/``_``) or none. Returns ``None`` for
    unknown OUIs and for inputs shorter than three octets (e.g. random/private
    addresses whose OUI is not a vendor identifier).
    """
    if not isinstance(mac, str):
        return None
    hex_only = "".join(c for c in mac if c in "0123456789abcdefABCDEF").upper()
    if len(hex_only) < 6:
        return None
    return OUI_VENDORS.get(hex_only[:6])
''')
    return "\n".join(content)


def update_oui() -> bool:
    """Download and (re)generate ``bt_ref/oui.py``. Returns success bool."""
    vendors: Dict[str, str] = {}
    source = ""
    csv_text = download_oui_csv()
    if csv_text:
        vendors = parse_oui_csv(csv_text)
        source = "IEEE MA-L registry (oui.csv)"
    if not vendors:
        manuf_text = download_manuf()
        if manuf_text:
            vendors = parse_manuf(manuf_text)
            source = "Wireshark manuf"
    if not vendors:
        print("Error: no OUI data obtained from any source.")
        return False

    print(f"Parsed {len(vendors)} OUIs from {source}. Writing {OUTPUT_PATH}...")
    OUTPUT_PATH.write_text(generate_module_content(vendors, source), encoding="utf-8")
    print("OUI database updated successfully!")
    return True


def regenerate() -> None:
    """``refresh-refs`` entry point — regenerate ``oui.py`` or raise on failure.

    Mirrors the ``regenerate()`` convention of the other ``bt_ref`` updaters so
    the unified ``refresh-refs`` mode can drive it uniformly. Raises
    ``RuntimeError`` when no OUI source is reachable; the committed ``oui.py`` is
    left untouched in that case (``update_oui`` never overwrites with empty data),
    preserving the "a refresh never zeroes a table" invariant.
    """
    if not update_oui():
        raise RuntimeError("IEEE OUI database regeneration failed (no source reachable)")


if __name__ == "__main__":
    update_oui()
