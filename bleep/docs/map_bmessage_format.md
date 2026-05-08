# MAP bMessage Format Reference

Comprehensive reference for the Bluetooth **Message Access Profile (MAP)**
bMessage format as implemented by BlueZ and consumed by BLEEP.

---

## 1  Protocol Overview

MAP allows a client (MCE — Message Client Equipment) to access messages on a
server (MSE — Message Server Equipment) via OBEX over Bluetooth Classic.  BlueZ
exposes MAP through the `org.bluez.obex.MessageAccess1` D-Bus interface on the
**session bus** (requires `bluetooth-obexd`).

Key D-Bus methods (from `org.bluez.obex.MessageAccess1`):

| Method | Purpose |
|--------|---------|
| `SetFolder(name)` | Navigate the folder hierarchy |
| `ListFolders(filter)` | List subfolders of the current directory |
| `ListMessages(folder, filter)` | List messages; returns `Message1` object paths |
| `PushMessage(sourcefile, folder, args)` | Upload a bMessage file to the remote device |
| `UpdateInbox()` | Request the remote to refresh its inbox |

Each message object (`org.bluez.obex.Message1`) supports:

| Method / Property | Access | Description |
|-------------------|--------|-------------|
| `Get(targetfile, attachment)` | method | Download message to local file |
| `Read` | read/write | Message read flag |
| `Deleted` | write-only | Message deleted flag |
| `Subject` | readonly | Message subject line |
| `Timestamp` | readonly | Message timestamp |
| `Sender` / `SenderAddress` | readonly | Originator name / address |
| `Recipient` / `RecipientAddress` | readonly | Recipient name / address |
| `Type` | readonly | `email`, `sms-gsm`, `sms-cdma`, `mms` |
| `Priority` | readonly | High-priority flag |
| `Status` | readonly | `complete`, `fractioned`, `notification` |
| `DeliveryStatus` | readonly | `delivered`, `sent`, `unknown` |
| `ConversationId` | readonly | Unique conversation identifier |
| `Direction` | readonly | `incoming`, `outgoing`, `outgoingdraft`, `outgoingpending` |
| `AttachmentMimeTypes` | readonly | MIME type of attachments |

**Source**: BlueZ D-Bus API `org.bluez.obex.MessageAccess1`,
`org.bluez.obex.Message1` (wrapped by `bleep/dbuslayer/obex_map.py`)

---

## 2  Supported Message Types

The `SupportedTypes` property on `MessageAccess1` advertises which types the
remote MAS supports.  The `TYPE:` field in a bMessage envelope must be one of:

| TYPE value | Description | Body format |
|------------|-------------|-------------|
| `SMS_GSM` | GSM short message | Plain text |
| `SMS_CDMA` | CDMA short message | Plain text |
| `EMAIL` | Email | RFC 2822 with headers (`From:`, `To:`, `Subject:`, etc.) |
| `MMS` | Multimedia message | MIME multipart (`Content-Type: multipart/mixed`) |
| `IM` | Instant message | Plain text (uses `EMAIL:` in VCARDs, not `TEL:`) |

Not all devices support all types.  Query at runtime:

```
BLEEP-DEBUG> cmap types
```

**Source**: `bleep/dbuslayer/obex_map.py` line 271 (`get_supported_types`),
BlueZ D-Bus API `org.bluez.obex.MessageAccess1` `SupportedTypes` property

---

## 3  Folder Hierarchy

MAP devices expose a standard folder tree under `telecom/msg/`:

```
telecom/
  msg/
    inbox/       ← received messages
    sent/        ← sent messages
    outbox/      ← queued for sending
    draft/       ← unsent drafts
    deleted/     ← trash / recently deleted
```

Some devices may expose additional folders.  Use `cmap folders` to enumerate
the full tree (calls `walk_folder_tree()` which recursively descends via
`SetFolder` + `ListFolders`).

