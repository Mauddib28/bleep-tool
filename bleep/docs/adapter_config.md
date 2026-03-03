---
description: Guide for local Bluetooth adapter configuration in BLEEP
---

# Adapter Configuration in **BLEEP**

BLEEP provides runtime access to all configurable properties of the local
Bluetooth adapter through a tiered tool strategy:

| Tier | Mechanism | Permissions | Use Case |
|------|-----------|------------|----------|
| **1 — D-Bus** | `Properties.Set()` on `org.bluez.Adapter1` | Standard user | Alias, Powered, Discoverable, Pairable, Connectable, timeouts |
| **2 — bluetoothctl mgmt** | Kernel management socket via subprocess | Root / `CAP_NET_ADMIN` | Class, local-name, SSP, SC, LE/BR/EDR toggle, privacy, PHY |
| **3 — main.conf** | `/etc/bluetooth/main.conf` (read-only) | Standard user (read) | Boot-time defaults inspection |

---

## 1  Prerequisites

* BlueZ ≥ 5.55 (tested 5.66+)
* `bluetoothctl` in `$PATH` (required for mgmt operations)
* Root or `CAP_NET_ADMIN` for management-socket operations (Class, local-name, etc.)

---

## 2  CLI Reference

### 2.1  Show all properties

```bash
bleep adapter-config show
bleep adapter-config show --adapter hci1
```

Displays all D-Bus adapter properties, lists writable properties by tier,
and shows active boot defaults from `/etc/bluetooth/main.conf`.

### 2.2  Get a single property

```bash
bleep adapter-config get alias
bleep adapter-config get class
bleep adapter-config get discoverable-timeout
```

### 2.3  Set a property

**D-Bus properties (no root required):**

```bash
bleep adapter-config set alias "MyBleepDevice"
bleep adapter-config set alias ""                   # reset to system name
bleep adapter-config set discoverable on
bleep adapter-config set discoverable off
bleep adapter-config set pairable on
bleep adapter-config set connectable off            # also forces discoverable off
bleep adapter-config set discoverable-timeout 300   # seconds; 0 = forever
bleep adapter-config set pairable-timeout 0         # 0 = stay pairable forever
```

**Management-socket properties (requires root/CAP_NET_ADMIN):**

```bash
sudo bleep adapter-config set class 1 4             # Computer / Desktop
sudo bleep adapter-config set class 4 1             # Audio / Headset
sudo bleep adapter-config set local-name "BleepBox" # kernel-level name
sudo bleep adapter-config set local-name "BleepBox" "Blp"  # with short name
sudo bleep adapter-config set ssp on
sudo bleep adapter-config set sc only               # on / off / only
sudo bleep adapter-config set le on
sudo bleep adapter-config set bredr off
sudo bleep adapter-config set privacy on
sudo bleep adapter-config set fast-conn on
sudo bleep adapter-config set linksec on
sudo bleep adapter-config set wbs on
```

---

## 3  Property Reference

### 3.1  D-Bus Readable Properties (all readonly unless noted)

| Property | Type | Writable | Description |
|----------|------|----------|-------------|
| Address | string | No | Hardware MAC address |
| AddressType | string | No | "public" or "random" |
| Name | string | No | System name (pretty hostname) |
| **Alias** | string | **Yes** | Friendly name visible to remote devices. Overrides Name. Set to `""` to reset. |
| Class | uint32 | No (D-Bus) | 24-bit Class of Device. Writable only via mgmt. |
| **Powered** | bool | **Yes** | Adapter power state |
| **Connectable** | bool | **Yes** | Accept incoming connections. Setting to False also clears Discoverable. |
| **Discoverable** | bool | **Yes** | Visible to scanning devices |
| **DiscoverableTimeout** | uint32 | **Yes** | Seconds before auto-disabling discoverable (0 = forever, default 180) |
| **Pairable** | bool | **Yes** | Accept pairing requests |
| **PairableTimeout** | uint32 | **Yes** | Seconds before auto-disabling pairable (0 = forever, default 0) |
| Discovering | bool | No | Whether a discovery session is active |
| UUIDs | array | No | Available local service UUIDs |
| Modalias | string | No | USB/BT vendor info |
| Roles | array | No | Supported roles (central, peripheral) |

### 3.2  Management-Socket Properties

These are **not exposed** through D-Bus `Properties.Set()` and require the
kernel management socket (`bluetoothctl mgmt.*`).

