"""
Core constants for BLEEP.

This module provides centralized constants for Bluetooth operations, organized by category.
All constants are imported directly from the original monolith for compatibility.
"""

# D-Bus Core Constants
DBUS_PROPERTIES = "org.freedesktop.DBus.Properties"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
INTROSPECT_INTERFACE = "org.freedesktop.DBus.Introspectable"

# BlueZ Core Constants
ADAPTER_NAME = "hci0"
BLUEZ_SERVICE_NAME = "org.bluez"
BLUEZ_NAMESPACE = "/org/bluez/"

# BlueZ Interface Constants
ADAPTER_INTERFACE = BLUEZ_SERVICE_NAME + ".Adapter1"
DEVICE_INTERFACE = BLUEZ_SERVICE_NAME + ".Device1"

# GATT Interface Constants
GATT_MANAGER_INTERFACE = BLUEZ_SERVICE_NAME + ".GattManager1"
GATT_SERVICE_INTERFACE = BLUEZ_SERVICE_NAME + ".GattService1"
GATT_CHARACTERISTIC_INTERFACE = BLUEZ_SERVICE_NAME + ".GattCharacteristic1"
GATT_DESCRIPTOR_INTERFACE = BLUEZ_SERVICE_NAME + ".GattDescriptor1"

# Advertisement Interface Constants
ADVERTISEMENT_INTERFACE = BLUEZ_SERVICE_NAME + ".LEAdvertisement1"
ADVERTISING_MANAGER_INTERFACE = BLUEZ_SERVICE_NAME + ".LEAdvertisingManager1"

# Media Interface Constants
MEDIA_CONTROL_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaControl1"
MEDIA_ENDPOINT_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaEndpoint1"
MEDIA_TRANSPORT_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaTransport1"
MEDIA_PLAYER_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaPlayer1"

# Agent/Mesh Constants
AGENT_NAMESPACE = "/test/agent"
MESH_AGENT_NAMESPACE = "/mesh/test/agent"
AGENT_INTERFACE = BLUEZ_SERVICE_NAME + ".mesh.ProvisioningAgent1"
MESH_AGENT_INTERFACE = BLUEZ_SERVICE_NAME + ".mesh.ProvisioningAgent1"
MANAGER_INTERFACE = BLUEZ_SERVICE_NAME + ".AgentManager1"

# Result/Error Codes
RESULT_OK = 0
RESULT_ERR = 1
RESULT_ERR_NOT_CONNECTED = 2
RESULT_ERR_NOT_SUPPORTED = 3
RESULT_ERR_SERVICES_NOT_RESOLVED = 4
RESULT_ERR_WRONG_STATE = 5
RESULT_ERR_ACCESS_DENIED = 6
RESULT_EXCEPTION = 7
RESULT_ERR_BAD_ARGS = 8
RESULT_ERR_NOT_FOUND = 9
RESULT_ERR_METHOD_SIGNATURE_NOT_EXIST = 10
RESULT_ERR_NO_DEVICES_FOUND = 11
RESULT_ERR_NO_BR_CONNECT = 12
RESULT_ERR_READ_NOT_PERMITTED = 13
RESULT_ERR_NO_REPLY = 14
RESULT_ERR_DEVICE_FORGOTTEN = 15
RESULT_ERR_ACTION_IN_PROGRESS = 16
RESULT_ERR_UNKNOWN_SERVCE = 17
RESULT_ERR_UNKNOWN_OBJECT = 18
RESULT_ERR_REMOTE_DISCONNECT = 19
RESULT_ERR_UNKNOWN_CONNECT_FAILURE = 20
RESULT_ERR_METHOD_CALL_FAIL = 21
RESULT_ERR_NOT_PERMITTED = 22  # Operation not permitted  ## Check validity of these two values
RESULT_ERR_NOT_AUTHORIZED = 23  # Authorization failure

# Granular GATT permission errors (Phase-5 classification)
# BlueZ collapses these at DBus level into NotPermitted but we expose them
# separately after parsing the underlying ATT opcode where possible.
RESULT_ERR_WRITE_NOT_PERMITTED = 24
RESULT_ERR_NOTIFY_NOT_PERMITTED = 25
RESULT_ERR_INDICATE_NOT_PERMITTED = 26

# Base UUID Constants
BASE_UUID__BLUETOOTH = "00000000-0000-1000-8000-00805F9B34F"

# GATT Property Constants
GATT__SERVICE__PROPERTIES = [
    "UUID",
    "Primary",
    "Device",
    "Includes",
    "Handle",
    "Characteristics",
]
GATT__CHARACTERISTIC__PROPERTIES = [
    "UUID",
    "Service",
    "Value",
    "WriteAcquired",
    "NotifyAcquired",
    "Notifying",
    "Flags",
    "Handle",
    "MTU",
]
GATT__DESCRIPTOR__PROPERTIES = ["UUID", "Characteristic", "Value", "Flags", "Handle"]

