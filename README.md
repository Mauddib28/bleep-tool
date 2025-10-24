# bleep-tool

Bluetooth Landscape Exploration &amp; Enumeration Platform

## Setup Using Virtual Environment:

### Setup Environment
python -m venv bti-env

### Activate the Virtual Environment
source bti-env/bin/activate

### Deactivate the Virtual Environment
deactivate

## Basic Usage:

### Install:
pip install -e .
#### Troubleshooting:
apt-get install build-essential libdbus-glib-1-dev libgirepository1.0-dev cmake libcairo2-dev libgirepository-2.0-dev
pip install dbus-python

### Usage Modes:
#### Command Line Interface (CLI) Mode:
python -m bleep.cli scan --timeout 30
python -m bleep.cli connect AA:DE:AD:BE:EF

#### BLE CTF Mode:
python -m bleep.blectf

#### Debug Mode:
python -m bleep.modes.debug

#### User Mode:
python -m bleep.cli user --menu

#### Help Menu
python -m bleep --help   # top-level help / version

## Key Notes:
Inital refactoring complete (v2.0.0)
- Done using mix of AI models (Claude, ChatGPT) to develop refactoring, porting over functionality, and performing parity checks
- Not entirely verified and valdiated; be aware of potential issues
    - Note: Modes outlined above are considered functional
- The use of double "-m" flags does not work.... instead grow off of the bleep. structure for sub-modules
- System should NOW allow call of 'bleep' instead of 'python -m bleep.*'

==========================================================================================
		            bleep platform - research / source documentation
==========================================================================================

Slides presenting D-Bus and Python research + development at CackalackyCon 2024:        https://github.com/Mauddib28/bleep--2024--CackalackyCon-Slides
    - YouTube Recording of the Presentation:                                            https://www.youtube.com/watch?v=kFSlYIJMxOI
Slides presenting Safari Hunt of Bluetooth Wildlife + Cartography at BSidesLV 2024:     https://github.com/Mauddib28/bleep--2024--BsidesLV-Slides
    - YouTube Recording of the Presentation:                                            https://youtu.be/AZ0U3bhRYkA
Slides presenting technical function and review of BLEEP + mapping at DefCon 32:        https://github.com/Mauddib28/bleep--2024--DefCon-DemoLabs-Slides
Slides presenting Bluetooth Wildlife dissection at CackalackyCon 2025:                  https://github.com/Mauddib28/bleep--2025--CackalackyCon-Slides
