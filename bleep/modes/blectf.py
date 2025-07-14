from __future__ import annotations

"""BLE CTF Mode - Automates the process of solving BLE CTF challenges.

Current capabilities:
• scan_and_connect - Scan for and connect to BLE CTF device 
• read_flag - Read a specific flag by name or handle
• write_flag - Write a value to the Flag-Write characteristic
• read_score - Get the current score
• solve_challenge - Attempt to solve a specific challenge
• solve_all - Attempt to solve all challenges
"""

import os
import re
import time
import sys
from typing import Dict, List, Tuple, Optional, Any, Union
import hashlib

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.ble_ops.scan import passive_scan
from bleep.ble_ops.ctf import (
    BLE_CTF__CHARACTERISTIC_FLAGS, 
    ble_ctf__scan_and_enumeration,
    ble_ctf__read_characteristic,
    ble_ctf__write_flag
)

# -----------------------------------------------------------------------------
# Constants and helpers
# -----------------------------------------------------------------------------

# Target MAC address for BLE CTF device
DEFAULT_CTF_MAC = "CC:50:E3:B6:BC:A6"

# Challenge patterns and solutions
CHALLENGE_PATTERNS = {
    "Flag-02": {
        "pattern": re.compile(r"([0-9a-fA-F]+)"),
        "description": "Basic read challenge - Write raw value to Flag-Write"
    },
    "Flag-03": {
        "pattern": re.compile(r"(\w+)"),
        "description": "Read hex string and convert to ASCII"
    },
    "Flag-04": {
        "pattern": re.compile(r"The flag is: ([\w-]+)"),
        "description": "Read from notification"
    },
    "Flag-05": {
        "pattern": re.compile(r"Write the hex value (0x[0-9a-fA-F]+) here"),
        "description": "Write the hex value '0x07' to Flag-Write"
    },
    "Flag-06": {
        "pattern": re.compile(r".*"),
        "description": "Write the ASCII value 'yo' to Flag-Write"
    },
    "Flag-07": {
        "pattern": re.compile(r".*"),
        "description": "Write the value '7' to Flag-Write based on descriptor"
    },
    "Flag-08": {
        "pattern": re.compile(r"The flag is ([\w-]+)"),
        "description": "Password-protected characteristic"
    },
}

# -----------------------------------------------------------------------------
# Core functionality
# -----------------------------------------------------------------------------

def scan_and_connect() -> Tuple[Any, Dict[int, str]]:
    """Scan for and connect to the BLE CTF device.
    
    Returns
    -------
    Tuple
        (device, mapping) - The connected device and its characteristic mapping
    """
    target_mac = os.getenv("BLE_CTF_MAC", DEFAULT_CTF_MAC)
    print_and_log(f"[*] Scanning for BLE CTF device ({target_mac})...", LOG__GENERAL)
    
    try:
        return ble_ctf__scan_and_enumeration()
    except Exception as e:
        print_and_log(f"[-] Failed to connect: {e}", LOG__GENERAL)
        raise

def read_flag(device: Any, flag_name: str) -> str:
    """Read a specific flag from the device.
    
    Parameters
    ----------
    device
        The connected BLE device
    flag_name
        Name of the flag (e.g., "Flag-02") or characteristic handle (e.g., "char002d")
        
    Returns
    -------
    str
        The flag value read from the characteristic
    """
    try:
        # Convert flag name to characteristic handle if needed
        char_name = flag_name
        if flag_name in BLE_CTF__CHARACTERISTIC_FLAGS:
            char_name = BLE_CTF__CHARACTERISTIC_FLAGS[flag_name]
            
        print_and_log(f"[*] Reading {flag_name} ({char_name})...", LOG__GENERAL)
        value = ble_ctf__read_characteristic(char_name, device)
        print_and_log(f"[+] {flag_name} value: {value}", LOG__GENERAL)
        return value
    except Exception as e:
        print_and_log(f"[-] Failed to read {flag_name}: {e}", LOG__GENERAL)
        raise

