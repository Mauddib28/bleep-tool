# Debug mode

Debug mode drops you into an **interactive shell** with helpers for inspecting BlueZ D-Bus objects, reading characteristics, and monitoring property changes in real-time.

## Launch Options

There are two ways to access the debug mode:

### Direct Module Access (Recommended)

This method directly accesses the debug mode implementation:

```bash
python -m bleep.modes.debug --help           # show flags
python -m bleep.modes.debug CC:50:E3:B6:BC:A6  # auto-connect to target
```

### CLI Module Access (Alternative)

This method goes through the main CLI interface:

```bash
python -m bleep.cli debug --help           # show flags
python -m bleep.cli debug CC:50:E3:B6:BC:A6  # auto-connect to target
```

> Note: The documentation previously showed `python -m bleep -m debug`, but this syntax is incorrect as the package doesn't have a `__main__.py` file.

Key flags:

| Flag | Description |
|------|-------------|
| `<MAC>` | Auto-connect to device at the specified MAC address |
| `--no-connect` | Start shell without connecting |
| `--monitor` or `-m` | Spawn background monitor printing property change events |
| `--detailed` or `-d` | Show detailed information including decoded UUIDs |

Once inside the prompt (`BLEEP-DEBUG>`):

| Command | Purpose |
|---------|---------|
| `scan` | Passive scan then list devices |
| `connect <MAC>` | Connect to device & build mapping |
| `services` | List primary services |
| `chars [<svc-uuid>]` | List characteristics (filtered by service) |
| `read <char>` | Read characteristic by handle/UUID |
| `write <char> <hex|ascii>` | Write bytes/ASCII to characteristic |
| `notify <char>` | Subscribe to notifications |
| `monitor` | Toggle property monitor |
| `ls / cd / pwd` | Navigate D-Bus object tree |
| `introspect [path]` | Pretty-print XML introspection data |
| `call <interface> <method> [args...]` | Call D-Bus method directly |
| `signals` | View captured signals |
| `pair <MAC> [options]` | Pair with device and connect for exploration |
| `connect <MAC>` | Connect to a device (auto-detects BLE vs Classic transport) |
| `agent` | Register / manage the BlueZ pairing agent |
| `help` | Show full built-in command list |

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
2. **Stale bond removal**: If already paired, removes the bond via `RemoveDevice()` and re-discovers before proceeding.
3. **Agent registration**: Registers a `PairingAgent` with the selected capability and I/O handler.
4. **Pairing dispatch**: Stops the background GLib event loop and runs a temporary `GLib.MainLoop` on the main thread for `dbus.service.Object` handler dispatch.  Restarts the background loop after pairing.
5. **Error classification**: After each failed attempt, reads `agent.last_pair_error` to classify: `AuthenticationFailed` = wrong PIN (advance), `AuthenticationRejected` = lockout (pause + retry same candidate), blocking errors = abort after 5 consecutive.
6. **Lockout cooldown**: When lockout is detected, pauses for `--lockout-cooldown` seconds (interruptible via Ctrl+C), then retries the same candidate up to `--max-lockout-retries` times.
7. **Post-pair connect** (default): Detects transport type (BR/EDR or LE), attempts connection, SDP enumeration for classic devices, opens RFCOMM keepalive socket, sets session device state, and returns to the shell.
8. **Post-pair test** (`--test` flag): Sets the device as trusted and monitors for auto-disconnect timing (PoC diagnostic mode).

### Connecting with the `connect` Command

The `connect` command auto-detects the device's transport type and routes to the appropriate connection method:

- **BLE**: `connect_and_enumerate__bluetooth__low_energy` — GATT service enumeration
- **BR/EDR Classic**: `connect_and_enumerate__bluetooth__classic` — profile connection + SDP enumeration, with fallback to SDP + RFCOMM keepalive if profile-level `Connect()` fails

```bash
connect D8:3A:DD:0B:69:B9    # auto-detect transport and connect
```

For explicit classic-only connection, `cconnect` remains available.  For BLE-only, use `connect` (BLE is the default when transport is ambiguous with LE indicators).

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

