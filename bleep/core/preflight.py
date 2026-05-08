"""
Preflight checks for BLEEP environment capabilities.

This module consolidates environment capability checks to inform users about
potential limitations before running BLEEP operations.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

__all__ = [
    "DeviceState",
    "PreflightReport",
    "EndpointOwner",
    "EndpointContentionReport",
    "check_device_state",
    "check_endpoint_contention",
    "print_preflight_summary",
    "require_adapter",
    "run_preflight_checks",
]


@dataclass
class DeviceState:
    """Snapshot of a Bluetooth device's connection/pairing/trust state."""

    connected: bool = False
    paired: bool = False
    trusted: bool = False

    @property
    def fully_bonded(self) -> bool:
        """True when the device is connected, paired, and trusted."""
        return self.connected and self.paired and self.trusted


def check_device_state(mac: str, transport: str = "auto") -> DeviceState:
    """Query a device's live state via the existing D-Bus wrappers.

    Parameters
    ----------
    mac : str
        Bluetooth MAC address (``"AA:BB:CC:DD:EE:FF"``).
    transport : str
        ``"le"`` for Low Energy, ``"classic"`` for BR/EDR, or ``"auto"``
        (default) which tries LE first, then Classic.

    Returns
    -------
    DeviceState
        Populated dataclass — fields default to ``False`` when the device is
        unknown to BlueZ (i.e. never discovered).
    """
    mac = mac.strip().upper()

    def _query_le() -> Optional[DeviceState]:
        try:
            from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy as _LEDev
            dev = _LEDev(mac)
            info = dev.get_device_info()
            return DeviceState(
                connected=bool(info.get("connected")),
                paired=bool(info.get("paired")),
                trusted=bool(info.get("trusted")),
            )
        except Exception:
            return None

    def _query_classic() -> Optional[DeviceState]:
        try:
            from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic as _ClassicDev
            dev = _ClassicDev(mac)
            info = dev.get_device_info()
            return DeviceState(
                connected=bool(info.get("connected")),
                paired=bool(info.get("paired")),
                trusted=bool(info.get("trusted")),
            )
        except Exception:
            return None

    if transport == "le":
        return _query_le() or DeviceState()
    if transport == "classic":
        return _query_classic() or DeviceState()
    # auto: try LE first (more common for modern peripherals), then Classic
    return _query_le() or _query_classic() or DeviceState()


def require_adapter(adapter_name: Optional[str] = None) -> bool:
    """Check that a Bluetooth adapter is present and ready.

    Returns ``True`` if the adapter is usable.  When it is **not** ready the
    function prints a uniform error message and returns ``False``, allowing
    callers to bail out early with a consistent UX.
    """
    try:
        from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter
        adapter = _Adapter(adapter_name) if adapter_name else _Adapter()
        if adapter.is_ready():
            return True
    except Exception:
        pass
    print_and_log("[!] Bluetooth adapter not found or not ready", LOG__GENERAL)
    return False


@dataclass
class PreflightReport:
    """Report of preflight check results."""
    
    bluetooth_tools: Dict[str, bool] = field(default_factory=dict)
    audio_tools: Dict[str, bool] = field(default_factory=dict)
    bt_audio_stack: Dict[str, bool] = field(default_factory=dict)
    bluetooth_config: Dict[str, Any] = field(default_factory=dict)
    bluez_version: Optional[str] = None
    python_dependencies: Dict[str, str] = field(default_factory=dict)
    
    def has_all_bluetooth_tools(self) -> bool:
        """Check if all required Bluetooth tools are available."""
        return all(self.bluetooth_tools.values())
    
    def has_audio_tools(self) -> bool:
        """Check if any audio tools are available."""
        return any(self.audio_tools.values())

    @property
    def has_bluetooth_audio_stack(self) -> bool:
        """True when at least one BT audio profile handler backend is detected."""
        return any(self.bt_audio_stack.values())
    
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
        "bluealsa-cli": shutil.which("bluealsactl") or shutil.which("bluealsa-cli"),
        "bluealsa-rfcomm": shutil.which("bluealsa-rfcomm"),
        # Analysis / codec
        "sox": shutil.which("sox"),
        "gst-launch-1.0": shutil.which("gst-launch-1.0"),
    }
    
    # Check for GStreamer Python bindings
    try:
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        tools["gstreamer_python"] = True
    except (ImportError, ValueError, AttributeError):
        tools["gstreamer_python"] = False
    
    return {tool: (path is not None if tool != "gstreamer_python" else tools[tool])
            for tool, path in tools.items()}


