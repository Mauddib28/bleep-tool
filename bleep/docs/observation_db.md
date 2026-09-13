# Observation database

BLEEP maintains a local SQLite database (`~/.bleep/observations.db`) that automatically stores information gathered during scans and interactions.

## What is stored?

| Table | Contents |
|-------|----------|
| `devices` | Basic device information (MAC, name, RSSI, first/last seen…) |
| `adv_reports` | Raw advertising reports with decoded fields |
| `services` / `characteristics` / `descriptors` | GATT hierarchy discovered during enumeration |
| `char_history` | Every value read from a characteristic (timestamped) |
| `media_players` / `media_transports` | AVRCP & A2DP state snapshots |
| `classic_services` | RFCOMM-based service → channel mapping (SDP) |
| `sdp_records` | Full SDP record snapshots with all attributes (Service Record Handle, Profile Descriptors, Service Version, etc.) |
| `pbap_metadata` | Phone-book repository metadata (entries, hash) |
| `aoi_analysis` | Assets-of-Interest analysis results (security concerns, unusual characteristics) — latest per device |
| `aoi_analysis_history` | Append-only history of every AoI analysis over time (Schema v17) |
| `device_type_evidence` | Device type classification evidence for audit/debugging (Schema v6) |
| `pairing_events` | Full pairing-workflow log, one row per pairing attempt (Schema v12) |
| `security_maps` | Per-enumeration landmine/permission maps and annotations (Schema v12) |
| `media_enumerations` | Full media-subsystem enumeration snapshots (players/transports/endpoints/browse tree) (Schema v12) |
| `audio_recon` | Host-level audio recon snapshots (cards, PCMs, recordings) — not device-scoped (Schema v12) |

## Automatic logging

* `scan`, `connect`, `gatt-enum` and related helpers insert devices, services and characteristics.
* `explore` and `enum-scan` commands save discovered services and characteristics to the database, including GATT hierarchy.
* `classic-enum`, `csdp` (debug mode), and SDP discovery functions automatically store full SDP record snapshots in `sdp_records` table.
* `multi_read_all` logs characteristic values into `char_history` with no extra flags.
* Media helpers snapshot players/transports whenever they are encountered.

## Counter & history semantics

A few stored fields are **change-logs or aggregates**, not raw per-observation
records.  Reading them as an event timeline will mislead — keep these in mind:

* **`adv_reports` is a change-log, not a per-round timeline.**  `insert_adv()`
  coalesces consecutive identical samples: a new row is written only when the
  `(data, decoded, adapter)` triple differs from the most recent row for that
  MAC **on that antenna**.  BlueZ's
  `GetManagedObjects()` re-reports the same advert every survey round, so without
  this the table floods with duplicates.  Two consequences:
  * **RSSI-only variation is intentionally not persisted here.**  RSSI is excluded
    from the dedup key, and per-round RSSI aggregates live on the `devices` row
    (`rssi_min`/`rssi_max`/`rssi_last`).  A steady-state advertiser therefore adds
    **no** new `adv_reports` rows across a run even though it is seen every round,
    so the newest `adv_reports.ts` can lag `devices.last_seen` by hours/days.  Use
    `devices.last_seen` (not `adv_reports`) to answer "when was it last seen".
  * Structurally-identical `decoded` payloads coalesce regardless of JSON key
    order; a genuine `A → B → A` payload rotation still produces three distinct
    rows (dedup is *consecutive*-only).
* **`devices.sighting_count` reflects the most recent `survey` run's census — it is
  *replaced* per run, not accumulated across runs.**  Each `survey` run overwrites the
  column with that run's census tally via
  `ON CONFLICT(mac) DO UPDATE SET sighting_count=excluded.sighting_count`
  (`bleep/core/observations/_devices.py`), and the write is gated so it only fires when the
  run's census count is `> 0` (`bleep/modes/survey.py`).  Consequently a device **not** seen
  this round (census `0`) keeps its previous stored value rather than being reset to `0`, but
  a device that *is* seen has its count overwritten by the current run's tally — the column is
  **not** a running total.  A single `survey` run's JSON `sightings` field mirrors that same
  run's census.  Cached re-reads of **paired/bonded** devices that did not advertise this
  round (no fresh RSSI) contribute `0` and therefore do **not** touch the stored value —
  unpaired advertisers with a transiently-missing RSSI still count (see the survey
  `--exclude-cached` / sighting-count semantics in [survey_mode.md](survey_mode.md)).

## CLI access

