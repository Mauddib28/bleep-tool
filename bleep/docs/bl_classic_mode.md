---
description: User-level guide for Bluetooth Classic features (scan, SDP enumeration, PBAP) in BLEEP
---

# Bluetooth Classic Support in **BLEEP**

BLEEP started as a Bluetooth Low Energy (BLE) toolkit.  Since v0.6 the same
modular infrastructure also covers **Bluetooth Classic / BR-EDR** operations.
This document explains prerequisites, commands, typical flows, logging, and
troubleshooting for Classic devices.

> The Classic helpers live next to the BLE ones – no special install step is
> required once BLEEP is installed in *editable* mode (`pip install -e .`).

---

## 1  Requirements

* BlueZ ≥ 5.55 (tested 5.66)
* `bluetooth-obexd` service **enabled & running** – required for PBAP transfer
* Adapter must be powered, discoverable / pairable as usual (`bluetoothctl`)
* The target phone/head-unit **paired & trusted** – PBAP typically rejects
  anonymous connections.

```bash
# enable obexd (Ubuntu / Debian)
sudo systemctl enable --now bluetooth-obexd.service
```

---

## 2  Command reference

| Command | Purpose |
|---------|---------|
| `classic-scan` | BR/EDR inquiry scan – lists nearby Classic devices |
| `classic-enum <MAC>` | SDP browse + records; prints RFCOMM services table (supports `--debug` for enhanced attributes, `--connectionless` for l2ping reachability check, `--version-info` for Bluetooth version information, `--analyze` for comprehensive SDP analysis) |
| `classic-pbap <MAC> --out <file.vcf>` | Pull full phone-book (VCF) via PBAP |
| Debug Mode: `csdp <MAC> [--connectionless]` | SDP discovery without full connection (connectionless mode with l2ping reachability check) |
| Debug Mode: `pbap [options]` | Interactive PBAP phonebook dumps from connected Classic devices |

All commands share global CLI flags such as `--hci <index>` and logging level.
Run `python -m bleep.cli --help` for details.

### 2.1  Scan example
```bash
# Simple
python -m bleep.cli classic-scan

# With discovery filters (BlueZ ≥5.55)
python -m bleep.cli classic-scan --uuid 112f,110b --rssi -65 --timeout 8
#  └─ only show devices advertising **PBAP (0x112f)** or **A2DP (0x110b)** and stronger than –65 dBm
# Path-loss filter (BlueZ ≥5.59)
python -m bleep.cli classic-scan --pathloss 70 --timeout 6
# With debug output
python -m bleep.cli classic-scan --debug
```
Output columns: MAC | Name | RSSI | Class | Flags (Paired/Trusted…).

### 2.2  Service enumeration example
```bash
# Basic enumeration
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E

# With debug output (shows enhanced SDP attributes)
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E --debug

# With connectionless mode (l2ping reachability check before SDP query)
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E --connectionless

# Combined: debug + connectionless
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E --debug --connectionless

# With version information (shows vendor/product IDs, profile versions, HCI/LMP versions)
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E --version-info

# All flags combined
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E --debug --connectionless --version-info

# With comprehensive SDP analysis (protocol analysis, version inference, anomaly detection)
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E --analyze

# Combined: all analysis features
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E --debug --version-info --analyze
```

Typical output (JSON format):
```json
{
  "OPP server": 16,
  "Voice Gateway": 3,
  "Hands-Free AG": 4,
  "PBAP server": 17
}
```

With `--debug` flag, enhanced SDP attributes are displayed:
```
[classic-enum] Found 5 SDP records
  [1] OPP server (UUID: 0x1105, Channel: 16) [Profiles: 1] (UUID: 0x1105, Ver: 256)
  [2] Voice Gateway (UUID: 0x1112, Channel: 3) [Profiles: 1] (UUID: 0x1112, Ver: 256)
  [3] Voice Gateway (UUID: 0x111f, Channel: 4) [Profiles: 1] (UUID: 0x111f, Ver: 261)
  [4] PBAP server (UUID: 0x112f, Channel: 17) [Profiles: 1] (UUID: 0x112f, Ver: 256)
  [5] BT DIAG (UUID: 0x1101, Channel: 18)
```

