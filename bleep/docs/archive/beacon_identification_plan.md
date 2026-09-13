> **ARCHIVED — historical planning document (in-package copy).**
> This is the package-internal home of the original beacon-identification plan
> (validated 2026-08-12 against `ESP32-S3-Beacon` `10:20:BA:46:AE:D5`), relocated
> here so all beacon documentation is contained within `bleep/`.
>
> **Implemented since:** `bleep beacon-identification` (S1); compact-iBeacon
> `0xFFFF`/5-byte decode → `ibeacon_compact` (S2); UUID-only Eddystone inference
> → `eddystone_pending` (S3); inline beacon summaries via `format_beacon_summary()`
> wired into `ble_ops/le/scan.py` (S7).
> **Not implemented:** Espressif custom-UUID reference seeds (S10). Other items
> (S4–S6, S8–S9) may be partial — consult the code, not this plan, for status.
>
> **Authoritative, self-contained docs:** operator/reference guidance now lives in
> [`../beacon_identification.md`](../beacon_identification.md) (scoring, output
> JSON, flags, limitations) and [`../adv_dissection.md`](../adv_dissection.md)
> (decoder semantics). The `workDir/…` and `/tmp/…` paths referenced below are
> historical, host-specific validation artifacts (outside `bleep/`) — prefer the
> two in-package docs above.

---

# Beacon Identification — Planning Document

**Status:** Draft for review and acceptance  
**Date:** 2026-08-12  
**Scope:** `bleep/` codebase — discovery, identification, and enumeration of rotating Bluetooth LE beacons  
**Origin:** Beacon identification exercise against deployed target `ESP32-S3-Beacon` (`10:20:BA:46:AE:D5`)

---

## 1. Executive summary

Live validation located the deployed beacon at **`10:20:BA:46:AE:D5`** (not the documented `10:20:BA:46:AE:D6`). bleep's RF observation path is **functionally correct** — it reads the same BlueZ `Device1` properties as reference scripts in `workDir/BlueZScripts/` and does not drop devices BlueZ exposes (parity test: 4/4 match, 0 drops).

The failure mode is **beacon-specific operator experience**: discovery required a 5.5-minute generic survey, manual JSON inspection, and offline hex decoding. Automatic identification of major/minor, Eddystone phase, and rotation did not occur.

This document defines ten gaps (G1–G10), planned solutions (S1–S10), a priority matrix, and end-to-end acceptance criteria for manual verification before implementation begins.

---

## 2. Target device profile (reference)

Use this profile for all acceptance tests unless a lab fixture specifies otherwise.

| Field | Value |
|---|---|
| **MAC (deployed)** | `10:20:BA:46:AE:D5` |
| **MAC (documented — wrong)** | `10:20:BA:46:AE:D6` |
| **Local name** | `ESP32-S3-Beacon` |
| **OUI** | `10:20:BA` |
| **Rotation period** | ~98 seconds |
| **Formats** | iOS-style iBeacon, Android-style, Eddystone URL |
| **iBeacon UUID** | `6E5F0001-B5A3-F393-E0A9-E50E24DCCA9E` |
| **Major / Minor** | 1 / 169 |
| **Eddystone** | Service UUID `FEAA`; URL resolves to `https://espressif.com` |
| **Observed non-standard encoding** | Manufacturer ID `0xFFFF` with compact payload `000100a9c5` → major=1, minor=169, tx=-59 |

**Sibling device (same OUI, different role):**

| Field | Value |
|---|---|
| MAC | `10:20:BA:46:1A:0D` |
| Name | `ESP32-S3-GW` |
| UUID | `6E5F0005-B5A3-F393-E0A9-E50E24DCCA9E` |

---

## 3. Live identification baseline (what happened)

### 3.1 Survey run (331 s, 11 LE rounds)

Command:

```bash
python -m bleep survey --duration 330 --round-time 30 --transport le --live \
  -o /tmp/beacon_identification_survey_r2.json
```

