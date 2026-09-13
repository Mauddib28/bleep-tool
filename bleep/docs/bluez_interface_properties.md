# BlueZ D-Bus Interface Property Reference

This document catalogues all BlueZ D-Bus interface properties captured and
displayed by BLEEP, with notes on their operational significance and security
implications.  It serves as an internal quick-reference for developers and
auditors working with BLEEP's enumeration output.

Source specifications: `doc/device-api.txt`, `doc/gatt-api.txt`,
`doc/adapter-api.txt`, `doc/battery-api.txt`, `doc/input-api.txt`,
`doc/device-set-api.txt` in the BlueZ source tree (v5.66+).

---

## org.bluez.Device1

Properties collected by `_collect_device_props()` (`bleep/ble_ops/le/scan.py`)
and `get_discovered_devices()` (`bleep/dbuslayer/adapter.py`).  Displayed by
`format_device_info_block()` in `bleep/ble_ops/common/conversion.py`.

| Property | D-Bus Type | Description | Security / Significance Notes |
|----------|-----------|-------------|-------------------------------|
| Address | string | Bluetooth device address (MAC). | Identifies the remote device.  May be randomised on BLE privacy-enabled devices. |
| AddressType | string | `"public"` or `"random"`. | `random` addresses rotate over time; correlating observations requires IRK resolution.  A `public` address is stable and can be fingerprinted. |
| Name | string | Remote name as reported by EIR/scan response. | User-controllable; never trust for authentication. |
| Alias | string | Friendly name (may be user-set locally). | Overrides Name in UIs.  Not from the remote device. |
| Paired | bool | Whether the device is paired. | Indicates key material exists.  Paired-but-not-trusted devices still reject service access. |
| Bonded | bool | Whether a bond (long-term key exchange) exists. | A bonded device has stored LTK/IRK/CSRK.  Removing a bond requires explicit `RemoveDevice()`. |
| Trusted | bool | Whether the device is authorised for automatic service connections. | **Security-sensitive**: a trusted device can auto-connect profiles without user confirmation.  Setting trust on an unknown device is a security risk. |
| Blocked | bool | Whether the device is blocked. | Blocked devices are rejected at the kernel level.  Useful for blacklisting rogue peripherals. |
| WakeAllowed | bool | Whether the device can wake the host from suspend. | Relevant for HID devices.  Enabling wake on untrusted devices is a DoS vector. |
| Connected | bool | Active ACL/LE connection exists. | Transient state; reflects the current moment only. |
| LegacyPairing | bool | Whether pairing uses legacy PIN exchange. | **Security-sensitive**: legacy pairing is vulnerable to passive eavesdropping.  SSP/SC should be preferred. |
| RSSI | int16 | Received signal strength in dBm. | Volatile; only valid during discovery.  Useful for proximity estimation but easily spoofable. |
| TxPower | int16 | Advertised transmit power in dBm. | Set by the remote device and not independently verifiable. |
| Class | uint32 | 24-bit Class of Device (BR/EDR). | Encodes major/minor device class and service class bits.  Decoded by `format_device_class()`. |
| Appearance | uint16 | GAP Appearance value (BLE). | Numeric category hint (e.g. 961 = keyboard).  Decoded by `decode_appearance()`. |
| Icon | string | Suggested icon name (e.g. `"input-keyboard"`). | Derived from Class or Appearance by BlueZ.  Informational only. |
| Modalias | string | PnP ID string (`usb:vXXXXpYYYY` or `bluetooth:vXXXXpYYYY`). | Encodes vendor/product/version.  Used for driver matching and device fingerprinting. |
| ManufacturerData | dict{uint16, bytes} | BLE advertising manufacturer-specific data. | Key is the Bluetooth SIG company ID.  Value is opaque payload.  Displayed as hex+decimal key and hex/ASCII value. |
| ServiceData | dict{string, bytes} | BLE advertising service-specific data keyed by UUID. | UUIDs are resolved to known names.  Payload displayed as hex/ASCII. |
| UUIDs | array[string] | Advertised service UUIDs. | Resolved to human-readable names where possible. |
| AdvertisingFlags | bytes | Raw AD flags from the advertising PDU. | Bit field indicating discovery mode, BR/EDR support, etc.  Displayed as hex/ASCII. |
| AdvertisingData | dict{byte, bytes} | Raw AD type→data map from advertising PDU. | Lower-level than ManufacturerData/ServiceData; provides access to all AD structures including those BlueZ doesn't parse into named properties. |
| ServicesResolved | bool | Whether GATT service discovery has completed. | Must be `True` before characteristic enumeration can proceed. |
| Sets | array{object, dict} | Object paths of the coordinated sets this device belongs to, each followed by a dict containing `Rank` (byte). | **Experimental.** Indicates membership in a CSIP Coordinated Set (e.g. TWS earbuds sharing a SIRK).  `Rank` identifies the device's position within the set (e.g. left=1, right=2).  See [DeviceSet1](#orgbluezdeviceset1) below. |
| PreferredBearer | string | Preferred transport for initial connection on dual-mode devices: `"last-used"`, `"bredr"`, `"le"`, or `"last-seen"`. | **Experimental, read-write.**  Changing from `"bredr"` to `"le"` removes the device from the auto-connect list.  Only takes effect when the device is disconnected. |

