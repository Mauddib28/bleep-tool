#!/usr/bin/python3
"""USB ID database updater for BLEEP.

Usage (CLI):
    python -m bleep.bt_ref.update_usb_ids           # regenerates usb_ids.py

The script downloads the official USB ID database from linux-usb.org and converts
it into static dictionaries for use throughout the codebase. The generated module
is written to `bleep/bt_ref/usb_ids.py` inside the package so regular imports
pick it up on next interpreter start.

This follows the same pattern as the BT SIG UUID updater, ensuring consistent
handling of external reference data.
"""
from __future__ import annotations

import os
import re
import urllib.request as _url
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Source location and constants
# ---------------------------------------------------------------------------

# Primary source for USB IDs database
USB_IDS_URL = "http://www.linux-usb.org/usb.ids"

# Backup URL in case the primary fails
USB_IDS_BACKUP_URL = "http://www.linux-usb.org/usb-ids.txt"

# Output file path (relative to this script)
OUTPUT_PATH = Path(__file__).parent / "usb_ids.py"

# Regular expressions for parsing the USB IDs file
VENDOR_RE = re.compile(r'^([0-9a-f]{4})\s+(.+)$')
DEVICE_RE = re.compile(r'^\t([0-9a-f]{4})\s+(.+)$')
INTERFACE_RE = re.compile(r'^\t\t([0-9a-f]{2})\s+(.+)$')

# ---------------------------------------------------------------------------
# Download and parsing functions
# ---------------------------------------------------------------------------

def download_usb_ids() -> str:
    """Download the USB IDs database from linux-usb.org.
    
    Returns:
        str: The contents of the USB IDs database file.
    """
    try:
        with _url.urlopen(USB_IDS_URL) as response:
            return response.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"Error downloading from primary URL: {e}")
        print(f"Trying backup URL...")
        try:
            with _url.urlopen(USB_IDS_BACKUP_URL) as response:
                return response.read().decode('utf-8', errors='replace')
        except Exception as e2:
            print(f"Error downloading from backup URL: {e2}")
            raise RuntimeError("Failed to download USB IDs database") from e2

def parse_usb_ids(content: str) -> Tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
    """Parse the USB IDs database content.
    
    Args:
        content: The raw content of the USB IDs database file.
        
    Returns:
        Tuple containing:
            - Dictionary mapping vendor IDs to vendor names
            - Dictionary mapping vendor IDs to dictionaries of product IDs and names
    """
    vendors = {}
    products = {}
    current_vendor = None
    
    for line in content.splitlines():
        # Skip comments and empty lines
        if not line or line.startswith('#'):
            continue
            
        # Check for vendor line
        vendor_match = VENDOR_RE.match(line)
        if vendor_match:
            vendor_id, vendor_name = vendor_match.groups()
            vendor_id = vendor_id.lower()
            current_vendor = vendor_id
            vendors[vendor_id] = vendor_name
            products[vendor_id] = {}
            continue
            
        # Check for device line (product)
        device_match = DEVICE_RE.match(line)
        if device_match and current_vendor:
            product_id, product_name = device_match.groups()
            product_id = product_id.lower()
            products[current_vendor][product_id] = product_name
            continue
            
        # We ignore interface lines for now as they're not needed for modalias parsing
    
    return vendors, products

