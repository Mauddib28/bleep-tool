"""
Core constants for BLEEP.

This module provides centralized constants for Bluetooth operations, organized by category.
All constants are imported directly from the original monolith for compatibility.
"""

from __future__ import annotations
from typing import Optional

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
LE_ADVERTISEMENT_BASE_PATH = "/org/bluez/bleep/advertisement"

# Advertisement Monitor Interface Constants (BZ-11/12)
ADV_MONITOR_INTERFACE = BLUEZ_SERVICE_NAME + ".AdvertisementMonitor1"
ADV_MONITOR_MANAGER_INTERFACE = BLUEZ_SERVICE_NAME + ".AdvertisementMonitorManager1"
ADV_MONITOR_APP_BASE_PATH = "/org/bluez/bleep/adv_monitor_app"

# Media Interface Constants
MEDIA_CONTROL_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaControl1"
MEDIA_ENDPOINT_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaEndpoint1"
MEDIA_TRANSPORT_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaTransport1"
MEDIA_PLAYER_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaPlayer1"
MEDIA_INTERFACE = BLUEZ_SERVICE_NAME + ".Media1"  # Adapter-level service
MEDIA_FOLDER_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaFolder1"
MEDIA_ITEM_INTERFACE = BLUEZ_SERVICE_NAME + ".MediaItem1"

# Agent/Mesh Constants
AGENT_NAMESPACE = "/test/agent"
MESH_AGENT_NAMESPACE = "/mesh/test/agent"
# AGENT_INTERFACE = BLUEZ_SERVICE_NAME + ".mesh.ProvisioningAgent1"  # WRONG: This is for mesh provisioning, not standard pairing
AGENT_INTERFACE = BLUEZ_SERVICE_NAME + ".Agent1"  # Correct: Standard BlueZ pairing agent interface (org.bluez.Agent1)
MESH_AGENT_INTERFACE = BLUEZ_SERVICE_NAME + ".mesh.ProvisioningAgent1"
MANAGER_INTERFACE = BLUEZ_SERVICE_NAME + ".AgentManager1"

# BlueZ Profile Manager / Profile interfaces (system bus, per org.bluez.ProfileManager.rst)
PROFILE_MANAGER_INTERFACE = BLUEZ_SERVICE_NAME + ".ProfileManager1"
PROFILE_INTERFACE = BLUEZ_SERVICE_NAME + ".Profile1"

# ============================================================================
# OBEX Interface Constants (BlueZ obexd – session bus)
# ============================================================================
# obexd runs on the session D-Bus under "org.bluez.obex".
# Reference: BlueZ doc/org.bluez.obex.*.rst

OBEX_SERVICE = "org.bluez.obex"
OBEX_ROOT_PATH = "/org/bluez/obex"
OBEX_CLIENT_INTERFACE = OBEX_SERVICE + ".Client1"
OBEX_SESSION_INTERFACE = OBEX_SERVICE + ".Session1"
OBEX_TRANSFER_INTERFACE = OBEX_SERVICE + ".Transfer1"
OBEX_AGENT_INTERFACE = OBEX_SERVICE + ".Agent1"
OBEX_AGENT_MANAGER_INTERFACE = OBEX_SERVICE + ".AgentManager1"

# OBEX profile-specific interfaces
OBEX_PBAP_INTERFACE = OBEX_SERVICE + ".PhonebookAccess1"
OBEX_OPP_INTERFACE = OBEX_SERVICE + ".ObjectPush1"
OBEX_MAP_INTERFACE = OBEX_SERVICE + ".MessageAccess1"
OBEX_MAP_MESSAGE_INTERFACE = OBEX_SERVICE + ".Message1"
OBEX_FTP_INTERFACE = OBEX_SERVICE + ".FileTransfer1"
OBEX_SYNC_INTERFACE = OBEX_SERVICE + ".Synchronization1"
OBEX_IMAGE_INTERFACE = OBEX_SERVICE + ".Image1"  # [experimental]

# ============================================================================
# Classic Profile UUIDs (Bluetooth SIG Assigned Numbers)
# ============================================================================
# 16-bit short forms and 128-bit canonical forms for Classic service detection.
# Full list: bleep.bt_ref.uuids.SPEC_UUID_NAMES__SERV_CLASS

# SPP (Serial Port Profile)
SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"
SPP_UUID_SHORT = "0x1101"

