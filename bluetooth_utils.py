#!/usr/bin/python3

# Updated 2024/10/09
#   - Expanded UUID identification to include UUIDs generated into the Bluetooth UUIDs file

# Imports
import dbus
import sys
from sys import stdin, stdout
sys.path.insert(0, '.')
import bluetooth_constants

# Variables
dbg = 0

# Attempt to Import the Bluetooth UUIDs file
try:
    import bluetooth_uuids
except Exception as e:
    print("[-] bluetooth_utils::Error Loading Bluetooth UUID Reference File")

def byteArrayToHexString(bytes):
    hex_string = ""
    for byte in bytes:
        hex_byte = '%02X' % byte
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
    elif isinstance(data, dbus.UInt16):
        data = int(data)
    elif isinstance(data, dbus.Byte):
        data = int(data)
    elif isinstance(data, dbus.Double):
        data = float(data)
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
    path = adapter_path + "/dev_" + bdaddr.replace(":","_")
    return path

def get_name_from_uuid(uuid):
    # Debugging Key Type used for UUID
    if dbg != 0:
        print("[*] bluetooth_utils::UUID passed as type [ {0} ]".format(type(uuid)))
        print("[*] bluetooth_utils::Searching for Known Name for UUID [ {0} ]".format(uuid))
    # Attempt to Get a Names from a UUID
    #try:
    # Search through the Bluetooth Constants file
    if uuid in bluetooth_constants.UUID_NAMES:
        return bluetooth_constants.UUID_NAMES[uuid]
    # Search through the Bluetooth UUIDs file's Services
    elif uuid in bluetooth_uuids.SPEC_UUID_NAMES__SERV:
        if dbg != 0:
            print("[+] bluetooth_utils::UUID [ {0} ] matches known Service UUID [ {1} ]".format(uuid, bluetooth_uuids.SPEC_UUID_NAMES__SERV[uuid]))
        return bluetooth_uuids.SPEC_UUID_NAMES__SERV[uuid]
    # Search through the Bluetooth UUIDs file's Characteristics
    elif uuid in bluetooth_uuids.SPEC_UUID_NAMES__CHAR:
        return bluetooth_uuids.SPEC_UUID_NAMES__CHAR[uuid]
    # Search through the Bluetooth UUIDs file's Descriptors
    elif uuid in bluetooth_uuids.SPEC_UUID_NAMES__DESC:
        return bluetooth_uuids.SPEC_UUID_NAMES__DESC[uuid]
    # Search through the Bluetooth UUIDs file's Members
    elif uuid in bluetooth_uuids.SPEC_UUID_NAMES__MEMB:
        return bluetooth_uuids.SPEC_UUID_NAMES__MEMB[uuid]
    # Search through the Bluetooth UUIDs file's SDOs
    elif uuid in bluetooth_uuids.SPEC_UUID_NAMES__SDO:
        return bluetooth_uuids.SPEC_UUID_NAMES__SDO[uuid]
    # Search through the Bluetooth UUIDs file's Service Class
    elif uuid in bluetooth_uuids.SPEC_UUID_NAMES__SERV_CLASS:
        return bluetooth_uuids.SPEC_UUID_NAMES__SERV_CLASS[uuid]
    # No idea what this UUID is
    else:
        return "Unknown"
    # In case of error throw error message and return Unknown
    #except Exception as e:
    #    print("[-] bluetooth_utils::Error attempting to retreive name from UUID\n\tException:\t{0}".format(e))
    #    return "Unknown"

def text_to_ascii_array(text):
    ascii_values = []
    for character in text:
        ascii_values.append(ord(character))
    return ascii_values

def print_properties(props):
    # dbus.Dictionary({dbus.String('SupportedInstances'): dbus.Byte(4, variant_level=1), dbus.String('ActiveInstances'): dbus.Byte(1, variant_level=1)}, signature=dbus.Signature('sv'))
    for key in props:
        print(key+"="+str(props[key]))
