# BLEEP Documentation

Welcome to the official documentation hub for **BLEEP – Bluetooth Landscape Exploration & Enumeration Platform**.  All files in this directory live **inside the `bleep` package** so the documentation is version-controlled and ships alongside the code.

## Table of contents

### CLI & Modes
- [CLI quick-start](cli_usage.md)
- [Debug mode](debug_mode.md) — interactive shell (`bleep debug`, also available as `python -m bleep.modes.debug`)
- [Scan modes](ble_scan_modes.md) — passive, naggy, pokey, brute
- [GATT enumeration commands](gatt_enumeration.md) — `gatt-enum` and `enum-scan`
- [Bluetooth Classic mode](bl_classic_mode.md) — BR/EDR scanning, profiles (PBAP, OPP, MAP, FTP, PAN, SPP, etc.)
  - [MAP bMessage format reference](map_bmessage_format.md) — envelope spec, LENGTH rules, nested envelopes, bulk ops, test corpus
- [Media mode](media_mode.md) — A2DP/AVRCP (`media-enum`, `media-ctrl`)
- [Audio recon](audio_recon.md) — PulseAudio/PipeWire enumeration, play/record
- [BLE CTF mode](ble_ctf_mode.md)
- [User mode](user_mode.md)
- [Explore mode](explore_mode.md) — automated GATT dump to JSON
- [Analysis mode](analysis_mode.md) — post-process JSON dumps
- [Agent mode](agent_mode.md) — pairing agent
- [Pairing agent](pairing_agent.md) — detailed agent architecture
- [Signal capture](signal_capture.md) — characteristic notification monitoring
- [Adapter configuration](adapter_config.md)

### Data & Security
- [Observation database](observation_db.md)
  - [Real-World Usage Scenarios](observation_db_usage_scenarios.md)
  - [Database in debug mode](debug_mode_db.md)
- [Assets-of-Interest (AoI) Mode](aoi_mode.md)
  - [AoI Security Analysis Algorithms](aoi_security_algorithms.md)
  - [AoI Customization Guide](aoi_customization_guide.md)
  - [AoI Implementation](aoi_implementation.md)

### Architecture & Reference
- `bleep/protocols/` — **design-only** package containing L2CAP and OBEX protocol design documents; no runtime code yet
- [BlueZ D-Bus interface property reference](bluez_interface_properties.md)
- [D-Bus reliability documentation](dbus_documentation_index.md)
- [D-Bus best practices](dbus_best_practices.md)
- [D-Bus debugging methods](dbus_debugging_methods.md)
- [Mainloop architecture](mainloop_architecture.md)
- [Unified D-Bus Event Aggregator](unified_dbus_event_aggregator.md)
- [Device type classification](device_type_classification.md)
- [UUID translation](uuid_translation.md)
- [Modalias handling](modalias_handling.md)
- [Network capability](network_capability_summary.md)
- [PAN connection analysis](pan_connection_analysis.md) — BlueZ source audit, D-Bus lifetime findings, BNEP transport failure analysis, requirements for working NAP
- [Agent documentation index](agent_documentation_index.md)

### Project Tracking
- [Change log](changelog.md)
- [Central TODO tracker](todo_tracker.md)

---

Each guide is intentionally concise and task-oriented – it shows **exact command invocations** and **expected outputs** rather than generic prose.  Read the one that matches your immediate need and get hands-on quickly. 