---

## org.bluez.GattService1

Properties captured during `services_resolved()` and deep enumeration in
`bleep/dbuslayer/device_le.py`.  Displayed in `format_gatt_tree()`.

| Property | D-Bus Type | Description | Significance Notes |
|----------|-----------|-------------|---------------------|
| UUID | string | 128-bit service UUID. | Resolved to a human-readable name via `get_name_from_uuid()`. |
| Primary | bool | `True` for primary services, `False` for secondary (included-only) services. | Secondary services are only reachable through the `Includes` property of a primary service. |
| Handle | uint16 | ATT handle of the service declaration attribute. | Useful for protocol-level debugging and handle-based operations. |
| Includes | array[object_path] | D-Bus paths of included (secondary) services. | Indicates service composition.  Included services share characteristics with the referencing primary service. |

---

## org.bluez.GattCharacteristic1

Properties captured by `Characteristic.__init__()` (`bleep/dbuslayer/characteristic.py`)
and stored in the GATT mapping.  Displayed in `format_gatt_tree()`.

| Property | D-Bus Type | Description | Significance Notes |
|----------|-----------|-------------|---------------------|
| UUID | string | 128-bit characteristic UUID. | Resolved to human-readable name. |
| Flags | array[string] | Permitted operations: `read`, `write`, `write-without-response`, `notify`, `indicate`, `authenticated-signed-writes`, `reliable-write`, `writable-auxiliaries`, `encrypt-read`, `encrypt-write`, `encrypt-authenticated-read`, `encrypt-authenticated-write`, `authorize`. | **Security-critical**: flags like `encrypt-read` and `encrypt-authenticated-write` indicate the characteristic requires encryption or authentication.  BLEEP displays these to help assess the device's security posture. |
| Handle | uint16 | ATT handle of the characteristic declaration. | Useful for protocol-level operations and cross-referencing with HCI traces. |
| MTU | uint16 | Negotiated ATT MTU for this characteristic (available post-connection). | Determines maximum payload size for read/write operations.  A low MTU may truncate large values. |
| Notifying | bool | Whether notifications/indications are currently active. | `True` when `StartNotify()` has been called.  Useful for understanding active data streams. |
| Value | bytes | Last-read or notified value. | Displayed as separate Hex and ASCII lines.  Non-printable bytes rendered as U+FFFD. |

---

## org.bluez.GattDescriptor1

Properties captured by `Descriptor.__init__()` (`bleep/dbuslayer/descriptor.py`).
Displayed in `format_gatt_tree()`.

| Property | D-Bus Type | Description | Significance Notes |
|----------|-----------|-------------|---------------------|
| UUID | string | 128-bit descriptor UUID. | Common descriptors: `0x2902` (CCCD — controls notify/indicate), `0x2901` (User Description), `0x2900` (Extended Properties). |
| Handle | uint16 | ATT handle of the descriptor. | Used for handle-based read/write. |
| Flags | array[string] | Permitted descriptor operations: `read`, `write`, `encrypt-read`, `encrypt-write`, `encrypt-authenticated-read`, `encrypt-authenticated-write`, `authorize`. | Writing the CCCD (`0x2902`) with incorrect values can enable unwanted notifications or indications. |
| Value | bytes | Last-read descriptor value. | Displayed as hex/ASCII.  CCCD values of `01 00` = notify enabled, `02 00` = indicate enabled. |

---

## org.bluez.Battery1

Properties collected by `_collect_device_props()` (`bleep/ble_ops/le/scan.py`)
from the device's object path when the interface is present.  Displayed in
`format_device_info_block()`.

