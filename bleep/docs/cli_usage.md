# CLI quick-start

The CLI can be accessed in two ways:

## Method 1: Using the Package Module (Recommended)

```bash
python -m bleep --help        # top-level help / version
python -m bleep               # interactive REPL (no subcommand)
python -m bleep scan --timeout 15
```

The `python -m bleep.cli` form also works and is equivalent.

## Method 2: Using the Package Entry Point (If Installed)

If the package is installed with `pip install -e .`:

```bash
bleep --help   # top-level help / version
```

> **Note:** BLEEP requires PyGObject (python3-gi) for core D-Bus operations. Install via your system package manager:
> - Ubuntu/Debian/Kali: `sudo apt-get install python3-gi`
> - Arch Linux: `sudo pacman -S python-gobject`
> 
> PyGObject is optional in pip install (moved to `extras_require["monitor"]`) to prevent build failures, but **required at runtime** for scanning, connecting, and monitoring operations.

### Global flags

These apply to the top-level `bleep` invocation (placed before the subcommand):

| Flag | Effect |
|------|--------|
| `--version` | Print `BLEEP <version> (DB schema v<N>)` and exit |
| `--check-env` | Check environment capabilities (tools, configs, dependencies, BlueZ experimental surfaces) and exit |
| `--diagnose-audio` | Run a detailed audio-stack diagnostic with install guidance and exit |
| `--json` | Emit structured JSON output to stdout (suppresses banner) |
| `--quiet`, `-q` | Suppress banner and progress messages; emit results only |

### BLE Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `scan` | Passive BLE scan for advertising packets; `--monitor` uses AdvertisementMonitor Flags-OR overlay ([docs](ble_scan_modes.md), [adv_monitor.md](adv_monitor.md)) | `bleep scan --timeout 15 --variant naggy` |
| `connect` | Connect + enumerate (auto-routes Classic; `--ble-only` forces GATT) | `bleep connect AA:BB:CC:DD:EE:FF` |
| `gatt-enum` | Single-pass GATT enumeration; `--deep` for retry reads & descriptor probing, `--report` for landmine/security JSON ([docs](gatt_enumeration.md)) | `bleep gatt-enum AA:BB:... --deep` |
| `enum-scan` | Multi-variant enumeration engine: passive, naggy, pokey, or brute ([docs](gatt_enumeration.md)) | `bleep enum-scan AA:BB:... --variant naggy` |
| `explore` | Scan & produce JSON mapping for later offline analysis ([docs](explore_mode.md)) | `bleep explore AA:BB:... --out dump.json --connection-mode naggy` |
| `analyse` / `analyze` | Post-process one or more JSON dumps ([docs](analysis_mode.md)) | `bleep analyse dump1.json dump2.json --detailed` |
| `signal` | Subscribe to characteristic notifications/indications ([docs](signal_capture.md)) | `bleep signal AA:BB:... char002d --time 60` |
| `signal-config` | Manage signal capture configurations ([docs](signal_capture.md)) | `bleep signal-config create my-config --default` |
| `survey` | Long-duration passive device census for LE + Classic; `--collector` for concurrent antennas, `--enumerator` for listen+enum, `--listen-monitor` for AdvMonitor Flags-OR overlay ([docs](survey_mode.md)) | `bleep survey --collector hci0:le --listen-monitor --enumerator hci1:passive --duration 120 --live -o targets.json` |
| `beacon-identification` | Discover/rank BLE beacons by OUI/name/decoded fields ([docs](beacon_identification.md)) | `bleep beacon-identification --oui 10:20:BA --name '*Beacon*' --live` |
| `aoi` | Enumerate Assets-of-Interest: scan, analyze, report, export ([docs](aoi_mode.md)) | `bleep aoi targets.json --file test-file.json --delay 5.0` |
| `ctf` | BLE CTF challenge solver and analyzer ([docs](ble_ctf_mode.md)) | `bleep ctf --discover --device CC:50:E3:B6:BC:A6` |
| `uuid-translate` | Translate UUID(s) to human-readable names ([docs](uuid_translation.md)) | `bleep uuid-translate 2a00 180a --verbose` |
| `advertise-monitor` | Advertisement Monitor: Flags-OR (no `-p`), `--manufacturer CID[:HEX]`, `--mfr-string TEXT`, or `-p` patterns (`caps`, `start`) ([docs](adv_monitor.md)) | `bleep advertise-monitor start --manufacturer 0x0006` |
| `advertise` | LE Advertising: broadcast custom BLE advertisements (`caps`, `start`) | `bleep advertise start` |
| `gatt-server` | GATT Server: publish local BLE services (`start`) | `bleep gatt-server start` |
| `device-sets` | DeviceSet1: manage coordinated device sets / TWS earbuds (`list`, `connect`, `disconnect`, `info`) | `bleep device-sets list` |
| `mesh` | Bluetooth Mesh provisioning [experimental] (`join`, `provision`, `reprovision`) | `bleep mesh join` |

