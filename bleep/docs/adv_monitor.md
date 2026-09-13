# Advertisement Monitor — Kernel-Offloaded Passive Scanning

## Overview

The Advertisement Monitor feature (BZ-11/12) provides kernel-offloaded BLE
advertisement pattern matching via the BlueZ `AdvertisementMonitor1` and
`AdvertisementMonitorManager1` experimental interfaces.  Unlike active
scanning with `StartDiscovery`, advertisement monitors run entirely in the
kernel's HCI layer — bluetoothd only wakes userspace when a matching device
appears or disappears.

**Use cases:**

- Long-duration passive presence detection without CPU-intensive active scans
- Pattern-based filtering (match specific AD types, manufacturer data, service UUIDs)
- RSSI-gated detection (only trigger when signal exceeds a threshold)
- Device found/lost event streaming

## Prerequisites

1. **BlueZ experimental mode**: bluetoothd must be running with the `-E` flag
   (or `Experimental = true` in `/etc/bluetooth/main.conf`). Confirm with
   `bleep --check-env` (HW-2 prints `AdvertisementMonitorManager1` /
   `ConnectDevice`).
2. **Kernel support**: Linux 5.10+ with `MSFT` HCI extensions (Intel, Qualcomm,
   MediaTek controllers) or software-based fallback in BlueZ 5.64+.
3. **Same-adapter overlay is allowed**: BlueZ delivers `DeviceFound` /
   `DeviceLost` “no matter if there is an ongoing discovery session.” Survey
   registers monitors **on top of** `StartDiscovery`. `STOP_CLEARS` still
   applies only to `StopDiscovery` (unpaired beacons vanish when discovery
   stops) — that is unrelated to AdvMonitor.

Check support:

```bash
bleep advertise-monitor caps
```

## CLI Usage

### Query Capabilities

```bash
bleep advertise-monitor caps [--adapter hci0]
```

Shows `SupportedMonitorTypes` (typically `or_patterns`) and
`SupportedFeatures` reported by the adapter's
`AdvertisementMonitorManager1` interface.

### Start Monitoring

```bash
bleep advertise-monitor start [OPTIONS]
```

Registers a monitor with BlueZ and streams `DeviceFound`/`DeviceLost`
events to the terminal (or structured JSON with `--json`).

**Options:**

| Flag | Description | Default |
|------|-------------|---------|
| `-p`, `--pattern OFF:AD:HEX` | Pattern to match (repeatable). Format: `start_offset:ad_type:hex_content` | omitted → Flags-OR overlay (not BlueZ match-all) |
| `--manufacturer CID[:HEX]` | Manufacturer AD (`0xFF`) at offset 0: company id + optional payload hex. Repeatable. With no `-p`, replaces Flags-OR | none |
| `--mfr-string TEXT` | UTF-8 string in manufacturer payload after the 2-byte CID (`0xFF` offset 2). Repeatable. With no `-p`, replaces Flags-OR | none |
| `--rssi-high THRESHOLD` | High RSSI threshold in dBm (-127 to 20) | None (unset) |
| `--rssi-high-timeout SECS` | Seconds signal must exceed high threshold (1-300) | 0 (unset) |
| `--rssi-low THRESHOLD` | Low RSSI threshold in dBm (-127 to 20) | None (unset) |
| `--rssi-low-timeout SECS` | Seconds signal must stay below low threshold (1-300) | 0 (unset) |
| `--sampling-period N` | RSSI sampling period (0 = report all events) | 0 |
| `--duration SECS` | Auto-stop after N seconds | None (Ctrl-C) |
| `--adapter NAME` | Adapter to use | hci0 |

**Pattern format:**

```
offset:ad_type:hex_content
```

- `offset` — byte position within the AD field where matching starts (usually 0)
- `ad_type` — BLE advertisement data type (hex or decimal):
  - `0x01` — Flags
  - `0x02`/`0x03` — 16-bit Service UUIDs (incomplete/complete)
  - `0x06`/`0x07` — 128-bit Service UUIDs (incomplete/complete)
  - `0x08`/`0x09` — Shortened/Complete Local Name
  - `0x0A` — TX Power Level
  - `0x19` — Appearance
  - `0xFF` — Manufacturer Specific Data
- `content` — hex bytes to match (max 31 bytes). **Must be non-empty.** BlueZ
  `bt_ad_pattern_new` rejects empty `Patterns` / empty content (`Release`, 0
  events). BLEEP never sends an empty monitor.