Results:

| MAC | Name | Sightings | RSSI avg | Beacon payloads |
|---|---|---|---|---|
| `10:20:BA:46:AE:D5` | ESP32-S3-Beacon | 11/11 | -34 dBm | FEAA UUID; mfg `0xFFFF`=`000100a9c5` |
| `10:20:BA:46:1A:0D` | ESP32-S3-GW | 11/11 | -55 dBm | UUID `6E5F0005-...` only |
| `10:20:BA:46:AE:D6` | — | **0** | — | **Never seen** |

### 3.2 What bleep did / did not do automatically

| Capability | Result |
|---|---|
| RF discovery of beacon MAC | ✓ (as D5) |
| Decode major=1 minor=169 | ✗ (manual hex decode required) |
| Label `ibeacon` protocol | ✗ |
| Decode Eddystone URL | ✗ (FEAA UUID only; no ServiceData snapshot) |
| Flag rotation (`fingerprint_changed`) | ✗ (false across all rounds) |
| Find device given wrong MAC (D6) | ✗ |
| Inline beacon detail in scan output | ✗ |

### 3.3 Proven not at fault

- bleep ≡ BlueZ device enumeration (0 devices dropped in parity test)
- Survey pipeline captures manufacturer/service data for other beacons (e.g. Apple mfg on `46:83:8B:55:44:3F`, Signify on `F0:98:7D:0A:05:07`)
- `adv_dissect.py` correctly decodes standard iBeacon and Eddystone when canonical payloads are present (20/20 unit tests pass)

---

## 4. Gap register

Each gap has a stable ID, problem statement, affected code/docs, planned solution ID, and acceptance reference (§6).

---

### G1 — No beacon-identification discovery workflow

**Problem:** No command to search by OUI, name pattern, iBeacon UUID, Eddystone URL, or manufacturer prefix. Operators must run generic `survey`/`scan` and manually grep JSON. A one-octet MAC typo blocks targeted `-d` scans entirely.

**Affected:**

- `bleep/modes/survey.py` — merges all devices; no beacon filter
- `bleep/cli/` — no `beacon` subcommand
- `bleep/docs/cli_usage.md`, `bleep/docs/survey_mode.md`

**Impact:** High — primary operator pain in beacon identification

**Solution:** S1

---

### G2 — Non-standard iBeacon framing not decoded

**Problem:** Target encodes major/minor/tx in manufacturer ID `0xFFFF` as 5 raw bytes (`000100a9c5`), not Apple `0x004C` + `02 15` + UUID. Dissector only attempts iBeacon for Apple company ID:

```python
# bleep/analysis/adv_dissect.py (lines 246–247)
if cid == COMPANY_ID__APPLE:
    decoded = _decode_ibeacon(raw) or _decode_apple_continuity(raw)
```

**Live result:** `db show` rendered hex only; `summary.protocols` empty.

**Impact:** High — beacon identity not surfaced automatically

**Solution:** S2

---

### G3 — Eddystone UUID advertised without ServiceData decode

**Problem:** Device advertises `0000FEAA-...` in `UUIDs` but `ServiceData` is frequently empty in end-of-round snapshots. Dissector only decodes Eddystone from ServiceData payload bytes (`u16 == "feaa"` with non-empty raw), not from UUID-only adverts.

**Live result:** FEAA visible in UUID list; no `eddystone` protocol label; URL never surfaced.

**Impact:** Medium — partial-phase identification failure

**Solution:** S3

---

### G4 — End-of-round snapshot misses rotating payloads

**Problem:** Survey LE rounds call `passive_scan`, which snapshots `GetManagedObjects()` once at round end. A ~98 s rotator may display format A at snapshot while formats B/C occurred mid-round. LR-2c intra-round tracking exists in `bleep/dbuslayer/signals.py` but `fingerprint_changed` was false for the beacon across 11 rounds.

**Affected:**

