"""Operations layer for Bluetooth Classic PAN (Personal Area Networking).

Wraps :mod:`bleep.dbuslayer.network` with logging, service detection,
and observation-database integration.

Supported PAN roles
-------------------
* ``nap`` – Network Access Point (internet sharing)
* ``panu`` – Personal Area Network User
* ``gn`` – Group Network
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG

try:
    from bleep.core import observations as _obs
except Exception:  # noqa: BLE001
    _obs = None

from bleep.dbuslayer.network import (
    NetworkClient,
    NetworkServer,
    NetworkMonitor,
    normalize_pan_role,
    pan_role_uuid,
)
from bleep.core.errors import (
    BLEEPError,
    NotSupportedError,
    ProfileUnavailableError,
    InvalidArgumentError,
)

from bleep.bt_ref.constants import (
    ADAPTER_NAME,
    ADAPTER_INTERFACE,
    BLUEZ_SERVICE_NAME,
    DBUS_OM_IFACE,
    DEVICE_INTERFACE,
    NETWORK_INTERFACE,
    NETWORK_SERVER_INTERFACE,
    PAN_PANU_UUID,
    PAN_NAP_UUID,
    PAN_GN_UUID,
)

_PAN_SHORTS = {"0x1115", "0x1116", "0x1117", "1115", "1116", "1117"}

# Full 128-bit PAN role UUID (upper-case) → human-readable role label.
_PAN_UUID_ROLE = {
    PAN_PANU_UUID.upper(): "PANU",
    PAN_NAP_UUID.upper(): "NAP",
    PAN_GN_UUID.upper(): "GN",
}


def detect_pan_service(service_map: Optional[Dict[str, int]]) -> bool:
    """Return True if the service map contains a PAN entry (PANU/NAP/GN)."""
    if not service_map:
        return False
    for key in service_map:
        low = key.lower()
        if any(s in low for s in _PAN_SHORTS) or "network" in low or "pan" in low:
            return True
    return False


# ---------------------------------------------------------------------------
# Connect-path helpers (bond/trust resolution + profile-connect fallback)
# ---------------------------------------------------------------------------

def _classic_device(mac_address: str, adapter: str):
    """Return a classic device wrapper, or ``None`` if it cannot be built.

    Lazily imported to avoid a hard dependency (and any import cycle) on the
    device layer for the pure server-side operations.
    """
    try:
        from bleep.dbuslayer.device_classic import (
            system_dbus__bluez_device__classic,
        )
        return system_dbus__bluez_device__classic(mac_address, adapter)
    except Exception as exc:  # noqa: BLE001 – precheck must never be fatal
        print_and_log(
            f"[PAN] Could not build device wrapper for {mac_address}: {exc}",
            LOG__DEBUG,
        )
        return None


def _device_uuids(device) -> List[str]:
    """Best-effort read of a classic device's advertised service UUIDs."""
    if device is None:
        return []
    try:
        uuids = device._props_iface.Get("org.bluez.Device1", "UUIDs")  # noqa: SLF001
        return [str(u) for u in uuids]
    except Exception:  # noqa: BLE001
        return []


def _precheck_pan_target(
    mac_address: str,
    role: str,
    *,
    adapter: str,
    ensure_trusted: bool = False,
) -> None:
    """Resolve bond/trust/SDP state before a PAN connect (detect-and-instruct).

    This is *advisory*: it emits actionable warnings but never raises, so the
    authoritative connect attempt still surfaces the real BlueZ error. It only
    mutates device state (Trusted) when *ensure_trusted* is explicitly set.
    """
    device = _classic_device(mac_address, adapter)
    if device is None:
        return

    try:
        if not device.is_paired():
            print_and_log(
                f"[PAN] {mac_address} is not paired; PAN connect will likely "
                f"fail. Pair first (e.g. bluetoothctl pair {mac_address}).",
                LOG__GENERAL,
            )
    except BLEEPError as exc:
        print_and_log(f"[PAN] Could not read Paired for {mac_address}: {exc}", LOG__DEBUG)

    if ensure_trusted:
        try:
            if not device.is_trusted():
                device.set_trusted(True)
                print_and_log(f"[PAN] Marked {mac_address} as trusted", LOG__GENERAL)
        except BLEEPError as exc:
            print_and_log(f"[PAN] Could not set Trusted for {mac_address}: {exc}", LOG__DEBUG)

    uuids = _device_uuids(device)
    if uuids and not detect_pan_service({u: 1 for u in uuids}):
        print_and_log(
            f"[PAN] {mac_address} does not advertise a PAN service (PANU/NAP/GN) "
            f"in its cached SDP record; the {role.upper()} connect may return "
            f"NotSupported. A fresh SDP browse (classic-connect / sdp) may help.",
            LOG__GENERAL,
        )