```
python -m bleep.cli db list --fields mac,name,last_seen
python -m bleep.cli db list --since 2026-08-06 --until 2026-08-09   # date window
python -m bleep.cli db show AA:BB:CC:DD:EE:FF
python -m bleep.cli db report --since 2026-08-06 --until 2026-08-09  # batch report
python -m bleep.cli db report --since 2026-08-06 --until 2026-08-09 --all-in-window --recon  # + recon analytics
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF     # char_history view
python -m bleep.cli db export AA:BB:... --out dump.json
python -m bleep.cli db export AA:BB:... --out dump.json --max-history 0  # full history
python -m bleep.cli db uuids                          # observed-UUID catalogue
python -m bleep.cli db uuids --uuid 0xFE95            # one UUID, all sightings
python -m bleep.cli db uuids --uuid <UUID> --promote "Vendor Service"  # promote to custom names
python -m bleep.cli db maintain                       # VACUUM + ANALYZE + row-count/size stats
```

## File location

Set `BLEEP_DB_PATH=/custom/path.db` to override the default.

## Schema Versioning

The database schema is versioned to allow for smooth migrations:

| Version | Changes |
|---------|---------|
| v1 | Initial schema with basic tables |
| v2 | Renamed columns to avoid Python keyword conflicts (`class` → `device_class`, `state` → `transport_state`) |
| v3 | Added `device_type` field for improved device type classification |
| v4 | Added `aoi_analysis` table for Assets-of-Interest integration |
| v5 | Added performance indexes for frequently queried fields |
| v6 | Added `device_type_evidence` table for classification audit trail and signature caching |
| v7 | Added `sdp_records` table for full SDP record snapshots with all attributes |
| v8 | **MAC address normalisation** — All MAC addresses in every table normalised to uppercase via one-time migration.  `_normalize_mac()` helper enforces uppercase on all write paths. |
| v9 | **UUID normalisation** — All UUIDs in `services`, `characteristics`, `classic_services`, `sdp_records`, and `char_history` normalised to uppercase via one-time migration.  `_normalize_uuid()` helper enforces uppercase on all write paths. |
| v10 | **Data fidelity enrichment** — Added `descriptors` table.  New device columns: `tx_power`, `modalias`, `icon`, `service_data`, `advertising_data`.  New service columns: `is_primary`, `includes`.  New characteristic column: `mtu`.  New APIs: `get_characteristic_id()`, `upsert_descriptors()`.  All CLI commands now persist full v10 metadata.  `_persist_mapping` handles descriptors, `is_primary`/`includes`, and `mtu` end-to-end. |
| v11 | **AoI augmentation** — `aoi_analysis`: added `pairing_profile`, `sdp_summary`, `post_pair_delta` (JSON) columns. |
| v12 | **Phase 2 persistence gap closure** — New tables `pairing_events`, `security_maps`, `media_enumerations`, `audio_recon`.  New `devices` columns: `uuids`, `paired`, `trusted`, `bonded`, `sighting_count`, `fingerprint_changed`.  New `sdp_records` columns: `mas_instance_id`, `supported_message_types`, `supported_features`. |
| v13 | **AoI analysis details** — `aoi_analysis`: added `analysis_details` (JSON) column. |
| v14 | **Remote Bluetooth version detection** — `devices`: added `lmp_version`, `lmp_subversion`, `bt_manufacturer`, `bt_spec_version`, `lmp_features`, `version_queried_at`. |
| v15 | **DIS version columns** — `devices`: added `firmware_revision`, `software_revision`, `model_number`, `dis_manufacturer_name`, `pnp_vendor_source`, `pnp_vendor_id`, `pnp_product_id`, `pnp_product_version`. |
| v16 | **`sdp_records` append-only / versioned** — Dropped `UNIQUE(mac, service_record_handle)` (table rebuilt, all rows preserved); added non-unique index `idx_sdp_records_mac_handle`.  `upsert_sdp_record()` appends a new snapshot only when service content changes. |
| v17 | **AoI analysis history** — Added append-only `aoi_analysis_history` table (+ indexes).  `store_aoi_analysis()` writes latest-only to `aoi_analysis` and appends a timestamped row to `aoi_analysis_history`. |
| v18 | **`sdp_records.source` provenance** — Added a `source` TEXT column (`"dbus"`/`"browse"`/`"xml"`/`"records"`/merged `"a+b"`); excluded from change-detection. |
| v19 | **Multi-antenna provenance** — `devices`: added `seen_by` (JSON), `enumerated_by` (TEXT); `adv_reports`: added `adapter` (TEXT). |
| v20 | **Enumerator recency** — `devices`: added `enumerated_at` (DATETIME, last successful GATT); used with survey `--enum-cooldown`. |

The database schema is currently at **version 20** (v20 added `devices.enumerated_at` for last-successful GATT recency; v19 added `devices.seen_by` / `devices.enumerated_by` and `adv_reports.adapter` for multi-antenna provenance; survey writes `enumerated_by`/`enumerated_at` only after a successful GATT enumeration. v18 added the `sdp_records.source` provenance column — excluded from change-detection; v17 made `aoi_analysis_history` append-only while `aoi_analysis` remains latest-only; v16 made `sdp_records` append-only/versioned — dropped `UNIQUE(mac, service_record_handle)`, snapshots appended only on content change).  Migrations occur transparently when the schema version changes. For detailed migration history, see the schema version table in [observation_db_schema.md](observation_db_schema.md).

