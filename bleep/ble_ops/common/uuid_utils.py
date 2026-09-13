"""UUID utility functions for Bluetooth operations."""

from typing import Set, Optional
import re
import logging

from bleep.bt_ref.constants import BT_SIG_BASE_UUID

_BT_SIG_NODASH = BT_SIG_BASE_UUID.replace("-", "").upper()


def identify_uuid(uuid: str) -> Set[str]:
    """Identify and normalize a UUID, handling various formats.

    Parameters
    ----------
    uuid : str
        The UUID to identify, in any format

    Returns
    -------
    Set[str]
        A set of possible canonical representations of the UUID (uppercase, no dashes)
    """
    target = uuid.replace("-", "").upper()
    canonical_targets: set[str] = set()

    short_uuid = None
    if len(target) == 32:
        if target[8:] == _BT_SIG_NODASH[8:]:
            short_uuid = target[4:8]
        else:
            canonical_targets.add(target)

    elif len(target) == 4:
        short_uuid = target
        canonical_targets.add(f"0000{target}{_BT_SIG_NODASH[8:]}")

    elif len(target) == 8:
        canonical_targets.add(f"{target}{_BT_SIG_NODASH[8:]}")

    else:
        clean_target = ''.join(c for c in target if c.isalnum()).upper()
        if len(clean_target) == 32:
            canonical_targets.add(clean_target)
            if clean_target[8:] == _BT_SIG_NODASH[8:]:
                short_uuid = clean_target[4:8]
        elif len(clean_target) == 4:
            short_uuid = clean_target
            canonical_targets.add(f"0000{clean_target}{_BT_SIG_NODASH[8:]}")
        elif len(clean_target) == 8:
            canonical_targets.add(f"{clean_target}{_BT_SIG_NODASH[8:]}")

    if short_uuid:
        canonical_targets.add(short_uuid)

    return canonical_targets


def match_uuid(target_uuid: str, available_uuids: list[str]) -> Optional[str]:
    """Match a target UUID against a list of available UUIDs.

    Parameters
    ----------
    target_uuid : str
        The UUID to match
    available_uuids : list[str]
        List of available UUIDs to match against

    Returns
    -------
    Optional[str]
        The matched UUID if found, None otherwise
    """
    target_forms = identify_uuid(target_uuid)

    normalized_uuids = {uuid.replace("-", "").upper(): uuid for uuid in available_uuids}

    for form in target_forms:
        if form in normalized_uuids:
            return normalized_uuids[form]

    for form in target_forms:
        if len(form) == 4:
            for uuid in normalized_uuids:
                if uuid[4:8] == form:
                    return normalized_uuids[uuid]

    return None
