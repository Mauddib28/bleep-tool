# Survey Mode

Long-duration passive Bluetooth device discovery with automatic deduplication,
RSSI tracking, and AoI-compatible target list output.

## Overview

`bleep survey` alternates LE and BR/EDR discovery rounds over a configurable
duration, merges sightings into a per-device census, and writes the final
device list to file or stdout in any of the three formats accepted by
`bleep aoi scan`.

Survey does **not** perform GATT/SDP analysis or reporting by default —
those stay with AoI as a separate step. With `--enumerator`, a second adapter
GATT-enumerates live census devices during the survey (see
[Concurrent enumeration](#concurrent-enumeration---enumerator)).

## Quick Start

```bash
# 2-minute ambient survey (default), output to file
bleep survey -o targets.json

# Feed into AoI enumeration
bleep aoi scan targets.json

# One-liner
bleep survey -o t.json && bleep aoi scan t.json
```

## Command Reference

```
bleep survey [OPTIONS]
```

### Discovery Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--duration` | int | 120 | Listen/admission window in seconds. With `--enumerator`, GATT continues after this until the queue is empty |
| `--round-time` | int | 30 | Duration of each scan round in seconds |
| `--transport` | choice | `both` | `le`, `bredr`, or `both` (alternating) |
| `--variant` | choice | `passive` | LE discovery variant for each LE round: `passive` (StartDiscovery) or `naggy` (`DuplicateData=true` via merged filter). Mutually exclusive with `--listen-monitor`. |
| `--min-rssi` | int | None | Exclude devices weaker than this threshold |
| `--min-sightings` | int | 1 | Minimum sightings required to include a device |
| `--adapter` | str | `hci0` | Bluetooth adapter name (single-adapter survey) |
| `--collector` | str (repeatable) | none | Enable multi-antenna collection: `hciN[:TRANSPORT]`. See [Multi-Antenna Collection](#multi-antenna-collection). |
| `--enumerator` | str | none | Secondary antenna for concurrent enumeration while collectors stay in discovery: `hciN[:MODE]` (`passive`/`naggy`/`pokey`/`pair`). Must be distinct from collectors. |
| `--enum-cooldown` | int | 3600 | Skip GATT when `enumerated_at` is newer than this many seconds (0 = no DB skip). This-run successes are never re-queued from collector re-sights. |
| `--stall-rounds` | int | 3 | **Multi-collector (`--collector`) only.** Re-arm discovery after N consecutive rounds with **no device reports**, even while BlueZ still claims `Discovering=true` (`0` = never). The single-adapter survey loop validates the value but does not implement stall re-arm. See [Collector stall detection](#collector-stall-detection---stall-rounds). |
| `--metrics-interval` | int | 0 | Sample RSS/threads/fds/census/pool every N seconds to `<output>.metrics.csv` (0=off, requires `-o`). Sampled **in-process**, so it cannot miss the run. |
| `--no-mainloop` | flag | off | Run with **no GLib main loop**. Required to survive long dual collector+enumerator runs (see [Loop-free operation](#loop-free-operation---no-mainloop)). **Passive enumeration only — deep enumeration requires the loop.** **Disables AdvMonitor callbacks, pairing and GATT notifications** — a warning listing them is printed. Rejected with `--listen-monitor` or pair mode (exit 2). |
| `--max-enum-devices` | int | 10 | Cap live enumeration device objects; the least-recently-used is torn down beyond the cap. `0` = unlimited (diagnostic). Bounds long-run memory. `BLEEP_MAX_ENUM_DEVICES` sets the same cap where this flag is unavailable. See [Enumeration device pool](#enumeration-device-pool---max-enum-devices). |
| `--listen-monitor` | flag | off | Flags-OR AdvMonitor overlay (one monitor, GAP Flags `{00,02,04,05,06,18,1A}`) on LE/`both` collectors. Census is the **union** of Device1 harvest and `DeviceFound`. Collectors stay discovering. Not `--variant passive`. See [Listen-monitor overlay](#listen-monitor-overlay---listen-monitor). |
| `--listen-pattern` | str (repeatable) | none | Extra `OFF:AD:HEX` pattern. Requires `--listen-monitor`. Registered as a second `or_patterns` child (not mixed onto Flags). |
| `--listen-manufacturer` | str (repeatable) | none | Extra manufacturer filter `CID` or `CID:HEX` (AD 0xFF, little-endian CID). Requires `--listen-monitor`. |
| `--listen-mfr-string` | str (repeatable) | none | Extra UTF-8 string in manufacturer payload after the 2-byte CID (AD 0xFF offset 2). Requires `--listen-monitor`. |
| `--resume-db` | flag | off | Pre-seed census with previously observed devices from the DB |
| `--adaptive` | flag | off | Auto-adjust round time based on discovery rate |
| `--adaptive-min` | int | 10 | Minimum round time in seconds (with `--adaptive`) |
| `--adaptive-max` | int | 60 | Maximum round time in seconds (with `--adaptive`) |
| `--exclude-cached` | flag | off | Exclude cached/bonded devices not actively seen during this scan |

### Output Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-o`, `--output` | path | stdout | Output file for AoI-compatible JSON |
| `--format` | choice | `objects` | `simple`, `objects`, or `grouped` |
| `--no-db` | flag | off | Skip Classic-round DB persistence (LE scan always persists via core infra) |
| `--live` | flag | off | Show live round progress to stderr (`enumerated_ok` / `attempted` when `--enumerator` is set) |
| `--quiet` | flag | off | Suppress per-device scan output |
| `--then-aoi` | flag | off | After survey, auto-run `bleep aoi scan` on output (requires `-o`) |
| `--checkpoint-interval` | int | 0 | Periodically flush the partial census to `<output>.partial` every N seconds (0=off, requires `-o`). Supported by the CLI **and** the debug shell — see [Census Checkpointing](#census-checkpointing-sr-g1). |
| `--auto-recover` | flag | off | If the adapter goes not-ready mid-survey, attempt a bounded in-run power-cycle to recover it (mutates host BT power state) — see [Adapter-Drop Resilience](#adapter-drop-resilience). |

## Output Formats

All three formats are valid inputs to `bleep aoi scan <file>`.

### `simple` — Flat MAC list

```json
["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]
```

### `objects` (default) — Enriched device objects

```json
[
  {
    "address": "AA:BB:CC:DD:EE:FF",
    "name": "Smart Lock",
    "device_type": "le",
    "sightings": 8,
    "rssi_avg": -65,
    "rssi_min": -72,
    "rssi_max": -58,
    "first_seen": "2026-05-07T19:50:00+00:00",
    "last_seen": "2026-05-07T19:52:00+00:00",
    "uuids": ["0000180f-0000-1000-8000-00805f9b34fb"],
    "manufacturer_data": {"76": "0215aabbccdd"},
    "service_data": {"0000180f": "64"},
    "tx_power": -10,
    "appearance": 960,
    "fingerprint_changed": true,
    "seen_by": ["hci0", "hci1"],
    "enumerated_by": "hci1",
    "advmon_seen": true,
    "advertising_flags": "06"
  }
]
```

The `manufacturer_data`, `service_data`, `tx_power`, `appearance`,
`fingerprint_changed`, `is_cached`, `seen_by`, `enumerated_by`, `advmon_seen`, and
`advertising_flags` fields are only present when applicable.
`fingerprint_changed` is `true` when a manufacturer or service
data payload changed between rounds (useful for detecting beacon rotation).
`seen_by` lists the adapters (antennas) that observed the device and is only
emitted for [multi-antenna](#multi-antenna-collection) runs.
`enumerated_by` is the enumerator adapter that **succeeded** GATT enumeration
(`--enumerator`); failed attempts are omitted. The observation-DB column is
the same success-gated last-writer value (schema v19).
`advmon_seen` is `true` when an AdvertisementMonitor `DeviceFound` tagged the
Device1 (see [Listen-monitor overlay](#listen-monitor-overlay---listen-monitor)).
`advertising_flags` is the Flags AD field as hex when BlueZ exposed it;
missing Flags is recorded as absent — the device is never dropped for it.
`is_cached` is `true` when the device was returned by BlueZ as a
cached/bonded entry without active RSSI (not seen advertising during this
scan).

### `grouped` — Grouped by transport type

```json
{
  "le_devices": {
    "devices": [{"address": "AA:BB:...", "name": "...", ...}]
  },
  "classic_devices": {
    "devices": [{"address": "11:22:...", "name": "...", ...}]
  },
  "dual_devices": {
    "devices": [{"address": "DD:EE:...", "name": "...", ...}]
  }
}
```

## Scan Strategy

The survey loop alternates LE and BR/EDR phases each round:

```
Round 1:  LE scan (30s) → Classic scan (30s)
Round 2:  LE scan (30s) → Classic scan (30s)
...
```

With `--duration 120 --round-time 30`, this gives 2 full LE+Classic cycles.
Each phase reuses the existing `passive_scan()` (LE) and adapter inquiry
(Classic) — no new BlueZ interaction code.

Devices seen in both LE and Classic rounds are automatically classified as
`dual`. RSSI min/max/average is tracked across all sightings.

## Multi-Antenna Collection

The single-adapter loop above **time-slices** one radio between LE and BR/EDR.
With two or more adapters you can instead collect on several antennas
**simultaneously** — the model needed for the longer-term goal of passively
collecting on one antenna while another enumerates the devices seen.

Enable it by repeating `--collector`; this overrides `--adapter`/`--transport`:

```bash
# Transport-split: hci0 sweeps LE while hci1 does BR/EDR inquiry (concurrently)
bleep survey --collector hci0:le --collector hci1:bredr --duration 300 --live -o t.json

# Bare adapters use the DEFAULT transport-split profile (le/bredr round-robin)
bleep survey --collector hci0 --collector hci1 -o t.json      # == hci0:le, hci1:bredr

# Spatial profile: same transport on multiple antennas (wider coverage / triangulation)
bleep survey --collector hci0:le --collector hci1:le --collector hci2:le -o t.json
```

`--collector hciN[:TRANSPORT]` — `TRANSPORT` is `le`, `bredr`, or `both`.

### Concurrent enumeration (`--enumerator`)

With a second adapter you can collect on one radio while another enumerates
(and optionally pairs) devices from the live census. Collectors stay in
discovery (`Discovering=true`); the enumerator never runs `StartDiscovery` on a
collector session.

```bash
# Listen on hci0, enumerate on hci1 (passive GATT)
bleep survey --collector hci0:le --enumerator hci1:passive --duration 300 --live -o t.json

# Same, but attempt a bond on the enumerator Device1 then passive-enum
bleep survey --collector hci0:le --enumerator hci1:pair --duration 300 --live -o t.json

# Bare --enumerator promotes --adapter/--transport to the collector
bleep survey --adapter hci0 --transport le --enumerator hci1:naggy -o t.json
```

`--enumerator hciN[:MODE]` — `MODE` is `passive` (default), `naggy`, `pokey`,
or `pair`. `brute` is accepted but mapped to `pokey` (survey has no
`--write-char` payload). The enumerator adapter **must** be distinct from every
`--collector` / promoted `--adapter`. Pairing is refused on collector sessions.

`--then-aoi` forwards `--adapter` to `bleep aoi scan`; when `--enumerator` was
used, the enumerator radio is the one forwarded.

`--duration` is the **listen/admission** window. Collectors harvest every
`--round-time` on a thread that never waits for GATT. The enumerator is a
worker: it picks the live census by `sighting_count` (then recency, then RSSI)
and takes as long as each target needs. When listen ends, collectors stop;
the worker finishes the current device and the remaining queue. A MAC already
enumerated (or attempted) this run is not picked again when collectors keep
seeing it. `--enum-cooldown` (default 3600s) also skips devices with a recent
DB `enumerated_at` (schema v20). `--live` reports `enum=<MAC> q=N
enumerated_ok=M attempted=N`. `enumerated_by` (JSON + DB) is set only on GATT
success. Survey exit joins the worker, then disconnects leftover enumerator
Device1s so a later `enum-scan --adapter hciN` does not skip-connect a stale
ACL.

**Live listen-only (2026-09-04).** `--collector hci0:le --listen-monitor
--duration 60 --round-time 10` → wall-clock 60s, 7 harvest rounds, 9 LE,
regulars at `sightings: 7`, overlay 1 monitor / 7 Flags-OR.

**Live dual (2026-09-05) — not accepted.** Same command plus
`--enumerator hci1:passive` reached 22 LE and `enumerated_ok=6` then
**SIGABRT** (`malloc(): unaligned tcache chunk detected`). Census JSON was
not written; leftover enumerator ACL remained, so a following
`enum-scan --adapter hci1` skip-connected BLECTF. Harvest/GATT overlap
during the first 60s was not in the surviving terminal scrollback (only
the enum tail, `round` frozen at 6). A `PYTHONFAULTHANDLER=1` re-run the
same evening reproduced the abort (exit 134) and localised it to the
enumerator worker inside `_LEDevice.__init__` → `bus.get_object`, reached
via per-target `create_device_manager()` rebuilds. Do not treat
leftover-sweep or JSON emit as proven until a dual run exits 0.
See `todo_tracker.md`.

> **PLANNED (not yet implemented) — two-phase transport-priority
> enumerator.** The enumerator is being redesigned so LE/GATT enumeration
> of newly observed targets always outranks BR/EDR work: LE is perishable
> (a device answers only while advertising) whereas BR/EDR is durable (SDP
> and l2ping answer whenever the device is present). New targets preempt
> BR/EDR at the next unit boundary — never mid-enumeration — and BR/EDR
> only runs once the queue of un-attempted LE targets drains. BR/EDR
> targets exclude `random` addresses (not BD_ADDRs) and include `public`
> ones even when currently typed `le`, since `public` is inconclusive.
> Per-transport results are tracked in separate DB columns
> (`enumerated_*` = LE/GATT, `br_enumerated_*` = SDP); combining them is an
> analysis-side concern. Full design, test matrix, and open decisions:
> `todo_tracker.md` → "Option B — two-phase transport-priority enumerator".

Debug-shell `survey start` refuses `--collector`, `--enumerator`, and
`--listen-monitor` — run those from the CLI.

> **BlueZ notes.** Device1 objects are per-adapter (`/org/bluez/hciN/dev_…`).
> `Adapter1.ConnectDevice` is used when present; otherwise the enumerator does a
> short discovery on **its** adapter only. Agent1 is process-global; bonds live
> on the enumerator Device1. `StopDiscovery` still clears unpaired non-connectable
> beacons (STOP_CLEARS) — that is why collectors stay discovering while the
> enumerator works.

### Collector stall detection (`--stall-rounds`)

> **Scope: multi-antenna (`--collector`) runs only.** The stall detection,
> escalation ladder, `.health.json` degradation, and early listen-monitor
> termination described here are implemented in `run_multi_collector()`
> (`modes/survey_multi.py`). The single-adapter survey loop (`modes/survey.py`)
> validates `--stall-rounds` but does not perform stall re-arm.

A collector can go deaf while BlueZ still reports `Discovering=true`. The old
loop never noticed, so the run continued for hours producing a census that
looked healthy but had frozen — this invalidated a 2h run that collected 11
devices and was dead from the 240s mark.

**`Discovering` is not a health signal.** What works is
`SurveyCensus.progress_counters()` → `(total_sightings, total_rssi_reports)`.
Both advance *only* on a live advertisement report; a cached `Device1` re-read
(no RSSI, paired/bonded) increments neither. A dead discovery keeps returning
cached objects from `GetManagedObjects`, so both totals freeze while the flag
stays true. Device *count* alone is unusable, since a static environment
legitimately plateaus while these keep climbing.

After `--stall-rounds` consecutive report-free rounds (default 3 = 90s at the
default round time) the **escalation ladder** runs. The first round only
establishes a baseline, so a slow start is never treated as a stall.

| Rung | Action | Gate |
|------|--------|------|
| 1 | Stop/start discovery, with the D-Bus **reply** wait bounded to 5s | always |
| 2 | Adapter power cycle | **only** with `--auto-recover` (mutates host BT power state) |
| 3 | **End the listen phase early**, proceed to enumeration, write output | always |

Rung 1 is bounded because a wedged bluetoothd returns *no reply at all*, and
dbus-python's 25s default then costs ~25s per attempt on the collector thread —
a 2h run lost roughly 9 minutes that way. Escalation happens after **2** failed
re-arms, since 21 identical timeouts in that run proved repetition is worthless.

Rung 2 cannot help when bluetoothd itself is blocked (it is still a D-Bus
write), which is exactly why rung 3 exists: a run that cannot recover stops
burning the clock instead of silently collecting nothing for 85 minutes.

Each stall logs the real `Powered`/`Discovering` values plus census size, pool
occupancy, RSS and threads. A probe that goes unanswered is logged as
`<no reply>`, which distinguishes a wedged **daemon** from a wedged **radio**.

Degraded coverage is always reported at run end and written to
`<output>.health.json` (`stall_events`, `rearm_ok`, `rearm_failed`,
`listen_ended_early`, `degraded`). It is a sidecar rather than a field in the
census because the output payloads are top-level lists consumed by
`bleep aoi scan`.

> **BlueZ note.** Discovery is **per-D-Bus-client** state. An external
> `dbus-send … StopDiscovery` returns `No discovery started` and cannot touch
> another client's discovery. This is also why the
> `StopDiscovery failed … No discovery started (Discovering=True)` message is
> *not* contradictory: a different client still holds discovery.

### Loop-free operation (`--no-mainloop`)

Long dual collector+enumerator runs die of **heap corruption**, not of any BLEEP
logic error: `malloc(): unaligned tcache chunk detected` → SIGABRT 134.
Time-to-abort scales with D-Bus call **rate**, not wall clock: `--round-time 10`
aborted in ~60s, `--round-time 30` at 54.7 min.

**Root cause** (Valgrind/Helgrind, 2026-09-08 — see `todo_tracker.md` mainloop_architecture.md).
The contended object is the **process-global default `GMainContext`**, created
at import by `DBusGMainLoop(set_as_default=True)` (`core/config.py:95`). Every
blocking D-Bus call from a worker thread registers a pending-call timeout, and
dbus-glib attaches/removes that `GSource` **on the default context, from the
calling thread**, while `bleep-mainloop` is inside `g_main_loop_run()`
dispatching the same context. Each thread holds only the *libdbus connection*
mutex, so two threads mutate one GLib hash table under two locks that do not
exclude each other — corrupting heap metadata that glibc reports later, at an
unrelated `malloc`.

This is why a **private** bus never helped: `g_main_context_default()` is
process-global, so a private `DBusConnection` still attaches its watches and
timeouts to the same context. The corrupted object was never the connection.

`--no-mainloop` removes the loop thread entirely, so there is no context to
race on. A 2h run with it was clean; the same command without it aborted.
Collectors harvest by polling `GetManagedObjects`, and enumeration waits on the
`ServicesResolved` **property**, so a *passive* survey never needed signal
delivery in the first place.

> **Loop-free is passive-only.** **Deep enumeration requires the MainLoop** —
> notifications and indications are signal-delivered, and `StartNotify`
> delivers nothing without a loop. Use `--no-mainloop` for passive collection
> and passive enumeration; for deep enumeration, keep the loop and accept the
> abort risk on long runs until a real fix lands. The flag is always the
> operator's explicit choice — nothing selects it automatically.

**What it costs.** Nothing dispatches inbound D-Bus traffic, so these stop
working and the flag prints a `LOG__USER` warning naming each one:

| Disabled | Consequence |
|----------|-------------|
| AdvMonitor callbacks (`Activate`/`DeviceFound`/`Release`) | `--listen-monitor` registers but goes inert |
| Pairing agent requests (`RequestPasskey`/`RequestConfirmation`) | Pairing cannot complete |
| GATT notifications / indications | `StartNotify` delivers nothing |
| GATT server and advertise modes | Inbound method calls unanswered |

The combinations that would fail *silently* are refused outright with exit 2:
`--no-mainloop` with `--listen-monitor`, and with pair mode. `BLEEP_NO_MAINLOOP=1`
does the same thing as the flag and still works as a diagnostic override.

> Per-target GATT results are unchanged with the loop off — enumeration
> fidelity was verified across runs. It is a **transport/dispatch** change, not
> an enumeration change.

### Enumeration device pool (`--max-enum-devices`)

Every `_LEDevice` registers itself with the global signals manager in
`__init__`, but `signals.unregister_device()` had **no callers anywhere in the
tree**. Device objects were therefore pinned for the life of the process along
with their D-Bus proxies and entire resolved GATT trees, and `manager._devices`
never evicts either — a 2h survey peaked at 206 MB.

Enumeration devices now go through a bounded LRU
(`bleep/dbuslayer/device_pool.py`, default 10). Past the cap the
least-recently-used device is `release()`d: unregistered from signal routing,
signal matches removed, proxies dropped, GATT/notification caches cleared. That
makes it collectable. `release()` is local-only (no D-Bus I/O), so it is safe on
a device that already disconnected, and it does **not** drop the ACL.
Re-enumerating a tracked address refreshes its recency instead of evicting it.

Scoped to the enumeration path deliberately — the same containment rule as the
10s `ConnectDevice` bound. Manager-owned devices are **not** pooled: the
collector keeps them in its own map and would be handed torn-down objects.

**Tuning the cap.** The cap is a free-form knob, not a fixed 10, so the
footprint/throughput trade can be retuned as the enumerator evolves:

| Setting | Effect |
|---------|--------|
| `--max-enum-devices N` | Any `N ≥ 1`. Lower = tighter memory, more teardown churn |
| `--max-enum-devices 0` | **Unlimited** — never evicts. Prints a warning. For A/B-ing the cap itself against a suspected fault |
| `BLEEP_MAX_ENUM_DEVICES=N` | Same cap for entry points **without** the flag (`enum-scan`, `explore`, `gatt-enum`, `aoi`, debug shell). The flag wins where both apply |

A malformed or negative env value warns and falls back to 10 rather than
raising — an env typo must not abort a long survey. Lowering the cap at runtime
evicts the backlog immediately.

The debug shell honours `--max-enum-devices` (the pool is process-wide, so it
also bounds later in-session `enum`/`connect` work) but **refuses**
`--no-mainloop`, which would disable notifications and pairing for the whole
interactive session.

> Capping objects does **not** fix the heap corruption above — that is a data
> race, and `--no-mainloop` is what addresses it. This bounds footprint and
> blast radius on long runs.

### Listen-monitor overlay (`--listen-monitor`)

AdvertisementMonitor is a **filter overlay**, not the census. Empty BlueZ
`or_patterns` is illegal (`Release`, 0 events). `--listen-monitor` registers
the Flags-OR overlay ([adv_monitor.md](adv_monitor.md): one monitor, GAP Flags
`{00,02,04,05,06,18,1A}`) on every LE/`both` collector **while StartDiscovery
stays running**. Completeness is the union of:

1. StartDiscovery Device1 harvest (R1/R2 `GetManagedObjects` / session census)
2. AdvMonitor `DeviceFound` → Device1 `Properties.GetAll`

Neither source is an inclusion gate. A device seen only on Found still enters
the census (`sightings=1`, `advmon_seen=true`). A device already harvested is
tagged `advmon_seen` without a double-count. Missing Flags is data, never a
drop.

This is **not** `--variant passive` (that remains StartDiscovery). BR/EDR-only
`--listen-monitor` exits non-zero. Extra filters require `--listen-monitor`:

- `--listen-pattern OFF:AD:HEX`
- `--listen-manufacturer CID[:HEX]` — SIG company id (decimal or `0x`-hex),
  optional payload hex prefix. Encoded as AD `0xFF` at offset 0, CID
  little-endian (`6` → `0600`, `0xFFFF:5a33` → `ffff5a33`).
- `--listen-mfr-string TEXT` — UTF-8 bytes at AD `0xFF` offset 2 (first
  payload byte after the CID). Memcmp, not a substring search; other offsets
  use `--listen-pattern`.

Extras register as a **second** `or_patterns` child. Mixing 0xFF extras onto
the Flags-OR child `NoReply`-killed software AdvMonitor on this host. Census
unions `DeviceFound` from both children. Same-adapter AdvMonitor +
`StartDiscovery` is allowed (BlueZ Found/Lost fire during an ongoing discovery
session). `STOP_CLEARS` is still `StopDiscovery` only.

```bash
# Flags-OR AdvMonitor overlay on the default adapter's LE/both discovery
bleep survey --listen-monitor --duration 120 --live -o t.json

# Dual-antenna: listen+overlay on hci0, enumerate on hci1
bleep survey --collector hci0:le --listen-monitor --enumerator hci1:passive -o t.json

# Microsoft CID 6 + ESP32 manufacturer payload prefix / "Z3" string
bleep survey --listen-monitor --listen-manufacturer 0x0006 \
    --listen-manufacturer 0xFFFF:5a33 --listen-mfr-string Z3 -o t.json
```

Requires `bluetoothd -E` / `Experimental=true`. `bleep --check-env` probes
`AdvertisementMonitorManager1`. Overlay registration failure is logged; the
StartDiscovery harvest continues so the run does not silently produce an
empty census. The Flags-OR set fits MSFT's 16 patterns/monitor cap.

### Coverage profiles

| Profile | How to select | Use case |
|---------|---------------|----------|
| **transport-split** (default) | bare adapters, or explicit mixed transports | One antenna per transport — no LE↔BR/EDR time-slicing, so neither transport starves the other. |
| **spatial** | same explicit transport on ≥2 adapters | Multiple same-transport antennas for wider physical coverage or RSSI triangulation. |

Bare (transport-less) adapters are assigned transports round-robin from
`(le, bredr)`, so two bare adapters split LE vs BR/EDR automatically.

### How it works

All collectors run **concurrently** on a single shared GLib main-loop
(`bleep.dbuslayer.loop_service`) rather than each blocking its own thread on a
separate loop. Each round: every adapter starts discovery, scans the same
window, then its sightings are harvested (filtered to that adapter's
`/org/bluez/hciN/` object-path so antennas never double-count each other) and
merged into one shared, thread-safe `SurveyCensus`. RSSI observations are routed
back to the emitting adapter by parsing the adapter out of the D-Bus object path
(adapter-aware signal routing), so a sighting on `hci1` never lands in `hci0`'s
cache. The `seen_by` output field records which antennas saw each device.

> **Scaling note.** The shared-loop service is reference-counted and sized for
> the expected handful of adapters. A thread-per-collector design (one
> `GLib.MainContext` per antenna) is documented as a future option in
> `loop_service.py` should profiling ever show the single loop thread
> saturating; it is deliberately deferred to keep one signal-routing path.

Adaptive round timing (`--adaptive`) and `--auto-recover` apply to the
single-adapter loop only; multi-antenna runs use a fixed per-round window.

## Device-Type Classification

Survey uses the `DeviceTypeClassifier` result (already computed by the
adapter layer during scanning) to assign `device_type` instead of relying
solely on which scan round discovered the device. This prevents
cached/bonded Classic devices returned by BlueZ during the LE scan phase
from being incorrectly labelled as `"le"`.

The Classic (BR/EDR) round keeps devices the inquiry can legitimately
account for — both pure Classic (`"br/edr"`) **and** dual-mode (`"dual"`)
devices — and excludes `"le"`/`"unknown"` so LE-only devices cached from a
prior round are not miscounted as Classic sightings. Each device is persisted
with its actual transport (`br/edr`→`classic`, `dual`→`dual`), so a dual-mode
device (e.g. an audio headset advertising LE while remaining BR/EDR-inquirable)
is neither dropped from a `--transport bredr` survey nor downgraded to
`classic` in the database.

Cached or bonded devices that appear without active RSSI are flagged with
`is_cached: true` in the output. Use `--exclude-cached` to remove them
from the output entirely:

```bash
bleep survey --exclude-cached -o targets.json
```

### Sighting-count semantics

`sightings` counts **live** observations — rounds where the device was actually
seen advertising — not raw `GetManagedObjects()` re-reads. A cached/bonded device
(`is_cached: true`) that BlueZ keeps listing without advertising does **not** increment
its count on each round, so bonded devices no longer inflate to ≈2×rounds. A device
first seen only as a cached entry starts at `sightings: 0` and is therefore excluded by
the default `--min-sightings 1` (identical to `--resume-db` seeded devices); pass
`--min-sightings 0` to include it. Once a cached device is seen advertising again its
`is_cached` flag clears and the count resumes incrementing. A dual-mode device seen live
in both the LE and Classic phases of one round counts as two sightings for that round.

The "live" test keys on the same predicate as `is_cached` — no fresh RSSI **and**
paired/bonded — rather than on RSSI alone, because under passive scanning
(`DuplicateData=True`) BlueZ drops RSSI for a small fraction of genuine advertisements.
Gating on raw RSSI would therefore undercount real, unpaired advertisers. To improve
RSSI availability, the survey captures RSSI from both `PropertiesChanged` **and** the
first-seen `InterfacesAdded` event; RSSI is only recorded while discovery is active, so
a recorded value always corresponds to a fresh advertisement in the current round.

### Non-connectable beacon harvest (R1/R2)

LE survey rounds call `passive_scan` / `naggy_scan`, which consume
`DeviceManager.take_last_harvest()` after a pre-`StopDiscovery` snapshot (R1).
A session census from D-Bus signals (R2) keeps last-seen manufacturer/service
data when BlueZ deletes unpaired non-connectable `Device1` objects on stop
(`STOP_CLEARS`). Multi-collector mode uses `AdapterSession.harvest` →
`snapshot_discovered_devices()` while Discovering is still true. Classic BR/EDR
inquiry still uses the adapter timed-scan path (unchanged; not the beacon
`STOP_CLEARS` case).

## BlueZ Health Monitoring

When the `BlueZServiceMonitor` D-Bus bindings are available, the survey loop
automatically starts a background health-check thread.  If BlueZ becomes
unresponsive (stall) or the daemon goes away, a warning is emitted to stderr
before the next round.  With `--live`, each round shows the adapter health in
the progress line: `BlueZ: OK` for a productive round, or
`BlueZ: adapter not ready` for a round that could not scan.  The monitor is
stopped cleanly when the survey ends or is interrupted.

## Adapter-Drop Resilience

If the Bluetooth controller becomes not-ready **during** a survey (the adapter
is powered off, soft-blocked by rfkill, or a cheap controller resets while the
survey alternates LE and BR/EDR discovery), the affected round cannot scan.
Rather than aborting the whole run, the survey:

- **skips the round** instead of crashing (a single transient `NotReady` no
  longer kills a multi-hour survey),
- **paces** the loop with a short backoff so a fast-failing round cannot
  busy-loop the CPU or spam warnings,
- keeps the in-memory census and, on completion, **exits `0`** with a partial
  result plus a prominent `N/M round(s) skipped` warning.

The true fix for a persistently not-ready adapter is environmental — keep the
controller powered:

```bash
rfkill unblock bluetooth
# /etc/bluetooth/main.conf
[Policy]
AutoEnable=true
dmesg | grep -i bluetooth   # look for controller resets / firmware errors
```

### `--auto-recover` (opt-in)

For hosts where the controller occasionally drops, `--auto-recover` attempts a
bounded (up to 3) in-run power recovery — re-assert `Powered`, then a full
power-cycle — and resumes the survey if the adapter comes back. It is **off by
default** because it mutates host Bluetooth power state; it does not fix rfkill
or hardware faults (after the attempt cap it falls back to skip-and-backoff).

```bash
bleep survey --duration 14400 --transport both --auto-recover --live -o out.json
```

## Discovery Error Surfacing (diagnostics)

Every `StartDiscovery` / `StopDiscovery` / `SetDiscoveryFilter` failure taken
during a round is **surfaced, not swallowed**.  When BlueZ rejects one of these
calls the adapter/manager layer emits a real warning carrying the exact D-Bus
error name and the adapter's current `Discovering` state, e.g.:

```
[!] StopDiscovery failed on /org/bluez/hci0: org.bluez.Error.Failed: No discovery started (Discovering=False) (degraded to no-op)
```

The most recent failure is also recorded on the object for programmatic
inspection (`system_dbus__bluez_adapter._last_discovery_error` and the matching
field on the device manager) as a dict of
`{method, error_name, error_message, discovering[, degraded]}`.  Control flow and
return values are unchanged — this is diagnosability only.  The happy path (normal
LE↔Classic transitions) emits **no** such warnings.

This matters for the LE↔Classic transition: on a single, uncontended adapter the
transition is race-free (validated on BlueZ 5.84 and 5.64), but a second D-Bus
client holding a discovery session keeps the adapter's global `Discovering`
property pinned `true`, and a same-sender `StopDiscovery` with no active session
returns `org.bluez.Error.Failed: No discovery started`.  Surfacing that error is
what lets an operator diagnose cross-client contention instead of silently
scanning on the wrong transport.  See `docs/todo_tracker.md` → "Step-3" for the
full evidence packet.

## Resuming from Database

Use `--resume-db` to pre-seed the census with devices previously observed by
BLEEP. Seeded devices start with `sighting_count=0`, so the default
`--min-sightings 1` filter excludes them unless they are re-seen during the
live scan. Use `--min-sightings 0` to include all historical devices in the
output.

```bash
bleep survey --resume-db --duration 120 --live -o targets.json
bleep survey --resume-db --min-sightings 0 -o all_known.json
```

This is useful for comparing historical vs. currently-active devices, or for
enriching a previous survey with fresh RSSI and fingerprint data.

## Adaptive Round Timing

Use `--adaptive` to let the survey dynamically adjust round duration based on
device discovery rate:

- **Zero new devices** in a round → halve the round time (faster cycling)
- **3+ new devices** → extend by 10 seconds (capture more)
- **1–2 new devices** → hold steady

The dynamic range is bounded by `--adaptive-min` (default 10s) and
`--adaptive-max` (default 60s). With `--live`, the current round time is
shown as `rt=Ns`.

```bash
bleep survey --adaptive --live -o targets.json
bleep survey --adaptive --adaptive-min 5 --adaptive-max 90 --live -o targets.json
```

## Graceful Interruption

Pressing Ctrl-C during a survey stops after the current round and writes
output with whatever data has been collected. Long surveys can always be
stopped early without losing results.

## Census Checkpointing (SR-G1)

By default the census JSON is written only once, at the very end of the run.
For long surveys, use `--checkpoint-interval N` to periodically flush the
partial census to `<output>.partial` every `N` seconds, so a hard crash or
power loss cannot lose the aggregated census/RSSI history (individual sightings
are persisted to the DB independently):

```bash
# Flush a partial snapshot every 60s during a 30-minute survey
bleep survey --duration 1800 --live -o targets.json --checkpoint-interval 60
```

- The checkpoint file (`<output>.partial`) is written **atomically** (temp file
  + `os.replace`) by `_write_survey_checkpoint()` and uses the **same filter and
  format** as the final output (`_format_survey_output()`).
- It is removed automatically after the clean final write.
- **Requires `-o`/`--output`** and a positive interval; `0` (default) disables it.
- Graceful `SIGINT`/`SIGTERM` already fall through to the final write; checkpoints
  additionally harden against hard crashes.
- **Available in both the CLI and the debug shell:** `survey start
  --checkpoint-interval N` uses the same worker helper (see
  [Debug Shell Integration](#debug-shell-integration)).

## Integration with AoI Pipeline

```bash
# Step 1: Discover devices
bleep survey --duration 300 --live -o targets.json

# Step 2: Inspect/edit target list (optional)
cat targets.json | python3 -m json.tool | head -20

# Step 3: Enumerate all targets
bleep aoi scan targets.json --deep --timeout 60

# Step 4: Per-device report (single device)
bleep aoi report --address AA:BB:CC:DD:EE:FF --format markdown

# Step 4b: Aggregate report (all AoI-analyzed devices)
bleep aoi report --all --format markdown

# Step 5: Export all data
bleep aoi export -o ./survey_results/
```

### One-Command Pipeline

Use `--then-aoi` to automatically chain survey discovery into AoI enumeration:

```bash
bleep survey --duration 300 --live -o targets.json --then-aoi
```

This runs the survey, writes the target list to `targets.json`, and then
immediately invokes `bleep aoi scan targets.json`.

## Examples

```bash
# Quick LE-only survey, simple MAC list
bleep survey --transport le --format simple -o le_targets.json

# Longer survey with filtering
bleep survey --duration 600 --live --min-rssi -80 --min-sightings 2 -o targets.json

# Classic-only survey
bleep survey --transport bredr --format objects -o classic_targets.json

# Pipe to stdout (progress goes to stderr)
bleep survey --live | tee targets.json

# Skip Classic DB writes (LE scan DB writes are always active via core infra)
bleep survey --no-db --duration 30 -o test.json

# Survey + auto-AoI enumeration in one command
bleep survey --duration 120 --live -o targets.json --then-aoi

# Resume from DB, include all historical + newly seen devices
bleep survey --resume-db --min-sightings 0 -o all.json

# Adaptive timing for dynamic environments
bleep survey --adaptive --live -o targets.json

# Full-featured: resume + adaptive + auto-AoI
bleep survey --resume-db --adaptive --live -o targets.json --then-aoi

# Generate aggregate report after enumeration
bleep aoi report --all --format json -o aggregate.json
```

## Debug Shell Integration

Survey can also be launched from within `bleep debug` interactive mode:

```bash
BLEEP-DEBUG> survey start --duration 120 --round-time 15 -o /tmp/targets.json
BLEEP-DEBUG> survey-status
BLEEP-DEBUG> survey stop
```

The survey runs in a **background thread** (same model as `monitor start|stop`),
so the debug shell prompt remains interactive while the survey is running. The
debug `survey start` command shares the full CLI flag set via the same parser,
including `--checkpoint-interval`: with `-o FILE --checkpoint-interval N` the
background worker atomically flushes the aggregated census to `FILE.partial`
every `N` seconds (via the same `_write_survey_checkpoint()` helper as the CLI)
and removes it after the clean final write — see
[Census Checkpointing](#census-checkpointing-sr-g1).

| Command | Description |
|---------|-------------|
| `survey start [opts]` | Launch a background survey with the given options |
| `survey stop` | Stop the running survey early (writes output with collected data) |
| `survey-status` | Print survey progress: state, round, elapsed, device counts |

Exiting the debug shell (`quit`/`exit`) automatically stops any running survey.

## Duration and Round-Time Guidance

| Scenario | Duration | Round-Time | Notes |
|----------|----------|------------|-------|
| Quick ambient check | 60 | 30 | 1 LE+Classic cycle |
| Default survey | 120 | 30 | 2 cycles, catches transient devices |
| Thorough survey | 300–600 | 30 | 5–10 cycles, good for busy environments |
| Extended recon | 1800+ | 60 | Automatically segmented — see below |

Shorter `--round-time` values (10–15s) cycle transports more frequently but
increase BlueZ stop/start churn. Longer values (60s+) are more stable but
alternate transports less often.

## Segmented long runs (`--segment-time`)

A single survey process stops collecting after roughly **80 harvest rounds
(~42 minutes)**: the adapter stops answering D-Bus entirely and no in-process
recovery brings it back. It is not adapter hardware, not enumeration, and not
the main loop — all of those were ruled out by controlled runs (see
`d-bus-reliability.md`, "the ~42-minute collector ceiling"). It ends when the
process exits; a fresh process collects normally from the first round.

So a `--duration` longer than one segment is executed as **consecutive segments
in fresh processes, then merged into a single census**. This is automatic:

```bash
# 4 hours, run as 8 half-hour segments and merged — no extra flags needed
bleep survey --collector hci0:le --enumerator hci1:passive \
    --duration 14400 -o survey.json
```

```
[survey] Long run split into 8 segment(s) of 1800/1800/... (14400s total)
[survey] === segment 1/8 (1800s) ===
...
[survey] Merged output written to survey.json
[survey] Segmented run complete: 214 unique device(s) from 8/8 segment(s)
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--segment-time N` | `1800` (30 min) | Maximum listen seconds per process. A `--duration` above this is split. |
| `--segment-time 0` | — | Never split. One process, any duration — expect the ceiling above ~42 min. |

**What you get on disk.** Each segment's own output is kept beside the merged
file, so a long run is inspectable part-by-part and an interruption costs at
most the current segment:

```
survey.json                        # merged census
survey.json.health.json            # aggregated health + segments_planned/completed
survey.json.segment01.json         # per-segment census
survey.json.segment01.json.health.json
...
```

If **no** segment produces output — an adapter that is down, say — the merged
file is left untouched rather than overwritten with an empty census, so a
failed run cannot destroy a previous one.

**How merging works.** Segments emit the canonical `objects` payload and are
folded together on address:

- `sightings` sum; `rssi_avg` is re-derived as a **sightings-weighted** mean, so
  a one-sighting segment cannot drag a hundred-sighting segment halfway — and
  is rounded to a whole dBm, as every other survey output is
- `rssi_min`/`rssi_max` widen; `first_seen`/`last_seen` span all segments
- `uuids` and `seen_by` union; `manufacturer_data`/`service_data` combine
- `fingerprint_changed` and `advmon_seen` latch on; `name`, `tx_power`,
  `appearance` and `enumerated_by` fill in from whichever segment learned them
- `is_cached` survives only if **no** segment saw the device live
- a device seen as `le` in one segment and `classic` in another becomes `dual`,
  which is exactly what that label records

Your `--format` choice still applies to the merged result (`objects`, `simple`
and `grouped` all work). `--then-aoi` runs once, on the merged census, rather
than per segment.

**Caveats.** Devices present only briefly between segments can be missed during
the sub-second process handover. Each segment starts discovery afresh, so a
device's `first_seen` reflects when that segment saw it. Segmentation is
skipped entirely for the common short run, so default behaviour is unchanged.
