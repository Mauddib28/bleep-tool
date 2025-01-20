#!/usr/bin/python3

# Last Updated:     Paul A. Wortman     -       2024/08/29

# Incorporated BLE CTF known flags
# Included [Mesh] Agent path and interfaces

ADAPTER_NAME = "hci0"

BLUEZ_SERVICE_NAME = "org.bluez"
BLUEZ_NAMESPACE = "/org/bluez/"
DBUS_PROPERTIES="org.freedesktop.DBus.Properties"
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
AGENT_NAMESPACE = "/test/agent"             # Agent Path (from simple-agent)
MESH_AGENT_NAMESPACE = "/mesh/test/agent"        # Agent Path (from agent.py)

ADAPTER_INTERFACE = BLUEZ_SERVICE_NAME + ".Adapter1"
DEVICE_INTERFACE = BLUEZ_SERVICE_NAME + ".Device1"
GATT_MANAGER_INTERFACE = BLUEZ_SERVICE_NAME + ".GattManager1"
GATT_SERVICE_INTERFACE = BLUEZ_SERVICE_NAME + ".GattService1"
GATT_CHARACTERISTIC_INTERFACE = BLUEZ_SERVICE_NAME + ".GattCharacteristic1"
GATT_DESCRIPTOR_INTERFACE = BLUEZ_SERVICE_NAME + ".GattDescriptor1"
ADVERTISEMENT_INTERFACE = BLUEZ_SERVICE_NAME + ".LEAdvertisement1"
ADVERTISING_MANAGER_INTERFACE = BLUEZ_SERVICE_NAME + ".LEAdvertisingManager1"
AGENT_INTERFACE = BLUEZ_SERVICE_NAME + ".mesh.ProvisioningAgent1"
MESH_AGENT_INTERFACE = BLUEZ_SERVICE_NAME + ".mesh.ProvisioningAgent1"
MANAGER_INTERFACE = BLUEZ_SERVICE_NAME + ".AgentManager1"

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
# Added error codes for error handling function
RESULT_ERR_METHOD_SIGNATURE_NOT_EXIST = 10      # Maybe too specific, use the RESULT_ERR_NOT_FOUND instead?
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

# Base UUID
BASE_UUID__BLUETOOTH = "00000000-0000-1000-8000-00805F9B34F"
# Nota Bene: It appears that every "short" UUID (i.g. 0xWXYZ) is the value expected to be seen in the 3rd and 4th octets
#   - Ex:       0000WXYZ-0000-1000-8000-00805F9B34F
#   -> Note: The rest of the UUID is assumed to be standardized via the OEM/implementer of a device

UUID_NAMES = {
    "00001801-0000-1000-8000-00805f9b34fb" : "Generic Attribute Service",
    "0000180a-0000-1000-8000-00805f9b34fb" : "Device Information Service",
    "e95d93b0-251d-470a-a062-fa1922dfa9a8" : "DFU Control Service",
    "e95d93af-251d-470a-a062-fa1922dfa9a8" : "Event Service",
    "e95d9882-251d-470a-a062-fa1922dfa9a8" : "Button Service",
    "e95d6100-251d-470a-a062-fa1922dfa9a8" : "Temperature Service",
    "e95dd91d-251d-470a-a062-fa1922dfa9a8" : "LED Service",
    "00002a05-0000-1000-8000-00805f9b34fb" : "Service Changed",
    "e95d93b1-251d-470a-a062-fa1922dfa9a8" : "DFU Control",
    "00002a05-0000-1000-8000-00805f9b34fb" : "Service Changed",
    "00002a24-0000-1000-8000-00805f9b34fb" : "Model Number String",
    "00002a25-0000-1000-8000-00805f9b34fb" : "Serial Number String",
    "00002a26-0000-1000-8000-00805f9b34fb" : "Firmware Revision String",
    "e95d9775-251d-470a-a062-fa1922dfa9a8" : "micro:bit Event",
    "e95d5404-251d-470a-a062-fa1922dfa9a8" : "Client Event",
    "e95d23c4-251d-470a-a062-fa1922dfa9a8" : "Client Requirements",
    "e95db84c-251d-470a-a062-fa1922dfa9a8" : "micro:bit Requirements",
    "e95dda90-251d-470a-a062-fa1922dfa9a8" : "Button A State",
    "e95dda91-251d-470a-a062-fa1922dfa9a8" : "Button B State",
    "e95d9250-251d-470a-a062-fa1922dfa9a8" : "Temperature",
    "e95d93ee-251d-470a-a062-fa1922dfa9a8" : "LED Text",
    "00002902-0000-1000-8000-00805f9b34fb" : "Client Characteristic Configuration",
    ## BLE CTF UUIDs
    "000000ff-0000-1000-8000-00805f9b34fb" : "BLE CTF Flags Service",
    "0000ff01-0000-1000-8000-00805f9b34fb" : "BLE CTF Score",
    "0000ff02-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag Submission",
    "0000ff03-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #002",
    "0000ff04-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #003",
    #"" : "BLE CTF Flag #004",
    "0000ff05-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #005",
    "0000ff06-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #006",
    "0000ff07-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #007",
    "0000ff08-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #008",
    "0000ff0a-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #009",
    "0000ff0b-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #010",
    "0000ff0c-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #011",
    "0000ff0d-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #012 + #014",
    "0000ff0f-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #013",
    #"0000ff0d-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #014",
    "0000ff12-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #015",
    "0000ff10-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #016",
    "0000ff14-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #017",
    "0000ff15-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #018",
    "0000ff16-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #019",
    "0000ff17-0000-1000-8000-00805f9b34fb" : "BLE CTF Flag #020",
    ## BW-16 UUIDs
    "0000a7e6-0000-1000-8000-00805f9b34fb" : "RealTek BW-16 System Status",
    "0000a7e7-0000-1000-8000-00805f9b34fb" : "RealTek BW-16 Alert Status"
    ## Encountered UUIDs / From Spec
}    

DEVICE_INF_SVC_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_UUID    = "00002a24-0000-1000-8000-00805f9b34fb"

TEMPERATURE_SVC_UUID = "e95d6100-251d-470a-a062-fa1922dfa9a8"
TEMPERATURE_CHR_UUID = "e95d9250-251d-470a-a062-fa1922dfa9a8"

LED_SVC_UUID = "e95dd91d-251d-470a-a062-fa1922dfa9a8"
LED_TEXT_CHR_UUID = "e95d93ee-251d-470a-a062-fa1922dfa9a8"

## Added Constants from Bluetooth Research
BLE_CTF_ADDR = 'CC:50:E3:B6:BC:A6'
INTROSPECT_INTERFACE = 'org.freedesktop.DBus.Introspectable'
INTROSPECT_SERVICE_STRING = 'service'
INTROSPECT_CHARACTERISTIC_STRING = 'char'
INTROSPECT_DESCRIPTOR_STRING = 'desc'

# Known Bluetooth Low Energy IDs
ARDUINO_BLE__BLE_UUID__MASK = "XXXXXXXX-0000-1000-8000-00805f9b34fb"

# Details for GATT Structure Properties
GATT__SERVICE__PROPERTIES = ["UUID", "Primary", "Device", "Includes", "Handle", "Characteristics"]
GATT__CHARACTERISTIC__PROPERTIES = ["UUID", "Service", "Value", "WriteAcquired", "NotifyAcquired", "Notifying", "Flags", "Handle", "MTU"]
GATT__DESCRIPTOR__PROPERTIES = ["UUID", "Characteristic", "Value", "Flags", "Handle"]
