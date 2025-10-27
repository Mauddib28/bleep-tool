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
import functools
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

from bleep.core.errors import BLEEPError
from bleep.bt_ref.utils import get_name_from_uuid
from bleep.core import observations


class BytesEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles bytes objects by converting them to hex strings."""
    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.hex()
        return super().default(obj)


def safe_db_operation(func):
    """
    Decorator for safely handling database operations with proper error handling.
    
    Args:
        func: The function to wrap
        
    Returns:
        Wrapped function with error handling
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Check for foreign key constraint failure
            if hasattr(e, '__module__') and e.__module__ == 'sqlite3' and 'FOREIGN KEY constraint failed' in str(e):
                logger.error(f"Database foreign key constraint error: {e}")
                
                # Try to extract device MAC from arguments
                device_mac = None
                if len(args) > 1 and isinstance(args[1], str):
                    device_mac = args[1]
                elif 'device_mac' in kwargs:
                    device_mac = kwargs['device_mac']
                elif 'mac' in kwargs:
                    device_mac = kwargs['mac']
                
                # If we found a MAC address, try to create the device
                if device_mac:
                    try:
                        logger.info(f"Creating missing device entry for {device_mac}")
                        observations.upsert_device(
                            device_mac,
                            name=f"Device {device_mac}",
                            addr_type="unknown",
                            device_class=0,
                            device_type="unknown"
                        )
                        # Retry the operation
                        return func(*args, **kwargs)
                    except Exception as inner_e:
                        logger.error(f"Failed to create device entry: {inner_e}")
            
            logger.error(f"Database operation failed: {e}")
            return None
    return wrapper

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
    
    def __init__(self, aoi_dir: Optional[str] = None, use_db: bool = True):
        """
        Initialize the AOI Analyser.
        
        Args:
            aoi_dir: Directory where AoI JSON dumps are stored. Defaults to ~/.bleep/aoi/
            use_db: Whether to use the database for storage/retrieval
        """
        self.aoi_dir = Path(aoi_dir or DEFAULT_AOI_DIR)
        self._ensure_aoi_dir()
        self.reports = {}
        self.use_db = use_db
        
    def _prepare_data_for_json(self, data):
        """
        Convert non-serializable types in data structure to serializable ones.
        
        Args:
            data: Any data structure that might contain non-serializable types
            
        Returns:
            Data structure with all non-serializable types converted to serializable ones
        """
        if isinstance(data, bytes):
            return data.hex()
        elif isinstance(data, dict):
            return {k: self._prepare_data_for_json(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._prepare_data_for_json(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self._prepare_data_for_json(item) for item in data)
        else:
            return data
        
    def _ensure_aoi_dir(self) -> None:
        """Ensure the AoI directory exists."""
        os.makedirs(self.aoi_dir, exist_ok=True)
    
    def list_devices(self) -> List[str]:
        """
        List all devices that have data in the AOI storage (file or database).
        
        Returns:
            List of normalized MAC addresses (with colons)
        """
        if self.use_db:
            # Try database first
            try:
                # Get devices from database
                devices = observations.get_aoi_analyzed_devices()
                if devices:
                    return [device["mac"].upper() for device in devices]
                    
                # If no devices found in database, fall back to files
                logger.info("No AoI devices found in database, falling back to files")
            except Exception as e:
                logger.error(f"Error accessing database, falling back to files: {str(e)}")
        
        # Fall back to file-based lookup
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
        Load AoI data for a specific device from either database or file.
        
        Args:
            device_mac: MAC address of the device
            
        Returns:
            Dictionary of device data
            
        Raises:
            FileNotFoundError: If no data exists for this device
            BLEEPError: If data exists but is corrupted or incompatible
        """
        # Try to load from database if enabled
        if self.use_db:
            try:
                # Get device details from database
                device_data = observations.get_device_detail(device_mac)
                if device_data:
                    # Add any AoI analysis data if available
                    aoi_analysis = observations.get_aoi_analysis(device_mac)
                    if aoi_analysis:
                        device_data["analysis"] = aoi_analysis
                    return device_data
                
                # If no device data in database, fall back to files
                logger.debug(f"No device data found in database for {device_mac}, falling back to files")
            except Exception as e:
                logger.error(f"Error accessing database for {device_mac}, falling back to files: {str(e)}")
        
        # Fall back to file-based lookup
        # Normalize MAC address format
        device_mac_norm = device_mac.replace(':', '').lower()
        
        # Find the most recent file for this device
        device_files = list(self.aoi_dir.glob(f"{device_mac_norm}*.json"))
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
    
    @safe_db_operation
    def save_device_data(self, device_mac: str, data: Dict[str, Any]) -> str:
        """
        Save device data to storage (database and/or file).
        
        Args:
            device_mac: MAC address of the device
            data: Dictionary of device data to save
            
        Returns:
            Path to the saved file (if file storage is used)
        """
        # Ensure device_mac is a string
        if not isinstance(device_mac, str):
            device_mac = str(device_mac)
            
        # Save to database if enabled
        if self.use_db:
            try:
                # Extract basic device information
                device_info = {
                    "name": data.get("name", "Unknown Device"),
                    "last_seen": datetime.now().isoformat()
                }
                
                # Add device type and addr_type if available
                if "device_type" in data:
                    device_info["device_type"] = data["device_type"]
                if "addr_type" in data:
                    device_info["addr_type"] = data["addr_type"]
                if "device_class" in data:
                    device_info["device_class"] = data["device_class"]
                
                # Save device info to database
                observations.upsert_device(device_mac, **device_info)
                
                # Save services if present
                if "services" in data:
                    services = []
                    # Handle different service data formats
                    if isinstance(data["services"], dict):
                        for svc_uuid, svc_info in data["services"].items():
                            if isinstance(svc_info, dict):
                                svc_info["uuid"] = svc_uuid
                                services.append(svc_info)
                            else:
                                services.append({"uuid": svc_uuid})
                    else:
                        for svc_uuid in data["services"]:
                            services.append({"uuid": svc_uuid})
                        
                    service_ids = observations.upsert_services(device_mac, services)
                    
                    # Save characteristics if present in services_mapping
                    if "services_mapping" in data and service_ids:
                        for svc_uuid, svc_id in service_ids.items():
                            chars = []
                            # Extract characteristics for this service
                            for uuid, handle in data["services_mapping"].items():
                                if handle == svc_uuid:
                                    # Find characteristic details if available
                                    char_info = {"uuid": uuid}
                                    if "characteristics" in data and uuid in data["characteristics"]:
                                        # Ensure bytes are converted to hex strings
                                        char_data = data["characteristics"][uuid]
                                        if isinstance(char_data, dict):
                                            for k, v in char_data.items():
                                                if isinstance(v, bytes):
                                                    char_data[k] = v.hex()
                                            char_info.update(char_data)
                                    chars.append(char_info)
                            
                            if chars:
                                observations.upsert_characteristics(svc_id, chars)
                
                # If analysis exists, save it
                if "analysis" in data:
                    observations.store_aoi_analysis(device_mac, data["analysis"])
                    
                logger.info(f"Saved AoI data to database for {device_mac}")
            except Exception as e:
                logger.error(f"Error saving to database: {str(e)}")
                # Continue with file save even if database save fails
        
        # Always save to file for backward compatibility
        # Normalize MAC address format
        device_mac_norm = device_mac.replace(':', '').lower()
        
        # Create timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create filename
        filename = f"{device_mac_norm}_{timestamp}.json"
        filepath = self.aoi_dir / filename
        
        # Prepare data for serialization
        serializable_data = self._prepare_data_for_json(data)
        
        with open(filepath, 'w') as f:
            json.dump(serializable_data, f, indent=2, cls=BytesEncoder)
        
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
        # Ensure device_mac is a string
        if not isinstance(device_mac, str):
            device_mac = str(device_mac)
            
        # Load data if not provided
        if data is None:
            data = self.load_device_data(device_mac)
            
        # Handle case where data is None or not a dictionary
        if not data or not isinstance(data, dict):
            logger.error(f"Invalid device data for {device_mac}")
            data = {}
        
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
        services_data = data.get("services", {})
        characteristics = data.get("characteristics", {})
        landmine_map = data.get("landmine_map", {})
        permission_map = data.get("permission_map", {})
        
        # Handle different service data formats
        # If services is a list of UUIDs
        if isinstance(services_data, list):
            for uuid in services_data:
                service_info = {"uuid": uuid}
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
        # If services is a dictionary
        elif isinstance(services_data, dict):
            for uuid, service_info in services_data.items():
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
        # Handle cases where characteristics might be in services_mapping instead
        if not characteristics and "services_mapping" in data:
            for handle, uuid in data.get("services_mapping", {}).items():
                char_info = {"uuid": uuid, "handle": handle}
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
        # Process normal characteristics dictionary
        elif isinstance(characteristics, dict):
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
        
        # Ensure all dictionary keys in the report are strings
        # This prevents "unhashable type: 'dict'" errors when the report is used as a key
        report = self._prepare_data_for_json(report)
        
        # Store the report
        self.reports[device_mac] = report
        
        # Store in database if enabled
        if self.use_db:
            try:
                # Ensure device exists in database before storing analysis
                try:
                    device_exists = observations.get_device_detail(device_mac) is not None
                    if not device_exists:
                        logger.info(f"Creating device entry for {device_mac} before storing analysis")
                        observations.upsert_device(
                            device_mac,
                            name=f"Device {device_mac}",
                            addr_type="unknown",
                            device_class=0,
                            device_type="unknown"
                        )
                except Exception as e:
                    logger.error(f"Error checking device existence: {str(e)}")
                
                observations.store_aoi_analysis(device_mac, report)
                logger.info(f"Saved analysis to database for {device_mac}")
            except Exception as e:
                logger.error(f"Error saving analysis to database: {str(e)}")
                
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
        
    def analyze_device_data(self, device_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze device data without requiring a device_mac.
        This method serves as a bridge between generate_report and analyse_device.
        
        Args:
            device_data: Device data dictionary
            
        Returns:
            Analysis report dictionary
        """
        # Extract the device MAC from the data if available
        device_mac = device_data.get("address", device_data.get("device_mac", "unknown"))
        return self.analyse_device(device_mac, device_data)
    
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
