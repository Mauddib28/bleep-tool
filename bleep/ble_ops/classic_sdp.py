from __future__ import annotations
"""bleep.ble_ops.classic_sdp – SDP service discovery for Bluetooth Classic.

This helper intentionally avoids third-party Bluetooth libraries.  It relies on
BlueZ’s *sdptool* binary to obtain the full SDP record (required for RFCOMM
channel extraction) because BlueZ’s D-Bus API only exposes the service UUID
list, not the protocol descriptor details.

Typical usage
-------------
>>> from bleep.ble_ops.classic_sdp import discover_services_sdp, discover_services_sdp_connectionless
>>> records = discover_services_sdp("AA:BB:CC:DD:EE:FF")
>>> for rec in records:
...     print(rec["name"], rec["channel"], rec["uuid"])

Connectionless mode (with l2ping reachability check):
>>> records = discover_services_sdp("AA:BB:CC:DD:EE:FF", connectionless=True)
>>> # Or use dedicated function:
>>> records = discover_services_sdp_connectionless("AA:BB:CC:DD:EE:FF")

Returned structure is a list of dicts::
    {"name": str | None,
     "uuid": str | None,
     "channel": int | None,
     "handle": int | None,  # Service Record Handle (0x0000)
     "profile_descriptors": List[Dict] | None,  # Bluetooth Profile Descriptor List (0x0009): [{"uuid": str, "version": int}]
     "service_version": int | None,  # Service Version (0x0300)
     "description": str | None,  # Service Description (0x0101)
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
    from bleep.ble_ops.classic_ping import classic_l2ping
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
            print_and_log(f"[classic_sdp] GetServiceRecords failed: {exc}", LOG__DEBUG)
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
            service_version_val: Optional[int] = None
            description_val: Optional[str] = None

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
                    # ProtocolDescriptorList – walk for RFCOMM
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

            parsed.append({
                "name": name_val,
                "uuid": uuid_val,
                "channel": channel_val,
                "handle": handle_val,
                "profile_descriptors": profile_descriptors,
                "service_version": service_version_val,
                "description": description_val,
                "raw": xml_text.strip(),
            })

        if parsed and any(r.get("channel") is not None for r in parsed):
            print_and_log("[classic_sdp] D-Bus GetServiceRecords successful", LOG__DEBUG)
            return parsed

        print_and_log("[classic_sdp] D-Bus records lacked RFCOMM info", LOG__DEBUG)
        return []

    except Exception as exc:  # noqa: BLE001 – log & fallback
        print_and_log(f"[classic_sdp] D-Bus SDP path raised: {exc}", LOG__DEBUG)
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SDPTOOL_PATH: Optional[str] = shutil.which("sdptool")


def _ensure_sdptool() -> str:
    """Return path to *sdptool* or raise RuntimeError if not found."""
    if _SDPTOOL_PATH is None:
        raise RuntimeError("'sdptool' binary not found in PATH – install bluez-utils")
    return _SDPTOOL_PATH


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
        
        record: Dict[str, Any] = {
            "name": name_match.group(1).strip() if name_match else None,
            "uuid": uuid_value,
            "channel": int(channel_match.group(1), 16 if channel_match and channel_match.group(1).startswith("0x") else 10) if channel_match else None,
            "handle": handle_val,
            "profile_descriptors": profile_descriptors,
            "service_version": service_version_val,
            "description": description_val,
            "raw": block.strip(),
        }
        results.append(record)
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
        return dbus_res

    # ------------------------------------------------------------------
    # 2. Fallback to external sdptool binary
    # ------------------------------------------------------------------

    path = _ensure_sdptool()

    # Strategy: try faster 'browse --tree' first. Fallback to the slower 'records'
    cmds_to_try = [
        [path, "browse", "--tree", mac_address],
        [path, "records", mac_address],
    ]

    last_error: Optional[str] = None
    for idx, cmd in enumerate(cmds_to_try, start=1):
        print_and_log(f"[*] Running '{' '.join(cmd)}' (attempt {idx})", LOG__DEBUG)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout if cmd[-2] != "records" else timeout * 2,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = f"sdptool {'records' if 'records' in cmd else 'browse'} timed out"
            continue

        if proc.returncode != 0:
            last_error = proc.stderr.strip() or proc.stdout.strip()
            continue

        # ------------------------------------------------------------------
        # Debug helpers – dump raw output & parsed results when LOG__DEBUG is
        # enabled so that users can see exactly what *sdptool* returned and
        # how the regex parser interpreted it.  This makes troubleshooting
        # parsing-failures (e.g. vendor-specific record formatting) easier.
        # ------------------------------------------------------------------

        # Log the raw text (trimmed to avoid flooding the terminal if debug
        # logging is not turned on globally).
        if LOG__DEBUG:
            print_and_log("[classic_sdp] ---- raw sdptool output ----", LOG__DEBUG)
            print_and_log(proc.stdout.strip() or "<empty>", LOG__DEBUG)
            print_and_log("[classic_sdp] ---- end raw output ----", LOG__DEBUG)

        parsed = _parse_records(proc.stdout)

        # Log the parsed intermediate structure
        if LOG__DEBUG:
            print_and_log(f"[classic_sdp] Parsed {len(parsed)} record block(s)", LOG__DEBUG)
            for idx_rec, rec in enumerate(parsed, start=1):
                debug_info = f"  [{idx_rec}] name={rec.get('name')} uuid={rec.get('uuid')} channel={rec.get('channel')}"
                if rec.get('handle') is not None:
                    debug_info += f" handle={rec.get('handle')}"
                if rec.get('profile_descriptors'):
                    debug_info += f" profiles={len(rec.get('profile_descriptors', []))}"
                if rec.get('service_version') is not None:
                    debug_info += f" svc_ver={rec.get('service_version')}"
                print_and_log(debug_info, LOG__DEBUG)

        # Ensure we have at least one RFCOMM channel.  Some devices omit
        # the "Channel" line from *sdptool browse --tree* output (notably
        # PBAP PSE on certain feature-phones).  In that case we fall back
        # to the slower, but more complete, `sdptool records` call.
        if parsed:
            if any(rec.get("channel") is not None for rec in parsed):
                # If PBAP (0x112f) channel isn't present, fall through to records
                pbap_present = any(
                    (
                        (rec.get("uuid") and rec["uuid"].lower() in {"0x112f",
                            "0000112f-0000-1000-8000-00805f9b34fb"})
                        or (rec.get("name") and "pbap" in rec["name"].lower())
                        or (rec.get("name") and "phonebook" in rec["name"].lower())
                    )
                    for rec in parsed
                )
                if pbap_present:
                    return parsed
                last_error = "PBAP not in browse output"
                continue
            # otherwise continue loop to try the next command variant
            last_error = "No RFCOMM channels in browse output"
            continue
        last_error = "No services found"

    raise RuntimeError(f"sdptool failed: {last_error}") 