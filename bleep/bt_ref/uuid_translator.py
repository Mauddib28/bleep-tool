"""
UUID Translation Module for BLEEP.

This module provides comprehensive UUID translation functionality, allowing users
to translate UUIDs (16-bit, 32-bit, or 128-bit) into human-readable formats
based on BLEEP's internal UUID databases.

The module is designed with modularity and extensibility in mind, making it easy
to add support for new UUID formats or database sources.
"""

from typing import Dict, List, Optional, Tuple, Any, Set
import re
from enum import Enum

from bleep.core.log import print_and_log, LOG__DEBUG

# Import UUID databases
try:
    from . import constants
    from . import uuids
except (ImportError, SyntaxError):
    # Fallback to stubs if databases are not available
    constants = None
    uuids = None


class UUIDFormat(Enum):
    """Enumeration of supported UUID formats."""
    SHORT_16BIT = "16-bit"
    MEDIUM_32BIT = "32-bit"
    FULL_128BIT = "128-bit"
    UNKNOWN = "unknown"


class UUIDCategory(Enum):
    """Enumeration of UUID categories/databases."""
    CUSTOM = "Custom"
    SERVICE = "Service"
    CHARACTERISTIC = "Characteristic"
    DESCRIPTOR = "Descriptor"
    MEMBER = "Member"
    SDO = "SDO"
    SERVICE_CLASS = "Service Class"


# Standard BT SIG Base UUID
BT_SIG_BASE_UUID = "00000000-0000-1000-8000-00805f9b34fb"
BT_SIG_BASE_UUID_NODASH = BT_SIG_BASE_UUID.replace("-", "").lower()


class UUIDFormatHandler:
    """
    Base class for UUID format handlers.
    
    This abstract base class defines the interface for handling different UUID
    formats. Subclasses can be registered to handle specific UUID formats or
    patterns, enabling easy extension for non-standard formats.
    """
    
    def can_handle(self, uuid_input: str) -> bool:
        """
        Check if this handler can process the given UUID input.
        
        Args:
            uuid_input: The UUID string to check
            
        Returns:
            True if this handler can process the UUID, False otherwise
        """
        raise NotImplementedError
    
    def normalize(self, uuid_input: str) -> Tuple[str, UUIDFormat, Optional[str]]:
        """
        Normalize the UUID and determine its format.
        
        Args:
            uuid_input: The UUID string to normalize
            
        Returns:
            Tuple of (normalized_uuid, uuid_format, short_form)
            - normalized_uuid: Canonical 128-bit form (no dashes, lowercase)
            - uuid_format: Detected format (UUIDFormat enum)
            - short_form: 16-bit form if applicable, None otherwise
        """
        raise NotImplementedError
    
    def expand_short(self, short_uuid: str) -> str:
        """
        Expand a short UUID to full 128-bit format.
        
        Args:
            short_uuid: 16-bit or 32-bit UUID string
            
        Returns:
            Full 128-bit UUID string (no dashes, lowercase)
        """
        raise NotImplementedError


