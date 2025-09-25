#!/usr/bin/python3
"""Modalias parsing utilities for BLEEP.

This module provides utilities for parsing and interpreting modalias strings
based on the Linux kernel's modalias format. It centralizes modalias handling
to ensure consistent interpretation throughout the codebase.

For more information on modalias format, see:
https://wiki.archlinux.org/title/Modalias
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple, Union

# Import the USB IDs database
try:
    from bleep.bt_ref.usb_ids import parse_modalias, get_vendor_name, get_product_name
except ImportError:
    # Fallback if the USB IDs database hasn't been generated yet
    def parse_modalias(modalias: str) -> dict:
        """Fallback modalias parser when USB IDs database isn't available."""
        match = re.match(r'usb:v([0-9A-Fa-f]{4})p([0-9A-Fa-f]{4})d([0-9A-Fa-f]{4})', modalias)
        if not match:
            return {}
            
        vendor_id = match.group(1).lower()
        product_id = match.group(2).lower()
        device_id = match.group(3).lower()
        
        # Hardcoded minimal vendor list for fallback
        vendors = {
            "05ac": "Apple, Inc.",
            "1d6b": "Linux Foundation",
            "8086": "Intel Corporation",
            "1a86": "QinHeng Electronics",
            "0403": "Future Technology Devices International, Ltd",
        }
        
        return {
            'vendor_id': vendor_id,
            'vendor_name': vendors.get(vendor_id, f"Unknown (0x{vendor_id})"),
            'product_id': product_id,
            'product_name': f"Unknown (0x{product_id})",
            'device_id': device_id,
        }
    
    def get_vendor_name(vendor_id: str) -> str:
        """Fallback vendor name lookup."""
        vendor_id = vendor_id.lower().replace('0x', '')
        vendors = {
            "05ac": "Apple, Inc.",
            "1d6b": "Linux Foundation",
            "8086": "Intel Corporation",
            "1a86": "QinHeng Electronics",
            "0403": "Future Technology Devices International, Ltd",
        }
        return vendors.get(vendor_id, f"Unknown (0x{vendor_id})")
    
    def get_product_name(vendor_id: str, product_id: str) -> str:
        """Fallback product name lookup."""
        return f"Unknown (0x{product_id})"

def format_modalias_info(modalias: str) -> str:
    """Format modalias information for display.
    
    Args:
        modalias: A modalias string (e.g., 'usb:v05ACp820Ad0210')
        
    Returns:
        str: Formatted modalias information string
    """
    info = parse_modalias(modalias)
    if not info:
        return modalias  # Return the original string if parsing fails
    
    return (f"{modalias} (Vendor: {info['vendor_name']}, "
            f"Product: 0x{info['product_id'].upper()}, "
            f"Device ID: 0x{info['device_id'].upper()})")

def decode_pnp_id_vendor(vendor_id_source: int, vendor_id: int) -> str:
    """Decode vendor information from PnP ID.
    
    Args:
        vendor_id_source: Vendor ID source (1=Bluetooth SIG, 2=USB IF)
        vendor_id: Vendor ID value
        
    Returns:
        str: Vendor name
    """
    if vendor_id_source == 1:  # Bluetooth SIG
        # Import here to avoid circular dependency
        from bleep.bt_ref.bluetooth_uuids import SPEC_ID_NAMES__COMPANY_IDENTS
        vendor_key = f"0x{vendor_id:04x}"
        return SPEC_ID_NAMES__COMPANY_IDENTS.get(vendor_key, f"Unknown (0x{vendor_id:04x})")
    elif vendor_id_source == 2:  # USB IF
        return get_vendor_name(f"{vendor_id:04x}")
    else:
        return f"Unknown source {vendor_id_source} (0x{vendor_id:04x})"
