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
| `classic-enum <MAC>` | SDP browse + records; prints RFCOMM services table (supports `--debug` for enhanced attributes, `--connectionless` for l2ping reachability check, `--version-info` for Bluetooth version information, `--analyze` for comprehensive SDP analysis, `--sdp-source` to select/union discovery sources) |
| `classic-connect <MAC>` | Connect to a Classic device via SDP + RFCOMM (`--check` status-only, `--no-pair`, `--channel N`, `--keep` to hold the socket, `--timeout`, `--no-profiles` to skip post-connect BlueZ profile activation) |
| `classic-rfcomm <MAC> [--probe] [--bind CHANNEL]` | Enumerate RFCOMM channels via SDP; `--probe` fingerprints each channel for terminal/serial/SSH endpoints, `--bind N` binds `/dev/rfcommN` (`--device-id`) to a channel, `--timeout` per-channel probe seconds |
| `hid-info <MAC> [--connect]` | Classify a device as a Human Interface Device (keyboard/mouse/…); default is connectionless from cached discovery props, `--connect` harvests richer `Input1` evidence |
| `classic-pbap <MAC> --out <file.vcf>` | Pull full phone-book (VCF) via PBAP |
| `classic-opp <MAC> send <file>` / `pull` / `exchange <file>` | Send a file, pull a business card, or `exchange` (push local vCard then pull the remote card) via OPP |
| `classic-map <MAC> folders\|list\|get\|push\|inbox\|types\|fields\|monitor\|instances [--instance N]` | Browse, manage, and monitor SMS/MMS via MAP (use `--instance` for multi-MAS; `get <handle>` takes `--folder` e.g. `telecom/msg/inbox` so obexd can materialise the message object before download) |
| `classic-ftp <MAC> ls\|get\|put\|mkdir\|rm` | Browse and transfer files via OBEX FTP |
| `classic-pan connect\|disconnect\|status\|monitor\|server-reg\|server-unreg <MAC>` | Personal Area Networking – PAN client, event-driven `monitor`, & multi-role server (`server-reg --role nap --role gn` / `--all` / `--authorize`) |
| `network-enum [--adapter hci0] [--json] [--all-devices]` | Enumerate PAN capability across adapters (`NetworkServer1`) and devices (`Network1` / PAN UUIDs) |
| `classic-spp register\|unregister\|status [--channel N] [--auth/--no-auth]` | SPP serial port profile registration |
| `connect-profile <MAC> <UUID> [--disconnect]` | Connect/disconnect a specific Bluetooth profile by UUID |
| `classic-sync <MAC> get\|put [--location int\|sim1]` | IrMC Synchronization – download/upload phonebook |
| `classic-bip <MAC> props\|get\|thumb <handle>` | Basic Imaging Profile – image properties / download / thumbnail [experimental] |
| Raw OBEX over RFCOMM (design doc) | ✅ |
| L2CAP raw channel access (design doc) | ✅ |
| Debug Mode: `csdp <MAC> [--connectionless]` | SDP discovery without full connection (connectionless mode with l2ping reachability check) |
| Debug Mode: `pbap [options]` | Interactive PBAP phonebook dumps from connected Classic devices |
| Debug Mode: `copen` / `csend` / `crecv` / `craw` | RFCOMM data-exchange commands (open socket, send, receive, interactive session) |
| Debug Mode: `copp send <file>` / `copp pull` / `copp exchange <local.vcf> [dest.vcf]` | Object Push Profile – send files, pull business cards, or exchange (push + pull) business cards |
| Debug Mode: `cmap folders\|list\|get\|push\|download-all\|push-all\|inbox\|types\|fields\|monitor\|instances [--instance N]` | Message Access Profile – browse, manage, bulk download/upload, and monitor SMS/MMS (multi-MAS) |
| Debug Mode: `cftp ls\|cd\|get\|put\|mkdir\|rm\|cp\|mv` | File Transfer Profile – browse and transfer files |
| Debug Mode: `cpan connect\|disconnect\|status\|server-reg\|server-unreg` | Personal Area Networking (PAN) – client & server (alias: `cpan server register\|unregister`) |
| Debug Mode: `cprofiles` | List `Device1.UUIDs` with resolved names |
| Debug Mode: `cprofile connect\|disconnect <UUID>` | Connect/disconnect a specific profile by UUID |
| Debug Mode: `cspp register\|unregister\|status [--auth/--no-auth]` | SPP serial port profile – incoming connections feed `csend`/`crecv` |
| Debug Mode: `csync get\|put [--location int\|sim1]` | IrMC Synchronization – download/upload phonebook |
| Debug Mode: `cbip props\|get\|thumb <handle>` | Basic Imaging Profile [experimental] |