### Classic Bluetooth Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `classic-scan` | Passive Classic (BR/EDR) scan | `bleep classic-scan --timeout 10 --uuid 110b,110e --debug` |
| `classic-connect` | Connect to Classic device via SDP + RFCOMM ([docs](bl_classic_mode.md)) | `bleep classic-connect AA:BB:... --keep` |
| `classic-enum` | Enumerate Classic RFCOMM/SDP services ([docs](bl_classic_mode.md)) | `bleep classic-enum AA:BB:... --analyze --version-info` |
| `classic-pbap` | Download phone-book via PBAP to VCF ([docs](bl_classic_mode.md)) | `bleep classic-pbap AA:BB:... --repos ALL --out pb.vcf` |
| `classic-opp` | Object Push Profile: send/pull/exchange files ([docs](bl_classic_mode.md)) | `bleep classic-opp AA:BB:... send file.vcf` |
| `classic-map` | Message Access Profile: browse SMS/MMS ([docs](bl_classic_mode.md)) | `bleep classic-map AA:BB:... inbox` |
| `classic-ftp` | OBEX File Transfer: ls/get/put/mkdir/rm ([docs](bl_classic_mode.md)) | `bleep classic-ftp AA:BB:... ls /` |
| `classic-pan` | Personal Area Networking: connect / server-reg / server-unreg ([docs](bl_classic_mode.md)) | `bleep classic-pan connect AA:BB:... --role nap` |
| `classic-spp` | Serial Port Profile: register/unregister ([docs](bl_classic_mode.md)) | `bleep classic-spp register --name "BLEEP SPP"` |
| `classic-sync` | IrMC Synchronization: get/put phonebook ([docs](bl_classic_mode.md)) | `bleep classic-sync AA:BB:... get --output pb.vcf` |
| `classic-bip` | Basic Imaging Profile: props/get/thumb [experimental] ([docs](bl_classic_mode.md)) | `bleep classic-bip AA:BB:... get <handle> --output img.jpg` |
| `connect-profile` | Connect/disconnect a specific profile by UUID (positional `uuid`; `--disconnect` tears down) ([docs](bl_classic_mode.md)) | `bleep connect-profile AA:BB:... 0000110a-0000-1000-8000-00805f9b34fb` |
| `classic-rfcomm` | Enumerate & optionally probe RFCOMM channels via SDP ([docs](bl_classic_mode.md)) | `bleep classic-rfcomm AA:BB:CC:DD:EE:FF` |
| `network-enum` | Enumerate PAN network-capable devices (`--adapter/--json/--all-devices`) ([docs](bl_classic_mode.md)) | `bleep network-enum --all-devices --json` |
| `hid-info` | Classify a device as HID (keyboard/mouse/gamepad); `--connect` harvests richer connected evidence (Input1.ReconnectMode) ([docs](device_type_classification.md)) | `bleep hid-info AA:BB:...` / `bleep hid-info AA:BB:... --connect` |
| `classic-ping` | L2CAP echo (l2ping) reachability test | `bleep classic-ping AA:BB:... --count 5` |

