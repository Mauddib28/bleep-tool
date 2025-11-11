"""bleep.analysis.sdp_analyzer – Comprehensive SDP record analysis and version inference.

This module provides advanced analysis of Bluetooth Classic SDP records, including:
- Comprehensive attribute extraction
- Protocol descriptor analysis (L2CAP, RFCOMM, BNEP, etc.)
- Advanced version inference
- Anomaly detection
- Service relationship analysis
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict
import re

from bleep.ble_ops.classic_version import map_profile_version_to_spec, map_lmp_version_to_spec
from bleep.core.log import print_and_log, LOG__DEBUG

__all__ = [
    "SDPAnalyzer",
    "analyze_sdp_records",
    "infer_bluetooth_spec_version",
    "detect_version_anomalies",
]

# SDP Attribute IDs (from Bluetooth Core Specification)
SDP_ATTR_SERVICE_RECORD_HANDLE = 0x0000
SDP_ATTR_SERVICE_CLASS_ID_LIST = 0x0001
SDP_ATTR_SERVICE_RECORD_STATE = 0x0002
SDP_ATTR_SERVICE_ID = 0x0003
SDP_ATTR_PROTOCOL_DESCRIPTOR_LIST = 0x0004
SDP_ATTR_BROWSE_GROUP_LIST = 0x0005
SDP_ATTR_LANGUAGE_BASE_ATTRIBUTE_ID_LIST = 0x0006
SDP_ATTR_SERVICE_INFO_TIME_TO_LIVE = 0x0007
SDP_ATTR_SERVICE_AVAILABILITY = 0x0008
SDP_ATTR_BLUETOOTH_PROFILE_DESCRIPTOR_LIST = 0x0009
SDP_ATTR_DOCUMENTATION_URL = 0x000A
SDP_ATTR_CLIENT_EXECUTABLE_URL = 0x000B
SDP_ATTR_ICON_URL = 0x000C
SDP_ATTR_SERVICE_NAME = 0x0100
SDP_ATTR_SERVICE_DESCRIPTION = 0x0101
SDP_ATTR_PROVIDER_NAME = 0x0102
SDP_ATTR_SERVICE_VERSION = 0x0300

# Protocol UUIDs (from Bluetooth Assigned Numbers)
PROTOCOL_L2CAP = "0x0100"
PROTOCOL_RFCOMM = "0x0003"
PROTOCOL_BNEP = "0x000F"
PROTOCOL_AVDTP = "0x0019"
PROTOCOL_AVCTP = "0x0017"
PROTOCOL_OBEX = "0x0008"
PROTOCOL_IP = "0x0800"
PROTOCOL_UDP = "0x0801"
PROTOCOL_TCP = "0x0802"

# Known profile UUIDs for version inference
PROFILE_VERSION_MAP: Dict[str, Dict[int, str]] = {
    "0x1101": {256: "1.0", 257: "1.1"},  # Serial Port Profile
    "0x1103": {256: "1.0", 257: "1.1"},  # Dial-up Networking
    "0x1105": {256: "1.0", 512: "1.1", 513: "1.2"},  # Object Push Profile
    "0x1106": {256: "1.0", 512: "1.1"},  # File Transfer Profile
    "0x110A": {256: "1.0", 512: "1.1"},  # Audio/Video Remote Control Profile
    "0x110B": {256: "1.0", 512: "1.1", 513: "1.2", 514: "1.3"},  # Advanced Audio Distribution Profile
    "0x110C": {256: "1.0", 512: "1.1"},  # Advanced Audio/Video Remote Control Profile
    "0x110E": {256: "1.0", 512: "1.1"},  # Headset Profile
    "0x1112": {256: "1.0", 512: "1.1", 513: "1.2", 514: "1.3", 515: "1.4", 516: "1.5", 517: "1.6"},  # Hands-Free Profile
    "0x1115": {256: "1.0", 512: "1.1"},  # Personal Area Networking Profile
    "0x111F": {256: "1.0", 512: "1.1", 513: "1.2", 514: "1.3", 515: "1.4", 516: "1.5", 517: "1.6"},  # Hands-Free Audio Gateway
    "0x112F": {256: "1.0", 512: "1.1"},  # Phone Book Access Profile
}


class SDPAnalyzer:
    """Comprehensive SDP record analyzer with version inference and anomaly detection."""
    
    def __init__(self, records: List[Dict[str, Any]]):
        """Initialize analyzer with SDP records.
        
        Parameters
        ----------
        records : List[Dict[str, Any]]
            List of SDP records from discover_services_sdp()
        """
        self.records = records
        self.analysis: Dict[str, Any] = {}
        self._protocols: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._profiles: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._version_hints: List[Tuple[str, Optional[str]]] = []
        
    def analyze(self) -> Dict[str, Any]:
        """Perform comprehensive analysis of SDP records.
        
        Returns
        -------
        Dict[str, Any]
            Comprehensive analysis results including:
            - protocol_analysis: Protocol usage breakdown
            - profile_analysis: Profile version analysis
            - version_inference: Inferred Bluetooth spec version
            - anomalies: Detected version inconsistencies
            - service_relationships: Service dependencies and groupings
            - comprehensive_attributes: All extracted attributes
        """
        self.analysis = {
            "total_records": len(self.records),
            "protocol_analysis": self._analyze_protocols(),
            "profile_analysis": self._analyze_profiles(),
            "version_inference": self._infer_version(),
            "anomalies": self._detect_anomalies(),
            "service_relationships": self._analyze_relationships(),
            "comprehensive_attributes": self._extract_all_attributes(),
        }
        return self.analysis
    
    def _analyze_protocols(self) -> Dict[str, Any]:
        """Analyze protocol descriptor usage across all records."""
        protocol_usage: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        for rec in self.records:
            # Extract RFCOMM channel if present
            if rec.get("channel") is not None:
                protocol_usage["RFCOMM"].append({
                    "service": rec.get("name", "Unknown"),
                    "uuid": rec.get("uuid"),
                    "channel": rec.get("channel"),
                    "handle": rec.get("handle"),
                })
            
            # Check for other protocols in raw data
            raw = rec.get("raw", "")
            if "L2CAP" in raw.upper():
                protocol_usage["L2CAP"].append({
                    "service": rec.get("name", "Unknown"),
                    "uuid": rec.get("uuid"),
                    "handle": rec.get("handle"),
                })
            if "BNEP" in raw.upper():
                protocol_usage["BNEP"].append({
                    "service": rec.get("name", "Unknown"),
                    "uuid": rec.get("uuid"),
                    "handle": rec.get("handle"),
                })
            if "OBEX" in raw.upper():
                protocol_usage["OBEX"].append({
                    "service": rec.get("name", "Unknown"),
                    "uuid": rec.get("uuid"),
                    "handle": rec.get("handle"),
                })
        
        return {
            "protocols_found": list(protocol_usage.keys()),
            "usage": dict(protocol_usage),
            "rfcomm_channels": [p["channel"] for p in protocol_usage.get("RFCOMM", []) if "channel" in p],
        }
    
    def _analyze_profiles(self) -> Dict[str, Any]:
        """Analyze profile versions and infer Bluetooth spec versions."""
        profile_stats: Dict[str, Dict[str, Any]] = {}
        version_distribution: Dict[str, int] = defaultdict(int)
        
        for rec in self.records:
            if rec.get("profile_descriptors"):
                for profile in rec.get("profile_descriptors", []):
                    uuid = profile.get("uuid", "Unknown")
                    version = profile.get("version")
                    
                    if uuid not in profile_stats:
                        profile_stats[uuid] = {
                            "uuid": uuid,
                            "versions": [],
                            "services": [],
                            "spec_hints": [],
                        }
                    
                    profile_stats[uuid]["versions"].append(version)
                    profile_stats[uuid]["services"].append(rec.get("name", "Unknown"))
                    
                    # Get spec version hint
                    spec_hint = map_profile_version_to_spec(version)
                    if spec_hint:
                        profile_stats[uuid]["spec_hints"].append(spec_hint)
                        version_distribution[spec_hint] += 1
        
        return {
            "profiles": profile_stats,
            "version_distribution": dict(version_distribution),
            "unique_profiles": len(profile_stats),
        }
    
    def _infer_version(self) -> Dict[str, Any]:
        """Infer Bluetooth Core Specification version from profile versions."""
        version_evidence: Dict[str, List[str]] = defaultdict(list)
        confidence_scores: Dict[str, float] = {}
        
        # Collect evidence from profile versions
        for rec in self.records:
            if rec.get("profile_descriptors"):
                for profile in rec.get("profile_descriptors", []):
                    uuid = profile.get("uuid")
                    version = profile.get("version")
                    
                    if uuid and version:
                        spec_hint = map_profile_version_to_spec(version)
                        if spec_hint:
                            version_evidence[spec_hint].append(f"{uuid}:v{version}")
        
        # Calculate confidence scores
        total_evidence = sum(len(ev) for ev in version_evidence.values())
        for spec_version, evidence in version_evidence.items():
            if total_evidence > 0:
                confidence_scores[spec_version] = len(evidence) / total_evidence
        
        # Determine most likely version
        most_likely = max(confidence_scores.items(), key=lambda x: x[1]) if confidence_scores else (None, 0.0)
        
        return {
            "inferred_version": most_likely[0],
            "confidence": most_likely[1],
            "evidence": dict(version_evidence),
            "confidence_scores": confidence_scores,
        }
    
    def _detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect version inconsistencies and anomalies."""
        anomalies: List[Dict[str, Any]] = []
        
        # Check for version inconsistencies across profiles
        profile_versions: Dict[str, Set[int]] = defaultdict(set)
        for rec in self.records:
            if rec.get("profile_descriptors"):
                for profile in rec.get("profile_descriptors", []):
                    uuid = profile.get("uuid")
                    version = profile.get("version")
                    if uuid and version:
                        profile_versions[uuid].add(version)
        
        # Detect multiple versions of same profile
        for uuid, versions in profile_versions.items():
            if len(versions) > 1:
                anomalies.append({
                    "type": "multiple_profile_versions",
                    "severity": "medium",
                    "description": f"Profile {uuid} has multiple versions: {sorted(versions)}",
                    "uuid": uuid,
                    "versions": sorted(versions),
                })
        
        # Check for unusual profile versions
        for rec in self.records:
            if rec.get("profile_descriptors"):
                for profile in rec.get("profile_descriptors", []):
                    uuid = profile.get("uuid")
                    version = profile.get("version")
                    
                    if uuid and version:
                        # Check if version is in known range for this profile
                        if uuid in PROFILE_VERSION_MAP:
                            known_versions = PROFILE_VERSION_MAP[uuid]
                            if version not in known_versions:
                                anomalies.append({
                                    "type": "unusual_profile_version",
                                    "severity": "low",
                                    "description": f"Profile {uuid} has unusual version {version}",
                                    "uuid": uuid,
                                    "version": version,
                                    "known_versions": list(known_versions.keys()),
                                })
        
        # Check for missing expected attributes
        for rec in self.records:
            if rec.get("uuid") and not rec.get("name"):
                anomalies.append({
                    "type": "missing_service_name",
                    "severity": "low",
                    "description": f"Service {rec.get('uuid')} missing name",
                    "uuid": rec.get("uuid"),
                    "handle": rec.get("handle"),
                })
        
        return anomalies
    
    def _analyze_relationships(self) -> Dict[str, Any]:
        """Analyze service relationships and dependencies."""
        # Group services by profile
        profile_groups: Dict[str, List[str]] = defaultdict(list)
        for rec in self.records:
            if rec.get("profile_descriptors"):
                for profile in rec.get("profile_descriptors", []):
                    uuid = profile.get("uuid")
                    if uuid:
                        profile_groups[uuid].append(rec.get("name", rec.get("uuid", "Unknown")))
        
        # Identify related services (same profile)
        related_services: List[List[str]] = []
        for profile, services in profile_groups.items():
            if len(services) > 1:
                related_services.append(services)
        
        return {
            "profile_groups": dict(profile_groups),
            "related_services": related_services,
            "service_count_by_profile": {k: len(v) for k, v in profile_groups.items()},
        }
    
    def _extract_all_attributes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract all available attributes from records."""
        all_attrs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        for rec in self.records:
            attrs = {
                "handle": rec.get("handle"),
                "name": rec.get("name"),
                "uuid": rec.get("uuid"),
                "channel": rec.get("channel"),
                "description": rec.get("description"),
                "service_version": rec.get("service_version"),
                "profile_descriptors": rec.get("profile_descriptors"),
            }
            all_attrs["extracted"].append(attrs)
        
        return dict(all_attrs)
    
    def generate_report(self) -> str:
        """Generate human-readable analysis report.
        
        Returns
        -------
        str
            Formatted analysis report
        """
        if not self.analysis:
            self.analyze()
        
        lines = []
        lines.append("=" * 60)
        lines.append("SDP Comprehensive Analysis Report")
        lines.append("=" * 60)
        lines.append(f"\nTotal SDP Records: {self.analysis['total_records']}")
        
        # Protocol Analysis
        proto_analysis = self.analysis["protocol_analysis"]
        lines.append(f"\n--- Protocol Analysis ---")
        lines.append(f"Protocols Found: {', '.join(proto_analysis['protocols_found']) or 'None'}")
        if proto_analysis.get("rfcomm_channels"):
            lines.append(f"RFCOMM Channels: {', '.join(map(str, proto_analysis['rfcomm_channels']))}")
        
        # Profile Analysis
        profile_analysis = self.analysis["profile_analysis"]
        lines.append(f"\n--- Profile Analysis ---")
        lines.append(f"Unique Profiles: {profile_analysis['unique_profiles']}")
        if profile_analysis.get("version_distribution"):
            lines.append("Version Distribution:")
            for version, count in profile_analysis["version_distribution"].items():
                lines.append(f"  Bluetooth {version}: {count} profile(s)")
        
        # Version Inference
        version_inf = self.analysis["version_inference"]
        if version_inf.get("inferred_version"):
            lines.append(f"\n--- Version Inference ---")
            lines.append(f"Inferred Bluetooth Spec: {version_inf['inferred_version']}")
            lines.append(f"Confidence: {version_inf['confidence']:.1%}")
        
        # Anomalies
        anomalies = self.analysis["anomalies"]
        if anomalies:
            lines.append(f"\n--- Detected Anomalies ({len(anomalies)}) ---")
            for anomaly in anomalies:
                lines.append(f"  [{anomaly['severity'].upper()}] {anomaly['type']}: {anomaly['description']}")
        else:
            lines.append(f"\n--- Anomalies ---")
            lines.append("  No anomalies detected")
        
        # Service Relationships
        relationships = self.analysis["service_relationships"]
        if relationships.get("related_services"):
            lines.append(f"\n--- Service Relationships ---")
            for group in relationships["related_services"]:
                lines.append(f"  Related Services: {', '.join(group)}")
        
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


def analyze_sdp_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convenience function to analyze SDP records.
    
    Parameters
    ----------
    records : List[Dict[str, Any]]
        SDP records from discover_services_sdp()
    
    Returns
    -------
    Dict[str, Any]
        Comprehensive analysis results
    """
    analyzer = SDPAnalyzer(records)
    return analyzer.analyze()


def infer_bluetooth_spec_version(records: List[Dict[str, Any]]) -> Optional[str]:
    """Infer Bluetooth Core Specification version from SDP records.
    
    Parameters
    ----------
    records : List[Dict[str, Any]]
        SDP records from discover_services_sdp()
    
    Returns
    -------
    Optional[str]
        Inferred Bluetooth spec version (e.g., "1.2", "2.0") or None
    """
    analyzer = SDPAnalyzer(records)
    analysis = analyzer.analyze()
    return analysis["version_inference"].get("inferred_version")


def detect_version_anomalies(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect version inconsistencies in SDP records.
    
    Parameters
    ----------
    records : List[Dict[str, Any]]
        SDP records from discover_services_sdp()
    
    Returns
    -------
    List[Dict[str, Any]]
        List of detected anomalies
    """
    analyzer = SDPAnalyzer(records)
    analysis = analyzer.analyze()
    return analysis["anomalies"]

