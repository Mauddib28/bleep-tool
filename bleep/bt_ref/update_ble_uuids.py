#!/usr/bin/python3
"""BLE SIG UUID updater for the refactored BLEEP code-base.

Usage (CLI):
    python -m bleep.bt_ref.update_ble_uuids           # regenerates uuids.py

The script downloads the official YAML tables from the Bluetooth SIG Bitbucket
repository and converts them into static dictionaries identical to those used
by the historical monolith.  The generated module is written to
`bleep/bt_ref/uuids.py` *inside the package* so regular imports pick it up on
next interpreter start.

Note: this tool purposefully lives **inside** bleep so it has no external
references and can be invoked from any environment that has the editable
package installed.  Networking errors do not raise – they will simply leave the
previous uuids.py untouched.
"""
from __future__ import annotations

import os
import json
import textwrap
import urllib.request as _url
import urllib.parse as _parse
import yaml as _yaml
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Source location mapping ----------------------------------------------------
# ---------------------------------------------------------------------------
# All YAML reference tables live under the Bluetooth-SIG *public/assigned_numbers*
# repository. Initial paths are defined here but are not considered definitive -
# BitBucket API search will be used to find files when default paths fail.
# ---------------------------------------------------------------------------

_SIG_ROOT = "https://bitbucket.org/bluetooth-SIG/public/raw/main/"
_SIG_API_ROOT = "https://api.bitbucket.org/2.0/repositories/bluetooth-SIG/public/"

# Default file paths - these are just starting points and may be updated
_FILES = {
    # UUID sub-directory ------------------------------------------------------
    "SERV": "assigned_numbers/uuids/service_uuids.yaml",
    "CHAR": "assigned_numbers/uuids/characteristic_uuids.yaml",
    "DESC": "assigned_numbers/uuids/descriptors.yaml",
    "MEMB": "assigned_numbers/uuids/member_uuids.yaml",
    "SDO": "assigned_numbers/uuids/sdo_uuids.yaml",
    "SERV_CLASS": "assigned_numbers/uuids/service_class.yaml",
    # Root-level and core/ subdirectory tables -------------------------------
    "COMPANY": "assigned_numbers/company_identifiers.yaml",
    "APPEAR": "assigned_numbers/core/appearance_values.yaml", 
    "AD_TYPES": "assigned_numbers/core/ad_types.yaml",
    "CODING_FORMAT": "assigned_numbers/core/coding_format.yaml",
    "NAMESPACE": "assigned_numbers/core/namespace.yaml",
    "PSM": "assigned_numbers/core/psm.yaml",
}

# Store the URL mappings in a JSON file for future use
_URL_MAPPING_PATH = Path(__file__).parent / "url_mappings.json"
_CACHE_DIR = Path(__file__).parent / "yaml_cache"

# Create cache directory if it doesn't exist
_CACHE_DIR.mkdir(exist_ok=True)

# Load URL mappings if available
_URL_MAPPINGS = {}
if _URL_MAPPING_PATH.exists():
    try:
        with open(_URL_MAPPING_PATH, 'r') as f:
            _URL_MAPPINGS = json.load(f)
            # Update _FILES with saved mappings to avoid trying incorrect paths
            for key, url in _URL_MAPPINGS.items():
                if key in _FILES and url.startswith(_SIG_ROOT):
                    # Extract the relative path from the full URL
                    relative_path = url[len(_SIG_ROOT):]
                    _FILES[key] = relative_path
                    print(f"[*] Using saved mapping for {key}: {relative_path}")
    except Exception as e:
        print(f"[!] Warning: Failed to load URL mappings: {e}")

# ---------------------------------------------------------------------------
# File header inserted at the top of *uuids.py* ------------------------------
# ---------------------------------------------------------------------------
#  • Starts at column-0 so the generated module is always syntactically valid.
#  • Mirrors the comment style of the historical *bluetooth_uuids.py* output.
# ---------------------------------------------------------------------------

_HEADER = (
    "#!/usr/bin/python3\n\n"
    "# Auto-generated Bluetooth SIG Assigned Numbers tables\n"
    "# DO NOT EDIT – run `python -m bleep.bt_ref.update_ble_uuids` instead.\n"
    "# Generated: {timestamp}\n"
    "# Incorporated BLE CTF known flags\n"
    "# Included [Mesh] Agent path and interfaces\n"
    "# Sources: {sources}\n\n"
)

_SRC_LIST = list(_FILES.values())  # Populated below – declared early for f-string