- `bleep/modes/survey.py` — `_run_le_round()` → `passive_scan`
- `bleep/ble_ops/le/scan.py` — end-of-scan `get_discovered_devices()`
- `bleep/dbuslayer/signals.py` — `_capture_device_adv_fingerprint()`

**Impact:** High for multi-format rotators

**Solution:** S4

---

### G5 — `DuplicateData` likely inverted in naggy mode

**Problem:** Documentation states naggy forwards every advertisement. Code sets `DuplicateData: False`:

```python
# bleep/ble_ops/le/scan.py (line 994)
_adapter.set_discovery_filter({"DuplicateData": False})
```

BlueZ (`workDir/BlueZDocs/org.bluez.Adapter.5`): **`DuplicateData=true` disables duplicate suppression** and generates `PropertiesChanged` for each ManufacturerData/ServiceData discovery. Current naggy may be *less* chatty than passive, opposite of intent.

**Affected:**

- `bleep/ble_ops/le/scan.py`
- `bleep/docs/ble_scan_modes.md`
- `bleep/modes/debug.py`, `bleep/modes/debug_scan.py`

**Impact:** Medium — reduces rotation capture reliability

**Solution:** S5

---

### G6 — Pokey `--target` uses invalid BlueZ filter key

**Problem:** Pokey sets `Address` in `SetDiscoveryFilter`. BlueZ documents **`Pattern`** (address/name prefix), not `Address`:

```python
# bleep/ble_ops/le/scan.py (lines 1028–1030)
_Adapter().set_discovery_filter({"Address": target_mac.upper()})
```

Reference: `workDir/BlueZDocs/org.bluez.Adapter.rst` — `Pattern` property.

Filter is silently ignored; pokey scans all devices then client-filters.

**Impact:** Medium — wasted controller time; false confidence in targeting

**Solution:** S6

---

### G7 — Scan/survey CLI hides beacon identity

**Problem:** Scan output shows MAC, name, RSSI only. Beacon identity requires `db show --full` or manual JSON parsing. Human `db show` for AE:D5 showed manufacturer hex but no decoded major/minor because `_render_adv_dissection_text()` returns empty when `protocols` is empty.

**Affected:**

- `bleep/ble_ops/le/scan.py` — console output loop
- `bleep/modes/db.py` — `_render_adv_dissection_text()`
- `bleep/modes/survey.py` — live progress lines

**Impact:** High — operator visibility

**Solution:** S7

---

### G8 — AdvertisementMonitor unavailable / inconsistently documented

**Problem:** `python -m bleep advertise-monitor caps` returned empty on validation host (no kernel pattern support). Best path for targeted iBeacon/Eddystone filtering (`workDir/BlueZScripts/example-adv-monitor`) unusable without BlueZ `-E`. Some docs still reference deprecated `bleep monitor` command name.

**Affected:**

- `bleep/modes/monitor.py`, `bleep/dbuslayer/adv_monitor.py`
- `bleep/docs/adv_monitor.md`

**Impact:** Medium — hosts without experimental BlueZ lack kernel offload

**Solution:** S8

---

### G9 — No Android / Google Nearby beacon decoder

**Problem:** Target rotates through an Android-format phase. bleep labels `FCF1` service data as `google_nearby` (`bleep/bt_ref/constants.py`) but performs no structured frame decode.

**Impact:** Medium — incomplete 3-format rotator coverage

**Solution:** S9

---

### G10 — Espressif / vendor UUIDs absent from reference layer

**Problem:** `6E5F0001-...` and `6E5F0005-...` resolve to `name: null` in dissection output. No vendor hint despite Espressif company ID `0x02E5` in SIG tables (`bleep/bt_ref/uuids.py`).

**Impact:** Low — attribution polish

**Solution:** S10

---

## 5. Planned solutions

---

### S1 — `bleep beacon-identification` command (addresses G1)

**Description:** New CLI subcommand dedicated to beacon discovery and identification.

**Interface (proposed):**

