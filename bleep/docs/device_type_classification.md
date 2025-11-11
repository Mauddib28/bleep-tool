# Device Type Classification Guide

## Overview

BLEEP uses an evidence-based classification system to determine whether a Bluetooth device is Classic-only, LE-only, dual-mode, or unknown. This system is **stateless** - classification decisions are based **only** on current device properties and active queries, never on historical database data. This prevents false positives from MAC address collisions.

## Classification System Architecture

### Core Components

1. **`DeviceTypeClassifier`** (`bleep/analysis/device_type_classifier.py`):
   - Central classification engine
   - Collects evidence from multiple sources
   - Applies strict dual-detection logic
   - Supports mode-aware evidence collection

2. **Evidence Collectors**:
   - Modular, pluggable evidence collection
   - Each collector has a `supported_modes` property
   - Collectors filter themselves based on scan mode

3. **Database Integration**:
   - `device_type_evidence` table for audit/debugging (NOT used for classification)
   - Signature caching for performance optimization
   - Schema v6 migration support

## Device Types

### Classification Results

- **`unknown`**: Not enough evidence to determine device type
- **`classic`**: Bluetooth Classic (BR/EDR) only
- **`le`**: Bluetooth Low Energy only
- **`dual`**: Both Classic and LE capabilities (requires conclusive evidence from BOTH)

### Detection Criteria

#### Classic Device Detection

**Conclusive Evidence:**
- `device_class` property present (Classic device class code)
- SDP records discovered via `GetServiceRecords()` or `discover_services_sdp_connectionless()`

**Strong Evidence:**
- Classic service UUIDs detected (from `SPEC_UUID_NAMES__SERV_CLASS`)

**Classification Logic:**
- Requires at least one conclusive piece of evidence
- Strong evidence alone is insufficient for Classic classification

#### LE Device Detection

**Conclusive Evidence:**
- `AddressType` = "random" (LE random addresses are conclusive)
- GATT services resolved via `services_resolved()`

**Strong Evidence:**
- LE service UUIDs detected (from `SPEC_UUID_NAMES__SERV`)
- Advertising data present

**Classification Logic:**
- Requires at least one conclusive piece of evidence OR multiple strong pieces
- `AddressType` = "public" is **inconclusive** (default for both Classic and LE)

#### Dual Device Detection

**Strict Requirements:**
- **MUST** have conclusive Classic evidence (device_class OR SDP records)
- **MUST** have conclusive LE evidence (random address OR GATT services)
- Both protocols must be confirmed independently

**Prevents False Positives:**
- MAC address collisions (same MAC, different devices over time)
- Incomplete data (partial Classic or LE information)
- Ambiguous evidence (public addresses, weak UUID matches)

## Evidence Types and Weights

### Evidence Weights

1. **CONCLUSIVE**: Definitively indicates device type
   - Examples: `device_class`, SDP records, random address type, GATT services

2. **STRONG**: Strong indicator but not definitive alone
   - Examples: Classic/LE service UUIDs, advertising data

3. **WEAK**: Weak indicator, requires corroboration
   - Examples: Service UUID patterns, advertising flags

4. **INCONCLUSIVE**: Cannot be used for classification
   - Examples: Public address type (default for both Classic and LE)

### Evidence Types

#### Classic Evidence

- **`CLASSIC_DEVICE_CLASS`** (CONCLUSIVE):
  - Source: D-Bus `Class` property
  - Value: Device class code (integer)
  - Collector: `ClassicDeviceClassCollector`

- **`CLASSIC_SDP_RECORDS`** (CONCLUSIVE):
  - Source: SDP query (`discover_services_sdp_connectionless()` or `discover_services_sdp()`)
  - Value: Number of SDP records found
  - Collector: `ClassicSDPRecordsCollector`
  - **Mode**: Only enabled in `pokey` and `bruteforce` modes

- **`CLASSIC_SERVICE_UUIDS`** (STRONG):
  - Source: D-Bus `UUIDs` property
  - Value: List of Classic profile UUIDs
  - Collector: `ClassicServiceUUIDsCollector`
  - Uses: `SPEC_UUID_NAMES__SERV_CLASS` constants

#### LE Evidence

