# Audio Recon in BLEEP

Audio recon enumerates Bluetooth audio cards, profiles, and per-profile sources/sinks; optionally plays a test file to sinks and records from sources/sinks; and analyses recordings with sox to determine if they contain audio.

## Prerequisites

- **Backend**: PulseAudio, PipeWire (PA-compat or native), or BlueALSA. At least one must be running.
- **Tools**: `pactl`, `pacmd`, `paplay`, `parecord` (PulseAudio/PipeWire PA-compat), `pw-dump`, `pw-play`, `pw-record`, `wpctl` (PipeWire native), `bluealsa-cli` (BlueALSA), `aplay`/`arecord` (ALSA), `sox` (analysis). Run `bleep --check-env` to verify.

## Commands

```bash
# Enumerate cards/profiles, play test file to sinks, record from sources/sinks, analyse with sox
bleep audio-recon

# Filter by device MAC
bleep audio-recon --device AA:BB:CC:DD:EE:FF

# Use a specific test file for playback
bleep audio-recon --test-file /path/to/piano.wav

# Skip playback or recording
bleep audio-recon --no-play --no-record

# Write structured result to JSON
bleep audio-recon --out /tmp/recon_result.json

# Custom record directory and duration (default: /tmp, 8s)
bleep audio-recon --record-dir /tmp --duration 5
```

Same options are available under the audio mode:

```bash
python -m bleep.modes.audio recon --device AA:BB:CC:DD:EE:FF --out /tmp/out.json
```

## Result structure

The recon result (and optional `--out` JSON) has this shape:

- **backend**: `"pulseaudio"` | `"pipewire"` | `"pipewire_native"` | `"bluealsa"` | `"none"`
- **cards**: List of cards (PA/PipeWire); each card has:
  - **index**, **name**, **mac_address**
  - **profiles**: List of profiles; each profile has **name**, **sources**, **sinks**
  - Each source/sink has **name**, **role** (microphone, headset_stream, speaker, interest, unknown), and if recording was run: **record_path**, **record_ok**, **has_audio**
- **bluealsa_pcms**: List of BlueALSA PCM entries; each has **pcm_path**, **mac_address**, **profile** (a2dp/sco), **direction** (sink/source), **alsa_device**, and optional **play_ok**, **record_path**, **record_ok**, **has_audio**
- **recordings**: Flat list of recording entries: **interface**, **role**, **profile**, **card_index**, **output_path**, **record_ok**, **has_audio**
- **errors**: List of error codes (e.g. `backend_not_supported`, `no_bluez_devices`)

Recordings are written under the record directory (default `/tmp`) unless disabled with `--no-record`.

## Role mapping

Role assignments are derived from observed ALSA source/sink naming behaviour on real Bluetooth audio devices:

- **Sources section** (interfaces listed under a PulseAudio card's `sources:` block):
  - `bluez_source.*` -> **microphone** (the headset's microphone input)
  - `bluez_sink.*` -> **headset_stream** (the audio stream being sent to the headset speakers, exposed as a recordable monitor)
- **Sinks section** (interfaces listed under a PulseAudio card's `sinks:` block):
  - `bluez_sink.*` -> **speaker** (the headset's speakers / audio output)
  - `bluez_source.*` -> **interest** (unusual; observed infrequently -- flagged for investigation)

The available interfaces change depending on the active profile selected for the Bluetooth device (e.g. A2DP vs HFP/HSP). BLEEP iterates through each profile to capture the full set.

## Supported backends

| Backend | Detection | Per-profile enum | Play / Record | Notes |
|---------|-----------|------------------|---------------|-------|
| **PulseAudio** | `pactl info` | `pactl list cards`, `pacmd list-cards` for sources/sinks | `paplay` / `parecord` | Fully supported |
| **PipeWire (PA compat)** | `pw-cli info` or `pactl info` showing PipeWire | Falls through to PulseAudio compat tools | `paplay` / `parecord` | Backend reported as `pipewire`; same tool path as PulseAudio |
| **PipeWire (native)** | `pw-cli info` succeeds but `pactl` absent or fails | `pw-dump` JSON for Bluetooth nodes; `wpctl set-profile` for switching | `pw-play --target=<id>` / `pw-record --target=<id>` | Backend reported as `pipewire_native`; requires `pw-dump`, `pw-play`, `pw-record`, `wpctl` |
| **BlueALSA** | `bluealsa-cli list-pcms` succeeds | PCMs enumerated directly with MAC, profile, direction | `aplay -D bluealsa:DEV=...` / `arecord -D bluealsa:DEV=...` | Backend `bluealsa` when sole backend; also enumerated as supplement when PA/PW is present |
| **ALSA (raw)** | `aplay -l` / `arecord -l` | Device listing only; no profile switching | `aplay` / `arecord` | Lowest-level fallback; no card/profile management |

BLEEP prefers the lowest-level tools available (ALSA utilities). BlueALSA is an acceptable bridge between Bluetooth and ALSA. Higher-level servers (PulseAudio, PipeWire) are also supported because they provide richer visibility in many scenarios. Different tools yield different levels of visibility:

- **BlueALSA** exposes per-profile PCM devices directly (one ALSA device per MAC + profile + direction).
- **PulseAudio** exposes cards with switchable profiles and per-profile sources/sinks.
- **PipeWire native** dumps the full media graph as JSON; nodes carry media class, profiles, and state.

### BlueALSA prerequisites

1. Install `bluealsa` (package name varies by distro; often `bluez-alsa` or `bluealsa`).
2. Start the BlueALSA daemon: `sudo bluealsa -p a2dp-sink -p a2dp-source -p hfp-hf`.
3. Ensure `bluealsa-cli` is on `$PATH` (`bleep --check-env` will verify).
4. **`asound.conf` / `.asoundrc`**: BlueALSA PCM devices are usable without any `asound.conf` changes when addressed explicitly (e.g. `aplay -D bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp file.wav`). If you want them as the default ALSA device, add a `pcm.!default` entry pointing to the BlueALSA PCM plugin.

### PipeWire native prerequisites

Ensure `pw-dump`, `pw-play`, `pw-record`, and `wpctl` are on `$PATH`. On most PipeWire installations these come with the `pipewire-utils` (or equivalent) package. Run `bleep --check-env` to verify.

If PulseAudio compatibility is available (`pactl info` works), BLEEP uses the PA-compat path by default. The native path is only engaged when PA compat is absent.

## Implementation notes

- **audio_tools.py**: `AudioToolsHelper` provides backend detection (including `pipewire_native` and `bluealsa` differentiation), BlueZ card listing (PA), PipeWire node enumeration (`_get_pipewire_bluez_nodes`), BlueALSA PCM listing (`list_bluealsa_pcms`), profile listing and switching (PA via `pactl`, PipeWire via `wpctl`), pacmd- and pw-dump-based parsing of sources/sinks with roles, and `play_to_sink` / `record_from_source` with automatic tool selection. Sox-based "has audio" check is in `check_audio_file_has_content()`.
- **audio_recon.py**: `run_audio_recon()` dispatches to backend-specific helpers (`_recon_pulseaudio`, `_recon_pipewire_native`, `_recon_bluealsa`). BlueALSA is also enumerated as a supplement when PA/PW is the primary backend.
- **Preflight**: All audio tools are checked: `sox`, `paplay`, `pacmd`, `pw-dump`, `pw-play`, `pw-record`, `wpctl`, `bluealsa-aplay`, `bluealsa-cli`, `bluealsa-rfcomm`.
- **Amusica integration**: Audio recon is used as a component of the Amusica workflow (`bleep amusica scan --connect`). Amusica calls `run_audio_recon()` with the target MAC filter after a successful JustWorks connection. See `bleep/ble_ops/amusica.py` and the Amusica section in `bleep/docs/todo_tracker.md` for the full workflow and future work items that build on these bonus objectives.

---

## Future work: Bonus Objectives

The following objectives are documented here to ease later expansion. They represent advanced audio stream manipulation capabilities beyond the core recon functionality.

### 1. Duplicate audio played to a device and record it

**Goal**: While audio is played to a connected Bluetooth device (e.g. headset), duplicate that same stream and record it (e.g. for verification or logging).

**Possible approaches**:

- **PulseAudio/PipeWire**: Use a "loopback" or "monitor" source that captures what is being sent to a given sink. Enumerate monitor sources for the target sink (e.g. `pactl list sources short` and match monitor of the sink), then `parecord -d <monitor_source> out.wav` for the desired duration. Implementation: add `get_monitor_source_for_sink(sink_name)` in `audio_tools.py` (parse `pactl list sources` or `pacmd list-sources` for the sink's monitor), then a `record_sink_playback(sink_id, output_path, duration_sec)` that records from that monitor.
- **ALSA**: If using ALSA directly (e.g. BlueALSA), investigate ALSA loopback or dmix/dsnoop so the same playback stream can be captured; document the chosen method in this file.

**Integration**: Optional step in `run_audio_recon()` (e.g. "record what we played") or a separate helper used by a new CLI subcommand (e.g. `bleep audio record-playback --device ... --sink ... --out ...`).

**Dependencies**: Existing `record_from_source` and sink enumeration; no new external binaries strictly required if monitor sources are available.

---

### 2. Consolidate all audio streams into a single recording

**Goal**: Record headset speakers and headset microphone (and any other device streams) into one mixed audio stream (e.g. one WAV file with multiple channels or a single mixed channel).

**Possible approaches**:

- **PulseAudio**: Use `parecord` with a "combined" or "null" sink that has multiple inputs, or create a temporary null sink, move multiple sources to it, and record the null sink's monitor. Alternatively use `pactl load-module module-loopback` / PipeWire graph to route multiple sources into one virtual source and record that.
- **Post-capture mix**: Record each interface separately (as recon already does), then use **sox** or **ffmpeg** to mix the WAVs (e.g. `sox -m mic.wav spk.wav mixed.wav` or multi-channel layout). Implementation: new function in `audio_tools.py` or a small `audio_mix.py` that takes a list of WAV paths and outputs one file; recon could optionally call it after recording.

**Integration**: New option in recon, e.g. `--consolidate-out /path/to/mixed.wav`, or a dedicated command `bleep audio consolidate --device ... --sources ... --out ...`.

**Dependencies**: sox or ffmpeg for mixing if using post-capture; otherwise PulseAudio/PipeWire modules.

---

### 3. Play audio into existing streams of a connected device

**Goal**: Play additional audio (e.g. background music or piano) into the existing audio stream that the headset is already receiving (mix with existing playback).

**Possible approaches**:

- **PulseAudio/PipeWire**: Use a **loopback** from a "file" or "playback" source into the same sink the device is using. E.g. create a playback stream that plays the extra file and set its target sink to the Bluetooth sink; the server will mix it with other streams. Implementation: ensure playback via `paplay -d <sink> file.wav` (or equivalent API) targets the device sink; if the device is already the default sink, that may be sufficient. For explicit "inject into this sink only", use module-loopback or the server's stream routing so the extra file is played to that sink.
- **ALSA**: Route an extra playback stream (e.g. `aplay -D <same_device> extra.wav`) so it is mixed with existing playback; may require dmix or explicit multi-client setup.

**Integration**: New helper e.g. `play_into_sink(sink_id, file_path, duration_sec)` that explicitly targets the given sink (and documents that it adds to existing stream). Option in recon, e.g. `--play-extra /path/to/extra.wav`, or a dedicated `bleep audio play-into --device ... --sink ... --file ...`.

**Dependencies**: paplay/aplay and sink/device selection; no new binaries.

---

### 4. Reconfigure audio I/O of existing interfaces

**Goal**: Change how an interface is used; e.g. use the headset microphone as a "speaker" for capturing recordings (e.g. for later transcription), or play audio into the headset microphone so it appears as additional input to the user.

**Possible approaches**:

- **Software routing**: Treat "microphone as output" as "record from the mic and write to a file" (already supported). "Play into the mic" is not physically supported by the hardware; the only option is to **inject audio into the same path the user hears** (see Bonus 3) so it is mixed with their side; or use a virtual source that the application reads as "microphone" and feed that from a file (PulseAudio: create a null source, play file to it, applications that record from "default source" could be pointed to that null source -- out of scope for BLEEP device recon).
- **Reconfig semantics for BLEEP**: (a) "Use mic for capture only" = current record-from-source. (b) "Present device playback as a single capture" = duplicate playback stream (Bonus 1). (c) "Play extra audio into device playback" = Bonus 3. Document in this file that "reconfig" is implemented via these building blocks unless the platform gains explicit role-switching APIs.

**Integration**: No new low-level reconfig call; document the mapping above and add a small "reconfig" helper or CLI that composes existing play/record and optional consolidate/play-into.

**Dependencies**: Same as Bonus 1 and 3.

---

### 5. Persist recon and bonus results in the observation DB

**Goal**: Track audio device info (cards, profiles, interfaces, roles, and optionally recording paths / has_audio) in the same observation store as the rest of BLEEP for visibility and reporting.

**Possible approaches**:

- Add an **audio_recon** table (or reuse a generic "snapshot" table) with columns such as: `mac`, `card_index`, `card_name`, `profile_name`, `interface_name`, `role`, `record_path`, `has_audio`, `recon_time`, `result_json` (optional). Insert/update from `run_audio_recon()` when `output_json_path` is set or a new flag `--persist` is set.
- Alternatively store a single JSON blob per device per recon run in an existing table (e.g. device notes or a new `audio_recon_snapshots` table with `mac`, `timestamp`, `result_json`).

**Integration**: In `run_audio_recon()`, after building the result dict, call a new `bleep.core.observations` function (e.g. `store_audio_recon_result(mac, result)`) when persistence is requested; keep the current file-based `--out` as-is.

**Dependencies**: Observation DB schema change; follow existing patterns in `observations.py` (e.g. `snapshot_media_transport`).

---

### Summary table

| Bonus objective                         | Main building blocks              | New code likely location     | DB / persistence |
|----------------------------------------|-----------------------------------|------------------------------|------------------|
| Duplicate playback and record           | Monitor source, record_from_source| audio_tools + optional recon  | Optional         |
| Consolidate streams to one recording   | Multiple record + sox/ffmpeg mix  | audio_tools or audio_mix     | Optional         |
| Play into existing stream              | play_to_sink, sink selection      | audio_tools + optional recon | No               |
| Reconfig I/O                           | Compose 1-3                       | Helpers + docs               | Optional         |
| Persist recon in observation DB        | run_audio_recon result            | core/observations + recon    | Yes (schema)     |

Implementing in the order 1, 2, 3, 4, 5 will minimise duplication and keep a clear path from current recon to full bonus behaviour.