def _detect_distro() -> str:
    """Best-effort detection of the Linux distribution family."""
    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
        if "ubuntu" in content or "debian" in content or "mint" in content:
            return "debian"
        if "fedora" in content or "rhel" in content or "centos" in content:
            return "fedora"
        if "arch" in content or "manjaro" in content:
            return "arch"
        if "suse" in content or "opensuse" in content:
            return "suse"
    except (FileNotFoundError, PermissionError):
        pass
    return "unknown"


def _audio_stack_install_hint() -> str:
    """Return OS-specific install commands for Bluetooth audio support."""
    distro = _detect_distro()
    lines = ["    Install one of the following Bluetooth audio profile handlers:"]
    if distro == "debian":
        lines.append("      Option A (BlueALSA – lightweight, no PulseAudio needed):")
        lines.append("        sudo apt-get install bluez-alsa-utils")
        lines.append("      Option B (PulseAudio):")
        lines.append("        sudo apt-get install pulseaudio pulseaudio-module-bluetooth")
        lines.append("        pulseaudio --start")
        lines.append("      Option C (PipeWire):")
        lines.append("        sudo apt-get install pipewire pipewire-pulse libspa-0.2-bluetooth")
    elif distro == "fedora":
        lines.append("      Option A (PipeWire – default on Fedora):")
        lines.append("        sudo dnf install pipewire pipewire-pulseaudio")
        lines.append("      Option B (BlueALSA):")
        lines.append("        sudo dnf install bluez-alsa")
    elif distro == "arch":
        lines.append("      Option A (PipeWire):")
        lines.append("        sudo pacman -S pipewire pipewire-pulse pipewire-audio")
        lines.append("      Option B (BlueALSA):")
        lines.append("        yay -S bluez-alsa-git  # from AUR")
    else:
        lines.append("      BlueALSA: install 'bluez-alsa-utils' via your package manager")
        lines.append("      PulseAudio: install 'pulseaudio-module-bluetooth'")
        lines.append("      PipeWire: install 'pipewire' with BlueZ/SPA plugin")
    return "\n".join(lines)


def diagnose_audio() -> None:
    """Print a detailed audio stack diagnostic report."""
    from bleep.core.log import LOG__USER
    print_and_log("=" * 60, LOG__USER)
    print_and_log("BLEEP Audio Stack Diagnostic", LOG__USER)
    print_and_log("=" * 60, LOG__USER)

    bt_stack = _check_bluetooth_audio_stack()
    print_and_log("\n[1] Bluetooth Audio Profile Handlers:", LOG__USER)
    for name, detected in bt_stack.items():
        status = "DETECTED" if detected else "not found"
        print_and_log(f"    {name}: {status}", LOG__USER)

    has_any = any(bt_stack.values())
    if not has_any:
        print_and_log("\n    PROBLEM: No Bluetooth audio stack detected!", LOG__USER)
        print_and_log(_audio_stack_install_hint(), LOG__USER)
    else:
        print_and_log("\n    At least one audio stack is available.", LOG__USER)

    audio_tools = _check_audio_tools()
    print_and_log("\n[2] Audio Tools:", LOG__USER)
    for tool, avail in sorted(audio_tools.items()):
        status = "available" if avail else "MISSING"
        print_and_log(f"    {tool}: {status}", LOG__USER)

    print_and_log("\n[3] Distro Detection:", LOG__USER)
    print_and_log(f"    Family: {_detect_distro()}", LOG__USER)

    print_and_log("\n[4] BlueZ Version:", LOG__USER)
    ver = _check_bluez_version()
    print_and_log(f"    {ver}", LOG__USER)

    print_and_log("\n" + "=" * 60, LOG__USER)
    if has_any:
        print_and_log("Audio stack appears ready for Bluetooth media operations.", LOG__USER)
    else:
        print_and_log("Audio stack is NOT ready. Follow install hints above.", LOG__USER)
    print_and_log("=" * 60, LOG__USER)


