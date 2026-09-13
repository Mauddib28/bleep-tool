from setuptools import setup, find_packages

# Check if PyGObject (gi) is already available system-wide
# This prevents pip from trying to build PyGObject from source when it's
# already installed via system package manager (apt, pacman, etc.)
_HAS_PYGOBJECT = False
try:
    import gi
    gi.require_version('GLib', '2.0')
    from gi.repository import GLib
    _HAS_PYGOBJECT = True
except (ImportError, ValueError, AttributeError):
    _HAS_PYGOBJECT = False

# Base requirements - always needed
# Only packages actually imported by the ``bleep`` runtime are listed here.
# dbus-python (``dbus``) and PyYAML (``yaml``) are the sole hard third-party
# imports; PyGObject (``gi``) is handled conditionally below.  Test-only and
# transitive/vestigial pins (pytest, numpy, xmltodict, pycairo, iniconfig,
# packaging, pluggy, Pygments) were removed after verifying none are imported
# anywhere under ``bleep/`` — pytest now lives in the ``test`` extra.
install_requires = [
    "dbus-python>=1.2.0",
    "PyYAML>=6.0",
]

# PyGObject is required for core D-Bus operations (scanning, connecting, monitoring)
# Also provides GStreamer Python bindings (gi.repository.Gst) for audio encoding
# If not system-installed, add it to install_requires
# If system-installed, add it to extras_require for users who want to manage via pip
if not _HAS_PYGOBJECT:
    # PyGObject not available - add to required dependencies
    # This will trigger pip to install it (or fail if build deps missing)
    install_requires.append("PyGObject>=3.48.0")
    # Building PyGObject from source (the pip path) pulls in pycairo for the
    # cairo integration layer. When PyGObject is supplied by the system
    # package manager this companion is unnecessary, so it is scoped here.
    install_requires.append("pycairo>=1.16")
    _pygobject_extras = {
        "monitor": [],  # No-op since it's already in install_requires
        "audio": [],  # No-op since it's already in install_requires
    }
else:
    # PyGObject is system-installed - make it optional for pip
    # System installation is preferred, but users can install via pip if needed
    _pygobject_extras = {
        "monitor": ["PyGObject>=3.48.0"],  # Optional for pip users
        "audio": ["PyGObject>=3.48.0"],  # Optional for audio encoding features
    }

# Test-only dependencies (CDU-M8a). pytest-timeout backs the `timeout` mark
# registered in pytest.ini so @pytest.mark.timeout(N) is honored rather than a
# no-op. Install with: pip install -e .[test]
_pygobject_extras["test"] = ["pytest>=8.0.0", "pytest-timeout>=2.3.0"]

setup(
    name="bleep",
    version="3.1.0",
    description="Bluetooth Landscape Exploration & Enumeration Platform",
    author="Paul A. Wortman",
    packages=find_packages(),
    install_requires=install_requires,
    extras_require=_pygobject_extras,
    package_data={
        "bleep.docs": ["*.md", "archive/*.md"],
        "bleep.bt_ref": [
            "sig_cache/*.yaml",
            "sig_cache/attribute_ids/*.yaml",
            "bluez_cache/*.h",
            "url_mappings.json",
            "vendor_specs_cache.json",
        ],
    },
    entry_points={
        'console_scripts': [
            'bleep=bleep.cli:main',
        ],
    },
    python_requires='>=3.10',
)
