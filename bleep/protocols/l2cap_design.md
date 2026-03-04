# L2CAP Raw Channel Access — Design Document

**bc-51** | Target: `bleep/protocols/l2cap.py` | Status: **Design**
**BLEEP version scope:** v2.7.13+

---

## 1  Motivation

BLEEP currently supports two transport paths for Classic Bluetooth:

1. **RFCOMM sockets** — via `classic_rfccomm_open()` in
   `bleep/ble_ops/classic_connect.py`.  RFCOMM provides reliable stream
   semantics over L2CAP.
2. **D-Bus (obexd / BlueZ)** — higher-level APIs that abstract away the
   transport entirely.

L2CAP sits below RFCOMM and provides direct access to Bluetooth logical
channels.  Raw L2CAP access is needed for:

1. **Non-RFCOMM protocols** — some profiles (HID, AVDTP, AVCTP, BNEP) use
   L2CAP directly via well-known PSM values rather than RFCOMM channels.
2. **Custom PSM services** — devices that expose proprietary services on
   dynamic L2CAP PSMs discovered through SDP.
3. **Protocol analysis** — inspecting raw L2CAP traffic for debugging and
   research.
4. **BLE L2CAP CoC** — L2CAP Connection-oriented Channels for BLE data
   transfer (LE Credit Based Flow Control mode).

---

## 2  L2CAP Protocol Overview

### 2.1  Socket Types

Linux exposes L2CAP via the Bluetooth socket API:

```python
import socket

# Classic BR/EDR — connection-oriented, sequenced packets
sock = socket.socket(
    socket.AF_BLUETOOTH,
    socket.SOCK_SEQPACKET,
    socket.BTPROTO_L2CAP,
)

# Classic BR/EDR — raw datagrams (connectionless)
sock = socket.socket(
    socket.AF_BLUETOOTH,
    socket.SOCK_DGRAM,
    socket.BTPROTO_L2CAP,
)

# Classic BR/EDR — stream mode (like RFCOMM but over L2CAP)
sock = socket.socket(
    socket.AF_BLUETOOTH,
    socket.SOCK_STREAM,
    socket.BTPROTO_L2CAP,
)
```

The primary type for most use cases is `SOCK_SEQPACKET` (connection-oriented,
message-boundary-preserving).

### 2.2  Addressing — `sockaddr_l2`

The Python equivalent of `struct sockaddr_l2`:

```python
# Connect to a remote PSM
sock.connect(("AA:BB:CC:DD:EE:FF", psm))

# Bind to a local PSM (server role)
sock.bind(("00:00:00:00:00:00", psm))
```

Python's `socket` module handles the `l2_family`, `l2_bdaddr`, and `l2_psm`
fields automatically.  For CID-based addressing (fixed channels), the
`l2_cid` field is not directly accessible from Python without `ctypes` or
a C extension.

### 2.3  Well-Known PSM Values

From the Bluetooth SIG Assigned Numbers (`References/psm.yaml`):

| PSM    | Name              | Profile/Protocol          |
|--------|-------------------|---------------------------|
| 0x0001 | SDP               | Service Discovery         |
| 0x0003 | RFCOMM            | RFCOMM multiplexer        |
| 0x000F | BNEP              | Bluetooth Network (PAN)   |
| 0x0011 | HID_Control       | Human Interface Device    |
| 0x0013 | HID_Interrupt     | Human Interface Device    |
| 0x0017 | AVCTP             | AV Control Transport      |
| 0x0019 | AVDTP             | AV Distribution Transport |
| 0x001B | AVCTP_Browsing    | AVCTP Browsing channel    |
| 0x001F | ATT               | Attribute Protocol (BLE)  |
| 0x0023 | LE_PSM_IPSP       | IP Support Profile (BLE)  |
| 0x0025 | OTS               | Object Transfer (BLE)     |
| 0x0027 | EATT              | Enhanced ATT (BLE)        |

Dynamic PSMs (≥ 0x1001, odd values) are assigned at runtime and
discovered via SDP.

### 2.4  Socket Options

From `l2cap.rst` (BlueZ documentation):

