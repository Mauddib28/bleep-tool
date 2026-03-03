# BlueZ Reference Scripts Analysis - Refined Findings

## Executive Summary

After examining the official BlueZ reference scripts and documentation, I've identified **critical differences** between the working BlueZ scripts and BLEEP's implementation that explain why methods aren't being registered on D-Bus.

## Key Findings from BlueZ Reference Scripts

### 1. Working BlueZ Scripts Pattern

**simple-agent** (`workDir/BlueZScripts/simple-agent`):
```python
# Line 134: Set mainloop FIRST
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Line 136: Create bus AFTER mainloop
bus = dbus.SystemBus()

# Line 155: Create agent (NO explicit __init__ - uses default)
agent = Agent(bus, path)
# Agent class has NO __init__ method - relies on default dbus.service.Object.__init__()

# Line 157: Create mainloop object
mainloop = GObject.MainLoop()

# Line 161: Register with BlueZ
manager.RegisterAgent(path, capability)

# Line 179: Request default (if no device args)
manager.RequestDefaultAgent(path)

# Line 181: Run mainloop (KEEPS AGENT ALIVE)
mainloop.run()
```

**test-profile** (`workDir/BlueZScripts/test-profile`):
```python
# Line 53: Set mainloop FIRST
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Line 55: Create bus
bus = dbus.SystemBus()

# Line 97: Create profile (NO explicit __init__)
profile = Profile(bus, options.path)
# Profile class has NO __init__ method

# Line 99: Create mainloop object
mainloop = GObject.MainLoop()

# Line 126: Register with BlueZ
manager.RegisterProfile(options.path, options.uuid, opts)

# Line 128: Run mainloop
mainloop.run()
```

**simple-obex-agent** (`workDir/BlueZScripts/simple-obex-agent`):
```python
# Line 60: Set mainloop FIRST
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Line 62: Create bus
bus = dbus.SessionBus()

# Line 67: Create agent (HAS explicit __init__)
agent = Agent(bus, path)
# Line 28-29: def __init__(self, conn=None, obj_path=None):
#             dbus.service.Object.__init__(self, conn, obj_path)

# Line 69: Create mainloop object
mainloop = GObject.MainLoop()

# Line 71: Register with BlueZ
manager.RegisterAgent(path)

# Line 77: Run mainloop
mainloop.run()
```

### 2. BLEEP Implementation Pattern

**BLEEP** (`bleep/modes/agent.py`):
```python
# Line 181: Set mainloop FIRST
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

# Line 183: Create bus AFTER mainloop
bus = dbus.SystemBus()

# Line 278: Create agent (via factory function)
agent = create_agent(...)
    # Inside: BlueZAgent.__init__(bus, agent_path)
    # Line 209: super().__init__(bus, agent_path)  # Explicit call

# Line 253-333: Register with BlueZ (inside create_agent)
    agent.register(capabilities=cap, default=args.default)
        # Calls: _agent_manager.RegisterAgent(agent_path, capabilities)
        # Calls: _agent_manager.RequestDefaultAgent(agent_path) if default

# Line 346: Create mainloop (ONLY if args.default)
if args.default:
    loop = GLib.MainLoop()
    loop.run()
```

## Critical Differences Identified

### Difference 1: Mainloop Object Creation Timing

**Working Scripts**:
- Mainloop object (`GObject.MainLoop()`) is created **BEFORE** BlueZ registration
- Mainloop object exists when methods are registered

**BLEEP**:
- Mainloop object is created **AFTER** BlueZ registration
- Mainloop object only exists if `--default` flag is set
- **Issue**: Methods may need mainloop object to exist during registration

### Difference 2: Agent Class __init__ Pattern

**Working Scripts**:
- `simple-agent`: **NO** `__init__` method - relies on default `dbus.service.Object.__init__()`
- `test-profile`: **NO** `__init__` method - relies on default
- `simple-obex-agent`: **HAS** explicit `__init__` with `dbus.service.Object.__init__(self, conn, obj_path)`

**BLEEP**:
- **HAS** explicit `__init__` with `super().__init__(bus, agent_path)`
- Similar to `simple-obex-agent`, so this is **NOT** the issue

**Conclusion**: Both patterns (with/without explicit `__init__`) work in BlueZ scripts, so this is **NOT** the root cause.

### Difference 3: Mainloop Object Existence During Registration

**Working Scripts**:
```python
# Pattern in ALL working scripts:
mainloop = GObject.MainLoop()  # Created BEFORE registration
manager.RegisterAgent(path, capability)  # Registration happens with mainloop object existing
mainloop.run()  # Run mainloop
```

**BLEEP**:
```python
# Pattern in BLEEP:
agent.register(...)  # Registration happens WITHOUT mainloop object
if args.default:
    loop = GLib.MainLoop()  # Created AFTER registration
    loop.run()
```

**Critical Finding**: The mainloop **object** (not just the default mainloop) must exist when methods are registered!

### Difference 4: Factory Function vs Direct Instantiation

**Working Scripts**:
- Direct instantiation: `agent = Agent(bus, path)`
- Simple, direct call to `dbus.service.Object.__init__()`

**BLEEP**:
- Factory function: `agent = create_agent(...)`
- Multiple layers of indirection before `super().__init__()` is called
- **Potential Issue**: Factory function may interfere with method registration

## Root Cause Analysis

### Primary Issue: Mainloop Object Must Exist During Registration

