"""
Preflight checks for BLEEP environment capabilities.

This module consolidates environment capability checks to inform users about
potential limitations before running BLEEP operations.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

__all__ = ["PreflightReport", "run_preflight_checks", "print_preflight_summary"]


@dataclass
class PreflightReport:
    """Report of preflight check results."""
    
    bluetooth_tools: Dict[str, bool] = field(default_factory=dict)
    audio_tools: Dict[str, bool] = field(default_factory=dict)
    bluetooth_config: Dict[str, Any] = field(default_factory=dict)
    bluez_version: Optional[str] = None
    python_dependencies: Dict[str, str] = field(default_factory=dict)
    
    def has_all_bluetooth_tools(self) -> bool:
        """Check if all required Bluetooth tools are available."""
        return all(self.bluetooth_tools.values())
    
    def has_audio_tools(self) -> bool:
        """Check if any audio tools are available."""
        return any(self.audio_tools.values())
    
    def get_missing_tools(self) -> List[str]:
        """Get list of missing tools."""
        missing = []
        for tool, available in self.bluetooth_tools.items():
            if not available:
                missing.append(tool)
        for tool, available in self.audio_tools.items():
            if not available:
                missing.append(tool)
        return missing


# Singleton instance to avoid repeated checks
_preflight_cache: Optional[PreflightReport] = None


def _check_bluetooth_tools() -> Dict[str, bool]:
    """
    Check availability of Bluetooth tools.
    
    Returns
    -------
    Dict[str, bool]
        Dictionary mapping tool names to availability status
    """
    tools = {
        "hciconfig": shutil.which("hciconfig"),
        "hcitool": shutil.which("hcitool"),
        "bluetoothctl": shutil.which("bluetoothctl"),
        "btmgmt": shutil.which("btmgmt"),
        "sdptool": shutil.which("sdptool"),
        "l2ping": shutil.which("l2ping"),
    }
    
    return {tool: path is not None for tool, path in tools.items()}


def _check_audio_tools() -> Dict[str, bool]:
    """
    Check availability of audio tools (PulseAudio, PipeWire, ALSA, and GStreamer).
    
    Returns
    -------
    Dict[str, bool]
        Dictionary mapping tool names to availability status
    """
    tools = {
        # PulseAudio
        "pactl": shutil.which("pactl"),
        "parecord": shutil.which("parecord"),
        "paplay": shutil.which("paplay"),
        "pacmd": shutil.which("pacmd"),
        # PipeWire (compat + native)
        "pw-cli": shutil.which("pw-cli"),
        "pw-record": shutil.which("pw-record"),
        "pw-play": shutil.which("pw-play"),
        "pw-dump": shutil.which("pw-dump"),
        "wpctl": shutil.which("wpctl"),
        # ALSA
        "aplay": shutil.which("aplay"),
        "arecord": shutil.which("arecord"),
        # BlueALSA
        "bluealsa-aplay": shutil.which("bluealsa-aplay"),
        "bluealsa-cli": shutil.which("bluealsa-cli"),
        "bluealsa-rfcomm": shutil.which("bluealsa-rfcomm"),
        # Analysis / codec
        "sox": shutil.which("sox"),
        "gst-launch-1.0": shutil.which("gst-launch-1.0"),
    }
    
    # Check for GStreamer Python bindings
    try:
        from gi.repository import Gst
        tools["gstreamer_python"] = True
    except (ImportError, ValueError, AttributeError):
        tools["gstreamer_python"] = False
    
    return {tool: (path is not None if tool != "gstreamer_python" else tools[tool])
            for tool, path in tools.items()}


def _check_bluetooth_config() -> Dict[str, Any]:
    """
    Check for local Bluetooth configuration files.
    
    Returns
    -------
    Dict[str, Any]
        Dictionary with config file information
    """
    config_dir = Path("/etc/bluetooth")
    result = {
        "config_dir_exists": config_dir.exists(),
        "config_files": [],
    }
    
    if config_dir.exists():
        # Check for common config files
        common_files = ["main.conf", "input.conf", "network.conf"]
        for config_file in common_files:
            file_path = config_dir / config_file
            if file_path.exists():
                result["config_files"].append(config_file)
    
    return result


def _check_bluez_version() -> Optional[str]:
    """
    Check BlueZ version via bluetoothctl.
    
    Returns
    -------
    Optional[str]
        BlueZ version string, or None if unavailable
    """
    bluetoothctl_path = shutil.which("bluetoothctl")
    if not bluetoothctl_path:
        return None
    
    try:
        result = subprocess.run(
            [bluetoothctl_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # bluetoothctl --version typically outputs: "bluetoothctl: 5.79"
            version_line = result.stdout.strip()
            if ":" in version_line:
                return version_line.split(":", 1)[1].strip()
            return version_line
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass
    
    return None


def _check_python_dependencies() -> Dict[str, str]:
    """
    Check Python dependency versions.
    
    Returns
    -------
    Dict[str, str]
        Dictionary mapping package names to version strings
    """
    dependencies = {}
    
    # Check dbus-python
    try:
        import dbus
        dependencies["dbus"] = getattr(dbus, "__version__", "unknown")
    except ImportError:
        dependencies["dbus"] = "not installed"
    
    # Check gi (PyGObject)
    try:
        from gi import __version__ as gi_version
        dependencies["gi"] = gi_version
    except ImportError:
        dependencies["gi"] = "not installed"
    
    return dependencies


def run_preflight_checks(use_cache: bool = True) -> PreflightReport:
    """
    Run all preflight checks and return a report.
    
    Parameters
    ----------
    use_cache : bool
        If True, return cached results if available (default: True)
    
    Returns
    -------
    PreflightReport
        Report containing all check results
    """
    global _preflight_cache
    
    if use_cache and _preflight_cache is not None:
        return _preflight_cache
    
    report = PreflightReport()
    
    # Run all checks
    report.bluetooth_tools = _check_bluetooth_tools()
    report.audio_tools = _check_audio_tools()
    report.bluetooth_config = _check_bluetooth_config()
    report.bluez_version = _check_bluez_version()
    report.python_dependencies = _check_python_dependencies()
    
    # Cache the results
    _preflight_cache = report
    
    return report


def print_preflight_summary(report: Optional[PreflightReport] = None) -> None:
    """
    Print a user-friendly summary of preflight check results.
    
    Parameters
    ----------
    report : Optional[PreflightReport]
        Preflight report to print. If None, runs checks first.
    """
    if report is None:
        report = run_preflight_checks()
    
    print_and_log("=" * 70, LOG__GENERAL)
    print_and_log("BLEEP Environment Capability Check", LOG__GENERAL)
    print_and_log("=" * 70, LOG__GENERAL)
    
    # Bluetooth tools
    print_and_log("\n[+] Bluetooth Tools:", LOG__GENERAL)
    for tool, available in sorted(report.bluetooth_tools.items()):
        status = "✓" if available else "✗"
        print_and_log(f"  {status} {tool}", LOG__GENERAL)
    
    # Audio tools
    print_and_log("\n[+] Audio Tools:", LOG__GENERAL)
    for tool, available in sorted(report.audio_tools.items()):
        status = "✓" if available else "✗"
        print_and_log(f"  {status} {tool}", LOG__GENERAL)
    
    # Bluetooth configuration
    print_and_log("\n[+] Bluetooth Configuration:", LOG__GENERAL)
    if report.bluetooth_config.get("config_dir_exists"):
        print_and_log(f"  ✓ /etc/bluetooth exists", LOG__GENERAL)
        config_files = report.bluetooth_config.get("config_files", [])
        if config_files:
            print_and_log(f"  ✓ Config files: {', '.join(config_files)}", LOG__GENERAL)
        else:
            print_and_log(f"  ⚠ No common config files found", LOG__GENERAL)
    else:
        print_and_log(f"  ✗ /etc/bluetooth not found", LOG__GENERAL)
    
    # BlueZ version
    print_and_log("\n[+] BlueZ Version:", LOG__GENERAL)
    if report.bluez_version:
        print_and_log(f"  ✓ {report.bluez_version}", LOG__GENERAL)
    else:
        print_and_log(f"  ✗ Unable to determine version", LOG__GENERAL)
    
    # Python dependencies
    print_and_log("\n[+] Python Dependencies:", LOG__GENERAL)
    for package, version in sorted(report.python_dependencies.items()):
        status = "✓" if version != "not installed" else "✗"
        print_and_log(f"  {status} {package}: {version}", LOG__GENERAL)
    
    # Summary
    print_and_log("\n" + "=" * 70, LOG__GENERAL)
    print_and_log("Summary:", LOG__GENERAL)
    
    missing = report.get_missing_tools()
    if missing:
        print_and_log(f"  ⚠ Missing tools: {', '.join(missing)}", LOG__GENERAL)
        print_and_log("  Note: Some BLEEP features may be limited without these tools.", LOG__GENERAL)
    else:
        print_and_log("  ✓ All checked tools are available", LOG__GENERAL)
    
    if not report.has_all_bluetooth_tools():
        print_and_log("  ⚠ Some Bluetooth Classic features may be unavailable", LOG__GENERAL)
    
    if not report.has_audio_tools():
        print_and_log("  ⚠ Audio sink/source operations will be unavailable", LOG__GENERAL)
    
    print_and_log("=" * 70, LOG__GENERAL)
