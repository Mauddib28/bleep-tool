# Real-World Usage Scenarios for BLEEP Observation Database

This document provides practical, real-world examples of how to use the BLEEP observation database for various use cases, from long-term monitoring to enterprise device tracking and security assessments.

## Table of Contents

1. [Long-Term Device Monitoring Workflows](#long-term-device-monitoring-workflows)
2. [Enterprise Device Tracking Patterns](#enterprise-device-tracking-patterns)
3. [Security Assessment Workflows](#security-assessment-workflows)
4. [Integration Examples with External Systems](#integration-examples-with-external-systems)

---

## Long-Term Device Monitoring Workflows

### Scenario 1: Continuous Device Presence Monitoring

**Use Case**: Monitor a facility for Bluetooth devices over time, tracking when devices appear, disappear, and their signal strength patterns.

```python
#!/usr/bin/env python3
"""
Long-term device presence monitoring script.
Runs periodic scans and tracks device presence patterns.
"""

import time
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from bleep.core.observations import get_devices, get_device_detail
from bleep.ble_ops.scan import passive_scan_and_connect

DB_PATH = Path.home() / ".bleep" / "observations.db"
SCAN_INTERVAL = 300  # 5 minutes
MONITORING_DURATION_HOURS = 24

def monitor_device_presence():
    """Monitor devices over a specified duration."""
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=MONITORING_DURATION_HOURS)
    
    print(f"[*] Starting device presence monitoring")
    print(f"[*] Duration: {MONITORING_DURATION_HOURS} hours")
    print(f"[*] Scan interval: {SCAN_INTERVAL} seconds")
    print(f"[*] Database: {DB_PATH}")
    
    scan_count = 0
    
    while datetime.now() < end_time:
        scan_count += 1
        print(f"\n[*] Scan #{scan_count} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Perform passive scan
            devices = passive_scan_and_connect(duration=10)
            print(f"[+] Discovered {len(devices)} devices")
            
            # Wait for next scan
            time.sleep(SCAN_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n[!] Monitoring interrupted by user")
            break
        except Exception as e:
            print(f"[-] Scan error: {e}")
            time.sleep(SCAN_INTERVAL)
    
    # Generate presence report
    generate_presence_report()

def generate_presence_report():
    """Generate a report of device presence patterns."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    print("\n" + "="*60)
    print("DEVICE PRESENCE REPORT")
    print("="*60)
    
    # Devices seen in last 24 hours
    query = """
        SELECT 
            mac,
            name,
            device_type,
            first_seen,
            last_seen,
            COUNT(DISTINCT DATE(ts)) as days_seen,
            AVG(rssi_last) as avg_rssi,
            MIN(rssi_min) as min_rssi,
            MAX(rssi_max) as max_rssi
        FROM devices d
        LEFT JOIN adv_reports a ON d.mac = a.mac
        WHERE d.last_seen >= datetime('now', '-24 hours')
        GROUP BY d.mac
        ORDER BY days_seen DESC, last_seen DESC
    """
    
    results = conn.execute(query).fetchall()
    
    print(f"\n[*] Devices seen in last 24 hours: {len(results)}")
    print(f"\n{'MAC Address':<18} {'Name':<20} {'Type':<8} {'Days':<6} {'Avg RSSI':<10} {'First Seen':<20} {'Last Seen':<20}")
    print("-" * 100)
    
    for row in results:
        print(f"{row['mac']:<18} {str(row['name'] or 'N/A')[:18]:<20} {row['device_type'] or 'unknown':<8} "
              f"{row['days_seen']:<6} {int(row['avg_rssi']) if row['avg_rssi'] else 'N/A':<10} "
              f"{row['first_seen']:<20} {row['last_seen']:<20}")
    
    conn.close()

if __name__ == "__main__":
    monitor_device_presence()
```

### Scenario 2: Device Behavior Analysis Over Time

**Use Case**: Track how device characteristics change over time, such as service availability, RSSI patterns, and characteristic value changes.

```python
#!/usr/bin/env python3
"""
Device behavior analysis over time.
Tracks characteristic value changes, service availability, and signal patterns.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from bleep.core.observations import get_characteristic_timeline, get_device_detail

DB_PATH = Path.home() / ".bleep" / "observations.db"

def analyze_device_behavior(mac_address: str, days: int = 7):
    """Analyze device behavior over specified time period."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    print(f"\n[*] Analyzing behavior for {mac_address}")
    print(f"[*] Time period: Last {days} days")
    print("="*60)
    
    # Get device detail
    device = get_device_detail(mac_address)
    if not device:
        print(f"[-] Device {mac_address} not found in database")
        return
    
    print(f"\n[*] Device: {device.get('name', 'Unknown')}")
    print(f"[*] Type: {device.get('device_type', 'unknown')}")
    print(f"[*] First seen: {device.get('first_seen')}")
    print(f"[*] Last seen: {device.get('last_seen')}")
    
    # Analyze characteristic value changes
    print("\n[*] Characteristic Value Changes:")
    timeline = get_characteristic_timeline(mac_address, limit=100)
    
    if timeline:
        # Group by characteristic
        char_changes = {}
        for entry in timeline:
            char_key = f"{entry['service_uuid']}/{entry['char_uuid']}"
            if char_key not in char_changes:
                char_changes[char_key] = []
            char_changes[char_key].append(entry)
        
        for char_key, entries in char_changes.items():
            print(f"\n  Characteristic: {char_key}")
            print(f"    Total reads: {len(entries)}")
            
            # Check for value changes
            values = [e['value'] for e in entries if e['value']]
            unique_values = len(set(values))
            if unique_values > 1:
                print(f"    [!] Value changed {unique_values} times")
                print(f"    Values: {[v.hex()[:20] + '...' if len(v) > 10 else v.hex() for v in set(values)[:5]]}")
            else:
                print(f"    [*] Value stable")
    
    # Analyze RSSI patterns
    print("\n[*] RSSI Patterns:")
    query = """
        SELECT 
            DATE(ts) as date,
            COUNT(*) as readings,
            AVG(rssi) as avg_rssi,
            MIN(rssi) as min_rssi,
            MAX(rssi) as max_rssi
        FROM adv_reports
        WHERE mac = ? AND ts >= datetime('now', '-{} days')
        GROUP BY DATE(ts)
        ORDER BY date DESC
    """.format(days)
    
    rssi_data = conn.execute(query, (mac_address,)).fetchall()
    
    if rssi_data:
        print(f"{'Date':<12} {'Readings':<10} {'Avg RSSI':<10} {'Min RSSI':<10} {'Max RSSI':<10}")
        print("-" * 60)
        for row in rssi_data:
            print(f"{row['date']:<12} {row['readings']:<10} {int(row['avg_rssi']):<10} "
                  f"{row['min_rssi']:<10} {row['max_rssi']:<10}")
    else:
        print("  No RSSI data available")
    
    # Analyze service availability
    print("\n[*] Service Availability:")
    query = """
        SELECT 
            uuid,
            name,
            first_seen,
            last_seen,
            COUNT(DISTINCT DATE(first_seen)) as days_available
        FROM services
        WHERE mac = ?
        GROUP BY uuid
        ORDER BY last_seen DESC
    """
    
    services = conn.execute(query, (mac_address,)).fetchall()
    
    if services:
        print(f"{'UUID':<38} {'Name':<30} {'Days Available':<15} {'Last Seen':<20}")
        print("-" * 100)
        for row in services:
            print(f"{row['uuid']:<38} {str(row['name'] or 'N/A')[:28]:<30} "
                  f"{row['days_available']:<15} {row['last_seen']:<20}")
    else:
        print("  No services found")
    
    conn.close()

if __name__ == "__main__":
    import sys
    mac = sys.argv[1] if len(sys.argv) > 1 else "AA:BB:CC:DD:EE:FF"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    analyze_device_behavior(mac, days)
```

### Scenario 3: Automated Daily Device Inventory

**Use Case**: Generate daily reports of all devices seen, with statistics and trends.

```python
#!/usr/bin/env python3
"""
Automated daily device inventory report.
Generates comprehensive daily reports of device activity.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from bleep.core.observations import get_devices, export_device_data

DB_PATH = Path.home() / ".bleep" / "observations.db"
REPORT_DIR = Path.home() / ".bleep" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

def generate_daily_inventory_report(date: datetime = None):
    """Generate daily inventory report for specified date (default: today)."""
    if date is None:
        date = datetime.now()
    
    date_str = date.strftime("%Y-%m-%d")
    report_file = REPORT_DIR / f"inventory_{date_str}.json"
    
    print(f"[*] Generating daily inventory report for {date_str}")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Get all devices seen on this date
    query = """
        SELECT DISTINCT d.*
        FROM devices d
        WHERE DATE(d.last_seen) = DATE(?)
           OR DATE(d.first_seen) = DATE(?)
           OR EXISTS (
               SELECT 1 FROM adv_reports a 
               WHERE a.mac = d.mac AND DATE(a.ts) = DATE(?)
           )
    """
    
    devices = conn.execute(query, (date_str, date_str, date_str)).fetchall()
    
    report = {
        "report_date": date_str,
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_devices": len(devices),
            "by_type": {},
            "by_manufacturer": {},
            "new_devices": 0,
            "returning_devices": 0
        },
        "devices": []
    }
    
    # Analyze devices
    for device_row in devices:
        mac = device_row['mac']
        device_detail = get_device_detail(mac)
        
        # Count by type
        device_type = device_row['device_type'] or 'unknown'
        report["summary"]["by_type"][device_type] = report["summary"]["by_type"].get(device_type, 0) + 1
        
        # Count by manufacturer
        if device_row['manufacturer_id']:
            mfg_id = f"0x{device_row['manufacturer_id']:04X}"
            report["summary"]["by_manufacturer"][mfg_id] = report["summary"]["by_manufacturer"].get(mfg_id, 0) + 1
        
        # Check if new device
        first_seen = datetime.fromisoformat(device_row['first_seen']) if device_row['first_seen'] else None
        if first_seen and first_seen.date() == date.date():
            report["summary"]["new_devices"] += 1
        else:
            report["summary"]["returning_devices"] += 1
        
        # Add device to report
        device_entry = {
            "mac": mac,
            "name": device_row['name'],
            "type": device_type,
            "first_seen": device_row['first_seen'],
            "last_seen": device_row['last_seen'],
            "rssi_stats": {
                "last": device_row['rssi_last'],
                "min": device_row['rssi_min'],
                "max": device_row['rssi_max']
            },
            "services_count": len(device_detail.get('services', [])),
            "characteristics_count": sum(len(s.get('characteristics', [])) for s in device_detail.get('services', []))
        }
        
        report["devices"].append(device_entry)
    
    # Save report
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"[+] Report saved to {report_file}")
    print(f"\n[*] Summary:")
    print(f"    Total devices: {report['summary']['total_devices']}")
    print(f"    New devices: {report['summary']['new_devices']}")
    print(f"    Returning devices: {report['summary']['returning_devices']}")
    print(f"    By type: {report['summary']['by_type']}")
    
    conn.close()
    return report

if __name__ == "__main__":
    generate_daily_inventory_report()
```

---

## Enterprise Device Tracking Patterns

### Scenario 4: Corporate Asset Tracking

**Use Case**: Track corporate Bluetooth-enabled assets (laptops, phones, IoT devices) across multiple locations.

```python
#!/usr/bin/env python3
"""
Corporate asset tracking system.
Tracks Bluetooth-enabled corporate assets with location and status information.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from bleep.core.observations import get_devices, get_device_detail, upsert_device

DB_PATH = Path.home() / ".bleep" / "observations.db"

class CorporateAssetTracker:
    """Track corporate Bluetooth assets."""
    
    def __init__(self, location: str):
        self.location = location
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        
        # Create asset registry table if it doesn't exist
        self._init_asset_registry()
    
    def _init_asset_registry(self):
        """Initialize asset registry table."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS asset_registry (
                mac TEXT PRIMARY KEY,
                asset_tag TEXT UNIQUE,
                asset_type TEXT,
                assigned_to TEXT,
                department TEXT,
                location TEXT,
                status TEXT,
                notes TEXT,
                registered_at DATETIME,
                last_updated DATETIME,
                FOREIGN KEY (mac) REFERENCES devices(mac)
            )
        """)
        self.conn.commit()
    
    def register_asset(self, mac: str, asset_tag: str, asset_type: str, 
                      assigned_to: str = None, department: str = None, 
                      notes: str = None) -> bool:
        """Register a corporate asset."""
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO asset_registry 
                (mac, asset_tag, asset_type, assigned_to, department, location, 
                 status, notes, registered_at, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, datetime('now'), datetime('now'))
            """, (mac, asset_tag, asset_type, assigned_to, department, 
                  self.location, notes))
            self.conn.commit()
            print(f"[+] Registered asset {asset_tag} ({mac})")
            return True
        except sqlite3.IntegrityError as e:
            print(f"[-] Registration failed: {e}")
            return False
    
    def get_asset_status(self, asset_tag: str = None, mac: str = None) -> Optional[Dict]:
        """Get asset status by tag or MAC."""
        if asset_tag:
            row = self.conn.execute(
                "SELECT * FROM asset_registry WHERE asset_tag = ?", 
                (asset_tag,)
            ).fetchone()
        elif mac:
            row = self.conn.execute(
                "SELECT * FROM asset_registry WHERE mac = ?", 
                (mac,)
            ).fetchone()
        else:
            return None
        
        if not row:
            return None
        
        # Get current device status from observation database
        device = get_device_detail(row['mac'])
        
        return {
            "asset_tag": row['asset_tag'],
            "mac": row['mac'],
            "asset_type": row['asset_type'],
            "assigned_to": row['assigned_to'],
            "department": row['department'],
            "location": row['location'],
            "status": row['status'],
            "last_seen": device.get('last_seen') if device else None,
            "is_present": device is not None and device.get('last_seen') is not None,
            "rssi": device.get('rssi_last') if device else None,
            "notes": row['notes']
        }
    
    def list_assets(self, department: str = None, status: str = None) -> List[Dict]:
        """List all assets, optionally filtered by department or status."""
        query = "SELECT * FROM asset_registry WHERE 1=1"
        params = []
        
        if department:
            query += " AND department = ?"
            params.append(department)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY asset_tag"
        
        rows = self.conn.execute(query, params).fetchall()
        
        assets = []
        for row in rows:
            device = get_device_detail(row['mac'])
            assets.append({
                "asset_tag": row['asset_tag'],
                "mac": row['mac'],
                "asset_type": row['asset_type'],
                "assigned_to": row['assigned_to'],
                "department": row['department'],
                "location": row['location'],
                "status": row['status'],
                "last_seen": device.get('last_seen') if device else None,
                "is_present": device is not None and device.get('last_seen') is not None
            })
        
        return assets
    
    def generate_asset_report(self) -> Dict:
        """Generate comprehensive asset report."""
        all_assets = self.list_assets()
        present_assets = [a for a in all_assets if a['is_present']]
        missing_assets = [a for a in all_assets if not a['is_present']]
        
        # Group by department
        by_department = {}
        for asset in all_assets:
            dept = asset['department'] or 'Unassigned'
            if dept not in by_department:
                by_department[dept] = {"total": 0, "present": 0, "missing": 0}
            by_department[dept]["total"] += 1
            if asset['is_present']:
                by_department[dept]["present"] += 1
            else:
                by_department[dept]["missing"] += 1
        
        return {
            "report_date": datetime.now().isoformat(),
            "location": self.location,
            "summary": {
                "total_assets": len(all_assets),
                "present": len(present_assets),
                "missing": len(missing_assets),
                "by_department": by_department
            },
            "present_assets": present_assets,
            "missing_assets": missing_assets
        }
    
    def close(self):
        """Close database connection."""
        self.conn.close()

# Example usage
if __name__ == "__main__":
    tracker = CorporateAssetTracker(location="Building A, Floor 3")
    
    # Register assets
    tracker.register_asset(
        mac="AA:BB:CC:DD:EE:01",
        asset_tag="LAPTOP-001",
        asset_type="Laptop",
        assigned_to="John Doe",
        department="Engineering",
        notes="Dell XPS 13"
    )
    
    tracker.register_asset(
        mac="AA:BB:CC:DD:EE:02",
        asset_tag="PHONE-042",
        asset_type="Mobile Phone",
        assigned_to="Jane Smith",
        department="Sales",
        notes="iPhone 14 Pro"
    )
    
    # Generate report
    report = tracker.generate_asset_report()
    print("\n" + "="*60)
    print("ASSET TRACKING REPORT")
    print("="*60)
    print(f"Location: {report['location']}")
    print(f"Total Assets: {report['summary']['total_assets']}")
    print(f"Present: {report['summary']['present']}")
    print(f"Missing: {report['summary']['missing']}")
    print(f"\nBy Department:")
    for dept, stats in report['summary']['by_department'].items():
        print(f"  {dept}: {stats['present']}/{stats['total']} present")
    
    tracker.close()
```

### Scenario 5: Multi-Location Device Correlation

**Use Case**: Track devices across multiple locations and correlate their presence patterns.

```python
#!/usr/bin/env python3
"""
Multi-location device correlation.
Tracks devices across multiple locations and identifies movement patterns.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from bleep.core.observations import get_devices

DB_PATH = Path.home() / ".bleep" / "observations.db"

class MultiLocationTracker:
    """Track devices across multiple locations."""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.locations = {}  # location_name -> DB path
    
    def add_location(self, name: str, db_path: Path):
        """Add a location to track."""
        if db_path.exists():
            self.locations[name] = db_path
            print(f"[+] Added location: {name} ({db_path})")
        else:
            print(f"[-] Database not found: {db_path}")
    
    def correlate_device_movement(self, mac: str, days: int = 7) -> Dict:
        """Correlate device presence across locations."""
        movement = {
            "mac": mac,
            "time_period_days": days,
            "locations": [],
            "movement_pattern": []
        }
        
        for location_name, db_path in self.locations.items():
            loc_conn = sqlite3.connect(db_path)
            loc_conn.row_factory = sqlite3.Row
            
            # Get device presence at this location
            query = """
                SELECT 
                    DATE(ts) as date,
                    COUNT(*) as sightings,
                    AVG(rssi) as avg_rssi,
                    MIN(ts) as first_seen,
                    MAX(ts) as last_seen
                FROM adv_reports
                WHERE mac = ? AND ts >= datetime('now', '-{} days')
                GROUP BY DATE(ts)
                ORDER BY date
            """.format(days)
            
            presence = loc_conn.execute(query, (mac,)).fetchall()
            
            if presence:
                movement["locations"].append({
                    "name": location_name,
                    "days_present": len(presence),
                    "presence_dates": [p['date'] for p in presence],
                    "avg_rssi": sum(p['avg_rssi'] for p in presence) / len(presence) if presence else None
                })
            
            loc_conn.close()
        
        # Identify movement pattern
        if len(movement["locations"]) > 1:
            movement["movement_pattern"] = "Multi-location device"
        elif len(movement["locations"]) == 1:
            movement["movement_pattern"] = "Single location"
        else:
            movement["movement_pattern"] = "Not detected"
        
        return movement
    
    def find_mobile_devices(self, days: int = 7, min_locations: int = 2) -> List[Dict]:
        """Find devices that appear in multiple locations."""
        mobile_devices = []
        
        # Get all unique MACs from all locations
        all_macs = set()
        for location_name, db_path in self.locations.items():
            loc_conn = sqlite3.connect(db_path)
            loc_conn.row_factory = sqlite3.Row
            
            query = """
                SELECT DISTINCT mac
                FROM adv_reports
                WHERE ts >= datetime('now', '-{} days')
            """.format(days)
            
            macs = [row['mac'] for row in loc_conn.execute(query).fetchall()]
            all_macs.update(macs)
            loc_conn.close()
        
        # Check each MAC across all locations
        for mac in all_macs:
            movement = self.correlate_device_movement(mac, days)
            if len(movement["locations"]) >= min_locations:
                mobile_devices.append(movement)
        
        return mobile_devices

# Example usage
if __name__ == "__main__":
    tracker = MultiLocationTracker()
    
    # Add multiple locations
    tracker.add_location("Building A", Path.home() / ".bleep" / "observations_building_a.db")
    tracker.add_location("Building B", Path.home() / ".bleep" / "observations_building_b.db")
    
    # Find mobile devices
    mobile = tracker.find_mobile_devices(days=7, min_locations=2)
    print(f"\n[*] Found {len(mobile)} devices appearing in multiple locations")
    
    for device in mobile[:5]:  # Show first 5
        print(f"\n  MAC: {device['mac']}")
        print(f"  Locations: {[loc['name'] for loc in device['locations']]}")
        print(f"  Pattern: {device['movement_pattern']}")
```

---

## Security Assessment Workflows

### Scenario 6: Automated Security Audit

**Use Case**: Automatically identify devices with security concerns based on AoI analysis and characteristic permissions.

```python
#!/usr/bin/env python3
"""
Automated security audit workflow.
Identifies devices with security concerns and generates audit reports.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from bleep.core.observations import get_aoi_analysis, get_devices, get_device_detail

DB_PATH = Path.home() / ".bleep" / "observations.db"
AUDIT_REPORT_DIR = Path.home() / ".bleep" / "audit_reports"
AUDIT_REPORT_DIR.mkdir(parents=True, exist_ok=True)

class SecurityAuditor:
    """Perform automated security audits."""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
    
    def audit_all_devices(self) -> Dict:
        """Audit all devices in the database."""
        devices = get_devices()
        
        audit_results = {
            "audit_date": datetime.now().isoformat(),
            "total_devices": len(devices),
            "devices_with_concerns": 0,
            "devices_without_analysis": 0,
            "findings": {
                "high_risk": [],
                "medium_risk": [],
                "low_risk": [],
                "info": []
            },
            "summary": {
                "insecure_characteristics": 0,
                "unusual_services": 0,
                "missing_encryption": 0,
                "excessive_permissions": 0
            }
        }
        
        for device in devices:
            mac = device['mac']
            aoi = get_aoi_analysis(mac)
            
            if not aoi:
                audit_results["devices_without_analysis"] += 1
                continue
            
            concerns = aoi.get('security_concerns', {})
            if concerns:
                audit_results["devices_with_concerns"] += 1
                
                # Categorize by risk level
                risk_level = self._assess_risk_level(concerns)
                finding = {
                    "mac": mac,
                    "name": device.get('name'),
                    "type": device.get('device_type'),
                    "concerns": concerns,
                    "recommendations": aoi.get('recommendations', [])
                }
                
                audit_results["findings"][risk_level].append(finding)
                
                # Update summary statistics
                if concerns.get('insecure_characteristics'):
                    audit_results["summary"]["insecure_characteristics"] += len(concerns['insecure_characteristics'])
                if concerns.get('unusual_services'):
                    audit_results["summary"]["unusual_services"] += len(concerns['unusual_services'])
                if concerns.get('missing_encryption'):
                    audit_results["summary"]["missing_encryption"] += 1
                if concerns.get('excessive_permissions'):
                    audit_results["summary"]["excessive_permissions"] += 1
        
        return audit_results
    
    def _assess_risk_level(self, concerns: Dict) -> str:
        """Assess overall risk level based on concerns."""
        high_risk_indicators = [
            'insecure_characteristics',
            'missing_encryption',
            'authentication_bypass'
        ]
        
        medium_risk_indicators = [
            'excessive_permissions',
            'unusual_services'
        ]
        
        for indicator in high_risk_indicators:
            if concerns.get(indicator):
                return "high_risk"
        
        for indicator in medium_risk_indicators:
            if concerns.get(indicator):
                return "medium_risk"
        
        return "low_risk" if concerns else "info"
    
    def generate_audit_report(self, audit_results: Dict = None) -> Path:
        """Generate audit report file."""
        if audit_results is None:
            audit_results = self.audit_all_devices()
        
        report_file = AUDIT_REPORT_DIR / f"security_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(report_file, 'w') as f:
            json.dump(audit_results, f, indent=2, default=str)
        
        # Also generate human-readable summary
        summary_file = report_file.with_suffix('.txt')
        with open(summary_file, 'w') as f:
            f.write("="*60 + "\n")
            f.write("SECURITY AUDIT REPORT\n")
            f.write("="*60 + "\n\n")
            f.write(f"Audit Date: {audit_results['audit_date']}\n")
            f.write(f"Total Devices: {audit_results['total_devices']}\n")
            f.write(f"Devices with Concerns: {audit_results['devices_with_concerns']}\n")
            f.write(f"Devices without Analysis: {audit_results['devices_without_analysis']}\n\n")
            
            f.write("Summary:\n")
            f.write(f"  Insecure Characteristics: {audit_results['summary']['insecure_characteristics']}\n")
            f.write(f"  Unusual Services: {audit_results['summary']['unusual_services']}\n")
            f.write(f"  Missing Encryption: {audit_results['summary']['missing_encryption']}\n")
            f.write(f"  Excessive Permissions: {audit_results['summary']['excessive_permissions']}\n\n")
            
            f.write("High Risk Devices:\n")
            for finding in audit_results['findings']['high_risk']:
                f.write(f"  {finding['mac']} - {finding.get('name', 'Unknown')}\n")
                for concern_type, details in finding['concerns'].items():
                    f.write(f"    - {concern_type}: {details}\n")
            
            f.write("\nMedium Risk Devices:\n")
            for finding in audit_results['findings']['medium_risk']:
                f.write(f"  {finding['mac']} - {finding.get('name', 'Unknown')}\n")
        
        print(f"[+] Audit report saved to {report_file}")
        print(f"[+] Summary saved to {summary_file}")
        
        return report_file
    
    def find_vulnerable_characteristics(self) -> List[Dict]:
        """Find characteristics with security vulnerabilities."""
        query = """
            SELECT DISTINCT
                c.mac,
                d.name as device_name,
                s.uuid as service_uuid,
                c.uuid as char_uuid,
                c.properties,
                c.permission_map
            FROM characteristics c
            JOIN services s ON c.service_id = s.id
            JOIN devices d ON s.mac = d.mac
            WHERE c.permission_map LIKE '%write_without_response%'
               OR c.permission_map LIKE '%write_no_response%'
               OR (c.permission_map NOT LIKE '%encrypted%' AND c.permission_map LIKE '%write%')
        """
        
        results = self.conn.execute(query).fetchall()
        
        vulnerable = []
        for row in results:
            vulnerable.append({
                "mac": row['mac'],
                "device_name": row['device_name'],
                "service_uuid": row['service_uuid'],
                "char_uuid": row['char_uuid'],
                "properties": row['properties'],
                "permission_map": row['permission_map'],
                "risk": "High" if "encrypted" not in row['permission_map'] else "Medium"
            })
        
        return vulnerable
    
    def close(self):
        """Close database connection."""
        self.conn.close()

# Example usage
if __name__ == "__main__":
    auditor = SecurityAuditor()
    
    # Perform audit
    print("[*] Performing security audit...")
    audit_results = auditor.audit_all_devices()
    
    # Generate report
    report_file = auditor.generate_audit_report(audit_results)
    
    # Find vulnerable characteristics
    print("\n[*] Finding vulnerable characteristics...")
    vulnerable = auditor.find_vulnerable_characteristics()
    print(f"[+] Found {len(vulnerable)} vulnerable characteristics")
    
    for vuln in vulnerable[:5]:  # Show first 5
        print(f"  {vuln['mac']} - {vuln['char_uuid']} ({vuln['risk']} risk)")
    
    auditor.close()
```

### Scenario 7: Threat Detection and Alerting

**Use Case**: Monitor for suspicious devices and generate alerts based on behavior patterns.

```python
#!/usr/bin/env python3
"""
Threat detection and alerting system.
Monitors for suspicious devices and generates alerts.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from bleep.core.observations import get_devices, get_device_detail

DB_PATH = Path.home() / ".bleep" / "observations.db"

class ThreatDetector:
    """Detect threats based on device behavior patterns."""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.whitelist = set()  # Known good devices
        self.blacklist = set()  # Known bad devices
    
    def add_to_whitelist(self, mac: str):
        """Add device to whitelist."""
        self.whitelist.add(mac.upper())
    
    def add_to_blacklist(self, mac: str):
        """Add device to blacklist."""
        self.blacklist.add(mac.upper())
    
    def detect_new_devices(self, hours: int = 24) -> List[Dict]:
        """Detect devices seen for the first time."""
        query = """
            SELECT mac, name, device_type, first_seen, last_seen
            FROM devices
            WHERE first_seen >= datetime('now', '-{} hours')
              AND mac NOT IN ({})
            ORDER BY first_seen DESC
        """.format(hours, ','.join('?' * len(self.whitelist)) or 'NULL')
        
        params = list(self.whitelist) if self.whitelist else []
        results = self.conn.execute(query, params).fetchall()
        
        alerts = []
        for row in results:
            alerts.append({
                "type": "new_device",
                "severity": "medium",
                "mac": row['mac'],
                "name": row['name'],
                "device_type": row['device_type'],
                "first_seen": row['first_seen'],
                "message": f"New device detected: {row['mac']} ({row['name'] or 'Unknown'})"
            })
        
        return alerts
    
    def detect_blacklisted_devices(self) -> List[Dict]:
        """Detect blacklisted devices."""
        if not self.blacklist:
            return []
        
        placeholders = ','.join('?' * len(self.blacklist))
        query = f"""
            SELECT mac, name, device_type, last_seen
            FROM devices
            WHERE mac IN ({placeholders})
              AND last_seen >= datetime('now', '-24 hours')
        """
        
        results = self.conn.execute(query, list(self.blacklist)).fetchall()
        
        alerts = []
        for row in results:
            alerts.append({
                "type": "blacklisted_device",
                "severity": "high",
                "mac": row['mac'],
                "name": row['name'],
                "device_type": row['device_type'],
                "last_seen": row['last_seen'],
                "message": f"BLACKLISTED device detected: {row['mac']}"
            })
        
        return alerts
    
    def detect_anomalous_behavior(self, mac: str, days: int = 7) -> List[Dict]:
        """Detect anomalous behavior patterns."""
        alerts = []
        
        # Check for unusual service changes
        query = """
            SELECT COUNT(DISTINCT uuid) as service_count
            FROM services
            WHERE mac = ? AND first_seen >= datetime('now', '-{} days')
        """.format(days)
        
        result = self.conn.execute(query, (mac,)).fetchone()
        if result and result['service_count'] > 10:
            alerts.append({
                "type": "anomalous_services",
                "severity": "medium",
                "mac": mac,
                "message": f"Device has {result['service_count']} new services in last {days} days"
            })
        
        # Check for rapid RSSI changes (potential movement/spoofing)
        query = """
            SELECT 
                AVG(rssi) as avg_rssi,
                MIN(rssi) as min_rssi,
                MAX(rssi) as max_rssi
            FROM adv_reports
            WHERE mac = ? AND ts >= datetime('now', '-{} days')
        """.format(days)
        
        result = self.conn.execute(query, (mac,)).fetchone()
        if result and result['max_rssi'] - result['min_rssi'] > 40:
            alerts.append({
                "type": "rssi_anomaly",
                "severity": "low",
                "mac": mac,
                "message": f"Large RSSI variation detected ({result['min_rssi']} to {result['max_rssi']} dBm)"
            })
        
        return alerts
    
    def generate_threat_report(self) -> Dict:
        """Generate comprehensive threat detection report."""
        report = {
            "report_date": datetime.now().isoformat(),
            "alerts": [],
            "summary": {
                "total_alerts": 0,
                "by_severity": {"high": 0, "medium": 0, "low": 0},
                "by_type": {}
            }
        }
        
        # Detect new devices
        new_devices = self.detect_new_devices()
        report["alerts"].extend(new_devices)
        
        # Detect blacklisted devices
        blacklisted = self.detect_blacklisted_devices()
        report["alerts"].extend(blacklisted)
        
        # Check for anomalous behavior on all recent devices
        recent_devices = get_devices(status='recent')
        for device in recent_devices[:20]:  # Limit to first 20 for performance
            anomalies = self.detect_anomalous_behavior(device['mac'])
            report["alerts"].extend(anomalies)
        
        # Generate summary
        for alert in report["alerts"]:
            report["summary"]["total_alerts"] += 1
            report["summary"]["by_severity"][alert["severity"]] = \
                report["summary"]["by_severity"].get(alert["severity"], 0) + 1
            alert_type = alert["type"]
            report["summary"]["by_type"][alert_type] = \
                report["summary"]["by_type"].get(alert_type, 0) + 1
        
        return report
    
    def close(self):
        """Close database connection."""
        self.conn.close()

# Example usage
if __name__ == "__main__":
    detector = ThreatDetector()
    
    # Add known good devices to whitelist
    detector.add_to_whitelist("AA:BB:CC:DD:EE:01")
    detector.add_to_whitelist("AA:BB:CC:DD:EE:02")
    
    # Add known bad devices to blacklist
    detector.add_to_blacklist("FF:FF:FF:FF:FF:FF")
    
    # Generate threat report
    print("[*] Generating threat detection report...")
    report = detector.generate_threat_report()
    
    print(f"\n[*] Threat Detection Report")
    print(f"    Total Alerts: {report['summary']['total_alerts']}")
    print(f"    High Severity: {report['summary']['by_severity']['high']}")
    print(f"    Medium Severity: {report['summary']['by_severity']['medium']}")
    print(f"    Low Severity: {report['summary']['by_severity']['low']}")
    
    print(f"\n[*] Alerts by Type:")
    for alert_type, count in report['summary']['by_type'].items():
        print(f"    {alert_type}: {count}")
    
    print(f"\n[*] Recent Alerts:")
    for alert in report['alerts'][:10]:
        print(f"    [{alert['severity'].upper()}] {alert['message']}")
    
    detector.close()
```

---

## Integration Examples with External Systems

### Scenario 8: Integration with SIEM Systems

**Use Case**: Export device data and security events to SIEM systems like Splunk, ELK, or Graylog.

```python
#!/usr/bin/env python3
"""
SIEM integration for BLEEP observation database.
Exports device data and security events to external SIEM systems.
"""

import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from bleep.core.observations import get_devices, get_aoi_analysis, export_device_data

class SIEMExporter:
    """Export BLEEP data to SIEM systems."""
    
    def __init__(self, siem_type: str = "splunk", endpoint: str = None, 
                 api_key: str = None):
        self.siem_type = siem_type.lower()
        self.endpoint = endpoint
        self.api_key = api_key
    
    def export_device_events(self, devices: List[Dict] = None, 
                           hours: int = 24) -> bool:
        """Export device events to SIEM."""
        if devices is None:
            devices = get_devices(status='recent')
        
        events = []
        for device in devices:
            event = {
                "timestamp": device.get('last_seen', datetime.now().isoformat()),
                "event_type": "bluetooth_device_detected",
                "source": "bleep",
                "device": {
                    "mac": device['mac'],
                    "name": device.get('name'),
                    "type": device.get('device_type'),
                    "rssi": device.get('rssi_last')
                }
            }
            events.append(event)
        
        return self._send_events(events)
    
    def export_security_events(self, hours: int = 24) -> bool:
        """Export security-related events to SIEM."""
        devices = get_devices(status='recent')
        
        events = []
        for device in devices:
            mac = device['mac']
            aoi = get_aoi_analysis(mac)
            
            if aoi and aoi.get('security_concerns'):
                event = {
                    "timestamp": datetime.now().isoformat(),
                    "event_type": "bluetooth_security_concern",
                    "source": "bleep",
                    "severity": "high" if aoi['security_concerns'].get('insecure_characteristics') else "medium",
                    "device": {
                        "mac": mac,
                        "name": device.get('name')
                    },
                    "concerns": aoi['security_concerns'],
                    "recommendations": aoi.get('recommendations', [])
                }
                events.append(event)
        
        return self._send_events(events)
    
    def _send_events(self, events: List[Dict]) -> bool:
        """Send events to SIEM system."""
        if self.siem_type == "splunk":
            return self._send_to_splunk(events)
        elif self.siem_type == "elk":
            return self._send_to_elk(events)
        elif self.siem_type == "graylog":
            return self._send_to_graylog(events)
        else:
            print(f"[-] Unsupported SIEM type: {self.siem_type}")
            return False
    
    def _send_to_splunk(self, events: List[Dict]) -> bool:
        """Send events to Splunk HEC (HTTP Event Collector)."""
        if not self.endpoint or not self.api_key:
            print("[-] Splunk endpoint and API key required")
            return False
        
        headers = {
            "Authorization": f"Splunk {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Splunk HEC expects events in specific format
        splunk_events = []
        for event in events:
            splunk_events.append({
                "time": event.get("timestamp", datetime.now().timestamp()),
                "event": event
            })
        
        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=splunk_events,
                timeout=10
            )
            response.raise_for_status()
            print(f"[+] Sent {len(events)} events to Splunk")
            return True
        except Exception as e:
            print(f"[-] Failed to send events to Splunk: {e}")
            return False
    
    def _send_to_elk(self, events: List[Dict]) -> bool:
        """Send events to ELK Stack (Elasticsearch)."""
        if not self.endpoint:
            print("[-] ELK endpoint required")
            return False
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            # ELK expects events in bulk format
            bulk_data = []
            for event in events:
                bulk_data.append(json.dumps({"index": {}}))
                bulk_data.append(json.dumps(event))
            
            response = requests.post(
                f"{self.endpoint}/_bulk",
                headers=headers,
                data="\n".join(bulk_data) + "\n",
                timeout=10
            )
            response.raise_for_status()
            print(f"[+] Sent {len(events)} events to ELK")
            return True
        except Exception as e:
            print(f"[-] Failed to send events to ELK: {e}")
            return False
    
    def _send_to_graylog(self, events: List[Dict]) -> bool:
        """Send events to Graylog GELF endpoint."""
        if not self.endpoint:
            print("[-] Graylog endpoint required")
            return False
        
        headers = {"Content-Type": "application/json"}
        
        try:
            # Graylog expects GELF format
            for event in events:
                gelf_event = {
                    "version": "1.1",
                    "host": "bleep",
                    "short_message": event.get("event_type", "bluetooth_event"),
                    "timestamp": datetime.now().timestamp(),
                    "level": 6,  # Info level
                    "_event_type": event.get("event_type"),
                    "_source": "bleep"
                }
                gelf_event.update(event)
                
                response = requests.post(
                    self.endpoint,
                    headers=headers,
                    json=gelf_event,
                    timeout=10
                )
                response.raise_for_status()
            
            print(f"[+] Sent {len(events)} events to Graylog")
            return True
        except Exception as e:
            print(f"[-] Failed to send events to Graylog: {e}")
            return False

# Example usage
if __name__ == "__main__":
    # Splunk integration
    splunk_exporter = SIEMExporter(
        siem_type="splunk",
        endpoint="https://splunk.example.com:8088/services/collector/event",
        api_key="your-splunk-hec-token"
    )
    splunk_exporter.export_device_events()
    splunk_exporter.export_security_events()
    
    # ELK integration
    elk_exporter = SIEMExporter(
        siem_type="elk",
        endpoint="https://elasticsearch.example.com:9200/bleep-events",
        api_key="your-elasticsearch-api-key"
    )
    elk_exporter.export_device_events()
```

### Scenario 9: REST API for Database Access

**Use Case**: Create a REST API to expose BLEEP observation database data to other systems.

```python
#!/usr/bin/env python3
"""
REST API for BLEEP observation database.
Provides HTTP API for accessing device data and statistics.
"""

from flask import Flask, jsonify, request
from datetime import datetime, timedelta
from bleep.core.observations import (
    get_devices, get_device_detail, get_characteristic_timeline,
    get_aoi_analysis, export_device_data
)

app = Flask(__name__)

@app.route('/api/v1/devices', methods=['GET'])
def list_devices():
    """List all devices with optional filtering."""
    status = request.args.get('status', 'all')
    device_type = request.args.get('type')
    limit = request.args.get('limit', type=int)
    
    devices = get_devices(status=status)
    
    if device_type:
        devices = [d for d in devices if d.get('device_type') == device_type]
    
    if limit:
        devices = devices[:limit]
    
    return jsonify({
        "count": len(devices),
        "devices": devices
    })

@app.route('/api/v1/devices/<mac>', methods=['GET'])
def get_device(mac: str):
    """Get detailed information about a specific device."""
    device = get_device_detail(mac)
    
    if not device:
        return jsonify({"error": "Device not found"}), 404
    
    return jsonify(device)

@app.route('/api/v1/devices/<mac>/timeline', methods=['GET'])
def get_device_timeline(mac: str):
    """Get characteristic timeline for a device."""
    service_uuid = request.args.get('service')
    char_uuid = request.args.get('char')
    limit = request.args.get('limit', type=int, default=100)
    
    timeline = get_characteristic_timeline(
        mac, 
        service_uuid=service_uuid,
        char_uuid=char_uuid,
        limit=limit
    )
    
    return jsonify({
        "count": len(timeline),
        "timeline": timeline
    })

@app.route('/api/v1/devices/<mac>/security', methods=['GET'])
def get_device_security(mac: str):
    """Get security analysis for a device."""
    aoi = get_aoi_analysis(mac)
    
    if not aoi:
        return jsonify({"error": "No security analysis available"}), 404
    
    return jsonify(aoi)

@app.route('/api/v1/devices/<mac>/export', methods=['GET'])
def export_device(mac: str):
    """Export complete device data."""
    format_type = request.args.get('format', 'json')
    
    device_data = export_device_data(mac)
    
    if not device_data:
        return jsonify({"error": "Device not found"}), 404
    
    if format_type == 'json':
        return jsonify(device_data)
    else:
        return jsonify({"error": "Unsupported format"}), 400

@app.route('/api/v1/statistics', methods=['GET'])
def get_statistics():
    """Get database statistics."""
    devices = get_devices()
    
    stats = {
        "total_devices": len(devices),
        "by_type": {},
        "recent_devices": len([d for d in devices if d.get('last_seen')]),
        "devices_with_analysis": 0
    }
    
    for device in devices:
        device_type = device.get('device_type', 'unknown')
        stats["by_type"][device_type] = stats["by_type"].get(device_type, 0) + 1
        
        if get_aoi_analysis(device['mac']):
            stats["devices_with_analysis"] += 1
    
    return jsonify(stats)

@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.4.6"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```

### Scenario 10: Database Backup and Sync

**Use Case**: Backup and synchronize observation database across multiple systems.

```python
#!/usr/bin/env python3
"""
Database backup and synchronization.
Backs up and syncs observation database across systems.
"""

import sqlite3
import shutil
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from bleep.core.observations import get_devices, export_device_data

DB_PATH = Path.home() / ".bleep" / "observations.db"
BACKUP_DIR = Path.home() / ".bleep" / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

class DatabaseBackup:
    """Handle database backup and synchronization."""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
    
    def create_backup(self, backup_name: str = None) -> Path:
        """Create a full database backup."""
        if backup_name is None:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        backup_path = BACKUP_DIR / backup_name
        
        # SQLite backup
        source_conn = sqlite3.connect(self.db_path)
        backup_conn = sqlite3.connect(backup_path)
        
        source_conn.backup(backup_conn)
        
        source_conn.close()
        backup_conn.close()
        
        print(f"[+] Backup created: {backup_path}")
        return backup_path
    
    def export_to_json(self, output_path: Path = None) -> Path:
        """Export all device data to JSON."""
        if output_path is None:
            output_path = BACKUP_DIR / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        devices = get_devices()
        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_devices": len(devices),
            "devices": []
        }
        
        for device in devices:
            device_data = export_device_data(device['mac'])
            if device_data:
                export_data["devices"].append(device_data)
        
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        print(f"[+] Export created: {output_path}")
        return output_path
    
    def restore_from_backup(self, backup_path: Path) -> bool:
        """Restore database from backup."""
        if not backup_path.exists():
            print(f"[-] Backup file not found: {backup_path}")
            return False
        
        # Create backup of current database first
        current_backup = self.create_backup(f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        
        try:
            # Restore from backup
            shutil.copy(backup_path, self.db_path)
            print(f"[+] Database restored from {backup_path}")
            return True
        except Exception as e:
            print(f"[-] Restore failed: {e}")
            # Restore from current backup
            shutil.copy(current_backup, self.db_path)
            print(f"[+] Restored previous database state")
            return False
    
    def sync_devices(self, source_db: Path) -> Dict:
        """Synchronize devices from source database."""
        if not source_db.exists():
            return {"error": "Source database not found"}
        
        source_conn = sqlite3.connect(source_db)
        source_conn.row_factory = sqlite3.Row
        
        target_conn = sqlite3.connect(self.db_path)
        target_conn.row_factory = sqlite3.Row
        
        # Get devices from source
        source_devices = source_conn.execute("SELECT * FROM devices").fetchall()
        
        synced = 0
        for device_row in source_devices:
            # Insert or update device
            target_conn.execute("""
                INSERT OR REPLACE INTO devices 
                (mac, addr_type, name, appearance, device_class, manufacturer_id,
                 manufacturer_data, rssi_last, rssi_min, rssi_max, first_seen, last_seen, notes, device_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_row['mac'], device_row.get('addr_type'), device_row.get('name'),
                device_row.get('appearance'), device_row.get('device_class'),
                device_row.get('manufacturer_id'), device_row.get('manufacturer_data'),
                device_row.get('rssi_last'), device_row.get('rssi_min'),
                device_row.get('rssi_max'), device_row.get('first_seen'),
                device_row.get('last_seen'), device_row.get('notes'),
                device_row.get('device_type')
            ))
            synced += 1
        
        target_conn.commit()
        source_conn.close()
        target_conn.close()
        
        print(f"[+] Synchronized {synced} devices from {source_db}")
        return {"synced": synced}

# Example usage
if __name__ == "__main__":
    backup = DatabaseBackup()
    
    # Create backup
    backup_path = backup.create_backup()
    
    # Export to JSON
    json_path = backup.export_to_json()
    
    # Sync from another database
    # backup.sync_devices(Path("/path/to/source.db"))
```

---

## Summary

These real-world usage scenarios demonstrate how the BLEEP observation database can be used for:

1. **Long-term monitoring**: Track device presence, behavior patterns, and generate daily reports
2. **Enterprise tracking**: Manage corporate assets, track devices across locations, and generate inventory reports
3. **Security assessment**: Automate security audits, detect threats, and identify vulnerable devices
4. **System integration**: Export data to SIEM systems, create REST APIs, and synchronize databases

Each scenario includes complete, working code examples that can be adapted to specific use cases. The examples follow BLEEP's coding patterns and leverage the full capabilities of the observation database module.

