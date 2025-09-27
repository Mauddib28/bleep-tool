# Assets-of-Interest (AoI) Testing Guide

This document provides a comprehensive guide to testing the Assets-of-Interest (AoI) functionality in BLEEP.

## Test Suite Overview

The AoI test suite is designed to verify all aspects of the AoI functionality:

1. **Input File Parsing**: Tests parsing of different JSON formats (simple list, detailed objects, nested structure)
2. **Scanning Functionality**: Tests the scanning of devices from input files
3. **Analysis Functionality**: Tests the analysis of device data, including deep analysis
4. **Reporting Functionality**: Tests the generation of reports in different formats (markdown, JSON, text)
5. **Export Functionality**: Tests the export of device data, both for individual devices and for all devices
6. **Edge Case Handling**: Tests handling of edge cases like empty files, malformed MAC addresses, etc.

## Test Files

The test suite includes three JSON files with different formats, all containing the following MAC addresses:

1. `CC:50:E3:B6:BC:A6` - BLE CTF device
2. `14:89:FD:31:8A:7E` - Known Bluetooth Classic phone device
3. `64:A2:F9:BC:8E:95` - Device that may not appear in all scans
4. `F0:98:7D:0A:05:07` - Unknown device
5. `EC:04:28:42:18:4E` - Unknown device
6. `A0:85:E3:0D:A1:E6` - Unknown device

### Test File Formats

1. **Simple List Format** (`aoi_test_simple.json`):
   ```json
   [
     "CC:50:E3:B6:BC:A6",
     "14:89:FD:31:8A:7E",
     ...
   ]
   ```

2. **Detailed Object Format** (`aoi_test_detailed.json`):
   ```json
   [
     {
       "address": "CC:50:E3:B6:BC:A6",
       "name": "BLE CTF Device",
       "notes": "Known BLE CTF device for testing security features"
     },
     ...
   ]
   ```

3. **Nested Structure Format** (`aoi_test_nested.json`):
   ```json
   {
     "ble_devices": [
       {
         "address": "CC:50:E3:B6:BC:A6",
         "name": "BLE CTF Device"
       }
     ],
     "classic_devices": [...],
     ...
   }
   ```

## Running Tests

### Prerequisites

1. Python 3.x installed
2. BLEEP installed (`pip install -e .` from the project root)
3. Bluetooth adapter enabled

### Basic Usage

To run all tests:

```bash
./run_aoi_tests.sh
```

To list available tests:

```bash
./run_aoi_tests.sh --list
```

To run a specific test class:

```bash
./run_aoi_tests.sh --class TestAoIFunctionality
```

To run a specific test method:

```bash
./run_aoi_tests.sh --class TestAoIFunctionality --method test_001_scan_with_simple_json
```

### Test Class Descriptions

1. **TestAoIFunctionality**: Tests the main functionality of the AoI module:
   - Scanning with different JSON formats
   - Listing devices
   - Analyzing devices
   - Generating reports
   - Exporting device data

2. **TestAoIEdgeCases**: Tests handling of edge cases:
   - Empty JSON files
   - Malformed MAC addresses
   - Mixed case MAC addresses

## Expected Results

### Scan Tests

The scan tests should show output like:

```
==== Testing scan with simple JSON format ====
[*] Processing AoI file aoi_test_simple.json
[*] AoI connect+enum CC:50:E3:B6:BC:A6
...
```

Some devices might not be found if they're not in range or not powered on. The test will still pass if the scan attempt is made.

### Analysis Tests

The analysis tests should show output like:

```
==== Testing device analysis ====
[*] Analyzing device: CC:50:E3:B6:BC:A6
[+] Analysis complete for CC:50:E3:B6:BC:A6
```

### Report Generation Tests

The report generation tests should show output like:

```
==== Testing markdown report generation ====
[*] Generating markdown report for device: CC:50:E3:B6:BC:A6
[+] Report saved to /home/user/.bleep/aoi/cc50e3b6bca6_report_20250926_123456.markdown
```

### Export Tests

The export tests should show output like:

```
==== Testing single device export ====
[*] Exporting data for device: CC:50:E3:B6:BC:A6
[+] Device data exported to /tmp/tmp1234/aoi_export_CC50E3B6BCA6.json
```

## Test Implementation Details

The test script (`test_aoi.py`) uses the Python `unittest` framework and runs BLEEP commands via subprocess calls. It sets up a clean environment for each test by:

1. Backing up the existing AoI data directory
2. Running the test with specific parameters
3. Restoring the backup after the test completes

This ensures that tests don't interfere with each other or with existing data.

## Troubleshooting

1. **Device Not Found**: If a device isn't found during scanning, check that:
   - The device is powered on and in range
   - Your Bluetooth adapter is working properly
   - You have permission to use the Bluetooth adapter

2. **Command Fails**: If a command fails with an error, check that:
   - BLEEP is installed correctly
   - You're running the script from the project root directory
   - You have the necessary permissions to write to the AoI data directory

## Future Test Enhancements

1. **Mock Device Tests**: Add tests with mock Bluetooth devices to avoid depending on physical devices
2. **Performance Tests**: Add tests to measure the performance of the AoI module with large input files
3. **Integration Tests**: Add tests that verify integration with other BLEEP modules
4. **API Tests**: Add tests for direct API calls to the AoI module classes

## References

- [AoI Mode Documentation](aoi_mode.md): User documentation for the AoI feature
- [AoI Implementation Documentation](aoi_implementation.md): Technical implementation details