def _connect_via_profile(
    mac_address: str,
    role: str,
    *,
    adapter: str,
    client: NetworkClient,
    timeout: float = 4.0,
) -> str:
    """Fallback path: connect the PAN profile via ``Device1.ConnectProfile``.

    Some stacks reject the bare ``Network1.Connect`` with ``NotSupported`` until
    the profile has been probed. ``ConnectProfile`` drives BlueZ's internal SDP
    probe + profile registration, after which ``Network1`` typically reports the
    interface. Returns the local interface name.
    """
    device = _classic_device(mac_address, adapter)
    if device is None:
        raise ProfileUnavailableError(
            mac_address, "cannot access Device1 for ConnectProfile fallback"
        )

    uuid = pan_role_uuid(role)
    print_and_log(
        f"[PAN] Network1.Connect unsupported; retrying via "
        f"Device1.ConnectProfile({uuid})",
        LOG__GENERAL,
    )
    device.connect_profile(uuid)

    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.status()
        if snap.get("connected") and snap.get("interface"):
            return str(snap["interface"])
        time.sleep(0.25)

    raise ProfileUnavailableError(
        mac_address,
        f"ConnectProfile({uuid}) completed but Network1 did not report a "
        f"connected interface for role {role.upper()}",
    )


# ---------------------------------------------------------------------------
# Client operations (Network1)
# ---------------------------------------------------------------------------

def connect(
    mac_address: str,
    role: str = "nap",
    *,
    adapter: str = ADAPTER_NAME,
    resolve: bool = True,
    ensure_trusted: bool = False,
    profile_fallback: bool = True,
) -> str:
    """Connect to a remote PAN device.

    Returns the local network interface name (e.g. ``bnep0``).

    Parameters
    ----------
    role
        ``panu``/``nap``/``gn`` or a full PAN role UUID.
    resolve
        When True (default), run an advisory bond/trust/SDP precheck that emits
        actionable warnings before attempting the connect.
    ensure_trusted
        When True, mark the device Trusted during the precheck (persistent
        state mutation; opt-in).
    profile_fallback
        When True (default), fall back to ``Device1.ConnectProfile`` if the
        direct ``Network1.Connect`` reports ``NotSupported``.
    """
    mac_address = mac_address.strip().upper()
    role = normalize_pan_role(role)
    print_and_log(f"[PAN] Connecting to {mac_address} as {role}", LOG__GENERAL)

    if resolve:
        _precheck_pan_target(
            mac_address, role, adapter=adapter, ensure_trusted=ensure_trusted
        )

    client = NetworkClient(mac_address, adapter=adapter)
    try:
        iface = client.connect(role)
    except NotSupportedError:
        if not profile_fallback:
            raise
        iface = _connect_via_profile(
            mac_address, role, adapter=adapter, client=client
        )
    print_and_log(f"[PAN] Connected – interface {iface}", LOG__GENERAL)

    if _obs:
        try:
            _obs.upsert_pan_access(mac_address, role, "connect", iface)
        except Exception:
            pass

    return iface


def disconnect(
    mac_address: str,
    *,
    adapter: str = ADAPTER_NAME,
) -> None:
    """Disconnect from a remote PAN device."""
    mac_address = mac_address.strip().upper()
    print_and_log(f"[PAN] Disconnecting from {mac_address}", LOG__GENERAL)
    client = NetworkClient(mac_address, adapter=adapter)
    client.disconnect()
    print_and_log(f"[PAN] Disconnected from {mac_address}", LOG__GENERAL)

    if _obs:
        try:
            _obs.upsert_pan_access(mac_address, "", "disconnect")
        except Exception:
            pass