- **`LE_ADDRESS_TYPE_RANDOM`** (CONCLUSIVE):
  - Source: D-Bus `AddressType` property
  - Value: "random"
  - Collector: `LEAddressTypeCollector`

- **`LE_ADDRESS_TYPE_PUBLIC`** (INCONCLUSIVE):
  - Source: D-Bus `AddressType` property
  - Value: "public"
  - Note: Not used for classification (default for both Classic and LE)

- **`LE_GATT_SERVICES`** (STRONG):
  - Source: `device.services_resolved()`
  - Value: List of GATT service objects
  - Collector: `LEGATTServicesCollector`
  - **Mode**: Enabled in `naggy`, `pokey`, and `bruteforce` modes

- **`LE_SERVICE_UUIDS`** (STRONG):
  - Source: D-Bus `UUIDs` property
  - Value: List of GATT service UUIDs
  - Collector: `LEServiceUUIDsCollector`
  - Uses: `SPEC_UUID_NAMES__SERV` constants

- **`LE_ADVERTISING_DATA`** (WEAK):
  - Source: D-Bus `AdvertisingData` property
  - Value: Advertising data dictionary
  - Collector: `LEAdvertisingDataCollector`

## Mode-Aware Evidence Collection

### Scan Modes

The classifier adapts evidence collection based on scan mode aggressiveness:

#### Passive Mode (`passive`)
- **Use Case**: Fast, non-intrusive scanning
- **Enabled Collectors**:
  - `classic_device_class`
  - `classic_service_uuids`
  - `le_address_type`
  - `le_service_uuids`
  - `le_advertising_data`
- **Disabled**: SDP queries, GATT enumeration (requires connection)

#### Naggy Mode (`naggy`)
- **Use Case**: Persistent connection attempts with exponential backoff
- **Enabled Collectors**: All passive collectors + `le_gatt_services`
- **Disabled**: SDP queries (too aggressive for naggy mode)

#### Pokey Mode (`pokey`)
- **Use Case**: Slow, thorough enumeration with extended timeouts
- **Enabled Collectors**: **All collectors** including SDP queries
- **Use**: Full Classic and LE enumeration

#### Bruteforce Mode (`bruteforce`)
- **Use Case**: Exhaustive characteristic testing
- **Enabled Collectors**: **All collectors** including SDP queries
- **Use**: Maximum information gathering

### Integration Points

Scan functions automatically pass appropriate scan_mode:

- `passive_scan_and_connect()` → `scan_mode="passive"`
- `naggy_scan_and_connect()` → `scan_mode="naggy"`
- `pokey_scan_and_connect()` → `scan_mode="pokey"`
- `bruteforce_scan_and_connect()` → `scan_mode="bruteforce"`
- `connect_and_enumerate__bluetooth__classic()` → `scan_mode="pokey"`

## Usage Examples

### Basic Classification

```python
from bleep.analysis.device_type_classifier import DeviceTypeClassifier

classifier = DeviceTypeClassifier()

# Build context from device properties
context = {
    "device_class": 0x5a020c,  # Classic device class
    "address_type": "random",  # LE random address
    "uuids": ["0000110B-0000-1000-8000-00805f9b34fb", "00001800-0000-1000-8000-00805f9b34fb"],
    "connected": True
}

# Classify with passive mode
result = classifier.classify_with_mode(
    mac="AA:BB:CC:DD:EE:FF",
    context=context,
    scan_mode="passive",
    use_database_cache=True
)

print(f"Device Type: {result.device_type}")
print(f"Confidence: {result.confidence:.2f}")
print(f"Reasoning: {result.reasoning}")
```

### Using Device Wrappers

```python
from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic

device = system_dbus__bluez_device__classic("AA:BB:CC:DD:EE:FF")

# Get device type with passive mode (default)
device_type = device.get_device_type()

# Get device type with pokey mode (enables SDP queries)
device_type = device.get_device_type(scan_mode="pokey")
```

### LE Device Type Check

```python
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy

device = system_dbus__bluez_device__low_energy("AA:BB:CC:DD:EE:FF")
device.connect()

# check_device_type() uses naggy mode if connected, passive otherwise
result = device.check_device_type()

if result["is_classic_device"]:
    print("Device supports Classic Bluetooth")
if result["is_le_device"]:
    print("Device supports Bluetooth Low Energy")
```

