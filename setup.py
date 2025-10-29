from setuptools import setup, find_packages

setup(
    name="bleep",
    version="2.3.1",
    description="Bluetooth Landscape Exploration & Enumeration Platform",
    author="Paul A. Wortman",
    packages=find_packages(),
    install_requires=[
        "dbus-python>=1.2.0",
        "PyYAML>=6.0",  # For UUID generation/parsing
        "pytest>=8.0.0",
        ],
    extras_require={
        "monitor": ["PyGObject>=3.48.0"],  # Only needed for --monitor and GLib-based helpers
    },
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