```bash
python -m bleep beacon-identification [OPTIONS]

Options:
  --oui PREFIX           Address OUI/prefix (maps to BlueZ Pattern filter)
  --name GLOB            Local-name glob (e.g. '*Beacon*')
  --ibeacon-uuid UUID    Filter decoded iBeacon UUID (canonical or hex)
  --eddystone-url SUBSTR Filter decoded Eddystone URL substring
  --major N              Filter iBeacon major
  --minor N              Filter iBeacon minor
  --duration SECS        Total identification duration (default: 300)
  --round-time SECS      Survey round length (default: 15 for rotators)
  --transport {le}       Transport (default: le)
  --min-rssi DBM         Minimum RSSI threshold
  -o, --output FILE      JSON output path
  --live                 Live progress to stderr
```

**Behaviour:**

1. Apply BlueZ `SetDiscoveryFilter({"Transport": "le", "Pattern": <oui>})` when `--oui` given.
2. Run survey-style rounds (reuse `SurveyCensus` + S4 payload history).
3. Post-filter by beacon signature fields (UUID, major/minor, URL).
4. Score and rank candidates by: protocol match weight + sighting count + RSSI.
5. Emit human table + JSON with decoded beacon fields inline.

**Files to create/modify:**

| File | Change |
|---|---|
| `bleep/modes/beacon_identification.py` | New mode implementation |
| `bleep/cli/parsers/beacon.py` | Argument parser |
| `bleep/cli/dispatch.py` | Register subcommand |
| `bleep/docs/beacon_identification.md` | Operator documentation |
| `tests/test_beacon_identification.py` | Unit + integration tests |

**Dependencies:** S2, S3, S7 (decode + display must work for identification output to be useful)

---

### S2 — Extended iBeacon heuristics (addresses G2)

**Description:** Add fallback decoders in `bleep/analysis/adv_dissect.py` for non-Apple manufacturer data.

**Decoders to add (in priority order):**

| Decoder ID | Trigger | Output |
|---|---|---|
| `ibeacon` (existing) | Apple CID + `02 15` prefix | uuid, major, minor, tx_power |
| `ibeacon` (extended) | Any CID + `02 15` prefix | same fields |
| `ibeacon_compact` | Any CID, exactly 5 bytes | major, minor, tx_power (no uuid) |
| `ibeacon_compact` (Espressif) | CID `0xFFFF` or `0x02E5`, 5 bytes matching major/minor/tx layout | same + vendor hint |

**Protocol label in `summary.protocols`:** include `ibeacon` or `ibeacon_compact`.

**Files to modify:**

| File | Change |
|---|---|
| `bleep/analysis/adv_dissect.py` | New `_decode_ibeacon_compact()`, extended CID logic |
| `tests/test_adv_dissect.py` | Cases for `0xFFFF`/`000100a9c5`, non-Apple full iBeacon |
| `bleep/docs/adv_dissection.md` | Document new decoders |

**Regression fixture:**

```python
dissect_advertisement(manufacturer_data={0xFFFF: bytes.fromhex("000100a9c5")})
# → protocol: ibeacon_compact, major: 1, minor: 169, tx_power: -59
```

---

### S3 — UUID-only Eddystone inference (addresses G3)

**Description:** When `feaa` appears in advertised service UUIDs but ServiceData is empty, emit a pending/inferred label rather than silence.

**Logic:**

```python
if u16 == "feaa" and not raw:
    entry["decoded"] = {"protocol": "eddystone", "frame": "pending", "note": "uuid-advertised; payload not yet captured"}
    protocols.append("eddystone_pending")
```

Survey/beacon-identification merges UUID-only and payload-present states across rounds; transition triggers `fingerprint_changed`.

**Files to modify:**

| File | Change |
|---|---|
| `bleep/analysis/adv_dissect.py` | UUID-list inference in `dissect_advertisement()` |
| `bleep/modes/survey.py` | Track UUID-only → payload transitions |
| `tests/test_adv_dissect.py` | UUID-only FEAA case |

