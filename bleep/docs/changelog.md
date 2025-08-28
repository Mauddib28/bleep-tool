## v2.1.4 – BLE CTF Mode Enhancement (2025-07-26)
### Added
* **BLE CTF Mode** – Enhanced with automated flag discovery and solving capabilities:
  * Intelligent pattern recognition for various flag formats and challenge types
  * Automatic solution generation with confidence scoring
  * Visual representation of flag status and progress
  * CLI integration for easy command-line usage
  * Comprehensive documentation in `docs/ble_ctf_mode.md`
* **BLE CTF Mode** – Added ability to write to any characteristic with the `write-char` command:
  * Supports writing to any characteristic by name or handle
  * Allows direct interaction with specific characteristics for advanced testing
  * Enables manual flag solving with precise control over values
* **BLE CTF Mode** – Added flexible data format options for writing values:
  * New `write-hex` command to write hex strings as raw bytes to Flag-Write
  * New `write-byte` command to write single byte values to Flag-Write
  * New `write-char-hex` command to write hex strings as raw bytes to any characteristic
  * New `write-char-byte` command to write single byte values to any characteristic
  * Auto-detection of hex strings in auto-solve mode for proper byte conversion

### Fixed
* **BLE CTF Mode** – Fixed D-Bus signature errors when reading and writing characteristics by properly specifying the signature for empty option dictionaries
* **BLE CTF Mode** – Reduced debug log noise by suppressing expected D-Bus errors (UnknownObject, bus attribute, and signature guessing) during direct handle access attempts
* **BLE CTF Mode** – Fixed mismatch between flag solutions and actual required values by improving pattern extraction and adding solution verification
* **BLE CTF Mode** – Enhanced visualization to indicate when solutions are found but not verified by checking the actual score

## v2.1.3 – User Mode Completion (2025-07-25)
### Added
* **User Mode** – Complete implementation of user-friendly interface for Bluetooth exploration:
  * Menu-driven interface for interactive device interaction
  * Simplified device discovery and connection workflow
  * Service and characteristic browsing with intuitive navigation
  * Multi-format value reading and writing for characteristics
  * Notification monitoring with human-readable output
  * Signal configuration interface with guided setup
  * Device data export for offline analysis
  * Integration with error handling system for user-friendly messages
  * Comprehensive documentation including:
    * Detailed UI navigation patterns with menu hierarchy
    * Quick-start examples for common workflows
    * Advanced usage examples and integration patterns
    * Expanded troubleshooting guide with solutions for common issues
* **Assets-of-Interest (AoI)** – Complete implementation with comprehensive analysis, reporting, and management:
  * Analysis engine for identifying security issues in Bluetooth devices
  * Report generation in multiple formats (markdown, JSON, text)
  * Persistent storage of device data for offline analysis
  * Advanced CLI commands for device management (`analyze`, `report`, `list`, `export`)
  * Security scoring system to prioritize findings
  * Comprehensive documentation in `docs/aoi_mode.md`
* **Debug Shell** – Added `aoi` command for analyzing device data and generating security reports.
* **Signal Capture System** – Comprehensive framework for capturing, filtering, and processing Bluetooth signals:
  * Structured configuration system with filters, routes, and actions
  * Persistent storage of signal configurations
  * Signal routing based on various criteria (signal type, device, service, etc.)
  * Multiple action types (logging, saving, callbacks, database storage)
  * CLI for managing configurations (`signal-config` command)
  * Integration with existing BlueZ signals system
  * Example workflows for common use cases
  * Detailed documentation in `docs/signal_capture.md`

### Fixed
* **Debug Mode** – Fixed "services" command to properly handle Service objects in `_get_handle_from_dict()` function, resolving the "argument of type 'Service' is not iterable" error.
* **Debug Mode** – Fixed error in property monitor callback when disconnecting from a device while monitoring is active.
* **Error Handling** – Standardized error handling across the codebase with the new `BlueZErrorHandler` class:
  * User-friendly error messages with contextual information
  * Automatic reconnection logic for common disconnection issues
  * Enhanced defensive programming patterns to prevent crashes
  * Detailed logging of error causes and contexts
  * Controller stall detection and mitigation