_OUT_PATH = Path(__file__).with_name("uuids.py")
_SIG_SUFFIX = "-0000-1000-8000-00805f9b34fb"

def _save_url_mappings():
    """Save URL mappings to JSON file for future use."""
    try:
        with open(_URL_MAPPING_PATH, 'w') as f:
            json.dump(_URL_MAPPINGS, f, indent=2)
    except Exception as e:
        print(f"[!] Warning: Failed to save URL mappings: {e}")

def _download_file(url: str, timeout: int = 15) -> str | None:
    """Download content from URL with timeout, returns None on failure."""
    try:
        with _url.urlopen(url, timeout=timeout) as resp:
            data = resp.read().decode()
        return data
    except Exception as e:
        print(f"[!] Failed to download {url}: {e}")
        return None

def _search_bitbucket_for_file(key: str, filename: str) -> str | None:
    """
    Search BitBucket API for the given file.
    Returns URL if found, None otherwise.
    """
    print(f"[*] Searching for '{filename}' in BitBucket repository...")
    
    # Use API search endpoint to find the file
    search_url = f"{_SIG_API_ROOT}src/main?q=filename:{filename}"
    print(f"[*] Using BitBucket API search: {search_url}")
    
    response_data = _download_file(search_url)
    if not response_data:
        return None
    
    try:
        response = json.loads(response_data)
        
        if "values" in response and len(response["values"]) > 0:
            # Extract paths of all matching results
            matches = []
            
            for item in response["values"]:
                if item.get("type") == "commit_file" and filename in item.get("path", ""):
                    path = item["path"]
                    raw_url = f"https://bitbucket.org/bluetooth-SIG/public/raw/main/{path}"
                    matches.append((path, raw_url))
            
            if not matches:
                print(f"[!] No matching files found for {filename}")
                return None
            
            if len(matches) == 1:
                # Only one match found, use it
                path, raw_url = matches[0]
                print(f"[+] Found file via API: {raw_url}")
                return raw_url
            else:
                # Multiple matches found, ask user to choose
                print(f"[*] Multiple matches found for {filename}:")
                for i, (path, url) in enumerate(matches, 1):
                    print(f"    {i}. {path}")
                
                # Return the first match by default, but will prompt user later
                return matches[0][1]
    except Exception as e:
        print(f"[!] Error parsing BitBucket API response: {e}")
    
    # If we couldn't search or parse results
    print(f"[!] Could not find {filename} in BitBucket repository")
    return None

def _prompt_user_for_url_update(key: str, new_url: str) -> bool:
    """Ask user to accept new URL and update mapping."""
    print("\n" + "=" * 80)
    print(f"Found alternative location for {key} file:")
    print(f"  {new_url}")
    print("Would you like to use this file and update the URL for future use?")
    response = input("Accept new URL? (y/n): ").strip().lower()
    print("=" * 80 + "\n")
    return response.startswith('y')

def _cache_yaml_file(key: str, data: str):
    """Save YAML data to local cache file."""
    try:
        cache_path = _CACHE_DIR / f"{key.lower()}.yaml"
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(data)
        print(f"[+] Cached {key} data to {cache_path}")
    except Exception as e:
        print(f"[!] Failed to cache {key} data: {e}")

def _load_cached_yaml(key: str) -> dict | None:
    """Load YAML data from local cache file."""
    try:
        cache_path = _CACHE_DIR / f"{key.lower()}.yaml"
        if cache_path.exists():
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = f.read()
            yaml_data = _yaml.safe_load(data)
            print(f"[+] Loaded {key} from local cache")
            return yaml_data
        else:
            print(f"[!] No local cache found for {key}")
    except Exception as e:
        print(f"[!] Failed to load cache for {key}: {e}")
    return None

