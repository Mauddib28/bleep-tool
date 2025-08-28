#!/usr/bin/env python3
"""BLE CTF Flag Discovery Patterns

This module provides automated discovery patterns for BLE CTF flags and challenges.
It includes pattern matching, decoding, and automated solving strategies for common
flag formats and challenge types.
"""

import re
import base64
import hashlib
import binascii
import time
from typing import Dict, List, Tuple, Optional, Any, Union, Pattern, Callable

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.ble_ops.ctf import (
    BLE_CTF__CHARACTERISTIC_FLAGS,
    ble_ctf__read_characteristic,
    ble_ctf__write_flag
)

# -----------------------------------------------------------------------------
# Flag Discovery Patterns
# -----------------------------------------------------------------------------

# Common flag formats
FLAG_PATTERNS = [
    # Standard CTF flag formats
    re.compile(r"flag\{([^}]+)\}", re.IGNORECASE),
    re.compile(r"ctf\{([^}]+)\}", re.IGNORECASE),
    re.compile(r"key\{([^}]+)\}", re.IGNORECASE),
    re.compile(r"flag:[ ]?([A-Za-z0-9_\-]+)", re.IGNORECASE),
    re.compile(r"the flag is:? ([A-Za-z0-9_\-]+)", re.IGNORECASE),
    re.compile(r"the flag is ([A-Za-z0-9_\-]+)", re.IGNORECASE),
    
    # Hex patterns
    re.compile(r"([0-9a-fA-F]{8,})"),
    
    # Base64 patterns (look for standard base64 strings)
    re.compile(r"([A-Za-z0-9+/]{4,}={0,2})"),
    
    # Instructions with embedded flags
    re.compile(r"write the hex value (0x[0-9a-fA-F]+)", re.IGNORECASE),
    re.compile(r"write the value ['\"](.*?)['\"]", re.IGNORECASE),
    re.compile(r"write ([0-9]+)", re.IGNORECASE),
    
    # MD5 hash instructions
    re.compile(r"md5 of ([^)]+)", re.IGNORECASE),
]

# -----------------------------------------------------------------------------
# Challenge Type Detection
# -----------------------------------------------------------------------------

class ChallengeType:
    """Types of BLE CTF challenges"""
    DIRECT_READ = "direct_read"
    HEX_TO_ASCII = "hex_to_ascii"
    ASCII_TO_HEX = "ascii_to_hex"
    NOTIFICATION = "notification"
    SPECIFIC_VALUE = "specific_value"
    HANDLE_LOOKUP = "handle_lookup"
    PASSWORD_PROTECTED = "password_protected"
    MD5_HASH = "md5_hash"
    UNKNOWN = "unknown"

def detect_challenge_type(value: str) -> Tuple[str, Optional[str]]:
    """
    Detect the type of challenge based on the characteristic value.
    
    Parameters
    ----------
    value : str
        The value read from the characteristic
        
    Returns
    -------
    Tuple[str, Optional[str]]
        A tuple containing (challenge_type, extracted_value)
    """
    # Check for MD5 hash instructions
    if "MD5 of" in value:
        if "Device Name" in value:
            return ChallengeType.MD5_HASH, "BLECTF"
        
        # Extract handle from MD5 instruction
        match = re.search(r"MD5 of handle 0x([0-9a-fA-F]+)", value)
        if match:
            handle_hex = match.group(1)
            handle_int = int(handle_hex, 16)
            return ChallengeType.MD5_HASH, str(handle_int)
            
        # Generic MD5 instruction
        match = re.search(r"MD5 of ([^)]+)", value)
        if match:
            return ChallengeType.MD5_HASH, match.group(1)
    
    # Check for handle lookup instructions
    if "handle" in value.lower():
        match = re.search(r"handle 0x([0-9a-fA-F]+)", value)
        if match:
            return ChallengeType.HANDLE_LOOKUP, match.group(1)
    
    # Check for specific value instructions
    if "write the hex value" in value.lower():
        match = re.search(r"write the hex value (0x[0-9a-fA-F]+)", value, re.IGNORECASE)
        if match:
            return ChallengeType.SPECIFIC_VALUE, match.group(1)
            
    if "write the value" in value.lower() or "write the ascii value" in value.lower():
        match = re.search(r"write the (?:ascii )?value ['\"](.*?)['\"]", value, re.IGNORECASE)
        if match:
            return ChallengeType.SPECIFIC_VALUE, match.group(1)
            
    # Special case for "Write anything here"
    if "write anything here" in value.lower():
        return ChallengeType.SPECIFIC_VALUE, "anything"
    
    # Check if value is likely hex encoded
    if re.match(r"^[0-9a-fA-F]+$", value) and len(value) % 2 == 0:
        try:
            ascii_value = bytes.fromhex(value).decode('ascii')
            if all(32 <= ord(c) < 127 for c in ascii_value):  # Printable ASCII
                return ChallengeType.HEX_TO_ASCII, ascii_value
        except (ValueError, UnicodeDecodeError):
            pass
    
    # Check for standard flag patterns
    for pattern in FLAG_PATTERNS:
        match = pattern.search(value)
        if match:
            return ChallengeType.DIRECT_READ, match.group(1)
    
    # If no specific pattern is detected
    return ChallengeType.UNKNOWN, None