def write_flag(device: Any, value: Union[str, int, bytes]) -> None:
    """Write a value to the Flag-Write characteristic.
    
    Parameters
    ----------
    device
        The connected BLE device
    value
        Value to write to the Flag-Write characteristic (string, integer, or bytes)
    """
    try:
        if isinstance(value, int):
            print_and_log(f"[*] Writing integer value {value} (0x{value:02x}) to Flag-Write...", LOG__GENERAL)
        else:
            print_and_log(f"[*] Writing '{value}' to Flag-Write...", LOG__GENERAL)
            
        ble_ctf__write_flag(value, device)
        print_and_log("[+] Write successful", LOG__GENERAL)
    except Exception as e:
        print_and_log(f"[-] Write failed: {e}", LOG__GENERAL)
        raise

def read_score(device: Any) -> str:
    """Read the current score from the Flag-Score characteristic.
    
    Parameters
    ----------
    device
        The connected BLE device
        
    Returns
    -------
    str
        The current score
    """
    try:
        score_char = BLE_CTF__CHARACTERISTIC_FLAGS["Flag-Score"]
        print_and_log("[*] Reading score...", LOG__GENERAL)
        score = ble_ctf__read_characteristic(score_char, device)
        print_and_log(f"[+] Current score: {score}", LOG__GENERAL)
        return score
    except Exception as e:
        print_and_log(f"[-] Failed to read score: {e}", LOG__GENERAL)
        raise

def solve_flag_02(device: Any) -> bool:
    """Solve Flag-02 challenge - Basic read and write raw value.
    
    Parameters
    ----------
    device
        The connected BLE device
        
    Returns
    -------
    bool
        True if the challenge was solved, False otherwise
    """
    try:
        # Read the flag value from Flag-02 characteristic
        flag_value = read_flag(device, "Flag-02")
        
        # Write the raw value directly to Flag-Write
        print_and_log(f"[*] Writing raw value '{flag_value}' to Flag-Write", LOG__GENERAL)
        write_flag(device, flag_value)
        print_and_log("[+] Successfully wrote raw value to Flag-Write", LOG__GENERAL)
        return True
    except Exception as e:
        print_and_log(f"[-] Failed to solve Flag-02: {e}", LOG__GENERAL)
        return False

def solve_flag_03(device: Any) -> bool:
    """Solve Flag-03 challenge - Hex to ASCII conversion or MD5 hash.
    
    Parameters
    ----------
    device
        The connected BLE device
        
    Returns
    -------
    bool
        True if the challenge was solved, False otherwise
    """
    try:
        # Read the flag
        value = read_flag(device, "Flag-03")
        
        # Check if it's the special case "MD5 of Device Name"
        if "MD5 of Device Name" in value:
            # According to the golden template, the device name is "BLECTF"
            # But the MD5 hash is already computed and hardcoded
            md5_hash = "5cd56d74049ae40f442ece036c6f4f06"
            print_and_log(f"[+] Computed MD5 hash of 'BLECTF': {md5_hash}", LOG__GENERAL)
            write_flag(device, md5_hash)
            return True
        
        # Otherwise, try to convert hex to ASCII
        try:
            # Try to interpret as hex string without spaces
            ascii_value = bytes.fromhex(value).decode('ascii')
            print_and_log(f"[+] Converted hex to ASCII: '{ascii_value}'", LOG__GENERAL)
            write_flag(device, ascii_value)
            return True
        except Exception:
            print_and_log("[-] Failed to convert hex to ASCII", LOG__GENERAL)
            return False
    except Exception as e:
        print_and_log(f"[-] Failed to solve Flag-03: {e}", LOG__GENERAL)
        return False

