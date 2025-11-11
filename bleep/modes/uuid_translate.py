"""
CLI mode for UUID translation.

This module provides a command-line interface for translating UUIDs to
human-readable formats using BLEEP's internal UUID databases.
"""

import argparse
import json
import sys
from typing import List, Optional

from bleep.bt_ref.uuid_translator import translate_uuid, UUIDCategory
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG


def format_uuid_with_dashes(uuid: str) -> str:
    """
    Format a UUID string with dashes in standard format.
    
    Args:
        uuid: UUID string without dashes (32 hex characters)
        
    Returns:
        UUID string with dashes: XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
    """
    if len(uuid) != 32:
        return uuid
    
    return f"{uuid[0:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:32]}"


def format_text_output(result: dict, verbose: bool = False) -> str:
    """
    Format translation result as human-readable text.
    
    Args:
        result: Translation result dictionary from translate_uuid()
        verbose: If True, include additional details
        
    Returns:
        Formatted text string
    """
    lines = []
    
    # Header
    lines.append("UUID Translation Results")
    lines.append("=" * 50)
    
    # Input information
    lines.append(f"Input UUID: {result['input_uuid']}")
    lines.append(f"Format: {result['uuid_format']}")
    
    # Normalized UUID
    normalized_formatted = format_uuid_with_dashes(result['normalized_uuid'])
    lines.append(f"Canonical 128-bit: {normalized_formatted}")
    
    # Short form if available
    if result.get('short_form'):
        lines.append(f"16-bit form: {result['short_form']}")
    
    # BT SIG format indicator
    if result.get('is_bt_sig_format'):
        lines.append("BT SIG Format: Yes")
    
    lines.append("")
    
    # Matches
    match_count = result['match_count']
    lines.append(f"Matches Found: {match_count}")
    lines.append("")
    
    if match_count == 0:
        lines.append("No matches found in BLEEP databases.")
        lines.append("This may be a custom/vendor-specific UUID.")
    else:
        # Group matches by category
        matches_by_category: dict[str, list] = {}
        for match in result['matches']:
            category = match['category'].value if isinstance(match['category'], UUIDCategory) else match['category']
            if category not in matches_by_category:
                matches_by_category[category] = []
            matches_by_category[category].append(match)
        
        # Display matches grouped by category
        for category in sorted(matches_by_category.keys()):
            matches = matches_by_category[category]
            lines.append(f"[{category}]")
            
            for match in matches:
                uuid_formatted = format_uuid_with_dashes(match['uuid'])
                name = match['name']
                lines.append(f"  {uuid_formatted}: {name}")
                
                if verbose:
                    source = match.get('source', 'Unknown')
                    lines.append(f"    Source: {source}")
            
            lines.append("")
    
    return "\n".join(lines)


def format_json_output(result: dict) -> str:
    """
    Format translation result as JSON.
    
    Args:
        result: Translation result dictionary from translate_uuid()
        
    Returns:
        JSON-formatted string
    """
    # Convert UUIDCategory enums to strings for JSON serialization
    json_result = result.copy()
    json_result['matches'] = [
        {
            **match,
            'category': match['category'].value if isinstance(match['category'], UUIDCategory) else match['category']
        }
        for match in json_result['matches']
    ]
    
    return json.dumps(json_result, indent=2, ensure_ascii=False)


def translate_single_uuid(uuid_input: str, json_output: bool = False, verbose: bool = False) -> int:
    """
    Translate a single UUID and print results.
    
    Args:
        uuid_input: UUID string to translate
        json_output: If True, output in JSON format
        verbose: If True, include verbose details
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        result = translate_uuid(uuid_input)
        
        if json_output:
            output = format_json_output(result)
        else:
            output = format_text_output(result, verbose)
        
        print(output)
        
        return 0
        
    except Exception as e:
        print(f"Error translating UUID '{uuid_input}': {e}", file=sys.stderr)
        if verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return 1


def translate_multiple_uuids(uuids: List[str], json_output: bool = False, verbose: bool = False) -> int:
    """
    Translate multiple UUIDs and print results.
    
    Args:
        uuids: List of UUID strings to translate
        json_output: If True, output in JSON format
        verbose: If True, include verbose details
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    results = []
    errors = []
    
    for uuid_input in uuids:
        try:
            result = translate_uuid(uuid_input)
            results.append(result)
        except Exception as e:
            error_msg = f"Error translating UUID '{uuid_input}': {e}"
            errors.append(error_msg)
            if verbose:
                print(error_msg, file=sys.stderr)
    
    if json_output:
        # Output as JSON array
        json_results = []
        for result in results:
            json_result = result.copy()
            json_result['matches'] = [
                {
                    **match,
                    'category': match['category'].value if isinstance(match['category'], UUIDCategory) else match['category']
                }
                for match in json_result['matches']
            ]
            json_results.append(json_result)
        
        print(json.dumps(json_results, indent=2, ensure_ascii=False))
    else:
        # Output each result separately
        for i, result in enumerate(results):
            if i > 0:
                print("\n" + "-" * 50 + "\n")
            print(format_text_output(result, verbose))
        
        # Print errors if any
        if errors:
            print("\n" + "=" * 50)
            print("Errors:")
            for error in errors:
                print(f"  {error}")
    
    # Return error code if any errors occurred
    return 1 if errors else 0


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments for UUID translation.
    
    Args:
        args: Optional list of arguments (defaults to sys.argv)
        
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Translate UUID(s) to human-readable format using BLEEP's internal databases",
        prog="bleep uuid-translate"
    )
    
    parser.add_argument(
        "uuids",
        nargs="+",
        help="UUID(s) to translate (16-bit, 32-bit, or 128-bit format)"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed information including source databases"
    )
    
    parser.add_argument(
        "--include-unknown",
        action="store_true",
        help="Include 'Unknown' entries in results"
    )
    
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """
    Main entry point for UUID translation CLI mode.
    
    Args:
        args: Optional list of command-line arguments
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    parsed_args = parse_args(args)
    
    # Enable verbose logging if requested
    if parsed_args.verbose:
        import logging
        logging.getLogger("bleep").setLevel(logging.DEBUG)
    
    # Translate UUIDs
    if len(parsed_args.uuids) == 1:
        # Single UUID
        return translate_single_uuid(
            parsed_args.uuids[0],
            json_output=parsed_args.json,
            verbose=parsed_args.verbose
        )
    else:
        # Multiple UUIDs
        return translate_multiple_uuids(
            parsed_args.uuids,
            json_output=parsed_args.json,
            verbose=parsed_args.verbose
        )


if __name__ == "__main__":
    sys.exit(main())

