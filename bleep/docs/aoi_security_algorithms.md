# Assets-of-Interest (AoI) Security Analysis Algorithms

This document provides detailed documentation of the security analysis algorithms implemented in the `AOIAnalyser` class. These algorithms identify security concerns, unusual characteristics, and notable services in Bluetooth devices.

## Overview

The AoI security analysis system uses a multi-layered approach to evaluate Bluetooth devices:

1. **Service Analysis**: Identifies notable services that may indicate security-relevant functionality
2. **Characteristic Analysis**: Detects security concerns and unusual patterns in GATT characteristics
3. **Permission Analysis**: Evaluates access control and permission maps
4. **Accessibility Scoring**: Calculates device accessibility metrics
5. **Recommendation Generation**: Produces actionable security recommendations

## Algorithm Details

### 1. Service Analysis Algorithm

**Method**: `_analyse_service(uuid, service_info)`

**Purpose**: Identifies services that are notable for security assessment purposes.

**Algorithm**:
1. Extract service UUID and resolve to human-readable name
2. Check for core BLE services (GAP: 0x1800, GATT: 0x1801)
3. Check the UUID against a curated set of known vendor OTA/DFU service UUIDs
4. Check for firmware update services (OTA/DFU/firmware keywords)
5. Check for authentication/security services (auth/security keywords)

**Notable Service Detection Rules**:
- **Core BLE Services**: Services with UUID `1800` (GAP) or `1801` (GATT) are marked as notable
- **Vendor OTA/DFU Services (F8)**: Services whose canonical UUID matches the
  curated `_OTA_DFU_SERVICE_UUIDS` set are marked notable with the vendor name
  (e.g. Nordic Secure DFU `FE59`, Nordic Legacy DFU `…1530…`, TI OAD `F000FFC0…`,
  Silicon Labs OTA `1D14D6EE…`, MCUmgr SMP `8D53DC1D…`). This catches custom
  128-bit firmware-update services that carry no descriptive SIG name. UUIDs are
  normalised via `_canonical_uuid()` so 16-/32-bit short forms also match.
- **Firmware Update Services**: Services whose resolved name contains "OTA"
  (case-sensitive acronym, to avoid false positives on substrings like "toyota"),
  or "dfu"/"firmware" (case-insensitive)
- **Security Services**: Services with names containing "auth" or "security" (case-insensitive)

**Output Structure**:
```python
{
    "uuid": "1800",
    "name": "Generic Access Profile",
    "is_primary": bool,
    "is_notable": True,
    "notable_reason": "Core BLE service",
    "characteristics": [...]
}
```

### 2. Characteristic Security Analysis Algorithm

**Method**: `_analyse_characteristic(uuid, char_info)`

**Purpose**: Identifies security concerns and unusual patterns in GATT characteristics.

#### Security Concern Detection

**Algorithm**:
1. Normalise properties to lower-case; `writable` = has `write` **or**
   `write-without-response`
2. Resolve an **effective name**: the SIG name from the UUID, or — when the UUID
   is unknown — the characteristic's own `name`/`description`/`user_description`
   (so custom UUIDs that carry a meaningful label are still matched)
3. Apply the two security-concern branches below

**Security Concern Detection Rules** (first match wins):

**Branch A — named auth/credential characteristic that is writable (high signal)**
- **Condition**: `writable` **AND** the effective name contains one of
  `auth`, `password`, `passphrase`, `key`, `pin`, `token`, `credential`
  (case-insensitive)
- **Result**: `security_concern = True`, with reason:
  - "Authentication-related characteristic '{name}' allows write without response"
    when `write-without-response` is present, else
  - "Authentication-related characteristic '{name}' is writable"

**Branch B — unauthenticated custom write surface (medium signal)**
- **Condition** (only if Branch A did not match): characteristic has
  `write-without-response`, **lacks** `authenticated-signed-writes`, **and** the
  UUID has no SIG name (`Unknown`/`Unknown Characteristic`)
- **Result**: `security_concern = True`, `security_risk = "medium"`, reason:
  "Custom characteristic accepts write-without-response with no
  authenticated/signed-write requirement (unauthenticated write surface)"

**Rationale**: Writable authentication/credential characteristics can be a
manipulation surface; a custom `write-without-response` characteristic with no
signed-write requirement is an unauthenticated write surface worth investigating.

#### Unusual Characteristic Detection

**Algorithm** (F8: refined, case-insensitive):
1. Normalise properties to lower-case
2. Check for a bidirectional control channel (writable **and** notify/indicate)
3. Check for an unusually long hex default value

**Unusual Characteristic Detection Rules**:

**Rule 1: Bidirectional Control Channel**
- **Condition**: Characteristic is writable (`write` or `write-without-response`)
- **AND** supports `notify` or `indicate` (case-insensitive)
- **Result**: Marked as unusual with reason: "Writable and notify/indicate — bidirectional control channel"
- **Note**: the previous arbitrary "more than 3 properties" count threshold was
  removed — the write+notify/indicate combination is the meaningful signal.

**Rule 2: Unusually Long Values**
- **Condition**: Characteristic has a string default value longer than 40 characters
- **AND** the value is hex-like (only `0-9a-fA-F`) — i.e. ≈20+ bytes of embedded data
- **Result**: Marked as unusual with reason: "Contains unusually long default value (possible embedded data)"

**Output Structure**:
```python
{
    "uuid": "0000abcd-...",           # custom auth/credential characteristic
    "name": "Auth Key",
    "properties": ["read", "write-without-response"],
    "security_concern": True,
    "security_reason": "Authentication-related characteristic 'Auth Key' allows write without response",
    "is_unusual": False
}
```

### 3. Permission Map Analysis Algorithm

**Method**: `_analyse_permission_map(permission_map)`

**Purpose**: Analyzes read/write permissions across device characteristics.

**Algorithm**:
1. Iterate through permission map entries
2. For each UUID, check if it's a critical characteristic
3. Mark status and criticality

**Critical UUID Detection**:
- Uses `_is_critical_uuid(uuid)` helper
- Checks characteristic name for keywords: "auth", "password", "key", "firmware", "dfu", "ota", "security"
- Returns boolean indicating if UUID is security-critical

**Output Structure**:
```python
{
    "uuid": {
        "status": "OK" | "BLOCKED" | "PROTECTED",
        "is_critical": True | False
    }
}
```

### 4. Landmine Map Analysis Algorithm

**Method**: `_analyse_landmine_map(landmine_map)`

**Purpose**: Identifies potentially dangerous operations that may cause device issues.

**Algorithm**:
1. Iterate through landmine map entries
2. For each UUID, check if it's a critical characteristic
3. Mark status and criticality

**Landmine Detection**:
- Landmines are characteristics that may cause device disconnection, reset, or other issues when accessed
- Critical characteristics flagged as landmines are particularly concerning

**Output Structure**:
```python
{
    "uuid": {
        "status": "OK" | "LANDMINE",
        "is_critical": True | False
    }
}
```

### 4b. SDP Record Analysis (F9)

**Method**: `_analyse_sdp_records(records)`

**Purpose**: Summarise Classic SDP records for the report.

**Data sourcing (SR-N1)**: `analyse_device()` reads SDP under the `sdp_summary`
key. Live scans set it directly; for devices loaded from the observation DB,
`_hydrate_db_device_data()` maps `sdp_records` (or `classic_services` as a
fallback) → `sdp_summary` so DB-sourced Classic evidence is analysed identically.
Pairing is bridged the same way (`pairing_events` → `pairing_profile`), and the
pairing analysis flags default/weak PINs. Record `name` may be NULL from the DB;
the scan coerces it safely.

**Algorithm**:
1. Build the backward-compatible shallow summary — `raw_count`,
   `services_found`, and `security_flags` (substring scan for exposed Classic
   profiles: obex/ftp/opp/pbap/map/spp/serial).
2. Build a readable **`services_inventory`** (via `_aggregate_sdp_inventory`):
   the snapshot-heavy record list collapsed by `(name, uuid, channel)` with an
   occurrence `count`, sorted by descending count then name/uuid — the same
   presentation convention as the DB-9 aggregate SDP inventory, but at
   single-device granularity. The RFCOMM `channel` is part of the key so the same
   service class exposed on different channels stays distinct. This is what the
   report's `## SDP Discovery` section renders (`Name (UUID[, ch N]) : count`,
   with an `N unique of M records` header); `services_found` is retained
   unchanged for JSON/back-compat.
3. **Enrich** the summary by routing the same records through the comprehensive
   `SDPAnalyzer.analyze()` (`bleep/analysis/sdp_analyzer.py`), adding — when
   present — `protocols` (e.g. RFCOMM/L2CAP/OBEX/BNEP), `rfcomm_channels`,
   `anomalies` (version inconsistencies, missing names), and
   `inferred_spec_version` (SDP profile-derived hint, **not** the core spec).

**Safety**: enrichment is strictly additive and wrapped in a guard — any
`SDPAnalyzer` failure leaves the shallow summary (and its `security_flags`)
untouched. Anomalies are surfaced in the report's SDP section only; they do
**not** create scored `security_concerns` (the authoritative LMP↔SDP
cross-validation concern is added separately in `analyse_device`).

### 4c. Pairing Profile Analysis (SR-N1)

**Method**: `_analyse_pairing_profile(profile)`