# -----------------------------------------------------------------------------
# Flag Processing Functions
# -----------------------------------------------------------------------------

def process_flag(value: str) -> List[Dict[str, Any]]:
    """
    Process a flag value and return potential solutions.
    
    Parameters
    ----------
    value : str
        The value read from the characteristic
        
    Returns
    -------
    List[Dict[str, Any]]
        A list of potential solutions, each with:
        - type: The type of solution
        - value: The processed value
        - confidence: A confidence score (0-100)
        - description: A description of the solution
    """
    solutions = []
    
    # Detect challenge type
    challenge_type, extracted = detect_challenge_type(value)
    
    # Process based on challenge type
    if challenge_type == ChallengeType.DIRECT_READ and extracted:
        solutions.append({
            "type": "direct",
            "value": extracted,
            "confidence": 90,
            "description": "Direct flag extraction"
        })
    
    elif challenge_type == ChallengeType.HEX_TO_ASCII and extracted:
        solutions.append({
            "type": "hex_to_ascii",
            "value": extracted,
            "confidence": 85,
            "description": "Hex string converted to ASCII"
        })
    
    elif challenge_type == ChallengeType.MD5_HASH and extracted:
        md5_hash = hashlib.md5(extracted.encode()).hexdigest()
        solutions.append({
            "type": "md5_hash",
            "value": md5_hash,
            "confidence": 95,
            "description": f"MD5 hash of '{extracted}'"
        })
    
    elif challenge_type == ChallengeType.HANDLE_LOOKUP and extracted:
        solutions.append({
            "type": "handle_lookup",
            "value": extracted,
            "confidence": 80,
            "description": f"Handle lookup required: 0x{extracted}"
        })
    
    elif challenge_type == ChallengeType.SPECIFIC_VALUE and extracted:
        if extracted.startswith("0x"):
            try:
                # Convert hex string to integer
                int_value = int(extracted, 16)
                solutions.append({
                    "type": "specific_value",
                    "value": int_value,
                    "confidence": 90,
                    "description": f"Write specific hex value: {extracted}"
                })
            except ValueError:
                pass
        else:
            solutions.append({
                "type": "specific_value",
                "value": extracted,
                "confidence": 90,
                "description": f"Write specific value: '{extracted}'"
            })
    
    # Try additional processing methods for unknown types
    if challenge_type == ChallengeType.UNKNOWN or not solutions:
        # Try base64 decoding
        try:
            # Check if the value could be base64 encoded
            if re.match(r"^[A-Za-z0-9+/]+={0,2}$", value):
                decoded = base64.b64decode(value).decode('utf-8')
                if all(32 <= ord(c) < 127 for c in decoded):  # Printable ASCII
                    solutions.append({
                        "type": "base64",
                        "value": decoded,
                        "confidence": 70,
                        "description": "Base64 decoded value"
                    })
        except (binascii.Error, UnicodeDecodeError):
            pass
        
        # Try ASCII value directly
        if all(32 <= ord(c) < 127 for c in value):  # Printable ASCII
            solutions.append({
                "type": "ascii",
                "value": value,
                "confidence": 60,
                "description": "Raw ASCII value"
            })
        
        # Try hex value directly
        if re.match(r"^[0-9a-fA-F]+$", value):
            solutions.append({
                "type": "hex_raw",
                "value": value,
                "confidence": 50,
                "description": "Raw hex string"
            })
    
    return solutions

