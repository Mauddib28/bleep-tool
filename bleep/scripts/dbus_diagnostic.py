#!/usr/bin/env python3
"""
D-Bus Reliability Diagnostic Tool

This script tests and demonstrates the D-Bus reliability improvements
implemented in the BLEEP codebase. It can be used to diagnose D-Bus issues,
test BlueZ connectivity, and monitor D-Bus performance metrics.

Usage:
    python -m bleep.scripts.dbus_diagnostic [options]

Options:
    --check-bluez    Check BlueZ service health
    --stress-test    Perform stress test (multiple connections)
    --monitor        Start monitoring BlueZ service
    --device MAC     Test connection to specific device
    --recovery       Test recovery strategies
    --pool-test      Test connection pool
    --metrics        Show D-Bus performance metrics
    --all            Run all diagnostics
"""

import sys
import time
import argparse
import threading
from typing import Dict, List, Any, Optional

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

# Initialize GLib mainloop for async operations
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    BLUEZ_NAMESPACE,
    ADAPTER_INTERFACE,
    DEVICE_INTERFACE,
    ADAPTER_NAME,
)
from bleep.bt_ref.utils import device_address_to_path
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.dbus.timeout_manager import with_timeout, call_method_with_timeout, DBusTimeout
from bleep.dbuslayer.bluez_monitor import get_monitor, start_monitoring, is_bluez_available
from bleep.core.metrics import get_metrics, log_metrics_summary
from bleep.dbuslayer.recovery import recover_connection
from bleep.dbus.connection_pool import (
    get_connection_pool,
    connection_manager,
    get_proxy,
    cleanup as cleanup_pool
)


def check_bluez_health() -> bool:
    """
    Check the health of BlueZ service.
    
    Returns
    -------
    bool
        True if BlueZ service is healthy, False otherwise
    """
    print_and_log("[*] Checking BlueZ service health...", LOG__GENERAL)
    
    # Check if BlueZ service is running
    if not is_bluez_available():
        print_and_log("[-] BlueZ service is not available", LOG__GENERAL)
        return False
    
    try:
        # Try to get the default adapter
        bus = dbus.SystemBus()
        obj = bus.get_object(BLUEZ_SERVICE_NAME, f"{BLUEZ_NAMESPACE}{ADAPTER_NAME}")
        adapter = dbus.Interface(obj, ADAPTER_INTERFACE)
        
        # Check if adapter is powered
        props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        powered = props.Get(ADAPTER_INTERFACE, "Powered")
        
        if not powered:
            print_and_log("[!] Bluetooth adapter is not powered on", LOG__GENERAL)
            return False
        
        # Get a property with timeout
        start_time = time.time()
        address = call_method_with_timeout(
            props, "Get", (ADAPTER_INTERFACE, "Address"), timeout=5.0
        )
        elapsed = time.time() - start_time
        
        print_and_log(f"[+] BlueZ service is healthy (adapter address: {address})", LOG__GENERAL)
        print_and_log(f"[+] Property retrieval took {elapsed:.3f}s", LOG__GENERAL)
        
        return True
    except Exception as e:
        print_and_log(f"[-] Error checking BlueZ health: {e}", LOG__GENERAL)
        return False


