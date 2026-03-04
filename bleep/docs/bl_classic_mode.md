---
description: User-level guide for Bluetooth Classic features (scan, SDP, PBAP, RFCOMM data exchange, OPP, MAP, FTP, PAN, SPP, SYNC) in BLEEP
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
* `bluetooth-obexd` service **enabled & running** – required for PBAP, OPP, and MAP
* Adapter must be powered, discoverable / pairable as usual (`bluetoothctl`)
* The target phone/head-unit **paired & trusted** – OBEX profiles typically reject
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
| `classic-opp <MAC> send <file>` / `pull` | Send a file or pull business card via OPP |
| `classic-map <MAC> folders\|list\|get\|push\|inbox\|types\|fields\|monitor\|instances [--instance N]` | Browse, manage, and monitor SMS/MMS via MAP (use `--instance` for multi-MAS) |
| `classic-ftp <MAC> ls\|get\|put\|mkdir\|rm` | Browse and transfer files via OBEX FTP |
| `classic-pan connect\|disconnect\|status\|serve\|unserve <MAC>` | Personal Area Networking – PAN client & server |
| `classic-spp register\|unregister\|status [--channel N]` | SPP serial port profile registration |
| `classic-sync <MAC> get\|put [--location int\|sim1]` | IrMC Synchronization – download/upload phonebook |
| `classic-bip <MAC> props\|get\|thumb <handle>` | Basic Imaging Profile – image properties / download / thumbnail [experimental] |
| Raw OBEX over RFCOMM (design doc) | ✅ |
| L2CAP raw channel access (design doc) | ✅ |
| Debug Mode: `csdp <MAC> [--connectionless]` | SDP discovery without full connection (connectionless mode with l2ping reachability check) |
| Debug Mode: `pbap [options]` | Interactive PBAP phonebook dumps from connected Classic devices |
| Debug Mode: `copen` / `csend` / `crecv` / `craw` | RFCOMM data-exchange commands (open socket, send, receive, interactive session) |
| Debug Mode: `copp send <file>` / `copp pull` | Object Push Profile – send files or pull business cards |
| Debug Mode: `cmap folders\|list\|get\|push\|inbox\|types\|fields\|monitor\|instances [--instance N]` | Message Access Profile – browse, manage, and monitor SMS/MMS (multi-MAS) |
| Debug Mode: `cftp ls\|cd\|get\|put\|mkdir\|rm\|cp\|mv` | File Transfer Profile – browse and transfer files |
| Debug Mode: `cpan connect\|disconnect\|status\|server` | Personal Area Networking (PAN) – client & server |
| Debug Mode: `cspp register\|unregister\|status` | SPP serial port profile – incoming connections feed `csend`/`crecv` |
| Debug Mode: `csync get\|put [--location int\|sim1]` | IrMC Synchronization – download/upload phonebook |
| Debug Mode: `cbip props\|get\|thumb <handle>` | Basic Imaging Profile [experimental] |

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

Typical output (formatted SDP records are always shown):
```
[+] Found 5 SDP record(s) for 14:89:FD:31:8A:7E

SDP Records:
================================================================================

Record 1:
  Name: OPP server
  UUID: 0x1105
  RFCOMM Channel: 16
  Profile Descriptors:
    0x1105: Version 0x0100

Record 2:
  Name: Voice Gateway
  UUID: 0x1112
  RFCOMM Channel: 3
  Profile Descriptors:
    0x1112: Version 0x0100

Record 3:
  Name: Hands-Free AG
  UUID: 0x111f
  RFCOMM Channel: 4
  Profile Descriptors:
    0x111f: Version 0x0105

Record 4:
  Name: PBAP server
  UUID: 0x112f
  RFCOMM Channel: 17
  Profile Descriptors:
    0x112f: Version 0x0100

Record 5:
  Name: BT DIAG
  UUID: 0x1101
  RFCOMM Channel: 18

================================================================================

Service Map (5 service(s)):
  OPP server                -> 16
  Voice Gateway             -> 3
  Hands-Free AG             -> 4
  PBAP server               -> 17
  BT DIAG                   -> 18
```

