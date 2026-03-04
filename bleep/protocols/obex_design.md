# Raw OBEX Protocol Implementation — Design Document

**bc-50** | Target: `bleep/protocols/obex.py` | Status: **Design**
**BLEEP version scope:** v2.7.13+

---

## 1  Motivation

All current BLEEP OBEX operations (OPP, MAP, PBAP, FTP, SYNC, BIP) route
through BlueZ `obexd` via its D-Bus API on the session bus.  This works well
when:

* `bluetooth-obexd` is installed, running, and accessible.
* The target device interoperates cleanly with `obexd`.
* The OBEX profile being used is one that `obexd` exposes (Client1 targets:
  `opp`, `map`, `pbap`, `ftp`, `sync`, `bip-avrcp`).

A raw OBEX implementation directly on top of an RFCOMM socket bypasses `obexd`
entirely.  This is useful when:

1. **obexd is unavailable** — embedded or minimal Linux environments.
2. **Interop issues** — some devices have quirks that `obexd` doesn't handle
   well (e.g., non-standard OBEX headers, partial SRM support).
3. **Non-standard profiles** — custom OBEX-based services that don't map to
   any `obexd` target.
4. **Testing / research** — fine-grained control over every OBEX packet for
   protocol analysis and fuzzing.

---

## 2  OBEX Protocol Overview (IrOBEX / GOEP)

OBEX (Object Exchange) is a binary session protocol originally defined by
IrDA, adopted by Bluetooth as GOEP (Generic Object Exchange Profile).  The
Bluetooth SIG specifications are:

* **GOEP v2.1** (Generic Object Exchange Profile)
* **IrOBEX v1.5** (core protocol spec)

### 2.1  Packet Structure

Every OBEX packet has the same envelope:

```
+--------+--------+--------+--------+---- - - - ----+
| Opcode |   Packet Length  |   Headers (TLV)        |
| 1 byte |   2 bytes (BE)   |   variable             |
+--------+--------+--------+--------+---- - - - ----+
```

* **Opcode** (1 byte): request opcode (high bit = Final flag) or response
  code.
* **Packet Length** (2 bytes, big-endian): total packet length including
  opcode and length fields.
* **Headers**: zero or more TLV (Tag-Length-Value) headers.

### 2.2  Request Opcodes

| Opcode | Name        | Final variant |
|--------|-------------|---------------|
| 0x00   | Connect     | 0x80          |
| 0x01   | Disconnect  | 0x81          |
| 0x02   | Put         | 0x82          |
| 0x03   | Get         | 0x83          |
| 0x04   | SetPath     | 0x84          |
| 0x05   | Action      | 0x85          |
| 0x06   | Session     | 0x86          |
| 0xFF   | Abort       | 0xFF          |

The **Final** bit (bit 7 = 1) indicates the last packet in a multi-packet
operation.

### 2.3  Response Codes

| Code   | Meaning              |
|--------|----------------------|
| 0x10   | Continue             |
| 0x20   | Success (OK)         |
| 0x40   | Bad Request          |
| 0x41   | Unauthorized         |
| 0x43   | Forbidden            |
| 0x44   | Not Found            |
| 0x4D   | Unsupported Media    |
| 0x60   | Internal Server Err  |
| 0x61   | Not Implemented      |
| 0x63   | Service Unavailable  |

(Response codes also carry the Final bit in bit 7.)

### 2.4  Header Format

Each header is identified by a single-byte **Header ID** (HI).  The top two
bits encode the value type:

| HI bits 7–6 | Type                              | Length encoding        |
|-------------|-----------------------------------|------------------------|
| 00          | Null-terminated Unicode (UTF-16BE) | HI(1) + Len(2) + data |
| 01          | Byte sequence                      | HI(1) + Len(2) + data |
| 10          | 1-byte unsigned int                | HI(1) + value(1)      |
| 11          | 4-byte unsigned int (BE)           | HI(1) + value(4)      |

Common headers:

| HI   | Name             | Type         |
|------|------------------|--------------|
| 0x01 | Count            | 4-byte int   |
| 0x42 | Type             | Byte seq     |
| 0x44 | Time (ISO 8601)  | Byte seq     |
| 0x46 | Target           | Byte seq     |
| 0x47 | HTTP             | Byte seq     |
| 0x48 | Body             | Byte seq     |
| 0x49 | End-of-Body      | Byte seq     |
| 0x4A | Who              | Byte seq     |
| 0xC0 | Count            | 4-byte int   |
| 0xC3 | Length           | 4-byte int   |
| 0xCB | Connection ID    | 4-byte int   |
| 0x01 | Name             | Unicode str  |

