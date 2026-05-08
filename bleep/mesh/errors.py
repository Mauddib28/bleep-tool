"""Bluetooth Mesh error mapping.

Maps ``org.bluez.mesh.Error.*`` D-Bus error names to BLEEP exception types.
Follows the same pattern as ``bleep.core.error_handling`` for the core BlueZ
stack.

Reference: ``workDir/bluez/doc/mesh-api.txt`` error returns.
"""

from __future__ import annotations

import dbus.exceptions

from bleep.mesh.constants import (
    MESH_ERROR_ABORT,
    MESH_ERROR_ALREADY_EXISTS,
    MESH_ERROR_BUSY,
    MESH_ERROR_DOES_NOT_EXIST,
    MESH_ERROR_FAILED,
    MESH_ERROR_IN_PROGRESS,
    MESH_ERROR_INVALID_ARGS,
    MESH_ERROR_NOT_AUTHORIZED,
    MESH_ERROR_NOT_FOUND,
    MESH_ERROR_NOT_SUPPORTED,
    MESH_ERROR_PREFIX,
)


class MeshError(RuntimeError):
    """Base exception for Bluetooth Mesh operations."""

    def __init__(self, message: str, dbus_name: str | None = None):
        super().__init__(message)
        self.dbus_name = dbus_name


class MeshInvalidArgsError(MeshError):
    """Invalid arguments supplied to a mesh method."""


class MeshAlreadyExistsError(MeshError):
    """Resource already exists (e.g. duplicate subnet or appkey)."""


class MeshNotFoundError(MeshError):
    """Requested resource not found."""


class MeshBusyError(MeshError):
    """Daemon is busy (e.g. provisioning in progress)."""


class MeshNotAuthorizedError(MeshError):
    """Caller is not authorized for this operation."""


class MeshNotSupportedError(MeshError):
    """Operation not supported by this node/daemon version."""


class MeshInProgressError(MeshError):
    """Operation already in progress."""


class MeshAbortError(MeshError):
    """Operation was aborted."""


_ERROR_MAP: dict[str, type[MeshError]] = {
    MESH_ERROR_INVALID_ARGS: MeshInvalidArgsError,
    MESH_ERROR_ALREADY_EXISTS: MeshAlreadyExistsError,
    MESH_ERROR_NOT_FOUND: MeshNotFoundError,
    MESH_ERROR_DOES_NOT_EXIST: MeshNotFoundError,
    MESH_ERROR_BUSY: MeshBusyError,
    MESH_ERROR_FAILED: MeshError,
    MESH_ERROR_NOT_AUTHORIZED: MeshNotAuthorizedError,
    MESH_ERROR_NOT_SUPPORTED: MeshNotSupportedError,
    MESH_ERROR_IN_PROGRESS: MeshInProgressError,
    MESH_ERROR_ABORT: MeshAbortError,
}


def map_mesh_dbus_error(exc: dbus.exceptions.DBusException) -> MeshError:
    """Convert a D-Bus exception from ``bluetooth-meshd`` to a typed error.

    Falls back to the base :class:`MeshError` for unknown error names.
    """
    name = exc.get_dbus_name() or ""
    msg = exc.get_dbus_message() or str(exc)

    if name.startswith(MESH_ERROR_PREFIX):
        cls = _ERROR_MAP.get(name, MeshError)
        return cls(msg, dbus_name=name)

    return MeshError(msg, dbus_name=name)
