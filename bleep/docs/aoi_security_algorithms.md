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
3. Check for firmware update services (OTA/DFU keywords)
4. Check for authentication/security services (auth/security keywords)

**Notable Service Detection Rules**:
- **Core BLE Services**: Services with UUID `1800` (GAP) or `1801` (GATT) are marked as notable
- **Firmware Update Services**: Services with names containing "OTA" or "dfu" (case-insensitive)
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
1. Extract characteristic properties (read, write, write-without-response, notify, indicate)
2. Extract characteristic name from UUID
3. Check for authentication-related characteristics with weak permissions

**Security Concern Detection Rules**:
- **Condition**: Characteristic has `write-without-response` property
- **AND** characteristic name contains one of: "auth", "password", "key" (case-insensitive)
- **Result**: Marked as security concern with reason: "Authentication-related characteristic allows write without response"

**Rationale**: Authentication-related characteristics that allow write without response may be vulnerable to unauthorized access or manipulation without proper authentication checks.

#### Unusual Characteristic Detection

**Algorithm**:
1. Count total properties
2. Check for multiple operation types
3. Check for unusually long default values

**Unusual Characteristic Detection Rules**:

**Rule 1: Multiple Operations**
- **Condition**: Characteristic has more than 3 properties
- **AND** characteristic has both "write" and "notify" properties
- **Result**: Marked as unusual with reason: "Multiple operations supported including write and notify"

**Rule 2: Unusually Long Values**
- **Condition**: Characteristic has a default value
- **AND** value is a string longer than 20 characters
- **Result**: Marked as unusual with reason: "Contains unusually long default value"

**Output Structure**:
```python
{
    "uuid": "2a00",
    "name": "Device Name",
    "properties": ["read", "write-without-response"],
    "security_concern": True,
    "security_reason": "Authentication-related characteristic allows write without response",
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

## Future Enhancement Opportunities

1. **Machine Learning Integration**: Train models on known vulnerabilities to improve detection accuracy
2. **Dynamic Rule Engine**: Allow rules to be configured or updated without code changes
3. **Threat Intelligence Integration**: Incorporate known CVEs and vulnerability databases
4. **Weighted Scoring**: Apply different weights to critical vs. non-critical characteristics in accessibility scoring
5. **Pattern Recognition**: Detect unusual patterns across multiple devices or over time
6. **Context-Aware Analysis**: Consider device type, manufacturer, and protocol version in analysis

