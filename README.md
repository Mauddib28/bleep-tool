# bleep-tool

**BLEEP** — Bluetooth Landscape Exploration & Enumeration Platform

A D-Bus/BlueZ-based toolkit for discovering, enumerating, and interacting with
Bluetooth Low Energy **and** Bluetooth Classic (BR/EDR) devices: scanning,
GATT/SDP enumeration, media & audio, pairing/agents, an observation database,
and an interactive debug shell.

## Setup Using Virtual Environment

```bash
# Create the virtual environment
python -m venv bti-env

# Activate the virtual environment
source bti-env/bin/activate

# Deactivate the virtual environment
deactivate
```

## Install

```bash
pip install -e .
```

This installs the `bleep` console entry point (equivalent to `python -m bleep`).

> **PyGObject / D-Bus:** BLEEP requires PyGObject (`python3-gi`) for core D-Bus
> operations (scan, connect, monitor). Prefer the system package — it is
> auto-detected by `setup.py` and left out of the pip requirements when present:
> - Debian/Ubuntu/Kali: `sudo apt-get install python3-gi`
> - Arch: `sudo pacman -S python-gobject`

**Troubleshooting:** If you hit build errors installing from pip, install the
system build dependencies first:

```bash
sudo apt-get install build-essential cmake pkg-config \
    libdbus-1-dev libgirepository1.0-dev libgirepository-2.0-dev \
    libcairo2-dev gir1.2-glib-2.0
pip install dbus-python
```

### Run the environment check

```bash
bleep --check-env        # tools, configs, dependencies, BlueZ experimental surfaces
bleep --diagnose-audio   # detailed audio-stack diagnostic + install guidance
```

## Usage

After `pip install -e .` the short-form `bleep` command is available. The
`python -m bleep` form is equivalent and works without installation.

```bash
bleep --help             # top-level help / version
bleep --version          # e.g. "BLEEP 3.1.0 (DB schema v20)"
bleep                    # interactive REPL (no subcommand)
```

### Common commands

```bash
bleep scan --timeout 30 --variant naggy          # BLE scan (passive|naggy|pokey|brute)
bleep connect AA:BB:CC:DD:EE:FF                   # connect + enumerate (auto-routes Classic)
bleep gatt-enum AA:BB:CC:DD:EE:FF --deep          # single-pass GATT enumeration
bleep explore AA:BB:CC:DD:EE:FF --out dump.json   # dump to JSON for offline analysis
bleep classic-scan --timeout 10                   # Bluetooth Classic (BR/EDR) scan
bleep survey --collector hci0:le --duration 120   # long-duration device census
bleep db list                                     # query the observation database
bleep ctf --discover --device CC:50:E3:B6:BC:A6   # BLE CTF solver
bleep user --menu                                 # guided, menu-driven explorer
bleep debug                                        # interactive low-level debug shell
```

BLEEP exposes a large command surface (BLE, Classic profiles — PBAP/OPP/MAP/FTP/PAN/SPP,
media & audio, pairing/agents, advertising, mesh, Assets-of-Interest, and more).
For the **full, authoritative command reference** with per-command flags and
examples, see the CLI quick-start:

- [`bleep/docs/cli_usage.md`](bleep/docs/cli_usage.md)

Run `bleep <command> --help` for detailed per-command options.

### Legacy `-m` module forms

The canonical, discoverable form is `bleep <command>`. Direct module entry
points remain available for scripts/CI that already depend on them:

```bash
python -m bleep.cli scan --timeout 30    # same as: bleep scan --timeout 30
python -m bleep.modes.debug              # same as: bleep debug
python -m bleep.modes.blectf             # same as: bleep ctf
```

## Key Notes

Current release: **v3.1.0** (see [`bleep/docs/changelog.md`](bleep/docs/changelog.md)).

- Developed and refactored with the assistance of a mix of AI models (Claude,
  ChatGPT) for porting functionality and parity checks. Not exhaustively
  validated — be aware of potential issues, though the modes above are
  considered functional.
- Docker is supported: build/run with [`docker.sh`](docker.sh) (see
  [`dockerfile`](dockerfile)).

## Documentation

Full internal documentation lives alongside the code in [`bleep/docs/`](bleep/docs/README.md).

---

## Research / Source Documentation

| Presentation | Slides | Recording |
|---|---|---|
| D-Bus and Python research + development — CackalackyCon 2024 | [Slides](https://github.com/Mauddib28/bleep--2024--CackalackyCon-Slides) | [YouTube](https://www.youtube.com/watch?v=kFSlYIJMxOI) |
| Safari Hunt of Bluetooth Wildlife + Cartography — BSidesLV 2024 | [Slides](https://github.com/Mauddib28/bleep--2024--BsidesLV-Slides) | [YouTube](https://youtu.be/AZ0U3bhRYkA) |
| Technical function and review of BLEEP + mapping — DefCon 32 | [Slides](https://github.com/Mauddib28/bleep--2024--DefCon-DemoLabs-Slides) | — |
| Bluetooth Wildlife dissection — CackalackyCon 2025 | [Slides](https://github.com/Mauddib28/bleep--2025--CackalackyCon-Slides) | — |
| BLEEP D-Bus and Unix ALSA — CackalackyCon 2026 | [Slides](https://github.com/Mauddib28/bleep--2026--CackalackyCon-Slides) | [YouTube](https://www.youtube.com/watch?v=3BKD1MsC9Fc) |
