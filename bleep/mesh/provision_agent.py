"""D-Bus service implementing ``org.bluez.mesh.ProvisionAgent1``.

The provision agent handles OOB (Out-of-Band) authentication during the
mesh provisioning process.  The daemon calls methods to request or display
keys and numeric/string values.

Reference: ``workDir/bluez/doc/mesh-api.txt`` lines 1240–1375.
"""

from __future__ import annotations

from typing import Any, List, Optional

import dbus
import dbus.service

from bleep.core.log import print_and_log, LOG__GENERAL
from bleep.mesh.constants import MESH_PROVISION_AGENT_IFACE


class MeshProvisionAgent(dbus.service.Object):
    """Skeleton ``ProvisionAgent1`` for OOB authentication.

    Parameters
    ----------
    bus : dbus.SystemBus
        Bus to register on.
    path : str
        Agent object path.
    capabilities : list[str]
        Agent capabilities from the spec: ``blink``, ``beep``, ``vibrate``,
        ``out-numeric``, ``out-alpha``, ``in-numeric``, ``in-alpha``,
        ``static-oob``, ``public-oob``.
    oob_info : list[str], optional
        Optional OOB information hints.
    uri : str, optional
        Optional provisioning URI.
    """

    def __init__(
        self,
        bus: dbus.SystemBus,
        path: str,
        capabilities: Optional[List[str]] = None,
        oob_info: Optional[List[str]] = None,
        uri: Optional[str] = None,
    ):
        super().__init__(bus, path)
        self.path = path
        self._capabilities = capabilities or ["out-numeric", "in-numeric"]
        self._oob_info = oob_info
        self._uri = uri

    # -- ProvisionAgent1 methods -------------------------------------------

    @dbus.service.method(MESH_PROVISION_AGENT_IFACE, out_signature="ay")
    def PrivateKey(self) -> dbus.Array:
        key = self.on_private_key()
        return dbus.Array(key, signature="y")

    @dbus.service.method(MESH_PROVISION_AGENT_IFACE, out_signature="ay")
    def PublicKey(self) -> dbus.Array:
        key = self.on_public_key()
        return dbus.Array(key, signature="y")

    @dbus.service.method(MESH_PROVISION_AGENT_IFACE, in_signature="s")
    def DisplayString(self, value: str) -> None:
        print_and_log(f"[mesh-agent] DisplayString: {value}", LOG__GENERAL)
        self.on_display_string(str(value))

    @dbus.service.method(MESH_PROVISION_AGENT_IFACE, in_signature="su")
    def DisplayNumeric(self, type_: str, number: dbus.UInt32) -> None:
        print_and_log(
            f"[mesh-agent] DisplayNumeric type={type_} number={int(number)}",
            LOG__GENERAL,
        )
        self.on_display_numeric(str(type_), int(number))

    @dbus.service.method(
        MESH_PROVISION_AGENT_IFACE, in_signature="s", out_signature="u",
    )
    def PromptNumeric(self, type_: str) -> dbus.UInt32:
        value = self.on_prompt_numeric(str(type_))
        return dbus.UInt32(value)

    @dbus.service.method(
        MESH_PROVISION_AGENT_IFACE, in_signature="s", out_signature="ay",
    )
    def PromptStatic(self, type_: str) -> dbus.Array:
        value = self.on_prompt_static(str(type_))
        return dbus.Array(value, signature="y")

    @dbus.service.method(MESH_PROVISION_AGENT_IFACE)
    def Cancel(self) -> None:
        print_and_log("[mesh-agent] Cancel", LOG__GENERAL)
        self.on_cancel()

    # -- Properties (read by daemon via standard Properties interface) ------

    @dbus.service.method(
        "org.freedesktop.DBus.Properties",
        in_signature="ss",
        out_signature="v",
    )
    def Get(self, interface: str, prop: str) -> Any:
        if interface != MESH_PROVISION_AGENT_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs",
            )
        if prop == "Capabilities":
            return dbus.Array(self._capabilities, signature="s")
        if prop == "OutOfBandInfo" and self._oob_info is not None:
            return dbus.Array(self._oob_info, signature="s")
        if prop == "URI" and self._uri is not None:
            return dbus.String(self._uri)
        raise dbus.exceptions.DBusException(
            "org.freedesktop.DBus.Error.InvalidArgs",
        )

    @dbus.service.method(
        "org.freedesktop.DBus.Properties",
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, interface: str) -> dbus.Dictionary:
        if interface != MESH_PROVISION_AGENT_IFACE:
            return dbus.Dictionary({}, signature="sv")
        props: dict = {
            "Capabilities": dbus.Array(self._capabilities, signature="s"),
        }
        if self._oob_info is not None:
            props["OutOfBandInfo"] = dbus.Array(self._oob_info, signature="s")
        if self._uri is not None:
            props["URI"] = dbus.String(self._uri)
        return dbus.Dictionary(props, signature="sv")

    # -- Hooks for subclasses ----------------------------------------------

    def on_private_key(self) -> bytes:
        """Override to provide a 32-byte private key."""
        raise NotImplementedError("Subclass must implement on_private_key")

    def on_public_key(self) -> bytes:
        """Override to provide a 64-byte public key."""
        raise NotImplementedError("Subclass must implement on_public_key")

    def on_display_string(self, value: str) -> None:
        """Override to display an alphanumeric string to the user."""

    def on_display_numeric(self, type_: str, number: int) -> None:
        """Override to display a numeric value to the user."""

    def on_prompt_numeric(self, type_: str) -> int:
        """Override to prompt the user for a numeric value."""
        raise NotImplementedError("Subclass must implement on_prompt_numeric")

    def on_prompt_static(self, type_: str) -> bytes:
        """Override to prompt the user for a 16-byte static OOB value."""
        raise NotImplementedError("Subclass must implement on_prompt_static")

    def on_cancel(self) -> None:
        """Override to handle agent cancellation."""
