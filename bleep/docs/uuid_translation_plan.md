# UUID Translation Functionality - Implementation Plan

## Overview

This document outlines the comprehensive plan for implementing user-interactive UUID translation functionality in BLEEP. The feature will allow users to quickly check and translate UUIDs (both 16-bit and 128-bit) into human-readable formats based on BLEEP's internal UUID databases.

## Requirements

### Functional Requirements

1. **128-bit UUID Translation**
   - Accept a 128-bit UUID in various formats (with/without dashes, uppercase/lowercase)
   - Return all potential matching translations from BLEEP's internal databases
   - Search across all UUID categories: Services, Characteristics, Descriptors, Members, SDOs, Service Classes, and custom constants

2. **16-bit UUID Translation**
   - Accept a 16-bit UUID (short form)
   - Return ALL potential matches for that 16-bit UUID across all categories
   - Since 16-bit UUIDs map to BT SIG base UUID format, show all matches where the short UUID appears

3. **User Interface**
   - CLI command: `bleep uuid-translate <UUID>` or `bleep uuid-lookup <UUID>`
   - Interactive mode integration: `uuid <UUID>` command
   - User mode integration: Menu option for UUID translation
   - Support for batch translation (multiple UUIDs)

4. **Output Format**
   - Clear, human-readable output showing:
     - UUID format (16-bit, 32-bit, or 128-bit)
     - All matches found categorized by type (Service, Characteristic, Descriptor, etc.)
     - Full 128-bit canonical form
     - Short form (if applicable)
     - Source database for each match

## Architecture

### Module Structure

```
bleep/
├── bt_ref/
│   └── uuid_translator.py      # NEW: Core UUID translation logic
├── modes/
│   └── uuid_translate.py       # NEW: CLI mode for UUID translation
└── cli.py                       # MODIFY: Add uuid-translate subcommand
```

### Core Components

#### 1. UUID Translator Module (`bt_ref/uuid_translator.py`)

**Purpose**: Centralized UUID translation engine that searches all BLEEP UUID databases.

**Key Functions**:
- `translate_uuid(uuid: str) -> Dict[str, Any]`: Main translation function
- `_normalize_uuid(uuid: str) -> Tuple[str, str, str]`: Normalize UUID and detect format
- `_search_databases(uuid: str, uuid_type: str) -> List[Dict]`: Search all UUID databases
- `_expand_16bit_to_128bit(short_uuid: str) -> str`: Convert 16-bit to 128-bit BT SIG format
- `_find_all_16bit_matches(short_uuid: str) -> List[Dict]`: Find all matches for 16-bit UUID

**Database Sources**:
- `constants.UUID_NAMES` (custom UUIDs)
- `uuids.SPEC_UUID_NAMES__SERV` (Services)
- `uuids.SPEC_UUID_NAMES__CHAR` (Characteristics)
- `uuids.SPEC_UUID_NAMES__DESC` (Descriptors)
- `uuids.SPEC_UUID_NAMES__MEMB` (Members)
- `uuids.SPEC_UUID_NAMES__SDO` (SDOs)
- `uuids.SPEC_UUID_NAMES__SERV_CLASS` (Service Classes)

#### 2. CLI Mode (`modes/uuid_translate.py`)

**Purpose**: Standalone CLI command for UUID translation.

**Features**:
- Command-line interface for quick UUID lookups
- Support for single or multiple UUIDs
- JSON output option for programmatic use
- Verbose mode for detailed information

**Usage Examples**:
```bash
# Single UUID
bleep uuid-translate 0000180a-0000-1000-8000-00805f9b34fb

# 16-bit UUID (shows all matches)
bleep uuid-translate 180a

# Multiple UUIDs
bleep uuid-translate 180a 2a00 2a01

# JSON output
bleep uuid-translate 180a --json

# Verbose mode
bleep uuid-translate 180a --verbose
```

#### 3. Interactive Mode Integration

**Purpose**: Add UUID translation to interactive and user modes.

**Implementation**:
- Add `uuid` command to `modes/interactive.py`
- Add UUID translation menu option to `modes/user.py`
- Support both standalone and device-context usage

