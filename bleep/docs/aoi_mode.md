# Assets-of-Interest (AoI) Mode

## Overview

The Assets-of-Interest (AoI) mode is a powerful feature in BLEEP designed for security researchers, penetration testers, and Bluetooth analysts. It provides a structured approach to identify, analyze, and track devices of particular interest in your Bluetooth landscape based on their security properties and characteristics.

This mode helps you:

- Identify potentially vulnerable Bluetooth devices
- Generate detailed security reports about device characteristics 
- Track device behavior changes over time
- Store and analyze device data offline
- Prioritize devices for further investigation

## Getting Started

### Basic Usage

```bash
# Scan for devices and analyze any that match AoI criteria
bleep aoi scan

# Analyze a specific device by MAC address
bleep aoi analyze --address 00:11:22:33:44:55

# Generate a security report for a device
bleep aoi report --address 00:11:22:33:44:55

# List all saved AoI devices
bleep aoi list
```

### Debug Shell Commands

Within the BLEEP debug shell, use the `aoi` command:

```
> aoi list
# Lists all saved AoI devices with their analysis status

> aoi analyze 00:11:22:33:44:55
# Analyzes a specific device and saves results

> aoi report 00:11:22:33:44:55 [--format markdown|json|text]
# Generates a security report in the specified format
```

## Technical Details

### AoI Analyzer

The core of the AoI system is the `AOIAnalyser` class, which provides methods to:

1. **Analyze Device Data**: Process device information to identify security concerns, unusual characteristics, or other notable findings.
2. **Generate Reports**: Create comprehensive security reports in multiple formats.
3. **Store Device Data**: Save device information for offline analysis or historical comparison.

```python
from bleep.analysis.aoi_analyser import AOIAnalyser

# Initialize the analyzer
analyzer = AOIAnalyser()

# Analyze a device
results = analyzer.analyze_device(device_object)

# Generate a report
report = analyzer.generate_report(device_address="00:11:22:33:44:55", format="markdown")
```

### Data Persistence

AoI device data is stored in JSON format at `~/.bleep/aoi/*.json` by default. Each file represents a device with its complete analysis data. This allows for:

- Offline analysis without needing the physical device
- Historical comparison of device behavior
- Sharing device data with other researchers
- Batch processing of multiple device profiles

### Security Scoring

The AoI analyzer assigns a security score to each device based on multiple factors:

| Score Range | Risk Level | Description |
|-------------|------------|-------------|
| 8-10        | High       | Critical security concerns identified |
| 5-7         | Medium     | Notable security issues present |
| 2-4         | Low        | Minor security considerations |
| 0-1         | Minimal    | No significant security concerns |

Factors affecting security scoring include:

- Presence of writable characteristics without authentication
- Use of static or predictable values
- Weak or missing encryption
- Insecure pairing methods
- Unusual service combinations
- Non-standard UUIDs
- Inconsistent device behavior

## Advanced Usage

### Deep Analysis

For comprehensive device examination:

```bash
bleep aoi analyze --address 00:11:22:33:44:55 --deep
```

The `--deep` flag enables:

- More exhaustive characteristic probing
- Advanced pattern analysis
- Extended security checks
- Cross-characteristic correlation

### Temporal Analysis

To analyze changes in a device over time:

```bash
bleep aoi diff --address 00:11:22:33:44:55 --from 2023-01-01 --to 2023-02-01
```

This compares device snapshots across multiple scans to identify:

- Changed characteristic values
- New or removed services
- Security configuration changes
- Behavioral inconsistencies

### Custom Security Checks

You can extend the AoI analyzer with custom security checks:

```python
def check_for_default_passwords(device_data):
    """Check if device uses default passwords."""
    # Implementation of check
    risk_level = "high" if vulnerable else "none"
    return {
        "name": "Default Password Check",
        "finding": finding_message,
        "risk": risk_level
    }

# Register the check
analyzer.register_security_check("default_passwords", check_for_default_passwords)

# Run analysis with custom check
results = analyzer.analyze_device_data(device_data, checks=["default_passwords"])
```

## Report Examples

### Basic Security Report

```markdown
# Security Report: Device Name (00:11:22:33:44:55)

**Generated:** 2025-07-24 15:30:22
**Security Score:** 7/10

## Vulnerabilities

🔴 **Unprotected Write Access:** Characteristic 0xFFE1 allows writes without authentication
🟠 **Static Value Pattern:** Characteristic 0x2A19 returns predictable values
🟡 **Non-standard Service:** Service 0xFFF0 uses a non-standard UUID

## Recommendations

1. Enable authentication for writable characteristics
2. Implement random challenges for the battery level characteristic
3. Verify the purpose of the custom service at 0xFFF0
```

### JSON Export

```json
{
  "device": {
    "address": "00:11:22:33:44:55",
    "name": "Device Name",
    "services": [
      {
        "uuid": "0000180f-0000-1000-8000-00805f9b34fb",
        "name": "Battery Service",
        "characteristics": [
          {
            "uuid": "00002a19-0000-1000-8000-00805f9b34fb",
            "name": "Battery Level",
            "flags": ["read", "notify"],
            "security_note": "Returns predictable values"
          }
        ]
      }
    ]
  },
  "analysis": {
    "security_score": 7,
    "vulnerabilities": [
      {
        "name": "Unprotected Write Access",
        "description": "Characteristic 0xFFE1 allows writes without authentication",
        "risk": "high"
      }
    ],
    "recommendations": [
      "Enable authentication for writable characteristics",
      "Implement random challenges for the battery level characteristic",
      "Verify the purpose of the custom service at 0xFFF0"
    ]
  }
}
```

## Best Practices

1. **Regular Scans**: Periodically scan devices to track changes over time.

2. **Detailed Documentation**: Use the `--format markdown` option to generate readable reports.

3. **Consistent Device Tracking**: Always use the same MAC address format (lowercase, with colons) for consistent tracking.

4. **Combine with Signal Capture**: Use the signal capture system alongside AoI analysis for behavioral insights:
   ```bash
   # Setup signal capture for a specific device
   bleep signal-config add --device 00:11:22:33:44:55 --action log
   
   # Run AoI analysis while monitoring signals
   bleep aoi analyze --address 00:11:22:33:44:55
   ```

5. **Export Results**: Always export critical findings for sharing or offline analysis:
   ```bash
   bleep aoi export --address 00:11:22:33:44:55 --output /path/to/export
   ```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Analysis fails to complete | Try increasing timeout with `--timeout 30` |
| Missing device properties | Run a deeper scan with `bleep aoi analyze --deep` |
| JSON parsing errors | Check the device data format or try `--repair` |
| No vulnerabilities detected | Try enabling more analysis types with `--all-checks` |
| Device not found | Verify the MAC address format and ensure device is in range |

## Related Documentation

- [Signal Capture System](signal_capture.md) - For capturing and analyzing Bluetooth signals
- [CLI Usage](cli_usage.md) - For general BLEEP command-line interface usage
- [Debug Mode](debug_mode.md) - For interactive device exploration
