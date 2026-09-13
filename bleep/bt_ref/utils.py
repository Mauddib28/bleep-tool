"""
Bluetooth utility functions.
"""

# Updated 2024/10/09
#   - Expanded UUID identification to include UUIDs generated into the Bluetooth UUIDs file

import dbus
import sys
from . import constants
from . import uuids

# Variables
dbg = 0

__all__ = [
    "byteArrayToHexString",
    "dbus_to_python",
    "device_address_to_path",
    "get_name_from_uuid",
    "text_to_ascii_array",
    "print_properties",
    "handle_int_to_hex",
    "handle_hex_to_int",
]


def byteArrayToHexString(bytes):
    hex_string = ""
    for byte in bytes:
        hex_byte = "%02X" % byte
        hex_string = hex_string + hex_byte
    return hex_string


def dbus_to_python(data):
    if isinstance(data, dbus.String):
        data = str(data)
    if isinstance(data, dbus.ObjectPath):
        data = str(data)
    elif isinstance(data, dbus.Boolean):
        data = bool(data)
    elif isinstance(data, dbus.Int64):
        data = int(data)
    elif isinstance(data, dbus.Int32):
        data = int(data)
    elif isinstance(data, dbus.Int16):
        data = int(data)
    elif isinstance(data, dbus.UInt64):
        data = int(data)
    elif isinstance(data, dbus.UInt32):
        data = int(data)
    elif isinstance(data, dbus.UInt16):
        data = int(data)
    elif isinstance(data, dbus.Byte):
        data = int(data)
    elif isinstance(data, dbus.Double):
        data = float(data)
    elif isinstance(data, dbus.types.UnixFd):
        data = data.take()
    elif isinstance(data, dbus.Array):
        data = [dbus_to_python(value) for value in data]
    elif isinstance(data, dbus.Dictionary):
        new_data = dict()
        for key in data.keys():
            new_data[key] = dbus_to_python(data[key])
        data = new_data
    return data


def device_address_to_path(bdaddr, adapter_path):
    # e.g.convert 12:34:44:00:66:D5 on adapter hci0 to /org/bluez/hci0/dev_12_34_44_00_66_D5
    path = adapter_path + "/dev_" + bdaddr.replace(":", "_")
    return path


def get_name_from_uuid(uuid, uuid_class=None, *, allow_observed=False):
    """Resolve a UUID to a human-readable name via the authoritative tiers.

    Tiers (in order): custom ``constants.UUID_NAMES`` → SIG GATT tables
    (service/characteristic/descriptor/member/SDO/service-class) → SIG Mesh model
    UUIDs. All are authoritative and never changed by observed data.

    ``allow_observed`` (keyword-only, default ``False``) adds a *final,
    non-authoritative* tier: when every authoritative tier misses, the observed
    catalogue is consulted and a ``"Unknown (seen as: …)"`` hint is returned if
    the UUID has been recorded under a name on a real device. It is opt-in so the
    default resolution output is unchanged (``"Unknown"``); only explicit callers
    (e.g. ``db uuids``) surface the observed hint. This never pollutes the
    authoritative tables.
    """
    if dbg != 0:
        print("[*] bluetooth_utils::UUID passed as type [ {0} ]".format(type(uuid)))
        print(
            "[*] bluetooth_utils::Searching for Known Name for UUID [ {0} ]".format(
                uuid
            )
        )

    uuid = uuid.strip().upper() if isinstance(uuid, str) else uuid

    if uuid in constants.UUID_NAMES:
        return constants.UUID_NAMES[uuid]

    if uuid in uuids.SPEC_UUID_NAMES__SERV:
        if dbg != 0:
            print(
                "[+] bluetooth_utils::UUID [ {0} ] matches known Service UUID [ {1} ]".format(
                    uuid, uuids.SPEC_UUID_NAMES__SERV[uuid]
                )
            )
        return uuids.SPEC_UUID_NAMES__SERV[uuid]
    elif uuid in uuids.SPEC_UUID_NAMES__CHAR:
        return uuids.SPEC_UUID_NAMES__CHAR[uuid]
    elif uuid in uuids.SPEC_UUID_NAMES__DESC:
        return uuids.SPEC_UUID_NAMES__DESC[uuid]
    elif uuid in uuids.SPEC_UUID_NAMES__MEMB:
        return uuids.SPEC_UUID_NAMES__MEMB[uuid]
    elif uuid in uuids.SPEC_UUID_NAMES__SDO:
        return uuids.SPEC_UUID_NAMES__SDO[uuid]
    elif uuid in uuids.SPEC_UUID_NAMES__SERV_CLASS:
        return uuids.SPEC_UUID_NAMES__SERV_CLASS[uuid]

    # Bluetooth Mesh model UUIDs (SIG-assigned, generated into bt_ref/mesh_ids.py).
    # These 16-bit model IDs (0x0000-0x00xx) live below the GATT ranges, so they
    # cannot collide with service/characteristic/descriptor UUIDs; consulted last
    # among the authoritative SIG tables.
    try:
        from . import mesh_ids as _mesh
        if uuid in _mesh.MESH_MODEL_UUIDS:
            return _mesh.MESH_MODEL_UUIDS[uuid]
    except Exception:  # noqa: BLE001 - mesh table optional/generated
        pass

    # Final, opt-in, NON-authoritative tier (todo Item D): the observed-UUID
    # catalogue. Only consulted when explicitly requested so default output stays
    # "Unknown". Returns a clearly-marked hint, never a bare authoritative name.
    if allow_observed and isinstance(uuid, str):
        try:
            from bleep.core.observations import get_observed_uuid_names
            observed = get_observed_uuid_names(uuid)
            if observed:
                return "Unknown (seen as: " + ", ".join(observed) + ")"
        except Exception:  # noqa: BLE001 - DB optional/unavailable
            pass

    return "Unknown"


def text_to_ascii_array(text):
    ascii_values = []
    for character in text:
        ascii_values.append(ord(character))
    return ascii_values


def print_properties(props):
    # dbus.Dictionary({dbus.String('SupportedInstances'): dbus.Byte(4, variant_level=1), dbus.String('ActiveInstances'): dbus.Byte(1, variant_level=1)}, signature=dbus.Signature('sv'))
    for key in props:
        print(key + "=" + str(props[key]))


def handle_int_to_hex(handle: int) -> str:
    """Convert an integer handle value to a hex string representation.
    
    Parameters
    ----------
    handle : int
        The handle value as an integer
        
    Returns
    -------
    str
        The handle value as a hex string (e.g., "0x002A")
    """
    return f"0x{handle:04X}"


def handle_hex_to_int(handle_hex: str) -> int:
    """Convert a hex string handle representation to an integer.
    
    Parameters
    ----------
    handle_hex : str
        The handle value as a hex string (e.g., "0x002A" or "0x2A")
        
    Returns
    -------
    int
        The handle value as an integer
    """
    if isinstance(handle_hex, int):
        return handle_hex
    
    if handle_hex.startswith("0x"):
        return int(handle_hex, 16)
    
    try:
        return int(handle_hex)
    except ValueError:
        # Try as hex without 0x prefix
        return int(handle_hex, 16)
