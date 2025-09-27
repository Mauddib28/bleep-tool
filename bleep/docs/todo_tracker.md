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
    - [ ] Add integration examples with observation database
    - [ ] Document advanced security analysis algorithms
    - [ ] Create customization guide for security assessment criteria
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

- [ ] Pairing agent polish (README.refactor)
- [ ] Device-feature database (SDP & PBAP)  
  * Merge existing bullet *"Local database for unknown UUIDs + device observations"* – expand scope to store:
    * SDP service/attribute snapshots per device (Classic & BLE)
    * PBAP phonebook metadata (repository sizes, Hash of full dump)  
    * First-seen / last-seen timestamps, adapter used, friendly names  
  * Decide storage: simple SQLite in `~/.bleep/observations.db` (no runtime deps)  **(SPEC FINAL 2025-07-24)**  
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
  * Write migration note in README.refactor
  * Device type classification improvements:
    - [ ] Enhance 'dual' device detection to require conclusive evidence from both protocols
    - [ ] Only set device_type='dual' when both BLE and Classic aspects are confirmed
    - [ ] Document specific detection criteria for each device type category
  * Database timestamps tracking:
    - [x] Fix `first_seen` field not being populated for new devices
    - [x] Ensure timestamp fields maintain correct data (first_seen stays constant, last_seen updates)
    - [x] Update default CLI display to show both timestamp fields
  * Enhance observation_db.md documentation:
    - [x] Document schema versioning information
    - [x] Add filtering examples for `db list` and `db timeline`
    - [ ] Expand database schema with comprehensive table and column descriptions
    - [ ] Add programmatic API usage examples
    - [ ] Document observation module's public functions with examples
    - [ ] Create advanced query cookbook for complex data extraction scenarios
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
  - [ ] Design targeted scanning framework
  - [ ] Implement device fingerprinting
  - [ ] Create vulnerability assessment helpers
  - [ ] Build reporting tools
  - [ ] Document assessment methodologies

## Documentation Improvements

> This section tracks gaps in current documentation, particularly for the device tracking and observation capabilities. Addressing these tasks will ensure users can fully leverage the existing features through both CLI and programmatic APIs.

- [ ] **Device Tracking Documentation**
  - [ ] Create comprehensive programmatic API reference for observation module
    - [ ] Document each function in `observations.py` with examples
    - [ ] Add integration examples for custom scripts
    - [ ] Create cookbook for common observation tasks
    - [ ] Document filtering and query techniques for device data
  - [ ] Enhance AOI Analyzer documentation
    - [ ] Create dedicated `aoi_analyzer_api.md` file with class reference
    - [ ] Add examples of direct usage of AOIAnalyser class methods
    - [ ] Document security analysis algorithms and scoring system
    - [ ] Provide customization examples for different analysis needs
  - [ ] Add real-world usage scenarios
    - [ ] Long-term device monitoring workflows
    - [ ] Enterprise device tracking patterns
    - [ ] Security assessment workflows using observation database
    - [ ] Integration examples with external systems
  - [ ] Document detailed database schema
    - [ ] Create complete schema diagram with relationships
    - [ ] Document each table and column with descriptions
    - [ ] Add query examples for complex data extraction
    - [ ] Create migration guide for schema changes

## Technical Scalability Improvements

- [ ] **Database Optimization**
  - [ ] Implement indexing strategy for observation database
  - [ ] Add query optimization for large device sets
  - [ ] Create database maintenance utilities
  - [ ] Document database schema and optimization techniques

- [ ] **Memory Management**
  - [ ] Audit large data structure usage
  - [ ] Implement lazy loading patterns for device maps
  - [ ] Add resource cleanup hooks
  - [ ] Document memory usage patterns and recommendations

- [ ] **D-Bus Reliability**
  - [ ] Enhance BlueZ stall detection
  - [ ] Implement automatic recovery strategies
  - [ ] Add connection pooling for high-volume operations
  - [ ] Document D-Bus reliability best practices

## CLI Command Enhancements (Completed)

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
   [ ] Add read-in and generation of UUIDs to create UUID Check lists (Servce, Characteristic, Descriptor)
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