---

### S4 — Beacon-aware survey payload history (addresses G4)

**Description:** Persist per-round payload snapshots for rotators; surface rotation reliably.

**Changes:**

1. Add `--variant {passive,naggy}` to survey (default `passive`; beacon-identification defaults to `naggy`).
2. Extend `DeviceSighting` with `payload_history: List[Dict]` — append `{round, ts, manufacturer_data, service_data}` each round.
3. Audit LR-2c wiring: ensure `fingerprint_rotated_in_round` from `bleep/dbuslayer/adapter_session.py` and `bleep/dbuslayer/signals.py` reaches census merge in all code paths (single-adapter and multi-collector).
4. Recommend `--round-time 15` in beacon-identification docs (≥2 snapshots per 98 s cycle).
5. Output `payload_history` in survey JSON when `--beacon-identification` or `--full-payloads`.

**Files to modify:**

| File | Change |
|---|---|
| `bleep/modes/survey.py` | Variant support, payload history, rotation audit |
| `bleep/cli/parsers/survey.py` | New flags |
| `bleep/docs/survey_mode.md` | Rotator guidance |
| `tests/test_adv_fingerprint_rotation.py` | Extend for survey integration |

---

### S5 — Fix `DuplicateData` in naggy mode (addresses G5)

**Description:** Correct naggy to disable duplicate suppression per BlueZ semantics.

**Change:**

```python
# bleep/ble_ops/le/scan.py — naggy_scan()
_adapter.set_discovery_filter({"DuplicateData": True})  # was False
```

**Documentation corrections:**

| File | Correction |
|---|---|
| `bleep/docs/ble_scan_modes.md` | passive = BlueZ default; naggy = `DuplicateData: true` |
| `bleep/modes/debug.py` | `scann` help text |
| `bleep/docs/changelog.md` | Entry documenting fix |

**Environment probe (optional, S5b):**

Add to `bleep --check-env`:

```
--probe-duplicate-data   Run 30s passive vs naggy; report PropertiesChanged counts
```

---

### S6 — Fix pokey Pattern filter (addresses G6)

**Description:** Replace invalid `Address` key with BlueZ `Pattern`.

**Change:**

```python
# bleep/ble_ops/le/scan.py — pokey_scan()
if target_mac:
    # Use address prefix as Pattern (BlueZ SetDiscoveryFilter)
    pattern = target_mac.upper().replace(":", "")  # or full MAC
    _Adapter().set_discovery_filter({"Pattern": pattern, "Transport": "le"})
```

Fallback: if `SetDiscoveryFilter` rejects `Pattern`, log warning and rely on client-side filter only.

**Documentation:** Update `bleep/docs/ble_scan_modes.md` pokey deep-dive (remove "Address filter" claim).

---

### S7 — Inline beacon detail in scan/db/survey output (addresses G7)

**Description:** Surface decoded beacon fields at discovery time without requiring `--full`.

**Scan output format (proposed):**

```
10:20:BA:46:AE:D5 (ESP32-S3-Beacon) [public] -34 dBm  [ibeacon_compact m=1/i=169 tx=-59] [feaa]
```

**`db show` changes:**

- Always render manufacturer/service hex.
- Apply S2/S3 decoders; show decoded block even when `protocols` was previously empty.
- Add decoded field lines to `_render_adv_dissection_text()` for compact iBeacon and pending Eddystone.

**Survey `--live` additions:**

```
[survey] round 3 | 6 devices | NEW 10:20:BA:46:AE:D5 [ibeacon_compact m=1/i=169] [feaa-pending]
```

**Files to modify:**

| File | Change |
|---|---|
| `bleep/ble_ops/le/scan.py` | `_format_beacon_summary(entry)` helper |
| `bleep/modes/db.py` | Enhanced `_render_adv_dissection_text()` |
| `bleep/modes/survey.py` | Live beacon detail lines |
| `bleep/analysis/adv_dissect.py` | Export `format_beacon_summary()` for reuse |