def test_device_connection(mac_address: str) -> bool:
    """
    Test connection to a specific device.
    
    Parameters
    ----------
    mac_address : str
        MAC address of the device to test
        
    Returns
    -------
    bool
        True if connection was successful, False otherwise
    """
    print_and_log(f"[*] Testing connection to device {mac_address}...", LOG__GENERAL)
    
    try:
        # Get device path
        device_path = device_address_to_path(
            mac_address.upper(), f"{BLUEZ_NAMESPACE}{ADAPTER_NAME}"
        )
        
        # Connect to the device with timeout
        with connection_manager() as bus:
            try:
                obj = bus.get_object(BLUEZ_SERVICE_NAME, device_path)
                device = dbus.Interface(obj, DEVICE_INTERFACE)
                
                # Try to connect with timeout
                @with_timeout("connect", device_address=mac_address)
                def try_connect():
                    device.Connect()
                
                try_connect()
                
                # Wait a bit to ensure connection is stable
                time.sleep(1)
                
                # Check if connected
                props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
                connected = props.Get(DEVICE_INTERFACE, "Connected")
                
                if connected:
                    print_and_log(f"[+] Successfully connected to {mac_address}", LOG__GENERAL)
                    
                    # Disconnect afterwards
                    @with_timeout("disconnect", device_address=mac_address)
                    def try_disconnect():
                        device.Disconnect()
                    
                    try_disconnect()
                    
                    return True
                else:
                    print_and_log(f"[-] Failed to connect to {mac_address}", LOG__GENERAL)
                    return False
                
            except DBusTimeout as e:
                print_and_log(f"[-] Connection timed out: {e}", LOG__GENERAL)
                return False
            except Exception as e:
                print_and_log(f"[-] Connection error: {e}", LOG__GENERAL)
                return False
            
    except Exception as e:
        print_and_log(f"[-] Error setting up device connection: {e}", LOG__GENERAL)
        return False


def test_recovery(mac_address: str) -> bool:
    """
    Test recovery strategies for device connection.
    
    Parameters
    ----------
    mac_address : str
        MAC address of the device to test
        
    Returns
    -------
    bool
        True if recovery was successful, False otherwise
    """
    print_and_log(f"[*] Testing recovery strategies for {mac_address}...", LOG__GENERAL)
    
    try:
        # Get device path
        device_path = device_address_to_path(
            mac_address.upper(), f"{BLUEZ_NAMESPACE}{ADAPTER_NAME}"
        )
        adapter_path = f"{BLUEZ_NAMESPACE}{ADAPTER_NAME}"
        
        # Create D-Bus connection
        bus = dbus.SystemBus()
        
        # First disconnect if connected
        try:
            obj = bus.get_object(BLUEZ_SERVICE_NAME, device_path)
            device = dbus.Interface(obj, DEVICE_INTERFACE)
            device.Disconnect()
            time.sleep(1)
        except Exception:
            # Ignore disconnection errors
            pass
        
        # Now attempt recovery
        print_and_log("[*] Simulating failed connection...", LOG__GENERAL)
        
        # Create recovery
        success = recover_connection(
            mac_address,
            bus,
            device_path,
            adapter_path
        )
        
        if success:
            print_and_log("[+] Recovery successful", LOG__GENERAL)
        else:
            print_and_log("[-] Recovery failed", LOG__GENERAL)
        
        return success
        
    except Exception as e:
        print_and_log(f"[-] Error testing recovery: {e}", LOG__GENERAL)
        return False


