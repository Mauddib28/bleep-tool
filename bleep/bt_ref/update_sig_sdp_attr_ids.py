#!/usr/bin/python3
"""Generator for **profile-scoped** SDP attribute-ID labels (SIG assigned numbers).

The universal SDP attribute IDs (``0x0000``–``0x000D`` + the primary-language
string trio) are unambiguous and are handled by
:mod:`bleep.bt_ref.update_bluez_refs` (BlueZ ``lib/sdp.h``). Attribute IDs
``>= 0x0200`` are **context-dependent**: the same numeric ID means different
things in different profiles (e.g. ``0x0200`` is ``HIDDeviceReleaseNumber`` under
HID but ``IpSubnet`` under PAN). The Bluetooth SIG publishes these per-profile in
``assigned_numbers/service_discovery/attribute_ids/<profile>.yaml`` (schema
``attribute_ids: [{name, value}]``).

This generator pulls every per-profile YAML and emits
``bt_ref/sdp_profile_attr_ids.py``:

* ``SDP_PROFILE_ATTR_IDS = {profile_stem: {"0xNNNN": name}}`` — the fetched data.
* ``SERVICE_CLASS_TO_PROFILE = {"0xNNNN": profile_stem}`` — a curated reverse map
  from a record's Service-Class-ID (SIG ``uuids/service_class.yaml``) to the
  profile whose attribute table applies. Only this map makes a profile label
  *reachable*, so a numeric ID is only ever labelled when the service class
  disambiguates it (no guessing).

Design mirrors the other SIG updaters: **network-best-effort with a committed
per-file cache** (``bt_ref/sig_cache/attribute_ids/<profile>.yaml``), so the
package stays self-contained and offline-safe. A failed fetch with no cache
leaves the previously committed module untouched — it never zeroes a table.

In addition to the per-profile ``attribute_ids/`` tree, this generator ingests two
sibling single-file YAMLs from ``assigned_numbers/service_discovery/`` and emits
them into the same module:

* ``SDP_STRING_ATTR_OFFSETS = {"0xNNNN": name}`` from
  ``attribute_id_offsets_for_strings.yaml`` — the offsets (0x0000 ServiceName,
  0x0001 ServiceDescription, 0x0002 ProviderName) added to a language *base* from
  the record's LanguageBaseAttributeIDList (attr 0x0006). Lets the SDP parser label
  *secondary-language* string attributes (primary base 0x0100 is already covered by
  the universal table).
* ``SDP_PROTOCOL_PARAMETERS = {protocol_name: {index: name}}`` from
  ``protocol_parameters.yaml`` — names the positional parameters inside a
  ProtocolDescriptorList (attr 0x0004), e.g. L2CAP[1]=PSM, RFCOMM[1]=Channel,
  BNEP[1]=Version, BNEP[2]=Supported Network Packet Type List.

Usage:
    python -m bleep.bt_ref.update_sig_sdp_attr_ids   # regenerate sdp_profile_attr_ids.py
"""
from __future__ import annotations

import json
import pprint
import re
from datetime import datetime
from pathlib import Path

import yaml as _yaml

from bleep.bt_ref.update_ble_uuids import _download_file, _SIG_API_ROOT, _SIG_ROOT

_HERE = Path(__file__).parent
_CACHE_DIR = _HERE / "sig_cache" / "attribute_ids"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_OUT = _HERE / "sdp_profile_attr_ids.py"

_SD_DIR = "assigned_numbers/service_discovery/"
_ATTR_DIR = _SD_DIR + "attribute_ids/"
_API_LIST = _SIG_API_ROOT + "src/main/" + _ATTR_DIR

# Sibling single-file YAMLs under service_discovery/ (cached alongside the tree).
_SIBLING_CACHE_DIR = _HERE / "sig_cache"
_STRING_OFFSETS_FILE = "attribute_id_offsets_for_strings.yaml"
_PROTOCOL_PARAMS_FILE = "protocol_parameters.yaml"

# Profiles whose attribute IDs live in the universal range and are therefore
# already covered by the BlueZ universal table — excluded from the profile map
# to avoid a duplicate/ambiguous source.
_UNIVERSAL_STEMS = {"universal_attributes", "sdp"}

