# LE Advertising

**Status:** Implemented (Sprint 2, BZ-6/7)

## Overview

The LE Advertising subsystem enables BLEEP to **broadcast** custom BLE
advertisement packets from the local adapter.  This is the transmit
counterpart to scanning — instead of receiving advertisements, BLEEP crafts
and sends them.

Use cases include:
- Impersonating a known device type during security assessments
- Broadcasting custom service UUIDs, manufacturer data, or local names
- Testing advertisement monitor setups (Sprint 4) end-to-end
- Emitting beacons (iBeacon-style via manufacturer data, Eddystone via
  service data)

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  bleep advertise start --name "TestDevice" --uuid 180D          │
│                        modes/advertise.py                        │
└──────────────────┬───────────────────────────────────────────────┘
                   │
          ┌────────▼──────────────┐
          │   LEAdvertisement     │  /org/bluez/bleep/advertisement0
          │   (dbus.service)      │
          └────────┬──────────────┘
                   │ registered with
          ┌────────▼──────────────────────┐
          │  LEAdvertisingManager1        │  /org/bluez/hci0
          │  (bluetoothd, system bus)     │
          └───────────────────────────────┘
```

## D-Bus Conversation Flow

1. **BLEEP exports an `LEAdvertisement1` object** on the system bus at a
   freely-chosen path (e.g. `/org/bluez/bleep/advertisement0`).  The object
   exposes properties via `GetAll`: `Type`, `ServiceUUIDs`,
   `ManufacturerData`, `LocalName`, `Appearance`, RSSI-related fields, etc.

2. **BLEEP calls `RegisterAdvertisement(object_path, options)`** on the
   adapter's `LEAdvertisingManager1` interface.

3. **bluetoothd calls `GetAll("org.bluez.LEAdvertisement1")`** on our object
   to read the advertisement data.  It constructs the correct AD structure
   and configures the kernel to send the advertisement.

4. **The adapter broadcasts** the constructed advertisement packet on the LE
   advertising channels.  Other devices in range will see it in their scans.

5. **bluetoothd calls `Release()`** on our object when the advertisement is
   removed (adapter powered down, instance limit reached, timeout expired).

6. **Cleanup:** BLEEP calls `UnregisterAdvertisement(object_path)` and
   removes the D-Bus object.

## CLI Usage

### Check capabilities

```bash
bleep advertise caps
bleep advertise caps --adapter hci1
```

Output:
```
Adapter: /org/bluez/hci0
  ActiveInstances ........... 0
  SupportedInstances ........ 5
  SupportedIncludes ......... tx-power, appearance, local-name
  SupportedSecondaryChannels  1M, 2M, Coded
  SupportedFeatures ......... CanSetTxPower, HardwareOffload
  SupportedCapabilities:
    MaxAdvLen: 31
    MaxScnRspLen: 31
    MaxTxPower: 7
    MinTxPower: -22
```

### Start advertising

Advertise as a peripheral with a custom name and Heart Rate service UUID:

```bash
bleep advertise start --name "BLEEP-Test" --uuid 180D
```

Advertise manufacturer data (e.g. Apple company ID `0x004C`):

```bash
bleep advertise start --manufacturer-data 0x004C:0215aabbccdd
```

Advertise multiple service UUIDs with TX power included:

```bash
bleep advertise start -u 180D -u 180F --include-tx-power
```

Broadcast mode (non-connectable) with custom interval:

```bash
bleep advertise start --type broadcast --name "Beacon" \
  --min-interval 100 --max-interval 200
```

Auto-stop after 30 seconds (local timer):

```bash
bleep advertise start --name "Temp" -u 180D --local-duration 30
```

BlueZ-level timeout (bluetoothd auto-removes the advertisement):

```bash
bleep advertise start --name "Temp" --duration 60
```

### Flags reference

| Flag | Description |
|------|-------------|
| `--type` | `peripheral` (connectable) or `broadcast` (non-connectable) |
| `-u, --uuid` | Service UUID to include (repeatable) |
| `-m, --manufacturer-data` | `COMPANY_ID:HEX_DATA` (repeatable) |
| `-s, --service-data` | `UUID:HEX_DATA` (repeatable) |
| `-n, --name` | Local name string |
| `--appearance` | GAP Appearance value (uint16) |
| `--discoverable` | Advertise as general discoverable |
| `--tx-power` | Requested TX power in dBm (-127..20) |
| `--min-interval` / `--max-interval` | Advertising interval in ms (20–10485000) |
| `--secondary-channel` | PHY: `1M`, `2M`, or `Coded` |
| `--include-tx-power` | Include tx-power in AD data |
| `--include-appearance` | Include appearance in AD data |
| `--include-name` | Include local-name in AD data |
| `--duration` | BlueZ-level timeout (seconds, auto-removes) |
| `--local-duration` | Local stop timer (seconds, Ctrl-C otherwise) |

## Python API

```python
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from bleep.dbuslayer.le_advertising import (
    AdvertisementConfig, LEAdvertisement, LEAdvertisingManager,
)

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()

mgr = LEAdvertisingManager(bus, "/org/bluez/hci0")
print(f"Available slots: {mgr.get_supported_instances()}")

config = AdvertisementConfig(
    ad_type="peripheral",
    local_name="BLEEP-Test",
    service_uuids=["180D", "180F"],
    manufacturer_data={0xFFFF: b"\x00\x01\x02"},
)
adv = LEAdvertisement(bus, config)
mgr.register(adv)

loop = GLib.MainLoop()
try:
    loop.run()
finally:
    mgr.unregister(adv)
    adv.remove_advertisement()
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `org.bluez.Error.NotPermitted` on register | All advertising instances are in use; check `bleep advertise caps` |
| `org.bluez.Error.InvalidLength` on register | AD packet exceeds 31 bytes; reduce service UUIDs, name length, or data |
| Advertisement not visible to scanners | Ensure adapter is powered; check `--type` (broadcast is non-connectable) |
| `CanSetTxPower` not in features | Adapter firmware doesn't support per-instance TX power control; `--tx-power` is ignored |