# OPP (Object Push Profile)
OPP_UUID = "00001105-0000-1000-8000-00805f9b34fb"
OPP_UUID_SHORT = "0x1105"

# PBAP (Phonebook Access Profile – PSE)
PBAP_PSE_UUID = "0000112f-0000-1000-8000-00805f9b34fb"
PBAP_PSE_UUID_SHORT = "0x112f"

# FTP (OBEX File Transfer Profile)
FTP_UUID = "00001106-0000-1000-8000-00805f9b34fb"
FTP_UUID_SHORT = "0x1106"

# MAP (Message Access Profile)
MAP_MSE_UUID = "00001132-0000-1000-8000-00805f9b34fb"
MAP_MSE_UUID_SHORT = "0x1132"
MAP_MNS_UUID = "00001133-0000-1000-8000-00805f9b34fb"
MAP_MNS_UUID_SHORT = "0x1133"
MAP_UUID = "00001134-0000-1000-8000-00805f9b34fb"
MAP_UUID_SHORT = "0x1134"

# MAP SDP attribute IDs (Bluetooth Assigned Numbers + MAP v1.4.3 spec)
MAP_SDP_ATTR_MAS_INSTANCE_ID = 0x0315
MAP_SDP_ATTR_SUPPORTED_MESSAGE_TYPES = 0x0316
MAP_SDP_ATTR_SUPPORTED_FEATURES = 0x0317  # MapSupportedFeatures bitmask

# MapSupportedFeatures bitmask (MAP v1.4.3, Section 7.1.1 / 7.1.2)
# Bits defined for both MCE (client) and MSE (server) roles.
MAP_FEATURE_NOTIFICATION_REGISTRATION = 0x00000001  # Bit 0
MAP_FEATURE_NOTIFICATION = 0x00000002               # Bit 1
MAP_FEATURE_BROWSING = 0x00000004                    # Bit 2
MAP_FEATURE_UPLOADING = 0x00000008                   # Bit 3
MAP_FEATURE_DELETE = 0x00000010                      # Bit 4
MAP_FEATURE_INSTANCE_INFO = 0x00000020               # Bit 5
MAP_FEATURE_EXTENDED_EVENT_REPORT_1_1 = 0x00000040   # Bit 6
MAP_FEATURE_EVENT_REPORT_1_2 = 0x00000080            # Bit 7
MAP_FEATURE_MESSAGE_FORMAT_1_1 = 0x00000100          # Bit 8
MAP_FEATURE_MESSAGES_LISTING_FORMAT_1_1 = 0x00000200 # Bit 9
MAP_FEATURE_PERSISTENT_MSG_HANDLES = 0x00000400      # Bit 10
MAP_FEATURE_DATABASE_ID = 0x00000800                 # Bit 11
MAP_FEATURE_FOLDER_VERSION_COUNTER = 0x00001000      # Bit 12
MAP_FEATURE_CONVERSATION_VERSION_COUNTER = 0x00002000  # Bit 13
MAP_FEATURE_PARTICIPANT_PRESENCE_CHANGE = 0x00004000   # Bit 14
MAP_FEATURE_PARTICIPANT_CHAT_STATE_CHANGE = 0x00008000 # Bit 15
MAP_FEATURE_PBAP_CONTACT_CROSS_REF = 0x00010000       # Bit 16
MAP_FEATURE_NOTIFICATION_FILTERING = 0x00020000        # Bit 17
MAP_FEATURE_UTC_OFFSET_TIMESTAMP = 0x00040000          # Bit 18
MAP_FEATURE_MAPSUPPORTEDFEATURES_IN_CONNECT = 0x00080000  # Bit 19
MAP_FEATURE_CONVERSATION_LISTING = 0x00100000          # Bit 20
MAP_FEATURE_OWNER_STATUS = 0x00200000                  # Bit 21
MAP_FEATURE_MESSAGE_FORWARDING = 0x00400000            # Bit 22