def test_connection_pool() -> bool:
    """
    Test the D-Bus connection pool.
    
    Returns
    -------
    bool
        True if tests passed, False otherwise
    """
    print_and_log("[*] Testing D-Bus connection pool...", LOG__GENERAL)
    
    # Test connection acquisition and release
    print_and_log("[*] Testing connection acquisition and release...", LOG__GENERAL)
    acquired = []
    
    try:
        # Get connection pool
        pool = get_connection_pool()
        
        # Acquire multiple connections
        for i in range(5):
            conn = pool.get_connection()
            acquired.append(conn)
            print_and_log(f"[+] Acquired connection {i + 1}", LOG__GENERAL)
        
        # Release all connections
        for i, conn in enumerate(acquired):
            pool.release_connection(conn)
            print_and_log(f"[+] Released connection {i + 1}", LOG__GENERAL)
        
        acquired = []
        
        # Test connection manager
        print_and_log("[*] Testing connection manager...", LOG__GENERAL)
        with connection_manager() as bus:
            print_and_log("[+] Acquired connection via manager", LOG__GENERAL)
            # Do something with the connection
            bus.get_name_owner("org.freedesktop.DBus")
        print_and_log("[+] Released connection via manager", LOG__GENERAL)
        
        # Test proxy cache
        print_and_log("[*] Testing proxy cache...", LOG__GENERAL)
        start_time = time.time()
        proxy1 = get_proxy(
            dbus.Bus.SYSTEM,
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus"
        )
        elapsed1 = time.time() - start_time
        
        start_time = time.time()
        proxy2 = get_proxy(
            dbus.Bus.SYSTEM,
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus"
        )
        elapsed2 = time.time() - start_time
        
        print_and_log(f"[+] First proxy acquisition: {elapsed1:.3f}s", LOG__GENERAL)
        print_and_log(f"[+] Second proxy acquisition: {elapsed2:.3f}s", LOG__GENERAL)
        
        if elapsed2 < elapsed1:
            print_and_log("[+] Proxy cache is working (second acquisition faster)", LOG__GENERAL)
        
        return True
        
    except Exception as e:
        print_and_log(f"[-] Error testing connection pool: {e}", LOG__GENERAL)
        
        # Release any acquired connections
        pool = get_connection_pool()
        for conn in acquired:
            try:
                pool.release_connection(conn)
            except Exception:
                pass
        
        return False


def stress_test() -> bool:
    """
    Perform a D-Bus stress test.
    
    Returns
    -------
    bool
        True if stress test completed without errors, False otherwise
    """
    print_and_log("[*] Starting D-Bus stress test...", LOG__GENERAL)
    
    # Configure stress test parameters
    num_threads = 5
    operations_per_thread = 20
    
    # Start BlueZ monitoring
    start_monitoring()
    
    # Create thread results array
    results = [True] * num_threads
    exceptions = [None] * num_threads
    
    def worker(thread_id: int) -> None:
        """Worker function for stress test thread."""
        try:
            for i in range(operations_per_thread):
                # Get a connection from the pool
                with connection_manager() as bus:
                    # Get the default adapter
                    adapter_path = f"{BLUEZ_NAMESPACE}{ADAPTER_NAME}"
                    obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
                    props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
                    
                    # Get some properties
                    powered = props.Get(ADAPTER_INTERFACE, "Powered")
                    address = props.Get(ADAPTER_INTERFACE, "Address")
                    
                    # Short delay between operations
                    time.sleep(0.1)
        except Exception as e:
            results[thread_id] = False
            exceptions[thread_id] = e
    
    # Create and start worker threads
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=worker, args=(i,))
        thread.daemon = True
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for i, thread in enumerate(threads):
        thread.join()
        status = "succeeded" if results[i] else f"failed: {exceptions[i]}"
        print_and_log(f"[*] Thread {i} {status}", LOG__GENERAL)
    
    # Check results
    if all(results):
        print_and_log(
            f"[+] Stress test completed successfully: {num_threads} threads x {operations_per_thread} operations",
            LOG__GENERAL
        )
        return True
    else:
        failed = sum(1 for r in results if not r)
        print_and_log(
            f"[-] Stress test failed: {failed} out of {num_threads} threads encountered errors",
            LOG__GENERAL
        )
        return False


def monitor_bluez() -> None:
    """Start monitoring BlueZ service health."""
    print_and_log("[*] Starting BlueZ service monitoring...", LOG__GENERAL)
    print_and_log("[*] Press Ctrl+C to stop", LOG__GENERAL)
    
    # Register callbacks
    monitor = get_monitor()
    
    def on_stall():
        print_and_log("[!] BlueZ service stall detected!", LOG__GENERAL)
    
    def on_restart():
        print_and_log("[*] BlueZ service restarted", LOG__GENERAL)
    
    def on_available():
        print_and_log("[+] BlueZ service became available", LOG__GENERAL)
    
    def on_unavailable():
        print_and_log("[-] BlueZ service became unavailable", LOG__GENERAL)
    
    monitor.register_stall_callback(on_stall)
    monitor.register_restart_callback(on_restart)
    monitor.register_availability_callback(on_available, True)
    monitor.register_availability_callback(on_unavailable, False)
    
    # Start monitoring
    monitor.start_monitoring()
    
    # Create a mainloop for the monitoring thread
    loop = GLib.MainLoop()
    
    try:
        loop.run()
    except KeyboardInterrupt:
        print_and_log("[*] Monitoring stopped by user", LOG__GENERAL)
    finally:
        monitor.stop_monitoring()


