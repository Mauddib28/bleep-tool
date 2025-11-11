"""Device Type Classifier - Evidence-based classification system for Bluetooth devices.

This module provides a comprehensive, stateless, mode-aware device type classification
system that determines whether a device is Classic, LE, dual-mode, or unknown based on
evidence collected from device properties and active queries.

Key Features:
- Stateless classification (no database dependency for decisions)
- Mode-aware evidence collection (passive/naggy/pokey/bruteforce)
- Database-first performance optimization (signature caching)
- Code reuse (leverages existing BLEEP functions)
- Strict dual-detection (requires conclusive evidence from both protocols)

Usage:
    from bleep.analysis.device_type_classifier import DeviceTypeClassifier
    
    classifier = DeviceTypeClassifier()
    result = classifier.classify_with_mode(
        mac="AA:BB:CC:DD:EE:FF",
        context={"device_class": 0x5a020c, "address_type": "random"},
        scan_mode="passive"
    )
    print(result.device_type)  # 'dual', 'classic', 'le', or 'unknown'
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
from bleep.core import constants


# ============================================================================
# Enums
# ============================================================================

class EvidenceType(Enum):
    """Types of evidence that can be collected for device classification."""
    
    # Classic Evidence
    CLASSIC_DEVICE_CLASS = "classic_device_class"
    CLASSIC_SDP_RECORDS = "classic_sdp_records"
    CLASSIC_SERVICE_UUIDS = "classic_service_uuids"
    
    # LE Evidence
    LE_ADDRESS_TYPE_RANDOM = "le_address_type_random"
    LE_ADDRESS_TYPE_PUBLIC = "le_address_type_public"
    LE_GATT_SERVICES = "le_gatt_services"
    LE_SERVICE_UUIDS = "le_service_uuids"
    LE_ADVERTISING_DATA = "le_advertising_data"


class EvidenceWeight(Enum):
    """Weight/confidence level of evidence."""
    
    CONCLUSIVE = "conclusive"  # Strong proof of capability
    STRONG = "strong"          # Strong indicator
    WEAK = "weak"              # Weak indicator
    INCONCLUSIVE = "inconclusive"  # Not useful for classification


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Evidence:
    """Single piece of evidence."""
    
    evidence_type: EvidenceType
    weight: EvidenceWeight
    source: str
    value: Any
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ClassificationResult:
    """Result of device type classification."""
    
    device_type: str  # 'unknown', 'classic', 'le', 'dual'
    confidence: float  # 0.0 to 1.0
    evidence_summary: Dict[str, List[str]]  # Evidence by type
    reasoning: str  # Human-readable explanation
    cached: bool = False  # Whether this was a cached result


# ============================================================================
# Evidence Set
# ============================================================================

class EvidenceSet:
    """Stores and queries collected evidence."""
    
    def __init__(self):
        self._evidence: Dict[EvidenceType, List[Evidence]] = {}
    
    def add(
        self,
        evidence_type: EvidenceType,
        weight: EvidenceWeight,
        source: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add evidence with weight and source information."""
        if evidence_type not in self._evidence:
            self._evidence[evidence_type] = []
        
        evidence = Evidence(
            evidence_type=evidence_type,
            weight=weight,
            source=source,
            value=value,
            metadata=metadata
        )
        self._evidence[evidence_type].append(evidence)
    
    def has(
        self,
        evidence_type: EvidenceType,
        weight: Optional[EvidenceWeight] = None
    ) -> bool:
        """Check if evidence of given type (and optionally weight) exists."""
        if evidence_type not in self._evidence:
            return False
        
        if weight is None:
            return len(self._evidence[evidence_type]) > 0
        
        return any(e.weight == weight for e in self._evidence[evidence_type])
    
    def get_weight(self, evidence_type: EvidenceType) -> Optional[EvidenceWeight]:
        """Get the highest weight evidence of given type."""
        if evidence_type not in self._evidence or not self._evidence[evidence_type]:
            return None
        
        weights_order = [
            EvidenceWeight.CONCLUSIVE,
            EvidenceWeight.STRONG,
            EvidenceWeight.WEAK,
            EvidenceWeight.INCONCLUSIVE
        ]
        
        for weight in weights_order:
            if any(e.weight == weight for e in self._evidence[evidence_type]):
                return weight
        
        return None
    
    def summarize(self) -> Dict[str, Any]:
        """Generate summary of all collected evidence."""
        summary = {}
        for evidence_type, evidence_list in self._evidence.items():
            summary[evidence_type.value] = [
                {
                    "weight": e.weight.value,
                    "source": e.source,
                    "value": str(e.value)[:100] if e.value else None
                }
                for e in evidence_list
            ]
        return summary


# ============================================================================
# Evidence Collectors (Abstract Base)
# ============================================================================