**Enhanced SDP Attributes Extracted:**
- **Service Record Handle** (0x0000) – Unique record identifier
- **Profile Descriptors** (0x0009) – Bluetooth profile UUIDs and versions
- **Service Version** (0x0300) – Service-specific version number
- **Service Description** (0x0101) – Human-readable service description

BLEEP first runs `sdptool browse --tree` (fast).  If a PBAP entry is missing or
no RFCOMM channels appear it automatically falls back to `sdptool records`.

**Connectionless SDP Queries:** SDP enumeration works without requiring a full
Bluetooth connection. If connection fails, BLEEP will still display SDP results
from the connectionless query, making it useful for reconnaissance even when
devices are not available for full connection.

**Reachability Check (`--connectionless` flag):** When enabled, BLEEP verifies device
reachability using `l2ping` before attempting SDP queries. This provides:
- **Faster failure detection** – l2ping typically completes in ~13 seconds vs. potential 30+ second SDP timeout
- **Better error messages** – Distinguishes unreachable devices from SDP-specific failures
- **Improved reconnaissance workflow** – Quickly identify which devices are actually reachable before spending time on SDP queries

**Version Information (`--version-info` flag):** When enabled, BLEEP displays comprehensive
Bluetooth version information:
- **Device Identification** – Vendor ID, Product ID, Version (from Device1 properties or Modalias)
- **Profile Versions** – Extracted from SDP records with Bluetooth spec version hints
- **Local Adapter Reference** – HCI/LMP version of your local adapter (for comparison)
- **Raw Properties** – Unprocessed property values preserved for offline analysis
- **Spec Version Mapping** – Profile versions mapped to likely Bluetooth Core Specification versions (heuristic)

Example output with `--version-info`:
```
=== Version Information ===
Vendor ID: 0x000A
Product ID: 0x0000
Version: 0x0000
Modalias: bluetooth:v000Ap0000d0000

Profile Versions (from SDP):
  0x1105: 0x0100 (~Bluetooth 1.0)
  0x1112: 0x0100 (~Bluetooth 1.0)
  0x111f: 0x0105 (~Bluetooth 1.5)
  0x112f: 0x0100 (~Bluetooth 1.0)

Local Adapter (for reference):
  LMP Version: 5 (Bluetooth 3.0 + HS)
  HCI Version: 5
  Manufacturer ID: 15
============================
```

**Comprehensive SDP Analysis (`--analyze` flag):** When enabled, BLEEP performs advanced
analysis of SDP records:
- **Protocol Analysis** – Identifies all protocols used (RFCOMM, L2CAP, BNEP, OBEX, etc.)
- **Profile Version Analysis** – Cross-references profile versions across all services
- **Version Inference** – Infers Bluetooth Core Specification version from profile patterns
- **Anomaly Detection** – Identifies version inconsistencies, unusual profile versions, and missing attributes
- **Service Relationships** – Groups related services and identifies service dependencies
- **Comprehensive Reporting** – Human-readable report with detailed analysis

Example output with `--analyze`:
```
============================================================
SDP Comprehensive Analysis Report
============================================================

Total SDP Records: 5

--- Protocol Analysis ---
Protocols Found: RFCOMM, L2CAP
RFCOMM Channels: 3, 4, 16, 17, 18

--- Profile Analysis ---
Unique Profiles: 4
Version Distribution:
  Bluetooth 1.0: 3 profile(s)
  Bluetooth 1.5: 1 profile(s)

--- Version Inference ---
Inferred Bluetooth Spec: 1.5
Confidence: 75.0%

--- Detected Anomalies (1) ---
  [LOW] missing_service_name: Service 0x1101 missing name

--- Service Relationships ---
  Related Services: Voice Gateway, Hands-Free AG
============================================================
```

**Where do the UUIDs come from?**  Use the 16-bit or 128-bit Service Class UUID
advertised by the remote device (shown in the *Output* column of `classic-enum`)
or consult the SIG Assigned Numbers list.  BLEEP bundles a YAML copy under
`References/service_uuids.yaml`; the raw text is shipped in
`workDir/BlueZDocs/assigned-numbers.txt` for quick lookup.

