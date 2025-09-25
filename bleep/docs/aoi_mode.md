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

### List Subcommand

```bash
# List all saved AOI devices
python -m bleep.cli aoi list
```

The list operation:
- Shows all devices stored in the AOI database
- Displays MAC address, device name, and analysis status
- Provides a numbered index for easy reference

### Report Subcommand

```bash
# Generate a report for a device
python -m bleep.cli aoi report --address 00:11:22:33:44:55 --format markdown
python -m bleep.cli aoi report --address 00:11:22:33:44:55 --format json --output device_report.json
```

The report operation generates detailed security reports:
- **Markdown Format**: Human-readable report with sections for security concerns, unusual characteristics, and recommendations
- **JSON Format**: Machine-readable report for integration with other tools
- **Text Format**: Simple text report for console output
- Reports can be saved to a specified file or auto-generated in the AOI directory

### Export Subcommand

```bash
# Export a specific device's data
python -m bleep.cli aoi export --address 00:11:22:33:44:55 --output device_data.json

# Export all devices' data
python -m bleep.cli aoi export --output export_dir
```

The export operation:
- Exports raw device data in JSON format
- Can export a single device or all devices
- Preserves all collected information including services, characteristics, and analysis results
- Useful for sharing data or processing with external tools

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

## Security Analysis Features

The AOI analyzer performs several types of security checks:

### Service Analysis
- Identifies core BLE services (GAP, GATT)
- Detects firmware update services (OTA, DFU)
- Flags authentication and security-related services

### Characteristic Analysis
- Identifies authentication characteristics with weak permissions
- Detects characteristics with unusual property combinations
- Flags characteristics with suspiciously long values

### Permission Analysis
- Maps read/write permissions across the device
- Identifies inconsistent permission patterns
- Detects potential security boundary issues

### Landmine Detection
- Identifies characteristics that might cause device crashes or lockups
- Detects potentially dangerous write operations
- Flags characteristics with unusual behavior

## Tips

- Use the `--delay` parameter to control the time between device scans (default: 4.0 seconds)
- For large device lists, consider splitting them into multiple files
- Use the `analyze --deep` subcommand for more thorough security analysis
- Generated reports can be in markdown, JSON, or text formats
- The AOI database persists between sessions, allowing for offline analysis
- Use the export command to share device data with other security tools
- When scanning multiple devices, consider increasing the delay for devices that are slow to respond