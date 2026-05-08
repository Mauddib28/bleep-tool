# PAN Connection Analysis: BlueZ Source Findings & Requirements

**Date:** 2026-04-01
**Status:** Reference — findings from BlueZ 5.x source code audit and live testing
**Scope:** `Network1.Connect()` client lifetime, `NetworkServer1.Register()` server
lifetime, BNEP transport reliability, and comparison with Agent Pairing D-Bus issues

---

## 1  Executive Summary

Live testing of BLEEP's PAN implementation revealed that `Network1.Connect()`
returns a nominal interface name (`bnep0`) but the BNEP session drops
immediately — `Connected` reads `False` within milliseconds and no `bnep0`
interface appears in `ip addr show`.

A deep audit of the BlueZ C source code was conducted to determine whether the
failure was caused by D-Bus client lifetime (the calling process exiting the
bus) or by a lower-layer BNEP/L2CAP transport issue.  The key findings:

| Aspect | Client (`Network1.Connect`) | Server (`NetworkServer1.Register`) |
|--------|----------------------------|-------------------------------------|
| D-Bus disconnect watch on caller | **No** — not implemented | **Yes** — `g_dbus_add_disconnect_watch()` |
| Connection survives caller exit | Yes (tied to BT device) | No (registration removed) |
| Process must stay alive | No | **Yes** |

The observed failures are therefore **not** caused by the D-Bus client exiting.
They originate at the BNEP/L2CAP transport layer — the remote device refuses
or immediately drops the PAN role negotiation.

---

## 2  BlueZ Source Evidence

All file paths below are relative to the BlueZ source tree (`workDir/bluez/`).

### 2.1  Client: `profiles/network/connection.c`

This file implements the `Network1` D-Bus interface (the client/per-device side).

**Key function:** `connection_connect()` — handler for `Network1.Connect(role)`

The connection flow is:

```
Network1.Connect(role)
  → connection_connect()         [connection.c]
    → bt_bnep_connect()          [bnep.c — L2CAP socket + BNEP setup]
      → bnep_setup_cb()          [callback on BNEP handshake completion]
        → bnep_if_up()           [brings up the bnep0 interface]
```

**Critical finding:** `connection_connect()` does **not** call
`g_dbus_add_disconnect_watch()` on `dbus_message_get_sender(msg)`.  The
connection's lifetime is managed by:

- `device_add_disconnect_watch()` — watches the **Bluetooth device** disconnect
  (HCI level), not the D-Bus caller
- `bnep_disconn_cb()` — internal BNEP session teardown callback

This means the BNEP connection is **not** automatically torn down when the
calling D-Bus client process exits the system bus.  The connection persists as
long as the underlying Bluetooth link and BNEP session remain up.

### 2.2  Server: `profiles/network/server.c`

This file implements the `NetworkServer1` D-Bus interface (per-adapter).

**Key function:** `register_server()` — handler for `NetworkServer1.Register(role, bridge)`

**Critical finding:** Line ~564 explicitly calls:

```c
g_dbus_add_disconnect_watch(conn, sender, server_disconnect, ns, NULL);
```

where `server_disconnect()` calls `server_remove_handler()`, tearing down the
server registration.  This confirms that **server registrations are tied to the
D-Bus caller's process lifetime** — when the process exits (or its unique bus
name vanishes), BlueZ automatically unregisters the server.

### 2.3  How BlueZ uses disconnect watches elsewhere

The `g_dbus_add_disconnect_watch()` pattern is used extensively across BlueZ
for features where a D-Bus client "owns" a registration:

| Feature | Source file | Watches caller? |
|---------|------------|----------------|
| Discovery (`StartDiscovery`) | `src/adapter.c` | Yes |
| Bonding (`Pair`) | `src/device.c` | Yes |
| Agent (`RegisterAgent`) | `src/agent.c` | Yes |
| GATT client (AcquireWrite/Notify) | `src/gatt-client.c` | Yes |
| Profile registration | `src/profile.c` | Yes |
| **PAN client (`Network1.Connect`)** | **`profiles/network/connection.c`** | **No** |
| **PAN server (`NetworkServer1.Register`)** | **`profiles/network/server.c`** | **Yes** |

The absence of a disconnect watch in the PAN client path is deliberate — a
completed BNEP connection is a kernel-level network interface (`bnep0`) managed
by the `bnep` kernel module, not by the D-Bus caller.

### 2.4  BlueZ documentation vs. source code

The BlueZ D-Bus documentation (`org.bluez.Network.rst`) states:

> "The connection will be closed and the network device is released either
> upon calling Disconnect() or when the client disappears from the message
> bus."

