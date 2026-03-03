"""
Audio tools helper for ALSA/PipeWire/PulseAudio operations.

This module provides wrappers for interacting with audio backends to support
Bluetooth audio sink/source operations.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Dict, List, Optional, Any

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL

__all__ = [
    "AudioToolsHelper",
    "get_audio_backend",
    "check_audio_file_has_content",
]


def check_audio_file_has_content(audio_file_path: str, sox_path: Optional[str] = None) -> bool:
    """
    Use sox to determine if an audio file contains non-zero amplitude (has audio).

    Runs: sox <file> -n stat 2>&1, parses Maximum and Minimum amplitude;
    if both are 0.0 then the file is considered to have no audio content.

    Parameters
    ----------
    audio_file_path : str
        Path to the audio file (e.g. WAV).
    sox_path : Optional[str]
        Path to sox binary. If None, uses shutil.which("sox").

    Returns
    -------
    bool
        True if the file appears to contain audio (non-zero amplitude), False otherwise.
    """
    path = sox_path or shutil.which("sox")
    if not path or not os.path.isfile(audio_file_path):
        return False
    try:
        result = subprocess.run(
            [path, audio_file_path, "-n", "stat"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = (result.stdout or "") + (result.stderr or "")
        max_amp: Optional[float] = None
        min_amp: Optional[float] = None
        for line in out.splitlines():
            if "Maximum amplitude" in line and ":" in line:
                try:
                    max_amp = float(line.split(":")[-1].strip())
                except ValueError:
                    pass
            if "Minimum amplitude" in line and ":" in line:
                try:
                    min_amp = float(line.split(":")[-1].strip())
                except ValueError:
                    pass
        if max_amp is not None and min_amp is not None:
            return bool(max_amp != 0.0 or min_amp != 0.0)
        return False
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        return False


class AudioToolsHelper:
    """
    Helper class for audio backend operations.
    
    Provides methods to interact with PipeWire, PulseAudio, or ALSA
    for Bluetooth audio device management.
    """
    
    def __init__(self):
        """Initialize the audio tools helper."""
        self._backend = None
        # PulseAudio
        self._pactl_path = shutil.which("pactl")
        self._pacmd_path = shutil.which("pacmd")
        self._paplay_path = shutil.which("paplay")
        self._parecord_path = shutil.which("parecord")
        # PipeWire
        self._pw_cli_path = shutil.which("pw-cli")
        self._pw_dump_path = shutil.which("pw-dump")
        self._pw_play_path = shutil.which("pw-play")
        self._pw_record_path = shutil.which("pw-record")
        self._wpctl_path = shutil.which("wpctl")
        # ALSA
        self._aplay_path = shutil.which("aplay")
        self._arecord_path = shutil.which("arecord")
        # BlueALSA
        self._bluealsa_cli_path = shutil.which("bluealsa-cli")
        self._bluealsa_aplay_path = shutil.which("bluealsa-aplay")
        # Analysis
        self._sox_path = shutil.which("sox")
    
    def get_audio_backend(self) -> str:
        """
        Detect the active audio backend.

        Returns
        -------
        str
            One of: ``'pipewire'`` (PipeWire with PA compat), ``'pipewire_native'``
            (PipeWire without PA compat), ``'pulseaudio'``, ``'bluealsa'``, or
            ``'none'``.
        """
        if self._backend is not None:
            return self._backend

        pw_running = False
        pa_compat = False

        # Check for PipeWire daemon
        if self._pw_cli_path:
            try:
                result = subprocess.run(
                    [self._pw_cli_path, "info"],
                    capture_output=True, text=True, timeout=2,
                )
                if result.returncode == 0:
                    pw_running = True
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass

        # Check for PulseAudio (or PA compat layer)
        if self._pactl_path:
            try:
                result = subprocess.run(
                    [self._pactl_path, "info"],
                    capture_output=True, text=True, timeout=2,
                )
                if result.returncode == 0:
                    if pw_running or "PipeWire" in result.stdout or "pipewire" in result.stdout.lower():
                        pa_compat = True
                    else:
                        self._backend = "pulseaudio"
                        return self._backend
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass

        if pw_running:
            self._backend = "pipewire" if pa_compat else "pipewire_native"
            return self._backend

        # Check for BlueALSA as standalone backend
        if self.is_bluealsa_running():
            self._backend = "bluealsa"
            return self._backend

        self._backend = "none"
        return self._backend
    
    def list_audio_sinks(self) -> List[Dict[str, Any]]:
        """
        List available audio sinks.
        
        Returns
        -------
        List[Dict[str, Any]]
            List of sink dictionaries with name, description, and state
        """
        backend = self.get_audio_backend()
        sinks = []
        
        if backend == "pipewire" and self._pw_cli_path:
            try:
                result = subprocess.run(
                    [self._pw_cli_path, "list-objects", "Sink"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Parse PipeWire output (simplified - would need more robust parsing for production)
                    for line in result.stdout.splitlines():
                        if "Sink" in line and "id:" in line:
                            # Extract basic info (simplified parsing)
                            sink_info = {
                                "name": line.strip(),
                                "backend": "pipewire",
                                "raw_output": line,
                            }
                            sinks.append(sink_info)
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass
        
        elif backend == "pulseaudio" and self._pactl_path:
            try:
                result = subprocess.run(
                    [self._pactl_path, "list", "sinks", "short"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 2:
                                sink_info = {
                                    "index": parts[0],
                                    "name": parts[1],
                                    "description": " ".join(parts[2:]) if len(parts) > 2 else "",
                                    "backend": "pulseaudio",
                                }
                                sinks.append(sink_info)
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass
        
        return sinks
    
    def list_audio_sources(self) -> List[Dict[str, Any]]:
        """
        List available audio sources.
        
        Returns
        -------
        List[Dict[str, Any]]
            List of source dictionaries with name, description, and state
        """
        backend = self.get_audio_backend()
        sources = []
        
        if backend == "pipewire" and self._pw_cli_path:
            try:
                result = subprocess.run(
                    [self._pw_cli_path, "list-objects", "Source"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if "Source" in line and "id:" in line:
                            source_info = {
                                "name": line.strip(),
                                "backend": "pipewire",
                                "raw_output": line,
                            }
                            sources.append(source_info)
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass
        
        elif backend == "pulseaudio" and self._pactl_path:
            try:
                result = subprocess.run(
                    [self._pactl_path, "list", "sources", "short"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 2:
                                source_info = {
                                    "index": parts[0],
                                    "name": parts[1],
                                    "description": " ".join(parts[2:]) if len(parts) > 2 else "",
                                    "backend": "pulseaudio",
                                }
                                sources.append(source_info)
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass
        
        return sources
    
    def is_bluetooth_audio_available(self) -> bool:
        """
        Check if Bluetooth audio capabilities are available.
        
        Returns
        -------
        bool
            True if Bluetooth audio sinks/sources are available
        """
        sinks = self.list_audio_sinks()
        sources = self.list_audio_sources()
        
        # Check for Bluetooth-related sinks/sources
        bluetooth_keywords = ["bluez", "bluetooth", "a2dp", "hsp", "hfp"]
        
        for sink in sinks:
            sink_str = str(sink).lower()
            if any(keyword in sink_str for keyword in bluetooth_keywords):
                return True
        
        for source in sources:
            source_str = str(source).lower()
            if any(keyword in source_str for keyword in bluetooth_keywords):
                return True
        
        return False
    
    def list_alsa_devices(self) -> List[Dict[str, Any]]:
        """
        List ALSA devices directly using 'aplay -l' and 'arecord -l'.
        
        This method bypasses PulseAudio/PipeWire and queries ALSA directly.
        Useful for identifying hardware devices that may not be exposed through
        higher-level audio servers.
        
        Returns
        -------
        List[Dict[str, Any]]
            List of ALSA device dictionaries with card, device, and name information.
            Each dict contains:
            - card: Card number (int)
            - device: Device number (int)
            - name: Device name (str)
            - type: 'playback' or 'capture' (str)
        """
        devices = []
        
        # List playback devices
        if self._aplay_path:
            try:
                result = subprocess.run(
                    [self._aplay_path, "-l"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        # Parse lines like: "card 0: PCH [HDA Intel PCH], device 0: ALC892 Analog [ALC892 Analog]"
                        match = re.match(r"card (\d+):\s+(\S+)\s+\[([^\]]+)\],\s+device (\d+):\s+(\S+)\s+\[([^\]]+)\]", line)
                        if match:
                            devices.append({
                                "card": int(match.group(1)),
                                "device": int(match.group(4)),
                                "card_name": match.group(2),
                                "card_description": match.group(3),
                                "device_name": match.group(5),
                                "device_description": match.group(6),
                                "type": "playback",
                                "alsa_id": f"hw:{match.group(1)},{match.group(4)}",
                            })
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass
        
        # List capture devices
        if self._arecord_path:
            try:
                result = subprocess.run(
                    [self._arecord_path, "-l"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        # Parse lines like: "card 0: PCH [HDA Intel PCH], device 0: ALC892 Analog [ALC892 Analog]"
                        match = re.match(r"card (\d+):\s+(\S+)\s+\[([^\]]+)\],\s+device (\d+):\s+(\S+)\s+\[([^\]]+)\]", line)
                        if match:
                            devices.append({
                                "card": int(match.group(1)),
                                "device": int(match.group(4)),
                                "card_name": match.group(2),
                                "card_description": match.group(3),
                                "device_name": match.group(5),
                                "device_description": match.group(6),
                                "type": "capture",
                                "alsa_id": f"hw:{match.group(1)},{match.group(4)}",
                            })
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass
        
        return devices
    
    def get_alsa_device_info(self, device_name: str) -> Dict[str, Any]:
        """
        Get detailed ALSA device information using 'aplay -D <device> --dump-hw-params'.
        
        Parameters
        ----------
        device_name : str
            ALSA device name (e.g., 'hw:0,0' or 'plughw:0,0')
        
        Returns
        -------
        Dict[str, Any]
            Dictionary containing hardware parameters or empty dict if unavailable.
            May include: access, format, subformat, channels, rate, etc.
        """
        info = {}
        
        # Try aplay first (playback devices)
        if self._aplay_path:
            try:
                result = subprocess.run(
                    [self._aplay_path, "-D", device_name, "--dump-hw-params"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Parse hardware parameters
                    for line in result.stdout.splitlines():
                        if ":" in line:
                            key, value = line.split(":", 1)
                            info[key.strip()] = value.strip()
                    info["type"] = "playback"
                    return info
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass
        
        # Try arecord (capture devices)
        if self._arecord_path:
            try:
                result = subprocess.run(
                    [self._arecord_path, "-D", device_name, "--dump-hw-params"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Parse hardware parameters
                    for line in result.stdout.splitlines():
                        if ":" in line:
                            key, value = line.split(":", 1)
                            info[key.strip()] = value.strip()
                    info["type"] = "capture"
                    return info
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass
        
        return info
    
    def extract_mac_from_alsa_device(self, device_name: str) -> Optional[str]:
        """
        Extract MAC address from ALSA/PulseAudio/PipeWire device name.
        
        This method performs pure string parsing - no D-Bus interaction.
        Common patterns:
        - PulseAudio: "bluez_sink.XX_XX_XX_XX_XX_XX.a2dp_sink"
        - PipeWire: "bluez_output.XX_XX_XX_XX_XX_XX.a2dp_sink"
        - ALSA: May contain MAC in various formats
        
        Parameters
        ----------
        device_name : str
            Device name from audio backend
        
        Returns
        -------
        Optional[str]
            MAC address in format "XX:XX:XX:XX:XX:XX" or None if not found
        """
        if not device_name:
            return None
        
        # Pattern 1: bluez_sink.XX_XX_XX_XX_XX_XX.profile
        # Pattern 2: bluez_source.XX_XX_XX_XX_XX_XX.profile
        # Pattern 3: bluez_output.XX_XX_XX_XX_XX_XX.profile
        # Pattern 4: bluez_input.XX_XX_XX_XX_XX_XX.profile
        
        # Match MAC address pattern (6 hex octets separated by underscores or colons)
        mac_patterns = [
            r"([0-9A-Fa-f]{2}[:_][0-9A-Fa-f]{2}[:_][0-9A-Fa-f]{2}[:_][0-9A-Fa-f]{2}[:_][0-9A-Fa-f]{2}[:_][0-9A-Fa-f]{2})",
            r"([0-9A-Fa-f]{2}-[0-9A-Fa-f]{2}-[0-9A-Fa-f]{2}-[0-9A-Fa-f]{2}-[0-9A-Fa-f]{2}-[0-9A-Fa-f]{2})",
        ]
        
        for pattern in mac_patterns:
            match = re.search(pattern, device_name, re.IGNORECASE)
            if match:
                mac = match.group(1)
                # Normalize to colon-separated format
                mac = mac.replace("_", ":").replace("-", ":")
                return mac.lower()
        
        return None
    
    def identify_bluetooth_profiles_from_alsa(
        self, 
        mac_address: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Identify Bluetooth audio profiles by analyzing ALSA device names.
        
        This method uses ONLY external tools (pactl, pw-cli, aplay) to enumerate
        devices, then correlates device names with known Bluetooth profile patterns.
        No D-Bus interaction occurs in this method.
        
        Parameters
        ----------
        mac_address : Optional[str]
            Optional MAC address to filter results. If None, returns all Bluetooth devices.
        
        Returns
        -------
        Dict[str, List[Dict[str, Any]]]
            Dictionary mapping profile UUIDs to lists of device information.
            Keys are profile UUIDs (e.g., "0000110b-0000-1000-8000-00805f9b34fb" for A2DP Sink).
            Values are lists of device info dicts containing:
            - sink_name or source_name: Device name from audio backend
            - mac_address: Extracted MAC address
            - profile_name: Human-readable profile name
            - backend: Audio backend ('pipewire', 'pulseaudio', 'alsa')
        
        Note
        ----
        This method does NOT interact with D-Bus. It only uses external tool
        output to infer profile information from device naming conventions.
        For complete profile information including D-Bus transport details,
        use AudioProfileCorrelator from audio_profile_correlator.py.
        """
        # Import centralized constants
        from bleep.bt_ref.constants import (
            AUDIO_PROFILE_NAMES,
            A2DP_SINK_UUID,
            A2DP_SOURCE_UUID,
            HFP_HANDS_FREE_UUID,
            HFP_AUDIO_GATEWAY_UUID,
            HSP_AUDIO_GATEWAY_UUID,
            HSP_HEADSET_UUID,
            get_profile_name,
        )
        
        # Profile name patterns (from device naming conventions)
        profile_patterns = {
            "a2dp_sink": A2DP_SINK_UUID,
            "a2dp_source": A2DP_SOURCE_UUID,
            "hfp": HFP_HANDS_FREE_UUID,
            "hfp_ag": HFP_AUDIO_GATEWAY_UUID,
            "hfp_hf": HFP_HANDS_FREE_UUID,
            "hsp": HSP_AUDIO_GATEWAY_UUID,
            "hsp_ag": HSP_AUDIO_GATEWAY_UUID,
            "hsp_hs": HSP_HEADSET_UUID,
        }
        
        result: Dict[str, List[Dict[str, Any]]] = {}
        
        # Get sinks and sources from existing methods
        sinks = self.list_audio_sinks()
        sources = self.list_audio_sources()
        
        # Process sinks
        for sink in sinks:
            sink_name = sink.get("name", "")
            if not sink_name:
                continue
            
            # Check if this is a Bluetooth device
            if not any(keyword in sink_name.lower() for keyword in ["bluez", "bluetooth"]):
                continue
            
            # Extract MAC address
            mac = self.extract_mac_from_alsa_device(sink_name)
            if not mac:
                continue
            
            # Filter by MAC if specified
            if mac_address and mac.lower() != mac_address.lower():
                continue
            
            # Identify profile from device name pattern
            sink_lower = sink_name.lower()
            profile_uuid = None
            profile_name = None
            
            for pattern, uuid in profile_patterns.items():
                if pattern in sink_lower:
                    profile_uuid = uuid
                    profile_name = get_profile_name(uuid)
                    break
            
            # Default to A2DP Sink if no specific pattern found but it's a Bluetooth sink
            if not profile_uuid:
                profile_uuid = A2DP_SINK_UUID
                profile_name = get_profile_name(profile_uuid)
            
            # Add to result
            if profile_uuid not in result:
                result[profile_uuid] = []
            
            result[profile_uuid].append({
                "sink_name": sink_name,
                "mac_address": mac,
                "profile_name": profile_name,
                "backend": sink.get("backend", "unknown"),
                "description": sink.get("description", ""),
            })
        
        # Process sources
        for source in sources:
            source_name = source.get("name", "")
            if not source_name:
                continue
            
            # Check if this is a Bluetooth device
            if not any(keyword in source_name.lower() for keyword in ["bluez", "bluetooth"]):
                continue
            
            # Extract MAC address
            mac = self.extract_mac_from_alsa_device(source_name)
            if not mac:
                continue
            
            # Filter by MAC if specified
            if mac_address and mac.lower() != mac_address.lower():
                continue
            
            # Identify profile from device name pattern
            source_lower = source_name.lower()
            profile_uuid = None
            profile_name = None
            
            for pattern, uuid in profile_patterns.items():
                if pattern in source_lower:
                    profile_uuid = uuid
                    profile_name = get_profile_name(uuid)
                    break
            
            # Default to A2DP Source if no specific pattern found but it's a Bluetooth source
            if not profile_uuid:
                profile_uuid = A2DP_SOURCE_UUID
                profile_name = get_profile_name(profile_uuid)
            
            # Add to result
            if profile_uuid not in result:
                result[profile_uuid] = []
            
            result[profile_uuid].append({
                "source_name": source_name,
                "mac_address": mac,
                "profile_name": profile_name,
                "backend": source.get("backend", "unknown"),
                "description": source.get("description", ""),
            })
        
        return result

    def check_audio_file_has_content(self, audio_file_path: str) -> bool:
        """Return True if the file has non-zero amplitude (has audio). Uses sox."""
        return check_audio_file_has_content(audio_file_path, self._sox_path)

    # ------------------------------------------------------------------
    # BlueALSA helpers
    # ------------------------------------------------------------------

    def is_bluealsa_running(self) -> bool:
        """Return True if the BlueALSA daemon is reachable (``bluealsa-cli list-pcms`` succeeds)."""
        if not self._bluealsa_cli_path:
            return False
        try:
            result = subprocess.run(
                [self._bluealsa_cli_path, "list-pcms"],
                capture_output=True, text=True, timeout=3,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return False

    def list_bluealsa_pcms(self) -> List[Dict[str, Any]]:
        """
        Enumerate Bluetooth ALSA PCM devices exposed by BlueALSA.

        Parses ``bluealsa-cli list-pcms`` output.  Typical lines::

            /org/bluealsa/hci0/dev_AA_BB_CC_DD_EE_FF/a2dp/sink
            /org/bluealsa/hci0/dev_AA_BB_CC_DD_EE_FF/sco/source

        Returns
        -------
        List[Dict[str, Any]]
            Each dict contains ``pcm_path``, ``mac_address``, ``profile``
            (``a2dp`` or ``sco``), ``direction`` (``sink`` or ``source``),
            and ``alsa_device`` (ALSA device string for aplay/arecord).
        """
        if not self._bluealsa_cli_path:
            return []
        try:
            result = subprocess.run(
                [self._bluealsa_cli_path, "list-pcms"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return []
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return []

        pcms: List[Dict[str, Any]] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # Extract MAC from dev_XX_XX_XX_XX_XX_XX pattern
            mac_match = re.search(
                r"dev_([0-9A-Fa-f]{2}_[0-9A-Fa-f]{2}_[0-9A-Fa-f]{2}_"
                r"[0-9A-Fa-f]{2}_[0-9A-Fa-f]{2}_[0-9A-Fa-f]{2})",
                line,
            )
            mac = mac_match.group(1).replace("_", ":").lower() if mac_match else None

            parts = line.rstrip("/").split("/")
            profile = parts[-2] if len(parts) >= 2 else "unknown"
            direction = parts[-1] if parts else "unknown"

            alsa_dev = ""
            if mac:
                mac_upper = mac.upper()
                alsa_dev = f"bluealsa:DEV={mac_upper},PROFILE={profile}"

            pcms.append({
                "pcm_path": line,
                "mac_address": mac,
                "profile": profile,
                "direction": direction,
                "alsa_device": alsa_dev,
            })
        return pcms

    def play_to_bluealsa_pcm(
        self, pcm_device: str, file_path: str, duration_sec: int = 8,
    ) -> bool:
        """Play an audio file to a BlueALSA PCM device via ``aplay -D``."""
        if not self._aplay_path or not os.path.isfile(file_path):
            return False
        try:
            result = subprocess.run(
                [self._aplay_path, "-D", pcm_device, file_path],
                capture_output=True, text=True,
                timeout=duration_sec + 10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return False

    def record_from_bluealsa_pcm(
        self, pcm_device: str, output_path: str, duration_sec: int = 8,
    ) -> bool:
        """Record from a BlueALSA PCM device via ``arecord -D``."""
        if not self._arecord_path:
            return False
        try:
            result = subprocess.run(
                [self._arecord_path, "-D", pcm_device,
                 "-d", str(duration_sec), "-f", "cd", output_path],
                capture_output=True, text=True,
                timeout=duration_sec + 10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return False

    # ------------------------------------------------------------------
    # PipeWire native helpers
    # ------------------------------------------------------------------

    def _get_pipewire_bluez_nodes(self) -> List[Dict[str, Any]]:
        """
        Enumerate Bluetooth audio nodes via ``pw-dump`` (JSON).

        Returns
        -------
        List[Dict[str, Any]]
            Each dict has ``node_id``, ``node_name``, ``mac_address``,
            ``media_class`` (e.g. ``Audio/Sink``), ``state``, and
            ``profiles`` (list of profile dicts if available).
        """
        if not self._pw_dump_path:
            return []
        try:
            result = subprocess.run(
                [self._pw_dump_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return []

        try:
            import json as _json
            objects = _json.loads(result.stdout)
        except (ValueError, TypeError):
            return []

        nodes: List[Dict[str, Any]] = []
        for obj in objects:
            obj_type = obj.get("type")
            if obj_type != "PipeWire:Interface:Node":
                continue
            info = obj.get("info", {})
            props = info.get("props", {})
            node_name = props.get("node.name", "")
            media_class = props.get("media.class", "")

            if "bluez" not in node_name.lower() and "bluetooth" not in node_name.lower():
                continue
            if "Audio" not in media_class:
                continue

            mac = self.extract_mac_from_alsa_device(node_name)
            node_id = obj.get("id")
            state = info.get("state", props.get("node.state", "unknown"))

            # Collect profile info from params if present
            profiles: List[Dict[str, Any]] = []
            for param in info.get("params", {}).get("EnumProfile", []):
                profiles.append({
                    "index": param.get("index"),
                    "name": param.get("name", ""),
                    "description": param.get("description", ""),
                })

            nodes.append({
                "node_id": node_id,
                "node_name": node_name,
                "mac_address": mac,
                "media_class": media_class,
                "state": str(state),
                "profiles": profiles,
            })
        return nodes

    def _get_pipewire_profiles(self, node_id: int) -> List[Dict[str, Any]]:
        """Return available profiles for a PipeWire node from ``pw-dump`` data."""
        nodes = self._get_pipewire_bluez_nodes()
        for node in nodes:
            if node.get("node_id") == node_id:
                return node.get("profiles", [])
        return []

    def _set_pipewire_profile(self, node_id: int, profile_index: int) -> bool:
        """Set the active profile on a PipeWire node via ``wpctl set-profile``."""
        if not self._wpctl_path:
            return False
        try:
            result = subprocess.run(
                [self._wpctl_path, "set-profile", str(node_id), str(profile_index)],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return False

    def _get_pipewire_sources_and_sinks(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get Bluetooth sources and sinks from PipeWire nodes (native, no PA compat).

        Returns dict with ``'sources'`` and ``'sinks'`` lists, each entry
        containing ``name``, ``role``, ``node_id``, and ``mac_address``.
        """
        nodes = self._get_pipewire_bluez_nodes()
        sources: List[Dict[str, Any]] = []
        sinks: List[Dict[str, Any]] = []
        for node in nodes:
            mc = node.get("media_class", "")
            entry = {
                "name": node.get("node_name", ""),
                "role": self._role_for_interface_name(
                    "sinks" if "Sink" in mc else "sources",
                    node.get("node_name", ""),
                ),
                "node_id": node.get("node_id"),
                "mac_address": node.get("mac_address"),
            }
            if "Sink" in mc:
                sinks.append(entry)
            elif "Source" in mc:
                sources.append(entry)
        return {"sources": sources, "sinks": sinks}

    def get_bluez_cards(self) -> List[Dict[str, Any]]:
        """
        List PulseAudio cards that are BlueZ (Bluetooth) cards.

        Requires pactl. Returns list of dicts with keys: index, name, driver.
        """
        if not self._pactl_path:
            return []
        try:
            result = subprocess.run(
                [self._pactl_path, "list", "cards", "short"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return []
            cards = []
            for line in result.stdout.splitlines():
                if not line.strip() or "bluez" not in line.lower():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    cards.append({
                        "index": parts[0],
                        "name": parts[1],
                        "driver": parts[2] if len(parts) > 2 else "",
                    })
            return cards
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return []

    def get_profiles_for_card(self, card_index: str) -> List[str]:
        """
        Get list of profile names for a card. Uses pactl list cards and parses Profiles block.
        """
        if not self._pactl_path:
            return []
        try:
            result = subprocess.run(
                [self._pactl_path, "list", "cards"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []
            in_card = False
            in_profiles = False
            profiles = []
            for line in result.stdout.splitlines():
                if re.match(r"^Card #", line) or line.strip().startswith("index:"):
                    if in_card and in_profiles:
                        break
                    in_profiles = False
                    if f"Card #{card_index}" in line or (line.strip().startswith("index:") and line.split(":")[1].strip() == str(card_index)):
                        in_card = True
                    else:
                        in_card = False
                    continue
                if in_card and "Profiles:" in line:
                    in_profiles = True
                    continue
                if in_card and in_profiles:
                    if re.match(r"^\s+[a-z_]+:", line) and ":" in line:
                        name = line.split(":")[0].strip()
                        if name and name != "Active Profile":
                            profiles.append(name)
                    if "Active Profile:" in line:
                        break
            return profiles
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return []

    def set_card_profile(self, card_index: str, profile_name: str) -> bool:
        """Set the active profile for a PulseAudio card. Returns True on success."""
        if not self._pactl_path:
            return False
        try:
            result = subprocess.run(
                [self._pactl_path, "set-card-profile", card_index, profile_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return False

    def _parse_pacmd_card_block(self, card_index: str) -> str:
        """Extract the card block for card_index from pacmd list-cards. Returns block text or empty."""
        if not self._pacmd_path:
            return ""
        try:
            result = subprocess.run(
                [self._pacmd_path, "list-cards"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return ""
            lines = result.stdout.splitlines()
            in_block = False
            block = []
            for line in lines:
                m = re.match(r"^\s*index:\s*(\d+)\s*$", line)
                if m:
                    idx = m.group(1)
                    if idx == str(card_index):
                        in_block = True
                        block = [line]
                    elif in_block:
                        break
                    continue
                if in_block:
                    block.append(line)
            return "\n".join(block)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return ""

    def _role_for_interface_name(self, section: str, name: str) -> str:
        """
        Map interface name to human-readable role per README observations.
        section is 'sources' or 'sinks'. name is e.g. bluez_source.XX.a2dp_sink.
        """
        name_lower = name.lower()
        if section == "sources":
            if "bluez_source" in name_lower:
                return "microphone"
            if "bluez_sink" in name_lower:
                return "headset_stream"
        if section == "sinks":
            if "bluez_sink" in name_lower:
                return "speaker"
            if "bluez_source" in name_lower:
                return "interest"
        return "unknown"

    def _extract_interfaces_from_block(self, block: str, section_key: str) -> List[Dict[str, Any]]:
        """Parse block for 'sources:' or 'sinks:' and return list of {name, role}."""
        interfaces = []
        in_section = False
        want = section_key.rstrip(":") + ":"
        for line in block.splitlines():
            stripped = line.strip()
            if want in stripped and (stripped == want or stripped.startswith(want)):
                in_section = True
                continue
            if in_section:
                part = re.search(r"\d+\.\s+(\S+)", line)
                if part:
                    name = part.group(1)
                    role_key = section_key.rstrip("s").rstrip(":")
                    role = self._role_for_interface_name(role_key, name)
                    interfaces.append({"name": name, "role": role})
                elif stripped and re.match(r"^[a-z_]+:\s*$", stripped):
                    break
        return interfaces

    def get_sources_and_sinks_for_card_profile(self, card_index: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        For a given card index (current active profile), get sources and sinks with roles.

        Uses pacmd list-cards to get the card block, then parses sources: and sinks:.
        Returns dict with keys 'sources' and 'sinks'; each value is a list of
        {name, role} where role is one of: microphone, headset_stream, speaker, interest, unknown.
        """
        block = self._parse_pacmd_card_block(card_index)
        if not block:
            return {"sources": [], "sinks": []}
        return {
            "sources": self._extract_interfaces_from_block(block, "sources"),
            "sinks": self._extract_interfaces_from_block(block, "sinks"),
        }

    def play_to_sink(
        self,
        sink_id: str,
        file_path: str,
        duration_sec: int = 8,
    ) -> bool:
        """
        Play an audio file to a sink.

        Selects the appropriate tool based on the active backend:
        ``paplay`` for PulseAudio / PipeWire-with-PA-compat,
        ``pw-play`` for PipeWire native, ``aplay`` as ALSA fallback.

        sink_id may be a PulseAudio sink name, PipeWire node ID, or ALSA device.
        """
        if not os.path.isfile(file_path):
            return False
        backend = self.get_audio_backend()
        timeout = duration_sec + 10

        if backend in ("pulseaudio", "pipewire") and self._paplay_path:
            try:
                return subprocess.run(
                    [self._paplay_path, "-d", sink_id, file_path],
                    capture_output=True, text=True, timeout=timeout,
                ).returncode == 0
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                return False

        if backend == "pipewire_native" and self._pw_play_path:
            try:
                return subprocess.run(
                    [self._pw_play_path, f"--target={sink_id}", file_path],
                    capture_output=True, text=True, timeout=timeout,
                ).returncode == 0
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass

        if self._aplay_path:
            try:
                return subprocess.run(
                    [self._aplay_path, "-D", sink_id, file_path],
                    capture_output=True, text=True, timeout=timeout,
                ).returncode == 0
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                return False
        return False

    def record_from_source(
        self,
        source_id: str,
        output_path: str,
        duration_sec: int = 8,
    ) -> bool:
        """
        Record from a source to a file.

        Selects the appropriate tool based on the active backend:
        ``parecord`` for PulseAudio / PipeWire-with-PA-compat,
        ``pw-record`` for PipeWire native, ``arecord`` as ALSA fallback.

        source_id may be a PulseAudio source name, PipeWire node ID, or ALSA device.
        """
        backend = self.get_audio_backend()
        timeout = duration_sec + 10

        if backend in ("pulseaudio", "pipewire") and self._parecord_path:
            try:
                return subprocess.run(
                    [self._parecord_path, "-d", source_id, output_path],
                    capture_output=True, text=True, timeout=timeout,
                ).returncode == 0
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                return False

        if backend == "pipewire_native" and self._pw_record_path:
            try:
                return subprocess.run(
                    [self._pw_record_path, f"--target={source_id}",
                     output_path],
                    capture_output=True, text=True, timeout=timeout,
                ).returncode == 0
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                pass

        if self._arecord_path:
            try:
                return subprocess.run(
                    [self._arecord_path, "-D", source_id,
                     "-d", str(duration_sec), "-f", "cd", output_path],
                    capture_output=True, text=True, timeout=timeout,
                ).returncode == 0
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
                return False
        return False


    def halt_audio_for_device(self, mac_address: str) -> Dict[str, Any]:
        """Halt all audio on a connected Bluetooth device.

        Performs a multi-step disruption sequence:
        1. Pause AVRCP playback via D-Bus MediaPlayer
        2. Set transport volume to 0
        3. Switch the device's audio card profile to "off"

        Parameters
        ----------
        mac_address : str
            MAC address of the target device.

        Returns
        -------
        Dict[str, Any]
            Result dict with keys ``paused``, ``volume_zeroed``,
            ``profile_off`` (each bool), and ``errors`` (list of str).
        """
        result: Dict[str, Any] = {
            "paused": False,
            "volume_zeroed": False,
            "profile_off": False,
            "errors": [],
        }

        # Step 1 – Pause via AVRCP MediaPlayer
        try:
            from bleep.dbuslayer.media import find_media_devices, MediaPlayer, MediaTransport
            media_devs = find_media_devices()
            mac_norm = mac_address.replace(":", "_").upper()
            for dev_path, ifaces in media_devs.items():
                if mac_norm not in dev_path.upper():
                    continue
                if "MediaPlayer" in ifaces:
                    try:
                        player = MediaPlayer(ifaces["MediaPlayer"])
                        player.pause()
                        result["paused"] = True
                    except Exception as exc:
                        result["errors"].append(f"pause: {exc}")
                # Step 2 – Volume to 0
                for tp in ifaces.get("MediaTransports", []):
                    try:
                        transport = MediaTransport(tp)
                        transport.set_volume(0)
                        result["volume_zeroed"] = True
                    except Exception as exc:
                        result["errors"].append(f"volume: {exc}")
        except Exception as exc:
            result["errors"].append(f"media_lookup: {exc}")

        # Step 3 – Switch card profile to "off"
        cards = self.get_bluez_cards()
        for card in cards:
            card_name = card.get("name", "")
            card_mac = self.extract_mac_from_alsa_device(card_name)
            if not card_mac:
                continue
            if card_mac.replace(":", "").lower() != mac_address.replace(":", "").lower():
                continue
            card_index = card.get("index", "")
            if card_index and self.set_card_profile(card_index, "off"):
                result["profile_off"] = True
            else:
                result["errors"].append("profile_off: set_card_profile failed")
            break

        return result


# Singleton instance
_audio_helper = AudioToolsHelper()


def get_audio_backend() -> str:
    """
    Get the detected audio backend.
    
    Returns
    -------
    str
        Backend name: 'pipewire', 'pulseaudio', or 'none'
    """
    return _audio_helper.get_audio_backend()
