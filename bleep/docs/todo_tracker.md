# Central TODO tracker

This page aggregates open tasks referenced across the project so contributors have a single place to check before starting work.  **Edit directly** whenever you add / complete an item – no special tooling required.

## TODO sources

| Source file | Section | Last reviewed |
|-------------|---------|---------------|
| `README.refactor` | Remaining refactor tasks | _2025-07-14_ |
| `BLEEP.golden-template` | Top-level TODO comments | _2025-07-14_ |
| Codebase (`bleep/**/*.py`) | Inline `# TODO:` comments | _(grep as needed)_ |

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
  * Write migration note in README.refactor - **COMPLETE**:
    - [x] Added v6→v7 migration notes to `README.refactor-migrations.md`
    - [x] Updated `README.refactor` to reference migration documentation
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
- [x] Classic Bluetooth enumeration (README.refactor)
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
    - [x] Create migration guide for schema changes (see `README.refactor-migrations.md` and schema version history in `observation_db_schema.md`)

## Technical Scalability Improvements

- [x] **Database Optimization**
  - [x] Implement indexing strategy for observation database
  - [x] Add query optimization for large device sets
  - [x] Create database maintenance utilities
  - [x] Document database schema and optimization techniques

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

