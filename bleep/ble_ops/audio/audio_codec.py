"""Audio codec encoding/decoding for Bluetooth audio streaming.

Uses GStreamer (via subprocess or Python bindings) for audio processing.
This module handles codec operations but does NOT interact with D-Bus.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Optional, Tuple

# Try to import GStreamer Python bindings (optional).
# Version pins follow the BlueZ reference (workDir/BlueZScripts/simple-asha).
try:
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import GLib, Gst
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


def _pump_fd_to_sink(
    fd: int,
    condition: int,
    *,
    read_chunk: int,
    deadline: Optional[float],
    hup_err_mask: int,
    push_cb,
    eos_cb,
    _now=time.monotonic,
) -> bool:
    """Single GLib IO-watch iteration: read the transport FD and push to a sink.

    Kept GStreamer-agnostic (no ``Gst``/``GLib`` references) so the pump logic
    is unit-testable with an ``os.pipe()`` and plain callables.

    Parameters
    ----------
    fd : int
        Transport file descriptor (expected to be non-blocking).
    condition : int
        GLib IO condition bitmask reported by the watch.
    read_chunk : int
        Bytes to read per iteration.
    deadline : Optional[float]
        ``time.monotonic()`` deadline; ``None`` means run until FD close/EOS.
    hup_err_mask : int
        Bitmask of hang-up/error conditions that should terminate the stream.
    push_cb : Callable[[bytes], bool]
        Consumes a data chunk; returns ``True`` to continue, ``False`` to stop.
    eos_cb : Callable[[], None]
        Invoked once when the stream should end (signals EOS downstream).

    Returns
    -------
    bool
        ``True`` to keep the GLib IO watch registered, ``False`` to remove it.
    """
    # Duration timebox takes priority over draining.
    if deadline is not None and _now() >= deadline:
        eos_cb()
        return False
    # Drain readable data FIRST so a hang-up delivered alongside buffered data
    # (poll reports IN|HUP together) does not discard the tail of the stream.
    try:
        data = os.read(fd, read_chunk)
    except BlockingIOError:
        # No data right now. End only if the FD also hung up/errored;
        # otherwise keep the watch alive and wait for more data.
        if condition & hup_err_mask:
            eos_cb()
            return False
        return True
    except OSError:
        eos_cb()
        return False
    if data:
        return bool(push_cb(data))
    # A successful zero-length read is a definitive EOF (FD closed).
    eos_cb()
    return False


# SBC codec-specific info element, octet 0, sampling-frequency bits (A2DP spec
# §4.3.2 "SBC Codec Specific Information Elements"). Maps the frequency bit to
# the RTP clock-rate used in the ``application/x-rtp`` caps for ``rtpsbcdepay``.
_SBC_SAMPLING_FREQ_BITS = {
    0x80: 16000,
    0x40: 32000,
    0x20: 44100,
    0x10: 48000,
}


def _sbc_rtp_clock_rate(configuration, default: int = 44100) -> int:
    """Derive the RTP clock-rate (SBC sampling frequency) from a negotiated
    SBC codec configuration blob.

    The A2DP transport carries RTP-encapsulated SBC; ``rtpsbcdepay`` needs the
    sampling frequency as the RTP ``clock-rate``. Octet 0's high nibble encodes
    the frequency. Falls back to ``default`` (44100 Hz, the common A2DP value)
    when the configuration is missing or unrecognised.
    """
    try:
        if configuration is not None and len(configuration) >= 1:
            return _SBC_SAMPLING_FREQ_BITS.get(int(configuration[0]) & 0xF0, default)
    except (TypeError, ValueError, IndexError):
        pass
    return default


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
            mainloop = GLib.MainLoop()
            pipeline_playing = [True]  # Use list to allow modification in nested function
            
            # NB: the GstBus "message" signal invokes handlers as
            # ``handler(bus, message)`` — a third ``user_data`` positional here
            # makes every emission raise TypeError, silently dropping EOS/ERROR
            # so the main loop never quits. Keep the arity at two.
            def bus_message(bus, message):
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
        mtu: int,
        duration: Optional[int] = None,
        configuration: Optional[bytes] = None,
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
        duration : Optional[int]
            Maximum recording duration in seconds. If ``None``, records until
            the transport FD closes (device stops streaming) or an error/EOS
            occurs. A Bluetooth transport has no natural end-of-stream, so a
            duration (or an external FD close) is required to terminate cleanly.
        configuration : Optional[bytes]
            Negotiated codec configuration blob from the MediaTransport. For
            SBC this supplies the sampling frequency used as the RTP
            ``clock-rate`` when depayloading the A2DP stream.
        
        Returns
        -------
        bool
            True if decoding succeeded, False otherwise
        """
        if _HAS_GST_PYTHON:
            return self._decode_with_python_bindings(
                input_fd, output_file, codec, mtu, duration=duration,
                configuration=configuration,
            )
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
        mtu: int,
        duration: Optional[int] = None,
        configuration: Optional[bytes] = None,
    ) -> bool:
        """
        Use GStreamer Python bindings for decoding (preferred method).
        """
        try:
            Gst.init(None)
            
            # Build pipeline based on codec
            if codec == SBC_CODEC_ID:
                # A2DP transport FDs deliver RTP-encapsulated SBC (RFC
                # draft-ietf-payload-rtp-sbc / A2DP v1.2 §4.3.4), *not* raw SBC
                # frames. ``rtpsbcdepay`` strips the RTP + SBC payload headers
                # and reassembles fragmented frames; it requires
                # ``application/x-rtp`` caps on the source with the SBC
                # sampling frequency as the RTP clock-rate. Each transport read
                # is one L2CAP SEQPACKET = one RTP packet = one pushed buffer,
                # which is exactly the framing ``rtpsbcdepay`` expects.
                clock_rate = _sbc_rtp_clock_rate(configuration)
                pipeline_str = (
                    "appsrc name=src "
                    'caps="application/x-rtp,media=(string)audio,'
                    "payload=(int)96,"
                    f"clock-rate=(int){clock_rate},"
                    'encoding-name=(string)SBC" ! '
                    "rtpsbcdepay ! "
                    "sbcparse ! "
                    "sbcdec ! "
                    "audioconvert ! "
                    "audioresample ! "
                    f'wavenc ! filesink location="{output_file}"'
                )
            elif codec == MP3_CODEC_ID:
                pipeline_str = (
                    "appsrc name=src ! "
                    # ``mp3parse`` was removed from modern GStreamer (>=1.x);
                    # the current MPEG-audio parser element is ``mpegaudioparse``.
                    "mpegaudioparse ! "
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
            
            # Configure appsrc for live streaming push from the transport FD.
            src.set_property("format", Gst.Format.TIME)
            src.set_property("is-live", True)
            src.set_property("do-timestamp", True)
            
            # Bus message handler
            mainloop = GLib.MainLoop()
            pipeline_playing = [True]
            
            # NB: the GstBus "message" signal invokes handlers as
            # ``handler(bus, message)`` — a third ``user_data`` positional here
            # makes every emission raise TypeError, silently dropping EOS/ERROR
            # so the main loop never quits. Keep the arity at two.
            def bus_message(bus, message):
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
            
            # Feed data from the transport FD into appsrc.
            #
            # A Bluetooth transport FD delivers a continuous stream with no
            # natural EOS, so termination is driven by: (a) the requested
            # duration, (b) the FD closing/erroring (HUP/ERR), or (c) a
            # zero-length read. The FD is made non-blocking so the GLib main
            # loop stays responsive and the duration deadline is honoured.
            #
            # This mirrors the proven producer path in
            # ``_encode_with_python_bindings`` (appsink + os.write), inverted
            # for consumption (os.read + appsrc push-buffer). The per-iteration
            # logic lives in the GStreamer-agnostic ``_pump_fd_to_sink`` helper
            # so it can be unit-tested without GStreamer.
            #
            # NB: A2DP transport FDs deliver RTP-encapsulated media payloads.
            # The SBC pipeline above handles this with ``rtpsbcdepay`` fed by
            # ``application/x-rtp`` caps. MP3/AAC branches remain raw-frame
            # pipelines (only reachable for non-A2DP/optional codec configs).
            import fcntl
            
            try:
                _flags = fcntl.fcntl(input_fd, fcntl.F_GETFL)
                fcntl.fcntl(input_fd, fcntl.F_SETFL, _flags | os.O_NONBLOCK)
            except OSError as exc:
                print_and_log(
                    f"[-] Failed to set transport FD non-blocking: {exc}",
                    LOG__DEBUG,
                )
                pipeline.set_state(Gst.State.NULL)
                return False
            
            read_chunk = max(int(mtu or 0), 2048)
            deadline = (time.monotonic() + duration) if duration else None
            hup_err_mask = GLib.IOCondition.HUP | GLib.IOCondition.ERR
            
            def _push(data):
                flow = src.emit(
                    "push-buffer", Gst.Buffer.new_wrapped(data),
                )
                if flow != Gst.FlowReturn.OK:
                    print_and_log(
                        f"[-] appsrc push-buffer returned {flow}", LOG__DEBUG,
                    )
                    return False
                return True
            
            def _feed_appsrc(fd, condition):
                return _pump_fd_to_sink(
                    fd,
                    int(condition),
                    read_chunk=read_chunk,
                    deadline=deadline,
                    hup_err_mask=int(hup_err_mask),
                    push_cb=_push,
                    eos_cb=lambda: src.emit("end-of-stream"),
                )
            
            GLib.io_add_watch(
                input_fd,
                GLib.PRIORITY_DEFAULT,
                GLib.IOCondition.IN | hup_err_mask,
                _feed_appsrc,
            )
            
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