def status(
    mac_address: str,
    *,
    adapter: str = ADAPTER_NAME,
) -> Dict[str, Any]:
    """Return the current Network1 property snapshot for a device."""
    mac_address = mac_address.strip().upper()
    client = NetworkClient(mac_address, adapter=adapter)
    return client.status()


def monitor(
    mac_address: str,
    *,
    adapter: str = ADAPTER_NAME,
    timeout: Optional[float] = None,
    on_change: Optional[Any] = None,
) -> Dict[str, Any]:
    """Stream live ``Network1`` state for a device until Ctrl-C or *timeout* (E5).

    Event-driven via the ``PropertiesChanged`` signal (no polling). Each change
    to ``Connected``/``Interface``/``UUID`` invokes *on_change(state, changed)*
    and is persisted through the observation DB. Returns the final merged state.
    """
    mac_address = mac_address.strip().upper()

    def _sink(state: Dict[str, Any], changed: Dict[str, Any]) -> None:
        if _obs and ("connected" in changed or "interface" in changed):
            try:
                action = "connect" if state.get("connected") else "disconnect"
                _obs.upsert_pan_access(
                    mac_address, "", action, state.get("interface") or ""
                )
            except Exception:  # noqa: BLE001
                pass
        if on_change:
            on_change(state, changed)

    print_and_log(f"[PAN] Monitoring Network1 for {mac_address}", LOG__GENERAL)
    mon = NetworkMonitor(mac_address, adapter=adapter, on_change=_sink)
    return mon.run(timeout=timeout)


# ---------------------------------------------------------------------------
# Server operations (NetworkServer1)
# ---------------------------------------------------------------------------

def register_server(
    role: str = "nap",
    bridge: str = "pan0",
    *,
    adapter: str = ADAPTER_NAME,
) -> None:
    """Register a PAN server so remote devices can connect."""
    role = normalize_pan_role(role)
    print_and_log(f"[PAN] Registering server role={role} bridge={bridge}", LOG__GENERAL)
    server = NetworkServer(adapter=adapter)
    server.register(role, bridge)
    print_and_log(f"[PAN] Server registered (role={role}, bridge={bridge})", LOG__GENERAL)


def unregister_server(
    role: str = "nap",
    *,
    adapter: str = ADAPTER_NAME,
) -> None:
    """Unregister a previously registered PAN server."""
    role = normalize_pan_role(role)
    print_and_log(f"[PAN] Unregistering server role={role}", LOG__GENERAL)
    server = NetworkServer(adapter=adapter)
    server.unregister(role)
    print_and_log(f"[PAN] Server unregistered (role={role})", LOG__GENERAL)


# All PAN roles that BlueZ's NetworkServer1 can host, used by "serve-all".
PAN_SERVER_ROLES = ("nap", "gn", "panu")


# Canonical PAN "server" verbs shared by both surfaces so their vocabulary can
# never drift (CDU-M1.5): the CLI subcommands ``classic-pan server-reg`` /
# ``server-unreg`` and the debug-shell ``cpan server-reg`` / ``server-unreg``
# (which also accepts the one retained two-token alias ``cpan server register`` /
# ``server unregister``). Maps every accepted spelling to its canonical
# ``NetworkServer1`` action.
PAN_SERVER_VERBS = {
    "server-reg": "register",
    "server-unreg": "unregister",
}


def resolve_pan_server_verb(token: str):
    """Return the canonical PAN server action for a CLI/debug verb spelling.

    ``server-reg`` → ``"register"``; ``server-unreg`` → ``"unregister"``.
    Returns ``None`` when *token* is not a PAN server verb.
    """
    return PAN_SERVER_VERBS.get(token)


def _normalize_role_list(roles: Iterable[str]) -> List[str]:
    """Normalize + de-duplicate a role list (preserving order)."""
    norm: List[str] = []
    for role in roles:
        canon = normalize_pan_role(role)
        if canon not in norm:
            norm.append(canon)
    if not norm:
        raise InvalidArgumentError("role", "no PAN roles given")
    return norm


