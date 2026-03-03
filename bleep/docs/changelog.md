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

* **Transport-aware `connect` command**: The `connect` command now auto-detects whether the target is a BR/EDR classic or BLE device and routes to the appropriate connection method. For classic devices, falls back to SDP enumeration + RFCOMM keepalive if profile-level `Connect()` fails.

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