### 2.5  Connect Handshake

The CONNECT request has extra fields after the standard 3-byte envelope:

```
+--------+--------+--------+--------+--------+--------+--------+---- - ----+
| 0x80   |   Pkt Length     | Version| Flags  | Max Pkt Length   | Headers  |
| 1 byte |   2 bytes        | 1 byte | 1 byte |   2 bytes (BE)   | variable |
+--------+--------+--------+--------+--------+--------+--------+---- - ----+
```

* **Version:** `0x10` (OBEX 1.0).
* **Flags:** typically `0x00`.
* **Max Packet Length:** the maximum OBEX packet size the sender will accept.

The CONNECT response has the same extra fields.

### 2.6  Target Header (profile selection)

When connecting to a specific OBEX profile, the Connect request includes a
**Target** header (HI `0x46`) containing the 16-byte UUID of the profile:

| Profile | Target UUID (16 bytes)                               |
|---------|------------------------------------------------------|
| FTP     | `F9EC7BC4-953C-11D2-984E-525400DC9E09`               |
| PBAP    | `7962-9263-1157-5F9D-4F44-941E-4BCF-D42C` (79622...)|
| MAP     | `BB582B40-420C-11DB-B0DE-0800200C9A66`               |
| SYNC    | `IRMC-SYNC` (well-known name, 8 bytes)               |

---

## 3  Proposed Architecture

### 3.1  Module Layout

```
bleep/protocols/
├── __init__.py          # package docstring (exists)
├── obex_design.md       # this design document
├── obex.py              # OBEX packet codec + session state machine (future)
└── l2cap_design.md      # L2CAP design document (bc-51)
```

### 3.2  `obex.py` — Proposed Public API

```python
class ObexPacket:
    """Immutable representation of a single OBEX request or response."""
    opcode: int
    is_final: bool
    headers: Dict[int, bytes]

    @classmethod
    def parse(cls, data: bytes) -> "ObexPacket": ...

    def serialize(self) -> bytes: ...


class ObexHeader:
    """Encode / decode individual OBEX headers."""
    @staticmethod
    def encode_unicode(hi: int, value: str) -> bytes: ...
    @staticmethod
    def encode_bytes(hi: int, value: bytes) -> bytes: ...
    @staticmethod
    def encode_u8(hi: int, value: int) -> bytes: ...
    @staticmethod
    def encode_u32(hi: int, value: int) -> bytes: ...
    @staticmethod
    def decode(data: bytes, offset: int) -> Tuple[int, Any, int]: ...


class ObexClient:
    """OBEX client session over a raw transport (socket).

    The transport must already be connected (e.g. RFCOMM socket from
    ``classic_rfccomm_open``).
    """

    def __init__(self, sock: socket.socket, *, max_packet: int = 65535): ...

    def connect(self, target: Optional[bytes] = None) -> ObexPacket: ...
    def disconnect(self) -> ObexPacket: ...
    def get(self, headers: Dict[int, bytes]) -> Iterator[bytes]: ...
    def put(self, headers: Dict[int, bytes], body: bytes) -> ObexPacket: ...
    def setpath(self, name: str, flags: int = 0) -> ObexPacket: ...
    def abort(self) -> ObexPacket: ...

    def _send(self, packet: ObexPacket) -> None: ...
    def _recv(self) -> ObexPacket: ...
```

### 3.3  Transport Independence

`ObexClient` takes a connected `socket.socket` — it does **not** open the
connection itself.  This means it can run on:

* **RFCOMM** — `socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM)` via
  `classic_rfccomm_open()`.
* **L2CAP** — `socket(AF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP)` via
  the planned `l2cap_open()`.
* **TCP** (testing) — any stream socket for unit testing without hardware.

### 3.4  Multi-Packet Transfers

OBEX GET and PUT operations may span multiple packets.  The `ObexClient`
handles the multi-packet Continue / Final dance internally:

* **GET:** sends `GET` (non-final), receives `Continue` + Body chunks,
  sends `GET` (final) to get `End-of-Body`.  `get()` yields body chunks
  as an iterator.
* **PUT:** sends `PUT` packets with Body headers, final packet carries
  `End-of-Body`.  Handles `Continue` responses between packets.