def _fetch_yaml(name: str) -> dict | None:
    """
    Fetch YAML data for the given key, following these steps:
    1. Try URL from saved mappings if available
    2. If failed, try the default URL
    3. If failed, search BitBucket API for file
    4. If found and approved by user, update URL mapping
    5. If all remote attempts fail, try local cache
    6. If cache fails, return None
    """
    file_path = _FILES[name]
    filename = Path(file_path).name
    
    # Step 1: Try URL from saved mappings first if available
    if name in _URL_MAPPINGS:
        mapped_url = _URL_MAPPINGS[name]
        print(f"[*] Trying saved mapping for {name}: {mapped_url}")
        data = _download_file(mapped_url)
        if data:
            # Successfully downloaded from saved mapping
            try:
                yaml_data = _yaml.safe_load(data)
                _cache_yaml_file(name, data)  # Cache for future use
                return yaml_data
            except Exception as e:
                print(f"[!] Error parsing YAML from saved mapping: {e}")
    
    # Step 2: Try the default URL if no mapping or mapping failed
    default_url = _SIG_ROOT + file_path
    print(f"[*] Trying default URL for {name}: {default_url}")
    data = _download_file(default_url)
    
    if data:
        # Successfully downloaded from default URL
        try:
            yaml_data = _yaml.safe_load(data)
            _cache_yaml_file(name, data)  # Cache for future use
            # Update the mapping to use this successful URL
            if name not in _URL_MAPPINGS or _URL_MAPPINGS[name] != default_url:
                _URL_MAPPINGS[name] = default_url
                _save_url_mappings()
            return yaml_data
        except Exception as e:
            print(f"[!] Error parsing YAML from default URL: {e}")
    
    # Step 3: Search BitBucket for file
    found_url = _search_bitbucket_for_file(name, filename)
    if found_url:
        # Step 4: Ask user to approve
        if _prompt_user_for_url_update(name, found_url):
            data = _download_file(found_url)
            if data:
                try:
                    # Update URL mapping for future use
                    _URL_MAPPINGS[name] = found_url
                    # Update the _FILES dictionary too
                    if found_url.startswith(_SIG_ROOT):
                        _FILES[name] = found_url[len(_SIG_ROOT):]
                    _save_url_mappings()
                    yaml_data = _yaml.safe_load(data)
                    _cache_yaml_file(name, data)  # Cache for future use
                    return yaml_data
                except Exception as e:
                    print(f"[!] Error parsing YAML from found URL: {e}")
    
    # Step 5: Try local cache
    print(f"[*] All remote sources failed, trying local cache for {name}")
    yaml_data = _load_cached_yaml(name)
    if yaml_data:
        return yaml_data
    
    # Step 6: All attempts failed
    print(f"[!] Failed to retrieve {name} data from any source")
    return None

# ---------------------------------------------------------------------------
# YAML → dict helpers --------------------------------------------------------
# ---------------------------------------------------------------------------

def _gen_dict_block(var: str, yaml_data: dict, *, key_style: str = "uuid") -> str:
    """Return formatted Python dictionary block with a leading comment.

    key_style:
        "uuid"  – 16-bit short UUIDs → 128-bit strings  (major tables)
        "hex"   – leave as *0xXXXX* hex string           (company, advert, …)
    """

    if var.startswith("SPEC_UUID_NAMES"):
        header_line = "# Specification UUID Definitions"
    else:
        header_line = "# Specification ID Definitions"
    header_line += f"\n# {var}"
    lines: list[str] = [header_line, f"{var} = {{"]

    if not yaml_data:
        print(f"[!] Warning: No data for {var}, creating empty dictionary")
        lines.append("}\n")
        return "\n".join(lines)

    try:
        # Handle different YAML structures
        # Check for the first top-level key in the YAML data
        first_key = next(iter(yaml_data))
        
        # Handle structured appearance data with categories and subcategories
        if first_key == "appearance_values" and var == "SPEC_ID_NAMES__APPEARANCE_VALUES":
            print(f"[*] Processing appearance values with categories and subcategories")
            appearances = yaml_data["appearance_values"]
            for entry in appearances:
                if "category" in entry and "name" in entry:
                    # Process main category
                    cat_val = int(str(entry["category"]), 16)
                    cat_name = entry["name"].replace("\"", r"\"")
                    key = f"0x{cat_val:04x}"
                    lines.append(f"\t\"{key}\" : \"{cat_name}\",")
                    
                    # Process subcategories if present
                    if "subcategory" in entry:
                        for sub in entry["subcategory"]:
                            if "value" in sub and "name" in sub:
                                # Calculate combined value (category + subcategory)
                                sub_val = int(str(sub["value"]), 16)
                                combined = (cat_val << 6) | sub_val
                                sub_name = sub["name"].replace("\"", r"\"")
                                key = f"0x{combined:04x}"
                                lines.append(f"\t\"{key}\" : \"{sub_name}\",")
        
        # Handle coding format data
        elif first_key == "coding_formats" and var == "SPEC_ID_NAMES__CODING_FORMATS":
            print(f"[*] Processing coding format data")
            formats = yaml_data["coding_formats"]
            for entry in formats:
                if "value" in entry and "name" in entry:
                    val = int(str(entry["value"]), 16)
                    name = entry["name"].replace("\"", r"\"")
                    key = f"0x{val:04x}"
                    lines.append(f"\t\"{key}\" : \"{name}\",")
        
        # Handle namespace data
        elif first_key == "namespace" and var == "SPEC_ID_NAMES__NAMESPACE_DESCS":
            print(f"[*] Processing namespace data")
            namespaces = yaml_data["namespace"]
            for entry in namespaces:
                if "value" in entry and "name" in entry:
                    val = int(str(entry["value"]), 16)
                    name = entry["name"].replace("\"", r"\"")
                    key = f"0x{val:04x}"
                    lines.append(f"\t\"{key}\" : \"{name}\",")
        
        # Handle PSM data
        elif first_key == "psms" and var == "SPEC_ID_NAMES__PSM":
            print(f"[*] Processing PSM data")
            psms = yaml_data["psms"]
            for entry in psms:
                if "psm" in entry and "name" in entry:
                    val = int(str(entry["psm"]), 16)
                    name = entry["name"].replace("\"", r"\"")
                    key = f"0x{val:04x}"
                    lines.append(f"\t\"{key}\" : \"{name}\",")
        
        # Default handling for standard list formats with uuid or value fields
        else:
            for entry in yaml_data.get(first_key, []):
                # Each entry holds 'uuid' or 'value'
                raw_val = entry.get("uuid") or entry.get("value")
                if raw_val is None:
                    continue

                # Convert to int if it begins with 0x otherwise assume decimal/int
                short = int(str(raw_val), 16) if isinstance(raw_val, str) and raw_val.startswith("0x") else int(raw_val)

                name = entry.get("name", "").replace("\"", r"\"")

                if key_style == "uuid":
                    key = f"0000{short:04x}{_SIG_SUFFIX}"
                else:
                    key = f"0x{short:04x}"

                lines.append(f"\t\"{key}\" : \"{name}\",")
    except Exception as e:
        print(f"[!] Error generating dictionary block for {var}: {e}")
        print(f"[!] YAML data structure: {list(yaml_data.keys())}")
        lines.append("}\n")
        return "\n".join(lines)

    lines.append("}\n")
    return "\n".join(lines)

