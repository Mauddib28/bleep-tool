## Beacon Identification

Discover and rank rotating BLE beacons by OUI, name glob, and decoded iBeacon/Eddystone fields.

```bash
# Classic non-connectable beacon (often name=None) — omit --name
python -m bleep beacon-identification \
  --oui 10:20:BA \
  --major 1 --minor 169 \
  --duration 120 --round-time 15 \
  --min-rssi -75 \
  --live \
  -o beacon_identification.json

# Named / WIN_POC-style targets may add a name glob
python -m bleep beacon-identification \
  --oui 10:20:BA \
  --name '*Beacon*' \
  --major 1 --minor 169 \
  --duration 120 --round-time 15

# Filter by decoded payload instead of address/name
python -m bleep beacon-identification \
  --ibeacon-uuid E2C56DB5-DFFB-48D2-B060-D0F5A71096E0 \
  --duration 60 --round-time 10 --quiet

python -m bleep beacon-identification \
  --eddystone-url 'example.com' \
  --transport le --duration 60
```

### Flags

All filters are applied **client-side** after the survey rounds complete (against
the merged `SurveyCensus`); every flag is optional. A candidate that fails any
*provided* filter is dropped outright — filters are hard gates, and the score
(below) only ranks the survivors.

| Flag | Default | Description |
|------|---------|-------------|
| `--oui <prefix>` | — | Address OUI/prefix filter (e.g. `10:20:BA`) |
| `--name <glob>` | — | Local-name glob filter (e.g. `'*Beacon*'`); omit for nameless beacons |
| `--ibeacon-uuid <uuid>` | — | Filter on the decoded iBeacon proximity UUID |
| `--eddystone-url <substr>` | — | Filter on a decoded Eddystone-URL substring |
| `--major <n>` | — | Filter iBeacon major |
| `--minor <n>` | — | Filter iBeacon minor |
| `--duration <s>` | 300 | Total identification duration in seconds |
| `--round-time <s>` | 15 | Length of each survey round in seconds |
| `--transport {le}` | `le` | Transport (LE only; BR/EDR beacons are still harvested via the LE round census) |
| `--min-rssi <dBm>` | — | Drop candidates weaker than this RSSI |
| `-o`, `--output <path>` | stdout | Write the JSON report to a file |
| `--live` | off | Stream live progress to stderr |
| `--quiet` | off | Suppress the human-readable candidate table |

This command is a thin wrapper over the survey LE round loop and `SurveyCensus`. It post-filters and scores candidates; it does not invent a second discovery engine.

Discovery harvest uses **R1/R2** (`DeviceManager` pre-`StopDiscovery` snapshot +
session census) so unpaired non-connectable beacons survive BlueZ
`STOP_CLEARS`. Each round is a **passive LE scan** — `beacon-identification`
calls `survey._run_le_round(..., quiet=True)` with no scan variant, so there is
**no `--variant` flag**. When payload rotation matters, widen coverage with a
longer `--duration` (more rounds) and a lower `--min-rssi` rather than switching
scan modes. Do **not** require `--name` for classic beacons that advertise
without a local name.

### Candidate scoring & ranking

Each surviving candidate gets a **deterministic** integer score
(`score_candidate()` in `bleep/modes/beacon_identification.py`):

| Signal | Weight |
|--------|--------|
| `--oui` supplied and address prefix matches | +20 |
| `--name` glob supplied and local name matches | +25 |
| Decoded iBeacon evidence — `--major`/`--minor` supplied **and** both match, **or** neither supplied (any decoded iBeacon/`ibeacon_compact`) | +40 |
| iBeacon proximity-UUID match | +0 (folded into the iBeacon evidence weight) |
| Eddystone frame pending (`eddystone_pending`) | +5 |
| Eddystone URL decoded (and, if `--eddystone-url` given, substring matches) | +15 |
| Sighting frequency — `round(10 × sightings ÷ max_sightings)` | 0…+10 |
| RSSI bucket — `≥ -50 → +10`, `≥ -65 → +7`, `≥ -80 → +4`, else `+1` | +1…+10 |

Candidates are sorted by **score desc → mean RSSI desc → sightings desc →
address asc**. The human table (suppressed by `--quiet`) prints the top 20.

### Output JSON

Written to `--output` (or stdout). `null` fields are omitted from each candidate.

```json
{
  "identification": {
    "duration_s": 300,
    "round_time_s": 15,
    "filters": {"oui": "10:20:BA", "major": 1, "minor": 169},
    "started_at": "<ISO-8601 UTC>",
    "completed_at": "<ISO-8601 UTC>"
  },
  "candidates": [
    {
      "address": "10:20:BA:46:AE:D5",
      "name": "ESP32-S3-Beacon",
      "score": 95,
      "sightings": 20,
      "rssi_avg": -34, "rssi_min": -36, "rssi_max": -32,
      "protocols": ["ibeacon_compact", "eddystone_pending"],
      "ibeacon": {"major": 1, "minor": 169, "tx_power": -59, "uuid": null},
      "eddystone": {"frame": "pending", "url": null, "confidence": "low"},
      "fingerprint_changed": true,
      "payload_history": [ {"round": 1, "ts": "<ISO-8601>", "manufacturer_data": {"65535": "000100a9c5"}, "service_data": {}} ],
      "first_seen": "<ISO-8601 UTC>",
      "last_seen": "<ISO-8601 UTC>"
    }
  ]
}
```

### Decoded beacon labels

Beacon fields come from the shared dissector, not a beacon-specific parser. The
labels you will see in `protocols[]` / the `[…]` summary tags are:

- `ibeacon` — canonical Apple (or any-CID) `02 15` framing (`uuid`, `major`, `minor`, `tx_power`).
- `ibeacon_compact` — vendor `0xFFFF` 5-byte framing (`major`, `minor`, `tx_power`; no UUID) used by ESP32-class beacons.
- `eddystone` — decoded `FEAA` ServiceData frame (UID / URL / TLM / EID).
- `eddystone_pending` — `FEAA` advertised as a service UUID but its payload not yet captured; upgrades to `eddystone` on the round the payload appears.

Full decoder semantics and triggers are documented in
[Advertisement dissection](adv_dissection.md#protocol-decoders).

### Limitations & non-goals

- **LE only.** `--transport` accepts only `le`; BR/EDR beacons are still harvested via the LE round census but there is no dedicated BR/EDR beacon path.
- **No `--variant` / scan-mode switching.** Rounds are passive; widen coverage with a longer `--duration` and lower `--min-rssi`, not scan modes.
- **Vendor UUID attribution is best-effort.** Custom Espressif UUIDs (`6E5F0001-…` / `6E5F0005-…`) are not seeded in `bt_ref/observed_seed.py`, so they resolve to `name: null`; add them to the [custom UUID overlay](uuid_translation.md) if attribution matters.
- **No triangulation, no GATT interaction, no automatic MAC correction** — beacon identification is discovery/observation only. Use the OUI/name/decoded-field filters to locate a device even when a documented MAC is wrong.

The original planning/gap-analysis record (gap register G1–G10, per-solution
acceptance criteria, and risk register) is archived inside the package at
[`archive/beacon_identification_plan.md`](archive/beacon_identification_plan.md).

---

*Last updated: 2026-09-13 (containment pass: internalized the scoring model, output-JSON schema, decoded-label reference, and limitations/non-goals from the code; removed the external repo-root `BEACON_IDENTIFICATION_PLAN.md` pointer in favour of the in-package `archive/beacon_identification_plan.md` and `adv_dissection.md` cross-references).*
