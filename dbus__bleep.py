#!/usr/bin/python3

# Imports from bluez.git/tree/test/test-device
from __future__ import absolute_import, print_function, unicode_literals

###
#   Bluetooth Landscape Exploration & Enumeration Platform
#       - Python Class Structures for Interacting with the BlueZ D-Bus interfaces
#
#   Last Edit Date:         2025/07/14
#   Author:                 Paul A. Wortman
#
#   Important Notes:
#       - Go to 'custom_ble_test_suite.py' for direct interaction code with the D-Bus
#       - Go to 'bluetooth_dbus_interface.py' for use of signals and classes to interact with the D-Bus
#       - Had to build BlueZ tools from source; btmon - Bluetooth monitor ver 5.77
#
#   Current Version:        v1.8
#   Current State:          Basic scanning and enumeration, ability to Read/Write from/to any Service/Characteristic/Descriptor, and a basic user interface
#                           Automated enumeraiton (default passive) of supplied Assets of Interest via JSON files
#                           Improved robutness via error handling and potential source of error reporting
#                           Mapping of Landmine and Security related GATT aspects
#                           Configuration of tools and capture for signals via user-mode
#                           Expanded enumeration of GATT and Media devices
#   Nota Bene:              Version with goal of consolidating function calls to streamline functionality
#                           - Note: This verison is full of various implementations for performing scans (e.g. user interaction functions vs batch scanning functions) and needs to e consolidated so that there is User Interaciton and Batch variations
#   Versioning Notes:
#       - v1.3  -   Conversion of older code to official BLEEP named Python script
#           -> Note: On 2024/01/27 19:13 EST it was noticed that the current call to the D-Bus was returning an access permission denied error (apparently done FIVE years ago); never noticed
#       - v1.4  -   Fixing the D-Bus calls using a more current library; Note: Might just be an issue with ArtII
#           - First attempted with GDBus, which is C API exposed to Python; assuming restart does not clear the issue
#           - Worked to fix D-Bus errors; eventually had to fix XML file (/etc/dbus-1/system.d/com.example.calculator.conf); 2024-01-28 17:37 EST
#           - Attaching other operating modes and building sanity checks around them
#       - v1.5  -   Adding enumeration specific output logging
#           - Improved robustness
#           - Mapping of device enumeration problem areas
#           - Assets of Interest mode with file-based input for automated enumeration
#       - v1.6  -   Added mapping (mine + permission) to connect_and_enumerate function
#           - Added usermode specific logging
#           - Second method of Reading characteristics (with and without signature attached)
#           - Auto-fix error hanlding for common issues with D-Bus BlueZ communication
#       - v1.7  -   Fixes and preparation for DefCon32 Demo Labs
#           - Improved robustness of tool to prevent crashes/failure
#           - Configuration and capture of signals via user mode
#           - Targeted device for user-mode operation
#       - v1.8  -   Expanding the Scope of Interface/Device Enumeration
#           - Potential limitation with Pico W training target; Note: May necessitate move to ESP32 chip libraries
#           - Expanded UUID identification with retrieval of Bluetooth SIG UUIDs from online repository
#           - Improved User Mode Write functionality
#               - Added file input capabilitiy
#               - Expanded to allow for named pipes
#           - Device Class Translation to Human Readable Format
#           - Manufacturer Identifier Translation to Human Readable Format
#           - Service Data Translation to Human Readable Format
#           - Advertising Type Translation to Human Readable Format
#           - Device Enumeration and Human Readable Printout for Media Device Landscape
#           - Structures for Augmentation to include Authentication via Pairing and Bonding
#           - Media Device Enumeration
#           - Device Type Identification
#
###

'''
    Resources and Notes:
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
'''

### TODO:
#   [ ] Create a function that searches through the Managed Objects for known Bluetooth objects (to the device that the code is running on)
#       - Note: Could make good OSINT capabilitiy
#   [ ] Check to see what type of device is being connected to
#       [ ] If BLE then connect with BLE Class structure
#       [ ] If BT then connect with Bluetooth Classic structure
#   [x] Create function mode that allows connecting directly to a specific device
#       - Note: Would attempt to connect regardless if in range of not; leverage D-Bus API (adapter? expermental capability)
#   [x] Improve error handling so that errors due not set everything to "None" but produce another set output (e.g. "ERROR")
#   [ ] Update the expected code structures bsaed on the updated BlueZ git documentation
#       - e.g. Error Codes, Responses, S/C/D properties
#       [ ] Look at updating any internal/code JSON references for expected data-structures
#   [ ] Create a decode + translation function for ManufacturerData using the "formattypes.yaml" BT SIG document
#       - Expectation is that this is how one can interpret the rest of the passed information where the SECOND OCTET is the "formattype" data type indicator
#   [x] Create a decode + translation function for Class data
#       [x] Hardcode Transation first to prove concept
#       [ ] Move to automatic pull down of YAML to perform conversion
#   [ ] Create a decode for appearance values
#       - Pull from bluetooth support files to better identify (e.g. similar to Class data)
#   [ ] Add functionality to re-read/refresh the device interface information
#       - Note: This is most likely where the D-Bus can read the GAP information (i.e. 0x1800)
#   [ ] Add read-in and generation of UUIDs to create UUID Check lists (Servce, Characteristic, Descriptor)
#   [ ] Make use of the "ARDUINO_BLE__BLE_UUID__MASK" variable to identify "groupings" of UUIDs
#       - Note: May be using the same Bluetooth SIG default UUID structure
#   [ ] Determine why pairing a device causes BIP to lose conneciton to the device
#   [x] Improving decoding information to use the BT SIG yaml files
#   [ ] Have the Mine/Permission mapping include a tracking of the associated error
#       - Make as a tuple? Perhaps dictionary?
#   [ ] Determine how to query if an action is in process for D-Bus/BlueZ
#   [ ] Add pairing to BLEEP
#       [ ] Basic pairing to a targeted device
#       [ ] Selective pairing to a targeted device
#       - Note: Research on the process shows that the communication "handshake" for Pairing() begins, but then fails due to lack of agent
#           - URL:      https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc/org.bluez.Agent.rst
## TODO (arduino):
#   [ ] Create function for starting a user interaction interface for a SPECIFIC ADDRESS
#   [ ] Clean-up and polish the user interaction interface screens
#   [ ] Add to the General Services Information Output:
#       [ ] ASCii print out for all Hex Array Values (S/C/D)
#       [ ] Handle print out for all S/C/D              <---- Note: This comes from the FOUR HEX of the [serv|char|desc]XXXX tags; BUT DIFFERENT FROM Characteristic Value Handle

## Added Features:
# BLE Class functions for performing Reads and Writes to GATT Characteristics
# Device Internals Map Exploration functionality added
# User interaction and exploration menu that can be used to enumerate and detail out Services/Characteristics/Descriptors
# Augmented user interaction to allow Read/Write to Characteristics and Descriptors
# Full device map update read
# D-Bus debugging functionality and error handling
# Got multi-read functionality working; allows for completeing 1000 read flag
# Got notification signal catching working
# Added auto-termination to scans using BlueZ Adapter Class
# Added debug logging for notification signal catching
# Added Passive vs Active flag for GATT enumeration
# Improved user interaction functionality
# Added target input file for target/device selection via user interaction
# Added automated scanning that takes in a single or multtiple processed data files for target selection and enumeration
# Expanded BLE Class information based on updated BlueZ git docs (2023-12-11)
# Threads for handling Signal Emittion Capture using GLib
# Improved error handling with source of error reporting
# Clarified prints to show where the prints are coming from
# Fixed all script prints to write to either GENERAL or DEBUG logs
# Identification of BLE CTF UUIDs
# Reconnection check functionality
# Added reconnection command to user interaction mode
# Class of Device decoding; based on Assigned Numbers BT SIG document of 2023-12-15
# Check for and report of missing Bluetooth adapter
# Improve error handling by adding separate error for NoReply vs NotConnected
# Dedicated output for enumeration of devices
# Dedicated output for usermode
# Mapping of Landmine and Security characteristics
# Improved error handling with auto-fix functionality
# Improved robustness of tool for user-mode operation
# Confirmed two methods of reading GATT values via D-Bus structures; fixed descriptor reads
# Added structures for configuring and capture of signals via user-mode
# Robutness of user-mode augment to tolerate unexpected/incorrect input by user
# Improved robustness of user-mode signal capture to prevent code failure/death
# Added specific device address selection to user-mode
# Improved UUID identification via online-based generation of known BT SIG UUIDs
# Added Agent and Agent UI Classes to alleviate pairing
# Expanded logging to include Agent/Agent UI specific information to alleviate debugging
# Creating Agent and Agent Manager via Agent UI class
# Runing Agent UI as separate thread (similar to signal capture)
# Raw file read and write via User Mode
# Use of named pipes for file write in User Mode
# Conversion of Device Class into Major Class, Minor Class, and Major Services associated to Device
# Conversion of Manufacturer / Company Identifier to Company Name
# Conversion of Service Data UUID to Member UUID
# Conversion of Advertising Flag ID to Advertising Type
# Augments logging to include database access
# Enumeration of Media Control/Endpoint/Transpot Interface(s)

### Imports
## Imports for using the D-Bus
import dbus
import dbus.exceptions
import dbus.service
import dbus.mainloop.glib   # Import for simple-agent example (e.g. Agent Class and functionality)
# Import GLib
from gi.repository import GLib
## Imports for specialty variables and functions
import bluetooth_constants
import bluetooth_exceptions
import bluetooth_utils
import bluetooth_uuids
## General usage libraries
import sys                      
import time
#sys.path.insert(0, '.')        # Note: Not sure how this work, put back in once better understood
# Import re
import re
# Import os
import os                       # Note: This ALSO helps with the calling of OS function/binaries from within Python
# Import subprocess
import subprocess               # Used to make the OS calls INSTEAD of 'os'
# Import etree and its many forms
import xml.etree.ElementTree as ET
# Import stat
import stat                     # Used to check file mode

# Imports from bluez.git/tree/test/test-device; Import
import dbus.mainloop.glib
try:
  from gi.repository import GObject
except ImportError:
  import gobject as GObject
#import bluezutils              # Note: Do NOT use.... replace with other code

# Imports for Arguments to Python Script
import getopt                   # Helps with argument passing

# Imports for Generating Introspection Maps
import json, xmltodict

# Import for adding threading to script
import threading

# Import for creating bruteforce hex mapping
from itertools import product

# Import for calculating the correct number of bytes for writes
import math

# Imports for Terminal Output Configuration (for Agents)
#import dbus.service
import numpy
# Terminal output configuration for BlueZ Agent usage
try:
    from termcolor import colored, cprint
    set_green = lambda x: colored(x, 'green', attrs=['bold'])
    set_cyan = lambda x: colored(x, 'cyan', attrs=['bold'])
except ImportError:
    set_green = lambda x: x
    set_cyan = lambda x: x

### Globals

# Debugging Bit
dbg = 0

# Service Resolving Timeout - In Seconds
#timeout_limit__in_seconds = 1800    # 30 minutes
#timeout_limit__in_seconds = 900    # 15 minutes
#timeout_limit__in_seconds = 300    # 5 minutes
timeout_limit__in_seconds = 120     # 2 minutes
#timeout_limit__in_seconds = 30      # 15 seconds is too short...
# Note: The above is more intended for batch scannin versus specific examination (i.e. user exploration mode)
timewait_in_progress = 0.200          # 200 milliseconds

# Logging Files
general_logging = '/tmp/bti__logging__general.txt'
debug_logging = '/tmp/bti__logging__debug.txt'
enumerate_logging = '/tmp/bti__logging__enumeration.txt'
usermode_logging = '/tmp/bti__logging__usermode.txt'
agent_logging = '/tmp/bti__logging__agent.txt'
database_logging = '/tmp/bti__logging__database.txt'
# Log Types
LOG__GENERAL = "GENERAL"
LOG__DEBUG = "DEBUG"
LOG__ENUM = "ENUMERATE"
LOG__USER = "USERMODE"
LOG__AGENT = "AGENT"
LOG__DATABASE = "DATABASE"

## Constants for BlueZ (Make local, then bring in larger bluetooth_constants)
# BLE CTF Variables
BLE_CTF_ADDR = 'CC:50:E3:B6:BC:A6'
INTROSPECT_INTERFACE = 'org.freedesktop.DBus.Introspectable'
INTROSPECT_SERVICE_STRING = 'service'
INTROSPECT_CHARACTERISTIC_STRING = 'char'
INTROSPECT_DESCRIPTOR_STRING = 'desc'

# Configuration of the dbus interface
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)       # Required prior to connecting to the bus; https://gitlab.freedesktop.org/dbus/dbus-python/-/blob/master/doc/tutorial.txt
dbus.mainloop.glib.threads_init()

# Known Bluetooth Low Energy IDs
ARDUINO_BLE__BLE_UUID__MASK = "XXXXXXXX-0000-1000-8000-00805f9b34fb"
BLE__GATT__SERVICE__GENERIC_ACCESS_PROFILE = "00001800-0000-1000-8000-00805f9b34fb"
BLE__GATT__DEVICE_NAME = "00002a00-0000-1000-8000-00805f9b34fb"

# Details for GATT Structure Properties
GATT__SERVICE__PROPERTIES = ["UUID", "Primary", "Device", "Includes", "Handle", "Characteristics", "Value"]
GATT__CHARACTERISTIC__PROPERTIES = ["UUID", "Service", "Value", "WriteAcquired", "NotifyAcquired", "Notifying", "Flags", "Handle", "MTU", "Notify", "Descriptors"]
GATT__DESCRIPTOR__PROPERTIES = ["UUID", "Characteristic", "Value", "Flags", "Handle"]
# Note: The above are running lists of property values seen when exploring devices via user mode

# Pretty Printing Variables
PRETTY_PRINT__GATT__FORMAT_LEN = 7

# Default Variables for Use with Mapping
UNKNOWN_VALUE = "-=!=- UNKNOWN -=!=-"

# D-Bus Signatures Translation
#   - Note: Each separate member in the signature provides its own meaning to the signature
#       - Example: 'i' means 32-bit int, 'ii' means two 32-bit ints
# NOTE: The 'a' here acts as a leading character to a signature aX
#   - Examples:    'as' => Array of Strings, 'a(ii)' => Array of Structs each containing two 32-bit integeres
# Structs are represented by Python tuples
#   - Example:      '(is)' is the signature of a struct containing a 32-bit integer and a string
# Dictionaries are represented by Python dictionaries
#   - Example:      'a{xy}' where 'x' represents the signature of the keys and 'y' represents the signature of the values
#   - Example:      'a{s(ii)}' is a dictionary where the keys are strings and the values are structs containing two 32-bit integers
# Note: The variant signature (i.e. 'v') is a variant type; D-Bus will send the type of its value alongside the value inside the payload
DBUS_SIGNATURE__JSON = {
    "Signature Character": {
        "o": {
            "Meanings": ["Proxy Object", "dbus.Interface", "dbus.service.Object", "dbus.ObjectPath"]
            }, 
        "b": {
            "Meanings": ["dbus.Boolean", "bool"]
            },
        "y": {
            "Meanings": ["dbus.Byte"]
            },
        "n": {
            "Meanings": ["dbus.Int16"]
            },
        "q": {
            "Meanings": ["dbus.UInt16"]
            },
        "i": {
            "Meanings": ["dbus.Int32", "int"]    # Note: In Python2, this would include 'long' type
            },
        "u": {
            "Meanings": ["dbus.UInt32"]
            },
        "x": {
            "Meanings": ["dbus.Int64"]
            },
        "t": {
            "Meanings": ["dbus.UInt64"]
            },
        "d": {
            "Meanings": ["dbus.Double", "float"]
            },
        "g": {
            "Meanings": ["dbus.Signature"]
            },
        "s": {
            "Meanings": ["dbus.String", "dbus.UTF8String", "bytes", "str"]
            },
        "a": {
            "Meanings": ["dbus.Array"]
            },
        "v": {
            "Meanings": ["signature of variant"]
            }
    },
    "Complete Signature": {
        "as": "Array of Strings",
        "a(ii)": "Array of Structs each containing two 32-bit integers"
    }
}

### Classes

## D-Bus Classes

# Adapter Interface Class   -   Used to Interact with the Adapter Interface, Set the Discovery Filter, and Search for Devices
#   [x] Add timeout to the scanning; create default that requires Ctrl+C
#   [ ] Add tracking of seen Added + Removed devices
#       - Note: One can use to check for reconnet due to Removed device signal
#   [ ] Add ability to specify the specific Bluetooth Adapter
class system_dbus__bluez_adapter:

    '''
    Entry point for using and interacting with the system's adapter interface

    This class is intended to be used for the purpose of interacting with Bluetooth devices and for enabling the running of device scans
    '''

    # Initialization Function
    def __init__(self, bluetooth_adapter=bluetooth_constants.ADAPTER_NAME):
        # Note: Adding the '_' in front seems to work the same as the '.' in a linux directory
        self._bus = dbus.SystemBus()                                # Main system D-Bus for Class Object operations
        self.devices_found = None
        self.default_discovery_filter = {'Transport': 'auto'}       # Note: Uses whatever the system adapter has configured
        self.classic_discovery_filter = {'Transport': 'bredr'}      # ONLY search for Bluetooth Classic devices
        self.le_discovery_filter = {'Transport': 'le'}              # ONLY search for Blueooth LE devices
        self.custom_discovery_filter = None                         # ONLY used by a user to set a custom discovery filter
        self.timer_id__last = None                                  # Tracking the last Timer ID created (i.e. .timeout_add() for GLib MainLoop)
        self.timer_id__list = []                                    # Tracking all the Timer IDs created by this D-Bus BlueZ Adapter Class
        self.timer__default_time__ms = 5000                         # Default setting of scanning time to 5000 milliseconds
        self.bluetooth_adapter = bluetooth_adapter                  # Bluetooth adapter to use for scanning for devices
        self._bus_listener = dbus.SystemBus()                       # System D-Bus used for signal/notification/indiciation configuration and capture

    # Internal Function for Clearing/Canceling All Active Timers
    def clear_all_timers(self):
        # Interate through all the timers in the internal array
        for timer_id__item in self.timer_id__list:
            #GLib.source_remove(self.timer_id__array[timer_id__item])
            # Remove the timer source from GLib
            GLib.source_remove(timer_id__item)
            # Remove the Timer ID from the list
            self.timer_id__list.remove(timer_id__item)
        # Clear/Re-Set the Timer Id Array
        #self.timer_id__array = {}

    # Internal Function for Clearing/Canceling a Single Timer - Identified via Timer ID
    def clear_single_timer(self, timer_id):
        # Ensure that the timer_id presented is known to the Adapter Class
        if timer_id not in self.timer_id__list:
            print("[!] ERROR:\tTimer ID is Unknown to Adapter")
            return False
        # Remove the Timer Source from GLib
        GLib.source_remove(timer_id)
        # Remove the Timer ID from the Timer ID Array
        self.timer_id__list.remove(timer_id)
        # Check if the Timer removed is the Last one seen
        if timer_id == self.timer_id__last:
            self.timer_id__last = None
        # Confirm everything got done
        return True

    # Internal Function for Running a Device Scan
    #   - Note: This makes a call to a generic function that exists in the rest of the code
    def run_scan(self):
        # Check if the custom_discovery_filter has been set
        if not self.custom_discovery_filter:
            run_and_detect__bluetooth_devices__with_provided_filter(self.default_discovery_filter)
        else:
            run_and_detect__bluetooth_devices__with_provided_filter(self.custom_discovery_filter)
        self.devices_found = create_and_return__discovered_managed_objects()

    # Internal Function for Running a Timed Device Scan
    def run_scan__timed(self):
        # Check if the custom_discovery_filter has been set
        if not self.custom_discovery_filter:
            self.run_and_detect__bluetooth_devices__with_provided_filter__with_timeout(self.default_discovery_filter, self.timer__default_time__ms)
        else:
            try:
                self.run_and_detect__bluetooth_devices__with_provided_filter__with_timeout(self.custom_discovery_filter, self.timer__default_time__ms)
            except dbus.exceptions.DBusException:
                raise dbus.exceptions.DBusException
        # TODO: Replace the line below with the use of internal varaibles to track found devices and lost devices (which can then be compared by the managed objects tracking)
        self.devices_found = create_and_return__discovered_managed_objects()
        # Remove the timer source
        self.clear_single_timer(self.timer_id__last)

    # Internal Functio for Setting the Discovery Filter
    def set_discovery_filter(self, new_discovery_filter):
        # Set the internal/customer discovery filter
        self.custom_discovery_filter = new_discovery_filter

    # Function for setting a timeout time for device discovery
    #   - Used as a callback function for the code (automatically on the backend?)
    def discovery_timeout(self, adapter_interface, mainloop):
        # Debugging the Discovery Timout function
        if dbg != 0:    # ~!~
            #print("[?] Debugging Timed Scan\n\tTimer ID:\t{0}\n\tTimer List:\t{1}".format(self.timer_id__last, self.timer_id__list))
            output_log_string = "[?] Debugging Timed Scan\n\tTimer ID:\t{0}\n\tTimer List:\t{1}".format(self.timer_id__last, self.timer_id__list)
            print_and_log(output_log_string, LOG__DEBUG)
        # To get the .source_remove() call to work one has to (1) track the timer_id as a class property (or global) variable, (2) Add the newly created 'timer_id' to this variable, (3) when the callback function gets called, pull the information from the Class object
        #GLib.source_remove(timer_id)
        #GLib.source_remove(self.timer_id__last)
        ## Stop the MainLoop
        mainloop.quit()
        ## Stop other processes, signals, etc.
        adapter_interface.StopDiscovery()
        '''
        ## Note: Below is only needed when signal receivers are required WITH the device scanning
        bus = dbus.SystemBus()
        # Removing the signal receiver to the System Bus
        bus.remove_signal_receiver(interfaces_added,"InterfacesAdded")
        # Removing another signal receiver to the System Bus
        bus.remove_signal_receiver(interfaces_added,"InterfacesRemoved")
        # Removing another signal receiver to the System Bus
        bus.remove_signal_receiver(properties_changed,"PropertiesChanged")
        # List the devices that were found
        list_devices_found()
        '''
        return True
    # Note: Might need to use the '*args' debugging to determine how/what information is passed to the above function


    ## [x] Add "Auto-termination" of the script after some period of time (to augment usability with automated scripts; lack of requirement for human interaction)
    # Function for Performing Bluetooth Device Scanning (type provided by user) as well as a default (or user provided) timeout
    #   - Nota Bene: The discovery filter can be 'auto', 'bredr', OR 'le'
    #   - Default timer set to 5000 milliseconds (i.e. 5 seconds)
    def run_and_detect__bluetooth_devices__with_provided_filter__with_timeout(self, discovery_filter={'Transport': 'auto'}, timeout_ms=5000):
        print("[*] Starting Discovery Process with Timing")
    
        # Debugging
        if dbg != 0:    # ~!~
            print("[?] Checking Timer Information\n\tLast Timer ID:\t{0}\n\tTimer List:\t{1}".format(self.timer_id__last, self.timer_id__list))
    
        ## Internal Functions for configuring timeout to the GLib MainLoop()
    
        ## Setup the Device Discovery
        # Create the Object for the Adapter Interface;
        #   [ ] Re-create these adpaters using the adpter Class Object
        #adapter_object, adapter_interface, adapter_properties = create_and_return__system_adapter_dbus_elements()
        try:    # Attempt to create the adapter structures
            adapter_object, adapter_interface, adapter_properties = create_and_return__system_adapter_dbus_elements__specific_hci(self.bluetooth_adapter)
        except dbus.exceptions.DBusException:       # Checking for generic exception; TODO: Create more detailed expection
            raise dbus.exceptions.DBusException
        # Configure the Scanning for Devices
        adapter_interface.SetDiscoveryFilter(discovery_filter)
        # Start the Discovery Process
        adapter_interface.StartDiscovery()
        # Setup the GLib MainLoop
        main_loop = GLib.MainLoop()
    
        # Adding a timeout to the GLib MainLoop
        #   - Note: According to documentation for the GLib timeout_add() function definition one can add an gpointer of data to pass to the callback function
        #       - URL:      https://docs.gtk.org/glib/func.timeout_add.html
        # Set the Timer ID to the Class property
        self.timer_id__last = GLib.timeout_add(timeout_ms, self.discovery_timeout, adapter_interface, main_loop)
        # Add this timer to the larger array
        self.timer_id__list.append(self.timer_id__last)
        # According to the documentation ANY NUMBER of additional variables can be passed back to the callback function by listing them AFTER the callback function
        #   - URL:      https://www.manpagez.com/html/pygobject/pygobject-2.28.3/glib-functions.php#function-glib--timeout-add

        # Debugging
        if dbg != 0:    # ~!~
            print("[?] Next Timers Check\n\tLast Timer ID:\t{0}\n\tTimer List:\t{1}".format(self.timer_id__last, self.timer_id__list))
    
        # Begin the Scanning for Devices
        try:
            print("\t!\t-\tPress Ctrl-C to end scan\n")
            main_loop.run()
        except KeyboardInterrupt:
            main_loop.quit()
        
        print("[+] Completed Discovery")

# Signal Catching Class - For catching/intercepting notification, indicate, or other Signal-Type (i.e. signal, method_call, method_response, error) and purposed with returning the information for other uses (e.g. tracking, updates, CTFs)
#   - Note: Similar to Adapter Class's functionality but much broader than just scans
class system_dbus__bluez_signals:
    '''
    Entry point for using and interacting with emitted signals over the D-Bus

    This class is intended to be used for the purpose of interacting with Bluetooth devices and for catching D-Bus/Bluetooth/GATT signals
    '''
    # Initialization Function
    def __init__(self):
        # Note: Adding the '_' in front seems to work the same as the '.' in a linux directory
        self._bus = dbus.SystemBus()
        self.devices_found = None
        #self.default_discovery_filter = {'Transport': 'auto'}       # Note: Uses whatever the system adapter has configured
        #self.classic_discovery_filter = {'Transport': 'bredr'}      # ONLY search for Bluetooth Classic devices
        #self.le_discovery_filter = {'Transport': 'le'}              # ONLY search for Blueooth LE devices
        #self.custom_discovery_filter = None                         # ONLY used by a user to set a custom discovery filter
        self.timer_id__last = None                                  # Tracking the last Timer ID created (i.e. .timeout_add() for GLib MainLoop)
        self.timer_id__list = []                                   # Tracking all the Timer IDs created by this D-Bus BlueZ Adapter Class
        self.timer__default_time__ms = 5000                         # Default setting of scanning time to 5000 milliseconds
        self.mainloop_run__default_time__ms = 5000                  # Default setting of the amount of time the MainLoop will run at any given time
        self.signal_receiver__list = {}                             # Tracking Signal Receivers that have been added to the D-Bus

    ## Definitions for Internal Property Tracking
    # Internal Function for Clearing/Canceling All Active Timers
    def clear_all_timers(self):
        # Interate through all the timers in the internal array
        for timer_id__item in self.timer_id__list:
            #GLib.source_remove(self.timer_id__array[timer_id__item])
            # Remove the timer source from GLib
            GLib.source_remove(timer_id__item)
            # Remove the Timer ID from the list
            self.timer_id__list.remove(timer_id__item)
        # Clear/Re-Set the Timer Id Array
        #self.timer_id__array = {}

    # Internal Function for Clearing/Canceling a Single Timer - Identified via Timer ID
    def clear_single_timer(self, timer_id):
        # Ensure that the timer_id presented is known to the Adapter Class
        if timer_id not in self.timer_id__list:
            #print("[!] ERROR:\tTimer ID is Unknown to Adapter")
            output_log_string = "[!] ERROR:\tTimer ID is Unknown to Adapter"
            print_and_log(output_log_string)
            return False
        # Remove the Timer Source from GLib
        GLib.source_remove(timer_id)
        # Remove the Timer ID from the Timer ID Array
        self.timer_id__list.remove(timer_id)
        # Check if the Timer removed is the Last one seen
        if timer_id == self.timer_id__last:
            self.timer_id__last = None
        # Confirm everything got done
        return True

    ## Definitions for the callbacks
    # Notification Catch Test
    def notify_catch(*args):
        #print("[!] Notify Catch\t-\tArgs:\t{0}".format(args))
        output_log_string = "[!] Notify Catch\t-\tArgs:\t{0}".format(args)
        print_and_log(output_log_string)

    # Basic Error Callback
    def notify_error(error):
        #print("[!] Notify Error\t-\tError:\t{0}".format(error))
        output_log_string = "[!] Notify Error\t-\tError:\t{0}".format(error)
        print_and_log(output_log_string)

    # Function for Debugging Unknown Signal
    #   - Borrow from the debugging signal catching function
    def callback__signal__debugging_general(self):
        output_log_string = "[!] Unknown Signal Caught... Creating alert for debugging"
        print_and_log(output_log_string, LOG__DEBUG)
        pass

    # Function for Catching an Interface Added Signal
    def callback__signal__interface_added(self, path, interfaces):
        # Check that the interface is the expected Bluetooth Device Interface
        if not bluetooth_constants.DEVICE_INTERFACE in interfaces:
            return
        # Extract the Device Properties
        device_properties = interfaces[bluetooth_constants.DEVICE_INTERFACE]
        ## Examining the Device Properties for specifics
        # Create logging string for general logging
        dbus_signal__interface_added__details_string = "[*] Interfaces Removed Signal Caught\n\tDevice Path:\t{0}".format(path)
        # Iterate through received information
        if 'Address' in device_properties:
            dbus_signal__interface_added__details_string += "\n\tAddress:\t{0}".format(bluetooth_utils.dbus_to_python(device_properties['Address']))
        if 'Name' in device_properties:
            dbus_signal__interface_added__details_string += "\n\tDevice Name:\t{0}".format(bluetooth_utils.dbus_to_python(device_properties['Name']))
        if 'Alias' in device_properties:
            dbus_signal__interface_added__details_string += "\n\tDevice Alias:\t{0}".format(bluetooth_utils.dbus_to_python(device_properties['Alias']))
        if 'RSSI' in device_properties:
            dbus_signal__interface_added__details_string += "\n\tDevice RSSI:\t{0}".format(bluetooth_utils.dbus_to_python(device_properties['RSSI']))
        if 'TxPower' in device_properties:
            dbus_signal__interface_added__details_string += "\n\tTx Power:\t{0}".format(bluetooth_utils.dbus_to_python(device_properties['TxPower']))
        logging__log_event(LOG__GENERAL, dbus_signal__interface_added__details_string)
        if dbg != 0:
            #print(dbus_signal__interface_added__details_string)
            print_and_log(dbus_signal__interface_added__details_string, LOG__DEBUG)

    # Function for Catching an Interface Removed Signal
    def callback__signal__interface_removed(self, path, interfaces):
        # Check that the interface is the expected Bluetooth Device Interface
        if not bluetooth_constants.DEVICE_INTERFACE in interfaces:
            return
        # Extract the Device Properties
        device_properties = interfaces[bluetooth_constants.DEVICE_INTERFACE]
        ## Examining the Device Properties for specifics
        # Create logging string for general logging
        dbus_signal__interface_added__details_string = "[*] Interfaces Added Signal Caught\n\tDevice Path:\t{0}\n\tAddress:\t{1}\n\tDevice Name:\t{2}\nDevice RSSI:\t{3}".format(path, bluetooth_utils.dbus_to_python(device_properties['Address']), bluetooth_utils.dbus_to_python(device_properties['Name']), bluetooth_utils.dbus_to_python(device_properties['RSSI']))
        logging__log_event(LOG__GENERAL, dbus_signal__interface_added__details_string)
        if dbg != 0:
            #print(dbus_signal__interface_added__details_string)
            print_and_log(dbus_signal__interface_added__details_string, LOG__DEBUG)

    # Function for Catching a Bluez Device Properties Changed Signal
    def callback__signal__bluez__device__properties_changed(self, interface, changed, invalidated, path):
        # Check that the interface is the expected Bluetooth Device Interface
        if interface != bluetooth_constants.DEVICE_INTERFACE:
            return
        ## Examining the Changed Information
        dbus_signal__properties_changed__details_string = "[*] Properties Changed Signal Caught\n\tDevice Path:\t{0}".format(path)
        # Iterate through the changed properties; Note not all information might be present (all signals suffer from this?)
        for changed_property in changed.items():
            # Add the items to the string
            if 'Address' in changed_property:
                dbus_signal__properties_changed__details_string += "\n\tAddress:\t{0}".format(bluetooth_utils.dbus_to_python(changed.items()[changed_property]))
            if 'Name' in changed_property:
                dbus_signal__properties_changed__details_string += "\n\tDevice Name:\t{0}".format(bluetooth_utils.dbus_to_python(changed.items()[changed_property]))
            if 'RSSI' in changed_property:
                dbus_signal__properties_changed__details_string += "\n\tDevice RSSI:\t{0}".format(bluetooth_utils.dbus_to_python(changed.items()[changed_property]))
            if 'TxPower' in changed_property:
                dbus_signal__properties_changed__details_string += "\n\tTx Power:\t{0}".format(bluetooth_utils.dbus_to_python(changed.items()[changed_property]))
        # Add the information to the general log
        logging__log_event(LOG__GENERAL, dbus_signal__properties_changed__details_string)

    # Function for Catching a Bluez GATT Characteristic Properties Changed Signal
    #def callback__signal__bluez__gatt_characteristic__properties_changed(self, interface

    ## Definition of GLib MainLoop Functions
    # Internal Function for Adding Signal Receivers to the Class' D-Bus property
    def mainloop__configure__add_signal_receiver(self, callback_function, dbus_interface_to_watch, signal_to_catch):
        # Add the signal receiver to the Class' D-Bus
        self._bus.add_signal_receiver(callback_function, dbus_interface = dbus_interface_to_watch, signal_name = signal_to_catch)

    # Internal Function for Removing Signal Receivers from the Class' D-Bus property
    #   - Note: This requires knowing the name of the Callback Function and the Emittion Signal
    def mainloop__configure__remove_signal_receiver(self, callback_function, signal_receiving):
        # Remove the signal receiver to the Class' D-Bus
        self._bus.remove_signal_receiver(callback_function, signal_receiving)

    # Internal Function for adding a timeout to the Class' D-Bus property; Take in a timeout in milliseconds and a function to call once timesd out
    #   - TODO: [ ] Get timeout functionality working on this
    #       - Might need to add additional inputs to this function
    #def mainloop__configure__add_timeout(self, timeout_ms, callback_function, watched_interface):
    def mainloop__configure__add_timeout(self, timeout_ms, callback_function, mainloop):

        # Create a GLib MainLoop Object (cause it's needed?)
        #mainloop = GLib.MainLoop() ; Not needed since the function is being passed a GLib MainLoop object

        # Adding a timeout to the GLib MainLoop
        #timer_id = GLib.timeout_add(timeout_ms, callback_function)
        #self.timer_id__last = GLib.timeout_add(timeout_ms, callback_function, watched_interface, main_loop)
        self.timer_id__last = GLib.timeout_add(timeout_ms, callback_function, mainloop)           # Nota Bene: This version of the script runs endlessly and does not stop.... Requires human interaction (TODO: FIX THIS); BECAUSE mainloop.quit() does NOT get called in the callback function (??)

        # Track the Timer IDs
        # Add this timer to the larger array
        self.timer_id__list.append(self.timer_id__last)

    # Internal Function for removing a timeout from the Class' D-Bus
    def mainloop__configure__remove_timeout(self, timer_id):
        # Remove the Timer ID source from GLib
        self.clear_single_timer(timer_id)

    ## Definitions for Notification catching using GLib MainLoop
    # Internal Function for Adding the Signal Receiver to D-Bus to Capture Signals          [ MIXED FUNCTION THAT IS PERFORMING BASIC LISTENING + TRYING TO ACT AS THE CALLBACK FUNCTION + TIMER ]
    #   - Note: This function has the default assumption of looking for PropertiesChanged signals on the Properties D-Bus interface
    # => This might need to be the callback function? OR make a new (general?) function for forcing the Notification Listening to end
    #def mainloop__notifications__capture(self, notifying_interface, callback_function=debugging__dbus_signals__catchall, dbus_interface_to_watch=bluetooth_constants.DBUS_PROPERTIES, signal_to_catch="PropertiesChanged", listening_time__ms=5000):
    def mainloop__notifications__capture(self, callback_function, dbus_interface_to_watch=bluetooth_constants.DBUS_PROPERTIES, signal_to_catch="PropertiesChanged", listening_time__ms=5000):
        ## Setup the Notification Capture       <----- Configuration and setup of the interface
        # Setting the debugging D-Bus signal catcher as the callback for any "PropertiesChanged" signals incoming on the org.freedesktop.DBus.Properties interface
        #self._bus.add_signal_receiver(debugging__dbus_signals__catchall, dbus_interface = bluetooth_constants.DBUS_PROPERTIES, signal_name = "PropertiesChanged")
        #self._bus.add_signal_receiver(callback_function, dbus_interface = dbus_interface_to_watch, signal_name = signal_to_catch)
        if dbg != 0:
            #print("[?] Callback Function:\t{1}\nD-Bus Interface:\t{0}\nSignal To Catch:\t{2}\nTimeout:\t{3}".format(dbus_interface_to_watch, callback_function, signal_to_catch, listening_time__ms))
            output_log_string = "[?] Callback Function:\t{1}\nD-Bus Interface:\t{0}\nSignal To Catch:\t{2}\nTimeout:\t{3}".format(dbus_interface_to_watch, callback_function, signal_to_catch, listening_time__ms)
            print_and_log(output_log_string, LOG__DEBUG)
        self.mainloop__configure__add_signal_receiver(callback_function, dbus_interface_to_watch, signal_to_catch)

    # Internal Function for Adding the Signal Receiver for Interface Added Signal


    # Internal Function for Adding the Signal Receiver for Interface Removed Signal


    ## Definitions of Timed Signal Catching (DEFAULT USAGE OF THIS CLASS)
    # Function for timing out the notification signal catching
    #   - Note: This is the callback function that MUST be given when adding a timeout to signal catching
    def timer__signal_catch(self, mainloop):
        # Removing the GLib timeout; using the last timer added to GLib
        self.mainloop__configure__remove_timeout(self.timer_id__last)
        # Stop the mainloop
        mainloop.quit()
        # Notification Listening for Notifications is Done
        #print("[+] Emittion Listening Completed")
        output_log_string = "[+] Emittion Listening Completed"
        print_and_log(output_log_string)
        # Nota Bene: During testing this function was successfully shown to capture a SINGLE notification and then end

    # Function for running the actual capture of notification signals
    def run__signal_catch__timed(self, notifying_interface, callback_function, signal_to_catch="PropertiesChanged"):
        ## Configuration of the Interface
        # Add the information to the general log
        dbus__signal_catch__start_string = "[*] Starting D-Bus Signal Catching"
        logging__log_event(LOG__GENERAL, dbus__signal_catch__start_string)
        # Setup the notifications capture
        #self.mainloop__notifications__capture(self, notification_interface, callback_function, dbus_interface_to_watch=bluetooth_constants.DBUS_PROPERTIES, signal_to_catch="PropertiesChanged", listening_time__ms=5000)
        # Note: Passing the defaults to the function above; Note getting an error about "got multiple values for argument 'dbus_interface_to_watch'"
        #   - The issue is that because the 'dbus_interface_to_watch' variable is passed as "dbus_interface_to_watch=bluetooth_constants.DBUS_PROPERTIES" which means Python interprets this as a keyword where the other is being passed as a positional argument (in the definition)
        self.mainloop__notifications__capture(callback_function)
        # dbus_interface_to_watch=bluetooth_constants.DBUS_PROPERTIES, signal_to_catch="PropertiesChanged", listening_time__ms=5000)

        # Add the information to the general log
        dbus__signal_catch__start_notify = "[*] Starting Notifications for Interface"
        logging__log_event(LOG__GENERAL, dbus__signal_catch__start_notify)

        # Start the notification on the given characteristic; (Does NOT matter what order I do these actions in?)
        notifying_interface.StartNotify()

        # Add the information to the general log
        dbus__signal_catch__create_mainloop = "[*] Creating GLib MainLoop"
        logging__log_event(LOG__GENERAL, dbus__signal_catch__create_mainloop)

        # Create MainLoop GLib Object for use below
        mainloop = GLib.MainLoop()

        # Add the information to the general log
        dbus__signal_catch__adding_timeout = "[*] Adding Timeout to GLib MainLoop"
        logging__log_event(LOG__GENERAL, dbus__signal_catch__adding_timeout)

        # Add the Timer to GLib
        self.mainloop__configure__add_timeout(self.mainloop_run__default_time__ms, self.timer__signal_catch, mainloop)
        # Note the massing of the mainloop structure to the timeout callback function; hence needing to call this here within the function (after mainloop is defined)

        ## Running the MainLoop
        ## Running the MainLoop             <----- This MUST be in the MAIN TIMED FUNCTION; MOVE THIS AND ABOVE TO THE RUNNING TIMED LISTEN FUNCTION
        # Loop for listening on the D-Bus for Notify signals (e.g. "PropertiesChanged")
        try:
            if dbg != 1:        # ~!~
                #print("[*] Listening for Emittions...")
                output_log_string = "[*] Listening for Emittions..."
                print_and_log(output_log_string, LOG__DEBUG)
            # Add the information to the general log
            dbus__signal_catch__mainloop_start = "[*] Starting GLib MainLoop"
            logging__log_event(LOG__GENERAL, dbus__signal_catch__mainloop_start)
            mainloop.run()
        except KeyboardInterrupt:
            mainloop.quit()
            if dbg != 1:        # ~!~
                #print("[+] Done Listening")
                output_log_string = "[+] Done Listening"
                print_and_log(output_log_string, LOG__DEBUG)
            # Add the information to the general log
            dbus__signal_catch__mainloop_stop = "[+] GLib MainLoop Succsesfully Stopped"
            logging__log_event(LOG__GENERAL, dbus__signal_catch__mainloop_stop)
        # TODO: Turn the above into an internal function

        ## Left-over Clean-up

        # Add the information to the general log
        dbus__signal_catch__clean_up_start = "[*] Starting D-Bus Signal Catching Clean-up"
        logging__log_event(LOG__GENERAL, dbus__signal_catch__clean_up_start)

        ## Clean-up of Notification Capture     <---- This is the Callback function part that stops the process and clean's up; MOVE THIS TO THE CALLBACK FUNCTION
        # Stop the notification signals
        notifying_interface.StopNotify()

        # Add the information to the general log
        dbus__signal_catch__removing_signal_receiver = "[*] Removing D-Bus signal receiver"
        logging__log_event(LOG__GENERAL, dbus__signal_catch__removing_signal_receiver)

        # Removing the debugging D-Bus signal catcher
        self.mainloop__configure__remove_signal_receiver(callback_function, signal_to_catch)

        # Add the information to the general log
        dbus__signal_catch__end_string = "[+] Completed D-Bus Signal Catching"
        logging__log_event(LOG__GENERAL, dbus__signal_catch__end_string)

    ### Scratch Space for Emittion Catching with Threads

    ## Definitions for Internal GLib MainLoop Controls
    # Function for stopping a passed GLib MainLoop
    def stop_handler(self, mainloop):
        # End the mainloop
        mainloop.quit()

    # Debugging Function for GATT Characteristic Properties Changed Emittion Data
    #   - Note: The above function variables are chosen for selecting expected input & matching function call (e.g. add_signal_receiver)
    def debugging__dbus_signals__properties_changed(self, interface, changed, invalidated, path):
        # Check that the emittion signal is for GATT characteristic
        if interface != bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE:
            # If the interface is NOT a GATT Characteristic (i.e. "org.bluez.GattCharacteristic1") then do not care
            return
        # Clear and set the variable for the emittion value/data received
        value = []
        value = changed.get('Value')            # Note: Need to confirm that this works (or that the data passed via the "changed" variable would have this entry)
        # Check if 'value' variable got anything set to it
        if not value:
            #print("[+] Got Changed of:\t{0}\n\tType:\t{1}".format(changed.items(), type(changed.items())))
            output_log_string = "[+] Got Changed of:\t{0}\n\tType:\t{1}".format(changed.items(), type(changed.items()))
            print_and_log(output_log_string)
        else:
            #print("[+] Found 'Value' in Changed:\t{0}".format(value))
            output_log_string = "[+] Found 'Value' in Changed:\t{0}".format(value)
            print_and_log(output_log_string)
            if isinstance(value, dbus.Array):
                #print("\tASCii:\t{0}".format(convert__hex_to_ascii(bluetooth_utils.dbus_to_python(value))))
                output_log_string = "\tASCii:\t{0}".format(convert__hex_to_ascii(bluetooth_utils.dbus_to_python(value)))
                print_and_log(output_log_string)
        '''
        # Checking for a (global?) callback function
        if global_callback is not None:
            global_callback(path, value)
        else:
            print("[-] No (global?) callback function set")
        '''

    # Function to Configure & Start D-Bus + GLib MainLoop
    def start_notification(self, characteristic_interface):
        # Add signal receiver for "PropertiesChanged"
        self._bus.add_signal_receiver(self.debugging__dbus_signals__properties_changed,
                                      bus_name=bluetooth_constants.BLUEZ_SERVICE_NAME,
                                      dbus_interface=bluetooth_constants.DBUS_PROPERTIES,
                                      signal_name="PropertiesChanged",
                                      path_keyword="path")
        # Add signal receiver for "StopNotifications"
        self._bus.add_signal_receiver(self.stop_handler, "StopNotifications")
        # Start Notifications on the Passed Characteristic Interface
        characteristic_interface.StartNotify()
        # Create & Start the GLib MainLoop    user_device__internals_map = user_device.enumerate    user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
        #mainloop = GObject.MainLoop()
        mainloop = GLib.MainLoop()
        # Add a timeout (for max debug time; prevent hangups)
        self.mainloop__configure__add_timeout(self.mainloop_run__default_time__ms, self.timer__signal_catch, mainloop)      # <------- This appears to add a scenario where AFTER A SINGLE NOTIFICATION the MainLoop stops
        #   -> Note: with the above we notice the arguements are (1) time in milliseconds, (2) the callback function to make, and (3) the mainloop object
        # Run the mainloop()
        mainloop.run()                  #   <------ Thread is getting caught here due to (1) lack of a try statement to allow keyboard interrupt and (2) timeout NOT happening (since NOT backgrounding the thread?)
        # TODO: Confirm that the above command will work; especially within the this Class structure

    # Function to verify the passed Characteristic Interface is valid for Notification Emittion Capture
    def validate__dbus__gatt_characteristic(self, user_device_object, characteristic_name):
        # Variable for checking function
        passed = False
        # Check that the User Device Object is connected
        if not user_device_object.device_connected:
            raise bluetooth_exceptions.StateError(bluetooth_constants.RESULT_ERR_NOT_CONNECTED)
            return passed
        # Check that the services have been resolved
        if not user_device_object.find_and_get__device_property("ServicesResolved"):
            raise bluetooth_exceptions.StateError(bluetooth_constants.RESULT_ERR_SERVICES_NOT_RESOLVED)     # TODO: Fix this error reporting
            return passed
        # Step for Creating Characteristic Interfaces based on the provided 'characteristic_name'
        characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device_object.find_and_return__characteristic__gatt_inspection_set(characteristic_name)
        # Create array of Characteristic Flags
        characteristic_properties_array = user_device_object.find_and_get__all_characteristic_properties(characteristic_properties)
        characteristic_flags = user_device_object.grab__properties_array__value(characteristic_properties_array, 'Flags')
        # Check that Characteristic has both 'notify' & 'indicate'
        if not 'notify' in characteristic_flags and not 'indicate' in characteristic_flags:
            raise bluetooth_exceptions.UnsupportedError(bluetooth_constants.RESULT_ERR_NOT_SUPPORTED)
            return passed
        # Check if the Notify Service is already running
        #if characteristic_interface.Get(bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE, "Notifying") == True:
        if user_device_object.find_and_get__characteristic_property(characteristic_interface, "Notifying") == True:
            raise bluetooth_exceptions.StateError(bluetooth_constants.RESULT_ERR_WRONG_STATE)
            return passed
        # Checks cleared, so continue
        passed = True
        # Check that verification passed
        if not passed:
            return None
        else:
            return characteristic_properties, characteristic_interface
        #return passed

    # Function for Configuring & Running the Thread(s)
    def threads__configure_and_run(self, callback_function, characteristic_interface):
        #print("[*] D-Bus Signal::Thread Configure:\tConfiguring Thread")
        output_log_string = "[*] D-Bus Signal::Thread Configure:\tConfiguring Thread"
        print_and_log(output_log_string)
        # Configure the thread
        thread = threading.Thread(target=callback_function, args=(characteristic_interface, ))
        #print("[*] D-Bus Signal::Thread Configure:\tSet Thread Daemon")
        output_log_string = "[*] D-Bus Signal::Thread Configure:\tSet Thread Daemon"
        print_and_log(output_log_string)
        # Set the Thread
        thread.daemon = True
        #print("[*] D-Bus Signal::Thread Configure:\tStart Thread")
        output_log_string = "[*] D-Bus Signal::Thread Configure:\tStart Thread"
        print_and_log(output_log_string)
        # Run the Thread
        thread.run()
        out_log_string = "[*] D-Bus Signal::Thread Configure:\tFinished Thread Run"
        print_and_log(out_log_string)

    # Function to Act on Emittion Data Captured
    def emittion_catch(path, value):
        # Print what data was received
        #print("[*] Received Emittion from [ {0} ] of value [ {1} ]".format(path, value))
        output_log_string = "[*] Received Emittion from [ {0} ] of value [ {1} ]".format(path, value)
        print_and_log(output_log_string)
        # Do any other stuff
        #   - Ex:       Check paths wanting/expecting emittion and act is the 'path' correspond to one of these

    # Function for .... Verification Check to Stop the Characteristic Notification
    def validate__dbus__gatt_characteristic__pre_stop(self, user_device_object, characteristic_properties, characteristic_interface):
        # Variable for checking function
        passed = False
        # Check that the User Device Object is connected
        if not user_device_object.device_connected:
            raise bluetooth_exceptions.StateError(bluetooth_constants.RESULT_ERR_NOT_CONNECTED)
            return passed
        # Check that the services have been resolved
        if not user_device_object.find_and_get__device_property("ServicesResolved"):
            raise bluetooth_exceptions.StateError(bluetooth_constants.RESULT_ERR_SERVICES_NOT_RESOLVED)
            return passed
        # Create array of Characteristic Flags
        characteristic_properties_array = user_device_object.find_and_get__all_characteristic_properties(characteristic_properties)
        characteristic_flags = user_device_object.grab__properties_array__value(characteristic_properties_array, 'Flags')
        # Check that Characteristic has both 'notify' & 'indicate'
        if not 'notify' in characteristic_flags and not 'indicate' in characteristic_flags:
            raise bluetooth_exceptions.UnsupportedError(bluetooth_constants.RESULT_ERR_NOT_SUPPORTED)
            return passed
        # Check if the Notify Service is already running
        #if characteristic_interface.Get(bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE, "Notifying") == False:
        if user_device_object.find_and_get__characteristic_property(characteristic_interface, "Notifying") == False:
            raise bluetooth_exceptions.StateError(bluetooth_constants.RESULT_ERR_WRONG_STATE)
            return passed
        # Checks cleared, so continue
        passed = True
        # Check that verification passed
        return passed
    
    # Function for .... Stopping the Characteristic Notification
    def stop_notification(self, characteristic_interface):
        #print("[*] Stopping Notification")
        output_log_string = "[*] Stopping Notification"
        print_and_log(output_log_string)
        characteristic_interface.StopNotify()

    # Function for Testing the Above Notification + Threads + Callback outlined above in the scratch space
    def capture_and_act__emittion__gatt_characteristic(self, user_device_object, characteristic_name):
        # Determine what element (e.g. S/C/D) is desired to capture a notification from
        #   - Bonus:    Decide if emittion capture once or continuous

        # Perform requirement/error check on provided S/C/D + Generate the Characteristic Interface needed
        #   - Prepare required configuration and tracking structures
        #print("[*] Creating Characteristic Structures to Emittion Capture")
        output_log_string = "[*] Creating Characteristic Structures to Emittion Capture"
        print_and_log(output_log_string)
        characteristic_properties, characteristic_interface = self.validate__dbus__gatt_characteristic(user_device_object, characteristic_name)
        #sanity_check = self.validate__dbus__gatt_characteristic(user_device_object, characteristic_name)
        #if not sanity_check:
        #    print("[-] Characteristic [ {0} ] Failed Pre-Check".format(characteristic_name))
        #    return
        if characteristic_interface is None:
            #print("[-] No Characteristic Interface Generated for [ {0} ]".format(characteristic_name))
            output_log_string = "[-] No Characteristic Interface Generated for [ {0} ]".format(characteristic_name)
            print_and_log(output_log_string)
            return

        # Configure the Thread for notification capture
        #   - Include BOTH callback function and teardown process (e.g. disable notification, stop MainLoop)
        #print("[*] Configuring and running the Thread")
        output_log_string = "[*] Configuring and running the Thread"
        print_and_log(output_log_string)
        self.threads__configure_and_run(self.start_notification, characteristic_interface)       # Note: This call to the threads function will set the receivers, start notification, and run the MainLoop
        # Function below gets used how?? Gets called by the above function, which will pass the characteristic_interface to it as well 
        #start_notification(self, characteristic_interface):

        # Artifical Timing on the Notification Running/Being Captured
        #print("[*] Waiting 20 Seconds....\n\tStart:\t{0}".format(time.ctime()))
        output_log_string = "[*] Waiting 20 Seconds....\n\tStart:\t{0}".format(time.ctime())
        print_and_log(output_log_string)
        time.sleep(20)
        #print("\tEnd:\t{0}\n[+] Done waiting time".format(time.ctime()))
        output_log_string = "\tEnd:\t{0}\n[+] Done waiting time".format(time.ctime())
        print_and_log(output_log_string)

        # Stop the Notification on the Characteristic Interface
        #print("[*] Validating Characteristic to Stop Notification")
        output_log_string = "[*] Validating Characteristic to Stop Notification"
        print_and_log(output_log_string)
        self.validate__dbus__gatt_characteristic__pre_stop(user_device_object, characteristic_properties, characteristic_interface)
        #print("[*] Stopping Notification on the Characteristic Interface")
        output_log_string = "[*] Stopping Notification on the Characteristic Interface"
        print_and_log(output_log_string)
        self.stop_notification(characteristic_interface)

        # Chec/Verify that "Action" was perform with/using any received value
        ## TODO: Something....

    # Internal Function for Catching a Notification due to a Read; Note: This function can be passed a notifying_interface, a reading_interface, and a timeout
    def run__read_signal_catch__timed(self, notifying_interface, reading_interface, callback_function, signal_to_catch="PropertiesChanged"):
        out_log_string = "[*] Creating Signal Catch for Read Notification"
        print_and_log(out_log_string)

        # Configure the callback function for the Signals Class Object
        self.mainloop__notifications__capture(callback_function)

        # Create MainLoop GLib Object for use below
        mainloop = GLib.MainLoop()

        # Add the Timer to GLib
        self.mainloop__configure__add_timeout(self.mainloop_run__default_time__ms, self.timer__signal_catch, mainloop)
        # Note the massing of the mainloop structure to the timeout callback function; hence needing to call this here within the function (after mainloop is defined)

        # Turn on Notifications
        notifying_interface.StartNotify()

        # Perform Read Operation
        reading_interface.ReadValue({})

        # Run MainLoop
        # Loop for listening on the D-Bus for Notify signals (e.g. "PropertiesChanged")
        try:
            # Add the information to the general log
            mainloop.run()
        except KeyboardInterrupt:
            mainloop.quit()
            dbus__signal_catch__mainloop_stop = "[+] GLib MainLoop Succsesfully Stopped"
            logging__log_event(LOG__GENERAL, dbus__signal_catch__mainloop_stop)
        # WORKS! Does a read and captures the return notification.  Limited to the debugging log

    # Internal Function for Catching a Notification due to a Write; Note: This function can be passed a notifying_interface, a writing_interface, and a timeou
    def run__write_signal_catch__timed(self, notifying_interface, writing_interface, callback_function, signal_to_catch="PropertiesChanged"):
        out_log_string = "[*] Creating Signal Catch for Write Notification"
        print_and_log(out_log_string)
        # Configuring Variables for testing
        #write_value = [ 0x88, 0x88, 0x88 ]      # XXX
        #write_value = dbus.Array([dbus.Byte(72), dbus.Byte(101), dbus.Byte(108), dbus.Byte(108), dbus.Byte(111)])
        #write_value = 136
        #write_value = [ 0x47, 0x65, 0x6E, 0x65, 0x72, 0x61, 0x6C, 0x20, 0x4B, 0x65, 0x6E, 0x6F, 0x62, 0x69, 0x21 ]
        write_value = [ 71, 101, 110, 101, 114, 97, 108, 32, 75, 101, 110, 111, 98, 105, 33 ]       # General Kenobi!
        dict_options = {}

        # Configure the callback function for the Signals Class Object
        self.mainloop__notifications__capture(callback_function)

        # Create MainLoop GLib Object for use below
        mainloop = GLib.MainLoop()

        # Add the Timer to GLib
        self.mainloop__configure__add_timeout(self.mainloop_run__default_time__ms, self.timer__signal_catch, mainloop)
        # Note the massing of the mainloop structure to the timeout callback function; hence needing to call this here within the function (after mainloop is defined)

        # Turon on Notifications
        notifying_interface.StartNotify()

        # Performing Variations of Write Options
        write_type_flag = 0
        if write_type_flag != 0:
            # Command type write
            if write_type_flag == 1:
                dict_options = {'type': "command"}
            elif write_type_flag == 2:
                dict_options = {'type': "request"}
            elif write_type_flag == 3:
                dict_options = {'type': "reliable"}
        else:               # Basic, no options, write; known to work
            dict_options = {}

        # Perform Write Operation
        #writing_interface.WriteValue([write_value], dict_options)       # Note: Fix to make writes based on data provided
        writing_interface.WriteValue(write_value, dict_options)

        # Run MainLoop
        # Loop for listening on the D-Bus for Notify signals (e.g. "PropertiesChanged")
        try:
            # Add the information to the general log
            mainloop.run()
        except KeyboardInterrupt:
            mainloop.quit()
            dbus__signal_catch__mainloop_stop = "[+] GLib MainLoop Succsesfully Stopped"
            logging__log_event(LOG__GENERAL, dbus__signal_catch__mainloop_stop)

# Device Object + Interface for Bluetooth Low Energy    -   Used to Interact with a Device, Determine the Device Properties, and Introspect the ``Lower Level'' Properties (i.e. Services, Characteristics, and Descriptors)
#   - Note: Added in functionality to change the HCI adapter
class system_dbus__bluez_device__low_energy:
    '''
    Entry point for creating, using, and interacting with a device via the system's D-Bus interfaces

    This class is intended to be used for the purpose of interacting with Bluetooth Low Energy (BLE) devices for connection + enumeration + interaction
    '''

    # Initialization Function
    def __init__(self, ble_device_address, bluetooth_adpater=bluetooth_constants.ADAPTER_NAME):
        # Note: Adding the '_' in front seems to work the same as the '.' in a linux directory
        self._bus = dbus.SystemBus()
        #self.device_address = ble_device_address
        # Create the full device path for setting to the class variable
        ble_device_path = bluetooth_utils.device_address_to_path(ble_device_address, bluetooth_constants.BLUEZ_NAMESPACE + bluetooth_constants.ADAPTER_NAME)
        # Path, Object, Interface, Properties, and Introspection for the Device
        self.device_path = ble_device_path
        self.device_object = None
        self.device_interface = None
        self.device_properties = None
        self.device_introspection = None
        # Properties related to the Device
        self.device_address = ble_device_address    #None                  # Note: Later on this should match the ble_device_address passed
        self.device_address_type = None
        self.device_name = None
        self.device_alias = None
        self.device_connected = None
        self.device_paired = None
        self.device_trusted = None
        self.device_bonded = None
        self.device_blocked = None
        self.device_legacy_pairing = None
        self.device_uuids = None
        self.device_service_data = None
        self.device_services_resolved = None        # Note: This property is useful for determining if a 'scan' of a device has completed with the Linux D-Bus
        self.manufacturer_data = None               # First seen in the wild with the information:  {dbus.UInt16(76): [16, 5, 35, 24, 102, 3, 129]};    # Manufacturer data strings; propriatary
        self.appearance = None                      # First seen in the wild with the information:  Value:  640
        self.icon = None                            # First seen in the wild with the information:  Value:  multimedia-player
        self.device_class = None
        self.wake_allowed = None
        self.modalias = None
        self.rssi = None
        self.tx_power = None
        self.advertising_flags = None
        self.advertising_data = None
        self.sets = None
        # Internal variable for determining auto re-scanning for devices
        self.rescan_flag = None
        # Internal variable for tracking errors within Class functionality (dirty but functional)
        self.error_buffer = None
        # Varibales Related to Signal Capture
        self.signal_thread = None

    # Internal Function for Handling Errors
    #   - Note: On 2023/12/11 looked into having the error handler return values to simplify error troubleshooting?
    #   - Note: On 2024/11/08 figured out that exception_e.args returns a tuple...
    def understand_and_handle__dbus_errors(self, exception_e):
        # Internals for error matching
        method_call_interface_error = "Method \"(.+?)\" with signature \"(.+?)\" on interface \"(.+?)\" doesn\'t exist"
        # Giant if statement determining what the error is and what the source of the error may be
        if dbg != 0:
            output_log_string = "[!] Starting understand_and_handle__dbus_errors()\n\tError:\t{0}".format(exception_e)
            print_and_log(output_log_string)
        #if exception_e == DBusException:
            # Something
            #print("[!] Error: May need to Connect to the Device first?\n\t{0}".format(exception_e))
        if exception_e == AttributeError:
            # Attribute Error Condition
            #print("[!] Error: May not have setup a D-Bus interface being used?\n\t{0}".format(exception_e))
            output_log_string = "[!] Error: May not have setup a D-Bus interface being used?\n\t{0}".format(exception_e)
            print_and_log(output_log_string, LOG__DEBUG)
        # TypeError Handling
        elif exception_e == TypeError:
            out_log_string = "[!] Error: TypeError thrown during tool operation\n\t{0}".format(exception_e)
            print_and_log(output_log_string, LOG__DEBUG)
        elif isinstance(exception_e, dbus.exceptions.DBusException):         ## Does not seem to work
            # Some form of DBusException
            if dbg != 0:
                #print("[!] Error: D-Bus error has occured!\n\t{0}".format(exception_e))
                output_log_string = "[!] Error: D-Bus error has occured!\n\t{0}".format(exception_e)
                print_and_log(output_log_string, LOG__DEBUG)
                #raise RuntimeError(exception_e.get_dbus_message())
            method_call_error_match = re.search(method_call_interface_error, exception_e.args[0])
            #method_call_error_match = re.search(r"Method \"(.+?)\" with signature \"(.+?)\" on interface \"(.+?)\" doesn\'t exist")
            #method_call_error_match = re.search("Method \"(.+?)\" with signature \"(.+?)\" on interface \"(.+?)\" doesn\'t exist")
            # org.freedesktop.DBus.Error.UnknownObject
            if method_call_error_match:
                method_name = method_call_error_match.group(1)
                method_signature = method_call_error_match.group(2)
                interface_name = method_call_error_match.group(3)
                out_log_string = "[!] Error: Method [ {0} ] with Signature [ {1} ] caused an issues when called from interface [ {2} ]".format(method_name, method_signature, interface_name)
                print_and_log(out_log_string, LOG__DEBUG)
                # Attempt to add a return value
                return bluetooth_constants.RESULT_ERR_METHOD_CALL_FAIL
            else:
                out_log_string = "[!] Error Not Related to Method Call Error"
                print_and_log(out_log_string, LOG__DEBUG)
            #if "NotPermitted" in exception_e.args:
            # Read not permitted error
            #if "Read not permitted" in exception_e.args:
            #    # Not Permitted Error Condition
            #    #print("[!] Error: May not have permission for R/W; perhaps need more than just connection to device? OR the 'read' capability does not exist at the target\n\t{0}".format(exception_e))
            #    output_log_string = "[!] Error: May not have permission for R/W; perhaps need more than just connection to device? OR the 'read' capability does not exist at the target\n\t{0}".format(exception_e)
            #    print_and_log(output_log_string)
            #    # Return Read Not Permitted Error
            #    return bluetooth_constants.RESULT_ERR_READ_NOT_PERMITTED
                # org.bluez.Error.NotPermitted
                if exception_e.get_dbus_name() == 'org.bluez.Error.NotPermitted':
                    # Error of Not Permitted
                    output_log_string = "[!] Error: May not have permission for R/W; perhaps need more than just connection to device? OR the 'read' capability does not exist at the target\n\t{0}".format(exception_e)
                    print_and_log(output_log_string)
                    # Return Read Not Permitted Error
                    return bluetooth_constants.RESULT_ERR_READ_NOT_PERMITTED
                #elif "InvalidAgruments" in exception_e.args:
                # Invalid offset exception
                elif "Invalid offset" in exception_e.args[0]:
                    # Invalid Arguments Error Condition
                    #print("[!] Error: May have incorrectly passed R/W variables? (e.g. invalid offset)\n\t{0}".format(exception_e))
                    output_log_string = "[!] Error: May have incorrectly passed R/W variables? (e.g. invalid offset)\n\t{0}".format(exception_e)
                    print_and_log(output_log_string)
                # ATT Error     | TODO: Figure out why this branch does NOT trigger
                elif "ATT error:" in exception_e.args[0]:
                    # ATT error
                    if "0x0e" in exception_e.args:
                        # Unlikely Error; maybe a Write Response from earlier bluez version (i.e. 5.50) Write with Response?; OR Host Rejected due to security reasons; e.g. The host at the remote side has rejected the connection because the remote host determined that the local host did not meet its security criteria.
                        #print("[!] Error: May be an incorreclty understood Write with Response or an Unlikely Error or Host Rejected Due to Security Reasons\n\t{0}".format(exception_e))
                        output_log_string = "[!] Error: May be an incorreclty understood Write with Response or an Unlikely Error or Host Rejected Due to Security Reasons\n\t{0}".format(exception_e)
                        print_and_log(output_log_string)
                    else:
                        output_log_string = "[!] Unrecognized ATT error seen\n\t{0}".format(exception_e)
                        print_and_log(output_log_string)
                elif "Operation failed with ATT error" in exception_e.args[0]:     # Second attempt at catching the "ATT error" error
                    print("[!!!!!!] ATT ERROR YO!")
                # Not connected error
                #elif "Not connected" in exception_e.args:
                #    # Error of not connected to target (?)
                #    #print("[!] error: may not be connected to the target device\n\t{0}".format(exception_e))
                #    output_log_string = "[!] Error: may not be connected to the target device\n\t{0}".format(exception_e)
                #    print_and_log(output_log_string, LOG__DEBUG)
                #    # Return code for not being connected
                #    return bluetooth_constants.RESULT_ERR_NOT_CONNECTED
                # org.freedesktop.DBus.Error.NoReply
                #elif "Did not receive a reply" in exception_e.args:
                elif (exception_e.get_dbus_name() == 'org.freedesktop.DBus.Error.NoReply'):
                    # Error of NoReply from the taret
                    output_log_string = "[!] Error: No Reply received from target\n\t{0}".format(exception_e)
                    print_and_log(output_log_string)
                    # Return code for not being connected
                    return bluetooth_constants.RESULT_ERR_NO_REPLY
                # org.freedesktop.DBus.Error.UnknownObject
                elif "Method \"GetAll\" with signature \"s\"" in exception_e.args[0]:
                    # Error of an Unknown Object call
                    output_log_string = "[!] Error: Method x with signature y error received, device may no longer be within range\n\t{0}".format(exception_e)
                    print_and_log(output_log_string)
                    # Attempt to add a return value
                    return bluetooth_constants.RESULT_ERR_NOT_FOUND
                # org.bluez.Error.InProgress
                #elif "In Progress" in exception_e.args:
                #    # Error of In Progress
                #    output_log_string = "[!] Error: In Progress error received\n\t{0}".format(exception_e)
                #    print_and_log(output_log_string)
                #    return bluetooth_constants.RESULT_ERR_ACTION_IN_PROGRESS
                # org.freedesktop.DBus.Error.ServiceUnknown
                #elif "was not provided by any .service files" in exception_e.args:
                elif (exception_e.get_dbus_name() == 'org.freedesktop.DBus.Error.ServiceUnknown'):
                    # Error of ServiceUnknown
                    output_log_string = "[!] Error: Unknown Service name provided\n\t{0}".format(exception_e)
                    print_and_log(output_log_string)
                    return bluetooth_constants.RESULT_ERR_UNKNOWN_SERVCE
                ## Improved error handling filter
                # Third attempt to catch the ATT Error
                elif exception_e.get_dbus_name() == 'org.bluez.Error.Failed':
                    if "ATT error" in exception_e.args:
                        print("[!!! !!!] ATT ERROR TIMEZ!")
                    elif "Not connected" in exception_e.args:
                        # Error of not connected to target (?)
                        #print("[!] error: may not be connected to the target device\n\t{0}".format(exception_e))
                        output_log_string = "[!] Error: may not be connected to the target device\n\t{0}".format(exception_e)
                        print_and_log(output_log_string, LOG__DEBUG)
                        # Return code for not being connected
                        return bluetooth_constants.RESULT_ERR_NOT_CONNECTED
                    elif "le-connection-abort-by-local" in exception_e.args[0]:
                        # TODO: Determine if the "local" in this scope is the device being connected to OR the entity trying to connect
                        #output_log_string = "[-] Device [ {0} ] does not allow low energy connections (?? Might be a local machine issue ??)".format(target_bt_addr)
                        #output_log_string = "[-] Device [ {0} ] has terminated the connection".format(target_bt_addr)   # NOTE: Status: Remote User Terminated Connection (0x13);   Unknown device flag (0x00000008)
                        output_log_string = "[!] Error: Target Device has terminated the connection remotely\n\t{0}".format(exception_e)
                        #print_and_log(output_log_string)
                        print_and_log(output_log_string, LOG__DEBUG)
                        return bluetooth_constants.RESULT_ERR_REMOTE_DISCONNECT
                    else:
                        output_log_string = "[!] Error: Unknown Error has Occured when Attempting a Connection"
                        print_and_log(output_log_string, LOG__DEBUG)
                        return bluetooth_constants.RESULT_ERR_UNKNOWN_CONNECT_FAILURE
                elif exception_e.get_dbus_name() == 'org.bluez.Error.InProgress':
                    # Error of In Progress
                    output_log_string = "[!] Error: In Progress error received\n\t{0}".format(exception_e)
                    print_and_log(output_log_string)
                    # Perform a forced wait 
                    time.sleep(timewait_in_progress)       # Force a sleep of 200 milliseconds
                    return bluetooth_constants.RESULT_ERR_ACTION_IN_PROGRESS
                # org.freedesktop.DBus.Error.UnknownObject
                elif exception_e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownObject':
                    # org.freedesktop.DBus.Error.UnknownObject; TODO: Add signature recognition checking
                    if "Method \"GetAll\" with signature \"s\"" in exception_e.args[0]:
                        # Error of an Unknown Object call
                        output_log_string = "[!] Error: Method x with signature y error received, device may no longer be within range\n\t{0}".format(exception_e)
                        print_and_log(output_log_string)
                        # Attempt to add a return value
                        return bluetooth_constants.RESULT_ERR_NOT_FOUND
                    else:
                        output_log_string = "[!] Error: Unknown UnknownObject error occured\n\t{0}".format(exception_e)
                        output_log_string += "\n\tType:\t{0}\n\tArgs:\t{1}\n\tD-Bus Message:\t{2}".format(exception_e, exception_e.args, exception_e.get_dbus_message())
                        print_and_log(output_log_string)
                        #search_string = "Method \"GetAll\" with signature \"s\""
                        search_string = "Method \"Get\" with signature \"ss\""
                        test_arg = exception_e.args[0].strip()
                        test_value = search_string in test_arg
                        output_log_string = "[!] Test: See if string [ {0} ] exists in the args [ {1} ] with response [ {2} ]".format(search_string, test_arg, test_value)
                        # NOTE: Above works, now TODO: Figure out how to use regex to search for specific match groups for matching method, signature, and interface for debugging feedback
                        #output_log_string += "\n\tType of Search String:\t[ {0} ]\n\tType of Test Arg:\t[ {1} ]".format(type(search_string), type(test_arg))
                        print_and_log(output_log_string)
                else:
                    # Unknown D-Bus Error
                    print("[!] understand_and_handle__dbus_errors::Error: D-Bus error\t-\t{0}".format(exception_e))
                    print("\tType:\t{0}".format(exception_e))
                    print("\tArgs:\t{0}".format(exception_e.args))
                    print("\tD-Bus Message:\t{0}".format(exception_e.get_dbus_message()))
                    return bluetooth_constants.RESULT_ERR
            # ALWAYS Write the detailed information to the debugging log; NOTE: This will produce a double output of the error
            output_log_string = "[!] Error: D-Bus error\t-\t{0}\n\tType:\t{1}\n\tArgs:\t{2}\n\tD-Bus Message:\t{3}".format(exception_e, exception_e, exception_e.args, exception_e.get_dbus_message())
            print_and_log(output_log_string, LOG__DEBUG)
        else:
            print("[!] Error:\tUnknown Error\t-\t{0}".format(exception_e))
            if dbg != 1:
                print(exception_e.get_dbus_message())
                print(type(exception_e))
                print(exception_e.args)
                print(exception_e)

    # Internal Function for Acting On / Fixing Known Errors based on Device Class Object Error Buffer
    def perform__fix_error(self):
        out_log_string = "[*] BLE Class::perform__fix_error::Attempting to Perform Fix(es) due to Device Class Object Error Buffer"
        print_and_log(out_log_string, LOG__DEBUG)
        ## Perform action based on Error Buffer value
        # Check if Error Action Requires Reconnect_Check()
        if self.error_buffer in {bluetooth_constants.RESULT_ERR_NOT_CONNECTED, bluetooth_constants.RESULT_ERR_SERVICES_NOT_RESOLVED, bluetooth_constants.RESULT_ERR_NO_DEVICES_FOUND, bluetooth_constants.RESULT_ERR_NO_REPLY, bluetooth_constants.RESULT_ERR_DEVICE_FORGOTTEN, bluetooth_constants.RESULT_ERR_REMOTE_DISCONNECT}:
            out_log_string = "[*] BLE Class::perform__fix_error::Error requires Reconnection Check"
            print_and_log(out_log_string, LOG__DEBUG)
            # Perform Device Reconnection
            self.Reconnect_Check()
            out_log_string = "[*] BLE Class::perform__fix_error::Reconnection Check Completed"
            print_and_log(out_log_string, LOG__DEBUG)
        elif self.error_buffer in {bluetooth_constants.RESULT_ERR_UNKNOWN_SERVCE, bluetooth_constants.RESULT_ERR_UNKNOWN_OBJECT}:
            out_log_string = "[*] BLE Class::perform__fix_error::Error requires Refindings the Device and Connecting"
            print_and_log(out_log_string, LOG__DEBUG)
            # Perform Device Refind and Connect action
        elif self.error_buffer in {bluetooth_constants.RESULT_ERR_ACTION_IN_PROGRESS}:
            out_log_string = "[*] BLE Class::perform__fix_error::Error require timewait for action in progress"
            print_and_log(out_log_string, LOG__DEBUG)
            # Wait some set amount of time
            time.sleep(timewait_in_progress)
            out_log_string = "[*] BLE Class::perform__fix_error::Completed Time Wait of [ {0} ] seconds".format(timewait_in_progress)
            print_and_log(out_log_string, LOG__DEBUG)
        elif self.error_buffer in {bluetooth_constants.RESULT_ERR_READ_NOT_PERMITTED}:
            out_log_string = "[*] BLE Class::perform__fix_error::Error due to lack of permission"
            print_and_log(out_log_string, LOG__DEBUG)
        elif self.error_buffer is None:
            out_log_string = "[*] BLE Class::No Error Present"
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            out_log_string = "[*] BLE Class::perform__fix_error::Error of Unknown Type and Solution Happened\t-\t[ {0} ]".format(self.error_buffer)
            print_and_log(out_log_string, LOG__DEBUG)
        # Assume error handled ??
        #self.reset__error_buffer()


    # Internal Function for Creating and Setting the Device Object relating to the BLE Device Path
    def create_and_set__device_object(self):
        # Create the device object
        ble_device_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, self.device_path)
        # Set the device object to the internal class variable
        self.device_object = ble_device_object

    # Internal Function for Creating and Setting the Device Interface relating to the Device Object
    def create_and_set__device_interface(self):
        # Check that the Device Object exists (is it None?)
        if not self.device_object:
            out_log_string = "[!] create_and_set__device_interface::Attempting to Create and Set the Device Object"
            print_and_log(out_log_string, LOG__DEBUG)
            # Create the Device Object and set it before continuing
            self.create_and_set__device_object()
        # Continue with the creation and setting of the Device Interface
        self.device_interface = dbus.Interface(self.device_object, bluetooth_constants.DEVICE_INTERFACE)

    # Internal Function for Creating and Setting the Device Properties relating to the Device Object
    def create_and_set__device_properties(self):
        # Check that the Device Object exists (is it None?)
        if not self.device_object:
            # Create the Device Object and set it before continuing
            self.create_and_set__device_object()
        # Continue with the creation and setting of the Device Properties
        self.device_properties = dbus.Interface(self.device_object, bluetooth_constants.DBUS_PROPERTIES)

    # Internal Function for Creating and Setting the Device Introspection relating to the Device Interface
    ##  - NOTE: This will provide a 'snapshot in time' of the Bluetooth Low Energy GATT Device Interface; Does NOT handle the need to double-read some properties
    def create_and_set__device_introspection(self):
        # Check that the Device Interface exist (is it None?)
        if not self.device_interface:
            out_log_string = "[!] create_and_set__device_introspection::Attempting to Create and Set the Device Interface"
            print_and_log(out_log_string, LOG__DEBUG)
            # Create the Device Interface and set it before continuing
            self.create_and_set__device_interface()
        # Continue with the creation and setting of the Device Introspection
        self.device_introspection = self.device_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)

    # Internal Function for Creating and Returning a set of GATT Service Object, Interface, Properties, and Introspection
    def create_and_return__service__gatt_inspection_set(self, service_name):
        # Create the variables to be used
        service_path = self.device_path + "/" + service_name
        # Create the various parts of the next level GATT Service
        service_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, service_path)
        service_interface = dbus.Interface(service_object, bluetooth_constants.GATT_SERVICE_INTERFACE)
        service_properties = dbus.Interface(service_object, bluetooth_constants.DBUS_PROPERTIES)
        service_properties_array = bluetooth_utils.dbus_to_python(service_properties.GetAll(bluetooth_constants.GATT_SERVICE_INTERFACE))
        service_introspection = service_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        # Return the set of GATT parts
        return service_path, service_object, service_interface, service_properties, service_introspection

    # Internal Function for Creating and Returning a set of GATT Characteristic Object, Interface, Properties, and Introspection
    def create_and_return__characteristic__gatt_inspection_set(self, service_path, characteristic_name):
        # Create the variables to be used
        characteristic_path = service_path + "/" + characteristic_name
        # Create the various parts of the next level GATT Characteristic
        characteristic_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, characteristic_path)
        characteristic_interface = dbus.Interface(characteristic_object, bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE)
        characteristic_properties = dbus.Interface(characteristic_object, bluetooth_constants.DBUS_PROPERTIES)
        characteristic_properties_array = bluetooth_utils.dbus_to_python(characteristic_properties.GetAll(bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE))
        characteristic_introspection = characteristic_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        # Return the set of GATT parts
        return characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection

    # Internal Function for Creating and Returning a set of GATT Descriptor Object, Interface, Properties, and Introspection
    def create_and_return__descriptor__gatt_inspection_set(self, characteristic_path, descriptor_name):
        # Create the variables to be used
        descriptor_path = characteristic_path + "/" + descriptor_name
        # Create the various parts of the next level GATT Descriptor
        descriptor_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, descriptor_path)
        descriptor_interface = dbus.Interface(descriptor_object, bluetooth_constants.GATT_DESCRIPTOR_INTERFACE)
        descriptor_properties = dbus.Interface(descriptor_object, bluetooth_constants.DBUS_PROPERTIES)
        try:
            descriptor_properties_array = bluetooth_utils.dbus_to_python(descriptor_properties.GetAll(bluetooth_constants.GATT_DESCRIPTOR_INTERFACE))       # Do not need this?  Since this call won't work?
            # Get Error:    org.freedesktop.DBus.Error.UnknownMethod: Method "ReadValue" with signature "s" on interface "org.freedesktop.DBus.Properties" doesn't exist
        except Exception as e:
            #print("[-] Unable to make call to GetAll() for a descriptor [ {0} ]".format(descriptor_path))
            output_log_string = "[-] Unable to make call to GetAll() for a descriptor [ {0} ]".format(descriptor_path)
            print_and_log(output_log_string)
            self.understand_and_handle__dbus_errors(e)
        # Get Error:    dbus.exceptions.DBusException: org.freedesktop.DBus.Error.UnknownObject: Method "GetAll" with signature "s" on interface "org.freedesktop.DBus.Properties" doesn't exist
        #   [ ] Test if able to make call for GetAll() for a descriptor     <---- Not sure that this works.... Due to being a descriptor? 
        # Solution: ONLY request the following properties from the org.bluez.GattDescriptor1; .Characteristic, .UUID, .Value
        #   -> Goal: Attempt to make a call to the .ReadValue() method function for the org.bluez.GattDescriptor1 object; as this MIGHT update the value (TODO)
        '''
        print("[!] Attempting to call .ReadValue() method function for the org.bluez.GattDescriptor1 object")
        try:
            descriptor_read_attempt = bluetooth_utils.dbus_to_python(descriptor_properties.ReadValue(bluetooth_constants.GATT_DESCRIPTOR_INTERFACE))
            print("[+] Able to make call to .ReadValue() method for a descriptor!")
        except Exception as e:
            print("[-] Unable to make call to .ReadValue() method for a descriptor [ {0} ]".format(descriptor_path))
            self.understand_and_handle__dbus_errors(e)
        '''
        # Note: There is no introspection for descriptors   <--- WRONG!?! TODO: Add descriptor_introspection
        descriptor_introspection = descriptor_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        #descriptor_
        '''
        print("[!] Testing interaction with a descriptor object\t-\tReadValue();\tNote: Form is 'array{byte} ReadValue(dict options)'")
        try:
            descriptor_interface.ReadValue({})                                  # Note: Form is 'array{byte} ReadValue(dict options)', only for characteristic; for descriptor it is 'dict flags'
            print("[+] Called ReadValue() with {} empty dicttionary of flags")
            # Attempt re-read of value property?
        except Exception as e:
            print("[-] Unable to make call to ReadValue() for a descriptor [ {0} ]".format(descriptor_path))
            self.understand_and_handle__dbus_errors(e)
        ## NOTE: The process for the above is: (1) sucessful read request, (2) notification/indication received, (3) PropertiesChanged emitted
        #   - Check the Flags property to see what limitations/functionality is set
        #   -> Potential Flags are: "read", "write", "encrypt-read", "encrypt-write", "encrypt-authenticated-read", "encrypt-authenticated-write", "secure-read" (Server Only), "secure-write" (Server Only), "authorize"
        '''
        # Return the set of GATT parts
        return descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection

    # Internal Function for Creating and Returning a set of Media Control Object, Interface, Properties, and Introspection
    def create_and_return__control__media_inspection_set(self):
        # Media Control Interface interfaces
        ## Enumerating the Media Control Interface [ depreciated interface ]
        # Test Searching into the Media Control Interface (org.bluez.MediaControl1); NOTE: Depreciated functionality as of 2025/05/01
        media_control_path = self.device_path        # Note that from the MediaControl1 documentation, one knows that the path ends with "dev_XX_XX_XX_XX_XX_XX"
        media_control_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, media_control_path)
        media_control_interface = dbus.Interface(media_control_object, bluetooth_constants.MEDIA_CONTROL_INTERFACE)      # Note change of interface to be medial control interface
        media_control_properties = dbus.Interface(media_control_object, bluetooth_constants.DBUS_PROPERTIES)
        media_control_properties_array = bluetooth_utils.dbus_to_python(media_control_properties.GetAll(bluetooth_constants.MEDIA_CONTROL_INTERFACE))
        media_control_introspection = media_control_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        # Return the set of Media Control parts
        return media_control_path, media_control_object, media_control_interface, media_control_properties, media_control_introspection

    # Internal Function for Creating and Returning a set of Media Endpoint Object, Interface, Properties, and Introspection
    def create_and_return__endpoint__media_inspection_set(self, sep_name):
        # Media Endpoint Interface interfaces
        # Searching into the Media Endpoint Interface (org.bluez.MediaEndpoint1)
        media_endpoint_path = self.device_path + "/" + sep_name        # Note that from the MediaEndpoint1 documentation, one knows that the path ends with "dev_XX_XX_XX_XX_XX_XX/sepX"
        media_endpoint_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, media_endpoint_path)
        media_endpoint_interface = dbus.Interface(media_endpoint_object, bluetooth_constants.MEDIA_ENDPOINT_INTERFACE)      # Note change of interface to be medial endpoint interface
        media_endpoint_properties = dbus.Interface(media_endpoint_object, bluetooth_constants.DBUS_PROPERTIES)
        media_endpoint_properties_array = bluetooth_utils.dbus_to_python(media_endpoint_properties.GetAll(bluetooth_constants.MEDIA_ENDPOINT_INTERFACE))
        media_endpoint_introspection = media_endpoint_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        # Return the set of Media Endpoint parts
        return media_endpoint_path, media_endpoint_object, media_endpoint_interface, media_endpoint_properties, media_endpoint_introspection

    # Internal Function for Creating and Returning a set of Media Transport Object, Interface, Properties, and Introspection
    def create_and_return__transport__media_inspection_set(self, sep_name, fd_name):
        # Media Transport Interface interfaces
        # Searching into the Media Endpoint Interface (org.bluez.MediaEndpoint1)
        if not sep_name:
            media_transport_path = self.device_path + "/" + fd_name
        else:
            media_transport_path = self.device_path + "/" + sep_name + "/" + fd_name       # Note that from the MediaTransport1 documentation, one knows that the path ends with "dev_XX_XX_XX_XX_XX_XX/fdX" HOWEVER in the wild seen as "dev_XX_XX_XX_XX_XX_XX/sepX/fdX"
        media_transport_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, media_transport_path)
        media_transport_interface = dbus.Interface(media_transport_object, bluetooth_constants.MEDIA_TRANSPORT_INTERFACE)      # Note change of interface to be medial transport interface
        media_transport_properties = dbus.Interface(media_transport_object, bluetooth_constants.DBUS_PROPERTIES)
        media_transport_properties_array = bluetooth_utils.dbus_to_python(media_transport_properties.GetAll(bluetooth_constants.MEDIA_TRANSPORT_INTERFACE))
        media_transport_introspection = media_transport_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        # Return the set of Media Endpoint parts
        return media_transport_path, media_transport_object, media_transport_interface, media_transport_properties, media_transport_introspection

    # Internal Function for Createing and Returning a set of Player Object, Interface, Properties, and Introspection
    def create_and_return__player__media_inspection_set(self, player_name):
        # Media Player Interface interfaces
        # Searching into the Media Player Interface (org.bluez.MediaPlayer1)
        media_player_path = self.device_path + "/" + player_name        # Note that from the MediaPlayer1 documentation, one knows that the path ends with "dev_XX_XX_XX_XX_XX_XX/playerX"
        media_player_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, media_player_path)
        media_player_interface = dbus.Interface(media_player_object, bluetooth_constants.MEDIA_PLAYER_INTERFACE)      # Note change of interface to be medial player interface
        media_player_properties = dbus.Interface(media_player_object, bluetooth_constants.DBUS_PROPERTIES)
        media_player_properties_array = bluetooth_utils.dbus_to_python(media_player_properties.GetAll(bluetooth_constants.MEDIA_PLAYER_INTERFACE))
        media_player_introspection = media_player_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        # Return the set of Media Player parts
        return media_player_path, media_player_object, media_player_interface, media_player_properties, media_player_introspection

    # Internal Function for Retrieving an array of the device properties; DEPRECIATED VERSION (???)
    #def find_and_get__all_device_properties(self):
    #    return bluetooth_utils.dbus_to_python(self.device_properties.GetAll(bluetooth_constants.DEVICE_INTERFACE))

    # Internal Function for Requesting/Getting a Specific Device Property using the Device Property interface
    def find_and_get__device_property(self, property_name):
        # Check that the device_properties aspect exists within the class
        if not self.device_properties:
            # Create and set the device properties
            self.create_and_set__device_properties()
        # Attempt to read the given 'property_name'; Note conversion to Python from D-Bus object; NOTE: The code below causes the behavior for BLEEP to shift and will require addressing
        try:
            if hasattr(self.device_properties, "Get"):
                property_return = bluetooth_utils.dbus_to_python(self.device_properties.Get(bluetooth_constants.DEVICE_INTERFACE, property_name))
            else:
                out_log_string = "[-] system_dbus__bluez_device__low_energy::find_and_get__device_property\t-\tGet method not available for device interface [ {0} ] and property [ {1} ]".format(self.device_properties, property_name)
                print_and_log(out_log_string)
                property_return = None
        except Exception as e:
            out_log_string = "[-] system_dbus__bluez_device__low_energy::find_and_get__device_property\t-\tError:\t{0}".format(e)
            print_and_log(out_log_string, LOG__DEBUG)
            return_error = self.understand_and_handle__dbus_errors(e)
            property_return = None      # TODO:  Determine if this is the right response of the tool.... maybe force it to redo the property read? <--- Have it just FAIL and attempt a recovery?
        # Commented out the code below to move this try statement to a higher level
        '''
        # Try statement to attempt reconnecting to a given device
        try:
            # Attempt to read the given 'property_name'; Note conversion to Python from D-Bus object
            property_return = bluetooth_utils.dbus_to_python(self.device_properties.Get(bluetooth_constants.DEVICE_INTERFACE, property_name))
        except Exception as e:
            return_error = self.understand_and_handle__dbus_errors(e)
            property_return = None
            # Produce error log
            if return_error == bluetooth_constants.RESULT_ERR_NOT_FOUND:
                output_log_string = "[-] Unable to query the device property.... Most likely due to device no longer being connected and within the D-Bus device list/memory"
                print_and_log(output_log_string, LOG__DEBUG)
        '''
        # Print out the result of the search
        if dbg != 0:        # ~!~
            #print("Device\t{0}\t-\tProperty\t{1}\n\tValue:\t\t{2}".format(self.device_address, property_name, property_return))
            output_log_string = "Device\t{0}\t-\tProperty\t{1}\n\tValue:\t\t{2}".format(self.device_address, property_name, property_return)
            print_and_log(output_log_string, LOG__DEBUG)
        # Return the property_return
        return property_return

    # Internal Function for Requesting/Getting all the device properties using the Device Property interface
    def find_and_get__all_device_properties(self):
        # Check that the device_properties aspect exists within the class
        if not self.device_properties:
            # Create and set the device properties
            self.create_and_set__device_properties()
        # Attempt to read all the properties
        try:
            # Attempt to read all of the device properties; Note conversion to Python from D-Bus object
            device_properties_array = bluetooth_utils.dbus_to_python(self.device_properties.GetAll(bluetooth_constants.DEVICE_INTERFACE))
            ## NOTA BENE: The above call only grabs the data that is related to 'snapshot in time' that was collected when the device_properties interface/object was generated
        except Exception as e:
            return_error = self.understand_and_handle__dbus_errors(e)
            device_properties_array = None      # NOTE: This can cause issues when attempting to interate through device properties if None; TODO: Perform a device relocation? reconnection? Throw error that device is no longer present?
        # Print out the result of the search
        if dbg != 1:        # ~!~
            #print("Device\t{0}\n\tProperties:\t\t{1}".format(self.device_address, device_properties_array))
            if device_properties_array:
                output_log_string = "Device\t{0}\n\tProperties:\t\t{1}".format(self.device_address, device_properties_array)
            else:
                output_log_string = "Device\t{0}\n\tProperties:\t\t{1}".format(self.device_address, "None... Device may be out of range or low level abstraction issues causing NoneType")
            print_and_log(output_log_string)
            # Nota Bene: HERE is where this framework can see ALL the SERVICE UUIDs, including the GENERIC ACCESS PROFILE UUID
            if device_properties_array is not None:
                for device_property in device_properties_array:
                    #print("\t{0}\t\t-\tValue:\t{1}".format(device_property, device_properties_array[device_property]))
                    # Check what type of property is being printed out and alter to add additional information
                    if device_property == "Class":
                        # Extract and Process the Class / Service information
                        list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check = decode__class_of_device(device_properties_array[device_property])
                        device_services, major_device, minor_device = extract__class_of_device__service_and_class_info(list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check)
                        # Print Information
                        out_log_string = "\t{0}\t\t-\tValue:\t{1}\t\t[ {2} : {3} - {4} ]".format(device_property, device_properties_array[device_property], major_device, minor_device, device_services)
                        print_and_log(out_log_string)
                        if dbg != 0:

                            output_log_string = "[?] Class of Device Information:\t{0}\n".format(device_properties_array[device_property])
                            output_log_string += "[?] Extracted Information:\n\tMajor Service Classes:\t{0}\n\tMajor Device Classes:\t{1}\n\tMinor Device Class:\t{2}\n\tFixed Bits Check:\t{3}".format(list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check)
                            print_and_log(output_log_string, LOG__DEBUG)
                    # Check if the property is ManufacturerData
                    elif device_property == "ManufacturerData":
                        # Extract the Manufacturer / Company Name
                        company_name, manufacturer_id = find_and_return__manufacturer_identifier(device_properties_array[device_property])
                        # Print Information
                        output_log_string = "\t{0}\t\t-\tValue:\t{1}\t\t[ {2} ]".format(device_property, device_properties_array[device_property], company_name)
                        print_and_log(output_log_string)
                    # Check if the property is ServiceData
                    elif device_property == "ServiceData":
                        # Extract the Member UUID from ServiceData UUID
                        member_name, member_id = find_and_return__service_data_decoding(device_properties_array[device_property])
                        # Print Information
                        out_log_string = "\t{0}\t\t-\tValue:\t{1}\t\t[ {2} ]".format(device_property, device_properties_array[device_property], member_name)
                        print_and_log(out_log_string)
                    # Check if the property is AdvertisingFlags
                    elif device_property == "AdvertisingFlags":
                        # Extract the Advertising Type Name and Flag
                        advertising_type, advertising_id = find_and_return__advertising_flag_decoding(device_properties_array[device_property])
                        # Print Information
                        out_log_string = "\t{0}\t\t-\tValue:\t{1}\t\t[ {2} ]".format(device_property, device_properties_array[device_property], advertising_type)
                        print_and_log(out_log_string)
                    # For All Other Properties
                    else:
                        # Perform Generic Print Out
                        output_log_string = "\t{0}\t\t-\tValue:\t{1}".format(device_property, device_properties_array[device_property])
                        print_and_log(output_log_string)

        # Return the device_properties_array
        return device_properties_array

    # Internal Function for Requesting/Getting a Specific Service Property using the Service Property interface
    def find_and_get__service_property(self, service_properties_interface, property_name):
        # Check that the device_properties aspect exists within the class
        if not service_properties_interface:
            if dbg != 0:
                #print("[-] No service_properties_interface passed")
                output_log_string = "[-] No service_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read the given 'property_name'; Note conversion to Python from D-Bus object
        try:
            property_return = bluetooth_utils.dbus_to_python(service_properties_interface.Get(bluetooth_constants.GATT_SERVICE_INTERFACE, property_name))
        except Exception as e:
            if dbg != 1:
                self.understand_and_handle__dbus_errors(e)
            property_return = None
        # Return the property_return
        return property_return

    # Internal Function for Requesting/Getting all the service properties using the GATT Service Property interface
    #   - TODO: Improve handling below; believe getting an error due to GAP + how D-Bus ignores this (by built in functionality; on purpose)
    def find_and_get__all_service_properties(self, service_properties_interface):
        # Check that the Service Properties Interface exists
        if not service_properties_interface:
            if dbg != 0:
                #print("[-] No service_properties_interface passed")
                output_log_string = "[-] No service_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read all the service properties
        try:
            service_properties_array = bluetooth_utils.dbus_to_python(service_properties_interface.GetAll(bluetooth_constants.GATT_SERVICE_INTERFACE))
            if dbg != 0:
                for service_property in service_properties_array:
                    #print("\t{0}\t\t-\tValue:\t{1}".format(service_property, service_properties_array[service_property]))
                    output_log_string = "\t{0}\t\t-\tValue:\t{1}".format(service_property, service_properties_array[service_property])
                    print_and_log(output_log_string, LOG__DEBUG)
        except Exception as e:
            self.understand_and_handle__dbus_errors(e)
            service_properties_array = None
        # Return the service_properties_array
        return service_properties_array

    # Internal Function for Requesting/Getting a Specific Characteristic Property using the Characteristic Property interface
    def find_and_get__characteristic_property(self, characteristic_properties_interface, property_name):
        # Check that the device_properties aspect exists within the class
        if not characteristic_properties_interface:
            if dbg != 0:
                #print("[-] No characteristic_properties_interface passed")
                output_log_string = "[-] No characteristic_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read the given 'property_name'; Note conversion to Python from D-Bus object
        try:
            property_return = bluetooth_utils.dbus_to_python(characteristic_properties_interface.Get(bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE, property_name))
        except Exception as e:
            if dbg != 0:    # ~!~ Chance that the Characteristic Handle always returns NULL/NONE; might be related to failure to read the property     <--- Reason: Server-side defined, and therefore no documentated "math" to generate
                self.error_buffer = self.understand_and_handle__dbus_errors(e)
            property_return = None
        # Return the property_return
        return property_return

    # Internal Function for Requesting/Getting all the characteristic properties using the GATT Characteristic Property Interface
    def find_and_get__all_characteristic_properties(self, characteristic_properties_interface):
        # Check that the Charactersitic Properties Interface exists
        if not characteristic_properties_interface:
            if dbg != 0:
                #print("[-] No characteristic_properties_interface passed")
                output_log_string = "[-] No characteristic_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read all the charactersitic properties
        try:
            characteristic_properties_array = bluetooth_utils.dbus_to_python(characteristic_properties_interface.GetAll(bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE))
            if dbg != 0:
                for characteristic_property in characteristic_properties_array:
                    #print("\t{0}\t\t-\tValue:\t{1}".format(characteristic_property, characteristic_properties_array[characteristic_property]))
                    output_log_string = "\t{0}\t\t-\tValue:\t{1}".format(characteristic_property, characteristic_properties_array[characteristic_property])
                    print_and_log(output_log_string, LOG__DEBUG)
        except Exception as e:
            self.understand_and_handle__dbus_errors(e)
            characteristic_properties_array = None
        # Return the characteristic_properties_array
        return characteristic_properties_array

    # Internal Function for Requesting/Getting a Specific Descriptor Property using the Descriptor Property interface
    def find_and_get__descriptor_property(self, descriptor_properties_interface, property_name):
        # Check that the device_properties aspect exists within the class
        if not descriptor_properties_interface:
            if dbg != 0:
                #print("[-] No descriptor_properties_interface passed")
                output_log_string = "[-] No descriptor_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read the given 'property_name'; Note conversion to Python from D-Bus object
        try:
            property_return = bluetooth_utils.dbus_to_python(descriptor_properties_interface.Get(bluetooth_constants.GATT_DESCRIPTOR_INTERFACE, property_name))
        except Exception as e:
            if dbg != 0:
                self.understand_and_handle__dbus_errors(e)
            property_return = None
        # Return the property_return
        return property_return

    # Internal Function for Requesting/Getting all the descriptor properties using the GATT Descriptor Property Interface
    def find_and_get__all_descriptor_properties(self, descriptor_properties_interface):
        # check that the Descriptor Properties Interface exists
        if not descriptor_properties_interface:
            if dbg != 0:
                #print("[-] No descriptor_properties_interface passed")
                output_log_string = "[-] No descriptor_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read all the descriptor properties
        try:
            descriptor_properties_array = bluetooth_utils.dbus_to_python(descriptor_properties_interface.GetAll(bluetooth_constants.GATT_DESCRIPTOR_INTERFACE))
            if dbg != 0:
                for descriptor_property in descriptor_properties_array:
                    print("\t{0}\t\t-\tValue:\t{1}".format(descriptor_property, descriptor_properties_array[descriptor_property]))
                    output_log_string = "\t{0}\t\t-\tValue:\t{1}".format(descriptor_property, descriptor_properties_array[descriptor_property])
                    print_and_log(output_log_string)
        except Exception as e:
            self.understand_and_handle__dbus_errors(e)
            descriptor_properties_array = None
        # Return the descriptor_properties_array
        return descriptor_properties_array

    # Internal Function for Requesting/Getting a Specific Media Control Property using the Media Control Property interface
    def find_and_get__media_control_property(self, media_control_properties_interface, property_name):
        # Check that the device_properties aspect exists within the class
        if not media_control_properties_interface:
            if dbg != 0:
                #print("[-] No media_control_properties_interface passed")
                output_log_string = "[-] No media_control_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read the given 'property_name'; Note conversion to Python from D-Bus object
        try:
            property_return = bluetooth_utils.dbus_to_python(media_control_properties_interface.Get(bluetooth_constants.MEDIA_CONTROL_INTERFACE, property_name))
        except Exception as e:
            if dbg != 1:
                self.understand_and_handle__dbus_errors(e)
            property_return = None
        # Return the property_return
        return property_return

    # Internal Function for Requesting/Getting all the media_control properties using the Media Control Property interface
    def find_and_get__all_media_control_properties(self, media_control_properties_interface):
        # Check that the Service Properties Interface exists
        if not media_control_properties_interface:
            if dbg != 0:
                #print("[-] No media_control_properties_interface passed")
                output_log_string = "[-] No media_control_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read all the media_control properties
        try:
            media_control_properties_array = bluetooth_utils.dbus_to_python(media_control_properties_interface.GetAll(bluetooth_constants.MEDIA_CONTROL_INTERFACE))
            if dbg != 0:
                for media_control_property in media_control_properties_array:
                    #print("\t{0}\t\t-\tValue:\t{1}".format(media_control_property, media_control_properties_array[media_control_property]))
                    output_log_string = "\t{0}\t\t-\tValue:\t{1}".format(media_control_property, media_control_properties_array[media_control_property])
                    print_and_log(output_log_string, LOG__DEBUG)
        except Exception as e:
            self.understand_and_handle__dbus_errors(e)
            media_control_properties_array = None
        # Return the media_control_properties_array
        return media_control_properties_array

    # Internal Function for Requesting/Getting a Specific Media Endpoint Property using the Media Endpoint Property interface
    def find_and_get__media_endpoint_property(self, media_endpoint_properties_interface, property_name):
        # Check that the device_properties aspect exists within the class
        if not media_endpoint_properties_interface:
            if dbg != 0:
                #print("[-] No media_endpoint_properties_interface passed")
                output_log_string = "[-] No media_endpoint_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read the given 'property_name'; Note conversion to Python from D-Bus object
        try:
            property_return = bluetooth_utils.dbus_to_python(media_endpoint_properties_interface.Get(bluetooth_constants.MEDIA_ENDPOINT_INTERFACE, property_name))
        except Exception as e:
            if dbg != 1:
                self.understand_and_handle__dbus_errors(e)
            property_return = None
        # Return the property_return
        return property_return

    # Internal Function for Requesting/Getting all the media_endpoint properties using the Media Endpoint Property interface
    def find_and_get__all_media_endpoint_properties(self, media_endpoint_properties_interface):
        # Check that the Service Properties Interface exists
        if not media_endpoint_properties_interface:
            if dbg != 0:
                #print("[-] No media_endpoint_properties_interface passed")
                output_log_string = "[-] No media_endpoint_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read all the media_endpoint properties
        try:
            media_endpoint_properties_array = bluetooth_utils.dbus_to_python(media_endpoint_properties_interface.GetAll(bluetooth_constants.MEDIA_ENDPOINT_INTERFACE))
            if dbg != 0:
                for media_endpoint_property in media_endpoint_properties_array:
                    #print("\t{0}\t\t-\tValue:\t{1}".format(media_endpoint_property, media_endpoint_properties_array[media_endpoint_property]))
                    output_log_string = "\t{0}\t\t-\tValue:\t{1}".format(media_endpoint_property, media_endpoint_properties_array[media_endpoint_property])
                    print_and_log(output_log_string, LOG__DEBUG)
        except Exception as e:
            self.understand_and_handle__dbus_errors(e)
            media_endpoint_properties_array = None
        # Return the media_endpoint_properties_array
        return media_endpoint_properties_array

    # Internal Function for Requesting/Getting all the media_transport properties using the Media Endpoint Property interface
    def find_and_get__all_media_transport_properties(self, media_transport_properties_interface):
        # Check that the Service Properties Interface exists
        if not media_transport_properties_interface:
            if dbg != 0:
                #print("[-] No media_transport_properties_interface passed")
                output_log_string = "[-] No media_transport_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read all the media_transport properties
        try:
            media_transport_properties_array = bluetooth_utils.dbus_to_python(media_transport_properties_interface.GetAll(bluetooth_constants.MEDIA_TRANSPORT_INTERFACE))
            if dbg != 0:
                for media_transport_property in media_transport_properties_array:
                    #print("\t{0}\t\t-\tValue:\t{1}".format(media_transport_property, media_transport_properties_array[media_transport_property]))
                    output_log_string = "\t{0}\t\t-\tValue:\t{1}".format(media_transport_property, media_transport_properties_array[media_transport_property])
                    print_and_log(output_log_string, LOG__DEBUG)
        except Exception as e:
            self.understand_and_handle__dbus_errors(e)
            media_transport_properties_array = None
        # Return the media_transport_properties_array
        return media_transport_properties_array

    # Internal Function for Requesting/Getting a Specific Media Player Property using the Media Player Property interface
    def find_and_get__media_player_property(self, media_player_properties_interface, property_name):
        # Check that the device_properties aspect exists within the class
        if not media_player_properties_interface:
            if dbg != 0:
                #print("[-] No media_player_properties_interface passed")
                output_log_string = "[-] No media_player_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read the given 'property_name'; Note conversion to Python from D-Bus object
        try:
            property_return = bluetooth_utils.dbus_to_python(media_player_properties_interface.Get(bluetooth_constants.MEDIA_PLAYER_INTERFACE, property_name))
        except Exception as e:
            if dbg != 1:
                self.understand_and_handle__dbus_errors(e)
            property_return = None
        # Return the property_return
        return property_return

    # Internal Function for Requesting/Getting all the media_player properties using the Media Player Property interface
    def find_and_get__all_media_player_properties(self, media_player_properties_interface):
        # Check that the Service Properties Interface exists
        if not media_player_properties_interface:
            if dbg != 0:
                #print("[-] No media_player_properties_interface passed")
                output_log_string = "[-] No media_player_properties_interface passed"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read all the media_player properties
        try:
            media_player_properties_array = bluetooth_utils.dbus_to_python(media_player_properties_interface.GetAll(bluetooth_constants.MEDIA_PLAYER_INTERFACE))
            if dbg != 0:
                for media_player_property in media_player_properties_array:
                    #print("\t{0}\t\t-\tValue:\t{1}".format(media_player_property, media_player_properties_array[media_player_property]))
                    output_log_string = "\t{0}\t\t-\tValue:\t{1}".format(media_player_property, media_player_properties_array[media_player_property])
                    print_and_log(output_log_string, LOG__DEBUG)
        except Exception as e:
            self.understand_and_handle__dbus_errors(e)
            media_player_properties_array = None
        # Return the media_player_properties_array
        return media_player_properties_array

    # Internal Function for Creating an eTree from Introspection and Returning its Contents
    #   - Note: The actions taken depend on the search_term provided and depends on what is being searched for (i.e. Service, Characteristics, or Descriptor)
    def find_and_get__device__etree_details(self, introspection_interface, search_term):
        # Ensure that the introspection_interface is not None
        if not introspection_interface:
            if dbg != 1:
                #print("[!] Error: Introspection Interface is non-existant")
                output_log_string = "[!] Error: Introspection Interface is non-existant"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        if dbg != 0:
            out_log_string = "[*] find_and_get__device__etree_details::Generating E-Tree from Introspection Interface\t\t-\t\tType:\t{0}".format(type(introspection_interface))
            print_and_log(out_log_string, LOG__DEBUG)
        # Create the eTree string to interacte through
        introspection_tree = ET.fromstring(introspection_interface)
        # Create different tracking (list vs dictionary) baised on search_term provided
        if search_term == 'enumerate':
            # Expand the exploration to search for outliers + strange interfaces (e.g. sep1, sep2, MediaControl1, Battery1)
            introspection_contents = {'interfaces': [], 'nodes': [], 'unknowns': []}
        else:
            introspection_contents = []     # Simple list tracking
        # Debugging to output the introspection tree; Note: This ONLY produces an address as the information shown
        if dbg != 1:
            output_log_string = "[!] Introspection E-Tree Information:\t\t{0}".format(introspection_tree)
            print_and_log(output_log_string, LOG__DEBUG)
        # Debug for the root of the E-Tree
        if dbg != 1:
            output_log_string = "Root Tag:\t[ {0} ]\t\t-\t\tRoot Attrib:\t[ {1} ]".format(introspection_tree.tag, introspection_tree.attrib)
            print_and_log(output_log_string, LOG__DEBUG)
        # Loop through the eTree and collect all the child.attrib that are 'node's and match the provided search term
        for child in introspection_tree:
            # Confirm that examining a 'node'
            if child.tag == 'node':
                # Looking for GATT Services
                if search_term == 'service':
                    introspection_contents.append(child.attrib['name'])
                elif search_term == 'char':
                    introspection_contents.append(child.attrib['name'])
                elif search_term == 'desc':
                    introspection_contents.append(child.attrib['name'])
                # Tracking Device Level Information
                elif search_term == 'enumerate':
                    introspection_contents['nodes'].append(child.attrib['name'])
                else:
                    if dbg != 1:
                        #print("[!] Error: Search term for introspection was unknown")
                        output_log_string = "[!] Error: Search term for introspection was unknown"
                        print_and_log(output_log_string, LOG__DEBUG)
            # Searching for interface information; intended for device-level enumeration
            elif child.tag == 'interface':
                # Collecting Interfaces Observed
                if search_term == 'enumerate':
                    introspection_contents['interfaces'].append(child.attrib['name'])
                else:
                    if dbg != 0:
                        #print("[!] Error: Search term for introspection was unknown")
                        output_log_string = "[!] Error: Search term for introspection was unknown"
                        print_and_log(output_log_string, LOG__DEBUG)
            # Unknown scenario
            else:
                # Collecting Unknown Elements
                if search_term == 'enumerate':
                    introspection_contents['unknowns'].append(child.attrib['name'])
                else:
                    if dbg != 0:
                        #print("[!] Error: Search term for introspection was unknown")
                        output_log_string = "[!] Error: Search term for introspection was unknown"
                        print_and_log(output_log_string, LOG__DEBUG)
            # Debugging for Introspeciton E-Tree inspection
            if dbg != 1:
                output_log_string = "\tChild Tag:\t[ {0} ]\t\t-\t\tChild Attrib:\t[ {1} ]".format(child.tag, child.attrib)
                print_and_log(output_log_string, LOG__DEBUG)
        # Return the Introspection Contents
        return introspection_contents

    # Internal Function for Enumerating the Interfaces, Nodes, and Unknowns presented by the Device Introspection interface
    def find_and_get__device_introspection__full_enumeration(self):
        # Ensure that the Necessary Introspection Interface
        if not self.device_introspection:
            out_log_string = "[*] find_and_get__device_introspection__full_enumeration::Attempting to Generate Introspection Interface"
            print_and_log(out_log_string, LOG__DEBUG)
            # Create the Introspection Interface and set it before continuing
            self.create_and_set__device_introspection()
        # Call the class function and passing that Device information is being search for
        introspection_enumeration_dictionary = self.find_and_get__device__etree_details(self.device_introspection, 'enumerate')
        # Return the found dictionary of device enumeration information
        return introspection_enumeration_dictionary 

    # Internal Function for Enumerating the Interfaces, Nodes, and Unknowns presented by the Given Target Introspection
    def find_and_get__interface_introspection__full_enumeration(self, target_introspection):
        # Ensure that the Necessary Introspection Interface
        if not target_introspection:
            out_log_string = "[*] find_and_get__interface_introspection__full_enumeration::No Target Interface provided"
            print_and_log(out_log_string, LOG__DEBUG)
            # Return False as indiciation of failure
            return None
        else:
        #    out_log_string = "[*] find_and_get__interface_introspection__full_enumeration::Continuing with Enumeration"
            if isinstance(target_introspection,dbus.proxies.Interface):
                out_log_string = "[-] find_and_get__interface_introspection__full_enumeration::Target Introspection expected to be type dbus.String and NOT dbus.proxies.Interface"
                print_and_log(out_log_string, LOG__DEBUG)
                # Return None as indiciation of failure
                return None
        out_log_string = "[*] find_and_get__interface_introspection__full_enumeration::Extracting E-Tree Details from Target Introspection"
        print_and_log(out_log_string, LOG__DEBUG)
        # Call the class function and passing the enumerate keyword
        introspection_enumeration_dictionary = self.find_and_get__device__etree_details(target_introspection, 'enumerate')
        #self.device_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        # Return the found dictionary of interface enumeration information
        return introspection_enumeration_dictionary

    # Internal Function for Enumerating the Services presented by the Device Introspection interface
    def find_and_get__device_introspection__services(self):
        # Ensure that the Necessary Introspection Interface
        if not self.device_introspection:
            out_log_string = "[*] find_and_get__device_introspection__services::Attempting to Generate Introspection Interface"
            print_and_log(out_log_string, LOG__DEBUG)
            # Create the Introspection Interface and set it before continuing
            self.create_and_set__device_introspection()
        # Call the class function and passing that Services are being searched for
        introspection_services_list = self.find_and_get__device__etree_details(self.device_introspection, 'service')
        # Return the found list of device services
        return introspection_services_list

    # Internal Function for Enumerating the Characteristics presented by the Service Introspection interface
    #   - Note: There is a variable number of characteristics PER service; may also be ZERO
    def find_and_get__device_introspection__characteristics(self, service_path, service_characteristics_list):
        introspection_characteristics_list = []
        # Call internal class function
        if not service_characteristics_list:
            if dbg != 0:
                #print("[*] Service's characteristics list is empty:\t\t{0}".format(service_characteristics_list))
                output_log_string = "[*] Service's characteristics list is empty:\t\t{0}".format(service_characteristics_list)
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        for service_characteristic in service_characteristics_list:
            # Create the eTree string to interate through the characteristics of the service
            characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = self.create_and_return__characteristic__gatt_inspection_set(service_path, service_characteristic)
            # TODO: Figure out how to have this function return (ALL?) characteristics related to the device (? or just a single level's worth)
            introspection_characteristics_list.append(self.find_and_get__device__etree_details(characteristic_introspection, 'char'))
        # Return the found list
        return introspection_characteristics_list

    # Internal Function for Enumerating the Descriptors presented by the Characteristic Introspection interface
    #   - Note: There is a variable number of descriptors (???) PER characteristic; should ONLY be ONE (??)
    def find_and_get__device_introspection__descriptors(self, characteristic_descriptors_list):
        introspection_descriptors_list = []
        # Call internal class function
        if not characteristic_descriptors_list:
            if dbg != 0:
                #print("[*] Characteristic's descriptors list is empty:\t\t{0}".format(characteristic_descriptors_list))
                output_log_string = "[*] Characteristic's descriptors list is empty:\t\t{0}".format(characteristic_descriptors_list)
                print_and_log(output_log_string, LOG__DEBUG)
        # Create the eTree string to interate through the descriptors of the characteristic
        characteristic_object, characteristic_interface, characteristics_properties, characteristic_introspection = self.create_and_return__characteristic__gatt_inspection_set(characteristic_name)
        # Return the found list
        return introspection_descriptors_list

    # Internal Function for Populating the Device Class Properties
    def identify_and_set__device_properties(self, device_properties_array):
        # Check that the device properties list exists
        if not device_properties_array:
            if dbg != 0:
                #print("[-] Device Properties Array is Empty.... Was it created?")
                output_log_string = "[-] Device Properties Array is Empty.... Was it created?"
                print_and_log(output_log_string, LOG__DEBUG)
        # Iterate through the Device Properties and Set the Device Class Properties
        for device_property in device_properties_array:
            # Large IF statement to set the different properties
            if device_property == 'Address':
                # Address
                self.device_address = device_properties_array[device_property]
            elif device_property == 'AddressType':
                # Address Type
                self.device_address_type = device_properties_array[device_property]
            elif device_property == 'Name':
                # Name
                self.device_name = device_properties_array[device_property]
            elif device_property == 'Alias':
                # Alias
                self.device_alias = device_properties_array[device_property]
            elif device_property == 'Paired':
                # Paired
                self.device_paired = device_properties_array[device_property]
            elif device_property == 'Trusted':
                # Trusted
                self.device_trusted = device_properties_array[device_property]
            elif device_property == 'Bonded':
                # Bonded
                self.device_bonded = device_properties_array[device_property]
            elif device_property == 'Blocked':
                # Blocked
                self.device_blocked = device_properties_array[device_property]
            elif device_property == 'LegacyPairing':
                # Legacy Pairing
                self.device_legacy_pairing = device_properties_array[device_property]
            elif device_property == 'Connected':
                # Connected
                self.device_connected = device_properties_array[device_property]
            elif device_property == 'UUIDs':
                # UUIDs
                self.device_uuids = device_properties_array[device_property]
            elif device_property == 'Adapter':
                # Adapter
                self.device_adapter = device_properties_array[device_property]
            elif device_property == 'ServiceData':
                # Service Data
                self.device_service_data = device_properties_array[device_property]
            elif device_property == 'ServicesResolved':
                # Services Resolved
                self.device_services_resolved = device_properties_array[device_property]
            elif device_property == 'ManufacturerData':
                # Manufacturer Data
                self.manufacturer_data = device_properties_array[device_property]
            elif device_property == 'Appearance':
                # Appearance
                self.appearance = device_properties_array[device_property]
            elif device_property == 'Icon':
                # Icon
                self.icon = device_properties_array[device_property]
            elif device_property == 'Class':
                # Class (Bluetooth Class of Device of the remote device)
                self.device_class = device_properties_array[device_property]
                '''
                if dbg != 1:
                    output_log_string = "[?] Class of Device Information:\t{0}\n".format(self.device_class)
                    list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check = decode__class_of_device(self.device_class)
                    output_log_string += "[?] Extracted Information:\n\tMajor Service Classes:\t{0}\n\tMajor Device Classes:\t{1}\n\tMinor Device Class:\t{2}\n\tFixed Bits Check:\t{3}".format(list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check)
                    print_and_log(output_log_string)
                '''
            elif device_property == 'WakeAllowed':
                # Wake Allowed Flag - If true device will be allowed to wake the host from system suspend
                self.wake_allowed = device_properties_array[device_property]
            elif device_property == 'Modalias':
                # Modalias - Remote Device Id information in modalias format used by kernel and udev
                self.modalias = device_properties_array[device_property]
            elif device_property == 'RSSI':
                # RSSI
                self.rssi = device_properties_array[device_property]
            elif device_property == 'TxPower':
                # TX Power - Advertised transmitted power level (inquiry or advertising)
                self.tx_power = device_properties_array[device_property]
            ## Experimental Details
            elif device_property == 'AdvertisingFlags':
                # Advertising Flags
                self.advertising_flags = device_properties_array[device_property]
            elif device_property == 'AdvertisingData':
                # Advertising Data
                self.advertising_data = device_properties_array[device_property]
            elif device_property == 'Sets':
                # Sets - Object paths of teh sets the device belongs to followed by a dictionary that can contain the rank of devices in the set
                self.sets = device_properties_array[device_property]
            ## Others
            else:
                # Unknown Property
                #print("[-] Unknown Property:\t{0}\t\t-\t\tValue:\t{1}".format(device_property, device_properties_array[device_property]))
                output_log_string = "[-] Unknown Property:\t{0}\t\t-\t\tValue:\t{1}".format(device_property, device_properties_array[device_property])
                print_and_log(output_log_string)

    # Internal Function for Writing a Single Byte to a Device Characteristic Interface
    def write__device__characteristic__single_byte(self, characteristic_interface, write_value, dict_options={}):
        #print("[*] Performing Single Byte Write")
        output_log_string = "[*] Performing Single Byte Write"
        print_and_log(output_log_string)
        try:
            # Write the single byte to the target
            characteristic_interface.WriteValue([write_value], dict_options)
            # Return confirmation of success
            return True
        except Exception as e:
            # Perform error handling
            self.understand_and_handle__dbus_errors(e)
        #print("[+] Completed Single Byte Write")
        output_log_string = "[+] Completed Single Byte Write"
        print_and_log(output_log_string)

    # Internal Function for Writing Byte-by-Byte to a Device Characteristic Interface
    def write__device__characteristic__byte_by_byte(self, characteristic_interface, write_value, dict_options={}):
        #print("[*] Performing Byte-by-Byte Write")
        output_log_string = "[*] Performing Byte-by-Byte Write"
        print_and_log(output_log_string)
        try:
            # Loop for writing byte-by-byte to the target
            for character_byte in write_value:
                # Write the single character byte to the target
                characteristic_interface.WriteValue([character_byte], dict_options)
            # Return confirmation of success
            return True
        except Exception as e:
            # Perform error handling
            self.understand_and_handle__dbus_errors(e)
        #print("[+] Completed Byte-by-Byte Write")
        output_log_string = "[+] Completed Byte-by-Byte Write"
        print_and_log(output_log_string)

    # Internal Function for Writing Single D-Bus Array to a Device Characteristic Interface
    def write__device__characteristic__single_array(self, characteristic_interface, write_value, dict_options={}):
        #print("[*] Performing Single Array Write")
        output_log_string = "[*] Performing Single Array Write"
        print_and_log(output_log_string)
        try:
            # Write the single array to the target
            characteristic_interface.WriteValue(write_value, dict_options)      # NOTE: The lack of [ ] around write_value ensures we do NOT pass a nested array (e.g. [ [...] ])
        except Exception as e:
            # Perform error handling
            self.understand_and_handle__dbus_errors(e)
        #print("[+] Completed Single Array Write")
        output_log_string = "[+] Completed Single Array Write"
        print_and_log(output_log_string)

    # Internal Function for Reading from a Device Characteristic Interface
    def read__device__characteristic(self, characteristic_interface, dict_options={}):
        # Check that the device characteristic interface exists
        if not characteristic_interface:
            if dbg != 0:
                #print("[-] Device Characteristic Interface is Empty.... Was it created?")
                output_log_string = "[-] Device Characteristic Interface is Empty.... Was it created?"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Variable for tracking read information; Allows default return in the case nothing is read
        characteristic_value = None
        # Attempt to read the characteristic value; TODO: Improve the visibility of this function call
        try:
            characteristic_value = characteristic_interface.ReadValue(dict_options)
            #return characteristic_interface.ReadValue(dict_options)
            #characteristic_interface.ReadValue(dict_options)
            #return self.find_and_get__characteristic_property(characteristic_properties, 'Value')
        except Exception as e:
            if dbg != 1:    # ~!~   NOTE: Testing why the 'read' gives a different value from the 'explore' or 'read-all' commands for the user interface
                out_log_string = "[-] BLE Class::read__device__characteristic\t-\tFailure in Performing Read"
                print_and_log(out_log_string, LOG__DEBUG)
            # Track the error via Class internal variable
            #return_error = self.understand_and_handle__dbus_errors(e)      # Note: Desire to pass errors, but unsure how.... Perform Class error variable?
            self.error_buffer = self.understand_and_handle__dbus_errors(e)
            out_log_string = "\tError Value Generated:\t\t[ {0} ]".format(self.error_buffer)
            print_and_log(out_log_string)
            print_and_log(out_log_string, LOG__DEBUG)
        finally:        # Check the error_buffer and act accordingly
            out_log_string = "[*] BLE Class::read__device__characteristic::Performing Fixes due to Error Buffer"
            print_and_log(out_log_string, LOG__DEBUG)
            self.perform__fix_error()
            #characteristic_value = None
            #return None
            #return UNKNOWN_VALUE
        # Return the value
        return characteristic_value

    # Internal Function for Reading from a Device Characteristic Interface - SECONDARY TESTING FUNCTION; Examination of Return
    def read__device__characteristic__with_signature(self, characteristic_interface, dict_options={}):
        # Check that the device characteristic interface exists
        if not characteristic_interface:
            if dbg != 0:
                #print("[-] Device Characteristic Interface is Empty.... Was it created?")
                output_log_string = "[-] Device Characteristic Interface is Empty.... Was it created?"
                print_and_log(output_log_string, LOG__DEBUG)
            return None
        # Attempt to read the characteristic value; TODO: Improve the visibility of this function call
        try:
            characteristic_value = characteristic_interface.ReadValue(dict_options)
            #return characteristic_interface.ReadValue(dict_options)
            #return characteristic_interface.ReadValue(dict_options)
            #return self.find_and_get__characteristic_property(characteristic_properties, 'Value')
        except Exception as e:
            if dbg != 1:    # ~!~   NOTE: Testing why the 'read' gives a different value from the 'explore' or 'read-all' commands for the user interface
                out_log_string = "[-] BLE Class::read__device__characteristic\t-\tFailure in Performing Read"
                print_and_log(out_log_string, LOG__DEBUG)
            # Track the error via Class internal variable
            #return_error = self.understand_and_handle__dbus_errors(e)      # Note: Desire to pass errors, but unsure how.... Perform Class error variable?
            self.error_buffer = self.understand_and_handle__dbus_errors(e)
            out_log_string = "\tError Value Generated:\t\t[ {0} ]".format(self.error_buffer)
            print_and_log(out_log_string)
            print_and_log(out_log_string, LOG__DEBUG)
            characteristic_value = None
        finally:        # Check the error_buffer and act accordingly
            out_log_string = "[*] BLE Class::read__device__characteristic::Performing Fixes due to Error Buffer"
            print_and_log(out_log_string, LOG__DEBUG)
            self.perform__fix_error()
            #characteristic_value = None
            #return None
            #return UNKNOWN_VALUE
        # Return the value
        return characteristic_value


    # Internal Function for Writing to a Device Characteristic Interface; TODO: Check if data being written is a SINGLE BYTE or MULTIPLE BYTES
    def write__device__characteristic(self, characteristic_interface, write_value, dict_options={}):
        # Check the device characteristic interface exists
        if not characteristic_interface:
            if dbg != 0:
                #print("[-] Device Characteristic Interface is Empty.... Was it created?")
                output_log_string = "[-] Device Characteristic Interface is Empty.... Was it created?"
                print_and_log(output_log_string, LOG__DEBUG)
        # Variables used for writing
        retry_type = None
        #user_input_type = type(write_value)
        if dbg != 1:    # ~!~
            #print("\tWrite Value:\t{0}\n\tWrite Type:\t{1}".format(write_value, type(write_value)))
            output_log_string = "\tWrite Value:\t{0}\n\tWrite Type:\t{1}".format(write_value, type(write_value))
            print_and_log(output_log_string)
        ## Attempt to write data to the target interface
        # Write Value is an integer
        if isinstance(write_value,int) and not isinstance(write_value, str):
            #print("[*] Write Value is Integer")
            output_log_string = "[*] Write Value is Integer"
            print_and_log(output_log_string)
            ## Check and convert int for writing
            # Further processing if the integer passed is larger than representable by a single byte
            if write_value > 255:       # Nota Bene: Via examination of the nRF Connect app, ALL numbers larger than 255 get passed as a byte array (e.g. 256 => \x01\x00; depending on endian-ness) # TODO: Test that PicoW received 256 as b'\x01\x00'; maybe sent as a string and NOT an array of Bytes?
                #num_bytes = math.ceil(write_value/255)      # NOPE.... This does not wokr that way
                #num_bytes = math.ceil(math.log(write_value, 256)) + 1       # Note the addition of an extra byte
                # Determine the number of bytes required to represent the presented number
                num_bytes = math.ceil(math.log(write_value, 255))
                # Write the provided integer as a num_bytes hex array
                write_value = int(write_value).to_bytes(num_bytes, byteorder='big')     # Note: This will produce a byte Class object (e.g. b'\x01\x00') which is what Pico W shows receiving from the nRF Connect app
                # Write array to target
                self.write__device__characteristic__single_array(characteristic_interface, write_value, dict_options)
            # Simple conversion
            else:
            #    write_value = int(write_value)
                # Write the integer to the target interface
                self.write__device__characteristic__single_byte(characteristic_interface, write_value, dict_options)
            return True     # TODO: Verify that this is correct behavior
        # Write Value is a float
        elif isinstance(write_value, float):
            #print("[*] Write Value is Float")
            output_log_string = "[*] Write Value is Float"
            print_and_log(output_log_string)
        # Write Value is a string
        elif isinstance(write_value, str):
            #print("[*] Write Value is String")
            output_log_string = "[*] Write Value is String"
            print_and_log(output_log_string)
            # Convert the input to an ASCii encoded string (required?)
            write_value = self.ascii_string__to__dbus_value(write_value)
            if dbg != 0:    # ~!~
                #print("[?] Write Value:\t{0}\n\tWrite Type:\t{1}".format(write_value, type(write_value)))
                output_log_string = "[?] Write Value:\t{0}\n\tWrite Type:\t{1}".format(write_value, type(write_value))
                print_and_log(output_log_string, LOG__DEBUG)
            ## Code for writing a string type
            ## TODO: Add separate choices for performing (1) byte-by-byte write and (2) total byte array all together
            # Check to see if the provided data is length ONE or GREATER; should be an indicitor of the type of data being passed
            if len(write_value) < 1:
                #print("[-] Data of length zero was passed to write")
                output_log_string = "[-] Data of length zero was passed to write"
                print_and_log(output_log_string)
                ## TODO: Determine if this should be allowed or not; what should the response be?
            elif len(write_value) == 1:
                #print("[*] Data passed is of length one")
                output_log_string = "[*] Data passed is of length one"
                print_and_log(output_log_string)
                # Note the extraction of the int from the provided list, since it is a single value within the list
                if isinstance(write_value, list):
                    write_value = write_value[0]
                self.write__device__characteristic__single_byte(characteristic_interface, write_value, dict_options)
            else:
                #print("[*] Data passed is of length {0}".format(len(write_value)))
                output_log_string = "[*] Data passed is of length {0}".format(len(write_value))
                print_and_log(output_log_string)
                # Now determine if the data should be written all together or individually
                ## NOTE: This might require learning what the signature of the target is
                self.write__device__characteristic__single_array(characteristic_interface, write_value, dict_options)       ## WORKS! Can write multiple characters to a single write
        # Write Value is a dict
        elif isinstance(write_value, dict):
            #print("[*] Write Value is Dictionary")
            output_log_string = "[*] Write Value is Dictionary"
            print_and_log(output_log_string)
        # Write Value is a list
        elif isinstance(write_value, list):
            #print("[*] Write Value is List")
            output_log_string = "[*] Write Value is List"
            print_and_log(output_log_string)
        # Write Value is a D-Bus Byte
        elif isinstance(write_value, dbus.Byte):
            #print("[*] Write Value is D-Bus Byte")
            output_log_string = "[*] Write Value is D-Bus Byte"
            print_and_log(output_log_string)
            # Write the D-Bus Byte to the target interface
            self.write__device__characteristic__single_byte(characteristic_interface, write_value, dict_options)
        # Write Value is a D-Bus Array
        elif isinstance(write_value,dbus.Array):
            #print("[*] Write Value is D-Bus Array")
            output_log_string = "[*] Write Value is D-Bus Array"
            print_and_log(output_log_string)
            # Write the D-Bus Array to the target interface
            self.write__device__characteristic__single_array(characteristic_interface, write_value, dict_options)
        # Write Value is Bytes
        elif isinstance(write_value,bytes):
            output_log_string = "[*] Write Value is Bytes"
            print_and_log(output_log_string)
            # Write the Bytes to the target interface
            self.write__device__characteristic__single_array(characteristic_interface, write_value, dict_options)       ## WORKS!!! Can pass bytes and the receiving end will receive the bytes correctly
        # Write Value is unhandled/unknown arrayu
        else:
            #print("[*] Write Value is Unknown/Unhandled")
            output_log_string = "[*] Write Value is Unknown/Unhandled"
            print_and_log(output_log_string)

        '''     WORKING VERSION
        # Attempt to read the characteristic value
        try:
            characteristic_interface.WriteValue([write_value], dict_options)
            return True
        except TypeError as e:
            if dbg != 0:
                print("[-] TypeError During Write\t-\tCould be either:(1) The wrong type of variable passed (e.g. str when expecting int) OR (2) The value is not being passed as iterable (e.g. array of single int)")
            # Debugging the error
            if dbg != 0:    # ~!~
                print(type(e))
                print(e)
            ## TODO: Attempt writing via other types?
            if "integer is required" in str(e):
                retry_type = int(1)
            if dbg != 1:    # ~!~
                print("[!] Attempting ReTry of Write Action....")
            ## Assuming failure of characteristic write, therefore attempt the others
            if isinstance(retry_type, int):
                # Write the user supplied write_value as an int
                try:
                    write_value = int(write_value)
                    characteristic_interface.WriteValue([write_value], dict_options)
                    return True
                except Exception as e:
                    if dbg != 1:    # ~!~
                        self.understand_and_handle__dbus_errors(e)
            else:
                print("[-] Unknown Type\t-\tWrite FAILURE with [ {0} ]".format(write_value))
        except Exception as e:
            if dbg != 0:
                self.understand_and_handle__dbus_errors(e)
        else:
            print("[!] Did not succeed in performing Write, but also had ZERO ERRORS")
        finally:
            # Final debug output for monitoring writes via D-Bus to Bluetooth Device (BLE)
            if dbg != 0:
                print("[+] Complete Write Action\t-\tNote: Not Proof of Successful Write of [ {0} ]\t-\tType [ {1} ]".format(write_value, type(write_value)))
        '''
        ## TODO: Incorporate the above code for Brute Force Writing function
        return False

    # Internal Function for Reading from a Device Descriptor Interface
    ##  - NOTE: Descriptors DO NOT have a flag variable and therefore should always allow a read
    #       -> Incorrect! git.kernel API documentation shows descriptors can have flags (even if not seen in the wild)
    def read__device__descriptor(self, descriptor_interface, dict_options={}):
        # Check that the device descriptor interface exists
        if not descriptor_interface:
            if dbg != 0:
               #print("[-] Device Descriptor Interface is Empty... Was it created?")
               output_log_string = "[-] Device Descriptor Interface is Empty... Was it created?"
               print_and_log(output_log_string, LOG__DEBUG)
        # Attempt to read the descriptor value
        try:
            # Note: Need to perform a double read to get actual data from a GATT Descriptor
            # First Read    ( Note: Do NOT set to a variable?  Because that causes issue???)    <---- Do not need this????
            #descriptor_interface.ReadValue(dict_options)
            return descriptor_interface.ReadValue(dict_options)
        except Exception as e:
            if dbg != 0:
                self.understand_and_handle__dbus_errors(e)
            return None

    # Internal Function for Writing to a Device Descriptor Interface
    def write__device__descriptor(self, decriptor_interface, write_value, dict_options={}):
        # Check that the device descriptor interface exists
        if not descriptor_interface:
            if dbg != 0:
                #print("[-] Device Descriptor Interface is Empty.... Was it created?")
                output_log_string = "[-] Device Descriptor Interface is Empty.... Was it created?"
                print_and_log(output_log_string)
        # Attempt to write to the descriptor value
        try:
            descriptor_interface.WriteValue([write_value], dict_options)
            return True
        except Exception as e:
            if dbg != 0:
                #print("[-] Device Descriptor Interface is Empty.... Was it created?")
                output_log_string = "[-] Device Descriptor Interface is Empty.... Was it created?"
                print_and_log(output_log_string)
        return False

    # Internal Function for Writing an ASCii string one byte at a time
    ## TODO: Encorporate mechanics of this into the larger class write command; should help with type conversion when writing
    def write__device__characteristic__one_byte_at_a_time(self, characteristic_interface, ascii_string, dict_options={}):
        if dbg != 0:
            #print("[*] Writing provided ASCii string")
            output_log_string = "[*] Writing provided ASCii string"
            print_and_log(output_log_string, LOG__DEBUG)
        encoded__ascii_string = self.ascii_string__to__dbus_value(ascii_string)
        for single_character in encoded__ascii_string:
            if dbg != 0:
                #print("\tEncoded Chatacter:\t{0}".format(single_character))
                output_log_string = "\tEncoded Chatacter:\t{0}".format(single_character)
                print_and_log(output_log_string, LOG__DEBUG)
            try:
                self.write__device__characteristic(characteristic_interface, single_character)
            except Exception as e:
                self.understand_and_handle__dbus_errors(e)
                return False
        if dbg != 0:
            #print("[+] Completed writing the ASCii string")
            output_log_string = "[+] Completed writing the ASCii string"
            print_and_log(output_log_string, LOG__DEBUG)
        return True
 
    # Internal Function for Connecting to the Device
    def Connect(self):
        # Check that the device_interface exists
        if not self.device_interface:
            # Create the device_interface
            self.create_and_set__device_interface()
        ## Attempt connection or return error; TODO
        try:
            # Connect to the Device using the Interface
            self.device_interface.Connect()
        except Exception as e:
            output_log_string = "[-] BLE Class::Connect\t-\tError Connecting:\t{0}".format(e)
            print_and_log(output_log_string, LOG__DEBUG)

    # Internal Function for Disconnecting from the Device
    def Disconnect(self):
        # Disconnect from the Device using the Interface
        self.device_interface.Disconnect()

    # Internal Function for Re-Connecting to a device   # TODO: Work on this
    def Reconnect_Check(self):
        out_log_string = "[*] BLE Class::Reconnect_Check\t-\tPerforming reconnect check"
        print_and_log(out_log_string, LOG__DEBUG)
        # TODO: Determine if this try statement should be allowed or not
        try:
            # Update the .device_connected variable; Note: SHOULD fix the issue of the .device_connected value being "stale"
            self.device_connected = self.find_and_get__device_property("Connected")
        except Exception as e:
            out_log_string = "[-] BLE Class::Reconnect_Check\t-\tException error was raised while retrieving Connected property\n\t{0}".format(e)
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            out_log_string = "[*] BLE Class::Reconnect_Check\t-\tCompleted retreiving Connected property without raising an error"
            print_and_log(out_log_string, LOG__DEBUG)
        finally:
            out_log_string = "[*] BLE Class::Reconnect_Check\t-\tFinal step of attempting to retrieve the Connected property"
            print_and_log(out_log_string, LOG__DEBUG)
        # Check if the device is connected
        if not self.device_connected:
            output_log_string = "[-] BLE Class::Reconnect_Check\t-\tDevice [ {0} ] is not connected".format(self.device_address)
            print_and_log(output_log_string, LOG__DEBUG)
            '''
            if self.rescan_flag:
                # Re-perform a scan for devices; TODO: Determine if this is the best use of where to call this....
                #   - Perhaps making the try statement too low level.... move up into the user interaction space
                create_and_return__bluetooth_scan__discovered_devices()
            '''
            # Call the internal Connect() function
            self.Connect()
        else:
            output_log_string = "[+] BLE Class::Reconnect_Check\t-\tDevice [{0}] is already connected".format(self.device_address)
            print_and_log(output_log_string, LOG__DEBUG)

    # Internal Function for Connecting to the Device
    #   - Expanded to allow the transfer of:
    #       i)      Reply Handler   -   Callback function that will be used to reply(?)
    #       ii)     Error Handler   -   Callback function that will be used when an error occurs
    #       iii)    Timeout         -   Timeout time in seconds(??) for the pairing action
    def Pair(self, reply_handler=None, error_handler=None, timeout=None):
        # Check that the device_interface exists
        if not self.device_interface:
            # Create the device_interface
            self.create_and_set__device_interface()
        if (reply_handler is None) and (error_handler is None) and (timeout is None):
            ## Attempt connection or return error; TODO
            try:
                # Connect to the Device using the Interface
                self.device_interface.Pair()
            except Exception as e:
                output_log_string = "[-] BLE Class::Default Pair\t-\tError Pair-ing:\t{0}".format(e)
                print_and_log(output_log_string, LOG__DEBUG)

    # Function for grabbing property values from an array
    def grab__properties_array__value(self, properties_array, properties_string):
        #print("[?] Searching for the string [ {0} ] in the properties array < {1} >".format(properties_string, properties_array))
        # Quick check to ensure there is a string value being passed
        if not properties_string:
            #print("[!] Properties String [ {0} ] is NoneType.... Returnning error")
            output_log_string = "[!] Properties String [ {0} ] is NoneType.... Returnning error"
            print_and_log(output_log_string)
            exit
        # Attempt to read the properties value
        try:
            properties_value = properties_array[properties_string]
            #print("\tProperty Value:\t{0}".format(''.join(chr(i) for i in properties_value)))
        except Exception as e:
            if dbg != 0:        # ~!~
                #print("\t[-] No Value [ {1} ] for this Property [ {2} ]\n\tERROR:\t{0}".format(e, properties_string, properties_array))
                output_log_string = "\t[-] No Value [ {1} ] for this Property [ {2} ]\n\tERROR:\t{0}".format(e, properties_string, properties_array)
                print_and_log(output_log_string)
            properties_value = None
        return properties_value

    # Internal Function for Enumerating the Device's Services, Characteristics, and Descriptors
    def enumerate_and_print__device__all_internals(self, nuclear_write=False):
        if dbg != 0:    # ~!~
            #print("[=] Warning! The generated Device Map will only be a skeleton of the target device. Reads have NOT been performed against the device yet...")
            output_log_string = "[=] BLE Class::enumerate_and_print__device__all_internals\tWarning! The generated Device Map will only be a skeleton of the target device. Reads have NOT been performed against the device yet..."
            print_and_log(output_log_string)
            print_and_log(output_log_string, LOG__ENUM)
        ## Santiy check for connectivity
        # Perform device re-check
        self.Reconnect_Check()      # TODO: Confirm this is a good place for this call
        if not self.device_connected:
            output_log_string = "[-] BLE Class::enumerate_and_print__device__all_internals\t-\tConnection still not present.... Going. to.. FAIL...... Returning Unkown Value...."
            print_and_log(output_log_string)
            print_and_log(output_log_string, LOG__ENUM)
            return UNKNOWN_VALUE
        ## Begin device enumeration
        # Create variable for generating a device map
        device__internals__map = { "Services" : {} }
        # Obtain the Device's Services List
        device_services_list = self.find_and_get__device_introspection__services()
        # Enumerate the Services
        for service_name in device_services_list:
            # Internal JSON mapping
            device__service__map = create_and_return__gatt__service_json()
            # Generate the Services elements to be used
            service_path, service_object, service_interface, service_properties, service_introspection = self.create_and_return__service__gatt_inspection_set(service_name)
            # Examine the Properties of the current Service
            service_properties_array = self.find_and_get__all_service_properties(service_properties)
            # Find and Return the Characteristics List for the current Service
            service_characteristics_list = self.find_and_get__device__etree_details(service_introspection, 'char')
            # Process and Pretty Print Service Information for UUID and Value
            #service_uuid = service_properties_array['UUID']
            service_uuid = self.grab__properties_array__value(service_properties_array, 'UUID')
            #print("Service UUID:\t{0}\t\t-\t\t{1}\t\t-\t\t[{2}]".format(service_uuid, bluetooth_utils.get_name_from_uuid(service_uuid), service_name))
            output_log_string = "Service UUID:\t{0}\t\t-\t\t{1}\t\t-\t\t[{2}]".format(service_uuid, bluetooth_utils.get_name_from_uuid(service_uuid), service_name)
            print_and_log(output_log_string)
            print_and_log(output_log_string, LOG__ENUM)
            # Read the service 'Value' field
            service_value = self.grab__properties_array__value(service_properties_array, 'Value')
            # Prepare all the service variables for adding to the map
            service_primary = self.grab__properties_array__value(service_properties_array, 'Primary')
            service_device = self.grab__properties_array__value(service_properties_array, 'Device')
            service_includes = self.grab__properties_array__value(service_properties_array, 'Includes')
            # Enumerate the Characteristics for the current Service
            for characteristic_name in service_characteristics_list:
                # Internal JSON mapping
                device__characteristic__map = create_and_return__gatt__characteristic_json()
                # Create elements for exploring the Characteristic
                characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = self.create_and_return__characteristic__gatt_inspection_set(service_path, characteristic_name)
                # Examine the Properties of the current Characteristic
                characteristic_properties_array = self.find_and_get__all_characteristic_properties(characteristic_properties)
                # Test read of characteristic_properties_array
                if dbg != 0:
                    out_log_string = "\t\t[?] Characteristic Properties Array:\t\t{0}".format(characteristic_properties_array)
                    print_and_log(out_log_string, LOG__DEBUG)
                # Find and Return the Descriptors List for the Characteristic
                characteristic_descriptors_list = self.find_and_get__device__etree_details(characteristic_introspection, 'desc')
                # Process and Pretty Print Characteristic Information for UUID and Flags
                characteristic_uuid = characteristic_properties_array['UUID']
                #characteristic_uuid = self.grab__properties_array__value(characteristic_properties_array, 'UUID')
                #print("\tCharacteristic UUID:\t{0}\t\t-\t\t{1}".format(characteristic_uuid, bluetooth_utils.get_name_from_uuid(characteristic_uuid)))
                # Display the Characteristic Handle
                #print("\tCharacteristic Handle:\t{0}".format(characteristic_name))
                # Note: Added the Characteristic Handle into the print out for the UUID
                #print("\tCharacteristic [{2}] UUID:\t{0}\t\t-\t\t{1}".format(characteristic_uuid, bluetooth_utils.get_name_from_uuid(characteristic_uuid), characteristic_name))
                #print("\tCharacteristic UUID:\t{0}\t\t-\t\t{1}\t\t-\t[{2}]".format(characteristic_uuid, bluetooth_utils.get_name_from_uuid(characteristic_uuid), characteristic_name))
                output_log_string = "\tCharacteristic UUID:\t{0}\t\t-\t\t{1}\t\t-\t[{2}]".format(characteristic_uuid, bluetooth_utils.get_name_from_uuid(characteristic_uuid), characteristic_name)
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__ENUM)
                # Setup the characteristic variables that will be fed into the device__characteristic__map
                #characteristic_flags = characteristic_properties_array['Flags']
                characteristic_flags = self.grab__properties_array__value(characteristic_properties_array, 'Flags')
                #print("\tCharacteristic Flags:\t{0}".format(characteristic_flags))
                output_log_string = "\tCharacteristic Flags:\t{0}".format(characteristic_flags)
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__ENUM)
                # Prepare all the characteristic variables for adding to the map
                characteristic_service = self.grab__properties_array__value(characteristic_properties_array, 'Service')
                characteristic_value = self.grab__properties_array__value(characteristic_properties_array, 'Value')
                # Testing value read
                if dbg != 0:
                    out_log_string = "\t\t[?] Characteristic Value Extracted:\t\t{0}".format(characteristic_value)
                    print_and_log(out_log_string, LOG__DEBUG)
                characteristic_writeAcquired = self.grab__properties_array__value(characteristic_properties_array, 'WriteAcquired')
                characteristic_notifyAcquired = self.grab__properties_array__value(characteristic_properties_array, 'NotifyAcquired')
                characteristic_notifying = self.grab__properties_array__value(characteristic_properties_array, 'Notifying')
                characteristic_mtu = self.grab__properties_array__value(characteristic_properties_array, 'MTU')
                # Check that the response was not NoneType
                if characteristic_flags:
                    # Check if the flag allows for a read; NOTE: Where the issues appears of the Characteristic Value being "None"; most likely due to the buffer not being populated from the previous read (i.e. characteristic_properties_array)
                    # TODO: Incorporate the dbus_read_value into the code; currently just uses the capability here and nowhere else
                    if "read" in characteristic_flags:
                        # Attempt ReadValue of the characteristic interface
                        #print("\tCharacteristic Value:\t{0}".format(self.read__device__characteristic(characteristic_interface)))
                        ## Check for the contents of the read and check if it should become ASCii converted
                        dbus_read_value = self.read__device__characteristic(characteristic_interface)
                        # Test the value of the dbus_read_value
                        if dbg != 0:
                            out_log_string = "\t\t[?] D-Bus Read Value:\t\t{0}".format(dbus_read_value)
                            print_and_log(out_log_string, LOG__DEBUG)
                        # Check to see what the returned data is
                        if isinstance(dbus_read_value, dbus.Array):
                            if dbg != 0:
                                #print("[!!] D-Bus Read Value is a D-Bus Array type!")
                                output_log_string = "[!!] D-Bus Read Value is a D-Bus Array type!"
                                print_and_log(output_log_string, LOG__DEBUG)
                            ## TODO: Check that the contents are ONLY D-Bus Bytes; then know to convert to ASCii
                            #print("\tCharacteristic Value (ASCii):\t{0}".format(self.dbus_read_value__to__ascii_string(self.read__device__characteristic(characteristic_interface))))
                            output_log_string = "\tCharacteristic Value (ASCii):\t{0}".format(self.dbus_read_value__to__ascii_string(self.read__device__characteristic(characteristic_interface)))
                            print_and_log(output_log_string)
                            print_and_log(output_log_string, LOG__ENUM)
                        else:
                            #print("\tCharacteristic Value:\t{0}".format(self.read__device__characteristic(characteristic_interface)))
                            output_log_string = "\tCharacteristic Value:\t{0}".format(self.read__device__characteristic(characteristic_interface))
                            print_and_log(output_log_string)
                            print_and_log(output_log_string, LOG__ENUM)
                    # Test Write ability        ||      NOTE: Added 'nuclear' flag for writing like crazy
                    if "write" in characteristic_flags:
                        # Check first if the function call desired the WRITE TO ALL THE THINGS flag (i.e. nuclear_write)
                        if nuclear_write:
                            #print("\t\t[*] Writes being attempted\t-\tActive Scan")
                            output_log_string = "\t\t[*] Writes being attempted\t-\tActive Scan"
                            print_and_log(output_log_string)
                            print_and_log(output_log_string, LOG__ENUM)
                            # Attempt to WriteValue of the characteristic interface
                            #self.write__device__characteristic(characteristic_interface, int(1))
                            if self.write__device__characteristic(characteristic_interface, int(1)):
                                #print("\t\t[+] Write\t-\tNon-Failure\t-\tUUID:\t{0}".format(characteristic_uuid))
                                output_log_string = "\t\t[+] Write\t-\tNon-Failure\t-\tUUID:\t{0}".format(characteristic_uuid)
                                print_and_log(output_log_string)
                                print_and_log(output_log_string, LOG__ENUM)
                            else:
                                #print("\t\t[-] Write\t-\tFailed\t-\tUUID:\t{0}".format(characteristic_uuid))
                                output_log_string = "\t\t[-] Write\t-\tFailed\t-\tUUID:\t{0}".format(characteristic_uuid)
                                print_and_log(output_log_string)
                                print_and_log(output_log_string, LOG__ENUM)
                        else:
                            #print("\t\t[-] Writes not being attempted\t-\tPassive Scan")
                            output_log_string = "\t\t[-] Writes not being attempted\t-\tDocile Scan"
                            print_and_log(output_log_string)
                            print_and_log(output_log_string, LOG__ENUM)
                else:
                    #print("\t[-] No Characteristic Flags")
                    output_log_string = "\t[-] No Characteristic Flags"
                    print_and_log(output_log_string)
                    print_and_log(output_log_string, LOG__ENUM)
                # Enumerate the Descriptors for the current Characteristic
                for descriptor_name in characteristic_descriptors_list:
                    # Internal JSON mapping
                    device__descriptor__map = create_and_return__gatt__descriptor_json()
                    # Create elements for exploring the Descriptor
                    descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = self.create_and_return__descriptor__gatt_inspection_set(characteristic_path, descriptor_name)
                    try:
                        if dbg != 0:
                            #print("[?] Descriptor Information:\n\tDescriptor Name:\t{0}\n\tDescriptors List:\t{1}".format(descriptor_name, characteristic_descriptors_list))
                            output_log_string = "[?] Descriptor Information:\n\tDescriptor Name:\t{0}\n\tDescriptors List:\t{1}".format(descriptor_name, characteristic_descriptors_list)
                            print_and_log(output_log_string, LOG__DEBUG)
                        # Examine the Properties of the current Descriptor 
                        descriptor_properties_array = self.find_and_get__all_descriptor_properties(descriptor_properties)
                        ## NOTE: The code below DOES NOT perform ANY sort of read action, this ONLY populates the device map using information generated from the initial connection to the BLE device
                        ##  -> This is because the information is produced by the underlying Linux D-Bus, which has not performed any reads of Services/Characteristics/Descriptors that were enumerated upon the ServicesResolved() call from Connect()
                        ##      - Further moore, GATT Descriptors SPECIFICALLY will ONLY populate the 'Value' field AFTER a .ReadValue() method call has occured (e.g. has to have happened once before data is provided)
                        ##          - Side Note: Arduino will NOT allow for an individual to write to a Descriptor Field (standard? limitation?)
                        ##      - Confirmed through PAINFUL checking between Python CLI and 'busctl' commands
                        # Process and Pretty Print Descriptor Information for UUID
                        #descriptor_uuid = descriptor_properties_array['UUID']
                        descriptor_uuid = self.grab__properties_array__value(descriptor_properties_array, 'UUID')
                        #print("\t\tDescriptor UUID:\t{0}\t\t-\t\t{1}\t\t-\t\t[{2}]".format(descriptor_uuid, bluetooth_utils.get_name_from_uuid(descriptor_uuid), descriptor_name))
                        output_log_string = "\t\tDescriptor UUID:\t{0}\t\t-\t\t{1}\t\t-\t\t[{2}]".format(descriptor_uuid, bluetooth_utils.get_name_from_uuid(descriptor_uuid), descriptor_name)
                        print_and_log(output_log_string)
                        print_and_log(output_log_string, LOG__ENUM)
                        #descriptor_value = descriptor_properties_array['Value']
                        descriptor_value = self.grab__properties_array__value(descriptor_properties_array, 'Value')
                        #print("\t\tDescriptor Value:\t{0}".format(descriptor_value))
                        output_log_string = "\t\tDescriptor Value:\t{0}".format(descriptor_value)
                        print_and_log(output_log_string)
                        print_and_log(output_log_string, LOG__ENUM)
                        # Prepare all the descriptor variables for adding to the map
                        descriptor_characteristic = self.grab__properties_array__value(descriptor_properties_array, 'Characteristic')
                        descriptor_flags = self.grab__properties_array__value(descriptor_properties_array, 'Flags')
                        # Update the current descriptor map
                        device__descriptor__map["UUID"] = descriptor_uuid
                        device__descriptor__map["Characteristic"] = descriptor_characteristic
                        device__descriptor__map["Value"] = descriptor_value
                        device__descriptor__map["Flags"] = descriptor_flags
                    except Exception as e:
                        self.understand_and_handle__dbus_errors(e)
                        #print("\t\t[-] Descriptor Access Error")
                        output_log_string = "\t\t[-] Descriptor Access Error"
                        print_and_log(output_log_string)
                        print_and_log(output_log_string, LOG__ENUM)
                    # Update the current descriptor map
                    device__characteristic__map["Descriptors"][descriptor_name] = device__descriptor__map
                # Update the current characteristic map
                device__characteristic__map["UUID"] = characteristic_uuid
                device__characteristic__map["Service"] = characteristic_service
                device__characteristic__map["Value"] = characteristic_value
                device__characteristic__map["WriteAcquired"] = characteristic_writeAcquired
                device__characteristic__map["NotifyAcquired"] = characteristic_notifyAcquired
                device__characteristic__map["Notifying"] = characteristic_notifying
                device__characteristic__map["Flags"] = characteristic_flags
                device__characteristic__map["MTU"] = characteristic_mtu
                device__service__map["Characteristics"][characteristic_name] = device__characteristic__map
            # Update the current services map
            device__service__map["UUID"] = service_uuid
            device__service__map["Value"] = service_value
            device__service__map["Primary"] = service_primary
            device__service__map["Device"] = service_device
            device__service__map["Includes"] = service_includes
            # Update the device map
            device__internals__map["Services"][service_name] = device__service__map
        # Return the mapping that was generated
        return device__internals__map

    # Internal Function for Generating a New Device Internals Map
    ## TODO: Create function for generating an entirely new map
    ## TODO: Create function for reading and updating ALL S/C/D + version for specific update

    # Internal Function for Updating and Existing Device Map with New Information
    ## Note: This is ONLY useful for updating KNOWN information; not NEW S/C/D that have appeared
    def enumerate_and_update__device__all_internals(self, old__device__internals__map):
        #print("[*] Updating the Device Internals Map [ Full Enumeration ]")
        output_log_string = "[*] Updating the Device Internals Map [ Full Enumeration ]"
        print_and_log(output_log_string)
        if dbg != 0:
            #print("\tOld Device Internals Map:\t{0}".format(old__device__internals__map))
            output_log_string = "\tOld Device Internals Map:\t{0}".format(old__device__internals__map)
            print_and_log(output_log_string, LOG__DEBUG)
        ## Code to re-read thorugh the old map and update KNOWN entries
        # Create variable for generating a device map
        device__internals__map = { "Services" : {} }
        # Obtain the Device's Services List;    KEEP: Does a fresh read of the information on the device
        device_services_list = self.find_and_get__device_introspection__services()
        # Enumerate the Services
        for service_name in device_services_list:
            # Internal JSON mapping
            device__service__map = create_and_return__gatt__service_json()
            # Generate the Services elements to be used
            service_path, service_object, service_interface, service_properties, service_introspection = self.create_and_return__service__gatt_inspection_set(service_name)
            # Examine the Properties of the current Service
            service_properties_array = self.find_and_get__all_service_properties(service_properties)
            # Find and Return the Characteristics List for the current Service
            service_characteristics_list = self.find_and_get__device__etree_details(service_introspection, 'char')
            # Process and Pretty Print Service Information for UUID and Value
            #service_uuid = service_properties_array['UUID']
            service_uuid = self.grab__properties_array__value(service_properties_array, 'UUID')
            if dbg != 0:
                #print("Service UUID:\t{0}\t\t-\t\t{1}".format(service_uuid, bluetooth_utils.get_name_from_uuid(service_uuid)))
                output_log_string = "Service UUID:\t{0}\t\t-\t\t{1}".format(service_uuid, bluetooth_utils.get_name_from_uuid(service_uuid))
                print_and_log(output_log_string, LOG__DEBUG)
            # Read the service 'Value' field
            service_value = self.grab__properties_array__value(service_properties_array, 'Value')
            # Prepare all the service variables for adding to the map
            service_primary = self.grab__properties_array__value(service_properties_array, 'Primary')
            service_device = self.grab__properties_array__value(service_properties_array, 'Device')
            service_includes = self.grab__properties_array__value(service_properties_array, 'Includes')
            # Enumerate the Characteristics for the current Service
            for characteristic_name in service_characteristics_list:
                # Internal JSON mapping
                device__characteristic__map = create_and_return__gatt__characteristic_json()
                # Create elements for exploring the Characteristic
                characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = self.create_and_return__characteristic__gatt_inspection_set(service_path, characteristic_name)
                # Examine the Properties of the current Characteristic
                characteristic_properties_array = self.find_and_get__all_characteristic_properties(characteristic_properties)
                # Find and Return the Descriptors List for the Characteristic
                characteristic_descriptors_list = self.find_and_get__device__etree_details(characteristic_introspection, 'desc')
                # Process and Pretty Print Characteristic Information for UUID and Flags
                #characteristic_uuid = characteristic_properties_array['UUID']
                characteristic_uuid = self.grab__properties_array__value(characteristic_properties_array, 'UUID')
                if dbg != 0:
                    #print("\tCharacteristic UUID:\t{0}\t\t-\t\t{1}".format(characteristic_uuid, bluetooth_utils.get_name_from_uuid(characteristic_uuid)))
                    output_log_string = "\tCharacteristic UUID:\t{0}\t\t-\t\t{1}".format(characteristic_uuid, bluetooth_utils.get_name_from_uuid(characteristic_uuid))
                    print_and_log(output_log_string, LOG__DEBUG)
                # Setup the characteristic variables that will be fed into the device__characteristic__map
                #characteristic_flags = characteristic_properties_array['Flags']
                characteristic_flags = self.grab__properties_array__value(characteristic_properties_array, 'Flags')
                if dbg != 0:
                    #print("\tCharacteristic Flags:\t{0}".format(characteristic_flags))
                    output_log_string = "\tCharacteristic Flags:\t{0}".format(characteristic_flags)
                    print_and_log(output_log_string, LOG__DEBUG)
                # Prepare all the characteristic variables for adding to the map
                characteristic_service = self.grab__properties_array__value(characteristic_properties_array, 'Service')
                characteristic_value = self.grab__properties_array__value(characteristic_properties_array, 'Value')
                characteristic_writeAcquired = self.grab__properties_array__value(characteristic_properties_array, 'WriteAcquired')
                characteristic_notifyAcquired = self.grab__properties_array__value(characteristic_properties_array, 'NotifyAcquired')
                characteristic_notifying = self.grab__properties_array__value(characteristic_properties_array, 'Notifying')
                characteristic_mtu = self.grab__properties_array__value(characteristic_properties_array, 'MTU')
                # Check that the response was not NoneType
                if characteristic_flags:
                    # Check if the flag allows for a read
                    if "read" in characteristic_flags:
                        # Attempt ReadValue of the characteristic interface
                        #print("\tCharacteristic Value:\t{0}".format(self.read__device__characteristic(characteristic_interface)))
                        ## Check for the contents of the read and check if it should become ASCii converted
                        dbus_read_value = self.read__device__characteristic(characteristic_interface)
                        # Check to see what the returned data is
                        if isinstance(dbus_read_value, dbus.Array):
                            if dbg != 0:
                                #print("[!!] D-Bus Read Value is a D-Bus Array type!")
                                output_log_string = "[!!] D-Bus Read Value is a D-Bus Array type!"
                                print_and_log(output_log_string, LOG__DEBUG)
                            ## TODO: Check that the contents are ONLY D-Bus Bytes; then know to convert to ASCii
                            if dbg != 0:
                                #print("\tCharacteristic Value (ASCii):\t{0}".format(self.dbus_read_value__to__ascii_string(self., landmine_map, security_mapread__device__characteristic(characteristic_interface))))
                                output_log_string = "\tCharacteristic Value (ASCii):\t{0}".format(self.dbus_read_value__to__ascii_string(self.read__device__characteristic(characteristic_interface)))
                                print_and_log(output_log_string, LOG__DEBUG)
                        else:
                            if dbg != 0:
                                #print("\tCharacteristic Value:\t{0}".format(self.read__device__characteristic(characteristic_interface)))
                                output_log_string = "\tCharacteristic Value:\t{0}".format(self.read__device__characteristic(characteristic_interface))
                                print_and_log(output_log_string, LOG__DEBUG)
                    '''     NO NEED TO RUN THIS DURING AN UPDATE ???
                    # Test Write ability
                    if "write" in characteristic_flags:
                        # Attempt to WriteValue of the characteristic interface
                        #self.write__device__characteristic(characteristic_interface, int(1))
                        if self.write__device__characteristic(characteristic_interface, int(1)):
                            if dbg != 0:
                                print("\t\t[+] Write\t-\tNon-Failure\t-\tUUID:\t{0}".format(characteristic_uuid))
                        else:
                            if dbg != 0:
                                print("\t\t[-] Write\t-\tFailed\t-\tUUID:\t{0}".format(characteristic_uuid))
                    '''
                else:
                    if dbg != 0:
                        #print("\t[-] No Characteristic Flags")
                        output_log_string = "\t[-] No Characteristic Flags"
                        print_and_log(output_log_string, LOG__DEBUG)
                # Enumerate the Descriptors for the current Characteristic
                for descriptor_name in characteristic_descriptors_list:
                    # Internal JSON mapping
                    device__descriptor__map = create_and_return__gatt__descriptor_json()
                    # Create elements for exploring the Descriptor
                    descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = self.create_and_return__descriptor__gatt_inspection_set(characteristic_path, descriptor_name)
                    try:
                        if dbg != 0:
                            #print("[?] Descriptor Information:\n\tDescriptor Name:\t{0}\n\tDescriptors List:\t{1}".format(descriptor_name, characteristic_descriptors_list))
                            output_log_string = "[?] Descriptor Information:\n\tDescriptor Name:\t{0}\n\tDescriptors List:\t{1}".format(descriptor_name, characteristic_descriptors_list)
                            print_and_log(output_log_string, LOG__DEBUG)
                        # Examine the Properties of the current Descriptor 
                        descriptor_properties_array = self.find_and_get__all_descriptor_properties(descriptor_properties)
                        # Process and Pretty Print Descriptor Information for UUID
                        #descriptor_uuid = descriptor_properties_array['UUID']
                        descriptor_uuid = self.grab__properties_array__value(descriptor_properties_array, 'UUID')
                        if dbg != 0:
                            #print("\t\tDescriptor UUID:\t{0}\t\t-\t\t{1}".format(descriptor_uuid, bluetooth_utils.get_name_from_uuid(descriptor_uuid)))
                            output_log_string = "\t\tDescriptor UUID:\t{0}\t\t-\t\t{1}".format(descriptor_uuid, bluetooth_utils.get_name_from_uuid(descriptor_uuid))
                            print_and_log(output_log_string, LOG__DEBUG)
                        #descriptor_value = descriptor_properties_array['Value']
                        descriptor_value = self.grab__properties_array__value(descriptor_properties_array, 'Value')
                        if dbg != 0:
                            #print("\t\tDescriptor Value:\t{0}".format(descriptor_value))
                            output_log_string = "\t\tDescriptor Value:\t{0}".format(descriptor_value)
                            print_and_log(output_log_string, LOG__DEBUG)
                        # Prepare all the descriptor variables for adding to the map
                        descriptor_characteristic = self.grab__properties_array__value(descriptor_properties_array, 'Characteristic')
                        descriptor_flags = self.grab__properties_array__value(descriptor_properties_array, 'Flags')
                        # Update the current descriptor map
                        device__descriptor__map["UUID"] = descriptor_uuid
                        device__descriptor__map["Characteristic"] = descriptor_characteristic
                        device__descriptor__map["Value"] = descriptor_value
                        device__descriptor__map["Flags"] = descriptor_flags
                    except Exception as e:
                        self.understand_and_handle__dbus_errors(e)
                        if dbg != 0:
                            #print("\t\t[-] Descriptor Access Error")
                            output_log_string = "\t\t[-] Descriptor Access Error"
                            print_and_log(output_log_string, LOG__DEBUG)
                    # Update the current descriptor map
                    device__characteristic__map["Descriptors"][descriptor_name] = device__descriptor__map
                # Update the current characteristic map
                device__characteristic__map["UUID"] = characteristic_uuid
                device__characteristic__map["Service"] = characteristic_service
                device__characteristic__map["Value"] = characteristic_value
                device__characteristic__map["WriteAcquired"] = characteristic_writeAcquired
                device__characteristic__map["NotifyAcquired"] = characteristic_notifyAcquired
                device__characteristic__map["Notifying"] = characteristic_notifying
                device__characteristic__map["Flags"] = characteristic_flags
                device__characteristic__map["MTU"] = characteristic_mtu
                device__service__map["Characteristics"][characteristic_name] = device__characteristic__map
            # Update the current services map
            device__service__map["UUID"] = service_uuid
            device__service__map["Value"] = service_value
            device__service__map["Primary"] = service_primary
            device__service__map["Device"] = service_device
            device__service__map["Includes"] = service_includes
            # Update the device map
            device__internals__map["Services"][service_name] = device__service__map
        ## TODO: Add check for differences between the old device map and the current device internals map
        # Return the mapping that was generated
        return device__internals__map

    # Internal Function for Waiting until the Services have been Resolved for the Device
    #   - Added timeout for the "Service Resolution" check; NOTE: This addition MUST be verified with the rest of the code operaiton (i.e. Does this cause issues with larger operaiton?)
    def check_and_wait__services_resolved(self):
        output_log_string = "[*] Waiting for device [ {0} ] services to be resolved".format(self.device_address)
        print("[*] Waiting for device [ {0} ] services to be resolved".format(self.device_address), end='')
        # Variables for tracking time to wait for "ServicesResolved"
        time_sleep__seconds = 0.5
        total_time_passed__seconds = 0
        # Hang and wait to make sure that the services are resolved
        while not self.find_and_get__device_property("ServicesResolved"):
            time.sleep(time_sleep__seconds)      # Sleep to give time for Services to Resolve
            print(".", end='')
            output_log_string += '.'
            # Check for abandoning "ServicesResolved"
            if total_time_passed__seconds > timeout_limit__in_seconds:
                print_and_log(output_log_string)
                # Configured seconds have passed attempting to resolve services, quit and move on
                output_log_string = "[-] Service Resolving Error:\tTimeout Limit Reached"
                print_and_log(output_log_string, LOG__DEBUG)
                break
            # Add to the timeout counter
            total_time_passed__seconds += time_sleep__seconds
        # Sanity check for debugging
        if self.find_and_get__device_property("ServicesResolved"):
            print_and_log(output_log_string)
            output_log_string = "\n[+] Device services resolved!"
            print_and_log(output_log_string)
            #print_and_log(output_log_string, LOG__ENUM)
        else:
            output_log_string = "\n[-] Device services not resolved"
            print_and_log(output_log_string)
            #print_and_log(output_log_String, LOG__ENUM)

    ## Internal Functions for Exploring a Device Internals Map

    # Internal Function for Returning a List of Mapped Services
    def find_and_return__internal_map__services_list(self, device__internals_map):
        #print("[*] Finding and Returing the List of Services from Internals Map")
        output_log_string = "[*] Finding and Returing the List of Services from Internals Map"
        print_and_log(output_log_string)
        services_list = []
        # Loop through the Device Internals Map and Build the List of Services
        for service_name in device__internals_map["Services"]:
            if dbg != 0:
                #print("\tService Name Found:\t{0}".format(service_name))
                output_log_string = "\tService Name Found:\t{0}".format(service_name)
                print_and_log(output_log_string, LOG__DEBUG)
            services_list.append(service_name)
        #print("[+] Returing Found List of Services")
        output_log_string = "[+] Returing Found List of Services"
        print_and_log(output_log_string)
        return services_list

    # Internal Function for Returning a List of Mapped Characteristics
    def find_and_return__internal_map__characteristics_list(self, device__internals_map):
        #print("[*] Finding and Returning the List of Characteristics from Internals Map")
        output_log_string = "[*] Finding and Returning the List of Characteristics from Internals Map"
        print_and_log(output_log_string)
        characteristics_list = []
        # Loop through the Device Internals Map and Build the List of Services
        for service_name in device__internals_map["Services"]:
            for characteristic_name in device__internals_map["Services"][service_name]["Characteristics"]:
                if dbg != 1:
                    #print("\tCharacteristic Name Found:\t{0}")
                    output_log_string = "\tCharacteristic Name Found:\t{0}".format(characteristic_name)
                    print_and_log(output_log_string, LOG__DEBUG)
                characteristics_list.append(characteristic_name)
        #print("[+] Returning Found List of Characteristics")
        output_log_string = "[+] Returning Found List of Characteristics"
        print_and_log(output_log_string)
        return characteristics_list

    # Internal Function for Returning a List of Mapped Descriptors
    def find_and_return__internal_map__descriptors_list(self, device__internals_map):
        #print("[*] Finding and Returning the List of Descriptors from Intnernals Map")
        output_log_string = "[*] Finding and Returning the List of Descriptors from Intnernals Map"
        print_and_log(output_log_string)
        descriptors_list = []
        # Loop through the Device Internals Map and Build the List of Services
        for service_name in device__internals_map["Services"]:
            for characteristic_name in device__internals_map["Services"][service_name]["Characteristics"]:
                for descriptor_name in device__internals_map["Services"][service_name]["Characteristics"][characteristic_name]["Descriptors"]:
                    if dbg != 0:
                        #print("\tDescriptor Name Found:\t{0}")
                        output_log_string = "\tDescriptor Name Found:\t{0}"
                        print_and_log(output_log_string, LOG__DEBUG)
                    descriptors_list.append(descriptor_name)
        #print("[+] Returning Found List of Descriptors")
        output_log_string = "[+] Returning Found List of Descriptors"
        print_and_log(output_log_string)
        return descriptors_list

    # Internal Function for Returning Detailed Information of a Mapped Service
    def find_and_return__internal_map__detailed_service(self, device__internals_map, specific_service):
        if dbg != 0:
            #print("[*] Find and Return Detailed Information of a Specific Services from Internals Map")
            output_log_string = "[*] Find and Return Detailed Information of a Specific Services from Internals Map"
            print_and_log(output_log_string, LOG__DEBUG)
        detailed_service_information = None
        for service_name in device__internals_map["Services"]:
            if service_name == specific_service:
                if dbg != 0:
                    #print("[+] Found the desired service [ {0} ]".format(specific_service))
                    output_log_string = "[+] Found the desired service [ {0} ]".format(specific_service)
                    print_and_log(output_log_string, LOG__DEBUG)
                # Collect detailed information of the service
                detailed_service_information = device__internals_map["Services"][service_name]
        # Check if anything was found
        if detailed_service_information:
            return detailed_service_information
        else:
            #print("[-] Desired Service NOT FOUND")
            output_log_string = "[-] Desired Service NOT FOUND"
            print_and_log(output_log_string)
            return None

    # Internal Function for Returning Detailed Information of a Mapped Characteristic
    def find_and_return__internal_map__detailed_characteristic(self, device__internals_map, specific_characteristic):
        if dbg != 0:
            #print("[*] Find and Return Detailed Information of a Specific Characteristic from Internals Map")
            output_log_string = "[*] Find and Return Detailed Information of a Specific Characteristic from Internals Map"
            print_and_log(output_log_string, LOG__DEBUG)
        detailed_characteristic_information = None
        for service_name in device__internals_map["Services"]:
            for characteristic_name in device__internals_map["Services"][service_name]["Characteristics"]:
                if characteristic_name == specific_characteristic:
                    if dbg != 0:
                        #print("[+] Found the desired characteristc [ {0} ]".format(specific_characteristic))
                        output_log_string = "[+] Found the desired characteristc [ {0} ]".format(specific_characteristic)
                        print_and_log(output_log_string, LOG__DEBUG)
                    # Collect detailed information of the characteristic
                    detailed_characteristic_information = device__internals_map["Services"][service_name]["Characteristics"][characteristic_name]
        # Check if anything was found
        if detailed_characteristic_information:
            return detailed_characteristic_information
        else:
            #print("[-] Desired Characteristic NOT FOUND")
            output_log_string = "[-] Desired Characteristic NOT FOUND"
            print_and_log(output_log_string)
            return None
    
    # Internal Function for Returning Detailed Information of a Mapped Descriptor
    def find_and_return__internal_map__detailed_descriptor(self, device__internals_map, specific_descriptor):
        if dbg != 0:
            #print("[*] Find and Return Detailed Information of a Specific Descriptor from Intnerals Map")
            output_log_string = "[*] Find and Return Detailed Information of a Specific Descriptor from Intnerals Map"
            print_and_log(output_log_string, LOG__DEBUG)
        detailed_descriptor_information = None
        for service_name in device__internals_map["Services"]:
            for characteristic_name in device__internals_map["Services"][service_name]["Characteristics"]:
                for descriptor_name in device__internals_map["Services"][service_name]["Characteristics"][characteristic_name]["Descriptors"]:
                    if descriptor_name == specific_descriptor:
                        if dbg != 0:
                            #print("[+] Found the desired descriptor [ {0} ]".format(specific_descriptor))
                            output_log_string = "[+] Found the desired descriptor [ {0} ]".format(specific_descriptor)
                            print_and_log(output_log_string, LOG__DEBUG)
                        # Collect detailed information of the descriptor
                        detailed_descriptor_information = device__internals_map["Services"][service_name]["Characteristics"][characteristic_name]["Descriptors"][descriptor_name]
                        # NOTE: This ONLY reads from the ALREADY produced map, NOT FRESH FROM THE DEVICE
        # Check if anything was found
        if detailed_descriptor_information:
            return detailed_descriptor_information
        else:
            #print("[-] Desired Descriptor NOT FOUND")
            output_log_string = "[-] Desired Descriptor NOT FOUND"
            print_and_log(output_log_string)
            return None

    # Internal Function for Finding a Specific Characteristic based on Name and Returning All Associated Structures
    def find_and_return__characteristic__gatt_inspection_set(self, characteristic_name):
        # Generate the Internals Map
        user_device__internals_map = self.enumerate_and_print__device__all_internals()
        #characteristic_name = "char0008"
        # Extract the information from the Internals Map based on the Characteristic's Name
        detailed_characteristic = self.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
        # Extract the Characteristic's Service Path
        characteristic_service_path = detailed_characteristic["Service"]
        # Create the FIVE GATT objects required for full inspection of the Characteristic
        characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = self.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
        # Note: Might be able to just return the result of the function call above
        return characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection
   
    # Internal Function for Pretty Printing Detailed Information of a Service
    def pretty_print__gatt__service__detailed_information(self, service__detailed_information, log_type=LOG__GENERAL):
        #print("----------\t Start of Detailed Pretty Print of Service Information Provided")
        output_log_string = "----------\t Start of Detailed Pretty Print of Service Information Provided"
        #output_log_string = "----------\t Start of Detailed Pretty Print of Service [ {0} ] Information".format(service__detailed_information)
        print_and_log(output_log_string)
        for service_property in service__detailed_information:
            if service_property in GATT__SERVICE__PROPERTIES:
                if dbg != 0:
                    #print("[!] The property [ {0} ] is in the GATT__SERVICE__PROPERTIES".format(service_property))
                    output_log_string = "[!] The property [ {0} ] is in the GATT__SERVICE__PROPERTIES".format(service_property)
                    print_and_log(output_log_string, LOG__DEBUG)
                if len(service_property) < PRETTY_PRINT__GATT__FORMAT_LEN:
                    #print("\t{0}:\t\t\t{1}".format(service_property, service__detailed_information[service_property]))
                    output_log_string = "\t{0}:\t\t\t{1}".format(service_property, service__detailed_information[service_property])
                    print_and_log(output_log_string, log_type)
                else:
                    #print("\t{0}:\t\t{1}".format(service_property, service__detailed_information[service_property]))
                    output_log_string = "\t{0}:\t\t{1}".format(service_property, service__detailed_information[service_property])
                    print_and_log(output_log_string, log_type)
            else:
                #print("[!] The property [ {0} ] is NOT an expected GATT__SERVICE__PROPERTIES".format(service_property))
                output_log_string = "[!] The property [ {0} ] is NOT an expected GATT__SERVICE__PROPERTIES\n\t{0}:\t\t\t{1}".format(service_property, service__detailed_information[service_property])
                print_and_log(output_log_string, log_type)
        #print("---\tEnd of Service Detailed Information")
        output_log_string = "---\tEnd of Service Detailed Information"
        print_and_log(output_log_string, log_type)
            
    # Internal Function for Pretty Printing Detailed Information of a Characteristic
    def pretty_print__gatt__characteristic__detailed_information(self, characteristic__detailed_information, log_type=LOG__GENERAL):
        #print("----------\t Start of Detailed Pretty Print of Characteristic Information Provided")
        output_log_string = "----------\t Start of Detailed Pretty Print of Characteristic Information Provided"
        #output_log_string = "----------\t Start of Detailed Pretty Print of Characteristic [ {0} ] Information".format(characteristic__detailed_information)
        print_and_log(output_log_string)
        for characteristic_property in characteristic__detailed_information:
            if characteristic_property in GATT__CHARACTERISTIC__PROPERTIES:
                if dbg != 0:
                    #print("[!] The property [ {0} ] is in the GATT__CHARACTERISTIC__PROPERTIES".format(characteristic_property))
                    output_log_string = "[!] The property [ {0} ] is in the GATT__CHARACTERISTIC__PROPERTIES".format(characteristic_property)
                    print_and_log(output_log_string, LOG__DEBUG)
                # NOTE: This is not where to translate D-Bus Arrays into ASCii strings?  
                read_value = characteristic__detailed_information[characteristic_property]
                if len(characteristic_property) < PRETTY_PRINT__GATT__FORMAT_LEN:
                    if characteristic_property == "Value":
                        #print("\t{0}:\t\t\t{1}".format(characteristic_property, self.dbus_read_value__to__ascii_string(read_value)))
                        output_log_string = "\t{0}:\t\t\t{1}".format(characteristic_property, self.dbus_read_value__to__ascii_string(read_value))
                        print_and_log(output_log_string, log_type)
                    else:
                        #print("\t{0}:\t\t\t{1}".format(characteristic_property, characteristic__detailed_information[characteristic_property]))
                        output_log_string = "\t{0}:\t\t\t{1}".format(characteristic_property, characteristic__detailed_information[characteristic_property])
                        print_and_log(output_log_string, log_type)
                else:
                    #print("\t{0}:\t\t{1}".format(characteristic_property, characteristic__detailed_information[characteristic_property]))
                    output_log_string = "\t{0}:\t\t{1}".format(characteristic_property, characteristic__detailed_information[characteristic_property])
                    print_and_log(output_log_string, log_type)
            else:
                #print("[!] The property [ {0} ] is NOT an expected GATT__CHARACTERISTIC__PROPERTIES\n\t{0}:\t\t\t{1}".format(characteristic_property, characteristic__detailed_information[characteristic_property]))
                output_log_string = "[!] The property [ {0} ] is NOT an expected GATT__CHARACTERISTIC__PROPERTIES\n\t{0}:\t\t\t{1}".format(characteristic_property, characteristic__detailed_information[characteristic_property])
                print_and_log(output_log_string, log_type)
        #print("---\tEnd of Characteristic Detailed Infomration")
        output_log_string = "---\tEnd of Characteristic Detailed Infomration"
        print_and_log(output_log_string, log_type)

    # Internal Function for Pretty Printing Detailed Information of a Descriptor
    def pretty_print__gatt__descriptor__detailed_information(self, descriptor__detailed_information, log_type=LOG__GENERAL):
        #print("----------\t Start of Detailed Pretty Print of Descriptor Information Provided")
        output_log_string = "----------\t Start of Detailed Pretty Print of Descriptor Information Provided"
        #output_log_string = "----------\t Start of Detailed Pretty Print of Descriptor [ {0} ] Information".format(descriptor__detailed_information)
        print_and_log(output_log_string)
        for descriptor_property in descriptor__detailed_information:
            if descriptor_property in GATT__DESCRIPTOR__PROPERTIES:
                if dbg != 0:
                    #print("[!] The property [ {0} ] is in the GATT__DESCRIPTOR__PROPERTIES".format(descriptor_property))
                    output_log_string = "[!] The property [ {0} ] is in the GATT__DESCRIPTOR__PROPERTIES".format(descriptor_property)
                    print_and_log(output_log_string, LOG__DEBUG)
                if len(descriptor_property) < PRETTY_PRINT__GATT__FORMAT_LEN:
                    #print("\t{0}:\t\t\t{1}".format(descriptor_property, descriptor__detailed_information[descriptor_property]))
                    output_log_string = "\t{0}:\t\t\t{1}".format(descriptor_property, descriptor__detailed_information[descriptor_property])
                    print_and_log(output_log_string, log_type)
                else:
                    #print("\t{0}:\t\t{1}".format(descriptor_property, descriptor__detailed_information[descriptor_property]))
                    output_log_string = "\t{0}:\t\t{1}".format(descriptor_property, descriptor__detailed_information[descriptor_property])
                    print_and_log(output_log_string, log_type)
            else:
                #print("[!] The property [ {0} ] is NOT an expected GATT__DESCRIPTOR__PROPERTIES\n\t{0}:\t\t\t{1}".format(descriptor_property, descriptor__detailed_information[descriptor_property]))
                output_log_string = "[!] The property [ {0} ] is NOT an expected GATT__DESCRIPTOR__PROPERTIES\n\t{0}:\t\t\t{1}".format(descriptor_property, descriptor__detailed_information[descriptor_property])
                print_and_log(output_log_string, log_type)
        #print("---\tEnd of Descriptor Detailed Inofrmation")
        output_log_string = "---\tEnd of Descriptor Detailed Inofrmation"
        print_and_log(output_log_string, log_type)

    ## TODO: Write functions for simplfiying the output for Characteristics and Descriptors when pretty printing the S/C/D
    # Function for translating D-Bus Array made of D-Bus Bytes to ASCii string
    def dbus_read_value__to__ascii_string(self, dbus_read_value):
        if dbg != 0:
            #print("[*] Converting D-Bus Array into ASCii String")
            output_log_string = "[*] Converting D-Bus Array into ASCii String"
            print_and_log(output_log_string)
        # Add try statement for error handling improvement
        try:
            ascii_string = convert__hex_to_ascii(dbus_read_value)
            if dbg != 0:
                output_log_string = "[+] Converted D-Bus Array into ASCii String"
                print_and_log(output_log_string, LOG__DEBUG)
        except Exception as e:
            if dbg != 0:
                output_log_string = "[-] Unable to perform ReadValue()\t-\tCharacteristic"
                print_and_log(output_log_string, LOG__DEBUG)
            output_log_string = "[-] system_dbus__bluez_signals::dbus_read_value__to__ascii_string\t-\tHex to ASCii Conversion Error\t-\tASCii String set to None"
            print_and_log(output_log_string)
            self.understand_and_handle__dbus_errors(e)
            ascii_string = None
        return ascii_string

    # Function for translating D-Bus Array made if D-Bus Bytes to a Hex string
    def dbus_read_value__to__hex_string(self, dbus_read_value):
        if dbg != 0:
            #print("[*] Converting D-Bus Array into Hex String")
            output_log_string = "[*] Converting D-Bus Array into Hex String"
            print_and_log(output_log_string)
        hex_string = convert__dbus_to_hex(dbus_read_value)
        if dbg != 0:
            #print("[+] Converted D-Bus Array into ASCii string")
            output_log_string = "[+] Converted D-Bus Array into ASCii string"
            print(output_log_string)
        return hex_string

    # Function for translating an ASCii string into a D-Bus Byte Array
    #   - Note: This function uses UTF-8 encoding
    ## TODO: Check if writing should be in HEX or not
    def ascii_string__to__dbus_value(self, ascii_string):
        if dbg != 0:
            #print("[*] Converting ASCii string into D-Bus Array of D-Bus Bytes")
            output_log_string = "[*] Converting ASCii string into D-Bus Array of D-Bus Bytes"
            print_and_log(output_log_string, LOG__DEBUG)
        # Encode the provided ASCii string as UTF-8
        #encoded__ascii_string = ascii_string.encode('utf-8')
        # Encode the provided string as ASCii
        encoded__ascii_string = ascii_string.encode('ascii')
        # Convert encoded string into hex
        hex_value = encoded__ascii_string.hex()
        # Create Variable for holding the temporary array
        temp_array = []
        '''
        # Loop for Creating the array of D-Bus Bytes
        for character_item in range(0, len(encoded__ascii_string), 1):
            if dbg != 0:
                print("Encoded Character:\t{0}".format(encoded__ascii_string[character_item]))
            temp_array.append(dbus.Byte(encoded__ascii_string[character_item]))
        # Create the final D-Bus Array
        dbus_value = dbus.Array(temp_array)         # Nope, this give an error about the TypeError and expecting an int
        '''
        '''
        # Loop for Creating a hex array
        for character_item in range(0, len(hex_value), 2 ):
            if dbg != 0:
                print("Hex Character:\t{0}".format(hex_value[character_item:character_item + 2]))
            temp_array.append(hex_value[character_item:character_item + 2])
        # Create the final Hex Array
        dbus_value = temp_array
        '''
        # Loop for Creating the array of ASCii int values
        for character_item in encoded__ascii_string:
            if dbg != 0:
                #print("ASCii Character:\t{0}".format(character_item))
                output_log_string = "ASCii Character:\t{0}".format(character_item)
                print_and_log(output_log_string, LOG__DEBUG)
            temp_array.append(character_item)
        # Create the final ASCii int array
        dbus_value = temp_array
        if dbg != 0:
            #print("[+] Completed conversion of ASCii string to D-Bus Write Value")
            output_log_string = "[+] Completed conversion of ASCii string to D-Bus Write Value"
            print_and_log(output_log_string, LOG__DEBUG)
        ## TODO: Add a signature the the created D-Bus Array
        return dbus_value

    '''
    # Create the eTree from the Introspection
    device_tree = ET.fromstring(device_introspection)
    # Enumerate through the eTree looking for the Services attached to the Device (Note: Assuming BLE Device)
    device_services_list = []
    for child in device_tree:
        if dbg != 0:
            print("Child Tag:\t\t{0}\n\tAttribs:\t\t{1}".format(child.tag, child.attrib))
        # Check for the expected 'service' information
        if child.tag == 'node' and 'service' in child.attrib['name']:
            if dbg != 0:
                print("\tAttrib:\t{0}\n\t\tValue:\t{1}".format(child.attrib, child.attrib['name']))
            device_services_list.append(child.attrib['name'])
    # Now return the findings from this dive into the Device Interface
    #print("[+]")
    '''
    ## Internal Functions for Debugging

    # Function for Blind/Test Printing of Variables from the D-Bus
    def debug_print__dbus__read_value(self, string__source_name, dbus__read_value):
        if dbg != 0:
            #print("[*] Attempting to print D-Bus Read [ {0} ] from Source named [ {1} ]".format(dbus__read_value, string__source_name))
            output_log_string = "[*] Attempting to print D-Bus Read [ {0} ] from Source named [ {1} ]".format(dbus__read_value, string__source_name)
            print_and_log(output_log_string, LOG__DEBUG)
        print("\t{0} Value".format(string__source_name), end=" ")
        #output_log_string = "\t{0} Value".format(string__source_name), end=" "
        #print_and_log(output_log_string)
        # Testing for the type of the variable
        if isinstance(dbus__read_value, dbus.Array):
            #print("(ASCii | Hex):\t{0}\t|\t{1}".format(self.dbus_read_value__to__ascii_string(dbus__read_value), self.dbus_read_value__to__hex_string(dbus__read_value)))
            output_log_string = "(ASCii | Hex):\t{0}\t|\t{1}".format(self.dbus_read_value__to__ascii_string(dbus__read_value), self.dbus_read_value__to__hex_string(dbus__read_value))
            print_and_log(output_log_string)
        else:
            #print("(Raw):\t{0}".format(dbus__read_value))
            output_log_string = "(Raw):\t{0}".format(dbus__read_value)
            print_and_log(output_log_string)
        ## OLD CODE
        '''
        if isinstance(dbus__read_value, dbus.Array):
            print("\tCharacteristic Value (ASCii | Hex):\t{0}\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(dbus__read_value), user_device.dbus_read_value__to__hex_string(dbus__read_value)))
        else:
            print("\tCharaceristic Value:\t{0}".format(dbus__read_value))
        '''

    ## Internal Functions for BLE Mapping

    # Function for Checking if a Provided Entry Exists within a Provided Map (i.e. Map with elements Services, Characteristics, Descriptors, and In-Review)
    def device_map__entry_check(self, map_to_check, reference_entry):
        if dbg != 0:
            out_log_string = "[*] device_map__entry_check::Examining Map [ {0} ] for Entry [ {1} ]".format(map_to_check, reference_entry)
            print_and_log(out_log_string)
            print_and_log(out_log_string, LOG__DEBUG)
        # Enumerate the map searching for the reference_entry
        for map_category in map_to_check:
            if reference_entry in map_to_check[map_category]:
                return True
        # Reference Entry was not found in the Provided Map
        return False

    # Function for Cleaning up a Provided Map (i.e. Map with elements Services, Characteristics, Descriptors, and In-Review)
    def device_map__clean_map(self, map_to_clean):
        if dbg != 0:
            out_log_string = "[*] device_map__clean_map::Cleaning Map [ {0} ]".format(map_to_clean)
            print_and_log(out_log_string)
            print_and_log(out_log_string, LOG__DEBUG)
        # Iterate through the In-Review category of the map
        for in_review_item in map_to_clean["In-Review"]:
            if dbg != 0:
                out_log_string = "[*] device_map__clean_map::In-Review Item [ {0} ]".format(in_review_item)
                print_and_log(out_log_string, LOG__DEBUG)
            # Check if the In-Review item exists in any of the other categories
            if ( in_review_item in map_to_clean["Services"] ) or ( in_review_item in map_to_clean["Characteristics"] ) or ( in_review_item in map_to_clean["Descriptors"] ):
                if dbg != 0:
                    out_log_string = "[*] device_map__clean_map::Removing Item [ {0} ] from In-Review".format(in_review_item)
                    print_and_log(out_log_string, LOG__DEBUG)
                # Remove duplicates from In-Review
                map_to_clean["In-Review"].remove(in_review_item)
        return map_to_clean

    # Function for Moving Provided Entry from In-Review to the Associated Service/Characteristic/Descriptor
    def device_map__set_from_in_review(self, map_to_update, reference_entry, associated_category):
        if dbg != 0:
            out_log_string = "[*] device_map__set_from_in_review::Moving Item [ {0} ] to Category [ {1} ] in Map [ {2} ]".format(reference_entry, associated_category, map_to_update)
            print_and_log(out_log_string)
            print_and_log(out_log_string, LOG__DEBUG)
        # Verify that the reference_entry exists in the In-Review category
        if reference_entry in map_to_update["In-Review"]:
            # Verify that the entry is not ALREADY in the associated_category
            if (reference_entry not in map_to_update[associated_category]) and (associated_category != "In-Review"):
                if dbg != 0:
                    out_log_string = "[*] device_map__set_from_in_review::Reference entry [ {0} ] to be added to the category [ {1} ]".format(reference_entry, associated_category)
                    print_and_log(out_log_string, LOG__DEBUG)
                # Add the reference_entry to the associated_category
                map_to_update[associated_category].append(reference_entry)
                # ??? Maybe perform a clean-up ???
            else:
                if dbg != 0:
                    out_log_string = "[*] device_map__set_from_in_review::Reference entry [ {0} ] already present in [ {1} ]".format(reference_entry, associated_category)
                    print_and_log(out_log_string, LOG__DEBUG)
        else:
            if dbg != 0:
                out_log_string = "[*] device_map__set_from_in_review::Reference entry [ {0} ] was NOT In-Review... No Action Taken".format(reference_entry)
                print_and_log(out_log_string, LOG__DEBUG)
        # Return the map_to_update
        return map_to_update

    # Function for Updating the Provided Entry into the In-Review for the Associated Map
    def device_map__update_in_review(self, map_to_update, reference_entry):
        # Update the Given Map
        if reference_entry not in map_to_update["In-Review"]:
            # Update the In-Review section of the Mine Map
            map_to_update["In-Review"].append(reference_entry)
            if dbg != 0:
                output_log_string = "[+] device_map__update_in_review::Reference Entry [ {0} ] being placed In-Review".format(reference_entry)
                print_and_log(output_log_string, LOG__DEBUG)
        else:
            if dbg != 0:
                output_log_string = "[*] device_map__update_in_review::Reference Entry [ {0} ] already under review".format(reference_entry)
                print_and_log(output_log_string, LOG__DEBUG)
        # Return the updated Map
        return map_to_update

## BlueZ Agent Classes

# BLE Agent Class - For performing pairing and bonding with a target device object; including pin/passkey
#   - Note: Built based on the BlueZ agent.py and simple-agent example files
class system_dbus__bluez_generic_agent(dbus.service.Object):
    '''
    Entry point for pairing, bonding, and authenticating with a device via the BlueZ Agent interfaces

    This class is intended to be used for the purpose of interacting with Bluetooth Low Energy (BLE) devices for pairing + bonding + authenticating
    '''

    # Initialization Function
    def __init__(self, bus, device_path=bluetooth_constants.AGENT_NAMESPACE):    #, bluetooth_adpater=bluetooth_constants.ADAPTER_NAME):
        # Note: Adding the '_' in front seems to work the same as the '.' in a linux directory
        self.bus = bus     #dbus.SystemBus()    # None
        #self.path = bluetooth_constants.AGENT_NAMESPACE     # Agent Path
        self.path = device_path     # Take as input from the function; due to already existing handler?? TODO: Either have this be static (only ONE agent at a time?) OR have this be an input (can then have multiple agents?)
        # Note: Error for above - KeyError: "Can't register the object-path handler for '/test/agent': there is already a handler"
        dbus.service.Object.__init__(self, bus, self.path)
        # Additional Internal Variables to Work with Internal Functions
        self.props = None
        self.dev = None
        self.dev_path = None
        self.device_object = None
        # Exit on Release Variable
        self.exit_on_release = True
        # Agent Properties
        self.agent = None
        # Class MainLoop
        self.mainloop = None
        # Class Agent Manageger variable
        self.manager = None
        # Thread for Running Agent
        self.thread = None
        # Timer Tracking for D-Bus
        self.timer_id__last = None                                  # Tracking the last Timer ID created (i.e. .timeout_add() for GLib MainLoop)
        self.timer_id__list = []                                    # Tracking all the Timer IDs created by this D-Bus BlueZ Adapter Class
        self.mainloop_run__default_time__ms = 60000                         # Default setting of timeout to 5000 milliseconds, 30000 milliseconds (30 seconds)
        
    ## Internal Functions

    # Internal Function for Converting a Byte Array to a String Value; Note: From BlueZ agent.py example
    def array_to_string(self, b_array):
	    str_value = ""
	    for b in b_array:
	    	str_value += "%02x" % b
	    return str_value

    # Internal Function for Getting Properties
    def get_properties(self):
        out_log_string = "[*] BLE Agent::Getting Properties of Agent"
        print_and_log(out_log_string, LOG__AGENT)
        caps = []
        # Array for Out-Of-Bounds (OOB)
        oob = []
        caps.append('out-numeric')
        #caps.append('in-numeric') -- Do not use well known in-oob
        caps.append('static-oob')
        #caps.append('public-oob') -- Do not use well known key pairs
        oob.append('other')
        return {
            bluetooth_constants.AGENT_INTERFACE: {
                # Creating a JSON with the Capabilities and Out-Of-Band info for ______'s properties
                'Capabilities': dbus.Array(caps, 's'),
                'OutOfBandInfo': dbus.Array(oob, 's')
            }
        }

    # Internal Fucntion for Obtaining the Path for the Provided D-Bus Object (from init function)
    def get_path(self):
        out_Log_string = "[*] BLE Agent::Retrieving Agent Path"
        print_and_log(out_log_string, LOG__AGENT)
        # May just return the Agent Path/NameSpace?
        return dbus.ObjectPath(self.path)

    # Internal Function for Setting the Exit on Release Class Variable
    def set_exit_on_release(self, exit_on_release):
        out_log_string = "[*] BLE Agent::Setting Exit on Release to [ {0} ]".format(exit_on_release)
        print_and_log(out_log_string, LOG__AGENT)
        # Set the Internal Class Variable for Exit on Release
        self.exit_on_release = exit_on_release

    ## Internal Functions with Method Definitions; TODO: Better understand this for future tool improvement

    # Internal Function for Canceling Actions by the Agent
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="", out_signature="")
    def Cancel(self):
        out_log_string = "[*] BLE Agent::Calling Cancel Function"
        print_and_log(out_log_string, LOG__AGENT)
        print("Cancel")

    # Internal Function for Displaying Numeric (e.g. Pin Code); Note use of different terminal color
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="su", out_signature="")
    def DisplayNumeric(self, type, value):
        out_log_string = "[*] BLE Agent::Displaying Numeric (e.g. Pin code)"
        print_and_log(out_log_string, LOG__AGENT)
        # Print the Numeric in Cyan
        print(set_cyan('DisplayNumeric ('), type, set_cyan(') number ='), set_green(value))

    # Internal Function for Prompting for Numeric Input (e.g. Pin Code)
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="s", out_signature="u")
    def PromptNumeric(self, type):
        out_log_string = "[*] BLE Agent::Prompt Numeric Function Called (e.g. Pin Code)"
        print_and_log(out_log_string, LOG__AGENT)
        # Sample in-oob -- DO-NOT-USE
        value = 12345
        # Print the Numeric Prompt
        print(set_cyan('PromptNumeric ('), type, set_cyan(') number ='), set_green(value))
        out_log_string = "[+] BLE Agent::Returning Pin Code [ {0} ]".format(value)
        print_and_log(out_log_string, LOG__AGENT)
        # Return the Numeric value
        return dbus.UInt32(value)

    # Internal Function for Creating and Returning the Private Key
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="", out_signature="ay")
    def PrivateKey(self):
        out_log_string = "[*] BLE Agent::Private Key Function Called"
        print_and_log(out_log_string, LOG__AGENT)
        # Sample Public/Private pair from Mesh Profile Spec DO-NOT-USE
        private_key_str = '6872b109ea0574adcf88bf6da64996a4624fe018191d9322a4958837341284bc'
        public_key_str = 'ce9027b5375fe5d3ed3ac89cef6a8370f699a2d3130db02b87e7a632f15b0002e5b72c775127dc0ce686002ecbe057e3d6a8000d4fbf2cdfffe0d38a1c55a043'
        # Print the Private Key
        print(set_cyan('PrivateKey ()'))
        print(set_cyan('Enter Public key on remote device: '), set_green(public_key_str));
        # Create the Private Key from the User-Provided Private Key String
        private_key = bytearray.fromhex(private_key_str)

        # Return the Private Key within a D-Bus Array with Signature
        return dbus.Array(private_key, signature='y')

    # Internal Function for Prompting for a Static Key
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="s", out_signature="ay")
    def PromptStatic(self, type):
        out_log_string = "[*] BLE Agent::Prompt Static Key Function Called"
        print_and_log(out_log_string, LOG__AGENT)
        # Create a Random Static Key
        static_key = numpy.random.randint(0, 255, 16)
        # Convert the Static Key into a String
        key_str = self.array_to_string(static_key)

        # Print the Prompt for the Static Key
        print(set_cyan('PromptStatic ('), type, set_cyan(')'))
        print(set_cyan('Enter 16 octet key on remote device: '), set_green(key_str));

        # Return the Static Key within a D-Bus Array with Signature
        return dbus.Array(static_key, signature='y')

    # Internal Function for Calling the Class' Release Method
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="", out_signature="")
    def Release(self):
        out_log_string = "[*] BLE Agent::Relase Functional Called"
        print_and_log(out_log_string, LOG__AGENT)
        # Print action being performed
        print("Release")
        # Check the value of the internal Exit on Release variable
        if self.exit_on_release:
            # Kill the MainLoop
            mainloop.quit()

    # Internal Function for Authorizing a Service
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device_object, uuid):
        out_log_string = "[*] BLE Agent::Authorize Service Function Called"
        print_and_log(out_log_string, LOG__AGENT)
        # Print action being performed
        print("AuthorizeService (%s, %s)" % (device_object, uuid))
        # Prompt the User to Authorize a Connection
        authorize = ask("Authorize connection (yes/no): ")
        # Check what the response was by the User
        if (authorize == "yes"):
            # Return success/acceptance for Authorization
            return
        # Return rejection of the Authorization
        raise Rejected("Connection rejected by user")

    # Internal Function for Requesting a Pin Code
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device_object):
        out_log_string = "[*] BLE Agent::Requesting Pin Code"
        print_and_log(out_log_string, LOG__AGENT)
        # Print action being performed
        print("RequestPinCode (%s)" % (device_object))
        # Set Trusted for the Device Object
        set_trusted(device_object)
        # Prompt the User for the Pin Code
        return ask("Enter PIN Code: ")

    # Internal Function for Requesting a Passkey
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device_object):
        out_log_string = "[*] BLE Agent::Requesting Pass Key"
        print_and_log(out_log_string, LOG__AGENT)
        # Print action being performed
        print("RequestPasskey (%s)" % (device_object))
        # Set Trusted for the Device Object
        set_trusted(device_object)
        # Prompt the User for the Passkey
        passkey = ask("Enter passkey: ")
        # Return a D-Bus UInt32 of the Passkey
        return dbus.UInt32(passkey)

    # Internal Function for Displaying the Passkey
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device_object, passkey, entered):
        out_log_string = "[*] BLE Agent::Displaying Passkey"
        print_and_log(out_log_string, LOG__AGENT)
        # Print action being performed
        print("DisplayPasskey (%s, %06u entered %u)" % (device_object, passkey, entered))

    # Internal Function for Displaying the Pin Code
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device_object, pincode):
        out_log_string = "[*] BLE Agent::Displaying Pin Code"
        print_and_log(out_log_string, LOG__AGENT)
        # Print action being performed
        print("DisplayPinCode (%s, %s)" % (device_object, pincode))

    # Internal Function for Requesting Confirmation
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device_object, passkey):
        out_log_string = "[*] BLE Agent::Requesting Confirmation"
        print_and_log(out_log_string, LOG__AGENT)
        # Print action being performed
        print("RequestConfirmation (%s, %06d)" % (device_object, passkey))
        # Prompt the User to Confirm the Passkey
        confirm = ask("Confirm passkey (yes/no): ")
        # Check the input from the User
        if (confirm == "yes"):
            # Set Trusted for the Device Object
            set_trusted(device_object)
            # Return success
            return
        # Return rejection of the Passkey by the User
        raise Rejected("Passkey doesn't match")

    # Internal Function for Requesting Authorization
    @dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        out_log_string = "[*] BLE Agent::Requesting Authorization"
        print_and_log(out_log_string, LOG__AGENT)
        # Print action being performed
        print("RequestAuthorization (%s)" % (device))
        # Prompt the User for Authorization
        auth = ask("Authorize? (yes/no): ")
        # Check the input from the User
        if (auth == "yes"):
            # Return success
            return
        # Raise error of rejection for the pairing
        raise Rejected("Pairing rejected")

    # Internal Function for Canceling an action (?); DUPLICATE
	#@dbus.service.method(bluetooth_constants.AGENT_INTERFACE, in_signature="", out_signature="")
	#def Cancel(self):
	#	print("Cancel")

    # Internal Function for Clearing a Single Timer from the Agent Bus
    def clear_single_timer(self, timer_id):
        out_log_string = "[*] BLE Agent::Removing Timer [ {0} ] from the Agent D-Bus".format(timer_id)
        print_and_log(out_log_string, LOG__AGENT)
        # Check that a timer_id was actually passed
        if timer_id not in self.timer_id__list:
            return False
        # Remove the timer_id from D-Bus
        GLib.source_remove(timer_id)
        # Remove the timer_id from tracking list
        self.timer_id__list.remove(timer_id)
        # Check if all timer_ids have been removed
        if timer_id == self.timer_id__last:
            self.timer_id__last = None
        return True

    # Internal Function for Configuring the MainLoop by Removing a timeout timer
    def mainloop__configure__remove_timeout(self, timer_id):
        out_log_string = "[*] BLE Agent::Configuring Mainloop\t-\tRemoving Timeout with Timer ID [ {0} ]".format(timer_id)
        print_and_log(out_log_string, LOG__AGENT)
        # Call the internal function to remove the timer_id
        self.clear_single_timer(timer_id)

    # Internal Function for Callback when D-Bus MainLoop timeout occurs
    def timer__signal_catch__end(self, mainloop):
        self.mainloop__configure__remove_timeout(self.timer_id__last)
        mainloop.quit()
        out_log_string = "[+] BLE Agent::Agent Signal Catch Completed"
        print_and_log(out_log_string, LOG__AGENT)

    # Internal Function for Adding a Timeout to the Agent D-Bus MainLoop
    def mainloop__configure__add_timeout(self, timeout_ms, callback_function, mainloop):
        out_log_string = "[*] BLE Agent::Configuring Mainloop\t-\tAdding Timeout of [ {0} ] ms".format(timeout_ms)
        print_and_log(out_log_string, LOG__AGENT)
        # Add the timeout and associated callback function to the provided mainloop
        self.timer_id__last = GLib.timeout_add(timeout_ms, callback_function, mainloop)
        # Add the timer_id to the tracking list
        self.timer_id__list.append(self.timer_id__last)

    # Internal Function for Stopping the Provided MainLoop
    def stop_agent(self, mainloop):
        # Stop the MainLoop
        mainloop.quit()
        out_log_string = "[+] BLE Agent::MainLoop Stopped"
        print_and_log(out_log_string, LOG__AGENT)

    # Internal Function for Performing Callback Function Debugging of a Received Signal
    def debugging__dbus_signals__agent(self, *args, **kwargs):
        out_log_string = "[*] BLE Agent::Generic D-Bus Signal Debugging"
        print_and_log(out_log_string, LOG__AGENT)
        # Iterate through Arguments Provided
        for arg_item in args:
            # Print the information per entry
            out_log_string = "\tArg:\t{0}".format(arg_item)
            print_and_log(out_log_string, LOG__AGENT)
        # Iterate thryough Keyword Args Provided
        for key, value in kwargs.items():
            # Print the information per key:value
            out_log_string = "\tKey:Value\t-\t[ {0}:{1} ]".format(key, value)
        out_log_string = "[+] BLE Agent::Completed Generic D-Bus Debugging"
        print_and_log(out_log_string, LOG__AGENT)

    # Internal Function for Configuring and Starting the Agent MainLoop
    def start_agent(self):
        out_log_string = "[*] BLE Agent::Starting Agent...."
        print_and_log(out_log_string, LOG__AGENT)
        out_log_string = "[*] BLE Agent::Adding Signal Receiver\t-\tGeneric Signal Capture"
        print_and_log(out_log_string, LOG__AGENT)
        # Add the signal receiver for any signal on the BlueZ D-Bus
        self.bus.add_signal_receiver(self.debugging__dbus_signals__agent, bus_name = bluetooth_constants.BLUEZ_SERVICE_NAME, dbus_interface = bluetooth_constants.DBUS_PROPERTIES, signal_name=None, path_keyword="path")
        # Note: The above 'dbus_interface' may need to be changed.....???
        out_log_string = "[*] BLE Agent::Adding Signal Receiver\t-\tStop Notifications"
        print_and_log(out_log_string, LOG__AGENT)
        # Add the signal receiver for stopping the Agent when a "StopNotifications" signal is sent
        self.bus.add_signal_receiver(self.stop_agent, "StopNotifications")
        # Note: The above 'signal_name' for the stop_agent command may need to be changed......???
        out_log_string = "[*] BLE Agent::Creating Agent MainLoop"
        print_and_log(out_log_string, LOG__AGENT)
        # Define the MainLoop that will run the agent within the thread
        self.mainloop = GLib.MainLoop()
        out_log_string = "[*] BLE Agent::Configuring Agent MainLoop\t-\tSetting Timeout and Shutdown Callback Function to Agent MainLoop"
        print_and_log(out_log_string, LOG__AGENT)
        # Configure the MainLoop and Add Required Timeouts
        self.mainloop__configure__add_timeout(self.mainloop_run__default_time__ms, self.timer__signal_catch__end, self.mainloop)
        out_log_string = "[*] BLE Agent::Starting Agent MainLoop..."
        print_and_log(out_log_string, LOG__AGENT)
        # Run the Agent MainLoop; Line where the Agent Thread will run until a [self.]mainloop.quit() call is made
        self.mainloop.run()
        out_log_string = "[!] BLE Agent::Testing Print on Other Side of MainLoop.Run() Call"
        print_and_log(out_log_string, LOG__AGENT)


# BLE Agent UI Class - For performing User Interaction (UI) with the BLE Agent Class
#   - Note: Built based on the BlueZ agent.py and simple-agent example files
class system_dbus__bluez_agent_user_interface(dbus.service.Object):
    '''
    Entry point for pairing, bonding, and authenticating with a device via the BlueZ Agent interfaces

    This class is intended to be used for the purpose of interacting with Bluetooth Low Energy (BLE) devices for pairing + bonding + authenticating
    '''

    # Initialization Function
    def __init__(self, bus, known_agent=None):    #, bluetooth_adpater=bluetooth_constants.ADAPTER_NAME):     # TODO: Does an Agent Manager require a path?!?!? (e.g. Agent Manager) No... From simple-agent doc
        # Note: Adding the '_' in front seems to work the same as the '.' in a linux directory
        self.bus = bus     #dbus.SystemBus()    # None
        #self.path = bluetooth_constants.AGENT_NAMESPACE     # Agent Path
        #self.path = device_path     # Take as input from the function; due to already existing handler?? TODO: Either have this be static (only ONE agent at a time?) OR have this be an input (can then have multiple agents?)
        # Note: Error for above - KeyError: "Can't register the object-path handler for '/test/agent': there is already a handler"
        #dbus.service.Object.__init__(self, bus, self.path)
        # Additional Internal Variables to Work with Internal Functions
        self.props = None
        self.dev = None
        self.dev_path = None
        #self.dev_path = device_object_path
        self.device_object = None       # TODO: Determine the difference between device_object, dev_path, dev, and device_obj
        #self.device_object = target_device_object
        # Exit on Release Variable
        #self.exit_on_release = True
        # Agent Properties
        self.agent = known_agent    # None
        # Class MainLoop
        self.mainloop = None
        # Class Agent Manageger variable
        self.manager = None

    # Internal Function for Replying when Paired
    def pair_reply(self):
        # Print device being paired
        print("[+] BLE Agent UI::Device paired")
        # Set Device Trusted
        self.set_trusted(self.dev_path)
        # Set Device Connected
        self.dev_connect(self.dev_path)
        # End the MainLoop
        self.mainloop.quit()

    # Internal Function for Error when Pairing
    def pair_error(self, error):
        # Configure the Error Name
    	err_name = error.get_dbus_name()
        # Check the Error and Device Object State
    	if err_name == "org.freedesktop.DBus.Error.NoReply" and device_obj:
            # Print time out error
            print("[-] BLE Agent UI::Timed out. Cancelling pairing")
            # Call CancelPairing() sub-function of the Device Object
            self.device_object.CancelPairing()
        # Different Error Occured
    	else:
            # Print device failed error
            print("[-] BLE Agent UI::Creating device failed: %s" % (error))
        # End the MainLoop
    	self.mainloop.quit()

    # Internal Function for Prompting for User Input
    def ask(self, prompt):
        # Attempt to Acquire Raw Input
        try:
            # Return the Raw Input
            return raw_input(prompt)
        except:
            # Return the attempt to use a different user-input prompting function; assumption one of these two calls will function
            return input(prompt)

    # Internal Function for Setting a Device as Trusted using Device Path
    def set_trusted(self, device_path):
        # Create the Properties Interface for the device_path Device's Properties Interface
    	self.props = dbus.Interface(bus.get_object("org.bluez", device_path),
    					"org.freedesktop.DBus.Properties")
        # Set the device_path's Device's Properties Interface's Trusted property to True
    	self.props.Set("org.bluez.Device1", "Trusted", True)
        # Nota Bene: Is this really all that creating a Trusted device requires?!?! (binary switch?)
        # TODO: Fixes to make to this function:
        #   [ ] Use the constant variables instead of strings
        #   [ ] Rename variables to more interesting / appropriate varaible names
        #   [ ] Do Class initialization variables need to come into play?

    # Internal Function for Connecting to a Set Device Path
    def dev_connect(self, device_path):
        # Create the Device Interface for the Provided Device Path
    	self.dev = dbus.Interface(bus.get_object("org.bluez", device_path),
    							"org.bluez.Device1")
        # Connect to the device
    	self.dev.Connect()

    ## Internal Functions for (Unit) Testing

    # Internal Function for Agent Testing; Note: May not work due to how properties are being called; can't create an Agent within an Agent??
    def testing__agent_to_device__pairing(self, pair_type=None):
        # Set Configuration of the D-Bus GLib MainLoop
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        # Set the bus property to the SystemBus()
        self.bus = dbus.SystemBus()

        # Set the capabilties of the agent(??)
        if pair_type is None:
            capability = "NoInputNoOutput"
        else:
            capability = "KeyboardDisplay"

        ## Option Parsing from Original simple-agent BlueZ example code
	    #parser = OptionParser()
	    #parser.add_option("-i", "--adapter", action="store",
	    #				type="string",
	    #				dest="adapter_pattern",
	    #				default=None)
	    #parser.add_option("-c", "--capability", action="store",
	    #				type="string", dest="capability")
	    #parser.add_option("-t", "--timeout", action="store",
	    #				type="int", dest="timeout",
	    #				default=60000)
	    #(options, args) = parser.parse_args()
	    #if options.capability:
	    #	capability  = options.capability

        # Set the path and Agent objects
        self.path = bluetooth_constants.AGENT_NAMESPACE #"/test/agent"   # Should be the same as the default?
        if self.agent is None:
            out_log_string = "[-] BLE Agent UI::No Agent Present.... Failing Pairing Test"
            print_and_log(out_log_string, LOG__AGENT)
            self.agent = system_dbus__bluez_generic_agent(self.bus, self.path)
        else:
            out_log_string = "[+] BLE Agent UI::Known Agent Confirmed"
            print_and_log(out_log_string, LOG__AGENT)
        #self.agent = system_dbus__bluez_generic_agent(self.bus, self.path)

        # Set the MainLoop object
        #self.mainloop = GObject.MainLoop()
        self.mainloop = GLib.MainLoop()
        ## Note: <stdin>:1: PyGIDeprecationWarning: GObject.MainLoop is deprecated; use GLib.MainLoop instead
        #   - TODO: Get this working with GLib.MainLoop

        # Configure the Device Object and Manager Class properties
        #self.device_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE)
        #self.device_object = self.bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE.rstrip("/"))      # Note the REQUIREMENT to not have the end slash
        # Nota Bene: The 'self.device_object' MUST BE A GENERIC BLUEZ INTERFACE (i.e. bluetooth_constants.BLUEZ_SERVICE_NAME)
        if self.device_object is None:
            out_log_string = "[-] BLE Agent UI::Device Object does not exist.... Defaulting BlueZ Device Object Pairing Test"
            print_and_log(out_log_string, LOG__AGENT)
            self.device_object = self.bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE.rstrip("/"))      # Note the REQUIREMENT to not have the end slash
        else:
            out_log_string = "[+] BLE Agent UI::Device Object exists.... Configuring Agent Manager"
            print_and_log(out_log_string, LOG__AGENT)
        self.agent.manager = dbus.Interface(self.device_object, bluetooth_constants.MANAGER_INTERFACE)
        self.agent.manager.RegisterAgent(self.path, capability)

        # Print Agent Registration Completed
        out_log_string = "[+] BLE Agent UI::Agent registered"
        print_and_log(out_log_string, LOG__AGENT)

        ## From simple-agent example
        # Fix-up old style invocation (BlueZ 4)
        #if len(args) > 0 and args[0].startswith("hci"):
	    #	options.adapter_pattern = args[0]
	    #	del args[:1]
        #
	    #if len(args) > 0:
	    #	device = bluezutils.find_device(args[0],
	    #					options.adapter_pattern)
	    #	dev_path = device.object_path
	    #	agent.set_exit_on_release(False)
	    #	device.Pair(reply_handler=pair_reply, error_handler=pair_error,
	    #							timeout=60000)
	    #	device_obj = device
	    #else:
	    #	manager.RequestDefaultAgent(path)

        # Perform Action of ________???
        self.agent.manager.RequestDefaultAgent(self.path)
        if self.device_object is None:
            out_log_string = "[*] BLE Agent UI::Agent does not exist.... Requesting default"
            print_and_log(out_log_string, LOG__AGENT)
            self.agent.manager.RequestDefaultAgent(self.path)
        else:
            # Check if device object exists?
            if self.device_object is None:
                out_log_string = "[-] BLE Agent UI::Device Object was not created"
                print_and_log(out_log_string, LOG__AGENT)
                #continue
            else:
                self.dev_path = self.device_object.object_path
                self.agent.set_exit_on_release(False)     # TODO: Determine the purpsoe for this
                out_log_string = "[+] BLE Agent UI::Configured Agent and Device aspects of Agent Class"
                print_and_log(out_log_string, LOG__AGENT)

        # Test Manager API Agent Request
        #self.manager.RequestDefaultAgent(self.path)

        try:
            out_log_string = "[*] BLE Agent UI::Starting MainLoop"
            print_and_log(out_log_string, LOG__AGENT)
            # Run the MainLoop
            self.mainloop.run()
        except KeyboardInterrupt:
            out_log_string = "[!] BLE Agent UI::Keyboard Interrupt Triggered.... Stopping Mainloop"
            print_and_log(out_log_string, LOG__AGENT)
            #self.mainloop.stop()
            self.mainloop.quit()

        # Unregister Agent
        #adapter.UnregisterAgent(path)      # Is this the adapter for the Manager?? Check the git.kernel documentation
        #print("Agent unregistered")

    # Internal Function for Testing the Thread Functionality of the Agent Class; NOTE: MUST be called by the Agent UI Class Object, since this is generating 
    def agent__test_thread(self):
        out_log_string = "[*] BLE Agent UI::Configuring the D-Bus GLib MainLoop in Preparation of Agent Thread Test"
        print_and_log(out_log_string, LOG__AGENT)
        # Set the configuration of the D-Bus GLib MainLoop
        #dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)   # Already hanlded by general script configuration
        # Initialize the GLib threads
        #dbus.mainloop.glib.threads_init()                       # Already handled by general script configuraiton
        out_log_string = "[*] BLE Agent UI::Creating the MainLoop Structure"
        print_and_log(out_log_string, LOG__AGENT)
        # Create a MainLoop object 
        agent_loop = GLib.MainLoop()
        output_log_string = "[*] BLE Agent UI::Creating the Agent Class Object"
        print_and_log(out_log_string, LOG__AGENT)
        # Create the Agent Class object
        agent = system_dbus__bluez_generic_agent(self.bus)
        output_log_string = "[*] BLE Agent UI::Setting the Agent MainLoop Property"
        print_and_log(out_log_string, LOG__AGENT)
        # Set the Agent MainLoop Property
        agent.mainloop = agent_loop
        # Check if the device_object property exists
        if self.device_object is None:
            out_log_string = "[-] BLE Agent UI::Device Object not created.... Creating the Device Object"
            print_and_log(out_log_string, LOG__AGENT)
            self.device_object = self.bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE.rstrip("/"))      # Note the REQUIREMENT to not have the end slash
        else:
            out_log_string = "[+] BLE Agent UI::Device Object exists.... Moving on to the Agent Manager"
            print_and_log(out_log_string, LOG__AGENT)
        output_log_string = "[*] BLE Agent UI::Creating the Manager Object and Assigning to Agent Property"
        print_and_log(out_log_string, LOG__AGENT)
        # Create the Manager Property of the Agent Class Object
        agent.manager = dbus.Interface(self.device_object, bluetooth_constants.MANAGER_INTERFACE)
        if agent.manager is None:
            out_log_string = ("[-] BLE Agent UI::Error in Creating Agent Manager Object")
            print_and_log(out_log_string, LOG__AGENT)
        else:
            out_log_string = ("[+] BLE Agent UI::Successfully Created Agent Manager Object")
            print_and_log(out_log_string, LOG__AGENT)
        # Set the capability that will be presented by the Agent
        capability = "KeyboardDisplay"
        output_log_string = "[*] BLE Agent UI::Determining Capabilitiy of the Agent Manager".format(capability)
        print_and_log(out_log_string, LOG__AGENT)
        output_log_string = "[*] BLE Agent UI::Configuring Capabilitiy of the Agent known to the Agent Manager Object [ {0} ]".format(capability)
        print_and_log(out_log_string, LOG__AGENT)
        # Register the Agent to the Manager
        agent.manager.RegisterAgent(agent.path, capability)
        output_log_string = "[*] BLE Agent UI::Configuring the Agent's Thread"
        print_and_log(out_log_string, LOG__AGENT)
        # Create and Configure the Thread for the Agent
        agent.thread = threading.Thread(target=agent.start_agent, daemon=False)     # Note: May need to change to True?
        output_log_string = "[*] BLE Agent UI::Starting the Agent Thread"
        print_and_log(out_log_string, LOG__AGENT)
        # Start the Agent Threat
        agent.thread.start()

## Class for Rejected Errors; from simple-agent example from BlueZ

## Rejected BlueZ Error Class
class Rejected(dbus.DBusException):
	_dbus_error_name = "org.bluez.Error.Rejected"

## Bluetooth Classic Classes

## BLE Classes      

# Note: Comes from older code.  Does GREAT RESTRUCTURE of how the original functions should NOT be called directly + AWESOME details
# Class for Device Manager for BLE Devices
#   - Note: Can use the class properties to interact with the interfaces (ex: device_manager._adapter_properties.GetAll(bluetooth_constants.ADAPTER_INTERFACE))
class bluetooth__le__deviceManager:
    '''
    Entry point for managing BLE GATT devices

    This class is intended to be subclassed to manage a specific set of GATT devices
    '''

    # Initialization Function
    def __init__(self, adapter_name):
        self.listener = None
        self.adapter_name = adapter_name
        # self.adapter_name = bluetooth_constants.ADAPTER_NAME

        self._bus = dbus.SystemBus()
        try:
            #adapter_object = self._bus.get_object('org.bluez', '/org/bluez/' + adapter_name)
            adapter_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE + adapter_name)
        except dbus.exceptions.DBusException as e:
            raise _error_from_dbus_error(e)
        #object_manager_object = self._bus.get_object("org.bluez", "/")
        object_manager_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, "/")
        #self._adapter = dbus.Interface(adapter_object, 'org.bluez.Adapter1')
        self._adapter = dbus.Interface(adapter_object, bluetooth_constants.ADAPTER_INTERFACE)
        #self._adapter_properties = dbus.Interface(self._adapter, 'org.freedesktop.DBus.Properties')
        self._adapter_properties = dbus.Interface(self._adapter, bluetooth_constants.DBUS_PROPERTIES)
        #self._object_manager = dbus.Interface(object_manager_object, "org.freedesktop.DBus.ObjectManager")
        self._object_manager = dbus.Interface(object_manager_object, bluetooth_constants.DBUS_OM_IFACE)
        self._device_path_regex = re.compile('^/org/bluez/' + adapter_name + '/dev((_[A-Z0-9]{2}){6})$')
        self._devices = {}
        self._discovered_devices = {}
        self._interface_added_signal = None
        self._properties_changed_signal = None
        self._main_loop = None
        self._timer_id = None

        self.update_devices()

    # Property export
    @property
    def is_adapter_powered(self):
        #return self._adapter_properties.Get('org.bluez.Adapter1', 'Powered') == 1
        return self._adapter_properties.Get(bluetooth_constants.ADAPTER_INTERFACE, 'Powered') == 1

    @is_adapter_powered.setter
    def is_adapter_powered(self, powered):
        #return self._adapter_properties.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(powered))
        return self._adapter_properties.Set(bluetooth_constants.ADAPTER_INTERFACE, 'Powered', dbus.Boolean(powered))

    # Timeout Function for Discovery Process - Prevent Stuck Running Endlessly
    #   - Note: Proven that this does EVENTUALLY get called...  Ex:     ble_class_manager.run(); time.sleep(15); ble_class_manager.stop()
    def discovery_timeout(self):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
        self._main_loop.quit()
        self._adapter.StopDiscovery()
        #bus = dbus.SystemBus()
        self._bus.remove_signal_receiver(self.interfaces_added,"InterfacesAdded")
        self._bus.remove_signal_receiver(self.interfaces_removed,"InterfacesRemoved")
        self._bus.remove_signal_receiver(self.properties_changed,"PropertiesChanged")
        self.list_devices_found()
        return True

    def run(self):
        """
        Starts the main loop that is necessary to receive Bluetooth events from the Bluetooth adapter.

        This call blocks until you call `stop()` to stop the main loop.
        """

        if self._main_loop:
            return

        self._interface_added_signal = self._bus.add_signal_receiver(
            self._interfaces_added,
            #dbus_interface='org.freedesktop.DBus.ObjectManager',
            dbus_interface=bluetooth_constants.DBUS_OM_IFACE,
            signal_name='InterfacesAdded')

        # TODO: Also listen to 'interfaces removed' events?

        self._properties_changed_signal = self._bus.add_signal_receiver(
            self._properties_changed,
            dbus_interface=dbus.PROPERTIES_IFACE,
            signal_name='PropertiesChanged',
            #arg0='org.bluez.Device1',
            arg0=bluetooth_constants.DEVICE_INTERFACE,
            path_keyword='path')

        def disconnect_signals():
            for device in self._devices.values():
                device.invalidate()
            self._properties_changed_signal.remove()
            self._interface_added_signal.remove()

        # Function that defines a timeout for the scan so that it does not get stuck running forever
        # Setup timeout
        scantime = 60   # In seconds
        timeout = int(scantime) * 1000
        # Setup the Timer ID
        self._timer_id = GLib.timeout_add(timeout, self.discovery_timeout)

        #self._main_loop = GObject.MainLoop()       # Deprecated
        self._main_loop = GLib.MainLoop()
        try:
            self._main_loop.run()
            disconnect_signals()
        except Exception:
            disconnect_signals()
            raise
        except KeyboardInterrupt:
            #print("BLE Manager::Exitting run...")
            output_log_string = "BLE Manager::Exitting run..."
            print_and_log(output_log_string)
            disconnect_signals()
            raise

    def stop(self):
        """
        Stops the main loop started with `start()`
        """
        if self._main_loop:
            self._main_loop.quit()
            self._main_loop = None

    def _manage_device(self, device):
        existing_device = self._devices.get(device.mac_address)
        if existing_device is not None:
            existing_device.invalidate()
        self._devices[device.mac_address] = device

    def update_devices(self):
        managed_objects = self._object_manager.GetManagedObjects().items()
        possible_mac_addresses = [self._mac_address(path) for path, _ in managed_objects]
        mac_addresses = [m for m in possible_mac_addresses if m is not None]
        new_mac_addresses = [m for m in mac_addresses if m not in self._devices]
        for mac_address in new_mac_addresses:
            self.make_device(mac_address)
        # TODO: Remove devices from `_devices` that are no longer managed, i.e. deleted

    def devices(self):
        """
        Returns all known Bluetooth devices.
        """
        self.update_devices()
        return self._devices.values()

    def start_discovery(self, service_uuids=[]):
        """Starts a discovery for BLE devices with given service UUIDs.

        :param service_uuids: Filters the search to only return devices with given UUIDs.
        """

        discovery_filter = {'Transport': 'le'}
        if service_uuids:  # D-Bus doesn't like empty lists, it needs to guess the type
            discovery_filter['UUIDs'] = service_uuids

        try:
            self._adapter.SetDiscoveryFilter(discovery_filter)
            self._adapter.StartDiscovery()
        except dbus.exceptions.DBusException as e:
            if e.get_dbus_name() == 'org.bluez.Error.NotReady':
                raise errors.NotReady(
                    "Bluetooth adapter not ready. "
                    "Set `is_adapter_powered` to `True` or run 'echo \"power on\" | sudo bluetoothctl'.")
            if e.get_dbus_name() == 'org.bluez.Error.InProgress':
                # Discovery was already started - ignore exception
                pass
            else:
                raise _error_from_dbus_error(e)

    def stop_discovery(self):
        """
        Stops the discovery started with `start_discovery`
        """
        try:
            self._adapter.StopDiscovery()
        except dbus.exceptions.DBusException as e:
            if (e.get_dbus_name() == 'org.bluez.Error.Failed') and (e.get_dbus_message() == 'No discovery started'):
                pass
            else:
                raise _error_from_dbus_error(e)

    def _interfaces_added(self, path, interfaces):
        self._device_discovered(path, interfaces)

    def _properties_changed(self, interface, changed, invalidated, path):
        # TODO: Handle `changed` and `invalidated` properties and update device
        self._device_discovered(path, [interface])

    def _device_discovered(self, path, interfaces):
        #if 'org.bluez.Device1' not in interfaces:
        if bluetooth_constants.DEVICE_INTERFACE not in interfaces:
            return
        mac_address = self._mac_address(path)
        if not mac_address:
            return
        device = self._devices.get(mac_address) or self.make_device(mac_address)
        if device is not None:
            self.device_discovered(device)

    def device_discovered(self, device):
        device.advertised()

    def _mac_address(self, device_path):
        match = self._device_path_regex.match(device_path)
        if not match:
            return None
        return match.group(1)[1:].replace('_', ':').lower()

    def make_device(self, mac_address):
        """
        Makes and returns a `Device` instance with specified MAC address.

        Override this method to return a specific subclass instance of `Device`.
        Return `None` if the specified device shall not be supported by this class.
        """
        return bluetooth__le__device(mac_address=mac_address, manager=self)

    def add_device(self, mac_address):
        """
        Adds a device with given MAC address without discovery.
        """
        # TODO: Implement

# Class for GATT/BLE Devices
class bluetooth__le__device:

    # Initailization Function
    def __init__(self, mac_address, manager, managed=True):
        """
        Represents a BLE GATT device.

        This class is intended to be sublcassed with a device-specific implementations
        that reflect the device's GATT profile.

        :param mac_address: MAC address of this device
        :manager: `DeviceManager` that shall manage this device
        :managed: If False, the created device will not be managed by the device manager
                  Particularly of interest for sub classes of `DeviceManager` who want
                  to decide on certain device properties if they then create a subclass
                  instance of that `Device` or not.
        """

        self.mac_address = mac_address
        self.manager = manager
        self.services = []

        self._bus = manager._bus
        self._object_manager = manager._object_manager

        # TODO: Device needs to be created if it's not yet known to bluetoothd, see "test-device" in bluez-5.43/test/
        self._device_path = '/org/bluez/%s/dev_%s' % (manager.adapter_name, mac_address.replace(':', '_').upper())
        #device_object = self._bus.get_object('org.bluez', self._device_path)
        device_object = self._bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, self._device_path)
        #self._object = dbus.Interface(device_object, 'org.bluez.Device1')
        self._object = dbus.Interface(device_object, bluetooth_constants.DEVICE_INTERFACE)
        #self._properties = dbus.Interface(self._object, 'org.freedesktop.DBus.Properties')
        self._properties = dbus.Interface(self._object, bluetooth_constants.DBUS_PROPERTIES)
        self._properties_signal = None
        self._connect_retry_attempt = None

        if managed:
            manager._manage_device(self)

    def advertised(self):
        """
        Called when an advertisement package has been received from the device. Requires device discovery to run.
        """
        pass

    def is_registered(self):
        # TODO: Implement, see __init__
        return False

    def register(self):
        # TODO: Implement, see __init__
        return

    def invalidate(self):
        self._disconnect_signals()

    def connect(self):
        """
        Connects to the device. Blocks until the connection was successful.
        """
        self._connect_retry_attempt = 0
        self._connect_signals()
        self._connect()

    def _connect(self):
        self._connect_retry_attempt += 1
        try:
            self._object.Connect()
            if not self.services and self.is_services_resolved():
                self.services_resolved()

        except dbus.exceptions.DBusException as e:
            if (e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownObject'):
                self.connect_failed(errors.Failed("Device does not exist, check adapter name and MAC address."))
            elif ((e.get_dbus_name() == 'org.bluez.Error.Failed') and
                  (e.get_dbus_message() == "Operation already in progress")):
                pass
            elif ((self._connect_retry_attempt < 5) and
                  (e.get_dbus_name() == 'org.bluez.Error.Failed') and
                  (e.get_dbus_message() == "Software caused connection abort")):
                self._connect()
            elif (e.get_dbus_name() == 'org.freedesktop.DBus.Error.NoReply'):
                # TODO: How to handle properly?
                # Reproducable when we repeatedly shut off Nuimo immediately after its flashing Bluetooth icon appears
                self.connect_failed(_error_from_dbus_error(e))
            else:
                self.connect_failed(_error_from_dbus_error(e))

    def _connect_signals(self):
        if self._properties_signal is None:
            self._properties_signal = self._properties.connect_to_signal('PropertiesChanged', self.properties_changed)
        self._connect_service_signals()

    def _connect_service_signals(self):
        for service in self.services:
            service._connect_signals()

    def connect_succeeded(self):
        """
        Will be called when `connect()` has finished connecting to the device.
        Will not be called if the device was already connected.
        """
        pass

    def connect_failed(self, error):
        """
        Called when the connection could not be established.
        """
        self._disconnect_signals()

    def disconnect(self):
        """
        Disconnects from the device, if connected.
        """
        self._object.Disconnect()

    def disconnect_succeeded(self):
        """
        Will be called when the device has disconnected.
        """
        self._disconnect_signals()
        self.services = []

    def _disconnect_signals(self):
        if self._properties_signal is not None:
            self._properties_signal.remove()
            self._properties_signal = None
        self._disconnect_service_signals()

    def _disconnect_service_signals(self):
        for service in self.services:
            service._disconnect_signals()

    def is_connected(self):
        """
        Returns `True` if the device is connected, otherwise `False`.
        """
        #return self._properties.Get('org.bluez.Device1', 'Connected') == 1
        return self._properties.Get(bluetooth_constants.DEVICE_INTERFACE, 'Connected') == 1

    def is_services_resolved(self):
        """
        Returns `True` is services are discovered, otherwise `False`.
        """
        #return self._properties.Get('org.bluez.Device1', 'ServicesResolved') == 1
        return self._properties.Get(bluetooth_constants.DEVICE_INTERFACE, 'ServicesResolved') == 1

    def alias(self):
        """
        Returns the device's alias (name).
        """
        try:
            #return self._properties.Get('org.bluez.Device1', 'Alias')
            return self._properties.Get(bluetooth_constants.DEVICE_INTERFACE, 'Alias')
        except dbus.exceptions.DBusException as e:
            if e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownObject':
                # BlueZ sometimes doesn't provide an alias, we then simply return `None`.
                # Might occur when device was deleted as the following issue points out:
                # https://github.com/blueman-project/blueman/issues/460
                return None
            else:
                raise _error_from_dbus_error(e)

    def properties_changed(self, sender, changed_properties, invalidated_properties):
        """
        Called when a device property has changed or got invalidated.
        """
        if 'Connected' in changed_properties:
            if changed_properties['Connected']:
                self.connect_succeeded()
            else:
                self.disconnect_succeeded()

        if ('ServicesResolved' in changed_properties and changed_properties['ServicesResolved'] == 1 and
                not self.services):
            self.services_resolved()

    def services_resolved(self):
        """
        Called when all device's services and characteristics got resolved.
        """
        self._disconnect_service_signals()

        services_regex = re.compile(self._device_path + '/service[0-9abcdef]{4}$')
        managed_services = [
            service for service in self._object_manager.GetManagedObjects().items()
            if services_regex.match(service[0])]
        self.services = [Service(
            device=self,
            path=service[0],
            #uuid=service[1]['org.bluez.GattService1']['UUID']) for service in managed_services]
            uuid=service[1][bluetooth_constants.GATT_SERVICE_INTERFACE]['UUID']) for service in managed_services]

        self._connect_service_signals()

    def characteristic_value_updated(self, characteristic, value):
        """
        Called when a characteristic value has changed.
        """
        # To be implemented by subclass
        pass

    def characteristic_read_value_failed(self, characteristic, error):
        """
        Called when a characteristic value read command failed.
        """
        # To be implemented by subclass
        pass

    def characteristic_write_value_succeeded(self, characteristic):
        """
        Called when a characteristic value write command succeeded.
        """
        # To be implemented by subclass
        pass

    def characteristic_write_value_failed(self, characteristic, error):
        """
        Called when a characteristic value write command failed.
        """
        # To be implemented by subclass
        pass

    def characteristic_enable_notifications_succeeded(self, characteristic):
        """
        Called when a characteristic notifications enable command succeeded.
        """
        # To be implemented by subclass
        pass

    def characteristic_enable_notifications_failed(self, characteristic, error):
        """
        Called when a characteristic notifications enable command failed.
        """
        # To be implemented by subclass
        pass

    def descriptor_read_value_failed(self, descriptor, error):
        """
        Called when a descriptor read command failed.
        """
        # To be implemented by subclass
        pass

### Functions

## Conversion Functions

# Function for converting the return of a Value from BLE (check with: characteristic) into an ASCii string; From a byte array to hex string THEN hex string to ascii string
##  - Note: This function converts a D-Bus Array into Hex, then translates the hex into ASCii
def convert__hex_to_ascii(string_byte_array):
    if dbg != 0:
        #print("[*] Converting string byte array to ascii string")
        output_log_string = "[*] Converting string byte array to ascii string\t-\tRaw:\t[ {0} ] ".format(string_byte_array)
        print_and_log(output_log_string)
    if not string_byte_array:   # or string_byte_array == UNKNOWN_VALUE:
        if dbg != 0:
            #print("[-] convert__hex_to_ascii::Provided string byte array is empty")
            output_log_string = "[-] convert__hex_to_ascii::Provided string byte array is empty"
            print_and_log(output_log_string)
        #return None
        return UNKNOWN_VALUE                 # "-=!=- UNKNOWN -=!=-"            # Test to see if this will allow more clear testing of ASCii translation attempts
    if dbg != 0:
        out_log_string = "[*] Provided string type:\t[ {0} ]".format(type(string_byte_array))
        print_and_log(out_log_string)
    byte_array__hex_string = bluetooth_utils.byteArrayToHexString(string_byte_array)
    try:
        byte_array__ascii_string = bytes.fromhex(byte_array__hex_string).decode("ASCII")
    except Exception as e:
        if dbg != 0:
            #print("[-] ASCii decode went wrong.... Attempting without .decode() call\n\t{0}".format(e))
            output_log_string = "[-] ASCii decode went wrong.... Attempting without .decode() call\n\t{0}".format(e)
            print_and_log(output_log_string, LOG__DEBUG)
        try:
            byte_array__ascii_string = bytes.fromhex(byte_array__hex_string)
        except Exception as e_internal:
            #print("[-] Nothing worked.....\n\t{0}".format(e_internal))
            output_log_string = "[-] Nothing worked.....\n\t{0}".format(e_internal)
            print_and_log(output_log_string)
    if dbg != 0:
        #print("[+] Converted [ {0} ] to [ {1} ]".format(string_byte_array, byte_array__ascii_string))
        output_log_string = "[+] Converted [ {0} ] to [ {1} ]".format(string_byte_array, byte_array__ascii_string)
        print_and_log(output_log_string, LOG__DEBUG)
    return byte_array__ascii_string

# Function for converting a String Byte Array (e.g. D-Bus Array of D-Bus Bytes) into a Hex string
def convert__dbus_to_hex(string_byte_array):
    if dbg != 0:
        #print("[*] Converting string byte array to hex string")
        output_log_string = "[*] Converting string byte array to hex string"
        print_and_log(output_log_string, LOG__DEBUG)
    if not string_byte_array:
        #print("[-] convert__dbus_to_hex::Provided string byte array is empty")
        output_log_string = "[-] convert__dbus_to_hex::Provided string byte array is empty"
        print_and_log(output_log_string)
        return None
    try:
        byte_array__hex_string = bluetooth_utils.byteArrayToHexString(string_byte_array)
    except Exception as e:
        #print("[-] Byte Array to Hex String\t-\t[ FAILED ]")
        output_log_string = "[-] Byte Array to Hex String\t-\t[ FAILED ]"
        print_and_log(output_log_string)
    if dbg != 0:
        #print("[+] Converted [ {0} ] to [ {1} ]".format(string_byte_array, byte_array__hex_string))
        output_log_string = "[+] Converted [ {0} ] to [ {1} ]".format(string_byte_array, byte_array__hex_string)
        print_and_log(output_log_string, LOG__DEBUG)
    return byte_array__hex_string

# Function for converting the returned Class of Device Information (i.e. 'Class') into a meaningful array
#   - TODO: Shift into an internal function for the BLE Class
#   - TODO: Incorporate the YAML file information; Can do math as int__mdc & 2 to get an AND operation of bits (e.g. bin(3 & 2) => bin(2) => 0b10; 0b11 & 0b10 => 0b10)     <------ Future Goal!!
#       -> YAML File:       https://bitbucket.org/bluetooth-SIG/public/src/main/assigned_numbers/core/class_of_device.yaml
def decode__class_of_device(class__dbus_uint):
    output_log_string = "[*] Decoding Class of Device"
    print_and_log(output_log_string, LOG__DEBUG)
    # TODO: Expand the code below to always extend the provided value to a 24 len array
    if class__dbus_uint.bit_length() != 23:
        #print("[-] Class Device bits are not of expected length (23-0); Number of bits is...", end="")
        output_log_string = "[-] Class Device bits are not of expected length (23-0); Number of bits is..."
        if class__dbus_uint.bit_length() > 23:
            #print("More", end="")
            output_log_string += "More"
        elif class__dbus_uint.bit_length() < 23:
            #print("Less", end="")
            output_log_string += "Less"
        else:
            #print("Unknown", end="")
            output_log_string += "Unknown"
            output_log_string += "\t-\t{0}".format(class__dbus_uint.bit_length())
            #print("\t-\t{0}".format(class__dbus_uint.bit_length()))
        print_and_log(output_log_string, LOG__DEBUG)
    else:
        #print("[+] Class Device bits are of expected length (23-0); Number of bits is...\t-\t{0}".format(class__dbus_uint.bit_length()))
        output_log_string = "[+] Class Device bits are of expected length (23-0); Number of bits is...\t-\t{0}".format(class__dbus_uint.bit_length())
        print_and_log(output_log_string, LOG__DEBUG)
    # Setting the variables to use for bit extraction
    start__major_service_classes = 0        # Starting at the 23rd bit (0 in the python array)
    end__major_service_classes = start__major_service_classes + (23 - 13)     # Bits 23 to 13 (23 - 13 = 10); 11 bits total (0 to 11)
    start__major_device_class = end__major_service_classes + 1              # Starting at the 12th bit (12 in the python array)
    end__major_device_class = start__major_device_class + (12 - 8)          # Bits 12 to 8 (12 - 8 = 4; +1 = 5); 5 bits total (11 to 17)
    start__minor_device_class = end__major_device_class + 1                 # Starting at the 7th bit (18 in the python array)
    end__minor_device_class = start__minor_device_class + (7 - 2)           # Bits 7 to 2 (7 - 2 = 5; +1 = 6); 6 bits total (17 to 22)
    start__fixed_value_bits = end__minor_device_class + 1                   # Startig at the 1st bit (21 in the python array)
    end__fixed_value_bits = start__fixed_value_bits + (1 - 0)               # Bits 1 to 0 (1 - 0 = 1; +1 = 2); 2 bits total (21 to 23)
    #print("[*] Extracting out the Class of Device information")
    output_log_string = "[*] Extracting out the Class of Device information"
    print_and_log(output_log_string, LOG__DEBUG)
    # Create string of only the binary information
    #class__binary_string = bin(class__dbus_uint)[2:]        # Note: The [2:] removes the leading '0b'
    class__binary_string = format(class__dbus_uint, 'b').zfill(24)      # Note: Extending the length of the dbus.UInt32 value to len 24 (0 to 23 bits; 24 total)
    # Extract the Major Service Classes
    #major_service_classes = class__binary_string[0:(23-13)]
    major_service_classes = class__binary_string[start__major_service_classes:end__major_service_classes + 1]
    # Extract the Major Device Class
    #major_device_class = class__binary_string[(23-13):(12-8)]
    major_device_class = class__binary_string[start__major_device_class:end__major_device_class + 1]
    # Extract the Minor Device Class
    #minor_device_class = class__binary_string[(23-13)+(12-8):(7-2)]
    minor_device_class = class__binary_string[start__minor_device_class:end__minor_device_class + 1]
    # Extract the Fixed Value (Note: Should always be 0b00)
    #fixed_value_bits = class__binary_string[(23-13)+(12-8)+(7-2):]
    fixed_value_bits = class__binary_string[start__fixed_value_bits:end__fixed_value_bits + 1]
    if dbg != 0:
        print("[?] Extraction Check:\n\tFull Binary String:\t{0}\n\tMajor Service Classes:\t{1}\n\tMajor Device Class:\t{2}\n\tMinor Device Class:\t{3}\n\tFixed Bits Data:\t{4}".format(class__binary_string, major_service_classes, major_device_class, minor_device_class, fixed_value_bits))
        output_log_string = "[?] Extraction Check:\n\tFull Binary String:\t{0}\n\tMajor Service Classes:\t{1}\n\tMajor Device Class:\t{2}\n\tMinor Device Class:\t{3}\n\tFixed Bits Data:\t{4}".format(class__binary_string, major_service_classes, major_device_class, minor_device_class, fixed_value_bits)
        print_and_log(output_log_string, LOG__DEBUG)
    ## Checking for Matching Class of Device Information
    # Setup Variables
    list__major_service_classes = []
    list__major_device_class = []
    list__minor_device_class = []
    fixed_bits_check = None
    # Convert binary strings to integer from base 2
    int__major_service_classes = int(major_service_classes, 2)
    int__major_device_class = int(major_device_class, 2)
    int__minor_device_class = int(minor_device_class, 2)
    # Major Service Classes
    if int__major_service_classes & 0b00000000001:       # Limited Discoverable Mode                                     [ bit 13 ]
        list__major_service_classes.append('Limited Discoverable Mode')
    if int__major_service_classes & 0b00000000010:       # LE Audio                                                      [ bit 14 ]
        list__major_service_classes.append('LE Audio')
    if int__major_service_classes & 0b00000000100:       # Reserved for Future Use                                       [ bit 15 ]
        list__major_service_classes.append('Reserved for Future Use')
    if int__major_service_classes & 0b00000001000:       # Positioning (Location identification)                         [ bit 16 ]
        list__major_service_classes.append('Positioning (Location identification)')
    if int__major_service_classes & 0b00000010000:       # Networking (LAN, Ad hoc, ...)                                 [ bit 17 ]
        list__major_service_classes.append('Networking (LAN, Ad hoc, ...)')
    if int__major_service_classes & 0b00000100000:       # Rendering (Printing, Speakers, ...)                           [ bit 18 ]
        list__major_service_classes.append('Rendering (Printing, Speakers, ...)')
    if int__major_service_classes & 0b00001000000:       # Capturing (Scanner, Microphone, ...)                          [ bit 19 ]
        list__major_service_classes.append('Capturing (Scanner, Microphone, ...)')
    if int__major_service_classes & 0b00010000000:       # Object Transfer (v-Inbox, v-Folder, ...)                      [ bit 20 ]
        list__major_service_classes.append('Object Transfer (v-Inbox, v-Folder, ...)')
    if int__major_service_classes & 0b00100000000:       # Audio (Speaker, Microphone, Headset service, ...)             [ bit 21 ]
        list__major_service_classes.append('Audio (Speaker, Microphone, Headset service, ...)')
    if int__major_service_classes & 0b01000000000:       # Telephony (Cordless telephony, Modem, Headset service, ...)   [ bit 22 ]
        list__major_service_classes.append('Telephony (Cordless telephony, Modem, Headset service, ...)')
    if int__major_service_classes & 0b10000000000:       # Information (WEB-server, WAP-server, ...)                     [ bit 23 ]
        list__major_service_classes.append('Information (WEB-server, WAP-server, ...)')
    # Major Device Classes; NOTE: Shoulld be only one Major Device Class ???
    if int__major_device_class == 0b11111:       # Uncategorized (device code not specified)                         [ all bits ]
        list__major_device_class.append('Uncategorized (device code not specified)')
    if int__major_device_class == 0b00001:       # Computer (desktop, notebook, PDA, organizer, ...)                 [ bit 8 ]
        list__major_device_class.append('Computer (desktop, notebook, PDA, organizer, ...)')
    if int__major_device_class == 0b00010:       # 'Phone (cellular, cordless, pay phone, modem, ...)                [ bit 9 ]
        list__major_device_class.append('Phone (cellular, cordless, pay phone, modem, ...)')
    if int__major_device_class == 0b00011:       # LAN/Network Access Point                                          [ bits 9 + 8 ]
        list__major_device_class.append('LAN/Network Access Point')
    if int__major_device_class == 0b00100:       # Audio/Video (headset, speaker, stereo, video display, VCR, ...)   [ bit 10 ]
        list__major_device_class.append('Audio/Video (headset, speaker, stereo, video display, VCR, ...)')
    if int__major_device_class == 0b00101:       # Peripheral (mouse, joystick, keyboard, ...)                       [ bits 10 + 8 ]
        list__major_device_class.append('Peripheral (mouse, joystick, keyboard, ...)')
    if int__major_device_class == 0b00110:       # Imaging (printer, scanner, camera, display, ...)                  [ bits 10 + 9 ]
        list__major_device_class.append('Imaging (printer, scanner, camera, display, ...)')
    if int__major_device_class == 0b00111:       # Wearable                                                          [ bits 10 + 9 + 8 ]
        list__major_device_class.append('Wearable')
    if int__major_device_class == 0b01000:       # Toy                                                               [ bit 11 ]
        list__major_device_class.append('Toy')
    if int__major_device_class == 0b01001:       # Health                                                            [ bit 11 + 8 ]
        list__major_device_class.append('Health')
    if not int__major_device_class:             # Miscellaneous                                                     [ none of the bits ]
        list__major_device_class.append('Miscellaneous')
        # Scenario where all the bits are 0 (zero)
    ## Minor Device Classes
    #   - Nota Bene: Can mean different things based on the Major Device Classes
    # Check for the contents of the Major Device Class list; TODO: Add signification/print out if an UNEXPECTED bit string is seen
    if 'Computer (desktop, notebook, PDA, organizer, ...)' in list__major_device_class:
        # Minor Device Classes for Computer Major Class
        if not int__minor_device_class:         # Uncategorized (code for device not assigned)                      [ none of the bits ]
            list__minor_device_class.append('Uncategorized (code for device not assigned)')
        if int__minor_device_class == 0b000001:  # Desktop Workstation                                               [ bit 2 ]
            list__minor_device_class.append('Desktop Workstation')
        if int__minor_device_class == 0b000010:  # Server-class Computer                                             [ bit 3 ]
            list__minor_device_class.append('Server-class Computer')
        if int__minor_device_class == 0b000011:  # Laptop                                                            [ bits 3 + 2 ]
            list__minor_device_class.append('Laptop')
        if int__minor_device_class == 0b000100:  # Handheld PC/PDA (clamshell)                                       [ bit 4 ]
            list__minor_device_class.append('Handheld PC/PDA (clamshell)')
        if int__minor_device_class == 0b000101:  # Palm-size PC/PDA                                                  [ bits 4 + 2 ]
            list__minor_device_class.append('Palm-size PC/PDA')
        if int__minor_device_class == 0b000110:  # Wearable Computer (watch size)                                    [ bits 4 + 3 ]
            list__minor_device_class.append('Wearable Computer (watch size)')
        if int__minor_device_class == 0b000111:  # Tablet                                                            [ bits 4 + 3 + 2 ]
            list__minor_device_class.append('Tablet')
    if 'Phone (cellular, cordless, pay phone, modem, ...)' in list__major_device_class:
        # Minor Device Classes for Phone Major Class
        if not int__minor_device_class:         # Uncategorized (code for device not assigned)                      [ none of the bits ]
            list__minor_device_class.append('Uncategorized (code for device not assigned)')
        if int__minor_device_class == 0b000001:  # Cellular                                                          [ bit 2 ]
            list__minor_device_class.append('Cellular')
        if int__minor_device_class == 0b000010:  # Cordless                                                          [ bit 3 ]
            list__minor_device_class.append('Cordless')
        if int__minor_device_class == 0b000011:  # Smartphone                                                        [ bits 3 + 2 ]
            list__minor_device_class.append('Smartphone')
        if int__minor_device_class == 0b000100:  # Wired Modem or Voice Gateway                                      [ bit 4 ]
            list__minor_device_class.append('Wired Modem or Voice Gateway')
        if int__minor_device_class == 0b000101:  # Common ISDN Access                                                [ bits 4 + 2 ]
            list__minor_device_class.append('Common ISDN Access')
    if 'LAN/Network Access Point' in list__major_device_class:
        # Minor Device Classes for LAN/Network Access Point Major Class
        if not int__minor_device_class:         # Fully Available + Uncategorized                                   [ none of the bits ]
            list__minor_device_class.append('Fully available')
        # Createing minor and sub-minor bit strings
        minor_string = minor_device_class[0:3]          # Bits 7 + 6 + 5
        sub_minor_string = minor_device_class[3:6]      # Bits 4 + 3 + 2
        int__minor_string = int(minor_string, 2)
        int__sub_minor_string = int(sub_minor_string, 2)
        # Rest of LAN/Network Access Point Minor Device Classes
        if int__minor_string == 0b001:           # 1% to 17% utilized                                                [ bit 5 ]
            list__minor_device_class.append('1% to 17% utilized')
        if int__minor_string == 0b010:           # 17% to 33% utilized                                               [ bit 6 ]
            list__minor_device_class.append('17% to 33% utilized')
        if int__minor_string == 0b011:           # 33% to 50% utilized                                               [ bits 6 + 5 ]
            list__minor_device_class.append('33% to 50% utilized')
        if int__minor_string == 0b100:           # 50% to 67% utilized                                               [ bit 7 ]
            list__minor_device_class.append('50% to 67% utilized')
        if int__minor_string == 0b101:           # 67% to 83% utilized                                               [ bits 7 + 5 ]
            list__minor_device_class.append('67% to 83% utilized')
        if int__minor_string == 0b110:           # 83% to 99% utilized                                               [ bits 7 + 6 ]
            list__minor_device_class.append('83% to 99% utilized')
        if int__minor_string == 0b111:           # No service available                                              [ bits 7 + 6 + 5 ]
            list__minor_device_class.append('No service available')
        # Sub Minor Device Classes
        if not int__sub_minor_string:           # Uncategorized (use this value if no others apply)                 [ none of the bits ]
            list__minor_device_class.append('Uncategorized (use this value if no others apply)')
    if 'Audio/Video (headset, speaker, stereo, video display, VCR, ...)' in list__major_device_class:
        # Minor Device Classes for Audio/Video Major Class
        if not int__minor_device_class:         # Uncategorized (code not assigned)                                 [ none of the bits ]
            list__minor_device_class.append('Uncategorized (code not assigned)')
        if int__minor_device_class == 0b000001:  # Wearable Headset Device                                           [ bit 2 ]
            list__minor_device_class.append('Wearable Headset Device')
        if int__minor_device_class == 0b000010:  # Hands-free Device                                                 [ bit 3 ]
            list__minor_device_class.append('Hands-free Device')
        if int__minor_device_class == 0b000011:  # Reserved for Future Use                                           [ bits 3 + 2 ]
            list__minor_device_class.append('Reserved for Future Use')
        if int__minor_device_class == 0b000100:  # Microphone                                                        [ bit 4 ]
            list__minor_device_class.append('Microphone')
        if int__minor_device_class == 0b000101:  # Loudspeaker                                                       [ bits 4 + 2 ]
            list__minor_device_class.append('Loudspeaker')
        if int__minor_device_class == 0b000110:  # Headphones                                                        [ bits 4 + 3 ]
            list__minor_device_class.append('Headphones')
        if int__minor_device_class == 0b000111:  # Portable Audio                                                    [ bits 4 + 3 + 2 ]
            list__minor_device_class.append('Portable Audio')
        if int__minor_device_class == 0b001000:  # Car Audio                                                         [ bit 5 ]
            list__minor_device_class.append('Car Audio')
        if int__minor_device_class == 0b001001:  # Set-top box                                                       [ bits 5 + 2 ]
            list__minor_device_class.append('Set-top box')
        if int__minor_device_class == 0b001010:  # HiFi Audio Device                                                 [ bits 5 + 3 ]
            list__minor_device_class.append('HiFi Audio Device')
        if int__minor_device_class == 0b001011:  # VCR                                                               [ bits 5 + 3 + 2 ]
            list__minor_device_class.append('VCR')
        if int__minor_device_class == 0b001100:  # Video Camera                                                      [ bits 5 + 4 ]
            list__minor_device_class.append('Video Camera')
        if int__minor_device_class == 0b001101:  # Camcorder                                                         [ bits 5 + 4 + 2 ]
            list__minor_device_class.append('Camcorder')
        if int__minor_device_class == 0b001110:  # Video Monitor                                                     [ bits 5 + 4 + 3 ]
            list__minor_device_class.append('Video Monitor')
        if int__minor_device_class == 0b001111:  # Video Display and Loudspeaker                                     [ bits 5 + 4 + 3 + 2 ]
            list__minor_device_class.append('Video Display and Loudspeaker')
        if int__minor_device_class == 0b010000:  # Video Conferencing                                                [ bit 6 ]
            list__minor_device_class.append('Video Conferencing')
        if int__minor_device_class == 0b010001:  # Reserved for Future Use                                           [ bits 6 + 2 ]
            list__minor_device_class.append('Reserved for Future Use')
        if int__minor_device_class == 0b010010:  # Gaming/Toy                                                        [ bits 6 + 3 ]
            list__minor_device_class.append('Gaming/Toy')
    if 'Peripheral (mouse, joystick, keyboard, ...)' in list__major_device_class:
        # Minor Device Classes for Peripheral Major Class
        if not int__minor_device_class:         # Uncategorized (code not assigned)                                 [ none of the bits ]
            list__minor_device_class.append('Uncategorized (code not assigned)')
        # Create minor and sub-minor strings for this class
        minor_string = minor_device_class[0:2]          # Bits 7 + 6
        sub_minor_string = minor_device_class[2:6]      # Bits 5 + 4 + 3 + 2
        int__minor_string = int(minor_string, 2)
        int__sub_minor_string = int(sub_minor_string, 2)
        # Rest of Peripheral Minor Device Classes
        if int__minor_string == 0b01:            # Keyboard                                                          [ bit 6 ]
            list__minor_device_class.append('Keyboard')
        if int__minor_string == 0b10:            # Pointing Device                                                   [ bit 7 ]
            list__minor_device_class.append('Pointing Device')
        # Sub Minor Device Classes
        if int__sub_minor_string == 0b0001:      # Joystick                                                          [ bit 2 ]
            list__minor_device_class.append('Joystick')
        if int__sub_minor_string == 0b0010:      # Gamepad                                                           [ bit 3 ]
            list__minor_device_class.append('Gamepad')
        if int__sub_minor_string == 0b0011:      # Remote Control                                                    [ bits 3 + 2 ]
            list__minor_device_class.append('Remote Control')
        if int__sub_minor_string == 0b0100:      # Sensing Device                                                    [ bit 4 ]
            list__minor_device_class.append('Sensing Device')
        if int__sub_minor_string == 0b0101:      # Digitizer Tablet                                                  [ bits 4 + 2 ]
            list__minor_device_class.append('Digitizer Tablet')
        if int__sub_minor_string == 0b0110:      # Card Reader (e.g., SIM Card Reader)                               [ bits 4 + 3 ]
            list__minor_device_class.append('Card Reader (e.g., SIM Card Reader)')
        if int__sub_minor_string == 0b0111:      # Digital Pen                                                       [ bits 4 + 3 + 2 ]
            list__minor_device_class.append('Digital Pen')
        if int__sub_minor_string == 0b1000:      # Handheld Scanner (e.g., barcodes, RFID)                           [ bit 5 ]
            list__minor_device_class.append('Handheld Scanner (e.g., barcodes, RFID)')
        if int__sub_minor_string == 0b1001:      # Handheld Gestural Input Device (e.g., “wand” form factor)         [ bits 5 + 2 ]
            list__minor_device_class.append('Handheld Gestural Input Device (e.g., “wand” form factor)')
    if 'Imaging (printer, scanner, camera, display, ...)' in list__major_device_class:
        # Minor Device Classes for Imaging Major Class
        if not int__minor_device_class:         # Uncategorized (default)                                           [ none of the bits ]
            list__minor_device_class.append('Uncategorized (default)')
        # Create minor and sub-minor strings for this class
        minor_string = minor_device_class[0:4]          # Bits 7 + 6 + 5 + 4
        sub_minor_string = minor_device_class[4:6]      # Bits 3 + 2
        int__minor_string = int(minor_string, 2)
        int__sub_minor_string = int(sub_minor_string, 2)
        # Rest of Imaging Major Classes
        if int__minor_string ^ 0b0001:                  # Display                                                   [ bit 4; rest DC ]
            list__minor_device_class.append('Display')
        if int__minor_string ^ 0b0010:                  # Camera                                                    [ bit 5; rest DC ]
            list__minor_device_class.append('Camera')
        if int__minor_string ^ 0b0100:                  # Scanner                                                   [ bit 6; rest DC ]
            list__minor_device_class.append('Scanner')
        if int__minor_string ^ 0b1000:                  # Printer                                                   [ bit 7; rest DC ]
            list__minor_device_class.append('Printer')
        # Sub Minor Device Classes
        # Not needed here, but prepare for future use
    if 'Wearable' in list__major_device_class:
        # Minor Device Classes for Wearable Major Class
        if int__minor_device_class == 0b000001:          # Wristwatch                                                [ bit 2 ]
            list__minor_device_class.append('Wristwatch')
        if int__minor_device_class == 0b000010:          # Pager                                                     [ bit 3 ]
            list__minor_device_class.append('Pager')
        if int__minor_device_class == 0b000011:          # Jacket                                                    [ bits 3 + 2 ]
            list__minor_device_class.append('Jacket')
        if int__minor_device_class == 0b000100:          # Helmet                                                    [ bit 4 ]
            list__minor_device_class.append('Helmet')
        if int__minor_device_class == 0b000101:          # Glasses                                                   [ bits 4 + 2 ]
            list__minor_device_class.append('Glasses')
        if int__minor_device_class == 0b000110:          # Pin (e.g., lapel pin, broach, badge)                      [ bits 4 + 3 ]
            list__minor_device_class.append('Pin (e.g., lapel pin, broach, badge)')
    if 'Toy' in list__major_device_class:
        # Minor Device Classes for Toy Major Class
        if int__minor_device_class == 0b000001:          # Robot                                                     [ bit 2 ]
            list__minor_device_class.append('Robot')
        if int__minor_device_class == 0b000010:          # Vehicle                                                   [ bit 3 ]
            list__minor_device_class.append('Vehicle')
        if int__minor_device_class == 0b000011:          # Doll/Action Figure                                        [ bits 3 + 2 ]
            list__minor_device_class.append('Doll/Action Figure')
        if int__minor_device_class == 0b000100:          # Controller                                                [ bit 4 ]
            list__minor_device_class.append('Controller')
        if int__minor_device_class == 0b000101:          # Game                                                      [ bits 4 + 2 ]
            list__minor_device_class.append('Game')
    if 'Health' in list__major_device_class:
        # Minor Device Classes for Health Major Class
        if not int__minor_device_class:                 # Undefined                                                 [ none of the bits ]
            list__minor_device_class.append('Undefined')
        if int__minor_device_class == 0b000001:          # Blood Pressure Monitor                                    [ bit 2 ]
            list__minor_device_class.append('Blood Pressure Monitor')
        if int__minor_device_class == 0b000010:          # Thermometer                                               [ bit 3 ]
            list__minor_device_class.append('Thermometer')
        if int__minor_device_class == 0b000011:          # Weighing Scale                                            [ bits 3 + 2 ]
            list__minor_device_class.append('Weighing Scale')
        if int__minor_device_class == 0b000100:          # Glucose Meter                                             [ bit 4 ]
            list__minor_device_class.append('Glucose Meter')
        if int__minor_device_class == 0b000101:          # Pulse Oximeter                                            [ bits 4 + 2 ]
            list__minor_device_class.append('Pulse Oximeter')
        if int__minor_device_class == 0b000110:          # Heart/Pulse Rate Monitor                                  [ bits 4 + 3 ]
            list__minor_device_class.append('Heart/Pulse Rate Monitor')
        if int__minor_device_class == 0b000111:          # Health Data Display                                       [ bits 4 + 3 + 2 ]
            list__minor_device_class.append('Health Data Display')
        if int__minor_device_class == 0b001000:          # Step Counter                                              [ bit 5 ]
            list__minor_device_class.append('Step Counter')
        if int__minor_device_class == 0b001001:          # Body Composition Analyzer                                 [ bits 5 + 2 ]
            list__minor_device_class.append('Body Composition Analyzer')
        if int__minor_device_class == 0b001010:          # Peak Flow Monitor                                         [ bits 5 + 3 ]
            list__minor_device_class.append('Peak Flow Monitor')
        if int__minor_device_class == 0b001011:          # Medication Monitor                                        [ bits 5 + 3 + 2 ]
            list__minor_device_class.append('Medication Monitor')
        if int__minor_device_class == 0b001100:          # Knee Prosthesis                                           [ bits 5 + 4 ]
            list__minor_device_class.append('Knee Prosthesis')
        if int__minor_device_class == 0b001101:          # Ankle Prosthesis                                          [ bits 5 + 4 + 2 ]
            list__minor_device_class.append('Ankle Prosthesis')
        if int__minor_device_class == 0b001110:          # Generic Health Manager                                    [ bits 5 + 4 + 3 ]
            list__minor_device_class.append('Generic Health Manager')
        if int__minor_device_class == 0b001111:          # Personal Mobility Device                                  [ bits 5 + 4 + 3 + 2 ]
            list__minor_device_class.append('Personal Mobility Device')

    # Verifying the Fixed Bit Values (Nota Bene: MUST be 0x00)
    if int(fixed_value_bits, 2) & 0b11:
        fixed_bits_check = False    # Unexpected fixed bits!!
    else:
        fixed_bits_check = True     # Expected 0x00 bits
    ## Printing the Collected information
    if dbg != 0:
        output_log_string = "[?] Extracted Information:\n\tMajor Service Classes:\t{0}\n\tMajor Device Classes:\t{1}\n\tMinor Device Class:\t{2}\n\tFixed Bits Check:\t{3}".format(list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check)
        print_and_log(output_log_string, LOG__DEBUG)

    ## Return the Device of Class information
    return list__major_service_classes, list__major_device_class, list__minor_device_class, fixed_bits_check

# Function for Displaying the Class and Service Information of a Device
def extract__class_of_device__service_and_class_info(major_service_class_info, major_device_class_info, minor_device_class_info, device_class__fixed_bits_check):
    ## Variables
    device_services, major_device, minor_device = "", "", ""
    ## Internal Functions
    # Internal Function to Extract Major and Minor Class Names
    def extract__class_name__high_level(class_name_info):
        # Grab the info before the sub-information and strip out white space; Note: Calling split on string without token will return the original string
        return class_name_info.split('(')[0].rstrip()
        
    ## Extract Device's Major Class
    # Check if only one extracted of each
    if len(major_device_class_info) == 1 and len(minor_device_class_info) == 1:
        major_device = extract__class_name__high_level(major_device_class_info[0])
        minor_device = extract__class_name__high_level(minor_device_class_info[0])
    elif len(major_device_class_info) > 1 and len(minor_device_class_info) == 1:
        # Extract and Append Each Major Device Class Name
        for major_class_name in major_device_class_info:
            major_device += "{0},".format(extract__class_name__high_level(major_class_name))
        # Strip Extra Comma from End of Major Device Class Name
        major_device = major_device.rstrip(',')
        # Extract Minor Device Class
        minor_device = extract__class_name__high_level(minor_device_class_info[0])
    elif len(major_device_class_info) > 1 and len(minor_device_class_info) > 1:
        # Extract and Append Each Major Device Class Name
        for major_class_name in major_device_class_info:
            major_device += "{0},".format(extract__class_name__high_level(major_class_name))
        # Strip Extra Comma from End of Major Device Class Name
        major_device.rstrip(',')
        # Extract and Append Each Minor Device Class Name
        for minor_class_name in minor_device_class_info:
            minor_device += "{0},".format(extract__class_name__high_level(major_class_name))
        # Strip Extra Comma from End of Minor Device Class Name
        minor_device = minor_device.rstrip(',')
    else:
        # Major and Minor Class Info were Length Zero (Does not exist)
        major_class = "-=UNKNOWN=-"
        minor_class = "-=UNKNOWN=-"

    ## Extract Device's Major Services
    # Check Number of Major Services
    if len(major_service_class_info) > 0:
        # Extract and Append Each Major Device Service Name
        for major_service_name in major_service_class_info:
            device_services += "{0},".format(extract__class_name__high_level(major_service_name))
        # Strip Extra Comma from End of Major Device Service Name
        device_services = device_services.rstrip(',')
    else:
        # Major Service Info was Length Zero (Does not exist)
        device_servces = "-=UNKNOWN=-"
        
    ## Print Informaiton Extracted
    if dbg != 0:
        print("Device Class Summary:\t\t[ {0} - {1} ]\n\tServices:\t\t[ {2} ]".format(major_device, minor_device, device_services))

    ## Return the Extracted Information
    return device_services, major_device, minor_device 

# Function for Finding and Returning the Manufacturer Identifier based on Provided Manufacturer Data
#   - Note:  The epxected format for Manufacturer Data is {dbus.UInt16(<dec-value>): [<manufacturer specific data>]}
def find_and_return__manufacturer_identifier(manufacturer_data):
    ## Variables
    # Tracking the Company Name (Note: Default is UNKNOWN)
    company_name = "-=UNKONWN=-"
    # Tracking the Company Identifier
    manufacturer_code = None

    ## Sanity Check for Manufacturer Format
    # Ensure single manufacturer / company identifier
    if len(manufacturer_data.keys()) > 1:
        # Set Company Name to Error
        company_name = "-=ERROR=-"
        # Create Error Log Entry for Unexpected Manufacturer Data
        out_log_string = "[!] Unexpected Manufacturer Data Observed! Writing to debug log\n\tManufacturerData:\t{0}".format(manufacturer_data)
        print_and_log(out_log_string, LOG__DEBUG)
    else:
        # Returns the first key element of a dictionary via iteralble and next entry
        manufacturer_code = next(iter(manufacturer_data))

    ## Searching for known Company Identifier and Return Value (i.e. Name)
    for identifier_entry in bluetooth_uuids.SPEC_ID_NAMES__COMPANY_IDENTS:
        # Check for a matching Company Identifier Code
        if int(identifier_entry, 16) == bluetooth_utils.dbus_to_python(manufacturer_code):
            company_name = bluetooth_uuids.SPEC_ID_NAMES__COMPANY_IDENTS[identifier_entry]
            if dbg != 0:
                out_log_string = "[+] Manufacturer Identified! Code:\t{0} [ {1} ]\t-\tCompany:\t{2}".format(manufacturer_code, hex(manufacturer_code), company_name)
                print_and_log(out_log_string)

    # Return the Company Name and Code Number
    return company_name, manufacturer_code

# Function for Finding and Returning Service Data Information
#   - Note: The expected format for Service Data is {dbus.String('0000fe0f-0000-1000-8000-00805f9b34fb'): [2, 16, 255, 255, 2]} as seen when communicating with the Light Orb
def find_and_return__service_data_decoding(service_data):
    ## Variables
    member_name = "-=UNKNOWN MEMBER=-"

    ## Extract out the Service Data UUID
    # Grab the Raw Service UUID
    serv_uuid = next(iter(service_data))
    # Extract to a String
    serv_uuid_string = bluetooth_utils.dbus_to_python(serv_uuid)

    ## Extract out the Short UUID from the Larger UUID
    # Pull Out Short ID
    serv_uuid_short = serv_uuid_string[4:8]     # Grab out the fourth to eigth octets in the UUID

    ## Compare and Find the Corresponding Member UUID
    # Look-up the Corresponding Member ID
    for member_id in bluetooth_uuids.SPEC_UUID_NAMES__MEMB:
        # Check for a maching Member Short UUID
        if int(member_id, 16) == int(serv_uuid_short, 16):
            # Prepare the variables with the found information
            member_name = bluetooth_uuids.SPEC_UUID_NAMES__MEMB[member_id]
            if dbg != 0:
                out_log_string = "[+] Found Member ID! ID:\t{0} ({1})\t-\t{2}".format(member_id, serv_uuid_short, member_name)
                print_and_log(out_log_string, LOG__DEBUG)

    ## Return information
    return member_name, serv_uuid_short

# Function for Finding and Returning Advertisement Type Information
def find_and_return__advertising_flag_decoding(advertising_flag):
    ## Variables
    advertisement_type = "-=UNKNOWN=-"
    advertisement_flag = None

    ## Extract out the Advertisement Flag
    if len(advertising_flag) > 1:
        out_log_string = "[!] Error: Unexpected Length of Advertising Flag [ {0} ]".format(advertising_flag)
        print_and_log(out_log_string, LOG__DEBUG)
    else:
        advertisement_flag = next(iter(advertising_flag))

    if dbg != 0:
        out_log_string = "Ad Type:\t{0}\t\tFlag:\t{1}".format(advertisement_type, advertisement_flag)
        print_and_log(out_log_string, LOG__DEBUG)

    ## Comparte and Find the Advertisement Type from Advertising Flag
    for advertising_id in bluetooth_uuids.SPEC_ID_NAMES__ADVERTISING_TYPES:
        # Compare Advertising Flag to Known Values
        if int(advertising_id, 16) == int(advertisement_flag):
            # Extract the Advertising Type Name
            advertisement_type = bluetooth_uuids.SPEC_ID_NAMES__ADVERTISING_TYPES[advertising_id]

    ## Return Information
    return advertisement_type, advertisement_flag

## TODO: WORK ON IT!!
# Function for Finding and Returning Media Device UUID Information
def find_and_return__media_uuid_decoding(media_uuid):
    print("[*] Decoding UUIDs for Media Devices")
    # Configure space

    # Iterate through ALL Media UUIDS??? Maybe make a more narrow search space?? Then aggregate in a single function

## Debugging Functions

# Function for decending into an introspection - Debug intended for human inspection
def debug__enumeration_of_introspection_tree(provided_introspection):
    #print("[*]")
    introspection_tree = ET.fromstring(provided_introspection)
    for child in introspection_tree:
        #print("Child Tag:\t\t{0}\n\tAttribs:\t{1}".format(child.tag, child.attrib))
        output_log_string = "Child Tag:\t\t{0}\n\tAttribs:\t{1}".format(child.tag, child.attrib)
        print_and_log(output_log_string)
    #print("[+]")
    output_log_string = "[+]"
    print_and_log(output_log_string)

# Function for pretty printing the GATT device JSON
def pretty_print__gatt__dive_json(device_object, complete_device_map):
    #print("Pretty Print JSON")
    output_log_string = "Pretty Print JSON"
    print_and_log(output_log_string)
    print_and_log(output_log_string, LOG__ENUM)
    #print("[ DEVICE\t-\t{0} ]".format(device_object.device_address))
    output_log_string = "[ DEVICE\t-\t{0} ]".format(device_object.device_address)
    print_and_log(output_log_string)
    print_and_log(output_log_string, LOG__ENUM)
    for ble_gatt__service in complete_device_map["Services"]:
        #print("Service\t-\t{0}".format(ble_gatt__service))
        output_log_string = "Service\t-\t{0}".format(ble_gatt__service)
        print_and_log(output_log_string)
        print_and_log(output_log_string, LOG__ENUM)
        service_handle = complete_device_map["Services"][ble_gatt__service]["Handle"]
        service_uuid = complete_device_map["Services"][ble_gatt__service]["UUID"]
        #print("-\tHandle:\t\t\t{0}".format(service_handle))
        output_log_string = "-\tHandle:\t\t\t{0}".format(service_handle)
        print_and_log(output_log_string)
        print_and_log(output_log_string, LOG__ENUM)
        #print("-\tUUID:\t\t\t{0}".format(service_uuid))
        output_log_string = "-\tUUID:\t\t\t{0}\t-\t{1}".format(service_uuid, bluetooth_utils.get_name_from_uuid(service_uuid))
        print_and_log(output_log_string)
        print_and_log(output_log_string, LOG__ENUM)
        for ble_gatt__characteristic in complete_device_map["Services"][ble_gatt__service]["Characteristics"]:
              #print("\tCharacteristic\t-\t{0}".format(ble_gatt__characteristic))
              output_log_string = "\tCharacteristic\t-\t{0}".format(ble_gatt__characteristic)
              print_and_log(output_log_string)
              print_and_log(output_log_string, LOG__ENUM)
              characteristic_uuid = complete_device_map["Services"][ble_gatt__service]["Characteristics"][ble_gatt__characteristic]["UUID"]
              characteristic_handle = complete_device_map["Services"][ble_gatt__service]["Characteristics"][ble_gatt__characteristic]["Handle"] 
              characteristic_flags = complete_device_map["Services"][ble_gatt__service]["Characteristics"][ble_gatt__characteristic]["Flags"]
              characteristic_value = complete_device_map["Services"][ble_gatt__service]["Characteristics"][ble_gatt__characteristic]["Value"]
              #print("\t-\tUUID:\t\t\t{0}".format(characteristic_uuid))
              output_log_string = "\t-\tUUID:\t\t\t{0}\t-\t{1}".format(characteristic_uuid, bluetooth_utils.get_name_from_uuid(characteristic_uuid))
              print_and_log(output_log_string)
              print_and_log(output_log_string, LOG__ENUM)
              #print("\t-\tHandle:\t\t\t{0}".format(characteristic_handle))
              output_log_string = "\t-\tHandle:\t\t\t{0}".format(characteristic_handle)
              print_and_log(output_log_string)
              print_and_log(output_log_string, LOG__ENUM)
              #print("\t-\tFlags:\t\t\t{0}".format(characteristic_flags))
              output_log_string = "\t-\tFlags:\t\t\t{0}".format(characteristic_flags)
              print_and_log(output_log_string)
              print_and_log(output_log_string, LOG__ENUM)
              #print("\t-\tValue:\t\t\t{0}".format(characteristic_value))
              output_log_string = "\t-\tValue:\t\t\t{0}".format(characteristic_value)
              print_and_log(output_log_string)
              print_and_log(output_log_string, LOG__ENUM)
              output_log_string = "\t-\tASCii:\t\t\t{0}".format(device_object.dbus_read_value__to__ascii_string(characteristic_value))
              print_and_log(output_log_string)
              print_and_log(output_log_string, LOG__ENUM)
              for ble_gatt__descriptor in complete_device_map["Services"][ble_gatt__service]["Characteristics"][ble_gatt__characteristic]["Descriptors"]:
                #print("\t\tDescriptor\t-\t\t\t{0}".format(ble_gatt__descriptor))
                output_log_string = "\t\tDescriptor\t-\t\t\t{0}".format(ble_gatt__descriptor)
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__ENUM)
                descriptor_flags = complete_device_map["Services"][ble_gatt__service]["Characteristics"][ble_gatt__characteristic]["Descriptors"][ble_gatt__descriptor]["Flags"]
                descriptor_uuid = complete_device_map["Services"][ble_gatt__service]["Characteristics"][ble_gatt__characteristic]["Descriptors"][ble_gatt__descriptor]["UUID"]
                descriptor_value = complete_device_map["Services"][ble_gatt__service]["Characteristics"][ble_gatt__characteristic]["Descriptors"][ble_gatt__descriptor]["Value"]
                #print("\t\t-\tUUID:\t\t\t{0}".format(descriptor_uuid))
                output_log_string = "\t\t-\tUUID:\t\t\t{0}\t-\t{1}".format(descriptor_uuid, bluetooth_utils.get_name_from_uuid(descriptor_uuid))
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__ENUM)
                #print("\t\t-\tFlags:\t\t\t{0}".format(descriptor_flags))
                output_log_string = "\t\t-\tFlags:\t\t\t{0}".format(descriptor_flags)
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__ENUM)
                #print("\t\t-\tValue:\t\t\t{0}".format(descriptor_value))
                output_log_string = "\t\t-\tValue:\t\t\t{0}".format(descriptor_value)
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__ENUM)

        #characteristic_value__hex_array = device_object.find_and_get__characteristic_property(characteristic_properties, 'Value')
        #characteristic_value__ascii_string = convert__hex_to_ascii(characteristic_value__hex_array)

# Function for writing output to the Debug Log
def logging__debug_log(string_to_log):
    if dbg != 0:
        print("[=] Writing to DEBUG LOG [ {0} ]".format(debug_logging))
    # Write the log information to the debug log
    with open(debug_logging, 'a') as debug_file:
        debug_file.write(string_to_log)

# Function for writing output to the General Log
def logging__general_log(string_to_log):
    if dbg != 0:
        print("[=] Writing to GENERAL LOG [ {0} ]".format(general_logging))
    # Write the log information to the general log
    with open(general_logging, 'a') as general_file:
        general_file.write(string_to_log)

# Function for writing output to the Enumeration log
def logging__enumeration_log(string_to_log):
    if dbg != 0:
        print("[=] Writing to ENUMERATION LOG [ {0} ]".format(enumerate_logging))
    # Write the log information to the enumeration log
    with open(enumerate_logging, 'a') as enumerate_file:
        enumerate_file.write(string_to_log)

# Function for writing output to the User Mode log
def logging__usermode_log(string_to_log):
    if dbg != 0:
        print("[=] Writing to USERMODE LOG [ {0} ]".format(usermode_logging))
    # Write the log information to the usermode log
    with open(usermode_logging, 'a') as usermode_file:
        usermode_file.write(string_to_log)

# Function for writing output to the Agent log
def logging__agent_log(string_to_log):
    if dbg != 0:
        print("[=] Writing to AGENT LOG [ {0} ]".format(agent_logging))
    # Write the log information to the agent log
    with open(agent_logging, 'a') as agent_file:
        agent_file.write(string_to_log)

# Function for writing output to the Database log
def logging__database_log(string_to_log):
    if dbg != 0:
        print("[=] Writing to DATABASE LOG [ {0} ]".format(database_logging))
    # Write the log information to the database log
    with open(database_logging, 'a') as database_file:
        database_file.write(string_to_log)

# Function for making a call to the desired logging function
#   - Nota Bene: Adding a '\n' at the end of any passed string to clean up logging
def logging__log_event(log_type, string_to_log):
    # Adding a newline to the end of any passed string
    string_to_log += "\n"
    # Check to see what Type of Log will be written to
    if log_type == LOG__DEBUG:
        logging__debug_log(string_to_log)
    elif log_type == LOG__GENERAL:
        logging__general_log(string_to_log)
    elif log_type == LOG__ENUM:
        logging__enumeration_log(string_to_log)
    elif log_type == LOG__USER:
        logging__usermode_log(string_to_log)
    elif log_type == LOG__AGENT:
        logging__agent_log(string_to_log)
    elif log_type == LOG__DATABASE:
        logging__database_log(string_to_log)
    else:
        if dbg != 0:
            print("[!] Error: Unknown Log Type.... Not Capturing information [ {0} ]".format(string_to_log))

# Function for Debugging Any D-Bus Signals
#   - Note: When performing basic testing the intial string is detected 
#   - Added printing of function varaibles for further debugging
# TODO: [ ] Create an input function call that gets ALL the informaiton expected by the standard
#   - NOTE: When using '*args' the expected order of data si:
#       [0]     =       Interface (e.g. org.bluez.Device1)
#       [1]     =       Dictionary of the changed value(s) with (i) the name of the changed property, (ii) the new value (i.e. change), and (iii) the signature of the data returned
#       [2]     =       Signature for the received change(s)
#   -> Expectation is that a notification (and indication?) signal is ALWAYS made of three aguments (outlined above)
#       - Found that this is ONLY true for "PropertiesChanged"(?); b/c found that "InterfacesAdded" returns 2
def debugging__dbus_signals__catchall(*args, **kwargs):        # Original debugging input function definition; NOTE: Using this version ALL of the signal information is passed via the *args variable             <---- Best inclusive function definition(?)
#def debugging__dbus_signals__catchall(interface, changed, invalidated, path, *args, **kwargs):         # New hotness debugging input function definition; thanks to BT SIG Developers V1 resources example
#def debugging__dbus_signals__catchall(interface, changed, invalidated, *args, **kwargs):         # New NEW hotness debugging input function definition; figured out "x_keyword" lets one set an input variable name
    dbus_signal_catchall__start_string = "[!] Received Signal! Debugging Signal\t-\tCatchall"
    # Add a ridiculous amount of debugging information into the debug logging file; all of which is USELESS
    #if dbg != 0:
    #    dbus_signal_catchall__start_string += "\nInput Variable Count:\t{0}\nInput Variable Names:\t{1}\nInput Varaible Defaults:\t{2}\nList of Local Parameters:\t{3}".format(debugging__dbus_signals__catchall.__code__.co_argcount, debugging__dbus_signals__catchall.__code__.co_varnames, debugging__dbus_signals__catchall.__defaults__, locals().keys())
    # Have meaningful debugging information returned; ONLY WORKS when using the function is expecting the 'interface', 'changed', and 'invalidated' input variables
    #if dbg != 0:
        # Note: Having the path might require use of the 'path_keyword = "path"' kwarg to the originating add_signal_receiver() function        <--- IT IS!!! 
        #dbus_signal_catchall__start_string += "\nInterface:\t{0}\n\tChanged:\n\t\tType:\t{1}\n\t\tItems:\t{2}\n\tInvalidated:\t{3}\n\tPath:\t{4}".format(interface, type(changed), changed.items(), invalidated, path)
        #dbus_signal_catchall__start_string += "\n\tInterface:\t{0}\n\tChanged:\n\t\tType:\t{1}\n\t\tItems:\t{2}\n\tInvalidated:\t{3}\n".format(interface, type(changed), changed.items(), invalidated)
    logging__log_event(LOG__DEBUG, dbus_signal_catchall__start_string)
    if dbg != 0:
        print(dbus_signal_catchall__start_string)
    ## Odd testing of initial data received by the signal catcher; ONLY works for keyword based call of the function?
    '''
    if kwargs is not None:
        dbus_signal_catchall__initial_data = "[-] Should not get this; no initial data found"
        try:
            dbus_signal_catchall__initial_data = "From:\t{0}\t.\t{1}".format(kwargs['dbus_interface'], kwargs['member'])
        except Exception as e:
            dbus_signal_catchall__initial_data = "Specific 'dbus_interface' and/or 'member' arguments not present.... Because of keyword missing?"
        logging__log_event(LOG__DEBUG, dbus_signal_catchall__initial_data)
    if dbg != 0:
        print(dbus_signal_catchall__initial_data)
    '''
    ## Examining '*args' received by the Debug Signal Catching Function
    dbus_signal_catchall__args__start_string = "Args:"
    logging__log_event(LOG__DEBUG, dbus_signal_catchall__args__start_string)
    if dbg != 0:
        print(dbus_signal_catchall__args__start_string)
    # Check for expected length of the arguments received; expecting three arguements passed to the debugging callback function
    if len(args) == 3:
        # Following expected number of arguments received scenario (i.e. three)
        dbus_signal_catchall__arg_details_string = "\tInterface:\t{0}\n\tChanged:\t{1}\n\tInvalidated:\t{2}".format(args[0], args[1], args[2])
        logging__log_event(LOG__DEBUG, dbus_signal_catchall__arg_details_string)
        if dbg != 0:
            print(dbus_signal_catchall__arg_details_string)
    elif len(args) == 2:
        # Following the assumption this signal is "InterfacesAdded" || "InterfacesRemoved" ?
        #   - First argument is the path of the device
        #   - Sub-interface information and properties
        dbus_signal_catchall__arg_details_string = "\tDevice Path:\t{0}\tInterface List:\n".format(args[0])
        # Iterating through the Device Properties
        for associated_interface in args[1]:
            # Add the interface to the logging string
            dbus_signal_catchall__arg_details_string += "\t\tInterface:\t{0}\n".format(associated_interface)
            # Check that there are Interface Properties (non-emtpy)
            if args[1][associated_interface]:
                dbus_signal_catchall__arg_details_string += "\t\tProperties:\t"
                # Enumerate the Interfaces Properties
                for interface_property in args[1][associated_interface]:
                    # Add each property to a list print out
                    dbus_signal_catchall__arg_details_string += "{0}, ".format(interface_property)
                    # Note: One can dig deeper and obtain the information about the value for each property
            else:
                dbus_signal_catchall__arg_details_string += "\t\tNo Properties"
        #dbus_signal_catchall__arg_details_string += "\n"       # Maybe this is not needed?
        logging__log_event(LOG__DEBUG, dbus_signal_catchall__arg_details_string)
        if dbg != 0:
            print(dbus_signal_catchall__arg_details_string)
    else:
        # Adding output mentioning the number of arguments received
        dbus_signal_catchall__args_number_string = "[!] Received an unexpected number of arguments [ {0} ]".format(len(args))
        logging__log_event(LOG__DEBUG, dbus_signal_catchall__args_number_string)
        if dbg != 0:
            print(dbus_signal_catchall__args_number_string)
        # Loop through the received args; since the number was unexpected
        for arg_item in args:
            dbus_signal_catchall__arg_string = "\tArg:\t{0}".format(arg_item)
            logging__log_event(LOG__DEBUG, dbus_signal_catchall__arg_string)
            if dbg != 0:
                print(dbus_signal_catchall__arg_string)
    ## Examining an '**kwargs' received by the Debug Signal Catching Function
    dbus_signal_catchall__kwargs__start_string = "Kwargs:"
    logging__log_event(LOG__DEBUG, dbus_signal_catchall__kwargs__start_string)
    if dbg != 0:
        print(dbus_signal_catchall__kwargs__start_string)
    # Loop through the received kwargs
    for key, value in kwargs.items():
        dbus_signal_catchall__kwarg_string = "\tKey:Value\t-\t[ {0}:{1} ]".format(key,value)
        logging__log_event(LOG__DEBUG, dbus_signal_catchall__kwarg_string)
        if dbg != 0:
            print(dbus_signal_catchall__kwarg_string)
    ## Debugging for Printing out Signal Details
    if len(args) == 3:
        dbus_signal__log_out = "ASCii Conversion Test for Args:\n"
        changed_data = args[1]
        unwrapped_data = bluetooth_utils.dbus_to_python(changed_data)
        if 'Value' in unwrapped_data:
            dbus_signal__log_out += "\t- Value:\t\t{0}".format(convert__hex_to_ascii(unwrapped_data['Value']))
        else:
            dbus_signal__log_out += "\t- No Value Found to Convert\t\t-\t\tKeys Present:\t{0}".format(unwrapped_data.keys())
        print_and_log(dbus_signal__log_out, LOG__DEBUG)
    dbus_signal_catchall__end_string = "[+] Signal Debug Complete"
    logging__log_event(LOG__DEBUG, dbus_signal_catchall__end_string)
    if dbg != 0:
        print(dbus_signal_catchall__end_string)

# Function for Evaluating the Device Class Object Error Buffer
def evaluate__device_error_buffer(device_class_object):
    out_log_string = "[*] evaluate__device_error_buffer::Attempting to Evaluate the Device Class Object Error Buffer"
    print_and_log(out_log_string, LOG__DEBUG)
    ## Evaluate the Device Class Object's Error Buffer
    if device_class_object.error_buffer is not None:        # An error exists
        # Attempt to perform fix of the error
        try:
            # Call to perform__fix_error function
            perform__fix_error(device_class_object)
        except Exception as e:
            device_class_object.error_buffer = device_class_object.understand_and_handle__dbus_errors(e)
            out_log_string = "[-] evaluate__device_error_buffer::Exception Error Occurred\t-\tError Buffer:\t[ {0} ]\n\tError:\t\t[ {1} ]".format(device_class_object.error_buffer, e)
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            out_log_string = "[*] evaluate__device_error_buffer::Alert! Try statement resolved without raising an exception"
            print_and_log(out_log_string, LOG__DEBUG)
        finally:
            out_log_string = "[*] evaluate__device_error_buffer::Completed evaluation of the Device Object Error Buffer\t[ {0} ]".format(device_class_object.error_buffer)
            print_and_log(out_log_string, LOG__DEBUG)
    else:       # No error
        out_log_string = "[+] evaluate__device_error_buffer::No error in buffer"


## Utility Functions

# Function for Checking for a Substring within a List of Sub-Strings
def check_for_substring(sub_string, string_list):
    # Convert all to lowercase to escape case sensitivity
    return any(sub_string.lower() in string_item.lower() for string_item in string_list)

# Function for Confirming Match between Expected Configuration and Information Present
def check_for_device_match(reference_dictionary, device_dictionary):
    # Variables
    pass_check = True       # Note: Default to True for AND-based check
    # Check interfaces
    for sub_interface in reference_dictionary['interfaces']:
        # AND each check interfaces exist
        pass_check = pass_check and check_for_substring(sub_interface, device_dictionary['interfaces'])
    # Check nodes
    for sub_node in reference_dictionary['nodes']:
        # AND each check nodes exist
        pass_check = pass_check and check_for_substring(sub_node, device_dictionary['nodes'])
    # Return the result
    return pass_check

## System OS function calls for implementing the (depreciated) 'gatttool'

# Function for enumerating and returning a map for identifying BlueZ Characteristics to GATT Tool Handle, Char Value Handle, and UUID
def enumerate_and_return__bluez_to_gatt_map__characteristics(bluetooth_device_address):
    # Create the command string to run
    command__list_characteristics = f"timeout 10 gatttool -b {bluetooth_device_address} --characteristics"
    # Run the command and capture the output from its execution
    command_response = subprocess.getoutput(command__list_characteristics)
    ## Add in a termination action if the gatttool return does NOT find/get/return anything
    #   - Done via a 'timeout' command preceeding the gatttool command
    if dbg != 0:
        #print("Command Response:\t{0}".format(command_response))
        output_log_string = "Command Response:\t{0}".format(command_response)
        print_and_log(output_log_string, LOG__DEBUG)
    # Examination of the Command Response; check what the response is
    if "Device or resource busy (16)" in command_response:
        #print("[-] Unable to access device\t\t-\tDue to too many connected devices")
        output_log_string = "[-] Unable to access device\t\t-\tDue to too many connected devices"
        print_and_log(output_log_string)
        return None
    # Create the basic map
    bluetooth_handle_map = {f"{bluetooth_device_address}": {} }
    # Loop through each line returned from the command response
    for characteristic_item in iter(command_response.splitlines()):
        # Extract the "Handle" value
        handle_value = characteristic_item.split(',')[0].split('=')[1].strip()
        # Extract the "Char Value Handle" value
        char_value_handle = characteristic_item.split(',')[2].split('=')[1].strip()
        # Extract the associated UUID value
        uuid_value = characteristic_item.split(',')[3].split('=')[1].strip()
        # Debug output to test the extraction of individual pieces from the gatttool command response
        if dbg != 0:
            #print("Handle:\t{0}\t\t-\tChar Value Handle:\t{1}\t\t-\tUUID:\t{2}".format(handle_value, char_value_handle, uuid_value))
            output_log_string = "Handle:\t{0}\t\t-\tChar Value Handle:\t{1}\t\t-\tUUID:\t{2}".format(handle_value, char_value_handle, uuid_value)
            print_and_log(output_log_string, LOG__DEBUG)
        # Add the entry into the bluetooth device's handle map
        bluetooth_handle_map[bluetooth_device_address].update({ handle_value : { "Char Value Handle": char_value_handle, "UUID": uuid_value } })
    # Debug output to test the map was formed correctly
    if dbg != 0:
        #print("Created Map:\t{0}".format(bluetooth_handle_map))
        output_log_string = "Created Map:\t{0}".format(bluetooth_handle_map)
        print_and_log(output_log_string, LOG__DEBUG)
    return bluetooth_handle_map

# Function to Convert GATT Tool Space Separated Hex Data into a Single Binary (plain hexadecimal dump without line number information and without a particular column layout)
def convert__hex_to_binary(space_separated_hex_data):
    # Craft the command for conversion using 'echo' and 'xxd'
    command_response__convert__hex_to_binary = subprocess.getoutput(f'echo "{space_separated_hex_data}" | xxd -r -p')
    # Return the converted data
    return command_response__convert__hex_to_binary

# Function to Convert BlueZ Python Characteristic Handles to the GATT Tool Handle format
def convert__bluez_handle_to_gatt_tool_handle(bluez__characteristic_handle):
    # Confirm that the input provided is a BlueZ Characteristic Handle
    if "char" not in bluez__characteristic_handle:
        #print("[-] Provided a non-BlueZ Characteristic Handle")
        output_log_string = "[-] Provided a non-BlueZ Characteristic Handle"
        print_and_log(output_log_string)
        return None
    # Perform the conversion of BlueZ to GATT Tool format
    gatttool__characteristic_handle = f"0x{bluez__characteristic_handle.split('char')[1]}"
    # Return the GATT Tool format handle
    return gatttool__characteristic_handle

# Function for using GATT Tool to perform a Write-Request and Listen for a Notification Response
#   - Note: One HAS to use the '-n' flag to provide a value with the write command
def gatttool__write_request_and_listen(bluetooth_device_address, characteristic_handle, conversion_map=None):
    # Check to see if a "conversion_map" was provided
    if not conversion_map:
        # Create the conversion_map
        conversion_map = enumerate_and_return__bluez_to_gatt_map__characteristics(bluetooth_device_address)
    # Extract out the Characteristic Value Handle from the Conversion Map
    expected_handle = conversion_map[bluetooth_device_address][f'{characteristic_handle}']['Char Value Handle']
    # Setup the command to run
    #   - Note: Added a leading 'timeout' command to prevent hanging due to the listening
    #command__listen_test = f"timeout 5 gatttool -b {bluetooth_device_address} --char-write-req -a {conversion_map[ble_ctf__addr][f'0x{handle_hex}']['Char Value Handle']} -n 0100 --listen"
    command__listen_test = f"timeout 5 gatttool -b {bluetooth_device_address} --char-write-req -a {expected_handle} -n 0100 --listen"
    # Run the command
    command_response = subprocess.getoutput(command__listen_test)
    ## Examine the returned output
    # Check that everything ran successfully
    if "Characteristic value was written successfully" not in command_response:
        #print("Command did NOT run successfully")
        output_log_string = "Command did NOT run successfully"
        print_and_log(output_log_string)
        return None
    ## Extract the expected data
    #   - Note: The 'expected_handle' is expected to the in the format 0xXXXX
    #   Input Vars:     original_command_response, expected_handle
    # Extract out the Space Separated Hex Data from the original command response using the epxected handle (e.g. 0x0040)
    #space_separated_hex_data = original_command_response.split(f"\nNotification handle = {expected_handle} value: ")[1]
    space_separated_hex_data = command_response.split(f"\nNotification handle = {expected_handle} value: ")[1]
    # Convert the data from hex to binary
    converted_data = convert__hex_to_binary(space_separated_hex_data)
    # Return the converted data
    return converted_data

## Callback functions for use with D-Bus and GATT functionality

# Function for Debugging GATT Notify Reply Handler Callback
def debugging__gatt_notify__reply_handler_callback():
    gatt_notify__reply_handler_callback__string = "[!] Received GATT Notify\t-\tReply Handler\t-\tCallback"
    logging__log_event(LOG__DEBUG, gatt_notify__reply_handler_callback__string)
    if dbg != 0:
        print(gatt_notify__reply_handler_callback__string)

# Function for Debugging GATT Notify Error Handler Callback
def debugging__gatt_notify__error_handler_callback(error):
    gatt_notify__error_handler_callback__string = "[!] GATT Notify\t-\tError Callback:\t-\t{0}".format(error)
    logging__log_event(LOG__DEBUG, gatt_notify__error_handler_callback__string)
    if dbg != 0:
        print(gatt_notify__error_handler_callback__string)

## Pretty printing of the UUID mapping information
def pretty_print__uuid_2_handle_map(ble_uuid_json):
    # Loop for going through the mapping
    for uuid_entry in ble_uuid_json:
        # Extract out the variables to be used
        uuid_handle = ble_uuid_json[uuid_entry]["Handle"]
        uuid_name = ble_uuid_json[uuid_entry]["Name"]
        uuid_path = ble_uuid_json[uuid_entry]["Path"]
        uuid_type = ble_uuid_json[uuid_entry]["Type"]
        #print("UUID:\t\t{0}\n\tHandle:\t{1}\n\tName:\t{2}\n\tPath:\t{3}\n\tType:\t{4}".format(uuid_entry, uuid_handle, uuid_name, uuid_path, uuid_type))
        output_log_string = "UUID:\t\t{0}\n\tHandle:\t{1}\n\tName:\t{2}\n\tPath:\t{3}\n\tType:\t{4}".format(uuid_entry, uuid_handle, uuid_name, uuid_path, uuid_type)
        print_and_log(output_log_string)

## Enumeration Functions

# Generic Function for Returning Child 'node' information from an introspection
def enumerate_and_return__introspection_interface_tree(provided_introspection, search_string):
    child_node_return_list = []
    introspection_tree = ET.fromstring(provided_introspection)
    for child in introspection_tree:
        #print("Child Tag:\t\t{0}\n\tAttribs:\t{1}".format(child.tag, child.attrib))
        if child.tag == 'node' and search_string in child.attrib['name']:
            child_node_return_list.append(child.attrib['name'])
    return child_node_return_list

# Generic Function for Creating and Returning the ``Next Level Down'' set of D-Bus Interfaces, Object, and sub-elements (e.g. Characteristics, Descriptors)
#   - Note: Utilizes the 'enumerate_and_return__introspection_interface_tree()' function
def enumerate_and_return__ble__next_level_of_gatt_information(current_level_object_path, next_level_object_path_name, search_string, system_bus=dbus.SystemBus()):
    #print("[*]")
    ## Variables
    interface_type = None
    ## Check which type of D-Bus Interface is being search for in the sub-level
    if search_string == 'service':
        interface_type = bluetooth_constants.GATT_SERVICE_INTERFACE
    elif search_string == 'char':
        interface_type = bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE
    elif search_string == 'desc':
        interface_type = bluetooth_constants.GATT_DESCRIPTOR_INTERFACE
    else:
        if dbg != 0:
            #print("[-] Error: Unknown BLE search_string passed to this function.... Aborting and returning nothing")
            output_log_string = "[-] Error: Unknown BLE search_string passed to this function.... Aborting and returning nothing"
            print_and_log(output_log_string, LOG__DEBUG)
        return None
    ## Create the Object, Interfaces, and call the method to return the list of sub-elements from this level
    next_level_object_path = current_level_object_path + "/" + next_level_object_path_name
    next_level_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, next_level_object_path)
    next_level_object_interface = dbus.Interface(next_level_object, interface_type)       ## Note: This will NEED to depend on the 'search_string', because if the wrong interface name is given, then things WILL NOT WORK
    next_level_object_properties = dbus.Interface(next_level_object, bluetooth_constants.DBUS_PROPERTIES)
    if dbg != 0:
        #print("Object Information for [ {0} ]".format(next_level_object_path))
        output_log_string = "Object Information for [ {0} ]".format(next_level_object_path)
        print_and_log(output_log_string, LOG__DEBUG)
        next_level_object_properties_array = bluetooth_utils.dbus_to_python(next_level_object_properties.GetAll(interface_type))
        for next_level_object_prop in next_level_object_properties_array:
            #print("\tProperty:\t\t{0}\n\t\tValue:\t\t{1}".format(bluetooth_utils.dbus_to_python(next_level_object_prop), bluetooth_utils.dbus_to_python(next_level_object_properties_array[next_level_object_prop])))
            output_log_string = "\tProperty:\t\t{0}\n\t\tValue:\t\t{1}".format(bluetooth_utils.dbus_to_python(next_level_object_prop), bluetooth_utils.dbus_to_python(next_level_object_properties_array[next_level_object_prop]))
            print_and_log(output_log_string)
    introspection__next_level_object_interface = next_level_object_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
    ## Find and Return the contents of Introspection of the next_level_object_interface
    next_level_object_introspection_list = enumerate_and_return__introspection_interface_tree(introspection__next_level_object_interface, search_string)
    ## Return the list of next level objects
    # Check if a return list was produced
    if next_level_object_introspection_list:
        return next_level_object_introspection_list     #, next_level_object_path
    # If not, then return None; cleans up later use for brute force enumeration
    else:
        return None
    # TODO: Include return of the paths (maybe even objects or interfaces?)
    #print("[+]")

# Function for interating through a device's services (i.e. BLE GATT Services, Characteristics, and Descriptors)
def enumerate__gatt__brute_force_enumeration(device_path, device_services_list):
    #print("[*] Beginning the Brute Force Enumeration of a BLE Device's Services, Characteristics, and Descriptors")
    output_log_string = "[*] Beginning the Brute Force Enumeration of a BLE Device's Services, Characteristics, and Descriptors"
    print_and_log(output_log_string)
    # Iterate through the device services found
    for device_service in device_services_list:
        if dbg != 1:        # ~!~
            #print("Device Service [ {0} ]".format(device_service))
            output_log_string = "Device Service [ {0} ]".format(device_service)
            print_and_log(output_log_string)
        # Obtain the list of Device Service Introspection
        device_service_introspection_list = enumerate_and_return__ble__next_level_of_gatt_information(device_path, device_service, 'service')
        if dbg != 1:        # ~!~
            #print("\tService List [ {0} ]".format(device_service_introspection_list))
            output_log_string = "\tService List [ {0} ]".format(device_service_introspection_list)
            print_and_log(output_log_string)
        # Check if there was a service list returned
        if not device_service_introspection_list:
            if dbg != 1:    # ~!~
                #print("\tNo Services Found")
                output_log_string = "\tNo Services Found"
                print_and_log(output_log_string)
            # Continue through the loop of Services
            continue
        else:
            if dbg != 0:
                #print("\tServices List Found")
                output_log_string = "\tServices List Found"
                print_and_log(output_log_string)
            # Iterate through the list of Service Characteristics for an other level deep examination
            for service_characteristic in device_service_introspection_list:
                if dbg != 1:    # ~!~
                    #print("\tCharacteristic:\t\t{0}".format(service_characteristic))
                    output_log_string = "\tCharacteristic:\t\t{0}".format(service_characteristic)
                    print_and_log(output_log_string)
                device_service_path = device_path + "/" + device_service
                # Obtain the list of Device Service Characteristic Introspection
                device_service_characteristic_introspection_list = enumerate_and_return__ble__next_level_of_gatt_information(device_service_path, service_characteristic, 'char')
                if dbg != 1:    # ~!~
                    #print("\tCharacteristic List [ {0} ]".format(device_service_characteristic_introspection_list))
                    output_log_string = "\tCharacteristic List [ {0} ]".format(device_service_characteristic_introspection_list)
                    print_and_log(output_log_string)
                # Check if there was a characteristic list returned
                if not device_service_characteristic_introspection_list:
                    if dbg != 1:
                        #print("\tNo Characteristic Found")
                        output_log_string = "\tNo Characteristic Found"
                        print_and_log(output_log_string)
                    # Continue through the loop of Characteristics
                    continue
                else:
                    if dbg != 0:
                        #print("\tCharacteristic List Found")
                        output_log_string = "\tCharacteristic List Found"
                        print_and_log(output_log_string)
                    # Iterate through the list of Service Characteristic Descriptor for another level deep examination
                    for characteristic_descriptor in device_service_characteristic_introspection_list:
                        if dbg != 1:    # ~!~
                            #print("\t\tDescriptor:\t\t{0}".format(characteristic_descriptor))
                            output_log_string = "\t\tDescriptor:\t\t{0}".format(characteristic_descriptor)
                            print_and_log(output_log_string)
                        device_service_characteristic_path = device_service_path + "/" + service_characteristic
                        # Obtain the list of Device Service Characteristic Descriptor Introspection
                        device_service_characteristic_descriptor_introspection_list = enumerate_and_return__ble__next_level_of_gatt_information(device_service_characteristic_path, 'desc')
                        if dbg != 1:    # ~!~
                            #print("\t\tDescriptor List [ {0} ]".format(device_service_characteristic_descriptor_introspection_list))
                            output_log_string = "\t\tDescriptor List [ {0} ]".format(device_service_characteristic_descriptor_introspection_list)
                            print_and_log(output_log_string)
                        # Check if there was a descriptor list returned
                        if not device_service_characteristic_descriptor_introspection_list:
                            if dbg != 1:    # ~!~
                                #print("\t\tNo Descriptor Found")
                                output_log_string = "\t\tNo Descriptor Found"
                                print_and_log(output_log_string)
                            # Continue looping thorugh Descriptors
                            continue
                        else:
                            if dbg != 0:
                                #print("\t\tDescriptor List Found")
                                output_log_string = "\t\tDescriptor List Found"
                                print_and_log(output_log_string)
    

# Function for Full Enumeration of a Bluetooth Low Energy Device
#   - Nota Bene: Used by "User Mode" and the "Passive, etc." modes
#   - TODO: Add in reconnect attempt whenever a mistake is made
def connect_and_enumerate__bluetooth__low_energy(target_bt_addr, landmine_mapping=None, security_mapping=None):

    ## Internal function declarations
    # Function for Attempting Connection to the associated Device to the Provided BLE Class Object
    def attempt__device_connect(device_class_object):
        out_log_string = "[*] attempt__device_connect::Attempting to Connect to Device using BLE Class Object"
        print_and_log(out_log_string, LOG__DEBUG)
        # Try-Except-Else-Finally Statement for Connecting to the Device
        try:
            # Connect to the device
            device_class_object.Connect()
            # Print out to perform if nothing happens above; TODO: Move to finally as last check
            out_log_string = "[+] attempt__device_connect::Connected to the target device [ {0} ]".format(device_class_object.device_address)
            print_and_log(out_log_string, LOG__DEBUG)
        except Exception as e:
            device_class_object.error_buffer = device_class_object.understand_and_handle__dbus_errors(e)
            out_log_string = "[-] attempt__device_connect::Exception Error Occurred\t-\tError Buffer:\t[ {0} ]\n\tError:\t\t[ {1} ]".format(device_class_object.error_buffer, e)
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            out_log_string = "[*] attempt__device_connect::Alert! Try statement resolved without raising an exception"
            print_and_log(out_log_string, LOG__DEBUG)
        # Always perform as last task before try statement concludes
        finally:
            # Perform a Read for the Device Connected property of the device
            device_connected = device_class_object.find_and_get__device_property("Connected")
            out_log_string = "[*] attempt__device_connect::Connection Success Flag [ {0} ]".format(device_connected)
            print_and_log(out_log_string, LOG__DEBUG)
        # Return the True/False if the Device Object is Connected
        return device_connected

    # Function for Awaiting ServicesResolved to be Completed OR Timeout
    def await__services_resolved(device_class_object):
        out_log_string = "[*] await__services_resolved::Waiting for device [ {0} ] services to be resolved".format(ble_device.device_address)
        # Variables for tracking time to wait for "ServicesResolved"
        time_sleep__seconds = 0.5
        total_time_passed__seconds = 0
        success = False
        while not device_class_object.find_and_get__device_property("ServicesResolved"):     # TODO: Add in timeout here too; NOTE: This may be causing an issue?? Maybe not?? Need to flesh out when device is enumerated versus when connection is confirmed
            # Hang and wait to make sure that the services are resolved
            time.sleep(time_sleep__seconds)     # Sleep to give time for Services to Resolve
            #if dbg != 1:    # ~!~
            #    print(".", end='')
            out_log_string += "."
            # Check for abandoning "ServicesResolved"
            if total_time_passed__seconds > timeout_limit__in_seconds:
                # Configured seconds have passed attempting to resolve services, quit and move on
                output_log_string = "\n[-] connect_and_enumerate__bluetooth__low_energy::Service Resolving Error:\tTimeout Limit Reached"
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__DEBUG)
                print_and_log(output_log_string, LOG__ENUM)
                # Exit the function
                break
            # Add to the timeout counter
            total_time_passed__seconds += time_sleep__seconds
        print_and_log(out_log_string, LOG__DEBUG)
        if device_class_object.find_and_get__device_property("ServicesResolved"):
            output_log_string = "\n[+] connect_and_enumeration__bluetooth__low_energy::Device services resolved"
        else:
            output_log_string = "\n[-] connect_and_enumeration__bluetooth__low_energy::Device services not resolved"
        print_and_log(output_log_string)
        print_and_log(output_log_string, LOG__ENUM)
        print_and_log(output_log_string, LOG__DEBUG)
        # Return the value of the ServicesResolved
        return device_class_object.find_and_get__device_property("ServicesResolved")

    # Function for Attempting Device Object Enumeration - At Device Interface Level
    def attempt__device_enumerate(device_class_object):
        out_log_string = "[*] attempt__device_enumerate::Attempting to enumerate device class object at device interface level"
        print_and_log(out_log_string, LOG__DEBUG)
        # Try-Except-Else-Finally Statement for Enumerating Device Information
        try:
            # Identify and Set Device Object Properties
            device_class_object.identify_and_set__device_properties(device_class_object.find_and_get__all_device_properties())        # Note: The call to find and get all device properties can print out high level device information
        except Exception as e:
            device_class_object.error_buffer = device_class_object.understand_and_handle__dbus_errors(e)
            out_log_string = "[-] attempt__device_enumerate::Exception Error Occurred\t-\tError Buffer:\t[ {0} ]\n\tError:\t\t[ {1} ]".format(device_class_object.error_buffer, e)
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            out_log_string = "[*] attempt__device_enumerate::Alert! Try statement resolved without raising an exception"
            print_and_log(out_log_string, LOG__DEBUG)
        finally:
            out_log_string = "[*] attempt__device_enumerate::Completed attempt to enumerate device object"
            print_and_log(out_log_string, LOG__DEBUG)
        # TODO: Determine if necessary return/error handling

    # Function for Attempting to Generate a Provided Device Class Object's Full Enumeration; NOTE: Assumption is that the enumeration is at a device level, BUT may be required at various levels; TODO: Improve DEVICE KEYWORD to ENUMERATE
    def attempt__generate_dictionary__device_enumeration(device_class_object):
        out_log_string = "[*] attempt__generate_dictionary__device_enumeration::Attempting to generatea dictionary of device enumeration"
        print_and_log(out_log_string, LOG__DEBUG)
        device_enumeration_dictionary = None
        # Try-Except-Else-Finally Statement for Generating a Device Enumerate Dictionary
        try:
            # Create Dictionary of BLE Device Enumeration
            device_enumeration_dictionary = device_class_object.find_and_get__device_introspection__full_enumeration()
        except Exception as e:
            device_class_object.error_buffer = device_class_object.understand_and_handle__dbus_errors(e)
            out_log_string = "[-] attempt__generate_dictionary__device_enumeration::Exception Error Occurred\t-\tError Buffer:\t[ {0} ]\n\tError:\t\t[ {1} ]".format(device_class_object.error_buffer, e)
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            out_log_string = "[*] attempt__generate_dictionary__device_enumeration::Alert! Try statement resolved without raising an exception"
            print_and_log(out_log_string, LOG__DEBUG)
        finally:
            out_log_string = "[*] attempt__generate_dictionary__device_enumeration::Completed attempted to generate dictionary of device information"
            print_and_log(out_log_string, LOG__DEBUG)
        out_log_string = "[*] attempt__generate_dictionary__device_enumeration::Generated Dictionary:\t\t[ {0} ]".format(device_enumeration_dictionary)
        print_and_log(out_log_string, LOG__DEBUG)
        return device_enumeration_dictionary

    # Function for Attempting to Generate a Provided Device Class Object's Service List
    def attempt__generate_list__device_services(device_class_object):
        out_log_string = "[*] attempt__generate_list__device_services::Attempting to generate a list of device services"
        print_and_log(out_log_string, LOG__DEBUG)
        device_services_list = None
        # Try-Except-Else-Finally Statement for Generating a Services List
        try:
            # Create List of BLE Device Services
            device_services_list = device_class_object.find_and_get__device_introspection__services()
        except Exception as e:
            device_class_object.error_buffer = device_class_object.understand_and_handle__dbus_errors(e)
            out_log_string = "[-] attempt__generate_list__device_services::Exception Error Occurred\t-\tError Buffer:\t[ {0} ]\n\tError:\t\t[ {1} ]".format(device_class_object.error_buffer, e)
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            out_log_string = "[*] attempt__generate_list__device_services::Alert! Try statement resolved without raising an exception"
            print_and_log(out_log_string, LOG__DEBUG)
        finally:
            out_log_string = "[*] attempt__generate_list__device_services::Completed attempted to generate list of device services"
            print_and_log(out_log_string, LOG__DEBUG)
        out_log_string = "[*] attempt__generate_list__device_services::Generated List:\t\t[ {0} ]".format(device_services_list)
        print_and_log(out_log_string, LOG__DEBUG)
        return device_services_list

    # Function for Performing Fixes based on Device Class Object Error Buffer
    def perform__fix_error(device_class_object):
        out_log_string = "[*] perform__fix_error::Attempting to Perform Fix(es) due to Device Class Object Error Buffer"
        print_and_log(out_log_string, LOG__DEBUG)
        ## Perform action based on Error Buffer value
        # Check if Error Action Requires Reconnect_Check()
        if device_class_object.error_buffer in {bluetooth_constants.RESULT_ERR_NOT_CONNECTED, bluetooth_constants.RESULT_ERR_SERVICES_NOT_RESOLVED, bluetooth_constants.RESULT_ERR_NO_DEVICES_FOUND, bluetooth_constants.RESULT_ERR_NO_REPLY, bluetooth_constants.RESULT_ERR_DEVICE_FORGOTTEN, bluetooth_constants.RESULT_ERR_REMOTE_DISCONNECT}:
            out_log_string = "[*] perform__fix_error::Error requires Reconnection Check"
            print_and_log(out_log_string, LOG__DEBUG)
            # Perform Device Reconnection
            device_class_object.Reconnect_Check()
            out_log_string = "[*] perform__fix_error::Reconnection Check Completed"
            print_and_log(out_log_string, LOG__DEBUG)
        elif device_class_object.error_buffer in {bluetooth_constants.RESULT_ERR_UNKNOWN_SERVCE, bluetooth_constants.RESULT_ERR_UNKNOWN_OBJECT}:
            out_log_string = "[*] perform__fix_error::Error requires Refindings the Device and Connecting"
            print_and_log(out_log_string, LOG__DEBUG)
            # Perform Device Refind and Connect action
        elif device_class_object.error_buffer in {bluetooth_constants.RESULT_ERR_ACTION_IN_PROGRESS}:
            out_log_string = "[*] perform__fix_error::Error require timewait for action in progress"
            print_and_log(out_log_string, LOG__DEBUG)
            # Wait some set amount of time
            time.sleep(timewait_in_progress)
        elif device_class_object.error_buffer in {bluetooth_constants.RESULT_ERR_READ_NOT_PERMITTED}:
            out_log_string = "[*] perform__fix_error::Error due to lack of permission"
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            out_log_string = "[*] perform__fix_error::Error of Unknown Type and Solution Happened\t-\t[ {0} ]".format(device_class_object.error_buffer)
            print_and_log(out_log_string, LOG__DEBUG)
        # Assume error handled ??
        #device_class_object.reset__error_buffer()

    # Function for Evaluating the Device Class Object Error Buffer
    def evaluate__device_error_buffer(device_class_object):
        out_log_string = "[*] evaluate__device_error_buffer::Attempting to Evaluate the Device Class Object Error Buffer"
        print_and_log(out_log_string, LOG__DEBUG)
        ## Evaluate the Device Class Object's Error Buffer
        if device_class_object.error_buffer is not None:        # An error exists
            # Attempt to perform fix of the error
            try:
                # Call to perform__fix_error function
                perform__fix_error(device_class_object)
            except Exception as e:
                device_class_object.error_buffer = device_class_object.understand_and_handle__dbus_errors(e)
                out_log_string = "[-] evaluate__device_error_buffer::Exception Error Occurred\t-\tError Buffer:\t[ {0} ]\n\tError:\t\t[ {1} ]".format(device_class_object.error_buffer, e)
                print_and_log(out_log_string, LOG__DEBUG)
            else:
                out_log_string = "[*] evaluate__device_error_buffer::Alert! Try statement resolved without raising an exception"
                print_and_log(out_log_string, LOG__DEBUG)
            finally:
                out_log_string = "[*] evaluate__device_error_buffer::Completed evaluation of the Device Object Error Buffer\t[ {0} ]".format(device_class_object.error_buffer)
                print_and_log(out_log_string, LOG__DEBUG)
        else:       # No error
            out_log_string = "[+] evaluate__device_error_buffer::No error in buffer"
            print_and_log(out_log_string, LOG__DEBUG)

    # Function for Evaluating if a given Characteristic Name is present in Known Maps (e.g. Mine, Permission); TODO: Decide if to split into two functions (one Mine and one Map)
    def evaluate__known_mine_check(device_class_object, reference_entry, mine_mapping, permission_mapping):
        out_log_string = "[*] evaluate__known_mine_check::Checking if the Reference Entry [ {0} ] exists in Mine Map [ {1} ] or Perm Map [ {2} ]".format(reference_entry, mine_mapping, permission_mapping)
        print_and_log(out_log_string, LOG__DEBUG)
        ## Enumerate Maps; NOTE: The expectation is Mine and Perm maps have the same categories
        for sub_category in mine_mapping:
            # Ignore the In-Review area
            if sub_category != "In-Review":
                # Check if the reference entry exists in either map
                if reference_entry in {mine_mapping[sub_category], permission_mapping[sub_category]}:
                    # Return True (Found Entry as Known Issue)
                    return True
        # Did not find the reference entry in any map
        return False

    ## Start of main function Code
    if dbg != 0:
        #print("[=] Warning! Connection to target device and initial enumeration ONLY produces a SKELETON of the device.  Reads will need to be performed against the device (e.g. populate descriptor fields)")
        output_log_string = "[=] Warning! Connection to target device and initial enumeration ONLY produces a SKELETON of the device.  Reads will need to be performed against the device (e.g. populate descriptor fields)"
        print_and_log(output_log_string)
        print_and_log(output_log_string, LOG__ENUM)
    out_log_string = "[*] ----====[ Beginning Connect and Enumeration of the Target [ {0} ] Bluetooth Low Energy Device ]====----".format(target_bt_addr)
    print_and_log(out_log_string, LOG__ENUM)
    # Debugging 
    if dbg != 0:
        output_log_string = "[=] ----====[ Beginning Connect and Enumeration of the Target [ {0} ] Bluetooth Low Energy Device ]====----\n\tMine Map:\t\t[ {1} ]\n\tSecurity Map:\t\t[ {2} ]".format(target_bt_addr, landmine_mapping, security_mapping)
        print_and_log(output_log_string, LOG__DEBUG)
    ## Creating the Objects and Structures for Enumeration
    # Create the Class Object for the Low Energy Bluez Deice
    ble_device = system_dbus__bluez_device__low_energy(target_bt_addr)
    # Attempt to Connect() to Target Device; TODO: Add post-connection error handling
    connected_flag = attempt__device_connect(ble_device)
    out_log_string = "[*] Device Connected Check:\t[ {0} ]".format(connected_flag)
    print_and_log(out_log_string, LOG__DEBUG)
    # Checks to ensure that services have been resolved prior to continuing
    if dbg != 1:    # ~!~
        print("[*] connect_and_enumerate__bluetooth__low_energy::Waiting for device [ {0} ] services to be resolved".format(ble_device.device_address), end='')
    # Await for ServicesResolved to Complete or Timeout; TODO: Add post-connection error handling
    resolved_flag = await__services_resolved(ble_device)
    out_log_string = "[*] Device Services Resolved:\t[ {0} ]".format(resolved_flag)
    print_and_log(out_log_string, LOG__DEBUG)
    ## Continue the enumeration of the device
    #ble_device.identify_and_set__device_properties(ble_device.find_and_get__all_device_properties())        # Note: The call to find and get all device properties can print out high level device information
    # Identify and Set Device Properties
    attempt__device_enumerate(ble_device)
    #ble_device_services_list = ble_device.find_and_get__device_introspection__services()
    ## Grab Full Enumeration of a Device for Unexpected Interfaces/Nodes within the E-Tree
    ble_device_enumeration_dictionary = attempt__generate_dictionary__device_enumeration(ble_device)
    out_log_string = "[!!] Device Information Dictionary:\t\t[ {0} ]".format(ble_device_enumeration_dictionary)
    print_and_log(out_log_string, LOG__DEBUG)
    # TODO: Following actions for added functionality
    #   [x] Determine IF the BLE Device has a GattService1 interface (i.e. org.freedesktop.DBus.Error.InvalidArgs: No such interface 'org.bluez.GattService1')
    #       [x] First Determine if a 'org.bluez.Device1' interface exists
    #           If the 'org.bluez.Device1' interface exists, then continue digging further
    #           [x] Determine if a 'org.bluez.GattService1' interface exists        <---- Done via nodes having a 'serv' entry
    #   [x] Determine IF one of the BLE__DEVICE_INTERFACES__LIST items appears in the ble_device_enumeration_dictionary
    #       [x] Examination of interesting Interfaces
    #       [x] Examination of interesting Node (e.g. sep1)
    #       [x] Determine if ANY unknowns are found
    #   [x] Encapsulate Device Enumeration based on Device
    ## Nested Enumeration of Device -> Service -> Characteristic -> Descriptor information
    print("DO STUFF!!!")       ## Where to place the "decision tree" for device enumeration

    try:
        device_services_list = ble_device.find_and_get__device_introspection__services()        ## Note: The step gets the 'service' information from the E-Tree dissection
    except Exception as e:
        ble_device.error_buffer = ble_device.understand_and_handle__dbus_errors(e)
        out_log_string = "[-] attempt__generate_list__device_services::Exception Error Occurred\t-\tError Buffer:\t[ {0} ]\n\tError:\t\t[ {1} ]".format(ble_device.error_buffer, e)
        print_and_log(out_log_string, LOG__DEBUG)
    print("~!~ Device Services List:\t\t{0}\t\t~!~".format(device_services_list))

    ## Check device type
    device_type = check_device_type(ble_device, ble_device_enumeration_dictionary)

    ## Perform Further Analysis of Media Device
    if device_type == "media_device":
        print("[*] Enumerating Device Type [ {0} ]".format(device_type))
        ble_device, ble_device__mapping, ble_device__mine_mapping, ble_device__permission_mapping = scan_and_enumerate__ble_device__media(ble_device, ble_device_enumeration_dictionary, landmine_mapping, security_mapping)
        # TODO: Have the media device enumeration also push out the same structures
    elif device_type == "gatt_server":
        print("[*] Enumerating Device Type [ {0} ]".format(device_type))
        # Note: Recall requirement to capture the structure details, since they MUST be returned by the larger structure
        ble_device, ble_device__mapping, ble_device__mine_mapping, ble_device__permission_mapping = scan_and_enumerate__ble_device__gatt(ble_device, ble_device_enumeration_dictionary, landmine_mapping, security_mapping)
    elif device_type == "-=UNKNOWN=-":
        ## Do DEEP NESTED ENUMERATION; TODO: Determine how to do it
        print("UNKNOWN ENUMERATION")
        # Maybe just attempt pairing anyway???
    else:
        print("WTF IS GOING ON?!?!?!")

    out_log_string = "[!] Debugging Output:\n\tDevice Mapping:\t\t{0}\n\tDevice Mine Map:\t\t{1}\n\tDevice Sec Map:\t\t{2}".format(ble_device__mapping, ble_device__mine_mapping, ble_device__permission_mapping)
    print_and_log(out_log_string)

    print("DONE DOING STUFF!!!")        ## Where to end the "decision tree" for device enumeration

    # End of function printout
    out_log_string = "[+] ----====[ Completed Connect and Enumeration of the Target [ {0} ] Bluetooth Low Energy Device ]====----".format(target_bt_addr)
    print_and_log(out_log_string, LOG__ENUM)
    # Return the device object and enumeration mapping of the BLE device
    #return ble_device, ble_device__mapping
    # Return the device object, enumeration mapping, landmine map, and security map of the BLE device
    return ble_device, ble_device__mapping, ble_device__mine_mapping, ble_device__permission_mapping

# Function for Confirming Device Type based on expected Device Properties are all confirmed within a Device Enumeration Dictionary
def check_device_type(ble_device, device_enumeration_dictionary):
    ## Definition of Device Mapping
    # GATT Server (Traditional)
    gatt_server = {
                "interfaces": [ bluetooth_constants.DEVICE_INTERFACE ],
                "nodes": [ 'serv' ] }
    # Media Device
    media_device = {
                "interfaces": [ bluetooth_constants.DEVICE_INTERFACE, bluetooth_constants.MEDIA_CONTROL_INTERFACE ],
                "nodes": [ 'sep' ] }
    ## Coupling Device Mapping to Keywords
    device_keyword_map = {
                'gatt_server': gatt_server,
                'media_device': media_device
            }

    ## Variables
    device_type = "-=UNKNOWN=-"

    out_log_string = "[*] check_device_type::Identifying Device Type"
    print_and_log(out_log_string, LOG__DEBUG)
    ## Checking for Device Type and Corresponding Response
    if check_for_device_match(gatt_server, device_enumeration_dictionary):
        # Gatt Server Check
        out_log_string = "[+] Found a Gatt Server!\n"
        out_log_string += "[+] Device Interface with Service Nodes Confirmed"      ## Expected BLEEP operation
        device_type = "gatt_server"
    elif check_for_device_match(media_device, device_enumeration_dictionary):
        # Media Device Check
        out_log_string = "[+] Found a Media Device!"
        out_log_string += "[+] Device Interface and Media Control Interface with Media Endpoint Nodes Confirmed"
        device_type = "media_device"
    elif not device_enumeration_dictionary['nodes']:
        out_log_string = "[-] Device does not present any nodes.... May be trying to hide itself? Or requires additional action?"
    else:
        # UNKNOWNS!!
        out_log_string = "[-] Unknown Device Type Observed!\n"
        out_log_string += "[-] Unknown Configuration of Interfaces and Nodes Discovered.....\n\tInterfaces:\t\t{0}\n\tNodes:\t\t{1}".format(device_enumeration_dictionary['interfaces'], device_enumeration_dictionary['nodes'])
    # TODO: Add capability to identify MULTIPLE TYPES of DEVICES and ENUMERATE THEM ALL!!!
    #   - Ex:       Phone that shows and Gatt Server + Media Device?? Maybe look for overlap and do special things??

    # Print the information to STDOUT and Debugging Logs
    print_and_log(out_log_string)
    print_and_log(out_log_string, LOG__DEBUG)

    # Return the Device Type Determined
    return device_type

# Function for Printing Out Properties
def print_properties(interface_name, properties_dictionary, indent=0):
    # Variable Configuration
    out_log_string = ""
    # Add Indenting
    out_log_string += "\t" * indent
    # Add Information
    out_log_string += "{0} Properties:\n".format(interface_name)
    for property_item in properties_dictionary:
        # Add Indenting
        out_log_string += "\t" * indent
        ## Determine Print Out for Information
        if property_item == "UUID":
            # Check for Deeper UUID Decoding
            uuid_value = bluetooth_utils.get_name_from_uuid(properties_dictionary[property_item])
            # Add Property Information + UUID Decoding
            out_log_string += "\t{0}:\t\t{1}\t\t\t[ {2} ]\n".format(property_item, properties_dictionary[property_item], uuid_value)
        # Check for Further Nested Information (expecting a dictionary)
        elif isinstance(properties_dictionary[property_item],dict):
            out_log_string += "\t{0} Info:\n".format(property_item)
            for property_sub_item in properties_dictionary[property_item]:
                out_log_string += "\t" * indent
                out_log_string += "\t\t{0}:\t\t{1}\n".format(property_sub_item,properties_dictionary[property_item][property_sub_item])
        # Treat Normally
        else:
            # Add Property Information
            out_log_string += "\t{0}:\t\t{1}\n".format(property_item, properties_dictionary[property_item])
    # Print to STDOUT
    print_and_log(out_log_string)
    # Print to Debug Log
    print_and_log(out_log_string, LOG__DEBUG)

## Functions for enumerating BLE device Services, Characteristics, and Descriptors
# Function for trying to find and return a given property from any GATT Service/Characteristic/Descriptor
def find_and_get__gatt_aspect(ble_device, gatt_aspect_name, gatt_properties_object, gatt_property_name):
    #print("Getting property [ {0} ] from aspect [ {1} ]".format(gatt_property_name, gatt_aspect_name))
    output_log_string = "Getting property [ {0} ] from aspect [ {1} ]".format(gatt_property_name, gatt_aspect_name)
    print_and_log(output_log_string)
    if gatt_aspect_name == 'Service':
        return_value = ble_device.find_and_get__service_property(gatt_properties_object, gatt_property_name)
    elif gatt_aspect_name == 'Characteristic':
        return_value = ble_device.find_and_get__characteristic_property(gatt_properties_object, gatt_property_name)
    elif gatt_aspect_name == 'Descriptor':
        return_value = ble_device.find_and_get__descriptor_property(gatt_properties_object, gatt_property_name)
    else:
        #print("[-] Well... do not know how to process that GATT aspect")
        output_log_string = "[-] Well... do not know how to process that GATT aspect"
        print_and_log(output_log_string)
        return_value = None
    return return_value

# Function for trying to enumerate a GATT Server Device using a known BLE Device Class structure
def scan_and_enumerate__ble_device__gatt(ble_device, ble_device_enumeration_dictionary, landmine_mapping, security_mapping):
    ## Continue Device Enumeration for Services, Characteristics, and Descriptors
    # Generate a Device Services List
    ble_device_services_list = attempt__generate_list__device_services(ble_device)
    # Create the JSON structure that is used for tracking the various services, characteristics, and descriptors from the GATT
    ble_device__mapping = { "Services" : {} }
    # JSON for tracking the landmine services, characteristics, and descriptors discovered during GATT enumeration
    if landmine_mapping is None:
        ble_device__mine_mapping = { "Services" : [], "Characteristics" : [], "Descriptors" : [], "In-Review" : [] }
    else:
        output_log_string = "[*] Received Mine Map\t\t[ {0} ]".format(landmine_mapping)
        print_and_log(output_log_string, LOG__DEBUG)
        ble_device__mine_mapping = landmine_mapping
    # JSON for tracking the security services, characteristics, and descriptors discovered during GATT enumeration
    if security_mapping is None:
        ble_device__permission_mapping = { "Services" : [], "Characteristics" : [], "Descriptors" : [], "In-Review" : [] }
    else:
        output_log_string = "[*] Received Permission Map\t\t[ {0} ]".format(security_mapping)
        print_and_log(output_log_string, LOG__DEBUG)
        ble_device__permission_mapping = security_mapping
    ## Nested Loops to Enumerate Services, Charactersitics, and Decriptors
    # Iterate through the 'Services' to enumerate all characteristics
    for ble_service in ble_device_services_list:
        # Internal JSON mapping
        device__service__map = create_and_return__gatt__service_json()
        if dbg != 1:
            #print("[*] BLE service\t-\t{0}".format(ble_service))
            output_log_string = "[*] scan_and_enumerate__ble_device__gatt::BLE service\t-\t{0}".format(ble_service)
            print_and_log(output_log_string, LOG__DEBUG)
        # Create the characteristic variables that we will work with
        service_path, service_object, service_interface, service_properties, service_introspection = ble_device.create_and_return__service__gatt_inspection_set(ble_service)
        # Generate the sub-list of Service Characteristics
        service_characteristics_list = ble_device.find_and_get__device__etree_details(service_introspection, 'char')       # Nota Bene: This only does the conversion of the eTree into something meaningful that can be enumerated for the Characteristic names; SAME THING as the line below
        # Next interation through the 'Characteristics' of the current Service
        for ble_service_characteristic in service_characteristics_list:
            # Internal JSON mapping
            device__characteristic__map = create_and_return__gatt__characteristic_json()
            # Generate the Interfaces for each Characteristic
            characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = ble_device.create_and_return__characteristic__gatt_inspection_set(service_path, ble_service_characteristic)
            # Check the Read/Write Flag(s) for the Characteristic interface
            characteristic_flags = ble_device.find_and_get__characteristic_property(characteristic_properties, 'Flags')
            if dbg != 0:    # ~!~
                output_log_string = "[*] scan_and_enumerate__ble_device__gatt::Characteristic [ {0} ] Flags:\t{1}".format(characteristic_path, characteristic_flags)
                print_and_log(output_log_string, LOG__DEBUG)

            ## Added return_error variable for error tracking
            return_error = None
            # Nota Bene:  In making use of the Pre-Read and Post-Read debugging can cause the "double read" necessary to populate the GATT server buffer
            if dbg != 0:
                output_log_string = "[!] scan_and_enumerate__ble_device__gatt::Pre-Read Test:\tCharacteristic Value:\t-\t{0}".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Value'))
                print_and_log(output_log_string, LOG__DEBUG)
            ## Check if there is a 'read' in the flags      <-------- TODO: Re-write this section to be an attempt-while read
            if 'read' in characteristic_flags or 'write' in characteristic_flags:      # NOTE: Even if 'write' is the only thing present, it can have a value name
                if dbg != 1:
                    output_log_string = "[*] scan_and_enumerate__ble_device__gatt::Attempt to read from Characteristic [ {0} ] due to Flags [ {1} ]".format(characteristic_path, characteristic_flags)
                    print_and_log(output_log_string, LOG__DEBUG)
                output_log_string = "[?] scan_and_enumerate__ble_device__gatt::Variable Test:\n\tService Characteristic:\t\t[ {0} ]\n\tMine Map:\t\t[ {1} ]\n\tSecurity Map:\t\t[ {2} ]".format(ble_service_characteristic, ble_device__mine_mapping, ble_device__permission_mapping)
                print_and_log(output_log_string, LOG__DEBUG)
                # Variable for tracking read attempts
                read_try_count = 0
                max_read_attempts = 3
                read_success = False
                # Debugging
                if dbg != 1:
                    output_log_string = "[*] scan_and_enumerate__ble_device__gatt::Determining if Characteristic is known Mine"
                    print_and_log(output_log_string, LOG__DEBUG)
                if ble_service_characteristic not in ble_device__mine_mapping['Characteristics']:
                    output_log_string = "[*] scan_and_enumerate__ble_device__gatt::Attempting Read of Characteristic [ {0} ]".format(ble_service_characteristic)
                    print_and_log(output_log_string, LOG__DEBUG)
                    output_log_string = "[*] scan_and_enumerate__ble_device__gatt::Checking Connectivity to Target"
                    print_and_log(output_log_string, LOG__DEBUG)
                    # Test connectivity to ensure read is possible
                    try:
                        ble_device.Reconnect_Check()
                    except Exception as e:
                        print("[-] Unable to reconnect....")
                    # Debugging
                    output_log_string = "[*] scan_and_enumerate__ble_device__gatt::Starting the repeated read loop"
                    print_and_log(output_log_string, LOG__DEBUG)
                    # Loop for read attempts
                    while read_try_count < max_read_attempts and not read_success:
                        if dbg != 1:
                            output_log_string = "[*] scan_and_enumerate__ble_device__gatt::performing read of characteristic [ {0} ]".format(ble_service_characteristic)
                            print_and_log(output_log_string, LOG__DEBUG)

                        ble_device.read__device__characteristic(characteristic_interface)       # Implementation using the Class function
                        # NOTE: ALWAYS perform the above action (with embedded error handling? Or just tracking) and then TRY the read of the property value; but maybe ALWAYS do this?
                        ## Error handling and determining if the read operation was successsful

                        # Error Handling via Error Buffer Evaluation
                        evaluate__device_error_buffer(ble_device)
                        # Determine read_success based on errors and Update the Maps' In-Review
                        if ble_device.error_buffer is not None:
                            read_success = False
                            out_log_string = "[*] scan_and_enumerate__ble_device__gatt::Read was a Failure\t-\tError Buffer:\t[ {0} ]".format(ble_device.error_buffer)
                            print_and_log(out_log_string, LOG__DEBUG)
                            # Add to Map Based on Error Buffer
                            if ble_device.error_buffer in {bluetooth_constants.RESULT_ERR_READ_NOT_PERMITTED}:
                                # Check if Characteristic already In-Review
                                if ble_device.device_map__entry_check(ble_device__permission_mapping, ble_service_characteristic):
                                    out_log_string = "[*] scan_and_enumerate__ble_device__gatt::Characteristic already In-Review for the Permission Map"
                                    print_and_log(out_log_string, LOG__DEBUG)
                                else:
                                    # Add to In-Review category of the Permissions Map
                                    ble_device__permission_mapping = ble_device.device_map__update_in_review(ble_device__permission_mapping, ble_service_characteristic)
                                    out_log_string = "[*] scan_and_enumerate__ble_device__gatt::Added Characteristic [ {0} ] to Permission Map [ {1} ]".format(ble_service_characteristic, ble_device__permission_mapping)
                                    print_and_log(out_log_string, LOG__DEBUG)
                            elif ble_device.error_buffer in {bluetooth_constants.RESULT_ERR_NO_REPLY, bluetooth_constants.RESULT_ERR_REMOTE_DISCONNECT}:
                                # Check if Characteristic already In-Review
                                if ble_device.device_map__entry_check(ble_device__mine_mapping, ble_service_characteristic):
                                    out_log_string = "[*] scan_and_enumerate__ble_device__gatt::Characteristic already In-Review for the Mine Map"
                                    print_and_log(out_log_string, LOG__DEBUG)
                                else:
                                    # Add to In-Review category of the Mine Map
                                    ble_device__permission_mapping = ble_device.device_map__update_in_review(ble_device__mine_mapping, ble_service_characteristic)
                                    out_log_string = "[*] scan_and_enumerate__ble_device__gatt::Added Characteristic [ {0} ] to Mine Map [ {1} ]".format(ble_service_characteristic, ble_device__mine_mapping)
                                    print_and_log(out_log_string, LOG__DEBUG)
                            elif ble_device.error_buffer in {bluetooth_constants.RESULT_ERR_ACTION_IN_PROGRESS}:
                                out_log_string = "[*] scan_and_enumerate__ble_device__gatt::Read on Characteristic [ {0} ] got an Action In Progress Error.... Waiting Time"
                                print_and_log(out_log_string, LOG__DEBUG)
                                time.sleep(timewait_in_progress)
                            else:
                                out_log_string = "[*] scan_and_enumerate__ble_device__gatt::Read on Characteristic [ {0} ] caused error [ {1} ].... Action Unknown.... No further action taken".format(ble_service_characteristic, ble_device.error_buffer)
                                print_and_log(out_log_string, LOG__DEBUG)
                        else:
                            read_success = True
                            out_log_string = "[*] scan_and_enumerate__ble_device__gatt::Read was a Success\t-\tError Buffer:\t[ {0} ]".format(ble_device.error_buffer)
                            print_and_log(out_log_string, LOG__DEBUG)
                        # TODO: Add in map updating, temp read, final read, and device char map update
                        # Increase read attempt incrementer
                        read_try_count += 1
                        # Debugging
                        out_log_string = "[*] scan_and_enumerate__ble_device__gatt::End of ReadValue Call Section\t-\tRead Count:\t[ {0} ]\t-\tRead Success:\t[ {1} ]".format(read_try_count, read_success)
                        print_and_log(out_log_string, LOG__DEBUG)
                    ## Validation of read attempt having been performed
                    output_log_string = "[*] scan_and_enumerate__ble_device__gatt::Beginning Validation of the Attempted Read operaiton"
                    print_and_log(output_log_string, LOG__DEBUG)

                    ## Perform moves of the Characteristic from In-Review to the Appropriate Map Category
                    # Mine Map move
                    ble_device.device_map__set_from_in_review(ble_device__mine_mapping, ble_service_characteristic, "Characteristics")
                    # Permission Map move
                    ble_device.device_map__set_from_in_review(ble_device__permission_mapping, ble_service_characteristic, "Characteristics")
                else:
                    output_log_string = "[-] Service Characteristic [ {0} ] is a known mine... Skipping Read Attempt".format(ble_service_characteristic)
                    print_and_log(output_log_string)
            # Characteristic has some other flags
            else:
                output_log_string = "[-] Characteristic [ {0} ] does not have one of the flags to act upon [ {1} ]".format(ble_service_characteristic, characteristic_flags)
                print_and_log(output_log_string, LOG__DEBUG)
            if dbg != 0:
                output_log_string = "[!] scan_and_enumerate__ble_device__gatt::Post-Read Test:\tCharacteristic Value:\t-\t{0}".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Value'))
                print_and_log(output_log_string, LOG__DEBUG)
                print_and_log(output_log_string, LOG__ENUM)

            # Read the value from characteristic properties
            characteristic_value__hex_array = ble_device.find_and_get__characteristic_property(characteristic_properties, 'Value')
            out_log_string = "[*] Checking value of Hex Array Read AGAIN:\t[ {0} ]".format(characteristic_value__hex_array)
            print_and_log(out_log_string, LOG__DEBUG)
            # Try statement to improve error handling and debugging
            try:
                characteristic_value__ascii_string = convert__hex_to_ascii(characteristic_value__hex_array)     # Note: This is where errors might occur about passing emtpy arrys to be converted
                if dbg != 1:
                    output_log_string = "[+] scan_and_enumerate__ble_device__gatt::Able to perform Hex to ASCii conversion"
                    print_and_log(output_log_string, LOG__DEBUG)
            except Exception as e:
                if dbg != 1:
                    output_log_string = "[-] scan_and_enumerate__ble_device__gatt::Unable to perform Hex to ASCii conversion"
                    print_and_log(output_log_string, LOG__DEBUG)
                output_log_string = "[-] scan_and_enumerate__ble_device__gatt::Hex to ASCii Conversion Error\t-\tCharacteristic Value ASCii String set to None"
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__ENUM)
                ble_device.understand_and_handle__dbus_errors(e)
                characteristic_value__ascii_string = None
            if dbg != 1:
                output_log_string = "\tscan_and_enumerate__ble_device__gatt::Characteristic Value:\t{0}\n\t\tRaw:\t{1}".format(characteristic_value__ascii_string, characteristic_value__hex_array)
                print_and_log(output_log_string, LOG__DEBUG)
                output_log_string = "\tscan_and_enumerate__ble_device__gatt::Value\t-\t{0}".format(characteristic_value__ascii_string)
                print_and_log(output_log_string, LOG__DEBUG)
                output_log_string = "\tscan_and_enumerate__ble_device__gatt::Handle\t-\t{0}".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Handle'))
                print_and_log(output_log_string, LOG__DEBUG)
                output_log_string = "\tscan_and_enumerate__ble_device__gatt::UUID\t-\t{0}".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'UUID'))
                print_and_log(output_log_string, LOG__DEBUG)
            # Setting the variables to be added into the JSON map for the device
            characteristic_uuid = ble_device.find_and_get__characteristic_property(characteristic_properties, 'UUID')
            characteristic_value = characteristic_value__ascii_string
            characteristic_handle = ble_device.find_and_get__characteristic_property(characteristic_properties, 'Handle')
            characteristic_raw = characteristic_value__hex_array
            # TODO: Add code for correctly producing the characteristic_handle; Check if it is simply the # part of the characteristic name (i.e. charXXXX)
            ## Move onto the Descriptors
            # Generate the sub-list of Characteristic Descriptors
            characteristic_descriptors_list = ble_device.find_and_get__device__etree_details(characteristic_introspection, 'desc')
            # Now do an iteration through the 'Descriptors' of the current Characteristic
            for ble_characteristic_descriptor in characteristic_descriptors_list:
                # Internal JSON mapping
                device__descriptor__map = create_and_return__gatt__descriptor_json()
                # Create the descriptor variables that we will work with
                descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = ble_device.create_and_return__descriptor__gatt_inspection_set(characteristic_path, ble_characteristic_descriptor)
                # Check the Read/Write Flag(s) for the Descriptor interface
                descriptor_flags = ble_device.find_and_get__descriptor_property(descriptor_properties, 'Flags')        # Note: Descriptor may NOT have a Flags property
                if dbg != 1:    # ~!~
                    output_log_string = "[*] scan_and_enumerate__ble_device__gatt::Descriptor [ {0} ] Flags:\t{1}".format(descriptor_path, descriptor_flags)
                    print_and_log(output_log_string, LOG__DEBUG)
                ## Attempt to Read/Write the value from the Descriptor; Note: Same structure as for Characteristics
                '''
                # Attempt Read
                try:
                    descriptor_interface.ReadValue({})
                except Exception as e:
                    ble_device.understand_and_handle__dbus_errors(e)
                # Attempt Write
                try
                    descriptor_interface.WriteValue("CCCCCCCC", {})
                except Exception as e:
                    ble_device.understand_and_handle__dbus_errors(e)
                '''
                # Check descriptor flags for read or write
                if descriptor_flags is not None:
                    if 'read' in descriptor_flags or 'write' in descriptor_flags:
                        output_log_string = "[*] Descriptor has a read or write flag"
                        print_and_log(output_log_string)
                        #try:
                        #    # Perform descriptor read using class function
                        #    ble_device.read__device__descriptor(descriptor_interface)
                        #except Exception as e:
                        #    output_log_string = "[-] scan_and_enumerate__ble_device__gatt::Descriptor read failed"
                        #    print_and_log(output_log_string, LOG__DEBUG)
                        #    ble_device.understand_and_handle__dbus_errors(e)
                # Update the current descriptor map
                device__descriptor__map["Flags"] = descriptor_flags
                # Update to the characteristic map
                device__characteristic__map["Descriptors"][ble_characteristic_descriptor] = device__descriptor__map
            # Update the current characteristic map
            device__characteristic__map["UUID"] = characteristic_uuid
            device__characteristic__map["Value"] = characteristic_value
            device__characteristic__map["Handle"] = characteristic_handle
            device__characteristic__map["Flags"] = characteristic_flags
            device__characteristic__map["Raw"] = characteristic_raw
            # Update to the services map
            device__service__map["Characteristics"][ble_service_characteristic] = device__characteristic__map
        # Get the variables we are looking for
        service_uuid = ble_device.find_and_get__service_property(service_properties, 'UUID')
        # Update to the current service map
        device__service__map["UUID"] = service_uuid
        # Update to the device map
        ble_device__mapping["Services"][ble_service] = device__service__map
    output_log_string = "[*] Cleaning up generated maps\n\tMine:\t[ {0} ]\n\tSecurity:\t[ {1} ]".format(ble_device__mine_mapping, ble_device__permission_mapping)
    print_and_log(output_log_string, LOG__DEBUG)
    # Cleaning up the Landmine Map (e.g. removing duplicates from In-Review)
    ble_device__mine_mapping = ble_device.device_map__clean_map(ble_device__mine_mapping)
    # Cleaning up the Security Map (e.g. removing duplicates from In-Review)
    ble_device__permission_mapping = ble_device.device_map__clean_map(ble_device__permission_mapping)
    # Debug output test for the mine map
    if dbg != 1:
        output_log_string = "[+] scan_and_enumerate__ble_device__gatt::Landmine Map Produced:\t\t[ {0} ]".format(ble_device__mine_mapping)
        print_and_log(output_log_string, LOG__DEBUG)
        output_log_string = "[+] scan_and_enumerate__ble_device__gatt::Security Map Produced:\t\t[ {0} ]".format(ble_device__permission_mapping)
        print_and_log(output_log_string, LOG__DEBUG)
    # Output for Enumeration
    output_log_string = "[+] Landmine Map Produced:\t\t[ {0} ]".format(ble_device__mine_mapping)
    print_and_log(output_log_string, LOG__ENUM)
    output_log_string = "[+] Security Map Produced:\t\t[ {0} ]".format(ble_device__permission_mapping)
    print_and_log(output_log_string, LOG__ENUM)
    # Return the device object, enumeration mapping, landmine map, and security map of the BLE device
    return ble_device, ble_device__mapping, ble_device__mine_mapping, ble_device__permission_mapping

## Functions for enumerating BLE device Media Controls, Endpoints, and Transports
# Function for trying to enumerate a Media Device using a known BLE Device Class structure
def scan_and_enumerate__ble_device__media(ble_device, ble_device_enumeration_dictionary, landmine_mapping, security_mapping):
    # Generate a Device Services List
    ble_device_services_list = attempt__generate_list__device_services(ble_device)
    # Create the JSON structure that is used for tracking the various services, characteristics, and descriptors from the GATT
    #ble_device__mapping = { "Services" : {} }
    ble_device__mapping = { "Audio" : {} }     # TODO: Determine the correct structure for an Audio/Media Device
    # JSON for tracking the landmine services, characteristics, and descriptors discovered during GATT enumeration
    if landmine_mapping is None:
        ble_device__mine_mapping = { "Controls" : [], "Players" : [], "Endpoints" : [], "Transports" : [], "In-Review" : [] }
    else:
        output_log_string = "[*] Received Mine Map\t\t[ {0} ]".format(landmine_mapping)
        print_and_log(output_log_string, LOG__DEBUG)
        ble_device__mine_mapping = landmine_mapping
    # JSON for tracking the security services, characteristics, and descriptors discovered during GATT enumeration
    if security_mapping is None:
        ble_device__permission_mapping = { "Controls" : [], "Players" : [], "Endpoints" : [], "Transports" : [], "In-Review" : [] }
    else:
        output_log_string = "[*] Received Permission Map\t\t[ {0} ]".format(security_mapping)
        print_and_log(output_log_string, LOG__DEBUG)
        ble_device__permission_mapping = security_mapping

    out_log_string = "[*] Generating Media Control Inspection using Structures"
    print_and_log(out_log_string, LOG__DEBUG)

    ## Outline for Full Enumeration of a Media Device
    # Start with Creating Structures for the Top (e.g. Device) level of the BLE
    media_control_path, media_control_object, media_control_interface, media_control_properties, media_control_introspection = ble_device.create_and_return__control__media_inspection_set()

    # Print out properties
    media_control_properties_array = ble_device.find_and_get__all_media_control_properties(media_control_properties)
    print_properties("Media Control", media_control_properties_array)

    # Determine Nodes for Media Device
    serv__node_list = [serv_match for serv_match in ble_device_enumeration_dictionary['nodes'] if "serv" in serv_match.lower()]
    sep__node_list = [sep_match for sep_match in ble_device_enumeration_dictionary['nodes'] if "sep" in sep_match.lower()]
    player__node_list = [player_match for player_match in ble_device_enumeration_dictionary['nodes'] if "player" in player_match.lower()]

    if dbg != 0:
        out_log_string = "\tService Node List:\t\t{0}\n\tSep Node List:\t\t{1}".format(serv__node_list, sep__node_list)
        print_and_log(out_log_string, LOG__DEBUG)

    ## One Loop for SEP + One Loop for SERV
    # For-Loop into the Sub Nodes
    for sep_interface in sep__node_list:
        out_log_string = "\t--/ Sep Interface:\t\t{0}\t/--".format(sep_interface)
        print_and_log(out_log_string)

        # Clear existing strcture hold
        device__sep__map = create_and_return__media__endpoint_json()

        # Create the Sub Node's Structures
        media_endpoint_path, media_endpoint_object, media_endpoint_interface, media_endpoint_properties, media_endpoint_introspection = ble_device.create_and_return__endpoint__media_inspection_set(sep_interface)
        media_endpoint_properties_array = ble_device.find_and_get__all_media_endpoint_properties(media_endpoint_properties)

        # Print out Properties
        print_properties("Media Endpoint", media_endpoint_properties_array, indent=1)

        # Add to the device structure   |   Note: Check if there should be an Unknown dump property to all the JSON dictionary maps
        '''
        device__sep__map['UUID'] = media_endpoint_properties_array['UUID']
        device__sep__map['Codec'] = media_endpoint_properties_array['Codec']
        device__sep__map['Vendor'] = media_endpoint_properties_array['Vendor']
        device__sep__map['Capabilities'] = media_endpoint_properties_array['Capabilities']
        device__sep__map['Metadata'] = media_endpoint_properties_array['Metadata']
        device__sep__map['Device'] = media_endpoint_properties_array['Device']
        device__sep__map['DelayReporting'] = media_endpoint_properties_array['DelayReporting']
        device__sep__map['Locations'] = media_endpoint_properties_array['Locations']
        device__sep__map['SupportedContext'] = media_endpoint_properties_array['SupportedContext']
        device__sep__map['Context'] = media_endpoint_properties_array['Context']
        device__sep__map['QoS'] = media_endpoint_properties_array['QoS']
        '''
        for sep_property in media_endpoint_properties_array:
            device__sep__map[sep_property] = media_endpoint_properties_array[sep_property]

        # Determine Nodes for the Sub Node Element
        sub_node_enumeration_map = ble_device.find_and_get__interface_introspection__full_enumeration(media_endpoint_introspection)

        if dbg != 0:
            out_log_string = "\t\tSub-Node Map:\t\t{0}".format(sub_node_enumeration_map)
            print_and_log(out_log_string, LOG__DEBUG)

        # One more nested sub looooooop??? (e.g. Media Transport Layer)
        if not sub_node_enumeration_map['nodes']:
            if dbg != 0:
                out_log_string = "\t\tNo Sub-Sub-Nodes"
                print_and_log(out_log_string, LOG__DEBUG)
        else:
            if dbg != 0:
                out_log_string = "\t\tSub-Sub-Node(s) Located"
                print_and_log(out_log_string, LOG__DEBUG)

            # Determine Nodes for Media Endpoint (e.g. Sub-Node)
            fd__node_list = [fd_match for fd_match in sub_node_enumeration_map['nodes'] if "fd" in fd_match.lower()]

            if dbg != 0:
                out_log_string = "Fd Node List:\t\t{0}\t\t{1}".format(fd__node_list, type(fd__node_list))
                print_and_log(out_log_string, LOG__DEBUG)

            # For-Loop into the Sub Sub Nodes
            for fd_interface in fd__node_list:
                out_log_string = "\t\t--/ Fd Interface:\t\t{0}\t/--".format(fd_interface)
                print_and_log(out_log_string)
                print_and_log(out_log_string, LOG__DEBUG)

                # Clear existing structure hold
                device__fd__map = create_and_return__media__transport_json()

                # Create the Sub Sub Node's Structures      ## NOTE: Code dying around this point..... Currently makes assumption that Media Transport has a find_and_get__all_media_transport_properties
                media_transport_path, media_transport_object, media_transport_interface, media_transport_properties, media_transport_introspection = ble_device.create_and_return__transport__media_inspection_set(sep_interface, fd_interface)
                media_transport_properties_array = ble_device.find_and_get__all_media_transport_properties(media_transport_properties)

                # Print out Properties
                print_properties("Media Transport", media_transport_properties_array, indent=2)

                # Add to the device structure
                '''
                device__fd__map['Device'] = media_transport_properties_array['Device']
                device__fd__map['UUID'] = media_transport_properties_array['UUID']
                device__fd__map['Codec'] = media_transport_properties_array['Codec']
                device__fd__map['Configuration'] = media_trancreate_and_return__media__player_jsosport_properties_array['Configuration']
                device__fd__map['State'] = media_transport_properties_array['State']
                device__fd__map['Delay'] = media_transport_properties_array['Delay']
                device__fd__map['Volume'] = media_transport_properties_array['Volume']
                device__fd__map['Endpoint'] = media_transport_properties_array['Endpoint']
                device__fd__map['Location'] = media_transport_properties_array['Location']
                device__fd__map['Metadata'] = media_transport_properties_array['Metadata']
                device__fd__map['Links'] = media_transport_properties_array['Links']
                device__fd__map['QoS'] = media_transport_properties_array['QoS']
                '''
                for fd_property in media_transport_properties_array:
                    device__fd__map[fd_property] = media_transport_properties_array[fd_property]

                # Check for Deeper Sub-Elements
                sub_sub_node_enumeration_map = ble_device.find_and_get__interface_introspection__full_enumeration(media_transport_introspection)
                if not sub_sub_node_enumeration_map['nodes']:
                    out_log_string = "\t\t\tNo Further Sub-Sub-Sub Nodes"
                    print_and_log(out_log_string, LOG__DEBUG)
                else:
                    out_log_string = "\t\t\tFurther Sub-Sub-Sub Nodes Identified:\t{0}".format(sub_sub_node_enumeration_map['nodes'])
                    print_and_log(out_log_string, LOG__DEBUG)

                # Add fd interface under the current sep interface
                device__sep__map["fds"][fd_interface] = device__fd__map
    # TODO: Add UUID Identification for Media UUID
    #   -> Note: Found the UUID for 0x110B under BT SIG Service Class
    #       - URL:      https://bitbucket.org/bluetooth-SIG/public/src/main/assigned_numbers/uuids/service_class.yaml
    # TODO: Add output for structures related to mapping of the Media Device
    #   - Mimic the structures made in the GATT Device enumeration function
        ble_device__mapping["Audio"][sep_interface] = device__sep__map
        #device__service__map["Characteristics"][ble_service_characteristic] = device__characteristic__map

    # For-Loop for Services
    for serv_interface in serv__node_list:
        out_log_string = "\t--/ Serv Interface:\t\t{0}\t/--".format(serv_interface)
        print_and_log(out_log_string)

    # For-Loop for Players (e.g. player0)
    for player_interface in player__node_list:
        out_log_string = "\t--/ Player Interface:\t\t{0}\t/--".format(player_interface)
        print_and_log(out_log_string)

        # Clear existing structure hold
        device__player__map = create_and_return__media__player_json()

        # Create the Sub Node's Structures
        media_player_path, media_player_object, media_player_interface, media_player_properties, media_player_introspection = ble_device.create_and_return__player__media_inspection_set(player_interface)
        media_player_properties_array = ble_device.find_and_get__all_media_player_properties(media_player_properties)

        # Print out Properties
        print_properties("Media Player", media_player_properties_array, indent=1)

        # Add to the device structure
        #device__player__map[] = media_player_properties_array[]
        for player_property in media_player_properties_array:
            device__player__map[player_property] = media_player_properties_array[player_property]

        # Determine Nodes for the Sub Node Element
        sub_node_enumeration_map = ble_device.find_and_get__interface_introspection__full_enumeration(media_player_introspection)

        #print("[!] Media Player Properties:\t\t{0}".format(media_player_properties_array))

        #print("[!] Sub Node Enumeration Map:\t\t{0}".format(sub_node_enumeration_map))

        if dbg != 0:
            out_log_string = "\t\tSub-Node Map:\t\t{0}".format(sub_node_enumeration_map)
            print_and_log(out_log_string, LOG__DEBUG)

        # One more nested sub looooooop??? (e.g. Media Transport Layer)
        if not sub_node_enumeration_map['nodes']:
            if dbg != 0:
                out_log_string = "\t\tNo Sub-Sub-Nodes"
                print_and_log(out_log_string, LOG__DEBUG)
        else:
            if dbg != 0:
                out_log_string = "\t\tSub-Sub-Node(s) Located"
                print_and_log(out_log_string, LOG__DEBUG)

        ## Testing BullShit:
        # Can code identify and force function of a media player
        media_player_interface.Stop()       # WORKS!
        ## Potential Attacks:
        # If .Repeat exists are a property on the interface then change to:  off, singletrack, alltracks, group
        # If .Shuffle exists as a property then change to: off, alltracks, group
        # If .Scan exists as a property then change to: off, alltracks, group
        # NOTA BENE: The above properties SHOULD display as WRITEABLE!  <------ Known via documentation AND NOT VIA PROPERTY READ (as seen with Characteristics)
        # If .Browsable exists as a property then IMMEDIATELY ATTEMPT TO BROWSE THE TARGET AS A MediaFolder
        # If .Searchable exists as a property then IMMEDIATELY ATTEMPT TO SEARCH THE TARGET AS A MediaFolder
        # If. ObexPort (experimental) exists as a proeprty then one can "... get cover art using BIP over OBEX on this PSM port"
        #   -> Nota Bene: If an .ImgHandle (experimental) exists then one can use the property to track the image handle
        #       - "... available and valid only during the lifetime of an OBEX BIP connection to the ObexPort." (seen in the wild when looking at YouTube videos)

    # Clean Maps and Prepare Debugging / Output
    ble_device__permission_mapping = ble_device.device_map__clean_map(ble_device__permission_mapping)
    # Debug output test for the mine map
    if dbg != 1:
        output_log_string = "[+] scan_and_enumerate__ble_device__media::Landmine Map Produced:\t\t[ {0} ]".format(ble_device__mine_mapping)
        print_and_log(output_log_string, LOG__DEBUG)
        output_log_string = "[+] scan_and_enumerate__ble_device__media::Security Map Produced:\t\t[ {0} ]".format(ble_device__permission_mapping)
        print_and_log(output_log_string, LOG__DEBUG)
    # Output for Enumeration
    output_log_string = "[+] Landmine Map Produced:\t\t[ {0} ]".format(ble_device__mine_mapping)
    print_and_log(output_log_string, LOG__ENUM)
    output_log_string = "[+] Security Map Produced:\t\t[ {0} ]".format(ble_device__permission_mapping)
    print_and_log(output_log_string, LOG__ENUM)
    # Return the device object, enumeration mapping, landmine map, and security map of the BLE device
    return ble_device, ble_device__mapping, ble_device__mine_mapping, ble_device__permission_mapping

## Creation and Return Functions

# Function for creating and returning the default system Bluetooth Adapter Object, Interface, and Properties
def create_and_return__system_adapter_dbus_elements(system_bus=dbus.SystemBus()):
    #print("[*]")
    # Create the Object for the Adapter Interface
    system_adapter_object = system_bus.get_object(bluetooth_constants. BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE + bluetooth_constants.ADAPTER_NAME)
    system_adapter_interface = dbus.Interface(system_adapter_object, bluetooth_constants.ADAPTER_INTERFACE)
    system_adapter_properties = dbus.Interface(system_adapter_object, bluetooth_constants.DBUS_PROPERTIES)
    #print("[+]")
    return system_adapter_object, system_adapter_interface, system_adapter_properties

# Function for creating and returning the specific system Bluetooth Adapter Object, Interface, and Properties
def create_and_return__system_adapter_dbus_elements__specific_hci(bluetooth_adapter=bluetooth_constants.ADAPTER_NAME, system_bus=dbus.SystemBus()):
    #print("[*]")
    # Create the Object for the Adapter Interface
    try:        # Attempt to create the D-Bus object; check that one exists
        system_adapter_object = system_bus.get_object(bluetooth_constants. BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE + bluetooth_constants.ADAPTER_NAME)
        system_adapter_interface = dbus.Interface(system_adapter_object, bluetooth_constants.ADAPTER_INTERFACE)
        system_adapter_properties = dbus.Interface(system_adapter_object, bluetooth_constants.DBUS_PROPERTIES)
        return system_adapter_object, system_adapter_interface, system_adapter_properties
    except dbus.exceptions.DBusException:
        print("[-] No Bluetooth Adapter found.... Raising errors ALL THE WAY TO THE TOP!!")
        raise dbus.exceptions.DBusException
    #print("[+]")

# Function for creating an Object Manager and returning a list of potential devices found from Discovery()
#   - Note: Only searching for Device1 profile interfaces
#   - Does NOT need adding the ADAPTER INTERFACE to this function
#def create_and_return__discovered_managed_objects(bluetooth_adapter=bluetooth_constants.ADAPTER_INTERFACE, system_bus=dbus.SystemBus()):
def create_and_return__discovered_managed_objects(system_bus=dbus.SystemBus()):
    #print("[*]")
    # Create Variables for tracking
    devices_found = []
    #device_names = []
    device_address, device_name = None, None
    # Create an Object Manager and associated Interface
    system_object_manager_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, "/")
    system_object_manager_interface = dbus.Interface(system_object_manager_object, bluetooth_constants.DBUS_OM_IFACE)
    
    # Get an array of managed objects
    system_managed_objects_items = system_object_manager_interface.GetManagedObjects().items()      # Returns a list of found devices from Discovery()
    system_managed_objects = system_object_manager_interface.GetManagedObjects()
    
    # Enumerate through the managed objects looking for Device1 profile interfaces
    for path, ifaces in system_managed_objects.items():
        # Iterate through the interfaces looking for a specific type/name
        for iface_name in ifaces:
            if iface_name == bluetooth_constants.DEVICE_INTERFACE:
                # Note: Built-in assumption is that there is ALWAYS a Bluetooth Address, but only sometimes a Bluetooth Name (hence the if-else statement)
                if dbg != 0:
                    #print("---------------------------\nDevice Path:\t\t{0}".format(path))
                    output_log_string = "---------------------------\nDevice Path:\t\t{0}".format(path)
                    print_and_log(output_log_string, LOG__DEBUG)
                item_device_properties = ifaces[bluetooth_constants.DEVICE_INTERFACE]
                # Tracking the addresses of devices seen
                if 'Address' in item_device_properties:
                    if dbg != 0:
                        #print("\tDevice BT ADDR:\t{0}".format(bluetooth_utils.dbus_to_python(item_device_properties['Address'])))
                        output_log_string = "\tDevice BT ADDR:\t{0}".format(bluetooth_utils.dbus_to_python(item_device_properties['Address']))
                        print_and_log(output_log_string, LOG__DEBUG)
                    #devices_found.append(bluetooth_utils.dbus_to_python(item_device_properties['Address']))
                    device_address = bluetooth_utils.dbus_to_python(item_device_properties['Address'])
                # Tracking the name of the devices seen
                if 'Name' in item_device_properties:
                    if dbg != 0:
                        output_log_string = "\tDevice BT Name:\t{0}".format(bluetooth_utils.dbus_to_python(item_device_properties['Name']))
                        print_and_log(output_log_string, LOG__DEBUG)
                    #device_names.append(bluetooth_utils.dbus_to_python(item_device_properties['Name']))
                    device_name = bluetooth_utils.dbus_to_python(item_device_properties['Name'])
                # Debugging of the entire device properties array
                if dbg != 0:
                    #print("\tDevice Properties:\t\t{0}".format(item_device_properties))
                    output_log_string = "\tDevice Properties:\t\t{0}".format(item_device_properties)
                    print_and_log(output_log_string, LOG__DEBUG)
                    #print("---------------------------")
                    output_log_string = "---------------------------"
                    print_and_log(output_log_string, LOG__DEBUG)
                # Combine the information found into a tuple for tracking devices_found
                device_info = (device_address, device_name)
                # Append information to the devices_found list
                devices_found.append(device_info)
                # Reset the variables for the next round
                device_address, device_name = None, None
    #print("[+]")
    # Return the list of device addresses found
    return devices_found

# Function for creating a Device Object Path, Object, Interface, and Properties for a given Device (via BT_ADDR)
def create_and_return__device_dbus_elements(bluetooth_address, system_bus=dbus.SystemBus()):
    #print("[*]")
    # Convert the bluetooth_address from the ':' separated form into the D-Bus '_' sepearated form (using bluetooth_utils) for the device object path
    device_path = bluetooth_utils.device_address_to_path(bluetooth_address, bluetooth_constants.BLUEZ_NAMESPACE + bluetooth_constants.ADAPTER_NAME)
    # Create the device Object
    device_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, device_path)
    # Create the device Interface
    device_interface = dbus.Interface(device_object, bluetooth_constants.DEVICE_INTERFACE)
    # Create the device Properties
    device_properties = dbus.Interface(device_object, bluetooth_constants.DBUS_PROPERTIES)
    # Debugging Information
    if dbg != 0:
        device_properties_array = bluetooth_utils.dbus_to_python(device_properties.GetAll(bluetooth_constants.DEVICE_INTERFACE))
        for device_prop in device_properties_array:
            #print("Device Property:\t\t{0}\n\tValue:\t\t{1}".format(bluetooth_utils.dbus_to_python(device_prop), bluetooth_utils.dbus_to_python(device_properties_array[device_prop])))
            output_log_string = "Device Property:\t\t{0}\n\tValue:\t\t{1}".format(bluetooth_utils.dbus_to_python(device_prop), bluetooth_utils.dbus_to_python(device_properties_array[device_prop]))
            print_and_log(output_log_string, LOG__DEBUG)
            if device_prop == 'UUIDs':
                for uuid_entry in bluetooth_utils.dbus_to_python(device_properties_array[device_prop]):
                    #print("\t\tUUID:\t\t{0}\n\t\tValue:\t\t{1}".format(uuid_entry, bluetooth_utils.get_name_from_uuid(uuid_entry)))
                    output_log_string = "\t\tUUID:\t\t{0}\n\t\tValue:\t\t{1}".format(uuid_entry, bluetooth_utils.get_name_from_uuid(uuid_entry))
                    print_and_log(output_log_string, LOG__DEBUG)
    # Create the device Introspection
    device_introspection = device_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
    # Create the eTree from the Introspection
    device_tree = ET.fromstring(device_introspection)
    # Enumerate through the eTree looking for the Services attached to the Device (Note: Assuming BLE Device)
    device_services_list = []
    for child in device_tree:
        if dbg != 0:
            #print("Child Tag:\t\t{0}\n\tAttribs:\t\t{1}".format(child.tag, child.attrib))
            output_log_string = "Child Tag:\t\t{0}\n\tAttribs:\t\t{1}".format(child.tag, child.attrib)
            print_and_log(output_log_string, LOG__DEBUG)
        # Check for the expected 'service' information
        if child.tag == 'node' and 'service' in child.attrib['name']:
            if dbg != 0:
                #print("\tAttrib:\t{0}\n\t\tValue:\t{1}".format(child.attrib, child.attrib['name']))
                output_log_string = "\tAttrib:\t{0}\n\t\tValue:\t{1}".format(child.attrib, child.attrib['name'])
                print_and_log(output_log_string, LOG__DEBUG)
            device_services_list.append(child.attrib['name'])
    # Now return the findings from this dive into the Device Interface
    #print("[+]")
    return device_object, device_interface, device_properties, device_introspection, device_services_list

# Function for generating and returning a generic GATT service JSON
def create_and_return__gatt__service_json():
    generic_service_json = {
        "UUID" : '',                # String
        "Primary" : None,           # Boolean
        "Includes" : None,          # Array{object}
        "Handle" : None,            # uint16
        "Characteristics" : {}
    }
    return generic_service_json

# Function for generating and returning a generic GATT characteristic JSON
def create_and_return__gatt__characteristic_json():
    generic_characteristic_json = {
        "UUID" : '',                # String
        "Service" : None,           # Object
        "Value" : None,             # Array{byte}
        "WriteAcquired" : None,     # Boolean
        "NotifyAcquired" : None,    # Boolean
        "Notify" : None,            # Boolean
        "Flags" : None,             # Array{string}
        "Handle" : None,            # uint16
        "MTU" : None,               # uint16
        "Descriptors" : {}
    }
    return generic_characteristic_json

# Function for generating and returning a generic GATT descriptor JSON
def create_and_return__gatt__descriptor_json():
    generic_descriptor_json = {
        "UUID" : '',                # String
        "Characteristic" : None,    # Object
        "Value" : None,             # Array{byte}
        "Flags" : None,             # Array{string}
        "Handle" : None             # uint16
    }
    return generic_descriptor_json

# Function for generating and returning a generic BLE GATT json for bluetoothctl gatt.list-attributes command
def create_and_return__bluetoothctl__ble_gatt_json():
    # Note: The below is for the information that is to be associated with a given UUID
    ble_gatt_json = {
        "Handle" : '',
        "Name" : '',
        "Path" : '',
        "Type" : ''
            }
    return ble_gatt_json

# Function for generating and returning a generic Media Control JSON
def create_and_return__meida__control_json():
    generic_media_control_json = {
        "Connected" : '',           # Boolean
        "Player" : ''               # Object
            }
    return generic_media_control_json

# Function for generating and returning a generic Media Player JSON
def create_and_return__media__player_json():
    generic_media_player_json = {
        "Equalizer" : '',           # String
        "Repeat" : '',              # String
        "Shuffle" : '',             # String
        "Scan" : '',                # String
        "Status" : '',              # String
        "Position" : '',            # Position
        "Track" : '',               # Dictionary of Metadata
        "Device" : '',              # Object
        "Name" : '',                # String
        "Type" : '',                # String
        "Subtype" : '',             # String
        "Browsable" : '',           # Boolean
        "Searchable" : '',          # Boolean
        "Playlist" : '',            # Object
        "ObexPort" : ''             # uint16
            }
    return generic_media_player_json

# Function for generating and returning a generic Media Endpoint JSON  [ BLE SEP ]
def create_and_return__media__endpoint_json():
    generic_media_endpoint_json = {
        "UUID" : '',                # String
        "Codec" : '',               # Byte
        "Vendor" : '',              # uint32_t
        "Capabilities" : '',        # Array{byte}
        "Metadata" : '',            # Array{byte}
        "Device" : '',              # Object
        "DelayReporting" : '',      # Boolean
        "Locations" : '',           # uint32
        "SupportedContext" : '',    # uint16
        "Context" : '',             # uint16
        "QoS" : '',                 # Dictionary
        "fds" : {}                  # Media Transports
            }
    return generic_media_endpoint_json

# Function for generating and returning a generic Media Transport JSON
def create_and_return__media__transport_json():
    generic_media_transport_json = {
        "Device" : '',              # Object
        "UUID" : '',                # String
        "Codec" : '',               # Byte
        "Configuration" : '',       # Array{byte}
        "State" : '',               # String
        "Delay" : '',               # uint16
        "Volume" : '',              # uint16
        "Endpoint" : '',            # Object
        "Location" : '',            # uint32
        "Metadata" : '',            # Array{byte}
        "Links" : '',               # Array{object} (Note: Two variants exist in the documentation as of 2025/06/05)
        "QoS" : ''                  # Dictionary
            }
    return generic_media_transport_json

# Function for scanning for devices and returning the list of Bluetooth Addresses
def create_and_return__bluetooth_scan__discovered_devices():
    if dbg != 0:
        print("[*] Scanning for Discoverable Bluetooth Devices")
    ## Step 1:  Create an adapter object the user can perform scans with
    # Create an adapter class object
    test_adapter = system_dbus__bluez_adapter()
    
    ## Step 2:  Have a method (of the adapter) that can enable + filter device scanning & perform the scan
    
    # Set a custom discovery filter                                                                             (Step 2i)
    custom_discovery_filter_test = {'Transport': 'auto'}
    test_adapter.set_discovery_filter(custom_discovery_filter_test)
    
    # Scan for devices via the adapter class object                                                             (Step 2ii)
    #test_adapter.run_scan()
    try:
        test_adapter.run_scan__timed()
    except dbus.exceptions.DBusException:
        raise dbus.exceptions.DBusException
    # Note: Changed above to run a FIVE SECOND scan by default
    
    # Show the device that were found using the adapter class objcet run_scan() method call                     (Step 2iii)
    #test_adapter.devices_found
    if dbg != 0:
        print("[+] List of Devices Found:\t{0}".format(test_adapter.devices_found))
    return test_adapter.devices_found

# Function for scanning for devices and returning the list of Bluetooth Addresses
def create_and_return__bluetooth_scan__discovered_devices__specific_adapter(bluetooth_adapter=bluetooth_constants.ADAPTER_NAME):
    if dbg != 0:
        print("[*] Scanning for Discoverable Bluetooth Devices")
    ## Step 1:  Create an adapter object the user can perform scans with
    # Create an adapter class object
    test_adapter = system_dbus__bluez_adapter(bluetooth_adapter)
    
    ## Step 2:  Have a method (of the adapter) that can enable + filter device scanning & perform the scan
    
    # Set a custom discovery filter                                                                             (Step 2i)
    custom_discovery_filter_test = {'Transport': 'auto'}
    test_adapter.set_discovery_filter(custom_discovery_filter_test)
    
    # Scan for devices via the adapter class object                                                             (Step 2ii)
    #test_adapter.run_scan()
    test_adapter.run_scan__timed()
    # Note: Changed above to run a FIVE SECOND scan by default
    
    # Show the device that were found using the adapter class objcet run_scan() method call                     (Step 2iii)
    #test_adapter.devices_found
    if dbg != 0:
        print("[+] List of Devices Found:\t{0}".format(test_adapter.devices_found))
    return test_adapter.devices_found

# Function for scanning for a specific device for a maximum number of times
def search_for_device(target_device, max_searches=3):
    # Variables for Tracking
    device_found_flag = False
    loop_iteration = 0

    # Search for the target device based on the max number of searches
    while device_found_flag == False and loop_iteration < max_searches:
        ## Initial Scanning of the device
        # Performing a scan for general devices; main scan for devices to populate the linux D-Bus
        discovered_devices = create_and_return__bluetooth_scan__discovered_devices()
        # Iterate through the tuples of discovered devices
        for discovered_device in discovered_devices:
            # Sanity check for having found the target device
            if target_device not in discovered_device:
                out_log_string = "[!] Unable to find device [ {0} ]".format(target_device)
                print_and_log(out_log_string)
                #return None
            else:
                out_log_string = "[+] Able to find device [ {0} ]".format(target_device)
                print_and_log(out_log_string)
                device_found_flag = True
        # Increase the interation count
        loop_iteration += 1

    if dbg != 1:
        output_log_string = "[*] Discovered Devices:\t[ {0} ]\t\t-\t\tFound Target Device [ {1} ] is [ {2} ]".format(discovered_devices, target_device, device_found_flag)
        print_and_log(output_log_string)
    # Return findings
    return device_found_flag, discovered_devices


## Check and Confirm Functions

# Function for Determining if the desired_bluetooth_device is in the provided list of devices_found
def check_and_confirm__device_found_from_scan(bluetooth_device_address, devices_found):
    #print("[*]")
    found_device_flag = False
    if bluetooth_device_address in devices_found:
        print("[+] Recognized the BLE Light Address [ {0} ] in the devices list [ {1} ]".format(bluetooth_device_address, devices_found))
        found_device_flag = True
    
    if not found_device_flag:
        print("[-] Did not find the inteded BLE Device.... Exiting")
        return found_device_flag
    else:
        print("[+] Found the intended device [ {0} ]".format(bluetooth_device_address))
    #print("[+]")
    return found_device_flag

## Run and Detect Functions

# Function for Performing Bluetooth Device Scanning (type provided by user)
#   - Nota Bene: The discovery filter can be 'auto', 'bredr', OR 'le'
def run_and_detect__bluetooth_devices__with_provided_filter(discovery_filter={'Transport': 'auto'}):
    print("[*] Starting Discovery Process")
    # Create the Object for the Adapter Interface
    adapter_object, adapter_interface, adapter_properties = create_and_return__system_adapter_dbus_elements()
    
    # Configure the Scanning for Devices
    adapter_interface.SetDiscoveryFilter(discovery_filter)
    adapter_interface.StartDiscovery()
    main_loop = GLib.MainLoop()

    # Begin the Scanning for Devices
    try:
        print("\t!\t-\tPress Ctrl-C to end scan\n")
        main_loop.run()
    except KeyboardInterrupt:
        main_loop.quit()
    
    # Stop the Discovery Process
    adapter_interface.StopDiscovery()
    print("[+] Completed Discovery")

## [x] Add "Auto-termination" of the script after some period of time (to augment usability with automated scripts; lack of requirement for human interaction)
# Function for Performing Bluetooth Device Scanning (type provided by user) as well as a default (or user provided) timeout
#   - Nota Bene: The discovery filter can be 'auto', 'bredr', OR 'le'
#   - Default timer set to 5000 milliseconds (i.e. 5 seconds)
def run_and_detect__bluetooth_devices__with_provided_filter__with_timeout(discovery_filter={'Transport': 'auto'}, timeout_ms=5000):
    print("[*] Starting Discovery Process with Timing")

    # Local varaibles for setup and tear down of GLib MainLoop scanning
    #main_loop, timer_id = None, None        # Note: Getting a "race condition" with the timer_id since below it is being passed to the function and being generated by the creation of the timeout_add() function

    ## Internal Functions for configuring timeout to the GLib MainLoop()

    # Function for setting a timeout time for device discovery
    #   - Used as a callback function for the code (automatically on the backend?)
    def discovery_timeout(adapter_interface, mainloop, timer_id):
        #global adapter_interface
        #global mainloop
        #global timer_id
        # To get the .source_remove() call to work one has to (1) track the timer_id as a class property (or global) variable, (2) Add the newly created 'timer_id' to this variable, (3) when the callback function gets called, pull the information from the Class object
        GLib.source_remove(timer_id)
        mainloop.quit()
        adapter_interface.StopDiscovery()
        '''
        ## Note: Below is only needed when signal receivers are required WITH the device scanning
        bus = dbus.SystemBus()
        # Removing the signal receiver to the System Bus
        bus.remove_signal_receiver(interfaces_added,"InterfacesAdded")
        # Removing another signal receiver to the System Bus
        bus.remove_signal_receiver(interfaces_added,"InterfacesRemoved")
        # Removing another signal receiver to the System Bus
        bus.remove_signal_receiver(properties_changed,"PropertiesChanged")
        # List the devices that were found
        list_devices_found()
        '''
        return True
    # Note: Might need to use the '*args' debugging to determine how/what information is passed to the above function

    ## Setup the Device Discovery
    # Create the Object for the Adapter Interface;
    #   [ ] Re-create these adpaters using the adpter Class Object
    adapter_object, adapter_interface, adapter_properties = create_and_return__system_adapter_dbus_elements()
    
    # Configure the Scanning for Devices
    adapter_interface.SetDiscoveryFilter(discovery_filter)
    adapter_interface.StartDiscovery()
    main_loop = GLib.MainLoop()

    # Adding a timeout to the GLib MainLoop
    #   - Note: According to documentation for the GLib timeout_add() function definition one can add an gpointer of data to pass to the callback function
    #       - URL:      https://docs.gtk.org/glib/func.timeout_add.html
    timer_id = GLib.timeout_add(timeout_ms, discovery_timeout, adapter_interface, main_loop, timer_id)
    # According to the documentation ANY NUMBER of additional variables can be passed back to the callback function by listing them AFTER the callback function
    #   - URL:      https://www.manpagez.com/html/pygobject/pygobject-2.28.3/glib-functions.php#function-glib--timeout-add

    # Begin the Scanning for Devices
    try:
        print("\t!\t-\tPress Ctrl-C to end scan\n")
        main_loop.run()
    except KeyboardInterrupt:
        main_loop.quit()
    
    # Stop the Discovery Process
    adapter_interface.StopDiscovery()
    print("[+] Completed Discovery")

# Function for Performing Bluetooth Device Scanning (bluetooth adapter and type provided by user) as well as a default (or user provided) timeout
#   - Nota Bene: The discovery filter can be 'auto', 'bredr', OR 'le'
#   - Default timer set to 5000 milliseconds (i.e. 5 seconds)
def run_and_detect__bluetooth_devices__with_provided_adapter_and_provided_filter__with_timeout(bluetooth_adapter=bluetooth_constants.ADAPTER_NAME, discovery_filter={'Transport': 'auto'}, timeout_ms=5000):
    print("[*] Starting Discovery Process with Timing")

    # Local varaibles for setup and tear down of GLib MainLoop scanning
    #main_loop, timer_id = None, None        # Note: Getting a "race condition" with the timer_id since below it is being passed to the function and being generated by the creation of the timeout_add() function

    ## Internal Functions for configuring timeout to the GLib MainLoop()

    # Function for setting a timeout time for device discovery
    #   - Used as a callback function for the code (automatically on the backend?)
    def discovery_timeout(adapter_interface, mainloop, timer_id):
        # To get the .source_remove() call to work one has to (1) track the timer_id as a class property (or global) variable, (2) Add the newly created 'timer_id' to this variable, (3) when the callback function gets called, pull the information from the Class object
        GLib.source_remove(timer_id)
        mainloop.quit()
        adapter_interface.StopDiscovery()
        return True
    # Note: Might need to use the '*args' debugging to determine how/what information is passed to the above function

    ## Setup the Device Discovery
    # Create the Object for the Adapter Interface;
    #   [ ] Re-create these adpaters using the adpter Class Object
    #adapter_object, adapter_interface, adapter_properties = create_and_return__system_adapter_dbus_elements()
    adapter_object, adapter_interface, adapter_properties = create_and_return__system_adapter_dbus_elements__specific_hci(bluetooth_adapter)
    
    # Configure the Scanning for Devices
    adapter_interface.SetDiscoveryFilter(discovery_filter)
    adapter_interface.StartDiscovery()
    main_loop = GLib.MainLoop()

    # Adding a timeout to the GLib MainLoop
    #   - Note: According to documentation for the GLib timeout_add() function definition one can add an gpointer of data to pass to the callback function
    #       - URL:      https://docs.gtk.org/glib/func.timeout_add.html
    timer_id = GLib.timeout_add(timeout_ms, discovery_timeout, adapter_interface, main_loop, timer_id)
    # According to the documentation ANY NUMBER of additional variables can be passed back to the callback function by listing them AFTER the callback function
    #   - URL:      https://www.manpagez.com/html/pygobject/pygobject-2.28.3/glib-functions.php#function-glib--timeout-add

    # Begin the Scanning for Devices
    try:
        print("\t!\t-\tPress Ctrl-C to end scan\n")
        main_loop.run()
    except KeyboardInterrupt:
        main_loop.quit()
    
    # Stop the Discovery Process
    adapter_interface.StopDiscovery()
    print("[+] Completed Discovery")

## User Interaction Functions

# Function for Asking the User to Pick a Bluetooth Low Energy Device in Range and Return its Address
def user_interaction__find_and_return__pick_device():
    print("[*] Searching for Discoverable Devices")
    try:
        discovered_devices = create_and_return__bluetooth_scan__discovered_devices()
    except dbus.exceptions.DBusException:
        raise dbus.exceptions.DBusException
    print("The following devices have been discovered:")
    itemNumber = 1
    for device_address in discovered_devices:
        print("\t{0}:\t\t\t{1}".format(itemNumber, device_address))
        itemNumber += 1
    user_selection = int(input("Please select the above device to return: "))
    user_input_check = False
    while not user_input_check:
        user_input_check = check_and_validate__user_selection(user_selection, itemNumber)
    if dbg != 0:
        print("[!] User has selected device [ {0} ]".format(user_selection))
    #user_selected_device = discovered_devices[int(user_selection)-1]
    user_selected_device = discovered_devices[int(user_input_check)-1]
    return user_selected_device

# Function for Asking the User to Pick a Bluetooth Low Energy Device in Range and Return its Address
def user_interaction__find_and_return__pick_device__specific_adapter(bluetooth_adapter=bluetooth_constants.ADAPTER_NAME):
    print("[*] Searching for Discoverable Devices")
    discovered_devices = create_and_return__bluetooth_scan__discovered_devices__specific_adapter(bluetooth_adapter)
    print("The following devices have been discovered:")
    itemNumber = 1
    for device_address in discovered_devices:
        print("\t{0}:\t\t\t{1}".format(itemNumber, device_address))
        itemNumber += 1
    user_selection = int(input("Please select the above device to return: "))
    user_input_check = False
    while not user_input_check:
        user_input_check = check_and_validate__user_selection(user_selection, itemNumber)
    if dbg != 0:
        print("[!] User has selected device [ {0} ]".format(user_selection))
    #user_selected_device = discovered_devices[int(user_selection)-1]
    user_selected_device = discovered_devices[int(user_input_check)-1]
    return user_selected_device

# Function for testing BLE CTF using D-Bus as a main function
def ble_ctf__main():
    print("[*] Start BLE CTF Main()")

    print("[*] Running Python DBus Interface...")
    # Setup adapter interface, mainloop, timer_id, and other properties
    #adapter_interface = None
    #mainloop = None
    #timer_id = None     # Keep as 'None'..... How does this work for the example script?
    # NOTE: The above three variables may not even be needed
    # Device findings and tracking variables
    devices = {}
    managed_objects_found = 0
    ble_ctf_device = None
    #print("[*] Testing Discovery Scanning")
    #bluetooth_dbus__discovery_scan(devices, managed_objects_found)
    # Testing structure and class building
    print("[*] Creating a BLE Device Manager object and scan for devices")
    adapter_name = bluetooth_constants.ADAPTER_NAME
    device_manager = bluetooth__le__deviceManager(adapter_name)
    # Start discovery scan
    device_manager.start_discovery()
    # Run the loop
    device_manager.run()
    ## TODO: Fix this issue with the run() getting stuck....
    # Stop the loop
    device_manager.stop()
    # Turn off discovery
    device_manager.stop_discovery()
    # Print the results
    device_list = device_manager.devices()
    for device in device_list:
        print("\tDevice MAC:\t{0}".format(device.mac_address))
        if 'cc' in device.mac_address:
            ble_ctf_device = device         # Grab the BLE CTF Device Object
    # At this point we have a list of device objects and a separate one for the BLE CTF
    ble_ctf_device._device_path
    ble_ctf_device.manager.adapter_name
    print("[+] Completed Running the Python DBus Interface")

    print("[+] Finished BLE CTF Main()")

### Code for Proof-of-Concept for Enumerating BLE Devices
def proof_of_concept__ble_device_enumeration():
    print("[*] Proof-of-Concept Code\t-\tEnumeration of a known BLE Device")
    ## Debugging Space - Immediately Run and Available for -i run of python3
    system_bus = dbus.SystemBus()
    
    # Made a device_manager object that can be used to Connect/Disconnect from a given device
    ble_ctf_device_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE + bluetooth_constants.ADAPTER_NAME + "/dev_CC_50_E3_B6_BC_A6")
    device_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE + bluetooth_constants.ADAPTER_NAME + "/dev_F0_98_7D_0A_05_07")
    
    device_manager = dbus.Interface(device_object, bluetooth_constants.DEVICE_INTERFACE)        # Similar to structure seen in busctl to access the Device1 profile
    device_properties = dbus.Interface(device_object, bluetooth_constants.DBUS_PROPERTIES)
    
    # Testing
    #device_manager.object_path
    #device_manager.Connect()
    #device_manager.Disconnect()
    
    ## Creating an adapter object, interface, and properties and using it directly
    adapter_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE + bluetooth_constants.ADAPTER_NAME)
    adapter_interface = dbus.Interface(adapter_object, bluetooth_constants.ADAPTER_INTERFACE)
    adapter_properties = dbus.Interface(adapter_object, bluetooth_constants.DBUS_PROPERTIES)
    
    adapter_properties.GetAll(bluetooth_constants.ADAPTER_INTERFACE)    # WORKS - Gets ALL the property entries
    adapter_properties.Get(bluetooth_constants.ADAPTER_INTERFACE, 'Discoverable')       # WORKS - Gets one specific entry
    bluetooth_utils.dbus_to_python(adapter_properties.Get(bluetooth_constants.ADAPTER_INTERFACE, 'Discoverable'))   # WORKS - Grabs and converts to python from dbus
    
    discovery_filter = {'Transport': 'le'}
    adapter_interface.SetDiscoveryFilter(discovery_filter)
    adapter_interface.StartDiscovery()
    main_loop = GLib.MainLoop()
    try:
        main_loop.run()
    except KeyboardInterrupt:
        main_loop.quit()
    adapter_interface.StopDiscovery()
    
    # Note: Need an Object Manager to read out the devices that have been found
    object_manager = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, "/")
    object_manager_interface = dbus.Interface(object_manager, bluetooth_constants.DBUS_OM_IFACE)
    
    managed_objects_items = object_manager_interface.GetManagedObjects().items()      # Note: Should contain list of found devices from Discovery()
    managed_objects = object_manager_interface.GetManagedObjects()
    # Enumerate through the managed objects looking for Device1 profile interfaces
    for path, ifaces in managed_objects.items():
        for iface_name in ifaces:
            if iface_name == bluetooth_constants.DEVICE_INTERFACE:
                print("---------------------------\nDevice Path:\t\t{0}".format(path))
                item_device_properties = ifaces[bluetooth_constants.DEVICE_INTERFACE]
                if 'Address' in item_device_properties:
                    print("\tDevice BT ADDR:\t{0}".format(bluetooth_utils.dbus_to_python(item_device_properties['Address'])))
                print("\tDevice Properties:\t\t{0}".format(item_device_properties))
                print("---------------------------")
    ## Note: Did not see the BLE CTF in this set.... perhaps need to run the mainloop for much longer?
    #   - TODO: Add in the time-limit to scanning; will require the creation of a Class.....
    
    ## Connecting to the 'Light Orb'
    device_path = bluetooth_utils.device_address_to_path("F0:98:7D:0A:05:07", bluetooth_constants.BLUEZ_NAMESPACE + bluetooth_constants.ADAPTER_NAME)
    device_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, device_path)
    device_interface = dbus.Interface(device_object, bluetooth_constants.DEVICE_INTERFACE)
    # Now connect
    device_interface.Connect()
    
    # Check the connection
    device_properties = dbus.Interface(device_object, bluetooth_constants.DBUS_PROPERTIES)
    device_properties.Get(bluetooth_constants.DEVICE_INTERFACE, 'Connected')        # WORKS
    bluetooth_utils.dbus_to_python(device_properties.Get(bluetooth_constants.DEVICE_INTERFACE, 'Connected'))    # WORKS
    
    # Grab array of properties
    device_properties_array = bluetooth_utils.dbus_to_python(device_properties.GetAll(bluetooth_constants.DEVICE_INTERFACE))
    for device_prop in device_properties_array:
        print("Device Property:\t\t{0}\n\tValue:\t\t{1}".format(bluetooth_utils.dbus_to_python(device_prop), bluetooth_utils.dbus_to_python(device_properties_array[device_prop])))
        if device_prop == 'UUIDs':
            for uuid_entry in bluetooth_utils.dbus_to_python(device_properties_array[device_prop]):
                print("\t\tUUID:\t\t{0}\n\t\tValue:\t\t{1}".format(uuid_entry, bluetooth_utils.get_name_from_uuid(uuid_entry)))
    
    ## Note: At this point one can enumerate the Device1 properties.... but how to get from here down to the GATTService1 profiles
    #   - The UUIDs in the Device1 'UUIDs' property correspond to the service UUIDs
    device_introspection = device_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
    device_tree = ET.fromstring(device_introspection)
    device_services_list = []
    
    # Loop through the 'device_tree' eTree and collect the child.attrib that are 'node's 'name' dictionary value to the 'device_services_list' list
    for child in device_tree:
        if dbg != 1:        # ~!~
            print("Child Tag:\t\t{0}\n\tAttribs:\t\t{1}".format(child.tag, child.attrib))
        # Check for the expected 'service' information
        if child.tag == 'node' and 'service' in child.attrib['name']:
            print("\tAttrib:\t{0}\n\t\tValue:\t{1}".format(child.attrib, child.attrib['name']))
            device_services_list.append(child.attrib['name'])
    
    # Now take the 'device_services_list' and use that in combination with the current 'device_path' (e.g. /org/bluez/hci0/dev_F0_98_7D_0A_05_07) to read through each service and extract that specific service's Introspection table (? equiv 'busctl''s introspect command)
    
    # Enumerating the GattService1 interfaces that came from the previously obtained list
    for service_name in device_services_list:
        service_path = device_path + "/" + service_name
        service_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, service_path)
        service_interface = dbus.Interface(service_object, bluetooth_constants.GATT_SERVICE_INTERFACE)
        service_properties = dbus.Interface(service_object, bluetooth_constants.DBUS_PROPERTIES)
        if dbg != 1:        # ~!~
            print("Service Information for [ {0} ]".format(service_path))
        # Request the GetAll() method from Properties of the Service Interface
        service_properties_array = bluetooth_utils.dbus_to_python(service_properties.GetAll(bluetooth_constants.GATT_SERVICE_INTERFACE))
        # Enumerate through the properties of the service interface
        for service_prop in service_properties_array:
            if dbg != 1:    # ~!~
                print("Service Property:\t\t{0}\n\tValue:\t\t{1}".format(bluetooth_utils.dbus_to_python(service_prop), bluetooth_utils.dbus_to_python(service_properties_array[service_prop])))
        # Introspection of another level down into the GattService1 - Proven via examination using 'busctl'
        service_introspection = service_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
        service_tree = ET.fromstring(service_introspection)
        device_service_characters_list = []
        # Enumerate through the properties of the GattService1 Interface
        for child in service_tree:
            if dbg != 1:    # ~!~
                print("\tChild Tag:\t\t{0}\n\t\tAttribs:\t{1}".format(child.tag, child.attrib))
            if child.tag == 'node' and 'char' in child.attrib['name']:
                if dbg != 1:    # ~!~
                    print("\t\tAttrib:\t{0}\n\t\tValue:\t{1}".format(child.attrib, child.attrib['name']))
                device_service_characters_list.append(child.attrib['name'])
        # Output the list of collected Characteristics
        if dbg != 1:
            print("\t\tCharactersitics List:\t\t{0}".format(device_service_characters_list))
        if dbg != 1:        # ~!~
            print("------------------------------------")
    
    ## Can introspect another level on the GattService1 -   Proven via examination using 'busctl'
    introspection_service = service_interface.Introspect(dbus_interface="org.freedesktop.DBus.Introspectable")
    tree_service = ET.fromstring(introspection_service)
    for child in tree_service:
        print("Child Tag:\t\t{0}\n\tAttribs:\t{1}".format(child.tag, child.attrib))
    
    ## Examine one of the characterisc descriptors
    
    # From the above, can get the new character name
    
    character_path = service_path + "/" + device_service_characters_list[0]
    #character_path
    character_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, character_path)
    character_interface = dbus.Interface(character_object, bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE)
    character_properties = dbus.Interface(character_object, bluetooth_constants.DBUS_PROPERTIES)
    print("Characteristic Information for [ {0} ]".format(character_path))
    character_properties_array = bluetooth_utils.dbus_to_python(character_properties.GetAll(bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE))
    for char_prop in character_properties_array:
        print("Characteristic Property:\t\t{0}\n\tValue:\t\t{1}".format(bluetooth_utils.dbus_to_python(char_prop), bluetooth_utils.dbus_to_python(character_properties_array[char_prop])))
    
    # Create the character intropsection using the character interface
    character_introspection = character_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
    character_tree = ET.fromstring(character_introspection)
    for child in character_tree:
        print("Child Tag:\t\t{0}\n\tAttribs:\t{1}".format(child.tag, child.attrib))
    
    ## One more level of recursive introspection left
    
    # Create the descriptor_path from the characteristic last in variable memory
    device_services_characters_descriptor_list = enumerate_and_return__introspection_interface_tree(character_introspection, 'desc')
    descriptor_path = character_path + "/" + device_services_characters_descriptor_list[0]
    descriptor_object = system_bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, descriptor_path)
    descriptor_interface = dbus.Interface(descriptor_object, bluetooth_constants.GATT_DESCRIPTOR_INTERFACE)
    descriptor_properties = dbus.Interface(descriptor_object, bluetooth_constants.DBUS_PROPERTIES)
    print("Descriptor Information for [ {0} ]".format(descriptor_path))
    descriptor_properties_array = bluetooth_utils.dbus_to_python(descriptor_properties.GetAll(bluetooth_constants.GATT_DESCRIPTOR_INTERFACE))
    for desc_prop in descriptor_properties_array:
        print("Descriptor Property:\t\t{0}\n\tValue:\t\t{1}".format(bluetooth_utils.dbus_to_python(desc_prop), bluetooth_utils.dbus_to_python(descriptor_properties_array[desc_prop])))
    print("[+] Completed Proof-of-Concept Code\t-\tEnumeration of a known BLE Device")

# Check if running in debug mode; if yes, run the PoC
if dbg != 0:
    proof_of_concept__ble_device_enumeration()

### Code for identifying a given BLE device, creating the adapters to interact with the device, and a brute-force enumeration of the BLE device
# Function for a complete device enumeration test
def full_device_enumeration_test():
    print("===============================================================================================\n\tCOMPLETE DEVICE ENUMERATION TEST\n===============================================================================================")
    
    ## First Scan for devices
    # Create the system bus interface
    system_bus = dbus.SystemBus()
    
    # Setup variables for scanning BLE
    ble_ctf__address = "CC:50:E3:B6:BC:A6"
    ble_light__address = "F0:98:7D:0A:05:07"
    discovery_filter = {'Transport': 'le'}      # Note: This sets up discovery filters for ONLY BLE devices
    bluetooth_target_address = ble_light__address
    
    # Scan for devices 
    run_and_detect__bluetooth_devices__with_provided_filter(discovery_filter)
    
    # Find and return the list of devices that were found from discovery
    devices_found = create_and_return__discovered_managed_objects()
    print("Devices Found:\t\t[ {0} ]".format(devices_found))
    
    # Check that the desired device was found from the scan
    if not check_and_confirm__device_found_from_scan(bluetooth_target_address, devices_found):
        print("[-] Failure to find the desired device [ {0} ]".format(bluetooth_target_address))
        exit        # TODO: Change to break when this is placed within a function
    
    ## Creating the Device Object Path, Object, Interface, and Properties
    # Find and return information relating to the Device Interface associated with the chosen Bluetooth device
    device_object, device_interface, device_properties, device_introspection, device_services_list = create_and_return__device_dbus_elements(bluetooth_target_address)
    
    ## Begin searching through the Device Services found and run the brute force recursive enumeration
    device_path = bluetooth_utils.device_address_to_path(bluetooth_target_address, bluetooth_constants.BLUEZ_NAMESPACE + bluetooth_constants.ADAPTER_NAME)
    # Enumerate through the device's services, characteristics, and descriptors
    enumerate__gatt__brute_force_enumeration(device_path, device_services_list)
    
    print("===============================================================================================\n\t[+] COMPLETED DEVICE ENUMERATION TEST [+]\n===============================================================================================")

# Running a full device enumeration test
#full_device_enumeration_test()

# Function for Running Full Enumeration of the BLE CTF Device
def ble_ctf__scan_and_enumeration():
    print("===============================================================================================\n\tCOMPLETE BLE CTF DEVICE ENUMERATION\n===============================================================================================")
    ## Code - Connect to BLE CTF device and resolve the services
    ble_ctf = system_dbus__bluez_device__low_energy('CC:50:E3:B6:BC:A6')
    ble_ctf.Connect()
    print("[*] Waiting for device [ {0} ] services to be resolved".format(ble_ctf.device_address), end='')
    # Hang and wait to make sure that the services are resolved
    while not ble_ctf.find_and_get__device_property("ServicesResolved"):
        time.sleep(0.5)      # Sleep to give time for Services to Resolve
        print(".", end='')
    print("\n[+] ble_ctf__scan_and_enumeration::Device services resolved!")
    ble_ctf.identify_and_set__device_properties(ble_ctf.find_and_get__all_device_properties())
    ble_services_list = ble_ctf.find_and_get__device_introspection__services()
    # JSON for tracking the various services, characteristics, and descriptors from the GATT
    ble_ctf__mapping = { "Services" : {} }
    '''
    Map of JSON Mapping:
        BDADDR : {
            Service001 : {
                Characteristic001 : {
                    Descriptor001 : {
                        descriptor_info_key : descriptor_info_value
                        },
                    characteristics_info_key : characteristic_info_value
                    },
                service_info_key : service_info_value
            }
    
    
    '''
    ## Code - Complete Enumeration through a BLE Device's Services, Characteristics, and Descriptors
    # Now do an iteration through the 'Services' to enumerate all the characteristics
    for ble_service in ble_services_list:
        # Internal JSON mapping
        device__service__map = create_and_return__gatt__service_json()
        if dbg != 0:    # ~!~
            print("[*] BLE Service\t-\t{0}".format(ble_service))
        # Create the characteristic variables that we will work with
        service_path, service_object, service_interface, service_properties, service_introspection = ble_ctf.create_and_return__service__gatt_inspection_set(ble_service)
        # Generate the sub-list of Service Characteristics
        service_characteristics_list = ble_ctf.find_and_get__device__etree_details(service_introspection, 'char')       # Nota Bene: This only does the conversion of the eTree into something meaningful that can be enumerated for the Characteristic names; SAME THING as the line below
        #ble_chars_list = ble_ctf.find_and_get__device_introspection__characteristics(service_path, service_characteristics_list)
        # Now do an iteration through the 'Characteristics' of the current Service
        for ble_service_characteristic in service_characteristics_list:
            # Internal JSON mapping
            device__characteristic__map = create_and_return__gatt__characteristic_json()
            # Generate the Interfaces for each Characteristic
            characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = ble_ctf.create_and_return__characteristic__gatt_inspection_set(service_path, ble_service_characteristic)
            # Check the Read/Write Flag(s) for the Characteristic interface
            characteristic_flags = ble_ctf.find_and_get__characteristic_property(characteristic_properties, 'Flags')
            if dbg != 0:    # ~!~
                #print("[*] Characteristic [ {0} ] Flags:\t{1}".format(ble_ctf.find_and_get__characteristic_property(characteristic_properties, 'Service'), characteristic_flags))
                print("[*] Characteristic [ {0} ] Flags:\t{1}".format(characteristic_path, characteristic_flags))
            ## Attempt to Read the value from the Characteristic (NOTE: AFTER checking if there is a read/write flag; TODO: Use the results from the ReadValue() function call to create the input for the WriteValue() function call
            '''
            # Attempt to Read
            try:
                characteristic_interface.ReadValue({})                                  # Note: Form is 'array{byte} ReadValue(dict options)'
                # Get Error:    org.bluez.Error.NotPermitted: Read not permitted
            except Exception as e:
                ble_ctf.understand_and_handle__dbus_errors(e)
            # Attempt to Write
            try:
                characteristic_interface.WriteValue("AAAAAAAA", {})                     # Note: Form is 'void WriteValue(array{byte} value, dict options)'
                # Get Error:    ERROR:dbus.connection:Unable to set arguments ('AAAAAAAA', {}) according to signature 'aya{sv}': <class 'TypeError'>: an integer is required (got type str)
            except Exception as e:
                ble_ctf.understand_and_handle__dbus_errors(e)
            '''
            if dbg != 0:
                print("[!] Pre-Read Test:\tCharacteristic Value:\t-\t{0}".format(ble_ctf.find_and_get__characteristic_property(characteristic_properties, 'Value')))
            ## Check if there is a 'read' in the flags
            if 'read' in characteristic_flags or 'write' in characteristic_flags:      # NOTE: Even if 'write' is the only thing present, it can have a value name
                if dbg != 0:
                    print("[*] Attempt to read from Characteristic [ {0} ] due to Flags [ {1} ]".format(characteristic_path, characteristic_flags))
                try:
                    characteristic_interface.ReadValue({})
                    if dbg != 0:
                        print("[+] Able to perform ReadValue()\t-\tCharacteristic")
                except Exception as e:
                    if dbg != 0:
                        print("[-] Unable to perform ReadValue()\t-\tCharacteristic")
                    ble_ctf.understand_and_handle__dbus_errors(e)
            if dbg != 0:
                print("[!] Post-Read Test:\tCharacteristic Value:\t-\t{0}".format(ble_ctf.find_and_get__characteristic_property(characteristic_properties, 'Value')))
            characteristic_value__hex_array = ble_ctf.find_and_get__characteristic_property(characteristic_properties, 'Value')
            try:
                characteristic_value__ascii_string = convert__hex_to_ascii(characteristic_value__hex_array)
            except Exception as e:
                ble_ctf.understand_and_handle__dbus_errors(e)
                characteristic_value__ascii_string = None
            if dbg != 0:
                print("\tCharacteristic Value:\t{0}\n\t\tRaw:\t{1}".format(characteristic_value__ascii_string, characteristic_value__hex_array))
                print("\tValue\t-\t{0}".format(characteristic_value__ascii_string))
                print("\tHandle\t-\t{0}".format(ble_ctf.find_and_get__characteristic_property(characteristic_properties, 'Handle')))
                print("\tUUID\t-\t{0}".format(ble_ctf.find_and_get__characteristic_property(characteristic_properties, 'UUID')))
            # Setting the variables to be added into the JSON map for the device
            characteristic_uuid = ble_ctf.find_and_get__characteristic_property(characteristic_properties, 'UUID')
            #characteristic_value = characteristic_value__ascii_string
            characteristic_value = characteristic_value__hex_array
            characteristic_handle = ble_ctf.find_and_get__characteristic_property(characteristic_properties, 'Handle')
            ## Move onto the Descriptors
            # Generate the sub-list of Characteristic Descriptors
            characteristic_descriptors_list = ble_ctf.find_and_get__device__etree_details(characteristic_introspection, 'desc')
            # Now do an iteration through the 'Descriptors' of the current Characteristic
            for ble_characteristic_descriptor in characteristic_descriptors_list:
                # Internal JSON mapping
                device__descriptor__map = create_and_return__gatt__descriptor_json()
                # Create the descriptor variables that we will work with
                descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = ble_ctf.create_and_return__descriptor__gatt_inspection_set(characteristic_path, ble_characteristic_descriptor)
                # Check the Read/Write Flag(s) for the Descriptor interface
                descriptor_flags = ble_ctf.find_and_get__descriptor_property(descriptor_properties, 'Flags')        # Note: Descriptor may NOT have a Flags property
                if dbg != 0:    # ~!~
                    print("[*] Descriptor [ {0} ] Flags:\t{1}".format(descriptor_path, descriptor_flags))
                ## Attempt to Read/Write the value from the Descriptor; Note: Same structure as for Characteristics
                '''
                # Attempt Read
                try:
                    descriptor_interface.ReadValue({})
                except Exception as e:
                    ble_ctf.understand_and_handle__dbus_errors(e)
                # Attempt Write
                try:
                    descriptor_interface.WriteValue("CCCCCCCC", {})
                except Exception as e:
                    ble_ctf.understand_and_handle__dbus_errors(e)
                '''
                # Update the current descriptor map
                device__descriptor__map["Flags"] = descriptor_flags
                # Update to the characteristic map
                device__characteristic__map["Descriptors"][ble_characteristic_descriptor] = device__descriptor__map
            # Update the current characteristic map
            device__characteristic__map["UUID"] = characteristic_uuid
            device__characteristic__map["Value"] = characteristic_value
            device__characteristic__map["Handle"] = characteristic_handle
            device__characteristic__map["Flags"] = characteristic_flags
            # Update to the services map
            device__service__map["Characteristics"][ble_service_characteristic] = device__characteristic__map
        # Get the variables we are looking for
        service_uuid = ble_ctf.find_and_get__service_property(service_properties, 'UUID')
        # Update to the current service map
        device__service__map["UUID"] = service_uuid
        # Update to the device map
        ble_ctf__mapping["Services"][ble_service] = device__service__map

    ## Pretty print the BLE CTF device mapping
    print("JSON Print of the Enumeration")
    #print(ble_ctf__mapping)
    pretty_print__gatt__dive_json(ble_ctf, ble_ctf__mapping)
    print("===============================================================================================\n\t[+] COMPLETED BLE CTF DEVICE ENUMERATION [+]\n===============================================================================================")
    return ble_ctf, ble_ctf__mapping

# Function for Reading from a Provided Characteristic Flag
def ble_ctf__read_characteristic(characteristic_name, user_device, user_device__internals_map):
    # Create structures for reading characteristic
    detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
    #print("Detailed Char:\n{0}".format(detailed_characteristic))
    # First check if that characteristic allows for reading
    if "read" not in detailed_characteristic["Flags"]:
        if dbg != 0:
            print("[-] No 'read' capability with characteristic [ {0} ]".format(characteristic_name))
        else:
            read_characteristic__response_string = "[-] No 'read' capability with characteristic [ {0} ]".format(characteristic_name)
            logging__log_event(LOG__GENERAL, read_characteristic__response_string)
        return None
    characteristic_service_path = detailed_characteristic["Service"]
    #print("Characteristic Service Path:\t{0}".format(characteristic_service_path))
    characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
    # Grab the DBus Array (i.e. raw) data
    read_raw = user_device.read__device__characteristic__with_signature(characteristic_interface)
    # Convery DBus Array into an ASCii string
    read_value = user_device.dbus_read_value__to__ascii_string(read_raw)
    if isinstance(read_value, dbus.Array):
        if dbg != 0:
            print("\tCharacteristic Value (ASCii | Hex):\t{0}\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(read_value), user_device.dbus_read_value__to__hex_string(read_value)))
        else:
            read_characteristic__response_string = "\tCharacteristic Value (ASCii | Hex):\t{0}\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(read_value), user_device.dbus_read_value__to__hex_string(read_value))
            logging__log_event(LOG__GENERAL, read_characteristic__response_string)
    else:
        if dbg != 0:
            print("\tCharaceristic Value:\t{0}".format(read_value))
        else:
            read_characteristic__response_string = "\tCharaceristic Value:\t{0}".format(read_value)
            logging__log_event(LOG__GENERAL, read_characteristic__response_string)
    # Return the read value (??)
    return read_value

# Function for Writing to a Provided Characteristic Flag
def ble_ctf__write_characteristic(write_value, characteristic_name, user_device, user_device__internals_map):
    # Create structures for writing to characteristic
    detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
    # First check if that characteristic allows for writing
    if "write" not in detailed_characteristic["Flags"]:
        if dbg != 0:
            print("[-] No 'write' capability with characteristic [ {0} ]".format(characteristic_name))
        else:
            write_characteristic__response_string = "[-] No 'write' capability with characteristic [ {0} ]".format(characteristic_name)
            logging__log_event(LOG__GENERAL, write_characteristic__response_string)
        return None
    characteristic_service_path = detailed_characteristic["Service"]
    characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
    #write_value = input("What should be written to the Characteristic: ")
    ## TODO: Have method of telling what the signature/info-type is expected by the Write       <---- DETERMINE WHICH ONE GIVES THE FLAG!
    #user_device.write__device__characteristic(characteristic_interface, write_value)
    # Function call to write the entire user input string to the characteristic
    #user_device.write__device__characteristic__one_byte_at_a_time(characteristic_interface, write_value)        # NOTE: This function call converts the value first to ASCii encoding and then passes the data
    # Trying a new Class write function
    user_device.write__device__characteristic(characteristic_interface, write_value)

# Structure for Holding the BLE CTF Flags
'''
        char0002        -       None
        char0029        -       Score:0 /20
        char002b        -       Write Flags Here
        char002d        -       d205303e099ceff44835
        char002f        -       MD5 of Device Name
        char0031        -       3873c0270763568cf7aa
        char0033        -       Write the ascii value "yo" he
        char0035        -       Write the hex value 0x07 here
        char0037        -       Write 0xC9 to handle 58
        char0039        -
        char003b        -       Brute force my value 00 to ff
        char003d        -       Read me 1000 times
        char003f        -       Listen to me for a single notification
        char0041        -       Listen to handle 0x0044 for a single indication
        char0043        -
        char0045        -       Listen to me for multi notifications
        char0047        -       Listen to handle 0x004a for multi indications
        char0049        -
        char004b        -       Connect with BT MAC address 11:22:33:44:55:66
        char004d        -       Set your connection MTU to 444
        char004f        -       Write+resp 'hello'  
        char0051        -       No notifications here! really?
        char0053        -       fbb966958f
        char0055        -       md5 of author's twitter handle
[+] Completed print of all characteristics and values
'''
# Note: For SOME reason the charactersitics are being read as -1 value to the HEX in the BLE CTF Material (i.e. using char002f instead ox 0x0030 for Flag #03)
#   - Characteristics with a Notify capability:     char003f, char0045, char0053, 
#   - Characteristics with an Indicate capability:  char0043, char0049
#   - Characteristics with an Extended-Properties:  char0053
BLE_CTF__CHARACTERISTIC_FLAGS = {
    "Flag-01":  "Given",
    "Flag-02":  "char002d",
    "Flag-03":  "char002f",
    "Flag-04":  "char0015",         # Note: This flag involves reading GATT Service extra device attributes
    "Flag-05":  "char0031",
    "Flag-06":  "char0033",
    "Flag-07":  "char0035",
    "Flag-08":  "char0037",
    "Flag-09":  "char003b",
    "Flag-10":  "char003d",
    "Flag-11":  "char003f",
    #"Flag-1x":  "char0039",         # Unsure of what this is; most likely nothing
    "Flag-12":  "char0041",
    "Flag-13":  "char0045",
    "Flag-14":  "char0047",
    "Flag-15":  "char004b",
    "Flag-16":  "char004d",
    "Flag-17":  "char0049",         # Note: This flag requires learning about write responses
    "Flag-18":  "char0051",
    "Flag-19":  "char0053",
    "Flag-20":  "char0055",
    "Flag-Score": "char0029",
    "Flag-Write": "char002b"
        }

# Function for extracting an array of UUIDs from an internals map
#   - Note: This does NOT work.... Since the Handle information is collected in some other manner....
def ble_ctf__extract_all_uuids(user_device__internals_map):
    # Create variable to hold the list of UUIDs
    uuids_array = []
    # Iterate through the user_device__internals_map to collect all the UUIDs present
    for service in user_device__internals_map["Services"]:
        if user_device__internals_map["Services"][service]["UUID"] not in uuids_array:
            uuids_array.append(user_device__internals_map["Services"][service]["UUID"])
        for characteristic in user_device__internals_map["Services"][service]["Characteristics"]:
            if user_device__internals_map["Services"][service]["Characteristics"][characteristic]["UUID"] not in uuids_array:
                uuids_array.append(user_device__internals_map["Services"][service]["Characteristics"][characteristic]["UUID"])
            for descriptor in user_device__internals_map["Services"][service]["Characteristics"][characteristic]["Descriptors"]:
                if user_device__internals_map["Services"][service]["Characteristics"][characteristic]["Descriptors"][descriptor]["UUID"] not in uuids_array:
                    uuids_array.append(user_device__internals_map["Services"][service]["Characteristics"][characteristic]["Descriptors"][descriptor]["UUID"])
    # Return the UUID array
    return uuids_array

# Function for Reading from the BLE CTF Score Flag
def ble_ctf__read_score_flag(user_device, user_device__internals_map):
    if dbg != 0:
        print("===============================================================================================\n\tREADING FROM BLE CTF SCORE FLAG\n===============================================================================================")
    else:
        ble_ctf__read_score__start_string = "===============================================================================================\n\tREADING FROM BLE CTF SCORE FLAG\n==============================================================================================="
        logging__log_event(LOG__GENERAL, ble_ctf__read_score__start_string)
    ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-Score"], user_device, user_device__internals_map)
    if dbg != 0:
        print("===============================================================================================\n\t[+] READ THE BLE CTF SCORE [+]\n===============================================================================================")
    else:
        ble_ctf__read_score__end_string = "===============================================================================================\n\t[+] READ THE BLE CTF SCORE [+]\n==============================================================================================="
        logging__log_event(LOG__GENERAL, ble_ctf__read_score__end_string)

# Function for Writing to the BLE CTF Flag Submission
def ble_ctf__write_flag(write_value, user_device, user_device__internals_map):
    ble_ctf__write_characteristic(write_value, BLE_CTF__CHARACTERISTIC_FLAGS["Flag-Write"], user_device, user_device__internals_map)

# Function for Performing the Entire BLE CTF
#   - Nota Bene:    ALL FLAGS are JUST the FIRST 20 CHARS of th values produced
#   [ ] Add logging to this function; with logging__log_event() function using LOG__GENERAL
def ble_ctf__perform_device_completion():
    print("===============================================================================================\n\tCOMPLETE BLE CTF DEVICE COMPLETION\n===============================================================================================")
    # TODO: Add in general scan to identify the BLE CTF device (on the DBus side)
    # Logging of BLE CTF Completion
    ble_ctf__start_string = "===============================================================================================\n\tCOMPLETE BLE CTF DEVICE COMPLETION\n===============================================================================================\n"
    logging__log_event(LOG__GENERAL, ble_ctf__start_string)
    ## Setup of variables and structures
    user_device, user_device__high_level_map = ble_ctf__scan_and_enumeration()
    user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
    print("[*] Generating all internal lists")
    services_list = user_device.find_and_return__internal_map__services_list(user_device__internals_map)
    characteristics_list = user_device.find_and_return__internal_map__characteristics_list(user_device__internals_map)
    descriptors_list = user_device.find_and_return__internal_map__descriptors_list(user_device__internals_map)
    print("[*] Checking the starting Score")
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    ## Flag #01
    # The first flag is a given "12345678901234567890"
    first_flag_value = "12345678901234567890"       # Note: Make sure to send the COMPLETE string; can be either are "12345678901234567890" OR str(12345678901234567890)
    ble_ctf__write_flag(first_flag_value, user_device, user_device__internals_map)
    ## Flag #02
    second_flag_value = ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-02"], user_device, user_device__internals_map)
    ble_ctf__write_flag(second_flag_value, user_device, user_device__internals_map)
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    ## Flag #03
    ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-03"], user_device, user_device__internals_map)
    # The above should print out that the next flag is the MD5 Hash of the Local Device Name
    # Note: This SHOULD be an MD5 hash of BLECTF, but due to artifact on the BLE CTF being train upon, the name is already set to the MD5 hash (i.e. 2b00042f7481c7b056c4b410d28f33cf); only need the first 20 chars
    third_flag_value = "2b00042f7481c7b056c4b410d28f33cf"
    ble_ctf__write_flag(third_flag_value, user_device, user_device__internals_map)
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    ## Flag #04
    # Note: This flag involves the reading of a GATT Service to provide the Generic Access -> Device Name field (UUID?)
    #   - HAVE to HARDCODE since the tools required to read from the Generic Access Profile (GAP) Service is IMPOSSIBLE with the current Bluez/DBus library (i.e. software OUTSIDE of Python)
    # Good resource for this part:      https://www.hackerdecabecera.com/2020/02/blectf-capture-flag-hardware-platafom.html
    '''
    Using the "gatttool" to interact directly with the BLE CTF Device
    gatttool -b CC:50:E3:B6:BC:A6 -I                                                        
    [CC:50:E3:B6:BC:A6][LE]> connect
    Attempting to connect to CC:50:E3:B6:BC:A6
    Connection successful
    [CC:50:E3:B6:BC:A6][LE]> primary
    attr handle: 0x0001, end grp handle: 0x0005 uuid: 00001801-0000-1000-8000-00805f9b34fb
    attr handle: 0x0014, end grp handle: 0x001c uuid: 00001800-0000-1000-8000-00805f9b34fb
    attr handle: 0x0028, end grp handle: 0xffff uuid: 000000ff-0000-1000-8000-00805f9b34fb
    [CC:50:E3:B6:BC:A6][LE]> char-desc 01 05
    handle: 0x0001, uuid: 00002800-0000-1000-8000-00805f9b34fb
    handle: 0x0002, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0003, uuid: 00002a05-0000-1000-8000-00805f9b34fb
    handle: 0x0004, uuid: 00002902-0000-1000-8000-00805f9b34fb
    [CC:50:E3:B6:BC:A6][LE]> char-desc 14 1c
    handle: 0x0014, uuid: 00002800-0000-1000-8000-00805f9b34fb
    handle: 0x0015, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0016, uuid: 00002a00-0000-1000-8000-00805f9b34fb
    handle: 0x0017, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0018, uuid: 00002a01-0000-1000-8000-00805f9b34fb
    handle: 0x0019, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x001a, uuid: 00002aa6-0000-1000-8000-00805f9b34fb
    [CC:50:E3:B6:BC:A6][LE]> char-read-hnd 0016
    Characteristic value/descriptor: 32 62 30 30 30 34 32 66 37 34 38 31 63 37 62 30 35 36 63 34 62 34 31 30 64 32 38 66 33 33 63 66

    echo "32 62 30 30 30 34 32 66 37 34 38 31 63 37 62 30 35 36 63 34 62 34 31 30 64 32 38 66 33 33 63 66" | xxd -r -p;printf '\n'                                                                        
    2b00042f7481c7b056c4b410d28f33cf            <--- Truncate THIS || Do below
    
    Note: Can only use the first 20 characters, therefore truncate and submit
    
    echo "32 62 30 30 30 34 32 66 37 34 38 31 63 37 62 30 35 36 63 34" | xxd -r -p;printf '\n' 
    2b00042f7481c7b056c4

    '''
    # Nota Bene:    Appears that neither of the above flags work.... Might be related to me messing up the BLE CTF attempting to write to the name/alias; Note: Might have messed up the GAP??
    #ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-04"], user_device, user_device__internals_map)        # Note: This causes an issue; due to trying to read a handle that is different??? (char0015)
    fourth_flag_value = user_device.device_name[:20]        # Only grab the first 20 characters of the device name
    ble_ctf__write_flag(fourth_flag_value, user_device, user_device__internals_map)
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    #print("[!] UNABLE TO PERFORM FLAG 04 AT THIS POINT IN TIME..... CONTINUE!")
    ## Flag #05
    # Note: This flag requests that the user write ANYTHING here; early framework ALWAYS attempts to write something to each writable S/C/D, therefore it is completed already
    ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-05"], user_device, user_device__internals_map)
    # Write anything to the Characteristic
    ble_ctf__write_characteristic("anything", BLE_CTF__CHARACTERISTIC_FLAGS["Flag-05"], user_device, user_device__internals_map)
    fifth_flag_value = ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-05"], user_device, user_device__internals_map)
    # Check the score
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    ## Flag 06
    # Read from the Flag to see what the step is
    ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-06"], user_device, user_device__internals_map)
    # Returns that one needs to write an ASCii "yo" to this flag
    ble_ctf__write_characteristic("yo", BLE_CTF__CHARACTERISTIC_FLAGS["Flag-06"], user_device, user_device__internals_map)
    sixth_flag_value = ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-06"], user_device, user_device__internals_map)
    # Write the flag value
    ble_ctf__write_flag(sixth_flag_value, user_device, user_device__internals_map)
    # Read new score
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    ## Flag #07
    # Read the flag
    ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-07"], user_device, user_device__internals_map)
    # Return tells us that the BLE CTF wants the hex value of "0x07" written to this flag
    #   - Note: Found that writing the INT value equivalent of 0x07 (i.e. d7) to this flag; below shows passing the hex representation of 0x07, which Python translates into an Int (as shown in logging)
    ble_ctf__write_characteristic(0x07, BLE_CTF__CHARACTERISTIC_FLAGS["Flag-07"], user_device, user_device__internals_map)
    seventh_flag_value = ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-07"], user_device, user_device__internals_map)
    # Read the score
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    ## Flag #08
    # Read the flag
    ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-08"], user_device, user_device__internals_map)
    # Nota Bene: The above flag returns information relating to the "Handle" value
    #   - This information is easily seen via gatttool, BUT CAN be calculated to determine the relative value compared to UUIDs
    '''
    Nota Bene: One has to use other tools (i.e. gatttool) to search for BLE Handles; limitation of the Bluez library

    char-desc 01 ff
    handle: 0x0001, uuid: 00002800-0000-1000-8000-00805f9b34fb
    handle: 0x0002, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0003, uuid: 00002a05-0000-1000-8000-00805f9b34fb
    handle: 0x0004, uuid: 00002902-0000-1000-8000-00805f9b34fb
    handle: 0x0014, uuid: 00002800-0000-1000-8000-00805f9b34fb
    handle: 0x0015, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0016, uuid: 00002a00-0000-1000-8000-00805f9b34fb
    handle: 0x0017, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0018, uuid: 00002a01-0000-1000-8000-00805f9b34fb
    handle: 0x0019, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x001a, uuid: 00002aa6-0000-1000-8000-00805f9b34fb
    handle: 0x0028, uuid: 00002800-0000-1000-8000-00805f9b34fb
    handle: 0x0029, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x002a, uuid: 0000ff01-0000-1000-8000-00805f9b34fb
    handle: 0x002b, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x002c, uuid: 0000ff02-0000-1000-8000-00805f9b34fb
    handle: 0x002d, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x002e, uuid: 0000ff03-0000-1000-8000-00805f9b34fb
    handle: 0x002f, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0030, uuid: 0000ff04-0000-1000-8000-00805f9b34fb
    handle: 0x0031, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0032, uuid: 0000ff05-0000-1000-8000-00805f9b34fb
    handle: 0x0033, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0034, uuid: 0000ff06-0000-1000-8000-00805f9b34fb
    handle: 0x0035, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0036, uuid: 0000ff07-0000-1000-8000-00805f9b34fb
    handle: 0x0037, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0038, uuid: 0000ff08-0000-1000-8000-00805f9b34fb
    handle: 0x0039, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x003a, uuid: 0000ff09-0000-1000-8000-00805f9b34fb
    handle: 0x003b, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x003c, uuid: 0000ff0a-0000-1000-8000-00805f9b34fb
    handle: 0x003d, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x003e, uuid: 0000ff0b-0000-1000-8000-00805f9b34fb
    handle: 0x003f, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0040, uuid: 0000ff0c-0000-1000-8000-00805f9b34fb
    handle: 0x0041, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0042, uuid: 0000ff0d-0000-1000-8000-00805f9b34fb
    handle: 0x0043, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0044, uuid: 0000ff0e-0000-1000-8000-00805f9b34fb
    handle: 0x0045, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0046, uuid: 0000ff0f-0000-1000-8000-00805f9b34fb
    handle: 0x0047, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0048, uuid: 0000ff10-0000-1000-8000-00805f9b34fb
    handle: 0x0049, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x004a, uuid: 0000ff11-0000-1000-8000-00805f9b34fb
    handle: 0x004b, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x004c, uuid: 0000ff12-0000-1000-8000-00805f9b34fb
    handle: 0x004d, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x004e, uuid: 0000ff13-0000-1000-8000-00805f9b34fb
    handle: 0x004f, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0050, uuid: 0000ff14-0000-1000-8000-00805f9b34fb
    handle: 0x0051, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0052, uuid: 0000ff15-0000-1000-8000-00805f9b34fb
    handle: 0x0053, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0054, uuid: 0000ff16-0000-1000-8000-00805f9b34fb
    handle: 0x0055, uuid: 00002803-0000-1000-8000-00805f9b34fb
    handle: 0x0056, uuid: 0000ff17-0000-1000-8000-00805f9b34fb

    Note: For this flag one has to write to handle 58; which DOES NOT EXIST in the above list
        - Unsure how one would go about finding the existence of Handle 58
    Would need to use another tool (e.g. gatttool) to write the required hex value to the associated Handle
        - Ex:       gatttool -b CC:50:E3:B6:BC:A6 --char-write-req -a 58 -n c9
    '''
    print("[!] UNABLE TO PERFORM FLAG 08 AT THIS POINT IN TIME..... CONTINUE!")
    ## Flag #09
    # Read the flag
    ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-09"], user_device, user_device__internals_map)
    # This flag requires brute forcing the value to write to this flag from 00 to ff
    # Nota Bene: It was learned during testing that there is a vast difference between HEX and INT and STR representations
    #   - The following will create a STRING of hex characters
    '''
    from itertools import product
    user_input__hex_length = int(input("What is the length of the hex bits to brute force: "))
    brute_force_map = map(''.join, product('0123456789ABCDEF', repeat=user_input__hex_length))
    for brute_force_string in brute_force_map:
        ble_ctf__write_characteristic(brute_force_string, BLE_CTF__CHARACTERISTIC_FLAGS["Flag-09"], user_device, user_device__internals_map)
    -> This will write out strings from "00" to "FF", but NOT in a way that works for this flag
    '''
    #   - The following will create a set of formatted strings
    '''
    hexlist = ["0x%02x" % n for n in range(256)]
    '''
    #   - The following will create an array of values
    '''
    hexlist =  [hex(x) for x in range(256)]

    one more way:
    for x in range(255): # 255 == FF
        xhex = '0x{:02x}'.format(x)
        os.system('gatttool -b 24:0a:c4:9a:7b:8e --char-write-req -a 0x3c -n '+xhex)
    '''
    #   -> Note: In all cases one can use int() to change to an int value with int(hex_value, 16)
    #       - Ex:       for hex_combo in hexlist:
    #                       ble_ctf__write_flag(int(hex_combo, 16), user_device, user_device__internals_map)
    #   - Still does not work.....
    #       - Attempted all lowercase with no leading "0x", but that still did not work
    # Create a brute-force map
    brute_force_map = map(''.join, product('0123456789ABCDEF', repeat=2))
    # Perform the brute-force write
    for brute_force_string in brute_force_map:
        # Convert the string to a decimal value (i.e. string to hex value)
        brute_force_string = int(brute_force_string, 16)
        ble_ctf__write_characteristic(brute_force_string, BLE_CTF__CHARACTERISTIC_FLAGS["Flag-09"], user_device, user_device__internals_map)
    # Read the new value
    ninth_flag_value = ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-09"], user_device, user_device__internals_map)
    # Submit the flag
    ble_ctf__write_flag(ninth_flag_value, user_device, user_device__internals_map)
    # Check the score
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    ## Flag #10
    read_iteration = 1000
    ## Begin the multi-read
    print("[*] Reading Characteristic [ {0} ]: ".format(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-10"]), end="")
    for read_iteration in range(0, read_iteration):
        #read_value = user_device.read__device__characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-10"])     # Having an issue performing this read... Might be missing structures for performing the reads?
        read_avlue = ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-10"], user_device, user_device__internals_map)
        print(".", end="")
    print("+")
    #read_value = user_device.read__device__characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-10"])
    read_value = ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-10"], user_device, user_device__internals_map)
    # Write the read value to the submission flag
    ble_ctf__write_flag(read_value, user_device, user_device__internals_map)
    # Check the score
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    ## Flag #11     -       Note: Currently implementes a 'gatttool' system call to get the data
    ble_ctf__read_characteristic(BLE_CTF__CHARACTERISTIC_FLAGS["Flag-11"], user_device, user_device__internals_map)
    # Note: Need to disconnect from the BLE CTF before making gatttool command calls
    user_device.Disconnect()
    # Create a conversion map via the GATT Tool
    conversion_map = enumerate_and_return__bluez_to_gatt_map__characteristics(user_device.device_address)
    # Create a converted handle from the BlueZ Handle format to the GATT Tool Handle format
    handle_value = convert__bluez_handle_to_gatt_tool_handle(BLE_CTF__CHARACTERISTIC_FLAGS['Flag-11'])
    # Use GATT Tool to perform the write request and listen for the response notification; capturing the return data
    eleventh_flag_value = gatttool__write_request_and_listen(user_device.device_address, handle_value)
    # Scan for devices again to try and "relocate" the BLE CTF
    discovered_devices = create_and_return__bluetooth_scan__discovered_devices()
    # Note: Reconnect to the BLE CTF after making gatttool command calls
    user_device.Connect()
    # Write the data to the flag submission and check the score
    ble_ctf__write_flag(eleventh_flag_value, user_device, user_device__internals_map)
    # Read new score
    ble_ctf__read_score_flag(user_device, user_device__internals_map)
    print("===============================================================================================\n\t[+] COMPLETED BLE CTF DEVICE FLAGS [+]\n===============================================================================================")
    ble_ctf__end_string = "===============================================================================================\n\t[+] COMPLETED BLE CTF DEVICE FLAGS [+]\n===============================================================================================\n"
    logging__log_event(LOG__GENERAL, ble_ctf__end_string)

#

## Running BLE CTF test
#ble_ctf__scan_and_enumeration()

## Attempt to pair the device
#device_interface.Pair()     # Fails... Due to 'Authentication Failed'

## Functions for Interacting with and Enumerating Handle Information

### Back of Envelope Space

# TODO: Fix the user input check below
def check_and_validate__user_selection(user_selection, itemNumber):
    if dbg != 1:    # ~!~
        #print("User Selection:\t{0}\nItem Number:\t{1}".format(user_selection, itemNumber))
        out_log_string = "User Selection:\t{0}\nItem Number:\t{1}".format(user_selection, itemNumber)
        print_and_log(out_log_string, LOG__DEBUG)
    # First attempt to convert the user selection into an int
    try:
        user_selection = int(user_selection)
    except ValueError:
        user_selection = input("Selection was not valid, please re-select: ")
    # Check that the value is an 'int' type
    while not isinstance(user_selection, int):
        user_selection = input("Selection was not an 'int', please re-select: ")
        user_selection = int(user_selection)
    while user_selection > itemNumber:
        user_selection = input("Selection was outside of scale, please re-select: ")
        user_selection = int(user_selection)
    while user_selection < 1:
        user_selection = input("Selection unacceptable... please re-select: ")
        user_selection = int(user_selection)
    # Return True to confirm that the selection was correct
    return user_selection

# Function for simply identifying and enumerating BLE devices that are in range
def find_and_enumerate__bluetooth_device__user_selected():
    print("===============================================================================================\n\t[*] COMPLETE USER SELECTED DEVICE ENUMERATION\n===============================================================================================")
    
    ## Call to devices discovery function
    print("[*] Scanning for Discoverable Devices")
    discovered_devices = create_and_return__bluetooth_scan__discovered_devices()
    print("[+] Discovered Devices:\t{0}".format(discovered_devices))

    ## Check if any devices were discovered
    if len(discovered_devices) < 1:
        print("[-] No Devices Seen..... Perform a rescan!")
        exit
    
    ## Display the list of discovered devices
    print("[*] The following are the devices that this platform has discovered/seen:")
    itemNumber=1
    for device_address in discovered_devices:
        print("\t{0}:\t\t{1}".format(itemNumber, device_address))
        itemNumber += 1
    #print("Please Select one of the Above Devices to Examine")
    user_selection = input("Please Select one of the Above Devices to Examine: ")
    user_input_check = False
    while not user_input_check:
        user_input_check = check_and_validate__user_selection(user_selection, itemNumber)
    print("[!] User has selected device [ {0} ]".format(user_selection))
    user_selected_device = discovered_devices[int(user_selection)-1]
    # Perform an enumeration of the device chosen by the user
    user_device, user_device__mapping = connect_and_enumerate__bluetooth__low_energy(user_selected_device)
    pretty_print__gatt__dive_json(user_device, user_device__mapping)
    
    print("===============================================================================================\n\t[+] COMPLETED USER SELECTED DEVICE ENUMERATION [+]\n===============================================================================================")

# Function for searching and exploring a Bluetooth Device selected by the User
def check_and_explore__bluetooth_device__user_selected(target_device=None):
    #print("===============================================================================================\n\t[*] COMPLETE USER SELECTED DEVICE EXPLORATION\n===============================================================================================")
    out_log_string = "===============================================================================================\n\t[*] COMPLETE USER SELECTED DEVICE EXPLORATION\n==============================================================================================="
    print_and_log(out_log_string, LOG__USER)

    # Create variables for functionality
    still_exploring = 0

    ## Inner Function Definitions
    # Function for printing out the User Interactive Exploration Tool help menu
    def uiet__help_menu():
        print("[*] User Interactive Exploration Tool - Select Action")
        print("\t- 'print' to Pretty Print the known user device internals map\n\t- 'info' to print device information")
        print("\t- 'tools' to Access the Tools Sub-Menu\n\t- 'signals' to configure emission capture")
        print("\t- 'generate' to Access the Generation Sub-Menu\n\t- 'explore' to Access the Exploration Sub-Menu")
        print("\t- 'read' to Access the Reading Sub-Menu\n\t- 'write' to Access the Writing Sub-Menu")
        print("\t- 'help' to print this information\n\t- 'quit' to exit user exploration")
        print("\t- 'reconnect' to reconnect to the current target device")
        print("\tNota Bene:\tComplete Re-Read of the Device may be required to update the Device Internals Map")
        print("\tSsh.....")

    # Function for printing out the Generation Sub-Menu help menu
    def uiet__generate__help_menu():
        print("Generation Sub-Menu:\n\t- 'services' to generate a services list\n\t- 'characteristics' to genreate a characteristics list\n\t- 'descriptors' to generate a descriptors list")

    # Function for printing out the Exploration Sub-Menu help menu
    def uiet__explore__help_menu():
        print("Exploration Sub-Menu:\n\t- 'service' to explore a service\n\t- 'characteristic' to explore a characteristic\n\t- 'descriptor' to explore a descriptor")

    # Function for printing out the Reading Sub-Menu help menu
    def uiet__read__help_menu():
        print("Reading Sub-Menu:\n\t- 'characteristic' to read a characteristic\n\t- 'descriptor' to read a descriptor\n\t- 'all-descriptors' to perform a read to all know Descriptors\n\t- 'multi-read' to perform multiple reads of a characteristic")

    # Function for printing out the Writing Sub-Menu help menu
    def uiet__write__help_menu():
        print("Writing Sub-Menu:\n\t- 'characteristic' to write to a characteristic\n\t- 'descriptor' to write to a descriptor\n\t- 'brute-write' to brute force write to a characteristic\n\t- 'file-write' to write a file contents to a characteristic")

    # Function for printing out the Toggle-Notify Sub-Menu help menu
    def uiet__toggle__help_menu():
        print("Toggle Notify Sub-Menu:\n\t- 'on' to toggle a Notification on\n\t- 'off' to toggle a Notification off\n\t- 'toggle' to toggle the Notification of a Characteristic")

    # Function for printing out the secret help menu
    def uiet__secret__help_menu():
        print("-= Super Secret Help =-\n\t- 'generate-all' to create all the necessary lists\n\t- 'read-all' to read and display all the Characterisitcs\n\t- 'update-map' to get a new device internals map based on current D-Bus information\n\t- 'toggle-notify' to toggle notify on a given Characteristic")

    # Function for printing out the tools (e.g. mapping) Sub-Menu
    def uiet__tools__help_menu():
        print("Tools Sub-Menu:\n\t- 'print-maps' to print out the Landmine and Security maps\n\t- 'deep-dive' to print out a detailed deep dive delve of the device")

    # Function for printing out the signals (e.g. Notifications) Sub-Menu
    def uiet__signals__help_menu():
        print("Signals Sub-Menu:\n\t- 'prep-tools' to prepare the tools necessary for signal capture\n\t- 'config-receive' to configure the signal receiver\n\t- 'start-capture' to begin receiving signals\n\t- 'stop-capture' to end the receiving of signals\n\t- 'clear-config' to clear and reset the configuration of tools used for signal capture\n\t- 'set-char' to set the Characteristic for signal intent\n\t- 'toggle-char' to toggle the Notifiy property of the Characteristic")

    # Function for printing out the Connectivity (e.g. Pairing) Sub-Menu
    def uiet__connectivity__help_menu():
        print("Connectivity Sub-Menu:\n\t- 'pair' to pair with the targeted device")

    # Function for checking that a given list has been generated (i.e. not NoneType)
    def uiet__check__list(given_list):
        if not given_list:
            print("ERROR: The required list has not been generated")
            return False
        else:
            if dbg != 0:
                print("[+] The provided list is confirmed to exist")
            return True

    # Function for checking that a given user input is part of the given list of choices
    def uiet__check__input(user_input, given_list):
        if user_input not in given_list:
            return False
        else:
            return True

    ## Continuing User Interaction Code
    # Search for devices to explore
    #print("[*] Scanning for Discoverable Devices")
    out_log_string = "[*] Scanning for Discoverable Devices"
    print_and_log(out_log_string, LOG__USER)
    if target_device is not None:
        user_selected_device = target_device
        #### SPECIAL LOOP FOR TARGET DEVICE SEARCH
        ## Loop for searching for the specific device
        device_found_flag = False
        loop_iteration = 0
        search_no_more_times = 3

        # Search for the device based on a set number of times
        while device_found_flag == False and loop_iteration < search_no_more_times:
            ## Initial Scanning of the device
            try:
                # Performing a scan for general devices; main scan for devices to populate the linux D-Bus
                discovered_devices = create_and_return__bluetooth_scan__discovered_devices()
            except Exception as e:
                out_log_string = "[-] Error with adapter while attempting to discover devices\n\tError:\t\t[ {0} ]".format(e)
                print_and_log(out_log_string)
                print_and_log(out_log_string, LOG__DEBUG)
                break
            if discovered_devices is None:
                print("[-] No devices were found during scan and discovery")
                break
            # Iterate through the discovered devices, since working with tuples of (address, name) and not just a list of addresses
            for discovered_device in discovered_devices:
                # Sanity check for having found the target device
                if target_device not in discovered_device:
                    if dbg != 0:
                        out_log_string = "[!] Unable to find device [ {0} ]".format(target_device)
                        print_and_log(out_log_string)
                        print_and_log(out_log_string, LOG__DEBUG)
                    if dbg != 0:
                        out_log_string = "\tDiscovered Devices:\t[ {0} ]".format(discovered_devices)
                        print_and_log(out_log_string)
                        print_and_log(out_log_string, LOG__DEBUG)
                    #return None
                else:
                    if dbg != 0:
                        out_log_string = "[+] Able to find device [ {0} ]".format(target_device)
                        print_and_log(out_log_string)
                        print_and_log(out_log_string, LOG__DEBUG)
                    device_found_flag = True
                # Increase the interation count
                loop_iteration += 1
        if device_found_flag != True:
            out_log_string = "[-] Device not found with address [ {0} ]".format(target_device)
            print_and_log(out_log_string)
            print_and_log(out_log_string, LOG__ENUM)
            print_and_log(out_log_string, LOG__DEBUG)
            return None
        else:
            out_log_string = "[+] Found the device with address [ {0} ]".format(target_device)
            print_and_log(out_log_string)
            print_and_log(out_log_string, LOG__ENUM)
            print_and_log(out_log_string, LOG__DEBUG)
    else:
        user_selection = user_interaction__find_and_return__pick_device()
        user_selected_device = user_selection[0]        # The 0th item is the Bluetooth Address and the 1st item is the Bluetooth Name
    # Wrapped in a try statement for robustness
    try:
        # Create the necessary objects and connect to the device
        user_device, user_device__mapping, landmine_map, security_map = connect_and_enumerate__bluetooth__low_energy(user_selected_device)          # For some reason will stall here when waiting to pair, but fails when hitting "pair" button on remote host
    except Exception as e:
        # TODO: Add handlers for other types of errors (take a look at the understanding and handling errors function from BLE Class)
        output_log_string = "[!] Error occurred while connecting to the device"
        print_and_log(output_log_string, LOG__USER)
        # Actions to perform if a D-Bus related error is thrown; includes BlueZ errors
        if isinstance(e, dbus.exceptions.DBusException):
            if e.get_dbus_name() == 'org.freedesktop.DBus.Error.NoReply':
                output_log_string = "[-] Got No Reply while Attempting to Connect"
                print_and_log(output_log_string, LOG__USER)
                #return None
                return bluetooth_constants.RESULT_ERR_NO_REPLY
            elif e.get_dbus_name() == 'org.bluez.Error.Failed':
                output_log_string = "[-] May be connection issue of BR/EDR vs BLE device"
                print_and_log(output_log_string, LOG__USER)
                return bluetooth_constants.RESULT_ERR_NO_BR_CONNECT
            elif e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownObject':
                output_log_string = "[-] Device no longer exists within D-Bus knowledge / memory"
                print_and_log(output_log_string, LOG__USER)
                return bluetooth_constants.RESULT_ERR_DEVICE_FORGOTTEN
            elif e.get_dbus_name() == 'org.bluez.Error.NotPermitted':
                output_log_string = "[-] Device refusing permission to perform I/O"
                print_and_log(output_log_string, LOG__USER)
                return bluetooth_constants.RESULT_ERR_READ_NOT_PERMITTED
            elif e.get_dbus_name() == 'org.bluez.Error.InProgress':
                output_log_string = "[-] Device already has action In Progress"
                print_and_log(output_log_string, LOG__USER)
                return bluetooth_constants.RESULT_ERR_ACTION_IN_PROGRESS
            elif e.get_dbus_name() == 'org.freedesktop.DBus.Error.ServiceUnknown':
                output_log_string = "[-] Device does not have Service with the provided name"
                print_and_log(output_log_string, LOG__USER)
                return bluetooth_constants.RESULT_ERR_UNKNOWN_SERVCE
            else:
                output_log_string = "[!] check_and_explore__bluetooth_device__user_selected::Unknown D-Bus Error has Occured when Attempting a Connection"      # TODO: Add handling for when attempting to pair to a device; currently fails while pairing continues
                if dbg != 1:
                    output_log_string += "\n\tError:\t{0}\n\tD-Bus Name:\t{1}\n\tAll Error Args:\t{2}".format(e, e.get_dbus_name, e.args)
                print_and_log(output_log_string, LOG__USER)
                return None
        else:
            output_log_string = "[!] check_and_explore__bluetooth_device__user_selected::Unknown Error has Occured when Attempting a Connection"
            if dbg != 1:
                output_log_string += "\n\tError:\t{0}\n\tError Type:\t{1}\n\tAll Error Args:\t{2}".format(e, type(e), e.args)
            print_and_log(output_log_string, LOG__DEBUG)
            return None
    print("[+] Exploration Basics Successfully Created")
    # Santiy check from the abover try statement
    if not user_device:
        output_log_string = "[-] Unable to generate the necessary User Device Class Object.... Exiting...."
        print_and_log(output_log_string, LOG__USER)
        return None
    # Collect and return a mapping of the services and characteristics (NOTE: Can be done either through the collceted information OR via D-Bus records)
    user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
    if dbg != 0:
        pretty_print__gatt__dive_json(user_device, user_device__internals_map)
    # Test print out of the produced map
    still_exploring = 1
    uiet__help_menu()
    # Variables that are used/populated for user interaction
    services_list = None
    characteristics_list = None
    descriptors_list = None
    # Configuring signal tracking variables
    signal_char = None
    signal_props = None
    signal_intf = None
    signal_conf = "default"
    # Loop for performing exploreation of the device; Nota Bene: To continue operating within usermode one must use 'continue', otherwise use 'break' to exit usermode entirely
    while still_exploring:
        user_input = input("Select an Action to Take: ")
        if user_input == "quit":
            still_exploring = 0
            break
        elif user_input == "help":
            uiet__help_menu()
        elif user_input == "print":
            pretty_print__gatt__dive_json(user_device, user_device__internals_map)
            ## TODO: Add switch to the above allow for ASCii/Hex/Array output for collected data
        elif user_input == "info":
            #print("\tAddress:\t{0}".format(user_device.device_address))
            out_log_string = "\tAddress:\t{0}".format(user_device.device_address)
            print_and_log(out_log_string, LOG__USER)
            user_device.find_and_get__all_device_properties()
            # Note: The above call will produce verbose information about the device properties
        elif user_input == "generate":
            uiet__generate__help_menu()
            user_input__sub_menu = input("Select a Sub-Action to Take: ")
            if user_input__sub_menu == "services":
                services_list = user_device.find_and_return__internal_map__services_list(user_device__internals_map)
            elif user_input__sub_menu == "characteristics":
                characteristics_list = user_device.find_and_return__internal_map__characteristics_list(user_device__internals_map)
            elif user_input__sub_menu == "descriptors":
                descriptors_list = user_device.find_and_return__internal_map__descriptors_list(user_device__internals_map)
            else:
                #print("\tDid not understand Sub-Menu User Input")
                out_log_string = "\tDid not understand Sub-Menu User Input"
                print_and_log(out_log_string, LOG__USER)
        elif user_input == "generate-all":
            #print("[*] Generating all internal lists")
            out_log_string = "[*] Generating all internal lists"
            print_and_log(out_log_string, LOG__USER)
            services_list = user_device.find_and_return__internal_map__services_list(user_device__internals_map)
            characteristics_list = user_device.find_and_return__internal_map__characteristics_list(user_device__internals_map)
            descriptors_list = user_device.find_and_return__internal_map__descriptors_list(user_device__internals_map)
        elif user_input == "explore":
            # NOTE: Will need this information to be generated prior to exploration?
            uiet__explore__help_menu()
            user_input__sub_menu = input("Select a Sub-Action to Take: ")
            if user_input__sub_menu == "service":
                # Get service name
                service_name = None
                if not uiet__check__list(services_list):
                    continue
                for service_item in services_list:
                    #print("\t{0}".format(service_item))
                    out_log_string = "\t{0}".format(service_item)
                    print_and_log(out_log_string, LOG__USER)
                service_name = input("Select a Service to Explore: ")
                detailed_service = user_device.find_and_return__internal_map__detailed_service(user_device__internals_map, service_name)
                user_device.pretty_print__gatt__service__detailed_information(detailed_service)
            elif user_input__sub_menu == "characteristic":
                # Get characteristic name
                characteristic_name = None
                acceptable_choice = False
                if not uiet__check__list(characteristics_list):
                    continue
                while not acceptable_choice:
                    for characteristic_item in characteristics_list:
                        #print("\t{0}".format(characteristic_item))
                        out_log_string = "\t{0}".format(characteristic_item)
                        print_and_log(out_log_string, LOG__USER)
                    characteristic_name = input("Select a Characteristic to Explore: ")
                    # Check that the response made sense
                    if characteristic_name in characteristics_list:
                        acceptable_choice = True
                detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
                user_device.pretty_print__gatt__characteristic__detailed_information(detailed_characteristic)
            elif user_input__sub_menu == "descriptor":
                # Get descriptor name
                descriptor_name = None
                if not uiet__check__list(descriptors_list):
                    continue
                for descriptor_item in descriptors_list:
                    #print("\t{0}".format(descriptor_item))
                    out_log_string = "\t{0}".format(descriptor_item)
                    print_and_log(out_log_string, LOG__USER)
                descriptor_name = input("Select a Descriptor to Explore: ")
                detailed_descriptor = user_device.find_and_return__internal_map__detailed_descriptor(user_device__internals_map, descriptor_name)
                user_device.pretty_print__gatt__descriptor__detailed_information(detailed_descriptor)
            else:
                #print("\tDid not understand Sub-Menu User Input")
                out_log_string = "\tDid not understand Sub-Menu User Input"
                print_and_log(out_log_string, LOG__USER)
        elif user_input == "read":
            # NOTE: Having an issue of 'NoneType' object is not iterable in Python
            uiet__read__help_menu()
            user_input__sub_menu = input("Select a Sub-Action to Take: ")
            if user_input__sub_menu == "characteristic":
                characteristic_name = None
                if not uiet__check__list(characteristics_list):
                    continue
                for characteristic_item in characteristics_list:
                    #print("\t{0}".format(characteristic_item))
                    out_log_string = "\t{0}".format(characteristic_item)
                    print_and_log(out_log_string, LOG__USER)
                characteristic_name = input("Select a Characteristic to Read: ")
                # Check that the provided characteristics is part of the generated list
                if not uiet__check__input(characteristic_name, characteristics_list):
                    out_log_string = "[-] Characteristic provided is not part of generated list"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Create structures for reading characteristic
                detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
                # First check if that characteristic allows for reading
                if "read" not in detailed_characteristic["Flags"]:
                    #print("[-] No 'read' capability with characteristic [ {0} ]".format(characteristic_name))
                    out_log_string = "[-] No 'read' capability with characteristic [ {0} ]".format(characteristic_name)
                    print_and_log(out_log_string, LOG__USER)
                    continue
                characteristic_service_path = detailed_characteristic["Service"]
                characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
                read_value = user_device.read__device__characteristic__with_signature(characteristic_interface)
                #read_value = user_device.find_and_get__characteristic_property(characteristic_properties, 'Value')
                if isinstance(read_value, dbus.Array):
                    #print("\tCharacteristic Value (ASCii | Hex):\t{0}\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(read_value), user_device.dbus_read_value__to__hex_string(read_value)))
                    out_log_string = "\tCharacteristic Value (ASCii | Hex):\t{0}\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(read_value), user_device.dbus_read_value__to__hex_string(read_value))
                    print_and_log(out_log_string, LOG__USER)
                else:
                    #print("\tCharaceristic Value:\t{0}".format(read_value))
                    out_log_string = "\tCharaceristic Value:\t{0}".format(read_value)
                    print_and_log(out_log_string, LOG__USER)
            elif user_input__sub_menu == "descriptor":
                descriptor_name = None
                if not uiet__check__list(descriptors_list):
                    #print("[-] Missing Descriptors List.  Please generate")
                    out_log_string = "[-] Missing Descriptors List.  Please generate"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                for descriptor_item in descriptors_list:
                    #print("\t{0}".format(descriptor_item))
                    out_log_string = "\t{0}".format(descriptor_item)
                    print_and_log(out_log_string, LOG__USER)
                descriptor_name = input("Select a Descriptor to Read: ")
                # Check that the provided descriptor is part of the generated list
                if not uiet__check__input(descriptor_name, descriptors_list):
                    out_log_string = "[-] Descriptor provided is not part of generated list"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Create structures for reading descriptor
                detailed_descriptor = user_device.find_and_return__internal_map__detailed_descriptor(user_device__internals_map, descriptor_name)
                #print("[?] Type for details:\t{0}\n\t{1}".format(type(detailed_descriptor), detailed_descriptor))
                # Check first that something was returned
                if not detailed_descriptor:
                    #print("[!] Error: Descriptor present in map but NOTHING was read....")
                    out_log_string = "[!] Error: Descriptor present in map but NOTHING was read...."
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Check if the flags exist 
                ## NOTE: Ignore the search for flags; just make the read regardless!
                '''
                if "Flags" in detailed_descriptor:
                    if not detailed_descriptor["Flags"]:
                        print("[-] Error: Descriptor present in map has 'None' as the flags...")
                        continue
                    # First chcek if the descriptor allows for reading
                    if "read" not in detailed_descriptor["Flags"]:
                        print("[-] No 'read' capability with descriptor [ {0} ]".format(descriptor_name))
                        continue
                    descriptor_characteristic_path = detailed_descriptor["Characteristic"]
                    descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = user_device.create_and_return__descriptor__gatt_inspection_set(descriptor_characteristic_path, descriptor_name)
                    read_value = user_device.read__device__descriptor(descriptor_interface)
                    if isinstance(read_value, dbus.Array):
                        print("\tDescriptor Value (ASCii):\t{0}".format(user_device.dbus_read_value__to__ascii_string(read_value)))
                    else:
                        print("\tDescriptor Value:\t{0}".format(read_value))
                else:
                    print("[-] Descriptor has no 'Flags'")
                    break
                '''
                # Create the necessary structures and read from the provided descriptor     | WORKS!
                descriptor_characteristic_path = detailed_descriptor["Characteristic"]
                descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = user_device.create_and_return__descriptor__gatt_inspection_set(descriptor_characteristic_path, descriptor_name)
                read_value = user_device.read__device__descriptor(descriptor_interface)
                # Test value read
                if dbg != 1:
                    out_log_string = "\t\t[?] Descriptor Read:\t\t{0}".format(read_value)
                    print_and_log(out_log_string, LOG__DEBUG)
                if isinstance(read_value, dbus.Array):
                    #print("\tDescriptor Value (ASCii | Hex):\t{0}\t\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(read_value), user_device.dbus_read_value__to__hex_string(read_value)))
                    out_log_string = "\tDescriptor Value (ASCii | Hex):\t{0}\t\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(read_value), user_device.dbus_read_value__to__hex_string(read_value))
                    print_and_log(out_log_string, LOG__USER)
                else:
                    #print("\tDescriptor Value:\t{0}".format(read_value))
                    out_log_string = "\tDescriptor Value:\t{0}".format(read_value)
                    print_and_log(out_log_string, LOG__USER)
            elif user_input__sub_menu == "all-descriptors":
                descriptor_name = None
                if not uiet__check__list(descriptors_list):
                    #print("[-] Missing Descriptors List. Please generate")
                    out_log_string = "[-] Missing Descriptors List. Please generate"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Loop for reading from EVERY Descriptor in the Descriptors List
                for descriptor_name in descriptors_list:
                    # Generating structures for exampling the 'snaphot' device internals map
                    detailed_descriptor = user_device.find_and_return__internal_map__detailed_descriptor(user_device__internals_map, descriptor_name)
                    descriptor_characteristic_path = detailed_descriptor["Characteristic"]
                    descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = user_device.create_and_return__descriptor__gatt_inspection_set(descriptor_characteristic_path, descriptor_name)
                    # Make method call to ReadValue() and get the read_value
                    read_value = user_device.read__device__descriptor(descriptor_interface)
                    if dbg != 0:
                        print("-----\n[?]\tRead Value:\t{0}\n\tDesc Name:\t{1}\n-----".format(read_value, descriptor_name))
                        out_log_stirng = "-----\n[?]\tRead Value:\t{0}\n\tDesc Name:\t{1}\n-----".format(read_value, descriptor_name)
                        print_and_log(out_log_string, LOG__USER)
                    '''
                    if isinstance(read_value, dbus.Array):
                        print("\tDescriptor Value (ASCii | Hex):\t{0}\t\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(read_value), user_device.dbus_read_value__to__hex_string(read_value)))
                    else:
                        print("\tDescriptor Value:\t{0}".format(read_value))
                    '''
                    # Testing Class debug print
                    user_device.debug_print__dbus__read_value("Descriptor", read_value)
            elif user_input__sub_menu == "multi-read":
                ## Performing multiple reads of a provided Characteristic; comes from BLE CTF flag (char003d)
                characteristic_name = None
                if not uiet__check__list(characteristics_list):
                    #print("[-] Missing Characteristics List. Please generate")
                    out_log_string = "[-] Missing Characteristics List. Please generate"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                for characteristic_item in characteristics_list:
                    #print("\t{0}".format(characteristic_item))
                    out_log_string = "\t{0}".format(characteristic_item)
                    print_and_log(out_log_string, LOG__USER)
                characteristic_name = input("Select a Characteristic to Read: ")
                # Check that the provided characteristics is part of the generated list
                if not uiet__check__input(characteristic_name, characteristics_list):
                    out_log_string = "[-] Characteristic provided is not part of generated list"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Create structures for reading characteristic
                detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
                # First check if that characteristic allows for reading
                if "read" not in detailed_characteristic["Flags"]:
                    #print("[-] No 'read' capability with characteristic [ {0} ]".format(characteristic_name))
                    out_log_string = "[-] No 'read' capability with characteristic [ {0} ]".format(characteristic_name)
                    print_and_log(out_log_string, LOG__USER)
                    continue
                ## Confirmed that this characteristic CAN be read from; now create the structures for reading the exact characteristic
                characteristic_service_path = detailed_characteristic["Service"]
                characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
                ## Request from the user how many times to read from the characteristic
                user_input__read_count = None
                while not isinstance(user_input__read_count,int):
                    user_input__read_count = int(input("Provide the number of reads to perform: "))
                #print("[?] User requested [ {0} ] reads against Characteristic [ {1} ]".format(user_input__read_count, characteristic_name))
                if dbg != 0:
                    out_log_string = "[?] User requested [ {0} ] reads against Characteristic [ {1} ]".format(user_input__read_count, characteristic_name)
                    print_and_log(out_log_string, LOG__USER)
                ## Begin the multi-read
                print("[*] Reading: ", end="")
                #out_log_stirng = "[*] Reading: "
                for read_iteration in range(0, user_input__read_count):
                    read_value = user_device.read__device__characteristic__with_signature(characteristic_interface)
                    #read_value = user_device.find_and_get__characteristic_property(characteristic_properties, 'Value')
                    print(".", end="")
                print("+")
                if isinstance(read_value, dbus.Array):
                    #print("\tCharacteristic Value (ASCii | Hex):\t{0}\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(read_value), user_device.dbus_read_value__to__hex_string(read_value)))
                    out_log_string = "\tCharacteristic Value (ASCii | Hex):\t{0}\t\t|\t\t{1}".format(user_device.dbus_read_value__to__ascii_string(read_value), user_device.dbus_read_value__to__hex_string(read_value))
                    print_and_log(out_log_string, LOG__USER)
                else:
                    #print("\tCharaceristic Value:\t{0}".format(read_value))
                    out_log_string = "\tCharaceristic Value:\t{0}".format(read_value)
                    print_and_log(out_log_string, LOG__USER)
            else:
                #print("\tDid not understand Sub-Menu User Input")
                out_log_string = "\tDid not understand Sub-Menu User Input"
                print_and_log(out_log_string, LOG__USER)
        elif user_input == "write":
            uiet__write__help_menu()        ## TODO: Add file write from here ~!~
            #print("[!] Note: Writes for BLE only pass the first 21 characters passed; BLE might expect 20 + terminator (e.g. 0x00)")
            out_log_string = "[!] Note: Writes for BLE only pass the first 21 characters passed; BLE might expect 20 + terminator (e.g. 0x00)"
            print_and_log(out_log_string, LOG__USER)
            user_input__sub_menu = input("Select a Sub-Action to Take: ")
            if user_input__sub_menu == "characteristic":
                characteristic_name = None
                if not uiet__check__list(characteristics_list):
                    continue
                for characteristic_item in characteristics_list:
                    print("\t{0}".format(characteristic_item))
                characteristic_name = input("Select a Characteristic to Write: ")
                # Check that the provided characteristics is part of the generated list
                if not uiet__check__input(characteristic_name, characteristics_list):
                    out_log_string = "[-] Characteristic provided is not part of generated list"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Create structures for writing to characteristic
                detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
                # First check if that characteristic allows for writing
                if "write" not in detailed_characteristic["Flags"]:
                    #print("[-] No 'write' capability with characteristic [ {0} ]".format(characteristic_name))
                    out_log_stirng = "[-] No 'write' capability with characteristic [ {0} ]".format(characteristic_name)
                    print_and_log(out_log_string, LOG__USER)
                    continue
                characteristic_service_path = detailed_characteristic["Service"]
                characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
                user_input__write_value = input("What should be written to the Characteristic: ")
                ## TODO: Have method of telling what the signature/info-type is expected by the Write
                #user_device.write__device__characteristic(characteristic_interface, user_input__write_value)
                # Function call to write the entire user input string to the characteristic
                #user_device.write__device__characteristic__one_byte_at_a_time(characteristic_interface, user_input__write_value)        # NOTE: This function call converts the value first to ASCii encoding and then passes the data
                # Trying a new Class write function
                #user_device.write__device__characteristic(characteristic_interface, user_input__write_value)
                ## NOTE: The above does multiple writes.  This has been commented out to just call the 'write__device__characteristc' function since it has built it type detection for writing
                # Check for type of write intended by the user; make changes as required
                if isinstance(user_input__write_value, str):
                    # String-based checks of variables passed for writing
                    if user_input__write_value.startswith('0x'):
                        out_log_string = "[*] Write identified as intended hex value [ {0} ]".format(user_input__write_value)
                        print_and_log(out_log_string, LOG__USER)
                        user_input__write_value = int(user_input__write_value, 16)
                    elif user_input__write_value.isdigit():
                        out_log_string = "[*] Write identified as intended decimal value [ {0} ]".format(user_input__write_value)
                        print_and_log(out_log_string, LOG__USER)
                        # Further processing if the integer passed is larger than representable by a single byte
                        #if int(user_input__write_value) > 255:
                            # Write the provided integer as a 20 byte string
                        #    user_input__write_value = int(user_input__write_value).to_bytes(20, byteorder='big')
                        # Simple conversion
                        #else:
                            #user_input__write_value = int(user_input__write_value)
                        # Simply convert value to int
                        user_input__write_value = int(user_input__write_value)
                    else:
                        out_log_string = "[*] Write identified as intended string value [ {0} ]".format(user_input__write_value)
                        print_and_log(out_log_string, LOG__USER)
                # Perform call to Write
                user_device.write__device__characteristic(characteristic_interface, user_input__write_value)
            elif user_input__sub_menu == "descriptor":
                descriptor_name = None
                if not uiet__check__list(descriptors_list):
                    continue
                for descriptor_item in descriptors_list:
                    #print("\t{0}".format(descriptor_item))
                    out_log_stirng = "\t{0}".format(descriptor_item)
                    print_and_log(out_log_string, LOG__USER)
                descriptor_name = input("Select a Descriptor to Write: ")
                # Check that the provided descriptor is part of the generated list
                if not uiet__check__input(descriptor_name, descriptors_list):
                    out_log_string = "[-] Descriptor provided is not part of generated list"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Create structures for writing to descriptor
                detailed_descriptor = user_device.find_and_return__internal_map__detailed_descriptor(user_device__internals_map, descriptor_name)
                # First check if the descriptor allows for writing
                if "write" not in detailed_descriptor["Flags"]:
                    #print("[-] No 'write' capability with descriptor [ {0} ]".format(descriptor_name))
                    out_log_stirng = "[-] No 'write' capability with descriptor [ {0} ]".format(descriptor_name)
                    print_and_log(out_log_string, LOG__USER)
                    continue
                descriptor_characteristic_path = detailed_descriptor["Descriptor"]
                descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = self.create_and_return__descriptor__gatt_inspection_set(descriptor_characteristic_path, descriptor_name)
                user_input__write_value = input("What should be written to the Descriptor: ")
                user_device.write__device__descriptor(descriptor_interface, user_input__write_value)
            elif user_input__sub_menu == "brute-write":
                ## Perform a brute force write to a specified Characteristic; Note: Writing will be (ASCii?) strings (e.g. copy and paste ASCii string flag response to write flag characteristic)
                characteristic_name = None
                if not uiet__check__list(characteristics_list):
                    #print("[-] Characteristics list is missing. Pleaes generate")
                    out_log_string = "[-] Characteristics list is missing. Pleaes generate"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                for characteristic_item in characteristics_list:
                    #print("\t{0}".format(characteristic_item))
                    out_log_string = "\t{0}".format(characteristic_item)
                    print_and_log(out_log_string, LOG__USER)
                characteristic_name = input("Select a Characteristic to Write: ")
                # Check that the provided characteristics is part of the generated list
                if not uiet__check__input(characteristic_name, characteristics_list):
                    out_log_string = "[-] Characteristic provided is not part of generated list"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Create structures for writing to characteristic
                detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
                # First check if that characteristic allows for writing
                if "write" not in detailed_characteristic["Flags"]:
                    #print("[-] No 'write' capability with characteristic [ {0} ]".format(characteristic_name))
                    out_log_string = "[-] No 'write' capability with characteristic [ {0} ]".format(characteristic_name)
                    print_and_log(out_log_string, LOG__USER)
                    continue
                ## Good to create the structures used for performing the write
                characteristic_service_path = detailed_characteristic["Service"]
                characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
                ## Obtain the number of bits for the entire HEX String
                #user_input__write_value = input("What should be written to the Characteristic: ")
                user_input__hex_length = None
                while not isinstance(user_input__hex_length,int):
                    user_input__hex_length = int(input("What is the length of the hex bits to brute force: "))
                out_log_string = "[?] User requested [ {0} ] length hex brute force against Characteristic [ {1} ]".format(user_input__hex_length, characteristic_name)
                print_and_log(out_log_string, LOG__USER)
                ## TODO: Have method of telling what the signature/info-type is expected by the Write
                #user_device.write__device__characteristic(characteristic_interface, user_input__write_value)
                # Function call to write the entire user input string to the characteristic
                #user_device.write__device__characteristic__one_byte_at_a_time(characteristic_interface, user_input__write_value)        # NOTE: This function call converts the value first to ASCii encoding and then passes the data
                # Trying a new Class write function
                ## Create the map of all Hex values to brute force
                from itertools import product
                brute_force_map = map(''.join, product('0123456789ABCDEF', repeat=user_input__hex_length))
                if dbg != 0:
                    out_log_string = "[*] check_and_explore__bluetooth_device__user_selected::brute_force_map\t-\t[ {0} ]".format(brute_force_map)
                    print_and_log(out_log_string, LOG__DEBUG)
                print("Brute Force Writing: ", end="")
                for brute_force_string in brute_force_map:
                    print(".", end="")
                    # Converting string to hex
                    brute_force_int = int(brute_force_string, 16)
                    #brute_force_string = hex(brute_force_int)      # NOTE: This will convert an int into a string (formatted to look like hex)
                    brute_force_string = brute_force_int            # NOTE: This works for writing "hex" even though it is JUST passing an int
                    if dbg != 0:
                        out_log_string = "[*] check_and_explore__bluetooth_device__user_selected::brute_force_string\t-\t[ {0} ]\t\tbrute_force_int\t-\t[ {1} ]".format(brute_force_string, brute_force_int)
                        print_and_log(out_log_string, LOG__DEBUG)
                    user_device.write__device__characteristic(characteristic_interface, brute_force_string)
                print("+")
            elif user_input__sub_menu == "file-write":
                ## Perform a write to a characteristic based on the contents of a provided file to a specified Characteristic; Note: Writing will be a raw read and write of the provided information to the characteristic based on a set buffer size (default 20 bytes)
                characteristic_name = None
                if not uiet__check__list(characteristics_list):
                    out_log_string = "[*] Characteristics list is missing. Please generate"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                for characteristic_item in characteristics_list:
                    out_log_string = "\t{0}".format(characteristic_item)
                    print_and_log(out_log_string, LOG__USER)
                characteristic_name = input("Select a Characteristic to Write: ")
                # Check that the provided characteristic is part of the generated list
                if not uiet__check__input(characteristic_name, characteristics_list):
                    out_log_string = "[-] Characteristic provided is not part of generated list"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Create structures for writing to characteristic
                detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
                # First check if that characteristic allows for writing
                if "write" not in detailed_characteristic["Flags"]:
                    #print("[-] No 'write' capability with characteristic [ {0} ]".format(characteristic_name))
                    out_log_string = "[-] No 'write' capability with characteristic [ {0} ]".format(characteristic_name)
                    print_and_log(out_log_string, LOG__USER)
                    continue
                ## Good to create the structures used for performing the write
                characteristic_service_path = detailed_characteristic["Service"]
                characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
                ## Provide file to feed as input
                user_input__file_path = None
                user_input__file_contents = None
                buffer_default_size = 20
                while not isinstance(user_input__file_path,str):
                    user_input__file_path = input("What is the path to the input file: ")
                led_test = False
                # Check that file exists and then read its contents
                if (os.path.isfile(user_input__file_path) and os.path.exists(user_input__file_path)):
                    with open(user_input__file_path, "r") as user_file:
                        while True:
                        #user_input__file_contents = user_file.readline()
                            if led_test:
                                command_start = "!".encode()
                                command_type = "C".encode()
                            command_data = user_file.readline()
                            #command_data = bytearray.fromhex(command_data)
                            if len(command_data) == 0:
                                break
                            ## TODO: Check if command data is MORE THAN 20 Bytes, then loop through the line until all contents are sent, then continue to the next line
                            elif len(command_data) > buffer_default_size:
                                buffer_line = 0
                                while buffer_line < len(command_data):
                                    chunk = command_data[buffer_line:buffer_line+buffer_default_size]
                                    user_device.write__device__characteristic(characteristic_interface, chunk)
                                    buffer_line += buffer_default_size       # Always increment by the default of 20
                        # Debug check
                        #print("File Contents:\t\t{0}".format(user_input__file_contents))
                            else:
                                if led_test:
                                    ## Working code for LED Driver
                                    # Import hexlify tool
                                    from binascii import hexlify
                        #for line in user_input__file_contents:
                            #command_header = "{0:02x}{1:02x}".format(command_start, command_type)
                                    command_header = "{0}{1}".format(hexlify(command_start).decode(), hexlify(command_type).decode())
                                #command_header = "{0}{1}".format(command_start, command_type)
                            #print(command_header)
                        #    print("Line:\t{0}".format(line))
                        #    command_data = line
                                    total_command = "{0}{1}".format(command_header, command_data)
                                #print(total_command)
                                    total_command = bytes.fromhex(total_command)
                                    user_device.write__device__characteristic(characteristic_interface, total_command)
                                else:
                                    user_device.write__device__characteristic(characteristic_interface, command_data)
                        # Print done
                        out_log_string = "[+] Completed writing file contents to characteristic"
                        print_and_log(out_log_string, LOG__USER)
                # Check if file is pipe and exists; Note: Interesting behavior where the pipe will not continue to process information until it is read (good for audio syncing)
                elif stat.S_ISFIFO(os.stat(user_input__file_path).st_mode) and os.path.exists(user_input__file_path):
                    out_log_string = "[*] Provided file is a pipe"
                    print_and_log(out_log_string, LOG__USER)
                    try:
                        # Open the passed pipe and begin processing information
                        with open(user_input__file_path, "r") as user_file:
                            while True:
                                # Read from the pipe
                                command_data = user_file.readline()
                                # Write out information
                                user_device.write__device__characteristic(characteristic_interface, command_data)
                            # TODO: Add exist clause for above, gets caught if the pipe gets removed
                            #   - Perhaps check if the file still exists, otherwise close it
                                if len(command_data) == 0:
                                    if not os.path.exists(user_intput__file_path):
                                        break       # Escape from while True
                    except:     # Error handling to begin fail proofing
                        out_log_string = "[-] Provided file not found"
                        print_and_log(out_log_string, LOG__USER)
                else:
                    out_log_string = "[-] Provided file does not exist and/or cannot be found"
                    print_and_log(out_log_string, LOG__USER)
            else:
                #print("\tDid not understand Sub-Menu User Input")
                out_log_string = "\tDid not understand Sub-Menu User Input"
                print_and_log(out_log_string, LOG__USER)
        # Command for performing a read of all characteristics within the generated characteristic list; part of secret menu actions
        elif user_input == "read-all":
            #print("[*] Providing List of All Read Values Associated to known Characteristics")
            out_log_string = "[*] Providing List of All Read Values Associated to known Characteristics"
            print_and_log(out_log_string, LOG__USER)
            #print("\t[ Char Handle ]\t-\t[ Value (ASCii) ]")
            out_log_string = "\t[ Char Handle ]\t-\t[ Value (ASCii) ]"
            print_and_log(out_log_string, LOG__USER)
            if not uiet__check__list(characteristics_list):
                continue
            for characteristic_item in characteristics_list:
                # Adding MORE error handling and debugging
                try:
                    detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_item)
                except Exception as e:
                    if isinstance(exception_e, dbus.exceptions.DBusException):
                        #print("[!] Got a D-Bus Error when attempting to do things")
                        out_log_stirng = "[!] Got a D-Bus Error when attempting to do things"
                        print_and_log(out_log_string, LOG__USER)
                        if user_device.understand_and_handle__dbus_errors(e) == bluetooth_constants.RESULT_ERR_NOT_FOUND:
                            #print("[!] Error: Potentially method not found")
                            out_log_string = "[!] Error: Potentially method not found"
                            print_and_log(out_log_string, LOG__USER)
                            # TODO: Do something else to maintain functionality
                    else:
                        #print("[!] Got a non D-Bus Error when attempting to do things")
                        out_log_string = "[!] Got a non D-Bus Error when attempting to do things"
                        print_and_log(out_log_string, LOG__USER)
                        return None
                finally:
                    if dbg != 0:
                        out_log_string = "[*] Generated detailed characteristic information for [ {0} ]".format(characteristic_item)
                        print_and_log(out_log_string, LOG__DEBUG)
                characteristic_service_path = detailed_characteristic["Service"]
                # TODO: Add additional error checking around this statement to aid with 'Method "GetAll" with signature "s" on interface "org.freedesktop.DBus.Properties" doesn't exist' errors; Might need a more universal error handling solution
                characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_item)
                #user_device.read__device__characteristic(characteristic_interface)      # Call for Read Method
                #characteristic__read_value = user_device.find_and_get__characteristic_property(characteristic_properties, 'Value')
                characteristic__read_value = user_device.read__device__characteristic__with_signature(characteristic_interface)      # Call for Read Method
                # Convert D-Bus value to ASCii
                if isinstance(characteristic__read_value, dbus.Array):
                    #print("\tCharacteristic Value (ASCii):\t{0}".format(user_device.dbus_read_value__to__ascii_string(characteristic__read_value)))
                    characteristic__read_value = user_device.dbus_read_value__to__ascii_string(characteristic__read_value)
                #else:
                #    print("\tCharaceristic Value:\t{0}".format(read_value))
                # Print out this characteristic's line + value
                #print("\t{0}\t-\t{1}".format(characteristic_item, characteristic__read_value))
                out_log_string = "\t{0}\t-\t{1}".format(characteristic_item, characteristic__read_value)
                print_and_log(out_log_string, LOG__USER)
                # Secondary grab for debugging
                #read_test = user_device.read__device__characteristic__with_sig(characteristic_interface)
                #if isinstance(read_test, dbus.Array):
                    #print("\tCharacteristic Value (ASCii):\t{0}".format(user_device.dbus_read_value__to__ascii_string(characteristic__read_value)))
                #    read_test = user_device.dbus_read_value__to__ascii_string(read_test)
                #if dbg != 1:
                #    print("\t\tSig Read:\t{0}".format(read_test))
            if dbg != 1:    # ~!~
                #print("[+] Completed print of all characteristics and values")
                out_log_string = "[+] Completed print of all characteristics and values"
                print_and_log(out_log_string, LOG__DEBUG)
        # Command to update the internal device map; part of secret menu
        elif user_input == "update-map":
            #print("[*] Updating Device Internals Map")
            out_log_string = "[*] Updating Device Internals Map"
            print_and_log(out_log_string, LOG__USER)
            user_device__internals_map = user_device.enumerate_and_update__device__all_internals(user_device__internals_map)
            if dbg != 0:
                #print("[+] Device Internals Map has been updated!")
                out_log_string = "[+] Device Internals Map has been updated!"
                print_and_log(out_log_string, LOG__DEBUG)
        # Command to toggle Notify on a given Characteristic
        elif user_input == "toggle-notify":
            # First Choose a Characteristic
            characteristic_name = None
            if not uiet__check__list(characteristics_list):
                continue
            for characteristic_item in characteristics_list:
                #print("\t{0}".format(characteristic_item))
                out_log_string = "\t{0}".format(characteristic_item)
                print_and_log(out_log_string, LOG__USER)
            characteristic_name = input("Select a Characteristic to Read: ")
            # Check that the provided characteristics is part of the generated list
            if not uiet__check__input(characteristic_name, characteristics_list):
                out_log_string = "[-] Characteristic provided is not part of generated list"
                print_and_log(out_log_string, LOG__USER)
                continue
            # Create structures for reading characteristic
            detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
            # First check if that characteristic allows for reading
            if "notify" not in detailed_characteristic["Flags"]:
                #print("[-] No 'read' capability with characteristic [ {0} ]".format(characteristic_name))
                out_log_string = "[-] No 'notify' capability with characteristic [ {0} ]".format(characteristic_name)
                print_and_log(out_log_string, LOG__USER)
                continue
            characteristic_service_path = detailed_characteristic["Service"]
            characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
            # Decide what to do with the Characteristic
            uiet__toggle__help_menu()
            user_input__sub_menu = input("Select a Sub-Action to Take: ")
            if user_input__sub_menu == "on":
                characteristic_interface.StartNotify()
            elif user_input__sub_menu == "off":
                characteristic_interface.StopNotify()
            elif user_input__sub_menu == "toggle":
                print("Read then change to opposite")
            else:
                print("I do not even know")
        # Command to Run Long-Term Signal Capturing
        elif user_input == "notify-capture":
            # First Choose a Characteristic
            characteristic_name = None
            if not uiet__check__list(characteristics_list):
                continue
            for characteristic_item in characteristics_list:
                #print("\t{0}".format(characteristic_item))
                out_log_string = "\t{0}".format(characteristic_item)
                print_and_log(out_log_string, LOG__USER)
            characteristic_name = input("Select a Characteristic to Watch for Notifications: ")
            # Check that the provided characteristics is part of the generated list
            if not uiet__check__input(characteristic_name, characteristics_list):
                out_log_string = "[-] Characteristic provided is not part of generated list"
                print_and_log(out_log_string, LOG__USER)
                continue
            signal_char = characteristic_name
            # Create structures for reading characteristic
            detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
            # First check if that characteristic allows for reading
            if "notify" not in detailed_characteristic["Flags"]:
                #print("[-] No 'read' capability with characteristic [ {0} ]".format(characteristic_name))
                out_log_string = "[-] No 'notify' capability with characteristic [ {0} ]".format(characteristic_name)
                print_and_log(out_log_string, LOG__USER)
                continue
            characteristic_service_path = detailed_characteristic["Service"]
            characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
            # Create Listener
            user_device._bus_listener = system_dbus__bluez_signals()
            # Setting Up the Signal Properties and Interfaces
            signal_prop, signal_intf = user_device._bus_listener.validate__dbus__gatt_characteristic(user_device, signal_char)
            if signal_intf is None:
                output_log_string = "[-] No Characteristic Interface Generated for [ {0} ]".format(signal_char)
                print_and_log(output_log_string)
                signal_prop, signal_intf = None, None
                continue
            else:
                output_log_string = "[+] Characteristic Interface Generated for [ {0} ]".format(signal_char)
                print_and_log(output_log_string)

            #user_device._bus_listener.threads__configure_and_run(user_device._bus_listener.start_notification, characteristic_interface)       # Note: This call to the threads function will set the receivers, start notification, and run the MainLoop

            #'''
            # Configuring the Thread
            # Check if D-Bus Listener has been configured
            if hasattr(user_device, '_bus_listener'):
                out_log_string = "[+] Listener D-Bus tools are confirmed prepared"
                print_and_log(out_log_string, LOG__USER)
                # Check if Characteristic is set
                if signal_char is not None:
                    # Choose either default or custom"
                    if signal_conf == "default":
                        out_log_string = "[+] Signal capture set to DEFAULT configuration"
                        print_and_log(out_log_string, LOG__USER)
                        # Configure threads for the Listener D-Bus Property
                        #user_device._bus_listener.threads__configure_and_run(user_device._bus_listener.start_notification, signal_intf)       # Note: This call to the threads function will set the receivers, start notification, and run the MainLoop
                        # TODO: Fix the above to split into TWO separate commands; (1) configure the threads [ keep here ] and (2) running the thread [ move to start-capture ]
                        #   -> Note: Will definitely require functional re-writes
                        ## Requirements for Configuring and Running a Thread
                        # 1)        Create a Thread with Specific arguments; target (callback_function) and args (characteristic_interface, )
                        # 2)        Set the Thread
                        # 3)        Run the Thread
                        # TODO: Create a BLE Class Object Property that is the 'signal_thread'
                        #       Assign that Thread at the "configured thread"
                        #       Set the Thread Daemon to true
                        ## Creation and Configuration of the Signal Thread
                        # Create the Thread
                        user_device.signal_thread = threading.Thread(target=user_device._bus_listener.start_notification, args=(signal_intf, ))
                        # Configure the Thread 
                        user_device.signal_thread.daemon = True

            # Run the Thread for Capture
            # Check if D-Bus Listener has been configured
            if user_device.signal_thread is not None:
                out_log_string = "[+] Receiver configuration is set, moving to begin the capture"
                print_and_log(out_log_string)
                # Check that the signal Characteristic has been set
                if signal_char is not None:
                    # Check that the thread target attribute has been set
                    if hasattr(user_device.signal_thread, '_target'):
                        out_log_string = "[+] Starting capture of signal for characteristic [ {0} ] using signal configuration [ {1} ]".format(signal_char, signal_conf)
                        print_and_log(out_log_string, LOG__USER)
                        #user_device.signal_thread.run()
                        user_device.signal_thread.start()
                    else:
                        out_log_string = "[-] Target for thread is not set.... Please re-configure the receiver thread"
                        print_and_log(out_log_string, LOG__USER)
                else:
                    out_log_string = "[-] Characteristic not configured for signal capture... Please set the characteristic"
                    print_and_log(out_log_string, LOG__USER)
            else:
                out_log_string = "[-] Receiver configuration has not been run...."
                #out_log_string = "[-] Thread for signal capture has not been created... Configure the signal receiving prior to starting capture"
                print_and_log(out_log_string, LOG__USER)
            #'''

            # Do Other Stuff


            # Stop Thread
            
        # Command to open the secret help menu
        elif user_input == "ssh":
            uiet__secret__help_menu()
        elif user_input == "reconnect":
            try:
                user_device.Reconnect_Check()
            except Exception as e:
                return_error = user_device.understand_and_handle__dbus_errors(e)
                #print("[?] Return Error:\t{0}".format(return_error))
                out_log_string = "[?] Return Error:\t{0}".format(return_error)
                print_and_log(out_log_string, LOG__DEBUG)
                # Produce error log
                if return_error == bluetooth_constants.RESULT_ERR_NOT_FOUND:
                    output_log_string = "[-] Unable to query the device property.... Most likely due to device no longer being connected and within the D-Bus device list/memory"
                    print_and_log(output_log_string, LOG__DEBUG)
                    create_and_return__bluetooth_scan__discovered_devices()
        # Access to the tools menu; where one can observe the created maps for landmines and security
        elif user_input == "tools":
            uiet__tools__help_menu()
            user_input__sub_menu = input("Select a Sub-Action to Take: ")
            # Print out the generated Landmin and Security maps
            if user_input__sub_menu == "print-maps":
                out_log_string = "[*] Printing out of generated maps\n\tLandmine Map:\t\t-[ {0} ]-\n\tSecurity Map:\t\t-[ {1} ]-".format(landmine_map, security_map)
                print_and_log(out_log_string, LOG__USER)
            # Print out detailed delve exploration of all the device "layers"
            elif user_input__sub_menu == "deep-dive":
                out_log_string = "[*] Printing out the deep dive delve of the complete device"
                print_and_log(out_log_string, LOG__USER)
                # Check if the required structures are prepared
                if (services_list is None) or (characteristics_list is None) or (descriptors_list is None):
                    out_log_string = "[-] Required structures have not been created, please generate all"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Explore the Services
                for service_entry in services_list:
                    out_log_string = "[*] Service to be Explored [ {0} ]".format(service_entry)
                    print_and_log(out_log_string, LOG__USER)
                    detailed_service = user_device.find_and_return__internal_map__detailed_service(user_device__internals_map, service_entry)
                    user_device.pretty_print__gatt__service__detailed_information(detailed_service)
                # Explore the Characteristics
                for characteristic_entry in characteristics_list:
                    out_log_string = "[*] Characteristc to be Explored [ {0} ]".format(characteristic_entry)
                    print_and_log(out_log_string, LOG__USER)
                    detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_entry)
                    user_device.pretty_print__gatt__characteristic__detailed_information(detailed_characteristic)
                # Explore the Descriptors
                for descriptor_entry in descriptors_list:
                    out_log_string = "[*] Descriptor to be Explored [ {0} ]".format(descriptor_entry)
                    print_and_log(out_log_string, LOG__USER)
                    detailed_descriptor = user_device.find_and_return__internal_map__detailed_descriptor(user_device__internals_map, descriptor_entry)
                    user_device.pretty_print__gatt__descriptor__detailed_information(detailed_descriptor)
            else:
                out_log_string = "\tDid not understand Sub-Menu User Input"
                print_and_log(out_log_string, LOG__USER)
        # Access the signals menu; where one can configure and capture signals
        elif user_input == "signals":
            uiet__signals__help_menu()
            user_input__sub_menu = input("Select a Sub-Action to Take: ")
            # Nota Bene: The variables used for tracking signals are delcared earlier within this function; but are used ONLY in this section
            if user_input__sub_menu == "prep-tools":
                out_log_string = "[*] Preparing tools for signal capture"
                print_and_log(out_log_string, LOG__USER)
                user_device._bus_listener = system_dbus__bluez_signals()
            elif user_input__sub_menu == "config-receive":
                out_log_string = "[*] Configuring the signal receiver"
                print_and_log(out_log_string, LOG__USER)
                # Check if D-Bus Listener has been configured
                if hasattr(user_device, '_bus_listener'):
                    out_log_string = "[+] Listener D-Bus tools are confirmed prepared"
                    print_and_log(out_log_string, LOG__USER)
                    # Check if Characteristic is set
                    if signal_char is not None:
                        # Choose either default or custom"
                        if signal_conf == "default":
                            out_log_string = "[+] Signal capture set to DEFAULT configuration"
                            print_and_log(out_log_string, LOG__USER)
                            # Configure threads for the Listener D-Bus Property
                            #user_device._bus_listener.threads__configure_and_run(user_device._bus_listener.start_notification, signal_intf)       # Note: This call to the threads function will set the receivers, start notification, and run the MainLoop
                            # TODO: Fix the above to split into TWO separate commands; (1) configure the threads [ keep here ] and (2) running the thread [ move to start-capture ]
                            #   -> Note: Will definitely require functional re-writes
                            ## Requirements for Configuring and Running a Thread
                            # 1)        Create a Thread with Specific arguments; target (callback_function) and args (characteristic_interface, )
                            # 2)        Set the Thread
                            # 3)        Run the Thread
                            # TODO: Create a BLE Class Object Property that is the 'signal_thread'
                            #       Assign that Thread at the "configured thread"
                            #       Set the Thread Daemon to true
                            ## Creation and Configuration of the Signal Thread
                            # Create the Thread
                            user_device.signal_thread = threading.Thread(target=user_device._bus_listener.start_notification, args=(signal_intf, ))
                            # Configure the Thread 
                            user_device.signal_thread.daemon = True
                        else:
                            out_log_string = "[+] Signal capture set to CUSTOM configuration\t-\t[ {0} ]".format(signal_conf)
                            print_and_log(out_log_string, LOG__USER)
                    else:
                        out_log_string = "[-] Target Characteristic is not set.... Please set the target Characteristic before configuring receiving of signals"
                        print_and_log(out_log_string, LOG__USER)
                else:
                    out_log_string = "[-] Listening D-Bus has not been prepared.... Prepare the signals tools prior to configuring receiving signals"
                    print_and_log(out_log_string, LOG__USER)
            elif user_input__sub_menu == "start-capture":
                out_log_string = "[*] Starting signal capture..."
                print_and_log(out_log_string, LOG__USER)
                # Check if D-Bus Listener has been configured
                if user_device.signal_thread is not None:
                    out_log_string = "[+] Receiver configuration is set, moving to begin the capture"
                    print_and_log(out_log_string)
                    # Check that the signal Characteristic has been set
                    if signal_char is not None:
                        # Check that the thread target attribute has been set
                        if hasattr(user_device.signal_thread, '_target'):
                            out_log_string = "[+] Starting capture of signal for characteristic [ {0} ] using signal configuration [ {1} ]".format(signal_char, signal_conf)
                            print_and_log(out_log_string, LOG__USER)
                            user_device.signal_thread.run()
                        else:
                            out_log_string = "[-] Target for thread is not set.... Please re-configure the receiver thread"
                            print_and_log(out_log_string, LOG__USER)
                    else:
                        out_log_string = "[-] Characteristic not configured for signal capture... Please set the characteristic"
                        print_and_log(out_log_string, LOG__USER)
                else:
                    out_log_string = "[-] Receiver configuration has not been run...."
                    #out_log_string = "[-] Thread for signal capture has not been created... Configure the signal receiving prior to starting capture"
                    print_and_log(out_log_string, LOG__USER)
            elif user_input__sub_menu == "stop-capture":
                out_log_string = "[*] Stopping signal capture..."
                print_and_log(out_log_string, LOG__USER)
                ## TODO: Implement Stop for signal capture
            elif user_input__sub_menu == "clear-config":
                out_log_string = "[*] Clearing configuration.... Removing timers and signal receivers"
                print_and_log(out_log_string, LOG__USER)
                # Check if D-Bus Listener has been configured
                if hasattr(user_device, '_bus_listener'):
                    user_device._bus_listener.clear_all_timers()
                    out_log_string = "[+] Removed timers and signal receivers"
                    print_and_log(out_log_string, LOG__USER)
                else:
                    out_log_string = "[-] Listening D-Bus has not been prepared.... Unable to clear timers and signal receivers"
                    print_and_log(out_log_string, LOG__USER)
            elif user_input__sub_menu == "set-char":
                out_log_string = "[*] Configure the Characteristic for emission capture"
                print_and_log(out_log_string, LOG__USER)
                # Present a list of potential Characteristics to select from
                #signal_char = None
                # Check to ensure that the characteristics list exists
                if not uiet__check__list(characteristics_list):
                    #print("[-] Missing Characteristics List. Please generate")
                    out_log_string = "[-] Missing Characteristics List. Please generate"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                # Check that prep-tools has been performed before allowing the user to set-char
                elif not hasattr(user_device, '_bus_listener'):
                    out_log_string = "[-] Signal capture tools have not been prepared.  Please prep the tools"
                    print_and_log(out_log_string, LOG__USER)
                    continue
                for characteristic_item in characteristics_list:
                    #print("\t{0}".format(characteristic_item))
                    out_log_string = "\t{0}".format(characteristic_item)
                    print_and_log(out_log_string, LOG__USER)
                signal_char = input("Select a Characteristic to Read: ")
                # Generate the structures for Notify control
                detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, signal_char)
                # Check that the characteristic has a notification ability
                if "notify" not in detailed_characteristic["Flags"]:
                    out_log_string = "[-] No 'notify' capability with the characteristic [ {0} ]".format(signal_char)
                    print_and_log(out_log_string, LOG__USER)
                    # Un-set the signal Characteristic
                    signal_char = None
                    continue
                else:
                    signal_prop, signal_intf = user_device._bus_listener.validate__dbus__gatt_characteristic(user_device, signal_char)
                    if signal_intf is None:
                        output_log_string = "[-] No Characteristic Interface Generated for [ {0} ]".format(signal_char)
                        print_and_log(output_log_string)
                        signal_prop, signal_intf = None, None
                        continue
                    else:
                        output_log_string = "[+] Characteristic Interface Generated for [ {0} ]".format(signal_char)
                        print_and_log(output_log_string)
            elif user_input__sub_menu == "toggle-char":
                out_log_string = "[*] Toggle Characteristic Notifications On/Off"
                print_and_log(out_log_string, LOG__USER)
                if signal_char is not None:
                    ## Continue
                    out_log_string = "[*] Characteristic signal [ {0} ] configured... Continuing to toggle notifications".format(signal_char)
                    print_and_log(out_log_string)
                    # Generate the structures for Notify control
                    detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, signal_char)
                else:
                    out_log_string = "[-] Error: Must determine Characteristic to toggle emission"
                    print_and_log(out_log_string)
            else:
                out_log_string = "\tDid not understand Sub-Menu User Input"
                print_and_log(out_log_string, LOG__USER)
        elif user_input == 'connectivity':
            uiet__connectivity__help_menu()
            user_input__sub_menu = input("Select a Sub-Action to Take: ")
            if user_input__sub_menu == 'pair':
                out_log_string = "[*] Pairing to target device [ {0} ]".format(user_device.device_address)
                print_and_log(out_log_string)
                # Check variables to see if device is known to support the pre-2.1 pairing mechanism
                if user_device.device_legacy_pairing:
                    out_log_string = "[+] Device supports pre-2.1 pairing mechanism OR false-positive due to device having disabled Extended Inquiry Response support"
                    print_and_log(out_log_string)
                else:
                    out_log_string = "[-] Device does not support pre-2.1 pairing mechanism"
                    print_and_log(out_log_string)
                # TODO: Call pairing function (i.e. user_device.Pair()?) to initiate pairing to the device
                user_device.device_interface.Pair()
            elif user_input__sub_menu == 'cancel-pair':
                out_log_string = "[*] Canceling initialized pairing operation"
                print_and_log(out_log_string)
                # TODO: Call cancel to pairing
                user_device.device_interface.CancelPairing()
        else:
            #print("\tDid not understand User Input")
            out_log_string = "\tDid not understand User Input"
            print_and_log(out_log_string, LOG__USER)
    #print("===============================================================================================\n\t[+] COMPLETED USER SELECTED DEVICE EXPLORATION [+]\n===============================================================================================")
    out_log_string = "===============================================================================================\n\t[+] COMPLETED USER SELECTED DEVICE EXPLORATION [+]\n==============================================================================================="
    print_and_log(out_log_string, LOG__USER)

## Functions for Debugging the D-Bus Interfaces

# Function for Enumerating a given D-Bus Interface Method Argument Dictionary and Return a Method Argument Map
def enumerate_and_return__dbus__method__single_argument_map(raw__method__argument_dict):
    if dbg != 0:
        print("[*] Returning [ Single Method Argument Map ] from Provided Data [ {0} ]".format(raw__method__argument_dict))
    # Create variabale for tracking the Single Method Argument Map
    method_argument_map = {}
    # Loop through the Method Arguments
    for raw__method_argument__attribute in raw__method__argument_dict:
        # NOTE: expecting that Method Arguments ONLY have the attributes '@name', '@type', and '@direction'
        if raw__method_argument__attribute == "@name":
            if dbg != 0:
                print("[*] Method Argument Name:\t\t\t{0}".format(raw__method__argument_dict[raw__method_argument__attribute]))
            method_argument_map["Name"] = raw__method__argument_dict[raw__method_argument__attribute]
        elif raw__method_argument__attribute == "@type":
            if dbg != 0:
                print("[*] Method Argument Type:\t\t\t{0}".format(raw__method__argument_dict[raw__method_argument__attribute]))
            method_argument_map["Type"] = raw__method__argument_dict[raw__method_argument__attribute]
        elif raw__method_argument__attribute == "@direction":
            if dbg != 0:
                print("[*] Method Argument Direction:\t\t{0}".format(raw__method__argument_dict[raw__method_argument__attribute]))
            method_argument_map["Direction"] = raw__method__argument_dict[raw__method_argument__attribute]
        else:
            print("[!] Uknown Method Argument:\t{0}".format(raw__method_argument__attribute))
    # Return the Generated Single Method Argument Map
    return method_argument_map

# Function for Enumeratin a given D-Bus Interface Method Argument List and Return a Method Argument Map
def enumerate_and_return__dbus__method__multi_argument_map(raw__method__argument_list):
    if dbg != 0:
        print("[*] Returning [ Single Method Argument Map ] from Provided Data [ {0} ]".format(raw__method__argument_list))
    ## TODO: Finish cleaning up this code for the dictionary scenario
    # Create variable for a single argument
    #method_argument_map = {}
    # Create variable for the Method's List of Arguments
    list_of_arguments = []
    # Loop through the Method Arguments
    for raw__method__argument_dict in raw__method__argument_list:
        '''
        if sub_element__interface__method__arg_attribute == "@name":
            if dbg != 0:
                print("\t\t\t\tSub-Interface Method Argument Name:\t{0}".format(sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]))
            # Add the name of the Argument to the List of Arguments
            #list_of_arguments.append(sub_element__interface__method__arg[sub_element__interface__method__arg_attribute])
            # Add the name of the Argument to the Single Argument Map
            method_argument_map["Name"] = sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]
        elif sub_element__interface__method__arg_attribute == "@type":
            if dbg != 0:
                print("\t\t\t\tSub-Interface Method Argument Type:\t{0}".format(sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]))
            # Add the type of the Argument to the Single Argument Map
            method_argument_map["Type"] = sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]
        elif sub_element__interface__method__arg_attribute == "@direction":
            if dbg != 0:
                print("\t\t\t\tSub-Interface Method Argument Direction:\t{0}".format(sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]))
            # Add the direction of the Argument to the Single Argument Map
            method_argument_map["Direction"] = sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]
        else:
            print("[!] Unknown Sub-Interface Method Argument Attribute:\t{0}".format(sub_element__interface__method__arg_attribute))
        '''
        # Call the Function for Returning a Method Argument Map from an Argument Dictionary
        method_argument_map = enumerate_and_return__dbus__method__single_argument_map(raw__method__argument_dict)
        # Add the Method Argument Map to the List of Arguments
        list_of_arguments.append(method_argument_map)
    # Return the Generated Single Method Argument Map
    return list_of_arguments

# Function for Enumerating a D-Bus Interface Method Dictionary and Return a Single Method Map
def enumerate_and_return__dbus__single_method_map(raw__method_dict):
    if dbg != 0:
        print("[*] Returning [ Single Method Map ] from Provided Data [ {0} ]".format(raw__method_dict))
    # Create variable for tracking the Single Method Map
    single_method_map = {}
    # Create variable for tracking the List of Arguments
    list_of_arguments = []
    # Loop through to contents of the raw Method Dictionary; NOTE: Expecting an "@name" and "arg" sub-fields
    for raw__method_attribute in raw__method_dict:
        # Check if the attribute is '@name'
        if raw__method_attribute == "@name":
            if dbg != 0:
                print("[*] Method Name:\t\t\t{0}".format(raw__method_dict[raw__method_attribute]))
            single_method_map["Name"] = raw__method_dict[raw__method_attribute]
        # Check if the attribute is 'arg'
        if raw__method_attribute == "arg":
            if dbg != 0:
                print("[*] Method Argument(s):\t\t{0}".format(raw__method_dict[raw__method_attribute]))
            # NOTE: Assumption is that NO MATTER WHAT create a LIST of Arguments; even if only one
            ## Check if the arguments are a LIST of a DICTIONARY
            if isinstance(raw__method_dict[raw__method_attribute], dict):
                ## Code for Examining a Method Attribute Dict
                if dbg != 0:
                    print("[!] Method Argument(s) is a Dictionary!")
                '''
                # Create variable for tracking the Method Argument Map
                method_argument_map = {}
                # Loop through the Method Arguments
                for raw__method_attribute__argument in raw__method_dict[raw__method_attribute]:
                    # NOTE: Expecting that Method Arguments only have the attributes '@name', '@type', and '@direction'
                    if raw__method_attribute__argument == "@name":
                        if dbg != 0:
                            print("[*] Method Argument Name:\t\t\t{0}".format(raw__method_dict[raw__method_attribute][raw__method_attribute__argument]))
                        method_argument_map["Name"] = raw__method_dict[raw__method_attribute][raw__method_attribute__argument]
                    elif raw__method_attribute__argument == "@type":
                        if dbg != 0:
                            print("[*] Method Argument Type:\t\t\t{0}".format(raw__method_dict[raw__method_attribute][raw__method_attribute__argument]))
                        method_argument_map["Type"] = raw__method_dict[raw__method_attribute][raw__method_attribute__argument]
                    elif raw__method_attribute__argument == "@direction":
                        if dbg != 0:
                            print("[*] Method Argument Direction:\t\t{0}".format(raw__method_dict[raw__method_attribute][raw__method_attribute__argument]))
                        method_argument_map["Direction"] = raw__method_dict[raw__method_attribute][raw__method_attribute__argument]
                    else:
                        print("[!] Uknown Method Argument:\t{0}".format(raw__method_attribute__argument))
                '''
                ## Call to Function for Returning a Map of the Arguments
                method_argument_map = enumerate_and_return__dbus__method__single_argument_map(raw__method_dict[raw__method_attribute])
                # Add the Single Method Arguments Map to the List of Arguments
                list_of_arguments.append(method_argument_map)
            elif isinstance(raw__method_dict[raw__method_attribute], list):
                ## Code for Examining a Method Attribute List
                #print("[!!] This function is NOT configured to deal with LISTs.... Recall with each content of the list")
                if dbg != 0:
                    print("Arguments are presented as a LIST")
                # Loop thorugh the List of Arguments Presented
                for method_argument_entry in raw__method_dict[raw__method_attribute]:
                    if dbg != 0:
                        print("[*] Method Argument Entry:\t{0}".format(method_argument_entry))
                    ## Call to Function for Returning a Map of the Arguments
                    method_argument_map = enumerate_and_return__dbus__method__single_argument_map(method_argument_entry)
                    # Add Single Argument Map to the List of Arguments
                    list_of_arguments.append(method_argument_map)
                #list_of_arguments = enumerate_and_return__dbus__method__multi_argument_map(raw__method_dict[raw__method_attribute])
            else:
                print("[!] Unknown Method Attribute:\t{0}".format(raw__method_dict[raw__method_attribute]))
            # Add the generated List of Arguments to the Single Method Map
            single_method_map["Arguments"] = list_of_arguments
    if dbg != 0:
        print("[+] Completed Single Method Map:\t[ {0} ]".format(single_method_map))
    # Return the constructed Single Method Map
    return single_method_map

# Function for Enumerating a given D-Bus Interface Property and Return a Single Property Map
def enumerate_and_return__dbus__single_property_map(raw__property_dict):
    if dbg != 0:
        print("[*] Returning [ Single Property Map ] from Provided Data [ {0} ]".format(raw__property_dict))
    # Create variable for a single property
    single_property_map = {}
    for raw__property_attribute in raw__property_dict:
        # Note: Assumption is that a property has ONLY the attributes '@name', '@type', and '@access'
        if raw__property_attribute == "@name":
            if dbg != 0:
                print("\t\t\t\tSub-Interface Property Name:\t{0}".format(raw__property_dict[raw__property_attribute]))
            # Add name of property to the List of Properties
            #list_of_properties.append(raw__property_dict[raw__property_attribute])
            # Add name of the property to the Single Property Map
            single_property_map["Name"] = raw__property_dict[raw__property_attribute]
        elif raw__property_attribute == "@type":
            if dbg != 0:
                print("\t\t\t\tSub-Interface Property Type:\t{0}".format(raw__property_dict[raw__property_attribute]))
            # Add type of the property to the Single Property Map
            single_property_map["Type"] = raw__property_dict[raw__property_attribute]
        elif raw__property_attribute == "@access":
            if dbg != 0:
                print("\t\t\t\tSub-Interface Property Access:\t{0}".format(raw__property_dict[raw__property_attribute]))
            # Add access of the property to the Single Property Map
            single_property_map["Access"] = raw__property_dict[raw__property_attribute]
        else:
            print("[!] Unknown Sub-Interface Property Attribute:\t{0}".format(raw__property_attribute))
    # Return the Generated Interface Property Map
    return single_property_map

# Function for Pretty Printing D-Bus Introspection XML Data
# - Note: Might be unique to Device Introspection XML Data; noticed that service__dictionary_data only has nodes as node information
def pretty_print__introspect__dict(introspect_xml__dict):
    if dbg != 0:
        print("-------------------------------------------------------")
    # Generate the Introspected Object Map
    introspected_object__map = {}
    # Create a Default Shape to the Introspected Object Map
    introspected_object__map = {
            "Object Name": None,
            "Interfaces": [],
            #"Signals": [],
            #"Properties": [],
            "Nodes": []
            }
    for introspected_object in introspect_xml__dict:
        if dbg != 0:
            print("Introspected Object (Root Node):\t{0}".format(introspected_object))
        ## TODO: Update code to capture the D-Bus Introspected Object Node's Name (IF IT EXISTS)
        for sub_element__object in introspect_xml__dict[introspected_object]:
            if dbg != 0:
                print("\tSub-Element Object:\t{0}".format(sub_element__object))
            number_of_sub_elements = len(introspect_xml__dict[introspected_object][sub_element__object])
            # Variables used for creating the introspected object's map
            interface__map = {}
            node__map = {}
            if sub_element__object == "interface":
                if dbg != 0:
                    print("[!] Examining an INTERFACE object:\t{0}".format(sub_element__object))
                # Create variable for tracking the List of Interfaces
                list_of_interfaces = []
                for sub_element__interface in introspect_xml__dict[introspected_object][sub_element__object]:
                    if dbg != 0:
                        print("\t\tSub-Element:\t{0}".format(sub_element__interface))
                    # Create the variable for a single interface
                    single_interface_map = {}
                    for sub_element__interface__attribute in sub_element__interface:
                        if dbg != 0:
                            print("\t\t\tSub-Interface Attribute:\t{0}\t\t\tValue:\t{1}".format(sub_element__interface__attribute, sub_element__interface[sub_element__interface__attribute]))
                        ## Create variables that wil be used for tracking Interface information
                        # Create variable for tracking the List of Signals
                        list_of_signals = []
                        # Create variable for tracking the List of Methods
                        list_of_methods = []
                        # Create variable for tracking the List of Properties
                        list_of_properties = []
                        # Case where the D-Bus Interface has a Name Type attribute
                        if sub_element__interface__attribute == "@name":
                            if dbg != 0:
                                print("\t\tSub-Interface Name:\t{0}".format(sub_element__interface[sub_element__interface__attribute]))
                            # Add the names of the interfaces to the List of Interfaces     | NOTE: Ideally this should be done so that EACH appended interface is a FULL MAP of that specific interface
                            #list_of_interfaces.append(sub_element__interface[sub_element__interface__attribute])
                            # Add the name of the Interface to the Single Interface Map
                            single_interface_map["Name"] = sub_element__interface[sub_element__interface__attribute]
                        # Case where the D-Bus Interface has a Method Type attribute
                        elif sub_element__interface__attribute == "method":
                            if dbg != 0:
                                print("\t\t\tSub-Interface Methods:\t{0}".format(sub_element__interface[sub_element__interface__attribute]))
                            if dbg != 0:
                                print("[?] The Sub-Interface Methods are Presented as a Type:\t{0}".format(type(sub_element__interface[sub_element__interface__attribute])))
                            # Check which type of Method information is presented as
                            if isinstance(sub_element__interface[sub_element__interface__attribute] , list):
                                '''
                                # Code for handling multiple METHODs for a D-Bus Interface
                                for sub_element__interface__method in sub_element__interface[sub_element__interface__attribute]:
                                    if dbg != 1:
                                        print("Sub-Interface Method Summary:\t{0}".format(sub_element__interface__method))
                                    # Create the variable for a single method
                                    single_method_map = {}
                                    for sub_element__interface__method_attribute in sub_element__interface__method:
                                        if dbg != 0:
                                            print("Sub-Interface Method Attribute:\t{0}".format(sub_element__interface__method_attribute))
                                        # Create variable for tracking the List of Arguments
                                        list_of_arguments = []
                                        if sub_element__interface__method_attribute == "@name":
                                            print("\t\t\tSub-Interface Method Name:\t{0}".format(sub_element__interface__method[sub_element__interface__method_attribute]))
                                            # Add the name of the Method to the List of Methods
                                            #list_of_methods.append(sub_element__interface__method[sub_element__interface__method_attribute])
                                            # Add the name of the Method to the Single Method Map
                                            single_method_map["Name"] = sub_element__interface__method[sub_element__interface__method_attribute]
                                        elif sub_element__interface__method_attribute == "arg":
                                            if dbg != 0:
                                                print("\t\t\tSub-Interface Method Arguments:\t{0}".format(sub_element__interface__method[sub_element__interface__method_attribute]))
                                            if isinstance(sub_element__interface__method[sub_element__interface__method_attribute], list):
                                                for sub_element__interface__method__arg in sub_element__interface__method[sub_element__interface__method_attribute]:
                                                    if dbg != 0:
                                                        print("Sub-Interface Method Arguments Elements Summary:\t{0}".format(sub_element__interface__method__arg))      # NOTE: This is just the Argument Name/Type/Direction
                                                    # Create variable for a single argument
                                                    single_argument_map = {}
                                                    for sub_element__interface__method__arg_attribute in sub_element__interface__method__arg:
                                                        if sub_element__interface__method__arg_attribute == "@name":
                                                            if dbg != 0:
                                                                print("\t\t\t\tSub-Interface Method Argument Name:\t{0}".format(sub_element__interface__method__arg[sub_element__interface__method__arg_attribute]))
                                                            # Add the name of the Argument to the List of Arguments
                                                            #list_of_arguments.append(sub_element__interface__method__arg[sub_element__interface__method__arg_attribute])
                                                            # Add the name of the Argument to the Single Argument Map
                                                            single_argument_map["Name"] = sub_element__interface__method__arg[sub_element__interface__method__arg_attribute]
                                                        elif sub_element__interface__method__arg_attribute == "@type":
                                                            if dbg != 0:
                                                                print("\t\t\t\tSub-Interface Method Argument Type:\t{0}".format(sub_element__interface__method__arg[sub_element__interface__method__arg_attribute]))
                                                            # Add the type of the Argument to the Single Argument Map
                                                            single_argument_map["Type"] = sub_element__interface__method__arg[sub_element__interface__method__arg_attribute]
                                                        elif sub_element__interface__method__arg_attribute == "@direction":
                                                            if dbg != 0:
                                                                print("\t\t\t\tSub-Interface Method Argument Direction:\t{0}".format(sub_element__interface__method__arg[sub_element__interface__method__arg_attribute]))
                                                            # Add the direction of the Argument to the Single Argument Map
                                                            single_argument_map["Direction"] = sub_element__interface__method__arg[sub_element__interface__method__arg_attribute]
                                                        else:
                                                            print("[!] Unknown Sub-Interface Method Argument Attribute:\t{0}".format(sub_element__interface__method__arg_attribute))
                                                    # Add the Single Argument Map to the List of Arguments
                                                    list_of_arguments.append(single_argument_map)
                                                #if dbg != 1:
                                                #    print("List of Args:\t{0}\nSingle Method Map:\t{1}".format(list_of_arguments, single_method_map))
                                                #single_method_map["Arguments"] = list_of_arguments
                                            elif isinstance(sub_element__interface__method[sub_element__interface__method_attribute], dict):
                                                if dbg != 0:
                                                    print("Arguments are presented as a DICTIONARY")
                                                ## TODO: Finish cleaning up this code for the dictionary scenario
                                                # Create variable for a single argument
                                                single_argument_map = {}
                                                for sub_element__interface__method__arg_attribute in sub_element__interface__method[sub_element__interface__method_attribute]:
                                                    if sub_element__interface__method__arg_attribute == "@name":
                                                        if dbg != 0:
                                                            print("\t\t\t\tSub-Interface Method Argument Name:\t{0}".format(sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]))
                                                        # Add the name of the Argument to the List of Arguments
                                                        #list_of_arguments.append(sub_element__interface__method__arg[sub_element__interface__method__arg_attribute])
                                                        # Add the name of the Argument to the Single Argument Map
                                                        single_argument_map["Name"] = sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]
                                                    elif sub_element__interface__method__arg_attribute == "@type":
                                                        if dbg != 0:
                                                            print("\t\t\t\tSub-Interface Method Argument Type:\t{0}".format(sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]))
                                                        # Add the type of the Argument to the Single Argument Map
                                                        single_argument_map["Type"] = sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]
                                                    elif sub_element__interface__method__arg_attribute == "@direction":
                                                        if dbg != 0:
                                                            print("\t\t\t\tSub-Interface Method Argument Direction:\t{0}".format(sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]))
                                                        # Add the direction of the Argument to the Single Argument Map
                                                        single_argument_map["Direction"] = sub_element__interface__method[sub_element__interface__method_attribute][sub_element__interface__method__arg_attribute]
                                                    else:
                                                        print("[!] Unknown Sub-Interface Method Argument Attribute:\t{0}".format(sub_element__interface__method__arg_attribute))
                                                # Add the Single Argument Map to the List of Arguments
                                                list_of_arguments.append(single_argument_map)
                                            else:
                                                print("[!] Unknown Type used for Sub-Interface Method Arguments:\t{0}\tType:\t{1}".format(sub_element__interface__method[sub_element__interface__method_attribute],type(sub_element__interface__method[sub_element__interface__method_attribute])))
                                            if dbg != 0:
                                                print("List of Args:\t{0}\nSingle Method Map:\t{1}".format(list_of_arguments, single_method_map))
                                            single_method_map["Arguments"] = list_of_arguments

                                        else:
                                            print("[!] Unknown Sub-Interface Method Attribute:\t{0}".format(sub_element__interface__method_attribute))
                                    #list_of_methods.append(single_method_map)
                                '''
                                ## Testing for Function Calls to Repeat the Above
                                # Loop through the individual dictionaries within the list
                                for sub_element__interface__method in sub_element__interface[sub_element__interface__attribute]:
                                    if dbg != 0:
                                        print("Sub-Interface Method Summary:\t{0}".format(sub_element__interface__method))
                                    ## Code for handling multiple METHODs for a D-Bus Interface
                                    # Call Function to Process each Method (Dictionary Format) and return the Single Method Map
                                    single_method_map = enumerate_and_return__dbus__single_method_map(sub_element__interface__method)
                                    if dbg != 0:
                                        print("-------\n[?] Single Method Map:\t{0}\n[?] O.G. Data:\t{1}\n-------".format(single_method_map, sub_element__interface__method))
                                    # Add the Single Method Map to the List of Methods
                                    list_of_methods.append(single_method_map)
                            elif isinstance(sub_element__interface[sub_element__interface__attribute], dict):
                                if dbg != 0:
                                    print("[!] Dictionary type Method Presented")
                                    print("High Level Data Set to Manipulate:\t{0}".format(sub_element__interface[sub_element__interface__attribute]))
                                ## Code for handling single METHOD for a D-Bus Interface
                                # Call Function to Process the Method (Dictionary Format) and return the Single Method Map
                                single_method_map = enumerate_and_return__dbus__single_method_map(sub_element__interface[sub_element__interface__attribute])
                                # Add the Single Method Map to the List of Methods
                                list_of_methods.append(single_method_map)
                            else:
                                print("[!] Unknown Type used for Presenting Method(s):\t{0}\tType:{1}".format(sub_element__interface[sub_element__interface__attribute], type(sub_element__interface[sub_element__interface__attribute])))
                        # Case where the D-Bus Interface has a Property Type attribute
                        elif sub_element__interface__attribute == "property":
                            if dbg != 0:
                                print("\t\t\tSub-Interface Properties:\t{0}".format(sub_element__interface[sub_element__interface__attribute]))
                            ## Code for interpreting multiple properties
                            for sub_element__interface__property in sub_element__interface[sub_element__interface__attribute]:
                                if dbg != 0:
                                    print("Sub-Interface Property Summary:\t{0}".format(sub_element__interface__property))
                                '''
                                # Create variable for a single property
                                single_property_map = {}
                                for sub_element__interface__property_attribute in sub_element__interface__property:
                                    if sub_element__interface__property_attribute == "@name":
                                        if dbg != 0:
                                            print("\t\t\t\tSub-Interface Property Name:\t{0}".format(sub_element__interface__property[sub_element__interface__property_attribute]))
                                        # Add name of property to the List of Properties
                                        #list_of_properties.append(sub_element__interface__property[sub_element__interface__property_attribute])
                                        # Add name of the property to the Single Property Map
                                        single_property_map["Name"] = sub_element__interface__property[sub_element__interface__property_attribute]
                                    elif sub_element__interface__property_attribute == "@type":
                                        if dbg != 0:
                                            print("\t\t\t\tSub-Interface Property Type:\t{0}".format(sub_element__interface__property[sub_element__interface__property_attribute]))
                                        # Add type of the property to the Single Property Map
                                        single_property_map["Type"] = sub_element__interface__property[sub_element__interface__property_attribute]
                                    elif sub_element__interface__property_attribute == "@access":
                                        if dbg != 0:
                                            print("\t\t\t\tSub-Interface Property Access:\t{0}".format(sub_element__interface__property[sub_element__interface__property_attribute]))
                                        # Add access of the property to the Single Property Map
                                        single_property_map["Access"] = sub_element__interface__property[sub_element__interface__property_attribute]
                                    else:
                                        print("[!] Unknown Sub-Interface Property Attribute:\t{0}".format(sub_element__interface__property_attribute))
                                '''
                                # Call to Function for Processing the Arguments for a Property
                                single_property_map = enumerate_and_return__dbus__single_property_map(sub_element__interface__property)
                                # Add the Single Property Map to the List of Properties
                                list_of_properties.append(single_property_map)
                        # Case where the D-Bus Interface has a Signal Type attribute
                        elif sub_element__interface__attribute == "signal":
                            # NOTE: The code below MAY need to be updated due to how the "signal" attribute is handled (e.g. one element vs. a list; assumed one element)
                            if dbg != 0:
                                print("\t\t\tSub-Interface Signal:\t{0}".format(sub_element__interface[sub_element__interface__attribute]))
                            # Create variable for tracking the List of Signals
                            #list_of_signals = []
                            # Create variable for a single signal
                            single_signal_map = {}
                            for sub_element__interface__signal_attribute in sub_element__interface[sub_element__interface__attribute]:
                                if dbg != 0:
                                    print("Sub-Interface Signal Attribute:\t{0}".format(sub_element__interface__signal_attribute))
                                # Signal Name attribute
                                if sub_element__interface__signal_attribute == "@name":
                                    if dbg != 0:
                                        print("\t\t\tSub-Interface Signal Name:\t{0}".format(sub_element__interface[sub_element__interface__attribute][sub_element__interface__signal_attribute]))
                                    # Add name of the signal to the Single Signal Map
                                    single_signal_map["Name"] = sub_element__interface[sub_element__interface__attribute][sub_element__interface__signal_attribute]
                                # Signal Arg attribute
                                elif sub_element__interface__signal_attribute == "arg":
                                    if dbg != 0:
                                        print("\t\t\tSub-Interface Signal Arguments:\t{0}".format(sub_element__interface[sub_element__interface__attribute][sub_element__interface__signal_attribute]))
                                    # Create variable for the List of Arguments
                                    list_of_arguments = []
                                    for sub_element__interface__signal__arg in sub_element__interface[sub_element__interface__attribute][sub_element__interface__signal_attribute]:
                                        if dbg != 0:
                                            print("\t\t\t\t\tSub-Interface Signal Arguments Element:\t{0}".format(sub_element__interface__signal__arg))
                                        # Create variable for a single argument for the signal
                                        single_argument_map = {}
                                        for sub_element__interface__signal__arg_attribute in sub_element__interface__signal__arg:
                                            if dbg != 0:
                                                print("Sub-Interface Signal Argument Element Attribute:\t{0}".format(sub_element__interface__signal__arg_attribute))
                                                print("Sub-Interface Signal Argument Element Attribute Value:\t{0}".format(sub_element__interface__signal__arg[sub_element__interface__signal__arg_attribute]))
                                            # Signal Argument Name
                                            if sub_element__interface__signal__arg_attribute == "@name":
                                                if dbg != 0:
                                                    print("\t\t\t\t\tSub-Interface Signal Argument Element Name:\t{0}".format(sub_element__interface__signal__arg[sub_element__interface__signal__arg_attribute]))
                                                # Add name to the Single Signal Map
                                                single_argument_map["Name"] = sub_element__interface__signal__arg[sub_element__interface__signal__arg_attribute]
                                            # Signal Argument Signature
                                            # NOTE: This is the "D-BUS SIGNATURE" that represents the type of data that one should receive from the given D-BUS INTERFACE SIGNAL
                                            elif sub_element__interface__signal__arg_attribute == "@type":
                                                if dbg != 0:
                                                    print("\t\t\t\t\tSub-Interface Signal Argument Element Type (Signature):\t{0}".format(sub_element__interface__signal__arg[sub_element__interface__signal__arg_attribute]))
                                                # Add type to the Single Signal Map
                                                single_argument_map["Type"] = sub_element__interface__signal__arg[sub_element__interface__signal__arg_attribute]
                                            else:
                                                print("[!] Unknown Sub-Interface Signal Argument Element Attribute:\t{0}".format(sub_element__interface__signal__arg_attribute))
                                        # Add the Single Signal Map to the List of Arguments
                                        list_of_arguments.append(single_argument_map)
                                    # Add the List of Arguments to the Single Signal Map
                                    single_signal_map["Arguments"] = list_of_arguments
                                else:
                                    print("[!] Unknown Sub-Interface Signal Attribute:\t{0}".format(sub_element__interface__signal_attribute))
                                if dbg != 0:
                                    print("Single Signal Map:\t{0}\n\tList of Signals:\t{1}".format(single_signal_map, list_of_signals))
                            # Add the Single Signal Map to the List of Signals
                            list_of_signals.append(single_signal_map)
                        else:
                            print("[!] Unknown Sub-Interface Attribute:\t{0}".format(sub_element__interface__attribute))
                        ## Adding the elements to the Single Interface Map ONLY IF THEY EXIST!
                        if list_of_signals != []:
                            # Add the List of Signals to the Single Interface Map
                            single_interface_map["Signals"] = list_of_signals
                        if list_of_properties != []:
                            # Add the List of Properties to the Single Interface Map
                            single_interface_map["Properties"] = list_of_properties
                        if list_of_methods != []:
                            # Add the List of Methods to the Single Interface Map
                            single_interface_map["Methods"] = list_of_methods
                    ## TODO: Add the single interface map to the List of Interfaces
                    list_of_interfaces.append(single_interface_map)
                interface__map = {"Interfaces": list_of_interfaces}
                if dbg != 0:
                    print("[?] Testing to establish the map:\n\tInterface Map:\t{0}\n\tList of Interfaces:\t{1}".format(interface__map, list_of_interfaces))
                # Update entry in map for the Interfaces
                introspected_object__map.update(interface__map)
            elif sub_element__object == "node":
                if dbg != 0:
                    print("[!] Examining a NODE object:\t{0}".format(sub_element__object))
                # Create a List of Nodes for any 'node' objects examined
                list_of_nodes = []
                ## Check to see if the nodes are a list (multiple) or a dictionary (single)
                if isinstance(introspect_xml__dict[introspected_object][sub_element__object], list):
                    # Dissect node entires information
                    for sub_element__node in introspect_xml__dict[introspected_object][sub_element__object]:
                        if dbg != 0:
                            print("\t\tSub-Element:\t{0}".format(sub_element__node))
                        for sub_element__node__attribute in sub_element__node:
                            if dbg != 0:
                                print("\t\t\tSub-Node Attribute:\t{0}".format(sub_element__node__attribute))
                            if sub_element__node__attribute == "@name":
                                if dbg != 0:
                                    print("[!] Found a Sub-Node '@name' Attribute:\t{0}".format(sub_element__node__attribute))
                                    print("Sub-Node Attribute:\t{0}\t\t\tValue:\t{1}".format(sub_element__node__attribute, sub_element__node[sub_element__node__attribute]))
                                if dbg != 0:
                                    print("\t\t\tSub-Node Name:\t\t{0}".format(sub_element__node[sub_element__node__attribute]))
                                # Add each sub-element name to the List of Nodes
                                list_of_nodes.append(sub_element__node[sub_element__node__attribute])
                elif isinstance(introspect_xml__dict[introspected_object][sub_element__object], dict):
                    # Dissect node entry information
                    for sub_element__node__attribute in introspect_xml__dict[introspected_object][sub_element__object]:
                        if dbg != 0:
                            print("\t\tSub-Element:\t{0}".format(sub_element__node__attribute))
                        if sub_element__node__attribute == "@name":
                            if dbg != 0:
                                print("Sub-Node Attribute\t{0}\t\t\tValue:\t{1}".format(sub_element__node__attribute, introspect_xml__dict[introspected_object][sub_element__object][sub_element__node__attribute]))
                            # Add each sub-element name to the List of Nodes
                            list_of_nodes.append(introspect_xml__dict[introspected_object][sub_element__object][sub_element__node__attribute])
                node__map = {"Nodes" : list_of_nodes}
            else:
                print("[!] Unknown Sub-Element object:\t{0}".format(sub_element__object))
            if dbg != 0:
                print("Sub-Information:\t{0}".format(introspect_xml__dict[introspected_object][sub_element__object]))
            # Update entry in map for the Nodes
            introspected_object__map.update(node__map)
        # Update the top level Introspected Object Map
        #introspected_object__map.update(interface__map)
        #introspected_object__map.update(node__map)
    if dbg != 0:
        print("-------------------------------------------------------")
    if dbg != 0:
        print("[?] Introspect Map:\t{0}".format(introspected_object__map))
    return introspected_object__map

# Function for Creating and Returning an Introspection Map of the Device Interface (of a given Device Object)
def create_and_return__introspection_map__device(device_object):
    # Create the D-Bus INTROSPECTION Map for a given DEVICE OBJECT
    device_introspection = device_object.device_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
    introspect_xml = bluetooth_utils.dbus_to_python(device_introspection)
    dictionary_data = xmltodict.parse(introspect_xml)
    introspect_map = pretty_print__introspect__dict(dict_data)
    # Return the Introspection Map
    return introspect_map

# Function for Creating and Returning an Introspection Map of the Service Interface (of a given Device Object)
def create_and_return__introspection_map__service(device_object, service_name):
    # Create the D-Bus INTROSPECTION Map for a given SERVICE name
    service_path, service_object, service_interface, service_properties, service_introspection = device_object.create_and_return__service__gatt_inspection_set(service_name)
    service__introspect_xml = bluetooth_utils.dbus_to_python(service_introspection)
    service__dict_data = xmltodict.parse(service__introspect_xml)
    service__introspect__map = pretty_print__introspect__dict(service__dict_data)
    # Return the Introspection Map
    return service__introspect__map

# Function for Creating and Returning an Introspection Map of the Characteristic Interface (of a given Device Object)
def create_and_return__introspection_map__characteristic(device_object, parent_service__path, characteristic_name):
    # Create the D-Bus INTROSPECTION Map for a given CHARACTERISTIC name
    characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = device_object.create_and_return__characteristic__gatt_inspection_set(parent_service__path, characteristic_name)
    characteristic__introspect_xml = bluetooth_utils.dbus_to_python(characteristic_introspection)
    characteristic__dict_data = xmltodict.parse(characteristic__introspect_xml)
    characteristic__introspect__map = pretty_print__introspect__dict(characteristic__dict_data)
    # Return the Introspection Map
    return characteristic__introspect__map

# Function for Creating and Returning an Introspection Map of the Descriptor Interface (of a given Device Object)
def create_and_return__introspection_map__descriptor(device_object, parent_characteristic__path, descriptor_name):
    # Create the D-Bus INTROSPECTION Map for a given DESCRIPTOR name
    descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = device_object.create_and_return__descriptor__gatt_inspection_set(parent_characteristic__path, descriptor_name)
    descriptor__introspect_xml = bluetooth_utils.dbus_to_python(descriptor_introspection)
    descriptor__dict_data = xmltodict.parse(descriptor__introspect_xml)
    descriptor__introspect__map = pretty_print__introspect__dict(descriptor__dict_data)
    # Return the Introspection Map
    return descriptor__introspect__map

# Function for Finding and Returning a List of Services associated with a given Device Object
def find_and_return__introspection_map__device_interface__services(device_object):
    # Create the Introspection Map for the Device Object
    device__introspection_map = create_and_return__introspection_map__device(device_object)
    # Return the "Nodes" of the Device, which are the Services of the Device
    return device__introspection_map["Nodes"]

# Function for Finding and Returning a List of Characteristics associated with a given Device Object's Service
def find_and_return__introspection_map__service_interface__characteristics(device_object, service_name):
    # Create the Introspection Map for the Device Object Service
    service__introspection_map = create_and_return__introspection_map__service(device_object, service_name)
    # Return the "Nodes" of the Service, which are the Characteristics of the Service
    return service__introspection_map["Nodes"]

# Function for Finding and Returning a List of Descriptors associated with a given Device Object's Service's Characteristic
def find_and_return__introspection_map__characteristic_interface__descriptors(device_object, parent_service_name, characteristic_name):
    # Create the Introspection Map for the Device Object Service Characteristic
    parent_service__path = device_object.device_path + "/" + parent_service_name
    characteristic__introspection_map = create_and_return__introspection_map__characteristic(device_object, parent_service__path, characteristic_name)
    # Return the "Nodes" of the Characteristic, which are the Descriptors of the Characteristic
    return characteristic__introspection_map["Nodes"]

# Function for Finding and Returning Information for any given Service Name
def find_and_return__introspection_map__service_info(device_object, service_name):
    print("[*] Collecting information for the service [ {0} ]".format(service_name))
    service_introspection_map = create_and_return__introspection_map__service(device_object, service_name)
    print("[+] Returning collected information")
    return service_introspection_map

# Function for Finding and Returning Information for any given Characteristic Name
def find_and_return__introspection_map__characteristic_info(device_object, characteristic_name):
    print("[*] Collecting information for the characteristic [ {0} ]".format(characteristic_name))
    # Create an empty variable to allow for later debug testing
    characteristic_introspection_map = None
    # Loop through the found services to see which has the correct Characteristic Name
    list_of_services = find_and_return__introspection_map__device_interface__services(device_object)
    for service_name in list_of_services:
        list_of_characteristics = find_and_return__introspection_map__service_interface__characteristics(device_object, service_name)
        # Check to see if the Characteristic Name is in the List of Characteristics
        if characteristic_name in list_of_characteristics:
            # Create the sub-varibale(s) required to generate the intropsect map
            parent_service__path = device_object.device_path + "/" + service_name
            # Generate the introspection map for the given Characteristic Name
            characteristic_introspection_map = create_and_return__introspection_map__characteristic(device_object, parent_service__path, characteristic_name)
    print("[+] Returning collected information")
    return characteristic_introspection_map

# Function for Finding and Returning Information for any given Descriptor Name
def find_and_return__introspection_map__descriptor_info(device_object, descriptor_name):
    print("[*] Collecting information for the descriptor [ {0} ]".format(descriptor_name))
    # Create an empty variable to allow for later debug testing
    descriptor_introspection_map = None
    list_of_services = find_and_return__introspection_map__device_interface__services(device_object)
    for service_name in list_of_services:
        list_of_characteristics = find_and_return__introspection_map__service_interface__characteristics(device_object, service_name)
        for characteristic_name in list_of_characteristics:
            list_of_descriptors = find_and_return__introspection_map__characteristic_interface__descriptors(device_object, service_name, characteristic_name)
            # Check to see if the Decsriptor Name is in the List of Descriptors
            if descriptor_name in list_of_descriptors:
                # Create the sub-variable(s) required to generate the introspect map
                parent_characteristic__path = device_object.device_path + "/" + service_name + "/" + characteristic_name
                # Generate the introspection map for the given Descriptor Name
                descriptor_intropsection_map = create_and_return__introspection_map__descriptor(device_object, parent_characteristic__path, descriptor_name)
    print("[+] Returning collected information")
    return descriptor_introspection_map

# Function for Finding and Returning the High Level Structure of the provided D-Bus Devuce (Interface) Object
#   - Note: Expected highest level for an INTROSPECTION MAP is { 'Object Name', 'Interfaces', 'Nodes' }
def find_and_return__introspection_map__high_level_map(device_object):
    print("[*] Producing a High-Level Map of the Introspection Interface")
    high_level_map = {}
    # Set the origin point for the high level map
    high_level_map["Origin"] = device_object.device_path
    ## TODO: Determine what the input to this function should be
    #   -> Ideally want to know (1) Nodes + Sub-Nodes of the interface & (2) Interfaces for each node
    # Create the preliminary variables required to begin the dive to generate the high-level map
    introspection_map__device = create_and_return__introspection_map__device(device_object)
    # Grab the highest level of the Inteface Map
    for introspection_map__section in introspection_map__device:
        # Gather the Interfaces information for the current level
        if introspection_map__section == "Interfaces":
            interface_list = []
            for interface_element in introspection_map__device[introspection_map__section]:
                interface_name = interface_element["Name"]
                interface_list.append(interface_name)
            # Add the new list of interfaces to the high-level map
            high_level_map["Interfaces"] = interface_list
            ## TODO: Create system for putting the Interfaces into the High Level Map
        # Gather the Services information for the current introspection map
        elif introspection_map__section == "Nodes":
            node_list = []
            for node_element in introspection_map__device[introspection_map__section]:
                node_list.append(node_element)
            # Add the new list of nodes (services?) to the high-level map
            high_level_map["Services"] = node_list
            ## TODO: Create system for putting the Nodes into the High Level Map
    ## Service enumerating section of code
    for service_name in introspection_map__device["Nodes"]:
        # Create variables for diving the services
        introspection_map__services = create_and_return__introspection_map__service(device_object, service_name)
        characteristics_list = []
        descriptors_list = []
        # Loop through the Service Introspection Map sections
        for service_map__section in introspection_map__services:
            # Gather the Characteristics information for the current introspection map
            if service_map__section == "Nodes":
                for node_element in introspection_map__services[service_map__section]:
                    characteristics_list.append(node_element)
                ## Characteristic enumerating section of code   | ## TODO: Add into the above for loop
                for characteristic_name in introspection_map__services[service_map__section]:
                    if dbg != 0:
                        print("[?] Char:\t{0}\t\tServ:\t{1}".format(characteristic_name, service_name))
                    # Create variables for diving the characteristics
                    parent_service_path = device_object.device_path + "/" + service_name
                    introspection_map__characteristics = create_and_return__introspection_map__characteristic(device_object, parent_service_path, characteristic_name)
                    # Loop through the Characteristic Introspection Map sections
                    for characteristic_map__section in introspection_map__characteristics:
                        # Gather the Descriptors information for the current introspection map
                        if characteristic_map__section == "Nodes":
                            #print("[!] Found a Characteristic Nodes Section")
                            if introspection_map__characteristics[characteristic_map__section]:
                                #print("\tSection:\t[ {0} ]".format(introspection_map__characteristics[characteristic_map__section]))
                                for node_element in introspection_map__characteristics[characteristic_map__section]:
                                    descriptors_list.append(node_element)
                                    if dbg != 1:
                                        print("Decsriptor:\t{0}".format(node_element))
                                        print("Descriptor List:\t{0}".format(descriptors_list))
                            elif not introspection_map__characteristics[characteristic_map__section]:
                                if dbg != 0:
                                    print("[!] Empty Descriptor Node List")
        # Debugging for List Additions
        if dbg != 1:
            if characteristics_list:
                print("[!] Characteristics to be added:\t[ {0} ]".format(characteristics_list))
            if descriptors_list:
                print("[!] Descriptors to be added:\t[ {0} ]".format(descriptors_list))
        ## Adding the information to the high level map
        if "Characteristics" not in high_level_map:
            # Add the new list of nodes (characteristics?) to the high-level map
            high_level_map["Characteristics"] = characteristics_list
        else:
            # Add the new list of nodes (characteristics?) to the high-level map
            high_level_map["Characteristics"] += characteristics_list
            # Note: Have multiple ways of making this call ot have them in record; Requires the two ways because one can not "+=" to a record that does not exist yet
        if "Descriptors" not in high_level_map:
            # Add the new list of nodes (descriptors?) to the high-level map
            high_level_map["Descriptors"] = descriptors_list
        else:
            # Add the new list of nodes (descriptors?) to the high-level map
            high_level_map["Descriptors"] += descriptors_list
    # Loop for examining the sub-contents of the current interface
    print("[+] Returning the High-Level Map")
    return high_level_map

# Function for Finding and Returning a Deep Dive of Information for any "Named Node"
#   - Note: The purpose of this function is to return an 'introspection_map' level of information for a given named node (i.e. Service, Characteristic, Descriptor)
def enumerate_and_return__introspection_map__named_node__deep_dive_information(introspeciton_map, named_node__name):
    named_node__info_map = {
                "Name": named_node__name,
                "Sub-Nodes": [],
                "Details": {}
            }
    # Search through the introspection_map for the an entry with the given name (i.e. named_node__name)
    return named_node__info_map

#   Inputs:     (A) Top-level map, (B) "Named Node" Name                                                <----- Maybe change to a 'device_object' being passed, since the function calls alread exist for it?
#   Output:     (i) Listing of associated interface information (e.g. methods, properties), (ii) I/O arguments + signatures, and (iii) pretty print _i_ and _ii_
# Note: Any "Named Node" would need to be a Service/Characteristics/Descriptor
def find_and_return__introspection_map__deep_dive__named_node(device_object, named_node__name):
    if dbg != 0:
        print("[*] Performing Deep Dive of Named Node [ {0} ]".format(named_node__name))
    ## Produce a High Level Map of the Named Node interface (e.g. using same function used to produce _A_); then create list(s) of information for _i_
    top_level_map = find_and_return__introspection_map__high_level_map(device_object)
    # Create the lists of information based on the Top Level Map
    list_of_services = top_level_map["Services"]
    list_of_characteristics = top_level_map["Characteristics"]
    list_of_descriptors = top_level_map["Descriptors"]

    # Determine if the "Named Node" is a Service/Characteristic/Descriptor
    if named_node__name in list_of_services:
        if dbg != 0:
            print("[+] Named Node was found to be a Service")
        named_node__high_level_map = find_and_return__introspection_map__service_info(device_object, named_node__name)
    elif named_node__name in list_of_characteristics:
        if dbg != 0:
            print("[+] Named Node was found to be a Characteristic")
        named_node__high_level_map = find_and_return__introspection_map__characteristic_info(device_object, named_node__name)
    elif named_node__name in list_of_descriptors:
        if dbg != 0:
            print("[+] Named Node was found to be a Descriptor")
        named_node__high_level_map = find_and_return__introspection_map__descriptor_info(device_object, named_node__name)
    else:
        if dbg != 0:
            print("[-] Named Node was NOT located... Returning Nothing")
        return None

    ## Use lists created above + existing function(s) to generate greater detail on Node info; then create list(s) of information for _ii_

    ## Use data from all the previous steps to create the pretty print output (to a given output path?); thus creating the information for _iii_

    # Below are sketches for how this information might appear
    '''
        "Named Node" Name:          < Name >
        Sub Nodes:                  < Sub-node name list >
        Properties:                 < Associated properties list >
        Signals:                    < Associated signals list >
        Methods:              < Associated methods list >

        Detailed Methods Table:     Method Name | Input Signature | Otuput Signature | Inputs (Input + Signature) | Outputs (Output + Signature)

        Method Pretty Print:                ( More Detailed Version )
            Method Name:        < Name >
                Inputs:             < List of Input Names >
                    < Input Name > : < Input Signature >
                Outputs:            < List of Output Names >
                    < Output Name > : < Output Signature >
    '''

    # Determine if the "Named Node" is a Service/Characteristic/Descriptor
    if named_node__name in list_of_services:
        if dbg != 0:
            print("[+] Named Node was found to be a Service")
        named_node__high_level_map = find_and_return__introspection_map__service_info(device_object, named_node__name)
    elif named_node__name in list_of_characteristics:
        if dbg != 0:
            print("[+] Named Node was found to be a Characteristic")
        named_node__high_level_map = find_and_return__introspection_map__characteristic_info(device_object, named_node__name)
    elif named_node__name in list_of_descriptors:
        if dbg != 0:
            print("[+] Named Node was found to be a Descriptor")
        named_node__high_level_map = find_and_return__introspection_map__descriptor_info(device_object, named_node__name)
    else:
        if dbg != 0:
            print("[-] Named Node was NOT located... Returning Nothing")
        return None

    ## Use lists created above + existing function(s) to generate greater detail on Node info; then create list(s) of information for _ii_

    ## Use data from all the previous steps to create the pretty print output (to a given output path?); thus creating the information for _iii_

    # Below are sketches for how this information might appear
    '''
        "Named Node" Name:          < Name >
        Sub Nodes:                  < Sub-node name list >
        Properties:                 < Associated properties list >
        Signals:                    < Associated signals list >
        Methods:              < Associated methods list >

        Detailed Methods Table:     Method Name | Input Signature | Otuput Signature | Inputs (Input + Signature) | Outputs (Output + Signature)

        Method Pretty Print:                ( More Detailed Version )
            Method Name:        < Name >
                Inputs:             < List of Input Names >
                    < Input Name > : < Input Signature >
                Outputs:            < List of Output Names >
                    < Output Name > : < Output Signature >
    '''

'''
Sketch for Iterating through for Methods and Arguents and such

>>> for item in introspect__map["Interfaces"]:
...     print("Name:\t{0}".format(item["Name"]))
...     for method_item in item["Methods"]: 
...             print(method_item)         
...                                       
Name:   org.freedesktop.DBus.Introspectable 
{'Name': 'Introspect', 'Arguments': [{'Name': 'xml', 'Type': 's', 'Direction': 'out'}]}                                             
Name:   org.bluez.Device1                                                                                                          
{'Name': 'Disconnect'}                                                                                                            
{'Name': 'Connect'}                                                                                                              
{'Name': 'ConnectProfile', 'Arguments': [{'Name': 'UUID', 'Type': 's', 'Direction': 'in'}]}                                     
{'Name': 'DisconnectProfile', 'Arguments': [{'Name': 'UUID', 'Type': 's', 'Direction': 'in'}]}                                 
{'Name': 'Pair'}                                                                                                              
{'Name': 'CancelPairing'}                                                                                                    
Name:   org.freedesktop.DBus.Properties                                                                                     
{'Name': 'Get', 'Arguments': [{'Name': 'interface', 'Type': 's', 'Direction': 'in'}, {'Name': 'name', 'Type': 's', 'Direction': 'in'}, {'Name': 'value', 'Type': 'v', 'Direction': 'out'}]}                                                                            
{'Name': 'Set', 'Arguments': [{'Name': 'interface', 'Type': 's', 'Direction': 'in'}, {'Name': 'name', 'Type': 's', 'Direction': 'in'}, {'Name': 'value', 'Type': 'v', 'Direction': 'in'}]}                                                                              
{'Name': 'GetAll', 'Arguments': [{'Name': 'interface', 'Type': 's', 'Direction': 'in'}, {'Name': 'properties', 'Type': 'a{sv}', 'Direction': 'out'}]}

'''
# Function for Enumerating and Creating a List of All Methods for an Interface
def enumerate_and_create__introspection_map__interface__list_of_methods(introspection_map, interface_name):
    interface__list_of_methods = []
    for interface_item in introspect_map["Interfaces"]:
        if dbg != 0:
            print("[?] Interface Name:\t{0}".format(interface_item["Name"]))
        # Check if the interface item is the interface being searched for
        if interface_item["Name"] == interface_name:
            # Check that the "Methods" information exists
            try:
                # Loop through the methods under this interface
                for method_item in interface_item["Methods"]:
                    interface__list_of_methods.append(method_item["Name"])
                # Return the List of Methods from the provided interface name
                return interface__list_of_methods
            except KeyError:
                print("[-] No Methods information exists for interface [ {0} ]".format(interface_name))
            else:
                if dbg != 0:
                    print("[-] Unknown Error Occured!")
    # Assume if here that the interface was not found
    if dbg != 0:
            print("[-] Did not find the given interface [ {0} ] in the provided introspection map".format(interface_name))
    # Return the empty List of Methods; assumed nothing was found by this point
    return interface__list_of_methods

def find_and_return__introspection_map__interface_info__methods(provided__introspect_map):
    # Create variables
    list_of_methods = []
    ## Cycle thorugh the Provided Introspect Map
    for interface_item in provided__introspect_map["Interfaces"]:
        # Enumerate through each method entry
        for method_item in interface_item["Methods"]:
            # Capture the Name of each Method
            list_of_methods.append(method_item["Name"])
    # Return the list of methods
    return list_of_methods

# Function for Enumerating and Creating Detailed Information about Interface Methods
def find_and_return__introspection_map__interface_info__methods__detailed_info(provided__introspect_map):
    # Create variables
    full_methods_map = {}
    ## Cycle thorugh the Provided Introspect Map
    for interface_item in provided__introspect_map["Interfaces"]:
        # Enumerate through each method entry
        for method_item in interface_item["Methods"]:
            # Variables for tracking Method Map information
            method__map = {}
            list_of_inputs = []
            inputs__signature = ""
            list_of_outputs = []
            outputs__signature = ""
            # Capture the Name of each Method
            method__map["Name"] = method_item["Name"]
            # Iterate through the Arguments of the Method
            for argument_item in method_item["Arguments"]:
                ## Check and Capture the Argument information into the larger map
                if argument_item["Direction"] == 'in':
                    method__input_name = argument_item["Name"]
                    method__input_signature = argument_item["Type"]
                    # Capture inputs information
                    list_of_inputs.append(method__input_name)
                    inputs__signature += method__input_signature
                    method__map__input_entry = { method__input_name : method__input_signature }                 # <-----------  Note: Need to determine how to track this pairing information and bring it forward; tuples? dictionary entries? ~!~ TODO ~!~
                elif argument_item["Direction"] == 'out':
                    method__output_name = arugment_item["Name"]
                    method__output_signature = argument_item["Type"]
                    # Capture outputs information
                    list_of_outputs.append(method__output_name)
                    outputs__signature += method__output_signature
                    method__map__output_entry = { method__output_name : method__output_signature }
                else:
                    if dbg != 0:
                        print("[!] Error: Unknown Direction for Method [ {0} ] Argument [ {1} ]\t-\tDirection [ {2} ]".format(method__map["Name"], argument_item["Name"], argument_item["Direction"]))
                    # Do nothing....?
    # Return the list of methods
    return list_of_methods

# Function for Enumerating and Creating Detailed Information about Interface Methods
def find_and_return__introspection_map__interface_info__methods__detailed_info(provided__introspect_map):
    # Create variables
    full_methods_map = {}
    ## Cycle thorugh the Provided Introspect Map
    for interface_item in provided__introspect_map["Interfaces"]:
        # Enumerate through each method entry
        for method_item in interface_item["Methods"]:
            # Variables for tracking Method Map information
            method__map = {}
            list_of_inputs = []
            inputs__signature = ""
            list_of_outputs = []
            outputs__signature = ""
            # Capture the Name of each Method
            method__map["Name"] = method_item["Name"]
            # Iterate through the Arguments of the Method
            for argument_item in method_item["Arguments"]:
                ## Check and Capture the Argument information into the larger map
                if argument_item["Direction"] == 'in':
                    method__input_name = argument_item["Name"]
                    method__input_signature = argument_item["Type"]
                    # Capture inputs information
                    list_of_inputs.append(method__input_name)
                    inputs__signature += method__input_signature
                    method__map__input_entry = { method__input_name : method__input_signature }                 # <-----------  Note: Need to determine how to track this pairing information and bring it forward; tuples? dictionary entries? ~!~ TODO ~!~
                elif argument_item["Direction"] == 'out':
                    method__output_name = arugment_item["Name"]
                    method__output_signature = argument_item["Type"]
                    # Capture outputs information
                    list_of_outputs.append(method__output_name)
                    outputs__signature += method__output_signature
                    method__map__output_entry = { method__output_name : method__output_signature }
                else:
                    if dbg != 0:
                        print("[!] Error: Unknown Direction for Method [ {0} ] Argument [ {1} ]\t-\tDirection [ {2} ]".format(method__map["Name"], argument_item["Name"], argument_item["Direction"]))
                    # Do nothing....?
    # Return the list of methods
    return list_of_methods

# Function for Enumerating and Creating a List of All Properties for an Interface
def enumerate_and_create__introspection_map__interface__list_of_properties(introspection_map, interface_name):
    interface__list_of_properties = []
    for interface_item in introspect_map["Interfaces"]:
        if dbg != 0:
            print("[?] Interface Name:\t{0}".format(interface_item["Name"]))
        # Check if the interface item is the interface being searched for
        if interface_item["Name"] == interface_name:
            # Check that the "Properties" information exists
            try:
                # Loop through the properties under this interface
                for properties_item in interface_item["Properties"]:
                    interface__list_of_properties.append(properties_item["Name"])
                # Return the List of Properties from the provided interface name
                return interface__list_of_properties
            except KeyError:
                print("[-] No Properties information exists for interface [ {0} ]".format(interface_name))
            else:
                if dbg != 0:
                    print("[-] Unknown Error Occured!")
    # Assume if here that the interface was not found
    if dbg != 0:
        print("[-] Did not find the given interface [ {0} ] in the provided introspection map".format(interface_name))
    # Return the empty List of Properties; assumed nothing was found by this point
    return interface__list_of_properties

# Function for Enumerating and Creating a List of All Signals for an Interface
def enumerate_and_create__introspection_map__interface__list_of_signals(introspection_map, interface_name):
    interface__list_of_signals = []
    for interface_item in introspect_map["Interfaces"]:
        if dbg != 0:
            print("[?] Interface Name:\t{0}".format(interface_item["Name"]))
        # Check if the interface item is the interface being searched for
        if interface_item["Name"] == interface_name:
            # Check that the "Signals" information exists
            try:
                # Loop through the signals under this interface
                for signals_item in interface_item["Signals"]:
                    interface__list_of_signals.append(signals_item["Name"])
                # Return the List of Signals from the provided interface name
                return interface__list_of_signals
            except KeyError:
                print("[-] No Signals information exists for interface [ {0} ]".format(interface_name))
            else:
                if dbg != 0:
                    print("[-] Unknown Error Occured!")
    # Assume if here that the interface was not found
    if dbg != 0:
        print("[-] Did not find the given interface [ {0} ] in the provided introspection map".format(interface_name))
    # Return the empty List of Signals; assumed nothing was found by this point
    return interface__list_of_signals

# Function for Enumerating and Creating a List of Arguments (Inputs and Outputs) for a Given Method for a Given Interface
def enumerate_and_create__introspection_map__interface_method__dict_of_arguments(introspection_map, interface_name, method_name):
    interface_method__dict_of_arguments = {
                "Inputs": [],
                "Outputs": []
            }
    for interface_item in introspect_map["Interfaces"]:
        if dbg != 0:
            print("[?] Interface Name:\t{0}".format(interface_item["Name"]))
        # Check if the interface item is the interface being searched for
        if interface_item["Name"] == interface_name:
            # Check that the "Methods" information exists
            try:
                # Loop through the methods under this interface
                for method_item in interface_item["Methods"]:
                    # Checking that the method item is the method being searched for
                    if method_item["Name"] == method_name:
                        # Check that the "Arguments" information exists
                        try:
                            # Loop through the arguments under this method
                            for argument_item in method_item["Arguments"]:
                                ## Check if the Argument is an Input or Output
                                if argument_item["Direction"] == "in":
                                    # Add the Argument informatoin as a tuple to the dictionary of arguments
                                    interface_method__dict_of_arguments["Inputs"].append((argument_item["Name"], argument_item["Type"]))
                                elif argument_item["Direction"] == "out":
                                    # Add the Argument information as a tuple to the dictionary of arguemnts
                                    interface_method__dict_of_arguments["Outputs"].append((argument_item["Name"], argument_item["Type"]))
                                else:
                                    # Unknown Case
                                    #interface_method__dict_of_arguments.append(method_item["Name"])
                                    if dbg != 0:
                                        print("[-] ERROR: Unknown 'Direction' for Method Argument")
                            # Return the List of Arguments for the provided method name from the provided interface name
                            return interface_method__dict_of_arguments
                        except KeyError:
                            print("[-] No Arguments information exists for method [ {0} ]".format(method_name))
                        else:
                            if dbg != 0:
                                print("[-] Unknown Error Occurred!")
            except KeyError:
                print("[-] No Methods information exists for interface [ {0} ]".format(interface_name))
            else:
                if dbg != 0:
                    print("[-] Unknown Error Occured!")
    # Assume if here that the interface was not found
    if dbg != 0:
            print("[-] Did not find the given interface [ {0} ] in the provided introspection map".format(interface_name))
    # Return the empty List of Methods; assumed nothing was found by this point
    print("[-] No Method [ {0} ] on Interface [ {1} ] found".format(method_name, interface_name))
    return interface_method__dict_of_arguments

# Function for Enumerating and Creating a List of All Services
def enumerate_and_create__introspection__list_of_services(device_object):
    high_level_map = find_and_return__introspection_map__high_level_map(device_object)
    list_of_services = high_level_map["Services"]
    # Return the List of Services
    return list_of_services

# Function for Enumerating and Creating a List of All Characteristics
def enumerate_and_create__introspection__list_of_characteristics(device_object):
    high_level_map = find_and_return__introspection_map__high_level_map(device_object)
    list_of_characteristics = high_level_map["Characteristics"]
    # Return the List of Characteristics
    return list_of_characteristics

# Function for Enumerating and Creating a List of All Descriptors
def enumerate_and_create__introspection__list_of_descriptors(device_object):
    high_level_map = find_and_return__introspection_map__high_level_map(device_object)
    list_of_descriptors = high_level_map["Descriptors"]
    # Return the List of Descriptors
    return list_of_descriptors

# Function for Generating and Returning the lists of Services, Characteristics, and Descriptors (in that order)
def generate_and_return__introspection__all_the_lists(device_object):
    # Call the sub-functions to enumerate and generate each list (e.g. Service, Characteristic, Descriptor)
    list_of_services = enumerate_and_create__introspection__list_of_service(device_object)
    list_of_characteristics = enumerate_and_create__introspection__list_of_characteristics(device_object)
    list_of_descriptors = enumerate_and_create__introspection__list_of_descriptors(device_object)
    # Return the lists of Services, Charateristics, and Descriptors
    return list_of_services, list_of_characteristics, list_of_descriptors

## Code for Pico W Testing

# Function for Running Full Enumeration of the BLE CTF Device
#   - Note: Mine map strucutre is outlined in here, but not implemented.  Shifted to the automation variant of this function
def ble_device__scan_and_enumeration(ble_device__address=None):
    ble__scan_enumerate__start_string = "[*] Starting BLE Scan and Enumerate\n"
    logging__log_event(LOG__GENERAL, ble__scan_enumerate__start_string)
    if ble_device__address == None:
        # Internal set variable; comment out later and add function input
        ble_device__address = 'CC:50:E3:B6:BC:A6'
    elif ble_device__address == "picow":
        # Set BLE address to known Pico-W server
        ble_device__address = 'D8:3A:DD:1F:D0:BC'
    ## Code - Connect to BLE CTF device and resolve the services
    ble_device = system_dbus__bluez_device__low_energy(ble_device__address)
    ble_device.Connect()
    print("[*] Waiting for device [ {0} ] services to be resolved".format(ble_device.device_address), end='')
    # Hang and wait to make sure that the services are resolved
    while not ble_device.find_and_get__device_property("ServicesResolved"):
        time.sleep(0.5)      # Sleep to give time for Services to Resolve
        print(".", end='')
    print("\n[+] ble_device__scan_and_enumeration::Device services resolved!")
    ble_device.identify_and_set__device_properties(ble_device.find_and_get__all_device_properties())
    # Print out the Class of Device Information
    decode__class_of_device(user_device.device_class)
    # Begin introspecting services
    ble_services_list = ble_device.find_and_get__device_introspection__services()
    # JSON for tracking the various services, characteristics, and descriptors from the GATT
    ble_device__mapping = { "Services" : {} }
    # JSON for tracking the landmine services, characteristics, and descriptors discovered during GATT enumeration
    #ble_device__mine_mapping = { "Services" : [], "Characteristics" : [], "Descriptors" : [] }
    '''
    Map of JSON Mapping:
        BDADDR : {
            Service001 : {
                Characteristic001 : {
                    Descriptor001 : {
                        descriptor_info_key : descriptor_info_value
                        },
                    characteristics_info_key : characteristic_info_value
                    },
                service_info_key : service_info_value
            }
    
    
    '''
    ## Code - Complete Enumeration through a BLE Device's Services, Characteristics, and Descriptors
    # Now do an iteration through the 'Services' to enumerate all the characteristics
    for ble_service in ble_services_list:
        # Internal JSON mapping
        device__service__map = create_and_return__gatt__service_json()
        if dbg != 0:    # ~!~
            print("[*] BLE Service\t-\t{0}".format(ble_service))
        ble__scan_enumerate__service_string = "[*] BLE Service\t-\t{0}\n".format(ble_service)
        logging__log_event(LOG__GENERAL, ble__scan_enumerate__service_string)
        # Create the characteristic variables that we will work with
        service_path, service_object, service_interface, service_properties, service_introspection = ble_device.create_and_return__service__gatt_inspection_set(ble_service)
        # Generate the sub-list of Service Characteristics
        service_characteristics_list = ble_device.find_and_get__device__etree_details(service_introspection, 'char')       # Nota Bene: This only does the conversion of the eTree into something meaningful that can be enumerated for the Characteristic names; SAME THING as the line below
        #ble_chars_list = ble_device.find_and_get__device_introspection__characteristics(service_path, service_characteristics_list)
        # Now do an iteration through the 'Characteristics' of the current Service
        for ble_service_characteristic in service_characteristics_list:
            # Internal JSON mapping
            device__characteristic__map = create_and_return__gatt__characteristic_json()
            # Generate the Interfaces for each Characteristic
            characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = ble_device.create_and_return__characteristic__gatt_inspection_set(service_path, ble_service_characteristic)
            # Check the Read/Write Flag(s) for the Characteristic interface
            characteristic_flags = ble_device.find_and_get__characteristic_property(characteristic_properties, 'Flags')
            if dbg != 0:    # ~!~
                #print("[*] Characteristic [ {0} ] Flags:\t{1}".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Service'), characteristic_flags))
                print("[*] Characteristic [ {0} ] Flags:\t{1}".format(characteristic_path, characteristic_flags))
            ble__scan_enumerate__characteristic_string = "[*] Characteristic [ {0} ] Flags:\t{1}\n".format(characteristic_path, characteristic_flags)
            logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_string)
            ## Attempt to Read the value from the Characteristic (NOTE: AFTER checking if there is a read/write flag; TODO: Use the results from the ReadValue() function call to create the input for the WriteValue() function call
            if dbg != 0:
                print("[!] Pre-Read Test:\tCharacteristic Value:\t-\t{0}".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Value')))
            ble__scan_enumerate__characteristic_test_string = "[!] Pre-Read Test:\tCharacteristic Value:\t-\t{0}\n".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Value'))
            logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_test_string)
            ## Check if there is a 'read' in the flags
            if 'read' in characteristic_flags or 'write' in characteristic_flags:      # NOTE: Even if 'write' is the only thing present, it can have a value name
                if dbg != 0:
                    print("[*] Attempt to read from Characteristic [ {0} ] due to Flags [ {1} ]".format(characteristic_path, characteristic_flags))
                ble__scan_enumerate__characteristic_read_string = "[*] Attempt to read from Characteristic [ {0} ] due to Flags [ {1} ]\n".format(characteristic_path, characteristic_flags)
                logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_read_string)
                try:
                    characteristic_interface.ReadValue({})
                    if dbg != 0:
                        print("[+] Able to perform ReadValue()\t-\tCharacteristic")
                    #logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_read_string)
                except Exception as e:
                    if dbg != 0:
                        print("[-] Unable to perform ReadValue()\t-\tCharacteristic")
                    # Add this "problem" to the mine map
                    #ble_device__mine_mapping["Characteristics"].extend(ble_service_characteristic)
                    #logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_read_string)
                    ble_device.understand_and_handle__dbus_errors(e)
            if dbg != 0:
                print("[!] Post-Read Test:\tCharacteristic Value:\t-\t{0}".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Value')))
            ble__scan_enumerate__characteristic_read2_string = "[!] Post-Read Test:\tCharacteristic Value:\t-\t{0}\n".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Value'))
            logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_read2_string)
            characteristic_value__hex_array = ble_device.find_and_get__characteristic_property(characteristic_properties, 'Value')
            try:
                characteristic_value__ascii_string = convert__hex_to_ascii(characteristic_value__hex_array)
            except Exception as e:
                ble_device.understand_and_handle__dbus_errors(e)
                characteristic_value__ascii_string = None
            if dbg != 0:
                print("\tCharacteristic Value:\t{0}\n\t\tRaw:\t{1}".format(characteristic_value__ascii_string, characteristic_value__hex_array))
                print("\tValue\t-\t{0}".format(characteristic_value__ascii_string))
                print("\tHandle\t-\t{0}".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Handle')))
                print("\tUUID\t-\t{0}".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'UUID')))
            # General Logging
            ble__scan_enumerate__characteristic_raw_string = "\tCharacteristic Value:\t{0}\n\t\tRaw:\t{1}\n".format(characteristic_value__ascii_string, characteristic_value__hex_array)
            ble__scan_enumerate__characteristic_value_string = "\tValue\t-\t{0}\n".format(characteristic_value__ascii_string)
            ble__scan_enumerate__characteristic_handle_string = "\tHandle\t-\t{0}\n".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'Handle'))
            ble__scan_enumerate__characteristic_uuid_string = "\tUUID\t-\t{0}\n".format(ble_device.find_and_get__characteristic_property(characteristic_properties, 'UUID'))
            logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_raw_string)
            logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_value_string)
            logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_handle_string)
            logging__log_event(LOG__GENERAL, ble__scan_enumerate__characteristic_uuid_string)
            # Setting the variables to be added into the JSON map for the device
            characteristic_uuid = ble_device.find_and_get__characteristic_property(characteristic_properties, 'UUID')
            characteristic_value = characteristic_value__ascii_string
            characteristic_handle = ble_device.find_and_get__characteristic_property(characteristic_properties, 'Handle')
            ## Move onto the Descriptors
            # Generate the sub-list of Characteristic Descriptors
            characteristic_descriptors_list = ble_device.find_and_get__device__etree_details(characteristic_introspection, 'desc')
            # Now do an iteration through the 'Descriptors' of the current Characteristic
            for ble_characteristic_descriptor in characteristic_descriptors_list:
                # Internal JSON mapping
                device__descriptor__map = create_and_return__gatt__descriptor_json()
                # Create the descriptor variables that we will work with
                descriptor_path, descriptor_object, descriptor_interface, descriptor_properties, descriptor_introspection = ble_device.create_and_return__descriptor__gatt_inspection_set(characteristic_path, ble_characteristic_descriptor)
                # Check the Read/Write Flag(s) for the Descriptor interface
                descriptor_flags = ble_device.find_and_get__descriptor_property(descriptor_properties, 'Flags')        # Note: Descriptor may NOT have a Flags property
                if dbg != 0:    # ~!~
                    print("[*] Descriptor [ {0} ] Flags:\t{1}".format(descriptor_path, descriptor_flags))
                ## Attempt to Read/Write the value from the Descriptor; Note: Same structure as for Characteristics
                # Update the current descriptor map
                device__descriptor__map["Flags"] = descriptor_flags
                # Update to the characteristic map
                device__characteristic__map["Descriptors"][ble_characteristic_descriptor] = device__descriptor__map
            # Update the current characteristic map
            device__characteristic__map["UUID"] = characteristic_uuid
            device__characteristic__map["Value"] = characteristic_value
            device__characteristic__map["Handle"] = characteristic_handle
            device__characteristic__map["Flags"] = characteristic_flags
            # Update to the services map
            device__service__map["Characteristics"][ble_service_characteristic] = device__characteristic__map
        # Get the variables we are looking for
        service_uuid = ble_device.find_and_get__service_property(service_properties, 'UUID')
        # Update to the current service map
        device__service__map["UUID"] = service_uuid
        # Update to the device map
        ble_device__mapping["Services"][ble_service] = device__service__map

    ## Pretty print the BLE CTF device mapping
    print("JSON Print of the Enumeration")
    #print(ble_device__mapping)
    # TODO: Capture the output from below and place into logging file
    pretty_print__gatt__dive_json(ble_device, ble_device__mapping)
    # Logging
    ble__scan_enumerate__end_string = "[+] Completed BLE Scan and Enumeration of [{0}]\n".format(ble_device__address)
    logging__log_event(LOG__GENERAL, ble__scan_enumerate__end_string)
    print_and_log(ble__scan_enumerate__end_string, LOG__ENUM)
    
    return ble_device, ble_device__mapping

# Function for learning about Notifications with Pico-W led_peripheral script
def debug__testing__pico_w():
    '''
    user_selected_device = user_interaction__find_and_return__pick_device()
    '''
    # Changed to use new enumeration structure
    user_selection = user_interaction__find_and_return__pick_device()
    print("[*] User Selection:\t{0}".format(user_selection))
    user_selected_device = user_selection[0]    # The 0th item is the Bluetooth Address and the 1st item is the Bluetooth Name
    user_device, user_device__mapping, landmine_map, security_map = connect_and_enumerate__bluetooth__low_energy(user_selected_device)
    user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
    characteristic_name = "char0008"
    detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_name)
    characteristic_service_path = detailed_characteristic["Service"]
    characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_name)
    # Set the call backs for notify
    #   - Ex:       characteristic_interface.StartNotify(reply_handler=test_cb, error_handler=test_error, dbus_interface=bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE)

    ## Definitions for the callbacks
    # Notification Catch Test
    def notify_catch(value):
        print("[!] Notify Catch\t-\tValue:\t{0}".format(value))

    # Basic Error Callback
    def notify_error(error):
        print("[!] Notify Error\t-\tError:\t{0}".format(error))

    ## Definitions for Notification catching using GLib MainLoop
    # Function for adding a timeout to the user_device's bus property; Take in a timeout in milliseconds and a function to call once timesd out
    #   - TODO: [ ] Get timeout functionality working on this
    def mainloop__configure__add_timeout(timeout_ms, callback_function):

        # Create a GLib MainLoop Object (cause it's needed?)
        mainloop = GLib.MainLoop()

        # Adding a timeout to the GLib MainLoop
        timer_id = GLib.timeout_add(timeout_ms, callback_function)

    #characteristic_interface.StartNotify(reply_handler=notify_catch, error_handler=notify_error, dbus_interface=bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE)

    ## More testing using the Signal Receiving and Notify Callbacks
    # Note: Get errors attempting to use "g-properties-changed"; ValueError: Invalid member name 'g-properties-changed': contains invalid character '-'
    #characteristic_interface.connect_to_signal('g-properties-changed', debugging__dbus_signals__catchall)
    #characteristic_interface.connect_to_signal('g-properties-changed', debugging__dbus_signals__catchall, dbus_interface=bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE)
    # Trying to capture signals using 'PropertesChanged'
    #characteristic_interface.connect_to_signal('PropertiesChanged', debugging__dbus_signals__catchall)
    #characteristic_interface.connect_to_signal('PropertiesChanged', debugging__dbus_signals__catchall, dbus_interface=bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE)
    # Note: The above were taken by Python, but still do not see the Notification
    #   -> Nota Bene: Comparing to the BT SIG V1 developer documents it might be the dbus_interface that is configured incorrectly
    #       - Ex:       if interface != bluetooth_constants.DEVICE_INTERFACE: which shows that the example is examining the DEVICE_INTERFACE D-Bus interface

    #user_device._bus.add_signal_receiver(debugging__dbus_signals__catchall, dbus_interface = bluetooth_constants.GATT_CHARACTERISTIC_INTERFACE, message_keyword='dbus_message')
    # Note: The reason the above does NOT work is that (1) the signal does not come on the Characteristic Interface, but on the Properties Interface and (2) a method call to .StartNotify() needs to be made before the signals appear

    '''
    # Setting the debugging D-Bus signal catcher as the callback for any "PropertiesChanged" signals incoming on the org.freedesktop.DBus.Properties interface
    user_device._bus.add_signal_receiver(debugging__dbus_signals__catchall, dbus_interface = bluetooth_constants.DBUS_PROPERTIES, signal_name = "PropertiesChanged")

    # Start the notification on the given characteristic
    characteristic_interface.StartNotify()

    # Create MainLoop GLib Object for use below
    mainloop = GLib.MainLoop()

    # Loop for listening on the D-Bus for Notify signals (e.g. "PropertiesChanged")
    try:
        mainloop.run()
    except KeyboardInterrupt:
        mainloop.quit()

    # Stop the notification signals
    characteristic_interface.StopNotify()
    '''

    # Structure creation and function call to replicate the code above
    test_signal = system_dbus__bluez_signals()
    test_signal.run__signal_catch__timed(characteristic_interface, debugging__dbus_signals__catchall)

    print("[+] Completed Notify Testing")

# Function for Debugging Signals with RealTek BW-16 UART Example; editted into LED control
def debug_bw16_signals():
    target_device = "94:C9:60:AE:2F:9D"
    #check_and_explore__bluetooth_device__user_selected(target_device)
    user_selection = user_interaction__find_and_return__pick_device()
    print("[*] User Selection:\t{0}".format(user_selection))
    user_selected_device = user_selection[0]    # The 0th item is the Bluetooth Address and the 1st item is the Bluetooth Name
    user_device, user_device__mapping, landmine_map, security_map = connect_and_enumerate__bluetooth__low_energy(user_selected_device)
    user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
    # Configure the two Characteristics
    char_to_write = "char000d"
    char_to_read_signal = "char000f"
    ## Create Structures
    write_detailed_char = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, char_to_write)
    write_char_service_path = write_detailed_char["Service"]
    write_char_path, write_char_object, write_char_interface, write_char_properties, write_char_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(write_char_service_path, char_to_write)
    read_signal_detailed_char = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, char_to_read_signal)
    read_signal_char_service_path = read_signal_detailed_char["Service"]
    read_signal_char_path, read_signal_char_object, read_signal_char_interface, read_signal_char_properties, read_signal_char_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(read_signal_char_service_path, char_to_read_signal)
    ## Variable for Performing Manual vs. Class Function use
    manual_bit = 0
    read_bit = 0
    #######
    if manual_bit != 0:
        ## Manually configuring signal emittion capture
        user_device._bus.add_signal_receiver(debugging__dbus_signals__catchall, dbus_interface = bluetooth_constants.DBUS_PROPERTIES, signal_name = "PropertiesChanged")
        read_signal_char_interface.StartNotify()
        # Generate a Mainloop
        from dbus.mainloop.glib import DBusGMainLoop
        #dbus_loop = DBusGMainLoop()
        dbus_loop = GLib.MainLoop()
        #test_bus = dbus.SystemBus(mainloop=dbus_loop)
        # Run Loop
        try:
            dbus_loop.run()
        except KeyboardInterrupt:
            dbus_loop.quit()
        # Turn off Notifications
        read_signal_char_interface.StopNotify()
    else:
        read_signal = system_dbus__bluez_signals()
        #read_signal.run__read_signal_catch__timed(read_signal_char_interface, write_char_interface, debugging__dbus_signals__catchall, "PropertiesChanged")
        if read_bit != 0:
            # Test read signal
            read_signal.run__read_signal_catch__timed(read_signal_char_interface, read_signal_char_interface, debugging__dbus_signals__catchall, "PropertiesChanged")
        # TODO: Change the above to return the value from the signal?  Place as part of the Class structure? (e.g. a buffer)
        else:
            # Test write signal
            read_signal.run__write_signal_catch__timed(read_signal_char_interface, write_char_interface, debugging__dbus_signals__catchall, "PropertiesChanged")

# Function for Learning Notification Capture
def debugging__notification():
    user_selected_device = user_interaction__find_and_return__pick_device()
    user_device, user_device__mapping = connect_and_enumerate__bluetooth__low_energy(user_selected_device)
    user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
    detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, BLE_CTF__CHARACTERISTIC_FLAGS['Flag-11'])
    characteristic_service_path = detailed_characteristic["Service"]
    characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, BLE_CTF__CHARACTERISTIC_FLAGS['Flag-11'])
    test_signal = system_dbus__bluez_signals()
    test_signal.capture_and_act__emittion__gatt_characteristic(user_device, BLE_CTF__CHARACTERISTIC_FLAGS['Flag-11'])
    # Now try to force signals
    characteristic_interface.StartNotify()
    user_selected_device = user_interaction__find_and_return__pick_device()
    
## Debugging Functions  -   Scratch Space
# Function for Pretty Printing of an Introspect Map (trained on Device Interface Interfaces)
## Note:  This function appears to work for ALL D-Bus Interfaces
def debug__pretty_print__device_interface__interfaces(introspect__map__interfaces):
    print("[*] Pretty Printing\t-\tIntrospection\t-\tDevice Interface\t-\tInterfaces")
    for interface_item in introspect__map__interfaces:
        if dbg != 0:    # ~!~
            print("Interface Item:\t{0}".format(interface_item))
        print("Interface Name:\t{0}".format(interface_item["Name"]))
        ## Attempt to check for "Methods" related to the current INTERFACE
        try:
            # Note: "Methods" is ALWAYS a list; need to extract the list items to interacte through
            for method_item in interface_item["Methods"]:
                print("\tMethod Name:\t{0}".format(method_item["Name"]))
                ## Attempt to check for "Arguments" related to the current METHOD
                try:
                    for method_argument in method_item["Arguments"]:
                        #print("\t\t[ {0} ]\t\tName:\t{1}\t\tType(signature):\t{2}".format(method_argument["Direction"], method_argument["Name"], method_argument["Type"]))
                        ## Printing 'try' statements for giving a full print of the METHOD ARGUMENTS
                        # Print DIRECTION of the ARGUMENT
                        try:
                            print("\t\t[ {0} ]".format(method_argument["Direction"]), end="")
                        except Exception as e:
                            print("\t\t[ N/A ]", end="")
                        # Print NAME of the ARGUMENT
                        try:
                            print("\t\tName:\t{0}".format(method_argument["Name"]), end="")
                        except Exception as e:
                            print("\t\tName:\tNone", end="")
                        # Print TYPE of the ARGUMENT
                        try:
                            print("\t\tType(signature):\t{0}".format(method_argument["Type"]))
                        except Exception as e:
                            print("\t\tType(signature):\tN/A")
                except Exception as e:
                    if dbg != 0:
                        print("\t\tNo Arguments")
                    if dbg != 0:
                        print("[!] ERROR:\t{0}".format(e))
        except Exception as e:
            if dbg != 0:
                print("\tNo Methods")
            if dbg != 0:
                print("[!] ERROR:\t{0}".format(e))
        ## Attempt to check for "Properties" related to the current INTERFACE
        try:
            for property_item in interface_item["Properties"]:
                ## Printing 'try' statements for giving a full print of the PROPERTIES of the INTERFACE
                # Print the NAME of the PROPERTY
                try:
                    print("\tProperty Name:\t{0}".format(property_item["Name"]), end="")
                except Exception as e:
                    print("\tProperty Name:\tN\\A", end="")
                # Print the ACCESS of the PROPERTY
                try:
                    print("\t\tAccess:\t{0}".format(property_item["Access"]), end="")
                except Exception as e:
                    print("\t\tAccess:\tN/A", end="")
                # Print the TYPE of the PROPERTY
                try:
                    print("\t\tType(signature):\t{0}".format(property_item["Type"]))
                except Exception as e:
                    print("\t\tType(signature):\tN/A")
                #print("\tAccess:\t{1}\t\tType(signature):\t{2}".format(property_item["Access"], property_item["Type"]))
        except Exception as e:
            if dbg != 0:
                print("\tNo Properties")
            if dbg != 0:
                print("[!] ERROR:\t{0}".format(e))
        ## Attempt to check for "Signals" related to the current INTERFACE
        try:
            for signal_item in interface_item["Signals"]:
                ## Printing 'try' statements for giving a full print of the SIGNALS of the INTERFACE
                # Print the NAME of the SIGNAL
                try:
                    print("\tSignal Name:\t{0}".format(signal_item["Name"]))
                except Exception as e:
                    print("\tSignal Name:\tN/A")
                ## Attempt to check for "Arguments" related to the current SIGNAL
                try:
                    for signal_argument in signal_item["Arguments"]:
                        ## Printing 'try' statements for giving a ful print of the SIGNAL ARGUMENTS
                        # Print the NAME of the ARGUMENT
                        try:
                            print("\t\tArgument Name:\t{0}".format(signal_argument["Name"]), end="")
                        except Exception as e:
                            print("\t\tArgument Name:\tN/A", end="")
                        # Print the TYPE of the ARGUMENT
                        try:
                            print("\t\tType(signature):\t{0}".format(signal_argument["Type"]))
                        except Exception as e:
                            print("\t\tType(signature):\tN/A")
                except Exception as e:
                    if dbg != 0:
                        print("\t\tNo Arguments")
        except Exception as e:
            if dbg != 0:
                print("\tNo Signals")
            if dbg != 0:
                print("[!] ERROR:\t{0}".format(e))
    print("[+] Completed Pretty Print\t-\tDevice Interface\t-\tInterfaces")

# Function for Pretty Printing of an Introspect Map (trained on Device Interface Nodes)
## Note:  This function appears to work for ALL D-Bus Interfaces
def debug__pretty_print__device_interface__nodes(introspect__map__nodes):
    print("[*] Pretty Printing\t-\tIntrospection\t-\tDevice Interface\t-\tNodes")
    for node_item in introspect__map__nodes:
        print("Node Name:\t{0}".format(node_item))
    print("[+] Completed Pretty Print\t-\tDevice Interface\t-\tNodes")

# Function for Pretty Printing all information of an Introspect Map of a given D-Bus Interface
def debug__pretty_print__interface_information(interface__map):
    print("[*] ---------- Pretty Print of D-Bus Interface -----------")
    print(" /--- Interfaces ---")
    debug__pretty_print__device_interface__interfaces(interface__map["Interfaces"])
    print(" /--- Nodes ---")
    debug__pretty_print__device_interface__nodes(interface__map["Nodes"])

# Function for Testing D-Bus Enumeration and Debugging
def debug__dbus_interface__testing():
    user_selected_device = user_interaction__find_and_return__pick_device()
    user_device, user_device__mapping = connect_and_enumerate__bluetooth__low_energy(user_selected_device)
    user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
    # Create the introspection pieces
    device_introspection = user_device.device_interface.Introspect(dbus_interface=INTROSPECT_INTERFACE)
    introspect_xml = bluetooth_utils.dbus_to_python(device_introspection)
    # Imports for libraries
    import json, xmltodict
    dict_data = xmltodict.parse(introspect_xml)
    # Test the pretty print
    introspect__map = pretty_print__introspect__dict(dict_data)
    # Return information
    return user_device, user_device__mapping, dict_data, introspect__map

# Function for Printing and Logging Data
def print_and_log(output_string, log_type=LOG__GENERAL):
    #log_type = LOG__GENERAL
    # Added silent printing if for debugging
    if (log_type != LOG__DEBUG) and (log_type != LOG__ENUM):
        print(output_string)
    logging__log_event(log_type, output_string)

# Function for Extracting Characteristics Information as ASCii
def extract_and_print__characteristics_list(user_device, user_device__internals_map):
    if dbg != 0:
        out_log_string = "[*] extract_and_print__characteristics_list::Attempting to Generate and Print the Characteristics List"
        print_and_log(out_log_string, LOG__DEBUG)
    # Create the characteristics list from the provided user_device
    characteristics_list = user_device.find_and_return__internal_map__characteristics_list(user_device__internals_map)
    # Iterate through the characteristics list
    for characteristic_item in characteristics_list:
        if dbg != 0:
            out_log_string = "[*] extract_and_print__characteristics_list::Building structures for Characteristic [ {0} ]".format(characteristic_item)
            print_and_log(out_log_string, LOG__DEBUG)
        detailed_characteristic = user_device.find_and_return__internal_map__detailed_characteristic(user_device__internals_map, characteristic_item)
        characteristic_service_path = detailed_characteristic["Service"]
        characteristic_path, characteristic_object, characteristic_interface, characteristic_properties, characteristic_introspection = user_device.create_and_return__characteristic__gatt_inspection_set(characteristic_service_path, characteristic_item)
        if dbg != 0:
            out_log_string = "[*] extract_and_print__characteristics_list::Attempting to call the ReadValue method via the characteristic interface"
            print_and_log(out_log_string, LOG__DEBUG)
        # Attempt call to the ReadValue method (via characteristic interface)
        try:
            user_device.read__device__characteristic(characteristic_interface)
        except Exception as e:
            output_log_string = "[-] extract_and_print__characteristics_list::Charateristic Read Method Call Error"
            print_and_log(output_log_string)
            print_and_log(output_log_string, LOG__ENUM)
            print_and_log(output_log_string, LOG__DEBUG)
            user_device.error_buffer = user_device.understand_and_handle__dbus_errors(e)
            characteristic__read_value = None
        else:
            if dbg != 0:
                out_log_string = "[*] extract_and_print__characteristics_list::Successfully made ReadValue method call wihtout raising an exception"
                print_and_log(out_log_string, LOG__DEBUG)
        # Attempt call to read the Value (via properties interface)
        try:
            # Get value
            characteristic__read_value = user_device.find_and_get__characteristic_property(characteristic_properties, 'Value')
        except Exception as e:
            out_log_string = "[-] extract_and_print__characteristics_list::Attempting to read the Value from the properties interface"
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            if dbg != 0:
                out_log_string = "[*] extract_and_print__characteristics_list::Successfully made read of Value without raising an exception"
                print_and_log(out_log_string, LOG__DEBUG)
        output_log_string = "[*] extract_and_print__characteristics_list::Retrieved a read value of  [ {0} ] of type [ {1} ]".format(characteristic__read_value, type(characteristic__read_value))
        print_and_log(output_log_string, LOG__DEBUG)
        # Check is a dbus.Array was returned
        if isinstance(characteristic__read_value, dbus.Array):
            characteristic__read_value = user_device.dbus_read_value__to__ascii_string(characteristic__read_value)
        # Check if nothing was returned
        elif characteristic__read_value is None:        ## TODO: Figure out what to do if the data acquired was NOT a dbus.Array
            characteristic__read_value = convert__hex_to_ascii(characteristic__read_value)
        # Check if a list (e.g. Array of hex/decimal values) was returned
        elif isinstance(characteristic__read_value, list):
            characteristic__read_value = convert__hex_to_ascii(characteristic__read_value)
        out_log_string = "\t{0}\t-\t{1}".format(characteristic_item, characteristic__read_value)
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)

# Function for Performing Print out of Process Data
#   - TODO: Improve print out to provide different information based on the scan mode?
def post_processing__ble__scan_analysis(user_device, user_device__internals_map, device_properties_array, scan_mode):
    out_log_string = "[*] [ {0} ] Scan Analsysis".format(scan_mode)
    print_and_log(out_log_string)
    print_and_log(out_log_string, LOG__ENUM)
    # Top Level GAP info
    out_log_string = "---\n- High Level Device Properties\n-----"
    print_and_log(out_log_string)
    print_and_log(out_log_string, LOG__ENUM)
    for device_property in device_properties_array:
        out_log_string = "\t{0}:\t\t\t{1}".format(device_property, device_properties_array[device_property])
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
    # Characteristics Printed out in ASCii
    #characteristics_list = user_device.find_and_return__internal_map__characteristics_list(user_device__internals_map)
    out_log_string = "-----\n- Characteristic Fields - ASCii\n-----"
    print_and_log(out_log_string)
    print_and_log(out_log_string, LOG__ENUM)
    # Note: The command below will REQUIRE that the user_device still be connected to query the device
    extract_and_print__characteristics_list(user_device, user_device__internals_map)
    # Characteristics + UUIDs with Write Flag (i.e. writeable)
    # Characteristics + UUIDs with Notify/Indicate Flag
    # Full formatted print out of the entire device map
    pretty_print__gatt__dive_json(user_device, user_device__internals_map)

# Function for Performing a BLE Scan on a Target Device using a Specific Scan Mode; Note: Default is "passive"
#   - TODO: Add functionality to pass the 'scan_mode' for a change in scanning
#   - Note: Order of Scan Modes from Quiet to Loud is Passive, Nag, Poke, Bruteforce
## TODO: Create a simple function that performs the following:
#   [x]     (0) Determine the specific "bluetooth_address" that should be targeted for communication        <------ Should be covered by the user input, but verification is always good
#   [x]     (1) Scan around for the "bluetooth_address" device; scanning until                              <------ Definitely incorporate this functionality into a scanning function
#               (i)     Continue scanning until the device is found                                             <----- Note: This WILL require a break-out command (i.e. Ctrl+C)
#               (ii)    Give-up/Terminate after time X                                                          <----- Already handled by the scan timeout functionality that got added
#   [x]     (2) Connect to the device and wait for the ServicesResolved() to return True                    <------ Should be covered by the inner functionality of the connect + scan function; connects, waits for ervices to resolve, then continues
#               - Is covered by the connect_and_enumerat function
#   [x]     (3) Read through all GATT S/C/D and create a device map                                         <------ Also done by the process of creating the user_device and enumerating the device's internals
#   [ ]     (4+)    Perform specific scanning actions based on the various scan types
#               -> SHOULD be able to leverage the "uesr_exploration" function calls; recall that this is done by using the device map as a reference structure and then selecting specific S/C/D for R/W I/O
def scanning__ble(target_device, scan_mode="passive"):
    # Variable for tracking all output generated
    out_log_string = "-=!=- Unchanged Log String -=!=-"
    discovered_devices = None
    #print("[*] Starting BLE Scan of Mode [{0}] on Target Device [{1}]".format(scan_mode, target_device))
    out_log_string = "[*] Starting BLE Scan of Mode [ {0} ] on Target Device [ {1} ]".format(scan_mode, target_device)
    print_and_log(out_log_string)
    print_and_log(out_log_string, LOG__ENUM)
    ## Loop for searching for the specific device
    device_found_flag = False
    loop_iteration = 0
    search_no_more_times = 3

    # Search for the device based on a set number of times
    while device_found_flag == False and loop_iteration < search_no_more_times:
        ## Initial Scanning of the device
        try:
            # Performing a scan for general devices; main scan for devices to populate the linux D-Bus
            discovered_devices = create_and_return__bluetooth_scan__discovered_devices()
        except Exception as e:
            out_log_string = "[-] Error with adapter while attempting to discover devices\n\tError:\t\t[ {0} ]".format(e)
            print_and_log(out_log_string)
            print_and_log(out_log_string, LOG__DEBUG)
            break
        if discovered_devices is None:
            print("[-] No devices were found during scan and discovery")
            break
        # Iterate through the discovered devices, since working with tuples of (address, name) and not just a list of addresses
        for discovered_device in discovered_devices:
            # Sanity check for having found the target device
            if target_device not in discovered_device:
                out_log_string = "[!] Unable to find device [ {0} ]".format(target_device)
                print_and_log(out_log_string)
                print_and_log(out_log_string, LOG__DEBUG)
                if dbg != 0:
                    out_log_string = "\tDiscovered Devices:\t[ {0} ]".format(discovered_devices)
                    print_and_log(out_log_string)
                    print_and_log(out_log_string, LOG__DEBUG)
                #return None
            else:
                out_log_string = "[+] Able to find device [ {0} ]".format(target_device)
                print_and_log(out_log_string)
                print_and_log(out_log_string, LOG__DEBUG)
                device_found_flag = True
            # Increase the interation count
            loop_iteration += 1
    if device_found_flag != True:
        out_log_string = "[-] Device not found with address [ {0} ]".format(target_device)
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
        print_and_log(out_log_string, LOG__DEBUG)
        return None
    else:
        out_log_string = "[+] Found the device with address [ {0} ]".format(target_device)
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
        print_and_log(out_log_string, LOG__DEBUG)
    ## Continue scanning the target device  | Basic Scan of the device due to generation of the internals informaiton
    # Reset loop variables
    loop_iteration = 0
    device_found_flag = False
    # Map tracking variables
    landmine_map = None
    security_map = None
    # Tracking for later Post Processing analysis
    user_device = None
    user_device__mapping = None
    ## Performing the selected Mode Scan
    # Passive Scan              # TODO: Remove re-try for the passive scan?? Perhaps less "pushy" landmine check?
    if scan_mode == "passive":
        # Performing Passive Scan of the Target Device
        #print("[*] Passive Scan being Performed Against Target [{0}]".format(target_device))
        out_log_string = "[*] Passive Scan being Performed Against Target [{0}]".format(target_device)
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
        # While loop for attemping connection and enumeration of a target device
        while loop_iteration < search_no_more_times and not device_found_flag:
            if dbg != 0:
                print("[?] Debug: First Test [ {0} ] + Second Test [ {1} ]\n\tLoop Iteration:\t{2}\t\tMax Searches:\t{3}\t\tDevice Found Flag:\t{4}".format(loop_iteration < search_no_more_times, not device_found_flag, loop_iteration, search_no_more_times, device_found_flag))
            # Expanded to try statement for improved troubleshooting
            try:
                # Pass the target_device to the connect and enumerate the device
                user_device, user_device__mapping, landmine_map, security_map = connect_and_enumerate__bluetooth__low_energy(target_device, landmine_map, security_map)
                # TODO: Add check here to validate that the device has been found
                #print("[?] User Device:\t[ {0} ]\n\tUser Dev Map:\t[ {1} ]".format(user_device, user_device__mapping))
                output_log_string = "[?] User Device:\t[ {0} ]\n\tUser Dev Map:\t[ {1} ]".format(user_device, user_device__mapping)
                print_and_log(output_log_string, LOG__DEBUG)
                # Set that the target device was found and enumerated
                device_found_flag = True
            except Exception as e:
                output_log_string = "[!] scanning__ble::Error: Connection and Enumeration of Provided Target Failed\n\t{0}".format(e)
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__DEBUG)
                # org.freedesktop.DBus.Error.UnknownObject
                if e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownObject':
                    output_log_string = "[-] scanning__ble::Unknown Object Error..."
                    print_and_log(output_log_string)
                    print_and_log(output_log_string, LOG__DEBUG)

                    # Re-try scanning for the device
                    found_flag, discovered_devices = search_for_device(target_device, max_searches=3)   # TODO: Move this elsewhere?
                    # Increase counter for attempting to see a given device
                    loop_iteration += 1
                    #return None
                elif e.get_dbus_name() == 'org.freedesktop.DBus.Error.NoReply':
                    output_log_string = "[-] scanning__ble::No Reply Error..."
                    print_and_log(output_log_string)
                    print_and_log(output_log_string, LOG__DEBUG)

                    # Re-try scanning for the device
                    found_flag, discovered_devices = search_for_device(target_device, max_searches=3)   # TODO: Move this elsewhere?
                    # Increase counter for attempting to see a given device
                    loop_iteration += 1
                    #return None
                else:
                    #raise _error_from_dbus_error(e)
                    output_log_string = "[-] scanning__ble::Unknown Error Occurred:\t\t{0}".format(e)
                    print_and_log(output_log_string, LOG__DEBUG)
                    # TODO: Improve this return to set a re-try
                    return None
                # Sleep for allowing time
                time.sleep(5)   # Wait five seconds
            else:
                out_log_string = "[*] scanning__ble::Connection and Enumeration completed without raising an execption"
                print_and_log(out_log_string, LOG__DEBUG)
                # Generate the Device Internals Map
                user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
                out_log_string = "[*] scanning__ble::Generated Device Internals Map"
                print_and_log(out_log_string)
                print_and_log(out_log_string, LOG__DEBUG)
    # Naggy Scan;   # NOTE: Have this be the first variation of the "land-mine" detecetion for passive
    elif scan_mode == "naggy":
        # Performing Naggy Scan of the Target Device (i.e. verbose passive reads)
        #print("[*] Nagging Scan being Performed Against Target [{0}]".format(target_device))
        out_log_string = "[*] Nagging Scan being Performed Against Target [{0}]".format(target_device)
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
        # While loop for attempting connection and enumeration of a target device
        while loop_iteration < search_no_more_times and not device_found_flag:
            out_log_string = "[*] scanning__ble::{0}\t-\tAttempting to Connect and Enumerate the Target [ {1} ]".format(scan_mode, target_device)
            print_and_log(out_log_string, LOG__DEBUG)
            # Try statement for connecting to the device and enumerating it
            try:
                # Pass the target_device to the connect and enumerate the device
                user_device, user_device__mapping, landmine_map, security_map = connect_and_enumerate__bluetooth__low_energy(target_device, landmine_map, security_map)
                out_log_string = "[*] scanning__ble::{0}\t-\tSetting Device Found Flag".format(scan_mode)
                print_and_log(out_log_string, LOG__DEBUG)
                # Set that the target device was found and enumerated
                device_found_flag = True
            except Exception as e:
                output_log_string = "[!] bleep::na-scan - Error Occurred During Connection and Enumeration of Provided Target\n\t{0}".format(e)
                print_and_log(output_log_string)
                # Sleep for allowing time
                time.sleep(5)   # Wait five seconds
            else:
                if dbg != 0:
                    out_log_string = "[*] scanning_ble::{0}\t-\tSuccess in Connect and Enumerate without raising an exception"
                    print_and_log(out_log_string, LOG__DEBUG)
            finally:
                if dbg != 0:
                    out_log_string = "[*] scanning__ble::{0}\t-\tCompleted Attempt to Connect and Enumerate target [ {1} ]".format(scan_mode, target_device)
                    print_and_log(out_log_string, LOG__DEBUG)
                    out_log_string = "[*] scanning__ble::{0}\t-\tVariable Check:\n\tType Device:\t[ {1} ]\n\tType DMap:\t[ {2} ]\n\tType LMap:\t[ {3} ]\n\tType SMap:\t[ {4} ]".format(scan_mode, user_device, user_device__mapping, landmine_map, security_map)
                    print_and_log(out_log_string, LOG__DEBUG)
            loop_iteration += 1
        # TODO: Move this functionality to the try-else statment
        if device_found_flag:
            out_log_string = "[*] scanning__ble::{0}\t-\tDevice Found and Generating Internals Map".format(scan_mode)
            print_and_log(out_log_string, LOG__DEBUG)
            # Generate the internals map for the device (initial map)
            user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
            out_log_string = "[*] scanning__ble::{0}\t-\tDisconnecting from target device".format(scan_mode)
            print_and_log(out_log_string, LOG__DEBUG)
        else:
            output_log_string = "[-] scanning__ble::Unable to find target device [ {0} ]".format(target_device)
            print_and_log(output_log_string, LOG__ENUM)
    # Pokey Scan
    elif scan_mode == "pokey":
        # Performing Pokey Scan of the Target Device (i.e. minimal writes)
        #print("[*] Poking Scan being Performed Against Target [{0}]".format(target_device))
        out_log_string = "[*] Poking Scan being Performed Against Target [{0}]".format(target_device)
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
    # Bruteforce Scan
    elif scan_mode == "bruteforce":
        # Performing Bruteforce Scan of the Target Device (i.e. loud bruteforce writes)
        #print("[*] Bruteforce Scan being Performed Against Target [{0}]".format(target_device))
        out_log_string = "[*] Bruteforce Scan being Performed Against Target [{0}]".format(target_device)
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
    # Unknown/Unrecognized Scan Mode
    else:
        #print("[!] Unknown Scan Mode [{0}] Passed..... Exiting".format(scan_mode))
        out_log_string = "[!] Unknown Scan Mode [{0}] Passed..... Exiting".format(scan_mode)
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
        #exit 1
        return None
    ## Performing Post-Processing 
    #print("[*] Performing the Post-Processing of Collected Scan Data")
    out_log_string = "[*] Performing the Post-Processing of Collected Scan Data"
    print_and_log(out_log_string)
    print_and_log(out_log_string, LOG__ENUM)
    print_and_log(out_log_string, LOG__DEBUG)
    # Generated Map Information
    out_log_string = "[*] Generated Maps:\n\tLandmines:\t\t[ {0} ]\n\tSecurity:\t\t[ {1} ]".format(landmine_map, security_map)
    print_and_log(out_log_string)
    print_and_log(out_log_string, LOG__ENUM)
    print_and_log(out_log_string, LOG__DEBUG)
    ## Sanity check that Device Objects/Structures were created
    # Grabbing user_device information      TODO: Remove/Replace this?
    if user_device is not None:
        # (Re-)Connection Check
        user_device.Reconnect_Check()
        # Device Internals Map Information
        out_log_string = "[*] Device Internals Map:\t\t[ {0} ]".format(user_device__internals_map)
        print_and_log(out_log_string, LOG__DEBUG)
        # Create Device Properties Array
        device_properties_array = bluetooth_utils.dbus_to_python(user_device.device_properties.GetAll(bluetooth_constants.DEVICE_INTERFACE))
        out_log_string = "[*] Post processing to follow....."
        print_and_log(out_log_string, LOG__DEBUG)
    else:
        device_properties_array = None
        output_log_string = "[*] No post processing for the target device... No device object created"
        print_and_log(output_log_string)
        print_and_log(output_log_string, LOG__DEBUG)
        print_and_log(output_log_string, LOG__ENUM)
        # Exit the function call since nothing else can be done
        return None
    # Test if previous scanning worked
    if user_device__internals_map == UNKNOWN_VALUE:
        out_log_print = "[-] No Internal Map Generated:\t\t[ {0} ]".format(user_device__internals_map)
        print_and_log(out_log_print, LOG__DEBUG)
        #continue
    # Passive Scan; TODO: Add processing to this information
    elif scan_mode == "passive":
        out_log_string = "[*] Passive Scan Analsysis"
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
        # Call to function for printing out information
        post_processing__ble__scan_analysis(user_device, user_device__internals_map, device_properties_array, scan_mode)
    # Naggy Scan
    elif scan_mode == "naggy":
        #print("[*] Nag Scan Analysis")
        out_log_string = "[*] Nag Scan Analysis"
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
        # Call to function for printing out information
        post_processing__ble__scan_analysis(user_device, user_device__internals_map, device_properties_array, scan_mode)
        # Top Level GAP info
        # Characteristics - Initial Values
        # Characteristics - Final Mass Read Values
        # Full formatted print out of the entire device map
    # Pokey Scan
    elif scan_mode == "pokey":
        #print("[*] Poke Scan Analysis")
        out_log_string = "[*] Poke Scan Analysis"
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
        # Top Level GAP info
        # Full Initial Map printout
        # Full End Map printout
    # Bruteforce Scan
    elif scan_mode == "bruteforce":
        #print("[*] Bruteforce Scan Analysis")
        out_log_string = "[*] Bruteforce Scan Analysis"
        print_and_log(out_log_string)
        print_and_log(out_log_string, LOG__ENUM)
        # Top Level GAP info
        # Full print of the initial map
        # Full print of the end map
    # Note: No need for an "Unknown Scan Mode" here since if that has occurred then the code will have exited earlier in the function
    # Disconnect from the device
    user_device.Disconnect()
    #print("[+] Completed BLE Scan of Mode [{0}] on Target Device [{1}]".format(scan_mode, target_device))
    out_log_string = "[+] Completed BLE Scan of Mode [{0}] on Target Device [{1}]".format(scan_mode, target_device)
    print_and_log(out_log_string)
    print_and_log(out_log_string, LOG__ENUM)

# Function for Input-Based Enumeraiton of Targets (Test Space)
def enumerate__user_targets(input__processed_data):
    ## Testing taking input of potential targets; TODO: Incorporate into the rest of the larger codebase
    #import json

    # Variables for Usage
    if not input__processed_data:
        input__processed_data = "/tmp/processed_data.txt"
    processed_data = None
    item_number__name = 1
    user_input_check = False
    output_log_string = ""

    # Read in the JSON Dictionary
    output_log_string = "[*] Beginning Target Selection Process for Device Enumeration"
    print_and_log(output_log_string)
    with open(input__processed_data) as pdata_repo:
        processed_data = json.load(pdata_repo)

    # Enumerate the unique name targets
    for unique_name in processed_data:
        #print("[*] {1}\)\tDevice Name:\t\t[ {0} ]".format(unique_name, item_number__name))
        output_log_string = "{1})\t\tDevice Name:\t\t[ {0} ]".format(unique_name, item_number__name)
        print_and_log(output_log_string)
        item_number__name += 1

    # Request a choice from the user
    user_selection = input("Select a device name from above to examine:\t")
    user_input_check = False
    while not user_input_check:
        user_input_check = check_and_validate__user_selection(user_selection, item_number__name)
    #print("[*] Examining Device Selection\t[ {0} ]".format(user_selection))
    name_list = list(processed_data)
    user_selected_name = name_list[int(user_selection)-1]
    output_log_string = "[*] Examining Device Selection\t[ {0} ] with Name\t[ {1} ]".format(user_selection, user_selected_name)
    print_and_log(output_log_string)

    # Iterate through all associated bluetooth addresses/targets
    for known_address in processed_data[user_selected_name]:
        output_log_string = "-----\n- Known Address:\t\t{0}\n-----".format(known_address)
        print_and_log(output_log_string)

        # Begin the Scanning and enumeration process
        scanning__ble(known_address)

# Function for Multiple Input-Based Enumeraiton of Targets with Fully Automated Enumeration
def enumerate__assets_of_interest(input__processed_data_files, scan_mode):
    ## Prepare variables for this function
    # Variables for Usage
    if not input__processed_data_files:
        #input__processed_data = "/tmp/processed_data.txt"
        out_log_string = "[-] bleep::enumerate__assets_of_interest - Error: No Input Files provided... Exiting"
        print_and_log(out_log_string, LOG__DEBUG)
        exit
    processed_data = None
    #item_number__name = 1
    #user_input_check = False
    output_log_string = "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< BLEEP - AoI Mode >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
    print_and_log(output_log_string, LOG__ENUM)

    ## Iterate through all the provided files; used to examine all provides AoIs in the provided input files
    for input_file in input__processed_data_files:
        output_log_string = "[*] Enumerating Assets of Interest within Input File:\t-[ {0} ]-".format(input_file)
        print_and_log(output_log_string)
        print_and_log(output_log_string, LOG__ENUM)

        # Read in the JSON Dictionary
        output_log_string = "[*] Beginning Target Selection Process for Device Enumeration"
        print_and_log(output_log_string)
        print_and_log(output_log_string, LOG__ENUM)
        with open(input_file) as pdata_repo:
            processed_data = json.load(pdata_repo)

        # Debuggin Information
        if dbg != 0:
            output_log_string = "[?] Read in Processed Data:\t\t[ {0} ]".format(processed_data)
            print_and_log(output_log_string, LOG__DEBUG)

        # Enumerate the processed data
        for asset_selection_criteria in processed_data:
            output_log_string = "[*] ================================<\tAsset of Interest Criteria:\t\t[ {0} ]\t>================================".format(asset_selection_criteria)
            print_and_log(output_log_string)
            print_and_log(output_log_string, LOG__ENUM)

            # Iterate through all associated bluetooth addresses/targets
            for asset_of_interest in processed_data[asset_selection_criteria]:
                output_log_string = "-----\n- Asset of Interest:\t\t{0}\n-----".format(asset_of_interest)
                print_and_log(output_log_string)
                print_and_log(output_log_string, LOG__ENUM)

                #try:
                # Begin the Scanning and Enumeratio Process
                scanning__ble(asset_of_interest, scan_mode)
                #except Exception as e:
                #    output_log_string = "[-] enumerate__assets_of_interest::scanning__ble() function call failed"
                #    print_and_log(output_log_string)
                #    print_and_log(output_log_string, LOG__DEBUG)

                # Set in a time wait to allow devices to get ready
                time.sleep(8)       # Large space to help prevent a race condition?

            output_log_string = "[+] ================================<\tEnumerated All AoI for Criteria [ {0} ]\t>================================".format(asset_selection_criteria)
            print_and_log(output_log_string)
            print_and_log(output_log_string, LOG__ENUM)

    ## Completed Automated Enumeration Scanning
    output_log_string = "[+] Completed Automated Enumeration of All Processed Data Input Files"
    print_and_log(output_log_string)
    print_and_log(output_log_string, LOG__ENUM)

# Function for Agent Testing; Note: May not work due to how properties are being called
def testing__agent_to_device__pairing():
    # Set Configuration of the D-Bus GLib MainLoop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # Set the bus property to the SystemBus()
    bus = dbus.SystemBus()

    # Set the capabilties of the agent(??)
    #capability = "KeyboardDisplay"
    capability = "NoInputNoOutput"      # Changing to force this; (potentially) limits interactibility with BLE targets?

    ## Option Parsing from Original simple-agent BlueZ example code
    #parser = OptionParser()
    #parser.add_option("-i", "--adapter", action="store",
    #				type="string",
    #				dest="adapter_pattern",
	#				default=None)
    #parser.add_option("-c", "--capability", action="store",
	#				type="string", dest="capability")
    #parser.add_option("-t", "--timeout", action="store",
	#				type="int", dest="timeout",
    #				default=60000)
	#(options, args) = parser.parse_args()
    #if options.capability:
	#	capability  = options.capability

    # Set the path and Agent objects
    path = bluetooth_constants.AGENT_NAMESPACE #"/test/agent"   # Should be the same as the default?
    agent = system_dbus__bluez_generic_agent(bus, path)

    # Set the MainLoop object
    agent.mainloop = GObject.MainLoop()

    # Configure the Device Object and Manager Class properties
    #agent.device_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE)
    agent.device_object = bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE.rstrip("/"))
    agent.manager = dbus.Interface(agent.device_object, bluetooth_constants.MANAGER_INTERFACE)
    agent.manager.RegisterAgent(path, capability)

    # Print Agent Registration Completed
    print("Agent registered")

    ## From simple-agent example
    # Fix-up old style invocation (BlueZ 4)
    #if len(args) > 0 and args[0].startswith("hci"):
    #	options.adapter_pattern = args[0]
	#	del args[:1]
    #
	#if len(args) > 0:
    #	device = bluezutils.find_device(args[0],
	#					options.adapter_pattern)
    #	dev_path = device.object_path
	#	agent.set_exit_on_release(False)
    #	device.Pair(reply_handler=pair_reply, error_handler=pair_error,
	#							timeout=60000)
    #	device_obj = device
	#else:
    #	manager.RequestDefaultAgent(path)

    # Test Manager API Agent Request
    agent.manager.RequestDefaultAgent(path)

    # Run the MainLoop
    agent.mainloop.run()

    # Unregister Agent
    #adapter.UnregisterAgent(path)      # Is this the adapter for the Manager?? Check the git.kernel documentation
    #print("Agent unregistered")

# Function for Testing Agent and Pairing
def basic_agent_pair_testing():
    # Create a test bus
    test_bus = dbus.SystemBus()
    # Create a test agent
    test_agent = system_dbus__bluez_generic_agent(test_bus)
    # Create the agent user interface
    test_agent_ui = system_dbus__bluez_agent_user_interface(test_bus, test_agent)
    # Run the "unit test" for the Agent UI
    test_agent_ui.testing__agent_to_device__pairing()

# Function for Testing Agent Pairing to a Provided Device Object
def basic_agent_pair_testing__device(ble_device_class_object=None):
    # Create a test bus
    test_bus = dbus.SystemBus()
    # Create a test agent
    test_agent = system_dbus__bluez_generic_agent(test_bus)
    if device_object is None:
        # Search for Local BLE Devices
        discovered_devices = create_and_return__bluetooth_scan__discovered_devices()
        # Show found devices
        print(discovered_devices)
        # Select target device
        target_device = discovered_devices[3][0]
        # Create the BLE Device Class Object
        ble_device = system_dbus__bluez_device__low_energy(target_device)
    else:
        ble_device = ble_device_class_object
    # Connect to the BLE Device to generate the internal class structures
    ble_device.Connect()
    # Create the agent user interface
    test_agent_ui = system_dbus__bluez_agent_user_interface(test_bus, ble_device.device_path, test_agent)
    # Test pairing to the specific device; NOTE: Might be an issue about proxying dbus adapters/interfaces..... DEEP DIVE THIS!!! Take notes :P
    test_agent_ui.testing__agent_to_device__pairing()

# Function for Testing Agent-Thread Usage
def basic_agent__thread_test():
    # Create a test bus
    test_bus = dbus.SystemBus()
    # Create Agent UI object
    agent_ui = system_dbus__bluez_agent_user_interface(test_bus)
    # Run the Agent thread
    agent_ui.agent__test_thread()
    # Find a Device Object
    #discovered_devices = create_and_return__bluetooth_scan__discovered_devices()
    user_selection = user_interaction__find_and_return__pick_device()
    user_selected_device = user_selection[0]        # The 0th item is the Bluetooth Address and the 1st item is the Bluetooth Name
    # Create a Device Object
    #user_device, user_device__mapping, landmine_map, security_map = connect_and_enumerate__bluetooth__low_energy(user_selected_device)
    user_device = system_dbus__bluez_device__low_energy(user_selected_device)
    # Connect to Device Object
    #user_device.Connect()
    #user_device.Disconnect()
    # Create the Device Interface without Abusing Higher Level Functions
    user_device.create_and_set__device_interface()
    # Pair to Device Object
    #user_device.device_interface.Pair()     # Leads to "Authentication Canceled" error
    user_device.Pair()                      # Replacement for above using BLE Device Class function
    # TODO: Attempt pairing but WHILE providing special pairing keywords

# Function for Awaiting ServicesResolved to be Completed OR Timeout
def await__services_resolved(device_class_object):
    out_log_string = "[*] await__services_resolved::Waiting for device [ {0} ] services to be resolved".format(device_class_object.device_address)
    # Variables for tracking time to wait for "ServicesResolved"
    time_sleep__seconds = 0.5
    total_time_passed__seconds = 0
    while not device_class_object.find_and_get__device_property("ServicesResolved"):     # TODO: Add in timeout here too; NOTE: This may be causing an issue?? Maybe not?? Need to flesh out when device is enumerated versus when connection is confirmed
        # Hang and wait to make sure that the services are resolved
        time.sleep(time_sleep__seconds)     # Sleep to give time for Services to Resolve
        out_log_string += "."
        # Check for abandoning "ServicesResolved"
        if total_time_passed__seconds > timeout_limit__in_seconds:
            # Configured seconds have passed attempting to resolve services, quit and move on
            output_log_string = "\n[-] connect_and_enumerate__bluetooth__low_energy::Service Resolving Error:\tTimeout Limit Reached"
            print_and_log(output_log_string)
            print_and_log(output_log_string, LOG__DEBUG)
            print_and_log(output_log_string, LOG__ENUM)
            # Exit the function
            break
        # Add to the timeout counter
        total_time_passed__seconds += time_sleep__seconds
    print_and_log(out_log_string, LOG__DEBUG)
    if device_class_object.find_and_get__device_property("ServicesResolved"):
        output_log_string = "\n[+] connect_and_enumeration__bluetooth__low_energy::Device services resolved"
    else:
        output_log_string = "\n[-] connect_and_enumeration__bluetooth__low_energy::Device services not resolved"
    print_and_log(output_log_string)
    print_and_log(output_log_string, LOG__ENUM)
    print_and_log(output_log_string, LOG__DEBUG)
    # Return the value of the ServicesResolved
    return device_class_object.find_and_get__device_property("ServicesResolved")

# Function for Attempting Device Object Enumeration - At Device Interface Level
def attempt__device_enumerate(device_class_object):
    out_log_string = "[*] attempt__device_enumerate::Attempting to enumerate device class object at device interface level"
    print_and_log(out_log_string, LOG__DEBUG)
    # Try-Except-Else-Finally Statement for Enumerating Device Information
    try:
        # Identify and Set Device Object Properties
        device_class_object.identify_and_set__device_properties(device_class_object.find_and_get__all_device_properties())        # Note: The call to find and get all device properties can print out high level device information
    except Exception as e:
        device_class_object.error_buffer = device_class_object.understand_and_handle__dbus_errors(e)
        out_log_string = "[-] attempt__device_enumerate::Exception Error Occurred\t-\tError Buffer:\t[ {0} ]\n\tError:\t\t[ {1} ]".format(device_class_object.error_buffer, e)
        print_and_log(out_log_string, LOG__DEBUG)
    else:
        out_log_string = "[*] attempt__device_enumerate::Alert! Try statement resolved without raising an exception"
        print_and_log(out_log_string, LOG__DEBUG)
    finally:
        out_log_string = "[*] attempt__device_enumerate::Completed attempt to enumerate device object"
        print_and_log(out_log_string, LOG__DEBUG)

# Function for Attempting to Generate a Provided Device Class Object's Service List
def attempt__generate_list__device_services(device_class_object):
    out_log_string = "[*] attempt__generate_list__device_services::Attempting to generate a list of device services"
    print_and_log(out_log_string, LOG__DEBUG)
    device_services_list = None
    # Try-Except-Else-Finally Statement for Generating a Services List
    try:
        # Create List of BLE Device Services
        device_services_list = device_class_object.find_and_get__device_introspection__services()
    except Exception as e:
        device_class_object.error_buffer = device_class_object.understand_and_handle__dbus_errors(e)
        out_log_string = "[-] attempt__generate_list__device_services::Exception Error Occurred\t-\tError Buffer:\t[ {0} ]\n\tError:\t\t[ {1} ]".format(device_class_object.error_buffer, e)
        print_and_log(out_log_string, LOG__DEBUG)
    else:
        out_log_string = "[*] attempt__generate_list__device_services::Alert! Try statement resolved without raising an exception"
        print_and_log(out_log_string, LOG__DEBUG)
    finally:
        out_log_string = "[*] attempt__generate_list__device_services::Completed attempted to generate list of device services"
        print_and_log(out_log_string, LOG__DEBUG)
    out_log_string = "[*] attempt__generate_list__device_services::Generated List:\t\t[ {0} ]".format(device_services_list)
    print_and_log(out_log_string, LOG__DEBUG)
    return device_services_list

# Function for Testing Agent-Thread Usage
def basic_agent__custom_pair__thread_test(custom=None):

    ## Internal Function Definitions

    # Internal Function for Enumerating a Device in Pretty Print (e.g. User Mode)
    #def 

    ## Main Code

    # Create a test bus
    test_bus = dbus.SystemBus()
    # Create Agent UI object
    agent_ui = system_dbus__bluez_agent_user_interface(test_bus)
    ## Run the Agent thread

    out_log_string = "[*] BLE Agent UI::Custom Thread\t-\tConfiguring the D-Bus GLib MainLoop in Preparation of Agent Thread Test"
    print_and_log(out_log_string, LOG__AGENT)
    # Set the configuration of the D-Bus GLib MainLoop
    #dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)   # Already hanlded by general script configuration
    # Initialize the GLib threads
    #dbus.mainloop.glib.threads_init()                       # Already handled by general script configuraiton
    out_log_string = "[*] BLE Agent UI::Custom Thread\t-\tCreating the MainLoop Structure"
    print_and_log(out_log_string, LOG__AGENT)
    # Create a MainLoop object 
    agent_loop = GLib.MainLoop()
    output_log_string = "[*] BLE Agent UI::Custom Thread\t-\tCreating the Agent Class Object"
    print_and_log(out_log_string, LOG__AGENT)
    # Create the Agent Class object
    agent = system_dbus__bluez_generic_agent(agent_ui.bus)
    output_log_string = "[*] BLE Agent UI::Custom Thread\t-\tSetting the Agent MainLoop Property"
    print_and_log(out_log_string, LOG__AGENT)
    # Set the Agent MainLoop Property
    agent.mainloop = agent_loop
    # Check if the device_object property exists
    if agent_ui.device_object is None:
        out_log_string = "[-] BLE Agent UI::Custom Thread\t-\tDevice Object not created.... Creating the Device Object"
        print_and_log(out_log_string, LOG__AGENT)
        agent_ui.device_object = agent_ui.bus.get_object(bluetooth_constants.BLUEZ_SERVICE_NAME, bluetooth_constants.BLUEZ_NAMESPACE.rstrip("/"))      # Note the REQUIREMENT to not have the end slash
    else:
        out_log_string = "[+] BLE Agent UI::Custom Thread\t-\tDevice Object exists.... Moving on to the Agent Manager"
        print_and_log(out_log_string, LOG__AGENT)
    output_log_string = "[*] BLE Agent UI::Custom Thread\t-\tCreating the Manager Object and Assigning to Agent Property"
    print_and_log(out_log_string, LOG__AGENT)
    # Create the Manager Property of the Agent Class Object
    agent.manager = dbus.Interface(agent_ui.device_object, bluetooth_constants.MANAGER_INTERFACE)
    if agent.manager is None:
        out_log_string = ("[-] BLE Agent UI::Custom Thread\t-\tError in Creating Agent Manager Object")
        print_and_log(out_log_string, LOG__AGENT)
    else:
        out_log_string = ("[+] BLE Agent UI::Custom Thread\t-\tSuccessfully Created Agent Manager Object")
        print_and_log(out_log_string, LOG__AGENT)
    # Set the capability that will be presented by the Agent
    #capability = "KeyboardDisplay"
    capability = "NoInputNoOutput"
    output_log_string = "[*] BLE Agent UI::Custom Thread\t-\tDetermining Capabilitiy of the Agent Manager".format(capability)
    print_and_log(out_log_string, LOG__AGENT)
    output_log_string = "[*] BLE Agent UI::Custom Thread\t-\tConfiguring Capabilitiy of the Agent known to the Agent Manager Object [ {0} ]".format(capability)
    print_and_log(out_log_string, LOG__AGENT)
    # Register the Agent to the Manager
    agent.manager.RegisterAgent(agent.path, capability)
    output_log_string = "[*] BLE Agent UI::Custom Thread\t-\tConfiguring the Agent's Thread"
    print_and_log(out_log_string, LOG__AGENT)
    # Create and Configure the Thread for the Agent
    agent.thread = threading.Thread(target=agent.start_agent, daemon=False)     # Note: May need to change to True?
    output_log_string = "[*] BLE Agent UI::Custom Thread\t-\tStarting the Agent Thread"
    print_and_log(out_log_string, LOG__AGENT)
    # Start the Agent Threat
    agent.thread.start()

    #agent_ui.agent__test_thread()
    # Find a Device Object
    #discovered_devices = create_and_return__bluetooth_scan__discovered_devices()
    user_selection = user_interaction__find_and_return__pick_device()
    user_selected_device = user_selection[0]        # The 0th item is the Bluetooth Address and the 1st item is the Bluetooth Name
    # Create a Device Object
    #user_device, user_device__mapping, landmine_map, security_map = connect_and_enumerate__bluetooth__low_energy(user_selected_device)
    user_device = system_dbus__bluez_device__low_energy(user_selected_device)
    # Connect to Device Object
    #user_device.Connect()
    #user_device.Disconnect()
    # Create the Device Interface without Abusing Higher Level Functions
    user_device.create_and_set__device_interface()
    # Check that the device exists (??)
    print("[?] User Device Object:\t{0}".format(user_device))
    # Pair to Device Object
    if custom is None:
        #user_device.device_interface.Pair()     # Leads to "Authentication Canceled" error
        user_device.Pair()                      # Replacement for above using BLE Device Class function
    # TODO: Attempt pairing but WHILE providing special pairing keywords
    else:
        user_device.Pair(reply_handler=agent_ui.pair_reply, error_handler=agent_ui.pair_error, timeout=30000)       # TODO: Force trigger of this command; might be cause of seen agent debug output?
    ## Output Device Statistics
    # Attempt to Resolved Services
    try:
        resolved_flag = await__services_resolved(user_device)
    except Exception as e:
        # Can store the below as a variable to contain the error returned
        error_capture = user_device.understand_and_handle__dbus_errors(e)
        out_log_string = "[!] BLE Agent UI::Error during resolution\t-\t[ {0} ]".format(e)
        print_and_log(out_log_string)
    if not resolved_flag:
        out_log_string = "[-] BLE Agent UI::Failed to Resolve Services with resolution of [ {0} ]".format(resolved_flag)
    else:
        out_log_string = "[+] BLE Agent UI::Able to Resolve Service with resolution of [ {0} ]".format(resolved_flag)
    print_and_log(out_log_string, LOG__AGENT)
    device_connected = user_device.find_and_get__device_property("Connected")
    ble_device_services_list = attempt__generate_list__device_services(user_device)
    out_log_string = "[?] BLE Agent UI::Custom Thread\t-\tData Dump:\n\tDevice Connected:\t[ {0} ]\n\tServices Resolved:\t[ {1} ]\n\tServices List:\t[ {2} ]".format(device_connected, resolved_flag, ble_device_services_list)
    print_and_log(out_log_string, LOG__AGENT)
    user_device__internals_map = user_device.enumerate_and_print__device__all_internals()
    print("---- Device ----")
    print(user_device)
    print("---- Internals Map ----")
    print(user_device__internals_map)
    print("-------[ PrEtTy PrInT ]--------")
    if user_device__internals_map != UNKNOWN_VALUE:
        pretty_print__gatt__dive_json(user_device, user_device__internals_map)
    else:
        out_log_string = "[-] BLE Agent UI::Unable to create device internals map [ {0} ]".format(user_device__internals_map)
        print_and_log(out_log_string, LOG__AGENT)
    print("===================[ Device Properties ]==========================")
    user_device.find_and_get__all_device_properties()
    print("=============================================")
    is_paired = user_device.find_and_get__device_property("Paired")
    print("Paired:\t\t{0}".format(is_paired))


# Function to Search for Nearby Devices and Provide Detailed Ouptut of Each Seen
def what_is_near_me():

    ## Variable Definitions
    # General D-Bus Object Paths
    #: The DBus Object Manager interface
    DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
    #: DBus Properties interface
    DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
    
    # General Bluez D-Bus Object Paths
    #: BlueZ DBus Service Name
    BLUEZ_SERVICE_NAME = 'org.bluez'
    #: BlueZ DBus adapter interface
    ADAPTER_INTERFACE = 'org.bluez.Adapter1'
    #: BlueZ DBus device Interface
    DEVICE_INTERFACE = 'org.bluez.Device1'

    # Bluez GATT D-Bus Object Paths
    #: BlueZ DBus GATT manager Interface
    GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
    #: BlueZ DBus GATT Profile Interface
    GATT_PROFILE_IFACE = 'org.bluez.GattProfile1'
    #: BlueZ DBus GATT Service Interface
    GATT_SERVICE_IFACE = 'org.bluez.GattService1'
    #: BlueZ DBus GATT Characteristic Interface
    GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
    #: BlueZ DBus GATT Descriptor Interface
    GATT_DESC_IFACE = 'org.bluez.GattDescriptor1'
    
    # Bluez Advertisment D-Bus object paths
    #: BlueZ DBus Advertising Manager Interface
    LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
    #: BlueZ DBus Advertisement Interface
    LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'
    
    # Bluez Media D-Bus object paths
    #: BlueZ DBus Media player Interface
    MEDIA_PLAYER_IFACE = 'org.bluez.MediaPlayer1'

    ## Internal Classes

    # MediaPlayerError Class Definition
    class MediaPlayerError(Exception):
        """Custom exception"""
        pass

    # MediaPlayer Class Definition
    class MediaPlayer:
        """Bluetooth MediaPlayer Class.
        This class instantiates an object that is able to interact with
        the player of a Bluetooth device and get audio from its source.
        """

        # Init Function
        def __init__(self, device_addr):
            """Default initialiser.

            Creates the interface to the remote Bluetooth device.

            :param device_addr: Address of Bluetooth device player to use.
            """
            self.player_path = _find_player_path(device_addr)
            self.player_object = get_dbus_obj(self.player_path)
            self.player_methods = get_dbus_iface(
                MEDIA_PLAYER_IFACE, self.player_object)
            self.player_props = get_dbus_iface(
                dbus.PROPERTIES_IFACE, self.player_object)

        # Detection of Browsing Capability Function
        @property
        def browsable(self):
            """If present indicates the player can be browsed using MediaFolder
            interface."""
            return self.player_props.Get(
                MEDIA_PLAYER_IFACE, 'Browsable')

        # Detection of Searching Capability Function
        @property
        def searchable(self):
            """If present indicates the player can be searched using
            MediaFolder interface."""
            return self.player_props.Get(
                MEDIA_PLAYER_IFACE, 'Searchable')

        # Obtain Track Metadata - As Dictionary
        @property
        def track(self):
            """Return a dict of the track metadata."""
            return self.player_props.Get(
                MEDIA_PLAYER_IFACE, 'Track')

        # Obtain Device Object Path
        @property
        def device(self):
            """Return Device object path"""
            return self.player_props.Get(
                MEDIA_PLAYER_IFACE, 'Device')

        # Obtain Playlist Object Path
        @property
        def playlist(self):
            """Return the Playlist object path."""
            return self.player_props.Get(
                MEDIA_PLAYER_IFACE, 'Playlist')

        # Obtain Equalizer Value
        @property
        def equalizer(self):
            """Return the equalizer value."""
            return self.player_props.Get(
                MEDIA_PLAYER_IFACE, 'Equalizer')

        # Set Equalizer Value
        @equalizer.setter
        def equalizer(self, value):
            """Possible values: "off" or "on"."""
            self.player_props.Set(
                MEDIA_PLAYER_IFACE, 'Equalizer', value)

        # Obtain the Player Name
        @property
        def name(self):
            """Return the player name"""
            return self.player_props.Get(
                MEDIA_PLAYER_IFACE, 'Name')

        # Obtain Repeat Value
        @property
        def repeat(self):
            """Return the repeat value"""
            return self.player_props.Get(
                MEDIA_PLAYER_IFACE, 'Repeat')

        # Set Repeat Value
        @repeat.setter
        def repeat(self, value):
            """Possible values: "off", "singletrack", "alltracks" or "group"""
            self.player_props.Set(
                MEDIA_PLAYER_IFACE, 'Repeat', value)

        # Obtain Shuffle Value
        @property
        def shuffle(self):
            """Return the shuffle value"""
            return self.player_props.Get(MEDIA_PLAYER_IFACE, 'Shuffle')

        # Set Shuffle Value
        @shuffle.setter
        def shuffle(self, value):
            """"Possible values: "off", "alltracks" or "group" """
            self.player_props.Set(MEDIA_PLAYER_IFACE, 'Shuffle', value)

        # Obtain Status Value
        @property
        def status(self):
            """Return the status of the player
            Possible status: "playing", "stopped", "paused",
            "forward-seek", "reverse-seek" or "error" """
            return self.player_props.Get(MEDIA_PLAYER_IFACE, 'Status')

        # Obtain Player Sub-Type
        @property
        def subtype(self):
            """Return the player subtype"""
            return self.player_props.Get(MEDIA_PLAYER_IFACE, 'Subtype')

        # Obtain Player Type
        def type(self, player_type):
            """Player type. Possible values are:

                    * "Audio"
                    * "Video"
                    * "Audio Broadcasting"
                    * "Video Broadcasting"
            """
            self.player_props.Set(
                MEDIA_PLAYER_IFACE, 'Type', player_type)

        # Obtain the Playback Position in Milliseconds
        @property
        def position(self):
            """Return the playback position in milliseconds."""
            return self.player_props.Get(MEDIA_PLAYER_IFACE, 'Position')

        # Call Function for Next Track
        def next(self):
            """Goes the next track and play it."""
            self.player_methods.Next()

        # Call Function for Play
        def play(self):
            """Resume the playback."""
            self.player_methods.Play()

        # Call Function for Pause
        def pause(self):
            """Pause the track."""
            self.player_methods.Pause()

        # Call Function for Stop
        def stop(self):
            """Stops the playback."""
            self.player_methods.Stop()

        # Call Function for Previous Track
        def previous(self):
            """Goes the previous track and play it"""
            self.player_methods.Previous()

        # Call Function for Fast Forward
        def fast_forward(self):
            """Fast forward playback, this action is only stopped
            when another method in this interface is called.
            """
            self.player_methods.FastForward()

        # Call Function for Rewind
        def rewind(self):
            """Rewind playback, this action is only stopped
            when another method in this interface is called.
            """
            self.player_methods.Rewind()

    ## Internal Functions

    # Internal Function for Getting D-Bus Objects
    def get_dbus_obj(dbus_path):
        """
        Get the the DBus object for the given path
        :param dbus_path:
        :return:
        """
        bus = dbus.SystemBus()
        return bus.get_object(constants.BLUEZ_SERVICE_NAME, dbus_path)

    # Internal Function for Getting D-Bus Interface
    def get_dbus_iface(iface, dbus_obj):
        """
        Return the DBus interface object for given interface and DBus object
        :param iface:
        :param dbus_obj:
        :return:
        """
        return dbus.Interface(dbus_obj, iface)

    # Internal Function for Getting all Managed Objects
    def get_managed_objects():
        """Return the objects currently managed by the DBus Object Manager."""
        bus = dbus.SystemBus()
        manager = dbus.Interface(bus.get_object(
            BLUEZ_SERVICE_NAME, '/'),
            DBUS_OM_IFACE)
        return manager.GetManagedObjects()

    # Internal Function to Search for a Media Device
    def search_media_device():
        managed_object = get_managed_objects()
        for path in get_managed_objects():
            print(f"Path:\t{path}")
            if managed_object[path].get(MEDIA_PLAYER_IFACE):
                print(f"Media Path?:\t{path}")

    # Internal Function to Search for a Player Device
    def search_player_device():
        mac_addr = None
        for dbus_path in get_managed_objects():
            print(f"D-Bus Path:\t{dbus_path}")
            if dbus_path.endswith('player0'):
                mac_addr = get_device_address_from_dbus_path(dbus_path)
                print(f"Found Player!:\t{dbus_path}")

    # Internal Function to Search for Media Players
    def find_media_players():
	    test_adapter = system_dbus__bluez_adapter()
	    custom_discovery_filter = {'Transport': 'auto'}
	    test_adapter.set_discovery_filter(custom_discovery_filter)
	    test_adapter.run_scan__timed()
	    search_media_device()

    # Internal Function to Enumerate Managed Objects Properties
    def enumerate_devices(managed_objects):
        for dbus_path, dbus_info in managed_objects.items():
            # Device Properties
            addr, name, alias, addr_type = None, None, None, None
            # Media Properties
            supported_uuids = None
            # Media Control Properties
            connected, player = None, None
            # Media Endpoint Properties
            endpoint_uuid, endpoint_codec, endpoint_vendor, endpoint_capabilities, endpoint_metadata, device_endpoint, endpoint_delay_reporting, endpoint_locations, endpoint_supported_context, endpoint_context, endpoint_qos = None, None, None, None, None, None, None, None, None, None, None
            # Media Transport Properties
            transport_device, transport_uuid, transport_codec, transport_configuration, transport_state, transport_delay, transport_volume, transport_endpoint, transport_location, transport_metadata, transport_links, transport_qos = None, None, None, None, None, None, None, None, None, None, None, None
            # Network Properties
            network_connected, network_interface, network_uuid = None, None, None
            ## Begin interface enumerations
            for interface_name, interface_properties in dbus_info.items():
                # Dissecting org.bluez.Device1
                if interface_name == "org.bluez.Device1":
                    if "Name" in interface_properties:
                        name = interface_properties["Name"]
                    if "Alias" in interface_properties:
                        alias = interface_properties["Alias"]
                    if "AddressType" in interface_properties:
                        addr_type = interface_properties["AddressType"]
                    if "Address" in interface_properties:
                        addr = interface_properties["Address"]
                    if "SupportedUUIDs" in interface_properties:
                        print(f"Supported UUIDs:\t{interface_properties['SupportedUUIDs']}")
                    print(f"Path:\t{dbus_path}\t\t\tName:\t{name}\t\t\tAlias:\t{alias}\t\t\tAddress Type:\t{addr_type}\t\t\tAddress:\t{addr}")
                # Dissecting org.bluez.Media1
                elif interface_name == "org.bluez.Media1":
                    if "SupportedUUIDs" in interface_properties:
                        supported_uuids = interface_properties["SupportedUUIDs"]
                        for uuid_val in supported_uuids:                # Note: These UUIDs are "List of 128-bit UUIDs that represents the supported Endpoint registration."
                            print(f"\t\tUUID Name:\t{bluetooth_utils.get_name_from_uuid(uuid_val)}\t\t\tUUID:\t{uuid_val}")
                    print(f"Path:\t{dbus_path}\t\tSupported UUIDs:\t{supported_uuids}")
                # Dissecting org.bluez.MediaControl1; Note: Most functionality is depreciated as of 2025/02/13
                elif interface_name == "org.bluez.MediaControl1":
                    if "Connected" in interface_properties:
                        connected = interface_properties["Connected"]
                    if "Player" in interface_properties:
                        player = interface_properties["Player"]
                    print()
                # Dissecting org.bluez.MediaEndpoint1
                elif interface_name == "org.bluez.MediaEndpoint1":
                    if "UUID" in interface_properties:
                        endpoint_uuid = interface_properties["UUID"]
                    if "Codec" in interface_properties:
                        endpoint_codec = interface_properties["Codec"]
                    if "Vendor" in interface_properties:
                        endpoint_vendor = interface_properties["Vendor"]
                    if "Capabilities" in interface_properties:
                        endpoint_capabilities = interface_properties["Capabilities"]
                    if "Metadata" in interface_properties:
                        endpoint_metadata = interface_properties["Metadata"]
                    if "Device" in interface_properties:
                        device_endpoint = interface_properties["Device"]
                    if "DelayReporting" in interface_properties:
                        endpoint_delay_reporting = interface_properties["DelayReporting"]
                    if "Locations" in interface_properties:
                        endpoint_locations = interface_properties["Locations"]
                    if "SupportedContext" in interface_properties:
                        endpoint_supported_context = interface_properties["SupportedContext"]
                    if "Context" in interface_properties:
                        endpoint_context = interface_properties["Context"]
                    if "QoS" in interface_properties:
                        endpoint_qos = interface_properties["QoS"]
                    print()
                # Dissecting org.bluez.MediaTransport1
                elif interface_name == "org.bluez.MediaTransport1":
                    if "Device" in interface_properties:
                        transport_device = interface_properties["Device"]
                    if "UUID" in interface_properties:
                        transport_uuid = interface_properties["UUID"]
                    if "Codec" in interface_properties:
                        transport_codec = interface_properties["Codec"]
                    if "Configuration" in interface_properties:
                        transport_configuration = interface_properties["Configuration"]
                    if "State" in interface_properties:
                        transport_state = interface_properties["State"]
                    if "Delay" in interface_properties:
                        transport_delay = interface_properties["Delay"]
                    if "Volume" in interface_properties:
                        transport_volume = interface_properties["Volume"]
                    if "Endpoint" in interface_properties:
                        transport_endpoint = interface_properties["Endpoint"]
                    if "Location" in interface_properties:
                        transport_location = interface_properties["Location"]
                    if "Metadata" in interface_properties:
                        transport_metadata = interface_properties["Metadata"]
                    if "Links" in interface_properties:
                        transport_links = interface_properties["Links"]
                    if "QoS" in interface_properties:
                        transport_qos = interface_properties["QoS"]
                    print()
                # Dissecting org.bluez.Network1
                elif interface_name == "org.bluez.Network1":
                    if "Connected" in interface_properties:
                        network_connected = interface_properties["Connected"]
                    if "Interface" in interface_properties:
                        network_interface = interface_properties["Interface"]
                    if "UUID" in interface_properties:
                        network_uuid = interface_properties["UUID"]
                # Unknown Interface Return
                else:
                    print(f"\tUncatelogued Bluetooth Interface:\t{interface_name}\t\t\tInfo:\t{interface_properties}")

    print("[*] Finding out what is nearby me...")

    # Search for Nearby Devices and Enumerate Informaiton
    find_media_players()
    managed_objects = get_managed_objects()
    enumerate_devices(managed_objects)

    print("[+] Completed Searching for What is Nearby")

### Main Code

# Main code function        ## TODO: Setup the python interactive version of the main function, but have it pre-generate the adapter and object_manger interfaces
def main(argv):
    # Welcome Message for the Tool
    output_log_string = "----------------------------\\\n\tBluetooth Landscape Exploration & Enumeration Platform\n\t\\----------------------------"
    print_and_log(output_log_string)

    #print("[*] Start Main()")
    out_log_string = "Note: Platform is defaulted to leverage HCI0"
    print_and_log(out_log_string)
    # Varibales for main()
    inputFile = ''
    outputFile = ''
    runMode = None
    target_device = None
    input_files = None
    try:
        #opts, args = getopt.getopt(argv, "hi:o:m:", ["in-file=","out-file=","mode="])
        opts, args = getopt.getopt(argv, "hm:i:d:", ["mode=","input=","device="])       # Note: Arguments that require an argument should be followed by a colon (:)
    except getopt.GetoptError:
        print('./bleep.py -m <runMode>')
    #print("Opts: [ {0} ]\nArgs: [ {1} ]".format(opts, args))
    # Parse the arguments passeed to the code/script
    for opt, arg in opts:
        # Check if the help menu is requested
        if opt == '-h':
            print('./bleep.py -m <runMode> [-device=<device_address>] [-i <input_file>]')
            sys.exit()
        #elif opt in ("-i", "--in-file"):
        #    inputFile = arg
        #elif opt in ("-o", "--out-file"):
        #    outputFile = arg
        # See what operation mode is requested
        else:
            # Check for the operating mode
            if opt in ("-m", "--mode"):
                if dbg != 0:    # ~!~
                    print("[?] Run Mode Debug:\n\tOpt:\t{0}\n\tArg:\t{1}".format(opt, arg))
                runMode = arg
            ## Assumption is that target(s) is given as a single device or as a list of targets
            # Check for a target device having been passed          # TODO: Still having issues trying to pass a specific target device address as an argument
            if opt in ("-d", "--device"):
                if dbg != 1:
                    print("[+] Target Device Passed:\t\t[ {0} ]".format(arg))
                # TODO: Add a bluetooth address Regex Check that the user supplied address is formatted/valid Bluetooth MAC
                # Check if a known device is passed
                if arg == 'lightorb':
                    target_device = 'F0:98:7D:0A:05:07'
                elif arg == 'blectf':
                    target_device = 'CC:50:E3:B6:BC:A6'
                elif arg == 'picow':
                    target_device = 'D8:3A:DD:2D:9D:66'
                else:
                    # Configure the target_device to hold the argument
                    target_device = arg
            # Check for input files to the tool
            elif opt in ("-i", "--input"):
                if dbg != 0:
                    print("[+] Input File(s) Passed:\t\t[ {0} ]".format(arg))
                input_files = arg.split(",")
    #print("Input file is:\t{0}".format(inputFile))
    #print("Output file is:\t{1}".format(outputFile))
    # Debugging Arguments to the BIP script
    if dbg != 0:    # ~!~
        print("[?] Debugging Arguments:\n\tArgs:\t{0}\n\tOpts:\t{1}\n\tRun Mode:\t{2}\n\tInput File(s):\t{3}".format(args, opts, runMode, input_files))
    # Checking the Run Mode for Main()
    if runMode == "user":
        # Call the User Interaction Exploration Template
        print("[*] Starting User Interaction Exploration")
        try:
            if target_device is not None:
                if dbg != 0:
                    out_log_string = "[*] Calling User Mode with a Target Device of [ {0} ]".format(target_device)
                    print_and_log(out_log_string, LOG__USER)
                check_and_explore__bluetooth_device__user_selected(target_device)
            else:
                check_and_explore__bluetooth_device__user_selected()
        except dbus.exceptions.DBusException:
            print("[-] D-Bus Error Raised: Likely Due to Missing Bluetooth Adapter")
            print("\tExiting.....")
            exit
    elif runMode == "debug":
        # Call to a command interface for debugging a device
        print("[*] Starting Debug Command Interface")
    elif runMode == "blectf":
        # Call to run example of completing the BLE CTF (Original)
        print("[*] Starting BLE CTF Completion")
        ble_ctf__perform_device_completion()
    elif runMode == "test":
        # Call to run testing script(s) to debug running
        user_device, user_device__mapping, dict_data, introspect_map = debug__dbus_interface__testing()
    elif runMode == "picow":
        # Call to the Pico-W testing script(s)
        debug__testing__pico_w()
    ## Function Modes for Bluetooth Low Energy (BLE) Scanning
    # Mode for BLE - Passive Scan
    elif runMode == "ble_passive":
        # Set the scanning mode
        scan_mode = "passive"
        if target_device != None:
            try:
                # Call the BLE scanning function with Passive Scan mode passed
                scanning__ble(target_device, scan_mode)
            except dbus.exceptions.DBusException:
                print("[-] D-Bus Error Raised: Likely Due to Missing Bluetooth Adapter")
                print("\tExiting.....")
                exit
        else:
            print("[-] Use of this mode requires a passed BLE target address")
    # Mode for BLE - Naggy Scan
    elif runMode == "ble_naggy":
        # Set the scanning mode
        scan_mode = "naggy"
        if target_device != None:
            try:
                # Call the BLE scanning function with Naggy Scan mode passed
                scanning__ble(target_device, scan_mode)
            except dbus.exceptions.DBusException:
                print("[-] D-Bus Error Raised: Likely Due to Missing Bluetooth Adapter")
                print("\tExiting.....")
                exit
        else:
            print("[-] Use of this mode requires a passed BLE target address")
    # Mode for BLE - Pokey Scan
    elif runMode == "ble_pokey":
        # Set the scanning mode
        scan_mode = "pokey"
        if target_device != None:
            try:
                # Call the BLE scanning function with Pokey Scan mode passed
                scanning__ble(target_device, scan_mode)
            except dbus.exceptions.DBusException:
                print("[-] D-Bus Error Raised: Likely Due to Missing Bluetooth Adapter")
                print("\tExiting.....")
                exit
        else:
            print("[-] Use of this mode requires a passed BLE target address")
    # Mode for BLE - Brute Force Scan
    elif runMode == "ble_bruteforce":
        # Set the scanning mode
        scan_mode = "bruteforce"
        if target_device != None:
            try:
                # Call the BLE scanning function with Bruteforce Scan mode passed
                scanning__ble(target_device, scan_mode)
            except dbus.exceptions.DBusException:
                print("[-] D-Bus Error Raised: Likely Due to Missing Bluetooth Adapter")
                print("\tExiting.....")
                exit
        else:
            print("[-] Use of this mode requires a passed BLE target address")
    # Mode for Data Input - Unique Names Enumeration Mode; Note: Requires User Input
    elif runMode == "scratch":
        # Setting the target file passed
        input_file = "/tmp/processed_data.txt"
        # Set the scnaning mode
        scan_mode = "passive"
        # Call the Scratch Space function
        #scratch_space()
        enumerate__user_targets(input_file)
    # Mode for Data Input - Multiple Files Automatic Enumeration Mode; Note: Does NOT Require User Input
    elif runMode == "assets_of_interest":
        # Check for passed files (REQUIRED)
        if not input_files:
            print("[-] Input files have not been provided with the '-i/--input' flag... Exiting")
            exit
        else:
            print("[+] Input files provided [ {0} ]".format(input_files))
        # Set the scanning mode
        scan_mode = "passive"
        ## TODO: Allow for variation in scan type
        # Call the Assets of Interest Enumeration Function
        enumerate__assets_of_interest(input_files, scan_mode)
    else:
        print("[-] Unknown Run Mode... Exiting")
    print("[+] Finished Main()")

# Definition for allowing CLI BLEEP execution
if __name__ == "__main__":
    main(sys.argv[1:])


##### Everything underhere gets run after the main BLEEP execution

## Figuring out UUID List Generation
import yaml

# List of Reference files with UUID (short) defined within them
list_of_uuid_files = ['References/descriptors.yaml', 'References/characteristic_uuids.yaml', 'References/service_uuids.yaml']

# Function to read the reference YAML file
def read_reference_yaml(file_path):
    with open(file_path, 'r') as file:
        reference_config = yaml.safe_load(file)
        file.close()
    return reference_config
# Note: Each element's 'id' will tell if the item is a descriptor or characteristic

# Function to generate the UUID dictionary
def generate_uuid_dict(first_two_octets, fifth_to_end_octets, reference_config):
    generated_uuid_dict = { "Services" : {},
                            "Characteristics" : {},
                            "Descriptors" : {},
                            "Unkonwns" : {} }
    for uuid_list in reference_config['uuids']:
        short_uuid = uuid_list['uuid']
        uuid_name = uuid_list['name']
        uuid_id = uuid_list['id']
        # Create full UUID string
        full_uuid_string = "{0}{1:x}-{2}".format(first_two_octets, short_uuid, fifth_to_end_octets)
        # Determine what type of UUID is being created
        if "bluetooth.service" in uuid_id:
            #generated_uuid_dict["Services"] = {full_uuid_string : uuid_name}
            generated_uuid_dict["Services"].update({full_uuid_string : uuid_name})
        elif "bluetooth.characteristic" in uuid_id:
            #generated_uuid_dict["Characteristics"] = {full_uuid_string : uuid_name}
            generated_uuid_dict["Characteristics"].update({full_uuid_string : uuid_name})
        elif "bluetooth.descriptor" in uuid_id:
            #generated_uuid_dict["Descriptors"] = {full_uuid_string : uuid_name}
            generated_uuid_dict["Descriptors"].update({full_uuid_string : uuid_name})
        else:
            generated_uuid_dict["Unknowns"].update({full_uuid_string : {
                                                    "Name" : uuid_name,
                                                    "ID" : uuid_id
                                                    }})
    return generated_uuid_dict

# Function for merging UUID dictionaries
def merge_generated_uuid_dicts(main_uuid_dict, supplementary_uuid_dict):
    for subset in main_uuid_dict:
        main_uuid_dict[subset].update(supplementary_uuid_dict[subset])

# Read in the Reference Files
descriptors_reference = read_reference_yaml(list_of_uuid_files[0])
characteristic_reference = read_reference_yaml(list_of_uuid_files[1])
service_reference = read_reference_yaml(list_of_uuid_files[2])

# Variables for Default Bluetooth UUID String Format
bluetooth_standard__front_uuid = "0000"
bluetooth_standard__end_uuid = "0000-1000-8000-00805f9b34fb"

# Generate and Combine Generated Dictionaries
desc_reference_dict = generate_uuid_dict(bluetooth_standard__front_uuid, bluetooth_standard__end_uuid, descriptors_reference)
char_reference_dict = generate_uuid_dict(bluetooth_standard__front_uuid, bluetooth_standard__end_uuid, characteristic_reference)
serv_reference_dict = generate_uuid_dict(bluetooth_standard__front_uuid, bluetooth_standard__end_uuid, service_reference)
#combined_dict = Merge(desc_reference_dict, char_reference_dict, serv_reference_dict)
total_uuid_dict = { "Services" : {},
                    "Characteristics" : {},
                    "Descriptors" : {},
                    "Unkonwns" : {} }
#total_uuid_dict.update(desc_reference_dict)
#total_uuid_dict.update(char_reference_dict)
#total_uuid_dict.update(serv_reference_dict)
merge_generated_uuid_dicts(total_uuid_dict, serv_reference_dict)
merge_generated_uuid_dicts(total_uuid_dict, char_reference_dict)
merge_generated_uuid_dicts(total_uuid_dict, desc_reference_dict)

## Scratch Space Code
# Just run to test scratch space
def scratch_space():
    ## Step 3:  Create a device object the user can connect/interact with that does:
    '''
    # Note: This is a grab of the Light Orb BLE Device in the testing space
    light_orb = system_dbus__bluez_device__low_energy('F0:98:7D:0A:05:07')
    
    
    ## Connect/Disconnect testing to the device                                                                  (Step 3i)
    # Connection Test
    #light_orb.device_interface.Connect()        # Note: The 30 second life IS REAL!! Make sure to connect within a short time after seeing the device; OTHERWISE need to set that variable that will give longer time before being 'purged'
    light_orb.Connect()
    if not light_orb.find_and_get__device_property('Connected'):
        print("[-] Unable to Connect to the Device\t{0}".format(light_orb.device_address))
    else:
        print("[+] Connected")
    # Disconnection Test
    #light_orb.device_interface.Disconnect()
    light_orb.Disconnect()
    if light_orb.find_and_get__device_property('Connected'):
        print("[-] Unable to Disconnect from the Device\t{0}".format(light_orb.device_address))
    else:
        print("[+] Disconnected")
    
    ## Enumerate the device's properties and services                                                            (Step 3ii)
    # Re-Connect
    light_orb.Connect()
    # Enumerate Properties
    device_properties_array = light_orb.find_and_get__all_device_properties()
    light_orb.identify_and_set__device_properties(device_properties_array)
    
    if light_orb.device_services_resolved:
        print("[+] Services were resolved")
        light_orb.enumerate_and_print__device__all_internals()
    else:
        print("[-] Services were NOT resolved")
    # WTF..... The long version above will run fine, but the above class function call only works after the long part?
    #   -> Issue appears to be that the descriptor_properties doesn't get made????
    #       - Maybe because not connected? Thus can not get information that was not obtained earlier?
    #       - It might just be the amount of time required....
    #   - TODO: Add in check for ServicesResolved BEFORE trying to print all internals
    #'''
    #light_orb.Disconnect()
    
    # Read/Write from/to properties from (3ii)                                                                  (Step 3iii)
    '''
    ble_ctf = system_dbus__bluez_device__low_energy('CC:50:E3:B6:BC:A6')
    ble_ctf.Connect()
    ble_ctf.identify_and_set__device_properties(ble_ctf.find_and_get__all_device_properties())
    ble_services_list = ble_ctf.find_and_get__device_introspection__services()
    # Note: Need to check first if the services have been resolved
    if not ble_ctf.device_services_resolved:
        print("[-] Services were NOT resolved")
        exit(22)        # Not sure that this works.... code run still got to lines below
    service_path, service_object, service_interface, service_properties, service_introspection = ble_ctf.create_and_return__service__gatt_inspection_set(ble_services_list[0])          # Note: This is only looking at a SINGLE characteristic
    service_characteristics_list = ble_ctf.find_and_get__device__etree_details(service_introspection, 'char')
    ble_chars_list = ble_ctf.find_and_get__device_introspection__characteristics(service_path, service_characteristics_list)
    # Attempt Read
    #characteristic_interface.ReadValue({})      # Note the use of {} to pass an empty dictionary
    '''
    
    ### Sketch Area for Full Characteristics Read
    
    ## Comparison of the pretty print of mapping for a targeted BLE device (e.g. BLE CTF)
    '''
    print("[*] Enumeration of a Chosen Target Device via Function")
    target_bt_addr = 'CC:50:E3:B6:BC:A6'
    ble_device, device__mapping = connect_and_enumerate__bluetooth__low_energy(target_bt_addr)
    pretty_print__gatt__dive_json(ble_device, device__mapping)
    
    # Re-create the ble_ctf device to test the handle information bit below
    print("-----------------------------------------------------------------------------------------\n- Handle-to-UUID Mapping Research \n-----------------------------------------------------------------------------------------")
    ble_ctf = system_dbus__bluez_device__low_energy('CC:50:E3:B6:BC:A6')
    ble_ctf.Connect()
    print("[*] Waiting for device [ {0} ] services to be resolved".format(ble_ctf.device_address), end='')
    # Hang and wait to make sure that the services are resolved
    while not ble_ctf.find_and_get__device_property("ServicesResolved"):
        time.sleep(0.5)      # Sleep to give time for Services to Resolve
        print(".", end='')
    print("\n[+] Device services resolved!")
    ble_ctf.identify_and_set__device_properties(ble_ctf.find_and_get__all_device_properties())
    '''
    '''
    Calling to the bluetoothctl function
        - subprocess.getoutput('bluetoothctl connect ' + BLE_ADDR)
        - subprocess.getoutput('bluetoothctl gatt.list-attributes')
        - subprocess.getoutput('bluetoothctl disconnect ' + BLE_ADDR)
    
    Fixing the Return from the subprocess call
        - test = subprocess.getoutput('bluetoothctl gatt.list-attributes')
        - formatted_test = test.replace('\\n', '\n').replace('\\t', '\t')
    '''
    ## Obtaining bluetoothctl output in order to have Handle information
    import subprocess
    '''
    # Connect to the device first
    subprocess.getoutput('bluetoothctl connect ' + ble_ctf.device_address)
    # Grab the list of GATT attributes
    raw__gatt_attributes_grab = subprocess.getoutput('bluetoothctl gatt.list-attributes')
    # Disconnect from the device
    subprocess.getoutput('bluetoothctl disconnect ' + ble_ctf.device_address)
    # Format the raw output captured into something we can then dissect
    formatted__gatt_attributes_grab = raw__gatt_attributes_grab.replace('\\n', '\n').replace('\\t', '\t')       # Note: This does not really do shit...
    # Using .split('\n') does give me an element per \n, but leaves any leading '\t' still as part of the string
    #   - Note: Since the data comes in EXPECTED sets of 4 we do a JSON using the UUID as a key and then have the information for each as sub-entries
    #   - Use .lstrip('\t')
    
    ## Pulling out the information required
    #   - Goals:
    #       1)      Extract out the various handles                                                 -   separated_test[::4]
    #       2)      Extract out the associated Service/Characteristic/Descriptor                    -   separated_test[1::4]
    #       3)      Extract out the associated UUID                                                 -   separated_test[2::4]
    #       4)      Extract out the "known" name for the UUID                                       -   separated_test[3::4]
    '''
    '''
    Example output from GATT attributes list:
    Characteristic (Handle 0x0000)
            /org/bluez/hci0/dev_CC_50_E3_B6_BC_A6/service0028/char002b
            0000ff02-0000-1000-8000-00805f9b34fb
            Unknown
    Characteristic (Handle 0x0000)
            /org/bluez/hci0/dev_CC_50_E3_B6_BC_A6/service0028/char0029
            0000ff01-0000-1000-8000-00805f9b34fb
            Unknown
    Primary Service (Handle 0x0000)
            /org/bluez/hci0/dev_CC_50_E3_B6_BC_A6/service0001
            00001801-0000-1000-8000-00805f9b34fb
            Generic Attribute Profile
    Characteristic (Handle 0x0000)
            /org/bluez/hci0/dev_CC_50_E3_B6_BC_A6/service0001/char0002
            00002a05-0000-1000-8000-00805f9b34fb
            Service Changed
    Descriptor (Handle 0x0000)
            /org/bluez/hci0/dev_CC_50_E3_B6_BC_A6/service0001/char0002/desc0004
            00002902-0000-1000-8000-00805f9b34fb
            Client Characteristic Configuration
    '''
    '''
    # Create the split array
    split__gatt_attributes = raw__gatt_attributes_grab.split('\n')
    # Setup sub-arrays of information
    uuids_array = split__gatt_attributes[2::4]
    paths_array = split__gatt_attributes[1::4]
    handles_array = split__gatt_attributes[::4]
    name_array = split__gatt_attributes[3::4]
    # Loop for creating the necessary JSON files
    bl_ctl__ble_json = {}
    #create_and_return__bluetoothctl__ble_gatt_json()
    number_of_entries = len(uuids_array)
    # Loop for populating the JSON structure
    for uuid_entry_number in range(0, number_of_entries):
        # Create the place holder UUID information
        uuid_entry_info = create_and_return__bluetoothctl__ble_gatt_json()
        # Create the varaibles
        handle_value = handles_array[uuid_entry_number].split('(')[1].split(')')[0].split(' ')[1]
        type_value = handles_array[uuid_entry_number].split('(')[0]
        name_value = name_array[uuid_entry_number].lstrip('\t')
        path_value = paths_array[uuid_entry_number].lstrip('\t')
        uuid_value = uuids_array[uuid_entry_number].lstrip('\t')
        # Populate the information
        uuid_entry_info["Handle"] = handle_value
        uuid_entry_info["Name"] = name_value
        uuid_entry_info["Path"] = path_value
        uuid_entry_info["Type"] = type_value
        bl_ctl__ble_json[uuid_value] = uuid_entry_info
    # Print out the created JSON array
    print(bl_ctl__ble_json)
    # Note: Can now use the bl_ctl__ble_json as a translation between the BLE CTF handles and known/found UUIDs
    '''

    #pretty_print__uuid_2_handle_map(bl_ctl__ble_json)
    
    ## Thinking about how to do the writes....
    # Using DBUS, writing requires: (1) knowing EXCATLY what characteristic to write to, (2) creating the necessary "interaction objects", (3) calling the .Write() method call, (3+) Create whatever settings are needed for doin the write properly
    
    # Set connection properties (i.e. Security)                                                                 (Step 3iv)
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    # Pair with a device                                                                                        (Step 3v)
    
    
    ## Testing of the user input aspect of the platform
    #find_and_enumerate__bluetooth_device__user_selected()

    ## Testing taking input of potential targets; TODO: Incorporate into the rest of the larger codebase
    import json

    # Variables for Usage
    input__processed_data = "/tmp/processed_data.txt"
    processed_data = None
    item_number__name = 1
    user_input_check = False
    output_log_string = ""

    # Read in the JSON Dictionary
    output_log_string = "[*] Beginning Target Selection Process for Device Enumeration"
    print_and_log(output_log_string)
    with open(input__processed_data) as pdata_repo:
        processed_data = json.load(pdata_repo)

    # Enumerate the unique name targets
    for unique_name in processed_data:
        #print("[*] {1}\)\tDevice Name:\t\t[ {0} ]".format(unique_name, item_number__name))
        output_log_string = "{1})\t\tDevice Name:\t\t[ {0} ]".format(unique_name, item_number__name)
        print_and_log(output_log_string)
        item_number__name += 1

    # Request a choice from the user
    user_selection = input("Select a device name from above to examine:\t")
    user_input_check = False
    while not user_input_check:
        user_input_check = check_and_validate__user_selection(user_selection, item_number__name)
    #print("[*] Examining Device Selection\t[ {0} ]".format(user_selection))
    name_list = list(processed_data)
    user_selected_name = name_list[int(user_selection)-1]
    output_log_string = "[*] Examining Device Selection\t[ {0} ] with Name\t[ {1} ]".format(user_selection, user_selected_name)
    print_and_log(output_log_string)

    # Iterate through all associated bluetooth addresses/targets
    for known_address in processed_data[user_selected_name]:
        output_log_string = "-----\n- Known Address:\t\t{0}\n-----".format(known_address)
        print_and_log(output_log_string)

        # Begin the Scanning and enumeration process
        scanning__ble(known_address)
