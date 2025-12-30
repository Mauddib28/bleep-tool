# Assets-of-Interest (AoI) Customization Guide

This guide explains how to customize the security assessment criteria used by the AoI Analyzer to match your specific security analysis needs.

## Overview

The AoI Analyzer uses configurable detection rules and analysis criteria. While the current implementation has hardcoded rules, this guide explains the analysis logic and provides patterns for extending or modifying the behavior.

## Current Analysis Criteria

### Service Notability Criteria

Services are marked as "notable" based on the following criteria:

**Core BLE Services**:
- UUID `1800` (Generic Access Profile)
- UUID `1801` (Generic Attribute Profile)

**Firmware Update Services**:
- Service name contains "OTA" (case-insensitive)
- Service name contains "dfu" (case-insensitive)

**Security Services**:
- Service name contains "auth" (case-insensitive)
- Service name contains "security" (case-insensitive)

### Security Concern Detection Criteria

Characteristics are flagged as security concerns when:

**Authentication Weakness Pattern**:
- Characteristic has `write-without-response` property
- **AND** characteristic name contains one of: "auth", "password", "key" (case-insensitive)

### Unusual Characteristic Detection Criteria

Characteristics are marked as unusual when:

**Pattern 1: Multiple Operations**:
- Characteristic has more than 3 properties
- **AND** characteristic has both "write" and "notify" properties

**Pattern 2: Unusually Long Values**:
- Characteristic has a default value
- **AND** value is a string longer than 20 characters

### Critical UUID Detection

Characteristics are considered critical when their name contains:
- "auth"
- "password"
- "key"
- "firmware"
- "dfu"
- "ota"
- "security"

### Accessibility Score Thresholds

**High Accessibility**: Score > 0.8
- Recommendation: Detailed enumeration recommended

**Low Accessibility**: Score < 0.3
- Recommendation: Consider authentication/pairing options

## Customization Patterns

### Pattern 1: Extending Service Notability Rules

To add new notable service patterns, modify `_analyse_service()` in `bleep/analysis/aoi_analyser.py`:

```python
def _analyse_service(self, uuid: str, service_info: Dict[str, Any]) -> Dict[str, Any]:
    service_report = {
        "uuid": uuid,
        "name": get_name_from_uuid(uuid),
        "is_primary": service_info.get("is_primary", False),
        "is_notable": False,
        "characteristics": service_info.get("characteristics", []),
    }
    
    # Existing rules...
    if uuid in ["1800", "1801"]:
        service_report["is_notable"] = True
        service_report["notable_reason"] = "Core BLE service"
    
    # Add your custom rule here:
    elif "custom_keyword" in service_report["name"].lower():
        service_report["is_notable"] = True
        service_report["notable_reason"] = "Custom notable service pattern"
    
    return service_report
```

### Pattern 2: Adding Security Concern Detection Rules

To add new security concern patterns, modify `_analyse_characteristic()`:

```python
def _analyse_characteristic(self, uuid: str, char_info: Dict[str, Any]) -> Dict[str, Any]:
    char_report = {
        "uuid": uuid,
        "name": get_name_from_uuid(uuid),
        "properties": char_info.get("properties", []),
        "security_concern": False,
        "is_unusual": False,
    }
    
    properties = char_info.get("properties", [])
    name_lower = char_report["name"].lower()
    
    # Existing rule...
    if "write-without-response" in properties and any(kw in name_lower for kw in ["auth", "password", "key"]):
        char_report["security_concern"] = True
        char_report["security_reason"] = "Authentication-related characteristic allows write without response"
    
    # Add your custom security rule:
    if "write" in properties and "encryption" not in properties and "admin" in name_lower:
        char_report["security_concern"] = True
        char_report["security_reason"] = "Admin characteristic allows write without encryption requirement"
    
    return char_report
```

### Pattern 3: Customizing Critical UUID Detection

To modify critical UUID keywords, update `_is_critical_uuid()`:

```python
def _is_critical_uuid(self, uuid: str) -> bool:
    name = get_name_from_uuid(uuid).lower()
    
    # Existing keywords
    critical_keywords = ["auth", "password", "key", "firmware", "dfu", "ota", "security"]
    
    # Add your custom keywords:
    custom_keywords = ["admin", "config", "control"]
    critical_keywords.extend(custom_keywords)
    
    return any(keyword in name for keyword in critical_keywords)
```

### Pattern 4: Adjusting Accessibility Score Thresholds

To modify accessibility score interpretation, update `_generate_recommendations()`:

```python
def _generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
    recommendations = []
    accessibility = report["summary"]["accessibility"]
    score = accessibility["accessibility_score"]
    
    # Customize thresholds:
    if score > 0.9:  # Changed from 0.8
        recommendations.append(
            f"Device is extremely accessible ({score:.2%}). "
            "Perform comprehensive security assessment."
        )
    elif score < 0.2:  # Changed from 0.3
        recommendations.append(
            f"Device has very limited accessibility ({score:.2%}). "
            "Authentication/pairing required for further analysis."
        )
    
    return recommendations
```

### Pattern 5: Adding Custom Unusual Characteristic Patterns

To add new unusual characteristic detection patterns:

```python
def _analyse_characteristic(self, uuid: str, char_info: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing code ...
    
    # Add custom unusual pattern:
    properties = char_info.get("properties", [])
    if "indicate" in properties and "write" in properties and "read" not in properties:
        char_report["is_unusual"] = True
        char_report["unusual_reason"] = "Write-only characteristic with indication (unusual pattern)"
    
    return char_report
```

## Advanced Customization: Subclassing AOIAnalyser

For more extensive customization, create a subclass of `AOIAnalyser`:

```python
from bleep.analysis.aoi_analyser import AOIAnalyser

class CustomAOIAnalyser(AOIAnalyser):
    """Custom AoI Analyzer with organization-specific rules."""
    
    def __init__(self, aoi_dir=None, use_db=True, custom_rules=None):
        super().__init__(aoi_dir, use_db)
        self.custom_rules = custom_rules or {}
    
    def _is_critical_uuid(self, uuid: str) -> bool:
        # Use custom rules if available
        if self.custom_rules.get("critical_keywords"):
            name = get_name_from_uuid(uuid).lower()
            return any(kw in name for kw in self.custom_rules["critical_keywords"])
        return super()._is_critical_uuid(uuid)
    
    def _analyse_characteristic(self, uuid: str, char_info: Dict[str, Any]) -> Dict[str, Any]:
        # Call parent method first
        char_report = super()._analyse_characteristic(uuid, char_info)
        
        # Apply custom rules
        if self.custom_rules.get("custom_security_check"):
            # Your custom security check logic here
            pass
        
        return char_report
```

## Configuration File Approach (Future Enhancement)

A future enhancement could support configuration files for rules:

```yaml
# aoi_rules.yaml
notable_services:
  core_ble:
    - "1800"  # GAP
    - "1801"  # GATT
  firmware_update:
    keywords: ["ota", "dfu"]
  security:
    keywords: ["auth", "security"]

security_concerns:
  authentication_weakness:
    properties: ["write-without-response"]
    name_keywords: ["auth", "password", "key"]
  
critical_characteristics:
  keywords: ["auth", "password", "key", "firmware", "dfu", "ota", "security"]

accessibility_thresholds:
  high: 0.8
  low: 0.3
```

## Use Case Examples

### Example 1: IoT Device Security Assessment

**Customization Needs**:
- Mark all characteristics with "sensor" in name as notable
- Flag characteristics with "calibration" and write permissions as security concerns
- Lower accessibility threshold for IoT devices (0.6 instead of 0.8)

**Implementation**:
```python
class IoTAOIAnalyser(AOIAnalyser):
    def _analyse_service(self, uuid, service_info):
        report = super()._analyse_service(uuid, service_info)
        if "sensor" in report["name"].lower():
            report["is_notable"] = True
            report["notable_reason"] = "IoT sensor service"
        return report
    
    def _analyse_characteristic(self, uuid, char_info):
        report = super()._analyse_characteristic(uuid, char_info)
        name_lower = report["name"].lower()
        properties = char_info.get("properties", [])
        
        if "calibration" in name_lower and "write" in properties:
            report["security_concern"] = True
            report["security_reason"] = "Calibration characteristic allows write access"
        
        return report
    
    def _generate_recommendations(self, report):
        recommendations = super()._generate_recommendations(report)
        accessibility = report["summary"]["accessibility"]
        score = accessibility["accessibility_score"]
        
        # Custom threshold for IoT
        if score > 0.6:  # Lower threshold
            recommendations.append(
                f"IoT device accessibility: {score:.2%}. "
                "Review sensor calibration and control characteristics."
            )
        
        return recommendations
```

### Example 2: Medical Device Compliance Assessment

**Customization Needs**:
- Mark all characteristics with "patient" or "medical" as critical
- Flag characteristics with "data" and no encryption requirement as security concerns
- Generate compliance-focused recommendations

**Implementation**:
```python
class MedicalDeviceAOIAnalyser(AOIAnalyser):
    def _is_critical_uuid(self, uuid: str) -> bool:
        name = get_name_from_uuid(uuid).lower()
        medical_keywords = ["patient", "medical", "health", "diagnostic"]
        return any(kw in name for kw in medical_keywords) or super()._is_critical_uuid(uuid)
    
    def _analyse_characteristic(self, uuid, char_info):
        report = super()._analyse_characteristic(uuid, char_info)
        name_lower = report["name"].lower()
        properties = char_info.get("properties", [])
        
        if "data" in name_lower and "write" in properties:
            # Check if encryption is required
            if "encryption" not in properties and "authenticated" not in properties:
                report["security_concern"] = True
                report["security_reason"] = "Medical data characteristic lacks encryption requirement (HIPAA concern)"
        
        return report
    
    def _generate_recommendations(self, report):
        recommendations = super()._generate_recommendations(report)
        
        # Add compliance-specific recommendations
        security_concerns = report["summary"]["security_concerns"]
        if security_concerns:
            recommendations.append(
                "Review HIPAA compliance: Ensure all patient data characteristics "
                "require encryption and authentication."
            )
        
        return recommendations
```

## Best Practices

1. **Document Custom Rules**: Always document why custom rules were added and what they detect
2. **Test Thoroughly**: Test custom rules against known devices to verify accuracy
3. **Maintain Backward Compatibility**: When subclassing, call parent methods first to preserve existing behavior
4. **Use Configuration When Possible**: Prefer configuration files over code changes for easier maintenance
5. **Version Control**: Track changes to analysis rules in version control
6. **Review Regularly**: Periodically review custom rules for false positives/negatives

## Integration with Existing Workflows

Custom analyzers can be integrated into existing AoI workflows:

```python
from bleep.analysis.aoi_analyser import AOIAnalyser
from my_custom_module import CustomAOIAnalyser

# Use custom analyzer
analyzer = CustomAOIAnalyser(use_db=True)
report = analyzer.analyse_device("00:11:22:33:44:55")
print(analyzer.generate_report(device_address="00:11:22:33:44:55"))
```

## Future Enhancement Roadmap

1. **Rule Configuration System**: YAML/JSON-based rule configuration
2. **Plugin Architecture**: Load custom analysis plugins at runtime
3. **Rule Testing Framework**: Unit tests for custom rules
4. **Rule Marketplace**: Share and distribute custom analysis rules
5. **Machine Learning Integration**: Learn from user feedback to improve rules