If the connection-based enumeration fails (e.g. `br-connection-create-socket`) but
SDP records were obtained, the command reports success with a warning:
```
[!] Connection failed (...), but SDP enumeration succeeded
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

### 2.7  RFCOMM Data Exchange (Debug Mode)

The debug shell provides raw RFCOMM data-exchange commands that operate on a
dedicated data socket, separate from the keep-alive socket (`ckeep`).

#### `copen` – Open / close the data socket

```bash
BLEEP-DEBUG[14:89:FD:31:8A:7E]> copen 18        # by channel number
BLEEP-DEBUG[14:89:FD:31:8A:7E]> copen --svc SPP  # by service name
BLEEP-DEBUG[14:89:FD:31:8A:7E]> copen --first    # first available
BLEEP-DEBUG[14:89:FD:31:8A:7E]> copen --status   # check status
BLEEP-DEBUG[14:89:FD:31:8A:7E]> copen --close    # close
```

#### `csend` – Send data over RFCOMM

```bash
BLEEP-DEBUG[14:89:FD:31:8A:7E]> csend str:AT+COPS?
BLEEP-DEBUG[14:89:FD:31:8A:7E]> csend hex:4f4b0d0a
BLEEP-DEBUG[14:89:FD:31:8A:7E]> csend file:/tmp/payload.bin
BLEEP-DEBUG[14:89:FD:31:8A:7E]> csend Hello World
```

Supports the same value formats as the BLE `write` command (`hex:`, `str:`,
`file:`, `uint8:`, etc.).  If no data socket is open, falls back to the
keep-alive socket with a warning.

#### `crecv` – Receive data from RFCOMM

```bash
BLEEP-DEBUG[14:89:FD:31:8A:7E]> crecv                  # 5s default timeout
BLEEP-DEBUG[14:89:FD:31:8A:7E]> crecv --timeout 10      # custom timeout
BLEEP-DEBUG[14:89:FD:31:8A:7E]> crecv --size 1024       # max buffer
BLEEP-DEBUG[14:89:FD:31:8A:7E]> crecv --hex             # force hex dump
BLEEP-DEBUG[14:89:FD:31:8A:7E]> crecv --save /tmp/rx.bin
```

#### `craw` – Interactive RFCOMM session

```bash
BLEEP-DEBUG[14:89:FD:31:8A:7E]> craw 18          # opens channel 18
BLEEP-DEBUG[14:89:FD:31:8A:7E]> craw --first     # first available
BLEEP-DEBUG[14:89:FD:31:8A:7E]> craw --hex       # hex-dump incoming
```

Opens a bidirectional interactive session: a background reader thread prints
incoming data, while the prompt accepts user input.  Type `quit` or press
`Ctrl+C` to end the session.  If no socket is open, `craw` opens one for the
session and closes it on exit.

### 2.8  Object Push Profile – OPP (Debug Mode)

Send files to or pull business cards from a connected Classic device via the
OBEX Object Push Profile (UUID `0x1105`).

```bash
BLEEP-DEBUG[14:89:FD:31:8A:7E]> copp send /tmp/photo.jpg
[+] OPP send complete: 12345/12345 bytes transferred

BLEEP-DEBUG[14:89:FD:31:8A:7E]> copp pull /tmp/card.vcf
[+] Business card saved → /tmp/card.vcf
```

**Prerequisites:** `bluetooth-obexd` running, device paired & trusted.  OPP
service detection is automatic from the SDP service map; if not found the
command attempts anyway.

### 2.9  Message Access Profile – MAP (Debug Mode)

Browse and manage SMS/MMS messages on a connected Classic device via the OBEX
Message Access Profile (UUIDs `0x1132` / `0x1134`).

```bash
# List message folders
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap folders

# List messages in a folder
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap list inbox

# Download a specific message
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap get 12345 /tmp/msg.txt

# Push / send a message
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap push /tmp/outgoing.bmsg

# Trigger inbox synchronisation
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap inbox

# View message properties
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap props 12345

# Mark as read / unread
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap read 12345 true

# Mark as deleted / undeleted
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap delete 12345
```

**Prerequisites:** same as OPP.  MAP service detection is automatic.

#### MNS Notification Monitoring

Monitor incoming message notifications in real-time via D-Bus
`PropertiesChanged` signals on `Message1` objects:

```
# Start monitoring (debug mode – runs in background)
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap monitor start