# Curated Service-Class-ID → profile-stem map, grounded in the SIG
# ``uuids/service_class.yaml`` names (verified 2026-07-24). Keys are lowercase
# 16-bit hex strings; a profile is only reachable (and therefore only ever emits
# a profile-specific label) when a record advertises one of these service classes.
_PROFILE_SERVICE_CLASSES: dict[str, set[str]] = {
    "a2dp": {"0x110a", "0x110b", "0x110d"},                 # Audio Source/Sink/A2DP
    "avrcp": {"0x110c", "0x110e", "0x110f"},                # A/V RC Target/RC/Controller
    "bip": {"0x111a", "0x111b", "0x111c", "0x111d"},        # Imaging*
    "bpp": {"0x1118", "0x1119", "0x1120", "0x1122", "0x1123"},  # Printing*
    "browse_group_descriptor_service": {"0x1001"},
    "calendar_tasks_and_notes": {"0x113c", "0x113d", "0x113e"},  # CTN*/CTN Profile
    "cordless_telephony_profile": {"0x1109"},
    "device_identification_profile": {"0x1200"},            # PnPInformation
    "dun": {"0x1103"},                                      # Dial-Up Networking
    "fax_profile": {"0x1111"},
    "file_transfer_profile": {"0x1106"},                    # OBEX File Transfer
    "gnss": {"0x1135", "0x1136"},
    "hands_free_profile": {"0x111e", "0x111f"},             # Hands-Free / AG
    "hardcopy_replacement_profile": {"0x1125", "0x1126", "0x1127"},
    "headset_profile": {"0x1108", "0x1112", "0x1131"},      # Headset / AG / HS
    "health_device_profile": {"0x1400", "0x1401", "0x1402"},  # HDP / Source / Sink
    "human_interface_device_profile": {"0x1124"},           # HID
    "interoperability_requirements": {"0x1113", "0x1114"},   # WAP / WAP_CLIENT
    "message_access_profile": {"0x1132", "0x1133", "0x1134"},
    "multi_profile": {"0x113a", "0x113b"},                  # MPS
    "object_push_profile": {"0x1105"},                      # OBEX Object Push
    "pan_profile": {"0x1115", "0x1116", "0x1117"},          # PANU / NAP / GN
    "phone_book_access_profile": {"0x112e", "0x112f", "0x1130"},
    "synchronization_profile": {"0x1104", "0x1107"},        # IrMCSync / SyncCommand
}

_HDR = (
    "#!/usr/bin/python3\n\n"
    "# Auto-generated profile-scoped SDP attribute-ID labels (SIG assigned numbers).\n"
    "# DO NOT EDIT - run `python -m bleep.bt_ref.update_sig_sdp_attr_ids` (or `bleep refresh-refs`).\n"
    "# Generated: {ts}\n"
    "# Source: {src}\n\n"
)

_VALUE_RE = re.compile(r"^0x[0-9a-fA-F]{1,4}$")


def _list_profiles() -> list[str]:
    """List profile YAML filenames via the SIG API (offline → cached files)."""
    names: list[str] = []
    url: str | None = _API_LIST
    while url:
        raw = _download_file(url)
        if not raw:
            names = []
            break
        try:
            j = json.loads(raw)
        except Exception:  # pragma: no cover - defensive
            names = []
            break
        for v in j.get("values", []):
            p = v.get("path", "")
            if p.endswith(".yaml"):
                names.append(p.split("/")[-1])
        url = j.get("next")
    if names:
        return sorted(names)
    # Offline fallback: whatever we have committed in the cache.
    print("[*] Falling back to committed attribute_ids cache listing")
    return sorted(p.name for p in _CACHE_DIR.glob("*.yaml"))


def _fetch_profile(filename: str) -> dict | None:
    """Fetch one profile YAML (network-best-effort → committed per-file cache)."""
    url = _SIG_ROOT + _ATTR_DIR + filename
    cache_path = _CACHE_DIR / filename
    raw = _download_file(url)
    if raw:
        try:
            parsed = _yaml.safe_load(raw)
            cache_path.write_text(raw, encoding="utf-8")
            return parsed
        except Exception as e:  # pragma: no cover - defensive
            print(f"[!] Parse error for {filename}: {e}")
    if cache_path.exists():
        return _yaml.safe_load(cache_path.read_text(encoding="utf-8"))
    return None


def _compile_profile(data: dict) -> dict[str, str]:
    """{``"0xNNNN"``: name} for one profile's ``attribute_ids`` list."""
    out: dict[str, str] = {}
    for entry in (data.get("attribute_ids") or []):
        name = entry.get("name")
        value = entry.get("value")
        if name is None or value is None:
            continue
        # PyYAML parses ``0xNNNN`` to int; normalise to a lowercase 4-hex key.
        if isinstance(value, int):
            val = value
        else:
            s = str(value).strip()
            if not _VALUE_RE.match(s):
                continue
            val = int(s, 16)
        out[f"0x{val:04x}"] = str(name).strip()
    return out


def _fetch_sibling(filename: str) -> dict | None:
    """Fetch a service_discovery/ single-file YAML (network-best-effort → cache)."""
    url = _SIG_ROOT + _SD_DIR + filename
    cache_path = _SIBLING_CACHE_DIR / filename
    raw = _download_file(url)
    if raw:
        try:
            parsed = _yaml.safe_load(raw)
            cache_path.write_text(raw, encoding="utf-8")
            return parsed
        except Exception as e:  # pragma: no cover - defensive
            print(f"[!] Parse error for {filename}: {e}")
    if cache_path.exists():
        return _yaml.safe_load(cache_path.read_text(encoding="utf-8"))
    return None


