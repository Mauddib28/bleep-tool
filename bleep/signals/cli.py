"""Command-line interface for signal configuration.

This module provides a CLI for managing signal capture configurations.
"""

import argparse
import json
import os
import sys
from typing import List, Optional, Dict, Any

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.signals.capture_config import (
    SignalCaptureConfig,
    SignalFilter,
    SignalRoute,
    SignalAction,
    SignalType,
    ActionType,
    load_config,
    save_config,
    list_configs,
    create_default_config,
)


def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser.
    
    Returns:
        Argument parser
    """
    parser = argparse.ArgumentParser(
        prog="bleep-signal-config",
        description="Manage signal capture configurations"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # List configs
    list_parser = subparsers.add_parser("list", help="List available configurations")
    
    # Create config
    create_parser = subparsers.add_parser("create", help="Create a new configuration")
    create_parser.add_argument("name", help="Name of the configuration")
    create_parser.add_argument("--description", help="Description of the configuration")
    create_parser.add_argument("--default", action="store_true", help="Create a default configuration with example routes")
    
    # Show config
    show_parser = subparsers.add_parser("show", help="Show a configuration")
    show_parser.add_argument("config", help="Name of the configuration file")
    
    # Add route
    add_route_parser = subparsers.add_parser("add-route", help="Add a route to a configuration")
    add_route_parser.add_argument("config", help="Name of the configuration file")
    add_route_parser.add_argument("name", help="Name of the route")
    add_route_parser.add_argument("--description", help="Description of the route")
    add_route_parser.add_argument("--signal-type", choices=[t.value for t in SignalType], help="Signal type filter")
    add_route_parser.add_argument("--device-mac", help="Device MAC address filter")
    add_route_parser.add_argument("--service-uuid", help="Service UUID filter")
    add_route_parser.add_argument("--char-uuid", help="Characteristic UUID filter")
    add_route_parser.add_argument("--path-pattern", help="D-Bus path pattern filter (regex)")
    add_route_parser.add_argument("--property-name", help="Property name filter")
    add_route_parser.add_argument("--value-pattern", help="Value pattern filter (regex)")
    add_route_parser.add_argument("--min-value-length", type=int, help="Minimum value length filter")
    add_route_parser.add_argument("--max-value-length", type=int, help="Maximum value length filter")
    add_route_parser.add_argument("--action", choices=[a.value for a in ActionType], required=True, help="Action type")
    add_route_parser.add_argument("--action-name", help="Action name")
    add_route_parser.add_argument("--action-params", help="Action parameters as JSON")
    add_route_parser.add_argument("--disabled", action="store_true", help="Create the route as disabled")
    
    # Remove route
    remove_route_parser = subparsers.add_parser("remove-route", help="Remove a route from a configuration")
    remove_route_parser.add_argument("config", help="Name of the configuration file")
    remove_route_parser.add_argument("name", help="Name of the route to remove")
    
    # Enable/disable route
    enable_route_parser = subparsers.add_parser("enable-route", help="Enable a route")
    enable_route_parser.add_argument("config", help="Name of the configuration file")
    enable_route_parser.add_argument("name", help="Name of the route to enable")
    
    disable_route_parser = subparsers.add_parser("disable-route", help="Disable a route")
    disable_route_parser.add_argument("config", help="Name of the configuration file")
    disable_route_parser.add_argument("name", help="Name of the route to disable")
    
    # Import/export
    import_parser = subparsers.add_parser("import", help="Import a configuration from a JSON file")
    import_parser.add_argument("file", help="JSON file to import")
    import_parser.add_argument("--name", help="Name for the imported configuration")
    
    export_parser = subparsers.add_parser("export", help="Export a configuration to a JSON file")
    export_parser.add_argument("config", help="Name of the configuration file")
    export_parser.add_argument("file", help="JSON file to export to")
    
    return parser


def _cmd_list() -> int:
    """List available configurations.
    
    Returns:
        Exit code
    """
    configs = list_configs()
    
    if not configs:
        print_and_log("No configurations found", LOG__GENERAL)
        return 0
    
    print_and_log("Available configurations:", LOG__GENERAL)
    for config in configs:
        print_and_log(f"  {config}", LOG__GENERAL)
    
    return 0


def _cmd_create(args: argparse.Namespace) -> int:
    """Create a new configuration.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    name = args.name
    description = args.description or f"Signal capture configuration: {name}"
    
    if args.default:
        config = create_default_config()
        config.name = name
        config.description = description
    else:
        config = SignalCaptureConfig(name=name, description=description)
    
    filepath = save_config(config)
    print_and_log(f"Created configuration: {filepath}", LOG__GENERAL)
    
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    """Show a configuration.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print_and_log(f"Configuration not found: {args.config}", LOG__GENERAL)
        return 1
    except ValueError as e:
        print_and_log(f"Error loading configuration: {e}", LOG__GENERAL)
        return 1
    
    print_and_log(f"Configuration: {config.name}", LOG__GENERAL)
    print_and_log(f"Description: {config.description}", LOG__GENERAL)
    print_and_log(f"Created: {config.created_at}", LOG__GENERAL)
    print_and_log(f"Updated: {config.updated_at}", LOG__GENERAL)
    print_and_log(f"Version: {config.version}", LOG__GENERAL)
    print_and_log(f"Routes: {len(config.routes)}", LOG__GENERAL)
    
    for i, route in enumerate(config.routes):
        status = "enabled" if route.enabled else "disabled"
        print_and_log(f"\nRoute {i+1}: {route.name} ({status})", LOG__GENERAL)
        print_and_log(f"  Description: {route.description}", LOG__GENERAL)
        
        # Filter
        filter_parts = []
        if route.filter.signal_type:
            filter_parts.append(f"signal_type={route.filter.signal_type.value}")
        if route.filter.device_mac:
            filter_parts.append(f"device_mac={route.filter.device_mac}")
        if route.filter.service_uuid:
            filter_parts.append(f"service_uuid={route.filter.service_uuid}")
        if route.filter.char_uuid:
            filter_parts.append(f"char_uuid={route.filter.char_uuid}")
        if route.filter.path_pattern:
            filter_parts.append(f"path_pattern={route.filter.path_pattern}")
        if route.filter.property_name:
            filter_parts.append(f"property_name={route.filter.property_name}")
        if route.filter.value_pattern:
            filter_parts.append(f"value_pattern={route.filter.value_pattern}")
        if route.filter.min_value_length is not None:
            filter_parts.append(f"min_value_length={route.filter.min_value_length}")
        if route.filter.max_value_length is not None:
            filter_parts.append(f"max_value_length={route.filter.max_value_length}")
        
        print_and_log(f"  Filter: {', '.join(filter_parts)}", LOG__GENERAL)
        
        # Actions
        for j, action in enumerate(route.actions):
            print_and_log(f"  Action {j+1}: {action.name} ({action.action_type.value})", LOG__GENERAL)
            if action.parameters:
                print_and_log(f"    Parameters: {json.dumps(action.parameters)}", LOG__GENERAL)
    
    return 0


def _cmd_add_route(args: argparse.Namespace) -> int:
    """Add a route to a configuration.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print_and_log(f"Configuration not found: {args.config}", LOG__GENERAL)
        return 1
    except ValueError as e:
        print_and_log(f"Error loading configuration: {e}", LOG__GENERAL)
        return 1
    
    # Check if route with the same name already exists
    if config.get_route(args.name):
        print_and_log(f"Route already exists: {args.name}", LOG__GENERAL)
        return 1
    
    # Create filter
    filter_kwargs = {}
    
    if args.signal_type:
        filter_kwargs["signal_type"] = SignalType(args.signal_type)
    if args.device_mac:
        filter_kwargs["device_mac"] = args.device_mac
    if args.service_uuid:
        filter_kwargs["service_uuid"] = args.service_uuid
    if args.char_uuid:
        filter_kwargs["char_uuid"] = args.char_uuid
    if args.path_pattern:
        filter_kwargs["path_pattern"] = args.path_pattern
    if args.property_name:
        filter_kwargs["property_name"] = args.property_name
    if args.value_pattern:
        filter_kwargs["value_pattern"] = args.value_pattern
    if args.min_value_length is not None:
        filter_kwargs["min_value_length"] = args.min_value_length
    if args.max_value_length is not None:
        filter_kwargs["max_value_length"] = args.max_value_length
    
    signal_filter = SignalFilter(**filter_kwargs)
    
    # Create action
    action_type = ActionType(args.action)
    action_name = args.action_name or f"{action_type.value}_action"
    action_params = {}
    
    if args.action_params:
        try:
            action_params = json.loads(args.action_params)
        except json.JSONDecodeError:
            print_and_log("Invalid action parameters JSON", LOG__GENERAL)
            return 1
    
    action = SignalAction(action_type=action_type, name=action_name, parameters=action_params)
    
    # Create route
    route = SignalRoute(
        name=args.name,
        description=args.description or f"Route: {args.name}",
        filter=signal_filter,
        actions=[action],
        enabled=not args.disabled
    )
    
    # Add route to config
    config.add_route(route)
    
    # Save config
    save_config(config, args.config)
    print_and_log(f"Added route '{args.name}' to configuration", LOG__GENERAL)
    
    return 0


