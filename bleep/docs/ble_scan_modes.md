# BLE Scan Variants in **BLEEP**

BLEEP offers four discovery-scan presets that balance radio footprint versus information gain. All are implemented in `bleep.ble_ops.le.scan` and available through:

```bash
python -m bleep.cli scan --variant <passive|naggy|pokey|brute> [--timeout 15] [--target AA:BB:CC:DD:EE:FF] [--adapter hciN] [--transport auto|le|bredr]
```

| Variant | Behaviour | When to use |
|---------|-----------|-------------|
| **passive** (default) | Standard LE discovery (BlueZ default `DuplicateData=false`, duplicate suppression on). One merged Transport filter per start. | Quiet landscape sweep. |
| **naggy** | One merged filter with `DuplicateData=true` → BlueZ emits ManufacturerData/ServiceData changes when the controller allows. | Collect RSSI graph, see peri-connection adverts, capture rotating beacons. |
| **pokey** | Repeats 1-second **naggy** scans for *N* seconds. Optional `--target <MAC>` merges a colonized BlueZ `Pattern` (client-side MAC filter remains authoritative). | Force a *specific* device to emit transient adverts (privacy MACs, button-press beacons). |
| **brute** | Two-phase: BR/EDR inquiry (half timeout) + naggy LE (half timeout). | Maximum coverage, noisy. |

### Adapter selection (`--adapter`, F5)

`--adapter hciN` selects the BlueZ controller for **all** scan variants
(passive/naggy/pokey/brute). The name is validated up-front via
`core.preflight.require_adapter`: a missing or not-ready controller fails with a
non-zero exit and a named diagnostic (`[!] Bluetooth adapter not found or not
ready: hciN`) rather than silently falling back to the default. Omitting the flag
uses the parser default `hci0` (== `ADAPTER_NAME`), so single-adapter hosts are
unaffected.

`--transport {auto,le,bredr}` is honored by passive/naggy **and** pokey (every
round uses the same transport/controller). `brute` is intrinsically dual-phase
(BR/EDR then LE) and ignores `--transport`, but both phases run on the selected
`--adapter`. For classic non-connectable iBeacons use `--transport le` (see
changelog "iBeacon LE transport").

`enum-scan --adapter hciN` (F5b) and `classic-scan --adapter hciN` (F5c) apply
the same policy. `enum-scan` threads the controller through the LE
connect/enumerate spine (`EnumerationController` → the connect primitive → the
`*_enum` variants) and gates on `require_adapter` before connecting;
`classic-scan` builds the BR/EDR inquiry on the selected controller. Both default
to `hci0` when the flag is omitted. `aoi scan --adapter`, `gatt-enum --adapter`,
`explore --adapter`, `pair --adapter`, and `classic-connect --adapter` use the
same Device1 path (`/org/bluez/hciN/dev_…`). `skip_scan=True` skips PRE-FLIGHT
discovery when Device1 already exists on that adapter (enumerator
`ConnectDevice` path).

### Discovery harvest (R1/R2)

BlueZ creates filtered `Device1` objects **during** an active discovery session.
Unpaired non-connectable advertisers (classic iBeacon/Eddystone) are removed as
soon as `StopDiscovery` runs (`STOP_CLEARS`). BLEEP therefore:

1. **R1:** Snapshots `GetManagedObjects` in `DeviceManager._timeout` **before**
   `StopDiscovery`, then returns that list via `take_last_harvest()` (used by
   `_native_scan` / passive / naggy / pokey / brute).
2. **R2:** Maintains a per-session census from D-Bus `InterfacesAdded` /
   `PropertiesChanged`; on `InterfacesRemoved` the row is kept until the next
   `start_discovery`. Harvest merges GMO + census by MAC (last-shot mfr/sd).

Multi-collector survey calls `snapshot_discovered_devices()` while Discovering
is still true (`AdapterSession.harvest`), then ends the session.