### Media & Audio Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `media-enum` | Enumerate AVRCP / MediaPlayer capabilities ([docs](media_mode.md)) | `bleep media-enum AA:BB:... --verbose --monitor` |
| `media-ctrl` | Control playback & volume on a media device | `bleep media-ctrl AA:BB:... play` |
| `audio-profiles` | List Bluetooth audio profiles via ALSA correlation | `bleep audio-profiles --device AA:BB:...` |
| `audio-play` | Play audio file to Bluetooth device | `bleep audio-play AA:BB:... song.mp3 --volume 80` |
| `audio-record` | Record audio from Bluetooth device (A2DP; add `--hfp` for the HFP/HSP microphone) | `bleep audio-record AA:BB:... output.wav --duration 30` / `bleep audio-record AA:BB:... mic.wav --hfp` |
| `audio-recon` | Audio recon: enumerate cards, play, record, analyse ([docs](audio_recon.md)) | `bleep audio-recon --device AA:BB:... --out result.json` |
| `audio-intercept` | Capture and optionally transcribe audio from a BT device ([docs](audio_recon.md)) | `bleep audio-intercept AA:BB:... --duration 15` |
| `amusica` | Amusica: scan, connect, recon, manipulate audio targets | `bleep amusica scan --timeout 10` |
| `audio-config` | Manage ALSA/BlueALSA config (`show`/`add`/`remove`/`tunnel`/`backup`/`restore`) | `bleep audio-config show` |

### Database Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `db list` | List devices in the observation database; filter by `--status`, `--name` (name substring), `--fields`, `--limit/--offset`, and a collection-date window `--since/--until` (dates in `--tz`, default UTC) selected by `--seen-basis {first,last,any}`. `--export-targets PATH` writes the selection as an AoI-ingestable target list; `--group-identity[=name|name_mfr|payload]` shows a heuristic RPA-identity-collapsed view (raw view is the default); `--name-audit` classifies device names into placeholder(own-MAC)/real/empty/foreign-MAC(anomaly) buckets with full collected records for real-named devices, tuned by `--name-sample`/`--name-detail-limit` ([docs](observation_db.md)) | `bleep db list --since 2026-08-06 --until 2026-08-09 --status ble --export-targets targets.json` |
| `db show` | Show device detail; add `--full` for complete formatted JSON | `bleep db show AA:BB:CC:DD:EE:FF --full` |
| `db report` | Batch, date-scoped aggregate security report over the windowed/filtered device set (delegates to the AoI report engine; includes advert-only devices in a "Not Reachable" section). `--format {markdown,json,text}`, `--since/--until/--seen-basis/--tz`, `--status/--name` filters, `--all-in-window` (else capped at `--limit`, default 500), `--group-identity`/`--identity-contrast` to compare raw vs heuristically-collapsed counts, `--name-audit` to append a Name Audit section (placeholder/real/empty/foreign-MAC buckets + anomaly warnings), and `--recon` to append a Reconnaissance Analytics section (unique-SDP inventory with counts, OUI/address-type breakdown with IEEE vendor decode, and manufacturer/service/AD hex pattern-detection + decode; `--recon-detail` also analyses characteristic-value hex). Reports use a unified `<unique entry> : <count>` notation; SDP/OUI inventories render as markdown tables by default with `--report-bullets` for the bullet form ([docs](observation_db.md)) | `bleep db report --since 2026-08-06 --until 2026-08-09 --all-in-window --recon` |
| `db timeline` | View chronological characteristic history; add `--sdp` (optionally `--uuid`) to show Classic SDP record change history instead — an `[initial]` snapshot then per-snapshot field diffs (incl. handle rotation) ([docs](observation_db.md)) | `bleep db timeline AA:BB:... --sdp --uuid 1101` |
| `db export` | Export device data to JSON; `--max-history N` / `--max-adv N` cap the per-device characteristic-history / advertisement-report rows (`0` = unlimited; defaults 500 / 100) | `bleep db export AA:BB:... --out device.json --max-history 0` |
| `db uuids` | Observed-UUID catalogue ("seen in the wild"): aggregate distinct UUIDs across all tables with names/counts/sources; `--uuid` filters one, `--promote NAME` persists a name into the custom-UUID overlay, `--seed` unions the curated non-SIG seed (`source=curated_seed`) ([docs](observation_db.md)) | `bleep db uuids --seed` |
| `db maintain` | Run VACUUM + integrity check + stats on the observation database | `bleep db maintain` |

