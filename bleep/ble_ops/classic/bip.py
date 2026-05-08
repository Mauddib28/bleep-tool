"""bleep.ble_ops.classic_bip – Basic Imaging Profile operations.

Thin wrapper around ``bleep.dbuslayer.obex_bip`` that adds BLEEP-standard
logging, optional observation-database storage, and service detection from
SDP records (UUID ``0x111A``).

Prerequisites: same as ``obex_bip`` (``bluetooth-obexd --experimental``,
paired/trusted).

.. warning::
   The BlueZ ``Image1`` interface is marked **[experimental]**.  It requires
   obexd to be started with ``--experimental`` and may change or be removed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None

from bleep.dbuslayer.obex_bip import BipSession

from bleep.bt_ref.constants import BIP_UUID_SHORT


def detect_bip_service(service_map: Optional[Dict[str, int]]) -> bool:
    """Return True if the service map contains a BIP entry."""
    if not service_map:
        return False
    for key in service_map:
        low = key.lower()
        if "111a" in low or "111b" in low or "imag" in low or "bip" in low:
            return True
    return False


def get_properties(
    mac_address: str,
    handle: str,
    *,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """Retrieve image properties for a handle on the remote device.

    Returns a list of dicts (handle/name, native description, variant
    descriptions).
    """
    mac_address = mac_address.strip().upper()
    print_and_log(
        f"[bip] Getting properties for handle {handle} on {mac_address}",
        LOG__GENERAL,
    )
    with BipSession(mac_address, timeout=timeout) as sess:
        props = sess.properties(handle)

    print_and_log(f"[bip] Got {len(props)} property entries", LOG__GENERAL)
    return props


def get_image(
    mac_address: str,
    target_file: str,
    handle: str,
    description: Optional[Dict[str, Any]] = None,
    *,
    timeout: int = 60,
) -> Path:
    """Download an image by handle from the remote device.

    *description*: one of the descriptions from ``get_properties()``.
    Pass ``None`` or ``{}`` to retrieve the native image.

    Returns the ``Path`` to the saved file.
    """
    mac_address = mac_address.strip().upper()
    print_and_log(
        f"[bip] Getting image handle={handle} from {mac_address}",
        LOG__GENERAL,
    )
    with BipSession(mac_address, timeout=timeout) as sess:
        result = sess.get_image(target_file, handle, description)

    print_and_log(f"[bip] Image saved → {result}", LOG__GENERAL)

    if _obs is not None:
        try:
            _obs.add_observation(
                mac_address,
                "bip_get_image",
                {"handle": handle, "file": str(result)},
            )
        except Exception:  # noqa: BLE001
            pass

    return result


def get_thumbnail(
    mac_address: str,
    target_file: str,
    handle: str,
    *,
    timeout: int = 60,
) -> Path:
    """Download an image thumbnail by handle from the remote device.

    Returns the ``Path`` to the saved thumbnail file.
    """
    mac_address = mac_address.strip().upper()
    print_and_log(
        f"[bip] Getting thumbnail handle={handle} from {mac_address}",
        LOG__GENERAL,
    )
    with BipSession(mac_address, timeout=timeout) as sess:
        result = sess.get_thumbnail(target_file, handle)

    print_and_log(f"[bip] Thumbnail saved → {result}", LOG__GENERAL)

    if _obs is not None:
        try:
            _obs.add_observation(
                mac_address,
                "bip_get_thumbnail",
                {"handle": handle, "file": str(result)},
            )
        except Exception:  # noqa: BLE001
            pass

    return result
