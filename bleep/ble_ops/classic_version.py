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
    "map_lmp_version_to_spec",
    "map_profile_version_to_spec",
]

# LMP Version to Bluetooth Core Specification mapping
# Based on Bluetooth Core Specification version numbers
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
    
    Uses hciconfig to read version information without requiring sudo.
    This queries the LOCAL adapter's capabilities, not the remote device.
    
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
        # Query adapter information
        result = subprocess.run(
            [hciconfig_path, adapter],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode != 0:
            print_and_log(
                f"[classic_version] hciconfig failed: {result.stderr.strip()}",
                LOG__DEBUG
            )
            return None
        
        output = result.stdout
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


def map_lmp_version_to_spec(lmp_version: Optional[int]) -> Optional[str]:
    """Map LMP version number to Bluetooth Core Specification version.
    
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