### Agent & Configuration Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `pair` | Pair with a Bluetooth device ([docs](pairing_agent.md)) | `bleep pair AA:BB:... --interactive` |
| `agent` | Run a pairing agent ([docs](agent_mode.md)) | `bleep agent --mode interactive --cap keyboard` |
| `adapter-config` | Show/get/set Bluetooth adapter properties ([docs](adapter_config.md)) | `bleep adapter-config show --adapter hci0` |
| `refresh-refs` | Regenerate committed reference data in place (BT SIG assigned numbers, BlueZ SDP universal attribute IDs, SIG profile SDP attribute IDs, CoD/mesh, vendor/community adv specs, IEEE OUI vendor database, USB-IF ID database); network-best-effort with committed-cache fallback. `--sig-only`/`--vendor-only`/`--oui-only`/`--usb-only` (mutually exclusive) scope the refresh; `--local-path` bootstraps vendor specs from a local checkout ([docs](uuid_translation.md)) | `bleep refresh-refs --oui-only` |
| `user` | User-friendly interactive Bluetooth explorer ([docs](user_mode.md)); add `--menu` for the numbered main-menu UI | `bleep user --scan 10 --device AA:BB:... --menu` |
| `interactive` | Enter interactive REPL console | `bleep interactive` |
| `debug` | Enter the interactive Debug Mode shell (low-level D-Bus, GATT, media, classic — see [docs](debug_mode.md)) | `bleep debug --no-connect` |

> The `debug` subcommand and `python -m bleep.modes.debug` are equivalent and both supported.  `bleep debug` is the canonical, discoverable form; the `-m`-style invocation remains available for scripts and CI that already depend on it.

> **Note:** All examples above use the short-form `bleep` command (available after `pip install -e .`).  Substitute `python -m bleep` if the package is not pip-installed.

Characteristic reads are automatically archived in the local database (no CLI flag needed).

Run `bleep <command> --help` for detailed per-command options.

### Environment variables

| Variable | Effect |
|----------|--------|
| `BLEEP_LOG_LEVEL` | Override default log level (`DEBUG`, `INFO`, etc.) |
| `BLE_CTF_MAC` | Default MAC address for CTF challenges (used by the `bleep ctf` command) |

### Hint convention (CLI vs. Debug Mode commands)

User-facing hint strings emitted from any CLI-reachable code path
(`bleep <subcommand>` and everything it transitively imports) **must** obey
one of the following two patterns.  This rule exists because debug-shell
commands like `audiocfg`, `mediaenum`, `audioplay`, `copp send`, `csdp`,
`copen`, etc. are not reachable from the CLI parser — referencing them
without context leaves the operator at a dead end.

1. **Reference a CLI subcommand directly.**  Example:

   > "Endpoint contention detected — rerun with `bleep audio-recon` for full details."

2. **Frame the hint with the literal phrase `Debug Mode`** so the operator
   knows they must enter the debug shell first.  The canonical wording is
   the parenthetical `(in Debug Mode: '<command>')` form.  Example:

   > "Endpoint contention: severity=warn (in Debug Mode: 'audiocfg --endpoints')"

A bare debug-shell command name (e.g. `"see 'audiocfg --endpoints'"`)
without the `Debug Mode` phrase is **forbidden** in CLI-reachable output.

The convention is enforced at test time by
[`tests/test_cli_hint_convention.py`](../../tests/test_cli_hint_convention.py),
which AST-walks every CLI-reachable module for string literals that
contain a known debug-shell command token and asserts that each such
literal also contains either `bleep debug` or `Debug Mode`.

To enter Debug Mode (both forms are equivalent and supported):

```bash
bleep debug                       # canonical form
python -m bleep.modes.debug       # legacy / scripting form
```

### Exit codes

`0` success, non-zero indicates an error (see stderr for details).

### Environmental limitations & known constraints

These are properties of the host adapter, kernel, or container — **not** BLEEP
defects. BLEEP now surfaces the underlying BlueZ/OS error in each case instead of
failing silently.

- **LE advertising payload conflicts** — BlueZ rejects an advertisement that both
  sets a property explicitly *and* asks it to auto-include the same field via
  `Includes` (`org.bluez.Error.Failed: Failed to parse advertisement`). Verified
  conflicts: `LocalName` vs `--include-name` and `Appearance` vs
  `--include-appearance` (`TxPower` vs `--include-tx-power` does **not** conflict).
  BLEEP now resolves these automatically — the explicit value wins and the
  redundant include is dropped — so `advertise start` no longer fails on them.
  (Both `peripheral` and `broadcast` advertising work; the earlier "peripheral is
  unsupported" behaviour was a symptom of the P0 dispatch bug leaving orphaned
  registrations, and is resolved.)
