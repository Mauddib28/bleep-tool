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
    
    def __init__(self, aoi_dir: Optional[str] = None, use_db: bool = True,
                 db_only: bool = False):
        """
        Initialize the AOI Analyser.
        
        Args:
            aoi_dir: Directory where AoI JSON dumps are stored. Defaults to ~/.bleep/aoi/
            use_db: Whether to use the database for storage/retrieval
            db_only: If True, skip file writes (database only)
        """
        self.aoi_dir = Path(aoi_dir or DEFAULT_AOI_DIR)
        self._ensure_aoi_dir()
        self.reports = {}
        self.use_db = use_db
        self.db_only = db_only
        
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
        device_mac_norm = device_mac.replace(':', '').upper()
        
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

                    # Persist chars/descriptors from the full GATT mapping structure
                    if "services_mapping" in data and service_ids:
                        svc_map = data["services_mapping"]
                        for svc_uuid, svc_id in service_ids.items():
                            svc_data = svc_map.get(svc_uuid)
                            if not isinstance(svc_data, dict):
                                continue
                            chars_data = svc_data.get("chars") or svc_data.get("Characteristics")
                            if not chars_data or not isinstance(chars_data, dict):
                                continue
                            char_list = []
                            for char_uuid, char_info in chars_data.items():
                                if not isinstance(char_info, dict):
                                    char_list.append({"uuid": char_uuid})
                                    continue
                                char_entry = {
                                    "uuid": char_uuid,
                                    "handle": char_info.get("handle"),
                                    "properties": list(char_info.get("properties", {}).keys()) if isinstance(char_info.get("properties"), dict) else char_info.get("properties", []),
                                    "value": char_info.get("value"),
                                }
                                if char_info.get("mtu") is not None:
                                    char_entry["mtu"] = char_info["mtu"]
                                char_list.append(char_entry)
                            if char_list:
                                observations.upsert_characteristics(svc_id, char_list, mac=device_mac, service_uuid=svc_uuid)
                            # Persist descriptors
                            for char_uuid, char_info in chars_data.items():
                                if not isinstance(char_info, dict):
                                    continue
                                desc_data = char_info.get("Descriptors") or char_info.get("descriptors")
                                if not desc_data or not isinstance(desc_data, dict):
                                    continue
                                char_id = observations.get_characteristic_id(svc_id, char_uuid)
                                if not char_id:
                                    continue
                                desc_list = []
                                for d_uuid, d_entry in desc_data.items():
                                    d_info = {"uuid": d_uuid}
                                    if isinstance(d_entry, dict):
                                        d_info["value"] = d_entry.get("Value") or d_entry.get("value")
                                        d_info["handle"] = d_entry.get("Handle") or d_entry.get("handle")
                                        d_info["flags"] = d_entry.get("Flags") or d_entry.get("flags")
                                    desc_list.append(d_info)
                                if desc_list:
                                    observations.upsert_descriptors(char_id, desc_list)
                
                # If analysis exists, merge v11 fields and persist
                if "analysis" in data:
                    merged_analysis = dict(data["analysis"])
                    for v11_key in ("pairing_profile", "sdp_summary", "post_pair_delta"):
                        if v11_key in data and v11_key not in merged_analysis:
                            merged_analysis[v11_key] = data[v11_key]
                    observations.store_aoi_analysis(device_mac, merged_analysis)
                    
                logger.info(f"Saved AoI data to database for {device_mac}")
            except Exception as e:
                logger.error(f"Error saving to database: {str(e)}")
                # Continue with file save even if database save fails
        
        if self.db_only:
            return ""

        # Normalize MAC address format
        device_mac_norm = device_mac.replace(':', '').upper()
        
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
        if isinstance(services_data, list):
            for elem in services_data:
                svc_uuid = elem.get("uuid", elem.get("UUID", "")) if isinstance(elem, dict) else str(elem)
                service_info = {"uuid": svc_uuid}
                service_report = self._analyse_service(svc_uuid, service_info)
                if service_report:
                    report["details"]["services"].append(service_report)
                    if service_report.get("is_notable", False):
                        report["summary"]["notable_services"].append({
                            "uuid": svc_uuid,
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
        
        # Extract characteristics from the full GATT mapping structure
        if not characteristics and "services_mapping" in data:
            svc_map = data.get("services_mapping", {})
            for _svc_uuid, svc_data in svc_map.items():
                if not isinstance(svc_data, dict):
                    continue
                chars_data = svc_data.get("chars") or svc_data.get("Characteristics") or {}
                if not isinstance(chars_data, dict):
                    continue
                for char_uuid, char_info in chars_data.items():
                    if not isinstance(char_info, dict):
                        char_info = {}
                    char_info_copy = dict(char_info)
                    char_info_copy["uuid"] = char_uuid
                    char_report = self._analyse_characteristic(char_uuid, char_info_copy)
                    if char_report:
                        report["details"]["characteristics"].append(char_report)

                        if char_report.get("security_concern", False):
                            report["summary"]["security_concerns"].append({
                                "uuid": char_uuid,
                                "name": char_report.get("name", "Unknown Characteristic"),
                                "reason": char_report.get("security_reason", ""),
                            })

                        if char_report.get("is_unusual", False):
                            report["summary"]["unusual_characteristics"].append({
                                "uuid": char_uuid,
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
        
        # Analyse v11 fields if present
        if "sdp_summary" in data:
            sdp_analysis = self._analyse_sdp_records(data["sdp_summary"])
            report["sdp_summary"] = sdp_analysis
            for flag in sdp_analysis.get("security_flags", []):
                report["summary"]["security_concerns"].append(
                    {"name": "Classic Profile", "reason": flag})

        if "pairing_profile" in data:
            pp_analysis = self._analyse_pairing_profile(data["pairing_profile"])
            report["pairing_profile"] = pp_analysis
            for c in pp_analysis.get("concerns", []):
                report["summary"]["security_concerns"].append(
                    {"name": "Pairing", "reason": c})

        if "post_pair_delta" in data:
            ppd = self._analyse_post_pair_delta(data["post_pair_delta"])
            report["post_pair_delta"] = ppd

        # Generate recommendations
        report["summary"]["recommendations"] = self._generate_recommendations(report)
        
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
                
                merged_report = dict(report)
                for v11_key in ("pairing_profile", "sdp_summary", "post_pair_delta"):
                    if v11_key in data and v11_key not in merged_report:
                        merged_report[v11_key] = data[v11_key]
                observations.store_aoi_analysis(device_mac, merged_report)
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
    
    def _analyse_sdp_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyse SDP records for security-relevant services.
        
        Returns a summary dict with ``services_found``, ``security_flags``,
        and ``raw_count``.
        """
        security_flags: List[str] = []
        svc_names: List[str] = []
        for rec in records:
            name = rec.get("name", "")
            svc_names.append(name or rec.get("uuid", "unknown"))
            lower = name.lower()
            if any(kw in lower for kw in ("obex", "ftp", "opp", "pbap", "map", "spp", "serial")):
                security_flags.append(f"Classic profile exposed: {name}")
        return {
            "raw_count": len(records),
            "services_found": svc_names,
            "security_flags": security_flags,
        }

    def _analyse_pairing_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Analyse a pairing-profile dict for security concerns."""
        concerns: List[str] = []
        if profile.get("paired") and profile.get("method") == "JustWorks":
            concerns.append("Device paired via JustWorks (no MITM protection)")
        if profile.get("error") and "rejected" not in str(profile["error"]).lower():
            concerns.append(f"Pairing error: {profile['error']}")
        return {"concerns": concerns, "method": profile.get("method"), "paired": profile.get("paired", False)}

    def _analyse_post_pair_delta(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """Analyse changes revealed by post-pair re-enumeration."""
        findings: List[str] = []
        if delta.get("le_delta"):
            le = delta["le_delta"]
            svc_count = len(le.get("services", []))
            findings.append(f"Post-pair LE enum revealed {svc_count} service(s)")
        if delta.get("sdp_delta"):
            findings.append(f"Post-pair SDP revealed {len(delta['sdp_delta'])} record(s)")
        return {"findings": findings}

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
        
        accessibility = report.get("summary", {}).get("accessibility", {})
        acc_score = accessibility.get("accessibility_score", 0) if isinstance(accessibility, dict) else 0
        if acc_score > 0.8:
            recommendations.append(
                f"Device is highly accessible ({acc_score:.2%}). "
                "Consider detailed enumeration of all characteristics."
            )
        elif acc_score < 0.3 and acc_score != 0:
            recommendations.append(
                f"Device has limited accessibility ({acc_score:.2%}). "
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
        
        if "services" in device_data:
            report.extend(["## Services", ""])
            for service in device_data["services"]:
                if isinstance(service, dict):
                    uuid = service.get("uuid", "Unknown")
                    name = service.get("name", get_name_from_uuid(uuid) or uuid)
                elif isinstance(service, str):
                    uuid = service
                    name = get_name_from_uuid(uuid) or uuid
                else:
                    continue
                report.append(f"### {name}")
                report.append(f"- UUID: `{uuid}`")
                if isinstance(service, dict):
                    chars = service.get("characteristics", [])
                    if chars:
                        report.append("- **Characteristics:**")
                        for char in chars:
                            char_uuid = char.get("uuid", "Unknown")
                            char_name = char.get("name", get_name_from_uuid(char_uuid) or char_uuid)
                            flags = ", ".join(char.get("flags", []))
                            report.append(f"  - {char_name} (`{char_uuid}`): {flags}")
                            for vuln in vulnerabilities:
                                if vuln.get("uuid") == char_uuid:
                                    report.append(f"    - ⚠️ {vuln.get('description', '')}")
                report.append("")
        
        # SDP summary section
        sdp_info = analysis.get("sdp_summary") or device_data.get("sdp_summary")
        if sdp_info:
            report.extend(["## SDP Discovery", ""])
            if isinstance(sdp_info, dict):
                for svc in sdp_info.get("services_found", []):
                    report.append(f"- {svc}")
                for flag in sdp_info.get("security_flags", []):
                    report.append(f"- **{flag}**")
            elif isinstance(sdp_info, list):
                for rec in sdp_info:
                    report.append(f"- {rec.get('name', rec.get('uuid', 'unknown'))}")
            report.append("")

        # Pairing profile section
        pp = analysis.get("pairing_profile") or device_data.get("pairing_profile")
        if pp and pp.get("attempted", pp.get("paired", False)):
            report.extend(["## Pairing Profile", ""])
            report.append(f"- **Method:** {pp.get('method', 'N/A')}")
            report.append(f"- **Paired:** {'Yes' if pp.get('paired') else 'No'}")
            for c in pp.get("concerns", []):
                report.append(f"- {c}")
            report.append("")

        ppd = analysis.get("post_pair_delta") or device_data.get("post_pair_delta")
        if ppd:
            findings = ppd.get("findings", [])
            if not findings:
                findings = []
                if ppd.get("le_delta"):
                    le = ppd["le_delta"]
                    cnt = len(le.get("services", []))
                    findings.append(f"Post-pair LE enum revealed {cnt} service(s)")
                if ppd.get("sdp_delta"):
                    findings.append(f"Post-pair SDP revealed {len(ppd['sdp_delta'])} record(s)")
            if findings:
                report.extend(["## Post-Pair Delta", ""])
                for f in findings:
                    report.append(f"- {f}")
                report.append("")

        # Recommendations
        recommendations = self._generate_recommendations(analysis)
        if recommendations:
            report.extend(["## Recommendations", ""])
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
        
        # SDP summary
        sdp_info = analysis.get("sdp_summary") or device_data.get("sdp_summary")
        if sdp_info:
            report.append("SDP DISCOVERY")
            if isinstance(sdp_info, dict):
                for svc in sdp_info.get("services_found", []):
                    report.append(f"- {svc}")
            elif isinstance(sdp_info, list):
                for rec in sdp_info:
                    report.append(f"- {rec.get('name', rec.get('uuid', 'unknown'))}")
            report.append("")

        # Pairing profile
        pp = analysis.get("pairing_profile") or device_data.get("pairing_profile")
        if pp and pp.get("attempted", pp.get("paired", False)):
            report.append("PAIRING PROFILE")
            report.append(f"Method: {pp.get('method', 'N/A')}")
            report.append(f"Paired: {'Yes' if pp.get('paired') else 'No'}")
            report.append("")

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
        
        report = {
            "device": device_data,
            "analysis": {
                "timestamp": datetime.now().isoformat(),
                "security_score": security_score,
                "vulnerabilities": vulnerabilities,
                "recommendations": recommendations,
            },
            "metadata": {
                "version": self._get_version(),
                "generator": "BLEEP AOI Analyzer",
            },
        }
        for v11_key in ("sdp_summary", "pairing_profile", "post_pair_delta"):
            val = analysis.get(v11_key) or device_data.get(v11_key)
            if val:
                report["analysis"][v11_key] = val

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
