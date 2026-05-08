"""RFCOMM channel probing for Bluetooth Classic devices.

Provides :func:`probe_rfcomm_channel` which opens a short-lived RFCOMM socket,
sends lightweight terminal / serial probes, and classifies the response.

Probe sequence (sent in order, each with its own read window):
    1. ``\\r\\n``          — generic line break; many serial consoles echo a prompt
    2. ``\\x1b[c``        — VT100 *Device Attributes* (DA1) query
    3. (passive read)     — SSH banners are pushed by the server unprompted

Classification of the concatenated response:
    * ``terminal``  — VT100 DA response (``\\x1b[?...c``) detected
    * ``ssh``       — ``SSH-`` banner prefix detected
    * ``serial``    — printable ASCII reply to ``\\r\\n`` (likely AT-command or shell prompt)
    * ``data``      — non-empty binary response that doesn't match above
    * ``closed``    — connection refused or reset by peer (RFCOMM rejected)
    * ``silent``    — connection succeeded but no response within timeout
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from typing import Optional, List

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.ble_ops.classic.connect import classic_rfccomm_open


@dataclass
class ProbeResult:
    """Outcome of probing a single RFCOMM channel."""

    channel: int
    classification: str  # terminal | ssh | serial | data | closed | silent
    raw_response: bytes = b""
    error: Optional[str] = None
    latency_ms: float = 0.0


def probe_rfcomm_channel(
    mac: str,
    channel: int,
    *,
    timeout: float = 4.0,
    read_window: float = 1.5,
) -> ProbeResult:
    """Open an RFCOMM socket to *channel* and classify the endpoint.

    Parameters
    ----------
    mac : str
        Target Bluetooth MAC address.
    channel : int
        RFCOMM channel number (1–30).
    timeout : float
        Socket connect timeout in seconds.
    read_window : float
        Seconds to wait for data after each probe send.
    """
    mac = mac.strip().upper()
    t0 = time.monotonic()

    try:
        sock = classic_rfccomm_open(mac, channel, timeout=timeout)
    except OSError as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return ProbeResult(
            channel=channel,
            classification="closed",
            error=str(exc),
            latency_ms=elapsed,
        )

    collected = b""
    try:
        sock.settimeout(read_window)

        # Probe 1: generic line break
        try:
            sock.sendall(b"\r\n")
            collected += _drain(sock, read_window)
        except OSError:
            pass

        # Probe 2: VT100 DA1 query
        try:
            sock.sendall(b"\x1b[c")
            collected += _drain(sock, read_window)
        except OSError:
            pass

        # Probe 3: passive read (catch unsolicited banners like SSH)
        collected += _drain(sock, read_window)

    finally:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()

    elapsed = (time.monotonic() - t0) * 1000
    classification = _classify(collected)
    print_and_log(
        f"[rfcomm-probe] ch={channel} class={classification} "
        f"bytes={len(collected)} latency={elapsed:.0f}ms",
        LOG__DEBUG,
    )
    return ProbeResult(
        channel=channel,
        classification=classification,
        raw_response=collected,
        latency_ms=elapsed,
    )


def probe_all_channels(
    mac: str,
    channels: List[int],
    *,
    timeout: float = 4.0,
    read_window: float = 1.5,
) -> List[ProbeResult]:
    """Probe multiple RFCOMM channels sequentially."""
    results = []
    for ch in channels:
        print_and_log(f"[*] Probing RFCOMM channel {ch}...", LOG__GENERAL)
        results.append(
            probe_rfcomm_channel(mac, ch, timeout=timeout, read_window=read_window)
        )
    return results


# ---------------------------------------------------------------------------
# Persistent RFCOMM binding via the ``rfcomm`` userspace utility
# ---------------------------------------------------------------------------


def bind_rfcomm_channel(
    mac: str,
    channel: int,
    *,
    device_id: int = 0,
) -> str:
    """Create a persistent ``/dev/rfcommN`` device via ``rfcomm bind``.

    Parameters
    ----------
    mac : str
        Target Bluetooth MAC address.
    channel : int
        RFCOMM channel number (1–30).
    device_id : int
        Device index N for ``/dev/rfcommN`` (default 0).

    Returns
    -------
    str
        Path to the created device (e.g. ``/dev/rfcomm0``).

    Raises
    ------
    FileNotFoundError
        If the ``rfcomm`` utility is not installed.
    RuntimeError
        If the bind command fails.
    """
    import shutil
    import subprocess

    rfcomm_bin = shutil.which("rfcomm")
    if rfcomm_bin is None:
        raise FileNotFoundError(
            "rfcomm utility not found — install bluez-utils or equivalent"
        )

    mac = mac.strip().upper()
    cmd = [rfcomm_bin, "bind", str(device_id), mac, str(channel)]
    print_and_log(f"[rfcomm-bind] {' '.join(cmd)}", LOG__DEBUG)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"rfcomm bind failed (rc={result.returncode}): {err}")

    dev_path = f"/dev/rfcomm{device_id}"
    print_and_log(f"[rfcomm-bind] Bound {mac} ch {channel} → {dev_path}", LOG__GENERAL)
    return dev_path


def release_rfcomm_channel(device_id: int = 0) -> None:
    """Release a previously bound ``/dev/rfcommN`` device.

    Parameters
    ----------
    device_id : int
        Device index N to release (default 0).

    Raises
    ------
    FileNotFoundError
        If the ``rfcomm`` utility is not installed.
    RuntimeError
        If the release command fails.
    """
    import shutil
    import subprocess

    rfcomm_bin = shutil.which("rfcomm")
    if rfcomm_bin is None:
        raise FileNotFoundError(
            "rfcomm utility not found — install bluez-utils or equivalent"
        )

    cmd = [rfcomm_bin, "release", str(device_id)]
    print_and_log(f"[rfcomm-release] {' '.join(cmd)}", LOG__DEBUG)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"rfcomm release failed (rc={result.returncode}): {err}")

    print_and_log(f"[rfcomm-release] Released /dev/rfcomm{device_id}", LOG__GENERAL)


def list_rfcomm_bindings() -> str:
    """Return the output of ``rfcomm`` (no args) showing active bindings."""
    import shutil
    import subprocess

    rfcomm_bin = shutil.which("rfcomm")
    if rfcomm_bin is None:
        return "(rfcomm utility not found)"

    result = subprocess.run([rfcomm_bin], capture_output=True, text=True, timeout=5)
    return result.stdout.strip() or "(no active bindings)"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _drain(sock: socket.socket, window: float) -> bytes:
    """Read from *sock* until timeout or no more data."""
    buf = b""
    deadline = time.monotonic() + window
    while time.monotonic() < deadline:
        remaining = max(deadline - time.monotonic(), 0.05)
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        except (socket.timeout, OSError):
            break
    return buf


def _classify(data: bytes) -> str:
    """Classify the concatenated response bytes."""
    if not data:
        return "silent"

    # VT100 DA response: ESC [ ? ... c
    if b"\x1b[?" in data and data.rstrip().endswith(b"c"):
        return "terminal"

    # SSH banner: starts with "SSH-"
    stripped = data.lstrip()
    if stripped[:4] == b"SSH-":
        return "ssh"

    # Printable ASCII heuristic: if >60% printable, likely serial/AT console
    printable = sum(1 for b in data if 0x20 <= b <= 0x7E or b in (0x09, 0x0A, 0x0D))
    if len(data) > 0 and printable / len(data) > 0.6:
        return "serial"

    return "data"
