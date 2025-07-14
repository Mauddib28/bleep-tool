#!/usr/bin/env python3
"""Test Mode for BLEEP.

This mode provides automated test functionality for D-Bus interfaces,
mock device interaction, automated test sequences, and result reporting.

Usage:
  python -m bleep -m test [options]

Options:
  --suite <name>      Test suite to run (default: all)
  --device <mac>      Target real device for testing (if applicable)
  --mock              Use mock devices instead of real hardware
  --verbose           Increase output verbosity
  --report <file>     Write test results to file
"""

import argparse
import time
import sys
import os
import json
from typing import Dict, List, Any, Optional, Tuple

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter
from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
from bleep.ble_ops.scan import passive_scan
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum

# Test result constants
TEST_PASS = "PASS"
TEST_FAIL = "FAIL"
TEST_SKIP = "SKIP"
TEST_ERROR = "ERROR"

class TestResult:
    """Class to store test results."""
    def __init__(self, name: str, status: str, message: str = "", duration: float = 0.0):
        self.name = name
        self.status = status
        self.message = message
        self.duration = duration
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert test result to dictionary."""
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "duration": self.duration,
            "timestamp": self.timestamp
        }

class TestSuite:
    """Base class for test suites."""
    def __init__(self, name: str, device_mac: Optional[str] = None, use_mock: bool = False):
        self.name = name
        self.device_mac = device_mac
        self.use_mock = use_mock
        self.results: List[TestResult] = []
        self.device = None
        self.mapping = None
    
    def setup(self) -> bool:
        """Set up the test suite."""
        print_and_log(f"[*] Setting up test suite: {self.name}", LOG__GENERAL)
        return True
    
    def teardown(self) -> None:
        """Clean up after the test suite."""
        print_and_log(f"[*] Tearing down test suite: {self.name}", LOG__GENERAL)
        if self.device and hasattr(self.device, "disconnect"):
            try:
                self.device.disconnect()
            except:
                pass
    
    def run_test(self, test_name: str) -> TestResult:
        """Run a single test."""
        test_method = getattr(self, f"test_{test_name}", None)
        if not test_method:
            return TestResult(test_name, TEST_SKIP, "Test not found")
        
        print_and_log(f"[*] Running test: {test_name}", LOG__GENERAL)
        start_time = time.time()
        
        try:
            result = test_method()
            duration = time.time() - start_time
            
            if isinstance(result, tuple) and len(result) == 2:
                status, message = result
            else:
                status = TEST_PASS if result else TEST_FAIL
                message = ""
            
            return TestResult(test_name, status, message, duration)
        
        except Exception as exc:
            duration = time.time() - start_time
            return TestResult(test_name, TEST_ERROR, str(exc), duration)
    
    def run_all_tests(self) -> List[TestResult]:
        """Run all tests in the suite."""
        self.results = []
        
        # Set up the test suite
        if not self.setup():
            self.results.append(TestResult("setup", TEST_ERROR, "Setup failed"))
            return self.results
        
        # Find all test methods
        test_methods = [name[5:] for name in dir(self) if name.startswith("test_")]
        
        # Run each test
        for test_name in test_methods:
            result = self.run_test(test_name)
            self.results.append(result)
        
        # Clean up
        self.teardown()
        
        return self.results
    
    def print_results(self) -> None:
        """Print test results to console."""
        print("\nTest Results:")
        print(f"Suite: {self.name}")
        print("-" * 60)
        
        pass_count = 0
        fail_count = 0
        skip_count = 0
        error_count = 0
        
        for result in self.results:
            status_str = {
                TEST_PASS: "\033[92mPASS\033[0m",  # Green
                TEST_FAIL: "\033[91mFAIL\033[0m",  # Red
                TEST_SKIP: "\033[93mSKIP\033[0m",  # Yellow
                TEST_ERROR: "\033[91mERROR\033[0m"  # Red
            }.get(result.status, result.status)
            
            print(f"{result.name:<30} {status_str:<10} {result.duration:.3f}s")
            
            if result.message:
                print(f"  {result.message}")
            
            if result.status == TEST_PASS:
                pass_count += 1
            elif result.status == TEST_FAIL:
                fail_count += 1
            elif result.status == TEST_SKIP:
                skip_count += 1
            elif result.status == TEST_ERROR:
                error_count += 1
        
        print("-" * 60)
        print(f"Total: {len(self.results)}, Pass: {pass_count}, Fail: {fail_count}, Skip: {skip_count}, Error: {error_count}")
        print()

class DBusInterfaceTestSuite(TestSuite):
    """Test suite for D-Bus interfaces."""
    def __init__(self, device_mac: Optional[str] = None, use_mock: bool = False):
        super().__init__("DBusInterfaceTests", device_mac, use_mock)
    
    def setup(self) -> bool:
        """Set up the test suite."""
        if not super().setup():
            return False
        
        if self.use_mock:
            # Set up mock device
            print_and_log("[*] Using mock device for testing", LOG__GENERAL)
            self.device = self._create_mock_device()
            self.mapping = {}
            return True
        
        if not self.device_mac:
            print_and_log("[-] No device MAC address specified for real device testing", LOG__DEBUG)
            return False
        
        # Connect to real device
        try:
            print_and_log(f"[*] Connecting to {self.device_mac}...", LOG__GENERAL)
            self.device, self.mapping, _, _ = _connect_enum(self.device_mac)
            print_and_log(f"[+] Connected to {self.device_mac}", LOG__GENERAL)
            return True
        except Exception as exc:
            print_and_log(f"[-] Connection failed: {exc}", LOG__DEBUG)
            return False
    
    def _create_mock_device(self):
        """Create a mock device for testing."""
        # This is a simple mock implementation
        class MockDevice:
            def __init__(self):
                self.mac_address = "00:11:22:33:44:55"
                self._connected = True
                self._name = "Mock Device"
                self._alias = "Mock Device"
                self._address_type = "public"
                self._rssi = -60
            
            def disconnect(self):
                self._connected = False
            
            def get_name(self):
                return self._name
            
            def get_alias(self):
                return self._alias
            
            def get_address_type(self):
                return self._address_type
            
            def get_rssi(self):
                return self._rssi
            
            def is_connected(self):
                return self._connected
            
            def is_paired(self):
                return False
            
            def is_trusted(self):
                return False
            
            def is_blocked(self):
                return False
            
            def is_legacy_pairing(self):
                return False
            
            def services_resolved(self):
                return True
        
        return MockDevice()
    
    def test_device_properties(self):
        """Test basic device properties."""
        if not self.device:
            return TEST_SKIP, "No device available"
        
        try:
            # Check basic properties
            name = self.device.get_name()
            alias = self.device.get_alias()
            address_type = self.device.get_address_type()
            
            # Basic validation
            if not isinstance(name, str) and name is not None:
                return TEST_FAIL, f"Invalid name type: {type(name)}"
            
            if not isinstance(alias, str) and alias is not None:
                return TEST_FAIL, f"Invalid alias type: {type(alias)}"
            
            if address_type not in ["public", "random"]:
                return TEST_FAIL, f"Invalid address type: {address_type}"
            
            return TEST_PASS, "Device properties validated"
        
        except Exception as exc:
            return TEST_ERROR, f"Error accessing device properties: {exc}"
    
    def test_connection_state(self):
        """Test device connection state."""
        if not self.device:
            return TEST_SKIP, "No device available"
        
        try:
            # Check connection state
            is_connected = self.device.is_connected()
            
            if not is_connected:
                return TEST_FAIL, "Device is not connected"
            
            return TEST_PASS, "Device is connected"
        
        except Exception as exc:
            return TEST_ERROR, f"Error checking connection state: {exc}"
    
    def test_services_resolved(self):
        """Test if services are resolved."""
        if not self.device:
            return TEST_SKIP, "No device available"
        
        try:
            # Check if services are resolved
            resolved = self.device.services_resolved()
            
            if not resolved:
                return TEST_FAIL, "Services not resolved"
            
            return TEST_PASS, "Services resolved"
        
        except Exception as exc:
            return TEST_ERROR, f"Error checking services resolved: {exc}"

class GATTTestSuite(TestSuite):
    """Test suite for GATT operations."""
    def __init__(self, device_mac: Optional[str] = None, use_mock: bool = False):
        super().__init__("GATTTests", device_mac, use_mock)
    
    def setup(self) -> bool:
        """Set up the test suite."""
        if not super().setup():
            return False
        
        if self.use_mock:
            # Set up mock device and mapping
            print_and_log("[*] Using mock GATT data for testing", LOG__GENERAL)
            self.device = self._create_mock_device()
            self.mapping = self._create_mock_mapping()
            return True
        
        if not self.device_mac:
            print_and_log("[-] No device MAC address specified for real device testing", LOG__DEBUG)
            return False
        
        # Connect to real device
        try:
            print_and_log(f"[*] Connecting to {self.device_mac}...", LOG__GENERAL)
            self.device, self.mapping, _, _ = _connect_enum(self.device_mac)
            print_and_log(f"[+] Connected to {self.device_mac}", LOG__GENERAL)
            return True
        except Exception as exc:
            print_and_log(f"[-] Connection failed: {exc}", LOG__DEBUG)
            return False
    
    def _create_mock_device(self):
        """Create a mock device for testing."""
        # Simple mock implementation
        class MockDevice:
            def __init__(self):
                self.mac_address = "00:11:22:33:44:55"
            
            def disconnect(self):
                pass
            
            def _find_characteristic(self, char_id, mapping):
                # Mock characteristic
                class MockCharacteristic:
                    def __init__(self, uuid):
                        self.uuid = uuid
                    
                    def ReadValue(self, options):
                        return [0x48, 0x65, 0x6c, 0x6c, 0x6f]  # "Hello" in ASCII
                    
                    def WriteValue(self, value, options):
                        pass
                
                return MockCharacteristic(char_id)
        
        return MockDevice()
    
    def _create_mock_mapping(self):
        """Create mock GATT mapping."""
        return {
            "00001800-0000-1000-8000-00805f9b34fb": {
                "Service": "/org/bluez/hci0/dev_00_11_22_33_44_55/service0001",
                "Characteristics": {
                    "00002a00-0000-1000-8000-00805f9b34fb": {
                        "UUID": "00002a00-0000-1000-8000-00805f9b34fb",
                        "Handle": 3,
                        "Properties": ["read"],
                        "Path": "/org/bluez/hci0/dev_00_11_22_33_44_55/service0001/char0002"
                    }
                }
            },
            "00001801-0000-1000-8000-00805f9b34fb": {
                "Service": "/org/bluez/hci0/dev_00_11_22_33_44_55/service0004",
                "Characteristics": {
                    "00002a05-0000-1000-8000-00805f9b34fb": {
                        "UUID": "00002a05-0000-1000-8000-00805f9b34fb",
                        "Handle": 5,
                        "Properties": ["indicate"],
                        "Path": "/org/bluez/hci0/dev_00_11_22_33_44_55/service0004/char0005"
                    }
                }
            }
        }
    
    def test_mapping_structure(self):
        """Test GATT mapping structure."""
        if not self.mapping:
            return TEST_SKIP, "No GATT mapping available"
        
        try:
            # Check if mapping is a dictionary
            if not isinstance(self.mapping, dict):
                return TEST_FAIL, f"Mapping is not a dictionary: {type(self.mapping)}"
            
            # Check if mapping has services
            if len(self.mapping) == 0:
                return TEST_FAIL, "Mapping has no services"
            
            # Check service structure
            for service_uuid, service_info in self.mapping.items():
                # Check if service has a path
                if "Service" not in service_info:
                    return TEST_FAIL, f"Service {service_uuid} has no path"
                
                # Check if service has characteristics
                if "Characteristics" not in service_info:
                    return TEST_FAIL, f"Service {service_uuid} has no characteristics"
            
            return TEST_PASS, f"Mapping structure valid with {len(self.mapping)} services"
        
        except Exception as exc:
            return TEST_ERROR, f"Error checking mapping structure: {exc}"
    
    def test_read_characteristic(self):
        """Test reading a characteristic."""
        if not self.device or not self.mapping:
            return TEST_SKIP, "No device or mapping available"
        
        try:
            # Find a readable characteristic
            readable_char = None
            for service_uuid, service_info in self.mapping.items():
                for char_uuid, char_info in service_info.get("Characteristics", {}).items():
                    if "read" in char_info.get("Properties", []):
                        readable_char = char_uuid
                        break
                if readable_char:
                    break
            
            if not readable_char:
                return TEST_SKIP, "No readable characteristic found"
            
            # Read the characteristic
            char = self.device._find_characteristic(readable_char, self.mapping)
            
            if not char:
                return TEST_FAIL, f"Characteristic not found: {readable_char}"
            
            value = char.ReadValue({})
            
            # Check if value is valid
            if not value:
                return TEST_FAIL, "Read returned empty value"
            
            return TEST_PASS, f"Successfully read characteristic {readable_char}"
        
        except Exception as exc:
            return TEST_ERROR, f"Error reading characteristic: {exc}"

class AdapterTestSuite(TestSuite):
    """Test suite for adapter operations."""
    def __init__(self, use_mock: bool = False):
        super().__init__("AdapterTests", None, use_mock)
        self.adapter = None
    
    def setup(self) -> bool:
        """Set up the test suite."""
        if not super().setup():
            return False
        
        try:
            self.adapter = system_dbus__bluez_adapter()
            return True
        except Exception as exc:
            print_and_log(f"[-] Failed to initialize adapter: {exc}", LOG__DEBUG)
            return False
    
    def test_adapter_properties(self):
        """Test adapter properties."""
        if not self.adapter:
            return TEST_SKIP, "No adapter available"
        
        try:
            # Check basic properties
            address = self.adapter.get_address()
            name = self.adapter.get_name()
            powered = self.adapter.is_powered()
            
            # Basic validation
            if not isinstance(address, str):
                return TEST_FAIL, f"Invalid address type: {type(address)}"
            
            if not isinstance(name, str) and name is not None:
                return TEST_FAIL, f"Invalid name type: {type(name)}"
            
            return TEST_PASS, f"Adapter properties valid: {address}, powered: {powered}"
        
        except Exception as exc:
            return TEST_ERROR, f"Error checking adapter properties: {exc}"
    
    def test_discovery(self):
        """Test device discovery."""
        if not self.adapter:
            return TEST_SKIP, "No adapter available"
        
        try:
            # Check if adapter is powered
            if not self.adapter.is_powered():
                return TEST_SKIP, "Adapter is not powered on"
            
            # Start discovery
            self.adapter.start_discovery()
            
            # Wait a bit
            time.sleep(2)
            
            # Check if discovery is active
            discovering = self.adapter.is_discovering()
            
            # Stop discovery
            self.adapter.stop_discovery()
            
            if not discovering:
                return TEST_FAIL, "Discovery did not start"
            
            return TEST_PASS, "Discovery started and stopped successfully"
        
        except Exception as exc:
            # Try to stop discovery if it was started
            try:
                self.adapter.stop_discovery()
            except:
                pass
            
            return TEST_ERROR, f"Error during discovery test: {exc}"

def run_test_suite(suite_name: str, device_mac: Optional[str] = None, use_mock: bool = False) -> List[TestResult]:
    """Run a specific test suite."""
    if suite_name == "dbus":
        suite = DBusInterfaceTestSuite(device_mac, use_mock)
    elif suite_name == "gatt":
        suite = GATTTestSuite(device_mac, use_mock)
    elif suite_name == "adapter":
        suite = AdapterTestSuite(use_mock)
    else:
        print_and_log(f"[-] Unknown test suite: {suite_name}", LOG__DEBUG)
        return []
    
    results = suite.run_all_tests()
    suite.print_results()
    return results

def run_all_suites(device_mac: Optional[str] = None, use_mock: bool = False) -> Dict[str, List[TestResult]]:
    """Run all test suites."""
    results = {}
    
    # Run adapter tests
    print_and_log("[*] Running adapter tests...", LOG__GENERAL)
    adapter_suite = AdapterTestSuite(use_mock)
    results["adapter"] = adapter_suite.run_all_tests()
    adapter_suite.print_results()
    
    # Run D-Bus interface tests
    print_and_log("[*] Running D-Bus interface tests...", LOG__GENERAL)
    dbus_suite = DBusInterfaceTestSuite(device_mac, use_mock)
    results["dbus"] = dbus_suite.run_all_tests()
    dbus_suite.print_results()
    
    # Run GATT tests
    print_and_log("[*] Running GATT tests...", LOG__GENERAL)
    gatt_suite = GATTTestSuite(device_mac, use_mock)
    results["gatt"] = gatt_suite.run_all_tests()
    gatt_suite.print_results()
    
    return results

def save_results_to_file(results: Dict[str, List[TestResult]], filename: str) -> None:
    """Save test results to a file."""
    # Convert results to serializable format
    serializable_results = {}
    for suite_name, suite_results in results.items():
        serializable_results[suite_name] = [result.to_dict() for result in suite_results]
    
    # Add metadata
    output = {
        "timestamp": time.time(),
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": serializable_results
    }
    
    # Save to file
    with open(filename, "w") as f:
        json.dump(output, f, indent=2)
    
    print_and_log(f"[+] Test results saved to {filename}", LOG__GENERAL)

def parse_args(args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BLEEP Test Mode")
    parser.add_argument("--suite", choices=["all", "dbus", "gatt", "adapter"], default="all",
                      help="Test suite to run (default: all)")
    parser.add_argument("--device", help="MAC address of device to test with")
    parser.add_argument("--mock", action="store_true", help="Use mock devices instead of real hardware")
    parser.add_argument("--verbose", action="store_true", help="Increase output verbosity")
    parser.add_argument("--report", help="Write test results to file")
    return parser.parse_args(args)

def main(args=None) -> int:
    """Main entry point for Test Mode."""
    parsed_args = parse_args(args)
    
    # Set log level based on verbosity
    if parsed_args.verbose:
        os.environ["BLEEP_LOG_LEVEL"] = "debug"
    
    print_and_log("[*] BLEEP Test Mode", LOG__GENERAL)
    
    # Run tests
    if parsed_args.suite == "all":
        results = run_all_suites(parsed_args.device, parsed_args.mock)
    else:
        results = {
            parsed_args.suite: run_test_suite(parsed_args.suite, parsed_args.device, parsed_args.mock)
        }
    
    # Save results to file if requested
    if parsed_args.report:
        save_results_to_file(results, parsed_args.report)
    
    # Determine exit code based on test results
    all_passed = True
    for suite_name, suite_results in results.items():
        for result in suite_results:
            if result.status in [TEST_FAIL, TEST_ERROR]:
                all_passed = False
                break
        if not all_passed:
            break
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
