# CLI quick-start

The CLI can be accessed in two ways:

## Method 1: Using the CLI Module (Recommended)

```bash
python -m bleep.cli --help   # top-level help / version
```

## Method 2: Using the Package Entry Point (If Installed)

If the package is installed with `pip install -e .`:

```bash
bleep --help   # top-level help / version
```

> **Note:** BLEEP requires PyGObject (python3-gi) for core D-Bus operations. Install via your system package manager:
> - Ubuntu/Debian/Kali: `sudo apt-get install python3-gi`
> - Arch Linux: `sudo pacman -S python-gobject`
> 
> PyGObject is optional in pip install (moved to `extras_require["monitor"]`) to prevent build failures, but **required at runtime** for scanning, connecting, and monitoring operations.

> Note: The documentation previously showed `python -m bleep`, but this won't work because the package doesn't have a `__main__.py` file.

### Common sub-commands

| Command | Purpose | Example |
|---------|---------|---------|
| `scan` | Passive BLE scan for advertising packets | `python -m bleep.cli scan --timeout 15` |
| `classic-scan` | Passive Classic (BR/EDR) scan | `python -m bleep.cli classic-scan --timeout 10 --uuid 110b,110e [--debug]` |
| `connect` | Connect to a target and enumerate its GATT DB | `python -m bleep.cli connect AA:BB:CC:DD:EE:FF` |
| `gatt-enum` | Quick or deep GATT enumeration incl. permission/landmine reports | `python -m bleep.cli gatt-enum AA:BB:... --deep` |
| `media-enum` | Enumerate AVRCP / MediaPlayer capabilities | `python -m bleep.cli media-enum AA:BB:... --verbose` |
| `media-ctrl` | Control playback & volume on a media device | `python -m bleep.cli media-ctrl AA:BB:... play/pause/volume/press [--value 0x41]` |
| `db list` | List devices in the observation database | `python -m bleep.cli db list --status classic` |
| `db show` | Show detailed information for a device | `python -m bleep.cli db show AA:BB:CC:DD:EE:FF` |
| `db timeline` | View chronological characteristic history | `python -m bleep.cli db timeline AA:BB:... --char 2a00` |
| `db export` | Export device data to JSON | `python -m bleep.cli db export AA:BB:... --out device.json` |
| `agent` | Run a pairing agent (simple/interactive) | `python -m bleep.cli agent --mode simple` |
| `explore` | Scan & produce JSON mapping for later offline analysis ([docs](explore_mode.md)) | `python -m bleep.cli explore AA:BB:CC:DD:EE:FF --out dump.json [--connection-mode naggy] [--timeout 15]` |
| `analyse` / `analyze` | Post-process one or more JSON dumps ([docs](analysis_mode.md)) | `python -m bleep.cli analyse dump1.json dump2.json [--detailed]` |
| `signal` | Subscribe to notifications/indications | `python -m bleep.cli signal AA:BB:... char002d --time 60` |
| `signal-config` | Manage signal capture configurations | `python -m bleep.cli signal-config create my-config --default` |
| `aoi` | Enumerate Assets-of-Interest listed in JSON files ([docs](aoi_mode.md)) | `python -m bleep.cli aoi targets.json [--file test-file.json] [--delay 5.0]` |
| `interactive` | Enter interactive REPL console | `python -m bleep.cli interactive` |

Characteristic reads are automatically archived in the local database (no CLI flag needed).

Run `python -m bleep.cli <command> --help` for detailed per-command options.

### Environment variables

| Variable | Effect |
|----------|--------|
| `BLEEP_LOG_LEVEL` | Override default log level (`DEBUG`, `INFO`, etc.) |
| `BLE_CTF_MAC` | Default MAC address for CTF challenges (used by `blectf` mode) |

### Exit codes

`0` success, non-zero indicates an error (see stderr for details). 