class StandardUUIDHandler(UUIDFormatHandler):
    """
    Handler for standard Bluetooth UUID formats.
    
    Handles:
    - 16-bit UUIDs (e.g., "180a", "0x180a")
    - 32-bit UUIDs (e.g., "0000180a")
    - 128-bit UUIDs in standard format (with or without dashes)
    - BT SIG base UUID format
    """
    
    # Pattern for hex digits only
    HEX_PATTERN = re.compile(r'^[0-9a-fA-F]+$')
    
    def can_handle(self, uuid_input: str) -> bool:
        """Standard handler can handle most common formats."""
        return True  # Default handler
    
    def normalize(self, uuid_input: str) -> Tuple[str, UUIDFormat, Optional[str]]:
        """
        Normalize UUID and detect format.
        
        Supports:
        - 16-bit: "180a", "0x180a", "0x180A"
        - 32-bit: "0000180a"
        - 128-bit: "0000180a-0000-1000-8000-00805f9b34fb" (with/without dashes)
        """
        # Remove common prefixes and whitespace
        cleaned = uuid_input.strip().lower()
        
        # Handle hex prefix
        if cleaned.startswith('0x'):
            cleaned = cleaned[2:]
        
        # Remove dashes for processing
        cleaned_no_dash = cleaned.replace("-", "")
        
        # Remove any non-hex characters (for robustness)
        hex_only = ''.join(c for c in cleaned_no_dash if c in '0123456789abcdef')
        
        if not self.HEX_PATTERN.match(hex_only):
            # Invalid format
            return (cleaned_no_dash, UUIDFormat.UNKNOWN, None)
        
        length = len(hex_only)
        
        if length == 4:  # 16-bit UUID
            short_form = hex_only
            normalized = self.expand_short(short_form)
            return (normalized, UUIDFormat.SHORT_16BIT, short_form)
        
        elif length == 8:  # 32-bit UUID
            short_form = hex_only[4:8]  # Extract last 4 hex digits
            normalized = self.expand_short(hex_only)
            return (normalized, UUIDFormat.MEDIUM_32BIT, short_form)
        
        elif length == 32:  # 128-bit UUID
            normalized = hex_only
            # Check if it follows BT SIG format
            if normalized[8:] == BT_SIG_BASE_UUID_NODASH[8:]:
                # Extract 16-bit form from positions 4-8
                short_form = normalized[4:8]
                return (normalized, UUIDFormat.FULL_128BIT, short_form)
            else:
                # Custom 128-bit UUID
                return (normalized, UUIDFormat.FULL_128BIT, None)
        
        else:
            # Unknown format
            return (hex_only, UUIDFormat.UNKNOWN, None)
    
    def expand_short(self, short_uuid: str) -> str:
        """
        Expand short UUID to BT SIG 128-bit format.
        
        Args:
            short_uuid: 16-bit (4 hex digits) or 32-bit (8 hex digits) UUID
            
        Returns:
            Full 128-bit UUID: 0000XXXX-0000-1000-8000-00805f9b34fb format
        """
        if len(short_uuid) == 4:
            # 16-bit: pad with zeros at the beginning
            return f"0000{short_uuid}{BT_SIG_BASE_UUID_NODASH[8:]}"
        elif len(short_uuid) == 8:
            # 32-bit: use as-is
            return f"{short_uuid}{BT_SIG_BASE_UUID_NODASH[8:]}"
        else:
            raise ValueError(f"Invalid short UUID length: {len(short_uuid)}")


