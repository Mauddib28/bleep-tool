from __future__ import annotations

"""Convenience helper for registering common A2DP endpoints via Media1.

This is *not* a full-featured application manager – it just builds the required
property dictionaries and calls Media1.RegisterEndpoint/UnregisterEndpoint so
BLEEP can act as a very simple SBC sink or source for testing purposes.
"""

from typing import Dict, Any

import dbus

from bleep.bt_ref.constants import (
    ADAPTER_NAME,
    BLUEZ_SERVICE_NAME,
)
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.core.errors import map_dbus_error

from .media_services import MediaService

__all__ = ["MediaRegisterHelper"]


class MediaRegisterHelper:
    """High-level helper to register SBC endpoints (sink/source)."""

    # UUIDs (Bluetooth SIG):
    A2DP_SOURCE_UUID = "0000110A-0000-1000-8000-00805F9B34FB"
    A2DP_SINK_UUID = "0000110B-0000-1000-8000-00805F9B34FB"

    SBC_CODEC = dbus.Byte(0x00)
    # Copy from BlueZ example-endpoint
    SBC_CAPABILITIES = dbus.Array(
        [dbus.Byte(0xFF), dbus.Byte(0xFF), dbus.Byte(2), dbus.Byte(64)],
        signature="y",
    )

    def __init__(self, adapter: str = ADAPTER_NAME):
        self.media = MediaService(adapter)

    # ------------------------------------------------------------------
    # Public API --------------------------------------------------------
    # ------------------------------------------------------------------

    def register_sbc_sink(self, endpoint_path: str) -> bool:
        """Register an SBC *sink* endpoint under *endpoint_path*."""
        props = self._build_sbc_properties(sink=True)
        return self.media.register_endpoint(endpoint_path, props)

    def register_sbc_source(self, endpoint_path: str) -> bool:
        """Register an SBC *source* endpoint under *endpoint_path*."""
        props = self._build_sbc_properties(sink=False)
        return self.media.register_endpoint(endpoint_path, props)

    def unregister(self, endpoint_path: str) -> bool:
        return self.media.unregister_endpoint(endpoint_path)

    # ------------------------------------------------------------------
    # Internal helpers --------------------------------------------------
    # ------------------------------------------------------------------

    @classmethod
    def _build_sbc_properties(cls, *, sink: bool) -> Dict[str, Any]:
        uuid = cls.A2DP_SINK_UUID if sink else cls.A2DP_SOURCE_UUID
        return {
            "UUID": uuid,
            "Codec": cls.SBC_CODEC,
            "DelayReporting": dbus.Boolean(True),
            "Capabilities": cls.SBC_CAPABILITIES,
        } 