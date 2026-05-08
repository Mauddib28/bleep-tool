# CLI quick-start

The CLI can be accessed in two ways:

## Method 1: Using the Package Module (Recommended)

```bash
python -m bleep --help        # top-level help / version
python -m bleep               # interactive REPL (no subcommand)
python -m bleep scan --timeout 15
```

The `python -m bleep.cli` form also works and is equivalent.

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

### BLE Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `scan` | Passive BLE scan for advertising packets ([docs](ble_scan_modes.md)) | `bleep scan --timeout 15 --variant naggy` |
| `connect` | Connect + enumerate (auto-routes Classic; `--ble-only` forces GATT) | `bleep connect AA:BB:CC:DD:EE:FF` |
| `gatt-enum` | Single-pass GATT enumeration; `--deep` for retry reads & descriptor probing, `--report` for landmine/security JSON ([docs](gatt_enumeration.md)) | `bleep gatt-enum AA:BB:... --deep` |
| `enum-scan` | Multi-variant enumeration engine: passive, naggy, pokey, or brute ([docs](gatt_enumeration.md)) | `bleep enum-scan AA:BB:... --variant naggy` |
| `explore` | Scan & produce JSON mapping for later offline analysis ([docs](explore_mode.md)) | `bleep explore AA:BB:... --out dump.json --connection-mode naggy` |
| `analyse` / `analyze` | Post-process one or more JSON dumps ([docs](analysis_mode.md)) | `bleep analyse dump1.json dump2.json --detailed` |
| `signal` | Subscribe to characteristic notifications/indications ([docs](signal_capture.md)) | `bleep signal AA:BB:... char002d --time 60` |
| `signal-config` | Manage signal capture configurations ([docs](signal_capture.md)) | `bleep signal-config create my-config --default` |
| `aoi` | Enumerate Assets-of-Interest: scan, analyze, report, export ([docs](aoi_mode.md)) | `bleep aoi targets.json --file test-file.json --delay 5.0` |
| `ctf` | BLE CTF challenge solver and analyzer ([docs](ble_ctf_mode.md)) | `bleep ctf --discover --device CC:50:E3:B6:BC:A6` |
| `uuid-translate` | Translate UUID(s) to human-readable names ([docs](uuid_translation.md)) | `bleep uuid-translate 2a00 180a --verbose` |

### Classic Bluetooth Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `classic-scan` | Passive Classic (BR/EDR) scan | `bleep classic-scan --timeout 10 --uuid 110b,110e --debug` |
| `classic-connect` | Connect to Classic device via SDP + RFCOMM ([docs](bl_classic_mode.md)) | `bleep classic-connect AA:BB:... --keep` |
| `classic-enum` | Enumerate Classic RFCOMM/SDP services ([docs](bl_classic_mode.md)) | `bleep classic-enum AA:BB:... --analyze --version-info` |
| `classic-pbap` | Download phone-book via PBAP to VCF ([docs](bl_classic_mode.md)) | `bleep classic-pbap AA:BB:... --repos ALL --out pb.vcf` |
| `classic-opp` | Object Push Profile: send/pull/exchange files ([docs](bl_classic_mode.md)) | `bleep classic-opp AA:BB:... send file.vcf` |
| `classic-map` | Message Access Profile: browse SMS/MMS ([docs](bl_classic_mode.md)) | `bleep classic-map AA:BB:... inbox` |
| `classic-ftp` | OBEX File Transfer: ls/get/put/mkdir/rm ([docs](bl_classic_mode.md)) | `bleep classic-ftp AA:BB:... ls /` |
| `classic-pan` | Personal Area Networking: connect/serve ([docs](bl_classic_mode.md)) | `bleep classic-pan connect AA:BB:... --role nap` |
| `classic-spp` | Serial Port Profile: register/unregister ([docs](bl_classic_mode.md)) | `bleep classic-spp register --name "BLEEP SPP"` |
| `classic-sync` | IrMC Synchronization: get/put phonebook ([docs](bl_classic_mode.md)) | `bleep classic-sync AA:BB:... get --output pb.vcf` |
| `classic-bip` | Basic Imaging Profile: props/get/thumb [experimental] ([docs](bl_classic_mode.md)) | `bleep classic-bip AA:BB:... get <handle> --output img.jpg` |
| `connect-profile` | Connect a specific Bluetooth profile by UUID ([docs](bl_classic_mode.md)) | `bleep connect-profile AA:BB:... --uuid 0000110a-... --action connect` |
| `hid-info` | Classify a device as HID (keyboard/mouse/gamepad) ([docs](device_type_classification.md)) | `bleep hid-info AA:BB:...` |
| `classic-ping` | L2CAP echo (l2ping) reachability test | `bleep classic-ping AA:BB:... --count 5` |