### AdvertisementMonitor (`scan --monitor`)

`bleep scan --monitor` does **not** run `StartDiscovery`. It registers the
Flags-OR AdvMonitor (one child, GAP Flags `{00,02,04,05,06,18,1A}`) and streams
`DeviceFound`/`DeviceLost`. Empty `or_patterns` is illegal in BlueZ. Devices
without matching Flags will not appear here.

For a census that must not miss Device1 objects StartDiscovery can see, use
`bleep survey --listen-monitor`: harvest **union** Found. Manufacturer extras
(`--listen-manufacturer CID[:HEX]`, `--listen-mfr-string TEXT`) register as a
second AdvMonitor child. Same-adapter AdvMonitor + `StartDiscovery` is allowed.
See [adv_monitor.md](adv_monitor.md) and
[survey_mode.md](survey_mode.md#listen-monitor-overlay---listen-monitor). Requires
`bluetoothd -E` (`bleep --check-env`).

### Pokey deep-dive
A single long scan still yields one harvested set per run (R1/R2). Pokey mode
repeatedly stops/starts discovery (1 s each) so BlueZ re-creates Device1 objects
many times per minute – effectively *poking* devices and refreshing ephemeral
advert state. With `--target` BLEEP merges a colonized `Pattern` into the single
discovery filter as an optimization; client-side filtering still decides which
results are shown.

---

Run `bleep debug` (or the equivalent `python -m bleep.modes.debug`) and use commands:
* `scan`   → passive
* `scann`  → naggy
* `scanp <MAC>` → pokey
* `scanb`  → brute

for interactive tests.

---

## Connection Modes (Explore / Connect Paths)

The `bleep explore` command and the `scan_and_connect()` dispatcher in
`bleep.ble_ops.le.scan_modes` use a separate set of **connection mode**
presets. These presets control how BLEEP *connects to and enumerates* a single
target device (as opposed to passive discovery which only listens).

### Architecture (post-P4-3)

All connection mode functions in `scan_modes.py` are **thin wrappers** around
the canonical `connect_and_enumerate__bluetooth__low_energy()` primitive in
`bleep.ble_ops.le.connect`. Each wrapper passes mode-specific parameters
(scan attempts, connect retries, timeouts, backoff) and then performs any
post-connect work unique to that mode:

```
scan_modes.py wrapper                    connect.py
─────────────────────────────────────    ──────────────────────────────
passive_scan_and_connect()          ──►  _connect_enum(scan_attempts=3,
  └► _classify_device(log_flags)          connect_retries=1, ...)

naggy_scan_and_connect()            ──►  _connect_enum(max_attempts=N,
  └► _classify_device()                   backoff_base=0.5, ...)

pokey_scan_and_connect()            ──►  _connect_enum(scan_timeout=10,
  ├► _pokey_deep_read(device)             connect_retries=5, ...)
  └► _classify_device()

bruteforce_scan_and_connect()
  ├► pokey_scan_and_connect()       ──►  (same as pokey)
  ├► handle sweep (local)
  └► _classify_device()
```

Classic (BR/EDR) devices are intercepted early via `_classic_connect()` —
they bypass the LE pipeline entirely since Classic devices have no GATT
database.

### Mode Parameters

| Parameter | Passive | Naggy | Pokey | Bruteforce |
|-----------|---------|-------|-------|------------|
| `scan_attempts` | 3 | 5 | 3 | (via pokey) |
| `scan_timeout` | `timeout//2` (min 5) | 8 s | 10 s | (via pokey) |
| `connect_retries` | 1 | 2 | 5 | (via pokey) |
| `connect_wait_timeout` | `timeout//4` (min 5) | 5.0 s | 10.0 s | (via pokey) |
| `timeout_services` | `timeout` (min 15) | 20 s | 30 s | (via pokey) |
| `max_attempts` (outer retry) | 2 | `max_retries` (10) | 1 | (via pokey) |
| Backoff (base / max / jitter) | n/a | 0.5 / 30.0 / 0.5 | n/a | n/a |
| Post-connect | classify (log flags) | classify | deep read + classify | pokey + handle sweep + classify |

### Key Behavioural Notes

- **Naggy mode** benefits from the outer retry loop with exponential backoff
  inside `connect.py`. Transient D-Bus `InProgress`/`Failed` errors are
  forgiven (don't count toward `max_attempts`).
- **Pokey mode** uses `deep_enumeration=False` for the initial connect
  (standard GATT resolution only), then runs `_pokey_deep_read()` to
  individually read every characteristic value, property, and descriptor.
- **Bruteforce mode** delegates its initial connect/enumerate to pokey, then
  performs an exhaustive handle sweep (0x0001–0x00FF) trying to read and write
  handles not discovered by standard GATT resolution.

---

## Enumeration variants (_enum / enumn / enump / enumb_)

> **CLI commands:** The debug-shell shortcuts below correspond to the top-level
> CLI commands `gatt-enum` and `enum-scan`.  See
> [GATT Enumeration Commands](gatt_enumeration.md) for full documentation of
> CLI flags, output formats, deep vs standard mode, and the brute-force
> payload system.

Discovery finds devices; **enumeration** digs into a single target's GATT
database. Four presets mirror the discovery spectrum:

| Command (debug-shell) | Behaviour | Writes? | Typical duration |
|-----------------------|-----------|---------|------------------|
| `enum  <MAC>`        | One-shot read of every readable characteristic. | No | 3-10 s |
| `enumn <MAC>`        | Same read pass **3x** → spot transient changes. | No | 9-30 s |
| `enump <MAC> [-r N]` | After each read pass sends **0x00 / 0x01** to every writable characteristic (skips descriptors). | Light | 5-60 s |
| `enumb <MAC> <CHAR>` | Fuzz **one** characteristic — payloads built with `--range`, `--patterns`, or `--payload-file`. | Heavy | Depends on payload set |

> **`all` is CLI-only.** The debug-shell `enumb` targets a single characteristic
> UUID. To fuzz **all writable** characteristics, use the top-level CLI:
> `bleep enum-scan <MAC> --variant brute --write-char all` (routes through
> `multi_write_all()`).

### Safety flags

- `--verify` – re-reads after each write and logs mismatches.
- `--force`  – in the CLI `enum-scan` brute path, toggles `respect_roeng` (default honours landmine / permission maps; `--force` bypasses them). **The debug-shell `enumb` always runs with `respect_roeng=False`** (ROE off), so `--force` there only affects landmine-confirmation prompts, not ROE enforcement.

### CLI examples

```bash
# Passive enumeration (read-only)
bleep debug -d
BLEEP-DEBUG> enum AA:BB:CC:DD:EE:FF

# Naggy enumeration with mapping diff
BLEEP-DEBUG> enumn AA:BB:CC:DD:EE:FF

# Pokey: two rounds, verify writes
BLEEP-DEBUG> enump AA:BB:CC:DD:EE:FF --rounds 2 --verify

# Bruteforce a single characteristic with default single-byte payload set
BLEEP-DEBUG> enumb AA:BB:CC:DD:EE:FF 00002a37-... \
             --range 0x00-0x0F \
             --patterns ascii \
             --payload-file fuzz.bin --force --verify
```

Allowed pattern keywords now include:
- ascii – printable ASCII bytes
- inc   – incrementing length-prefixed byte strings
- alt   – single 0xAA / 0x55 bytes
- repeat:\<byte\>:\<len\> – repeat byte value *len* times  (e.g. repeat:ff:4)
- hex:\<deadbeef\>      – arbitrary hex string converted to raw bytes

Logs are written to `LOG__ENUM` for post-analysis (diffs, errors, landmine hits).

*Last updated: 2026-05-21*
