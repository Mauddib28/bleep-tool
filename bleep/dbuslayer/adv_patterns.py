"""AdvertisementMonitor ``or_patterns`` validation and catch-all covering.

BlueZ ``or_patterns`` is memcmp-OR, not match-all. Empty ``Patterns`` or empty
content is rejected by ``bt_ad_pattern_new`` (monitor ``Release``, 0 events).
Valid AD types are ``0x01``–``0x3D`` and ``0xFF``; content is 1–31 bytes;
``start_pos + len <= 31``.

Default overlay (Module A, live 2026-09-04): **one** monitor whose patterns
are common GAP Flags bytes (AD type ``0x01``). Four of those values (``00``,
``02``, ``04``, ``06``) Activate'd on this host with 6 unique DeviceFound and
no bluetoothd restart. Prefix-covers of 8×256 / 62×256 ``NoReply``-killed
the daemon and are withdrawn. Completeness stays StartDiscovery harvest.

Manufacturer extras (``CID[:HEX]`` / UTF-8 payload string at offset 2) are a
**second** ``or_patterns`` child — mixing AD type ``0xFF`` onto the Flags
child ``NoReply``-killed software AdvMonitor on this host.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from bleep.dbuslayer.adv_monitor import MonitorPattern

__all__ = [
    "PatternError",
    "VALID_AD_TYPE_MIN",
    "VALID_AD_TYPE_MAX",
    "AD_TYPE_MANUFACTURER",
    "MSFT_PATTERNS_PER_MONITOR",
    "FLAGS_OR_VALUES",
    "is_valid_ad_type",
    "validate_pattern",
    "parse_pattern_arg",
    "parse_manufacturer_arg",
    "parse_mfr_string_arg",
    "parse_listen_extras",
    "company_id_le",
    "catch_all_pattern_groups",
    "catch_all_counts",
    "catch_all_summary",
    "chunk_patterns",
]

VALID_AD_TYPE_MIN = 0x01
VALID_AD_TYPE_MAX = 0x3D  # BT_AD_3D_INFO_DATA
AD_TYPE_MANUFACTURER = 0xFF
MSFT_PATTERNS_PER_MONITOR = 16
_MAX_CONTENT = 31
# Module A: one or_patterns child. 00/02/04/06 live-validated 2026-09-04
# (Activate, 6 unique, sampling 255). 05/18/1A are cheap GAP extras.
FLAGS_OR_VALUES = (0x00, 0x02, 0x04, 0x05, 0x06, 0x18, 0x1A)


class PatternError(ValueError):
    """Illegal AdvertisementMonitor pattern."""


def is_valid_ad_type(ad_type: int) -> bool:
    return VALID_AD_TYPE_MIN <= ad_type <= VALID_AD_TYPE_MAX or ad_type == AD_TYPE_MANUFACTURER


def all_valid_ad_types() -> Tuple[int, ...]:
    return tuple(range(VALID_AD_TYPE_MIN, VALID_AD_TYPE_MAX + 1)) + (AD_TYPE_MANUFACTURER,)


def validate_pattern(pattern: MonitorPattern) -> MonitorPattern:
    """Raise :class:`PatternError` if *pattern* cannot be activated by BlueZ."""
    if not isinstance(pattern.content, (bytes, bytearray)):
        raise PatternError("pattern content must be bytes")
    content = bytes(pattern.content)
    if not content:
        raise PatternError("pattern content must be non-empty (BlueZ rejects empty or_patterns)")
    if len(content) > _MAX_CONTENT:
        raise PatternError(f"pattern content exceeds {_MAX_CONTENT} bytes")
    if pattern.start_pos < 0 or pattern.start_pos >= _MAX_CONTENT:
        raise PatternError("start_pos must be 0..30")
    if pattern.start_pos + len(content) > _MAX_CONTENT:
        raise PatternError("start_pos + content length exceeds 31")
    if not is_valid_ad_type(int(pattern.ad_type)):
        raise PatternError(
            f"AD type 0x{int(pattern.ad_type):02X} is not valid "
            f"(BlueZ accepts 0x01-0x3D and 0xFF)"
        )
    return pattern


def parse_pattern_arg(raw: str) -> MonitorPattern:
    """Parse ``offset:ad_type:hex_content`` into a validated :class:`MonitorPattern`."""
    parts = raw.split(":", 2)
    if len(parts) != 3:
        raise PatternError(
            f"Pattern must be offset:ad_type:hex_content — got {raw!r}"
        )
    try:
        start_pos = int(parts[0], 0)
        ad_type = int(parts[1], 0)
        content = bytes.fromhex(parts[2])
    except ValueError as exc:
        raise PatternError(f"Invalid pattern {raw!r}: {exc}") from exc
    return validate_pattern(
        MonitorPattern(start_pos=start_pos, ad_type=ad_type, content=content)
    )


def company_id_le(company_id: int) -> bytes:
    """Return the 2-byte little-endian Company Identifier used in AD type 0xFF."""
    if not isinstance(company_id, int) or company_id < 0 or company_id > 0xFFFF:
        raise PatternError(f"company id must be 0..65535 — got {company_id!r}")
    return company_id.to_bytes(2, "little")


def parse_manufacturer_arg(raw: str) -> MonitorPattern:
    """Parse ``CID`` or ``CID:HEX`` into an AD type 0xFF pattern at offset 0.

    *CID* is decimal or ``0x``-hex (Bluetooth SIG Company Identifier). The
    optional *HEX* is a manufacturer-payload prefix after the 2-byte CID.
    Example: ``0x0006`` → ``0600``; ``0xFFFF:5a33`` → ``ffff5a33``.
    """
    if not raw or not str(raw).strip():
        raise PatternError("manufacturer argument must be CID or CID:HEX")
    text = str(raw).strip()
    cid_part, _, payload_part = text.partition(":")
    try:
        company_id = int(cid_part, 0)
    except ValueError as exc:
        raise PatternError(f"Invalid manufacturer company id {cid_part!r}: {exc}") from exc
    try:
        payload = bytes.fromhex(payload_part) if payload_part else b""
    except ValueError as exc:
        raise PatternError(f"Invalid manufacturer payload {payload_part!r}: {exc}") from exc
    content = company_id_le(company_id) + payload
    return validate_pattern(
        MonitorPattern(start_pos=0, ad_type=AD_TYPE_MANUFACTURER, content=content)
    )


def parse_mfr_string_arg(raw: str, *, start_pos: int = 2) -> MonitorPattern:
    """Match a UTF-8 string inside manufacturer AD data (type 0xFF).

    Default *start_pos* is 2 (first payload byte after the 16-bit company id).
    This is memcmp at a fixed offset, not a substring search — use
    ``--listen-pattern`` for other offsets. Example: ``Z3`` matches ESP32
    manufacturer payloads whose first two payload bytes are ``5a 33``.
    """
    if raw is None or raw == "":
        raise PatternError("manufacturer string must be non-empty")
    try:
        content = str(raw).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PatternError(f"Invalid manufacturer string {raw!r}: {exc}") from exc
    return validate_pattern(
        MonitorPattern(
            start_pos=start_pos, ad_type=AD_TYPE_MANUFACTURER, content=content
        )
    )


def parse_listen_extras(
    *,
    patterns: Sequence[str] | None = None,
    manufacturers: Sequence[str] | None = None,
    mfr_strings: Sequence[str] | None = None,
    mfr_string_offset: int = 2,
) -> List[MonitorPattern]:
    """Parse survey / advertise-monitor extra patterns into ``MonitorPattern``s."""
    out: List[MonitorPattern] = []
    for raw in patterns or []:
        out.append(parse_pattern_arg(raw))
    for raw in manufacturers or []:
        out.append(parse_manufacturer_arg(raw))
    for raw in mfr_strings or []:
        out.append(parse_mfr_string_arg(raw, start_pos=mfr_string_offset))
    return out


def chunk_patterns(
    patterns: Sequence[MonitorPattern], size: int
) -> List[List[MonitorPattern]]:
    if size < 1:
        raise PatternError("chunk size must be >= 1")
    return [list(patterns[i : i + size]) for i in range(0, len(patterns), size)]


def _flags_or_group() -> List[MonitorPattern]:
    return [
        MonitorPattern(start_pos=0, ad_type=0x01, content=bytes([b]))
        for b in FLAGS_OR_VALUES
    ]


def catch_all_pattern_groups(*, offload: bool = False) -> List[List[MonitorPattern]]:
    """Return OR-groups for the default listen overlay.

    One Flags-OR monitor (Module A). ``offload`` is accepted for API
    compatibility; 7 patterns fit the MSFT 16-pattern cap, so the group is
    the same. ``--listen-pattern`` extras are appended by the caller.
    """
    del offload
    group = _flags_or_group()
    if len(group) > MSFT_PATTERNS_PER_MONITOR:
        return chunk_patterns(group, MSFT_PATTERNS_PER_MONITOR)
    return [group]


def catch_all_counts(*, offload: bool = False) -> Tuple[int, int]:
    """Return ``(n_monitors, n_patterns)`` for the default overlay."""
    groups = catch_all_pattern_groups(offload=offload)
    return len(groups), sum(len(g) for g in groups)


def catch_all_summary(*, offload: bool = False) -> str:
    n_mon, n_pat = catch_all_counts(offload=offload)
    listed = ",".join(f"{b:02X}" for b in FLAGS_OR_VALUES)
    unit = "monitor" if n_mon == 1 else "monitors"
    return (
        f"Flags-OR overlay: {n_mon} {unit}, {n_pat} patterns "
        f"AD type 0x01 content {{{listed}}}"
    )
