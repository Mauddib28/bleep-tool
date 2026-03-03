# GLib MainLoop Architecture: Current State and Future Design

**Date:** 2026-03-01
**Status:** Design document — not yet implemented
**Scope:** Debug mode and agent callback dispatch across all BLEEP modes

## Problem Statement

`dbus-python` only dispatches `dbus.service.Object` method handlers (e.g.
`RequestPinCode`, `RequestPasskey`) when `GLib.MainLoop().run()` executes on
the **main thread**.  A background-thread MainLoop causes these handlers to
silently never fire, even though the D-Bus message arrives on the socket.

This constraint creates a tension in the debug shell: the shell needs
`input()` blocking on the main thread for interactive prompts, while the
agent needs `GLib.MainLoop().run()` on the main thread for D-Bus dispatch.

## Current Architecture (v2.6)

```
Main thread:       input() loop ──── blocks waiting for user ────
Background thread: GLib.MainLoop().run() ── dispatches D-Bus signals ──

pair command:  stop background loop → pair_device() runs temp MainLoop
               on main thread (dispatches RequestPinCode) → restart
               background loop
```

**Trade-offs:**
- Works reliably for single-shot pairing operations
- Requires stop/restart cycle around every pairing attempt
- Agent cannot receive callbacks while shell is idle (background loop
  does not dispatch `dbus.service.Object` handlers)
- Brute-force mode must stop/restart per attempt (handled by `PinBruteForcer`)

## Compatibility Assessment

All BLEEP modes were analyzed for MainLoop usage:

| Mode | Uses MainLoop | Main thread? | Uses input()? | Compatible with inversion? |
|------|--------------|-------------|--------------|---------------------------|
| debug | Yes (background thread) | No | Yes | **Needs changes** |
| agent | Yes | Yes | No | Already compatible |
| interactive | Via manager.run() | Yes | Yes | Compatible |
| scan | Via manager.run() | Yes | No | Compatible |
| aoi | Via manager.run() | Yes | No | Compatible |
| amusica | No | N/A | No | Compatible |
| blectf | No | N/A | Yes | Compatible |
| exploration | Via manager.run() | Yes | No | Compatible |
| analysis | No | N/A | No | Compatible |
| signal | Yes | Yes | No | Already compatible |
| user | No | N/A | Yes | Compatible |
| picow | No | N/A | Yes | Compatible |

**Conclusion:** Only debug mode requires changes.  All other modes either
already run MainLoop on the main thread or do not maintain a persistent
MainLoop.

## Proposed Future Architecture

Two implementation options were evaluated.  **Option A is recommended.**

### Option A: Worker Thread for input() (Recommended)

```
Main thread:   GLib.MainLoop().run() ── dispatches D-Bus + queued commands ──
Worker thread: input() loop ── queues commands via GLib.idle_add() ──
```

**Implementation sketch:**

```python
def debug_shell():
    loop = GLib.MainLoop()
    cmd_done = threading.Event()

    def _input_worker():
        while True:
            line = input(prompt)
            parts = shlex.split(line)
            if not parts:
                continue
            cmd, *rest = parts
            if cmd in {"quit", "exit"}:
                GLib.idle_add(loop.quit)
                break
            cmd_done.clear()
            GLib.idle_add(_run_cmd, cmd, rest)
            cmd_done.wait()

    def _run_cmd(cmd, rest):
        handler = _CMDS.get(cmd)
        if handler:
            handler(rest)
        cmd_done.set()
        return False

    threading.Thread(target=_input_worker, daemon=True).start()
    loop.run()
```

**Pros:**
- `input()` loop structure barely changes; easy to reason about
- `GLib.idle_add()` is thread-safe and well-documented
- All command handlers run on the main thread (same context as today)
- `_cmd_pair` no longer needs stop/restart — MainLoop is on main thread
- Agent always ready for callbacks, even while shell is idle

**Cons:**
- Python `readline` module has edge cases on non-main threads (signal
  handling for Ctrl+C may not propagate cleanly)
- Worker thread must synchronize with main thread via Event/Queue
- If a command handler calls `input()` (e.g. interactive PIN prompt),
  it blocks the MainLoop temporarily — acceptable, same as BlueZ
  `simple-agent` pattern

**Estimated effort:** ~60-80 lines changed in `debug.py`

### Option B: GLib.io_add_watch on stdin

```
Main thread: GLib.MainLoop().run()
             ├── D-Bus handler dispatch
             └── GLib.io_add_watch(stdin) → on_stdin_ready callback
```

**Pros:**
- No threading; everything on the main thread
- Cleanest architecture; MainLoop drives both D-Bus and stdin

**Cons:**
- **Loses readline editing features** (history, arrow keys, tab
  completion) because `sys.stdin.readline()` bypasses `readline`
- **Structural refactor:** synchronous `while True: input()` loop
  becomes callback-driven
- **Nested `input()` conflicts:** interactive PIN prompt would
  conflict with the stdin watch registration, requiring careful
  watch enable/disable management
- **Prompt interleaving:** D-Bus output between prompt display and
  user input causes cosmetic issues

**Estimated effort:** ~100-120 lines changed, structural refactor

### Why Option A Over Option B

The nested `input()` problem in Option B is the deciding factor.  When
the `--interactive` pair mode calls `input("Enter PIN code: ")` inside
the `_on_stdin_ready` callback, the stdin watch is still registered.
The next line of input would be consumed by either `input()` or the
watch — not both.  This requires disabling the watch around every
interactive prompt, adding fragile state management.

Option A avoids this entirely because `input()` always runs on the
worker thread, and interactive PIN prompts run on the main thread
inside `GLib.idle_add()`.  The worker is blocked on `cmd_done.wait()`
during this time, so there is no conflict.

## When to Adopt

Consider implementing Option A when:
- The agent needs to handle **unsolicited** pairing requests (passive
  agent mode) while the debug shell is idle
- Brute-force needs to run as a **background task** without blocking
  the debug shell
- Persistent property monitoring needs to coexist with agent callbacks

The current stop/restart pattern is adequate for the v2.6 use cases
(single-shot and brute-force pairing initiated by the user).

## References

- `bleep/dbuslayer/agent.py` lines 1072-1076: MainLoop requirement
  confirmed via PoC
- `bleep/modes/debug.py` lines 746-750: background loop limitation
  documented
- BlueZ `test/simple-agent`: reference implementation using
  `GObject.MainLoop().run()` on main thread with `input()` in
  D-Bus handler
