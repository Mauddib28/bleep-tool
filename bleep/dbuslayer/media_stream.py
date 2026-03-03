"""High-level audio streaming manager for Bluetooth media transports.

This module orchestrates MediaTransport acquisition, codec encoding,
and audio streaming. Uses D-Bus for transport management and delegates
codec operations to audio_codec.py.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from bleep.dbuslayer.media import find_media_devices, MediaTransport
from bleep.ble_ops.audio_codec import AudioCodecEncoder, AudioCodecDecoder
from bleep.bt_ref.constants import A2DP_SINK_UUID, A2DP_SOURCE_UUID, get_codec_name, get_profile_name
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER
from bleep.core.errors import map_dbus_error, BLEEPError

__all__ = ["MediaStreamManager"]


class MediaStreamManager:
    """
    High-level manager for Bluetooth audio streaming.
    
    Handles:
    - MediaTransport acquisition/release (D-Bus)
    - Codec negotiation (D-Bus)
    - Audio encoding/streaming (delegates to audio_codec.py)
    """
    
    # Default profile UUIDs - use centralized constants from bleep.bt_ref.constants
    # Access via: A2DP_SINK_UUID, A2DP_SOURCE_UUID (imported at module level)
    
    def __init__(self, device_mac: str, profile_uuid: Optional[str] = None):
        """
        Initialize stream manager for a specific device and profile.
        
        Parameters
        ----------
        device_mac : str
            MAC address of Bluetooth device
        profile_uuid : Optional[str]
            Profile UUID (defaults to A2DP Sink). Use constants from bt_ref/constants.py
        """
        self.device_mac = device_mac
        self.profile_uuid = profile_uuid or A2DP_SINK_UUID
        self._transport: Optional[MediaTransport] = None
        self._transport_fd: Optional[int] = None
        self._read_mtu: Optional[int] = None
        self._write_mtu: Optional[int] = None
    
    def _get_transport(self) -> Optional[MediaTransport]:
        """
        Get MediaTransport for this device and profile.
        
        Uses existing find_media_devices() and MediaTransport classes.
        
        Returns
        -------
        Optional[MediaTransport]
            MediaTransport instance if found, None otherwise
        """
        if self._transport:
            return self._transport
        
        media_devices = find_media_devices()
        
        # Find device path for this MAC address
        device_path = None
        for path, interfaces in media_devices.items():
            if "dev_" in path:
                path_mac = path.split("dev_")[-1].replace("_", ":")
                if path_mac.lower() == self.device_mac.lower().replace(":", "_"):
                    device_path = path
                    break
        
        if not device_path or "MediaTransports" not in media_devices.get(device_path, {}):
            return None
        
        # Find transport with matching UUID
        for transport_path in media_devices[device_path]["MediaTransports"]:
            try:
                transport = MediaTransport(transport_path)
                if transport.get_uuid() == self.profile_uuid:
                    self._transport = transport
                    return transport
            except Exception as e:
                print_and_log(
                    f"[-] Error accessing transport {transport_path}: {str(e)}",
                    LOG__DEBUG,
                )
        
        return None
    
    def acquire_transport(
        self, 
        codec_preference: Optional[str] = None
    ) -> Tuple[int, int, int]:
        """
        Acquire MediaTransport file descriptor for audio streaming.
        
        Uses existing MediaTransport.acquire() from dbuslayer/media.py.
        
        Parameters
        ----------
        codec_preference : Optional[str]
            Codec preference (not used currently, reserved for future codec negotiation)
        
        Returns
        -------
        Tuple[int, int, int]
            Tuple of (file_descriptor, read_mtu, write_mtu)
            
        Raises
        ------
        BLEEPError
            If transport acquisition fails
        """
        transport = self._get_transport()
        if not transport:
            raise BLEEPError(
                f"MediaTransport not found for device {self.device_mac} profile {self.profile_uuid}"
            )
        
        try:
            fd, read_mtu, write_mtu = transport.acquire()
            self._transport_fd = fd
            self._read_mtu = read_mtu
            self._write_mtu = write_mtu
            print_and_log(
                f"[+] Acquired transport: fd={fd}, read_mtu={read_mtu}, write_mtu={write_mtu}",
                LOG__GENERAL,
            )
            return fd, read_mtu, write_mtu
        except Exception as e:
            print_and_log(
                f"[-] Failed to acquire transport: {str(e)}",
                LOG__USER,
            )
            raise map_dbus_error(e) if hasattr(e, 'get_dbus_name') else BLEEPError(str(e))
    
    def release_transport(self) -> None:
        """
        Release the acquired transport file descriptor.
        
        Uses existing MediaTransport.release() from dbuslayer/media.py.
        """
        if self._transport and self._transport_fd is not None:
            try:
                self._transport.release()
                print_and_log("[+] Released transport", LOG__GENERAL)
            except Exception as e:
                print_and_log(
                    f"[-] Error releasing transport: {str(e)}",
                    LOG__DEBUG,
                )
            finally:
                self._transport_fd = None
                self._read_mtu = None
                self._write_mtu = None
    
    def get_transport_info(self) -> dict:
        """
        Get current transport information (codec, state, volume, etc.).
        
        Returns
        -------
        dict
            Dictionary with transport information
        """
        transport = self._get_transport()
        if not transport:
            return {}
        
        return {
            "uuid": transport.get_uuid(),
            "codec": transport.get_codec(),
            "codec_name": get_codec_name(transport.get_codec() or 0),
            "state": transport.get_state(),
            "volume": transport.get_volume(),
            "delay": transport.get_delay(),
            "configuration": transport.get_configuration(),
        }
    
    def set_volume(self, volume: int) -> bool:
        """
        Set transport volume.
        
        Uses existing MediaTransport.set_volume() from dbuslayer/media.py.
        
        Parameters
        ----------
        volume : int
            Volume level (0-127 for A2DP, 0-255 for BAP)
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        transport = self._get_transport()
        if not transport:
            return False
        
        return transport.set_volume(volume)
    
    def get_codec_info(self) -> dict:
        """
        Get codec information from transport.
        
        Returns
        -------
        dict
            Dictionary with codec information
        """
        transport = self._get_transport()
        if not transport:
            return {}
        
        codec = transport.get_codec()
        return {
            "codec_id": codec,
            "codec_name": get_codec_name(codec or 0),
            "configuration": transport.get_configuration(),
        }
    
    def play_audio_file(
        self,
        audio_file: str,
        volume: Optional[int] = None
    ) -> bool:
        """
        Play audio file to Bluetooth device.
        
        Orchestrates:
        1. Transport acquisition (D-Bus)
        2. Volume setting (D-Bus)
        3. Audio encoding (audio_codec.py)
        4. Transport release (D-Bus)
        
        Parameters
        ----------
        audio_file : str
            Path to audio file (MP3, WAV, FLAC, etc.)
        volume : Optional[int]
            Volume level (0-127). If None, current volume is used.
        
        Returns
        -------
        bool
            True if playback succeeded, False otherwise
        """
        try:
            # Acquire transport
            fd, read_mtu, write_mtu = self.acquire_transport()
            
            # Set volume if specified
            if volume is not None:
                self.set_volume(volume)
            
            # Get codec from transport
            codec_info = self.get_codec_info()
            codec_id = codec_info.get("codec_id")
            if codec_id is None:
                print_and_log("[-] Codec information not available", LOG__USER)
                self.release_transport()
                return False
            
            # Initialize encoder
            encoder = AudioCodecEncoder(codec_id, codec_info.get("configuration"))
            
            # Encode and write to transport
            print_and_log(
                f"[*] Encoding and playing {audio_file} using {codec_info.get('codec_name', 'Unknown')} codec",
                LOG__USER,
            )
            success = encoder.encode_file_to_transport(audio_file, fd, write_mtu)
            
            # Release transport
            self.release_transport()
            
            if success:
                print_and_log(f"[+] Audio playback completed", LOG__GENERAL)
            else:
                print_and_log(f"[-] Audio playback failed", LOG__USER)
            
            return success
            
        except Exception as e:
            print_and_log(
                f"[-] Error during audio playback: {str(e)}",
                LOG__USER,
            )
            # Ensure transport is released on error
            try:
                self.release_transport()
            except Exception:
                pass
            return False
    
    def record_audio(
        self,
        output_file: str,
        duration: Optional[int] = None
    ) -> bool:
        """
        Record audio from Bluetooth device.
        
        Orchestrates:
        1. Transport acquisition (D-Bus)
        2. Audio decoding (audio_codec.py)
        3. Transport release (D-Bus)
        
        Parameters
        ----------
        output_file : str
            Path to output audio file
        duration : Optional[int]
            Recording duration in seconds. If None, records until stopped.
            (Note: Duration control not yet implemented)
        
        Returns
        -------
        bool
            True if recording succeeded, False otherwise
        """
        try:
            # Acquire transport
            fd, read_mtu, write_mtu = self.acquire_transport()
            
            # Get codec from transport
            codec_info = self.get_codec_info()
            codec_id = codec_info.get("codec_id")
            if codec_id is None:
                print_and_log("[-] Codec information not available", LOG__USER)
                self.release_transport()
                return False
            
            # Initialize decoder
            decoder = AudioCodecDecoder(codec_id)
            
            # Decode and write to file
            print_and_log(
                f"[*] Recording audio to {output_file} using {codec_info.get('codec_name', 'Unknown')} codec",
                LOG__USER,
            )
            success = decoder.decode_audio_stream(fd, output_file, codec_id, read_mtu)
            
            # Release transport
            self.release_transport()
            
            if success:
                print_and_log(f"[+] Audio recording completed", LOG__GENERAL)
            else:
                print_and_log(f"[-] Audio recording failed", LOG__USER)
            
            return success
            
        except Exception as e:
            print_and_log(
                f"[-] Error during audio recording: {str(e)}",
                LOG__USER,
            )
            # Ensure transport is released on error
            try:
                self.release_transport()
            except Exception:
                pass
            return False
