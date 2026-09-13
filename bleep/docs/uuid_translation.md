# UUID Translation Functionality

## Overview

BLEEP provides comprehensive UUID translation functionality that allows users to quickly translate UUIDs (16-bit, 32-bit, or 128-bit) into human-readable formats based on BLEEP's internal UUID databases.

## Features

- **Multiple UUID Format Support**: Handles 16-bit, 32-bit, and 128-bit UUIDs
- **Comprehensive Database Search**: Searches across all BLEEP UUID databases:
  - Services (SPEC_UUID_NAMES__SERV)
  - Characteristics (SPEC_UUID_NAMES__CHAR)
  - Descriptors (SPEC_UUID_NAMES__DESC)
  - Members (SPEC_UUID_NAMES__MEMB)
  - SDOs (SPEC_UUID_NAMES__SDO)
  - Service Classes (SPEC_UUID_NAMES__SERV_CLASS)
  - Custom UUIDs (constants.UUID_NAMES)
- **16-bit UUID Expansion**: Automatically finds all matches for 16-bit UUIDs
- **Flexible Input Formats**: Accepts UUIDs with or without dashes, case-insensitive
- **Multiple Output Formats**: Human-readable text or JSON

## Usage

### CLI Command

The primary way to use UUID translation is through the `uuid-translate` command:

```bash
# Single UUID (16-bit)
bleep uuid-translate 180a

# Single UUID (128-bit)
bleep uuid-translate 0000180a-0000-1000-8000-00805f9b34fb

# Multiple UUIDs
bleep uuid-translate 180a 2a00 2a01

# JSON output
bleep uuid-translate 180a --json

# Verbose mode (shows source databases)
bleep uuid-translate 180a --verbose
```

**Aliases**: The command can also be invoked as `uuid-lookup`:

```bash
bleep uuid-lookup 180a
```

### Interactive Mode

In BLEEP's interactive mode, use the `uuid` command:

```
BLEEP> uuid 180a
BLEEP> uuid 0000180a-0000-1000-8000-00805f9b34fb
BLEEP> uuid 180a 2a00 2a01
```

### User Mode

In BLEEP's user-friendly menu mode, select option "5" (Translate UUID) from the main menu.

## Input Formats

The UUID translator accepts UUIDs in various formats:

- **16-bit**: `180a`, `0x180a`, `0x180A`
- **32-bit**: `0000180a`
- **128-bit**: `0000180a-0000-1000-8000-00805f9b34fb` (with dashes)
- **128-bit**: `0000180a00001000800000805f9b34fb` (without dashes)

All formats are case-insensitive.

## Output Format

### Text Output

```
UUID Translation Results
==================================================
Input UUID: 180a
Format: 16-bit
Canonical 128-bit: 0000180a-0000-1000-8000-00805f9b34fb
16-bit form: 180a
BT SIG Format: Yes

Matches Found: 1

[Service]
  0000180a-0000-1000-8000-00805f9b34fb: Device Information
```

### JSON Output

```json
{
  "input_uuid": "180a",
  "normalized_uuid": "0000180a00001000800000805f9b34fb",
  "uuid_format": "16-bit",
  "short_form": "180a",
  "matches": [
    {
      "category": "Service",
      "uuid": "0000180a00001000800000805f9b34fb",
      "name": "Device Information",
      "source": "Service"
    }
  ],
  "match_count": 1,
  "is_bt_sig_format": true
}
```

## Examples

### Example 1: 16-bit Service UUID

```bash
$ bleep uuid-translate 180a

UUID Translation Results
==================================================
Input UUID: 180a
Format: 16-bit
Canonical 128-bit: 0000180a-0000-1000-8000-00805f9b34fb
16-bit form: 180a
BT SIG Format: Yes

Matches Found: 1

[Service]
  0000180a-0000-1000-8000-00805f9b34fb: Device Information
```

### Example 2: 16-bit Characteristic UUID

```bash
$ bleep uuid-translate 2a00

UUID Translation Results
==================================================
Input UUID: 2a00
Format: 16-bit
Canonical 128-bit: 00002a00-0000-1000-8000-00805f9b34fb
16-bit form: 2a00
BT SIG Format: Yes

Matches Found: 1

[Characteristic]
  00002a00-0000-1000-8000-00805f9b34fb: Device Name
```

### Example 3: Multiple UUIDs

