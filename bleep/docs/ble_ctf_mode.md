# BLE CTF Mode

The BLE CTF mode provides specialized tools for solving Bluetooth Low Energy Capture The Flag (CTF) challenges. It includes automated flag discovery, analysis, and solving capabilities.

## Overview

BLE CTF challenges typically involve a series of flags that must be discovered and solved by interacting with a BLE device. These challenges often require:

- Reading values from specific characteristics
- Converting between different formats (hex to ASCII, computing MD5 hashes, etc.)
- Writing specific values to a "Flag-Write" characteristic
- Understanding and following instructions embedded in characteristic values
- Handling notifications and other BLE-specific interactions

The BLE CTF mode in BLEEP provides tools to automate and simplify these tasks, allowing for efficient discovery and solving of CTF challenges.

## Quick Start

### Command-Line Interface

```bash
# Interactive mode
python -m bleep.cli ctf --interactive

# Automatically discover and analyze flags
python -m bleep.cli ctf --discover

# Automatically solve all flags
python -m bleep.cli ctf --solve

# Generate a visual representation of flag status
python -m bleep.cli ctf --visualize

# Specify a custom device address (default is CC:50:E3:B6:BC:A6)
python -m bleep.cli ctf --device 11:22:33:44:55:66 --discover
```

### Interactive Shell Commands

When using the interactive shell (`--interactive` or default), the following commands are available:

```
help                Show help message
scan                Scan for BLE devices
connect             Connect to the BLE CTF device
read <flag>         Read a specific flag (e.g., Flag-02 or char002d)
write <value>       Write a value to Flag-Write characteristic
score               Read the current score
solve <flag>        Solve a specific challenge (e.g., Flag-02)
solve-all           Attempt to solve all available challenges
discover            Automatically discover and analyze flags
auto-solve          Automatically discover and solve all flags
visualize           Generate a visual representation of flag status
list                List all available flags
quit                Exit the program
```

## Features

### Automated Flag Discovery

The flag discovery system automatically:

1. Reads all flag characteristics from the device
2. Analyzes the content to determine the challenge type
3. Extracts relevant information using pattern matching
4. Suggests potential solutions with confidence scores

Example patterns detected:

- Standard CTF flag formats (`flag{...}`, `ctf{...}`, etc.)
- Hex-encoded strings that can be converted to ASCII
- Instructions to write specific values
- References to MD5 hashing
- Handle lookup instructions

### Automated Flag Solving

The auto-solve feature:

1. Discovers all flags and analyzes them
2. Determines the most likely solution for each flag
3. Submits solutions to the Flag-Write characteristic
4. Tracks the score before and after solving
5. Provides a summary of solved challenges

### Flag Visualization

The visualization feature generates a table showing:

- All available flags
- Their current status (solved, potentially solvable, unknown)
- Confidence scores for potential solutions
- Brief descriptions of the solutions

Example:
```
┌─────────────────────────────────────────────────────────┐
│ BLE CTF Flag Status                 Score: 3/20         │
├─────────────────────────────────────────────────────────┤
│ Flag     │ Status  │ Confidence │ Solution              │
├─────────────────────────────────────────────────────────┤
│ Flag-02  │ ✓      │ 90%        │ 1a2b3c                │
│ Flag-03  │ ✓      │ 85%        │ hello                 │
│ Flag-04  │ ?      │ 60%        │ handle lookup required │
│ Flag-05  │ ✓      │ 90%        │ 0x07                  │
│ Flag-06  │ ?      │ 0%         │ Unknown               │
└─────────────────────────────────────────────────────────┘
```

## Challenge Types

The BLE CTF mode can detect and solve various types of challenges:

| Type | Description | Example |
|------|-------------|---------|
| Direct Read | Flag is directly readable from characteristic | `flag{abc123}` |
| Hex to ASCII | Hex-encoded string that needs conversion | `68656c6c6f` → `hello` |
| ASCII to Hex | ASCII string that needs hex conversion | `hello` → `68656c6c6f` |
| Notification | Flag is delivered via notification | Requires enabling notifications |
| Specific Value | A specific value must be written | `Write the hex value 0x07` |
| Handle Lookup | Value must be read from another handle | `Read handle 0x0029` |
| Password Protected | Requires writing a password first | Write `CTF` before reading |
| MD5 Hash | Requires computing an MD5 hash | `MD5 of Device Name` |

## Customization

The BLE CTF mode is designed to work with standard BLE CTF challenges, but can be customized for specific CTF events:

- The default device MAC address can be changed with `--device`
- New challenge patterns can be added to `CHALLENGE_PATTERNS` in `blectf.py`
- Additional solving strategies can be implemented in the `solve_flag_XX` functions

## Troubleshooting

### Connection Issues

If you have trouble connecting to the BLE CTF device:

1. Verify the device is powered on and in range
2. Check that the MAC address is correct
3. Try resetting the Bluetooth adapter (`sudo hciconfig hci0 reset`)
4. Ensure no other devices are connected to the CTF device

### Solving Issues

If automatic solving isn't working:

1. Try reading individual flags manually (`read Flag-XX`)
2. Check the score to see if any flags have been solved
3. Use the `discover` command to analyze flags without solving
4. Try solving individual flags manually (`solve Flag-XX`)

## Advanced Usage

### Adding New Challenge Types

To add support for a new challenge type:

1. Add a new pattern to `FLAG_PATTERNS` in `ctf_discovery.py`
2. Add a new challenge type in the `ChallengeType` class
3. Update the `detect_challenge_type` function to detect the new pattern
4. Add a new case in the `process_flag` function to handle the new type
5. Implement a solver function in `blectf.py` if needed

### Custom Payload Generation

For brute-force challenges, you can create custom payloads:

```python
from bleep.ble_ops.enum_helpers import build_payload_iterator, brute_write_range

# Generate payloads
payloads = build_payload_iterator(
    value_range=(0, 255),  # Range of values
    patterns=["ascii", "increment"]  # Patterns to use
)

# Write payloads to characteristic
results = brute_write_range(
    device,
    "char002b",  # Flag-Write characteristic
    payloads=payloads,
    delay=0.05,  # Delay between writes
    verify=True  # Read back after each write
)
```

## References

- [BLE CTF GitHub Repository](https://github.com/hackgnar/ble_ctf)
- [BLEEP Documentation](https://github.com/your-org/bleep)