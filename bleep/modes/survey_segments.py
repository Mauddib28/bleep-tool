"""Segmented long surveys: consecutive fresh processes, merged into one census.

Why this exists
---------------
A survey process stops collecting after roughly 80 harvest rounds (~42 min).
It was reproduced five consecutive times, on two different controllers, with
and without an enumerator, and with discovery torn down and rebuilt every
round — so it is not adapter hardware, not enumeration, and not a long-lived
discovery session.  The failure clears on process exit: every fresh run
collects normally from t=0.  ``docs/d-bus-reliability.md`` carries the
evidence table.

Until the cause is known, the supported way to survey for longer than one
segment is to run consecutive segments in fresh processes and merge their
output.  ``--segment-time`` sets the segment length; the default of 30 minutes
sits inside the observed ceiling with enough headroom that a slow round cannot
push a segment over it.

Segments are spawned by re-invoking the CLI with a bounded ``--duration``, so
they inherit every other flag the operator passed and there is no second copy
of the survey loop to keep in step with the first.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence

from bleep.core.log import print_and_log, LOG__USER, LOG__DEBUG

__all__ = [
    "DEFAULT_SEGMENT_S",
    "SEGMENTATION_DISABLED",
    "plan_segments",
    "merge_objects",
    "render_merged",
    "run_segmented",
]

#: Default listen segment length in seconds.
DEFAULT_SEGMENT_S = 1800

#: ``--segment-time 0`` runs a single process of whatever length was requested.
SEGMENTATION_DISABLED = 0

#: A trailing stub shorter than this fraction of a segment is absorbed into the
#: previous one rather than spending a whole process on a few seconds of
#: listening.
_STUB_DIVISOR = 10

#: Flags that must not be inherited by a segment: the duration and output are
#: rewritten per segment, the format is pinned to the canonical one for
#: merging, ``--segment-time 0`` stops a segment from segmenting again, and
#: ``--then-aoi`` belongs to the merged result rather than to each part.
_OVERRIDDEN_FLAGS = frozenset(
    {"--duration", "-o", "--output", "--segment-time", "--format"}
)
_DROPPED_FLAGS = frozenset({"--then-aoi"})

_TYPE_RANK = {"unknown": 0, "le": 1, "classic": 1, "dual": 2}


def plan_segments(
    duration: Optional[int], segment_time: Optional[int]
) -> Optional[List[int]]:
    """Split *duration* into segment lengths, or ``None`` to run in-process.

    ``None`` means "carry on exactly as before" — the run fits in one segment,
    or segmentation is switched off — so callers can treat it as a no-op.
    """
    if segment_time is None:
        segment_time = DEFAULT_SEGMENT_S
    if segment_time <= SEGMENTATION_DISABLED:
        return None
    if not duration or duration <= segment_time:
        return None

    whole, remainder = divmod(duration, segment_time)
    plan = [segment_time] * whole
    if remainder:
        if plan and remainder < max(1, segment_time // _STUB_DIVISOR):
            plan[-1] += remainder
        else:
            plan.append(remainder)
    return plan


def _wider_type(left: Optional[str], right: Optional[str]) -> str:
    """Combine two ``device_type`` labels.

    Two *different* single-transport labels across segments mean the device
    answered on both, which is precisely what ``dual`` records.
    """
    left = left or "unknown"
    right = right or "unknown"
    if left == right:
        return left
    rank_l, rank_r = _TYPE_RANK.get(left, 0), _TYPE_RANK.get(right, 0)
    if rank_l == 1 and rank_r == 1:
        return "dual"
    return left if rank_l >= rank_r else right


def _fold(base: Dict[str, Any], extra: Dict[str, Any]) -> None:
    """Fold *extra* into *base* in place; both in ``--format objects`` shape."""
    count_base = int(base.get("sightings") or 0)
    count_extra = int(extra.get("sightings") or 0)

    # Weighted mean, computed before the counts are combined.  Rounded to a
    # whole dBm with no ``ndigits``, exactly as ``DeviceSighting.rssi_avg``
    # does, so a merged census cannot carry a float where every other survey
    # output carries an int.
    avg_base, avg_extra = base.get("rssi_avg"), extra.get("rssi_avg")
    if avg_base is not None and avg_extra is not None and (count_base + count_extra):
        base["rssi_avg"] = round(
            (avg_base * count_base + avg_extra * count_extra)
            / (count_base + count_extra)
        )
    elif avg_base is None and avg_extra is not None:
        base["rssi_avg"] = avg_extra

    base["sightings"] = count_base + count_extra

    for key, pick in (("rssi_min", min), ("rssi_max", max)):
        left, right = base.get(key), extra.get(key)
        if left is None:
            base[key] = right
        elif right is not None:
            base[key] = pick(left, right)

    # ISO-8601 UTC timestamps sort lexicographically.
    if extra.get("first_seen") and (
        not base.get("first_seen") or extra["first_seen"] < base["first_seen"]
    ):
        base["first_seen"] = extra["first_seen"]
    if extra.get("last_seen") and (
        not base.get("last_seen") or extra["last_seen"] > base["last_seen"]
    ):
        base["last_seen"] = extra["last_seen"]

    for key in ("uuids", "seen_by"):
        union = set(base.get(key) or []) | set(extra.get(key) or [])
        if union:
            base[key] = sorted(union)

    for key in ("manufacturer_data", "service_data"):
        combined = dict(base.get(key) or {})
        combined.update(extra.get(key) or {})
        if combined:
            base[key] = combined

    if extra.get("payload_history"):
        base["payload_history"] = list(base.get("payload_history") or []) + list(
            extra["payload_history"]
        )

    for key in ("fingerprint_changed", "advmon_seen"):
        if extra.get(key):
            base[key] = True

    for key in ("name", "tx_power", "appearance", "advertising_flags",
                "enumerated_by"):
        if base.get(key) in (None, "", "Unknown") and extra.get(key) not in (None, ""):
            base[key] = extra[key]

    base["device_type"] = _wider_type(base.get("device_type"), extra.get("device_type"))

    # Cached only if no segment ever saw it live.
    if not extra.get("is_cached"):
        base.pop("is_cached", None)


def merge_objects(
    batches: Iterable[Sequence[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """Merge per-segment ``objects`` payloads into one list, keyed on address."""
    merged: Dict[str, Dict[str, Any]] = {}
    for batch in batches:
        for obj in batch or []:
            mac = str(obj.get("address") or "").upper()
            if not mac:
                continue
            if mac in merged:
                _fold(merged[mac], obj)
            else:
                merged[mac] = dict(obj)
    return [merged[mac] for mac in sorted(merged)]


def render_merged(merged: List[Dict[str, Any]], out_format: str) -> Any:
    """Present merged objects in the format the operator asked for."""
    if out_format == "simple":
        return [obj["address"] for obj in merged]
    if out_format == "grouped":
        from bleep.modes.survey import SurveyCensus

        return SurveyCensus.group_objects(merged)
    return merged


def merge_health(reports: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine per-segment collection-health sidecars into one verdict."""
    total: Dict[str, Any] = {
        "stall_events": 0,
        "rearm_ok": 0,
        "rearm_failed": 0,
        "listen_ended_early": False,
        "degraded": False,
    }
    for report in reports:
        for key in ("stall_events", "rearm_ok", "rearm_failed"):
            total[key] += int(report.get(key) or 0)
        for key in ("listen_ended_early", "degraded"):
            total[key] = bool(total[key] or report.get(key))
    return total