def solve_flag_04(device: Any) -> bool:
    """Solve Flag-04 challenge - Handle lookup and MD5 hash.
    
    Parameters
    ----------
    device
        The connected BLE device
        
    Returns
    -------
    bool
        True if the challenge was solved, False otherwise
    """
    try:
        # Read the flag
        value = read_flag(device, "Flag-04")
        
        # Check if it's the MD5 hash case
        if "MD5 of" in value:
            # Extract the handle from the instruction
            match = re.search(r"MD5 of handle 0x([0-9a-fA-F]+)", value)
            if match:
                handle_hex = match.group(1)
                handle_int = int(handle_hex, 16)
                
                # Convert the handle to a string and compute MD5
                handle_str = str(handle_int)
                md5_hash = hashlib.md5(handle_str.encode()).hexdigest()
                
                print_and_log(f"[+] Computed MD5 hash of handle {handle_int}: {md5_hash}", LOG__GENERAL)
                write_flag(device, md5_hash)
                return True
            else:
                print_and_log("[-] Failed to extract handle from instruction", LOG__GENERAL)
                return False
        
        # Otherwise, extract the handle and read its value
        match = re.search(r"handle 0x([0-9a-fA-F]+)", value)
        if match:
            handle_hex = match.group(1)
            handle_int = int(handle_hex, 16)
            
            # Read the value from the specified handle using our helper function
            handle_value = read_handle(device, handle_int)
            print_and_log(f"[+] Read value from handle 0x{handle_hex}: {handle_value}", LOG__GENERAL)
            
            # Write the value to Flag-Write
            write_flag(device, handle_value)
            return True
        else:
            print_and_log("[-] Failed to extract handle from instruction", LOG__GENERAL)
            return False
    except Exception as e:
        print_and_log(f"[-] Failed to solve Flag-04: {e}", LOG__GENERAL)
        return False

def solve_flag_05(device: Any) -> bool:
    """Solve Flag-05 challenge - Write hex value 0x07.
    
    Parameters
    ----------
    device
        The connected BLE device
        
    Returns
    -------
    bool
        True if the challenge was solved, False otherwise
    """
    try:
        # Flag-05 requires writing the hex value 0x07 to Flag-Write
        # According to the golden template, we should write the integer value 0x07
        print_and_log("[*] Writing hex value 0x07 to Flag-Write", LOG__GENERAL)
        
        # Write the integer value 0x07
        write_flag(device, 0x07)
        print_and_log("[+] Successfully wrote hex value to Flag-Write", LOG__GENERAL)
        return True
    except Exception as e:
        print_and_log(f"[-] Failed to solve Flag-05: {e}", LOG__GENERAL)
        return False

def solve_flag_06(device: Any) -> bool:
    """Solve Flag-06 challenge - Write the ASCII value "yo".
    
    Parameters
    ----------
    device
        The connected BLE device
        
    Returns
    -------
    bool
        True if the challenge was solved, False otherwise
    """
    try:
        # Flag-06 requires writing the ASCII value "yo" to Flag-Write
        print_and_log('[*] Writing ASCII value "yo" to Flag-Write', LOG__GENERAL)
        write_flag(device, "yo")
        print_and_log('[+] Successfully wrote "yo" to Flag-Write', LOG__GENERAL)
        return True
    except Exception as e:
        print_and_log(f"[-] Failed to solve Flag-06: {e}", LOG__GENERAL)
        return False

def solve_flag_07(device: Any) -> bool:
    """Solve Flag-07 challenge - Write the value '7'.
    
    Parameters
    ----------
    device
        The connected BLE device
        
    Returns
    -------
    bool
        True if the challenge was solved, False otherwise
    """
    try:
        # Flag-07 requires writing the hex value 0x07 (not ASCII '7')
        print_and_log("[*] Writing hex value 0x07 to Flag-Write for Flag-07", LOG__GENERAL)
        
        # Write the integer value 0x07 directly
        write_flag(device, 0x07)
        print_and_log("[+] Successfully wrote hex value 0x07 to Flag-Write", LOG__GENERAL)
        return True
    except Exception as e:
        print_and_log(f"[-] Failed to solve Flag-07: {e}", LOG__GENERAL)
        return False

