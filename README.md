# bleep-tool

Bluetooth Landscape Exploration & Enumeration Platform

## Setup Using Virtual Environment

```bash
# Create the virtual environment
python -m venv bti-env

# Activate the virtual environment
source bti-env/bin/activate

# Deactivate the virtual environment
deactivate
```

## Basic Usage

### Install

```bash
pip install -e .
```

**Troubleshooting:** If you hit build errors, install system dependencies first:

```bash
apt-get install build-essential libdbus-glib-1-dev libgirepository1.0-dev cmake libcairo2-dev libgirepository-2.0-dev
pip install dbus-python
```

### Usage Modes

#### Command Line Interface (CLI) Mode

```bash
python -m bleep.cli scan --timeout 30
python -m bleep.cli connect AA:DE:AD:BE:EF
```

#### BLE CTF Mode

```bash
python -m bleep.blectf
```

#### Debug Mode

```bash
python -m bleep.modes.debug
```

#### User Mode

```bash
python -m bleep.cli user --menu
```

#### Help Menu

```bash
python -m bleep --help   # top-level help / version
```

## Key Notes

Initial refactoring complete (v2.0.0)

- Done using a mix of AI models (Claude, ChatGPT) to develop refactoring, port over functionality, and perform parity checks.
- Not entirely verified and validated; be aware of potential issues.
  - **Note:** Modes outlined above are considered functional.
- The use of double `-m` flags does not work — instead grow off of the `bleep.` structure for sub-modules.
- System should now allow calling `bleep` instead of `python -m bleep.*`.

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