**Important OBEX semantics**: `SetFolder(folder)` navigates *relative* to the
current position.  BLEEP's `list_messages()` navigates to the folder first,
then calls `ListMessages("")` on the current directory to avoid the
double-folder bug (where `SetFolder("inbox")` followed by
`ListMessages("inbox")` resolves to `inbox/inbox`).

**Source**: `bleep/ble_ops/classic/map.py` lines 159–186,
`bleep/dbuslayer/obex_map.py` lines 116–117

---

## 4  bMessage Envelope Format

`PushMessage` requires the source file to be in **bMessage format** — a
vCard-derived envelope defined by the Bluetooth MAP specification.  The general
structure:

```
BEGIN:BMSG
VERSION:1.0
STATUS:READ|UNREAD
TYPE:SMS_GSM|SMS_CDMA|EMAIL|MMS|IM
FOLDER:telecom/msg/<folder>
BEGIN:VCARD                    ← originator (sender)
VERSION:3.0
FN:<display name>
N:<display name>
TEL:<phone>                    ← for SMS/MMS; use EMAIL: for EMAIL/IM types
END:VCARD
BEGIN:BENV                     ← envelope (can be nested for forwarded messages)
BEGIN:VCARD                    ← recipient(s) — one VCARD per recipient
VERSION:3.0
FN:<display name>
N:<display name>
TEL:<phone>
END:VCARD
BEGIN:BBODY
CHARSET:UTF-8
ENCODING:8BIT                  ← optional; used for EMAIL/MMS
LENGTH:<byte count>            ← see §5 for calculation rules
BEGIN:MSG
<message body content>
END:MSG
END:BBODY
END:BENV
END:BMSG
```

### Key structural rules

1. **Originator VCARD** comes **before** `BEGIN:BENV` (outside the envelope).
2. **Recipient VCARDs** go **inside** `BEGIN:BENV`, before `BEGIN:BBODY`.
3. **Multiple recipients** = multiple consecutive VCARDs inside one BENV.
4. **One bMessage per file** — there is no support for multiple
   `BEGIN:BMSG`/`END:BMSG` blocks in a single file (see §7).
5. `ENCODING:` is optional for SMS types but recommended for EMAIL and MMS.

### Type-specific body content

- **SMS_GSM / SMS_CDMA / IM**: Plain text between `BEGIN:MSG` / `END:MSG`.
- **EMAIL**: Full RFC 2822 email with headers (`From:`, `To:`, `Subject:`,
  `Date:`, `Content-Type:`, blank line, body text).
- **MMS**: MIME multipart content with boundary, each part having its own
  `Content-Type` and optional `Content-Disposition` for attachments.

---

## 5  LENGTH Field Calculation & Line Endings

### CRLF requirement

The MAP specification mandates **CRLF** (`\r\n`) line endings throughout the
bMessage envelope.  Files with bare LF (`\n`) endings are silently rejected by
many Message Access Servers even though the OBEX transfer reports success.

BLEEP **auto-normalizes** bMessage files before every push:

1. Bare LF → CRLF conversion.
2. `LENGTH` recalculation to match the CRLF content.

This normalization is performed by `normalize_bmessage()` in
`bleep/ble_ops/classic/map.py` and applied transparently in `push_message()`.

### LENGTH semantics

The `LENGTH:` field in the `BBODY` block must equal the **byte count** from the
start of `BEGIN:MSG\r\n` through the end of `END:MSG\r\n`, inclusive of both
delimiters and their CRLF line endings.

```
LENGTH = len("BEGIN:MSG\r\n") + len(<body with \r\n endings>) + len("END:MSG\r\n")
```

BLEEP validates this before every single push and warns on mismatch:

```python
# bleep/modes/debug_classic_obex.py  _validate_bmsg_length()
# Warns about LF-only line endings and LENGTH mismatches.
# The operations layer auto-normalizes, so the push still succeeds.
```

**A mismatched LENGTH causes many devices to silently discard the message**
even though the OBEX transfer itself succeeds.

### Common pitfall: LENGTH drift

Editing a downloaded bMessage (e.g. changing the body text) without updating
the `LENGTH:` field is the most common cause of silent push failures.  BLEEP's
auto-normalization handles this transparently, but when crafting files by hand
always use CRLF endings and recount the LENGTH after any edit.

