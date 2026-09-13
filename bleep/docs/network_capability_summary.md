# Network Capability Integration - Summary

> **⚠️ Phase-numbering note (2026-07-12):** This document uses its *own* original
> phase scheme (Phase 1 = D-Bus wrapper; Phases 2–5 = enumeration / device-class
> helpers). It is **distinct** from the authoritative
> [`todo_tracker.md`](todo_tracker.md) → *"Bluetooth Networking (BlueZ PAN / BNEP)
> — Full D-Bus Incorporation Plan"*, whose numbering is Phase 1 = prerequisite
> preflight (**done**), Phase 2 = connect-path correctness (**done**), Phase 3 =
> enumeration + device-class integration. This document's "Phases 2–5" map to
> that tracker's **Phase 3**. For current status, defer to the tracker.

## Overview

This document summarizes the plan to integrate Bluetooth Network (PAN) capability detection and enumeration into the BLEEP codebase. **Network capability is a service capability (like media), not a device type.** A device can be Classic, LE, or Dual-mode AND have network capabilities.

## Key Corrections

### Network is NOT a Device Type

- Network capability is **orthogonal** to device type classification (Classic/LE/Dual)
- Similar to how media playback is a capability, not a device type
- A device can be Classic/LE/Dual AND have network capabilities
- Focus is on **enumeration of Network interface properties, methods, and attributes**

### Network Profile Limitations

- **Classic Bluetooth profile**: Network (PAN) is only available on Classic devices
- **Dual-mode devices**: Can have network capabilities when using Classic bearer
- **Pure LE devices**: Cannot have Network interface (Classic-only profile)

## Implementation Strategy

### Following Media Capability Pattern

The implementation follows the existing media capability detection pattern:

1. **Interface Detection**: Check for `org.bluez.Network1` interface presence
2. **Wrapper Classes**: `NetworkClient` (per-device `Network1`) and `NetworkServer` (per-adapter `NetworkServer1`) in `bleep/dbuslayer/network.py`
3. **Enumeration**: Provide enumeration functions for network-capable devices
4. **Property Access**: Enumerate all Network interface properties and methods

### Network Interface Details (from BlueZ docs)

**Interface**: `org.bluez.Network1`  
**Object Path**: `/{hci0,hci1,...}/dev_XX_XX_XX_XX_XX_XX`

**Properties**:
- `Connected` (boolean, readonly): Connection status
- `Interface` (string, readonly, optional): Network interface name (e.g., "bnep0")
- `UUID` (string, readonly, optional): Connection role UUID

**Methods**:
- `Connect(string uuid)` → string: Connect to network, returns interface name
- `Disconnect()` → void: Disconnect from network

**Network Roles**:
- PANU: `00001115-0000-1000-8000-00805f9b34fb`
- NAP: `00001116-0000-1000-8000-00805f9b34fb`
- GN: `00001117-0000-1000-8000-00805f9b34fb`

## Implementation Status

> **✅ Update (2026-07-12): tracker Phase 3 is COMPLETE.** The enumeration and
> device-class integration described below as "Future Enhancement" has shipped —
> though in `bleep/ble_ops/classic/pan.py` (not a new `classic_network.py`), with
> list-returning helpers (`find_network_servers()` / `find_network_devices()` /
> `network_roles_from_uuids()`), device-class helpers on both `device_classic.py`
> and `device_le.py` (`is_network_device()`, `has_network_uuids()`,
> `get_network_roles()`, `get_network_status()`, `has_network_interface()`), an
> additive `network` key in `get_device_info()`, and the `network-enum` CLI
> (`--adapter/--json/--all-devices`). `check_device_type()` was intentionally
> **not** modified. See `bl_classic_mode.md` §2.11.1 and `changelog.md`.
>
> **Note (superseded 2026-07-12):** An earlier note (2026-04-01) claimed the
> Phase 2–5 device-class-helper / `network-enum` approach had *not* shipped and
> was an "optional future enhancement." That is **no longer accurate** — those
> items shipped as tracker Phase 3 (see the ✅ update above). The `classic-pan`
> CLI and the `network-enum` / device-class helpers now coexist.