def _cmd_remove_route(args: argparse.Namespace) -> int:
    """Remove a route from a configuration.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print_and_log(f"Configuration not found: {args.config}", LOG__GENERAL)
        return 1
    except ValueError as e:
        print_and_log(f"Error loading configuration: {e}", LOG__GENERAL)
        return 1
    
    if not config.remove_route(args.name):
        print_and_log(f"Route not found: {args.name}", LOG__GENERAL)
        return 1
    
    save_config(config, args.config)
    print_and_log(f"Removed route '{args.name}' from configuration", LOG__GENERAL)
    
    return 0


def _cmd_enable_route(args: argparse.Namespace) -> int:
    """Enable a route.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print_and_log(f"Configuration not found: {args.config}", LOG__GENERAL)
        return 1
    except ValueError as e:
        print_and_log(f"Error loading configuration: {e}", LOG__GENERAL)
        return 1
    
    if not config.enable_route(args.name):
        print_and_log(f"Route not found or already enabled: {args.name}", LOG__GENERAL)
        return 1
    
    save_config(config, args.config)
    print_and_log(f"Enabled route '{args.name}'", LOG__GENERAL)
    
    return 0


def _cmd_disable_route(args: argparse.Namespace) -> int:
    """Disable a route.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print_and_log(f"Configuration not found: {args.config}", LOG__GENERAL)
        return 1
    except ValueError as e:
        print_and_log(f"Error loading configuration: {e}", LOG__GENERAL)
        return 1
    
    if not config.disable_route(args.name):
        print_and_log(f"Route not found or already disabled: {args.name}", LOG__GENERAL)
        return 1
    
    save_config(config, args.config)
    print_and_log(f"Disabled route '{args.name}'", LOG__GENERAL)
    
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    """Import a configuration from a JSON file.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    try:
        with open(args.file, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print_and_log(f"File not found: {args.file}", LOG__GENERAL)
        return 1
    except json.JSONDecodeError:
        print_and_log(f"Invalid JSON file: {args.file}", LOG__GENERAL)
        return 1
    
    try:
        config = SignalCaptureConfig.from_dict(data)
    except Exception as e:
        print_and_log(f"Error creating configuration from file: {e}", LOG__GENERAL)
        return 1
    
    if args.name:
        config.name = args.name
    
    filepath = save_config(config)
    print_and_log(f"Imported configuration: {filepath}", LOG__GENERAL)
    
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    """Export a configuration to a JSON file.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print_and_log(f"Configuration not found: {args.config}", LOG__GENERAL)
        return 1
    except ValueError as e:
        print_and_log(f"Error loading configuration: {e}", LOG__GENERAL)
        return 1
    
    try:
        with open(args.file, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
    except Exception as e:
        print_and_log(f"Error exporting configuration: {e}", LOG__GENERAL)
        return 1
    
    print_and_log(f"Exported configuration to: {args.file}", LOG__GENERAL)
    
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI.
    
    Args:
        argv: Command line arguments (defaults to sys.argv[1:])
        
    Returns:
        Exit code
    """
    parser = _create_parser()
    args = parser.parse_args(argv or sys.argv[1:])
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == "list":
        return _cmd_list()
    elif args.command == "create":
        return _cmd_create(args)
    elif args.command == "show":
        return _cmd_show(args)
    elif args.command == "add-route":
        return _cmd_add_route(args)
    elif args.command == "remove-route":
        return _cmd_remove_route(args)
    elif args.command == "enable-route":
        return _cmd_enable_route(args)
    elif args.command == "disable-route":
        return _cmd_disable_route(args)
    elif args.command == "import":
        return _cmd_import(args)
    elif args.command == "export":
        return _cmd_export(args)
    else:
        print_and_log(f"Unknown command: {args.command}", LOG__GENERAL)
        return 1


if __name__ == "__main__":
    sys.exit(main())
