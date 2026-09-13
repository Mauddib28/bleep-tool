---
description: User-level guide for Bluetooth Media control features in BLEEP
---

# Media Mode in **BLEEP**

BLEEP supports a rich set of *BlueZ Media* interfaces (A2DP / AVRCP)
for querying and controlling playback on Bluetooth Classic **and** BLE devices
that expose the relevant profiles.  This guide explains requirements, CLI
usage and helper APIs introduced during the media-layer refactor (2025-07).

> The implementation is 100 % D-Bus based – no BlueZ test scripts or external
> processes are needed once BLEEP is installed in *editable* mode
> (`pip install -e .`).

---

## 1  Prerequisites

* BlueZ ≥ 5.55 (tested 5.66)
* Controller powered and connected to the target device (pairing not strictly
  required for A2DP sink but recommended)
* For **sink** registration the audio server (PipeWire / PulseAudio) must not
  already occupy the A2DP profile on the adapter – otherwise BlueZ will reject
  the custom endpoint.
* If the host has **no audio server** (e.g. headless systems, containers, minimal
  installs), install `bluez-alsa-utils` (`sudo apt-get install bluez-alsa-utils`)
  to provide the A2DP/HFP profile handlers that `Device1.Connect()` requires.
  Without any audio profile handler, `media-enum` will fail with
  `br-connection-profile-unavailable` on dual-mode audio devices.
  Run `bleep --check-env` to verify audio tool availability.

---

## 2  Command reference

BLEEP exposes media functionality through two top-level CLI commands:

| Command | Purpose |
|---------|---------|
| `bleep media-enum` | Enumerate media devices, players, transports, and the full D-Bus object tree |
| `bleep media-ctrl <MAC> <action> [args]` | AVRCP playback and volume control |

### 2.1  `media-enum` — enumeration

```bash
bleep media-enum 28:EF:01:02:AB:CD                        # player/transport/endpoint summary (JSON)
bleep media-enum 28:EF:01:02:AB:CD --verbose              # + full property bags + D-Bus media-object tree
bleep media-enum 28:EF:01:02:AB:CD --browse               # + top-level folder listing (if browsable)
bleep media-enum 28:EF:01:02:AB:CD --passive              # cached-property assessment, no connection
bleep media-enum 28:EF:01:02:AB:CD --connect-via classic  # force BR/EDR Device1.Connect() path
bleep media-enum 28:EF:01:02:AB:CD --monitor --duration 60 --interval 5   # poll status changes
```

| Flag | Default | Description |
|------|---------|-------------|
| `--connect-via {auto,ble,classic}` | `auto` | Connection strategy. `auto` picks by device type; `ble` forces the GATT-oriented path (works for Classic devices when a host audio stack is present); `classic` forces a BR/EDR `Device1.Connect()` |
| `--verbose` | off | Add full player/transport/endpoint `properties` bags **and** the D-Bus media-object tree (`media_objects`) to the JSON |
| `--browse` | off | Include the top-level folder listing when the player is browsable (`MediaFolder1.ListItems`; no recursion) |
| `--passive` | off | Passive recon only — assess media capability from cached `Device1` properties **without connecting** |
| `--monitor` | off | Poll media status changes for `--duration` seconds |
| `--duration` | 30 | Monitor duration in seconds (with `--monitor`) |
| `--interval` | 2 | Poll interval in seconds (with `--monitor`) |

Output is a JSON document (not a text tree). Non-verbose excerpt:
```json
{
  "device_info": {"address": "28:EF:01:02:AB:CD", "name": "Speaker", "is_connected": true},
  "media_capabilities": {
    "has_media_control": true, "has_media_player": true,
    "has_media_endpoints": true, "has_media_transports": true
  },
  "player": {"name": "...", "status": "playing", "track": {"Title": "..."}},
  "transports": [{"path": ".../fd0", "uuid_name": "A2DP Sink", "codec_name": "SBC", "state": "active"}],
  "endpoints":  [{"path": ".../sep1", "uuid_name": "A2DP Source", "codec_name": "SBC"}]
}
```

With `--verbose`, each `player`/`transport`/`endpoint` gains a full `properties`
bag and a top-level `media_objects` tree (Players → Folders → Items) is added.

### 2.2  `media-ctrl` — AVRCP control

```bash
bleep media-ctrl 28:EF:01:02:AB:CD play
bleep media-ctrl 28:EF:01:02:AB:CD volume --value 90       # 0–127
bleep media-ctrl 28:EF:01:02:AB:CD press  --value 0x44     # raw AVRCP key code (hex ok)
bleep media-ctrl 28:EF:01:02:AB:CD info                    # current track / player status
```

| Action | Description |
|--------|-------------|
| `play` / `pause` / `stop` | Transport control |
| `next` / `previous` | Track navigation |
| `volume` | Set absolute volume; requires `--value 0-127` |
| `info` | Print current track metadata and player status |
| `press` | Send a raw AVRCP key code; requires `--value <code>` (hex accepted with `0x` prefix) |

---

## 3  Developer helpers

### 3.1  `find_media_objects()`
A high-level enumeration helper that returns all Media1-related paths in a
single dictionary – ideal for scripts that need to correlate Players, Folders
and Items without hand-parsing object paths.

```python
from bleep.dbuslayer.media import find_media_objects
objs = find_media_objects()
print(objs["Players"].keys())
```

### 3.2  `MediaRegisterHelper`
Register a minimal SBC endpoint in 3 lines – useful for experimentation or test
sinks.
```python
from bleep.dbuslayer.media_register import MediaRegisterHelper
helper = MediaRegisterHelper()
helper.register_sbc_sink("/test/endpoint")
# … later …
helper.unregister("/test/endpoint")
```

---

## 4  Logging
All Media1 method calls, property changes and error codes are captured in the
per-category log files under `~/.local/share/bleep/logs/` (`general.log`,
`debug.log`, `enumeration.log`, …; see `bleep/core/log.py`).  For backward
compatibility BLEEP also maintains legacy symlinks at
`/tmp/bti__logging__*.txt` that point at those real files.  The `media-enum` /
`media-ctrl` parsers have **no** global `-v`/verbose flag; use `media-enum
--verbose` for richer JSON, and read the log files above for the full call
trace.

---

## 5  Roadmap / limitations

* Browsing: `--browse` lists the top-level folder via `MediaFolder1.ListItems`
  but does not recurse into sub-folders — recursive navigation helpers are a
  future contribution opportunity.
* Broadcast sink/source (BAP ISO) registration is out of scope for the initial
  refactor; see `todo_tracker.md` for future tasks.
* No automatic codec negotiation – helper registers SBC capabilities only.

---

## See also

* **Audio recon** (PulseAudio/PipeWire enumeration, per-profile sources/sinks, play/record, sox analysis): see [audio_recon.md](audio_recon.md). Covers `bleep audio-recon` and future Bonus Objectives (stream redirection, consolidate streams, play into streams, reconfig I/O).
* **Audio *capture*** — `media-enum`/`media-ctrl` are control-only and do **not**
  capture audio. A2DP stream capture and HFP/HSP microphone capture live in the
  audio layer (`bleep audio-record`); see [audio_recon.md](audio_recon.md).

---

*Last updated: 2026-09-13 (v3.0.0 doc-fidelity pass: corrected the logging section to the real `~/.local/share/bleep/logs/*.log` location with legacy `/tmp/bti__logging__*.txt` symlinks and removed the false global `-v` claim; dropped the stale "Since v0.8" version reference).*