MAP_FEATURE_NAMES = {
    MAP_FEATURE_NOTIFICATION_REGISTRATION: "NotificationRegistration",
    MAP_FEATURE_NOTIFICATION: "Notification",
    MAP_FEATURE_BROWSING: "Browsing",
    MAP_FEATURE_UPLOADING: "Uploading",
    MAP_FEATURE_DELETE: "Delete",
    MAP_FEATURE_INSTANCE_INFO: "InstanceInformation",
    MAP_FEATURE_EXTENDED_EVENT_REPORT_1_1: "ExtendedEventReport1.1",
    MAP_FEATURE_EVENT_REPORT_1_2: "EventReport1.2",
    MAP_FEATURE_MESSAGE_FORMAT_1_1: "MessageFormat1.1",
    MAP_FEATURE_MESSAGES_LISTING_FORMAT_1_1: "MessagesListingFormat1.1",
    MAP_FEATURE_PERSISTENT_MSG_HANDLES: "PersistentMessageHandles",
    MAP_FEATURE_DATABASE_ID: "DatabaseIdentifier",
    MAP_FEATURE_FOLDER_VERSION_COUNTER: "FolderVersionCounter",
    MAP_FEATURE_CONVERSATION_VERSION_COUNTER: "ConversationVersionCounter",
    MAP_FEATURE_PARTICIPANT_PRESENCE_CHANGE: "ParticipantPresenceChange",
    MAP_FEATURE_PARTICIPANT_CHAT_STATE_CHANGE: "ParticipantChatStateChange",
    MAP_FEATURE_PBAP_CONTACT_CROSS_REF: "PBAPContactCrossReference",
    MAP_FEATURE_NOTIFICATION_FILTERING: "NotificationFiltering",
    MAP_FEATURE_UTC_OFFSET_TIMESTAMP: "UTCOffsetTimestamp",
    MAP_FEATURE_MAPSUPPORTEDFEATURES_IN_CONNECT: "MapSupportedFeaturesInConnect",
    MAP_FEATURE_CONVERSATION_LISTING: "ConversationListing",
    MAP_FEATURE_OWNER_STATUS: "OwnerStatus",
    MAP_FEATURE_MESSAGE_FORWARDING: "MessageForwarding",
}

# MAP supported message type bits (SDP attribute 0x0316)
MAP_MSG_TYPE_EMAIL = 0x01
MAP_MSG_TYPE_SMS_GSM = 0x02
MAP_MSG_TYPE_SMS_CDMA = 0x04
MAP_MSG_TYPE_MMS = 0x08
MAP_MSG_TYPE_IM = 0x10

MAP_MSG_TYPE_NAMES = {
    MAP_MSG_TYPE_EMAIL: "EMAIL",
    MAP_MSG_TYPE_SMS_GSM: "SMS_GSM",
    MAP_MSG_TYPE_SMS_CDMA: "SMS_CDMA",
    MAP_MSG_TYPE_MMS: "MMS",
    MAP_MSG_TYPE_IM: "IM",
}


def decode_map_supported_features(bitmask: int) -> list:
    """Decode a MapSupportedFeatures bitmask into human-readable feature names."""
    return [name for bit, name in MAP_FEATURE_NAMES.items() if bitmask & bit]


def decode_map_message_types(bitmask: int) -> list:
    """Decode a MAP supported message types bitmask into names."""
    return [name for bit, name in MAP_MSG_TYPE_NAMES.items() if bitmask & bit]

# SYNC (IrMC Synchronization)
SYNC_UUID = "00001104-0000-1000-8000-00805f9b34fb"
SYNC_UUID_SHORT = "0x1104"
SYNC_CMD_UUID = "00001107-0000-1000-8000-00805f9b34fb"
SYNC_CMD_UUID_SHORT = "0x1107"

# BIP (Basic Imaging Profile) — [experimental] in BlueZ
BIP_UUID = "0000111a-0000-1000-8000-00805f9b34fb"
BIP_UUID_SHORT = "0x111a"
BIP_RESPONDER_UUID = "0000111b-0000-1000-8000-00805f9b34fb"
BIP_RESPONDER_UUID_SHORT = "0x111b"

# PAN (Personal Area Networking)
PAN_PANU_UUID = "00001115-0000-1000-8000-00805f9b34fb"
PAN_PANU_UUID_SHORT = "0x1115"
PAN_NAP_UUID = "00001116-0000-1000-8000-00805f9b34fb"
PAN_NAP_UUID_SHORT = "0x1116"
PAN_GN_UUID = "00001117-0000-1000-8000-00805f9b34fb"
PAN_GN_UUID_SHORT = "0x1117"

# BlueZ PAN D-Bus interfaces (system bus, per org.bluez.Network.rst / NetworkServer.rst)
NETWORK_INTERFACE = BLUEZ_SERVICE_NAME + ".Network1"
NETWORK_SERVER_INTERFACE = BLUEZ_SERVICE_NAME + ".NetworkServer1"

