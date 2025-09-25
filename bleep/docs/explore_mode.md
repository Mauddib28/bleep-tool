# Explore Mode

## Overview

The Explore mode in BLEEP is designed to scan and produce JSON mappings of Bluetooth Low Energy (BLE) devices for later offline analysis. This mode connects to a specified BLE device, enumerates its GATT database, and saves the results to a JSON file.

## Command Syntax

```bash
python -m bleep.cli explore <MAC_ADDRESS> [options]
```

### Required Arguments

- `MAC_ADDRESS`: The Bluetooth MAC address of the target device (e.g., "AA:BB:CC:DD:EE:FF")

### Options

- `--out FILE`, `--dump-json FILE`: Output JSON file path (default: stdout)
- `--verbose`, `-v`: Include verbose characteristic list with handles
- `--connection-mode MODE`, `--conn-mode MODE`: Connection mode to use:
  - `passive`: Single connection attempt (default)
  - `naggy`: Multiple connection attempts with retries
- `--timeout SECONDS`: Scan timeout in seconds (default: 10)
- `--retries NUMBER`: Number of connection retries in naggy mode (default: 3)

## Examples

### Basic Usage

```bash
# Scan a device and save to a JSON file
python -m bleep.cli explore AA:BB:CC:DD:EE:FF --out device_dump.json
```

### Advanced Usage

```bash
# Use naggy mode with more retries for unreliable connections
python -m bleep.cli explore AA:BB:CC:DD:EE:FF --connection-mode naggy --retries 5 --out device_dump.json

# Increase timeout for slow-responding devices
python -m bleep.cli explore AA:BB:CC:DD:EE:FF --timeout 20 --out device_dump.json

# Include verbose characteristic details
python -m bleep.cli explore AA:BB:CC:DD:EE:FF --verbose --out device_dump.json
```

## Output Format

The explore command produces a JSON file with the following structure:

```json
{
  "device": {
    "address": "AA:BB:CC:DD:EE:FF",
    "name": "Device Name",
    "services": [
      {
        "uuid": "0000180a-0000-1000-8000-00805f9b34fb",
        "path": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/service000a",
        "characteristics": [
          {
            "uuid": "00002a29-0000-1000-8000-00805f9b34fb",
            "path": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/service000a/char002b",
            "handle": 43,
            "flags": ["read"],
            "descriptors": [
              {
                "uuid": "00002902-0000-1000-8000-00805f9b34fb",
                "path": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/service000a/char002b/desc002d"
              }
            ]
          }
        ]
      }
    ]
  }
}
```

## Connection Modes

### Passive Mode (Default)

The passive mode performs a single scan and connection attempt with reasonable timeouts. It's suitable for most devices in good signal conditions. The connection process is divided into three phases:

1. **Scanning**: Finding the device (50% of the timeout)
2. **Connection**: Establishing connection (25% of the timeout)
3. **Service Resolution**: Resolving GATT services (25% of the timeout)

### Naggy Mode

The naggy mode is designed for unreliable connections or challenging environments. It uses multiple connection attempts with exponential backoff between retries. This mode is more aggressive and persistent, making it suitable for:

- Devices with intermittent connectivity
- Environments with interference
- Devices that require multiple connection attempts

## Post-Processing

After generating a JSON dump with the explore command, you can use the `analyse`/`analyze` command to process and extract insights from the data. See [Analysis Mode](analysis_mode.md) for more details.

## Troubleshooting

### Device Not Found

If the device is not found during scanning:
- Ensure the device is powered on and in range
- Increase the `--timeout` value
- Verify the MAC address is correct

### Connection Failures

If the connection fails:
- Try using `--connection-mode naggy` with increased `--retries`
- Ensure the device is not already connected to another application
- Check if the device requires pairing (use the `agent` command first)

### Service Resolution Failures

If services fail to resolve:
- Increase the `--timeout` value
- Try using `--connection-mode naggy`
- Some devices may have incomplete or non-standard GATT implementations
