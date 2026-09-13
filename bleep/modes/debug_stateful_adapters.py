"""Debug-shell adapters over stateful / loop-driven CLI cores (CDU-M4).

Like the M3 stateless adapters (:mod:`bleep.modes.debug_cli_adapters`), every
verb here delegates to the exact core the CLI dispatch calls and parses its
tokens through the *real* CLI subparser (:func:`parse_as_cli`) so it can never
drift from its CLI twin.  What makes them "stateful":

* ``explore`` / ``audiointercept`` default their target MAC to the live
  ``state.current_device`` when the user omits a leading MAC (matching the
  ``chid``/``aoi`` debug conventions).
* ``signal`` reuses the connected/enumerated ``state.current_device`` directly
  (no reconnect), via ``signal.run(..., device=...)``.
* ``signal`` / ``gattserver`` / ``advertise`` delegate to cores that run their
  own foreground ``GLib.MainLoop`` + SIGINT handler, so they run inside
  :func:`foreground_loop_handoff` (background-loop + Ctrl-C handoff).

``refresh-refs`` is intentionally *not* ported (batch reference-data
maintenance, no session value) — see the capability registry.
"""

from __future__ import annotations

from typing import List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.modes.debug_state import DebugState, foreground_loop_handoff
from bleep.modes.debug_cli_adapters import parse_as_cli


def _inject_current_mac(args: List[str], state: DebugState, *, label: str) -> Optional[List[str]]:
    """Return *args* with the current-device MAC prepended when omitted.

    A leading non-option token is treated as a user-supplied MAC/positional and
    returned unchanged.  Otherwise the live ``state.current_device`` MAC is
    prepended; when there is no current device, prints a hint and returns
    ``None`` so the caller aborts.
    """
    tokens = list(args)
    if tokens and not tokens[0].startswith("-"):
        return tokens
    dev = state.current_device
    if dev is None:
        print_and_log(
            f"[-] {label}: no current device — connect first or pass a MAC explicitly",
            LOG__GENERAL,
        )
        return None
    return [dev.mac_address, *tokens]


# ---------------------------------------------------------------------------
# GATT exploration / signals (reuse the live session)
# ---------------------------------------------------------------------------

def cmd_explore(args: List[str], state: DebugState) -> None:
    """``explore [MAC] [--out F] [--conn-mode passive|naggy] [...]``."""
    tokens = _inject_current_mac(args, state, label="explore")
    if tokens is None:
        return
    ns = parse_as_cli("explore", tokens)
    if ns is None:
        return
    from bleep.modes.exploration import run as _explore_run

    _explore_run(ns)


def cmd_signal(args: List[str], state: DebugState) -> None:
    """``signal <char-uuid|handle> [--time N]`` — timed notification listener.

    Reuses the live ``state.current_device`` (no reconnect); the lightweight
    ``notify`` verb remains the quick toggle. Requires a current LE device.
    """
    dev = state.current_device
    if dev is None:
        print_and_log(
            "[-] signal: no current device — connect to an LE device first",
            LOG__GENERAL,
        )
        return
    if not args:
        print_and_log("Usage: signal <char-uuid|handle> [--time N]", LOG__GENERAL)
        return
    ns = parse_as_cli("signal", [dev.mac_address, *args])
    if ns is None:
        return
    from bleep.modes.signal import run as _signal_run

    with foreground_loop_handoff(state):
        _signal_run(ns, device=dev)


# ---------------------------------------------------------------------------
# Classic SDP enumeration (depth twin of the CLI classic-enum)
# ---------------------------------------------------------------------------

def cmd_cenum(args: List[str], state: DebugState) -> None:
    """``cenum [MAC] [--version-info] [--analyze] [--sdp-source S] [--connectionless]``.

    The richer Classic SDP enumeration/analysis verb — the exact CLI
    ``classic-enum`` twin (same ``bleep.analysis.sdp_analyzer`` path). Distinct
    from ``csdp``, which keeps its raw socket-oriented SDP-browse semantics.
    MAC defaults to ``state.current_device`` when omitted.
    """
    tokens = _inject_current_mac(args, state, label="cenum")
    if tokens is None:
        return
    ns = parse_as_cli("classic-enum", tokens)
    if ns is None:
        return
    from bleep.modes.classic_enum import run as _cenum_run

    _cenum_run(ns)


