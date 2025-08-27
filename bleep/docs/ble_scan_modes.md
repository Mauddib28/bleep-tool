# BLE Scan Variants in **BLEEP**

BLEEP offers four discovery-scan presets that balance radio footprint versus information gain. All are implemented in `bleep.ble_ops.scan` and available through:

```bash
python -m bleep.cli scan --variant <passive|naggy|pokey|brute> [--timeout 15] [--target AA:BB:CC:DD:EE:FF]
```

| Variant | Behaviour | When to use |
|---------|-----------|-------------|
| **passive** (default) | Standard LE discovery (`DuplicateData=True`). One *InterfacesAdded* signal per device per session. | Quiet landscape sweep. |
| **naggy** | Same filter but `DuplicateData=False` → every advertisement forwarded. | Collect RSSI graph, see peri-connection adverts. |
| **pokey** | Repeats 1-second **naggy** scans for *N* seconds. Requires `--target <MAC>` to hammer one address. | Force a *specific* device to emit transient adverts (privacy MACs, button-press beacons). |
| **brute** | Two-phase: BR/EDR inquiry (half timeout) + naggy LE (half timeout). | Maximum coverage, noisy. |

### Pokey deep-dive
BlueZ only delivers discovery results after `StopDiscovery()`. A single long scan therefore yields one update per MAC.  Pokey mode repeatedly stops/starts discovery (1 s each) so BlueZ flushes its cache many times per minute – effectively *poking* devices.  With `--target` BLEEP installs an `Address` filter first so controller time is spent solely on the chosen beacon.

---

Run `python -m bleep.modes.debug` and use commands:
* `scan`   → passive
* `scann`  → naggy
* `scanp <MAC>` → pokey
* `scanb`  → brute

for interactive tests.

*Last updated: 2025-07-21* 

---

## Enumeration variants (_enum / enumn / enump / enumb_)

Discovery finds devices; **enumeration** digs into a single target’s GATT
database. Four presets mirror the discovery spectrum:

| Command (debug-shell) | Behaviour | Writes? | Typical duration |
|-----------------------|-----------|---------|------------------|
| `enum  <MAC>`        | One-shot read of every readable characteristic. | ❌ | 3-10 s |
| `enumn <MAC>`        | Same read pass **3×** → spot transient changes. | ❌ | 9-30 s |
| `enump <MAC> [-r N]` | After each read pass sends **0x00 / 0x01** to every writable characteristic (skips descriptors). | ⚠️ Light | 5-60 s |
| `enumb <MAC> <CHAR|all>` | Fuzz **one** characteristic (or **all writable** when the literal `all` is passed) – payloads built with `--range`, `--patterns`, or `--payload-file`. | ⚠️ Heavy | Depends on payload set |

### Safety flags

• `--verify` – re-reads after each write and logs mismatches.

• `--force`  – bypasses ROE (rules-of-engagement) checks; by default *brute* honours landmine / permission maps and refuses risky writes.

### CLI examples

```bash
# Passive enumeration (read-only)
python -m bleep.modes.debug -d    # detailed mode
BLEEP-DEBUG> enum AA:BB:CC:DD:EE:FF

# Naggy enumeration with mapping diff
BLEEP-DEBUG> enumn AA:BB:CC:DD:EE:FF

# Pokey: two rounds, verify writes
BLEEP-DEBUG> enump AA:BB:CC:DD:EE:FF --rounds 2 --verify

# Bruteforce 0x00-0x0F range, ASCII pattern, custom file payload
# Bruteforce **all writable characteristics** with default single-byte payload set
BLEEP-DEBUG> enumb AA:BB:CC:DD:EE:FF all --verify
BLEEP-DEBUG> enumb AA:BB:CC:DD:EE:FF 00002a37-... \
             --range 0x00-0x0F \
             --patterns ascii \
             --payload-file fuzz.bin --force --verify
```

Allowed pattern keywords now include:
• ascii – printable ASCII bytes
• inc   – incrementing length‐prefixed byte strings
• alt   – single 0xAA / 0x55 bytes
• repeat:<byte>:<len> – repeat byte value *len* times  (e.g. repeat:ff:4)
• hex:<deadbeef>      – arbitrary hex string converted to raw bytes

Logs are written to `LOG__ENUM` for post-analysis (diffs, errors, landmine hits).

*Last updated: 2025-07-24* 