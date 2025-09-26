from setuptools import setup, find_packages

setup(
    name="bleep",
    version="2.0.0",
    description="Bluetooth Landscape Exploration & Enumeration Platform",
    author="Paul A. Wortman",
    packages=find_packages(),
    install_requires=[
        "dbus-python>=1.2.0",
        "PyYAML>=6.0",  # For UUID generation/parsing
        # PyGObject/gi is optional (needed for property monitoring). Installing via pip
        # works on many Linux distros where the underlying GLib introspection libs exist.
        # Users on minimal systems can choose the extra instead.
        "PyGObject>=3.48.0",  # enable --monitor and other GLib-based helpers
        "pytest>=8.0.0",
        ],
    package_data={
        "bleep.docs": ["*.md"],
    },
    entry_points={
        'console_scripts': [
            'bleep=bleep.cli:main',
        ],
    },
    python_requires='>=3.6',
) 