class EvidenceCollector(ABC):
    """Base class for evidence collectors."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this collector."""
        pass
    
    @property
    @abstractmethod
    def evidence_types(self) -> List[EvidenceType]:
        """List of evidence types this collector can provide."""
        pass
    
    @property
    @abstractmethod
    def supported_modes(self) -> List[str]:
        """List of scan modes this collector supports (passive, naggy, pokey, bruteforce)."""
        pass
    
    @abstractmethod
    def collect(
        self,
        mac: str,
        context: Dict[str, Any],
        evidence: EvidenceSet
    ) -> None:
        """
        Collect evidence and add to EvidenceSet.
        
        Args:
            mac: Device MAC address
            context: Context dictionary with available data (properties, device objects, etc.)
            evidence: EvidenceSet to add findings to
        """
        pass


# ============================================================================
# Default Evidence Collectors
# ============================================================================

class ClassicDeviceClassCollector(EvidenceCollector):
    """Collects Classic device class evidence."""
    
    @property
    def name(self) -> str:
        return "classic_device_class"
    
    @property
    def evidence_types(self) -> List[EvidenceType]:
        return [EvidenceType.CLASSIC_DEVICE_CLASS]
    
    @property
    def supported_modes(self) -> List[str]:
        return ["passive", "naggy", "pokey", "bruteforce"]  # Available from advertising/scan
    
    def collect(
        self,
        mac: str,
        context: Dict[str, Any],
        evidence: EvidenceSet
    ) -> None:
        """Collect device_class property (conclusive Classic evidence)."""
        device_class = context.get("device_class")
        if device_class is not None:
            evidence.add(
                EvidenceType.CLASSIC_DEVICE_CLASS,
                EvidenceWeight.CONCLUSIVE,
                "dbus_property",
                device_class,
                {"property": "Class"}
            )


class ClassicSDPRecordsCollector(EvidenceCollector):
    """Collects Classic SDP records evidence using existing SDP discovery functions."""
    
    @property
    def name(self) -> str:
        return "classic_sdp_records"
    
    @property
    def evidence_types(self) -> List[EvidenceType]:
        return [EvidenceType.CLASSIC_SDP_RECORDS]
    
    @property
    def supported_modes(self) -> List[str]:
        return ["pokey", "bruteforce"]  # Requires connection/query
    
    def collect(
        self,
        mac: str,
        context: Dict[str, Any],
        evidence: EvidenceSet
    ) -> None:
        """Collect SDP records using existing discover_services_sdp_connectionless function."""
        # Check if SDP records already in context (from previous queries)
        sdp_records = context.get("sdp_records")
        
        if sdp_records is None:
            # Try to get SDP records using existing function
            try:
                from bleep.ble_ops.classic_sdp import discover_services_sdp_connectionless
                sdp_records = discover_services_sdp_connectionless(mac)
            except Exception as e:
                print_and_log(
                    f"[device_type_classifier] SDP query failed for {mac}: {e}",
                    LOG__DEBUG
                )
                return
        
        if sdp_records and len(sdp_records) > 0:
            evidence.add(
                EvidenceType.CLASSIC_SDP_RECORDS,
                EvidenceWeight.CONCLUSIVE,
                "sdp_query",
                len(sdp_records),
                {"record_count": len(sdp_records)}
            )


