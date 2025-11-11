# UUID Translation Functionality

## Overview

BLEEP provides comprehensive UUID translation functionality that allows users to quickly translate UUIDs (16-bit, 32-bit, or 128-bit) into human-readable formats based on BLEEP's internal UUID databases.

## Features

- **Multiple UUID Format Support**: Handles 16-bit, 32-bit, and 128-bit UUIDs
- **Comprehensive Database Search**: Searches across all BLEEP UUID databases:
  - Services (SPEC_UUID_NAMES__SERV)
  - Characteristics (SPEC_UUID_NAMES__CHAR)
  - Descriptors (SPEC_UUID_NAMES__DESC)
  - Members (SPEC_UUID_NAMES__MEMB)
  - SDOs (SPEC_UUID_NAMES__SDO)
  - Service Classes (SPEC_UUID_NAMES__SERV_CLASS)
  - Custom UUIDs (constants.UUID_NAMES)
- **16-bit UUID Expansion**: Automatically finds all matches for 16-bit UUIDs
- **Flexible Input Formats**: Accepts UUIDs with or without dashes, case-insensitive
- **Multiple Output Formats**: Human-readable text or JSON

## Usage

### CLI Command

The primary way to use UUID translation is through the `uuid-translate` command:

```bash
# Single UUID (16-bit)
bleep uuid-translate 180a

# Single UUID (128-bit)
bleep uuid-translate 0000180a-0000-1000-8000-00805f9b34fb

# Multiple UUIDs
bleep uuid-translate 180a 2a00 2a01

# JSON output
bleep uuid-translate 180a --json

# Verbose mode (shows source databases)
bleep uuid-translate 180a --verbose
```

**Aliases**: The command can also be invoked as `uuid-lookup`:

```bash
bleep uuid-lookup 180a
```

### Interactive Mode

In BLEEP's interactive mode, use the `uuid` command:

```
BLEEP> uuid 180a
BLEEP> uuid 0000180a-0000-1000-8000-00805f9b34fb
BLEEP> uuid 180a 2a00 2a01
```

### User Mode

In BLEEP's user-friendly menu mode, select option "5" (Translate UUID) from the main menu.

## Input Formats

The UUID translator accepts UUIDs in various formats:

- **16-bit**: `180a`, `0x180a`, `0x180A`
- **32-bit**: `0000180a`
- **128-bit**: `0000180a-0000-1000-8000-00805f9b34fb` (with dashes)
- **128-bit**: `0000180a00001000800000805f9b34fb` (without dashes)

All formats are case-insensitive.

## Output Format

### Text Output

```
UUID Translation Results
==================================================
Input UUID: 180a
Format: 16-bit
Canonical 128-bit: 0000180a-0000-1000-8000-00805f9b34fb
16-bit form: 180a
BT SIG Format: Yes

Matches Found: 1

[Service]
  0000180a-0000-1000-8000-00805f9b34fb: Device Information
```

### JSON Output

```json
{
  "input_uuid": "180a",
  "normalized_uuid": "0000180a00001000800000805f9b34fb",
  "uuid_format": "16-bit",
  "short_form": "180a",
  "matches": [
    {
      "category": "Service",
      "uuid": "0000180a00001000800000805f9b34fb",
      "name": "Device Information",
      "source": "Service"
    }
  ],
  "match_count": 1,
  "is_bt_sig_format": true
}
```

## Examples

### Example 1: 16-bit Service UUID

```bash
$ bleep uuid-translate 180a

UUID Translation Results
==================================================
Input UUID: 180a
Format: 16-bit
Canonical 128-bit: 0000180a-0000-1000-8000-00805f9b34fb
16-bit form: 180a
BT SIG Format: Yes

Matches Found: 1

[Service]
  0000180a-0000-1000-8000-00805f9b34fb: Device Information
```

### Example 2: 16-bit Characteristic UUID

```bash
$ bleep uuid-translate 2a00

UUID Translation Results
==================================================
Input UUID: 2a00
Format: 16-bit
Canonical 128-bit: 00002a00-0000-1000-8000-00805f9b34fb
16-bit form: 2a00
BT SIG Format: Yes

Matches Found: 1

[Characteristic]
  00002a00-0000-1000-8000-00805f9b34fb: Device Name
```