# Aggregate set for classic OBEX profile detection
OBEX_PROFILE_UUIDS = frozenset({
    OPP_UUID, FTP_UUID, PBAP_PSE_UUID, MAP_MSE_UUID, MAP_UUID,
})

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
RESULT_ERR_TIMEOUT = 27  # Explicit timeout error (not from BlueZ, used by timeout_manager)

# BlueZ-specific connection error codes (from workDir/BlueZDocs/errors.txt)
RESULT_ERR_PROFILE_UNAVAILABLE = 28       # BR/EDR: no connectable services / target service
RESULT_ERR_PAGE_TIMEOUT = 29              # BR/EDR: page timeout (EHOSTDOWN)
RESULT_ERR_CONNECTION_REFUSED = 30        # Remote refused (security, resources, address type)
RESULT_ERR_CONNECTION_LIMIT = 31          # Concurrent connection limit (EMLINK)
RESULT_ERR_ALREADY_CONNECTED = 32         # Profile or ACL already connected (EALREADY/EISCONN)
RESULT_ERR_AUTH_CANCELED = 33             # Pair() canceled by user or agent
RESULT_ERR_AUTH_REJECTED = 34             # Pair() rejected by remote device
RESULT_ERR_AUTH_TIMEOUT = 35              # Pair() timed out
RESULT_ERR_CONNECTION_ABORTED_REMOTE = 36 # Remote terminated (low resources / power off)
RESULT_ERR_CONNECTION_ABORTED_LOCAL = 37  # Local host aborted
RESULT_ERR_PROTOCOL_ERROR = 38            # LMP or link-layer protocol error (EPROTO)
RESULT_ERR_SOCKET_ERROR = 39              # BT IO socket creation/connect failed (EIO)
RESULT_ERR_NOT_POWERED = 40              # Adapter not powered (EHOSTUNREACH)

# ---------------------------------------------------------------------------
# Legacy PIN codes (pre-BT 2.1, RequestPinCode agent method).
# Format: string, 1–16 characters, ALPHANUMERIC (BlueZ rejects len<1 or len>16).
# Grouped by length, ordered by empirical frequency within each group.
# ---------------------------------------------------------------------------
COMMON_PINS_4 = ["0000", "1234", "9999", "1111", "0001", "1010", "2468"]
COMMON_PINS_6 = ["000000", "123456", "888888", "098765"]
COMMON_PINS_ALPHA = ["BlueZ", "BRCM", "default"]
COMMON_PINS = COMMON_PINS_4 + COMMON_PINS_6 + COMMON_PINS_ALPHA

# ---------------------------------------------------------------------------
# SSP Passkeys (BT 2.1+, RequestPasskey agent method).
# Format: uint32, 0–999999.  Always displayed as 6-digit zero-padded.
# NOTE: SSP normally generates a RANDOM passkey per pairing attempt;
# brute-forcing random passkeys is infeasible (1-in-1,000,000 per try).
# This list is only useful for the rare case of devices with a FIXED passkey
# (some embedded / industrial hardware).
# ---------------------------------------------------------------------------
COMMON_PASSKEYS = [0, 1234, 123456, 9999, 1111]

# ---------------------------------------------------------------------------
# IO Capability strings for BlueZ AgentManager1.RegisterAgent().
# Empty string "" falls back to KeyboardDisplay in bluetoothd.
# IMPORTANT: For BR/EDR, the kernel converts KeyboardDisplay (0x04) to
# DisplayYesNo (0x01) — they are functionally identical on BR/EDR.
# KeyboardDisplay is SMP-specific (LE).
# ---------------------------------------------------------------------------
AGENT_CAPABILITIES = [
    "NoInputNoOutput",
    "DisplayOnly",
    "DisplayYesNo",
    "KeyboardOnly",
    "KeyboardDisplay",
]

# Base UUID Constants — the canonical BT SIG base UUID (Core Spec v5.4, Vol 3, Part B §2.5.1).
# All short-form (16-bit / 32-bit) UUIDs expand into this 128-bit template.
BT_SIG_BASE_UUID = "00000000-0000-1000-8000-00805f9b34fb"
BT_SIG_BASE_UUID_NODASH = BT_SIG_BASE_UUID.replace("-", "").lower()

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
    # ESP SSP (Custom UUID - not in Bluetooth SIG specifications)
    "0000abf0-0000-1000-8000-00805f9b34fb": "ESP SSP",
    # Microsoft Nearby Sharing (proprietary CDPX protocol over BLE)
    "a82efa21-ae5c-3dde-9bbc-f16da7b16c5a": "Microsoft Nearby Sharing",
    # Samsung IcService_New (proprietary cross-device interconnect over RFCOMM)
    "a23d00bc-217c-123b-9c00-fc44577136ee": "Samsung IcService_New",
}

