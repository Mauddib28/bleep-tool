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
