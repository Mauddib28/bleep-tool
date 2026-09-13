#!/usr/bin/python3

# Auto-generated SDP universal attribute-ID labels.
# DO NOT EDIT - run `python -m bleep.bt_ref.update_bluez_refs` (or `bleep refresh-refs`).
# Generated: 2026-07-28T09:31:13
# Source: bluez lib/sdp.h @ 4c431e5dae3e7cee4ce3d0720fefc530a2524e0b (lib/sdp.h)


"""SDP universal attribute-ID labels (BlueZ lib/sdp.h, universal range).

Only the universal SDP attribute IDs (0x0000-0x000D) plus the primary-language
string offsets (0x0100-0x0102) carry an unambiguous single label and live in
``SDP_UNIVERSAL_ATTR_IDS``. IDs >= 0x0200 are profile-context-dependent, so they
are absent from that table; ``resolve_sdp_attr_id(attr_id, service_class_uuid)``
resolves them via the per-profile SIG tables in ``sdp_profile_attr_ids.py`` only
when the record's service class disambiguates them."""

SDP_UNIVERSAL_ATTR_IDS = {   '0x0000': 'Service Record Handle',
    '0x0001': 'Service Class ID List',
    '0x0002': 'Service Record State',
    '0x0003': 'Service ID',
    '0x0004': 'Protocol Descriptor List',
    '0x0005': 'Browse Group List',
    '0x0006': 'Language Base Attribute ID List',
    '0x0007': 'Service Info Time To Live',
    '0x0008': 'Service Availability',
    '0x0009': 'Bluetooth Profile Descriptor List',
    '0x000a': 'Documentation URL',
    '0x000b': 'Client Executable URL',
    '0x000c': 'Icon URL',
    '0x000d': 'Additional Protocol Descriptor Lists',
    '0x0100': 'Service Name',
    '0x0101': 'Service Description',
    '0x0102': 'Provider Name'}

def _service_class_key(service_class_uuid):
    """Normalise a Service-Class-ID to a lowercase 16-bit hex key ("0xnnnn")."""
    if service_class_uuid is None:
        return None
    if isinstance(service_class_uuid, int):
        return f"0x{service_class_uuid & 0xFFFF:04x}"
    s = str(service_class_uuid).strip().lower().replace("0x", "").replace("-", "")
    if len(s) >= 32 and s.endswith("00001000800000805f9b34fb"):
        s = s[4:8]  # 16-bit portion of a SIG-base 128-bit UUID
    try:
        return f"0x{int(s, 16) & 0xFFFF:04x}"
    except ValueError:
        return None


def resolve_sdp_attr_id(attr_id, service_class_uuid=None):
    """Return an SDP attribute-ID label, or None if unknown/ambiguous.

    ``attr_id`` may be an int (0x0004) or a hex string ("0x0004"/"0004").

    The universal range (0x0000-0x000D, plus the primary-language string offsets)
    is always resolved. Profile-context IDs (>= 0x0200) are only resolved when
    ``service_class_uuid`` is supplied *and* maps to a profile whose SIG attribute
    table knows the ID — otherwise None (a numeric ID like 0x0200 means different
    things per profile, so it is never guessed)."""
    if isinstance(attr_id, str):
        s = attr_id.strip().lower().replace("0x", "")
        try:
            attr_id = int(s, 16)
        except ValueError:
            return None
    key = f"0x{attr_id:04x}"
    universal = SDP_UNIVERSAL_ATTR_IDS.get(key)
    if universal is not None:
        return universal
    sc_key = _service_class_key(service_class_uuid)
    if sc_key is None:
        return None
    try:
        from bleep.bt_ref.sdp_profile_attr_ids import (
            SDP_PROFILE_ATTR_IDS,
            SERVICE_CLASS_TO_PROFILE,
        )
    except Exception:
        return None
    profile = SERVICE_CLASS_TO_PROFILE.get(sc_key)
    if not profile:
        return None
    return SDP_PROFILE_ATTR_IDS.get(profile, {}).get(key)
