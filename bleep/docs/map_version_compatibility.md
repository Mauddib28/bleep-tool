# MAP Version Compatibility and Feature Negotiation

## Overview

The Bluetooth Message Access Profile (MAP) has evolved through several
versions (1.0 through 1.4). Modern Android devices typically implement
MAP 1.2 or later as a MAP Server (MSE) and expect connecting clients (MCE)
to negotiate feature support via the `MapSupportedFeatures` bitmask.

BLEEP delegates MAP OBEX sessions to BlueZ's `obexd` daemon, which acts as a
MAP 1.0-level client. This creates a version mismatch when connecting to
modern devices.

## Android "Feature Downgrade" Alert

When a MAP client connects without including the `MapSupportedFeatures`
header in the OBEX Connect request, Android MAP-MSE implementations
(version 1.2+) detect this as an older client and display:

> **Remote Message Access Feature Downgrade**
> Re-pair for Message Access Version Compatibility

### Root cause

1. BlueZ `obexd` creates MAP sessions with `Target: "map"` only.
2. It does **not** include `MapSupportedFeatures` in the OBEX Connect
   Application Parameters header.
3. Android's `BluetoothMapMasInstance` compares the remote feature set
   (absent = 0x0) against its own and triggers the downgrade notification
   when a mismatch is detected.

### Impact on BLEEP

- The alert is cosmetic on the target device side. MAP operations
  (folder listing, message retrieval, push) still work under the
  downgraded MAP 1.0 feature set.
- Features requiring MAP >= 1.1 (extended event reports, message format
  v1.1, persistent message handles, conversation listing) are **not**
  available through `obexd`.

## SDP Attributes

BLEEP's SDP parser extracts three MAP-specific attributes from the remote
device's service records:

| Attribute ID | Name                       | Description                                       |
|-------------|----------------------------|----------------------------------------------------|
| 0x0315      | MAS Instance ID            | Identifies the MAS instance (0-255)                |
| 0x0316      | Supported Message Types    | Bitmask: EMAIL, SMS_GSM, SMS_CDMA, MMS, IM         |
| 0x0317      | MapSupportedFeatures       | 32-bit bitmask of supported MAP features            |

Use `cmapinfo` in debug mode to query and decode these attributes from a
connected Classic device.

## MapSupportedFeatures Bitmask

| Bit | Feature                          | MAP Version |
|-----|----------------------------------|-------------|
| 0   | Notification Registration        | 1.0         |
| 1   | Notification                     | 1.0         |
| 2   | Browsing                         | 1.0         |
| 3   | Uploading                        | 1.0         |
| 4   | Delete                           | 1.0         |
| 5   | Instance Information             | 1.0         |
| 6   | Extended Event Report 1.1        | 1.1         |
| 7   | Event Report 1.2                 | 1.2         |
| 8   | Message Format 1.1               | 1.1         |
| 9   | Messages Listing Format 1.1      | 1.1         |
| 10  | Persistent Message Handles       | 1.2         |
| 11  | Database Identifier              | 1.2         |
| 12  | Folder Version Counter           | 1.2         |
| 13  | Conversation Version Counter     | 1.3         |
| 14  | Participant Presence Change      | 1.3         |
| 15  | Participant Chat State Change    | 1.3         |
| 16  | PBAP Contact Cross Reference     | 1.3         |
| 17  | Notification Filtering           | 1.3         |
| 18  | UTC Offset Timestamp             | 1.4         |
| 19  | MapSupportedFeatures in Connect  | 1.2         |
| 20  | Conversation Listing             | 1.3         |
| 21  | Owner Status                     | 1.4         |
| 22  | Message Forwarding               | 1.4         |

## BlueZ Version Reference

From `supported-features.txt` in BlueZ source:

- MAP Server: version 1.0
- MAP Client: version 1.4

Despite the client being listed as 1.4, `obexd` does not send the
`MapSupportedFeatures` header. The "1.4" designation likely refers to
parsing capabilities rather than full OBEX-level negotiation.

## Workarounds

1. **Accept the downgrade**: MAP 1.0 operations work correctly. The
   Android notification is informational only.
2. **Re-pair after connection**: Some devices suppress the alert after
   the first successful MAP session.
3. **Use `cmapinfo`**: Before MAP operations, run `cmapinfo` to see what
   the remote device supports. Features beyond bit 5 are unavailable
   through BlueZ `obexd`.

## Future Work

- Investigate patching `obexd` or using an alternative OBEX library to
  include `MapSupportedFeatures` in the Connect request.
- Consider a BLEEP-native OBEX/MAP implementation that bypasses `obexd`
  for full MAP version negotiation.