## Implementation Details

### Phase 1: Core Translation Engine

**File**: `bleep/bt_ref/uuid_translator.py`

**Key Implementation Points**:

1. **UUID Normalization**
   ```python
   def _normalize_uuid(uuid: str) -> Tuple[str, str, str]:
       """
       Normalize UUID and determine its format.
       
       Returns:
           (normalized_uuid, uuid_format, short_form)
           - normalized_uuid: Canonical 128-bit form (no dashes, lowercase)
           - uuid_format: '16-bit', '32-bit', or '128-bit'
           - short_form: 16-bit form if applicable, None otherwise
       """
   ```

2. **Database Search**
   ```python
   def _search_databases(uuid: str, uuid_type: str) -> List[Dict]:
       """
       Search all UUID databases for matches.
       
       Returns list of matches with:
       - category: Type (Service, Characteristic, etc.)
       - uuid: Full UUID
       - name: Human-readable name
       - source: Database source
       """
   ```

3. **16-bit UUID Expansion**
   ```python
   def _expand_16bit_to_128bit(short_uuid: str) -> str:
       """
       Convert 16-bit UUID to BT SIG 128-bit format.
       Format: 0000XXXX-0000-1000-8000-00805f9b34fb
       """
   ```

4. **Main Translation Function**
   ```python
   def translate_uuid(uuid: str, include_unknown: bool = False) -> Dict[str, Any]:
       """
       Translate a UUID to human-readable format(s).
       
       Args:
           uuid: UUID in any format (16-bit, 32-bit, or 128-bit)
           include_unknown: Include "Unknown" entries in results
       
       Returns:
           Dictionary with:
           - input_uuid: Original input
           - normalized_uuid: Canonical 128-bit form
           - uuid_format: Detected format
           - short_form: 16-bit form if applicable
           - matches: List of all matches found
           - match_count: Total number of matches
       """
   ```

### Phase 2: CLI Command

**File**: `bleep/modes/uuid_translate.py`

**Implementation**:
- Parse command-line arguments
- Call translation engine
- Format output (text or JSON)
- Handle multiple UUIDs

**CLI Integration** (`cli.py`):
```python
# Add to parse_args()
uuid_parser = subparsers.add_parser("uuid-translate", 
    help="Translate UUID(s) to human-readable format",
    aliases=["uuid-lookup"])
uuid_parser.add_argument("uuids", nargs="+", help="UUID(s) to translate")
uuid_parser.add_argument("--json", action="store_true", 
    help="Output in JSON format")
uuid_parser.add_argument("--verbose", "-v", action="store_true",
    help="Show detailed information")
```

### Phase 3: Interactive Mode Integration

**File**: `bleep/modes/interactive.py`

**Add Command**:
```python
def _cmd_uuid(args: List[str]):
    """Translate UUID to human-readable format."""
    if not args:
        print("Usage: uuid <UUID> [UUID2 ...]")
        return
    
    from bleep.bt_ref.uuid_translator import translate_uuid
    
    for uuid_input in args:
        result = translate_uuid(uuid_input)
        # Format and display result
        _display_uuid_result(result)
```

**File**: `bleep/modes/user.py`

**Add Menu Option**:
```python
def uuid_translation_menu() -> UserMenu:
    """Menu for UUID translation."""
    options = [
        UserMenuOption("1", "Translate single UUID", translate_single_uuid),
        UserMenuOption("2", "Translate multiple UUIDs", translate_multiple_uuids),
        UserMenuOption("0", "Back", lambda: None),
    ]
    return UserMenu("UUID Translation", options)
```

### Phase 4: Output Formatting

**Text Output Format**:
```
UUID Translation Results
========================
Input UUID: 180a
Format: 16-bit
Canonical 128-bit: 0000180a-0000-1000-8000-00805f9b34fb

Matches Found: 1

[Service]
  0000180a-0000-1000-8000-00805f9b34fb: Device Information
  Source: SPEC_UUID_NAMES__SERV
```