### Data Integrity (FK Defense Chain)

The database persistence layer includes a self-healing foreign-key defense chain:

- `_ensure_device_exists(cur, mac)` — Performs `INSERT OR IGNORE` to guarantee the parent `devices` row exists before any child-table insert.  Integrated into 8 child-table methods.
- `_ensure_service_exists(cur, mac, service_uuid)` — Performs `INSERT OR IGNORE` to guarantee the parent `services` row exists before any `characteristics` insert.
- `upsert_characteristics()` accepts optional `mac` and `service_uuid` kwargs; when supplied, both helpers are called internally, making characteristic inserts self-healing against missing parent rows.

## AOI Integration

The database now integrates with the Assets-of-Interest (AoI) module, allowing for:

1. **Unified Storage**: AoI analysis results are stored in the `aoi_analysis` table while maintaining backward compatibility with the file-based system
2. **Bidirectional Synchronization**: Data can flow between the database and AoI JSON files
3. **Enhanced Querying**: Use SQL queries to find devices with specific security characteristics or issues

### CLI Commands for AoI-Database Integration

```bash
# Import AoI data from files to database
python -m bleep.cli aoi db import [--address MAC]

# Export AoI data from database to files
python -m bleep.cli aoi db export [--address MAC]

# Synchronize database and files (bidirectional). Always syncs ALL devices —
# --address is ignored for sync (unlike import/export, which honor it).
python -m bleep.cli aoi db sync

# Use database for storage when scanning
python -m bleep.cli aoi scan targets.json --db-only

# Disable database for a specific operation
python -m bleep.cli aoi analyze --address 00:11:22:33:44:55 --no-db
```

### Programmatic Access

The observation database can be accessed programmatically through the `bleep.core.observations` module. Here are comprehensive examples:

#### Basic Device Queries

```python
from bleep.core.observations import get_devices, get_device_detail

# List all devices
all_devices = get_devices()

# List devices with filtering
ble_devices = get_devices(status='ble')  # BLE devices (including dual-mode)
classic_devices = get_devices(status='classic')  # Classic devices (including dual-mode)
dual_devices = get_devices(status='dual')  # Dual-mode devices only
recent_devices = get_devices(status='recent')  # Seen in last 24 hours
media_devices = get_devices(status='media')  # Devices with media capabilities

# Pagination support
first_page = get_devices(limit=50, offset=0)
second_page = get_devices(limit=50, offset=50)

# Combined filters
recent_ble = get_devices(status='recent,ble', limit=20)

# Collection-date window (DB-1). Bounds are naive-UTC ISO strings; `until` is
# exclusive. `seen_basis` ∈ {'last' (default), 'first', 'any'} selects which
# timestamp the window applies to ('any' = observation span overlaps the window).
from bleep.core.time_utils import local_date_range_to_utc
since, until = local_date_range_to_utc('2026-08-06', '2026-08-09', tz='UTC')
window = get_devices(since=since, until=until, seen_basis='last', limit=10000)
```

#### Device Detail Retrieval

```python
from bleep.core.observations import get_device_detail, export_device_data

# Get complete device information
mac = "00:11:22:33:44:55"
device_info = get_device_detail(mac)

# Access device data
device = device_info['device']  # Device record
services = device_info['services']  # GATT services
characteristics = device_info['characteristics']  # GATT characteristics
classic_services = device_info['classic_services']  # Classic service mappings
sdp_records = device_info['sdp_records']  # Full SDP record snapshots
pbap_metadata = device_info['pbap_metadata']  # PBAP repository metadata
media_players = device_info['media_players']  # AVRCP player snapshots
media_transports = device_info['media_transports']  # A2DP transport snapshots

# Export complete device data for offline analysis
device_data = export_device_data(mac)
# Returns JSON-serializable dictionary with all device data
# BLOBs are automatically converted to hex strings
```

#### Characteristic History

```python
from bleep.core.observations import get_characteristic_timeline

# Get timeline for a specific characteristic
timeline = get_characteristic_timeline(
    mac="00:11:22:33:44:55",
    service_uuid="1800",
    char_uuid="2a00",
    limit=100
)

# Get all characteristic history for a device
all_history = get_characteristic_timeline(
    mac="00:11:22:33:44:55",
    limit=500
)

# Scope to a specific service/characteristic
scoped = get_characteristic_timeline(
    mac="00:11:22:33:44:55",
    service_uuid="1800",
    char_uuid="2a00",
    limit=100
)
# Note: there is no `source` filter parameter; filter on the returned rows'
# `source` field (e.g. [r for r in scoped if r["source"] == "read"]) instead.
```