# Common Service/Characteristic UUIDs
DEVICE_INF_SVC_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
TEMPERATURE_SVC_UUID = "e95d6100-251d-470a-a062-fa1922dfa9a8"
TEMPERATURE_CHR_UUID = "e95d9250-251d-470a-a062-fa1922dfa9a8"
LED_SVC_UUID = "e95dd91d-251d-470a-a062-fa1922dfa9a8"
LED_TEXT_CHR_UUID = "e95d93ee-251d-470a-a062-fa1922dfa9a8"

# Service Discovery Server UUID (16-bit form for Classic device type classification)
SERVICE_DISCOVERY_SERVER_UUID_16 = "1000"

# Arduino BLE Constants
ARDUINO_BLE__BLE_UUID__MASK = "XXXXXXXX-0000-1000-8000-00805f9b34fb"

# ============================================================================
# Audio Profile UUIDs (Bluetooth SIG Assigned Numbers)
# ============================================================================
# These are commonly used audio profile UUIDs for A2DP, HFP, HSP
# Full comprehensive list available in bleep.bt_ref.uuids.SPEC_UUID_NAMES__SERV_CLASS
# Reference: Bluetooth SIG Assigned Numbers - Service Class UUIDs

# A2DP (Advanced Audio Distribution Profile)
A2DP_SOURCE_UUID = "0000110a-0000-1000-8000-00805f9b34fb"
A2DP_SINK_UUID = "0000110b-0000-1000-8000-00805f9b34fb"

# HFP (Hands-Free Profile)
HFP_HANDS_FREE_UUID = "0000111e-0000-1000-8000-00805f9b34fb"
HFP_AUDIO_GATEWAY_UUID = "0000111f-0000-1000-8000-00805f9b34fb"

# HSP (Headset Profile)
HSP_AUDIO_GATEWAY_UUID = "00001112-0000-1000-8000-00805f9b34fb"
HSP_HEADSET_UUID = "00001113-0000-1000-8000-00805f9b34fb"

# AVRCP (Audio/Video Remote Control Profile)
AVRCP_TARGET_UUID = "0000110c-0000-1000-8000-00805f9b34fb"
AVRCP_CONTROLLER_UUID = "0000110e-0000-1000-8000-00805f9b34fb"

# Aggregate set of UUIDs that indicate audio-capable devices.
# Used by Amusica scan filter to identify targets with audio services.
AUDIO_SERVICE_UUIDS = frozenset({
    A2DP_SOURCE_UUID,
    A2DP_SINK_UUID,
    HFP_HANDS_FREE_UUID,
    HFP_AUDIO_GATEWAY_UUID,
    HSP_AUDIO_GATEWAY_UUID,
    HSP_HEADSET_UUID,
    AVRCP_TARGET_UUID,
    AVRCP_CONTROLLER_UUID,
})

# Profile UUID to human-readable name mapping
# (Derived from SPEC_UUID_NAMES__SERV_CLASS for consistency)
AUDIO_PROFILE_NAMES = {
    A2DP_SOURCE_UUID: "A2DP Source",
    A2DP_SINK_UUID: "A2DP Sink",
    HFP_HANDS_FREE_UUID: "HFP Hands-Free",
    HFP_AUDIO_GATEWAY_UUID: "HFP Audio Gateway",
    HSP_AUDIO_GATEWAY_UUID: "HSP Audio Gateway",
    HSP_HEADSET_UUID: "HSP Headset",
    AVRCP_TARGET_UUID: "AVRCP Target",
    AVRCP_CONTROLLER_UUID: "AVRCP Controller",
}