**Purpose**: Surface pairing-related security concerns from an observed bond
(live `--deep` pairing) or from a DB `pairing_events` row bridged to a
`pairing_profile` (see the SR-N1 data-sourcing note in §4b).

**Concerns raised**:
- **JustWorks** — `paired == True` and `method == "JustWorks"` →
  "Device paired via JustWorks (no MITM protection)"
- **Default/weak PIN** — a PIN was observed **and** `_is_weak_pin()` returns
  True → "Default/weak pairing PIN observed ({pin})"
- **Pairing error** — `error` is set and does not contain "rejected" →
  "Pairing error: {error}"

**Weak-PIN rule** (`_is_weak_pin(pin)`) — a stripped PIN is weak when it is:
- one of the well-known defaults `0000`, `1234`, `1111`, `0000000`, `00000000`,
  or `123456`; **or**
- all-numeric with every digit identical (e.g. `2222`); **or**
- all-numeric and shorter than 6 digits.

These concerns feed the risk ranking: JustWorks/"no MITM" → **high** (Rule 1),
default/weak PIN → **medium** (Rule 4).

### 5. Accessibility Scoring Algorithm

**Method**: `_generate_accessibility_summary(landmine_map, permission_map)`

**Purpose**: Calculates a quantitative measure of device accessibility.

**Algorithm**:
1. Calculate total unique characteristics from both maps
2. Count blocked characteristics (landmine_map status != "OK")
3. Count protected characteristics (permission_map status != "OK")
4. Calculate accessibility score: `(total - blocked - protected) / total`

**Accessibility Score Formula**:
```
accessibility_score = (total_characteristics - blocked_characteristics - protected_characteristics) / total_characteristics
```

**Score Interpretation**:
- **0.0 - 0.3**: Low accessibility (limited access, many protections)
- **0.3 - 0.7**: Moderate accessibility (balanced access and protection)
- **0.7 - 1.0**: High accessibility (most characteristics accessible)

**Output Structure**:
```python
{
    "total_characteristics": 25,
    "blocked_characteristics": 3,
    "protected_characteristics": 5,
    "accessibility_score": 0.68  # (25 - 3 - 5) / 25
}
```

### 6. Recommendation Generation Algorithm

**Method**: `_generate_recommendations(report)`

**Purpose**: Generates actionable security recommendations based on analysis findings.

**Algorithm**:
1. Check for security concerns
2. Check for unusual characteristics
3. Evaluate accessibility score
4. Generate context-specific recommendations

**Recommendation Rules**:

**Rule 1: Security Concerns Present**
- **Condition**: Report contains security concerns
- **Action**: Generate recommendation to investigate security concerns
- **Format**: "Investigate {count} security concerns including {first_concern_name}."

**Rule 2: Unusual Characteristics Present**
- **Condition**: Report contains unusual characteristics
- **Action**: Generate recommendation to examine unusual characteristics
- **Format**: "Examine {count} unusual characteristics including {first_unusual_name}."

**Rule 3: High Accessibility**
- **Condition**: Accessibility score > 0.8
- **Action**: Recommend detailed enumeration
- **Format**: "Device is highly accessible ({score}%). Consider detailed enumeration of all characteristics."

**Rule 4: Low Accessibility**
- **Condition**: Accessibility score < 0.3
- **Action**: Recommend authentication/pairing exploration
- **Format**: "Device has limited accessibility ({score}%). Consider authentication/pairing options."

**Rule 5: Default Recommendation**
- **Condition**: No specific concerns found
- **Action**: Provide standard continuation recommendation
- **Format**: "No specific concerns found. Continue with standard enumeration."

**Output**: List of recommendation strings

## Analysis Workflow

The complete analysis workflow follows these steps:

1. **Data Loading**: Load device data from database or file
2. **Service Analysis**: Analyze all services using `_analyse_service()`
3. **Characteristic Analysis**: Analyze all characteristics using `_analyse_characteristic()`
4. **Permission Analysis**: Process permission maps using `_analyse_permission_map()`
5. **Landmine Analysis**: Process landmine maps using `_analyse_landmine_map()`
6. **Accessibility Calculation**: Generate accessibility summary
7. **Recommendation Generation**: Create actionable recommendations
8. **Report Assembly**: Combine all findings into structured report

## Risk Ranking

Each security concern is assigned a `risk` level (`high`, `medium`, or `low`) by
`_assign_concern_risk(concern, source)`.  Pre-existing `risk` values are never
overwritten (idempotent).

### Classification Rules (evaluated in order)