def _check_bluetooth_audio_stack_detailed() -> Dict[str, Dict[str, Any]]:
    """Structured status of each Bluetooth audio profile-handler backend.

    Per-backend the returned dict carries:

    * ``present`` – CLI/tooling for the backend is installed.
    * ``running``/``loaded``/``plugin_loaded`` – runtime activity probes.
    * ``plugin_installed`` (PipeWire only) – ``libspa-bluez5.so`` is on disk.
    * ``status`` – one of ``active`` (handling BlueZ endpoints now),
      ``installed`` (tooling/plugin present but not loaded), or ``absent``.

    This is the authoritative probe; :func:`_check_bluetooth_audio_stack`
    collapses it to ``Dict[str, bool]`` for callers that only care about
    "is *any* handler available".
    """

    result: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # BlueALSA — tooling + live daemon probe (bluealsa-cli list-pcms)
    # ------------------------------------------------------------------
    bluealsa_cli = shutil.which("bluealsactl") or shutil.which("bluealsa-cli")
    bluealsa_aplay = shutil.which("bluealsa-aplay")
    bluealsa_present = bool(bluealsa_cli or bluealsa_aplay)
    bluealsa_running = False
    if bluealsa_cli:
        try:
            proc = subprocess.run(
                [bluealsa_cli, "list-pcms"],
                capture_output=True, text=True, timeout=3,
            )
            bluealsa_running = proc.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError,
                FileNotFoundError):
            bluealsa_running = False

    bluealsa_status = (
        "active" if bluealsa_running
        else ("installed" if bluealsa_present else "absent")
    )
    result["bluealsa"] = {
        "present": bluealsa_present,
        "running": bluealsa_running,
        "status": bluealsa_status,
    }

    # ------------------------------------------------------------------
    # PulseAudio with module-bluetooth-{discover,policy}
    # ------------------------------------------------------------------
    pactl = shutil.which("pactl")
    pulse_present = pactl is not None
    pulse_loaded = False
    if pactl:
        try:
            proc = subprocess.run(
                [pactl, "list", "modules", "short"],
                capture_output=True, text=True, timeout=5,
            )
            pulse_loaded = "bluetooth" in proc.stdout.lower()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError,
                FileNotFoundError):
            pulse_loaded = False

    pulse_status = (
        "active" if pulse_loaded
        else ("installed" if pulse_present else "absent")
    )
    result["pulseaudio_bt"] = {
        "present": pulse_present,
        "loaded": pulse_loaded,
        "status": pulse_status,
    }

    # ------------------------------------------------------------------
    # PipeWire — distinguish plugin on-disk vs. plugin loaded in graph
    # ------------------------------------------------------------------
    pw_cli = shutil.which("pw-cli")
    plugin_globs = [
        "/usr/lib/*/spa-0.2/bluez5/libspa-bluez5.so",
        "/usr/lib/spa-0.2/bluez5/libspa-bluez5.so",
        "/usr/lib64/spa-0.2/bluez5/libspa-bluez5.so",
        "/usr/local/lib/*/spa-0.2/bluez5/libspa-bluez5.so",
    ]
    plugin_installed = False
    for pattern in plugin_globs:
        if glob.glob(pattern):
            plugin_installed = True
            break

    plugin_loaded = False
    if pw_cli:
        try:
            proc = subprocess.run(
                [pw_cli, "list-objects"],
                capture_output=True, text=True, timeout=5,
            )
            plugin_loaded = "bluez" in proc.stdout.lower()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError,
                FileNotFoundError):
            plugin_loaded = False

    pipewire_present = pw_cli is not None
    pipewire_status = (
        "active" if plugin_loaded
        else ("installed" if (plugin_installed or pipewire_present) else "absent")
    )
    result["pipewire_bt"] = {
        "present": pipewire_present,
        "plugin_installed": plugin_installed,
        "plugin_loaded": plugin_loaded,
        "status": pipewire_status,
    }

    return result