class ClassicServiceUUIDsCollector(EvidenceCollector):
    """Collects Classic service UUIDs from advertising or connection."""
    
    @property
    def name(self) -> str:
        return "classic_service_uuids"
    
    @property
    def evidence_types(self) -> List[EvidenceType]:
        return [EvidenceType.CLASSIC_SERVICE_UUIDS]
    
    @property
    def supported_modes(self) -> List[str]:
        return ["passive", "naggy", "pokey", "bruteforce"]  # Available from advertising
    
    def collect(
        self,
        mac: str,
        context: Dict[str, Any],
        evidence: EvidenceSet
    ) -> None:
        """Collect Classic service UUIDs from UUIDs property using existing BLEEP constants."""
        from bleep.bt_ref import uuids as bt_uuids
        from bleep.ble_ops.uuid_utils import identify_uuid
        
        uuids_list = context.get("uuids", [])
        if not uuids_list:
            return
        
        # Get Classic profile UUIDs from existing BLEEP constants
        # SPEC_UUID_NAMES__SERV_CLASS contains Classic profile UUIDs (0x11xx range)
        classic_profile_uuids = getattr(bt_uuids, 'SPEC_UUID_NAMES__SERV_CLASS', {})
        
        if not classic_profile_uuids:
            # Fallback: If constants not available, log and return
            print_and_log(
                "[device_type_classifier] SPEC_UUID_NAMES__SERV_CLASS not available",
                LOG__DEBUG
            )
            return
        
        classic_uuids = []
        # Pre-normalize Classic profile UUIDs for efficient lookup
        classic_uuid_set = set()
        classic_short_uuids = set()
        for classic_uuid_key in classic_profile_uuids.keys():
            classic_normalized = classic_uuid_key.replace("-", "").lower()
            classic_uuid_set.add(classic_normalized)
            # Extract short form (positions 4-8, which is the 16-bit UUID part)
            if len(classic_normalized) >= 8:
                classic_short_uuids.add(classic_normalized[4:8])
        
        for uuid in uuids_list:
            uuid_str = str(uuid)
            
            # Normalize UUID using existing BLEEP utility
            uuid_forms = identify_uuid(uuid_str)
            
            # Check if any normalized form matches a Classic profile UUID
            matched = False
            for uuid_form in uuid_forms:
                # Normalize for comparison (remove dashes, lowercase, strip whitespace)
                normalized_form = uuid_form.replace("-", "").lower().strip()
                
                # Check full UUID match
                if normalized_form in classic_uuid_set:
                    classic_uuids.append(uuid_str)
                    matched = True
                    break
                
                # Check short UUID match (extract 16-bit part from full UUID or use as-is)
                if len(normalized_form) == 32:
                    # Full UUID - extract short form (positions 4-8)
                    short_form = normalized_form[4:8]
                    if short_form in classic_short_uuids:
                        classic_uuids.append(uuid_str)
                        matched = True
                        break
                elif len(normalized_form) == 4:
                    # Already a short UUID
                    if normalized_form in classic_short_uuids:
                        classic_uuids.append(uuid_str)
                        matched = True
                        break
            
            # Also check direct string matching as fallback
            if not matched:
                uuid_upper = uuid_str.upper().replace("-", "")
                for classic_uuid_key in classic_profile_uuids.keys():
                    classic_upper = classic_uuid_key.replace("-", "").upper()
                    if uuid_upper == classic_upper or (len(uuid_upper) == 4 and classic_upper.endswith(uuid_upper)):
                        classic_uuids.append(uuid_str)
                        break
        
        if classic_uuids:
            evidence.add(
                EvidenceType.CLASSIC_SERVICE_UUIDS,
                EvidenceWeight.STRONG,
                "dbus_property",
                classic_uuids,
                {"uuid_count": len(classic_uuids), "source": "SPEC_UUID_NAMES__SERV_CLASS"}
            )


class LEAddressTypeCollector(EvidenceCollector):
    """Collects LE address type evidence."""
    
    @property
    def name(self) -> str:
        return "le_address_type"
    
    @property
    def evidence_types(self) -> List[EvidenceType]:
        return [
            EvidenceType.LE_ADDRESS_TYPE_RANDOM,
            EvidenceType.LE_ADDRESS_TYPE_PUBLIC
        ]
    
    @property
    def supported_modes(self) -> List[str]:
        return ["passive", "naggy", "pokey", "bruteforce"]  # Available from advertising/scan
    
    def collect(
        self,
        mac: str,
        context: Dict[str, Any],
        evidence: EvidenceSet
    ) -> None:
        """Collect address_type property (conclusive LE if random, inconclusive if public)."""
        address_type = context.get("address_type")
        if address_type == "random":
            evidence.add(
                EvidenceType.LE_ADDRESS_TYPE_RANDOM,
                EvidenceWeight.CONCLUSIVE,
                "dbus_property",
                address_type,
                {"property": "AddressType"}
            )
        elif address_type == "public":
            # Public address type is inconclusive (default for Classic too)
            evidence.add(
                EvidenceType.LE_ADDRESS_TYPE_PUBLIC,
                EvidenceWeight.INCONCLUSIVE,
                "dbus_property",
                address_type,
                {"property": "AddressType", "note": "Default for Classic too"}
            )


class LEGATTServicesCollector(EvidenceCollector):
    """Collects LE GATT services evidence using existing GATT enumeration."""
    
    @property
    def name(self) -> str:
        return "le_gatt_services"
    
    @property
    def evidence_types(self) -> List[EvidenceType]:
        return [EvidenceType.LE_GATT_SERVICES]
    
    @property
    def supported_modes(self) -> List[str]:
        return ["naggy", "pokey", "bruteforce"]  # Requires connection
    
    def collect(
        self,
        mac: str,
        context: Dict[str, Any],
        evidence: EvidenceSet
    ) -> None:
        """Collect GATT services using existing device.services_resolved() method."""
        # Check if device is connected
        if not context.get("connected", False):
            return
        
        # Check if GATT services already in context
        gatt_services = context.get("gatt_services")
        
        if gatt_services is None:
            # Try to get GATT services using existing device object
            device = context.get("device")
            if device and hasattr(device, "services_resolved"):
                try:
                    gatt_services = device.services_resolved(skip_device_type_check=True)
                except Exception as e:
                    print_and_log(
                        f"[device_type_classifier] GATT enumeration failed for {mac}: {e}",
                        LOG__DEBUG
                    )
                    return
        
        if gatt_services and len(gatt_services) > 0:
            evidence.add(
                EvidenceType.LE_GATT_SERVICES,
                EvidenceWeight.STRONG,
                "gatt_enumeration",
                len(gatt_services),
                {"service_count": len(gatt_services)}
            )