| Priority | Condition | Risk | Examples |
|----------|-----------|------|----------|
| 1 | `reason` contains `write without response`, `justworks`, or `no mitm` | **high** | Writable auth characteristics, JustWorks pairing |
| 2 | `reason` contains `outdated bluetooth`, `knob`, or `bias` | **high** | LMP < 6 (pre-BT 4.0), KNOB/BIAS vulnerable versions |
| 3 | `name` contains `pairing` AND `reason` contains `error` | **medium** | Pairing error states |
| 4 | `reason` contains `pairing pin`, `weak pin`, or `default/weak` | **medium** | Default/weak pairing PINs (SR-N1) |
| 5 | `reason` contains `obex`, `ftp`, `pbap`, `map`, `spp`, `opp`, `serial`, or `classic profile` | **medium** | Exposed Classic profiles |
| 6 | `reason` contains `version mismatch` or `claims profile version` | **medium** | SDP/LMP version inconsistencies |
| 7 | `source == "characteristic"` (no keyword match) | **high** | Unrecognised characteristic-level concerns default to high |
| 8 | Fallback | **low** | Informational findings |

A `description` field is set from the `reason` value via `setdefault`.

### Implementation

```python
# bleep/analysis/aoi_analyser.py — _assign_concern_risk()
if "risk" in concern:
    return concern  # never overwrite existing classification

reason = (concern.get("reason") or "").lower()
# Rule 1: high-risk keywords → "high"
# Rule 2: version vulnerability keywords → "high"
# Rule 3: pairing errors → "medium"
# Rule 4: default/weak pairing PIN keywords → "medium" (SR-N1)
# Rule 5: Classic profile keywords → "medium"
# Rule 6: version mismatch → "medium"
# Rule 7: characteristic source fallback → "high"
# Rule 8: everything else → "low"
concern.setdefault("description", concern.get("reason", ""))
```

## Security Score

The security score is a 0–10 integer computed by `_calculate_security_score()`,
where **higher = more risk**. A fully clean device scores **0** (F5).

### Formula

```
score = (high_count   × 3)
      + (medium_count × 2)
      + (low_count    × 1)

final = clamp(score, 0, 10)
```

Integer severity weights keep the score exact (no truncation). A device with no
security concerns scores 0; any single concern raises the score by its severity
weight.

| Scenario | Calculation | Score |
|----------|-------------|-------|
| No concerns (clean) | 0 | **0** |
| 1 low | 1 | **1** |
| 1 medium | 2 | **2** |
| 1 high | 3 | **3** |
| 2 high + 1 medium | 3 + 3 + 2 = 8 | **8** |
| 10 high | 30 → clamped | **10** |

> **History note (F5, schema-independent).** Before this redesign the score used
> a baseline of 5 with fractional weights (high 1.5 / medium 0.75 / low 0.25) and
> `int()` truncation, so a clean device reported 5/10 and the effective range was
> 5–10. The current 0-based integer model removes that misrepresentation.

### Legacy Concern Handling

Concerns without a `risk` field (from older analysis runs) are retroactively
classified via `_assign_concern_risk(concern, source="unknown")` before counting.

## Algorithm Complexity

- **Service Analysis**: O(n) where n = number of services
- **Characteristic Analysis**: O(m) where m = number of characteristics
- **Permission/Landmine Analysis**: O(p) where p = number of mapped characteristics
- **Accessibility Calculation**: O(p) for set operations
- **Recommendation Generation**: O(1) - constant time checks
- **Overall Complexity**: O(n + m + p) - linear in total number of services and characteristics

## Limitations and Considerations

1. **Keyword-Based Detection**: Security concern detection relies on keyword matching in characteristic names, which may produce false positives or miss concerns with non-standard naming
2. **Static Rules**: Detection rules are hardcoded and may not adapt to new attack vectors
3. **No Context Awareness**: Algorithms don't consider device type, manufacturer, or known vulnerabilities
4. **Permission Map Dependency**: Analysis quality depends on accurate permission map data from enumeration
5. **Accessibility Score Simplification**: Score doesn't weight critical characteristics differently
6. **Additive Score Model**: Security score is additive from a **baseline of 0** — a clean device scores 0 and each concern adds by severity (high 3 / medium 2 / low 1), capped at 10; higher scores indicate more exposure (F5)
7. **Risk Classification Order-Dependent**: The first matching keyword rule wins; overlapping conditions (e.g., a `justworks` concern on a characteristic) resolve to the earlier rule

## Future Enhancement Opportunities

1. **Machine Learning Integration**: Train models on known vulnerabilities to improve detection accuracy
2. **Dynamic Rule Engine**: Allow rules to be configured or updated without code changes
3. **Threat Intelligence Integration**: Incorporate known CVEs and vulnerability databases
4. **Weighted Scoring**: Apply different weights to critical vs. non-critical characteristics in accessibility scoring
5. **Pattern Recognition**: Detect unusual patterns across multiple devices or over time
6. **Context-Aware Analysis**: Consider device type, manufacturer, and protocol version in analysis

