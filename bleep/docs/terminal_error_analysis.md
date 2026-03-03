# Terminal Error Analysis - What the Errors Mean

## Error 1: AccessDenied on Introspection

### The Error
```
org.freedesktop.DBus.Error.AccessDenied: Rejected send message, 1 matched rules; 
type="method_call", sender=":1.46328" 
interface="org.freedesktop.DBus.Introspectable" member="Introspect" 
destination=":1.46328"
```

### Why This Happens

**D-Bus Security Restriction**: A process **cannot introspect its own objects** using the proxy mechanism. This is a security feature to prevent processes from calling methods on themselves via the bus.

**What's Happening**:
1. Agent process (bus unique name `:1.46328`) creates object at `/test/agent`
2. Agent tries to introspect itself: `bus.get_object(":1.46328", "/test/agent")`
3. D-Bus security policy rejects: "You can't call methods on yourself"
4. Error: `AccessDenied`

**This is EXPECTED behavior** - not a bug. The introspection code I added cannot work due to D-Bus security.

### Solution

**Remove the introspection attempt** - it will always fail due to security. Instead:
1. Use internal dbus-python state to check method registration
2. Test introspection from a **different process** (external)
3. Rely on actual method invocation logs to verify registration

## Error 2: Methods Not Being Invoked (The Real Problem)

### The Evidence

From agent logs:
```
[2026-01-02 13:57:43] METHOD CALL: RequestPinCode 
  sender=:1.629 (BlueZ), destination=:1.46268 (BLEEP)
[+] DESTINATION VERIFIED: BlueZ is calling BLEEP agent
```

**But**:
- ❌ **NO** `[!!!] RequestPinCode METHOD ENTRY POINT REACHED` log
- ❌ **NO** IO handler logs
- ❌ **NO** METHOD RETURN sent
- ✅ BlueZ times out after ~7 seconds and sends Cancel

### What This Proves

1. **Object path exists**: BlueZ can send METHOD CALLs to `/test/agent`
2. **Routing works**: Destination matches BLEEP's bus unique name
3. **Methods NOT invoked**: Python methods never execute
4. **No response**: BlueZ times out waiting for METHOD RETURN

### The Core Issue

**Methods are registered on the object path, but D-Bus cannot route METHOD CALLs to the Python methods.**

This suggests:
- `dbus.service.Object.__init__()` registers the object path ✅
- But methods decorated with `@dbus.service.method` are **NOT** being registered as callable ❌
- OR methods are registered but D-Bus can't route to them ❌

## Why Methods Aren't Being Invoked

### Theory 1: Methods Not Discovered by dbus-python

**Hypothesis**: `dbus.service.Object.__init__()` doesn't discover methods decorated with `@dbus.service.method`.

**Evidence**:
- Methods are properly decorated
- `super().__init__(bus, agent_path)` is called
- But methods never execute

**Possible Causes**:
- Timing: Methods need to exist before `__init__` is called (they do)
- Class definition: Methods need to be on the class, not instance (they are)
- Decorator issue: `@dbus.service.method` not working (unlikely - same as reference scripts)

### Theory 2: Methods Registered But Not Callable

**Hypothesis**: Methods are registered in dbus-python's internal tables, but D-Bus daemon can't route calls to them.

**Evidence**:
- Object path exists (BlueZ can send to it)
- Destination matches (routing is correct)
- But Python methods never receive calls

**Possible Causes**:
- Service name required: Objects may need a service name (bus name) to be callable
- Mainloop not running: Methods may need mainloop to be running to receive calls
- Connection state: D-Bus connection may not be in correct state

### Theory 3: dbus-python Version Issue

**Hypothesis**: Some versions of dbus-python have bugs where methods aren't properly registered.

**Evidence**:
- Reference scripts work (may be different dbus-python version)
- BLEEP doesn't work (current version)

**Need to Check**: dbus-python version

## Key Difference: simple-agent vs BLEEP

### simple-agent (WORKING)
```python
class Agent(dbus.service.Object):
    # NO __init__ method - uses default dbus.service.Object.__init__()
    
    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        print("RequestPinCode (%s)" % (device))
        return ask("Enter PIN Code: ")

# Usage:
agent = Agent(bus, path)  # Calls default __init__ directly
```

### BLEEP (NOT WORKING)
```python
class BlueZAgent(dbus.service.Object):
    def __init__(self, bus, agent_path=AGENT_NAMESPACE, io_handler=None):
        super().__init__(bus, agent_path)  # Explicit call to parent
        # ... additional initialization
    
    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        print_and_log("[!!!] RequestPinCode METHOD ENTRY POINT REACHED", LOG__AGENT)
        # ... method implementation
```

**Difference**: BLEEP has explicit `__init__`, simple-agent doesn't.

**BUT**: `simple-obex-agent` HAS explicit `__init__` and works, so this isn't the issue.

## What We Need to Do

1. **Remove introspection code** - It can't work due to security
2. **Check internal method table** - Use `_dbus_class_table` to verify methods are registered
3. **Test from external process** - Properly introspect from different process
4. **Compare dbus-python versions** - Check if version mismatch is the issue
5. **Test minimal agent** - Create simplest possible agent to isolate issue

## The Real Question

**Why can BlueZ send METHOD CALLs to the object path, but Python methods never execute?**

This is the core mystery that needs solving. The AccessDenied error is a red herring - it's expected D-Bus security behavior. The real issue is method invocation failure.