---

### S8 — AdvertisementMonitor fallback and docs sync (addresses G8)

**Description:** Graceful degradation when kernel pattern matching unavailable.

**Changes:**

1. `bleep beacon-identification --monitor` — try `AdvMonitorManager`; on failure, fall back to software pattern match via `PropertiesChanged` with explicit stderr message.
2. Pattern presets: `--pattern ibeacon` (mfg `4C000215...`), `--pattern eddystone` (svc data `FEAA`).
3. `bleep --check-env` reports AdvertisementMonitor capability.
4. Sync `bleep/docs/adv_monitor.md` — all examples use `bleep advertise-monitor`.

**Files to modify:**

| File | Change |
|---|---|
| `bleep/modes/beacon_identification.py` | Monitor fallback path |
| `bleep/modes/monitor.py` | Pattern presets |
| `bleep/docs/adv_monitor.md` | Command name sync |
| `bleep/docs/check_env.md` | Monitor capability check |

---

### S9 — Google Nearby / Android beacon decoder (addresses G9)

**Description:** Structured decode for `FCF1` and related service-data UUIDs.

**Scope (phase 1):**

- Parse frame type byte and TLV structure from raw payload.
- Label `google_nearby` with sub-frame type in decoded output.
- Register in beacon-identification protocol filter.

**Reference:** `bleep/bt_ref/vendor_adv_specs.py` — Google Nearby manifest hints.

**Files to modify:**

| File | Change |
|---|---|
| `bleep/analysis/adv_dissect.py` | `_decode_google_nearby()` |
| `tests/test_adv_dissect.py` | Nearby frame cases |
| `bleep/docs/adv_dissection.md` | Protocol table update |

---

### S10 — Espressif UUID reference entries (addresses G10)

**Description:** Add observed vendor UUIDs to reference layer.

**Entries:**

| UUID | Label |
|---|---|
| `6E5F0001-B5A3-F393-E0A9-E50E24DCCA9E` | Espressif custom (iBeacon UUID) |
| `6E5F0005-B5A3-F393-E0A9-E50E24DCCA9E` | Espressif custom (gateway service) |

**Files to modify:**

| File | Change |
|---|---|
| `bleep/bt_ref/observed_seed.py` | UUID entries |
| `bleep/docs/adv_dissection.md` | Cross-reference note |

---

## 6. Acceptance criteria

### 6.1 Per-solution acceptance

#### S1 — beacon identification

```bash
python -m bleep beacon-identification --oui 10:20:BA --duration 120 --live
```
- [ ] Lists `10:20:BA:46:AE:D5` with name `ESP32-S3-Beacon`
- [ ] Finds D5 when operator passes wrong MAC `--oui 10:20:BA:46:AE` (D6 never required)
- [ ] JSON output includes decoded beacon fields (not raw hex only)
- [ ] Ranks D5 above GW (`46:1A:0D`) by beacon-evidence score

#### S2 — compact iBeacon decode

```bash
python -m bleep db show 10:20:BA:46:AE:D5
```
- [ ] Shows `Protocols: ibeacon_compact` (or `ibeacon`)
- [ ] Shows `Major: 1  Minor: 169  Tx: -59`
- [ ] Unit test `test_ibeacon_compact_0xffff` passes

#### S3 — Eddystone pending

- [ ] UUID-only FEAA advert labels `eddystone_pending`
- [ ] When ServiceData with URL frame captured, upgrades to `eddystone` with `url: https://espressif.com`
- [ ] UUID-only → payload transition sets `fingerprint_changed: true`

#### S4 — payload history

```bash
python -m bleep survey --duration 300 --round-time 15 --variant naggy \
  --beacon-identification --oui 10:20:BA -o rot.json
```
- [ ] `rot.json` entry for AE:D5 contains `payload_history` with ≥2 entries
- [ ] `fingerprint_changed: true` over 300 s
- [ ] ≥2 distinct protocol labels across history (e.g. `ibeacon_compact` + `eddystone`)