#### Device Type Evidence

```python
from bleep.core.observations import (
    get_device_type_evidence,
    get_device_evidence_signature
)

# Get all evidence for a device
evidence = get_device_type_evidence("00:11:22:33:44:55")

# Get evidence signature for caching
signature = get_device_evidence_signature("00:11:22:33:44:55")
# Returns dictionary with signature components or None
```

#### Assets-of-Interest (AoI) Analysis

```python
from bleep.core.observations import (
    get_aoi_analysis,
    get_aoi_analysis_history,
    store_aoi_analysis,
    has_aoi_analysis,
    get_aoi_analyzed_devices
)

# Check if device has analysis
if has_aoi_analysis("00:11:22:33:44:55"):
    # Get analysis results. The concern lists are nested under 'summary'
    # (see _aoi._row_to_analysis); 'timestamp' is top-level, and
    # 'pairing_profile'/'sdp_summary'/'post_pair_delta'/'details' appear
    # top-level only when present.
    analysis = get_aoi_analysis("00:11:22:33:44:55")
    summary = analysis.get('summary', {})
    security_concerns = summary.get('security_concerns', [])
    recommendations = summary.get('recommendations', [])

# Store analysis results. The concern lists MUST be nested under 'summary'
# (store_aoi_analysis reads analysis["summary"][...]); a top-level timestamp is
# ignored (the row timestamp is always set to utc_now_iso() by the writer).
# 'pairing_profile'/'sdp_summary'/'post_pair_delta'/'details' are optional
# top-level keys persisted only when present.
analysis_data = {
    'summary': {
        'security_concerns': [...],
        'unusual_characteristics': [...],
        'notable_services': [...],
        'recommendations': [...],
    },
    # optional top-level v11+ fields:
    'pairing_profile': {...},
    'sdp_summary': {...},
    'post_pair_delta': {...},
    'details': {...},
}
store_aoi_analysis("00:11:22:33:44:55", analysis_data)

# Get all devices with AoI analysis
analyzed_devices = get_aoi_analyzed_devices()
```

#### Data Storage Functions

```python
from bleep.core.observations import (
    upsert_device,
    insert_adv,
    upsert_services,
    upsert_characteristics,
    upsert_classic_services,
    upsert_sdp_record,
    upsert_pbap_metadata,
    insert_char_history
)

# Store/update device information
upsert_device(
    mac="00:11:22:33:44:55",
    name="My Device",
    device_type="le",
    rssi_last=-65
)

# Store advertising report
insert_adv(
    mac="00:11:22:33:44:55",
    rssi=-70,
    data=b'\x02\x01\x06...',  # Raw advertising data
    decoded={'flags': 6, 'services': ['1800']},  # Decoded structure
    adapter="hci0",  # optional; same payload on a different antenna is a new row
)

# Store GATT services
upsert_services(
    mac="00:11:22:33:44:55",
    services=[
        {
            'uuid': '1800',
            'handle_start': 1,
            'handle_end': 7,
            'name': 'Generic Access'
        }
    ]
)

# Store characteristics (with FK-defense kwargs)
upsert_characteristics(
    service_id=1,
    char_list=[
        {
            'uuid': '2a00',
            'handle': 3,
            'properties': ['read'],
            'value': b'Device Name'
        }
    ],
    mac="00:11:22:33:44:55",        # FK defense: ensures device row exists
    service_uuid="1800",             # FK defense: ensures service row exists
)

# Store Classic service mapping
upsert_classic_services(
    mac="00:11:22:33:44:55",
    services=[
        {
            'uuid': '0x110e',
            'channel': 1,
            'name': 'Headset'
        }
    ]
)

# Store full SDP record snapshot
upsert_sdp_record(
    mac="00:11:22:33:44:55",
    record={
        'handle': 0x10001,
        'uuid': '0x110e',
        'channel': 1,
        'name': 'Headset',
        'profile_descriptors': [{'uuid': '0x110e', 'version': 256}],
        'service_version': 1,
        'description': 'Headset Profile',
        'raw': '<?xml version="1.0"?>...'
    }
)

# Store PBAP metadata
upsert_pbap_metadata(
    mac="00:11:22:33:44:55",
    repo="PB",
    entries=150,
    vcf_hash="a1b2c3d4e5f6..."
)

# Store characteristic value history
insert_char_history(
    mac="00:11:22:33:44:55",
    service_uuid="1800",
    char_uuid="2a00",
    value=b"Device Name",
    source="read"
)
```

#### Integration with Scanning Operations

```python
from bleep.core.observations import upsert_device
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter

# Scan and automatically store devices
adapter = system_dbus__bluez_adapter("hci0")
devices = adapter.get_discovered_devices()

# Devices are automatically stored during scanning
# You can also manually update device information
for device in devices:
    upsert_device(
        mac=device.mac_address,
        name=device.name,
        rssi_last=device.rssi,
        device_type=device.device_type
    )
```