- **Fixed in Unreleased Version**: The `services` command previously failed with "argument of type 'Service' is not iterable" error. This was fixed by updating the `_get_handle_from_dict()` function to properly handle Service objects in addition to dictionaries.
- **Fixed in Unreleased Version**: Error in property monitor callback when disconnecting from a device while monitoring is active. This was fixed by adding a check for `_current_device` existence before trying to access its attributes.

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
```1495:1525:bleep/modes/debug.py
def _cmd_introspect(args: List[str]) -> None:
    """Introspect a D-Bus object."""
    global _current_path
    
    if len(args) > 0:
        path = args[0]
    else:
        path = _current_path or "/org/bluez"
    
    # Resolve relative paths
    path = _resolve_path(path, _current_path)
    
    try:
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        introspect_iface = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
        xml = introspect_iface.Introspect()
        
        print(f"\nIntrospection of {path}:\n")
        print(xml)
        print_and_log(f"[+] Introspected {path}", LOG__DEBUG)
    except Exception as exc:
        print_and_log(f"[-] Introspection failed: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)
```

### Direct D-Bus Method Calls

#### `call <interface> <method> [args...]` - Call D-Bus Method

Manually invoke any D-Bus method on the current object path (or device path if no current path is set).

```bash
BLEEP-DEBUG> call org.bluez.Adapter1 StartDiscovery
BLEEP-DEBUG> call org.freedesktop.DBus.Properties Get org.bluez.Device1 Connected
```

**Code Reference:**
```1351:1389:bleep/modes/debug.py
def _cmd_call(args: List[str]) -> None:
    """Call a method on an interface."""
    global _current_path

    if len(args) < 2:
        print("Usage: call <interface> <method> [args...]")
        return

    interface = args[0]
    method = args[1]
    method_args = args[2:] if len(args) > 2 else []

    # Use current path if available, otherwise use device path
    path = _current_path
    if not path and _current_device:
        path = _current_device._device_path

    if not path:
        print("[-] No device connected and no current path")
        return

    try:
        # Get the D-Bus object for the path
        bus = dbus.SystemBus()
        obj = bus.get_object("org.bluez", path)
        iface = dbus.Interface(obj, interface)
        method_obj = getattr(iface, method)

        if method_args:
            result = method_obj(*method_args)
        else:
            result = method_obj()

        print(f"[+] Method call successful")
        print(f"Result: {result}")
    except Exception as exc:
        print_and_log(f"[-] Method call failed: {exc}", LOG__DEBUG)
        _print_detailed_dbus_error(exc)
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

Toggles real-time property change monitoring. When enabled, all `PropertiesChanged` signals are displayed with timestamps and formatted values.

```bash
BLEEP-DEBUG> monitor              # Toggle monitoring on/off
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
- Can be toggled on/off during session

**Example Output:**
```
[2025-11-10 14:23:45] PropertiesChanged on /org/bluez/hci0/dev_CC_50_E3_B6_BC_A6
  Interface: org.bluez.Device1
  Connected: True
  RSSI: -67
  ServicesResolved: True
```