# Notifications appear as they arrive:
# [MNS] /org/bluez/obex/session1/message42
#       Status: notification
#       Type: sms-gsm
#       Sender: +1234567890

# Stop monitoring
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap monitor stop
```

CLI equivalent (blocks until Ctrl+C):

```bash
python -m bleep.cli classic-map AA:BB:CC:DD:EE:FF monitor
```

#### Metadata Queries

```
# List message types supported by the remote device
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap types

# List available filter fields for message listing
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap fields
```

CLI equivalents:

```bash
python -m bleep.cli classic-map AA:BB:CC:DD:EE:FF types
python -m bleep.cli classic-map AA:BB:CC:DD:EE:FF fields
```

**Note:** MNS monitoring requires `PyGObject` (`python3-gi`) for the GLib
main loop.  The monitor session stays open until explicitly stopped.

#### 2.7.6  Multi-Instance MAS Selection

Some devices expose multiple MAS instances (e.g. one for SMS and another for
email), each advertising a separate RFCOMM channel in their SDP records.  Use
`instances` to discover them and `--instance <channel>` to target a specific
one.

```
# Discover MAS instances via SDP
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap instances
  Channel   4  MAP SMS  (UUID 0x1132)
  Channel  10  MAP Email  (UUID 0x1132)

# Target the email MAS instance
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap --instance 10 folders
```

```bash
# CLI equivalents
python -m bleep.cli classic-map AA:BB:CC:DD:EE:FF instances
python -m bleep.cli classic-map AA:BB:CC:DD:EE:FF --instance 10 folders
```

Under the hood, `--instance` passes the RFCOMM channel as the `Channel` byte
in the `CreateSession` D-Bus call (per `org.bluez.obex.Client1`).  When
omitted, BlueZ connects to the first available MAS.

### 2.8  `cftp` – File Transfer Profile (OBEX FTP)

Browse and transfer files on a connected Classic device via the OBEX File
Transfer Profile (UUID `0x1106`, `org.bluez.obex.FileTransfer1`).

```
# List current remote folder
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cftp ls

# List a specific path (navigates from root)
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cftp ls Photos/2024

# Navigate to a folder (session-scoped, single-operation)
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cftp cd Documents

# Download a file
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cftp get report.pdf /tmp/report.pdf

# Upload a file
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cftp put /tmp/notes.txt

# Create a folder
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cftp mkdir NewFolder

# Delete a file or folder
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cftp rm oldfile.txt

# Copy/move on remote
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cftp cp source.txt backup.txt
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cftp mv temp.dat final.dat
```

**Prerequisites:** same as OPP.  FTP service detection (UUID `0x1106`) is automatic.

**Note:** Each sub-command opens and closes its own OBEX session.  The `cd`
command is illustrative — for multi-step workflows, use the operations-layer
functions or a `FtpSession` context manager directly.

### 2.9  `cpan` / `classic-pan` – Personal Area Networking

Connect to or host a Bluetooth PAN network using `org.bluez.Network1` (client)
and `org.bluez.NetworkServer1` (server) on the **system bus**.

Supported roles: `nap` (Network Access Point – internet sharing), `panu`
(Personal Area Network User), `gn` (Group Network).

```
# Connect to a paired device as NAP client
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cpan connect nap
[+] PAN connected – interface bnep0

# Check connection status
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cpan status

# Disconnect
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cpan disconnect

# Register as a PAN server (accepts incoming connections)
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cpan server register nap pan0

# Unregister server
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cpan server unregister nap
```

```bash
# CLI equivalents
python -m bleep.cli classic-pan connect AA:BB:CC:DD:EE:FF --role nap
python -m bleep.cli classic-pan status AA:BB:CC:DD:EE:FF
python -m bleep.cli classic-pan disconnect AA:BB:CC:DD:EE:FF
python -m bleep.cli classic-pan serve --role nap --bridge pan0
python -m bleep.cli classic-pan unserve --role nap
```

**Prerequisites:** Device must be paired and trusted.  The `Network1` interface
is available on device objects; `NetworkServer1` is on the local adapter.
A Linux bridge interface (e.g. `pan0`) may need to be created before serving.

### 2.10  `cspp` / `classic-spp` – Serial Port Profile

Register a custom SPP profile via BlueZ `ProfileManager1.RegisterProfile` on
the **system bus**.  When a remote device connects, the `Profile1.NewConnection`
callback delivers an RFCOMM file descriptor.

In **debug mode**, the incoming socket is automatically set as the RFCOMM data
socket used by `csend`/`crecv`/`craw`, enabling seamless bidirectional data
exchange without `copen`.

```
# Register as SPP server (auto-assigned channel)
BLEEP-DEBUG> cspp register

