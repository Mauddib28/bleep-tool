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

import time
from typing import Any, Dict, List, Optional

import dbus

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    BLUEZ_NAMESPACE,
    ADAPTER_NAME,
    DBUS_PROPERTIES,
    NETWORK_INTERFACE as _NET_IFACE,
    NETWORK_SERVER_INTERFACE as _NET_SERVER_IFACE,
    PAN_PANU_UUID,
    PAN_NAP_UUID,
    PAN_GN_UUID,
)
from bleep.bt_ref.utils import device_address_to_path
from bleep.core.log import print_and_log, LOG__DEBUG
from bleep.core.errors import (
    map_dbus_error,
    ConnectionError as _ConnectionError,
    InvalidArgumentError as _InvalidArgumentError,
)

# Canonical short-name → full 128-bit UUID mapping for the three PAN roles.
# BlueZ's ``Network1.Connect`` / ``NetworkServer1.Register`` accept *both* the
# short strings and the full UUIDs (see ``profiles/network/connection.c``
# ``get_pan_srv_id`` and ``org.bluez.Network.rst``), so we accept both and
# normalise to the short form BlueZ prefers.
_ROLE_UUIDS = {
    "panu": PAN_PANU_UUID,
    "nap": PAN_NAP_UUID,
    "gn": PAN_GN_UUID,
}
_UUID_TO_ROLE = {uuid.upper(): role for role, uuid in _ROLE_UUIDS.items()}

# Retained for backward compatibility with any external importer.
_VALID_ROLES = set(_ROLE_UUIDS)


def normalize_pan_role(role: str) -> str:
    """Return the canonical short PAN role name (``panu``/``nap``/``gn``).

    Accepts either a short role name (case-insensitive) or a full 128-bit PAN
    UUID, matching what BlueZ's ``Network1.Connect`` accepts.

    Raises
    ------
    InvalidArgumentError
        If *role* is neither a known short name nor a PAN role UUID.
    """
    if not role or not str(role).strip():
        raise _InvalidArgumentError("role", "empty PAN role")
    short = str(role).strip().lower()
    if short in _ROLE_UUIDS:
        return short
    full = str(role).strip().upper()
    if full in _UUID_TO_ROLE:
        return _UUID_TO_ROLE[full]
    raise _InvalidArgumentError(
        "role",
        f"invalid PAN role '{role}'; expected one of "
        f"{sorted(_ROLE_UUIDS)} or a PAN role UUID",
    )


def pan_role_uuid(role: str) -> str:
    """Return the full 128-bit UUID for a PAN role (short name or UUID)."""
    return _ROLE_UUIDS[normalize_pan_role(role)]


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
            raise map_dbus_error(exc) from exc

        self._net = dbus.Interface(dev_obj, _NET_IFACE)
        self._props = dbus.Interface(dev_obj, DBUS_PROPERTIES)

    # -- methods ---

    def connect(
        self,
        role: str = "nap",
        *,
        verify: bool = True,
        verify_timeout: float = 2.0,
    ) -> str:
        """Connect as *role* (``panu``, ``nap``, or ``gn``).

        Returns the local network interface name (e.g. ``bnep0``).

        When *verify* is True (default), a post-connect check confirms that the
        BNEP session actually stabilised.  BlueZ may return an interface name
        optimistically before the BNEP handshake completes (see
        ``connection.c:136-232``).  The check is **event-driven** — it waits on
        the ``Network1`` ``PropertiesChanged`` signal for ``Connected`` (G8) up
        to *verify_timeout* seconds — and falls back to a single 0.5 s poll if
        the signal path is unavailable (e.g. no GLib loop).
        """
        role = normalize_pan_role(role)
        print_and_log(f"[PAN] Connecting to {self.mac} as {role}", LOG__DEBUG)
        try:
            iface_name = str(self._net.Connect(role))
        except dbus.exceptions.DBusException as exc:
            raise map_dbus_error(exc) from exc

        if verify and not self._verify_connected(verify_timeout):
            raise _ConnectionError(
                self.mac,
                f"PAN Connect returned interface '{iface_name}' but the "
                f"BNEP session did not persist (Connected=False after "
                f"{verify_timeout:g} s). The remote device may have refused the "
                f"{role.upper()} role or dropped the L2CAP/BNEP connection.",
            )

        print_and_log(f"[PAN] Connected – interface {iface_name}", LOG__DEBUG)
        return iface_name

    def _verify_connected(self, timeout: float) -> bool:
        """Return True once ``Connected`` is True, event-driven with poll fallback.

        Fast-paths when already connected; otherwise waits on the ``Network1``
        ``PropertiesChanged`` signal. Any failure in the signal path degrades
        gracefully to the historical single 0.5 s poll.
        """
        if self.connected:
            return True
        try:
            monitor = NetworkMonitor(self.mac, adapter=self._adapter)
            if monitor.wait_for(lambda st: st.get("connected") is True, timeout):
                return True
        except Exception as exc:  # noqa: BLE001 – fall back to the legacy poll
            print_and_log(
                f"[PAN] event-driven verify unavailable ({exc}); polling", LOG__DEBUG
            )
            time.sleep(0.5)
        return self.connected

    def disconnect(self) -> None:
        """Disconnect from the PAN network."""
        print_and_log(f"[PAN] Disconnecting from {self.mac}", LOG__DEBUG)
        try:
            self._net.Disconnect()
        except dbus.exceptions.DBusException as exc:
            raise map_dbus_error(exc) from exc

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
        """Return an atomic snapshot of all Network1 properties.

        Uses a single ``GetAll`` D-Bus call to avoid race conditions between
        individual property reads.
        """
        try:
            raw = dict(self._props.GetAll(_NET_IFACE))
            return {
                "connected": bool(raw.get("Connected", False)),
                "interface": str(raw["Interface"]) if raw.get("Interface") else None,
                "uuid": str(raw["UUID"]) if raw.get("UUID") else None,
            }
        except dbus.exceptions.DBusException:
            return {
                "connected": self.connected,
                "interface": self.interface,
                "uuid": self.uuid,
            }


