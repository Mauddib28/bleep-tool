# Advertisement Monitor

**Status:** Implemented (Sprint 4, BZ-11/12)
**BlueZ requirement:** experimental interfaces — bluetoothd must be started with `-E` or `--experimental`.

## Overview

The Advertisement Monitor subsystem enables **kernel-offloaded** passive BLE
scanning with pattern matching and RSSI thresholds.  Unlike `StartDiscovery`,
which is poll-based and battery-heavy, advertisement monitors are registered
once and fire `DeviceFound`/`DeviceLost` callbacks only when criteria are met.
When hardware supports it (Intel, Qualcomm), pattern matching runs entirely in
the controller firmware.

## The Problem `StartDiscovery` Has

Normally, to discover BLE devices you call `Adapter1.StartDiscovery()` on
D-Bus.  That puts the adapter into active scanning mode — the kernel receives
**every** advertisement PDU, bluetoothd parses them all, creates/updates
`Device1` objects, and fires `PropertiesChanged` signals for every device in
range.  This is:

1. **CPU/battery expensive** — processing every advertisement from every nearby device.
2. **Requires an active session** — discovery stops when the caller disconnects.
3. **No kernel/firmware filtering** — all filtering happens in userspace after the PDU is already delivered.

## What Advertisement Monitor Does Instead

`AdvertisementMonitorManager1` lets you tell the Bluetooth controller:
*"I only care about advertisements matching these specific byte patterns at
this RSSI level.  Wake me up only when you see one."*

On hardware that supports it, the pattern matching runs **in the controller
firmware itself** — the host CPU never even sees non-matching advertisements.
On other hardware, BlueZ does the filtering in the kernel, which is still
cheaper than full userspace discovery.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  bleep monitor start --pattern 0:0x09:4845 --rssi-high -60  │
│                       modes/monitor.py                       │
└──────────────────┬───────────────────────────────────────────┘
                   │
          ┌────────▼─────────┐
          │  AdvMonitorApp   │  /org/bluez/bleep/adv_monitor_app0
          │  (ObjectManager) │
          └────────┬─────────┘
                   │ contains
          ┌────────▼─────────┐
          │   AdvMonitor     │  /org/bluez/bleep/adv_monitor_app0/monitor0
          │  (dbus.service)  │
          └────────┬─────────┘
                   │ registered with
          ┌────────▼──────────────────┐
          │  AdvMonitorManager1       │  /org/bluez/hci0
          │  (bluetoothd, system bus) │
          └───────────────────────────┘
```

## D-Bus Conversation Flow

The following describes the actual D-Bus method calls exchanged between BLEEP
and bluetoothd during a monitor session.

### Step 1 — BLEEP registers objects on the system bus

BLEEP exports a tree of `dbus.service.Object` instances that bluetoothd will
call **back into** (the direction is reversed from the usual client→daemon
pattern):

```
/org/bluez/bleep/adv_monitor_app0            ← AdvMonitorApp (ObjectManager root)
/org/bluez/bleep/adv_monitor_app0/monitor0   ← AdvMonitor (the actual filter)
```

`AdvMonitorApp` implements `org.freedesktop.DBus.ObjectManager.GetManagedObjects()`.
When bluetoothd calls this, it discovers all child monitors and reads their
configuration.

### Step 2 — BLEEP tells bluetoothd to pick up the objects

```
org.bluez.AdvertisementMonitorManager1.RegisterMonitor(
    object_path: "/org/bluez/bleep/adv_monitor_app0"
)
```

This is called on the adapter object (e.g. `/org/bluez/hci0`).  bluetoothd then:

1. Calls `GetManagedObjects()` on the app root to discover child monitors.
2. Calls `GetAll("org.bluez.AdvertisementMonitor1")` on each child to read
   the filter config.
3. Programs the controller firmware (if supported) or sets up kernel-level
   filters.

### Step 3 — bluetoothd reads the monitor's properties

Each `AdvMonitor` exposes these properties via `GetAll`:

| Property | D-Bus Signature | Meaning |
|----------|-----------------|---------|
| `Type` | `s` | Always `"or_patterns"` — match if ANY pattern hits |
| `RSSIHighThreshold` | `n` (int16) | Device must exceed this dBm to trigger `DeviceFound` |
| `RSSIHighTimeout` | `q` (uint16) | ...for this many seconds continuously |
| `RSSILowThreshold` | `n` (int16) | Device drops below this to trigger `DeviceLost` |
| `RSSILowTimeout` | `q` (uint16) | ...for this many seconds continuously |
| `RSSISamplingPeriod` | `q` (uint16) | Optional; 0 = report all samples |
| `Patterns` | `a(yyay)` | Array of `(start_pos, ad_type, content_bytes)` |

The `Patterns` array is the core filter.  Each tuple says: *"In the
advertisement's AD structure of type `ad_type`, starting at byte offset
`start_pos`, look for the byte sequence `content_bytes`."*

Example: `(0, 0x09, [0x48, 0x45])` means "match any device whose Complete
Local Name starts with `HE`" (0x48=H, 0x45=E).

### Step 4 — bluetoothd calls back into BLEEP's objects

Once registered, bluetoothd invokes D-Bus methods **on our objects**:

| Method | When | Argument |
|--------|------|----------|
| `Activate()` | bluetoothd successfully installed the filter | — |
| `DeviceFound(o)` | An advertisement matched pattern + RSSI criteria | Device object path (e.g. `/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF`) |
| `DeviceLost(o)` | Device RSSI dropped below threshold for the timeout duration | Same path format |
| `Release()` | bluetoothd is shutting down or the monitor was rejected | — |

No `StartDiscovery` is needed.  The controller does the heavy lifting.

### Step 5 — Cleanup

```
org.bluez.AdvertisementMonitorManager1.UnregisterMonitor(
    object_path: "/org/bluez/bleep/adv_monitor_app0"
)
```

This tells bluetoothd to stop monitoring and remove the firmware/kernel filters.

### Concrete Example

Detect when an Apple device comes within ~2 meters (roughly -60 dBm):

```bash
bleep monitor start --pattern 0:0xFF:4c00 --rssi-high -60 --rssi-high-timeout 2
```

The D-Bus sequence is:

1. BLEEP creates `AdvMonitor` with `Patterns=[(0, 0xFF, [0x4c, 0x00])]` and
   `RSSIHighThreshold=-60`, `RSSIHighTimeout=2`.
2. BLEEP calls `RegisterMonitor("/org/bluez/bleep/adv_monitor_app0")` on `hci0`.
3. bluetoothd calls `GetManagedObjects()` → finds `monitor0`.
4. bluetoothd calls `GetAll("org.bluez.AdvertisementMonitor1")` on `monitor0`
   → reads the pattern and RSSI config.
5. bluetoothd programs the controller: "match manufacturer data starting with
   `4C 00` (Apple's BLE company ID)".
6. bluetoothd calls `Activate()` on `monitor0`.
7. When an Apple device's advertisement exceeds -60 dBm for 2+ seconds:
   bluetoothd calls `DeviceFound("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF")`.
8. When it drops below the low threshold: `DeviceLost(...)` fires.

## CLI Usage

### Check capabilities

```bash
bleep monitor caps
bleep monitor caps --adapter hci1
```

Output:
```
Adapter: /org/bluez/hci0
  SupportedMonitorTypes .. or_patterns
  SupportedFeatures ..... controller-patterns