## Database Integration

### Evidence Storage

Evidence is stored in `device_type_evidence` table for audit/debugging:

```python
from bleep.core.observations import (
    store_device_type_evidence,
    get_device_type_evidence,
    get_device_evidence_signature
)

# Store evidence (automatically called by classifier)
store_device_type_evidence(
    mac="AA:BB:CC:DD:EE:FF",
    evidence_type="classic_device_class",
    evidence_weight="conclusive",
    source="dbus_property",
    value=0x5a020c,
    metadata={"property": "Class"}
)

# Retrieve all evidence for a device
evidence_list = get_device_type_evidence("AA:BB:CC:DD:EE:FF")

# Get evidence signature for caching
signature = get_device_evidence_signature("AA:BB:CC:DD:EE:FF")
```

### Signature Caching

The classifier uses database-first caching for performance:

1. Check if device exists in database
2. Build current evidence signature
3. Compare with stored signature (80% tolerance)
4. If match: return cached classification (1-5ms)
5. If no match: perform full classification (100-5000ms)

**Note**: Caching is for performance only. Classification decisions remain stateless.

## Adding Custom Evidence Collectors

### Example: Custom Collector

```python
from bleep.analysis.device_type_classifier import (
    EvidenceCollector,
    EvidenceType,
    EvidenceWeight,
    EvidenceSet
)

class CustomCollector(EvidenceCollector):
    """Example custom evidence collector."""
    
    @property
    def name(self) -> str:
        return "custom_evidence"
    
    @property
    def evidence_types(self) -> List[EvidenceType]:
        return [EvidenceType.CLASSIC_DEVICE_CLASS]  # Or create new type
    
    @property
    def supported_modes(self) -> List[str]:
        return ["passive", "naggy", "pokey", "bruteforce"]
    
    def collect(
        self,
        mac: str,
        context: Dict[str, Any],
        evidence: EvidenceSet
    ) -> None:
        # Your custom evidence collection logic
        custom_value = context.get("custom_property")
        if custom_value:
            evidence.add(
                EvidenceType.CLASSIC_DEVICE_CLASS,  # Or your custom type
                EvidenceWeight.STRONG,
                "custom_source",
                custom_value,
                {"metadata": "example"}
            )

# Register collector
classifier = DeviceTypeClassifier()
classifier.add_collector(CustomCollector())
```

## Evidence Table Schema

### `device_type_evidence` Table

```sql
CREATE TABLE device_type_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT REFERENCES devices(mac) ON DELETE CASCADE,
    evidence_type TEXT NOT NULL,
    evidence_weight TEXT NOT NULL,
    source TEXT NOT NULL,
    value TEXT,
    metadata TEXT,
    ts DATETIME NOT NULL,
    UNIQUE(mac, evidence_type, source)
);

CREATE INDEX idx_device_type_evidence_mac ON device_type_evidence(mac);
CREATE INDEX idx_device_type_evidence_type ON device_type_evidence(evidence_type);
CREATE INDEX idx_device_type_evidence_ts ON device_type_evidence(ts);
```

### Querying Evidence

```python
import sqlite3
from bleep.core.observations import _DB_PATH

conn = sqlite3.connect(_DB_PATH)
conn.row_factory = sqlite3.Row

# Get all evidence for a device
cursor = conn.execute("""
    SELECT * FROM device_type_evidence
    WHERE mac = ?
    ORDER BY ts DESC
""", ("AA:BB:CC:DD:EE:FF",))

for row in cursor.fetchall():
    print(f"{row['evidence_type']}: {row['value']} ({row['evidence_weight']})")

# Get evidence by type
cursor = conn.execute("""
    SELECT * FROM device_type_evidence
    WHERE mac = ? AND evidence_type = ?
    ORDER BY ts DESC
""", ("AA:BB:CC:DD:EE:FF", "classic_device_class"))

# Get classification history
cursor = conn.execute("""
    SELECT * FROM device_type_evidence
    WHERE mac = ? AND evidence_type = 'classification_result'
    ORDER BY ts DESC
""", ("AA:BB:CC:DD:EE:FF",))
```

## Classification Scenarios

### Scenario 1: Classic-Only Device

