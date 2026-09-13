"""bleep.ble_ops.classic_version – Bluetooth version detection helpers.

This module provides functions to query Bluetooth version information including
HCI/LMP versions and profile version mapping.
"""

from __future__ import annotations

import subprocess
import shutil
import re
from typing import Dict, Any, Optional, Tuple

from bleep.core.log import print_and_log, LOG__DEBUG

__all__ = [
    "query_hci_version",
    "query_remote_version",
    "map_lmp_version_to_spec",
    "map_profile_version_to_spec",
    "resolve_manufacturer_name",
    "infer_min_bt_version_from_le_features",
]

# LMP Version to Bluetooth Core Specification mapping (FALLBACK)
# Primary resolution uses SPEC_ID_NAMES__CORE_VERSION from uuids.py codegen.
# This hardcoded map serves as a fallback when codegen data is unavailable.
_LMP_VERSION_MAP: Dict[int, str] = {
    0: "Bluetooth 1.0b",
    1: "Bluetooth 1.1",
    2: "Bluetooth 1.2",
    3: "Bluetooth 2.0 + EDR",
    4: "Bluetooth 2.1 + EDR",
    5: "Bluetooth 3.0 + HS",
    6: "Bluetooth 4.0",
    7: "Bluetooth 4.1",
    8: "Bluetooth 4.2",
    9: "Bluetooth 5.0",
    10: "Bluetooth 5.1",
    11: "Bluetooth 5.2",
    12: "Bluetooth 5.3",
    13: "Bluetooth 5.4",
    14: "Bluetooth 5.5",
    15: "Bluetooth 5.6",
}

# Profile version to Bluetooth spec version mapping (heuristic)
# Profile versions are typically encoded as major.minor (e.g., 256 = 1.0, 257 = 1.1)
_PROFILE_VERSION_HINTS: Dict[int, str] = {
    # Common profile versions and their likely spec versions
    256: "1.0",  # 0x0100
    257: "1.1",  # 0x0101
    258: "1.2",  # 0x0102
    260: "1.4",  # 0x0104 (often used for 1.2+)
    261: "1.5",  # 0x0105 (often used for 2.0+)
    512: "2.0",  # 0x0200
    513: "2.1",  # 0x0201
    768: "3.0",  # 0x0300
}


