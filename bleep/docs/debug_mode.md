# Debug mode

Debug mode drops you into an **interactive shell** with helpers for inspecting BlueZ D-Bus objects, reading characteristics, and monitoring property changes in real-time.

## Launch

Debug mode is reachable in two equivalent forms — pick whichever fits the
context.  The `bleep debug` subcommand is the canonical, discoverable form
(`bleep --help` lists it alongside every other mode); the `python -m`
form remains supported unchanged for scripts and CI that already depend
on it:

```bash
bleep debug --help                          # canonical form
bleep debug CC:50:E3:B6:BC:A6               # auto-connect to target

python -m bleep.modes.debug --help          # equivalent (legacy / scripting)
python -m bleep.modes.debug CC:50:E3:B6:BC:A6
```

Key flags:

| Flag | Description |
|------|-------------|
| `<MAC>` | Auto-connect to device at the specified MAC address |
| `--no-connect` | Start shell without connecting |
| `--monitor` or `-m` | Spawn background monitor printing property change events |
| `--detailed` or `-d` | Show detailed information including decoded UUIDs |

Once inside the prompt (`BLEEP-DEBUG>`):

**Connection & Device Info**

| Command | Purpose |
|---------|---------|
| `connect <MAC>` | BLE connect + GATT enumerate (use `cconnect` for Classic) |
| `disconnect` | Disconnect from the current device |
| `info` | Show current device properties |

**BLE Scanning** (see [Scan Modes](ble_scan_modes.md))

| Command | Purpose |
|---------|---------|
| `scan [--timeout N]` | Passive scan then list devices (default 10 s) |
| `scann [--timeout N]` | Naggy scan (duplicate adverts) |
| `scanp <MAC> [--timeout N]` | Pokey scan (repeated short bursts targeting one device) |
| `scanb [--timeout N]` | Brute scan (BR/EDR inquiry + LE naggy; default 20 s) |
| `dscan [--timeout N]` | Dual scan — combined LE + BR/EDR discovery in a single session (`debug_scan.py`) |
| `advertise-monitor caps` | Show `AdvertisementMonitorManager1` capabilities |
| `advertise-monitor start [options]` | Register kernel-offloaded pattern/RSSI monitor(s) and stream `DeviceFound`/`DeviceLost` until Ctrl-C |
| `survey start [--duration N] [--round-time N] [-o FILE] \| survey stop` | Start/stop a long-duration background LE+Classic device census (mirrors CLI `survey`). `--collector` / `--enumerator` / `--listen-monitor` are refused here — run those from the CLI. |
| `survey-status` | Show survey progress and device counts |

All four scan verbs accept an optional `--timeout`/`-t` (parity with `bleep scan --timeout`); omitting it preserves each verb's historical default.

`advertise-monitor` is the kernel-offloaded **Advertisement** Monitor (parity with the CLI `bleep advertise-monitor`), and is distinct from the `monitor` command below, which toggles a live `PropertiesChanged` **device-property** monitor. `start` options mirror the CLI: `[-p OFF:AD:HEX ...]` (omit `-p` for Flags-OR overlay — one monitor, not a BlueZ match-all), `--manufacturer CID[:HEX]`, `--mfr-string TEXT`, `--rssi-high`/`--rssi-low` (+ their `-timeout`), `--sampling-period`, `--duration`, `--adapter`. Survey `--listen-monitor` is CLI-only.

**BLE Enumeration** (see [GATT Enumeration](gatt_enumeration.md))

| Command | Purpose |
|---------|---------|
| `enum <MAC>` | One-shot GATT read of every readable characteristic |
| `enumn <MAC>` | Naggy enumeration (3× read pass, detects changing values) |
| `enump <MAC> [--rounds N]` | Pokey enumeration (light write probes after each round) |
| `enumb <MAC> <CHAR>` | Brute-force write enumeration of a **single** characteristic (ROE off). Fuzzing **all** writable characteristics is CLI-only: `bleep enum-scan <MAC> --variant brute --write-char all` |
| `mines` | Display current landmine/permission maps |
| `explore [MAC] [--out F] [--conn-mode passive\|naggy] [--timeout N]` | Scan & dump GATT DB to JSON (mirrors CLI `explore`; MAC defaults to current device) |

**GATT Interaction**

| Command | Purpose |
|---------|---------|
| `services` | List primary services |
| `chars [<svc-uuid>]` | List characteristics (optionally filtered by service) |
| `char <uuid>` | Show details for a single characteristic |
| `read <char>` | Read characteristic by handle/UUID |
| `write <char> <hex\|ascii>` | Write bytes/ASCII to characteristic |
| `notify <char>` | Subscribe to notifications (quick toggle) |
| `signal <char> [--time N]` | Timed notification listener on the current device, no reconnect (mirrors CLI `signal`) |
| `detailed` | Toggle verbose output (hex dumps, decoded UUIDs) |
| `multiread <char> [rounds]` | Multi-read a single characteristic |
| `multiread_all [rounds]` | Multi-read all readable characteristics |
| `brutewrite <char> [options]` | Brute-force write to a characteristic |