**Context:**
- `device_class`: 0x5a020c (Phone)
- `address_type`: None
- `uuids`: ["0000110B-0000-1000-8000-00805f9b34fb"] (PBAP)

**Evidence Collected:**
- `CLASSIC_DEVICE_CLASS` (CONCLUSIVE)
- `CLASSIC_SERVICE_UUIDS` (STRONG)

**Result:** `classic` (high confidence)

### Scenario 2: LE-Only Device

**Context:**
- `device_class`: None
- `address_type`: "random"
- `uuids`: ["00001800-0000-1000-8000-00805f9b34fb"] (GAP)

**Evidence Collected:**
- `LE_ADDRESS_TYPE_RANDOM` (CONCLUSIVE)
- `LE_SERVICE_UUIDS` (STRONG)

**Result:** `le` (high confidence)

### Scenario 3: Dual-Mode Device

**Context:**
- `device_class`: 0x5a020c (Phone)
- `address_type`: "random"
- `uuids`: ["0000110B-0000-1000-8000-00805f9b34fb", "00001800-0000-1000-8000-00805f9b34fb"]
- `connected`: True
- `gatt_services`: [Service(...), Service(...)]

**Evidence Collected:**
- `CLASSIC_DEVICE_CLASS` (CONCLUSIVE)
- `LE_ADDRESS_TYPE_RANDOM` (CONCLUSIVE)
- `LE_GATT_SERVICES` (STRONG)

**Result:** `dual` (high confidence)

### Scenario 4: Insufficient Evidence

**Context:**
- `device_class`: None
- `address_type`: "public" (inconclusive)
- `uuids`: []

**Evidence Collected:**
- None (insufficient)

**Result:** `unknown` (low confidence)

## Troubleshooting

### Classification Returns "unknown"

**Possible Causes:**
1. Insufficient evidence (no conclusive indicators)
2. Device not connected (GATT services unavailable)
3. Scan mode too passive (SDP queries disabled)
4. Device properties not available

**Solutions:**
- Use more aggressive scan mode (`pokey` or `bruteforce`)
- Ensure device is connected for GATT enumeration
- Check device properties are accessible via D-Bus

### False Dual Detection

**Prevention:**
- Strict dual-detection logic requires conclusive evidence from BOTH protocols
- Public address type is not used as LE evidence
- Database history is not used for classification (stateless)

**Debugging:**
- Check evidence table: `get_device_type_evidence(mac)`
- Review evidence weights and types
- Verify both Classic and LE evidence are conclusive

### Performance Issues

**Optimization:**
- Database-first caching (1-5ms cache hits)
- Use appropriate scan mode (passive for fast, pokey for thorough)
- Evidence signature matching (80% tolerance)

**Monitoring:**
- Check evidence table size
- Review signature matching success rate
- Monitor classification timing

## Migration Notes

### Schema v5 to v6

The `device_type_evidence` table is automatically created during database initialization. Migration happens automatically when BLEEP detects schema version 5.

**Migration Steps:**
1. Create `device_type_evidence` table
2. Create indexes for performance
3. Update schema version to 6

**No Data Loss:**
- Existing `devices.device_type` column preserved
- Evidence table is additive (audit trail only)

## Best Practices

1. **Use Appropriate Scan Mode**:
   - Passive for fast discovery
   - Pokey for thorough enumeration
   - Bruteforce for exhaustive testing

2. **Check Classification Results**:
   - Review `confidence` score
   - Check `reasoning` for explanation
   - Verify evidence in database if needed

3. **Handle Edge Cases**:
   - `unknown` type is valid (insufficient evidence)
   - Public addresses are inconclusive
   - MAC address collisions possible (stateless prevents false positives)

4. **Performance Optimization**:
   - Enable database caching (`use_database_cache=True`)
   - Use passive mode when possible
   - Cache classification results in application layer

## References

- **Implementation Plan**: `bleep/docs/DUAL_DEVICE_DETECTION_PLAN.md`
- **Type Property Fix**: `bleep/docs/TYPE_PROPERTY_FIX_PLAN.md`
- **Database Schema**: `bleep/docs/observation_db_schema.md`
- **Source Code**: `bleep/analysis/device_type_classifier.py`