* **User Mode** – Fixed import error in `user.py` module by updating references from `SignalFilterRule` to `SignalFilter` to match the actual class name in `signals.capture_config.py`
* **User Mode** – Fixed connection error by correctly unpacking the 4-tuple returned from `connect_and_enumerate__bluetooth__low_energy` function
* **User Mode** – Fixed service display error by updating the code to handle the dictionary structure of services instead of expecting a list of service objects
* **User Mode** – Added helper methods to device_le.py that leverage existing Service objects for proper service and characteristic access
* **User Mode** – Updated service display to correctly show actual services using proper BlueZ object access patterns
* **User Mode** – Added Brute-Write functionality to the characteristic actions menu for writable characteristics
* **User Mode** – Completed comprehensive testing of UI functionality against multiple device types, ensuring robust operation across different Bluetooth implementations
* **User Mode** – Fixed signal capture configuration functionality by properly initializing SignalCaptureConfig with required parameters and using correct API methods
* **User Mode** – Fixed SignalAction creation in signal capture configuration by using the correct parameter names and ActionType enum values
* **User Mode** – Fixed filter rule addition in signal capture configuration to correctly use ActionType enum
* **User Mode** – Fixed signal type selection in filter rules by using the proper SignalType enum values

## v2.1.2 – Database and CLI Enhancements (2025-07-24)
### Added
* **Documentation** – CLI quick-start now lists the `aoi` command; `todo_tracker.md` expanded with detailed AoI workflow subtasks.
* **Observation DB** – Now stores characteristic value history (`char_history` table). Values are logged automatically during multi-read operations.
* **CLI** – Enhanced with new commands:
  * `db` command with `--fields` filter for `list` and new `timeline` sub-command
  * Enumeration helper enhancements:
    * `build_payload_iterator` now supports alt, repeat:<byte>:<len>, hex:<bytes> patterns
    * `brute_write_range` respects ROE flags gracefully (logs + skip instead of raising)
* **Documentation** – User-mode quick-start guide and helper docs added

### Changed
* **Database Schema** – Upgraded to v2 schema, renaming columns to avoid Python keyword conflicts:
  * `class` → `device_class` in devices table
  * `state` → `transport_state` in media_transports table
* **Documentation** – Updated observation_db.md with schema versioning information and filtering examples.

## v2.1.1 – Media Layer Expansion (2025-07-23)
### Added
- Media-layer refactor complete:
  - `MediaService` wrapper (org.bluez.Media1) for endpoint/player registration.
  - `MediaFolder` / `MediaItem` browsing helpers with ListItems/Search support.
  - `find_media_objects()` enumeration utility returning Media1/Player/Folder/Item tree.
  - `MediaRegisterHelper` convenience class to register SBC sink/source endpoints.
  - CLI `media list --objects` flag to dump full object tree.
- Stand-alone documentation **docs/media_mode.md** covering prerequisites, CLI, helpers.
- Unit tests `tests/test_media_helpers.py` validating enumeration & registration helpers.

### Changed
- `modes/media.py` list command prints concise view by default, retains old behaviour.

## v2.1.0 – Bluetooth Classic Support (2025-07-22)
### Added
- Interactive *Debug* mode support for Classic Bluetooth (`cscan`, `cconnect`, `cservices`).
- `classic-ping` timeout control and robust RTT parsing.
- **Native SDP fast-path** via D-Bus `GetServiceRecords`; falls back to *sdptool* when missing.
- **classic_rfccomm_open()** helper for generic RFCOMM sockets.
- Integration test suite for Classic discovery + BLE-CTF workflow; full pytest suite now passes.

### Fixed
- UUID name mismatches in tests (`Device Information Service`).
- Regression where `.bus` attribute was missing; added read-only proxy.
- Potential crash when detaching property signals now handled defensively.

### Changed
- README feature table now lists Bluetooth Classic support and links to guide.
- Expanded logging around `classic_l2ping` and debug commands.

---

# BLEEP change log