**Classic Bluetooth** (see [Classic Mode](bl_classic_mode.md))

| Command | Purpose |
|---------|---------|
| `cscan [--uuid U] [--rssi N] [--pathloss N] [--timeout N] [--adapter hciX] [--debug]` | Classic (BR/EDR) inquiry scan — delegates to the shared `classic_scan.run` (mirrors CLI `classic-scan`); UUID/RSSI/path-loss discovery filters + observation-DB persistence |
| `cconnect <MAC>` | Classic connect (SDP + RFCOMM fallback) |
| `cservices` | List RFCOMM services |
| `csdp [MAC]` | SDP browse / query (raw socket) |
| `cenum [MAC] [--version-info] [--analyze] [--sdp-source S] [--connectionless]` | Rich SDP enumeration/analysis (mirrors CLI `classic-enum`; MAC defaults to current device) |
| `ckeep` | Open RFCOMM keepalive socket |
| `pbap [MAC]` | Download phone-book via PBAP |
| `copp <send\|pull\|exchange>` | Object Push Profile operations |
| `cmapinfo` | Show MAP version, features & BlueZ compatibility info |
| `cmap <subcommand>` | Message Access Profile operations |
| `cftp <subcommand>` | OBEX File Transfer operations |
| `csync <get\|put>` | IrMC Sync operations |
| `cbip <props\|get\|thumb>` | Basic Imaging Profile operations |
| `netenum [--adapter hciX] [--all-devices] [--json]` | Enumerate PAN network capability across adapters/devices (mirrors CLI `network-enum`) |
| `cping <MAC> [--count N] [--timeout N]` | L2CAP echo (l2ping) reachability test (mirrors CLI `classic-ping`) |
| `cpan <subcommand>` | Personal Area Networking: `connect` / `disconnect` / `status` / `server-reg` / `server-unreg` (alias: `server register`/`server unregister`) |
| `cprofiles` | List Device1.UUIDs (advertised profiles) with resolved names |
| `cprofile connect\|disconnect <UUID>` | Connect/disconnect a specific profile by UUID |
| `chid [MAC]` | HID classification: connected device, or connectionless when given a `MAC` (mirrors CLI `hid-info`) |
| `cspp <subcommand>` | Serial Port Profile operations (`--auth`/`--no-auth`) |
| `crfcomm [--probe] [--timeout N]` | List RFCOMM channels via SDP, optionally probe endpoints (mirrors CLI `classic-rfcomm`) |
| `cbind <ch> [--device N] \| release [N] \| list` | Persistent RFCOMM `/dev/rfcommN` binding |
| `copen / csend / crecv / craw` | Raw RFCOMM channel operations |

**Media & Audio**

| Command | Purpose |
|---------|---------|
| `mediaenum` | List media D-Bus objects for the connected device (mirrors CLI `media-enum`) |
| `mediaprops` | Show `MediaControl`/`MediaPlayer`/`MediaTransport` properties |
| `mediactrl <play\|pause\|stop\|next\|prev\|volume\|info\|press> [val]` | AVRCP media-player control (mirrors CLI `media-ctrl`) |
| `audiorecon [--mac MAC] [--file F] [--no-play] [--no-record]` | Audio reconnaissance: backend, cards, play/record (mirrors CLI `audio-recon`) |
| `audioplay <file> [--system] [--volume N] [--direct] [--codec C]` | Play an audio file to the connected BT device (mirrors CLI `audio-play`) |
| `audiorec <output> [--system] [--duration N] [--direct] [--hfp] [--keep-profile]` | Record audio from the connected BT device (mirrors CLI `audio-record`) |

**Pairing**

| Command | Purpose |
|---------|---------|
| `agent status\|register\|unregister` | Register / manage the BlueZ pairing agent (session verbs) |
| `agent trust\|untrust\|remove-bond <MAC>` | Device management, delegates to the shared CLI `agent` core (mirrors `bleep agent --trust/--untrust/--remove-bond`) |
| `agent list-trusted\|list-bonded` | List trusted / bonded devices (mirrors CLI `agent --list-trusted/--list-bonded`) |
| `pair <MAC> [options]` | Pair with device and connect for exploration |

**D-Bus Navigation & Introspection**

| Command | Purpose |
|---------|---------|
| `ls [path]` | List D-Bus objects at path |
| `cd [path]` | Change current D-Bus path |
| `pwd` | Show current D-Bus path |
| `back` | Return to the previous D-Bus path (pops the `cd` history) |
| `interfaces [path]` | List interfaces on an object |
| `props [interface]` | Show properties for an interface |
| `methods [interface]` | List methods on an interface |
| `signals <interface>` | Introspect a **named interface** and list *its* D-Bus signals |
| `introspect [path]` | Pretty-print XML introspection data |
| `call <iface> <method> [args]` | Call D-Bus method directly |
| `monitor [start\|stop]` | Start/stop device `PropertiesChanged` monitoring (bare `monitor` = **start**; distinct from `advertise-monitor`) |