class LEServiceUUIDsCollector(EvidenceCollector):
    """Collects LE service UUIDs from advertising or connection."""
    
    @property
    def name(self) -> str:
        return "le_service_uuids"
    
    @property
    def evidence_types(self) -> List[EvidenceType]:
        return [EvidenceType.LE_SERVICE_UUIDS]
    
    @property
    def supported_modes(self) -> List[str]:
        return ["passive", "naggy", "pokey", "bruteforce"]  # Available from advertising
    
    def collect(
        self,
        mac: str,
        context: Dict[str, Any],
        evidence: EvidenceSet
    ) -> None:
        """Collect GATT service UUIDs from UUIDs property using existing BLEEP constants."""
        from bleep.bt_ref import uuids as bt_uuids
        from bleep.ble_ops.uuid_utils import identify_uuid
        
        uuids_list = context.get("uuids", [])
        if not uuids_list:
            return
        
        # Get GATT service UUIDs from existing BLEEP constants
        # SPEC_UUID_NAMES__SERV contains GATT service UUIDs (0x18xx range)
        gatt_service_uuids = getattr(bt_uuids, 'SPEC_UUID_NAMES__SERV', {})
        
        if not gatt_service_uuids:
            # Fallback: If constants not available, log and return
            print_and_log(
                "[device_type_classifier] SPEC_UUID_NAMES__SERV not available",
                LOG__DEBUG
            )
            return
        
        gatt_uuids = []
        # Pre-normalize GATT service UUIDs for efficient lookup
        gatt_uuid_set = set()
        gatt_short_uuids = set()
        for gatt_uuid_key in gatt_service_uuids.keys():
            gatt_normalized = gatt_uuid_key.replace("-", "").lower()
            gatt_uuid_set.add(gatt_normalized)
            # Extract short form (positions 4-8, which is the 16-bit UUID part)
            if len(gatt_normalized) >= 8:
                gatt_short_uuids.add(gatt_normalized[4:8])
        
        for uuid in uuids_list:
            uuid_str = str(uuid)
            
            # Normalize UUID using existing BLEEP utility
            uuid_forms = identify_uuid(uuid_str)
            
            # Check if any normalized form matches a GATT service UUID
            matched = False
            for uuid_form in uuid_forms:
                # Normalize for comparison (remove dashes, lowercase, strip whitespace)
                normalized_form = uuid_form.replace("-", "").lower().strip()
                
                # Check full UUID match
                if normalized_form in gatt_uuid_set:
                    gatt_uuids.append(uuid_str)
                    matched = True
                    break
                
                # Check short UUID match (extract 16-bit part from full UUID or use as-is)
                if len(normalized_form) == 32:
                    # Full UUID - extract short form (positions 4-8)
                    short_form = normalized_form[4:8]
                    if short_form in gatt_short_uuids:
                        gatt_uuids.append(uuid_str)
                        matched = True
                        break
                elif len(normalized_form) == 4:
                    # Already a short UUID
                    if normalized_form in gatt_short_uuids:
                        gatt_uuids.append(uuid_str)
                        matched = True
                        break
            
            # Also check direct string matching as fallback
            if not matched:
                uuid_upper = uuid_str.upper().replace("-", "")
                for gatt_uuid_key in gatt_service_uuids.keys():
                    gatt_upper = gatt_uuid_key.replace("-", "").upper()
                    if uuid_upper == gatt_upper or (len(uuid_upper) == 4 and gatt_upper.endswith(uuid_upper)):
                        gatt_uuids.append(uuid_str)
                        break
        
        if gatt_uuids:
            evidence.add(
                EvidenceType.LE_SERVICE_UUIDS,
                EvidenceWeight.STRONG,
                "dbus_property",
                gatt_uuids,
                {"uuid_count": len(gatt_uuids), "source": "SPEC_UUID_NAMES__SERV"}
            )


class LEAdvertisingDataCollector(EvidenceCollector):
    """Collects LE advertising data evidence."""
    
    @property
    def name(self) -> str:
        return "le_advertising_data"
    
    @property
    def evidence_types(self) -> List[EvidenceType]:
        return [EvidenceType.LE_ADVERTISING_DATA]
    
    @property
    def supported_modes(self) -> List[str]:
        return ["passive", "naggy"]  # Available from scan
    
    def collect(
        self,
        mac: str,
        context: Dict[str, Any],
        evidence: EvidenceSet
    ) -> None:
        """Collect advertising data (weak LE evidence)."""
        advertising_data = context.get("advertising_data")
        if advertising_data:
            evidence.add(
                EvidenceType.LE_ADVERTISING_DATA,
                EvidenceWeight.WEAK,
                "dbus_property",
                advertising_data,
                {"property": "AdvertisingData"}
            )


