# Explore Mode

## Overview

The Explore mode in BLEEP scans and produces JSON mappings of Bluetooth Low Energy (BLE) devices for later offline analysis. It connects to a specified BLE device, enumerates its GATT database, and saves the results to a JSON file.

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
  - `passive`: Single discovery pass with one bounded connect+resolve retry (default)
  - `naggy`: Multiple connection attempts with retries
- `--timeout SECONDS`: Scan timeout in seconds (default: 10)
- `--retries NUMBER`: Number of connection retries in naggy mode (default: 3)
- `--adapter hciN`: BlueZ controller (default `hci0`). Device1 is constructed on this adapter.

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
                "path": "/org/bluez/hci0/dev_AA_BB_CC_DD_EE:FF/service000a/char002b/desc002d"
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

### Architecture

Explore mode delegates connection to `scan_and_connect()` in
`bleep.ble_ops.le.scan_modes`, which dispatches to mode-specific wrapper
functions. Each wrapper calls the parameterised
`connect_and_enumerate__bluetooth__low_energy()` primitive in
`bleep.ble_ops.le.connect` with mode-appropriate settings — scan attempts,
connect retries, timeouts, and (for naggy) exponential backoff. See
[BLE Scan Modes](ble_scan_modes.md) for the full parameter table.

### Passive Mode (Default)

Passive mode performs a single discovery pass and then a bounded connect+resolve cycle (one retry). It is suitable for most devices in good signal conditions. Timeouts are derived from `--timeout` (`T`):

1. **Scanning**: Finding the device — `T // 2` (floor 5s)
2. **Connection**: Establishing connection — `T // 4` (floor 5s)
3. **Service Resolution**: Resolving GATT services — `max(T, 15)` (floor 15s)

Service resolution uses a fixed 15s floor (independent of the scan budget) because it is the slowest phase on rich GATT servers (robotics/audio/wearables); a smaller window previously caused spurious `ServicesNotResolved` failures on devices that merely resolve slowly. A single bounded connect+resolve retry absorbs transient first-attempt misses.

Internally this maps to `_connect_enum(scan_attempts=3, scan_timeout=max(T//2,5), connect_retries=1, connect_wait_timeout=max(T//4,5), timeout_services=max(T,15), max_attempts=2, backoff_base=0.5, backoff_max=5.0, backoff_jitter=0.5)`.

### Naggy Mode

Naggy mode is designed for unreliable connections or challenging environments. It uses multiple connection attempts with exponential backoff between retries. The `--retries` flag controls the outer retry count (default 10 when invoked via `scan_modes.py`, 3 when invoked via `explore`).

Internally this maps to `_connect_enum(max_attempts=retries, scan_attempts=5, scan_timeout=8, connect_retries=2, connect_wait_timeout=5.0, timeout_services=20, backoff_base=0.5, backoff_max=30.0, backoff_jitter=0.5)`.

Transient D-Bus `InProgress`/`Failed` errors are forgiven (they don't count toward the retry limit), making naggy mode robust against BlueZ state-machine glitches.

Use naggy mode for:
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

*Last updated: 2026-07-27*