def _segment_argv(seconds: int, out_path: str) -> List[str]:
    """Rebuild this invocation for one segment, without the leading program.

    Reuses the operator's own argv so every unrelated flag is inherited rather
    than re-declared here, which would rot the moment a flag is added.  The
    top-level flags *before* the subcommand are carried too: dropping ``--json``
    would let a segment's progress output corrupt the stdout the parent is
    about to emit a JSON document on.
    """
    try:
        pivot = sys.argv.index("survey")
        head, tail = sys.argv[1:pivot], sys.argv[pivot + 1:]
    except ValueError:  # pragma: no cover - defensive
        head, tail = [], []

    argv: List[str] = []
    skip_value = False
    for token in tail:
        if skip_value:
            skip_value = False
            continue
        if token in _OVERRIDDEN_FLAGS:
            skip_value = True
            continue
        if token in _DROPPED_FLAGS:
            continue
        if token.split("=", 1)[0] in _OVERRIDDEN_FLAGS | _DROPPED_FLAGS:
            continue
        argv.append(token)

    return head + ["survey"] + argv + [
        "--duration", str(seconds),
        "--output", out_path,
        "--segment-time", str(SEGMENTATION_DISABLED),
        "--format", "objects",
    ]


def _read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        print_and_log(f"[survey] segment output {path} unreadable: {exc}", LOG__DEBUG)
        return None