def regenerate() -> None:
    """Download all YAML tables and rewrite uuids.py."""
    blocks: list[str] = []
    failed_fetches = []
    successful_fetches = []
    
    print("[*] Starting BLE SIG UUID regeneration process...")

    uuid_keys = ["SERV", "CHAR", "DESC", "MEMB", "SDO", "SERV_CLASS"]
    for key in uuid_keys:
        print(f"\n[*] Processing {key}...")
        data = _fetch_yaml(key)
        if data is None:
            failed_fetches.append(key)
        else:
            successful_fetches.append(_FILES[key])
        blocks.append(_gen_dict_block(f"SPEC_UUID_NAMES__{key}", data, key_style="uuid"))

    id_map = {
        "COMPANY": "SPEC_ID_NAMES__COMPANY_IDENTS",
        "AD_TYPES": "SPEC_ID_NAMES__ADVERTISING_TYPES",
        "APPEAR": "SPEC_ID_NAMES__APPEARANCE_VALUES",
        "CODING_FORMAT": "SPEC_ID_NAMES__CODING_FORMATS",
        "NAMESPACE": "SPEC_ID_NAMES__NAMESPACE_DESCS",
        "PSM": "SPEC_ID_NAMES__PSM",
    }

    for key, var in id_map.items():
        print(f"\n[*] Processing {key}...")
        data = _fetch_yaml(key)
        if data is None:
            failed_fetches.append(key)
        else:
            successful_fetches.append(_FILES[key])
        blocks.append(_gen_dict_block(var, data, key_style="hex"))

    if failed_fetches:
        print(f"\n[!] Warning: Failed to fetch data for these keys: {', '.join(failed_fetches)}")
        print("    The output file will contain empty dictionaries for these keys.")
    
    if not successful_fetches:
        print("\n[!] CRITICAL: Could not fetch ANY data. Output will contain only empty dictionaries.")
        print("    Check network connectivity and ensure BitBucket repository is accessible.")
    
    # Use successful fetches as sources in header, or indicate fallback if none
    sources = successful_fetches if successful_fetches else ["none - using empty dictionaries"]
    content = _HEADER.format(timestamp=datetime.now().isoformat(timespec="seconds"), sources=", ".join(sources)) + "\n\n" + "\n".join(blocks)

    _OUT_PATH.write_text(content, encoding="utf-8")
    print(f"\n[+] Regenerated {_OUT_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    regenerate() 