def query_hci_version(adapter: str = "hci0") -> Optional[Dict[str, Any]]:
    """Query HCI and LMP version information from the local adapter.
    
    Uses **hciconfig** to read version information without requiring sudo.
    This queries the LOCAL adapter's capabilities, not the remote device.

    **Important:** Plain ``hciconfig hciX`` (no flags/commands) only prints *basic*
    info (type, BD address, MTUs, flags) per ``hciconfig(1)``. HCI/LMP version
    lines require either ``-a`` (all details) or the ``version`` subcommand.
    This function uses ``hciconfig -a <adapter>`` first, then falls back to
    ``hciconfig <adapter>`` if ``-a`` fails.
    
    Parameters
    ----------
    adapter : str, optional
        HCI adapter name (default: "hci0")
    
    Returns
    -------
    Optional[Dict[str, Any]]
        Dictionary containing:
        - hci_version: Optional[int] - HCI version number
        - hci_revision: Optional[int] - HCI revision
        - lmp_version: Optional[int] - LMP version number
        - lmp_subversion: Optional[int] - LMP subversion
        - manufacturer: Optional[int] - Manufacturer ID
        - raw_output: Optional[str] - Raw hciconfig output for analysis
        None if hciconfig is unavailable or query fails
    """
    hciconfig_path = shutil.which("hciconfig")
    if not hciconfig_path:
        print_and_log("[classic_version] hciconfig not found in PATH", LOG__DEBUG)
        return None
    
    try:
        # Prefer ``-a``: basic-only ``hciconfig hciX`` omits HCI/LMP/Manufacturer.
        for args in ([hciconfig_path, "-a", adapter], [hciconfig_path, adapter]):
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                output = result.stdout
                break
        else:
            print_and_log(
                f"[classic_version] hciconfig failed: {result.stderr.strip()}",
                LOG__DEBUG,
            )
            return None
        info: Dict[str, Any] = {
            "hci_version": None,
            "hci_revision": None,
            "lmp_version": None,
            "lmp_subversion": None,
            "manufacturer": None,
            "raw_output": output,
        }
        
        # Parse HCI Version (e.g., "HCI Version: 3.0 (0x5)")
        hci_ver_match = re.search(r'HCI Version:\s*[\d.]+.*?\(0x([0-9A-Fa-f]+)\)', output)
        if hci_ver_match:
            try:
                info["hci_version"] = int(hci_ver_match.group(1), 16)
            except ValueError:
                pass
        
        # Parse HCI Revision (e.g., "Revision: 0x2ec")
        hci_rev_match = re.search(r'Revision:\s*0x([0-9A-Fa-f]+)', output)
        if hci_rev_match:
            try:
                info["hci_revision"] = int(hci_rev_match.group(1), 16)
            except ValueError:
                pass
        
        # Parse LMP Version (e.g., "LMP Version: 3.0 (0x5)")
        lmp_ver_match = re.search(r'LMP Version:\s*[\d.]+.*?\(0x([0-9A-Fa-f]+)\)', output)
        if lmp_ver_match:
            try:
                info["lmp_version"] = int(lmp_ver_match.group(1), 16)
            except ValueError:
                pass
        
        # Parse LMP Subversion (e.g., "Subversion: 0x4203")
        lmp_sub_match = re.search(r'Subversion:\s*0x([0-9A-Fa-f]+)', output)
        if lmp_sub_match:
            try:
                info["lmp_subversion"] = int(lmp_sub_match.group(1), 16)
            except ValueError:
                pass
        
        # Parse Manufacturer (e.g., "Manufacturer: Broadcom Corporation (15)")
        mfr_match = re.search(r'Manufacturer:.*?\((\d+)\)', output)
        if mfr_match:
            try:
                info["manufacturer"] = int(mfr_match.group(1))
            except ValueError:
                pass
        
        return info
        
    except subprocess.TimeoutExpired:
        print_and_log("[classic_version] hciconfig query timed out", LOG__DEBUG)
        return None
    except Exception as exc:
        print_and_log(f"[classic_version] Error querying HCI version: {exc}", LOG__DEBUG)
        return None


# ---------------------------------------------------------------------------
# Remote device LMP version query
# ---------------------------------------------------------------------------

# hcitool info output format (from BlueZ source tools/hcitool.c):
#   \tLMP Version: %s (0x%x) LMP Subversion: 0x%x
#   \tManufacturer: %s (%d)
#   \tFeatures[ page N]: 0x%2.2x 0x%2.2x 0x%2.2x 0x%2.2x 0x%2.2x 0x%2.2x 0x%2.2x 0x%2.2x
_REMOTE_LMP_RE = re.compile(
    r'LMP Version:\s*[\d.]+\s*\(0x([0-9A-Fa-f]+)\)\s*'
    r'LMP Subversion:\s*0x([0-9A-Fa-f]+)',
)
_REMOTE_MFR_RE = re.compile(r'Manufacturer:\s*(.+?)\s*\((\d+)\)')
_REMOTE_FEATURES_RE = re.compile(
    r'Features(?:\s*page\s*(\d+))?:\s*((?:0x[0-9A-Fa-f]{2}\s*)+)',
)


