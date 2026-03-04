# Central TODO tracker

This page aggregates open tasks referenced across the project so contributors have a single place to check before starting work.  **Edit directly** whenever you add / complete an item – no special tooling required.

## TODO sources

| Source | Section | Last reviewed |
|--------|---------|---------------|
| Codebase (`bleep/**/*.py`) | Inline `# TODO:` comments | _(grep as needed)_ |
| `bleep/docs/audio_recon.md` | Audio recon future work (Bonus Objectives) | _2026-02-28_ |
| `bleep/docs/adapter_config.md` | Adapter configuration reference | _2026-02-28_ |
| `bleep/ble_ops/amusica.py` | Amusica orchestration (core) | _2026-02-28_ |
| `bleep/modes/amusica.py` | Amusica CLI mode | _2026-02-28_ |
| `bleep/docs/agent_dbus_communication_issue.md` | Agent dispatch fix (debug mode pairing) | _2026-02-28_ |
| `bleep/docs/mainloop_requirement_analysis.md` | GLib main-thread dispatch requirement | _2026-02-28_ |

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
      - [x] Plan created for modular, expandable dual device detection framework (`bleep/docs/DUAL_DEVICE_DETECTION_PLAN.md`)
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
### TODO (arduino):
   [ ] Create function for starting a user interaction interface for a SPECIFIC ADDRESS
   [ ] Clean-up and polish the user interaction interface screens
   [ ] Add to the General Services Information Output:
       [ ] ASCii print out for all Hex Array Values (S/C/D)
       [ ] Handle print out for all S/C/D              <---- Note: This comes from the FOUR HEX of the [serv|char|desc]XXXX tags; BUT DIFFERENT FROM Characteristic Value Handle

### TODO (capabilities)
    [ ] Force Media Players to end ALL PLAYING AUDIO by "... setting position to the maxmium uint32 value."
        - Purpose is to allow bleep to identify MediaPlayer devices and force current media to stop playing

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

