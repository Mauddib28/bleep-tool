# Assets of Interest (AOI) Mode

The AOI mode is a powerful feature in BLEEP for systematically analyzing multiple Bluetooth devices of interest. This mode provides comprehensive functionality for:

1. **Batch Scanning**: Process lists of target MAC addresses from JSON files
2. **Security Analysis**: Identify security concerns and unusual characteristics
3. **Report Generation**: Create detailed security reports in multiple formats
4. **Persistent Storage**: Store device data for offline analysis and tracking
5. **Data Export**: Export device information for external processing

## Basic Usage

```bash
# Scan devices from a JSON file
python -m bleep.cli aoi targets.json

# Scan devices from multiple files
python -m bleep.cli aoi targets1.json targets2.json

# Use the --file option for a single file
python -m bleep.cli aoi --file targets.json

# Adjust delay between device scans
python -m bleep.cli aoi targets.json --delay 5.0
```

## Advanced Usage

The AOI mode supports several subcommands for different operations. When using the CLI without a subcommand, it defaults to the `scan` operation.

### Database Integration

AOI mode now integrates with BLEEP's observation database, providing a unified storage system for device data and analysis results:

```bash
# Use database for storage when scanning (no files)
python -m bleep.cli aoi scan targets.json --db-only

# Analyze a device and store results in database
python -m bleep.cli aoi analyze --address 00:11:22:33:44:55

# Disable database for a specific operation
python -m bleep.cli aoi analyze --address 00:11:22:33:44:55 --no-db

# Generate report using database data
python -m bleep.cli aoi report --address 00:11:22:33:44:55

# List devices from database
python -m bleep.cli aoi list
```

Database integration is enabled by default for all operations. Use the `--no-db` flag to disable it when needed.

### Scan Subcommand

```bash
# Explicitly use the scan subcommand
python -m bleep.cli aoi scan targets.json --delay 5.0
```

The scan operation:
- Reads MAC addresses from the specified JSON files
- Connects to each device sequentially
- Enumerates the GATT database (services, characteristics, descriptors)
- Stores the collected data in the AOI database (~/.bleep/aoi/)
- Waits for the specified delay between devices (default: 4.0 seconds)

**Scan flags:**

- `--analyze` — after scanning each target, immediately run the security
  analysis on it in the same pass (equivalent to a per-device follow-up
  `aoi analyze`)
