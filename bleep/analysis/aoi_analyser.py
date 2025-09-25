"""
Assets-of-Interest (AoI) analysis module.

This module provides functionality to analyze Bluetooth device data collected during
enumeration and generate actionable reports based on the findings. It processes device
mappings, service/characteristic information, and security-related metadata to identify
notable items of interest.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

from bleep.core.errors import BLEEPError
from bleep.bt_ref.utils import get_name_from_uuid

# Configure logger
logger = logging.getLogger(__name__)

# Default location for AoI JSON dumps
DEFAULT_AOI_DIR = os.path.expanduser("~/.bleep/aoi")


class AOIAnalyser:
    """
    Analyser for Assets-of-Interest data collected from Bluetooth devices.
    
    This class processes device data collected during enumeration and generates
    actionable reports highlighting security concerns, unusual characteristics,
    and other notable findings.
    """
    
    def __init__(self, aoi_dir: Optional[str] = None):
        """
        Initialize the AOI Analyser.
        
        Args:
            aoi_dir: Directory where AoI JSON dumps are stored. Defaults to ~/.bleep/aoi/
        """
        self.aoi_dir = Path(aoi_dir or DEFAULT_AOI_DIR)
        self._ensure_aoi_dir()
        self.reports = {}
        
    def _ensure_aoi_dir(self) -> None:
        """Ensure the AoI directory exists."""
        os.makedirs(self.aoi_dir, exist_ok=True)
    
    def list_devices(self) -> List[str]:
        """
        List all devices that have data in the AOI directory.
        
        Returns:
            List of normalized MAC addresses (with colons)
        """
        # Ensure directory exists
        self._ensure_aoi_dir()
        
        # Get all JSON files in the directory
        json_files = list(self.aoi_dir.glob("*.json"))
        
        # Extract device MAC addresses from filenames
        devices = set()
        for file_path in json_files:
            # Extract the MAC part from the filename (before the timestamp)
            filename = file_path.stem  # Get filename without extension
            if "_" in filename:
                mac = filename.split("_")[0]  # Get the part before the first underscore
                # Convert to standard MAC format with colons
                normalized = ":".join([mac[i:i+2] for i in range(0, len(mac), 2)]).upper()
                devices.add(normalized)
        
        return list(devices)
        
    def load_device_data(self, device_mac: str) -> Dict[str, Any]:
        """
        Load AoI data for a specific device.
        
        Args:
            device_mac: MAC address of the device
            
        Returns:
            Dictionary of device data
            
        Raises:
            FileNotFoundError: If no data exists for this device
            BLEEPError: If data exists but is corrupted or incompatible
        """
        # Normalize MAC address format
        device_mac = device_mac.replace(':', '').lower()
        
        # Find the most recent file for this device
        device_files = list(self.aoi_dir.glob(f"{device_mac}*.json"))
        if not device_files:
            raise FileNotFoundError(f"No AoI data found for device {device_mac}")
            
        # Sort by modification time (most recent first)
        device_files.sort(key=os.path.getmtime, reverse=True)
        latest_file = device_files[0]
        
        try:
            with open(latest_file, 'r') as f:
                data = json.load(f)
            return data
        except json.JSONDecodeError as e:
            raise BLEEPError(f"Invalid JSON in {latest_file}: {str(e)}")
        except Exception as e:
            raise BLEEPError(f"Error loading {latest_file}: {str(e)}")
    
    def save_device_data(self, device_mac: str, data: Dict[str, Any]) -> str:
        """
        Save device data to the AoI directory.
        
        Args:
            device_mac: MAC address of the device
            data: Dictionary of device data to save
            
        Returns:
            Path to the saved file
        """
        # Normalize MAC address format
        device_mac = device_mac.replace(':', '').lower()
        
        # Create timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create filename
        filename = f"{device_mac}_{timestamp}.json"
        filepath = self.aoi_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved AoI data to {filepath}")
        return str(filepath)
    
    def analyse_device(self, device_mac: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze device data and generate a report.
        
        Args:
            device_mac: MAC address of the device
            data: Optional device data dictionary. If None, data will be loaded from file
            
        Returns:
            Analysis report dictionary
        """
        # Load data if not provided
        if data is None:
            data = self.load_device_data(device_mac)
        
        # Initialize report structure
        report = {
            "device_mac": device_mac,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "security_concerns": [],
                "unusual_characteristics": [],
                "notable_services": [],
                "accessibility": {},
                "recommendations": [],
            },
            "details": {
                "services": [],
                "characteristics": [],
                "landmine_map": {},
                "permission_map": {},
            }
        }
        
        # Extract service and characteristic information
        services = data.get("services", {})
        characteristics = data.get("characteristics", {})
        landmine_map = data.get("landmine_map", {})
        permission_map = data.get("permission_map", {})
        
        # Analyze services
        for uuid, service_info in services.items():
            service_report = self._analyse_service(uuid, service_info)
            if service_report:
                report["details"]["services"].append(service_report)
                
                # Check for notable services
                if service_report.get("is_notable", False):
                    report["summary"]["notable_services"].append({
                        "uuid": uuid,
                        "name": service_report.get("name", "Unknown Service"),
                        "reason": service_report.get("notable_reason", ""),
                    })
        
        # Analyze characteristics
        for uuid, char_info in characteristics.items():
            char_report = self._analyse_characteristic(uuid, char_info)
            if char_report:
                report["details"]["characteristics"].append(char_report)
                
                # Check for security concerns
                if char_report.get("security_concern", False):
                    report["summary"]["security_concerns"].append({
                        "uuid": uuid,
                        "name": char_report.get("name", "Unknown Characteristic"),
                        "reason": char_report.get("security_reason", ""),
                    })
                
                # Check for unusual characteristics
                if char_report.get("is_unusual", False):
                    report["summary"]["unusual_characteristics"].append({
                        "uuid": uuid,
                        "name": char_report.get("name", "Unknown Characteristic"),
                        "reason": char_report.get("unusual_reason", ""),
                    })
        
        # Analyze permission and landmine maps
        report["details"]["landmine_map"] = self._analyse_landmine_map(landmine_map)
        report["details"]["permission_map"] = self._analyse_permission_map(permission_map)
        
        # Generate accessibility summary
        report["summary"]["accessibility"] = self._generate_accessibility_summary(
            report["details"]["landmine_map"], 
            report["details"]["permission_map"]
        )
        
        # Generate recommendations
        report["summary"]["recommendations"] = self._generate_recommendations(report)
        
        # Store the report
        self.reports[device_mac] = report
        return report
    
    def _analyse_service(self, uuid: str, service_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a service and generate a report.
        
        Args:
            uuid: Service UUID
            service_info: Service information dictionary
            
        Returns:
            Service analysis report
        """
        # Basic service report
        service_report = {
            "uuid": uuid,
            "name": get_name_from_uuid(uuid),
            "is_primary": service_info.get("is_primary", False),
            "is_notable": False,
            "characteristics": service_info.get("characteristics", []),
        }
        
        # Check for notable services
        if uuid in ["1800", "1801"]:  # GAP and GATT
            service_report["is_notable"] = True
            service_report["notable_reason"] = "Core BLE service"
        elif "OTA" in service_report["name"] or "dfu" in service_report["name"].lower():
            service_report["is_notable"] = True
            service_report["notable_reason"] = "Firmware update service"
        elif "auth" in service_report["name"].lower() or "security" in service_report["name"].lower():
            service_report["is_notable"] = True
            service_report["notable_reason"] = "Authentication/security service"
        
        return service_report
    
    def _analyse_characteristic(self, uuid: str, char_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a characteristic and generate a report.
        
        Args:
            uuid: Characteristic UUID
            char_info: Characteristic information dictionary
            
        Returns:
            Characteristic analysis report
        """
        # Basic characteristic report
        char_report = {
            "uuid": uuid,
            "name": get_name_from_uuid(uuid),
            "properties": char_info.get("properties", []),
            "security_concern": False,
            "is_unusual": False,
        }
        
        # Check properties
        properties = char_info.get("properties", [])
        
        # Check for security concerns
        if "write-without-response" in properties and ("auth" in char_report["name"].lower() or 
                                                      "password" in char_report["name"].lower() or
                                                      "key" in char_report["name"].lower()):
            char_report["security_concern"] = True
            char_report["security_reason"] = "Authentication-related characteristic allows write without response"
        
        # Check for unusual characteristics
        if len(properties) > 3 and "write" in properties and "notify" in properties:
            char_report["is_unusual"] = True
            char_report["unusual_reason"] = "Multiple operations supported including write and notify"
            
        # Check for unusual values
        if "value" in char_info and isinstance(char_info["value"], str) and len(char_info["value"]) > 20:
            char_report["is_unusual"] = True
            char_report["unusual_reason"] = "Contains unusually long default value"
        
        return char_report
    
    def _analyse_landmine_map(self, landmine_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the landmine map.
        
        Args:
            landmine_map: Landmine map from device data
            
        Returns:
            Processed landmine map with additional analysis
        """
        result = {}
        for uuid, status in landmine_map.items():
            result[uuid] = {
                "status": status,
                "is_critical": self._is_critical_uuid(uuid),
            }
        return result
    
    def _analyse_permission_map(self, permission_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the permission map.
        
        Args:
            permission_map: Permission map from device data
            
        Returns:
            Processed permission map with additional analysis
        """
        result = {}
        for uuid, status in permission_map.items():
            result[uuid] = {
                "status": status,
                "is_critical": self._is_critical_uuid(uuid),
            }
        return result
    
    def _is_critical_uuid(self, uuid: str) -> bool:
        """
        Determine if a UUID is for a critical characteristic.
        
        Args:
            uuid: Characteristic UUID
            
        Returns:
            True if the UUID is critical, False otherwise
        """
        # Get UUID name and convert to lowercase
        name = get_name_from_uuid(uuid).lower()
        
        # Check for critical keywords
        critical_keywords = ["auth", "password", "key", "firmware", "dfu", "ota", "security"]
        return any(keyword in name for keyword in critical_keywords)
    
    def _generate_accessibility_summary(self, landmine_map: Dict[str, Any], 
                                       permission_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a summary of device accessibility.
        
        Args:
            landmine_map: Processed landmine map
            permission_map: Processed permission map
            
        Returns:
            Accessibility summary
        """
        total_chars = len(set(landmine_map.keys()).union(set(permission_map.keys())))
        blocked_chars = sum(1 for _, info in landmine_map.items() if info["status"] != "OK")
        protected_chars = sum(1 for _, info in permission_map.items() if info["status"] != "OK")
        
        return {
            "total_characteristics": total_chars,
            "blocked_characteristics": blocked_chars,
            "protected_characteristics": protected_chars,
            "accessibility_score": (total_chars - blocked_chars - protected_chars) / total_chars if total_chars else 0,
        }
    
    def _generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """
        Generate recommendations based on the report.
        
        Args:
            report: Device analysis report
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Check security concerns
        if report["summary"]["security_concerns"]:
            recommendations.append(
                f"Investigate {len(report['summary']['security_concerns'])} security concerns including "
                f"{report['summary']['security_concerns'][0]['name']}."
            )
        
        # Check unusual characteristics
        if report["summary"]["unusual_characteristics"]:
            recommendations.append(
                f"Examine {len(report['summary']['unusual_characteristics'])} unusual characteristics including "
                f"{report['summary']['unusual_characteristics'][0]['name']}."
            )
        
        # Check accessibility
        accessibility = report["summary"]["accessibility"]
        if accessibility["accessibility_score"] > 0.8:
            recommendations.append(
                f"Device is highly accessible ({accessibility['accessibility_score']:.2%}). "
                "Consider detailed enumeration of all characteristics."
            )
        elif accessibility["accessibility_score"] < 0.3:
            recommendations.append(
                f"Device has limited accessibility ({accessibility['accessibility_score']:.2%}). "
                "Consider authentication/pairing options."
            )
        
        # Default recommendation
        if not recommendations:
            recommendations.append("No specific concerns found. Continue with standard enumeration.")
        
        return recommendations
        
    def generate_report(self, device_address: str = None, device_data: Dict = None, 
                       format: str = "markdown") -> str:
        """
        Generate a security report for the specified device.
        
        Args:
            device_address: MAC address of the device
            device_data: Device data if already loaded
            format: Report format ("markdown", "json", "text")
            
        Returns:
            Report content as string
        """
        # Load device data if not provided
        if not device_data and device_address:
            device_data = self.load_device_data(device_address)
            
        if not device_data:
            raise BLEEPError("No device data available for report generation")
            
        # Analyze the device data if not already analyzed
        if "analysis" not in device_data:
            analysis = self.analyze_device_data(device_data)
        else:
            analysis = device_data["analysis"]
            
        # Calculate security score
        security_score = self._calculate_security_score(analysis)
            
        # Generate report based on format
        if format == "json":
            return self._generate_json_report(device_data, analysis, security_score)
        elif format == "text":
            return self._generate_text_report(device_data, analysis, security_score)
        else:  # markdown is default
            return self._generate_markdown_report(device_data, analysis, security_score)
    
    def _calculate_security_score(self, analysis: Dict) -> int:
        """Calculate a security score from 0-10 based on analysis."""
        score = 5  # Start with a neutral score
        
        # Add points for security concerns
        if "summary" in analysis and "security_concerns" in analysis["summary"]:
            concerns = analysis["summary"]["security_concerns"]
            high_risk = sum(1 for c in concerns if c.get("risk") == "high")
            medium_risk = sum(1 for c in concerns if c.get("risk") == "medium")
            low_risk = sum(1 for c in concerns if c.get("risk") == "low")
            
            score += high_risk * 1.5
            score += medium_risk * 0.75
            score += low_risk * 0.25
        
        # Cap at 0-10
        return min(max(int(score), 0), 10)
    
    def _generate_markdown_report(self, device_data: Dict, analysis: Dict, security_score: int) -> str:
        """Generate a markdown report."""
        address = device_data.get("address", "Unknown")
        name = device_data.get("name", "Unnamed Device")
        
        report = [
            f"# Security Report: {name} ({address})",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**BLEEP Version:** {self._get_version()}",
            "",
            "## Device Information",
            "",
            f"- **Address:** {address}",
            f"- **Name:** {name}",
        ]
        
        # Add RSSI if available
        if "rssi" in device_data:
            report.append(f"- **RSSI:** {device_data['rssi']} dBm")
            
        # Add device class if available
        if "device_class" in device_data:
            report.append(f"- **Device Class:** {device_data['device_class']}")
            
        report.extend([
            "",
            "## Security Analysis",
            "",
            f"**Security Score:** {security_score}/10",
            "",
        ])
        
        # Add vulnerabilities section
        vulnerabilities = []
        if "summary" in analysis and "security_concerns" in analysis["summary"]:
            vulnerabilities = analysis["summary"]["security_concerns"]
            
        if vulnerabilities:
            report.append("### Vulnerabilities")
            report.append("")
            
            for vuln in vulnerabilities:
                risk_emoji = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(vuln.get("risk", "low"), "⚪")
                report.append(f"{risk_emoji} **{vuln.get('name')}:** {vuln.get('description', '')}")
                
            report.append("")
        
        # Add services section
        if "services" in device_data:
            report.extend([
                "## Services",
                "",
            ])
            
            for service in device_data["services"]:
                uuid = service.get("uuid", "Unknown")
                name = service.get("name", get_name_from_uuid(uuid) or uuid)
                
                report.append(f"### {name}")
                report.append(f"- UUID: `{uuid}`")
                
                # Add characteristics
                chars = service.get("characteristics", [])
                if chars:
                    report.append("- **Characteristics:**")
                    
                    for char in chars:
                        char_uuid = char.get("uuid", "Unknown")
                        char_name = char.get("name", get_name_from_uuid(char_uuid) or char_uuid)
                        flags = ", ".join(char.get("flags", []))
                        report.append(f"  - {char_name} (`{char_uuid}`): {flags}")
                        
                        # Add security notes if present
                        for vuln in vulnerabilities:
                            if vuln.get("uuid") == char_uuid:
                                report.append(f"    - ⚠️ {vuln.get('description', '')}")
                                
                report.append("")
        
        # Add recommendations
        recommendations = self._generate_recommendations(analysis)
        if recommendations:
            report.extend([
                "## Recommendations",
                "",
            ])
            
            for i, rec in enumerate(recommendations, 1):
                report.append(f"{i}. {rec}")
                
        return "\n".join(report)
    
    def _generate_text_report(self, device_data: Dict, analysis: Dict, security_score: int) -> str:
        """Generate a plain text report."""
        address = device_data.get("address", "Unknown")
        name = device_data.get("name", "Unnamed Device")
        
        # Convert markdown to plain text
        report = [
            f"SECURITY REPORT: {name} ({address})",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"BLEEP Version: {self._get_version()}",
            "",
            "DEVICE INFORMATION",
            f"Address: {address}",
            f"Name: {name}",
        ]
        
        # Add RSSI if available
        if "rssi" in device_data:
            report.append(f"RSSI: {device_data['rssi']} dBm")
            
        # Add device class if available
        if "device_class" in device_data:
            report.append(f"Device Class: {device_data['device_class']}")
            
        report.extend([
            "",
            "SECURITY ANALYSIS",
            f"Security Score: {security_score}/10",
            "",
        ])
        
        # Add vulnerabilities section
        vulnerabilities = []
        if "summary" in analysis and "security_concerns" in analysis["summary"]:
            vulnerabilities = analysis["summary"]["security_concerns"]
            
        if vulnerabilities:
            report.append("VULNERABILITIES")
            
            for vuln in vulnerabilities:
                risk = vuln.get("risk", "low").upper()
                report.append(f"[{risk}] {vuln.get('name')}: {vuln.get('description', '')}")
                
            report.append("")
        
        # Add recommendations
        recommendations = self._generate_recommendations(analysis)
        if recommendations:
            report.append("RECOMMENDATIONS")
            
            for i, rec in enumerate(recommendations, 1):
                report.append(f"{i}. {rec}")
                
        return "\n".join(report)
    
    def _generate_json_report(self, device_data: Dict, analysis: Dict, security_score: int) -> str:
        """Generate a JSON report."""
        # Extract vulnerabilities
        vulnerabilities = []
        if "summary" in analysis and "security_concerns" in analysis["summary"]:
            vulnerabilities = analysis["summary"]["security_concerns"]
            
        # Extract recommendations
        recommendations = self._generate_recommendations(analysis)
        
        # Build report object
        report = {
            "device": device_data,
            "analysis": {
                "timestamp": datetime.now().isoformat(),
                "security_score": security_score,
                "vulnerabilities": vulnerabilities,
                "recommendations": recommendations
            },
            "metadata": {
                "version": self._get_version(),
                "generator": "BLEEP AOI Analyzer"
            }
        }
        
        return json.dumps(report, indent=2)
    
    def save_report(self, report_content: str, filename: str = None, device_address: str = None) -> str:
        """
        Save a report to disk.
        
        Args:
            report_content: Content of the report
            filename: Custom filename
            device_address: Device address to use in filename
            
        Returns:
            Path to saved report
        """
        if not filename:
            if device_address:
                safe_addr = device_address.replace(':', '')
                filename = f"report_{safe_addr}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            else:
                filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                
        # Create reports subdirectory in the AOI directory
        report_dir = Path(self.aoi_dir) / "reports"
        os.makedirs(report_dir, exist_ok=True)
        
        # Save the report
        report_path = report_dir / filename
        with open(report_path, 'w') as f:
            f.write(report_content)
            
        logger.info(f"Report saved to {report_path}")
        return str(report_path)
    
    def _get_version(self) -> str:
        """Get BLEEP version."""
        try:
            from bleep import __version__
            return __version__
        except (ImportError, AttributeError):
            return "Unknown"


def analyse_aoi_data(device_mac: str, data: Optional[Dict[str, Any]] = None, 
                    aoi_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to analyze AoI data for a device.
    
    Args:
        device_mac: Device MAC address
        data: Optional device data. If None, data will be loaded from file
        aoi_dir: Directory where AoI JSON dumps are stored
        
    Returns:
        Analysis report
    """
    analyser = AOIAnalyser(aoi_dir=aoi_dir)
    return analyser.analyse_device(device_mac, data)
