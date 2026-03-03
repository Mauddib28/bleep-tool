# Real Issue Investigation - Methods Registered But Not Invoked

## Current Status (Confirmed)

✅ **Methods ARE registered** (class table shows 9 methods)  
✅ **Mainloop IS running** (agent is active, `loop.run()` is blocking)  
✅ **Object IS registered on bus** (locations show connection and path)  
✅ **BlueZ sends METHOD CALLs** (verified via eavesdropping)  
✅ **Destination matches** (routing correct)  
❌ **Methods never invoke** (no entry point logs)  

## The Real Question

**Why isn't dbus-python dispatching method calls even though everything appears correct?**

## Possible Root Causes

### 1. Object Path Mismatch

**Hypothesis**: The object path registered doesn't match what BlueZ is calling.

**Check**:
- What path is BlueZ calling? (from eavesdropping logs)
- What path is the object registered at? (from agent logs)
- Do they match exactly?

**Evidence needed**: Compare METHOD CALL path with registered object path.

### 2. Connection Not Receiving Messages

**Hypothesis**: The connection is registered but not actually receiving messages from D-Bus daemon.

**Possible causes**:
- Connection not properly activated
- Message filter not set up correctly
- D-Bus daemon not routing to this connection

**Check**: Can we verify messages are arriving at the connection?

### 3. Method Signature Mismatch

**Hypothesis**: BlueZ is calling with a signature that doesn't match registered methods.

**Check**:
- What signature is BlueZ using? (from eavesdropping)
- What signature are methods registered with? (from class table)
- Do they match?

### 4. Interface Name Mismatch

**Hypothesis**: BlueZ is calling with an interface name that doesn't match.

**Check**:
- What interface is BlueZ using? (from eavesdropping: `interface=org.bluez.Agent1`)
- What interface are methods registered under? (should be `org.bluez.Agent1`)
- Do they match?

### 5. dbus-python Dispatch Issue

**Hypothesis**: dbus-python has a bug or configuration issue preventing dispatch.

**Possible causes**:
- Mainloop integration issue
- Connection state issue
- Object registration timing issue

## What to Check Next

1. **Compare object paths**: Verify BlueZ's METHOD CALL path matches registered path exactly
2. **Check message arrival**: Verify messages are actually arriving at the connection
3. **Verify method signatures**: Compare BlueZ's call signature with registered signatures
4. **Test with minimal agent**: Create simplest possible agent and see if it works
5. **Compare with working simple-agent**: Run simple-agent and see what's different

## Key Diagnostic: Message Path Comparison

From eavesdropping logs, we see:
```
METHOD CALL: RequestPinCode (interface=org.bluez.Agent1, path=/test/agent, ...)
```

From agent logs, we see:
```
[!!!] Agent created: bus_unique_name=:1.46458, path=/test/agent
```

**Paths match** (`/test/agent`), so this isn't the issue.

## Next Diagnostic: Message Processing

We need to verify:
1. Are messages arriving at the connection?
2. Is dbus-python attempting to dispatch them?
3. Why isn't dispatch succeeding?

This requires adding low-level diagnostic logging to dbus-python's message processing, which may not be easily accessible.

## Alternative Approach: Test with Working simple-agent

Run the working `simple-agent` script and compare:
- How it registers the object
- How it sets up the connection
- How it runs the mainloop
- What's different from BLEEP

This will help identify what BLEEP is missing.


