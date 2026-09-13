from __future__ import annotations
"""bleep.ble_ops.classic_sdp – SDP service discovery for Bluetooth Classic.

This helper intentionally avoids third-party Bluetooth libraries.  It relies on
BlueZ’s *sdptool* binary to obtain the full SDP record (required for RFCOMM
channel extraction) because BlueZ’s D-Bus API only exposes the service UUID
list, not the protocol descriptor details.

Discovery chain (bc-53):
    1. ``Device1.GetServiceRecords`` (D-Bus, fast, BlueZ >= 5.66)
    2. ``sdptool browse <addr>`` (plain browse — follows the public browse group;
       the only single source that reliably returns every advertised record with
       its RFCOMM channel and L2CAP PSM; parsed by ``_parse_records``)
    3. ``sdptool browse --xml <addr>`` (structured XML fallback)
    4. ``sdptool records <addr>`` (human-readable handle-range scan, last resort)

Typical usage
-------------
>>> from bleep.ble_ops.classic.sdp import discover_services_sdp, build_svc_map
>>> records = discover_services_sdp("AA:BB:CC:DD:EE:FF")
>>> svc_map = build_svc_map(records)   # collision-safe keyed map

Connectionless mode (with l2ping reachability check):
>>> records = discover_services_sdp("AA:BB:CC:DD:EE:FF", connectionless=True)

Returned structure is a list of dicts::
    {"name": str | None,
     "uuid": str | None,
     "channel": int | None,
     "handle": int | None,  # Service Record Handle (0x0000)
     "profile_descriptors": List[Dict] | None,  # Bluetooth Profile Descriptor List (0x0009): [{"uuid": str, "version": int}]
     "protocol_descriptors": List[Dict] | None,  # Protocol Descriptor List (0x0004): [{"uuid": str, "params": {...}}]
     "service_version": int | None,  # Service Version (0x0300)
     "description": str | None,  # Service Description (0x0101)
     "mas_instance_id": int | None,  # MAS Instance ID (0x0315) – MAP only
     "supported_message_types": int | None,  # Supported Message Types (0x0316) – MAP only
     "supported_features": int | None,  # MapSupportedFeatures bitmask (0x0317) – MAP only
     "source": str | None,  # provenance: "dbus" | "browse" | "xml" | "records"
                            #   (or "a+b" when unioned via source="merge"/"all")
     "attribute_labels": Dict[str, str] | None,  # {attr_id_hex: SDP attribute label}
                            #   for attribute IDs present in the record. The universal range
                            #   (0x0000-0x000D, 0x0100-0x0102; BlueZ lib/sdp.h) always resolves.
                            #   Context-dependent IDs (>= 0x0200) resolve only via the record's
                            #   Service Class (SIG per-profile tables), so e.g. 0x0200 labels as
                            #   HIDDeviceReleaseNumber for a HID record but IpSubnet for PAN, and
                            #   is omitted when the service class is unknown. Additive; never
                            #   drops raw data or overwrites a parsed field.
     "raw": str}  # full block text for reference

Source selection (bc-source-union)
----------------------------------
``discover_services_sdp(..., source=...)`` selects which discovery source(s) to
use.  ``"auto"`` (default) preserves the historical first-success-wins chain
above.  ``"dbus" | "browse" | "xml" | "records"`` force a single source.
``"merge"`` (alias ``"all"``) queries *every* available source and unions the
records keyed by ``service_record_handle`` (fallback ``uuid``, then ``name``),
filling missing fields and recording per-field provenance.  When two sources
disagree on a scalar field the union stores a ``source_conflicts`` mapping
(``{field: {source: value}}``) which :class:`bleep.analysis.SDPAnalyzer`
surfaces as a ``source_discrepancy`` anomaly.  Merged records preserve *all*
captured text by concatenating each source's raw block under a ``# source:``
header, so no observed data is discarded.

The discovery functions raise :class:`~bleep.core.errors.NotSupportedError` if
*sdptool* is missing from PATH, :class:`~bleep.core.errors.ConnectionError` if the
target is unreachable (connectionless mode), or :class:`~bleep.core.errors.BLEEPError`
if SDP discovery yields no records / *sdptool* exits with an error.
"""

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from typing import List, Dict, Any, Optional

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.core.errors import BLEEPError, ConnectionError, NotSupportedError
from bleep.bt_ref.constants import RESULT_ERR, RESULT_ERR_NOT_FOUND
from bleep.bt_ref.sdp_attr_ids import resolve_sdp_attr_id
import dbus

# SIG sibling reference tables (defensive: enrichment must never break parsing).
try:  # pragma: no cover - trivial import guard
    from bleep.bt_ref.sdp_profile_attr_ids import (
        SDP_STRING_ATTR_OFFSETS as _SDP_STRING_ATTR_OFFSETS,
        SDP_PROTOCOL_PARAMETERS as _SDP_PROTOCOL_PARAMETERS,
    )
except Exception:  # pragma: no cover
    _SDP_STRING_ATTR_OFFSETS, _SDP_PROTOCOL_PARAMETERS = {}, {}

# LanguageBaseAttributeIDList: attr 0x0006 is a sequence of uint16 triplets
# (code_ISO639, encoding, base_offset); string attributes live at base+offset.
# Primary base 0x0100 is already labelled by the universal table.
_SDP_PRIMARY_LANG_BASE = 0x0100

__all__ = [
    "build_svc_map",
    "discover_service_channel",
    "discover_services_sdp",
    "discover_services_sdp_connectionless",
    "format_protocol_descriptors",
]

# Import l2ping helper for connectionless reachability check
try:
    from bleep.ble_ops.classic.ping import classic_l2ping
except ImportError:
    classic_l2ping = None  # Graceful degradation if classic_ping not available

# ---------------------------------------------------------------------------
# D-Bus helpers (bc-15)
# ---------------------------------------------------------------------------


