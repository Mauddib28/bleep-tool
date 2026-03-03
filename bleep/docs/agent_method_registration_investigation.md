# Agent Method Registration Investigation - What We Know vs What We Assumed

## My Error: Making Assumptions Without Proof

I incorrectly assumed that creating the mainloop object before agent registration would fix the issue, based on:
- Pattern matching with BlueZ reference scripts
- Theory about mainloop timing

**I had NO PROOF this was the actual issue.**

## What We Actually Know (Evidence)

### Evidence 1: BlueZ Sends METHOD CALLs
- ✅ Unified monitoring captures `METHOD CALL: RequestPinCode`
- ✅ Destination verification shows BlueZ is calling BLEEP's agent (destination matches BLEEP's bus unique name)
- **Source**: `bleep/dbuslayer/signals.py` - unified D-Bus monitoring

### Evidence 2: Python Methods Never Invoke
- ❌ No agent method entry point logs (`[!!!] RequestPinCode METHOD ENTRY POINT REACHED`)
- ❌ No IO handler logs
- ❌ No METHOD RETURN sent to BlueZ
- **Source**: Agent logs show no method invocations

### Evidence 3: Introspection Test is Incorrect
- The test `bus.get_object('org.bluez', '/test/agent')` is **wrong**
- BLEEP's agent is NOT owned by `org.bluez` - it's owned by BLEEP's process
- Empty XML from wrong service name doesn't prove methods aren't registered
- **Source**: D-Bus object ownership model

## What We DON'T Know (Need to Investigate)

### Unknown 1: Are Methods Actually Registered?
- **Question**: If we introspect with the CORRECT bus unique name, do methods appear?
- **Test Needed**: Use BLEEP's bus unique name (from logs) to introspect
- **Current Status**: Haven't tested this correctly

### Unknown 2: Why Aren't Methods Invoked?
- **Question**: If methods ARE registered, why don't they get called?
- **Possible Causes**:
  - Methods registered but D-Bus can't route to them
  - Timing issue (methods registered after BlueZ sends calls)
  - Service name issue (even though reference scripts don't use it)
  - dbus-python bug

### Unknown 3: Does Mainloop Object Timing Matter?
- **Question**: Does creating mainloop before registration actually help?
- **Current Status**: Implemented but not verified
- **Proof Needed**: Compare introspection XML before/after fix

## Correct Diagnostic Steps

### Step 1: Add Introspection Logging to Agent

**Implemented**: Added introspection logging in `BlueZAgent.__init__()` that:
- Tests introspection immediately after object creation
- Uses the CORRECT bus unique name
- Logs the actual XML returned
- Checks if methods are present

**Location**: `bleep/dbuslayer/agent.py:220-250`

### Step 2: Run Agent and Check Logs

```bash
# Start agent
bleep agent --mode=simple --cap=keyboard --default

# Check agent logs for introspection XML
tail -f /tmp/bti__logging__agent.txt | grep -A 50 "introspection XML"
```

**What to Look For**:
- Does XML contain `<interface name="org.bluez.Agent1">`?
- Are method definitions present (`<method name="RequestPinCode">`)?
- Or is XML empty/just `<node></node>`?

### Step 3: Test with Correct Bus Unique Name

From agent logs, get the bus unique name:
```
[!!!] Agent created: bus_unique_name=:1.46295, path=/test/agent
```

Then test introspection:
```python
import dbus
bus = dbus.SystemBus()
obj = bus.get_object(":1.46295", "/test/agent")  # Use actual bus unique name
intro = dbus.Interface(obj, "org.freedesktop.DBus.Introspectable")
print(intro.Introspect())
```

### Step 4: Compare with Working simple-agent

Run the working BlueZ script and test its introspection:
```bash
# Run simple-agent
python3 workDir/BlueZScripts/simple-agent --capability=KeyboardDisplay

# In another terminal, get its bus unique name and introspect
# (Need to find its bus unique name first)
```

## Why My Fix May Not Work

1. **No Proof Mainloop Timing is the Issue**: I assumed this based on pattern matching, not evidence
2. **Introspection Test Was Wrong**: Can't verify fix with incorrect test
3. **May Be a Different Issue**: Could be service name, dbus-python version, or something else entirely

## What We Need to Do Next

1. **Run agent with introspection logging** - See actual XML generated
2. **Test introspection with correct bus unique name** - Verify if methods are registered
3. **Compare with working simple-agent** - See what's different
4. **Check dbus-python version** - Some versions have known issues
5. **Test minimal agent script** - Isolate the issue

## The Real Question

**Why do Python methods never invoke even though:**
- BlueZ sends METHOD CALLs (verified)
- Destination matches BLEEP's bus (verified)  
- Object path exists (BlueZ can send to it)

**This is the core mystery that needs solving.**