# -----------------------------------------------------------------------------
# Automated Flag Discovery
# -----------------------------------------------------------------------------

def discover_flags(device: Any) -> Dict[str, List[Dict[str, Any]]]:
    """
    Automatically discover and process flags from a BLE CTF device.
    
    Parameters
    ----------
    device : Any
        The connected BLE device
        
    Returns
    -------
    Dict[str, List[Dict[str, Any]]]
        A dictionary mapping flag names to lists of potential solutions
    """
    results = {}
    
    # Read each flag characteristic
    for flag_name, char_name in BLE_CTF__CHARACTERISTIC_FLAGS.items():
        # Skip special flags
        if flag_name in ["Flag-01", "Flag-Score", "Flag-Write"]:
            continue
            
        try:
            print_and_log(f"[*] Reading {flag_name} ({char_name})...", LOG__GENERAL)
            value = ble_ctf__read_characteristic(char_name, device)
            
            if isinstance(value, bytes):
                try:
                    value = value.decode('utf-8')
                except UnicodeDecodeError:
                    value = value.hex()
            
            print_and_log(f"[+] {flag_name} value: {value}", LOG__GENERAL)
            
            # Process the flag value
            solutions = process_flag(value)
            if solutions:
                results[flag_name] = solutions
                
                # Log the best solution
                best = max(solutions, key=lambda x: x["confidence"])
                print_and_log(f"[+] {flag_name} likely solution: {best['description']} -> {best['value']}", LOG__GENERAL)
            else:
                print_and_log(f"[-] No solution found for {flag_name}", LOG__GENERAL)
                results[flag_name] = [{
                    "type": "unknown",
                    "value": value,
                    "confidence": 0,
                    "description": "No solution found"
                }]
        except Exception as e:
            print_and_log(f"[-] Error reading {flag_name}: {e}", LOG__GENERAL)
            results[flag_name] = [{
                "type": "error",
                "value": str(e),
                "confidence": 0,
                "description": f"Error: {e}"
            }]
    
    return results

