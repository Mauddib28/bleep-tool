---
description: User-level guide for Bluetooth Media control features in BLEEP
---

# Media Mode in **BLEEP**

Since v0.8 BLEEP supports a rich set of *BlueZ Media* interfaces (A2DP / AVRCP)
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

### 2.1  Enumeration examples
```bash
bleep media-enum 28:EF:01:02:AB:CD                # player summary, transports, endpoints
bleep media-enum 28:EF:01:02:AB:CD --verbose       # full property bags + D-Bus object tree
bleep media-enum 28:EF:01:02:AB:CD --browse        # include top-level folder listing (if browsable)
bleep media-enum 28:EF:01:02:AB:CD --monitor       # poll media status changes for --duration seconds
```

Sample `--verbose` output (excerpt):
```
[=] Full media object tree:
  Media1 service: /org/bluez/hci0
  Player: /org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0 (Device=/org/bluez/hci0/dev_28_EF_01_02_AB_CD)
    Folder: /org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0/NowPlaying (Player=/org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0)
    Item: /org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0/item42 (Player=/org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0)
```

### 2.2  Control examples
```bash
bleep media-ctrl 28:EF:01:02:AB:CD play
bleep media-ctrl 28:EF:01:02:AB:CD volume --value 90
```

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
The existing `__logging__general.txt` and `__logging__debug.txt` files capture
all Media1 method calls, property changes and error codes.  Enable `-v` on the
CLI to mirror *general* messages to stdout.

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

---

*Last updated: 2026-04-02*