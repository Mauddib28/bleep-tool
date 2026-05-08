"""Shared pairing and Classic-connect helpers for CLI, debug mode, and ops-layer.

Consolidates device-state checks, stale-bond removal, agent registration,
device-path resolution, and SDP+RFCOMM Classic connection so that each
caller remains thin and there is a single source of truth.
"""

from __future__ import annotations

import socket
import time
from typing import Optional

import dbus

from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    DEVICE_INTERFACE,
    DBUS_PROPERTIES,
)
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG, LOG__AGENT


# ---------------------------------------------------------------------
# Device-path resolution
# ---------------------------------------------------------------------

def find_device_path(mac: str) -> Optional[str]:
    """Resolve a MAC address to its BlueZ D-Bus object path.

    Walks ``GetManagedObjects`` on the system bus.  Returns ``None`` when
    the device has not been discovered yet.
    """
    mac = mac.strip().upper()
    try:
        bus = dbus.SystemBus()
        om = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, "/"),
            "org.freedesktop.DBus.ObjectManager",
        )
        for path, ifaces in om.GetManagedObjects().items():
            dev = ifaces.get(DEVICE_INTERFACE)
            if dev and str(dev.get("Address", "")).upper() == mac:
                return str(path)
    except dbus.exceptions.DBusException:
        pass
    return None


def resolve_device_for_pair(mac: str, adapter) -> Optional[str]:
    """Discover a device and return its D-Bus path, running a scan if needed.

    Parameters
    ----------
    mac : str
        Target Bluetooth MAC address.
    adapter
        An initialised ``system_dbus__bluez_adapter`` instance.

    Returns
    -------
    str or None
        D-Bus object path, or ``None`` if the device cannot be found.
    """
    device_path = find_device_path(mac)
    if device_path is None:
        print_and_log(
            f"[*] Device {mac} not in BlueZ object tree – running 15 s discovery…",
            LOG__GENERAL,
        )
        adapter.set_discovery_filter({"Transport": "auto"})
        adapter.run_scan__timed(duration=15)
        device_path = find_device_path(mac)
    return device_path


# ---------------------------------------------------------------------
# Pair-status checking
# ---------------------------------------------------------------------

def check_pair_status(mac: str, transport: str = "auto") -> dict:
    """Query the live pairing / trust / connection state of a device.

    Returns a dict with keys ``paired``, ``trusted``, ``connected``,
    ``fully_bonded``, and ``found`` (False when BlueZ has never seen the
    device).
    """
    from bleep.core.preflight import check_device_state

    state = check_device_state(mac, transport=transport)
    found = state.paired or state.trusted or state.connected
    return {
        "paired": state.paired,
        "trusted": state.trusted,
        "connected": state.connected,
        "fully_bonded": state.fully_bonded,
        "found": found,
    }


def report_pair_status(mac: str, status: dict) -> None:
    """Print a human-readable summary of a device's pairing state."""
    if not status["found"]:
        print_and_log(f"[*] Device {mac}: not previously seen by BlueZ", LOG__GENERAL)
        return

    flags = []
    if status["paired"]:
        flags.append("paired")
    if status["trusted"]:
        flags.append("trusted")
    if status["connected"]:
        flags.append("connected")

    summary = ", ".join(flags) if flags else "discovered but not paired"
    print_and_log(f"[*] Device {mac}: {summary}", LOG__GENERAL)

    if status["fully_bonded"]:
        print_and_log(
            f"[+] Device {mac} is fully bonded (connected + paired + trusted)",
            LOG__GENERAL,
        )


# ---------------------------------------------------------------------
# Stale-bond removal
# ---------------------------------------------------------------------

def remove_stale_bond(
    mac: str,
    device_path: str,
    adapter,
    *,
    rediscover: bool = True,
    discover_duration: int = 15,
    bus: Optional[dbus.SystemBus] = None,
) -> Optional[str]:
    """Remove an existing pairing and optionally re-discover the device.

    Parameters
    ----------
    mac : str
        Target Bluetooth MAC address.
    device_path : str
        Current D-Bus object path for the device.
    adapter
        An initialised ``system_dbus__bluez_adapter`` (or compatible)
        instance that exposes ``set_discovery_filter`` and
        ``run_scan__timed``.
    rediscover : bool
        If True (default), run a scan after bond removal and return the
        new device path.
    discover_duration : int
        Duration of the re-discovery scan in seconds.
    bus : dbus.SystemBus, optional
        Reuse an existing bus connection.  Created internally when None.

    Returns
    -------
    str or None
        The (possibly new) device path after bond removal, or ``None``
        if the device could not be re-discovered.
    """
    if bus is None:
        bus = dbus.SystemBus()

    try:
        dev_props = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, device_path),
            DBUS_PROPERTIES,
        )
        already_paired = bool(dev_props.Get(DEVICE_INTERFACE, "Paired"))
        if not already_paired:
            return device_path

        print_and_log(
            f"[*] Device {mac} already paired – removing stale bond",
            LOG__GENERAL,
        )
        adapter_path = getattr(adapter, "adapter_path", "/org/bluez/hci0")
        adapter_obj = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
            "org.bluez.Adapter1",
        )
        adapter_obj.RemoveDevice(device_path)
        time.sleep(0.5)

        if not rediscover:
            return None

        print_and_log(
            f"[*] Re-discovering {mac} after bond removal ({discover_duration} s)…",
            LOG__GENERAL,
        )
        adapter.set_discovery_filter({"Transport": "auto"})
        adapter.run_scan__timed(duration=discover_duration)
        return find_device_path(mac)

    except dbus.exceptions.DBusException as exc:
        print_and_log(f"[*] Bond removal note: {exc}", LOG__DEBUG)
    return device_path