def auto_solve_flags(device: Any) -> Dict[str, bool]:
    """
    Automatically attempt to solve all flags on a BLE CTF device.
    
    Parameters
    ----------
    device : Any
        The connected BLE device
        
    Returns
    -------
    Dict[str, bool]
        A dictionary mapping flag names to solve status (True if solved)
    """
    results = {}
    
    # Parse score format to extract number
    def parse_score(score_text):
        match = re.search(r"Score:(\d+)\s*/\s*(\d+)", score_text)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 0, 0  # Default if parsing fails
    
    # Get initial score
    try:
        score_char = BLE_CTF__CHARACTERISTIC_FLAGS["Flag-Score"]
        initial_score_text = ble_ctf__read_characteristic(score_char, device)
        initial_score, total_flags = parse_score(initial_score_text)
        print_and_log(f"[*] Initial score: {initial_score_text} ({initial_score}/{total_flags})", LOG__GENERAL)
    except Exception as e:
        print_and_log(f"[-] Failed to read initial score: {e}", LOG__GENERAL)
        initial_score_text = "Unknown"
        initial_score, total_flags = 0, 0
    
    # Discover flags and potential solutions
    flag_solutions = discover_flags(device)
    
    # Try to solve each flag
    for flag_name, solutions in flag_solutions.items():
        print_and_log(f"\n[*] Attempting to solve {flag_name}...", LOG__GENERAL)
        
        if not solutions or solutions[0]["type"] == "error":
            print_and_log(f"[-] No valid solutions for {flag_name}", LOG__GENERAL)
            results[flag_name] = False
            continue
        
        # Get the highest confidence solution
        best_solution = max(solutions, key=lambda x: x["confidence"])
        
        try:
            # Handle special cases
            if best_solution["type"] == "handle_lookup":
                # Need to read from a specific handle first
                handle_hex = best_solution["value"]
                handle_int = int(handle_hex, 16)
                handle_char = f"char{handle_hex}"
                
                print_and_log(f"[*] Looking up handle 0x{handle_hex}...", LOG__GENERAL)
                try:
                    handle_value = ble_ctf__read_characteristic(handle_char, device)
                    print_and_log(f"[+] Handle value: {handle_value}", LOG__GENERAL)
                    
                    # Process the handle value
                    handle_solutions = process_flag(handle_value)
                    if handle_solutions:
                        best_handle_solution = max(handle_solutions, key=lambda x: x["confidence"])
                        value_to_write = best_handle_solution["value"]
                    else:
                        value_to_write = handle_value
                except Exception as e:
                    print_and_log(f"[-] Failed to read handle: {e}", LOG__GENERAL)
                    results[flag_name] = False
                    continue
            elif best_solution["type"] == "specific_value":
                # Use the exact value for specific value types
                value_to_write = best_solution["value"]
                if value_to_write == "anything":
                    # For "Write anything here", use a specific value
                    value_to_write = "BLEEP_SOLVED"
            else:
                value_to_write = best_solution["value"]
            
            # Read score before attempting solution
            try:
                before_score_text = ble_ctf__read_characteristic(score_char, device)
                before_score, _ = parse_score(before_score_text)
            except Exception:
                before_score = initial_score
            
            # Write the solution to Flag-Write
            print_and_log(f"[*] Writing solution: {value_to_write}", LOG__GENERAL)
            
            # Try to determine if this is a hex value that should be written as bytes
            if isinstance(value_to_write, str) and re.match(r'^[0-9a-fA-F]+$', value_to_write) and len(value_to_write) % 2 == 0:
                try:
                    # Try to write as raw bytes
                    byte_value = bytes.fromhex(value_to_write)
                    print_and_log(f"[*] Writing as raw bytes (hex): {len(byte_value)} bytes", LOG__GENERAL)
                    ble_ctf__write_flag(byte_value, device)
                except (ValueError, TypeError):
                    # Fall back to string if conversion fails
                    print_and_log(f"[*] Writing as string (conversion to bytes failed)", LOG__GENERAL)
                    ble_ctf__write_flag(value_to_write, device)
            else:
                # Write as normal value
                ble_ctf__write_flag(value_to_write, device)
                
            print_and_log(f"[+] Solution submitted for {flag_name}", LOG__GENERAL)
            
            # Wait a moment for the device to process
            time.sleep(0.5)
            
            # Check if score increased to verify solution
            try:
                after_score_text = ble_ctf__read_characteristic(score_char, device)
                after_score, _ = parse_score(after_score_text)
                
                if after_score > before_score:
                    print_and_log(f"[+] Solution VERIFIED for {flag_name} - Score increased!", LOG__GENERAL)
                    results[flag_name] = True
                else:
                    print_and_log(f"[-] Solution FAILED for {flag_name} - Score unchanged", LOG__GENERAL)
                    results[flag_name] = False
                    
                    # Try alternative solutions if available
                    if len(solutions) > 1:
                        print_and_log(f"[*] Trying alternative solution for {flag_name}...", LOG__GENERAL)
                        # Sort solutions by confidence, skip the first (already tried)
                        alt_solutions = sorted(solutions, key=lambda x: x["confidence"], reverse=True)[1:]
                        
                        for alt_solution in alt_solutions:
                            alt_value = alt_solution["value"]
                            print_and_log(f"[*] Trying alternative: {alt_value}", LOG__GENERAL)
                            
                            # Try to determine if this is a hex value that should be written as bytes
                            if isinstance(alt_value, str) and re.match(r'^[0-9a-fA-F]+$', alt_value) and len(alt_value) % 2 == 0:
                                try:
                                    # Try to write as raw bytes
                                    byte_value = bytes.fromhex(alt_value)
                                    print_and_log(f"[*] Writing as raw bytes (hex): {len(byte_value)} bytes", LOG__GENERAL)
                                    ble_ctf__write_flag(byte_value, device)
                                except (ValueError, TypeError):
                                    # Fall back to string if conversion fails
                                    print_and_log(f"[*] Writing as string (conversion to bytes failed)", LOG__GENERAL)
                                    ble_ctf__write_flag(alt_value, device)
                            else:
                                # Write as normal value
                                ble_ctf__write_flag(alt_value, device)
                            
                            # Wait a moment for the device to process
                            time.sleep(0.5)
                            
                            # Check if score increased
                            try:
                                new_score_text = ble_ctf__read_characteristic(score_char, device)
                                new_score, _ = parse_score(new_score_text)
                                
                                if new_score > after_score:
                                    print_and_log(f"[+] Alternative solution VERIFIED for {flag_name}!", LOG__GENERAL)
                                    results[flag_name] = True
                                    break
                            except Exception:
                                pass
            except Exception as e:
                print_and_log(f"[-] Failed to verify solution: {e}", LOG__GENERAL)
                results[flag_name] = False
            
        except Exception as e:
            print_and_log(f"[-] Failed to solve {flag_name}: {e}", LOG__GENERAL)
            results[flag_name] = False
    
    # Get final score
    try:
        final_score_text = ble_ctf__read_characteristic(score_char, device)
        final_score, _ = parse_score(final_score_text)
        print_and_log(f"[*] Final score: {final_score_text}", LOG__GENERAL)
    except Exception as e:
        print_and_log(f"[-] Failed to read final score: {e}", LOG__GENERAL)
        final_score_text = "Unknown"
        final_score = 0
    
    # Summary
    print_and_log("\n[*] --- Challenge Summary ---", LOG__GENERAL)
    solved = sum(1 for status in results.values() if status)
    total = len(results)
    print_and_log(f"[*] Attempted {total} challenges, solved {solved}", LOG__GENERAL)
    print_and_log(f"[*] Initial score: {initial_score_text}", LOG__GENERAL)
    print_and_log(f"[*] Final score: {final_score_text}", LOG__GENERAL)
    print_and_log(f"[*] Score improvement: {final_score - initial_score} points", LOG__GENERAL)
    
    for flag_name, status in results.items():
        status_str = "✓" if status else "✗"
        solutions = flag_solutions.get(flag_name, [])
        description = solutions[0]["description"] if solutions else "Unknown"
        print_and_log(f"[*] {status_str} {flag_name}: {description}", LOG__GENERAL)
    
    return results