# Register with explicit RFCOMM channel
BLEEP-DEBUG> cspp register --channel 3 --name "My SPP"

# Check status
BLEEP-DEBUG> cspp status

# Unregister
BLEEP-DEBUG> cspp unregister
```

```bash
# CLI – register and block until Ctrl+C (prints received data to stdout)
python -m bleep.cli classic-spp register --channel 3
python -m bleep.cli classic-spp status
python -m bleep.cli classic-spp unregister
```

**Prerequisites:** `PyGObject` (`python3-gi`) required for the GLib mainloop
integration needed by `dbus.service.Object`.  The remote device must be paired
and trusted.

---

### 2.11  `csync` / `classic-sync` – IrMC Synchronization

Download or upload the entire phonebook via the legacy OBEX IrMC Synchronization
profile (`Synchronization1`, UUID `0x1104`).  Few modern devices advertise this
service; it is primarily useful for older handsets that expose phonebook data
through the IrMC store rather than PBAP.

The object store location can be set to `"int"` (internal memory, default) or
`"sim1"`, `"sim2"`, etc. for SIM card access.

```
# Download phonebook (internal store)
BLEEP-DEBUG> csync get

# Download phonebook from SIM card
BLEEP-DEBUG> csync get /tmp/sim_pb.vcf --location sim1

# Upload phonebook
BLEEP-DEBUG> csync put /tmp/contacts.vcf --location int
```

```bash
# CLI – download phonebook
python -m bleep.cli classic-sync AA:BB:CC:DD:EE:FF get --output /tmp/pb.vcf
python -m bleep.cli classic-sync AA:BB:CC:DD:EE:FF get --location sim1

# CLI – upload phonebook
python -m bleep.cli classic-sync AA:BB:CC:DD:EE:FF put /tmp/contacts.vcf --location int
```

**Prerequisites:** `bluetooth-obexd` must be running.  The target device must
be paired, trusted, and must advertise IrMC Sync (UUID `0x1104`).

---

### 2.12  `cbip` / `classic-bip` – Basic Imaging Profile [experimental]

Download images and thumbnails from a remote device via the BlueZ
**experimental** `Image1` interface (UUID `0x111A`).  The session target is
`"bip-avrcp"`.

> **Warning:** `Image1` is marked `[experimental]` in BlueZ.  `bluetooth-obexd`
> must be started with the `--experimental` flag for this interface to be
> available.  The API may change or be removed without notice.

```
# Get image properties for a handle
BLEEP-DEBUG> cbip props 1000001

# Download full image
BLEEP-DEBUG> cbip get 1000001 /tmp/image.jpg

# Download thumbnail
BLEEP-DEBUG> cbip thumb 1000001 /tmp/thumb.jpg
```

```bash
# CLI – image properties
python -m bleep.cli classic-bip AA:BB:CC:DD:EE:FF props 1000001

# CLI – download full image
python -m bleep.cli classic-bip AA:BB:CC:DD:EE:FF get 1000001 --output /tmp/image.jpg