```bash
$ bleep uuid-translate 180a 2a00 2a01

UUID Translation Results
==================================================
Input UUID: 180a
Format: 16-bit
Canonical 128-bit: 0000180a-0000-1000-8000-00805f9b34fb
16-bit form: 180a
BT SIG Format: Yes

Matches Found: 1

[Service]
  0000180a-0000-1000-8000-00805f9b34fb: Device Information

--------------------------------------------------

UUID Translation Results
==================================================
Input UUID: 2a00
Format: 16-bit
Canonical 128-bit: 00002a00-0000-1000-8000-00805f9b34fb
16-bit form: 2a00
BT SIG Format: Yes

Matches Found: 1

[Characteristic]
  00002a00-0000-1000-8000-00805f9b34fb: Device Name

--------------------------------------------------

UUID Translation Results
==================================================
Input UUID: 2a01
Format: 16-bit
Canonical 128-bit: 00002a01-0000-1000-8000-00805f9b34fb
16-bit form: 2a01
BT SIG Format: Yes

Matches Found: 1

[Characteristic]
  00002a01-0000-1000-8000-00805f9b34fb: Appearance
```

### Example 4: Custom 128-bit UUID

```bash
$ bleep uuid-translate e95d93b0-251d-470a-a062-fa1922dfa9a8

UUID Translation Results
==================================================
Input UUID: e95d93b0-251d-470a-a062-fa1922dfa9a8
Format: 128-bit
Canonical 128-bit: e95d93b0251d470aa062fa1922dfa9a8
BT SIG Format: No

Matches Found: 1

[Custom]
  e95d93b0251d470aa062fa1922dfa9a8: DFU Control Service
```

## Programmatic Usage

The UUID translator can also be used programmatically:

```python
from bleep.bt_ref.uuid_translator import translate_uuid

# Translate a UUID
result = translate_uuid("180a")

# Access results
print(f"Format: {result['uuid_format']}")
print(f"Matches: {result['match_count']}")
for match in result['matches']:
    print(f"  {match['category']}: {match['name']}")
```

### Display-only convenience: `get_uuid_name`

For display code that only needs a single friendly name (not the full match
structure), use `get_uuid_name()`. It is a thin wrapper over `translate_uuid()`
that returns the best (highest-priority) match name, or a caller-supplied
`default` (empty string by default) when nothing matches — letting callers branch
on a falsy result:

```python
from bleep.bt_ref.uuid_translator import get_uuid_name

get_uuid_name("0x110E")   # -> "A/V Remote Control"  (16-bit short form)
get_uuid_name("180a")     # -> "Device Information Service"
get_uuid_name("00001800-0000-1000-8000-00805F9B34FB")  # -> "GAP"
get_uuid_name("ffffffff") # -> ""  (unknown → default)
get_uuid_name("bad", default="?")  # -> "?"
```

Because it delegates to `translate_uuid()`, it normalizes 16/32/128-bit input in
any case, dashed or not. This is the resolver used by the Classic (BR/EDR)
enumeration output (`classic-enum`, debug `csdp`/`cservices`) to name SDP records
that lack an explicit SDP Service Name — including the common short-form service
UUIDs (`0x110E`, `0x1116`, `0x112F`, …) emitted by `sdptool`.

> **Note on `get_name_from_uuid()`:** the older
> `bleep.bt_ref.utils.get_name_from_uuid()` performs **exact-string** matching
> only (no short↔long normalization) and returns the sentinel string
> `"Unknown"`. Prefer `get_uuid_name()` for any path that may receive short-form
> or mixed-case UUIDs.

### Resolution tiers of `get_name_from_uuid()`

`get_name_from_uuid(uuid, uuid_class=None, *, allow_observed=False)` consults, in
order:

1. **Custom** — `constants.UUID_NAMES` (includes operator promotions, see below).
2. **SIG GATT** — service / characteristic / descriptor / member / SDO /
   service-class tables (`bt_ref/uuids.py`).
3. **SIG Mesh** — mesh model UUIDs (`bt_ref/mesh_ids.py`, generated from SIG
   `mesh/mesh_model_uuids.yaml`). 16-bit model IDs live below the GATT ranges so
   they cannot collide with the tables above.
4. **Observed (opt-in only)** — when `allow_observed=True` and every
   authoritative tier misses, the observed-UUID catalogue is consulted and a
   `"Unknown (seen as: <names>)"` hint is returned. Default (`False`) preserves
   the historical `"Unknown"` output, so no default caller changes behaviour.
   This tier is *never* authoritative and never pollutes tiers 1–3.

### Observed-UUID catalogue ("seen in the wild")

`bleep.core.observations.get_observed_uuid_catalogue(limit=None, uuid=None)`
aggregates every UUID observed on real devices (LE services / characteristics /
descriptors + Classic services + SDP records), canonicalised to 128-bit so short
and long forms of the same logical UUID merge, into
`{uuid, names, count, sources, first_seen, last_seen, sample_macs}` (most-observed
first). Surface it with `bleep db uuids [--uuid <UUID>]`.

### Promoting an observed UUID

