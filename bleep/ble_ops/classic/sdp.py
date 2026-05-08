from __future__ import annotations
"""bleep.ble_ops.classic_sdp – SDP service discovery for Bluetooth Classic.

This helper intentionally avoids third-party Bluetooth libraries.  It relies on
BlueZ’s *sdptool* binary to obtain the full SDP record (required for RFCOMM
channel extraction) because BlueZ’s D-Bus API only exposes the service UUID
list, not the protocol descriptor details.

Discovery chain (bc-53):
    1. ``Device1.GetServiceRecords`` (D-Bus, fast, BlueZ >= 5.66)
    2. ``sdptool browse --xml <addr>`` (structured XML, reliable parsing)
    3. ``sdptool records <addr>`` (human-readable, regex-parsed fallback)

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
     "raw": str}  # full block text for reference

The function raises *RuntimeError* if *sdptool* is missing or returns an error.
"""

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from typing import List, Dict, Any, Optional

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
import dbus

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
                    uuid_val = f"0x{attr.findtext('uint16').lower()}" if attr.find("uint16") is not None else None
                elif attr_id == "0x0004":
                    # ProtocolDescriptorList – full extraction + RFCOMM channel
                    pdl = _extract_protocol_descriptors_xml(attr)
                    if pdl:
                        protocol_descriptors = pdl
                    for pseq in attr.iter("sequence"):
                        proto_uuid = pseq.findtext("uuid")
                        if proto_uuid and proto_uuid.lower().endswith("0003"):  # RFCOMM UUID
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
                            if uuid_text.lower().endswith("0000-1000-8000-00805f9b34fb"):
                                # Extract 16-bit UUID from 128-bit format
                                profile_uuid = f"0x{uuid_text[4:8].lower()}"
                            elif len(uuid_text) == 36 and "-" in uuid_text:
                                # Full 128-bit UUID
                                profile_uuid = uuid_text.lower()
                            elif uuid_text.startswith("0x") or (len(uuid_text) == 4 and all(c in "0123456789abcdefABCDEF" for c in uuid_text)):
                                # 16-bit UUID
                                profile_uuid = f"0x{uuid_text.lower().replace('0x', '')}"
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
            "mas_instance_id": rec.get("mas_instance_id"),
            "supported_message_types": rec.get("supported_message_types"),
            "supported_features": rec.get("supported_features"),
        }
    return svc_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SDPTOOL_PATH: Optional[str] = shutil.which("sdptool")


def _ensure_sdptool() -> str:
    """Return path to *sdptool* or raise RuntimeError if not found."""
    if _SDPTOOL_PATH is None:
        raise RuntimeError("'sdptool' binary not found in PATH – install bluez-utils")
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
    except RuntimeError:
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
# Service Record Handle
_HANDLE_RE = re.compile(r"Service\s+Rec(?:ord)?\s+Handle(?:.*?)?:\s*(0x[0-9A-Fa-f]+|\d+)", re.IGNORECASE)
# Protocol Descriptor List entry: "L2CAP" (0x0100)  or  "RFCOMM" (0x0003)
_PROTO_ENTRY_RE = re.compile(
    r'"([^"]+)"\s*\(0x([0-9A-Fa-f]{4})\)', re.MULTILINE
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
            uuid_value = uuid_match.group(1).lower()
        else:
            uuid16 = _UUID16_RE.search(block)
            if uuid16:
                uuid_value = f"0x{uuid16.group(1).lower()}"

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

        # Extract protocol descriptor entries from text output
        protocol_descriptors: Optional[List[Dict[str, Any]]] = None
        proto_matches = _PROTO_ENTRY_RE.findall(block)
        if proto_matches:
            plist: List[Dict[str, Any]] = []
            for proto_name, proto_hex in proto_matches:
                entry: Dict[str, Any] = {
                    "uuid": f"0x{proto_hex.lower()}",
                    "name": proto_name,
                }
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
            "raw": block.strip(),
        }
        results.append(record)
    return results


# ---------------------------------------------------------------------------
# XML parser for ``sdptool browse --xml`` output (bc-53)
# ---------------------------------------------------------------------------