| Property | D-Bus Type | Description | Significance Notes |
|----------|-----------|-------------|---------------------|
| Percentage | byte | Battery level as a percentage (0–100). | Standard BAS (Battery Service) value.  Useful for assessing device operational readiness. |
| Source | string | Source of the battery information (e.g. `"native"`, `"HFP"`, `"AVRCP"`). | Indicates which profile provided the battery level.  `native` = GATT Battery Service; `HFP`/`AVRCP` = Bluetooth Classic profile-specific reporting. |

---

## org.bluez.Input1

Properties collected by `_collect_device_props()` from the device path when
the interface is present (typically HID devices).  Displayed in
`format_device_info_block()`.

| Property | D-Bus Type | Description | Significance Notes |
|----------|-----------|-------------|---------------------|
| ReconnectMode | string | HID reconnect policy. | **Security-relevant values:** |
| | | | - `"none"` — device does not automatically reconnect.  Safest; requires explicit user action. |
| | | | - `"host"` — only the host can initiate reconnection.  Moderately secure; device cannot force a connection. |
| | | | - `"device"` — only the device can initiate reconnection.  Peripheral can reconnect at will which may be a concern for untrusted devices. |
| | | | - `"any"` — **both host and device can initiate reconnection.**  Most permissive; an untrusted device in `"any"` mode can reconnect and potentially inject input without explicit user approval. |

---

## org.bluez.Adapter1

Properties returned by `get_adapter_info()` (`bleep/dbuslayer/adapter.py`).
Displayed by `adapter-config show` (`bleep/modes/adapter_config.py`).

| Property | D-Bus Type | Writable | Description | Significance Notes |
|----------|-----------|----------|-------------|--------------------|
| Address | string | No | Hardware MAC address. | Fixed identifier of the local controller. |
| AddressType | string | No | `"public"` or `"random"`. | Random is used when LE privacy is enabled. |
| Name | string | No | System hostname. | Read from kernel; not directly settable via D-Bus. |
| Alias | string | Yes | Friendly name broadcast to remote devices. | Setting a descriptive alias can aid device identification during scanning. |
| Class | uint32 | No (D-Bus) | 24-bit Class of Device. | Writable via management socket only.  Affects how remote devices categorise this host. |
| Powered | bool | Yes | Whether the adapter is powered on. | Toggling power resets all connections.  Some adapters may not support soft power-off. |
| PowerState | string | No | Fine-grained power state: `on`, `off`, `on-disabling`, `off-enabling`. | Transitional states (`on-disabling`, `off-enabling`) indicate the controller is in the process of changing power state.  BlueZ ≥ 5.64. |
| Discoverable | bool | Yes | Whether the adapter is visible to scanning devices. | **Security-sensitive**: leaving discoverable enabled indefinitely exposes the host to discovery by any nearby device.  Use `DiscoverableTimeout` for auto-disable. |
| DiscoverableTimeout | uint32 | Yes | Seconds before discoverable auto-disables. | `0` = remain discoverable forever (not recommended in production). |
| Pairable | bool | Yes | Whether the adapter accepts pairing requests. | **Security-sensitive**: enabling pairable without a registered agent may allow unauthenticated pairing. |
| PairableTimeout | uint32 | Yes | Seconds before pairable auto-disables. | `0` = remain pairable forever. |
| Connectable | bool | Yes | Whether incoming connections are accepted. | Setting to `False` also clears Discoverable. |
| Discovering | bool | No | Whether a discovery session is active. | Reflects `StartDiscovery()`/`StopDiscovery()` state. |
| Manufacturer | uint16 | No | Bluetooth SIG company identifier of the adapter chipset. | Useful for identifying the hardware vendor (e.g. Intel, Broadcom, Realtek). |
| Version | uint8 | No | LMP version of the controller. | Indicates Bluetooth specification version support (e.g. 9 = Bluetooth 5.0). |
| ExperimentalFeatures | array[string] | No | UUIDs of enabled BlueZ experimental features. | Features like LL Privacy, Quality Report, and Codec Offload are gated behind experimental flags.  Knowing which are active helps assess available functionality. |
| UUIDs | array[string] | No | Locally registered service UUIDs. | Lists profiles the adapter supports. |
| Modalias | string | No | USB/Bluetooth vendor info string. | Encodes vendor, product, and version for driver matching. |
| Roles | array[string] | No | Supported GAP roles: `"central"`, `"peripheral"`. | Determines whether the adapter can act as a BLE central, peripheral, or both. |

---

## org.bluez.DeviceSet1

The DeviceSet interface implements the **CSIP (Coordinated Set Identification
Profile)** concept in BlueZ.  It groups multiple Bluetooth devices that
logically belong together — such as a pair of TWS earbuds (left and right), a
set of hearing aids, or a multi-speaker arrangement — into a single
manageable unit.

