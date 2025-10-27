# Agent Mode

The `bleep agent` mode provides a command-line interface for Bluetooth pairing operations. This document covers the usage and options of this mode.

## Overview

The agent mode allows you to register a Bluetooth agent for handling pairing requests and managing trust relationships. It supports different types of agents with various capabilities and interaction models.

## Basic Usage

```
bleep agent [OPTIONS]
```

## Agent Types

The `--mode` option determines which type of agent to create:

- `simple`: Auto-accepts all pairing requests. Useful for unattended operation.
- `interactive`: Prompts user via terminal for all decisions. Good for CLI applications.
- `enhanced`: Configurable callback-based agent. Suitable for integration with other applications.
- `pairing`: Full-featured agent with state machine and secure storage. Best for complex applications.

## Agent Capabilities

The `--cap` option sets the agent's capabilities:

- `none`: No input or output capability (`NoInputNoOutput`).
- `display`: Can display but not accept input (`DisplayOnly`).
- `yesno`: Can display and accept yes/no input (`DisplayYesNo`).
- `keyboard`: Can accept input but not display (`KeyboardOnly`).
- `kbdisp`: Can both display and accept input (`KeyboardDisplay`).

## Options

### Registration Options

- `--mode=MODE`: Agent type (simple, interactive, enhanced, pairing).
- `--cap=CAP`: Agent capabilities (none, display, yesno, keyboard, kbdisp).
- `--default`: Register as the default agent.
- `--auto-accept`: Auto-accept pairing requests (for enhanced and pairing agents).
- `--timeout=SECONDS`: Timeout for pairing operations (default: 30 seconds).

### Trust Management

- `--trust=MAC`: Set a device as trusted.
- `--untrust=MAC`: Set a device as untrusted.
- `--list-trusted`: List all trusted devices.

### Bond Management

- `--list-bonded`: List all bonded devices with stored keys.
- `--remove-bond=MAC`: Remove bonding information for a device.
- `--storage-path=PATH`: Path to store bonding information.

### Pairing

- `--pair=MAC`: Pair with a device (only for pairing agent).

## Examples

### Run a Simple Agent

```bash
# Register a simple agent as default with no input/output capability
bleep agent --mode=simple --cap=none --default
```

### Run an Interactive Agent

```bash
# Register an interactive agent with keyboard-display capability
bleep agent --mode=interactive --cap=kbdisp
```

### Pair with a Device

```bash
# Pair with a specific device
bleep agent --mode=pairing --pair=00:11:22:33:44:55 --cap=kbdisp
```

### Manage Trust Relationships

```bash
# Set a device as trusted
bleep agent --trust=00:11:22:33:44:55

# List all trusted devices
bleep agent --list-trusted

# Set a device as untrusted
bleep agent --untrust=00:11:22:33:44:55
```

### Manage Bond Information

```bash
# List all bonded devices
bleep agent --list-bonded

# Remove bond information for a device
bleep agent --remove-bond=00:11:22:33:44:55

# Use custom storage path
bleep agent --list-bonded --storage-path=/path/to/storage
```

## Programmatic Usage

The agent functionality is also available programmatically. See [Pairing Agent](./pairing_agent.md) documentation for details.

## Related Documentation

- [Pairing Agent](./pairing_agent.md): Comprehensive guide to the pairing agent system.
- [Agent Documentation Index](./agent_documentation_index.md): Index of all agent-related documentation.