---

## 6  Nested Envelopes (Forwarded / Attached Messages)

The bMessage format supports **nested `BEGIN:BENV`/`END:BENV` blocks** to
represent forwarded or attached messages.  The outer envelope wraps the
forwarding context; the inner envelope contains the original message with its
own originator VCARD and BBODY.

```
BEGIN:BMSG
...
BEGIN:BENV                         ← outer: the forwarding message
  BEGIN:VCARD ... END:VCARD        ← final recipient
  BEGIN:BENV                       ← inner: the original/attached message
    BEGIN:VCARD ... END:VCARD      ← original sender
    BEGIN:BBODY
    LENGTH:<n>
    BEGIN:MSG
    <original message content>
    END:MSG
    END:BBODY
  END:BENV
  BEGIN:BBODY                      ← forwarding body
  LENGTH:<m>
  BEGIN:MSG
  <forwarding message content>
  END:MSG
  END:BBODY
END:BENV
END:BMSG
```

Each envelope level has its own `BBODY` with its own `LENGTH` field.  When
validating nested messages, each `LENGTH` must be computed independently
against its own `BEGIN:MSG`/`END:MSG` span.

A concrete forwarded-email example:

```
BEGIN:BMSG
VERSION:1.0
STATUS:READ
TYPE:EMAIL
FOLDER:telecom/msg/outbox
BEGIN:VCARD
VERSION:3.0
FN:Forwarder
N:Forwarder
EMAIL:forwarder@example.com
END:VCARD
BEGIN:BENV
BEGIN:VCARD
VERSION:3.0
FN:Final Recipient
N:Final Recipient
EMAIL:final@example.com
END:VCARD
BEGIN:BENV
BEGIN:VCARD
VERSION:3.0
FN:Original Sender
N:Original Sender
EMAIL:original@example.com
END:VCARD
BEGIN:BBODY
CHARSET:UTF-8
ENCODING:8BIT
LENGTH:147
BEGIN:MSG
From: original@example.com
To: forwarder@example.com
Subject: Original message

This is the original message being forwarded.
END:MSG
END:BBODY
END:BENV
BEGIN:BBODY
CHARSET:UTF-8
ENCODING:8BIT
LENGTH:193
BEGIN:MSG
From: forwarder@example.com
To: final@example.com
Subject: Fwd: Original message

Forwarding this message for your review.

---------- Forwarded message ----------
(see attached original)
END:MSG
END:BBODY
END:BENV
END:BMSG
```

This file contains 2 body blocks — one for the inner (original) message and
one for the outer (forwarding) message — each with its own `LENGTH`.

---

## 7  Bulk Operations: Download and Upload All Messages

### Downloading all messages (supported)

You can enumerate and download every message on the device by:

1. Walking the folder tree (`cmap folders` / `list_folder_tree()`)
2. Listing messages in each leaf folder (`cmap list <folder>` / `list_messages()`)
3. Downloading each message individually (`cmap get <handle>` / `get_message()`)

The `ListMessages` filter supports pagination (`Offset`, `MaxCount`) to avoid
timeouts on large folders — BlueZ obexd buffers and parses the full XML listing
synchronously with a default `MaxListCount` of 1024.

**Source**: `bleep/dbuslayer/obex_map.py` lines 160–212 (`list_messages`),
`bleep/ble_ops/classic/map.py` lines 189–209 (`get_message`),
BlueZ `obexd/client/map.c` line 59 (`#define DEFAULT_COUNT 1024`)

### Uploading multiple messages (one file per push)

**There is no batch upload** in the MAP specification.  Each `PushMessage` call
accepts exactly one bMessage file.  To upload multiple messages, you must make
sequential `PushMessage` calls, each with its own file.

The BlueZ D-Bus API makes this explicit — `PushMessage(sourcefile, folder, args)`
takes a single `sourcefile` string path:

