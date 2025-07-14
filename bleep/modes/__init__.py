"""High-level run-modes for the BLEEP CLI.

Only a minimal *interactive* mode is provided for now; other historical modes
(user/scan/exploration/agent…) will be re-implemented incrementally once their
specific features are required.
"""

from importlib import import_module as _imp

__all__ = ["interactive", "scan", "agent", "exploration", "analysis", "aoi", "signal", "blectf", 
           "debug", "test", "picow", "scratch"]

interactive = _imp("bleep.modes.interactive")  # lazy-import to avoid D-Bus cost
scan = _imp("bleep.modes.scan")
agent = _imp("bleep.modes.agent")
exploration = _imp("bleep.modes.exploration")
analysis = _imp("bleep.modes.analysis")
aoi = _imp("bleep.modes.aoi")
signal = _imp("bleep.modes.signal")
blectf = _imp("bleep.modes.blectf")  # BLE CTF challenge mode
debug = _imp("bleep.modes.debug")  # Debug mode for device inspection
test = _imp("bleep.modes.test")  # Test mode for D-Bus interface testing
picow = _imp("bleep.modes.picow")  # PicoW mode for Raspberry Pi Pico W devices
scratch = _imp("bleep.modes.scratch")  # Scratch mode for batch processing 