## v1.x.x - Initial Implementation of Bluetooth Landscape Exploration & Enumeration Platform

   Bluetooth Landscape Exploration & Enumeration Platform
       - Python Class Structures for Interacting with the BlueZ D-Bus interfaces

   Last Edit Date:         2025/07/14
   Author:                 Paul A. Wortman

   Important Notes:
       - Go to 'custom_ble_test_suite.py' for direct interaction code with the D-Bus
       - Go to 'bluetooth_dbus_interface.py' for use of signals and classes to interact with the D-Bus
       - Had to build BlueZ tools from source; btmon - Bluetooth monitor ver 5.77

   Current Version:        v1.8
   Current State:          Basic scanning and enumeration, ability to Read/Write from/to any Service/Characteristic/Descriptor, and a basic user interface
                           Automated enumeraiton (default passive) of supplied Assets of Interest via JSON files
                           Improved robutness via error handling and potential source of error reporting
                           Mapping of Landmine and Security related GATT aspects
                           Configuration of tools and capture for signals via user-mode
                           Expanded enumeration of GATT and Media devices
   Nota Bene:              Version with goal of consolidating function calls to streamline functionality
                           - Note: This verison is full of various implementations for performing scans (e.g. user interaction functions vs batch scanning functions) and needs to e consolidated so that there is User Interaciton and Batch variations
   Versioning Notes:
       - v1.3  -   Conversion of older code to official BLEEP named Python script
           -> Note: On 2024/01/27 19:13 EST it was noticed that the current call to the D-Bus was returning an access permission denied error (apparently done FIVE years ago); never noticed
       - v1.4  -   Fixing the D-Bus calls using a more current library; Note: Might just be an issue with ArtII
           - First attempted with GDBus, which is C API exposed to Python; assuming restart does not clear the issue
           - Worked to fix D-Bus errors; eventually had to fix XML file (/etc/dbus-1/system.d/com.example.calculator.conf); 2024-01-28 17:37 EST
           - Attaching other operating modes and building sanity checks around them
       - v1.5  -   Adding enumeration specific output logging
           - Improved robustness
           - Mapping of device enumeration problem areas
           - Assets of Interest mode with file-based input for automated enumeration
       - v1.6  -   Added mapping (mine + permission) to connect_and_enumerate function
           - Added usermode specific logging
           - Second method of Reading characteristics (with and without signature attached)
           - Auto-fix error hanlding for common issues with D-Bus BlueZ communication
       - v1.7  -   Fixes and preparation for DefCon32 Demo Labs
           - Improved robustness of tool to prevent crashes/failure
           - Configuration and capture of signals via user mode
           - Targeted device for user-mode operation
       - v1.8  -   Expanding the Scope of Interface/Device Enumeration
           - Potential limitation with Pico W training target; Note: May necessitate move to ESP32 chip libraries
           - Expanded UUID identification with retrieval of Bluetooth SIG UUIDs from online repository
           - Improved User Mode Write functionality
               - Added file input capabilitiy
               - Expanded to allow for named pipes
           - Device Class Translation to Human Readable Format
           - Manufacturer Identifier Translation to Human Readable Format
           - Service Data Translation to Human Readable Format
           - Advertising Type Translation to Human Readable Format
           - Device Enumeration and Human Readable Printout for Media Device Landscape
           - Structures for Augmentation to include Authentication via Pairing and Bonding
           - Media Device Enumeration
           - Device Type Identification

> Maintained alongside the code so every release carries its own history.

## Added Features:
- BLE Class functions for performing Reads and Writes to GATT Characteristics
- Device Internals Map Exploration functionality added
- User interaction and exploration menu that can be used to enumerate and detail out Services/Characteristics/Descriptors
- Augmented user interaction to allow Read/Write to Characteristics and Descriptors
- Full device map update read
- D-Bus debugging functionality and error handling
- Got multi-read functionality working; allows for completeing 1000 read flag
- Got notification signal catching working
- Added auto-termination to scans using BlueZ Adapter Class
- Added debug logging for notification signal catching
- Added Passive vs Active flag for GATT enumeration
- Improved user interaction functionality
- Added target input file for target/device selection via user interaction
- Added automated scanning that takes in a single or multtiple processed data files for target selection and enumeration
- Expanded BLE Class information based on updated BlueZ git docs (2023-12-11)
- Threads for handling Signal Emittion Capture using GLib
- Improved error handling with source of error reporting
- Clarified prints to show where the prints are coming from
- Fixed all script prints to write to either GENERAL or DEBUG logs
- Identification of BLE CTF UUIDs
- Reconnection check functionality
- Added reconnection command to user interaction mode
- Class of Device decoding; based on Assigned Numbers BT SIG document of 2023-12-15
- Check for and report of missing Bluetooth adapter
- Improve error handling by adding separate error for NoReply vs NotConnected
- Dedicated output for enumeration of devices
- Dedicated output for usermode
- Mapping of Landmine and Security characteristics
- Improved error handling with auto-fix functionality
- Improved robustness of tool for user-mode operation
- Confirmed two methods of reading GATT values via D-Bus structures; fixed descriptor reads
- Added structures for configuring and capture of signals via user-mode
- Robutness of user-mode augment to tolerate unexpected/incorrect input by user
- Improved robustness of user-mode signal capture to prevent code failure/death
- Added specific device address selection to user-mode
- Improved UUID identification via online-based generation of known BT SIG UUIDs
- Added Agent and Agent UI Classes to alleviate pairing
- Expanded logging to include Agent/Agent UI specific information to alleviate debugging
- Creating Agent and Agent Manager via Agent UI class
- Runing Agent UI as separate thread (similar to signal capture)
- Raw file read and write via User Mode
- Use of named pipes for file write in User Mode
- Conversion of Device Class into Major Class, Minor Class, and Major Services associated to Device
- Conversion of Manufacturer / Company Identifier to Company Name
- Conversion of Service Data UUID to Member UUID
- Conversion of Advertising Flag ID to Advertising Type
- Augments logging to include database access
- Enumeration of Media Control/Endpoint/Transpot Interface(s)