Example: PBAP-PSE advertises Service Class UUID `0x112f` → pass `--uuid 112f`.

### 2.3  Phone-book dump
```bash
python -m bleep.cli classic-pbap 14:89:FD:31:8A:7E --out /tmp/phone.vcf
# If the phone shows an authorisation prompt use --auto-auth to register a
# temporary OBEX agent that auto-accepts:
python -m bleep.cli classic-pbap 14:89:FD:31:8A:7E --out /tmp/phone.vcf --auto-auth
```
Flow:
1. Create `org.bluez.obex.Client1` session with Target =`"PBAP"`.
2. `Select("int", "pb")` (ignored if phone does not implement it).
3. `PullAll("", {"Format":"vcard21"})` – BlueZ stores file in `$XDG_CACHE_HOME`.
4. On `Transfer1` *complete* event the file is moved to `--out` path.

If the D-Bus path fails (service not running / permissions) a descriptive error
is raised.  Check log files below.

### 2.4  Debug Mode SDP Discovery (Connectionless)

The debug mode (`python -m bleep -m debug`) includes a `csdp` command for SDP discovery on Classic devices. This command supports connectionless mode with l2ping reachability checking, matching the functionality of the CLI `classic-enum --connectionless` flag.

**Features:**
- Regular SDP discovery (no connection required)
- Connectionless mode with l2ping reachability check (faster failure detection)
- Configurable l2ping parameters
- Detailed SDP record display with all enhanced attributes
- Automatic service map generation from discovered records

**Usage:**
```bash
# Start debug mode
python -m bleep -m debug

# Regular SDP discovery (no connection required)
BLEEP-DEBUG> csdp 14:89:FD:31:8A:7E
[*] Performing SDP discovery for 14:89:FD:31:8A:7E...
[+] Found 5 SDP record(s)

SDP Records:
================================================================================

Record 1:
  Name: PBAP server
  UUID: 0x112f
  RFCOMM Channel: 19
  Service Record Handle: 0x0001
  Service Version: 0x0100
  Profile Descriptors:
    0x112f: Version 0x0100

...

Service Map (5 service(s)):
  PBAP server              → 19
  Hands-Free AG            → 17
  Audio Source             → 16
  ...

# Connectionless mode with l2ping reachability check
BLEEP-DEBUG> csdp 14:89:FD:31:8A:7E --connectionless
[*] Performing connectionless SDP discovery for 14:89:FD:31:8A:7E...
[*] Checking reachability via l2ping (count=3, timeout=13s)...
[+] Found 5 SDP record(s)
...

# Custom l2ping parameters
BLEEP-DEBUG> csdp 14:89:FD:31:8A:7E --connectionless --l2ping-count 5 --l2ping-timeout 20
[*] Performing connectionless SDP discovery for 14:89:FD:31:8A:7E...
[*] Checking reachability via l2ping (count=5, timeout=20s)...
[+] Found 5 SDP record(s)
...
```

**Command Options:**
- `<MAC>` – Target MAC address (required)
- `--connectionless` – Verify device reachability via l2ping before SDP query (faster failure detection)
- `--l2ping-count <N>` – Number of l2ping echo requests (default: 3)
- `--l2ping-timeout <N>` – Seconds to wait for l2ping (default: 13)

**Benefits of Connectionless Mode:**
- **Faster failure detection** – Unreachable devices detected in ~13 seconds vs. 30+ seconds for SDP timeout
- **Better error messages** – Distinguishes between unreachable devices and SDP failures
- **No connection required** – Works without pairing or establishing a full Bluetooth connection
- **Reconnaissance** – Useful for discovering services before attempting connection

**Error Handling:**
- If device is unreachable in connectionless mode, provides clear error message and skips SDP query
- If l2ping is unavailable, falls back to regular SDP discovery with warning
- Detailed error reporting for debugging

### 2.5  Debug Mode PBAP Command