**JSON Output Format**:
```json
{
  "input_uuid": "180a",
  "normalized_uuid": "0000180a-0000-1000-8000-00805f9b34fb",
  "uuid_format": "16-bit",
  "short_form": "180a",
  "matches": [
    {
      "category": "Service",
      "uuid": "0000180a-0000-1000-8000-00805f9b34fb",
      "name": "Device Information",
      "source": "SPEC_UUID_NAMES__SERV"
    }
  ],
  "match_count": 1
}
```

## Error Handling

1. **Invalid UUID Format**
   - Detect malformed UUIDs
   - Provide helpful error messages
   - Suggest correct format

2. **No Matches Found**
   - Return empty matches list
   - Optionally suggest similar UUIDs (future enhancement)

3. **Database Access Errors**
   - Gracefully handle missing database imports
   - Log warnings but continue with available databases

## Testing Strategy

### Unit Tests (`tests/test_uuid_translator.py`)

1. **UUID Normalization Tests**
   - Test various input formats
   - Verify canonical form generation
   - Test 16-bit, 32-bit, and 128-bit detection

2. **Translation Tests**
   - Test known UUIDs (Services, Characteristics)
   - Test 16-bit UUID expansion
   - Test multiple matches for 16-bit UUIDs
   - Test custom UUIDs from constants

3. **Edge Cases**
   - Invalid UUID formats
   - Non-existent UUIDs
   - Empty input
   - Special characters

### Integration Tests

1. **CLI Command Tests**
   - Test single UUID translation
   - Test multiple UUID translation
   - Test JSON output
   - Test verbose mode

2. **Interactive Mode Tests**
   - Test UUID command in interactive mode
   - Test error handling

## Documentation

### User Documentation

1. **CLI Usage Guide** (`docs/uuid_translation.md`)
   - Command syntax
   - Examples
   - Output format explanation
   - Common use cases

2. **Interactive Mode Guide**
   - How to use UUID translation in interactive mode
   - User mode menu integration

### Developer Documentation

1. **API Documentation**
   - Function signatures
   - Return value structures
   - Database source information

2. **Architecture Documentation**
   - Module structure
   - Database search order
   - Extension points

## Future Enhancements

1. **Fuzzy Matching**
   - Suggest similar UUIDs when exact match not found
   - Typo correction

2. **UUID History**
   - Cache recently translated UUIDs
   - Quick access to translation history

3. **Batch Processing**
   - Support for UUID files
   - CSV/JSON import/export

4. **Enhanced Search**
   - Search by name (reverse lookup)
   - Partial UUID matching
   - Category filtering

5. **Statistics**
   - Show UUID database sizes
   - Match statistics
   - Coverage information

## Implementation Timeline

1. **Phase 1** (Core Engine): 2-3 hours
   - Implement `uuid_translator.py`
   - Unit tests for core functionality

2. **Phase 2** (CLI Command): 1-2 hours
   - Implement `uuid_translate.py` mode
   - CLI integration
   - Output formatting

3. **Phase 3** (Interactive Integration): 1 hour
   - Add to interactive mode
   - Add to user mode menu

4. **Phase 4** (Testing & Documentation): 1-2 hours
   - Complete test suite
   - Write documentation
   - Code review

**Total Estimated Time**: 5-8 hours

## Code Quality Standards

- Follow BLEEP's existing code style and conventions
- Use type hints for all functions
- Include comprehensive docstrings
- Follow PEP 8 guidelines
- Add appropriate logging using `bleep.core.log`
- Handle errors gracefully with informative messages
- Maintain backward compatibility

## Dependencies

- No new external dependencies required
- Uses existing BLEEP modules:
  - `bleep.bt_ref.uuids`
  - `bleep.bt_ref.constants`
  - `bleep.bt_ref.utils`
  - `bleep.ble_ops.uuid_utils`

## Success Criteria

1. ✅ Successfully translate 128-bit UUIDs to human-readable format
2. ✅ Successfully find all matches for 16-bit UUIDs
3. ✅ CLI command works for single and multiple UUIDs
4. ✅ Integration with interactive and user modes
5. ✅ Comprehensive test coverage (>80%)
6. ✅ Complete documentation
7. ✅ No breaking changes to existing functionality

