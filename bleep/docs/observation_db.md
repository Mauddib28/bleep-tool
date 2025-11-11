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
| `pbap_metadata` | Phone-book repository metadata (entries, hash) |
| `aoi_analysis` | Assets-of-Interest analysis results (security concerns, unusual characteristics) |
| `device_type_evidence` | *NEW* – Device type classification evidence for audit/debugging (Schema v6) |

## Automatic logging

* `scan`, `connect`, `gatt-enum` and related helpers insert devices, services and characteristics.
* `explore` and `enum-scan` commands save discovered services and characteristics to the database, including GATT hierarchy.
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

```python
# Import necessary modules
from bleep.analysis.aoi_analyser import AOIAnalyser
from bleep.core import observations

# Initialize analyzer with database integration
analyzer = AOIAnalyser(use_db=True)

# Load device data from database
device_mac = "00:11:22:33:44:55"
device_data = analyzer.load_device_data(device_mac)

# Get AoI analysis from database
analysis = observations.get_aoi_analysis(device_mac)

# Store AoI analysis in database
observations.store_aoi_analysis(device_mac, analysis)

# Get all devices with AoI analysis
analyzed_devices = observations.get_aoi_analyzed_devices()
```

## Device Type Classification

BLEEP uses an **evidence-based, stateless classification system** (Schema v6). Classification decisions are based **only** on current device properties and active queries, never on historical database data. This prevents false positives from MAC address collisions.

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