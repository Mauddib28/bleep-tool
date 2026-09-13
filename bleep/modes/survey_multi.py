"""Multi-antenna survey collection (D2).

Runs N collector sessions concurrently — one per Bluetooth adapter — on the
shared GLib main-loop (:mod:`bleep.dbuslayer.loop_service`), merging every
adapter's sightings into a single :class:`~bleep.modes.survey.SurveyCensus`.
This is the "passive collection on separate antennas" model: e.g. one antenna
sweeping LE advertisements while another performs BR/EDR inquiry, or several
antennas on the same transport for spatial coverage / triangulation.

With ``--enumerator``, collectors stay in discovery while a distinct adapter
enumerates (and optionally pairs) devices from the live census
(:mod:`bleep.modes.survey_enum`, :mod:`bleep.dbuslayer.enumerator`).

Coverage profiles
-----------------
* transport-split (default): bare ``--collector hciN`` adapters are assigned
  transports round-robin from (le, bredr), so two adapters split LE vs BR/EDR.
* spatial (opt-in): give the same explicit transport to multiple adapters
  (``--collector hci0:le --collector hci1:le``) to widen coverage / triangulate.

Adaptive round-time is intentionally not applied here (each adapter scans a
fixed window per round); revisit if adaptive multi-adapter pacing is needed.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER

__all__ = ["parse_collectors", "run_multi_collector"]

_VALID_TRANSPORTS = ("le", "bredr", "both")
# Transports cycled through for bare (transport-less) collectors → the default
# transport-split coverage profile.
_SPLIT_CYCLE = ("le", "bredr")


def parse_collectors(tokens: Optional[List[str]]) -> List[Tuple[str, str]]:
    """Parse ``--collector`` tokens into ``[(adapter_name, transport), ...]``.

    Each token is ``hciN`` or ``hciN:transport``.  Bare adapters receive the
    transport-split default (round-robin over ``le``/``bredr``); this is why
    ``--collector`` overrides ``--transport`` rather than honouring it.
    Duplicate ``(adapter, transport)`` pairs are collapsed while preserving
    order.  Returns an empty list when *tokens* is falsy (single-adapter
    survey).
    """
    if not tokens:
        return []
    specs: List[List[Optional[str]]] = []
    for raw in tokens:
        tok = (raw or "").strip()
        if not tok:
            continue
        if ":" in tok:
            name, _, transport = tok.partition(":")
            transport = transport.strip().lower()
            if transport not in _VALID_TRANSPORTS:
                raise ValueError(
                    f"Invalid collector transport '{transport}' in '{tok}' "
                    f"(expected le|bredr|both)"
                )
            specs.append([name.strip(), transport])
        else:
            specs.append([tok, None])

    split_idx = 0
    for spec in specs:
        if spec[1] is None:
            spec[1] = _SPLIT_CYCLE[split_idx % len(_SPLIT_CYCLE)]
            split_idx += 1

    seen: set = set()
    result: List[Tuple[str, str]] = []
    for name, transport in specs:
        key = (name, transport)
        if key in seen:
            continue
        seen.add(key)
        result.append((name, transport))  # type: ignore[arg-type]
    return result


def _persist_devices(
    devices: List[Dict[str, Any]], adapter: Optional[str] = None
) -> None:
    """Upsert harvested devices into the observation DB (mirrors classic round)."""
    try:
        from bleep.core import observations as _obs
        from bleep.modes.survey import _CLASSIFIER_TYPE_MAP
    except Exception:  # pragma: no cover - observations optional
        return
    for d in devices:
        addr = d.get("address")
        if not addr or addr == "??":
            continue
        info: Dict[str, Any] = {
            "name": d.get("name") or d.get("alias"),
            "rssi_last": d.get("rssi"),
            "device_class": d.get("device_class"),
            "addr_type": d.get("address_type"),
        }
        type_label = str(d.get("type", "")).lower()
        if type_label in _CLASSIFIER_TYPE_MAP:
            info["device_type"] = _CLASSIFIER_TYPE_MAP[type_label]
        if d.get("tx_power") is not None:
            info["tx_power"] = int(d["tx_power"])
        if d.get("appearance") is not None:
            info["appearance"] = int(d["appearance"])
        if d.get("modalias"):
            info["modalias"] = str(d["modalias"])
        if d.get("icon"):
            info["icon"] = str(d["icon"])
        if d.get("uuids"):
            info["uuids"] = d["uuids"]
        for flag in ("paired", "trusted", "bonded"):
            if d.get(flag) is not None:
                info[flag] = bool(d[flag])
        if adapter:
            info["seen_by"] = [adapter]
        try:
            _obs.upsert_device(addr, **info)
        except Exception as exc:  # pragma: no cover - defensive
            print_and_log(f"[survey] persist warning {addr}: {exc}", LOG__DEBUG)


def _harvest_into_census(
    sessions: List[Any],
    overlays: List[Tuple[Any, Any]],
    census: Any,
    persist_db: bool,
    keep_listening: bool,
    round_num: int,
) -> None:
    """Merge one harvest of collectors + AdvMonitor overlays into *census*."""
    for session in sessions:
        devices: Dict[str, Dict[str, Any]] = {}
        try:
            devices = session.harvest()
        except Exception as exc:
            print_and_log(
                f"[survey] collector {session.adapter_name} harvest error: {exc}",
                LOG__DEBUG,
            )
        if not keep_listening:
            session.end()
        if not devices:
            continue
        if session.transport == "bredr":
            classic = [
                d
                for d in devices.values()
                if str(d.get("type", "")).lower() in ("br/edr", "dual")
            ]
            census.merge_classic_results(
                classic, adapter=session.adapter_name, round_num=round_num
            )
            if persist_db:
                _persist_devices(classic, adapter=session.adapter_name)
        else:
            census.merge_le_results(
                devices, adapter=session.adapter_name, round_num=round_num
            )
            if persist_db:
                _persist_devices(
                    list(devices.values()), adapter=session.adapter_name
                )

    for session, overlay in overlays:
        try:
            found = overlay.take_found()
        except Exception as exc:
            print_and_log(
                f"[survey] overlay harvest {session.adapter_name}: {exc}",
                LOG__DEBUG,
            )
            continue
        if not found:
            continue
        census.merge_le_results(
            found, adapter=session.adapter_name, round_num=round_num
        )
        if persist_db:
            _persist_devices(list(found.values()), adapter=session.adapter_name)


#: Consecutive report-free rounds before discovery is treated as dead.
#: Three rounds (90s at the default ``--round-time 30``) is long enough that a
#: genuinely quiet moment does not trigger a re-arm, short enough that a real
#: stall does not silently consume the run.
DEFAULT_STALL_ROUNDS = 3


class _ProgressWatcher:
    """Decides when collectors have gone deaf, from the census progress pair.

    Kept separate from the round loop so the decision is unit-testable: the
    fault it guards against cannot be injected from outside the process, because
    BlueZ scopes discovery per D-Bus client (an external ``StopDiscovery``
    returns ``No discovery started``).
    """

    def __init__(self, stall_rounds: int) -> None:
        self._stall_rounds = stall_rounds
        self._last: Optional[Tuple[int, int]] = None
        self._quiet = 0

    @property
    def quiet_rounds(self) -> int:
        return self._quiet

    def update(self, progress: Tuple[int, int]) -> bool:
        """Feed this round's counters.  True when a re-arm is due.

        The first call only establishes the baseline, so a slow first round is
        never counted as a stall.  The quiet counter resets after signalling so
        a persistent stall re-arms periodically rather than every round.
        """
        if not self._stall_rounds:
            return False
        if self._last is None or progress != self._last:
            self._last = progress
            self._quiet = 0
            return False
        self._quiet += 1
        if self._quiet >= self._stall_rounds:
            self._quiet = 0
            return True
        return False


#: Reply-wait bound for a re-arm's ``StartDiscovery``.  A wedged bluetoothd
#: returns *no reply at all*, so the dbus-python 25s default costs ~25s per
#: attempt on the collector thread (Run D: 21 attempts ≈ 9 minutes lost).
REARM_DBUS_TIMEOUT_S = 5.0

#: Failed re-arms before escalating to the next rung of the ladder.
REARM_ATTEMPTS_BEFORE_ESCALATION = 2


def _adapter_diagnostics(session: Any) -> str:
    """Snapshot the adapter state behind a stall.  Never raises.

    Run D asserted "despite active discovery" without ever reading
    ``Discovering``, so a 2h stall produced no evidence about what BlueZ
    believed.  Each probe is bounded, and an unanswered probe is itself the
    finding — it means bluetoothd, not just the radio, is wedged.
    """
    name = getattr(session, "adapter_name", "?")
    bits = []
    try:
        adapter = session.adapter
        for prop in ("Powered", "Discovering"):
            value = adapter._get_property(prop)
            # ``_get_property`` swallows and returns None on failure, so None
            # here means "bluetoothd did not answer" — itself the finding.
            bits.append(
                f"{prop}={bool(value)}" if value is not None else f"{prop}=<no reply>"
            )
    except Exception as exc:  # pragma: no cover - defensive
        bits.append(f"adapter=<unreachable: {type(exc).__name__}>")
    return f"{name}: " + ", ".join(bits) if bits else f"{name}: <no state>"


def _process_diagnostics(census: Any) -> str:
    """Census / pool / process footprint at the moment of a stall.  Never raises."""
    parts = []
    try:
        parts.append(f"devices={census.device_count}")
    except Exception:
        pass
    try:
        from bleep.dbuslayer.device_pool import enumerator_device_pool

        parts.append(f"pool={len(enumerator_device_pool)}")
    except Exception:
        pass
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    parts.append(f"rss={line.split()[1]}kB")
                elif line.startswith("Threads:"):
                    parts.append(f"threads={line.split()[1]}")
    except Exception:
        pass
    return ", ".join(parts)


def _power_cycle(session: Any) -> bool:
    """Escalation rung 2: power-cycle the adapter.  Returns True on success.

    Only reached with ``--auto-recover``, because it mutates host BT power
    state.  This is itself a D-Bus write, so it cannot help when *bluetoothd*
    is the thing that is wedged — Run E proved that, failing for the same
    reason the re-arm did.  There is no rung below it today; the ladder's next
    step is to end the listen phase and report degraded coverage.  A transport
    below D-Bus (rfkill / ``hciconfig down/up``) is tracked as C-10 in
    ``docs/todo_tracker.md`` B.19-B.23.
    """
    name = getattr(session, "adapter_name", "?")
    try:
        # Reuse the adapter's own power_cycle rather than re-implementing the
        # Powered toggle here.
        if session.adapter.power_cycle(off_delay=1.5):
            time.sleep(1.5)  # let BlueZ re-expose the adapter before restarting
            print_and_log(f"[survey] power-cycled {name}", LOG__USER)
            return True
        _warn_left_powered_off(name)
        return False
    except Exception as exc:
        print_and_log(f"[survey] power cycle {name} FAILED: {exc}", LOG__USER)
        _warn_left_powered_off(name)
        return False


def _warn_left_powered_off(name: str) -> None:
    """Tell the operator the host may be worse off than before we tried.

    A failed cycle can leave the adapter powered down (the off half succeeds,
    the on half times out).  Run E ended with hci0 DOWN and said nothing about
    it, so the degradation was only found by inspecting the host afterwards.
    """
    print_and_log(
        f"[survey] power cycle {name} FAILED — it may be LEFT POWERED OFF; "
        f"restore with: bluetoothctl power on (or 'hciconfig {name} up')",
        LOG__USER,
    )


def _rearm_collectors(
    sessions: List[Any],
    round_num: int,
    quiet_rounds: int,
    timeout: int,
) -> Tuple[int, int]:
    """Stop and restart discovery on every collector.

    Returns ``(succeeded, attempted)`` — both, because counting only successes
    made 21 consecutive failures report as silence (survey_mode.md).
    """
    rearmed = 0
    attempted = 0
    for session in sessions:
        attempted += 1
        try:
            try:
                session.end()
            except Exception as exc:
                print_and_log(
                    f"[survey] re-arm {session.adapter_name}: stop failed: {exc}",
                    LOG__DEBUG,
                )
            session.begin(timeout=timeout, dbus_timeout=REARM_DBUS_TIMEOUT_S)
            rearmed += 1
            print_and_log(
                f"[survey] re-armed collector {session.adapter_name}", LOG__USER
            )
        except Exception as exc:
            print_and_log(
                f"[survey] re-arm {session.adapter_name} FAILED: {exc}",
                LOG__USER,
            )
    return rearmed, attempted


def run_multi_collector(
    census: Any,
    collectors: List[Tuple[str, str]],
    args: Any,
    output: Any,
    persist_db: bool,
    enumerator: Optional[Tuple[str, str]] = None,
) -> Tuple[int, float]:
    """Drive concurrent per-adapter collection into *census*.

    ``args.duration`` is the listen/admission window. Collectors stay
    ``Discovering=true`` for that window. When *enumerator* is set, a worker
    GATT-enumerates on a distinct adapter in parallel (not on the harvest
    thread) and may run past the listen window until the queue is empty.

    Returns ``(round_num, elapsed)`` so the caller's summary/persist tail is
    shared with the single-adapter path.
    """
    from bleep.dbuslayer.loop_service import loop_service
    from bleep.dbuslayer.adapter_session import (
        AdapterSession,
        ROLE_COLLECTOR,
        ROLE_ENUMERATOR,
    )
    from bleep.modes import survey as _survey

    sessions = [
        AdapterSession(name, transport=transport, role=ROLE_COLLECTOR)
        for name, transport in collectors
    ]
    labels = ", ".join(f"{s.adapter_name}:{s.transport}" for s in sessions)
    enum_session = None
    enum_mode = "passive"
    enum_state = None
    listen_monitor = bool(getattr(args, "listen_monitor", False))
    extra_patterns = None
    if listen_monitor:
        from bleep.dbuslayer.adv_patterns import PatternError, parse_listen_extras

        try:
            extra_patterns = parse_listen_extras(
                patterns=getattr(args, "listen_patterns", None),
                manufacturers=getattr(args, "listen_manufacturers", None),
                mfr_strings=getattr(args, "listen_mfr_strings", None),
            ) or None
        except PatternError as exc:
            print_and_log(f"[survey] listen extras: {exc}", LOG__GENERAL)
            extra_patterns = None
        le_sessions = [s for s in sessions if s.transport != "bredr"]
        if not le_sessions:
            print_and_log(
                "[survey] --listen-monitor skipped: no LE/both collector",
                LOG__GENERAL,
            )
            listen_monitor = False
    keep_listening = enumerator is not None or listen_monitor
    if enumerator:
        enum_name, enum_mode = enumerator
        enum_session = AdapterSession(
            enum_name, transport="le", role=ROLE_ENUMERATOR
        )
        output.emit_progress(
            f"[survey] Multi-antenna collection ({len(sessions)} antennas): "
            f"{labels}; enumerator {enum_name}:{enum_mode}"
        )
    else:
        output.emit_progress(
            f"[survey] Multi-antenna collection ({len(sessions)} antennas): {labels}"
        )

    duration = args.duration
    round_time = args.round_time
    checkpoint_interval = getattr(args, "checkpoint_interval", 0) or 0

    # Collector liveness: consecutive rounds in which no device reported.
    stall_rounds = getattr(args, "stall_rounds", None)
    if stall_rounds is None:
        stall_rounds = DEFAULT_STALL_ROUNDS
    watcher = _ProgressWatcher(stall_rounds)
    auto_recover = getattr(args, "auto_recover", False)
    rearms = 0
    rearm_failures = 0
    stall_events = 0
    failed_stalls = 0
    listen_ended_early = False

    round_num = 0
    t_start = time.monotonic()
    deadline = t_start + float(duration)
    elapsed = 0.0
    last_checkpoint = t_start
    collectors_started = False
    listening_stopped = False
    worker = None

    # In-process resource sampling: an external sampler lost the
    # measurement for a whole 2h run, so this lives inside the process.
    metrics_interval = getattr(args, "metrics_interval", 0) or 0
    sampler = None
    if metrics_interval and getattr(args, "output", None):
        from bleep.modes.survey_metrics import MetricsSampler

        sampler = MetricsSampler(
            f"{args.output}.metrics.csv", metrics_interval, census
        ).start()

    loop_service.acquire()
    overlays: List[Tuple[Any, Any]] = []
    try:
        if listen_monitor:
            from bleep.dbuslayer.adv_collector import AdvMonitorOverlay
            import dbus
            bus = dbus.SystemBus()
            for session in sessions:
                if session.transport == "bredr":
                    continue
                ov = AdvMonitorOverlay(session.adapter_name)
                try:
                    ov.start(bus=bus, extra_patterns=extra_patterns)
                    overlays.append((session, ov))
                except Exception as exc:
                    print_and_log(
                        f"[survey] AdvMonitor overlay {session.adapter_name}: {exc}",
                        LOG__GENERAL,
                    )
        if enum_session is not None:
            from bleep.modes.survey_enum import EnumeratorState, enumerator_worker

            enum_state = EnumeratorState()
            worker = threading.Thread(
                target=enumerator_worker,
                args=(census, enum_session, enum_mode, args, enum_state, persist_db),
                name="bleep-enumerator",
                daemon=True,
            )
            worker.start()

        while not _survey._stop:
            now = time.monotonic()
            listening = now < deadline
            if listening:
                round_num += 1
                remaining = deadline - now
                rt = max(1, min(round_time, int(remaining)))
                if not keep_listening or not collectors_started:
                    for session in sessions:
                        try:
                            session.begin(
                                timeout=rt if not keep_listening else duration
                            )
                        except Exception as exc:
                            print_and_log(
                                f"[survey] collector {session.adapter_name} "
                                f"begin error: {exc}",
                                LOG__DEBUG,
                            )
                    collectors_started = True
                _survey._interruptible_sleep(rt)
                _harvest_into_census(
                    sessions, overlays, census, persist_db,
                    keep_listening, round_num,
                )
                if watcher.update(census.progress_counters()):
                    stall_events += 1
                    print_and_log(
                        f"[survey] STALL: no device reports for {stall_rounds} "
                        f"rounds (round {round_num}) — "
                        + "; ".join(_adapter_diagnostics(s) for s in sessions)
                        + f" | {_process_diagnostics(census)}",
                        LOG__USER,
                    )
                    ok, tried = _rearm_collectors(
                        sessions,
                        round_num,
                        stall_rounds,
                        duration if keep_listening else rt,
                    )
                    rearms += ok
                    rearm_failures += tried - ok

                    if ok:
                        failed_stalls = 0
                    else:
                        failed_stalls += 1
                        # Rung 2: power cycle, only where the operator allowed
                        # host BT state to be mutated.
                        if failed_stalls >= REARM_ATTEMPTS_BEFORE_ESCALATION:
                            recovered = False
                            if auto_recover:
                                print_and_log(
                                    f"[survey] {failed_stalls} failed re-arms — "
                                    f"escalating to adapter power cycle",
                                    LOG__USER,
                                )
                                recovered = any(
                                    _power_cycle(s) for s in list(sessions)
                                )
                                if recovered:
                                    ok2, tried2 = _rearm_collectors(
                                        sessions, round_num, stall_rounds,
                                        duration if keep_listening else rt,
                                    )
                                    rearms += ok2
                                    rearm_failures += tried2 - ok2
                                    recovered = bool(ok2)
                            else:
                                print_and_log(
                                    "[survey] collectors are unrecoverable and "
                                    "--auto-recover was not given (it mutates "
                                    "host BT power state), so no power cycle "
                                    "was attempted",
                                    LOG__USER,
                                )
                            if recovered:
                                failed_stalls = 0
                            else:
                                # Rung 3: stop burning the clock collecting
                                # nothing. Run D lost ~85 of 120 listen minutes
                                # to a stall it could not recover from.
                                print_and_log(
                                    f"[survey] ENDING LISTEN PHASE EARLY at "
                                    f"{int(time.monotonic() - t_start)}s of "
                                    f"{duration}s — collectors did not recover. "
                                    f"Proceeding to enumeration and writing "
                                    f"output; coverage is INCOMPLETE.",
                                    LOG__USER,
                                )
                                listen_ended_early = True
                                deadline = time.monotonic()
            else:
                if not listening_stopped:
                    for _session, overlay in overlays:
                        try:
                            overlay.stop()
                        except Exception:
                            pass
                    overlays = []
                    if keep_listening:
                        for session in sessions:
                            session.end()
                    listening_stopped = True
                    if enum_state is not None:
                        with enum_state.lock:
                            enum_state.listen_over = True
                    if worker is None:
                        break
                if worker is None or not worker.is_alive():
                    break
                _survey._interruptible_sleep(1)

            elapsed = time.monotonic() - t_start
            if sampler is not None:
                # Outside the --live block on purpose: metrics must not depend
                # on a display flag.
                sampler.state.round_num = round_num
                sampler.state.phase = "listen" if listening else "enum"
            if getattr(args, "live", False):
                st = census.summary()
                extra = ""
                if enum_state is not None:
                    from bleep.modes.survey_enum import queue_depth

                    with enum_state.lock:
                        inflight = enum_state.inflight or "-"
                        n_ok = len(enum_state.ok)
                        n_done = len(enum_state.done)
                    q = queue_depth(census, args, enum_state, persist_db)
                    extra = (
                        f" | enum={inflight} q={q} "
                        f"enumerated_ok={n_ok} attempted={n_done}"
                    )
                phase = "listen" if listening else "enum"
                output.emit_progress(
                    f"[survey] round {round_num} | {st['total']} devices "
                    f"({st['le']} LE, {st['classic']} Classic, {st['dual']} Dual) | "
                    f"{phase} {int(elapsed)}s listen={duration}s | "
                    f"antennas={len(sessions)}{extra}"
                )
            # Not gated on ``listening``: the enumeration tail is the longest and
            # riskiest phase (hours of GATT work, and where the aborts landed),
            # and the worker keeps stamping enumerated_by/at into the census
            # throughout. Checkpointing only while listening left exactly that
            # window unprotected.
            if checkpoint_interval and args.output:
                chk = time.monotonic()
                if chk - last_checkpoint >= checkpoint_interval:
                    _survey._write_survey_checkpoint(census, args, output)
                    last_checkpoint = chk
    finally:
        if enum_state is not None:
            with enum_state.lock:
                enum_state.listen_over = True
                enum_state.stop = _survey._stop
        if worker is not None:
            worker.join()
        for _session, overlay in overlays:
            try:
                overlay.stop()
            except Exception:
                pass
        for session in sessions:
            session.end()
        if enum_session is not None:
            try:
                from bleep.dbuslayer.enumerator import disconnect_connected_on_session

                disconnect_connected_on_session(enum_session)
            except Exception:
                pass
        loop_service.release()
        if sampler is not None:
            print_and_log(
                f"[survey] metrics: {sampler.stop()} samples written to "
                f"{sampler.path}",
                LOG__USER,
            )
        # Always report when a stall happened. Counting only successes meant a
        # run with 21 consecutive failures said nothing at all (survey_mode.md).
        if stall_events:
            print_and_log(
                f"[survey] DEGRADED COVERAGE: {stall_events} stall(s); "
                f"re-arm {rearms} ok / {rearm_failures} failed"
                + ("; listen phase ended early" if listen_ended_early else ""),
                LOG__USER,
            )
        # Surface it in the artefact too, so post-hoc analysis of the JSON can
        # tell a complete census from a truncated one.
        census.collection_health = {
            "stall_events": stall_events,
            "rearm_ok": rearms,
            "rearm_failed": rearm_failures,
            "listen_ended_early": listen_ended_early,
            "degraded": bool(stall_events),
        }

    return round_num, elapsed
