"""Audio codec encoding/decoding for Bluetooth audio streaming.

Uses GStreamer (via subprocess or Python bindings) for audio processing.
This module handles codec operations but does NOT interact with D-Bus.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional, Tuple

# Try to import GStreamer Python bindings (optional)
try:
    from gi.repository import Gst
    _HAS_GST_PYTHON = True
except (ImportError, ValueError, AttributeError):
    _HAS_GST_PYTHON = False

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER
from bleep.bt_ref.constants import (
    SBC_CODEC_ID,
    MP3_CODEC_ID,
    AAC_CODEC_ID,
    ATRAC_CODEC_ID,
    APTX_CODEC_ID,
    APTX_HD_CODEC_ID,
    LC3_CODEC_ID,
    VENDOR_SPECIFIC_CODEC_ID,
    CODEC_NAMES,
    get_codec_name,
)

__all__ = ["AudioCodecEncoder", "AudioCodecDecoder", "get_codec_name"]

# Re-export for backward compatibility
SBC_CODEC = SBC_CODEC_ID
MP3_CODEC = MP3_CODEC_ID
AAC_CODEC = AAC_CODEC_ID
ATRAC_CODEC = ATRAC_CODEC_ID
APTX_CODEC = APTX_CODEC_ID
APTX_HD_CODEC = APTX_HD_CODEC_ID
LC3_CODEC = LC3_CODEC_ID
VENDOR_SPECIFIC_CODEC = VENDOR_SPECIFIC_CODEC_ID


class AudioCodecEncoder:
    """
    Audio codec encoder using GStreamer.
    
    Uses external GStreamer tools (gst-launch-1.0) or Python bindings.
    Reference implementation: workDir/BlueZScripts/simple-asha
    """
    
    def __init__(self, codec: int, configuration: Optional[bytes] = None):
        """
        Initialize encoder for specific codec.
        
        Parameters
        ----------
        codec : int
            Codec ID (SBC_CODEC, MP3_CODEC, etc.)
        configuration : Optional[bytes]
            Codec configuration bytes from MediaTransport (optional)
        """
        self.codec = codec
        self.configuration = configuration
        self._gst_launch_path = shutil.which("gst-launch-1.0")
        self.codec_name = get_codec_name(codec)
    
    def encode_file_to_transport(
        self,
        input_file: str,
        output_fd: int,
        mtu: int,
        codec_config: Optional[bytes] = None
    ) -> bool:
        """
        Encode audio file and write to transport file descriptor.
        
        Uses GStreamer pipeline (via subprocess or Python bindings).
        Reference: workDir/BlueZScripts/simple-asha lines 48-106
        
        Parameters
        ----------
        input_file : str
            Path to input audio file (MP3, WAV, FLAC, etc.)
        output_fd : int
            File descriptor from MediaTransport.acquire()
        mtu : int
            Maximum transmission unit from transport
        codec_config : Optional[bytes]
            Codec configuration bytes (optional)
        
        Returns
        -------
        bool
            True if encoding succeeded, False otherwise
        """
        if not os.path.exists(input_file):
            print_and_log(f"[-] Audio file not found: {input_file}", LOG__USER)
            return False
        
        if _HAS_GST_PYTHON:
            return self._encode_with_python_bindings(input_file, output_fd, mtu, codec_config)
        elif self._gst_launch_path:
            print_and_log(
                "[!] GStreamer Python bindings not available, using subprocess (limited functionality)",
                LOG__DEBUG,
            )
            return self._encode_with_subprocess(input_file, output_fd, mtu, codec_config)
        else:
            print_and_log(
                "[-] GStreamer not available. Install gstreamer1.0-tools or python3-gst-1.0",
                LOG__USER,
            )
            return False
    
    def _encode_with_python_bindings(
        self,
        input_file: str,
        output_fd: int,
        mtu: int,
        codec_config: Optional[bytes]
    ) -> bool:
        """
        Use GStreamer Python bindings for encoding (preferred method).
        
        Reference: workDir/BlueZScripts/simple-asha
        """
        try:
            Gst.init(None)
            
            # Build pipeline based on codec
            # Reference: workDir/BlueZScripts/simple-asha (uses G.722 for ASHA, but pattern applies)
            if self.codec == SBC_CODEC_ID:
                # SBC encoding pipeline (for A2DP)
                pipeline_str = (
                    f'filesrc location="{input_file}" ! '
                    "decodebin ! "
                    "audioconvert ! "
                    "audioresample ! "
                    "audiobuffersplit output-buffer-duration=20/1000 ! "
                    "avenc_sbc ! "
                    "appsink name=sink emit-signals=true"
                )
            elif self.codec == MP3_CODEC_ID:
                # MP3 encoding pipeline
                pipeline_str = (
                    f'filesrc location="{input_file}" ! '
                    "decodebin ! "
                    "audioconvert ! "
                    "audioresample ! "
                    "lamemp3enc ! "
                    "appsink name=sink emit-signals=true"
                )
            elif self.codec == AAC_CODEC_ID:
                # AAC encoding pipeline
                pipeline_str = (
                    f'filesrc location="{input_file}" ! '
                    "decodebin ! "
                    "audioconvert ! "
                    "audioresample ! "
                    "avenc_aac ! "
                    "appsink name=sink emit-signals=true"
                )
            else:
                print_and_log(
                    f"[-] Codec {self.codec_name} ({self.codec}) encoding not yet implemented",
                    LOG__USER,
                )
                return False
            
            pipeline = Gst.parse_launch(pipeline_str)
            sink = pipeline.get_by_name("sink")
            
            if not sink:
                print_and_log("[-] Failed to get appsink from pipeline", LOG__DEBUG)
                return False
            
            # Callback for writing encoded data to transport FD
            def on_new_sample(appsink):
                try:
                    sample = appsink.emit("pull-sample")
                    if not sample:
                        return Gst.FlowReturn.EOS
                    
                    buf = sample.get_buffer()
                    if not buf:
                        return Gst.FlowReturn.ERROR
                    
                    # Map buffer for reading
                    success, map_info = buf.map(Gst.MapFlags.READ)
                    if not success:
                        return Gst.FlowReturn.ERROR
                    
                    try:
                        # Write to transport file descriptor
                        # For A2DP/SBC, we write the encoded data directly
                        # Reference: simple-asha shows pattern for ASHA (G.722 with sequence numbers)
                        # For A2DP SBC, we typically don't need sequence numbers
                        data = map_info.data
                        written = os.write(output_fd, data)
                        if written != len(data):
                            print_and_log(
                                f"[!] Partial write: {written}/{len(data)} bytes",
                                LOG__DEBUG,
                            )
                    finally:
                        buf.unmap(map_info)
                    
                    return Gst.FlowReturn.OK
                except Exception as e:
                    print_and_log(f"[-] Error in sample callback: {str(e)}", LOG__DEBUG)
                    return Gst.FlowReturn.ERROR
            
            sink.connect("new-sample", on_new_sample)
            
            # Bus message handler
            # Reference: workDir/BlueZScripts/simple-asha lines 90-101
            from gi.repository import GLib
            
            mainloop = GLib.MainLoop()
            pipeline_playing = [True]  # Use list to allow modification in nested function
            
            def bus_message(bus, message, user_data):
                if message.type == Gst.MessageType.EOS:
                    print_and_log("[+] End of stream", LOG__GENERAL)
                    pipeline_playing[0] = False
                    mainloop.quit()
                    return False
                elif message.type == Gst.MessageType.ERROR:
                    err, debug = message.parse_error()
                    print_and_log(
                        f"[-] Pipeline error: {err.message} ({debug})",
                        LOG__USER,
                    )
                    pipeline_playing[0] = False
                    mainloop.quit()
                    return False
                return True
            
            bus = pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", bus_message)
            
            # Start pipeline
            ret = pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                print_and_log("[-] Failed to start pipeline", LOG__USER)
                pipeline.set_state(Gst.State.NULL)
                return False
            
            # Run main loop until EOS or error
            # Reference: simple-asha line 163
            try:
                mainloop.run()
            except KeyboardInterrupt:
                print_and_log("[*] Playback interrupted by user", LOG__USER)
                pipeline.set_state(Gst.State.NULL)
                return False
            
            # Cleanup
            pipeline.set_state(Gst.State.NULL)
            
            return True
            
        except Exception as e:
            print_and_log(f"[-] GStreamer encoding error: {str(e)}", LOG__DEBUG)
            return False
    
    def _encode_with_subprocess(
        self,
        input_file: str,
        output_fd: int,
        mtu: int,
        codec_config: Optional[bytes]
    ) -> bool:
        """
        Use gst-launch-1.0 subprocess for encoding (fallback method).
        
        Note: This is a simplified implementation. Full implementation would
        require more complex subprocess handling and FD passing.
        """
        print_and_log(
            "[!] Subprocess encoding not fully implemented - requires GStreamer Python bindings",
            LOG__DEBUG,
        )
        return False


class AudioCodecDecoder:
    """
    Audio codec decoder for Bluetooth audio recording.
    
    Decodes SBC, MP3, AAC streams from MediaTransport file descriptors.
    """
    
    def __init__(self, codec: int):
        """
        Initialize decoder for specific codec.
        
        Parameters
        ----------
        codec : int
            Codec ID (SBC_CODEC, MP3_CODEC, etc.)
        """
        self.codec = codec
        self._gst_launch_path = shutil.which("gst-launch-1.0")
        self.codec_name = get_codec_name(codec)
    
    def decode_audio_stream(
        self,
        input_fd: int,
        output_file: str,
        codec: int,
        mtu: int
    ) -> bool:
        """
        Decode audio stream from transport FD and write to file.
        
        Uses GStreamer pipeline for decoding.
        
        Parameters
        ----------
        input_fd : int
            File descriptor from MediaTransport.acquire()
        output_file : str
            Path to output audio file
        codec : int
            Codec ID
        mtu : int
            Maximum transmission unit
        
        Returns
        -------
        bool
            True if decoding succeeded, False otherwise
        """
        if _HAS_GST_PYTHON:
            return self._decode_with_python_bindings(input_fd, output_file, codec, mtu)
        elif self._gst_launch_path:
            print_and_log(
                "[!] GStreamer Python bindings not available, using subprocess (limited functionality)",
                LOG__DEBUG,
            )
            return self._decode_with_subprocess(input_fd, output_file, codec, mtu)
        else:
            print_and_log(
                "[-] GStreamer not available. Install gstreamer1.0-tools or python3-gst-1.0",
                LOG__USER,
            )
            return False
    
    def _decode_with_python_bindings(
        self,
        input_fd: int,
        output_file: str,
        codec: int,
        mtu: int
    ) -> bool:
        """
        Use GStreamer Python bindings for decoding (preferred method).
        """
        try:
            Gst.init(None)
            
            # Build pipeline based on codec
            if codec == SBC_CODEC_ID:
                pipeline_str = (
                    "appsrc name=src ! "
                    "sbcparse ! "
                    "sbcdec ! "
                    "audioconvert ! "
                    "audioresample ! "
                    f'wavenc ! filesink location="{output_file}"'
                )
            elif codec == MP3_CODEC_ID:
                pipeline_str = (
                    "appsrc name=src ! "
                    "mp3parse ! "
                    "mpg123audiodec ! "
                    "audioconvert ! "
                    "audioresample ! "
                    f'wavenc ! filesink location="{output_file}"'
                )
            elif codec == AAC_CODEC_ID:
                pipeline_str = (
                    "appsrc name=src ! "
                    "aacparse ! "
                    "avdec_aac ! "
                    "audioconvert ! "
                    "audioresample ! "
                    f'wavenc ! filesink location="{output_file}"'
                )
            else:
                print_and_log(
                    f"[-] Codec {self.codec_name} ({codec}) decoding not yet implemented",
                    LOG__USER,
                )
                return False
            
            pipeline = Gst.parse_launch(pipeline_str)
            src = pipeline.get_by_name("src")
            
            if not src:
                print_and_log("[-] Failed to get appsrc from pipeline", LOG__DEBUG)
                return False
            
            # Bus message handler
            from gi.repository import GLib
            
            mainloop = GLib.MainLoop()
            pipeline_playing = [True]
            
            def bus_message(bus, message, user_data):
                if message.type == Gst.MessageType.EOS:
                    print_and_log("[+] Recording complete", LOG__GENERAL)
                    pipeline_playing[0] = False
                    mainloop.quit()
                    return False
                elif message.type == Gst.MessageType.ERROR:
                    err, debug = message.parse_error()
                    print_and_log(
                        f"[-] Pipeline error: {err.message} ({debug})",
                        LOG__USER,
                    )
                    pipeline_playing[0] = False
                    mainloop.quit()
                    return False
                return True
            
            bus = pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", bus_message)
            
            # Start pipeline
            ret = pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                print_and_log("[-] Failed to start pipeline", LOG__USER)
                pipeline.set_state(Gst.State.NULL)
                return False
            
            # Read data from transport FD and feed to appsrc
            # This requires proper main loop integration
            # For now, this is a placeholder - full implementation would:
            # 1. Read from transport FD in chunks
            # 2. Push data to appsrc using appsrc.push_buffer()
            # 3. Handle EOS when transport closes
            # Reference: GStreamer appsrc documentation
            
            # Run main loop
            try:
                mainloop.run()
            except KeyboardInterrupt:
                print_and_log("[*] Recording interrupted by user", LOG__USER)
                pipeline.set_state(Gst.State.NULL)
                return False
            
            # Cleanup
            pipeline.set_state(Gst.State.NULL)
            
            return True
            
        except Exception as e:
            print_and_log(f"[-] GStreamer decoding error: {str(e)}", LOG__DEBUG)
            return False
    
    def _decode_with_subprocess(
        self,
        input_fd: int,
        output_file: str,
        codec: int,
        mtu: int
    ) -> bool:
        """
        Use gst-launch-1.0 subprocess for decoding (fallback method).
        
        Note: This is a simplified implementation. Full implementation would
        require more complex subprocess handling and FD passing.
        """
        print_and_log(
            "[!] Subprocess decoding not fully implemented - requires GStreamer Python bindings",
            LOG__DEBUG,
        )
        return False