Each set is identified by its **SIRK (Set Identity Resolving Key)**, a
cryptographic key shared among all members during pairing.  BlueZ uses the
SIRK to resolve set membership and automatically group devices that share the
same key.  The SIRK is visible in the D-Bus object path
(`/org/bluez/hci0/set_{sirk}`).

**The entire DeviceSet1 API is experimental** and requires BlueZ to be
started with `--experimental` (or `bluetoothd -E`).

D-Bus wrapper: `bleep/dbuslayer/device_set.py` (`DeviceSet`,
`enumerate_device_sets()`).  CLI mode: `bleep/modes/device_sets.py`
(`bleep device-sets {list,connect,disconnect,info}`).

Source specification: `workDir/BlueZDocs/org.bluez.DeviceSet.rst` (BlueZ,
September 2023).

:Service: `org.bluez`
:Interface: `org.bluez.DeviceSet1`
:Object path: `[variable prefix]/{hci0,hci1,...}/set_{sirk}`

### Methods

| Method | Description | Notes |
|--------|-------------|-------|
| `Connect()` | Connects all member devices in sequence, following the same procedure as `Device1.Connect()`. | Errors: `NotReady`, `Failed`, `InProgress`, `AlreadyConnected`. |
| `Disconnect()` | Disconnects all member devices in sequence, following the same procedure as `Device1.Disconnect()`. | Errors: `NotConnected`. |

### Properties

| Property | D-Bus Type | Writable | Description | Significance Notes |
|----------|-----------|----------|-------------|--------------------|
| Adapter | object | No | Object path of the adapter this set belongs to. | Links the set to its parent controller. |
| AutoConnect | bool | Yes | Whether all members are automatically connected when *any* member connects. | **Key operational property.**  When `True`, connecting one earbud automatically brings up the other.  Toggled via `set_auto_connect()` in `device_set.py`. |
| Devices | array{object} | No | Object paths of the member `Device1` objects. | The actual set membership list.  Compare `len(Devices)` against `Size` to determine if all members have been discovered. |
| Size | byte | No | Expected number of members in the set. | Advertised by the set coordinator.  If `len(Devices) < Size`, some members have not yet been paired or discovered. |

### Relationship to Device1

Individual devices expose their set membership via the `Device1.Sets`
property (see [org.bluez.Device1](#orgbluezdevice1) above).  Each entry
in `Sets` contains the set's object path and a dict with a `Rank` byte
indicating the device's position in the set.

### Typical Use Case: TWS Earbuds

1. Both earbuds share the same SIRK during initial pairing.
2. BlueZ creates a single `set_{sirk}` object under the adapter.
3. Both `Device1` objects (left/right) appear in the set's `Devices` array.
4. Calling `Connect()` on the `DeviceSet1` connects both earbuds in sequence.
5. With `AutoConnect = True`, connecting one earbud triggers automatic
   connection of the other.

---

## Intentionally Unsupported: Deprecated BlueZ Profile Plugin APIs

The following BlueZ D-Bus interfaces were **removed in BlueZ 5.48+** and are intentionally not implemented as D-Bus wrappers in BLEEP:

| Interface | Profile | BlueZ Removal | BLEEP Approach |
|-----------|---------|---------------|----------------|
| `ThermometerManager1` / `Thermometer1` | Health Thermometer | 5.48 | GATT-level decode via `gatt_profile_decode.py` |
| `HeartRateManager1` / `HeartRate1` | Heart Rate | 5.48 | GATT-level decode via `gatt_profile_decode.py` |
| `CyclingSpeedManager1` / `CyclingSpeed1` | Cycling Speed and Cadence | 5.48 | GATT-level decode via `gatt_profile_decode.py` |
| `ProximityMonitor1` / `ProximityReporter1` | Proximity (Alert/Link Loss/Tx Power) | 5.48 | GATT-level decode via `gatt_profile_decode.py` |

These profiles are based on standard GATT services that BLEEP already reads during normal enumeration.  Rather than re-implementing the removed BlueZ plugin APIs, BLEEP provides profile-aware value decoding at the GATT level (see [GATT Enumeration — Recognized GATT Profiles](gatt_enumeration.md#recognized-gatt-profiles-deprecated-bluez-plugin-apis)), which works on **all** BlueZ versions regardless of whether the legacy plugins were ever present.

---

*Last updated: 2026-05-22 — added org.bluez.DeviceSet1 section and Device1.Sets/PreferredBearer properties*
