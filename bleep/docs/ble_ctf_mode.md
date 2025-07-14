# BLE CTF mode

`blectf` mode automates many of the repetitive steps required to solve typical Bluetooth Low Energy Capture-The-Flag challenges.

## Quick start

```bash
python -m bleep -m blectf  # interactive helper (coming soon)
```

Right now the module is best used **programmatically**:

```python
from bleep.modes.blectf import scan_and_connect, solve_all

device, _mapping = scan_and_connect()
results = solve_all(device)
print(results)
```

## API reference

| Function | Purpose |
|----------|---------|
| `scan_and_connect()` | Scan for the CTF device (env var `BLE_CTF_MAC` or default) and connect |
| `read_flag(device, flag_name)` | Read a specific flag (by name or handle) |
| `write_flag(device, value)` | Write raw data to the Flag-Write characteristic |
| `read_score(device)` | Fetch current score |
| `solve_challenge(device, flag_name)` | Attempt single challenge solve |
| `solve_all(device)` | Iterate over known challenges, returning a dict of outcomes |

Each high-level solver ultimately delegates to lower-level helpers in `bleep.ble_ops.ctf` so you can mix automated and manual techniques.

## Environment variables

- `BLE_CTF_MAC` – override default MAC address `CC:50:E3:B6:BC:A6`.

## Extending

New CTFs rarely match exactly – extend `CHALLENGE_PATTERNS` (regex + description) and add bespoke `solve_flag_xx()` helpers as necessary, then hook them up in `solve_all()`. 