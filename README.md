# bleep-tool
Bluetooth Landscape Exploration &amp; Enumeration Platform
==========================================================================================
		Bluetooth Interaction Platform - Usage Documentation
==========================================================================================

----------------------------------
- Main Script for Functionality: -
----------------------------------
	- Script:		pybluez_dbus__now_with_classes.py

---------------
- How to Run: -
---------------
	- Without any arguments/flags
		1)		Script will begin with "COMPLETE DEVICE ENUMERATION TEST"
			- This will search for Bluetooth devices until the user provides a 'Ctrl-C' input
		2)		The script will then output the list of discovered BLE devices
			- This includes a specific search for the BLE CTF device
		3)		Once the "COMPLETE DEVICE ENUMERATION TEST" is completed, the script begins in another "Starting Discovery Process"
			- The purpose here is that the "memory" of the device being seen is being "kept fresh"
				-> This allows the later connection and enumeration of the target device to occur with minimal issue; e.g. connecting to the specific device
		4)		Once another 'Ctrl-C' input is provided by the user, the script move to resolve the desired device for enumeration (e.g. BLE CTF)
			- The purpose for this is that if the ServicesResolved does not complete, then the local DBUS memory will have a "map" of all services on the targeted device
		5)		The enumeration of the target device is broken down as follows:
			i)		High-level general services information for the targeted device
			ii)		JSON Pretty Print output from the Device Enumeration
				a)		Service information; including Handle and UUID data
				b)		Characteristic information; including UUID, Handle, Flags, and Value data
					- Note: The 'Flag' and 'Value' are displayed in a Human-Readable Format
				c)		Descriptor information; including UUID, Flags, and Value
			iii)		Array of the UUIDs and their respective sub-information
				- Note: For the purpose of double-checking the 'Handle' values that are being captured correctly
					-> Except ALL Handles are printing out the same value
			iv)		Print out of each UUID and its respective information; including Handle, Name, Path, and Type data
				- Note: The purpose of this print out is to associate the UUID to a Handle value
					-> Except ALL Handles are printing out the same value
		-> Has basic functionality to enumerate a device given the device's Bluetooth ADDR
	- With arguments/flags
		1)		Use the '-m' flag to provide a "runMode" for the Interaction Platform
			i)		'user' will call the User Interaction Exploration Template
			ii)		'debug' will start the Debug Command Interface
			iii)		'blectf' will begin an automated completion of the original BLE CTF
			iv)		'test' will run the testing script(s) to debug functionality
			v)		'picow' will run the test script(s) for interacting with a Pico-W BLE server
			vi)		'ble_passive' will perform a passive enumeration scan
			vii)		'ble_naggy' will perform a naggy (excessive reads, no write) enumeration scan
			viii)		'ble_pokey' will perform a pokey (small writes at connect) enumeration scan
			ix)		'ble_bruteforce' will perform a brute-force (all the writes) enumeration scan
			x)		'scratch' will run the existing scratch space code
			xi)		'assets_of_interest' will perform a automated multi-target enumeration scan; Note: no user input
	- Help information
		1)		Use the '-h' flag to have the script print out the help menu