| Property | Values | Description |
|----------|--------|-------------|
| class | `<major> <minor>` | Device class (e.g., 1 4 = Computer/Desktop) |
| local-name | `<name> [shortname]` | Sets a **temporary** Alias via the kernel mgmt socket (does not persist across daemon restarts; use D-Bus `Alias` for persistent changes) |
| ssp | on/off | Secure Simple Pairing |
| sc | on/off/only | Secure Connections |
| le | on/off | LE transport support |
| bredr | on/off | BR/EDR transport support |
| privacy | on/off | LE privacy (random addresses) |
| fast-conn | on/off | Fast Connectable (reduced page scan interval) |
| linksec | on/off | Link-level security |
| wbs | on/off | Wideband Speech (HFP) |

### 3.3  Common Class of Device Values

| Major | Minor | Hex | Description |
|-------|-------|-----|-------------|
| 1 | 0 | 0x000100 | Computer (uncategorized) |
| 1 | 4 | 0x000104 | Computer / Desktop |
| 1 | 8 | 0x000108 | Computer / Server |
| 2 | 0 | 0x000200 | Phone (uncategorized) |
| 2 | 4 | 0x000204 | Phone / Cellular |
| 4 | 1 | 0x000404 | Audio / Headset |
| 4 | 6 | 0x000418 | Audio / Headphones |
| 4 | 3 | 0x00040C | Audio / Loudspeaker |
| 5 | 1 | 0x000504 | Peripheral / Keyboard |
| 5 | 2 | 0x000508 | Peripheral / Pointing device |

---

## 4  Python API

All configuration methods live on `system_dbus__bluez_adapter`:

```python
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter

adapter = system_dbus__bluez_adapter("hci0")

# Read all properties
info = adapter.get_adapter_info()

# D-Bus getters
adapter.get_alias()
adapter.get_name()
adapter.get_class()
adapter.get_discoverable()

# D-Bus setters
adapter.set_alias("MyDevice")
adapter.set_discoverable(True)
adapter.set_discoverable_timeout(0)

# Management-socket setters (require root)
adapter.set_class(1, 4)              # Computer / Desktop
adapter.set_local_name("BleepBox")
adapter.set_ssp(True)
adapter.set_secure_connections("only")
adapter.set_le(True)
adapter.set_bredr(True)
```

---

## 5  Boot Defaults (`main.conf`)

`/etc/bluetooth/main.conf` controls daemon-level defaults applied at BlueZ
startup.  BLEEP reads this file for informational display only (no writes).

Key settings in `[General]`:

| Setting | Default | Description |
|---------|---------|-------------|
| Name | BlueZ X.YZ | Default adapter name |
| Class | 0x000000 | Default device class |
| DiscoverableTimeout | 180 | Seconds |
| PairableTimeout | 0 | Seconds (0 = forever) |
| ControllerMode | dual | dual / bredr / le |
| Privacy | off | off / network / device |
| FastConnectable | false | Reduced page scan interval |
| SecureConnections | on | on / off / only |

Changes to `main.conf` require a BlueZ daemon restart:
`sudo systemctl restart bluetooth`

---

## 6  Architecture Notes

* **D-Bus path** (`Properties.Set`) is preferred for all writable properties
  because it is in-process, fast, and requires no subprocess overhead.
* **bluetoothctl mgmt** is used only for properties not reachable via D-Bus
  (Class, security toggles).  It talks to the kernel management socket
  (`MGMT_OP_*` commands), the same mechanism BlueZ daemon uses internally.
* **hciconfig** is deprecated by BlueZ; BLEEP uses it only in `recovery.py`
  for legacy controller reset.  New features use `bluetoothctl mgmt.*` instead.
* **Alias vs Name vs local-name**: `Name` is the system hostname and is
  read-only on D-Bus.  `Alias` (D-Bus writable) overrides `Name` for what
  remote devices see, and is **persisted** in the adapter settings file
  (`/var/lib/bluetooth/<addr>/settings`).  `mgmt.name` sends
  `MGMT_OP_SET_LOCAL_NAME` to the kernel, but the daemon's
  `local_name_changed_callback` (adapter.c:924-948) treats this as a
  `current_alias` update — a **temporary** alias that lasts only for the
  lifetime of the `bluetoothd` process and does not persist.  For persistent
  name changes, use D-Bus `Alias` (`set_alias()`).  `mgmt.name` is retained
  for completeness but is generally not preferred over `set_alias()`.