# -----------------------------------------------------------------------------
# Flag Visualization
# -----------------------------------------------------------------------------

def generate_flag_visualization(device: Any) -> str:
    """
    Generate a visual representation of the BLE CTF device's flags and their status.
    
    Parameters
    ----------
    device : Any
        The connected BLE device
        
    Returns
    -------
    str
        A string containing the visualization
    """
    # Read the current score
    try:
        score_char = BLE_CTF__CHARACTERISTIC_FLAGS["Flag-Score"]
        score = ble_ctf__read_characteristic(score_char, device)
    except Exception:
        score = "Unknown"
    
    # Discover flags and solutions
    flag_solutions = discover_flags(device)
    
    # Try to get actual solved status by reading the score
    solved_count = 0
    try:
        match = re.search(r"Score:(\d+)\s*/\s*(\d+)", score)
        if match:
            solved_count = int(match.group(1))
    except Exception:
        pass
    
    # Generate the visualization
    lines = []
    lines.append("┌─" + "─" * 60 + "┐")
    lines.append(f"│ BLE CTF Flag Status                 Score: {score:<15} │")
    lines.append("├─" + "─" * 60 + "┤")
    
    # Add header
    lines.append("│ Flag     │ Status  │ Confidence │ Solution                     │")
    lines.append("├─" + "─" * 60 + "┤")
    
    # Add each flag
    for flag_name, solutions in sorted(flag_solutions.items()):
        if solutions:
            best = max(solutions, key=lambda x: x["confidence"])
            # Show a checkmark if we have a solution, but add a note if score is 0
            status = "✓" if best["confidence"] >= 70 else "?"
            if solved_count == 0 and status == "✓":
                status = "✓*"  # Add asterisk to indicate "solution found but not verified"
            confidence = f"{best['confidence']}%" if best["confidence"] > 0 else "N/A"
            solution = str(best["value"])
            if len(solution) > 25:
                solution = solution[:22] + "..."
        else:
            status = "✗"
            confidence = "N/A"
            solution = "Unknown"
        
        lines.append(f"│ {flag_name:<8} │ {status:<7} │ {confidence:<10} │ {solution:<27} │")
    
    lines.append("└─" + "─" * 60 + "┘")
    
    # Add a note if we're showing solutions but score is 0
    if solved_count == 0 and any("✓*" in line for line in lines):
        lines.append("")
        lines.append("* Solutions found but not verified (score is 0)")
    
    return "\n".join(lines)