The debug mode (`python -m bleep -m debug`) now includes a `pbap` command for interactive PBAP phonebook dumps from Classic devices. This provides the same functionality as the `classic-pbap` CLI command but within the debug shell environment.

**Prerequisites:**
- Classic device must be connected via `cconnect <mac>` command
- Device must support PBAP service
- `bluetooth-obexd` service must be running

**Usage:**
```bash
# Start debug mode and connect to Classic device
python -m bleep -m debug
BLEEP-DEBUG> cconnect 14:89:FD:31:8A:7E
[+] Connected to 14:89:FD:31:8A:7E – 5 RFCOMM services

# Basic PBAP dump (PB repository only)
BLEEP-DEBUG[14:89:FD:31:8A:7E]> pbap
[+] Starting PBAP dump for 14:89:FD:31:8A:7E (repos: PB, format: vcard21)...
[+] PBAP dump successful
[+] Saved PB → /tmp/1489fd318a7e_PB.vcf (1234 lines, 45 entries)

# Multiple repositories
BLEEP-DEBUG[14:89:FD:31:8A:7E]> pbap --repos PB,ICH,OCH
[+] Saved PB → /tmp/1489fd318a7e_PB.vcf (1234 lines, 45 entries)
[+] Saved ICH → /tmp/1489fd318a7e_ICH.vcf (567 lines, 12 entries)
[+] Saved OCH → /tmp/1489fd318a7e_OCH.vcf (890 lines, 23 entries)

# Custom output file (single repository only)
BLEEP-DEBUG[14:89:FD:31:8A:7E]> pbap --out /tmp/my_phonebook.vcf
[+] Saved PB → /tmp/my_phonebook.vcf (1234 lines, 45 entries)

# With auto-authentication and extended watchdog
BLEEP-DEBUG[14:89:FD:31:8A:7E]> pbap --auto-auth --watchdog 15
[+] PBAP dump successful
[+] Saved PB → /tmp/1489fd318a7e_PB.vcf (1234 lines, 45 entries)

# vCard 3.0 format
BLEEP-DEBUG[14:89:FD:31:8A:7E]> pbap --format vcard30
[+] Saved PB → /tmp/1489fd318a7e_PB.vcf (1456 lines, 45 entries)
```

**Command Options:**
- `--repos <list>` – Comma-separated repository list (PB, ICH, OCH, MCH, CCH, SPD, FAV) or ALL (default: PB)
- `--format <vcard21|vcard30>` – vCard format version (default: vcard21)
- `--auto-auth` – Register temporary OBEX agent that auto-accepts authentication prompts
- `--watchdog <seconds>` – Watchdog timeout before aborting stalled transfer (default: 8, 0 to disable)
- `--out <path>` – Output file path (for single repository only; multi-repo uses `/tmp/<mac>_<repo>.vcf`)

**Features:**
- Automatically detects PBAP service from service map or SDP records
- Supports all PBAP repositories (PB, ICH, OCH, MCH, CCH, SPD, FAV)
- Automatic database integration (if enabled) – saves PBAP metadata with hash and entry counts
- Comprehensive error handling with helpful diagnostic messages
- Entry counting and file statistics display

**Error Handling:**
- If PBAP service not found, suggests running `cservices` to check available services
- If OBEX service unavailable, provides instructions to start `bluetooth-obexd`
- Detailed D-Bus error reporting for debugging

### 2.6  Reachability test (l2ping)
```bash
python -m bleep.cli classic-ping 14:89:FD:31:8A:7E --count 5
# → prints average RTT or error if device not reachable
# (may need sudo on some distros because *l2ping* requires CAP_NET_RAW)
```

---

## 3  Logging

BLEEP writes per-category logs to `/tmp` (overwritten each run):

| File suffix | What it contains |
|-------------|------------------|
| `__logging__general.txt` | High-level progress lines |
| `__logging__debug.txt`   | Retry loops, D-Bus method names, SDP raw output |
| `__logging__enumeration.txt` | Parsed SDP records table |
| `__logging__usermode.txt`| RFCOMM connect attempts |

