# Assets-of-Interest (AoI) Implementation Details

This document describes the internal workings of the Assets-of-Interest (AoI) module in BLEEP, including key classes, data structures, and recent fixes.

## Architecture

The AoI functionality is implemented across multiple modules:

1. **Command Line Interface**: `bleep/cli.py` contains the AoI command parser and parameter handling.
2. **AoI Mode**: `bleep/modes/aoi.py` implements the main functionality for scanning, analyzing, listing, reporting, and exporting.
3. **AoI Analyzer**: `bleep/analysis/aoi_analyser.py` provides the core analysis logic for device data.

## Data Flow

1. **Input**: JSON files containing device MAC addresses in various formats.
2. **Scanning**: The AoI mode connects to each device and collects data.
3. **Storage**: Device data is stored in JSON files in `~/.bleep/aoi/`.
4. **Analysis**: The AOIAnalyser class processes the device data to identify security concerns.
5. **Reporting**: Results are formatted as markdown, JSON, or text reports.
6. **Export**: Raw device data can be exported for external processing.

## Key Classes

### AOIAnalyser

The `AOIAnalyser` class in `bleep/analysis/aoi_analyser.py` is responsible for analyzing device data and generating reports.

#### Key Methods:

- **`__init__(self, aoi_dir=None)`**: Initializes the analyzer with a specified data directory.
- **`list_devices(self)`**: Returns a list of all devices in the AOI database.
- **`load_device_data(self, device_mac)`**: Loads data for a specific device.
- **`save_device_data(self, device_mac, data)`**: Saves device data to the database.
- **`analyse_device(self, device_mac, data=None)`**: Analyzes device data and returns a report.
- **`analyze_device_data(self, device_data)`**: Bridge method to handle data without explicit device MAC.
- **`generate_report(self, device_address=None, device_data=None, format="markdown")`**: Generates a formatted report.
- **`save_report(self, report_content, filename=None, device_address=None)`**: Saves a report to disk.

### AoI Mode Functions

The `main()` function in `bleep/modes/aoi.py` processes the different subcommands:

- **`scan`**: Reads devices from JSON files and collects data.
- **`analyze`**: Analyzes a specific device's data.
- **`list`**: Lists all devices in the database.
- **`report`**: Generates a report for a specific device.
- **`export`**: Exports device data for external processing.

## Data Structures

### Device Data JSON Format

The device data JSON files can contain various structures:

```json
{
  "address": "00:11:22:33:44:55",
  "name": "Device Name",
  "services": ["uuid1", "uuid2", ...],
  "services_mapping": {
    "handle1": "uuid1",
    "handle2": "uuid2",
    ...
  },
  "characteristics": {
    "uuid1": {
      "properties": ["read", "write", ...],
      "value": "..."
    },
    ...
  },
  "landmine_map": { ... },
  "permission_map": { ... },
  "scan_timestamp": 1632150000
}
```

### Analysis Report Structure

The analysis reports include:

```json
{
  "device_mac": "00:11:22:33:44:55",
  "timestamp": "2023-09-01T12:00:00Z",
  "summary": {
    "security_concerns": [...],
    "unusual_characteristics": [...],
    "notable_services": [...],
    "accessibility": {...},
    "recommendations": [...]
  },
  "details": {
    "services": [...],
    "characteristics": [...],
    "landmine_map": {...},
    "permission_map": {...}
  }
}
```

## Recent Fixes

### 1. Method Name Consistency

**Issue**: Method name mismatch between callers and implementations.

**Fix**: Added a bridge method to handle different naming conventions:

```python
def analyze_device_data(self, device_data: Dict[str, Any]) -> Dict[str, Any]:
    """Bridge between generate_report and analyse_device."""
    device_mac = device_data.get("address", device_data.get("device_mac", "unknown"))
    return self.analyse_device(device_mac, device_data)
```

### 2. Service Data Handling

