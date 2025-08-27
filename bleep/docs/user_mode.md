# User-mode quick-start guide

User-mode is a high-level wrapper around BLEEP's discovery and enumeration
helpers. It trades raw flexibility for **speed and safety**, making it ideal
for day-to-day reconnaissance or troubleshooting when you don't need every
single handle in the GATT database.

The user mode provides two interfaces:
1. A **menu-driven interface** for interactive exploration (default)
2. A **command-line interface** for automation

## Menu-driven Interface

The menu interface provides a user-friendly way to interact with Bluetooth devices without needing to memorize commands.

```bash
# Launch the menu interface
python -m bleep.cli user
```

This will display the main menu:

```
==================================================
BLEEP User Mode
==================================================

No device connected

Options:
1. Scan for Devices
2. Connect to Device
3. View Device Info
4. Browse Services
5. Configure Signal Capture
6. Export Device Data
7. Disconnect
0. Exit
```

### Key Features

- **Device Discovery**: Scan for nearby Bluetooth devices and connect to them
- **Service & Characteristic Browsing**: Navigate through device services and characteristics
- **Value Reading & Writing**: Read and write characteristic values with various formats
- **Notifications**: Enable and capture characteristic notifications
- **Signal Configuration**: Configure signal capture settings
- **Data Export**: Export device data to JSON for offline analysis

### Starting with a Connected Device

```bash
# Launch with automatic scan and connection
python -m bleep.cli user --scan 5

# Connect directly to a specific device
python -m bleep.cli user --device 00:11:22:33:44:55
```

---

## Typical workflow

```bash
# 1. Discover devices (passive)
python -m bleep.cli scan

# 2. Enumerate a target safely (read-only)
python -m bleep.cli gatt-enum --address AA:BB:CC:DD:EE:FF

# 3. Compare changes over time (multi-read)
python -m bleep.cli enum-scan --address AA:BB:CC:DD:EE:FF --variant naggy

# 4. Light write probe (pokey)
python -m bleep.cli enum-scan --address AA:BB:CC:DD:EE:FF --variant pokey --verify

# 5. Full brute-force of a single characteristic (expert-only)
python -m bleep.cli enum-scan --address AA:BB:CC:DD:EE:FF --variant brute \
                             --write-char 00002a37-0000-1000-8000-00805f9b34fb \
                             --range 0x00-0x1F --patterns ascii,alt
```

All commands write JSON results to `~/.bleep/reports/YYYY-MM-DD/` and append
human-readable logs to `~/.bleep/logs/user_mode.log`.

---

## Command reference

| Command | Description |
|---------|-------------|
| `scan`  | Wrapper around discovery presets – defaults to **passive**; `--variant` flag exposes naggy/pokey/brute. |
| `enum`  | Passive enumeration (single read). |
| `enumn` | Multi-read enumeration – default **3** rounds, configurable with `--rounds`. |
| `enump` | Pokey enumeration – multi-read + 0/1 write probes; `--verify` re-reads after each write. |
| `enumb` | Brute enumeration – exhaustive writes to one characteristic.  Accepts `--range`, `--patterns`, `--payload-file`, `--force`, `--verify`. |

Safety guardrails are enabled by default: landmine/permission maps are honoured
unless `--force` is provided.

---

## Menu Interface Workflows

### Device Discovery & Connection

1. Select **Scan for Devices** from the main menu
2. Enter scan duration (default 10 seconds)
3. Select a device from the list of discovered devices
4. The device will be connected and its services enumerated

### Service & Characteristic Browsing

1. Select **Browse Services** from the main menu
2. Select a service from the list
3. Select a characteristic from the list
4. Choose an action (Read, Write, Enable Notifications, etc.)

### Characteristic Value Reading

1. Navigate to a characteristic as described above
2. Select **Read Value**
3. The value will be displayed in multiple formats (hex, ASCII, integer, etc.)

### Characteristic Value Writing

1. Navigate to a characteristic as described above
2. Select **Write Value**
3. Choose the value format (hex, ASCII, decimal)
4. Enter the value
5. Choose whether to use write-without-response (if supported)

### Enable Notifications

1. Navigate to a characteristic that supports notifications
2. Select **Enable Notifications**
3. Notifications will be displayed as they are received
4. Press Enter to stop receiving notifications

### Signal Configuration