- **`--include-appearance` without an explicit `--appearance`** — `--appearance
  <value>` sends a *self-contained* Appearance in the advertisement, whereas
  `--include-appearance` asks BlueZ to *source* the value from the adapter/system
  appearance, which is frequently unset. When it is unset the controller rejects
  the advertisement with `org.bluez.Error.Failed: Failed to register
  advertisement` (even though `appearance` is listed in `SupportedIncludes` —
  "supported" ≠ "a value is available"). BLEEP now **warns before registering**
  when `--include-appearance` is used without a value and prints a **targeted
  hint** on failure. Pass an explicit `--appearance <value>` for reliable
  behaviour (it may be combined with `--include-appearance`; the explicit value
  wins). The same self-contained vs. sourced distinction applies to
  `--name`/`--include-name`.
- **Requested include not in `SupportedIncludes`** — `advertise start` now
  pre-flights the requested `--include-*` flags against the adapter's
  `SupportedIncludes` (see `advertise caps`) and warns before registering when an
  include is not advertised as supported.
- **AdvertisementMonitor (`advertise-monitor` / `scan --monitor` / `survey --listen-monitor`)** — requires `AdvertisementMonitorManager1` (`bluetoothd -E`). Empty `or_patterns` is illegal. Omitting `-p` injects a one-monitor Flags-OR (`0x01` `{00,02,04,05,06,18,1A}`), not a 256-prefix cover. Survey extras: `--listen-manufacturer CID[:HEX]`, `--listen-mfr-string TEXT`, `--listen-pattern` (second `or_patterns` child; do not mix 0xFF onto the Flags child on software AdvMonitor). Same-adapter StartDiscovery is allowed; collectors stay discovering while the overlay is up. Overlay registration failure is logged and survey continues. `bleep --check-env` probes the interface. Dual-antenna `--enumerator` runs on a worker while collectors harvest; `--duration` is listen/admission only; `--enum-cooldown` (default 3600s) plus this-run `done`/`ok` prevent re-enum from collector re-sights.
- **Long-running `survey` collection (`--segment-time`, `--stall-rounds`, `--metrics-interval`, `--no-mainloop`, `--max-enum-devices`)** — a single survey process stops collecting after ~80 harvest rounds (~42 min); the adapter stops answering D-Bus and no in-process recovery clears it (see [`d-bus-reliability.md`](d-bus-reliability.md)). A `--duration` above `--segment-time` (default `1800`, i.e. 30 min) is therefore split into consecutive segments in fresh processes and merged into one census; `--segment-time 0` disables splitting. `--stall-rounds N` (default 3) sets how many device-report-free rounds declare a stall, which escalates re-arm → adapter power cycle (only with `--auto-recover`) → end the listen phase early and record `<output>.health.json` with `degraded: true`. `--metrics-interval N` samples RSS, threads, fds, census/pool size, D-Bus match rules, socket backlog and BlueZ harvest size to `<output>.metrics.csv`. `--no-mainloop` removes the GLib loop thread to avoid the `GMainContext` data race (see [`mainloop_architecture.md`](mainloop_architecture.md)) and is therefore **passive-enumeration only** — it is refused with `--listen-monitor` or pair mode, and refused outright in the debug shell. `--max-enum-devices N` bounds live enumeration device objects (default 10, `0` = unlimited, also settable via `BLEEP_MAX_ENUM_DEVICES`). Full detail in [`survey_mode.md`](survey_mode.md).
- **`classic-ping` under WSL** — `l2ping` needs `CAP_NET_RAW`; unprivileged WSL
  users get `Operation not permitted`. Run as root or grant the capability.
- **`audio-play` / `audio-record` (SBC codec paths)** — require GStreamer codec
  plugins (`gstreamer1.0-plugins-good`, `-bad`, and `libgstreamer-plugins-*`).
  Run `bleep --diagnose-audio`; the verdict now reports "routing available but
  codec plugins incomplete" when only the routing stack (PipeWire/PulseAudio) is
  present. Audio *routing* still works without the codec plugins; only the
  BLEEP-owned capture/playback pipelines are affected.