Adapter selection via `--adapter hciN` (default `hci0`; there is no global `--hci` flag) is available on the scanning, connection, enumeration, RFCOMM, ping, and network subcommands — `classic-scan`, `classic-enum`, `classic-connect`, `classic-ping`, `classic-rfcomm`, `network-enum`, `classic-pan monitor`, `hid-info`, and `connect-profile`. It is **not** exposed on the OBEX/profile-operation subcommands (`classic-pbap`, `classic-map`, `classic-opp`, `classic-ftp`, `classic-sync`, `classic-bip`, `classic-spp`) or on `classic-pan connect|disconnect|status`, which use the default adapter.
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

**Discovery chain.**  BLEEP tries `Device1.GetServiceRecords` (D-Bus, BlueZ
≥ 5.66) first, then plain `sdptool browse` — which follows the public browse
group and is the only single source that reliably returns *every* advertised
record with its RFCOMM channel and L2CAP PSM (verified against honeypot targets
whose extra browse-group services are dropped by `browse --xml` and truncated by
`records`).  `sdptool browse --xml` (structured) and `sdptool records`
(handle-range scan) remain as ordered fallbacks.

**UUID name resolution.**  When a record carries no SDP Service Name (attribute
`0x0100`) but does advertise a Service Class UUID, BLEEP annotates the UUID line
with a name resolved from its UUID databases via
`uuid_translator.get_uuid_name()`.  This handles the short-form UUIDs (`0x110E`,
`0x1116`, `0x112F`, …) that `sdptool` typically emits, e.g.
`UUID: 0x110E (A/V Remote Control)`.

### Vendor-Specific / Proprietary SDP Services

SDP enumeration may discover services that are **not** part of the Bluetooth SIG
assigned numbers.  These use vendor-specific 128-bit UUIDs and proprietary
protocol names.  BLEEP discovers and displays them like any other SDP record,
but it has no profile-specific logic for them — only raw RFCOMM I/O is possible.

#### BT DIAG (Samsung / LG / various OEMs)

| Field | Value |
|-------|-------|
| **SDP Service Name** | `BT DIAG` |
| **UUID** | `0x1101` (Serial Port Profile) |
| **Transport** | RFCOMM (channel varies per device) |
| **Vendor** | Samsung, LG, and other Android OEMs |
| **Purpose** | Bluetooth diagnostic / engineering-mode serial channel.  Uses the standard SPP UUID (`0x1101`) but exposes a vendor-specific AT-command or binary diagnostic interface rather than a generic serial port. |
| **BLEEP interaction** | Discoverable via `cservices` / `classic-enum`.  Raw data exchange possible via `copen <ch>` / `craw`. |

#### IcService_New (Samsung)

| Field | Value |
|-------|-------|
| **SDP Service Name** | `IcService_New` |
| **UUID** | `a23d00bc-217c-123b-9c00-fc44577136ee` |
| **Transport** | RFCOMM (channel 5 observed on SM-G891A) |
| **Profile Descriptors** | None |
| **Vendor** | Samsung Electronics |
| **Observed on** | SAMSUNG-SM-G891A (Galaxy S7 Active), Galaxy S8+, Galaxy Tab S7 FE |

**Purpose:**  Samsung-proprietary cross-device interconnect service ("IC" =
Interconnect).  Part of Samsung's device-to-device continuity framework
(Samsung Flow, SideSync, Samsung Accessory Framework) that provides a general
control/data channel between paired Samsung phones and companion devices (PCs,
tablets, watches).  Likely coordinates:
- Phone call / SMS relay to paired devices
- Audio routing coordination
- Clipboard sync and notification mirroring
- Samsung Smart Switch / Quick Share bootstrap

