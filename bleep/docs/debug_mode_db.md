# Debug Mode Database Integration

The BLEEP debug mode now integrates with the observation database, allowing all operations performed in the debug shell to be recorded for later analysis. This document describes the database features available in debug mode and how to use them.

## Advanced Read/Write Commands

Debug mode now includes powerful commands for advanced read and write operations that fully integrate with the database:

### multiread <char_uuid|handle> [rounds=10]

Read a characteristic multiple times and track all values in the database:

```
BLEEP-DEBUG> multiread 00002a00-0000-1000-8000-00805f9b34fb 5
[*] Reading 00002a00-0000-1000-8000-00805f9b34fb 5 times...

Results for 00002a00-0000-1000-8000-00805f9b34fb (5 reads):
------------------------------------------------------------
Read 1/5: 44 65 76 69 63 65 20 4e 61 6d 65
Read 2/5: 44 65 76 69 63 65 20 4e 61 6d 65
Read 3/5: 44 65 76 69 63 65 20 4e 61 6d 65
Read 4/5: 44 65 76 69 63 65 20 4e 61 6d 65
Read 5/5: 44 65 76 69 63 65 20 4e 61 6d 65
------------------------------------------------------------
```

### multiread_all [rounds=3]

Read all readable characteristics multiple times:

```
BLEEP-DEBUG> multiread_all 2
[*] Reading all characteristics 2 times...

[*] Multi-read complete: 15 characteristics, 30 total reads
[*] Values saved to database (use 'dbexport' or 'timeline' to view)
```

### brutewrite <char_uuid|handle> <pattern> [--range start-end] [--verify]

Brute force write values to a characteristic:

```
BLEEP-DEBUG> brutewrite 00002a00-0000-1000-8000-00805f9b34fb inc --range 0-5
[*] Writing 6 values to 00002a00-0000-1000-8000-00805f9b34fb...

Results for 00002a00-0000-1000-8000-00805f9b34fb (6 writes):
------------------------------------------------------------
Write 00: OK
Write 01: OK
Write 02: OK
Write 03: OK
Write 04: OK
Write 05: OK
------------------------------------------------------------
Success rate: 6/6 (100.0%)
```

Supported patterns:
- `ascii` - ASCII printable characters
- `inc` - Incrementing bytes (0x00, 0x01, 0x02...)
- `alt` - Alternating bits (0x55, 0xAA)
- `repeat:X:N` - Repeat byte X for N bytes
- `hex:HEXSTR` - Raw hex bytes

## Overview

Debug mode now tracks:
- Device information discovered during scans and enumeration
- Services and characteristics discovered during enumeration
- Characteristic values read via the `read` command
- Values written via the `write` command
- Notifications received from subscribed characteristics

All data is stored in the same observation database used by the CLI commands, ensuring consistency across all BLEEP interfaces.

## Commands

The following database-related commands are available in debug mode:

### dbsave [on|off]

Toggle database saving on or off. When disabled, no operations will be recorded in the database.

```
BLEEP-DEBUG> dbsave
[*] Database saving enabled
BLEEP-DEBUG> dbsave off
[*] Database saving disabled
BLEEP-DEBUG> dbsave on
[*] Database saving enabled
```

### dbexport [--save]

Export all data for the currently connected device from the database. This includes device information, services, characteristics, and characteristic value history.

```
BLEEP-DEBUG> dbexport
[*] Device: 2b00042f7481c7b056c4b410d28f33cf
[*] MAC: cc:50:e3:b6:bc:a6
[*] Services: 2
[*] Characteristics: 24
[*] Characteristic history entries: 15
```

Use the `--save` flag to save the exported data to a JSON file:

```
BLEEP-DEBUG> dbexport --save
[*] Device: 2b00042f7481c7b056c4b410d28f33cf
[*] MAC: cc:50:e3:b6:bc:a6
[*] Services: 2
[*] Characteristics: 24
[*] Characteristic history entries: 15
[*] Exported data to bleep_debug_export_cc50e3b6bca6.json
```

## Database Integration Points

The following operations in debug mode now update the database:

### Enumeration

When using `enum`, `enumn`, `enump`, or `enumb` commands, the device information, services, and characteristics are saved to the database:

```
BLEEP-DEBUG> enum CC:50:E3:B6:BC:A6
[*] Connecting to CC:50:E3:B6:BC:A6...
[*] Connected
[*] Discovering services...
[*] Found 2 services
[*] Device information saved to database
```

### Read Operations

When reading characteristic values with the `read` command, the value is saved to the characteristic history table with source="read":

```
BLEEP-DEBUG> read 00002a00-0000-1000-8000-00805f9b34fb
Value (ASCII): "Device Name"
Value (HEX): 44 65 76 69 63 65 20 4e 61 6d 65
```

### Write Operations

When writing to characteristics with the `write` command, the value is saved to the characteristic history table with source="write":

```
BLEEP-DEBUG> write 00002a00-0000-1000-8000-00805f9b34fb str:NewName
[+] Successfully wrote to characteristic 00002a00-0000-1000-8000-00805f9b34fb
```

### Notifications

When subscribed to notifications with the `notify` command, received notifications are saved to the characteristic history table with source="notification":

```
BLEEP-DEBUG> notify 00002a37-0000-1000-8000-00805f9b34fb on
[+] Notifications enabled for 00002a37-0000-1000-8000-00805f9b34fb
```

## Schema Changes

The `char_history` table has been updated to include a `source` field that indicates how the value was obtained:

- `read`: Value read using the `read` command
- `write`: Value written using the `write` command
- `notification`: Value received via notification
- `unknown`: Source not specified (default for backward compatibility)

## Integration with CLI Commands

All data recorded in debug mode can be accessed using the standard CLI commands:

```bash
# List all devices discovered in debug mode
bleep db list

# Show details for a specific device
bleep db show <MAC>

# Export all data for a device
bleep db export <MAC>

# View characteristic value history
bleep db timeline <MAC>
```

## Troubleshooting

If database operations fail, check the following:

1. Ensure the database file exists and is writable
2. Verify that the `observations` module is properly imported
3. Check that database saving is enabled (`dbsave on`)
4. Look for error messages in the debug output

If you encounter persistent issues, you can disable database integration with `dbsave off` and continue using debug mode without database tracking.