**Database & AoI**

| Command | Purpose |
|---------|---------|
| `aoi [--save] [MAC]` | Live AoI analysis on current/specified device (default helper) |
| `aoi <scan\|analyze\|list\|report\|export\|db> [...]` | Full AoI pipeline — delegates to the shared `aoi.run` (mirrors CLI `bleep aoi <subcommand>`) |
| `dbsave` | Save current session data to observation database (session helper) |
| `dbexport [--save]` | Print the observation-DB summary for the **currently connected** device; `--save` also writes `bleep_debug_export_<MAC>.json` (requires a connected device; no MAC argument) |
| `db <list\|show\|timeline\|export\|report\|uuids\|maintain> [MAC] [opts]` | Full observation-DB query/maintenance surface (mirrors CLI `bleep db`, incl. `db report`, via `parse_as_cli`; terminal output) |

**Utilities**

| Command | Purpose |
|---------|---------|
| `uuidtr <uuid...> [--json] [--verbose] [--include-unknown]` | Translate UUID(s) to human-readable names (mirrors CLI `uuid-translate`) |
| `adaptercfg [show \| get <prop> \| set <prop> <val...>] [--adapter hciX]` | View/modify local adapter configuration (mirrors CLI `adapter-config`) |
| `audiocfg [--endpoints]` | Host audio-backend + BT audio-stack readiness diagnostics (read-only) |
| `audiocfg <show\|add\|remove\|tunnel\|backup\|restore> [...]` | Manage ALSA/BlueALSA config (mirrors CLI `audio-config`) |

**Local Roles, Broadcast & Advanced**

Each mirrors the corresponding CLI subcommand (`bleep gatt-server` / `advertise` / `audio-intercept` / `device-sets` / `mesh` / `ctf`). `gattserver`/`advertise` run the shared core's own foreground GLib loop — the debug shell hands the loop off and restores Ctrl-C on exit (same handoff as `advertise-monitor start`).

| Command | Purpose |
|---------|---------|
| `gattserver start [--uuid U ...] [--name N] [--read-value HEX] [--duration N]` | Publish a local GATT server until Ctrl-C |
| `advertise caps \| start [options]` | Broadcast custom LE advertisements until Ctrl-C |
| `audiointercept [MAC] [--duration N] [--engine whisper\|vosk] [--no-transcribe]` | Capture/optionally transcribe audio from a BT device (MAC defaults to current device) |
| `devicesets [list \| connect <path> \| disconnect <path> \| info <path>]` | Manage `DeviceSet1` coordinated sets (e.g. TWS earbuds) |
| `mesh [join <uuid> \| provision <uuid> \| reprovision <unicast> --node-path P]` | Bluetooth Mesh provisioning (experimental) |
| `ctf [--device MAC] [--discover] [--solve] [--visualize] [--interactive]` | BLE CTF solver/analyzer (secondary interaction path) |

**General**

| Command | Purpose |
|---------|---------|
| `help` | Show full built-in command list |
| `quit` / `Ctrl-D` | Exit debug shell |

Exit with `Ctrl-D` or `quit`.

### Pairing with the `pair` Command

The `pair` command registers a BlueZ agent, initiates pairing, and handles PIN/passkey exchange.  After pairing, it **connects the device and returns to the shell** so you can explore with `info`, `interfaces`, `props`, etc.

Use `--test` for the legacy PoC behaviour (pair + auto-disconnect monitor).

#### Operational Mode (default)

After pairing succeeds the command auto-detects the device transport and attempts to maintain a persistent connection:

- **BR/EDR Classic**: SDP enumeration + RFCOMM keepalive socket
- **BLE**: standard GATT connect + service enumeration

```bash
pair D8:3A:DD:0B:69:B9                           # default PIN 0000, connect after
pair D8:3A:DD:0B:69:B9 --pin 12345               # custom PIN
pair D8:3A:DD:0B:69:B9 --passkey 123456          # LE passkey (uint32)
pair D8:3A:DD:0B:69:B9 --pin 12345 --timeout 90  # extend timeout
pair D8:3A:DD:0B:69:B9 --cap DisplayYesNo        # override capability
pair D8:3A:DD:0B:69:B9 --interactive              # prompt for PIN/passkey
pair D8:3A:DD:0B:69:B9 --check                    # check pairing state only
pair D8:3A:DD:0B:69:B9 --reset                    # remove existing bond, then re-pair
pair D8:3A:DD:0B:69:B9 --reset --pin 12345        # force re-pair with PIN
```

After pairing the shell shows connection status and returns to the prompt.  Use `info` to inspect the device, `cservices` to list RFCOMM services, or `interfaces` / `props` for D-Bus exploration.

#### Test Mode (`--test`)