def run_segmented(
    args: argparse.Namespace, output: Any, plan: Sequence[int]
) -> int:
    """Run *plan* as consecutive survey processes and merge their output.

    Segment files are kept beside ``--output`` so a long run is inspectable
    part-by-part and an interruption never costs more than the current segment.
    """
    total = sum(plan)
    print_and_log(
        f"[survey] Long run split into {len(plan)} segment(s) of "
        f"{'/'.join(str(s) for s in plan)}s ({total}s total): each segment is a "
        f"fresh process, then the censuses are merged. See "
        f"docs/survey_mode.md 'Segmented long runs'.",
        LOG__USER,
    )

    scratch = None
    if args.output:
        stem = args.output
    else:
        scratch = tempfile.mkdtemp(prefix="bleep-survey-seg-")
        stem = os.path.join(scratch, "segment")

    batches: List[Any] = []
    reports: List[Dict[str, Any]] = []
    completed = 0
    interrupted = False

    try:
        for index, seconds in enumerate(plan, start=1):
            seg_path = f"{stem}.segment{index:02d}.json"
            print_and_log(
                f"[survey] === segment {index}/{len(plan)} ({seconds}s) ===",
                LOG__USER,
            )
            command = [sys.executable, "-m", "bleep"] + _segment_argv(
                seconds, seg_path
            )
            try:
                result = subprocess.run(command)
            except KeyboardInterrupt:
                interrupted = True
                break

            payload = _read_json(seg_path)
            if isinstance(payload, list):
                batches.append(payload)
                completed += 1
            elif payload is not None:
                print_and_log(
                    f"[survey] segment {index} produced {type(payload).__name__}, "
                    f"expected a list — skipped",
                    LOG__USER,
                )

            health = _read_json(f"{seg_path}.health.json")
            if isinstance(health, dict):
                reports.append(health)

            if result.returncode not in (0, None):
                print_and_log(
                    f"[survey] segment {index} exited {result.returncode}; "
                    f"merging what completed",
                    LOG__USER,
                )
                break
    finally:
        merged = merge_objects(batches)
        rendered = render_merged(merged, getattr(args, "out_format", "objects"))
        payload = json.dumps(rendered, indent=2, ensure_ascii=False)

        if args.output and not batches:
            # Nothing to merge — an early failure must not clobber an existing
            # census with an empty list.
            print_and_log(
                f"[survey] No segment produced output; {args.output} left "
                f"untouched",
                LOG__USER,
            )
        elif args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(payload + "\n")
            print_and_log(
                f"[survey] Merged output written to {args.output}", LOG__USER
            )
            if reports:
                health = merge_health(reports)
                health["segments_planned"] = len(plan)
                health["segments_completed"] = completed
                try:
                    with open(
                        f"{args.output}.health.json", "w", encoding="utf-8"
                    ) as handle:
                        handle.write(json.dumps(health, indent=2) + "\n")
                except OSError as exc:  # pragma: no cover - defensive
                    print_and_log(
                        f"[survey] merged health sidecar failed: {exc}", LOG__DEBUG
                    )
        else:
            print(payload)

        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    print_and_log(
        f"[survey] Segmented run complete: {len(merged)} unique device(s) from "
        f"{completed}/{len(plan)} segment(s)",
        LOG__USER,
    )
    incomplete = interrupted or completed < len(plan)
    if incomplete:
        print_and_log(
            "[survey] COVERAGE INCOMPLETE: not every segment finished.", LOG__USER
        )

    # AoI analyses the merged census, not the parts — which is why --then-aoi is
    # withheld from the segments themselves.
    if getattr(args, "then_aoi", False) and args.output and merged:
        from bleep.modes.survey import _then_aoi_argv

        aoi_adapter = getattr(args, "enumerator", None) or getattr(
            args, "adapter", None
        )
        if isinstance(aoi_adapter, str) and ":" in aoi_adapter:
            aoi_adapter = aoi_adapter.split(":", 1)[0]
        aoi_cmd = _then_aoi_argv(args.output, output, adapter=aoi_adapter)
        print_and_log(f"[survey] Launching: {' '.join(aoi_cmd)}", LOG__USER)
        return subprocess.run(
            aoi_cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr
        ).returncode

    return 1 if incomplete else 0
