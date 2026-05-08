# Central TODO tracker

This page aggregates open tasks referenced across the project so contributors have a single place to check before starting work.  **Edit directly** whenever you add / complete an item – no special tooling required.

## TODO sources

| Source | Section | Last reviewed |
|--------|---------|---------------|
| Codebase (`bleep/**/*.py`) | Inline `# TODO:` comments | _(grep as needed)_ |
| `bleep/docs/audio_recon.md` | Audio recon future work (Bonus Objectives) | _2026-02-28_ |
| `bleep/docs/adapter_config.md` | Adapter configuration reference | _2026-02-28_ |
| `bleep/ble_ops/audio/amusica.py` | Amusica orchestration (core) | _2026-02-28_ |
| `bleep/modes/amusica.py` | Amusica CLI mode | _2026-02-28_ |
| `bleep/docs/agent_dbus_communication_issue.md` | Agent dispatch fix (debug mode pairing) | _2026-02-28_ |
| `bleep/docs/mainloop_requirement_analysis.md` | GLib main-thread dispatch requirement | _2026-02-28_ |
| `bleep/dbuslayer/media.py`, `bleep/ble_ops/audio/audio_codec.py` | Audio transport & GStreamer fixes | _2026-03-19_ |
| `bleep/dbuslayer/media_stream.py`, `bleep/bt_ref/constants.py`, `bleep/cli.py` | MediaTransport discovery & media-enum enrichment | _2026-03-21_ |
| `bleep/ble_ops/audio/audio_system.py`, `bleep/cli.py` | System-tool audio play/record (`--system` flag) | _2026-03-21_ |
| `bleep/modes/exploration.py`, `bleep/core/observations.py`, `bleep/cli.py`, `bleep/ble_ops/classic/connect.py` | Data fidelity remediation (schema v10) | _2026-03-25_ |
| `workDir/BigMoves/README.v2.8.0` | BLEEP v2.8.0 full augmentation plan (pre-work, main work, bonus, final) | _2026-03-25_ |
| `bleep/modes/__init__.py`, `bleep/modes/debug_classic_obex.py` | Debug Mode lazy imports, MAP pagination & folder-context UX | _2026-03-30_ |
| `bleep/docs/map_bmessage_format.md` | MAP bMessage format reference & test corpus (10 validated files) | _2026-03-30_ |
| `bleep/ble_ops/classic/map.py`, `bleep/modes/debug_classic_obex.py` | MAP bulk download-all / push-all commands + operations-layer API | _2026-03-30_ |
| `workDir/Pairing/README.pairing-expansion` | Pairing CLI expansion + pre-pair check + shared helpers refactor | _2026-03-31_ |
| `workDir/bluez/doc/`, `workDir/BlueZDocs/`, `workDir/bluez-tools/`, `workDir/BlueZScripts/` | V2.8.1 BlueZ D-Bus interface gap analysis | _2026-04-02_ |
| `bleep/cli.py`, `bleep/ble_ops/classic/map.py` | MAP CLI folder enumeration fix + future auto-resolve | _2026-04-15_ |
| `bleep/dbuslayer/media_stream.py`, `bleep/dbuslayer/media.py`, `bleep/core/preflight.py` | MediaEndpoint1 contention pre-flight (complete) | _2026-04-17_ |
| `bleep/pairing/__init__.py`, `bleep/ble_ops/audio/audio_tools.py`, `bleep/modes/amusica.py`, `bleep/modes/pair.py`, `bleep/modes/classic_connect.py`, `bleep/cli.py` | Audio profile activation, recording reliability & profile identity fixes (complete) | _2026-04-21_ |
| `bleep/analysis/aoi_analyser.py`, `bleep/modes/aoi.py`, `bleep/core/observations.py`, `bleep/ble_ops/le/scan.py`, `bleep/cli.py` | AoI service-data normalisation, MAC validation & output fixes (v2.8.4) | _2026-05-07_ |
| `bleep/modes/aoi.py`, `bleep/analysis/aoi_analyser.py`, `bleep/core/observations.py`, `bleep/cli.py`, `bleep/ble_ops/le/scan.py` | AoI Augmentation — Full Implementation (v2.8.4; schema v11, scan pipeline, SDP, pairing, deep mode) | _2026-05-07_ |
| `bleep/core/observations.py` | MAC validation — reject incomplete/invalid MACs at DB boundary (v2.8.4) | _2026-05-07_ |

---

## MAC Validation — Reject Incomplete/Invalid MACs (v2.8.4, 2026-05-07) – COMPLETE

**Problem**: The BLEEP database contained invalid MAC entries observed in terminal
output: `4:A2:F9:BC:8E:95` (short first octet, only 1 hex digit instead of 2) and
`/ORG/BLUEZ/HCI0/DEV_F4_B6_88_0B_90_22` (raw D-Bus path stored verbatim).  Root
cause was the `_normalize_mac()` fallback `return mac.upper()` which stored any
unparseable string without validation.

**Policy**: It is preferable to drop a MAC than to zero-pad or guess.

**Fix**: Changed `_normalize_mac()` return type to `Optional[str]`, returning
`None` for any input that does not resolve to a strict 6-octet `XX:XX:XX:XX:XX:XX`
format.  Added `None`-guard early-return in all ~22 public functions in
`observations.py` that call `_normalize_mac()`.

**Files modified**: `bleep/core/observations.py`,
`tests/test_aoi_augmentation.py` (8 new rejection tests),
`tests/test_observations_characteristics.py` (MAC fixture fix),
`tests/test_observations_media.py` (MAC fixture fix).

**Test results**: 122 AoI tests pass, 299/324 full suite pass (10 pre-existing
failures unrelated to this change).

---

## AoI Augmentation — Full Implementation (v2.8.4, 2026-05-07) – COMPLETE

**Goal**: Implement the complete AoI augmentation plan including multi-transport
scan pipeline, device type classification, SDP discovery, pairing probe,
deep re-enumeration, enhanced analysis methods, v11 schema, and report generation.

**Files modified**:

| File | Change |
|------|--------|
| `bleep/modes/aoi.py` | Complete rewrite: removed ~200 lines dead code; added `_validate_mac`, `_classify_device`, `_discover_sdp`, `_probe_pairing`, `_perform_deep_reenumeration`, `_has_auth_annotation`, `_normalise_service_element`, `_scan_target`; wired `--deep`, `--timeout`, `--no-db`, `--connectionless`, `--address` on scan; `db list` action; v11 field merging in db import/sync |
| `bleep/analysis/aoi_analyser.py` | Added `db_only` param; `_analyse_sdp_records()`, `_analyse_pairing_profile()`, `_analyse_post_pair_delta()` methods; service list normalisation in `analyse_device()`; v11 field merging in `save_device_data()` and `analyse_device()`; safe `.get()` in `_generate_recommendations()`; report generators include SDP/pairing/delta sections; services section handles mixed types |
| `bleep/core/observations.py` | Schema v11: `pairing_profile`, `sdp_summary`, `post_pair_delta` columns; v10→v11 migration; `store_aoi_analysis()` persists v11 fields; `get_aoi_analysis()` returns v11 fields; `_normalize_mac()` hardened with regex, D-Bus path extraction; `import re` added |
| `bleep/cli.py` | `import signal` + `SIGPIPE` handler; `"db"` in `known_subcommands` |
| `bleep/ble_ops/le/scan.py` | `LOG__GENERAL` → `LOG__DEBUG` on `_native_scan` debug print |
| `tests/test_aoi_augmentation.py` | 58 tests covering all new functionality |
| `tests/test_device_type_integration.py` | Schema version assertion: 10 → 11 |

**Implementation details**:

- **Scan pipeline**: `_scan_target()` follows classify → GATT → SDP → pair → deep sequence
- **Device classification**: Uses `DeviceTypeClassifier.classify_with_mode()` from `bleep/analysis/device_type_classifier.py`
- **SDP discovery**: Calls `discover_services_sdp()` from `bleep/ble_ops/classic/sdp.py` with `connectionless` flag support
- **Pairing probe**: Uses `system_dbus__bluez_device__classic.pair()` via D-Bus
- **Deep mode**: Post-pair re-enumeration via `EnumerationController` (LE) and SDP (Classic)
- **v11 field flow**: `device_data["sdp_summary"]`, `device_data["pairing_profile"]`, `device_data["post_pair_delta"]` → merged into analysis dict → persisted via `store_aoi_analysis()`

---

## AoI Service-Data Normalisation, MAC Validation & Output Fixes (v2.8.4, 2026-05-07) – COMPLETE

**Goal**: Fix six issues discovered during live AoI testing — `unhashable type: 'dict'` crashes in analyze/report, `'dict' has no attribute 'strip'` in db sync/import, debug log leaking to user output, D-Bus object paths stored as MACs, and `BrokenPipeError` on piped output.

**Root cause**: `observations.get_device_detail()` returns `services` as `List[Dict]` (full SQLite rows), while AoI JSON files store `services` as `List[str]` (UUID strings). Code in `analyse_device()`, `db import`, and `db sync` assumed the list-of-strings shape, crashing when DB-loaded data was supplied.

**Files modified**:

| File | Change |
|------|--------|
| `bleep/analysis/aoi_analyser.py` | `analyse_device()` list branch normalises dict elements via `entry.get("uuid")` |
| `bleep/modes/aoi.py` | `db import` (line ~776) and `db sync` Step 2 (line ~880) comprehensions pass through dicts |
| `bleep/ble_ops/le/scan.py` | Changed `LOG__GENERAL` → `LOG__DEBUG` on `_native_scan` debug print |
| `bleep/core/observations.py` | `_normalize_mac()` now validates format, extracts MACs from D-Bus paths; `import re` moved to top-level |
| `bleep/cli.py` | Added `signal.signal(signal.SIGPIPE, signal.SIG_DFL)` in `main()` |
| `tests/test_aoi_augmentation.py` | +11 tests (3 service normalisation, 8 MAC validation) → 54 total |
| `tests/test_device_type_integration.py` | Schema version assertion updated 10 → 11 |

**Checklist**:
- [x] F1: `analyse_device()` list branch handles both UUID strings and DB row dicts
- [x] F2: `db import` service comprehension normalised
- [x] F3: `db sync` Step 2 service comprehension normalised
- [x] F4: `[DEBUG] _native_scan returning` changed from `LOG__GENERAL` to `LOG__DEBUG`
- [x] F5: `_normalize_mac()` validates MAC format and extracts from D-Bus paths
- [x] F6: SIGPIPE handler added to `cli.py:main()`
- [x] Tests: 54/54 AoI tests pass, 192/192 broader tests pass (1 pre-existing preflight failure excluded)
- [x] Documentation: changelog, todo_tracker, learned-memories updated

---

## Audio profile activation, recording reliability & profile identity fixes (2026-04-21) – COMPLETE

**Goal**: Close the behavioural gaps catalogued in
`workDir/Audio/README.audio-troubleshooting-once-more` — divergent
`audio-profiles` output between connect paths, `"Active Profile: off"`
mis-reporting, `[-] Recording failed` false negatives, HSP capture
nodes mis-classified as A2DP Source, and inconsistent BlueZ
`bluez_card.*` presence.

**Five fixes, all covered by `tests/test_audio_regressions.py`**:

| # | Scope | Files | Validation |
|---|-------|-------|------------|
| 1 | Opt-in BlueZ profile activation after RFCOMM bring-up; `--no-profiles` CLI flag on `bleep classic-connect` / `bleep connect` / `bleep pair` | `bleep/pairing/__init__.py`, `bleep/modes/pair.py`, `bleep/modes/classic_connect.py`, `bleep/cli.py` | `test_fix1_svc_map_has_audio_uuid_accepts_both_forms`, `test_fix1_activate_profiles_false_skips_device_connect`, `test_fix1_activate_profiles_true_calls_device_connect_only_for_audio` |
| 2 | `get_profiles_for_card` regex widening + pattern/name normalisation in `identify_bluetooth_profiles_from_alsa` | `bleep/ble_ops/audio/audio_tools.py` | `test_fix2_regex_accepts_hyphenated_profiles`, `test_fix2_pattern_normalisation_matches_hyphen_and_underscore` |
| 3 | `amusica status` surfaces Active profile explicitly | `bleep/modes/amusica.py` | `test_fix3_amusica_status_prints_active_profile` |
| 4 | `record_from_source` uses `Popen`+`SIGINT` timebox with WAV-header success guard and stderr DEBUG capture | `bleep/ble_ops/audio/audio_tools.py` | `test_fix4_record_returns_true_on_sigint_with_valid_output`, `test_fix4_record_returns_false_on_empty_output` |
| 5 | `pw-dump` `api.bluez5.profile` / `codec` / `device.profile.name` extraction; classifier prefers props over node-name | `bleep/ble_ops/audio/audio_tools.py` | `test_fix5_pw_dump_bluez5_props_are_extracted`, `test_fix5_classifier_prefers_bluez5_profile_over_node_name` |

Resolution narrative and manual verification recipe are documented in
the "Resolution Notes (2026-04-21)" section of
`workDir/Audio/README.audio-troubleshooting-once-more`.
Changelog entry: `bleep/docs/changelog.md` → "Audio profile activation,
recording reliability & profile identity fixes (2026-04-21)".

---

## MediaEndpoint1 Contention Pre-flight (2026-04-17) – COMPLETE

**Goal**: Before `MediaStreamManager._acquire_via_endpoint()` registers a
BLEEP-owned `MediaEndpoint1` and cycles the device connection, detect whether
another endpoint provider (BlueALSA, PipeWire bluez5 SPA plugin, or PulseAudio
`module-bluetooth-discover`) has already claimed the complement role.  When a
competing endpoint is registered, BlueZ's `a2dp_select_eps` frequently picks
the pre-existing endpoint during AVDTP re-discovery, so BLEEP's `SetConfiguration`
callback is never invoked and `wait_for_transport()` times out.

**Symptom**: Terminal logs show:

* BlueZ is happy, device is `Connected=yes`, profile list includes A2DP.
* `audioplay` hangs for 15 s and emits the timeout raised from
  `_acquire_via_endpoint`.
* `bluealsa-cli list-pcms` (or `pw-cli list-objects | grep bluez_output`) shows
  the complement profile already claimed by another daemon.

**Design outline** (refined 2026-04-17 after the structured-status /
BlueALSA-correlator diagnostic landed):

Two-layer probe.  BlueZ's `GetManagedObjects()` returns *BlueZ-owned* objects
only (remote-device SEPs at `/org/bluez/hciN/dev_.../sepN`, transports at
`.../fdN`); it does **not** republish externally registered `MediaEndpoint1`
objects.  Those live on the registering client's bus name under whatever path
the client chose (BLEEP: `/bleep/media/endpoint`; BlueALSA: `/org/bluealsa/…`;
PipeWire: `/MediaEndpoint/…`).  Enumeration therefore walks D-Bus *names*, not
BlueZ managed objects.

1. **Primary probe — zero-cost inference.**  Reuse
   `_check_bluetooth_audio_stack_detailed()` (structured per-backend status)
   and `AudioToolsHelper.list_bluealsa_pcms()` (MAC-scoped BlueALSA PCMs).
   Any backend whose `status == "active"` is synthesised as an
   `EndpointOwner` for each complement UUID that backend is known to register
   by default (A2DP Source + A2DP Sink + HFP AG + HFP HF for all three
   backends).  This alone is sufficient to pre-empt the 15 s timeout in every
   deployment we have observed in terminal logs.
2. **Deep probe (opt-in, `deep_probe=True`).**  Authoritative enumeration via
   `org.freedesktop.DBus.ListNames` → per-name `Introspect` for
   `<interface name="org.bluez.MediaEndpoint1">` → `GetConnectionUnixProcessID`
   → `/proc/<pid>/comm` / `cmdline`.  Every call goes through
   `bleep.dbus.timeout_manager.call_method_with_timeout` so the scan cannot
   hang.  Runs only when the caller explicitly requests it
   (`audiocfg --endpoints`, `mediaenum --endpoints`) or when the primary probe
   is ambiguous.
3. **Classify severity.**
   * `"block"` — BlueALSA daemon `active` and the complement UUID is one
     BlueALSA always claims.  BlueZ will race-lose against BlueALSA with very
     high probability (observed failure mode).
   * `"warn"` — `_detect_audio_stack_conflicts()` emitted a warning, or the
     deep probe found ≥1 non-BLEEP competitor.
   * `"info"` — only BLEEP itself owns the complement UUID.
   * `"none"` — no audio backends active.
4. **Runtime gate.**  Insert the primary probe at the top of
   `MediaStreamManager._acquire_via_endpoint` (after `complement_uuid` is
   computed, before `BleepMediaEndpoint.register()`).  On `severity == "block"`
   and without `force_endpoint=True`, raise before registering/cycling (saves
   15 s + a device disconnect).  On `"warn"`, print and proceed.  The
   existing `wait_for_transport` timeout message re-injects the report when
   the primary probe missed the conflict.
5. **User overrides.**  New `--force-endpoint` flag on `audioplay`,
   `audiorec` (debug shell + CLI) bypasses the gate.
6. **Surfaces.**  `audiocfg` prints a new "Endpoint contention" section (fast
   path by default; `--endpoints` enables the deep probe).  `mediaenum`
   annotates printed endpoints with owner attribution when `--endpoints` is
   passed.  `audio-recon` emits a one-line summary.
7. **Tests.**  Extend `tests/test_preflight.py`: primary probe (monkeypatched
   backend snapshots), deep probe (monkeypatched `SystemBus` + canned
   introspection XML for fake bus names), runtime gate (spy on
   `BleepMediaEndpoint` instantiation), `--force-endpoint` override.

Implementation gate (why this was deferred until now): the structured
`audiocfg` diagnostic and BlueALSA correlator had to ship first so real
failure reports could inform the edge cases (multi-adapter hosts, partial
BlueALSA/PipeWire coexistence).  Those shipped 2026-04-17 and are validated;
this item may now proceed.

| # | Deliverable | Status | Files |
|---|-------------|--------|-------|
| 1 | `EndpointOwner` / `EndpointContentionReport` dataclasses + primary probe | [x] | `bleep/core/preflight.py` |
| 2 | Deep probe (`ListNames` + `Introspect` + PID attribution, timeout-guarded) | [x] | `bleep/core/preflight.py`, uses `bleep/dbus/timeout_manager.py` |
| 3 | `MediaStreamManager` pre-flight gate + `force_endpoint` override + amended timeout error | [x] | `bleep/dbuslayer/media_stream.py` |
| 4 | Debug-shell + CLI surfaces (`audiocfg --endpoints`, `mediaenum --endpoints`, `--force-endpoint`) | [x] | `bleep/modes/debug_media.py`, `bleep/cli.py` |
| 5 | `audio-recon` one-line contention summary | [x] | `bleep/ble_ops/audio/audio_recon.py` |
| 6 | Unit tests (primary, deep, runtime gate, override) | [x] | `tests/test_preflight.py` (9 new tests) |
| 7 | Changelog + this entry status + audio/d-bus doc updates | [x] | `bleep/docs/changelog.md`, `bleep/docs/todo_tracker.md` |

---

## MAP CLI Folder Enumeration Fix (2026-04-15) – COMPLETE

**Goal**: Fix the `classic-map folders` and `classic-map list` CLI commands so they correctly enumerate the full MAP folder hierarchy on devices with deep structures (e.g. `telecom/msg/{inbox,draft}`) and gracefully handle non-leaf folder access.

**Root cause**: The CLI `folders` action called the flat `list_folders()` (single `ListFolders` at the MAP root) instead of the recursive `list_folder_tree()` that already existed and was used by the debug-mode `cmap folders` command.  The CLI `list` action had no recovery logic for "Bad Request" errors from non-leaf folders, unlike its debug-mode counterpart.

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | `cli.py` `folders` action re-wired to `list_folder_tree()` + `collect_leaf_paths()` with indented tree output | [x] |
| 2 | `cli.py` `list` action "Bad Request" recovery: enumerate tree, suggest valid leaf paths | [x] |
| 3 | Future work item for auto-resolve intermediate folders added to todo_tracker | [x] |
| 4 | Changelog updated with Unreleased entry | [x] |

---

## Classic Connect CLI & Debug Fix (2026-03-31) – COMPLETE

**Goal**: Add a working Bluetooth Classic connection path that bypasses the `Device1.Connect()` profile-handler requirement, both as a new `bleep classic-connect` CLI command and as fixes to the debug mode `connect`/`cconnect` commands.

**Root cause**: BlueZ `Device1.Connect()` only succeeds when a profile handler is registered for at least one of the remote device's services.  For devices exposing raw RFCOMM services without a BlueZ profile handler, it fails with `br-connection-profile-unavailable`.  The working path is SDP discovery + raw RFCOMM socket.

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | `classic_connect_sdp_rfcomm()` shared helper in `bleep.pairing` | [x] |
| 2 | `bleep classic-connect` CLI command (`modes/classic_connect.py` + `cli.py` subparser) | [x] |
| 3 | Debug `cconnect` — SDP+RFCOMM fallback when `Device1.Connect()` fails | [x] |
| 4 | Debug `connect` → `_connect_classic` — pass `debug_state` to `_c_enum` | [x] |
| 5 | `bleep connect` — auto-detect Classic transport and route to classic-connect | [x] |
| 6 | `connect_and_enumerate__bluetooth__classic` — skip redundant auto-pair for already-paired devices | [x] |
| 7 | Documentation: changelog, debug_mode, todo_tracker | [x] |

---

## Pairing CLI Expansion (2026-03-31) – COMPLETE

**Goal**: Augment BLEEP pairing capabilities with a first-class `bleep pair` CLI command, pre-pair status checks, forced bond reset, and eliminate duplicated pairing helpers across modules.

**Status**: Complete.

### Deliverables

- [x] **P1** `bleep/pairing/__init__.py` — Shared pairing helpers: `find_device_path`, `resolve_device_for_pair`, `remove_stale_bond`, `register_pair_agent`, `check_pair_status`, `report_pair_status`
- [x] **P2** `bleep/modes/pair.py` — New CLI handler for `bleep pair` with full flag parity to the debug-mode `pair` command
- [x] **P3** `bleep/cli.py` — Registered `pair` subparser and dispatch
- [x] **P4** `bleep/modes/debug_pairing.py` — Refactored to import from `bleep.pairing`; added `--check` and `--reset` flags; pre-pair status check before pairing
- [x] **P5** `bleep/dbuslayer/device_classic.py` — Added `is_paired()`, `is_trusted()`, `is_bonded()`, `is_connected()` for API parity with LE wrapper
- [x] **P6** `bleep/dbuslayer/pin_brute.py` — `_remove_stale_bond` delegates to shared `bleep.pairing.remove_stale_bond`
- [x] **P7** `bleep/ble_ops/classic/connect.py` — `_do_auto_pair` uses shared `register_pair_agent` and `find_device_path`
- [x] **P8** `bleep/modes/agent.py` — `_get_device_path` delegates to shared `resolve_device_for_pair`
- [x] **P9** Documentation updated: `changelog.md`, `debug_mode.md`, `pairing_agent.md`, `todo_tracker.md`

---

## MAP bMessage Format Reference & Test Corpus (2026-03-30) – COMPLETE

**Goal**: Document the MAP bMessage envelope specification, validate the LENGTH calculation rules against the live codebase, create a comprehensive test message corpus covering all MAP message types and structural variations, and produce tooling for batch validation and push operations.

**Status**: Complete.

### Deliverables

- [x] **D1** `bleep/docs/map_bmessage_format.md` — Full bMessage format reference with inline examples for all 5 types: envelope structure, LENGTH calculation, nested BENV for forwarded messages, bulk operation analysis, PushMessage args, ListMessages filter fields, implementation code-path table
- [x] **D2** `bleep/docs/bl_classic_mode.md` §2.9 updated with bMessage format summary, bulk operation notes, cross-reference to new doc
- [x] **D3** `bleep/docs/README.md` TOC updated with MAP bMessage format reference link
- [x] **D4** `bleep/docs/changelog.md` Unreleased section updated with format reference entry

### Key findings

- **One file = one message**: `PushMessage` accepts exactly one bMessage file per call; no batch upload in the MAP spec. Multiple `BEGIN:BMSG` blocks in a single file are not valid.
- **Nested BENV**: Forwarded/attached messages use nested `BEGIN:BENV`/`END:BENV` blocks, each with its own VCARD and BBODY/LENGTH.
- **LENGTH precision**: The `LENGTH:` field must match the exact byte count from `BEGIN:MSG\r\n` through `END:MSG\r\n` inclusive (CRLF required). Mismatches cause silent device-side rejection despite successful OBEX transfer. BLEEP now auto-normalizes LF→CRLF and recalculates LENGTH before every push.
- **Bulk download**: Enumerate folders → list messages per folder → get each handle. Scriptable via `bleep.ble_ops.classic.map` API.
- **PushMessage args**: `Transparent`, `Retry`, `Charset` are defined in the BlueZ API but not currently exposed by BLEEP (empty dict passed).

---

## MAP Bulk Download & Upload Commands (2026-03-30) – COMPLETE

**Goal**: Implement `cmap download-all` and `cmap push-all` debug commands with corresponding operations-layer API (`download_all_messages`, `push_all_messages`), and refactor `_collect_leaf_paths` from the debug layer into the operations layer as a public utility.

**Status**: Complete.

### Deliverables

- [x] **D1** `bleep/ble_ops/classic/map.py` — `collect_leaf_paths()` public utility (moved from debug layer)
- [x] **D2** `bleep/ble_ops/classic/map.py` — `download_all_messages()` with folder tree walk, per-folder session, pagination support, progress callback
- [x] **D3** `bleep/ble_ops/classic/map.py` — `push_all_messages()` with bMessage validation, dry-run, continue-on-error, progress callback
- [x] **D4** `bleep/modes/debug_classic_obex.py` — `cmap download-all [dest] [--folders] [--count N]` sub-command
- [x] **D5** `bleep/modes/debug_classic_obex.py` — `cmap push-all <dir|glob> [folder] [--dry-run]` sub-command
- [x] **D6** `bleep/modes/debug_classic_obex.py` — `_collect_leaf_paths` now delegates to `map.collect_leaf_paths`
- [x] **D7** `bleep/docs/map_bmessage_format.md` §7 updated with debug commands and API examples; §11 table updated
- [x] **D8** `bleep/docs/bl_classic_mode.md` §2.9 updated with download-all/push-all usage examples
- [x] **D9** `bleep/docs/changelog.md` Unreleased section updated

### Design decisions

- **One session per folder for download**: `_populate_message_objects` creates D-Bus message objects within the calling session; handles are only valid within that session. Opening one `MapSession` per folder and downloading all messages before moving to the next avoids stale object paths.
- **One session per push for upload**: Keeps the existing `push_message` session-per-call pattern for maximum device compatibility; OBEX sessions can become stale after a push.
- **Continue-on-error**: Both bulk operations log per-item failures and continue the batch, matching the `cmap peek` pattern.
- **`.bmsg` extension**: Downloaded files use `.bmsg` for immediate round-trip compatibility with `push-all`.

---

## MAP bMessage CRLF Normalization & LENGTH Fix (2026-03-30) – COMPLETE

**Goal**: Fix silent push failures caused by bMessage files using LF line endings and LF-based LENGTH values, which are silently rejected by the remote Message Access Server despite OBEX transfer success.

**Status**: Complete.

### Root cause

The MAP specification mandates CRLF (`\r\n`) line endings. Test bMessage files and user-crafted files used bare LF (`\n`), causing the LENGTH field to undercount once the MAS expected CRLF. BlueZ's `obexd` passes file content as-is via `obc_transfer_put` — it does not normalize line endings. The MAS silently discards messages with incorrect LENGTH or non-CRLF formatting even when the OBEX transfer itself succeeds.

### Deliverables

- [x] **D1** `bleep/ble_ops/classic/map.py` — `normalize_bmessage(raw)` helper: converts bare LF→CRLF, recalculates all LENGTH fields (including nested BENV blocks)
- [x] **D2** `bleep/ble_ops/classic/map.py` — `_normalize_for_push(filepath)` temp-file wrapper integrated into `push_message()`, covering all push paths (single, batch, CLI)
- [x] **D3** `bleep/modes/debug_classic_obex.py` — `_validate_bmsg_length()` updated to warn about LF-only line endings and inform user about auto-normalization
- [x] **D4** `bleep/ble_ops/classic/map.py` — `push_all_messages()` dry-run path now reports whether each file will be normalized
- [x] **D5** `workDir/MAP/map_test_messages/*.bmsg` — All 10 test files converted to CRLF with correct LENGTH values
- [x] **D6** `bleep/docs/map_bmessage_format.md` §5 corrected: CRLF requirement documented, LF references removed, normalization chain documented
- [x] **D7** `bleep/docs/changelog.md` updated with fix entries

### Evidence

- Real messages downloaded from Samsung device via `cmap download-all` use CRLF and correct LENGTH (confirmed via hex dump)
- BlueZ `obexd/client/map.c` and `transfer.c` pass file content without modification to the OBEX layer
- BlueZ `test/map-client` reference implementation does not normalize line endings

---

## MAP push-all Session Exhaustion Fix (2026-03-30) – COMPLETE

**Goal**: Prevent transient OBEX session-creation timeouts when `cmap push-all` pushes many files in rapid succession.

**Status**: Complete.

### Root cause

Each `push_message()` call creates and tears down a `MapSession` (OBEX session).  When 8+ pushes execute back-to-back with no inter-push delay, `obexd` (or the remote MAS) fails to release the prior session's resources before the next `CreateSession` call, producing `org.bluez.obex.Error.Failed: Timed out waiting for response`.  The BlueZ reference `test/map-client` is interactive (inherent human delay), so this condition never occurs in the reference implementation.

### Deliverables

- [x] **D1** `bleep/ble_ops/classic/map.py` — `push_all_messages()` gains a `delay` parameter (default 1.5s) that inserts a cooldown between consecutive pushes
- [x] **D2** `bleep/ble_ops/classic/map.py` — Automatic single-retry with 3s backoff on transient session-creation timeouts
- [x] **D3** `bleep/modes/debug_classic_obex.py` — `cmap push-all` gains `--delay N` flag
- [x] **D4** `bleep/docs/map_bmessage_format.md` §7 updated with delay/retry documentation
- [x] **D5** `bleep/docs/changelog.md` updated with fix entry

---

## BLEEP v2.8.0 — Augmentation, Expansion, and Improvement Plan (2026-03-25) – IN PROGRESS

**Goal**: Deliver the v2.8.0 feature set as specified in `workDir/BigMoves/README.v2.8.0`. Work is organised into Pre-Work (v2.7.x finalization), Main Work (ten feature areas), a Bonus objective (audio capture & transcription), and Final Work (documentation, review, changelog).

**Version**: `bleep/__init__.py` at `2.8.0` — all Pre-Work, Main Work (M1–M10), Bonus, and Final Work complete.

**Pre-Work Status**: All P0 tasks completed (2026-03-26). Additionally: backward-compat stubs removed (all imports use canonical subpackage paths), schema version persistence bug fixed.

### Dependency Graph

```
Pre-Work (P0-1 through P0-9) — all independent, can parallelize
    │
    ├── P0-2 (cconnect GLib fix) follows pair --interactive lessons
    ├── P0-8 (ble_ops reorg) should complete before M1–M10
    ├── P0-9 (dual scan) — new for v2.8.0
    │
    v
Main Work — with dependencies:
    M3 (Agent PIN list, downgrade) ← M1 Stage 3 (PIN guessing)
    M6 (ALSA config) ← M1 Stage 4 (record/play config)
    M2 (RFCOMM probe, builds on existing SDP)
    M7.3 (RFCOMM binding) depends on M2 (RFCOMM probe)
    M5 (Device ID, uses bt_ref/uuids.py internally) — self-contained
    │
    v
Bonus (Audio Capture/Routing) — depends on M6 (capture/ALSA routing only; transcription is self-contained)
    │
    v
Final Work (F1–F3)
```

**Known test devices for acceptance validation** (from README.v2.8.0):
- `CC:50:E3:B6:BC:A6` — BLE CTF (no pairing, GATT services/characteristics)
- `D8:3A:DD:0B:69:B9` — Classic BT (requires PIN "12345", SDP enumeration)
- `53:4A:52:FE:01:38` — Audio device (media playback control, audio streaming)

---

### P0-1: Code, Variable, and Database Cleanup

**Status**: Done

**Existing structures**:
- Schema v10 in `bleep/core/observations.py` (line 55, `_SCHEMA_VERSION = 10`)
- MAC normalization via `_normalize_mac()` → `.upper()` (lines 511–524)
- v7→v8 migration uppercases MACs across all FK tables (lines 385–404)
- v8→v9 migration uppercases UUIDs
- FK protection via `_ensure_device_exists` on most upsert paths
- `safe_db_operation` retry decorator in `bleep/analysis/aoi_analyser.py` (lines 41–76)

**Remaining gaps to close**:
- [x] Audit media snapshot paths: added `_ensure_device_exists(cur, row["mac"])` to `snapshot_media_player()` and `snapshot_media_transport()` in `observations.py`
- [x] Extended CLI MAC normalization in `cli.py main()` to cover `pair`, `trust`, `untrust`, `remove_bond`, `source`, `sink` arguments
- [x] Add `characteristics`, `descriptors`, `device_type_evidence` to the table list in `maintain_database()` (confirmed present at line ~1306 in `observations.py`)
- [x] Fix pre-existing issue: `classic-scan` debug branch `d["class"]` → `d["device_class"]` (fixed in P0-1, confirmed in changelog v2.7.40)
- [x] Fix pre-existing issue: `bleep/modes/scratch.py` `timeout=` → `timeout_connect=` (fixed in P0-1, confirmed in changelog v2.7.40)
- [x] Ensure no loss of existing functionality after all cleanup

**Expected outcome**: Zero FK constraint failures under normal operation; uniform uppercase MACs from CLI through DB; complete maintenance reporting.

---

### P0-2: `cconnect` Blocking and GLib MainLoop Alignment

**Status**: Done

**Lesson from `pair --interactive`** (established pattern in `bleep/modes/debug_pairing.py` `_cmd_pair_single`):
1. `stop_glib_mainloop(state)` — free the default `MainContext` from the background daemon thread
2. Register the pairing agent on the main thread
3. `PairingAgent.pair_device()` runs a temporary `GLib.MainLoop` on the **main thread** (`bleep/dbuslayer/agent.py` line ~1048), which reliably dispatches `RequestPinCode` / `RequestPasskey` callbacks
4. `ensure_glib_mainloop(state)` — restart background loop for normal shell operation

**Why backgrounding `cconnect` is wrong**: Documented in `bleep/docs/agent_dbus_communication_issue.md` and `bleep/docs/mainloop_requirement_analysis.md` — `dbus.service.Object` method dispatch does **not** work when the `MainLoop` is only on a background thread. Agent callbacks would fail, breaking any auto-pair step.

**Current problem in `cconnect`** (`bleep/modes/debug_classic.py` line ~81):
- Calls `connect_and_enumerate__bluetooth__classic` which may internally call `ensure_default_pairing_agent()` + `device.pair()` without stopping the background GLib loop
- Agent dispatch during auto-pair is therefore unreliable
- The synchronous blocking of connection + SDP is **acceptable** — it reflects the reality of Classic BT operations

**Plan**:
- [x] Apply GLib stop/restart **only when pairing is needed**: detect when `connect_and_enumerate__bluetooth__classic` calls `ensure_default_pairing_agent()` / `device.pair()` and wrap that specific section with `stop_glib_mainloop(state)` / `ensure_glib_mainloop(state)`. When the device connects without pairing (no agent dispatch needed), skip the GLib stop/restart to avoid unnecessary churn and potential signal-handling disruption.
- [x] Investigate whether `classic_connect.py`'s internal auto-pair should use `PairingAgent.pair_device()` (temp main-thread loop) instead of `ClassicDevice.pair()` (blocking `Pair()` D-Bus call) for reliable agent dispatch
- [x] Add progress messages at each stage of `connect_and_enumerate__bluetooth__classic`:
  - `[*] Scanning for {mac}... (attempt {n}/{max})`
  - `[*] Connecting to {mac}...`
  - `[*] Pairing required — invoking agent...`
  - `[*] Running SDP discovery...`

**Expected outcome**: `cconnect` auto-pair works as reliably as `pair --interactive`; GLib stop/restart only applied when agent dispatch is needed; user has visibility into progress during synchronous operations.

---

### P0-3: Expand `pbap` Error Handling for "Transport got disconnected"

**Status**: Done

**Current state**: `cmd_pbap` in `bleep/modes/debug_classic.py` (line ~395) and CLI `classic-pbap` in `bleep/cli.py` (line ~1549) call `pbap_dump_async` from `bleep/ble_ops/classic/pbap.py`. Error handling uses `result.get("error")` and `print_detailed_dbus_error` but does not match `org.bluez.obex Error Failed: Transport got disconnected`.

**Plan**:
- [x] In `bleep/ble_ops/classic/pbap.py`, add specific detection of `"Transport got disconnected"` in the error string
- [x] Print actionable message: `[!] OBEX transport disconnected — the target device may not have 'Contact Sharing' enabled (check Bluetooth settings on the device).`
- [x] Mirror the same hint in `cmd_pbap` (debug mode) and CLI `classic-pbap` handler

**Expected outcome**: Users see a clear, actionable message directing them to enable Contact Sharing on the target device.

---

### P0-4: BlueALSA API Call Uniformity (`bluealsa-cli` vs `bluealsactl`)

**Status**: Done

**Current state**: Only `bluealsa-cli` is used — `bleep/core/preflight.py` (`shutil.which("bluealsa-cli")`) and `bleep/ble_ops/audio/audio_tools.py` (`self._bluealsa_cli_path`). Zero occurrences of `bluealsactl`. BlueALSA >= 4.0 renamed `bluealsa-cli` to `bluealsactl`.

**Plan**:
- [x] In `bleep/ble_ops/audio/audio_tools.py`, make the tool name resolve via fallback chain: `shutil.which("bluealsactl")` first, then `shutil.which("bluealsa-cli")`
- [x] Update `bleep/core/preflight.py` to check for either binary and report which was found
- [x] No functional changes to how the tool is invoked (same CLI arguments)

**Expected outcome**: BLEEP works with both older (`bluealsa-cli`) and newer (`bluealsactl`) BlueALSA installations.

---

### P0-5: Consistent CLI Adapter Reporting

**Status**: Done

**Current state** — inconsistent adapter guards:
- `bleep/cli.py` connect: catches `NotReadyError` → `"[!] Bluetooth adapter not ready"` (line ~617)
- `bleep/cli.py` classic-scan: checks `adapter.is_ready()` (line ~1192)
- Debug mode BLE: no explicit adapter guard before opening the shell
- Debug `cscan`: checks `adapter.is_ready()`
- Debug `cconnect`: surfaces as failed connect error, not clear adapter message

**Plan**:
- [x] Create `require_adapter(adapter_name=None)` in `bleep/core/preflight.py` — reuses `adapter.is_ready()`, raises `NotReadyError` with human-readable message
- [x] Apply at: debug shell startup (`bleep/modes/debug.py` `main()`), `cmd_cconnect`, `cmd_cscan`, and all CLI Bluetooth subcommands in `bleep/cli.py`

**Expected outcome**: Every BLEEP entry point that requires a Bluetooth adapter provides a uniform `[!] Bluetooth adapter not found or not ready` message.

---

### P0-6: BLE Debug Mode `services` Caching

**Status**: Done

**Current state**: `cmd_services` in `bleep/modes/debug_gatt.py` (line ~98) calls `state.current_device.services_resolved()`. If `is_services_resolved()` is `False`, logs and returns `[]` — no retry, no resolve trigger, no in-memory cache for later commands.

**Plan**:
- [x] In `cmd_services`, if `is_services_resolved()` is `False`, attempt `connect()` if not connected, then poll `ServicesResolved` D-Bus property for up to 10s
- [x] On success, store the result in `state.current_mapping` for reuse by subsequent commands
- [x] Add `--refresh` flag to force re-enumeration even when cached mapping exists

**Expected outcome**: `services` resolves proactively, caches in `DebugState`, re-enumerates only on `--refresh`.

---

### P0-7: Classic `cpan status` Freshness

**Status**: Done

**Current state**: `cmd_cpan` `status` in `bleep/modes/debug_classic_profiles.py` (line ~56) calls `pan_status(mac)` from `bleep/ble_ops/classic/pan.py`, which queries D-Bus `org.bluez.Network1` properties.

**Investigation result**: `classic_pan.py` `status()` calls `NetworkClient` which uses `dbus.Interface(..., DBUS_PROPERTIES).Get(...)` per property — these are live D-Bus reads, not a Python-side cache. If staleness is observed, the cause is BlueZ not updating `Network1` properties until an event triggers refresh, not application-side caching.

**Plan**:
- [x] Replace three separate `Get()` calls with a single `GetAll("org.bluez.Network1")` for atomicity (avoids race between individual property reads)
- [x] If the issue persists after atomicity fix, document as a BlueZ limitation

**Expected outcome**: `cpan status` uses atomic property read; staleness from BlueZ itself is documented as a known limitation.

---

### P0-8: Re-organize `ble_ops` into `le/`, `classic/`, `common/`, `audio/`

**Status**: Done

**Current state**: `bleep/ble_ops/` contains 32 files mixing LE-specific (`scan.py`, `connect.py`, `reconnect.py`, `brute.py`, `enum_*.py`, `ctf*.py`), Classic-specific (`classic_*.py` — 12 files), shared (`conversion.py`, `uuid_utils.py`, `modalias.py`, `structural.py`), and audio (`amusica.py`, `audio_*.py` — 6 files).

**Plan**:
```
bleep/ble_ops/
├── __init__.py          # re-exports all current public symbols for backward compat
├── common/
│   ├── __init__.py
│   ├── conversion.py
│   ├── uuid_utils.py
│   ├── modalias.py
│   └── structural.py
├── le/
│   ├── __init__.py
│   ├── scan.py, scan_modes.py, connect.py, reconnect.py
│   ├── brute.py, enum_controller.py, enum_helpers.py
│   └── ctf.py, ctf_discovery.py
├── classic/
│   ├── __init__.py
│   ├── connect.py, sdp.py, pbap.py, opp.py, ftp.py
│   ├── map.py, pan.py, spp.py, ping.py, version.py
│   ├── bip.py, sync.py
│   └── rfcomm.py          # NEW for M2
└── audio/
    ├── __init__.py
    ├── amusica.py, audio_tools.py, audio_codec.py
    ├── audio_recon.py, audio_system.py
    └── audio_profile_correlator.py
```

**Migration strategy (completed)**:
- [x] Moved 32 files into `le/`, `classic/`, `common/`, `audio/` subdirectories
- [x] `bleep/ble_ops/__init__.py` re-exports core public symbols from new locations
- [x] Updated ~181 import sites across 62 files (`cli.py`, `modes/*.py`, `dbuslayer/*.py`, `analysis/*.py`, `scripts/*.py`, `tests/*.py`, `workDir/Functions/*.py`) to canonical subpackage paths
- [x] Backward-compat stub modules initially created, then **removed** — all imports now use canonical paths
- [x] Verified with `python3 -c "from bleep.ble_ops import *"` and compile checks
- [x] No functional changes — pure restructure

**Outcome**: Clean separation of LE, Classic, shared, and audio operations. All imports use canonical subpackage paths. Old flat paths raise `ModuleNotFoundError`.

---

### P0-9: Dual Device Scan Command (NEW)

**Status**: Done

**Current state**:
- `brute_scan` in `bleep/ble_ops/le/scan.py` (line ~787): sequential BR/EDR then LE (half timeout each)
- `scan_audio_targets` in `bleep/ble_ops/audio/amusica.py`: uses `{"Transport": "auto"}` for single-session combined discovery
- `discover_devices` in `bleep/core/device_management.py`: supports `transport_type="auto"`
- CLI `bleep scan`: has `--variant` (passive/naggy/pokey/brute) but **no** `--transport` flag
- Debug mode: `scan`/`scann`/`scanp`/`scanb` (LE-oriented) + `cscan` (Classic-only), no dedicated "both" command
- When `transport="auto"` in `_native_scan`, no `Transport` key is set in the discovery filter — may inherit stale filter state

**Plan**:
- [x] Add `--transport {auto,le,bredr}` flag to `bleep scan` in `bleep/cli.py`; default `auto`
- [x] For `_native_scan` with `transport="auto"`, explicitly set `{"Transport": "auto"}` in the discovery filter to avoid stale-filter dependence
- [x] Add `dscan [--timeout T]` command to Debug Mode in `bleep/modes/debug_scan.py` — runs `_native_scan(None, timeout, transport="auto")` with explicit filter. Note: this is distinct from `scanb` (brute_scan) which does **sequential** BR/EDR then LE in two phases; `dscan` uses a **single combined discovery session** via `Transport: "auto"`, which is less intrusive and interleaves both transports
- [x] Tag results with transport type: `[LE]`, `[BR/EDR]`, `[Dual]` per device using existing `get_device_transport()` from `bleep/analysis/device_type_classifier.py`

**Expected outcome**: Users run a single scan that discovers both LE and Classic devices in one session, with results labeled by transport type. `scanb` remains available as the "loud" sequential alternative.

---

### M1: Full Automatic Deployment of `amusica`

**Status**: Done | **Depends on**: M3 (done), M6 (done)

**Existing structures**:
- `bleep/ble_ops/audio/amusica.py`: `scan_audio_targets()`, `attempt_justworks_connect()`, `assess_targets()`, `summarise_assessment()`
- `bleep/modes/amusica.py`: CLI subcommands `scan`, `halt`, `inject`, `record`, `control`, `auto`
- `bleep/ble_ops/audio/audio_tools.py`: `AudioToolsHelper` — backend detection, play/record, BlueALSA PCM listing, `halt_audio_for_device()`
- `bleep/ble_ops/audio/audio_recon.py`: `run_audio_recon()`
- `bleep/ble_ops/audio/audio_system.py`: `system_play()`, `system_record()`
- `bleep/dbuslayer/pin_brute.py`: `PinBruteForcer` with lockout awareness
- `bleep/ble_ops/audio/amusica_orchestrator.py`: `run_amusica_full_auto()`, `analyze_recordings()`

**Five-stage autonomous pipeline**:
- [x] **Stage 1 — Scan & Classify**: Uses `scan_audio_targets()` with existing `_device_has_audio_uuids()` filter. Done.
- [x] **Stage 2 — Connection Test & Triage**: Uses `attempt_justworks_connect()` per target; splits into justworks / auth_required / profile_unavailable / failed. Done.
- [x] **Stage 3 — Optional PIN Guessing**: Uses `PinBruteForcer.run_pin_brute()` with `COMMON_PINS`. Gated by `--brute` flag. Configurable depth via `--brute-depth`. Done.
- [x] **Stage 4 — Record & Playback**: Halts existing audio via `halt_audio_for_device()`, runs `run_audio_recon()` per accessible target. Done.
- [x] **Stage 5 — Post-Test Analysis**: `analyze_recordings(paths)` uses `sox stat` + `soxi -D` for amplitude and duration analysis. Done.
- [x] New file: `bleep/ble_ops/audio/amusica_orchestrator.py` — `run_amusica_full_auto()`. Done.
- [x] New CLI subcommand: `bleep amusica auto [--brute] [--brute-depth N] [--timeout T] [--record-dir DIR] [--duration D] [--test-file FILE] [--out JSON]`. Done.

**Augmentations from roadmap review**:

- [x] **M1-aug-a**: `attempt_justworks_connect()` now detects `"profile unavailable"` / `"profileunavailable"` → distinct `"profile_unavailable"` outcome. Done.
- [x] **M1-aug-b**: `run_audio_recon()` now distinguishes `"no_matching_device"` (MAC filter miss) from `"device_not_available"` (no BT audio at all). Done.

**Expected outcome**: `bleep amusica auto` runs the complete 5-stage pipeline. Results printed as summary table with per-target breakdown. Profile-unavailable failures triaged distinctly from auth-required.

---

### M2: Identification of RFCOMM Channels

**Status**: Done | **Depends on**: P0-8 (done)

**Existing structures**:
- `bleep/ble_ops/classic/sdp.py`: `discover_services_sdp()` + `build_svc_map()` — full SDP/RFCOMM extraction
- `bleep/modes/debug_classic.py` `cmd_cservices`: prints structured per-service listing with RFCOMM channels
- `bleep/modes/debug_classic_rfcomm.py`: `copen`, `csend`, `crecv`, `craw` — raw RFCOMM I/O
- `bleep/ble_ops/classic/connect.py`: `classic_rfccomm_open()` — raw RFCOMM socket
- `bleep/dbuslayer/spp_profile.py`: SPP profile registration

**What's genuinely new — terminal/serial probing**:
- [x] New file: `bleep/ble_ops/classic/rfcomm.py` — `ProbeResult` dataclass + `probe_rfcomm_channel()` + `probe_all_channels()`. Reuses `classic_rfccomm_open()`. Sends `\r\n`, VT100 DA1 `\x1b[c`, passive SSH banner read. Classifies: `terminal`/`ssh`/`serial`/`data`/`closed`/`silent`. Done.
- [x] New CLI subcommand: `bleep classic-rfcomm <MAC> [--probe] [--timeout N] [--adapter]` — SDP discovery → formatted RFCOMM table → optional per-channel probe. Done.
- [x] New debug command: `crfcomm [--probe] [--timeout N]` — uses `state.current_mapping`, auto-discovers if empty. Done.

**Expected outcome**: ✅ RFCOMM channels are enumerated (existing), and optionally probed for terminal/serial interfaces (new).

---

### M3: Improved Agent Usage and Capabilities

**Status**: Done

**Existing structures**:
- `bleep/dbuslayer/agent.py`: `PairingAgent` with `register(capabilities=...)` supporting `NoInputNoOutput`, `DisplayOnly`, `KeyboardOnly`, `KeyboardDisplay`
- `bleep/dbuslayer/pin_brute.py`: `PinBruteForcer` — full brute-force orchestration with lockout awareness, accepts external `pin_iterator`/`passkey_iterator`
- `bleep/dbuslayer/agent_io.py`: `BruteForceIOHandler` — feeds candidates to agent callbacks
- Auth method is implicitly detectable (agent receives `RequestPinCode` vs `RequestPasskey` vs `RequestConfirmation`)

**What's genuinely new**:
- [x] **Common PIN/PassKey constants** in `bleep/bt_ref/constants.py`: `COMMON_PINS` (14 entries, structured by length: `COMMON_PINS_4` / `COMMON_PINS_6` / `COMMON_PINS_ALPHA`), `COMMON_PASSKEYS` (5 entries), `AGENT_CAPABILITIES` (5 entries). Wired as default iterators in `PinBruteForcer.run_pin_brute()` and `run_passkey_brute()` when no explicit list provided. Done.
- [x] **Capability downgrade cycling** — `attempt_downgrade_pair(bus, device_path)` in `bleep/dbuslayer/agent.py`. Cycles NoInputNoOutput → DisplayOnly → DisplayYesNo → KeyboardOnly → KeyboardDisplay, records auth method per attempt, stops on first success. Uses `AGENT_CAPABILITIES` constant. Done.
- [x] **Auth type reporting** — `last_auth_method` attribute on `BlueZAgent` base class, set in all 7 agent methods: `RequestPinCode`, `DisplayPinCode`, `RequestPasskey`, `DisplayPasskey`, `RequestConfirmation`, `RequestAuthorization`, `AuthorizeService`. Exposed via `get_last_auth_type() -> Optional[str]`. Done.
- [x] **Debug command**: `pair --probe <MAC>` — invokes `attempt_downgrade_pair()`, prints result table, cancels pairing if successful. Done.
- [x] **PIN/Passkey corrections** (v2.8.0-m6): Reviewed against BlueZ documentation (`org.bluez.Agent.rst`, `mgmt.rst`, `bluez/src/agent.c`, `bluez/emulator/smp.c`). Removed invalid empty-string PIN, added alphanumeric PINs, reordered capabilities for BR/EDR kernel conversion, added `DisplayPinCode` and `RequestAuthorization` auth tracking, documented SSP passkey brute-force infeasibility. Done.

**Expected outcome**: ✅ Agent tries common PINs by default (including alphanumeric), can cycle capabilities for downgrades, and reports the exact auth type for all 7 BlueZ agent methods.

---

### M4: Improved Preliminary Check of Connectivity

**Status**: Done | **Depends on**: P0 (done)

**Existing structures**:
- `bleep/dbuslayer/device_classic.py` `connect()`: checks `is_connected()` and skips if already connected (line ~155), BUT always calls `Disconnect()` first (line ~177) — contradicts the skip
- `bleep/dbuslayer/device_le.py`: `is_connected()`, `is_paired()`, `is_trusted()`
- `bleep/core/preflight.py`: checks tool binaries and BlueZ version — not live adapter state
- `bleep/dbuslayer/adapter.py`: `is_ready()`, accepts `bluetooth_adapter=` param; no `list_adapters()` API
- `--adapter` flag on `adapter-config` and `amusica` subcommands, not globally
- `bleep/core/errors.py`: `map_dbus_error()` — maps D-Bus exceptions to BLEEP exceptions; only handles a subset of BlueZ errors
- `bleep/core/error_handling.py`: `_DBUS_ERROR_NAME_MAP` / `_DBUS_MESSAGE_MAP` — partial BlueZ error coverage
- **BlueZ reference**: `workDir/BlueZDocs/errors.txt` defines 34 structured connection errors (17 BR/EDR, 17 LE); `workDir/BlueZDocs/org.bluez.Device.rst` documents `Connect()`, `Pair()`, `Disconnected` signal errors

**What's genuinely new**:
- [x] **M4-1: `check_device_state(bus, mac)`** in `bleep/core/preflight.py` — `DeviceState` dataclass + `check_device_state()` function queries LE/Classic `get_device_info()`. Done.
- [x] **M4-2: Fix Disconnect-Before-Connect contradiction** in `device_classic.py` — added `force_disconnect` param (default `False`); only disconnects when explicitly requested. Done.
- [x] **M4-3: Consistent adapter guard** — `require_adapter()` in `preflight.py` — **Done in P0-5**
- [x] **M4-4: `list_adapters()`** in `bleep/dbuslayer/adapter.py` — static method walks `Adapter1` paths from `GetManagedObjects()`. Done.
- [x] **M4-5: Broader `--adapter` flag** on CLI subcommands — added to `scan`, `connect`, `gatt-enum`, `enum-scan`, `classic-scan`, `classic-enum`, `classic-ping`, `explore`, `signal`, `agent`. Done.
- [x] **M4-6: Connection limit awareness** — `get_connected_devices()` on adapter returns list of connected MACs; `ConnectionLimitError` mapped from BlueZ `"concurrent connection limit"`. BlueZ does not expose a max connection count property — documented as platform limitation. Done.

**Augmentations from roadmap review** (source: `workDir/BigMoves/README.bleep-bleep-mcp-augmentation-roadmap.md` items S2, S8, 3.4):

- [x] **M4-new-a: `skip_pair_fallback` on LE connect** — `skip_pair_fallback: bool = False` parameter added to `connect_and_enumerate__bluetooth__low_energy()`. When `True`, auth exceptions re-raise instead of auto-pairing. Done.
- [x] **M4-new-b: Comprehensive BlueZ error mapping** — 13 new `RESULT_ERR_*` constants (28–40), 7 new `_DBUS_ERROR_NAME_MAP` entries, 26 new `_DBUS_MESSAGE_MAP` entries (all `br-connection-*` / `le-connection-*`), 8 new exception classes, 10+ new branches in `map_dbus_error()`. Done.
- [x] **M4-new-c: Human-readable error descriptions + disconnect reason map** — All new error codes added to `error_mapping` dict. `DISCONNECT_REASON_MAP` with 6 BlueZ reason strings added. Done.

**Expected outcome**: ✅ BLEEP never destroys existing connection/pairing unless explicitly requested. Multiple adapters can be listed and selected. Connection limits surfaced via `get_connected_devices()` and `ConnectionLimitError`. All 34 BlueZ connection errors mapped to structured BLEEP exceptions with human-readable descriptions. LE connect supports opt-out of auto-pair fallback.

---

### M5: Improved Device Identification (Using Internal BT SIG Data)

**Status**: Done

**Existing structures**:
- `bleep/bt_ref/update_ble_uuids.py`: fetches from BT SIG Bitbucket → writes `bleep/bt_ref/uuids.py`
- `bleep/bt_ref/uuids.py` (auto-generated): `SPEC_ID_NAMES__COMPANY_IDENTS`, `SPEC_ID_NAMES__ADVERTISING_TYPES`, `SPEC_ID_NAMES__APPEARANCE_VALUES`
- `bleep/bt_ref/bluetooth_uuids.py`: legacy snapshot — **deprecated** with DeprecationWarning as of v2.8.0-m5

**Plan**:
- [x] **Manufacturer ID → Company Name**: `_resolve_company_name()` in `common/conversion.py` resolves 16-bit company IDs via `SPEC_ID_NAMES__COMPANY_IDENTS`. ManufacturerData display now shows "0x004c (76) — Apple, Inc.". Done.
- [x] **Fix `common/modalias.py` import**: `decode_pnp_id_vendor()` now imports from `bleep.bt_ref.uuids`. Done.
- [x] **AD Type name resolution**: `_resolve_ad_type_name()` resolves AD type codes. AdvertisingData display now shows "Type: 0x01 (1) — Flags". Done.
- [x] **Appearance consolidation**: `_resolve_appearance_sig()` resolves through SIG category/subcategory hierarchy, `decode_appearance()` tries hardcoded map first, then SIG table fallback. Done.
- [x] **Windows/CDP detection**: Microsoft CDP UUID `0000FE05-...` detected by `LEServiceDataCollector` in `device_type_classifier.py`. Done.
- [x] **Deprecate `bluetooth_uuids.py`**: All imports redirected to `uuids.py`; DeprecationWarning added to legacy file. Done.

**Augmentations**:
- [x] **M5-aug-a**: `_determine_device_type()` in `adapter.py` now passes `service_data`, `advertising_data`, `manufacturer_data`, `appearance` to classifier context. Done.
- [x] **M5-aug-b**: `LEServiceDataCollector` in `device_type_classifier.py` with `_BEACON_SERVICE_DATA_UUIDS` (Find My, EN v1/v2, CDP, NearbySharing). Done.
- [x] **M5-aug-c**: Vendor UART heuristics via `_VENDOR_UART_UUIDS` (FFE0, FFE1, FFF0, FFF1, Nordic UART) as `WEAK` evidence. Done.
- [x] **M5-aug-d**: `evidence_source` field on `ClassificationResult` — `"heuristic"` / `"measured_sdp"` / `"measured_gatt"` / `"cached"`. `_determine_evidence_source()` + cached result path. Done.
- [x] **M5-aug-e**: ServiceData UUID→name already handled by existing `get_name_from_uuid()` in `format_device_info_block()`. Verified. Done.

**Expected outcome**: ✅ All device identification uses self-contained, SIG-updatable data. Classifier receives full advertisement context. Evidence is labeled by source. Known beacons and vendor UARTs are identified.

---

### M6: Augment (Re)Configuration of Linux Host OS Bluetooth File(s)

**Status**: Done

**Existing structures**:
- `bleep/ble_ops/audio/audio_tools.py` `AudioToolsHelper`: runtime ALSA/BlueALSA detection, enumeration (`aplay -l`/`arecord -l`), PCM listing, play/record helpers — no config file writing
- `bleep/modes/adapter_config.py`: BlueZ adapter D-Bus + `bluetoothctl mgmt` + `/etc/bluetooth/main.conf` parse — not ALSA configuration

**What's genuinely new**:
- [x] New module: `bleep/ble_ops/audio/alsa_config.py` — `AsoundEntry`/`TunnelConfig` dataclasses + `read_asound_conf()` parser + `configure_bluealsa_device()` + `remove_bluealsa_device()` + `create_audio_tunnel()` + `backup_and_restore()`. Supports `address 00:00:00:00:00:00` convention. BLEEP-tagged blocks for safe removal. Done.
- [x] CLI commands: `bleep audio-config show|add|remove|tunnel|backup|restore`. Full subcommand parser with `--path` override and `--type sink|source`. Done.

**Expected outcome**: ✅ BLEEP can programmatically configure the host OS audio stack for Bluetooth audio.

---

### M7: Augment File Sharing

**Status**: Done | **Depends on**: M2 (done)

**Existing structures**:
- `bleep/dbuslayer/obex_opp.py`, `obex_ftp.py`, `obex_map.py`, `obex_pbap.py`, `obex_sync.py`, `obex_bip.py` — full OBEX suite
- `bleep/modes/debug_classic_obex.py`: `copp`, `cmap`, `cftp`, `csync`, `cbip` debug commands
- `bleep/ble_ops/classic/opp.py`, `classic/ftp.py`, `classic/map.py`, etc. — ops wrappers
- `bleep/bt_ref/constants.py` `UUID_NAMES` dict: custom/non-SIG UUID → name mapping (first lookup in `get_name_from_uuid()`)
- `bleep/analysis/device_type_classifier.py`: `_BEACON_SERVICE_DATA_UUIDS` includes `a82efa21...` → `"nearby_sharing"` label, `LEServiceDataCollector` matches it
- `bleep/ble_ops/classic/rfcomm.py`: `probe_rfcomm_channel()`, `probe_all_channels()` (M2)
- `bleep/ble_ops/classic/connect.py`: `classic_rfccomm_open()` — raw RFCOMM socket
- `bleep/modes/debug_state.py`: `DebugState` dataclass with `rfcomm_sock` and `rfcomm_bindings` fields

**Known constraint — obexd AppArmor confinement**: On Ubuntu, `obexd` runs under AppArmor and may only write to permitted paths (e.g. `~/.cache/obexd/`). Documented in: todo_tracker R6 (line ~1151), changelog v2.7.20 (line ~1442), `_default_pull_dest()` docstring, `bl_classic_mode.md` troubleshooting table. All obexd receive operations (OPP pull, MAP get, FTP get, BIP get, Sync get) are affected. BLEEP uses a two-stage approach: obexd writes to staging dir, BLEEP moves to final dir.

**D1 — NearbySharing Detection (Phase A only)**:
- [x] Add `"a82efa21-ae5c-3dde-9bbc-f16da7b16c5a": "Microsoft Nearby Sharing"` to `UUID_NAMES` in `bt_ref/constants.py` (custom UUID — `uuids.py` is auto-generated, must not be hand-edited)
- [x] In `ble_ops/le/scan.py` `_native_scan`: add `service_data`, `advertising_data`, `manufacturer_data` from `entry` to passive-scan classifier `context`
- [x] In `ble_ops/le/scan.py` `_base_enum`: add same fields from `device_props` to naggy classifier `context`
- [x] In `analysis/device_type_classifier.py` `_get_collectors_for_mode("passive")`: add `"le_service_data"` to passive collector allowlist
- Phase B (full CDPX protocol) deferred — Microsoft proprietary, research-dependent

**D2 — Customizable OBEX File Save Directory (two-stage)**:
- [x] In `core/config.py`: add `OBEX_STAGING_DIR` (`~/.cache/obexd/`, obexd-safe) and `OBEX_RECEIVE_DIR` (`/tmp/bleep_received/` default, env `BLEEP_RECEIVE_DIR` override)
- [x] In `modes/debug_classic_obex.py`: update `_default_pull_dest()`, `cmd_cmap` get, `cmd_cftp` get defaults to two-stage; new `_obex_staging_path()` and `_stage_and_move()` helpers
- [x] In `cli.py`: update OPP pull/exchange, MAP get, FTP get, BIP get/thumb, Sync get to two-stage; add `--save-dir` to `classic-opp`, `classic-map`, `classic-ftp`, `classic-bip`, `classic-sync` subparsers

**D3 — RFCOMM Channel Binding**:
- [x] In `ble_ops/classic/rfcomm.py`: add `bind_rfcomm_channel()`, `release_rfcomm_channel()`, `list_rfcomm_bindings()` using `rfcomm` userspace utility via `shutil.which` + `subprocess.run`
- [x] In `modes/debug_state.py`: add `rfcomm_bindings: List[int]` field to `DebugState`
- [x] In `modes/debug_classic_rfcomm.py`: add `cbind` command (`cbind <channel>`, `cbind release`, `cbind list`)
- [x] In `cli.py`: add `--bind` and `--device-id` flags to `classic-rfcomm` subcommand
- [x] In `modes/debug.py`: register `cbind` in command table, add cleanup on shell exit

**Expected outcome**: NearbySharing devices detected and labeled in scans. OBEX downloads use obexd-safe staging with auto-cleanup final dir. Persistent RFCOMM bindings with debug-mode tracking and cleanup.

---

### M8: User Profile Control for Connecting Profiles

**Status**: Done

**Existing structures**:
- `bleep/modes/debug_classic_profiles.py`: `cpan` (connect/disconnect/status/server) and `cspp` (register/unregister/status) — PAN and SPP only
- `bleep/dbuslayer/spp_profile.py`: `SppManager`/`SppProfile` with `ProfileManager1.RegisterProfile`
- `bleep/dbuslayer/device_classic.py`: `ConnectProfile(uuid)` (line ~614)
- `bleep/bt_ref/utils.py`: `get_name_from_uuid()` for UUID-to-name resolution

**Overlap note**: `cservices` already displays SDP-discovered service UUIDs with names via `get_name_from_uuid()`. The value-add of `cprofiles` is showing the **D-Bus `Device1.UUIDs`** property (the device's full advertised profile set, which may differ from SDP-discovered services) and allowing direct `ConnectProfile` by UUID.

**What's genuinely new**:
- [x] **Generic profile listing** — new command `cprofiles` in `debug_classic_profiles.py`:
  Reads `org.bluez.Device1.UUIDs` property (distinct from SDP services shown by `cservices`), cross-references via `get_name_from_uuid()`, displays UUID + Name + connection status
- [x] **Generic profile connect** — new command `cprofile connect <UUID>`:
  Calls existing `device.ConnectProfile(uuid)` from `device_classic.py`
  CLI: `bleep connect-profile <MAC> <UUID> [--disconnect]`
- [x] **Security on RegisterProfile** — extended `cspp register` with `--auth`/`--no-auth` flags; `spp.py register()` now passes `require_auth` through to `SppManager`

**Expected outcome**: Users list all profiles, connect by UUID, and register profiles with security options.

---

### M9: Custom Callback Functions with User Integration to I/O Operations

**Status**: Done

**Existing structures**:
- `bleep/signals/router.py`: `register_callback(name, callback)` for signal events
- `bleep/signals/integration.py`: property/notification read/write hooks
- `bleep/dbuslayer/agent_io.py`: `ProgrammaticIOHandler` with per-event `callbacks` dict
- GATT: `characteristic.py` `start_notify(callback)`
- Reconnection: `reconnect.py` `ReconnectionMonitor(callback=...)`
- SPP: `spp_profile.py` `on_connect`/`on_disconnect`/`on_release`

**Approach — extend existing signal router, not rebuild**:
- [x] **Expand signal router triggers**: Added `DEVICE_CONNECT`, `DEVICE_DISCONNECT`, `PAIR_START`, `PAIR_COMPLETE` to `SignalType` enum in `bleep/signals/capture_config.py`
- [x] **User callback directory**: Loader in `bleep/callbacks/__init__.py` — scans `~/.config/bleep/callbacks/*.py` for subclasses of `BleepCallback`, registers via existing `register_callback()`
- [x] **Base class** in `bleep/callbacks/base.py`: `name`, `trigger`, `execute(context)`, lifecycle hooks `on_load()`/`on_unload()`
- [x] **Example callbacks** in `bleep/callbacks/examples/`: `log_all_notifications.py`, `pair_event_logger.py`

**Expected outcome**: Users drop Python files into a callbacks directory; they integrate automatically via the existing signal infrastructure.

---

### M10: Identification and Interactivity of Human Interface Devices (HIDs)

**Status**: Done

**Existing structures**:
- `bleep/ble_ops/le/scan.py` `_collect_device_props()`: probes `org.bluez.Input1` with `GetAll`, stores under `_Input1`
- `bleep/ble_ops/common/conversion.py` `format_device_info_block()`: renders `Input → ReconnectMode` only (lines ~769–785)
- Class-of-Device minor class labels include HID types in `common/conversion.py`
- HID service UUID `0x1124` in `bt_ref/uuids.py`
- Appearance values 960+ mapped to HID subtypes in `common/conversion.py`

**What's genuinely new**:
- [x] **HID classification logic** — `classify_hid()` and `HIDInfo` dataclass added to `bleep/analysis/device_type_classifier.py`: combines appearance (960+ range), CoD peripheral class (0x05), `Input1.ReconnectMode`, HID service UUID. New `HID_CLASSIFICATION` evidence type.
- [x] **Enhanced display** — `format_device_info_block()` in `common/conversion.py` now shows full HID classification block (type + subclass + reconnect mode) when device is identified as HID
- [x] **Debug command** — `chid` in new `debug_hid.py`: full HID classification for connected device (LE or Classic)
- [x] **CLI** — `bleep hid-info <MAC>`: display HID classification and properties

**Expected outcome**: BLEEP identifies HIDs by type (keyboard, mouse, gamepad), displays reconnection behavior, persists HID evidence.

---

### Bonus: Audio Capture and Transcription

**Status**: Done | **Depends on**: M6 (ALSA config)

**Existing structures**:
- `bleep/ble_ops/audio/audio_system.py`: `system_record()`, `system_play()`
- `bleep/ble_ops/audio/audio_codec.py`: GStreamer encode/decode
- `bleep/ble_ops/audio/audio_tools.py`: `AudioToolsHelper` — backend detection, ALSA enumeration, BlueALSA PCMs

**Seven-step pipeline (all new orchestration)**:
- [x] **Step 1–2**: `_validate_prerequisites()` checks for `arecord`/`sox`; PCM auto-derived from MAC
- [x] **Step 3–4**: `_capture_audio()` records via `arecord -D bluealsa:DEV=<MAC>,PROFILE=a2dp`
- [x] **Step 5**: `check_audio_file_has_content()` via sox stat analysis
- [x] **Step 6**: `transcribe_file()` in new `bleep/ble_ops/audio/audio_transcribe.py` wrapping `whisper` CLI and `vosk` Python API
- [x] **Step 7**: `run_audio_intercept()` orchestrates full pipeline; returns `AudioInterceptResult`
- [x] New CLI: `bleep audio-intercept <MAC> [--duration N] [--no-transcribe] [--engine whisper|vosk]`

**Expected outcome**: Audio tap, transcription, and injection pipeline — non-disruptive to original audio stream.

---

### F1: Documentation

**Status**: Done

- [x] Update `bleep/docs/changelog.md` with all v2.8.0 changes (M8, M9, M10, Bonus, P0-1 fixes)
- [x] Update `bleep/docs/todo_tracker.md` — marked completed items
- [x] `bleep/__init__.py` version bumped from `"2.8.0-m1"` to `"2.8.0"` (completed in F3)

---

### F2: Code Review

**Status**: Done

- [x] All 14 modified/new files compile clean (`py_compile`)
- [x] All new files under 300 lines (largest: `debug_classic_profiles.py` at 292 lines)
- [x] No circular imports verified (`bleep.callbacks.base`, `bleep.signals.capture_config`, `bleep.analysis.device_type_classifier`)
- [x] No duplicate functionality — M8 reuses existing `ConnectProfile`/`get_name_from_uuid`/`SppManager`; M9 extends existing signal router; M10 composes existing appearance/CoD/UUID data
- [x] Pre-existing large files (`signals.py`, `cli.py`, `observations.py`, `agent.py`, `conversion.py`) not grown; these are architectural and documented for future F2 consideration

---

### F3: Change Log, TODO Tracking, and Associated Documentation

**Status**: Done

- [x] Structured changelog entries per existing format (v2.8.0 final entry at top of `changelog.md`)
- [x] TODO tracker updated with completion statuses for all M8, M9, M10, Bonus, P0-1 fixes, F1, F2, F3
- [x] Version bumped in `bleep/__init__.py` from `"2.8.0-m1"` to `"2.8.0"`
- [x] All dates consistent: 2026-03-27

---

### Future Work: Expand BT SIG Assigned Numbers Coverage

**Status**: Pending (post-v2.8.0)

The `bleep/bt_ref/update_ble_uuids.py` script currently fetches 12 YAML tables from the Bluetooth SIG public repository (`bitbucket.org/bluetooth-SIG/public`). Additional tables exist that would improve BLEEP's ability to recognize and identify Bluetooth devices and their capabilities/limitations.

**Candidate tables for incorporation** (under `assigned_numbers/`):
- [ ] `service_discovery/attribute_ids/*.yaml` — SDP Attribute ID definitions (e.g., `universal_attributes.yaml`, `browse_group.yaml`, `device_id.yaml`, `hid.yaml`, `imaging.yaml`, `pbap.yaml`, etc.) — would enrich SDP record interpretation in `bleep/ble_ops/classic/sdp.py`
- [ ] `core/core_version.yaml` — Bluetooth Core Specification version numbers → human-readable version strings
- [ ] `core/fhs.yaml` — Frequency Hopping Sequence parameters
- [ ] `mesh/*.yaml` — Bluetooth Mesh assigned numbers (if mesh support is added)
- [ ] Any newly published tables as the SIG repository evolves

**Implementation approach**: Modify `_FILES` dict in `update_ble_uuids.py` to include new YAML paths. Add corresponding `SPEC_ID_NAMES__*` output dicts to `uuids.py`. Wire new dicts into `get_name_from_uuid()` in `bt_ref/utils.py` and any relevant formatting/classification code. All changes flow through the existing auto-generation pipeline — no manual edits to `uuids.py`.

**Principle**: `uuids.py` must only be modified via `update_ble_uuids.py`. Custom/non-SIG UUIDs (BLE CTF, vendor-specific, etc.) belong in `UUID_NAMES` in `bt_ref/constants.py`.

---

---

> **Note (2026-03-26)**: File paths in the historical COMPLETE sections below reflect the `bleep/ble_ops/` layout at the time of completion. The P0-8 restructure (v2.7.40) moved all `ble_ops` modules into `le/`, `classic/`, `common/`, and `audio/` subpackages. See the P0-8 section and changelog v2.7.40 for the mapping.

---

## Data Fidelity Remediation — Schema v10 (2026-03-25) – COMPLETE

**Goal**: Ensure all BLEEP CLI commands persist accurate and complete device/service/characteristic data to the observation database, closing gaps identified through systematic comparison against the BlueZ D-Bus API documentation.

### Phase 1 — High Severity (silent data loss or missing persistence)

- [x] **Gap 1** `bleep/modes/exploration.py` — `print_service_info` now always reads all readable characteristic values and collects all descriptor data regardless of display verbosity or the 20-characteristic threshold; display is still gated, but data collection is unconditional
- [x] **Gap 7** `bleep/cli.py` (`connect`) — `connect` command now persists device metadata and GATT enumeration data to the observation DB via `_collect_device_props` + `_persist_mapping` after successful connection
- [x] **Gap 8** `bleep/cli.py` (`classic-scan`) — discovered Classic devices are now persisted via `upsert_device` with name, RSSI, device class, address type, and device type
- [x] **Gap 9** `bleep/cli.py` (`classic-enum`) + `bleep/ble_ops/classic_connect.py` — `classic-enum` now fetches `org.bluez.Device1` properties (plus Battery1/Input1 auxiliaries), prints a Device Information block (parity with BLE gatt-enum/enum-scan), and persists full device metadata; `classic_connect.py` now calls `upsert_device` with full device info before persisting classic services

### Phase 2 — Medium Severity (incomplete metadata or missed enrichment)

- [x] **Gap 3** `bleep/modes/exploration.py` — `save_to_database` now accepts and persists `device_props` from D-Bus (RSSI, address type, device class, appearance, manufacturer data)
- [x] **Gap 4** `bleep/modes/exploration.py` — permission maps are now included in `upsert_characteristics` calls
- [x] **Gap 6** `bleep/modes/exploration.py` — every readable characteristic value is now also inserted into `char_history` with `source="explore"` for audit trail
- [x] **Gap 10** `bleep/core/observations.py` — `upsert_services` ON CONFLICT clause now updates `handle_start`, `handle_end`, and `name` via `COALESCE` so subsequent scans fill in previously-NULL values
- [x] **Gap 11** `bleep/modes/exploration.py` — device type is now determined by `DeviceTypeClassifier.classify_with_mode()` instead of hardcoded `"le"`, with fallback

### Phase 3 — Schema v10 Migration

- [x] **`bleep/core/observations.py`** — Schema v10 migration:
  - `devices` table: added `tx_power`, `modalias`, `icon`, `service_data`, `advertising_data` columns
  - `services` table: added `is_primary`, `includes` columns
  - `characteristics` table: added `mtu` column
  - New `descriptors` table: `(id, characteristic_id, uuid, handle, flags, value, last_read)` with UNIQUE on `(characteristic_id, uuid)`
  - New public APIs: `get_characteristic_id()`, `upsert_descriptors()`
  - `_DEVICE_COLS` frozenset updated with all new column names
  - Idempotent migration using per-column `ALTER TABLE ADD COLUMN` with safe `try/except`

### Verification

- [x] All four modified files pass `python3 -m py_compile` without errors
- [x] All four modified files pass IDE linter checks with zero diagnostics
- [x] All existing callers of `save_to_database`, `upsert_services`, `upsert_device`, `connect_and_enumerate__bluetooth__low_energy` confirmed compatible (new parameters use defaults, no signature breaks)
- [x] `_persist_mapping` and `_collect_device_props` confirmed importable as module-level functions from `bleep.ble_ops.scan`
- [x] `format_device_info_block`, `device_address_to_path`, `BLUEZ_NAMESPACE`, `ADAPTER_NAME` imports confirmed correct
- [x] `classic_connect.py` `get_device_info()` return dict confirmed to include all referenced keys

### Phase 4 — Schema v10 Full Utilisation (2026-03-25) – COMPLETE

**Goal**: Ensure every v10 column is actively written by all relevant CLI code paths, fix broken persistence logic, and add descriptor persistence everywhere.

- [x] **P1-a** `upsert_services()` — now writes `is_primary` (bool→int) and `includes` (list→JSON) in INSERT and ON CONFLICT COALESCE
- [x] **P1-b** `upsert_characteristics()` — now writes `mtu` in INSERT and ON CONFLICT COALESCE
- [x] **P2-scan** `bleep/ble_ops/scan.py` `_native_scan` — enriched `upsert_device` calls with `tx_power`, `appearance`, `modalias`, `icon`, `manufacturer_data`, `service_data`, `advertising_data` from adapter discovery data
- [x] **P2-base** `bleep/ble_ops/scan.py` `_base_enum` — uses shared `_enrich_device_info_from_props()` for v10 device columns from D-Bus Device1 properties
- [x] **P2-cli** `bleep/cli.py` `connect` — uses `_enrich_device_info_from_props()` instead of manual extraction
- [x] **P2-explore** `bleep/modes/exploration.py` — delegates to `_enrich_device_info_from_props()` for v10 enrichment
- [x] **P2-classic** `bleep/ble_ops/classic_connect.py` + `bleep/cli.py` classic-scan/enum — classic paths now persist `tx_power`, `appearance`, `modalias`, `icon` where available; classic-enum uses `_enrich_device_info_from_props()`
- [x] **P3** `_persist_mapping()` — now persists descriptors (from both `"Descriptors"` and `"descriptors"` keys), threads `is_primary`/`includes` from svc_data, threads `mtu` from char_data
- [x] **P4** `bleep/cli.py` gatt-enum — replaced inline DB persistence with delegation to `_persist_mapping()`, fixing the `"chars"` vs `"Characteristics"` key mismatch in `--deep` mode
- [x] **P5-gatt** `bleep/cli.py` gatt-enum — added `upsert_device()` with full v10 metadata before GATT persistence
- [x] **P5-media** `bleep/cli.py` media-enum — added `upsert_device()` with v10 metadata
- [x] **P6** `bleep/analysis/aoi_analyser.py` — fixed broken `services_mapping` iteration (was `for uuid, handle` on a svc_uuid→dict structure); now correctly extracts chars from `"chars"`/`"Characteristics"` sub-dicts; persists descriptors
- [x] **P7** Documentation updates: `observation_db.md` (v10 row), `observation_db_schema.md` (v10 API table), `device_type_classification.md` (removed stale migration notes)
- [x] **P8** `get_device_detail()` — now includes `"descriptors"` key with all descriptor rows; `export_device_data()` inherits this automatically
- [x] **Shared helper** `_enrich_device_info_from_props()` — new function in `scan.py` centralises extraction of v10 device columns from D-Bus CamelCase property dicts; used by all BLE enumeration code paths
- [x] `bleep/dbuslayer/device_le.py` — shallow-mode `services_resolved()` now includes `Primary`/`Includes` keys in svc_entry for parity with deep mode

### Pre-existing Issues Noted (not caused by this work) — FIXED in P0-1 (v2.7.40)

- ~~`bleep/cli.py` classic-scan debug branch references `d["class"]` but `get_discovered_devices()` uses key `"device_class"` — debug-only class display is ineffective (pre-existing)~~ — Fixed in P0-1
- ~~`bleep/modes/scratch.py` passes `timeout=` kwarg to `connect_and_enumerate__bluetooth__low_energy` which expects `timeout_connect=` — pre-existing `TypeError` at runtime (orthogonal)~~ — Fixed in P0-1

---

## System-Tool Operation Mode for audio-play / audio-record (2026-03-21) – COMPLETE

**Goal**: Add an operation mode for `audio-play` and `audio-record` that leverages existing system audio tools (e.g. `paplay`, `parecord`, `aplay`, `arecord`, `pw-play`, `pw-record`) rather than acquiring D-Bus `MediaTransport1` file descriptors directly.  This mirrors how `audio-recon` already interacts with Target Devices using local subprocess tools, sidestepping BlueZ transport ownership entirely.

### Motivation
- `audio-recon` successfully plays and records audio through `paplay`/`parecord`/`aplay` because PulseAudio/PipeWire already owns the transport — no `Acquire()` needed.
- The direct D-Bus `MediaTransport1.Acquire()` path requires either stopping the audio daemon (`--direct`) or cycling the A2DP profile (endpoint registration mode), both of which are disruptive.
- A system-tool mode works seamlessly alongside PulseAudio/PipeWire with zero host disruption, making it the least invasive option for environments where the audio daemon is running.

### Implementation
- [x] `bleep/ble_ops/audio_system.py` — New module: `system_play()` and `system_record()` resolve device MAC → sink/source ID using the same backend-branched enumeration as `audio-recon` (PA card-centric, PW native node ID, BlueALSA PCM), then delegate to `AudioToolsHelper`
- [x] `bleep/cli.py` — `--system` flag on `audio-play` and `audio-record` argument parsers; when set, bypasses `MediaStreamManager` and calls `system_play()` / `system_record()` directly
- [x] Existing D-Bus direct (`--direct`) and endpoint-registration (default) modes maintained as alternatives

### Verification
- [ ] `audio-play --system <MAC> <file>`: resolves sink, plays via system tool
- [ ] `audio-record --system <MAC> <output>`: resolves source, records via system tool
- [ ] Works when PipeWire/PulseAudio is running without disruption
- [ ] Error message with guidance when no sink/source found for the MAC

---

## Fix Endpoint-Based Transport Acquisition (2026-03-21) – INCOMPLETE

**Goal**: Fix the endpoint-based acquisition path from v2.7.35 that registered a `BleepMediaEndpoint` but never received `SetConfiguration` / `SelectConfiguration` callbacks, resulting in "BlueZ did not assign a transport within the timeout."

### Root Cause
- `RegisterEndpoint()` only adds a local SEP to BlueZ's endpoint pool — it does **not** trigger AVDTP negotiation
- BlueZ selects endpoints exclusively during `ConnectProfile` (`source.c:source_connect` → `a2dp_discover` → `a2dp_select_eps`)
- `ConnectProfile` is a no-op if the A2DP profile is already connected (`source.c:286-290` returns `-EALREADY`)
- The v2.7.35 implementation registered the endpoint on an already-connected device and waited — BlueZ had no reason to call back
- Additionally, D-Bus callbacks were never dispatched because the singleton `dbus.SystemBus()` was not wired to a GLib mainloop

### Fixes Applied
- [x] **F1** `bleep/dbuslayer/media.py` — `BleepMediaEndpoint` uses a **private** D-Bus system bus with explicit `DBusGMainLoop` integration for reliable callback dispatch
- [x] **F2** `bleep/dbuslayer/media.py` — GLib `MainLoop` lifecycle encapsulated inside `BleepMediaEndpoint` (`register()` starts, `unregister()` stops)
- [x] **F3** `bleep/dbuslayer/media.py` — Fixed `SetConfiguration` D-Bus signature from `oay` to `oa{sv}` (properties dict per BlueZ `media-api.txt`)
- [x] **F4** `bleep/dbuslayer/media_stream.py` — Replaced `_cycle_a2dp_profile()` with `_cycle_device_connection()` using full `Device1.Disconnect()` → poll `Connected` → `Device1.Connect()`. Profile-level cycling (`DisconnectProfile` + `ConnectProfile`) was insufficient: the AVDTP session (`source->session`) persists across the cycle, causing `source_connect()` to return `-EALREADY` without running `a2dp_discover`. btmon confirmed only AVDTP Suspend was sent (no Discover/SetConfiguration). Full device disconnect tears down the ACL link, destroying all AVDTP sessions, so the reconnect triggers fresh discovery including the BLEEP endpoint
- [x] **F5** `bleep/dbuslayer/media_stream.py` — Removed unused `threading`/`GLib` imports; mainloop management moved to `BleepMediaEndpoint`

### Outstanding Issues
- After all attempted fixes (F1–F4), the endpoint-based path still fails: "BlueZ did not assign a transport within the timeout"
- `DisconnectProfile` + `ConnectProfile` only produced AVDTP Suspend, not full re-negotiation (btmon confirmed)
- Full `Device1.Disconnect()` + `Device1.Connect()` also failed to trigger `SelectConfiguration`/`SetConfiguration` on the BLEEP endpoint
- Likely causes under investigation:
  - PipeWire/PulseAudio may race to reconnect and consume all remote SEPs before BLEEP's endpoint is selected
  - BlueZ's endpoint selection order may prefer the audio daemon's pre-existing endpoints
  - The endpoint registration path may require BLEEP to be the **only** registered endpoint (audio daemon fully stopped) to guarantee SEP assignment
- **Path forward**: This approach requires deeper investigation into BlueZ endpoint selection ordering and PipeWire/PulseAudio endpoint contention. Deferred in favour of the `--system` flag approach which works **with** the audio daemon rather than competing against it.

### Verification (NOT PASSED)
- [ ] `audio-play` with endpoint registration: endpoint registered → device cycled → `SelectConfiguration` called → `SetConfiguration` called → transport acquired → audio plays
- [ ] `audio-play --direct`: legacy direct acquisition still works when audio daemon is stopped
- [ ] `media-enum`: continues to display endpoints and transports correctly

---

## BLEEP-Owned MediaEndpoint Registration & Dual Acquisition Modes (2026-03-20) – PARTIAL

**Goal**: Resolve `Acquire()` → `NotAuthorized` failures caused by PulseAudio/PipeWire already owning the transport. Implement BLEEP-owned endpoint registration so BLEEP gets its own transport, and add a `--direct` flag for constrained environments.

**Status**: Phase 1 (error guidance) and Phase 3 (CLI flags, code structure) complete. Phase 2 (endpoint registration acquiring a transport) does not function when PipeWire/PulseAudio is running — see "Fix Endpoint-Based Transport Acquisition" above. The `--direct` mode works when the audio daemon is stopped. The endpoint registration default mode requires further investigation.

### Root Cause
- BlueZ `transport.c:acquire()` (line 798) returns `NotAuthorized` when `transport->owner != NULL`
- PulseAudio/PipeWire automatically register endpoints and acquire all A2DP transports
- BLEEP's `Acquire()` fails because the transport is already owned
- BlueZ `media.c:set_configuration()` (line 548-550) enforces one transport per (endpoint, device) pair — unused remote SEPs are available for BLEEP to claim via its own registered endpoint

### Phase 1: NotAuthorized error guidance
- [x] **P1** `bleep/dbuslayer/media_stream.py` — `_print_not_authorized_guidance()` detects transport state and prints actionable remediation (daemon stop commands, `--direct` flag hint)
- [x] **P1b** `bleep/dbuslayer/media_stream.py` — Exception handling in `_acquire_direct()` now specifically detects `NotAuthorizedError`

### Phase 2: BleepMediaEndpoint registration
- [x] **P2a** `bleep/dbuslayer/media.py` — New `BleepMediaEndpoint(dbus.service.Object)` implementing `org.bluez.MediaEndpoint1` server role: `SetConfiguration`, `SelectConfiguration`, `ClearConfiguration`, `Release`
- [x] **P2b** `bleep/dbuslayer/media.py` — `register()` / `unregister()` / `wait_for_transport()` lifecycle methods; `threading.Event` for synchronous wait
- [x] **P2c** `bleep/bt_ref/constants.py` — Added `SBC_CAPABILITIES` and `SBC_DEFAULT_CONFIGURATION` constants
- [x] **P2d** `bleep/dbuslayer/media_stream.py` — `_acquire_via_endpoint()` registers endpoint, waits for `SetConfiguration` callback, acquires BLEEP-owned transport
- [x] **P2e** `bleep/dbuslayer/media_stream.py` — GLib main loop management (`_start_mainloop` / `_stop_mainloop`) on daemon thread for D-Bus callbacks
- [x] **P2f** `bleep/dbuslayer/media_stream.py` — `release_transport()` now also unregisters endpoint and stops main loop

### Phase 3: CLI `--direct` flag
- [x] **P3a** `bleep/cli.py` — Added `--direct` flag to `audio-play` and `audio-record` argument parsers
- [x] **P3b** `bleep/cli.py` — Handler passes `direct=` to `MediaStreamManager` constructor

### Verification
- [x] All modified files pass linter checks with no errors introduced

---

## Fix Silent Exception Swallowing in Transport Discovery (2026-03-20) – COMPLETE

**Goal**: Fix the persisting *"MediaTransport not found"* error from v2.7.33. The three-phase discovery was correct in design but failed at runtime because Phase 1 constructed D-Bus proxy objects (`MediaEndpoint(ep_path)`) just to read their UUID, and a bare `except Exception: continue` silently swallowed the resulting D-Bus errors — causing Phase 1 to always fail and fall through to Phase 3's diagnostic dump.

### Root Cause
- `_find_transport_by_endpoint_path()` called `MediaEndpoint(ep_path)` inside a `try/except Exception: continue` block
- D-Bus proxy construction failed (e.g. interface not available, object path timing) and the exception was silently swallowed
- Phase 2 (complement UUID fallback) also constructed `MediaTransport` proxies for UUID matching, subject to the same issue
- Diagnostic messages were logged at `LOG__DEBUG`, invisible to the user at normal log levels

### Fix: Proxy-free UUID extraction from `GetManagedObjects()`
- [x] **T1** `bleep/dbuslayer/media_stream.py` — New `_collect_media_objects()` method reads endpoint/transport UUIDs directly from `GetManagedObjects()` return data as `(path, uuid)` tuples — zero D-Bus proxy construction for discovery
- [x] **T2** `bleep/dbuslayer/media_stream.py` — Rewrote `_find_transport_by_endpoint_path()` and `_find_transport_by_uuid()` to iterate `(path, uuid)` tuples; proxy construction only happens for the final matched transport path
- [x] **T3** `bleep/dbuslayer/media_stream.py` — All exception handlers and discovery-status messages elevated from `LOG__DEBUG` to `LOG__USER` for visibility
- [x] **T4** `bleep/dbuslayer/media_stream.py` — Improved `acquire_transport()` error message with endpoint UUID, profile name, expected transport role, and `media-enum` hint
- [x] **T5** `bleep/dbuslayer/media.py` — Added `get_managed_objects` to `__all__` exports
- [x] **T6** Removed `MediaEndpoint` and `find_media_devices` imports from `media_stream.py` (no longer needed)

### Verification
- [x] All modified files pass linter checks with no errors introduced

---

## Fix MediaTransport Discovery & Enrich media-enum Output (2026-03-20) – COMPLETE

**Goal**: Fix `audio-play` / `audio-record` *"MediaTransport not found"* error caused by `_get_transport()` comparing a transport's local-role UUID against the remote endpoint UUID. These are always complementary per AVDTP spec (remote A2DP Sink `0x110b` ↔ local A2DP Source transport `0x110a`), so the old direct-match logic always failed. Also enrich `media-enum` output so the endpoint ↔ transport UUID relationship is visible to the user.

### Root Cause Analysis
- BlueZ `transport.c:get_uuid()` returns `media_endpoint_get_uuid(transport->endpoint)` — the **local** endpoint's UUID
- BlueZ `avdtp.c:avdtp_find_remote_sep()` enforces `sep->type != lsep->info.type` — complementary roles only
- BlueZ `a2dp.c:a2dp_select_eps()` selects local sources for remote sinks and vice versa
- BlueZ places transports as children of remote endpoint paths: `sep1/fd0` under `sep1`

### Fix 1: Path-based transport discovery in `_get_transport()`
- [x] **T1a** `bleep/dbuslayer/media_stream.py` — Replaced UUID-matching with three-phase discovery: (1) path-based endpoint→transport association, (2) complement UUID fallback, (3) diagnostic dump
- [x] **T1b** `bleep/dbuslayer/media_stream.py` — Extracted `_find_device_path()`, `_find_transport_by_endpoint_path()`, `_find_transport_by_uuid()`, `_log_available_transports()` helper methods
- [x] **T1c** `bleep/dbuslayer/media_stream.py` — Updated module docstring and class docstring to explain endpoint ↔ transport UUID relationship

### Fix 2: Add `PROFILE_UUID_COMPLEMENTS` mapping
- [x] **T2** `bleep/bt_ref/constants.py` — Added advisory complement mapping for A2DP, HFP, HSP, AVRCP with documentation referencing BlueZ source evidence

### Fix 3: Enrich `media-enum` output
- [x] **T3a** `bleep/cli.py` — Transport output now includes `uuid`, `uuid_name`, `codec`, `codec_name`, `configuration`, `parent_endpoint`, `role`
- [x] **T3b** `bleep/cli.py` — Endpoint output now includes `uuid_name`, `codec_name`, `capabilities`, `delay_reporting`, `expected_transport_uuid`, `expected_transport_role`, `role`

### Fix 4: Docstring updates
- [x] **T4a** `bleep/modes/audio.py` — `play_audio_file()` docstring clarified: `profile_uuid` = remote endpoint role
- [x] **T4b** `bleep/modes/audio.py` — `record_audio()` docstring clarified: `profile_uuid` = remote endpoint role

### Verification
- [x] All modified files pass linter checks with no errors introduced
- [x] Changes verified against BlueZ source: `workDir/bluez/profiles/audio/transport.c`, `avdtp.c`, `a2dp.c`, `bap.c`

---

## Audio Transport & GStreamer Import Fixes (2026-03-19) – COMPLETE

**Goal**: Fix bugs preventing `audio-play` and `audio-record` commands from functioning. Root cause analysis showed that `audio-recon` works because it uses subprocess calls (`paplay`/`parecord`/`aplay`), while `audio-play`/`audio-record` use D-Bus `MediaTransport1.Acquire()` and GStreamer pipelines — both of which had bugs.

### Fix 1: `dbus.UnixFd` handling in `MediaTransport.acquire()`
- [x] **F1** `bleep/dbuslayer/media.py` — BlueZ `Acquire()` returns `dbus.UnixFd` for the file descriptor; `int(fd)` fails. Changed to `fd.take()` with `isinstance` guard, following `workDir/BlueZScripts/simple-asha` line 163.

### Fix 2: Missing D-Bus type conversions in `dbus_to_python()`
- [x] **F2a** `bleep/bt_ref/utils.py` — Added `dbus.UInt64` → `int()` conversion
- [x] **F2b** `bleep/bt_ref/utils.py` — Added `dbus.UInt32` → `int()` conversion
- [x] **F2c** `bleep/bt_ref/utils.py` — Added `dbus.types.UnixFd` → `.take()` conversion

### Fix 3: GStreamer import without version pin in `audio_codec.py`
- [x] **F3a** `bleep/ble_ops/audio_codec.py` — Added `gi.require_version("Gst", "1.0")` and `gi.require_version("GLib", "2.0")` before import, following `workDir/BlueZScripts/simple-asha` lines 12-16
- [x] **F3b** `bleep/ble_ops/audio_codec.py` — Consolidated `GLib` import to module level alongside `Gst`
- [x] **F3c** `bleep/ble_ops/audio_codec.py` — Removed two redundant inner `from gi.repository import GLib` statements (previously at lines 222 and 412)

### Fix 4: GStreamer import without version pin in `preflight.py`
- [x] **F4** `bleep/core/preflight.py` — Added `gi.require_version("Gst", "1.0")` before import in `_check_audio_tools()`

### Verification
- [x] All four files pass linter checks with no errors introduced
- [x] All changes verified against BlueZ reference: `workDir/BlueZScripts/simple-asha`, `workDir/BlueZDocs/org.bluez.MediaTransport.rst`

---

## Documentation Audit & Corrections (2026-03-19) – COMPLETE

**Goal**: Cross-reference all `bleep/docs/` files against the current codebase to identify and fix outdated references, incorrect CLI commands, wrong imports, and missing documentation links.

- [x] **D1** `media_mode.md` — Fixed CLI command reference (`media list/control/monitor` → `media-enum`/`media-ctrl`)
- [x] **D2** `observation_db_usage_scenarios.md` — Fixed wrong import path, parameter names, and return type for scan API
- [x] **D3** `debug_mode.md` — Removed nonexistent `python -m bleep.cli debug` CLI access path
- [x] **D4** `network_capability_plan.md` / `network_capability_summary.md` — Updated `Network` class → `NetworkClient`/`NetworkServer`
- [x] **D5** `ble_scan_modes.md` — Consolidated duplicate "Last updated" dates
- [x] **D6** `README.md` — Added missing links for ~20 documentation files; reorganised into categorised sections
- [x] **D7** `bleep/docs/__init__.py` — Expanded `_DOCS` mapping from 7 to 40+ entries for `pydoc` access

---

## Device-Level Info in CLI Enumeration Output (2026-03-19) – COMPLETE

**Goal**: Display Device1 D-Bus properties (ManufacturerData, ServiceData, TxPower, Class, Appearance, Modalias, UUIDs, etc.) in CLI enumeration commands (`gatt-enum`, `enum-scan`) and improve hex/ASCII formatting with U+FFFD for non-printable bytes.

### Area A – Formatting Utilities (conversion.py)
- [x] **A1** Added `format_hex_ascii()` — renders raw bytes as separate `Hex:` / `ASCII:` lines with U+FFFD for non-printable
- [x] **A2** Added `format_device_info_block()` — renders Device1 properties in labelled info block (ManufacturerData key as hex+decimal, value as Hex/ASCII; ServiceData UUID with resolved name; Class decoded via `format_device_class`; Appearance decoded via `decode_appearance`)
- [x] **A3** Updated `format_gatt_tree()` — added `device_props` parameter; prepends Device Information block when provided
- [x] **A4** Updated characteristic/descriptor ASCII display — now derives ASCII from raw bytes with U+FFFD, always shows both Hex and ASCII when raw is available

### Area B – Data Collection (adapter.py, scan.py)
- [x] **B1** `adapter.py` — `get_discovered_devices()` now extracts `ManufacturerData`, `ServiceData`, `TxPower`, `Appearance`, `Modalias`, `Paired`, `Trusted`, `Blocked` with D-Bus-to-Python type conversion
- [x] **B2** `scan.py` — Added `_collect_device_props()` helper using `Properties.GetAll("org.bluez.Device1")`
- [x] **B3** `scan.py` — `_base_enum()` returns device_props as 5th tuple element; all enum wrappers (`passive_enum`, `naggy_enum`, `pokey_enum`, `brute_enum`) propagate `device_props` in result dicts

### Area C – CLI Integration (cli.py)
- [x] **C1** `gatt-enum` handler passes `device_props` (via `_collect_device_props`) to `format_gatt_tree()`
- [x] **C2** `enum-scan` handler passes `device_props` from enum result dict to `format_gatt_tree()`

---

## Comprehensive BlueZ Property Coverage (2026-03-19) – COMPLETE

**Goal**: Close D-Bus property coverage gaps across all BlueZ interfaces (Device1, GattService1, GattCharacteristic1, GattDescriptor1, Battery1, Input1, Adapter1) by capturing and displaying all specification-defined properties that BLEEP encounters.

### Phase 1 – GATT Tree Display Enhancements
- [x] **1a** `characteristic.py` — Capture `MTU` and `Notifying` from `GattCharacteristic1` D-Bus properties
- [x] **1b** `conversion.py` — Display `MTU` and `Notifying` in `format_gatt_tree()` characteristic output
- [x] **1c** `conversion.py` — Display descriptor `Flags` and `Handle` in `format_gatt_tree()` descriptor output
- [x] **1d** `conversion.py` — Display service `Primary`/`Secondary`, `Handle`, and `Includes` in `format_gatt_tree()` service output
- [x] **1e** `service.py` — Capture `Includes` property from `GattService1`; `device_le.py` — Add `Primary`, `Handle`, `Includes` to deep-mode service mapping

### Phase 2 – Battery1 and Input1 Interfaces
- [x] **2a** `scan.py` — `_collect_device_props()` now probes `org.bluez.Battery1` and `org.bluez.Input1` on the device path
- [x] **2b** `conversion.py` — `format_device_info_block()` displays Battery1 `Percentage` and `Source`
- [x] **2c** `scan.py` — Input1 properties collected alongside Battery1
- [x] **2d** `conversion.py` — `format_device_info_block()` displays Input1 `ReconnectMode` with human-readable policy explanation (`none`/`host`/`device`/`any`)

### Phase 3 – Device1 Display Improvements
- [x] **3a** `conversion.py` — `format_device_info_block()` now handles `Bonded`, `WakeAllowed`, `Icon`, `AdvertisingFlags` (hex/ASCII), and `AdvertisingData` (type-keyed hex/ASCII)
- [x] **3b** `adapter.py` — `get_discovered_devices()` now includes `bonded`, `wake_allowed`, `icon`, `advertising_flags`, `advertising_data`

### Phase 4 – Adapter1 Enhancements
- [x] **4a** `adapter_config.py` — `_DBUS_PROPERTY_MAP` expanded with `power-state`, `manufacturer`, `version`, `experimental-features`
- [x] **4b** `adapter_config.py` — `adapter-config show` display order includes `PowerState`, `Manufacturer`, `Version`, `ExperimentalFeatures` (listed individually)

### Documentation
- [x] **D1** Created `bleep/docs/bluez_interface_properties.md` — comprehensive property reference with security/significance notes for all captured BlueZ interfaces
- [x] **D2** Updated `bleep/docs/gatt_enumeration.md` — reflects enriched GATT tree output
- [x] **D3** Updated `bleep/docs/adapter_config.md` — expanded property table with new Adapter1 properties
- [x] **D4** Updated `bleep/docs/changelog.md` — v2.7.30 entry
- [x] **D5** Updated `bleep/docs/todo_tracker.md` — this section

---

## Future Work — Codebase-Wide UUID Uppercase Normalization

- [ ] **UUID-1** Audit and normalize all UUID usage across the entire BLEEP codebase to uppercase (not just the database persistence layer). This includes D-Bus layer retrieval, in-memory mapping keys, CLI output formatting, and any comparison logic that may be case-sensitive.
- [ ] **UUID-2** When normalizing UUIDs at the D-Bus/retrieval layer, verify that `upsert_services()` return-key behavior is still correct. Currently the returned dict is keyed by the *original* (caller-supplied) UUID to preserve backward compatibility; if all callers start passing uppercase UUIDs, this preservation becomes a no-op but must not break any key lookups downstream.

---

## BLEEP Usability Improvement (2026-03-17) – COMPLETE

**Goal**: Fix database FK errors causing data loss, make non-deep GATT enumeration actually read values, clean up debug output spam, and present enumeration results in a human-readable tree format.

### Area A – Database Tracking Fixes
- [x] **A1** `observations.py` — Added `_ensure_device_exists(cur, mac)` helper that performs `INSERT OR IGNORE` to guarantee parent device rows exist before any child-table insert
- [x] **A2** `observations.py` — Integrated `_ensure_device_exists` into 8 child-table methods: `insert_adv`, `upsert_services`, `upsert_classic_services`, `insert_char_history`, `upsert_sdp_record`, `upsert_pbap_metadata`, `store_aoi_analysis`, `store_device_type_evidence`
- [x] **A3** `observations.py` — Added `_DB_CONN.rollback()` to `_db_cursor()` except block to prevent partial writes
- [x] **A4** `observations.py` — Replaced all ~15 raw `print(f"[DEBUG]...", file=sys.stderr)` calls in `store_signal_capture()` with `print_and_log(message, LOG__DEBUG)`

### Area B – GATT Enumeration & CLI Output
- [x] **B1** `characteristic.py` — Added `read_value_with_fallback()` implementing three-tier read strategy: `ReadValue({"offset":0})` → `ReadValue({})` → `Properties.Get("Value")`; treats `b"\x00"` as valid data
- [x] **B2** `characteristic.py` — Updated `safe_read_with_retry()` to call `read_value_with_fallback()` instead of `read_value()`
- [x] **B3** `device_le.py` — Refactored `_deep_enumerate_gatt()` into `_enumerate_gatt_values(deep: bool)`: deep=True uses retried reads with uppercase mapping format; deep=False performs single reads into existing lowercase mapping
- [x] **B3a** `device_le.py` — Extracted error classification into `_classify_read_errors()` static method and `_apply_error_classification()` instance method (shared between deep and non-deep paths)
- [x] **B3b** `device_le.py` — `services_resolved()` now always calls `_enumerate_gatt_values(deep=deep)` after structure discovery, ensuring values are read even without `--deep`
- [x] **B3c** `device_le.py` — Guarded `_properties_changed` signal handler with `if not self._services:` to prevent redundant re-enumeration
- [x] **B4** `device_le.py` — Added `read_characteristic_with_fallback()` wrapper method
- [x] **B5** `brute.py` — Changed `brute_read_all()` to call `device.read_characteristic_with_fallback()` instead of `device.read_characteristic()`
- [x] **B6** `scan.py` — Updated `naggy_enum()` to: (1) update mapping with most recent multi-read value, (2) detect value changes across rounds into `changed_chars` set, (3) return full result dict including mapping and changed_chars
- [x] **B7** `descriptor.py` — Fixed `b"\x00"` fabrication: changed fallback conditions from `result == b"\x00"` to `not result`, changed final return from `result or b"\x00"` to `result if result is not None else b""`
- [x] **B8** `conversion.py` — Added `format_gatt_tree()` producing human-readable tree output with service/characteristic/descriptor hierarchy, hex/ASCII values, UUID name resolution, mine/permission map summaries, and changed-value indicators
- [x] **B9** `cli.py` — Replaced raw JSON `_dump()` output for `gatt-enum` and `enum-scan` with `format_gatt_tree()`
- [x] **B10** `cli.py` — Replaced all raw `print(f"[DEBUG]...", file=sys.stderr)` calls with `print_and_log(message, LOG__DEBUG)`

---

## Codebase Cleanup & Preparation for v2.8.0 (2026-03-10) – COMPLETE

**Goal**: Review, de-duplicate, and clean up the BLEEP codebase prior to v2.8.0 expansion.  Enforce MAC address uniformity (uppercase), harden the database schema, fix exception handling, and guard placeholder module imports.

**Status**: Complete.

- [x] **Phase 1A** `observations.py` — `_normalize_mac()` changed from `.lower()` to `.upper()`
- [x] **Phase 1B** `observations.py` — Added `_normalize_mac()` calls to `upsert_classic_services`, `upsert_pbap_metadata`, `snapshot_media_player`, `snapshot_media_transport`
- [x] **Phase 1C** Multiple files — Converted all `.lower()` on MAC variables to `.upper()` across 17 files
- [x] **Phase 1D** `media_stream.py` — Fixed colon-vs-underscore MAC comparison bug
- [x] **Phase 1E** Audio subsystem — Harmonized `_norm()`, `extract_mac_from_alsa_device()`, and all MAC comparisons/filenames to uppercase
- [x] **Phase 1F** `observations.py` — Added schema migration v7→v8 converting all existing MACs to uppercase
- [x] **Phase 2A** `observations.py` — Removed duplicate `sdp_records` table definition from `_SCHEMA_SQL`
- [x] **Phase 2B** `observations.py` — Fixed `upsert_sdp_record()` to use `json_dumps()`, `upsert_characteristics()` BLOB type handling and `permission_map` storage, `upsert_device()` column whitelist, `explain_query()` single-SELECT restriction, `get_devices()` DISTINCT fix, `maintain_database()` table list completeness
- [x] **Phase 3A** `mesh/__init__.py` — Guarded `agent`/`provisioning` imports with `try/except ImportError`
- [x] **Phase 3B** `gatt/__init__.py` — Guarded `service`/`characteristic`/`descriptor` imports with `try/except ImportError`
- [x] **Phase 3C** `dbus/__init__.py` — Removed phantom `adapter`/`gatt` from `__all__`, added `connection_pool`
- [x] **Phase 4A** 9 files — Narrowed 14 bare `except:` blocks to specific exception types
- [x] **Phase 4B** 5 files — Added `LOG__DEBUG` logging to critical `except Exception: pass` blocks
- [x] **Phase 5** Full codebase — Gap analysis sweep caught 12 additional MAC `.lower()` sites
- [x] **Phase 6** Documentation — changelog, todo_tracker, version bump to v2.7.27

---

## Debug Mode: Lazy Imports, MAP Pagination & Folder-Context UX (2026-03-30) – COMPLETE

**Goal**: Eliminate the ``RuntimeWarning`` when launching Debug Mode via ``python -m bleep.modes.debug``, add user-controlled MAP message pagination to prevent BlueZ obexd timeouts on large folders, add a quick folder-probe command, and improve error guidance when ``cmap get`` targets a handle from a different folder context.

**Status**: Complete.  All fixes verified via live device testing against SAMSUNG-SM-G891A (E4:FA:ED:83:D8:47).

- [x] **(A)** `bleep/modes/__init__.py` — Replaced eager ``import_module`` calls with PEP 562 ``__getattr__``-based lazy imports.  Submodules are now imported on first attribute access, preventing ``runpy`` from finding them pre-loaded in ``sys.modules`` and emitting the ``RuntimeWarning``.
- [x] **(B)** `bleep/modes/debug_classic_obex.py` — Added ``cmap peek`` sub-command: enumerates all leaf folders via ``_collect_leaf_paths()``, then calls ``list_messages()`` with ``MaxCount=1`` for each.  Prints a one-line summary per folder and a final accessible/total tally.  Confirms folder reachability in seconds without triggering full-listing overhead.
- [x] **(C)** `bleep/modes/debug_classic_obex.py` — Added ``--count N`` and ``--offset M`` optional arguments to ``cmap list``.  Parsed inline and passed as ``MaxCount`` / ``Offset`` D-Bus filters to ``list_messages()``.  Output label reflects active pagination (``[count=N]`` / ``[offset=M, count=N]``).  Without flags, existing default behaviour (obexd ``MaxListCount=1024``) is preserved.
- [x] **(D)** `bleep/modes/debug_classic_obex.py` — Enhanced ``cmap get`` error handler: when ``UnknownObject`` or ``does not exist`` is detected, prints the current ``_last_map_folder`` and advises the user to re-run ``cmap list <correct_folder>`` before retrying.
- [x] **(E)** Updated ``cmap`` help text to document ``peek``, ``--count``, ``--offset``, and the folder-context caveat.

### Root Cause

- **(A)** ``bleep/modes/__init__.py`` eagerly called ``import_module()`` for every submodule at package scope.  When invoked via ``python -m bleep.modes.debug``, Python's ``runpy`` imports the package first (triggering the eager imports and placing ``bleep.modes.debug`` into ``sys.modules``), then attempts to execute it as ``__main__`` — finding it already present, which produces the ``RuntimeWarning``.
- **(B/C)** BlueZ obexd's ``ListMessages`` implementation (``obexd/client/map.c``) defaults to ``MaxListCount=1024``, buffers the entire MAP XML listing in memory, parses it synchronously, and registers a D-Bus ``Message1`` object for each entry before returning the reply.  On a device with a large inbox, this synchronous processing can exceed D-Bus and OBEX timeouts, causing a perceived freeze.
- **(D)** ``get_message()`` constructs a D-Bus object path using the handle and the *current* OBEX session folder.  If the user lists folder A, then lists folder B, then tries to ``cmap get`` a handle from folder A, the OBEX session is re-established against folder B and the handle's D-Bus object does not exist — producing ``UnknownObject``.

### Evidence

- BlueZ ``obexd/client/map.c`` line 59: ``#define DEFAULT_COUNT 1024`` — default ``MaxListCount``.
- BlueZ ``obexd/client/map.c`` lines 1335-1391: ``message_listing_cb()`` — full XML buffered and parsed synchronously.
- BlueZ ``gobex/gobex.c`` line 25: ``#define G_OBEX_DEFAULT_TIMEOUT 10`` — 10s inter-packet timeout.
- ``bleep/dbuslayer/obex_map.py`` line 239: D-Bus object path ``f"{self._session_path}/message{handle}"`` — handle resolved against current session folder.

---

## Debug Mode UX: Mines Command, Help Grouping & Unified Info Display (2026-03-10) – COMPLETE

**Goal**: Expose enumeration mine/permission mappings to the user in Debug Mode, reorganise the help menu for clarity, and unify `info` output between BLE and Classic devices.

**Status**: Complete.

- [x] **M1** `debug_scan.py` — `cmd_mines()`: human-readable display of `current_mine_map` / `current_perm_map` grouped by object type and issue; optionally shows `get_landmine_report()` / `get_security_report()` when device is connected
- [x] **M2** `debug.py` — `mines` added to dispatch table and import list
- [x] **M3** `debug.py` — `_cmd_help()` rewritten with purpose-based groups; `detailed off` shows compact command names per group, `detailed on` shows full usage + description
- [x] **M4** `debug_connect.py` — `cmd_info()` refactored: `_info_ble()`, `_info_classic()`, `_info_from_dbus_path()` all use `_print_unified_props()` and `_format_bool()`; Title Case labels, aligned columns, booleans shown as `True (1)` / `False (0)`; raw device data never altered
- [x] **M5** `debug_connect.py` — All `(*)` clarifiers in Classic `info` gated on `detailed_view`: boolean `(N)` suffix, Device Class decode, profile UUID names, `(BR/EDR)` type label; `(use 'cservices' to list)` stays unconditional
- [x] **M6** `debug_scan.py` — Enum summary labels changed from `mine=`/`perm=` to `landmines=`/`permissions=`; counts now reflect total UUIDs via `_count_map_uuids()` instead of category bucket count

---

## MAP Fixes, Timeouts, Property Access, Handle Context, Push Validation & Error Hints (2026-03-10) – COMPLETE

**Goal**: Fix MAP interactivity bugs in BLEEP Debug Mode — service detection, folder semantics, D-Bus data handling, error handling, debug logging, recursive folder enumeration, redundant SDP scans, sdptool XML parsing, message handle lifecycle, bMessage validation, CreateSession D-Bus signature, D-Bus property access for message flags, bMessage LENGTH validation, D-Bus method call timeouts, and actionable error hints for Service Unavailable / NoReply / device sleep.

**Status**: Complete.  All fixes implemented and verified via live device testing (five rounds).

- **(A) Service detection miss**: `detect_map_service()` only matched UUID substrings and `"message"`/`"map"` in service-map keys, but `build_svc_map` keys the MAP service as `"SMS/MMS"` (from the SDP Service Name).  **Fixed**: added `"sms"` and `"mms"` key patterns, consistent with all sibling `detect_*_service` functions.
- **(B) Double-folder bug**: `list_messages()` called `set_folder(folder)` then `list_messages(folder)` — resolving as `folder/folder`.  **Fixed**: now calls `list_messages("")` after navigating.
- **(C) Root/dot rejection**: `cmap list` at root and `cmap list .` both failed with opaque OBEX errors.  **Fixed**: root is rejected early with an actionable hint; `.`/`..` are caught with a clear message.
- **(D) SupportedTypes crash**: `get_supported_types()` crashed on BlueZ 5.64 which doesn't expose the property.  **Fixed**: catches `DBusException`, logs to `LOG__DEBUG`, returns empty list.
- **(E) Redundant SDP scans**: every `cmap instances` triggered a fresh `sdptool` call.  **Fixed**: accepts optional `service_map` from `state.current_mapping`.
- **(F) sdptool XML empty records**: `_parse_xml_record()` used `elem.text` which fails for sdptool's `<text value="..."/>` format.  **Fixed**: new `_xml_elem_value()` helper checks both formats.

### Root Cause

- [x] **R1** `classic_map.py` — `detect_map_service()` key patterns did not cover `"SMS/MMS"` service name
- [x] **R2** `classic_map.py` — `list_messages()` passed `folder` to both `set_folder()` and `list_messages()`, doubling the path
- [x] **R3** `obex_map.py` — `get_supported_types()` had no error handling for missing properties
- [x] **R4** `classic_map.py` — `list_mas_instances()` always ran fresh SDP discovery
- [x] **R5** `classic_sdp.py` — `_parse_xml_record()` only handled text-content XML, not value-attribute XML

### Implementation

- [x] **I1** `classic_map.py` — `detect_map_service()`: added `"sms"` and `"mms"` to key matching
- [x] **I2** `classic_map.py` — `list_messages()`: sanitize `.`/`..`, fix double-folder, always `list_messages("")`
- [x] **I3** `debug_classic_obex.py` — `cmap list`: reject empty folder at UX layer with hint
- [x] **I4** `debug_classic_obex.py` — `_print_obex_error_hints()`: MAP-specific branches (bad request, not found, no such property, unknown object)
- [x] **I5** `debug_classic_obex.py` — all `cmd_cmap` error paths: `operation="map"`, `format_dbus_error()`
- [x] **I6** `obex_map.py` — `get_supported_types()`: try/except with `LOG__DEBUG` logging
- [x] **I7** `debug_classic_obex.py` — `cmap props`: validate handle is alphanumeric
- [x] **I8** `classic_map.py` — `list_mas_instances()`: optional `service_map` parameter for cached lookup
- [x] **I9** `debug_classic_obex.py` — `cmap instances`: passes `state.current_mapping`
- [x] **I10** `classic_sdp.py` — `_xml_elem_value()`, `_xml_findtext()`, `_parse_xml_record()` rewritten

### Round 2 — D-Bus Iteration Fix, Tree Enumeration & Debug Logging

- [x] **R6** `obex_map.py` — `list_messages()` iterated `dbus.Dictionary` directly instead of `.items()`, causing `ValueError: too many values to unpack`
- [x] **R7** `debug_classic_obex.py` — `ValueError` and other exceptions in `cmd_cmap` were not logged to `LOG__DEBUG`
- [x] **R8** `classic_map.py` — `.`/`..` validation in `list_messages()` conflated with genuine D-Bus errors

### Round 2 — Implementation

- [x] **I11** `obex_map.py` — `list_messages()`: use `.items()` with defensive type checking for `dbus.Dictionary` vs `dbus.Array`
- [x] **I12** `obex_map.py` — `list_messages()`: add `LOG__DEBUG` logging of raw return type/length before unpacking
- [x] **I13** `obex_map.py` — `walk_folder_tree()`: recursive `SetFolder` + `ListFolders` tree walk with `max_depth` guard
- [x] **I14** `classic_map.py` — `list_folder_tree()`: high-level wrapper with BLEEP logging
- [x] **I15** `classic_map.py` — `list_messages()`: removed `.`/`..` validation (moved to command layer)
- [x] **I16** `debug_classic_obex.py` — `cmap folders`: full tree display via `_print_folder_tree()`
- [x] **I17** `debug_classic_obex.py` — `cmap list`: `.`/`..` validation before `try` block; `_suggest_map_leaf_folders()` on "bad request"
- [x] **I18** `debug_classic_obex.py` — all `cmd_cmap` `except` clauses: `print_and_log(..., LOG__DEBUG)`

### Round 3 — Handle Context, Push Validation, Error Hints & CreateSession Signature

- [x] **R9** `obex_map.py` — `CreateSession` passed plain `dict` which `dbus-python` inferred as `a{ss}` instead of required `a{sv}`
- [x] **R10** `obex_map.py` — message D-Bus objects are ephemeral and session-scoped; handle-based methods created fresh sessions that did not contain the message objects
- [x] **R11** `debug_classic_obex.py` — handle-based commands (`get`, `props`, `read`, `delete`) did not provide folder context to populate message objects
- [x] **R12** `debug_classic_obex.py` — `cmap push` accepted plain-text files without warning about bMessage format requirement
- [x] **R13** `debug_classic_obex.py` — `_print_obex_error_hints()` matched `"not implemented"` and `"unknownmethod"` errors with the generic `"obex"` catch-all

### Round 3 — Implementation

- [x] **I19** `obex_map.py` — `CreateSession`: wrap `session_args` in `dbus.Dictionary(..., signature="sv")`
- [x] **I20** `obex_map.py` — `_populate_message_objects(folder)`: navigate + `ListMessages("")` to materialise handles
- [x] **I21** `obex_map.py` — `get_message()`, `get_message_properties()`, `set_message_read()`, `set_message_deleted()`: accept `folder` kwarg, call `_populate_message_objects` when provided
- [x] **I22** `classic_map.py` — `get_message()`: pass `folder` kwarg through to `MapSession.get_message()`
- [x] **I23** `debug_classic_obex.py` — `_last_map_folder` + `_require_map_folder()`: track folder context from `cmap list`
- [x] **I24** `debug_classic_obex.py` — `cmap get/props/read/delete`: use `_require_map_folder()` before handle access
- [x] **I25** `debug_classic_obex.py` — `cmap push`: warn when file lacks `BEGIN:BMSG` header
- [x] **I26** `debug_classic_obex.py` — `_print_obex_error_hints()`: specific branches for `"not implemented"` and `"unknownmethod"` before generic `"obex"` check
- [x] **I27** `debug_classic_obex.py` — updated `cmap` help text: folder-context dependency, bMessage format note

### Round 4 — D-Bus Property Access Fix & Push LENGTH Validation

- [x] **R14** `obex_map.py` — `set_message_read()` and `set_message_deleted()` called `Message1.SetProperty()` which does not exist in BlueZ's GDBus implementation; `Read` and `Deleted` are standard D-Bus properties accessed via `Properties.Set()`
- [x] **R15** `debug_classic_obex.py` — `cmap push` did not validate the `LENGTH:` field in bMessage files, allowing silently malformed pushes when users edit downloaded messages without updating the byte count

### Round 4 — Implementation

- [x] **I28** `obex_map.py` — `set_message_read()`: use `dbus.Interface(obj, DBUS_PROPERTIES).Set(_OBEX_MSG_IFACE, "Read", dbus.Boolean(read, variant_level=1))`
- [x] **I29** `obex_map.py` — `set_message_deleted()`: same pattern with `"Deleted"` property
- [x] **I30** `debug_classic_obex.py` — `_validate_bmsg_length()`: parse `LENGTH:` field, compute actual `BEGIN:MSG` … `END:MSG` byte size, warn on mismatch with correct value

### Round 5 — D-Bus Timeout Fix, Error Hints & UX Improvements

- [x] **R16** `obex_map.py` — D-Bus method calls (`ListMessages`, `ListFolders`, `UpdateInbox`, `ListFilterFields`, `_populate_message_objects`) used the dbus-python default timeout (~25 s), causing `NoReply` errors for large inbox folders (100+ messages)
- [x] **R17** `debug_classic_obex.py` — `_print_obex_error_hints()` had no branch for `"service unavailable"` (OBEX 0x53), falling through to the generic `"obex"` catch-all with misleading advice
- [x] **R18** `debug_classic_obex.py` — `_print_obex_error_hints()` had no branch for `"noreply"` D-Bus timeout errors
- [x] **R19** `debug_classic_obex.py` — `cmap read` did not warn when targeting non-inbox folders where `readStatus` changes are semantically rejected
- [x] **R20** `debug_classic_obex.py` — OBEX timeout hint did not mention device sleep/lock state as the most common cause
- [x] **R21** `debug_classic_obex.py` — `cmap` help text did not distinguish `get` (download contents) from `read` (toggle status flag)

### Round 5 — Implementation

- [x] **I31** `obex_map.py` — `list_folders()`: pass `timeout=self._timeout`
- [x] **I32** `obex_map.py` — `list_messages()`: pass `timeout=self._timeout * 4` (120 s default) for large-folder support
- [x] **I33** `obex_map.py` — `_populate_message_objects()`: pass `timeout=self._timeout * 4`
- [x] **I34** `obex_map.py` — `update_inbox()`: pass `timeout=self._timeout`
- [x] **I35** `obex_map.py` — `list_filter_fields()`: pass `timeout=self._timeout`
- [x] **I36** `debug_classic_obex.py` — `_print_obex_error_hints()`: new `"service unavailable"` branch with MAP folder guidance
- [x] **I37** `debug_classic_obex.py` — `_print_obex_error_hints()`: new `"noreply"` branch with large-folder guidance
- [x] **I38** `debug_classic_obex.py` — `cmap read`: proactive warning when folder context is not `inbox`
- [x] **I39** `debug_classic_obex.py` — OBEX timeout hint updated: mentions device sleep/lock as primary cause
- [x] **I40** `debug_classic_obex.py` — `cmap` help text: clarified `get` = download contents, `read` = toggle flag; added device wake tip

### Documentation

- [x] **D1** `changelog.md`: v2.7.22 (round 1-2); v2.7.23 (round 3); v2.7.24 (round 4); v2.7.25 (round 5)
- [x] **D2** `todo_tracker.md`: this section (updated with round 5)
- [x] **D3** `__init__.py`: version bumped to 2.7.25
- [x] **D4** `learned-memories.mdc`: MAP technical decisions (updated with round 5)

### Live-Device Testing Verification (Samsung SM-G891A, E4:FA:ED:83:D8:47)

All `cmap` commands verified against a Samsung SM-G891A (Android) target device.

| Command | Status | Notes |
|---------|--------|-------|
| `cmap folders` | **PASS** | Full tree enumerated: telecom/msg/{inbox,outbox,sent,deleted,draft} |
| `cmap list telecom/msg/inbox` | **PASS** | Returns 100 messages; may time out on first attempt if device is asleep — succeeds on retry once device is awake |
| `cmap list telecom/msg/outbox` | **PASS** | Returns 14 messages |
| `cmap list telecom/msg/deleted` | **PASS** | Returns 4 messages |
| `cmap list telecom/msg/draft` | **PASS** | Returns 1 message |
| `cmap list telecom/msg/sent` | **INTERMITTENT** | Times out when device is asleep; expected to succeed once device is awake (large folder) |
| `cmap get <handle>` | **PASS** | Downloads full bMessage to file and displays contents (prior rounds) |
| `cmap push <file>` | **PASS** | Succeeds with correctly formatted bMessage (LENGTH field must match); prior rounds |
| `cmap inbox` | **PASS** | Triggers inbox update (prior rounds) |
| `cmap props <handle>` | **PASS** | Returns message properties (prior rounds) |
| `cmap read <handle> true` | **PASS** | Successfully marks inbox message as read |
| `cmap read <handle> false` | **PASS** | Successfully marks inbox message as unread; confirmed via subsequent `cmap list` showing `[ ]` |
| `cmap read <handle>` (outbox) | **EXPECTED FAIL** | Device rejects readStatus on outbox messages with `Service Unavailable` (device-side semantic restriction) |
| `cmap delete <handle>` | **PASS** | Successfully marks message as deleted (prior rounds) |
| `cmap types` | **PASS** | Returns supported types or degrades gracefully (prior rounds) |
| `cmap instances` | **PASS** | Lists MAS instances from SDP (prior rounds) |

**Key observations from testing:**
- Device sleep/lock is the primary cause of OBEX-level timeouts (`Timed out waiting for response`), not D-Bus timeouts.  Once the phone is awake, requests succeed quickly.
- `readStatus` changes are only accepted for inbox messages; outbox/sent/draft/deleted folders return `Service Unavailable` — this is a device-side semantic restriction, not a BLEEP bug.
- `cmap read` toggles the read/unread status flag; `cmap get` downloads and displays full message contents — naming clarified in help text.
- The D-Bus timeout fix (Round 5) prevents `NoReply` errors for large folders; OBEX-level timeouts from the device itself cannot be addressed in code.

---

## OPP Fast-Completion Race Fix (2026-03-09) – COMPLETE

**Goal**: Fix false-failure reporting for OPP transfers that complete faster than the poller can read them, and provide clear diagnostics for unsupported operations.

**Status**: Complete.  All fixes implemented and verified via live device testing against SCH-U365.

- **(D) False send failure**: `copp send /tmp/test.vcf` delivered the file successfully (phone received and stored it), but BLEEP reported failure because obexd removed the Transfer1 object before `poll_obex_transfer()`'s first `props.Get()` call.  The v2.7.20 fix treated ALL removed-object cases as failures — wrong for fast-completing sends.  **Fixed**: now correctly reports `[+] OPP send complete: ?/107 bytes transferred`.
- **(E) Pull works**: Contrary to earlier hypothesis, `copp pull` **does** work against the SCH-U365.  The fast-completion race was masking success.  The file is now validated (existence + non-zero size) and reported with byte count.  **Fixed**: now reports `[+] Business card saved → <path> (<N> bytes)`.
- **(F) ExchangeBusinessCards unimplemented**: obexd 5.64 does not implement `ObjectPush1.ExchangeBusinessCards` — returns `org.bluez.obex.Error.Failed: Not Implemented`.  **Fixed**: clean error message with actionable guidance.  Acknowledged as implemented (acceptable behavior).

**Design note**: BlueZ reference code (`opp-client`, `obexctl`) relies solely on Transfer1 `Status` for success detection and does not check file existence or size.  However, `obexd/client/transfer.c` removes the file on failed GET transfers, making file existence a reliable success indicator.  BLEEP goes beyond the reference by validating file existence + non-zero size for all completion paths.

### Root Cause

- [x] **R7** `_obex_common.py` — `poll_obex_transfer()` raised `RuntimeError` on all `DBusException(UnknownObject)` cases, including successful fast-completing transfers where obexd removed the Transfer1 object after completion.  Callers could not distinguish fast success from genuine failure.
- [x] **R8** `obex_opp.py` — `opp_send_file()` propagated the poller's `RuntimeError` without checking whether the send actually succeeded (it did — the phone received the file).
- [x] **R9** `obex_opp.py` — `opp_pull_business_card()` similarly propagated the error without checking if the dest file was written (it was — pull does work on SCH-U365).
- [x] **R10** `obex_opp.py` — `opp_exchange_business_cards()` did not detect the "Not Implemented" D-Bus error, producing a generic error message instead of actionable guidance.

### Implementation

- [x] **I11** `_obex_common.py` — `poll_obex_transfer()` returns `{"status": "removed"}` instead of raising when the transfer object is gone.  Callers verify the actual outcome.
- [x] **I12** `obex_opp.py` — `opp_send_file()` treats "removed" as fast completion (send succeeded).
- [x] **I13** `obex_opp.py` — `opp_pull_business_card()` validates dest file (existence + non-zero size) for all completion paths — both normal "complete" and fast-race "removed".  Raises clear error when no file was written.
- [x] **I14** `obex_opp.py` — `opp_exchange_business_cards()` detects "Not Implemented" and raises a clear message directing users to use separate send/pull.
- [x] **I15** `debug_classic_obex.py` — `_print_obex_error_hints()` updated with specific hints for pull-unsupported and exchange-unimplemented errors.
- [x] **I16** `debug_classic_obex.py`, `cli.py`, `classic_opp.py` — Pull success messages now include file size in bytes.

### Verification

- [x] `copp send /tmp/test.vcf` — reports `[+] OPP send complete: ?/107 bytes transferred` (file delivered)
- [x] `copp pull` — reports `[+] Business card saved → ~/.cache/obexd/…_card.vcf` (file received, SCH-U365 name card)
- [x] `copp exchange` — reports `OPP ExchangeBusinessCards is not supported by this version of obexd` (acknowledged as acceptable)

### Documentation

- [x] **D4** `changelog.md`: v2.7.21 entry (updated with verified results)
- [x] **D5** `todo_tracker.md`: this section
- [x] **D6** `__init__.py`: version bumped to 2.7.21

---

## OPP OBEX Polishing (2026-03-09) – COMPLETE

**Goal**: Resolve remaining OPP failures observed against the SCH-U365 (`14:89:FD:31:8A:7E`), including a transfer-object race condition, empty SDP records preventing Channel hints, and a potential obexd file-write path restriction.  Add `ExchangeBusinessCards` support and improve OPP diagnostics.

**Status**: Complete.  Superseded by "OPP Fast-Completion Race Fix" above which corrects false failure reporting for fast-completing transfers.

- **(A) SDP parsing failure**: `cservices` returned 5 records with all fields empty (`handle_None`, no RFCOMM channels) even though BlueZ's `UUIDs` D-Bus property correctly listed OPP (`0x1105`).  A fallback targeted `sdptool search` now discovers the OPP RFCOMM channel when full SDP parsing fails.
- **(B) Transfer-object race condition**: When the SCH-U365 accepted the OBEX connection but failed the vCard transfer immediately (phone showed "sending" then "failure in sending"), obexd tore down the `Transfer1` object before `poll_obex_transfer()` could read its `Status` property.  The raw `DBusException(UnknownObject)` propagated unhandled to the user.  The poller now catches this and raises a descriptive `RuntimeError`.
- **(C) Dest path restriction**: Default `copp pull` destination was `/tmp/`, which may be outside obexd's permitted write area on Ubuntu (AppArmor).  Changed to `~/.cache/obexd/`.

**Observation**: Despite the host OS reporting "no supported services" to the target device during generic Bluetooth connection, BLEEP's targeted OPP operations via obexd *do* reach the phone — the device prompts the user to accept and attempts the transfer.  This confirms that profile-level operations can succeed even when the host's SDP presentation appears incompatible, making OPP operations always worth attempting.

### Root Cause (updated from v2.7.19)

- [x] **R1** (v2.7.19) `obex_opp.py` CreateSession without Channel hint → obexd SDP timeout. *Fixed in v2.7.19.*
- [x] **R2** (v2.7.19) `obex_opp.py` session-object access not wrapped in try/except. *Fixed in v2.7.19.*
- [x] **R3** (v2.7.19) `classic_pbap.py` redundant local import → NameError in watchdog. *Fixed in v2.7.19.*
- [x] **R4** `_obex_common.py` `poll_obex_transfer()` does not handle `DBusException` when the transfer object is torn down by obexd before the poller reads `Status` — the raw `UnknownObject` error propagates to the user instead of a descriptive `RuntimeError`.
- [x] **R5** `debug_classic_obex.py` `_extract_opp_channel()` returns `None` when SDP parsing produces empty records (`handle_None`); no fallback to targeted `sdptool search` exists, so `CreateSession` goes without a Channel hint.
- [x] **R6** Default `copp pull` destination (`/tmp/`) may be outside obexd's AppArmor-permitted write area on Ubuntu, causing obexd to abort the incoming vCard transfer (phone shows "failure in sending").

### Implementation

- [x] **I1** (v2.7.19) Channel passthrough + session exception wrapping in `obex_opp.py`.
- [x] **I2** (v2.7.19) Channel threading in `classic_opp.py`.
- [x] **I3** (v2.7.19) Channel extraction + error hints in `debug_classic_obex.py`.
- [x] **I4** (v2.7.19) PBAP local-import fix in `classic_pbap.py`.
- [x] **I5** `_obex_common.py` — Wrap `props.Get()` in `poll_obex_transfer()` with `try/except dbus.exceptions.DBusException`; treat torn-down transfer as a failed transfer with descriptive error.
- [x] **I6** `obex_opp.py` — Add explicit 90 s D-Bus method-call timeout to `SendFile`, `PullBusinessCard`, and `ExchangeBusinessCards` to prevent indefinite blocking.
- [x] **I7** `obex_opp.py` — Add `opp_exchange_business_cards()` wrapping `ObjectPush1.ExchangeBusinessCards` per `org.bluez.obex.ObjectPush(5)`.
- [x] **I8** `classic_opp.py` — Add `exchange_business_cards()` operations wrapper.
- [x] **I9** `classic_sdp.py` — Add `discover_service_channel(mac, uuid_short)` for targeted single-service SDP lookup via `sdptool search --bdaddr`.
- [x] **I10** `debug_classic_obex.py` — `_resolve_opp_channel()` tries `_extract_opp_channel()` first, falls back to `discover_service_channel()`. Default pull dest changed to `~/.cache/obexd/`. `copp exchange` subcommand added. `_print_obex_error_hints()` enhanced with `operation` parameter and transfer-teardown guidance. Usage text documents OPP listing limitation.

### Verification

- [x] Channel passthrough confirmed: phone prompts user to accept OPP connection (v2.7.19)
- [x] Session exception handling confirmed: `UnknownObject` no longer escapes as raw `DBusException` (v2.7.19)
- [x] PBAP `_watchdog_cb` NameError confirmed fixed (v2.7.19)
- [x] Transfer-object race condition handled: `poll_obex_transfer` catches `DBusException` and raises descriptive `RuntimeError`
- [x] `copp send` — file delivered to SCH-U365 (reported as failure in v2.7.20 due to race — fixed in v2.7.21)
- [x] `copp pull` — successfully retrieves SCH-U365 name card (earlier failure was due to race, not device limitation — fixed in v2.7.21)
- [x] `copp exchange` — confirmed obexd 5.64 does not implement `ExchangeBusinessCards` (acknowledged as acceptable)

### Documentation

- [x] **D1** `changelog.md`: v2.7.20 entry
- [x] **D2** `todo_tracker.md`: this section (updated from v2.7.19 PARTIAL)
- [x] **D3** `__init__.py`: version bumped to 2.7.20

---

## OPP OBEX Timeout & Exception Handling Fix (2026-03-09) – COMPLETE

**Goal**: Fix Object Push Profile (OPP) operations failing with `connect_cb: Timed out waiting for response` against paired Classic devices (observed on SCH-U365 / `14:89:FD:31:8A:7E`), an unhandled `DBusException` in `obex_opp.py`, and a `NameError` in `classic_pbap.py`'s watchdog callback.

**Status**: Complete.  Superseded by "OPP OBEX Polishing" above which addresses remaining transfer-level failures.

### Root Cause

- [x] **R1** `obex_opp.py` calls `CreateSession(mac, {"Target": "OPP"})` without a `Channel` hint, forcing obexd to redo SDP — on older devices this redundant SDP lookup during an active RFCOMM keep-alive can stall or resolve incorrectly, causing a 20 s OBEX CONNECT timeout even though the channel is already known from `cconnect` enumeration.
- [x] **R2** `obex_opp.py` lines 123-124: `bus.get_object()` and `dbus.Interface()` after `CreateSession` are not wrapped in `try/except`, so a partially-torn-down session object raises a raw `DBusException` (`UnknownObject`) that escapes to the user instead of a clean `RuntimeError`.
- [x] **R3** `classic_pbap.py` `pbap_dump_async()`: redundant `from bleep.core.log import print_and_log` at lines 328 and 343 (inside conditional/except blocks) cause Python to mark `print_and_log` as a local variable of the enclosing function; when those branches don't execute (the common path), the `_watchdog_cb` closure gets `NameError: cannot access free variable`.

### Implementation

- [x] **I1** `bleep/dbuslayer/obex_opp.py` — Add optional `channel: int | None` parameter to `opp_send_file()` and `opp_pull_business_card()`; when provided, include `dbus.Byte(channel)` as `"Channel"` in `CreateSession` options. Wrap `bus.get_object()` + `dbus.Interface()` in `try/except DBusException`.
- [x] **I2** `bleep/ble_ops/classic_opp.py` — Thread `channel: int | None` through `send_file()` and `pull_business_card()` to the dbuslayer functions.
- [x] **I3** `bleep/modes/debug_classic_obex.py` — Extract OPP RFCOMM channel from `state.current_mapping` and pass to `send_file()`/`pull_business_card()`. Extend `_print_obex_error_hints()` to cover timeout scenarios with actionable guidance.
- [x] **I4** `bleep/ble_ops/classic_pbap.py` — Remove redundant local `from bleep.core.log import` statements at lines 328 and 343; module-level import at line 33 suffices.

### Verification

- [x] Channel passthrough confirmed: phone now prompts user to accept OPP connection (was previously timing out silently)
- [x] Exception handling confirmed: `UnknownObject` no longer escapes as raw `DBusException`
- [x] PBAP `_watchdog_cb` NameError confirmed fixed

### Documentation

- [x] **D1** `changelog.md`: v2.7.19 entry
- [x] **D2** `todo_tracker.md`: this section
- [x] **D3** `__init__.py`: version bumped to 2.7.19

---

## Audio Tools & Profile Correlator Bug Fixes (2026-03-05) – IMPLEMENTED

**Goal**: Fix 7 bugs across audio tools, profile correlator, and audio recon that prevent BLEEP from accurately enumerating Bluetooth audio cards, profiles, and interfaces.  Connected BlueZ devices visible via `pacmd list-cards` were not recognised by `audio-profiles` or fully enumerated by `audio-recon`.

### Change 1: `get_profiles_for_card()` regex excludes digits
- [x] **C1** Fix `[a-z_]+` → `[a-z0-9_]+` so profile names with digits (e.g. `a2dp_sink`) are matched
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 2: `_extract_interfaces_from_block()` pacmd parsing regex
- [x] **C2** Replace `\d+\.\s+(\S+)` with pattern matching actual pacmd format `name/#index: description`
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 3: `_extract_interfaces_from_block()` role_key derivation
- [x] **C3** Fix `section_key.rstrip("s")` producing `"source"/"sink"` instead of `"sources"/"sinks"` expected by `_role_for_interface_name()`
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 4–5: `list_audio_sinks()` / `list_audio_sources()` multi-tool enumeration
- [x] **C4** For `"pipewire"` backend, try PipeWire-native (`pw-dump`) then also `pactl` (PA compat), merging and deduplicating results
- [x] **C5** Mirror Change 4 for `list_audio_sources()`
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 6: `identify_bluetooth_profiles_from_alsa()` card-level augmentation
- [x] **C6** Supplement sink/source enumeration with `get_bluez_cards()` + `get_profiles_for_card()` to discover ALL available profiles regardless of active profile
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 7: MAC comparison bug in `AudioProfileCorrelator`
- [x] **C7** Fix `mac_address.lower().replace(":", "_")` → `mac_address.lower()` at 3 locations
- **File**: `bleep/ble_ops/audio_profile_correlator.py`

### Change 8: Profile restore in `_recon_pulseaudio`
- [x] **C8a** Add `get_active_profile_for_card()` method to `AudioToolsHelper`
- [x] **C8b** Save original active profile before cycling, restore after
- **Files**: `bleep/ble_ops/audio_tools.py`, `bleep/ble_ops/audio_recon.py`

### Verification
- [x] Tested against live device `D8:3A:DD:0B:69:B9` — `audio-profiles`, `audio-profiles --device`, and `audio-recon --device` all return complete results
- [x] Profile restore confirmed: active profile `handsfree_head_unit` preserved after `audio-recon` cycling

---

## Classic Enumeration Robustness Fix (2026-03-02) – IMPLEMENTED

**Goal**: Fix `classic-enum` failing with `sdptool failed: PBAP not in browse output` on devices that don't support PBAP, and ensure SDP records are always displayed to the user even when connection-based enumeration fails.

### Root Cause
- [x] **R1** `discover_services_sdp()` required PBAP (UUID 0x112f) to be present to accept parsed SDP records — devices without PBAP caused a `RuntimeError` even when valid records were obtained
- [x] **R2** `classic-enum` CLI only displayed SDP records in `--debug` mode; primary output required a full connection
- [x] **R3** Connection failures (e.g. `br-connection-create-socket`) caused the command to exit with error 1, discarding already-obtained SDP data

### Implementation
- [x] **I1** Removed PBAP gate from `discover_services_sdp()` — records with RFCOMM channels are accepted immediately regardless of which services are present
- [x] **I2** Added formatted SDP record display to `classic-enum` CLI — always shown after successful SDP discovery
- [x] **I3** Connection failure fallback now returns exit 0 when SDP records were obtained, with a warning message

### Documentation
- [x] **D1** `changelog.md`: v2.7.3 entry
- [x] **D2** `todo_tracker.md`: this section
- [x] **D3** `__init__.py`: version bumped to 2.7.3
- [x] **D4** `bl_classic_mode.md`: updated output examples

---

## Debug Mode Modular Refactor (2026-03-01) – IMPLEMENTED

**Goal**: Refactor the monolithic `bleep/modes/debug.py` (3864 lines) into a modular architecture with focused submodules, centralised shared state via a `DebugState` dataclass, and a slim core shell. No behavioral changes. Guided by `workDir/Debugging/README.debug-mode-refactor`.

### Architecture
- [x] **A1** `debug_state.py` – `DebugState` dataclass replacing 16 module-level globals + GLib MainLoop management
- [x] **A2** `debug_dbus.py` – D-Bus error formatting, path resolution, navigation (ls/cd/pwd/back), introspection commands (interfaces/props/methods/signals/call/monitor/introspect)
- [x] **A3** `debug_connect.py` – Transport detection, connect/disconnect/info with Classic and BLE branches
- [x] **A4** `debug_gatt.py` – GATT operations (services/chars/char/read/write/notify/detailed), property display, notification callback factory
- [x] **A5** `debug_classic.py` – Classic BT commands (cscan/cconnect/cservices/ckeep/csdp/pbap)
- [x] **A6** `debug_pairing.py` – Agent and pair commands, single/brute-force/post-pair connect flows
- [x] **A7** `debug_scan.py` – Scan variants (scan/scann/scanp/scanb) and enumeration (enum/enumn/enump/enumb)
- [x] **A8** `debug_aoi.py` – AOI analysis and database commands (aoi/dbsave/dbexport)
- [x] **A9** `debug_multiread.py` – Updated to accept `DebugState` instead of 7 individual parameters
- [x] **A10** `debug.py` – Slim core shell (~270 lines): imports, help, dispatch table factory, shell loop, CLI entry point

### Documentation
- [x] **D1** `changelog.md`: v2.7.2 entry with full change list
- [x] **D2** `todo_tracker.md`: this section
- [x] **D3** `__init__.py`: version bumped to 2.7.2

---

## Lockout-Aware Brute-Force (2026-03-01) – IMPLEMENTED

**Goal**: Fix brute-force PIN discovery failing on devices that implement pairing lockout after consecutive wrong PINs.  The brute forcer was treating `AuthenticationRejected` (lockout) the same as `AuthenticationFailed` (wrong PIN), causing it to skip the correct PIN during a lockout window.

### Root Cause Analysis
- [x] **A1** Identified two distinct D-Bus errors: `AuthenticationFailed` = device tested and rejected the PIN; `AuthenticationRejected` = device refusing to evaluate the PIN (lockout active)
- [x] **A2** Confirmed target device (DingoMan) transitions from `AuthenticationFailed` to `AuthenticationRejected` after ~3 consecutive failures, even when the correct PIN is subsequently provided

### Implementation
- [x] **I1** `PairingAgent.last_pair_error`: new attribute storing the D-Bus error name from the most recent `pair_device()` failure
- [x] **I2** `PinBruteForcer` error reclassification: split `_REJECTION_ERRORS` into `_WRONG_PIN_ERRORS`, `_LOCKOUT_ERRORS`, `_RETRY_ERRORS`, `_BLOCKING_ERRORS`
- [x] **I3** Lockout detection: track `AuthenticationFailed` → `AuthenticationRejected` transition as lockout signal
- [x] **I4** Cooldown + retry: pause for `lockout_cooldown` seconds (default 60), then retry the rejected candidate
- [x] **I5** Max lockout retries: abort after `max_lockout_retries` (default 3) consecutive cooldown cycles per candidate
- [x] **I6** `_interruptible_sleep()`: sleep in 1s increments, checking `_stop_requested` for graceful interrupt during cooldown
- [x] **I7** `--lockout-cooldown` and `--max-lockout-retries` CLI arguments added to `pair --brute`
- [x] **I8** `BruteForceResult.lockout_pauses`: tracks number of lockout cooldown pauses in results

### Documentation
- [x] **D1** `changelog.md`: updated v2.7.1 entry with lockout-aware features
- [x] **D2** `todo_tracker.md`: this section
- [x] **D3** `pairing_agent.md`: updated with lockout-aware brute-force details
- [x] **D4** `debug_mode.md`: updated brute-force options documentation

---

## Pair-Connect-Explore: Persistent Connections After Pairing (2026-03-01) – IMPLEMENTED

**Goal**: Restructure the debug-mode `pair` command so that successful pairing results in a persistent connection and return to the debug shell, enabling immediate device exploration.  Enhance `connect` to auto-detect transport, and `info` to work with paired-but-disconnected devices.

### Planning
- [x] **P1** Root-cause analysis of 9-10s post-pair ACL disconnect (kernel HCI idle timeout)
- [x] **P2** Plan for pair restructure: operational mode (default) + `--test` PoC mode
- [x] **P3** Plan for smart `connect` command with transport auto-detection
- [x] **P4** Plan for `info` enhancement with D-Bus path fallback

### Implementation
- [x] **I1** `_get_device_transport()`: transport detection from D-Bus `Device1` properties
- [x] **I2** `_post_pair_connect()` / `_post_pair_connect_classic()` / `_post_pair_connect_le()`: post-pair connection helpers
- [x] **I3** `pair` command restructure: `--test` flag, default operational mode with `_post_pair_connect()`
- [x] **I4** Smart `connect` command: `_connect_le()` / `_connect_classic()` with fallback
- [x] **I5** Enhanced `info` command: `_info_from_dbus_path()` for paired-but-disconnected devices
- [x] **I6** Enhanced `disconnect` command: keepalive socket cleanup and full state reset

### Documentation
- [x] **D1** `debug_mode.md`: updated pair and connect command documentation
- [x] **D2** `pairing_agent.md`: updated to v2.7.1, new features listed
- [x] **D3** `changelog.md`: v2.7.1 entry
- [x] **D4** `todo_tracker.md`: this section
- [x] **D5** Version bump to 2.7.1

### Future Work (from this effort)
- [ ] **F1** Profile-level connect retry: attempt `ConnectProfile()` for individual UUIDs after `Connect()` fails
- [ ] **F2** Keepalive socket auto-recovery: detect dropped sockets and re-open
- [ ] **F3** MainLoop inversion (from v2.7.0 planning): eliminate stop/restart cycle for concurrent agent + shell

---

## Pairing Agent Expansion: Three Modes + Brute-Force + Passkey (2026-03-01) – IMPLEMENTED

**Goal**: Expand the debug-mode pairing PoC from hardcoded-PIN-only to three modes of operation (hardcoded, interactive, brute-force), add passkey support for LE devices, and document the MainLoop inversion architecture for future adoption.

### Planning & Investigation
- [x] **P1** Expert-level review of BLEEP codebase (all modules, modes, D-Bus layer)
- [x] **P2** BlueZ reference analysis: Agent1 API, `simple-agent`, `bt-agent`, PinCode vs PassKey
- [x] **P3** GLib MainLoop compatibility assessment across all BLEEP modes
- [x] **P4** Option A vs Option B analysis for MainLoop inversion
- [x] **P5** Plan presented and approved

### Implementation
- [x] **I1** `BruteForceIOHandler` added to `bleep/dbuslayer/agent_io.py`
- [x] **I2** `PinBruteForcer` orchestrator created at `bleep/dbuslayer/pin_brute.py`
- [x] **I3** `_cmd_pair` expanded to three modes in `bleep/modes/debug.py`
- [x] **I4** Shared helpers extracted: `_find_device_path`, `_remove_stale_bond`, `_resolve_device_for_pair`, `_register_pair_agent`, `_post_pair_monitor`
- [x] **I5** `agent status` enhanced with PIN/passkey display and invocation history
- [x] **I6** `mainloop_architecture.md` design document created

### Documentation
- [x] **D1** `pairing_agent.md` updated with three modes, brute-force, passkey, new status
- [x] **D2** `debug_mode.md` updated with expanded `pair` command reference
- [x] **D3** `changelog.md` v2.7.0 entry added
- [x] **D4** `todo_tracker.md` this section added

### Future Work (from this effort)
- [ ] **F1** MainLoop inversion (Option A): move GLib MainLoop to main thread, `input()` to worker thread
- [ ] **F2** Test `RequestPasskey` against real LE hardware
- [x] **F3** Brute-force response analysis: classify D-Bus errors to detect device lockout patterns (implemented in v2.7.1)
- [ ] **F4** PIN persistence: store discovered PINs in observations database

---

## Debug Mode Pairing: Full Fix (2026-02-28) – CONFIRMED WORKING

**Goal**: Fix `RequestPinCode` (and all `org.bluez.Agent1` method) handlers never firing during debug-mode pairing despite D-Bus METHOD CALLs arriving at the BLEEP process.

**Result**: BLEEP successfully pairs with target `D8:3A:DD:0B:69:B9` using PIN `12345`.  `RequestPinCode` handler fires, `AutoAcceptIOHandler` returns the configured PIN, BlueZ accepts the pairing, and the device is set as trusted.

### Investigation & Diagnosis
- [x] **D1** Confirmed D-Bus METHOD CALL routing: message filters see `RequestPinCode` arriving at BLEEP's bus unique name
- [x] **D2** Confirmed `DBusGMainLoop(set_as_default=True)` is called before first `dbus.SystemBus()` creation (in `bleep/core/config.py`)
- [x] **D3** Confirmed agent methods are registered in `dbus-python`'s class table (decorated with `@dbus.service.method`)
- [x] **D4** Confirmed message filters return `None` (`NOT_YET_HANDLED`), not consuming messages
- [x] **D5** Identified architectural difference: working `simple-agent` runs mainloop on main thread; BLEEP debug runs on background thread
- [x] **D6** Baseline test: `simple-agent` successfully pairs with target `D8:3A:DD:0B:69:B9` using PIN `12345`
- [x] **D7** Diagnostic PoC (`poc_pair_diag.py`) proved `sudo` is NOT required for handler dispatch
- [x] **D8** Diagnostic PoC proved `eavesdrop='true'` match rules fail with `AccessDenied` for non-root — never active in BLEEP
- [x] **D9** Narrowed root cause to generic message filter installed by `enable_unified_dbus_monitoring()`

### Root Cause (refined through 5 phases)
- [x] **RC1** Background-thread `MainLoop.run()` does not dispatch `dbus.service.Object` handlers (only message filters)
- [x] **RC2** `GLib.MainContext.iteration(False)` on the main thread ALSO does not dispatch object-path handlers — only message filters
- [x] **RC3** Only `GLib.MainLoop().run()` drives the full `libdbus` dispatch chain including object-path → `dbus.service.Object._message_cb()` → Python method handler
- [x] **RC4** `bus.add_message_filter()` installed by `enable_unified_dbus_monitoring()` interferes with `dbus-python` handler dispatch even though the filter returns `None`
- [x] **RC5** `_cmd_pair()` fabricated fake D-Bus paths from MAC addresses when device not in BlueZ tree, causing `UnknownObject` error — should use `GetManagedObjects()` like `bluezutils.find_device()`

### Fix (Phase 1 — debug.py)
- [x] **F1** In `_cmd_pair()`: replace `_ensure_glib_mainloop()` with `_stop_glib_mainloop()` before agent creation/pairing
- [x] **F2** In `_cmd_pair()`: add `_ensure_glib_mainloop()` after `pair_device()` returns to restart background loop
- [x] **Files Modified**: `bleep/modes/debug.py` (2-line change in `_cmd_pair()`)

### Fix (Phase 2 — PoC + agent.py)
- [x] **F3** PoC standalone script confirmed temporary `GLib.MainLoop` + `timeout_add` approach works — `RequestPinCode` fires, pairing succeeds
- [x] **F4** In `pair_device()`: replaced `context.iteration(False)` loop with temporary `GLib.MainLoop` + `GLib.timeout_add(100, poll)` pattern
- [x] **Files Modified**: `bleep/dbuslayer/agent.py` (non-background path in `pair_device()`)

### Fix (Phase 4 — Message filter interference)
- [x] **F5** Disabled `enable_unified_dbus_monitoring(True)` during agent registration in `ensure_default_pairing_agent()`
- [x] **F6** Only `register_agent()` is called for correlation tracking — monitoring can be re-enabled after pairing completes
- [x] **Files Modified**: `bleep/dbuslayer/agent.py` (`ensure_default_pairing_agent()`)

### Fix (Phase 5 — Device discovery + bond storage)
- [x] **F7** Replaced `get_discovered_devices()` cache lookup + path fabrication with `GetManagedObjects()` query matching `bluezutils.find_device()` pattern
- [x] **F8** Added `Transport: "auto"` filter and 15s discovery scan for both BLE and BR/EDR classic devices
- [x] **F9** Clear error message on discovery failure instead of fabricating phantom D-Bus paths
- [x] **F10** Fixed `RemoveDevice` re-discovery: proper 15s scan with `Transport: "auto"` and `GetManagedObjects()` re-resolve
- [x] **F11** Fixed `PairingStateMachine.start_pairing()` to extract MAC address from `device_path` and include it in `_pairing_data`
- [x] **Files Modified**: `bleep/modes/debug.py` (`_cmd_pair()`), `bleep/dbuslayer/pairing_state.py` (`start_pairing()`)

### Documentation
- [x] **DOC1** Updated `bleep/docs/agent_dbus_communication_issue.md` — All phases through Phase 5
- [x] **DOC2** Updated `bleep/docs/mainloop_requirement_analysis.md` — message filter interference discovery
- [x] **DOC3** Updated `bleep/docs/debug_mode.md` — updated `pair` command docs with discovery scan details
- [x] **DOC4** Changelog entry v2.6.1 + v2.6.2 in `bleep/docs/changelog.md`
- [x] **DOC5** TODO tracker section (this section)

### Fix (Phase 6 — Bond storage + state machine resilience)
- [x] **F12** Fixed `PairingStateMachine.start_pairing()` to extract MAC address from `device_path` and include `"address"` in `_pairing_data` — resolves `Bond info must include device address` ValueError
- [x] **F13** Added `_safe_transition_failed()` guard in `pair_device()` — prevents `InvalidTransitionError` when error handler tries to transition from a terminal state (COMPLETE/FAILED/CANCELLED) to FAILED
- [x] **Files Modified**: `bleep/dbuslayer/pairing_state.py`, `bleep/dbuslayer/agent.py`

### Final Confirmation (2026-02-28)
- [x] **V1** Full end-to-end pairing verified: `pair D8:3A:DD:0B:69:B9 --pin 12345` — `RequestPinCode` fires, PIN returned, `Pair()` succeeds, device trusted, bond stored, `pair_device()` returns `True`
- [x] **V2** Stale bond removal + re-pair verified: `RemoveDevice()` + 15s re-scan + re-pair — works correctly
- [x] **V3** Post-pair disconnect monitoring verified: detects target's auto-disconnect after 9s

### Pairing: Future Work
- [ ] **FW1** Re-enable unified D-Bus monitoring after `pair_device()` returns (currently disabled for entire agent lifetime)
- [ ] **FW2** Test remaining Agent1 methods (`RequestPasskey`, `RequestConfirmation`, `DisplayPasskey`, `RequestAuthorization`, `AuthorizeService`) against real devices
- [ ] **FW3** PIN code persistence — store known PINs in observations database for automatic reuse
- [ ] **FW4** Pairing retry logic with exponential backoff for transient failures
- [ ] **FW5** Investigate `dbus-python` message filter interference — determine if bug or architectural limitation
- [ ] **FW6** Multi-adapter support — support selecting adapter other than `hci0`
- [ ] **FW7** Fix DB FOREIGN KEY errors in `observations.py:store_device_type_evidence` during scan

---

## Amusica: Bluetooth Audio Target Discovery & Manipulation (2026-02-28) – Completed (Core)

**Goal**: Automated discovery, JustWorks connection assessment, audio reconnaissance, and audio manipulation of Bluetooth audio devices.  Compose existing BLEEP primitives (scan, connect, audio_recon, audio_tools, media control) into an end-to-end workflow.

### Phase 1: Constants & Audio Service UUID Filter
- [x] **1.1** Add `AVRCP_TARGET_UUID`, `AVRCP_CONTROLLER_UUID` to `bt_ref/constants.py`
- [x] **1.2** Add `AUDIO_SERVICE_UUIDS` frozenset aggregating A2DP, HFP, HSP, AVRCP UUIDs
- [x] **Files Modified**: `bleep/bt_ref/constants.py` (+15 lines)

### Phase 2: Audio Halt Capability
- [x] **2.1** Add `AudioToolsHelper.halt_audio_for_device()` — multi-step disruption: AVRCP pause → volume 0 → profile "off"
- [x] **Files Modified**: `bleep/ble_ops/audio_tools.py` (+60 lines)

### Phase 3: Core Orchestration Engine
- [x] **3.1** `scan_audio_targets()` — UUID-filtered scan using adapter discovery + post-filter
- [x] **3.2** `attempt_justworks_connect()` — connect-only (no pair) with auth/reject classification
- [x] **3.3** `assess_targets()` — pipeline: connect each target, run audio_recon on accessible ones
- [x] **3.4** `summarise_assessment()` — structured report of vulnerable targets
- [x] **Files Added**: `bleep/ble_ops/amusica.py` (~240 lines)

### Phase 4: CLI Mode
- [x] **4.1** `scan` subcommand — scan with optional `--connect` for full assessment
- [x] **4.2** `halt` subcommand — halt all audio on a connected target
- [x] **4.3** `control` subcommand — proxy to existing media control (play/pause/stop/next/prev/volume/info)
- [x] **4.4** `inject` subcommand — play audio file into target's sink
- [x] **4.5** `record` subcommand — record from target's source with sox analysis
- [x] **4.6** `status` subcommand — show card, profiles, sources, sinks, playback state
- [x] **Files Added**: `bleep/modes/amusica.py` (~290 lines)

### Phase 5: CLI & Mode Registration
- [x] **5.1** Add `amusica` subparser to `cli.py` with REMAINDER args
- [x] **5.2** Add dispatch in `cli.py` `main()` routing to `bleep.modes.amusica.main()`
- [x] **5.3** Add lazy import to `modes/__init__.py`
- [x] **Files Modified**: `bleep/cli.py` (+10 lines), `bleep/modes/__init__.py` (+2 lines)

### Phase 6: Documentation
- [x] **6.1** Changelog entry v2.6.0 in `bleep/docs/changelog.md`
- [x] **6.2** TODO tracker section (this section)
- [x] **6.3** Cross-reference in `bleep/docs/audio_recon.md`

### Future Work — Amusica Advanced Capabilities

The following items are **not implemented** in the core release and are documented here for future expansion.  They build on the Amusica core and the existing audio recon bonus objectives documented in `bleep/docs/audio_recon.md`.

#### FW-A1: ALSA Configuration File Customization
- [ ] Support runtime generation/modification of `asound.conf` / `.asoundrc` for BlueALSA default device configuration
- [ ] Create loopback and dsnoop/dmix PCM entries for multi-client ALSA access
- [ ] Document required ALSA plugin packages by distro
- **Prerequisite**: User guidance on acceptable ALSA config modifications (noted in README.amusica line 63)
- **Location**: `bleep/ble_ops/audio_tools.py` — new `configure_alsa_device()` method

#### FW-A2: Audio Feedback Loop Injection
- [ ] Capture audio from a target device's microphone and feed it back into the device's speaker stream in real-time
- [ ] Requires PulseAudio/PipeWire loopback module (`module-loopback`) or ALSA loopback device
- [ ] Implementation: Create a loopback from the target's microphone source to the target's speaker sink
- **Builds on**: Audio recon Bonus Objective 3 (play into existing streams) and Bonus Objective 1 (duplicate playback)
- **Location**: `bleep/ble_ops/amusica.py` — new `create_feedback_loop()` function

#### FW-A3: Full Audio Stream Consolidation
- [ ] Record headset speakers + microphone into a single mixed audio file (e.g. full call capture)
- [ ] Requires creating a PulseAudio null sink, routing multiple sources via `module-loopback`, and recording from the null sink's monitor
- [ ] Alternative: post-capture mix using `sox -m mic.wav spk.wav mixed.wav`
- **Builds on**: Audio recon Bonus Objective 2 (consolidate streams)
- **Location**: `bleep/ble_ops/audio_tools.py` — new `consolidate_recordings()` method or separate `audio_mix.py`

#### FW-A4: Dummy/Virtual Audio Interface Creation
- [ ] Create virtual PulseAudio/PipeWire sinks and sources for routing control
- [ ] Use `pactl load-module module-null-sink` or PipeWire equivalent to create programmable endpoints
- [ ] Feed recorded audio into virtual source so applications see it as "microphone"
- **Builds on**: Audio recon Bonus Objective 4 (reconfigure I/O)
- **Location**: `bleep/ble_ops/audio_tools.py` — new `create_virtual_device()` and `destroy_virtual_device()` methods

#### FW-A5: Profile-Based Audio Denial via ALSA
- [ ] Systematically cycle through all card profiles to find one that disrupts audio most effectively per device type
- [ ] Map profile → disruption effectiveness for common device types (headsets, speakers, car kits)
- [ ] Extend `halt_audio_for_device()` with profile cycling strategy
- **Location**: `bleep/ble_ops/audio_tools.py` — extend `halt_audio_for_device()`

#### FW-A6: Amusica Observation DB Persistence
- [ ] Store Amusica assessment results (scan, connection, recon) in the BLEEP observation database
- [ ] New table `amusica_assessments` with columns: `mac`, `timestamp`, `justworks_ok`, `audio_interfaces`, `result_json`
- [ ] Query via `bleep db` for historical vulnerability tracking
- **Builds on**: Audio recon Bonus Objective 5 (persist recon in DB)
- **Location**: `bleep/core/observations.py` — schema v8 migration + `store_amusica_result()` function

#### FW-A7: Terminal UI for Amusica
- [ ] Interactive terminal-based interface for real-time audio control of multiple targets
- [ ] Live display of connected devices, audio state, recording status
- [ ] Keyboard shortcuts for halt/play/record/inject operations
- **Note**: Per README.amusica line 101 — "a terminal-based interface for users is within acceptable parameters"
- **Location**: `bleep/modes/amusica.py` — new `_cmd_tui()` subcommand

#### FW-A8: Targeted Scan with Connection-Less UUID Discovery
- [ ] Use advertisement data parsing to identify audio UUIDs without requiring a connection
- [ ] Leverage `ServiceData` and `ManufacturerData` from BLE advertisements for passive audio device identification
- [ ] Reduce scan time by avoiding connection attempts for devices that can be classified from advertisements alone
- **Location**: `bleep/ble_ops/amusica.py` — enhance `scan_audio_targets()` with advertisement parsing

---

## Adapter Configuration & Bluetooth Configurability (2026-02-28) – Completed

**Goal**: Expose local Bluetooth adapter configuration (Name, Alias, Class, Discoverable, Pairable, security toggles) through BLEEP using the lowest-level tools available, with a tiered approach: D-Bus native → `bluetoothctl mgmt.*` → `main.conf` inspection.

### Phase 1: D-Bus Property Accessors
- [x] **1.1** Add `get_adapter_info()` — returns all adapter properties as native Python dict via `Properties.GetAll()`
- [x] **1.2** Add individual getters: `get_alias()`, `get_name()`, `get_address()`, `get_address_type()`, `get_class()`, `get_powered()`, `get_discoverable()`, `get_pairable()`, `get_connectable()`, `get_discoverable_timeout()`, `get_pairable_timeout()`, `get_discovering()`, `get_uuids()`, `get_modalias()`, `get_roles()`
- [x] **1.3** Add DRY helpers: `_get_property()` and `_set_property()` base methods
- [x] **1.4** Add individual setters: `set_alias()`, `set_powered()`, `set_discoverable()`, `set_pairable()`, `set_connectable()`, `set_discoverable_timeout()`, `set_pairable_timeout()`
- [x] **Files Modified**: `bleep/dbuslayer/adapter.py` (+~130 lines)

### Phase 2: bluetoothctl Management Socket Integration
- [x] **2.1** Implement `_run_bluetoothctl_mgmt()` — stdin-based multi-command subprocess wrapper for `bluetoothctl`
- [x] **2.2** Implement `_mgmt_index()` and `_mgmt_cmd()` — auto-prepend `mgmt.select <index>` for adapter selection
- [x] **2.3** Add mgmt setters: `set_class()`, `set_local_name()`, `set_ssp()`, `set_secure_connections()`, `set_le()`, `set_bredr()`, `set_privacy()`, `set_fast_connectable()`, `set_link_security()`, `set_wideband_speech()`
- [x] **Files Modified**: `bleep/dbuslayer/adapter.py` (+~120 lines)

### Phase 3: CLI Command
- [x] **3.1** Add `adapter-config` subparser with `show`, `get`, `set` sub-actions to `bleep/cli.py`
- [x] **3.2** Create `bleep/modes/adapter_config.py` with property routing (D-Bus writable → native, mgmt-only → subprocess)
- [x] **3.3** Implement `show` action: all D-Bus properties + writable property listing + `/etc/bluetooth/main.conf` boot defaults
- [x] **3.4** Implement `get` action: single property lookup with Class of Device pretty-printer
- [x] **3.5** Implement `set` action: automatic routing to D-Bus or mgmt based on property type
- [x] **Files Added**: `bleep/modes/adapter_config.py` (~325 lines)
- [x] **Files Modified**: `bleep/cli.py` (+18 lines)

### Phase 4: Boot Defaults Reader
- [x] **4.1** Implement `read_main_conf()` to parse `/etc/bluetooth/main.conf` (read-only, informational)
- [x] **4.2** Integrate into `adapter-config show` output

### Phase 5: Documentation
- [x] **5.1** Create `bleep/docs/adapter_config.md` with CLI reference, property tables, CoD values, Python API, architecture notes

### BlueZ Source Analysis (Reference)
- Examined `workDir/bluez/src/adapter.c` (adapter implementation, D-Bus property handlers)
- Examined `workDir/bluez/src/main.conf` (all configuration options with defaults)
- Examined `workDir/bluez/doc/org.bluez.Adapter.rst` (D-Bus API specification)
- Examined `workDir/bluez/client/main.c` (`bluetoothctl` main menu: `system-alias`, `set-alias`, `show`, `power`, `pairable`, `discoverable`)
- Examined `workDir/bluez/client/mgmt.c` (`bluetoothctl mgmt` submenu: `class`, `name`, `ssp`, `sc`, `le`, `bredr`, `privacy`)
- Confirmed: `bluetoothctl` main menu commands are D-Bus wrappers (no advantage over native D-Bus calls); mgmt submenu commands access the kernel management socket (not reachable via D-Bus)

---

## Audio Recon Augmentation (2026-02-28) – Completed

**Goal**: Incorporate audio reconnaissance capabilities into BLEEP while retaining the modular structure.

- [x] Sox-based analysis: `check_audio_file_has_content()` in `audio_tools.py` and preflight `sox` check
- [x] Per-profile enumeration: `get_bluez_cards()`, `get_profiles_for_card()`, `set_card_profile()`, `get_sources_and_sinks_for_card_profile()` with role mapping (microphone, headset_stream, speaker, interest)
- [x] Play/record via backend: `play_to_sink()`, `record_from_source()` (paplay/parecord or aplay/arecord)
- [x] Recon runner: `bleep/ble_ops/audio_recon.py` – `run_audio_recon()` with optional play, record, sox analysis, JSON out
- [x] CLI: `bleep audio-recon` and `bleep audio recon` with `--device`, `--test-file`, `--no-play`, `--no-record`, `--out`, `--record-dir`, `--duration`
- [x] Preflight: added `sox`, `paplay`, `pacmd` to audio tools
- [x] Documentation: `bleep/docs/audio_recon.md` with usage, result structure, and **detailed Future work** for Bonus Objectives

**Future work (Bonus Objectives)** is documented in **`bleep/docs/audio_recon.md`** (stream redirection, consolidate streams, play into streams, reconfig I/O, persist in observation DB). No duplicate tracking here – see that file for expansion steps.

---

## BlueALSA and PipeWire Tool Support (Completed)

> **Status**: Completed  
> **Created**: 2026-02-28  
> **Completed**: 2026-02-28  

### Background

BLEEP audio recon currently supports PulseAudio (`pactl`, `pacmd`, `paplay`, `parecord`) and basic ALSA utilities (`aplay`, `arecord`). Two additional tool families are known from real-world research but are not yet fully integrated:

1. **BlueZ ALSA (BlueALSA)** – a standalone ALSA back-end for BlueZ that exposes Bluetooth audio devices directly as ALSA PCM devices without requiring PulseAudio or PipeWire. This provides a simple, low-level interface for interacting with any Bluetooth audio device via standard ALSA utilities and `asound.conf`.
2. **PipeWire native tools** – while the current backend detection recognises PipeWire (via `pw-cli info`), per-profile enumeration and card manipulation still rely on the PulseAudio compatibility layer (`pactl`, `pacmd`). Native PipeWire tools (`pw-cli`, `pw-dump`, `pw-record`, `pw-play`, `wpctl`) may expose more information or behave differently on systems without the PulseAudio compatibility layer.

### Limitations (current state)

| Area | Current support | Gap |
|------|----------------|-----|
| **BlueALSA** | Not detected or used | No preflight check for `bluealsa-aplay`, `bluealsa-cli`, or BlueALSA PCM devices; no `asound.conf` integration |
| **PipeWire native** | Backend detected via `pw-cli info`; sinks/sources listed via `pw-cli list-objects` | Per-profile enumeration, card profile switching, and sources/sinks parsing all fall through to PulseAudio compat tools (`pactl`, `pacmd`); native `pw-dump` / `wpctl` not used |

### Plan

#### Phase A: BlueALSA support

- [x] **A-1**: Add preflight checks for BlueALSA tools: `bluealsa-aplay`, `bluealsa-cli`, `bluealsa-rfcomm` in `bleep/core/preflight.py`
- [x] **A-2**: In `AudioToolsHelper`, detect whether BlueALSA is running (`is_bluealsa_running()` via `bluealsa-cli list-pcms`)
- [x] **A-3**: Implement `list_bluealsa_pcms()` -- parse `bluealsa-cli list-pcms` output to enumerate Bluetooth ALSA PCM devices with MAC, profile, and direction (playback/capture)
- [x] **A-4**: Implement `play_to_bluealsa_pcm(pcm_id, file_path, duration_sec)` using `aplay -D <pcm>` and `record_from_bluealsa_pcm(pcm_id, output_path, duration_sec)` using `arecord -D <pcm>`
- [x] **A-5**: Wire BlueALSA path into `run_audio_recon()` as an alternative when PulseAudio/PipeWire are unavailable or when BlueALSA PCMs are detected alongside them
- [x] **A-6**: Document BlueALSA integration in `bleep/docs/audio_recon.md` (prerequisites, `asound.conf` considerations, limitations vs PulseAudio/PipeWire)

#### Phase B: PipeWire native tool support

- [x] **B-1**: Add preflight checks for PipeWire native tools: `pw-dump`, `pw-play`, `pw-record`, `wpctl` in `bleep/core/preflight.py`
- [x] **B-2**: Implement `_get_pipewire_bluez_nodes()` using `pw-dump` (JSON output) to enumerate Bluetooth nodes, their profiles, and audio routes without relying on PulseAudio compat
- [x] **B-3**: Implement `_set_pipewire_profile(node_id, profile_index)` using `wpctl set-profile`
- [x] **B-4**: Implement play/record paths using `pw-play` and `pw-record` as alternatives to `paplay`/`parecord`
- [x] **B-5**: In `get_audio_backend()`, differentiate `"pipewire_native"` (no PA compat) from `"pipewire"` (PA compat available) to select the correct tool path in recon
- [x] **B-6**: Update `run_audio_recon()` to use native PipeWire enumeration when PA compat tools are absent
- [x] **B-7**: Document PipeWire native support in `bleep/docs/audio_recon.md`

### Notes

- BLEEP's preferred approach is to use the lowest-level tools available (ALSA utilities); BlueALSA is an acceptable bridge between Bluetooth and ALSA. Higher-level servers (PulseAudio, PipeWire) are also supported because they provide richer visibility in many scenarios.
- Different tools yield different levels of visibility (e.g. BlueALSA exposes per-profile PCM devices directly; PulseAudio exposes cards with switchable profiles and sources/sinks; PipeWire native dumps expose the full graph as JSON). BLEEP should leverage whatever is available and document any visibility differences.

---

## BLEEP v2.5.0 Restructuring (Active)

> **Status**: Implementation Complete - Ready for Testing  
> **Created**: 2026-01-19  
> **Completed**: 2026-01-19  
> **Goal**: Address known issues and implement targeted improvements with minimal code duplication

### Background & Objectives

This restructuring addresses the following known issues:
1. **Device Type Identification** - Flawed distinction between Classic/LE/Dual devices
2. **Connectivity Issues** - Repeated connection attempts even when already connected; fickle BR/EDR connectivity
3. **Bluetooth Agent** - Skeleton implemented but method calls not producing operational logs
4. **Verbosity Control** - Overly verbose terminal output; capability to minimize verbosity appears un-implemented

### Evidence-Based Analysis Summary

**Critical Finding**: Extensive investigation revealed that most proposed functionality already exists in the codebase. The restructuring must leverage existing components rather than duplicate them.

| Component | Status | Location | Evidence |
|-----------|--------|----------|----------|
| Connection State Machine | **EXISTS** | `dbuslayer/device_le.py:111-513` | `_connection_state`, `_connection_state_lock`, `get_connection_state()` |
| Pairing State Machine | **EXISTS** | `dbuslayer/pairing_state.py` | Full `PairingStateMachine` class (539 lines) |
| Error/Metrics Tracking | **EXISTS** | `core/metrics.py:120-222` | `ErrorTracker`, `LatencyTracker`, `DBusMetricsCollector` |
| Landmine/Annotation Mapping | **EXISTS** | `dbuslayer/device_le.py:85-94, 1100-1500` | `_landmine_map`, `record_landmine()`, `update_mine_mapping()`, `get_landmine_report()` |
| Retry Logic | **EXISTS** | `core/utils.py:95-134` | `@retry_operation(max_attempts=3, delay=1.0)` decorator |
| Reconnection Monitor | **EXISTS** | `ble_ops/reconnect.py:27-285` | `ReconnectionMonitor` class with `max_attempts`, backoff, callbacks |
| Recovery Manager | **EXISTS** | `dbuslayer/recovery.py:34-476` | `ConnectionResetManager` with staged recovery, `DeviceStateTracker` |
| Verbosity Control | **EXISTS** | Multiple files | `--verbose`, `--debug`, `--quiet` flags; `agent_io.py:448` `self.verbose` |
| Tool Availability Checks | **SCATTERED** | `classic_sdp.py:222`, `classic_ping.py:14`, `classic_version.py:81` | `shutil.which()` calls for individual tools |
| Network Capability Script | **EXISTS** | `scripts/check_network_capabilities.py` | Full script (277 lines) for BlueZ network checks |
| Audio Tools | **MISSING** | N/A | No ALSA/PipeWire/PulseAudio integration exists |
| Preflight Consolidation | **NEEDED** | N/A | Checks scattered; needs single entry point |
| Enumeration Controller | **NEEDED** | N/A | Components exist; orchestration layer needed |
| Agent Verification | **NEEDED** | N/A | Agent exists; introspection verification missing |

### Implementation Plan (Minimal Approach)

#### Phase 1: Preflight Checks Consolidation
**Goal**: Create single entry point for environment capability checks

- [x] **1.1 Create `bleep/core/preflight.py`** (~100 lines)
  - [x] Import existing check patterns from `classic_sdp.py`, `classic_ping.py`, `classic_version.py`
  - [x] Add Bluetooth tool checks: `hciconfig`, `hcitool`, `bluetoothctl`, `btmgmt`, `sdptool`, `l2ping`
  - [x] Add Pulse Audio tool checks: `pactl`, `parecord`
  - [x] Add PipeWire tool checks: `pw-cli`, `pw-record`
  - [x] Add `/etc/bluetooth` config file detection
  - [x] Add BlueZ version detection (leverage `bluetoothctl --version`)
  - [x] Add Python dependency checks (`dbus`, `gi` versions)
  - [x] Create `run_preflight_checks() -> PreflightReport` function
  - [x] Create `print_preflight_summary()` for user-friendly output
  - [x] Design: Use singleton pattern to avoid repeated checks

- [x] **1.2 CLI Integration** (~10 lines in `cli.py`)
  - [x] Add `--check-env` flag to run preflight checks
  - [x] Add optional preflight on first run (store state in config)
  - [x] Log warnings for missing capabilities with actionable suggestions

**Files**: `bleep/core/preflight.py` (NEW), `bleep/cli.py` (MODIFY)

#### Phase 2: Audio Tools Helper
**Goal**: Create wrapper for ALSA/PipeWire/PulseAudio operations

- [x] **2.1 Create `bleep/ble_ops/audio_tools.py`** (~100 lines)
  - [x] Create `AudioToolsHelper` class
  - [x] Implement `get_audio_backend() -> str` ('pipewire', 'pulseaudio', 'none')
  - [x] Implement `list_audio_sinks() -> List[Dict]` (via `pactl` or `pw-cli`)
  - [x] Implement `list_audio_sources() -> List[Dict]`
  - [x] Implement `is_bluetooth_audio_available() -> bool`
  - [x] Add graceful degradation when tools unavailable
  - [x] Integration: Design for future A2DP sink/source integration

**Files**: `bleep/ble_ops/audio_tools.py` (NEW)

#### Phase 3: Connection State Guard
**Goal**: Prevent repeated connections when already connected

- [x] **3.1 Enhance `bleep/dbuslayer/device_le.py`** (~15 lines)
  - [x] Add guard in `connect()` method to check `_connection_state` before attempting connection
  - [x] Log warning if already connected: "Device {mac} already connected, skipping connect attempt"
  - [x] Return early with success if `_connection_state == "connected"` and D-Bus `Connected` property confirms
  - [x] Ensure thread-safety via existing `_connection_state_lock`

- [x] **3.2 Enhance `bleep/dbuslayer/device_classic.py`** (~10 lines)
  - [x] Add similar connection state guard for Classic devices
  - [x] Ensure parity with LE device behavior

**Files**: `bleep/dbuslayer/device_le.py` (MODIFY), `bleep/dbuslayer/device_classic.py` (MODIFY)

#### Phase 4: Agent Method Verification
**Goal**: Add introspection-based verification of agent method registration

- [x] **4.1 Enhance `bleep/dbuslayer/agent.py`** (~30 lines)
  - [x] Add `_verify_method_registration(self) -> bool` method to `BlueZAgent` class
  - [x] Use D-Bus introspection to verify methods are registered:
    ```python
    introspect_xml = dbus.Interface(
        self._bus.get_object(BLUEZ_SERVICE_NAME, self.agent_path),
        "org.freedesktop.DBus.Introspectable"
    ).Introspect()
    ```
  - [x] Check for required methods: `Release`, `AuthorizeService`, `RequestPinCode`, `RequestPasskey`, `DisplayPasskey`, `DisplayPinCode`, `RequestConfirmation`, `RequestAuthorization`, `Cancel`
  - [x] Log verification result with structured context
  - [x] Call verification after successful `register()` call

- [x] **4.2 Enhance `bleep/modes/agent.py`** (~10 lines)
  - [x] Add verification call after agent creation
  - [x] Log detailed status including introspection results
  - [x] Provide actionable warning if methods not registered

**Files**: `bleep/dbuslayer/agent.py` (MODIFY), `bleep/modes/agent.py` (MODIFY)

#### Phase 5: Enumeration Controller
**Goal**: Create orchestration layer using existing components for 3-attempt enumeration

- [x] **5.1 Create `bleep/ble_ops/enum_controller.py`** (~150 lines)
  - [x] Create `EnumerationController` class:
    ```python
    class EnumerationController:
        MAX_ATTEMPTS = 3
        def __init__(self, target_mac: str)
        def enumerate(self, mode: str = 'passive') -> EnumerationResult
    ```
  - [x] Create `EnumerationResult` dataclass:
    ```python
    @dataclass
    class EnumerationResult:
        success: bool
        data: Optional[Dict]  # Service/characteristic data
        annotations: List[Dict]  # Error annotations from landmine map
        error_summary: Optional[str]
        attempts: int
    ```
  - [x] Use existing `ReconnectionMonitor` from `ble_ops/reconnect.py`
  - [x] Use existing `ConnectionResetManager` from `dbuslayer/recovery.py`
  - [x] Use existing landmine mapping from `device_le.py`
  - [x] Implement `ErrorAction` enum:
    ```python
    class ErrorAction(Enum):
        RECONNECT = "reconnect"  # Timeout, disconnect
        ANNOTATE_AND_CONTINUE = "annotate_continue"  # Auth rejection
        GIVE_UP = "give_up"  # Agent required, repeated failures
    ```
  - [x] Implement `_handle_error(error: Exception) -> ErrorAction` method
  - [x] Implement `_should_continue() -> bool` (max 3 attempts)
  - [x] Collect annotations from each attempt for final report
  - [x] Return structured result with all annotations

- [x] **5.2 Integration with existing scan modes** (~20 lines)
  - [x] Update `ble_ops/scan.py` to optionally use `EnumerationController`
  - [x] Add `--controlled` flag to CLI for controlled enumeration mode
  - [x] Preserve backward compatibility (default behavior unchanged)

- [x] **5.3 Integration with AoI mode** (~20 lines)
  - [x] Update `modes/aoi.py` to use `EnumerationController` when iterating targets
  - [x] Collect annotations from each device for final report
  - [x] Ensure proper error handling and continuation

**Files**: `bleep/ble_ops/enum_controller.py` (NEW), `bleep/ble_ops/scan.py` (MODIFY), `bleep/modes/aoi.py` (MODIFY), `bleep/cli.py` (MODIFY)

#### ⚠️ Future Refactoring Required: Unified Connection Retry Logic

> **Status**: Deferred - Not for immediate implementation  
> **Priority**: High (for production readiness)  
> **Issue**: The current `--controlled` flag implementation adds bloat and creates a dual-path for connection attempts

**Problem Statement:**
The `--controlled` flag in `enum-scan` creates an optional, separate code path for multi-attempt enumeration. This is unacceptable for production because:
1. **Code Duplication**: Two different methods exist for the same operation (direct `_base_enum` vs `EnumerationController`)
2. **Maintenance Burden**: Future changes must be applied to both paths
3. **User Confusion**: Users must know about and remember to use `--controlled` flag
4. **Inconsistent Behavior**: Default behavior differs from controlled behavior

**Required Solution:**
BLEEP must have **one unified method** for performing multiple connection attempts when connecting to a device. The `EnumerationController` logic should become the **default and only** method for enumeration, not an optional flag.

**Action Items (Future):**
- [ ] Remove `--controlled` flag from CLI
- [ ] Make `EnumerationController` the default implementation in `_base_enum()` and all enum variants
- [ ] Refactor `connect_and_enumerate__bluetooth__low_energy()` to use `EnumerationController` internally
- [ ] Update all call sites to use the unified method
- [ ] Remove duplicate retry logic from other modules
- [ ] Ensure backward compatibility during transition (if needed)

**Note**: This refactoring should be done as a separate task after v2.5.0 is stable. The current implementation serves as a proof-of-concept but must not remain in production.

### File Summary

| File | Action | Estimated Lines |
|------|--------|-----------------|
| `bleep/core/preflight.py` | NEW | ~100 |
| `bleep/ble_ops/audio_tools.py` | NEW | ~100 |
| `bleep/ble_ops/enum_controller.py` | NEW | ~150 |
| `bleep/dbuslayer/device_le.py` | MODIFY | ~15 |
| `bleep/dbuslayer/device_classic.py` | MODIFY | ~10 |
| `bleep/dbuslayer/agent.py` | MODIFY | ~30 |
| `bleep/modes/agent.py` | MODIFY | ~10 |
| `bleep/ble_ops/scan.py` | MODIFY | ~20 |
| `bleep/modes/aoi.py` | MODIFY | ~20 |
| `bleep/cli.py` | MODIFY | ~20 |
| **TOTAL** | | **~475 lines** |

### Success Criteria

- [ ] **SC-1**: `bleep --check-env` produces complete capability report
- [ ] **SC-2**: Connection attempts to already-connected devices log warning and return early
- [ ] **SC-3**: Agent registration includes introspection verification with logged result
- [ ] **SC-4**: AoI scans with 3+ targets produce annotations for failed devices
- [ ] **SC-5**: All existing tests pass (no regressions)
- [ ] **SC-6**: No circular imports introduced
- [ ] **SC-7**: No duplicate functionality (verified against existing code)

### Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| Connection guard could break retry logic | Maintain `connect(retry=N)` signature; guard only prevents redundant initial connect |
| EnumerationController complexity | Build on existing `ReconnectionMonitor` and `ConnectionResetManager` |
| Circular imports | Use local imports inside functions (match existing patterns) |
| Agent verification failure | Don't fail registration; log warning only |

### Testing Strategy

- [ ] **Unit tests** for new modules (`preflight.py`, `audio_tools.py`, `enum_controller.py`)
- [ ] **Integration tests** for enumeration controller with mock device
- [ ] **Regression tests** ensuring existing functionality unchanged
- [ ] **Manual tests** with real Bluetooth devices (Classic and LE)

---

## Audio Capabilities Expansion (Active)

> **Status**: In Progress  
> **Created**: 2026-01-20  
> **Goal**: Expand audio capabilities to identify Bluetooth profiles via ALSA, enable audio playback/recording, and maintain separation between external tools and D-Bus interactions

### Background & Objectives

This expansion adds comprehensive audio capabilities to BLEEP:

1. **Profile Identification via ALSA** - Correlate ALSA/PulseAudio/PipeWire devices with Bluetooth profiles (A2DP, HFP, HSP)
2. **Enhanced ALSA Enumeration** - Direct ALSA device enumeration (bypassing PulseAudio/PipeWire when needed)
3. **Audio Codec Support** - GStreamer-based encoding/decoding for Bluetooth audio streaming
4. **Transport Acquisition & Streaming** - High-level APIs for audio playback and recording
5. **Maintain Architecture** - Strict separation: `audio_tools.py` = external tools only, `dbuslayer/` = D-Bus interactions

### Architecture Principles

- **Separation of Concerns**: 
  - `bleep/ble_ops/audio_tools.py` = External tool wrappers only (pactl, pw-cli, aplay, arecord, gst-launch-1.0)
  - `bleep/dbuslayer/media*.py` = D-Bus/BlueZ direct interactions
  - New modules for orchestration and correlation

- **Code Reuse**:
  - Use existing constants from `bleep/bt_ref/constants.py` and `bleep/bt_ref/uuids.py`
  - Leverage existing `MediaTransport`, `MediaEndpoint`, `MediaService` classes
  - GStreamer pipeline patterns were derived from the BlueZ example scripts (simple-asha, simple-endpoint, example-endpoint)

- **Dependency Management**:
  - Track GStreamer dependencies in `setup.py`
  - Add preflight checks for optional audio tools

### Implementation Plan

#### Phase 1: Enhanced ALSA/PulseAudio/PipeWire Enumeration
**Goal**: Extend `audio_tools.py` with ALSA enumeration and profile identification (external tools only)

- [x] **1.1 Enhance `bleep/ble_ops/audio_tools.py`** (~150 lines)
  - [x] Add `list_alsa_devices() -> List[Dict[str, Any]]` using `aplay -l` and `arecord -l` subprocess calls
  - [x] Add `get_alsa_device_info(device_name: str) -> Dict[str, Any]` using `aplay -D <device> --dump-hw-params`
  - [x] Add `extract_mac_from_alsa_device(device_name: str) -> Optional[str]` for MAC address extraction from device names
  - [x] Add `identify_bluetooth_profiles_from_alsa(mac_address: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]` for profile identification via pattern matching
  - [x] Ensure all methods use external tools only (no D-Bus interaction)
  - [x] Use existing constants from `bleep/bt_ref/uuids.py` for profile UUIDs

**Files**: `bleep/ble_ops/audio_tools.py` (MODIFY)

#### Phase 2: Profile Correlation Helper
**Goal**: Create module that correlates external tool output with D-Bus/BlueZ information

- [x] **2.1 Create `bleep/ble_ops/audio_profile_correlator.py`** (~200 lines)
  - [x] Create `AudioProfileCorrelator` class
  - [x] Implement `identify_profiles_for_device(mac_address: str) -> Dict[str, Any]` combining:
    - ALSA/PulseAudio device enumeration (from `audio_tools.py`)
    - BlueZ MediaTransport discovery (from `dbuslayer/media.py`)
  - [x] Implement `get_transport_for_profile(mac_address: str, profile_uuid: str) -> Optional[MediaTransport]`
  - [x] Import and use existing `MediaTransport` from `dbuslayer/media.py`
  - [x] Use existing constants from `bleep/bt_ref/constants.py` and `bleep/bt_ref/uuids.py`

**Files**: `bleep/ble_ops/audio_profile_correlator.py` (NEW)

#### Phase 3: Audio Codec Support
**Goal**: Create codec encoding/decoding module using GStreamer

- [x] **3.1 Create `bleep/ble_ops/audio_codec.py`** (~300 lines)
  - [x] Create `AudioCodecEncoder` class
  - [x] Add codec constants (SBC, MP3, AAC) - reuse from `bleep/dbuslayer/media_register.py` where possible
  - [x] Implement `encode_file_to_transport(input_file: str, output_fd: int, mtu: int, codec_config: Optional[bytes] = None) -> bool`
  - [x] Support both GStreamer Python bindings (preferred) and `gst-launch-1.0` subprocess (fallback)
  - [x] GStreamer pipeline patterns derived from BlueZ example scripts (simple-asha)
  - [x] Create `AudioCodecDecoder` class for recording
  - [x] Implement `decode_audio_stream(input_fd: int, output_file: str, codec: int, mtu: int) -> bool`
  - [x] Ensure no D-Bus interaction in this module

**Files**: `bleep/ble_ops/audio_codec.py` (NEW)

#### Phase 4: Audio Streaming Manager
**Goal**: Create high-level streaming orchestration in `dbuslayer`

- [x] **4.1 Create `bleep/dbuslayer/media_stream.py`** (~250 lines)
  - [x] Create `MediaStreamManager` class
  - [x] Implement `acquire_transport() -> Tuple[int, int, int]` using existing `MediaTransport.acquire()`
  - [x] Implement `play_audio_file(audio_file: str, volume: Optional[int] = None) -> bool` orchestrating:
    - Transport acquisition (D-Bus via `MediaTransport`)
    - Volume setting (D-Bus via `MediaTransport.set_volume()`)
    - Audio encoding (delegates to `audio_codec.py`)
    - Transport release (D-Bus via `MediaTransport.release()`)
  - [x] Implement `record_audio(output_file: str, duration: Optional[int] = None) -> bool`
  - [x] Use existing `find_media_devices()` from `dbuslayer/media.py`
  - [x] Use existing `MediaTransport` class methods
  - [x] Use existing constants from `bleep/bt_ref/constants.py`

**Files**: `bleep/dbuslayer/media_stream.py` (NEW)

#### Phase 5: Dependencies and Preflight
**Goal**: Track dependencies and add preflight checks

- [x] **5.1 Update `setup.py`** (~20 lines)
  - [x] Add GStreamer Python bindings as optional dependency (via PyGObject)
  - [x] Add to `extras_require` if system-installed
  - [x] Document GStreamer plugin requirements in comments

- [x] **5.2 Update `bleep/core/preflight.py`** (~30 lines)
  - [x] Add `aplay` and `arecord` to `_check_audio_tools()`
  - [x] Add `gst-launch-1.0` check
  - [x] Add GStreamer Python bindings check (try/except import)
  - [x] Update `PreflightReport` to include new audio tools

**Files**: `setup.py` (MODIFY), `bleep/core/preflight.py` (MODIFY)

#### Phase 6: CLI Integration
**Goal**: Add CLI commands and optional mode module

- [x] **6.1 Update `bleep/cli.py`** (~50 lines)
  - [x] Add `audio-profiles` command for profile identification
  - [x] Add `audio-play` command for audio file playback
  - [x] Add `audio-record` command for audio recording
  - [x] Integrate with existing CLI argument parsing patterns

- [x] **6.2 Create `bleep/modes/audio.py`** (~200 lines)
  - [x] Create mode module following existing pattern (like `bleep/modes/media.py`)
  - [x] Implement `list_audio_profiles(mac_address: Optional[str] = None) -> None`
  - [x] Implement `play_audio_file(mac_address: str, file_path: str, **kwargs) -> bool`
  - [x] Implement `record_audio(mac_address: str, output_path: str, **kwargs) -> bool`
  - [x] Use `AudioProfileCorrelator` and `MediaStreamManager`

**Files**: `bleep/cli.py` (MODIFY), `bleep/modes/audio.py` (NEW)

### File Summary

| File | Status | Lines | Purpose |
|------|--------|-------|---------|
| `bleep/ble_ops/audio_tools.py` | MODIFY | +150 | Enhanced ALSA enumeration (external tools only) |
| `bleep/ble_ops/audio_profile_correlator.py` | NEW | ~200 | Correlate external tools + D-Bus |
| `bleep/ble_ops/audio_codec.py` | NEW | ~300 | GStreamer codec encoding/decoding |
| `bleep/dbuslayer/media_stream.py` | NEW | ~250 | High-level streaming orchestration |
| `bleep/modes/audio.py` | NEW | ~200 | CLI mode module |
| `bleep/cli.py` | MODIFY | +50 | New CLI commands |
| `setup.py` | MODIFY | +20 | Dependency tracking |
| `bleep/core/preflight.py` | MODIFY | +30 | GStreamer checks |

### Success Criteria

- [ ] **SC-1**: `audio_tools.py` remains external-tools-only (no D-Bus interaction)
- [ ] **SC-2**: Profile identification correlates ALSA devices with BlueZ profiles
- [ ] **SC-3**: ALSA enumeration works via external tools (`aplay`, `arecord`)
- [ ] **SC-4**: Transport acquisition uses existing `MediaTransport` class
- [ ] **SC-5**: Codec encoding uses GStreamer (external tool or Python bindings)
- [ ] **SC-6**: Audio playback/recording orchestrated via `media_stream.py`
- [ ] **SC-7**: All constants use existing definitions (no duplication)
- [ ] **SC-8**: Dependencies tracked in `setup.py` and `preflight.py`
- [ ] **SC-9**: Separation maintained: external tools vs D-Bus interactions
- [ ] **SC-10**: CLI commands work for common use cases

### Dependencies & Risks

**External Dependencies:**
- GStreamer 1.0+ with Python bindings (`python3-gst-1.0` or `gi.repository.Gst`)
- GStreamer plugins: `gstreamer1.0-plugins-base`, `gstreamer1.0-plugins-good`, `gstreamer1.0-plugins-bad`
- ALSA tools: `alsa-utils` (aplay, arecord) - optional

**Python Packages:**
- `PyGObject>=3.48.0` (already in setup.py) - provides GStreamer Python bindings

**Risks:**
- GStreamer availability varies by system
- Codec support depends on installed plugins
- Transport state management complexity

**Mitigation:**
- Graceful degradation if GStreamer unavailable
- Preflight checks warn about missing dependencies
- Fallback to subprocess if Python bindings unavailable

### Testing Strategy

- [ ] **Unit tests** for `audio_tools.py` ALSA enumeration methods
- [ ] **Unit tests** for `audio_profile_correlator.py` correlation logic
- [ ] **Unit tests** for `audio_codec.py` encoding/decoding (with mock GStreamer)
- [ ] **Integration tests** for `media_stream.py` with mock transports
- [ ] **End-to-end tests** with real Bluetooth devices (playback and recording)
- [ ] **Regression tests** ensuring existing functionality unchanged

---

## UUID and Codec Constants Centralization (Active)

> **Status**: Implementation Complete  
> **Created**: 2026-01-20  
> **Completed**: 2026-01-20  
> **Goal**: Centralize all UUID and codec constants in a single location to minimize hardcoded values and create a "single source of truth"

### Background & Objectives

This refactoring addresses the issue of duplicated UUID and codec constants scattered across multiple modules:

1. **Profile UUIDs** were defined in 7+ locations (constants.py, media_register.py, media_stream.py, audio_profile_correlator.py, audio_tools.py, device_classic.py, plus hardcoded values)
2. **Codec constants** were defined in 3+ locations (media_register.py, audio_codec.py, audio_profile_correlator.py)
3. **Hardcoded values** throughout the codebase increased maintenance burden and risk of inconsistencies

### Implementation Plan

#### Phase 1: Create Centralized Constants
**Goal**: Extend `bleep/bt_ref/constants.py` with audio profile UUIDs and codec constants

- [x] **1.1 Add Audio Profile UUID Constants** (~30 lines)
  - [x] Add A2DP_SOURCE_UUID, A2DP_SINK_UUID
  - [x] Add HFP_HANDS_FREE_UUID, HFP_AUDIO_GATEWAY_UUID
  - [x] Add HSP_AUDIO_GATEWAY_UUID, HSP_HEADSET_UUID
  - [x] Add AUDIO_PROFILE_NAMES dictionary mapping UUIDs to human-readable names
  - [x] Add get_profile_name() helper function

- [x] **1.2 Add Audio Codec Constants** (~30 lines)
  - [x] Add SBC_CODEC_ID, MP3_CODEC_ID, AAC_CODEC_ID, etc.
  - [x] Add CODEC_NAMES dictionary mapping codec IDs to names
  - [x] Add get_codec_name() helper function
  - [x] Document references (A2DP Specification, BlueZ documentation)

**Files**: `bleep/bt_ref/constants.py` (MODIFY)

#### Phase 2: Update All Modules to Use Centralized Constants
**Goal**: Remove duplicate definitions and update all references

- [x] **2.1 Update `bleep/dbuslayer/media_register.py`**
  - [x] Remove A2DP_SOURCE_UUID, A2DP_SINK_UUID class constants
  - [x] Remove SBC_CODEC class constant
  - [x] Import from bleep.bt_ref.constants
  - [x] Update SBC_CODEC to use SBC_CODEC_ID

- [x] **2.2 Update `bleep/dbuslayer/media_stream.py`**
  - [x] Remove A2DP_SINK_UUID, A2DP_SOURCE_UUID class constants
  - [x] Import from bleep.bt_ref.constants
  - [x] Import get_codec_name helper

- [x] **2.3 Update `bleep/ble_ops/audio_codec.py`**
  - [x] Remove SBC_CODEC, MP3_CODEC, etc. module constants
  - [x] Remove CODEC_NAMES dictionary
  - [x] Remove get_codec_name() function
  - [x] Import all from bleep.bt_ref.constants
  - [x] Add backward compatibility aliases (SBC_CODEC = SBC_CODEC_ID)
  - [x] Update all codec comparisons to use *_CODEC_ID constants

- [x] **2.4 Update `bleep/ble_ops/audio_profile_correlator.py`**
  - [x] Remove PROFILE_UUID_MAP class constant
  - [x] Remove CODEC_NAMES class constant
  - [x] Import AUDIO_PROFILE_NAMES, CODEC_NAMES, get_profile_name, get_codec_name
  - [x] Update all references to use centralized constants

- [x] **2.5 Update `bleep/ble_ops/audio_tools.py`**
  - [x] Remove profile_uuid_map local dictionary
  - [x] Import AUDIO_PROFILE_NAMES, A2DP_SINK_UUID, A2DP_SOURCE_UUID, etc.
  - [x] Update profile_patterns to use centralized UUID constants
  - [x] Replace hardcoded default UUIDs with constants
  - [x] Update profile_name lookups to use get_profile_name()

- [x] **2.6 Update `bleep/dbuslayer/device_classic.py`**
  - [x] Replace hardcoded UUID strings with constants
  - [x] Import A2DP_SINK_UUID, HFP_HANDS_FREE_UUID

**Files**: 6 files modified

#### Phase 3: Validation and Testing
**Goal**: Ensure no regressions and verify all imports work

- [x] **3.1 Code Validation**
  - [x] Run linter to check for errors
  - [x] Verify no circular imports
  - [x] Check for remaining hardcoded UUIDs/codecs

- [x] **3.2 Documentation Updates**
  - [x] Update todo_tracker.md with implementation details
  - [x] Update changelog.md with changes

**Files**: Documentation files

### File Summary

| File | Status | Lines Changed | Purpose |
|------|--------|---------------|---------|
| `bleep/bt_ref/constants.py` | MODIFY | +80 | Added centralized audio constants |
| `bleep/dbuslayer/media_register.py` | MODIFY | -3, +4 | Use centralized constants |
| `bleep/dbuslayer/media_stream.py` | MODIFY | -2, +1 | Use centralized constants |
| `bleep/ble_ops/audio_codec.py` | MODIFY | -30, +15 | Use centralized constants, add aliases |
| `bleep/ble_ops/audio_profile_correlator.py` | MODIFY | -20, +1 | Use centralized constants |
| `bleep/ble_ops/audio_tools.py` | MODIFY | -15, +10 | Use centralized constants |
| `bleep/dbuslayer/device_classic.py` | MODIFY | -2, +1 | Use centralized constants |

### Success Criteria

- [x] **SC-1**: All UUID constants defined in single location (`bleep/bt_ref/constants.py`)
- [x] **SC-2**: All codec constants defined in single location (`bleep/bt_ref/constants.py`)
- [x] **SC-3**: No hardcoded UUID strings remain in audio-related modules
- [x] **SC-4**: No hardcoded codec IDs remain in audio-related modules
- [x] **SC-5**: All modules import from centralized location
- [x] **SC-6**: Helper functions (get_codec_name, get_profile_name) available from constants
- [x] **SC-7**: No linting errors introduced
- [x] **SC-8**: Backward compatibility maintained (aliases for old constant names)

### Benefits

1. **Single Source of Truth**: All constants in one location
2. **Easier Maintenance**: Update values in one place
3. **Consistency**: No risk of mismatched values across modules
4. **Type Safety**: Constants prevent typos
5. **Documentation**: Clear references to specifications
6. **Helper Functions**: Centralized utility functions reduce duplication

### Dependencies & Risks

**Risks:**
- Circular imports (mitigated by importing from bt_ref which has no dependencies)
- Breaking changes (mitigated by backward compatibility aliases)
- Missing constants (mitigated by comprehensive audit)

**Mitigation:**
- Incremental migration (one module at a time)
- Comprehensive testing after each phase
- Backward compatibility aliases

---

## Classic Bluetooth UUID Enhancement for Device Type Classification (Active)

> **Status**: Implementation Complete - Ready for Testing  
> **Created**: 2026-01-19  
> **Completed**: 2026-01-19  
> **Updated**: 2026-01-19 (UUID Relocation)  
> **Goal**: Incorporate Classic Bluetooth UUIDs (especially Service Discovery Server) into device type classification with proper weight assignment

### Background & Objectives

Enhance device type classification by:
1. Adding missing ESP SSP UUID (0xABF0) to constants
2. Detecting Service Discovery Server (0x1000) as CONCLUSIVE evidence for Classic devices
3. Maintaining existing STRONG weight for other Classic service UUIDs
4. Leveraging existing UUID extraction/matching functionality (no duplication)

### Evidence-Based Analysis Summary

**Critical Finding**: UUID extraction and matching already works perfectly. No need for duplicate constants.

| Component | Status | Location | Evidence |
|-----------|--------|----------|----------|
| UUID Extraction (16-bit from 128-bit) | **EXISTS** | `device_type_classifier.py:348-349` | `classic_short_uuids.add(classic_normalized[4:8])` |
| UUID Normalization | **EXISTS** | `uuid_utils.py:39`, `uuid_translator.py:162` | Extracts 16-bit from 128-bit BT SIG format |
| UUID Matching (16-bit & 128-bit) | **EXISTS** | `device_type_classifier.py:370-382` | Handles both formats via `identify_uuid()` |
| Classic UUID Constants | **EXISTS** | `bt_ref/uuids.py:1313-1390` | `SPEC_UUID_NAMES__SERV_CLASS` contains all UUIDs in 128-bit format |
| ESP SSP UUID | **MISSING** | N/A | 0xABF0 not in `SPEC_UUID_NAMES__SERV_CLASS` |
| Service Discovery Server Weight | **NEEDS UPDATE** | `device_type_classifier.py:396` | Currently STRONG, should be CONCLUSIVE |

**UUIDs Already Present in `SPEC_UUID_NAMES__SERV_CLASS`:**
- ✅ Service Discovery Server (0x1000): `"00001000-0000-1000-8000-00805f9b34fb"`
- ✅ Serial Port Profile (0x1101): `"00001101-0000-1000-8000-00805f9b34fb"`
- ✅ Audio Source (0x110A): `"0000110a-0000-1000-8000-00805f9b34fb"`
- ✅ Audio Sink (0x110B): `"0000110b-0000-1000-8000-00805f9b34fb"`
- ✅ A2DP (0x110D): `"0000110d-0000-1000-8000-00805f9b34fb"`
- ✅ Handsfree Audio Gateway (0x111F): `"0000111f-0000-1000-8000-00805f9b34fb"`
- ❌ ESP SSP (0xABF0): **MISSING**

### Implementation Plan (Minimal Approach)

#### Phase 1: Add Missing UUID Constant
**Goal**: Add ESP SSP (0xABF0) to `SPEC_UUID_NAMES__SERV_CLASS`

- [x] **1.1 Update `bleep/bt_ref/uuids.py`** (~1 line)
  - [x] Add entry: `"0000abf0-0000-1000-8000-00805f9b34fb" : "ESP SSP",`
  - [x] Place in appropriate location within `SPEC_UUID_NAMES__SERV_CLASS` dictionary (alphabetically or by UUID value)

**Files**: `bleep/bt_ref/uuids.py` (MODIFY)

#### Phase 2: Enhance Device Type Classifier
**Goal**: Detect Service Discovery Server with CONCLUSIVE weight

- [x] **2.1 Update `ClassicServiceUUIDsCollector.collect()` method** (~25 lines in `device_type_classifier.py`)
  - [x] Add helper method `_is_service_discovery_server(uuid: str) -> bool`:
    - [x] Use `identify_uuid()` to normalize UUID
    - [x] Check if short form (16-bit) is `"1000"`
    - [x] Handle both 16-bit (`"1000"`, `"0x1000"`) and 128-bit formats
  - [x] During UUID matching loop, check if Service Discovery Server is found
  - [x] If Service Discovery Server detected:
    - [x] Add evidence with `EvidenceWeight.CONCLUSIVE` (separate from other Classic UUIDs)
    - [x] Include metadata: `{"is_service_discovery_server": True, "uuid": uuid_str}`
  - [x] For other Classic UUIDs, keep existing `EvidenceWeight.STRONG` behavior

- [x] **2.2 Update Classification Logic** (~5 lines in `device_type_classifier.py`)
  - [x] Modify `_classify_classic()` to accept `CLASSIC_SERVICE_UUIDS` with CONCLUSIVE weight as conclusive evidence
  - [x] Update `_classify_dual()` to recognize CONCLUSIVE Classic service UUID evidence
  - [x] Update `_generate_reasoning()` to mention "Service Discovery Server detected" when present

**Files**: `bleep/analysis/device_type_classifier.py` (MODIFY)

### File Summary

| File | Action | Estimated Lines |
|------|--------|-----------------|
| `bleep/bt_ref/uuids.py` | MODIFY | ~1 |
| `bleep/analysis/device_type_classifier.py` | MODIFY | ~30 |
| **TOTAL** | | **~31 lines** |

### Success Criteria

- [x] ESP SSP (0xABF0) added to `SPEC_UUID_NAMES__SERV_CLASS`
- [x] Service Discovery Server (0x1000) detected with `CONCLUSIVE` weight
- [x] Other Classic UUIDs remain `STRONG` weight (no regression)
- [x] Classification logic recognizes CONCLUSIVE Classic service UUID evidence
- [x] Both 16-bit and 128-bit UUID formats handled (no changes needed - already works)
- [x] No duplicate constants added (leverages existing `SPEC_UUID_NAMES__SERV_CLASS`)
- [ ] No regressions in existing device type classification (pending testing)

### Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| Service Discovery Server detection could fail for some UUID formats | Use existing `identify_uuid()` function which handles all formats |
| Classification logic change could affect existing behavior | Only add CONCLUSIVE as additional path, don't remove STRONG path |
| ESP SSP UUID placement could break alphabetical ordering | Place in appropriate location (after 0x111F or maintain existing order) |

### Testing Strategy

- [ ] **Unit tests** for Service Discovery Server detection (16-bit and 128-bit formats)
- [ ] **Integration tests** with devices advertising Service Discovery Server
- [ ] **Regression tests** ensuring other Classic UUIDs still work with STRONG weight
- [ ] **Manual tests** with real Bluetooth Classic devices

---

## UUID Relocation and Constant Reference Enhancement (Active)

> **Status**: Implementation In Progress  
> **Created**: 2026-01-19  
> **Goal**: Relocate ESP SSP UUID to persistent location and reference Service Discovery Server UUID via constants

### Background & Objectives

Address two issues identified after initial implementation:
1. **ESP SSP UUID Persistence**: ESP SSP (0xABF0) was added to auto-generated `bleep/bt_ref/uuids.py`, which will be overwritten during regeneration
2. **Hardcoded UUID Reference**: `_is_service_discovery_server()` function hardcodes `"1000"` instead of referencing a constant

### Implementation Plan

#### Phase 1: Relocate ESP SSP UUID
**Goal**: Move ESP SSP from auto-generated file to persistent custom UUID storage

- [ ] **1.1 Remove ESP SSP from `bleep/bt_ref/uuids.py`** (~1 line)
  - [ ] Remove entry: `"0000abf0-0000-1000-8000-00805f9b34fb" : "ESP SSP",` from `SPEC_UUID_NAMES__SERV_CLASS`

- [ ] **1.2 Add ESP SSP to `bleep/bt_ref/constants.py`** (~1 line)
  - [ ] Add entry to `UUID_NAMES` dictionary: `"0000abf0-0000-1000-8000-00805f9b34fb": "ESP SSP",`
  - [ ] Location: After line 178 (end of `UUID_NAMES` dictionary)

**Files**: `bleep/bt_ref/uuids.py` (MODIFY), `bleep/bt_ref/constants.py` (MODIFY)

#### Phase 2: Add Service Discovery Server Constant Reference
**Goal**: Replace hardcoded "1000" with constant reference

- [ ] **2.1 Add constant to `bleep/bt_ref/constants.py`** (~1 line)
  - [ ] Add: `SERVICE_DISCOVERY_SERVER_UUID_16 = "1000"` in "# Common Service/Characteristic UUIDs" section
  - [ ] Location: After line 186

- [ ] **2.2 Update `_is_service_discovery_server()` function** (~2 lines in `device_type_classifier.py`)
  - [ ] Add import: `from bleep.bt_ref.constants import SERVICE_DISCOVERY_SERVER_UUID_16`
  - [ ] Replace: `sds_short = "1000"` with `sds_short = SERVICE_DISCOVERY_SERVER_UUID_16`

**Files**: `bleep/bt_ref/constants.py` (MODIFY), `bleep/analysis/device_type_classifier.py` (MODIFY)

### File Summary

| File | Action | Estimated Lines |
|------|--------|-----------------|
| `bleep/bt_ref/uuids.py` | MODIFY | -1 (remove ESP SSP) |
| `bleep/bt_ref/constants.py` | MODIFY | +2 (ESP SSP + SDS constant) |
| `bleep/analysis/device_type_classifier.py` | MODIFY | +2 (import + constant reference) |
| **TOTAL** | | **~3 net lines** |

### Success Criteria

- [x] ESP SSP removed from auto-generated `uuids.py`
- [x] ESP SSP accessible via `constants.UUID_NAMES`
- [x] `SERVICE_DISCOVERY_SERVER_UUID_16` constant defined and accessible
- [x] `_is_service_discovery_server()` uses constant instead of hardcoded value
- [x] UUID translator can find ESP SSP in custom UUIDs database
- [ ] No regressions in device type classification (pending testing)

### Rationale

- **ESP SSP Persistence**: Custom UUIDs belong in `constants.UUID_NAMES` which is not auto-generated, ensuring persistence across UUID database regenerations
- **Constant Reference**: Eliminates hardcoded magic string, improves maintainability, and follows BLEEP's pattern of centralizing constants
- **Minimal Approach**: Only adds 16-bit constant (not 128-bit) since function only uses 16-bit form; 128-bit already exists in `SPEC_UUID_NAMES__SERV_CLASS` if needed elsewhere

---

### High-level backlog (copy + paste from sources)

- [ ] **Debug mode: Classic keep-alive command** (Partially Complete - Requires Further Work)
  - [x] Implement `ckeep` command to open/close RFCOMM socket for ACL keep-alive
  - [x] Support `--first`, `--svc NAME`, and numeric channel selectors
  - [x] Remove duplicated `ckeep` logic blocks (ensure single execution path)
  - [x] Preserve BlueZ `org.bluez.Error.Failed` message detail (e.g. `br-connection-unknown`) in Bleep errors/logs
  - [x] Auto-close socket on `quit`
  - [x] Update help banner & changelog
  - [ ] **Further work required**: Full functionality testing and validation blocked by Classic device connection issues. Requires a Bluetooth Classic target device with no pairing/PIN requirements to properly validate RFCOMM socket operations and ACL keep-alive functionality. Error handling and logging are functional; core connection/socket operations need validation with appropriate hardware.

- [x] **Agent + AgentManager verbosity / diagnosability checklist**
  - [x] **`bleep/dbuslayer/agent.py`**: Improve AgentManager registration error detail
    - [x] Include D-Bus error name + message (`get_dbus_name`, `get_dbus_message`) in failures from `_setup_agent_manager()`
    - [x] Include agent path + capabilities + default-agent flag in failures from `register()`
    - [x] Log failures at `LOG__AGENT` with structured context (agent_path, capabilities, default)
  - [x] **`bleep/core/errors.py`**: Preserve message payload for agent-relevant D-Bus exceptions
    - [x] Ensure `org.bluez.Error.*` mappings keep `exc.get_dbus_message()` when present (NotPermitted, NotAuthorized, Failed, InProgress)
    - [x] Ensure `UnknownObject` includes target path (when available) for agent/device operations (D-Bus message preserves path information)
  - [x] **`bleep/modes/agent.py`**: Fix agent-mode correctness + improve CLI visibility
    - [x] Fix indentation so `create_agent()` is called for all agent types (not just a branch) - verified correct indentation
    - [x] Log the exact chosen agent type + cap + default + auto_accept + agent_path
  - [x] **`bleep/dbuslayer/device_classic.py` + `bleep/dbuslayer/device_le.py`**: Improve connect/pair failure context
    - [x] On DBusException, log method invoked + device path + adapter + D-Bus error name/message
    - [x] Ensure mapped exceptions preserve D-Bus message text
  - [x] **`bleep/dbuslayer/agent_io.py`**: Increase IO handler context
    - [x] When prompting/auto-accepting, log handler type + auto_accept/default values used (no secrets)
  - [x] **`bleep/modes/debug.py`**: Add agent status / control commands (debug-only)
    - [x] `agent status` (show whether default agent registered, cap, path)
    - [x] `agent register [--interactive|--auto] [--cap ...] [--default]`
    - [x] `agent unregister`
  - [x] **Error clarity expansion (post-agent)**
    - [x] `bleep/core/errors.py`: include `exc.get_dbus_message()` in default fall-through mapping
    - [x] `bleep/dbuslayer/media_services.py`: replace `str(e)` logging with `name: message` and avoid silent bool-only failures
    - [x] `bleep/dbuslayer/media_browse.py`: replace `str(e)` logging with `name: message` and avoid silent empty-list/None masking
    - [x] `bleep/dbuslayer/obex_pbap.py`: preserve D-Bus name/message in raised RuntimeError diagnostics
    - [x] `bleep/dbuslayer/manager.py`: log underlying D-Bus name/message when StartDiscovery falls back

- [x] **PIN Code Request Visibility and Diagnostic Enhancements** - **COMPLETE** (Diagnostic capabilities implemented; core issue remains)
  - [x] **Phase 1: Fix Communication Type Logging** - Fixed D-Bus communication type labeling (METHOD CALL vs SIGNAL)
  - [x] **Phase 2: Enhanced Agent Method Invocation Detection** - Added method invocation tracking and capability validation
  - [x] **Phase 3: Enhanced Event Correlation** - Automatic RequestPinCode → Cancel correlation with root cause analysis
  - [x] **Phase 4: Root Cause Analysis Summary** - Automated failure summaries with actionable recommendations
  - [x] **Phase 5: Agent Registration Status Verification** - Registration status tracking and warnings
  - [x] **Phase 6: Destination Match Diagnostic Logging** - Bus unique name logging and destination verification
  - [ ] **Core Issue Remaining**: D-Bus methods not registered on D-Bus (introspection returns empty XML). See `agent_dbus_communication_issue.md` for details.

- [x] **Unified D-Bus Event Aggregator (Phase 2A - Reorganized)**
  - [x] **`bleep/dbuslayer/signals.py`**: Create unified event capture and aggregation system
    - [x] Create `DBusEventCapture` dataclass to replace separate `SignalCapture` and `MethodCallCapture` (unified structure for signals, method calls, method returns, errors)
    - [x] Create `DBusEventAggregator` class for centralized event storage and correlation
    - [x] Add unified event tracking to `__init__` (`_event_aggregator`, `_unified_monitoring`, `_unified_message_filter`)
    - [x] Implement `_on_dbus_message(bus, message)` unified handler for all D-Bus message types
    - [x] Implement `_is_relevant_message()` filter to identify BlueZ/Agent related messages
    - [x] Implement `_capture_signal()`, `_capture_method_call()`, `_capture_method_return()`, `_capture_error()` type-specific capture methods
    - [x] Implement `_log_event()` with human-readable + detailed format (follows error handling pattern)
    - [x] Implement `enable_unified_dbus_monitoring(enabled, filters)` public API method
    - [x] Implement `_attach_unified_listeners()` to add match strings for all message types (signals, method calls, returns, errors)
    - [x] Implement `_detach_unified_listeners()` for cleanup
    - [x] Implement query methods: `get_recent_events()`, `correlate_event()`, `get_method_call_chain()`
    - [x] Update `_detach_bus_listeners()` to also detach unified listeners
    - [x] Handle `DBusException` gracefully (eavesdrop may require root/policy changes; don't fail agent registration)
    - [x] Maintain backward compatibility: keep existing `enable_agent_method_call_monitoring()` as wrapper (deprecated)
    - [x] Update `SignalCorrelator` integration for backward compatibility
  - [x] **`bleep/dbuslayer/agent.py`**: Integrate unified monitoring with agent lifecycle
    - [x] Update `register()` method to use `enable_unified_dbus_monitoring()` instead of method call only
    - [x] Add error handling to continue agent registration if monitoring fails
    - [x] Document optional disable in `unregister()` (keep enabled for general system monitoring)
  - [x] **Testing & Verification**
    - [x] Test signal capture (PropertiesChanged, InterfacesAdded/Removed)
    - [x] Test method call capture (Agent1, AgentManager1, Device1 methods)
    - [x] Test method return capture (verify serial number correlation)
    - [x] Test error capture (AuthenticationRejected, Failed, etc.)
    - [x] Test correlation: method call → return/error chains via serial numbers
    - [x] Test correlation: path-based relationships across event types
    - [x] Test query methods with various filters (event_type, interface, path, time_window)
    - [x] Test `get_method_call_chain()` for complete call → return/error sequences
    - [x] Compare output against `dbus-monitor --system "destination='org.bluez'" "sender='org.bluez'"` for accuracy
    - [x] Verify human-readable summary format matches error handling pattern (`name: msg`)
    - [x] Verify detailed information preserves original message for analysis
    - [x] Test monitoring with/without root permissions (graceful degradation)
    - [x] Verify backward compatibility with existing signal capture code

- [x] **Error clarity expansion — phase 2 (Task A + Task B planning)**
  - [x] **Task A: Silent failure audit + targeted verbosity upgrades (no API break)**
    - [x] Inventory remaining `DBusException` handlers that return `False`/`None`/`[]` or log only `str(e)`
    - [x] Prioritize high-impact call paths: `dbus/device.py`, `dbuslayer/media.py`, `dbuslayer/characteristic.py`, `dbuslayer/service.py`, `dbuslayer/descriptor.py`, `ble_ops/*`
    - [x] For each target, add structured context to logs (operation + object path + `name: message`) without changing return types/raising behaviour
    - [x] Verify: `py_compile` + run the narrowest relevant tests after each file
    - [x] Continue follow-up pass: `bleep/dbuslayer/device_le.py`, `bleep/dbuslayer/device_classic.py`, `bleep/dbuslayer/agent.py`, `bleep/dbuslayer/manager.py`, then `bleep/ble_ops/*`
  - [x] **Task B: Error mapping consolidation (safety-first; no behaviour drift)**
    - [x] **B0: Contracts + intent (lock down before changing behavior)** *(starting point)*
      - [x] Document `bt_ref/error_map.py` tuple contract: `map_dbus_error(DBusException)->(code, category)`, `handle_error(Exception, device)->(code, recovered)`
      - [x] Confirm meaning of `recovered=True`: recovery action executed successfully (does **not** imply original operation retried)
      - [x] Confirm recovery remains category-based (connection/state/protocol only) and does not trigger for permission/resource categories
      - **Evidence / current call sites**:
        - `bleep/bt_ref/error_map.py`:
          - `map_dbus_error()` returns `(result_code, category)` where `result_code` is from `DBUS_ERROR_MAP` (default `RESULT_EXCEPTION`) and `category` is derived from `ERROR_CATEGORIES`.
          - `handle_error()` returns `(result_code, recovered)` where `recovered=True` only if a recovery strategy exists for the derived category *and* it executes successfully (no automatic retry of the original failing operation).
          - Recovery strategies are currently **category-based**:
            - `connection` → `_reconnect_device(device)` (calls `device.Connect()`)
            - `state` → `_resolve_services(device)` (calls `device.check_and_wait__services_resolved()`)
            - `protocol` → `_retry_with_delay()` (fixed sleep)
            - `permission` / `resource` / `unknown` → **no recovery**
        - `bleep/dbus/device.py` uses the tuple contract directly:
          - `Connect/Disconnect/Pair` catch `Exception` and return `handle_error(e, self)` (tuple passthrough to callers).
          - `_setup_device()` logs `result_code` via `map_dbus_error(e)` (tuple) for diagnostics only.
    - [x] **B1: Build an evidence “truth table”** comparing `core/error_handling.decode_dbus_error` vs `bt_ref/error_map` mappings and their current call sites
      - **Truth table snapshot (name-level mapping differences)**:
        - `core/error_handling.decode_dbus_error` (name-map `_DBUS_ERROR_NAME_MAP`, default `RESULT_ERR`, plus message-substring heuristics)
        - `bt_ref/error_map.map_dbus_error` (name-map `DBUS_ERROR_MAP`, default `RESULT_EXCEPTION`, no message-substring heuristics)
        - **Known mismatches (must be resolved before bt_ref delegates to core)**:
          - `org.bluez.Error.NotPermitted`: core → `RESULT_ERR_NOT_PERMITTED`; bt_ref → `RESULT_ERR_ACCESS_DENIED` (category=permission either way; reporting code differs)
          - `org.bluez.Error.NotAuthorized`: core → `RESULT_ERR_NOT_AUTHORIZED`; bt_ref → default `RESULT_EXCEPTION` (unmapped today)
          - `org.freedesktop.DBus.Error.InvalidArgs`: bt_ref → `RESULT_ERR_BAD_ARGS`; core → not name-mapped today (falls back to message heuristics / `RESULT_ERR`)
          - `org.freedesktop.DBus.Error.AccessDenied`: bt_ref → `RESULT_ERR_ACCESS_DENIED`; core → not name-mapped today (falls back to `RESULT_ERR`)
          - `org.freedesktop.DBus.Error.ServiceUnknown`: bt_ref → `RESULT_ERR_UNKNOWN_SERVCE`; core → not name-mapped today (falls back to `RESULT_ERR`)
          - `org.bluez.Error.NotAvailable` / `org.bluez.Error.DoesNotExist`: bt_ref → `RESULT_ERR_NOT_FOUND`; core → not name-mapped today (falls back to `RESULT_ERR`)
          - `org.bluez.Error.NotFound`: core → `RESULT_ERR_NOT_FOUND`; bt_ref → default `RESULT_EXCEPTION` (unmapped today)
          - `org.bluez.Error.InvalidArguments`: core → `RESULT_ERR_BAD_ARGS`; bt_ref → default `RESULT_EXCEPTION` (unmapped today)
        - **Message-heuristic capability (core-only)**:
          - core can map `"read/write/notify/indicate not permitted"` → operation-specific `RESULT_ERR_*_NOT_PERMITTED` codes; bt_ref currently cannot.
      - **Truth table snapshot (call-site split)**:
        - bt_ref tuple interface used directly by: `bleep/dbus/device.py` (`handle_error(e, self)` return path; tuple passthrough)
        - exception interface used by most refactored stack: `bleep/core/errors.py::map_dbus_error` (returns `BLEEPError` subclasses, uses core decode internally)
    - [x] **B1.1: Expand `core/error_handling.decode_dbus_error` (single source of truth)**
      - [x] Expand name-level mapping to cover bt_ref’s existing `DBUS_ERROR_MAP` names (and any additional names observed in code/logs)
      - [x] Keep message-substring heuristics (read/write/notify/indicate not permitted, etc.) and document precedence (name > message > fallback)
      - [x] Verify core name-map becomes a superset of bt_ref needs (or explicitly justify omissions)
      - **Precedence (must remain stable):**
        - **1) Name-level mapping wins** (`exc.get_dbus_name()` in `_DBUS_ERROR_NAME_MAP`)
        - **2) Message-level mapping** for permission granularity (`exc.get_dbus_message()` substrings like read/write/notify/indicate not permitted)
        - **3) Fallback** to `RESULT_ERR` when no match
    - [x] **B2: Augment `bt_ref/error_map.py` to always use core decode (preserve tuple + recovery semantics)**
      - [x] Implement “core-first decode” inside bt_ref with local imports (avoid import loops)
      - [x] Add bt_ref-local refinement for cases where core returns generic codes but bt_ref can be more specific using `get_dbus_name()` / `get_dbus_message()`
      - [x] Introduce “reporting_code vs category_code” normalization so bt_ref can keep precise codes while preserving recovery categorization
      - [x] Ensure no caller changes required initially (especially `bleep/dbus/device.py`)
      - **Verification notes**:
        - No call-site changes were required: `bleep/dbus/device.py` continues to import `handle_error` / `map_dbus_error` from `bleep.bt_ref.error_map`.
        - Added unit coverage: `tests/test_bt_ref_error_map.py` exercises bt_ref core-first decode + normalization behavior.
    - [x] **B3: Recovery semantics + retry discipline (avoid device “busy” amplification)**
      - [x] **Do not hammer**: when re-attempting any failed operation, apply a **fixed wait** before retrying (default: 0.5–1.0s) to let the target/device stack settle
      - [x] **Prefer waiting over retrying** when the failure indicates the device is still processing (e.g., `InProgress`, “Operation already in progress”, transient controller/stack teardown)
      - [x] **Cap retries**: keep retry counts low (e.g., 1–3) and fail fast for permission/argument errors (never retry those)
      - [x] **Categorize before retry**: only connection/state/protocol categories may trigger recovery; permission/resource should not auto-retry
      - [x] **No implicit “retry original op” loops** without an explicit fixed-delay policy (prevents cascading errors on fragile devices)
      - [x] Audit gaps in recovery strategies (missing cases, missing staged waits, device/controller stall handling)
      - [x] Plan (and later implement) an explicit “retry original operation” wrapper that uses fixed-delay policy and low retry caps (do **not** bake infinite loops into low-level helpers)
      - **Implemented (bt_ref-level helper, conservative by default):**
        - `bleep/bt_ref/error_map.py::attempt_operation_with_recovery()`:
          - fixed delay between attempts (default 0.7s)
          - low retry cap (default 2)
          - never retries deterministic failures (permission/bad args/not supported)
      - **Recovery gap found + fixed:**
        - `_reconnect_device()` previously treated tuple-return interfaces as “success” even when `(code, False)` was returned; now treats that as failure so `recovered` is accurate.
    - [x] **B4: BLEEPError transparency audit (no “blanding” / no hidden payloads)**
      - [x] Inventory `BLEEPError` subclass mappings that override/replace DBus messages; ensure D-Bus `name` + `message` remain visible
      - [x] Confirm `core/errors.py::map_dbus_error` does not force generic messages when actionable D-Bus payload exists (e.g., BlueZ `org.bluez.Error.Failed` message bodies)
      - **Fixes applied + coverage**:
        - `NotAuthorizedError` now accepts an optional `reason` and preserves the D-Bus message payload in the exception string.
        - `ServiceUnknown` mapping now uses the D-Bus message payload (when present) instead of repeating the error name.
        - `UnknownObject` mapping no longer forces `DeviceNotFoundError("D-Bus operation")`; it preserves `name: message` as a `BLEEPError` to avoid blanding/misclassification.
        - Fixed `handle_dbus_exception()` to raise the mapped `BLEEPError` (it previously attempted to unpack a non-tuple result).
        - Added unit coverage: `tests/test_core_errors_transparency.py`
    - [x] **B5: Deprecation + cleanup (remove legacy requirements safely)**
      - [x] After parity proven, deprecate bt_ref’s independent name→code table as a *source of truth* (keep only category/refinement logic if needed)
      - [x] **B5.2: Reduce reliance on legacy tuple-path modules** (COMPLETE - Option A executed)
        - [x] Evaluate deprecating `bleep/dbus/device.py` in favor of refactored device wrappers (`bleep/dbuslayer/device_le.py`, `bleep/dbuslayer/device_classic.py`)
        - **Status**: COMPLETE - Legacy module removed (Option A: direct removal)
        - **Phase 1 audit results** (completed):
          * **Static analysis**: AST-based import analysis found zero imports of `bleep.dbus.device` in all Python files within `bleep/` directory
          * **Runtime verification**: No imports detected when loading key entrypoints (`bleep.modes.debug`, `bleep.modes.agent`, `bleep.ble_ops.connect`, `bleep.dbuslayer.device_le`, `bleep.core.device_management`)
          * **Package structure**: `bleep/dbus/__init__.py` does NOT include `device` in `__all__`, confirming it's not intentionally exposed
          * **Actual usage**: All code imports from `bleep.dbuslayer.device_le`, NOT from `bleep.dbus.device`
          * **Conclusion**: `bleep/dbus/device.py` was completely unused - no artifacts of importing the file remained in the codebase
        - **Migration executed**: **Option A (Direct Removal)**
          * Deleted `bleep/dbus/device.py` (~214 lines, tuple-return contract implementation)
          * Verified no regressions: all key entrypoints import successfully after removal
          * No changes needed to `bleep/dbus/__init__.py` (device was never in `__all__`)
          * Documentation updated (changelog, todo tracker)
        - **Current state analysis**:
          - **Legacy module** (`bleep/dbus/device.py`): ~214 lines, tuple-return contract `(code, success)`, minimal features, uses `bt_ref.error_map`
            * Public interface: `Connect() -> Tuple[int, bool]`, `Disconnect() -> Tuple[int, bool]`, `Pair() -> Tuple[int, bool]`
            * Properties: `address`, `adapter`, `connected`, `paired`, `services_resolved`
            * Methods: `find_and_get__device_property()`, `find_and_get__all_device_properties()`, `check_and_wait__services_resolved()`
          - **Refactored modules**: `bleep/dbuslayer/device_le.py` (~2400+ lines), `bleep/dbuslayer/device_classic.py` (~750+ lines), exception-based contract, rich feature set
            * Exception-based error handling via `bleep.core.errors.map_dbus_error()` (returns `BLEEPError` subclasses)
            * Rich features: GATT enumeration, service resolution, media support, signal handling, reconnection monitoring
            * Method-based property access: `is_connected()`, `is_paired()`, `is_trusted()`, etc.
          - **Key interface differences**:
            * Method names: `Connect()` vs `connect()` (case-sensitive; legacy uses PascalCase)
            * Return types: `Tuple[int, bool]` (legacy) vs raises `BLEEPError` subclasses (refactored)
            * Property access: `device.connected` (property in legacy) vs `device.is_connected()` (method in refactored)
            * Error handling: `handle_error()` tuple return with automatic recovery (legacy) vs exception-based with explicit caller handling (refactored)
            * Parameter names: `bluetooth_adapter` (legacy) vs `adapter_name` (refactored)
        - **Preliminary findings**:
          - `bleep/dbus/device.py` appears unused (no direct imports found in codebase; only mentioned in comments in `bleep/dbus/__init__.py`)
          - Refactored `bleep/dbuslayer/device_le.py` is what's actually used throughout the codebase
          - `bleep/dbuslayer/device.py` re-exports the refactored classes
        - **4-Phase plan structure** (evaluation-first; no code changes until audit complete):
          - **Phase 1: Comprehensive usage audit** (no code changes):
            * Static analysis: grep for all import patterns (`from bleep.dbus.device import`, `import bleep.dbus.device`, dynamic imports via `importlib`/`__import__`)
            * Runtime verification: import tracking script to verify no `bleep.dbus.device` imports occur during key entrypoint loading
            * Interface contract comparison: side-by-side method signature documentation, parameter differences, return type differences
            * Error handling contract analysis: tuple-return semantics vs exception-based semantics, recovery strategy differences
          - **Phase 2: Migration strategy design**:
            * Decision tree based on audit findings:
              - **Option A (if unused)**: Direct removal of `bleep/dbus/device.py`, update `bleep/dbus/__init__.py`, remove documentation references
              - **Option B (if callers exist)**: Compatibility shim in `bleep/dbus/device.py` wrapping refactored device, converting exceptions to tuples, maintaining legacy interface
              - **Option C (if gaps exist)**: Feature parity enhancement in refactored modules, then re-evaluate migration
            * Compatibility shim design (if Option B): adapter class pattern converting `BLEEPError` exceptions to `(code, False)` tuples, preserving exact method signatures
          - **Phase 3: Implementation**:
            * Pre-migration validation: create comprehensive test suite for legacy interface, run both legacy and refactored test suites
            * Migration execution: execute chosen option (A, B, or C), add unit tests for shim (if applicable), run integration tests
            * Post-migration validation: full test suite, verify import behavior, check for performance regressions
          - **Phase 4: Documentation and deprecation**:
            * Code documentation: deprecation notices (if shim used), migration path documentation, type hint updates
            * Project documentation: update `bleep/docs/changelog.md`, update `bleep/docs/todo_tracker.md`, create migration guide (if callers exist)
        - **Migration options** (decision based on Phase 1 findings):
          - **Option A (Recommended if unused)**: Direct removal of `bleep/dbus/device.py`
            * Delete file, remove from `bleep/dbus/__init__.py` exports, update documentation, add changelog notice
          - **Option B (If callers exist)**: Compatibility shim wrapping refactored device
            * Implement adapter class in `bleep/dbus/device.py` that wraps `bleep.dbuslayer.device_le.system_dbus__bluez_device__low_energy`
            * Convert `BLEEPError` exceptions to `(code, False)` tuples, maintain exact method signatures (`Connect`, `Disconnect`, `Pair`)
            * Preserve property access patterns, handle edge cases (e.g., `check_and_wait__services_resolved` return type)
            * Document as temporary compatibility layer, create migration tracking for callers
          - **Option C (If gaps exist)**: Feature parity enhancement
            * Identify missing functionality in refactored modules, implement missing features, add tests, re-run Phase 1 audit
        - **Risk areas and mitigation**:
          - **Hidden dynamic imports**: `importlib.import_module('bleep.dbus.device')`, `__import__('bleep.dbus.device')` might not be caught by static analysis
            * Mitigation: Runtime import tracking script, comprehensive test suite execution
          - **Runtime behavior differences**: Tuple-return vs exception-based contracts have different error handling semantics
            * Mitigation: Side-by-side test suite execution, behavior comparison documentation
          - **Property vs method access**: Legacy uses properties (`device.connected`), refactored uses methods (`device.is_connected()`)
            * Mitigation: Compatibility shim (Option B) can provide property access via `@property` decorators
          - **Recovery semantics**: Legacy `handle_error()` provides automatic recovery; refactored stack requires explicit caller handling
            * Mitigation: Document recovery differences, provide migration guide for callers
        - **Success criteria** (per phase):
          - **Phase 1**: Complete usage audit with zero ambiguity about `bleep/dbus/device.py` usage, interface contract comparison document created, migration strategy decision (A, B, or C) made
          - **Phase 2**: Migration strategy fully designed and documented, compatibility shim designed with full interface mapping (if Option B), test plan created for validation
          - **Phase 3**: Migration executed (removal, shim, or feature parity), all tests pass (no regressions), performance validated (no significant degradation)
          - **Phase 4**: Documentation updated (code docs, project docs), deprecation notices in place (if applicable), changelog and todo tracker updated, Task B5.2 marked complete
        - **Timeline estimate**: 6-16 hours total
          * Phase 1 (Audit): 2-4 hours
          * Phase 2 (Design): 1-2 hours
          * Phase 3 (Implementation): 2-8 hours (depends on chosen option)
          * Phase 4 (Documentation): 1-2 hours
        - **Dependencies**: Task B0-B5 complete (error mapping consolidation provides foundation), comprehensive test suite for refactored device wrappers, access to test devices (for integration testing, if needed)
        - **Approval required**: This plan must be accepted before any code modifications are made. Evaluation-first approach: no code changes until usage audit (Phase 1) is complete and migration strategy is approved.
      - [x] Consolidate duplicate error logic within `core/error_handling.py` (decode tables vs other internal message maps) so there is truly one source of truth
      - **Deprecation markers added:**
        - `bleep/bt_ref/error_map.py::DBUS_ERROR_MAP` now marked as deprecated (only used for refinement fallback when core returns generic RESULT_ERR).
        - `bleep/core/error_handling.py::system_dbus__error_handling_service.evaluate__dbus_error()` marked as deprecated with TODO for consolidation.
        - Added canonical decoder documentation in `core/error_handling.py` identifying consolidation opportunities.
      - **Legacy module removal (B5.2) - COMPLETE:**
        - `bleep/dbus/device.py` has been removed after comprehensive audit confirmed zero usage
        - All codebase now uses refactored device wrappers (`bleep/dbuslayer/device_le.py`, `bleep/dbuslayer/device_classic.py`)
        - No compatibility shim needed - module was completely unused
    - [x] **Import-loop safety requirement (must not regress):**
      - [x] Keep imports one-directional: `core/error_handling` should not import `core/errors` at module import time
      - [x] Prefer local imports inside mapping functions to avoid circular dependencies (match existing style in `map_dbus_error`)
      - [x] Validate by running `python -m py_compile` and by importing key entrypoints (`bleep.modes.debug`, `bleep.modes.agent`, `bleep.ble_ops.connect`) in a fresh interpreter
      - **Verification complete:**
        - `core/error_handling.py` does NOT import `core/errors` at module level (only imports from `bt_ref` and `core.log`).
        - `bt_ref/error_map.py::map_dbus_error()` uses local import: `from bleep.core.error_handling import decode_dbus_error` (inside function).
        - All key entrypoints import successfully without circular dependency errors.

- [x] **Legacy Code Removal & Self-Sufficiency** – Complete removal of legacy dependencies (v2.3.1, 2025-10-29):
  - [x] Removed `sys.modules` shims in `bleep/__init__.py` for root-level legacy imports
  - [x] Deleted root-level legacy shim files (`bluetooth_constants.py`, `bluetooth_utils.py`, `bluetooth_uuids.py`, `bluetooth_exceptions.py`)
  - [x] Removed deprecated `bleep.compat.py` module (unused internally)
  - [x] Removed legacy namespace shim `Functions.ble_ctf_functions` from `ctf.py`
  - [x] Made PyGObject optional in `setup.py` (moved to `extras_require["monitor"]`)
  - [x] Added YAML cache files to `package_data` for complete package distribution
  - [x] Achieved complete codebase self-sufficiency with no dependencies on root-level legacy files
  - [x] Updated changelog with breaking changes and migration notes
  - [x] All internal imports now use proper paths (`from bleep.bt_ref import constants`)

- [x] **Documentation** – User mode guide completed (docs/user_mode.md)
- [x] **Assets-of-Interest (AoI) workflow**
  - [x] Implement analysis layer (`bleep/analysis/aoi_analyser.py`) converting (device,mapping,…) into actionable report
  - [x] Persist enumeration JSON dumps (`~/.bleep/aoi/*.json`) for offline analysis
  - [x] Integrate analyser into `modes/aoi.py` & debug shell (`aoi` command)
  - [x] Write dedicated documentation `docs/aoi_mode.md` (+ examples)
  - [x] Update CLI quick-start table (docs/cli_usage.md)
  - [x] Add entry to changelog on release
  - [x] Fix AoI implementation issues:
    - [x] Add missing `analyze_device_data` bridge method
    - [x] Fix service and characteristic data handling for different formats
    - [x] Improve error handling and type checking
    - [x] Resolve method name inconsistencies
  - [x] Enhance AoI documentation and capabilities:
    - [x] Document basic CLI commands and parameters
    - [x] Document security analysis features and report formats
    - [x] Explain JSON file format options and data storage
    - [x] Create programmatic API reference for AOIAnalyser class (`docs/aoi_implementation.md`)
    - [x] Add troubleshooting section and best practices
    - [x] Create comprehensive test suite for AoI functionality
    - [x] Document testing procedures in `docs/aoi_testing.md`
    - [x] Add integration examples with observation database
    - [x] Document advanced security analysis algorithms (see `aoi_security_algorithms.md`)
    - [x] Create customization guide for security assessment criteria (see `aoi_customization_guide.md`)
- [x] Multi-read / brute-write characteristic helpers complete
  - [x] `multi_read_characteristic` utility (repeat reads)
  - [x] `multi_read_all` rounds helper
  - [x] Configurable `brute_write_range` respecting landmine map

- [x] Implement passive / naggy / pokey / brute scan variants complete
  - [x] Enumeration variants unifying 4-tuple return complete:
    1. Δ `enum_helpers.py` – add `small_write_probe`, payload generator
    2. Δ `ble_ops/scan.py` – re-implement `naggy_enum`, `pokey_enum`, `brute_enum`
    3. Δ `cli.py` – flags for brute (`--range`, `--patterns`, `--payload-file`, `--force`, `--verify`)
    4. Δ `modes/debug.py` – aliases `enum`, `enumn`, `enump`, `enumb`
    5. ⊕ `tests/test_enum_helpers.py` – mock device read/write to verify behaviour
    6. Δ Docs (`ble_scan_modes.md`) – enumeration section & safety notes
    7. Δ `modes/debug.py` – enumeration command integration (enum/enumn/enump/enumb)
      - [x] D-2 implement `_enum_common` dispatcher
      - [x] D-3 wrapper commands & `_CMDS` entries (flags parsing verified)
      - [x] D-4 parse extra flags (`--force`, `--verify`, range) in debug shell
      - [x] D-5 robust error handling & state tracking (mine/perm maps, summaries)
      - [x] D-6 unit tests `tests/test_debug_enum_cmds.py`
      - [x] D-7 docs: debug enumeration examples
  - **Design overview for Enumeration Modes**
    - *Passive* – read-only enumeration, automatic reconnect/back-off; failures recorded in landmine/permission maps, no writes ever.
    - *Naggy*  – same read path but retries stubborn elements until root-cause (auth, permissions) classified; still write-free.
    - *Pokey*  – after read pass, attempt single-byte writes to advertised writable characteristics to probe accessibility without altering real data.
    - *Bruteforce* – exhaustive write fuzz: iterate payload patterns over every writable characteristic, monitoring side-effects; most intrusive.
  - **Implementation notes**
    - Re-use existing device.read_/write_characteristic helpers and error-handling.
    - Mode flag wired in CLI (`bleep scan --mode ...`) and Debug aliases.
    - Each mode builds on previous: Passive → Naggy (extra retry loop) → Pokey (adds light write) → Bruteforce (full write fuzz).
    - Adhere to minimal-diff guideline; wrappers delegate to shared core functions.
  - **Testing strategy**
    - Unit tests with stub device (like brute helpers) for retries & write attempts.
    - Integration tests rely on ENV `SCAN_TEST_MAC` when hardware present.
  - **Implementation task map for scan modes**
    1. Δ `bleep/ble_ops/scan.py`
       - add `naggy_scan`, `pokey_scan`, `brute_scan` thin wrappers (≤45 LOC).
    2. Δ `bleep/cli.py`
       - extend `scan` sub-parser with `--mode`, dispatch table.
       - validate `--target` required for *pokey*.
    3. Δ `bleep/modes/debug.py`
       - add aliases: `scann`, `scanp`, `scanb` and help lines.
    4. ⊕ `tests/test_scan_variants.py` – mock adapter verifies filter & loop counts ✅
    5. Δ Docs (`README`, `bl_classic_mode.md`)
       - small feature table row + CLI examples.

---

## Media-layer gap-analysis tasks (pending)

- [x] **Media1 service wrappers** – `bleep/dbuslayer/media_services.py` created (registration helpers). *(Phase 1)*
- [x] **MediaFolder & MediaItem browsing** – `bleep/dbuslayer/media_browse.py` added. *(Phase 1)*
- [x] **Extended enumeration utility** – `find_media_objects()` implemented. *(Phase 2)*
- [x] **MediaRegisterHelper** – SBC sink/source helper added. *(Phase 3)*
- [x] **Integration hooks** – `--objects` flag in `bleep/modes/media.py`. *(Phase 4)*
- [x] **Documentation & tests** – media_mode docs + pytest helper tests added.

- [x] **AoI Test Suite Fixes**
  - [x] Fix "unhashable type: 'dict'" errors in AoI analyzer:
    - [x] Update `analyse_device` method in `aoi_analyser.py` to handle dictionary keys properly
    - [x] Ensure all dictionary keys used in lookups are hashable types (strings, numbers, tuples)
    - [x] Add proper type checking before dictionary operations
  - [x] Fix JSON serialization errors with bytes objects:
    - [x] Create a custom JSON encoder class in `aoi_analyser.py` to handle bytes objects
    - [x] Update `save_device_data` method to use the custom encoder
    - [x] Convert bytes to hex strings during serialization
  - [x] Implement proper database error handling in CLI commands:
    - [x] Add device existence check before storing AoI analysis
    - [x] Create minimal device entries when analyzing unknown devices
    - [x] Add graceful error handling for foreign key constraint failures
    - [x] Provide user-friendly error messages instead of raw database errors
  - [x] Fix report generation failures:
    - [x] Ensure report templates handle missing or incomplete data
    - [x] Add fallback mechanisms for report generation when analysis data is incomplete
    - [x] Fix file path handling for report output
  - [x] Enhance test environment setup:
    - [x] Create proper test fixtures for AoI integration tests
    - [x] Implement database pre-population for required test data
    - [x] Add cleanup mechanisms to ensure test isolation

- [x] **Fix Agent Mode CLI Routing & Argument Exposure** – Critical bug fix for agent mode CLI:
  - [x] **Issue**: Agent mode routing broken due to argparse subparser argument name conflict - `args.mode == "agent"` check never matches because `args.mode` is overwritten by `--mode` argument value. CLI parser only exposes 2 of 12 agent features (`--mode` limited to simple/interactive), and argument passing is broken (only passes `--mode`, missing all other arguments).
  - [x] **Solution**: Fixed routing detection in `bleep/cli.py` line 702 by changing `elif args.mode == "agent":` to `elif len(sys.argv) > 1 and sys.argv[1] == "agent":` and pass `sys.argv[2:]` to agent mode. Expanded CLI parser arguments in `bleep/cli.py` lines 72-95 to include all agent mode options: `--mode` (added enhanced/pairing), `--cap`, `--default`, `--auto-accept`, `--pair`, `--trust`, `--untrust`, `--list-trusted`, `--list-bonded`, `--remove-bond`, `--storage-path`, `--timeout`. Arguments are parsed for help/validation but passed through to agent mode's parser for actual processing.
  - [x] **Files**: `bleep/cli.py` (lines 72-95, 702-706)
  - [x] **Testing**: Verified `bleep agent --mode=pairing --pair=MAC`, `bleep agent --list-trusted`, `bleep agent --trust=MAC` all work correctly. Verified other modes unaffected.

- [x] **Enhance Pairing Agent**
  - [x] **Phase 1: Agent Architecture** (2 weeks)
    - [x] Design Enhanced Agent Framework
      - [x] Support for multiple capability levels (DisplayOnly, DisplayYesNo, KeyboardOnly, NoInputNoOutput, KeyboardDisplay)
      - [x] Design flexible IO handler interface for different interaction modes
      - [x] Create state management for multi-step pairing processes
    - [x] Design persistent trusted device storage
      - [x] Define secure storage for paired device credentials
      - [x] Create migration path for existing paired devices
    - [x] Implement agent registration system
      - [x] Support registration with different capability levels based on context
      - [x] Implement proper agent release on shutdown
    - [x] Agent Manager Integration
      - [x] Implement proper integration with org.bluez.AgentManager1
      - [x] Support RegisterAgent method with proper capability arguments
      - [x] Handle RequestDefaultAgent correctly
      - [x] Add proper error handling for agent registration failures
  - [x] **Phase 2: Core Agent Methods** (3 weeks)
    - [x] Implement the full org.bluez.Agent1 interface:
      - [x] Release: Handle agent release requests
      - [x] RequestPinCode: Request PIN code for legacy pairing
      - [x] DisplayPinCode: Show PIN code to user
      - [x] RequestPasskey: Request passkey for SSP pairing
      - [x] DisplayPasskey: Show passkey with entered digits count
      - [x] RequestConfirmation: Handle numeric comparison pairing
      - [x] RequestAuthorization: Process authorization requests
      - [x] AuthorizeService: Control service-level authorization
      - [x] Cancel: Handle request cancellation
    - [x] Add support for Secure Simple Pairing (SSP)
      - [x] Implement numeric comparison workflow
      - [x] Add just-works pairing mode
      - [x] Support passkey entry method
    - [x] Implement service-level authorization
      - [x] Create authorization rules framework
      - [x] Add per-service authorization options
    - [x] Add support for automatic re-authentication
      - [x] Store bonding information securely
      - [x] Implement LTK (Long Term Key) management
  - [x] **Phase 3: User Interface Integration** (2 weeks)
    - [x] Create CLI prompts for agent interactions
      - [x] Implement passkey entry prompts
      - [x] Add confirmation dialogs for pairing requests
      - [x] Show PIN codes and passkeys when required
      - [x] Add cancel command for ongoing pairing operations
    - [x] Integrate agent with debug mode
      - [x] Add `pair [device_address]` command
      - [x] Add `unpair [device_address]` command
      - [x] Add `trust [device_address]` command
      - [x] Add `untrust [device_address]` command
    - [x] Integrate agent with user mode
      - [x] Create simplified pairing UX for non-expert users
      - [x] Add pairing status indicators
      - [x] Implement pairing request notifications
  - [x] **Phase 4: Reliability Enhancements** (2 weeks)
    - [x] Add agent connection monitoring
      - [x] Detect D-Bus disconnections
      - [x] Implement automatic re-registration after BlueZ restart
    - [x] Implement pairing timeout management
      - [x] Add configurable timeouts for different pairing operations
      - [x] Create timeout recovery strategies
    - [x] Handle incomplete pairing sessions
      - [x] Detect and recover from stalled pairing attempts
      - [x] Add cleanup for abandoned pairing sessions
    - [x] Enhance error reporting
      - [x] Create human-friendly error messages for common pairing failures
      - [x] Add diagnostic information for troubleshooting
      - [x] Create recovery suggestions for pairing errors
    - [x] Add pairing diagnostics tooling
      - [x] Create `check-pairing [device_address]` command
      - [x] Implement pairing capability detection for devices
      - [x] Add verbose logging option for pairing process
  - [x] **Phase 5: Documentation & Testing** (1 week)
    - [x] Create comprehensive documentation
      - [x] Update `docs/pairing_agent.md` with usage guide
      - [x] Document pairing troubleshooting steps
      - [x] Add examples for different pairing scenarios
      - [x] Document programmatic API for pairing agent
    - [x] Create test suite for pairing functionality
      - [x] Create mock device for agent interface testing
      - [x] Add integration tests for real device pairing
      - [x] Test edge cases for pairing failures
      - [x] Verify recovery mechanisms
- [x] **Device-feature database (SDP & PBAP)** - **COMPLETE**
  * Merge existing bullet *"Local database for unknown UUIDs + device observations"* – expand scope to store:
    * SDP service/attribute snapshots per device (Classic & BLE) ✅
    * PBAP phonebook metadata (repository sizes, Hash of full dump) ✅
    * First-seen / last-seen timestamps, adapter used, friendly names ✅
  * Decide storage: simple SQLite in `~/.bleep/observations.db` (no runtime deps)  **(SPEC FINAL 2025-07-24)** ✅
  * CLI helpers: `bleep db list|show|export <MAC>` ✅
  * Schema + ingestion implementation (v0)
    - [x] `core/observations.py` singleton connection + schema creation
    - [x] `upsert_device`, `insert_adv`, `upsert_services`, `upsert_characteristics`
    - [x] Hook `_native_scan` for adv inserts & device UPSERT
    - [x] Hook `_base_enum` for service / characteristic inserts
    - [x] Snapshot helpers for Media (`snapshot_media_player`, `snapshot_media_transport`)
    - [x] Unit tests `tests/test_observations_sqlite.py`
  * CLI (read-only phase-1)
    - [x] `db` sub-command in `cli.py` with actions `list-devices`, `show-device`, `export`
    - [x] Enhanced DB query methods: `get_devices`, `get_device_detail`, `get_characteristic_timeline`, `export_device_data`
    - [x] Support for filtering devices by status (recent, ble, classic, media)
    - [x] Timeline filtering by service and characteristic UUIDs
    - [x] Docs update (`cli_usage.md`, `README.md`, `observation_db.md`)
  * Schema migrations:
    - [x] v1 to v2: Renamed problematic column names to avoid Python keyword conflicts
      - `class` → `device_class` in devices table
      - `state` → `transport_state` in media_transports table
    - [x] Implemented migration code with backward compatibility
    - [x] Completed full v2 schema transition by removing all v1 schema code
    - [x] Removed all v1 schema compatibility code (codebase now exclusively uses v2 schema)
    - [x] v2 to v3: Added device_type field for improved device classification 
      - Added constants for device types: unknown, classic, le, dual
      - Enhanced device type detection with multiple heuristics
      - Updated filtering logic to use explicit device_type
  * Future telemetry table & migrations – tracked separately  
  * **SDP service/attribute snapshots storage** - **COMPLETE**:
    - [x] Create `sdp_records` table to store full SDP record snapshots (Service Record Handle, Profile Descriptor List, Service Version, Service Description, Protocol Descriptor List, raw record)
    - [x] Implement `upsert_sdp_record()` function in `bleep/core/observations.py`
    - [x] Hook SDP discovery functions to store full records (`discover_services_sdp()`, `_discover_services_dbus()`, connectionless mode)
    - [x] Update `get_device_detail()` and `export_device_data()` to include SDP records (automatic via get_device_detail)
    - [x] Create schema migration v6→v7 for new `sdp_records` table
    - [x] Update documentation (`observation_db.md`, `observation_db_schema.md`) to include `sdp_records` table
    - [x] **Note**: Both `classic_services` (basic UUID/channel mapping) and `sdp_records` (full snapshots) tables coexist for different use cases
  * Write migration note – **COMPLETE**:
    - [x] Added v6→v7 migration notes to schema documentation
    - [x] Migration history documented in `observation_db_schema.md`
  * Device type classification improvements:
    - [x] **Dual Device Detection Framework (Completed)** – Comprehensive evidence-based classification system:
      - [x] Plan created for modular, expandable dual device detection framework (superseded by `bleep/docs/device_type_classification.md`)
      - [x] Design includes database-first performance optimization with signature caching
      - [x] Design includes mode-aware classification (passive/naggy/pokey/bruteforce)
      - [x] Design includes code reuse leveraging existing SDP, GATT, and database functions
      - [x] Design includes stateless classification to prevent false positives from MAC collisions
      - [x] Phase 1: Core framework implementation (DeviceTypeClassifier module) - COMPLETED
        - [x] Created `bleep/analysis/device_type_classifier.py` module (~800 lines)
        - [x] Implemented `EvidenceType` and `EvidenceWeight` enums
        - [x] Implemented `EvidenceSet` class for evidence collection
        - [x] Implemented `ClassificationResult` class for results
        - [x] Implemented base `EvidenceCollector` abstract class
        - [x] Implemented 7 default evidence collectors (mode-aware, leveraging existing code)
        - [x] Implemented `DeviceTypeClassifier` main class with mode-aware evidence collection
        - [x] Implemented database signature caching (`_check_database_signature()`)
        - [x] Implemented signature matching (`_signatures_match()`)
        - [x] Implemented strict dual-detection logic
        - [x] Code reuse integration (SDP, GATT, database functions)
        - [x] Updated `bleep/analysis/__init__.py` to export new classifier
        - [x] Unit tests for evidence collection, classification, and mode awareness
      - [x] Phase 2: Database integration (schema v6, evidence table, signature caching) - COMPLETED
        - [x] Updated schema version to v6
        - [x] Created `device_type_evidence` table with proper indexes
        - [x] Implemented migration from v5 to v6
        - [x] Added `store_device_type_evidence()` function
        - [x] Added `get_device_type_evidence()` function
        - [x] Added `get_device_evidence_signature()` function for caching
        - [x] Updated `DeviceTypeClassifier._check_database_signature()` to use evidence table
        - [x] Updated `DeviceTypeClassifier._store_evidence_signature()` to store all evidence
        - [x] Verified database migration and evidence storage/retrieval
      - [x] Phase 3: D-Bus layer integration (fix Type property access errors) - COMPLETED
        - [x] Fixed `device_classic.get_device_type()` - removed incorrect Type property access
        - [x] Updated `device_classic.get_device_type()` to use DeviceTypeClassifier
        - [x] Fixed `device_le.check_device_type()` - removed incorrect Type property access
        - [x] Updated `device_le.check_device_type()` to use DeviceTypeClassifier
        - [x] Fixed `adapter._determine_device_type()` - removed hardcoded UUID patterns
        - [x] Updated `adapter._determine_device_type()` to use DeviceTypeClassifier
        - [x] All methods now use evidence-based classification with proper context building
        - [x] Backward compatibility maintained (return types unchanged)
      - [x] Phase 4: Mode-aware evidence collection (scan mode integration) - COMPLETED
        - [x] Verified classifier mode-aware filtering (passive/naggy/pokey/bruteforce)
        - [x] Updated `passive_scan_and_connect()` to call device type classification with "passive" mode
        - [x] Updated `naggy_scan_and_connect()` to call device type classification with "naggy" mode
        - [x] Updated `pokey_scan_and_connect()` to call device type classification with "pokey" mode
        - [x] Updated `bruteforce_scan_and_connect()` to call device type classification with "bruteforce" mode
        - [x] Updated `connect_and_enumerate__bluetooth__classic()` to call device type classification with "pokey" mode
        - [x] All scan functions now pass appropriate scan_mode to classifier
        - [x] Evidence collectors already mode-aware (implemented in Phase 1)
      - [x] Phase 5: Documentation & testing - COMPLETED
        - [x] Created comprehensive documentation (`device_type_classification.md`)
        - [x] Updated `observation_db.md` with evidence-based classification details
        - [x] Updated `observation_db_schema.md` with device_type_evidence table documentation
        - [x] Created integration test suite (`test_device_type_integration.py`)
        - [x] Tests cover evidence collection, classification logic, mode filtering, database integration, edge cases
        - [x] All tests passing (20/21 tests, 1 test requires hardware-specific setup)
      - [x] Phase 6: Foreign Key Constraint Fix (2025-11-27) - COMPLETED
        - [x] Fixed FOREIGN KEY constraint violations during device scanning
        - [x] Restructured database operation sequence: insert device → classify → update type
        - [x] Modified `adapter.get_discovered_devices()` to defer classification
        - [x] Updated `scan._native_scan()` for proper sequencing
        - [x] Updated `scan._base_enum()` for consistency
        - [x] Fixed SyntaxWarning in `media.py` docstring
        - [x] Added defensive IntegrityError handling in `observations.py`
        - [x] Preserved backward compatibility (`_determine_device_type()` method retained)
        - [x] Created comprehensive documentation (`CHANGES_APPLIED.md`)
    - [x] Enhance 'dual' device detection to require conclusive evidence from both protocols (addressed in framework) - COMPLETED
    - [x] Only set device_type='dual' when both BLE and Classic aspects are confirmed (addressed in framework) - COMPLETED
    - [x] Document specific detection criteria for each device type category (addressed in framework) - COMPLETED
  * Database timestamps tracking:
    - [x] Fix `first_seen` field not being populated for new devices
    - [x] Ensure timestamp fields maintain correct data (first_seen stays constant, last_seen updates)
    - [x] Update default CLI display to show both timestamp fields
  * Enhance observation_db.md documentation:
    - [x] Document schema versioning information
    - [x] Add filtering examples for `db list` and `db timeline`
    - [x] Expand database schema with comprehensive table and column descriptions
    - [x] Add programmatic API usage examples
    - [x] Document observation module's public functions with examples
    - [x] Create advanced query cookbook for complex data extraction scenarios
  * GATT enumeration database improvements:
    - [x] Fix SQL syntax error in upsert_characteristics function
    - [x] Add robust error handling to prevent cascade failures
    - [x] Support multiple data structure formats (standard, gatt-enum, enum-scan)
    - [x] Improve gatt-enum command to correctly extract and save characteristics
    - [x] Add automatic reconnection and retry logic for database operations
    - [x] Determine why enum-scan, gatt-enum, and gatt-enum --deep scans produce different information verbosity within the database (Note: Behavior may be perfectly within expected operational parameters)
    - [x] Investigate why gatt-enum --deep scan produces LESS database information than gatt-enum scan despite printing more information to terminal; ensure all terminal output is properly captured in the database
- [x] Classic Bluetooth enumeration
- [x] Improve detection of controller stall (NoReply / timeout) and offer automatic `bluetoothctl disconnect` prompt
  - [x] Fixed property monitor callback error when disconnecting from a device while monitoring is active
- [x] bc-14 Discovery filter options (`--uuid / --rssi / --pathloss`) in classic-scan, wire through `SetDiscoveryFilter` (docs updated)
- [x] bc-15 Native SDP via D-Bus (`Device1.GetServiceRecords` fast-path) before sdptool fallback
- [x] **Enhanced SDP Attribute Extraction (Phase 1)** – Extract additional SDP attributes:
  - [x] Service Record Handle (0x0000)
  - [x] Bluetooth Profile Descriptor List (0x0009) with UUIDs and versions
  - [x] Service Version (0x0300)
  - [x] Service Description (0x0101)
  - [x] Added `--debug` flag to `classic-enum` command
  - [x] Graceful fallback when connection fails but SDP succeeds (connectionless queries)
- [x] **Connectionless SDP Query with l2ping (Phase 2)** – Reachability verification before SDP:
  - [x] Implemented `discover_services_sdp_connectionless()` function with l2ping check
  - [x] Updated `discover_services_sdp()` to support optional `connectionless` parameter
  - [x] Added `--connectionless` flag to `classic-enum` CLI command
  - [x] Faster failure detection and better error messages for unreachable devices
  - [x] Backward compatible (default behavior unchanged)
- [x] **Basic Bluetooth Version Detection (Phase 3)** – Extract and display version information:
  - [x] Added `get_vendor()`, `get_product()`, `get_version()`, `get_modalias()` methods to `device_classic.py`
  - [x] Created `get_device_version_info()` method that aggregates version information
  - [x] Created `bleep/ble_ops/classic_version.py` module with version detection helpers
  - [x] Implemented `query_hci_version()` for local adapter HCI/LMP version query (no sudo required)
  - [x] Implemented `map_lmp_version_to_spec()` for LMP to Bluetooth spec version mapping
  - [x] Implemented `map_profile_version_to_spec()` for profile version to spec version mapping (heuristic)
  - [x] Added `--version-info` flag to `classic-enum` CLI command
  - [x] Dual-source extraction (Device1 properties + modalias fallback)
  - [x] Raw property preservation for offline analysis
- [x] **Enhanced SDP Analysis (Phase 4)** – Comprehensive SDP record analysis and version inference:
  - [x] Created `bleep/analysis/sdp_analyzer.py` module with `SDPAnalyzer` class
  - [x] Protocol analysis (RFCOMM, L2CAP, BNEP, OBEX, etc.) extraction and identification
  - [x] Advanced version inference engine with cross-referencing of profile versions
  - [x] Anomaly detection for version inconsistencies and unusual patterns
  - [x] Service relationship analysis grouping related services by profile
  - [x] Comprehensive reporting with human-readable and JSON output formats
  - [x] Added `--analyze` flag to `classic-enum` CLI command
  - [x] Integration with existing debug and version-info modes
- [x] **Debug Mode PBAP Command (bc-10)** – Interactive PBAP phonebook dumps in debug mode:
  - [x] Implemented `_cmd_pbap()` function in `bleep/modes/debug.py`
  - [x] Added command registration to `_CMDS` dictionary
  - [x] Updated help text with PBAP command documentation
  - [x] PBAP service detection from service map and SDP records
  - [x] Support for all CLI `classic-pbap` features (repos, format, auto-auth, watchdog, output)
  - [x] Database integration for PBAP metadata (if enabled)
  - [x] Comprehensive error handling with diagnostic messages
  - [x] Entry counting and file statistics display
  - [x] Updated documentation in `bl_classic_mode.md`
  - [x] Updated changelog and todo tracker
- [x] **Debug Mode Connectionless SDP Discovery** – Added `csdp` command for connectionless SDP queries:
  - [x] Implemented `_cmd_csdp()` function in `bleep/modes/debug.py`
  - [x] Added command registration to `_CMDS` dictionary
  - [x] Updated help text with csdp command documentation
  - [x] Connectionless mode with l2ping reachability check (matches CLI `--connectionless` flag)
  - [x] Configurable l2ping parameters (`--l2ping-count`, `--l2ping-timeout`)
  - [x] Detailed SDP record display with enhanced attributes
  - [x] Automatic service map generation from discovered records
  - [x] Error handling for unreachable devices with clear messages
  - [x] Updated documentation in `bl_classic_mode.md`
  - [x] Updated changelog
- [x] **Classic Integration Tests (bc-12)** – Comprehensive test suite for Classic Bluetooth functionality:
  - [x] Phase 1: Enhanced SDP feature tests (enhanced attributes, connectionless queries, version detection, comprehensive analysis)
  - [x] Phase 2: PBAP comprehensive tests (multiple repositories, vCard formats, auto-auth, watchdog, output handling, database integration)
  - [x] Phase 3: CLI command tests (classic-enum, classic-pbap, classic-ping)
  - [x] Phase 4: Debug mode command tests (cscan, cconnect, cservices, csdp, pbap)
  - [x] Phase 5: Error recovery & edge cases (reconnection, concurrent operations, timeout handling, partial service discovery)
  - [x] Created `tests/test_classic_cli.py` for CLI command tests
  - [x] Created `tests/test_classic_debug_mode.py` for debug mode tests
  - [x] Updated `tests/test_classic_integration.py` with comprehensive test coverage
  - [x] Updated documentation
- [x] bc-16 Helper `classic_rfccomm_open(mac, channel)` for generic RFCOMM sockets (pre-req for MAP/OPP)
- [x] bc-17 Lightweight in-process OBEX agent for PBAP authentication (`--auto-auth` flag)
- [x] bc-18 PBAP watchdog to auto-disconnect on stalled transfer (>8 s without progress)
- [x] bc-19 `classic_l2ping(mac, count=3)` helper using *l2ping* CLI to verify reachability before connect
- [x] bc-13 Update CHANGELOG & todo-tracker after completing Classic Bluetooth feature set
- [x] bc-20 RFCOMM data-exchange debug commands (`copen`, `csend`, `crecv`, `craw`):
  - [x] Extracted shared value-parsing utility to `debug_utils.py` (reused by BLE `write` and `csend`)
  - [x] Added `rfcomm_sock` field to `DebugState` (separate from `keepalive_sock`)
  - [x] `copen` – open/close/status of dedicated data RFCOMM socket
  - [x] `csend` – send raw data with format support (hex:/str:/file:/uint8:/etc.)
  - [x] `crecv` – receive data with timeout, hex dump, save-to-file options
  - [x] `craw` – interactive bidirectional RFCOMM session with background reader thread
  - [x] Registered all commands in dispatch table and help text
- [x] bc-21 Object Push Profile (`copp`) via BlueZ obexd D-Bus:
  - [x] `dbuslayer/obex_opp.py` – D-Bus layer (`opp_send_file`, `opp_pull_business_card`)
  - [x] `ble_ops/classic_opp.py` – operations layer with logging and service detection
  - [x] `copp send <file>` and `copp pull [dest]` debug commands
- [x] bc-22 Message Access Profile (`cmap`) via BlueZ obexd D-Bus:
  - [x] `dbuslayer/obex_map.py` – D-Bus layer (`MapSession` class with full API)
  - [x] `ble_ops/classic_map.py` – operations layer with logging and service detection
  - [x] `cmap` debug command with sub-commands: folders, list, get, push, inbox, props, read, delete
- [x] bc-23 Refactored value-parsing from `debug_gatt.py` into shared `debug_utils.py`
- [x] bc-24 Documented future expansion items not covered by this change (FTP, SYNC, MNS, BIP, SPP, PAN, L2CAP raw, CLI sub-commands)
- [x] bc-25 Updated `bl_classic_mode.md` with new command documentation and feature tracker

### OBEX Expansion Roadmap (v2.7.5 – v2.7.13+)

Planned path forward for Classic OBEX profile and transport augmentations.
All versions remain within the v2.7.x range.  BlueZ D-Bus API references
are in `workDir/BlueZDocs/org.bluez.obex.*.rst` and reference scripts in
`workDir/BlueZScripts/`.

| Phase | Version | Scope | BlueZ Interface / Bus | Reference Script(s) | bc-IDs |
|-------|---------|-------|-----------------------|----------------------|--------|
| 1 | v2.7.5 | OBEX FTP + transfer-poller dedup | `FileTransfer1` (session) | `ftp-client`, `list-folders`, `service-ftp.xml` | bc-26 – bc-29 |
| 2 | v2.7.6 | CLI `classic-opp`, `classic-map`, `classic-ftp` | — (CLI wiring only) | — | bc-30 – bc-32 |
| 3 | v2.7.7 | MAP MNS notification monitoring | `MessageAccess1` signals (session) | `map-client` | bc-33 – bc-35 |
| 4 | v2.7.8 | MAP multi-instance MAS selection | `Client1` `Channel` byte (session) | `map-client` | bc-36 |
| 5 | v2.7.9 | PAN networking | `Network1` + `NetworkServer1` (system) | `test-network`, `test-nap` | bc-37 – bc-40 |
| 6 | v2.7.10 | SPP serial port emulation | `ProfileManager1` + `Profile1` (system) | `test-profile`, `service-spp.xml` | bc-41 – bc-43 |
| 7 | v2.7.11 | SYNC profile | `Synchronization1` (session) | — | bc-44 – bc-46 |
| 8 | v2.7.12 | BIP (Basic Imaging, experimental) | `Image1` [experimental] (session), target `"bip-avrcp"` | — | bc-47 – bc-49 |
| 9 | v2.7.13+ | Raw OBEX over RFCOMM, L2CAP raw | N/A (protocol-level) | — | TBD |

#### Phase 1 – OBEX FTP (v2.7.5)

- [x] bc-26 Extract shared OBEX transfer poller into `dbuslayer/_obex_common.py`; refactor `obex_opp.py`, `obex_map.py`, `obex_pbap.py` to use it
- [x] bc-27 FTP D-Bus layer: `dbuslayer/obex_ftp.py` (`FtpSession` context manager wrapping `FileTransfer1`)
  - Session target: `"ftp"` (per `org.bluez.obex.Client.rst`)
  - Methods: `ChangeFolder`, `CreateFolder`, `ListFolder`, `GetFile`, `PutFile`, `CopyFile`, `MoveFile`, `Delete`
  - Note: `GetFile(targetfile, sourcefile)` — first arg is local, second is remote
  - Note: `PutFile(sourcefile, targetfile)` — first arg is local, second is remote
- [x] bc-28 FTP operations layer: `ble_ops/classic_ftp.py` (logging, service detection UUID `0x1106`, obs-DB)
- [x] bc-29 FTP debug command `cftp` (ls/cd/get/put/mkdir/rm/cp/mv) + constants (`FTP_UUID`, `FTP_UUID_SHORT`, update `OBEX_PROFILE_UUIDS`) + dispatch wiring in `debug.py`

#### Phase 2 – CLI Sub-Commands (v2.7.6)

- [x] bc-30 CLI `classic-opp` command (send / pull) mirroring `classic-pbap` pattern
- [x] bc-31 CLI `classic-map` command (folders / list / get / push / inbox) with `--type` filter per `MessageAccess.rst`
- [x] bc-32 CLI `classic-ftp` command (ls / get / put / mkdir / rm)

#### Phase 3 – MAP MNS Notification Monitoring (v2.7.7)

- [x] bc-33 MAP signal-based notification watch via `PropertiesChanged` on `Message1` objects (not a custom D-Bus server — BlueZ does not expose `SetNotificationRegistration`)
- [x] bc-34 `MapSession.get_supported_types()` and `list_filter_fields()` wrappers (per `MessageAccess.rst` `SupportedTypes` property and `ListFilterFields()` method)
- [x] bc-35 Debug `cmap monitor start|stop` + `cmap types` + `cmap fields` sub-commands + CLI `classic-map types|fields|monitor`

#### Phase 4 – MAP Multi-Instance (v2.7.8)

- [x] bc-36 `MapSession` gains optional `instance` parameter → `CreateSession` `Channel` byte; `list_mas_instances()` from SDP; all ops functions accept `instance` kwarg; `cmap instances` debug sub-cmd; `classic-map --instance` CLI flag

#### Phase 5 – PAN Networking (v2.7.9)

- [x] bc-37 Constants: `NETWORK_INTERFACE`, `NETWORK_SERVER_INTERFACE`, PAN UUIDs (`0x1115`, `0x1116`, `0x1117`)
- [x] bc-38 D-Bus wrapper `dbuslayer/network.py` (`NetworkClient` + `NetworkServer` on **system bus**; `Connect(role)` returns interface name, `Disconnect()`, properties: `Connected`, `Interface`, `UUID`; server `Register`/`Unregister`)
- [x] bc-39 Operations layer `ble_ops/classic_pan.py` + debug command `cpan` (connect/disconnect/status/server register|unregister)
- [x] bc-40 CLI `classic-pan` command (connect/disconnect/status/serve/unserve)

#### Phase 6 – SPP Serial Port Emulation (v2.7.10)

- [x] bc-41 D-Bus layer `dbuslayer/spp_profile.py`: `SppProfile(dbus.service.Object)` implementing `Profile1` (`NewConnection` delivers fd); `SppManager` for register/unregister via `ProfileManager1` at `/org/bluez` on **system bus**
- [x] bc-42 Debug command `cspp` (register/unregister/status); fd exposed as `state.rfcomm_sock` for `csend`/`crecv`; CLI `classic-spp` (register/unregister/status)
- [x] bc-43 Constants: `PROFILE_MANAGER_INTERFACE`, `PROFILE_INTERFACE` (SPP UUID already exists); operations layer `ble_ops/classic_spp.py`

#### Phase 7 – SYNC Profile (v2.7.11)

- [x] bc-44 D-Bus layer `dbuslayer/obex_sync.py` (`SyncSession`, target `"sync"`; methods: `SetLocation`, `GetPhonebook`, `PutPhonebook` per `Synchronization.rst`)
- [x] bc-45 Debug command `csync` (get/put/location) + CLI `classic-sync` subparser
- [x] bc-46 Operations layer `ble_ops/classic_sync.py`

#### Phase 8 – BIP Basic Imaging (v2.7.12)

- [x] bc-47 D-Bus layer `dbuslayer/obex_bip.py` (`BipSession`, target `"bip-avrcp"` per `Client.rst`; `Image1` is **[experimental]**; methods: `Get`, `Properties`, `GetThumbnail` per `Image.rst`)
- [x] bc-48 Debug command `cbip` (get/props/thumb) + CLI `classic-bip` subparser with runtime guard for experimental interface
- [x] bc-49 Operations layer `ble_ops/classic_bip.py`

#### Phase 9 – Raw OBEX & L2CAP (v2.7.13+ — design only)

- [x] bc-50 Design doc for raw OBEX framing over RFCOMM (bypassing obexd) → `bleep/protocols/obex_design.md`
- [x] bc-51 Design doc for L2CAP raw channel access via `socket.AF_BLUETOOTH` / `BTPROTO_L2CAP` → `bleep/protocols/l2cap_design.md`

#### Cross-cutting

- [x] Split `debug_classic_data.py` (1,192 lines) into focused sub-modules (v2.7.14):
  - `debug_classic_rfcomm.py` (~378 lines) — copen, csend, crecv, craw + helpers
  - `debug_classic_obex.py` (~646 lines) — copp, cmap, cftp, csync, cbip
  - `debug_classic_profiles.py` (~200 lines) — cpan, cspp
  - `debug_classic_data.py` (49-line re-export shim) — backward-compatible imports
  - Fixed `cmd_csync`/`cmd_cbip` signature bug (reversed params, non-existent `state.bdaddr`)

- [x] bc-52 Enrich `current_mapping` from `Dict[str, int]` to `Dict[str, Dict]` with full SDP record fields (v2.7.15):
  - `classic_connect.py` — builds enriched `svc_map` with all SDP record fields
  - `debug_classic.py` — `_ch()` helper, rewritten `cmd_cservices` (normal + detailed), updated `cmd_ckeep`/`cmd_csdp`/`cmd_pbap`
  - `debug_classic_rfcomm.py` — `_resolve_rfcomm_channel` updated for enriched dicts
  - `debug_pairing.py` — `post_pair_connect_classic` builds enriched dicts
  - `debug_connect.py` — info message updated for non-RFCOMM inclusion
  - `cli.py` — `classic-enum` summary updated

- [x] bc-53 Fix SDP parsing gap: XML parser & collision-safe svc_map (v2.7.16):
  - `classic_sdp.py` — replaced `browse --tree` with `browse --xml` in fallback chain
  - `classic_sdp.py` — new `_parse_xml_record()` / `_parse_browse_xml()` for structured XML parsing
  - `classic_sdp.py` — new `build_svc_map()` public helper with duplicate-key disambiguation
  - `classic_sdp.py` — D-Bus path no longer requires RFCOMM channel to accept results
  - All inline `svc_map` builders (`classic_connect.py`, `debug_classic.py`, `debug_classic_rfcomm.py`, `debug_pairing.py`, `cli.py`) replaced with shared `build_svc_map()`

- [x] bc-54 MediaPlayer optional property handling (v2.7.17):
  - `dbuslayer/media.py` — `_get_property()` distinguishes optional vs required props per BlueZ spec
  - `dbuslayer/media.py` — `get_name()` delegates to `_get_property()` for consistent handling
  - `core/observations.py` — `snapshot_media_player()` uses `GetAll` instead of individual getters

*(collapse / expand sections as items are completed)* 

## User Mode Implementation Tasks

- [x] **Core UI Implementation**
  - [x] Design simplified menu structure vs. debug mode
  - [x] Implement basic device discovery and selection flow
  - [x] Create characteristic interaction screens (read/write/notify)
  - [x] Build signal configuration UI components
  - [x] Implement error handling with user-friendly messages
- [x] **Backend Functionality**
  - [x] Create abstraction layer above debug mode operations
  - [x] Implement simplified device map visualization
  - [x] Build notification/signal capture configuration system
  - [x] Add export/import of device interactions
- [x] **Documentation**
  - [x] Create `docs/user_mode.md` guide with screenshots
  - [x] Add quick-start examples for common workflows
  - [x] Document UI navigation patterns
- [x] **Testing**
  - [x] Create test suite for UI functionality
  - [x] Validate against multiple device types

## Codebase Gap Analysis & Remediation Plan (2026-04-01) – IN PROGRESS

**Origin**: Exhaustive review of the entire `bleep/` codebase (163 Python modules, 58 documentation files), cross-referenced against `bleep/docs/changelog.md`, this tracker, and `workDir/BigMoves/README.bleep-bleep-mcp-augmentation-roadmap.md`. This section captures all discovered gaps, shortcomings, incomplete work, and documentation errors with a phased remediation plan.

**Methodology**: Static analysis of all `bleep/**/*.py` modules, grep for TODO/FIXME/HACK/PLACEHOLDER markers, comparison of `__all__` exports against actual imports, test coverage mapping (163 modules vs `tests/` import references), deprecated API usage audit, and documentation-to-code consistency checks.

---

### Category 1: Active Bugs and Broken References

#### G-1.1 `modes/test.py` calls non-existent adapter API

**Finding**: `bleep/modes/test.py` lines 478, 499, 509 call `self.adapter.is_powered()` and `self.adapter.is_discovering()`. The adapter class (`dbuslayer/adapter.py`) only exposes `get_powered()` and `get_discovering()` — the `is_*` names were removed during the v2.7+ API cleanup.

**Impact**: `bleep test` crashes with `AttributeError` whenever it reaches the adapter property check or discovery test.

**Reasoning**: This is a straightforward rename oversight. The rest of the codebase was migrated, but `modes/test.py` was missed. Grep confirms these are the **only** three occurrences of the old names across the entire `bleep/` tree.

**Fix**: Replace `is_powered()` → `get_powered()` and `is_discovering()` → `get_discovering()` in `modes/test.py`.

- [x] **G-1.1** Fix stale `is_powered()`/`is_discovering()` calls in `modes/test.py`

#### G-1.2 `identify_uuid()` space-padding in `uuid_utils.py`

**Finding**: `bleep/ble_ops/common/uuid_utils.py` line 84 adds `target.ljust(32, " ")` to `canonical_targets`, injecting space-padded strings into a set meant for hex comparison.

**Impact**: This padded form will never match any real UUID (hex strings don't contain spaces). It wastes a set entry on every call and could cause confusion if anyone iterates `canonical_targets` for display or logging. The actual matching still works because other branches add the correct hex forms.

**Reasoning**: Likely a debugging artifact or misguided attempt to normalize length. The set already receives correct-length hex forms from the 16-bit, 32-bit, and 128-bit branches. The space-padded entry serves no purpose.

**Fix**: Remove the `canonical_targets.add(target.ljust(32, " "))` line.

- [x] **G-1.2** Remove space-padding in `identify_uuid()` (`ble_ops/common/uuid_utils.py`)

#### G-1.3 `dbuslayer/__init__.py` `__all__` lists unexported names

**Finding**: `bleep/dbuslayer/__init__.py` `__all__` lists `bluez_monitor`, `recovery`, `agent_io`, `pairing_state`, `bond_storage` but the file only imports `system_dbus__bluez_adapter`, `system_dbus__bluez_signals`, `system_dbus__bluez_generic_agent`, `system_dbus__bluez_agent_user_interface`, `Characteristic`, `Descriptor`. The five listed-but-not-imported names have no `__getattr__` lazy loader — only `system_dbus__bluez_device__low_energy` does.

**Impact**: `from bleep.dbuslayer import *` silently fails to export those five modules. Direct `from bleep.dbuslayer import bluez_monitor` raises `ImportError`. Code that uses the fully-qualified path (`from bleep.dbuslayer.bluez_monitor import ...`) works fine.

**Reasoning**: `__all__` was expanded to document intended scope without wiring up the imports. This is misleading to anyone inspecting the package API.

**Fix**: Either add `__getattr__` lazy loaders for the five modules (matching the `device_le` pattern) or remove them from `__all__`.

- [x] **G-1.3** Fix `dbuslayer/__init__.py` `__all__` vs actual imports

#### G-1.4 `__main__.py` missing for `python -m bleep`

**Finding**: `bleep/docs/cli_usage.md` line 25 explicitly notes: "The documentation previously showed `python -m bleep`, but this won't work because the package doesn't have a `__main__.py` file." The standard Python convention (`python -m <package>`) does not work.

**Impact**: User friction. `python -m bleep.cli` works, but `python -m bleep` is the expected pattern (matching `python -m pytest`, `python -m pip`, etc.).

**Reasoning**: A `__main__.py` containing `from bleep.cli import main; import sys; sys.exit(main())` would make `python -m bleep` behave identically to `python -m bleep.cli`. When no subcommand is given, `args.mode` is `None`, which falls through to the `else` branch at `cli.py:2572` and launches the interactive REPL — same as today. All flags and subcommands work identically since both paths invoke the same `main()`. The `bleep/__init__.py` side-effects (signal patching, log init) are triggered either way because importing the package always runs `__init__.py`.

**Fix**: Create `bleep/__main__.py` (3 lines). Update `cli_usage.md` to remove the caveat note.

- [x] **G-1.4** Add `bleep/__main__.py` for `python -m bleep` support
- [x] **G-1.4b** Update `cli_usage.md` to remove the "won't work" caveat

#### G-1.5 Orphaned bytecode without source

**Finding**: `bleep/callbacks/examples/__pycache__/auto_pair_accept.cpython-311.pyc` exists with no corresponding `auto_pair_accept.py` source file.

**Impact**: None at runtime (Python won't load `.pyc` without being asked), but it pollutes the tree and suggests a deleted file that was never cleaned up.

**Fix**: Delete the orphaned `.pyc` file.

- [x] **G-1.5** Delete orphaned `auto_pair_accept.cpython-311.pyc`

---

### Category 2: Incomplete Features (Explicitly Marked Elsewhere, Consolidated Here)

#### G-2.1 Endpoint-based transport acquisition — INCOMPLETE

**Cross-ref**: "Fix Endpoint-Based Transport Acquisition (2026-03-21) – INCOMPLETE" section in this tracker (line ~827).

**Finding**: `BleepMediaEndpoint` registration (Phase 2) does not function when PipeWire/PulseAudio is running. BlueZ never calls `SelectConfiguration`/`SetConfiguration` because the audio daemon claims all SEPs first. The `--direct` mode works only when the audio daemon is stopped.

**Impact**: `audio-play` without `--direct` or `--system` is non-functional in common desktop configurations.

**Reasoning**: This is an architectural contention issue between BLEEP and the system audio daemon. Deferred in favor of `--system` flag approach that works *with* the daemon. Further investigation into BlueZ endpoint selection ordering and PipeWire endpoint contention is needed. May require BLEEP to be the only registered endpoint.

**Status**: Deferred — documented here for tracking.

#### G-2.2 `audio_codec.py` GStreamer appsrc recording placeholder

**Finding**: `bleep/ble_ops/audio/audio_codec.py` lines 445-451 contain a placeholder comment block for the recording path that reads from a transport FD and feeds data to GStreamer's `appsrc`. No actual implementation exists.

**Impact**: Recording via the codec pipeline (non-system-tool path) is non-functional.

**Reasoning**: This requires GStreamer `appsrc` integration with `push_buffer()` and proper EOS handling. The `--system` recording path via `arecord`/`parecord` works as an alternative.

#### G-2.3 `service.py` signal handling ✅ Complete

**Finding**: `bleep/dbuslayer/service.py` previously had log-only signal placeholders.

- [x] `Service._props_changed` now updates local state (`primary`, `includes`, `handle`) on `GattService1` `PropertiesChanged`
- [x] `Service.on_property_changed()` callback registration for callers
- [x] `signals.py` routes `GATT_SERVICE_INTERFACE` property changes to the owning Service object
- [x] Module docstring updated (no longer "placeholder")
- [x] 6 mock-based tests for signal dispatch path

#### G-2.4 `device_le.py` legacy compatibility stubs

**Finding**: Lines 1668-1691 in `bleep/dbuslayer/device_le.py` contain Phase-4 legacy stubs including an empty `register()` method and connection signalling no-ops. The `interfaces_added` callback (line 2077) only logs, doesn't update caches.

**Impact**: External callers expecting monolith-era device registration or real-time interface tracking get silent no-ops.

---

### Category 3: Empty/Placeholder Packages

#### G-3.1 `bleep/gatt/` — Future migration namespace

**Finding**: Contains only `__init__.py` with guarded imports of `service`, `characteristic`, `descriptor` that all resolve to `None` because no `.py` modules exist in this directory. The real implementations remain in `bleep/dbuslayer/`.

**Reasoning**: Declared as a future migration target. No runtime impact, but the package's existence may mislead developers into thinking GATT wrappers live here.

**Decision needed**: Migrate the implementations here, or remove the package and document `bleep.dbuslayer` as the canonical home.

- [x] **G-3.1** ~~Decide on `bleep/gatt/`~~ — **Decision: keep as future migration target.** When GATT wrappers are mature enough to decouple from `dbuslayer/`, move `service.py`, `characteristic.py`, `descriptor.py` here. No action needed now.

#### G-3.2 `bleep/mesh/` — Partially implemented

**Finding**: `agent` and `provisioning` modules listed in `__all__` don't exist (import-guarded to `None`). Only `proxy_solicitation` is a real module.

**Reasoning**: Mesh support is early-stage. The package should exist but `__all__` should only list what's real.

- [x] **G-3.2** Restructured `bleep/mesh/__init__.py` — `__all__` now lists only `proxy` (the real module); planned `agent`/`provisioning` documented in docstring only

#### G-3.3 `bleep/protocols/` — Design docs only

**Finding**: Package docstring states "Contains design documentation only. Implementation is planned for a future version." Only `l2cap_design.md` and `obex_design.md` exist — no Python code.

**Reasoning**: Acceptable for design-phase packages, but should be noted in `docs/README.md` to avoid confusion.

- [x] **G-3.3** Note `protocols/` as design-only in docs index

---

### Category 4: Deprecated/Legacy Code

#### G-4.1 `bluetooth_uuids.py` still imported by bleep-mcp (BC-003)

**Finding**: Module emits `DeprecationWarning` on import, directing to `bleep.bt_ref.uuids`. No internal `bleep/` code imports it, but `bleep-mcp/bleep_mcp/resources/reference_data.py` has 3 import sites that still use it.

**Reasoning**: Coordination item between `bleep/` and `bleep-mcp/`. Once `bleep.bt_ref.uuids` has full export parity, the MCP imports should migrate.

**Cross-ref**: BC-003 in `workDir/BigMoves/README.bleep-bleep-mcp-augmentation-roadmap.md`.

- [x] **G-4.1** Verify `bleep.bt_ref.uuids` export parity then migrate bleep-mcp imports (BC-003) — imports migrated, `bluetooth_uuids.py` deleted

#### G-4.2 `compat.py` — deprecated, zero internal callers

**Finding**: Entire module warns on import. No `bleep/` code imports it. Exists only for hypothetical external scripts.

- [x] **G-4.2** `compat.py` removed in v2.8.1 (was marked for deletion since v2.6)

#### G-4.3 Legacy shim modules (`bluetooth_utils.py`, `bluetooth_constants.py`, `bluetooth_exceptions.py`)

**Finding**: Three one-line `from .X import *` files in `bt_ref/`. No internal importers.

- [x] **G-4.3** `bluetooth_utils.py`, `bluetooth_constants.py`, `bluetooth_exceptions.py` shims removed in v2.8.1

#### G-4.4 Duplicate D-Bus error mapping (B5 consolidation)

**Finding**: `core/error_handling.py` lines 55-61 document three overlapping error mapping systems: `decode_dbus_error()`, `evaluate__dbus_error()`, and `BlueZErrorHandler.ERROR_MESSAGES`. Plus `bt_ref/error_map.py` has its own table marked "DEPRECATED as primary source of truth."

**Impact**: Tables may diverge, producing inconsistent error codes/messages depending on which path handles the error.

**Reasoning**: The B5 consolidation TODO is open and well-documented in-code. The work is to refactor callers of the deprecated paths to use `decode_dbus_error()` as the single source of truth, then remove the duplicates.

- [x] **G-4.4** Complete B5 D-Bus error mapping consolidation — `evaluate__dbus_error` now delegates to `decode_dbus_error()`, `bt_ref/error_map.map_dbus_error` renamed to `classify_dbus_error` (alias kept), `DBUS_ERROR_MAP` aligned with canonical decoder, cross-system consistency tests added

---

### Category 5: Test Coverage Gaps

#### G-5.1 Majority of modules lack direct test coverage

**Finding**: Of 163 Python modules, only ~30 are directly referenced by any test file in `tests/`. The gap includes entire subsystems:

| Subsystem | Key untested modules |
|-----------|---------------------|
| `ble_ops/audio/` | All 10 modules (amusica, audio_recon, audio_codec, audio_system, etc.) |
| `ble_ops/classic/` | map, pbap, sdp, opp, ftp, pan, spp, rfcomm, ping, version (only `connect` is referenced) |
| `ble_ops/common/` | `uuid_utils`, `modalias`, `structural` |
| `dbuslayer/` | device_le, device_classic, device, manager, service, media_stream, media_browse, all obex_*, bond_storage, pin_brute, etc. |
| `core/` | config, preflight, metrics, utils |
| `callbacks/` | All |
| `signals/` | capture_config, router, integration, cli |
| `modes/` | All 30+ mode files except aoi, debug, media (partial) |

**Reasoning**: Many of these modules require D-Bus/BlueZ at runtime, which makes pure unit testing hard. However, mock-based unit tests for the non-D-Bus logic (parsing, formatting, data structures, error handling) are feasible and valuable.

**Note**: Some modules get indirect coverage through CLI integration tests (`test_classic_cli.py` runs `bleep` as a subprocess), but this is brittle and doesn't validate internal logic paths.

- [x] **G-5.1a** Created `tests/conftest.py` with `MockAdapter`, `MockDeviceInfo`, `dbus_stub`, and `glib_stub` fixtures
- [x] **G-5.1b** 23 tests for `uuid_utils.py` — `identify_uuid` (16/32/128-bit, BT SIG vs custom, edge cases) and `match_uuid` (exact, partial, case-insensitive, empty)
- [x] **G-5.1c** 18 tests for `core/preflight.py` — `DeviceState`, `PreflightReport`, `check_device_state`, `require_adapter`, `_check_bluetooth_tools`, `_check_bluez_version`, `_check_bluetooth_config`, `run_preflight_checks` caching
- [x] **G-5.1d** 14 tests for `ble_ops/classic/map.py` — `normalize_bmessage` (LF→CRLF, LENGTH recalc, multi-block, edge cases) and `_normalize_for_push` (temp-file round-trip)
- [x] **G-5.1e** 12 tests for `callbacks/base.py` — ABC enforcement, `execute` dispatch, `on_load`/`on_unload` lifecycle, class attribute defaults
- [x] **G-5.1f** 18 tests for `analysis/sdp_analyzer.py` — empty records, protocol detection (RFCOMM/L2CAP/OBEX/BNEP), profile analysis, version inference with confidence, anomaly detection, report generation
- [x] **G-5.1g** 14 mock-based tests for `dbuslayer/service.py` + `device_classic.py` — `Service.__init__`/`get_handle`/`discover_characteristics`, `device_classic` state queries/pair/connect with D-Bus mocks

---

### Category 6: Documentation Gaps and Errors

#### G-6.1 `cli_usage.md` — `python -m bleep` caveat

**Cross-ref**: G-1.4 above. Once `__main__.py` is added, update the docs.

#### G-6.2 `bl_classic_mode.md` bc-01 tracker stale

**Finding**: Section 6 "Temporary Classic-Feature TODO Tracker" shows bc-01 as "pending" while most other items are completed. Appears to be outdated.

- [x] **G-6.2** Marked bc-01 as ✅ completed in `bl_classic_mode.md` (research fully realized in implementation)

#### G-6.3 `network_capability_plan.md` / `network_capability_summary.md` drift

**Finding**: These design docs describe Phases 2-5 as "Planned" but `bl_classic_mode.md` already documents working `classic-pan`. The plan docs may be partially superseded.

- [x] **G-6.3** Updated `network_capability_plan.md` and `network_capability_summary.md` — Phase 1 + 1b (classic-pan) complete; Phases 2-5 marked as future enhancements; manual verification with real PAN device recommended

#### G-6.4 `mainloop_architecture.md` — "Design document, not yet implemented"

**Finding**: Line 4 states "Status: Design document — not yet implemented." This is accurate but the doc doesn't cross-reference the FW items (FW1/F1/F3) that track the actual work.

- [x] **G-6.4** Added "Related Work Items" table to `mainloop_architecture.md` cross-referencing FW1, F1, F3 from todo_tracker

#### G-6.5 `observation_db_schema.md` — `protocol_descriptors` "Reserved for future use"

**Finding**: Column exists in schema v10, documented as reserved. `observations.py` has the column in CREATE TABLE and migration SQL, but sets it to `None` in most code paths. Some population logic exists at lines 1035-1068 but appears to be partial.

- [x] **G-6.5** Populated `protocol_descriptors` from SDP attribute 0x0004 — all three parsers (D-Bus XML, sdptool XML, sdptool text) now extract full ProtocolDescriptorList

---

### Category 7: Roadmap Items (from augmentation-roadmap.md, not tracked elsewhere)

These items from `workDir/BigMoves/README.bleep-bleep-mcp-augmentation-roadmap.md` are **not yet tracked** in this file. Added here for completeness:

- [x] **G-7.1** (S4) `_classify_le()` and `_classify_dual()` now consume `LE_ADVERTISING_DATA` evidence at STRONG weight — scan-only devices with beacon/CDP/service-data heuristics classify as `le` instead of `unknown`
- [x] **G-7.2** (S5) Vendor UART UUIDs (`FFE0`, `FFE1`, `FFF0`, `FFF1`, Nordic UART) elevated from WEAK to STRONG evidence; reasoning output updated
- [x] **G-7.3** (S9) `upsert_device()` now tracks `rssi_min`/`rssi_max` via `MIN()`/`MAX()` SQL; scan path seeds both values; manufacturer data selects longest payload instead of first entry
- [ ] **G-7.4** (B1-B4) Blind spots: advertised UUIDs treated as ground truth for Classic/LE split; cached classification not flagged; Find My / `fcf1` beacons ignored for `type`
- [ ] **G-7.5** (3.1) Advertisement dissection — parse `ServiceData` and `ManufacturerData` into structured fields
- [x] **G-7.6** (BC-001) Extracted shared `BT_SIG_BASE_UUID` / `BT_SIG_BASE_UUID_NODASH` into `bt_ref/constants.py`; `uuid_utils.py` and `uuid_translator.py` now import from the canonical source (also fixed pre-existing truncation bug in `BASE_UUID__BLUETOOTH`)

**Note**: BC-001 numeric values are currently correct and aligned between the two files. The risk is duplication drift, not a current bug.

---

### Remediation Phases

#### Phase 1: Critical Fixes (Immediate — ~30 minutes)

Quick wins that fix actual runtime bugs and standard Python packaging.

| # | Item | Effort | Files |
|---|------|--------|-------|
| 1 | G-1.1: Fix `is_powered()`/`is_discovering()` in `modes/test.py` | 10 min | `modes/test.py` |
| 2 | G-1.2: Remove `ljust` space-padding in `uuid_utils.py` | 5 min | `ble_ops/common/uuid_utils.py` |
| 3 | G-1.3: Fix `dbuslayer/__init__.py` `__all__` vs imports | 15 min | `dbuslayer/__init__.py` |
| 4 | G-1.4: Add `bleep/__main__.py` + update `cli_usage.md` | 5 min | New: `__main__.py`, `docs/cli_usage.md` |
| 5 | G-1.5: Delete orphaned `.pyc` | 1 min | `callbacks/examples/__pycache__/` |

#### Phase 2: Consolidation and Cleanup ✅ Complete (2026-04-01)

Tech debt that compounds if left unaddressed.

| # | Item | Effort | Status |
|---|------|--------|--------|
| 6 | G-4.4: B5 D-Bus error mapping consolidation | 2-3 hr | Deferred to Phase 4 — multiple overlapping tables with subtle semantic differences require dedicated analysis |
| 7 | G-7.6: Extract shared BT SIG base UUID constant | 30 min | ✅ Done |
| 8 | G-6.2, G-6.3, G-6.4: Update stale doc status markers | 1 hr | ✅ Done |
| 9 | G-5.1a: Create `tests/conftest.py` with shared fixtures | 2 hr | Deferred to Phase 3 (test expansion) |
| 10 | G-4.2, G-4.3: Deprecated shims deleted in v2.8.1 | 1 hr | ✅ Done |
| 11 | G-3.2: Structure `mesh/` for proper future development | 10 min | ✅ Done |

#### Phase 3: Test Coverage Expansion ✅ Complete (2026-04-01)

Prioritized by likelihood of catching real bugs.  112 tests total, all passing (<1s).

| # | Item | Priority | Status |
|---|------|----------|--------|
| Prereq | G-5.1a: `tests/conftest.py` with shared fixtures | — | ✅ Done |
| 12 | G-5.1b: Unit tests for `uuid_utils.py` (23 tests) | High | ✅ Done |
| 13 | G-5.1c: Unit tests for `core/preflight.py` (18 tests) | High | ✅ Done |
| 14 | G-5.1f: Unit tests for `analysis/sdp_analyzer.py` (18 tests) | Medium | ✅ Done |
| 15 | G-5.1d: Unit tests for `ble_ops/classic/map.py` (14 tests) | Medium | ✅ Done |
| 16 | G-5.1e: Unit tests for `callbacks/base.py` (12 tests) | Medium | ✅ Done |
| 17 | G-5.1g: Mock tests for `dbuslayer/service.py`, `device_classic.py` (14 tests) | Medium | ✅ Done |

#### Phase 4: Feature Completion & Error Consolidation ✅ Complete (2026-04-01)

Four bounded items addressing error-handling fragility, live GATT observation, device classification, and data quality.  279 tests total, all passing.

| # | Item | Complexity | Status |
|---|------|-----------|--------|
| 6 | G-4.4: B5 D-Bus error mapping consolidation (deferred from Phase 2) | 2-3 hr | ✅ Done |
| 20 | G-2.3: `service.py` signal handling — propagate GATT property changes | Medium | ✅ Done |
| 21 | G-7.1, G-7.2: Device type classifier enrichment (`ServiceData`/`AdvertisingData` + vendor UUID heuristics) | Medium | ✅ Done |
| 22 | G-7.3: DB row enrichment from scan data (RSSI min/max tracking, best-manufacturer selection) | Small | ✅ Done |

**Deferred to future sprint / v2.9 milestone:**

| # | Item | Reason |
|---|------|--------|
| 18 | G-2.1: Endpoint transport acquisition (PipeWire contention) | Large scope; `--system` audio workaround covers all current use cases |
| 19 | G-2.2: `audio_codec.py` appsrc recording | Depends on G-2.1 transport acquisition |
| 23 | G-7.5: Advertisement dissection tool | Large standalone feature, high maintenance burden |
| 28 | G-3.1-M: Migrate GATT wrappers (`service.py`, `characteristic.py`, `descriptor.py`) from `dbuslayer/` into `bleep/gatt/` | Blocked until GATT wrappers are mature enough to decouple from D-Bus layer; see G-3.1 decision |

#### Phase 5: Package Hygiene and Documentation ✅ Complete (2026-04-01)

All four items resolved: deprecated UUID file deleted, protocol descriptors populated from SDP, docs updated.

| # | Item | Status |
|---|------|--------|
| 24 | G-3.1: `bleep/gatt/` — decision: keep as future migration target (no action now) | ✅ Done |
| 25 | G-3.3: Note `protocols/` as design-only in docs README | ✅ Done |
| 26 | G-4.1: `bluetooth_uuids.py` deprecated — bleep-mcp imports migrated to `bt_ref.uuids`, file deleted | ✅ Done |
| 27 | G-6.5: `protocol_descriptors` column now populated from SDP ProtocolDescriptorList (all 3 parsers) | ✅ Done |
| 29 | v2.8.1 deprecated module removal: `compat.py`, `bluetooth_exceptions.py`, `bluetooth_constants.py`, `bluetooth_utils.py` deleted; `bt_ref/__init__.py` legacy block removed; docstring references updated | ✅ Done |
| 30 | Documentation drift: `map.py` docstring, `mainloop_architecture.md` status, `media_mode.md` flags/examples, `aoi.py` TODO stub | ✅ Done |
| 31 | Media enumeration expansion: non-verbose player output, AVRCP labels, `--verbose` object tree, `--browse` flag, `media_mode.md` sync | ✅ Done |
| 32 | Bluetooth Mesh skeleton: full `bleep/mesh/` package (constants, errors, network, node, management, application, element, provisioner, provision_agent); `proxy_solicitation.py` API corrected | ✅ Done |

---

## V2.8.1 BlueZ D-Bus Interface Gap Analysis (2026-04-02) – IN PROGRESS

**Origin**: Systematic comparison of every `org.bluez.*` D-Bus interface documented in `workDir/BlueZDocs/*.rst`, `workDir/bluez/doc/*.txt`, and `workDir/bluez-tools/contrib/bluez-api-5.20-fixed/*.txt` against the BLEEP v2.8.1 codebase (`bleep/**/*.py`). Goal: ensure BLEEP achieves **complete** enumeration, capture, and interaction coverage of all BlueZ-exposed Bluetooth capabilities.

**Methodology**: For each BlueZ D-Bus interface, every property, method, and signal was checked for presence in BLEEP code (not just constants, but actual read/write/call usage). Items marked PARTIAL have interface name constants defined in `bt_ref/constants.py` but no functional implementation.

**Reference documents** (for manual verification):
- Adapter: `workDir/BlueZDocs/org.bluez.Adapter.rst`
- Device: `workDir/BlueZDocs/org.bluez.Device.rst`
- GATT: `workDir/BlueZDocs/org.bluez.GattCharacteristic.rst`, `org.bluez.GattManager.rst`, `org.bluez.GattProfile.rst`
- Agent: `workDir/BlueZDocs/org.bluez.Agent.rst`, `org.bluez.AgentManager.rst`
- LE Advertising: `workDir/BlueZDocs/org.bluez.LEAdvertisement.rst`, `org.bluez.LEAdvertisingManager.rst`
- Battery: `workDir/BlueZDocs/org.bluez.Battery.rst`, `org.bluez.BatteryProvider.rst`, `org.bluez.BatteryProviderManager.rst`
- Media: `workDir/BlueZDocs/org.bluez.Media.rst`, `org.bluez.MediaPlayer.rst`, `org.bluez.MediaTransport.rst`, `org.bluez.MediaEndpoint.rst`, `org.bluez.MediaFolder.rst`, `org.bluez.MediaItem.rst`, `org.bluez.MediaAssistant.rst`
- Network: `workDir/BlueZDocs/org.bluez.Network.rst`, `org.bluez.NetworkServer.rst`
- Profile: `workDir/BlueZDocs/org.bluez.Profile.rst`, `org.bluez.ProfileManager.rst`
- Input: `workDir/BlueZDocs/org.bluez.Input.rst`
- Adv Monitor: `workDir/BlueZDocs/org.bluez.AdvertisementMonitor.rst`, `org.bluez.AdvertisementMonitorManager.rst`
- Admin Policy: `workDir/BlueZDocs/org.bluez.AdminPolicySet.rst`, `org.bluez.AdminPolicyStatus.rst`
- Device Sets: `workDir/BlueZDocs/org.bluez.DeviceSet.rst`
- Bearer Split: `workDir/BlueZDocs/org.bluez.Bearer.LE.rst`, `org.bluez.Bearer.BREDR.rst`
- Health: `workDir/bluez/doc/health-api.txt`
- SAP: `workDir/bluez/doc/sap-api.txt`
- Thermometer: `workDir/bluez/doc/thermometer-api.txt`
- Mesh: `workDir/bluez/doc/mesh-api.txt`

---

### Gap Summary Table

| # | Gap ID | Interface / Area | Gap Description | Severity | BLEEP Status |
|---|--------|-----------------|-----------------|----------|-------------|
| 1 | BZ-1 | `GattCharacteristic1` | `AcquireWrite()` / `AcquireNotify()` not implemented | High | Missing |
| 2 | BZ-2 | `GattCharacteristic1` | `WriteAcquired` / `NotifyAcquired` properties — constants only, not read from D-Bus | Medium | Partial |
| 3 | BZ-3 | `GattCharacteristic1` | `Confirm()` method (server-side indication ack) not implemented | Low | Missing |
| 4 | BZ-4 | `GattManager1` | `RegisterApplication()` / `UnregisterApplication()` — GATT server not implemented | High | Partial (constant only) |
| 5 | BZ-5 | `GattProfile1` | Interface not implemented (GATT profile registration) | Low | Missing |
| 6 | BZ-6 | `LEAdvertisingManager1` | `RegisterAdvertisement()` / `UnregisterAdvertisement()` + capability queries | High | **DONE** (Sprint 2) |
| 7 | BZ-7 | `LEAdvertisement1` | Advertisement object (Type, ServiceUUIDs, ManufacturerData, etc.) + CLI | High | **DONE** (Sprint 2) |
| 8 | BZ-8 | `Device1` | `Disconnected` signal (reason + message payload) not subscribed to | Medium | Missing |
| 9 | BZ-9 | `BatteryProvider1` | Battery provider registration not implemented | Low | Missing |
| 10 | BZ-10 | `BatteryProviderManager1` | `RegisterBatteryProvider()` / `UnregisterBatteryProvider()` not implemented | Low | Missing |
| 11 | BZ-11 | `AdvertisementMonitor1` | Advertisement monitoring (pattern-based passive scanning) not implemented | High | Missing |
| 12 | BZ-12 | `AdvertisementMonitorManager1` | `RegisterMonitor()` / `UnregisterMonitor()` not implemented | High | Missing |
| 13 | BZ-13 | `AdminPolicySet1` | `SetServiceAllowList()` not implemented | Low | Missing |
| 14 | BZ-14 | `AdminPolicyStatus1` | `ServiceAllowList` / `IsAffectedByPolicy` properties not read | Low | Missing |
| 15 | BZ-15 | `DeviceSet1` | Interface methods (`Connect()`, `Disconnect()`) and properties not implemented | Medium | Missing (Device1 `Sets` property IS read) |
| 16 | BZ-16 | `Bearer.LE1` / `Bearer.BREDR1` | Bearer-split interfaces not implemented | Low | Missing (experimental) |
| 17 | BZ-17 | `HealthManager1` / `HealthDevice1` / `HealthChannel1` | Bluetooth Health Profile (HDP) not implemented | Low | Missing |
| 18 | BZ-18 | `SimAccess1` | SIM Access Profile not implemented | Low | Missing |
| 19 | BZ-19 | `MediaAssistant1` | Broadcast Audio Assistant not implemented | Low | Missing (experimental) |
| 20 | BZ-20 | `Thermometer1` / `ThermometerManager1` | Thermometer profile D-Bus API not implemented | Low | Missing (deprecated) |
| 21 | BZ-21 | `HeartRate1` / `HeartRateManager1` | Heart Rate profile D-Bus API not implemented | Low | Missing (deprecated) |
| 22 | BZ-22 | `CyclingSpeed1` / `CyclingSpeedManager1` | Cycling Speed profile D-Bus API not implemented | Low | Missing (deprecated) |
| 23 | BZ-23 | `ProximityMonitor1` / `ProximityReporter1` | Proximity profile D-Bus API not implemented | Low | Missing (deprecated) |
| 24 | BZ-24 | Mesh `ProvisionAgent1` | All OOB hooks raise `NotImplementedError` | Medium | Partial (skeleton only) |
| 25 | BZ-25 | Mesh `Provisioner1` | `RequestReprovData`, `ReprovComplete`, `ReprovFailed` not implemented | Low | Partial |

---

### Detailed Gap Descriptions

#### BZ-1: GATT AcquireWrite / AcquireNotify (HIGH)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.GattCharacteristic.rst`):
- `AcquireWrite(dict options)` → `(fd, uint16 mtu)` — Returns a file descriptor for streaming writes, bypassing per-packet D-Bus overhead
- `AcquireNotify(dict options)` → `(fd, uint16 mtu)` — Returns a file descriptor for streaming notification reception

**BLEEP status**: `dbuslayer/characteristic.py` lines 3-6 explicitly note these are "for later." No implementation exists. BLEEP uses `ReadValue`/`WriteValue` and `StartNotify`/`StopNotify` exclusively.

**Impact**: High-throughput BLE data streams (sensor feeds, firmware updates, audio-over-GATT) suffer D-Bus round-trip latency on every packet. The fd-based path eliminates this overhead entirely.

**Implementation plan**:
- [x] **BZ-1a** Add `acquire_write(dict options) → (fd, mtu)` to `dbuslayer/characteristic.py`
    - Calls `GattCharacteristic1.AcquireWrite({})` on the D-Bus interface
    - Returns the Unix FD and negotiated MTU
    - Tracks `WriteAcquired` property to prevent double-acquire
    - Handles `NotPermitted` / `NotSupported` gracefully (fall back to `WriteValue`)
- [x] **BZ-1b** Add `acquire_notify(dict options) → (fd, mtu)` to `dbuslayer/characteristic.py`
    - Calls `GattCharacteristic1.AcquireNotify({})` on the D-Bus interface
    - Returns the Unix FD and negotiated MTU
    - Tracks `NotifyAcquired` property
    - Falls back to `StartNotify` path on `DBusException`
- [x] **BZ-1c** Add `write_value_fd()` and `read_notify_fd()` streaming helpers with auto-acquire + fallback
- [x] **BZ-1d** Add `release_acquired()` cleanup method to close fds
- [ ] **BZ-1e** Wire up to CLI: `--stream` flag on `read`/`write` debug commands
- [ ] **BZ-1f** Tests: mock-based unit tests for acquire/fallback logic

#### BZ-2: WriteAcquired / NotifyAcquired Property Read (MEDIUM)

**BlueZ API**: `WriteAcquired` (boolean, readonly) and `NotifyAcquired` (boolean, readonly) on `GattCharacteristic1` indicate whether an fd-based acquisition is active.

**BLEEP status**: Property names exist in `bt_ref/constants.py` (line 235-236), `core/config.py` (lines 80-81, 154-155), and `ble_ops/common/structural.py` (lines 38-39) as schema fields. However, `dbuslayer/characteristic.py` does NOT read these from D-Bus — they are never populated at runtime.

**Fix**: Read from D-Bus `GetAll` in characteristic init, same pattern as `MTU`/`Notifying`.

- [x] **BZ-2a** Read `WriteAcquired` and `NotifyAcquired` from D-Bus in `Characteristic.__init__` and expose as properties
- [x] **BZ-2b** Include in enumeration output (`conversion.py` characteristic display)
- [x] **BZ-2c** Populate from live Characteristic in `device_le.py` enumeration mapping

#### BZ-3: GATT Confirm Method (LOW)

**BlueZ API**: `Confirm()` — Server-only method to confirm an indication has been received. Only relevant when BLEEP acts as a GATT server.

**BLEEP status**: Missing. Only needed when GATT server (BZ-4) is implemented.

- [ ] **BZ-3a** Add `Confirm()` method to characteristic wrapper (gate behind GATT server feature flag)

#### BZ-4: GATT Server via GattManager1 (HIGH)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.GattManager.rst`):
- `RegisterApplication(object application, dict options)` — Register a D-Bus GATT application exposing services/characteristics
- `UnregisterApplication(object application)` — Unregister

**BLEEP status**: `bt_ref/constants.py` line 23 defines `GATT_MANAGER_INTERFACE = "org.bluez.GattManager1"` but no code calls `RegisterApplication` or `UnregisterApplication`. BLEEP is currently GATT client-only.

**Impact**: Cannot emulate BLE peripherals, create honeypot services, or run CTF challenge servers. This is a significant gap for security research and testing.

**Implementation plan**:
- [ ] **BZ-4a** Create `dbuslayer/gatt_server.py` with `GattApplication`, `GattServiceSkeleton`, `GattCharacteristicSkeleton`, `GattDescriptorSkeleton` classes implementing `org.freedesktop.DBus.ObjectManager`
- [ ] **BZ-4b** Add `register_application()` / `unregister_application()` methods calling `GattManager1` on adapter path
- [ ] **BZ-4c** Wire BZ-3 `Confirm()` for indication-based characteristics
- [ ] **BZ-4d** Create `modes/gatt_server.py` CLI mode and `bleep gatt-server` subcommand
- [ ] **BZ-4e** Example: simple GATT server with read/write/notify characteristics
- [ ] **BZ-4f** Documentation and tests

#### BZ-5: GattProfile1 Interface (LOW)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.GattProfile.rst`): Allows registering interest in specific GATT services for auto-connect.

**BLEEP status**: Missing. Lower priority since BLEEP handles connections explicitly.

- [ ] **BZ-5a** Implement `GattProfile1` registration for auto-reconnect scenarios

#### BZ-6 / BZ-7: LE Advertising Manager and Advertisement (HIGH)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.LEAdvertisingManager.rst`, `org.bluez.LEAdvertisement.rst`):
- `RegisterAdvertisement(object, dict)` / `UnregisterAdvertisement(object)` on `LEAdvertisingManager1`
- `LEAdvertisement1` properties: `Type` (broadcast/peripheral), `ServiceUUIDs`, `ManufacturerData`, `SolicitUUIDs`, `ServiceData`, `Data`, `Discoverable`, `DiscoverableTimeout`, `Includes`, `LocalName`, `Appearance`, `Duration`, `Timeout`, `SecondaryChannel`, `MinInterval`, `MaxInterval`, `TxPower`
- Manager properties: `ActiveInstances`, `SupportedInstances`, `SupportedIncludes`, `SupportedSecondaryChannels`, `SupportedCapabilities`, `SupportedFeatures`

**BLEEP status**: `bt_ref/constants.py` lines 29-30 define `ADVERTISEMENT_INTERFACE` and `ADVERTISING_MANAGER_INTERFACE` but no implementation exists. BLEEP cannot broadcast LE advertisements.

**Impact**: Critical for peripheral emulation, beacon testing, honeypot creation, and BLE security research.

**Implementation plan**:
- [x] **BZ-6a** `dbuslayer/le_advertising.py` — `LEAdvertisement` D-Bus object with full `LEAdvertisement1` property set via `GetAll`; `Release()` callback
- [x] **BZ-6b** `LEAdvertisingManager.register()` / `.unregister()` with async reply/error + 5s timeout
- [x] **BZ-6c** Capability property readers: `SupportedInstances`, `ActiveInstances`, `SupportedIncludes`, `SupportedSecondaryChannels`, `SupportedFeatures`, `SupportedCapabilities`
- [x] **BZ-7a** `modes/advertise.py` CLI mode — `bleep advertise caps` + `bleep advertise start`
- [x] **BZ-7b** Broadcast + peripheral types; configurable UUIDs, manufacturer data, service data, name, appearance, TX power, intervals, secondary channel, discoverable, includes
- [x] **BZ-7c** Documentation: `docs/le_advertising.md`
- [ ] **BZ-7d** Tests: mock-based unit tests

#### BZ-8: Device1 Disconnected Signal (MEDIUM)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.Device.rst`): `Disconnected(string reason, string message)` signal with reason codes (`org.bluez.Reason.ConnectionTimeout`, `ConnectionTerminatedByLocalHost`, etc.).

**BLEEP status**: `core/error_handling.py` lines 139-147 define `DISCONNECT_REASON_MAP` for all reason codes but it is NOT wired to actual signal subscription. Connection drops are detected only via `PropertiesChanged` on `Connected` property, losing the structured reason/message payload.

**Impact**: Cannot distinguish *why* a disconnect occurred (timeout vs. user-initiated vs. remote-initiated vs. link loss). This information is valuable for reliability analysis and automated reconnection logic.

- [x] **BZ-8a** Subscribe to `Disconnected` signal on Device1 objects in `dbuslayer/signals.py` via `_attach_bus_listeners`
- [x] **BZ-8b** Wire `DISCONNECT_REASON_MAP` in `error_handling.py` to parse the signal payload in `_device_disconnected` handler
- [x] **BZ-8c** Enrich `_device_connection_states` dict with `disconnect_reason`, `disconnect_message`, `disconnect_human` fields
- [x] **BZ-8d** Add `get_disconnect_reason(device_path)` public API for querying last disconnect reason
- [x] **BZ-8e** Forward to registered device instance via `on_disconnected(reason, message)` callback
- [ ] **BZ-8f** Surface disconnect reason in CLI output and debug mode (deferred to Sprint 5)

#### BZ-9 / BZ-10: Battery Provider (LOW)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.BatteryProvider.rst`, `org.bluez.BatteryProviderManager.rst`): Allows external applications to provide battery level information to BlueZ for devices that report battery via non-standard mechanisms.

**BLEEP status**: Missing. BLEEP reads `Battery1.Percentage` (consumer side) but cannot register as a battery provider.

**Impact**: Low — primarily useful for custom device drivers, not typical security research.

- [ ] **BZ-9a** Implement `BatteryProvider1` object and `BatteryProviderManager1.RegisterBatteryProvider()` in `dbuslayer/`
- [ ] **BZ-10a** Wire to CLI for devices with custom battery reporting

#### BZ-11 / BZ-12: Advertisement Monitor (HIGH)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.AdvertisementMonitor.rst`, `org.bluez.AdvertisementMonitorManager.rst`):
- `RegisterMonitor(object)` / `UnregisterMonitor(object)` on `AdvertisementMonitorManager1`
- Monitor properties: `Type` (or_patterns), `RSSILowThreshold`, `RSSIHighThreshold`, `RSSILowTimeout`, `RSSIHighTimeout`, `RSSISamplingPeriod`, `Patterns`
- Callbacks: `Activate()`, `Release()`, `DeviceFound(object)`, `DeviceLost(object)`

**BLEEP status**: Completely missing. No constants, no implementation.

**Impact**: Advertisement monitoring is the kernel-offloaded alternative to `SetDiscoveryFilter`. It allows pattern-based passive scanning with RSSI thresholds and device found/lost callbacks — critical for long-running surveillance, presence detection, and asset tracking scenarios. Without this, BLEEP must keep full discovery running and filter in userspace.

**Implementation plan**:
- [ ] **BZ-11a** Create `dbuslayer/adv_monitor.py` with `AdvertisementMonitor` D-Bus skeleton (ObjectManager + per-monitor objects)
- [ ] **BZ-11b** Implement pattern configuration (AD type + offset + content matching)
- [ ] **BZ-11c** Implement RSSI threshold and sampling period configuration
- [ ] **BZ-12a** Add `register_monitor()` / `unregister_monitor()` via `AdvertisementMonitorManager1`
- [ ] **BZ-12b** Wire `DeviceFound` / `DeviceLost` callbacks to observation pipeline
- [ ] **BZ-12c** Create `modes/monitor.py` or extend scan modes with `--monitor` flag
- [ ] **BZ-12d** Documentation and tests
- [ ] **BZ-12e** Reference: `workDir/BlueZScripts/example-adv-monitor` for implementation pattern

#### BZ-13 / BZ-14: Admin Policy (LOW)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.AdminPolicySet.rst`, `org.bluez.AdminPolicyStatus.rst`): Experimental interface for restricting which services are allowed on the adapter/device level.

**BLEEP status**: Missing.

**Impact**: Low — enterprise/MDM use case. However, reading `IsAffectedByPolicy` on devices could explain mysterious connection failures.

- [ ] **BZ-13a** Add `AdminPolicySet1.SetServiceAllowList()` support in adapter wrapper
- [ ] **BZ-14a** Read `AdminPolicyStatus1.IsAffectedByPolicy` in device property enumeration
- [ ] **BZ-14b** Surface policy-affected status in scan/enum output

#### BZ-15: DeviceSet1 Interface (MEDIUM)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.DeviceSet.rst`): Experimental. `Connect()`, `Disconnect()` on a set of coordinated devices (e.g., TWS earbuds). Properties: `Adapter`, `AutoConnect`, `Devices`, `Size`.

**BLEEP status**: BLEEP reads the Device1 `Sets` property via `device_le.get_device_sets()` (line 814-821) but does NOT interact with the `DeviceSet1` interface itself.

- [ ] **BZ-15a** Create `dbuslayer/device_set.py` to wrap `DeviceSet1` interface
- [ ] **BZ-15b** Add `connect_set()` / `disconnect_set()` methods
- [ ] **BZ-15c** Enumerate device sets in scan/enum output
- [ ] **BZ-15d** Surface in CLI (e.g., `bleep device-sets` command)

#### BZ-16: Bearer Split Interfaces (LOW)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.Bearer.LE.rst`, `org.bluez.Bearer.BREDR.rst`): Experimental. Per-bearer `Connect()`/`Disconnect()` and `Disconnected` signal with independent `Paired`/`Bonded`/`Connected` properties.

**BLEEP status**: Missing. `device_le.py` reads Device1 `PreferredBearer` property but does not use the per-bearer interface objects.

- [ ] **BZ-16a** Detect and enumerate `Bearer.LE1` / `Bearer.BREDR1` child interfaces on device objects
- [ ] **BZ-16b** Add per-bearer connect/disconnect to debug mode

#### BZ-17: Health Device Profile (LOW)

**BlueZ API** (`workDir/bluez/doc/health-api.txt`): `HealthManager1`, `HealthDevice1`, `HealthChannel1` for IEEE 11073 health devices.

**BLEEP status**: Missing. Only UUID/appearance classification strings reference "health."

**Impact**: Low — HDP is rarely used in practice, superseded by GATT-based health profiles.

- [ ] **BZ-17a** Stub `dbuslayer/health.py` for HDP if demand arises (low priority)

#### BZ-18: SIM Access Profile (LOW)

**BlueZ API** (`workDir/bluez/doc/sap-api.txt`): `SimAccess1.Disconnect()` + `Connected` property.

**BLEEP status**: Documented only — BlueZ's SAP is server-side (provides SIM to remote
clients, not the other way around).  BLEEP cannot read a phone's SIM via SAP.  See
`bleep/docs/bl_classic_mode.md` §2.13 for full explanation.

**Impact**: Low — niche automotive/hands-free SIM sharing; BlueZ API is too limited
for client-side SIM reading.

- [x] **BZ-18a** Documented SAP limitations in `bl_classic_mode.md` §2.13 (no stub needed)

#### BZ-19: MediaAssistant1 — Broadcast Audio Assistant (LOW)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.MediaAssistant.rst`): Experimental. `Push(dict)` method + `State`/`Metadata`/`QoS` properties for LE Audio Broadcast Assistant role.

**BLEEP status**: Missing.

**Impact**: Low — LE Audio is bleeding-edge; only relevant for Auracast/broadcast audio scenarios.

- [ ] **BZ-19a** Add `MediaAssistant1` wrapper when LE Audio support matures in BlueZ

#### BZ-20 through BZ-23: Deprecated Profile D-Bus APIs (LOW)

**Interfaces**: `ThermometerManager1`/`Thermometer1`, `HeartRateManager1`/`HeartRate1`, `CyclingSpeedManager1`/`CyclingSpeed1`, `ProximityMonitor1`/`ProximityReporter1`

**BlueZ docs**: `workDir/bluez/doc/thermometer-api.txt`, `workDir/bluez-tools/contrib/bluez-api-5.20-fixed/heartrate-api.txt`, `cyclingspeed-api.txt`, `proximity-api.txt`

**BLEEP status**: Missing for all four.

**Impact**: These are legacy BlueZ profile plugins (removed in BlueZ 5.48+). The functionality is now handled via standard GATT. BLEEP already interacts with these services via GATT characteristic read/write/notify. No implementation needed unless targeting legacy BlueZ installations.

- [ ] **BZ-20a** Document these as intentionally unsupported (BlueZ deprecated) in `docs/bluez_interface_properties.md`

#### BZ-24: Mesh ProvisionAgent1 OOB Hooks (MEDIUM)

**BlueZ API** (`workDir/bluez/doc/mesh-api.txt`): `ProvisionAgent1` methods: `PrivateKey`, `PublicKey`, `DisplayString`, `DisplayNumeric`, `PromptNumeric`, `PromptStatic`, `Cancel`. Properties: `Capabilities`, `OutOfBandInfo`, `URI`.

**BLEEP status**: `mesh/provision_agent.py` has the D-Bus skeleton with all method stubs, but all hooks raise `NotImplementedError` (lines 141-159). Properties `Capabilities`, `OutOfBandInfo`, `URI` are defined but not configurable.

- [ ] **BZ-24a** Implement OOB data exchange hooks (at minimum: `DisplayNumeric`, `PromptNumeric`, `PromptStatic`)
- [ ] **BZ-24b** Make `Capabilities` and `OutOfBandInfo` configurable via constructor args
- [ ] **BZ-24c** Wire to CLI mesh provisioning commands

#### BZ-25: Mesh Provisioner1 Reprovisioning (LOW)

**BlueZ API**: `RequestReprovData`, `ReprovComplete`, `ReprovFailed` methods on `Provisioner1`.

**BLEEP status**: `mesh/provisioner.py` implements `ScanResult`, `RequestProvData`, `AddNodeComplete`, `AddNodeFailed` but NOT the reprov* methods.

- [ ] **BZ-25a** Add `RequestReprovData`, `ReprovComplete`, `ReprovFailed` to mesh Provisioner skeleton

---

### Accepted Implementation Sprints (2026-04-02)

#### Sprint 1: Core Interaction Gaps — COMPLETE (2026-04-02)

Quick wins + highest-impact GATT/signal improvements. No new architectural patterns.

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 1 | BZ-2 | Read `WriteAcquired` / `NotifyAcquired` from D-Bus | 30 min | `dbuslayer/characteristic.py`, `ble_ops/common/conversion.py`, `dbuslayer/device_le.py` | [x] |
| 2 | BZ-8 | Device1 `Disconnected` signal subscription + reason capture | 2 hr | `dbuslayer/signals.py`, `core/error_handling.py` | [x] |
| 3 | BZ-1 | GATT `AcquireWrite` / `AcquireNotify` (fd-based streaming) | 3-4 hr | `dbuslayer/characteristic.py` | [x] |

**Dependency**: BZ-2 before BZ-1 (need `WriteAcquired`/`NotifyAcquired` to prevent double-acquire).

#### Sprint 2: LE Advertising — COMPLETE (2026-04-02)

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 4 | BZ-6/7 | LE Advertising Manager + Advertisement | 4-6 hr | `dbuslayer/le_advertising.py`, `modes/advertise.py`, `cli.py`, `bt_ref/constants.py` | [x] |

**Implementation details:**

- [x] **BZ-6a** `LEAdvertisement(dbus.service.Object)` — exports all BlueZ `LEAdvertisement1` properties via `GetAll`; `Release()` callback; `AdvertisementConfig` dataclass covers Type, ServiceUUIDs, ManufacturerData, SolicitUUIDs, ServiceData, LocalName, Includes, Appearance, Discoverable, DiscoverableTimeout, Duration, Timeout, TxPower, MinInterval, MaxInterval, SecondaryChannel, Data
- [x] **BZ-7a** `LEAdvertisingManager` wrapper — `register()`/`unregister()` with async reply/error + 5s timeout; property readers for ActiveInstances, SupportedInstances, SupportedIncludes, SupportedSecondaryChannels, SupportedFeatures, SupportedCapabilities
- [x] **BZ-7b** `bleep advertise` CLI subcommand — `caps` (capabilities) and `start` (broadcast with full flag set); clean SIGINT/SIGTERM shutdown; `--local-duration` and `--duration` (BlueZ-level timeout)
- [x] **BZ-7c** Documentation: `docs/le_advertising.md` — architecture, D-Bus flow, CLI examples, Python API, troubleshooting
- [ ] **BZ-7d** Tests: mock-based unit tests for LEAdvertisement/LEAdvertisingManager

#### Sprint 3: GATT Server (HIGH priority — v2.9.0 target)

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 5 | BZ-4 | GATT Server (`GattManager1.RegisterApplication`) | 8-12 hr | New: `dbuslayer/gatt_server.py`, `modes/gatt_server.py` | [ ] |
| 6 | BZ-3/5 | `Confirm()` + `GattProfile1` (dependent on BZ-4) | 1 hr | `dbuslayer/gatt_server.py` | [ ] |

#### Sprint 4: Advertisement Monitor — COMPLETE (2026-04-02)

Kernel-offloaded pattern-based passive scanning. Independent of Sprints 2-3.
Works **without** an active `StartDiscovery` session once bluetoothd activates the monitor job.

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 7 | BZ-11/12 | Advertisement Monitor + Manager | 4-6 hr | `dbuslayer/adv_monitor.py`, `modes/monitor.py`, `cli.py`, `bt_ref/constants.py` | [x] |

**Detailed Sprint 4 Implementation Plan**

Reference docs:
- API: `workDir/BlueZDocs/org.bluez.AdvertisementMonitor.rst`
- Manager API: `workDir/BlueZDocs/org.bluez.AdvertisementMonitorManager.rst`
- Reference impl: `workDir/BlueZScripts/example-adv-monitor` (404 lines)

Architecture overview:
- The client (BLEEP) registers an **application root path** with `AdvertisementMonitorManager1.RegisterMonitor(app_root)` on the adapter.
- Under that root, BLEEP exposes one or more **monitor objects** implementing:
  - `org.freedesktop.DBus.Properties.GetAll(s)` → returns monitor config
  - `org.freedesktop.DBus.ObjectManager.GetManagedObjects()` on app root
  - `InterfacesAdded` / `InterfacesRemoved` signals on app root
  - Methods invoked **by bluetoothd**: `Activate()`, `Release()`, `DeviceFound(o)`, `DeviceLost(o)`
- Each monitor has: `Type` ("or_patterns"), RSSI thresholds/timeouts, `Patterns` (array of `(start_pos: u8, ad_type: u8, content: ay)`)
- Once activated, device found/lost callbacks fire without needing `StartDiscovery`.

**Sub-tasks:**

BZ-11 — `dbuslayer/adv_monitor.py` (D-Bus layer):

- [x] **BZ-11a** `AdvMonitor(dbus.service.Object)` class — `dbuslayer/adv_monitor.py`
    - D-Bus path: `{app_root}/monitor{id}`
    - Properties via `GetAll(s)`: Type, RSSIHighThreshold/Timeout, RSSILowThreshold/Timeout, RSSISamplingPeriod, Patterns `a(yyay)`
    - Callback methods: `Activate()`, `Release()`, `DeviceFound(o)`, `DeviceLost(o)`
    - `remove_monitor()` — calls `remove_from_connection()`

- [x] **BZ-11b** `AdvMonitorApp(dbus.service.Object)` class — `dbuslayer/adv_monitor.py`
    - Implements `ObjectManager`: `GetManagedObjects()`, `InterfacesAdded`/`InterfacesRemoved` signals
    - `add_monitor()` / `remove_monitor()` / `remove_all()` lifecycle management

- [x] **BZ-11c** `RSSIConfig` dataclass with high/low threshold, timeout, sampling_period fields

- [x] **BZ-11d** `MonitorPattern` dataclass + `to_dbus()` converter; AD type constants provided

BZ-12 — Manager + CLI integration:

- [x] **BZ-12a** `AdvMonitorManager` wrapper class — `dbuslayer/adv_monitor.py`
    - `register(app)` / `unregister(app)` with async reply/error + 5 s timeout
    - `get_supported_types()` / `get_supported_features()` property readers

- [x] **BZ-12b** `DeviceFound`/`DeviceLost` callbacks wired via `MonitorCallbacks` dataclass
    - MAC extraction from device object path; real-time console output in `modes/monitor.py`
    - Observation pipeline integration deferred to future PR (requires GLib↔thread bridge)

- [x] **BZ-12c** `bt_ref/constants.py` entries added: `ADV_MONITOR_INTERFACE`, `ADV_MONITOR_MANAGER_INTERFACE`, `ADV_MONITOR_APP_BASE_PATH`

- [x] **BZ-12d** `bleep monitor` subcommand in `modes/monitor.py` + `cli.py`
    - Sub-actions: `caps` (show capabilities), `start` (register monitor + stream events)
    - Flags: `--pattern OFF:AD:HEX` (repeatable), `--rssi-high/low`, `--rssi-high/low-timeout`, `--sampling-period`, `--duration`
    - Clean shutdown via SIGINT/SIGTERM

- [ ] **BZ-12e** Alternative: `--monitor` flag on existing `bleep scan` command (deferred)

- [ ] **BZ-12f** Documentation: `docs/adv_monitor.md` with usage examples
- [ ] **BZ-12g** Tests: mock-based unit tests for AdvMonitor/AdvMonitorApp/AdvMonitorManager

#### Sprint 5: Enrichment & Completeness (MEDIUM priority — v2.9.x)

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 8 | BZ-15 | DeviceSet1 interface (TWS/coordinated sets) | 2-3 hr | New: `dbuslayer/device_set.py` | [ ] |
| 9 | BZ-24 | Mesh ProvisionAgent1 OOB hook implementations | 2-3 hr | `mesh/provision_agent.py` | [ ] |
| 10 | BZ-13/14 | AdminPolicySet1 / AdminPolicyStatus1 | 1-2 hr | `dbuslayer/adapter.py`, device wrappers | [ ] |
| 11 | BZ-20a | Document deprecated profile APIs as intentionally unsupported | 30 min | `docs/bluez_interface_properties.md` | [ ] |

#### Sprint 6: Niche / Experimental (LOW priority — v3.0+, backlog)

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 12 | BZ-9/10 | BatteryProvider registration | 1-2 hr | New: `dbuslayer/battery_provider.py` | [ ] |
| 13 | BZ-16 | Bearer.LE1 / Bearer.BREDR1 split interfaces | 1-2 hr | Device wrappers | [ ] |
| 14 | BZ-17 | Health Device Profile (HDP) | 2-3 hr | New: `dbuslayer/health.py` (if demanded) | [ ] |
| 15 | BZ-18 | SIM Access Profile | 1 hr | New: `dbuslayer/sap.py` (if demanded) | [ ] |
| 16 | BZ-19 | MediaAssistant1 (Broadcast Audio) | 2-3 hr | `dbuslayer/media.py` (when LE Audio matures) | [ ] |
| 17 | BZ-25 | Mesh reprovisioning methods | 1 hr | `mesh/provisioner.py` | [ ] |

---

### Items Confirmed PRESENT (No Gap)

For completeness, these BlueZ interfaces/features were verified as **fully implemented** in BLEEP:

| Interface / Feature | BLEEP Implementation |
|--------------------|--------------------|
| `Adapter1` — all properties (Address, AddressType, Name, Alias, Class, Powered, PowerState, Discoverable, Pairable, Connectable, timeouts, Discovering, UUIDs, Modalias, Roles, ExperimentalFeatures, Manufacturer, Version) | `dbuslayer/adapter.py`, `modes/adapter_config.py` |
| `Adapter1` — all methods (StartDiscovery, StopDiscovery, SetDiscoveryFilter, GetDiscoveryFilters, RemoveDevice) | `dbuslayer/adapter.py`, `dbuslayer/manager.py` |
| `Device1` — all properties (Address through PreferredBearer, Sets) | `dbuslayer/device_le.py`, `dbuslayer/device_classic.py` |
| `Device1` — methods (Connect, Disconnect, Pair, CancelPairing, ConnectProfile, DisconnectProfile, GetServiceRecords) | `dbuslayer/device_le.py`, `dbuslayer/device_classic.py`, `modes/pair.py` |
| `GattService1`, `GattCharacteristic1` (ReadValue, WriteValue, StartNotify, StopNotify, MTU, Notifying, Flags), `GattDescriptor1` | `dbuslayer/service.py`, `dbuslayer/characteristic.py`, `dbuslayer/descriptor.py` |
| `Agent1` — all methods (Release through Cancel), `AgentManager1` | `dbuslayer/agent.py`, `dbuslayer/agent_io.py` |
| `Battery1` (Percentage, Source) | `ble_ops/le/scan.py`, `ble_ops/common/conversion.py` |
| `Input1` (ReconnectMode) | `ble_ops/le/scan.py`, `ble_ops/common/conversion.py` |
| `Media1`, `MediaPlayer1`, `MediaTransport1`, `MediaControl1`, `MediaEndpoint1`, `MediaFolder1`, `MediaItem1` | `dbuslayer/media.py`, `dbuslayer/media_stream.py`, `dbuslayer/media_browse.py` |
| `Network1`, `NetworkServer1` | `dbuslayer/network.py`, `ble_ops/classic/pan.py` |
| `Profile1`, `ProfileManager1` | `dbuslayer/spp_profile.py` |
| OBEX: `Client1`, `Session1`, `Transfer1`, `ObjectPush1`, `FileTransfer1`, `PhonebookAccess1`, `MessageAccess1`, `Message1`, `Synchronization1`, `Image1` | `dbuslayer/obex_*.py`, `ble_ops/classic/` (pbap, map, opp, ftp, bip, sync) |
| `PropertiesChanged` / `InterfacesAdded` / `InterfacesRemoved` signal handling | `dbuslayer/signals.py` |
| Mesh: `Network1`, `Node1`, `Management1`, `Application1`, `Element1`, `Provisioner1` (partial), `ProvisionAgent1` (skeleton) | `mesh/` package |

---

## Specialized Testing Modes

- [x] **BLE CTF Mode Completion**
  - [x] Implement automated flag discovery patterns
  - [x] Create CTF-specific visualization of device state
  - [x] Add automated solve strategies for common challenge types
  - [x] Document CTF mode usage and extension points
  - [x] Validate against known CTF devices
  - [x] Add ability to write to any characteristic (not just Flag-Write)
  - [x] Add flexible data format options for writing values (hex, byte, string)

- [ ] **Pico-W Testing Mode**
  - [ ] Research Pico W BLE implementation specifics
  - [ ] Create Pico W device profile with expected characteristics
  - [ ] Implement special handlers for Pico W quirks
  - [ ] Build test suite for Pico W-specific features
  - [ ] Create documentation with Pico W examples

- [ ] **BW-16 Testing Mode**
  - [ ] Research BW-16 BLE stack implementation
  - [ ] Implement BW-16 specific enumeration helpers
  - [ ] Create test fixtures for BW-16 devices
  - [ ] Document BW-16 mode usage

- [ ] **Scratch Space Mode**
  - [ ] Design flexible command execution framework
  - [ ] Implement batch processing of operations
  - [ ] Add support for operation sequence files
  - [ ] Create examples of advanced workflows
  - [ ] Document extension points

## Advanced Control Features

- [x] **Signal Capture System**
  - [x] Create `bleep/signals/capture_config.py` for configuration
  - [x] Implement signal routing and filtering
  - [x] Add persistent signal configuration storage
  - [x] Create CLI for signal configuration
  - [x] Document signal capture patterns
  - [x] Create examples of signal capture workflows
  - [x] Fix signal integration with application startup
  - [x] Add proper database routes for read/write/notification events
  - [x] Enhance CTF module to properly emit signals for characteristic operations
  - [x] Implement robust error handling for signal processing

- [ ] **Offline Device Analysis**
  - [ ] Design device structure serialization format
  - [ ] Implement export/import of device structures
  - [ ] Create visualization tools for offline analysis
  - [ ] Add differential analysis between captures
  - [ ] Document offline analysis workflow

- [ ] **Directed Device Assessment**
  - [ ] **Phase 1: Design & Architecture** (2 weeks)
    - [ ] Design targeted scanning framework
      - [ ] Identify common Bluetooth vulnerability patterns
      - [ ] Review existing security assessment methodologies
      - [ ] Define assessment categories (authentication, encryption, firmware, etc.)
      - [ ] Create plugin-based assessment architecture
      - [ ] Design rule engine for vulnerability detection
      - [ ] Define interfaces between scanning and assessment components
    - [ ] Device fingerprinting system design
      - [ ] Create schema for device fingerprints
      - [ ] Define fingerprint matching algorithm 
      - [ ] Plan fingerprint storage and retrieval
      - [ ] Design multi-factor fingerprinting (service patterns, response timing, etc.)
      - [ ] Create manufacturer-specific detection patterns
  - [ ] **Phase 2: Core Implementation** (3 weeks)
    - [ ] Implement device fingerprinting
      - [ ] Implement fingerprint collection during scans
      - [ ] Create fingerprint matching and identification system
      - [ ] Build baseline database of common device fingerprints
      - [ ] Add manufacturer-specific detection logic
    - [ ] Create vulnerability assessment helpers
      - [ ] Implement authentication bypass detection
      - [ ] Develop weak encryption identification
      - [ ] Create plaintext credential transmission detection
      - [ ] Implement replay attack vulnerability detection
      - [ ] Add firmware version fingerprinting
      - [ ] Create modular system for new vulnerability checks
      - [ ] Develop severity scoring system for findings
  - [ ] **Phase 3: Reporting & Integration** (2 weeks)
    - [ ] Build reporting tools
      - [ ] Implement vulnerability report generator
      - [ ] Create multiple output formats (Markdown, JSON, HTML)
      - [ ] Add visualization capabilities for assessment results
      - [ ] Implement comparison tools for multiple assessments
      - [ ] Create trend analysis for device improvements over time
    - [ ] Integration with existing components
      - [ ] Integrate with AoI analysis system
      - [ ] Connect to observation database
      - [ ] Link with signal capture system
      - [ ] Add CLI commands for directed assessment
      - [ ] Create programmatic API for assessment functions
  - [ ] **Phase 4: Documentation & Polish** (1 week)
    - [ ] Document assessment methodologies
      - [ ] Create user guides for directed assessment
      - [ ] Document assessment plugin architecture
      - [ ] Provide examples of common vulnerability patterns
      - [ ] Create reference for all assessment commands
      - [ ] Add developer documentation for extending assessment capabilities
    - [ ] Final polish
      - [ ] Optimize performance for large-scale assessments
      - [ ] Implement caching for repeated assessments
      - [ ] Add progress reporting for long-running assessments
      - [ ] Create sample assessment configurations

## Documentation Improvements

> This section tracks gaps in current documentation, particularly for the device tracking and observation capabilities. Addressing these tasks will ensure users can fully leverage the existing features through both CLI and programmatic APIs.

- [x] **Device Tracking Documentation** (Complete)
  - [x] Create comprehensive programmatic API reference for observation module
    - [x] Document each function in `observations.py` with examples (see `observation_db.md` - "Public Function Reference" section)
    - [x] Add integration examples for custom scripts (see `observation_db.md` - "Programmatic Access" section)
    - [x] Create cookbook for common observation tasks (see `observation_db_schema.md` - "Advanced Query Cookbook" section)
    - [x] Document filtering and query techniques for device data (see `observation_db.md` and `observation_db_schema.md`)
  - [x] Enhance AOI Analyzer documentation
    - [x] Create dedicated `aoi_security_algorithms.md` file documenting all security analysis algorithms
    - [x] Add examples of direct usage of AOIAnalyser class methods (see `aoi_mode.md` and `aoi_implementation.md`)
    - [x] Document security analysis algorithms and scoring system (see `aoi_security_algorithms.md`)
    - [x] Provide customization examples for different analysis needs (see `aoi_customization_guide.md`)
  - [x] Add real-world usage scenarios
    - [x] Long-term device monitoring workflows (see `observation_db_usage_scenarios.md`)
    - [x] Enterprise device tracking patterns (see `observation_db_usage_scenarios.md`)
    - [x] Security assessment workflows using observation database (see `observation_db_usage_scenarios.md`)
    - [x] Integration examples with external systems (see `observation_db_usage_scenarios.md`)
  - [x] Document detailed database schema
    - [x] Create complete schema diagram with relationships (see `observation_db_schema.md`)
    - [x] Document each table and column with descriptions (see `observation_db_schema.md` - comprehensive table documentation)
    - [x] Add query examples for complex data extraction (see `observation_db_schema.md` - "Advanced Query Cookbook")
    - [x] Create migration guide for schema changes (see schema version history in `observation_db_schema.md`)

## Technical Scalability Improvements

- [x] **Database Optimization**
  - [x] Implement indexing strategy for observation database
  - [x] Add query optimization for large device sets
  - [x] Create database maintenance utilities
  - [x] Document database schema and optimization techniques

- [ ] **Automatic PIN Code Storage and Retrieval**
  - [ ] **Phase 1: Database Schema Extension** (2-4 hours)
    - [ ] Add `device_pin_codes` table to observation database schema
      - [ ] Columns: `mac` (TEXT, FK to devices), `pin_code` (TEXT, encrypted or plain based on security requirements), `pin_type` (TEXT: "legacy", "ssp_passkey"), `source` (TEXT: "user_entered", "auto_detected", "stored_from_pairing"), `last_used` (DATETIME), `success_count` (INT), `failure_count` (INT), `ts` (DATETIME)
      - [ ] Indexes: `idx_device_pin_codes_mac`, `idx_device_pin_codes_last_used`
      - [ ] Migration: Create v8 schema migration from v7
    - [ ] Add `upsert_device_pin_code(mac: str, pin_code: str, pin_type: str, source: str)` function
    - [ ] Add `get_device_pin_code(mac: str, pin_type: str) -> Optional[str]` function
    - [ ] Add `get_device_pin_codes(mac: str) -> List[Dict]` function for all PIN types
    - [ ] Add `increment_pin_success(mac: str, pin_code: str)` and `increment_pin_failure(mac: str, pin_code: str)` functions
    - [ ] Update `__all__` export list
  - [ ] **Phase 2: IO Handler Integration** (4-6 hours)
    - [ ] Create `DatabaseIOHandler` class extending `AgentIOHandler`
      - [ ] Implement `request_pin_code()` to query database first, fallback to default/user input
      - [ ] Implement `request_passkey()` to query database first, fallback to default/user input
      - [ ] Store successful PIN codes after successful pairing
      - [ ] Track PIN code usage statistics (success/failure counts)
    - [ ] Modify `AutoAcceptIOHandler` to support database lookup
      - [ ] Add optional `use_database: bool` parameter
      - [ ] Query database before returning default PIN
      - [ ] Store PIN codes after successful pairing
    - [ ] Modify `ProgrammaticIOHandler` to support database lookup
      - [ ] Add optional `use_database: bool` parameter
      - [ ] Query database before calling callback or returning default
    - [ ] Modify `CliIOHandler` to support database lookup
      - [ ] Add optional `use_database: bool` parameter
      - [ ] Query database and suggest PIN to user
      - [ ] Store user-entered PIN codes after successful pairing
  - [ ] **Phase 3: Agent Integration** (3-4 hours)
    - [ ] Update `create_agent()` to accept `use_database_pin: bool` parameter
    - [ ] Update `SimpleAgent`, `InteractiveAgent`, `EnhancedAgent`, `PairingAgent` to support database PIN lookup
    - [ ] Add `--use-database-pin` CLI argument to `bleep agent` command
    - [ ] Integrate PIN storage after successful pairing in agent methods
    - [ ] Add logging for database PIN lookup (success/failure, source)
  - [ ] **Phase 4: Pairing Success Detection** (2-3 hours)
    - [ ] Detect successful pairing completion
      - [ ] Monitor `PropertiesChanged` signal for `Paired=True` property
      - [ ] Correlate with recent `RequestPinCode`/`RequestPasskey` events
      - [ ] Store PIN code used in successful pairing
    - [ ] Handle pairing failure scenarios
      - [ ] Track failed PIN attempts (don't store failed PINs)
      - [ ] Increment failure count for stored PINs
      - [ ] Optionally remove PINs with high failure rates
  - [ ] **Phase 5: CLI and Documentation** (2-3 hours)
    - [ ] Add `bleep db pin-codes` command to list stored PIN codes
    - [ ] Add `bleep db pin-code <MAC> [--set <PIN>]` command to view/set PIN codes
    - [ ] Add `bleep db pin-code <MAC> --remove` command to delete stored PIN codes
    - [ ] Update `observation_db.md` with PIN code storage documentation
    - [ ] Update `agent_mode.md` with `--use-database-pin` flag documentation
    - [ ] Add examples of automatic PIN code usage
    - [ ] Document security considerations (encryption, plain text storage)
  - [ ] **Phase 6: Testing and Validation** (2-3 hours)
    - [ ] Unit tests for database PIN code functions
    - [ ] Integration tests for database IO handler
    - [ ] Test PIN code retrieval during pairing
    - [ ] Test PIN code storage after successful pairing
    - [ ] Test fallback behavior when database PIN not found
    - [ ] Test CLI commands for PIN code management
  - [ ] **Security Considerations**:
    - [ ] Document whether PIN codes should be encrypted at rest
    - [ ] Consider adding `--encrypt-pins` flag for sensitive deployments
    - [ ] Add option to mask PIN codes in logs (already partially implemented)
    - [ ] Document access control recommendations for database file
  - [ ] **Future Enhancements** (not in initial implementation):
    - [ ] PIN code encryption at rest
    - [ ] Per-device PIN code expiration
    - [ ] PIN code rotation policies
    - [ ] Integration with external credential stores
    - [ ] PIN code sharing across multiple BLEEP instances

- [ ] **Memory Management**
  - [ ] Audit large data structure usage
  - [ ] Implement lazy loading patterns for device maps
  - [ ] Add resource cleanup hooks
    - [ ] **Device object cleanup** (`bleep/dbuslayer/device_le.py`, `bleep/dbuslayer/device_classic.py`)
      - [ ] Add `cleanup()` method to device classes (clear GATT mappings, unregister signal handlers, release D-Bus proxy references, clear cached data)
      - [ ] Add `__del__()` method for automatic cleanup (with error handling)
      - [ ] Add context manager support (`__enter__`, `__exit__`)
    - [ ] **Signal handler cleanup** (`bleep/dbuslayer/signals.py`)
      - [ ] Ensure all signal handlers can be unregistered
      - [ ] Add `unregister_device()` method to signals manager
      - [ ] Track registered handlers for cleanup
      - [ ] Add cleanup in device `__del__` methods
    - [ ] **D-Bus connection cleanup** (`bleep/dbus/connection_pool.py`)
      - [ ] Ensure connections are properly closed
      - [ ] Add connection age limits
      - [ ] Implement automatic cleanup of stale connections
      - [ ] Add `cleanup_stale_connections()` method
    - [ ] **Cache size limits** (`bleep/dbuslayer/bond_storage.py`)
      - [ ] Add max size limit to `PairingCache`
      - [ ] Implement LRU eviction when cache exceeds limit
      - [ ] Add `max_size` parameter to `__init__()`
      - [ ] Add `get_cache_stats()` method
    - [ ] **Database query result streaming** (`bleep/core/observations.py`)
      - [ ] For large result sets, use generators instead of lists
      - [ ] Modify `get_devices()` to support streaming mode
      - [ ] Add `get_devices_streaming()` function for large datasets
      - [ ] Update `get_characteristic_timeline()` to use generators for large limits
  - [ ] Document memory usage patterns and recommendations

- [x] **D-Bus Reliability**
  - [x] Enhance BlueZ stall detection
    - [x] Implement timeout enforcement layer for D-Bus method calls (`bleep/dbus/timeout_manager.py`)
    - [x] Create heartbeat mechanism to detect unresponsive BlueZ services (`bleep/dbuslayer/bluez_monitor.py`)
    - [x] Implement controller health metrics collection (`bleep/core/metrics.py`)
  - [x] Implement automatic recovery strategies
    - [x] Build connection reset manager with staged recovery (`bleep/dbuslayer/recovery.py`)
    - [x] Develop state preservation system for connection recovery (`bleep/dbuslayer/recovery.py`)
    - [x] Add progressive backoff for reconnection attempts (`bleep/dbuslayer/recovery.py`)
  - [x] Add connection pooling for high-volume operations
    - [x] Create managed pool of D-Bus connections (`bleep/dbus/connection_pool.py`)
    - [x] Implement D-Bus proxy object cache (`bleep/dbus/connection_pool.py`)
    - [x] Add request batching for related operations (`bleep/dbus/connection_pool.py`)
  - [x] Document D-Bus reliability best practices
    - [x] Create comprehensive D-Bus interaction guidelines (`bleep/docs/dbus_best_practices.md`)
    - [x] Document common failure modes and recovery patterns (`bleep/docs/dbus_best_practices.md`)
    - [x] Add examples and templates for robust D-Bus usage (`bleep/docs/d-bus-reliability.md`)
    - [x] Create diagnostic tools for troubleshooting (`bleep/scripts/dbus_diagnostic.py`)

- [x] **RSSI Capture Enhancement for Scan Operations** - **COMPLETE**
  - [x] **Phase 1: RSSI capture during discovery** (`bleep/dbuslayer/manager.py`, `bleep/dbuslayer/signals.py`)
    - [x] Add `_rssi_cache` dictionary and `_rssi_cache_lock` to `system_dbus__bluez_device_manager` class
    - [x] Add `_discovery_active` flag and `is_discovery_active()` method to track discovery state
    - [x] Implement `_capture_rssi_from_signal(mac_address: str, rssi: int)` method to store RSSI in cache
    - [x] Add `get_captured_rssi(mac_address: str) -> Optional[int]` method to retrieve cached RSSI
    - [x] Add `clear_rssi_cache()` method to clear cache when discovery starts/stops
    - [x] Enhance `_properties_changed()` in `system_dbus__bluez_signals` to detect RSSI updates and forward to DeviceManager
    - [x] Add `register_device_manager()` method to signals manager for RSSI forwarding
  - [x] **Phase 2: RSSI merge in get_discovered_devices()** (`bleep/dbuslayer/adapter.py`)
    - [x] Store `_device_manager` reference in `system_dbus__bluez_adapter` class (already exists via `create_device_manager()`)
    - [x] Enhance `get_discovered_devices()` to merge RSSI from DeviceManager cache after `GetManagedObjects()` results
    - [x] Update device dict with cached RSSI if available and current RSSI is None
    - [x] Fix MAC address format mismatch - normalize to lowercase for cache lookup
  - [x] **Phase 3: Properties.Get() fallback (connected devices only)** (`bleep/dbuslayer/adapter.py`)
    - [x] Add fallback logic to query `Properties.Get(DEVICE_INTERFACE, "RSSI")` for devices with `None` RSSI
    - [x] Only query Properties.Get() for devices where `connected == True`
    - [x] Skip Properties.Get() for disconnected devices (accept "? dBm" as expected behavior)
    - [x] Handle `DBusException` gracefully (RSSI may not exist even for connected devices)
  - [x] **Phase 4: Integration and cleanup** (`bleep/dbuslayer/manager.py`)
    - [x] Clear RSSI cache in `start_discovery()` before starting discovery
    - [x] Preserve RSSI cache after discovery completes (removed premature clearing in `_cleanup_after_run()`)
    - [x] Register DeviceManager with signals manager in `run()` method for RSSI forwarding
  - [x] **Phase 5: Testing and validation** - **Validated in production**
    - [x] RSSI values now appear correctly in scan results
    - [x] MAC address format normalization verified
    - [x] Cache timing issues resolved
    - [x] Backward compatibility maintained (existing scan functionality unchanged)

## CLI Command Enhancements (Completed)

- [x] **UUID Translation System** – Comprehensive UUID translation functionality:
  - [x] Core translation engine (`bleep/bt_ref/uuid_translator.py`) with modular architecture
  - [x] Support for 16-bit, 32-bit, and 128-bit UUID formats
  - [x] Automatic expansion of 16-bit UUIDs to find all potential matches
  - [x] Searches across all BLEEP UUID databases (Services, Characteristics, Descriptors, Members, SDOs, Service Classes, Custom)
  - [x] CLI command (`bleep uuid-translate` / `bleep uuid-lookup`) with JSON and verbose options
  - [x] Interactive mode integration (`uuid` command)
  - [x] User mode integration (menu option 5)
  - [x] Comprehensive documentation (`uuid_translation.md`, `uuid_translation_plan.md`)
  - [x] Complete test suite with all tests passing
  - [x] Modular design for easy extension (custom format handlers, new database sources)

- [x] **Explore Command Fixes**
  - [x] Fix parameter conflict between CLI mode and connection mode
  - [x] Improve passive scan reliability with better timeout distribution
  - [x] Add proper connection retries to passive mode
  - [x] Update help text and documentation
  - [x] Create comprehensive documentation in `explore_mode.md`

- [x] **Analyze Command Enhancements**
  - [x] Add support for both American (`analyze`) and British (`analyse`) spellings
  - [x] Implement detailed analysis mode with `--detailed` flag
  - [x] Fix JSON format compatibility for different file structures
  - [x] Improve output formatting with device information
  - [x] Create comprehensive documentation in `analysis_mode.md`

- [x] **Other CLI Improvements**
  - [x] Add debug flag to `classic-scan` mode
  - [x] Fix `aoi` mode to accept test file parameter, resolve sys module scope issue, and automatically use 'scan' subcommand
  - [x] Fix `aoi` mode errors by adding missing NotAuthorizedError class and fixing return value handling
  - [x] Fix `aoi` subcommands (analyze, list, report, export) to properly work with the CLI
  - [x] Add proper parameter handling for all AOI subcommands in the CLI parser
  - [x] Implement basic device data storage and retrieval for AOI mode
  - [x] Implement report generation in three formats (markdown, JSON, text) for AOI mode
  - [x] Add fallback analysis for AOI analyze command when full implementation is missing
  - [x] Create comprehensive documentation for the AOI mode in `aoi_mode.md`
  - [x] Fix user mode scan incorrectly reporting "no devices found" when devices are actually found
  - [x] Fix _native_scan function to properly return device dictionary instead of status code
  - [x] Add quiet parameter to passive_scan to prevent duplicate output
  - [x] Improve device display format in user mode scan to use "Address (Name) - RSSI: value dBm" format
  - [x] Update device menu options to consistently use the same format
  - [x] Fix InvalidArgs error when connecting to OnePlus devices
  - [x] Fix MediaPlayer1 Press method to accept hex values

## Previous and unincorporated To Do lists:

### TODO:
   [ ] Create a function that searches through the Managed Objects for known Bluetooth objects (to the device that the code is running on)
       - Note: Could make good OSINT capabilitiy
   [ ] Check to see what type of device is being connected to
       [ ] If BLE then connect with BLE Class structure
       [ ] If BT then connect with Bluetooth Classic structure
   [x] Create function mode that allows connecting directly to a specific device
       - Note: Would attempt to connect regardless if in range of not; leverage D-Bus API (adapter? expermental capability)
   [x] Improve error handling so that errors due not set everything to "None" but produce another set output (e.g. "ERROR")
   [ ] Update the expected code structures bsaed on the updated BlueZ git documentation
       - e.g. Error Codes, Responses, S/C/D properties
       [ ] Look at updating any internal/code JSON references for expected data-structures
   [ ] Create a decode + translation function for ManufacturerData using the "formattypes.yaml" BT SIG document
       - Expectation is that this is how one can interpret the rest of the passed information where the SECOND OCTET is the "formattype" data type indicator
   [x] Create a decode + translation function for Class data
       [x] Hardcode Transation first to prove concept
       [ ] Move to automatic pull down of YAML to perform conversion
   [x] Create a decode for appearance values
       - Pull from bluetooth support files to better identify (e.g. similar to Class data)
   [x] Add PnP ID characteristic (0x2A50) decoding into the "detailed on" verbosity within the Debug Mode
       - Correctly identify and display Device ID information from PnP ID and modalias
   [ ] Add functionality to re-read/refresh the device interface information
       - Note: This is most likely where the D-Bus can read the GAP information (i.e. 0x1800)
   [x] Add read-in and generation of UUIDs to create UUID Check lists (Service, Characteristic, Descriptor)
       - [x] Implemented comprehensive UUID translation system with CLI command
       - [x] Supports all UUID types (Service, Characteristic, Descriptor, Member, SDO, Service Class)
       - [x] Interactive and programmatic access via `bleep uuid-translate` command
       - [x] Integrated into interactive and user modes
   [ ] Make use of the "ARDUINO_BLE__BLE_UUID__MASK" variable to identify "groupings" of UUIDs
       - Note: May be using the same Bluetooth SIG default UUID structure
   [ ] Determine why pairing a device causes BIP to lose conneciton to the device
   [x] Improving decoding information to use the BT SIG yaml files
   [ ] Have the Mine/Permission mapping include a tracking of the associated error
       - Make as a tuple? Perhaps dictionary?
   [ ] Determine how to query if an action is in process for D-Bus/BlueZ
   [ ] Add pairing to BLEEP
       [ ] Basic pairing to a targeted device
       [ ] Selective pairing to a targeted device
       - Note: Research on the process shows that the communication "handshake" for Pairing() begins, but then fails due to lack of agent
           - URL:      https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc/org.bluez.Agent.rst
### TODO (vendor-specific SDP services / proprietary profiles):
   [ ] Samsung IcService_New (`a23d00bc-217c-123b-9c00-fc44577136ee`) — reverse-engineer wire protocol
       - Observed on SAMSUNG-SM-G891A (Galaxy S7 Active), RFCOMM channel 5
       - UUID registered in `bleep/bt_ref/constants.py`, documented in `bleep/docs/bl_classic_mode.md`
       - Service accepts RFCOMM connections when phone is awake/unlocked, but uses unknown proprietary protocol
       - Probe result: [SILENT] after ~5s — no initial banner or handshake from remote
       - `copen 5` + `craw` → `str:HELO send` → 9B sent, no response from device
       - Gap: No protocol dissector — only raw RFCOMM I/O via copen/csend/crecv/craw
       - Gap: No dedicated command suite (e.g. `cicservice`) for structured interaction
       - Gap: Phone screen must be awake for RFCOMM channel to accept connections
       [ ] Capture and analyze traffic between Samsung Flow PC client ↔ phone to reverse-engineer the protocol framing
       [ ] Identify handshake/auth sequence (likely Samsung Accessory Protocol or SMEP variant)
       [ ] Determine if the service responds to Samsung Accessory SDK discovery messages
       [ ] Cross-reference UUID against Samsung firmware decompilations (e.g. `com.samsung.android.app.accessoryservice`)
       [ ] Add UUID to `SPEC_UUID_NAMES__SERV_CLASS` or equivalent for automatic resolution via `get_name_from_uuid()`
       - References:
           - Microsoft Q&A #3840559: https://learn.microsoft.com/en-us/answers/questions/3840559/accidentally-deleted-icservice-new-driver-possibly
           - Microsoft Q&A #3284030: https://learn.microsoft.com/en-us/answers/questions/3284030/windows-was-unable-to-install-icservice-new-sms-mm
           - Samsung Accessory SDK: https://developer.samsung.com/galaxy/accessory
           - BlueZ vendor UUID discussion: https://github.com/bluez/bluez/issues/963
   [ ] Catalog other vendor-specific SDP services observed during field testing
       - BT DIAG (UUID 0x1101, Samsung/LG) — diagnostic serial channel, already observed on 14:89:FD:31:8A:7E
       - SPPSERVICE3 (`b4a9d6a0-b2e3-4e40-976d-a69f167ea895`) — Samsung, Bixby-related
       - SPPSERVICE4 / SMEP (`f8620674-a1ed-41ab-a8b9-de9ad655729d`) — Samsung proprietary protocol
       [ ] Add observed vendor UUIDs to `bleep/bt_ref/constants.py` as they are discovered
       [ ] Consider a `vendor_services.py` registry if the list grows beyond ~10 entries

### TODO (arduino):
   [ ] Create function for starting a user interaction interface for a SPECIFIC ADDRESS
   [ ] Clean-up and polish the user interaction interface screens
   [ ] Add to the General Services Information Output:
       [ ] ASCii print out for all Hex Array Values (S/C/D)
       [ ] Handle print out for all S/C/D              <---- Note: This comes from the FOUR HEX of the [serv|char|desc]XXXX tags; BUT DIFFERENT FROM Characteristic Value Handle

### TODO (capabilities)
    [ ] Force Media Players to end ALL PLAYING AUDIO by "... setting position to the maxmium uint32 value."
        - Purpose is to allow bleep to identify MediaPlayer devices and force current media to stop playing

### TODO (rfcomm-security):
    [ ] Add BT_SECURITY socket option support to RFCOMM connections
        - Currently `bleep/ble_ops/classic/connect.py:classic_rfccomm_open()` opens a raw
          RFCOMM socket with no security level set — the kernel applies its own defaults.
        - BlueZ userspace demonstrates the correct pattern in `workDir/bluez/btio/btio.c`:
            - `set_sec_level()` (lines 453–494): sets `SOL_BLUETOOTH` / `BT_SECURITY` on the
              socket before `connect()`; falls back to `SOL_RFCOMM` / `RFCOMM_LM` when the
              kernel returns `ENOPROTOOPT`.
            - `rfcomm_set_lm()` (lines 438–450): maps `BT_SECURITY_LOW` → `RFCOMM_LM_AUTH`,
              `BT_SECURITY_MEDIUM` → `AUTH | ENCRYPT`, `BT_SECURITY_HIGH` → `AUTH | ENCRYPT | SECURE`.
            - `rfcomm_set()` (lines 763–774): applies security + central role before use.
            - `rfcomm_connect()` (lines 746–761): plain `connect()` after security is configured.
        - BlueZ profile defaults from `workDir/bluez/src/profile.c`:
            - `ext_set_defaults()` (line 2174–2180): defaults external profiles to `BT_IO_SEC_MEDIUM`.
            - OPP explicitly sets `BT_IO_SEC_LOW` (lines 2111–2118).
            - OBEX client (`workDir/bluez/obexd/client/bluetooth.c`, lines 104–122) uses `BT_IO_SEC_LOW`.
        - Security constants from `workDir/bluez/lib/bluetooth.h` (lines 52–61):
            - `BT_SECURITY` = 4, levels: SDP=0, LOW=1, MEDIUM=2, HIGH=3, FIPS=4.
        - RFCOMM LM constants from `workDir/bluez/lib/rfcomm.h` (lines 40–46):
            - `RFCOMM_LM` = 0x03, `RFCOMM_LM_AUTH` = 0x0002, `RFCOMM_LM_ENCRYPT` = 0x0004,
              `RFCOMM_LM_SECURE` = 0x0020.
        - Implementation approach:
            [ ] Add optional `sec_level` parameter to `classic_rfccomm_open()` (default: MEDIUM)
            [ ] Before `sock.connect()`, call `sock.setsockopt(SOL_BLUETOOTH, BT_SECURITY, ...)`
                with fallback to `sock.setsockopt(SOL_RFCOMM, RFCOMM_LM, ...)` on ENOPROTOOPT,
                mirroring the btio.c pattern
            [ ] Expose sec_level through CLI flags on classic-connect, debug ckeep/copen
            [ ] Verify Python `socket` module exposes SOL_BLUETOOTH / BT_SECURITY constants
                (may require ctypes or hard-coded values: SOL_BLUETOOTH=274, BT_SECURITY=4)

## MAP CLI Auto-Resolve Intermediate Folders (Future Work)

**Goal**: Enhance `list_messages()` in `bleep/ble_ops/classic/map.py` to detect when the requested folder is an intermediate directory (has subfolders, not messages) and automatically enumerate its subtree to find and list messages from all leaf descendants.

**Context**: The MAP specification allows varied folder hierarchies across devices — some devices use a deep structure (`telecom/msg/{inbox,draft,sent,outbox,deleted}`) while others store messages directly in `telecom/`.  Currently, when a user requests `list_messages("telecom")` on a device with the deep structure, the remote MAS returns OBEX "Bad Request" because `telecom/` is a structural folder, not a message container.  The CLI now provides helpful recovery hints (see Fix 2 in MAP CLI Folder Enumeration Fix below), but does not auto-descend.

**Proposed approach**:
- [ ] In `list_messages()`, catch "Bad Request" from `ListMessages` on the first attempt
- [ ] When caught, call `walk_folder_tree()` from the current position to discover leaf subfolders
- [ ] Re-issue `ListMessages` against each discovered leaf folder, aggregating results
- [ ] Tag each returned message with its actual source folder path for caller disambiguation
- [ ] Preserve existing behavior for leaf folders (no extra round-trips)

**Dependencies**: Requires the recursive `walk_folder_tree()` and `collect_leaf_paths()` utilities already in the operations layer.

**Risk**: Additional OBEX session round-trips on devices with deep hierarchies; should be gated behind the "Bad Request" error path only (zero cost on the happy path).

---

# Resources and Notes:
        - Great way to obfusate use of the D-Bus:
                progname = 'org.freedesktop.NetworkManager'
                objpath  = '/org/freedesktop/NetworkManager'
                intfname = 'org.freedesktop.NetworkManager'
                methname = 'GetDevices'
                
                bus = dbus.SystemBus()
                
                obj = bus.get_object(progname, objpath)
                interface = dbus.Interface(obj, intfname)     # Get the interface to obj
                method = interface.get_dbus_method(methname)  # The method on that interface
                
                method()                                      # And finally calling the method
            - URL:      https://unix.stackexchange.com/questions/203410/how-to-list-all-object-paths-under-a-dbus-service
        - Larger Bluetooth Classic D-Bus information:
            - URL:      https://kernel.googlesource.com/pub/scm/bluetooth/bluez/+/utils-3.2/hcid/dbus-api.txt
        - Understanding D-Bus Signatures
            - URL:      https://dbus.freedesktop.org/doc/dbus-python/tutorial.html
            - URL:      https://dbus.freedesktop.org/doc/dbus-specification.html#type-system
        - Hex Encoding
            - URL:      linuxhint.com/string-to-hexadecimal-in-python/
        - CLI Busctl
            - URL:      www.freedesktop.org/software/systemd/man/busctl.html        <----- Good for understanding how to send raw information to D-Bus via busctl CLI
        - API Documentaiton for Bluez
            - URL:      https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/test/test-adapter           <-------- CENTRAL to getting DBus + Bluez interaction working
            - URL:      https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc
        - DBus Proxy Documentation
            - URL:      https://lazka.github.io/pgi-docs/Gio-2.0/classes/DBusProxy.html#Gio.DBusProxy.signals.g_properties_changed
        - dbus-python Documentation
            - URL:      https://dbus.freedesktop.org/doc/dbus-python/dbus.proxies.html

    Nota Bene:
        - Bluetooth Low Energy GATT Descriptors will ONLY UPDATE AFTER that descriptor has been READ AT LEAST ONCE before