def query_remote_version(
    address: str, adapter: str = "hci0"
) -> Optional[Dict[str, Any]]:
    """Query a remote Classic (BR/EDR) device's LMP version via ``hcitool info``.

    Establishes an ACL connection, issues HCI Read Remote Version Information
    and Read Remote Features, then disconnects. This is an **active** operation
    that the remote device may log.

    Parameters
    ----------
    address : str
        Remote device BD_ADDR (e.g. "AA:BB:CC:DD:EE:FF").
    adapter : str, optional
        Local HCI adapter name (default: "hci0").

    Returns
    -------
    Optional[Dict[str, Any]]
        Dictionary containing:
        - lmp_version: int — LMP version byte (0x00–0x0F)
        - lmp_subversion: int — LMP subversion (uint16)
        - manufacturer: int — controller manufacturer company ID
        - manufacturer_name: Optional[str] — human-readable manufacturer name
        - lmp_spec: Optional[str] — mapped Core Specification string
        - features_raw: list[str] — per-page hex feature dumps
        - raw_output: str — full hcitool output for diagnostics
        None if hcitool is unavailable, device unreachable, or parse fails.
    """
    hcitool_path = shutil.which("hcitool")
    if not hcitool_path:
        print_and_log(
            "[classic_version] hcitool not found in PATH — cannot query remote version",
            LOG__DEBUG,
        )
        return None

    cmd = [hcitool_path, "-i", adapter, "info", address.upper()]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        print_and_log(
            f"[classic_version] hcitool info {address} timed out (30s)", LOG__DEBUG,
        )
        return None
    except Exception as exc:
        print_and_log(
            f"[classic_version] hcitool info {address} failed: {exc}", LOG__DEBUG,
        )
        return None

    if result.returncode != 0:
        stderr_msg = result.stderr.strip() if result.stderr else "unknown error"
        print_and_log(
            f"[classic_version] hcitool info {address} exited {result.returncode}: {stderr_msg}",
            LOG__DEBUG,
        )
        return None

    output = result.stdout
    if not output.strip():
        print_and_log(
            f"[classic_version] hcitool info {address} returned empty output", LOG__DEBUG,
        )
        return None

    # Parse LMP Version + Subversion
    lmp_match = _REMOTE_LMP_RE.search(output)
    if not lmp_match:
        print_and_log(
            f"[classic_version] Could not parse LMP version from hcitool info output",
            LOG__DEBUG,
        )
        return None

    try:
        lmp_version = int(lmp_match.group(1), 16)
        lmp_subversion = int(lmp_match.group(2), 16)
    except (ValueError, IndexError):
        return None

    # Parse Manufacturer
    manufacturer: Optional[int] = None
    manufacturer_name: Optional[str] = None
    mfr_match = _REMOTE_MFR_RE.search(output)
    if mfr_match:
        manufacturer_name = mfr_match.group(1).strip()
        try:
            manufacturer = int(mfr_match.group(2))
        except ValueError:
            pass

    # Parse Features pages
    features_raw: list[str] = []
    for feat_match in _REMOTE_FEATURES_RE.finditer(output):
        page_hex = feat_match.group(2).strip()
        page_num = feat_match.group(1)
        prefix = f"page {page_num}: " if page_num else ""
        features_raw.append(f"{prefix}{page_hex}")

    return {
        "lmp_version": lmp_version,
        "lmp_subversion": lmp_subversion,
        "manufacturer": manufacturer,
        "manufacturer_name": manufacturer_name,
        "lmp_spec": map_lmp_version_to_spec(lmp_version),
        "features_raw": features_raw,
        "raw_output": output,
    }


def map_lmp_version_to_spec(lmp_version: Optional[int]) -> Optional[str]:
    """Map LMP version number to Bluetooth Core Specification version.

    Attempts resolution via the SIG-sourced ``SPEC_ID_NAMES__CORE_VERSION``
    dict (populated by ``update_ble_uuids``). Falls back to the hardcoded
    ``_LMP_VERSION_MAP`` if the codegen dict is unavailable or lacks the entry.
    
    Parameters
    ----------
    lmp_version : Optional[int]
        LMP version number (0-15)
    
    Returns
    -------
    Optional[str]
        Bluetooth Core Specification version string (e.g., "Bluetooth 5.0")
        or None if version is unknown
    """
    if lmp_version is None:
        return None

    # Primary: SIG-sourced codegen data (richer names)
    try:
        from bleep.ble_ops.common.conversion import resolve_core_version
        sig_name = resolve_core_version(lmp_version)
        if sig_name:
            return sig_name
    except ImportError:
        pass

    # Fallback: hardcoded map
    return _LMP_VERSION_MAP.get(lmp_version)


def map_profile_version_to_spec(profile_version: Optional[int]) -> Optional[str]:
    """Map profile version number to likely Bluetooth spec version (heuristic).
    
    This is a heuristic mapping based on common profile version encodings.
    Profile versions are typically encoded as major.minor (e.g., 256 = 1.0).
    
    Parameters
    ----------
    profile_version : Optional[int]
        Profile version number (typically 256+)
    
    Returns
    -------
    Optional[str]
        Likely Bluetooth spec version (e.g., "1.2") or None if unknown
    """
    if profile_version is None:
        return None
    
    # Direct lookup
    if profile_version in _PROFILE_VERSION_HINTS:
        return _PROFILE_VERSION_HINTS[profile_version]
    
    # Heuristic: extract major.minor from version
    # Version 256 = 0x0100 = 1.0, 257 = 0x0101 = 1.1, etc.
    major = (profile_version >> 8) & 0xFF
    minor = profile_version & 0xFF
    
    if major > 0:
        return f"{major}.{minor}"
    
    return None