| Level          | Option              | Description                     |
|----------------|---------------------|---------------------------------|
| SOL_BLUETOOTH  | BT_SECURITY         | Security level (SDP/Low/Med/High/FIPS) |
| SOL_BLUETOOTH  | BT_DEFER_SETUP      | Defer connection authorization   |
| SOL_BLUETOOTH  | BT_FLUSHABLE        | Allow flushing channel data      |
| SOL_BLUETOOTH  | BT_POWER            | Sniff mode exit policy           |
| SOL_BLUETOOTH  | BT_CHANNEL_POLICY   | AMP channel policy               |
| SOL_BLUETOOTH  | BT_PHY              | Supported PHY types              |
| SOL_BLUETOOTH  | BT_MODE             | L2CAP mode (Basic/ERTM/Stream/LE_FlowCtl) |

### 2.5  L2CAP Modes

| Mode               | Value | Description                          |
|--------------------|-------|--------------------------------------|
| BT_MODE_BASIC      | 0x00  | Default basic mode                   |
| BT_MODE_ERTM       | 0x01  | Enhanced Retransmission (BR/EDR)     |
| BT_MODE_STREAM     | 0x02  | Streaming mode (BR/EDR)              |
| BT_MODE_LE_FLOWCTL | 0x03  | LE Credit Based Flow Control         |
| BT_MODE_EXT_FLOWCTL| 0x04  | Extended Credit Based Flow Control   |

---

## 3  Proposed Architecture

### 3.1  Module Layout

```
bleep/protocols/
├── __init__.py          # package docstring (exists)
├── obex_design.md       # raw OBEX design (bc-50)
├── obex.py              # OBEX codec + client (future)
├── l2cap_design.md      # this design document
└── l2cap.py             # L2CAP helpers (future)
```

### 3.2  `l2cap.py` — Proposed Public API

```python
def l2cap_open(
    mac_address: str,
    psm: int,
    *,
    sock_type: int = socket.SOCK_SEQPACKET,
    timeout: float = 8.0,
    security: Optional[int] = None,
    mode: Optional[int] = None,
) -> socket.socket:
    """Open an L2CAP socket to *mac_address* on *psm*.

    Returns a connected socket.  Mirrors the API of
    ``classic_rfccomm_open`` for consistency.
    """
    ...


def l2cap_listen(
    psm: int = 0,
    *,
    sock_type: int = socket.SOCK_SEQPACKET,
    backlog: int = 1,
    security: Optional[int] = None,
) -> socket.socket:
    """Bind and listen on a local L2CAP PSM.

    If *psm* is 0, the kernel assigns a dynamic PSM.  Returns the
    listening socket; call ``.accept()`` to get client connections.
    """
    ...


def l2cap_get_psm(sock: socket.socket) -> int:
    """Return the PSM bound to a listening socket."""
    ...


class L2capConnection:
    """Context manager wrapping an L2CAP socket.

    Provides send/recv helpers with logging and optional timeout.
    """

    def __init__(self, sock: socket.socket): ...

    def send(self, data: bytes) -> int: ...
    def recv(self, bufsize: int = 4096) -> bytes: ...
    def close(self) -> None: ...

    def __enter__(self) -> "L2capConnection": ...
    def __exit__(self, *exc) -> None: ...
```

### 3.3  Security Level Helper

```python
# Constants from <bluetooth/bluetooth.h>
BT_SECURITY_SDP    = 0
BT_SECURITY_LOW    = 1
BT_SECURITY_MEDIUM = 2
BT_SECURITY_HIGH   = 3
BT_SECURITY_FIPS   = 4

SOL_BLUETOOTH = 274
BT_SECURITY   = 4

def set_security(sock: socket.socket, level: int) -> None:
    """Set the security level on an L2CAP or RFCOMM socket."""
    import struct
    sock.setsockopt(
        SOL_BLUETOOTH,
        BT_SECURITY,
        struct.pack("I", level),
    )
```

---

## 4  Integration with Existing BLEEP Architecture

### 4.1  Relationship to RFCOMM

L2CAP is the layer below RFCOMM.  `l2cap_open()` parallels
`classic_rfccomm_open()` — both return connected sockets that higher-level
code (e.g., raw OBEX client, custom protocol handlers) can use.

```
┌──────────────────────────────────────────────┐
│               Application Layer              │
│  ObexClient  │  HID handler  │  Custom proto │
├──────────────┼───────────────┼───────────────┤
│  RFCOMM sock │  L2CAP sock   │  L2CAP sock   │
│  (channel)   │  (PSM 0x0011) │  (dynamic PSM)│
├──────────────┴───────────────┴───────────────┤
│              HCI / Controller                │
└──────────────────────────────────────────────┘
```

### 4.2  Debug Commands (Future)