```python
# bleep/dbuslayer/obex_map.py lines 253–263
def push_message(self, filepath: str, folder: str = "telecom/msg/outbox") -> None:
    filepath = os.path.abspath(filepath)
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    transfer_path, _ = self._map.PushMessage(
        filepath, folder, dbus.Dictionary({}, signature="sv")
    )
    self._poll_transfer(transfer_path)
```

**Multiple `BEGIN:BMSG`/`END:BMSG` blocks in a single file are NOT valid** and
will be rejected or only the first will be processed.

### Debug-mode commands

BLEEP exposes both operations as first-class debug commands:

```
cmap download-all [dest_dir] [--folders f1,f2] [--count N]
cmap push-all <dir_or_glob> [folder] [--dry-run] [--delay N]
```

`download-all` walks the folder tree, lists every message per folder, and
downloads each into `dest_dir` (default `OBEX_RECEIVE_DIR/<mac>_map_dump/`).
Files are named `<folder>_<handle>.bmsg` for easy round-trip with `push-all`.

`push-all` iterates `.bmsg` files in a directory (or glob), validates each
(`BEGIN:BMSG` header, bMessage normalization), and pushes sequentially.
A 1.5-second cooldown between pushes (configurable via `--delay`) prevents
OBEX session exhaustion on the remote device.  If a session-creation timeout
occurs, the push is automatically retried once after a 3-second pause.
`--dry-run` validates without pushing.  Errors are logged per-file; the batch
continues.

### Operations-layer API

The same functionality is available programmatically:

```python
from bleep.ble_ops.classic.map import download_all_messages, push_all_messages

# Download everything
results = download_all_messages(mac, "/tmp/dump", max_count=50)
# results: {folder: [Path, ...]}

# Push a directory of .bmsg files (with default 1.5s inter-push delay)
outcomes = push_all_messages(mac, bmsg_file_list, "telecom/msg/outbox")
# outcomes: {filepath: "ok" | "ok (retry)" | error_string}

# Custom delay (e.g. slower device)
outcomes = push_all_messages(mac, bmsg_file_list, "telecom/msg/outbox", delay=3.0)
```

Both functions accept an optional `progress_cb` for real-time feedback.
`push_all_messages` also accepts a `delay` parameter (default 1.5s) to control
the inter-push cooldown and automatically retries once on transient session
timeouts.

---

## 8  PushMessage Arguments

The BlueZ `PushMessage` method accepts a `dict args` parameter with three
optional keys:

| Key | Type | Description |
|-----|------|-------------|
| `Transparent` | boolean | If true, the MSE does not add the message to the sent folder |
| `Retry` | boolean | If true, the MSE should retry sending on failure |
| `Charset` | string | Character set override (default UTF-8) |

BLEEP currently passes an empty dictionary (`dbus.Dictionary({}, signature="sv")`)
for these args.  Future enhancement could expose these as `cmap push` flags.

**Source**: BlueZ D-Bus API `org.bluez.obex.MessageAccess1` `PushMessage` method

---

## 9  ListMessages Filter Fields

The `ListMessages` method accepts a filter dictionary.  Available field names
(from `ListFilterFields()`):

```
subject, timestamp, sender, sender-address, recipient, recipient-address,
type, size, status, text, attachment, priority, read, sent, protected, replyto
```

Type-based filtering:

| Filter key | Values |
|------------|--------|
| `Types` | `"sms"`, `"email"`, `"mms"` |
| `Read` | `True` (read) / `False` (unread) |
| `Priority` | `True` (high) / `False` (normal) |
| `PeriodBegin` / `PeriodEnd` | `"YYYYMMDDTHHMMSS"` format |
| `Offset` | uint16, default 0 |
| `MaxCount` | uint16, default 1024 |
| `SubjectLength` | byte, default 256 |

**Source**: BlueZ D-Bus API `org.bluez.obex.MessageAccess1` `ListMessages` method,
`bleep/dbuslayer/obex_map.py` lines 160–212

---

## 10  bMessage Examples by Type

