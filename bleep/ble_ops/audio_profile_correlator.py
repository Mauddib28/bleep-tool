"""Correlate ALSA/PulseAudio device information with BlueZ D-Bus media interfaces.

This module bridges external tool output (from audio_tools.py) with D-Bus
information (from dbuslayer/media.py) to provide complete profile identification.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any

from bleep.ble_ops.audio_tools import AudioToolsHelper
from bleep.dbuslayer.media import find_media_devices, MediaTransport
from bleep.bt_ref.constants import AUDIO_PROFILE_NAMES, CODEC_NAMES, get_profile_name, get_codec_name
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL

__all__ = ["AudioProfileCorrelator"]


class AudioProfileCorrelator:
    """
    Correlates external audio tool output with BlueZ D-Bus media information.
    
    This class combines:
    - External tool enumeration (audio_tools.py)
    - D-Bus media interface discovery (dbuslayer/media.py)
    
    Provides unified profile identification that leverages both sources of information.
    """
    
    def __init__(self):
        """Initialize the profile correlator."""
        self._audio_tools = AudioToolsHelper()
    
    def identify_profiles_for_device(
        self, 
        mac_address: str
    ) -> Dict[str, Any]:
        """
        Identify all audio profiles for a Bluetooth device.
        
        Combines:
        1. ALSA/PulseAudio device enumeration (external tools)
        2. BlueZ MediaTransport discovery (D-Bus)
        
        Parameters
        ----------
        mac_address : str
            MAC address of the Bluetooth device
        
        Returns
        -------
        Dict[str, Any]
            Comprehensive profile information dictionary containing:
            - profiles: Dict mapping profile UUIDs to profile info
            - alsa_devices: List of ALSA device info from external tools
            - transports: List of MediaTransport info from D-Bus
            - mac_address: Device MAC address
        """
        result: Dict[str, Any] = {
            "mac_address": mac_address,
            "profiles": {},
            "alsa_devices": [],
            "transports": [],
        }
        
        # Get profile information from ALSA/PulseAudio (external tools)
        alsa_profiles = self._audio_tools.identify_bluetooth_profiles_from_alsa(mac_address)
        
        # Get MediaTransport information from D-Bus
        media_devices = find_media_devices()
        
        # Find device path for this MAC address
        device_path = None
        for path, interfaces in media_devices.items():
            # Extract MAC from path (format: /org/bluez/hci0/dev_XX_XX_XX_XX_XX_XX)
            path_mac = path.split("dev_")[-1].replace("_", ":") if "dev_" in path else None
            if path_mac and path_mac.lower() == mac_address.lower().replace(":", "_"):
                device_path = path
                break
        
        # Get transports for this device
        if device_path and "MediaTransports" in media_devices.get(device_path, {}):
            for transport_path in media_devices[device_path]["MediaTransports"]:
                try:
                    transport = MediaTransport(transport_path)
                    transport_info = {
                        "transport_path": transport_path,
                        "uuid": transport.get_uuid(),
                        "codec": transport.get_codec(),
                        "codec_name": get_codec_name(transport.get_codec() or 0),
                        "state": transport.get_state(),
                        "volume": transport.get_volume(),
                        "device_path": transport.get_device(),
                    }
                    result["transports"].append(transport_info)
                    
                    # Map transport UUID to profile
                    uuid = transport.get_uuid()
                    if uuid and uuid not in result["profiles"]:
                        result["profiles"][uuid] = {
                            "uuid": uuid,
                            "profile_name": get_profile_name(uuid),
                            "codec": transport.get_codec(),
                            "codec_name": transport_info["codec_name"],
                            "state": transport.get_state(),
                            "transport_path": transport_path,
                            "alsa_devices": [],
                        }
                except Exception as e:
                    print_and_log(
                        f"[-] Error accessing transport {transport_path}: {str(e)}",
                        LOG__DEBUG,
                    )
        
        # Correlate ALSA devices with D-Bus transports
        for profile_uuid, alsa_devices in alsa_profiles.items():
            if profile_uuid not in result["profiles"]:
                # Profile found via ALSA but not in D-Bus (not connected yet)
                result["profiles"][profile_uuid] = {
                    "uuid": profile_uuid,
                    "profile_name": get_profile_name(profile_uuid),
                    "codec": None,
                    "codec_name": None,
                    "state": None,
                    "transport_path": None,
                    "alsa_devices": alsa_devices,
                }
            else:
                # Profile found in both - merge ALSA device info
                result["profiles"][profile_uuid]["alsa_devices"] = alsa_devices
            
            # Add to alsa_devices list
            result["alsa_devices"].extend(alsa_devices)
        
        return result
    
    def get_transport_for_profile(
        self,
        mac_address: str,
        profile_uuid: str
    ) -> Optional[MediaTransport]:
        """
        Get MediaTransport object for specific device and profile.
        
        Uses D-Bus to find MediaTransport matching the device MAC and profile UUID.
        
        Parameters
        ----------
        mac_address : str
            MAC address of the Bluetooth device
        profile_uuid : str
            Profile UUID (e.g., A2DP Sink UUID)
        
        Returns
        -------
        Optional[MediaTransport]
            MediaTransport instance if found, None otherwise
        """
        media_devices = find_media_devices()
        
        # Find device path for this MAC address
        device_path = None
        for path, interfaces in media_devices.items():
            # Extract MAC from path
            if "dev_" in path:
                path_mac = path.split("dev_")[-1].replace("_", ":")
                if path_mac.lower() == mac_address.lower().replace(":", "_"):
                    device_path = path
                    break
        
        if not device_path or "MediaTransports" not in media_devices.get(device_path, {}):
            return None
        
        # Find transport with matching UUID
        for transport_path in media_devices[device_path]["MediaTransports"]:
            try:
                transport = MediaTransport(transport_path)
                if transport.get_uuid() == profile_uuid:
                    return transport
            except Exception as e:
                print_and_log(
                    f"[-] Error accessing transport {transport_path}: {str(e)}",
                    LOG__DEBUG,
                )
        
        return None
    
    def get_all_transports_for_device(
        self,
        mac_address: str
    ) -> List[MediaTransport]:
        """
        Get all MediaTransport objects for a device.
        
        Parameters
        ----------
        mac_address : str
            MAC address of the Bluetooth device
        
        Returns
        -------
        List[MediaTransport]
            List of MediaTransport instances for the device
        """
        transports = []
        media_devices = find_media_devices()
        
        # Find device path for this MAC address
        device_path = None
        for path, interfaces in media_devices.items():
            if "dev_" in path:
                path_mac = path.split("dev_")[-1].replace("_", ":")
                if path_mac.lower() == mac_address.lower().replace(":", "_"):
                    device_path = path
                    break
        
        if device_path and "MediaTransports" in media_devices.get(device_path, {}):
            for transport_path in media_devices[device_path]["MediaTransports"]:
                try:
                    transport = MediaTransport(transport_path)
                    transports.append(transport)
                except Exception as e:
                    print_and_log(
                        f"[-] Error accessing transport {transport_path}: {str(e)}",
                        LOG__DEBUG,
                    )
        
        return transports