def _compile_protocol_parameters(data: dict) -> dict[str, dict[int, str]]:
    """{protocol_name: {index: name}} from ``protocol_parameters`` list."""
    out: dict[str, dict[int, str]] = {}
    for entry in (data.get("protocol_parameters") or []):
        proto = entry.get("protocol")
        name = entry.get("name")
        index = entry.get("index")
        if proto is None or name is None or index is None:
            continue
        try:
            idx = int(index)
        except (TypeError, ValueError):
            continue
        out.setdefault(str(proto).strip(), {})[idx] = str(name).strip()
    return out


def _committed(constant: str, default):
    """Return a constant already committed in ``sdp_profile_attr_ids.py`` (or default).

    Used so a sibling fetch that yields nothing (offline, no cache) never *zeroes*
    a previously-committed table when the module is rewritten.
    """
    try:
        import importlib

        mod = importlib.import_module("bleep.bt_ref.sdp_profile_attr_ids")
        return getattr(mod, constant, default)
    except Exception:  # pragma: no cover - module may not exist yet
        return default


def _emit(
    profiles: dict[str, dict[str, str]],
    string_offsets: dict[str, str],
    protocol_parameters: dict[str, dict[int, str]],
    src: str,
) -> None:
    reverse: dict[str, str] = {}
    for stem, classes in _PROFILE_SERVICE_CLASSES.items():
        if stem not in profiles:
            continue  # never map to a profile we failed to compile
        for sc in classes:
            reverse[sc] = stem

    body = [_HDR.format(ts=datetime.now().isoformat(timespec="seconds"), src=src)]
    body.append(
        '"""Profile-scoped SDP attribute-ID labels + string offsets + protocol params\n'
        "(SIG assigned_numbers/service_discovery).\n\n"
        "Attribute IDs >= 0x0200 are context-dependent; a label is only correct in the\n"
        "context of the record's Service-Class-ID. ``SERVICE_CLASS_TO_PROFILE`` maps a\n"
        "service class to the owning profile so a numeric ID is only ever labelled when\n"
        "the service class disambiguates it.\n\n"
        "``SDP_STRING_ATTR_OFFSETS`` are offsets added to a LanguageBaseAttributeIDList\n"
        "base (attr 0x0006) for ServiceName/Description/ProviderName in each language.\n"
        "``SDP_PROTOCOL_PARAMETERS`` names the positional parameters of a\n"
        'ProtocolDescriptorList (attr 0x0004) per protocol."""'
    )
    body.append("SDP_PROFILE_ATTR_IDS = " + pprint.pformat(profiles, indent=4, width=100, sort_dicts=True))
    body.append("")
    body.append("SERVICE_CLASS_TO_PROFILE = " + pprint.pformat(reverse, indent=4, width=100, sort_dicts=True))
    body.append("")
    body.append("SDP_STRING_ATTR_OFFSETS = " + pprint.pformat(string_offsets, indent=4, width=100, sort_dicts=True))
    body.append("")
    body.append("SDP_PROTOCOL_PARAMETERS = " + pprint.pformat(protocol_parameters, indent=4, width=100, sort_dicts=True))
    body.append("")
    _OUT.write_text("\n".join(body), encoding="utf-8")


def regenerate() -> None:
    """Regenerate ``sdp_profile_attr_ids.py`` (non-destructive on failure)."""
    filenames = _list_profiles()
    if not filenames:
        print("[!] No attribute_ids profiles available; leaving sdp_profile_attr_ids.py untouched")
        return
    profiles: dict[str, dict[str, str]] = {}
    for filename in filenames:
        stem = filename[:-5] if filename.endswith(".yaml") else filename
        if stem in _UNIVERSAL_STEMS:
            continue
        data = _fetch_profile(filename)
        if not data:
            continue
        table = _compile_profile(data)
        if table:
            profiles[stem] = table
    if not profiles:
        print("[!] No profile attribute IDs parsed; leaving sdp_profile_attr_ids.py untouched")
        return

    # Sibling single-file tables. On a fetch/parse miss with no cache, preserve the
    # already-committed constant rather than zeroing it (non-destructive discipline).
    so_data = _fetch_sibling(_STRING_OFFSETS_FILE)
    string_offsets = _compile_profile(so_data) if so_data else {}
    if not string_offsets:
        string_offsets = _committed("SDP_STRING_ATTR_OFFSETS", {})

    pp_data = _fetch_sibling(_PROTOCOL_PARAMS_FILE)
    protocol_parameters = _compile_protocol_parameters(pp_data) if pp_data else {}
    if not protocol_parameters:
        protocol_parameters = _committed("SDP_PROTOCOL_PARAMETERS", {})

    _emit(profiles, string_offsets, protocol_parameters, src=_SD_DIR + "{attribute_ids/*,siblings}.yaml")
    total = sum(len(t) for t in profiles.values())
    print(
        f"[+] Wrote {_OUT.name} ({len(profiles)} profiles, {total} attribute IDs; "
        f"{len(string_offsets)} string offsets, {len(protocol_parameters)} protocols)"
    )


if __name__ == "__main__":
    regenerate()
