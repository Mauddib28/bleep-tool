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