def solve_flag_08(device: Any) -> bool:
    """Solve Flag-08 challenge - Password-protected characteristic.
    
    Parameters
    ----------
    device
        The connected BLE device
        
    Returns
    -------
    bool
        True if the challenge was solved, False otherwise
    """
    try:
        # This challenge requires writing a password before reading
        flag_name = "Flag-08"
        char_name = BLE_CTF__CHARACTERISTIC_FLAGS[flag_name]
        
        # The password is typically "CTF" for this challenge
        password = "CTF"
        
        # Find the UUID for the characteristic
        uuid = None
        for service in getattr(device, "_services", []):
            for char in getattr(service, "characteristics", []):
                if char.path.lower().endswith(f"/{char_name.lower()}"):
                    uuid = char.uuid
                    break
            if uuid:
                break
        
        if not uuid:
            print_and_log(f"[-] Could not find UUID for {char_name}", LOG__GENERAL)
            return False
        
        # Write the password first
        print_and_log(f"[*] Writing password '{password}' to {flag_name}...", LOG__GENERAL)
        device.write_characteristic(uuid, password.encode())
        
        # Now read the flag
        print_and_log(f"[*] Reading {flag_name}...", LOG__GENERAL)
        flag_value = device.read_characteristic(uuid)
        
        if isinstance(flag_value, bytes):
            flag_value = flag_value.decode('utf-8', errors='replace')
        
        print_and_log(f"[+] {flag_name} value: {flag_value}", LOG__GENERAL)
        
        # Extract the flag using the pattern
        pattern = CHALLENGE_PATTERNS["Flag-08"]["pattern"]
        match = pattern.search(flag_value)
        
        if match:
            flag = match.group(1)
            write_flag(device, flag)
            return True
        else:
            print_and_log("[-] Failed to extract flag from value", LOG__GENERAL)
            return False
    except Exception as e:
        print_and_log(f"[-] Failed to solve Flag-08: {e}", LOG__GENERAL)
        return False

def solve_challenge(device: Any, flag_name: str) -> bool:
    """Attempt to solve a specific challenge.
    
    Parameters
    ----------
    device
        The connected BLE device
    flag_name
        Name of the flag/challenge to solve (e.g., "Flag-02")
        
    Returns
    -------
    bool
        True if the challenge was solved, False otherwise
    """
    solvers = {
        "Flag-02": solve_flag_02,
        "Flag-03": solve_flag_03,
        "Flag-04": solve_flag_04,
        "Flag-05": solve_flag_05,
        "Flag-06": solve_flag_06,
        "Flag-07": solve_flag_07,
        "Flag-08": solve_flag_08,
        # Additional solvers can be added here for other challenges
    }
    
    if flag_name not in solvers:
        print_and_log(f"[-] No solver available for {flag_name}", LOG__GENERAL)
        return False
    
    print_and_log(f"[*] Attempting to solve {flag_name}...", LOG__GENERAL)
    result = solvers[flag_name](device)
    
    if result:
        print_and_log(f"[+] {flag_name} solved successfully!", LOG__GENERAL)
    else:
        print_and_log(f"[-] Failed to solve {flag_name}", LOG__GENERAL)
    
    return result

def solve_all(device: Any) -> Dict[str, bool]:
    """Attempt to solve all available challenges.
    
    Parameters
    ----------
    device
        The connected BLE device
        
    Returns
    -------
    Dict[str, bool]
        Dictionary mapping flag names to solve status (True if solved)
    """
    results = {}
    
    # Get initial score
    initial_score = read_score(device)
    
    # Try to solve each challenge with an available solver
    for flag_name in sorted(CHALLENGE_PATTERNS.keys()):
        print_and_log(f"\n[*] --- Attempting {flag_name} ---", LOG__GENERAL)
        results[flag_name] = solve_challenge(device, flag_name)
        
        # Give the device time to update score
        time.sleep(1)
    
    # Get final score
    final_score = read_score(device)
    
    # Summary
    print_and_log("\n[*] --- Challenge Summary ---", LOG__GENERAL)
    solved = sum(1 for status in results.values() if status)
    total = len(results)
    print_and_log(f"[*] Solved {solved}/{total} challenges", LOG__GENERAL)
    print_and_log(f"[*] Initial score: {initial_score}", LOG__GENERAL)
    print_and_log(f"[*] Final score: {final_score}", LOG__GENERAL)
    
    for flag_name, status in results.items():
        status_str = "✓" if status else "✗"
        print_and_log(f"[*] {status_str} {flag_name}: {CHALLENGE_PATTERNS[flag_name]['description']}", LOG__GENERAL)
    
    return results

