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
install_requires = [
    "dbus-python>=1.2.0",
    "PyYAML>=6.0",
    "pytest>=8.0.0",
    "xmltodict>=0.14.2",
    "numpy>=2.3.1",
]

# PyGObject is required for core D-Bus operations (scanning, connecting, monitoring)
# If not system-installed, add it to install_requires
# If system-installed, add it to extras_require for users who want to manage via pip
if not _HAS_PYGOBJECT:
    # PyGObject not available - add to required dependencies
    # This will trigger pip to install it (or fail if build deps missing)
    install_requires.append("PyGObject>=3.48.0")
    _pygobject_extras = {
        "monitor": [],  # No-op since it's already in install_requires
    }
else:
    # PyGObject is system-installed - make it optional for pip
    # System installation is preferred, but users can install via pip if needed
    _pygobject_extras = {
        "monitor": ["PyGObject>=3.48.0"],  # Optional for pip users
    }

setup(
    name="bleep",
    version="2.3.1",
    description="Bluetooth Landscape Exploration & Enumeration Platform",
    author="Paul A. Wortman",
    packages=find_packages(),
    install_requires=install_requires,
    extras_require=_pygobject_extras,
    package_data={
        "bleep.docs": ["*.md"],
        "bleep.bt_ref": ["yaml_cache/*.yaml", "url_mappings.json"],
    },
    entry_points={
        'console_scripts': [
            'bleep=bleep.cli:main',
        ],
    },
    python_requires='>=3.6',
)
