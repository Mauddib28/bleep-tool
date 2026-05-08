# Bluetooth Agent Documentation Index

This document serves as an index for all Bluetooth agent-related documentation in the BLEEP framework.

## Overview

The BLEEP framework includes a comprehensive Bluetooth agent implementation for handling pairing, bonding, and authorization requests. This system is designed to be flexible, secure, and reliable, with support for various interaction modes and integration with the D-Bus reliability framework.

## Core Documentation

1. [Pairing Agent](pairing_agent.md): Comprehensive guide to the pairing agent system, including architecture, usage examples, and best practices.

2. [Agent Mode](agent_mode.md): Documentation for the `bleep agent` command-line mode.

3. [Debug Mode — Pairing](debug_mode.md#pairing-with-the-pair-command): Pairing and brute-force from the debug shell, including lockout detection and post-pair connection flows.

## Component Documentation

### Agent Classes (`bleep/dbuslayer/agent.py`)

| Class | Description |
|-------|-------------|
| `BlueZAgent` | Base class for all agents — handles D-Bus registration and Agent1 interface |
| `SimpleAgent` | Auto-accepting agent — accepts all pairing/authorization requests |
| `InteractiveAgent` | CLI-based interactive agent — prompts the user for PIN/passkey |
| `EnhancedAgent` | Callback-based agent — delegates decisions to an I/O handler |
| `PairingAgent` | Full-featured agent with state machine, storage, and brute-force support |

### I/O Handlers (`bleep/dbuslayer/agent_io.py`)

| Class | Description |
|-------|-------------|
| `AgentIOHandler` | Abstract base class defining the I/O contract |
| `CliIOHandler` | Terminal-based interaction (stdin/stdout) |
| `ProgrammaticIOHandler` | Callback-based interaction for embedding in other tools |
| `AutoAcceptIOHandler` | Auto-accept all requests (no user interaction) |

### State Machine (`bleep/dbuslayer/pairing_state.py`)

- `PairingStateMachine`: Manages pairing process states and transitions.

### Secure Storage (`bleep/dbuslayer/bond_storage.py`)

- `SecureStorage`: Base class for secure persistence.
- `DeviceBondStore`: Manages device bonding information on disk.
- `PairingCache`: In-memory cache for active pairing data.

## Integration Points

1. [D-Bus Reliability](d-bus-reliability.md): How the agent integrates with the D-Bus reliability framework (timeout enforcement, connection recovery).

2. [D-Bus Best Practices](dbus_best_practices.md): Error handling patterns and recovery strategies applicable to agent operations.

## External References

1. [BlueZ Agent API](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc/agent-api.txt): Official BlueZ documentation for the Agent1 interface.

2. [Secure Simple Pairing (SSP)](https://www.bluetooth.com/blog/secure-simple-pairing/): Overview of Bluetooth Secure Simple Pairing.

---

*Last updated: 2026-03-18*