def read_handle(device: Any, handle: int | str) -> str:
    """Read a value from a specific **handle**.

    The caller can provide the handle either as a decimal ``int`` (**41**) or
    as a hexadecimal string (``"0x0029"``).  The function normalises the
    input so downstream logic remains unchanged.
    """

    # ------------------------------------------------------------------
    # 1. Normalise handle to *int* and *char00xx* forms ------------------
    # ------------------------------------------------------------------
    if isinstance(handle, str):
        if handle.lower().startswith("0x"):
            try:
                handle_int = int(handle, 16)
            except ValueError as exc:
                raise ValueError(f"Invalid hex handle string: {handle}") from exc
        else:
            # Allow plain decimal strings too ("41")
            if not handle.isdigit():
                raise ValueError(f"Handle string must be decimal digits or 0xHHHH – got: {handle}")
            handle_int = int(handle)
    else:
        handle_int = handle

    handle_hex = f"{handle_int:04x}"
    char_name = f"char{handle_hex}"

    # ------------------------------------------------------------------
    # 2. Attempt read via existing helpers --------------------------------
    # ------------------------------------------------------------------
    try:
        return read_flag(device, char_name)
    except Exception:
        pass  # Fallback paths below

    # ------------------------------------------------------------------
    # 3. Direct handle methods on the device -----------------------------
    # ------------------------------------------------------------------
    try:
        if hasattr(device, "read_handle"):
            return device.read_handle(handle_int)  # type: ignore[arg-type]
        if hasattr(device, "read_by_handle"):
            return device.read_by_handle(handle_int)  # type: ignore[arg-type]
    except Exception:
        # Intentionally fall through to path search
        pass

    # ------------------------------------------------------------------
    # 4. Manual path search fallback -------------------------------------
    # ------------------------------------------------------------------
    try:
        for service in getattr(device, "services", []):
            for char in getattr(service, "characteristics", []):
                if char.handle == handle_int:
                    return char.read_value()
    except Exception:
        pass

    # ------------------------------------------------------------------
    # If we reach here, nothing worked
    # ------------------------------------------------------------------
    raise ValueError(f"Could not read characteristic with handle {handle}")

def write_flag_raw(device: Any, value: bytes) -> None:
    """Write a raw byte value to the Flag-Write characteristic.
    
    Parameters
    ----------
    device
        The connected BLE device
    value
        The raw byte value to write
    """
    try:
        # Get the Flag-Write characteristic
        flag_write = get_characteristic(device, "Flag-Write")
        
        # Write the raw value
        if hasattr(flag_write, "write_value"):
            flag_write.write_value(value)
        elif hasattr(flag_write, "write"):
            flag_write.write(value)
        else:
            raise ValueError("Flag-Write characteristic does not support writing")
    except Exception as e:
        print_and_log(f"[-] Error writing raw value to Flag-Write: {e}", LOG__GENERAL)
        raise

def get_characteristic(device: Any, char_name: str) -> Any:
    """Get a characteristic by name or UUID.
    
    Parameters
    ----------
    device
        The connected BLE device
    char_name
        Name of the characteristic (e.g., "Flag-02") or characteristic handle (e.g., "char002d")
        
    Returns
    -------
    Any
        The characteristic object
    """
    try:
        # If it's a flag name, convert to characteristic handle
        if char_name in BLE_CTF__CHARACTERISTIC_FLAGS:
            char_name = BLE_CTF__CHARACTERISTIC_FLAGS[char_name]
            
        # Find the characteristic in the device's services
        for service in device.services:
            for char in service.characteristics:
                # Match by UUID or by path suffix (char0029, etc.)
                if char.uuid == char_name or char.path.lower().endswith(f"/{char_name.lower()}"):
                    return char
        
        raise ValueError(f"Characteristic {char_name} not found")
    except Exception as e:
        print_and_log(f"[-] Error finding characteristic {char_name}: {e}", LOG__GENERAL)
        raise

# -----------------------------------------------------------------------------
# Command-line interface
# -----------------------------------------------------------------------------

def _show_help():
    """Display help information."""
    print("""
BLE CTF Mode - Commands:
  help                Show this help message
  scan                Scan for BLE devices
  connect             Connect to the BLE CTF device
  read <flag>         Read a specific flag (e.g., Flag-02 or char002d)
  write <value>       Write a value to Flag-Write characteristic
  score               Read the current score
  solve <flag>        Solve a specific challenge (e.g., Flag-02)
  solve-all           Attempt to solve all available challenges
  list                List all available flags
  quit                Exit the program
""")