### 3.5  Error Handling

* Response codes ≥ 0x40 (with Final bit masked) raise `ObexError` with the
  response code and any descriptive headers.
* Socket errors (timeout, broken pipe) propagate as `OSError`.
* The class does **not** attempt automatic reconnection.

---

## 4  Integration with Existing BLEEP Architecture

### 4.1  Relationship to obexd-Based Layers

The raw OBEX path is an **alternative** to the D-Bus path, not a
replacement.  Existing code continues to use `obexd` by default.

```
┌──────────────────────────────────────────────────────────┐
│                    Operations Layer                       │
│   classic_opp.py  classic_map.py  classic_ftp.py  …      │
├─────────────┬────────────────────────────────────────────┤
│  D-Bus path │            Raw path (new)                  │
│  obex_opp   │   ObexClient + profile-specific helpers    │
│  obex_map   │   (over RFCOMM / L2CAP socket)             │
│  obex_ftp   │                                            │
│  obex_sync  │                                            │
│  obex_bip   │                                            │
├─────────────┴────────────────────────────────────────────┤
│                  Transport Layer                          │
│   obexd (session bus)  │  RFCOMM socket  │  L2CAP socket │
└────────────────────────┴────────────────┴────────────────┘
```

### 4.2  Operations Layer Changes (Future)

Each operations module (e.g., `classic_ftp.py`) would gain a `backend`
parameter:

```python
def list_folder(mac, path="", *, timeout=30, backend="dbus"):
    if backend == "dbus":
        # existing obexd path
        ...
    elif backend == "raw":
        # new ObexClient path
        channel = _resolve_ftp_channel(mac)
        sock = classic_rfccomm_open(mac, channel)
        client = ObexClient(sock)
        client.connect(target=FTP_TARGET_UUID)
        ...
```

### 4.3  CLI / Debug Integration (Future)

A `--raw` flag would be added to relevant commands:

```bash
python -m bleep.cli classic-ftp AA:BB:CC:DD:EE:FF ls --raw
```

```
BLEEP-DEBUG> cftp ls --raw
```

---

## 5  Implementation Phases

| Phase | Scope                                    | Version  |
|-------|------------------------------------------|----------|
| 5.1   | `ObexPacket` + `ObexHeader` codec        | v2.7.13  |
| 5.2   | `ObexClient` CONNECT / DISCONNECT        | v2.7.13  |
| 5.3   | `ObexClient` GET / PUT (single-packet)   | v2.7.14  |
| 5.4   | Multi-packet GET / PUT (Continue loop)   | v2.7.14  |
| 5.5   | SetPath + Abort                          | v2.7.14  |
| 5.6   | Profile-specific helpers (FTP, OPP)      | v2.7.15  |
| 5.7   | `--raw` backend flag in ops layer + CLI  | v2.7.15  |
| 5.8   | Unit tests with mock TCP transport       | v2.7.15  |

---

## 6  Testing Strategy

* **Unit tests** (no hardware): mock socket with canned OBEX responses.
  Verify packet serialization / parsing round-trips.
* **Integration tests** (with hardware): run against a real device (phone,
  ESP32) with FTP / OPP services.  Compare results against the obexd path
  to confirm behavioral parity.
* **Fuzz tests** (optional): feed malformed packets into the parser to
  verify robustness.

---

## 7  Security Considerations

* The raw OBEX client operates over an already-authenticated Bluetooth
  link.  Authentication, pairing, and encryption are handled at the
  transport layer (RFCOMM / L2CAP) before the OBEX session begins.
* The `ObexClient` does **not** implement OBEX-level authentication
  (Challenge/Response headers 0x4D/0x4E).  This could be added in a
  future version if needed for specific devices.
* File write operations (PUT) should validate paths to prevent directory
  traversal.

---

## 8  References

* IrOBEX 1.5 specification (IrDA)
* Bluetooth GOEP v2.1 specification (Bluetooth SIG)
* BlueZ `obexd` source: `obexd/src/obex.c`, `obexd/client/`
* BlueZ `org.bluez.obex.Client.rst`, `org.bluez.obex.Transfer.rst`
* BLEEP existing code: `bleep/dbuslayer/obex_*.py`, `bleep/dbuslayer/_obex_common.py`
* BLEEP RFCOMM connector: `bleep/ble_ops/classic_connect.py:classic_rfccomm_open()`