def _detect_audio_stack_conflicts(
    detailed: Dict[str, Dict[str, Any]],
) -> List[str]:
    """Return human-readable warnings when multiple backends claim endpoints.

    BlueZ allows only one owner per :class:`MediaEndpoint1` tuple
    ``(adapter, UUID, codec)``.  If BlueALSA and a PulseAudio/PipeWire
    bluez5 plugin are both active they race during ``RegisterEndpoint``
    and whoever registers first wins — the loser's devices never surface
    as sinks/sources.  Downstream code (``cmd_audiocfg``) uses these
    strings verbatim.
    """

    warnings: List[str] = []
    bluealsa_active = detailed.get("bluealsa", {}).get("status") == "active"
    pulse_active = detailed.get("pulseaudio_bt", {}).get("status") == "active"
    pipewire_active = detailed.get("pipewire_bt", {}).get("status") == "active"

    if bluealsa_active and (pulse_active or pipewire_active):
        competitor = "PulseAudio" if pulse_active else "PipeWire"
        warnings.append(
            f"BlueALSA daemon is running alongside an active {competitor} "
            f"Bluetooth backend. Both try to register the same "
            f"MediaEndpoint1 tuples with BlueZ; whichever registered first "
            f"wins, and the loser's devices will not appear as sinks/sources."
        )

    pipewire = detailed.get("pipewire_bt", {})
    if (
        pipewire.get("present")
        and pipewire.get("plugin_installed")
        and not pipewire.get("plugin_loaded")
    ):
        warnings.append(
            "PipeWire is running and the bluez5 SPA plugin is installed, "
            "but no BlueZ objects are visible in the PipeWire graph. The "
            "plugin is not being loaded — another backend (e.g. BlueALSA) "
            "may hold the BlueZ endpoints, or the session manager "
            "(wireplumber) may be disabled or misconfigured."
        )

    return warnings


def _check_bluetooth_audio_stack() -> Dict[str, bool]:
    """Detect whether a Bluetooth audio profile handler backend is available.

    BlueZ ``Device1.Connect()`` requires a registered profile handler for at
    least one remote service.  Audio devices (phones, speakers) advertise
    A2DP/HFP/HSP — without a local audio stack BlueZ returns
    ``br-connection-profile-unavailable``.

    Returns a dict of backend names → detected boolean.  Semantics match the
    historic implementation so existing callers
    (:class:`PreflightReport`, :func:`diagnose_audio`) keep working:

    * ``bluealsa`` – ``True`` when tooling is present on ``PATH``.
    * ``pulseaudio_bt`` – ``True`` when ``module-bluetooth-*`` is loaded.
    * ``pipewire_bt`` – ``True`` when BlueZ objects are visible in
      ``pw-cli list-objects``.

    For the authoritative structured status (running vs. installed vs.
    absent, conflicts, PipeWire plugin on-disk vs. loaded) use
    :func:`_check_bluetooth_audio_stack_detailed`.
    """

    detailed = _check_bluetooth_audio_stack_detailed()
    return {
        "bluealsa": detailed.get("bluealsa", {}).get("present", False),
        "pulseaudio_bt": detailed.get("pulseaudio_bt", {}).get("loaded", False),
        "pipewire_bt": detailed.get("pipewire_bt", {}).get("plugin_loaded", False),
    }


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
    report.bt_audio_stack = _check_bluetooth_audio_stack()
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

    # Bluetooth audio profile handler backends
    print_and_log("\n[+] Bluetooth Audio Stack:", LOG__GENERAL)
    for backend, detected in sorted(report.bt_audio_stack.items()):
        status = "✓" if detected else "✗"
        print_and_log(f"  {status} {backend}", LOG__GENERAL)
    if not report.has_bluetooth_audio_stack:
        print_and_log(
            "  ⚠ No Bluetooth audio profile handlers detected.\n"
            "    Commands like 'gatt-enum' and 'media-enum' may fail with\n"
            "    'br-connection-profile-unavailable' on audio-capable devices.",
            LOG__GENERAL,
        )
        print_and_log(_audio_stack_install_hint(), LOG__GENERAL)
    
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

    if not report.has_bluetooth_audio_stack:
        print_and_log(
            "  ⚠ No BT audio stack — 'gatt-enum'/'media-enum' may fail on audio devices",
            LOG__GENERAL,
        )
    
    print_and_log("=" * 70, LOG__GENERAL)