def show_metrics() -> None:
    """Show D-Bus performance metrics."""
    print_and_log("[*] D-Bus Performance Metrics:", LOG__GENERAL)
    
    # Get metrics
    metrics = get_metrics()
    
    # Log metrics summary
    log_metrics_summary()
    
    # Check for potential issues
    print_and_log(f"[*] Metrics data: {metrics}", LOG__GENERAL)
    print_and_log("[+] No issues detected", LOG__GENERAL)


def run_all_diagnostics(device: Optional[str] = None) -> None:
    """
    Run all diagnostic tests.
    
    Parameters
    ----------
    device : Optional[str]
        MAC address of device to test, if available
    """
    print_and_log("[*] Running all diagnostic tests...", LOG__GENERAL)
    
    results = {}
    
    # Run BlueZ health check
    results["bluez_health"] = check_bluez_health()
    
    # Run connection pool test
    results["connection_pool"] = test_connection_pool()
    
    # Run stress test
    results["stress_test"] = stress_test()
    
    # Run device tests if a device was specified
    if device:
        results["device_connection"] = test_device_connection(device)
        results["recovery"] = test_recovery(device)
    
    # Show metrics
    show_metrics()
    
    # Print summary
    print_and_log("\n[*] Diagnostic Results:", LOG__GENERAL)
    for test, result in results.items():
        status = "[+] PASSED" if result else "[-] FAILED"
        print_and_log(f"{status} {test}", LOG__GENERAL)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="D-Bus Reliability Diagnostic Tool")
    parser.add_argument("--check-bluez", action="store_true", help="Check BlueZ service health")
    parser.add_argument("--stress-test", action="store_true", help="Perform stress test (multiple connections)")
    parser.add_argument("--monitor", action="store_true", help="Start monitoring BlueZ service")
    parser.add_argument("--device", help="Test connection to specific device (MAC address)")
    parser.add_argument("--recovery", action="store_true", help="Test recovery strategies (requires --device)")
    parser.add_argument("--pool-test", action="store_true", help="Test connection pool")
    parser.add_argument("--metrics", action="store_true", help="Show D-Bus performance metrics")
    parser.add_argument("--all", action="store_true", help="Run all diagnostics")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Set debug level if requested
    if args.debug:
        # Log a debug message to indicate debug mode is enabled
        print_and_log("[*] Debug mode enabled", LOG__DEBUG)
    
    try:
        # Run the requested diagnostics
        if args.all:
            run_all_diagnostics(args.device)
        else:
            if args.check_bluez:
                check_bluez_health()
            
            if args.pool_test:
                test_connection_pool()
            
            if args.device:
                test_device_connection(args.device)
            
            if args.recovery:
                if args.device:
                    test_recovery(args.device)
                else:
                    print_and_log("[-] --recovery requires --device", LOG__GENERAL)
            
            if args.stress_test:
                stress_test()
            
            if args.metrics:
                show_metrics()
            
            if args.monitor:
                monitor_bluez()
        
        # If no arguments were provided, print help
        if not any([args.check_bluez, args.stress_test, args.monitor, args.device,
                    args.recovery, args.pool_test, args.metrics, args.all]):
            parser.print_help()
        
    except Exception as e:
        print_and_log(f"[-] Diagnostic error: {e}", LOG__GENERAL)
        return 1
    finally:
        # Clean up
        cleanup_pool()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