# ============================================================================
# Main Classifier
# ============================================================================

class DeviceTypeClassifier:
    """Main device type classifier with mode-aware evidence collection and caching."""
    
    def __init__(self):
        self._collectors: List[EvidenceCollector] = []
        self._register_default_collectors()
    
    def _register_default_collectors(self) -> None:
        """Register default evidence collectors."""
        self._collectors = [
            ClassicDeviceClassCollector(),
            ClassicSDPRecordsCollector(),
            ClassicServiceUUIDsCollector(),
            LEAddressTypeCollector(),
            LEGATTServicesCollector(),
            LEServiceUUIDsCollector(),
            LEAdvertisingDataCollector(),
        ]
    
    def register_collector(self, collector: EvidenceCollector) -> None:
        """Register a new evidence collector (extensibility point)."""
        self._collectors.append(collector)
    
    def classify_with_mode(
        self,
        mac: str,
        context: Dict[str, Any],
        scan_mode: str = "passive",
        use_database_cache: bool = True
    ) -> ClassificationResult:
        """
        Classify device type with mode-aware evidence collection and database caching.
        
        Args:
            mac: Device MAC address
            context: Available device properties/context
            scan_mode: Scan mode ('passive', 'naggy', 'pokey', 'bruteforce')
            use_database_cache: If True, check database signature first
        
        Returns:
            ClassificationResult with device type and confidence
        """
        # Step 1: Database signature check (performance optimization)
        if use_database_cache:
            cached_result = self._check_database_signature(mac, context, scan_mode)
            if cached_result:
                return cached_result
        
        # Step 2: Collect evidence based on scan mode
        evidence = self.collect_evidence(mac, context, scan_mode)
        
        # Step 3: Classify based on evidence
        result = self.classify(evidence)
        
        # Step 4: Store evidence in database for future cache hits
        if use_database_cache:
            self._store_evidence_signature(mac, evidence, result)
        
        return result
    
    def collect_evidence(
        self,
        mac: str,
        context: Dict[str, Any],
        scan_mode: str = "passive"
    ) -> EvidenceSet:
        """
        Collect evidence based on scan mode capabilities.
        
        Scan Mode Capabilities:
        - passive: Only advertising data (AddressType, UUIDs from advertising, device_class)
        - naggy: Passive + connection attempt (can get GATT services if connected)
        - pokey: Naggy + extended timeouts (can do SDP queries if Classic)
        - bruteforce: Pokey + aggressive queries (full SDP, full GATT enumeration)
        """
        evidence = EvidenceSet()
        
        # Filter collectors based on scan mode
        active_collectors = self._get_collectors_for_mode(scan_mode)
        
        for collector in active_collectors:
            try:
                collector.collect(mac, context, evidence)
            except Exception as e:
                # Log but continue - don't fail entire classification
                print_and_log(
                    f"[device_type_classifier] Collector {collector.name} failed: {e}",
                    LOG__DEBUG
                )
        
        return evidence
    
    def _get_collectors_for_mode(self, scan_mode: str) -> List[EvidenceCollector]:
        """Return collectors appropriate for the scan mode."""
        if scan_mode == "passive":
            # Only use collectors that work with advertising data
            return [
                c for c in self._collectors
                if c.name in [
                    "classic_device_class",
                    "classic_service_uuids",
                    "le_address_type",
                    "le_service_uuids",
                    "le_advertising_data"
                ]
            ]
        elif scan_mode == "naggy":
            # Passive + connection-based collectors
            return [
                c for c in self._collectors
                if c.name not in ["classic_sdp_records"]  # Too aggressive for naggy
            ]
        elif scan_mode in ["pokey", "bruteforce"]:
            # All collectors available
            return self._collectors
        else:
            # Default to passive
            return self._get_collectors_for_mode("passive")
    
    def classify(self, evidence: EvidenceSet) -> ClassificationResult:
        """Classify device type based on collected evidence."""
        # Check for dual-mode (strict requirement)
        if self._classify_dual(evidence):
            return ClassificationResult(
                device_type=constants.BT_DEVICE_TYPE_DUAL,
                confidence=self._calculate_confidence(evidence, "dual"),
                evidence_summary=evidence.summarize(),
                reasoning=self._generate_reasoning(evidence, "dual")
            )
        
        # Check for Classic
        if self._classify_classic(evidence):
            return ClassificationResult(
                device_type=constants.BT_DEVICE_TYPE_CLASSIC,
                confidence=self._calculate_confidence(evidence, "classic"),
                evidence_summary=evidence.summarize(),
                reasoning=self._generate_reasoning(evidence, "classic")
            )
        
        # Check for LE
        if self._classify_le(evidence):
            return ClassificationResult(
                device_type=constants.BT_DEVICE_TYPE_LE,
                confidence=self._calculate_confidence(evidence, "le"),
                evidence_summary=evidence.summarize(),
                reasoning=self._generate_reasoning(evidence, "le")
            )
        
        # Default to unknown
        return ClassificationResult(
            device_type=constants.BT_DEVICE_TYPE_UNKNOWN,
            confidence=0.0,
            evidence_summary=evidence.summarize(),
            reasoning="Not enough evidence to determine device type"
        )
    
    def _classify_dual(self, evidence: EvidenceSet) -> bool:
        """
        Strict dual-detection: Requires CONCLUSIVE evidence from BOTH protocols.
        
        **CRITICAL: Classification is STATELESS - based ONLY on current device state.**
        **NO database queries are used for classification decisions.**
        
        Classic Evidence (at least ONE required):
        - CONCLUSIVE: device_class present OR SDP records available
        - OR STRONG: Classic service UUIDs present (from current device properties)
        
        LE Evidence (at least ONE required):
        - CONCLUSIVE: addr_type="random" OR GATT services successfully resolved
        - OR STRONG: GATT service UUIDs present AND GATT services resolved (from current device state)
        
        Both must be satisfied for "dual" classification.
        """
        classic_conclusive = (
            evidence.has(EvidenceType.CLASSIC_DEVICE_CLASS, weight=EvidenceWeight.CONCLUSIVE) or
            evidence.has(EvidenceType.CLASSIC_SDP_RECORDS, weight=EvidenceWeight.CONCLUSIVE)
        )
        
        classic_strong = (
            evidence.has(EvidenceType.CLASSIC_SERVICE_UUIDS, weight=EvidenceWeight.STRONG)
        )
        
        le_conclusive = (
            evidence.has(EvidenceType.LE_ADDRESS_TYPE_RANDOM, weight=EvidenceWeight.CONCLUSIVE) or
            evidence.has(EvidenceType.LE_GATT_SERVICES, weight=EvidenceWeight.STRONG)
        )
        
        le_strong = (
            evidence.has(EvidenceType.LE_GATT_SERVICES, weight=EvidenceWeight.STRONG) and
            evidence.has(EvidenceType.LE_SERVICE_UUIDS, weight=EvidenceWeight.STRONG)
        )
        
        has_classic = classic_conclusive or classic_strong
        has_le = le_conclusive or le_strong
        
        return has_classic and has_le
    
    def _classify_classic(self, evidence: EvidenceSet) -> bool:
        """Classify as Classic if conclusive or strong Classic evidence exists."""
        return (
            evidence.has(EvidenceType.CLASSIC_DEVICE_CLASS, weight=EvidenceWeight.CONCLUSIVE) or
            evidence.has(EvidenceType.CLASSIC_SDP_RECORDS, weight=EvidenceWeight.CONCLUSIVE) or
            evidence.has(EvidenceType.CLASSIC_SERVICE_UUIDS, weight=EvidenceWeight.STRONG)
        )
    
    def _classify_le(self, evidence: EvidenceSet) -> bool:
        """Classify as LE if conclusive or strong LE evidence exists."""
        return (
            evidence.has(EvidenceType.LE_ADDRESS_TYPE_RANDOM, weight=EvidenceWeight.CONCLUSIVE) or
            evidence.has(EvidenceType.LE_GATT_SERVICES, weight=EvidenceWeight.STRONG) or
            (
                evidence.has(EvidenceType.LE_SERVICE_UUIDS, weight=EvidenceWeight.STRONG) and
                evidence.has(EvidenceType.LE_GATT_SERVICES, weight=EvidenceWeight.STRONG)
            )
        )
    
    def _calculate_confidence(self, evidence: EvidenceSet, device_type: str) -> float:
        """Calculate confidence score (0.0 to 1.0) based on evidence quality."""
        conclusive_count = sum(
            1 for ev_type in EvidenceType
            if evidence.has(ev_type, weight=EvidenceWeight.CONCLUSIVE)
        )
        strong_count = sum(
            1 for ev_type in EvidenceType
            if evidence.has(ev_type, weight=EvidenceWeight.STRONG)
        )
        weak_count = sum(
            1 for ev_type in EvidenceType
            if evidence.has(ev_type, weight=EvidenceWeight.WEAK)
        )
        
        # Weighted confidence calculation
        confidence = (
            conclusive_count * 0.5 +
            strong_count * 0.3 +
            weak_count * 0.1
        )
        
        # Cap at 1.0
        return min(confidence, 1.0)
    
    def _generate_reasoning(self, evidence: EvidenceSet, device_type: str) -> str:
        """Generate human-readable reasoning for classification."""
        reasons = []
        
        if evidence.has(EvidenceType.CLASSIC_DEVICE_CLASS, weight=EvidenceWeight.CONCLUSIVE):
            reasons.append("Classic device class present")
        if evidence.has(EvidenceType.CLASSIC_SDP_RECORDS, weight=EvidenceWeight.CONCLUSIVE):
            reasons.append("SDP records available")
        if evidence.has(EvidenceType.CLASSIC_SERVICE_UUIDS, weight=EvidenceWeight.STRONG):
            reasons.append("Classic service UUIDs detected")
        
        if evidence.has(EvidenceType.LE_ADDRESS_TYPE_RANDOM, weight=EvidenceWeight.CONCLUSIVE):
            reasons.append("LE random address type")
        if evidence.has(EvidenceType.LE_GATT_SERVICES, weight=EvidenceWeight.STRONG):
            reasons.append("GATT services resolved")
        if evidence.has(EvidenceType.LE_SERVICE_UUIDS, weight=EvidenceWeight.STRONG):
            reasons.append("GATT service UUIDs detected")
        
        if reasons:
            return f"Classified as {device_type} based on: {', '.join(reasons)}"
        else:
            return f"Classified as {device_type} (insufficient evidence)"
    
    def _check_database_signature(
        self,
        mac: str,
        context: Dict[str, Any],
        scan_mode: str
    ) -> Optional[ClassificationResult]:
        """
        Check if device signature matches database entry.
        
        Returns cached classification if:
        - Device exists in database
        - Current evidence matches stored signature within tolerance
        - Stored classification is not 'unknown'
        
        Returns None if:
        - Device not in database
        - Evidence signature changed significantly
        - Need full classification
        """
        try:
            from bleep.core.observations import get_device_detail
            
            device_detail = get_device_detail(mac)
            if not device_detail or not device_detail.get('device'):
                return None  # Device not in database
            
            stored_device = device_detail['device']
            stored_type = stored_device.get('device_type')
            
            # Don't use cache if stored type is unknown
            if not stored_type or stored_type == constants.BT_DEVICE_TYPE_UNKNOWN:
                return None
            
            # Build current evidence signature
            current_sig = self._build_evidence_signature(context, scan_mode)
            
            # Get stored signature from evidence table
            from bleep.core.observations import get_device_evidence_signature
            
            stored_sig = get_device_evidence_signature(mac)
            
            # If no stored signature exists, fall back to simple device property comparison
            if stored_sig is None:
                stored_sig = {
                    'device_class': stored_device.get('device_class'),
                    'address_type': stored_device.get('addr_type'),
                }
            
            # Compare signatures
            if self._signatures_match(current_sig, stored_sig, tolerance=0.8):
                # Signatures match - use cached result
                similarity = self._signature_similarity(current_sig, stored_sig)
                return ClassificationResult(
                    device_type=stored_type,
                    confidence=0.9,  # High confidence for cached match
                    evidence_summary={},
                    reasoning=f"Cached classification (signature match: {similarity:.2f})",
                    cached=True
                )
            
            # Signatures don't match - need full classification
            return None
            
        except Exception as e:
            print_and_log(
                f"[device_type_classifier] Database signature check failed: {e}",
                LOG__DEBUG
            )
            return None
    
    def _build_evidence_signature(
        self,
        context: Dict[str, Any],
        scan_mode: str
    ) -> Dict[str, Any]:
        """
        Build a signature from current evidence for comparison.
        
        Signature includes:
        - device_class (if available)
        - address_type (if available)
        - UUIDs hash (for privacy - hash of UUID list)
        - scan_mode (affects available evidence)
        """
        uuids = context.get("uuids", [])
        uuid_hash = None
        if uuids:
            uuid_str = "|".join(sorted(str(u).upper() for u in uuids))
            uuid_hash = hashlib.md5(uuid_str.encode()).hexdigest()[:8]
        
        sig = {
            'scan_mode': scan_mode,
            'device_class': context.get('device_class'),
            'address_type': context.get('address_type'),
            'has_classic_uuids': bool(self._has_classic_uuids(uuids)),
            'has_le_uuids': bool(self._has_le_uuids(uuids)),
            'uuid_hash': uuid_hash,
        }
        return sig
    
    def _has_classic_uuids(self, uuids: List[str]) -> bool:
        """Check if UUIDs list contains Classic service patterns using existing BLEEP constants."""
        from bleep.bt_ref import uuids as bt_uuids
        from bleep.ble_ops.uuid_utils import identify_uuid
        
        classic_profile_uuids = getattr(bt_uuids, 'SPEC_UUID_NAMES__SERV_CLASS', {})
        if not classic_profile_uuids:
            return False
        
        # Pre-normalize for efficient lookup
        classic_uuid_set = set()
        classic_short_uuids = set()
        for classic_uuid_key in classic_profile_uuids.keys():
            classic_normalized = classic_uuid_key.replace("-", "").lower()
            classic_uuid_set.add(classic_normalized)
            if len(classic_normalized) >= 8:
                classic_short_uuids.add(classic_normalized[4:8])
        
        for uuid in uuids:
            uuid_str = str(uuid)
            uuid_forms = identify_uuid(uuid_str)
            
            for uuid_form in uuid_forms:
                normalized_form = uuid_form.replace("-", "").lower().strip()
                
                # Check full UUID match
                if normalized_form in classic_uuid_set:
                    return True
                
                # Check short UUID match
                if len(normalized_form) == 32:
                    short_form = normalized_form[4:8]
                    if short_form in classic_short_uuids:
                        return True
                elif len(normalized_form) == 4:
                    if normalized_form in classic_short_uuids:
                        return True
        return False
    
    def _has_le_uuids(self, uuids: List[str]) -> bool:
        """Check if UUIDs list contains GATT service patterns using existing BLEEP constants."""
        from bleep.bt_ref import uuids as bt_uuids
        from bleep.ble_ops.uuid_utils import identify_uuid
        
        gatt_service_uuids = getattr(bt_uuids, 'SPEC_UUID_NAMES__SERV', {})
        if not gatt_service_uuids:
            return False
        
        # Pre-normalize for efficient lookup
        gatt_uuid_set = set()
        gatt_short_uuids = set()
        for gatt_uuid_key in gatt_service_uuids.keys():
            gatt_normalized = gatt_uuid_key.replace("-", "").lower()
            gatt_uuid_set.add(gatt_normalized)
            if len(gatt_normalized) >= 8:
                gatt_short_uuids.add(gatt_normalized[4:8])
        
        for uuid in uuids:
            uuid_str = str(uuid)
            uuid_forms = identify_uuid(uuid_str)
            
            for uuid_form in uuid_forms:
                normalized_form = uuid_form.replace("-", "").lower().strip()
                
                # Check full UUID match
                if normalized_form in gatt_uuid_set:
                    return True
                
                # Check short UUID match
                if len(normalized_form) == 32:
                    short_form = normalized_form[4:8]
                    if short_form in gatt_short_uuids:
                        return True
                elif len(normalized_form) == 4:
                    if normalized_form in gatt_short_uuids:
                        return True
        return False
    
    def _signatures_match(
        self,
        current: Dict[str, Any],
        stored: Dict[str, Any],
        tolerance: float = 0.8
    ) -> bool:
        """Check if signatures match within tolerance."""
        # Compare key signature elements
        matches = 0
        total = 0
        
        for key in ['device_class', 'address_type', 'has_classic_uuids', 'has_le_uuids']:
            total += 1
            if current.get(key) == stored.get(key):
                matches += 1
        
        similarity = matches / total if total > 0 else 0.0
        return similarity >= tolerance
    
    def _signature_similarity(
        self,
        current: Dict[str, Any],
        stored: Dict[str, Any]
    ) -> float:
        """Calculate similarity score between signatures (0.0 to 1.0)."""
        matches = 0
        total = 0
        
        for key in ['device_class', 'address_type', 'has_classic_uuids', 'has_le_uuids']:
            total += 1
            if current.get(key) == stored.get(key):
                matches += 1
        
        return matches / total if total > 0 else 0.0
    
    def _store_evidence_signature(
        self,
        mac: str,
        evidence: EvidenceSet,
        result: ClassificationResult
    ) -> None:
        """
        Store evidence signature in database for future cache hits and audit trail.
        
        **Note:** Evidence is stored for audit/debugging purposes only. Classification
        decisions are stateless and based only on current device state.
        """
        try:
            from bleep.core.observations import store_device_type_evidence
            
            # Store each piece of evidence in the database
            for evidence_type, evidence_list in evidence._evidence.items():
                for ev in evidence_list:
                    store_device_type_evidence(
                        mac=mac,
                        evidence_type=ev.evidence_type.value,
                        evidence_weight=ev.weight.value,
                        source=ev.source,
                        value=ev.value,
                        metadata=ev.metadata
                    )
            
            # Also store the classification result as metadata
            # This helps with debugging and understanding classification decisions
            store_device_type_evidence(
                mac=mac,
                evidence_type="classification_result",
                evidence_weight="inconclusive",  # Not used for classification
                source="device_type_classifier",
                value=result.device_type,
                metadata={
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                    "cached": result.cached
                }
            )
            
        except Exception as e:
            # Don't fail classification if evidence storage fails
            print_and_log(
                f"[device_type_classifier] Failed to store evidence for {mac}: {e}",
                LOG__DEBUG
            )


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    'DeviceTypeClassifier',
    'EvidenceType',
    'EvidenceWeight',
    'EvidenceSet',
    'ClassificationResult',
    'EvidenceCollector',
]