Replicates the original PoC behaviour: pair, then monitor for auto-disconnect without connecting.  Useful for diagnosing pairing parameters and timing.

```bash
pair D8:3A:DD:0B:69:B9 --pin 12345 --test        # pair + disconnect monitor
```

#### Brute-Force Discovery

```bash
pair D8:3A:DD:0B:69:B9 --brute                         # PIN 0000-9999
pair D8:3A:DD:0B:69:B9 --brute --range 00000-99999     # custom range
pair D8:3A:DD:0B:69:B9 --brute --passkey-brute          # passkey 000000-999999
pair D8:3A:DD:0B:69:B9 --brute --pin-list pins.txt     # dictionary attack
pair D8:3A:DD:0B:69:B9 --brute --delay 1.0              # rate limiting
pair D8:3A:DD:0B:69:B9 --brute --max-attempts 500       # cap attempts
pair D8:3A:DD:0B:69:B9 --brute --lockout-cooldown 90    # 90s lockout pause
pair D8:3A:DD:0B:69:B9 --brute --max-lockout-retries 5  # up to 5 cooldowns
```

Iterates through candidate PINs or passkeys, performing a full pair/remove/re-pair cycle for each attempt until the correct value is found.

**Lockout awareness**: Many devices implement pairing lockout after consecutive wrong PINs, returning `AuthenticationRejected` instead of `AuthenticationFailed`.  The brute forcer detects this transition (wrong PIN errors followed by outright rejection) and pauses for `--lockout-cooldown` seconds before retrying the rejected candidate.  This prevents skipping the correct PIN during a lockout window.

#### Options Reference

| Option | Default | Description |
|--------|---------|-------------|
| `--pin` | `0000` | PIN code for hardcoded mode (BR/EDR string, 1-16 chars) |
| `--passkey` | — | Passkey for hardcoded mode (LE uint32, 0-999999) |
| `--interactive` | — | Prompt for PIN/passkey at pair time |
| `--check` | — | Check pairing state only — do not pair |
| `--reset` | — | Force-remove existing bond before pairing |
| `--no-connect` | — | Pair only — skip the post-pair connection flow |
| `--no-trust` | — | Do not set the device as trusted after pairing |
| `--test` | — | PoC test mode: pair + auto-disconnect monitor |
| `--brute` | — | Enable brute-force mode |
| `--passkey-brute` | — | Brute-force passkeys instead of PINs |
| `--range` | `0000-9999` | PIN range for brute-force (e.g. `00000-99999`) |
| `--pin-list` | — | File with candidate PINs, one per line |
| `--delay` | `0.5` | Seconds between brute-force attempts |
| `--max-attempts` | `0` | Max brute-force attempts (0 = unlimited) |
| `--lockout-cooldown` | `60` | Seconds to pause when device lockout is detected |
| `--max-lockout-retries` | `3` | Max lockout-retry cycles per candidate before aborting |
| `--cap` | `KeyboardDisplay` | Agent capability |
| `--timeout` | `60` | Per-attempt pairing timeout in seconds |

#### How it works

1. **Device discovery**: Queries BlueZ's `GetManagedObjects()` for a `Device1` matching the target MAC.  Runs a 15-second auto-discovery scan if not found.
2. **Pre-pair check**: Queries the device's `Paired`, `Trusted`, and `Connected` D-Bus properties.  If already paired and `--reset` was not given, reports the current state and skips directly to connection.  Use `--check` to inspect pairing state without pairing.  Use `--reset` to force-remove the existing bond via `RemoveDevice()` and re-discover before proceeding.
3. **Agent registration**: Registers a `PairingAgent` with the selected capability and I/O handler.
4. **Pairing dispatch**: Stops the background GLib event loop and runs a temporary `GLib.MainLoop` on the main thread for `dbus.service.Object` handler dispatch.  Restarts the background loop after pairing.
5. **Error classification**: After each failed attempt, reads `agent.last_pair_error` to classify: `AuthenticationFailed` = wrong PIN (advance), `AuthenticationRejected` = lockout (pause + retry same candidate), blocking errors = abort after 5 consecutive.
6. **Lockout cooldown**: When lockout is detected, pauses for `--lockout-cooldown` seconds (interruptible via Ctrl+C), then retries the same candidate up to `--max-lockout-retries` times.
7. **Post-pair connect** (default): Detects transport type (BR/EDR or LE), attempts connection, SDP enumeration for classic devices, opens RFCOMM keepalive socket, sets session device state, and returns to the shell.
8. **Post-pair test** (`--test` flag): Sets the device as trusted and monitors for auto-disconnect timing (PoC diagnostic mode).

### Connecting with the `connect` Command

The `connect` command is **BLE-only** by design for directed LE testing.
It always calls `connect_and_enumerate__bluetooth__low_energy` to perform
GATT service enumeration, regardless of the target device's transport type.

```bash
connect D8:3A:DD:0B:69:B9    # BLE GATT connect + enumerate
```