Below are representative bMessage examples for each supported type.  All
`LENGTH` values are correct for the CRLF content in the corresponding test
files under `workDir/MAP/map_test_messages/`.

### 10.1  SMS_GSM — basic outbox message

```
BEGIN:BMSG
VERSION:1.0
STATUS:READ
TYPE:SMS_GSM
FOLDER:telecom/msg/outbox
BEGIN:VCARD
VERSION:3.0
FN:BLEEP Test Suite
N:BLEEP Test Suite
TEL:+15551234567
END:VCARD
BEGIN:BENV
BEGIN:VCARD
VERSION:3.0
FN:Target Device
N:Target Device
TEL:+15559876543
END:VCARD
BEGIN:BBODY
CHARSET:UTF-8
LENGTH:46
BEGIN:MSG
Hello from BLEEP test suite
END:MSG
END:BBODY
END:BENV
END:BMSG
```

Variations on this template:

- **UNREAD inbox injection**: Change `STATUS:UNREAD` and `FOLDER:telecom/msg/inbox`.
- **Draft**: Change `FOLDER:telecom/msg/draft`.
- **SMS_CDMA**: Change `TYPE:SMS_CDMA`.

### 10.2  EMAIL — RFC 2822 body with headers

The body between `BEGIN:MSG`/`END:MSG` must be a complete RFC 2822 message:

```
BEGIN:BMSG
VERSION:1.0
STATUS:READ
TYPE:EMAIL
FOLDER:telecom/msg/outbox
BEGIN:VCARD
VERSION:3.0
FN:BLEEP Tester
N:BLEEP Tester
EMAIL:tester@bleep-bt.local
END:VCARD
BEGIN:BENV
BEGIN:VCARD
VERSION:3.0
FN:Target User
N:Target User
EMAIL:target@example.com
END:VCARD
BEGIN:BBODY
CHARSET:UTF-8
ENCODING:8BIT
LENGTH:251
BEGIN:MSG
From: tester@bleep-bt.local
To: target@example.com
Subject: MAP Email Test
Date: Mon, 30 Mar 2026 12:00:00 -0400
Content-Type: text/plain; charset=UTF-8

This is a test email pushed via Bluetooth MAP.
Sent from the BLEEP test suite.
END:MSG
END:BBODY
END:BENV
END:BMSG
```

### 10.3  MMS — MIME multipart with attachment

MMS bodies use standard MIME multipart encoding:

```
BEGIN:BMSG
VERSION:1.0
STATUS:READ
TYPE:MMS
FOLDER:telecom/msg/outbox
BEGIN:VCARD
VERSION:3.0
FN:MMS Sender
N:MMS Sender
TEL:+15558881234
END:VCARD
BEGIN:BENV
BEGIN:VCARD
VERSION:3.0
FN:MMS Recipient
N:MMS Recipient
TEL:+15559995678
END:VCARD
BEGIN:BBODY
CHARSET:UTF-8
ENCODING:8BIT
LENGTH:459
BEGIN:MSG
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mms-boundary-bleep"

--mms-boundary-bleep
Content-Type: text/plain; charset=UTF-8

MMS test message with a simulated text attachment.
Sent via Bluetooth MAP from BLEEP test suite.

--mms-boundary-bleep
Content-Type: text/plain; charset=UTF-8; name="note.txt"
Content-Disposition: attachment; filename="note.txt"

This is an attached text file within the MMS.
--mms-boundary-bleep--
END:MSG
END:BBODY
END:BENV
END:BMSG
```

### 10.4  IM — Instant Message

IM type uses `EMAIL:` instead of `TEL:` in VCARDs:

```
BEGIN:BMSG
VERSION:1.0
STATUS:READ
TYPE:IM
FOLDER:telecom/msg/outbox
BEGIN:VCARD
VERSION:3.0
FN:IM Sender
N:IM Sender
EMAIL:sender@example.com
END:VCARD
BEGIN:BENV
BEGIN:VCARD
VERSION:3.0
FN:IM Recipient
N:IM Recipient
EMAIL:recipient@example.com
END:VCARD
BEGIN:BBODY
CHARSET:UTF-8
LENGTH:56
BEGIN:MSG
Instant message test via MAP protocol
END:MSG
END:BBODY
END:BENV
END:BMSG
```

