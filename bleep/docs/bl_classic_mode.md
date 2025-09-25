---
description: User-level guide for Bluetooth Classic features (scan, SDP enumeration, PBAP) in BLEEP
---

# Bluetooth Classic Support in **BLEEP**

BLEEP started as a Bluetooth Low Energy (BLE) toolkit.  Since v0.6 the same
modular infrastructure also covers **Bluetooth Classic / BR-EDR** operations.
This document explains prerequisites, commands, typical flows, logging, and
troubleshooting for Classic devices.

> The Classic helpers live next to the BLE ones – no special install step is
> required once BLEEP is installed in *editable* mode (`pip install -e .`).

---

## 1  Requirements

* BlueZ ≥ 5.55 (tested 5.66)
* `bluetooth-obexd` service **enabled & running** – required for PBAP transfer
* Adapter must be powered, discoverable / pairable as usual (`bluetoothctl`)
* The target phone/head-unit **paired & trusted** – PBAP typically rejects
  anonymous connections.

```bash
# enable obexd (Ubuntu / Debian)
sudo systemctl enable --now bluetooth-obexd.service
```

---

## 2  Command reference

| Command | Purpose |
|---------|---------|
| `classic-scan` | BR/EDR inquiry scan – lists nearby Classic devices |
| `classic-enum <MAC>` | SDP browse + records; prints RFCOMM services table |
| `classic-pbap <MAC> --out <file.vcf>` | Pull full phone-book (VCF) via PBAP |

All commands share global CLI flags such as `--hci <index>` and logging level.
Run `python -m bleep.cli --help` for details.

### 2.1  Scan example
```bash
# Simple
python -m bleep.cli classic-scan

# With discovery filters (BlueZ ≥5.55)
python -m bleep.cli classic-scan --uuid 112f,110b --rssi -65 --timeout 8
#  └─ only show devices advertising **PBAP (0x112f)** or **A2DP (0x110b)** and stronger than –65 dBm
# Path-loss filter (BlueZ ≥5.59)
python -m bleep.cli classic-scan --pathloss 70 --timeout 6
# With debug output
python -m bleep.cli classic-scan --debug
```
Output columns: MAC | Name | RSSI | Class | Flags (Paired/Trusted…).

### 2.2  Service enumeration example
```bash
python -m bleep.cli classic-enum 14:89:FD:31:8A:7E
```
Typical output
```
Service                    UUID          RFCOMM
-----------------------------------------------
Serial Port                1101              16
Headset AG                 1112               3
Hands-Free AG              111f               4
PBAP-PSE                   112f              18   <-- phone-book channel
```

BLEEP first runs `sdptool browse --tree` (fast).  If a PBAP entry is missing or
no RFCOMM channels appear it automatically falls back to `sdptool records`.

**Where do the UUIDs come from?**  Use the 16-bit or 128-bit Service Class UUID
advertised by the remote device (shown in the *Output* column of `classic-enum`)
or consult the SIG Assigned Numbers list.  BLEEP bundles a YAML copy under
`References/service_uuids.yaml`; the raw text is shipped in
`workDir/BlueZDocs/assigned-numbers.txt` for quick lookup.

Example: PBAP-PSE advertises Service Class UUID `0x112f` → pass `--uuid 112f`.

### 2.3  Phone-book dump
```bash
python -m bleep.cli classic-pbap 14:89:FD:31:8A:7E --out /tmp/phone.vcf
# If the phone shows an authorisation prompt use --auto-auth to register a
# temporary OBEX agent that auto-accepts:
python -m bleep.cli classic-pbap 14:89:FD:31:8A:7E --out /tmp/phone.vcf --auto-auth
```
Flow:
1. Create `org.bluez.obex.Client1` session with Target =`"PBAP"`.
2. `Select("int", "pb")` (ignored if phone does not implement it).
3. `PullAll("", {"Format":"vcard21"})` – BlueZ stores file in `$XDG_CACHE_HOME`.
4. On `Transfer1` *complete* event the file is moved to `--out` path.

If the D-Bus path fails (service not running / permissions) a descriptive error
is raised.  Check log files below.

