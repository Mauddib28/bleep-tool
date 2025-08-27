from __future__ import annotations

"""Media browsing helpers – org.bluez.MediaFolder1 & MediaItem1.
Phase-1 addition: minimal wrappers for listing items and basic playback.
"""

from typing import Dict, Any, List, Tuple, Optional

import dbus

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    DBUS_PROPERTIES,
    MEDIA_FOLDER_INTERFACE,
    MEDIA_ITEM_INTERFACE,
)
from bleep.bt_ref.utils import dbus_to_python
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.core.errors import map_dbus_error

__all__ = ["MediaFolder", "MediaItem"]


class MediaFolder:
    """Wrapper around org.bluez.MediaFolder1 objects returned by MediaPlayer."""

    def __init__(self, folder_path: str):
        self.folder_path = folder_path
        self._bus = dbus.SystemBus()
        try:
            self._object = self._bus.get_object(BLUEZ_SERVICE_NAME, folder_path)
            self._interface = dbus.Interface(self._object, MEDIA_FOLDER_INTERFACE)
            self._properties = dbus.Interface(self._object, DBUS_PROPERTIES)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] MediaFolder unavailable: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)

    # Internal helper ----------------------------------------------------
    def _get_property(self, name: str):
        try:
            value = self._properties.Get(MEDIA_FOLDER_INTERFACE, name)
            return dbus_to_python(value)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get {name} property: {str(e)}", LOG__DEBUG)
            return None

    # Public helpers -----------------------------------------------------
    def list_items(self, start: int = 0, end: Optional[int] = None, attributes: Optional[List[str]] = None) -> List[Tuple[str, Dict[str, Any]]]:
        """Return items within the folder using BlueZ *ListItems*.

        Converts D-Bus array into list[(path, property-dict)].
        """
        filter_dict: Dict[str, Any] = {}
        if start:
            filter_dict["Start"] = dbus.UInt32(start)
        if end is not None:
            filter_dict["End"] = dbus.UInt32(end)
        if attributes is not None:
            filter_dict["Attributes"] = dbus.Array([dbus.String(a) for a in attributes], signature="s")
        try:
            result = self._interface.ListItems(dbus.Dictionary(filter_dict, signature="sv"))
            return [(str(path), dbus_to_python(props)) for path, props in result]
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] ListItems failed: {str(e)}", LOG__DEBUG)
            return []

    def change_folder(self, folder_path: str) -> bool:
        try:
            self._interface.ChangeFolder(dbus.ObjectPath(folder_path))
            print_and_log(f"[+] Changed folder to {folder_path}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] ChangeFolder failed: {str(e)}", LOG__DEBUG)
            return False

    def search(self, value: str, attributes: Optional[List[str]] = None):
        filter_dict: Dict[str, Any] = {}
        if attributes is not None:
            filter_dict["Attributes"] = dbus.Array([dbus.String(a) for a in attributes], signature="s")
        try:
            folder = self._interface.Search(dbus.String(value), dbus.Dictionary(filter_dict, signature="sv"))
            return str(folder)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Search failed: {str(e)}", LOG__DEBUG)
            return None

    # Properties
    def get_number_of_items(self) -> Optional[int]:
        return self._get_property("NumberOfItems")

    def get_name(self) -> Optional[str]:
        return self._get_property("Name")


class MediaItem:
    """Wrapper around org.bluez.MediaItem1 objects."""

    def __init__(self, item_path: str):
        self.item_path = item_path
        self._bus = dbus.SystemBus()
        try:
            self._object = self._bus.get_object(BLUEZ_SERVICE_NAME, item_path)
            self._interface = dbus.Interface(self._object, MEDIA_ITEM_INTERFACE)
            self._properties = dbus.Interface(self._object, DBUS_PROPERTIES)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] MediaItem unavailable: {str(e)}", LOG__DEBUG)
            raise map_dbus_error(e)

    # Internal helper
    def _get_property(self, name: str):
        try:
            value = self._properties.Get(MEDIA_ITEM_INTERFACE, name)
            return dbus_to_python(value)
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Failed to get {name} property: {str(e)}", LOG__DEBUG)
            return None

    # Methods
    def play(self) -> bool:
        try:
            self._interface.Play()
            print_and_log(f"[+] Play MediaItem {self.item_path}", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] Play failed: {str(e)}", LOG__DEBUG)
            return False

    def add_to_now_playing(self) -> bool:
        try:
            self._interface.AddtoNowPlaying()
            print_and_log(f"[+] Added MediaItem to now playing", LOG__GENERAL)
            return True
        except dbus.exceptions.DBusException as e:
            print_and_log(f"[-] AddToNowPlaying failed: {str(e)}", LOG__DEBUG)
            return False

    # Property helpers
    def get_player(self) -> Optional[str]:
        return self._get_property("Player")

    def get_name(self) -> Optional[str]:
        return self._get_property("Name")

    def get_type(self) -> Optional[str]:
        return self._get_property("Type")

    def get_folder_type(self) -> Optional[str]:
        return self._get_property("FolderType")

    def is_playable(self) -> bool:
        playable = self._get_property("Playable")
        return bool(playable)

    def get_metadata(self) -> Dict[str, Any]:
        meta = self._get_property("Metadata")
        return meta if meta else {} 