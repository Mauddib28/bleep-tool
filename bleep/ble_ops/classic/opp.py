"""bleep.ble_ops.classic_opp – Object Push Profile operations.

Thin wrapper around ``bleep.dbuslayer.obex_opp`` that adds BLEEP-standard
logging, optional observation-database storage, and service detection from
SDP records (UUID ``0x1105``).

Prerequisites: same as ``obex_opp`` (``bluetooth-obexd``, paired/trusted).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None

from bleep.dbuslayer.obex_opp import opp_send_file as _opp_send
from bleep.dbuslayer.obex_opp import opp_pull_business_card as _opp_pull
from bleep.dbuslayer.obex_opp import opp_exchange_business_cards as _opp_exchange

from bleep.bt_ref.constants import (
    OPP_UUID_SHORT,
    OPP_UUID as OPP_UUID_FULL,
)


def detect_opp_service(service_map: Optional[Dict[str, int]]) -> bool:
    """Return True if the service map contains an OPP entry."""
    if not service_map:
        return False
    for key in service_map:
        low = key.lower()
        if "1105" in low or "object push" in low or "opp" in low:
            return True
    return False


def send_file(
    mac_address: str,
    filepath: str,
    *,
    timeout: int = 120,
    channel: Optional[int] = None,
) -> Dict:
    """Send a file to *mac_address* via OPP.

    Parameters
    ----------
    channel
        RFCOMM channel for OPP on the target (from prior SDP).

    Returns a dict with ``status``, ``transferred``, ``size`` keys on success.
    Raises ``RuntimeError`` on failure.
    """
    mac_address = mac_address.strip().upper()
    filepath = os.path.abspath(filepath)

    print_and_log(f"[OPP] Sending {filepath} → {mac_address}", LOG__GENERAL)
    result = _opp_send(mac_address, filepath, timeout=timeout, channel=channel)
    print_and_log(
        f"[OPP] Transfer complete: {result.get('transferred', '?')}B", LOG__GENERAL
    )

    if _obs:
        try:
            _obs.upsert_opp_transfer(
                mac_address, os.path.basename(filepath), "send",
                result.get("size", 0),
            )
        except Exception:
            pass

    return result


def pull_business_card(
    mac_address: str,
    dest: str = "business_card.vcf",
    *,
    timeout: int = 60,
    channel: Optional[int] = None,
) -> Path:
    """Pull the default business card from *mac_address* via OPP.

    Parameters
    ----------
    channel
        RFCOMM channel for OPP on the target (from prior SDP).

    Returns the ``Path`` to the downloaded file.
    Raises ``RuntimeError`` on failure.
    """
    mac_address = mac_address.strip().upper()

    print_and_log(f"[OPP] Pulling business card from {mac_address}", LOG__GENERAL)
    result = _opp_pull(mac_address, dest, timeout=timeout, channel=channel)
    size = result.stat().st_size if result.exists() else 0
    print_and_log(f"[OPP] Saved → {result} ({size} bytes)", LOG__GENERAL)

    if _obs:
        try:
            _obs.upsert_opp_transfer(
                mac_address, str(result), "pull",
                result.stat().st_size if result.exists() else 0,
            )
        except Exception:
            pass

    return result


def exchange_business_cards(
    mac_address: str,
    client_vcf: str,
    dest: str = "business_card.vcf",
    *,
    timeout: int = 120,
    channel: Optional[int] = None,
) -> Path:
    """Push *client_vcf* to *mac_address* then pull the remote business card.

    Parameters
    ----------
    channel
        RFCOMM channel for OPP on the target (from prior SDP).

    Returns the ``Path`` to the downloaded remote card.
    Raises ``RuntimeError`` on failure.
    """
    mac_address = mac_address.strip().upper()

    print_and_log(
        f"[OPP] Exchanging cards with {mac_address} (push={client_vcf})",
        LOG__GENERAL,
    )
    result = _opp_exchange(
        mac_address, client_vcf, dest, timeout=timeout, channel=channel,
    )
    print_and_log(f"[OPP] Exchange complete — remote card → {result}", LOG__GENERAL)

    if _obs:
        try:
            _obs.upsert_opp_transfer(
                mac_address, str(result), "exchange",
                result.stat().st_size if result.exists() else 0,
            )
        except Exception:
            pass

    return result