def register_servers(
    roles: Iterable[str],
    bridge: str = "pan0",
    *,
    adapter: str = ADAPTER_NAME,
) -> NetworkServer:
    """Register one or more PAN roles on a single :class:`NetworkServer`.

    Returns the ``NetworkServer`` instance holding every registration so the
    caller can keep it alive and later call :meth:`NetworkServer.unregister_all`
    for guaranteed teardown. If any role fails mid-list, the roles already
    registered by this call are rolled back before the error propagates, so a
    partial failure never strands a registered role.
    """
    norm = _normalize_role_list(roles)
    server = NetworkServer(adapter=adapter)
    try:
        for role in norm:
            server.register(role, bridge)
            print_and_log(
                f"[PAN] Server registered (role={role}, bridge={bridge})",
                LOG__GENERAL,
            )
    except Exception:
        rollback = server.unregister_all()
        if rollback:
            print_and_log(
                f"[PAN] Rolled back partial registration: {rollback}", LOG__GENERAL
            )
        raise
    return server


def unregister_servers(
    roles: Iterable[str],
    *,
    adapter: str = ADAPTER_NAME,
) -> Dict[str, Optional[str]]:
    """Best-effort unregister of several PAN roles (out-of-process teardown).

    Unlike :meth:`NetworkServer.unregister_all` (which only knows roles it
    registered in-process), this targets an explicit role list — useful for
    ``unserve`` from a fresh process. Each role is attempted independently;
    returns ``{role: error}`` (``None`` on success). A role that was not
    registered simply reports its D-Bus error and does not abort the others.
    """
    norm = _normalize_role_list(roles)
    server = NetworkServer(adapter=adapter)
    results: Dict[str, Optional[str]] = {}
    for role in norm:
        try:
            server.unregister(role)
            results[role] = None
            print_and_log(f"[PAN] Server unregistered (role={role})", LOG__GENERAL)
        except Exception as exc:  # noqa: BLE001 – continue with remaining roles
            results[role] = str(exc)
            print_and_log(
                f"[PAN] unserve: role={role} not unregistered: {exc}", LOG__GENERAL
            )
    return results


# ---------------------------------------------------------------------------
# Server-side authorization observer (Agent) — E7
# ---------------------------------------------------------------------------

# BNEP protocol UUID that BlueZ authorizes for inbound PAN connections
# (profiles/network/server.c → btd_request_authorization with BNEP_SVC_UUID).
BNEP_SVC_UUID = "0000000f-0000-1000-8000-00805f9b34fb"


def _authorize_label(uuid: str) -> str:
    """Human label for an authorized service UUID (PAN role / BNEP / other)."""
    up = str(uuid).upper()
    if up == BNEP_SVC_UUID.upper():
        return "BNEP"
    return _PAN_UUID_ROLE.get(up, str(uuid))


def register_pan_agent(*, auto_accept: bool = True, on_authorize=None):
    """Register a default BlueZ agent to observe inbound BNEP authorizations (E7).

    While hosting a NAP/GN, BlueZ calls the *default* agent's ``AuthorizeService``
    for each inbound BNEP client (``server.c`` ``btd_request_authorization``).
    This registers an :class:`~bleep.dbuslayer.agent.EnhancedAgent` whose
    ``authorize_service`` callback logs the connecting device + service and then
    accepts (``auto_accept=True``) or rejects the request.

    Parameters
    ----------
    auto_accept
        When True (default), inbound BNEP services are authorized after logging;
        when False they are rejected (observe-only, deny inbound).
    on_authorize
        Optional ``callback(device_info, uuid, label, accepted)`` invoked for
        each authorization, for callers that want to record/track clients.

    Returns
    -------
    tuple
        ``(agent, bus)`` — call ``agent.unregister()`` on teardown. A GLib
        ``MainLoop`` must be iterating for the agent to receive D-Bus calls.
    """
    import dbus
    import dbus.mainloop.glib

    from bleep.dbuslayer.agent import EnhancedAgent

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    def _authorize(device_info: str, uuid: str) -> bool:
        label = _authorize_label(uuid)
        decision = "authorized" if auto_accept else "rejected"
        print_and_log(
            f"[PAN][serve] inbound BNEP client {device_info} service={label} "
            f"({uuid}) → {decision}",
            LOG__GENERAL,
        )
        if on_authorize:
            try:
                on_authorize(device_info, uuid, label, auto_accept)
            except Exception:  # noqa: BLE001 – observer must not break auth
                pass
        return bool(auto_accept)

    agent = EnhancedAgent(bus, auto_accept=auto_accept)
    agent.set_callback("authorize_service", _authorize)
    agent.register(capabilities="NoInputNoOutput", default=True)
    print_and_log(
        f"[PAN][serve] authorization observer registered "
        f"(auto_accept={auto_accept})",
        LOG__GENERAL,
    )
    return agent, bus