This statement is **misleading for the client path** in the current BlueZ 5.x
source code.  The "client disappears" clause likely refers to the server-side
behaviour (where the disconnect watch IS present) or is a holdover from an
earlier BlueZ version.

The reference test scripts reinforce the confusion:

- `workDir/BlueZScripts/test-network` (PAN client) — calls `time.sleep()` in a
  loop after `Connect()`, suggesting the authors believed the connection needed
  the process alive.  However, based on the source code, this sleep is
  unnecessary for maintaining the BNEP connection itself.
- `workDir/BlueZScripts/test-nap` (PAN server) — calls `mainloop.run()` after
  `Register()`.  This IS required because the server registration has a
  disconnect watch.

---

## 3  BNEP Transport Failure Analysis

### 3.1  Observed behaviour

Testing against device `84:5F:04:45:36:12` from BLEEP debug mode:

```
cpan connect panu
[PAN] Connected – interface bnep0     ← BlueZ returned bnep0
cpan status
  Connected : False                   ← Already disconnected
  Interface : None
  UUID/Role : None
```

Three separate `ip addr show` checks over ~2 minutes confirmed no `bnep0`
interface ever appeared on the system.  The `cpan disconnect` attempt returned
`org.bluez.Error.NotConnected`.

Both `panu` and `nap` roles were attempted — identical failure pattern.

### 3.2  Root cause

Since the D-Bus client lifetime is **not** the cause (§2.1), the failure must
be in the BNEP/L2CAP transport path:

1. **L2CAP connection to PSM 0x000F (BNEP)** — may succeed momentarily then
   drop, or the remote may refuse the L2CAP connection entirely
2. **BNEP setup negotiation** — the remote may reject the BNEP Setup Request
   (role mismatch, unsupported features, or policy)
3. **Remote device not running a PAN service** — if the SDP record advertises
   PAN but the service is not actually active, the L2CAP connection succeeds
   but BNEP setup fails

BlueZ's `Network1.Connect()` returns the interface name **optimistically** from
`bt_bnep_connect()` before the BNEP handshake fully completes (the D-Bus reply
is sent from `connection_connect()` after the L2CAP socket is created).  The
actual BNEP setup completes asynchronously via `bnep_setup_cb()`.  If the
setup fails, the `Connected` property transitions to `False` but the original
`Connect()` call has already returned successfully.

### 3.3  Mitigation in BLEEP

`NetworkClient.connect()` now performs a post-connect verification:

```python
if verify:
    time.sleep(0.5)
    if not self.connected:
        raise RuntimeError(
            f"PAN Connect to {self.mac} returned interface "
            f"'{iface_name}' but the BNEP session did not persist ..."
        )
```

This catches the "optimistic success" scenario by waiting 500 ms for the
asynchronous BNEP setup to either stabilise or fail, then checking the
`Connected` property.

---

## 4  Comparison with Agent Pairing D-Bus Issues

BLEEP previously encountered D-Bus dispatch issues with Agent Pairing.  A
comparison confirms that those issues **do not apply** to PAN operations.

### 4.1  Agent Pairing problem (resolved)

The Agent Pairing issues stemmed from:

1. **`dbus.service.Object` method handlers** (e.g., `RequestPinCode`,
   `RequestPasskey`) require `GLib.MainLoop().run()` executing on the **main
   thread** to dispatch incoming D-Bus method calls.
2. **Message filter interference** — certain D-Bus message filters could
   intercept agent messages before the service object handler received them.

These are documented in:
- `bleep/docs/mainloop_architecture.md`
- `bleep/docs/mainloop_requirement_analysis.md`
- `bleep/docs/agent_dbus_communication_issue.md`

### 4.2  Why PAN client is not affected

PAN client operations (`Network1.Connect`, `Network1.Disconnect`) are
**outgoing D-Bus method calls** — BLEEP calls a method on BlueZ and waits for
the return value.  No `dbus.service.Object` is registered.  No incoming
method calls need to be dispatched.  Therefore:

- No `GLib.MainLoop` is needed for PAN client operations
- No main-thread requirement exists
- No message filter interference is possible
- A background thread or CLI process can safely call `Connect()`/`Disconnect()`

### 4.3  PAN server considerations

`NetworkServer1.Register()` and `Unregister()` are also **outgoing method
calls** (BLEEP → BlueZ).  BlueZ handles incoming PAN client connections
internally — it does not call back into the registering application via D-Bus
method invocations.  Therefore:

- No `dbus.service.Object` is registered for PAN server either
- No `GLib.MainLoop` is needed
- The only requirement is that the **process stays alive** (to keep its D-Bus
  bus name active), which is satisfied by `signal.pause()` in CLI mode and
  by retaining the `NetworkServer` on `DebugState.pan_server` in debug mode

