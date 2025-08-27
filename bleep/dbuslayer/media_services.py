from __future__ import annotations

"""Light-weight wrapper for the org.bluez.Media1 service.

Phase-1 addition: provides only registration helpers so higher layers can
programmatically register endpoints/players without dropping to BlueZ test
scripts.  Mirrors coding/logging style of other dbuslayer modules.
"""

from typing import Dict, Any, Optional

import dbus

# Import the shared interface constant definitions
from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    ADAPTER_NAME,
    DBUS_PROPERTIES,
    MEDIA_INTERFACE,
)
from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.core.errors import map_dbus_error, BLEEPError

__all__ = ["MediaService"]


class MediaService:
    """Wrapper around *org.bluez.Media1* at the adapter level."""

    def __init__(self, adapter: str = ADAPTER_NAME):
        self.adapter = adapter
        self.service_path = f"/org/bluez/{adapter}"
        self._bus = dbus.SystemBus()
        try:
            self._object = self._bus.get_object(BLUEZ_SERVICE_NAME, self.service_path)
            self._interface = dbus.Interface(self._object, MEDIA_INTERFACE)
            self._properties = dbus.Interface(self._object, DBUS_PROPERTIES)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Media1 interface unavailable on {self.service_path}: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)

    # ------------------------------------------------------------------
    # Registration helpers ---------------------------------------------
    # ------------------------------------------------------------------

    def register_endpoint(self, endpoint_path: str, properties: Dict[str, Any]) -> bool:
        """Register a MediaEndpoint1 implementation with BlueZ.

        *endpoint_path* must already be exported on the bus by the caller.
        *properties* mirrors BlueZ docs (Codec, UUID, etc.).
        """
        try:
            self._interface.RegisterEndpoint(
                dbus.ObjectPath(endpoint_path),
                dbus.Dictionary(properties, signature="sv"),
            )
            print_and_log(f"[+] Registered MediaEndpoint {endpoint_path}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] RegisterEndpoint failed: {str(e)}", LOG__DEBUG)
            return False

    def unregister_endpoint(self, endpoint_path: str) -> bool:
        try:
            self._interface.UnregisterEndpoint(dbus.ObjectPath(endpoint_path))
            print_and_log(f"[+] Unregistered MediaEndpoint {endpoint_path}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] UnregisterEndpoint failed: {str(e)}", LOG__DEBUG)
            return False

    def register_player(self, player_path: str) -> bool:
        """Register a custom MediaPlayer1 implementation (source role)."""
        try:
            self._interface.RegisterPlayer(dbus.ObjectPath(player_path))
            print_and_log(f"[+] Registered MediaPlayer {player_path}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] RegisterPlayer failed: {str(e)}", LOG__DEBUG)
            return False

    def unregister_player(self, player_path: str) -> bool:
        try:
            self._interface.UnregisterPlayer(dbus.ObjectPath(player_path))
            print_and_log(f"[+] Unregistered MediaPlayer {player_path}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] UnregisterPlayer failed: {str(e)}", LOG__DEBUG)
            return False

    # ------------------------------------------------------------------
    # Introspection helpers --------------------------------------------
    # ------------------------------------------------------------------

    def get_registered_players(self) -> Optional[list[str]]:
        """Return list of currently registered custom players (if supported)."""
        try:
            supported = self._properties.Get(MEDIA_INTERFACE, "Players")
            return [str(p) for p in supported] if supported else []
        except dbus.exceptions.DBusException:
            return None

    def get_registered_endpoints(self) -> Optional[list[str]]:
        try:
            eps = self._properties.Get(MEDIA_INTERFACE, "Endpoints")
            return [str(e) for e in eps] if eps else []
        except dbus.exceptions.DBusException:
            return None 