# ===========================================================================
# MediaEndpoint1 contention pre-flight
# ===========================================================================
#
# BlueZ's AVDTP endpoint selection (a2dp_select_eps) picks *one* local
# MediaEndpoint1 per (adapter, profile UUID, codec) tuple during profile
# negotiation.  If another daemon (BlueALSA, PipeWire bluez5 SPA plugin,
# PulseAudio module-bluetooth) has already registered for the same tuple,
# BLEEP's newly-registered endpoint is very likely to lose the selection
# race — BlueZ never invokes our SetConfiguration callback, so
# BleepMediaEndpoint.wait_for_transport() times out after 15 s.
#
# This pre-flight detects the race condition *before* the device-connection
# cycle and lets callers short-circuit the failure with an actionable message.
#
# Two probe layers:
#   * Primary (zero cost)  – inference from _check_bluetooth_audio_stack_detailed
#     and AudioToolsHelper.list_bluealsa_pcms.  Each active backend is known
#     to register the four audio complement UUIDs by default, so we synthesise
#     one EndpointOwner per (backend, UUID) pair.
#   * Deep (opt-in)        – authoritative enumeration via
#     org.freedesktop.DBus.ListNames → per-name Introspect → property read →
#     GetConnectionUnixProcessID → /proc/<pid>/comm.  Every call goes through
#     bleep.dbus.timeout_manager.call_method_with_timeout so a congested
#     session bus cannot hang the scan.


@dataclass
class EndpointOwner:
    """A single MediaEndpoint1 owner discovered on the system bus.

    Attributes mirror the data the diagnostic surfaces consume.  Fields not
    available in the primary (inference-only) probe are left as ``None``.
    """

    backend: str                      # bluealsa | pipewire | pulseaudio | bleep | unknown
    bus_name: str = ""                # well-known or unique (":1.N"); "" for inferred
    object_path: str = ""             # endpoint path on that bus; "" for inferred
    uuid: Optional[str] = None        # complement profile UUID (if known)
    codec: Optional[int] = None       # codec ID (if known)
    pid: Optional[int] = None         # from GetConnectionUnixProcessID
    cmdline: Optional[str] = None     # /proc/<pid>/comm (short name preferred)
    inferred: bool = False            # True when synthesised by primary probe


@dataclass
class EndpointContentionReport:
    """Structured result of :func:`check_endpoint_contention`."""

    profile_uuid: str                      # what BLEEP wants to stream
    complement_uuid: str                   # what BLEEP will register
    competitors: List[EndpointOwner] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    severity: str = "none"                 # none | info | warn | block
    deep_probe_run: bool = False

    def has_blocker(self) -> bool:
        """True when the gate should short-circuit endpoint registration."""

        return self.severity == "block"


