"""bleep.ble_ops.classic_sync – IrMC Synchronization operations.

Thin wrapper around ``bleep.dbuslayer.obex_sync`` that adds BLEEP-standard
logging, optional observation-database storage, and service detection from
SDP records (UUID ``0x1104``).

Prerequisites: same as ``obex_sync`` (``bluetooth-obexd``, paired/trusted).

Note: very few modern devices advertise IrMC Sync.  This profile is
primarily useful for legacy handsets that expose phonebook or calendar
data through the IrMC store rather than PBAP.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None

from bleep.dbuslayer.obex_sync import SyncSession

from bleep.bt_ref.constants import SYNC_UUID_SHORT


def detect_sync_service(service_map: Optional[Dict[str, int]]) -> bool:
    """Return True if the service map contains an IrMC Sync entry."""
    if not service_map:
        return False
    for key in service_map:
        low = key.lower()
        if "1104" in low or "irmc" in low or "sync" in low:
            return True
    return False


def set_location(
    mac_address: str,
    location: str = "int",
    *,
    timeout: int = 30,
) -> None:
    """Set the phonebook object store location on the remote device.

    *location*: ``"int"`` (internal) or ``"sim1"``, ``"sim2"``, etc.
    """
    mac_address = mac_address.strip().upper()
    print_and_log(
        f"[sync] Setting phonebook location → {location} on {mac_address}",
        LOG__GENERAL,
    )
    with SyncSession(mac_address, timeout=timeout) as sess:
        sess.set_location(location)
    print_and_log(f"[sync] Location set to '{location}'", LOG__GENERAL)


def get_phonebook(
    mac_address: str,
    target_file: str = "",
    *,
    location: str = "int",
    timeout: int = 60,
) -> Path:
    """Download the phonebook from the remote device.

    *target_file*: local file path.  If empty, obexd auto-generates one.
    *location*: ``"int"`` or ``"sim{#}"``.

    Returns the ``Path`` to the downloaded file.
    """
    mac_address = mac_address.strip().upper()
    print_and_log(
        f"[sync] Getting phonebook ({location}) from {mac_address}",
        LOG__GENERAL,
    )
    with SyncSession(mac_address, timeout=timeout) as sess:
        sess.set_location(location)
        result = sess.get_phonebook(target_file)

    print_and_log(f"[sync] Phonebook saved → {result}", LOG__GENERAL)

    if _obs is not None:
        try:
            _obs.add_observation(
                mac_address,
                "sync_get_phonebook",
                {"location": location, "file": str(result)},
            )
        except Exception:  # noqa: BLE001
            pass

    return result


def put_phonebook(
    mac_address: str,
    source_file: str,
    *,
    location: str = "int",
    timeout: int = 60,
) -> Dict[str, Any]:
    """Upload a phonebook file to the remote device.

    *source_file*: local VCF file to upload.
    *location*: ``"int"`` or ``"sim{#}"``.
    """
    mac_address = mac_address.strip().upper()
    src = Path(source_file)
    if not src.is_file():
        raise FileNotFoundError(f"Source file not found: {source_file}")

    print_and_log(
        f"[sync] Putting phonebook ({location}) → {mac_address}",
        LOG__GENERAL,
    )
    with SyncSession(mac_address, timeout=timeout) as sess:
        sess.set_location(location)
        result = sess.put_phonebook(source_file)

    print_and_log(f"[sync] Phonebook uploaded OK", LOG__GENERAL)

    if _obs is not None:
        try:
            _obs.add_observation(
                mac_address,
                "sync_put_phonebook",
                {"location": location, "file": str(src)},
            )
        except Exception:  # noqa: BLE001
            pass

    return result
