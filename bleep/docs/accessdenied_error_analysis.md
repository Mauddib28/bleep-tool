# AccessDenied Error Analysis - D-Bus Security Restriction

## The Error

From the agent logs, we see:

```
[!] Could not introspect agent after creation: org.freedesktop.DBus.Error.AccessDenied: 
Rejected send message, 1 matched rules; type="method_call", sender=":1.46328" 
interface="org.freedesktop.DBus.Introspectable" member="Introspect" 
destination=":1.46328"
```

## Why This Error Occurs

**D-Bus Security Restriction**: A process **cannot introspect its own objects** using the proxy mechanism (`bus.get_object()` + `Interface.Introspect()`). This is a D-Bus security policy that prevents processes from calling methods on themselves via the bus.

**What's Happening**:
1. Agent process creates object at `/test/agent` (bus unique name `:1.46328`)
2. Agent tries to introspect itself: `bus.get_object(":1.46328", "/test/agent")`
3. D-Bus security policy rejects this: "You can't call methods on yourself via the bus"
4. Error: `AccessDenied`

**This is NOT a bug** - it's expected D-Bus behavior.

## The Real Issue (Still Unresolved)

Despite the introspection error being a red herring, the **actual problem remains**:

From the logs:
```
[2026-01-02 13:57:43] METHOD CALL: RequestPinCode (interface=org.bluez.Agent1, path=/test/agent, sender=:1.629, destination=:1.46268)
[+] DESTINATION VERIFIED: BlueZ is calling BLEEP agent (destination=:1.46268 matches BLEEP_bus=:1.46268)
```

**Evidence**:
- ✅ BlueZ sends METHOD CALL (verified)
- ✅ Destination matches BLEEP's bus (verified)
- ❌ **NO agent method entry point logs** (`[!!!] RequestPinCode METHOD ENTRY POINT REACHED`)
- ❌ **NO IO handler logs**
- ❌ **NO METHOD RETURN sent** (BlueZ times out after ~7 seconds)

**Conclusion**: Methods are **NOT being invoked** even though BlueZ sends calls to them.

## Why Methods Aren't Being Invoked

Since introspection can't verify registration (due to security restriction), we need other evidence:

### Evidence 1: No Entry Point Logs
The agent code has this at the start of `RequestPinCode`:
```python
print_and_log(
    "[!!!] RequestPinCode METHOD ENTRY POINT REACHED - Agent method invoked by BlueZ",
    LOG__AGENT
)
```

**This log NEVER appears**, proving the method is never called.

### Evidence 2: BlueZ Times Out
BlueZ sends `RequestPinCode`, waits ~7 seconds, then sends `Cancel`. This means:
- BlueZ successfully sent the METHOD CALL
- No METHOD RETURN was received
- BlueZ timed out and cancelled

### Evidence 3: Destination Verification Works
The monitoring system correctly identifies that BlueZ is calling BLEEP's agent (destination matches), so routing is correct.

## Possible Root Causes

### Theory 1: Methods Not Registered
- `dbus.service.Object.__init__()` may not be registering methods
- Methods decorated with `@dbus.service.method` may not be discovered
- **But**: Object path exists (BlueZ can send to it)

### Theory 2: Methods Registered But Not Callable
- Methods may be registered but D-Bus can't route calls to them
- May need service name (bus name) for proper routing
- **But**: Reference scripts don't use service names

### Theory 3: Timing Issue
- Methods may be registered after BlueZ sends calls
- Mainloop may need to be running for methods to be callable
- **But**: Mainloop fix didn't help (or wasn't the issue)

### Theory 4: dbus-python Bug
- Known issues with method registration in some dbus-python versions
- Methods may not be properly exported even though object path is
- **Need to check**: dbus-python version

## Correct Way to Verify Method Registration

Since self-introspection is blocked, we need alternative methods:

### Method 1: Use dbus-python's Internal API

```python
# In BlueZAgent.__init__(), after super().__init__()
# Access the internal method table directly
if hasattr(self, '_dbus_method_table'):
    print_and_log(f"[DEBUG] Registered methods: {list(self._dbus_method_table.keys())}", LOG__AGENT)
else:
    print_and_log("[DEBUG] No _dbus_method_table found", LOG__AGENT)
```

### Method 2: Test from External Process

```python
# Run this from a DIFFERENT process (not the agent process)
import dbus
bus = dbus.SystemBus()

# Get BLEEP's bus unique name from agent logs
bleep_bus_name = ":1.46268"  # From logs: [!!!] Agent created: bus_unique_name=:1.46268

obj = bus.get_object(bleep_bus_name, '/test/agent')
intro = dbus.Interface(obj, 'org.freedesktop.DBus.Introspectable')
xml = intro.Introspect()
print(xml)
```

### Method 3: Check dbus-python Internal State

```python
# In BlueZAgent.__init__()
import dbus.service
# Check if object is actually registered
if hasattr(dbus.service, 'Object'):
    # Try to access registration info
    pass
```

## Next Steps

1. **Remove introspection code** - It can't work due to security restriction
2. **Add internal method table inspection** - Check if methods are in dbus-python's internal tables
3. **Test from external process** - Properly introspect from different process
4. **Check dbus-python version** - Some versions have known registration bugs
5. **Compare with working simple-agent** - See what's different in actual registration

## The Core Mystery

**Why can BlueZ send METHOD CALLs to the object path, but Python methods never get invoked?**

This suggests:
- Object path IS registered (BlueZ can send to it)
- Methods are NOT callable (Python never receives the calls)
- D-Bus routing may be broken, or methods aren't actually registered