#### S5 — DuplicateData fix

```bash
python -m bleep --check-env --probe-duplicate-data
```
- [ ] Naggy PropertiesChanged count ≥ passive count over 30 s with beacon present

#### S6 — pokey Pattern

```bash
python -m bleep scan --variant pokey --target 10:20:BA:46:AE:D5 --timeout 30
```
- [ ] Output shows only AE:D5 (no unrelated MACs per round)
- [ ] No `Address` key sent to SetDiscoveryFilter (verify via debug log)

#### S7 — inline detail

```bash
python -m bleep scan -d 10:20:BA:46:AE:D5 --timeout 30
```
- [ ] Single-line output includes `[ibeacon_compact m=1/i=169 tx=-59]` and `[feaa]`
- [ ] `db show` (without `--full`) renders decoded block

#### S8 — adv monitor fallback

```bash
python -m bleep --check-env
```
- [ ] Reports AdvertisementMonitor availability
- [ ] `beacon-identification --monitor` degrades gracefully with message when unavailable

#### S9 — Google Nearby decode

- [ ] When Android phase active, `protocols` includes `google_nearby` with decoded structure
- [ ] Unit test with fixture payload passes

#### S10 — Espressif UUID names

```bash
python -m bleep uuid-lookup 6E5F0001-B5A3-F393-E0A9-E50E24DCCA9E
```
- [ ] Returns `Espressif custom (iBeacon UUID)` or equivalent

---

### 6.2 End-to-end acceptance scenario

**Precondition:** Target beacon deployed and advertising at `10:20:BA:46:AE:D5`.

**Command (single operator action, no manual JSON inspection):**

```bash
python -m bleep beacon-identification \
  --oui 10:20:BA \
  --name '*Beacon*' \
  --major 1 --minor 169 \
  --eddystone-url espressif.com \
  --duration 300 \
  --round-time 15 \
  -o beacon_identification_acceptance.json
```

**Pass — all must be true:**

| # | Criterion |
|---|---|
| 1 | Finds `10:20:BA:46:AE:D5` within 120 s |
| 2 | Reports `major=1 minor=169 tx=-59` without manual hex decode |
| 3 | Reports Eddystone phase (`eddystone` with URL or `eddystone_pending`) |
| 4 | Sets `fingerprint_changed: true` over 300 s |
| 5 | RSSI reported; beacon ranked first by proximity/beacon score |
| 6 | Succeeds when documentation MAC is wrong (`AE:D6`) — OUI search still finds `AE:D5` |
| 7 | No bleep source modifications required by operator beyond running the command |
| 8 | Output JSON validates against documented schema (§7) |

**Fail — any of:**

- Beacon not found in 300 s while `btmon` or `get-managed-objects` shows it
- bleep drops device present in BlueZ parity test
- Decoded major/minor wrong vs known deployment values
- Regression: existing `tests/test_adv_dissect.py` cases fail

---

## 7. Output schema (beacon identification JSON)

```json
{
  "identification": {
    "duration_s": 300,
    "round_time_s": 15,
    "filters": {"oui": "10:20:BA", "major": 1, "minor": 169},
    "started_at": "ISO-8601",
    "completed_at": "ISO-8601"
  },
  "candidates": [
    {
      "address": "10:20:BA:46:AE:D5",
      "name": "ESP32-S3-Beacon",
      "score": 95,
      "sightings": 20,
      "rssi_avg": -34,
      "rssi_min": -36,
      "rssi_max": -32,
      "protocols": ["ibeacon_compact", "eddystone_pending"],
      "ibeacon": {"major": 1, "minor": 169, "tx_power": -59, "uuid": null},
      "eddystone": {"frame": "pending", "url": null},
      "fingerprint_changed": true,
      "payload_history": [
        {"round": 1, "ts": "ISO-8601", "manufacturer_data": {"65535": "000100a9c5"}, "service_data": {}},
        {"round": 5, "ts": "ISO-8601", "manufacturer_data": {}, "service_data": {"0000feaa-...": "10..."}}
      ],
      "first_seen": "ISO-8601",
      "last_seen": "ISO-8601"
    }
  ]
}
```