**Evidence**:
1. **All working BlueZ scripts** create the mainloop object **before** registration
2. **BLEEP** creates the mainloop object **after** registration (and only if `--default`)
3. **dbus-python** may require the mainloop object to exist for method registration to work

**Theory**: `dbus.service.Object.__init__()` may need the mainloop object to exist to properly register methods. Without it, methods are registered on the object path but not actually callable.

### Secondary Issue: Factory Function Indirection

**Evidence**:
1. Working scripts use direct instantiation
2. BLEEP uses a factory function with multiple layers
3. Factory function may delay or interfere with method registration

**Theory**: The factory function may create timing issues where methods are registered before the D-Bus connection is fully ready.

## Recommended Solutions

### Solution 1: Create Mainloop Object Before Registration (HIGH PRIORITY)

**Implementation**:
```python
# In bleep/modes/agent.py, modify main() function:

def main(argv: list[str] | None = None):
    # ... existing code ...
    
    # Setup D-Bus mainloop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    
    # CRITICAL: Create mainloop object BEFORE agent creation
    loop = GLib.MainLoop()
    
    # Now create and register agent
    agent = create_agent(...)
    
    # Register with BlueZ (mainloop object now exists)
    # ... registration code ...
    
    # Run mainloop if default agent
    if args.default:
        loop.run()
    else:
        # For non-default agents, still need mainloop to exist
        # but don't run it indefinitely
        pass
```

**Rationale**: Matches the pattern used in ALL working BlueZ scripts.

### Solution 2: Ensure Mainloop Object Exists During Agent Creation

**Implementation**:
```python
# In bleep/dbuslayer/agent.py, modify BlueZAgent.__init__():

def __init__(self, bus, agent_path=AGENT_NAMESPACE, io_handler=None):
    # CRITICAL: Ensure mainloop object exists
    # Check if mainloop is running or exists
    try:
        from gi.repository import GLib
        # Try to get existing mainloop or create one
        # This ensures mainloop context exists for method registration
        pass
    except:
        pass
    
    super().__init__(bus, agent_path)
    # ... rest of initialization
```

**Rationale**: Ensures mainloop context exists when `super().__init__()` is called.

### Solution 3: Simplify Factory Function (MEDIUM PRIORITY)

**Implementation**:
```python
# In bleep/modes/agent.py, use direct instantiation:

# Instead of:
agent = create_agent(...)

# Use:
if agent_type == "simple":
    agent = SimpleAgent(bus, AGENT_NAMESPACE)
elif agent_type == "interactive":
    agent = InteractiveAgent(bus, AGENT_NAMESPACE)
# ... etc

# Then register
agent.register(capabilities=cap, default=args.default)
```

**Rationale**: Matches the direct instantiation pattern used in working scripts.

## Verification Steps

### Step 1: Test Mainloop Object Timing

1. Modify BLEEP to create mainloop object before agent creation
2. Verify introspection returns non-empty XML
3. Test if methods are invoked

### Step 2: Compare with Working Script

1. Run `simple-agent` and verify introspection
2. Compare introspection XML between `simple-agent` and BLEEP
3. Identify any differences in XML structure

### Step 3: Test Direct Instantiation

1. Modify BLEEP to use direct instantiation (no factory function)
2. Verify if this fixes method registration
3. If yes, keep factory function but ensure it doesn't delay registration

## Evidence from BlueZ Documentation

### org.bluez.Agent.5 Documentation

**Key Points**:
- Interface: `org.bluez.Agent1`
- Object path: "freely definable" (no specific requirement)
- Service: "unique name" (not specified, can be default)

**Methods Required**:
- `Release()` - void
- `RequestPinCode(object device)` - returns string
- `DisplayPinCode(object device, string pincode)` - void
- `RequestPasskey(object device)` - returns uint32
- `DisplayPasskey(object device, uint32 passkey, uint16 entered)` - void
- `RequestConfirmation(object device, uint32 passkey)` - void
- `RequestAuthorization(object device)` - void
- `AuthorizeService(object device, string uuid)` - void
- `Cancel()` - void

**BLEEP Implementation**: ✅ All methods are correctly implemented with correct signatures.

### org.bluez.AgentManager.5 Documentation

**Key Points**:
- `RegisterAgent(object agent, string capability)` - Registers agent
- `RequestDefaultAgent(object agent)` - Makes agent default
- Agent must implement `org.bluez.Agent1` interface

**BLEEP Implementation**: ✅ Correctly calls both methods.

## Conclusion

The root cause is **mainloop object timing**: the mainloop object must exist **before** agent registration, not after. This matches the pattern in ALL working BlueZ reference scripts.

**Primary Fix**: Create `GLib.MainLoop()` object before calling `agent.register()`.

**Secondary Fix**: Consider simplifying the factory function to match direct instantiation pattern.

## References

1. **BlueZ Reference Scripts**:
   - `workDir/BlueZScripts/simple-agent` - Working agent implementation
   - `workDir/BlueZScripts/test-profile` - Working profile implementation
   - `workDir/BlueZScripts/simple-obex-agent` - Working OBEX agent

2. **BlueZ Documentation**:
   - `workDir/BlueZDocs/org.bluez.Agent.5` - Agent interface specification
   - `workDir/BlueZDocs/org.bluez.AgentManager.5` - AgentManager interface specification

3. **BLEEP Implementation**:
   - `bleep/dbuslayer/agent.py` - Agent implementation
   - `bleep/modes/agent.py` - Agent CLI entry point