**Evidence:**
- Windows Device Manager creates a device node named `IcService_New` when a
  Samsung phone pairs via Bluetooth Classic.  Removal of this driver breaks
  Bluetooth audio streaming between the phone and PC
  ([Microsoft Q&A #3840559](https://learn.microsoft.com/en-us/answers/questions/3840559/accidentally-deleted-icservice-new-driver-possibly),
  [Microsoft Q&A #3284030](https://learn.microsoft.com/en-us/answers/questions/3284030/windows-was-unable-to-install-icservice-new-sms-mm)).
- Service appears alongside `SMS/MMS` (MAP) in SDP, consistent with Samsung's
  phone-to-PC integration stack.
- The `_New` suffix suggests a v2 revision of an earlier `IcService`.
- Not present in the Bluetooth SIG assigned numbers, BlueZ source, or any
  public Samsung SDK documentation.  Entirely proprietary.

**Live SDP record** (captured from SAMSUNG-SM-G891A / `E4:FA:ED:83:D8:47`):
```
Record 13:
  Name        : IcService_New
  UUID        : a23d00bc-217c-123b-9c00-fc44577136ee
  RFCOMM Ch   : 5
```

**RFCOMM probe results** (BLEEP `crfcomm --probe`):
```
  ch  5 (IcService_New): [SILENT]  (4907ms)
```

**BLEEP interaction:**
- Discovery: ✅ `cservices` / `classic-enum` correctly discovers and names the
  service via SDP attribute `0x0100` (ServiceName).
- UUID recognition: ✅ `a23d00bc-217c-123b-9c00-fc44577136ee` registered in
  `bleep/bt_ref/constants.py` as `"Samsung IcService_New"`.
- Raw RFCOMM connect: ⚠️ `copen 5` succeeds only when the phone is awake and
  unlocked.  Connection refused when phone screen is off.
- Protocol dissection: ❌ Samsung's proprietary wire protocol is undocumented.
  Only raw byte send/receive via `csend` / `crecv` / `craw` is possible.
- Dedicated commands: ❌ No `cicservice` or equivalent command suite exists.

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

**SDP source selection (`--sdp-source` flag):** selects which discovery source(s)
`classic-enum` uses. Default `auto` preserves the historical first-success chain
(D-Bus `GetServiceRecords` → `sdptool browse` → `browse --xml` → `records`).

| Value | Behaviour |
|-------|-----------|
| `auto` (default) | First source that returns records wins (unchanged behaviour) |
| `dbus` \| `browse` \| `xml` \| `records` | Force a single discovery source |
| `merge` / `all` | Query **every** source and union records (keyed by handle→uuid→name), filling missing fields, preserving all raw text, and flagging per-field disagreements |

In `merge`/`all` mode each record shows its contributing `Source` (e.g.
`browse+xml`) and any `[!] Source discrepancy on <field>` where sources disagree.
Discrepancies are also persisted (`sdp_records.source`) and surfaced by
`SDPAnalyzer` as `source_discrepancy` anomalies — useful for fingerprinting
honeypots / SDP servers that answer inconsistently.

```bash
# Union every SDP source and expose cross-source disagreements
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E --sdp-source merge --analyze
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

The debug mode (`python -m bleep debug`) includes a `csdp` command for SDP discovery on Classic devices. This command supports connectionless mode with l2ping reachability checking, matching the functionality of the CLI `classic-enum --connectionless` flag.

**Features:**
- Regular SDP discovery (no connection required)
- Connectionless mode with l2ping reachability check (faster failure detection)
- Configurable l2ping parameters
- Detailed SDP record display with all enhanced attributes
- Automatic service map generation from discovered records

**Usage:**
```bash
# Start debug mode
python -m bleep debug

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

The debug mode (`python -m bleep debug`) now includes a `pbap` command for interactive PBAP phonebook dumps from Classic devices. This provides the same functionality as the `classic-pbap` CLI command but within the debug shell environment.

**Prerequisites:**
- Classic device must be connected via `cconnect <mac>` command
- Device must support PBAP service
- `bluetooth-obexd` service must be running

**Usage:**
```bash
# Start debug mode and connect to Classic device
python -m bleep debug
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
- `--watchdog <seconds>` – Watchdog timeout before aborting stalled transfer (default: 30, 0 to disable)
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

> **Comprehensive reference**: See [MAP bMessage Format Reference](map_bmessage_format.md)
> for the full bMessage envelope specification, LENGTH calculation rules,
> nested-envelope (forwarded message) structure, bulk operation capabilities,
> supported message types, and the test message corpus.

```bash
# List message folders
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap folders

# Quick 1-message probe of all folders
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap peek

# List messages in a folder (with optional pagination)
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap list telecom/msg/inbox
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap list telecom/msg/inbox --count 10 --offset 0

# Download a specific message
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap get 12345 /tmp/msg.txt

# Push / send a message (must be in bMessage format)
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap push /tmp/outgoing.bmsg
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap push /tmp/outgoing.bmsg telecom/msg/draft

# Download all messages from every folder
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap download-all
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap download-all /tmp/dump --folders telecom/msg/inbox,telecom/msg/sent --count 50

# Push all .bmsg files in a directory
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap push-all /tmp/dump/
BLEEP-DEBUG[14:89:FD:31:8A:7E]> cmap push-all /tmp/dump/ telecom/msg/outbox --dry-run

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

#### bMessage Format (Push)

The `cmap push` command requires files in **bMessage format** — a vCard-derived
envelope with `BEGIN:BMSG`/`END:BMSG`.  Supported message types: `SMS_GSM`,
`SMS_CDMA`, `EMAIL`, `MMS`, `IM`.  The `LENGTH:` field must match the exact
byte count from `BEGIN:MSG\n` through `END:MSG\n` (inclusive); a mismatch causes
most devices to silently discard the message.  BLEEP validates this before push
and prints a warning with the correct value when mismatched.

Each `PushMessage` call sends **one bMessage file** — there is no batch upload
in the MAP spec.  To push multiple messages, use sequential
`push_message()` calls.  See
[MAP bMessage Format Reference §10](map_bmessage_format.md#10--bmessage-examples-by-type)
for inline examples of every supported type.

#### Bulk Download

All messages on a device can be downloaded by walking the folder tree, listing
messages per folder, then calling `Get` on each handle individually.  See
[MAP bMessage Format Reference §7](map_bmessage_format.md#7--bulk-operations-download-and-upload-all-messages)
for the full workflow and API usage.

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

#### Multi-Instance MAS Selection

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

### 2.10  `cftp` – File Transfer Profile (OBEX FTP)

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

### 2.11  `cpan` / `classic-pan` – Personal Area Networking

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
python -m bleep.cli classic-pan server-reg --role nap --bridge pan0
python -m bleep.cli classic-pan server-unreg --role nap

# Host several PAN roles on one bridge (repeatable --role, or --all = nap+gn+panu)
python -m bleep.cli classic-pan server-reg --role nap --role gn --bridge pan0
python -m bleep.cli classic-pan server-reg --all --bridge pan0
python -m bleep.cli classic-pan server-unreg --all
```

> **Multi-role server (v3.x).** `server-reg` registers one or more PAN roles on a
> single `NetworkServer`; the underlying wrapper tracks `{role: bridge}` and, on
> Ctrl-C **or** any error, guarantees `unregister_all()` teardown (best-effort —
> every role is attempted even if one fails). If a later role fails to register,
> the roles already registered by that call are rolled back so nothing is
> stranded. `server-unreg` accepts the same repeatable `--role` / `--all` and reports
> per-role results.

**Prerequisites:** Device must be paired and trusted.  The `Network1` interface
is available on device objects; `NetworkServer1` is on the local adapter.
A Linux bridge interface (e.g. `pan0`) may need to be created before serving.

> **Prerequisite preflight (v3.x):** `classic-pan connect` and `classic-pan server-reg`
> now run a **detect-and-instruct** preflight before acting.  It checks the host
> prerequisites BlueZ does *not* manage — the `bnep` kernel module, a powered
> adapter, and (for `server-reg`) that the `--bridge` interface exists and is a bridge
> plus whether IPv4 forwarding is enabled (advisory, for NAP internet sharing).
> The check **never mutates host networking**; it prints actionable remediation
> commands (`sudo modprobe bnep`, `sudo ip link add pan0 type bridge`, …) and then
> continues, so existing success paths are unchanged.  Pass `--no-preflight` to
> skip it.  Example:
>
> ```
> [+] PAN client prerequisites (role=nap):
>   ✓ bnep kernel module
>   ✓ Bluetooth adapter ready
>   ✓ All PAN prerequisites satisfied
> ```
>
> Opt-in bridge/NAT/DHCP auto-provisioning for NAP hosting is planned future work
> (see `docs/todo_tracker.md` → "NAP host auto-setup").

> **Connect-path correctness (v3.x):** `classic-pan connect` was hardened:
> * **Roles**: the CLI `--role` flag accepts only the short names
>   (`nap`/`panu`/`gn`, default `nap`; enforced by `argparse` `choices`).  The
>   underlying ops/D-Bus layer (`NetworkClient`) additionally normalises full
>   PAN UUIDs (e.g. `00001116-0000-1000-8000-00805F9B34FB`) to the short form
>   BlueZ expects, so programmatic callers may pass either form.
> * A **bond/SDP precheck** warns (non-fatally) when the target is not paired or
>   does not advertise a PAN service.  `--trust` additionally marks the device
>   Trusted before connecting.
> * On `NotSupported` from `Network1.Connect`, BLEEP **falls back to
>   `Device1.ConnectProfile(<pan-uuid>)`**, which drives BlueZ's SDP probe +
>   profile registration, then reads back the resulting interface.  Disable with
>   `--no-fallback`.
> * All PAN D-Bus failures now surface as mapped `BLEEPError` types (consistent
>   with the rest of BLEEP) rather than bare `RuntimeError`.

> **Event-driven connect verification (v3.x, G8).** `NetworkClient.connect()`
> confirms the BNEP session actually stabilised before returning. As of Phase 4
> this is **event-driven**: it primes a one-shot `GetAll` snapshot and then waits
> on the `Network1` `PropertiesChanged` signal for `Connected` (default 2 s), and
> **falls back** to the historical single 0.5 s poll if the signal path is
> unavailable (e.g. no GLib loop). If the session drops immediately after BlueZ
> returns, the command raises a descriptive error instead of falsely reporting
> success.
>
> The CLI `classic-pan server-reg` command blocks (via `signal.pause()`, or a GLib
> main loop when `--authorize` is set) to keep the registration alive.  Press
> **Ctrl-C** to cleanly unregister.  In debug mode, the `NetworkServer` object is
> retained on session state.

> **Networking capability boundary (what BLEEP can and cannot reach over D-Bus).**
> In BlueZ, "Bluetooth networking" is **exclusively** the PAN profile carried by
> **BNEP over L2CAP (PSM `0x000F`)** — there is no 6LoWPAN/IPSP support in the
> BlueZ tree.  As a **D-Bus client**, BLEEP can reach only the two high-level
> interfaces `bluetoothd` exports:
> * `org.bluez.Network1` (per-device client: `Connect`/`Disconnect` + `Connected`
>   / `Interface` / `UUID`), surfaced here as `classic-pan connect|disconnect|status`
>   and the device-class helpers `is_network_device()` / `get_network_roles()` /
>   `get_network_status()`.
> * `org.bluez.NetworkServer1` (per-adapter: `Register`/`Unregister`), surfaced as
>   `classic-pan server-reg|server-unreg` and `network-enum`.
>
> Everything **below** those interfaces is internal to `bluetoothd` and the Linux
> kernel and is **not reachable over D-Bus**: BNEP control messages / protocol &
> multicast **filters** (`SetupConnectionRequest`, `FilterNetTypeSet`, …), the
> `bnepX` netdev creation, and the daemon-side `network.conf` (`DisableSecurity`,
> `bnep` naming).  Host-side prerequisites BlueZ does *not* manage (the `bnep`
> module, a Linux bridge, IPv4 forwarding/NAT) are **detected and reported** by
> the preflight (Phase 1) but never mutated.  Raw BNEP framing and NAP host
> auto-provisioning are tracked as Future Work in
> `docs/todo_tracker.md`.

#### 2.11.1  `network-enum` – PAN capability discovery

Enumerates PAN capability across the whole BlueZ object tree from a single
`GetManagedObjects` snapshot — no per-device connections. It reports which
adapters expose `NetworkServer1` (PAN NAP/GN hosting) and which devices expose
`Network1` and/or advertise PAN role UUIDs (PANU/NAP/GN).

```bash
python -m bleep.cli network-enum                 # human-readable
python -m bleep.cli network-enum --json          # machine-readable
python -m bleep.cli network-enum --adapter hci0  # restrict to one adapter
python -m bleep.cli network-enum --all-devices   # include non-network devices
```

The same discovery is exposed programmatically as
`bleep.ble_ops.classic.pan.find_network_servers()` /
`find_network_devices(managed_objects=None, adapter=None, only_capable=True)` and,
per-device, via the additive device-class helpers `is_network_device()`,
`get_network_roles()`, `has_network_interface()`, and `get_network_status()` on
both the Classic and LE device wrappers (dual-mode devices carry PAN over the
BR/EDR bearer). `get_device_info()` now includes an additive `network` key
(`{roles, has_interface, status}` or `null`). The standalone helper
`bleep/scripts/check_network_capabilities.py` is a thin wrapper over these ops.

#### 2.11.2  `classic-pan monitor` – event-driven Network1 watch (E5)

Streams live `Network1` state (`Connected` / `Interface` / `UUID`) for a device
by subscribing to the `PropertiesChanged` signal — **no polling**. Each change
is printed and persisted to the observation DB; runs until Ctrl-C (or `--timeout`).

```bash
python -m bleep.cli classic-pan monitor 98:3B:8F:EF:FE:EC            # until Ctrl-C
python -m bleep.cli classic-pan monitor 98:3B:8F:EF:FE:EC --timeout 30
```

Programmatic core: `bleep.dbuslayer.network.NetworkMonitor` (pure signal-merge in
`_apply_change`; `wait_for(predicate, timeout)` and `run(timeout=…)` drive a GLib
loop) and the ops wrapper `bleep.ble_ops.classic.pan.monitor(mac, adapter, timeout,
on_change)`.

#### 2.11.3  `classic-pan server-reg --authorize` – observe inbound BNEP clients (E7)

While hosting a NAP/GN, `--authorize` registers a **default BlueZ agent** so that
each inbound BNEP client triggers `AuthorizeService` (`server.c`
`btd_request_authorization` for `BNEP_SVC_UUID`). BLEEP logs the connecting device
and service and auto-accepts; a GLib main loop is run so the agent receives the
calls, and the agent is unregistered on teardown alongside the server roles.

```bash
# Requires host prerequisites: bnep module + a bridge (pan0)
sudo modprobe bnep
sudo ip link add pan0 type bridge 2>/dev/null; sudo ip link set pan0 up
python -m bleep.cli classic-pan server-reg --role nap --bridge pan0 --authorize
```

#### 2.11.4  Scripted PAN peer harness & order of operations

`bleep/scripts/pan_peer.py` is a **standalone** (raw BlueZ D-Bus, no BLEEP import)
controllable peer for repeatable two-node testing. Run it on a **second** host or
adapter. It has three subcommands: `connect` (PANU client into a NAP), `serve`
(host a NAP so BLEEP connects as PANU), and `monitor` (cross-check the signal).

**A — BLEEP hosts NAP, peer is PANU client (exercises `server-reg --authorize`, E7):**

1. BLEEP host: `classic-pan server-reg --role nap --bridge pan0 --authorize` (after `modprobe bnep`
   and creating `pan0`).
2. Get the BLEEP host adapter MAC (`bluetoothctl show`).
3. Peer host: `sudo python3 bleep/scripts/pan_peer.py connect <BLEEP_MAC> --role panu --pair --hold`.
4. BLEEP logs `inbound BNEP client … → authorized`; peer prints its `bnepX`.
5. Ctrl-C peer (auto-disconnect), then Ctrl-C BLEEP (auto-unregister).

**B — Peer hosts NAP, BLEEP is PANU client (exercises `monitor` E5 + connect G8):**

1. Peer host: `modprobe bnep`, create `pan1`, then
   `sudo python3 bleep/scripts/pan_peer.py serve --role nap --bridge pan1`.
2. Get the peer adapter MAC.
3. BLEEP host, terminal 1: `classic-pan monitor <PEER_MAC>`; terminal 2:
   `classic-pan connect <PEER_MAC> --role panu --trust`.
4. BLEEP's monitor prints `connected=True` + interface; connect verifies via the
   `PropertiesChanged` signal (G8).

**Pairing note:** PAN needs a bond + trust on at least one side. Use `--pair` on
the peer `connect`, `--trust` on BLEEP `connect`, or pair once with `bluetoothctl`
before the first connection.

### 2.12  `cspp` / `classic-spp` – Serial Port Profile

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

### 2.13  `csync` / `classic-sync` – IrMC Synchronization

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

### 2.14  `cbip` / `classic-bip` – Basic Imaging Profile [experimental]

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

#### Handle discovery

BlueZ's experimental `Image1` interface exposes `Get`, `Properties`, and
`GetThumbnail` — but **no image-listing method**.  Handles must be obtained
through external means:

| Method | When it works |
|--------|---------------|
| **AVRCP media browsing** | If the device is an A2DP source, cover-art handles are exposed via the `bip-avrcp` OBEX target. |
| **Sequential probe** | Start from handle `0` or `1000001` and call `classic-bip props <handle>`, incrementing until the device returns an error. |
| **Cross-profile discovery** | Image attachment handles may appear in MAP message metadata or FTP directory listings. |

Run `classic-bip list` for a quick reminder of these approaches.

### 2.15  SIM Access Profile (SAP) — informational

SDP enumeration of some devices reveals `SIM Access` (UUID `0x112D`).  The
BlueZ D-Bus API (`org.bluez.SimAccess1`) for this profile is **extremely
limited**:

| Method / Property | Description |
|-------------------|-------------|
| `Disconnect()` | Terminates an existing SAP connection. |
| `Connected` (read-only) | Boolean indicating whether a SAP connection is active. |

BlueZ exposes the **server** side of SAP — it allows the local host to
*provide* SIM access to a remote client (e.g., a car kit), not to *consume*
a remote device's SIM.  Consequently BLEEP **cannot** read SIM data from a
phone that advertises SAP.

If you need SIM access you must use AT commands over an RFCOMM serial channel
(e.g., `craw` → `AT+CRSM` on devices that support it).

---

## 3  Logging

BLEEP writes per-category logs to the per-user data directory
`~/.local/share/bleep/logs/` (see `bleep/core/log.py`).  For backward
compatibility, legacy `/tmp/bti__logging__*.txt` **symlinks** point at these
real files:

| Primary file | Legacy symlink | What it contains |
|--------------|----------------|------------------|
| `general.log` | `/tmp/bti__logging__general.txt` | High-level progress lines |
| `debug.log`   | `/tmp/bti__logging__debug.txt`   | Retry loops, D-Bus method names, SDP raw output |
| `enumeration.log` | `/tmp/bti__logging__enumeration.txt` | Parsed SDP records table |
| `usermode.log`| `/tmp/bti__logging__usermode.txt`| RFCOMM connect attempts |

There is no top-level `-v` flag; set `BLEEP_LOG_LEVEL=DEBUG` (or another level)
to raise verbosity.

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
| `org.bluez.obex.Error.Failed: Unable to find service record` during PBAP | **Device-side, not a BLEEP defect.** obexd's session-time SDP ServiceSearch for the PBAP record failed even though the record *is* advertised (`classic-enum --sdp-source merge --analyze` and `sdptool search 0x112F` both find it). **Confirmed root cause on some Target Device implementations:** repeated failed OBEX attempts wedge the *device's* OBEX stack, after which it cycles through `Too short header in packet`, `Unable to find service record`, and `Timed out waiting for response` non-deterministically and never reaches the authorisation stage (so no on-device prompt appears). | **Restart the Target Device** — this clears its OBEX buffers and is the confirmed fix (validated live: PBAP dump succeeded immediately after a device restart, 313 vCard lines pulled). Depending on the device implementation a power-cycle may be required rather than a `bluetoothctl disconnect`. After restart, attend the device to accept any PBAP / Contact-Sharing prompt (some variants require per-access confirmation), then retry. |
| `OPP CreateSession failed` or `MAP CreateSession failed` | `bluetooth-obexd` not running, or device not paired/trusted | `sudo systemctl start bluetooth-obexd`; pair & trust device first |
| `MAP CreateSession failed … device not responding` / `Timed out waiting for response` | **MAS access not authorised** on the target (screen locked/asleep, or message-sharing disabled for this pairing). Reaching the auth stage requires an awake device. | **Wake/unlock the target**, enable Bluetooth **message/SMS sharing** for the pairing, and **accept the Message-Access prompt**, then retry. BLEEP now surfaces this as a Convention-aligned `BLEEPError` with these steps inline. |
| `[!] MAP (0x1132/0x1134) not advertised by <MAC> in SDP – attempting anyway` | The target does **not** expose a MAS instance in SDP (e.g. feature phones / honeypots). Non-fatal pre-flight warning. | Confirm the device supports MAP; run `classic-map <MAC> instances` to list MAS channels. If none, MAP is unavailable on that target — not a BLEEP defect. |
| `[!] OPP (0x1105) not advertised …` / `[!] OBEX-FTP (0x1106) not advertised … – attempting anyway` | Non-fatal SDP pre-flight for `classic-opp` / `classic-ftp`: the profile UUID was not found in the target's service map (mirrors the interactive `detect_*_service` guard). | Confirm the device advertises the profile via `classic-enum <MAC>`. Most phones expose OPP but **not** FTP/SYNC/BIP. If absent the command still attempts, then fails cleanly at CreateSession. |
| `OBEX CreateSession failed: <PROFILE> service record not retrievable at session time` (OPP/FTP/SYNC/BIP) | Either the profile is **not advertised** by the target (common for FTP `0x1106`, SYNC `0x1104`, BIP `0x111A/B` on modern phones) or an advertised record transiently failed obexd's session-time SDP lookup. | Verify support with `classic-enum <MAC>`. If genuinely absent, the profile is unavailable on that target — not a BLEEP defect. If advertised, accept any on-device prompt and retry, or `bluetoothctl disconnect <MAC>` and reconnect. |
| `Operation not supported: BIP Image1 interface (obexd must run with --experimental)` | BIP's `Image1` D-Bus interface is `[experimental]` in BlueZ and is unavailable unless obexd is launched with `--experimental`. | Start obexd with the experimental flag (e.g. `bluetooth-obexd -n -d --experimental`) and retry `classic-bip`. Note that few devices advertise BIP at all. |
| OPP pull / FTP get / MAP get succeeds but file is empty or remote shows "failure in sending" | **obexd AppArmor confinement** — on Ubuntu, `obexd` runs under AppArmor and may only write to permitted paths (e.g. `~/.cache/obexd/`). If the destination is outside the permitted area, the transfer silently fails. | BLEEP uses a two-stage approach: obexd writes to `~/.cache/obexd/` (staging), then BLEEP moves the file to the final directory (`/tmp/bleep_received/` by default). Override the final directory with `--save-dir` or `BLEEP_RECEIVE_DIR` env var. |
| `OPP transfer timed out` / `MAP transfer timed out` | Remote device did not complete OBEX transfer in time | Increase timeout, restart remote device, check logs |
| `csend` / `crecv` → `Send failed` / `Receive failed` | RFCOMM socket disconnected or channel mismatch | Re-open with `copen`; verify channel with `cservices` |
| `br-connection-profile-unavailable` on `gatt-enum` / `media-enum` for dual-mode audio devices | Host system lacks Bluetooth audio profile handlers (no PulseAudio/PipeWire/BlueALSA) — BlueZ `Device1.Connect()` requires a local handler for at least one remote profile | Install `bluez-alsa-utils` (`sudo apt-get install bluez-alsa-utils`) or ensure an audio server with Bluetooth support is running.  Run `bleep --check-env` to verify.  Confirmed fix on OnePlus 6T and Samsung S7 Active. |
| `br-connection-create-socket` during `classic-enum` / `classic-rfcomm` (F6) | **Non-fatal, environmental.** The initial `Device1.Connect()` attempt failed to open the BR/EDR socket (device busy, half-open link, or auto-connect from a paired host racing the CLI). This is the same class as `br-connection-busy`. | **No action required** — SDP enumeration proceeds connectionlessly and completes normally. If a *connection-based* profile op (PBAP/MAP/etc.) is needed, `bluetoothctl disconnect <MAC>`, wait 2–3 s, and retry. |
| `db show` / `db list` reports `Address Type: public` for a device whose LE address is structurally random (e.g. `47:xx…` with the two MSBs set) (F7) | **Not a bug — faithful echo.** BLEEP reports `org.bluez.Device1.AddressType` exactly as BlueZ exposes it. BlueZ may label an address `public` even when the bits indicate a (resolvable/non-resolvable) private/random address, depending on how the controller/kernel populated the property. | Informational only. Treat the address *structure* (top two bits) as the authoritative RPA indicator; the reported `AddressType` string reflects BlueZ's view, not BLEEP's classification. |

---

## 5  Limitations / roadmap

### Implemented
* **PBAP** – phone-book dump via BlueZ obexd (CLI and debug mode).
* **OPP** – file send and business-card pull via BlueZ obexd (debug mode `copp`).
* **MAP** – folder browse, message list/get/push, bulk download-all/push-all, inbox update, read/delete flags, multi-instance MAS selection (debug mode `cmap`).
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

*Last updated: 2026-09-13 (v3.0.0 doc-fidelity pass: scoped the `--adapter` availability statement to the subcommands that actually accept it; corrected the debug `cpan` verb summary to `server-reg`/`server-unreg`; added `classic-connect`, `classic-rfcomm`, `hid-info`, and `classic-opp exchange` to the command table; renumbered the profile sections to remove duplicate §2.8/§2.9 headings — OPP stays §2.8 and MAP stays §2.9, while `cftp`→§2.10, `cpan`→§2.11, `cspp`→§2.12, `csync`→§2.13, `cbip`→§2.14, SAP→§2.15 (active cross-refs in `network_capability_summary.md`, `pan_connection_analysis.md`, and `archive/network_capability_plan.md` updated accordingly; historical `changelog.md`/`todo_tracker.md` entries retain their original numbering). Earlier (2026-07-23): corrected completed-tracker module paths to the nested `bleep/ble_ops/classic/` layout; MAP handle fix, PBAP watchdog 30 s, BIP handle discovery docs, SAP docs)*

---

> **Note.** The former §6 "Temporary Classic-Feature TODO Tracker" and §7
> "Feature Tracker" (all items ✅ complete) were removed on 2026-07-23 per their
> own removal note. The completed-task record is preserved in
> [`todo_tracker.md`](todo_tracker.md) (Classic foundational tasks bc-01…bc-11
> plus the bc-14…bc-54 feature set) and the per-version rollout history is in
> [`changelog.md`](changelog.md).
