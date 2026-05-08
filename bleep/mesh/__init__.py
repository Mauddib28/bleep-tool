"""Bluetooth Mesh support for BLEEP.

Provides D-Bus wrappers for BlueZ's ``bluetooth-meshd`` mesh daemon,
following ``workDir/bluez/doc/mesh-api.txt``.

Modules
-------
- ``constants`` — D-Bus service names, interface names, paths, and error codes.
- ``errors`` — Exception hierarchy for ``org.bluez.mesh.Error.*`` errors.
- ``network`` — ``Network1`` client (join/attach/leave/create/import).
- ``node`` — ``Node1`` client (send/publish/key management, node properties).
- ``management`` — ``Management1`` client (provisioning ops, key DB).
- ``application`` — ``Application1`` D-Bus service skeleton (join callbacks).
- ``element`` — ``Element1`` D-Bus service skeleton (message receive).
- ``provisioner`` — ``Provisioner1`` D-Bus service skeleton (scan/prov callbacks).
- ``provision_agent`` — ``ProvisionAgent1`` D-Bus service skeleton (OOB auth).
- ``proxy_solicitation`` — Send Mesh Proxy Solicitation PDUs.
"""

from . import constants  # noqa: F401
from . import errors  # noqa: F401
from . import proxy_solicitation as proxy  # noqa: F401

__all__ = [
    "constants",
    "errors",
    "proxy",
]

# Heavier modules that require dbus are loaded lazily to avoid import-time
# failures when bluetooth-meshd is not running.


def __getattr__(name: str):
    _lazy = {
        "network": ".network",
        "node": ".node",
        "management": ".management",
        "application": ".application",
        "element": ".element",
        "provisioner": ".provisioner",
        "provision_agent": ".provision_agent",
    }
    if name in _lazy:
        import importlib
        mod = importlib.import_module(_lazy[name], __package__)
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
