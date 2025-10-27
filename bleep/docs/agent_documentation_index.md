# Bluetooth Agent Documentation Index

This document serves as an index for all Bluetooth agent-related documentation in the BLEEP framework.

## Overview

The BLEEP framework includes a comprehensive Bluetooth agent implementation for handling pairing, bonding, and authorization requests. This system is designed to be flexible, secure, and reliable, with support for various interaction modes and integration with the D-Bus reliability framework.

## Core Documentation

1. [Pairing Agent](./pairing_agent.md): Comprehensive guide to the pairing agent system, including architecture, usage examples, and best practices.

2. [Agent Mode](./agent_mode.md): Documentation for the `bleep agent` command-line mode.

## Component Documentation

1. **Agent Classes**:
   - `BlueZAgent`: Base class for all agents
   - `SimpleAgent`: Auto-accepting agent
   - `InteractiveAgent`: CLI-based interactive agent
   - `EnhancedAgent`: Callback-based agent
   - `PairingAgent`: Full-featured agent with state machine and storage

2. **I/O Handlers**:
   - `AgentIOHandler`: Abstract base class
   - `CliIOHandler`: Terminal-based interaction
   - `ProgrammaticIOHandler`: Callback-based interaction
   - `AutoAcceptIOHandler`: Auto-accept all requests

3. **State Machine**:
   - `PairingStateMachine`: Manages pairing process states

4. **Secure Storage**:
   - `SecureStorage`: Base class for secure persistence
   - `DeviceBondStore`: Manages device bonding information
   - `PairingCache`: In-memory cache for pairing data

## Integration Points

1. [D-Bus Reliability](./d-bus-reliability.md): How the agent integrates with the D-Bus reliability framework.

2. [BlueZ Integration](./bluez_integration.md): How the agent interfaces with the BlueZ Bluetooth stack.

## Best Practices

1. [Agent Security Best Practices](./agent_security.md): Guidelines for secure agent implementation and usage.

2. [Pairing Workflows](./pairing_workflows.md): Common pairing workflows and how to implement them.

## References

1. [BlueZ Agent API](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc/agent-api.txt): Official BlueZ documentation for the Agent API.

2. [Secure Simple Pairing (SSP)](https://www.bluetooth.com/blog/secure-simple-pairing/): Overview of Bluetooth Secure Simple Pairing.

## Examples

1. [Simple Pairing Example](../examples/simple_pairing.py): Basic example of pairing with a device.

2. [Custom Agent Example](../examples/custom_agent.py): Example of implementing a custom agent with specialized behavior.

3. [Secure Bonding Example](../examples/secure_bonding.py): Example of securely storing and managing bonding information.

---

For questions, issues, or contributions to the agent documentation, please open an issue or pull request in the repository.