# Backend → complement UUIDs it registers with BlueZ by default.  All three
# supported audio daemons register the full audio set on startup, so any of
# them being ``active`` contends for every audio complement.
def _default_complements_for_backend() -> Dict[str, List[str]]:
    # Local import to avoid polluting the module namespace at import time and
    # to keep the constants module's UUID symbols lazily resolved.
    from bleep.bt_ref.constants import (
        A2DP_SINK_UUID,
        A2DP_SOURCE_UUID,
        HFP_AUDIO_GATEWAY_UUID,
        HFP_HANDS_FREE_UUID,
    )

    audio_uuids = [
        A2DP_SINK_UUID,
        A2DP_SOURCE_UUID,
        HFP_AUDIO_GATEWAY_UUID,
        HFP_HANDS_FREE_UUID,
    ]
    return {
        "bluealsa": list(audio_uuids),
        "pipewire": list(audio_uuids),
        "pulseaudio": list(audio_uuids),
    }


_PROCESS_NAME_BACKENDS = (
    # ordered most-specific first so "pipewire-pulse" matches pulseaudio-compat
    # but "pipewire" still resolves correctly
    ("bluealsa", "bluealsa"),
    ("pipewire-pulse", "pulseaudio"),
    ("pipewire", "pipewire"),
    ("wireplumber", "pipewire"),
    ("pulseaudio", "pulseaudio"),
    ("bleep", "bleep"),
)


def _backend_from_cmdline(cmdline: Optional[str]) -> str:
    """Map a process command line to a known backend identifier."""

    if not cmdline:
        return "unknown"
    lower = cmdline.lower()
    for needle, backend in _PROCESS_NAME_BACKENDS:
        if needle in lower:
            return backend
    return "unknown"


