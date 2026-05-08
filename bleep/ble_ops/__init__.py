"""High-level BLE operation modules.

Organised into subpackages:
- ``le/``      – Bluetooth Low Energy scan, connect, enum, CTF
- ``classic/`` – Bluetooth Classic (BR/EDR) connect, SDP, OBEX, PAN, …
- ``common/``  – Shared utilities (conversion, UUID helpers, modalias, structural)
- ``audio/``   – Audio target discovery, tools, codec, recon, system

All imports should use the canonical subpackage paths, e.g.
``from bleep.ble_ops.le.connect import …``.

Convenience re-exports (e.g. ``from bleep.ble_ops import passive_scan``) are
resolved lazily via ``__getattr__`` so that importing lightweight submodules
like ``bleep.ble_ops.common.uuid_utils`` does **not** pull in the full LE /
Classic stacks and their transitive ``dbuslayer`` dependencies.  This breaks
the circular import: ``device_le → ble_ops.common → ble_ops.__init__ →
le.connect → device_le``.
"""

__all__ = [
    # LE
    "passive_scan",
    "connect_and_enumerate__bluetooth__low_energy",
    "passive_scan_and_connect",
    "naggy_scan_and_connect",
    "pokey_scan_and_connect",
    "bruteforce_scan_and_connect",
    "scan_and_connect",
    "PASSIVE_MODE",
    "NAGGY_MODE",
    "POKEY_MODE",
    "BRUTEFORCE_MODE",
    # Classic
    "discover_services_sdp",
    "discover_services_sdp_connectionless",
    "connect_and_enumerate__bluetooth__classic",
    "query_hci_version",
    "map_lmp_version_to_spec",
    "map_profile_version_to_spec",
]

_LAZY_IMPORTS = {
    # LE – scan
    "passive_scan":                                (".le.scan", "passive_scan"),
    # LE – connect
    "connect_and_enumerate__bluetooth__low_energy": (".le.connect", "connect_and_enumerate__bluetooth__low_energy"),
    # LE – scan modes
    "passive_scan_and_connect":                    (".le.scan_modes", "passive_scan_and_connect"),
    "naggy_scan_and_connect":                      (".le.scan_modes", "naggy_scan_and_connect"),
    "pokey_scan_and_connect":                      (".le.scan_modes", "pokey_scan_and_connect"),
    "bruteforce_scan_and_connect":                 (".le.scan_modes", "bruteforce_scan_and_connect"),
    "scan_and_connect":                            (".le.scan_modes", "scan_and_connect"),
    "PASSIVE_MODE":                                (".le.scan_modes", "PASSIVE_MODE"),
    "NAGGY_MODE":                                  (".le.scan_modes", "NAGGY_MODE"),
    "POKEY_MODE":                                  (".le.scan_modes", "POKEY_MODE"),
    "BRUTEFORCE_MODE":                             (".le.scan_modes", "BRUTEFORCE_MODE"),
    # Classic – SDP
    "discover_services_sdp":                       (".classic.sdp", "discover_services_sdp"),
    "discover_services_sdp_connectionless":        (".classic.sdp", "discover_services_sdp_connectionless"),
    # Classic – connect
    "connect_and_enumerate__bluetooth__classic":   (".classic.connect", "connect_and_enumerate__bluetooth__classic"),
    # Classic – version
    "query_hci_version":                           (".classic.version", "query_hci_version"),
    "map_lmp_version_to_spec":                     (".classic.version", "map_lmp_version_to_spec"),
    "map_profile_version_to_spec":                 (".classic.version", "map_profile_version_to_spec"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib
        module_path, attr = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_path, __name__)
        value = getattr(module, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