# ---------------------------------------------------------------------------
# Enumeration (network capability discovery over ObjectManager)
# ---------------------------------------------------------------------------

def network_roles_from_uuids(uuids: Optional[List[str]]) -> List[str]:
    """Return the PAN role labels (``PANU``/``NAP``/``GN``) present in *uuids*.

    Accepts a list of 128-bit UUID strings (any case) as found in a device or
    adapter ``UUIDs`` property; unknown UUIDs are ignored. Order is preserved
    and de-duplicated.
    """
    roles: List[str] = []
    for uuid in uuids or []:
        label = _PAN_UUID_ROLE.get(str(uuid).upper())
        if label and label not in roles:
            roles.append(label)
    return roles


def _fetch_managed_objects() -> Dict[str, Dict[str, Any]]:
    """Best-effort single ``GetManagedObjects`` fetch. Empty dict on any error."""
    try:
        import dbus  # local import keeps the ops layer import-light

        bus = dbus.SystemBus()
        om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
        return dict(om.GetManagedObjects())
    except Exception as exc:  # noqa: BLE001 – enumeration must never raise
        print_and_log(f"[PAN] GetManagedObjects failed: {exc}", LOG__DEBUG)
        return {}


def find_network_servers(
    managed_objects: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    adapter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Enumerate adapters and their PAN ``NetworkServer1`` capability.

    Pass a pre-fetched ``GetManagedObjects`` dict as *managed_objects* to avoid
    an extra D-Bus round-trip (e.g. in survey mode); otherwise one is fetched.
    Never raises — returns ``[]`` on error.
    """
    mo = managed_objects if managed_objects is not None else _fetch_managed_objects()
    servers: List[Dict[str, Any]] = []
    for path, ifaces in mo.items():
        if ADAPTER_INTERFACE not in ifaces:
            continue
        if adapter and not str(path).endswith(f"/{adapter}"):
            continue
        props = ifaces.get(ADAPTER_INTERFACE, {})
        servers.append({
            "path": str(path),
            "name": str(props.get("Name") or "Unknown"),
            "address": str(props.get("Address") or "Unknown"),
            "powered": bool(props.get("Powered", False)),
            "has_networkserver": NETWORK_SERVER_INTERFACE in ifaces,
            "network_uuids": network_roles_from_uuids(props.get("UUIDs", [])),
        })
    return servers


def find_network_devices(
    managed_objects: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    adapter: Optional[str] = None,
    only_capable: bool = True,
) -> List[Dict[str, Any]]:
    """Enumerate devices exposing PAN capability (``Network1`` or PAN UUIDs).

    Uses the pre-fetched ``Network1`` properties already present in the
    ObjectManager snapshot for status — no per-device D-Bus calls. When
    *only_capable* is True (default), non-network devices are omitted.
    Never raises — returns ``[]`` on error.
    """
    mo = managed_objects if managed_objects is not None else _fetch_managed_objects()
    devices: List[Dict[str, Any]] = []
    for path, ifaces in mo.items():
        if DEVICE_INTERFACE not in ifaces:
            continue
        if adapter and not str(path).startswith(f"/org/bluez/{adapter}/"):
            continue
        props = ifaces.get(DEVICE_INTERFACE, {})
        has_iface = NETWORK_INTERFACE in ifaces
        roles = network_roles_from_uuids(props.get("UUIDs", []))
        capable = has_iface or bool(roles)
        if only_capable and not capable:
            continue
        entry: Dict[str, Any] = {
            "path": str(path),
            "address": str(props.get("Address") or "Unknown"),
            "name": str(props.get("Name") or props.get("Alias") or "Unknown"),
            "has_network_interface": has_iface,
            "network_uuids": roles,
            "has_network_capability": capable,
        }
        if has_iface:
            net = ifaces.get(NETWORK_INTERFACE, {})
            entry["network_status"] = {
                "connected": bool(net.get("Connected", False)),
                "interface": str(net["Interface"]) if net.get("Interface") else None,
                "uuid": str(net["UUID"]) if net.get("UUID") else None,
            }
        devices.append(entry)
    return devices