Enable verbose CLI flag `-v` to mirror *general* log on stdout.

---

## 4  Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `obexd PBAP path failed – will try RFCOMM fallback` | `bluetooth-obexd` not running OR phone requires bonding | `sudo systemctl start bluetooth-obexd`; make sure phone is paired & trusted |
| `PBAP service not found on device (no RFCOMM channel)` | Phone hides PBAP until authenticated OR SDP cache stale | Pair first; run `classic-enum` again; power-cycle phone |
| `org.bluez.obex.Error.Failed: Too short header in packet` | **Stale OBEX state on device** (previous transfer aborted mid-flight) | **SOLUTION CONFIRMED: Restart the target device** to clear OBEX buffers. Alternative: `bluetoothctl disconnect <MAC>` then reconnect. |
| `BlueZ obexd PBAP transfer failed; see logs for details` | Transfer aborted by remote, wrong repository selected | Check `/tmp/...debug.txt`; some feature phones only expose `int/pb.vcf` after `Select` – already handled; open an issue if persists |
| `Failed to connect … Operation timed out` | Device busy or radio glitch | Retry; Classic connect uses 5×2 s back-off |
| `org.freedesktop.DBus.Error.NoReply` or `Timed out waiting for response` during PBAP | Bluetooth controller stuck in half-open BR/EDR connection (BlueZ bug) | In `bluetoothctl` type `disconnect <MAC>` for the target device, wait 2-3 s, then re-run the command.  Power-cycling the phone is a second fallback. |

---

## 5  Limitations / roadmap

* Only **PBAP-PSE** is implemented.  Other OBEX profiles (MAP, SYNC) pending.
* No automatic OBEX-AUTH support; relies on BlueZ trust settings (though `--auto-auth` flag available in CLI and debug mode).
* Integration tests for Classic flows (task **bc-12**) completed.

---

*Last updated: 2025-11-09 (Enhanced SDP attributes, debug mode, connectionless queries, version detection, comprehensive SDP analysis, debug mode PBAP command, debug mode connectionless SDP discovery)* 

---

## 6  Temporary Classic-Feature TODO Tracker  
*(will be removed once every item is ✅ completed)*

| ID | Task | Status |
|----|------|--------|
| bc-01 | Research BlueZ D-Bus APIs for Classic (discovery, SDP, RFCOMM, PBAP) | ⏱️ pending |
| bc-02 | Design high-level Classic API surface mirroring BLE helpers | ✅ completed |
| bc-03 | Implement `dbuslayer.device_classic` wrapper | ✅ completed |
| bc-04 | Create SDP service-discovery helper (`classic_sdp.py`) | ✅ completed |
| bc-05 | Parse RFCOMM channels from SDP records | ✅ completed |
| bc-06 | Extend `classic_connect_and_enumerate()` to return service→channel map | ✅ completed |
| bc-07 | PBAP phone-book dump helper via BlueZ OBEX D-Bus | ✅ completed |
| bc-08 | Add `br_ops` equivalents (`classic_scan`, `classic_connect_and_enumerate`) | ✅ completed |
| bc-09 | Add CLI sub-commands `classic-scan` & `classic-enum` | ✅ completed |
| bc-10 | Debug-mode interactive support for Classic devices (PBAP command) | ✅ completed |
| bc-11 | Write documentation for Classic mode & update README TOC | ✅ completed |
| bc-12 | Integration tests for Classic flow incl. PBAP | ✅ completed |
| bc-13 | Update CHANGELOG / todo_tracker after full feature set | ✅ completed |

Legend: ⏱️ pending 🔄 in-progress ✅ completed 

---

## 7  Feature Tracker

| Feature | Status |
|---------|--------|
| Classic discovery (`cscan`) | ✅ |
| Classic SDP discovery (`csdp` with connectionless mode) | ✅ |
| Classic connection (`cconnect`) | ✅ |
| Classic services listing (`cservices`) | ✅ |
| Classic PBAP dump (CLI `classic-pbap` and debug mode `pbap`) | ✅ |
| BLE scan presets (shared CLI `bleep scan --variant`) | ✅ | 