## How to update

1. Add a new heading at the **top** using the format:
   `## vX.Y.Z – YYYY-MM-DD`
2. Under that heading list bullet-points in past-tense, grouped by type:
   - **Added** – new capabilities
   - **Changed** – behaviour changes
   - **Fixed** – bug fixes
   - **Removed** – deprecations
3. Keep descriptions concise; link to commit hashes or PR numbers if applicable.

---

## v2.0.0 – Initial Refactored Modular Variant

Shifted away from monolith design structure to a modular variant
- Issues with circular import logic when first refactoring; addressed in current state
- Have basic working functionality:
    - Command Line implementation for CLI use in python one-liners to examine functionality
    - BLE CTF mode purposed for tool development and sanity checking against the BLE CTF device
    - Debug mode that allows for path-aware exploration and examination of Bluetooth Low Energy Devices
        - Include additional detailed information extraction

Immediate Future Tasks:
- Continue port and verification + validation of BLEEP v1.8 capabilities/functioanlity into the new BLEEP V2.0 
- Ensure UUID and non-UUID identification is functioning as desired
- Sanity check tracking structures to allow for off-line enumeration of devices no-longer in range
    - Will hit temporal and failure issues when establishing enumreations
- Expand to include basic structures for Bluetooth Classi BR/EDR

Long Term Future Tasks:
- Expand CLI mode fully
- Ensure full equivalent use of Debug Mode ith BR/EDR devices
- Establish User Mode functional equivlanet of BLEEP v1.8 User Mode capabilities

*Added*
- Modular package layout (`bleep.*`) replacing monolith script.
- In-package documentation hub (`bleep.docs`).
- Interactive *debug* mode and *BLE CTF* helper utilities.

*Changed*
- CLI rewritten to use sub-commands (`python -m bleep <cmd>`).

*Known issues*
- User mode UI still WIP – see `docs/user_mode.md` for roadmap. 

## v2.0.1 – 2025-07-18

### Added
- Classic Bluetooth **PBAP** dumping via `classic-pbap` CLI sub-command with multi-repository support and async transfer logic.
- Enhanced `classic-enum` command for SDP service enumeration.
- Documentation: `docs/bl_classic_mode.md`, CLI usage examples, troubleshooting steps.

### Fixed
- Graceful handling of BlueZ `NoReply` / timeout errors; suggests `bluetoothctl disconnect <MAC>` when controller stalls.
- Unicode decode errors in phone-book files containing non-UTF-8 characters.
- D-Bus signature mismatch when registering an OBEX agent (`input signature is longer…`).
- `classic-scan` now honours `--rssi` and `--pathloss` discovery filters, matching BlueZ SetDiscoveryFilter capabilities.

### Changed
- `classic-pbap` now stores multi-repo dumps under `/tmp/<mac>_<REPO>.vcf` by default; `--out` supported for single repo.

--- 

## v2.0.2 – 2025-07-18

### Added
- `--auto-auth` flag on `classic-pbap` that spins up an in-process OBEX Agent and automatically approves authentication / push requests.
- Generic `classic_rfccomm_open()` helper for future Classic profiles.

### Fixed
- D-Bus signature mismatch when registering an OBEX agent (`input signature is longer…`).

### Changed
- Documentation updated for auto-auth usage; bc-17 marked complete in tracker.

--- 

## v2.0.3 – 2025-07-18

### Added
- Configurable PBAP watchdog (`--watchdog` seconds, default 8).
- `classic-ping` sub-command wrapping BlueZ *l2ping* for reachability checks.

### Fixed
- `classic-pbap` no longer hangs indefinitely on stalled transfers; aborts after watchdog timeout.

--- 
