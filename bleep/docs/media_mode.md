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

---

## 2  Command reference (`bleep modes media`)

| Sub-command | Purpose |
|-------------|---------|
| `list` | Show detected Media devices, players and transports |
| `list --objects` | Full D-Bus object tree (Media1 services, folders, items) |
| `control <MAC> <action>` | AVRCP control wrappers (play/pause/next/… volume) |
| `monitor <MAC>` | Poll playback status & track changes |

Run `python -m bleep.cli media --help` for all global flags.

### 2.1  List examples
```bash
python -m bleep.cli media list
python -m bleep.cli media list --objects  # dumps folders & items
```

Sample *--objects* output
```
[=] Full media object tree:
  Media1 service: /org/bluez/hci0
  Player: /org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0 (Device=/org/bluez/hci0/dev_28_EF_01_02_AB_CD)
    Folder: /org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0/NowPlaying (Player=/org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0)
    Item: /org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0/item42 (Player=/org/bluez/hci0/dev_28_EF_01_02_AB_CD/player0)
```

### 2.2  Control examples
```bash
python -m bleep.cli media control 28:EF:01:02:AB:CD play
python -m bleep.cli media control 28:EF:01:02:AB:CD volume --value 90
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

* Browsing API currently exposes `MediaFolder1.ListItems` but not recursive
  navigation helpers – contributions welcome.
* Broadcast sink/source (BAP ISO) registration is out of scope for the initial
  refactor; see `todo_tracker.md` for future tasks.
* No automatic codec negotiation – helper registers SBC capabilities only.

---

*Last updated: 2025-07-21* 