# Matches ``<?xml ...?>`` processing instructions that delimit records in
# concatenated sdptool XML output.
_XML_PI_RE = re.compile(r"<\?xml[^?]*\?>")


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
        "0001": ("SDP", None),
    }
    protos: List[Dict[str, Any]] = []
    for seq in attr_elem.iter("sequence"):
        uuid_elem = seq.find("uuid")
        if uuid_elem is None:
            continue
        raw_uuid = (_xml_elem_value(uuid_elem) or "").lower().replace("0x", "")
        if not raw_uuid:
            continue
        # Normalise: take last 4 hex chars for 16-bit SIG UUIDs
        short = raw_uuid[-4:] if len(raw_uuid) <= 4 else raw_uuid
        if raw_uuid.endswith("0000-1000-8000-00805f9b34fb"):
            short = raw_uuid[4:8] if len(raw_uuid) > 8 else raw_uuid[:4]
        proto_name, param_key = _KNOWN_PROTOS.get(short, (None, None))
        entry: Dict[str, Any] = {"uuid": f"0x{short}"}
        if proto_name:
            entry["name"] = proto_name
        # Extract first numeric param after the UUID element
        param_elem = seq.find("uint8") or seq.find("uint16") or seq.find("uint32")
        param_val_str = _xml_elem_value(param_elem)
        if param_val_str and param_key:
            try:
                entry["params"] = {param_key: int(param_val_str, 0)}
            except (ValueError, AttributeError):
                pass
        protos.append(entry)
    return protos


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

    for attr in root.findall("attribute"):
        attr_id = attr.get("id", "").lower()

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
                low = raw.lower()
                if low.endswith("0000-1000-8000-00805f9b34fb"):
                    uuid_val = f"0x{low[4:8]}"
                elif len(raw) == 36 and "-" in raw:
                    uuid_val = low
                else:
                    uuid_val = f"0x{low.replace('0x', '')}"
                break  # first Service Class UUID

        elif attr_id == "0x0004":  # Protocol Descriptor List
            pdl = _extract_protocol_descriptors_xml(attr)
            if pdl:
                protocol_descriptors = pdl
            for seq in attr.iter("sequence"):
                proto_uuid_elem = seq.find("uuid")
                if proto_uuid_elem is None:
                    continue
                proto = (_xml_elem_value(proto_uuid_elem) or "").lower()
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
                low_u = raw_u.lower()
                if low_u.endswith("0000-1000-8000-00805f9b34fb"):
                    p_uuid = f"0x{low_u[4:8]}"
                elif len(raw_u) == 36 and "-" in raw_u:
                    p_uuid = low_u
                else:
                    p_uuid = f"0x{low_u.replace('0x', '')}"
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
        try:
            results.append(_parse_xml_record(frag))
        except ET.ParseError:
            continue
    return results


# ---------------------------------------------------------------------------
# Connectionless SDP Query with Reachability Check
# ---------------------------------------------------------------------------

def discover_services_sdp_connectionless(
    mac_address: str,
    timeout: int = 30,
    l2ping_count: int = 3,
    l2ping_timeout: int = 13,
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
            raise RuntimeError(
                f"Device {mac_address} is not reachable via L2CAP: {error_msg}. "
                "SDP query skipped. Ensure device is powered on and in range."
            )
        
        print_and_log(
            f"[classic_sdp] Device reachable (avg RTT: {rtt:.2f}ms), proceeding with SDP query",
            LOG__DEBUG
        )
    
    # Device is reachable, proceed with normal SDP discovery (without connectionless to avoid recursion)
    return discover_services_sdp(mac_address, timeout=timeout, connectionless=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_services_sdp(
    mac_address: str,
    timeout: int = 30,
    connectionless: bool = False,
    l2ping_count: int = 3,
    l2ping_timeout: int = 13,
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

    Returns
    -------
    list of dict
        Parsed records as described in the module docstring.

    Raises
    ------
    RuntimeError
        If connectionless=True and device is unreachable, or if *sdptool* is missing/exits with error.
    """
    
    # If connectionless mode requested, use dedicated function
    if connectionless:
        return discover_services_sdp_connectionless(
            mac_address,
            timeout=timeout,
            l2ping_count=l2ping_count,
            l2ping_timeout=l2ping_timeout,
        )

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

    # Strategy (bc-53): ``browse --xml`` gives structured XML that the
    # XML parser handles reliably (no RFCOMM/L2CAP confusion).
    # ``records`` is the final fallback — its human-readable format is
    # what ``_parse_records()`` was designed for.
    _CMD_XML = "browse_xml"
    _CMD_REC = "records"
    cmds_to_try = [
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

    raise RuntimeError(f"sdptool failed: {last_error}") 


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