"""Shared utilities for debug-mode command handlers."""

from __future__ import annotations

import struct
from typing import Optional, Tuple

_PACK_MAP = {
    "hex": None, "str": None, "file": None,
    "uint8": "B", "int8": "b",
    "uint16": "<H", "int16": "<h", "uint16be": ">H", "int16be": ">h",
    "uint32": "<I", "int32": "<i", "uint32be": ">I", "int32be": ">i",
    "float": "<f", "floatbe": ">f",
    "double": "<d", "doublebe": ">d",
}

VALUE_FORMAT_HELP = (
    "  Value formats:\n"
    "    hex:01ab23cd      - Hex-encoded bytes\n"
    "    str:hello         - UTF-8 string\n"
    "    file:/path/to/f   - Raw file contents\n"
    "    uint8:123         - 8-bit unsigned int\n"
    "    int8:-123         - 8-bit signed int\n"
    "    uint16:12345      - 16-bit unsigned int (LE)\n"
    "    int16:-12345      - 16-bit signed int (LE)\n"
    "    uint16be:12345    - 16-bit unsigned int (BE)\n"
    "    uint32:123456     - 32-bit unsigned int (LE)\n"
    "    int32:-123456     - 32-bit signed int (LE)\n"
    "    float:1.23        - 32-bit float (LE)\n"
    "    double:1.23       - 64-bit double (LE)\n"
    "    (plain text)      - Treated as UTF-8 string"
)


def parse_value(value_str: str) -> Tuple[bytes, Optional[str]]:
    """Parse a user-supplied value string into raw bytes.

    Returns ``(data, error_message)``.  On success *error_message* is ``None``.
    On failure *data* is ``b""`` and *error_message* describes the problem.
    """
    try:
        if ":" in value_str:
            fmt, val = value_str.split(":", 1)
            fmt = fmt.lower()
            if fmt == "hex":
                clean = "".join(c for c in val if c in "0123456789abcdefABCDEF")
                if len(clean) % 2 != 0:
                    clean = "0" + clean
                return bytes.fromhex(clean), None
            if fmt == "str":
                return val.encode(), None
            if fmt == "file":
                try:
                    with open(val, "rb") as fh:
                        return fh.read(), None
                except OSError as exc:
                    return b"", f"Cannot read file: {exc}"
            if fmt in _PACK_MAP and _PACK_MAP[fmt] is not None:
                pack_fmt = _PACK_MAP[fmt]
                if "f" in pack_fmt or "d" in pack_fmt:
                    return struct.pack(pack_fmt, float(val)), None
                return struct.pack(pack_fmt, int(val)), None
            return b"", f"Unknown format: {fmt}"
        return value_str.encode(), None
    except (ValueError, struct.error) as exc:
        return b"", f"Value parse error: {exc}"


def hexdump(data: bytes, *, width: int = 16) -> str:
    """Return a classic hex-dump string for *data*."""
    lines = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {offset:04x}  {hex_part:<{width * 3}}  {ascii_part}")
    return "\n".join(lines)