# ---------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------

def register_pair_agent(io_handler, cap: str) -> bool:
    """Clear any existing default agent and register a fresh pairing agent.

    Parameters
    ----------
    io_handler
        An ``AgentIOHandler`` implementation (``CliIOHandler``,
        ``AutoAcceptIOHandler``, etc.).
    cap : str
        BlueZ capability string, e.g. ``"KeyboardDisplay"``.

    Returns
    -------
    bool
        True on success.
    """
    from bleep.dbuslayer.agent import (
        ensure_default_pairing_agent,
        clear_default_pairing_agent,
    )
    import bleep.dbuslayer.agent as _agent_mod

    existing = getattr(_agent_mod, "_DEFAULT_AGENT", None)
    if existing is not None and existing.is_registered():
        try:
            clear_default_pairing_agent()
        except Exception:
            pass

    try:
        ensure_default_pairing_agent(
            capabilities=cap, auto_accept=True, io_handler=io_handler,
        )
        return True
    except Exception as exc:
        print_and_log(f"[-] Agent registration failed: {exc}", LOG__GENERAL)
        return False


# ---------------------------------------------------------------------
# Classic connection via SDP + raw RFCOMM (bypasses Device1.Connect)
# ---------------------------------------------------------------------

def _svc_map_has_audio_uuid(svc_map: dict) -> bool:
    """Return True when *svc_map* advertises a known audio-profile UUID.

    Accepts entries whose ``uuid`` field is either a full 128-bit UUID
    string (``0000110b-0000-1000-8000-00805f9b34fb``) or the short
    ``0x110b`` form produced by ``bleep.ble_ops.classic.sdp`` when only
    a 16-bit UUID is present in the SDP record.  Normalises both forms
    against ``AUDIO_SERVICE_UUIDS`` from ``bleep.bt_ref.constants``.
    """
    from bleep.bt_ref.constants import AUDIO_SERVICE_UUIDS

    for entry in svc_map.values():
        if not isinstance(entry, dict):
            continue
        u = (entry.get("uuid") or "").lower()
        if not u:
            continue
        if u in AUDIO_SERVICE_UUIDS:
            return True
        if u.startswith("0x") and len(u) == 6:
            full = f"0000{u[2:]}-0000-1000-8000-00805f9b34fb"
            if full in AUDIO_SERVICE_UUIDS:
                return True
    return False


def _activate_bluez_profiles(device, mac: str) -> bool:
    """Non-fatal best-effort ``Device1.Connect()`` to activate BlueZ profiles.

    After a raw RFCOMM bring-up, the device's ACL link is up but BlueZ
    has not attached any profile handlers.  For audio-capable devices
    this prevents a BlueZ ``bluez_card.*`` from being created and makes
    ``bleep audio-profiles`` / ``amusica status`` appear to see "no
    card" until something else triggers profile activation.

    Calling :py:meth:`system_dbus__bluez_device__classic.connect` is
    idempotent when the ACL is already up and causes BlueZ to iterate
    its registered profile handlers (A2DP, HFP, HSP, AVRCP, …).  Any
    failure is logged at DEBUG and swallowed so that RFCOMM bring-up
    remains authoritative.
    """
    try:
        if device.connect():
            print_and_log(
                f"[+] Activated BlueZ profile handlers for {mac}",
                LOG__GENERAL,
            )
            return True
        print_and_log(
            f"[*] BlueZ profile activation returned False for {mac} "
            "(RFCOMM keep-alive already authoritative)",
            LOG__DEBUG,
        )
    except Exception as exc:
        print_and_log(
            f"[*] BlueZ profile activation skipped for {mac}: {exc}",
            LOG__DEBUG,
        )
    return False


