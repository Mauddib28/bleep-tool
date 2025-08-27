# Observation database

BLEEP maintains a local SQLite database (`~/.bleep/observations.db`) that automatically stores information gathered during scans and interactions.

## What is stored?

| Table | Contents |
|-------|----------|
| `devices` | Basic device information (MAC, name, RSSI, first/last seen…) |
| `adv_reports` | Raw advertising reports with decoded fields |
| `services` / `characteristics` / `descriptors` | GATT hierarchy discovered during enumeration |
| `char_history` | *NEW* – every value read from a characteristic (timestamped) |
| `media_players` / `media_transports` | AVRCP & A2DP state snapshots |
| `classic_services` | RFCOMM-based service → channel mapping (SDP) |
| `pbap_metadata` | Phone-book repository metadata (entries, hash) |

## Automatic logging

* `scan`, `connect`, `gatt-enum` and related helpers insert devices, services and characteristics.
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

Migrations occur transparently when the schema version changes. For detailed migration history, see [README.refactor-migrations.md](../../README.refactor-migrations.md).

## Database CLI Filters

The `db list` command supports filtering devices by status:

```bash
# List only Classic Bluetooth devices
python -m bleep.cli db list --status classic

# List only BLE devices
python -m bleep.cli db list --status ble

# List only devices with media capabilities
python -m bleep.cli db list --status media

# List recently seen devices (last 24 hours)
python -m bleep.cli db list --status recent
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