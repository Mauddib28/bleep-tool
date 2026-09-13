# BLEEP v3.1 — API Specification

**Version**: 0.1.2 (Phase 7 — API Surface Definition; 2026-09-13 v3.1.0 bump)
**Date**: 2026-09-13
**BLEEP Version**: 3.1.0
**Schema Version**: 20

---

## 1  Overview

This document defines the **library-level public API** for the BLEEP
(Bluetooth Landscape Exploration & Enumeration Platform) package.  It is
the primary deliverable of **Phase 7** of the BLEEP v3.0 Expansion Plan
and provides the contract that programmatic callers (MCP server, future
REST wrapper, third-party scripts) rely on.

### 1.1  Scope

The API surface is defined as the union of all symbols exported via
`__all__` in each package and module.  Symbols *not* listed in `__all__`
are considered internal implementation details and may change without
notice.

### 1.2  Conventions

| Convention | Example |
|------------|---------|
| MAC address | `"AA:BB:CC:DD:EE:FF"` — uppercase, colon-separated |
| UUID | `"0000180A-0000-1000-8000-00805F9B34FB"` — uppercase, dashed, 128-bit |
| Result codes | Integer constants `RESULT_OK` (0), `RESULT_ERR` (1), … from `bleep.bt_ref.constants` |
| Exceptions | All exceptions inherit `BLEEPError`; each carries a `.code` matching a `RESULT_ERR_*` constant |
| Output mode | `OutputContext` controls terminal / JSON / quiet routing |

---

## 2  Package Hierarchy

Top-level packages (one line each):

- `analysis/` — Device classification, AoI, SDP analysis, advertisement dissection, identity collapse
- `ble_ops/` — BLE + Classic operations (`audio/`, `classic/`, `common/`, `le/` subpackages)
- `bt_ref/` — Reference data: constants, UUIDs, OUI/USB IDs, SDP attribute IDs, generators
- `callbacks/` — Pluggable callback system (`examples/` subpackage)
- `cli/` — CLI entry point, argument parsing (`parsers/`), dispatch
- `core/` — D-Bus services, errors, logging, output, preflight; `observations/` SQLite database
- `dbus/` — Connection pool, timeout manager
- `dbuslayer/` — BlueZ D-Bus abstractions (adapter, device, GATT, agent, media, …)
- `gatt/` — Reserved GATT namespace package (currently no public symbols)
- `mesh/` — Bluetooth Mesh provisioning
- `modes/` — CLI mode entry points (interactive, survey, debug, classic, media, …)
- `pairing/` — Pairing helpers and agent management
- `protocols/` — Design-only package for raw L2CAP/OBEX (documentation only; no runtime code yet)
- `signals/` — Signal capture, routing, integration

The authoritative package tree below (with per-package module-file counts) is
**auto-generated** — regenerate it with `python bleep/scripts/gen_api_spec.py --write`.

<!-- AUTOGEN:hierarchy START (python bleep/scripts/gen_api_spec.py --write) -->
```
bleep/
├── (3 top-level module files, incl. __init__.py, __main__.py)
├── analysis/  (6 module files)
├── ble_ops/  (2 module files)
    ├── audio/  (10 module files)
    ├── classic/  (14 module files)
    ├── common/  (6 module files)
    └── le/  (11 module files)
├── bt_ref/  (23 module files)
├── callbacks/  (2 module files)
    └── examples/  (3 module files)
├── cli/  (5 module files)
    └── parsers/  (16 module files)
├── core/  (13 module files)
    └── observations/  (12 module files)
├── dbus/  (3 module files)
├── dbuslayer/  (46 module files)
├── gatt/  (1 module file)
├── mesh/  (12 module files)
├── modes/  (63 module files)
├── pairing/  (1 module file)
├── protocols/  (1 module file)
└── signals/  (5 module files)
```
<!-- AUTOGEN:hierarchy END -->

---

## 3  API Surface Catalog

### 3.1  Root Package — `bleep`

| Symbol | Type | Description |
|--------|------|-------------|
| `__version__` | `str` | Semantic version (e.g. `"3.1.0"`) |
| `__author__` | `str` | Package author |

Internal helper `_ensure_bluez_signals()` is available but not part of the
public contract.

---

### 3.2  Analysis — `bleep.analysis`

**14 symbols** re-exported from submodules.

| Symbol | Source Module | Type | Description |
|--------|-------------|------|-------------|
| `AOIAnalyser` | `aoi_analyser` | class | Area-of-Interest analysis engine |
| `analyse_aoi_data` | `aoi_analyser` | function | Run AoI analysis for a device |
| `SDPAnalyzer` | `sdp_analyzer` | class | SDP record analyzer |
| `analyze_sdp_records` | `sdp_analyzer` | function | Analyze SDP records for a device |
| `infer_bluetooth_spec_version` | `sdp_analyzer` | function | Infer BT spec version from SDP |
| `detect_version_anomalies` | `sdp_analyzer` | function | Detect version inconsistencies |
| `DeviceTypeClassifier` | `device_type_classifier` | class | ML-style device classifier |
| `EvidenceType` | `device_type_classifier` | enum | Types of classification evidence |
| `EvidenceWeight` | `device_type_classifier` | enum | Weight tiers for evidence |
| `EvidenceSet` | `device_type_classifier` | dataclass | Collection of typed evidence |
| `ClassificationResult` | `device_type_classifier` | dataclass | Classification outcome |
| `EvidenceCollector` | `device_type_classifier` | class | Collects evidence from device data |
| `HIDInfo` | `device_type_classifier` | dataclass | HID device metadata |
| `classify_hid` | `device_type_classifier` | function | Classify HID device type |

---

### 3.3  BLE Operations — `bleep.ble_ops`

**20 symbols** lazily re-exported.

#### 3.3.1  LE Scanning