#### Error Handling

```python
from bleep.core.observations import get_device_detail

try:
    device_info = get_device_detail("00:11:22:33:44:55")
    if device_info['device'] is None:
        print("Device not found in database")
    else:
        print(f"Device: {device_info['device']['name']}")
except Exception as e:
    print(f"Error accessing database: {e}")
    # Database operations are designed to fail gracefully
    # BLEEP never crashes if database is unavailable
```

## Device Type Classification

BLEEP uses an **evidence-based, stateless classification system** (Schema v6). Classification decisions are based **only** on current device properties and active queries, never on historical database data. This prevents false positives from MAC address collisions. The database schema is currently at **version 20** (see [Schema Versioning](#schema-versioning) section above).

| Device Type | Description | Detection Criteria |
|-------------|-------------|-------------------|
| `unknown` | Unable to determine device type | Insufficient evidence available |
| `classic` | BR/EDR (Classic Bluetooth) only | Requires conclusive Classic evidence (device_class OR SDP records) |
| `le` | Bluetooth Low Energy only | Requires conclusive LE evidence (random address OR GATT services) |
| `dual` | Dual-mode device (both Classic and BLE) | **Strict requirement**: Conclusive evidence from BOTH protocols |

### Evidence-Based Detection

**Classic Evidence (Conclusive):**
- `device_class` property present (Classic device class code)
- SDP records discovered via `GetServiceRecords()` or connectionless SDP queries

**LE Evidence (Conclusive):**
- `AddressType` = "random" (LE random addresses are conclusive)
- GATT services resolved via `services_resolved()`

**Important Notes:**
- `AddressType` = "public" is **inconclusive** (default for both Classic and LE)
- Dual-mode detection requires **conclusive evidence from BOTH** protocols
- Database history is **NOT** used for classification (stateless system)
- Evidence is stored in `device_type_evidence` table for audit/debugging only

### Mode-Aware Collection

Evidence collection adapts to scan mode aggressiveness:

- **Passive Mode**: Only advertising data (device_class, UUIDs, address_type)
- **Naggy Mode**: Passive + connection-based (GATT services if connected)
- **Pokey/Bruteforce Modes**: All collectors enabled (including SDP queries)

For detailed information, see [Device Type Classification Guide](device_type_classification.md).

## Database CLI Filters

The `db list` command supports filtering devices by status:

```bash
# List only Classic Bluetooth devices (including dual-mode devices)
python -m bleep.cli db list --status classic

# List only BLE devices (including dual-mode devices)
python -m bleep.cli db list --status ble

# Show specific fields including first_seen and last_seen timestamps
python -m bleep.cli db list --fields mac,name,first_seen,last_seen

# List only dual-mode devices (supporting both Classic and BLE)
python -m bleep.cli db list --status dual

# List only devices with unknown classification
python -m bleep.cli db list --status unknown

# List only devices with media capabilities
python -m bleep.cli db list --status media

# List recently seen devices (last 24 hours)
python -m bleep.cli db list --status recent

# Combine multiple filters with commas
python -m bleep.cli db list --status recent,ble

# Filter by device name (case-insensitive substring). Useful for enumerating every
# RPA identity of one named device (e.g. a rotating-address host) without merging.
python -m bleep.cli db list --name DESKTOP-1APRSIB

# Paginate; when a page is exactly full, a truncation notice hints at --limit/--offset
python -m bleep.cli db list --limit 50 --offset 50
```

> **Note:** `-d/--device` filtering is client-side only and applies to `scan`, not `db list`.
> For `db list`, use `--status`, `--name`, `--fields`, and `--limit/--offset`.

### Collection-date windows, batch reports, target lists & identity collapse (DB-1…DB-6)

`db list` and `db report` accept an arbitrary **collection-date window** (not just
the fixed `--status recent` 24-hour filter):

```bash
# Devices collected 6–9 Aug 2026 (inclusive of the whole 9th).
python -m bleep.cli db list --since 2026-08-06 --until 2026-08-09

# Choose which timestamp the window applies to:
#   last (default, indexed) | first | any (observation span overlaps the window)
python -m bleep.cli db list --since 2026-08-06 --until 2026-08-09 --seen-basis any

# Dates are interpreted in --tz (default UTC, matching stored naive-UTC timestamps).
python -m bleep.cli db list --since 2026-08-06 --until 2026-08-09 --tz America/New_York
```

**Window semantics.** Timestamps are stored as naive-UTC ISO strings (see
[Counter & history semantics](#counter--history-semantics)); the window compares
lexicographically. `--until` is **inclusive of the whole day** — internally the
upper bound is the following midnight (exclusive). `--seen-basis`:

| basis | predicate | meaning |
|-------|-----------|---------|
| `last` (default) | `last_seen ∈ [since, until)` | last observed in the window (uses `idx_devices_last_seen`) |
| `first` | `first_seen ∈ [since, until)` | first discovered in the window (full scan) |
| `any` | `first_seen < until AND last_seen ≥ since` | observation span overlaps the window |

**Target lists (`--export-targets`).** Write the current (windowed/filtered)
selection as a survey/AoI-ingestable JSON list of `{address,name,device_type,
first_seen,last_seen}` objects — the `address` key is what `aoi` consumes:

```bash
python -m bleep.cli db list --since 2026-08-06 --until 2026-08-09 --status ble \
    --export-targets targets.json
python -m bleep.cli aoi scan targets.json --analyze
```

**Batch report (`db report`).** Generate one aggregate security report over the
windowed/filtered device set. It **delegates to the AoI report engine**, so
advert-only (never-enumerated) devices are not dropped — they appear in a
"Not Reachable (no GATT/SDP enumerated)" section, while enumerated devices get
scored per-device. A dense passive window can match tens of thousands of RPA rows,
so output is **capped at `--limit` (default 500)** unless `--all-in-window` is
given; narrow with `--status`/`--name` instead of dumping everything.

```bash
# Markdown report saved under ~/.bleep/aoi/reports/ (or --out PATH).
python -m bleep.cli db report --since 2026-08-06 --until 2026-08-09 --status ble

# JSON report to stdout for downstream tooling.
python -m bleep.cli db report --since 2026-08-06 --until 2026-08-09 --format json --json
```

**Heuristic identity / RPA collapse (`--group-identity`, `--identity-contrast`).**
BLE privacy rotates Resolvable Private Addresses (RPAs), so one physical device
appears as many `devices` rows. True resolution needs the device's IRK (only
available after bonding) which BLEEP does **not** store, so collapse is **heuristic
only** and **off by default** — the raw, non-collapsed view is authoritative and is
always available for comparison. Strategies: `name` (default), `name_mfr`
(name + manufacturer id), `payload` (manufacturer/service/UUID/protocol signature,
via `adv_dissect`). Every collapsed output prints its provenance
(`raw N → collapsed M, strategy=…, heuristic, no IRK`) so a cluster is never
mistaken for a cryptographically resolved identity. On dense real-world data the
delta is often small (address rotation co-occurs with payload rotation) — that
delta is itself the analytical signal.

```bash
# Collapsed identity view for a window (list).
python -m bleep.cli db list --since 2026-08-06 --until 2026-08-09 --group-identity

# Report showing BOTH raw and collapsed counts for compare/contrast.
python -m bleep.cli db report --since 2026-08-06 --until 2026-08-09 --identity-contrast
```

### Name audit (`--name-audit`, DB-8)

Most `devices` rows carry BlueZ's **default alias** as their name — the device's own
MAC with `-` separators (e.g. `25-B4-9B-B7-AA-A8`), which is just a "variation of the
MAC" and not a real identifier. `--name-audit` (on both `db list` and `db report`)
classifies every name in the windowed/filtered selection into four buckets via
`bleep.analysis.identity.classify_name` (comparison normalises `:`/`-`/`_` and case):

| Bucket | Definition | Detail emitted |
|--------|------------|----------------|
| `placeholder` | MAC-shaped **and** normalises to the device's **own** MAC (default alias) | count + a sample of `--name-sample` rows (default 10) |
| `real` | a genuine, non-MAC name | count + **full collected record** per device (see below), grouped by name |
| `empty` | NULL / blank | count + full per-device detail |
| `foreign_mac` | MAC-shaped **but** normalises to a MAC **≠** own address | count + full per-device detail — **anomaly, always surfaced** |

The `foreign_mac` bucket answers the specific concern: a name that *looks* like a MAC
but is **not** the device's own address (possible spoofing/mislabelling) is raised as an
explicit `[!] ANOMALY` warning on the terminal (and listed under `name_audit.foreign_mac`
in JSON / the report's **Anomalies** section) regardless of how many are found.

For **real** (interesting) names, each group carries a compact `summary` (advertisement
vendors/protocols, GATT/SDP/classic surface counts, exposed SDP profile names — reusing
the same `adv_dissection` `db show` surfaces) **and**, for the first `--name-detail-limit`
names (default 50; `0` = all), the **complete collected record per member device** via the
DB-5 uncapped `export_device_data` (device row, services, characteristics, SDP, all
advertisement reports, full characteristic history, AoI analysis, type evidence).

```bash
# Human table + full per-device dumps for real-named devices in the window.
python -m bleep.cli db list --since 2026-08-06 --until 2026-08-10 --seen-basis any --name-audit

# Machine-readable audit (counts, anomalies, real[].summary + real[].devices full records).
python -m bleep.cli --json db list --since 2026-08-06 --until 2026-08-10 --seen-basis any \
    --name-audit --name-detail-limit 0 > name_audit.json

# Append a "## Name Audit" section (buckets + anomalies + real-name summaries) to a report.
python -m bleep.cli db report --since 2026-08-06 --until 2026-08-10 --seen-basis any \
    --status classic --all-in-window --name-audit --out report.md
```

This is a read-only classification of the already-selected rows — it issues no extra
query for bucketing and reuses `collapse`-style name grouping, so it composes with every
window/status/name filter above.

### Reconnaissance Analytics (`--recon`, DB-9)

`db report --recon` appends a top-level `## Reconnaissance Analytics` section that
aggregates three views over the report's windowed/filtered selection. It is
opt-in, read-only, and additive (a JSON `recon` sibling block, or a markdown/text
section appended to the report body). `--recon` is a single umbrella flag layered
over modular per-analytic builders, so granular flags can be added later without
refactoring.

1. **SDP inventory** — every unique `(name, uuid)` SDP service item across the
   selection with a distinct-device count, sorted by prevalence. Backed by a single
   batched `get_sdp_inventory(macs)` query (no per-device `get_device_detail`
   loads).
2. **OUI / address-type breakdown** — bucketed by `addr_type`:
   * **public** → tallied by 24-bit OUI and **IEEE-vendor-decoded** via
     `resolve_oui()` (graceful "vendor unknown" when a prefix is unregistered or
     the OUI module is absent);
   * **random** → sub-classified from the first octet's top two bits into
     **RPA** (resolvable, `01`), **static-random** (`11`) and **NRPA** (`00`), and
     explicitly *not* vendor-decoded — a random address's OUI is a privacy
     address, not a manufacturer.
3. **Advertisement hex analysis** — reuses the `dissect_persisted_record` decoder
   shared with `db show` to fold, across the selection: manufacturer data (grouped
   by company id), service data (grouped by UUID), and advertising-data AD
   structures. Each payload group reports a unique-payload tally, the longest
   common whole-byte prefix (the shared "pattern"), a decoded representative, and a
   **repeated-payload flag** — an identical payload seen across ≥2 devices, flagged
   as a possible static/identity leak (also surfaced on the terminal).

`--recon-detail` implies `--recon` and additionally analyses **characteristic-value
hex** (grouped by characteristic UUID, decoded via `decode_characteristic_value`)
using a batched `get_characteristic_values(macs)` query — heavier, hence its own
flag.

**Presentation.** Every count-bearing block follows one `<unique entry> : <count>`
convention. The SDP and OUI inventories render as markdown tables by default
(capped at the top 50 with a pointer to the complete JSON `recon` block); pass
`--report-bullets` for the unified bullet form. UUID short-forms display in
lower-case Bluetooth notation (`0x1200`), Advertisement Dissection ASCII uses the
hexdump convention (non-printable bytes → `.`), and empty sections show `- None.`.
Per-device SDP enrichment (flags/protocols/spec-hint/anomalies) is grouped under a
`Flags & enrichment:` sub-label beneath the service inventory; repeated security
flags and SDP anomalies are collapsed to unique `… : count` rows and rendered as
their own tables (`| Security flag | Count |`, `| Severity | SDP anomaly | Count |`)
— also switchable to bullets via `--report-bullets`. Protocols and the spec hint
stay inline.

The OUI vendor database lives in `bleep/bt_ref/oui.py` (24-bit IEEE MA-L, ~40k
entries), regenerated via `bleep refresh-refs --oui-only` (or directly with
`python -m bleep.bt_ref.update_oui`) following the same `bt_ref`
updater+generated-module pattern as `usb_ids.py`. MA-M/MA-S (28/36-bit shared
prefixes) are intentionally left unresolved rather than misattributed.

```bash
# Append "## Reconnaissance Analytics" (SDP inventory + OUI decode + hex patterns).
python -m bleep.cli db report --since 2026-08-06 --until 2026-08-10 --seen-basis any \
    --status classic --all-in-window --recon --out recon_report.md

# Machine-readable recon block (with characteristic-hex analysis).
python -m bleep.cli --json db report --since 2026-08-06 --until 2026-08-10 --seen-basis any \
    --all-in-window --recon-detail > recon.json
```

Both OUI (2) and advertisement (3) analyses read columns already returned by
`get_devices` (`addr_type`, `manufacturer_id/_data`, `service_data`,
`advertising_data`, `uuids`) — **zero** extra queries; only the SDP rollup and
optional characteristic-hex view issue one batched query each.

The `db timeline` command supports filtering by service and characteristic UUIDs:

```bash
# Filter by service UUID
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF --service 1800

# Filter by characteristic UUID
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF --char 2a00

# Limit the number of entries
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF --limit 10
```

#### SDP record change view (`db timeline --sdp`)

Classic SDP record snapshots are stored append-only (schema v16 — a new row is
appended only when an attribute value changes), so `db timeline --sdp` renders the
history of a device's SDP records rather than characteristic reads. It prints an
`[initial]` snapshot per record, then for each later snapshot only the fields that
changed (attribute values **and** service-record-handle rotation), oldest-first.
Add `--uuid` to scope one service class.

```bash
# All SDP record changes for a device
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF --sdp

# One service class only (any form: 1101, 0x1101, or full 128-bit)
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF --sdp --uuid 1101
```

Backed by `get_observed_uuid`-adjacent `get_sdp_timeline(mac, uuid=None, limit=None)`
in `bleep.core.observations`, which reads the `sdp_records` history ordered by
`(uuid, channel, ts, id)`.

### Observed-UUID catalogue (`db uuids`)

`db uuids` aggregates every UUID **actually observed** on scanned/enumerated
devices — across LE services, characteristics, descriptors, Classic services, and
SDP records — canonicalised to 128-bit so short and long forms of the same UUID
merge. Each entry reports the names it was seen under, the observation count, the
source tables, first/last-seen timestamps, and up to five sample device MACs.

```bash
# Full catalogue, most-observed first (JSON with --json / --quiet)
python -m bleep.cli db uuids

# Everything known about one UUID (any form: 0xFE95, FE95, or full 128-bit)
python -m bleep.cli db uuids --uuid 0xFE95

# Promote a vendor/proprietary UUID into the authoritative custom names
python -m bleep.cli db uuids --uuid 0000FE95-0000-1000-8000-00805F9B34FB --promote "Xiaomi Mi"

# Union the curated non-SIG seed (Nordic UART, Google Fast Pair, …)
python -m bleep.cli db uuids --seed
```

Promotions persist to `~/.bleep/custom_uuids.json` (override with
`BLEEP_CUSTOM_UUIDS`) which `constants.UUID_NAMES` merges at import, so subsequent
runs resolve the UUID directly. The catalogue itself is a *non-authoritative*
"seen in the wild" tier and never overwrites the SIG/custom reference tables; see
[UUID Translation](uuid_translation.md) for the resolver tiers.

**Curated seed (`--seed`).** `get_observed_uuid_catalogue(include_seed=True)`
unions a small hand-maintained set of well-known **non-SIG** UUIDs (from
`bt_ref/observed_seed.py` — e.g. Nordic UART, Google Nearby/Fast Pair) into the
result, tagged `source="curated_seed"`. Unobserved seed UUIDs appear as count-0
reference rows; a seed UUID that was also observed merges (names/sources union,
observed count retained). The seed is **documentation/reference only** — it is
*not* consumed by the classifier's promotion path, so it can never affect a
device-type verdict.

#### Classifier feed (device-type enrichment)

The device-type classifier's `LEServiceDataCollector` consults
`get_observed_uuid_names()` for advertised UUIDs that the curated beacon/UART
signature sets don't recognise. By default a hit adds **WEAK**
`LE_ADVERTISING_DATA` evidence tagged `evidence_source="observed_catalogue"`. This
is *additive context only*: WEAK evidence enriches the confidence and reasoning but
can never flip a verdict (`_classify_le`/`_classify_classic`/`_classify_dual`
consult only CONCLUSIVE/STRONG evidence), so a mislabelled or self-referential
observation can never mis-type a device.

**Opt-in source-aware promotion.** When enabled via
`context["allow_observed_promotion"]` or env `BLEEP_CLASSIFIER_OBSERVED_PROMOTION`,
the feed instead calls `get_observed_uuid_evidence(uuid)` — which reports whether
the UUID was **LE-measured** (`services`/`characteristics`/`descriptors`) and/or
**Classic-measured** (`classic_services`/`sdp_records`) — and promotes to STRONG
evidence *on the matching transport only* (`LE_ADVERTISING_DATA` /
`CLASSIC_SERVICE_UUIDS`, tagged `promoted=True`). This path **can** flip a verdict,
so it is off by default and always provenance-tagged. The curated `--seed` set is
never consulted here. See [device_type_classification.md](device_type_classification.md).

## Real-World Usage Scenarios

For comprehensive examples of how to use the observation database in real-world scenarios, see [Real-World Usage Scenarios](observation_db_usage_scenarios.md), which includes:

- **Long-term device monitoring workflows**: Continuous monitoring, behavior analysis, and daily inventory reports
- **Enterprise device tracking patterns**: Corporate asset tracking, multi-location correlation, and inventory management
- **Security assessment workflows**: Automated security audits, threat detection, and vulnerability identification
- **Integration examples**: SIEM integration, REST API creation, and database backup/sync

Each scenario includes complete, working code examples that can be adapted to specific use cases.