# ============================================================================
# MediaEndpoint ↔ MediaTransport UUID Relationship
# ============================================================================
# In BlueZ, a MediaEndpoint1 interface represents the **remote** device's role
# (e.g. A2DP Sink = "this device can receive audio"), while the associated
# MediaTransport1 interface represents the **local** host's complementary role
# (e.g. A2DP Source = "the host sends audio via this file descriptor").
#
# The transport UUID is always derived from the local endpoint registered by
# the audio server (PulseAudio/PipeWire). Per the Bluetooth SIG AVDTP
# specification, local and remote endpoints must have complementary roles
# (Source ↔ Sink). BlueZ enforces this in avdtp.c:avdtp_find_remote_sep().
#
# This mapping is advisory — used for diagnostic logging and fallback
# transport discovery. BLEEP does not reject transports with unexpected UUIDs.
#
# Reference: BlueZ profiles/audio/transport.c get_uuid(),
#            BlueZ profiles/audio/avdtp.c avdtp_find_remote_sep()
PROFILE_UUID_COMPLEMENTS = {
    A2DP_SINK_UUID: A2DP_SOURCE_UUID,
    A2DP_SOURCE_UUID: A2DP_SINK_UUID,
    HFP_AUDIO_GATEWAY_UUID: HFP_HANDS_FREE_UUID,
    HFP_HANDS_FREE_UUID: HFP_AUDIO_GATEWAY_UUID,
    HSP_AUDIO_GATEWAY_UUID: HSP_HEADSET_UUID,
    HSP_HEADSET_UUID: HSP_AUDIO_GATEWAY_UUID,
    AVRCP_TARGET_UUID: AVRCP_CONTROLLER_UUID,
    AVRCP_CONTROLLER_UUID: AVRCP_TARGET_UUID,
}

# ============================================================================
# Audio Codec Constants (A2DP Codec IDs)
# ============================================================================
# Reference: A2DP Specification, BlueZ MediaEndpoint1 documentation
# Codec IDs are defined in A2DP specification section 4.3.2
# These constants represent the codec identifier byte used in A2DP configuration

SBC_CODEC_ID = 0x00
MP3_CODEC_ID = 0x01
AAC_CODEC_ID = 0x02
ATRAC_CODEC_ID = 0x03
APTX_CODEC_ID = 0x04
APTX_HD_CODEC_ID = 0x05
LC3_CODEC_ID = 0x06
VENDOR_SPECIFIC_CODEC_ID = 0xFF

# Codec ID to human-readable name mapping
CODEC_NAMES = {
    SBC_CODEC_ID: "SBC",
    MP3_CODEC_ID: "MP3",
    AAC_CODEC_ID: "AAC",
    ATRAC_CODEC_ID: "ATRAC",
    APTX_CODEC_ID: "AptX",
    APTX_HD_CODEC_ID: "AptX HD",
    LC3_CODEC_ID: "LC3",
    VENDOR_SPECIFIC_CODEC_ID: "Vendor Specific",
}


# ---------------------------------------------------------------------------
# SBC codec capabilities and default configuration for endpoint registration
# Values from A2DP specification section 4.3.2 and BlueZ simple-endpoint.
# ---------------------------------------------------------------------------

# Channel Modes: Mono DualChannel Stereo JointStereo
# Frequencies: 16kHz 32kHz 44.1kHz 48kHz
# Subbands: 4 8
# Blocks: 4 8 12 16
# Bitpool: 2-64
SBC_CAPABILITIES = bytes([0xFF, 0xFF, 0x02, 0x40])

# JointStereo 44.1kHz Subbands:8 Blocks:16 Bitpool:2-53
SBC_DEFAULT_CONFIGURATION = bytes([0x21, 0x15, 0x02, 0x35])


CODEC_NAME_TO_ID = {v.upper(): k for k, v in CODEC_NAMES.items()}


def codec_name_to_id(name: str) -> Optional[int]:
    """Map a codec name (e.g. 'SBC', 'AAC', 'MP3') to its numeric ID.

    Returns None if the name is not recognised.
    """
    return CODEC_NAME_TO_ID.get(name.upper())


def get_codec_name(codec_id: int) -> str:
    """
    Get human-readable codec name from codec ID.
    
    Parameters
    ----------
    codec_id : int
        Codec ID (e.g., SBC_CODEC_ID = 0x00)
    
    Returns
    -------
    str
        Codec name or "Unknown" if not recognized
    """
    return CODEC_NAMES.get(codec_id, "Unknown")


def get_profile_name(profile_uuid: str) -> str:
    """
    Get human-readable profile name from UUID.
    
    Parameters
    ----------
    profile_uuid : str
        Profile UUID (e.g., A2DP_SINK_UUID)
    
    Returns
    -------
    str
        Profile name or "Unknown Profile" if not recognized
    """
    return AUDIO_PROFILE_NAMES.get(profile_uuid.lower(), "Unknown Profile")
