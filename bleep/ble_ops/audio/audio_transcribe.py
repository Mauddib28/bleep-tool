"""Audio intercept and transcription pipeline.

Implements a 7-step pipeline:

1. Validate audio prerequisites (BlueALSA, recording tools)
2. Configure ALSA loopback (if needed)
3. Start audio capture from a BT source
4. Wait for capture duration
5. Analyse captured audio (sox stat)
6. Transcribe via whisper or vosk (if available)
7. Return structured result

Designed to be composable — each step can be called independently.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.ble_ops.audio.audio_tools import check_audio_file_has_content

__all__ = [
    "AudioInterceptResult",
    "run_audio_intercept",
    "transcribe_file",
]


@dataclass
class AudioInterceptResult:
    """Structured result from an audio intercept run."""
    wav_path: str = ""
    duration_seconds: float = 0.0
    has_content: bool = False
    transcript: Optional[str] = None
    engine: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------

def _find_tool(name: str) -> Optional[str]:
    return shutil.which(name)


def _validate_prerequisites() -> List[str]:
    """Return list of missing prerequisite tool names."""
    required = ["arecord", "sox"]
    return [t for t in required if _find_tool(t) is None]


def _capture_audio(
    device_pcm: str,
    output_path: str,
    duration: int = 10,
    sample_rate: int = 44100,
    channels: int = 2,
) -> bool:
    """Record audio from *device_pcm* to *output_path* for *duration* seconds."""
    arecord = _find_tool("arecord")
    if not arecord:
        return False
    cmd = [
        arecord,
        "-D", device_pcm,
        "-f", "S16_LE",
        "-r", str(sample_rate),
        "-c", str(channels),
        "-d", str(duration),
        output_path,
    ]
    print_and_log(f"[audio-intercept] Recording {duration}s from {device_pcm}", LOG__GENERAL)
    try:
        subprocess.run(cmd, timeout=duration + 10, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        print_and_log(f"[audio-intercept] Capture failed: {exc}", LOG__DEBUG)
        return False


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def transcribe_file(
    wav_path: str,
    engine: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Transcribe a WAV file using whisper or vosk (first available).

    Returns dict ``{"text": ..., "engine": ...}`` or ``None`` on failure.
    """
    if engine is None:
        if _find_tool("whisper"):
            engine = "whisper"
        else:
            try:
                import vosk  # noqa: F401
                engine = "vosk"
            except ImportError:
                return None

    if engine == "whisper":
        return _transcribe_whisper(wav_path)
    elif engine == "vosk":
        return _transcribe_vosk(wav_path)
    return None


def _transcribe_whisper(wav_path: str) -> Optional[Dict[str, Any]]:
    whisper = _find_tool("whisper")
    if not whisper:
        return None
    try:
        result = subprocess.run(
            [whisper, wav_path, "--model", "base", "--output_format", "txt"],
            capture_output=True, text=True, timeout=120,
        )
        txt_path = wav_path.rsplit(".", 1)[0] + ".txt"
        if os.path.isfile(txt_path):
            text = Path(txt_path).read_text().strip()
            return {"text": text, "engine": "whisper"}
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _transcribe_vosk(wav_path: str) -> Optional[Dict[str, Any]]:
    try:
        import json
        import wave
        import vosk
    except ImportError:
        return None

    model_path = os.environ.get("VOSK_MODEL_PATH", "")
    if not model_path or not os.path.isdir(model_path):
        return None

    try:
        model = vosk.Model(model_path)
        wf = wave.open(wav_path, "rb")
        rec = vosk.KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)
        text_parts: List[str] = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                partial = json.loads(rec.Result())
                text_parts.append(partial.get("text", ""))
        final = json.loads(rec.FinalResult())
        text_parts.append(final.get("text", ""))
        wf.close()
        return {"text": " ".join(text_parts).strip(), "engine": "vosk"}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_audio_intercept(
    mac: str,
    *,
    duration: int = 10,
    output_dir: str = "/tmp",
    pcm_device: Optional[str] = None,
    transcribe: bool = True,
    engine: Optional[str] = None,
) -> AudioInterceptResult:
    """Execute the full 7-step audio intercept pipeline.

    Parameters
    ----------
    mac : str
        Bluetooth MAC of the source device.
    duration : int
        Capture duration in seconds.
    output_dir : str
        Directory for the captured WAV file.
    pcm_device : str, optional
        ALSA PCM device name.  Auto-derived from *mac* if not given.
    transcribe : bool
        Whether to attempt transcription after capture.
    engine : str, optional
        Force a transcription engine (``"whisper"`` or ``"vosk"``).
    """
    result = AudioInterceptResult()

    # Step 1 — prerequisites
    missing = _validate_prerequisites()
    if missing:
        result.error = f"Missing tools: {', '.join(missing)}"
        return result

    # Step 2 — derive PCM device
    if pcm_device is None:
        pcm_device = f"bluealsa:DEV={mac},PROFILE=a2dp"
    result.metadata["pcm_device"] = pcm_device

    # Step 3+4 — capture
    safe_mac = mac.replace(":", "_")
    ts = int(time.time())
    wav_path = os.path.join(output_dir, f"intercept_{safe_mac}_{ts}.wav")
    result.wav_path = wav_path
    result.duration_seconds = float(duration)

    ok = _capture_audio(pcm_device, wav_path, duration=duration)
    if not ok:
        result.error = "Audio capture failed"
        return result

    # Step 5 — analyse
    result.has_content = check_audio_file_has_content(wav_path)

    # Step 6 — transcribe
    if transcribe and result.has_content:
        tr = transcribe_file(wav_path, engine=engine)
        if tr:
            result.transcript = tr["text"]
            result.engine = tr["engine"]

    return result