### Media & Audio Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `media-enum` | Enumerate AVRCP / MediaPlayer capabilities ([docs](media_mode.md)) | `bleep media-enum AA:BB:... --verbose --monitor` |
| `media-ctrl` | Control playback & volume on a media device | `bleep media-ctrl AA:BB:... play` |
| `audio-profiles` | List Bluetooth audio profiles via ALSA correlation | `bleep audio-profiles --device AA:BB:...` |
| `audio-play` | Play audio file to Bluetooth device | `bleep audio-play AA:BB:... song.mp3 --volume 80` |
| `audio-record` | Record audio from Bluetooth device | `bleep audio-record AA:BB:... output.wav --duration 30` |
| `audio-recon` | Audio recon: enumerate cards, play, record, analyse ([docs](audio_recon.md)) | `bleep audio-recon --device AA:BB:... --out result.json` |
| `audio-intercept` | Capture and optionally transcribe audio from a BT device ([docs](audio_recon.md)) | `bleep audio-intercept AA:BB:... --duration 15` |
| `amusica` | Amusica: scan, connect, recon, manipulate audio targets | `bleep amusica scan --timeout 10` |

### Database Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `db list` | List devices in the observation database ([docs](observation_db.md)) | `bleep db list --status classic --fields mac,name,last_seen` |
| `db show` | Show detailed information for a device | `bleep db show AA:BB:CC:DD:EE:FF` |
| `db timeline` | View chronological characteristic history | `bleep db timeline AA:BB:... --char 2a00 --limit 50` |
| `db export` | Export device data to JSON | `bleep db export AA:BB:... --out device.json` |

### Agent & Configuration Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `pair` | Pair with a Bluetooth device ([docs](pairing_agent.md)) | `bleep pair AA:BB:... --interactive` |
| `agent` | Run a pairing agent ([docs](agent_mode.md)) | `bleep agent --mode interactive --cap keyboard` |
| `adapter-config` | Show/get/set Bluetooth adapter properties ([docs](adapter_config.md)) | `bleep adapter-config show --adapter hci0` |
| `user` | User-friendly interactive Bluetooth explorer ([docs](user_mode.md)) | `bleep user --scan 10 --device AA:BB:...` |
| `interactive` | Enter interactive REPL console | `bleep interactive` |
| `debug` | Enter the interactive Debug Mode shell (low-level D-Bus, GATT, media, classic — see [docs](debug_mode.md)) | `bleep debug --no-connect` |

> The `debug` subcommand and `python -m bleep.modes.debug` are equivalent and both supported.  `bleep debug` is the canonical, discoverable form; the `-m`-style invocation remains available for scripts and CI that already depend on it.

> **Note:** All examples above use the short-form `bleep` command (available after `pip install -e .`).  Substitute `python -m bleep` if the package is not pip-installed.

Characteristic reads are automatically archived in the local database (no CLI flag needed).

Run `bleep <command> --help` for detailed per-command options.

### Environment variables

| Variable | Effect |
|----------|--------|
| `BLEEP_LOG_LEVEL` | Override default log level (`DEBUG`, `INFO`, etc.) |
| `BLE_CTF_MAC` | Default MAC address for CTF challenges (used by `blectf` mode) |

### Hint convention (CLI vs. Debug Mode commands)

User-facing hint strings emitted from any CLI-reachable code path
(`bleep <subcommand>` and everything it transitively imports) **must** obey
one of the following two patterns.  This rule exists because debug-shell
commands like `audiocfg`, `mediaenum`, `audioplay`, `copp send`, `csdp`,
`copen`, etc. are not reachable from the CLI parser — referencing them
without context leaves the operator at a dead end.

1. **Reference a CLI subcommand directly.**  Example:

   > "Endpoint contention detected — rerun with `bleep audio-recon` for full details."

2. **Frame the hint with the literal phrase `Debug Mode`** so the operator
   knows they must enter the debug shell first.  The canonical wording is
   the parenthetical `(in Debug Mode: '<command>')` form.  Example:

   > "Endpoint contention: severity=warn (in Debug Mode: 'audiocfg --endpoints')"

A bare debug-shell command name (e.g. `"see 'audiocfg --endpoints'"`)
without the `Debug Mode` phrase is **forbidden** in CLI-reachable output.

The convention is enforced at test time by
[`tests/test_cli_hint_convention.py`](../../tests/test_cli_hint_convention.py),
which AST-walks every CLI-reachable module for string literals that
contain a known debug-shell command token and asserts that each such
literal also contains either `bleep debug` or `Debug Mode`.

To enter Debug Mode (both forms are equivalent and supported):

```bash
bleep debug                       # canonical form
python -m bleep.modes.debug       # legacy / scripting form
```

### Exit codes

`0` success, non-zero indicates an error (see stderr for details). 