### Phase 1: Network Interface Wrapper ✅ Complete
- Created `bleep/dbuslayer/network.py`
- Implemented `NetworkClient` class (wraps `org.bluez.Network1` per-device) with property accessors and `Connect()`/`Disconnect()` methods
- Implemented `NetworkServer` class (wraps `org.bluez.NetworkServer1` per-adapter) with `Register()`/`Unregister()` methods

### Phase 1b: Operations Layer + CLI ✅ Complete (v2.7.9)
- Created `bleep/ble_ops/classic/pan.py` — operations layer with `connect()`, `disconnect()`, `status()`, `register_server()`, `unregister_server()`
- Created `classic-pan` CLI command with `connect|disconnect|status|server-reg|server-unreg` actions
- Created `cpan` debug-mode command
- PAN constants (`NETWORK_INTERFACE`, `NETWORK_SERVER_INTERFACE`, PAN UUIDs) added to `bleep/bt_ref/constants.py`
- PAN service detection via `detect_pan_service()` for SDP integration
- Observation database integration (`upsert_pan_access` in `bleep/core/observations/_services.py`)

### Phase 2: Device Capability Detection ✅ Complete (tracker Ph 3, 2026-07-12)
- `is_network_device()`, `has_network_uuids()`, `get_network_roles()`,
  `get_network_status()`, `has_network_interface()` on both device classes.
- `check_device_type()` was **not** modified (kept stable for parity); network
  capability is surfaced via the additive `network` key in `get_device_info()`.

### Phase 3: Network Enumeration ✅ Complete (tracker Ph 3, 2026-07-12)
- Implemented in `bleep/ble_ops/classic/pan.py` (not `classic_network.py`):
  `find_network_servers()`, `find_network_devices()`, `network_roles_from_uuids()`.
- Property + UUID enumeration from a single `GetManagedObjects` snapshot.

### Phase 4: Dedicated Enumeration CLI ✅ Complete (tracker Ph 3, 2026-07-12)
- `network-enum` command with `--adapter`, `--json`, `--all-devices`.
- Human-readable and JSON output; standalone
  `scripts/check_network_capabilities.py` refactored to reuse the same ops.

### Phase 5: Device Info Integration ✅ Complete (tracker Ph 3, 2026-07-12)
- `get_device_info()` gained one additive `network` key (`{roles, has_interface, status}` or `None`).
- `check_device_type()` was intentionally **not** modified.

## Files

### Implemented
- **`bleep/dbuslayer/network.py`** — Network D-Bus wrapper (`NetworkClient` + `NetworkServer`)
- **`bleep/ble_ops/classic/pan.py`** — Operations layer
- **`bleep/cli/parsers/classic.py`** — `classic-pan` subcommand
- **`bleep/modes/debug_classic_profiles.py`** — `cpan` debug command
- **`bleep/bt_ref/constants.py`** — PAN-related constants