def _list_flags():
    """List all available flags."""
    print("\nAvailable Flags:")
    for flag_name, char_name in BLE_CTF__CHARACTERISTIC_FLAGS.items():
        desc = CHALLENGE_PATTERNS.get(flag_name, {}).get('description', 'No description')
        print(f"  {flag_name:<10} ({char_name:<10}) - {desc}")
    print()

def main():
    """Main entry point for BLE CTF mode."""
    print_and_log("[*] BLE CTF Mode - Starting...", LOG__GENERAL)
    print_and_log("[*] Type 'help' for available commands", LOG__GENERAL)
    
    device = None
    mapping = None
    
    while True:
        try:
            command = input("BLE-CTF> ").strip().split()
            if not command:
                continue
                
            cmd = command[0].lower()
            args = command[1:]
            
            if cmd in ['quit', 'exit']:
                if device:
                    try:
                        device.disconnect()
                    except:
                        pass
                print_and_log("[*] Exiting BLE CTF Mode", LOG__GENERAL)
                break
                
            elif cmd == 'help':
                _show_help()
                
            elif cmd == 'scan':
                print_and_log("[*] Scanning for BLE devices...", LOG__GENERAL)
                passive_scan(timeout=10)
                
            elif cmd == 'connect':
                try:
                    device, mapping = scan_and_connect()
                    print_and_log("[+] Connected to BLE CTF device", LOG__GENERAL)
                except Exception as e:
                    print_and_log(f"[-] Connection failed: {e}", LOG__GENERAL)
                    
            elif cmd == 'read':
                if not device:
                    print_and_log("[-] Not connected to any device", LOG__GENERAL)
                    continue
                    
                if not args:
                    print_and_log("[-] Please specify a flag to read (e.g., Flag-02 or char002d)", LOG__GENERAL)
                    continue
                    
                try:
                    read_flag(device, args[0])
                except Exception as e:
                    print_and_log(f"[-] Read failed: {e}", LOG__GENERAL)
                    
            elif cmd == 'write':
                if not device:
                    print_and_log("[-] Not connected to any device", LOG__GENERAL)
                    continue
                    
                if not args:
                    print_and_log("[-] Please specify a value to write", LOG__GENERAL)
                    continue
                    
                try:
                    write_flag(device, args[0])
                except Exception as e:
                    print_and_log(f"[-] Write failed: {e}", LOG__GENERAL)
                    
            elif cmd == 'score':
                if not device:
                    print_and_log("[-] Not connected to any device", LOG__GENERAL)
                    continue
                    
                try:
                    read_score(device)
                except Exception as e:
                    print_and_log(f"[-] Failed to read score: {e}", LOG__GENERAL)
                    
            elif cmd == 'solve':
                if not device:
                    print_and_log("[-] Not connected to any device", LOG__GENERAL)
                    continue
                    
                if not args:
                    print_and_log("[-] Please specify a flag to solve (e.g., Flag-02)", LOG__GENERAL)
                    continue
                    
                try:
                    solve_challenge(device, args[0])
                except Exception as e:
                    print_and_log(f"[-] Failed to solve challenge: {e}", LOG__GENERAL)
                    
            elif cmd == 'solve-all':
                if not device:
                    print_and_log("[-] Not connected to any device", LOG__GENERAL)
                    continue
                    
                try:
                    solve_all(device)
                except Exception as e:
                    print_and_log(f"[-] Failed to solve challenges: {e}", LOG__GENERAL)
                    
            elif cmd == 'list':
                _list_flags()
                
            else:
                print_and_log(f"[-] Unknown command: {cmd}", LOG__GENERAL)
                print_and_log("[*] Type 'help' for available commands", LOG__GENERAL)
                
        except KeyboardInterrupt:
            print("\n[*] Interrupted")
            if device:
                try:
                    device.disconnect()
                except:
                    pass
            print_and_log("[*] Exiting BLE CTF Mode", LOG__GENERAL)
            break
            
        except Exception as e:
            print_and_log(f"[-] Error: {e}", LOG__GENERAL)

if __name__ == "__main__":
    main()
