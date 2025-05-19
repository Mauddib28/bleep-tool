# bleep-tool
Bluetooth Landscape Exploration &amp; Enumeration Platform
==========================================================================================
		bluetooth interaction platform - usage documentation
==========================================================================================

Note: The usage documentation is easier to read as a basic text file

-------------------------------------
- Requirements/Package Installation - 
-------------------------------------
    - Python Libraries:     python3 -m pip install xmltodict

----------------------------------
- Main Script for Functionality: -
----------------------------------
	- Script:		dbus__bleep.py

--------------------
- TL;DC Tool Usage -
--------------------
    - Command Line:     python3 dbus__bleep.py -m user

---------------
- How to Run: -
---------------
	- Without any arguments/flags
        1)      Nothing will occur

	- Help information
		1)		Use the '-h' flag to have the script print out the help menu

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

    - With the usermode flag
		1)		Script will begin with "COMPLETE USER SELECTED DEVICE EXPLORATION"
			- This will search for Bluetooth devices for a set amount of time or until the user provides a 'Ctrl-C' input
		2)		The script will then output the list of discovered BLE devices
			- This includes a pairing of the Bluetooth ADDR and Device Name
		3)		Once the user selects a device target, then the usermode menu will be displayed
            - Note: Depending on the amount of time spent between start of the usermode (i.e. discovery of devices) and the selection of a target is too long, then the D-Bus will "forget" about the device and will require restarting bleep
        4)      When done with the usermode, type 'quit' to exit usermode

    - With the assets_of_internet flag
        1)      This mode REQUIRES that an input file be presented with potential targets
            - Note: The format for this data is a JSON {"<criteria>" : ["<target_001>", .... , "<target_n>"]}
        2)      The platform will then attempt to discover these targets and enumerate them
            - All information is copied into the appropriate logs
	    3)		The enumeration of the target device is broken down as follows:
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

---------------------------------
- Signal Capture with User Mode -
---------------------------------

There are specific steps that must be taken when capturing signals using User-Mode
The steps are:
1)      Prepare tools
2)      Set Characteristic
        - Nota Bene: This has to happen first or will generate an AttributeError
                - Ex:   'NoneType' object has no attribute 'StartNotify'
3)      Configure recieve
4)      Toggle Notify
5)      Start capture


--------------------
- Troubleshooting: -
--------------------
    - If encountering issues related to the adapter, attempt to run the 'setup.sh' script to correct them
        - Note: There is an assumption of the Bluetooth adapter being HCI0 (i.e. hardcorded within the script)

    - If encountering issues related to a "Missing Bluetooth Adapter" then follow the steps below:
        - Check that there exists an attached Bluetooth Device; Look for an "hci0" device in the response
            - Ex:       hciconfig -a
            - If there is no hci0 device, then connect the Bluetooth antenna (e.g. Sena UD-100)
        - If the error persists, then ensure that the Bluetooth Service is enabled and follow with a reboot
            - Ex:       systemctl enable bluetooth.service
                        reboot
        - Check that the BLEEP script can be run


==========================================================================================
		            bleep platform - research / source documentation
==========================================================================================

Slides presenting D-Bus and Python research + development at CackalackyCon 2024:        https://github.com/Mauddib28/bleep--2024--CackalackyCon-Slides
    - YouTube Recording of the Presentation:                                            https://www.youtube.com/watch?v=kFSlYIJMxOI
Slides presenting Safari Hunt of Bluetooth Wildlife + Cartography at BSidesLV 2024:     https://github.com/Mauddib28/bleep--2024--BsidesLV-Slides
    - YouTube Recording of the Presentation:                                            https://youtu.be/AZ0U3bhRYkA
Slides presenting technical function and review of BLEEP + mapping at DefCon 32:        https://github.com/Mauddib28/bleep--2024--DefCon-DemoLabs-Slides
Slides presenting Bluetooth Wildlife dissection at CackalackyCon 2025:                  https://github.com/Mauddib28/bleep--2025--CackalackyCon-Slides
