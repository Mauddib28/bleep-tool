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

- [ ] **Documentation** – finish User mode guide once implementation stabilises (README.refactor)
- [ ] Asset-of-Interest enumeration processing (README.refactor)
- [ ] Multi-read / brute-write characteristic helpers (README.refactor)
- [ ] Implement passive / naggy / pokey / brute scan variants (README.refactor)
- [ ] Pairing agent polish (README.refactor)
- [ ] Local database for unknown UUIDs + device observations (README.refactor)
- [ ] Classic Bluetooth enumeration (README.refactor)
- [ ] Fix mixed tabs/spaces lint errors in `BLEEP.golden-template` (golden-template)

*(collapse / expand sections as items are completed)* 

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
   [ ] Create a decode for appearance values
       - Pull from bluetooth support files to better identify (e.g. similar to Class data)
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

