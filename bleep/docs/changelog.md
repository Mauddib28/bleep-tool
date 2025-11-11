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