- `--deep` — attempt pairing + post-pair re-enumeration (invasive; see the
  pairing note under [Analyze Subcommand](#analyze-subcommand))
- `--timeout SECS` — per-device timeout (default 30s); bounds the LE
  connect/service-resolution phase as well as SDP/pairing
- `--refresh-scan SECS` — before enumerating, run a `SECS`-second discovery scan
  to repopulate the adapter cache (helps stale RPAs left over from an earlier
  survey); `0` (default) disables it
- `--adapter hciN` — Bluetooth controller used for connect / enumerate / pair
  (default `hci0`). Honoured by `scan`, `--refresh-scan`, `--deep` pairing, and
  `--then-aoi` from survey. A missing or not-ready controller fails with
  `require_adapter` rather than silently falling back to `hci0`.
- `--connectionless` — use connectionless SDP (`l2ping` + `sdptool`) for Classic
  enumeration instead of opening a full BR/EDR connection
- `--db-only` — store results only in the observation database, skipping the
  file-based `~/.bleep/aoi/` directory
- `--no-db` — disable database integration entirely (file storage only)

```bash
# Scan, then analyze each device inline, with a longer per-device timeout
python -m bleep.cli aoi scan targets.json --analyze --timeout 60

# Repopulate the adapter cache with a 15s discovery scan before enumerating
python -m bleep.cli aoi scan targets.json --refresh-scan 15

# Enumerate via a second controller (e.g. after survey --enumerator hci1)
python -m bleep.cli aoi scan targets.json --adapter hci1

# Use connectionless SDP for Classic targets
python -m bleep.cli aoi scan targets.json --connectionless
```

### Analyze Subcommand

```bash
# Analyze a specific device
python -m bleep.cli aoi analyze --address 00:11:22:33:44:55 --deep
python -m bleep.cli aoi analyze --address 00:11:22:33:44:55 --timeout 60
```

The analyze operation performs comprehensive security analysis:
- **Security Concerns**: Identifies authentication-related characteristics with weak permissions
- **Unusual Characteristics**: Detects characteristics with unusual properties or values
- **Notable Services**: Highlights important services (GAP, GATT, OTA, authentication)
- **Permission Maps**: Analyzes read/write permissions across the device
- **Landmine Maps**: Identifies potentially dangerous operations
- **Recommendations**: Generates security recommendations based on findings

The `--deep` flag enables more thorough analysis, and `--timeout` adjusts the analysis timeout.

> **Pairing side effect (deep mode only).** Pairing is attempted **only** when
> `--deep` is supplied. A deep scan/analyze performs a real bond and mutates
> adapter/device bonding state; a plain (non-deep) scan is non-invasive and
> never pairs. Authentication-related findings surfaced by enumeration are still
> recorded as annotations without pairing.

### List Subcommand

```bash
# List all saved AOI devices
python -m bleep.cli aoi list
```

The list operation:
- Shows all devices stored in the AOI database
- Displays MAC address, device name, and analysis status
- Provides a numbered index for easy reference

By default, seeded/test-fixture MACs (e.g. `AA:BB:CC:DD:EE:*`) are **excluded**
from `list` and `report` output. Pass `--include-synthetic` to include them:

```bash
python -m bleep.cli aoi list --include-synthetic
```

### Report Subcommand

```bash
# Generate a report for a single device
python -m bleep.cli aoi report --address 00:11:22:33:44:55 --format markdown
python -m bleep.cli aoi report --address 00:11:22:33:44:55 --format json --output device_report.json

# Generate an aggregate report for ALL analyzed devices
python -m bleep.cli aoi report --all --format markdown
python -m bleep.cli aoi report --all --format json -o aggregate.json
```

The report operation generates detailed security reports:
- **Markdown Format**: Human-readable report with sections for security concerns, unusual characteristics, and recommendations
- **JSON Format**: Machine-readable report for integration with other tools
- **Text Format**: Simple text report for console output
- **Aggregate Mode** (`--all`): Combines all AoI-analyzed devices into a single report with a summary table and per-device sections. Synthetic/test MACs are excluded unless `--include-synthetic` is passed.
- Reports can be saved to a path via `--output`, or auto-generated under the AoI `reports/` directory (see [Data Storage](#data-storage))

### Export Subcommand

```bash
# Export a specific device's data
python -m bleep.cli aoi export --address 00:11:22:33:44:55 --output device_data.json

# Export all devices' data
python -m bleep.cli aoi export --output export_dir

# Export without using the database
python -m bleep.cli aoi export --address 00:11:22:33:44:55 --output device_data.json --no-db
```

The export operation:
- Exports raw device data in JSON format
- Can export a single device or all devices
- Preserves all collected information including services, characteristics, and analysis results
- Useful for sharing data or processing with external tools

### Database Subcommand

```bash
# Import AoI data from files to database
python -m bleep.cli aoi db import [--address 00:11:22:33:44:55]

# Export AoI data from database to files
python -m bleep.cli aoi db export [--address 00:11:22:33:44:55]

# Synchronize database and files (bidirectional)
python -m bleep.cli aoi db sync
```

The database operations:
- **Import**: Loads data from JSON files into the observation database
- **Export**: Saves database data to JSON files
- **Sync**: Performs bidirectional synchronization between database and files
- Can operate on a single device (with `--address`) or all devices
- Creates a unified storage system for device data and analysis results

## JSON File Format

The AOI mode accepts input JSON files in several formats:

### 1. Simple Array of MAC Addresses

```json
[
  "00:11:22:33:44:55",
  "AA:BB:CC:DD:EE:FF",
  "11:22:33:44:55:66"
]
```

### 2. Array of Device Objects

```json
[
  {
    "address": "00:11:22:33:44:55",
    "name": "Device 1",
    "notes": "Test device"
  },
  {
    "address": "AA:BB:CC:DD:EE:FF",
    "name": "Device 2"
  }
]
```

### 3. Nested Dictionary Structure

The AOI module can extract MAC addresses from nested dictionary structures using recursive traversal.

## Data Storage

AOI data is stored persistently in the following location:

```
~/.bleep/aoi/
```

Files are named using the pattern: `{normalized_mac}_{timestamp}.json`

For example:
```
~/.bleep/aoi/001122334455_20230901_123456.json
```

Reports are written to a **`reports/` subdirectory** of the AoI directory
(`~/.bleep/aoi/reports/`), not the top-level AoI directory:

- **Per-device auto-name** (no `--output`): `report_{normalized_mac}_{timestamp}.md`
  (the auto-generated name always uses a `.md` extension, even for `--format
  json`/`text` — the *content* still matches the requested format).
- **Aggregate auto-name** (`--all`, no `--output`):
  `aggregate_report_{timestamp}.{json|md|txt}` (extension follows `--format`).
- **With `--output <path>`**: the given path is used. A *relative* path resolves
  under `~/.bleep/aoi/reports/`; pass an *absolute* path to write elsewhere.

The Device Information block of markdown/text reports includes **Enumerated via**
(the adapter that last GATT-enumerated the device) and **Seen by** (antennas that
observed it during survey) when those fields are present in the scan JSON or the
observation-DB `devices` row (schema v19/v20). Survey JSON emits `enumerated_by`
when GATT enumeration succeeded (`--enumerator`); failed attempts are omitted
from JSON and from the DB columns. `enumerated_at` (v20) is the recency stamp
`--enum-cooldown` uses.

## Security Analysis Features

The AOI analyzer performs several types of security checks:

### Service Analysis
- Identifies core BLE services (GAP, GATT)
- Detects firmware update services — by name (OTA/DFU/firmware) **and** by a
  curated set of vendor OTA/DFU UUIDs (Nordic, TI OAD, Silicon Labs, MCUmgr SMP),
  catching custom 128-bit services that carry no SIG name
- Flags authentication and security-related services

### Characteristic Analysis
- Identifies authentication/credential characteristics that are writable
- Flags custom write-without-response characteristics with no authenticated/signed-write requirement
- Detects bidirectional control channels (writable **and** notify/indicate)
- Flags characteristics with unusually long hex default values (possible embedded data)

### SDP Analysis (Classic)
- Summarises discovered SDP services and flags exposed Classic profiles (OBEX, FTP, PBAP, MAP, SPP, …)
- The report's `## SDP Discovery` section renders a collapsed **service inventory** — records grouped by `(name, uuid, channel)` with occurrence counts, shown as `Name (UUID, ch N) : count` under an `N unique of M records` header (mirrors the DB-9 aggregate SDP inventory but per-device). Keeps snapshot-heavy devices legible and disambiguates the same service class exposed on different RFCOMM channels.
- Enriches the summary via `SDPAnalyzer`: protocols (RFCOMM/L2CAP/…), RFCOMM channels, version anomalies, and an SDP-inferred spec hint

### Permission Analysis
- Maps read/write permissions across the device
- Identifies inconsistent permission patterns
- Detects potential security boundary issues

### Landmine Detection
- Identifies characteristics that might cause device crashes or lockups
- Detects potentially dangerous write operations
- Flags characteristics with unusual behavior

## Best Practices

1. **Use Survey Mode for Target Lists**: Use `bleep survey -o targets.json` to generate AoI target lists automatically from ambient device discovery — see [Survey Mode](survey_mode.md)
2. **Organize Device Lists**: Group related devices in separate JSON files for better organization
3. **Set Appropriate Delays**: Use `--delay` parameter to control the time between device scans (default: 4.0 seconds)
4. **Use Deep Analysis**: For important devices, use the `--deep` flag for more thorough security analysis
5. **Save Reports**: Always save security reports for important findings
6. **Export Data**: Export device data for integration with other security tools
7. **Monitor Changes**: Re-scan and analyze devices periodically to track changes. Each analysis is appended to the `aoi_analysis_history` table (schema v17), so successive scans are retained and can be compared over time via `get_aoi_analysis_history(mac)` (the latest is always available via `get_aoi_analysis(mac)`)

## Troubleshooting

- **No Devices Found**: Ensure your Bluetooth adapter is working and the devices are in range. On a two-radio host, pass `--adapter hciN` so GATT/SDP run on the same controller that saw the device (survey `--then-aoi` does this automatically).
- **Analysis Fails**: Verify the device has been scanned and data exists in `~/.bleep/aoi/`
- **Empty Reports**: Some devices might not provide enough information for meaningful analysis
- **Connection Issues**: Use `--delay` with higher values for devices that are slow to respond

## Implementation Notes

The AOI implementation includes robust handling for different data formats and structures:

1. **Service Data Handling**:
   - Supports both list format (`"services": ["uuid1", "uuid2"]`) and dictionary format for services
   - Properly processes services from different data sources

2. **Characteristic Data Handling**:
   - Extracts characteristics from service mappings when needed
   - Handles characteristics in various formats
   - Processes both direct UUIDs and characteristic objects

3. **Error Handling**:
   - Robust type checking to prevent failures with unexpected data structures
   - Graceful fallbacks for missing or incomplete data
   - Comprehensive error reporting and logging

## Tips

- Use the `--delay` parameter to control the time between device scans (default: 4.0 seconds)
- For large device lists, consider splitting them into multiple files
- Use the `analyze --deep` subcommand for more thorough security analysis
- Generated reports can be in markdown, JSON, or text formats
- The AOI database persists between sessions, allowing for offline analysis
- Use the export command to share device data with other security tools
- When scanning multiple devices, consider increasing the delay for devices that are slow to respond