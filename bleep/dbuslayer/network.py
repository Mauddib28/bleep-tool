"""D-Bus wrapper for BlueZ PAN (Personal Area Networking).

Covers the **client** role via ``org.bluez.Network1`` (per-device, system bus)
and the **server** role via ``org.bluez.NetworkServer1`` (per-adapter, system
bus).

Reference docs
--------------
* ``workDir/BlueZDocs/org.bluez.Network.rst``
* ``workDir/BlueZDocs/org.bluez.NetworkServer.rst``
* ``workDir/BlueZScripts/test-network``
* ``workDir/BlueZScripts/test-nap``
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import dbus

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    BLUEZ_NAMESPACE,
    ADAPTER_NAME,
    DBUS_PROPERTIES,
    NETWORK_INTERFACE as _NET_IFACE,
    NETWORK_SERVER_INTERFACE as _NET_SERVER_IFACE,
)
from bleep.bt_ref.utils import device_address_to_path
from bleep.core.log import print_and_log, LOG__DEBUG

# Valid PAN role strings accepted by BlueZ
_VALID_ROLES = {"panu", "nap", "gn"}


# ---------------------------------------------------------------------------
# Network1 – client side (per-device)
# ---------------------------------------------------------------------------

class NetworkClient:
    """Thin wrapper around ``org.bluez.Network1`` on a remote device.

    Usage::

        client = NetworkClient("AA:BB:CC:DD:EE:FF")
        iface = client.connect("nap")   # returns e.g. "bnep0"
        print(client.connected, client.interface)
        client.disconnect()
    """

    def __init__(
        self,
        mac_address: str,
        *,
        adapter: str = ADAPTER_NAME,
    ):
        self.mac = mac_address.strip().upper()
        self._adapter = adapter
        self._bus = dbus.SystemBus()

        adapter_path = f"{BLUEZ_NAMESPACE}{adapter}"
        self._device_path = device_address_to_path(self.mac, adapter_path)

        try:
            dev_obj = self._bus.get_object(BLUEZ_SERVICE_NAME, self._device_path)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"Device {self.mac} not found on {adapter}: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

        self._net = dbus.Interface(dev_obj, _NET_IFACE)
        self._props = dbus.Interface(dev_obj, DBUS_PROPERTIES)

    # -- methods ---

    def connect(self, role: str = "nap") -> str:
        """Connect as *role* (``panu``, ``nap``, or ``gn``).

        Returns the local network interface name (e.g. ``bnep0``).
        """
        role = role.lower()
        if role not in _VALID_ROLES:
            raise ValueError(f"Invalid PAN role '{role}'; expected one of {_VALID_ROLES}")
        print_and_log(f"[PAN] Connecting to {self.mac} as {role}", LOG__DEBUG)
        try:
            iface_name = str(self._net.Connect(role))
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"PAN Connect failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc
        print_and_log(f"[PAN] Connected – interface {iface_name}", LOG__DEBUG)
        return iface_name

    def disconnect(self) -> None:
        """Disconnect from the PAN network."""
        print_and_log(f"[PAN] Disconnecting from {self.mac}", LOG__DEBUG)
        try:
            self._net.Disconnect()
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"PAN Disconnect failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

    # -- properties ---

    def _get_prop(self, name: str) -> Any:
        try:
            return self._props.Get(_NET_IFACE, name)
        except dbus.exceptions.DBusException:
            return None

    @property
    def connected(self) -> bool:
        val = self._get_prop("Connected")
        return bool(val) if val is not None else False

    @property
    def interface(self) -> Optional[str]:
        val = self._get_prop("Interface")
        return str(val) if val else None

    @property
    def uuid(self) -> Optional[str]:
        val = self._get_prop("UUID")
        return str(val) if val else None

    def status(self) -> Dict[str, Any]:
        """Return a snapshot of all Network1 properties."""
        return {
            "connected": self.connected,
            "interface": self.interface,
            "uuid": self.uuid,
        }


# ---------------------------------------------------------------------------
# NetworkServer1 – server side (per-adapter)
# ---------------------------------------------------------------------------

class NetworkServer:
    """Thin wrapper around ``org.bluez.NetworkServer1`` on the local adapter.

    Usage::

        server = NetworkServer()
        server.register("nap", "pan0")
        # … accept connections …
        server.unregister("nap")
    """

    def __init__(self, adapter: str = ADAPTER_NAME):
        self._adapter = adapter
        self._bus = dbus.SystemBus()
        adapter_path = f"{BLUEZ_NAMESPACE}{adapter}"

        try:
            adapter_obj = self._bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"Adapter {adapter} not found: "
                f"{exc.get_dbus_name()}: {exc.get_dbus_message() or ''}"
            ) from exc

        self._server = dbus.Interface(adapter_obj, _NET_SERVER_IFACE)

    def register(self, role: str = "nap", bridge: str = "pan0") -> None:
        """Register a PAN server for *role*, bridging connections to *bridge*."""
        role = role.lower()
        if role not in _VALID_ROLES:
            raise ValueError(f"Invalid PAN role '{role}'; expected one of {_VALID_ROLES}")
        print_and_log(f"[PAN] Registering server role={role} bridge={bridge}", LOG__DEBUG)
        try:
            self._server.Register(role, bridge)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"PAN server Register failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc

    def unregister(self, role: str = "nap") -> None:
        """Unregister a previously registered PAN server for *role*."""
        role = role.lower()
        print_and_log(f"[PAN] Unregistering server role={role}", LOG__DEBUG)
        try:
            self._server.Unregister(role)
        except dbus.exceptions.DBusException as exc:
            raise RuntimeError(
                f"PAN server Unregister failed: {exc.get_dbus_name()}: "
                f"{exc.get_dbus_message() or ''}"
            ) from exc