`bleep db uuids --uuid <UUID> --promote "<Name>"` (or
`bleep.bt_ref.custom_uuids.promote_uuid(uuid, name)`) folds a vendor/proprietary
UUID into the authoritative **custom** tier. Promotions persist to a JSON overlay
(`~/.bleep/custom_uuids.json`, override with `BLEEP_CUSTOM_UUIDS`) that
`constants.UUID_NAMES` merges at import — self-contained and reversible (delete
the entry/file to undo).

## Architecture

The UUID translation system is designed with modularity and extensibility in mind:

- **Format Handlers**: Pluggable system for handling different UUID formats
- **Database Abstraction**: Unified interface to all UUID databases
- **Easy Extension**: Simple to add support for new UUID formats or databases

### Adding Custom Format Handlers

To add support for non-standard UUID formats, create a custom handler:

```python
from bleep.bt_ref.uuid_translator import UUIDFormatHandler, UUIDFormat

class CustomFormatHandler(UUIDFormatHandler):
    def can_handle(self, uuid_input: str) -> bool:
        # Check if this handler can process the UUID
        return uuid_input.startswith("custom:")
    
    def normalize(self, uuid_input: str):
        # Normalize the UUID
        # Return (normalized_uuid, uuid_format, short_form)
        pass
    
    def expand_short(self, short_uuid: str) -> str:
        # Expand short UUID to full format
        pass

# Register the handler
from bleep.bt_ref.uuid_translator import get_translator
translator = get_translator()
translator.register_format_handler(CustomFormatHandler())
```

## Troubleshooting

### No Matches Found

