"""UUID utility functions for Bluetooth operations."""

from typing import Set, Optional
import re
import logging

# Standard BT SIG Base UUID
BT_SIG_BASE_UUID = "00000000-0000-1000-8000-00805f9b34fb"


def identify_uuid(uuid: str) -> Set[str]:
    """Identify and normalize a UUID, handling various formats.
    
    This function takes a UUID string in any format (16-bit, 32-bit, or 128-bit)
    and returns a set of possible canonical representations to match against.
    It handles both BT SIG standard UUIDs and custom UUIDs.
    
    Parameters
    ----------
    uuid : str
        The UUID to identify, in any format
        
    Returns
    -------
    Set[str]
        A set of possible canonical representations of the UUID
    """
    # Normalize input: remove dashes and convert to lowercase
    target = uuid.replace("-", "").lower()
    canonical_targets: set[str] = set()
    
    # Extract the short UUID (16-bit) if this is a full UUID
    short_uuid = None
    if len(target) == 32:  # Full 128-bit UUID
        # Check if this follows BT SIG format
        bt_sig_base = BT_SIG_BASE_UUID.replace("-", "").lower()
        if target[8:] == bt_sig_base[8:]:
            # This is a BT SIG UUID, extract the short form
            short_uuid = target[4:8]
        else:
            # This is a custom UUID, just add it as is
            canonical_targets.add(target)
    
    # Handle short UUIDs (16-bit)
    elif len(target) == 4:
        short_uuid = target
        
        # Add the BT SIG canonical form
        canonical = f"0000{target}00001000800000805f9b34fb"
        canonical_targets.add(canonical)
    
    # Handle 32-bit UUIDs
    elif len(target) == 8:
        # Add the BT SIG canonical form
        canonical = f"{target}00001000800000805f9b34fb"
        canonical_targets.add(canonical)
    
    # Handle other formats by cleaning and checking length
    else:
        # Extract just the UUID part without dashes
        clean_target = ''.join(c for c in target if c.isalnum()).lower()
        if len(clean_target) == 32:  # Full 128-bit
            canonical_targets.add(clean_target)
            
            # Check if this follows BT SIG format
            bt_sig_base = BT_SIG_BASE_UUID.replace("-", "").lower()
            if clean_target[8:] == bt_sig_base[8:]:
                short_uuid = clean_target[4:8]
        
        elif len(clean_target) == 4:  # 16-bit
            short_uuid = clean_target
            canonical = f"0000{clean_target}00001000800000805f9b34fb"
            canonical_targets.add(canonical)
        
        elif len(clean_target) == 8:  # 32-bit
            canonical = f"{clean_target}00001000800000805f9b34fb"
            canonical_targets.add(canonical)
    
    # Add the raw target for direct comparison
    canonical_targets.add(target.ljust(32, " "))  # pad to avoid length mismatch
    
    # If we extracted a short UUID, add it for partial matching
    if short_uuid:
        canonical_targets.add(short_uuid)
    
    return canonical_targets


def match_uuid(target_uuid: str, available_uuids: list[str]) -> Optional[str]:
    """Match a target UUID against a list of available UUIDs.
    
    This function tries to find the best match for the target UUID
    in the list of available UUIDs.
    
    Parameters
    ----------
    target_uuid : str
        The UUID to match
    available_uuids : list[str]
        List of available UUIDs to match against
        
    Returns
    -------
    Optional[str]
        The matched UUID if found, None otherwise
    """
    # Get all possible canonical forms of the target UUID
    target_forms = identify_uuid(target_uuid)
    
    # Normalize all available UUIDs
    normalized_uuids = {uuid.replace("-", "").lower(): uuid for uuid in available_uuids}
    
    # First try exact matches
    for form in target_forms:
        if form in normalized_uuids:
            return normalized_uuids[form]
    
    # Then try partial matches (for short UUIDs)
    for form in target_forms:
        if len(form) == 4:  # This is a short UUID
            for uuid in normalized_uuids:
                # Check if the short UUID is contained in the full UUID
                if uuid[4:8] == form:
                    return normalized_uuids[uuid]
    
    # No match found
    return None 