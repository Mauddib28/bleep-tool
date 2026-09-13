# Device Type Classification Guide

## Overview

BLEEP uses an evidence-based classification system to determine whether a Bluetooth device is Classic-only, LE-only, dual-mode, or unknown. This system is **stateless** - classification decisions are based **only** on current device properties and active queries, never on historical database data. This prevents false positives from MAC address collisions.

> **Advertisement service-data / beacon labels.** The `LEServiceDataCollector`'s
> beacon and service-data UUID labels are sourced from the single authoritative
> map (`SERVICE_DATA_PROTOCOL_LABELS`) in `bt_ref/constants.py` (the canonical
> UUID reference layer), shared with the advertisement dissector so the two
> cannot drift. Several prior labels were
> misattributed (e.g. `FCF1` is Google LLC, not "find_my_beacon"; `FE05` is GN
> Hearing, not Microsoft CDP). These corrections are **relabel-only** — evidence
> type and weight are unchanged, so classification decisions are preserved. See
> [adv_dissection.md](adv_dissection.md) "Known UUID attribution corrections".

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
   - Current schema: **v20** (see [observation_db_schema.md](observation_db_schema.md) for migration history)

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

**Strong Evidence:**
- GATT services resolved via `services_resolved()` (weighted `STRONG`, **not** conclusive — see `bleep/analysis/device_type_classifier.py::LEGATTServicesCollector`)
- LE service UUIDs detected (from `SPEC_UUID_NAMES__SERV`)
- Advertising data present

**Classification Logic (`_classify_le`):**
- Classifies as LE on **any one** of: `LE_ADDRESS_TYPE_RANDOM` (conclusive),
  `LE_GATT_SERVICES` STRONG, `LE_ADVERTISING_DATA` STRONG, **or** the combination
  `LE_SERVICE_UUIDS` STRONG **and** `LE_GATT_SERVICES` STRONG. A single sufficient
  strong signal (e.g. advertising data or resolved GATT services) is enough — it
  does not require multiple strong pieces.
- `AddressType` = "public" is **inconclusive** (default for both Classic and LE)

#### Dual Device Detection

**Strict Requirements:**
- **MUST** have Classic evidence — conclusive (device_class OR SDP records) or strong (Classic service UUIDs)
- **MUST** have LE evidence — conclusive (random address) **or** strong (GATT services resolved, which are weighted **STRONG**, not conclusive; or advertising data / strong LE service UUIDs)
- Both protocols must be confirmed independently

> **Note on GATT weight.** `LE_GATT_SERVICES` is **STRONG**, not CONCLUSIVE (see
> `LEGATTServicesCollector`). In `_classify_dual`, the LE side is satisfied by a
> **conclusive** random address *or* **strong** GATT services — so GATT contributes
> STRONG evidence toward a `dual` verdict, it is not itself conclusive LE evidence.

**Prevents False Positives:**
- MAC address collisions (same MAC, different devices over time)
- Incomplete data (partial Classic or LE information)
- Ambiguous evidence (public addresses, weak UUID matches)

## Evidence Types and Weights

### Evidence Weights

1. **CONCLUSIVE**: Definitively indicates device type
   - Examples: `device_class`, SDP records, random address type

2. **STRONG**: Strong indicator but not definitive alone
   - Examples: GATT services (resolved), Classic/LE service UUIDs, advertising data

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

- **`LE_ADVERTISING_DATA`** (STRONG — advertisement heuristics):
  - Collector: `LEServiceDataCollector`
  - Sources, all treated as advertisement heuristics (`evidence_source="heuristic"`):
    - Beacon / known service-data UUIDs (labels from the authoritative
      `SERVICE_DATA_PROTOCOL_LABELS` map in `bt_ref/constants.py`).
    - `FE05` in advertised UUIDs (CORE Transport Technologies NZ; LE-only indicator).
    - Vendor UART UUIDs (`FFE0`/`FFE1`/`FFF0`/`FFF1`/Nordic UART).
    - **`ManufacturerData`/`ServiceData` BLE protocols (G-7.4)** — the collector
      feeds **both** `ManufacturerData` and `ServiceData` through the shared
      `dissect_advertisement()` and emits evidence when a **BLE-only** protocol is
      decoded (`ibeacon`, `apple_continuity`, `eddystone`; set
      `_LE_INDICATIVE_ADV_PROTOCOLS`). Eddystone lives in `ServiceData` (`0xFEAA`),
      so it is only reachable once `service_data` is passed to the dissector. This
      lets beacon-only devices classify as `le` instead of `unknown`. A bare,
      undecoded company payload is **not** LE evidence, because `ManufacturerData`
      also appears in Classic EIR. Decode logic lives only in the dissector — see
      [adv_dissection.md](adv_dissection.md).