class UUIDDatabase:
    """
    Container for UUID database sources.
    
    This class provides a unified interface to all UUID databases in BLEEP,
    making it easy to search across all sources and add new databases.
    """
    
    def __init__(self):
        """Initialize database sources."""
        self._databases: Dict[UUIDCategory, Dict[str, str]] = {}
        self._load_databases()
    
    def _load_databases(self) -> None:
        """Load all available UUID databases."""
        # Custom UUIDs from constants
        if constants and hasattr(constants, 'UUID_NAMES'):
            self._databases[UUIDCategory.CUSTOM] = constants.UUID_NAMES
        
        # Specification UUIDs from uuids module
        if uuids:
            if hasattr(uuids, 'SPEC_UUID_NAMES__SERV'):
                self._databases[UUIDCategory.SERVICE] = uuids.SPEC_UUID_NAMES__SERV
            
            if hasattr(uuids, 'SPEC_UUID_NAMES__CHAR'):
                self._databases[UUIDCategory.CHARACTERISTIC] = uuids.SPEC_UUID_NAMES__CHAR
            
            if hasattr(uuids, 'SPEC_UUID_NAMES__DESC'):
                self._databases[UUIDCategory.DESCRIPTOR] = uuids.SPEC_UUID_NAMES__DESC
            
            if hasattr(uuids, 'SPEC_UUID_NAMES__MEMB'):
                self._databases[UUIDCategory.MEMBER] = uuids.SPEC_UUID_NAMES__MEMB
            
            if hasattr(uuids, 'SPEC_UUID_NAMES__SDO'):
                self._databases[UUIDCategory.SDO] = uuids.SPEC_UUID_NAMES__SDO
            
            if hasattr(uuids, 'SPEC_UUID_NAMES__SERV_CLASS'):
                self._databases[UUIDCategory.SERVICE_CLASS] = uuids.SPEC_UUID_NAMES__SERV_CLASS
    
    def search(self, uuid: str, short_form: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search all databases for UUID matches.
        
        Args:
            uuid: Normalized 128-bit UUID (no dashes, lowercase)
            short_form: Optional 16-bit UUID form for expanded search
            
        Returns:
            List of match dictionaries, each containing:
            - category: UUIDCategory enum
            - uuid: Full UUID string
            - name: Human-readable name
            - source: Database source name
        """
        matches: List[Dict[str, Any]] = []
        uuid_normalized = uuid.replace("-", "").lower()
        
        # Helper to format UUID with dashes (as stored in databases)
        def format_with_dashes(uuid_no_dash: str) -> str:
            """Format UUID with dashes: XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"""
            if len(uuid_no_dash) == 32:
                return f"{uuid_no_dash[0:8]}-{uuid_no_dash[8:12]}-{uuid_no_dash[12:16]}-{uuid_no_dash[16:20]}-{uuid_no_dash[20:32]}"
            return uuid_no_dash
        
        # Search each database
        for category, db_dict in self._databases.items():
            # Try matching with dashes (as stored in databases)
            uuid_with_dashes = format_with_dashes(uuid_normalized)
            if uuid_with_dashes in db_dict:
                matches.append({
                    "category": category,
                    "uuid": uuid_with_dashes,
                    "name": db_dict[uuid_with_dashes],
                    "source": category.value,
                })
            
            # Also try without dashes (for robustness)
            elif uuid_normalized in db_dict:
                matches.append({
                    "category": category,
                    "uuid": uuid_normalized,
                    "name": db_dict[uuid_normalized],
                    "source": category.value,
                })
            
            # If we have a short form, search for matches in BT SIG format
            if short_form:
                # Construct BT SIG format UUID for this short form (with dashes)
                bt_sig_uuid_no_dash = f"0000{short_form}{BT_SIG_BASE_UUID_NODASH[8:]}"
                bt_sig_uuid_with_dashes = format_with_dashes(bt_sig_uuid_no_dash)
                
                if bt_sig_uuid_with_dashes in db_dict:
                    matches.append({
                        "category": category,
                        "uuid": bt_sig_uuid_with_dashes,
                        "name": db_dict[bt_sig_uuid_with_dashes],
                        "source": category.value,
                    })
                elif bt_sig_uuid_no_dash in db_dict:
                    matches.append({
                        "category": category,
                        "uuid": bt_sig_uuid_no_dash,
                        "name": db_dict[bt_sig_uuid_no_dash],
                        "source": category.value,
                    })
        
        return matches
    
    def search_all_16bit_matches(self, short_uuid: str) -> List[Dict[str, Any]]:
        """
        Find all matches for a 16-bit UUID across all databases.
        
        This is useful when a 16-bit UUID could map to multiple categories
        (e.g., a UUID that exists as both a Service and Characteristic).
        
        Args:
            short_uuid: 16-bit UUID (4 hex digits)
            
        Returns:
            List of all matches found across all databases
        """
        # Expand to BT SIG format
        expanded_uuid = f"0000{short_uuid}{BT_SIG_BASE_UUID_NODASH[8:]}"
        return self.search(expanded_uuid, short_uuid)


class UUIDTranslator:
    """
    Main UUID translation engine.
    
    This class provides the primary interface for UUID translation, using
    format handlers and database sources to translate UUIDs into human-readable
    formats.
    """
    
    def __init__(self):
        """Initialize translator with default handlers and databases."""
        self._format_handlers: List[UUIDFormatHandler] = [StandardUUIDHandler()]
        self._database = UUIDDatabase()
    
    def register_format_handler(self, handler: UUIDFormatHandler, priority: int = 0) -> None:
        """
        Register a custom UUID format handler.
        
        This allows extending the translator to support non-standard UUID formats.
        Handlers are checked in registration order (with priority support for
        future enhancement).
        
        Args:
            handler: UUIDFormatHandler instance
            priority: Priority level (higher = checked first, reserved for future use)
        """
        # For now, insert at beginning (highest priority)
        # Future: implement priority-based ordering
        self._format_handlers.insert(0, handler)
    
    def _normalize_uuid(self, uuid_input: str) -> Tuple[str, UUIDFormat, Optional[str]]:
        """
        Normalize UUID using registered format handlers.
        
        Args:
            uuid_input: UUID string in any supported format
            
        Returns:
            Tuple of (normalized_uuid, uuid_format, short_form)
        """
        # Try each handler in order
        for handler in self._format_handlers:
            if handler.can_handle(uuid_input):
                try:
                    result = handler.normalize(uuid_input)
                    if result[1] != UUIDFormat.UNKNOWN:
                        return result
                except Exception as e:
                    print_and_log(
                        f"UUID normalization error with handler {handler.__class__.__name__}: {e}",
                        LOG__DEBUG
                    )
                    continue
        
        # If no handler succeeded, return unknown format
        cleaned = uuid_input.replace("-", "").lower()
        return (cleaned, UUIDFormat.UNKNOWN, None)
    
    def translate(self, uuid_input: str, include_unknown: bool = False) -> Dict[str, Any]:
        """
        Translate a UUID to human-readable format(s).
        
        This is the main translation function that:
        1. Normalizes the input UUID
        2. Searches all databases for matches
        3. Returns comprehensive results
        
        Args:
            uuid_input: UUID in any format (16-bit, 32-bit, or 128-bit)
            include_unknown: If True, include "Unknown" entries in results
            
        Returns:
            Dictionary containing:
            - input_uuid: Original input string
            - normalized_uuid: Canonical 128-bit form
            - uuid_format: Detected format string
            - short_form: 16-bit form if applicable, None otherwise
            - matches: List of all matches found
            - match_count: Total number of matches
            - is_bt_sig_format: Whether UUID follows BT SIG base format
        """
        # Normalize UUID
        normalized_uuid, uuid_format, short_form = self._normalize_uuid(uuid_input)
        
        # Determine if this is BT SIG format
        is_bt_sig_format = (
            uuid_format in (UUIDFormat.SHORT_16BIT, UUIDFormat.MEDIUM_32BIT) or
            (uuid_format == UUIDFormat.FULL_128BIT and 
             normalized_uuid[8:] == BT_SIG_BASE_UUID_NODASH[8:])
        )
        
        # Search databases
        if uuid_format == UUIDFormat.SHORT_16BIT and short_form:
            # For 16-bit UUIDs, find all matches
            matches = self._database.search_all_16bit_matches(short_form)
        else:
            # For 32-bit and 128-bit UUIDs, search directly
            matches = self._database.search(normalized_uuid, short_form)
        
        # Filter out "Unknown" entries unless requested
        if not include_unknown:
            matches = [m for m in matches if m.get("name", "").lower() != "unknown"]
        
        # Format result
        result = {
            "input_uuid": uuid_input,
            "normalized_uuid": normalized_uuid,
            "uuid_format": uuid_format.value,
            "short_form": short_form,
            "matches": matches,
            "match_count": len(matches),
            "is_bt_sig_format": is_bt_sig_format,
        }
        
        return result


# Global translator instance for convenience
_translator_instance: Optional[UUIDTranslator] = None


def get_translator() -> UUIDTranslator:
    """
    Get the global UUID translator instance.
    
    Returns:
        Singleton UUIDTranslator instance
    """
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = UUIDTranslator()
    return _translator_instance


def translate_uuid(uuid_input: str, include_unknown: bool = False) -> Dict[str, Any]:
    """
    Convenience function to translate a UUID.
    
    This is the primary public API for UUID translation.
    
    Args:
        uuid_input: UUID in any format (16-bit, 32-bit, or 128-bit)
        include_unknown: If True, include "Unknown" entries in results
        
    Returns:
        Dictionary containing translation results (see UUIDTranslator.translate)
        
    Example:
        >>> result = translate_uuid("180a")
        >>> print(result["matches"][0]["name"])
        Device Information
    """
    translator = get_translator()
    return translator.translate(uuid_input, include_unknown)