### Example 3: Multiple UUIDs

```bash
$ bleep uuid-translate 180a 2a00 2a01

UUID Translation Results
==================================================
Input UUID: 180a
Format: 16-bit
Canonical 128-bit: 0000180a-0000-1000-8000-00805f9b34fb
16-bit form: 180a
BT SIG Format: Yes

Matches Found: 1

[Service]
  0000180a-0000-1000-8000-00805f9b34fb: Device Information

--------------------------------------------------

UUID Translation Results
==================================================
Input UUID: 2a00
Format: 16-bit
Canonical 128-bit: 00002a00-0000-1000-8000-00805f9b34fb
16-bit form: 2a00
BT SIG Format: Yes

Matches Found: 1

[Characteristic]
  00002a00-0000-1000-8000-00805f9b34fb: Device Name

--------------------------------------------------

UUID Translation Results
==================================================
Input UUID: 2a01
Format: 16-bit
Canonical 128-bit: 00002a01-0000-1000-8000-00805f9b34fb
16-bit form: 2a01
BT SIG Format: Yes

Matches Found: 1

[Characteristic]
  00002a01-0000-1000-8000-00805f9b34fb: Appearance
```

### Example 4: Custom 128-bit UUID

```bash
$ bleep uuid-translate e95d93b0-251d-470a-a062-fa1922dfa9a8

UUID Translation Results
==================================================
Input UUID: e95d93b0-251d-470a-a062-fa1922dfa9a8
Format: 128-bit
Canonical 128-bit: e95d93b0251d470aa062fa1922dfa9a8
BT SIG Format: No

Matches Found: 1

[Custom]
  e95d93b0251d470aa062fa1922dfa9a8: DFU Control Service
```

## Programmatic Usage

The UUID translator can also be used programmatically:

```python
from bleep.bt_ref.uuid_translator import translate_uuid

# Translate a UUID
result = translate_uuid("180a")

# Access results
print(f"Format: {result['uuid_format']}")
print(f"Matches: {result['match_count']}")
for match in result['matches']:
    print(f"  {match['category']}: {match['name']}")
```

## Architecture

The UUID translation system is designed with modularity and extensibility in mind:

- **Format Handlers**: Pluggable system for handling different UUID formats
- **Database Abstraction**: Unified interface to all UUID databases
- **Easy Extension**: Simple to add support for new UUID formats or databases

### Adding Custom Format Handlers

To add support for non-standard UUID formats, create a custom handler:

```python
from bleep.bt_ref.uuid_translator import UUIDFormatHandler, UUIDFormat

class CustomFormatHandler(UUIDFormatHandler):
    def can_handle(self, uuid_input: str) -> bool:
        # Check if this handler can process the UUID
        return uuid_input.startswith("custom:")
    
    def normalize(self, uuid_input: str):
        # Normalize the UUID
        # Return (normalized_uuid, uuid_format, short_form)
        pass
    
    def expand_short(self, short_uuid: str) -> str:
        # Expand short UUID to full format
        pass

# Register the handler
from bleep.bt_ref.uuid_translator import get_translator
translator = get_translator()
translator.register_format_handler(CustomFormatHandler())
```

## Troubleshooting

### No Matches Found

If no matches are found for a UUID, it may be:
- A custom/vendor-specific UUID not in the standard databases
- A malformed UUID (check the input format)
- A UUID from a newer Bluetooth specification (update BLEEP's UUID databases)

### Invalid UUID Format

If you receive an "Invalid UUID format" error:
- Ensure the UUID contains only hexadecimal characters
- Check that the length matches the expected format (4, 8, or 32 hex digits)
- Remove any non-hexadecimal characters

## Related Documentation

- [UUID Translation Plan](uuid_translation_plan.md) - Detailed implementation plan
- [BLEEP CLI Usage](cli_usage.md) - General CLI documentation
- [Interactive Mode](user_mode.md) - Interactive mode documentation

## Database Sources

BLEEP's UUID databases are automatically updated from the Bluetooth SIG's Assigned Numbers repository. To update the databases manually:

```bash
python -m bleep.bt_ref.update_ble_uuids
```

This will fetch the latest UUID definitions from the Bluetooth SIG and regenerate the internal databases.

