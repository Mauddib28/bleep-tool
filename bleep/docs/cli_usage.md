# CLI quick-start

The CLI entry-point is the `bleep` module itself and is typically launched with the `-m` flag:

```bash
python -m bleep --help   # top-level help / version
```

### Common sub-commands

| Command | Purpose | Example |
|---------|---------|---------|
| `scan` | Passive BLE scan for advertising packets | `python -m bleep scan --timeout 15` |
| `connect` | Connect to a target and enumerate its GATT DB | `python -m bleep connect AA:BB:CC:DD:EE:FF` |
| `gatt-enum` | Quick or deep GATT enumeration incl. permission/landmine reports | `python -m bleep gatt-enum AA:BB:... --deep` |
| `media-enum` | Enumerate AVRCP / MediaPlayer capabilities | `python -m bleep media-enum AA:BB:... --verbose` |
| `agent` | Run a pairing agent (simple/interactive) | `python -m bleep agent --mode simple` |
| `explore` | Scan & produce JSON mapping for later offline analysis | `python -m bleep explore AA:BB:CC:DD:EE:FF --out dump.json` |
| `analyse` | Post-process one or more JSON dumps | `python -m bleep analyse dump1.json dump2.json` |
| `signal` | Subscribe to notifications/indications | `python -m bleep signal AA:BB:... char002d --time 60` |

Run `python -m bleep <command> --help` for detailed per-command options.

### Environment variables

| Variable | Effect |
|----------|--------|
| `BLEEP_LOG_LEVEL` | Override default log level (`DEBUG`, `INFO`, etc.) |
| `BLE_CTF_MAC` | Default MAC address for CTF challenges (used by `blectf` mode) |

### Exit codes

`0` success, non-zero indicates an error (see stderr for details). 