**Default overlay (no `-p`).** One `or_patterns` child: GAP Flags (`0x01`)
content `{00,02,04,05,06,18,1A}`. Live on this host (2026-09-04):
`-p 0:0x01:00 -p 0:0x01:02 -p 0:0x01:04 -p 0:0x01:06 --sampling-period 255`
→ Activate, 6 unique FOUND, clean Release, no daemon restart. Prefix-covers
(8×256 / 62×256) `NoReply`-killed bluetoothd and are not used. Completeness
for survey remains StartDiscovery harvest — see
[survey `--listen-monitor`](survey_mode.md#listen-monitor-overlay---listen-monitor).

MSFT `controller-patterns` still accepts this Flags-OR set (7 ≤ 16
patterns/monitor). Discovery harvest remains the complete census.

## Examples

### Flags-OR overlay (no `-p`)

```bash
bleep advertise-monitor start --sampling-period 255 --duration 60
```

Registers the Flags-OR overlay described above. This is **not** a BlueZ
“match all” — empty `or_patterns` is illegal and would `Release` immediately.

### Match devices with specific manufacturer data

Company id (little-endian on the wire) plus optional payload prefix — no raw
`OFF:AD:HEX` required:

```bash
# Microsoft CID 6 (live: tags Flags-00 beacons that Flags-OR missed)
bleep advertise-monitor start --manufacturer 0x0006 --sampling-period 255 --duration 20

# ESP32 0xFFFF payload starting 5a33 ("Z3")
bleep advertise-monitor start --manufacturer 0xFFFF:5a33 --mfr-string Z3 --sampling-period 255 --duration 20
```

Equivalent raw pattern for Apple iBeacon prefix (`4C00` + `0215`):

```bash
bleep advertise-monitor start -p 0:0xFF:4c000215
# or:  --manufacturer 0x004C:0215
```

### RSSI-gated proximity detection

Only trigger for devices closer than -50 dBm, with 3-second confirmation:

```bash
bleep advertise-monitor start --rssi-high -50 --rssi-high-timeout 3
```

### Match by device name prefix

Match devices whose Complete Local Name starts with "Light":

```bash
bleep advertise-monitor start -p 0:0x09:4c69676874
```

(`4c69676874` = hex for "Light")

### Multiple patterns (OR logic)

Match either manufacturer data OR specific service UUID:

```bash
bleep advertise-monitor start -p 0:0xFF:4c00 -p 0:0x03:0d18
```

### JSON output for programmatic consumption

```bash
bleep --json advertise-monitor start --duration 30
```

Output (one JSON line per event):

```json
{"event": "device_found", "mac": "F0:98:7D:0A:05:07", "elapsed_s": 2.3}
{"event": "device_lost", "mac": "F0:98:7D:0A:05:07", "elapsed_s": 45.1}
{"event": "monitor_stopped", "elapsed_s": 30.0, "found_count": 3, "lost_count": 1}
```

## Architecture

```
┌───────────────────────────────────────────────────┐
│  bleep advertise-monitor start                              │
│   └─ modes/monitor.py                             │
│       └─ dbuslayer/adv_monitor.py                 │
│           ├─ AdvMonitorManager (register/unreg)   │
│           ├─ AdvMonitorApp (ObjectManager root)   │
│           └─ AdvMonitor (per-monitor D-Bus obj)   │
│               ├─ Activate()   ← bluetoothd        │
│               ├─ Release()    ← bluetoothd        │
│               ├─ DeviceFound()← bluetoothd        │
│               └─ DeviceLost() ← bluetoothd        │
└───────────────────────────────────────────────────┘
         │ RegisterMonitor(app_path)
         ▼
┌───────────────────────────────────────────────────┐
│  bluetoothd (AdvertisementMonitorManager1)        │
│   └─ HCI kernel offload (MSFT extensions)         │
│      or software-based pattern matching           │
└───────────────────────────────────────────────────┘
```

**Key classes:**

| Class | Module | Role |
|-------|--------|------|
| `AdvMonitorManager` | `dbuslayer/adv_monitor.py` | Wraps `AdvertisementMonitorManager1`; handles register/unregister |
| `AdvMonitorApp` | `dbuslayer/adv_monitor.py` | D-Bus `ObjectManager` root; manages child monitors |
| `AdvMonitor` | `dbuslayer/adv_monitor.py` | Per-monitor D-Bus service object; receives callbacks |
| `MonitorPattern` | `dbuslayer/adv_monitor.py` | Pattern dataclass (offset + AD type + content) |
| `RSSIConfig` | `dbuslayer/adv_monitor.py` | RSSI threshold/timeout configuration |

## Comparison with Active Scanning

| Feature | `bleep scan` | `bleep advertise-monitor start` |
|---------|-------------|----------------------|
| Power consumption | High (active inquiry) | Low (kernel offload) |
| Result type | Snapshot of visible devices | Event stream (found/lost) |
| Pattern filtering | Post-scan in userspace | Pre-filter in kernel |
| RSSI thresholds | Manual post-filter | Built-in kernel support |
| Duration | Fixed timeout | Indefinite (until Ctrl-C) |
| Concurrent with scan | N/A | Allowed (Found/Lost fire during StartDiscovery) |
| Requires experimental | No | Yes (`-E` flag) |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Cannot access AdvertisementMonitorManager1` | bluetoothd not in experimental mode | Restart with `bluetoothd -E` or add `Experimental = true` to `/etc/bluetooth/main.conf`. `bleep --check-env` reports this as a dedicated experimental line. |
| Monitor `Release` / 0 events immediately | Empty `or_patterns` (illegal) or RegisterMonitor failed | BLEEP injects Flags-OR when `-p` is omitted and refuses empty patterns. Check `--check-env`. |
| Monitor registered but few events | Catch-all is prefix-OR, not Device1 harvest; MSFT offload covers Flags+manufacturer only | Use `bleep survey --listen-monitor` so StartDiscovery harvest unions with Found. |
| `SupportedMonitorTypes: (none)` | Adapter/kernel too old | Requires Linux 5.10+ and BlueZ 5.55+ |
| Events stop after `--duration` | Expected behavior | Remove `--duration` for indefinite monitoring |

## Related

- `bleep scan` — StartDiscovery scan; `bleep scan --monitor` is Flags-OR AdvMonitor (no Device1 harvest)
- `bleep survey --listen-monitor` — Device1 harvest **union** AdvMonitor Found (census completeness)
- BlueZ docs: `workDir/BlueZDocs/org.bluez.AdvertisementMonitor.rst`
- BlueZ docs: `workDir/BlueZDocs/org.bluez.AdvertisementMonitorManager.rst`
- Reference script: `workDir/BlueZScripts/example-adv-monitor`