- **Observed-UUID catalogue feed** (default WEAK; opt-in STRONG):
  - Collector: `LEServiceDataCollector` (tagged `evidence_source="observed_catalogue"`)
  - Source: advertised UUIDs the curated beacon/UART sets don't recognise but that
    were **observed under a name before** (LE/Classic service or SDP tables).
  - **Default (promotion off).** Emits WEAK `LE_ADVERTISING_DATA` via
    `get_observed_uuid_names()`. This is **additive context only**: WEAK evidence
    contributes to confidence and reasoning but **cannot flip a verdict**
    (`_classify_le/_classic/_dual` consult only CONCLUSIVE/STRONG), so a mislabelled
    or self-referential observation can never mis-type a device.
  - **Opt-in (promotion on).** When `_observed_promotion_enabled(context)` is true —
    `context["allow_observed_promotion"]` or env `BLEEP_CLASSIFIER_OBSERVED_PROMOTION`
    — the feed instead consults `get_observed_uuid_evidence(uuid)` and promotes to
    **STRONG** evidence *source-aware*: an LE-measured UUID (seen in the `services`/
    `characteristics`/`descriptors` tables) emits STRONG `LE_ADVERTISING_DATA`
    tagged `source="observed_le_gatt"`; a Classic-measured UUID (seen in
    `classic_services`/`sdp_records`) emits STRONG `CLASSIC_SERVICE_UUIDS` tagged
    `source="observed_classic"`. All promoted evidence carries `promoted=True`.
    Because promotion is measurement-scoped, a UUID only ever promotes toward the
    transport it was actually measured on. Off by default so the verdict-affecting
    path is explicit and provenance-tagged.
  - A catalogue/DB failure is swallowed and never breaks classification either way.
    See [observation_db.md](observation_db.md) "Classifier feed".

> **Provenance (G-7.4).** Classic evidence derived from the advertised/cached
> `UUIDs` property (not a live SDP browse) is flagged `ground_truth=False` /
> `source_kind="advertised"`, and `_determine_evidence_source()` reports such a
> verdict as `evidence_source="heuristic"` — only measured SDP/GATT promote to
> `measured_sdp` / `measured_gatt`. The AoI report surfaces the result's
> `evidence_source` and `cached` flags on a **Device Type** line so an
> advertised or cached guess is never mistaken for a measured capability.

#### HID Evidence (added in package v2.8.0; current package 3.1.0)

- **`HID_CLASSIFICATION`** (STRONG):
  - Source: Combined analysis of Appearance, Class of Device, HID Service UUID (0x1124), and `Input1.ReconnectMode` D-Bus property
  - Value: `HIDInfo` dataclass with `is_hid`, `hid_type` (keyboard/mouse/gamepad/joystick/generic), `appearance_value`, `reconnect_mode`, and `evidence_sources`
  - Function: `classify_hid(context)` in `bleep/analysis/device_type_classifier.py`
  - CLI: `bleep hid-info <MAC>` or debug mode `chid`

The `classify_hid()` function evaluates four evidence sources:
1. **Appearance** (GAP 0x19): values 960–968 map to specific HID types (961=keyboard, 962=mouse, etc.)
2. **Class of Device**: major class 0x05 (Peripheral)
3. **HID Service UUID**: presence of `00001124-0000-1000-8000-00805f9b34fb`
4. **Input1.ReconnectMode**: `device` or `host` confirms HID capability

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
  - `le_service_data`
- **Disabled**: SDP queries, GATT enumeration (requires connection)

#### Naggy Mode (`naggy`)
- **Use Case**: Persistent connection attempts with exponential backoff
- **Enabled Collectors**: All passive collectors + `le_gatt_services`
- **Disabled**: SDP queries (too aggressive for naggy mode)

#### Pokey Mode (`pokey`)
- **Use Case**: Slow, thorough enumeration with extended timeouts
- **Enabled Collectors**: Connection/query collectors including SDP queries and
  `le_gatt_services` (`classic_device_class`, `classic_sdp_records`,
  `classic_service_uuids`, `le_address_type`, `le_gatt_services`,
  `le_service_uuids`)
- **Disabled**: `le_advertising_data` and `le_service_data` — these are
  scan/advertising-only collectors whose `supported_modes` is `["passive", "naggy"]`
- **Use**: Full Classic and LE enumeration

#### Bruteforce Mode (`bruteforce`)
- **Use Case**: Exhaustive characteristic testing
- **Enabled Collectors**: Same set as pokey (SDP + `le_gatt_services` +
  UUID/class/address collectors)
- **Disabled**: `le_advertising_data` and `le_service_data` (passive/naggy only)
- **Use**: Maximum information gathering

### Integration Points

Scan functions automatically pass appropriate scan_mode:

- `passive_scan_and_connect()` → `scan_mode="passive"`
- `naggy_scan_and_connect()` → `scan_mode="naggy"`
- `pokey_scan_and_connect()` → `scan_mode="pokey"`
- `bruteforce_scan_and_connect()` → `scan_mode="bruteforce"`
- `connect_and_enumerate__bluetooth__classic()` → `scan_mode="pokey"`

### AoI scan seeding (2026-07-16)

The classifier remains **stateless** and always authoritative when it produces a
concrete result. However, `aoi scan` (`bleep/modes/aoi.py` `_scan_target`) layers
a **seed** on top of it for the `unknown` case only: if the live classification is
inconclusive, a trustworthy transport supplied by the survey JSON (or, failing
that, the stored device record) is adopted so a device the survey already typed
does not regress to `unknown` and does not get probed on an irrelevant transport.

- A **concrete** live result (`le`/`classic`/`dual`) is **never** overridden by a
  seed — statelessness is preserved for every determinate classification.
- The seed is applied by the pure helpers `_resolve_seeded_type()` /
  `_resolve_device_type()`; the outcome is recorded on the AoI record as
  `device_type_source` (`"live"` vs `"seed"`) for auditability.

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
- Strict dual-detection logic requires **independent** evidence from BOTH
  protocols — each side satisfied by conclusive **or** strong evidence (see the
  Dual Device Detection section above and `_classify_dual`); a single protocol's
  signals alone never yield a `dual` verdict
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

### Schema v6 to v7

The `sdp_records` table is automatically created during database initialization. Migration happens automatically when BLEEP detects schema version 6.

**Migration Steps:**
1. Create `sdp_records` table for full SDP record snapshots
2. Create indexes on `mac`, `uuid`, and `ts` for performance
3. Update schema version to 7

**No Data Loss:**
- Existing `classic_services` table preserved (basic UUID/channel mapping)
- SDP records table is additive (detailed snapshots)
- Both tables coexist for different use cases

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

## Known Issues & Fixes

### Foreign Key Constraint Fix (2025-11-27)

**Issue**: FOREIGN KEY constraint violations during scan operations when storing classification evidence.

**Root Cause**: The classifier was storing evidence before devices were inserted into the database, violating the foreign key constraint in the `device_type_evidence` table.

**Solution**: Restructured database operation sequencing:
1. Insert device into database FIRST (creates parent row)
2. Perform classification SECOND (with database cache enabled)
3. Update device with classified type THIRD

**Files Modified**:
- `bleep/dbuslayer/adapter.py` - Deferred classification from `get_discovered_devices()`
- `bleep/ble_ops/le/scan.py` - Restructured `_native_scan()` and `_base_enum()` for proper sequencing
- `bleep/core/observations/` - Added defensive IntegrityError handling (package with submodules `_connection.py`, `_devices.py`, `_services.py`, …)

**Impact**: All scan operations now complete without foreign key errors while maintaining classification accuracy and backward compatibility.

## HID classification: connectionless vs connected (CDU-M1.6)

`classify_hid(context)` is a pure function over an evidence dict. Both surfaces
build that dict through the single shared helper `bleep/ble_ops/hid.py`, so they
cannot drift; they differ only in *which* evidence a given path can obtain.

| Evidence key | Connectionless | Connected | Source |
|--------------|:--------------:|:---------:|--------|
| `device_class` (Class-of-Device, peripheral major `0x05`) | ✓ | ✓ | cached `Device1.Class` |
| `uuids` (HID service `0x1124`) | ✓ | ✓ | `Device1.UUIDs` / SDP profiles |
| `appearance` (LE, `960+`) | usually ✗ | ✓ (LE) | `Device1.Appearance` |
| `_Input1.ReconnectMode` | ✗ | ✓ | `org.bluez.Input1` (only instantiated once connected/bonded) |

Both variants are available on both surfaces:

| Variant | CLI | Debug shell |
|---------|-----|-------------|
| Connectionless (cached discovery props) | `bleep hid-info <MAC>` (default) | `chid <MAC>` (no live session needed) |
| Connected (adds `appearance` / `Input1.ReconnectMode`) | `bleep hid-info <MAC> --connect` | `chid` against the live `connect`/`cconnect` session |

Evidence assembly lives in `bleep/ble_ops/hid.py`
(`context_from_classic` / `context_from_le` / `build_hid_context`); the CLI
dispatch and the debug `chid` command both delegate to it.

## References

- **Database Schema**: [observation_db_schema.md](observation_db_schema.md) (device_type_evidence table, schema v6)
- **Source Code**: `bleep/analysis/device_type_classifier.py`, `bleep/ble_ops/hid.py`
- **Changelog**: [changelog.md](changelog.md) (device-type classification landed in package v2.4.4; current package 3.0.0)