# CLI – download thumbnail
python -m bleep.cli classic-bip AA:BB:CC:DD:EE:FF thumb 1000001 --output /tmp/thumb.jpg
```

**Prerequisites:** `bluetooth-obexd --experimental` must be running.  The
target device must be paired, trusted, and must advertise BIP (UUID `0x111A`
or `0x111B`).

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
| `OPP CreateSession failed` or `MAP CreateSession failed` | `bluetooth-obexd` not running, or device not paired/trusted | `sudo systemctl start bluetooth-obexd`; pair & trust device first |
| `OPP transfer timed out` / `MAP transfer timed out` | Remote device did not complete OBEX transfer in time | Increase timeout, restart remote device, check logs |
| `csend` / `crecv` → `Send failed` / `Receive failed` | RFCOMM socket disconnected or channel mismatch | Re-open with `copen`; verify channel with `cservices` |

---

## 5  Limitations / roadmap

### Implemented
* **PBAP** – phone-book dump via BlueZ obexd (CLI and debug mode).
* **OPP** – file send and business-card pull via BlueZ obexd (debug mode `copp`).
* **MAP** – folder browse, message list/get/push, inbox update, read/delete flags, multi-instance MAS selection (debug mode `cmap`).
* **FTP** – remote filesystem browse, get/put/mkdir/rm/cp/mv via BlueZ obexd (debug mode `cftp`).
* **RFCOMM data exchange** – raw send/recv/interactive session over any RFCOMM channel (debug mode `copen`/`csend`/`crecv`/`craw`).
* **PAN** – Personal Area Networking client and server via `Network1`/`NetworkServer1` (debug mode `cpan`, CLI `classic-pan`).
* **SPP** – Serial Port Profile registration via `ProfileManager1`/`Profile1`; incoming connections delivered as RFCOMM sockets (debug mode `cspp`, CLI `classic-spp`).

### Current limitations
* No automatic OBEX-AUTH support; relies on BlueZ trust settings (though `--auto-auth` flag available for PBAP in CLI and debug mode).
* Integration tests for Classic flows (task **bc-12**) completed; tests for new RFCOMM/OPP/MAP commands pending.

### Not yet implemented (future expansion)
* ~~**OBEX FTP**~~ – implemented in v2.7.5 (see `cftp` debug command).
* ~~**SYNC (IrMC Sync)**~~ – implemented in v2.7.11 (`csync`, `classic-sync`).
* ~~**MAP MNS**~~ – implemented in v2.7.7 via `PropertiesChanged` signal monitoring on `Message1` objects (`cmap monitor`, `classic-map monitor`).
* ~~**MAP multi-instance**~~ – implemented in v2.7.8 via `--instance` flag on `cmap` and `classic-map` (`Channel` byte in `CreateSession`); `cmap instances` / `classic-map instances` for SDP-based discovery.
* ~~**BIP (Basic Imaging Profile)**~~ – implemented in v2.7.12 (`cbip`, `classic-bip`).  **Experimental** – requires `obexd --experimental`.
* **Raw OBEX over RFCOMM** – design document complete (`bleep/protocols/obex_design.md`).  Implementation planned for v2.7.13+.  Bypasses `obexd` to implement OBEX protocol directly on top of `classic_rfccomm_open`.
* **L2CAP raw channel access** – design document complete (`bleep/protocols/l2cap_design.md`).  Implementation planned for v2.7.13+.  Raw data exchange over L2CAP (non-RFCOMM) channels.
* ~~**CLI sub-commands for OPP/MAP/FTP**~~ – implemented in v2.7.6 (`classic-opp`, `classic-map`, `classic-ftp`).
* ~~**SPP serial port emulation**~~ – implemented in v2.7.10 via `ProfileManager1.RegisterProfile`. Debug: `cspp`; CLI: `classic-spp`.
* ~~**PAN (Personal Area Networking)**~~ – implemented in v2.7.9 via `Network1` (client) and `NetworkServer1` (server). Debug: `cpan`; CLI: `classic-pan`.

---

*Last updated: 2026-03-03 (Raw OBEX & L2CAP design docs, Basic Imaging Profile, IrMC Synchronization, SPP serial port profile, PAN networking, MAP multi-instance MAS selection, MAP MNS monitoring, metadata queries, CLI sub-commands, RFCOMM data exchange, OPP, MAP, FTP, transfer-poller dedup)*

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
| bc-20 | RFCOMM data-exchange commands (`copen`, `csend`, `crecv`, `craw`) | ✅ completed |
| bc-21 | OPP D-Bus layer + ops layer + `copp` debug command | ✅ completed |
| bc-22 | MAP D-Bus layer + ops layer + `cmap` debug command | ✅ completed |
| bc-23 | Value-parsing utility extraction (`debug_utils.py`) | ✅ completed |
| bc-24 | Future expansion documentation (FTP, SYNC, MNS, BIP, SPP, PAN) | ✅ completed |
| bc-25 | Updated `bl_classic_mode.md` with new command documentation and feature tracker | ✅ completed |
| bc-26 | Shared OBEX transfer poller `_obex_common.py` | ✅ completed |
| bc-27 | FTP D-Bus layer `obex_ftp.py` (`FtpSession`) | ✅ completed |
| bc-28 | FTP operations layer `classic_ftp.py` | ✅ completed |
| bc-29 | FTP debug command `cftp` + constants + dispatch wiring | ✅ completed |
| bc-30 | CLI `classic-opp` command (send / pull) | ✅ completed |
| bc-31 | CLI `classic-map` command (folders / list / get / push / inbox) with `--type` filter | ✅ completed |
| bc-32 | CLI `classic-ftp` command (ls / get / put / mkdir / rm) | ✅ completed |
| bc-33 | MAP MNS notification watch via `PropertiesChanged` signals | ✅ completed |
| bc-34 | `MapSession.get_supported_types()` and `list_filter_fields()` | ✅ completed |
| bc-35 | Debug `cmap monitor/types/fields` + CLI `classic-map types/fields/monitor` | ✅ completed |
| bc-36 | MAP multi-instance MAS selection (`--instance` flag, `cmap instances`, SDP discovery) | ✅ completed |
| bc-37 | PAN constants: `NETWORK_INTERFACE`, `NETWORK_SERVER_INTERFACE`, PAN UUIDs | ✅ completed |
| bc-38 | PAN D-Bus wrapper `dbuslayer/network.py` (`NetworkClient` + `NetworkServer`) | ✅ completed |
| bc-39 | PAN operations layer `classic_pan.py` + debug command `cpan` | ✅ completed |
| bc-40 | CLI `classic-pan` command (connect/disconnect/status/serve/unserve) | ✅ completed |
| bc-41 | SPP D-Bus layer `spp_profile.py` (`SppProfile` + `SppManager`) | ✅ completed |
| bc-42 | SPP debug command `cspp` (register/unregister/status) + CLI `classic-spp` | ✅ completed |
| bc-43 | Constants `PROFILE_MANAGER_INTERFACE`, `PROFILE_INTERFACE` + ops layer | ✅ completed |
| bc-44 | SYNC D-Bus layer `dbuslayer/obex_sync.py` (`SyncSession`, target `"sync"`) | ✅ completed |
| bc-45 | SYNC debug command `csync` (get/put) + CLI `classic-sync` subparser | ✅ completed |
| bc-46 | SYNC operations layer `ble_ops/classic_sync.py` + constants | ✅ completed |
| bc-47 | BIP D-Bus layer `dbuslayer/obex_bip.py` (`BipSession`, target `"bip-avrcp"`, experimental) | ✅ completed |
| bc-48 | BIP debug command `cbip` (props/get/thumb) + CLI `classic-bip` subparser | ✅ completed |
| bc-49 | BIP operations layer `ble_ops/classic_bip.py` + constants | ✅ completed |
| bc-50 | Design doc: raw OBEX framing over RFCOMM (`bleep/protocols/obex_design.md`) | ✅ completed |
| bc-51 | Design doc: L2CAP raw channel access (`bleep/protocols/l2cap_design.md`) | ✅ completed |

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
| RFCOMM data socket (`copen` / `csend` / `crecv`) | ✅ |
| Interactive RFCOMM session (`craw`) | ✅ |
| Object Push Profile (`copp send` / `copp pull`) | ✅ |
| Message Access Profile (`cmap folders\|list\|get\|push\|inbox`) | ✅ |
| BLE scan presets (shared CLI `bleep scan --variant`) | ✅ |
| OBEX FTP (`cftp ls\|cd\|get\|put\|mkdir\|rm\|cp\|mv`) | ✅ |
| SYNC profile | ✅ |
| MAP MNS notification monitoring (`cmap monitor`, `classic-map monitor`) | ✅ |
| MAP multi-instance MAS selection (`--instance`, `cmap instances`) | ✅ |
| CLI sub-commands (`classic-opp`, `classic-map`, `classic-ftp`) | ✅ |
| PAN networking (`cpan`, `classic-pan`) | ✅ |
| SPP serial port profile (`cspp`, `classic-spp`) | ✅ | | Basic Imaging Profile (`cbip`, `classic-bip`) [experimental] | ✅ |