def generate_module_content(vendors: Dict[str, str], products: Dict[str, Dict[str, str]]) -> str:
    """Generate Python module content from parsed USB ID data.
    
    Args:
        vendors: Dictionary mapping vendor IDs to vendor names
        products: Dictionary mapping vendor IDs to dictionaries of product IDs and names
        
    Returns:
        str: Python code for the usb_ids.py module
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Start with the module docstring and imports
    content = [
        '#!/usr/bin/python3',
        '"""USB ID database for BLEEP.',
        '',
        f'Auto-generated from linux-usb.org/usb.ids on {timestamp}.',
        'Do not edit manually - run update_usb_ids.py to regenerate.',
        '"""',
        'from __future__ import annotations',
        'import re',
        '',
        '# Dictionary mapping vendor IDs (as lowercase hex strings) to vendor names',
        'USB_VENDORS = {',
    ]
    
    # Add vendor dictionary entries
    for vendor_id, vendor_name in sorted(vendors.items()):
        # Escape any quotes in the vendor name
        vendor_name = vendor_name.replace('"', '\\"')
        content.append(f'    "{vendor_id}": "{vendor_name}",')
    
    content.append('}')
    content.append('')
    
    # Add product dictionary entries
    content.append('# Dictionary mapping vendor IDs to dictionaries of product IDs and names')
    content.append('USB_PRODUCTS = {')
    
    for vendor_id, vendor_products in sorted(products.items()):
        if vendor_products:  # Only include vendors with products
            content.append(f'    "{vendor_id}": {{')
            for product_id, product_name in sorted(vendor_products.items()):
                # Escape any quotes in the product name
                product_name = product_name.replace('"', '\\"')
                content.append(f'        "{product_id}": "{product_name}",')
            content.append('    },')
    
    content.append('}')
    content.append('')
    
    # Add helper functions for modalias parsing
    content.append('''
# Helper functions for modalias parsing

def get_vendor_name(vendor_id: str) -> str:
    """Get vendor name from vendor ID.
    
    Args:
        vendor_id: Vendor ID as a hex string (with or without '0x' prefix)
        
    Returns:
        str: Vendor name or "Unknown" if not found
    """
    # Normalize vendor ID to lowercase without '0x' prefix
    vendor_id = vendor_id.lower().replace('0x', '')
    
    return USB_VENDORS.get(vendor_id, f"Unknown (0x{vendor_id})")

def get_product_name(vendor_id: str, product_id: str) -> str:
    """Get product name from vendor ID and product ID.
    
    Args:
        vendor_id: Vendor ID as a hex string (with or without '0x' prefix)
        product_id: Product ID as a hex string (with or without '0x' prefix)
        
    Returns:
        str: Product name or "Unknown" if not found
    """
    # Normalize IDs to lowercase without '0x' prefix
    vendor_id = vendor_id.lower().replace('0x', '')
    product_id = product_id.lower().replace('0x', '')
    
    vendor_products = USB_PRODUCTS.get(vendor_id, {})
    return vendor_products.get(product_id, f"Unknown (0x{product_id})")

def parse_modalias(modalias: str) -> dict:
    """Parse a modalias string into its components.
    
    Args:
        modalias: A modalias string (e.g., 'usb:v05ACp820Ad0210')
        
    Returns:
        dict: Dictionary with parsed components or empty dict if parsing fails
    """
    # Parse USB modalias format: usb:vVVVVpPPPPdDDDD
    match = re.match(r'usb:v([0-9A-Fa-f]{4})p([0-9A-Fa-f]{4})d([0-9A-Fa-f]{4})', modalias)
    if not match:
        return {}
        
    vendor_id = match.group(1).lower()
    product_id = match.group(2).lower()
    device_id = match.group(3).lower()
    
    return {
        'vendor_id': vendor_id,
        'vendor_name': get_vendor_name(vendor_id),
        'product_id': product_id,
        'product_name': get_product_name(vendor_id, product_id),
        'device_id': device_id,
    }
''')
    
    return '\n'.join(content)

def update_usb_ids() -> bool:
    """Main function to update the USB IDs database.
    
    Returns:
        bool: True if the update was successful, False otherwise.
    """
    try:
        print(f"Downloading USB IDs database from {USB_IDS_URL}...")
        content = download_usb_ids()
        
        print("Parsing USB IDs database...")
        vendors, products = parse_usb_ids(content)
        
        print(f"Found {len(vendors)} vendors and {sum(len(p) for p in products.values())} products")
        
        print("Generating module content...")
        module_content = generate_module_content(vendors, products)
        
        print(f"Writing to {OUTPUT_PATH}...")
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            f.write(module_content)
        
        print("USB IDs database updated successfully!")
        return True
    except Exception as e:
        print(f"Error updating USB IDs database: {e}")
        return False

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    update_usb_ids()