For Bluetooth Classic targets use `cconnect`, which performs SDP discovery
and opens an RFCOMM keepalive socket — bypassing the `Device1.Connect()`
profile requirement that causes `br-connection-profile-unavailable` for
most Classic devices.

#### PinCode vs Passkey

| Aspect | PinCode | Passkey |
|--------|---------|---------|
| Transport | BR/EDR classic | LE (Secure Simple Pairing) |
| D-Bus return type | string | uint32 |
| Value range | 1-16 chars | 0-999999 |
| Typical length | 4-6 digits | Always 6 digits |
| Agent1 method | `RequestPinCode` | `RequestPasskey` |
| Required capability | `KeyboardOnly` or `KeyboardDisplay` | Same |

### Tips

- Use `detailed` to toggle verbose output (hex dumps, decoded appearances, etc.)
- All printouts also go to the log files set up in `/tmp/bti__logging__*.txt` for later analysis.

### Known Issues and Fixes

- **Fixed (v3.0.0)**: The `services` command previously failed with "argument of type 'Service' is not iterable" error. This was fixed by updating the `_get_handle_from_dict()` function to properly handle Service objects in addition to dictionaries.
- **Fixed (v3.0.0)**: Error in property monitor callback when disconnecting from a device while monitoring is active. This was fixed by adding a check for `_current_device` existence before trying to access its attributes.

---

## D-Bus Introspection and Raw Access

Debug mode provides comprehensive access to raw D-Bus operations for inspecting BlueZ objects and debugging interactions.

### D-Bus Navigation Commands

#### `ls [path]` - List D-Bus Objects

Lists all D-Bus objects at the specified path (or current path if omitted).

```bash
BLEEP-DEBUG> ls /org/bluez
BLEEP-DEBUG> ls .                    # List current path
```

#### `cd [path]` - Change Current D-Bus Path

Changes the current working D-Bus path for relative path operations.

```bash
BLEEP-DEBUG> cd /org/bluez/hci0
BLEEP-DEBUG> cd ..                   # Go up one level
BLEEP-DEBUG> cd .                    # Stay at current path
```

#### `pwd` - Show Current Path

Displays the current D-Bus path.

```bash
BLEEP-DEBUG> pwd
/org/bluez/hci0/dev_CC_50_E3_B6_BC_A6
```

### D-Bus Introspection

#### `introspect [path]` - Inspect D-Bus Object

Pretty-prints XML introspection data for any D-Bus object, showing all available interfaces, methods, properties, and signals.

```bash
BLEEP-DEBUG> introspect /org/bluez/hci0
BLEEP-DEBUG> introspect .            # Introspect current path
```

**Example Output:**
```xml
<node>
  <interface name="org.bluez.Adapter1">
    <method name="StartDiscovery"/>
    <method name="StopDiscovery"/>
    <property name="Powered" type="b" access="readwrite"/>
    ...
  </interface>
</node>
```

**Code Reference:**
```585:610:bleep/modes/debug_dbus.py
def cmd_introspect(args: List[str], state: DebugState) -> None:
    """Introspect a D-Bus object."""
    if args:
        path = resolve_path(args[0], state)
    elif state.current_path:
        path = state.current_path
    elif state.current_device:
        path = state.current_device._device_path
    else:
        print("[-] No device connected and no current path")
        return

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()
        dom = minidom.parseString(xml)
        pretty_xml = dom.toprettyxml(indent="  ")
        pretty_xml = re.sub(r'\n\s*\n', '\n', pretty_xml)

        print(f"\nIntrospection of {path}:\n")
        print(pretty_xml)
        print()
    except Exception as exc:
        print_and_log(f"[-] Introspection failed: {exc}", LOG__DEBUG)
```

### Direct D-Bus Method Calls

#### `call <interface> <method> [args...]` - Call D-Bus Method

Manually invoke any D-Bus method on the current object path (or device path if no current path is set).

```bash
BLEEP-DEBUG> call org.bluez.Adapter1 StartDiscovery
BLEEP-DEBUG> call org.freedesktop.DBus.Properties Get org.bluez.Device1 Connected
```

**Code Reference:**
```464:490:bleep/modes/debug_dbus.py
def cmd_call(args: List[str], state: DebugState) -> None:
    """Call a method on an interface."""
    if len(args) < 2:
        print("Usage: call <interface> <method> [args...]")
        return

    interface = args[0]
    method = args[1]
    method_args = args[2:] if len(args) > 2 else []

    path = _get_path_for_cmd(state)
    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        iface = dbus.Interface(obj, interface)
        method_obj = getattr(iface, method)

        result = method_obj(*method_args) if method_args else method_obj()
        print("[+] Method call successful")
        print(f"Result: {result}")
    except Exception as exc:
        print_and_log(f"[-] Method call failed: {exc}", LOG__DEBUG)
        print_detailed_dbus_error(exc)
```

### Raw D-Bus Access Capabilities