def classic_connect_sdp_rfcomm(
    mac: str,
    *,
    channel: Optional[int] = None,
    open_keepalive: bool = True,
    keepalive_timeout: float = 5.0,
    activate_profiles: bool = True,
) -> dict:
    """Connect to a Classic device via SDP discovery and a raw RFCOMM socket.

    ``Device1.Connect()`` only succeeds when BlueZ has a registered profile
    handler for one of the remote device's services.  For devices that
    expose only RFCOMM-based services without a BlueZ profile handler,
    the call fails with ``br-connection-profile-unavailable``.

    This helper takes the proven alternative path:
    1. Run connectionless SDP discovery to enumerate services.
    2. Open a raw RFCOMM socket on the first available channel (or a
       caller-specified *channel*), which implicitly creates the ACL link.
    3. (Opt-in) When *activate_profiles* is True **and** the SDP map
       advertises an audio service UUID (A2DP / HFP / HSP / AVRCP),
       call :py:meth:`system_dbus__bluez_device__classic.connect` as a
       non-fatal step so BlueZ attaches its profile handlers and the
       device appears in ``bleep audio-profiles`` without needing a
       subsequent ``amusica status`` round-trip.

    Parameters
    ----------
    mac : str
        Target Bluetooth MAC address.
    channel : int, optional
        Specific RFCOMM channel to connect.  When ``None`` the first
        channel found via SDP is used.
    open_keepalive : bool
        Open a persistent RFCOMM socket to keep the ACL link alive.
    keepalive_timeout : float
        Timeout in seconds for the RFCOMM socket connection.
    activate_profiles : bool
        When True (default), attempt ``Device1.Connect()`` after the
        RFCOMM bring-up if audio UUIDs are present in SDP.  Failures
        are non-fatal and do not affect the returned ``sock``/``channel``.
        Pass ``False`` from CLI ``--no-profiles`` to preserve the legacy
        RFCOMM-only behaviour.

    Returns
    -------
    dict
        ``device``             – ``system_dbus__bluez_device__classic`` instance
        ``svc_map``            – enriched service-channel map from SDP
        ``sock``               – the keepalive ``socket.socket`` (or ``None``)
        ``channel``            – the RFCOMM channel used (or ``None``)
        ``profiles_activated`` – True when BlueZ profile handlers were
                                 successfully attached via
                                 ``Device1.Connect()``; False otherwise
                                 (including when no audio UUIDs were seen
                                 or *activate_profiles* was False).
    """
    from bleep.dbuslayer.device_classic import (
        system_dbus__bluez_device__classic as _ClassicDevice,
    )
    from bleep.ble_ops.classic.sdp import discover_services_sdp, build_svc_map
    from bleep.ble_ops.classic.connect import classic_rfccomm_open

    mac = mac.strip().upper()
    device = _ClassicDevice(mac)

    svc_map: dict = {}
    try:
        records = discover_services_sdp(mac)
        svc_map = build_svc_map(records)
        rfcomm_count = sum(1 for v in svc_map.values() if v.get("channel") is not None)
        if svc_map:
            print_and_log(
                f"[+] SDP enumeration: {len(svc_map)} service(s) ({rfcomm_count} with RFCOMM)",
                LOG__GENERAL,
            )
    except Exception as exc:
        print_and_log(f"[*] SDP enumeration unavailable: {exc}", LOG__DEBUG)

    sock: Optional[socket.socket] = None
    used_channel: Optional[int] = None

    if open_keepalive:
        if channel is not None:
            candidates = [channel]
        else:
            candidates = []
            for entry in svc_map.values():
                ch = entry.get("channel") if isinstance(entry, dict) else entry
                if ch is not None and ch not in candidates:
                    candidates.append(ch)

        last_err: Optional[Exception] = None
        for ch in candidates:
            try:
                sock = classic_rfccomm_open(mac, ch, timeout=keepalive_timeout)
                used_channel = ch
                print_and_log(
                    f"[+] Keep-alive socket opened on RFCOMM channel {ch}",
                    LOG__GENERAL,
                )
                break
            except Exception as exc:
                print_and_log(
                    f"[*] Keep-alive socket failed (channel {ch}): {exc}",
                    LOG__DEBUG,
                )
                last_err = exc

        if sock is None and candidates and last_err is not None:
            print_and_log(
                f"[*] All {len(candidates)} RFCOMM channel(s) failed — last error: {last_err}",
                LOG__GENERAL,
            )

    profiles_activated = False
    if activate_profiles and _svc_map_has_audio_uuid(svc_map):
        profiles_activated = _activate_bluez_profiles(device, mac)

    return {
        "device": device,
        "svc_map": svc_map,
        "sock": sock,
        "channel": used_channel,
        "profiles_activated": profiles_activated,
    }