# Device Interface Constants
BLE__DEVICE_INTERFACES__LIST = [
    "org.bluez.Device1",
    "org.bluez.MediaControl1",
    "org.bluez.Battery1",
    "org.bluez.MediaEndpoint1",
    "org.bluez.MediaTransport1",
]

# Formatting Constants
PRETTY_PRINT__GATT__FORMAT_LEN = 7  # Used for pretty printing GATT data

# Known Device Constants
BLE_CTF_ADDR = "CC:50:E3:B6:BC:A6"

# Introspection Constants
INTROSPECT_SERVICE_STRING = "service"
INTROSPECT_CHARACTERISTIC_STRING = "char"
INTROSPECT_DESCRIPTOR_STRING = "desc"

# UUID Mapping
UUID_NAMES = {
    "00001801-0000-1000-8000-00805f9b34fb": "Generic Attribute Service",
    "0000180a-0000-1000-8000-00805f9b34fb": "Device Information Service",
    "e95d93b0-251d-470a-a062-fa1922dfa9a8": "DFU Control Service",
    "e95d93af-251d-470a-a062-fa1922dfa9a8": "Event Service",
    "e95d9882-251d-470a-a062-fa1922dfa9a8": "Button Service",
    "e95d6100-251d-470a-a062-fa1922dfa9a8": "Temperature Service",
    "e95dd91d-251d-470a-a062-fa1922dfa9a8": "LED Service",
    "00002a05-0000-1000-8000-00805f9b34fb": "Service Changed",
    "e95d93b1-251d-470a-a062-fa1922dfa9a8": "DFU Control",
    "00002a24-0000-1000-8000-00805f9b34fb": "Model Number String",
    "00002a25-0000-1000-8000-00805f9b34fb": "Serial Number String",
    "00002a26-0000-1000-8000-00805f9b34fb": "Firmware Revision String",
    "e95d9775-251d-470a-a062-fa1922dfa9a8": "micro:bit Event",
    "e95d5404-251d-470a-a062-fa1922dfa9a8": "Client Event",
    "e95d23c4-251d-470a-a062-fa1922dfa9a8": "Client Requirements",
    "e95db84c-251d-470a-a062-fa1922dfa9a8": "micro:bit Requirements",
    "e95dda90-251d-470a-a062-fa1922dfa9a8": "Button A State",
    "e95dda91-251d-470a-a062-fa1922dfa9a8": "Button B State",
    "e95d9250-251d-470a-a062-fa1922dfa9a8": "Temperature",
    "e95d93ee-251d-470a-a062-fa1922dfa9a8": "LED Text",
    "00002902-0000-1000-8000-00805f9b34fb": "Client Characteristic Configuration",
    # BLE CTF UUIDs
    "000000ff-0000-1000-8000-00805f9b34fb": "BLE CTF Flags Service",
    "0000ff01-0000-1000-8000-00805f9b34fb": "BLE CTF Score",
    "0000ff02-0000-1000-8000-00805f9b34fb": "BLE CTF Flag Submission",
    "0000ff03-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #002",
    "0000ff04-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #003",
    "0000ff05-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #005",
    "0000ff06-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #006",
    "0000ff07-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #007",
    "0000ff08-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #008",
    "0000ff0a-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #009",
    "0000ff0b-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #010",
    "0000ff0c-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #011",
    "0000ff0d-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #012 + #014",
    "0000ff0f-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #013",
    "0000ff12-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #015",
    "0000ff10-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #016",
    "0000ff14-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #017",
    "0000ff15-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #018",
    "0000ff16-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #019",
    "0000ff17-0000-1000-8000-00805f9b34fb": "BLE CTF Flag #020",
    # BW-16 UUIDs
    "0000a7e6-0000-1000-8000-00805f9b34fb": "RealTek BW-16 System Status",
    "0000a7e7-0000-1000-8000-00805f9b34fb": "RealTek BW-16 Alert Status",
    # Advanced Audio Distribution Profile (A2DP)
    "0000110a-0000-1000-8000-00805f9b34fb": "Advanced Audio Distribution Profile (A2DP) - A2DP Source",
    "0000110b-0000-1000-8000-00805f9b34fb": "Advanced Audio Distribution Profile (A2DP) - A2DP Sink",
}

# Common Service/Characteristic UUIDs
DEVICE_INF_SVC_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
TEMPERATURE_SVC_UUID = "e95d6100-251d-470a-a062-fa1922dfa9a8"
TEMPERATURE_CHR_UUID = "e95d9250-251d-470a-a062-fa1922dfa9a8"
LED_SVC_UUID = "e95dd91d-251d-470a-a062-fa1922dfa9a8"
LED_TEXT_CHR_UUID = "e95d93ee-251d-470a-a062-fa1922dfa9a8"

# Arduino BLE Constants
ARDUINO_BLE__BLE_UUID__MASK = "XXXXXXXX-0000-1000-8000-00805f9b34fb"