Debug mode provides direct access to D-Bus objects via `dbus.SystemBus()`, allowing you to:

- Introspect any D-Bus path using `org.freedesktop.DBus.Introspectable.Introspect()`
- Call any D-Bus method directly on any interface
- Read/write properties via `org.freedesktop.DBus.Properties` interface
- Navigate the entire BlueZ D-Bus object tree

---

## Property Monitoring

Debug mode includes comprehensive real-time monitoring of D-Bus property changes.

### `monitor` Command

Starts or stops real-time property change monitoring: `monitor [start|stop]`.
A bare `monitor` defaults to **start** (it is not a toggle). When active, all
`PropertiesChanged` signals for the connected device are displayed with
timestamps and formatted values.

```bash
BLEEP-DEBUG> monitor              # start monitoring (bare = start)
BLEEP-DEBUG> monitor start        # start monitoring
BLEEP-DEBUG> monitor stop         # stop monitoring
```

### `--monitor` Flag

Start debug mode with monitoring enabled from the beginning:

```bash
python -m bleep.modes.debug --monitor CC:50:E3:B6:BC:A6
```

### Property Monitoring Features

- Monitors `PropertiesChanged` signals from BlueZ
- Background thread for continuous monitoring
- Logs all property changes with timestamps
- Formats values based on type (bytes shown as hex, arrays/dictionaries summarized)
- Started/stopped during the session via `monitor start` / `monitor stop`

**Example Output:**
```
[MONITOR] Properties changed:
  Interface: org.bluez.Device1
  Path: /org/bluez/hci0/dev_CC_50_E3_B6_BC_A6
  Connected: True
  RSSI: -67
  ServicesResolved: True
```

The `monitor` command (`cmd_monitor`, debug_dbus.py ~550) spawns the background
worker `_monitor_properties`:

**Code Reference:**
```493:547:bleep/modes/debug_dbus.py
def _monitor_properties(device_path: str, stop_event: threading.Event, state: DebugState) -> None:
    """Monitor properties of a device in real-time."""
    try:
        bus = dbus.SystemBus()
        bus.get_object("org.bluez", device_path)

        from dbus.mainloop.glib import DBusGMainLoop
        DBusGMainLoop(set_as_default=True)
        from gi.repository import GLib as glib

        mainloop = glib.MainLoop()

        def properties_changed_cb(interface, changed, invalidated, path=None):
            if stop_event.is_set():
                mainloop.quit()
                return

            print("\n[MONITOR] Properties changed:")
            print(f"  Interface: {interface}")
            print(f"  Path: {path}")

            for prop, value in changed.items():
                print(f"  {prop}: {value}")

            if invalidated:
                print("  Invalidated properties:")
                for prop in invalidated:
                    print(f"    {prop}")

            if state.current_device is not None:
                print(DEVICE_PROMPT.format(state.current_device.mac_address), end="", flush=True)
            else:
                print(PROMPT, end="", flush=True)

        bus.add_signal_receiver(
            properties_changed_cb,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path=device_path,
            path_keyword="path",
        )

        def check_stop():
            if stop_event.is_set():
                mainloop.quit()
                return False
            return True

        glib.timeout_add(500, check_stop)
        print_and_log("[+] Property monitoring started", LOG__GENERAL)
        mainloop.run()
    except Exception as exc:
        print_and_log(f"[-] Monitoring error: {exc}", LOG__DEBUG)
    finally:
        print_and_log("[*] Property monitoring stopped", LOG__GENERAL)
```

---

## Signal Viewing

### `signals` Command

Introspect a **named D-Bus interface** and list the signals it declares
(`signals <interface>`, `cmd_signals` in debug_dbus.py ~411). This is a static
introspection of the interface definition — it does **not** display previously
captured/live signal traffic. Provide the interface name as the argument;
without one it prints `Usage: signals <interface>`.

```bash
BLEEP-DEBUG> signals org.bluez.Device1
BLEEP-DEBUG> signals org.freedesktop.DBus.Properties
```

Example output lists each signal and its argument signature, e.g.
`PropertiesChanged(interface: s, changed_properties: a{sv}, invalidated_properties: as)`
for `org.freedesktop.DBus.Properties`. To watch live property changes on the
connected device, use the `monitor` command instead.

---

## D-Bus Error Handling

Debug mode includes detailed error reporting for D-Bus exceptions, providing comprehensive diagnostic information.

### Error Details Displayed

When a D-Bus error occurs, debug mode automatically displays:

- **Full D-Bus error name** (e.g., `org.freedesktop.DBus.Error.InvalidArgs`)
- **Error message and arguments**
- **Method/property name extraction** for `InvalidArgs` errors
- **BLEEP error mapping** showing how the error maps to BLEEP's error system

**Example Error Output:**
```
[!] D-Bus Error Details:
[-] D-Bus Error: org.freedesktop.DBus.Error.InvalidArgs
[-] Message: No such property 'InvalidProperty'
[-] Invalid property: InvalidProperty
[-] On interface: org.bluez.Device1
[-] Maps to BLEEP error: InvalidPropertyError
```

