# Method Invocation Investigation - What to Check

## Current Status

✅ **Methods ARE registered** (class table populated)  
✅ **BlueZ sends METHOD CALLs** (verified via eavesdropping)  
✅ **Destination matches** (routing correct)  
❌ **Methods never invoke** (no entry point logs)  
❌ **No IO handler logs** (methods not called)  

## Critical Requirement: Mainloop Must Be RUNNING

**dbus-python REQUIRES the mainloop to be RUNNING to process incoming D-Bus messages.**

### How dbus-python Processes Messages

1. D-Bus daemon receives METHOD CALL from BlueZ
2. D-Bus daemon routes message to BLEEP's process
3. **Mainloop must be running** to:
   - Read messages from D-Bus connection
   - Dispatch messages to registered objects
   - Invoke Python methods
   - Send METHOD RETURN responses

**Without mainloop running, messages sit in the queue unprocessed.**

## What to Check

### 1. Is Mainloop Running?

**Check**: Are you running with `--default` flag?

```bash
# This runs mainloop
bleep agent --mode=simple --cap=keyboard --default

# This does NOT run mainloop
bleep agent --mode=simple --cap=keyboard
```

**Evidence from code** (`bleep/modes/agent.py:353-375`):
```python
if args.default:
    loop.run()  # Mainloop runs
else:
    # Mainloop is NOT running!
    print_and_log("[*] Agent registered (non-default)...")
```

**If mainloop isn't running, methods CANNOT be invoked.**

### 2. Is Mainloop Actually Processing Messages?

Even if mainloop is running, check:
- Is the mainloop thread blocked?
- Are there errors preventing message processing?
- Is the D-Bus connection active?

**Add diagnostic logging**:
```python
# In agent.py, add after loop.run()
print_and_log("[DEBUG] Mainloop is running", LOG__AGENT)
```

### 3. Are Methods Actually Registered?

**Already verified**: Class table shows methods are registered.

But verify:
- Are methods in the class table for the correct class name?
- Is the interface name correct (`org.bluez.Agent1`)?
- Are method signatures correct?

**Check logs for**:
```
[!!!] Agent methods in class table: ['RequestPinCode', 'Release', ...]
```

### 4. Is D-Bus Connection Active?

Check if the connection is properly established:
```python
# In agent.__init__()
if hasattr(self, 'connection'):
    print_and_log(f"[DEBUG] Connection active: {self.connection is not None}", LOG__AGENT)
```

### 5. Are There Any Errors Being Swallowed?

dbus-python may silently fail to process messages. Check:
- Are there exceptions in the mainloop?
- Are there D-Bus errors being ignored?
- Is message processing failing silently?

**Add error handlers**:
```python
# Wrap mainloop.run() with error handling
try:
    loop.run()
except Exception as e:
    print_and_log(f"[!] Mainloop error: {e}", LOG__AGENT)
```

## Comparison with simple-agent

### simple-agent (WORKING)
```python
# Line 155: Create agent
agent = Agent(bus, path)

# Line 157: Create mainloop
mainloop = GObject.MainLoop()

# Line 161: Register agent
manager.RegisterAgent(path, capability)

# Line 181: ALWAYS run mainloop
mainloop.run()  # <-- CRITICAL: Always runs
```

### BLEEP (Current)
```python
# Line 261: Create mainloop
loop = GLib.MainLoop()

# Line 284: Create agent
agent = create_agent(...)

# Line 365: CONDITIONALLY run mainloop
if args.default:
    loop.run()  # Only runs if --default
else:
    # Mainloop NOT running - methods can't be invoked!
```

## Root Cause Hypothesis

**If mainloop is NOT running**:
- Methods are registered ✅
- BlueZ sends calls ✅
- But dbus-python can't process them ❌
- Methods never invoke ❌

**If mainloop IS running**:
- Methods are registered ✅
- BlueZ sends calls ✅
- Mainloop should process them ✅
- But methods still don't invoke ❌
- **Need to investigate**: Connection state, message processing, error handling

## Next Steps

1. **Verify mainloop is running**: Check if `--default` flag is used
2. **Add mainloop status logging**: Log when mainloop starts/stops
3. **Add message processing diagnostics**: Log when messages are received
4. **Check for errors**: Add error handlers around mainloop
5. **Test with --default**: Ensure mainloop runs for testing

## Diagnostic Commands

```bash
# Check if agent process is running
ps aux | grep "bleep agent"

# Check if mainloop is running (if process exists, mainloop should be running)
# But this doesn't guarantee message processing

# Check D-Bus connection
dbus-send --system --print-reply --dest=org.bluez /org/bluez org.freedesktop.DBus.Introspectable.Introspect

# Monitor D-Bus messages
dbus-monitor --system "interface='org.bluez.Agent1'"
```

## Expected Behavior

When mainloop is running and methods are registered:
1. BlueZ sends METHOD CALL
2. D-Bus daemon routes to BLEEP
3. Mainloop reads message from connection
4. dbus-python dispatches to registered object
5. Python method is invoked
6. Entry point log appears: `[!!!] RequestPinCode METHOD ENTRY POINT REACHED`
7. IO handler is called
8. METHOD RETURN is sent to BlueZ

If any step fails, methods won't be invoked.