| Symbol | Source | Signature / Value | Description |
|--------|--------|-------------------|-------------|
| `passive_scan` | `le.scan` | `(device=None, timeout=60, transport="auto", quiet=False, *, filter_record=False) → dict` | Passive BLE scan (returns a `devices` dict keyed by address) |
| `passive_scan_and_connect` | `le.scan_modes` | `(target_mac, **kwargs) → tuple` | Scan + connect (passive) |
| `naggy_scan_and_connect` | `le.scan_modes` | `(target_mac, **kwargs) → tuple` | Scan + connect (naggy: multi-read) |
| `pokey_scan_and_connect` | `le.scan_modes` | `(target_mac, **kwargs) → tuple` | Scan + connect (pokey: probing) |
| `bruteforce_scan_and_connect` | `le.scan_modes` | `(target_mac, **kwargs) → tuple` | Scan + connect (brute-force write) |
| `scan_and_connect` | `le.scan_modes` | `(mode, target_mac, **kwargs) → tuple` | Dispatcher for all scan modes |
| `PASSIVE_MODE` | `le.scan_modes` | `str` = `"ble_passive"` | Mode constant |
| `NAGGY_MODE` | `le.scan_modes` | `str` = `"ble_naggy"` | Mode constant |
| `POKEY_MODE` | `le.scan_modes` | `str` = `"ble_pokey"` | Mode constant |
| `BRUTEFORCE_MODE` | `le.scan_modes` | `str` = `"ble_bruteforce"` | Mode constant |

#### 3.3.2  LE Connection & Enumeration

| Symbol | Source | Signature | Description |
|--------|--------|-----------|-------------|
| `connect_and_enumerate__bluetooth__low_energy` | `le.connect` | `(target_mac) → tuple[device, mapping, landmine_map, permission_map]` | Connect to BLE device and enumerate GATT. Returns the device object, the service→characteristic `mapping` dict, and the landmine / permission maps. |

#### 3.3.3  Classic (BR/EDR)

| Symbol | Source | Signature | Description |
|--------|--------|-----------|-------------|
| `discover_services_sdp` | `classic.sdp` | `(mac, timeout=30, connectionless=False, l2ping_count=3, l2ping_timeout=13, source="auto") → list[dict]` | SDP service discovery. `source` selects the discovery path (`auto`/`dbus`/`browse`/`xml`/`records`) or unions all (`merge`/`all`), tagging each record's `source` and flagging cross-source disagreements. Records carry a lossless `attribute_labels` map (universal SDP attribute IDs → names). |
| `discover_services_sdp_connectionless` | `classic.sdp` | `(mac) → list[dict]` | SDP discovery (connectionless) |
| `connect_and_enumerate__bluetooth__classic` | `classic.connect` | `(mac, **kwargs) → Tuple[ClassicDevice, Dict[str, int]]` | Connect to Classic device; returns `(device, service_map)` |
| `query_hci_version` | `classic.version` | `(adapter="hci0") → Optional[dict]` | Query the **local** adapter's HCI/LMP version |
| `query_remote_version` | `classic.version` | `(address, adapter="hci0") → Optional[dict]` | Query a **remote** device's LMP version |
| `map_lmp_version_to_spec` | `classic.version` | `(lmp_version: int) → str` | Map LMP version to BT spec. Primary source is the SIG-generated `SPEC_ID_NAMES__CORE_VERSION` (via `resolve_core_version`), so it returns the full canonical name (e.g. `"Bluetooth® Core Specification 5.2"`); falls back to a static map only for versions absent from the SIG table. |
| `map_profile_version_to_spec` | `classic.version` | `(profile_version: int) → str` | Map profile version to spec |
| `resolve_manufacturer_name` | `classic.version` | `(manufacturer_id: Optional[int]) → Optional[str]` | Resolve BT SIG company ID to name |
| `infer_min_bt_version_from_le_features` | `classic.version` | `(features_bytes: bytes) → Optional[str]` | Infer minimum BT spec from LE feature bits |

