"""High-level BLE operation modules.

All helpers are implemented natively against the refactored `bleep.dbuslayer`
stack.  No legacy monolith proxy remains."""

from bleep.ble_ops.scan import passive_scan
from bleep.ble_ops.connect import connect_and_enumerate__bluetooth__low_energy
from bleep.ble_ops.scan_modes import (
    passive_scan_and_connect,
    naggy_scan_and_connect, 
    pokey_scan_and_connect,
    bruteforce_scan_and_connect,
    scan_and_connect,
    PASSIVE_MODE,
    NAGGY_MODE,
    POKEY_MODE,
    BRUTEFORCE_MODE,
)
from bleep.ble_ops.classic_sdp import discover_services_sdp
from bleep.ble_ops.classic_connect import connect_and_enumerate__bluetooth__classic

__all__ = [
    # From scan.py
    "passive_scan",
    
    # From connect.py
    "connect_and_enumerate__bluetooth__low_energy",
    
    # From scan_modes.py
    "passive_scan_and_connect",
    "naggy_scan_and_connect",
    "pokey_scan_and_connect", 
    "bruteforce_scan_and_connect",
    "scan_and_connect",
    "PASSIVE_MODE",
    "NAGGY_MODE",
    "POKEY_MODE",
    "BRUTEFORCE_MODE",
    # Classic helpers
    "discover_services_sdp",
    "connect_and_enumerate__bluetooth__classic",
]