# ---------------------------------------------------------------------------
# Local roles: GATT server / advertising (own foreground loop)
# ---------------------------------------------------------------------------

def cmd_gattserver(args: List[str], state: DebugState) -> None:
    """``gattserver start [--uuid U ...] [--name N] [--read-value HEX] [--duration N]``."""
    if not args:
        print_and_log(
            "Usage: gattserver start [--uuid U ...] [--name N] [--read-value HEX] "
            "[--duration N] [--adapter hciX]",
            LOG__GENERAL,
        )
        return
    ns = parse_as_cli("gatt-server", args)
    if ns is None:
        return
    from bleep.modes.gatt_server import run as _gs_run

    with foreground_loop_handoff(state):
        _gs_run(ns)


def cmd_advertise(args: List[str], state: DebugState) -> None:
    """``advertise caps | start [options]`` — LE advertising broadcaster."""
    if not args:
        print_and_log("Usage: advertise caps | start [options]", LOG__GENERAL)
        return
    ns = parse_as_cli("advertise", args)
    if ns is None:
        return
    from bleep.modes.advertise import run as _adv_run

    with foreground_loop_handoff(state):
        _adv_run(ns)


# ---------------------------------------------------------------------------
# Audio intercept
# ---------------------------------------------------------------------------

def cmd_audiointercept(args: List[str], state: DebugState) -> None:
    """``audiointercept [MAC] [--duration N] [--engine whisper|vosk] [...]``."""
    tokens = _inject_current_mac(args, state, label="audiointercept")
    if tokens is None:
        return
    ns = parse_as_cli("audio-intercept", tokens)
    if ns is None:
        return
    from bleep.ble_ops.audio.audio_transcribe import run_audio_intercept

    result = run_audio_intercept(
        ns.address,
        duration=ns.duration,
        output_dir=ns.output_dir,
        pcm_device=ns.pcm,
        transcribe=not ns.no_transcribe,
        engine=ns.engine,
    )
    if result.error:
        print_and_log(f"[-] Error: {result.error}", LOG__GENERAL)
        return
    print_and_log(f"[+] Captured: {result.wav_path}", LOG__GENERAL)
    print_and_log(f"    Duration:    {result.duration_seconds}s", LOG__GENERAL)
    print_and_log(f"    Has content: {result.has_content}", LOG__GENERAL)
    if result.transcript:
        print_and_log(f"    Engine:      {result.engine}", LOG__GENERAL)
        print_and_log(f"    Transcript:  {result.transcript[:200]}", LOG__GENERAL)
    elif result.has_content:
        print_and_log("    (no transcription engine available)", LOG__GENERAL)


# ---------------------------------------------------------------------------
# Device sets / mesh / CTF
# ---------------------------------------------------------------------------

def cmd_devicesets(args: List[str], state: DebugState) -> None:
    """``devicesets [list | connect <path> | disconnect <path> | info <path>]``."""
    ns = parse_as_cli("device-sets", args)
    if ns is None:
        return
    from bleep.modes.device_sets import handle_device_sets

    handle_device_sets(ns)


def cmd_mesh(args: List[str], state: DebugState) -> None:
    """``mesh [join <uuid> | provision <uuid> | reprovision <unicast> --node-path P]``."""
    ns = parse_as_cli("mesh", args)
    if ns is None:
        return
    from bleep.modes.mesh_provision import handle_mesh

    handle_mesh(ns)


def cmd_ctf(args: List[str], state: DebugState) -> None:
    """``ctf [--device MAC] [--discover] [--solve] [--visualize] [--interactive]``."""
    ns = parse_as_cli("ctf", args)
    if ns is None:
        return
    from bleep.modes.blectf import run as _ctf_run

    _ctf_run(ns)