### 2.4  Reachability test (l2ping)
```bash
python -m bleep.cli classic-ping 14:89:FD:31:8A:7E --count 5
# → prints average RTT or error if device not reachable
# (may need sudo on some distros because *l2ping* requires CAP_NET_RAW)
```

---

## 3  Logging

BLEEP writes per-category logs to `/tmp` (overwritten each run):

| File suffix | What it contains |
|-------------|------------------|
| `__logging__general.txt` | High-level progress lines |
| `__logging__debug.txt`   | Retry loops, D-Bus method names, SDP raw output |
| `__logging__enumeration.txt` | Parsed SDP records table |
| `__logging__usermode.txt`| RFCOMM connect attempts |

Enable verbose CLI flag `-v` to mirror *general* log on stdout.

---

## 4  Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `obexd PBAP path failed – will try RFCOMM fallback` | `bluetooth-obexd` not running OR phone requires bonding | `sudo systemctl start bluetooth-obexd`; make sure phone is paired & trusted |
| `PBAP service not found on device (no RFCOMM channel)` | Phone hides PBAP until authenticated OR SDP cache stale | Pair first; run `classic-enum` again; power-cycle phone |
| `BlueZ obexd PBAP transfer failed; see logs for details` | Transfer aborted by remote, wrong repository selected | Check `/tmp/...debug.txt`; some feature phones only expose `int/pb.vcf` after `Select` – already handled; open an issue if persists |
| `Failed to connect … Operation timed out` | Device busy or radio glitch | Retry; Classic connect uses 5×2 s back-off |
| `org.freedesktop.DBus.Error.NoReply` or `Timed out waiting for response` during PBAP | Bluetooth controller stuck in half-open BR/EDR connection (BlueZ bug) | In `bluetoothctl` type `disconnect <MAC>` for the target device, wait 2-3 s, then re-run the command.  Power-cycling the phone is a second fallback. |

---

## 5  Limitations / roadmap

* Only **PBAP-PSE** is implemented.  Other OBEX profiles (MAP, SYNC) pending.
* No automatic OBEX-AUTH support; relies on BlueZ trust settings.
* Debug-mode lacks a `pbap` command (planned under task **bc-10**).
* Integration tests for Classic flows (task **bc-12**) still to be written.

---

*Last updated: 2025-07-18* 

---

## 6  Temporary Classic-Feature TODO Tracker  
*(will be removed once every item is ✅ completed)*

| ID | Task | Status |
|----|------|--------|
| bc-01 | Research BlueZ D-Bus APIs for Classic (discovery, SDP, RFCOMM, PBAP) | ⏱️ pending |
| bc-02 | Design high-level Classic API surface mirroring BLE helpers | ✅ completed |
| bc-03 | Implement `dbuslayer.device_classic` wrapper | ✅ completed |
| bc-04 | Create SDP service-discovery helper (`classic_sdp.py`) | ✅ completed |
| bc-05 | Parse RFCOMM channels from SDP records | ✅ completed |
| bc-06 | Extend `classic_connect_and_enumerate()` to return service→channel map | ✅ completed |
| bc-07 | PBAP phone-book dump helper via BlueZ OBEX D-Bus | ✅ completed |
| bc-08 | Add `br_ops` equivalents (`classic_scan`, `classic_connect_and_enumerate`) | ✅ completed |
| bc-09 | Add CLI sub-commands `classic-scan` & `classic-enum` | ✅ completed |
| bc-10 | Debug-mode interactive support for Classic devices | ⏱️ pending |
| bc-11 | Write documentation for Classic mode & update README TOC | ✅ completed |
| bc-12 | Integration tests for Classic flow incl. PBAP | ⏱️ pending |
| bc-13 | Update CHANGELOG / todo_tracker after full feature set | ✅ completed |

Legend: ⏱️ pending 🔄 in-progress ✅ completed 

---

## 7  Feature Tracker

| Feature | Status |
|---------|--------|
| Classic discovery (`cscan`) | ✅ |
| BLE scan presets (shared CLI `bleep scan --variant`) | ✅ |
| RFCOMM enumeration (`cservices`) | ✅ | 