---

## 8. Implementation priority and phasing

### Phase 1 — Operator unblock (P0)

| Item | Gap | Solution | Est. effort |
|---|---|---|---|
| Compact iBeacon decode | G2 | S2 | 0.5 day |
| Inline beacon detail | G7 | S7 | 0.5 day |
| Beacon identification command (MVP) | G1 | S1 | 1–2 days |

**Phase 1 exit:** End-to-end acceptance §6.2 passes except rotation history (Phase 2).

### Phase 2 — Rotator reliability (P1)

| Item | Gap | Solution | Est. effort |
|---|---|---|---|
| DuplicateData fix | G5 | S5 | 0.25 day |
| Pokey Pattern fix | G6 | S6 | 0.25 day |
| UUID-only Eddystone | G3 | S3 | 0.5 day |
| Payload history + rotation audit | G4 | S4 | 1–2 days |

**Phase 2 exit:** `fingerprint_changed: true` and `payload_history` in acceptance output.

### Phase 3 — Completeness (P2)

| Item | Gap | Solution | Est. effort |
|---|---|---|---|
| Adv monitor fallback | G8 | S8 | 1 day |
| Google Nearby decoder | G9 | S9 | 1–2 days |
| Espressif UUID names | G10 | S10 | 0.25 day |

---

## 9. Non-goals (out of scope)

- RSSI triangulation / physical beacon-identification mapping UI
- Modifications to BlueZ or kernel Bluetooth stack
- Connection/GATT-based beacon interaction
- Automated MAC address correction (operator must validate deployment docs)
- Support for Bluetooth Mesh beacons (`bleep/bt_ref/mesh_ids.py` — separate domain)

---

## 10. Risk register

| Risk | Mitigation |
|---|---|
| Heuristic iBeacon decode false-positives on random 5-byte mfg data | Require CID allowlist (`0xFFFF`, `0x02E5`) or confidence flag in output |
| DuplicateData default varies by BlueZ version (.rst says false, .5 says true) | Runtime probe (S5b); document observed behaviour |
| Pattern filter merged OR-style across BlueZ clients | Client-side re-validation per BlueZ docs |
| AdvertisementMonitor never available on target deployment hardware | Software fallback path (S8) |
| Rotation faster than round-time | Document minimum `--round-time`; adaptive round-time in survey |

---

## 11. References

| Resource | Path |
|---|---|
| Advertisement dissection design | `bleep/docs/adv_dissection.md` |
| Survey mode | `bleep/docs/survey_mode.md` |
| BLE scan variants | `bleep/docs/ble_scan_modes.md` |
| Adv monitor | `bleep/docs/adv_monitor.md` |
| BlueZ Device1 properties | `workDir/BlueZDocs/org.bluez.Device.rst` |
| BlueZ SetDiscoveryFilter | `workDir/BlueZDocs/org.bluez.Adapter.rst` |
| BlueZ adv monitor example | `workDir/BlueZScripts/example-adv-monitor` |
| BlueZ discovery example | `workDir/BlueZScripts/test-discovery` |
| Dissector implementation | `bleep/analysis/adv_dissect.py` |
| Survey implementation | `bleep/modes/survey.py` |
| Scan implementation | `bleep/ble_ops/le/scan.py` |
| Live identification artifacts | `/tmp/beacon_identification_survey_r2.json` |

---

## 12. Review and acceptance sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Author | | | |
| Technical reviewer | | | |
| Acceptance authority | | | |

**Decision options:** Approved / Approved with changes / Deferred / Rejected

**Change requests:**

```
(Reviewer notes here)
```

---

*Document version: 1.0 — generated from live beacon-identification validation against `10:20:BA:46:AE:D5` (2026-08-12).*