### Documentation
- **`bleep/docs/archive/network_capability_plan.md`** — Original detailed design sketch (Phases 2–5 shipped as tracker Phase 3; that doc's code samples predate the shipped API)
- **`bleep/docs/bl_classic_mode.md`** — User-facing PAN docs (Section 2.11)
- **`bleep/scripts/check_network_capabilities.py`** — Local BlueZ capability checker

## Key Design Principles

1. **Capability, not Type**: Network is a capability like media, not a device type
2. **Interface-Based Detection**: Use `org.bluez.Network1` interface presence as definitive indicator
3. **Property Enumeration**: Enumerate all Network interface properties (Connected, Interface, UUID)
4. **Method Access**: Provide access to Network methods (Connect, Disconnect)
5. **Role Detection**: Extract network roles from device UUIDs property
6. **Classic Limitation**: Acknowledge that Network is Classic-only profile

## Usage Examples

### Check Local Capabilities
```bash
python3 bleep/scripts/check_network_capabilities.py
python3 bleep/scripts/check_network_capabilities.py --verbose
```

### Enumerate Network Devices
```bash
bleep network-enum
bleep network-enum --adapter hci0
bleep network-enum --all-devices   # Include devices without an active Network1 interface
bleep network-enum --json
```

> There is **no** `network-enum --verbose` flag; use `--json` for full detail.

### Programmatic Usage (shipped API)
```python
from bleep.ble_ops.classic.connect import connect_and_enumerate__bluetooth__classic
from bleep.ble_ops.classic.pan import (
    find_network_devices,
    find_network_servers,
    network_roles_from_uuids,
)

# Per-device capability helpers (present on both device_classic and device_le):
device, _service_map = connect_and_enumerate__bluetooth__classic("AA:BB:CC:DD:EE:FF")
if device.is_network_device():
    print(f"Roles:      {device.get_network_roles()}")     # ['NAP'], ['PANU'], ...
    print(f"Has UUIDs:  {device.has_network_uuids()}")
    print(f"Has iface:  {device.has_network_interface()}")
    print(f"Status:     {device.get_network_status()}")    # {connected, interface, uuid} or None

# Adapter-wide enumeration from a single GetManagedObjects snapshot.
# Both return lists of dicts and never raise:
for dev in find_network_devices():
    # keys: path, address, name, has_network_interface, network_uuids,
    #       has_network_capability, and network_status when the iface is present
    print(f"{dev['address']}: roles={dev['network_uuids']} "
          f"capable={dev['has_network_capability']}")

for srv in find_network_servers():
    # keys: path, name, address, powered, has_networkserver, network_uuids
    print(f"server {srv['address']}: uuids={srv['network_uuids']}")

# UUID list → PAN role labels
print(network_roles_from_uuids(["00001116-0000-1000-8000-00805f9b34fb"]))  # ['NAP']
```

## Testing Strategy

1. **Unit Tests**: Mock Network interface and test wrapper class
2. **Integration Tests**: Test with real network-capable devices
3. **Property Tests**: Verify all properties are accessible
4. **Method Tests**: Test Connect/Disconnect methods
5. **Enumeration Tests**: Test enumeration across device types
6. **Error Handling**: Test with non-network devices

## Current Status

PAN client/server D-Bus wrappers and CLI/debug commands are **implemented** via
`classic-pan` CLI and `cpan` debug command (v2.7.9+).  End-to-end operation
(BNEP session establishment, `bnep0` interface creation) depends on the remote
device accepting the PAN role — testing has shown that the BNEP transport layer
may fail immediately even when BlueZ returns a nominal success from
`Network1.Connect()`.  A post-connect verification step now detects this.
Server registration (`classic-pan server-reg`) requires the CLI process to stay alive
(uses `signal.pause()`); Ctrl-C cleanly unregisters.

The Phases 2-5 enumeration enhancements (this doc's numbering = tracker **Phase 3**)
are now **implemented** (2026-07-12): device-class capability helpers, module-level
`find_network_servers()`/`find_network_devices()`, an additive `network` key in
`get_device_info()`, and the `network-enum` CLI. See `bl_classic_mode.md` §2.11.1.

## References

- **[PAN connection analysis](pan_connection_analysis.md)** — BlueZ source code audit of D-Bus client lifetime, BNEP transport failure root-cause analysis, Agent Pairing comparison, and requirements checklist for a working NAP connection
- **BlueZ Documentation**: `workDir/BlueZDocs/org.bluez.Network.rst`, `workDir/BlueZDocs/org.bluez.NetworkServer.rst`
- **BlueZ Source**: `workDir/bluez/profiles/network/connection.c` (client), `workDir/bluez/profiles/network/server.c` (server)
- **BlueZ Scripts**: `workDir/BlueZScripts/test-network`, `test-nap`
- **Existing Patterns**: `bleep/dbuslayer/media.py` (media capability pattern)
- **Device Helpers**: `bleep/dbuslayer/device_le.py` (media methods as reference)

---

*Last updated: 2026-09-13 (v3.0.0 doc-fidelity pass: corrected `classic-pan` action list to `server-reg`/`server-unreg`, and fixed the `network_capability_plan.md` path to `archive/`).*
