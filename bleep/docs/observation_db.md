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
| `aoi_analysis` | Assets-of-Interest analysis results (security concerns, unusual characteristics) |
| `device_type_evidence` | Device type classification evidence for audit/debugging (Schema v6) |

## Automatic logging

* `scan`, `connect`, `gatt-enum` and related helpers insert devices, services and characteristics.
* `explore` and `enum-scan` commands save discovered services and characteristics to the database, including GATT hierarchy.
* `classic-enum`, `csdp` (debug mode), and SDP discovery functions automatically store full SDP record snapshots in `sdp_records` table.
* `multi_read_all` logs characteristic values into `char_history` with no extra flags.
* Media helpers snapshot players/transports whenever they are encountered.

## CLI access

```
python -m bleep.cli db list --fields mac,name,last_seen
python -m bleep.cli db show AA:BB:CC:DD:EE:FF
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF     # char_history view
python -m bleep.cli db export AA:BB:... --out dump.json
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

Migrations occur transparently when the schema version changes. For detailed migration history, see [README.refactor-migrations.md](../../README.refactor-migrations.md).

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

# Synchronize database and files (bidirectional)
python -m bleep.cli aoi db sync [--address MAC]

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

# Filter by source (read, write, notification, etc.)
read_operations = get_characteristic_timeline(
    mac="00:11:22:33:44:55",
    source="read",
    limit=100
)
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
    store_aoi_analysis,
    has_aoi_analysis,
    get_aoi_analyzed_devices
)

# Check if device has analysis
if has_aoi_analysis("00:11:22:33:44:55"):
    # Get analysis results
    analysis = get_aoi_analysis("00:11:22:33:44:55")
    security_concerns = analysis.get('security_concerns', [])
    recommendations = analysis.get('recommendations', [])

# Store analysis results
analysis_data = {
    'analysis_timestamp': '2025-01-15T10:30:00',
    'security_concerns': [...],
    'unusual_characteristics': [...],
    'notable_services': [...],
    'recommendations': [...]
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
    decoded={'flags': 6, 'services': ['1800']}  # Decoded structure
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

# Store characteristics
upsert_characteristics(
    mac="00:11:22:33:44:55",
    services=[{
        'uuid': '1800',
        'characteristics': [
            {
                'uuid': '2a00',
                'handle': 3,
                'properties': 'read',
                'value': b'Device Name'
            }
        ]
    }]
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

BLEEP uses an **evidence-based, stateless classification system** (Schema v6). Classification decisions are based **only** on current device properties and active queries, never on historical database data. This prevents false positives from MAC address collisions. The database schema is currently at **version 7** (see [Schema Versioning](#schema-versioning) section above).

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
```

The `db timeline` command supports filtering by service and characteristic UUIDs:

```bash
# Filter by service UUID
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF --service 1800

# Filter by characteristic UUID
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF --char 2a00

# Limit the number of entries
python -m bleep.cli db timeline AA:BB:CC:DD:EE:FF --limit 10
```