If no matches are found for a UUID, it may be:
- A custom/vendor-specific UUID not in the standard databases
- A malformed UUID (check the input format)
- A UUID from a newer Bluetooth specification (update BLEEP's UUID databases)

### Invalid UUID Format

If you receive an "Invalid UUID format" error:
- Ensure the UUID contains only hexadecimal characters
- Check that the length matches the expected format (4, 8, or 32 hex digits)
- Remove any non-hexadecimal characters

## Related Documentation

- [UUID Translation Plan](archive/uuid_translation_plan.md) - Detailed implementation plan
- [BLEEP CLI Usage](cli_usage.md) - General CLI documentation
- [Interactive Mode](user_mode.md) - Interactive mode documentation

## Database Sources

BLEEP's UUID databases are automatically updated from the Bluetooth SIG's Assigned Numbers repository. To update the databases manually:

```bash
python -m bleep.bt_ref.update_ble_uuids
```

This will fetch the latest UUID definitions from the Bluetooth SIG and regenerate the internal databases.

Alternatively, use the unified CLI command to refresh every committed
reference-data module in one step:

```bash
bleep refresh-refs              # all sources
bleep refresh-refs --sig-only   # only BT SIG assigned numbers (+ CoD/Mesh + BlueZ SDP)
bleep refresh-refs --vendor-only
bleep refresh-refs --oui-only    # only the IEEE OUI vendor database (bt_ref/oui.py)
bleep refresh-refs --usb-only    # only the USB-IF ID database (bt_ref/usb_ids.py)
```

`refresh-refs` wraps seven self-contained, network-best-effort updaters (each
falls back to its committed cache / prior module on failure — a refresh never
zeroes a table). The scope flags above are mutually exclusive; a bare
`refresh-refs` runs all seven:

| Source | Updater | Emits |
|--------|---------|-------|
| BT SIG assigned numbers | `bt_ref/update_ble_uuids.py` | `bt_ref/uuids.py` |
| BT SIG CoD + Mesh | `bt_ref/update_extra_refs.py` | `bt_ref/cod.py`, `bt_ref/mesh_ids.py` |
| **BlueZ SDP universal attribute IDs** | `bt_ref/update_bluez_refs.py` | `bt_ref/sdp_attr_ids.py` |
| **SIG profile SDP attribute IDs** | `bt_ref/update_sig_sdp_attr_ids.py` | `bt_ref/sdp_profile_attr_ids.py` |
| Vendor/community adv specs | `bt_ref/update_vendor_specs.py` | `bt_ref/vendor_adv_specs.py` |
| **IEEE OUI vendor database** (`--oui-only`) | `bt_ref/update_oui.py` | `bt_ref/oui.py` |
| **USB-IF ID database** (`--usb-only`) | `bt_ref/update_usb_ids.py` | `bt_ref/usb_ids.py` |

### BlueZ-sourced SDP attribute-ID labels

The SDP *attribute-ID* labels are **not** a single machine-readable SIG file (the
SIG `service_discovery/attribute_ids/` tree is a directory of per-profile YAMLs).
The canonical, stable source is the upstream BlueZ header `lib/sdp.h`, pulled from
`https://github.com/bluez/bluez.git` (canonical:
`git://git.kernel.org/pub/scm/bluetooth/bluez.git`), **pinned** to a specific
commit for reproducible refreshes and cached at `bt_ref/bluez_cache/sdp.h`.

> **SDP attribute IDs are context-dependent above the universal range.** Only the
> *universal* attribute IDs `0x0000`–`0x000D` (plus the primary-language string
> offsets `0x0100`–`0x0102`) carry a single unambiguous label. IDs `>= 0x0200`
> are **reused across profiles** — BlueZ defines `0x0200` as *all* of `GROUP_ID`,
> `IP_SUBNET`, `VERSION_NUM_LIST`, `SUPPORTED_FEATURES_LIST`, `GOEP_L2CAP_PSM`,
> `SPECIFICATION_ID`, `HID_DEVICE_RELEASE_NUMBER`, … — so their meaning depends on
> the record's service-class UUID.

#### Profile-scoped resolution

`resolve_sdp_attr_id(attr_id, service_class_uuid=None)` resolves context-dependent
IDs when the service class is known. It first checks the universal table
(`sdp_attr_ids.py`), then, for `>= 0x0200`, joins the ID to the service class via
`sdp_profile_attr_ids.py`:

- `SDP_PROFILE_ATTR_IDS = {profile_stem: {"0xNNNN": name}}` — the per-profile
  attribute-ID labels ingested from the SIG `service_discovery/attribute_ids/*.yaml`
  tree (generated by `update_sig_sdp_attr_ids.py`, cached under
  `bt_ref/sig_cache/attribute_ids/`).
- `SERVICE_CLASS_TO_PROFILE = {"0xNNNN": profile_stem}` — a curated reverse map
  (grounded in `uuids/service_class.yaml`) that picks the profile for a service
  class, so e.g. `0x0200` resolves to `HIDDeviceReleaseNumber` under HID
  (`0x1124`) but `IPSubnet`/PAN under `0x1116`.

Without a service class, `resolve_sdp_attr_id()` still returns universal labels and
returns `None` for unresolved context-dependent IDs. The SDP XML parser pre-scans a
record's Service Class ID List (attribute `0x0001`) *before* the main loop so
labelling is order-independent, then attaches resolved labels to the record's
`attribute_labels` field as a *lossless, additive* annotation — it never drops raw
data or overwrites a parsed field. Every ingested profile is reachable (a standing
test asserts no profile lacks a `SERVICE_CLASS_TO_PROFILE` entry — e.g. the WAP
`interoperability_requirements` table resolves under service classes `0x1113`/`0x1114`).

#### Sibling tables — string offsets & protocol parameters

`update_sig_sdp_attr_ids.py` also ingests two single-file siblings from
`assigned_numbers/service_discovery/` (cached under `bt_ref/sig_cache/`) into the
same generated module:

- `SDP_STRING_ATTR_OFFSETS` (from `attribute_id_offsets_for_strings.yaml`) —
  `ServiceName`/`ServiceDescription`/`ProviderName` at offsets `0x0000`/`0x0001`/
  `0x0002`. These are added to a **language base** declared in the record's
  `LanguageBaseAttributeIDList` (attr `0x0006`, a sequence of uint16 triplets
  `(code_ISO639, encoding, base_offset)` per BlueZ `sdp.c`). The SDP parser
  pre-scans attr `0x0006` and labels *secondary-language* string attributes as e.g.
  `"Service Name (fr)"` (the primary base `0x0100` is already covered by the
  universal table).
- `SDP_PROTOCOL_PARAMETERS` (from `protocol_parameters.yaml`) — names the positional
  parameters inside a ProtocolDescriptorList (attr `0x0004`) per protocol
  (`L2CAP[1]=PSM`, `RFCOMM[1]=Channel`, `BNEP[1]=Version`, `BNEP[2]=Supported
  Network Packet Type List`, …). `_extract_protocol_descriptors_xml` attaches these
  as an additive `parameters` list (`{index, name, value}`) on each descriptor,
  alongside the existing `uuid`/`name`.

### Core Specification version names

`bt_ref/uuids.py` also carries `SPEC_ID_NAMES__CORE_VERSION` (from SIG
`core/core_version.yaml`), keyed by the 1-byte LMP/HCI version as 2-digit hex
(`"0x0c"` → *Bluetooth® Core Specification 5.3*). `resolve_core_version()` and
`ble_ops/classic/version.py:map_lmp_version_to_spec()` consume it as the
**primary** name source (the hardcoded `_LMP_VERSION_MAP` is a fallback only for
values the SIG table lacks). The SIG table also authoritatively corrects LMP
`0x0E`/`0x0F` to *6.0*/*6.1* (the fallback historically mislabelled them
"5.5"/"5.6").