# ---------------------------------------------------------------------------
# Network1 – event-driven monitor (PropertiesChanged)
# ---------------------------------------------------------------------------

def _coerce_net_value(key: str, value: Any) -> Any:
    """Coerce a raw D-Bus ``Network1`` property value to a plain Python type."""
    if key == "Connected":
        return bool(value)
    if key in ("Interface", "UUID"):
        return str(value) if value else None
    return value


class NetworkMonitor:
    """Event-driven watcher for ``org.bluez.Network1`` ``PropertiesChanged``.

    Replaces polling for ``Connected``/``Interface``/``UUID`` (gap **G8**).
    The signal-handling core (:meth:`_apply_change`) is pure and unit-testable;
    :meth:`wait_for` and :meth:`run` drive a GLib main loop and are only invoked
    against a live bus.

    Usage::

        mon = NetworkMonitor("AA:BB:CC:DD:EE:FF", on_change=print)
        mon.run(timeout=30)                       # live stream until Ctrl-C/timeout
        ok = mon.wait_for(lambda s: s["connected"], timeout=2.0)
    """

    _PROP_MAP = {"Connected": "connected", "Interface": "interface", "UUID": "uuid"}

    def __init__(
        self,
        mac_address: str,
        *,
        adapter: str = ADAPTER_NAME,
        on_change: Optional[Any] = None,
    ):
        self.mac = mac_address.strip().upper()
        self._adapter = adapter
        self._on_change = on_change
        self.state: Dict[str, Any] = {"connected": None, "interface": None, "uuid": None}

        adapter_path = f"{BLUEZ_NAMESPACE}{adapter}"
        self._device_path = device_address_to_path(self.mac, adapter_path)
        self._bus: Optional[Any] = None
        self._match = None
        self._loop = None

    # -- pure, testable core -------------------------------------------------

    def _apply_change(self, interface: str, changed: Dict[str, Any],
                      invalidated: List[str]) -> bool:
        """Merge a PropertiesChanged payload into ``self.state``.

        Returns True if any tracked ``Network1`` property actually changed.
        Ignores payloads for other interfaces.
        """
        if str(interface) != _NET_IFACE:
            return False
        touched = False
        for raw_key, state_key in self._PROP_MAP.items():
            if raw_key in changed:
                new_val = _coerce_net_value(raw_key, changed[raw_key])
                if self.state.get(state_key) != new_val:
                    self.state[state_key] = new_val
                    touched = True
            if raw_key in (invalidated or []):
                if self.state.get(state_key) is not None:
                    self.state[state_key] = None
                    touched = True
        return touched

    def _handle_signal(self, interface, changed, invalidated):
        changed_py = {str(k): _coerce_net_value(str(k), v) for k, v in dict(changed).items()}
        if self._apply_change(str(interface), dict(changed), list(invalidated)):
            print_and_log(
                f"[PAN][monitor] {self.mac} {interface} changed: {changed_py} "
                f"→ state={self.state}",
                LOG__DEBUG,
            )
            if self._on_change:
                try:
                    self._on_change(dict(self.state), changed_py)
                except Exception as exc:  # noqa: BLE001 – callback must not kill loop
                    print_and_log(f"[PAN][monitor] on_change error: {exc}", LOG__DEBUG)
            self._maybe_quit()

    # -- live-bus machinery --------------------------------------------------

    def prime(self) -> Dict[str, Any]:
        """Populate ``self.state`` from a one-shot ``GetAll`` snapshot."""
        bus = self._ensure_bus()
        try:
            props = dbus.Interface(
                bus.get_object(BLUEZ_SERVICE_NAME, self._device_path), DBUS_PROPERTIES
            )
            raw = dict(props.GetAll(_NET_IFACE))
        except dbus.exceptions.DBusException:
            return dict(self.state)
        for raw_key, state_key in self._PROP_MAP.items():
            if raw_key in raw:
                self.state[state_key] = _coerce_net_value(raw_key, raw[raw_key])
        return dict(self.state)

    def _ensure_bus(self):
        if self._bus is None:
            import dbus.mainloop.glib

            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._bus = dbus.SystemBus()
        return self._bus

    def _subscribe(self):
        bus = self._ensure_bus()
        self._match = bus.add_signal_receiver(
            self._handle_signal,
            dbus_interface=DBUS_PROPERTIES,
            signal_name="PropertiesChanged",
            arg0=_NET_IFACE,
            path=self._device_path,
        )

    def _unsubscribe(self):
        if self._match is not None:
            try:
                self._match.remove()
            except Exception:  # noqa: BLE001
                pass
            self._match = None

    _predicate = None

    def _maybe_quit(self):
        if self._loop is not None and self._predicate is not None:
            try:
                if self._predicate(dict(self.state)):
                    self._loop.quit()
            except Exception:  # noqa: BLE001
                pass

    def wait_for(self, predicate, timeout: float) -> bool:
        """Block until ``predicate(state)`` is True or *timeout* elapses.

        Primes from a ``GetAll`` snapshot first (so an already-satisfied state
        returns immediately without running a loop), then waits on live signals.
        """
        self.prime()
        if predicate(dict(self.state)):
            return True

        from gi.repository import GLib

        self._predicate = predicate
        self._subscribe()
        self._loop = GLib.MainLoop()
        timed_out = {"v": False}

        def _on_timeout():
            timed_out["v"] = True
            self._loop.quit()
            return False

        GLib.timeout_add(int(max(0.0, timeout) * 1000), _on_timeout)
        try:
            self._loop.run()
        finally:
            self._unsubscribe()
            self._loop = None
            self._predicate = None
        return not timed_out["v"] and bool(predicate(dict(self.state)))

    def run(self, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Stream live changes (invoking ``on_change``) until Ctrl-C or timeout.

        Returns the final merged state. Intended for the ``classic-pan monitor``
        command; installs a SIGINT handler that cleanly quits the loop.
        """
        import signal as _signal
        from gi.repository import GLib

        self.prime()
        if self._on_change:
            self._on_change(dict(self.state), dict(self.state))
        self._subscribe()
        self._loop = GLib.MainLoop()
        try:
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, _signal.SIGINT, self._loop.quit)
        except Exception:  # noqa: BLE001 – SIGINT integration is best-effort
            pass
        if timeout is not None:
            GLib.timeout_add(int(max(0.0, timeout) * 1000), lambda: (self._loop.quit(), False)[1])
        try:
            self._loop.run()
        except KeyboardInterrupt:
            pass
        finally:
            self._unsubscribe()
            self._loop = None
        return dict(self.state)


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
            raise map_dbus_error(exc) from exc

        self._server = dbus.Interface(adapter_obj, _NET_SERVER_IFACE)
        # role → bridge for every role this instance has successfully registered,
        # so a single owner can host several PAN roles and tear them all down.
        self._registered: Dict[str, str] = {}

    @property
    def registered_roles(self) -> Dict[str, str]:
        """Return a copy of the ``{role: bridge}`` map registered by this instance."""
        return dict(self._registered)

    def register(self, role: str = "nap", bridge: str = "pan0") -> None:
        """Register a PAN server for *role*, bridging connections to *bridge*.

        On success the ``role → bridge`` pairing is tracked so that
        :meth:`unregister_all` can guarantee teardown of every role this
        instance registered.
        """
        role = normalize_pan_role(role)
        print_and_log(f"[PAN] Registering server role={role} bridge={bridge}", LOG__DEBUG)
        try:
            self._server.Register(role, bridge)
        except dbus.exceptions.DBusException as exc:
            raise map_dbus_error(exc) from exc
        self._registered[role] = bridge

    def unregister(self, role: str = "nap") -> None:
        """Unregister a previously registered PAN server for *role*."""
        role = normalize_pan_role(role)
        print_and_log(f"[PAN] Unregistering server role={role}", LOG__DEBUG)
        try:
            self._server.Unregister(role)
        except dbus.exceptions.DBusException as exc:
            raise map_dbus_error(exc) from exc
        finally:
            self._registered.pop(role, None)

    def unregister_all(self) -> Dict[str, Optional[str]]:
        """Unregister every role this instance registered (best-effort teardown).

        Attempts each role even if an earlier one fails, so a partial failure
        never strands a still-registered role. Returns a ``{role: error}`` map
        where ``error`` is ``None`` on success or the string form of the failure.
        """
        results: Dict[str, Optional[str]] = {}
        for role in list(self._registered):
            try:
                self.unregister(role)
                results[role] = None
            except Exception as exc:  # noqa: BLE001 – teardown must continue
                results[role] = str(exc)
                print_and_log(
                    f"[PAN] unregister_all: failed to unregister role={role}: {exc}",
                    LOG__DEBUG,
                )
        return results
