"""Debug shell commands for BLEEP Survey Mode.

``survey`` launches a background survey thread (like ``monitor``).
``survey-status`` reports progress from the shared ``DebugState`` census.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from typing import List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__USER
from bleep.core.errors import BLEEPError
from bleep.modes.debug_state import DebugState

from bleep.modes.survey import (
    SurveyCensus,
    _run_le_round,
    _run_classic_round,
    _start_health_monitor,
    _stop_health_monitor,
    _write_survey_checkpoint,
    _attempt_adapter_recovery,
)


class _ProgressShim:
    """Adapt ``print_and_log`` to the ``OutputContext.emit_progress`` interface.

    ``survey._write_survey_checkpoint()`` (shared with the CLI path) emits its
    progress line via ``output.emit_progress``; the debug shell has no
    ``OutputContext``, so this shim routes it to the debug console/log instead.
    """

    @staticmethod
    def emit_progress(msg: str) -> None:
        print_and_log(msg, LOG__GENERAL)


def _survey_worker(state: DebugState, duration: int, round_time: int,
                   transport: str, output: Optional[str], out_format: str,
                   min_rssi: Optional[int], min_sightings: int,
                   no_db: bool, adapter: str, then_aoi: bool,
                   live: bool = False, resume_db: bool = False,
                   adaptive: bool = False, adaptive_min: int = 10,
                   adaptive_max: int = 60,
                   exclude_cached: bool = False,
                   checkpoint_interval: int = 0,
                   auto_recover: bool = False) -> None:
    """Background worker that runs the survey loop, updating DebugState.

    SR-G1: when ``checkpoint_interval > 0`` and ``output`` is set, the aggregated
    census is atomically flushed to ``<output>.partial`` every N seconds (via the
    shared ``survey._write_survey_checkpoint``), hardening a long debug survey
    against hard crashes; the checkpoint is removed after the clean final write.

    Adapter-drop resilience: a round that cannot scan because the controller went
    not-ready is skipped (not fatal) and paced; ``auto_recover`` optionally
    attempts a bounded in-run power recovery. Mirrors ``bleep.modes.survey.run``.
    """
    import argparse as _argparse

    census = SurveyCensus()

    # SR-G1: build the Namespace the shared checkpoint/formatter helpers expect,
    # and normalise the interval (0 / None = disabled).
    checkpoint_interval = checkpoint_interval or 0
    _ckpt_args = _argparse.Namespace(
        output=output,
        out_format=out_format,
        min_rssi=min_rssi,
        min_sightings=min_sightings,
        exclude_cached=exclude_cached,
    )
    _ckpt_progress = _ProgressShim()

    if resume_db:
        seeded = census.seed_from_db()
        if seeded:
            print_and_log(f"[survey] Resumed {seeded} device(s) from database", LOG__GENERAL)

    state.survey_census = census
    state.survey_round = 0
    state.survey_elapsed = 0.0
    state.survey_duration = duration
    state.survey_output = output

    persist_db = not no_db
    monitoring = _start_health_monitor()
    dynamic_rt = round_time
    prev_count = census.device_count

    t_start = time.monotonic()
    last_checkpoint = t_start

    # Adapter-drop resilience — mirrors ``bleep.modes.survey.run``: never crash
    # the worker thread nor busy-loop when the controller goes not-ready.
    skipped_rounds = 0
    recovery_attempts = 0
    _MAX_RECOVERY_ATTEMPTS = 3

    while state.survey_elapsed < duration and not state.survey_stop_event.is_set():
        state.survey_round += 1

        productive = False
        round_error: BLEEPError | None = None

        if transport in ("le", "both"):
            remaining = duration - state.survey_elapsed
            rt = min(dynamic_rt, max(1, int(remaining)))
            try:
                census.merge_le_results(
                    _run_le_round(rt, quiet=True), round_num=state.survey_round
                )
                productive = True
            except BLEEPError as exc:
                round_error = exc
            state.survey_elapsed = time.monotonic() - t_start
            if state.survey_stop_event.is_set():
                break

        if transport in ("bredr", "both") and state.survey_elapsed < duration \
                and not state.survey_stop_event.is_set():
            remaining = duration - state.survey_elapsed
            rt = min(dynamic_rt, max(1, int(remaining)))
            try:
                census.merge_classic_results(
                    _run_classic_round(
                        rt, adapter_name=adapter, persist_db=persist_db,
                    ),
                    round_num=state.survey_round,
                )
                productive = True
            except BLEEPError as exc:
                round_error = exc
            state.survey_elapsed = time.monotonic() - t_start

        if not productive and not state.survey_stop_event.is_set():
            skipped_rounds += 1
            detail = f" ({round_error})" if round_error is not None else ""
            print_and_log(
                f"[survey] WARNING: adapter not ready — skipped round "
                f"{state.survey_round}{detail}",
                LOG__GENERAL,
            )

            if auto_recover and recovery_attempts < _MAX_RECOVERY_ATTEMPTS:
                recovery_attempts += 1
                print_and_log(
                    f"[survey] Attempting adapter recovery "
                    f"({recovery_attempts}/{_MAX_RECOVERY_ATTEMPTS})\u2026",
                    LOG__GENERAL,
                )
                if _attempt_adapter_recovery(adapter):
                    print_and_log(
                        "[survey] Adapter recovered — resuming", LOG__GENERAL,
                    )
                    recovery_attempts = 0
                    state.survey_elapsed = time.monotonic() - t_start
                    continue

            remaining = duration - state.survey_elapsed
            if remaining > 0:
                # Event.wait is natively interruptible by 'survey stop'.
                state.survey_stop_event.wait(
                    timeout=max(1, min(dynamic_rt, int(remaining)))
                )
                state.survey_elapsed = time.monotonic() - t_start
        elif productive:
            recovery_attempts = 0

        if adaptive:
            new_devices = census.device_count - prev_count
            prev_count = census.device_count
            if new_devices == 0:
                dynamic_rt = max(adaptive_min, dynamic_rt // 2)
            elif new_devices >= 3:
                dynamic_rt = min(adaptive_max, dynamic_rt + 10)

        if live:
            s = census.summary()
            if not productive:
                health = " | BlueZ: adapter not ready"
            elif monitoring:
                health = " | BlueZ: OK"
            else:
                health = ""
            rt_label = f" | rt={dynamic_rt}s" if adaptive else ""
            print_and_log(
                f"[survey] round {state.survey_round} | {s['total']} devices "
                f"({s['le']} LE, {s['classic']} Classic, {s['dual']} Dual) | "
                f"elapsed {int(state.survey_elapsed)}s/{duration}s{rt_label}{health}",
                LOG__GENERAL,
            )

        # SR-G1: periodic census checkpoint (guarded on interval > 0 and output).
        if checkpoint_interval and output:
            now = time.monotonic()
            if now - last_checkpoint >= checkpoint_interval:
                _write_survey_checkpoint(census, _ckpt_args, _ckpt_progress)
                last_checkpoint = now

    if monitoring:
        _stop_health_monitor()

    filtered = census.filter(min_rssi=min_rssi, min_sightings=min_sightings,
                             exclude_cached=exclude_cached)

    if out_format == "simple":
        payload = census.format_simple(filtered)
    elif out_format == "grouped":
        payload = census.format_grouped(filtered)
    else:
        payload = census.format_objects(filtered)

    json_str = json.dumps(payload, indent=2, ensure_ascii=False)

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(json_str + "\n")
        # SR-G1: the complete census is now on disk; drop any stale checkpoint.
        try:
            partial = f"{output}.partial"
            if os.path.exists(partial):
                os.remove(partial)
        except OSError:
            pass

    s = census.summary()
    stopped = "stopped" if state.survey_stop_event.is_set() else "complete"
    print_and_log(
        f"[survey] Survey {stopped}: {s['total']} unique devices in "
        f"{state.survey_round} round(s) over {int(state.survey_elapsed)}s"
        + (f" → {output}" if output else ""),
        LOG__GENERAL,
    )
    if skipped_rounds:
        print_and_log(
            f"[survey] WARNING: {skipped_rounds}/{state.survey_round} round(s) "
            f"skipped — the Bluetooth adapter was not ready. Keep the controller "
            f"powered ('rfkill unblock bluetooth', 'AutoEnable=true' in "
            f"/etc/bluetooth/main.conf) or use --auto-recover.",
            LOG__GENERAL,
        )

    if then_aoi and output and filtered:
        aoi_cmd = [sys.executable, "-m", "bleep", "aoi", "scan", output]
        if adapter:
            aoi_cmd.extend(["--adapter", adapter])
        print_and_log(f"[survey] Launching: {' '.join(aoi_cmd)}", LOG__GENERAL)
        import subprocess as _sp
        _sp.run(
            aoi_cmd,
            stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
        )

    state.survey_thread = None


def cmd_survey(args: List[str], state: DebugState) -> None:
    """Start or stop a background survey.

    Usage:
        survey start [--duration N] [--round-time N] [--transport le|bredr|both]
                     [-o FILE] [--format simple|objects|grouped]
                     [--min-rssi N] [--min-sightings N] [--no-db]
                     [--adapter hciX] [--then-aoi] [--checkpoint-interval N]
        survey stop

    SR-G1: with ``-o FILE --checkpoint-interval N`` the aggregated census is
    flushed to ``FILE.partial`` every N seconds (crash resilience).
    """
    action = args[0].lower() if args else "start"

    if action == "stop":
        if state.survey_thread is None or not state.survey_thread.is_alive():
            print("[-] No survey running")
            return
        state.survey_stop_event.set()
        state.survey_thread.join(timeout=60.0)
        print_and_log("[*] Survey stopped", LOG__GENERAL)
        return

    if action != "start":
        print("Usage: survey start [options] | survey stop")
        return

    if state.survey_thread is not None and state.survey_thread.is_alive():
        print("[-] Survey already running — use 'survey stop' first")
        return

    import argparse
    from bleep.cli.parsers.survey import _add_survey_arguments
    p = argparse.ArgumentParser(prog="survey", add_help=False)
    _add_survey_arguments(p)

    rest = args[1:] if len(args) > 1 else []
    try:
        opts = p.parse_args(rest)
    except SystemExit:
        return

    # Multi-antenna collection (``--collector``) runs a concurrent orchestrator
    # on a shared main-loop; the debug shell's background worker is a
    # single-adapter loop, so accepting the flag here would silently ignore it.
    # Refuse explicitly and point at the CLI rather than mislead the operator.
    if getattr(opts, "collector", None) or getattr(opts, "enumerator", None) or getattr(opts, "listen_monitor", False):
        print(
            "[-] Multi-antenna collection (--collector/--enumerator) and "
            "--listen-monitor are not supported in the debug shell; run them "
            "from the CLI: 'bleep survey --collector ... [--enumerator ...] "
            "[--listen-monitor]'"
        )
        return

    # Same reasoning as above: ``--no-mainloop`` is a process-wide transport
    # change applied in ``bleep.modes.survey.run``, which the debug shell does
    # not call.  It would also break the interactive session's notification and
    # agent handling.  Refuse rather than accept-and-ignore.
    if getattr(opts, "no_mainloop", False):
        print(
            "[-] --no-mainloop is not supported in the debug shell (it would "
            "disable notifications and pairing for the whole session); run it "
            "from the CLI: 'bleep survey --no-mainloop ...'"
        )
        return

    # ``--max-enum-devices`` *is* honourable here: the pool is process-wide, so
    # it also bounds later in-session 'enum'/'connect' commands.
    from bleep.dbuslayer.device_pool import apply_capacity

    pool_ok, pool_msg = apply_capacity(getattr(opts, "max_enum_devices", None))
    if pool_msg:
        print_and_log(pool_msg, LOG__USER)
    if not pool_ok:
        return

    # Segmentation needs a *fresh process* per segment, which an interactive
    # session cannot provide, so the debug shell cannot honour --segment-time.
    # Warn rather than refuse: a long in-shell survey is still legitimate, it
    # just loses collection past the ceiling instead of being split around it.
    from bleep.modes.survey_segments import DEFAULT_SEGMENT_S

    segment_time = getattr(opts, "segment_time", None) or DEFAULT_SEGMENT_S
    if opts.duration > segment_time:
        print_and_log(
            f"[!] --duration {opts.duration}s exceeds the {segment_time}s "
            f"collection ceiling and the debug shell cannot segment (that "
            f"needs a fresh process per segment). Expect collection to stop "
            f"after ~80 rounds. For a split-and-merged long run use the CLI: "
            f"'bleep survey --duration {opts.duration} -o out.json'",
            LOG__USER,
        )

    state.survey_stop_event = threading.Event()
    state.survey_thread = threading.Thread(
        target=_survey_worker,
        args=(state, opts.duration, opts.round_time, opts.transport,
              opts.output, opts.out_format, opts.min_rssi, opts.min_sightings,
              opts.no_db, opts.adapter, opts.then_aoi, opts.live,
              opts.resume_db, opts.adaptive, opts.adaptive_min,
              opts.adaptive_max, opts.exclude_cached,
              getattr(opts, "checkpoint_interval", 0),
              getattr(opts, "auto_recover", False)),
        daemon=True,
        name="survey-worker",
    )
    state.survey_thread.start()
    print_and_log(
        f"[*] Survey started in background: duration={opts.duration}s, "
        f"round_time={opts.round_time}s, transport={opts.transport}"
        + (f", output={opts.output}" if opts.output else ""),
        LOG__GENERAL,
    )


def cmd_survey_status(args: List[str], state: DebugState) -> None:
    """Show the status of a running or completed survey.

    Usage:  survey-status
    """
    if state.survey_census is None:
        print("[-] No survey data — run 'survey start' first")
        return

    running = state.survey_thread is not None and state.survey_thread.is_alive()
    status = "RUNNING" if running else "FINISHED"
    s = state.survey_census.summary()

    print(f"[survey-status] {status}")
    print(f"  Round:    {state.survey_round}")
    print(f"  Elapsed:  {int(state.survey_elapsed)}s / {state.survey_duration}s")
    print(f"  Devices:  {s['total']} total  "
          f"({s['le']} LE, {s['classic']} Classic, {s['dual']} Dual)")
    if state.survey_output:
        print(f"  Output:   {state.survey_output}")