def _discover_services_dbus(mac_address: str, timeout: int = 5) -> List[Dict[str, Any]]:
    """Try to read SDP records via BlueZ Device1.GetServiceRecords.

    Returns empty list if the method is unavailable or record XML misses
    RFCOMM information.  Any exception is caught and logged at DEBUG level –
    callers decide whether to fall back to *sdptool*.
    """

    mac_address = mac_address.strip().upper()

    try:
        bus = dbus.SystemBus()
        om = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
        objects = om.GetManagedObjects()
        device_path = None
        for path, ifaces in objects.items():
            if "org.bluez.Device1" not in ifaces:
                continue
            if ifaces["org.bluez.Device1"].get("Address", "").upper() == mac_address:
                device_path = path
                break

        if not device_path:
            print_and_log("[classic_sdp] Device not found on bus for D-Bus SDP", LOG__DEBUG)
            return []

        dev_obj = bus.get_object("org.bluez", device_path)
        introspect_xml = dbus.Interface(dev_obj, "org.freedesktop.DBus.Introspectable").Introspect()
        if "GetServiceRecords" not in introspect_xml:
            print_and_log("[classic_sdp] Device1.GetServiceRecords not available – BlueZ < 5.66", LOG__DEBUG)
            return []

        dev_iface = dbus.Interface(dev_obj, "org.bluez.Device1")
        try:
            # BlueZ returns an array of dicts (variant {sv}) where each record
            # has key "Record" containing XML (string) – tolerate both ay and s.
            records_variant = dev_iface.GetServiceRecords()
        except dbus.exceptions.DBusException as exc:
            print_and_log(
                "[classic_sdp] GetServiceRecords failed ({}): {}: {}".format(
                    device_path,
                    getattr(exc, "get_dbus_name", lambda: "unknown")(),
                    getattr(exc, "get_dbus_message", lambda: "")() or "",
                ),
                LOG__DEBUG,
            )
            return []

        parsed: List[Dict[str, Any]] = []
        for rec in records_variant:
            # Convert Variant/ByteArray to str if necessary
            if isinstance(rec, (bytes, bytearray)):
                xml_text = bytes(rec).decode(errors="ignore")
            else:
                xml_text = str(rec)

            # Quick-parse XML; look for service-name attribute 0x0100 and
            # RFCOMM protocol descriptor list (0x0004 → uuid 0x0003 channel …)
            try:
                root = ET.fromstring(xml_text)
            except ET.ParseError:
                continue

            name_val = None
            uuid_val = None
            channel_val: Optional[int] = None
            handle_val: Optional[int] = None
            profile_descriptors: Optional[List[Dict[str, Any]]] = None
            protocol_descriptors: Optional[List[Dict[str, Any]]] = None
            service_version_val: Optional[int] = None
            description_val: Optional[str] = None
            mas_instance_id: Optional[int] = None
            supported_message_types: Optional[int] = None
            supported_features_val: Optional[int] = None

            for attr in root.findall("attribute"):
                attr_id = attr.get("id", "").lower()
                if attr_id == "0x0100":  # Service Name
                    name_val = attr.findtext("text") or None
                elif attr_id == "0x0101":  # Service Description
                    description_val = attr.findtext("text") or None
                elif attr_id == "0x0000":  # Service Record Handle
                    handle_elem = attr.find("uint32") or attr.find("uint16") or attr.find("uint8")
                    if handle_elem is not None:
                        try:
                            handle_val = int(handle_elem.text, 0)
                        except (ValueError, AttributeError):
                            pass
                elif attr_id == "0x0003":
                    # Service ID UUID 16-bit
                    uuid_val = f"0x{attr.findtext('uint16').upper()}" if attr.find("uint16") is not None else None
                elif attr_id == "0x0004":
                    # ProtocolDescriptorList – full extraction + RFCOMM channel
                    pdl = _extract_protocol_descriptors_xml(attr)
                    if pdl:
                        protocol_descriptors = pdl
                    for pseq in attr.iter("sequence"):
                        proto_uuid = pseq.findtext("uuid")
                        if proto_uuid and proto_uuid.upper().endswith("0003"):  # RFCOMM UUID
                            chan_elem = pseq.find("uint8") or pseq.find("uint16") or pseq.find("uint32")
                            if chan_elem is not None:
                                try:
                                    channel_val = int(chan_elem.text, 0)
                                except Exception:
                                    pass
                elif attr_id == "0x0009":  # Bluetooth Profile Descriptor List
                    # Extract profile UUIDs and versions
                    profile_list: List[Dict[str, Any]] = []
                    for pseq in attr.iter("sequence"):
                        profile_uuid = None
                        profile_ver = None
                        # Look for UUID element
                        uuid_elem = pseq.find("uuid")
                        if uuid_elem is not None:
                            uuid_text = uuid_elem.text or ""
                            # Handle both 16-bit (0xXXXX) and 128-bit UUIDs
                            if uuid_text.upper().endswith("0000-1000-8000-00805F9B34FB"):
                                # Extract 16-bit UUID from 128-bit format
                                profile_uuid = f"0x{uuid_text[4:8].upper()}"
                            elif len(uuid_text) == 36 and "-" in uuid_text:
                                # Full 128-bit UUID
                                profile_uuid = uuid_text.upper()
                            elif uuid_text.startswith("0x") or (len(uuid_text) == 4 and all(c in "0123456789abcdefABCDEF" for c in uuid_text)):
                                # 16-bit UUID
                                profile_uuid = f"0x{uuid_text.upper().replace('0X', '')}"
                        # Look for version (uint16 or uint8)
                        ver_elem = pseq.find("uint16") or pseq.find("uint8")
                        if ver_elem is not None:
                            try:
                                profile_ver = int(ver_elem.text, 0)
                            except (ValueError, AttributeError):
                                pass
                        if profile_uuid:
                            profile_list.append({
                                "uuid": profile_uuid,
                                "version": profile_ver
                            })
                    if profile_list:
                        profile_descriptors = profile_list
                elif attr_id == "0x0300":  # Service Version
                    ver_elem = attr.find("uint16") or attr.find("uint8")
                    if ver_elem is not None:
                        try:
                            service_version_val = int(ver_elem.text, 0)
                        except (ValueError, AttributeError):
                            pass
                elif attr_id == "0x0315":  # MAS Instance ID
                    inst_elem = attr.find("uint8") or attr.find("uint16")
                    if inst_elem is not None:
                        try:
                            mas_instance_id = int(inst_elem.text, 0)
                        except (ValueError, AttributeError):
                            pass
                elif attr_id == "0x0316":  # Supported Message Types
                    mt_elem = attr.find("uint8") or attr.find("uint16")
                    if mt_elem is not None:
                        try:
                            supported_message_types = int(mt_elem.text, 0)
                        except (ValueError, AttributeError):
                            pass
                elif attr_id == "0x0317":  # MapSupportedFeatures
                    sf_elem = attr.find("uint32") or attr.find("uint16")
                    if sf_elem is not None:
                        try:
                            supported_features_val = int(sf_elem.text, 0)
                        except (ValueError, AttributeError):
                            pass

            parsed.append({
                "name": name_val,
                "uuid": uuid_val,
                "channel": channel_val,
                "handle": handle_val,
                "profile_descriptors": profile_descriptors,
                "protocol_descriptors": protocol_descriptors,
                "service_version": service_version_val,
                "description": description_val,
                "mas_instance_id": mas_instance_id,
                "supported_message_types": supported_message_types,
                "supported_features": supported_features_val,
                "source": "dbus",
                "raw": xml_text.strip(),
            })

        if parsed:
            print_and_log(
                f"[classic_sdp] D-Bus GetServiceRecords successful – {len(parsed)} record(s)",
                LOG__DEBUG,
            )
            return parsed

        print_and_log("[classic_sdp] D-Bus GetServiceRecords returned no parseable records", LOG__DEBUG)
        return []

    except Exception as exc:  # noqa: BLE001 – log & fallback
        print_and_log(f"[classic_sdp] D-Bus SDP path raised: {exc}", LOG__DEBUG)
        return []


# ---------------------------------------------------------------------------
# svc_map builder (bc-53)
# ---------------------------------------------------------------------------