**Code Reference:**
```1391:1544:bleep/modes/debug.py
def _monitor_properties(device_path: str, stop_event: threading.Event) -> None:
    """Monitor property changes for a device."""
    global _current_device
    
    bus = dbus.SystemBus()
    
    # Set up signal receiver for PropertiesChanged
    def on_properties_changed(interface, changed, invalidated, path):
        if not path.startswith(device_path):
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{timestamp}] PropertiesChanged on {path}")
        print(f"  Interface: {interface}")
        
        for prop_name, value in changed.items():
            # Format value based on type
            if isinstance(value, dbus.Array):
                value_str = f"Array({len(value)} items)"
            elif isinstance(value, dbus.Dictionary):
                value_str = f"Dictionary({len(value)} keys)"
            elif isinstance(value, bytes):
                value_str = f"bytes({len(value)}): {value.hex()}"
            else:
                value_str = str(value)
            
            print(f"  {prop_name}: {value_str}")
            print_and_log(
                f"[PROPERTY] {path}::{prop_name} = {value_str}",
                LOG__DEBUG
            )
        
        if invalidated:
            print(f"  Invalidated: {', '.join(invalidated)}")
    
    # Add signal receiver
    bus.add_signal_receiver(
        on_properties_changed,
        signal_name="PropertiesChanged",
        dbus_interface="org.freedesktop.DBus.Properties",
        path_keyword="path"
    )
    
    # Run mainloop until stop event
    loop = gobject.MainLoop()
    
    def check_stop():
        if stop_event.is_set():
            loop.quit()
            return False
        return True
    
    gobject.timeout_add(100, check_stop)  # Check every 100ms
    
    try:
        loop.run()
    except Exception as e:
        print_and_log(f"[-] Monitor error: {e}", LOG__DEBUG)
    finally:
        # Remove signal receiver
        try:
            bus.remove_signal_receiver(
                on_properties_changed,
                signal_name="PropertiesChanged",
                dbus_interface="org.freedesktop.DBus.Properties"
            )
        except Exception:
            pass
```

---

## Signal Viewing

### `signals` Command

View captured D-Bus signals for the current device or session.

```bash
BLEEP-DEBUG> signals
```

This command displays signals that have been captured by the signal system, including:
- `PropertiesChanged` signals
- `InterfacesAdded` signals
- `InterfacesRemoved` signals
- Characteristic read/write/notification events

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
```89:129:bleep/modes/debug.py
def _print_detailed_dbus_error(exc: Exception) -> None:
    """Print detailed information about a D-Bus exception.

    This function extracts and displays:
    - The full D-Bus error name (e.g., org.freedesktop.DBus.Error.InvalidArgs)
    - The error message and arguments
    - For InvalidArgs errors, it tries to extract the specific method, interface or property name
    - Shows how the error maps to the BLEEP error system
    """
    print("\n[!] D-Bus Error Details:")

    if isinstance(exc, dbus.exceptions.DBusException):
        error_name = exc.get_dbus_name()
        error_msg = str(exc)

        print(f"[-] D-Bus Error: {error_name}")
        print(f"[-] Message: {error_msg}")

        # Extract method/property name for InvalidArgs errors
        if error_name == "org.freedesktop.DBus.Error.InvalidArgs":
            # Try to extract the property or method name from the error message
            prop_match = re.search(r"property '([^']+)'", error_msg)
            method_match = re.search(r"method '([^']+)'", error_msg)
            iface_match = re.search(r"interface '([^']+)'", error_msg)

            if prop_match:
                print(f"[-] Invalid property: {prop_match.group(1)}")
            if method_match:
                print(f"[-] Invalid method: {method_match.group(1)}")
            if iface_match:
                print(f"[-] On interface: {iface_match.group(1)}")

        # Map to BLEEP error system
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

## Module Structure (v2.7.2)

Debug mode is organised into focused submodules under `bleep/modes/`:

| Module | Responsibility |
|---|---|
| `debug.py` | Core shell: imports, help text, dispatch table, `debug_shell()`, `main()` |
| `debug_state.py` | `DebugState` dataclass (shared session state) + GLib MainLoop management |
| `debug_dbus.py` | D-Bus error formatting, path resolution, navigation (`ls`/`cd`/`pwd`/`back`), introspection (`interfaces`/`props`/`methods`/`signals`/`call`/`monitor`/`introspect`) |
| `debug_connect.py` | Transport detection, `connect`/`disconnect`/`info` |
| `debug_gatt.py` | `services`/`chars`/`char`/`read`/`write`/`notify`/`detailed`, notification callback, property display |
| `debug_classic.py` | `cscan`/`cconnect`/`cservices`/`ckeep`/`csdp`/`pbap` |
| `debug_pairing.py` | `agent`/`pair` (single, brute-force), post-pair connect flows |
| `debug_scan.py` | `scan`/`scann`/`scanp`/`scanb`/`enum`/`enumn`/`enump`/`enumb` |
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