1. Select **Configure Signal Capture** from the main menu
2. Choose to create, edit, or delete a configuration
3. For new configurations, specify filters and actions
4. Configurations are saved for future use

### Data Export

1. Select **Export Device Data** from the main menu
2. The device data will be exported to `~/.bleep/exports/`

## UI Navigation Patterns

The User Mode provides a consistent, hierarchical navigation pattern that makes it easy to explore Bluetooth devices without memorizing commands.

### Menu Hierarchy

```
Main Menu
├── Scan for Devices
│   └── Device Selection Menu
│       └── (Connect to selected device)
├── Connect to Device
│   └── (Manual address entry)
├── View Device Info
├── Browse Services
│   ├── Service 1
│   │   ├── Characteristic 1.1
│   │   │   ├── Read Value
│   │   │   ├── Write Value (if supported)
│   │   │   ├── Enable Notifications (if supported)
│   │   │   ├── Disable Notifications (if supported)
│   │   │   └── Multi-Read
│   │   └── Characteristic 1.2
│   │       └── (Actions...)
│   └── Service 2
│       └── (Characteristics...)
├── Configure Signal Capture
│   ├── Create new configuration
│   ├── Edit existing configuration
│   └── Delete configuration
├── Export Device Data
└── Disconnect
```

### Navigation Controls

Throughout the User Mode interface, the following controls are consistent:

- **Numeric keys (1-9)**: Select menu options
- **0**: Exit the application
- **B**: Go back to the previous menu (when available)
- **Enter**: Confirm actions or continue after information display
- **Ctrl+C**: Exit the application from any screen

### Menu Context

Each menu displays contextual information:
- The current menu title
- Connection status (device address and name, if connected)
- Available options based on the current context
- Navigation hints

### State-Based Options

The interface dynamically shows or hides options based on the current state:
- Options requiring a connected device are hidden when no device is connected
- Write and notification options are only shown for characteristics supporting those operations
- Configuration editing options are only shown when configurations exist

### Error Handling

When errors occur, the User Mode provides:
- User-friendly error messages explaining what went wrong
- Suggestions for resolving common issues
- Automatic recovery attempts for connection problems
- Seamless handling of permissions and authentication issues

## Quick-Start Examples for Common Workflows

### Example 1: Finding and Reading a Battery Level

```bash
# Start the User Mode
python -m bleep.cli user

# From the main menu:
# 1. Select "1" to scan for devices
# 2. Enter scan duration (e.g., 5 seconds)
# 3. Select the device number from the list
# 4. Select "4" to browse services
# 5. Look for "Battery Service" and select it
# 6. Select "Battery Level" characteristic
# 7. Choose "1" to read the value
```

### Example 2: Configuring Notifications for Heart Rate

```bash
# Start the User Mode with direct connection
python -m bleep.cli user --device 00:11:22:33:44:55

# From the main menu:
# 1. Select "4" to browse services
# 2. Select "Heart Rate Service"
# 3. Select "Heart Rate Measurement" characteristic
# 4. Choose "3" to enable notifications
# 5. Watch for incoming notifications
# 6. Press Enter to stop notifications
```

### Example 3: Writing to a Characteristic

```bash
# Start the User Mode
python -m bleep.cli user

# From the main menu:
# 1. Select "2" to connect to a device manually
# 2. Enter the device address
# 3. Select "4" to browse services
# 4. Navigate to the desired service and characteristic
# 5. Choose "2" to write a value
# 6. Select the format (hex, ASCII, or decimal)
# 7. Enter the value
# 8. Choose whether to use write-without-response (if applicable)
```

### Example 4: Setting Up Signal Capture

```bash
# Start the User Mode
python -m bleep.cli user

# From the main menu:
# 1. Select "5" to configure signal capture
# 2. Choose "1" to create a new configuration
# 3. Enter a name for the configuration
# 4. Select filter options (e.g., specific device, service, etc.)
# 5. Choose action options (logging, database storage, etc.)
```

### Example 5: Exporting Device Data for Analysis

```bash
# Start the User Mode with scan
python -m bleep.cli user --scan 5

# From the main menu:
# 1. Select a device from the scan results
# 2. Select "6" to export device data
# 3. Note the path where data is exported
```

## Advanced Usage

### Command Line Integration

The User Mode can be combined with other BLEEP commands for advanced workflows:

```bash
# Scan with User Mode then export the data for analysis
python -m bleep.cli user --scan 10
# Export to JSON then use jq to filter for specific services
jq '.services[] | select(.uuid | contains("180f"))' ~/.bleep/exports/device_*.json

# Use classic scan to find BR/EDR devices, then connect with User Mode
python -m bleep.cli classic-scan
python -m bleep.cli user --device 00:11:22:33:44:55
```

### Custom User Mode Sessions

Start User Mode with specific focuses:

```bash
# Focus on signal analysis
# 1. Start with scanning
python -m bleep.cli user --scan 8
# 2. Configure signal capture
# 3. Enable notifications for characteristics of interest
# 4. Export data after capture session
```

### Integration with AoI Analysis

Use User Mode to collect data, then analyze it with the AoI tools:

```bash
# 1. Use User Mode to connect and export device data
python -m bleep.cli user --device 00:11:22:33:44:55
# 2. Then run AoI analysis on the collected data
python -m bleep.cli aoi analyze --address 00:11:22:33:44:55
# 3. Generate a security report
python -m bleep.cli aoi report --address 00:11:22:33:44:55
```

### Multi-Device Management

Navigate efficiently when working with multiple devices:

```bash
# Start User Mode with scan
python -m bleep.cli user --scan 5
# Connect to first device and perform operations
# Use "7. Disconnect" option
# Then use "2. Connect to Device" to connect to another device
```

## Multi-read helpers

Internally `enumn` and `enump` rely on two utilities exported from
`bleep.ble_ops.enum_helpers`:

```python
from bleep.ble_ops.enum_helpers import multi_read_characteristic, multi_read_all

# read one handle repeatedly
values = multi_read_characteristic(dev, "00002a37-…", repeats=5)

# full-database snapshot 3 times
rounds = multi_read_all(dev, mapping, rounds=3)
```

Use these helpers in your own scripts when you need change-detection logic.

---

## Brute-write helpers

`enumb` is powered by `build_payload_iterator` and `brute_write_range`.
Advanced users can craft custom payloads:

```python
from bleep.ble_ops.enum_helpers import build_payload_iterator, brute_write_range

payloads = build_payload_iterator(
    value_range=(0x00, 0x0F),
    patterns=["alt", "repeat:ff:8", "hex:DEADBEEF"],
)

results = brute_write_range(
    dev,
    "00002a37-…",
    payloads=payloads,
    verify=True,
)
```

---

## Troubleshooting

### Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| **Controller Stall** | Operations hang or "No Reply" errors | User Mode automatically suggests running `bluetoothctl disconnect <MAC>`. If reconnection fails, restart BlueZ with `sudo systemctl restart bluetooth` or power-cycle your adapter. |
| **Permission Errors** | "Not authorized" or "Not permitted" messages | Check if characteristic requires authentication. Try pairing with the device using `bluetoothctl`. Landmine and permission maps are logged under `~/.bleep/maps/`. |
| **Connection Failures** | "Connection refused" or timeouts | Ensure the device is in range and advertising. If the device was recently connected elsewhere, it may need time to reset. |
| **Value Reading Errors** | "Value format not recognized" | The characteristic may use a custom format. Try viewing the data in hexadecimal format. |
| **Notification Issues** | Notifications not appearing | Ensure the characteristic supports notifications and they are properly enabled. Check if other applications are already subscribed. |
| **Device Disappears** | Device no longer appears in scan results | Some devices stop advertising after connection or timeout. Try disabling/enabling Bluetooth or putting the device back in discovery mode. |

### Signal Capture Troubleshooting

* **Signals not being captured**: Check that your configuration has the correct filters and is enabled.
* **Filter not matching**: Verify UUID format and ensure you're using the correct address format.
* **Signal capture permissions**: Ensure you have appropriate permissions for file writing if using log actions.

### Getting Help

If you encounter issues not covered here:

1. Check the log files located in `~/.bleep/logs/`
2. Look for errors in the console output
3. Try running BLEEP in debug mode for more verbose output:
   ```bash
BLEEP_LOG_LEVEL=DEBUG python -m bleep.cli user
```
4. Review known issues in the project documentation

---

*Last updated: 2025-07-25 (Extended with UI navigation patterns and workflow examples; corrected command syntax to use python -m bleep.cli)* 