def build_svc_map(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build a collision-safe service-map from raw SDP records.

    Duplicate keys (e.g. two *Voice Gateway* entries from different
    handles) are disambiguated by appending the SDP handle.
    """
    svc_map: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        key = rec.get("name") or rec.get("uuid") or f"handle_{rec.get('handle', 'unknown')}"
        if key in svc_map:
            h = rec.get("handle")
            key = f"{key} (0x{h:04x})" if h is not None else f"{key} ({len(svc_map)})"
        svc_map[key] = {
            "uuid": rec.get("uuid"),
            "name": rec.get("name"),
            "channel": rec.get("channel"),
            "handle": rec.get("handle"),
            "service_version": rec.get("service_version"),
            "description": rec.get("description"),
            "profile_descriptors": rec.get("profile_descriptors"),
            "protocol_descriptors": rec.get("protocol_descriptors"),
            "mas_instance_id": rec.get("mas_instance_id"),
            "supported_message_types": rec.get("supported_message_types"),
            "supported_features": rec.get("supported_features"),
            "source": rec.get("source"),
        }
    return svc_map


def format_protocol_descriptors(pdl: Optional[List[Dict[str, Any]]]) -> str:
    """Render a Protocol Descriptor List into a compact one-line summary.

    Example outputs: ``L2CAP PSM 25, AVDTP v0x0103`` or ``L2CAP, RFCOMM ch 4``.
    Returns an empty string when *pdl* is empty or ``None``.
    """
    if not pdl:
        return ""
    parts: List[str] = []
    for entry in pdl:
        label = entry.get("name") or entry.get("uuid") or "?"
        params = entry.get("params") or {}
        if "psm" in params:
            label += f" PSM {params['psm']}"
        elif "channel" in params:
            label += f" ch {params['channel']}"
        elif "version" in params:
            label += f" v0x{params['version']:04X}"
        parts.append(label)
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SDPTOOL_PATH: Optional[str] = shutil.which("sdptool")


def _ensure_sdptool() -> str:
    """Return path to *sdptool* or raise ``NotSupportedError`` if not found."""
    if _SDPTOOL_PATH is None:
        raise NotSupportedError("SDP via sdptool ('sdptool' not in PATH – install bluez-utils)")
    return _SDPTOOL_PATH


def discover_service_channel(
    mac_address: str,
    uuid_short: str,
    timeout: int = 15,
) -> Optional[int]:
    """Run ``sdptool search --bdaddr <MAC> <UUID>`` to find the RFCOMM channel.

    Targeted single-service lookup — more reliable than full ``browse`` on
    devices whose SDP records confuse the bulk parser (e.g. SCH-U365).

    Returns the RFCOMM channel number, or ``None`` if not found.
    """
    mac_address = mac_address.strip().upper()
    uuid_short = uuid_short.strip().upper().replace("0X", "0x")

    try:
        path = _ensure_sdptool()
    except (RuntimeError, NotSupportedError):
        return None

    try:
        proc = subprocess.run(
            [path, "search", "--bdaddr", mac_address, uuid_short],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        print_and_log(
            f"[classic_sdp] sdptool search {uuid_short} timed out", LOG__DEBUG,
        )
        return None

    if proc.returncode != 0 or not proc.stdout.strip():
        return None

    chan_match = _RFCOMM_RE.search(proc.stdout)
    if chan_match:
        try:
            val = chan_match.group(1)
            return int(val, 16 if val.startswith("0x") else 10)
        except (ValueError, AttributeError):
            pass
    return None


_SVC_START_RE = re.compile(r"^Service Name:\s*(.*)$", re.MULTILINE)
_UUID128_RE = re.compile(r"UUID.*?([0-9a-fA-F\-]{36})")  # 128-bit
# First 16-bit UUID inside "(0xXXXX)" capture group
_UUID16_RE = re.compile(r"\(0x([0-9A-Fa-f]{4})\)")
# Matches either "Channel: 16" or "Channel/Port (Integer) : 0x10"
_RFCOMM_RE = re.compile(r"Channel(?:/Port)?[^:]*:\s*(0x[0-9A-Fa-f]+|\d+)")
# Profile Descriptor List - matches "Version: X" or "Version (Integer): X" or "Version: 0xXX"
_PROFILE_VERSION_RE = re.compile(r"Version(?:.*?)?:\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE)
# Service Version - matches "Service Version: X" or similar
_SERVICE_VERSION_RE = re.compile(r"Service\s+Version(?:.*?)?:\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE)
# Service Description
_SERVICE_DESC_RE = re.compile(r"Service\s+Description:\s*(.*)$", re.MULTILINE | re.IGNORECASE)
# Service Record Handle — sdptool prints "Service RecHandle:" (no space), so
# the separator between "Rec" and "Handle" must be optional whitespace (\s*).
_HANDLE_RE = re.compile(r"Service\s+Rec(?:ord)?\s*Handle(?:.*?)?:\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE)
# Protocol Descriptor List entry: "L2CAP" (0x0100)  or  "RFCOMM" (0x0003)
_PROTO_ENTRY_RE = re.compile(
    r'"([^"]+)"\s*\(0x([0-9A-Fa-f]{4})\)', re.MULTILINE
)
# Trailing parameter value that follows a protocol entry in the text output,
# e.g. "PSM: 1", "Channel: 4", "Version: 0x0100", "uint16: 0x0103".
_PROTO_PARAM_RE = re.compile(
    r"(?:PSM|Channel|Version|uint8|uint16|uint32)\s*:\s*(0x[0-9A-Fa-f]+|\d+)",
    re.IGNORECASE,
)
# Protocol name → the parameter key associated with its trailing value.
_PROTO_PARAM_KEYS = {
    "L2CAP": "psm",
    "RFCOMM": "channel",
    "BNEP": "version",
    "AVDTP": "version",
    "AVCTP": "version",
}
# Isolate the indented body of the "Protocol Descriptor List:" attribute so that
# entries from "Service Class ID List:" / "Profile Descriptor List:" are not
# mis-attributed as protocol descriptors.  The body ends at the next column-0
# header line (attributes are column-0, their contents indented).
_PROTO_SECTION_RE = re.compile(
    r"^Protocol Descriptor List:[ \t]*\n(.*?)(?=^\S|\Z)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)


def _parse_records(raw_output: str) -> List[Dict[str, Any]]:
    """Extract service name, UUID, RFCOMM channel, and additional attributes from *sdptool* text."""
    blocks = raw_output.split("\n\n")
    results: List[Dict[str, Any]] = []
    for block in blocks:
        if not block.strip():
            continue
        name_match = _SVC_START_RE.search(block)
        # Prefer 128-bit UUID if present, else fall back to first 16-bit code
        uuid_match = _UUID128_RE.search(block)
        uuid_value: Optional[str] = None
        if uuid_match:
            uuid_value = uuid_match.group(1).upper()
        else:
            uuid16 = _UUID16_RE.search(block)
            if uuid16:
                uuid_value = f"0x{uuid16.group(1).upper()}"

        channel_match = _RFCOMM_RE.search(block)
        
        # Extract additional attributes
        handle_match = _HANDLE_RE.search(block)
        handle_val: Optional[int] = None
        if handle_match:
            try:
                handle_val = int(handle_match.group(1), 16 if handle_match.group(1).startswith("0x") else 10)
            except (ValueError, AttributeError):
                pass
        
        # Extract profile descriptors (may appear multiple times in block)
        profile_descriptors: Optional[List[Dict[str, Any]]] = None
        profile_versions = _PROFILE_VERSION_RE.findall(block)
        if profile_versions and uuid_value:
            # If we found profile versions and have a UUID, create profile descriptors
            profile_list: List[Dict[str, Any]] = []
            for ver_match in profile_versions:
                ver_str = ver_match if isinstance(ver_match, str) else (ver_match[0] if ver_match else None)
                if ver_str:
                    try:
                        ver_int = int(ver_str, 16 if ver_str.startswith("0x") else 10)
                        profile_list.append({
                            "uuid": uuid_value,
                            "version": ver_int
                        })
                    except (ValueError, AttributeError):
                        pass
            if profile_list:
                profile_descriptors = profile_list
        
        # Extract service version
        service_version_val: Optional[int] = None
        svc_ver_match = _SERVICE_VERSION_RE.search(block)
        if svc_ver_match:
            try:
                service_version_val = int(svc_ver_match.group(1), 16 if svc_ver_match.group(1).startswith("0x") else 10)
            except (ValueError, AttributeError):
                pass
        
        # Extract service description
        desc_match = _SERVICE_DESC_RE.search(block)
        description_val: Optional[str] = desc_match.group(1).strip() if desc_match else None

        # Extract protocol descriptor entries from the "Protocol Descriptor List:"
        # section only, associating the trailing numeric parameter
        # (PSM / Channel / Version) with each entry by scanning the text between
        # consecutive protocol lines.
        protocol_descriptors: Optional[List[Dict[str, Any]]] = None
        proto_section_match = _PROTO_SECTION_RE.search(block)
        proto_section = proto_section_match.group(1) if proto_section_match else ""
        proto_iter = list(_PROTO_ENTRY_RE.finditer(proto_section))
        if proto_iter:
            plist: List[Dict[str, Any]] = []
            for i, m in enumerate(proto_iter):
                proto_name = m.group(1)
                entry: Dict[str, Any] = {
                    "uuid": f"0x{m.group(2).upper()}",
                    "name": proto_name,
                }
                param_key = _PROTO_PARAM_KEYS.get(proto_name.upper())
                if param_key:
                    seg_end = proto_iter[i + 1].start() if i + 1 < len(proto_iter) else len(proto_section)
                    param_match = _PROTO_PARAM_RE.search(proto_section[m.end():seg_end])
                    if param_match:
                        val_str = param_match.group(1)
                        try:
                            entry["params"] = {
                                param_key: int(val_str, 16 if val_str.lower().startswith("0x") else 10)
                            }
                        except (ValueError, AttributeError):
                            pass
                plist.append(entry)
            if plist:
                protocol_descriptors = plist

        record: Dict[str, Any] = {
            "name": name_match.group(1).strip() if name_match else None,
            "uuid": uuid_value,
            "channel": int(channel_match.group(1), 16 if channel_match and channel_match.group(1).startswith("0x") else 10) if channel_match else None,
            "handle": handle_val,
            "profile_descriptors": profile_descriptors,
            "protocol_descriptors": protocol_descriptors,
            "service_version": service_version_val,
            "description": description_val,
            "mas_instance_id": None,
            "supported_message_types": None,
            "supported_features": None,
            "attribute_labels": None,
            "raw": block.strip(),
        }
        # Skip blocks that yielded no meaningful identifier (e.g. stray sdptool
        # status lines such as "Failed to connect to SDP server ...") to avoid
        # emitting empty "handle_None" records.
        if (
            not record["name"]
            and not record["uuid"]
            and record["channel"] is None
            and record["handle"] is None
        ):
            continue
        results.append(record)
    return results


# ---------------------------------------------------------------------------
# XML parser for ``sdptool browse --xml`` output (bc-53)
# ---------------------------------------------------------------------------

# Matches ``<?xml ...?>`` processing instructions that delimit records in
# concatenated sdptool XML output.
_XML_PI_RE = re.compile(r"<\?xml[^?]*\?>")

# Matches a single ``<record>...</record>`` element. ``sdptool`` frequently
# appends non-XML status lines (e.g. "Browsing AA:BB:... ", "Service Search
# failed: Invalid argument") *after* the closing ``</record>`` within the same
# PI-delimited fragment; clipping to this span lets us ignore that trailing
# noise instead of discarding the whole record on a parse error.
_XML_RECORD_RE = re.compile(r"<record>.*?</record>", re.DOTALL)


def _xml_elem_value(elem) -> Optional[str]:
    """Extract the text payload from an XML element.

    ``sdptool browse --xml`` encodes values as attributes
    (``<text value="SMS/MMS" />``), while the BlueZ D-Bus path uses text
    content (``<text>SMS/MMS</text>``).  This helper normalises both
    formats.
    """
    if elem is None:
        return None
    return (elem.text or elem.get("value") or "").strip() or None


def _xml_findtext(parent, tag: str) -> Optional[str]:
    """Like ``parent.findtext(tag)`` but also checks the ``value`` attribute."""
    elem = parent.find(tag)
    return _xml_elem_value(elem)


def _extract_protocol_descriptors_xml(attr_elem, *, use_text_content: bool = True) -> List[Dict[str, Any]]:
    """Parse a ProtocolDescriptorList (attr 0x0004) XML element.

    Returns a list of protocol entries, each with ``uuid`` and optional
    ``params`` dict containing protocol-specific values (e.g. ``psm``,
    ``channel``, ``version``).

    Parameters
    ----------
    attr_elem
        The ``<attribute id="0x0004">`` XML element.
    use_text_content : bool
        If True, reads values via ``elem.text``.  If False, uses the
        ``value`` attribute (sdptool browse --xml format).  The helper
        :func:`_xml_elem_value` is used internally to handle both.
    """
    _KNOWN_PROTOS = {
        "0100": ("L2CAP", "psm"),
        "0003": ("RFCOMM", "channel"),
        "0008": ("OBEX", None),
        "0017": ("AVCTP", "version"),
        "0019": ("AVDTP", "version"),
        "001b": ("BNEP", "version"),
        "000f": ("BNEP", "version"),
        "0004": ("TCP", "port"),
        "0002": ("UDP", "port"),
        "0001": ("SDP", None),
    }
    protos: List[Dict[str, Any]] = []
    for seq in attr_elem.iter("sequence"):
        uuid_elem = seq.find("uuid")
        if uuid_elem is None:
            continue
        raw_uuid = (_xml_elem_value(uuid_elem) or "").upper().replace("0X", "").replace("0x", "")
        if not raw_uuid:
            continue
        # Normalise: take last 4 hex chars for 16-bit SIG UUIDs
        short = raw_uuid[-4:] if len(raw_uuid) <= 4 else raw_uuid
        if raw_uuid.endswith("0000-1000-8000-00805F9B34FB"):
            short = raw_uuid[4:8] if len(raw_uuid) > 8 else raw_uuid[:4]
        proto_name, param_key = _KNOWN_PROTOS.get(short.lower(), (None, None))
        entry: Dict[str, Any] = {"uuid": f"0x{short}"}
        if proto_name:
            entry["name"] = proto_name
        # Extract first numeric param after the UUID element (back-compat scalar).
        # Explicit ``is None`` chain: ElementTree.Element truth-value is deprecated
        # (a childless element is falsy today and will raise in future versions).
        param_elem = seq.find("uint8")
        if param_elem is None:
            param_elem = seq.find("uint16")
        if param_elem is None:
            param_elem = seq.find("uint32")
        param_val_str = _xml_elem_value(param_elem)
        if param_val_str and param_key:
            try:
                entry["params"] = {param_key: int(param_val_str, 0)}
            except (ValueError, AttributeError):
                pass
        # SIG-named positional parameters (attr 0x0004): every numeric element after
        # the protocol UUID is a positional parameter (1-based). Names come from
        # SDP_PROTOCOL_PARAMETERS; unnamed params still surface with value + index.
        # Purely additive — never disturbs ``uuid``/``name``/``params``.
        param_names = _SDP_PROTOCOL_PARAMETERS.get(proto_name or "", {})
        positional: List[Dict[str, Any]] = []
        for child in list(seq):
            tag = child.tag.lower()
            if tag not in ("uint8", "uint16", "uint32"):
                continue
            raw = _xml_elem_value(child)
            val: Optional[int] = None
            if raw is not None:
                try:
                    val = int(raw, 0)
                except (ValueError, AttributeError):
                    val = None
            idx = len(positional) + 1
            positional.append({"index": idx, "name": param_names.get(idx), "value": val})
        if positional:
            entry["parameters"] = positional
        protos.append(entry)
    return protos


def _decode_iso639(code: int) -> str:
    """Decode a LanguageBaseAttributeIDList language identifier (2 packed ASCII
    letters, e.g. 0x656E -> "en") to a lowercase tag, or a hex fallback."""
    hi, lo = (code >> 8) & 0xFF, code & 0xFF
    if (0x41 <= hi <= 0x7A) and (0x41 <= lo <= 0x7A):
        return (chr(hi) + chr(lo)).lower()
    return f"0x{code:04x}"


def _extract_language_bases(root) -> List[tuple]:
    """Return ``[(base_offset:int, lang_tag:str), ...]`` from LanguageBaseAttributeIDList.

    Attr 0x0006 is a sequence of uint16 triplets ``(code_ISO639, encoding,
    base_offset)`` (BlueZ ``sdp.c:sdp_get_lang_attr``). Order-independent; the
    primary base (0x0100) is included but callers typically skip it since the
    universal table already labels 0x0100-0x0102.
    """
    out: List[tuple] = []
    for attr in root.findall("attribute"):
        if attr.get("id", "").lower() != "0x0006":
            continue
        vals: List[int] = []
        for elem in attr.iter("uint16"):
            raw = _xml_elem_value(elem)
            if raw is None:
                continue
            try:
                vals.append(int(raw, 0))
            except (ValueError, AttributeError):
                continue
        for i in range(0, len(vals) - 2, 3):  # full triplets only
            code, _encoding, base = vals[i], vals[i + 1], vals[i + 2]
            out.append((base, _decode_iso639(code)))
        break
    return out


def _build_lang_string_labels(root) -> Dict[str, str]:
    """Labels for *secondary-language* string attributes (ServiceName/Description/
    ProviderName) at each non-primary language base, keyed ``"0xNNNN"``.

    Uses the SIG offsets (``SDP_STRING_ATTR_OFFSETS``) to know which offsets are
    string attributes and reuses the universal label wording (0x0100+offset) for
    consistency, appending the language tag, e.g. ``"Service Name (fr)"``.
    """
    labels: Dict[str, str] = {}
    if not _SDP_STRING_ATTR_OFFSETS:
        return labels
    for base, lang in _extract_language_bases(root):
        if base == _SDP_PRIMARY_LANG_BASE:
            continue  # primary strings already labelled by the universal table
        for off_key, sig_name in _SDP_STRING_ATTR_OFFSETS.items():
            try:
                off = int(off_key, 16)
            except (ValueError, TypeError):
                continue
            base_label = resolve_sdp_attr_id(_SDP_PRIMARY_LANG_BASE + off) or sig_name
            labels[f"0x{base + off:04x}"] = f"{base_label} ({lang})"
    return labels


def _parse_xml_record(xml_text: str) -> Dict[str, Any]:
    """Parse a single SDP record XML fragment into a record dict.

    Uses the same attribute-extraction logic as ``_discover_services_dbus``
    but operates on standalone XML produced by *sdptool*.

    Handles both ``value``-attribute format (``sdptool browse --xml``)
    and text-content format (BlueZ D-Bus ``GetServiceRecords``).
    """
    root = ET.fromstring(xml_text)

    name_val: Optional[str] = None
    uuid_val: Optional[str] = None
    channel_val: Optional[int] = None
    handle_val: Optional[int] = None
    profile_descriptors: Optional[List[Dict[str, Any]]] = None
    protocol_descriptors: Optional[List[Dict[str, Any]]] = None
    service_version_val: Optional[int] = None
    description_val: Optional[str] = None
    mas_instance_id: Optional[int] = None
    supported_message_types: Optional[int] = None
    supported_features_val: Optional[int] = None

    # SDP attribute-ID labels. Purely additive: every attribute ID present in the
    # record is labelled when resolvable, so IDs we don't otherwise parse are
    # surfaced instead of silently dropped. Never overwrites a parsed scalar field
    # or the raw block. The universal range (BlueZ lib/sdp.h) always resolves;
    # context-dependent IDs (>= 0x0200) resolve only via the record's Service Class
    # (SIG per-profile tables), so a numeric ID is never guessed. Secondary-language
    # string attributes (ServiceName/Description/ProviderName at a non-primary
    # LanguageBaseAttributeIDList base) are labelled from the SIG string offsets.
    # Both the service class and the language bases are pre-scanned here so
    # labelling does not depend on attribute ordering.
    attribute_labels: Dict[str, str] = {}
    service_class_for_labels: Optional[str] = None
    for _attr in root.findall("attribute"):
        if _attr.get("id", "").lower() == "0x0001":  # Service Class ID List
            for _uuid_elem in _attr.iter("uuid"):
                _raw = _xml_elem_value(_uuid_elem)
                if _raw:
                    service_class_for_labels = _raw  # resolver normalises the form
                    break
            break

    # Secondary-language string labels (via LanguageBaseAttributeIDList, attr 0x0006).
    # Pre-scanned so labelling is order-independent; additive only.
    lang_string_labels = _build_lang_string_labels(root)

    for attr in root.findall("attribute"):
        attr_id = attr.get("id", "").lower()

        label = resolve_sdp_attr_id(attr_id, service_class_for_labels) if attr_id else None
        if not label and attr_id:
            label = lang_string_labels.get(attr_id)
        if label:
            attribute_labels[attr_id] = label

        if attr_id == "0x0100":  # Service Name
            name_val = _xml_findtext(attr, "text")

        elif attr_id == "0x0101":  # Service Description
            description_val = _xml_findtext(attr, "text")

        elif attr_id == "0x0000":  # Service Record Handle
            for tag in ("uint32", "uint16", "uint8"):
                elem = attr.find(tag)
                val = _xml_elem_value(elem)
                if val:
                    try:
                        handle_val = int(val, 0)
                    except (ValueError, AttributeError):
                        pass
                    break

        elif attr_id == "0x0001":  # Service Class ID List
            for uuid_elem in attr.iter("uuid"):
                raw = _xml_elem_value(uuid_elem)
                if not raw:
                    continue
                up = raw.upper()
                if up.endswith("0000-1000-8000-00805F9B34FB"):
                    uuid_val = f"0x{up[4:8]}"
                elif len(raw) == 36 and "-" in raw:
                    uuid_val = up
                else:
                    uuid_val = f"0x{up.replace('0X', '')}"
                break  # first Service Class UUID

        elif attr_id == "0x0004":  # Protocol Descriptor List
            pdl = _extract_protocol_descriptors_xml(attr)
            if pdl:
                protocol_descriptors = pdl
            for seq in attr.iter("sequence"):
                proto_uuid_elem = seq.find("uuid")
                if proto_uuid_elem is None:
                    continue
                proto = (_xml_elem_value(proto_uuid_elem) or "").upper()
                if proto.endswith("0003"):  # RFCOMM UUID
                    chan_elem = seq.find("uint8") or seq.find("uint16")
                    chan_val = _xml_elem_value(chan_elem)
                    if chan_val:
                        try:
                            channel_val = int(chan_val, 0)
                        except (ValueError, AttributeError):
                            pass

        elif attr_id == "0x0009":  # Bluetooth Profile Descriptor List
            profile_list: List[Dict[str, Any]] = []
            for seq in attr.iter("sequence"):
                p_uuid_elem = seq.find("uuid")
                if p_uuid_elem is None:
                    continue
                raw_u = _xml_elem_value(p_uuid_elem)
                if not raw_u:
                    continue
                up_u = raw_u.upper()
                if up_u.endswith("0000-1000-8000-00805F9B34FB"):
                    p_uuid = f"0x{up_u[4:8]}"
                elif len(raw_u) == 36 and "-" in raw_u:
                    p_uuid = up_u
                else:
                    p_uuid = f"0x{up_u.replace('0X', '')}"
                p_ver: Optional[int] = None
                ver_elem = seq.find("uint16") or seq.find("uint8")
                ver_str = _xml_elem_value(ver_elem)
                if ver_str:
                    try:
                        p_ver = int(ver_str, 0)
                    except (ValueError, AttributeError):
                        pass
                profile_list.append({"uuid": p_uuid, "version": p_ver})
            if profile_list:
                profile_descriptors = profile_list

        elif attr_id == "0x0300":  # Service Version
            ver_elem = attr.find("uint16") or attr.find("uint8")
            ver_str = _xml_elem_value(ver_elem)
            if ver_str:
                try:
                    service_version_val = int(ver_str, 0)
                except (ValueError, AttributeError):
                    pass

        elif attr_id == "0x0315":  # MAS Instance ID
            inst_elem = attr.find("uint8") or attr.find("uint16")
            inst_str = _xml_elem_value(inst_elem)
            if inst_str:
                try:
                    mas_instance_id = int(inst_str, 0)
                except (ValueError, AttributeError):
                    pass

        elif attr_id == "0x0316":  # Supported Message Types
            mt_elem = attr.find("uint8") or attr.find("uint16")
            mt_str = _xml_elem_value(mt_elem)
            if mt_str:
                try:
                    supported_message_types = int(mt_str, 0)
                except (ValueError, AttributeError):
                    pass

        elif attr_id == "0x0317":  # MapSupportedFeatures
            sf_elem = attr.find("uint32") or attr.find("uint16")
            sf_str = _xml_elem_value(sf_elem)
            if sf_str:
                try:
                    supported_features_val = int(sf_str, 0)
                except (ValueError, AttributeError):
                    pass

    return {
        "name": name_val,
        "uuid": uuid_val,
        "channel": channel_val,
        "handle": handle_val,
        "profile_descriptors": profile_descriptors,
        "protocol_descriptors": protocol_descriptors,
        "service_version": service_version_val,
        "description": description_val,
        "mas_instance_id": mas_instance_id,
        "supported_message_types": supported_message_types,
        "supported_features": supported_features_val,
        "attribute_labels": attribute_labels or None,
        "raw": xml_text.strip(),
    }


def _parse_browse_xml(raw_output: str) -> List[Dict[str, Any]]:
    """Parse concatenated XML output from ``sdptool browse --xml``.

    *sdptool* emits one ``<?xml …?>`` + ``<record>…</record>`` fragment per
    SDP record, separated by whitespace.  We split on the PI boundary and
    parse each fragment individually.
    """
    fragments = _XML_PI_RE.split(raw_output)
    results: List[Dict[str, Any]] = []
    for frag in fragments:
        frag = frag.strip()
        if not frag or not frag.startswith("<"):
            continue
        # Clip to the <record>...</record> span(s) so trailing sdptool status
        # text (which makes the fragment malformed XML) does not sink the whole
        # record. Fall back to the raw fragment when no <record> is present, so
        # any other well-formed XML still parses exactly as before.
        for span in _XML_RECORD_RE.findall(frag) or [frag]:
            try:
                results.append(_parse_xml_record(span))
            except ET.ParseError:
                continue
    return results


# ---------------------------------------------------------------------------
# Source union + provenance (bc-source-union)
# ---------------------------------------------------------------------------

# Ordered sdptool sources and their argv (mac appended by the runner). The label
# is the provenance value stored on each record and in the DB ``source`` column.
_SDPTOOL_SOURCES = {
    "browse": ["browse"],
    "xml": ["browse", "--xml"],
    "records": ["records"],
}

# Scalar fields unioned/conflict-checked when merging multi-source records.
_MERGE_SCALAR_FIELDS = (
    "name", "uuid", "channel", "handle", "service_version", "description",
    "mas_instance_id", "supported_message_types", "supported_features",
)
# List-valued fields: filled from the first source that provides a non-empty list.
_MERGE_LIST_FIELDS = ("profile_descriptors", "protocol_descriptors")


def _run_sdptool_source(
    path: str, source: str, mac_address: str, timeout: int
) -> Optional[List[Dict[str, Any]]]:
    """Run a single *sdptool* source and return its parsed, source-tagged records.

    Returns ``None`` on process failure/timeout (so callers can distinguish "not
    run/failed" from "ran, zero records"). Mirrors the per-source timeout used by
    the historical ``auto`` chain (``browse``/``records`` get ``timeout*2``, the
    structured ``xml`` path gets ``timeout``).
    """
    argv = [path, *_SDPTOOL_SOURCES[source], mac_address]
    proc_timeout = timeout if source == "xml" else timeout * 2
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=proc_timeout, check=False
        )
    except subprocess.TimeoutExpired:
        print_and_log(f"[classic_sdp] sdptool {source} timed out", LOG__DEBUG)
        return None
    if proc.returncode != 0:
        print_and_log(
            f"[classic_sdp] sdptool {source} failed: "
            f"{(proc.stderr.strip() or proc.stdout.strip())[:200]}",
            LOG__DEBUG,
        )
        return None
    parsed = _parse_browse_xml(proc.stdout) if source == "xml" else _parse_records(proc.stdout)
    for rec in parsed:
        rec["source"] = source
    return parsed


def _record_key(rec: Dict[str, Any]):
    """Merge identity: handle → uuid → name (matches build_svc_map precedence)."""
    if rec.get("handle") is not None:
        return ("handle", rec["handle"])
    if rec.get("uuid"):
        return ("uuid", rec["uuid"])
    if rec.get("name"):
        return ("name", rec["name"])
    return ("id", id(rec))


def _union_sdp_records(
    source_lists: List[tuple],
) -> List[Dict[str, Any]]:
    """Union records from multiple sources with per-field provenance.

    *source_lists* is an ordered list of ``(source_label, [records])`` in
    priority order (first source wins the primary value of each scalar field).
    Later sources fill fields the earlier ones left ``None``. When two sources
    supply *different* non-``None`` values for a scalar field, both are recorded
    under ``source_conflicts[field] = {source: value}`` (the first writer's
    source included) — this is the evidence the analyzer turns into a
    ``source_discrepancy`` anomaly. All raw text is preserved: each merged record
    concatenates every contributing source's raw block under a ``# source:``
    header, so nothing observed is dropped.
    """
    merged: Dict[Any, Dict[str, Any]] = {}
    order: List[Any] = []
    for label, recs in source_lists:
        for rec in recs or []:
            key = _record_key(rec)
            if key not in merged:
                m: Dict[str, Any] = {f: rec.get(f) for f in _MERGE_SCALAR_FIELDS}
                for f in _MERGE_LIST_FIELDS:
                    m[f] = rec.get(f)
                m["attribute_labels"] = dict(rec.get("attribute_labels") or {})
                m["sources"] = [label]
                m["source_conflicts"] = {}
                m["_field_src"] = {
                    f: label for f in _MERGE_SCALAR_FIELDS if rec.get(f) is not None
                }
                m["_raw_by_source"] = {label: rec.get("raw") or ""}
                merged[key] = m
                order.append(key)
                continue
            m = merged[key]
            if label not in m["sources"]:
                m["sources"].append(label)
            for f in _MERGE_SCALAR_FIELDS:
                val = rec.get(f)
                if val is None:
                    continue
                cur = m.get(f)
                if cur is None:
                    m[f] = val
                    m["_field_src"][f] = label
                elif cur != val:
                    conf = m["source_conflicts"].setdefault(f, {})
                    conf.setdefault(m["_field_src"].get(f, "?"), cur)
                    conf[label] = val
            for f in _MERGE_LIST_FIELDS:
                if not m.get(f) and rec.get(f):
                    m[f] = rec.get(f)
            if rec.get("attribute_labels"):
                m["attribute_labels"].update(rec["attribute_labels"])
            m["_raw_by_source"][label] = rec.get("raw") or ""

    out: List[Dict[str, Any]] = []
    for key in order:
        m = merged[key]
        m.pop("_field_src", None)
        raw_by_source = m.pop("_raw_by_source", {})
        m["attribute_labels"] = m.get("attribute_labels") or None
        m["source"] = "+".join(m["sources"])
        m["raw"] = "\n\n".join(
            f"# source: {s}\n{r}" for s, r in raw_by_source.items() if r
        )
        out.append(m)
    return out


def _discover_sdp_merged(mac_address: str, timeout: int) -> List[Dict[str, Any]]:
    """Query every available source and union the records (source='merge'/'all')."""
    source_lists: List[tuple] = []
    dbus_res = _discover_services_dbus(mac_address)  # already tagged source="dbus"
    if dbus_res:
        source_lists.append(("dbus", dbus_res))
    try:
        path = _ensure_sdptool()
    except (RuntimeError, NotSupportedError):
        path = None
    if path is not None:
        for src in _SDPTOOL_SOURCES:  # browse, xml, records (dict is ordered)
            recs = _run_sdptool_source(path, src, mac_address, timeout)
            if recs:
                source_lists.append((src, recs))

    if not source_lists:
        raise BLEEPError(
            "sdptool failed: no SDP records from any source (D-Bus + sdptool)",
            RESULT_ERR_NOT_FOUND,
        )
    merged = _union_sdp_records(source_lists)
    _store_sdp_records(mac_address, merged)
    return merged


# ---------------------------------------------------------------------------
# Connectionless SDP Query with Reachability Check
# ---------------------------------------------------------------------------

def discover_services_sdp_connectionless(
    mac_address: str,
    timeout: int = 30,
    l2ping_count: int = 3,
    l2ping_timeout: int = 13,
    source: str = "auto",
) -> List[Dict[str, Any]]:
    """Perform SDP discovery with l2ping reachability check first (connectionless).
    
    This function verifies device reachability using l2ping before attempting
    SDP queries. This provides faster failure detection and better error messages
    when devices are unreachable.
    
    Parameters
    ----------
    mac_address : str
        Target Bluetooth classic device address ("AA:BB:CC:DD:EE:FF").
    timeout : int, optional
        Seconds to wait for the *sdptool* process, default 30.
    l2ping_count : int, optional
        Number of l2ping echo requests to send, default 3.
    l2ping_timeout : int, optional
        Seconds to wait for l2ping to complete, default 13.
    
    Returns
    -------
    list of dict
        Parsed records as described in the module docstring.
    
    Raises
    ------
    RuntimeError
        If device is unreachable (l2ping fails) or if *sdptool* is missing/exits with error.
    """
    mac_address = mac_address.strip().upper()
    
    # Check reachability first using l2ping
    if classic_l2ping is None:
        print_and_log(
            "[classic_sdp] classic_l2ping not available, skipping reachability check",
            LOG__DEBUG
        )
    else:
        print_and_log(
            f"[classic_sdp] Checking reachability for {mac_address} via l2ping...",
            LOG__DEBUG
        )
        rtt, error = classic_l2ping(mac_address, count=l2ping_count, timeout=l2ping_timeout)
        
        if rtt is None:
            # Device is unreachable
            error_msg = error or "Device unreachable"
            raise ConnectionError(
                mac_address,
                f"not reachable via L2CAP: {error_msg}. SDP query skipped. "
                "Ensure device is powered on and in range.",
            )
        
        print_and_log(
            f"[classic_sdp] Device reachable (avg RTT: {rtt:.2f}ms), proceeding with SDP query",
            LOG__DEBUG
        )
    
    # Device is reachable, proceed with normal SDP discovery (without connectionless to avoid recursion)
    return discover_services_sdp(mac_address, timeout=timeout, connectionless=False, source=source)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_services_sdp(
    mac_address: str,
    timeout: int = 30,
    connectionless: bool = False,
    l2ping_count: int = 3,
    l2ping_timeout: int = 13,
    source: str = "auto",
) -> List[Dict[str, Any]]:
    """Run *sdptool records* against *mac_address* and parse the results.

    Parameters
    ----------
    mac_address : str
        Target Bluetooth classic device address ("AA:BB:CC:DD:EE:FF").
    timeout : int, optional
        Seconds to wait for the *sdptool* process, default 30.
    connectionless : bool, optional
        If True, verify device reachability via l2ping before SDP query.
        Default False (backward compatible).
    l2ping_count : int, optional
        Number of l2ping echo requests when connectionless=True, default 3.
    l2ping_timeout : int, optional
        Seconds to wait for l2ping when connectionless=True, default 13.
    source : str, optional
        Discovery source selection (default ``"auto"``). See the module
        docstring: ``"auto"`` keeps the historical first-success-wins chain;
        ``"dbus" | "browse" | "xml" | "records"`` force a single source;
        ``"merge"`` (alias ``"all"``) unions every source with provenance.

    Returns
    -------
    list of dict
        Parsed records as described in the module docstring.

    Raises
    ------
    bleep.core.errors.ConnectionError
        If connectionless=True and the device is unreachable.
    bleep.core.errors.NotSupportedError
        If *sdptool* is missing from PATH.
    bleep.core.errors.BLEEPError
        If SDP discovery yields no records / *sdptool* exits with error.
    """
    
    # If connectionless mode requested, use dedicated function
    if connectionless:
        return discover_services_sdp_connectionless(
            mac_address,
            timeout=timeout,
            l2ping_count=l2ping_count,
            l2ping_timeout=l2ping_timeout,
            source=source,
        )

    source = (source or "auto").lower()

    # ------------------------------------------------------------------
    # Explicit source selection (bc-source-union). "auto" falls through to
    # the historical chain below (unchanged), preserving default behaviour.
    # ------------------------------------------------------------------
    if source in ("merge", "all"):
        return _discover_sdp_merged(mac_address, timeout)
    if source == "dbus":
        dbus_only = _discover_services_dbus(mac_address)
        if not dbus_only:
            raise BLEEPError(
                "sdptool failed: D-Bus GetServiceRecords returned no records",
                RESULT_ERR_NOT_FOUND,
            )
        _store_sdp_records(mac_address, dbus_only)
        return dbus_only
    if source in _SDPTOOL_SOURCES:
        single = _run_sdptool_source(_ensure_sdptool(), source, mac_address, timeout)
        if not single:
            raise BLEEPError(
                f"sdptool failed: no records from source '{source}'",
                RESULT_ERR_NOT_FOUND,
            )
        _store_sdp_records(mac_address, single)
        return single
    if source != "auto":
        raise ValueError(f"Unknown SDP source '{source}'")

    # ------------------------------------------------------------------
    # 1. Fast-path via BlueZ Device1.GetServiceRecords (bc-15)
    # ------------------------------------------------------------------

    dbus_res = _discover_services_dbus(mac_address)
    if dbus_res:
        # Store SDP records in database if available
        _store_sdp_records(mac_address, dbus_res)
        return dbus_res
    
    # Track successful parsed records for storage
    successful_records: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # 2. Fallback to external sdptool binary
    # ------------------------------------------------------------------

    path = _ensure_sdptool()

    # Strategy: plain ``browse`` follows the public browse group and is the only
    # single source that reliably returns every advertised record *with* its
    # RFCOMM channel and L2CAP PSM (verified against honeypot targets whose extra
    # browse-group services are dropped/attribute-stripped by ``browse --xml``
    # and truncated by ``records``).  Its human-readable layout is exactly what
    # ``_parse_records()`` targets.  ``browse --xml`` (structured params) and
    # ``records`` (handle-range scan) remain as ordered fallbacks.
    _CMD_BROWSE = "browse"
    _CMD_XML = "browse_xml"
    _CMD_REC = "records"
    cmds_to_try = [
        (_CMD_BROWSE, [path, "browse", mac_address]),
        (_CMD_XML, [path, "browse", "--xml", mac_address]),
        (_CMD_REC, [path, "records", mac_address]),
    ]

    last_error: Optional[str] = None
    for idx, (tag, cmd) in enumerate(cmds_to_try, start=1):
        print_and_log(f"[*] Running '{' '.join(cmd)}' (attempt {idx})", LOG__DEBUG)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout if tag == _CMD_XML else timeout * 2,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = f"sdptool {tag} timed out"
            continue

        if proc.returncode != 0:
            last_error = proc.stderr.strip() or proc.stdout.strip()
            continue

        if LOG__DEBUG:
            preview = proc.stdout.strip()[:2000] if tag == _CMD_XML else proc.stdout.strip()
            print_and_log(f"[classic_sdp] ---- raw sdptool {tag} output ----", LOG__DEBUG)
            print_and_log(preview or "<empty>", LOG__DEBUG)
            print_and_log(f"[classic_sdp] ---- end raw {tag} output ----", LOG__DEBUG)

        parsed = _parse_browse_xml(proc.stdout) if tag == _CMD_XML else _parse_records(proc.stdout)
        # Provenance label (bc-source-union): normalise the internal command tag
        # to the public source label stored on each record and in the DB.
        _src_label = "xml" if tag == _CMD_XML else ("records" if tag == _CMD_REC else "browse")
        for _rec in parsed:
            _rec["source"] = _src_label

        if LOG__DEBUG:
            print_and_log(f"[classic_sdp] Parsed {len(parsed)} record(s) via {tag}", LOG__DEBUG)
            for idx_rec, rec in enumerate(parsed, start=1):
                debug_info = f"  [{idx_rec}] name={rec.get('name')} uuid={rec.get('uuid')} channel={rec.get('channel')}"
                if rec.get('handle') is not None:
                    debug_info += f" handle=0x{rec['handle']:04x}"
                if rec.get('profile_descriptors'):
                    debug_info += f" profiles={len(rec['profile_descriptors'])}"
                if rec.get('service_version') is not None:
                    debug_info += f" svc_ver=0x{rec['service_version']:04x}"
                print_and_log(debug_info, LOG__DEBUG)

        if parsed:
            if any(rec.get("channel") is not None for rec in parsed):
                successful_records = parsed
                break
            successful_records = parsed
            if idx == len(cmds_to_try):
                break
            last_error = f"No RFCOMM channels in {tag} output"
            continue
        last_error = f"No services found via {tag}"

    if successful_records:
        _store_sdp_records(mac_address, successful_records)
        return successful_records

    raise BLEEPError(f"sdptool failed: {last_error}", RESULT_ERR)


def _store_sdp_records(mac_address: str, records: List[Dict[str, Any]]) -> None:
    """Store SDP records in the database if available.
    
    Parameters
    ----------
    mac_address : str
        Device MAC address
    records : List[Dict[str, Any]]
        List of SDP records to store
    """
    try:
        from bleep.core import observations as _obs
        if _obs:
            for record in records:
                try:
                    _obs.upsert_sdp_record(mac_address, record)
                except Exception as e:
                    print_and_log(
                        f"[classic_sdp] Failed to store SDP record: {e}",
                        LOG__DEBUG
                    )
    except ImportError:
        # Database module not available - graceful degradation
        pass
    except Exception:
        # Any other error - don't fail SDP discovery
        pass 