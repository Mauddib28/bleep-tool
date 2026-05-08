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