def _read_proc_comm(pid: int) -> Optional[str]:
    """Best-effort PID → short command name via /proc/<pid>/comm.

    Falls back to cmdline if comm is unreadable.  Returns None on failure so
    callers can classify the owner as ``"unknown"``.
    """

    try:
        with open(f"/proc/{pid}/comm", "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip() or None
    except (OSError, ValueError):
        pass
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
        if not raw:
            return None
        # cmdline is NUL-separated argv; first token is the executable.
        first = raw.split(b"\x00", 1)[0]
        return first.decode("utf-8", errors="replace") or None
    except (OSError, ValueError):
        return None


def _primary_endpoint_probe(
    profile_uuid: str,
    complement_uuid: str,
) -> List[EndpointOwner]:
    """Derive competitors from the structured backend-stack status.

    No D-Bus traffic is generated — we re-use
    :func:`_check_bluetooth_audio_stack_detailed` (which itself caches nothing
    but is cheap) and synthesise one :class:`EndpointOwner` per backend that
    is ``active`` and registers the complement UUID by default.
    """

    detailed = _check_bluetooth_audio_stack_detailed()
    default_map = _default_complements_for_backend()
    owners: List[EndpointOwner] = []

    for stack_key, backend_id in (
        ("bluealsa", "bluealsa"),
        ("pipewire_bt", "pipewire"),
        ("pulseaudio_bt", "pulseaudio"),
    ):
        info = detailed.get(stack_key, {})
        if info.get("status") != "active":
            continue
        if complement_uuid not in default_map.get(backend_id, []):
            continue
        owners.append(
            EndpointOwner(
                backend=backend_id,
                uuid=complement_uuid,
                inferred=True,
            )
        )
    return owners


def _deep_endpoint_probe(
    complement_uuid: str,
    *,
    timeout: float,
) -> List[EndpointOwner]:
    """Authoritative enumeration of MediaEndpoint1 owners on the system bus.

    Any failure (missing dependency, D-Bus error, timeout) returns an empty
    list so callers can fall back to the primary probe without disruption.
    """

    owners: List[EndpointOwner] = []

    try:
        import dbus  # noqa: WPS433 — optional dependency, imported lazily
        from xml.etree import ElementTree as _ET
        from bleep.dbus.timeout_manager import call_method_with_timeout
    except Exception as exc:  # pragma: no cover — env without python-dbus
        print_and_log(
            f"[debug] deep endpoint probe unavailable ({exc.__class__.__name__}: {exc})",
            LOG__DEBUG,
        )
        return owners

    try:
        bus = dbus.SystemBus()
    except Exception as exc:
        print_and_log(
            f"[debug] deep endpoint probe: SystemBus() failed: {exc}",
            LOG__DEBUG,
        )
        return owners

    # ------------------------------------------------------------------
    # ListNames() – all currently claimed bus names (unique + well-known)
    # ------------------------------------------------------------------
    try:
        dbus_proxy = bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus")
        dbus_iface = dbus.Interface(dbus_proxy, "org.freedesktop.DBus")
        names = call_method_with_timeout(dbus_iface, "ListNames", timeout=timeout)
    except Exception as exc:
        print_and_log(
            f"[debug] deep endpoint probe: ListNames failed: {exc}",
            LOG__DEBUG,
        )
        return owners

    candidate_paths = (
        "/",
        "/MediaEndpoint",
        "/bleep/media/endpoint",
        "/org/bluealsa",
    )

    def _walk_introspect(bus_name: str, root: str, depth: int = 0) -> List[str]:
        """Return every path under *root* that advertises MediaEndpoint1."""

        if depth > 4:
            return []
        found: List[str] = []
        try:
            proxy = bus.get_object(bus_name, root)
            introspect_iface = dbus.Interface(
                proxy, "org.freedesktop.DBus.Introspectable",
            )
            xml = call_method_with_timeout(
                introspect_iface, "Introspect", timeout=timeout,
            )
        except Exception:
            return []
        try:
            tree = _ET.fromstring(str(xml))
        except _ET.ParseError:
            return []

        for iface in tree.findall("interface"):
            if iface.get("name") == "org.bluez.MediaEndpoint1":
                found.append(root)
                break
        for node in tree.findall("node"):
            child = node.get("name")
            if not child:
                continue
            child_path = root.rstrip("/") + "/" + child
            found.extend(_walk_introspect(bus_name, child_path, depth + 1))
        return found

    for name in names:
        # Skip bus-daemon and obvious non-audio services to bound the scan.
        name_str = str(name)
        if name_str.startswith("org.freedesktop.") and not name_str.startswith(
            "org.freedesktop.DBus.",
        ):
            # Keep non-freedesktop well-known and all unique names; skip
            # the freedesktop.* umbrella (none of the audio daemons live there
            # except via the DBus bus-daemon itself which has no endpoints).
            # ``org.freedesktop.DBus.`` is the bus daemon; excluded by the
            # outer predicate so we never introspect it here.
            continue
        paths: List[str] = []
        for root in candidate_paths:
            paths.extend(_walk_introspect(name_str, root))
        if not paths:
            continue

        # Resolve owner PID once per bus name.
        pid: Optional[int] = None
        cmdline: Optional[str] = None
        try:
            pid_raw = call_method_with_timeout(
                dbus_iface,
                "GetConnectionUnixProcessID",
                name_str,
                timeout=timeout,
            )
            pid = int(pid_raw)
            cmdline = _read_proc_comm(pid)
        except Exception:
            pass

        backend = _backend_from_cmdline(cmdline) if cmdline else "unknown"

        for ep_path in paths:
            uuid_val: Optional[str] = None
            codec_val: Optional[int] = None
            try:
                ep_proxy = bus.get_object(name_str, ep_path)
                props_iface = dbus.Interface(
                    ep_proxy, "org.freedesktop.DBus.Properties",
                )
                uuid_val = str(call_method_with_timeout(
                    props_iface, "Get",
                    "org.bluez.MediaEndpoint1", "UUID",
                    timeout=timeout,
                ))
            except Exception:
                uuid_val = None
            try:
                codec_raw = call_method_with_timeout(
                    props_iface, "Get",
                    "org.bluez.MediaEndpoint1", "Codec",
                    timeout=timeout,
                )
                codec_val = int(codec_raw)
            except Exception:
                codec_val = None

            # Filter to the complement we care about when the UUID is known.
            if uuid_val is not None and uuid_val.lower() != complement_uuid.lower():
                continue

            owners.append(
                EndpointOwner(
                    backend=backend,
                    bus_name=name_str,
                    object_path=ep_path,
                    uuid=uuid_val or complement_uuid,
                    codec=codec_val,
                    pid=pid,
                    cmdline=cmdline,
                    inferred=False,
                )
            )
    return owners


def check_endpoint_contention(
    profile_uuid: str,
    device_mac: Optional[str] = None,
    *,
    deep_probe: bool = False,
    timeout: float = 3.0,
) -> EndpointContentionReport:
    """Detect whether another daemon has claimed the complement MediaEndpoint1.

    Parameters
    ----------
    profile_uuid : str
        The profile UUID BLEEP wants to stream (e.g. ``A2DP_SINK_UUID`` when
        recording from a microphone, ``A2DP_SOURCE_UUID`` when playing to a
        sink).  The *complement* UUID is computed via
        :data:`bleep.bt_ref.constants.PROFILE_UUID_COMPLEMENTS` and is what
        BLEEP will register locally.
    device_mac : Optional[str]
        Device MAC address (``"AA:BB:CC:DD:EE:FF"``) — reserved for future
        use when classifying device-scoped vs. adapter-scoped endpoints.
        Currently the same adapter-wide contention signal applies to every
        device, so the argument is accepted and logged but not filtered on.
    deep_probe : bool
        When ``True``, enumerate every ``MediaEndpoint1`` on the system bus
        via ``ListNames`` + ``Introspect``.  When ``False`` (default), rely
        on the zero-cost inference from the structured backend-stack status.
    timeout : float
        Per-D-Bus-call timeout for the deep probe.  Ignored when
        ``deep_probe=False``.

    Returns
    -------
    EndpointContentionReport
        Structured report with ``severity`` in ``{none, info, warn, block}``.
    """

    from bleep.bt_ref.constants import PROFILE_UUID_COMPLEMENTS

    complement_uuid = PROFILE_UUID_COMPLEMENTS.get(profile_uuid, profile_uuid)

    competitors: List[EndpointOwner] = _primary_endpoint_probe(
        profile_uuid, complement_uuid,
    )

    deep_ran = False
    if deep_probe:
        deep_ran = True
        deep = _deep_endpoint_probe(complement_uuid, timeout=timeout)
        # Merge: deep results supersede inferred entries for the same backend.
        seen_backends = {owner.backend for owner in deep if owner.backend != "bleep"}
        competitors = [
            o for o in competitors if o.backend not in seen_backends
        ] + [o for o in deep if o.backend != "bleep"]

    # Warnings from the coarse conflict detector are always relevant.
    warnings = _detect_audio_stack_conflicts(_check_bluetooth_audio_stack_detailed())

    # --- Severity classification ------------------------------------------
    # "block" is reserved for BlueALSA (observed failure mode) — other
    # backends are downgraded to "warn" until we have a confirmed failure
    # report for them.
    severity = "none"
    has_bluealsa = any(o.backend == "bluealsa" for o in competitors)
    has_other = any(
        o.backend in ("pipewire", "pulseaudio", "unknown") for o in competitors
    )
    if has_bluealsa:
        severity = "block"
    elif has_other or warnings:
        severity = "warn"
    elif competitors:
        severity = "info"

    # ``device_mac`` is accepted for API-completeness; log at DEBUG so future
    # maintainers can see which scope the pre-flight was called with.
    if device_mac:
        print_and_log(
            f"[debug] check_endpoint_contention: profile_uuid={profile_uuid} "
            f"complement={complement_uuid} device={device_mac} "
            f"deep={deep_probe} severity={severity} competitors={len(competitors)}",
            LOG__DEBUG,
        )

    return EndpointContentionReport(
        profile_uuid=profile_uuid,
        complement_uuid=complement_uuid,
        competitors=competitors,
        warnings=warnings,
        severity=severity,
        deep_probe_run=deep_ran,
    )