New debug commands for raw L2CAP:

```
BLEEP-DEBUG> l2open <MAC> <PSM>        # open L2CAP connection
BLEEP-DEBUG> l2send <data>             # send data
BLEEP-DEBUG> l2recv [--timeout N]      # receive data
BLEEP-DEBUG> l2raw <MAC> <PSM>         # interactive L2CAP session
BLEEP-DEBUG> l2listen <PSM>            # listen for incoming connections
```

These mirror the existing `copen` / `csend` / `crecv` / `craw` RFCOMM
commands.

### 4.3  CLI Commands (Future)

```bash
python -m bleep.cli l2cap-connect AA:BB:CC:DD:EE:FF 17 --security medium
python -m bleep.cli l2cap-send AA:BB:CC:DD:EE:FF 17 "hex:0102030405"
python -m bleep.cli l2cap-listen 0x1001 --timeout 30
```

### 4.4  PSM Discovery via SDP

Dynamic L2CAP PSMs are discovered through SDP.  The existing
`classic_sdp.py` / `csdp` infrastructure already parses SDP records.  A
helper to extract L2CAP PSMs (in addition to the existing RFCOMM channel
extraction) would be added:

```python
def extract_l2cap_psms(sdp_records: dict) -> Dict[str, int]:
    """Extract L2CAP PSM values from SDP service records."""
    ...
```

---

## 5  Implementation Phases

| Phase | Scope                                        | Version  |
|-------|----------------------------------------------|----------|
| 5.1   | `l2cap_open()` + `l2cap_listen()` functions  | v2.7.13  |
| 5.2   | `L2capConnection` context manager             | v2.7.13  |
| 5.3   | Security level helpers + constants            | v2.7.13  |
| 5.4   | Debug commands (`l2open`, `l2send`, etc.)     | v2.7.14  |
| 5.5   | CLI subparsers                                | v2.7.14  |
| 5.6   | SDP L2CAP PSM extraction helper              | v2.7.14  |
| 5.7   | Unit tests with loopback sockets             | v2.7.14  |
| 5.8   | BLE L2CAP CoC support (LE mode)              | v2.7.15+ |

---

## 6  Testing Strategy

* **Unit tests** (no hardware): use local L2CAP sockets in loopback mode
  (requires root/CAP_NET_RAW) or mock sockets for pure codec testing.
* **Integration tests**: connect to a known device and verify PSM-level
  communication (e.g., SDP queries on PSM 0x0001).
* **BLE L2CAP CoC tests**: require a BLE peripheral advertising a CoC
  service.

---

## 7  Security Considerations

* L2CAP sockets to well-known PSMs (0x0001–0x001F) may require elevated
  privileges (root or `CAP_NET_RAW` + `CAP_NET_ADMIN`).
* Dynamic PSMs (≥ 0x1001) are generally accessible without special privileges
  after pairing.
* The security level should be set **before** `connect()` to ensure the
  link is established at the desired security level.
* Server sockets (`l2cap_listen`) should use `BT_SECURITY_MEDIUM` or higher
  to require authentication before accepting connections.

---

## 8  Platform Notes

* **Linux only** — `AF_BLUETOOTH` / `BTPROTO_L2CAP` are Linux kernel
  features.  macOS and Windows use different Bluetooth APIs.
* **Python `socket` module** — Python exposes `AF_BLUETOOTH`, `BTPROTO_L2CAP`,
  and `BTPROTO_RFCOMM` on Linux.  Socket options require `struct.pack()` for
  the value parameter since Python doesn't have native Bluetooth sockopt
  wrappers.
* **BlueZ version** — `BT_MODE` and `BT_PHY` require BlueZ ≥ 5.50 / kernel
  ≥ 5.10.  ERTM mode may require `bluetooth.conf` configuration.

---

## 9  References

* Linux Bluetooth socket API: `include/net/bluetooth/bluetooth.h`,
  `include/net/bluetooth/l2cap.h`
* BlueZ `l2cap.rst` documentation (see `workDir/BlueZDocs/l2cap.rst`)
* BlueZ `hci.rst` documentation (see `workDir/BlueZDocs/hci.rst`)
* Bluetooth SIG Assigned Numbers: `References/psm.yaml`
* BLEEP RFCOMM connector: `bleep/ble_ops/classic_connect.py:classic_rfccomm_open()`
* Python `socket` module: https://docs.python.org/3/library/socket.html
