# Mainloop Requirement Analysis - Critical Discovery

## The Key Difference: Mainloop Must Be RUNNING

### simple-agent (WORKING)
```python
# Line 155: Create agent
agent = Agent(bus, path)

# Line 157: Create mainloop
mainloop = GObject.MainLoop()

# Line 161: Register agent
manager.RegisterAgent(path, capability)

# Line 181: RUN the mainloop (ALWAYS)
mainloop.run()  # <-- THIS IS CRITICAL
```

### BLEEP (FIXED in v2.6.2 — NOW WORKING)
```python
# pair_device() creates temporary MainLoop when no background loop is running:
tmp_loop = GLib.MainLoop()
GLib.timeout_add(100, _poll_result)
tmp_loop.run()  # <-- RUNS ON MAIN THREAD, dispatches agent handlers
```

**Previous broken pattern** (before v2.6.1):
```python
# Background thread loop — did NOT dispatch dbus.service.Object handlers:
if args.default:
    loop.run()  # <-- Ran on background thread or not at all
```

## The Critical Issue

**dbus-python REQUIRES the mainloop to be RUNNING to process D-Bus messages.**

When BlueZ sends a METHOD CALL:
1. D-Bus daemon receives it ✅
2. D-Bus daemon routes it to BLEEP's process ✅
3. **BUT**: dbus-python can only process it if the mainloop is running ❌
4. If mainloop isn't running, the message sits in the queue unprocessed ❌
5. Python methods never get invoked ❌

## Evidence

From the logs:
- ✅ Methods ARE registered (class table populated)
- ✅ BlueZ sends METHOD CALLs (verified via eavesdropping)
- ✅ Destination matches (routing correct)
- ❌ Methods never invoke (mainloop not processing messages)
- ❌ No METHOD RETURN sent (mainloop not running to send response)

## The Solution

**The mainloop MUST be running for methods to be invoked.**

Options:
1. **Always run mainloop** (even for non-default agents)
2. **Run mainloop in a thread** (for non-default agents)
3. **Document that --default is required** for method invocation

## Why This Wasn't Obvious

- Methods ARE registered (class table shows this)
- Object path IS registered (BlueZ can send to it)
- But without mainloop running, dbus-python can't process incoming messages
- This is a **runtime requirement**, not a registration issue

## Additional Discovery: Main-Thread Requirement (2026-02-28)

Running the GLib `MainLoop` on a **background thread** (as done in BLEEP's debug mode) does NOT work for `dbus.service.Object` method dispatch.  The GLib default `MainContext` must be iterated on the **main thread** for object-path handlers (`RequestPinCode`, `RequestPasskey`, etc.) to fire.

### Evidence

| Approach | `RequestPinCode` fires? | Notes |
|----------|------------------------|-------|
| `mainloop.run()` on main thread (`simple-agent`) | **Yes** | Baseline test: pairing succeeds with PIN "12345" |
| `mainloop.run()` on background daemon thread (debug `_cmd_pair` v1) | **No** | Message filters see the call; Python handler never invoked |
| `context.iteration(False)` on main thread (debug `_cmd_pair` v2) | **No** | Filters fire, but object-path handlers do NOT |
| Temporary `GLib.MainLoop` + `timeout_add` (PoC) | **Yes** | PoC confirmed: pairing succeeds with PIN "12345" |
| Temporary `GLib.MainLoop` + `timeout_add` in `pair_device()` | **Yes (CONFIRMED)** | v2.6.2: end-to-end pairing succeeds with PIN "12345" |

### Why `context.iteration(False)` Fails

`GLib.MainContext.default().iteration(False)` processes GLib event sources (IO watches, timeouts) and triggers `dbus_connection_add_filter()` callbacks.  However, it does **not** drive the full `dbus_connection_dispatch()` → `_dbus_object_tree_dispatch_and_unlock()` chain that routes messages to `dbus.service.Object` Python method handlers.

Only `GLib.MainLoop().run()` — which internally calls `g_main_loop_run()` → `g_main_context_iteration(context, TRUE)` in a loop with the context **acquired** — triggers the complete dispatch path including object-path handlers.

This was confirmed empirically: with `context.iteration(False)`, message filters logged `RequestPinCode` arrival but the Python `RequestPinCode` method on the agent never executed.  With a temporary `GLib.MainLoop().run()`, both filters and the Python handler fired.

### Fix

Two-part fix:

1. **`debug.py`**: `_cmd_pair()` stops the background GLib loop before pairing and restarts it after.
2. **`agent.py`**: `pair_device()`'s non-background path uses a temporary `GLib.MainLoop` with `GLib.timeout_add(100, poll)` instead of `context.iteration(False)`.  The poll callback checks for completion/timeout and quits the loop.

## Additional Discovery: Message Filter Interference (2026-02-28)

Even with the temporary `GLib.MainLoop` fix in place, `RequestPinCode` handlers still did not fire when `enable_unified_dbus_monitoring()` had been called.  This function installs a generic message filter via `bus.add_message_filter()`.

### Evidence

| Configuration | `RequestPinCode` fires? | Notes |
|--------------|------------------------|-------|
| Temporary `GLib.MainLoop` + no message filter | **Yes** | PoC and non-root diagnostic test both succeed |
| Temporary `GLib.MainLoop` + message filter active | **No** | Handler never invoked despite filter returning `None` |
| Temporary `GLib.MainLoop` + eavesdrop rules (non-root) | N/A | `AccessDenied` — rules never registered |

### Why Message Filters Interfere

`dbus-python`'s `bus.add_message_filter(callback)` registers a callback via `dbus_connection_add_filter()` in `libdbus`.  Despite the callback returning `None` (equivalent to `DBUS_HANDLER_RESULT_NOT_YET_HANDLED`), the presence of the filter interferes with the subsequent object-path dispatch pipeline.  Specifically, `dbus_connection_dispatch()` processes filters first; when a filter is present, the object-tree lookup → `dbus.service.Object._message_cb()` chain does not reliably trigger for incoming method calls.

This is a behavioral quirk of `dbus-python`'s integration with `libdbus`, not a documented limitation.  The workaround is to avoid installing message filters when `dbus.service.Object` handler dispatch is needed (e.g. during pairing).

### Fix

In `ensure_default_pairing_agent()` (`agent.py`), `enable_unified_dbus_monitoring(True)` is no longer called.  Only `signals_instance.register_agent(self)` is called for method invocation correlation.  Monitoring can be re-enabled after pairing completes if needed.