**Code Reference:**
```73:103:bleep/modes/debug_dbus.py
def print_detailed_dbus_error(exc: Exception) -> None:
    """Print detailed information about a D-Bus exception."""
    print("\n[!] D-Bus Error Details:")

    if isinstance(exc, dbus.exceptions.DBusException):
        error_name = exc.get_dbus_name()
        error_msg = exc.get_dbus_message() or str(exc)

        print(f"[-] D-Bus Error: {error_name}")
        print(f"[-] Message: {error_msg}")

        if error_name == "org.freedesktop.DBus.Error.InvalidArgs":
            prop_match = re.search(r"property '([^']+)'", error_msg)
            method_match = re.search(r"method '([^']+)'", error_msg)
            iface_match = re.search(r"interface '([^']+)'", error_msg)

            if prop_match:
                print(f"[-] Invalid property: {prop_match.group(1)}")
            if method_match:
                print(f"[-] Invalid method: {method_match.group(1)}")
            if iface_match:
                print(f"[-] On interface: {iface_match.group(1)}")

        try:
            bleep_error = map_dbus_error(exc)
            print(f"[-] Maps to BLEEP error: {type(bleep_error).__name__}")
        except Exception as e:
            print(f"[-] Could not map to BLEEP error: {e}")
    else:
        print(f"[-] Error: {exc}")
        print(f"[-] Type: {type(exc).__name__}")
```

---

## Debugging Workflow Examples

### Raw D-Bus Message Inspection

1. **Start debug mode with monitoring:**
   ```bash
   python -m bleep.modes.debug --monitor CC:50:E3:B6:BC:A6
   ```

2. **Navigate D-Bus tree:**
   ```bash
   BLEEP-DEBUG> ls /org/bluez
   BLEEP-DEBUG> cd /org/bluez/hci0
   BLEEP-DEBUG> pwd
   ```

3. **Introspect objects:**
   ```bash
   BLEEP-DEBUG> introspect /org/bluez/hci0/dev_CC_50_E3_B6_BC_A6
   ```

4. **Call D-Bus methods directly:**
   ```bash
   BLEEP-DEBUG> call org.freedesktop.DBus.Properties GetAll org.bluez.Device1
   ```

5. **Monitor property changes:**
   ```bash
   BLEEP-DEBUG> monitor
   ```

### Using External Tools

For complete D-Bus visibility, you can use external tools alongside debug mode:

```bash
# Monitor all BlueZ D-Bus traffic in another terminal
sudo dbus-monitor --system "destination='org.bluez'" "sender='org.bluez'"
```

This provides raw D-Bus message inspection while debug mode provides structured interaction.

---

## Logging

## Methodology & CLI parity

BLEEP exposes most capabilities on **two surfaces** that follow deliberately
different contracts. The `bleep/cli/capability_registry.py` registry is the
single source of truth mapping each capability to the command name(s) it
exposes per surface, and two guard tests keep code and docs honest:
`tests/test_cli_debug_parity.py` (every reachable command is registered and each
`parity` value is internally consistent) and `tests/test_docs_match_registry.py`
(every registered command is documented on its surface — this file and
`cli_usage.md`).

### The two contracts

| | CLI (`bleep <subcommand>`) | Debug shell verb |
|---|---|---|
| Invocation | One-shot, scriptable, non-interactive | Interactive REPL line (`shlex`-split) |
| Parsing | `argparse` subparser in `bleep/cli/parsers/*` | `fn(args: List[str], state: DebugState) -> None` |
| State | Stateless per process | Persistent `DebugState` (current device, GLib loop, survey thread, …) |
| Output | `OutputContext` (terminal / `--json` / `--quiet`) + exit code | `print_and_log` to the terminal |
| Lifecycle | Connect → act → exit | Reuses the already-connected/enumerated session |

### Anti-drift mechanism (shared implementation, thin adapters)

A capability is implemented **once** (its `shared_impl`) and wrapped by thin
per-surface adapters — never duplicated:

- **Shared option builders** (`_add_*_arguments`, the `shared_args` column) define
  a command's flags once and are consumed by both the CLI subparser and any
  standalone parser.
- **`parse_as_cli(cli_name, tokens)`** (`bleep/modes/debug_cli_adapters.py`) parses
  debug tokens through the *real* CLI subparser, so ported verbs (`cscan`, `cenum`,
  `netenum`, `cping`, `uuidtr`, `adaptercfg`, `db`, `explore`, `gattserver`,
  `advertise`, `advertise-monitor`, `audiointercept`, `devicesets`, `mesh`, `ctf`,
  the `agent` management verbs, the `aoi` subcommand pipeline, and the `audiocfg`
  write sub-surface) accept *exactly* their CLI twin's options and can never
  drift. `SystemExit` from argparse is caught so a bad line never tears down the
  shell. (`advertise-monitor` was migrated onto this seam in CDU-M9, retiring the
  last hand-built debug parser.)