def resolve_manufacturer_name(manufacturer_id: Optional[int]) -> Optional[str]:
    """Resolve a 16-bit BT SIG company identifier to its registered name.

    Uses the codegen ``SPEC_ID_NAMES__COMPANY_IDENTS`` dict (via the common
    conversion helper). Returns None if the ID is unknown.

    Parameters
    ----------
    manufacturer_id : Optional[int]
        BT SIG company identifier (0–65535).

    Returns
    -------
    Optional[str]
        Registered company name, or None.
    """
    if manufacturer_id is None:
        return None
    try:
        from bleep.ble_ops.common.conversion import resolve_manufacturer_name as _resolve
        return _resolve(manufacturer_id)
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# BLE advertisement feature-based version inference (RV-4b)
# ---------------------------------------------------------------------------

# LE Supported Features bit positions and the minimum BT Core version that
# introduced them. Only features definitively tied to a specific version are
# included. Ref: Bluetooth Core Spec Vol 6, Part B, Section 4.6.
_LE_FEATURE_MIN_VERSION: Dict[int, Tuple[int, str]] = {
    # bit: (min_lmp_version, feature_name)
    1: (7, "LE Encryption"),                    # BT 4.1 refined
    5: (7, "LE Data Packet Length Extension"),   # BT 4.2 (actually 8, corrected below)
    8: (9, "LE 2M PHY"),                        # BT 5.0
    9: (9, "Stable Modulation Index - Tx"),      # BT 5.0
    10: (9, "Stable Modulation Index - Rx"),     # BT 5.0
    11: (9, "LE Coded PHY"),                     # BT 5.0
    12: (9, "LE Extended Advertising"),          # BT 5.0
    13: (9, "LE Periodic Advertising"),          # BT 5.0
    14: (9, "Channel Selection Algorithm #2"),   # BT 5.0
    17: (9, "Minimum Number of Used Channels"),  # BT 5.0
    24: (11, "Connected Isochronous Stream - Central"),  # BT 5.2
    25: (11, "Connected Isochronous Stream - Peripheral"),  # BT 5.2
    26: (11, "Isochronous Broadcaster"),         # BT 5.2
    27: (11, "Synchronized Receiver"),           # BT 5.2
    28: (11, "Connected Isochronous Stream (Host)"),  # BT 5.2
    30: (12, "Connection Subrating"),            # BT 5.3
    31: (12, "Connection Subrating (Host)"),     # BT 5.3
    32: (12, "Channel Classification"),          # BT 5.3
}
# Correct Data Length Extension: introduced in 4.2 (LMP 8)
_LE_FEATURE_MIN_VERSION[5] = (8, "LE Data Packet Length Extension")


def infer_min_bt_version_from_le_features(features_bytes: bytes) -> Optional[str]:
    """Infer the minimum Bluetooth Core version from LE Supported Features.

    Examines the LE Supported Features bitmask (AD type 0x27 or from HCI)
    and determines the minimum Core Specification version required to support
    the observed feature set.

    Parameters
    ----------
    features_bytes : bytes
        Raw LE Supported Features bytes (little-endian bitmask, up to 8 bytes).

    Returns
    -------
    Optional[str]
        Minimum Bluetooth specification string (e.g., "Bluetooth 5.0"),
        or None if no version-specific features are detected.
    """
    if not features_bytes:
        return None

    # Convert bytes to integer bitmask (little-endian)
    features_int = int.from_bytes(features_bytes, byteorder="little")

    max_lmp = 0
    for bit, (min_lmp, _name) in _LE_FEATURE_MIN_VERSION.items():
        if features_int & (1 << bit):
            if min_lmp > max_lmp:
                max_lmp = min_lmp

    if max_lmp == 0:
        return None

    return map_lmp_version_to_spec(max_lmp)

