"""Interactive MeshProvisionAgent using AgentIOHandler pattern (BZ-24a).

Provides a concrete ``MeshProvisionAgent`` subclass that delegates OOB
authentication prompts and display calls to a pluggable I/O handler,
following the same ``AgentIOHandler`` pattern used for Bluetooth pairing
(``dbuslayer/agent_io.py``).

This bridges the D-Bus ``ProvisionAgent1`` callbacks to the appropriate
I/O handler (CLI, programmatic, auto-accept, etc.) so mesh provisioning
can work in both interactive and headless modes.

Reference: ``workDir/BlueZDocs/mesh-api.txt`` lines 1240-1375.
"""

from __future__ import annotations

from typing import Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.mesh.provision_agent import MeshProvisionAgent


class MeshIOHandler:
    """Abstract I/O handler for mesh provisioning OOB operations.

    Follows the same pattern as ``AgentIOHandler`` but with methods specific
    to mesh provisioning OOB authentication.
    """

    def display_string(self, value: str) -> None:
        """Display an alphanumeric OOB string to the operator."""

    def display_numeric(self, type_: str, number: int) -> None:
        """Display a numeric OOB value to the operator."""

    def prompt_numeric(self, type_: str) -> int:
        """Prompt the operator for a numeric OOB value.

        Returns
        -------
        int
            The numeric value entered by the operator.
        """
        raise NotImplementedError

    def prompt_static(self, type_: str) -> bytes:
        """Prompt the operator for a 16-byte static OOB value.

        Returns
        -------
        bytes
            The 16-byte static value.
        """
        raise NotImplementedError

    def on_cancel(self) -> None:
        """Notify the operator that provisioning was cancelled."""


class CliMeshIOHandler(MeshIOHandler):
    """CLI-based I/O handler for interactive mesh provisioning."""

    def display_string(self, value: str) -> None:
        print_and_log(f"[mesh-oob] Display string: {value}", LOG__GENERAL)

    def display_numeric(self, type_: str, number: int) -> None:
        print_and_log(
            f"[mesh-oob] Display numeric ({type_}): {number}", LOG__GENERAL,
        )

    def prompt_numeric(self, type_: str) -> int:
        print_and_log(f"[mesh-oob] Enter numeric value ({type_}):", LOG__GENERAL)
        while True:
            try:
                return int(input("Numeric OOB value: "))
            except ValueError:
                print_and_log("[-] Invalid number, try again.", LOG__GENERAL)

    def prompt_static(self, type_: str) -> bytes:
        print_and_log(
            f"[mesh-oob] Enter 16-byte static OOB hex ({type_}):", LOG__GENERAL,
        )
        while True:
            try:
                raw = input("Static OOB (32 hex chars): ").strip()
                data = bytes.fromhex(raw)
                if len(data) == 16:
                    return data
                print_and_log("[-] Must be exactly 16 bytes (32 hex chars).", LOG__GENERAL)
            except ValueError:
                print_and_log("[-] Invalid hex, try again.", LOG__GENERAL)

    def on_cancel(self) -> None:
        print_and_log("[mesh-oob] Provisioning cancelled.", LOG__GENERAL)


class AutoAcceptMeshIOHandler(MeshIOHandler):
    """Auto-accept handler for headless/automated mesh provisioning.

    Returns zeros for all OOB prompts.  Suitable for testing or devices
    that use no-OOB provisioning.
    """

    def display_string(self, value: str) -> None:
        print_and_log(f"[mesh-oob-auto] String: {value}", LOG__DEBUG)

    def display_numeric(self, type_: str, number: int) -> None:
        print_and_log(
            f"[mesh-oob-auto] Numeric ({type_}): {number}", LOG__DEBUG,
        )

    def prompt_numeric(self, type_: str) -> int:
        print_and_log(
            f"[mesh-oob-auto] Auto-returning 0 for numeric ({type_})", LOG__DEBUG,
        )
        return 0

    def prompt_static(self, type_: str) -> bytes:
        print_and_log(
            f"[mesh-oob-auto] Auto-returning zeros for static ({type_})", LOG__DEBUG,
        )
        return b"\x00" * 16

    def on_cancel(self) -> None:
        print_and_log("[mesh-oob-auto] Provisioning cancelled.", LOG__DEBUG)


class InteractiveProvisionAgent(MeshProvisionAgent):
    """Concrete ``ProvisionAgent1`` that delegates OOB I/O to a handler.

    Parameters
    ----------
    bus : dbus.SystemBus
        Bus to register on.
    path : str
        Agent object path.
    io_handler : MeshIOHandler, optional
        Handler for OOB prompts/display.  Defaults to :class:`CliMeshIOHandler`.
    capabilities : list[str], optional
        Agent capabilities list.
    oob_info : list[str], optional
        OOB information hints.
    uri : str, optional
        Provisioning URI.
    """

    def __init__(self, bus, path, io_handler=None, **kwargs):
        super().__init__(bus, path, **kwargs)
        self._io: MeshIOHandler = io_handler or CliMeshIOHandler()

    @property
    def io_handler(self) -> MeshIOHandler:
        return self._io

    @io_handler.setter
    def io_handler(self, handler: MeshIOHandler) -> None:
        self._io = handler

    def on_private_key(self) -> bytes:
        raise NotImplementedError(
            "Private key provisioning requires application-specific key management"
        )

    def on_public_key(self) -> bytes:
        raise NotImplementedError(
            "Public key provisioning requires application-specific key management"
        )

    def on_display_string(self, value: str) -> None:
        self._io.display_string(value)

    def on_display_numeric(self, type_: str, number: int) -> None:
        self._io.display_numeric(type_, number)

    def on_prompt_numeric(self, type_: str) -> int:
        return self._io.prompt_numeric(type_)

    def on_prompt_static(self, type_: str) -> bytes:
        return self._io.prompt_static(type_)

    def on_cancel(self) -> None:
        self._io.on_cancel()


def create_mesh_io_handler(handler_type: str = "cli") -> MeshIOHandler:
    """Factory for mesh I/O handlers.

    Parameters
    ----------
    handler_type : str
        ``"cli"`` for interactive terminal, ``"auto"`` for headless.
    """
    if handler_type == "cli":
        return CliMeshIOHandler()
    elif handler_type == "auto":
        return AutoAcceptMeshIOHandler()
    else:
        raise ValueError(f"Unknown mesh IO handler type: {handler_type}")