---

## 5  Requirements for a Working PAN NAP Connection

Based on the BlueZ source analysis, Bluetooth specification, and observed
failure modes, a successful PAN client connection requires ALL of the following:

### 5.1  Local (BLEEP host) requirements

| Requirement | How to verify | BLEEP status |
|-------------|--------------|-------------|
| BlueZ ≥ 5.55 running | `bluetoothctl --version` | Assumed (documented prerequisite) |
| `bnep` kernel module loaded | `lsmod \| grep bnep` | Not checked by BLEEP |
| Adapter powered and up | `hciconfig hci0` or BLEEP preflight | Checked |
| Device paired and trusted | `bluetoothctl info <MAC>` | Assumed (documented prerequisite) |

### 5.2  Remote device requirements

| Requirement | How to verify | Notes |
|-------------|--------------|-------|
| Remote runs a PAN NAP/PANU/GN service | SDP query for UUID 0x1115/0x1116/0x1117 | BLEEP can check via `csdp` / `classic-sdp` |
| Remote accepts BNEP connections on PSM 0x000F | Attempt connection | No pre-check possible |
| Remote supports requested role | Match local role to remote capability | NAP↔PANU or GN↔GN |
| Remote PAN service is actually active (not just advertised) | Attempt connection | SDP may advertise inactive services |

### 5.3  Role compatibility matrix

| Local role | Remote must support | Typical scenario |
|-----------|-------------------|-----------------|
| `nap` | NAP (0x1116) | Phone sharing internet to laptop |
| `panu` | PANU (0x1115) | Peer-to-peer networking |
| `gn` | GN (0x1117) | Group ad-hoc network |

The most common real-world scenario is a laptop (PANU client) connecting to a
phone (NAP server) for internet tethering.  In this case, BLEEP should connect
with role `nap` (requesting the remote's NAP service):

```bash
python -m bleep.cli classic-pan connect <PHONE_MAC> --role nap
```

### 5.4  PAN server requirements (hosting from BLEEP)

| Requirement | How to satisfy |
|-------------|---------------|
| Linux bridge interface exists | `sudo brctl addbr pan0 && sudo ip link set pan0 up` |
| IP forwarding enabled (for NAP) | `echo 1 > /proc/sys/net/ipv4/ip_forward` |
| NAT/masquerade configured (for NAP) | `iptables -t nat -A POSTROUTING -o <WAN_IF> -j MASQUERADE` |
| DHCP server on bridge (for NAP) | `dnsmasq --interface=pan0 --dhcp-range=...` |
| BLEEP process stays alive | `classic-pan serve` blocks with `signal.pause()` |

---

## 6  Diagnostic Checklist

When a PAN `connect` fails (post-verification catches it), run through:

1. **Is the device paired and trusted?**
   ```bash
   bluetoothctl info <MAC>
   ```
   Look for `Paired: yes` and `Trusted: yes`.

2. **Does the device advertise a PAN service?**
   ```
   BLEEP-DEBUG> csdp
   ```
   Look for UUIDs `0x1115` (PANU), `0x1116` (NAP), or `0x1117` (GN).

3. **Is the `bnep` kernel module loaded?**
   ```bash
   lsmod | grep bnep
   sudo modprobe bnep   # if not loaded
   ```

4. **Is the remote's PAN service actually active?**
   On Android: Settings → Network → Bluetooth Tethering (must be enabled).
   On iOS: PAN is not supported.

5. **Check BlueZ logs for L2CAP/BNEP errors:**
   ```bash
   sudo journalctl -u bluetooth -f
   ```
   Look for `BNEP`, `L2CAP`, or `bnep0` messages during the connection attempt.

6. **Try the BlueZ reference script directly:**
   ```bash
   sudo python3 workDir/BlueZScripts/test-network <MAC> nap
   ```
   If this also fails, the issue is between BlueZ and the remote device — not
   in BLEEP's code.

---

## 7  Related Documentation

- [Network capability summary](network_capability_summary.md) — implementation overview and status
- [Network capability plan](network_capability_plan.md) — original design plan (Phases 2-5 future work)
- [Bluetooth Classic mode](bl_classic_mode.md) §2.9 — user-facing `cpan` / `classic-pan` docs
- [Mainloop architecture](mainloop_architecture.md) — GLib MainLoop and agent dispatch (for contrast)
- [Agent D-Bus communication issue](agent_dbus_communication_issue.md) — historical agent pairing analysis
- [D-Bus best practices](dbus_best_practices.md) — general BlueZ D-Bus reliability patterns
- [Changelog](changelog.md) — "PAN Reliability Fixes" section
