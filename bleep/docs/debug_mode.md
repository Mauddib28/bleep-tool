# Debug mode

Debug mode drops you into an **interactive shell** with helpers for inspecting BlueZ D-Bus objects, reading characteristics, and monitoring property changes in real-time.

Launch:

```bash
python -m bleep -m debug --help           # show flags
python -m bleep -m debug --device AA:BB:CC:DD:EE:FF  # auto-connect to target
```

Key flags:

| Flag | Description |
|------|-------------|
| `--device <MAC>` | Auto-connect to device and populate helper variables |
| `--no-connect` | Start shell without connecting |
| `--monitor` | Spawn background monitor printing property change events |
| `--timeout` | Monitor duration (default 60 s) |

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