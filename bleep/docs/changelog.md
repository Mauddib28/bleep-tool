## Unreleased

_No unreleased changes yet._

## 3.1.0 (2026-09-13)

### Documentation-fidelity remediation + version bump (2026-09-13)

Version bumped **3.0.0 → 3.1.0** (`bleep/__init__.py`, `setup.py`;
`bleep --version` now reports `BLEEP 3.1.0 (DB schema v20)`).

All user and internal documentation was audited against the current
implementation and corrected for fidelity (no code behaviour changed). Notable
fixes: `ble_scan_modes.md` passive-connect parameters (`connect_wait_timeout`
min 5, `timeout_services` `max(timeout,15)`, `max_attempts` 2) and the
debug-shell `enumb`/ROE semantics (single-characteristic, `respect_roeng=False`;
`all` is CLI-only via `enum-scan --write-char all`); `user_mode.md` menu
examples now include the required `--menu`; `debug_mode.md` `dbexport [--save]`;
`bl_classic_mode.md` logging section repointed to `~/.local/share/bleep/logs/*.log`
(legacy `/tmp/bti__logging__*.txt` symlinks) and PAN `--role`/`copp exchange`
corrections; `map_bmessage_format.md` source citations refreshed;
`pan_connection_analysis.md` event-driven `_verify_connected` and archive links;
agent/pairing docs (`stop_glib_mainloop`/`ensure_glib_mainloop` in
`debug_state.py`, `--reset`-gated stale-bond removal, `register()` defaults);
observation-DB docs (getter signatures, `sighting_count` per-run semantics,
`analysis_details` = `details` sub-dict, `audio_recon` cascade exception,
`store_aoi_analysis` example nested under `summary`);
`device_type_classification.md` collector-mode matrix and dual/LE logic;
`dbus_best_practices.md` log-path symbol; and `survey_mode.md` `--variant` row +
`--stall-rounds` multi-collector scoping. All 67 markdown files pass internal
link/anchor and code-fence validation.

### Segmented long surveys + documentation consolidation (2026-09-08)

**New: `--segment-time` (default 1800s = 30 min).** A `--duration` longer than
one segment is now executed as consecutive segments in **fresh processes** and
merged into a single census, because a single process stops collecting after
~80 harvest rounds (~42 min). Ruled out as causes, each by controlled
measurement: adapter hardware (wedges identically on `hci1`), the enumerator
(wedges with none configured), long-lived discovery sessions (wedges with
discovery torn down every round), the GLib loop (all runs loop-free), and
`dbus-daemon` match-rule/reply limits, socket backpressure, signals-registry
retention and BlueZ object accumulation. `d-bus-reliability.md` carries the
table so it is not re-investigated. `--segment-time 0` restores single-process
behaviour.

Merging folds per-segment `objects` payloads on address: `sightings` sum,
`rssi_avg` becomes a **sightings-weighted** mean, RSSI extremes widen,
timestamps span all segments, `uuids`/`seen_by` union, payload dicts combine,
`is_cached` survives only if no segment saw the device live, and a device seen
`le` in one segment and `classic` in another becomes `dual`. Per-segment
outputs and health sidecars are kept beside the merged file, so an interruption
costs at most one segment. `--then-aoi` runs once on the merged census.
`format_grouped` was refactored onto a new `SurveyCensus.group_objects()` so the
merger regroups without a second copy of the bucketing rules. 39 tests in
`tests/test_survey_segments.py`; verified end-to-end on hardware (two 60s
segments, 17 devices each, merged to 17 unique with sightings summed 67+67=134).

**Documentation consolidated.** ~780 lines of run-by-run narrative were removed
from `todo_tracker.md` after relocating the durable knowledge to the documents
that own those areas: the `GMainContext` data-race root cause and the rule
against driving GATT from the loop thread to `mainloop_architecture.md`; the
collector ceiling and its eliminated hypotheses to `d-bus-reliability.md`;
operator-facing flag behaviour to `survey_mode.md` and `cli_usage.md`, which
was missing all five of the new flags. The tracker now keeps accepted policies,
open items, and closed-with-reason entries. Stale cross-references from code
comments and other docs were repointed to the new homes.

**Dropped as not operationally relevant:** the ~2.1 MB/round retention
(200 MB/hour on a 15 GB host, and not the stall trigger — one run died at
197.5 MB where another died at 207.7 MB), plus bounding `manager._devices` and
the round-cadence item.

### Debt audit of the collector/enumerator work (2026-09-08)

Whole-module audit of everything the collector/enumerator work added. All seven
new modules have production importers and tests and contain **zero dead
functions**, so the added code is not bloat; the debt was narrower.

**Removed.** The write-only `_services_resolved_pending` flag (`device_le.py`)
— two `Store` sites, zero `Load` sites. The `if self._bus_is_private:` branch
that actually defers the work is kept and its comment corrected: per `mainloop_architecture.md` the
hazard is driving GATT from the loop thread, not the connection's ownership.

**De-duplicated.** `--max-enum-devices` validation and application existed
twice, in `survey.py` and `debug_survey.py`, and had already drifted — the CLI
warned that `0` grows without bound, the debug shell reported "unlimited" with
no warning. Both now call `device_pool.apply_capacity()`.

**Fixed — recovery that degraded the host.** `adapter.power_cycle()` wrapped
both `Powered` writes in one `try`, so a failed power-*on* left the adapter off
and returned a bare `False`. Survey Run E hit exactly this and left `hci0`
`DOWN` after exit with nothing in the log saying so. The writes are now
separate, the power-on is retried once, and the survey ladder prints the
restore command via `_warn_left_powered_off()`. `_power_cycle`'s docstring also
claimed "the ladder has a rung below it" — it does not; the next step is to end
the listen phase.

**Fixed — flaky test.** `test_two_workers_get_different_buses` closed the first
worker's bus before creating the second and compared `id()` snapshots, so
CPython could reuse the freed address. Both connections are now held open
across the comparison.

**Correction.** An earlier draft of `todo_tracker.md` claimed `bus.py`'s
justification was "definitively disproved". That was wrong. `bus.py` never
claimed to fix the abort — it carries an explicit warning that private
connections achieve no isolation and that the corruption still reproduces — and
its stated mechanism ("the GLib main-loop integration ... is not safe against a
second thread adding and removing watches while the loop iterates them") is
precisely what Valgrind **confirmed**. The module is kept unchanged.

### Heap-abort root cause identified via Valgrind (2026-09-08)

Documentation only — no behaviour change. The `malloc(): unaligned tcache chunk
detected` SIGABRT that has driven the loop-free design since B.19 has been
**root-caused** rather than merely avoided.

**It is not a D-Bus connection race.** Helgrind (418 races, 64 contexts) shows
the contended object is the **process-global default `GMainContext`** hash
table, allocated at import by `g_main_context_default()` under
`DBusGMainLoop(set_as_default=True)` (`core/config.py:95`). Every blocking
D-Bus call from a worker thread registers a pending-call timeout, and dbus-glib
attaches/removes that `GSource` **on the default context, from the calling
thread**, while `bleep-mainloop` is inside `g_main_loop_run()` dispatching the
same context. Each thread holds only the *libdbus connection* mutex, so two
threads mutate one GLib hash table under two locks that do not exclude each
other — which corrupts heap metadata that glibc later reports at an unrelated
`malloc`.

This explains all four recorded observations: the loop-on/loop-off asymmetry,
time-to-abort scaling with D-Bus call rate, the abort always landing
in the enumerator thread inside `call_blocking`, and — previously unexplained —
**why the private-bus approach (Option A) never fixed it**: `g_main_context_default()`
is process-global, so a private `DBusConnection` still attaches its watches and
timeouts to the same context. Per-connection isolation was never going to help,
because the corrupted object was never the connection.

Memcheck corroborates: 42 rounds / 31 enumeration attempts (~6x the volume that
normally aborts) across 36 GB of allocation traffic produced **0 errors from 0
contexts**. Memcheck serializes threads, closing the race window; a
deterministic overflow would have been caught immediately.

**Consequence for the design.** `--no-mainloop` is now a *proven* fix rather
than an empirical workaround — but it is only viable for **passive**
enumeration. Deep enumeration needs loop-dispatched signals, so the loop-free
mode is an operator-selectable trade, not a universal default. See
`todo_tracker.md` B.23.

**Memory growth answered.** Run E's in-process sampler measured
36 MB -> 204 MB at ~2.1 MB/round, linear in *productive harvest rounds* and flat
in device count, threads, and fds; RSS flatlined the instant discovery died.
Valgrind classifies it as **0 bytes definitely lost** — Python-level retention,
not a C leak. The census is exonerated by measurement (1.6 kB/round against
2100 kB/round observed).

**Retractions.** "Round cadence degrades with census size" is
**withdrawn** — the 55s rounds are `round_time` plus one 25s D-Bus reply
timeout, and appear only after the adapter stops answering, with the census
frozen. `GIVE_UP` 2-vs-3 is **narrowed**: the third attempt is
reachable for connection/timeout errors and unreachable only for auth-class and
truly-unknown errors.

### Stall escalation ladder + in-process metrics (2026-09-08)

Corrections from the 2h Run D post-mortem, where stall *detection* worked but
**21 of 21 re-arms failed** with `Operation timed out` and the collector stayed
dead for ~70% of the run.

**Escalation ladder.** A re-arm now bounds its D-Bus **reply** wait to 5s
(`REARM_DBUS_TIMEOUT_S`) instead of inheriting dbus-python's 25s default — a
wedged bluetoothd returns *no reply at all*, so the old default cost ~25s per
attempt on the collector thread (~9 minutes across Run D). After **2** failed
re-arms the run escalates to an adapter power cycle, reusing the existing
`adapter.power_cycle()`, and **only** when `--auto-recover` is set, since it
mutates host BT power state; without it the operator is told explicitly that no
power cycle was attempted. If recovery still fails, the **listen phase ends
early** and the run proceeds to enumeration and writes output rather than
burning the remaining clock collecting nothing.

**Diagnostics at each stall.** The previous message asserted "despite active
discovery" without ever reading `Discovering`, so a 2h stall produced no
evidence. Each stall now logs real `Powered`/`Discovering` values plus census
size, pool occupancy, RSS and thread count. An unanswered probe is reported as
`<no reply>` — that is itself the finding, distinguishing a wedged *daemon* from
a wedged radio.

**Degraded coverage is now reported.** `_rearm_collectors` returns
`(succeeded, attempted)`; counting only successes meant 21 consecutive failures
produced complete silence at run end. Health is also written to a
`<output>.health.json` sidecar — not into the census, because the
objects/grouped/simple payloads are top-level *lists* consumed by
`bleep aoi scan` and wrapping them would be a breaking schema change.

**`--metrics-interval N`** samples RSS, VmSize, threads, fds, census size, pool
occupancy, round and phase to `<output>.metrics.csv` from a daemon thread inside
the process. Run D's external sampler died after one sample and silently lost
the measurement for the whole run; an in-process sampler cannot miss the run,
and it can record state no external observer can see.

### Collector stall detection + checkpoint coverage (2026-09-07)

**`--stall-rounds`** (default **3**, `0` = off) detects a collector that has gone
deaf and re-arms it. A stalled discovery keeps `Adapter1.Discovering=true`, so
nothing noticed and a run could burn hours producing a frozen census that looked
healthy (a 2h run collected 11 devices, dead from 240s). New
`SurveyCensus.progress_counters()` returns `(total_sightings,
total_rssi_reports)`, both of which advance *only* on a live advertisement
report — a cached `Device1` re-read increments neither — so they freeze on a
stall while the flag lies. Device count alone is unusable because a static
environment legitimately plateaus. `_ProgressWatcher` counts report-free rounds
and `_rearm_collectors()` does stop-then-start per session, warning at
`LOG__USER` (a re-arm means lost coverage) with a total in the run-end summary.

The fault cannot be injected externally — BlueZ scopes discovery per D-Bus
client, so an outside `StopDiscovery` returns `No discovery started` and leaves
the survey's discovery alone. The decision logic is therefore isolated in
`_ProgressWatcher` and unit-tested directly, including a case driven off a real
census where cached-only rounds trigger the stall and a live report clears it.
This also retires the "contradictory" `StopDiscovery failed … No discovery
started (Discovering=True)` item: per-client discovery makes both the message and
the flag correct.

**Checkpointing now covers the enumeration tail.** The multi-collector checkpoint
was gated on `listening`, so it stopped when the listen window closed and never
protected the enum phase — the longest, riskiest part of a run and where the
aborts landed. Gate removed.

> Correction to an earlier entry: `--checkpoint-interval` was **not** broken.
> It fires correctly in both loops. `<output>.partial` is deliberately deleted on
> successful completion (`survey.py:1323`), and every check for it had been made
> after the run finished. The claim that checkpointing existed only in the
> single-adapter loop was also wrong; it is at `survey_multi.py:373`.

### Loop-free survey + bounded enumeration device pool (2026-09-07)

**`--no-mainloop`** (survey) runs the process with no GLib main loop, which is
what makes long dual collector+enumerator runs survive. The aborts were heap
corruption (`malloc(): unaligned tcache chunk detected`, SIGABRT 134); under
`MALLOC_CHECK_=3` the fault appears as a SIGSEGV in the `bleep-mainloop` thread
while the enumerator thread builds a `DBusException` in `call_blocking` — two
threads in one connection's message machinery. Time-to-abort tracks D-Bus call
*rate* (~60s at `--round-time 10`, 54.7 min at 30). With no loop thread that
pair cannot form: a 2h loop-free run was clean. The survey never needed signal
delivery (collectors poll `GetManagedObjects`; enumeration waits on the
`ServicesResolved` property).

The cost is surfaced, not buried: a **`LOG__USER`** warning names every
capability lost (AdvMonitor callbacks, pairing agent requests, GATT
notifications, GATT server/advertise). The combinations that would degrade
*silently* are refused with **exit 2** — `--no-mainloop` with `--listen-monitor`
or with pair mode. `BLEEP_NO_MAINLOOP=1` remains as a diagnostic override.

**`--max-enum-devices`** (default **10**, `0` = unlimited) bounds live enumeration device
objects. Root cause of the long-run growth: every `_LEDevice` registers with the
signals manager in `__init__`, but `signals.unregister_device()` had **no callers
anywhere in the tree**, so every device ever built stayed pinned with its proxies
and full resolved GATT tree (`manager._devices` never evicts either) — a 2h run
peaked at 206 MB. New `bleep/dbuslayer/device_pool.py` holds an LRU of
enumeration devices and `release()`s what it evicts; new `release()` methods on
`_LEDevice`/`Service`/`Characteristic`/`Descriptor` unregister from signal
routing, remove matches, and drop proxies plus GATT/notification caches. Local
teardown only (no D-Bus I/O, safe post-disconnect) and it does not drop the ACL.
Scoped to the enumeration path — manager-owned devices are not pooled, since the
collector would be handed torn-down objects. Verified live: cap 3 over a survey
produced 28 evictions with enumeration unaffected.

The cap is tunable for later resource work rather than fixed: any `N ≥ 1`,
`0` for unlimited (warns; for A/B-ing the cap against a suspected fault), and
**`BLEEP_MAX_ENUM_DEVICES`** for the entry points that have no flag
(`enum-scan`, `explore`, `gatt-enum`, `aoi`, debug shell), read at pool
construction. A malformed or negative env value warns and falls back to 10 —
an env typo must not abort a long survey. The debug shell honours the cap but
**refuses `--no-mainloop`**, which would kill notifications and pairing for the
whole interactive session; that follows the existing precedent there of
refusing flags it cannot honour instead of accepting and ignoring them.

> Object caps do **not** fix the heap corruption (a data race); `--no-mainloop`
> does. They bound footprint and blast radius.

### Parallel listen + priority enumerator (2026-09-04)

`--duration` is the **listen/admission** window, not a GATT abort. Collectors
harvest on `--round-time` while a worker thread enumerates on the distinct
`--enumerator` adapter. GATT is not cut when the listen clock expires; the
process finishes the in-flight device plus the remaining queue, then writes
JSON. Pick order is `sighting_count` desc, `last_seen` desc, `rssi_avg` desc.
A MAC that succeeded (or was attempted) this run is never re-queued when
collectors increment sightings. Schema **v20** `devices.enumerated_at` plus
`--enum-cooldown` (default 3600s) skip DB-recent successes (`enum-scan` / AoI
/ survey stamp the column only on GATT success). `--live` shows
`enum=<MAC> q=N enumerated_ok=M attempted=N`. ConnectDevice wait stays 15s;
controller timeouts are not used as a survey budget.

Listen-only proof (2026-09-04): `--collector hci0:le --listen-monitor
--duration 60 --round-time 10 --live` → 60s, **7 rounds**, 9 LE, overlay 1×7.

Dual listen+enum (2026-09-05) is **not accepted**. Same command with
`--enumerator hci1:passive -o /tmp/survey_dual.json` ran past listen
(`listen=60s`, phase `enum`, 22 LE, `enumerated_ok=6 attempted=20`) then
**SIGABRT 134** (`malloc(): unaligned tcache chunk detected`) on the
enumerator worker. Python `finally` did not run: JSON was not rewritten
(`/tmp/survey_dual.json` stayed a prior 2026-09-04 file), leftover ACL
survived. Immediate `enum-scan --adapter hci1` path-logged correctly but
**skip-connected** `CC:50:E3:B6:BC:A6`. Terminal scrollback was only the
enum tail (`round` frozen at 6, 1 Hz `--live`). `enum_controller` still
GIVE_UPs at attempt 2 while advertising “max 3”. See todo_tracker.

### Enumerator drain budget + `enumerated_by` honesty (2026-09-04)

`--duration` is wall-clock for dual-antenna survey (`deadline = t_start +
duration`). `drain_enumerator` does not start Connect/enum when remaining time
is below 15s (`DRAIN_FLOOR_S`, the `ConnectDevice` wait); those MACs stay out
of `done` so the next harvest round can retry. After a budgeted drain slice
the collectors harvest again while they stay `Discovering=true`. `--live`
prints `enumerated_ok=M attempted=N` (GATT success vs drain attempts).
`enumerated_by` is written to the DB, `DeviceSighting`, and survey JSON **only**
on `EnumerationResult.success`. Survey `finally` disconnects leftover
Connected Device1s on the enumerator adapter. `_LEDevice.connect` and
`enum-scan` log `adapter=hciN path=/org/bluez/hciN/dev_…` (including
skip-connect).

Unit tests: `tests/test_survey_enum.py`, `format_objects` emission,
`disconnect_connected_on_session`. Live accept of the 60s dual command is still
the operator re-run (not claimed here).

### Dual-antenna live gate (2026-09-04)

`bleep survey --collector hci0:le --listen-monitor --enumerator hci1:passive
--duration 60 --live` **ran**: Flags-OR overlay 1 monitor / 7 patterns on
hci0, no bluetoothd restart, 9 unique LE with RSSI, `seen_by=["hci0"]` in
JSON, DB `enumerated_by=hci1` for every drained MAC. GATT succeeded on
BB-184E, Light Orb, both ESP32s, BLECTF, and `23:35:10:A7:40:2C`; failed
(still marked enumerated) on Galaxy Buds, `2D:78:C9:54:45:1D`,
`24:AC:B4:14:2E:70`.

**Not accepted as a complete gate.** Enumerator drain is synchronous and
unbounded: the 60s survey took **224s / 1 harvest round** (`elapsed
224s/60s | enumerated=9`). `enumerated=N` counts drain attempts, not GATT
success. Survey JSON still has no `enumerated_by`. The `enum-scan
AA:BB:CC:DD:EE:FF --adapter hci1` example is a placeholder — it
`not_found`'d; path fidelity for this run is the DB radio split, not that
command. Next work is bounding drain to remaining `--duration`.

### Manufacturer AdvMonitor extras (2026-09-04)

`--listen-manufacturer CID[:HEX]` and `--listen-mfr-string TEXT` (survey) plus
`--manufacturer` / `--mfr-string` (`advertise-monitor start`) match AD type
`0xFF`. Company id is little-endian on the wire (`6` → `0600`); optional `:HEX`
is a payload prefix after the CID; strings memcmp at offset 2 (after the
2-byte CID), not a substring search.

Live: manufacturer-only `advertise-monitor start --manufacturer 0x0006
--manufacturer 0xFFFF:5a33 --mfr-string Z3` Activate'd, 2 unique Found
(`3C:0F:02:E4:F5:F9` ESP32 `5a33`, plus `04:DE:0B:15:BF:8D`). Mixing those
0xFF patterns onto the Flags-OR child `NoReply`-killed software AdvMonitor;
extras therefore register as a **second** `or_patterns` child (2 monitors).
Retry: overlay registered (2 monitors), 6 unique LE, RSSI on all, `advmon_seen`
on all including a Flags-`00` Microsoft CID-6 device (`0F:17:95:85:B9:F2`)
that Flags-OR alone had been leaving harvest-only. Completeness stays harvest.

### Flags-OR overlay PoC (Module A, 2026-09-04)

Default `--listen-monitor` / no-`-p` AdvMonitor is **one** child whose
`or_patterns` are GAP Flags bytes `{00,02,04,05,06,18,1A}`. Live: four of
those (`00,02,04,06`) Activate'd with 6 unique DeviceFound, sampling 255,
no bluetoothd restart. Prefix-covers (62×256 and 8×256) remain withdrawn.
Collectors stay `Discovering=true` while the overlay is registered (same
`keep_listening` path as `--enumerator`). `RegisterMonitor` failure no longer
claims missing `-E` when the daemon `NoReply`d.

### AdvMonitor catch-all must not crash bluetoothd (2026-09-04)

Live `--listen-monitor` registered 62 monitors / 15872 patterns and bluetoothd
disconnected (`NoReply`, service restart). Overlay failure then hit
`NameError: LOG__GENERAL is not defined` in `survey_multi.py` and aborted the
census. Catch-all is now 8 high-yield AD-type monitors (software) or 2
monitors (MSFT, 16 prefixes/type). Overlay `RegisterMonitor` failure is logged
and survey continues on StartDiscovery harvest.

### AdvMonitor catch-all overlay + HW-2 — Phase 4d (2026-09-04)

AdvertisementMonitor is a **filter overlay**, not a census. Empty `or_patterns`
is illegal in BlueZ (Release / 0 events); BLEEP no longer claims “no `-p` =
match all”. `advertise-monitor start` and `scan --monitor` without `-p` inject
a 1-byte prefix covering of **high-yield** AD types (Flags, manufacturer,
names, UUID16, service-data-16, UUID128-complete — 8 monitors on the software
path) so AdvMonitor catches typical adverts without crashing bluetoothd.
Exhaustive 0x01–0x3D covering (62 monitors) is withdrawn: it `NoReply`-killed
bluetoothd on this host. Survey completeness is the
**union** of StartDiscovery Device1 harvest (R1/R2) and `DeviceFound` →
Device1 `GetAll`. Missing Flags is recorded, never a drop.

Same-adapter AdvMonitor + `StartDiscovery` is **allowed** (BlueZ: Found/Lost
fire “no matter if there is an ongoing discovery session”). `STOP_CLEARS`
still applies only to `StopDiscovery`. CLI is `survey --listen-monitor` (not
`--passive`; that remains `--variant passive` StartDiscovery). Debug shell
refuses `--listen-monitor`.

HW-2: `bleep --check-env` probes `AdvertisementMonitorManager1` and
`ConnectDevice` and prints one experimental-mode line + `bluetoothd -E` hint
(detect-only).

MSFT `controller-patterns` hosts get a reduced catch-all (Flags + manufacturer,
16 prefixes/type, 2 monitors) with a loud warning; discovery harvest stays
complete.

### Dual-antenna listen + enumerate — Phase A+B+D (2026-09-03)

Makes collect-on-one-antenna / enumerate-on-another actually work. Device1
objects are now constructed on the requested controller, `--adapter` reaches
AoI / gatt-enum / explore / pair / classic-connect, and `bleep survey
--collector hci0:le --enumerator hci1:passive` keeps collectors in discovery
while a distinct enumerator radio connects (preferring `Adapter1.ConnectDevice`),
optionally pairs, GATT-enumerates with `skip_scan`, and disconnects.

- **Phase A (path fidelity).** `_LEDevice` / `ClassicDevice` take `adapter_name`;
  `find_device_path(mac, adapter=)` filters `/org/bluez/hciN/`; `--then-aoi`
  forwards `--adapter` (enumerator radio if `--enumerator` was set). Debug-shell
  `survey` refuses `--enumerator` the same way it already refuses `--collector`.
- **Phase B (orchestrator).** New `bleep/dbuslayer/enumerator.py` +
  `bleep/modes/survey_enum.py`. Collector sessions refuse `Pair()`. `brute`
  enumerator mode maps to `pokey` (no write-char payload in survey).
- **Phase D (schema v19).** `devices.seen_by` (JSON, union-merged on upsert),
  `devices.enumerated_by`, `adv_reports.adapter` (part of consecutive-identical
  dedup). AoI markdown/text reports print `Enumerated via:` / `Seen by:`.
- **Phase C / HW-2** landed separately as **Phase 4d** (2026-09-04): AdvMonitor
  catch-all overlay (`survey --listen-monitor`) + `--check-env` experimental
  probe. Not a `survey --passive` replacement.

Live gate (two controllers): `enum-scan --adapter hci1` must Connect on **hci1**;
`bleep survey --collector hci0:le --enumerator hci1:passive --duration 60 --live`.
Live 2026-09-04: overlay + enumerator **ran** (DB `enumerated_by=hci1`,
`seen_by=hci0`) but drain overran `--duration` (224s vs 60s). See Unreleased.

### Report readability polish — unified count notation, tables, hexdump ASCII (2026-08-27)

Sweeping readability pass over `db report` output so every count-bearing block
follows one convention and long inventories scan cleanly:

- **Unified `<unique entry> : <count>` notation** across the Reconnaissance
  Analytics section — the OUI breakdown (`Vendor (OUI) : count`, previously
  `OUI xN (vendor: …)`), random address types (per-line `RPA (resolvable) : N`,
  `Static-random : N`, `NRPA (non-resolvable) : N`, previously packed prose), and
  the Advertisement Data groups (primary `**Vendor (0xID)** : N device(s)` with
  unique-payload/common-prefix/decoded/repeated detail demoted to sub-bullets).
  Vulnerability `(×N)` occurrence counts are intentionally left as-is (they signify
  occurrences, not an inventory).
- **Markdown tables by default** for the explodable SDP and OUI inventories
  (aggregate *and* per-device SDP Discovery), with a new **`--report-bullets`**
  flag to render the unified bullet form instead. Threaded through
  `AOIAnalyser.generate_aggregate_report(..., bullets=…)`.
- **Consistent top-N cap** (`_RECON_TOP_N = 50`) on the SDP and OUI inventories
  with a `(full set in the JSON \`recon\` block)` pointer when truncated.
- **Part B polish:** UUID short-forms normalized to lower-case Bluetooth notation
  (`0X1200` → `0x1200`) via the shared `format_uuid_display` conversion helper;
  Advertisement Dissection ASCII now uses the **hexdump convention**
  (non-printable bytes → `.`) via `_ascii_from_hex`, killing replacement-character
  mojibake; empty `## Services` / `## Advertisement Dissection` sections show a
  simple `- None.`; per-device SDP enrichment (flags/protocols/spec-hint/anomalies)
  grouped under a **`Flags & enrichment:`** sub-label distinct from the service
  inventory; thousands separators on large counts. The `Flags & enrichment` block
  now **collapses repeated security flags and SDP anomalies to unique `… : count`
  rows** and renders them as their own tables (`| Security flag | Count |` and
  `| Severity | SDP anomaly | Count |`) — a snapshot-heavy device that previously
  emitted the same flag 600+ times (once per SDP record) is now two rows.
  `--report-bullets` renders these as collapsed bullets instead.

Rendering-only (JSON `recon` block unchanged). New tests in
`tests/test_db_reporting_enhancements.py` (`TestReconRenderMarkdown`) and
`tests/test_aoi_augmentation.py` (hexdump ASCII, None sections, table/bullet SDP
inventory, Flags & enrichment). Docs updated (`cli_usage.md`, `observation_db.md`,
`debug_mode_db.md`, `api_specification.md`).

### Per-device SDP Discovery — aggregate service inventory (2026-08-27)

The per-device `## SDP Discovery` section of the AoI Security Report (both the
markdown and text renderers, shared by `db report` per-device sections and `aoi`
single-device reports) now presents a collapsed **service inventory** instead of
one bullet per stored SDP record. `_analyse_sdp_records()` adds a
`services_inventory` field (via the new `_aggregate_sdp_inventory` helper) that
groups records by `(name, uuid, channel)` with an occurrence `count`, sorted by
descending count — mirroring the DB-9 aggregate SDP inventory but per-device. The
RFCOMM channel is part of the grouping key, so the same service class on different
channels stays distinct, and rows render as `Name (UUID, ch N) : count` under an
`N unique of M records` header. This makes snapshot-heavy devices legible (e.g. a
real device with **899 SDP records** collapses to 42 readable rows, and the RFCOMM
channel disambiguates the three `NearbyShare` instances on channels 14/16/20 that
were previously indistinguishable). `services_found` is retained unchanged for
JSON/back-compat (additive change). New tests in `tests/test_aoi_augmentation.py`;
docs updated (`aoi_security_algorithms.md`, `aoi_mode.md`).

### refresh-refs — wire IEEE OUI + USB-IF updaters (2026-08-27)

`bleep refresh-refs` now also regenerates the two external (non-SIG) registries
that were previously standalone-only: the IEEE OUI vendor database
(`bt_ref/oui.py`, added in DB-9) and the USB-IF ID database (`bt_ref/usb_ids.py`).
Both run on a bare `refresh-refs` and gain their own mutually-exclusive scope
flags **`--oui-only`** and **`--usb-only`** (alongside the existing `--sig-only` /
`--vendor-only`). Each is an independent, network-best-effort step: a failure is
reported but never blocks the others, and a failed fetch leaves the committed
module untouched (`update_oui`/`update_usb_ids` never overwrite with empty data),
preserving the "a refresh never zeroes a table" invariant. New
`update_oui.regenerate()` / `update_usb_ids.regenerate()` wrappers adapt the
bool-returning generators to the shared `regenerate()` convention (raise on
failure). Docs (`api_specification.md` §3.5.3, `uuid_translation.md`,
`cli_usage.md`, `observation_db.md`) and `tests/test_refresh_refs.py` updated
(17 tests, all green).

### DB-9 — Reconnaissance Analytics (`db report --recon`) (2026-08-26)

Adds an opt-in top-level `## Reconnaissance Analytics` section to `db report`,
aggregating three views across the windowed/filtered selection:

- **SDP inventory** — every unique `(name, uuid)` service item with a per-device
  count (`Name (UUID) : count`), sorted by prevalence, via a single batched
  `get_sdp_inventory(macs)` query (no N per-device detail loads).
- **OUI / address-type breakdown** — public addresses tallied by 24-bit OUI and
  **IEEE-vendor-decoded** (graceful "vendor unknown"); random addresses
  sub-classified into RPA (resolvable) / static-random / NRPA and explicitly *not*
  vendor-decoded (their OUI is a privacy address, not a manufacturer).
- **Advertisement hex analysis** — manufacturer data (grouped by company id),
  service data (grouped by UUID) and advertising-data AD structures, each with a
  unique-payload tally, longest-common-byte-prefix ("pattern"), decoded
  representative, and a **repeated-payload flag** (identical payload across ≥2
  devices → possible static/identity leak, also surfaced on the terminal). Reuses
  the existing `dissect_persisted_record` decoder shared with `db show`.

`--recon-detail` implies `--recon` and additionally folds in characteristic-value
hex (grouped by characteristic UUID, decoded via `decode_characteristic_value`) via
a batched `get_characteristic_values(macs)` query. The whole feature is flag-gated,
read-only, and additive (JSON `recon` sibling block; markdown/text section append).

New IEEE OUI reference module `bleep/bt_ref/oui.py` (~40k MA-L OUIs) plus its
`bleep/bt_ref/update_oui.py` updater, following the existing `bt_ref`
updater+generated-module pattern (`usb_ids.py`). Resolver `resolve_oui()` added to
`bleep/ble_ops/common/conversion.py` (cached, never raises → graceful unknown).
Only 24-bit MA-L blocks are decoded; MA-M/MA-S (28/36-bit shared prefixes) return
`None` rather than misattributing a vendor. 11 new tests (57 total in the DB suite).

### DB-8 — Device-name audit (`db list/report --name-audit`) (2026-08-26)

Classifies device names in the windowed/filtered selection into four buckets so an
operator can pull the *real* observed names out of the sea of MAC-derived default
aliases, and flags any name that looks like a MAC but is not the device's own.

- **New `classify_name(name, mac)` (`analysis/identity.py`):** returns
  `placeholder` (MAC-shaped ∧ normalises to own MAC — BlueZ default alias), `real`
  (genuine name), `empty` (NULL/blank), or `foreign_mac` (MAC-shaped ∧ normalises to
  a **different** MAC — anomaly). Normalisation strips `:`/`-`/`_` and case, so the
  dash-separated alias matches the colon-separated `mac` column. Anchored MAC regex —
  an *embedded* MAC substring stays a `real` name. Also exports `is_mac_shaped`,
  `normalize_mac`, `NAME_CLASSES`.
- **`--name-audit` on `db list` and `db report`:** emits per-bucket counts; **full
  detail** for `empty` and `foreign_mac` rows; the **complete collected record** per
  `real`-named device (grouped by name) via the DB-5 uncapped `export_device_data`
  plus a compact advertisement/GATT/SDP `summary` (reusing `db show`'s
  `adv_dissection`); and a `--name-sample` (default 10) sample of the `placeholder`
  set. `--name-detail-limit` (default 50; `0`=all) caps how many real names are
  expanded with full records.
- **Anomaly awareness:** any `foreign_mac` device is always surfaced — an
  `[!] ANOMALY` banner on the terminal and a `name_audit.foreign_mac` list / report
  **Anomalies** section in structured output.
- **Report integration:** `db report --name-audit` appends a `## Name Audit` section
  to markdown/text reports and attaches a `name_audit` block to `--json` output
  (mirrors the `--identity-contrast` pattern). Read-only; no extra query for bucketing.
- **Tests:** `tests/test_db_reporting_enhancements.py` — `classify_name` units
  (dash/colon/underscore, case, foreign, embedded, empty) + `db list`/`db report`
  `--name-audit` integration over a seeded one-of-each-bucket DB (14 new; 35 total).
- **Docs:** `observation_db.md` (Name audit subsection), `cli_usage.md` (list/report
  rows), `debug_mode_db.md` (CLI-integration example + flag reference), `todo_tracker.md`.

### DB examination / analysis / reporting enhancements (DB-1…DB-7) (2026-08-23)

Adds first-class collection-date windowing, batch reporting, target-list export,
heuristic identity collapse, and export uncapping to the `db` surface — all
additive and reusing existing engines (no new persistence, no schema change).

- **DB-6 — `local_date_range_to_utc()` (`core/time_utils.py`):** converts a local
  `--since`/`--until` date range (with optional `--tz`) into naive-UTC ISO bounds
  matching the DB's timestamp convention; `--until` is treated as **exclusive**
  (whole-day inclusive when a bare date is given).
- **DB-1 — `get_devices(..., since, until, seen_basis)`:** window filtering against
  `seen_basis` = `first` (first_seen), `last` (last_seen, default) or `any`
  (overlap). Purely additive kwargs; existing callers unchanged.
- **DB-5 — `export_device_data(mac, char_limit=500, adv_limit=100)`:** caps are now
  parameters; `0` returns the **unbounded** `characteristic_history` / `adv_reports`
  set. Surfaced via `db export --max-history/--max-adv`.
- **DB-4 — heuristic identity collapse (`analysis/identity.py`):** groups
  RPA-rotating rows by stable advertisement attributes (`name`, `name_mfr`,
  `payload`) reusing `adv_dissect.dissect_advertisement`. **Read-only, opt-in, and
  honest** — carries `method="heuristic"`, `irk_resolved=False`, and always reports
  `raw_count` vs `collapsed_count` so the non-collapsed view is preserved for
  contrast (the delta is itself the signal).
- **DB-2/DB-3 — `db report` + `--export-targets`:** new `db report` action reuses
  `AOIAnalyser.generate_aggregate_report()` over any window (advert-only devices are
  analyzed on the fly and categorized "not reachable"); `db list --export-targets`
  writes an AoI-ingestable target list. Reports cap at 500 devices unless
  `--all-in-window` is passed.
- **New `db list`/`db report` flags:** `--since`, `--until`, `--seen-basis`, `--tz`,
  `--export-targets`, `--group-identity`, `--identity-contrast`, `--all-in-window`,
  `--report-format`, `--max-history`, `--max-adv`. Parser logic consolidated into
  `bleep.cli.parsers.db._add_db_arguments` for CLI/standalone parity.
- **Tests/Docs:** `tests/test_db_reporting_enhancements.py` (21 tests) plus updated
  `tests/test_data_pipeline_fixes.py`; docs in `observation_db.md`, `cli_usage.md`,
  `debug_mode_db.md`, `api_specification.md`, `todo_tracker.md`.

### F5b/F5c — Wire `enum-scan --adapter` and `classic-scan --adapter` (2026-08-13)

Completes F5: the remaining two commands that parsed `--adapter` but ignored it
now honor the selected controller.

- **F5b (`enum-scan`):** `adapter_name` threaded (keyword-only) through the LE
  connect/enumerate spine — `EnumerationController(adapter_name=…)` →
  `connect_and_enumerate__bluetooth__low_energy(adapter_name=…)` for `passive`,
  and → `naggy_enum`/`pokey_enum`/`brute_enum` → `_base_enum` → same connect
  primitive for the variant modes. The connect primitive constructs
  `_Adapter(adapter_name)` (else default) at PRE-FLIGHT 0. `enum_scan.run`
  validates via `require_adapter(args.adapter)` up-front (non-zero exit, no
  silent fallback).
- **F5c (`classic-scan`):** `classic_scan.run` builds `_Adapter(args.adapter)`
  (else default) for the BR/EDR inquiry; not-ready surfaces the adapter name.
- **Additive/back-compat:** every new parameter defaults to `None` → default
  controller (`ADAPTER_NAME`), so existing callers (`aoi`, `user`,
  `connect_with_monitoring`, `scan_modes`) are unchanged. Default parser value
  `hci0` keeps single-adapter hosts identical.
- **Tests:** `tests/test_enum_controller_sr_n3.py` (passive + naggy variant
  adapter forwarding, default `None`); `tests/test_m7_partial_closure.py`
  (classic-scan selects requested adapter / not-ready fails).
- **Docs:** `ble_scan_modes.md`; plan `SCAN_ADAPTER_F5_PLAN.md` status.

### F5 — Wire `scan --adapter` (+ pokey/brute `--transport`) (2026-08-13)

`bleep scan --adapter hciN` previously parsed but was **ignored** — LE discovery
always used the default controller (`dispatch.py` never forwarded `args.adapter`;
`_native_scan` hardcoded `_Adapter()`). Now all four variants honor it.

- **Threading:** `adapter_name` added (keyword-only) to `_native_scan`,
  `passive_scan`, `naggy_scan`, `pokey_scan`, `brute_scan`. `pokey_scan` /
  `brute_scan` also fixed to forward `transport` (pre-existing sibling defect:
  `scan --variant pokey/brute --transport le` silently ignored `--transport`).
  pokey threads adapter+transport into every inner naggy round; brute runs both
  BR/EDR and LE phases on the selected adapter (transport intrinsic).
- **Validation:** `dispatch.py` scan branch validates via
  `core.preflight.require_adapter(args.adapter)` before scanning — a
  missing/not-ready controller fails with a non-zero exit and **no silent
  fallback** to the default. `require_adapter` now names the adapter in its
  diagnostic.
- **Default unchanged:** parser default `hci0` == `ADAPTER_NAME`, so
  single-adapter hosts behave exactly as before.
- **Scope:** F5a only (`scan`). `enum-scan` (F5b) and `classic-scan` (F5c) were
  landed as follow-ons — see the "F5b/F5c" entry above.
- **Tests:** `tests/test_scan_variants.py` (variant threading),
  `tests/test_scan_cli_adapter.py` (CLI thread + readiness gate + default).
- **Docs:** `ble_scan_modes.md`; plan `SCAN_ADAPTER_F5_PLAN.md` status.

### R1/R2 — Pre-stop harvest + session census for non-connectable beacons (2026-08-13)

Fixes BlueZ `STOP_CLEARS`: unpaired non-connectable `Device1` objects (classic
iBeacon/Eddystone) are removed immediately on `StopDiscovery`, so post-stop
`GetManagedObjects` reads never saw them.

- **R1:** `DeviceManager._timeout` snapshots via `_compose_harvest()` **before**
  `StopDiscovery`; `_native_scan` / `create_and_return__*` consume
  `take_last_harvest()`; `AdapterSession.harvest` uses
  `snapshot_discovered_devices()` while Discovering is still true. Shared
  mapper: `build_discovered_device_dict`.
- **R2:** Per-session `_session_devices` census from `InterfacesAdded` /
  `PropertiesChanged` (last-shot mfr/sd); `InterfacesRemoved` marks removed but
  **keeps** the row until the next `start_discovery`. Harvest merges GMO + census
  by MAC. Session capture outlives Discovering until `take_last_harvest`.
- **Tests:** `tests/test_discovery_harvest.py`; stubs updated in
  `test_survey_multi` / `test_discovery_error_surfacing`.
- **Docs:** `ble_scan_modes.md`, `survey_mode.md`, `beacon_identification.md`;
  plan status in `BEACON_DISCOVERY_R1_R2_PLAN.md`.
- **Operator note:** For nameless classic beacons prefer
  `beacon-identification --oui …` without `--name '*Beacon*'`.
- **Live confirmed (2026-08-13):** `beacon-identification` and multi-round naggy
  harvests identify rotating classic beacons (`10:20:BA:46:AE:D5`) across both
  Apple iBeacon (`0x004C`) and Eddystone-URL phases (~90s rotation).
- **iBeacon LE transport:** Classic non-connectable iBeacons require an LE
  discovery filter (`Transport=le`, or survey/scan LE path). They are not
  visible on BR/EDR-only inquiry; use `--transport le` / LE survey rounds /
  `scan --variant naggy` (LE). Default `scan` without an explicit Classic-only
  transport is fine when the manager filter is LE; do not expect iBeacons from
  Classic-only collectors.

### Beacon identification plan v1.3.1 — Phase 0 through Phase 3 core (2026-08-12)

Implements `BEACON_IDENTIFICATION_PLAN.md` (reuse-first):

- **S0a+:** `DeviceManager.start_discovery` merges Transport/DuplicateData/Pattern/RSSI/Pathloss in one `SetDiscoveryFilter`; scan/naggy/pokey/connect/scan_modes no longer pre-set partial filters. Naggy uses `DuplicateData=true`; pokey uses colonized `Pattern`.
- **S0b+:** Survey `DeviceSighting` tracks per-round `payload_history` + signatures; format rotation (compact mfr → FEAA svc) sets `fingerprint_changed`.
- **S2/S3/S7:** `ibeacon_compact` (`0xFFFF` only), `eddystone_pending`, shared `format_beacon_summary`; classifier includes `ibeacon_compact`.
- **S1:** `bleep beacon-identification` thin survey wrapper with deterministic scoring + CDU registry row.
- **S4:** survey `--variant {passive,naggy}` and `--full-payloads`.
- **S5/S6:** docs/help corrected (`ble_scan_modes.md`, debug `scann`).
- **S10:** Espressif UUIDs in `constants.UUID_NAMES`.
- **S11:** `db show` prefers latest `adv_reports.decoded` multi-key dissection.
- **S8:** `adv_monitor.md` / monitor usage strings synced to `advertise-monitor`.
- **S9:** still deferred (no Android fixture).

### Hardware-swap gap analysis — Realtek RTL8761B/BU antenna: HW-1 + HW-4 (2026-08-11)

Work arising from swapping in a Realtek RTL8761B/BU controller (HCI/LMP 5.1, dual-mode).
Full analysis and remaining items live in `docs/todo_tracker.md` (HW-1…HW-6).

- **HW-1 — `media_stream.py` no longer hardcodes `/org/bluez/hci0`.** `MediaStreamManager`
  built the A2DP/AVRCP device path with a literal `hci0`, so `_cycle_device_connection()`
  operated on the wrong object on multi-adapter hosts or when the controller enumerates as
  non-`hci0`. Fix (Option A — resolve from live BlueZ data):
  - New module-level `_device_base_from_path()` (shared base-extraction helper, also reused by
    `_collect_media_objects()` — DRY) and `_first_adapter_name()` (lazy-imports
    `system_dbus__bluez_adapter.list_adapters()` to avoid an import cycle).
  - New `MediaStreamManager._resolve_device_path()` reads the live `.../dev_<MAC>` path from
    `GetManagedObjects()`.
  - `_device_path()` now returns the resolved path, falling back to the first enumerated
    adapter (never a literal `hci0`) only when the device is absent. No new constructor params;
    caller unchanged.
  - Tests: `tests/test_media_helpers.py` +6 (helper, non-`hci0` resolution, first-adapter
    fallback, `hci0`-only-when-no-adapters, absent→`None`, failing `GetManagedObjects()`→`None`);
    existing `_cycle_device_connection` tests made hermetic. Full media/audio/preflight/
    api-surface run green.
  - Live-verified on `hci0` against a real A2DP sink (DS220 `53:4A:52:FE:01:38`): resolver +
    `_device_path()` + `_collect_media_objects()` all returned the live path; the changed caller
    `_cycle_device_connection()` executed a real `Disconnect()`→`Connect()` with no exception.
- **HW-4 — safe, privilege-aware `btmgmt` preflight probe** (`bleep/core/preflight.py`).
  `btmgmt` blocks indefinitely on the kernel mgmt socket without `CAP_NET_ADMIN` and drops into
  an interactive REPL on stdin. Added `BtmgmtStatus` + `run_btmgmt()`/`check_btmgmt()` that use
  `btmgmt --version` as a socket-free runnable probe, `stdin=DEVNULL` + `--timeout` + a hard
  subprocess timeout to prevent hangs, and skip the controller query when unprivileged.
  `_check_bluetooth_tools`/`print_preflight_summary` now surface the privilege-aware status.
  Tests: `tests/test_preflight.py` +8 (`TestRunBtmgmt`, `TestCheckBtmgmt`).
- **Live media validation (DS220 A2DP sink).** Confirmed BLEEP's transport-observation and
  control paths against real hardware: `MediaTransport`/`get_transport_info()` read the live
  `active` SBC transport (config `11150235` = 48 kHz/JointStereo/16-block/8-subband/Loudness/
  bitpool 2–53); `MediaControl1` passthrough + absolute-volume round-trip via
  `MediaStreamManager.set_volume()` (84→40→110→84) all succeeded. BLEEP endpoint-registration
  mode correctly **lost the AVDTP selection race** to a running `bluealsad --all-codecs`
  (alongside PulseAudio/PipeWire) and emitted accurate contention diagnostics — a live
  confirmation of the HW-2 endpoint-contention item (no code change).

### QA: consolidated triple-pass review of OBEX-D2 + ERR-D3 (2026-07-30)

Combined fidelity/no-regression gate over the two error-convention sweeps below. **Result:
clean — no gaps, issues, or detrimental effects.** Pass 1 (correctness) re-read the full diff
of all 20 changed source files: every `RuntimeError` conversion is Convention-aligned, no
orphaned locals, docstrings current. Pass 2 (integration) verified referenced
symbols/signatures (`get_message` `folder=` kwarg both layers; `detect_opp/ftp/map_service`;
`build_svc_map`; `list_mas_instances`); confirmed **only 3** `except RuntimeError` handlers
exist repo-wide and all are coordinated; and confirmed the remaining `raise RuntimeError`
sites are **exactly** the deferred/excluded scope (`agent_io`, `update_usb_ids`,
`custom_uuids`) — no over-reach. Pass 3 (runtime): all 20 modules import clean, all
`bleep.core.errors` classes + `RESULT_*` constants resolve, **96 passed / 14 skipped**
targeted suites, **0 lint errors**. Scope note: this QA pass covered only the error-convention
sweeps (OBEX-D2 + ERR-D3). The LR-2c / dedup changes (`manager.py`, `signals.py`,
`adapter_session.py`, `_history.py`, `survey.py`, the `scan.py` LR-2c hunk, and
survey/observation tests) were reviewed and validated separately under their own **LR-2c**
entry below; all of the above shipped together in the same commit.

### ERR-D3: codebase-wide `RuntimeError` → `BLEEPError` convergence (2026-07-30)

Accepted 2026-07-30 (Tier 1 + Tier 2 + the `error_map` Tier-3 component; `agent_io`
deferred; `update_usb_ids.py`/`custom_uuids.py` excluded). Converges the remaining runtime
`RuntimeError` raises onto the Convention-aligned `bleep.core.errors` framework. A repo-wide
scan first proved the entire blast radius: only **three** `except RuntimeError` handlers
exist in `bleep/`, all updated here.

- **Tier 1 — self-contained** (callers catch broad `Exception`; no type-specific catchers):
  - `dbuslayer/obex_pbap.py` (7): closes the OBEX-D2 deferral — obexd-not-running →
    `BLEEPError(WRONG_STATE)`; both `CreateSession` sites → shared `obex_session_error`
    (`profile="PBAP"`); `Too short header` PullAll → `BLEEPError(WRONG_STATE)` (keeps the
    power-cycle guidance); generic PullAll → `map_dbus_error`; missing-`Filename`/file →
    `BLEEPError(RESULT_ERR)`.
  - `ble_ops/le/scan.py` (4) + `ble_ops/le/enum_helpers.py` (1): native-stack guards →
    `NotSupportedError`.
  - `ble_ops/classic/spp.py` (1) + `dbuslayer/spp_profile.py` (3): already-registered →
    `OperationInProgressError`; no-GLib → `NotSupportedError`; `RegisterProfile` DBus →
    `map_dbus_error`.
  - `ble_ops/classic/rfcomm.py` (2): `rfcomm` bind/release failures → `BLEEPError(RESULT_ERR)`.
- **Tier 2 — coordinated** (`ble_ops/classic/sdp.py`, 7): `_ensure_sdptool` missing →
  `NotSupportedError`; device unreachable → `ConnectionError`; empty SDP results →
  `BLEEPError(RESULT_ERR_NOT_FOUND)`; sdptool exit error → `BLEEPError(RESULT_ERR)`. Companion
  handler updates shipped together: `sdp.py` `_ensure_sdptool` catchers (×2) →
  `except (RuntimeError, NotSupportedError)`; `modes/debug_classic.py` connectionless catcher
  → `except (RuntimeError, BLEEPError)` (its `"not reachable"` string-match still fires against
  `ConnectionError`). `discover_services_sdp` docstring updated.
- **Tier 3 — `error_map.py` only** (3): `_reconnect_device` failure → `ConnectionError`;
  `_resolve_services` failure → `ServicesNotResolvedError` (aliased local imports to avoid the
  `bt_ref.exceptions import *` name collision; best-effort address via `getattr`).
- **Deferred / excluded (unchanged).** `dbuslayer/agent_io.py` (5) — exceptions cross the
  BlueZ D-Bus **agent boundary** and drive brute-force control flow; deferred pending dedicated
  pairing validation. `bt_ref/update_usb_ids.py` (dev script) and `bt_ref/custom_uuids.py`
  excluded per scope.
- **Validation.** All touched modules import clean; **no lint errors**; targeted suites green
  (**24 passed / 15 skipped** classic; **183 passed / 6 skipped** for sdp/scan/error_map/
  rfcomm/pbap/spp incl. `test_bt_ref_error_map`, `test_scan_variants`,
  `test_discovery_error_surfacing`, `test_rfcomm_enomem`). Behavioral: `_ensure_sdptool`
  absence still yields `None` from `discover_service_channel`; `ConnectionError` message still
  contains `"not reachable"`. Live (OnePlus 15R): `classic-enum` (22 SDP records + RFCOMM
  channels) and `classic-scan` regression-free.

### OBEX-D2: OPP/FTP/SYNC/BIP error-type convention alignment (2026-07-30)

Accepted 2026-07-30 (BIP via shared mapper + optional OPP/FTP CLI pre-flight). Completes
the OBEX-layer consistency sweep deferred in MAP-D1 — the four remaining profiles now use
the same shared `obex_session_error` mapper and `BLEEPError` convention as PBAP/MAP.
Diagnostics-and-error-type only; no change to control flow, session lifecycle, or any
successful transfer.

- **Shared mapper reuse** (`bleep/dbuslayer/{obex_opp,obex_ftp,obex_sync,obex_bip}.py`).
  Every `CreateSession` `DBusException` now routes through `obex_session_error(exc, mac,
  profile=…, service_hint=…)` (OPP `0x1105`, OBEX-FTP `0x1106`, IrMC Sync `0x1104`, BIP
  `0x111A/0x111B`) — identical curated messages/codes to PBAP/MAP, zero re-implementation.
- **`_SHARE_FEATURE` extended + BIP `_EXTRA_HINT`** (`bleep/dbuslayer/_obex_common.py`).
  Added `SYNC`/`BIP` sharing-feature strings. BIP's `Image1` is `[experimental]`; the
  mapper's unknown-variant branch now appends a `--experimental` hint for `profile="BIP"`
  so that guidance survives while BIP still uses the shared path (chosen option).
- **`RuntimeError` → Convention-aligned errors** across all four layers: obexd-not-running
  → `BLEEPError(RESULT_ERR_WRONG_STATE)`; per-method D-Bus wraps (ChangeFolder, ListFolder,
  GetFile/PutFile, SendFile, Properties, Get/GetThumbnail, SetLocation, Get/PutPhonebook,
  Copy/Move/Delete) → canonical `map_dbus_error(exc)`; OPP logic failures (no vCard / no
  file written) → `BLEEPError(RESULT_ERR)`; OPP `ExchangeBusinessCards` "not implemented"
  and BIP `Image1`-unavailable → `NotSupportedError`.
- **Shared transfer poller** (`bleep/dbuslayer/_obex_common.poll_obex_transfer`). Timeout
  → `TimeoutError`, non-`complete` status → `BLEEPError(RESULT_ERR)` (previously bare
  `RuntimeError`). Benefits **all six** OBEX profiles including the already-validated
  PBAP/MAP; regression-checked below.
- **CLI parity** (`bleep/modes/classic_profiles.py`). New shared `_warn_if_not_advertised`
  helper adds a non-fatal SDP pre-flight to `run_opp`/`run_ftp` (mirrors `run_map`), warning
  when OPP/FTP is absent from the target's service map before attempting anyway.
- **Docstrings** updated (`Raises RuntimeError` → `BLEEPError`) in the four D-Bus layers,
  the OPP `ble_ops` wrapper, and `poll_obex_transfer`; BIP module warning now cites
  `NotSupportedError`.
- **Docs.** Added `bl_classic_mode.md` §4 rows: OPP/FTP not-advertised pre-flight, the
  shared "service record not retrievable" CreateSession error, and the BIP `--experimental`
  `NotSupportedError`.
- **Deferred at the time (since closed).** `bleep/dbuslayer/obex_pbap.py` was left with its
  7 `RuntimeError` sites here to honour the OPP/FTP/SYNC/BIP scope. That deferral was
  **subsequently closed by ERR-D3** (see the ERR-D3 entry above), which converted all 7 to
  `BLEEPError`/`obex_session_error`/`map_dbus_error`; `obex_pbap.py` no longer raises
  `RuntimeError`. `bleep-mcp/` untouched.

### MAP-D1: shared OBEX CreateSession error mapper + MAP error-type convention alignment (2026-07-30)

Accepted 2026-07-30 (recommended DRY option; MAP+PBAP scope). Consolidates the
OBEX session-time diagnostics into one reusable helper and brings MAP up to the same
Convention-aligned, actionable standard as PBAP. No behavioural change to successful
transfers.

- **Shared mapper** (`bleep/dbuslayer/_obex_common.py`). New `obex_session_error(exc,
  mac, *, profile, service_hint)` maps an obexd `CreateSession` `DBusException` to a
  Convention-aligned `BLEEPError` with a curated, profile-aware message + `RESULT_ERR_*`
  code for the shared failure modes (`Too short header` → `WRONG_STATE`, `Transport got
  disconnected` → `NOT_CONNECTED`, `NoReply`/`Timed out` → `NO_REPLY`, `Unable to find
  service record` → `UNKNOWN_SERVCE`); unknown variants delegate to the canonical
  `map_dbus_error` (which already handles `NotAuthorized`/`NotReady`/etc.).
- **PBAP de-duplicated** (`bleep/ble_ops/classic/pbap.py`). `pbap_dump_async`'s inline
  CreateSession branches (added in PBAP-D1 above) are replaced by a single call to the
  shared mapper — identical messages/codes, less code.
- **MAP aligned** (`bleep/dbuslayer/obex_map.py`). `MapSession` CreateSession now raises
  via the shared mapper (previously a bare `RuntimeError` with no guidance — e.g. the
  OnePlus 15R `Timed out waiting for response` = unauthorised MAS). obexd-not-running and
  notification-watch paths now raise `BLEEPError` / `NotSupportedError` /
  `OperationInProgressError` instead of `RuntimeError`.
- **MAP monitor** (`bleep/ble_ops/classic/map.py`). "Monitor already active" now raises
  `OperationInProgressError`.
- **CLI parity** (`bleep/modes/classic_profiles.py`). `run_map` gains a non-fatal
  `list_mas_instances` pre-flight that warns when MAP is not advertised in SDP, matching
  the interactive layer's `detect_map_service` guard.
- **`Unable to find service record` message honesty (from live validation).** The mapper
  branch no longer asserts the record *is* advertised (only true for the honeypot/transient
  case). It now presents both possibilities — target does not support the profile **or**
  advertised-but-transient SDP failure — since the mapper cannot know which. Surfaced by
  running the MAP failure path against PhreakMe-Blue (no MAP advertised).
- **MAP `get --folder` fix (defect found in live validation)** (`bleep/cli/parsers/
  classic.py`, `bleep/modes/classic_profiles.py`). CLI `classic-map … get` previously had
  no way to specify the message's folder, so `get_message` could not materialise the
  `Message1` object and failed with `UnknownObject … Message1 "Get"`. Added `--folder`
  (mirrors `ftp get --path`) and wired it through. MAP `get` now works end-to-end.
- **Docs.** Fixed the stale "no multi-instance MAP" note in `obex_map.py`; added MAP
  troubleshooting rows to `bl_classic_mode.md` §4 (unauthorised MAS / MAP not advertised).
- **Live validation (OnePlus 15R `78:ED:BC:23:67:96`, attended).** Success path confirmed:
  `instances` (SMS/MMS ch26), `folders` (full telecom/msg tree), `list` (real inbox MMS),
  `types` (graceful "none" on BlueZ 5.64), `fields`, and `get` (1182-byte bMessage after
  the `--folder` fix). Failure path confirmed on PhreakMe-Blue (pre-flight warning +
  honest `BLEEPError`). `push`/`monitor` not exercised (write/long-running; avoided on a
  live personal handset).
- **Unchanged.** `OPP/FTP/SYNC/BIP` CreateSession error handling (deferred consistency
  sweep), `pan.py`, `bleep-mcp/`.

### PBAP-D1: actionable diagnostic for obexd `Unable to find service record` + PBAP error-type convention alignment (2026-07-30)

Accepted 2026-07-30 (full-consistency option) after a live preliminary scan on the
PhreakMe-Blue honeypot (`14:89:FD:31:8A:7E`). Documentation-and-diagnostics only — no
behavioural change to any working PBAP transfer.

- **Root cause (evidence-based, not a BLEEP defect).** `classic-enum --sdp-source
  merge --analyze` and `sdptool search 0x112F` both find the PBAP PSE record
  (`browse+xml+records`, ch18) yet obexd's session-time SDP ServiceSearch
  intermittently fails. Across live attempts the failure was **non-deterministic**,
  cycling between `Too short header in packet`, `Unable to find service record`, and
  `Timed out waiting for response` (obexd log: `connect_cb: Timed out` + `Transport got
  disconnected`) — never reaching the authorisation stage, so no on-device prompt
  appears.
- **Confirmed cause-and-fix (attended live validation, 2026-07-30).** The repeated
  failed OBEX attempts wedge the *Target Device's* OBEX stack. **Restarting the Target
  Device clears its buffers and fully restores PBAP** — validated live: immediately
  after a device restart the dump succeeded, pulling **313 vCard lines** from
  PhreakMe-Blue. Depending on the device implementation a power-cycle may be required
  rather than a `bluetoothctl disconnect`; users should be aware the Target Device may
  need restarting. PBAP is therefore *serviceable* on this target — the failures were
  accumulated device-side stale state, not a permanent refusal.
- **Diagnostic gap closed** (`bleep/ble_ops/classic/pbap.py`). `pbap_dump_async` now
  has an actionable branch for `Unable to find service record` (previously fell through
  to a bare `raise`, surfacing as a cryptic `org.bluez.obex.Error.Failed: …` with no
  guidance). The new message states the record *is* advertised, that the failure is
  transient, and to accept any on-device prompt then retry / reconnect.
- **Error-type convention alignment** (`bleep/ble_ops/classic/pbap.py`). All PBAP
  `CreateSession` failure paths (`Too short header`, `Transport got disconnected`,
  `NoReply`/`Timed out`, the new `Unable to find service record`) plus the
  `dump_phonebook_pbap` fallback now raise the Convention-aligned
  `bleep.core.errors.BLEEPError` (with mapped `RESULT_ERR_*` codes) instead of bare
  `RuntimeError`. Callers already catch broad `Exception`, so surfaced messages are
  unchanged.
- **Docs.** New `bl_classic_mode.md` §4 troubleshooting row for `Unable to find
  service record` (device-side, on-device-prompt guidance, non-deterministic posture).
- **Unchanged.** `obex_map.py`, `map.py` (MAP already pre-flights via
  `detect_map_service` in the command layers), `pan.py`, the sync `obex_pbap.py`
  transport, and `bleep-mcp/` (out of scope).

### LR-2c: signal-fed intra-round advertisement-fingerprint rotation detection (2026-07-30)

Additive enhancement (accepted 2026-07-30; re-grafted 2026-07-30 onto the pulled
multi-adapter D1/D2 baseline). Detects same-length advertisement payload rotations
that occur **and revert within a single survey round** — invisible to the end-of-round
`GetManagedObjects()` snapshot that both the census and `adv_reports` consume (the
residual limitation flagged when LR-2b was retracted). The mechanism mirrors LR-6's
RSSI capture: the per-advertisement D-Bus signal stream is the only sub-round source.
Default (no-signal) behaviour and `adv_reports` semantics are unchanged; the new
detection can only *set* `fingerprint_changed`, never clear it.

- **Phase 0 feasibility gate (passed).** A throwaway probe subscribed to
  `PropertiesChanged`/`InterfacesAdded` for the Light Orb (`F0:98:7D:0A:05:07`) under
  realistic survey conditions (`DuplicateData=True`): BlueZ delivered `ServiceData` in
  **252/252** `PropertiesChanged` events over 90s — it does **not** coalesce
  `ServiceData`/`ManufacturerData` the way it partly does for RSSI, so a rotation is
  observable on the signal stream. (No `bleep/` code involved in the probe.)
- **DeviceManager tracker** (`bleep/dbuslayer/manager.py`). New per-round
  `_adv_fp_last` (MAC → {(kind,key): payload}) + `_adv_fp_rotated` set under a
  dedicated lock; reset in `start_discovery` alongside the RSSI cache. State is
  per-manager, so under the multi-adapter model each adapter's manager tracks only its
  own devices. `_capture_adv_fingerprint(mac, kind, key, payload)` flags a rotation on
  `len(new)==len(old) and new!=old` — the exact predicate the per-round census merge
  uses (`_merge_svc_data`/`_merge_mfr_data`); strictly longer/shorter payloads are
  left to the snapshot merge. `pop_fingerprint_rotated(mac)` is a one-shot read+clear.
- **Signal wiring** (`bleep/dbuslayer/signals.py`). New
  `_capture_device_adv_fingerprint(path, props)` next to `_capture_device_rssi`,
  called from `_properties_changed` and `_interfaces_added` when the `Device1`
  interface carries `ServiceData`/`ManufacturerData`. Routed to the owning adapter's
  manager via `_resolve_manager_for_path` (D1 adapter-aware routing), so a rotation
  seen on one antenna never lands in another adapter's tracker. Same
  `is_discovery_active` gating and swallow-all-failures contract as the RSSI path;
  keys normalised to the census's `str` UUID / `int` company-id.
- **Scan surface** (`bleep/ble_ops/le/scan.py`). Each returned entry now carries
  `fingerprint_rotated_in_round = manager.pop_fingerprint_rotated(<path MAC>)`. The pop
  keys off the D-Bus *path* MAC (which the tracker keyed on) so a bonded device seen
  via a resolvable-private address — whose resolved identity `address` differs (N4) —
  is still matched; the census still attributes to the identity-keyed sighting.
- **Multi-adapter (D2) parity** (`bleep/dbuslayer/adapter_session.py`).
  `AdapterSession.harvest()` pops `fingerprint_rotated_in_round` from its own manager
  for each collected device, so `--collector` multi-antenna surveys surface the flag
  identically to the single-adapter `_native_scan` path.
- **Census OR-in** (`bleep/modes/survey.py:_merge_entry`). `if
  entry.get("fingerprint_rotated_in_round"): s.fingerprint_changed = True` — purely
  additive to the existing snapshot-based detection.
- **Tests.** `tests/test_adv_fingerprint_rotation.py` (18) covers the manager tracker
  (same-length flag; identical/longer/shorter/first-sample no-flag; key/MAC isolation;
  manufacturer path; non-bytes ignored; one-shot pop; clear-on-discovery) and the
  signals forwarder (svc/mfr rotation, inactive-discovery gate, no-manager,
  non-device path, missing-accessor swallow, `_interfaces_added` seeding). +3 census
  OR-in tests in `tests/test_survey.py`.

### Review follow-ups: adv dedup key-order hardening, DB semantics docs (2026-07-30)

Post-acceptance follow-ups from the triple-pass review of the LR-1a/1b/2/3/5/6 +
F-1/F-2 batch. Additive and default-path-safe; +1 test. (The USB-IDs `\R` escape fix
from this review batch is already present upstream — hardened independently via a
`_pystr()` helper in `bleep/bt_ref/update_usb_ids.py` — and is therefore not
re-applied here.)

- **`adv_reports` dedup is now key-order independent.** `insert_adv`
  (`bleep/core/observations/_history.py`) compared the incoming `decoded` blob to the
  last stored row by exact string, but `json_dumps` does not sort keys — so two
  structurally-identical payloads serialized in a different key order would emit a
  redundant row. New `_decoded_matches()` keeps the fast exact-string path and adds a
  structural (`json.loads`) fallback; a parse failure persists the row (never drops
  a sample). Stored format is unchanged. +1 test
  (`test_insert_adv_coalesces_regardless_of_decoded_key_order`). Worst prior case was
  a harmless extra row, so this is hardening, not a correctness fix.
- **DB counter/history semantics documented.** `bleep/docs/observation_db.md` gains a
  "Counter & history semantics" section: `adv_reports` is a coalesced change-log
  (RSSI churn is not persisted there; the newest `ts` can lag `last_seen`, so use
  `devices.last_seen` for "last seen"), and `devices.sighting_count` is
  cumulative-across-runs and skips paired/bonded cached re-reads.
- **LR-2 "data-path gap" (LR-2b) investigated and RETRACTED — not a defect.** The
  census round-result and `adv_reports` are built from the **same** per-round
  `GetManagedObjects()` snapshot in `_native_scan`, so the two cannot diverge; the
  earlier claim of a "per-advertisement signal stream feeding `adv_reports`" was
  factually wrong. The residual (real, equal-to-both-sinks) limitation — end-of-round
  snapshot sampling misses a rotation that reverts within one round — was
  subsequently addressed by **LR-2c** (see the LR-2c entry above).

### CLI ↔ Debug Mode capability uniformity — M7/M8/M9 residual-parity, harness hygiene & anti-drift harmonization (2026-07-29)

- **M7 — residual `partial` rows closed to `full` (classic-scan, agent, aoi).**
  - **`classic-scan`.** New shared builder
    `bleep.cli.parsers.classic._add_classic_scan_arguments` (single source for
    `--timeout/--uuid/--rssi/--pathloss/--debug/--adapter`); the CLI subparser now
    consumes it. Debug `cscan` (`bleep/modes/debug_classic.py`) no longer inlines a
    stripped scan — it parses via `parse_as_cli("classic-scan", …)` and delegates
    to the same `classic_scan.run`, gaining the discovery filters **and**
    observation-DB persistence (behavior change: debug `cscan` output is now the CLI
    format).
  - **`agent`.** Debug `agent` keeps its native session verbs
    (`status`/`register`/`unregister`) and gains device-management verbs
    `trust`/`untrust`/`remove-bond <MAC>` and `list-trusted`/`list-bonded`, which
    translate to the CLI flag form and delegate to the shared `bleep.modes.agent.run`
    (one-shot ops that return before the agent loop — `agent.py:279`).
  - **`aoi`.** Debug `aoi` keeps the live `aoi [--save] [MAC]` helper as its default
    and adds a leading-verb gate: a first token in
    `scan/analyze/list/report/export/db` delegates to the same `aoi.run` pipeline via
    `parse_as_cli` + `apply_aoi_subcommand` (a MAC can never equal a subcommand name,
    so no collision).
  - Registry rows `classic-scan`/`agent`/`aoi` `partial → full`; **no `partial` rows
    remain**. New guard `tests/test_m7_partial_closure.py`.
- **M8 — test-harness hygiene.**
  - New `pytest.ini` registers the `pbap` and `timeout` marks (silences 23
    `PytestUnknownMarkWarning`s). `pytest-timeout>=2.3.0` added as a `test` extra in
    `setup.py` so `@pytest.mark.timeout(N)` is honored rather than a no-op.
  - Fixed the `DeprecationWarning` in `bleep/ble_ops/classic/sdp.py` — replaced the
    `seq.find("uint8") or seq.find("uint16") or seq.find("uint32")` chain (which
    relied on the deprecated `Element.__bool__` truth-value) with explicit
    `is None` checks (behavior-preserving).
- **M9 — anti-drift harmonization.** `debug_advmon.cmd_advertise_monitor` now parses
  through `parse_as_cli("advertise-monitor", …)` instead of a hand-built parser;
  `_build_parser` removed. This retires the last bespoke debug parser — every ported
  verb now shares the single `parse_as_cli` seam. `advertise-monitor start` still
  runs under `foreground_loop_handoff`. `tests/test_advertise_monitor_uniformity.py`
  gains assertions that the verb routes through `parse_as_cli` and that
  `_build_parser` is gone.

### CLI ↔ Debug Mode capability uniformity — M6 docs/registry/enforcement reconciliation (2026-07-29)

- **New guard `tests/test_docs_match_registry.py`** — asserts every capability
  with a non-empty `cli_command` is documented in `bleep/docs/cli_usage.md` and
  every capability with a non-empty `debug_command` is documented in
  `bleep/docs/debug_mode.md` (capability-level, code-span parse discipline
  mirroring `test_cli_hint_convention.py`). Completes the docs/registry/test triad.
- **Doc-sweep gaps filled in `debug_mode.md`** — added the previously
  undocumented debug verbs: `crfcomm`/`cbind` (Classic table), a new **Media &
  Audio** table (`mediaenum`/`mediaprops`/`mediactrl`/`audiorecon`/`audioplay`/
  `audiorec`), and `survey`/`survey-status` (BLE Scanning table).
- **New "Methodology & CLI parity" section in `debug_mode.md`** — codifies the two
  surface contracts (one-shot CLI vs. stateful debug REPL), the anti-drift
  mechanism (`shared_impl`, `_add_*_arguments`, `parse_as_cli`,
  `foreground_loop_handoff`), and *why* Class-A (CLI-only) and Class-B
  (debug-only) commands are intentionally single-surface. Module map gains
  `debug_cli_adapters.py` (M3) and `debug_advmon.py` (M2).
- **Hint-convention token list extended** (`tests/test_cli_hint_convention.py`)
  with the debug-unique verbs `cenum`/`netenum`/`cping`/`uuidtr`/`adaptercfg`/
  `gattserver`/`devicesets`. `advertise-monitor` and `mesh` are intentionally
  **omitted** — they are identical to their CLI subcommand names, so a
  CLI-reachable literal citing them is a legitimate self-reference, not a
  cross-surface debug reference.

### CLI ↔ Debug Mode capability uniformity — M5 depth parity (2026-07-29)

- **New debug `cenum` verb** (`bleep/modes/debug_stateful_adapters.py`) — the true
  depth twin of CLI `classic-enum`, delegating to the same `classic_enum.run`
  (`bleep.analysis.sdp_analyzer`) with full `--version-info` / `--analyze` /
  `--sdp-source` / `--connectionless` support; MAC defaults to
  `state.current_device`. The separate `csdp` verb keeps its raw socket-oriented
  SDP-browse semantics unchanged (accepted 2026-07-29 — do **not** overload `csdp`).
- **Debug `audiocfg` gains a write sub-surface** (`bleep/modes/debug_media.py`):
  `audiocfg <show|add|remove|tunnel|backup|restore> [...]` delegates to the same
  `run_audio_config` core the CLI `audio-config` subcommand uses; no-arg /
  `--endpoints` / `--profile` keeps the existing read-only backend diagnostics.
- Both write paths reuse the M3 `parse_as_cli` anti-drift seam, so options can
  never diverge from their CLI twins and argparse errors can't tear down the shell.
- **Registry.** `classic-enum` (`debug=("cenum","csdp")`) and `audio-config` flip
  `partial` → `full`.
- Docs: `debug_mode.md` (BR/EDR Classic + Utilities tables, module map) + in-shell
  `help`. New `tests/test_m5_depth_parity.py`.

### CLI ↔ Debug Mode capability uniformity — M4 stateful-core parity verbs (2026-07-29)

- **Eight connection-aware CLI modes ported into the debug shell** (new
  `bleep/modes/debug_stateful_adapters.py`), each delegating to the same core the
  CLI dispatch calls and parsing tokens through the real CLI subparser
  (`parse_as_cli`, promoted from M3's `_parse_as_cli`):
  - `explore` → `exploration.run`; `audiointercept` → `run_audio_intercept` —
    both default the target MAC to the live `state.current_device` when omitted
    (matching the `chid`/`aoi` conventions).
  - `signal` → `signal.run` — **reuses the live `state.current_device` (no
    reconnect)** via a new additive `signal.run(..., device=...)` parameter; the
    lightweight `notify` toggle is unchanged.
  - `gattserver` → `gatt_server.run`; `advertise` → `advertise.run` — cores that
    run their own foreground GLib loop, so they run inside the new shared
    `foreground_loop_handoff` context manager.
  - `devicesets` → `handle_device_sets`; `mesh` → `handle_mesh`; `ctf` →
    `blectf.run`.
- **New shared `foreground_loop_handoff(state)`** (`bleep/modes/debug_state.py`)
  stops the background debug GLib loop and saves/restores the shell's
  SIGINT/SIGTERM handlers around any core that runs its own foreground loop.
  `debug_advmon` (M2) was refactored onto it, removing its inline duplicate.
- **`refresh-refs` intentionally NOT ported** — stays `cli-only` (batch
  reference-data maintenance, no session value).
- **Registry.** `explore`, `signal`, `gatt-server`, `advertise`,
  `audio-intercept`, `device-sets`, `mesh`, `ctf` flip `cli-only` → `full`.
- Docs: `debug_mode.md` (Enumeration/GATT tables + new "Local Roles, Broadcast &
  Advanced" section) + in-shell `help` groups. New `tests/test_m4_stateful_parity.py`.
- **Verified:** M4 + M3 + M2 + parity/hint guards → `258 passed` (M2 test
  `test_debug_start_delegates_inside_loop_handoff` updated for the shared
  `foreground_loop_handoff` refactor). Full adapter-dependent suite pending a host
  with Bluetooth hardware.

### CLI ↔ Debug Mode capability uniformity — M3 zero-risk utility parity verbs (2026-07-29)

- **Five CLI utilities ported into the debug shell as thin, stateless adapters**
  (new `bleep/modes/debug_cli_adapters.py`), each delegating to the *same* core
  the CLI dispatch calls — no logic duplicated:
  - `uuidtr` → `bleep.modes.uuid_translate.main` (tokens passed straight through).
  - `adaptercfg` → `bleep.modes.adapter_config.handle_adapter_config`.
  - `netenum` → `bleep.modes.classic_profiles.run_network_enum`.
  - `cping` → `bleep.ble_ops.classic.ping.classic_l2ping`.
  - `db` → `bleep.modes.db.run` (full `list/show/timeline/export/uuids/maintain`
    surface; terminal `OutputContext`, no shim needed — `db.run` emits via
    `print_and_log`). Broader than the session-scoped `dbsave`/`dbexport`
    helpers, which are retained.
- **Anti-drift mechanism.** `adaptercfg`/`netenum`/`cping`/`db` parse their
  tokens through the *real* CLI subparser via `build_argument_parser()`
  (`_parse_as_cli`), so a debug verb can never accept a different option set than
  its CLI twin. `SystemExit` from argparse (`--help` / parse errors) is contained
  so it can never tear down the interactive shell (`uuidtr` guards its
  self-parsing `main()` the same way).
- **Registry.** `uuid-translate`, `adapter-config`, `network-enum`,
  `classic-ping` flip `cli-only` → `full`; `db` flips `partial` → `full`
  (`debug_command` = `db`, `dbsave`, `dbexport`; `shared_impl` → `bleep.modes.db.run`).
- Docs: `debug_mode.md` (Classic / Database / new Utilities tables) + in-shell
  `help` groups updated. New `tests/test_m3_utility_parity.py`.
- **Verified:** M3 suite + M2 + parity/hint guards → `227 passed`. Full
  adapter-dependent suite pending a host with Bluetooth hardware.

### CLI ↔ Debug Mode capability uniformity — M2 Advertisement Monitor (2026-07-29)

- **CLI hard rename (no alias).** `bleep monitor` → `bleep advertise-monitor`
  (`caps`/`start`), disambiguating it from the debug device-property `monitor`.
  `bleep/cli/parsers/utility.py` now exposes the shared
  `_add_advertise_monitor_start_arguments` builder consumed by both surfaces;
  the dispatch branch (`bleep/cli/dispatch.py`) matches `advertise-monitor`. The
  sub-action dest stays `monitor_action`, so `bleep.modes.monitor` is untouched.
- **Debug parity (new verb).** New thin adapter `bleep/modes/debug_advmon.py`
  adds the `advertise-monitor` debug verb, delegating to the same
  `bleep.modes.monitor.run` (terminal `OutputContext`). For `start` it hands the
  GLib default context to `monitor`'s own foreground loop (stops/restarts the
  background debug loop) and saves/restores the shell's SIGINT/SIGTERM handlers,
  so Ctrl-C returns cleanly to the prompt. The debug `monitor` (live
  `PropertiesChanged`) verb is unchanged and now documented as distinct.
- **Registry:** `advertisement-monitor` flips `cli-only` → `full`
  (`cli_command`/`debug_command` = `advertise-monitor`, `shared_args` = the new
  builder); the parity guard enforces both surfaces + the removed `monitor`
  subcommand.
- Docs: `cli_usage.md`, `debug_mode.md` (BLE Scanning table + disambiguation
  note), and in-shell `help` updated.
- **Verified:** new `tests/test_advertise_monitor_uniformity.py` + the parity and
  hint-convention guards pass (`207 passed`). Full-suite (adapter-dependent rows)
  pending a host with Bluetooth hardware.

### CLI ↔ Debug Mode capability uniformity — M0 registry + M1 drift fixes (2026-07-29)

First implementation slice of the accepted CLI/Debug uniformity plan
(`bleep/docs/todo_tracker.md` → "CLI ↔ Debug Mode capability uniformity
CDU-M0..M6"). Both surfaces keep their distinct methodologies (one-shot CLI vs.
stateful debug shell); parity is achieved by shared implementations + shared
argument builders, never by duplicating logic.

- **M0 — parity registry + guard.** New `bleep/cli/capability_registry.py`
  declares every capability and the command name(s) it exposes per surface. New
  `tests/test_cli_debug_parity.py` asserts every reachable CLI subcommand and
  every debug dispatch key is declared (and vice-versa: no stale rows), plus
  per-row parity/rationale/shared-impl invariants. `bleep/cli/parsers/__init__.py`
  gains `build_argument_parser()` + `iter_cli_subcommands()` (behaviour-preserving
  refactor; `build_parser()` unchanged).
- **M1 — Class-C option/default drift eliminated.**
  - PBAP `--watchdog` unified via `classic.py::_add_pbap_arguments` (canonical
    default **30 s**; removes the debug shell's 8 s default that aborted long
    phonebook pulls).
  - `pair` options unified via `pairing.py::_add_pair_arguments`; the debug
    shell gains `--no-connect` / `--no-trust`, threaded through the pairing flow.
  - Debug `scan`/`scann`/`scanp`/`scanb` gained an overridable `--timeout`
    (historical 10 s / 20 s defaults preserved).
  - Debug `audioplay` gained `--codec`; debug `audiorec` gained
    `--hfp` / `--keep-profile` (wired to the same shared calls as the CLI).
- **Follow-up fix.** The declarative registry legitimately names debug-shell
  commands (in its command tuples and parity rationale) and emits no user-facing
  output, so `bleep/cli/capability_registry.py` was added to the
  `EXEMPT_PATH_PARTS` allow-list of `tests/test_cli_hint_convention.py`.
- **Verified:** full suite green on a host with a Bluetooth adapter
  (`1837 passed, 34 skipped`); the parity + hint-convention guards pass
  (`196 passed`).

### CLI ↔ Debug Mode capability uniformity — M1.5 PAN rename + M1.6 HID dual-variant (2026-07-29)

- **M1.5 — `classic-pan` vocabulary unified (hard rename).** CLI `serve`/`unserve`
  → `server-reg`/`server-unreg` (no alias). The debug shell's `cpan` gains the
  same `server-reg`/`server-unreg` primary verbs and keeps the one accepted
  two-token alias `server register`/`server unregister`. Both surfaces resolve
  spellings through the new shared `bleep/ble_ops/classic/pan.py::
  PAN_SERVER_VERBS` / `resolve_pan_server_verb`, and the debug register/
  unregister logic is factored into a shared `_cpan_server_action` helper.
- **M1.6 — HID classification available with and without a connection on both
  surfaces.** New shared evidence builder `bleep/ble_ops/hid.py` assembles the
  `classify_hid` evidence dict once for both surfaces. CLI `hid-info` gains
  `--connect` (connected variant → harvests `Input1.ReconnectMode`); debug
  `chid` gains an optional `[MAC]` (connectionless variant, no live session).
  Also fixes a latent LE bug where the old debug `chid` LE branch called a
  non-existent `get_properties()` and therefore always produced empty evidence;
  it now uses the real `get_device_appearance`/`get_uuids` + `Input1` accessors.
- Docs: `bleep/docs/device_type_classification.md` gained a
  connectionless-vs-connected evidence-delta table and a variant matrix;
  `cli_usage.md`, `debug_mode.md`, and the in-shell `help` were updated. New
  tests: `tests/test_pan_command_uniformity.py`, `tests/test_hid_dual_variant.py`.
- **Verified:** full suite green (`1856 passed, 34 skipped, 0 failed`);
  M1.5/M1.6 + guard subset `215 passed`.

### Live-test remediation: async D-Bus dispatch, defensive accessors, honest verdicts (2026-07-28)

Fixes found during a live CLI/soak test pass. Root-caused, proven with
contention-independent PoCs, and validated live before/after.

- **P0 — async D-Bus reply dispatch (the `advertise` / `gatt-server` / `monitor`
  "silent 5 s timeout" bug).** `LEAdvertisingManager.register`,
  `GattServerManager.register_application`, `AdvMonitorManager.register` (and
  their unregister siblings) issued an *asynchronous* D-Bus call with
  `reply_handler`/`error_handler` but then busy-waited with `time.sleep()`, which
  never lets the GLib loop dispatch the reply — so the registration always timed
  out even when BlueZ succeeded, and the real error was hidden. Extracted a
  single shared helper **`bleep/dbuslayer/_dbus_wait.py::call_async_await`** that
  runs a temporary `GLib.MainLoop` when no background loop owns the default
  context (the proven `agent.py` pattern), terminates via a GLib timer (immune to
  clock mocking), and surfaces the real BlueZ error. Wired into all six
  register/unregister call sites, removing ~12 duplicated busy-wait blocks.
  *Result:* `gatt-server start` and `advertise --type broadcast` now work;
  unsupported operations fail fast with the true error instead of hanging.
- **P1 — defensive optional-property accessors.** `device_le` accessors
  (`Icon`, `Appearance`, `RSSI`, `TxPower`, `Modalias`, `UUIDs`,
  `ManufacturerData`, `ServiceData`, `AdvertisingFlags`/`Data`, `Sets`,
  `PreferredBearer`, `Alias`, `Name`) previously re-raised on
  `InvalidArgs` ("No such property") — crashing e.g. `media-enum --passive` on
  devices that don't expose `Icon`. Collapsed into one
  `_get_optional_property()` helper that maps both `UnknownObject` and
  `InvalidArgs` to `None` and re-raises anything else.
- **P1 — advertise payload validation.** BlueZ rejects an advertisement that both
  sets a property explicitly *and* asks it to auto-include the same field via
  `Includes` ("Failed to parse advertisement"). `_build_properties` now drops the
  redundant include when the explicit property is set. Verified against the live
  conflict matrix: `LocalName`↔`local-name` and `Appearance`↔`appearance` conflict
  (both fixed); `TxPower`↔`tx-power` does **not** conflict (left untouched).
- **P1 — `media-enum --passive` object lifecycle.** LE peers using
  resolvable-private addresses routinely rotate/disappear between discovery and
  assessment; `assess_media_device` then blew up on a raw `UnknownObject` D-Bus
  dump at the first state read. It now maps a vanished object to a clean
  `DeviceNotFoundError` ("Device … not found").
- **P1 — `classic-enum` device resolution.** A connected-but-non-discoverable
  (bonded) peer failed the fresh BR/EDR discovery gate. `_target_known()` now
  consults the object manager first, so already-known devices skip discovery.
- **P2 — `usb_ids` generator escaping.** `update_usb_ids.py` only escaped quotes,
  emitting an invalid `\R` escape (`SyntaxWarning`) for the product name
  `CD\RW 40X`. Added `_pystr()` (escapes `\` then `"`); fixed the one affected
  generated line (runtime value unchanged).
- **P3 — output ordering.** `print_and_log` now flushes stdout so piped/redirected
  output stays in chronological order with the file logs and stderr.
- **P3 — `agent --list-bonded`.** Renders epoch timestamps as
  `YYYY-MM-DD HH:MM:SS` and falls back to the observations DB for the device name.
- **P3 — `--diagnose-audio` verdict.** Now factors in GStreamer SBC codec
  readiness: reports "routing available but codec plugins incomplete" instead of
  a blanket "ready".
- **Advertise include guidance (`--include-appearance` foot-gun).** `--appearance
  <value>` sends a self-contained Appearance; `--include-appearance` asks BlueZ to
  source it from the (often-unset) adapter/system value, which then fails with
  "Failed to register advertisement". `advertise start` now (A) warns before
  registering when `--include-appearance` is used without `--appearance`, (B)
  prints a targeted "pass --appearance <value>" hint on that failure, and (C)
  pre-flights all requested `--include-*` flags against the adapter's
  `SupportedIncludes` and warns on any it does not advertise. Logic lives in a
  pure, unit-tested helper `advertise._validate_includes`; flag help text
  clarified (self-contained vs. sourced). Tests: `tests/test_advertise_includes.py`.
- **Correction (triple-pass live validation).** The earlier working hypothesis
  that this CSR 4.0 controller "rejects connectable `peripheral` advertising" was
  a **misdiagnosis**: with the P0 dispatch fix in place, `peripheral` advertising
  succeeds reliably (8/8 repeat runs, plus name/appearance variants). The prior
  failures were orphaned registrations left by the busy-wait bug. The misleading
  "retry with `--type broadcast`" hint was removed; the mode now points to the
  real BlueZ error and `advertise caps`.
- **Docs.** Added/corrected the "Environmental limitations & known constraints"
  section in `cli_usage.md`: advertising payload conflicts (auto-resolved),
  `--include-appearance`-without-value controller quirk, AdvertisementMonitor
  support, WSL `l2ping` capability, and audio codec packages.
- **Tests:** new `tests/test_dbus_wait.py`, `tests/test_device_le_optional_props.py`,
  `tests/test_classic_target_known.py`; advertise payload-conflict cases
  (local-name + appearance drop, tx-power kept); `media-enum --passive`
  vanished-object cases; `tests/test_advertise_includes.py` (include validation
  A/B/C); existing register/unregister timeout tests updated to the new helper
  contract. Full suite: **1653 passed, 34 skipped**.

### DT-1: repo-wide `datetime.utcnow()` deprecation migration (2026-07-28)

`datetime.utcnow()` is deprecated in Python 3.12+. Migrated all **29 call sites
across 13 files** to a central helper, **preserving the on-disk naive-UTC string
format** the observation DB and its comparison queries depend on — so there is
**zero behavioural change** to stored timestamps.

- **New `bleep/core/time_utils.py`** with two helpers:
  - `utc_now_iso()` → `datetime.now(timezone.utc).replace(tzinfo=None).isoformat()`
    — a naive-UTC string that is **byte-shape identical** to the legacy
    `datetime.utcnow().isoformat()` (verified at runtime). Drop-in for all 25 DB
    string writers.
  - `utc_now()` → `datetime.now(timezone.utc)` — an aware object for
    arithmetic/durations only (the 4 `_maintenance.py` VACUUM/ANALYZE timing
    sites). Never persisted as a string.
  - Rationale: the `datetime.now(timezone.utc)` form the deprecation warning
    suggests is *aware* and its `.isoformat()` appends `+00:00`, which breaks
    lexicographic comparison against SQLite's naive `datetime('now')` and raises
    `TypeError` when mixed with existing naive rows. `utc_now_iso()` strips
    `tzinfo` to stay a true drop-in.
- **Migrated sites:** observations layer (`_connection`, `_services`, `_history`,
  `_aoi`, `_devices`, `_media`, `_pairing`, `_evidence`, `_maintenance`) plus the
  four LT-2 writers (`aoi_analyser`, `ble_ops/le/scan`, `modes/classic_enum`,
  `dbuslayer/device_classic`). Removed now-unused `from datetime import datetime`
  imports; display/report/filename `datetime.now()` calls and the SQL literal
  `datetime('now')` were intentionally left unchanged.
- **Tests/gates:** added `tests/test_time_utils.py` (format/offset/roundtrip/aware
  assertions). `utcnow(` in `bleep/` is now zero; lint-clean; full suite **1627
  passed / 27 skipped** (pre-existing gstreamer/audio-codec env failures excluded
  and proven unrelated by stashing the change set). Live-verified against a temp
  `BLEEP_DB_PATH`: device/service/adv writes store naive UTC with no offset,
  `first_seen == last_seen` on insert, recency query and `aoi list` work.
- **Scope note:** format-preserving — historical rows are not rewritten; the
  signals `capture_config`/`router` config-file timestamps (separate subsystem,
  `datetime.now()`, not the observation DB) are out of scope. Full plan + PoC:
  `bleep/docs/datetime_utc_migration_plan.md`.

### Live-test fixes: explore service-resolution robustness + UTC timestamp normalization (2026-07-27)

Two defects surfaced during multi-antenna live testing against local targets
(BLE-CTF, Light Orb, a Sphero robot). Both fixes are surgical and behaviour is
verified live on real hardware.

- **`explore` passive mode spuriously failed `ServicesNotResolved` on rich GATT
  servers (`bleep/ble_ops/le/scan_modes.py`).** `passive_scan_and_connect`
  distributed its `--timeout` (default 10 s) as 50/25/25 across scan/connect/
  resolve, leaving only **5 s** for service resolution with a single attempt. A
  Sphero robot (6 services / 25 characteristics) *connected* fine but could not
  resolve within 5 s, so `explore` failed twice where `gatt-enum`/`aoi scan`
  (which use the stack default 15 s window / retry controller) succeeded on the
  first attempt. Fixed by aligning the service-resolution floor with the rest of
  the stack (`max(timeout, 15)` s), scaling the connect floor to 5 s, and adding
  one bounded connect+resolve retry (`max_attempts=2`, capped backoff) — matching
  gatt-enum/AoI robustness without turning passive into the aggressive naggy
  mode. Verified live: the same Sphero now resolves (`Services resolved: True`,
  6 services / 25 characteristics enumerated).
- **AoI analysis wrote `devices.last_seen` in local time
  (`bleep/analysis/aoi_analyser.py`).** Every `aoi ... --analyze` run overwrote
  `last_seen` via `datetime.now().isoformat()` (local) while the entire
  observations layer and survey persistence use naive UTC
  (`datetime.utcnow().isoformat()`). This made AoI-enumerated devices show a
  `last_seen` earlier than their survey-set `first_seen` in `db list`. Normalized
  that writer — plus three sibling `version_queried_at` writers that also used
  local time (`bleep/ble_ops/le/scan.py`, `bleep/modes/classic_enum.py`,
  `bleep/dbuslayer/device_classic.py`) — to naive UTC. (Normalized to the
  existing dominant naive-UTC convention rather than tz-aware to avoid breaking
  lexicographic comparisons against SQLite's naive `datetime('now')`.) Verified
  live: after `aoi analyze` a device's `last_seen` now records UTC
  (`23:45` UTC, not local `19:45`), consistent with `first_seen`.
- **Docs/tracker.** `todo_tracker.md` gains LT-1/LT-2 (resolved) and **DT-1**
  (planned repo-wide `datetime.utcnow()` deprecation migration).
  `observation_db_schema.md` now documents the **enforced naive-UTC** timestamp
  convention (with an explicit "never write local time / tz-aware offset" rule).
  `explore_mode.md` updated for the new passive timeouts/retry. Added
  `datetime_utc_migration_plan.md` — DT-1 plan of work with executed PoC and
  citations (proves the naive-UTC-preserving helper is byte-shape identical to
  the legacy output and that mixing naive/aware timestamps breaks arithmetic).

### Multi-antenna survey + adapter-aware signal routing D1/D2 (2026-07-26)

Implements concurrent multi-adapter passive collection (Phase 4 groundwork): one
antenna can sweep LE while another performs BR/EDR inquiry simultaneously, or
several antennas cover the same transport for spatial coverage. Foundation for
the collect-on-one-antenna / enumerate-on-another goal. All changes are additive
and default-path-preserving (single-adapter survey is unchanged); +36 tests
(routing 15, multi/census 12, loop service 3, DB lock 2, plus existing 10 RSSI
capture green). Full suite **1600 passed / 34 skipped** (pre-existing 11 failures
are BlueZ/GStreamer/subprocess env-only, identical on a pristine `HEAD`).

- **D1 — Adapter-aware RSSI routing (`bleep/dbuslayer/signals.py`).** The signals
  manager previously held a single `_device_manager` slot, so with multiple
  adapters an RSSI observation could land in the wrong adapter's cache. It now
  keeps a `_device_managers` dict keyed by `adapter_name`; `_capture_device_rssi`
  parses the `hciN` out of the D-Bus object path (`_adapter_from_device_path`) and
  routes to the owning manager. With ≥2 managers and no adapter match the
  observation is dropped (never mis-routed); with exactly one manager the legacy
  adapter-blind behaviour is preserved. `register`/`unregister_device_manager`
  manage the dict, and a compat `_device_manager` property/setter keeps existing
  single-adapter callers/tests working. `manager.py::_cleanup_after_run` now
  deregisters on exit.
- **D1.4 — Shared GLib main-loop service (`bleep/dbuslayer/loop_service.py`, new).**
  A reference-counted process-wide `MainLoopService` runs one `GLib.MainLoop` on a
  dedicated daemon thread so N adapter sessions collect concurrently without each
  blocking a thread on its own loop. A thread-per-collector alternative is
  documented as a deferred future option (feasibility note in-module).
- **D1.5 — `AdapterSession` + registry (`bleep/dbuslayer/adapter_session.py`, new).**
  Thin composition of adapter + role (collector/enumerator) + transport with
  non-blocking `begin`/`harvest`/`end`; `harvest` filters the global
  `GetManagedObjects` view by adapter object-path so antennas never double-count.
  `DeviceManager` gains non-blocking `begin_discovery`/`end_discovery` and
  `start_discovery(transport=...)` (default `le`, backward compatible).
- **D2.1 — Observation DB serialization (`bleep/core/observations/_connection.py`).**
  `_db_cursor()` now acquires `_DB_LOCK` for the whole cursor→commit window (the
  shared `sqlite3` connection is `check_same_thread=False` and unsafe for
  concurrent use). `_DB_LOCK` is upgraded to an `RLock` so the ~29 existing
  `with _DB_LOCK, _db_cursor()` sites (and lazy `_init_db`) remain reentrant
  rather than self-deadlocking.
- **D2.2/2.3 — Multi-collector orchestrator + census enrichment
  (`bleep/modes/survey_multi.py` new; `bleep/modes/survey.py`).** `SurveyCensus`
  is made thread-safe (`RLock` around merge/filter) and gains a `seen_by` set;
  `merge_le_results`/`merge_classic_results` accept an `adapter` tag emitted as the
  `seen_by` output field. `run_multi_collector` drives concurrent per-adapter
  rounds into one census on the shared loop, with **transport-split** as the
  default coverage profile and **spatial** (same transport on ≥2 antennas) as an
  opt-in.
- **D2.4 — CLI (`bleep/cli/parsers/survey.py`).** Repeatable
  `--collector hciN[:TRANSPORT]` flag; bare adapters round-robin `le`/`bredr`
  (transport-split default). `survey.run()` dispatches to the multi path when any
  collector is given and otherwise runs the unchanged single-adapter loop.

### Survey sighting-count semantics + passive RSSI capture LR-1b/LR-6 (2026-07-25)

Follow-up to the LR-1a/LR-2/LR-3/LR-5 batch below, resolving the two findings that were
previously deferred pending analysis. Both changes are additive and default-path-safe;
+13 tests (3 survey, 10 signals). Full targeted suites green
(`test_survey.py` 61, `test_signals_rssi_capture.py` 10, checkpoint/insert_adv/aoi 109).

- **LR-1b — `sightings` now counts live observations, not cached re-reads.**
  `SurveyCensus._merge_entry` (`bleep/modes/survey.py`) incremented `sighting_count`
  unconditionally every round, so bonded/paired devices that BlueZ keeps in
  `GetManagedObjects()` without advertising inflated to ≈rounds (×2 for dual) — live-run
  confirmed 4 paired devices (`98:3B:8F:EF:FE:EC`, `F4:B6:88:0B:90:22`,
  `9C:D3:5B:A0:C3:C4`, `43:25:00:6A:0E:CA`) counted 6/6 rounds with RSSI never present.
  The increment is now gated on the **cached predicate** already used for `is_cached`
  (no fresh RSSI **and** paired/bonded); a device first seen only as a cache entry seeds
  `sightings: 0` and is excluded by the default `--min-sightings 1` (consistent with
  `--resume-db` seeded devices). Gating on the cached predicate rather than raw RSSI is
  deliberate: passive `DuplicateData=True` drops RSSI for ~4% of genuine adverts
  (measured: one unpaired advertiser flapped `[None,None,-60]`; naggy 100%), so an
  RSSI-only gate would undercount real unpaired advertisers. Trade-off: a transient
  *unpaired* lingering managed object may still be counted, bounded by BlueZ's temporary
  eviction — chosen over undercounting live devices. `last_seen` still advances on cached
  re-reads; dual seen live in both phases counts 2/round.
- **LR-6 — RSSI captured from `InterfacesAdded`, not only `PropertiesChanged`.** The
  DeviceManager RSSI cache was fed solely by `PropertiesChanged`
  (`bleep/dbuslayer/signals.py`), so under passive scanning (often a single
  `InterfacesAdded` per device) a live device could report `rssi=None`. The capture
  logic is refactored into a shared `_capture_device_rssi(path, rssi)` helper (guards:
  device path + `is_discovery_active`) now called from both `PropertiesChanged` and
  `_interfaces_added` (only when `DEVICE_INTERFACE` carries `RSSI`). Radio behavior is
  unchanged; switching survey rounds to naggy by default was rejected to preserve the
  passive/quiet character (a future opt-in flag is tracked in `todo_tracker.md`).

### Survey/AoI live-run fixes LR-1a/LR-2/LR-3/LR-5 (2026-07-25)

Four correctness/hygiene fixes surfaced by an agent-executed 4-hour `--transport
both` survey (`--resume-db --adaptive --exclude-cached --checkpoint-interval 120
--auto-recover`) followed by `aoi scan --analyze` + `aoi report --all`. All changes
are additive and default-path-preserving; source-cited verification lives in
`workDir/LongRun_20260725_070234/`. Full suite **1574 passed / 27 skipped** (+14
tests). Two run findings were dispositioned without code changes: **LR-1b**
(`sighting_count` inflated by cached ManagedObjects re-reads) is **deferred** (a fix
changes the meaning of `sightings` and needs a semantics decision), and **LR-4**
(pure-Classic discovery ~0 after warm-up) is **disproven** — environmental, the
`bredr` inquiry path is correct.

- **LR-2 — `fingerprint_changed` now detects same-length payload rotation.**
  `SurveyCensus._merge_mfr_data`/`_merge_svc_data` (`bleep/modes/survey.py`)
  previously flagged a change only when the incoming payload was *strictly longer*,
  so the common iBeacon/Eddystone/status-byte rotation (same length, differing bytes)
  was silently missed — 0/76 devices flagged across the run despite Light Orb
  (`F0:98:7D:0A:05:07`) rotating service-data `0210ffff00`→`0210ffff02`. Both helpers
  now also adopt-and-flag when `len(new)==len(old) and new!=old`. Longest-wins and
  shorter-ignored semantics are preserved.
- **LR-1a — `--exclude-cached` now honors DB-resumed devices.** `seed_from_db()`
  built each `DeviceSighting` without `is_cached`, defaulting it `False`, so
  `--resume-db --exclude-cached` still emitted bonded devices never seen live this run
  (`43:25:00:6A:0E:CA`, `98:3B:8F:EF:FE:EC`, …). Seeded sightings are now created with
  `is_cached=True`; the existing re-sight path clears the flag the moment the device
  is seen live with RSSI (`survey.py:252-253`), matching the documented
  `--exclude-cached` semantics.
- **LR-3 — `adv_reports` coalesces consecutive identical samples.** BlueZ's
  `GetManagedObjects()` re-reports the same advert every survey round, and `insert_adv`
  did an unconditional `INSERT` (1807 rows/run, 465 identical rows for BLECTF; the raw
  `data` blob is almost always empty because `advertising_data` is rarely exposed).
  `bleep/core/observations/_history.py` now skips the insert when `(data, decoded)`
  equals the most recent row for that MAC (new `_as_blob_bytes` normalizer for stable
  BLOB comparison). RSSI-only changes are intentionally not persisted here — RSSI
  aggregates already live on the `devices` row. Non-consecutive changes (A,B,A) still
  produce distinct rows.
- **LR-5 — `aoi report --all` no longer diluted by non-enumerated targets.**
  `generate_aggregate_report` averaged/tabulated over every loaded device, so dozens
  of `0/10` LE targets that never enumerated (stale RPAs) dragged the aggregate toward
  0.6/10. New `AOIAnalyser._device_was_enumerated()` classifies a device as reachable
  when it exposes GATT services, Classic SDP/pairing data, enumerated characteristics,
  or any raised concern. Markdown/text reports split the summary into **Analyzed** vs
  **Not Reachable (no GATT/SDP enumerated)**; the average is computed over analyzed
  devices only. JSON gains `analyzed_count`/`not_reachable_count` metadata and a
  per-device `reachable` flag; `device_count` and `avg_security_score` keys are
  retained (average is now analyzed-only).
- **Tests (+14).** `tests/test_survey.py`:
  `test_manufacturer_data_same_length_change_flags_fingerprint`,
  `test_manufacturer_data_same_length_identical_no_flag`,
  `test_service_data_same_length_change_flags_fingerprint`,
  `test_service_data_shorter_does_not_replace`, `test_seed_marks_devices_cached`,
  `test_seed_cached_excluded_by_exclude_cached`, `test_seed_cached_cleared_when_seen_live`.
  `tests/test_insert_adv.py`: `test_insert_adv_coalesces_consecutive_identical`,
  `test_insert_adv_new_row_on_decoded_change`, `test_insert_adv_new_row_on_data_change`,
  `test_insert_adv_dedup_is_consecutive_only`, `test_insert_adv_coalesces_empty_data`.
  `tests/test_aoi_augmentation.py`: `test_aggregate_markdown_excludes_not_reachable`,
  `test_aggregate_json_average_over_reachable_only`.

### SDP XML robustness (F-1) + timeline UUID display normalization (F-2) (2026-07-25)

Two fixes surfaced during real-device validation of the SDP profile-label work
(PLT V8200 headset `F4:B6:88:0B:90:22`, BlueZ 5.79). Both are additive and leave
the default operator path byte-for-byte unchanged. Full suite **1560 passed / 27
skipped** (+4 tests).

- **F-1 — `_parse_browse_xml` tolerates sdptool trailing status text.**
  `sdptool browse --xml` frequently appends non-XML status lines
  (`Browsing …`, `Service Search failed: Invalid argument`) *after* `</record>`
  in the same `<?xml?>`-delimited fragment, making the fragment malformed and
  previously sinking the whole record on `ET.ParseError`. `ble_ops/classic/sdp.py`
  adds `_XML_RECORD_RE` and clips each fragment to its `<record>…</record>`
  span(s) before parsing (`… or [frag]` falls back to the old whole-fragment
  parse when no `<record>` is present; it also parses multiple records in one
  fragment). Effect: the XML-only enrichments (attribute labels incl.
  profile-scoped IDs, additive protocol `parameters`, secondary-language string
  labels) now actually reach output. Verified on hardware: `source="xml"` returns
  the DID record with labels `0x0200–0x0205` (previously raised "no records");
  `source="all"` union changes from `browse+records` to `browse+xml+records`. The
  `auto` chain (MCP default) is unchanged — plain `browse` text still wins when it
  returns RFCOMM channels.
- **F-2 — canonical UUID rendering in `db timeline --sdp`.** Legacy `sdp_records`
  rows stored short UUIDs with an upper-cased `0X` prefix (`0X1108`). `modes/db.py`
  adds display-only `_canon_sdp_uuid()` (`0X1108`→`0x1108`, upper-cases hex and
  dashed 128-bit forms, passes through `None`/non-UUIDs) applied to the
  `timeline_sdp` grouping key, so legacy rows render canonically **and** fold onto
  the same group as their lower-case equivalent. Stored data is untouched; the
  current parser already emits canonical `0x…` forms.
- **Tests.** `test_sig_sdp_profile_attr_ids.py`:
  `test_browse_xml_survives_trailing_status_text` (uses the real trailing-junk
  capture) + `test_browse_xml_multiple_clean_records_still_parse`.
  `test_db_sdp_timeline.py`: `test_canon_sdp_uuid_forms` +
  `test_timeline_display_canonicalizes_legacy_uuid`.

### SDP profile-label follow-through: WAP mapping + string offsets + protocol parameters (2026-07-24)

Discharges the two deferred successors of the profile-scoped SDP work. All changes
are additive/lossless and default-output-preserving; verified against BlueZ
`lib/sdp.h`/`sdp.c` (`workDir/bluez/`). Full suite **1556 passed / 27 skipped**
(+12 tests).

- **Item 2 — WAP profile now reachable.** `update_sig_sdp_attr_ids.py` maps
  `interoperability_requirements` → service classes `0x1113`/`0x1114` (WAP /
  WAP_CLIENT, SIG `service_class.yaml`), so its WAP attribute table
  (`0x0306 NetworkAddress` … `0x0309 WAPStackType`) resolves. New standing test
  `test_no_unmapped_profile` asserts **every** ingested profile has a
  `SERVICE_CLASS_TO_PROFILE` entry (guards against future unmapped tables).
- **Item 1b — protocol-parameter names.** Generator ingests the sibling
  `protocol_parameters.yaml` → `SDP_PROTOCOL_PARAMETERS = {protocol: {index: name}}`
  (cached at `bt_ref/sig_cache/protocol_parameters.yaml`).
  `_extract_protocol_descriptors_xml` now emits an additive `parameters` list
  (`{index, name, value}`) per descriptor, naming positional params
  (`L2CAP[1]=PSM`, `RFCOMM[1]=Channel`, `BNEP[1]=Version`,
  `BNEP[2]=Supported Network Packet Type List`) and capturing **all** params (not
  just the first). Fixed a latent case bug (`_KNOWN_PROTOS` lookup upper-cased the
  hex UUID so `BNEP`/`AVCTP`/`AVDTP` never matched); existing `uuid`/`name`/`params`
  fields are untouched.
- **Item 1a — secondary-language string labels (Option B).** Generator ingests
  `attribute_id_offsets_for_strings.yaml` → `SDP_STRING_ATTR_OFFSETS`
  (ServiceName/Description/ProviderName at offsets 0/1/2). `_parse_xml_record`
  pre-scans the `LanguageBaseAttributeIDList` (attr `0x0006`, uint16 triplets
  `(code_ISO639, encoding, base_offset)` per BlueZ `sdp_get_lang_attr`) and labels
  non-primary-base string attributes as e.g. `"Service Name (fr)"` in
  `attribute_labels`. Primary base `0x0100` stays with the universal table;
  order-independent; additive.
- **Generator discipline.** Both siblings are network-best-effort with committed
  per-file cache and a `_committed()` fallback that preserves prior constants on an
  empty fetch (never zeroes a table). `refresh-refs` wiring unchanged (already runs
  the generator in the SIG group).

### Deferred-item follow-through: adv/observed evidence + profile SDP labels + observed seed + SDP change view (2026-07-24)

Four scoped, additive items from the "Directly deferred from the just-finished
cycle" list. Acceptance decisions: observed-catalogue promotion is **opt-in
(default off, provenance-tagged)**; the curated seed is **kept separate from the
classifier**; SDP profile labels emit **per-profile attribute IDs only**. See
`docs/todo_tracker.md` → "ACCEPTED WORK — Deferred-item follow-through …".

- **Eddystone as STRONG LE evidence (A1).** `analysis/device_type_classifier.py`
  adds `"eddystone"` to `_LE_INDICATIVE_ADV_PROTOCOLS` and now feeds **both**
  ManufacturerData and ServiceData through the shared dissector — a decoded
  Eddystone (ServiceData/0xFEAA) frame classifies a beacon-only device as LE
  instead of `unknown`. Confidence counts distinct evidence-type presence, so the
  existing FEAA beacon-block STRONG add is not double-counted.
- **Opt-in source-aware observed promotion (A2).** New
  `core/observations/get_observed_uuid_evidence(uuid)` reports which table-kinds a
  UUID was *measured* in. With promotion enabled
  (`context["allow_observed_promotion"]` or env
  `BLEEP_CLASSIFIER_OBSERVED_PROMOTION`), an advertised UUID measured as LE GATT
  elsewhere adds STRONG `LE_ADVERTISING_DATA` (`observed_le_gatt`); measured as
  Classic/SDP adds STRONG `CLASSIC_SERVICE_UUIDS` (`observed_classic`), both tagged
  `promoted=True`. **Default off is byte-identical** to the prior WEAK-only feed
  (stateless guarantee); verdict functions unchanged.
- **Profile-scoped SDP attribute-ID labels (B).** New generator
  `bt_ref/update_sig_sdp_attr_ids.py` pulls the SIG
  `service_discovery/attribute_ids/*.yaml` per-profile tables (cached under
  `bt_ref/sig_cache/attribute_ids/`) into `bt_ref/sdp_profile_attr_ids.py`
  (`SDP_PROFILE_ATTR_IDS` + curated `SERVICE_CLASS_TO_PROFILE`, grounded in SIG
  `service_class.yaml`). `resolve_sdp_attr_id(attr_id, service_class_uuid=None)`
  (regenerated in `sdp_attr_ids.py`) now disambiguates context IDs (≥ 0x0200) by
  service class — e.g. `0x0200` → `HIDDeviceReleaseNumber` for a HID record,
  `IpSubnet` for PAN. `_parse_xml_record` pre-scans the Service-Class-ID so
  labelling is order-independent; `attribute_labels` stays additive/lossless.
  Wired into `refresh-refs` (SIG group).
- **Curated observed-UUID seed (C).** New committed `bt_ref/observed_seed.py`
  (Nordic UART trio, Google Nearby vendor base). `get_observed_uuid_catalogue(...,
  include_seed=True)` (CLI `db uuids --seed`) unions it as a distinct
  `source="curated_seed"` tier — never fed to the classifier, default output
  unchanged.
- **SDP change timeline (D).** New `core/observations/get_sdp_timeline(mac, uuid,
  limit)` reads the append-only `sdp_records` history; `db timeline --sdp` prints
  an `[initial]` snapshot then consecutive-snapshot field diffs (incl. handle
  rotation). Read-only; default `db timeline` (characteristics) unchanged.
- **Tests.** +32 (`test_classifier_adv_protocol_feed`, `…_observed_promotion`,
  `test_sig_sdp_profile_attr_ids`, `test_observed_seed`, `test_db_sdp_timeline`);
  `test_api_surface` observation-symbol count 38→40. Full suite **1544 passed /
  27 skipped**.
- **Deferred (future work):** ingesting the SIG
  `attribute_id_offsets_for_strings.yaml` / `protocol_parameters.yaml` siblings;
  profiles without a service-class mapping (e.g. `interoperability_requirements`)
  ship their table but stay unreachable until a mapping is added.

### Classifier feed + SDP attribute-ID labels + core_version emission (2026-07-24)

Three deferred-cycle items, implemented additively. Decisions locked at
acceptance: BlueZ pull pinned to commit `4c431e5d`; SDP labels use verbose Core
Spec names; classifier feed is WEAK-only. See `docs/todo_tracker.md` →
"ACCEPTED WORK — Classifier feed + SDP attr-ID labels + core_version emission".

- **BlueZ-sourced SDP universal attribute-ID labels (Item 2).** New
  network-best-effort updater `bt_ref/update_bluez_refs.py` pulls upstream BlueZ
  `lib/sdp.h` (`github.com/bluez/bluez`, canonical
  `git://git.kernel.org/pub/scm/bluetooth/bluez.git`, pinned commit
  `4c431e5dae3e7cee4ce3d0720fefc530a2524e0b`) into a committed
  `bt_ref/bluez_cache/sdp.h` fallback and emits `bt_ref/sdp_attr_ids.py`
  (`SDP_UNIVERSAL_ATTR_IDS`, `resolve_sdp_attr_id()`). Scope is the **unambiguous
  universal range** `0x0000–0x000D` plus the primary-language string offsets
  `0x0100–0x0102`; IDs `>= 0x0200` are profile-context-dependent (BlueZ reuses
  `0x0200` across GROUP_ID/IP_SUBNET/VERSION_NUM_LIST/SPECIFICATION_ID/HID… ) and
  resolve to `None`. `ble_ops/classic/sdp.py` `_parse_xml_record` gains a
  **lossless, additive** `attribute_labels` annotation (labels universal IDs
  present in a record — including ones it doesn't otherwise parse — without
  dropping raw data or overwriting parsed fields); the merge/union path unions
  labels across sources. Wired into `refresh-refs`.
- **`core_version.yaml` emission into `uuids.py` (Item 3).** New dedicated
  `core_version` branch in `_gen_dict_block` emits **2-digit** keys (`"0x0c"`) to
  match `resolve_core_version()`'s `f"0x{lmp_version:02x}"` lookup. Fixed a latent
  codegen bug: PyYAML parses `0x0A` as the int `10`, so the generic
  `int(str(value), 16)` path mis-keyed values ≥ `0x0A` (10 → `"0x10"`); the new
  branch handles the already-parsed-int case. `SPEC_ID_NAMES__CORE_VERSION` is now
  populated in the committed `uuids.py` (surgically appended — no full-file
  regen, preserving hand-added CTF/Mesh header content and avoiding SIG data
  drift). **Behavioural change:** `map_lmp_version_to_spec()` /
  `query_remote_version()` / `infer_min_bt_version_from_le_features()` now return
  the richer SIG names (e.g. *"Bluetooth® Core Specification 5.2"*) as the primary
  source, with `_LMP_VERSION_MAP` as fallback. This also **corrects** LMP
  `0x0E`/`0x0F`, which the stale fallback mislabelled "5.5"/"5.6", to the
  authoritative *6.0*/*6.1*. Ten `test_remote_version.py` assertions updated to the
  SIG strings.
- **Classifier observed-UUID feed (Item 1).** `LEServiceDataCollector` now adds
  **WEAK** `LE_ADVERTISING_DATA` evidence for advertised UUIDs found in the
  observed-UUID catalogue (`get_observed_uuid_names`) but not in the curated
  beacon/UART sets, tagged `evidence_source="observed_catalogue"`. Additive only:
  WEAK evidence contributes to confidence/reasoning but **cannot flip a verdict**
  (`_classify_*` consult only CONCLUSIVE/STRONG), so a mislabelled observation can
  never mis-type a device. Wrapped so a catalogue/DB error never breaks
  classification.
- **Tests.** New `tests/test_sdp_attr_ids_core_version.py` (10) and
  `tests/test_classifier_observed_feed.py` (5). Docs: `docs/uuid_translation.md`
  (BlueZ SDP source, context-dependence, core_version), `docs/observation_db.md`
  (classifier feed).

### SDP source union + Observed-UUID catalogue + CoD/Mesh reference tables (2026-07-24)

Groups three accepted "Future Work" items into one additive, default-preserving
change set. Existing outputs, DB rows, and `bt_ref/uuids.py` are untouched; new
reference data lands in *new* generated modules so the SIG tables have zero drift
risk. See `docs/todo_tracker.md` → "ACCEPTED WORK — SDP union + Observed-UUID
catalogue + Reference additions (2026-07-24)".

- **Updater safety hardening** (`bt_ref/update_ble_uuids.py`) — a failed fetch
  now **preserves the previously committed table** instead of emitting an empty
  dict (closes the offline `regenerate()`/`refresh-refs` footgun that could zero
  out `uuids.py`). New `_load_existing_tables`/`_emit_existing_block`/`_block_for`
  helpers; header `sources` reflects preserved-vs-fetched state.
- **Class-of-Device is now table-driven** — new generated `bt_ref/cod.py`
  (`COD_SERVICES`, `COD_MAJOR_DEVICE_CLASS`, `COD_MINOR_DEVICE_CLASS`,
  `COD_SUBMINOR_DEVICE_CLASS`) from SIG `core/class_of_device.yaml`.
  `decode_class_of_device()` sources every label from it (no more ~150 hardcoded
  bit→string literals). Triple-pass correction: SIG's historical `core/fhs.yaml`
  *was* Class-of-Device data; the canonical source today is `class_of_device.yaml`,
  so "incorporate fhs" is implemented as incorporate-CoD. Golden-parity test plus
  documented normalisations (e.g. `"LE audio"` casing) and new minor coverage.
- **Bluetooth Mesh assigned numbers** — new generated `bt_ref/mesh_ids.py`
  (`MESH_MODEL_UUIDS`, `MESH_BEACON_TYPES`) from SIG `mesh/*.yaml`;
  `get_name_from_uuid()` gains a final authoritative SIG tier for mesh model
  UUIDs (additive — only fills names that were `Unknown`).
- **`refresh-refs`** now regenerates `cod.py` + `mesh_ids.py` alongside the SIG
  UUID tables (independent failure handling).
- **SDP source union + provenance** (`ble_ops/classic/sdp.py`) —
  `discover_services_sdp(..., source=...)` selects the discovery source:
  `"auto"` (default, unchanged first-success chain), `"dbus"|"browse"|"xml"|
  "records"` (single source), or `"merge"`/`"all"` (union every source keyed by
  handle→uuid→name, filling missing fields, preserving *all* raw text under
  `# source:` headers, and recording per-field `source_conflicts`). Each record
  carries a `source` provenance label. `classic-enum` gains `--sdp-source`.
- **DB schema v18** — `sdp_records.source` provenance column (additive migration;
  existing rows get NULL). `upsert_sdp_record()` stores `source` (excluded from
  the change-detection tuple so provenance never inflates history).
- **`SDPAnalyzer`** gains a `source_discrepancy` anomaly (medium) when merged
  sources disagree on a scalar field.
- **Observed-UUID catalogue** ("seen in the wild") — new
  `core/observations/_uuids.py`: `get_observed_uuid_catalogue()` aggregates every
  UUID observed across LE services/characteristics/descriptors + Classic services
  + SDP records (canonicalised to 128-bit so short/long forms merge) into
  `{uuid, names, count, sources, first/last seen, sample_macs}`;
  `get_observed_uuid_names()` backs an **opt-in** observed tier of
  `get_name_from_uuid(..., allow_observed=True)` that returns a
  `"Unknown (seen as: …)"` hint (default output stays `"Unknown"`). New
  `db uuids` subcommand (list + `--uuid` filter + `--promote NAME`).
- **UUID promotion path** — new `bt_ref/custom_uuids.py` persists operator
  promotions to a JSON overlay (`~/.bleep/custom_uuids.json`, `BLEEP_CUSTOM_UUIDS`)
  that `constants.UUID_NAMES` merges at import (self-contained, reversible).
- **Deferred (future work, not dropped):** classifier feed of observed
  UUIDs/`adv_dissection`; SDP universal attribute-ID labels; `core_version.yaml`
  emission into `uuids.py`.
- **Tests** — `test_update_ble_uuids_safety.py`, `test_cod_decode.py`,
  `test_mesh_ids.py`, `test_sdp_source_union.py`, `test_observed_uuid_catalogue.py`;
  updated `test_refresh_refs.py` and `test_aoi_augmentation.py` (schema v18). Also
  fixed a pre-existing test-isolation leak in `test_observations_classic.py`
  (stale `_DB_CONN` to a deleted temp DB poisoned later tests).

### Test-isolation fix: thread-local output-mode leak (2026-07-24)

Fixed a pre-existing full-suite-only failure
(`test_discovery_error_surfacing::…test_stop_discovery_surfaces_no_discovery_started`,
which passed in isolation). Root cause: mode `run()` entry points call
`set_output_mode()`, stored in a `threading.local()` that is never cleared. A test
running a mode in `json`/`quiet` (e.g.
`test_db_show_adv_dissection::test_run_json_path_attaches_adv_dissection`) left the
main thread's mode set, so `print_and_log()` rerouted to stderr for later tests
asserting on captured stdout. Fix: added an autouse `tests/conftest.py` fixture
(`_reset_output_mode`) that restores the documented `"terminal"` default around
every test. No production code changed; full suite now green (1495 passed / 27
skipped).

### Advertisement dissection surfaced in `db show` (G-7.5) (2026-07-24)

Surfaces the attributed, lossless advertisement dissection in the CLI
device-detail command, so beacon/vendor payloads are readable for **any scanned
device**, not just AoI targets — the dissection is recomputed from the persisted
raw fields rather than requiring a stored block.

- **`analysis/adv_dissect.py`** — new `dissect_persisted_record(record)` shared
  adapter: reconstructs dissector inputs from persisted device/adv fields
  (`manufacturer_id`/`manufacturer_data`/`service_data`/`advertising_data`/
  `uuids`; bytes/hex/JSON/D-Bus-list tolerant; top-level or nested `device` row)
  and returns the dissection, or `None` when no adv data is present. Never raises.
- **`analysis/aoi_analyser.py`** — `_render_adv_dissection` now calls the shared
  adapter instead of its own inlined reconstruction (single source of truth;
  removed the now-dead `_adv_field` helper). Report output unchanged.
- **`modes/db.py`** — `db show <mac>` prints an "Advertisement Dissection"
  section (vendors/protocols, decoded protocols, raw hex + ASCII per entry);
  `db show --full` / `--json` / `--quiet` attach an `adv_dissection` block.
  `get_device_detail()` is unchanged (enrichment is done in the show command).
- **Tests** — `tests/test_db_show_adv_dissection.py` (human section, `--full`
  JSON, JSON path); `tests/test_adv_dissect.py` adds `dissect_persisted_record`
  coverage (BLOB/JSON/nested/empty/malformed).

### Advertisement dissection (G-7.5) (2026-07-23)

Adds structured, attributed dissection of BLE advertisement fields
(`ManufacturerData`, `ServiceData`, advertised UUIDs, `AdvertisingData`) while
**preserving all captured bytes** (raw hex + printable ASCII). Advertisements
sometimes carry clear text (e.g. some headsets embed a model string), so the
dissector never discards data even when a structured decoder also runs.

- **New `bleep/analysis/adv_dissect.py`** — `dissect_advertisement(...)` with
  two-source attribution (BT SIG + vendor/community specs), lossless raw+ASCII
  per entry, and protocol decoders for iBeacon, Eddystone (UID/URL/TLM/EID), and
  Apple Continuity TLVs. Graceful on malformed/short payloads.
- **New `bleep/bt_ref/update_vendor_specs.py`** + committed
  **`bleep/bt_ref/vendor_adv_specs.py`** — vendor/community fingerprint updater
  mirroring the BT SIG updater. Sources from the public `device-library` repo
  (GitHub tree API + raw), with `--local-path` bootstrap and a
  `vendor_specs_cache.json` offline fallback. Fully self-contained: no runtime
  dependency on any external checkout.
- **`ble_ops/le/scan.py`** — attaches an additive `adv_dissection` block to the
  persisted advertisement `decoded` payload (no schema change; never blocks the
  scan).
- **`analysis/device_type_classifier.py`** — **relabel-only** correction of
  misattributed beacon/service-data UUIDs (`FCF1`, `FE0F`, `FD6F`, `FE05`, …),
  now sourced from the single authoritative map in `adv_dissect.py` so the
  classifier and dissector cannot drift. Evidence type/weight unchanged →
  classification decisions preserved. See
  [adv_dissection.md](adv_dissection.md) "Known UUID attribution corrections".
- **`analysis/aoi_analyser.py`** — new "Advertisement Dissection" report section
  rendering attributed entries with raw hex + ASCII.
- **Docs** — new [adv_dissection.md](adv_dissection.md); cross-reference note in
  [device_type_classification.md](device_type_classification.md).
- **Tests** — `tests/test_adv_dissect.py` covers iBeacon/Eddystone/Continuity
  decoders, clear-text preservation, malformed input, lossless invariants, and
  the corrected UUID labels.

### Unified reference-data refresh command (2026-07-24)

Adds a single `bleep refresh-refs` command that regenerates BLEEP's committed
reference-data modules, wrapping the two previously module-only updaters.

- **New `bleep/modes/refresh_refs.py`** + `refresh-refs` subparser
  (`cli/parsers/utility.py`) and dispatch route (`cli/dispatch.py`). Runs both
  updaters by default; `--sig-only` / `--vendor-only` select one, `--local-path`
  bootstraps vendor specs from a local `device-library` checkout.
  - BT SIG assigned numbers → `bt_ref/uuids.py` (`update_ble_uuids.regenerate`).
  - Vendor/community adv specs → `bt_ref/vendor_adv_specs.py`
    (`update_vendor_specs.regenerate`).
- **`cli/main.py`** — `refresh-refs` is exempt from the Bluetooth adapter guard
  (`_non_bt_modes`); it performs no Bluetooth I/O. Both underlying updaters remain
  network-best-effort and self-contained (leave committed modules untouched / use
  cached data on failure).
- **Tests** — `tests/test_refresh_refs.py` covers flag routing, mutual exclusion,
  exception handling, and parser/dispatch/adapter-guard wiring.

### Classification blind spots closed (G-7.4) (2026-07-24)

Closes the three device-type classification blind spots, reusing the G-7.5
dissector instead of re-implementing decode logic in the classifier.

- **`analysis/device_type_classifier.py`** — `LEServiceDataCollector` now feeds
  `ManufacturerData` through `dissect_advertisement()` and emits STRONG
  `LE_ADVERTISING_DATA` evidence for BLE-only protocols (`ibeacon`,
  `apple_continuity`; set `_LE_INDICATIVE_ADV_PROTOCOLS`). Beacon-only devices
  (no advertised GATT/service-data UUID) now classify as `le` instead of
  `unknown`. A bare, undecoded company payload is **not** treated as LE evidence
  (mfg-data also appears in Classic EIR).
- **`analysis/device_type_classifier.py`** — advertised Classic-profile UUID
  evidence is now flagged `ground_truth=False` / `source_kind="advertised"`; such
  a verdict reports `evidence_source="heuristic"` (only measured SDP/GATT promote
  to `measured_*`). The decision is unchanged; it is now honestly labelled.
- **`modes/aoi.py`** — `_classify_device` returns the full `ClassificationResult`;
  `_scan_target` records `device_type_evidence_source` and `device_type_cached`.
- **`analysis/aoi_analyser.py`** — the markdown report now renders a **Device
  Type** line annotated with the evidence source, a `cached` marker, and the
  seed/live source, so an advertised/cached guess is never read as measured.
- **Tests** — new cases in `tests/test_device_type_integration.py` (iBeacon /
  Apple Continuity → `le`; bare vendor mfg-data → `unknown`; advertised Classic
  UUID → `heuristic` + `ground_truth=False`) and
  `tests/test_aoi_concern_render_sr_n5.py` (Device Type provenance render).

### Survey mode — adapter-drop resilience + opt-in in-run recovery (2026-07-23)

Fixes a fatal crash where a mid-survey adapter drop (controller goes not-ready —
`hciX DOWN`, rfkill, or a controller reset during LE↔BR/EDR alternation) aborted
an entire long-running survey with `Error: Bluetooth adapter not ready…`. Root
cause: `manager.start_discovery()`'s `SetDiscoveryFilter` branch re-raises
`org.bluez.Error.NotReady` (only `UnknownObject`/`NotSupported` are non-fatal),
and the survey loop called the scan rounds unguarded, so the mapped
`NotReadyError` escaped to the CLI catch-all. `dbuslayer/manager.py` is
intentionally **unchanged** — `connect`/`scan_modes` depend on that raise
contract (pinned by `tests/test_discovery_error_surfacing.py`); the fix lives at
the survey call sites, matching their existing `except NotReadyError` precedent.

- **`modes/survey.py`** — the round loop now wraps each transport round in
  `except BLEEPError`, tracks a per-round `productive` flag, and on a
  non-productive round (adapter not ready) surfaces a warning, paces the loop via
  `_interruptible_sleep()` (≤1s slices honouring SIGINT/SIGTERM) so a fast-failing
  round cannot busy-loop, and continues. A dropped adapter now yields a graceful
  exit `0` with a partial census plus a prominent final "N/M round(s) skipped"
  warning and remediation hints, instead of a crash. The `--live` health label is
  now derived from the round outcome (`BlueZ: adapter not ready` vs `BlueZ: OK`)
  rather than merely whether the monitor thread started.
- **`modes/survey.py`** — `_run_classic_round()` now raises `NotReadyError` when
  the adapter is not ready (was a silent `[]`), so the loop can distinguish
  "adapter down" from "ready but zero devices" and pace/recover correctly. A
  dedicated `except NotReadyError: raise` guards it from the function's broad
  handler. (Private to survey — no external callers.)
- **`--auto-recover`** (`cli/parsers/survey.py`, default **off**): on a
  non-productive round, attempt a bounded (≤3) in-run recovery via the existing
  `system_dbus__bluez_adapter.set_powered(True)` → `power_cycle()` helpers, then
  resume — an opt-in analogue to Ubuntu's `AutoEnable`. Off by default to honour
  the non-goal of never mutating host BT state without an explicit command.
- **`modes/debug_survey.py`** — the debug-shell background worker (a duplicate
  loop) received the identical resilience treatment, using
  `survey_stop_event.wait()` for interruptible pacing, plus `--auto-recover`
  threaded through `cmd_survey`. Prevents an unguarded `NotReadyError` from
  silently killing the daemon worker thread. (Coexists with the SR-G1
  `--checkpoint-interval` support added to the same worker below.)
- Tests: `tests/test_survey.py` (`TestAdapterDropResilience`,
  `TestClassicRoundNotReady`, `TestAutoRecover`,
  `TestDebugSurveyWorkerResilience`) — LE not-ready survived with rc 0, pacing
  engaged, classic-round raises, `--auto-recover` resumes, debug worker survives.
  Live-validated on real `hci0` (drop/restore, sustained outage pacing, and
  `--auto-recover` power-cycle).

### Documentation-fidelity pass + SR-G1-FollowUp debug-shell checkpoint fix (2026-07-23)

**Code fix (SR-G1-FollowUp / D3): debug-shell `survey` now honours
`--checkpoint-interval`.** The debug shell parsed the flag but silently dropped
it — `cmd_survey` never forwarded `opts.checkpoint_interval` and `_survey_worker`
had no such parameter, so SR-G1 census checkpointing never ran in Debug Mode (a
long debug survey that hard-crashed lost the whole aggregated census; only the
CLI `bleep survey` path honoured it).

- **`bleep/modes/debug_survey.py`**: added a `checkpoint_interval` parameter to
  `_survey_worker`, forwarded `opts.checkpoint_interval` from `cmd_survey`, and
  reused the CLI's shared `survey._write_survey_checkpoint()` / `.partial`
  atomic-write logic in the debug round loop (guarded on `output` set and
  interval > 0). A small `_ProgressShim` routes the checkpoint's `emit_progress`
  line to `print_and_log` (the debug shell has no `OutputContext`). The worker
  now also removes the stale `.partial` after its clean final write, matching the
  CLI. No atomic-write logic was duplicated.
- **Tests**: `tests/test_survey_checkpoint_sr_g1.py` gained
  `TestDebugSurveyCheckpointing` — mid-run checkpoints fire and `.partial` is
  cleaned up after a clean run, and interval `0` stays a no-op. **7 SR-G1 tests
  pass.**
- **Docs**: `survey_mode.md` updated — the `--checkpoint-interval` row, the
  Census Checkpointing section, and the Debug Shell Integration section now state
  the flag works in **both** the CLI and the debug shell (the earlier "CLI only"
  caveat removed). `todo_tracker.md` `SR-G1-FollowUp` flipped to RESOLVED.

**Documentation-fidelity sweep (P0–P3).** A comprehensive audit aligned the
internal docs with the current codebase (no runtime code changed by this part):

- **Version/schema truth-up**: `api_specification.md` (Schema Version → 17,
  re-export count → 20, corrected `passive_scan` / classic-enumerate /
  `query_hci_version` / `maintain_database` signatures, LE-enumerate 4-tuple
  return, mode entry points), `device_type_classification.md` (schema → v17;
  GATT-services-resolved moved to *Strong* evidence to match code weighting).
- **CLI/API sync**: `cli_usage.md` gained a Global-flags section and 8 missing
  subcommands (`monitor`, `advertise`, `gatt-server`, `device-sets`, `mesh`,
  `classic-rfcomm`, `network-enum`, `audio-config`) + `db maintain`;
  `gatt_enumeration.md` dropped the removed `--controlled` flag.
- **AoI / media / survey docs** corrected to match the shipped
  implementations (AoI flags + report `reports/` path; media-enum/-ctrl flag &
  action tables and JSON output shape; AoI security two-branch char rules,
  weak-PIN rule, SR-N1 pairing analysis, nested `services_mapping`).
- **Network capability docs**: Phase 5 marked complete; stubbed examples
  replaced with shipped `find_network_devices` / `network_roles_from_uuids` APIs.
- **Agent/pairing D-Bus (D1)**: the "methods not registered / empty
  introspection XML" finding was confirmed a **misdiagnosis** (a process
  introspecting its own bus object + wrong service name); agent registration and
  `org.bluez.Agent1` dispatch work end-to-end (running-MainLoop fix, v2.6.2),
  re-confirmed live. The 8 historical investigation docs were archived with
  banners pointing to `agent_pairing_flow_analysis.md`.
- **Tracker hygiene**: `bl_classic_mode.md` §6/§7 completed "Temporary" trackers
  removed per their own note; the bc-01…bc-11 foundational-task record was
  migrated into `todo_tracker.md` so no history was lost.

### Audio follow-ups — GStreamer codec-plugin preflight + HFP/HSP microphone capture (2026-07-22)

Two follow-ups to the A2DP capture work below: proactive codec-plugin visibility
in preflight, and a new voice-capture path for HFP/HSP microphones.

- **GStreamer codec-plugin preflight** (`core/preflight.py`): `bleep --check-env`
  and `--diagnose-audio` now report which codec pipelines are actually usable,
  not just whether GStreamer is installed. `_check_gstreamer_codec_plugins()`
  probes the element factories each pipeline needs (`rtpsbcdepay`/`sbcparse`/
  `sbcdec` for SBC capture, `avenc_sbc` for playback, MP3/AAC groups, and the
  shared `appsrc`/`wavenc`/… core), grouped by capability so the summary names
  the **specific missing element** and an OS-specific install hint. This closes
  the silent-failure footgun where SBC capture failed at runtime because
  `gstreamer1.0-plugins-bad` was absent. New `PreflightReport.codec_plugins`
  field + `can_record_sbc` property. Tests: `tests/test_preflight.py`
  (`TestGstreamerCodecPlugins`, 6 new).
- **HFP/HSP microphone capture** (`ble_ops/audio/audio_system.py`,
  `audio-record --hfp`): A2DP is output-only; the remote **microphone** is only
  exposed as a SCO source when the device's card is on an HFP/HSP profile. New
  `system_record_hfp()` switches the card to a headset/hands-free profile
  (`handsfree-head-unit` / `headset-head-unit`), records the SCO source via the
  host audio tools, then **restores the original profile** (override with
  `--keep-profile`). BlueALSA SCO source PCMs are addressed directly (no switch).
  Voice-grade capture, distinct from the A2DP music path.
  - **Live E2E PASS** (PLT V8200 Series, PipeWire): `audio-record <MAC> --hfp`
    switched `a2dp-sink-sbc` → `headset-head-unit`, recorded
    `bluez_input.…headset-head-unit`, produced a valid WAV (5.93 s, real mic
    audio), and **restored** the card to `a2dp-sink-sbc`, exit `rc=0`.
  - Tests: `tests/test_audio_hfp_capture.py` (18 new — profile predicate,
    BlueALSA SCO resolution, switch/record/restore, already-HFP no-switch,
    no-HFP-profile rejection, restore-on-failure, `--keep-profile`).
- Full `tests/` suite: **1407 passed, 27 skipped**.

### A2DP audio capture (`audio-record`) — record-via-codec path made functional + live E2E from a remote source (2026-07-22)

Completed the codebase-gap item **G-2.2** and closed the audio record/decode path
end-to-end, culminating in the first successful **live** capture from a remote A2DP
**source** (a Windows desktop streaming to this host). All fixes below were validated
against real BlueZ; the deterministic pieces are covered by unit/integration tests.

- **Record-via-codec decode path implemented** (`ble_ops/audio/audio_codec.py`):
  `_decode_with_python_bindings()` was a placeholder that never fed the transport FD
  into GStreamer. Added a `GLib.io_add_watch` feeder built on the new
  `_pump_fd_to_sink()` helper (drain-first semantics: read available data before
  honouring `HUP`/`ERR`, so the final chunk is never dropped). `decode_audio_stream()`
  and `MediaStreamManager.record_audio()` now honour `--duration`.
- **RTP encapsulation handled**: BlueZ A2DP transport FDs carry RTP-encapsulated SBC,
  not raw frames. The SBC decode pipeline now prepends `rtpsbcdepay` with
  `application/x-rtp` caps, and `_sbc_rtp_clock_rate()` derives the RTP clock-rate from
  the negotiated SBC configuration (threaded from `media_stream.py`).
- **Latent decode bugs fixed**: GStreamer bus handler arity (`bus_message(bus, message)`)
  that had silently dropped EOS/ERROR and hung the mainloop; stale `mp3parse` →
  `mpegaudioparse`.
- **`Media1.RegisterEndpoint` object-path marshalling** (`dbuslayer/media.py`):
  the endpoint path was passed as a bare `str` (signature `sa{sv}`), which BlueZ rejected
  with `UnknownMethod` (expects `oa{sv}`). Wrapped in `dbus.ObjectPath` for
  register/unregister. Endpoint registration now succeeds live.
- **A2DP source-role connection orchestration** (`dbuslayer/media_stream.py`):
  `_cycle_device_connection()` does `Device1.Disconnect()` → `Connect()` to force
  `a2dp_discover` to re-select BLEEP's SEP. A remote A2DP **source** must originate the
  link itself, so the Linux-initiated `Connect()` is refused
  (`br-connection-create-socket` / `br-connection-unknown`). The cycle now catches the
  connection-family error (`_REMOTE_INITIATE_ERROR_HINTS`) and enters a **wait-for-
  remote-initiated-reconnect** mode (up to `_REMOTE_RECONNECT_TIMEOUT` = 30 s) instead of
  aborting. Non-connection DBus errors still propagate; the sink path (headphones/
  speakers) is unchanged (10 s wait). Additive by design.
- **`--system` capture on PipeWire hosts** (`ble_ops/audio/audio_tools.py`):
  `get_sources_and_sinks_for_card_profile()` relied on `pacmd`, which PipeWire's
  PulseAudio shim does not implement, breaking `--system` play/record. Added a `pactl`
  fallback that associates sinks/sources by MAC when the `pacmd` block is empty.
- **`core/log.py` hardening**: a prior `sudo bleep` run could leave root-owned legacy
  symlinks in `/tmp`; the cleanup `unlink()`/`touch()` then raised `PermissionError` and
  crashed **every** `bleep` import. Legacy-path bookkeeping is now fully non-fatal.
- **Live E2E PASS** (DESKTOP-1APRSIB A2DP source, PipeWire paused): observed
  `Connect()` refused → remote-reconnect wait → source re-initiated →
  `SetConfiguration transport=…/fd7` → transport acquired (`fd=18`, MTU 672) → SBC/RTP
  decode → **2.6 MB WAV, RIFF 16-bit stereo 44.1 kHz, 15.13 s, RMS 4984 / peak 31905**
  (real audio), exit `rc=0`.
- **Tests:** `tests/test_audio_codec_pump.py` (drain-first pump), deterministic
  SBC-over-RTP loopback + `_sbc_rtp_clock_rate` in
  `tests/test_audio_codec_decode_integration.py`, `RegisterEndpoint` marshalling +
  4 `_cycle_device_connection` reconnect-semantics tests in `tests/test_media_helpers.py`,
  and `--system` PipeWire fallback ("Fix 6") in `tests/test_audio_regressions.py`.
  Full `tests/` suite: **1383 passed, 27 skipped**.

### Survey→AoI live-run fixes — SR-N1: DB SDP/pairing surfaced to analysis (2026-07-22)

Accepted **SR-N1** of the `docs/todo_tracker.md` "Survey → AoI live-run findings"
plan. A manually-executed 4-hour survey → AoI run showed that every Classic/dual
device analysed **from the observation DB** scored `0/10` with no SDP or pairing
findings — even one exposing OBEX/PBAP and bonded with PIN `0000`.

- **Root cause:** `get_device_detail()` returns Classic data under `sdp_records`
  / `classic_services` / `pairing_events`, but `analyse_device()` only reads
  `sdp_summary` / `pairing_profile`, and `_hydrate_db_device_data()` never
  bridged the two — so DB-sourced Classic evidence was silently dropped.
- **Fix (`analysis/aoi_analyser.py`):**
  - `_hydrate_db_device_data()` now maps `sdp_records` (falling back to
    `classic_services`) → `sdp_summary`, and the latest `pairing_events` row →
    `pairing_profile` via the new `_pairing_event_to_profile()` helper (parses
    `post_pair_state` for `fully_bonded`). Additive only — never overrides a key
    live/file-sourced data already set.
  - `_analyse_pairing_profile()` flags **default/weak pairing PINs** (`0000`,
    `1234`, all-same-digit, or numeric length < 6) as a medium concern via the
    new `_is_weak_pin()` helper, and returns the observed PIN for the report.
  - `_assign_concern_risk()` classifies weak/default-PIN reasons as **medium**.
  - `_analyse_sdp_records()` hardened against NULL SDP record names.
- **Effect (verified live):** `14:89:FD:31:8A:7E` (PhreakMe-Blue) now reports
  **6/10** with an SDP Discovery section (PBAP/OPP/HFP/HSP/BT-DIAG), a Pairing
  Profile section, and 3 medium concerns (2 exposed Classic profiles + default
  PIN). LE-only and data-less devices are unaffected (still 0/10).
- **Tests (`tests/test_aoi_sr_n1_db_hydration.py`, 9 new):** hydrator mapping,
  no-override guard, pairing derivation (incl. malformed JSON), classic-profile
  + PIN flagging from DB-shaped data, weak-PIN table, and a clean-device=0/10
  regression. Full `tests/` suite: **1320 passed, 27 skipped**.

### Survey→AoI live-run fixes — SR-N3: LE enum honours --timeout, caps dual attempts (2026-07-22)

Accepted **SR-N3**. The AoI `--timeout` never reached the LE connect path, and
seeded ``dual`` targets burnt all 3 LE attempts (≈3×`br-connection-page-timeout`,
~80 s) before SDP even started.

- **`EnumerationController.enumerate()`** now accepts keyword-only `timeout` and
  `max_attempts`. In `passive` (base-connect) mode `timeout` is forwarded as
  `timeout_connect` / `timeout_services` to
  `connect_and_enumerate__bluetooth__low_energy`; `max_attempts` overrides the
  per-call retry-loop bound (defaults to the class `MAX_ATTEMPTS=3`). Variant
  modes (naggy/pokey/brute) run their own timing and ignore `timeout`.
- **`modes/aoi.py::_scan_target`** passes the resolved `--timeout` and caps
  seeded ``dual`` targets to a single LE attempt before falling through to SDP
  (the Classic half will not answer an LE connect). Pure `le`/`unknown` keep the
  full 3-attempt retry budget.
- **CLI help:** `aoi --timeout` help clarifies it bounds the LE connect phase too.
- **Tests (`tests/test_enum_controller_sr_n3.py`, 5 new):** timeout forwarded /
  omitted-by-default; `max_attempts` caps the loop; default uses `MAX_ATTEMPTS`;
  AoI dual target → `max_attempts=1`. Full suite **1325 passed, 27 skipped**.

### Survey→AoI live-run fixes — SR-G2: `aoi scan --analyze` (2026-07-22)

Accepted **SR-G2**. Added an opt-in `--analyze` flag to the `aoi` parser
(`cli/parsers/aoi.py`, `dest=analyze_inline`). When set, the scan command
(`modes/aoi.py::_run_impl`) runs `AOIAnalyser.analyse_device()` on each target
immediately after persisting it — so a single `bleep aoi scan targets.json
--analyze` produces analysis/reports without a separate analyze pass. Analyses
whatever was persisted (including Classic SDP/pairing), not only LE-successful
targets. Default off — existing scan behaviour unchanged. CLI help updated.
2 new tests in `tests/test_aoi_database_integration.py`; full suite **1327
passed, 27 skipped**.

### Survey→AoI live-run fixes — SR-G1: survey census checkpointing (2026-07-22)

Accepted **SR-G1**. `survey` wrote its census only once (at the end); a late
crash lost the whole in-memory census/RSSI aggregation (DB rows survived, the
formatted census did not).

- **`cli/parsers/survey.py`:** new `--checkpoint-interval N` (seconds, default
  `0` = off; requires `-o/--output`).
- **`modes/survey.py`:** the round loop now writes the partial census to
  `<output>.partial` every N seconds via `_write_survey_checkpoint()` (atomic
  temp-file + `os.replace`); the stale `.partial` is removed after the clean
  final write. Filtering/formatting is shared with the final write through the
  new `_format_survey_output()` helper (DRY). Checkpoint failures are logged and
  swallowed so a bad write never aborts a run. Graceful SIGINT/SIGTERM already
  fall through to the normal final write, so this specifically hardens against
  hard crashes.
- **Tests (`tests/test_survey_checkpoint_sr_g1.py`, 5 new):** atomic partial
  write, no-op without `-o`, format parity, an end-to-end run that leaves no
  stale `.partial`, and parser default/parse. Full suite **1332 passed, 27
  skipped**.

### Survey→AoI live-run fixes — SR-N4: exclude seeded test fixtures from list/report (2026-07-22)

Accepted **SR-N4**. Seeded test-fixture MACs (`AA:BB:CC:DD:EE:*`,
`11:22:33:44:55:66`, all-zero) leaked into a real DB and polluted the aggregate
report ("Devices Analyzed: 47") while diluting the average risk score.

- **`analysis/aoi_analyser.py`:** new `_is_synthetic_mac()` helper (narrow set —
  never matches a legitimate random/private RPA). `list_devices()` gained
  `include_synthetic=False` and excludes those MACs by default. Filtering lives
  **only** in `list_devices()`, so direct-address callers
  (`generate_aggregate_report([...])`, `analyse_device(mac, …)`) are unaffected.
- **CLI:** `aoi --include-synthetic` restores them for `list` / `report --all`.
- **Tests (`tests/test_aoi_synthetic_filter_sr_n4.py`, 4 new):** fixture
  detection, real-MAC negatives, default-exclude / include-synthetic round-trip,
  explicit-address aggregate still renders synthetic. Full suite **1336 passed,
  27 skipped**.

### Survey→AoI live-run fixes — SR-N5: concern UUID/handle + de-dup in renders (2026-07-22)

Accepted **SR-N5**. Rendered concerns dropped the characteristic UUID/handle and
repeated identical lines (e.g. 21× "Custom characteristic accepts
write-without-response" with no identifier).

- **`analysis/aoi_analyser.py`:** new `_dedup_concerns()` collapses identical
  `(name, description, risk)` findings and collects the distinct char
  identifiers (`uuid` or `uuid#handle`, de-duped, order-preserving);
  `_concern_id_suffix()` renders `[`uuid`]` for singletons or
  `(×N: id1, id2, …)` for groups. Both markdown and text vulnerability sections
  use them. The **JSON** report is unchanged (keeps the full per-UUID list).
- **Tests (`tests/test_aoi_concern_render_sr_n5.py`, 7 new):** grouping + id
  collection, handle formatting, device-level (no-uuid) concerns, distinct
  concerns not merged, markdown/text include UUID + `×N`, JSON not collapsed.
  Full suite **1343 passed, 27 skipped**.

### Survey→AoI live-run fixes — SR-N2/SR-G4/SR-C4 (2026-07-22)

Accepted the remaining Survey→AoI items.

- **SR-N2 — pre-enum refresh scan.** New `aoi --refresh-scan SECS` (default 0 =
  off). When set, `modes/aoi.py` runs a `SECS`-second `passive_scan()` before the
  target loop to repopulate BlueZ's object cache, mitigating rotated-RPA
  staleness when AoI runs hours after a passive survey. Implemented as an
  explicit-value int (not `nargs='?'`) to avoid argparse consuming a following
  positional on the flat `aoi` parser.
- **SR-G4 — actionable empty aggregate.** `report --all` under `--db-only` with
  no analysed rows now checks for scanned-but-unanalysed devices and prints a
  clear next step (`bleep aoi analyze …` / `aoi scan … --analyze`) instead of a
  silent empty report; still returns non-zero.
- **SR-C4 — docs.** `observation_db_schema.md` documents that a `-`/NULL
  `rssi_max` means no RSSI was ever observed (typically a bonded/cached device),
  not an error.
- **Tests:** 3 new CLI tests (`tests/test_aoi_database_integration.py`) for
  `--refresh-scan` on/off and the SR-G4 warning.

### AoI risk-score redesign — Batch 5 (F5) (2026-07-16)

Accepted **Batch 5** (F5) of the `docs/todo_tracker.md` AoI plan, implemented as
**option (a)** (baseline-0 additive integer weights) per explicit user sign-off on
the acceptance-gated scale decision.

- **F5 — risk score (`analysis/aoi_analyser.py:_calculate_security_score`):** a
  fully clean device now scores **0/10** instead of the misleading 5/10. The
  baseline-5 + fractional-weights + `int()`-truncation model (effective range
  5–10) is replaced by exact integer severity weights: `score = min(10, high×3 +
  medium×2 + low×1)`. "Higher = more risk" labels are unchanged and now accurate
  across the full 0–10 range. No schema change; the informational
  `notable_services`/`unusual_characteristics` lists (F8) still don't feed the
  score.
- **Tests (`tests/test_data_pipeline_fixes.py`):** rewrote the pinned
  `TestCalculateSecurityScore` assertions for the new scale (clean=0, high=3,
  medium=2, low=1, 2 high+1 medium=8, cap 10) and added an explicit
  medium/low-weight test. `avg_security_score` remains a float (rounded mean),
  so that assertion is unaffected.
- **Docs:** rewrote the `aoi_security_algorithms.md` "Security Score" section
  (formula, worked examples, and a history note on the prior model).

### AoI docs drift + analysis history — Batch 4 (F10, F7) (2026-07-16)

Accepted **Batch 4** of the `docs/todo_tracker.md` AoI plan. F10 is docs-only; F7
was implemented as **option (a)** (analysis history table + migration) per explicit
user sign-off on the schema-gated decision. Full suite green with new tests.

- **F10 — documentation drift (docs-only):** corrected `aoi_implementation.md`'s
  CLI-parser path (was `bleep/cli.py`; now `bleep/cli/parsers/aoi.py` +
  `bleep/cli/dispatch.py`, reflecting the F3 consolidation), documented the
  read-only `report` path and the `db` subcommand, and refreshed
  `aoi_mode.md`'s Service/Characteristic/SDP feature descriptions to match the
  Batch 3 (F8/F9) behavior. (F6 pairing note and F1 functional landmine/permission
  analysis were already reflected from earlier batches.)
- **F7 — AoI analysis history (schema v16→v17):** `store_aoi_analysis()` now keeps
  `aoi_analysis` as the single latest row per device (**unchanged** semantics —
  `get_aoi_analysis`/`has_aoi_analysis` and the existing update test are
  untouched) **and** appends a timestamped row to a new append-only
  `aoi_analysis_history` table so re-scans can be compared over time. New public
  API `get_aoi_analysis_history(mac, limit=None)` returns history newest-first.
  The v16→v17 migration creates the table (`IF NOT EXISTS`) and backfills the
  existing latest row as the first history entry (non-destructive). Added 5
  regression tests (empty/ordering/latest-preservation/limit/migration-backfill)
  and bumped the `_SCHEMA_VERSION` assertion 16→17.

### AoI notable-service / SDP enrichment — Batch 3 (F8, F9) (2026-07-16)

Accepted **Batch 3** (F8 + F9) of the `docs/todo_tracker.md` AoI plan — additive,
F5-independent analysis enrichment. `1305 passed, 27 skipped` (full suite, zero
regressions); `549 passed` across the AoI + SDP-analyzer suites with 8 new tests.

- **F8 — notable-service detection (`analysis/aoi_analyser.py`):** added a curated
  `_OTA_DFU_SERVICE_UUIDS` set (Nordic Legacy/Secure/Buttonless DFU, TI OAD,
  Silicon Labs OTA, MCUmgr SMP) and a `_canonical_uuid()` normaliser so vendor
  firmware-update services with **custom 128-bit UUIDs and no SIG name** are now
  flagged notable (with the vendor label). The name heuristic now also matches
  "firmware" ("OTA" stays a case-sensitive acronym to avoid "toyota"-style false
  positives; "dfu" remains case-insensitive).
- **F8 — unusual-characteristic heuristics:** replaced the arbitrary
  "`len(properties) > 3` and `write`+`notify`" rule (which was also
  case-sensitive against the raw property list) with a case-insensitive
  **writable + notify/indicate** (bidirectional control channel) rule, and
  tightened the long-value rule to hex-like strings > 40 chars (≈20 bytes). These
  feed the informational `unusual_characteristics` list only — **not** the score.
- **F9 — SDP enrichment (`analysis/aoi_analyser.py`):** `_analyse_sdp_records`
  now routes records through the comprehensive `SDPAnalyzer.analyze()` and
  surfaces `protocols`, `rfcomm_channels`, `anomalies`, and an
  `inferred_spec_version` hint, **preserving** the existing `raw_count` /
  `services_found` / `security_flags` output. The enrichment is wrapped in a
  guard (falls back to the shallow summary on any analyzer error) and is rendered
  in the markdown/text report SDP sections. No new scored concerns are created
  (anomalies are informational; the authoritative LMP↔SDP cross-validation
  concern remains separate).
- **Score safety:** neither item adds `security_concerns`, so `security_score` /
  `avg_security_score` are unchanged — F5-independent, as required by the plan.
- **Docs:** `aoi_security_algorithms.md` updated (notable-service rules, refined
  unusual rules, new SDP-record analysis subsection).

### AoI parser consolidation — Batch 2 (F3) (2026-07-16)

Accepted **Batch 2** (F3) of the `docs/todo_tracker.md` AoI plan: eliminate the
two divergent AoI argument parsers. There were previously a flat production
parser (`cli/parsers/aoi.py`, used by `bleep aoi …`) and a *separate* nested
sub-parser (`modes/aoi.py:_arg_parser`, used only by the standalone `main()` and
its tests) — duplicated definitions that had already drifted (the production one
was missing the `--timeout`/`--format` defaults later fixed in Batch 1). The
suite validated the non-production parser. `1296 passed, 27 skipped` (full suite,
zero regressions).

- **Single source of truth — `cli/parsers/aoi.py`:** extracted the canonical flag/
  positional set into `_add_aoi_arguments(parser)` and the subcommand resolution
  into `apply_aoi_subcommand(args)` (returns whether an explicit subcommand was
  matched). `register()` now calls `_add_aoi_arguments`. This mirrors the accepted
  survey dedup pattern (`_add_survey_arguments`).
- **`cli/dispatch.py`:** the inline subcommand-extraction block was replaced with a
  call to `apply_aoi_subcommand`; the "no files/subcommand" error path is preserved
  exactly (explicit-but-empty subcommands still fall through to `_run_impl`, only a
  bare `aoi` with no args errors at dispatch).
- **`modes/aoi.py`:** the ~70-line nested `_arg_parser()` was **deleted**; the
  standalone `main()` now builds from the same `_add_aoi_arguments` + resolves via
  `apply_aoi_subcommand`, so `python -m bleep.modes.aoi …` and `bleep aoi …` can
  never diverge again. The now-orphaned `_DEF_WAIT` constant was removed.
- **Latent export bug fixed:** `_run_impl` export used `os.makedirs(args.output)`;
  the production flat parser has always passed `--output=None` here (the deleted
  nested parser's `default="."` only masked it for the standalone path), so a bare
  `aoi export` would have crashed. `output_dir = args.output or "."` now applies in
  the one canonical place for both entry points.
- **Tests — `tests/test_aoi_augmentation.py`:** `TestArgParser` was repointed from
  the deleted `_arg_parser()` to the canonical `_add_aoi_arguments` +
  `apply_aoi_subcommand` path (so it validates the parser the runtime actually
  uses), with added coverage for implicit-scan and the `--format` default. The
  `main()`-driven db/scan tests (`test_aoi_mode_db_commands.py`,
  `test_aoi_database_integration.py`) pass unchanged.

> **Note on approach.** The plan's *preferred* wording was "route the real CLI
> through the subparser-based `_arg_parser()` and delete the flat parser." That
> direction was **rejected as detrimental**: the flat parser backs documented
> integrated-CLI behaviour (`bleep aoi targets.json` implicit scan, `aoi --file …`)
> that strict nested subparsers would break, and `main()` is the tested standalone
> entry. Consolidating onto the flat parser achieves the same single-source-of-truth
> goal with zero behaviour change.

### AoI analysis/reporting hardening — Batch 1 (F1, F2, F4, F6) (2026-07-16)

Accepted **Batch 1** of the `docs/todo_tracker.md` "AoI Analysis & Reporting —
deep review findings F1–F10" plan. All four items are additive/isolated and
provably non-regressive; `510 passed` across the AoI + data-pipeline + api-surface
suites, with new regression tests for each finding.

- **F1 — `analysis/aoi_analyser.py`:** new `AOIAnalyser._normalize_security_map()`
  reads **both** the flat `{uuid: status}` contract and the nested
  `{obj_type: {issue_type: [uuid, …]}}` shape that live GATT enumeration actually
  emits (see `dbuslayer/device_le.py`). `_analyse_landmine_map`/
  `_analyse_permission_map` route through it; the `accessibility` summary keys and
  the float `accessibility_score` are preserved (consumed by `debug_aoi.py` and
  recommendations). Fixes nonsense per-UUID analysis when maps were populated.
- **F2 — `cli/parsers/aoi.py`:** `--timeout` now `type=int, default=30` and
  `--format` `default="markdown"`. Previously the production parser left both as
  `None`, so `None` reached SDP/pairing timeouts ("wait forever") and aggregate
  markdown reports were mislabelled `.txt`.
- **F4 — `analysis/aoi_analyser.py`:** `analyse_device`/`analyze_device_data` gained
  a keyword-only `persist: bool = True`; `generate_report` and
  `generate_aggregate_report` pass `persist=False`. Rendering a report for an
  un-analysed device no longer persists analysis to the DB as a side effect.
- **F6 — `modes/aoi.py`:** pairing in `_scan_target` is gated **strictly** behind
  `--deep`. The annotation-triggered pairing path and the now-unused
  `_has_auth_annotation()` were removed; a plain scan is non-invasive and never
  creates a bond. Documented in `aoi_mode.md`. Auth findings still recorded via
  enumeration annotations.
- **Test housekeeping (pre-existing drift, confirmed on a clean tree):** removed the
  obsolete `_normalise_service_element` tests (function removed by the earlier A–E
  work) and corrected the schema-version assertion `15`→`16` to match
  `_SCHEMA_VERSION` (the test pre-dated the v15→v16 bump).

### Survey Classic-round dual-device fix (2026-07-16)

Fixes an independent Classic-round classification issue surfaced by the Step-3
OS #2 evidence packet (`docs/todo_tracker.md`): the BR/EDR inquiry round kept
only devices typed exactly `"br/edr"`, silently **dropping dual-mode devices**
(a Classic-capable device that also advertises LE — e.g. an audio headset).

- **`modes/survey.py` `_run_classic_round`:** the round filter now keeps
  `type in ("br/edr", "dual")` (previously `== "br/edr"`), while still excluding
  `le`/`unknown` so LE-only devices cached from a prior round are not miscounted
  as Classic sightings. DB persistence now derives `device_type` from the actual
  transport (`br/edr`→`classic`, `dual`→`dual`) via `_CLASSIFIER_TYPE_MAP` instead
  of hardcoding `"classic"` — the hardcoded value bypassed `upsert_device`'s
  "preserve dual" merge and **downgraded** dual devices to `classic`.
- **Effect:** a `--transport bredr` survey no longer under-reports Classic-capable
  devices; `--transport both` is unchanged (superset preserved). No new BlueZ
  interaction code; census classification (`_resolve_device_type`) already handled
  `dual` correctly.
- **Live-verified on BlueZ 5.84 (Kali):** `bredr-only` now returns the discoverable
  headsets (`PLT V8200`, `Pro PSP1806`) — previously `0`; `both` unchanged at 5
  devices with both headsets typed `dual`; DB stores both as `device_type=dual`
  (no downgrade). Existing `tests/test_survey.py` (90) pass with no regression.
- **Tests (CI-safe, planned for the canonical suite):** mock-adapter round where
  `get_discovered_devices` returns a `dual` + an `le` device → assert the `dual`
  is kept and the `le` dropped, `merge_classic_results` keeps it `dual`, and the
  persisted `device_type` is `dual` (not `classic`).

### Step-3 — LE↔Classic discovery diagnosability: error surfacing (2026-07-16)

Accepted **first deliverable** of the `docs/todo_tracker.md` "Step-3" plan,
following the OS/BlueZ #1 (5.84) and #2 (5.64 + cross-client contention) evidence
packets. Version-independent, additive, behaviour-preserving: previously
swallowed discovery-call failures are now surfaced instead of hidden at DEBUG.
**No happy-path timing or return values change**, and the reverted
`Discovering`-settle guard (`bb4cde3`) is **not** reinstated.

- **`dbuslayer/adapter.py`** — new `_note_discovery_error()` helper wired into
  `run_scan__timed` (`StartDiscovery`), `_discovery_timeout` (`StopDiscovery`),
  and `set_discovery_filter`. On failure it logs a WARNING with the exact D-Bus
  error name + current `Discovering` state and records the failure on
  `self._last_discovery_error`. Return values and control flow are unchanged
  (the prior `logger.debug` was invisible at the INFO root level).
- **`dbuslayer/manager.py`** — matching `_note_discovery_error()` helper wired
  into `start_discovery` (degraded `InProgress`/`WrongState`/`NotFound` no-op
  **and** the hard-error raise path), `stop_discovery`, and the optional-
  `SetDiscoveryFilter` branch. Emits a real `LOG__GENERAL` warning + records
  `_last_discovery_error`; graceful-degrade and raise semantics are preserved.
  This captures the cross-client `org.bluez.Error.Failed: No discovery started`
  that the OS #2 contention evidence proved is otherwise silent.
- **Tests:** `tests/test_discovery_error_surfacing.py` — 9 CI-safe unit tests
  (no hardware; objects built with `object.__new__` + injected fakes) asserting
  each site surfaces the error (name + `Discovering` state, via
  `_last_discovery_error` and the emitted warning) and that happy-path returns
  are unchanged; covers DBus and non-DBus exceptions, degrade vs. raise, and the
  filter-unavailable branch.
- **Live-verification (gate 5, CLOSED on both builds):** the documented
  re-verification procedure passed identically on **BlueZ 5.84** (Kali 6.12.20)
  and **BlueZ 5.64** (Ubuntu 22.04) — 12/12 method-level surfacing checks
  (`InvalidArguments` / `Failed: No discovery started` / `InProgress`, plus the
  two manager degrade lines), a clean `both`-transport survey (`rc=0`, **0**
  false-positive discovery warnings), and on-disk persistence in
  `general.log`. Error names/messages were byte-for-byte identical across builds.
- **Docs:** `docs/survey_mode.md` gains a "Discovery Error Surfacing (diagnostics)"
  section describing the surfaced warning, the `_last_discovery_error` record, and
  the cross-client-contention rationale; `docs/todo_tracker.md` "Step-3" records
  both live-re-verification packets and closes gate 5. The bounded own-session
  settle/retry (second deliverable) stays deferred — no build reproduces the race.

### Survey arg dedup + AoI data-pipeline hardening (2026-07-15)

Accepted work from the `docs/todo_tracker.md` "Survey arg dedup + AoI
data-pipeline hardening" plan (task **#3** + AoI items **A–F**). All changes are
additive/behaviour-preserving except where noted.

- **#3 — Survey argument dedup:** the survey CLI flag set is now defined once in
  `_add_survey_arguments()` (`cli/parsers/survey.py`) and consumed by all three
  parsers (`cli/parsers/survey.py` `register`, `modes/survey.py` `_build_parser`,
  `modes/debug_survey.py` `cmd_survey`). The debug shell **gains the previously
  missing `--quiet`**; the three parsers now expose an identical attribute set.
  Removed a dead `from math import ceil` import.
- **AoI A+E — characteristic-import fix + single write path:** extracted
  `AOIAnalyser._persist_device_to_db(mac, data)` and routed `save_device_data`
  **and** `aoi db import`/`sync` through it. Fixes a bug where import/sync treated
  the nested `services_mapping` GATT structure as a flat `{char_uuid: svc_uuid}`
  map and **never imported any characteristics** into the DB. Removed the dead
  `_normalise_service_element` helper (its string/dict service-element handling is
  folded into the shared method, preserving the export→sync round-trip).
- **AoI B — `aoi list` device name:** falls back to the nested `device.name` for
  DB-hydrated records (previously showed `Unknown` for DB-sourced devices).
- **AoI C — broader GATT concern detection:** `_analyse_characteristic` now
  resolves an effective name from explicit `name`/`description` fields and flags
  **custom (Unknown-UUID) write-without-response, non-authenticated**
  characteristics as **medium** risk. The three duplicated concern-append sites
  are centralised in `_char_concern_from_report()`. The numeric score and the
  existing high-signal rule are unchanged (avoids alert flooding).
- **AoI D — report label clarity:** the report metric is relabelled from
  "Security Score" to **"Risk Score … (higher = more risk)"** in the markdown,
  text, and aggregate renderers. The numeric computation and JSON keys
  (`security_score`/`avg_security_score`) are unchanged.
- **AoI F — seed AoI device-type from survey/DB:** `aoi scan` now threads the
  survey entry's `device_type` into `_scan_target` as `seeded_type`. A concrete
  live classification always wins; only when the live result is `unknown` is a
  trustworthy seed adopted (explicit hint first, then the DB record via
  `observations.get_device_detail`) — via new pure helpers `_resolve_seeded_type`
  and `_resolve_device_type`. This stops a survey-typed device that is idle at AoI
  time from regressing to `unknown` and from being probed on an irrelevant
  transport. Provenance is recorded as `device_type_source` (`"live"`/`"seed"`).
  Live-verified on real `hci0`: a device the survey typed `le` live-classified
  `unknown` and correctly adopted the `le` seed (LE-enum ran, SDP skipped;
  persisted `device_type=le`, no `unknown` regression).
- **Tests:** added `TestPersistDeviceToDb` (real, isolated-DB regression proving
  nested `services_mapping` characteristics persist, incl. via the `aoi db import`
  command path); removed the obsolete `_normalise_service_element` unit tests and
  repurposed one into a `_persist_device_to_db` dict-service-list test; added
  `TestSeededDeviceType` covering the F seed-resolution matrix and the
  `_scan_target` seed-adoption path.

### Bluetooth Networking (PAN/BNEP) — Phase 4: real-time signals + server authorization (2026-07-13)

Fourth phase of the accepted "Full D-Bus Incorporation" plan
(`docs/todo_tracker.md`). Moves PAN state tracking from polling to events
(gap **G8**, expansion **E5**) and observes inbound clients while hosting
(expansion **E7**), plus a scripted peer harness for two-node testing.

- **`NetworkMonitor`** (`dbuslayer/network.py`) — event-driven watcher for
  `Network1` `PropertiesChanged`. The signal-merge core (`_apply_change`) is
  pure/unit-tested; `prime()` seeds from a one-shot `GetAll`; `wait_for(predicate,
  timeout)` and `run(timeout=…)` drive a GLib loop (SIGINT-clean).
- **Event-driven connect verify (G8):** `NetworkClient.connect()` now confirms
  `Connected` via the signal (`_verify_connected`, default 2 s) and **falls back**
  to the historical single 0.5 s poll if the signal path is unavailable — no
  behaviour change on the success/failure contract.
- **`classic-pan monitor <MAC> [--adapter] [--timeout]`** (E5): live-streams
  `Connected`/`Interface`/`UUID` changes (no polling), persisting each to the
  observation DB. Ops wrapper `pan.monitor(mac, adapter, timeout, on_change)`.
- **`classic-pan serve --authorize`** (E7): registers a default BlueZ agent
  (`register_pan_agent`) so inbound BNEP clients trigger `AuthorizeService`
  (`server.c` `btd_request_authorization`, `BNEP_SVC_UUID`); BLEEP logs the
  device+service, auto-accepts, runs a GLib loop, and unregisters the agent on
  teardown alongside the server roles.
- **Scripted peer harness** `bleep/scripts/pan_peer.py` — standalone (raw BlueZ
  D-Bus, no BLEEP import) `connect` (PANU client) / `serve` (NAP host) / `monitor`
  peer to run on a second host/adapter. Documented order-of-operations in
  `docs/bl_classic_mode.md` §2.9.4.
- **Tests:** `tests/test_network_pan.py` (+19, 98 total) cover `NetworkMonitor`
  signal-merge/coercion/invalidation, `wait_for` primed fast-path, connect
  event/poll fallback, the authorize-observer accept/reject callback, and the
  peer-harness argparse — all without live D-Bus/GLib.

### Bluetooth Networking (PAN/BNEP) — Phase 3b: multi-role PAN server (2026-07-12)

Server-side hosting round-out (expansion **E2**). Previously `classic-pan serve`
could register a single role and unregister only that one; a crash mid-setup
could strand a registration.

- **`NetworkServer` now tracks `{role: bridge}`** for every role it registers,
  exposes `registered_roles`, and gains **`unregister_all()`** — a best-effort
  teardown that attempts every role even if one fails (returns `{role: error}`).
  `unregister()` drops the role from tracking even when the D-Bus call errors.
- **Ops helpers** in `ble_ops/classic/pan.py`: `register_servers(roles, bridge)`
  returns the live `NetworkServer` for the caller to hold and tear down, and
  **rolls back** any partial registration if a later role fails;
  `unregister_servers(roles)` does out-of-process best-effort removal;
  `PAN_SERVER_ROLES = ("nap", "gn", "panu")` backs `--all`.
- **CLI:** `classic-pan serve`/`unserve` take a **repeatable `--role`** and a new
  **`--all`** flag (host/remove nap+gn+panu). `serve` now guarantees
  `unregister_all()` in a `finally` block on Ctrl-C or error; `unserve` reports
  per-role results and only fails if nothing was removed.
- **Tests:** `tests/test_network_pan.py` (+14, 79 total) cover role/bridge
  tracking, UUID-role normalization, `unregister_all` continuing past failures,
  `register_servers` rollback on partial failure, dedup, and invalid/empty role
  rejection — all with a fake `NetworkServer1` proxy (no live D-Bus).

### Bluetooth Networking (PAN/BNEP) — Phase 3: enumeration + device-class integration (2026-07-12)

Third phase of the accepted "Full D-Bus Incorporation" plan
(`docs/todo_tracker.md`). Makes PAN capability **discoverable** (gaps **G1, G4**;
expansions **E4, E8**) — previously a device's network capability was invisible
outside an explicit `classic-pan` command. Also completed the Phase 0
boundary-doc precursor.

- **Shared enumeration ops** (`ble_ops/classic/pan.py`): `network_roles_from_uuids()`,
  `find_network_servers()`, and `find_network_devices()`. All accept a
  pre-fetched `GetManagedObjects` snapshot (threaded through by callers to avoid
  D-Bus storms in survey mode) and **never raise** — returning `[]` on error.
  `find_network_devices()` reads the `Network1` status straight from the OM
  snapshot (E4-style, no per-device round-trip).
- **Device-class helpers** (additive, mirror the media-capability pattern) on
  `device_classic.py` **and** `device_le.py` (dual-mode): `get_network_roles()`,
  `has_network_uuids()`, `get_network_status()`, `has_network_interface()`,
  `is_network_device()`.
- **`get_device_info()`** gains one **additive** `network` key
  (`{roles, has_interface, status}` or `None`) on both device classes.
  `check_device_type()` is untouched; no existing key changed.
- **New `network-enum` CLI command** (+ `run_network_enum()` dispatch): lists
  adapters with `NetworkServer1` and network-capable devices; `--adapter`,
  `--json`, `--all-devices` flags.
- **Refactor:** `scripts/check_network_capabilities.py` is now a thin wrapper over
  the shared ops (duplicate D-Bus/UUID logic removed). This also **fixed a latent
  bug** in the old script — it lowercased device UUIDs but compared them against
  upper-case keys, so `network_uuids` was always empty; the shared helper matches
  case-insensitively and now correctly reports PANU/NAP/GN.
- **Non-disruption safeguards honoured:** `check_device_type()` unchanged; survey
  snapshot paths don't consume `get_device_info()` (verified — survey uses its own
  `DeviceSighting`); lazy imports (no cycles); helpers falsy-on-error; existing
  `classic-pan` behaviour unchanged.
- **Tests:** `tests/test_network_pan.py` (+12, 65 total) enumerate a fixture
  `GetManagedObjects` covering: adapter with/without `NetworkServer1`, device with
  `Network1` iface but no PAN UUID (live baseline edge case), UUID-only device
  (Alias fallback), non-network device filtering, and adapter path filtering.

### Bluetooth Networking (PAN/BNEP) — Phase 2: connect-path correctness (2026-07-12)

Second phase of the accepted "Full D-Bus Incorporation" plan
(`docs/todo_tracker.md` → "Bluetooth Networking (BlueZ PAN / BNEP)…"). Addresses
gaps **G3, G6, G7** and D-Bus expansions **E1, E3, E6** — making the PAN connect
path robust and consistent with the rest of the codebase.

- **Role fidelity (G6/E6).** `dbuslayer/network.py` gains `normalize_pan_role()`
  and `pan_role_uuid()`. `Network1.Connect` / `NetworkServer1.Register` (and the
  ops layer) now accept both the short role names (`panu`/`nap`/`gn`,
  case-insensitive) **and** the full 128-bit PAN UUIDs BlueZ accepts
  (`profiles/network/connection.c` `get_pan_srv_id`), normalising to the short
  form. Invalid roles raise `InvalidArgumentError` early.
- **Error consistency (G7).** Every bare `RuntimeError`/`ValueError` in
  `network.py` is replaced with the project convention: `map_dbus_error(...)` for
  D-Bus failures, `ConnectionError` for the post-connect BNEP verification, and
  `InvalidArgumentError` for bad roles. All are `BLEEPError` subclasses, so broad
  `except Exception` callers (`run_pan`, `cmd_cpan`) are unaffected.
- **Bond/trust/SDP precheck (G3/E3).** `ble_ops/classic/pan.py::connect` runs an
  advisory, non-fatal precheck: warns when the target is not paired or does not
  advertise a PAN service in its cached SDP (`detect_pan_service` over
  `Device1.UUIDs`), and — opt-in via `--trust` — marks it Trusted. It never
  mutates host state otherwise, so the authoritative connect still surfaces the
  real BlueZ error.
- **ConnectProfile fallback (E1).** When `Network1.Connect` returns
  `NotSupported` (common before bluetoothd has probed the profile), connect now
  retries via `Device1.ConnectProfile(<pan-uuid>)` — which drives BlueZ's SDP
  probe + profile registration (`org.bluez.Device.rst`, `manager.c`) — then polls
  `Network1` for the resulting interface. Disable with `--no-fallback`.
- **CLI.** `classic-pan connect` gains `--trust` and `--no-fallback`, wired
  through `run_pan()`.
- **Tests:** `tests/test_network_pan.py` (+23, 53 total) covers role
  normalisation (short/full-UUID/invalid), `pan_role_uuid`, and `connect()`
  orchestration (normal path, `NotSupported`→fallback, `--no-fallback` re-raise,
  UUID-role normalisation, invalid-role early reject) — all D-Bus-free.

### Bluetooth Networking (PAN/BNEP) — Phase 1: prerequisite preflight (2026-07-12)

First phase of the accepted "Full D-Bus Incorporation" plan for BlueZ networking
(`docs/todo_tracker.md` → "Bluetooth Networking (BlueZ PAN / BNEP)…"). Addresses
gap **G2** (host prerequisites never checked — the #1 cause of silent PAN connect
failures per `docs/pan_connection_analysis.md` §3/§5).

- **`classic-pan connect` / `serve` now run a detect-and-instruct preflight.**
  New `check_pan_prerequisites()` / `PanPrereqReport` / `print_pan_prereq_summary()`
  in `core/preflight.py` probe the prerequisites BlueZ does **not** manage: the
  `bnep` kernel module (`/sys/module/bnep` + `/proc/modules`), a powered adapter
  (reuses `require_adapter`), and — for `serve` — that `--bridge` exists and is a
  bridge (`/sys/class/net/<b>/bridge`) plus IPv4 forwarding
  (`/proc/sys/net/ipv4/ip_forward`, advisory). Cross-validated against
  `workDir/bluez/lib/bnep.h` (BNEP PSM/roles) and `profiles/network/server.c`
  (bridge attach flow).
- **Read-only / non-blocking.** The check never mutates host networking (no
  `modprobe`, bridge creation, or sysctl); it prints actionable remediation steps
  and continues, so existing success paths are byte-for-byte unchanged. New
  `--no-preflight` flag skips it.
- **Tests:** `tests/test_network_pan.py` (30 cases) covers the `/proc`+`/sys`
  probes (monkeypatched, CI-safe), `PanPrereqReport` readiness/blocking/instruction
  logic, `check_pan_prerequisites` composition, and `detect_pan_service` matching.
- **Docs:** `bl_classic_mode.md` §2.9 updated; `todo_tracker.md` planning section
  added (gaps G1–G9, D-Bus expansions E1–E8, phased plan, Future-Work Option B).

### Multi-Target Enumeration Hardening — Round 2, post-retest follow-ups (2026-07-10)

A full re-test of the Round 1 fixes against all in-range targets surfaced five
further items (N5 excluded — a known BLECTF advertising artifact). Each was
cross-validated against BlueZ source before implementation.

- **N1/#7 (P1) — bounded `ENOMEM` back-off on RFCOMM connect.** `classic-connect`
  against the honeypot failed every RFCOMM channel with `[Errno 12] Cannot allocate
  memory`: several channels were opened in rapid succession, exhausting host/
  controller memory. `ble_ops/classic/connect.py::classic_rfccomm_open` now retries
  **only** `ENOMEM` a bounded number of times (`enomem_retries=2`) with linear
  back-off (`enomem_backoff=0.3`), recreating the socket each attempt; every other
  errno raises immediately as before. Validated against `errors.txt:70-74` (ENOMEM =
  "Failed to allocate memory in either host stack or controller"), `src/error.c:163`
  (`ERR_BREDR_CONN_MEMORY_ALLOC`, distinct from permanent classes) and the inter-
  attempt pacing in `tools/rctest.c`. Live: back-off engaged on 3 channels and the
  terminal error changed from `ENOMEM` to the more-informative `EACCES`.
- **N2 (P3) — version-info NOTE distinguishes "requested but failed".**
  `analysis/sdp_analyzer.py::generate_report` gained `version_info_requested`; when
  `--version-info` was supplied but the remote HCI Read Remote Version returned
  nothing (`query_remote_version` → `None`, e.g. the honeypot refused / never ACL-
  connected), the Core-Spec NOTE now reads "remote HCI/LMP version query returned no
  result (device refused / did not ACL-connect)" instead of misleadingly advising the
  user to add a flag they already used. `modes/classic_enum.py` passes the flag.
- **N3 (P3) — `classic-connect` channel-count terminology.** Distinguishes services
  advertising RFCOMM (e.g. 8) from the de-duplicated distinct channels attempted
  (e.g. 5): "8 advertising RFCOMM across 5 distinct channel(s)" and "5 distinct RFCOMM
  channel(s) attempted (from 8 advertising service(s)) — none connectable".
- **N4 (P3) — scan disambiguates resolved-RPA identities (no dedup).** A bonded
  device seen via a resolvable-private address yields a second `Device1` object whose
  path encodes the RPA but whose `Address` is the identity (`org.bluez.Device.rst:226`,
  "Identity Address after pairing"), printing two identical lines. `ble_ops/le/scan.py`
  now appends `[identity; adv/RPA <path-mac>]` when the path MAC differs from the
  resolved `Address`, surfacing the RPA↔identity linkage rather than hiding it.
- **N6 (test) — `classify_gatt_read_error` coverage.** New `tests/test_gatt_error_classifier.py`
  (13 cases): `NotPermitted`+"Not paired"→encryption, write/read variants, `Failed`+
  "ATT error: 0xNN" per-code mapping, unknown-code and bare-`Failed` fallbacks, and
  deferral to `decode_dbus_error`.

**Tests:** new `tests/test_rfcomm_enomem.py` (3) + `tests/test_gatt_error_classifier.py`
(13). Full suite: 1181 passed, 27 skipped, 1 failed (pre-existing
`test_schema_version_is_15` schema drift, unrelated).

### Multi-Target Enumeration Hardening (2026-07-10)

Remediation from a multi-target enumeration campaign (`python3 -m bleep` only; no `bleep-mcp`,
no DB-derived findings) against the `winbt-honeypot` (`98:3B:8F:EF:FE:EC` + LE RPA
`47:23:78:E6:8A:16`), BLECTF (`CC:50:E3:B6:BC:A6`) and a Philips Hue bulb (`F0:98:7D:0A:05:07`).
17 gaps were triaged; each fix was **cross-validated against BlueZ source** (`workDir/bluez/`
v5.83), which corrected 6 original assumptions before any code change. Full detail with
BlueZ line references lives in `docs/todo_tracker.md` (Gate 1/2/3/4). #7 (RFCOMM `ENOMEM`
back-off) and #17 (withdrawn) are **not** part of this change; see tracker.

**P1 — broken features**
- **#1 `hid-info` / `connect-profile` crash.** `cli/dispatch.py` passed
  `bluetooth_adapter=` to `system_dbus__bluez_device__classic(mac, adapter_name)` →
  `TypeError`. Renamed the kwarg to `adapter_name=` at both call sites.
- **#3 `gatt-enum` empty tree reported success.** A connected-but-empty GATT database (the
  tell-tale of a dual-mode device whose GATT lives under an LE RPA, or a Classic-only
  endpoint) now prints a diagnostic hint and returns non-zero (`modes/gatt_enum.py`, new
  `_has_characteristics` handles both live and canonical mapping shapes).

**P2 — wrong / misleading results**
- **#4 Auth/encryption GATT reads mis-/un-classified — BlueZ-accurate rewrite.** Added
  `RESULT_ERR_INSUFFICIENT_ENCRYPTION = 41` (`bt_ref/constants.py`) and a single canonical
  classifier `core/error_handling.py::classify_gatt_read_error` that is message-aware:
  `org.bluez.Error.NotPermitted` + `"Not paired"` → encryption-required (ATT 0x05/0x0c/0x0f,
  per `gatt-client.c:create_gatt_dbus_error`); `org.bluez.Error.Failed` + `"ATT error: 0xNN"`
  → the specific ATT code; everything else defers to `decode_dbus_error`. Replaced the
  divergent local `_ERR_MAP`s in `dbuslayer/characteristic.py` and `dbuslayer/device_le.py`
  with this classifier, and added a `requires_encryption` permission category to
  `device_le.py::_classify_read_errors`.
- **#6 `pair --probe` misreported pre-existing bonds.** `modes/pair.py::_do_probe` now
  pre-checks `check_pair_status`; an already-bonded device short-circuits with
  "already bonded — run `pair --reset` to re-probe" instead of a misleading `AlreadyExists`
  "requires explicit auth".
- **#5 Pairing identity guard.** After `resolve_device_for_pair` / `remove_stale_bond`,
  `modes/pair.py` verifies the resolved D-Bus path's MAC == requested MAC and aborts
  otherwise — prevents accidentally bonding an RPA that appeared post-reset. Defensive;
  the deeper root-cause repro is deferred (destructive).
- **#8 SDP version inference mislabeled profile versions as core-spec.**
  `analysis/sdp_analyzer.py::generate_report` now takes `authoritative_spec` / `lmp_version`
  (from HCI Read Remote Version) and renders the HCI/LMP core spec as authoritative, demoting
  SDP-derived numbers to a clearly-labelled "profile spec-hint". `modes/classic_enum.py`
  passes the target's `lmp_spec`/`lmp_version`.
- **#9 `naggy` mode escaped its retry loop on transient connection errors.**
  `core/errors.py::map_dbus_error` now maps the **transient** `br-/le-connection-*` variants
  (`canceled`, `timeout`, `busy`, `abort*`, `unknown`; strings from `workDir/bluez/src/error.h`)
  under `org.bluez.Error.Failed` to `ConnectionError`, so the existing
  `except (ConnectionError, ServicesNotResolvedError)` retry path engages and honours
  `--retries`. Permanent variants (`not-supported`, `key-missing`, `bad-socket`,
  `adapter-not-powered`, `invalid-arguments`) still fall through to a base `BLEEPError`
  (fail fast). `connection-refused` unchanged.

**Opt-in feature**
- **#2 Dual-mode LE identity correlation (`--correlate`).** New non-merging, read-only helper
  `ble_ops/le/correlate.py::correlate_le_identity` reuses `get_discovered_devices()` to rank
  candidate LE addresses by Name (required) + Icon + Class + random-addr-type into
  high/medium/low confidence. `gatt-enum --correlate` (default off) uses it as a fallback when
  the requested address resolves no GATT (empty tree **or** `ServicesNotResolvedError`),
  re-enumerating against the top candidate and labelling results as a heuristic correlation
  (never auto-merged). Without the flag, behaviour is unchanged.

**P3 — polish**
- **#13 `classic-connect`** returns `1` when SDP advertised RFCOMM channel(s) but none could
  be opened (`modes/classic_connect.py`).
- **#14 CTF flag translation** falls back to `ble_device__handle_uuid_map` (int + hex keys)
  when the service-UUID-keyed lookup misses (`ble_ops/le/ctf.py`).
- **#15 `classic-ping --timeout`** is now wired to `l2ping -t <timeout>`; the subprocess hard
  cap is `timeout + 2` (`ble_ops/classic/ping.py`).
- **#16 `classic-opp --save-dir`** parses whether placed before or after the sub-action, via a
  shared `argparse.SUPPRESS` parent parser (`cli/parsers/classic.py`).
- **#10/#11/#12 `scan` output clarity** (`ble_ops/le/scan.py`): shows BlueZ `AddressType`
  (`[random]`/`[public]`), and tags non-advertising entries `RSSI: n/a [cached, not advertising]`
  or `[bonded, cached]`.

**Tests:** new `tests/test_le_correlate.py` (7) and transient/permanent connection-error
mapping params in `tests/test_core_errors_transparency.py` (15). Full suite: 1165 passed,
27 skipped, 1 failed (pre-existing `test_schema_version_is_15` schema drift, unrelated).

### Re-Enumeration Audit Remediation — SDP versioning, display & query aids (2026-07-10)

Follow-up remediation from a read-only re-enumeration of the `winbt-honeypot` dual-mode
target (`DESKTOP-1APRSIB`, `98:3B:8F:EF:FE:EC`). Findings F1–F7; F2/F3/F5 fixed, F1
presentational aids added, F6/F7 documented. Identity correlation (IRK-based) and a
`db timeline`-style SDP change view are deferred (see `todo_tracker.md`).

**F2 — `sdp_records` is now append-only / versioned (schema v16).**
- Root cause: `NULL service_record_handle` defeated `ON CONFLICT(mac, service_record_handle)`
  (SQLite treats NULLs as distinct → unbounded re-inserts on browse-group services), and
  for *stable* handles the `ON CONFLICT … DO UPDATE` **overwrote history in place** — a
  latent destructive loss that contradicts the DB's change-over-time purpose.
- `bleep/core/observations/_connection.py`: bumped `_SCHEMA_VERSION` 15→16; removed the
  `UNIQUE(mac, service_record_handle)` constraint from `sdp_records` (base DDL for fresh
  DBs) and added a **non-unique** `idx_sdp_records_mac_handle`. A v15→v16 migration rebuilds
  the table (rename→create→copy→drop), preserving every existing row.
- `bleep/core/observations/_services.py` (`upsert_sdp_record`): replaced the overwrite with
  an append-only `INSERT` that writes a new timestamped snapshot **only when the service
  content changed** vs the latest snapshot for the same logical service
  (identity = `mac + uuid + channel`; comparison excludes the volatile
  `service_record_handle`, `ts`, and `raw_record`). Never UPDATEs, never DELETEs.
- Effect: identical re-observations (incl. handle-only rotation) no longer bloat the table;
  genuine changes are retained as distinct `ts`-versioned snapshots. Live: two `classic-enum`
  passes over the honeypot held the row count at 89 (pre-fix each pass added rows).

**F3 — Short-UUID name resolution in Classic Service Map & RFCOMM table.**
- `bleep/modes/classic_rfcomm.py` and `bleep/modes/classic_enum.py`: unnamed SDP records
  keyed by their bare UUID (e.g. `0x111F`) now resolve via `get_uuid_name()` at display time,
  so the Service Map / RFCOMM table read `0x111F (AG Hands-Free)` instead of raw hex.

**F5 — Filter-aware `scan -d/--device` message.**
- `bleep/ble_ops/le/scan.py`: when a `-d` filter matches nothing but other devices were
  seen, prints `No device matching <MAC> found (N other device(s) discovered)`, distinct from
  a genuinely empty scan.

**F1 (presentational aids only; non-merging).**
- `bleep/core/observations/_devices.py` (`get_devices`): added an optional `name` substring
  filter (`name LIKE %value%`), qualified as `d.name` on the media JOIN path.
- `bleep/modes/db.py` + `bleep/cli/parsers/db.py`: added `db list --name <substr>` (enumerate
  every RPA identity of one named device without heuristic merging) and a truncation notice
  when a page is exactly full (RPA rotation can inflate row counts). Identity correlation
  remains deferred to a future IRK-based design.

**F6/F7 — Documentation only** (`bl_classic_mode.md` troubleshooting table): non-fatal
`br-connection-create-socket` connect variant; BlueZ echoing `AddressType: public` for a
structurally-random LE address.

**Tests:** updated `tests/test_data_pipeline_fixes.py` (SDP MAP round-trip now asserts
append-only semantics; new identical-re-observation test; pagination assertions include the
new `name` kwarg). Full targeted suite green (415 passed, 8 skipped); no new lint.

### Short-form UUID Name Resolution in Classic SDP Output (2026-07-09)

Follow-up to the BR/EDR remediation below. Live re-run showed SDP records carrying
16-bit UUIDs (e.g. `0x110E`, `0x1116`, `0x112F`) still printed as bare hex because
the display path used `get_name_from_uuid()`, which does exact-string matching only
and never normalizes short↔long forms against the 128-bit-keyed name tables.

**Root cause:** the short/long-aware lookup already existed
(`bleep/bt_ref/uuid_translator.py::translate_uuid`) but the Classic display code
called the non-normalizing `get_name_from_uuid()` instead.

**Fixes (no change to `get_name_from_uuid`):**
- `bleep/bt_ref/uuid_translator.py`: added thin public convenience
  `get_uuid_name(uuid, default="")` that wraps `translate_uuid()` and returns the
  best match name (or a falsy default), for display-only call sites.
- `bleep/modes/classic_enum.py`: record-name and reconciliation (`_name_for`)
  lookups now use `get_uuid_name()`; removed the ad-hoc manual short→128-bit
  expansion inside `_name_for` (the translator handles all forms).
- `bleep/modes/debug_classic.py`: all four `csdp`/`cservices` display lookups now
  use `get_uuid_name()`.

**Verification:** `get_uuid_name` resolves `0x110E`→`A/V Remote Control`,
`0x1116`→`NAP`, `0x112F`→`Phonebook Access Server`, `180a`→`Device Information
Service`, full 128-bit forms, and returns `""` for unknown/empty input; both
Classic modes import and byte-compile cleanly.

### BR/EDR SDP Enumeration Gap Remediation (2026-07-09)

Closed gaps found by comparing BLEEP's Classic (BR/EDR) enumeration output against
raw `sdptool browse` ground truth. Previously `classic-enum` / debug `csdp`
reported only 8–9 SDP records with RFCOMM channels 1–2, missing honeypot services
(`SPP`/`OPP`/`FTP`/`PBAP`/`MAP` on ch 4–5 and `CDP Proximal Transport` on ch 3).

**Root cause:** `discover_services_sdp()` preferred `sdptool browse --xml`, whose
stream omits `ProtocolDescriptorList` for browse-group-follow services, so RFCOMM
channel extraction always failed and the richer record set was discarded in favour
of `sdptool records`, which truncates mid-enumeration and never reaches the
honeypot handles.

**Fixes:**
- `bleep/ble_ops/classic/sdp.py`: added plain `sdptool browse` as the primary
  discovery command (parsed by existing `_parse_records()`), keeping `browse --xml`
  and `records` as fallbacks. Fixed `_HANDLE_RE` to match `RecHandle` (no space)
  so Service Record Handles populate. Guarded `_parse_records()` against emitting
  empty (`handle_None`) records from stray status lines. Captured L2CAP PSM /
  RFCOMM channel / protocol versions into `protocol_descriptors[].params` (scoped
  to the "Protocol Descriptor List:" section). Carried `protocol_descriptors`
  through `build_svc_map()`. Added shared `format_protocol_descriptors()` helper.
- `bleep/modes/classic_enum.py`: resolve UUID→name for records lacking an SDP
  Service Name; display a compact `Protocols:` line; reconcile BlueZ
  `Device1.UUIDs` against parsed SDP records (advertised-but-not-in-SDP /
  SDP-but-not-advertised).
- `bleep/modes/debug_classic.py`: same UUID name resolution + `Protocols:` line in
  `csdp` and the detailed `cservices` view.
- `bleep/ble_ops/common/conversion.py`: `decode_class_of_device()` now validates
  against the fixed 24-bit CoD field instead of `bit_length() != 23`, eliminating a
  spurious "not of expected length" warning for values with leading zero bits
  (e.g. `0x2E410C`).

**Verification:** parser-level validation of handles/channels/PSM on plain-browse
text; Classic/SDP test suites pass (29 passed, 14 skipped hardware-gated). Live
device re-run pending.

### CLI Help Menu Audit & Fixes (2026-06-03)

Comprehensive audit and correction of all CLI `--help` output across the BLEEP
command tree. Every parser file (`bleep/cli/parsers/*.py`) and dispatch path was
cross-referenced against its implementation to ensure help text accurately
represents available functionality.

**Fixes — hidden or misleading functionality (8):**
- `bleep scan` help title changed from "Passive BLE scan" → "BLE scan (passive,
  naggy, pokey, or brute via --variant)" to reflect all supported variants
- `bleep enum-scan` removed deprecated `--controlled` flag (behaviour is always
  active since v2.8)
- `bleep aoi` help now lists `db` as a valid subcommand alongside scan, analyze,
  list, report, export
- `bleep aoi` parser added three missing flags: `--db-only`, `--no-db`,
  `--connectionless` — previously only accessible programmatically
- `bleep aoi --deep` and `--timeout` help text corrected from "for analyze
  subcommand" to "for scan and analyze subcommands"
- `bleep classic-enum --analyze` help clarified: "combine with --version-info
  for LMP cross-validation"
- `bleep agent --auto-accept` replaced with `--no-auto-accept`
  (`action="store_false"`, `default=True`) — the previous `store_true` +
  `default=True` meant the flag could never be disabled
- `bleep aoi db` dispatch: added action bridging in `modes/aoi.py` so the `db`
  subcommand's sub-actions (list, import, export, sync) are correctly routed
  when invoked from the main CLI; added graceful error for missing action

**New functionality exposed (2):**
- `bleep db maintain` — new subcommand running `VACUUM` + `ANALYZE` on the
  observation database, exposing the previously internal-only
  `maintain_database()` function
- `bleep --version` now includes database schema version:
  `BLEEP 3.0.0 (DB schema v15)`

**Error message improvements (2):**
- `bleep aoi` dispatch error updated to include `db` in the subcommand list
- `bleep aoi db` with no action emits valid action list instead of
  `Unknown database action: None`

**Files**: `bleep/cli/parsers/__init__.py`, `bleep/cli/parsers/aoi.py`,
`bleep/cli/parsers/db.py`, `bleep/cli/parsers/scan.py`,
`bleep/cli/parsers/classic.py`, `bleep/cli/parsers/pairing.py`,
`bleep/cli/dispatch.py`, `bleep/modes/aoi.py`, `bleep/modes/db.py`,
`bleep/modes/agent.py`

---

### Internal Documentation Audit (2026-06-03)

Comprehensive review and update of all internal documentation files to ensure
accuracy against the BLEEP 3.0.0 codebase.

**`bleep/docs/aoi_security_algorithms.md`:**
- Added new **Risk Ranking** section documenting `_assign_concern_risk()` logic:
  keyword matching for HIGH (unauthenticated, no encryption, justworks, mitm,
  knob, bias), MEDIUM (legacy, weak, outdated, deprecated), LOW (default)
- Added new **Security Score Calculation** section documenting
  `_calculate_security_score()`: baseline=5, stacking weights (+1.5/+0.75/+0.25
  per HIGH/MEDIUM/LOW concern), cap=10, legacy auto-classification

**`bleep/docs/observation_db_schema.md`:**
- Added Schema v13 migration details (survey metadata columns: `sighting_count`,
  `first_seen_survey`, `last_seen_survey`, `fingerprint_changed`)
- Added Schema v14 migration details (Classic version columns: `lmp_version`,
  `lmp_subversion`, `bt_manufacturer`, `bt_spec_version`, `lmp_features`,
  `version_queried_at`)
- Added Schema v15 migration details (DIS columns: `firmware_revision`,
  `software_revision`, `model_number`, `dis_manufacturer_name`,
  `pnp_vendor_source`, `pnp_vendor_id`, `pnp_product_id`,
  `pnp_product_version`)

**Minor fixes:**
- `changelog.md`: corrected RV test count from 79 → 73
- `observation_db.md`: schema version reference updated 13 → 15
- `api_specification.md`: schema version reference updated 13 → 15
- `device_type_classification.md`: schema version reference updated 13 → 15

**Files**: `bleep/docs/aoi_security_algorithms.md`,
`bleep/docs/observation_db_schema.md`, `bleep/docs/changelog.md`,
`bleep/docs/observation_db.md`, `bleep/docs/api_specification.md`,
`bleep/docs/device_type_classification.md`, `bleep/docs/todo_tracker.md`

---

### Augmented Verification Script — 100-Check Comprehensive Verification (2026-06-03)

**Augmented `workDir/BLEEP_3-0_verify_script.sh` from 12 sections / ~30 checks
to 23 sections / 100 checks**, covering the full BLEEP 3.0.0 feature surface
including risk ranking, security scoring, report generation, AoI analysis pipeline,
survey census structure, SDP analysis, live DB device analysis, and end-to-end
pipelines with live 120-second surveys.

**Stale assertion fixes (3):**
- Schema version: `== 13` → `== 15` (schema v14 added LMP columns, v15 added DIS)
- API surface test count: hardcoded `grep '299 passed'` → threshold `>= 299`
- Full test suite threshold: `>= 1090` → `>= 1130` (1140 currently passing)

**New offline validation sections (6):**
- **Risk Ranking Engine** (Sec 10, 8 checks): validates `_assign_concern_risk()`
  for high/medium/low classification, idempotency, and description propagation
  per `aoi_security_algorithms.md`
- **Security Score Calculation** (Sec 11, 6 checks): validates
  `_calculate_security_score()` baseline (5), stacking (+1.5/+0.75/+0.25 per
  risk tier), capping at 10, and legacy concern auto-classification
- **Report Generation & Version Embedding** (Sec 12, 6 checks): markdown risk
  emojis, text `[HIGH]` prefixes, JSON `metadata.version == "3.0.0"`, aggregate
  report summary table with Score/High/Med/Low columns
- **AoI Analysis Pipeline** (Sec 13, 5 checks): `analyse_device()` end-to-end
  including outdated LMP (< 6) flagging and JustWorks pairing detection
- **Survey Census Structure** (Sec 14, 7 checks): `SurveyCensus` offline
  validation of `format_simple`/`format_objects`/`format_grouped`, filter
  parameters, and dual-mode device detection across LE+Classic rounds
- **SDP Analyzer** (Sec 15, 4 checks): `SDPAnalyzer` import, `analyze()` return
  keys, report header, and anomaly severity constraints

**New live data validation sections (3):**
- **Live DB Device Analysis** (Sec 16, 6 checks): exercises full
  analyse→report pipeline against real production DB devices (Light Orb
  F0:98:7D:0A:05:07 with 32 characteristics, OnePlus 78:ED:BC:23:67:96
  with 211 SDP records)
- **Live Survey Pipeline** (Sec 17, 3 checks): validates `--format objects`,
  `--format grouped`, and `--format simple` CLI output structure from live
  5-second surveys
- **DB Schema v15 Features** (Sec 18, 4 checks): verifies v14 LMP columns,
  v15 DIS columns, and survey metadata columns present in `_SCHEMA_SQL`

**New end-to-end pipeline sections (2):**
- **E2E Survey-to-Report** (Sec 19, 5 checks): 120-second live survey →
  `analyse_device()` → report generation in all 3 formats (markdown, text, JSON)
- **E2E DB Aggregate & Individual Reports** (Sec 20, 6 checks): aggregate
  report across all AoI-analyzed DB devices + individual report on richest
  device, all 3 formats; output written to `/tmp/bleep_verify_e2e/`

**Infrastructure improvements:**
- CWD guard: script auto-detects project root from its own location, removing
  dependency on being invoked from a specific directory
- Timeout protection: all adapter/CLI commands wrapped with `timeout` to prevent
  indefinite hangs when Bluetooth hardware is unavailable or unresponsive
- Original hardware-dependent sections (adapter, DB CLI, test suite) preserved
  as Sections 21–23

**File**: `workDir/BLEEP_3-0_verify_script.sh`

**Results**: 100/100 passed (all checks green),
1140 passed in full test suite with 2 failures (known hardware-dependent).

---

### Remote Bluetooth Version Detection — Full Implementation (2026-05-26)

**NEW: Authoritative remote device Bluetooth version identification.**
Implements the complete Remote Bluetooth Version Detection plan (RV-1 through RV-5),
enabling BLEEP to definitively identify the Bluetooth Core Specification version
running on remote devices via multiple complementary methods.

**Phase 1 — Classic BR/EDR version query:**
- New `query_remote_version(address, adapter)` function in
  `bleep/ble_ops/classic/version.py` — wraps `hcitool info` to issue HCI Read
  Remote Version Information, returning LMP version, subversion, manufacturer,
  and feature pages
- Graceful failure handling: missing hcitool, timeout, connection refused, unparseable output

**Phase 2 — Database schema extension (v14→v15):**
- Schema v14: 6 new columns on `devices` table for Classic version data
  (`lmp_version`, `lmp_subversion`, `bt_manufacturer`, `bt_spec_version`,
  `lmp_features`, `version_queried_at`)
- Schema v15: 8 new columns for BLE Device Information Service data
  (`firmware_revision`, `software_revision`, `model_number`,
  `dis_manufacturer_name`, `pnp_vendor_source`, `pnp_vendor_id`,
  `pnp_product_id`, `pnp_product_version`)
- Idempotent migrations for both schema versions

**Phase 3 — CLI and analysis integration:**
- `classic-enum --version-info` now displays authoritative remote LMP version
  alongside local adapter info and SDP profile versions
- AoI security analysis flags outdated Bluetooth versions:
  - LMP < 6 (pre-BT 4.0): high-risk — lacks LE Secure Connections
  - LMP 6–7 (BT 4.0/4.1): high-risk — vulnerable to KNOB/BIAS attacks
- New `SDPAnalyzer.cross_validate_lmp()` method detects version mismatches
  between actual LMP and SDP-advertised profile versions (possible firmware
  spoofing indicator)
- `device_classic.py` new method `query_and_store_remote_version()` for
  programmatic access with automatic DB persistence

**Phase 4 — BLE version detection:**
- GATT Device Information Service (0x180A) extraction during BLE enumeration:
  reads Firmware Revision (0x2A26), Software Revision (0x2A28), PnP ID (0x2A50),
  Model Number (0x2A24), Manufacturer Name (0x2A29) and persists to DB
- New `infer_min_bt_version_from_le_features(features_bytes)` function: maps
  LE Supported Features bits to minimum BT Core version (20+ feature mappings
  covering BT 4.2 through 5.3)

**Phase 5 — Reference data integration:**
- Extended `update_ble_uuids.py` codegen pipeline with `CORE_VERSION` table
- New `resolve_core_version()` and public `resolve_manufacturer_name()` helpers
  in `bleep/ble_ops/common/conversion.py`
- `map_lmp_version_to_spec()` now uses SIG-sourced data as primary with
  hardcoded map retained as fallback

**Files**: `bleep/ble_ops/classic/version.py`, `bleep/ble_ops/__init__.py`,
`bleep/ble_ops/le/scan.py`, `bleep/ble_ops/common/conversion.py`,
`bleep/core/observations/_connection.py`, `bleep/core/observations/_devices.py`,
`bleep/dbuslayer/device_classic.py`, `bleep/modes/classic_enum.py`,
`bleep/analysis/aoi_analyser.py`, `bleep/analysis/sdp_analyzer.py`,
`bleep/bt_ref/update_ble_uuids.py`, `bleep/bt_ref/yaml_cache/core_version.yaml`

**Tests**: ~37 new tests across `tests/test_remote_version.py` (LE features
inference, manufacturer resolution, remote version parsing, failure modes),
`tests/test_sdp_analyzer.py` (cross-validation including `TestCrossValidateLmp`),
`tests/test_aoi_augmentation.py`
(version security concerns, schema version). Total: 348 passed, 0 failed.

---

### Report & UUID-Translate Fixes (2026-05-25)

**BUG: `### None` headings in report Services section.**
When a GATT service had `name: None` in the DB row, `service.get("name", fallback)`
returned `None` (key exists with null value) instead of using the fallback.
Changed to `service.get("name") or get_name_from_uuid(uuid) or uuid` so null
names resolve via UUID lookup.

**BUG: Duplicate UUID-translate results for 128-bit BT SIG UUIDs.**
`UUIDDatabase.search()` performed two search phases: direct normalized lookup
and short-form expansion. When the input was already a 128-bit BT SIG UUID,
both phases matched the same entries, producing duplicates. Added a `seen` set
keyed on `(category, name)` to deduplicate within the search.

**Files**: `bleep/analysis/aoi_analyser.py`, `bleep/bt_ref/uuid_translator.py`,
`tests/test_data_pipeline_fixes.py`

**Tests**: 5 new tests — 2 for service-name-None rendering, 3 for UUID dedup.
Total test suite: 1103 passed, 1 failed (CTF hardware), 28 skipped.

---

### Post-Audit Fixes — Verification Script Analysis (2026-05-25)

**BUG: CLI uuid-translate incorrectly gated by adapter guard.**
`uuid-translate` and `uuid-lookup` CLI modes are pure software operations
(YAML dictionary lookup) but were blocked by `require_adapter()` in
`bleep/cli/main.py`.  Added both modes to `_non_bt_modes` set so they
execute without a Bluetooth adapter.

**BUG: Device name overwritten by placeholder during AoI scan.**
`save_device_data()` in `aoi_analyser.py` called
`upsert_device(mac, name="Unknown Device")` as a default when the incoming
data had no name (e.g., after a failed LE enumeration), destroying the
previously-stored BlueZ-resolved name (e.g., "PLT V8200 Series").
Three-layer fix:
1. `upsert_device()` SQL: ON CONFLICT now uses CASE logic for the `name`
   column — a resolved name is never downgraded to a placeholder.
2. `save_device_data()`: only passes `name` when the caller supplied a
   meaningful one, not "Unknown Device" or "Unknown".
3. `aoi.py` file-import paths (2 call sites): same placeholder filtering.

**Files**: `bleep/cli/main.py`, `bleep/core/observations/_devices.py`,
`bleep/analysis/aoi_analyser.py`, `bleep/modes/aoi.py`,
`tests/test_data_pipeline_fixes.py`

**Tests**: 7 new tests — 2 for adapter guard bypass, 5 for name protection.

---

### Data Pipeline Remediation — Phase 1 (2026-05-24)

**BUG-1 fix: AoI report identity resolution.** Reports now correctly display
device MAC addresses and names when loaded from the observation database.
Previously, all devices showed as "Unknown" / "Unnamed Device" because the DB
returns a nested `{device: {mac, name}}` shape while report generators expected
flat `{address, name}` keys. Added `_resolve_identity()` helper that handles
both shapes; applied across markdown, text, JSON, and aggregate report generators.

**BUG-2 fix: Security scoring and risk classification.** Security concerns now
carry a `risk` field (`high`, `medium`, `low`) enabling the scorer to produce
meaningful scores above the default 5/10. Previously, `analyse_device()` wrote
concerns with a `reason` field only, but `_calculate_security_score()` looked
for `risk` — resulting in a permanently stuck 5/10 score. Added
`_assign_concern_risk()` helper applied at all concern-append sites; scorer
retroactively classifies legacy concerns for backward compatibility. Vulnerability
text in reports now falls back from `description` to `reason` to display properly.

**Files**: `bleep/analysis/aoi_analyser.py`, `tests/test_data_pipeline_fixes.py` (new).
**Tests**: 32 new tests (all passing), 0 regressions across 432 AoI/API test suite.

### Data Pipeline Remediation — Phase 2 (2026-05-24)

**BUG-3 fix: DB→Analyser characteristic shape mismatch.** Characteristic-level
security analysis now works for DB-loaded devices. Previously, `get_device_detail()`
returned `characteristics` as a flat list of row dicts (with comma-separated
`properties` strings), but `analyse_device()` only handled dict-keyed or
`services_mapping`-shaped characteristics — silently producing zero findings.

Added `_hydrate_db_device_data()` helper called in `load_device_data()` that
transforms DB-shaped data at load time: converts the characteristics list to a
UUID-keyed dict (splitting properties CSV back to lists, converting BLOB values
to hex), builds a `services_mapping` for grouped analysis, and extracts
`landmine_map`/`permission_map` from the latest `security_maps` row.

Also added a defensive `isinstance(characteristics, list)` branch in
`analyse_device()` as a safety net for callers that bypass `load_device_data()`.

**Files**: `bleep/analysis/aoi_analyser.py`, `tests/test_data_pipeline_fixes.py`.
**Tests**: 21 new tests (53 total, all passing), 0 regressions (1058 passed).

### Data Pipeline Remediation — Phase 3 (2026-05-24)

**BUG-4 fix: `load_device_data()` empty-shell fallback.** When the observation
database contains a MAC address but no actual device row (e.g., from a partial
scan), `get_device_detail()` returns `{device: None, services: [], ...}`. This
was treated as valid data because the dict is truthy, preventing fallback to
file-based lookup. Changed the truthiness check to
`if device_data and device_data.get("device"):` so empty shells correctly fall
through. Logging improved: `info` for empty shell, `warning` for DB exceptions.

**BUG-5 fix: Analysis details persistence.** The `details` block (containing
per-characteristic analysis, service reports, landmine/permission maps) was
discarded during `store_aoi_analysis()` — only the summary sub-keys were
persisted. Added `analysis_details JSON` column to `aoi_analysis` table
(schema v13 migration), updated `store_aoi_analysis()` to serialize the full
`details` block, and updated `get_aoi_analysis()` to deserialize it back as
`result["details"]` on retrieval.

**Files**: `bleep/analysis/aoi_analyser.py`, `bleep/core/observations/_aoi.py`,
`bleep/core/observations/_connection.py`, `tests/test_aoi_augmentation.py`,
`tests/test_data_pipeline_fixes.py`.
**Tests**: 7 new tests (60 total, all passing), 0 regressions (1065 passed).
**Schema**: v12 → v13.

### Data Pipeline Remediation — Phase 6 (2026-05-25)

**BUG-9 fix: Export data missing AoI analysis and device type evidence.**
`export_device_data()` returned characteristic history and advertisement reports
but omitted AoI analysis results and device type classification evidence.  Added
`get_aoi_analysis(mac)` and `get_device_type_evidence(mac)` calls, including
the results only when data exists for the device.

**BUG-10 fix: `db list` ignores pagination parameters.** `get_devices()` already
supported `limit` and `offset` parameters (default 100/0), but the CLI and
`run()` handler never passed them through.  Added `--offset` argument to the
CLI parser, changed `--limit` default to `None` (resolved to 100 for list, 50
for timeline at handler level), and wired both through `list_devices()` and
the JSON output path.

**Files**: `bleep/core/observations/_devices.py`, `bleep/modes/db.py`,
`bleep/cli/parsers/db.py`, `tests/test_data_pipeline_fixes.py`.
**Tests**: 8 new tests (86 total), 0 regressions (1083 passed).

### Data Pipeline Remediation — Phase 5 (2026-05-25)

**BUG-7 fix: SDP MAP columns not persisted.** The `sdp_records` table had
`mas_instance_id`, `supported_message_types`, and `supported_features` columns
(added in schema v12), but `upsert_sdp_record()` never included them in its
INSERT/UPDATE statement.  MAP-specific SDP attributes parsed by the SDP parser
were silently discarded.  Fixed by adding all three columns to the INSERT column
list and the ON CONFLICT UPDATE clause.

**BUG-8 fix: Survey→AoI name/type loss.** `_iter_macs()` extracted only MAC
addresses from survey JSON, discarding `name` and `device_type` metadata
carried by the survey objects.  Devices were enumerated without the survey-derived
name as a DB baseline, causing name loss if enumeration failed to connect.
Fixed by changing `_iter_macs()` to return `List[Dict]` with `mac`, `name`,
`device_type` keys, and adding a pre-seed `upsert_device()` call in the scan
loop before enumeration.

**Files**: `bleep/core/observations/_services.py`, `bleep/modes/aoi.py`,
`tests/test_data_pipeline_fixes.py`, `tests/test_survey.py`,
`tests/test_aoi_augmentation.py`.
**Tests**: 10 new tests (78 total), 6 updated tests, 0 regressions (1075 passed).

### Data Pipeline Remediation — Phase 4 (2026-05-24)

**BUG-6 fix: `db show` data truncation.** The `db show` command previously
emitted only `characteristics_count` and `classic_services_count` integers
instead of the actual characteristic, classic service, and SDP record data.

JSON output (`--json`/`--quiet`) now emits the full `get_device_detail()` dict
with bytes→hex conversion for JSON safety. Terminal output has been redesigned
from a flat JSON dump to a structured summary with expanded sections for
characteristics (uuid, handle, properties, has_value), classic services
(uuid, channel, name), and SDP records (service_uuid, service_name, channel).

Added `--full` flag to `db show` for dumping the complete device detail as
formatted JSON directly in the terminal — an alternative to `db export` without
the history/adv_reports overhead.

**Files**: `bleep/modes/db.py`, `bleep/cli/parsers/db.py`,
`tests/test_data_pipeline_fixes.py`.
**Tests**: 8 new tests (68 total, all passing), 0 regressions (1073 passed).

---

## 3.0.0 (2026-05-22)

**BLEEP v3.0 — API-Ready Architecture**

Version bump from 2.8.4 to 3.0.0 marks the completion of the 7-phase
expansion plan (Phases 1–7 + PREP-7). All phases are complete.

### Phase 7 — API Surface Definition (2026-05-22)

**Deliverable**: `bleep/docs/api_specification.md` v0.1.0

- **P7-1: Library API Surface Audit** — Programmatically extracted and cataloged
  all `__all__` exports: 84 modules, 410 symbols. Every symbol classified by
  type (class/function/constant/module), source module, and description.
  Function signatures documented for all key entry points.
- **P7-2: Concurrency Constraints** — Documented GLib.MainLoop requirements
  (pairing agent, timed scan, GATT server, LE advertising require MainLoop on
  main thread), single-flight operations (one scan/pairing/connection per
  adapter), and thread-safety characteristics (DB is thread-safe via `_DB_LOCK`;
  D-Bus calls require `GLib.idle_add()` from worker threads).
- **P7-3: Structured Error Response Format** — Mapped all 40 `RESULT_ERR_*`
  integer codes to stable string identifiers (`ERR_NOT_FOUND`,
  `ERR_AUTH_TIMEOUT`, etc.) with exception class cross-reference. Defined
  JSON error response format for programmatic callers.
- **P7-4: Session Lifecycle Contract** — Documented adapter initialization
  sequence, BLE device lifecycle (scan → connect → enumerate → read/write →
  disconnect → persist), Classic device lifecycle (SDP → connect → profile ops →
  disconnect → persist), and long-running operation management with cancellation
  and expected duration ranges.
- **P7-5: Integration Tests** — Created `tests/test_api_surface.py` with 299
  tests exercising the library API without CLI: module importability (T1),
  symbol resolution (T2), internal export hygiene (T3), error hierarchy and
  `.code` attributes (T4), OutputContext contract (T5), observation DB API (T6),
  preflight API (T7), signals API (T8), pairing API (T9), EnumerationController
  contract (T10), symbol census (T11), package re-export integrity (T12).
- **P7-6: API Specification Document** — `bleep/docs/api_specification.md`
  (8 sections): overview/conventions, package hierarchy, full API catalog with
  17 subsections covering every public package, concurrency constraints, session
  lifecycle, data formats, symbol census, and version history.

**Test suite**: 299 new tests (all passing), 0 new failures.
**Files**: `bleep/docs/api_specification.md` (new), `tests/test_api_surface.py` (new).

### Deferred Item Resolution — P3-E1 & 7B-5c (2026-05-22)

**P3-E1: user.py bare `print()` → `print_and_log()` conversion**

- Converted all 139 bare `print()` calls across 18 functions in `bleep/modes/user.py`
  to `print_and_log(msg, LOG__USER)` — output now logged to file and respects
  thread-local routing (stderr in json/quiet mode)
- Functions converted: `UserMenu.display()`, `translate_uuid_interactive()`,
  `display_device_info()`, `browse_services()`, `browse_characteristics()`,
  `characteristic_actions()`, `read_characteristic()`, `write_characteristic()`,
  `notification_callback()`, `toggle_notifications()`, `multi_read_characteristic_ui()`,
  `brute_write_characteristic_ui()`, `configure_signal_capture()`,
  `export_device_data()`, `disconnect_device()`, `scan_and_connect_menu()`,
  `manual_connect()`, `run_user_mode()`
- Zero bare `print()` calls remain in any mode module

**7B-5c: Idempotent `devices.uuids` uppercase fixup**

- Added post-migration idempotent step in `_init_db()`:
  `UPDATE devices SET uuids = UPPER(uuids) WHERE uuids IS NOT NULL AND uuids != UPPER(uuids)`
- Runs on every DB initialization; only touches rows with lowercase UUID data
- No schema version bump required — idempotent and non-destructive
- Closes the last deferred item from PREP-7B UUID normalization

**Test suite**: 706 passed, 28 skipped, 0 new failures.

### Phase 7 Preparation — Pre-Specification Remediation (2026-05-22)

Three infrastructure issues resolved to ensure Phase 7 API surface audit has
a clean foundation:

**PREP-7A: FW7 Device Type Evidence FK Verification**

- Confirmed `_ensure_device_exists` auto-create path works correctly
- Added `test_evidence_auto_creates_device_row` and
  `test_evidence_rejects_invalid_mac` regression tests
- FW7 marked CLOSED — defensive fix confirmed working

**PREP-7B: Full UUID Uppercase Normalization (UUID-1 + UUID-2)**

- Canonical form: `XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX` (uppercase, dashed)
- `update_ble_uuids.py`: generates uppercase keys via `%04X` + uppercase suffix
- `uuids.py`: regenerated from BT SIG YAML sources — 1,401 uppercase UUID keys,
  0 lowercase remaining (generated 2026-05-22)
- `constants.py`: all ~77 UUID string literals uppercased
- `get_name_from_uuid()`: normalizes input to uppercase before lookup; stale
  lowercase fallback removed after `uuids.py` regeneration
- `uuid_utils.py`, `uuid_translator.py`: canonical form changed to uppercase
- D-Bus boundary: service/char/descriptor UUIDs normalized to uppercase on read
  from BlueZ (7 D-Bus entry points in adapter, device_le, device_classic,
  characteristic, descriptor)
- Runtime comparisons: ~35 production files updated from `.lower()` to `.upper()`
- DB column: `upsert_device()` normalizes `uuids` list to uppercase
- D-Bus safety verified: BlueZ accepts any hex case on UUID input
- ~10 test files updated for uppercase assertions
- Test suite: 706 passed, 28 skipped, 0 new failures

**PREP-7C: `__all__` API Surface Remediation**

- Added `__all__` to 7 high-priority modules: `bleep/__init__.py`,
  `core/output.py`, `pairing/__init__.py`, `callbacks/__init__.py`,
  `ble_ops/classic/sdp.py`, `ble_ops/classic/connect.py`,
  `analysis/aoi_analyser.py`
- Added `__all__` to 14 mode entry-point modules and 2 dbuslayer modules
- Removed 2 underscore-prefixed symbols from existing `__all__` exports
- Aligned package re-exports: dbuslayer (Classic device), mesh (8 lazy modules),
  analysis (HIDInfo, classify_hid)
- Added `TYPE_CHECKING` stubs to `dbuslayer/__init__.py` and `mesh/__init__.py`
  for static analysis resolution of lazy-loaded names
- 64 → ~85 modules with `__all__` definitions

### Phase 6 — CLI Decomposition (2026-05-22)

Phase 6 decomposes the monolithic `cli.py` (2,964 lines) into a modular
`bleep/cli/` package and extracts 19 inline dispatch blocks into dedicated
mode modules.  No behavioral changes — purely structural relocation.

**Sub-phase 6A: Inline Implementation Extraction**

19 modes with inline implementation blocks (1,811 lines total) were extracted
into `run()` functions in their respective mode modules:

- New `modes/classic_profiles.py` (688 lines): `run_pbap()`, `run_opp()`,
  `run_map()`, `run_ftp()`, `run_pan()`, `run_spp()`, `run_sync()`,
  `run_bip()` — 8 Classic OBEX profile handlers.
- New `modes/classic_scan.py` (113 lines): `run(args, output)`.
- New `modes/classic_enum.py` (227 lines): `run(args, output)`.
- New `modes/classic_rfcomm.py` (65 lines): `run(args, output)`.
- New `modes/connect.py` (129 lines): `run(args, output)`.
- New `modes/gatt_enum.py` (68 lines): `run(args, output)`.
- New `modes/enum_scan.py` (83 lines): `run(args, output)`.
- Extended `modes/audio.py`: added `run_audio_profiles()`, `run_audio_config()`.
- Extended `modes/media.py`: added `run_media_enum()`.
- Extended `modes/blectf.py`: added `run(args, output)`.
- Fixed `modes/aoi.py` P3-E3: cli.py `main(opts)` dispatch converted to
  `run(args, output)` pattern, eliminating 63-line subcommand reassembly.

New mode module total: 1,373 lines across 7 new files.

**Sub-phase 6B: Structural Decomposition**

The remaining `cli.py` (1,243 lines after 6A) was fully decomposed into a
`bleep/cli/` package (1,326 lines across 19 files):

- `cli/__init__.py` (6 lines): re-exports `main`, `parse_args`,
  `_rebuild_debug_argv` for backward compatibility.
- `cli/__main__.py` (7 lines): enables `python -m bleep.cli`.
- `cli/main.py` (86 lines): `main()`, `_rebuild_debug_argv()`, MAC
  normalization, adapter guard, banner print, `--check-env`,
  `--diagnose-audio`, `BLEEP_LOG_LEVEL` handling.
- `cli/dispatch.py` (402 lines): central mode dispatch — 48 explicit mode
  branches + interactive fallback, all thin delegation to mode `run()`
  functions.
- `cli/parsers/__init__.py` (51 lines): `build_parser()`, registers all 14
  parser modules.
- 14 domain parser modules in `cli/parsers/`: `scan.py`, `explore.py`,
  `connect.py`, `gatt.py`, `classic.py` (247 lines, 14 subparsers),
  `media.py`, `audio.py` (81 lines, 7 subparsers), `pairing.py`,
  `db.py`, `survey.py`, `aoi.py`, `debug.py`, `utility.py` (146 lines,
  9 subparsers), `other.py`.

Old `bleep/cli.py` deleted (Python import resolution prefers `bleep/cli/`
package over `bleep/cli.py` file).

**Entry points preserved:**

- `bleep=bleep.cli:main` (setup.py console_scripts) — via `__init__.py`
  re-export.
- `python -m bleep` — via `bleep/__main__.py` → `from bleep.cli import main`.
- `python -m bleep.cli` — via `bleep/cli/__main__.py`.

**Test suite:** 704 passed, 28 skipped, 2 failed (hardware-dependent CTF),
0 regressions from pre-Phase 6 baseline.

### Sprint 5E — Deprecated Profile GATT-Level Recognition (BZ-20/21/22/23) (2026-05-22)

Sprint 5E (P4) completes Phase 5 by adding profile-aware recognition and
structured value interpretation for deprecated BlueZ plugin profiles at the
GATT level.  Rather than re-implementing the removed BlueZ D-Bus interfaces,
BLEEP now decodes characteristic values per Bluetooth SIG specifications,
providing better coverage across all BlueZ versions.

**BZ-20-23a: Profile UUID Constants (`bt_ref/constants.py`):**

- 6 service UUID constants: `HEALTH_THERMOMETER_SVC_UUID` (`0x1809`),
  `HEART_RATE_SVC_UUID` (`0x180D`), `CSC_SVC_UUID` (`0x1816`),
  `IMMEDIATE_ALERT_SVC_UUID` (`0x1802`), `LINK_LOSS_SVC_UUID` (`0x1803`),
  `TX_POWER_SVC_UUID` (`0x1804`).
- 11 characteristic UUID constants: Temperature Measurement/Type/Intermediate/
  Interval, HR Measurement/Body Sensor Location, Alert Level, Tx Power Level,
  CSC Measurement/Feature, Sensor Location.
- `DEPRECATED_GATT_PROFILE_SVCS` frozenset, `DEPRECATED_GATT_PROFILE_NAMES`
  dict, `DEPRECATED_GATT_CHR_TO_SVC` mapping.

**BZ-20-23b: Value Decoders (`ble_ops/common/gatt_profile_decode.py`):**

- New module with 11 per-characteristic decoders:
  - **Temperature Measurement** (0x2A1C / 0x2A1E): IEEE 11073 FLOAT → °C/°F,
    optional timestamp skip, temperature type enum.
  - **Temperature Type** (0x2A1D): uint8 → body location enum.
  - **Measurement Interval** (0x2A21): uint16 → seconds.
  - **Heart Rate Measurement** (0x2A37): flags-driven uint8/uint16 BPM,
    sensor contact status, energy expended (kJ), RR intervals (ms).
  - **Body Sensor Location** (0x2A38): uint8 → location enum.
  - **Alert Level** (0x2A06): uint8 → No/Mild/High Alert.
  - **Tx Power Level** (0x2A07): int8 → dBm.
  - **CSC Measurement** (0x2A5B): flags-driven wheel/crank revolutions +
    event timestamps.
  - **CSC Feature** (0x2A5C): uint16 bitmask → feature flags.
  - **Sensor Location** (0x2A5D): uint8 → 17-value location enum.
- Internal `_decode_ieee11073_float()` for IEEE 11073-20601 FLOAT type with
  NaN/NRes/Infinity special-value handling.
- Public `decode_characteristic_value(uuid, raw)` facade returns decoded
  string or None.

**BZ-20-23c: Display Integration:**

- `format_gatt_tree()` (`conversion.py`): adds `Decoded:` line after Hex/ASCII
  when a profile decoder matches.  Affects `gatt-enum`, `enum-scan`, `connect`.
- `debug_gatt.py` `cmd_read()`: shows `Value (Profile):` line for known UUIDs
  alongside existing PnP ID and numeric interpretations.
- `exploration.py`: stores `decoded` field in char_info dict, prints
  `Decoded:` line in verbose mode.
- `aoi_analyser.py`: populates `decoded_value` field in characteristic
  analysis when raw bytes are available.

**BZ-20-23d + BZ-20a: Documentation:**

- `docs/gatt_enumeration.md`: new "Recognized GATT Profiles" section with
  profile table, decoder output example, and implementation reference.
- `docs/bluez_interface_properties.md`: new "Intentionally Unsupported:
  Deprecated BlueZ Profile Plugin APIs" section documenting the four removed
  interface families and BLEEP's GATT-level approach.

**Tests: 59 tests in `tests/test_sprint5e.py`:**

- `TestSprintEConstants` — 11 tests (service UUIDs, frozenset, names, mappings).
- `TestIEEE11073Float` — 6 tests (positive, negative exponent, zero, NaN, NRes, short).
- `TestTemperatureMeasurement` — 5 tests (Celsius, Fahrenheit, type, short, intermediate).
- `TestTemperatureType` — 3 tests (enum values, empty).
- `TestMeasurementInterval` — 3 tests (normal, zero, short).
- `TestHeartRateMeasurement` — 6 tests (uint8/16, contact, energy, RR, short).
- `TestBodySensorLocation` — 3 tests (enum values, empty).
- `TestAlertLevel` — 3 tests (enum values, empty).
- `TestTxPowerLevel` — 3 tests (positive, negative, empty).
- `TestCSCMeasurement` — 4 tests (wheel, crank, both, no fields).
- `TestCSCFeature` — 3 tests (all features, none, short).
- `TestSensorLocation` — 3 tests (enum values, empty).
- `TestDecodeCharacteristicValue` — 4 tests (unknown UUID, list input, uppercase, corrupt).
- `TestFormatGattTreeDecoded` — 2 tests (alert level in tree, HR in tree).

**Test suite status:** **704 passed**, 28 skipped, 2 failed (hardware-dependent CTF), 0 errors.

### Sprint 5D — Niche Interfaces (BZ-9/10/16/17/19/24) (2026-05-21)

Sprint 5D (P3) implements the low-priority niche interfaces, completing the
Battery Provider, Bearer split interfaces, mesh OOB provisioning, HDP
documentation, and LE Audio Broadcast Assistant wrappers.

**BZ-9a/10a: BatteryProvider1 (`bleep/dbuslayer/battery_provider.py`):**

- New `BatteryProviderObject` — exposes `Percentage`, `Device`, optional
  `Source` via `BatteryProvider1`.  `update_percentage()` emits
  `PropertiesChanged`.  Percentage clamped to 0-100.
- New `BatteryProviderApp` — ObjectManager root for battery provider
  hierarchy.  `add_battery()`, `GetManagedObjects()`, `remove_all()`.
- New `BatteryProviderManager` — `register()`/`unregister()` wrappers
  calling `BatteryProviderManager1.RegisterBatteryProvider()`.
- Registered as lazy-loaded module in `dbuslayer/__init__.py`.

**BZ-16a–b: Bearer.LE1/Bearer.BREDR1 (`device_le.py`, `device_classic.py`):**

- `device_le.get_device_info()` now reads `Bearer.LE1` properties (`Paired`,
  `Bonded`, `Connected`) as `bearer_le` dict.  Graceful `None` fallback.
- `device_classic.get_device_info()` now reads `Bearer.BREDR1` properties
  as `bearer_bredr` dict.  Same graceful fallback.
- `bearer_le_connect()`/`bearer_le_disconnect()` methods on LE device.
- `bearer_bredr_connect()`/`bearer_bredr_disconnect()` methods on Classic device.

**BZ-24a: InteractiveProvisionAgent (`bleep/mesh/interactive_provision_agent.py`):**

- `MeshIOHandler` abstract base class for mesh OOB operations.
- `CliMeshIOHandler` — interactive terminal prompts for numeric/static OOB.
- `AutoAcceptMeshIOHandler` — headless handler returning zeros.
- `InteractiveProvisionAgent` — concrete `MeshProvisionAgent` subclass
  delegating all `on_*` hooks to pluggable `MeshIOHandler`.
- `create_mesh_io_handler()` factory.

**BZ-24c: Mesh CLI (`bleep/modes/mesh_provision.py`):**

- `bleep mesh join` — join a mesh network with device UUID.
- `bleep mesh provision` — provision a remote device (stub; requires active node).
- `bleep mesh reprovision` — re-provision a remote node by unicast address.
- Parser and dispatch wired in `cli.py`.

**BZ-17a: HDP Stub (`bleep/dbuslayer/health.py`):**

- Documentation stub explaining HDP removal from BlueZ 5.50+.
- `HDP_SUPPORTED = False`, legacy interface constants for reference.

**BZ-19a: MediaAssistant1 (`bleep/dbuslayer/media_assistant.py`):**

- `MediaAssistant` — proxy for `MediaAssistant1` (LE Audio Broadcast):
  `push()`, `get_state()`, `get_metadata()`, `get_qos()`, `get_info()`.
- `enumerate_media_assistants()` — discover all assistant objects.
- Registered as lazy-loaded module in `dbuslayer/__init__.py`.

**Constants:**

- Added `BATTERY_INTERFACE`, `BATTERY_PROVIDER_INTERFACE`,
  `BATTERY_PROVIDER_MANAGER_INTERFACE`, `BATTERY_PROVIDER_BASE_PATH`,
  `BEARER_LE_INTERFACE`, `BEARER_BREDR_INTERFACE`,
  `MEDIA_ASSISTANT_INTERFACE` to `bt_ref/constants.py`.

**Tests: 37 mock-based unit tests in `tests/test_sprint5d.py`:**

- `TestBatteryProviderObject` — 7 tests (path, percentage clamping, Device, Source).
- `TestBatteryProviderApp` — 4 tests (add, GetManagedObjects, empty, remove_all).
- `TestBatteryProviderManager` — 2 tests (register, unregister).
- `TestSprintDConstants` — 6 tests (all new interface constants).
- `TestBearerConstants` — 2 tests (import validation).
- `TestMediaAssistant` — 5 tests (path, push, state, info, enumerate).
- `TestInteractiveProvisionAgent` — 6 tests (default IO, custom IO, delegation).
- `TestMeshIOHandlerFactory` — 3 tests (cli, auto, invalid).
- `TestHDPStub` — 2 tests (HDP_SUPPORTED, legacy constants).

**Test suite status:** **645 passed**, 28 skipped, 1 failed (hardware-dependent CTF), 0 errors.

### Sprint 5C — Enrichment Interfaces (BZ-5/BZ-13/BZ-14/BZ-15/BZ-25) (2026-05-21)

Sprint 5C (P2) implements the medium-priority enrichment interfaces and closes
several remaining BlueZ capability gaps: GATT profile auto-connect, device sets,
admin policy, and mesh reprovisioning.

**BZ-5a: GattProfile1 Auto-Connect (`bleep/dbuslayer/gatt_server.py`):**

- `GattProfileSkeleton` — D-Bus object exposing `UUIDs` (read-only) and
  `Release()` callback.  Registered alongside GATT services via
  `GattApplication.GetManagedObjects()`.
- `GattApplication.add_profile()` — adds profiles to the ObjectManager hierarchy.
- `GattApplication.remove_all()` — now cleans up profiles alongside services.
- Reference: `workDir/BlueZDocs/org.bluez.GattProfile.rst`.

**BZ-15a–c: DeviceSet1 Coordinated Sets (`bleep/dbuslayer/device_set.py`, `bleep/modes/device_sets.py`):**

- New `DeviceSet` class wrapping `org.bluez.DeviceSet1` (experimental):
  `connect()`, `disconnect()`, `get_adapter()`, `get_auto_connect()`,
  `set_auto_connect()`, `get_devices()`, `get_size()`, `get_info()`.
- `enumerate_device_sets(bus, adapter_path)` — discovers all DeviceSet1
  objects via ObjectManager.
- `bleep device-sets` CLI command with `list`, `connect`, `disconnect`, `info`
  subcommands (`modes/device_sets.py`).
- Registered as lazy-loaded module in `dbuslayer/__init__.py`.

**BZ-13a: AdminPolicySet1 (`bleep/dbuslayer/adapter.py`):**

- `set_service_allow_list(uuids)` — calls `AdminPolicySet1.SetServiceAllowList()`
  on the adapter to restrict allowed services.
- `get_service_allow_list()` — reads `AdminPolicyStatus1.ServiceAllowList`
  from the adapter.

**BZ-14a–b: AdminPolicyStatus1 (`bleep/dbuslayer/device_le.py`, `device_classic.py`):**

- Both `device_le.get_device_info()` and `device_classic.get_device_info()` now
  read `AdminPolicyStatus1.IsAffectedByPolicy` as `is_affected_by_policy`.
- Graceful degradation: returns `None` when BlueZ lacks `--experimental`.

**BZ-25a: Mesh Reprovisioning (`bleep/mesh/management.py`):**

- `MeshManagement.reprovision(unicast, options)` — client wrapper calling
  `Management1.Reprovision()` to trigger NPPI re-provisioning procedures.
- D-Bus skeleton methods (`RequestReprovData`, `ReprovComplete`, `ReprovFailed`)
  were already present in `mesh/provisioner.py` from the earlier mesh sprint.

**Constants & fixes:**

- Added `ADMIN_POLICY_SET_INTERFACE`, `ADMIN_POLICY_STATUS_INTERFACE`,
  `DEVICE_SET_INTERFACE` to `bt_ref/constants.py`.
- Fixed stale `MESH_AGENT_INTERFACE` constant from `ProvisioningAgent1` to
  correct `ProvisionAgent1`.
- Added `GATT_PROFILE_INTERFACE` import to `dbuslayer/gatt_server.py`.

**Documentation corrections:**

- BZ-24b marked as pre-existing complete (constructor args already existed).
- BZ-25 gap table updated from "not implemented" to reflect existing D-Bus
  methods plus new Management wrapper.
- Stale line references in todo_tracker.md corrected.
- BZ-24a and BZ-24c deferred to Sprint 5D (niche mesh provisioning).

**Tests: 30 mock-based unit tests in `tests/test_sprint5c.py`:**

- `TestGattProfileSkeleton` — 7 tests (path, properties, GetAll, Release).
- `TestGattApplicationProfiles` — 4 tests (add_profile, GetManagedObjects,
  mixed services+profiles, remove_all).
- `TestDeviceSet` — 8 tests (path, connect, disconnect, adapter, auto_connect,
  set_auto_connect, devices, get_info).
- `TestEnumerateDeviceSets` — 3 tests (empty, finds sets, adapter filtering).
- `TestAdminPolicySet` — 5 tests (constants validation, interface corrections).
- `TestMeshManagementReprovision` — 3 tests (call, args, error mapping).

**Test suite status:** **608 passed**, 28 skipped, 2 failed (hardware-dependent), 0 errors.

### Sprint 5B — GATT Server (BZ-3/BZ-4) (2026-05-21)

Sprint 5B (P1) implements the GATT server stack, enabling BLEEP to publish
local BLE services that remote devices can discover, connect to, and interact
with.  This is the highest-priority remaining BlueZ capability gap.

**BZ-4a–f: Full GATT Server Implementation (`bleep/dbuslayer/gatt_server.py`):**

- New D-Bus layer module with full service hierarchy:
  - `GattApplication` — root `dbus.service.Object` implementing
    `org.freedesktop.DBus.ObjectManager` (`GetManagedObjects`).
  - `GattServiceSkeleton` — local GATT service (UUID, primary/secondary).
  - `GattCharacteristicSkeleton` — local characteristic with `ReadValue`,
    `WriteValue`, `StartNotify`/`StopNotify`, `Confirm` (BZ-3), and
    `PropertiesChanged` notification signal.
  - `GattDescriptorSkeleton` — local descriptor with `ReadValue`/`WriteValue`.
  - `GattServerManager` — wrapper around `GattManager1` with
    `register_application()`/`unregister_application()` (async + 5s timeout).
  - 5 D-Bus error types: `InvalidArgsError`, `NotSupportedError`,
    `NotPermittedError`, `InvalidValueLengthError`, `FailedError`.
- Architecture follows established patterns from `le_advertising.py`
  (single-object registration) and `adv_monitor.py` (ObjectManager hierarchy).

**BZ-3a: Confirm() for Indications:**

- `GattCharacteristicSkeleton.Confirm()` — server-side indication
  acknowledgement, gated behind the GATT server feature.

**BZ-4d: CLI mode (`bleep/modes/gatt_server.py`, `bleep gatt-server start`):**

- New CLI subcommand: `bleep gatt-server start`.
- Options: `--uuid` (repeatable), `--read-value` (hex), `--duration`, `--adapter`.
- Example characteristics per service: static read (…def1), logged write
  (…def2), 2-second tick notifier (…def3).
- GLib MainLoop with SIGINT/SIGTERM graceful shutdown.
- JSON output context support for structured event emission.

**Constants & wiring:**

- Added `GATT_PROFILE_INTERFACE` and `GATT_APP_BASE_PATH` to
  `bt_ref/constants.py`.
- Registered `gatt_server` as lazy-loaded module in `dbuslayer/__init__.py`.
- Added `gatt-server` subparser and dispatch in `cli.py`.

**BZ-4f: Tests (`tests/test_gatt_server.py`):**

- 40 new mock-based unit tests covering:
  - `GattDescriptorSkeleton`: path, properties, GetAll, default read/write raises (6 tests)
  - `GattCharacteristicSkeleton`: path, properties, descriptors, GetAll,
    read/write raises, start/stop notify, Confirm, send_notification
    when notifying/not notifying (11 tests)
  - `GattServiceSkeleton`: path, primary/secondary, characteristics, GetAll (6 tests)
  - `GattApplication`: path, empty/single/full/multi-service managed objects,
    remove_all (6 tests)
  - `GattServerManager`: register/unregister success/failure/timeout (6 tests)
  - D-Bus error types: all 5 error name strings (5 tests)

**Test suite status:** 578 passed, 28 skipped, 2 failed (hardware-dependent), 0 errors.

---

### Sprint 5A — Wire Completed Code to CLI + Mock-Based Tests (2026-05-21)

Phase 5 begins.  Sprint 5A (P0) wires existing D-Bus layer code to the CLI
and adds comprehensive mock-based unit tests for all three callback-inversion
interfaces.

**BZ-1f: AcquireWrite/AcquireNotify mock tests (`tests/test_characteristic_descriptor.py`):**

- 12 new tests covering `acquire_write()`, `acquire_notify()`, `write_value_fd()`,
  `read_notify_fd()`, and `release_acquired()`.
- Tests validate: fd+mtu return, idempotent acquire, `UnixFd.take()` vs `int()`
  fallback, auto-acquire on first use, `DBusException` fallback to
  `write_value()`/empty bytes, fd cleanup on release, simultaneous write+notify
  fd cleanup.
- Production fix: `write_value_fd()` and `read_notify_fd()` `except` clauses
  now resolve `dbus.exceptions.DBusException` dynamically via `_dbus_exc()`
  helper to support test stub environments where the module-level `dbus`
  binding may differ from `sys.modules["dbus"]`.

**BZ-7d: LEAdvertisement/LEAdvertisingManager mock tests (`tests/test_le_advertising.py`):**

- 21 new tests covering `AdvertisementConfig` dataclass, `_build_properties()`
  mapping (minimal and full), `GetAll()` interface filtering, `Release()`
  callback invocation, path auto-increment, `LEAdvertisingManager` capability
  queries, and register/unregister success/failure/timeout paths.

**BZ-12e: `--monitor` flag on `bleep scan` (`bleep/modes/scan_monitor.py`):**

- New `--monitor` flag on `bleep scan` delegates to kernel-offloaded
  `AdvertisementMonitor` instead of `StartDiscovery`.
- `bleep/modes/scan_monitor.py`: standalone module implementing monitor-based
  scan with MAC filtering (`--device`), timeout support, and device found/lost
  event streaming.
- Requires BlueZ `--experimental` mode and kernel >= 5.10.

**BZ-12g: AdvMonitor/AdvMonitorApp/AdvMonitorManager mock tests (`tests/test_adv_monitor.py`):**

- 29 new tests covering `MonitorPattern` (fields, `to_dbus()`), `RSSIConfig`
  (defaults, custom), `AdvMonitor` (path construction, properties, `GetAll`,
  `Activate`/`Release`/`DeviceFound`/`DeviceLost` callbacks, sampling period
  conditional inclusion), `AdvMonitorApp` (ObjectManager, add/remove/remove_all),
  `AdvMonitorManager` (capability queries, register/unregister paths),
  `_device_path_to_mac` helper.

**Test cleanup (pre-Sprint 5A — carried forward from test baseline work):**

- Fixed stale import paths in `test_gatt_enumeration.py`, `test_ble_ctf_full.py`.
- Fixed mock name mismatch in `test_preflight.py` (`system_dbus__bluez_device__le`
  → `system_dbus__bluez_device__low_energy`).
- Fixed DB isolation in `test_observations_aoi.py`, `test_aoi_database_integration.py`,
  `test_device_type_integration.py` (proper `BLEEP_DB_PATH` env + `_connection`
  state management).
- Fixed hardcoded schema version assertion in `test_device_type_integration.py`
  (now uses `_SCHEMA_VERSION` constant).
- Fixed incomplete D-Bus stub in `test_characteristic_descriptor.py` (added
  `UInt64`, `UInt32`, `UInt16`, `dbus.lowlevel`, `dbus.types.UnixFd`, property
  defaults for `MTU`/`Notifying`/etc.). Converted `sys.modules` assignments to
  `monkeypatch.setitem` to prevent test isolation leaks.
- Added `pytest.mark.skipif(os.geteuid() != 0)` to D-Bus integration tests
  requiring root privileges.
- Marked `test_parity_monolith_vs_refactor.py` as unconditionally skipped
  (obsolete after Phase 1-4 CLI refactoring).
- Updated CLI output assertions in `test_gatt_enumeration.py` for tree format.

**Test suite status:** 538 passed, 28 skipped, 2 failed (hardware-dependent), 0 errors.

---

### Pre-Phase 5 — Deferred Item Resolution & Test Baseline (2026-05-21)

Resolves deferred items from Phases 3–4 and fixes broken test infrastructure
to establish a clean baseline (454 tests passing) before Phase 5 work begins.

**Test import fixes (4 files):**

- `tests/test_brute_helpers.py`: `bleep.ble_ops.brute` → `bleep.ble_ops.le.brute`
  (also fixed stub to use `read_characteristic_with_fallback` method name)
- `tests/test_brute_multi.py`: `bleep.ble_ops.enum_helpers` → `bleep.ble_ops.le.enum_helpers`
- `tests/test_scan_variants.py`: `bleep.ble_ops.scan` → `bleep.ble_ops.le.scan`
- `tests/test_uuid_translation.py`: `bleep.ble_ops.conversion` → `bleep.ble_ops.common.conversion`

These 4 test modules (8 tests) had been silently uncollectable since the
`ble_ops/` subpackage reorganization (P0-8, v2.8.0).  All 8 tests now
collect and pass.

**P3-E4: OutputMode type alias consolidation (`bleep/core/log.py`):**

- Removed duplicate `OutputModeLiteral = Literal["terminal", "json", "quiet"]`
  definition from `log.py`; now imports `OutputMode` from `bleep.core.output`
  as the `OutputModeLiteral` alias.  Single source of truth for the type.
- Removed unused `Literal` from `typing` imports in `log.py`.

**P3-E2: `db.py` helper bare `print()` → `print_and_log()` (`bleep/modes/db.py`):**

- Converted all bare `print()` calls in `list_devices()`, `timeline()`,
  `show_device()`, and `export_device()` helper functions to
  `print_and_log()`.  These functions only execute in terminal mode (the
  `run()` function routes json/quiet to `emit_result()` directly), but the
  conversion ensures all output is captured in BLEEP log files and respects
  thread-local output routing.

**P3-D1: Centralized file-based stream routing (`bleep/core/output.py`):**

- `output_from_args()` now automatically opens `-o`/`--output` file as the
  `OutputContext.stream` when in json/quiet mode.  Modes that call
  `emit_result()` get file output for free without implementing file-write
  logic inline.
- Added `OutputContext.close()` method to clean up file handles opened by
  the factory (no-op for stdout/stderr).
- Terminal mode ignores the file arg (modes handle their own terminal output).
- Parent directories are created automatically (`mkdir -p` semantics).

**BZ-12f: Advertisement Monitor documentation (`bleep/docs/adv_monitor.md`):**

- New documentation file covering the `bleep monitor` command (BZ-11/12):
  prerequisites, CLI usage for `caps` and `start` sub-actions, pattern
  format reference, RSSI threshold configuration, examples (manufacturer
  data matching, proximity detection, name prefix, JSON output), architecture
  diagram, comparison with active scanning, and troubleshooting guide.
- `bleep/docs/README.md` TOC updated with link to new doc.

**Test baseline:** 454 passed, 22 failed (pre-existing), 15 errors
(D-Bus permission — pre-existing), 16 skipped.

---

### Phase 4 — P4-6: AoI deep mode → pokey write probes (2026-05-21)

**`bleep/modes/aoi.py`:**
- `_scan_target(deep=True)` now dispatches `controller.enumerate(mode="pokey", rounds=2)`
  instead of `mode="passive"`.  This gives AoI access to write-probe data that
  reveals which characteristics are writable — information that was previously
  only available through direct `pokey_enum` invocation on the CLI.
- `_perform_deep_reenumeration()` (post-pair re-enum) also switched to
  `mode="pokey"` with 2 rounds, capturing characteristics that became writable
  after pairing.
- `_variant_extra` (per-round mappings, device_props) extracted from
  `result.data` and stored separately in `device_data["variant_extra"]` and
  `delta["le_delta"]["variant_extra"]` for downstream analysis.
- Non-deep path (`deep=False`) unchanged — still uses `mode="passive"`.
- Removed unused `_connect_enum` import (dead since P4-4 centralised all
  AoI enumeration through `EnumerationController`).

### Phase 4 — P4-4: EnumerationResult persistence & P4-7 completion (2026-05-21)

**P4-4: EnumerationResult persistence to `security_maps` table:**

- `EnumerationResult` dataclass extended with two new members:
  - `serialized_annotations` (property): returns annotations as a JSON-serialisable
    `List[Dict[str, Any]]`, centralising the serialisation logic previously
    duplicated in AoI mode.
  - `persist_security_maps(mac, source)` (method): calls
    `observations.store_security_maps()` with the result's `landmine_map`,
    `permission_map`, and `serialized_annotations`.  Silently returns when there
    is nothing to persist or the observation module is unavailable.
- `cli.py` `enum-scan`: now calls `result.persist_security_maps(address,
  source="enum-scan:<variant>")` after every successful enumeration.  Previously
  security maps were never stored from this path.
- `cli.py` `gatt-enum`: now persists `landmine_map` and `permission_map` via
  `store_security_maps(source="gatt-enum")`.  Previously only GATT
  services/characteristics were persisted.
- `bleep/modes/aoi.py`: replaced 4-line manual annotation serialisation
  (list comprehension) with `le_result.serialized_annotations`.  Replaced 8-line
  manual `store_security_maps()` call with `le_result.persist_security_maps()`.
  No change in behavior — same data stored, same table, same column.
- No schema change required — annotations stored in existing
  `security_maps.enumeration_annotations` JSON column (added in v12).
- `store_security_maps()` type hint corrected: `enumeration_annotations`
  parameter changed from `Optional[Dict[str, Any]]` to
  `Optional[List[Dict[str, Any]]]` to match actual usage (list of annotation
  dicts, not a single dict).  No runtime change — `json_dumps` handles both.

**P4-7 completion: documentation updated to reflect unified architecture:**

- `ble_scan_modes.md`: rewritten — added "Connection Modes" section with ASCII
  architecture diagram, mode parameter table, and behavioural notes.  Old content
  (discovery scan variants, enumeration variants, safety flags) preserved.
- `explore_mode.md`: "Connection Modes / Architecture" section rewritten to
  describe wrapper-based delegation to `connect.py`.  Passive/naggy mode docs
  updated with internal parameter mappings.
- `todo_tracker.md` P4-7 entry: expanded with "Old → New Architecture Translation
  Reference" — a table mapping every element of the pre-P4-3 `scan_modes.py`
  implementation to its post-P4-3 equivalent in `connect.py` parameters and
  extracted helpers.

**Tests:** 446 passed; 22 pre-existing failures unrelated to these changes.

### Phase 4 — P4-3: scan_modes.py ↔ connect.py reconciliation (2026-05-21)

Eliminates the duplicated scan/connect/service-resolve pipeline in
`scan_modes.py` by parameterising `connect_and_enumerate__bluetooth__low_energy()`
and reducing each scan-mode function to a thin wrapper.

**`bleep/ble_ops/le/connect.py` — parameterised canonical pipeline:**

- New keyword parameters (all backward-compatible defaults):
  `scan_attempts`, `scan_timeout`, `connect_retries`, `connect_wait_timeout`,
  `transport`, `max_attempts`, `backoff_base`, `backoff_max`, `backoff_jitter`.
- `timeout_connect` kept as deprecated alias — when `connect_wait_timeout` is
  `None` (default), falls back to `timeout_connect` value.  All 3 existing
  callers (`bleep-mcp ble_connect`, `scratch.py`, `four_hour_recon_session.py`)
  continue to work unchanged.
- Transport discovery filter applied via `SetDiscoveryFilter` when `transport`
  is `"le"` or `"bredr"` (best-effort, matching `scan_modes._scan_until_visible`
  behavior).
- Scan loop parameterised: `scan_attempts` / `scan_timeout` replace hardcoded
  `3` / `5`.
- Connect call parameterised: `device.connect(retry=connect_retries,
  wait_timeout=connect_wait_timeout)` replaces hardcoded `retry=5`.
- Outer retry loop (`max_attempts > 1`): wraps connect + service-resolve with
  exponential backoff + jitter.  D-Bus `InProgress`/`Failed` errors forgiven
  (don't count toward `max_attempts`) — guarded by `max_attempts > 1` so
  single-attempt callers (legacy default) never enter an infinite retry.
  Pair-fallback, stall-mitigation, and audio hint preserved inside each attempt.
- Removed unused `import sys as _sys`.
- Added `import random as _random` for backoff jitter.

**`bleep/ble_ops/le/scan_modes.py` — thin wrappers:**

- Three private helpers extracted:
  - `_classic_connect(target, transport)` — BR/EDR device scan + connect path
    with `ClassicDevice is None` guard.
  - `_classify_device(device, mode, log_flags)` — best-effort device-type
    classification; `log_flags=True` only for passive (preserves existing
    behavior where only passive logs `device_type_flags`).
  - `_pokey_deep_read(device)` — char/descriptor deep-read loop extracted from
    pokey (lines 435–481 of the original).
- `passive_scan_and_connect`: delegates to `_connect_enum` with timeout-derived
  params (`scan_attempts=3`, `connect_retries=1`, etc.).  Classic branch via
  `_classic_connect`.
- `naggy_scan_and_connect`: delegates outer retry to `_connect_enum` with
  `max_attempts=max_retries`, `backoff_base=0.5`, `backoff_max=30`,
  `backoff_jitter=0.5`.
- `pokey_scan_and_connect`: delegates connect to `_connect_enum` with
  `scan_timeout=10`, `connect_retries=5`, `timeout_services=30`,
  `deep_enumeration=False`; runs `_pokey_deep_read` post-connect.
- `bruteforce_scan_and_connect`: structure unchanged — calls
  `pokey_scan_and_connect` then handle sweep.
- Removed duplicated code: `_wait_for_services()`, `_get_adapter()`,
  `_scan_until_visible()`, inline scan/connect/service-resolve blocks, inline
  D-Bus exception mapping.
- Removed unused imports: `Optional`, `_log_disconnect_reason` (now handled
  internally by `connect.py`), `time`, `random`, `Set`, `Union`.
- `scan_and_connect()` dispatcher unchanged.
- Mode constants (`PASSIVE_MODE`, etc.), `__all__`, and all public function
  signatures unchanged.

**Backward compatibility:**

- All existing callers require zero changes.
- `scan_modes.py` reduced from 684 to 548 lines (~20% reduction).
- `connect.py` grew from 295 to 370 lines (parameterisation + retry loop).
- 394 tests pass; 10 pre-existing failures unrelated to this change.

### Phase 4 — Enumeration Architecture Unification: P4-2 & P4-7 partial (2026-05-20)

Makes `EnumerationController` the standard dispatch path for ALL `enum-scan`
invocations.  The `--controlled` flag is retained for backward compatibility
but is a no-op — the controller is always active.

**P4-2: Controller becomes the default path (`bleep/cli.py`):**

- Removed the dual-path dispatch (controlled vs direct).  All `enum-scan`
  traffic now flows through `EnumerationController.enumerate()`.
- `_variant_extra` data (e.g. `changed_chars`, `multi_read`, `device_props`)
  is separated from the GATT mapping before DB persistence and tree output
  to avoid phantom service entries.
- Tree-formatted output preserved: `format_gatt_tree()` receives the clean
  mapping dict, `result.landmine_map`, `result.permission_map`, and variant
  extras (`changed_chars`, `device_props`) for change-detection highlighting.
- DB persistence preserved: `_persist_mapping()` receives the clean mapping
  (without `_variant_extra`).
- Annotation summary printed to stderr when retries occurred (does not
  interfere with pipe-friendly stdout).
- `--controlled` argument kept in argparser with deprecated help text.

**P4-7 (partial): Documentation fixes (`bleep/docs/gatt_enumeration.md`):**

- Removed false claim about `ReconnectionMonitor` in Controlled Mode section.
- Corrected 8 stale file paths:
  - `bleep/ble_ops/connect.py` → `bleep/ble_ops/le/connect.py`
  - `bleep/ble_ops/scan.py` → `bleep/ble_ops/le/scan.py` (4 occurrences)
  - `bleep/ble_ops/conversion.py` → `bleep/ble_ops/common/conversion.py` (2 occurrences)
  - `bleep/ble_ops/enum_controller.py` → `bleep/ble_ops/le/enum_controller.py`
- Rewrote "Controlled Mode" section as "Enumeration Controller" — documents
  always-active retry/annotation behavior and variant-specific forwarding.
- Updated comparison table: `--controlled mode` → `Retry + annotations`.
- Updated `--controlled` argument description as deprecated.
- Updated "Last updated" date.

**Backward compatibility:**

- `bleep enum-scan ... --controlled` still accepted (no error).
- AoI mode, MCP `ble_enumerate` tool: no change (already use controller directly).
- Test suite: 446/468 pass, 22 failures + 15 errors all pre-existing
  (D-Bus permission, stale test modules).

**Modified files:**

- `bleep/cli.py` — unified enum-scan dispatch through controller
- `bleep/docs/gatt_enumeration.md` — 8 stale paths corrected, ReconnectionMonitor
  claim removed, Controlled Mode → Enumeration Controller section rewrite
- `bleep/docs/todo_tracker.md` — P4-2 marked complete, P4-7 partially complete
- `bleep/docs/changelog.md` — this entry

---

### Phase 4 — Enumeration Architecture Unification: P4-1 & P4-5 (2026-05-20)

Makes `EnumerationController.enumerate(mode)` dispatch to the actual scan.py
variant functions instead of only toggling the `deep_enumeration` boolean.
Prior to this change, calling `controller.enumerate(mode="naggy")` was
identical to `mode="passive"` — the mode name was accepted but had no effect
beyond toggling `deep_enumeration` for `pokey`/`bruteforce`.

**Core change — variant dispatch (`bleep/ble_ops/le/enum_controller.py`):**

- `enumerate(mode, **variant_kwargs)` now delegates to `_dispatch_variant()`
  for `naggy`, `pokey`, `brute`/`bruteforce` modes
- `_run_naggy()` → calls `scan.naggy_enum()` (3-round multi-read, change
  detection)
- `_run_pokey()` → calls `scan.pokey_enum()` (multi-round reconnect + write
  probes); forwards `rounds`, `verify` kwargs
- `_run_brute()` → calls `scan.brute_enum()` (payload fuzzing); forwards
  `write_char`, `value_range`, `patterns`, `payload_file`, `force`, `verify`,
  `deep` kwargs
- `passive` mode unchanged — direct `connect_and_enumerate` call
- Variant-specific results stored under `result.data["_variant_extra"]`
- `set` types (e.g. `changed_chars` from naggy) converted to sorted lists
  for JSON serialization

**Docstring & dead code cleanup:**

- Module docstring: removed false claims about `ReconnectionMonitor` and
  `ConnectionResetManager` integration
- Class docstring: rewritten to accurately describe passive vs variant
  dispatch behavior
- `enumerate()` docstring: documents all supported modes with accepted kwargs
- Removed dead `_should_continue()` method (unused by `enumerate()` loop)
- Removed unused `BLEEPError` import
- Added `ConnectionAnnotation` to `__all__` exports

**CLI `enum-scan --controlled` (`bleep/cli.py`):**

- Now forwards variant-specific kwargs to `controller.enumerate()` — pokey
  gets `rounds`/`verify`, brute gets `write_char`/`value_range`/`patterns`/
  `payload_file`/`force`/`verify`
- JSON output uses `default=str` for non-serializable types

**MCP `ble_enumerate` tool (`bleep-mcp/bleep_mcp/tools/ble.py`):**

- Fixed return value to use correct `EnumerationResult` fields (`data`,
  `landmine_map`, `permission_map`, `annotations`, `error_summary`) instead
  of non-existent `result.services` / `result.errors`

**scan.py variant return values (`bleep/ble_ops/le/scan.py`):**

- `passive_enum` and `naggy_enum` now include `device` object in return
  dict — enables callers (including controller) to access device name and
  services from all variants

**Backward compatibility:**

- AoI mode calls `controller.enumerate(mode="passive")` — hits the
  unchanged direct-connect path; no behavioral change
- Existing `enum-scan` without `--controlled` — subsequently unified in P4-2
  (controller now always active)
- Test suite: 76/77 tests pass; 1 pre-existing failure in
  `test_get_aoi_analyzed_devices` (unrelated to this change)

**Modified files:**

- `bleep/ble_ops/le/enum_controller.py` — variant dispatch, docstring fixes,
  dead code removal, `ConnectionAnnotation` export
- `bleep/ble_ops/le/scan.py` — `passive_enum` and `naggy_enum` include
  `device` in return dict
- `bleep/cli.py` — `--controlled` forwards variant kwargs, `default=str`
  for JSON output
- `bleep-mcp/bleep_mcp/tools/ble.py` — correct `EnumerationResult` field
  access
- `bleep/docs/todo_tracker.md` — P4-1, P4-5 marked complete
- `bleep/docs/changelog.md` — this entry

---

### Phase 3 — Output Contract & Stdout Contamination Fix (2026-05-20)

Establishes a clean output contract for `--json`/`--quiet` modes across all
BLEEP CLI modes.  Prior to this work, running `bleep explore --json` mixed
human-readable `print_and_log()` output on stdout with structured JSON from
`emit_result()`, breaking pipe-friendly consumers.

**Core mechanism — thread-local output routing (`bleep/core/log.py`):**

- Added `set_output_mode(mode)` / `get_output_mode()` using
  `threading.local()` to control the `print()` destination in
  `print_and_log()` without altering its call signature or any call sites
- In `"json"` or `"quiet"` mode: `print()` routes to `sys.stderr`
- In `"terminal"` mode (default): `print()` routes to `sys.stdout`
  (existing behavior)
- **Critical invariant**: `logging__log_event()` **always** writes to log
  files regardless of output mode — no log data is ever lost or deferred

**Mode wiring — all 11 mode `run()` entry points:**

- `survey.py`, `agent.py`, `exploration.py`, `signal.py`, `db.py`,
  `classic_connect.py`, `pair.py`, `aoi.py`, `user.py`, `monitor.py`,
  `advertise.py` — each calls `set_output_mode(output.mode)` immediately
  after resolving `OutputContext`

**Bare `print()` → `print_and_log()` conversion:**

- `classic_connect.py` — all bare `print()` calls in `run()` and
  `_ensure_paired()` converted; messages now logged to file and routed
  correctly in json/quiet mode
- `pair.py` — all bare `print()` calls in `_do_probe()`, `_do_brute()`,
  `_do_pair()` converted; `run()` entry point restored after accidental
  removal during editing
- `monitor.py` — all bare `print()` converted; `run()` entry point added
  with `OutputContext` and `set_output_mode()` wiring
- `advertise.py` — all bare `print()` converted; `run()` entry point
  added with `OutputContext` and `set_output_mode()` wiring
- `user.py` — bare `print()` in `run()` exception handlers converted
- `db.py` — bare `print()` in `run()` module-unavailable guard and
  sub-command fallthrough error converted; `main()` wrapper guard also
  converted

**Structured result emission (P3-B5 — `emit_result()` for final output):**

- `exploration.py` — in `--json`/`--quiet` mode, emits the full GATT
  result dict (device address, name, services, characteristics, handles,
  flags, descriptors, mappings) via `output.emit_result(result)`;
  suppresses verbose terminal listing when not in terminal mode
- `db.py` — `list` emits device array (with optional field filtering),
  `show` emits single device detail dict, `export` emits full device
  data record, `timeline` emits characteristic history array; all route
  through `output.emit_result()` in json/quiet mode while preserving
  terminal table formatting in default mode
- `signal.py` — each BLE notification emits a structured JSON event:
  `{"ts": <ISO-8601>, "uuid": <char-uuid>, "char_path": <dbus-path>,
  "value_hex": <hex-string>, "length": <int>}`; progress messages
  (`Listening...`, `Done`) route via `output.emit_progress()` to stderr

**Structured JSON events for long-running modes (P3-C):**

- `agent.py` — `agent_registered`, `pairing_started`,
  `pairing_succeeded`, `pairing_failed`, `device_trusted` events via
  `output.emit_result()`
- `monitor.py` — `device_found`, `device_lost`, `monitor_stopped`,
  `monitor_caps` events
- `advertise.py` — `adv_started`, `adv_stopped`, `adv_released`,
  `advertise_caps` events

**Subprocess flag propagation:**

- `survey.py` `--then-aoi` subprocess now forwards `--json`/`--quiet`
  global flags to the spawned `bleep aoi scan` process

**Dead code removal:**

- `survey.py` — removed unused `total_rounds` variable and `ceil` import

**CLI dispatch updates (`bleep/cli.py`):**

- `monitor` and `advertise` modes now dispatch through
  `run(args, output_from_args(args))` instead of direct
  `handle_monitor()`/`handle_advertise()` calls

**Design decisions:**

- Thread-local approach chosen over (a) adding `output` parameter to every
  `print_and_log()` call site (hundreds of changes) or (b) modifying the
  logging stack (too invasive).  `threading.local()` applies to the entire
  call stack without touching intermediate functions like
  `scan_and_connect()` that call `print_and_log()` internally.
- `LOG__DEBUG` and `LOG__ENUM` log types continue to suppress all
  terminal/stderr output (file-only) — this is intentional pre-existing
  behavior for debug and enumeration log channels.
- `user.py` interactive TUI (~120 bare prints) and `db.py` terminal-only
  helpers (~27 bare prints) deferred — these only execute in terminal mode
  and are not stdout contamination sources.

**Modified files:**

- `bleep/core/log.py` — `set_output_mode()`, `get_output_mode()`,
  `print_and_log()` routing, removed unused `Union` import
- `bleep/core/output.py` — no changes (validated compatible)
- `bleep/modes/survey.py` — `set_output_mode` wiring, subprocess flag
  propagation, dead code removal
- `bleep/modes/agent.py` — `set_output_mode` wiring, structured events
- `bleep/modes/exploration.py` — `set_output_mode` wiring
- `bleep/modes/signal.py` — `set_output_mode` wiring
- `bleep/modes/db.py` — `set_output_mode` wiring, `print_and_log` import,
  bare print conversion in `run()`
- `bleep/modes/classic_connect.py` — `set_output_mode` wiring, full bare
  print conversion
- `bleep/modes/pair.py` — `set_output_mode` wiring, `run()` restoration,
  full bare print conversion
- `bleep/modes/aoi.py` — `set_output_mode` wiring
- `bleep/modes/user.py` — `set_output_mode` wiring, bare print conversion
  in `run()` exception handlers
- `bleep/modes/monitor.py` — `run()` entry point, `set_output_mode`
  wiring, full bare print conversion, structured events
- `bleep/modes/advertise.py` — `run()` entry point, `set_output_mode`
  wiring, full bare print conversion, structured events
- `bleep/cli.py` — monitor/advertise dispatch via `run()`
- `bleep/docs/todo_tracker.md` — Phase 3 items marked complete
- `bleep/docs/changelog.md` — this entry

---

### Phase 2 — Database Persistence Gap Closure (2026-05-19)

Closes all seven data domains that were printed to terminal but never persisted
to the observation database.  Schema upgraded from v11 to v12.  The DB can now
serve as a reliable structured-data API surface for all BLEEP operational modes.

**Schema changes (`bleep/core/observations/_connection.py`):**

- **New tables**: `pairing_events` (full pairing workflow per attempt),
  `security_maps` (per-enumeration landmine/permission maps),
  `media_enumerations` (full media-enum JSON snapshots),
  `audio_recon` (host-level audio reconnaissance — no device FK)
- **New `devices` columns**: `uuids` (JSON), `paired` (BOOLEAN),
  `trusted` (BOOLEAN), `bonded` (BOOLEAN), `sighting_count` (INT),
  `fingerprint_changed` (BOOLEAN)
- **New `sdp_records` columns**: `mas_instance_id` (INT),
  `supported_message_types` (TEXT), `supported_features` (TEXT)
- **Migration**: v11→v12 block with idempotent `ALTER TABLE ADD COLUMN`
  and `CREATE TABLE IF NOT EXISTS`; indexes on mac/ts for all new tables

**New persistence API functions (`bleep/core/observations/`):**

- `store_pairing_event()` — method, PIN, result, capabilities, auth
  matrix, brute-force stats, pre/post pair state (`_pairing.py`)
- `get_pairing_events()` — retrieve with JSON field deserialization
- `store_security_maps()` — landmine map, permission map, enumeration
  annotations, source tag (`_evidence.py`)
- `get_security_maps()` — retrieve with JSON field deserialization
- `store_media_enumeration()` — players, transports, endpoints, browse
  tree, capabilities (`_media.py`)
- `get_media_enumerations()` — retrieve with JSON field deserialization
- `store_audio_recon()` — backend, cards, pcms, recordings, sox
  analysis, contention (`_media.py`)
- `get_audio_recon()` — retrieve with JSON field deserialization
- Extended `upsert_device()` — accepts `uuids`, `paired`, `trusted`,
  `bonded`, `sighting_count`, `fingerprint_changed`; auto JSON-serializes
  list/dict values for `uuids`, `service_data`, `advertising_data`

**Persistence wiring (11 integration points):**

- `bleep/modes/signal.py` — `insert_char_history()` in `_notify_cb`
- `bleep/modes/pair.py` — `store_pairing_event()` in `_do_pair`,
  `_do_probe`, `_do_brute` (3 call sites)
- `bleep/modes/agent.py` — `store_pairing_event()` + `upsert_device()`
- `bleep/modes/debug_pairing.py` — `store_pairing_event()` in
  `_cmd_pair_single`
- `bleep/cli.py` — `store_media_enumeration()` in `media-enum` handler
- `bleep/modes/media.py` — `store_media_enumeration()` in
  `enumerate_media_passive()`
- `bleep/ble_ops/audio/audio_recon.py` — `store_audio_recon()` at end
  of `run_audio_recon()`
- `bleep/modes/exploration.py` — `store_security_maps()` in
  `save_to_database()`
- `bleep/modes/aoi.py` — `store_security_maps()` after scan pipeline
- `bleep/ble_ops/le/scan.py` — `insert_adv()` in `_native_scan()`;
  `uuids`, `paired`, `trusted`, `bonded` via `upsert_device()`
- `bleep/modes/survey.py` — `upsert_device()` with `sighting_count`,
  `fingerprint_changed`, `uuids` after main loop

**Data retrieval enhancements:**

- `get_device_detail()` now includes `pairing_events`, `security_maps`,
  and `media_enumerations` in its response
- `export_device_data()` transitively includes all Phase 2 tables
- `__all__` expanded to 35 symbols (8 new Phase 2 functions)

**Preparation work (completed prior to Phase 2 implementation):**

- Refactored `bleep/core/observations.py` (2065 LOC monolith) into
  `bleep/core/observations/` package with 10 submodules
- `obs_db` pytest fixture in `tests/conftest.py` for isolated temp DBs
- 4 focused `insert_adv()` tests in `tests/test_insert_adv.py`

**Test fixes (pre-existing issues exposed during review):**

- `tests/test_observations_sqlite.py` — fixed DB isolation (was using
  `patch.object` instead of `_connection._DB_PATH` direct assignment)
- `tests/test_observations_media.py` — fixed stub interface mismatch
  and DB isolation

**Modified files:**

- `bleep/core/observations/_connection.py` — schema v12, migration
- `bleep/core/observations/_devices.py` — extended `_DEVICE_COLS`,
  JSON serialization, `get_device_detail` Phase 2 tables
- `bleep/core/observations/_pairing.py` — new module
- `bleep/core/observations/_evidence.py` — `store/get_security_maps`
- `bleep/core/observations/_media.py` — `store/get_media_enumeration`,
  `store/get_audio_recon`
- `bleep/core/observations/__init__.py` — re-exports, `__all__`
- `bleep/ble_ops/le/scan.py` — `insert_adv`, UUID/boolean persistence
- `bleep/modes/signal.py` — notification persistence
- `bleep/modes/survey.py` — survey metadata persistence
- `bleep/modes/exploration.py` — security map persistence
- `bleep/modes/aoi.py` — security map persistence
- `bleep/modes/pair.py` — pairing event persistence
- `bleep/modes/agent.py` — pairing event persistence
- `bleep/modes/debug_pairing.py` — pairing event persistence
- `bleep/modes/media.py` — media enumeration persistence
- `bleep/cli.py` — media-enum persistence
- `bleep/ble_ops/audio/audio_recon.py` — audio recon persistence
- `bleep/docs/observation_db_schema.md` — v12 documentation
- `bleep/docs/todo_tracker.md` — P2-A/B items marked complete

---

### Phase 1 — Documentation Corrections & Dead Code Removal (2026-05-18/19)

No behavioral changes.  Fixes documentation drift, updates stale metadata,
and wires two BZ items that had completed D-Bus code but no CLI surface.

**Documentation & metadata fixes:**

- `bleep/docs/observation_db_schema.md` — updated to reflect schema v11:
  documented `aoi_analysis.pairing_profile`, `sdp_summary`, `post_pair_delta`
  columns added in v2.8.4
- `bleep/mesh/__init__.py` — fixed docstring path from
  `workDir/bluez/doc/mesh-api.txt` to `workDir/BlueZDocs/mesh-api.txt`
- `setup.py` — synced version from `2.7.25` to `2.8.4` (matching
  `bleep/__init__.py`)
- `.taskmaster/docs/bleep-refactor-gap-analysis-prd.txt` — marked all 10
  identified gaps as **IMPLEMENTED** (debug mode, BLE CTF, advanced scanning,
  pairing/bonding, media, Bluetooth Classic — completed in v2.7–v2.8)
- `README.refactor` — archived with banner directing to
  `bleep/docs/todo_tracker.md` for current work
- BZ gap summary table in `todo_tracker.md` — corrected BZ-6/7 to
  `DONE (Sprint 2)`, BZ-8 to `DONE (Sprint 1)`, BZ-11/12 to
  `DONE (Sprint 4)`
- `bleep/gatt/__init__.py` — restored package (not dead code); updated
  docstring clarifying its purpose as a refactoring target for breaking
  GATT files into ≤300 LOC modules

**BZ wiring (existing D-Bus code surfaced to CLI):**

- **BZ-1e** `--stream` flag on debug mode `read`/`write` commands:
  `read --stream <uuid>` uses `AcquireNotify` fd-based streaming via
  `select()` loop; `write --stream <uuid> <value>` uses `AcquireWrite`
  fd via `char.write_value_fd()`.  Falls back to standard D-Bus
  ReadValue/WriteValue if characteristic does not support acquire.
  (`bleep/modes/debug_gatt.py`)
- **BZ-8f** Disconnect reason surfaced in debug mode `info` command and
  scan/enum output: `_print_disconnect_reason()` in `debug_connect.py`
  called from `_info_ble()`, `_info_classic()`, `_info_from_dbus_path()`;
  `_log_disconnect_reason()` helper added to `connect.py`, called from
  `connect.py` (services-not-resolved), `scan_modes.py`
  (passive/naggy/pokey service-resolution failures).  Queries both
  `_get_global_signals()` and `_signals_manager` singleton; prints
  human-readable label with optional reason code; no-op when no
  disconnect signal was captured.

**Modified files:**

- `bleep/docs/observation_db_schema.md`, `bleep/mesh/__init__.py`,
  `setup.py`, `.taskmaster/docs/bleep-refactor-gap-analysis-prd.txt`,
  `README.refactor`, `bleep/gatt/__init__.py`,
  `bleep/modes/debug_gatt.py`, `bleep/modes/debug_connect.py`,
  `bleep/dbuslayer/device_le.py`, `bleep/ble_ops/le/connect.py`,
  `bleep/ble_ops/le/scan_modes.py`, `bleep/docs/todo_tracker.md`

---

### Survey Mode — Long-Duration Passive Device Discovery

New `bleep survey` CLI command for multi-transport passive scanning with
automatic deduplication, per-device RSSI tracking, and AoI-compatible
target list output.

**Phase 1 — Core Implementation:**

- **`bleep/modes/survey.py`** — `DeviceSighting` dataclass, `SurveyCensus`
  accumulator class (merge LE/Classic results, RSSI min/max/avg, sighting
  count, type upgrade to `dual`), three output formatters (`simple`,
  `objects`, `grouped`), `_run_le_round()` and `_run_classic_round()` scan
  helpers, `SIGINT`/`SIGTERM` graceful interruption, `_build_parser()`,
  `main()` entry point
- **`tests/test_survey.py`** — 32 unit tests covering census merge, filter,
  all three output formats, AoI `_iter_macs()` compatibility, signal
  handling, argument parser, JSON roundtrip, summary counts
- **`bleep/docs/survey_mode.md`** — user documentation with command
  reference, output format specs, integration examples

**Phase 2 — Enhancements:**

- **Aggregate Report (`bleep aoi report --all`)** — new
  `generate_aggregate_report()` method in `AOIAnalyser` producing combined
  markdown/text/JSON reports with summary table and per-device sections;
  `report` subparser `--address` is now optional (use `--all` for all
  AoI-analyzed devices)
- **BlueZ Health Monitoring** — survey loop now starts
  `BlueZServiceMonitor` (heartbeat thread) at survey begin, registers
  stall/unavailability callbacks that emit stderr warnings before each
  round; `--live` output includes `BlueZ: OK` health status; monitor is
  stopped cleanly on survey end/interrupt
- **`--then-aoi` convenience flag** — after survey output is written,
  automatically invokes `bleep aoi scan <file>` via subprocess; requires
  `-o` for a file-based target list
- **`--no-db` fix** — `_run_classic_round()` now accepts `persist_db`
  parameter; the old inert `BLEEP_SURVEY_NO_DB` env var approach removed

**Bug-fixes (post-field-test):**

- **`bleep/modes/aoi.py`** — aggregate report auto-filename used
  `datetime.now()` on the `datetime` *module* instead of `datetime.datetime.now()`;
  manifested as `module 'datetime' has no attribute 'now'` when `-o` was omitted
- **`bleep/analysis/aoi_analyser.py`** — `_generate_aggregate_json()` and
  `_generate_json_report()` passed raw device data (which may contain `bytes`
  from DB) directly to `json.dumps()`; added `_sanitize_for_json()` static
  method to recursively hex-encode bytes before serialization
- **`bleep/dbuslayer/bluez_monitor.py`** line 93 — missing closing `]` in
  availability log message; `[! BlueZ …` → `[!] BlueZ …`

**Phase 3 — Debug Mode Integration:**

- **`survey start|stop`** — new debug shell command that runs a survey in a
  background daemon thread (same model as `monitor start|stop`); supports all
  CLI flags (`--duration`, `--round-time`, `--transport`, `-o`, `--format`,
  `--min-rssi`, `--min-sightings`, `--no-db`, `--adapter`, `--then-aoi`);
  quit/exit auto-stops any running survey
- **`survey-status`** — new debug shell command that reports survey progress:
  RUNNING/FINISHED state, round count, elapsed/duration, device breakdown
  (LE/Classic/Dual), output path
- **`DebugState`** extended with survey fields (`survey_thread`,
  `survey_stop_event`, `survey_census`, `survey_round`, `survey_elapsed`,
  `survey_duration`, `survey_output`)

**Modified files (Phase 3):**

- **`bleep/modes/debug_survey.py`** — new submodule with `cmd_survey` and
  `cmd_survey_status`
- **`bleep/modes/debug_state.py`** — survey fields added to `DebugState`
- **`bleep/modes/debug.py`** — import, dispatch table entries, help group,
  quit cleanup
- **`tests/test_survey.py`** — 7 new debug-shell tests (43 total)

**Phase 6 — Extended Features:**

- **Beacon fingerprinting** — `DeviceSighting` extended with full
  `manufacturer_data` (Dict[int, bytes]), `service_data` (Dict[str, bytes]),
  `tx_power`, `appearance`, and `fingerprint_changed` flag; `_merge_entry()`
  uses union/longest-wins policy for manufacturer & service payloads;
  `format_objects()` / `format_grouped()` hex-encode bytes in JSON output;
  detects and flags payload changes across rounds
- **Survey resume from DB** — `SurveyCensus.seed_from_db()` paginates
  through `observations.get_devices()`, converts ISO timestamps to epoch
  floats, sets `sighting_count=0` for seeded entries; new `--resume-db`
  CLI flag in `bleep survey` and `bleep debug survey start`; default
  `--min-sightings 1` excludes DB-only entries unless overridden
- **Adaptive round timing** — `--adaptive` flag enables discovery-rate-based
  round time adjustment; zero new devices halves `dynamic_rt`, >=3 new
  devices adds 10s, clamped by `--adaptive-min` (10s) / `--adaptive-max`
  (60s); `--live` output includes current `rt=Ns` when adaptive is active

**Modified files (Phase 6):**

- **`bleep/modes/survey.py`** — `DeviceSighting` new fields,
  `_merge_mfr_data()`, `_merge_svc_data()`, `seed_from_db()`,
  `_hex_encode_bytes()`, adaptive loop logic, new CLI flags
- **`bleep/modes/debug_survey.py`** — `--resume-db`, `--adaptive`,
  `--adaptive-min`, `--adaptive-max` flags wired through to worker
- **`tests/test_survey.py`** — 25 new tests (67 total): beacon
  fingerprinting, DB resume, adaptive timing

**Phase 5 — Device-Type Classification Accuracy:**

- **Classifier-aware merge** — `_merge_entry()` now uses the
  `DeviceTypeClassifier` result from `entry["type"]` (already computed by
  the adapter layer) instead of blindly using the scan-round transport
  label; cached Classic devices found during the LE scan phase are now
  correctly classified as `"classic"` instead of `"le"`
- **Cached device provenance** — `DeviceSighting.is_cached` flag tracks
  devices returned by BlueZ without active RSSI that are paired/bonded;
  emitted as `"is_cached": true` in `objects`/`grouped` output formats;
  flag clears automatically when device is re-seen with real RSSI
- **`--exclude-cached` flag** — opt-in filter to remove cached/bonded
  devices from survey output; supported in both `bleep survey` and
  `bleep debug survey start`
- **RSSI 0 dBm fix** — `entry.get("rssi") or entry.get("rssi_last")`
  treated RSSI of 0 as falsy and fell through to `rssi_last`; now uses
  explicit `None` check

**Modified files (Phase 5):**

- **`bleep/modes/survey.py`** — `_resolve_device_type()` helper,
  `_CLASSIFIER_TYPE_MAP`, `DeviceSighting.is_cached`, updated
  `_merge_entry()`, `filter(exclude_cached=)`, `format_objects()`,
  `_build_parser()`, `main()`
- **`bleep/modes/debug_survey.py`** — `--exclude-cached` flag,
  `_survey_worker()` param, thread args
- **`bleep/docs/survey_mode.md`** — device-type classification section,
  `--exclude-cached` in command reference, `is_cached` field docs
- **`tests/test_survey.py`** — 23 new tests (90 total): classifier-aware
  merge, cached provenance, exclude filter, RSSI 0 handling, output format

**Modified files:**

- **`bleep/cli.py`** — `survey` subparser (+ `--then-aoi`), `aoi` parser
  (+ `--all`), `report` dispatch (forwards `--all`)
- **`bleep/analysis/aoi_analyser.py`** — `generate_aggregate_report()`,
  `_generate_aggregate_markdown()`, `_generate_aggregate_text()`,
  `_generate_aggregate_json()`
- **`bleep/modes/aoi.py`** — `report` handler supports `--all` aggregate
  mode; `--address` no longer required on report
- **`bleep/modes/survey.py`** — health monitor integration, `--then-aoi`,
  `--no-db` properly wired via `persist_db` param
- **`tests/test_survey.py`** — 4 new tests (36 total): `--then-aoi`
  parsing/validation, health monitor callbacks
- **`tests/test_aoi_augmentation.py`** — 5 new tests: aggregate report
  markdown/JSON/text generation, skip-missing, raise-on-empty
- **`bleep/docs/survey_mode.md`** — `--then-aoi` docs, health monitoring
  section, aggregate report examples
- **`bleep/docs/aoi_mode.md`** — `report --all` docs and examples
- **`bleep/docs/changelog.md`** — this entry

---

## v2.8.4 (2026-05-07)

### MAC Validation — Reject Incomplete/Invalid MACs

Hardened `_normalize_mac()` in `bleep/core/observations.py` to **reject** incomplete
or unparseable MAC addresses instead of storing them verbatim.  Previously, the
function had a permissive fallback (`return mac.upper()`) that allowed garbage
strings, truncated MACs (e.g. `4:A2:F9:BC:8E:95`), and raw D-Bus paths
(e.g. `/ORG/BLUEZ/HCI0/DEV_F4_B6_88_0B_90_22`) into the database.

**Policy:** It is better to drop an observation than to store an erroneous MAC.
Zero-padding short octets is explicitly disallowed — it would be a guess.

**Changes:**

- **`bleep/core/observations.py`**
  - `_normalize_mac()` now returns `None` instead of `mac.upper()` for
    unparseable input (return type changed to `Optional[str]`)
  - Added `None`-guard in every public function that calls `_normalize_mac()`
    (~22 functions): write functions silently skip, read functions return
    appropriate empty defaults
  - `_ensure_device_exists()` and `_ensure_service_exists()` now return the
    normalised MAC (or `None`) so callers can detect rejection
- **`tests/test_aoi_augmentation.py`**
  - Added 8 new `TestNormalizeMac` cases: short octet, missing octet, garbage
    string, raw D-Bus path, non-string input, too many octets, empty string,
    whitespace-only
- **`tests/test_observations_characteristics.py`**
  - Fixed test to use full 6-octet MAC (`AA:BB:CC:DD:EE:FF` instead of `AA:BB`)
- **`tests/test_observations_media.py`**
  - Fixed stubs to use full 6-octet MAC (`AA:AA:BB:BB:CC:CC` instead of `AA:AA`)

### AoI Augmentation — Full Implementation

Complete implementation of the AoI augmentation plan, including all planned
features and the six follow-up fixes discovered during live testing.

**Core scan pipeline rewrite** (`bleep/modes/aoi.py`):
* Removed ~200 lines of dead code (unused report generators, duplicate
  `BytesEncoder` and `_prepare_for_json`)
* New `_scan_target()` unified pipeline: classify → GATT → SDP → pair → deep
* Added `_validate_mac()`, `_classify_device()`, `_discover_sdp()`,
  `_probe_pairing()`, `_perform_deep_reenumeration()`, `_has_auth_annotation()`,
  `_normalise_service_element()` helper functions
* Wired `--deep`, `--timeout`, `--no-db`, `--connectionless`, `--address`
  flags on `scan` subparser
* `--deep` on `analyze` now invokes SDP + pairing probe before analysis
* `db` subcommand added to `known_subcommands` in `cli.py` for proper routing
* `db list` action added to the `db` subparser
* Service normalisation: both `db import` and `db sync` now use
  `_normalise_service_element()` to handle string/dict duality
* v11 field merging: `db import`/`sync` merge `pairing_profile`,
  `sdp_summary`, `post_pair_delta` into analysis before `store_aoi_analysis()`

**AOIAnalyser enhancements** (`bleep/analysis/aoi_analyser.py`):
* `db_only` constructor parameter — suppresses file writes when set
* `_analyse_sdp_records()` — flags exposed Classic profiles (OBEX, FTP, SPP, etc.)
* `_analyse_pairing_profile()` — flags JustWorks, pairing errors
* `_analyse_post_pair_delta()` — summarises post-pair re-enumeration delta
* `analyse_device()` now calls the three new methods for v11 data
* `analyse_device()` service list branch normalises dict elements (extracts `"uuid"`)
* `save_device_data()` merges v11 fields before `store_aoi_analysis()`
* `_generate_recommendations()` uses safe `.get()` for accessibility score
* Report generation (markdown, text, JSON) includes SDP, pairing, and
  post-pair delta sections; services section handles both string and dict elements

**Schema v11** (`bleep/core/observations.py`):
* `aoi_analysis` table gains `pairing_profile`, `sdp_summary`,
  `post_pair_delta` JSON columns
* `store_aoi_analysis()` persists all three v11 fields
* `get_aoi_analysis()` returns v11 fields when present
* v10→v11 migration adds columns via `ALTER TABLE`
* `_normalize_mac()` hardened: handles D-Bus paths, dash-separated MACs,
  whitespace; uses compiled regex patterns

**CLI fixes** (`bleep/cli.py`):
* `import signal` + `SIGPIPE` handler in `main()` prevents `BrokenPipeError`
  when piping `db list` output
* `"db"` added to `known_subcommands` for AoI routing

**Scan log fix** (`bleep/ble_ops/le/scan.py`):
* `_native_scan` debug message changed from `LOG__GENERAL` to `LOG__DEBUG`

**Tests** (`tests/test_aoi_augmentation.py`):
* 58 tests covering all new helpers, analysis methods, schema v11 round-trips,
  report generation, service normalisation, MAC validation, and `_prepare_for_json`

### AoI service-data normalisation, MAC validation & output fixes

Six fixes addressing gaps discovered during live AoI testing.

* **Fix 1 — `analyse_device()` crashes on DB-loaded service data**
  (`bleep/analysis/aoi_analyser.py`).
  `observations.get_device_detail()` returns `services` as a list of
  SQLite row dicts (`[{"uuid": "...", "id": 1, ...}]`), but the list
  branch in `analyse_device()` iterated each element as a bare UUID
  string and passed the dict to `get_name_from_uuid()`, which performed
  `uuid in constants.UUID_NAMES` — hashing a dict → `TypeError:
  unhashable type: 'dict'`.  The list branch now normalises each
  element: dicts have their `"uuid"` key extracted; strings are used
  directly.

* **Fix 2+3 — `db import` / `db sync` crash on DB-loaded service data**
  (`bleep/modes/aoi.py`).
  Both the `db import` and `db sync` Step 2 code paths built service
  rows with `[{"uuid": u} for u in device_data["services"]]`.  When
  `u` was already a dict (DB row), this produced `{"uuid": <dict>}`,
  and `_normalize_uuid()` called `.strip()` on the nested dict →
  `AttributeError: 'dict' object has no attribute 'strip'`.  Both
  comprehensions now pass through existing dicts unchanged and wrap
  only bare strings.

* **Fix 4 — `[DEBUG] _native_scan returning N devices` leaks to user
  output** (`bleep/ble_ops/le/scan.py`).
  The log call used `LOG__GENERAL` (always-visible) instead of
  `LOG__DEBUG`.  Changed to `LOG__DEBUG`.

* **Fix 5 — `_normalize_mac()` accepts D-Bus object paths as MACs**
  (`bleep/core/observations.py`).
  `_normalize_mac()` only called `.upper()` with no format validation,
  allowing strings like `/org/bluez/hci0/dev_F4_B6_88_0B_90_22` to be
  stored as MAC addresses.  Now validates standard `XX:XX:…` format,
  converts dash-separated MACs to colons, and extracts MACs from D-Bus
  object paths automatically.  Also moved `import re` to top-level
  imports and removed the duplicate mid-file import.

* **Fix 6 — `BrokenPipeError` when piping BLEEP CLI output**
  (`bleep/cli.py`).
  Added `signal.signal(signal.SIGPIPE, signal.SIG_DFL)` at the start
  of `main()` so piped commands (e.g. `bleep db list | head`) exit
  cleanly without a Python traceback.

* **Test assertion fix** (`tests/test_device_type_integration.py`).
  Updated `test_schema_v6_migration` to expect schema version 11
  (was pinned to 10 from before the v11 AoI augmentation).

* **New tests** (`tests/test_aoi_augmentation.py`).
  Added 11 new tests: `TestServiceDataNormalisation` (3 tests for
  string-list, dict-list, and comprehension normalisation) and
  `TestNormalizeMac` (8 tests for standard, D-Bus path, dash-separated,
  whitespace, empty, and None inputs).  Total: 54 tests.

### Audio profile activation, recording reliability & profile identity fixes (2026-04-21)

Five focused fixes addressing the behavioural gaps catalogued in
`workDir/Audio/README.audio-troubleshooting-once-more` — why different
connect paths (`bleep connect` vs `bleep classic-connect` vs `bleep
pair`) led to divergent `audio-profiles` output, why `audio-record`
sometimes reported `"Recording failed"` despite producing a playable
WAV, and why a BlueZ input node was mis-classified as A2DP Source.

* **Fix 1 — Opt-in BlueZ profile activation after RFCOMM bring-up**
  (`bleep/pairing/__init__.py`, `bleep/modes/pair.py`,
  `bleep/modes/classic_connect.py`, `bleep/cli.py`).
  `classic_connect_sdp_rfcomm()` now accepts a keyword-only
  ``activate_profiles: bool = True``.  When SDP reports an
  audio-profile UUID (A2DP / HFP / HSP / AVRCP — normalised via
  `AUDIO_SERVICE_UUIDS`), the helper issues a best-effort
  `Device1.Connect()` after RFCOMM bring-up so BlueZ attaches its
  profile handlers and the device appears in
  `bleep audio-profiles` without a subsequent `amusica status`
  round-trip.  The call is idempotent, non-fatal, and logged at
  DEBUG on failure.  Two small helpers (`_svc_map_has_audio_uuid`,
  `_activate_bluez_profiles`) keep the surface testable.
  `bleep classic-connect`, `bleep connect` (Classic auto-route) and
  `bleep pair` gain a matching `--no-profiles` flag for operators
  that prefer the legacy RFCOMM-only behaviour.

* **Fix 2 — `get_profiles_for_card` regex & pattern normalisation**
  (`bleep/ble_ops/audio/audio_tools.py`).
  The profile-line regex was `r"^\s+[a-z0-9_]+:"` which silently
  dropped every hyphenated PipeWire profile name (`a2dp-sink`,
  `headset-head-unit`), leaving only the literal `off` entry and
  driving operator confusion ("card parked at off").  Widened to
  `r"^\s+[a-z][a-z0-9_-]*:"` and the surrounding
  `identify_bluetooth_profiles_from_alsa` now normalises both
  pattern keys and candidate names (`-` → `_`, lower-cased) before
  membership checks so hyphenated and underscored forms resolve
  identically.  The `Active Profile:` header is still excluded
  explicitly.

* **Fix 3 — `amusica status` surfaces the Active profile**
  (`bleep/modes/amusica.py`).
  Extended the card-info block to emit `Available profiles` and
  `Active profile` on separate lines using the existing
  `get_active_profile_for_card()` helper, so operators no longer
  have to infer the active profile from the `ss` source/sink list.

* **Fix 4 — `record_from_source` timeboxing & stderr capture**
  (`bleep/ble_ops/audio/audio_tools.py`).
  `parecord` and `pw-record` accept no duration flag, so the
  previous `subprocess.run(..., timeout=duration+10)` path raised
  `TimeoutExpired` and reported `False` even when the WAV was
  fully written to disk.  New private helper `_run_popen_timed`
  spawns the recorder via `Popen`, arms a `threading.Timer` that
  sends `SIGINT` after `duration_sec`, lets the recorder flush
  the WAV header/trailer cleanly, and returns `True` iff the
  process exited cleanly **and** the output file exists with
  more than 44 bytes (header-only guard).  stderr tails are
  logged at DEBUG on failure.  The `arecord` path retains its
  native `-d` handling; only the stderr capture is additive.

* **Fix 5 — Profile identity via PipeWire bluez5 properties**
  (`bleep/ble_ops/audio/audio_tools.py`).
  `_get_pipewire_bluez_nodes` now captures `api.bluez5.profile`,
  `api.bluez5.codec`, and `device.profile.name` from the `pw-dump`
  JSON; `list_audio_sinks`/`list_audio_sources` propagate them into
  the returned dicts; and `identify_bluetooth_profiles_from_alsa`
  prefers these authoritative values over node-name pattern
  matching.  This stops `bluez_input.<mac>.0` being classified as
  A2DP Source when it is actually an HSP/HFP capture node, which
  was the root cause of the "HSP interfaces showing under A2DP"
  observation.

* **Documentation** —
  * `workDir/Audio/README.audio-troubleshooting-once-more`:
    "Resolution Notes" section appended describing each fix,
    the observable symptoms they address, and the manual
    verification recipe (`bleep classic-connect <MAC>`,
    `bleep amusica status <MAC>`, `bleep audio-record …`).
  * `bleep/docs/todo_tracker.md`: updated with the five fixes
    and their verification matrix.

* **Regression coverage** — `tests/test_audio_regressions.py`
  (10 tests) mocks every external binary and covers: hyphenated
  profile surfacing, pattern normalisation, `amusica status`
  active-profile output, SIGINT-based recorder success/failure,
  pw-dump props extraction and classifier precedence, and both
  branches of the opt-in profile-activation flag.

### `bleep debug` CLI subcommand & hint-convention enforcement (2026-04-17)

Two related fixes addressing operator confusion when CLI commands emitted
hints that pointed at debug-shell-only tokens (e.g. `audio-recon`'s
`(see 'audiocfg --endpoints' for details)`) without explaining how to
reach the debug shell — and the closely related issue that the debug
shell was undiscoverable from `bleep --help` and only reachable via
`python -m bleep.modes.debug`.

* **`bleep debug` subcommand** — a new top-level subparser registered in
  `bleep/cli.py` mirrors the option matrix of
  `bleep.modes.debug.parse_args()` (`device` positional, `-m/--monitor`,
  `-n/--no-connect`, `-d/--detailed`).  Dispatch is delegated to
  `bleep.modes.debug.main()` via the new `_rebuild_debug_argv()` helper,
  which preserves a single source of truth for the debug shell's CLI
  surface.  The legacy `python -m bleep.modes.debug` invocation is
  **unchanged and fully supported** — both forms are equivalent.

* **CLI hint convention** — formalised in `bleep/docs/cli_usage.md`
  ("Hint convention" section).  Any user-facing string emitted from a
  CLI-reachable code path that references a debug-shell command token
  (`audiocfg`, `mediaenum`, `audioplay`, `copp`, `csdp`, …) must also
  contain either `bleep debug` or the literal phrase `Debug Mode`.
  Canonical wording: `(in Debug Mode: '<command>')`.  Bare references
  like `(see 'audiocfg --endpoints' for details)` are forbidden.

* **Hint string fixes** — three CLI-reachable violations corrected:
  * `bleep/ble_ops/audio/audio_recon.py` — `audio-recon` summary now
    emits `(in Debug Mode: 'audiocfg --endpoints')`.
  * `bleep/dbuslayer/media_stream.py` — both the warn-severity
    contention addendum and the post-timeout `BLEEPError` body reworded
    to frame `audiocfg` / `mediaenum` references with `In Debug Mode:`.
  * `bleep/dbuslayer/obex_opp.py` — `OPP ExchangeBusinessCards is not
    supported` `RuntimeError` (raised across the `bleep classic-opp`
    path) reworded to frame `'copp send'` and `'copp pull'` with
    `In Debug Mode:`.

* **Lint enforcement** — `tests/test_cli_hint_convention.py` AST-walks
  every Python module under `bleep/` (excluding the debug-shell modules
  themselves), flags any string literal that contains a known
  debug-shell command token without a convention marker, and supports a
  small per-file allow-list keyed on `(relative_path, substring)` for
  internal docstrings that are never user-visible.  12 tests in total
  (one full-walk lint + 8 matcher self-tests + 3 marker / allow-list
  sanity checks).

* **Subcommand tests** — `tests/test_cli_debug_subcommand.py` (13
  tests) covers `_rebuild_debug_argv()` for every flag combination,
  parser registration (mode is `"debug"`, accepts positional MAC,
  `--help` exits 0 with the expected option matrix), dispatch
  (`bleep debug` calls `bleep.modes.debug.main` with the rebuilt argv,
  propagates non-zero exit, treats `None` return as `0`), and the
  parity guarantee that `bleep.modes.debug.parse_args()` consumes the
  rebuilt argv form unchanged.

* **Documentation** —
  * `bleep/docs/cli_usage.md`: added `debug` row to the
    Agent & Configuration table; added the "Hint convention" section.
  * `bleep/docs/debug_mode.md`: launch section now lists `bleep debug`
    as the canonical form alongside `python -m bleep.modes.debug`.
  * `bleep/docs/README.md` and `bleep/docs/ble_scan_modes.md`: cross
    references updated to mention both invocation forms.
  * `bleep/modes/debug.py`: stale module-level usage docstring updated
    (was `python -m bleep -m debug`, which never worked).

Files touched: `bleep/cli.py`, `bleep/modes/debug.py`,
`bleep/dbuslayer/media_stream.py`, `bleep/dbuslayer/obex_opp.py`,
`bleep/ble_ops/audio/audio_recon.py`, `bleep/docs/cli_usage.md`,
`bleep/docs/debug_mode.md`, `bleep/docs/README.md`,
`bleep/docs/ble_scan_modes.md`, `tests/test_cli_debug_subcommand.py`,
`tests/test_cli_hint_convention.py`.

### MediaEndpoint1 contention pre-flight (2026-04-17)

Previously, `audioplay` / `audiorec` would cycle the device connection,
register a BLEEP-owned `MediaEndpoint1`, then block in
`wait_for_transport()` for 15 s when BlueZ's `a2dp_select_eps` picked a
pre-existing BlueALSA / PipeWire / PulseAudio endpoint over ours.  The
timeout gave no structured hint about *why* selection lost the race, and
every audio capture attempt on a BlueALSA-first host hit the same wall.

This release adds a proactive pre-flight that detects the contention
**before** the device is cycled, short-circuits the failure mode with an
actionable message, and surfaces the same diagnostic in `audiocfg`,
`mediaenum`, and `audio-recon` so operators can assess the host state
without attempting a stream.

* **`bleep.core.preflight.check_endpoint_contention()`** — new public
  helper returning an :class:`EndpointContentionReport` with per-backend
  :class:`EndpointOwner` attribution and a four-level
  severity (`none`/`info`/`warn`/`block`).  Two probe layers:

  * *Primary* (default, zero cost): infers competitors from the structured
    `_check_bluetooth_audio_stack_detailed()` snapshot and the existing
    BlueALSA PCM enumeration.  Sufficient for every failure report we have
    on file.
  * *Deep* (`deep_probe=True`): authoritative walk via
    `org.freedesktop.DBus.ListNames` → per-name `Introspect` for the
    `org.bluez.MediaEndpoint1` interface → `GetConnectionUnixProcessID`
    → `/proc/<pid>/comm`.  All D-Bus calls are wrapped in
    `bleep.dbus.timeout_manager.call_method_with_timeout` so a congested
    bus cannot hang the scan (default 3 s per call).

* **`MediaStreamManager` runtime gate** — `_acquire_via_endpoint()` now
  invokes the primary probe before `BleepMediaEndpoint.register()`.  When
  severity is `"block"` (BlueALSA active — the observed failure mode),
  the manager raises a `BLEEPError` with the full contention report
  *before* cycling the device.  `severity="warn"` is logged and allowed
  to proceed; the post-timeout path re-runs the probe with
  `deep_probe=True` and re-injects the owner list into the raised error
  so the operator sees exactly which bus name, PID, and object path won
  the AVDTP selection race.

* **`--force-endpoint` override** — added to the debug shell's
  `audioplay` / `audiorec` and to the top-level `audio-play` /
  `audio-record` CLI subcommands, and threaded through
  `MediaStreamManager(force_endpoint=…)` for tests/integrators.  Use when
  the competing daemon is known to release the endpoint during the
  cycle, or for diagnostic purposes.

* **Debug-shell surfaces** — `audiocfg` always prints an "Endpoint
  contention" section (primary probe by default); `audiocfg --endpoints`
  upgrades to the deep probe.  `mediaenum` gained a `--endpoints` flag
  that appends the same report after the D-Bus enumeration, covering the
  "no media interfaces found" path so operators always see *why* the
  device has no BlueZ-visible endpoints.

* **`audio-recon` summary line** — `run_audio_recon()` now emits a
  one-line `[!] Endpoint contention: severity=… competitors=…` message
  (promoted to `USER` level for `warn`/`block`, `DEBUG` otherwise) and
  records the same data in the result dict under
  `endpoint_contention: {severity, competitors: [...]}`.

* **Documentation** — `bleep/docs/todo_tracker.md` entry for this item
  is now **COMPLETE** with the corrected probe strategy
  (`ListNames` + introspection — `GetManagedObjects()` does not republish
  externally registered endpoints).  Nine new unit tests cover the
  primary probe (five severity scenarios), the deep probe (monkeypatched
  D-Bus + synthesised introspection XML, including BLEEP self-exclusion),
  and the runtime gate (both blocking and `force_endpoint=True` bypass).

Files touched: `bleep/core/preflight.py`, `bleep/dbuslayer/media_stream.py`,
`bleep/modes/debug_media.py`, `bleep/cli.py`,
`bleep/ble_ops/audio/audio_recon.py`, `tests/test_preflight.py`,
`bleep/docs/todo_tracker.md`.

### Audio diagnostic & debug-shell parser fixes (2026-04-17)

Field reports showed that a Bluetooth headset advertising A2DP/HFP could be
paired and connected (BlueZ `Connected=yes`) yet remain invisible to
`audiorecon`, `audioplay`, and host tools like `pactl list`.  Root-cause
analysis pointed to two distinct failures in the BLEEP audio layer plus one
fragile piece of debug-shell UX.  The following targeted changes address the
items that belong inside the BLEEP codebase (host-side stack conflicts remain
the operator's responsibility but are now surfaced clearly).

* **`audio_tools.identify_bluetooth_profiles_from_alsa()` now merges BlueALSA
  PCMs** — BLEEP previously enumerated sinks/sources only via
  PulseAudio/PipeWire (`pactl`, `pw-dump`) and PulseAudio BlueZ cards.  On
  BlueALSA-only hosts (where BlueALSA owns BlueZ's `MediaEndpoint1`
  interfaces) the correlator returned an empty mapping even though the
  headset was reachable.  BlueALSA PCMs listed by `bluealsa-cli list-pcms`
  are now parsed into the same result shape, with `pcm_path`, `alsa_device`,
  and `backend="bluealsa"` metadata, and classified into A2DP Sink/Source
  (for `a2dp/{sink,source}`) or HFP AG/HF (for `sco/{sink,source}`).  This
  feeds `AudioProfileCorrelator.identify_profiles_for_device()` with no
  callsite changes.
* **`preflight._check_bluetooth_audio_stack_detailed()`** — new structured
  probe returning per-backend `{present, running|loaded, plugin_installed,
  plugin_loaded, status}` dicts where `status ∈ {active, installed, absent}`.
  BlueALSA is probed by actually running `bluealsa-cli list-pcms` (not just
  `which`), PulseAudio by inspecting `pactl list modules short`, and
  PipeWire by distinguishing `libspa-bluez5.so` on disk from `bluez` nodes
  being visible in `pw-cli list-objects`.  The legacy
  `_check_bluetooth_audio_stack()` is retained as a thin back-compat wrapper
  that collapses to `Dict[str, bool]` with the exact historical semantics
  (so `PreflightReport` / `diagnose_audio` behave identically).
* **`preflight._detect_audio_stack_conflicts()`** — new helper emits
  human-readable warnings when multiple backends claim BlueZ endpoints
  (e.g. BlueALSA active alongside an active PulseAudio/PipeWire Bluetooth
  module) or when the PipeWire bluez5 plugin is installed but not loaded
  into the graph.  The first is the exact failure mode observed in the
  field (endpoints race, the loser's devices never appear as sinks/sources).
* **`debug_media.cmd_audiocfg` rewritten** — now renders the structured
  per-backend status, any conflict/gap warnings, and *conditional,
  non-prescriptive* remediation: it only suggests start/stop commands for
  backends that are actually installed on the host, and explicitly notes
  that BLEEP does not prescribe one stack over another.  Pure ALSA +
  BlueALSA deployments are treated as a first-class option.
* **`media_stream.MediaStreamManager._acquire_via_endpoint` timeout error
  rewritten** — the previous message ("BlueZ did not assign a transport
  within the timeout") misled users into thinking the remote device lacked
  the endpoint.  In practice the usual cause is that BlueZ's
  `a2dp_select_eps` picked a competing (pre-registered) endpoint owned by
  BlueALSA/PipeWire/PulseAudio rather than the BLEEP endpoint, so
  `SetConfiguration` was never dispatched to BLEEP.  The new message names
  the actual mechanism, enumerates the three common causes (backend
  contention, incompatible endpoint/codec, AVDTP discovery timing), and
  points to `audiocfg` / `mediaenum` / `--direct` as next steps.
* **`debug_media.cmd_audioplay` / `cmd_audiorec` switched to `argparse`** —
  the previous hand-rolled `List[str]` parser treated `--system <path>` as
  `<file>=--system`, failed to expand `~` in paths (resulting in
  "file not found" on plainly-valid inputs), and swallowed `--help`.  Both
  commands now build an `argparse.ArgumentParser(prog=..., add_help=False)`
  with a `try/except SystemExit` usage-print block — matching the house
  style already in `debug_classic_obex.py` and `debug_classic_rfcomm.py` —
  and normalise the file path with
  `os.path.expandvars(os.path.expanduser(...))` before passing it into
  `system_play` / `MediaStreamManager.play_audio_file` / `record_audio`.
  No downstream behaviour changes.
* **`docs/todo_tracker.md`** — added a "MediaEndpoint1 Contention Pre-flight
  (2026-04-17) – FUTURE WORK" section detailing the design for a pre-flight
  that would detect the endpoint race before `_acquire_via_endpoint` cycles
  the device connection.  Intentionally deferred until the diagnostic
  changes above are validated in the field.

### MAP CLI folder enumeration fix

* **`classic-map folders` now shows full folder hierarchy** — The command
  was calling the flat `list_folders()` (single `ListFolders` at the MAP
  root), which only returned the top-level entry (e.g. `telecom/`).
  Re-wired to use the recursive `list_folder_tree()` / `walk_folder_tree()`
  that already existed in the operations layer and was correctly used by the
  debug-mode `cmap folders` command.  The output now renders the full
  indented tree and prints a summary of valid message-leaf folder paths.
* **`classic-map list` graceful recovery on non-leaf folders** — When the
  remote MAS returns OBEX "Bad Request" (indicating the user specified an
  intermediate folder that contains subfolders, not messages), BLEEP now
  enumerates the device's folder tree and prints the valid message-folder
  paths as actionable suggestions.  Mirrors the `_suggest_map_leaf_folders`
  pattern already used in the debug-mode `cmap list` command.

## v2.8.3 (2026-04-09)

### Circular-import & import-correctness fixes

Comprehensive review of the import graph to eliminate the "partially
initialised module" error observed when running `media-ctrl` and `explore`
commands.

* **Deferred heavy imports in `modes/media.py`** — Module-level imports of
  `dbuslayer.device_le` and `dbuslayer.media` moved into per-function lazy
  helpers (`_get_device_le_class`, `_get_media_helpers`) so that the
  `device_le` module is not pulled in before the signal system finishes
  initialising.
* **Deferred heavy imports in `modes/exploration.py`** — `Adapter`,
  `LEDevice`, and `scan_and_connect` imports moved into `main()`.  Scan-mode
  constants (`PASSIVE_MODE` etc.) remain eagerly imported since they are
  plain strings with no D-Bus side-effects.
* **Lazy signals-manager singleton (`dbuslayer/device_le.py`)** — Replaced
  the module-level `_signals_manager = _SignalsRegistry()` (which called
  `dbus.SystemBus()` at import time) with a `_get_signals_manager()` lazy
  getter.  All call-sites updated.
* **Deferred `integrate_with_bluez_signals()` in `bleep/__init__.py`** —
  The D-Bus signal integration is no longer executed eagerly at package
  import; instead it runs on first demand via `_ensure_bluez_signals()`.
  `patch_signal_capture_class()` remains eager (safe, no D-Bus ops).
* **Fixed broken import name in `core/preflight.py`** — Changed
  `system_dbus__bluez_device__le` → `system_dbus__bluez_device__low_energy`
  (the class that actually exists in `device_le.py`).
* **Fixed stale import path in `core/device_management.py`** — Two deferred
  imports of `system_dbus__bluez_device__low_energy` now reference
  `bleep.dbuslayer.device_le` directly instead of the shim
  `bleep.dbuslayer.device` (which eagerly loads both `device_le` and
  `device_classic`).
* **Guarded `observations` import in `modes/exploration.py` and
  `modes/db.py`** — Both modules now wrap the `bleep.core.observations`
  import in `try/except`, falling back to `None` and degrading gracefully
  when `sqlite3` or other dependencies are unavailable.
* **Removed duplicate GATT property definitions in `core/config.py`** —
  `GATT__SERVICE__PROPERTIES`, `GATT__CHARACTERISTIC__PROPERTIES`, and
  `GATT__DESCRIPTOR__PROPERTIES` were defined twice; the first (shorter)
  definition has been removed, keeping only the authoritative second
  definition that includes `Value`, `Notify`, and `Descriptors` fields.

## v2.8.2 (2026-04-08)

### Fixes — OnePlus 6T debugging findings

* **MAP handle display** — `classic-map list` now correctly extracts the
  message handle from the D-Bus object path instead of showing `?`.  Added
  `-v`/`--verbose` flag to display additional message metadata (Type, Sender,
  DateTime).
* **PBAP watchdog timeout** — Default watchdog increased from 8 s to 30 s
  (CLI `--watchdog` and `pbap_dump_async` default).  Watchdog now resets after
  each successful `Select` call, preventing premature abort on multi-repo
  dumps from slower devices.
* **BIP handle discovery** — Added `classic-bip list` informational subcommand
  documenting how to discover image handles (AVRCP browsing, sequential probe,
  cross-profile).  Added §2.12 "Handle discovery" to `bl_classic_mode.md`.
* **SAP documentation** — Documented BlueZ's server-side-only SAP limitation
  in `bl_classic_mode.md` §2.13; updated `todo_tracker.md` BZ-18 accordingly.

### Host audio stack detection & documentation

Real-world testing confirmed that `gatt-enum` and `media-enum` failures with
`br-connection-profile-unavailable` on dual-mode audio devices (OnePlus 6T,
Samsung S7 Active, and others) are resolved by installing `bluez-alsa-utils`
on the host.  BlueZ `Device1.Connect()` requires a registered profile handler
for at least one remote service; without an audio stack, no handler exists for
A2DP/HFP/HSP profiles.

* **Preflight audio stack detection** — `PreflightReport` now includes
  `bt_audio_stack` (BlueALSA, PulseAudio BT module, PipeWire BT module) and
  `has_bluetooth_audio_stack` property.  `bleep --check-env` prints a
  dedicated "Bluetooth Audio Stack" section with actionable guidance when no
  backend is detected.
* **Contextual hint on profile-unavailable** — When `connect_and_enumerate`
  catches a `profile-unavailable` D-Bus error and the preflight detects no
  audio stack, a hint is printed with the install command before re-raising.
* **Documentation** — Troubleshooting sections added to `gatt_enumeration.md`,
  `bl_classic_mode.md` §4, `media_mode.md` §1, and `audio_recon.md`.
* **Observations** — New O-17 (field observation) and L-16 (lesson learned)
  documenting the host audio stack as a `Device1.Connect()` prerequisite.

## v2.8.1 (2026-04-02)

### BlueZ Gap Analysis Sprint 2 — LE Advertising (2026-04-02)

* **BZ-6: LEAdvertisement D-Bus object** — new ``dbuslayer/le_advertising.py``
  module providing ``LEAdvertisement`` (``dbus.service.Object`` exposing
  ``Type``, ``ServiceUUIDs``, ``ManufacturerData``, ``LocalName``,
  ``Appearance``, ``Discoverable``, ``TxPower``, ``MinInterval``/
  ``MaxInterval``, ``SecondaryChannel``, ``Data``, ``Includes``, ``Timeout``
  and more via ``GetAll``; ``Release()`` callback from bluetoothd) and
  ``AdvertisementConfig`` dataclass for structured configuration.
* **BZ-7: LEAdvertisingManager wrapper + CLI** — ``LEAdvertisingManager``
  wraps ``LEAdvertisingManager1`` on the adapter for ``register``/``unregister``
  and capability queries (``SupportedInstances``, ``ActiveInstances``,
  ``SupportedIncludes``, ``SupportedSecondaryChannels``, ``SupportedFeatures``,
  ``SupportedCapabilities``).  New ``bleep advertise`` CLI subcommand with
  ``caps`` (show capabilities) and ``start`` (register advertisement with
  service UUIDs, manufacturer data, local name, RSSI, interval, channel,
  discoverable flag — broadcast until Ctrl-C or duration limit).
* **Constants** — ``LE_ADVERTISEMENT_BASE_PATH`` added to ``bt_ref/constants.py``.

### BlueZ Gap Analysis Sprint 4 — Advertisement Monitor (2026-04-02)

* **BZ-11: AdvMonitor D-Bus objects** — new ``dbuslayer/adv_monitor.py`` module
  providing ``AdvMonitor`` (per-monitor ``dbus.service.Object`` with ``Activate``,
  ``Release``, ``DeviceFound``, ``DeviceLost`` callbacks), ``AdvMonitorApp``
  (application root implementing ``ObjectManager`` with child lifecycle), and
  helper dataclasses ``MonitorPattern``, ``RSSIConfig``, ``MonitorCallbacks``.
  AD type constants (Flags, UUID16/128, Name, Manufacturer, Appearance, etc.)
  included for convenience.
* **BZ-12: AdvMonitorManager + CLI** — ``AdvMonitorManager`` wraps
  ``AdvertisementMonitorManager1`` on the adapter for ``register``/``unregister``
  and capability queries (``SupportedMonitorTypes``, ``SupportedFeatures``).
  New ``bleep monitor`` CLI subcommand with ``caps`` (show capabilities) and
  ``start`` (register pattern monitors, stream real-time ``FOUND``/``LOST``
  events with RSSI thresholds and optional duration limit).
* **Constants** — ``ADV_MONITOR_INTERFACE``, ``ADV_MONITOR_MANAGER_INTERFACE``,
  ``ADV_MONITOR_APP_BASE_PATH`` added to ``bt_ref/constants.py``.

### BlueZ Gap Analysis Sprint 1 — GATT Acquire & Disconnect Signal (2026-04-02)

* **BZ-1: GATT AcquireWrite / AcquireNotify** — ``Characteristic`` now exposes
  ``acquire_write()`` and ``acquire_notify()`` returning a Unix fd + negotiated
  MTU for zero-copy streaming.  Convenience helpers ``write_value_fd()`` and
  ``read_notify_fd()`` auto-acquire on first use and fall back to the standard
  ``WriteValue``/``StartNotify`` path when the remote characteristic does not
  support the acquire methods.  ``release_acquired()`` closes all fds.
* **BZ-2: WriteAcquired / NotifyAcquired properties** — ``Characteristic.__init__``
  now reads these booleans from D-Bus (same pattern as ``MTU``/``Notifying``).
  Enumeration output in ``conversion.py`` and ``device_le.py`` includes them.
* **BZ-8: Device1 Disconnected signal** — ``signals.py`` now subscribes to the
  ``Disconnected`` signal on ``org.bluez.Device1``, capturing the structured
  reason string (e.g. ``org.bluez.Reason.Timeout``) and human-readable message.
  ``DISCONNECT_REASON_MAP`` from ``error_handling.py`` is wired for translation.
  ``get_disconnect_reason(device_path)`` API added.  Registered devices receive
  an ``on_disconnected(reason, message)`` callback.

### Bluetooth Mesh Skeleton (2026-04-02)

* **Full ``bleep/mesh/`` package** built from ``workDir/bluez/doc/mesh-api.txt``:
  - ``constants.py`` — All D-Bus paths, interface names, and error codes.
  - ``errors.py`` — ``MeshError`` hierarchy mapping ``org.bluez.mesh.Error.*``.
  - ``network.py`` — ``MeshNetwork`` client for ``Network1`` (join/attach/leave/
    create/import).
  - ``node.py`` — ``MeshNode`` client for ``Node1`` (send/publish/key mgmt,
    node properties).
  - ``management.py`` — ``MeshManagement`` client for ``Management1``
    (unprovisioned scan, subnet/appkey CRUD, remote node management, key export).
  - ``application.py`` — ``MeshApplication`` D-Bus service skeleton
    (``JoinComplete``/``JoinFailed`` callbacks, ``ObjectManager``).
  - ``element.py`` — ``MeshElement`` D-Bus service skeleton
    (``MessageReceived``/``DevKeyMessageReceived``/``UpdateModelConfiguration``).
  - ``provisioner.py`` — ``MeshProvisioner`` D-Bus service skeleton
    (``ScanResult``/``RequestProvData``/``AddNodeComplete``/``AddNodeFailed``).
  - ``provision_agent.py`` — ``MeshProvisionAgent`` D-Bus service skeleton
    (OOB key exchange, capabilities properties).
* **``proxy_solicitation.py`` corrected** — API calls now match ``mesh-api.txt``:
  ``Network1.Attach(app_root, token)`` (was 0-arg) and
  ``Node1.Send(element_path, dest, key_index, options, data)`` (was 4-arg).
* **``__init__.py`` updated** — lazy loading for heavy D-Bus modules; ``__all__``
  lists only eagerly-loaded modules.

### Media Enumeration Expansion (2026-04-02)

* **Non-verbose player output expanded** — ``bleep media-enum <MAC>`` now
  returns ``type``, ``subtype``, ``position``, ``repeat``, ``shuffle``,
  ``browsable``, ``searchable`` in addition to ``name``, ``status``, ``track``.
* **AVRCP labels added** — ``AUDIO_PROFILE_NAMES`` in ``bt_ref/constants.py``
  now includes ``AVRCP Target`` and ``AVRCP Controller`` entries; transports
  with AVRCP UUIDs no longer display ``"Unknown Profile"``.
* **``--verbose`` includes D-Bus object tree** — ``find_media_objects()`` output
  added to verbose JSON under ``media_objects`` key.
* **``--browse`` flag** — New flag enumerates top-level folder contents via
  ``MediaFolder1.ListItems`` when the player is browsable.
* **``media_mode.md`` updated** — Documented ``--verbose``, ``--browse``,
  ``--monitor`` flags; removed phantom ``--objects``; examples require MAC.

### Documentation Drift Fixes & v2.8.1 Deprecation Removal (2026-04-02)

* **`map.py` docstring corrected** — Module header no longer claims "No
  multi-instance MAS support"; the `list_mas_instances()` function and the
  `instance` parameter have been implemented across all session-based operations
  since v2.7.8.
* **`mainloop_architecture.md` status updated** — Line 4 changed from
  "not yet implemented" to "partial implementation tracked below" to reflect the
  mix of Open and Done items in the Related Work Items table.
* **`media_mode.md` aligned with CLI** — Removed phantom `--objects` flag;
  examples now show the required MAC positional argument and the actual flags
  (`--verbose`, `--browse`, `--monitor`).
* **`modes/aoi.py` planning comment cleaned** — Replaced multi-line `## TODO`
  stub with a single-line tracker cross-reference.
* **v2.8.1 deprecated modules removed:**
  - Deleted `bleep/compat.py` (zero internal callers since v2.6).
  - Deleted `bleep/bt_ref/bluetooth_exceptions.py` (shim; use `bt_ref.exceptions`).
  - Deleted `bleep/bt_ref/bluetooth_constants.py` (shim; use `bt_ref.constants`).
  - Deleted `bleep/bt_ref/bluetooth_utils.py` (shim; use `bt_ref.utils`).
  - Removed dead legacy-loader comment block from `bleep/bt_ref/__init__.py`.
  - Updated docstring references in `core/config.py`, `core/errors.py`, and
    `core/constants.py` to use canonical module paths.

### PAN Reliability Fixes (2026-04-01)

* **Post-connect verification** — `NetworkClient.connect()` in
  `bleep/dbuslayer/network.py` now waits 500 ms and checks the `Connected`
  D-Bus property before returning.  If the BNEP session dropped immediately
  (remote device refused the role or L2CAP/BNEP negotiation failed), a
  descriptive `RuntimeError` is raised instead of falsely reporting success.
* **Debug mode: retained PAN objects** — `cmd_cpan` in
  `bleep/modes/debug_classic_profiles.py` now stores the `NetworkClient`
  and `NetworkServer` instances on `DebugState.pan_client` /
  `DebugState.pan_server`, keeping the D-Bus bus name alive for server
  registrations and enabling clean `Disconnect()` calls.
* **CLI `classic-pan serve` long-lived process** — The `serve` action now
  blocks with `signal.pause()` after registering the PAN server, keeping
  the D-Bus bus name alive.  Ctrl-C cleanly unregisters and exits.
  BlueZ's `NetworkServer1.Register()` tears down the server when the
  calling D-Bus client exits (confirmed in `profiles/network/server.c`).
* **`upsert_pan_access()` implemented** — Added the missing observation
  function in `bleep/core/observations.py`.  Updates `last_seen` on the
  device row.  Previously the calls in `pan.py` silently failed due to
  `AttributeError` swallowed by bare `except`.
* **Unused imports removed** — `PAN_PANU_UUID_SHORT`, `PAN_NAP_UUID_SHORT`,
  `PAN_GN_UUID_SHORT`, `List`, `LOG__DEBUG` removed from
  `bleep/ble_ops/classic/pan.py`.
* **Documentation corrected** — `network_capability_summary.md` no longer
  claims PAN is "fully operational"; bc-39 file path fixed in
  `bl_classic_mode.md`; behaviour notes added for post-connect verification
  and `serve` blocking.
* **`pan_connection_analysis.md` created** — New reference document chronicling
  BlueZ source code audit findings: D-Bus client lifetime for `Network1` vs
  `NetworkServer1`, `g_dbus_add_disconnect_watch` usage table across BlueZ
  interfaces, BNEP transport failure root-cause analysis, comparison with Agent
  Pairing D-Bus issues, complete requirements checklist for establishing a
  working PAN NAP connection, and a diagnostic troubleshooting guide.
  Cross-referenced from `network_capability_summary.md`,
  `network_capability_plan.md`, `dbus_documentation_index.md`, and
  `README.md`.

### Phase 5: Package Hygiene and Documentation (2026-04-01)

* **Deprecated `bluetooth_uuids.py` removed** — `bleep-mcp` imports migrated
  from `bleep.bt_ref.bluetooth_uuids` to `bleep.bt_ref.uuids` (canonical,
  auto-generated).  The deprecated 200 KB file is deleted.
* **`protocol_descriptors` column populated** — `upsert_sdp_record()` now
  stores the full ProtocolDescriptorList (attr 0x0004) as JSON.  All three
  SDP parsers (D-Bus XML, sdptool browse XML, sdptool text) extract protocol
  entries with UUID, name, and parameters (PSM, channel, version).
* **`protocols/` noted as design-only** — Docs README now marks
  `bleep/protocols/` as containing design documents only, with no runtime code.
* **`bleep/gatt/` migration decision** — Recorded as future migration target;
  no action until GATT wrappers are mature enough to decouple from `dbuslayer/`.

### Phase 4: Feature Completion & Error Consolidation (2026-04-01)

* **RSSI min/max tracking** — `upsert_device()` now uses `MIN()`/`MAX()` SQL
  to track the observed RSSI range across multiple scan observations.  Scan
  path seeds `rssi_min`/`rssi_max` from each observation.
* **Manufacturer data selection** — Scan enrichment now selects the
  manufacturer entry with the longest payload instead of the first entry,
  reducing data loss for multi-company `ManufacturerData` advertisements.
* **Device type classifier: advertising data** — `_classify_le()` and
  `_classify_dual()` now consume `LE_ADVERTISING_DATA` evidence at STRONG
  weight, so scan-only devices with beacon, CDP, or service-data heuristics
  are classified as `le` instead of `unknown`.
* **Device type classifier: vendor UART** — Vendor UART UUIDs (`FFE0`,
  `FFE1`, `FFF0`, `FFF1`, Nordic UART) elevated from WEAK to STRONG evidence;
  reasoning output updated to mention advertising/heuristic matches.
* **D-Bus error mapping consolidation** — `evaluate__dbus_error()` now
  delegates to `decode_dbus_error()` instead of maintaining its own parallel
  mapping.  `bt_ref/error_map.map_dbus_error` renamed to
  `classify_dbus_error` (alias kept for backward compatibility).
  `DBUS_ERROR_MAP` aligned with the canonical decoder.  Cross-system
  consistency tests added.
* **GATT Service signal propagation** — `Service._props_changed()` now
  updates local state (`primary`, `includes`, `handle`) when
  `GattService1.PropertiesChanged` fires.  Callers can register callbacks via
  `Service.on_property_changed()`.  The global signal hub in `signals.py`
  routes `GATT_SERVICE_INTERFACE` changes to the owning Service object.

### Added

* **`bleep classic-connect` CLI command** — Connect to Bluetooth Classic
  devices via SDP discovery + raw RFCOMM socket, bypassing the
  `Device1.Connect()` profile-handler requirement that causes
  `br-connection-profile-unavailable` for most Classic targets.
  Supports `--check`, `--no-pair`, `--channel`, `--keep`, and
  `--timeout` flags.
* **`bleep connect` Classic auto-routing** — The CLI `bleep connect`
  command now detects BR/EDR and dual-mode devices and automatically
  routes them through the Classic connection path instead of failing
  with `br-connection-profile-unavailable`.  Use `--ble-only` to force
  BLE (GATT) connection even for Classic or dual-mode devices.
* **`classic_connect_sdp_rfcomm()` shared helper** — New function in
  `bleep.pairing` that encapsulates the SDP + raw RFCOMM connection
  pattern used by both CLI and debug mode.
* **`bleep pair` CLI command** — First-class CLI mode for pairing with
  Bluetooth devices.  Supports `--pin`, `--passkey`, `--interactive`,
  `--brute`, `--passkey-brute`, `--probe`, `--check`, `--reset`,
  `--no-connect`, `--no-trust`, and all brute-force tuning flags
  (`--range`, `--pin-list`, `--delay`, `--lockout-cooldown`, etc.).
  Mirrors the full feature set previously only available in the debug
  shell's `pair` command.
* **Pre-pair status check** — Both `bleep pair` and the debug-mode `pair`
  command now query the device's `Paired`/`Trusted`/`Connected` state
  before attempting to pair.  Already-paired devices skip straight to
  connection unless `--reset` is given.  Use `--check` to inspect
  pairing state without pairing.
* **`--reset` flag** — Forces removal of an existing bond via
  `RemoveDevice()` before re-pairing.  Available on both the CLI
  `bleep pair` and the debug-mode `pair` command.
* **`--check` flag** — Reports pairing, trust, and connection state for
  a device without initiating pairing.
* **`bleep.pairing` shared helpers** — New `bleep/pairing/` package
  consolidating `find_device_path`, `resolve_device_for_pair`,
  `remove_stale_bond`, `register_pair_agent`, `check_pair_status`, and
  `report_pair_status`.  Eliminates duplicated pairing preparation
  logic across debug mode, agent mode, classic connect, and brute-force
  modules.
* **Classic device state query methods** — Added `is_paired()`,
  `is_trusted()`, `is_bonded()`, and `is_connected()` to
  `system_dbus__bluez_device__classic`, achieving API parity with the
  LE device wrapper.

### Fixed

* **Debug `connect` is BLE-only** — The debug-mode `connect` command now
  always performs BLE GATT enumeration, restoring its design intent for
  directed LE testing.  Classic connection is handled exclusively by
  `cconnect`.
* **Debug `cconnect` silent failure** — The `cconnect` command in debug
  mode now falls back to SDP + RFCOMM keepalive when
  `Device1.Connect()` fails.  Previously errors were swallowed to the
  debug log with no user-visible output.
* **Debug `_connect_classic` GLib handling** — `_connect_classic` now
  passes `debug_state` to `connect_and_enumerate__bluetooth__classic`,
  enabling correct GLib MainLoop stop/restart during auto-pair.
* **`connect_and_enumerate__bluetooth__classic` paired-device handling**
  — When `Device1.Connect()` fails for an already-paired device (no
  profile handler), the function now skips the redundant auto-pair
  attempt and proceeds directly to SDP discovery.

* **`query_hci_version()`** — Calls ``hciconfig -a <adapter>`` (not bare
  ``hciconfig <adapter>``) so HCI/LMP/Manufacturer lines are present per
  ``hciconfig(1)``; falls back to the basic invocation if ``-a`` fails.
* **RuntimeWarning on ``python -m bleep.modes.debug``** — Replaced eager
  ``import_module`` calls in ``bleep/modes/__init__.py`` with PEP 562
  ``__getattr__``-based lazy imports.  The previous approach placed each
  submodule into ``sys.modules`` before ``runpy`` could execute it as
  ``__main__``, producing the warning on every invocation.
* **``cmap get`` stale folder context** — When ``cmap get`` fails with
  ``UnknownObject`` (handle not materialised in the current OBEX session),
  the error output now displays the active folder context and instructs
  the user to re-run ``cmap list <correct_folder>`` before retrying.
* **MAP push silently rejected by MAS** — bMessage files with bare LF
  (`\n`) line endings and LF-based LENGTH values were silently discarded
  by the remote Message Access Server despite OBEX transfer success.
  Added `normalize_bmessage()` in `bleep/ble_ops/classic/map.py` which
  auto-converts LF→CRLF and recalculates LENGTH before every push.
  Applied via temp-file substitution in `push_message()`, covering all
  push paths (single `cmap push`, batch `cmap push-all`, CLI).
* **`_validate_bmsg_length()` false positives** — Updated the validator
  in `debug_classic_obex.py` to also warn about LF-only line endings
  and to inform the user that BLEEP will auto-normalize before pushing.
* **Test bMessage files** — Converted all 10 test files in
  `workDir/MAP/map_test_messages/` to CRLF line endings with correct
  LENGTH fields matching the CRLF content.
* **`cmap push-all` session exhaustion** — Rapid successive pushes
  caused OBEX session-creation timeouts because `obexd` and the remote
  MAS couldn't tear down the previous session fast enough.  Added a
  configurable inter-push cooldown (default 1.5s via `--delay`) and
  automatic retry-once-on-timeout (3s backoff) to `push_all_messages()`.

### Added

* **`python -m bleep` support** — Added `bleep/__main__.py` so the standard
  `python -m bleep` invocation works (equivalent to `python -m bleep.cli`).
  Updated `docs/cli_usage.md` to reflect the new recommended invocation.
* **`dbuslayer` lazy-loaded submodules** — `bluez_monitor`, `recovery`,
  `agent_io`, `pairing_state`, and `bond_storage` are now properly
  lazy-loaded via `__getattr__` in `bleep/dbuslayer/__init__.py`, matching
  their presence in `__all__`.

### Fixed (Gap Analysis Phase 1)

* **`modes/test.py` stale adapter API** — Replaced `is_powered()` and
  `is_discovering()` with `get_powered()` and `get_discovering()` to match
  the current `system_dbus__bluez_adapter` API (the `is_*` names were
  removed during the v2.7+ cleanup).
* **`identify_uuid()` space-padding** — Removed erroneous
  `target.ljust(32, " ")` from `ble_ops/common/uuid_utils.py` that injected
  space-padded strings into the canonical UUID set, where they could never
  match a real hex UUID.
* **Orphaned bytecode** — Deleted
  `callbacks/examples/__pycache__/auto_pair_accept.cpython-311.pyc` (source
  file was removed but `.pyc` was not cleaned up).

### Added (Gap Analysis Phase 3 — Test Coverage Expansion)

* **`tests/conftest.py`** — New shared test fixtures: `MockAdapter`,
  `MockDeviceInfo`, `dbus_stub` (fake D-Bus module injection), and
  `glib_stub` (fake GLib/GObject injection) for D-Bus-free unit testing.
* **`tests/test_uuid_utils.py`** — 23 tests for `ble_ops/common/uuid_utils.py`:
  `identify_uuid` across 16-bit, 32-bit, 128-bit (BT SIG and custom),
  edge cases (empty, whitespace, mixed-case); `match_uuid` exact/partial/
  case-insensitive/empty matching.
* **`tests/test_preflight.py`** — 18 tests for `core/preflight.py`:
  `DeviceState` dataclass, `PreflightReport` tool aggregation,
  `check_device_state` with mocked LE/Classic paths, `require_adapter`
  success/failure, `_check_bluetooth_tools`/`_check_bluez_version`/
  `_check_bluetooth_config` with mocked filesystem/subprocess, and
  `run_preflight_checks` cache behaviour.
* **`tests/test_sdp_analyzer.py`** — 18 tests for `analysis/sdp_analyzer.py`:
  `SDPAnalyzer`, convenience wrappers, protocol detection
  (RFCOMM/L2CAP/OBEX/BNEP), profile analysis with version distribution,
  version inference with confidence scoring, anomaly detection (multiple
  versions, unusual versions, missing service names), report generation.
* **`tests/test_map_normalize.py`** — 14 tests for `ble_ops/classic/map.py`:
  bMessage `normalize_bmessage` (bare-LF→CRLF, CRLF preservation,
  mixed endings, LENGTH recalculation, multi-block, edge cases),
  `_normalize_for_push` temp-file round-trip.
* **`tests/test_callbacks_base.py`** — 12 tests for `callbacks/base.py`:
  ABC enforcement, `execute` dispatch, `on_load`/`on_unload` lifecycle
  hooks, class attribute defaults and isolation.
* **`tests/test_dbuslayer_service_classic.py`** — 14 mock tests for
  `dbuslayer/service.py` and `device_classic.py`: `Service.__init__`
  (bus vs device), `get_handle` (D-Bus vs path-regex fallback),
  `discover_characteristics` (ObjectManager mock), `device_classic`
  state queries, `pair` success/failure, `connect` already-connected
  short-circuit.

### Changed (Gap Analysis Phase 2 — Consolidation & Cleanup)

* **Canonical BT SIG base UUID** — Fixed truncated `BASE_UUID__BLUETOOTH` in
  `bt_ref/constants.py` (was missing final `B`) and renamed to
  `BT_SIG_BASE_UUID` / `BT_SIG_BASE_UUID_NODASH`.  `uuid_translator.py`
  and `uuid_utils.py` now import from the single canonical source instead
  of each defining their own copy.
* **`compat.py` removal timeline** — Deprecation warning now states
  "will be removed in v2.8.1"; module docstring updated accordingly.
* **Legacy `bluetooth_*.py` shim removal timeline** — `bluetooth_utils.py`,
  `bluetooth_constants.py`, `bluetooth_exceptions.py` in `bt_ref/` now
  carry "Scheduled for removal in v2.8.1" headers.
* **`mesh/__init__.py` restructured** — `__all__` now exports only the
  implemented `proxy` module; planned `agent`/`provisioning` documented
  in the module docstring without polluting the public API.
* **`bl_classic_mode.md` bc-01** — Marked as ✅ completed (the BlueZ D-Bus
  API research was fully realized in the Classic implementation).
* **`network_capability_plan.md` / `network_capability_summary.md`** —
  Updated status markers: Phase 1 + Phase 1b (classic-pan via v2.7.9)
  complete; Phases 2-5 re-labelled as optional future enhancements;
  manual verification with a real PAN device recommended.
* **`mainloop_architecture.md`** — Added "Related Work Items" table
  cross-referencing FW1, F1, F3 from `todo_tracker.md`.

### Added

* **``cmap peek``** — New sub-command that enumerates all MAP leaf folders
  and requests ``MaxCount=1`` from each via ``ListMessages``.  Confirms
  folder accessibility in seconds without triggering the full-listing
  buffer/parse overhead in BlueZ obexd that causes hangs on large folders.
* **``cmap list --count N [--offset M]``** — Optional pagination filters
  for ``ListMessages``.  ``--count`` sets ``MaxCount`` and ``--offset``
  sets ``Offset`` in the MAP Application Parameters, limiting the number
  of messages the remote MAS serialises and obexd must buffer.  Without
  flags, existing behaviour is unchanged (obexd default of 1024).
* **MAP bMessage format reference** — New documentation at
  `bleep/docs/map_bmessage_format.md`: complete bMessage envelope spec with
  inline examples for all 5 message types (`SMS_GSM`, `SMS_CDMA`, `EMAIL`,
  `MMS`, `IM`), LENGTH calculation rules, nested-envelope structure for
  forwarded messages, multi-recipient VCARDs, bulk download/upload
  capabilities and limitations (one file per PushMessage), PushMessage
  optional args (`Transparent`, `Retry`, `Charset`), ListMessages filter
  fields and type filtering, implementation code-path reference table.
* **`cmap download-all`** — Bulk message download: walks the MAP folder tree,
  lists messages in every leaf folder, and downloads each to a local
  directory as individual `.bmsg` files.  Supports `--folders` to restrict
  scope and `--count N` to paginate large folders.
* **`cmap push-all`** — Bulk message upload: iterates `.bmsg` files in a
  directory (or glob), validates bMessage format and LENGTH field, and pushes
  each sequentially.  `--dry-run` validates without pushing.
* **`download_all_messages()` / `push_all_messages()`** — New operations-layer
  functions in `bleep/ble_ops/classic/map.py` providing programmatic bulk
  download and upload with progress callbacks.
* **`collect_leaf_paths()`** — Moved from `debug_classic_obex.py` to
  `bleep/ble_ops/classic/map.py` as a public utility for flattening MAP
  folder trees.  Debug layer delegates to this implementation.

## v2.8.0 – Final Release (2026-03-27)

### Fixed

* **P0-1 FK safety gap** — `snapshot_media_player()` and
  `snapshot_media_transport()` in `core/observations.py` now call
  `_ensure_device_exists(cur, mac)` before inserting into media tables,
  preventing `IntegrityError` when a device row does not yet exist.
* **P0-1 CLI MAC normalization** — extended the CLI `main()` MAC
  normalization loop to cover `pair`, `trust`, `untrust`, `remove_bond`,
  `source`, and `sink` argument names, ensuring all MAC-bearing arguments
  are uppercased consistently.

### Added

* **M8 — User Profile Control**:
  - `cprofiles` debug command — lists all `Device1.UUIDs` with resolved
    names via `get_name_from_uuid()`.
  - `cprofile connect|disconnect <UUID>` debug command — calls
    `ConnectProfile()` / `DisconnectProfile()` on the connected Classic
    device.
  - `cspp register --auth|--no-auth` — `require_auth` flag now
    propagated through `spp.py register()` to `SppManager`.
  - `bleep connect-profile <MAC> <UUID> [--disconnect]` CLI subcommand.
* **M9 — Custom Callback Functions**:
  - `bleep/callbacks/base.py` — `BleepCallback` abstract base class with
    `name`, `trigger`, `execute(context)`, and lifecycle hooks.
  - `bleep/callbacks/__init__.py` — auto-loader scanning
    `~/.config/bleep/callbacks/*.py` for `BleepCallback` subclasses;
    registers them via existing `signals.router.register_callback()`.
  - `SignalType` enum extended with `DEVICE_CONNECT`,
    `DEVICE_DISCONNECT`, `PAIR_START`, `PAIR_COMPLETE`.
  - Example callbacks: `log_all_notifications.py`, `pair_event_logger.py`.
* **M10 — HID Identification**:
  - `classify_hid()` and `HIDInfo` dataclass in
    `analysis/device_type_classifier.py` — combines appearance (960+),
    CoD peripheral major class (0x05), `Input1.ReconnectMode`, HID
    service UUID (0x1124) to produce typed HID classification.
  - `format_device_info_block()` in `ble_ops/common/conversion.py` now
    shows full HID classification block when device is identified as HID.
  - `chid` debug command in new `modes/debug_hid.py`.
  - `bleep hid-info <MAC>` CLI subcommand.
* **Bonus — Audio Capture & Transcription**:
  - `bleep/ble_ops/audio/audio_transcribe.py` — 7-step audio intercept
    pipeline: validate prerequisites, derive PCM, capture via `arecord`,
    analyse via `sox`, transcribe via `whisper` CLI or `vosk` Python API.
  - `AudioInterceptResult` dataclass for structured pipeline output.
  - `bleep audio-intercept <MAC> [--duration N] [--no-transcribe]
    [--engine whisper|vosk]` CLI subcommand.

### Changed

* `bleep/modes/debug_classic_profiles.py` — now hosts `cmd_cprofiles`
  and `cmd_cprofile` in addition to existing `cmd_cpan` and `cmd_cspp`.
* `bleep/modes/debug.py` — dispatch table and help text updated for
  `cprofiles`, `cprofile`, `chid` commands.
* `bleep/ble_ops/classic/spp.py` — `register()` accepts `require_auth`
  kwarg (default `True`), forwarded to `SppManager`.
* `bleep/signals/capture_config.py` — `SignalType` enum extended with
  4 new connection/pairing event types.
* `bleep/analysis/device_type_classifier.py` — `EvidenceType` enum
  extended with `HID_CLASSIFICATION`.
* `bleep/cli.py` — new subparsers and handlers for `connect-profile`,
  `hid-info`, and `audio-intercept` CLI subcommands; `cspp register`
  `--auth`/`--no-auth` flags; `_subparser_map` updated.

---

## v2.8.0-m1 – M1 Full Automatic Deployment of Amusica (2026-03-27)

### Added

* **Five-stage autonomous audio pipeline** — new file
  `bleep/ble_ops/audio/amusica_orchestrator.py` with `run_amusica_full_auto()`.
  Stages: (1) Scan & classify via `scan_audio_targets()`, (2) Connection
  test & triage (JustWorks / auth-required / profile-unavailable),
  (3) Optional PIN brute-force via `PinBruteForcer` with `COMMON_PINS`,
  (4) Audio recon + record/playback per accessible target, (5) Post-test
  analysis via `analyze_recordings()` using `sox`/`soxi`.
* **`bleep amusica auto` CLI subcommand** — runs the full pipeline with
  flags: `--brute`, `--brute-depth N`, `--timeout T`, `--record-dir DIR`,
  `--duration D`, `--test-file FILE`, `--out JSON`.  Summary table printed
  at completion with per-target breakdown.
* **`analyze_recordings(paths)`** — `sox stat` analysis for audio presence
  detection, max amplitude, duration; returns `List[RecordingResult]`.
* **M1-aug-a**: `attempt_justworks_connect()` in `amusica.py` now detects
  `"profile unavailable"` errors as a distinct `"profile_unavailable"`
  outcome (previously fell through to generic error).
* **M1-aug-b**: `run_audio_recon()` in `audio_recon.py` now distinguishes
  `"no_matching_device"` (MAC filter found nothing) from
  `"device_not_available"` (no BT audio devices at all).

### Changed

* `bleep/ble_ops/audio/amusica.py` — `attempt_justworks_connect()` error
  handler extended with `"profileunavailable"` string match.
* `bleep/ble_ops/audio/audio_recon.py` — empty-result error classification
  now MAC-filter-aware.

---

## v2.8.0-m7 – M7 Augment File Sharing (2026-03-27)

### Added

* **D1 — NearbySharing Detection (Phase A)**: Microsoft Nearby Sharing UUID
  (`a82efa21-ae5c-3dde-9bbc-f16da7b16c5a`) added to `bt_ref/constants.py`
  `UUID_NAMES` dict for automatic resolution by `get_name_from_uuid()`.
  `_native_scan` and `_base_enum` in `ble_ops/le/scan.py` now pass
  `service_data`, `advertising_data`, `manufacturer_data` to the
  `DeviceTypeClassifier` context.  `le_service_data` collector added to
  `passive` scan-mode allowlist in `device_type_classifier.py`.
* **D2 — Two-Stage OBEX File Save Directory**: `OBEX_STAGING_DIR`
  (`~/.cache/obexd/`, AppArmor-safe for obexd writes) and `OBEX_RECEIVE_DIR`
  (`/tmp/bleep_received/` default, override via `BLEEP_RECEIVE_DIR` env var)
  added to `core/config.py`.  All OBEX receive operations (OPP pull/exchange,
  MAP get, FTP get, BIP get/thumb, Sync get) updated in both
  `modes/debug_classic_obex.py` and `cli.py` to use two-stage approach
  (obexd → staging → final).  New `--save-dir` CLI flag added to
  `classic-opp`, `classic-map`, `classic-ftp`, `classic-bip`, `classic-sync`
  subparsers.  AppArmor constraint documented in `bl_classic_mode.md`
  troubleshooting table.
* **D3 — Persistent RFCOMM Channel Binding**: `bind_rfcomm_channel()`,
  `release_rfcomm_channel()`, `list_rfcomm_bindings()` added to
  `ble_ops/classic/rfcomm.py` using `rfcomm` userspace utility via
  `shutil.which` + `subprocess.run`.  `rfcomm_bindings` field added to
  `DebugState` in `modes/debug_state.py`.  New `cbind` debug command
  (bind/release/list) in `modes/debug_classic_rfcomm.py`, registered in
  `modes/debug.py` with automatic cleanup on shell exit.  CLI `--bind`
  and `--device-id` flags added to `classic-rfcomm` subparser.

### Changed

* `modes/debug_classic_obex.py` — `_default_pull_dest()` now returns
  `(staging_path, final_path)` tuple; new `_obex_staging_path()` and
  `_stage_and_move()` helpers encapsulate the two-stage download logic.
* `analysis/device_type_classifier.py` — passive mode now includes
  `le_service_data` collector for beacon/CDP/NearbySharing detection.

---

## v2.8.0-m6 – M3 PIN/Passkey Corrections (2026-03-27)

Post-implementation review of M3 against BlueZ documentation (`org.bluez.Agent.rst`,
`mgmt.rst`, `bluez/src/agent.c`, `bluez/emulator/smp.c`) identified 7 issues in
PIN/Passkey/Agent handling.  All corrected with minimal, targeted edits.

### Fixed

* **`bleep/bt_ref/constants.py`** — `COMMON_PINS`: removed empty string `""`
  (BlueZ rejects PIN length < 1, per `bluez/src/agent.c` line 493).  Added
  alphanumeric PINs (`"BlueZ"`, `"BRCM"`, `"default"`) since PINs are explicitly
  alphanumeric per `org.bluez.Agent.rst` line 39.  Structured by length
  (`COMMON_PINS_4`, `COMMON_PINS_6`, `COMMON_PINS_ALPHA`) for efficient iteration.
* **`bleep/bt_ref/constants.py`** — `COMMON_PASSKEYS`: trimmed to 5 entries;
  documented that SSP generates random passkeys per attempt (brute-force
  infeasible at 1-in-1,000,000) — list only useful for rare fixed-passkey devices.
* **`bleep/bt_ref/constants.py`** — `AGENT_CAPABILITIES`: reordered to place
  `DisplayYesNo` before `KeyboardOnly`.  For BR/EDR, kernel converts
  `KeyboardDisplay` (0x04) → `DisplayYesNo` (0x01) per `mgmt.rst` lines 1058–1060.
* **`bleep/dbuslayer/agent.py`** — `DisplayPinCode`: now sets
  `self.last_auth_method = "DisplayPinCode"` (was untracked).
* **`bleep/dbuslayer/agent.py`** — `RequestAuthorization`: now sets
  `self.last_auth_method = "RequestAuthorization"` (was untracked; used for
  Just Works pairing per `org.bluez.Agent.rst` lines 118–124).
* **`bleep/dbuslayer/agent.py`** — `attempt_downgrade_pair()`: replaced hardcoded
  capability list with reference to `AGENT_CAPABILITIES` constant (single source
  of truth).

### Changed

* **`bleep/dbuslayer/pin_brute.py`** — `run_passkey_brute()` docstring: now
  accurately describes SSP passkey limitations and the narrow use case
  (fixed-passkey devices only).

---

## v2.8.0-m5 – M2 + M3 + M5 + M6 (2026-03-25)

Milestones M2, M3, M5, and M6 of the v2.8.0 augmentation plan.

### Added

* **M2 — RFCOMM Channel Probing** (`bleep/ble_ops/classic/rfcomm.py`): New
  `ProbeResult` dataclass, `probe_rfcomm_channel()` and `probe_all_channels()`.
  Sends `\r\n`, VT100 DA1, passive SSH banner read. Classifies: terminal / ssh /
  serial / data / closed / silent.
* **M2 — CLI `classic-rfcomm`**: SDP discovery → RFCOMM table + optional
  `--probe` per channel.
* **M2 — Debug `crfcomm`**: RFCOMM listing + optional `--probe` from
  `state.current_mapping`.
* **M3 — Common PIN/PassKey constants** (`bleep/bt_ref/constants.py`):
  `COMMON_PINS` (14), `COMMON_PASSKEYS` (5), `AGENT_CAPABILITIES` (5). Wired
  as default iterators in `PinBruteForcer`.
* **M3 — Capability downgrade cycling** (`bleep/dbuslayer/agent.py`):
  `attempt_downgrade_pair()` cycles through all agent capabilities.
* **M3 — Auth type reporting**: `last_auth_method` on `BlueZAgent` base class,
  set in all 7 agent methods (`RequestPinCode`, `DisplayPinCode`,
  `RequestPasskey`, `DisplayPasskey`, `RequestConfirmation`,
  `RequestAuthorization`, `AuthorizeService`). Exposed via
  `get_last_auth_type()`.
* **M3 — Debug `pair --probe`**: Invokes `attempt_downgrade_pair()`, prints
  result table, cancels pairing.
* **M5 — Manufacturer ID → Company Name**: `_resolve_company_name()` in
  `common/conversion.py` resolves ManufacturerData keys via SIG table.
* **M5 — AD Type name resolution**: `_resolve_ad_type_name()` resolves
  AdvertisingData type codes.
* **M5 — Appearance consolidation**: `_resolve_appearance_sig()` falls back
  through SIG category/subcategory hierarchy.
* **M5 — Classifier enrichment**: `_determine_device_type()` now passes
  `service_data`, `advertising_data`, `manufacturer_data`, `appearance` context.
* **M5 — Beacon / CDP detection**: `LEServiceDataCollector` with 5 known beacon
  UUIDs (Find My, EN v1/v2, Microsoft CDP, NearbySharing).
* **M5 — Vendor UART heuristics**: 5 common UART UUIDs as WEAK evidence.
* **M5 — Evidence source labeling**: `evidence_source` field on
  `ClassificationResult` (`heuristic` / `measured_sdp` / `measured_gatt` /
  `cached`).
* **M6 — ALSA config management** (`bleep/ble_ops/audio/alsa_config.py`):
  `read_asound_conf()`, `configure_bluealsa_device()`, `remove_bluealsa_device()`,
  `create_audio_tunnel()`, `backup_and_restore()`.
* **M6 — CLI `audio-config`**: Subcommands `show|add|remove|tunnel|backup|restore`.

### Changed

* **M5 — `modalias.py`**: Import fixed from stale `bluetooth_uuids` to `uuids`.
* **M5 — `bluetooth_uuids.py`**: Marked deprecated with `DeprecationWarning`.
* **M3 — `PinBruteForcer`**: `pin_iterator` and `passkey_iterator` now optional
  (`None` defaults to `COMMON_PINS` / `COMMON_PASSKEYS`).

---

## v2.8.0-m4 – Improved Preliminary Check of Connectivity (2026-03-27)

Milestone M4 of the v2.8.0 augmentation plan. Comprehensive BlueZ error
mapping, connection-state awareness, adapter enumeration, and CLI ergonomics.

### Added

* **Comprehensive BlueZ error mapping** (`bleep/bt_ref/constants.py`,
  `bleep/core/error_handling.py`, `bleep/core/errors.py`) — 13 new
  `RESULT_ERR_*` constants (28–40), 8 new exception classes
  (`ProfileUnavailableError`, `AlreadyConnectedError`, `PageTimeoutError`,
  `ConnectionRefusedError`, `ConnectionLimitError`,
  `AuthenticationCanceledError`, `AuthenticationRejectedError`,
  `AuthenticationTimeoutError`), 7 new `_DBUS_ERROR_NAME_MAP` entries, 26 new
  `_DBUS_MESSAGE_MAP` entries covering all 34 BlueZ BR/EDR and LE connection
  error strings from `errors.txt` and `org.bluez.Device.rst`.  Human-readable
  descriptions added to `error_mapping` dict.
* **`DISCONNECT_REASON_MAP`** (`bleep/core/error_handling.py`) — maps 6
  `org.bluez.Reason.*` strings from the BlueZ `Disconnected` signal.
* **`DeviceState` dataclass and `check_device_state()`**
  (`bleep/core/preflight.py`) — queries LE/Classic `get_device_info()` and
  extracts `connected`/`paired`/`trusted` into a typed container with a
  `fully_bonded` convenience property.
* **`list_adapters()`** (`bleep/dbuslayer/adapter.py`) — static method walks
  `Adapter1` objects from `GetManagedObjects()`.
* **`get_connected_devices()`** (`bleep/dbuslayer/adapter.py`) — returns MACs
  of devices currently connected to the adapter.
* **`skip_pair_fallback` parameter** on
  `connect_and_enumerate__bluetooth__low_energy()` in
  `bleep/ble_ops/le/connect.py` — when `True`, auth exceptions re-raise
  instead of auto-pairing, allowing callers to handle auth requirements
  explicitly.
* **`--adapter` CLI flag** on `scan`, `connect`, `gatt-enum`, `enum-scan`,
  `classic-scan`, `classic-enum`, `classic-ping`, `explore`, `signal`, and
  `agent` subcommands.

### Changed

* **`device_classic.py` `connect()`** — removed the unconditional
  `Disconnect()` call in the retry loop.  Added `force_disconnect: bool`
  parameter (default `False`); only disconnects when explicitly requested.
* **`map_dbus_error()`** — expanded with ~10 new branches for named D-Bus
  errors and message-string discrimination within `org.bluez.Error.Failed`.
* **`_DBUS_ERROR_NAME_MAP`** — `org.bluez.Error.AlreadyConnected` now maps to
  `RESULT_ERR_ALREADY_CONNECTED` (was `RESULT_ERR_WRONG_STATE`).

---

## v2.7.40 – v2.8.0 Pre-Work: Cleanup, Reorganisation, and Hardening (2026-03-26)

Pre-work for the v2.8.0 augmentation plan (`workDir/BigMoves/README.v2.8.0`).
Nine P0 tasks address code quality, structural organisation, and
operational reliability before the main feature work begins.

### Fixed

* **`bleep/core/observations.py`** — Schema version persistence bug:
  the v8→v9 and v9→v10 migration messages printed on every launch
  because the version `UPDATE` compared the locally-mutated
  `current_version` (already bumped to 10) against `_SCHEMA_VERSION`
  (also 10), so the `UPDATE` was skipped and the DB stayed at 8.  Fixed
  by tracking the original DB value as `stored_version` for the
  comparison.

* **`bleep/core/observations.py`** — Added `descriptors` to the table
  list in `maintain_database()` so it is included in row-count reports.

* **`bleep/cli.py`** — `classic-scan` debug branch referenced
  `d["class"]` but `get_discovered_devices()` returns `"device_class"`;
  corrected to use the actual key.

* **`bleep/modes/scratch.py`** — Passed `timeout=` kwarg to
  `connect_and_enumerate__bluetooth__low_energy` which expects
  `timeout_connect=`; corrected the keyword.

* **`bleep/ble_ops/classic/connect.py`** — `cconnect` auto-pair now
  uses the same GLib MainLoop stop/restart pattern as
  `pair --interactive`: stops the background loop before agent dispatch,
  runs `PairingAgent.pair_device()` on the main thread, then restarts.
  Conditional — only applied when pairing is actually needed.

* **`bleep/ble_ops/classic/pbap.py`** — Added specific detection of
  `"Transport got disconnected"` errors with actionable user guidance
  (enable Contact Sharing on the target device).

* **`bleep/dbuslayer/network.py`** — `NetworkClient.status()` now uses
  a single `GetAll("org.bluez.Network1")` D-Bus call for atomic
  property reads, with fallback to individual reads if `GetAll` fails.

### Added

* **`bleep/core/preflight.py`** — `require_adapter()` function:
  centralised Bluetooth adapter readiness check with uniform
  `[!] Bluetooth adapter not found or not ready` error message.
  Applied at debug shell startup, `cmd_cconnect`, and all CLI
  Bluetooth subcommands.

* **`bleep/cli.py`** — Centralised MAC address normalisation to
  uppercase in `main()` after argument parsing, covering `address`,
  `target`, `device`, and `mac` arguments.

* **`bleep/cli.py`** — `--transport {auto,le,bredr}` flag on
  `bleep scan`, defaulting to `auto`.

* **`bleep/modes/debug_scan.py`** — `dscan` command for combined
  LE + BR/EDR discovery in a single session via `Transport: "auto"`.
  Distinct from `scanb` (sequential two-phase brute scan).

* **`bleep/modes/debug_gatt.py`** — `cmd_services` now reconnects and
  polls `ServicesResolved` if services are not yet resolved, caches the
  result in `state.current_mapping`, and supports `--refresh` to force
  re-enumeration.

* **`bleep/ble_ops/le/scan.py`** — `_native_scan` now explicitly sets
  `{"Transport": "auto"}` in the discovery filter for `transport="auto"`
  to avoid inheriting stale filter state.

### Changed

* **`bleep/ble_ops/` restructure** — All 32 modules reorganised into
  four subpackages:
  * `le/` — scan, connect, reconnect, brute, enum, CTF (9 modules)
  * `classic/` — connect, sdp, pbap, opp, ftp, map, pan, spp, ping,
    version, bip, sync (12 modules)
  * `common/` — conversion, uuid_utils, modalias, structural (4 modules)
  * `audio/` — amusica, audio_tools, audio_codec, audio_recon,
    audio_system, audio_profile_correlator (6 modules)

  All ~181 import statements across 62 files updated to canonical
  subpackage paths.  31 backward-compat stub files removed.
  `bleep/ble_ops/__init__.py` re-exports core public symbols for
  package-level convenience imports.

* **`bleep/ble_ops/audio/audio_tools.py`** and
  **`bleep/core/preflight.py`** — BlueALSA binary resolution now tries
  `bluealsactl` first (>= 4.0) with fallback to `bluealsa-cli`.

---

## v2.7.39 – Schema v10 Full Utilisation (2026-03-25)

Follow-up audit ensuring every v10 column is actively written by all
CLI code paths, fixing broken persistence logic, and adding descriptor
persistence everywhere.

### Fixed

* **`bleep/core/observations.py`** — `upsert_services()` now writes
  `is_primary` (bool→int) and `includes` (list→JSON) in both INSERT and
  ON CONFLICT COALESCE branches.  Previously these v10 columns were
  defined in the schema but never populated.

* **`bleep/core/observations.py`** — `upsert_characteristics()` now
  writes the `mtu` column in both INSERT and ON CONFLICT COALESCE.

* **`bleep/cli.py`** (`gatt-enum`) — Replaced inline DB persistence
  code (which only handled the shallow `"chars"` key) with a single
  delegation to `_persist_mapping()`.  Deep mode (`--deep`) was silently
  losing all characteristics because it uses the `"Characteristics"`
  key.  Added `upsert_device()` call with full v10 metadata.

* **`bleep/cli.py`** (`media-enum`) — Added `upsert_device()` with v10
  metadata.  Previously media-enum wrote nothing to the database.

* **`bleep/analysis/aoi_analyser.py`** — Fixed broken
  `services_mapping` iteration in `save_device_data()` that treated
  service data dicts as `(uuid, handle)` pairs.  Now correctly walks
  the GATT mapping hierarchy (`svc → chars → char_info`) and persists
  characteristics and descriptors.  The same fix applied to the analysis
  path that extracts characteristics for security/unusual reporting.

* **`bleep/dbuslayer/device_le.py`** — Shallow-mode
  `services_resolved()` now includes `Primary` and `Includes` keys in
  the svc_entry dict for parity with deep mode, ensuring
  `_persist_mapping → upsert_services` can write them.

### Added

* **`bleep/ble_ops/scan.py`** — `_enrich_device_info_from_props()`:
  shared helper that merges v10 device columns from a D-Bus Device1
  property dict (CamelCase keys) into an `upsert_device` kwargs dict.
  Used by `_base_enum`, `cli.py connect`, `cli.py gatt-enum`,
  `cli.py classic-enum`, `cli.py media-enum`, and `exploration.py`.

* **`bleep/ble_ops/scan.py`** — `_persist_mapping()` now persists
  descriptors for each characteristic, threads `is_primary`/`includes`
  from service data, and threads `mtu` from characteristic data.

* **`bleep/core/observations.py`** — `get_device_detail()` return dict
  now includes a `"descriptors"` key with all descriptor rows for the
  device.  `export_device_data()` inherits this automatically.

### Changed

* **`bleep/ble_ops/scan.py`** (`_native_scan`) — `upsert_device` calls
  now include `tx_power`, `appearance`, `modalias`, `icon`,
  `manufacturer_data`, `service_data`, `advertising_data` when available
  in the adapter discovery data.

* **`bleep/ble_ops/classic_connect.py`** — `upsert_device` now includes
  `tx_power` when available in the device info dict.

* **`bleep/cli.py`** (`classic-scan`) — `upsert_device` calls now
  include `tx_power`, `appearance`, `modalias`, `icon` where available.

* **`bleep/cli.py`** (`connect`, `classic-enum`) — Replaced manual
  property extraction with calls to `_enrich_device_info_from_props()`.

* **`bleep/modes/exploration.py`** — Replaced manual v10 enrichment
  with call to `_enrich_device_info_from_props()`.

### Documentation

* `observation_db.md` — Updated schema version table with v10 entry and
  changed "currently at version 9" to "currently at version 10".
* `observation_db_schema.md` — Added v10 API reference table.
* `device_type_classification.md` — Replaced stale per-version migration
  notes with a single "current schema: v10" reference.

---

## v2.7.38 – Data Fidelity Remediation & Schema v10 (2026-03-25)

Systematic audit of all BLEEP CLI commands against BlueZ D-Bus API
documentation identified 11 data fidelity gaps where device, service,
characteristic, or descriptor information was either lost, incomplete,
or never persisted to the observation database.  All gaps have been
addressed with minimal, targeted changes to four files.

### Fixed

* **`bleep/modes/exploration.py`** — `print_service_info` now reads
  **all** readable characteristic values and collects **all** descriptor
  data unconditionally, regardless of the `--verbose` flag or the
  20-characteristic display threshold.  Previously, characteristics
  beyond position 20 in non-verbose mode were silently skipped for both
  display *and* data collection, causing permanent data loss in the DB.

* **`bleep/modes/exploration.py`** — `save_to_database` now accepts
  `mapping` and `device_props` parameters.  Full device metadata (RSSI,
  address type, device class, appearance, manufacturer data) is
  persisted via `upsert_device`.  Service handle ranges from the GATT
  mapping are included.  Permission maps are stored per-characteristic.
  Readable values are also recorded in `char_history` with
  `source="explore"` for audit trail.  Device type is determined by
  `DeviceTypeClassifier` instead of being hardcoded to `"le"`.

* **`bleep/cli.py`** (`connect`) — The `connect` command now persists
  device metadata and GATT enumeration data to the observation DB after
  successful connection, using `_collect_device_props` and
  `_persist_mapping`.  Previously, `connect` returned success but wrote
  nothing to the database.

* **`bleep/cli.py`** (`classic-scan`) — Discovered Classic BR/EDR
  devices are now persisted to the DB via `upsert_device` with name,
  RSSI, device class, address type, and `device_type="classic"`.

* **`bleep/cli.py`** (`classic-enum`) — Now fetches full
  `org.bluez.Device1` D-Bus properties (plus `Battery1`/`Input1`
  auxiliaries) and prints a Device Information block identical to what
  BLE enumeration commands display (`format_device_info_block`).  Full
  device metadata is persisted to the observation DB.

* **`bleep/ble_ops/classic_connect.py`** —
  `connect_and_enumerate__bluetooth__classic` now calls `upsert_device`
  with full device info (`name`, `rssi`, `device_class`, `device_type`)
  before persisting classic services.  Previously only
  `upsert_classic_services` was called.

* **`bleep/core/observations.py`** — `upsert_services` ON CONFLICT
  clause now updates `handle_start`, `handle_end`, and `name` via
  `COALESCE(excluded.X, services.X)` so subsequent scans can fill in
  previously-NULL values rather than only updating `last_seen`.

### Added

* **`bleep/core/observations.py`** — Schema v10 migration:
  * `devices` table: `tx_power`, `modalias`, `icon`, `service_data`,
    `advertising_data` columns
  * `services` table: `is_primary`, `includes` columns
  * `characteristics` table: `mtu` column
  * New `descriptors` table with `UNIQUE(characteristic_id, uuid)`
    constraint and covering index
  * New public APIs: `get_characteristic_id()` and
    `upsert_descriptors()`
  * `_DEVICE_COLS` frozenset updated with all new column names
  * Idempotent migration via per-column `ALTER TABLE ADD COLUMN` with
    safe `try/except` for existing databases

---

## v2.7.37 – System-Tool Audio Playback & Recording (2026-03-21)

Added `--system` flag to `audio-play` and `audio-record` that delegates
to host audio tools (`paplay`/`parecord`/`pw-play`/`pw-record`/`aplay`/
`arecord`) through the running audio daemon.  Works **with**
PulseAudio/PipeWire/BlueALSA rather than competing for D-Bus transport
ownership — mirrors how `audio-recon` already operates.

### Added

* **`bleep/ble_ops/audio_system.py`** — New module with `system_play()`
  and `system_record()` functions.  Resolves a device MAC to a sink or
  source identifier using the same backend-specific enumeration that
  `audio-recon` uses:
  * PulseAudio / PipeWire-PA-compat: card-centric enumeration via
    `get_bluez_cards()` → `get_sources_and_sinks_for_card_profile()`
  * PipeWire native: `_get_pipewire_sources_and_sinks()` → node ID
  * BlueALSA: `list_bluealsa_pcms()` → ALSA device string
  Then delegates to `AudioToolsHelper.play_to_sink()` /
  `record_from_source()` / `play_to_bluealsa_pcm()` /
  `record_from_bluealsa_pcm()`.

* **`bleep/cli.py`** — `--system` flag on `audio-play` and
  `audio-record`.  When set, bypasses `MediaStreamManager` entirely and
  calls `system_play()` / `system_record()` directly.

---

## v2.7.36 – Fix Endpoint-Based Transport Acquisition (2026-03-21)

Fixed the endpoint-based transport acquisition path introduced in v2.7.35.
`RegisterEndpoint()` only creates a local SEP — BlueZ selects endpoints
exclusively during A2DP profile connection (`ConnectProfile`), which is a
no-op if the profile is already connected.  The previous implementation
registered the endpoint but never triggered negotiation, causing
`SetConfiguration` to never be called.

### Fixed

* **`bleep/dbuslayer/media.py`** — `BleepMediaEndpoint` now uses a
  **private** D-Bus system bus with explicit `DBusGMainLoop` integration
  so callbacks dispatch correctly regardless of the shared bus singleton.
  GLib `MainLoop` lifecycle is encapsulated within the class (`register()`
  starts it, `unregister()` stops it).  Fixed `SetConfiguration` D-Bus
  signature from `oay` to `oa{sv}` (properties dict, not byte array).

* **`bleep/dbuslayer/media_stream.py`** — `_acquire_via_endpoint()` now
  performs a full device disconnect/reconnect (`Device1.Disconnect()` →
  poll `Connected` → `Device1.Connect()`) instead of profile-level
  cycling.  `DisconnectProfile` + `ConnectProfile` was insufficient
  because the AVDTP session (`source->session`) persists across the
  cycle, causing `source_connect()` to return `-EALREADY` without
  re-running `a2dp_discover`.  A full device disconnect tears down the
  ACL link, destroying all AVDTP sessions.  On reconnect, BlueZ performs
  fresh AVDTP discovery including the BLEEP endpoint.  Removed unused
  `threading` and `GLib` imports; mainloop management is now internal to
  `BleepMediaEndpoint`.

### Added

* **`bleep/docs/todo_tracker.md`** — Future work note for a system-tool
  operation mode (`--system` flag) for `audio-play` / `audio-record`
  that leverages `paplay`/`parecord`/`aplay` (like `audio-recon`) to
  sidestep D-Bus transport ownership entirely.

---

## v2.7.35 – BLEEP-Owned MediaEndpoint Registration & Dual Acquisition Modes (2026-03-20)

Introduced BLEEP-owned MediaEndpoint registration so `audio-play` and
`audio-record` can acquire transports even when PulseAudio/PipeWire is
running.  Previously, the audio daemon would automatically acquire all
A2DP transports, causing `Acquire()` to fail with `NotAuthorized`.

### Added

* **`bleep/dbuslayer/media.py`** — New `BleepMediaEndpoint` class: a
  D-Bus service implementing `org.bluez.MediaEndpoint1` (server role).
  When registered with BlueZ via `Media1.RegisterEndpoint()`, BlueZ
  pairs it with an unused remote SEP and creates a transport that BLEEP
  owns exclusively.  Implements `SetConfiguration`,
  `SelectConfiguration`, `ClearConfiguration`, and `Release` callbacks.
  Runs a GLib main loop on a daemon thread for async D-Bus handling.

* **`bleep/bt_ref/constants.py`** — Added `SBC_CAPABILITIES` and
  `SBC_DEFAULT_CONFIGURATION` byte constants for A2DP endpoint
  registration (values from A2DP spec section 4.3.2 and BlueZ
  `simple-endpoint`).

* **`bleep/cli.py`** — Added `--direct` flag to `audio-play` and
  `audio-record` commands.  Without the flag (default), BLEEP registers
  its own endpoint to get an uncontested transport.  With `--direct`,
  the legacy behaviour is used (acquire an existing transport directly —
  requires the audio daemon to be stopped).

### Changed

* **`bleep/dbuslayer/media_stream.py`** — `MediaStreamManager` now
  supports two acquisition modes:
  * **Default**: `_acquire_via_endpoint()` — registers a
    `BleepMediaEndpoint`, waits for BlueZ's `SetConfiguration`
    callback, then `Acquire()`s the BLEEP-owned transport.
  * **Direct** (`direct=True`): `_acquire_direct()` — finds an
    existing transport on D-Bus and attempts `Acquire()` directly
    (legacy/constrained mode).
  * `release_transport()` now also unregisters the BLEEP endpoint and
    stops the GLib main loop thread.

* **`bleep/dbuslayer/media_stream.py`** — When `Acquire()` returns
  `NotAuthorized`, the error handler now detects the transport state
  and prints actionable guidance (which daemon to stop, which flags
  to use).

### Reference

* BlueZ `profiles/audio/transport.c` `acquire()` (line 790–828) — two
  conditions produce `NotAuthorized`: `transport->owner != NULL` or
  `transport->state >= TRANSPORT_STATE_REQUESTING`.
* BlueZ `profiles/audio/media.c` `set_configuration()` (line 533–555) —
  `find_device_transport()` enforces one transport per
  (endpoint, device) pair; `media_transport_create()` is called when no
  existing transport is found.
* BlueZ `test/simple-endpoint` — reference implementation for
  `RegisterEndpoint` / `SelectConfiguration` / `SetConfiguration` flow.

## v2.7.34 – Fix Silent Exception Swallowing in Transport Discovery (2026-03-20)

Fixed the persisting *"MediaTransport not found"* error from v2.7.33.
The three-phase discovery strategy was correct in design, but Phase 1
silently swallowed D-Bus exceptions via `except Exception: continue`
when constructing `MediaEndpoint` proxy objects just to read their UUID.
This caused Phase 1 to fail silently and fall through to Phase 3.

### Fixed

* **`bleep/dbuslayer/media_stream.py`** — Replaced D-Bus proxy-based
  UUID extraction with direct property reads from `GetManagedObjects()`
  data.  New `_collect_media_objects()` method scans the managed objects
  dict and extracts `(path, uuid)` tuples for endpoints and transports
  in a single pass — no D-Bus proxy construction needed for Phase 1 or
  Phase 2 UUID matching.  Proxy construction is now deferred to the
  final step when the correct transport path has been identified.

* **`bleep/dbuslayer/media_stream.py`** — All exception handlers in
  Phase 1/2 now log errors at `LOG__USER` level (previously
  `LOG__DEBUG`), making transport proxy failures visible to the user.

* **`bleep/dbuslayer/media_stream.py`** — Improved `acquire_transport()`
  error message: now includes the searched endpoint UUID, its profile
  name, and the expected transport role, plus a hint to run `media-enum`.

* **`bleep/dbuslayer/media_stream.py`** — Discovery summary messages
  (device not found, no transports) elevated from `LOG__DEBUG` to
  `LOG__USER` so failures are always visible.

### Changed

* **`bleep/dbuslayer/media_stream.py`** — Replaced import of
  `find_media_devices` and `MediaEndpoint` with `get_managed_objects`
  (already defined in `media.py`).  `MediaEndpoint` is no longer needed
  in this module.

* **`bleep/dbuslayer/media.py`** — Added `get_managed_objects` to
  `__all__` exports.

## v2.7.33 – Fix MediaTransport Discovery & Enrich media-enum Output (2026-03-20)

Fixed critical transport discovery bug that caused `audio-play` and
`audio-record` to fail with *"MediaTransport not found"* even when a
valid transport existed.  Root cause: `_get_transport()` compared the
transport UUID directly against the remote endpoint UUID, but BlueZ
assigns the **local** host's complementary role UUID to the transport
(per AVDTP specification).  Also enriched `media-enum` output to expose
the endpoint ↔ transport relationship to the user.

### Fixed

* **`bleep/dbuslayer/media_stream.py`** — `_get_transport()` used
  `transport.get_uuid() == self.profile_uuid` to locate the transport,
  comparing the transport's local-role UUID against the remote endpoint
  UUID.  These are always complementary (e.g. remote A2DP Sink
  `0x110b` → local A2DP Source transport `0x110a`), so the match always
  failed.  Replaced with a three-phase discovery strategy:
  1. **Path-based association** — find the MediaEndpoint matching the
     target profile UUID, then locate the MediaTransport whose D-Bus
     path is a child of that endpoint (following BlueZ's own object
     hierarchy).  Accepts the transport regardless of its UUID.
  2. **Complement UUID fallback** — if path association fails, search
     for a transport with the expected complement UUID from the new
     `PROFILE_UUID_COMPLEMENTS` mapping.
  3. **Diagnostic dump** — log all available transport paths/UUIDs so
     the user can diagnose mismatches.

### Added

* **`bleep/bt_ref/constants.py`** — Added `PROFILE_UUID_COMPLEMENTS`
  mapping that documents the expected relationship between remote
  endpoint UUIDs and local transport UUIDs for all audio profiles
  (A2DP, HFP, HSP, AVRCP).  Advisory only — BLEEP does not reject
  transports with unexpected UUIDs.

### Changed

* **`bleep/cli.py`** (`media-enum`) — Enriched default output for
  transports (added `uuid`, `uuid_name`, `codec`, `codec_name`,
  `configuration`, `parent_endpoint`, `role`) and endpoints (added
  `uuid_name`, `codec_name`, `capabilities`, `delay_reporting`,
  `expected_transport_uuid`, `expected_transport_role`, `role`).
  Resolves the TODO comments requesting expansion.

* **`bleep/dbuslayer/media_stream.py`** — Updated module and class
  docstrings to explain the MediaEndpoint ↔ MediaTransport UUID
  relationship: endpoint UUID = remote device role, transport UUID =
  local host complementary role.

* **`bleep/modes/audio.py`** — Updated `play_audio_file()` and
  `record_audio()` docstrings to clarify that `profile_uuid` refers
  to the remote endpoint role.

### Reference

* BlueZ `profiles/audio/transport.c` `get_uuid()` — transport UUID is
  always `media_endpoint_get_uuid(transport->endpoint)` (local endpoint).
* BlueZ `profiles/audio/avdtp.c` `avdtp_find_remote_sep()` — enforces
  complementary Source ↔ Sink pairing at the AVDTP protocol level.
* BlueZ `profiles/audio/a2dp.c` `a2dp_select_eps()` — remote SINK →
  local sources; remote SOURCE → local sinks.
* BlueZ `profiles/audio/bap.c` — BAP follows the same complementary
  model for LE Audio PAC endpoints.

---

## v2.7.32 – Audio Transport & GStreamer Import Fixes (2026-03-19)

Fixed critical bugs preventing `audio-play` and `audio-record` commands from
functioning.  The `audio-recon` command was unaffected because it uses a
completely different code path (subprocess calls to `paplay`/`parecord`/`aplay`
etc.) that never touches D-Bus transport acquisition.

### Fixed

* **`bleep/dbuslayer/media.py`** — `MediaTransport.acquire()` called `int(fd)`
  on the file descriptor returned by BlueZ `MediaTransport1.Acquire()`, but
  BlueZ returns a `dbus.UnixFd` wrapper which is not convertible via `int()`.
  This caused both `audio-play` and `audio-record` to fail with:
  `"Failed to acquire transport: int() argument must be a string, a bytes-like
  object or a real number, not 'dbus.UnixFd'"`.
  Now uses `fd.take()` (per the BlueZ reference script `simple-asha`) to
  extract the raw integer file descriptor and transfer ownership so the
  wrapper does not close it prematurely.

* **`bleep/bt_ref/utils.py`** — `dbus_to_python()` was missing conversions for
  `dbus.UInt64`, `dbus.UInt32`, and `dbus.types.UnixFd`.  Any code path
  passing these D-Bus types through the generic converter would return them
  unconverted.  Added `int()` branches for unsigned 64/32-bit integers and a
  `.take()` branch for `UnixFd`.

* **`bleep/ble_ops/audio_codec.py`** — Importing `Gst` from `gi.repository`
  without calling `gi.require_version("Gst", "1.0")` first produced a
  `PyGIWarning` on every invocation of `audio-play` or `audio-record`.
  Additionally, `GLib` was imported without a version pin inside two method
  bodies (`_encode_with_python_bindings`, `_decode_with_python_bindings`).
  Now follows the canonical BlueZ pattern from `workDir/BlueZScripts/simple-asha`:
  both `Gst` and `GLib` are version-pinned and imported together at module
  level.  The two redundant inner `from gi.repository import GLib` statements
  have been removed.

* **`bleep/core/preflight.py`** — `_check_audio_tools()` imported `Gst`
  without `gi.require_version()`, producing the same `PyGIWarning`.  Added
  the version pin before the import.

### Reference

All GStreamer/D-Bus changes were verified against the BlueZ reference material:

* `workDir/BlueZScripts/simple-asha` — canonical `gi.require_version` +
  `fd.take()` pattern (lines 12-16, 163)
* `workDir/BlueZDocs/org.bluez.MediaTransport.rst` — `Acquire()` returns
  `fd, uint16, uint16`

---

## v2.7.31 – Documentation Audit & Corrections (2026-03-19)

Performed a comprehensive cross-reference audit of all `bleep/docs/` files
against the current codebase and fixed every discrepancy found.

### Fixed

* **`media_mode.md`** — CLI command reference was using the wrong subcommand
  structure (`media list`/`media control`/`media monitor`). Updated to reflect
  the actual top-level commands `media-enum` and `media-ctrl`.
* **`observation_db_usage_scenarios.md`** — Scenario 1 imported
  `passive_scan_and_connect` from the wrong module with incorrect parameters
  (`duration` instead of `timeout`) and wrong return type. Fixed to use the
  adapter discovery API.
* **`debug_mode.md`** — Documented a nonexistent `python -m bleep.cli debug`
  CLI access path. Debug mode is only accessible via
  `python -m bleep.modes.debug`; removed the invalid section.
* **`network_capability_plan.md`** and **`network_capability_summary.md`** —
  Referenced a `Network` class and `find_network_devices()` that do not exist.
  Updated to reflect the actual implementation: `NetworkClient` and
  `NetworkServer` classes in `bleep/dbuslayer/network.py`.
* **`ble_scan_modes.md`** — Had duplicate "Last updated" dates (2025-07-21
  and 2026-03-18). Consolidated to a single date.
* **`README.md`** — Was missing links to the majority of documentation files
  (Classic mode, audio recon, explore mode, analysis mode, signal capture,
  adapter config, BlueZ interface properties, D-Bus guides, etc.).
  Reorganised into categorised sections for discoverability.
* **`bleep/docs/__init__.py`** — `_DOCS` mapping only listed 7 of 40+ doc
  files, causing `pydoc bleep.docs.<name>` to fail for most guides. Expanded
  to cover all documentation files.

---

## v2.7.30 – Comprehensive BlueZ Property Coverage (2026-03-19)

Broadened D-Bus property capture and display across all BlueZ interfaces
to close coverage gaps identified during a full specification audit.

### Added

* **`bleep/dbuslayer/characteristic.py`** — `Characteristic` now captures
  `MTU` (negotiated ATT MTU, post-connection) and `Notifying` (active
  notification state) from `GattCharacteristic1` D-Bus properties.
* **`bleep/dbuslayer/service.py`** — `Service` now captures `Includes`
  (list of included/secondary service object paths) from `GattService1`.
* **`bleep/dbuslayer/device_le.py`** — Deep-mode GATT mapping now includes
  `Primary`, `Handle`, and `Includes` at the service level; `MTU` and
  `Notifying` at the characteristic level.
* **`bleep/ble_ops/scan.py`** — `_collect_device_props()` now also probes
  `org.bluez.Battery1` and `org.bluez.Input1` interfaces on the device
  path, merging results under reserved keys `_Battery1` and `_Input1`.
* **`bleep/ble_ops/conversion.py`** — `format_device_info_block()` now
  displays: `Bonded`, `WakeAllowed`, `Icon`, `AdvertisingFlags` (hex/ASCII),
  `AdvertisingData` (type-keyed hex/ASCII), Battery1 (`Percentage`, `Source`),
  and Input1 (`ReconnectMode` with human-readable policy explanation).
* **`bleep/ble_ops/conversion.py`** — `format_gatt_tree()` now displays:
  service `Handle`, `Primary`/`Secondary` label, and `Includes`; characteristic
  `MTU` and `Notifying`; descriptor `Handle` and `Flags`.
* **`bleep/dbuslayer/adapter.py`** — `get_discovered_devices()` now includes
  `bonded`, `wake_allowed`, `icon`, `advertising_flags`, and
  `advertising_data` in returned device dictionaries.
* **`bleep/modes/adapter_config.py`** — `adapter-config show` now displays
  `PowerState`, `Manufacturer`, `Version`, and `ExperimentalFeatures`.
  `adapter-config get` supports new property names: `power-state`,
  `manufacturer`, `version`, `experimental-features`.
* **`bleep/docs/bluez_interface_properties.md`** — New comprehensive reference
  documenting all captured BlueZ D-Bus interface properties with security
  and operational significance notes covering Device1, GattService1,
  GattCharacteristic1, GattDescriptor1, Battery1, Input1, and Adapter1.

### Changed

* **`bleep/docs/gatt_enumeration.md`** — Updated to reflect the enriched
  GATT tree output (service handles, MTU, notifying, descriptor flags).
* **`bleep/docs/adapter_config.md`** — Property table expanded with
  `PowerState`, `Manufacturer`, `Version`, and `ExperimentalFeatures`.

---

## v2.7.29 – Device Info in Enumeration Output (2026-03-19)

Added device-level D-Bus property display to CLI enumeration commands
(`gatt-enum`, `enum-scan`) and improved hex/ASCII value formatting across
the GATT tree output.

### Added

* **`bleep/ble_ops/conversion.py`** — `format_hex_ascii()` utility formats raw
  bytes as separate `Hex:` and `ASCII:` lines with U+FFFD for non-printable
  bytes (consistent with existing `convert__hex_to_ascii` behaviour).
* **`bleep/ble_ops/conversion.py`** — `format_device_info_block()` renders
  Device1 D-Bus properties (ManufacturerData, ServiceData, Class, RSSI,
  TxPower, Appearance, Modalias, UUIDs, etc.) as a formatted info block.
  ManufacturerData keys are shown as `0x{key:04x} ({decimal})`, values as
  Hex/ASCII lines.  ServiceData UUIDs are resolved to known names.
* **`bleep/ble_ops/conversion.py`** — `format_gatt_tree()` accepts optional
  `device_props` parameter; when provided, a `Device Information` section
  is prepended before the GATT tree.
* **`bleep/dbuslayer/adapter.py`** — `get_discovered_devices()` now includes
  `manufacturer_data`, `service_data`, `tx_power`, `appearance`, `modalias`,
  `paired`, `trusted`, and `blocked` in returned device dictionaries.
* **`bleep/ble_ops/scan.py`** — `_collect_device_props()` helper fetches all
  `org.bluez.Device1` properties from D-Bus for display formatting.
  `_base_enum()` now collects and returns device properties as a 5th element.
  All enum wrappers (`passive_enum`, `naggy_enum`, `pokey_enum`, `brute_enum`)
  propagate `device_props` in their returned dictionaries.

### Changed

* **`bleep/ble_ops/conversion.py`** — Characteristic and descriptor ASCII
  display in `format_gatt_tree()` now derives ASCII directly from raw bytes
  with U+FFFD for non-printable characters (0x00–0x1F, 0x7F+), replacing the
  previous behaviour where ASCII was only shown if a pre-decoded value existed.
  When raw bytes are available, both `Hex:` and `ASCII:` lines are always shown.
* **`bleep/cli.py`** — `gatt-enum` and `enum-scan` handlers now pass
  `device_props` to `format_gatt_tree()` for device-level info display.

## v2.7.28c – Documentation Reference Cleanup (2026-03-18)

Removed all dangling references to project-root files and non-existent
documentation from the internal `bleep/docs/` documentation.  All docs now
reference only files that exist within the `bleep/` codebase.

### Fixed

* **`bleep/docs/agent_documentation_index.md`** — Rewrote to remove references
  to 3 non-existent example files (`../examples/simple_pairing.py`,
  `custom_agent.py`, `secure_bonding.py`) and 3 non-existent docs
  (`bluez_integration.md`, `agent_security.md`, `pairing_workflows.md`).
  Replaced with table-formatted component references pointing to actual source
  files and existing docs.

* **`bleep/docs/dbus_documentation_index.md`** — Removed 5 dangling references
  to project-root markdown files (`../../RELIABILITY_VERIFICATION.md`,
  `DIAGNOSTIC_TOOL_FIXES.md`, `USING_DBUS_RELIABILITY.md`,
  `PHASE4_COMPLETED.md`, `DBUS_RELIABILITY_SUMMARY.md`).  Replaced with a
  self-contained verification/testing section referencing the diagnostic tool.

* **`bleep/docs/d-bus-reliability.md`** — Removed dangling reference to
  `../scripts/dbus_diagnostic.py` (relative link) and non-existent
  `../docs/api_reference.md`.  Replaced with inline module path and invocation
  command.

* **`bleep/docs/device_type_classification.md`** — Removed references to
  non-existent `DUAL_DEVICE_DETECTION_PLAN.md` and
  `TYPE_PROPERTY_FIX_PLAN.md`.  Retained valid references to
  `observation_db_schema.md` and `changelog.md`.

* **`bleep/docs/ble_ctf_mode.md`** — Replaced placeholder URL
  (`https://github.com/your-org/bleep`) with link to `cli_usage.md`.

* **`bleep/docs/todo_tracker.md`** — Updated historical reference to removed
  `DUAL_DEVICE_DETECTION_PLAN.md` to point to its successor
  `device_type_classification.md`.

---

## v2.7.28b – Documentation Audit: CLI, Database, and Debug Mode (2026-03-18)

Comprehensive documentation audit identifying and closing gaps across CLI
command coverage, database schema versioning, and debug mode command reference.

### Added

* **`bleep/docs/cli_usage.md`** — Expanded from 18 to 34 commands, organised
  into categorised tables (BLE, Classic, Media & Audio, Database, Agent &
  Configuration).  Previously missing commands: `user`, `uuid-translate`,
  `ctf`, `adapter-config`, `audio-profiles`, `audio-play`, `audio-record`,
  `audio-recon`, `amusica`, `classic-enum`, `classic-pbap`, `classic-opp`,
  `classic-map`, `classic-ftp`, `classic-pan`, `classic-spp`, `classic-sync`,
  `classic-bip`, `classic-ping`.

* **`bleep/docs/debug_mode.md`** — Expanded the debug shell command table from
  17 entries to a comprehensive categorised reference covering all submodules:
  connection/info, BLE scanning (4 variants), BLE enumeration (5 commands),
  GATT interaction (10 commands), Classic Bluetooth (14 commands), pairing (2),
  D-Bus navigation (10 commands), and database/AoI (3 commands).

### Improved

* **`bleep/docs/observation_db.md`** — Updated schema version table from v7 to
  v9 (v8: MAC uppercase normalisation, v9: UUID uppercase normalisation).
  Added "Data Integrity (FK Defense Chain)" section documenting
  `_ensure_device_exists`, `_ensure_service_exists`, and
  `upsert_characteristics` self-healing FK kwargs.  Updated
  `upsert_characteristics` code example to show `mac`/`service_uuid` kwargs.
  Fixed stale "version 7" reference in Device Type Classification section.

* **`bleep/docs/observation_db_schema.md`** — Added schema version 8 (MAC
  normalisation with affected columns listed) and version 9 (UUID
  normalisation with affected columns listed) to the version history table.

---

## v2.7.28a – Internal Documentation: GATT Enumeration Commands (2026-03-18)

Added comprehensive internal documentation for the `gatt-enum` and `enum-scan`
CLI commands, closing a gap where only the debug-shell enumeration shortcuts
were documented.

### Added

* **`bleep/docs/gatt_enumeration.md`** — New reference covering both
  `gatt-enum` and `enum-scan` commands: synopsis, all flags and arguments,
  standard vs deep mode behavioural differences (read strategy, key casing,
  descriptor handling, retry logic), the four `enum-scan` variants (passive,
  naggy, pokey, brute) with payload pattern documentation, `--controlled` mode,
  a side-by-side comparison table, output format description, and database
  persistence notes.

### Improved

* **`bleep/docs/cli_usage.md`** — Added missing `enum-scan` row to the
  command table; refined the `gatt-enum` description to mention `--deep` and
  `--report` flags with a link to the new enumeration doc.

* **`bleep/docs/ble_scan_modes.md`** — Added cross-reference callout in the
  enumeration-variants section pointing to the new `gatt_enumeration.md` for
  full CLI flag documentation.

* **`bleep/docs/README.md`** — Added `gatt_enumeration.md` to the table of
  contents between scan modes and media mode.

---

## v2.7.28 – BLEEP Usability & Data Integrity Improvements (2026-03-17)

Fixes database foreign-key failures on characteristic inserts, ensures GATT
enumeration reads values even without `--deep`, cleans up CLI debug output,
adds tree-formatted enumeration output, normalises UUIDs to uppercase in the
observation database, and hardens the enum-scan return-type contract.

### Breaking Changes

* **UUID casing**: All UUIDs stored in the BLEEP observation database are now
  **uppercase** (e.g. `0000FF01-0000-1000-8000-00805F9B34FB`).  A one-time
  automatic migration (schema v8 → v9) converts existing data on first run.
  External tools reading the SQLite database directly should expect uppercase
  UUIDs after this upgrade.

### Fixed

* **`bleep/core/observations.py`** — Added `_normalize_uuid()` helper
  (mirrors `_normalize_mac()`) to convert UUID strings to uppercase before
  every write path: `upsert_services`, `upsert_characteristics`,
  `upsert_classic_services`, `insert_char_history`, `upsert_sdp_record`.
  Read path `get_characteristic_timeline` also normalises filter parameters.

* **`bleep/core/observations.py`** — Added `_ensure_service_exists(cur, mac,
  service_uuid)` defensive helper (mirrors `_ensure_device_exists`) that
  performs `INSERT OR IGNORE` to guarantee the parent service row exists
  before any characteristic insert, preventing `FOREIGN KEY constraint failed`
  errors.

* **`bleep/core/observations.py`** — `upsert_characteristics()` expanded with
  optional `mac` and `service_uuid` keyword arguments.  When supplied, the
  function calls `_ensure_device_exists` and `_ensure_service_exists`
  internally, making it self-healing against missing parent rows.

* **`bleep/core/observations.py`** — Schema migration v8 → v9 converts all
  existing UUIDs in `services`, `characteristics`, `classic_services`,
  `sdp_records`, and `char_history` tables to uppercase.

* **`bleep/ble_ops/scan.py`** — `pokey_enum()` and `brute_enum()` now return
  dictionaries (matching `passive_enum()` / `naggy_enum()`) instead of raw
  tuples, fixing the `'tuple' object has no attribute 'items'` crash in
  `_persist_mapping`.  Both include a `"device"` key preserving the device
  object for future use.

* **`bleep/ble_ops/scan.py`** — `_persist_mapping()` now passes `mac` and
  `service_uuid` to `upsert_characteristics()` for FK defense.

* **`bleep/cli.py`** — Removed broken special-case persistence block for the
  `passive` enum-scan variant that passed service-data dicts where UUID
  strings were expected (caused `'dict' object has no attribute 'strip'`
  and previously stored garbage).  All variants now use the unified
  `_persist_mapping()` path.

### Improved

* **`bleep/core/observations.py`** — `upsert_services()` normalises UUIDs to
  uppercase for storage but returns its ID-mapping dict keyed by the
  *original* (caller-supplied) UUID, preserving backward compatibility.

* **`bleep/cli.py`**, **`bleep/modes/exploration.py`**,
  **`bleep/modes/aoi.py`**, **`bleep/analysis/aoi_analyser.py`** — All
  `upsert_characteristics` call sites updated to pass `mac` and
  `service_uuid` keyword arguments, completing the FK defense chain.

* **`bleep/core/observations.py`** — `_ensure_device_exists()` integrated
  into 8 child-table methods; `_db_cursor()` rolls back on error;
  `store_signal_capture()` debug output migrated to `print_and_log`.

* **`bleep/dbuslayer/characteristic.py`** — `read_value_with_fallback()`
  three-tier read strategy; `safe_read_with_retry()` uses fallback reads.

* **`bleep/dbuslayer/device_le.py`** — `_enumerate_gatt_values(deep)` reads
  values in both deep and non-deep modes; redundant re-enumeration guarded.

* **`bleep/dbuslayer/descriptor.py`** — Fixed `b"\x00"` fabrication in
  fallback reads.

* **`bleep/ble_ops/conversion.py`** — `format_gatt_tree()` for human-readable
  tree output with UUID name resolution, mine/permission map summaries.

* **`bleep/cli.py`** — `gatt-enum` and `enum-scan` output uses
  `format_gatt_tree()` instead of raw JSON; debug `print()` calls migrated
  to `print_and_log()`.

---

## v2.7.27 – Codebase Cleanup & Preparation for v2.8.0 (2026-03-10)

Comprehensive codebase cleanup, variable uniformity enforcement, database
schema hardening, and exception handling improvements in preparation for the
BLEEP v2.8.0 expansion.

### Breaking Changes

* **MAC address casing**: All MAC addresses stored in the BLEEP observation
  database are now **uppercase** (e.g. `AA:BB:CC:DD:EE:FF`).  A one-time
  automatic migration (schema v7 → v8) converts existing data on first run.
  External tools reading the SQLite database directly should expect uppercase
  MACs after this upgrade.

* **Output filenames**: PBAP, OPP, and MAP cache filenames now use uppercase
  hex (e.g. `AABBCCDDEEFF_PB.vcf` instead of `aabbccddeeff_PB.vcf`).

### Fixed

* **`bleep/core/observations.py`** — `_normalize_mac()` changed from
  `mac.lower()` to `mac.upper()`.  Added missing `_normalize_mac()` calls to
  `upsert_classic_services()`, `upsert_pbap_metadata()`,
  `snapshot_media_player()`, and `snapshot_media_transport()`.

* **`bleep/core/observations.py`** — Removed duplicate `sdp_records` table
  definition from `_SCHEMA_SQL`.

* **`bleep/core/observations.py`** — `upsert_sdp_record()` now uses
  `json_dumps()` instead of raw `_json.dumps()` for `profile_descriptors`
  column.

* **`bleep/core/observations.py`** — `upsert_characteristics()` now converts
  the `value` parameter to `bytes` for the BLOB column, and stores
  `permission_map` when provided.

* **`bleep/core/observations.py`** — `upsert_device()` validates column names
  against a whitelist before interpolation, preventing potential SQL injection
  from untrusted callers.

* **`bleep/core/observations.py`** — `explain_query()` restricted to single
  `SELECT` statements to prevent SQL injection via multi-statement input.

* **`bleep/core/observations.py`** — `get_devices()` with `status='media'`
  filter now uses `SELECT DISTINCT` to avoid duplicate rows when a device has
  multiple media players.

* **`bleep/core/observations.py`** — `maintain_database()` statistics now
  include `sdp_records`, `device_type_evidence`, and `pbap_metadata` tables.

* **`bleep/dbuslayer/media_stream.py`** — Fixed MAC comparison bug: the
  colon-separated `device_mac` was compared against the underscore-separated
  `path_mac` (always `False`).

* **`bleep/dbuslayer/device_classic.py`** — `mac_address` stored as uppercase
  instead of lowercase, matching the D-Bus path convention used one line later.

* **`bleep/dbuslayer/device_le.py`** — `mac_address` stored as uppercase.

* **MAC uniformity** — Converted all remaining `.lower()` MAC sites to
  `.upper()` across: `cli.py`, `adapter.py`, `manager.py`, `signals.py`,
  `device_classic.py`, `device_le.py`, `audio_recon.py`, `audio_tools.py`,
  `audio_profile_correlator.py`, `amusica.py`, `agent.py`, `ctf.py`,
  `capture_config.py`, `device_management.py`, `debug_classic.py`,
  `debug_classic_obex.py`, `aoi_analyser.py`.

### Improved

* **`bleep/mesh/__init__.py`** — Guarded imports of planned-but-unimplemented
  `agent` and `provisioning` modules with `try/except ImportError` so the
  package loads cleanly.  Docstring documents planned scope.

* **`bleep/gatt/__init__.py`** — Same treatment: guarded `service`,
  `characteristic`, `descriptor` imports.  Docstring explains these currently
  live in `bleep.dbuslayer`.

* **`bleep/dbus/__init__.py`** — Removed phantom `"adapter"` and `"gatt"`
  from `__all__` and `TYPE_CHECKING` block.  Added `"connection_pool"` to
  `__all__`.  Updated docstring.

* **Exception handling** — All bare `except:` blocks (14 locations across 9
  files) narrowed to specific exception types.  Critical `except Exception:
  pass` blocks in `device_le.py`, `device_classic.py`, `signals.py`,
  `characteristic.py`, and `descriptor.py` now emit `LOG__DEBUG` messages.

* **Database schema v8** — Migration converts all existing MACs to uppercase
  across all 11 tables containing a `mac` column.

---

## v2.7.26 – Debug Mode UX: Mines Command, Help Grouping & Unified Info Display (2026-03-10)

Adds the `mines` command for inspecting landmine and permission maps from
enumeration results, reorganises the `help` menu into purpose-based groups
with a compact/detailed toggle, and unifies the `info` command output so BLE
and Classic devices share a consistent property format.

### Added

* **`bleep/modes/debug_scan.py`** — `cmd_mines()`: new Debug Mode command that
  displays the contents of `state.current_mine_map` and
  `state.current_perm_map` in a human-readable, categorised format.  When the
  device is still connected, also prints `get_landmine_report()` and
  `get_security_report()` detail records.

* **`bleep/modes/debug.py`** — `mines` registered in the dispatch table.

### Improved

* **`bleep/modes/debug.py`** — `_cmd_help()` rewritten:
  - Commands grouped by purpose: Scanning, Connection, Device Information,
    BLE Enumeration, BLE Read/Write, Advanced BLE Read/Write, BR/EDR Classic
    Profiles, Pairing & Security, D-Bus Inspection, Navigation, Analysis &
    Database, Session.
  - `detailed off` (default): compact listing showing only command names per
    group.
  - `detailed on`: full usage synopsis and description for every command,
    retaining all original information.

* **`bleep/modes/debug_connect.py`** — `cmd_info()` unified display:
  - BLE and Classic devices now share the same visual layout — Title Case
    property labels, consistent column alignment, and boolean values shown as
    both human-readable and numeric (e.g. `True (1)` / `False (0)`).
  - BLE previously showed raw D-Bus values (`Blocked: 0`); Classic showed
    Python booleans with lowercase keys (`blocked: False`).  Both now use the
    unified format.
  - All parenthetical clarifiers gated on `detailed on`: boolean numeric
    suffixes (`True (1)` → `True`), Device Class decoding, profile UUID names,
    and `Classic (BR/EDR)` → `Classic`.  Only the `(use 'cservices' to list)`
    hint remains unconditional.
  - `_info_from_dbus_path()` (no-wrapper fallback) also uses the unified
    formatter.
  - Raw captured data (ServiceData, UUIDs, ManufacturerData) is never altered.

* **`bleep/modes/debug_scan.py`** — Enumeration summary line fix:
  - `mine=` / `perm=` renamed to `landmines=` / `permissions=` for clarity.
  - Counts now reflect total UUIDs across all categories (via
    `_count_map_uuids()`) instead of the number of top-level category buckets.
    e.g. `landmines=42` instead of the misleading `mine=1`.

---

## v2.7.25 – MAP D-Bus Timeout Fix & Error Hint Improvements (2026-03-10)

Fixes `cmap list telecom/msg/inbox` (and other large-folder operations) timing
out with `org.freedesktop.DBus.Error.NoReply` by passing explicit timeouts to
all D-Bus method calls in `MapSession`.  Also adds actionable error hints for
`Service Unavailable` and `NoReply` errors, and a proactive warning when
`cmap read` targets a non-inbox folder where `readStatus` changes are
semantically rejected by many MAP-MSE implementations.

### Fixed

* **`bleep/dbuslayer/obex_map.py`** — All D-Bus method calls on the
  `MessageAccess1` proxy (`ListMessages`, `ListFolders`, `UpdateInbox`,
  `ListFilterFields`) and the internal `_populate_message_objects` helper now
  pass an explicit `timeout` parameter derived from `self._timeout`.
  `ListMessages` and `_populate_message_objects` use `self._timeout * 4`
  (default 120 s) since large folders (100+ messages) require the remote device
  to build and transfer a full XML listing.  Other calls use `self._timeout`
  (default 30 s).  Previously all calls used the dbus-python default (~25 s),
  which was insufficient for inbox folders on slower devices.

### Added

* **`bleep/modes/debug_classic_obex.py`** — `_print_obex_error_hints()`:
  - New `"service unavailable"` branch explains OBEX 0x53 rejection with
    MAP-specific guidance (readStatus only meaningful for inbox messages).
  - New `"noreply"` branch explains D-Bus timeout with guidance on large
    folders and retry strategies.
  - `cmap read` now prints a proactive warning when the current folder context
    is not `inbox`, since many MAP-MSE devices reject readStatus changes on
    sent/draft/outbox messages with `Service Unavailable`.

### Improved

* **`bleep/modes/debug_classic_obex.py`** — OBEX timeout hint now mentions
  device sleep/lock state as the most common cause and suggests waking the
  phone before large-folder operations.  `cmap` help text clarified: `get`
  downloads & displays message contents, `read` only toggles the read flag.
  Added tip about waking the target device.

### Verified (live-device testing against Samsung SM-G891A)

* `cmap folders`, `cmap list` (all 5 leaf folders), `cmap get`, `cmap push`,
  `cmap props`, `cmap delete`, `cmap instances`, `cmap types` — all **PASS**.
* `cmap read <handle> true/false` — **PASS** on inbox messages; confirmed flag
  toggle via subsequent `cmap list` showing `[R]` → `[ ]` transition.
* `cmap read` on outbox — **expected failure** (`Service Unavailable`);
  device-side semantic restriction, not a BLEEP bug.
* Large-folder timeouts (inbox, sent) — caused by device sleep/lock state, not
  D-Bus or BLEEP.  Requests succeed on retry once device is awake.

---

## v2.7.24 – MAP Property Access Fix & Push LENGTH Validation (2026-03-10)

Fixes `cmap read` and `cmap delete` commands which failed with
`UnknownMethod: Method "SetProperty" ... doesn't exist` — the
`org.bluez.obex.Message1` interface only exposes `Get` as a method;
`Read` and `Deleted` are GDBus **properties** that must be set via
`org.freedesktop.DBus.Properties.Set()`.  Also adds pre-push validation
of the bMessage `LENGTH:` field to prevent silent device-side rejections
when the field doesn't match the actual content size.

### Fixed

* **`bleep/dbuslayer/obex_map.py`** — `set_message_read()` and
  `set_message_deleted()` now use `org.freedesktop.DBus.Properties.Set()`
  with a variant-wrapped boolean (`variant_level=1`) instead of calling
  a non-existent `SetProperty` method on the `Message1` interface.  The
  BlueZ `map_msg_methods[]` table only registers `Get`; `Read` and
  `Deleted` are standard GDBus properties with setter callbacks
  (`set_read`, `set_deleted`) accessed through the Properties interface.
  The reference `map-client` script uses a legacy `SetProperty` call
  that no longer exists in the current BlueZ GDBus implementation.

### Added

* **`bleep/modes/debug_classic_obex.py`** — `_validate_bmsg_length()`:
  pre-push check that compares the declared `LENGTH:` value in a bMessage
  file against the actual byte size of the `BEGIN:MSG` … `END:MSG`
  content.  A mismatch warning is printed with the correct value so the
  user can fix the file before retrying.  This prevents the common case
  where editing a downloaded bMessage changes the body length but the
  `LENGTH:` field is not updated, causing the device to silently discard
  the message despite a successful OBEX transfer.

---

## v2.7.23 – MAP Handle Context, Push Validation & Error Hints (2026-03-10)

Fixes four remaining MAP issues: handle-based commands (`get`, `props`,
`read`, `delete`) failing with `UnknownObject`; `push` silently discarding
plain-text files; misleading error hints for "Not Implemented" and
`CreateSession` failures; intermittent `CreateSession` D-Bus signature
mismatch (`sa{ss}` vs `sa{sv}`).

### Fixed

* **`bleep/dbuslayer/obex_map.py`** — `CreateSession` now passes
  `dbus.Dictionary(session_args, signature="sv")` instead of a plain
  Python `dict`.  The `dbus-python` library could infer `a{ss}` for a
  `{"Target": "map"}` dict, which does not match the `a{sv}` signature
  expected by `org.bluez.obex.Client1.CreateSession` — causing
  intermittent `UnknownMethod` failures.

* **`bleep/dbuslayer/obex_map.py`** — `get_message()`,
  `get_message_properties()`, `set_message_read()`, `set_message_deleted()`
  now accept a `folder` keyword argument.  When provided, the session
  navigates to the folder and calls `ListMessages` to materialise message
  D-Bus objects before attempting handle access.  This matches the
  lifecycle pattern used by BlueZ's reference `map-client` script and
  fixes `UnknownObject` errors on every handle-based command.

* **`bleep/modes/debug_classic_obex.py`** — `_print_obex_error_hints()`
  now handles `"not implemented"` and `"unknownmethod"` errors with
  specific guidance **before** the generic `"obex"` catch-all, preventing
  the misleading *"Ensure bluetooth-obexd is running"* hint for errors
  that are unrelated to daemon state.

### Added

* **`bleep/dbuslayer/obex_map.py`** — `MapSession._populate_message_objects(folder)`:
  navigates to *folder* and calls `ListMessages("")` to create ephemeral
  message D-Bus objects within the current session.  Called automatically
  by handle-based methods when a `folder` is supplied.

* **`bleep/modes/debug_classic_obex.py`** — `_last_map_folder` module
  state and `_require_map_folder()` helper.  Handle-based commands (`get`,
  `props`, `read`, `delete`) now automatically use the folder from the
  last successful `cmap list` call.  If no folder context is available,
  the user is prompted to run `cmap list <folder>` first.

* **`bleep/modes/debug_classic_obex.py`** — `cmap push` now checks
  whether the file starts with `BEGIN:BMSG` (the bMessage envelope
  required by MAP / RFC 6474).  A warning is printed if the file does not
  appear to be in bMessage format, but the push proceeds to let the OBEX
  transport complete.

### Improved

* **`cmap` help text** — updated to document the folder-context
  dependency for handle-based commands and the bMessage format
  requirement for `push`.

---

## v2.7.22 – MAP Fixes, Folder Tree Enumeration & Debug Logging (2026-03-10)

Fixes six bugs affecting Message Access Profile (MAP) interactivity in
BLEEP Debug Mode, adds recursive folder tree enumeration, and improves
debug logging.  Observed against Samsung SCH-U365 (`E4:FA:ED:83:D8:47`):
`cmap folders` only showed root entries; `cmap list` failed with a D-Bus
unpacking error; error diagnostics were absent from debug logs.

### Fixed

* **`bleep/ble_ops/classic_map.py`** — `detect_map_service()` now matches
  `"sms"` and `"mms"` in service-map keys.  `build_svc_map` keys the MAP
  service as `"SMS/MMS"` (from the SDP Service Name), which the previous
  pattern set (`1132`, `1134`, `message`, `map`) did not cover — causing
  the false warning *"MAP service not detected in service map"*.

* **`bleep/ble_ops/classic_map.py`** — `list_messages()` folder semantics
  rewritten:
  - **Double-folder bug**: previously called `set_folder(folder)` then
    `list_messages(folder)`, resolving as `folder/folder` → OBEX "Bad
    Request".  Now calls `list_messages("")` (current folder) after
    navigating.
  - **Root listing**: calling `cmap list` without a folder is now
    rejected early with an actionable hint (MAP root has no messages).
  - **Dot/dotdot rejection**: `"."` and `".."` are not valid OBEX MAP
    path components — now caught with a clear error message.

* **`bleep/dbuslayer/obex_map.py`** — `get_supported_types()` now catches
  `DBusException` when `SupportedTypes` is unavailable (e.g. BlueZ 5.64)
  and returns an empty list.  The full D-Bus error is logged to
  `LOG__DEBUG`.

* **`bleep/ble_ops/classic_map.py`** — `list_mas_instances()` accepts an
  optional `service_map` parameter.  When the cached service map from
  `state.current_mapping` is provided, it extracts MAP entries directly
  instead of running a fresh `sdptool` process.

* **`bleep/ble_ops/classic_sdp.py`** — `_parse_xml_record()` now handles
  both `<text value="..."/>` (sdptool) and `<text>...</text>` (D-Bus) XML
  formats via new `_xml_elem_value()` / `_xml_findtext()` helpers.  This
  fixes the empty-records issue from `sdptool browse --xml` where all
  fields (name, UUID, channel) were `None`.

* **`bleep/dbuslayer/obex_map.py`** — `list_messages()` iterated the
  `a{oa{sv}}` return value from `ListMessages` directly instead of calling
  `.items()`, causing `ValueError: too many values to unpack (expected 2)`
  when the `dbus.Dictionary` yielded only keys.  Now uses `.items()` with
  defensive type checking for `dbus.Dictionary` vs `dbus.Array` to handle
  BlueZ version differences.

### Added

* **`bleep/dbuslayer/obex_map.py`** — `MapSession.walk_folder_tree()`:
  recursive depth-first enumeration of the MAP folder hierarchy using
  `SetFolder` + `ListFolders` within a single OBEX session.  Returns a
  nested `[{"name": ..., "children": [...]}]` structure.  `max_depth`
  parameter (default 10) prevents runaway recursion.

* **`bleep/ble_ops/classic_map.py`** — `list_folder_tree()`: high-level
  wrapper around `walk_folder_tree()` with BLEEP-standard logging.

* **`bleep/modes/debug_classic_obex.py`** — `cmap folders` now displays
  the complete MAP folder tree with indentation (e.g. `telecom/` →
  `msg/` → `inbox/`, `outbox/`, `sent/`, `deleted/`, `draft/`) instead
  of only the root-level entries.

* **`bleep/modes/debug_classic_obex.py`** — `cmap list` now suggests
  valid leaf message folders (via on-demand tree enumeration) when the
  remote device rejects a request with "Bad Request" — typically because
  the user specified an intermediate container folder rather than a leaf.

### Improved

* **`bleep/dbuslayer/obex_map.py`** — `list_messages()` now logs the raw
  D-Bus return type and length to `LOG__DEBUG` before unpacking, aiding
  diagnosis of unexpected return formats.

* **`bleep/modes/debug_classic_obex.py`** — all `except` clauses in
  `cmd_cmap` now write to `LOG__DEBUG` via `print_and_log()`, ensuring
  every MAP error is captured in the debug log file.  `.`/`..` path
  validation moved from `classic_map.list_messages()` to the command
  handler (before the `try` block), so that `ValueError` inside `try`
  represents a genuinely unexpected error.

* **`bleep/modes/debug_classic_obex.py`** — `_print_obex_error_hints()`
  extended with MAP-specific hint branches for "Bad Request" (root folder
  listing), "Not Found" (invalid folder), "No such property" (missing
  BlueZ property), and "UnknownObject" (invalid message handle).  All MAP
  `cmd_cmap` error paths now pass `operation="map"` and format errors via
  `format_dbus_error()`.

* **`bleep/modes/debug_classic_obex.py`** — `cmap props` now validates
  that the argument is alphanumeric before attempting the D-Bus call,
  preventing confusing `UnknownObject` errors when a folder name is passed
  instead of a message handle.

* **`bleep/modes/debug_classic_obex.py`** — `cmap instances` now passes
  the cached `state.current_mapping` to `list_mas_instances()`, avoiding a
  redundant SDP scan every invocation.

---

## v2.7.21 – OPP Fast-Completion Race Fix (2026-03-09)

Fixes false-failure reporting for OPP transfers that complete faster than
the poller can read them.  Live testing against the SCH-U365 confirmed:

- `copp send` delivers the file — now correctly reports success with size.
- `copp pull` successfully retrieves the device's name card — now reports
  the saved file path and size (e.g. `(234 bytes)`).
- `copp exchange` is correctly reported as unimplemented in obexd 5.64.

### Fixed

* **`bleep/dbuslayer/_obex_common.py`** — `poll_obex_transfer()` no longer
  raises `RuntimeError` when the Transfer1 object is removed before the
  first status read.  Instead returns `{"status": "removed"}` to let each
  caller verify the actual outcome.

* **`bleep/dbuslayer/obex_opp.py`** — `opp_send_file()` now treats a
  "removed" transfer status as a successful fast completion (the remote
  device accepted and processed the file before the poller could read it).

* **`bleep/dbuslayer/obex_opp.py`** — `opp_pull_business_card()` now
  validates the destination file (existence + non-zero size) for **all**
  completion paths — both normal "complete" and fast-race "removed".  obexd
  removes the file on failed GET transfers (`transfer.c`), so file existence
  is a reliable success indicator per the BlueZ reference.  Raises a clear
  error when no file was written.

* **`bleep/dbuslayer/obex_opp.py`** — `opp_exchange_business_cards()` now
  detects the "Not Implemented" error from obexd and raises a clear message
  directing users to use separate send/pull commands.

* **`bleep/modes/debug_classic_obex.py`** — `_print_obex_error_hints()`
  updated with specific hints for pull-unsupported and exchange-unimplemented
  errors.

* **`bleep/modes/debug_classic_obex.py`**, **`bleep/cli.py`** — Pull
  success messages now include file size: `Business card saved → <path>
  (<N> bytes)`.

* **`bleep/ble_ops/classic_opp.py`** — `pull_business_card()` log message
  now includes file size.

### Verified (live device testing)

* `copp send /tmp/test.vcf` → `[+] OPP send complete: ?/107 bytes transferred`
* `copp pull` → `[+] Business card saved → ~/.cache/obexd/…_card.vcf`
  (file received successfully from SCH-U365)
* `copp exchange` → clean "not supported by this version of obexd" message

---

## v2.7.20 – OPP OBEX Polishing (2026-03-09)

Robustness, diagnostics, and new functionality for Object Push Profile
operations. Addresses three layered issues observed against the SCH-U365
(`14:89:FD:31:8A:7E`): (A) SDP parsing returning empty records so no
RFCOMM channel hint was available, (B) a transfer-object race condition
in the OBEX poller when the remote device fails the transfer immediately,
and (C) the default pull destination path potentially being outside
obexd's permitted write area on Ubuntu.

Despite the host OS reporting "no supported services" to the target device
during generic connection, BLEEP's OPP operations via obexd do reach the
phone — the device prompts the user to accept and attempts the transfer.
This confirms that targeted profile operations can succeed even when the
host's generic SDP presentation appears incompatible.

### Fixed

* **`bleep/dbuslayer/_obex_common.py`** — `poll_obex_transfer()` now catches
  `DBusException` when reading the transfer object's `Status` property.  If
  obexd tears down the transfer before the poller reads it (race condition when
  the remote device fails immediately after accepting), a clean `RuntimeError`
  is raised instead of a raw `UnknownObject` D-Bus error propagating to the
  user.

* **`bleep/modes/debug_classic_obex.py`** — Default `copp pull` destination
  changed from `/tmp/` to `~/.cache/obexd/` to stay within obexd's expected
  write area on Ubuntu (AppArmor / sandboxing may restrict writes elsewhere).

* **`bleep/modes/debug_classic_obex.py`** — When SDP parsing returns empty
  records (no OPP channel in `state.current_mapping`), `cmd_copp` now falls
  back to a targeted `sdptool search --bdaddr <MAC> 0x1105` to discover the
  OPP RFCOMM channel directly.

### Added

* **`bleep/dbuslayer/obex_opp.py`** — `opp_exchange_business_cards()`:
  wraps `ObjectPush1.ExchangeBusinessCards` per `org.bluez.obex.ObjectPush(5)`.
  Pushes a local vCard then pulls the remote device's business card in a
  single OBEX session.

* **`bleep/ble_ops/classic_opp.py`** — `exchange_business_cards()` operations
  wrapper with BLEEP logging and observation-DB storage.

* **`bleep/modes/debug_classic_obex.py`** — `copp exchange <local.vcf> [dest]`
  debug command.

* **`bleep/ble_ops/classic_sdp.py`** — `discover_service_channel(mac, uuid)`
  helper for targeted single-service SDP lookup via `sdptool search`.

### Changed

* **`bleep/dbuslayer/obex_opp.py`** — `opp_send_file()`,
  `opp_pull_business_card()`, and `opp_exchange_business_cards()` now pass an
  explicit 90 s D-Bus method-call timeout to prevent indefinite blocking when
  obexd stalls on a dead RFCOMM channel.

* **`bleep/modes/debug_classic_obex.py`** — `_print_obex_error_hints()` now
  accepts an `operation` keyword and provides targeted guidance for transfer-
  object teardown errors (suggests trying `copp send` to verify OPP
  connectivity when pull fails).  `copp` usage text documents the OPP file-
  listing limitation and points to `cftp` for directory browsing.

### Internal

* Tracking ID: `opp-obex-polish-2026-03-09`

---

## v2.7.19 – OPP OBEX Timeout & Exception Handling Fix (2026-03-09)

**Note**: Code-level fixes are implemented (channel passthrough, exception
wrapping, PBAP NameError).  OPP `copp pull` remains **unverified** — the sole
test device (SCH-U365) accepts the Bluetooth connection after the channel fix
but immediately reports failure on the phone side, indicating the device's OPP
server likely does not support `PullBusinessCard`.  `copp send` has not yet
been tested.  Full OPP validation requires a device with confirmed
bidirectional OPP support.

### Fixed

* **`bleep/dbuslayer/obex_opp.py`** — `opp_send_file()` and
  `opp_pull_business_card()` called `CreateSession` without a `Channel` hint,
  forcing obexd to redo SDP during an active RFCOMM keep-alive.  On older
  devices (e.g. SCH-U365) this caused a 20 s OBEX CONNECT timeout.  Both
  functions now accept an optional `channel` parameter; when provided,
  `dbus.Byte(channel)` is passed in the `CreateSession` options dict.

* **`bleep/dbuslayer/obex_opp.py`** — `bus.get_object()` and
  `dbus.Interface()` after `CreateSession` were not wrapped in `try/except`,
  so a partially-torn-down session raised a raw `DBusException`
  (`UnknownObject`) instead of a clean `RuntimeError`.

* **`bleep/modes/debug_classic_obex.py`** — `cmd_copp` now extracts the OPP
  RFCOMM channel from `state.current_mapping` and passes it through to the
  dbuslayer, avoiding redundant SDP lookups by obexd.

* **`bleep/modes/debug_classic_obex.py`** — `_print_obex_error_hints()`
  extended with timeout-specific guidance (check phone screen for acceptance
  prompt, verify keep-alive isn't blocking, try disconnecting/reconnecting).

* **`bleep/ble_ops/classic_pbap.py`** — `pbap_dump_async()` had redundant
  `from bleep.core.log import print_and_log` inside conditional/except blocks
  (lines 328, 343) that shadowed the module-level import.  When those branches
  didn't execute (the common path), the `_watchdog_cb` closure raised
  `NameError: cannot access free variable 'print_and_log'`.  Removed the
  redundant local imports.

### Changed

* **`bleep/ble_ops/classic_opp.py`** — `send_file()` and
  `pull_business_card()` now accept an optional `channel: int` parameter,
  threaded through to the dbuslayer functions.

### Internal

* Tracking ID: `opp-obex-fix-2026-03-09`

---

## v2.7.18 – Audio Tools & Profile Correlator Bug Fixes (2026-03-05)

### Fixed

* **`bleep/ble_ops/audio_tools.py`** — `get_profiles_for_card()` regex `[a-z_]+`
  excluded profile names containing digits (e.g. `a2dp_sink`, `a2dp_source`).
  Changed to `[a-z0-9_]+`.

* **`bleep/ble_ops/audio_tools.py`** — `_extract_interfaces_from_block()` regex
  expected numbered-list format (`0. name`) but actual `pacmd list-cards` output
  uses `name/#index: description`.  Fixed to match real output.

* **`bleep/ble_ops/audio_tools.py`** — `_extract_interfaces_from_block()` derived
  `role_key` via `section_key.rstrip("s")` producing `"source"/"sink"` which
  never matched `_role_for_interface_name()` checks for `"sources"/"sinks"`.
  Now passes `section_key` directly.

* **`bleep/ble_ops/audio_tools.py`** — `list_audio_sinks()` and
  `list_audio_sources()` used exclusive `if/elif` branching, so `"pipewire"`
  backend (PipeWire with PA compat) never reached the `pactl` path.  Both
  methods now try PipeWire tools first then also try `pactl` when PA compat is
  available, merging results.

* **`bleep/ble_ops/audio_profile_correlator.py`** — MAC comparison in
  `identify_profiles_for_device()`, `get_transport_for_profile()`, and
  `get_all_transports_for_device()` compared colon-separated MAC against
  underscore-separated MAC (always `False`).  Removed erroneous
  `.replace(":", "_")`.

* **`bleep/ble_ops/audio_recon.py`** — `_recon_pulseaudio()` restored the first
  non-off profile instead of the original active profile after cycling.  Now
  saves and restores the original active profile.

### Added

* **`bleep/ble_ops/audio_tools.py`** — `get_active_profile_for_card()` method
  that returns the currently active profile name for a PA/PipeWire card.

* **`bleep/ble_ops/audio_tools.py`** — `identify_bluetooth_profiles_from_alsa()`
  now supplements sink/source enumeration with card-level enumeration via
  `get_bluez_cards()` + `get_profiles_for_card()`, discovering all available
  profiles regardless of which is currently active.

### Internal

* Tracking ID: `audio-tools-fix-2026-03-05`

---

## v2.7.17 – MediaPlayer Optional Property Handling (2026-03-04)

### Fixed

* **`bleep/dbuslayer/media.py`** — `MediaPlayer._get_property()` now
  distinguishes between optional and required properties per the BlueZ
  `org.bluez.MediaPlayer.rst` specification.  Optional properties (`Name`,
  `Type`, `Subtype`, `Browsable`, `Searchable`, `Playlist`, `Equalizer`,
  `Repeat`, `Shuffle`, `Scan`, `ObexPort`) that a device doesn't expose
  now log at `[*]` (informational) instead of `[-]` (error), eliminating
  misleading "Failed to get" debug messages for compliant devices.

* **`bleep/dbuslayer/media.py`** — `MediaPlayer.get_name()` refactored to
  delegate to `_get_property()` so it benefits from the optional-property
  handling above.

* **`bleep/core/observations.py`** — `snapshot_media_player()` now uses
  `player.get_properties()` (D-Bus `GetAll`) instead of individual getter
  calls.  `GetAll` returns only properties the device actually exposes,
  avoiding D-Bus errors for optional properties like `Name` and `Subtype`.

### Internal

* Tracking ID: `bc-54`

---

## v2.7.16 – SDP XML Parser & Collision-safe Service Map (2026-03-04)

### Fixed

* **`bleep/ble_ops/classic_sdp.py`** — Replaced `sdptool browse --tree` with
  `sdptool browse --xml` in the fallback chain.  The previous `--tree` output
  was incorrectly parsed by `_parse_records()` (designed for `sdptool records`),
  causing `name=None`, `uuid=None`, and L2CAP PSM values being misidentified as
  RFCOMM channels.  The new `_parse_browse_xml()` function reliably extracts all
  SDP attributes from the structured XML output.  Discovery chain is now:
  D-Bus → `browse --xml` → `records`.

* **`bleep/ble_ops/classic_sdp.py`** — D-Bus `GetServiceRecords` path no longer
  requires at least one RFCOMM channel to accept the result, aligning with the
  v2.7.15 enriched mapping that includes all services.

### Added

* **`bleep/ble_ops/classic_sdp.py`** — New `_parse_xml_record()` and
  `_parse_browse_xml()` functions for parsing `sdptool browse --xml` output.
  Extracts Service Name (0x0100), Description (0x0101), Service Record Handle
  (0x0000), Service Class ID (0x0001), Protocol Descriptor List (0x0004),
  Profile Descriptor List (0x0009), and Service Version (0x0300).

* **`bleep/ble_ops/classic_sdp.py`** — New `build_svc_map()` public helper that
  builds a collision-safe `Dict[str, Dict]` from raw SDP records.  Duplicate
  keys (e.g. two "Voice Gateway" entries from different handles) are
  disambiguated by appending the SDP handle.

### Changed

* **`bleep/ble_ops/classic_connect.py`**, **`bleep/modes/debug_classic.py`**,
  **`bleep/modes/debug_classic_rfcomm.py`**, **`bleep/modes/debug_pairing.py`**,
  **`bleep/cli.py`** — All inline `svc_map` construction loops replaced with
  the shared `build_svc_map()` helper, eliminating code duplication and
  ensuring consistent collision handling across all entry points.

### Internal

* Tracking ID: `bc-53`

---

## v2.7.15 – Enriched Classic SDP Service Mapping (2026-03-04)

### Changed

* **`bleep/ble_ops/classic_connect.py`** — `svc_map` return type changed from
  `Dict[str, int]` to `Dict[str, Dict[str, Any]]`.  Each entry now carries the
  full SDP record: `uuid`, `name`, `channel`, `handle`, `service_version`,
  `description`, and `profile_descriptors`.  Services without an RFCOMM channel
  are now included (previously filtered out).

* **`bleep/modes/debug_classic.py`**:
  * New `_ch(entry)` helper for uniform channel extraction from both the
    enriched dict and legacy int formats.
  * `cmd_cservices` rewritten — normal mode shows a one-line summary with UUID
    translation; `detailed on` shows handle, version, profile descriptors, and
    description per record.
  * `cmd_ckeep` SDP fallback and channel resolution updated to build enriched
    dicts and use `_ch()`.
  * `cmd_csdp` local `svc_map` build updated to enriched dicts; summary now
    shows total services and RFCOMM count.
  * `cmd_pbap` PBAP channel lookup now uses `_ch()` and also matches on UUID
    field inside the enriched dict.

* **`bleep/modes/debug_classic_rfcomm.py`** — `_resolve_rfcomm_channel()` SDP
  fallback now builds enriched dicts; `--svc` and `--first` lookups use `_ch()`.

* **`bleep/modes/debug_pairing.py`** — `post_pair_connect_classic()` builds
  enriched dicts from SDP records; keep-alive channel extraction updated.

* **`bleep/modes/debug_connect.py`** — `cmd_info` Classic info message updated
  from "RFCOMM services" to "SDP services" to reflect inclusion of non-RFCOMM
  records.

* **`bleep/cli.py`** — `classic-enum` SDP summary display updated to enriched
  format; connection-based enumeration message updated.

### Design Notes

The enriched `current_mapping` provides BLE-like service detail parity for
Classic connections.  The `_ch()` helper ensures backward compatibility if any
legacy `int` values remain in the mapping during transition.

---

## v2.7.14 – debug_classic_data.py Module Split (2026-03-04)

### Refactored

* **`bleep/modes/debug_classic_data.py`** — split from a 1,192-line monolith
  into three focused sub-modules to improve maintainability:
  * **`debug_classic_rfcomm.py`** (~378 lines) — `cmd_copen`, `cmd_csend`,
    `cmd_crecv`, `cmd_craw`, plus shared helpers `_resolve_rfcomm_channel()`
    and `_ensure_classic_connected()`.
  * **`debug_classic_obex.py`** (~646 lines) — `cmd_copp`, `cmd_cmap`,
    `cmd_cftp`, `cmd_csync`, `cmd_cbip`, plus shared `_print_obex_error_hints()`.
  * **`debug_classic_profiles.py`** (~200 lines) — `cmd_cpan`, `cmd_cspp`.
  * **`debug_classic_data.py`** (49-line shim) — re-exports all 11 `cmd_*`
    symbols so existing imports from `debug.py` work without modification.

### Fixed

* **`cmd_csync` / `cmd_cbip` signature bug** — both functions had reversed
  parameter order (`state, args` instead of `args, state`) and referenced the
  non-existent `state.bdaddr` attribute.  Corrected to use the standard
  `(args: List[str], state: DebugState)` signature with the
  `state.current_device.mac_address` pattern used by all other commands.

---

## v2.7.13 – Raw OBEX & L2CAP Design Documents (2026-03-03)

### Added

* **`bleep/protocols/` package** (new) — low-level protocol implementations
  that operate directly on raw sockets rather than through BlueZ D-Bus.
  Currently contains design documentation only; implementation is planned for
  future versions.
* **Raw OBEX design document** (`bleep/protocols/obex_design.md`) — complete
  design for a raw OBEX packet codec and client session state machine over
  RFCOMM, bypassing `obexd`.  Covers:
  - OBEX packet structure, opcodes, response codes, header format
  - Connect handshake with Target header for profile selection
  - Proposed `ObexPacket`, `ObexHeader`, `ObexClient` API
  - Multi-packet GET/PUT transfer handling
  - Transport independence (RFCOMM, L2CAP, TCP for testing)
  - Integration plan with existing operations layer (`--raw` backend flag)
  - Phased implementation roadmap (v2.7.13–v2.7.15)
* **L2CAP design document** (`bleep/protocols/l2cap_design.md`) — complete
  design for raw L2CAP channel access via `socket.AF_BLUETOOTH` /
  `BTPROTO_L2CAP`.  Covers:
  - L2CAP socket types (SEQPACKET, DGRAM, STREAM)
  - Well-known PSM values from Bluetooth SIG Assigned Numbers
  - Socket options (security levels, modes, PHY, channel policy)
  - Proposed `l2cap_open()`, `l2cap_listen()`, `L2capConnection` API
  - Security level helpers and constants
  - Debug commands (`l2open`, `l2send`, `l2recv`, `l2raw`, `l2listen`)
  - SDP-based dynamic PSM discovery
  - BLE L2CAP CoC (Connection-oriented Channels) support plan
  - Phased implementation roadmap (v2.7.13–v2.7.15+)

### Documentation

* `bl_classic_mode.md`: "Not yet implemented" section updated (raw OBEX and
  L2CAP now reference design docs), bc-50 and bc-51 added to tracker and
  marked completed, feature tracker updated.
* `todo_tracker.md`: bc-50 and bc-51 marked completed.
* `changelog.md`: this entry.

### Modified files

* `bleep/__init__.py` (version → 2.7.13)
* `bleep/protocols/__init__.py` (new)
* `bleep/protocols/obex_design.md` (new)
* `bleep/protocols/l2cap_design.md` (new)
* `bleep/docs/bl_classic_mode.md`
* `bleep/docs/todo_tracker.md`
* `bleep/docs/changelog.md`

---

## v2.7.12 – Basic Imaging Profile (experimental) (2026-03-03)

### Added

* **Basic Imaging Profile (BIP)** – retrieve image properties, download
  full images, and download thumbnails via the BlueZ **experimental**
  `Image1` interface (session target `"bip-avrcp"`):
  - D-Bus layer: `dbuslayer/obex_bip.py` with `BipSession` context manager
    wrapping `Properties(handle)`, `Get(targetfile, handle, description)`,
    and `GetThumbnail(targetfile, handle)`.
  - Operations layer: `ble_ops/classic_bip.py` with `get_properties()`,
    `get_image()`, `get_thumbnail()`, service detection, and obs-DB
    integration.
  - Debug command: `cbip props|get|thumb <handle> [target_file]`.
  - CLI subparser: `classic-bip <MAC> props|get|thumb <handle> [--output]
    [--timeout]`.
* **Constants:** `OBEX_IMAGE_INTERFACE`, `BIP_UUID`, `BIP_UUID_SHORT`,
  `BIP_RESPONDER_UUID`, `BIP_RESPONDER_UUID_SHORT` added to
  `bt_ref/constants.py`.

### Changed

* `debug.py` module docstring updated to include `cbip`.
* `debug_classic_data.py` module docstring updated.

### Documentation

* `bl_classic_mode.md`: new section 2.12, command reference table updated,
  feature tracker updated (BIP → ✅), "Not yet implemented" section updated
  (SYNC and BIP marked as implemented), bc-47 through bc-49 added and marked
  completed.
* `todo_tracker.md`: bc-47 through bc-49 marked completed.
* `changelog.md`: this entry.

### Modified files

* `bleep/__init__.py` (version → 2.7.12)
* `bleep/bt_ref/constants.py`
* `bleep/dbuslayer/obex_bip.py` (new)
* `bleep/ble_ops/classic_bip.py` (new)
* `bleep/modes/debug_classic_data.py`
* `bleep/modes/debug.py`
* `bleep/cli.py`
* `bleep/docs/bl_classic_mode.md`
* `bleep/docs/todo_tracker.md`
* `bleep/docs/changelog.md`

### Notes

* `Image1` is marked **[experimental]** in BlueZ.  `bluetooth-obexd` must be
  started with `--experimental` for BIP to function.  The API may change or
  be removed without notice.

---

## v2.7.11 – IrMC Synchronization Profile (2026-03-03)

### Added

* **IrMC Synchronization profile** – download or upload an entire phonebook via
  the legacy OBEX Synchronization1 interface (UUID `0x1104`):
  - D-Bus layer: `dbuslayer/obex_sync.py` with `SyncSession` context manager
    wrapping `SetLocation`, `GetPhonebook`, `PutPhonebook` (session target `"sync"`).
  - Operations layer: `ble_ops/classic_sync.py` with `set_location()`,
    `get_phonebook()`, `put_phonebook()`, service detection, and obs-DB
    integration.
  - Debug command: `csync get [target] [--location int|sim1]`,
    `csync put <source> [--location int|sim1]`.
  - CLI subparser: `classic-sync <MAC> get|put [--location] [--timeout]`.
* **Constants:** `OBEX_SYNC_INTERFACE`, `SYNC_UUID`, `SYNC_UUID_SHORT`,
  `SYNC_CMD_UUID`, `SYNC_CMD_UUID_SHORT` added to `bt_ref/constants.py`.

### Changed

* `debug.py` module docstring updated to include `csync`.
* `debug_classic_data.py` module docstring updated.

### Documentation

* `bl_classic_mode.md`: new section 2.11, command reference table updated,
  feature tracker updated (SYNC → ✅), bc-44 through bc-46 added and marked
  completed.
* `todo_tracker.md`: bc-44 through bc-46 marked completed.
* `changelog.md`: this entry.

### Modified files

* `bleep/__init__.py` (version → 2.7.11)
* `bleep/bt_ref/constants.py`
* `bleep/dbuslayer/obex_sync.py` (new)
* `bleep/ble_ops/classic_sync.py` (new)
* `bleep/modes/debug_classic_data.py`
* `bleep/modes/debug.py`
* `bleep/cli.py`
* `bleep/docs/bl_classic_mode.md`
* `bleep/docs/todo_tracker.md`
* `bleep/docs/changelog.md`

---

## v2.7.10 – SPP Serial Port Profile (2026-03-03)

### Added

* **SPP serial port profile** – register a custom Serial Port Profile via BlueZ
  `ProfileManager1.RegisterProfile` on the system bus; incoming RFCOMM
  connections are delivered as Python sockets:
  - D-Bus layer: `dbuslayer/spp_profile.py` with `SppProfile(dbus.service.Object)`
    implementing `Profile1` (`NewConnection` delivers fd, `RequestDisconnection`,
    `Release`) and `SppManager` for lifecycle management (register/unregister).
  - Operations layer: `ble_ops/classic_spp.py` with `register()`, `unregister()`,
    `status()`, `is_registered()`.
  - Debug mode: `cspp` command with sub-commands `register [--channel N] [--name]
    [--role]`, `unregister`, `status`. Incoming connections automatically set
    `state.rfcomm_sock` for use with `csend`/`crecv`/`craw`.
  - CLI: `classic-spp` with actions `register` (blocks until Ctrl+C, prints
    received data), `unregister`, `status`.
  - GLib MainLoop thread for D-Bus service object dispatch.

* **Profile constants** in `bt_ref/constants.py`:
  - `PROFILE_MANAGER_INTERFACE` (`org.bluez.ProfileManager1`)
  - `PROFILE_INTERFACE` (`org.bluez.Profile1`)

### Documentation

* `bl_classic_mode.md` – new section 2.10 (`cspp` / `classic-spp`); updated
  command reference table, "Implemented" list, bc-ID tracker (bc-41 – bc-43),
  feature tracker.
* `todo_tracker.md` – bc-41 through bc-43 marked complete.
* `changelog.md` – this entry.

### Modified files

* `bleep/__init__.py` – version `2.7.9` → `2.7.10`
* `bleep/bt_ref/constants.py` – `PROFILE_MANAGER_INTERFACE`, `PROFILE_INTERFACE`
* `bleep/dbuslayer/spp_profile.py` (new) – `SppProfile`, `SppManager`
* `bleep/ble_ops/classic_spp.py` (new) – operations layer
* `bleep/modes/debug_classic_data.py` – `cmd_cspp`
* `bleep/modes/debug.py` – dispatch + help
* `bleep/cli.py` – `classic-spp` subparser + handler
* `bleep/docs/bl_classic_mode.md`
* `bleep/docs/todo_tracker.md`
* `bleep/docs/changelog.md`

---

## v2.7.9 – PAN Networking (2026-03-03)

### Added

* **Personal Area Networking (PAN)** – client and server support via BlueZ
  `org.bluez.Network1` and `org.bluez.NetworkServer1` on the system bus:
  - D-Bus layer: `dbuslayer/network.py` with `NetworkClient` (per-device:
    `Connect(role)`, `Disconnect()`, properties `Connected`/`Interface`/`UUID`)
    and `NetworkServer` (per-adapter: `Register(role, bridge)`, `Unregister(role)`).
  - Operations layer: `ble_ops/classic_pan.py` with `connect()`, `disconnect()`,
    `status()`, `register_server()`, `unregister_server()`.
  - Debug mode: `cpan` command with sub-commands `connect [role]`, `disconnect`,
    `status`, `server register [role] [bridge]`, `server unregister [role]`.
  - CLI: `classic-pan` with actions `connect`, `disconnect`, `status`, `serve`,
    `unserve`; role choices `nap`/`panu`/`gn`.

* **PAN constants** in `bt_ref/constants.py`:
  - `PAN_PANU_UUID` / `PAN_PANU_UUID_SHORT` (`0x1115`)
  - `PAN_NAP_UUID` / `PAN_NAP_UUID_SHORT` (`0x1116`)
  - `PAN_GN_UUID` / `PAN_GN_UUID_SHORT` (`0x1117`)
  - `NETWORK_INTERFACE` (`org.bluez.Network1`)
  - `NETWORK_SERVER_INTERFACE` (`org.bluez.NetworkServer1`)

### Documentation

* `bl_classic_mode.md` – new section 2.9 (`cpan` / `classic-pan`); updated
  command reference table, "Implemented" list, bc-ID tracker (bc-37 – bc-40),
  feature tracker.
* `todo_tracker.md` – bc-37 through bc-40 marked complete.
* `changelog.md` – this entry.

### Modified files

* `bleep/__init__.py` – version `2.7.8` → `2.7.9`
* `bleep/bt_ref/constants.py` – PAN UUIDs + D-Bus interface constants
* `bleep/dbuslayer/network.py` (new) – `NetworkClient`, `NetworkServer`
* `bleep/ble_ops/classic_pan.py` (new) – operations layer
* `bleep/modes/debug_classic_data.py` – `cmd_cpan`
* `bleep/modes/debug.py` – dispatch + help
* `bleep/cli.py` – `classic-pan` subparser + handler
* `bleep/docs/bl_classic_mode.md`
* `bleep/docs/todo_tracker.md`
* `bleep/docs/changelog.md`

---

## v2.7.8 – MAP Multi-Instance MAS Selection (2026-03-03)

### Added

* **MAP multi-instance MAS selection** – target specific MAS instances on devices
  that expose multiple Message Access Service entries (e.g. separate SMS and email):
  - D-Bus layer: `MapSession.__init__()` gains optional `instance` parameter; the
    RFCOMM channel is passed as `Channel` byte to `CreateSession` (per
    `org.bluez.obex.Client1`).
  - Operations layer: all `classic_map.py` functions (`list_folders`, `list_messages`,
    `get_message`, `push_message`, `update_inbox`, `get_supported_types`,
    `list_filter_fields`, `start_message_monitor`) accept `instance` kwarg.
  - New `list_mas_instances(mac)` function discovers MAP-MSE SDP records and
    returns their RFCOMM channel numbers for instance targeting.
  - Debug mode: `cmap instances` sub-command; all `cmap` sub-commands accept
    `--instance <channel>`.
  - CLI: `classic-map --instance <channel>` flag; `classic-map <MAC> instances`
    action for SDP-based discovery.

### Changed

* Internal helper `_session()` added to `classic_map.py` to reduce boilerplate
  when constructing `MapSession` with optional `instance`.

### Documentation

* `bl_classic_mode.md` – new section 2.7.6 (Multi-Instance MAS Selection);
  updated command reference table, "Implemented" list, bc-ID tracker (bc-36),
  feature tracker.
* `todo_tracker.md` – bc-36 marked complete.
* `changelog.md` – this entry.

### Modified files

* `bleep/__init__.py` – version `2.7.7` → `2.7.8`
* `bleep/dbuslayer/obex_map.py` – `instance` parameter + `Channel` byte
* `bleep/ble_ops/classic_map.py` – `instance` kwarg threaded through all functions;
  `list_mas_instances()` added
* `bleep/modes/debug_classic_data.py` – `--instance` parsing; `instances` sub-cmd
* `bleep/cli.py` – `--instance` flag on `classic-map`; `instances` action
* `bleep/docs/bl_classic_mode.md`
* `bleep/docs/todo_tracker.md`
* `bleep/docs/changelog.md`

---

## v2.7.7 – MAP MNS Notification Monitoring & Metadata Queries (2026-03-03)

### Added

* **MAP MNS notification monitoring** – real-time monitoring of incoming message notifications via D-Bus `PropertiesChanged` signals on `Message1` objects within the MAP session:
  - D-Bus layer: `MapSession.start_notification_watch(callback)` and `stop_notification_watch()` using a background GLib MainLoop thread.
  - Operations layer: `start_message_monitor()` and `stop_message_monitor()` with session lifecycle management.
  - Debug mode: `cmap monitor start|stop` sub-commands.
  - CLI: `classic-map <MAC> monitor` (blocks until Ctrl+C).
  - Graceful teardown on `MapSession.close()`.

* **MAP metadata queries**:
  - `MapSession.get_supported_types()` – reads `SupportedTypes` property from `MessageAccess1` (returns e.g. `EMAIL`, `SMS_GSM`, `SMS_CDMA`, `MMS`, `IM`).
  - `MapSession.list_filter_fields()` – calls `ListFilterFields()` method (returns field names for `ListMessages` filtering).
  - Operations wrappers: `get_supported_types()`, `list_filter_fields()`.
  - Debug mode: `cmap types`, `cmap fields` sub-commands.
  - CLI: `classic-map <MAC> types`, `classic-map <MAC> fields`.

### Changed

* **`obex_map.py`** – added GLib MainLoop imports (with graceful fallback), MNS signal handling, metadata query methods, and auto-cleanup in `close()`.
* **`classic_map.py`** – added `_active_monitors` dict for session lifecycle, new public functions for MNS and metadata.
* **`debug_classic_data.py`** – extended `cmd_cmap` help text and added `types`, `fields`, `monitor` sub-commands.
* **`cli.py`** – added `types`, `fields`, `monitor` sub-parsers to `classic-map`; monitor uses `signal.pause()` for blocking.

### Documentation

* **`bl_classic_mode.md`** – added MNS monitoring and metadata query documentation, updated command reference table, bc-ID tracker (bc-33 through bc-35), feature tracker, and limitations/roadmap.
* **`todo_tracker.md`** – marked bc-33 through bc-35 complete.
* **`changelog.md`** – this entry.

### Files Modified

* `bleep/__init__.py` — version bumped to 2.7.7
* `bleep/dbuslayer/obex_map.py` — MNS watch, metadata queries, GLib integration
* `bleep/ble_ops/classic_map.py` — MNS lifecycle, metadata wrappers
* `bleep/modes/debug_classic_data.py` — `cmap types|fields|monitor` sub-commands
* `bleep/cli.py` — `classic-map types|fields|monitor` sub-parsers and handlers
* `bleep/docs/bl_classic_mode.md` — expanded documentation
* `bleep/docs/todo_tracker.md` — marked Phase 3 items complete
* `bleep/docs/changelog.md` — this entry

---

## v2.7.6 – CLI Sub-Commands for OPP, MAP, and FTP (2026-03-03)

### Added

* **`classic-opp` CLI command** – top-level CLI for Object Push Profile:
  - `classic-opp <MAC> send <file> [--timeout N]` – send a file via OPP.
  - `classic-opp <MAC> pull [--out dest.vcf] [--timeout N]` – pull the default business card.

* **`classic-map` CLI command** – top-level CLI for Message Access Profile:
  - `classic-map <MAC> folders` – list message folders.
  - `classic-map <MAC> list [folder] [--type SMS|MMS]` – list messages with optional type filter.
  - `classic-map <MAC> get <handle> [--out dest.txt]` – download a message.
  - `classic-map <MAC> push <file> [folder]` – push/send a bMessage file.
  - `classic-map <MAC> inbox` – trigger inbox update on remote device.

* **`classic-ftp` CLI command** – top-level CLI for File Transfer Profile:
  - `classic-ftp <MAC> ls [path]` – list remote folder contents.
  - `classic-ftp <MAC> get <remote> [--out dest] [--path folder] [--timeout N]` – download a file.
  - `classic-ftp <MAC> put <file> [--name remote_name] [--path folder] [--timeout N]` – upload a file.
  - `classic-ftp <MAC> mkdir <name> [--path folder]` – create a remote folder.
  - `classic-ftp <MAC> rm <name> [--path folder]` – delete a remote file or folder.

### Changed

* **`MapSession.list_messages()`** (`obex_map.py`) – now accepts optional `filters` dict (passed to D-Bus `ListMessages` as filter properties).
* **`classic_map.list_messages()`** (`classic_map.py`) – now accepts optional `filters` kwarg for type filtering.

### Documentation

* **`bl_classic_mode.md`** – added CLI command entries to reference table, updated bc-ID tracker (bc-30 through bc-32), feature tracker, and limitations/roadmap.
* **`todo_tracker.md`** – marked bc-30 through bc-32 complete.
* **`changelog.md`** – this entry.

### Files Modified

* `bleep/__init__.py` — version bumped to 2.7.6
* `bleep/cli.py` — added `classic-opp`, `classic-map`, `classic-ftp` subparsers and execution handlers
* `bleep/dbuslayer/obex_map.py` — `list_messages()` gains `filters` parameter
* `bleep/ble_ops/classic_map.py` — `list_messages()` gains `filters` kwarg pass-through
* `bleep/docs/bl_classic_mode.md` — expanded documentation
* `bleep/docs/todo_tracker.md` — marked Phase 2 items complete
* `bleep/docs/changelog.md` — this entry

---

## v2.7.5 – OBEX File Transfer Profile & Transfer Poller Deduplication (2026-03-03)

### Added

* **File Transfer Profile (`cftp`)** (debug mode) – browse and transfer files on remote Classic devices via OBEX FTP (UUID `0x1106`, `org.bluez.obex.FileTransfer1`):
  - D-Bus layer: `bleep/dbuslayer/obex_ftp.py` with `FtpSession` context manager wrapping `FileTransfer1`.
  - Operations layer: `bleep/ble_ops/classic_ftp.py` with logging, service detection, and obs-DB hooks.
  - `cftp` debug command with sub-commands: `ls`, `cd`, `get`, `put`, `mkdir`, `rm`, `cp`, `mv`.
  - Constants: `FTP_UUID`, `FTP_UUID_SHORT`; `OBEX_PROFILE_UUIDS` updated.

* **Shared OBEX transfer poller** (`bleep/dbuslayer/_obex_common.py`) – extracted duplicated `_poll_transfer()` logic from `obex_opp.py`, `obex_map.py`, and `obex_pbap.py` into a single `poll_obex_transfer()` function. Also provides `cancel_obex_transfer()` and `unwrap_dbus()` utilities.

* **OBEX expansion roadmap** documented in `todo_tracker.md` – nine-phase plan (v2.7.5 – v2.7.13+) covering FTP, CLI wiring, MAP MNS, MAP multi-instance, PAN, SPP, SYNC, BIP, and raw OBEX/L2CAP.

### Changed

* **`obex_opp.py`** – replaced inline `_poll_transfer()` with shared `poll_obex_transfer()` from `_obex_common.py`. Removed unused `time` import.
* **`obex_map.py`** – replaced inline `_poll_transfer()` and `_unwrap()` with shared functions from `_obex_common.py`. Removed unused `time` import.
* **`obex_pbap.py`** – replaced inline transfer polling loop with shared `poll_obex_transfer()`. Removed unused `time`, `OBEX_TRANSFER_INTERFACE`, and `DBUS_PROPERTIES` imports.

### Documentation

* **`bl_classic_mode.md`** – added section 2.8 (`cftp` commands), updated command reference table, limitations/roadmap, bc-ID tracker (bc-26 through bc-29), and feature tracker.
* **`todo_tracker.md`** – added OBEX Expansion Roadmap section with nine phases and bc-26 through bc-51 entries.
* **`changelog.md`** – this entry.

### Files Added

* `bleep/dbuslayer/_obex_common.py` — shared OBEX transfer polling, cancel, and D-Bus type unwrapping
* `bleep/dbuslayer/obex_ftp.py` — FTP D-Bus layer (`FtpSession` class)
* `bleep/ble_ops/classic_ftp.py` — FTP operations layer

### Files Modified

* `bleep/__init__.py` — version bumped to 2.7.5
* `bleep/bt_ref/constants.py` — added `FTP_UUID`, `FTP_UUID_SHORT`; updated `OBEX_PROFILE_UUIDS`
* `bleep/dbuslayer/obex_opp.py` — refactored to use shared poller
* `bleep/dbuslayer/obex_map.py` — refactored to use shared poller and unwrap
* `bleep/dbuslayer/obex_pbap.py` — refactored to use shared poller
* `bleep/modes/debug_classic_data.py` — added `cmd_cftp` function
* `bleep/modes/debug.py` — updated imports, dispatch table, help text for `cftp`
* `bleep/docs/bl_classic_mode.md` — expanded documentation
* `bleep/docs/todo_tracker.md` — OBEX expansion roadmap
* `bleep/docs/changelog.md` — this entry

---

## v2.7.4 – Classic Channel Data Exchange Expansion (2026-03-03)

### Added

* **RFCOMM data-exchange commands** (debug mode) – new `copen`, `csend`, `crecv`, `craw` commands provide full send/receive capability over Classic RFCOMM channels:
  - `copen` opens a dedicated data socket (separate from the keep-alive socket) by channel number, service name, or first available.
  - `csend` sends data with format support (`hex:`, `str:`, `file:`, `uint8:`, etc.) matching the BLE `write` format vocabulary.
  - `crecv` receives data with configurable timeout, buffer size, hex dump display, and save-to-file.
  - `craw` starts an interactive bidirectional RFCOMM session with a background reader thread.

* **Object Push Profile (`copp`)** (debug mode) – send files or pull business cards via OPP (UUID `0x1105`):
  - D-Bus layer: `bleep/dbuslayer/obex_opp.py` wrapping `org.bluez.obex.ObjectPush1`.
  - Operations layer: `bleep/ble_ops/classic_opp.py` with logging and service detection.
  - `copp send <file>` and `copp pull [dest.vcf]` debug commands.

* **Message Access Profile (`cmap`)** (debug mode) – browse and manage SMS/MMS via MAP (UUIDs `0x1132`/`0x1134`):
  - D-Bus layer: `bleep/dbuslayer/obex_map.py` with `MapSession` class wrapping `org.bluez.obex.MessageAccess1` and `org.bluez.obex.Message1`.
  - Operations layer: `bleep/ble_ops/classic_map.py` with logging and service detection.
  - `cmap` debug command with sub-commands: `folders`, `list`, `get`, `push`, `inbox`, `props`, `read`, `delete`.

* **Shared value-parsing utility** (`bleep/modes/debug_utils.py`) – extracted from `debug_gatt.py` to avoid duplication. Both BLE `write` and Classic `csend` now share `parse_value()`. Also provides `hexdump()` and `VALUE_FORMAT_HELP`.

* **`rfcomm_sock` field** on `DebugState` – dedicated data-exchange socket independent of `keepalive_sock`.

### Changed

* **`cmd_write` in `debug_gatt.py`** refactored to use shared `parse_value()` from `debug_utils.py` instead of inline parsing logic. Behaviour unchanged.

* **`debug_classic.py`** module header expanded; now imports `select`, `threading`, and shared utilities. Internal `_resolve_rfcomm_channel()` and `_ensure_classic_connected()` helpers extracted for reuse across `copen`, `ckeep`, and `craw`.

### Documentation

* **`bl_classic_mode.md`** – added sections 2.7 (RFCOMM Data Exchange), 2.8 (OPP), 2.9 (MAP). Updated command reference table, limitations/roadmap (now documents 10 future expansion items), and feature tracker.
* **`todo_tracker.md`** – added tracking entries bc-20 through bc-25.
* **`changelog.md`** – this entry.

### Future Expansion (documented, not implemented)

* OBEX FTP (`org.bluez.obex.FileTransfer1`)
* SYNC profile (`org.bluez.obex.Synchronization1`)
* MAP MNS push notifications
* MAP multi-instance MAS support
* BIP (Basic Imaging Profile)
* Raw OBEX over RFCOMM (bypassing obexd)
* L2CAP raw channel access
* CLI sub-commands for OPP/MAP (`classic-opp`, `classic-map`)
* SPP serial port emulation via `ProfileManager1.RegisterProfile`
* PAN networking via `org.bluez.Network1`

### Files Added

* `bleep/modes/debug_utils.py` — shared `parse_value()`, `hexdump()`, `VALUE_FORMAT_HELP`
* `bleep/modes/debug_classic_data.py` — RFCOMM data-exchange + OBEX commands (split from `debug_classic.py`)
* `bleep/dbuslayer/obex_opp.py` — OPP D-Bus layer
* `bleep/dbuslayer/obex_map.py` — MAP D-Bus layer (`MapSession` class)
* `bleep/ble_ops/classic_opp.py` — OPP operations layer
* `bleep/ble_ops/classic_map.py` — MAP operations layer

### Files Modified

* `bleep/__init__.py` — version bumped to 2.7.4
* `bleep/modes/debug_state.py` — added `rfcomm_sock` field
* `bleep/modes/debug_classic.py` — trimmed; data-exchange commands moved to `debug_classic_data.py`
* `bleep/modes/debug_gatt.py` — refactored `cmd_write` to use shared parser
* `bleep/modes/debug.py` — updated imports (two classic modules), dispatch table, help text
* `bleep/docs/bl_classic_mode.md` — expanded documentation
* `bleep/docs/todo_tracker.md` — new tracking entries
* `bleep/docs/changelog.md` — this entry

---

## v2.7.3 – Classic Enumeration Robustness Fix (2026-03-02)

### Fixed

* **`classic-enum` PBAP gate removed** (`classic_sdp.py`): `discover_services_sdp()` no longer requires PBAP (UUID 0x112f) to be present among parsed SDP records. Previously, devices without a PBAP service caused `sdptool failed: PBAP not in browse output` even when valid SDP records with RFCOMM channels were successfully parsed and logged. The function now accepts any parsed records that contain at least one RFCOMM channel.

* **`classic-enum` always displays SDP records** (`cli.py`): The `classic-enum` CLI command now prints a formatted SDP record table (Name, UUID, RFCOMM Channel, Service Record Handle, Profile Descriptors, etc.) immediately after discovery succeeds, regardless of whether the subsequent connection attempt succeeds or fails. Previously, SDP records were only visible in `--debug` mode and the primary output was a JSON service map that required a full connection.

* **Graceful connection failure handling** (`cli.py`): When `classic-enum` obtains SDP records but the connection-based enumeration fails (e.g. `br-connection-create-socket`), the command now reports success (exit 0) with a warning instead of failing with exit 1. The user retains all SDP enumeration data.

### Files Modified

* `bleep/ble_ops/classic_sdp.py` — Removed PBAP-specific gating logic from `discover_services_sdp()`
* `bleep/cli.py` — Restructured `classic-enum` output to always display SDP records; improved connection failure fallback
* `bleep/__init__.py` — Version bumped to 2.7.3
* `bleep/docs/changelog.md` — This entry
* `bleep/docs/todo_tracker.md` — New tracking section
* `bleep/docs/bl_classic_mode.md` — Updated output examples

---

## v2.7.2 – Debug Mode Modular Refactor (2026-03-01)

### Changed

* **Debug mode modular architecture**: Refactored the monolithic `debug.py` (3864 lines) into nine focused submodules plus a slim core shell (~270 lines). No behavioral changes — all commands, prompts, and output remain identical.

* **`DebugState` dataclass** (`debug_state.py`): Replaces 16 module-level global variables with a single, explicit container that is passed to every command handler. Fields: `current_device`, `current_mapping`, `current_mode`, `keepalive_sock`, `current_path`, `monitoring`, `monitor_thread`, `monitor_stop_event`, `notification_handlers`, `detailed_view`, `path_history`, `db_save_enabled`, `path_cache`, `glib_loop`, `glib_thread`, `current_mine_map`, `current_perm_map`, `db_available`, `obs`.

* **GLib MainLoop management** (`debug_state.py`): `ensure_glib_mainloop()` and `stop_glib_mainloop()` now operate on the `DebugState` instance instead of module globals.

* **D-Bus helpers & navigation** (`debug_dbus.py`): `format_dbus_error()`, `print_detailed_dbus_error()`, path resolution, `ls`/`cd`/`pwd`/`back`, introspection commands (`interfaces`, `props`, `methods`, `signals`, `call`, `monitor`, `introspect`).

* **Connect / disconnect / info** (`debug_connect.py`): Transport detection, `find_device_path()`, `cmd_connect()`, `cmd_disconnect()`, `cmd_info()` with Classic and BLE branches.

* **GATT operations** (`debug_gatt.py`): `cmd_services()`, `cmd_chars()`, `cmd_char()`, `cmd_read()`, `cmd_write()`, `cmd_notify()`, `cmd_detailed()`, `show_properties()`, `get_handle_from_dict()`, and the comprehensive `debugging_notification_callback` (now a factory function bound to state).

* **Classic BT commands** (`debug_classic.py`): `cmd_cscan()`, `cmd_cconnect()`, `cmd_cservices()`, `cmd_ckeep()`, `cmd_csdp()`, `cmd_pbap()`.

* **Pairing & agent commands** (`debug_pairing.py`): `cmd_agent()`, `cmd_pair()`, single and brute-force pair flows, post-pair connect helpers.

* **Scan & enumeration** (`debug_scan.py`): `cmd_scan()`/`scann`/`scanp`/`scanb`, `cmd_enum()`/`enumn`/`enump`/`enumb`, `_enum_common()`.

* **AOI & database commands** (`debug_aoi.py`): `cmd_aoi()`, `cmd_dbsave()`, `cmd_dbexport()`.

* **Multi-read & brute-write** (`debug_multiread.py`): Updated to accept `DebugState` instead of individual state parameters. Function signatures simplified from 7 positional parameters to `(args, state)`.

* **Core shell** (`debug.py`): Now contains only imports, `_cmd_help()`, the `_build_dispatch_table()` factory (binds state to all handlers via closures), `debug_shell()`, `parse_args()`, and `main()`.

---

## v2.7.1 – Pair-Connect-Explore + Lockout-Aware Brute-Force (2026-03-01)

### Added

* **Operational pair mode** (default): After successful pairing, the `pair` command now auto-detects the device transport (BR/EDR vs BLE) and establishes a persistent connection, returning the user to the debug shell for immediate exploration with `info`, `interfaces`, `props`, `cservices`, etc.

* **`--test` flag** for `pair`: Preserves the original PoC behavior (pair + auto-disconnect monitor) for diagnostic use.

* **Transport-aware `connect` command**: The `connect` command now auto-detects whether the target is a BR/EDR classic or BLE device and routes to the appropriate connection method. For classic devices, falls back to SDP enumeration + RFCOMM keepalive if profile-level `Connect()` fails.  *(Note: debug-mode `connect` was later reverted to BLE-only — see Unreleased; use `cconnect` for Classic.)*

* **Enhanced `info` command**: Works with paired-but-disconnected devices when only a D-Bus path is available. Displays address, name, paired/trusted/connected status, device class, RSSI, and advertised UUIDs directly from D-Bus properties.

* **Transport detection** via `_get_device_transport()`: Inspects `AddressType`, `ServicesResolved`, and UUID prefixes from `org.bluez.Device1` properties to classify devices as `br-edr`, `le`, or `dual`.

* **Post-pair classic connect flow** (`_post_pair_connect_classic()`): SDP enumeration via `sdptool`, RFCOMM keepalive socket on the first available channel, and session state setup — all without requiring BlueZ profile-level `Connect()`.

* **Post-pair BLE connect flow** (`_post_pair_connect_le()`): Standard GATT connect + service enumeration with fallback to D-Bus path exploration.

* **Lockout-aware brute-force**: `PinBruteForcer` now distinguishes `AuthenticationFailed` (wrong PIN — device tested it) from `AuthenticationRejected` (device refusing to test — lockout active). When a lockout transition is detected, the brute forcer pauses for a configurable cooldown period and retries the rejected candidate, preventing correct PINs from being skipped during a lockout window.

* **`--lockout-cooldown` flag** for `pair --brute`: Configures the pause duration (seconds) when device lockout is detected (default: 60).

* **`--max-lockout-retries` flag** for `pair --brute`: Limits consecutive lockout-retry cycles per candidate before aborting (default: 3).

* **`PairingAgent.last_pair_error`**: Exposes the D-Bus error name from the most recent `pair_device()` failure, enabling callers to classify errors precisely.

* **`BruteForceResult.lockout_pauses`**: Tracks the number of lockout cooldown pauses during a brute-force run.

### Changed

* **`pair` command**: Default behavior now connects and returns to shell instead of entering the blocking auto-disconnect monitor. The monitor is available via `--test`.

* **`connect` command**: Refactored from BLE-only to transport-aware. Extracted `_connect_le()` and `_connect_classic()` helpers. Classic path tries full `connect_and_enumerate__bluetooth__classic()` first, then falls back to `_post_pair_connect_classic()`.

* **`disconnect` command**: Now cleans up keepalive sockets, resets `_current_path`, and resets `_current_mode` in addition to clearing the device wrapper.

* **`_cmd_pair_single()`**: Accepts `test_mode` parameter to select between operational (default) and PoC test behavior.

* **`PinBruteForcer` error classification**: Replaced the single `_REJECTION_ERRORS` set with distinct `_WRONG_PIN_ERRORS`, `_LOCKOUT_ERRORS`, `_RETRY_ERRORS`, and `_BLOCKING_ERRORS` categories. The brute-force loop now reads `agent.last_pair_error` after each attempt and dispatches accordingly — wrong PIN advances to the next candidate, lockout triggers cooldown + retry of the same candidate, blocking errors abort after 5 consecutive occurrences.

* **Brute-force summary**: Now reports lockout pause count in the final summary line.

### Files Modified

* `bleep/dbuslayer/pin_brute.py` — Lockout-aware error classification, cooldown/retry logic, `_handle_failure()`, `_interruptible_sleep()`, updated `_print_summary()`
* `bleep/dbuslayer/agent.py` — `last_pair_error` attribute on `PairingAgent`, set in `pair_device()` on D-Bus and non-D-Bus failures
* `bleep/modes/debug.py` — `_cmd_pair`: added `--lockout-cooldown` and `--max-lockout-retries` args; `_cmd_pair_brute`: passes new params to `PinBruteForcer`; plus all prior v2.7.1 changes
* `bleep/docs/debug_mode.md` — Updated pair/connect documentation
* `bleep/docs/pairing_agent.md` — Updated status, added lockout-aware brute-force features
* `bleep/docs/changelog.md` — This entry
* `bleep/docs/todo_tracker.md` — Updated with lockout-aware implementation items
* `bleep/__init__.py` — Version bump to 2.7.1

---

## v2.7.0 – Pairing Agent Expansion: Three Modes, Brute-Force, Passkey Support (2026-03-01)

### Added

* **Three pairing modes** in the debug `pair` command:
  * **Hardcoded** (default): `pair MAC --pin CODE` / `pair MAC --passkey CODE` — returns a fixed PIN or passkey on every `RequestPinCode` / `RequestPasskey` callback.
  * **Interactive**: `pair MAC --interactive` — prompts the user for PIN/passkey within the debug shell terminal using `CliIOHandler`.
  * **Brute-force**: `pair MAC --brute` — iterates candidate PINs or passkeys through repeated pair/remove/re-pair cycles until the correct value is found.

* **`BruteForceIOHandler`** (`agent_io.py`): New I/O handler that consumes values from an iterator, returning the next candidate on each `request_pin_code()` or `request_passkey()` call.

* **`PinBruteForcer`** (`pin_brute.py`): Orchestrator for brute-force pairing. Manages the attempt loop, handles stale bond removal, device re-discovery, rate limiting (`--delay`), attempt capping (`--max-attempts`), and device-blocking detection.

* **Iterator generators** (`pin_brute.py`): `pin_range()`, `passkey_range()`, `pins_from_file()` for generating candidate search spaces.

* **Passkey support**: `--passkey` flag for hardcoded LE passkeys (uint32, 0-999999), `--passkey-brute` for passkey brute-force.

* **Dictionary attack**: `--pin-list FILE` reads candidate PINs from a text file (one per line, `#` comments supported).

* **Enhanced `agent status`**: Now shows configured default PIN/passkey and recent method invocation timestamps.

* **MainLoop architecture document** (`mainloop_architecture.md`): Design document for future MainLoop inversion — Option A (worker thread for `input()`) vs Option B (`GLib.io_add_watch` on stdin). Recommends Option A. Includes full compatibility matrix across all BLEEP modes.

### Refactored

* **`_cmd_pair`** (`debug.py`): Extracted shared helpers `_find_device_path()`, `_remove_stale_bond()`, `_resolve_device_for_pair()`, `_register_pair_agent()`, `_post_pair_monitor()` to eliminate duplication between single-shot and brute-force modes.

### Files
| File | Action | Detail |
|------|--------|--------|
| `bleep/dbuslayer/agent_io.py` | Modified | Added `BruteForceIOHandler` class; updated `create_io_handler()` factory with `"bruteforce"` type |
| `bleep/dbuslayer/pin_brute.py` | **New** | `PinBruteForcer`, `BruteForceResult`, `pin_range()`, `passkey_range()`, `pins_from_file()` |
| `bleep/modes/debug.py` | Modified | Expanded `_cmd_pair` to three modes; extracted shared pairing helpers; enhanced `agent status` |
| `bleep/docs/mainloop_architecture.md` | **New** | MainLoop inversion design document |
| `bleep/docs/pairing_agent.md` | Modified | Added three-mode documentation, `BruteForceIOHandler`, updated status/limitations/future work |
| `bleep/docs/debug_mode.md` | Modified | Updated `pair` command reference with all modes and options |
| `bleep/docs/changelog.md` | Modified | This entry |
| `bleep/docs/todo_tracker.md` | Modified | Tracked planning and implementation of pairing agent expansion |

---

## v2.6.2 – Successful Pairing: Message Filter Fix + Device Discovery Fix + Bond Storage Fix (2026-02-28)

### Fixed — Pairing Now Works End-to-End

* **CONFIRMED**: BLEEP successfully pairs with target `D8:3A:DD:0B:69:B9` using PIN `12345`.  `RequestPinCode` handler fires, `AutoAcceptIOHandler` returns the PIN, BlueZ accepts the pairing, and the device is set as trusted.

* **Message filter blocking handler dispatch** (Phase 4) — `enable_unified_dbus_monitoring()` installed a `bus.add_message_filter()` that prevented `dbus-python` from dispatching incoming method calls to `dbus.service.Object` handlers.  Diagnostic PoC tests (`poc_pair_diag.py`) proved:
  * `sudo` is NOT required — non-root agent handler dispatch works correctly
  * `eavesdrop='true'` match rules fail with `AccessDenied` for non-root users — they were never active in BLEEP, ruling them out
  * The generic message filter was the sole remaining cause
  * **Fix (agent.py)**: Disabled `enable_unified_dbus_monitoring(True)` during agent registration; only `register_agent()` is called for correlation tracking

* **Fabricated device path causing `UnknownObject` error** (Phase 5) — When the target device was not in BlueZ's object tree (e.g. after `RemoveDevice`), `_cmd_pair()` constructed a fake D-Bus path from the MAC address.  BlueZ returned `UnknownObject: Method "Pair"... doesn't exist` because no `Device1` interface existed at that path.
  * **Root cause**: BLEEP used `adapter.get_discovered_devices()` (internal cache) instead of BlueZ's `GetManagedObjects()` API.  When the device wasn't cached, a path was fabricated — a pattern the BlueZ reference `bluezutils.find_device()` explicitly avoids.
  * **Fix (debug.py)**: Replaced cache lookup + path fabrication with `GetManagedObjects()` query (matching `bluezutils.find_device()` pattern).  Added `Transport: "auto"` filter and 15s discovery scan for both BLE and classic devices.  Clear error on discovery failure instead of phantom path.

* **`Bond info must include device address` post-pairing error** — `PairingStateMachine.start_pairing()` initialized `_pairing_data` without an `"address"` key.  When `_on_pairing_complete` → `save_device_bond()` ran, it raised `ValueError`.
  * **Fix (pairing_state.py)**: Extract MAC address from `device_path` (e.g. `/org/bluez/hci0/dev_D8_3A_DD_0B_69_B9` → `D8:3A:DD:0B:69:B9`) and include it in `_pairing_data` at pairing start.

* **`Invalid transition: COMPLETE -> FAILED` state machine crash** — When the bond storage `ValueError` propagated through `handle_pairing_success()`, the exception handler in `pair_device()` called `handle_pairing_failed()` while the state machine was already in the `COMPLETE` terminal state.  `COMPLETE → FAILED` is not a valid transition.
  * **Fix (agent.py)**: Added `_safe_transition_failed()` guard that checks the current state before attempting the FAILED transition.  If the state machine is already in a terminal state (COMPLETE, FAILED, or CANCELLED), the transition is skipped.

### Files
| File | Action | Detail |
|------|--------|--------|
| `bleep/dbuslayer/agent.py` | Modified | Disabled `enable_unified_dbus_monitoring()` during agent registration; added `_safe_transition_failed()` guard |
| `bleep/modes/debug.py` | Modified | `_cmd_pair()`: replaced cache lookup + path fabrication with `GetManagedObjects()` query; added `Transport: "auto"` 15s scan; clear error on discovery failure; proper re-discovery after bond removal |
| `bleep/dbuslayer/pairing_state.py` | Modified | `start_pairing()`: extract and include MAC `address` in `_pairing_data` |
| `bleep/docs/agent_dbus_communication_issue.md` | Modified | Phase 4 + Phase 5 resolution; final RESOLVED status |
| `bleep/docs/mainloop_requirement_analysis.md` | Modified | Added message filter interference discovery; confirmed evidence table |
| `bleep/docs/debug_mode.md` | Modified | Updated `pair` command docs with discovery scan details |
| `bleep/docs/agent_pairing_flow_analysis.md` | Rewritten | Full update: confirmed working, capabilities table, limitations, future work |
| `bleep/docs/pairing_agent.md` | Modified | Added current status, limitations, future work, integration notes |
| `bleep/docs/changelog.md` | Modified | This entry |
| `bleep/docs/todo_tracker.md` | Modified | Updated pairing fix tracking with Phases 4–6, future work items |

---

## v2.6.1 – Fix Agent Method Dispatch in Debug Mode Pairing (2026-02-28)

### Fixed
* **`RequestPinCode` handler never invoked during debug-mode pairing** — `dbus-python`'s `dbus.service.Object` method dispatch requires `GLib.MainLoop().run()`.  `GLib.MainContext.iteration(False)` triggers message filters but does **not** dispatch object-path handlers, so agent methods silently never fire.
  * **Root cause confirmed** via baseline test: BlueZ's `simple-agent` (uses `mainloop.run()`) successfully pairs with target `D8:3A:DD:0B:69:B9` using PIN `12345`.
  * **PoC validated**: Standalone script using temporary `GLib.MainLoop` with `GLib.timeout_add` for controlled quitting successfully pairs and dispatches `RequestPinCode`.
  * **Fix (debug.py)**: `_cmd_pair()` stops the background GLib loop before pairing and restarts it after, so `pair_device()` takes the non-background path.
  * **Fix (agent.py)**: `pair_device()`'s non-background path replaced `context.iteration(False)` loop with a temporary `GLib.MainLoop` + `GLib.timeout_add(100, poll)` pattern — the only mechanism that reliably dispatches `dbus.service.Object` method handlers.

### Files
| File | Action | Detail |
|------|--------|--------|
| `bleep/dbuslayer/agent.py` | Modified | `pair_device()` non-bg path: temporary `GLib.MainLoop` replaces `context.iteration(False)` |
| `bleep/modes/debug.py` | Modified | `_cmd_pair()`: stop bg loop before pairing, restart after |
| `bleep/docs/agent_dbus_communication_issue.md` | Modified | Phase 2 + Phase 3 resolution with PoC evidence |
| `bleep/docs/mainloop_requirement_analysis.md` | Modified | Added `context.iteration()` vs `MainLoop.run()` discovery |
| `bleep/docs/debug_mode.md` | Modified | Added `pair` command documentation with usage examples |
| `bleep/docs/changelog.md` | Modified | This entry |
| `bleep/docs/todo_tracker.md` | Modified | Added pairing fix tracking section |

---

## v2.6.0 – Amusica: Bluetooth Audio Target Discovery & Manipulation (2026-02-28)

### Added
* **Amusica orchestration module** (`bleep/ble_ops/amusica.py` — NEW ~240 lines) – Composable primitives for the full Amusica workflow:
  * `scan_audio_targets()` — UUID-filtered scan that identifies devices advertising audio service UUIDs (A2DP, HFP, HSP, AVRCP)
  * `attempt_justworks_connect()` — Connect-only (no pair) attempt that classifies targets as JustWorks-accessible vs authentication-required
  * `assess_targets()` — Pipeline that connects to each scanned target and runs audio recon on accessible ones
  * `summarise_assessment()` — Produces a structured report of vulnerable targets with audio interfaces

* **Amusica CLI mode** (`bleep/modes/amusica.py` — NEW ~290 lines) – Full CLI interface under `bleep amusica`:
  * **`amusica scan`** — Scan for audio-capable devices, optionally attempt JustWorks connections and recon (`--connect`, `--test-file`, `--out`)
  * **`amusica halt`** — Halt all audio on a connected target (pause + volume zero + profile off)
  * **`amusica control`** — Media playback control (play/pause/stop/next/previous/volume/info) via existing AVRCP layer
  * **`amusica inject`** — Play audio file into target device's audio sink (auto-detects sink or explicit `--sink`)
  * **`amusica record`** — Record audio from target device (auto-detects source or explicit `--source`)
  * **`amusica status`** — Show current audio state: card, profiles, sources, sinks, playback info

* **Audio halt capability** — `AudioToolsHelper.halt_audio_for_device()` in `bleep/ble_ops/audio_tools.py`:
  * Multi-step disruption: AVRCP pause → transport volume to 0 → card profile to "off"
  * Returns structured result dict with per-step success/failure and error details

* **Audio service UUID constants** — `AUDIO_SERVICE_UUIDS` frozenset and AVRCP UUIDs in `bleep/bt_ref/constants.py`:
  * `AVRCP_TARGET_UUID`, `AVRCP_CONTROLLER_UUID`
  * `AUDIO_SERVICE_UUIDS` — aggregate set of A2DP, HFP, HSP, and AVRCP UUIDs for scan filtering

* **CLI registration** — `bleep amusica` subparser with `REMAINDER` args in `bleep/cli.py` (+7 lines)

* **Mode registration** — `amusica` added to `bleep/modes/__init__.py`

### Design Decisions
* **Compose, don't duplicate** — Amusica reuses existing BLEEP primitives (scan, classic_connect, audio_recon, audio_tools, media control) rather than reimplementing any capability
* **Connect-only, no pair** — JustWorks assessment uses `device.connect()` without `device.pair()` to minimize user interaction and avoid authentication prompts
* **CLI-centric** — Primary interface is CLI subcommands; no TUI in initial release
* **Recordings default to /tmp** — Per requirement for space usage concerns
* **Multi-backend inherited** — All audio operations go through `AudioToolsHelper`, automatically supporting PulseAudio, PipeWire (native and PA-compat), BlueALSA, and raw ALSA

### Files
| File | Action | Lines |
|------|--------|-------|
| `bleep/ble_ops/amusica.py` | New | ~240 |
| `bleep/modes/amusica.py` | New | ~290 |
| `bleep/ble_ops/audio_tools.py` | Modified | +60 |
| `bleep/bt_ref/constants.py` | Modified | +15 |
| `bleep/cli.py` | Modified | +10 |
| `bleep/modes/__init__.py` | Modified | +2 |
| `bleep/docs/changelog.md` | Modified | entry added |
| `bleep/docs/todo_tracker.md` | Modified | Amusica section added |
| `bleep/docs/audio_recon.md` | Modified | cross-reference + future work detail |

---

## v2.5.3 – Adapter Configuration & Bluetooth Configurability (2026-02-28)

### Added
* **Adapter Configuration CLI** – New `bleep adapter-config` command for viewing and modifying local adapter properties:
  * **`adapter-config show`**: Displays all adapter D-Bus properties, lists writable properties by tier (D-Bus vs mgmt), and shows active boot defaults from `/etc/bluetooth/main.conf`
  * **`adapter-config get <property>`**: Reads a single adapter property (alias, name, class, powered, discoverable, etc.)
  * **`adapter-config set <property> <value>`**: Sets a writable property, automatically routing to D-Bus or `bluetoothctl mgmt.*` based on property type
  * **Files Added**: `bleep/modes/adapter_config.py` (NEW — ~325 lines)
  * **Files Modified**: `bleep/cli.py` (+18 lines — subparser + dispatch)

* **D-Bus Adapter Property Accessors** – Comprehensive getter/setter methods on `system_dbus__bluez_adapter`:
  * **Getters**: `get_adapter_info()`, `get_alias()`, `get_name()`, `get_address()`, `get_address_type()`, `get_class()`, `get_powered()`, `get_discoverable()`, `get_pairable()`, `get_connectable()`, `get_discoverable_timeout()`, `get_pairable_timeout()`, `get_discovering()`, `get_uuids()`, `get_modalias()`, `get_roles()`
  * **Setters**: `set_alias()`, `set_powered()`, `set_discoverable()`, `set_pairable()`, `set_connectable()`, `set_discoverable_timeout()`, `set_pairable_timeout()`
  * **DRY helpers**: `_get_property()` and `_set_property()` base methods eliminate repetition
  * **Files Modified**: `bleep/dbuslayer/adapter.py` (+~130 lines)

* **bluetoothctl Management Socket Integration** – Kernel-level adapter configuration for properties not reachable via D-Bus:
  * **Subprocess wrapper**: `_run_bluetoothctl_mgmt()` feeds commands via stdin to a single `bluetoothctl` session, supporting multi-command sequences (e.g. `mgmt.select` then `mgmt.class`)
  * **Setters**: `set_class()`, `set_local_name()`, `set_ssp()`, `set_secure_connections()`, `set_le()`, `set_bredr()`, `set_privacy()`, `set_fast_connectable()`, `set_link_security()`, `set_wideband_speech()`
  * **Adapter selection**: `_mgmt_cmd()` auto-prepends `mgmt.select <index>` for non-default adapters
  * **Files Modified**: `bleep/dbuslayer/adapter.py` (+~120 lines)

* **Boot Defaults Reader** – `read_main_conf()` in `adapter_config.py` parses `/etc/bluetooth/main.conf` for informational display (read-only; no writes)

* **Documentation**: New `bleep/docs/adapter_config.md` with CLI reference, full property tables (D-Bus + mgmt), common Class of Device values, Python API examples, and architecture notes

### Design Decisions
* **Tiered tool strategy**: D-Bus native for writable properties (no subprocess overhead), `bluetoothctl mgmt.*` only for kernel-management-only properties (Class, SSP, SC, transport toggles)
* **No `hciconfig` for new features**: Deprecated by BlueZ; existing usage in `recovery.py` preserved but new operations use `bluetoothctl mgmt.*`
* **No writes to `main.conf`**: Too invasive (requires root + daemon restart); runtime-only changes via D-Bus and mgmt
* **Alias vs Name vs local-name**: `Name` is the system hostname (read-only on D-Bus, set via `hostnamectl`). `Alias` (D-Bus writable) overrides `Name` for what remote devices see and is **persisted** across daemon restarts. `mgmt.name` also updates the `Alias` property (via `current_alias` in the daemon), but this is a **temporary** alias that does not persist across daemon restarts — it only lasts for the lifetime of the `bluetoothd` process (see `adapter.c:local_name_changed_callback`, lines 924-948). For persistent name changes, D-Bus `Alias` is the correct method.

---

## v2.5.2 – BlueALSA & PipeWire Native Tool Support (2026-02-28)

### Added
* **BlueALSA Integration** – Full support for BlueZ ALSA backend:
  * **Preflight checks**: `bluealsa-aplay`, `bluealsa-cli`, `bluealsa-rfcomm` added to `bleep/core/preflight.py`
  * **Backend detection**: `AudioToolsHelper.is_bluealsa_running()` detects BlueALSA daemon via `bluealsa-cli list-pcms`
  * **PCM enumeration**: `AudioToolsHelper.list_bluealsa_pcms()` parses `bluealsa-cli list-pcms` output to enumerate Bluetooth ALSA PCM devices with MAC address, profile (A2DP/SCO), direction (sink/source), and ALSA device string
  * **Play/Record**: `play_to_bluealsa_pcm()` and `record_from_bluealsa_pcm()` use `aplay -D` / `arecord -D` with BlueALSA ALSA device identifiers
  * **Recon integration**: `_recon_bluealsa()` helper in `audio_recon.py` enumerates BlueALSA PCMs, optionally plays test files and records from each PCM with sox analysis; runs as supplement alongside PA/PW when BlueALSA is detected
  * **Result structure**: New `bluealsa_pcms` list in recon result for BlueALSA-specific entries
  * **Files Modified**: `bleep/core/preflight.py`, `bleep/ble_ops/audio_tools.py`, `bleep/ble_ops/audio_recon.py`

* **PipeWire Native Tool Support** – Direct PipeWire integration without PulseAudio compatibility layer:
  * **Preflight checks**: `pw-dump`, `pw-play`, `pw-record`, `wpctl` added to `bleep/core/preflight.py`
  * **Backend differentiation**: `get_audio_backend()` now returns `"pipewire_native"` when PipeWire is running but PulseAudio compatibility is absent; `"pipewire"` when PA compat is available
  * **Node enumeration**: `_get_pipewire_bluez_nodes()` parses `pw-dump` JSON output to enumerate Bluetooth audio nodes with node ID, name, MAC address, media class, state, and available profiles
  * **Profile switching**: `_set_pipewire_profile()` uses `wpctl set-profile` to switch profiles on PipeWire nodes
  * **Sources/sinks**: `_get_pipewire_sources_and_sinks()` extracts Bluetooth sources and sinks from PipeWire node data with role mapping
  * **Play/Record**: `play_to_sink()` and `record_from_source()` now use `pw-play --target=<id>` / `pw-record --target=<id>` when backend is `pipewire_native`
  * **Recon integration**: `_recon_pipewire_native()` helper in `audio_recon.py` enumerates PipeWire Bluetooth nodes, groups by MAC, enumerates sources/sinks, and performs optional play/record with sox analysis
  * **Files Modified**: `bleep/core/preflight.py`, `bleep/ble_ops/audio_tools.py`, `bleep/ble_ops/audio_recon.py`

### Changed
* **Backend detection**: `get_audio_backend()` now returns five possible values: `"pulseaudio"`, `"pipewire"` (PA compat), `"pipewire_native"` (no PA compat), `"bluealsa"` (sole backend), or `"none"`
* **Recon architecture**: `run_audio_recon()` refactored from monolithic function to dispatch to three backend-specific helpers (`_recon_pulseaudio`, `_recon_pipewire_native`, `_recon_bluealsa`), reducing complexity and enabling independent backend evolution
* **Play/Record tool selection**: `play_to_sink()` and `record_from_source()` now automatically select the correct tool based on detected backend (paplay/parecord for PA/PipeWire-compat, pw-play/pw-record for PipeWire native, aplay/arecord for ALSA fallback)
* **Documentation**: `bleep/docs/audio_recon.md` updated with BlueALSA prerequisites, PipeWire native prerequisites, updated backend table, and updated result structure

---

## v2.5.1 – Audio Recon Augmentation (2026-02-28)

### Added
* **Audio Recon** – Incorporate capabilities from AudioRecon.sh into BLEEP with modular structure:
  * **Sox-based analysis** (`bleep/ble_ops/audio_tools.py`):
    - **`check_audio_file_has_content(audio_file_path, sox_path)`**: Module-level helper using sox `stat` to determine if a recording has non-zero amplitude (has audio).
    - **`AudioToolsHelper.check_audio_file_has_content()`**: Instance method delegating to the above with optional sox path.
  * **Per-profile enumeration** (`bleep/ble_ops/audio_tools.py`):
    - **`get_bluez_cards()`**: List PulseAudio cards that are BlueZ (Bluetooth) via `pactl list cards short`.
    - **`get_profiles_for_card(card_index)`**: List profile names for a card from `pactl list cards`.
    - **`set_card_profile(card_index, profile_name)`**: Set active profile via `pactl set-card-profile`.
    - **`get_sources_and_sinks_for_card_profile(card_index)`**: Parse `pacmd list-cards` card block for `sources:` and `sinks:` with human-readable roles (microphone, headset_stream, speaker, interest) based on observed ALSA source/sink naming conventions.
  * **Play and record via backend** (`bleep/ble_ops/audio_tools.py`):
    - **`play_to_sink(sink_id, file_path, duration_sec)`**: Play file to a sink using paplay (PulseAudio/PipeWire) or aplay (ALSA).
    - **`record_from_source(source_id, output_path, duration_sec)`**: Record from a source using parecord or arecord.
  * **Recon runner** (`bleep/ble_ops/audio_recon.py`):
    - **`run_audio_recon(...)`**: Orchestrates backend detection, BlueZ card enumeration, per-profile sources/sinks, optional play of test file to sinks, optional record from each interface to `/tmp` (or `record_dir`), and sox analysis on each recording. Returns structured dict and optionally writes JSON to `output_json_path`.
  * **CLI and mode**:
    - **`bleep audio-recon`**: New CLI command with `--device`, `--test-file`, `--no-play`, `--no-record`, `--out`, `--record-dir`, `--duration`.
    - **`bleep audio recon`** (modes/audio.py): Recon subcommand with same options.
  * **Preflight** (`bleep/core/preflight.py`): Added **sox**, **paplay**, and **pacmd** to `_check_audio_tools()`.
  * **Documentation**: New **`bleep/docs/audio_recon.md`** with usage, result structure, and detailed **Future work** for Bonus Objectives (stream redirection, consolidate streams, play into streams, reconfig I/O).
  * **Tracking**: Recon result is a structured dict (and optional JSON file) for visibility; no observation DB schema change in this release.

### Changed
* **Preflight**: Audio tools list now includes `sox`, `paplay`, and `pacmd` for audio recon and playback/analysis.

---

## v2.5.0 – Re-modularization, UUID Enhancement & Code Quality Improvements (2026-01-19)

### Added
* **Audio Capabilities Expansion** – Comprehensive Bluetooth audio profile identification, playback, and recording:
  * **Enhanced ALSA Enumeration** (`bleep/ble_ops/audio_tools.py`):
    - **ALSA Device Listing**: Added `list_alsa_devices()` method using `aplay -l` and `arecord -l` subprocess calls to enumerate ALSA hardware devices directly
    - **ALSA Device Information**: Added `get_alsa_device_info()` method using `aplay -D <device> --dump-hw-params` to retrieve detailed hardware parameters
    - **MAC Address Extraction**: Added `extract_mac_from_alsa_device()` method for parsing MAC addresses from ALSA/PulseAudio/PipeWire device names via string pattern matching
    - **Profile Identification**: Added `identify_bluetooth_profiles_from_alsa()` method that correlates device naming patterns with Bluetooth profile UUIDs (A2DP, HFP, HSP)
    - **External Tools Only**: All methods use external tools (pactl, pw-cli, aplay, arecord) with no D-Bus interaction, maintaining strict separation of concerns
    - **Files Modified**: `bleep/ble_ops/audio_tools.py` (+~200 lines)
  * **Profile Correlation Helper** (`bleep/ble_ops/audio_profile_correlator.py`):
    - **New Module**: Created `AudioProfileCorrelator` class (~200 lines) to bridge external tool output with D-Bus information
    - **Profile Identification**: `identify_profiles_for_device()` combines ALSA/PulseAudio enumeration with BlueZ MediaTransport discovery
    - **Transport Discovery**: `get_transport_for_profile()` and `get_all_transports_for_device()` methods for finding MediaTransport objects via D-Bus
    - **D-Bus Integration**: Uses existing `find_media_devices()` and `MediaTransport` classes from `dbuslayer/media.py`
    - **Files Added**: `bleep/ble_ops/audio_profile_correlator.py` (NEW)
  * **Audio Codec Support** (`bleep/ble_ops/audio_codec.py`):
    - **New Module**: Created `AudioCodecEncoder` and `AudioCodecDecoder` classes (~450 lines) for GStreamer-based audio processing
    - **GStreamer Integration**: Uses GStreamer Python bindings (preferred) or `gst-launch-1.0` subprocess (fallback) for encoding/decoding
    - **Codec Support**: Implements SBC, MP3, and AAC codec pipelines (ATRAC, AptX, LC3 defined but not yet implemented)
    - **Encoding**: `encode_file_to_transport()` method encodes audio files (MP3, WAV, FLAC) and writes to MediaTransport file descriptors
    - **Decoding**: `decode_audio_stream()` method decodes audio streams from transport FDs and writes to files
    - **Pipeline Patterns**: GStreamer pipeline construction patterns derived from BlueZ example scripts (simple-asha)
    - **Main Loop Integration**: Uses GLib.MainLoop for proper GStreamer event handling (reference: simple-asha)
    - **No D-Bus Interaction**: Module handles codec operations only, maintaining separation from D-Bus layer
    - **Files Added**: `bleep/ble_ops/audio_codec.py` (NEW)
  * **Audio Streaming Manager** (`bleep/dbuslayer/media_stream.py`):
    - **New Module**: Created `MediaStreamManager` class (~250 lines) for high-level audio streaming orchestration
    - **Transport Management**: `acquire_transport()` and `release_transport()` methods using existing `MediaTransport.acquire()` and `MediaTransport.release()`
    - **Audio Playback**: `play_audio_file()` method orchestrates transport acquisition, volume setting (via D-Bus), audio encoding (delegates to audio_codec.py), and transport release
    - **Audio Recording**: `record_audio()` method orchestrates transport acquisition, audio decoding (delegates to audio_codec.py), and transport release
    - **Codec Information**: `get_codec_info()` and `get_transport_info()` methods for retrieving transport state and codec details
    - **Volume Control**: `set_volume()` method using existing `MediaTransport.set_volume()` D-Bus interface
    - **D-Bus Focus**: Module handles D-Bus interactions and delegates codec operations to audio_codec.py
    - **Files Added**: `bleep/dbuslayer/media_stream.py` (NEW)
  * **CLI Integration**:
    - **New Commands**: Added `audio-profiles`, `audio-play`, and `audio-record` commands to `bleep/cli.py`
    - **Audio Mode Module**: Created `bleep/modes/audio.py` (~200 lines) following existing mode patterns
    - **Profile Listing**: `list_audio_profiles()` function for displaying Bluetooth audio profiles via ALSA correlation
    - **Playback Interface**: `play_audio_file()` function for playing audio files to Bluetooth devices
    - **Recording Interface**: `record_audio()` function for recording audio from Bluetooth devices
    - **Files Added**: `bleep/modes/audio.py` (NEW)
    - **Files Modified**: `bleep/cli.py` (+~50 lines)
  * **Dependency Management**:
    - **GStreamer Support**: Updated `setup.py` to track GStreamer Python bindings (via PyGObject) as optional dependency
    - **Preflight Checks**: Enhanced `bleep/core/preflight.py` to check for `aplay`, `arecord`, `gst-launch-1.0`, and GStreamer Python bindings
    - **Graceful Degradation**: All modules handle missing GStreamer/ALSA tools gracefully
    - **Files Modified**: `setup.py` (+~5 lines), `bleep/core/preflight.py` (+~15 lines)
  * **Architecture Compliance**:
    - **Separation of Concerns**: Maintained strict separation between external tools (`audio_tools.py`) and D-Bus interactions (`dbuslayer/`)
    - **Code Reuse**: Leveraged existing constants, classes, and infrastructure throughout
    - **No Duplication**: Reused existing `MediaTransport`, `find_media_devices()`, and other D-Bus infrastructure
  * **Status**: Fully implemented - provides comprehensive Bluetooth audio capabilities with proper architectural separation

* **UUID and Codec Constants Centralization** – Single source of truth for audio-related constants:
  * **Centralized Constants**: Extended `bleep/bt_ref/constants.py` with comprehensive audio profile UUIDs and codec constants
  * **Audio Profile UUIDs**: Added A2DP_SOURCE_UUID, A2DP_SINK_UUID, HFP_HANDS_FREE_UUID, HFP_AUDIO_GATEWAY_UUID, HSP_AUDIO_GATEWAY_UUID, HSP_HEADSET_UUID
  * **Audio Codec Constants**: Added SBC_CODEC_ID, MP3_CODEC_ID, AAC_CODEC_ID, ATRAC_CODEC_ID, APTX_CODEC_ID, APTX_HD_CODEC_ID, LC3_CODEC_ID, VENDOR_SPECIFIC_CODEC_ID
  * **Helper Functions**: Added `get_codec_name(codec_id)` and `get_profile_name(profile_uuid)` utility functions
  * **Profile Name Mapping**: Added AUDIO_PROFILE_NAMES dictionary mapping UUIDs to human-readable names
  * **Codec Name Mapping**: Added CODEC_NAMES dictionary mapping codec IDs to names
  * **Module Updates**: Updated 6 modules to use centralized constants:
    - `bleep/dbuslayer/media_register.py` - Removed duplicate A2DP UUIDs and SBC_CODEC, uses imported constants directly
    - `bleep/dbuslayer/media_stream.py` - Removed duplicate A2DP UUIDs, uses imported constants directly
    - `bleep/ble_ops/audio_codec.py` - Removed duplicate codec constants and CODEC_NAMES, uses imported constants directly
    - `bleep/ble_ops/audio_profile_correlator.py` - Removed duplicate PROFILE_UUID_MAP and CODEC_NAMES, uses imported constants directly
    - `bleep/ble_ops/audio_tools.py` - Removed local profile_uuid_map, uses imported constants directly
    - `bleep/dbuslayer/device_classic.py` - Replaced hardcoded UUIDs with imported constants
  * **Code Quality**: Eliminated redundant self-assignments (e.g., `A2DP_SOURCE_UUID = A2DP_SOURCE_UUID`) - all modules now use imported constants directly
  * **Backward Compatibility**: Added aliases (SBC_CODEC = SBC_CODEC_ID) in audio_codec.py for existing code that may reference old constant names
  * **Documentation**: Added comprehensive comments referencing A2DP Specification and BlueZ documentation
  * **Files Modified**: `bleep/bt_ref/constants.py` (+80 lines), 6 audio-related modules
  * **Status**: Fully implemented - eliminates hardcoded values and provides single source of truth
* **Preflight Checks Consolidation** – Comprehensive environment capability checking system:
  * **New Module**: Created `bleep/core/preflight.py` (~100 lines) to consolidate scattered tool availability checks
  * **Bluetooth Tool Checks**: Verifies presence of `hciconfig`, `hcitool`, `bluetoothctl`, `btmgmt`, `sdptool`, `l2ping`
  * **Audio Tool Checks**: Verifies presence of PulseAudio tools (`pactl`, `parecord`) and PipeWire tools (`pw-cli`, `pw-record`)
  * **System Configuration**: Detects `/etc/bluetooth` configuration files and BlueZ version
  * **Python Dependencies**: Checks `dbus` and `gi` (GObject Introspection) versions
  * **CLI Integration**: Added `--check-env` flag to run preflight checks and display user-friendly capability report
  * **Singleton Pattern**: Prevents repeated checks during single session
  * **Files Added**: `bleep/core/preflight.py` (NEW)
  * **Files Modified**: `bleep/cli.py` (added `--check-env` flag)
  * **Status**: Fully implemented - provides comprehensive environment capability reporting
* **Audio Tools Helper** – Wrapper for ALSA/PipeWire/PulseAudio operations:
  * **New Module**: Created `bleep/ble_ops/audio_tools.py` (~100 lines) with `AudioToolsHelper` class
  * **Backend Detection**: `get_audio_backend()` identifies active audio backend ('pipewire', 'pulseaudio', 'none')
  * **Audio Device Listing**: `list_audio_sinks()` and `list_audio_sources()` provide audio device information
  * **Bluetooth Audio Detection**: `is_bluetooth_audio_available()` checks for Bluetooth audio device availability
  * **Graceful Degradation**: Handles missing audio tools gracefully without errors
  * **Future Integration**: Designed for future A2DP sink/source integration
  * **Files Added**: `bleep/ble_ops/audio_tools.py` (NEW)
  * **Status**: Fully implemented - ready for A2DP integration
* **Enumeration Controller** – Orchestration layer for multi-attempt device enumeration:
  * **New Module**: Created `bleep/ble_ops/enum_controller.py` (~150 lines) with `EnumerationController` class
  * **Structured Results**: `EnumerationResult` dataclass provides success status, data, annotations, error summaries, and attempt count
  * **Error Handling**: `ErrorAction` enum categorizes errors (RECONNECT, ANNOTATE_AND_CONTINUE, GIVE_UP)
  * **Existing Component Integration**: Leverages existing `ReconnectionMonitor`, `ConnectionResetManager`, and landmine mapping functionality
  * **Maximum Attempts**: Enforces 3-attempt limit with structured error annotation collection
  * **CLI Integration**: Added `--controlled` flag to `enum-scan` command for controlled enumeration mode
  * **AoI Mode Integration**: Updated Assets of Interest (AoI) mode to use `EnumerationController` for target device iteration
  * **Files Added**: `bleep/ble_ops/enum_controller.py` (NEW)
  * **Files Modified**: `bleep/ble_ops/scan.py` (optional EnumerationController integration), `bleep/modes/aoi.py` (EnumerationController usage), `bleep/cli.py` (added `--controlled` flag)
  * **Status**: Fully implemented - provides structured multi-attempt enumeration with error tracking
  * **Note**: `--controlled` flag is a proof-of-concept; future refactoring will make EnumerationController the default (see "Changed" section)
* **Agent Method Verification** – D-Bus introspection-based agent registration verification:
  * **Method Verification**: Added `_verify_method_registration()` method to `BlueZAgent` class that uses D-Bus introspection to verify all required agent methods are registered
  * **Required Methods Check**: Verifies presence of `Release`, `AuthorizeService`, `RequestPinCode`, `RequestPasskey`, `DisplayPasskey`, `DisplayPinCode`, `RequestConfirmation`, `RequestAuthorization`, `Cancel`
  * **Structured Logging**: Logs verification results with structured context, including missing methods if any
  * **Automatic Verification**: Verification is automatically called after successful agent registration
  * **Non-Blocking**: Verification failures log warnings but do not prevent agent registration
  * **Files Modified**: `bleep/dbuslayer/agent.py` (added verification method), `bleep/modes/agent.py` (added verification call)
  * **Status**: Fully implemented - provides diagnostic visibility into agent method registration
* **Classic Bluetooth UUID Enhancement for Device Type Classification** – Enhanced device type classification with Service Discovery Server detection:
  * **Service Discovery Server Detection**: Added `_is_service_discovery_server()` helper method to `ClassicServiceUUIDsCollector` that detects Service Discovery Server (0x1000) UUID in both 16-bit and 128-bit formats
  * **CONCLUSIVE Weight Assignment**: Service Discovery Server (0x1000) now receives `EvidenceWeight.CONCLUSIVE` when detected, as it is the most indicative UUID for Bluetooth Classic (BR/EDR) devices
  * **Classification Logic Updates**: Updated `_classify_classic()` and `_classify_dual()` to recognize CONCLUSIVE Classic service UUID evidence, and enhanced `_generate_reasoning()` to mention "Service Discovery Server detected" when present
  * **UUID Format Handling**: Leverages existing `identify_uuid()` function to handle all UUID formats (16-bit, 32-bit, 128-bit, with/without dashes, with/without 0x prefix)
  * **Files Modified**: `bleep/analysis/device_type_classifier.py` (added helper method, enhanced collector, updated classification logic)
  * **Status**: Fully implemented and verified - Service Discovery Server detection works correctly for all UUID formats
* **ESP SSP UUID Support** – Added custom ESP SSP (0xABF0) UUID to persistent custom UUID storage:
  * **Custom UUID Storage**: ESP SSP UUID added to `constants.UUID_NAMES` dictionary in `bleep/bt_ref/constants.py` for persistence across UUID database regenerations
  * **UUID Translator Integration**: ESP SSP is automatically available via `UUIDDatabase` custom UUID category and can be found by UUID translation functionality
  * **Files Modified**: `bleep/bt_ref/constants.py` (added ESP SSP to `UUID_NAMES` dictionary)
  * **Status**: Fully implemented - ESP SSP UUID persists in custom UUID storage and is accessible via UUID translator
* **Service Discovery Server UUID Constant** – Added constant reference for Service Discovery Server 16-bit UUID:
  * **Constant Definition**: Added `SERVICE_DISCOVERY_SERVER_UUID_16 = "1000"` to `bleep/bt_ref/constants.py` in "# Common Service/Characteristic UUIDs" section
  * **Function Reference Update**: Updated `_is_service_discovery_server()` to reference `SERVICE_DISCOVERY_SERVER_UUID_16` constant instead of hardcoded `"1000"` string
  * **Maintainability**: Eliminates magic string, improves code maintainability, and follows BLEEP's pattern of centralizing constants
  * **Files Modified**: `bleep/bt_ref/constants.py` (added constant), `bleep/analysis/device_type_classifier.py` (updated function to use constant)
  * **Status**: Fully implemented - constant reference replaces hardcoded value

### Changed
* **Connection State Guards** – Prevented redundant connection attempts:
  * **LE Device Connection Guard**: Enhanced `bleep/dbuslayer/device_le.py` `connect()` method to check `_connection_state` before attempting connection
  * **Classic Device Connection Guard**: Enhanced `bleep/dbuslayer/device_classic.py` `connect()` method with similar connection state guard
  * **Early Return**: If device is already connected (verified via D-Bus `Connected` property), method logs warning and returns early with success
  * **Thread Safety**: Uses existing `_connection_state_lock` to ensure thread-safe state checking
  * **Impact**: Eliminates repeated connection attempts when device is already connected, addressing fickle BR/EDR connectivity issues
  * **Files Modified**: `bleep/dbuslayer/device_le.py` (~15 lines), `bleep/dbuslayer/device_classic.py` (~10 lines)
  * **Status**: Fully implemented - redundant connection attempts prevented
* **Device Type Classification Weight System** – Enhanced evidence weighting for Classic device identification:
  * **Service Discovery Server**: Now receives `EvidenceWeight.CONCLUSIVE` (most indicative of Classic devices)
  * **Other Classic UUIDs**: Continue to receive `EvidenceWeight.STRONG` (existing behavior maintained)
  * **Dual-Mode Detection**: Updated to recognize CONCLUSIVE Classic service UUID evidence as conclusive Classic evidence
  * **Files Modified**: `bleep/analysis/device_type_classifier.py` (weight assignment logic, classification methods)
* **Enumeration Retry Logic** – Introduced structured multi-attempt enumeration (proof-of-concept):
  * **New Approach**: `EnumerationController` provides orchestrated 3-attempt enumeration with error categorization
  * **Backward Compatibility**: Default enumeration behavior unchanged; `--controlled` flag enables new approach
  * **Future Direction**: `--controlled` flag is temporary; future refactoring will make `EnumerationController` the default and only method (see "Known Issues" section)
  * **Files Modified**: `bleep/ble_ops/scan.py`, `bleep/modes/aoi.py`, `bleep/cli.py`

### Fixed
* **Repeated Connection Attempts** – Fixed issue where BLEEP repeatedly attempted connections to already-connected devices:
  * **Root Cause**: Connection methods did not check existing connection state before attempting new connections
  * **Solution**: Added connection state guards in both LE and Classic device `connect()` methods that verify connection state and D-Bus `Connected` property before attempting connection
  * **Impact**: Eliminates unnecessary connection attempts, reduces log noise, and addresses fickle BR/EDR connectivity issues
  * **Files Modified**: `bleep/dbuslayer/device_le.py`, `bleep/dbuslayer/device_classic.py`
* **ESP SSP UUID Persistence** – Fixed potential loss of ESP SSP UUID during UUID database regeneration:
  * **Root Cause**: ESP SSP (0xABF0) was initially added to auto-generated `bleep/bt_ref/uuids.py` file, which would be overwritten during regeneration
  * **Solution**: Moved ESP SSP UUID to persistent `constants.UUID_NAMES` dictionary in `bleep/bt_ref/constants.py`, which is not auto-generated
  * **Impact**: ESP SSP UUID now persists across UUID database regenerations and remains accessible via UUID translator
  * **Files Modified**: `bleep/bt_ref/uuids.py` (removed ESP SSP from auto-generated file), `bleep/bt_ref/constants.py` (added ESP SSP to custom UUID storage)

### Known Issues / Future Work
* **Enumeration Retry Logic Duplication** – The `--controlled` flag creates a dual-path for enumeration:
  * **Issue**: Current implementation adds optional `--controlled` flag that creates separate code path for multi-attempt enumeration, leading to code duplication and maintenance burden
  * **Impact**: Users must know about and use `--controlled` flag; default behavior differs from controlled behavior
  * **Required Solution**: Future refactoring must make `EnumerationController` the default and only method for enumeration, removing the `--controlled` flag and eliminating duplicate retry logic
  * **Priority**: High (for production readiness)
  * **Status**: Deferred until v2.5.0 is stable; current implementation serves as proof-of-concept
  * **Action Items**: Remove `--controlled` flag, make `EnumerationController` default in `_base_enum()` and all enum variants, refactor `connect_and_enumerate__bluetooth__low_energy()` to use `EnumerationController` internally, remove duplicate retry logic from other modules

## v2.4.7 – Agent D-Bus Method Registration Fix (2026-01-09)

### Fixed
* **Agent D-Bus Method Registration** – Critical fix for agent functionality:
  * **Root Cause**: Agent methods were not being registered on D-Bus because the mainloop object (`GLib.MainLoop()`) was created **after** agent registration instead of **before**. This prevented `dbus.service.Object.__init__()` from properly registering methods during object initialization.
  * **Solution**: Modified `bleep/modes/agent.py` to create the mainloop object **before** agent creation and registration, matching the pattern used in all working BlueZ reference scripts (`simple-agent`, `test-profile`, `simple-obex-agent`).
  * **Impact**: Agent methods are now properly registered on D-Bus, enabling:
    - D-Bus introspection returns non-empty XML with registered methods
    - BlueZ METHOD CALLs are properly routed to Python agent methods
    - IO Handler is engaged during pairing operations
    - PIN code requests and other agent methods are successfully handled
  * **Evidence**: Analysis of BlueZ reference scripts revealed that ALL working implementations create the mainloop object before agent registration, not after.
  * **Files Modified**: `bleep/modes/agent.py` (moved `GLib.MainLoop()` creation to before agent creation, added explanatory comments)
  * **Documentation**: Updated `bleep/docs/agent_dbus_communication_issue.md` to reflect issue resolution, added `bleep/docs/bluez_reference_analysis_refined.md` with detailed comparison analysis
  * **Status**: Fix implemented and ready for testing. Verification should show non-empty introspection XML and successful method invocations.

## v2.4.6 – Comprehensive D-Bus Monitoring, Agent Diagnostics, SDP Storage & Error Visibility (2025-12-30)

### Added
* **Real-World Usage Scenarios Documentation** – Comprehensive practical examples for observation database:
  * **Long-term device monitoring workflows**: Continuous device presence monitoring, behavior analysis over time, and automated daily device inventory reports
  * **Enterprise device tracking patterns**: Corporate asset tracking system, multi-location device correlation, and asset status reporting
  * **Security assessment workflows**: Automated security audit system, threat detection and alerting, and vulnerable characteristic identification
  * **Integration examples**: SIEM system integration (Splunk, ELK, Graylog), REST API for database access, and database backup/synchronization
  * **Complete code examples**: All scenarios include full, working Python code examples that can be adapted to specific use cases
  * **Files Added**: `bleep/docs/observation_db_usage_scenarios.md` (comprehensive usage guide with 10 detailed scenarios)
  * **Files Modified**: `bleep/docs/observation_db.md` (added reference to usage scenarios), `bleep/docs/README.md` (added link to usage scenarios), `bleep/docs/todo_tracker.md` (marked real-world usage scenarios as complete)
* **SDP Record Storage (Schema v7)** – Full SDP record snapshot storage:
  * **New `sdp_records` table**: Stores complete SDP record snapshots with all attributes (Service Record Handle, Profile Descriptor List, Service Version, Service Description, Protocol Descriptors, raw record)
  * **Automatic storage**: SDP records are automatically stored when discovered via `discover_services_sdp()`, `discover_services_sdp_connectionless()`, or D-Bus `GetServiceRecords()` method
  * **Database integration**: `get_device_detail()` and `export_device_data()` now include SDP records in their output
  * **Backward compatibility**: `classic_services` table (basic UUID/channel mapping) continues to exist alongside `sdp_records` for different use cases
  * **Schema migration**: Automatic migration from v6 to v7 creates the new table and indexes
  * **Files Modified**: `bleep/core/observations.py` (added `sdp_records` table, `upsert_sdp_record()` function, migration v6→v7, updated query functions), `bleep/ble_ops/classic_sdp.py` (added `_store_sdp_records()` helper, integrated storage into discovery functions), `bleep/docs/observation_db.md`, `bleep/docs/observation_db_schema.md` (documentation updates)
* **Agent + AgentManager Verbosity / Diagnosability Enhancements** – Comprehensive error visibility improvements:
  * **Agent Error Handling**: Enhanced `_setup_agent_manager()` and `register()` methods in `bleep/dbuslayer/agent.py` to use consistent `name: message` error format with full context (agent_path, capabilities, default)
  * **Device Connect/Pair Error Context**: Improved error logging in `device_classic.py` and `device_le.py` to include method name, device path, adapter name, and full D-Bus error details
  * **IO Handler Context Logging**: Enhanced all IO handlers (`CliIOHandler`, `ProgrammaticIOHandler`, `AutoAcceptIOHandler`) to log handler type, auto_accept status, and default values when prompting/auto-accepting (no secrets logged)
  * **Debug Mode Agent Commands**: Enhanced `agent status` command to show comprehensive agent details (class, path, registered status, capabilities, default_requested, auto_accept, io_handler type)
  * **Error Clarity Expansion**: Updated `media_services.py`, `media_browse.py`, `obex_pbap.py`, and `manager.py` to use consistent `name: message` error format instead of `str(e)`, preserving full D-Bus error context
  * **Error Message Preservation**: Verified and enhanced `bleep/core/errors.py` to preserve D-Bus message payloads for all agent-relevant exceptions (NotPermitted, NotAuthorized, Failed, InProgress, UnknownObject)
  * **Files Modified**: `bleep/dbuslayer/agent.py` (added `_format_dbus_error` helper, enhanced error logging), `bleep/dbuslayer/device_classic.py` (enhanced connect/pair error logging), `bleep/dbuslayer/device_le.py` (enhanced connect/pair error logging), `bleep/dbuslayer/agent_io.py` (enhanced handler context logging), `bleep/modes/agent.py` (enhanced agent registration logging), `bleep/modes/debug.py` (enhanced agent status command), `bleep/dbuslayer/media_services.py`, `bleep/dbuslayer/media_browse.py`, `bleep/dbuslayer/obex_pbap.py`, `bleep/dbuslayer/manager.py` (consistent error formatting)
* **Agent Method Entry Point Logging** – Comprehensive visibility into D-Bus method invocations:
  * All agent methods now log when called by BlueZ: `RequestPinCode`, `DisplayPinCode`, `RequestPasskey`, `DisplayPasskey`, `RequestConfirmation`, `RequestAuthorization`, `AuthorizeService`, `Release`, `Cancel`
  * Logs include device path, agent path, and registration status for complete diagnostic context
  * Enables verification that BLEEP's agent is actually being used by BlueZ during pairing
  * Logs written to `LOG__AGENT` (`/tmp/bti__logging__agent.txt` or `~/.bleep/logs/agent.log`)
* **Agent Registration Status Logging** – Enhanced registration diagnostics:
  * Detailed logging during agent registration including path, capabilities, and default agent request status
  * Logs registration success/failure with full D-Bus error context
  * Logs `RequestDefaultAgent` calls and any failures (non-fatal)
  * Provides complete registration lifecycle visibility
* **Agent Status Command** – New diagnostic tool for agent verification:
  * `bleep agent --status` command to check if BLEEP agent is registered and active
  * Displays agent class, path, and registration status
  * Provides guidance on agent usage and log file locations
  * Exit code indicates registration status (0 = registered, 1 = not registered)
* **Unified D-Bus Event Aggregator** – Comprehensive D-Bus communication visibility (Complete & Verified):
  * **Unified Event Capture**: New `DBusEventCapture` dataclass replaces separate `SignalCapture` and `MethodCallCapture` structures
  * **Event Aggregator**: New `DBusEventAggregator` class provides centralized storage and correlation for all D-Bus event types
  * **Complete Coverage**: Captures signals, method calls, method returns, and errors in a single unified system
  * **General Catch-All Watcher**: Monitors all BlueZ/Agent/AgentManager communications on the system (not limited to BLEEP's agent)
  * **Human-Readable + Detailed Logging**: Follows error handling pattern (`name: msg`) with summary line + detailed line preserving full D-Bus message context
  * **Event Correlation**: Correlates method calls with their returns/errors via serial numbers, and events by path relationships
  * **Query API**: `get_recent_events()`, `correlate_event()`, `get_method_call_chain()` for accessing aggregated events
  * **Special Highlighting**: PIN code requests, authentication errors, and agent registration events are specially highlighted
  * **Original Message Preservation**: All original D-Bus messages preserved in `DBusEventCapture.original_message` for detailed analysis
  * **Automatic Enablement**: Automatically enabled when agent is registered via `enable_unified_dbus_monitoring()`
  * **Graceful Degradation**: Handles permission issues gracefully (eavesdropping may require root/D-Bus policy changes)
  * **Backward Compatibility**: Existing `enable_agent_method_call_monitoring()` delegates to unified system; old methods retained but deprecated
  * **Comprehensive Test Suite**: Created complete test coverage with 80+ test cases covering all functionality
  * **Integration Testing**: Real D-Bus interaction tests with BlueZ operations
  * **Verification**: Tested against `dbus-monitor` for accuracy validation
  * **D-Bus Message Type Constants Fix**: Fixed AttributeError by defining message type constants in `bleep/core/constants.py` and using them instead of non-existent `dbus.lowlevel.Message.*` attributes
  * **Enhanced Error Logging**: Error handler now transparently shows exception type and message (e.g., `AttributeError: type object 'dbus.lowlevel.Message' has no attribute 'SIGNAL'`) for better debugging
  * **Files Modified**: `bleep/dbuslayer/signals.py` (added `DBusEventCapture`, `DBusEventAggregator`, unified monitoring, fixed message type constants), `bleep/dbuslayer/agent.py` (updated to use unified monitoring), `bleep/core/constants.py` (added D-Bus message type constants)
  * **Test Files Added**: `tests/test_unified_dbus_event_aggregator.py`, `tests/test_unified_dbus_integration.py`, `tests/test_unified_dbus_graceful_degradation.py`
  * **Status**: Fully implemented, tested, and verified working in production use
* **Debug Mode – `ckeep` command** – Classic Bluetooth keep-alive functionality (Partially Complete):
  * Opens an RFCOMM socket to keep a Classic (BR/EDR) ACL alive after `cconnect`.
  * Channel selection: `--first`, `--svc <name|uuid>`, or explicit numeric channel.
  * `ckeep --close` closes the socket and allows BlueZ to drop the link.
  * Auto-closes socket on `quit` command.
  * Enhanced error handling preserves BlueZ D-Bus error details (e.g., `org.bluez.Error.Failed: br-connection-unknown`) for better diagnostics.
  * All error paths now use `name: message` format following BLEEP error handling patterns.
  * **Status**: Error handling and logging are functional. Full functionality testing and validation is blocked by Classic device connection issues. Requires a Bluetooth Classic target device with no pairing/PIN requirements to properly validate RFCOMM socket operations and ACL keep-alive functionality. Further work pending appropriate test hardware.
* **RSSI Capture Enhancement for Scan Operations** – Comprehensive RSSI value capture during device discovery:
  * **Three-tier RSSI capture system**: Primary source from `GetManagedObjects()`, secondary from PropertiesChanged signal cache during discovery, and fallback via `Properties.Get()` for connected devices only
  * **Signal-based RSSI capture**: Enhanced `PropertiesChanged` handler in `system_dbus__bluez_signals` to detect and cache RSSI updates during active discovery
  * **DeviceManager RSSI cache**: Thread-safe RSSI cache in `system_dbus__bluez_device_manager` that stores RSSI values captured from D-Bus signals during discovery
  * **RSSI merge in get_discovered_devices()**: Enhanced `get_discovered_devices()` to merge RSSI from multiple sources, with MAC address normalization for consistent cache lookups
  * **Connected device fallback**: Properties.Get() fallback only queries RSSI for connected devices (disconnected devices show "? dBm" as expected behavior)
  * **Cache timing optimization**: RSSI cache persists after discovery completes to allow `get_discovered_devices()` to access cached values
  * **Backward compatibility**: Existing scan functionality unchanged; RSSI values now appear correctly in scan results
  * **Files Modified**: `bleep/dbuslayer/manager.py` (added RSSI cache, discovery tracking, signal forwarding), `bleep/dbuslayer/signals.py` (enhanced PropertiesChanged handler for RSSI capture), `bleep/dbuslayer/adapter.py` (enhanced get_discovered_devices() with RSSI merge and fallback)
  * **Status**: Fully implemented and verified working in production - RSSI values now appear correctly in scan results
* **PIN Code Request Visibility and Diagnostic Enhancements** – Comprehensive diagnostic capabilities for PIN code pairing failures:
  * **Phase 1: Communication Type Logging Fix** – Fixed D-Bus communication type labeling to correctly identify METHOD CALL, METHOD RETURN, ERROR, and SIGNAL messages. Added validation in `_on_dbus_message()` to ensure message types match captured event types, with debug logging for troubleshooting.
  * **Phase 2: Agent Method Invocation Detection** – Added method invocation tracking in `BlueZAgent` class to correlate captured D-Bus method calls with actual agent method invocations. Added capability validation warnings when agent capability doesn't support requested method (e.g., DisplayOnly cannot provide PIN codes).
  * **Phase 3: Enhanced Event Correlation** – Implemented automatic RequestPinCode → Cancel correlation with time deltas, device connection state correlation with PIN code requests, and timeout detection for pending method calls.
  * **Phase 4: Root Cause Analysis Summary** – Added automated root cause analysis summaries for PIN code request failures, including agent registration status, capability support, method invocation status, device connection state, timing analysis, and actionable recommendations.
  * **Phase 5: Agent Registration Status Verification** – Added tracking of agent registration/unregistration events and verification of agent registration status at time of each request, with warnings when agent is not registered.
  * **Phase 6: Destination Verification Diagnostic Logging** – Added comprehensive diagnostic logging to verify if BlueZ is calling BLEEP's agent or a different agent:
    * **Bus unique name logging**: Logs D-Bus bus unique name at agent creation and registration for destination verification
    * **Destination comparison**: Compares METHOD CALL destination with BLEEP's bus unique name to detect if BlueZ is calling a different agent
    * **Verification messages**: Logs clear verification messages indicating whether destination matches BLEEP's agent or if a different agent is being called
    * **Fix**: Moved destination verification code from deprecated `_on_method_call()` function to `_log_event()` function (used by unified monitoring) to ensure logs actually appear
    * **Files Modified**: `bleep/dbuslayer/agent.py` (added bus unique name logging in `__init__()` and `register()`), `bleep/dbuslayer/signals.py` (added destination verification in `_log_event()` for both method_call events and signal reclassification cases, removed incorrect code from `_on_method_call()`)
    * **Purpose**: Diagnose why agent methods may not be invoked even when METHOD CALL events are captured (destination mismatch indicates BlueZ calling different agent)
    * **Status**: Fully implemented and verified - destination verification logs now appear correctly in agent.log
  * **Files Modified**: `bleep/dbuslayer/signals.py` (added communication type validation, agent method invocation correlation, RequestPinCode → Cancel correlation, device connection state tracking, root cause analysis, destination verification), `bleep/dbuslayer/agent.py` (added method invocation tracking, capability validation, expected methods logging, bus unique name logging), `bleep/bt_ref/exceptions.py` (added `RejectedException` class)
    * **Status**: Diagnostic capabilities fully implemented. **Core issue resolved in v2.4.7**: D-Bus method registration fixed by creating mainloop object before agent registration. See `agent_dbus_communication_issue.md` for details.

### Fixed
* **AGENT_INTERFACE Constant** – Critical fix for agent functionality:
  * **Root Cause**: `AGENT_INTERFACE` was incorrectly set to `"org.bluez.mesh.ProvisioningAgent1"` (mesh provisioning interface) instead of `"org.bluez.Agent1"` (standard pairing agent interface)
  * **Impact**: All agent D-Bus method decorators used the wrong interface, preventing BlueZ from recognizing agent methods during pairing operations
  * **Solution**: Corrected `AGENT_INTERFACE` to `"org.bluez.Agent1"` in `bleep/bt_ref/constants.py` (old value preserved as comment for historical tracking)
  * **Files Modified**: `bleep/bt_ref/constants.py` (line 44-45)
  * **Verification**: Agent methods now correctly register with BlueZ's standard pairing agent interface
* **Unified D-Bus Monitoring – Critical Syntax and Logic Fixes**:
  * **Root Cause**: `enable_agent_method_call_monitoring()` had duplicate implementation code after delegation, causing syntax errors and duplicate message filter registration
  * **Impact**: 
    * Invalid docstring in middle of function body (line 1248)
    * Duplicate message filters registered (both unified and old handlers active simultaneously)
    * Duplicate logging of same events
    * Unreachable code after delegation call
  * **Solution**: 
    * Removed duplicate code (lines 1248-1275) from `enable_agent_method_call_monitoring()` - function now only delegates to unified monitoring
    * Improved `_is_relevant_message()` filter to better detect BlueZ messages:
      * Added ObjectManager signal detection at root path (`/`)
      * Fixed handling of signals with null destination
      * Removed flawed bus name heuristic (bus names like `:1.149` don't contain "bluez")
      * Improved path-based filtering for all message types
    * Refined match strings to reduce overlap and improve specificity:
      * Replaced `sender='org.bluez'` signal matching with `path_namespace='/org/bluez'` (more reliable)
      * Added explicit ObjectManager signal matching
      * Removed redundant match strings that overlapped
      * Made eavesdrop rules more specific (interface-based instead of broad)
  * **Files Modified**: `bleep/dbuslayer/signals.py` (lines 1237-1275, 925-965, 788-808)
  * **Verification**: 
    * Syntax check passed (`py_compile`)
    * Runtime verification passed (import, instantiation, method calls)
    * No duplicate filters registered
    * Improved message detection for BlueZ communications
* **Debug Mode – `ckeep` reliability** – Removed duplicated execution blocks inside `_cmd_ckeep()` so the command runs a single, consistent code path.
* **Debug Mode – `ckeep` error handling** – Enhanced error messages to preserve BlueZ D-Bus error details:
  * Created `_format_dbus_error()` helper function to format D-Bus exceptions as `name: message` following BLEEP error handling patterns.
  * Updated all error paths in `_cmd_ckeep()` to use enhanced error formatting (connect failures, SDP discovery failures, socket open failures).
  * Error messages now show full D-Bus error context (e.g., `org.bluez.Error.Failed: br-connection-unknown`) for better troubleshooting.
  * **Note**: Error handling and logging are fully functional. Core RFCOMM socket functionality requires further validation with a Classic device that has no pairing/PIN requirements.
* **Error visibility** – Preserve BlueZ `org.bluez.Error.Failed` message details (e.g. `br-connection-unknown`) in mapped Bleep errors for easier troubleshooting.
* **Agent + AgentManager diagnostics** – Improve verbosity across agent registration, connect/pair failures, and IO handlers:
  * AgentManager setup/register failures now include D-Bus error name/message + agent context.
  * Classic/LE connect/pair logging now includes device path + D-Bus error name/message.
  * Programmatic/AutoAccept IO handlers now include handler context (auto_accept + defaults used).
  * Debug mode adds `agent status|register|unregister` for quick verification.
* **Error clarity expansion** – Preserve D-Bus name/message across additional subsystems:
  * Default D-Bus error mapping now retains message payload in the generic fall-through path.
  * Media (Media1/MediaFolder/MediaItem) wrappers log structured `name: message` instead of `str(e)`.
  * OBEX PBAP errors now include D-Bus `name` + `message` in raised diagnostics.
  * LE manager StartDiscovery fallback now logs the underlying D-Bus `name: message`.
  * GATT wrappers (Characteristic/Descriptor/Service) emit structured D-Bus `name: message` for otherwise-silent failure paths.
  * Media wrappers now consistently avoid `str(e)` logs; all D-Bus failures include object path + `name: message`.
  * Classic/LE device wrappers and agent unregister now preserve D-Bus `name: message` on otherwise low-signal failure paths (trust/disconnect/profile ops/type-check fallbacks).
  * LE discovery manager now logs StopDiscovery failures with adapter path + D-Bus `name: message` (still non-fatal).
  * `ble_ops/*` callers now preserve D-Bus `name: message` in otherwise generic exception logs (scan/pokey/bruteforce enumeration and classic SDP/PBAP D-Bus paths).
  * **Task A complete** – Completed “silent failure audit + targeted verbosity upgrades” across high-impact D-Bus/GATT/media/scan paths (logging-only; no behavior changes).
* **bt_ref error mapping** – `bleep/bt_ref/error_map.py` now uses core-first D-Bus decoding (name+message) while preserving the `(code, category)` / `(code, recovered)` contract and recovery semantics.
* **bt_ref recovery accuracy** – Fix tuple-return recovery handling and add disciplined retry helper:
  * Recovery helpers now treat tuple-return failures `(code, False)` as actual failures (previously could report recovered when it wasn’t).
  * Added `attempt_operation_with_recovery()` to centralize fixed-delay, low-cap retry behavior and avoid ad-hoc retry loops.
* **BLEEPError transparency** – Improve core D-Bus exception mapping to preserve actionable payloads:
  * `NotAuthorizedError` preserves the original D-Bus message as a reason (no “blanding”).
  * `ServiceUnknown` mapping now surfaces the D-Bus message payload when present.
  * `UnknownObject` mapping preserves `name: message` instead of forcing an unrelated “Device not found” message.
  * Fixed `handle_dbus_exception()` to raise the mapped `BLEEPError` (previously attempted to unpack a non-tuple).
  * **Error mapping deprecation markers (B5)** – Marked duplicate/legacy error mapping systems for future consolidation:
    * `bt_ref/error_map.py::DBUS_ERROR_MAP` deprecated as primary source (now refinement-only fallback).
    * `core/error_handling.py::evaluate__dbus_error()` deprecated in favor of canonical `decode_dbus_error()`.
    * Added documentation identifying consolidation opportunities within `core/error_handling.py`.
  * **Legacy module removal (B5.2)** – Removed unused `bleep/dbus/device.py` after comprehensive audit confirmed zero imports/usage:
    * Phase 1 audit: AST-based static analysis and runtime verification confirmed no artifacts of `bleep.dbus.device` imports in codebase
    * All actual usage imports from `bleep.dbuslayer.device_le` (refactored implementation)
    * Direct removal executed (Option A) - no compatibility shim needed
    * Verified no regressions: all key entrypoints import successfully after removal

### Fixed
* **PIN Code Request Logging Visibility** – Resolved issue where PIN code requests from BlueZ were not visible in BLEEP logs:
  * **Root Cause**: Agent methods were being called but entry point logging was missing, making it unclear if agent was selected by BlueZ
  * **Solution**: Added comprehensive entry point logging to all agent methods and enhanced registration status logging
  * **Impact**: Users can now verify agent selection and see complete PIN code request flow in agent logs
  * **Verification**: Check `/tmp/bti__logging__agent.txt` for `"[*] RequestPinCode METHOD CALLED"` messages during pairing

### Known issues / Investigations
* **Pairing prompts not shown in Bleep terminal (Classic / legacy PIN flows)**:
  * `btmon` may show `PIN Code Request`, but no interactive prompt appears in the Bleep terminal in some setups.
  * **Status**: Enhanced logging now provides visibility into whether BLEEP's agent is being called. Use `bleep agent --status` and check agent logs to verify agent selection.
  * **Diagnosis**: If `RequestPinCode METHOD CALLED` logs appear, agent is working but may need different IO handler. If logs don't appear, BlueZ is using a different agent.
* **`ckeep` keep-alive functionality requires further work**:
  * Error handling and logging are fully functional and working as designed.
  * Full functionality testing and validation is blocked by Classic device connection issues.
  * Requires a Bluetooth Classic target device with no pairing/PIN requirements to properly validate RFCOMM socket operations and ACL keep-alive functionality.
  * Core connection/socket operations need validation with appropriate hardware before functionality can be confirmed working end-to-end.

---

## v2.4.5 – Agent Mode CLI Fix (2025-12-16)

### Fixed
* **Agent Mode CLI Routing** – Fixed critical bug preventing agent mode from working via CLI:
  * **Root Cause**: argparse subparser argument name conflict - `args.mode` overwritten by `--mode` argument value, causing `args.mode == "agent"` check to never match
  * **Solution**: Changed routing check from `args.mode == "agent"` to `sys.argv[1] == "agent"` and pass `sys.argv[2:]` to agent mode
  * **Files Modified**: `bleep/cli.py` (routing fix at line 702, argument expansion at lines 72-95)
  * **Impact**: All 12 agent mode features now accessible via CLI (previously only 2 worked)

### Enhanced
* **Agent Mode CLI Arguments** – Exposed all agent mode features via CLI:
  * Expanded `--mode` choices to include `enhanced` and `pairing` (previously only simple/interactive)
  * Added `--cap`, `--default`, `--auto-accept`, `--pair`, `--trust`, `--untrust`, `--list-trusted`, `--list-bonded`, `--remove-bond`, `--storage-path`, `--timeout` arguments
  * All arguments passed through to agent mode's parser for processing
  * Improved `bleep agent --help` output with complete option list

## v2.4.4 – Database Foreign Key Constraint Fix (2025-11-27)

### Fixed
* **FOREIGN KEY Constraint Errors During Scan** – Fixed critical database integrity issue:
  * **Root Cause**: Device type classifier was storing evidence before devices were inserted into database
  * **Solution**: Restructured database operation sequence to insert device first, then classify, then update
  * **Files Modified**:
    * `bleep/dbuslayer/adapter.py` – Removed premature classification from `get_discovered_devices()`
    * `bleep/ble_ops/scan.py` – Restructured `_native_scan()` and `_base_enum()` for proper sequencing
    * `bleep/core/observations.py` – Added defensive IntegrityError handling
    * `bleep/dbuslayer/media.py` – Fixed SyntaxWarning from invalid escape sequences
  * **Impact**: All scan operations now complete without foreign key errors
  * **Backward Compatibility**: `_determine_device_type()` method preserved for other callers

### Enhanced
* **Database Operation Sequencing** – Improved architectural flow:
  * Device insertion happens BEFORE classification evidence storage
  * Classification performed AFTER device exists in database
  * Database caching enabled safely after initial device insert
  * Two `upsert_device()` calls per device (minimal performance impact)

## v2.4.3 – UUID Translation System (2025-11-XX)

### Added
* **UUID Translation Functionality** – Comprehensive UUID translation system for quick lookups:
  * **Core Translation Engine** (`bleep/bt_ref/uuid_translator.py`):
    * Modular architecture with pluggable format handlers for extensibility
    * Support for 16-bit, 32-bit, and 128-bit UUID formats
    * Automatic expansion of 16-bit UUIDs to find all potential matches
    * Searches across all BLEEP UUID databases (Services, Characteristics, Descriptors, Members, SDOs, Service Classes, Custom)
    * Handles multiple input formats (with/without dashes, case-insensitive, hex prefixes)
    * Structured output with categorized matches and metadata
  * **CLI Command** (`bleep uuid-translate` / `bleep uuid-lookup`):
    * Standalone command for quick UUID lookups
    * Support for single or multiple UUIDs in one command
    * JSON output option for programmatic use (`--json`)
    * Verbose mode for detailed information including source databases (`--verbose`)
    * Human-readable text output with categorized results
  * **Interactive Mode Integration**:
    * Added `uuid` command to interactive mode for quick translations
    * Supports multiple UUIDs: `uuid 180a 2a00 2a01`
    * Integrated into help system
  * **User Mode Integration**:
    * Added "Translate UUID" menu option (option 5) to user-friendly menu mode
    * Interactive UUID translation with verbose output
    * User-friendly prompts and error handling
  * **Comprehensive Documentation**:
    * Created `uuid_translation.md` with usage guide, examples, and architecture details
    * Created `uuid_translation_plan.md` with detailed implementation plan
    * Updated CLI usage documentation
  * **Test Suite**:
    * Added comprehensive unit tests in `tests/test_uuid_translation.py`
    * Tests cover 16-bit, 32-bit, and 128-bit UUID formats
    * Tests for custom UUIDs, unknown UUIDs, and edge cases
    * Tests for case-insensitive handling and multiple format normalization
    * All tests passing

### Enhanced
* **Modularity & Extensibility**:
  * Designed with modular architecture for easy extension
  * `UUIDFormatHandler` base class allows adding support for non-standard UUID formats
  * `UUIDDatabase` class provides unified interface to all UUID sources
  * Simple registration system for custom format handlers
  * Future-proof design for handling non-standard 128-bit UUID formats

### Technical Details
* **Database Integration**: Leverages existing BLEEP UUID databases:
  * `constants.UUID_NAMES` (custom UUIDs)
  * `uuids.SPEC_UUID_NAMES__SERV` (Services)
  * `uuids.SPEC_UUID_NAMES__CHAR` (Characteristics)
  * `uuids.SPEC_UUID_NAMES__DESC` (Descriptors)
  * `uuids.SPEC_UUID_NAMES__MEMB` (Members)
  * `uuids.SPEC_UUID_NAMES__SDO` (SDOs)
  * `uuids.SPEC_UUID_NAMES__SERV_CLASS` (Service Classes)
* **Format Support**: Handles various UUID input formats:
  * 16-bit: `180a`, `0x180a`, `0x180A`
  * 32-bit: `0000180a`
  * 128-bit: `0000180a-0000-1000-8000-00805f9b34fb` (with dashes)
  * 128-bit: `0000180a00001000800000805f9b34fb` (without dashes)
* **Output Formats**: Provides both human-readable and JSON output:
  * Text output with categorized matches grouped by type
  * JSON output with structured data for programmatic use
  * Verbose mode includes source database information

## v2.4.2 – Dual Device Detection Framework (2025-11-10)

### Added
* **Dual Device Detection Framework** – Comprehensive evidence-based device type classification system:
  * **Phase 1: Core Framework** – Created `DeviceTypeClassifier` module (`bleep/analysis/device_type_classifier.py`):
    * Evidence-based classification with weighted evidence (CONCLUSIVE, STRONG, WEAK, INCONCLUSIVE)
    * 7 default evidence collectors (Classic: device_class, SDP records, service UUIDs; LE: address_type, GATT services, service UUIDs, advertising data)
    * Mode-aware evidence collection (passive/naggy/pokey/bruteforce)
    * Strict dual-detection logic requiring conclusive evidence from BOTH protocols
    * Stateless classification (based ONLY on current device state, no database dependency for decisions)
    * Code reuse leveraging existing BLEEP functions (`discover_services_sdp_connectionless()`, `device.services_resolved()`, `identify_uuid()`, etc.)
    * UUID detection using existing BLEEP constants (`SPEC_UUID_NAMES__SERV_CLASS`, `SPEC_UUID_NAMES__SERV`) - no hardcoded patterns
  * **Phase 2: Database Integration** – Schema v6 with evidence audit trail:
    * Created `device_type_evidence` table for audit/debugging (NOT used for classification decisions)
    * Database-first performance optimization with signature caching (1-5ms cache hits vs 100-5000ms full classification)
    * Evidence storage functions (`store_device_type_evidence()`, `get_device_type_evidence()`, `get_device_evidence_signature()`)
    * Automatic schema migration from v5 to v6
    * Proper indexes for efficient evidence queries

  * **Phase 3: D-Bus Layer Integration** – Fixed Type property access errors:
    * Fixed `device_classic.get_device_type()` - removed incorrect `Type` property access, now uses evidence-based classification
    * Fixed `device_le.check_device_type()` - removed incorrect `Type` property access, now uses evidence-based classification
    * Fixed `adapter._determine_device_type()` - removed hardcoded UUID patterns, now uses DeviceTypeClassifier with existing BLEEP constants
    * All methods maintain backward compatibility (return types unchanged)
    * Proper context building from device properties for classifier

  * **Phase 4: Mode-Aware Evidence Collection** – Scan mode integration:
    * Updated all scan functions to pass appropriate `scan_mode` to device type classification
    * `passive_scan_and_connect()` uses "passive" mode (advertising data only)
    * `naggy_scan_and_connect()` uses "naggy" mode (passive + connection-based collectors)
    * `pokey_scan_and_connect()` uses "pokey" mode (all collectors including SDP queries)
    * `bruteforce_scan_and_connect()` uses "bruteforce" mode (all collectors, exhaustive testing)
    * `connect_and_enumerate__bluetooth__classic()` uses "pokey" mode (SDP enumeration)
    * Evidence collectors already mode-aware (implemented in Phase 1)
    * Mode filtering ensures appropriate evidence collection based on scan aggressiveness

  * **Phase 5: Documentation & Testing** – Comprehensive documentation and test suite:
    * Created `device_type_classification.md` - Complete guide with examples, troubleshooting, and best practices
    * Updated `observation_db.md` - Evidence-based classification system documentation
    * Updated `observation_db_schema.md` - Schema v6 migration notes and device_type_evidence table documentation
    * Created `test_device_type_integration.py` - Comprehensive integration test suite (21 tests)
    * Tests cover: evidence collection, classification logic, mode-aware filtering, database integration, edge cases, schema migration
    * All core functionality tests passing

## v2.4.1 – Enhanced SDP Attribute Extraction, Connectionless Queries, Version Detection & Comprehensive SDP Analysis (2025-11-09)
### Added
* **Classic Integration Tests (bc-12)** – Comprehensive test suite covering:
  * Enhanced SDP feature tests (Phase 1-4 features: enhanced attributes, connectionless queries, version detection, comprehensive analysis)
  * PBAP comprehensive tests (multiple repositories, vCard formats, auto-auth, watchdog, output handling, database integration)
  * CLI command tests (`classic-enum`, `classic-pbap`, `classic-ping`) in `tests/test_classic_cli.py`
  * Debug mode command tests (`cscan`, `cconnect`, `cservices`, `csdp`, `pbap`) in `tests/test_classic_debug_mode.py`
  * Error recovery & edge case tests (reconnection, concurrent operations, timeout handling, partial service discovery)
  * Enhanced `tests/test_classic_integration.py` with comprehensive test coverage
  * All tests follow existing patterns, use proper fixtures, and skip gracefully when hardware unavailable
* **Debug Mode PBAP Command (bc-10)** – Added `pbap` command to debug mode:
  * Interactive PBAP phonebook dumps from connected Classic devices
  * Supports all CLI `classic-pbap` features (multiple repositories, vCard formats, auto-auth, watchdog)
  * Automatic PBAP service detection from service map or SDP records
  * Database integration for PBAP metadata (if enabled)
  * Comprehensive error handling with helpful diagnostic messages
  * Entry counting and file statistics display
  * Follows existing debug mode command patterns and conventions
* **Debug Mode Connectionless SDP Discovery** – Added `csdp` command to debug mode:
  * SDP discovery for Classic devices without requiring full connection
  * Connectionless mode with l2ping reachability check (matches CLI `--connectionless` flag)
  * Configurable l2ping parameters (`--l2ping-count`, `--l2ping-timeout`)
  * Detailed SDP record display with all enhanced attributes (handles, profile versions, service versions, descriptions)
  * Automatic service map generation from discovered records
  * Faster failure detection for unreachable devices (~13 seconds vs. 30+ seconds)
  * Useful for reconnaissance before attempting connection
* **Enhanced SDP Attribute Extraction** – Extended Classic Bluetooth SDP discovery:
  * Extract Service Record Handle (0x0000) from SDP records
  * Extract Bluetooth Profile Descriptor List (0x0009) with profile UUIDs and versions
  * Extract Service Version (0x0300) when available
  * Extract Service Description (0x0101) when available
  * Enhanced both D-Bus XML parsing and sdptool text parsing to capture additional attributes
* **Debug Mode for classic-enum** – Added `--debug` flag to `classic-enum` command:
  * Displays enhanced SDP attributes (handles, profile versions, service versions, descriptions)
  * Shows detailed parsing information
  * Enables verbose logging to `/tmp/bti__logging__debug.txt`
* **Connectionless SDP Fallback** – Improved `classic-enum` to work without full connection:
  * SDP queries work connectionless (no pairing/connection required)
  * If connection fails, still displays SDP enumeration results
  * Useful for reconnaissance when devices are not available for full connection
* **Connectionless Mode with Reachability Check** – Added `--connectionless` flag and `discover_services_sdp_connectionless()` function:
  * Verifies device reachability using `l2ping` before attempting SDP queries
  * Provides faster failure detection (~13 seconds vs. 30+ second SDP timeout)
  * Better error messages distinguishing unreachable devices from SDP failures
  * Configurable l2ping parameters (`l2ping_count`, `l2ping_timeout`)
  * Graceful degradation if `classic_l2ping` module unavailable
* **Bluetooth Version Detection** – Added `--version-info` flag and version detection capabilities:
  * Device version information extraction (`get_vendor()`, `get_product()`, `get_version()`, `get_modalias()`)
  * Dual-source extraction: Device1 properties with modalias fallback
  * Profile version mapping from SDP records to Bluetooth spec versions (heuristic)
  * Local HCI adapter version query via `hciconfig` (no sudo required)
  * LMP version to Bluetooth Core Specification mapping (Bluetooth 1.0b through 5.6)
  * Raw property preservation for offline analysis
  * Created `bleep/ble_ops/classic_version.py` module for version detection helpers
* **Comprehensive SDP Analysis** – Added `--analyze` flag and `SDPAnalyzer` class:
  * Protocol analysis identifying all protocols used (RFCOMM, L2CAP, BNEP, OBEX, etc.)
  * Profile version analysis with cross-referencing across services
  * Advanced version inference engine using profile version patterns
  * Anomaly detection for version inconsistencies and unusual patterns
  * Service relationship analysis grouping related services
  * Comprehensive reporting with human-readable and JSON output formats
  * Created `bleep/analysis/sdp_analyzer.py` module for advanced SDP analysis

### Enhanced
* **SDP Record Structure** – Extended return structure with optional fields:
  * `handle` – Service Record Handle
  * `profile_descriptors` – List of profile UUID/version pairs
  * `service_version` – Service version number
  * `description` – Service description text
  * All new fields are optional (None if not available) for backward compatibility

## v2.4.0 – Enhanced Pairing Agent (2025-10-01)
### Added
* **Enhanced Pairing Agent** – Comprehensive Bluetooth pairing system:
  * Implemented flexible I/O handler framework (`bleep/dbuslayer/agent_io.py`) with CLI, programmatic, and auto-accept options
  * Added pairing state machine (`bleep/dbuslayer/pairing_state.py`) for robust pairing process management
  * Created secure storage for bonding information (`bleep/dbuslayer/bond_storage.py`)
  * Enhanced BlueZ agent classes with modular design and D-Bus reliability integration
  * Added support for all pairing methods (legacy PIN, SSP)
  * Added support for all capability levels (NoInputNoOutput, DisplayOnly, KeyboardDisplay, etc.)
  * Implemented service-level authorization
* **Pairing Agent Documentation** – Comprehensive documentation for the pairing agent:
  * Created detailed `pairing_agent.md` guide with architecture and usage examples
  * Added `agent_mode.md` with CLI usage instructions
  * Created `agent_documentation_index.md` for easy navigation
  * Updated main documentation index with new agent documentation
  * Added programmatic usage examples and best practices

### Enhanced
* **Agent Mode** – Improved agent mode in CLI:
  * Added bond management commands (list-bonded, remove-bond)
  * Enhanced trust management (trust, untrust, list-trusted)
  * Added customization options for agent capabilities
  * Improved error handling and user feedback

## v2.3.1 – Legacy Code Removal & Complete Self-Sufficiency (2025-10-29)

### Breaking Changes
* **Removed Legacy Module Shims** – Complete removal of backward compatibility shims for root-level imports:
  * Removed `sys.modules` shims in `bleep/__init__.py` that allowed `import bluetooth_constants` (root-level)
  * Deleted root-level legacy shim files (`bluetooth_constants.py`, `bluetooth_utils.py`, `bluetooth_uuids.py`, `bluetooth_exceptions.py`)
  * External scripts must now use proper import paths: `from bleep.bt_ref import constants, utils, uuids, exceptions`
  * **Migration Required**: Any external scripts using root-level `import bluetooth_constants` will break and must be updated

### Removed
* **Legacy Compatibility Module** – Removed deprecated `bleep.compat.py` module:
  * Module was unused internally and provided deprecated backward compatibility shims
  * Cleaner codebase with reduced maintenance burden
* **Legacy Namespace Shim** – Removed `sys.modules` shim for `Functions.ble_ctf_functions` in `bleep/ble_ops/ctf.py`:
  * Legacy namespace was not used in refactored codebase
  * Removed unnecessary defensive programming artifact

### Changed
* **Package Installation** – Improved package portability and installation:
  * Made PyGObject optional (moved to `extras_require["monitor"]`) to fix installation failures in environments without build dependencies
  * Added YAML cache files (`yaml_cache/*.yaml`, `url_mappings.json`) to `package_data` for complete package distribution
  * `pip install -e .` now works without requiring `libgirepository1.0-dev` for PyGObject compilation
  * Users needing monitor features can install with: `pip install -e .[monitor]`

### Fixed
* **Self-Sufficiency** – Achieved complete codebase independence:
  * All internal imports now use proper paths (`from bleep.bt_ref import constants`)
  * No dependencies on root-level legacy files
  * Package can be installed in any directory without external file dependencies
  * No circular import issues when deployed to different environments

## v2.3.0 – D-Bus Reliability Improvements (2025-09-30)
### Added
* **D-Bus Reliability Framework** – Comprehensive system to improve D-Bus interaction stability:
  * Added timeout enforcement layer (`bleep/dbus/timeout_manager.py`) to prevent operations from hanging
  * Implemented BlueZ service monitor (`bleep/dbuslayer/bluez_monitor.py`) for stall and restart detection
  * Created controller health metrics system (`bleep/core/metrics.py`) for performance tracking
  * Added automatic connection recovery with staged strategies (`bleep/dbuslayer/recovery.py`)
  * Implemented state preservation system for reconnection handling
  * Added D-Bus connection pool (`bleep/dbus/connection_pool.py`) for optimized connections
  * Created comprehensive diagnostic tool (`bleep/scripts/dbus_diagnostic.py`)
* **D-Bus Reliability Documentation** – Detailed guides and best practices:
  * Added comprehensive best practices guide (`bleep/docs/dbus_best_practices.md`)
  * Created system architecture documentation (`bleep/docs/d-bus-reliability.md`) 
  * Added examples and templates for robust D-Bus usage
  * Documentation for diagnostic tool and troubleshooting

### Fixed
* **BlueZ Connection Stability** – Fixed common issues with BlueZ D-Bus operations:
  * Implemented reliable timeout handling for all D-Bus method calls
  * Added graceful error recovery for connection issues
  * Improved performance for high-volume D-Bus operations
  * Added detailed metrics collection for operation diagnosis

## v2.2.2 – AoI Mode Fixes & Documentation Improvements (2025-09-26)
### Fixed
* **AoI Implementation Issues** – Fixed critical issues with the Assets-of-Interest functionality:
  * Added missing `analyze_device_data` method to bridge between function calls with different naming conventions
  * Fixed service and characteristic data handling to support different data structures
  * Added robust type checking to prevent "'list' object has no attribute 'items'" errors
  * Improved handling of service and characteristic UUIDs in different formats
  * Enhanced error handling for various data structure formats in saved AoI data
  * Fixed method name mismatches between American and British spelling conventions
  * Added support for extracting characteristics from services_mapping when needed
  * Fixed proper path resolution when working with device data files

### Added
* **AoI Documentation Improvements** – Enhanced documentation for the Assets-of-Interest feature:
  * Added detailed implementation notes about data handling and error recovery
  * Updated examples with more realistic use cases
  * Added new troubleshooting section with common issues and solutions
  * Expanded best practices with tips for more effective device analysis
  * Added explanation of different data structures supported by the analyzer

## v2.2.1 – Debug Mode Command Improvements (2025-09-26)
### Fixed
* **Debug Mode Command Errors** – Fixed and improved the multiread_all command:
  * Fixed parameter parsing to properly handle both `rounds=X` format and direct number format
  * Added robust result structure handling to prevent "'str' object has no attribute 'get'" errors
  * Improved error handling and reporting for all multi-read operations
  * Ensures consistent behavior across all debug mode commands
  * Made command device-agnostic to work with any Bluetooth device, not just specific ones
  * Properly identifies all readable characteristics by examining flags and properties
  * Added multiple methods to discover characteristics, with progressive fallbacks
  * Enhanced logging with proper log levels for better debugging and traceability
  * Preserved existing functionality while adding improved error handling
  * Added comprehensive docstrings and comments for better code maintainability
  * Implemented generic device address handling to work with any device type

## v2.2.0 – Complete Timeline Tracking & Signal System Integration (2025-09-26)
### Added
* **Full Timeline Tracking** – Added comprehensive timeline tracking for all characteristic operations:
  * Implemented complete database tracking for characteristic reads, writes, and notifications
  * Added `bleep db timeline` command to view characteristic history with filtering options
  * Enhanced signal system to capture all characteristic operations across all interfaces
  * Ensured consistent source attribution for all database entries

### Fixed
* **Signal System Integration** – Fixed critical issue with signal handling system not being initialized:
  * Added proper initialization of signal system in `bleep/__init__.py`
  * Ensured signal integration with BlueZ signals via `integrate_with_bluez_signals()`
  * Added `patch_signal_capture_class()` call to ensure all signal captures are processed
  * Created default signal routes to store read/write/notification events in database
  * Enhanced CTF module to properly emit signals for characteristic operations
  * Added robust error handling for signal processing and database storage
  * Fixed direct D-Bus access operations to properly emit signals
  * Added direct database insertion as fallback for CTF module operations
  * Implemented comprehensive debugging for signal system
  * Ensures all characteristic operations are properly tracked in the database
  * Fixed `bleep db timeline` command to correctly show characteristic history

## v2.1.17 – Complete Enum-Scan Database Integration Fix (2025-09-26)
### Fixed
* **Enum-Scan Characteristics Database Error** – Fixed critical issue with characteristics not being saved to database:
  * **Root cause identified**: SQL syntax error in upsert_characteristics function and CLI data format mismatch
  * Added robust error handling to upsert_characteristics function to prevent cascade failures
  * Fixed property handling to properly format as comma-separated strings for database storage
  * Added robust support for multiple data structure formats (standard, gatt-enum, and enum-scan)
  * Fixed direct persistence in CLI module to handle different enum-scan variant outputs
  * Implemented unified data structure handling in _persist_mapping function to support all formats
  * Added support for enum-scan's "mapping" key format that was previously unrecognized
  * Implemented case-insensitive key detection for "chars"/"Characteristics", "properties"/"Flags", etc.
  * Added smart handle conversion from hex string format to numeric values
  * Improved value extraction with fallback to binary "Raw" data when available
  * Added explicit database commit to ensure all changes are persisted
  * Fixed CLI enum-scan and gatt-enum commands to ensure results are persisted properly
  * Added improved error logging to diagnose future issues
  * Streamlined error handling to prevent service persistence without characteristics
  * Maintains backward compatibility with all existing code paths

## v2.1.16 – Enum-Scan Database Integration Fix (2025-09-26)
### Fixed
* **Enum-Scan Database Error** – Fixed critical issue with enum-scan database integration:
  * Added robust type checking to prevent "'str' object has no attribute 'get'" errors
  * Enhanced error handling for non-dictionary service and characteristic data
  * Added detailed debug logging for unexpected data structures
  * Ensures enum-scan commands properly save device information to the database

## v2.1.15 – Database Transaction Fix (2025-09-26)
### Fixed
* **Missing Database Commit** – Fixed critical issue with characteristic history tracking:
  * Added missing commit operation to `insert_char_history` function
  * Fixed issue where characteristic reads were not being persisted to the database
  * Ensures all characteristic values are properly saved to the database
  * Allows `bleep db timeline` to correctly show characteristic history

## v2.1.14 – Debug Mode Parameter Parsing Fixes (2025-09-26)
### Fixed
* **Rounds Parameter Parsing** – Fixed critical issue with rounds parameter in debug mode:
  * Updated argument parsing to correctly handle `rounds=X` format
  * Fixed issue where `rounds=1000` was being ignored and defaulting to 10
  * Added support for both direct number and key=value format
  * Ensures user-specified round count is properly respected
* **Multi-Read Database Integration** – Fixed issue with database tracking:
  * Updated `multiread` command to explicitly save each read value to the database
  * Fixed disconnect between specified rounds and database entries
  * Added count reporting for database saves
  * Ensures all read operations are properly tracked in the database

## v2.1.13 – Debug Mode Enhancements (2025-09-26)
### Added
* **Advanced Read/Write Commands in Debug Mode** – Added powerful commands to debug mode:
  * Added `multiread` command to read a characteristic multiple times
  * Added `multiread_all` command to read all readable characteristics multiple times
  * Added `brutewrite` command for brute force writing to characteristics
  * All new commands integrate with the database tracking system
  * Exposed the same functionality available in the CLI to debug mode

### Fixed
* **Database Tracking for Multi-Read Operations** – Fixed source attribution in database:
  * Updated `insert_char_history` calls in `enum_helpers.py` to include "read" source
  * Ensures consistent source attribution across all database operations
  * Improves filtering capabilities in timeline view

## v2.1.12 – Debug Mode Database Integration (2025-09-26)
### Added
* **Debug Mode Database Integration** – Added comprehensive database integration to debug mode:
  * Added `dbsave` command to toggle database saving on/off
  * Added `dbexport` command to export device data from database
  * Enhanced enumeration commands to save services and characteristics
  * Added tracking for read operations with source attribution
  * Added tracking for write operations with source attribution
  * Added tracking for notifications with source attribution
  * Added new documentation in `debug_mode_db.md`
* **Characteristic History Source Tracking** – Enhanced characteristic history table:
  * Added `source` field to track how values were obtained (read, write, notification)
  * Updated schema migration to add the new field with default value
  * Modified `insert_char_history` function to support source attribution

## v2.1.11 – Database Export & MAC Address Fixes (2025-09-26)
### Fixed
* **Database MAC Address Handling** – Fixed critical issue with case sensitivity in MAC addresses:
  * Added `_normalize_mac` function to standardize all MAC addresses to lowercase
  * Updated all database functions to normalize MAC addresses before operations
  * Fixed issue where uppercase MAC addresses wouldn't match lowercase ones in database
  * Ensures consistent behavior regardless of MAC address case in commands
  * Resolves issue where `bleep db export` command couldn't find services for some devices
* **JSON Serialization Error** – Fixed error in database export functionality:
  * Added `_convert_binary_for_json` function to properly handle binary data in database
  * Converts binary data (like characteristic values) to hex strings for JSON serialization
  * Ensures `bleep db export` command works correctly with all types of data
  * Prevents "Object of type bytes is not JSON serializable" error

## v2.1.10 – Database Integration Fixes (2025-09-26)
### Fixed
* **Exploration Database Integration** – Fixed critical issues with exploration data not being saved to database:
  * Fixed function name mismatch (`upsert_service` vs. `upsert_services`)
  * Corrected value conversion from exploration format to database format
  * Fixed duplicate service saving in enum-scan command
  * Added proper error handling and logging
  * Ensured consistent device type classification across all commands

## v2.1.9 – Database Commands & Exploration Integration (2025-09-26)
### Added
* **Database Timeline Command** – Added missing `timeline` command to view characteristic value history:
  * Implemented `bleep db timeline <mac>` command to display characteristic value history
  * Added filtering options by service UUID (`--service`) and characteristic UUID (`--char`)
  * Added limit option (`--limit`) to control the number of entries displayed
  * Updated documentation with examples of timeline command usage
### Fixed
* **Exploration Database Integration** – Fixed issues with exploration data not being saved to database:
  * Added code to `exploration.py` to save discovered services and characteristics
  * Ensured consistent device type classification across all commands
  * Updated documentation to reflect new automatic logging capabilities

## v2.1.8 – Database Enhancements (2025-09-25)
### Added
* **Device Type Classification System** – Added more sophisticated device type classification:
  * Added `device_type` field to database schema (v3)
  * Implemented classification logic based on multiple properties (AddressType, DeviceClass, UUIDs)
  * Added constants for device types: `unknown`, `classic`, `le`, and `dual`
  * Updated `get_devices` function to filter by device type
  * Added documentation for device type classification
### Fixed
* **Database Timestamp Tracking** – Fixed issues with timestamp tracking:
  * Modified `upsert_device` to set `first_seen` only for new devices
  * Updated `last_seen` for all device updates
  * Added `first_seen` to default displayed columns in `db list`
  * Ensures proper tracking of device discovery and update times

## v2.1.7 – Stability & Performance (2025-09-24)
### Fixed
* **BlueZ Adapter Stability** – Improved stability of BlueZ adapter interactions:
  * Added more robust error handling for D-Bus method calls
  * Implemented automatic retry logic for transient failures
  * Added timeout handling for unresponsive adapters
  * Fixed race condition in device discovery events
* **Performance Optimizations** – Improved performance for large device lists:
  * Optimized database queries for faster device listing
  * Added indexing for frequently queried fields
  * Reduced memory usage during scan operations
  * Improved JSON serialization performance for export operations

## v2.1.6 – CLI Improvements (2025-09-23)
### Added
* **Enhanced CLI Output** – Improved CLI output formatting:
  * Added color support for terminal output
  * Implemented progress indicators for long-running operations
  * Added verbose mode for debugging
  * Improved error messages with suggested actions
* **Command Aliases** – Added convenient command aliases:
  * `bleep s` for `bleep scan`
  * `bleep e` for `bleep explore`
  * `bleep c` for `bleep connect`
  * `bleep d` for `bleep disconnect`

## v2.1.5 – New Features (2025-09-22)
### Added
* **Bluetooth Classic Support** – Enhanced support for Bluetooth Classic devices:
  * Added RFCOMM service discovery
  * Implemented SDP record parsing
  * Added support for common Bluetooth profiles (A2DP, HFP, etc.)
  * Improved device classification for dual-mode devices
* **Media Control** – Added media device control capabilities:
  * Implemented AVRCP profile support
  * Added commands for play, pause, next, previous
  * Added volume control
  * Added metadata display for playing media

## v2.1.0 – Major Update (2025-09-15)
### Added
* **Complete Refactoring** – Refactored codebase for better maintainability:
  * Modularized architecture with clear separation of concerns
  * Improved error handling and logging
  * Added comprehensive documentation
  * Implemented consistent coding style
* **Database Integration** – Added SQLite database for persistent storage:
  * Automatically logs discovered devices and services
  * Tracks advertising data and RSSI values
  * Stores characteristic values and history
  * Provides CLI commands for database access
* **Enhanced Scanning** – Improved scanning capabilities:
  * Added support for different scan modes (passive, active, etc.)
  * Implemented filtering options (RSSI, services, etc.)
  * Added real-time display of discovered devices
  * Improved handling of different address types
* **GATT Exploration** – Enhanced GATT service exploration:
  * Added support for primary and secondary services
  * Implemented characteristic and descriptor discovery
  * Added value reading and writing
  * Implemented notification and indication handling