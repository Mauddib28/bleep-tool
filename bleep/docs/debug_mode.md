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
| `help` | Show full built-in command list |

Exit with `Ctrl-D` or `quit`.

### Tips

- Use `detailed` to toggle verbose output (hex dumps, decoded appearances, etc.)
- All printouts also go to the log files set up in `/tmp/bleep-logs/` for later analysis.

### Known Issues and Fixes

- **Fixed in Unreleased Version**: The `services` command previously failed with "argument of type 'Service' is not iterable" error. This was fixed by updating the `_get_handle_from_dict()` function to properly handle Service objects in addition to dictionaries.
- **Fixed in Unreleased Version**: Error in property monitor callback when disconnecting from a device while monitoring is active. This was fixed by adding a check for `_current_device` existence before trying to access its attributes.