### 10.5  Multi-recipient — group message

Multiple `BEGIN:VCARD`/`END:VCARD` blocks inside one `BEGIN:BENV`:

```
BEGIN:BMSG
VERSION:1.0
STATUS:READ
TYPE:SMS_GSM
FOLDER:telecom/msg/outbox
BEGIN:VCARD
VERSION:3.0
FN:Group Sender
N:Group Sender
TEL:+15551110000
END:VCARD
BEGIN:BENV
BEGIN:VCARD
VERSION:3.0
FN:Recipient One
N:Recipient One
TEL:+15552220001
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Recipient Two
N:Recipient Two
TEL:+15552220002
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN:Recipient Three
N:Recipient Three
TEL:+15552220003
END:VCARD
BEGIN:BBODY
CHARSET:UTF-8
LENGTH:62
BEGIN:MSG
Group text sent to three recipients at once
END:MSG
END:BBODY
END:BENV
END:BMSG
```

### 10.6  Forwarded message (nested BENV)

See the full inline example in §6 above.

---

## 11  Implementation Reference

### Code paths for MAP operations

| Operation | Debug command | CLI command | Operations layer | D-Bus layer |
|-----------|--------------|-------------|-----------------|-------------|
| List folders | `cmap folders` | `classic-map folders` | `map.list_folders()` / `list_folder_tree()` | `MapSession.list_folders()` / `walk_folder_tree()` |
| List messages | `cmap list <folder>` | `classic-map list` | `map.list_messages()` | `MapSession.list_messages()` |
| Get message | `cmap get <handle>` | `classic-map get` | `map.get_message()` | `MapSession.get_message()` |
| Push message | `cmap push <file>` | `classic-map push` | `map.push_message()` | `MapSession.push_message()` |
| Download all | `cmap download-all` | — | `map.download_all_messages()` | `MapSession` per folder |
| Push all | `cmap push-all` | — | `map.push_all_messages()` | sequential `push_message()` |
| Update inbox | `cmap inbox` | `classic-map inbox` | `map.update_inbox()` | `MapSession.update_inbox()` |
| Message props | `cmap props <handle>` | — | — | `MapSession.get_message_properties()` |
| Set read flag | `cmap read <handle>` | — | — | `MapSession.set_message_read()` |
| Set deleted | `cmap delete <handle>` | — | — | `MapSession.set_message_deleted()` |
| MAS instances | `cmap instances` | `classic-map instances` | `map.list_mas_instances()` | SDP discovery |
| MNS monitor | `cmap monitor` | `classic-map monitor` | `map.start_message_monitor()` | `MapSession.start_notification_watch()` |

### Pre-push validation & normalization chain

1. `debug_classic_obex.py` checks file starts with `BEGIN:BMSG`
2. `_validate_bmsg_length()` warns about LF-only endings and LENGTH mismatches
3. `map.push_message()` calls `normalize_bmessage()` → converts LF→CRLF, recalculates LENGTH, writes temp file if needed
4. `MapSession.push_message()` verifies file exists, calls `PushMessage` D-Bus method
5. Transfer is polled via `_poll_transfer()` until `complete` or `error`
6. Temp file (if created) is cleaned up

### Key constants

- MAP-MSE UUID: `0x1132` — Message Access Server
- MAP UUID: `0x1134` — Message Access Profile
- D-Bus interface: `org.bluez.obex.MessageAccess1`
- D-Bus message interface: `org.bluez.obex.Message1`
- Default push folder: `telecom/msg/outbox`

**Source**: `bleep/bt_ref/constants.py`, `bleep/dbuslayer/obex_map.py` lines 27–33

---

*Last updated: 2026-03-30 (added `cmap download-all` / `cmap push-all` debug commands; `download_all_messages` / `push_all_messages` operations-layer API; moved `collect_leaf_paths` to `map.py`)*