**Issue**: The `analyse_device` method expected services to be dictionaries, but they could be lists.

**Fix**: Updated code to handle both formats:

```python
# Handle different service data formats
if isinstance(services_data, list):
    # Process list of UUIDs
    for uuid in services_data:
        service_info = {"uuid": uuid}
        service_report = self._analyse_service(uuid, service_info)
        # ...
elif isinstance(services_data, dict):
    # Process dictionary of service info
    for uuid, service_info in services_data.items():
        service_report = self._analyse_service(uuid, service_info)
        # ...
```

### 3. Characteristic Data Handling

**Issue**: Characteristic data could be missing or in different formats.

**Fix**: Added support for extracting characteristics from other fields:

```python
# Handle cases where characteristics might be in services_mapping instead
if not characteristics and "services_mapping" in data:
    for handle, uuid in data.get("services_mapping", {}).items():
        char_info = {"uuid": uuid, "handle": handle}
        char_report = self._analyse_characteristic(uuid, char_info)
        # ...
elif isinstance(characteristics, dict):
    # Process normal characteristics dictionary
    for uuid, char_info in characteristics.items():
        char_report = self._analyse_characteristic(uuid, char_info)
        # ...
```

## Best Practices for Developers

When working with the AoI module, follow these best practices:

1. **Type Checking**: Always check the type of data before processing to handle different structures.
2. **Consistent Naming**: Use consistent naming conventions for methods and variables.
3. **Error Handling**: Implement robust error handling with meaningful messages.
4. **Modular Design**: Keep analysis logic separate from CLI handling.
5. **Documentation**: Document data structures and expected formats.

## Database Integration

The AoI module now integrates with BLEEP's observation database, providing a unified storage system while maintaining backward compatibility with the original file-based approach.

### Key Integration Features

1. **Bidirectional Data Flow**:
   - AoI data can be loaded from and saved to both files and the database
   - The `use_db` parameter in `AOIAnalyser` controls database integration

2. **Unified CLI Commands**:
   - `aoi db import`: Import file data to database
   - `aoi db export`: Export database data to files
   - `aoi db sync`: Bidirectional synchronization
   - `--db-only` flag for database-only operations
   - `--no-db` flag to disable database integration

3. **Database Schema**:
   - New `aoi_analysis` table stores analysis results
   - Security concerns, unusual characteristics, and recommendations are stored as JSON
   - Linked to device records via the `mac` foreign key

4. **API Changes**:
   - `AOIAnalyser` constructor now accepts a `use_db` parameter (default: `True`)
   - New methods check both file storage and database based on the `use_db` setting
   - The `load_device_data` and `save_device_data` methods support both storage mechanisms

### Implementation Details

The integration uses the following components:

1. **Database Functions**:
   - `store_aoi_analysis`: Stores analysis results in the `aoi_analysis` table
   - `get_aoi_analysis`: Retrieves analysis results from the database
   - `has_aoi_analysis`: Checks if analysis exists for a device
   - `get_aoi_analyzed_devices`: Lists all devices with AoI analysis

2. **Schema Changes**:
   - Version 4 of the database schema introduces the `aoi_analysis` table
   - Automatic migration is performed when the schema version changes

3. **Fallback Mechanism**:
   - If database operations fail, the system falls back to file-based storage/retrieval
   - This ensures backward compatibility and resilience

## Future Improvements

Potential improvements for the AoI module:

1. **Standardized Method Naming**: Consistently use either American or British spelling.
2. **Comprehensive Type Validation**: Add validators for all input data.
3. **Enhanced Data Schema**: Define a formal schema for device data and analysis reports.
4. **Test Cases**: Add dedicated test cases for the AoI functionality to prevent regression.
5. **Detailed Documentation**: Create comprehensive API documentation for all AoI classes and methods.

## References

- [AoI Mode Documentation](aoi_mode.md): User documentation for the AoI feature.
- [Changelog](changelog.md): History of changes to the AoI module.