- **`foreground_loop_handoff(state)`** (`bleep/modes/debug_state.py`) lets debug
  verbs delegate to cores that run their own foreground `GLib.MainLoop` +
  SIGINT/SIGTERM handlers (`advertise-monitor`, `signal`, `gattserver`,
  `advertise`) by stopping the background debug loop and restoring the shell's
  Ctrl-C handler afterwards.

### Why some commands are intentionally single-surface

Parity means *"the same capability is reachable where it makes sense"*, not
*"every command exists on both surfaces"*. The registry records each deliberate
single-surface command in its `parity` field + `rationale`:

- **Debug-only (`debug-only`)** — interactive or stateful operations that are
  meaningless as a one-shot CLI verb: raw RFCOMM socket I/O (`copen`/`csend`/
  `crecv`/`craw`/`ckeep`), per-characteristic GATT interaction
  (`read`/`write`/`notify`/`char`/…), D-Bus tree navigation/introspection
  (`ls`/`cd`/`interfaces`/`call`/…), the live `monitor` property watcher, the
  advertised-profile listing (`cprofiles`), and shell meta (`help`/`quit`/`exit`).
- **CLI-only (`cli-only`)** — batch, offline, or self-contained flows with no live
  session value: `refresh-refs` (reference-data regeneration), `analyse` (offline
  JSON post-processing), `amusica` (self-contained audio sub-CLI), `gatt-enum`
  (single-pass enum; the debug `enum*` family covers connected variants),
  `audio-profiles`, `signal-config`, and the `user`/`interactive`/`debug` entry
  points.

Everything else is `full` (both surfaces delegate to one core) or `partial`
(both surfaces present, with a documented option-depth difference the registry
`rationale` records).

## Module Structure (v3.0.0)

Debug mode is organised into focused submodules under `bleep/modes/`:

| Module | Responsibility |
|---|---|
| `debug.py` | Core shell: imports, help text, dispatch table, `debug_shell()`, `main()` |
| `debug_state.py` | `DebugState` dataclass (shared session state) + GLib MainLoop management |
| `debug_dbus.py` | D-Bus error formatting, path resolution, navigation (`ls`/`cd`/`pwd`/`back`), introspection (`interfaces`/`props`/`methods`/`signals`/`call`/`monitor`/`introspect`) |
| `debug_connect.py` | Transport detection, `connect`/`disconnect`/`info` |
| `debug_gatt.py` | `services`/`chars`/`char`/`read`/`write`/`notify`/`detailed`, notification callback, property display |
| `debug_classic.py` | `cscan`/`cconnect`/`cservices`/`ckeep`/`csdp`/`pbap` |
| `debug_classic_data.py` | Classic data-exchange re-export shim (splits into the focused `debug_classic_*` sub-modules) |
| `debug_classic_obex.py` | OBEX profiles: `copp`/`cmapinfo`/`cmap`/`cftp`/`csync`/`cbip` |
| `debug_media.py` | `mediaenum`/`mediactrl`/`mediaprops`/`audiorecon`/`audioplay`/`audiorec`/`audiocfg` |
| `debug_survey.py` | `survey`/`survey-status` (background census thread) |
| `debug_stateful_adapters.py` | `explore`/`signal`/`cenum`/`gattserver`/`advertise`/`audiointercept`/`devicesets`/`mesh`/`ctf` (thin CLI-core twins) |
| `debug_cli_adapters.py` | `parse_as_cli` anti-drift helper + stateless CLI twins (`uuidtr`/`adaptercfg`/`netenum`/`cping`/`db`) |
| `debug_advmon.py` | `advertise-monitor` (kernel-offloaded Advertisement Monitor, foreground-loop handoff) |
| `debug_classic_profiles.py` | `cprofiles`/`cprofile` (connect/disconnect profiles), `cspp --auth` |
| `debug_hid.py` | `chid` (HID classification) |
| `debug_pairing.py` | `agent`/`pair` (single, brute-force), post-pair connect flows |
| `debug_scan.py` | `scan`/`scann`/`scanp`/`scanb`/`dscan`/`enum`/`enumn`/`enump`/`enumb` |
| `debug_aoi.py` | `aoi`/`dbsave`/`dbexport` |
| `debug_multiread.py` | `multiread`/`multiread_all`/`brutewrite` |

All command handlers share a single `DebugState` instance that replaces the 16 module-level globals from the pre-v2.7.2 monolith. Each handler signature is `fn(args: List[str], state: DebugState) -> None`.

---

All debug mode operations are logged to `/tmp/bti__logging__debug.txt` for later analysis. This includes:

- All D-Bus introspection operations
- All method calls and their results
- All property changes when monitoring is enabled
- All error details and diagnostics

View logs in real-time:
```bash
tail -f /tmp/bti__logging__debug.txt
```