```

### Start a monitor

Match advertisements containing "HE" in the Complete Local Name field:

```bash
bleep monitor start --pattern 0:0x09:4845
```

Match manufacturer data from a specific company (e.g. Apple = `0x004C`):

```bash
bleep monitor start --pattern 0:0xFF:4c00
```

Add RSSI filtering — only report devices stronger than -70 dBm for at least 3
seconds, and declare them lost when below -80 dBm for 5 seconds:

```bash
bleep monitor start \
  --pattern 0:0x09:4845 \
  --rssi-high -70 --rssi-high-timeout 3 \
  --rssi-low -80 --rssi-low-timeout 5
```

Auto-stop after 60 seconds:

```bash
bleep monitor start --pattern 0:0xFF:4c00 --duration 60
```

Multiple patterns (OR logic — any match triggers the monitor):

```bash
bleep monitor start \
  --pattern 0:0x09:4845 \
  --pattern 0:0xFF:4c00
```

### Pattern format

```
offset:ad_type:hex_content
```

| Field | Description |
|-------|-------------|
| `offset` | Byte position within the AD field where matching starts (usually 0) |
| `ad_type` | BLE AD data type (hex or decimal) |
| `hex_content` | Pattern bytes as hex string (no `0x` prefix) |

Common AD types:

| AD Type | Name |
|---------|------|
| `0x01` | Flags |
| `0x02` / `0x03` | 16-bit UUID (incomplete / complete) |
| `0x06` / `0x07` | 128-bit UUID (incomplete / complete) |
| `0x08` / `0x09` | Shortened / Complete Local Name |
| `0x0A` | Tx Power Level |
| `0x19` | Appearance |
| `0xFF` | Manufacturer Specific Data |

## Python API

```python
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from bleep.dbuslayer.adv_monitor import (
    AdvMonitorApp, AdvMonitorManager,
    MonitorPattern, RSSIConfig, MonitorCallbacks,
)

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()

mgr = AdvMonitorManager(bus, "/org/bluez/hci0")
print("Supported types:", mgr.get_supported_types())

app = AdvMonitorApp(bus)
app.add_monitor(
    monitor_type="or_patterns",
    rssi=RSSIConfig(high_threshold=-60, high_timeout=3),
    patterns=[MonitorPattern(0, 0x09, b"HE")],
    callbacks=MonitorCallbacks(
        on_device_found=lambda path: print(f"Found: {path}"),
        on_device_lost=lambda path: print(f"Lost: {path}"),
    ),
)
mgr.register(app)

loop = GLib.MainLoop()
try:
    loop.run()
finally:
    mgr.unregister(app)
    app.remove_all()
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `org.freedesktop.DBus.Error.UnknownObject` on register | Ensure bluetoothd runs with `--experimental` flag |
| `SupportedMonitorTypes` is empty | Kernel or adapter firmware does not support monitor offload; software fallback still works |
| No `DeviceFound` events | Check that patterns match real advertisement data; use `btmon` to inspect raw ADV_IND PDUs |