> **Note:** `resolve_oui()` and `format_uuid_display()` are **not** re-exported at
> the `bleep.ble_ops` package level (not in `ble_ops/__init__.py`'s `__all__`).
> They live in `bleep.ble_ops.common.conversion` — import them from there (see
> §3.4.4). `resolve_oui(mac)` resolves a MAC's 24-bit IEEE MA-L OUI to its
> registered vendor (cached, never raises, `None` for unknown/random/short);
> `format_uuid_display(uuid)` normalizes a UUID for report display (never raises).

---

### 3.4  BLE Operations — Subpackages (Leaf Imports)

These modules export symbols via `__all__` but are **not** re-exported at
the `bleep.ble_ops` package level.  Use the full module path.

#### 3.4.1  Audio — `bleep.ble_ops.audio`

| Module | Symbols | Key Functions |
|--------|---------|---------------|
| `amusica` | 3 | `scan_audio_targets()`, `attempt_justworks_connect()`, `assess_targets()` |
| `amusica_orchestrator` | 3 | `run_amusica_full_auto()`, `RecordingResult`, `AutoResult` |
| `audio_codec` | 3 | `AudioCodecEncoder`, `AudioCodecDecoder`, `get_codec_name()` |
| `audio_profile_correlator` | 1 | `AudioProfileCorrelator` |
| `audio_recon` | 1 | `run_audio_recon()` |
| `audio_system` | 3 | `system_play()`, `system_record()`, `system_record_hfp()` |
| `audio_tools` | 3 | `AudioToolsHelper`, `get_audio_backend()`, `check_audio_file_has_content()` |
| `audio_transcribe` | 3 | `AudioInterceptResult`, `run_audio_intercept()`, `transcribe_file()` |

#### 3.4.2  LE — `bleep.ble_ops.le`

| Module | Symbols | Key Exports |
|--------|---------|-------------|
| `brute` | 2 | `brute_read_all()`, `brute_write_all()` |
| `ctf` | 8 | `ble_ctf__scan_and_enumeration()`, `ble_ctf__read_characteristic()`, `ble_ctf__write_flag()`, … |
| `enum_controller` | 4 | `EnumerationController`, `EnumerationResult`, `ConnectionAnnotation`, `ErrorAction` |
| `enum_helpers` | 5 | `multi_read_characteristic()`, `multi_read_all()`, `small_write_probe()`, `build_payload_iterator()`, `brute_write_range()` |
| `reconnect` | 2 | `ReconnectionMonitor`, `reconnect_check()` |
| `scan` | 6 | `passive_scan()`, `naggy_scan()`, `pokey_scan()`, `brute_scan()`, `create_and_return__bluetooth_scan__discovered_devices()`, `…__specific_adapter()` |
| `scan_modes` | 4 | `passive_scan_and_connect()`, `naggy_scan_and_connect()`, `pokey_scan_and_connect()`, `bruteforce_scan_and_connect()` |

#### 3.4.3  Classic — `bleep.ble_ops.classic`

| Module | Symbols | Key Exports |
|--------|---------|-------------|
| `connect` | 2 | `classic_rfccomm_open()`, `connect_and_enumerate__bluetooth__classic()` |
| `pbap` | 1 | `dump_phonebook_pbap()` |
| `ping` | 1 | `classic_l2ping()` |
| `sdp` | 5 | `build_svc_map()`, `discover_service_channel()`, `discover_services_sdp()`, `discover_services_sdp_connectionless()`, `format_protocol_descriptors()` |
| `version` | 6 | `query_hci_version()`, `query_remote_version()`, `map_lmp_version_to_spec()`, `map_profile_version_to_spec()`, `resolve_manufacturer_name()`, `infer_min_bt_version_from_le_features()` |

#### 3.4.4  Common — `bleep.ble_ops.common`

| Module | Symbols | Key Exports |
|--------|---------|-------------|
| `conversion` | 11 | `convert__hex_to_ascii()`, `convert__dbus_to_hex()`, `decode_class_of_device()`, `decode_appearance()`, `decode_pnp_id()`, `format_device_class()`, … |
| `structural` | 3 | `create_and_return__gatt__service_json()`, `…__characteristic_json()`, `…__descriptor_json()` |

---

### 3.5  Reference Data — `bleep.bt_ref`

| Symbol | Source | Type | Description |
|--------|--------|------|-------------|
| `constants` | module | module | All BT constants, result codes, UUIDs, `SERVICE_DATA_PROTOCOL_LABELS` |
| `exceptions` | module | module | Legacy exception aliases |
| `utils` | module | module | Utility functions |
| `uuids` | module | module | UUID-to-name lookup tables + `SPEC_ID_NAMES__CORE_VERSION` (LMP→core-spec names) |
| `uuid_translator` | module | module | Short↔long UUID normalization & translation (see 3.5.2) |
| `sdp_attr_ids` | module | module | `SDP_UNIVERSAL_ATTR_IDS` + `resolve_sdp_attr_id(attr_id, service_class_uuid=None)` — universal SDP attribute-ID labels (BlueZ `lib/sdp.h`), with profile-scoped resolution for `>= 0x0200` when a service class is supplied |
| `sdp_profile_attr_ids` | module | module | SIG `service_discovery` tables: `SDP_PROFILE_ATTR_IDS` (per-profile attribute-ID labels) + `SERVICE_CLASS_TO_PROFILE` reverse map (consumed by `resolve_sdp_attr_id`); `SDP_STRING_ATTR_OFFSETS` (language-base string offsets for attr 0x0006) and `SDP_PROTOCOL_PARAMETERS` (positional PDL parameter names for attr 0x0004), both consumed by `ble_ops/classic/sdp.py` |
| `observed_seed` | module | module | `OBSERVED_UUID_SEED` — curated non-SIG UUIDs (Nordic UART, Google Fast Pair, …) + `get_seed_names()`; unioned into `db uuids --seed` (reference only, not consumed by the classifier) |
| `cod` | module | module | Generated Class-of-Device lookup tables (major/minor/service classes) |
| `mesh_ids` | module | module | Generated Bluetooth Mesh model UUIDs / beacon types |
| `usb_ids` | module | module | Generated USB-IF vendor/product IDs (PnP ID resolution) |
| `custom_uuids` | module | module | User-promoted UUID→name overlay (JSON, merged into `UUID_NAMES` at import) |
| `vendor_adv_specs` | module | module | Generated vendor/community advertisement specs |

#### 3.5.1  `bleep.bt_ref.utils` — 8 symbols

| Function | Signature | Description |
|----------|-----------|-------------|
| `byteArrayToHexString` | `(data: bytes) → str` | Convert byte array to hex string |
| `dbus_to_python` | `(value) → Any` | Convert D-Bus types to Python natives |
| `device_address_to_path` | `(address: str) → str` | MAC to D-Bus object path |
| `get_name_from_uuid` | `(uuid: str) → str` | Exact-match UUID name lookup (no short↔long normalization; returns `"Unknown"` on miss). For short-form/mixed-case input prefer `uuid_translator.get_uuid_name`. |
| `text_to_ascii_array` | `(text: str) → list[int]` | Text to ASCII byte array |
| `print_properties` | `(properties: dict) → None` | Pretty-print D-Bus properties |
| `handle_int_to_hex` | `(value: int) → str` | Integer to hex string |
| `handle_hex_to_int` | `(value: str) → int` | Hex string to integer |

#### 3.5.2  `bleep.bt_ref.uuid_translator` — UUID normalization & translation

Short↔long UUID resolution engine. Normalizes 16/32/128-bit input (dashed or
not, any case), expands short forms to the BT SIG base, and searches all name
databases. Preferred over exact-match `utils.get_name_from_uuid` wherever
short-form or mixed-case UUIDs may occur (e.g. `sdptool`-derived SDP records).

| Function | Signature | Description |
|----------|-----------|-------------|
| `translate_uuid` | `(uuid_input: str, include_unknown: bool = False) → dict` | Full translation: normalized form, detected format, short form, and all category matches. |
| `get_uuid_name` | `(uuid_input: str, default: str = "") → str` | Display convenience over `translate_uuid`; returns best match name or `default`. Used by `classic-enum` / debug `csdp`/`cservices`. |
| `get_translator` | `() → UUIDTranslator` | Singleton translator (register custom `UUIDFormatHandler`s). |

#### 3.5.3  Reference-data generators (`update_*`) & `refresh-refs`

The committed lookup tables above are **generated, self-contained, and offline-safe**:
each generator is network-best-effort with a committed-cache fallback, and a failed
fetch never zeroes an existing table. The CLI `bleep refresh-refs` command
(`bleep.modes.refresh_refs`) drives all the generators below; each can also be run
directly via its `regenerate()`. Scopes: bare `refresh-refs` runs everything;
`--sig-only` / `--vendor-only` / `--oui-only` / `--usb-only` (mutually exclusive)
restrict the run to one group.

| Generator module | Emits | Upstream source | In `refresh-refs`? |
|------------------|-------|-----------------|--------------------|
| `update_ble_uuids` | `uuids.py` (incl. `SPEC_ID_NAMES__CORE_VERSION`) | BT SIG `assigned_numbers` YAML | ✅ (SIG group) |
| `update_extra_refs` | `cod.py`, `mesh_ids.py` | BT SIG `class_of_device.yaml`, mesh YAMLs | ✅ (SIG group) |
| `update_bluez_refs` | `sdp_attr_ids.py` | BlueZ `lib/sdp.h` (pinned commit; committed `bluez_cache/sdp.h`) | ✅ (SIG group) |
| `update_sig_sdp_attr_ids` | `sdp_profile_attr_ids.py` | BT SIG `service_discovery/attribute_ids/*.yaml` | ✅ (SIG group) |
| `update_vendor_specs` | `vendor_adv_specs.py` | Public device-library manifests (or `--local-path`) | ✅ (vendor group) |
| `update_oui` | `oui.py` | IEEE MA-L `oui.csv` (fallback Wireshark `manuf`) | ✅ (`--oui-only`) |
| `update_usb_ids` | `usb_ids.py` | USB-IF `usb.ids` | ✅ (`--usb-only`) |

---

### 3.6  Callbacks — `bleep.callbacks`

**4 symbols**.

| Symbol | Type | Description |
|--------|------|-------------|
| `BleepCallback` | class | Base callback interface |
| `DEFAULT_CALLBACK_DIR` | `str` | Default directory for callback plugins |
| `load_callbacks` | function | Load all callbacks from a directory |
| `get_loaded` | function | Get currently loaded callbacks |

---

### 3.7  CLI — `bleep.cli`

**2 symbols** (the CLI entry point; not typically used as a library API).

| Symbol | Type | Description |
|--------|------|-------------|
| `main` | function | CLI entry point |
| `parse_args` | function | Parse command-line arguments |

---

### 3.8  Core — `bleep.core`

**6 symbols** re-exported at package level.

| Symbol | Type | Description |
|--------|------|-------------|
| `system_dbus__device_management_service` | class | D-Bus device management |
| `system_dbus__scanner_service` | class | D-Bus scanning service |
| `system_dbus__error_handling_service` | class | D-Bus error handling |
| `BleepError` | exception | Base exception (alias for `BLEEPError`) |
| `DeviceNotFoundError` | exception | Device not found |
| `ConnectionError` | exception | Connection failure |

---

### 3.9  Errors — `bleep.core.errors`

**24 symbols**. All exceptions inherit from `BLEEPError` which carries a
`.code` attribute mapping to `RESULT_ERR_*` constants.

| Exception | `.code` Constant | Trigger |
|-----------|-----------------|---------|
| `BLEEPError` | `RESULT_ERR` (1) | Base — generic failure |
| `BleepError` | — | Alias for `BLEEPError` |
| `DeviceNotFoundError` | `RESULT_ERR_NOT_FOUND` (9) | MAC not discoverable |
| `ConnectionError` | `RESULT_ERR_NOT_CONNECTED` (2) | Connection failed |
| `ServiceNotFoundError` | `RESULT_ERR_UNKNOWN_SERVCE` (17) | UUID not on device |
| `ServicesNotResolvedError` | `RESULT_ERR_SERVICES_NOT_RESOLVED` (4) | GATT not resolved |
| `OperationInProgressError` | `RESULT_ERR_ACTION_IN_PROGRESS` (16) | Concurrent op conflict |
| `PermissionError` | `RESULT_ERR_ACCESS_DENIED` (6) | Not permitted |
| `NotSupportedError` | `RESULT_ERR_NOT_SUPPORTED` (3) | Op not supported |
| `TimeoutError` | `RESULT_ERR_NO_REPLY` (14) | D-Bus / BT timeout |
| `InvalidArgumentError` | `RESULT_ERR_BAD_ARGS` (8) | Bad arguments |
| `NotReadyError` | `RESULT_ERR_WRONG_STATE` (5) | Adapter not powered |
| `NotReady` | — | Alias for `NotReadyError` |
| `NotAuthorizedError` | `RESULT_ERR_ACCESS_DENIED` (6) | Authorization required |
| `ProfileUnavailableError` | `RESULT_ERR_PROFILE_UNAVAILABLE` (28) | No connectable profile |
| `AlreadyConnectedError` | `RESULT_ERR_ALREADY_CONNECTED` (32) | Already connected |
| `PageTimeoutError` | `RESULT_ERR_PAGE_TIMEOUT` (29) | BR/EDR page timeout |
| `ConnectionRefusedError` | `RESULT_ERR_CONNECTION_REFUSED` (30) | Remote refused |
| `ConnectionLimitError` | `RESULT_ERR_CONNECTION_LIMIT` (31) | Adapter limit |
| `AuthenticationCanceledError` | `RESULT_ERR_AUTH_CANCELED` (33) | Pairing canceled |
| `AuthenticationRejectedError` | `RESULT_ERR_AUTH_REJECTED` (34) | Pairing rejected |
| `AuthenticationTimeoutError` | `RESULT_ERR_AUTH_TIMEOUT` (35) | Pairing timeout |
| `map_dbus_error` | — | `(DBusException) → BLEEPError` |
| `handle_dbus_exception` | — | Map + log + raise |

#### 3.9.1  Stable Error Identifiers

For programmatic callers (MCP server, REST wrappers) that need stable
string identifiers rather than integer codes:

| Identifier | Code | Exception |
|------------|------|-----------|
| `ERR_GENERIC` | 1 | `BLEEPError` |
| `ERR_NOT_CONNECTED` | 2 | `ConnectionError` |
| `ERR_NOT_SUPPORTED` | 3 | `NotSupportedError` |
| `ERR_SERVICES_NOT_RESOLVED` | 4 | `ServicesNotResolvedError` |
| `ERR_WRONG_STATE` | 5 | `NotReadyError` |
| `ERR_ACCESS_DENIED` | 6 | `PermissionError`, `NotAuthorizedError` |
| `ERR_BAD_ARGS` | 8 | `InvalidArgumentError` |
| `ERR_NOT_FOUND` | 9 | `DeviceNotFoundError` |
| `ERR_NO_DEVICES_FOUND` | 11 | — (constant only) |
| `ERR_NO_BR_CONNECT` | 12 | — (constant only) |
| `ERR_READ_NOT_PERMITTED` | 13 | — (constant only) |
| `ERR_NO_REPLY` | 14 | `TimeoutError` |
| `ERR_DEVICE_FORGOTTEN` | 15 | — (constant only) |
| `ERR_ACTION_IN_PROGRESS` | 16 | `OperationInProgressError` |
| `ERR_UNKNOWN_SERVICE` | 17 | `ServiceNotFoundError` |
| `ERR_UNKNOWN_OBJECT` | 18 | — (constant only) |
| `ERR_REMOTE_DISCONNECT` | 19 | — (constant only) |
| `ERR_UNKNOWN_CONNECT_FAILURE` | 20 | — (constant only) |
| `ERR_METHOD_CALL_FAIL` | 21 | — (constant only) |
| `ERR_NOT_PERMITTED` | 22 | — (constant only) |
| `ERR_NOT_AUTHORIZED` | 23 | — (constant only) |
| `ERR_WRITE_NOT_PERMITTED` | 24 | — (constant only) |
| `ERR_NOTIFY_NOT_PERMITTED` | 25 | — (constant only) |
| `ERR_INDICATE_NOT_PERMITTED` | 26 | — (constant only) |
| `ERR_TIMEOUT` | 27 | — (constant only) |
| `ERR_PROFILE_UNAVAILABLE` | 28 | `ProfileUnavailableError` |
| `ERR_PAGE_TIMEOUT` | 29 | `PageTimeoutError` |
| `ERR_CONNECTION_REFUSED` | 30 | `ConnectionRefusedError` |
| `ERR_CONNECTION_LIMIT` | 31 | `ConnectionLimitError` |
| `ERR_ALREADY_CONNECTED` | 32 | `AlreadyConnectedError` |
| `ERR_AUTH_CANCELED` | 33 | `AuthenticationCanceledError` |
| `ERR_AUTH_REJECTED` | 34 | `AuthenticationRejectedError` |
| `ERR_AUTH_TIMEOUT` | 35 | `AuthenticationTimeoutError` |
| `ERR_CONNECTION_ABORTED_REMOTE` | 36 | — (constant only) |
| `ERR_CONNECTION_ABORTED_LOCAL` | 37 | — (constant only) |
| `ERR_PROTOCOL_ERROR` | 38 | — (constant only) |
| `ERR_SOCKET_ERROR` | 39 | — (constant only) |
| `ERR_NOT_POWERED` | 40 | — (constant only) |

---

### 3.10  Output — `bleep.core.output`

**3 symbols**.

| Symbol | Type | Description |
|--------|------|-------------|
| `OutputMode` | `Literal["terminal", "json", "quiet"]` | Output mode type alias |
| `OutputContext` | dataclass | Controls mode output routing |
| `output_from_args` | function | `(argparse.Namespace) → OutputContext` |

**`OutputContext` fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `mode` | `OutputMode` | `"terminal"` | Output mode |
| `stream` | `IO[str]` | `sys.stdout` | Structured data destination |
| `progress` | `IO[str]` | `sys.stderr` | Progress message destination |

**`OutputContext` methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `emit_result` | `(data: Any) → None` | Write JSON line in json/quiet modes; no-op in terminal |
| `emit_progress` | `(msg: str) → None` | Write to progress stream unless quiet |
| `close` | `() → None` | Close stream if file-backed |

**Properties:** `is_terminal`, `is_json`, `is_quiet` — boolean mode checks.

---

### 3.11  Preflight — `bleep.core.preflight`

**15 symbols**.

| Symbol | Type | Description |
|--------|------|-------------|
| `DeviceState` | dataclass | Connection/pairing/trust snapshot |
| `PreflightReport` | dataclass | Full preflight check result |
| `BtmgmtStatus` | dataclass | Privilege-aware `btmgmt` availability/runnability status |
| `EndpointOwner` | dataclass | D-Bus endpoint ownership info |
| `EndpointContentionReport` | dataclass | Endpoint contention analysis |
| `PanPrereqReport` | dataclass | PAN (BNEP) host prerequisite check result |
| `check_device_state` | function | `(mac, transport="auto") → DeviceState` |
| `check_btmgmt` | function | `(adapter_index=0) → BtmgmtStatus`; privilege-aware probe that never hangs |
| `run_btmgmt` | function | `(args, *, timeout=3.0) → Optional[CompletedProcess]`; non-interactive `btmgmt` invocation |
| `check_endpoint_contention` | function | `() → EndpointContentionReport` |
| `check_pan_prerequisites` | function | `(role="nap", *, server=False) → PanPrereqReport` |
| `print_pan_prereq_summary` | function | Pretty-print PAN prerequisite summary |
| `print_preflight_summary` | function | Pretty-print preflight results |
| `require_adapter` | function | Assert adapter is available and powered |
| `run_preflight_checks` | function | Full environment check |

---

### 3.12  Observation Database — `bleep.core.observations`

**43 symbols** (per `__all__`).

#### Write Operations

| Function | Signature | Description |
|----------|-----------|-------------|
| `upsert_device` | `(mac, **cols) → None` | Insert or update device record. `seen_by` (schema v19) is union-merged across upserts; `enumerated_by` is last-writer-wins; `enumerated_at` (schema v20) is the last successful GATT time. Survey / `enum-scan` / AoI supply both only after a successful GATT enumeration. |
| `get_enumeration_stamp` | `(mac) → (enumerated_by, enumerated_at)` | Lightweight read of the last successful GATT adapter and timestamp. |
| `insert_adv` | `(mac, rssi, data, decoded, adapter=None) → None` | Insert advertisement observation. Consecutive-identical `(data, decoded)` samples coalesce **per adapter**; the same payload on a different antenna is a new row (schema v19). |
| `upsert_services` | `(mac, services_dict) → dict` | Insert/update GATT services |
| `upsert_characteristics` | `(mac, service_uuid, chars_dict) → None` | Insert/update characteristics |
| `upsert_descriptors` | `(mac, service_uuid, char_uuid, descs_dict) → None` | Insert/update descriptors |
| `upsert_classic_services` | `(mac, sdp_records) → None` | Insert Classic SDP records |
| `upsert_sdp_record` | `(mac, record) → None` | Append-only SDP snapshot (schema v16): appends a new timestamped row only when the record content changed vs the latest snapshot for the same `mac + uuid + channel`; never overwrites/deletes. Persists the record's `source` provenance (schema v18) but excludes it from change-detection so a same-content re-observation from a different source never adds a spurious row. |
| `upsert_pan_access` | `(mac, pan_data) → None` | PAN access data |
| `upsert_pbap_metadata` | `(mac, pbap_data) → None` | PBAP metadata |
| `insert_char_history` | `(mac, char_uuid, value, …) → None` | Characteristic value timeline |
| `snapshot_media_player` | `(mac, player_data) → None` | Media player state snapshot |
| `snapshot_media_transport` | `(mac, transport_data) → None` | Media transport snapshot |
| `store_signal_capture` | `(mac, signal_data) → None` | Signal capture data |
| `store_aoi_analysis` | `(mac, analysis_data) → None` | AoI analysis results (upserts latest `aoi_analysis` row **and** appends to `aoi_analysis_history`, schema v17) |
| `store_device_type_evidence` | `(mac, evidence) → None` | Classification evidence |
| `store_security_maps` | `(mac, maps, source="…") → None` | Security maps |
| `store_pairing_event` | `(mac, event_data) → None` | Pairing event record |
| `store_media_enumeration` | `(mac, enum_data) → None` | Media enumeration data |
| `store_audio_recon` | `(mac, recon_data) → None` | Audio recon results |

#### Read Operations

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_devices` | `(status=None, limit=100, offset=0, name=None, since=None, until=None, seen_basis="last") → list[dict]` | List observed devices; optional `status` (comma-separated: recent/ble/classic/dual/unknown/media) and `name` (case-insensitive substring) filters, with `limit`/`offset` pagination. `since`/`until` are naive-UTC ISO bounds (`until` exclusive) filtered against `seen_basis` = `"first"` (first_seen), `"last"` (last_seen, default), or `"any"` (overlap: `first_seen < until AND last_seen >= since`). |
| `get_device_detail` | `(mac) → dict` | Full device detail (`{device, services, characteristics, …}`) |
| `get_characteristic_timeline` | `(mac, char_uuid) → list[dict]` | Char value history |
| `get_sdp_timeline` | `(mac, uuid=None, limit=None) → list[dict]` | Classic SDP record change history from the append-only `sdp_records` table, ordered `(uuid, channel, ts, id)`; optional `uuid` scopes one service class. Backs `db timeline --sdp`. |
| `export_device_data` | `(mac, char_limit=500, adv_limit=100) → dict` | Export full device record (device, services, characteristics, sdp, adv, history) as a JSON-ready dict. `char_limit`/`adv_limit` cap the `characteristic_history`/`adv_reports` slices; pass `0` for either to return the **unbounded** set (DB-5). |
| `get_sdp_inventory` | `(macs) → list[dict]` | Batched SDP rollup for `db report --recon` (DB-9): distinct `(name, uuid)` service items across `macs` with `device_count`/`record_count`, sorted by prevalence. Single `WHERE mac IN (…)` query. |
| `get_characteristic_values` | `(macs) → list[dict]` | Batched latest characteristic value per `(mac, char_uuid)` across `macs` as `{mac, service_uuid, char_uuid, value_hex}` (DB-9); backs `db report --recon-detail`. |
| `get_aoi_analysis` | `(mac) → dict\|None` | Retrieve latest AoI analysis |
| `get_aoi_analysis_history` | `(mac, limit=None) → list[dict]` | Retrieve AoI analysis history, newest-first (schema v17) |
| `has_aoi_analysis` | `(mac) → bool` | Check if AoI exists |
| `get_aoi_analyzed_devices` | `() → list[str]` | MACs with AoI analysis |
| `get_device_type_evidence` | `(mac) → list[dict]` | Retrieve classification evidence |
| `get_device_evidence_signature` | `(mac) → dict\|None` | Evidence signature |
| `get_security_maps` | `(mac) → list[dict]` | Retrieve security maps |
| `get_pairing_events` | `(mac) → list[dict]` | Retrieve pairing events |
| `get_media_enumerations` | `(mac) → list[dict]` | Retrieve media enumerations |
| `get_audio_recon` | `(mac) → list[dict]` | Retrieve audio recon data |
| `get_observed_uuid_catalogue` | `(limit=None, uuid=None, max_sample_macs=…, include_seed=False) → list[dict]` | Observed-UUID catalogue ("seen in the wild"): distinct UUIDs aggregated across services/characteristics/descriptors/classic_services/sdp_records with name, count, sources, first/last-seen, and sample MACs (UUIDs canonicalized to 128-bit for grouping). `include_seed=True` unions the curated non-SIG seed (`bt_ref/observed_seed.py`) as count-0 reference rows tagged `source="curated_seed"`. Backs `db uuids` / `db uuids --seed`. |
| `get_observed_uuid_names` | `(uuid) → list[str]` | Names observed for a single UUID (any stored form); used by the classifier's default WEAK observed-catalogue feed. |
| `get_observed_uuid_evidence` | `(uuid) → dict` | Source-aware measurement report for one UUID: `{le_measured, classic_measured, le_names, classic_names}` from the LE (services/characteristics/descriptors) vs Classic (classic_services/sdp_records) tables. Backs the classifier's **opt-in** STRONG promotion path. |

#### Maintenance

| Function | Signature | Description |
|----------|-----------|-------------|
| `maintain_database` | `(vacuum=True, analyze=True) → dict` | Run VACUUM, integrity check, stats |
| `explain_query` | `(sql: str) → str` | EXPLAIN QUERY PLAN output |

---

### 3.13  D-Bus Layer — `bleep.dbuslayer`

**19 symbols** (mix of eager and lazy imports).

| Symbol | Type | Description |
|--------|------|-------------|
| `system_dbus__bluez_adapter` | class | Adapter D-Bus interface |
| `system_dbus__bluez_device__low_energy` | class | LE device interface (lazy) |
| `system_dbus__bluez_device__classic` | class | Classic device interface (lazy) |
| `system_dbus__bluez_signals` | class | BlueZ signal monitor |
| `system_dbus__bluez_generic_agent` | class | Generic pairing agent |
| `system_dbus__bluez_agent_user_interface` | class | Agent user interface |
| `Characteristic` | class | GATT characteristic wrapper |
| `Descriptor` | class | GATT descriptor wrapper |
| `le_advertising` | module | LE advertising (lazy) |
| `adv_monitor` | module | Advertisement monitoring (lazy) |
| `gatt_server` | module | GATT server hosting (lazy) |
| `device_set` | module | Device sets (lazy) |
| `battery_provider` | module | Battery service provider (lazy) |
| `media_assistant` | module | Media assistant (lazy) |
| `bluez_monitor` | module | BlueZ D-Bus monitoring (lazy) |
| `recovery` | module | Connection recovery (lazy) |
| `agent_io` | module | Agent I/O handlers (lazy) |
| `pairing_state` | module | Pairing state machine (lazy) |
| `bond_storage` | module | Bond/key storage (lazy) |

#### 3.13.1  Adapter — `bleep.dbuslayer.adapter`

**Key methods of `system_dbus__bluez_adapter`:**

| Method | Signature | MainLoop? | Description |
|--------|-----------|-----------|-------------|
| `run_scan` | `() → bool` | No | Start discovery (no blocking) |
| `run_scan__timed` | `(duration=None) → bool` | **Yes** | Timed scan with MainLoop block |
| `set_discovery_filter` | `(filter_dict) → bool` | No | Set scan filter |
| `get_managed_objects` | `() → dict\|None` | No | All BlueZ managed objects |
| `get_discovered_devices` | `() → list` | No | Parsed discovered devices |
| `power_cycle` | `(off_delay=0.5) → bool` | No | Power off → on |
| `is_ready` | `() → bool` | No | Adapter exists and powered |
| `get_connected_devices` | `() → list` | No | Connected MAC list |
| `list_adapters` | `() → list` | No | Static: all adapters |
| `get_adapter_info` | `() → dict` | No | Full adapter properties |

**Property getters:** `get_alias()`, `get_name()`, `get_address()`, `get_address_type()`,
`get_class()`, `get_powered()`, `get_discoverable()`, `get_pairable()`, `get_connectable()`,
`get_discoverable_timeout()`, `get_pairable_timeout()`, `get_discovering()`, `get_uuids()`,
`get_modalias()`, `get_roles()` — all return `Optional[T]`.

**Property setters (D-Bus):** `set_alias()`, `set_powered()`, `set_discoverable()`,
`set_pairable()`, `set_connectable()`, `set_discoverable_timeout()`,
`set_pairable_timeout()` — all return `bool`.

**Management (root required):** `set_class()`, `set_local_name()`, `set_ssp()`,
`set_secure_connections()`, `set_le()`, `set_bredr()`, `set_privacy()`,
`set_fast_connectable()`, `set_link_security()`, `set_wideband_speech()`.

---

### 3.14  Signals — `bleep.signals`

**19 symbols**.

| Category | Symbols |
|----------|---------|
| Config classes | `SignalCaptureConfig`, `SignalFilter`, `SignalRoute`, `SignalAction`, `SignalType`, `ActionType` |
| Config functions | `load_config()`, `save_config()`, `create_default_config()`, `list_configs()` |
| Router classes | `SignalRouter`, `ActionExecutor` |
| Router functions | `get_router()`, `set_router()`, `process_signal()`, `process_signal_capture()`, `register_callback()` |
| Integration | `integrate_with_bluez_signals()`, `patch_signal_capture_class()` |

---

### 3.15  Pairing — `bleep.pairing`

**7 symbols**.

| Symbol | Type | Description |
|--------|------|-------------|
| `find_device_path` | function | Resolve MAC to D-Bus object path |
| `resolve_device_for_pair` | function | Find and prepare device for pairing |
| `check_pair_status` | function | Check current pairing state |
| `report_pair_status` | function | Print pairing status summary |
| `remove_stale_bond` | function | Remove stale bond records |
| `register_pair_agent` | function | Register pairing agent |
| `classic_connect_sdp_rfcomm` | function | Classic connect via SDP/RFCOMM |

---

### 3.16  Mesh — `bleep.mesh`

**11 symbols** (module-level re-exports of subpackage modules).

| Symbol | Type |
|--------|------|
| `constants` | module |
| `errors` | module |
| `proxy` | module |
| `network` | module |
| `node` | module |
| `management` | module |
| `application` | module |
| `element` | module |
| `provisioner` | module |
| `provision_agent` | module |
| `interactive_provision_agent` | module |

---

### 3.17  Mode Entry Points — `bleep.modes`

**13 mode modules** are lazily re-exported from `modes/__init__.py`'s `__all__`
(listed below).  Each provides a `run()` or `main()` entry point.  These are
CLI-facing and not typically called as library API.

> **Note:** the `bleep.modes` package ships **63 module files** in total (see the
> §7 census). Most are reached through CLI dispatch (`bleep/cli/dispatch.py`) or
> the debug shell rather than the package-level `__all__` — e.g. `survey*`,
> `classic_*`, `media`, `audio`, `beacon_identification`, `advertise`, `monitor`,
> `db`, `pair`, `user`, `gatt_enum`, `enum_scan`, and the many `debug_*` helpers.
> The 13 below are only the lazily re-exported entry points.

| Module | Entry Point | Description |
|--------|-------------|-------------|
| `interactive` | `main()` | Interactive debug mode (REPL) |
| `scan` | `main()` | Scan-only mode |
| `agent` | `run()` / `main()` | Pairing agent mode |
| `exploration` | `run()` / `main()` | Device exploration |
| `analysis` | `main()` | Analysis mode |
| `aoi` | `run()` / `main()` | Area of Interest mode |
| `signal` | `run()` / `main()` | Signal capture mode |
| `blectf` | `run()` / `main()` | BLE CTF challenge mode |
| `debug` | `main()` | Debug utilities |
| `test` | `main()` | Test mode |
| `picow` | — | Pico W interaction |
| `scratch` | — | Scratch/experimental |
| `amusica` | `main()` | Audio recon mode |

---

## 4  Concurrency Constraints

### 4.1  GLib.MainLoop Requirement

The BLEEP platform interfaces with BlueZ over D-Bus using `dbus-python`.
Certain operations require `GLib.MainLoop` to be running on the **main
thread** to dispatch incoming D-Bus method calls:

| Category | Requires MainLoop on Main Thread | Notes |
|----------|----------------------------------|-------|
| **Pairing agent callbacks** | **Yes** | `RequestPinCode`, `RequestPasskey`, `DisplayPinCode`, `DisplayPasskey`, `RequestConfirmation`, `RequestAuthorization`, `AuthorizeService`, `Cancel` |
| **Timed discovery scan** | **Yes** | `system_dbus__bluez_adapter.run_scan__timed()` blocks on `mainloop.run()` |
| **GATT server hosting** | **Yes** | `GattServerManager` requires MainLoop for characteristic read/write dispatch |
| **LE advertising** | **Yes** | `LEAdvertisingManager` uses MainLoop for registration callbacks |
| **Outbound D-Bus calls** | No | Property reads, method calls (Connect, Disconnect, ReadValue, WriteValue) are synchronous |
| **Object registration** | No | `dbus.service.Object` subclass registration is synchronous |

### 4.2  Single-Flight Operations

Due to BlueZ and D-Bus constraints, certain operations must be serialized
(only one instance running at a time):

| Operation | Constraint | Enforcement |
|-----------|-----------|-------------|
| BLE scan | One active discovery per adapter | BlueZ enforces; `OperationInProgressError` if concurrent |
| BLE connection | Sequential per target device | `EnumerationController` serializes retries |
| Pairing | One pairing per adapter | BlueZ agent framework enforces |
| GATT read/write | Sequential per characteristic | BlueZ serializes at characteristic level |
| MainLoop | One active `mainloop.run()` per process | Application must coordinate |

### 4.3  Thread Safety

| Component | Thread-Safe? | Notes |
|-----------|-------------|-------|
| Observation DB | Yes | `_DB_LOCK` (threading.Lock) guards all cursor operations |
| `print_and_log()` | Yes | File writes are atomic at OS level |
| `OutputContext` | No | Single-threaded; create per mode |
| D-Bus calls | Partially | `dbus-python` SystemBus is not thread-safe; calls from worker threads require `GLib.idle_add()` |
| `SignalRouter` | Yes | Thread-safe event dispatch |

---

## 5  Session Lifecycle

### 5.1  Adapter Initialization

```
1. require_adapter()           → assert adapter exists and is powered
2. run_preflight_checks()      → full environment audit (optional)
3. system_dbus__bluez_adapter() → construct adapter instance
4. adapter.set_discovery_filter({...})  → configure scan parameters
```

### 5.2  BLE Device Lifecycle

```
1. passive_scan() / run_scan__timed()  → discover devices
2. connect_and_enumerate__bluetooth__low_energy(mac)
   → returns (device, mapping, landmine_map, permission_map)
3. Read/Write operations via Characteristic.ReadValue() / WriteValue()
4. Device disconnect (explicit or remote-initiated)
5. Observation data persisted via upsert_device(), upsert_services(), etc.
```

### 5.3  Classic Device Lifecycle

```
1. discover_services_sdp(mac) or discover_services_sdp_connectionless(mac)
2. connect_and_enumerate__bluetooth__classic(mac)
3. Profile-specific operations (PBAP, OPP, FTP, MAP, PAN, SPP)
4. Disconnect
5. Observation data persisted via upsert_classic_services(), upsert_sdp_record()
```

### 5.4  Long-Running Operations

| Operation | Typical Duration | Cancellation |
|-----------|-----------------|-------------|
| Passive scan | 5–60 seconds | `adapter.stop_discovery()` |
| Timed scan | Configurable (default 5s) | MainLoop quit |
| BLE enumeration | 10–60 seconds | Not cancellable mid-stream |
| Classic SDP | 5–30 seconds | Timeout-based |
| Audio recon | Minutes | Keyboard interrupt |
| Brute-force write | Minutes to hours | Keyboard interrupt |

---

## 6  Data Formats

### 6.1  Device Record (from `get_device_detail`)

```json
{
  "mac": "AA:BB:CC:DD:EE:FF",
  "name": "Device Name",
  "alias": "User Alias",
  "rssi": -45,
  "address_type": "public",
  "manufacturer_data": {"0x004C": "..."},
  "uuids": ["0000180A-0000-1000-8000-00805F9B34FB"],
  "first_seen": "2026-05-22T10:00:00",
  "last_seen": "2026-05-22T11:00:00",
  "services": [...],
  "characteristics": [...],
  "descriptors": [...]
}
```

### 6.2  GATT Service Structure (from enumeration)

```json
{
  "UUID": "0000180A-0000-1000-8000-00805F9B34FB",
  "name": "Device Information Service",
  "primary": true,
  "characteristics": {
    "00002A29-0000-1000-8000-00805F9B34FB": {
      "name": "Manufacturer Name String",
      "flags": ["read"],
      "value": "Example Corp",
      "descriptors": {}
    }
  }
}
```

### 6.3  EnumerationResult (from `EnumerationController.enumerate`)

```python
EnumerationResult(
    success=True,
    data={"services": {...}, "characteristics": {...}, ...},
    annotations=[],
    error_summary=None,
    attempts=1,
    device=<device_object>,
    landmine_map={"char_uuid": "auth_required"},
    permission_map={"char_uuid": ["read", "write"]}
)
```

### 6.4  Error Response Format (for programmatic callers)

```json
{
  "success": false,
  "error": {
    "code": 9,
    "identifier": "ERR_NOT_FOUND",
    "message": "Device AA:BB:CC:DD:EE:FF not found",
    "exception": "DeviceNotFoundError"
  }
}
```

---

## 7  Symbol Census

Per-top-level-package inventory (subpackages folded in). **Exported names** sums
every literal `__all__` across the package subtree; modules that build exports
dynamically or omit `__all__` contribute 0 but are still counted as module files.
This block is **auto-generated** — regenerate with
`python bleep/scripts/gen_api_spec.py --write`.

<!-- AUTOGEN:census START (python bleep/scripts/gen_api_spec.py --write) -->
| Top-level package | Module files | Exported names (Σ `__all__`) |
|-------------------|-------------:|-----------------------------:|
| (root) | 3 | 2 |
| `bleep.analysis` | 6 | 55 |
| `bleep.ble_ops` | 43 | 122 |
| `bleep.bt_ref` | 23 | 16 |
| `bleep.callbacks` | 5 | 8 |
| `bleep.cli` | 21 | 4 |
| `bleep.core` | 25 | 143 |
| `bleep.dbus` | 3 | 4 |
| `bleep.dbuslayer` | 46 | 153 |
| `bleep.gatt` | 1 | 0 |
| `bleep.mesh` | 12 | 22 |
| `bleep.modes` | 63 | 98 |
| `bleep.pairing` | 1 | 14 |
| `bleep.protocols` | 1 | 0 |
| `bleep.signals` | 5 | 38 |

**Totals:** 258 `.py` module files; **679** names exported via a literal `__all__`. (Modules that build exports dynamically or omit `__all__` contribute 0 to the count but are included in the module-file tally.)
<!-- AUTOGEN:census END -->

---

## 8  Version History

| Date | Version | Change |
|------|---------|--------|
| 2026-09-13 | 0.1.2 | BLEEP package version bump 3.0.0 → 3.1.0 (see changelog); documented API surface unchanged. |
| 2026-09-13 | 0.1.1 | Doc-fidelity pass: corrected symbol counts against `__all__` (`observations` 36→43, `classic/version` 3→6, `classic/sdp` 4→5); moved `resolve_oui`/`format_uuid_display` out of the `ble_ops` package surface (they live in `ble_ops.common.conversion`); added `gatt/`+`protocols/` to the hierarchy; noted the full 63-file `modes` inventory; §2 tree and §7 census are now auto-generated by `bleep/scripts/gen_api_spec.py`. |
| 2026-05-22 | 0.1.0 | Initial API specification (Phase 7) |
