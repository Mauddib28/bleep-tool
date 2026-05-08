"""High-level audio streaming manager for Bluetooth media transports.

This module orchestrates MediaTransport acquisition, codec encoding,
and audio streaming. Uses D-Bus for transport management and delegates
codec operations to audio_codec.py.

MediaEndpoint ↔ MediaTransport UUID relationship
-------------------------------------------------
A MediaEndpoint1 interface on D-Bus represents the **remote** device's
advertised role (e.g. A2DP Sink = "this device can receive audio").
The associated MediaTransport1 interface represents the **local** host's
complementary role (e.g. A2DP Source = "the host sends audio through
this file descriptor").

BlueZ places the transport as a child of the remote endpoint in the
D-Bus object hierarchy:

    /org/bluez/hci0/dev_XX_XX/sep1       ← MediaEndpoint1 (remote Sink)
    /org/bluez/hci0/dev_XX_XX/sep1/fd0   ← MediaTransport1 (local Source)

Transport discovery in ``_get_transport()`` uses this path hierarchy as
the primary association mechanism, with complement UUID matching as a
fallback.  This approach is UUID-agnostic and will not reject transports
with unexpected UUIDs.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import time

import dbus

from bleep.dbuslayer.media import (
    get_managed_objects,
    MediaTransport,
    BleepMediaEndpoint,
)
from bleep.ble_ops.audio.audio_codec import AudioCodecEncoder, AudioCodecDecoder
from bleep.bt_ref.constants import (
    A2DP_SINK_UUID,
    A2DP_SOURCE_UUID,
    BLUEZ_SERVICE_NAME,
    DBUS_PROPERTIES,
    DEVICE_INTERFACE,
    MEDIA_ENDPOINT_INTERFACE,
    MEDIA_TRANSPORT_INTERFACE,
    PROFILE_UUID_COMPLEMENTS,
    get_codec_name,
    get_profile_name,
)
from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL, LOG__USER
from bleep.core.errors import map_dbus_error, BLEEPError, NotAuthorizedError
from bleep.core import preflight as _preflight

__all__ = ["MediaStreamManager"]


def _format_contention_message(report: "_preflight.EndpointContentionReport") -> str:
    """Render an EndpointContentionReport as a user-facing multiline string."""

    lines: List[str] = []
    header = {
        "block": (
            "[-] Endpoint contention detected — BLEEP endpoint registration is "
            "very likely to lose the AVDTP selection race."
        ),
        "warn": (
            "[!] Endpoint contention detected — BLEEP endpoint registration "
            "may lose the AVDTP selection race."
        ),
        "info": (
            "[*] Endpoint contention pre-flight: no active competitors for "
            f"{get_profile_name(report.complement_uuid)} detected."
        ),
    }.get(report.severity, "")
    if header:
        lines.append(header)

    if report.competitors:
        lines.append(
            f"    Competitors for {get_profile_name(report.complement_uuid)} "
            f"({report.complement_uuid}):"
        )
        for owner in report.competitors:
            if owner.backend == "bleep":
                continue
            tag = "inferred" if owner.inferred else "observed"
            proc = f" pid={owner.pid}" if owner.pid else ""
            cmd = f" ({owner.cmdline})" if owner.cmdline else ""
            path = f" {owner.object_path}" if owner.object_path else ""
            lines.append(f"      - {owner.backend}{proc}{cmd}{path} [{tag}]")

    for warning in report.warnings:
        lines.append(f"    warning: {warning}")

    if report.severity == "block":
        lines.append(
            "    BLEEP endpoint registration gated.  Options:"
        )
        lines.append(
            "      * Stop the competing daemon for the duration of the capture"
        )
        lines.append(
            "      * Rerun with '--direct' to acquire the existing transport"
        )
        lines.append(
            "      * Rerun with '--force-endpoint' to bypass this gate"
        )
    elif report.severity == "warn":
        lines.append(
            "    Proceeding anyway; in Debug Mode: 'audiocfg --endpoints' "
            "for the authoritative endpoint owner list."
        )
    return "\n".join(lines)


class MediaStreamManager:
    """High-level manager for Bluetooth audio streaming.

    Handles:
    - MediaTransport acquisition/release (D-Bus)
    - Codec negotiation (D-Bus)
    - Audio encoding/streaming (delegates to audio_codec.py)

    Two acquisition modes are supported:

    * **Default (endpoint registration)** — BLEEP registers its own
      ``MediaEndpoint`` with BlueZ via ``RegisterEndpoint()``, then
      cycles the A2DP profile (``DisconnectProfile`` →
      ``ConnectProfile``) so BlueZ includes the new endpoint in AVDTP
      negotiation and creates a BLEEP-owned transport.
    * **Direct mode** (``direct=True``) — find an existing transport on
      D-Bus and call ``Acquire()`` directly.  Requires the audio daemon
      to be stopped so the transport is unowned.

    Parameters
    ----------
    device_mac : str
        MAC address of Bluetooth device.
    profile_uuid : Optional[str]
        The **remote endpoint** UUID that identifies the desired
        capability on the target device.  Defaults to ``A2DP_SINK_UUID``.
    direct : bool
        If ``True``, skip endpoint registration and attempt to acquire
        an existing transport directly (legacy / constrained mode).
    force_endpoint : bool
        If ``True``, bypass the MediaEndpoint1 contention pre-flight.
        The pre-flight normally short-circuits endpoint registration when
        BlueALSA (the observed race-loser pattern) is running, because
        BlueZ's ``a2dp_select_eps`` would pick the BlueALSA endpoint and
        BLEEP's ``wait_for_transport()`` would time out after 15 s.  Set
        this flag when you have manually verified the competing daemon is
        quiesced for the target device, or when you want to attempt the
        cycle anyway for diagnostic purposes.
    """

    def __init__(
        self,
        device_mac: str,
        profile_uuid: Optional[str] = None,
        direct: bool = False,
        force_endpoint: bool = False,
    ):
        self.device_mac = device_mac
        self.profile_uuid = profile_uuid or A2DP_SINK_UUID
        self.direct = direct
        self.force_endpoint = force_endpoint
        self._transport: Optional[MediaTransport] = None
        self._transport_fd: Optional[int] = None
        self._read_mtu: Optional[int] = None
        self._write_mtu: Optional[int] = None
        self._bleep_endpoint: Optional[BleepMediaEndpoint] = None

    # ------------------------------------------------------------------
    # Transport discovery
    # ------------------------------------------------------------------

    def _collect_media_objects(self) -> Tuple[
        Optional[str],
        list,
        list,
    ]:
        """Scan ``GetManagedObjects()`` for this device's endpoints and transports.

        Extracts endpoint/transport UUIDs directly from the managed-objects
        data so that Phase 1 never needs to construct D-Bus proxy objects
        just to read a UUID — eliminating the silent-exception failures
        that plagued the previous implementation.

        Returns
        -------
        Tuple[Optional[str], list, list]
            ``(device_path,
              [(endpoint_path, endpoint_uuid), ...],
              [(transport_path, transport_uuid), ...])``
            where ``device_path`` is ``None`` if the device was not found.
        """
        managed_objects = get_managed_objects()

        mac_fragment = self.device_mac.upper().replace(":", "_")
        device_path: Optional[str] = None
        endpoints: list = []
        transports: list = []

        for path, interfaces in managed_objects.items():
            path_str = str(path)
            if "/dev_" not in path_str:
                continue

            base = path_str.split("/sep")[0].split("/fd")[0]
            path_mac = base.rsplit("dev_", 1)[-1]
            if path_mac.upper() != mac_fragment:
                continue

            if device_path is None:
                device_path = base

            if MEDIA_ENDPOINT_INTERFACE in interfaces:
                ep_props = interfaces[MEDIA_ENDPOINT_INTERFACE]
                ep_uuid = str(ep_props.get("UUID", "")) if "UUID" in ep_props else ""
                endpoints.append((path_str, ep_uuid))

            if MEDIA_TRANSPORT_INTERFACE in interfaces:
                tp_props = interfaces[MEDIA_TRANSPORT_INTERFACE]
                tp_uuid = str(tp_props.get("UUID", "")) if "UUID" in tp_props else ""
                transports.append((path_str, tp_uuid))

        return device_path, endpoints, transports

    def _get_transport(self) -> Optional[MediaTransport]:
        """Locate the MediaTransport associated with the target endpoint.

        Discovery follows a three-phase strategy so that the most
        structurally sound method is tried first, with progressively
        looser fallbacks:

        1. **Path-based association** — using UUIDs extracted directly
           from ``GetManagedObjects()`` data (no D-Bus proxy needed),
           find a MediaEndpoint whose UUID matches
           ``self.profile_uuid``, then find the MediaTransport whose
           D-Bus path is a child of that endpoint.  The transport is
           accepted regardless of its own UUID.
        2. **Complement UUID fallback** — if no endpoint match or the
           matched endpoint has no child transport, search all transports
           for one whose UUID equals the expected complement from
           ``PROFILE_UUID_COMPLEMENTS``.
        3. **Diagnostic dump** — if both phases fail, log every available
           transport path and UUID so the user can diagnose the mismatch.

        Returns
        -------
        Optional[MediaTransport]
            The resolved transport, or ``None``.
        """
        if self._transport:
            return self._transport

        device_path, endpoints, transports = self._collect_media_objects()

        if not device_path:
            print_and_log(
                f"[-] Device {self.device_mac} not found in BlueZ managed objects",
                LOG__USER,
            )
            return None

        if not transports:
            print_and_log(
                f"[-] No MediaTransports available for {self.device_mac}",
                LOG__USER,
            )
            return None

        profile_name = get_profile_name(self.profile_uuid)
        complement_uuid = PROFILE_UUID_COMPLEMENTS.get(self.profile_uuid)
        complement_name = (
            get_profile_name(complement_uuid) if complement_uuid else "N/A"
        )

        print_and_log(
            f"[*] Searching for transport: endpoint={profile_name}, "
            f"expected transport role={complement_name}, "
            f"endpoints={len(endpoints)}, transports={len(transports)}",
            LOG__DEBUG,
        )

        # Phase 1: path-based endpoint → transport association
        transport = self._find_transport_by_endpoint_path(endpoints, transports)
        if transport:
            self._transport = transport
            return transport

        # Phase 2: complement UUID fallback
        if complement_uuid:
            transport = self._find_transport_by_uuid(transports, complement_uuid)
            if transport:
                print_and_log(
                    f"[+] Transport found via complement UUID fallback "
                    f"({complement_name})",
                    LOG__GENERAL,
                )
                self._transport = transport
                return transport

        # Phase 3: diagnostic dump
        self._log_available_transports(transports, profile_name, complement_name)
        return None

    def _find_transport_by_endpoint_path(
        self,
        endpoints: list,
        transports: list,
    ) -> Optional[MediaTransport]:
        """Phase 1: find transport whose path is a child of a matching endpoint.

        Uses pre-extracted UUIDs from ``GetManagedObjects()`` — no D-Bus
        proxy construction needed for the UUID comparison.
        """
        for ep_path, ep_uuid in endpoints:
            if not ep_uuid or ep_uuid.lower() != self.profile_uuid.lower():
                continue

            ep_profile = get_profile_name(ep_uuid)
            print_and_log(
                f"[+] Matched endpoint {ep_path} ({ep_profile})",
                LOG__DEBUG,
            )

            for tp_path, tp_uuid in transports:
                if not tp_path.startswith(ep_path + "/"):
                    continue

                tp_profile = get_profile_name(tp_uuid) if tp_uuid else "unknown"
                print_and_log(
                    f"[+] Found child transport {tp_path} "
                    f"(local role: {tp_profile})",
                    LOG__GENERAL,
                )
                try:
                    return MediaTransport(tp_path)
                except Exception as e:
                    print_and_log(
                        f"[-] Failed to acquire proxy for transport "
                        f"{tp_path}: {e}",
                        LOG__USER,
                    )
        return None

    def _find_transport_by_uuid(
        self,
        transports: list,
        target_uuid: str,
    ) -> Optional[MediaTransport]:
        """Phase 2: find transport matching a specific UUID."""
        for tp_path, tp_uuid in transports:
            if tp_uuid and tp_uuid.lower() == target_uuid.lower():
                try:
                    return MediaTransport(tp_path)
                except Exception as e:
                    print_and_log(
                        f"[-] Failed to acquire proxy for transport "
                        f"{tp_path}: {e}",
                        LOG__USER,
                    )
        return None

    @staticmethod
    def _log_available_transports(
        transports: list,
        profile_name: str,
        complement_name: str,
    ) -> None:
        """Phase 3: log all transports for diagnostic purposes."""
        print_and_log(
            f"[-] No transport found for endpoint profile {profile_name} "
            f"(expected transport role: {complement_name})",
            LOG__USER,
        )
        for tp_path, tp_uuid in transports:
            tp_name = get_profile_name(tp_uuid) if tp_uuid else "unknown"
            print_and_log(
                f"    Available: {tp_path} uuid={tp_uuid} ({tp_name})",
                LOG__USER,
            )
    
    @staticmethod
    def _print_not_authorized_guidance(state: str) -> None:
        """Print actionable guidance when ``Acquire()`` returns NotAuthorized."""
        print_and_log(
            f"[-] Transport Acquire() denied (transport state: {state})",
            LOG__USER,
        )
        if state == "active":
            print_and_log(
                "[!] The transport is already owned by another process "
                "(likely PulseAudio or PipeWire).\n"
                "    Remediation options:\n"
                "    1. Stop the audio daemon before running BLEEP:\n"
                "         systemctl --user stop pipewire.socket "
                "pipewire.service   # PipeWire\n"
                "         systemctl --user stop pulseaudio.socket "
                "pulseaudio.service # PulseAudio\n"
                "    2. Use 'audio-play --direct' to attempt direct "
                "acquisition (requires daemon stopped)\n"
                "    3. Run without --direct (default) to let BLEEP "
                "register its own endpoint",
                LOG__USER,
            )
        elif state == "idle":
            print_and_log(
                "[!] The transport is idle — no stream has been "
                "requested yet.\n"
                "    The device may need to initiate playback or the "
                "audio profile may need reconnection.",
                LOG__USER,
            )
        else:
            print_and_log(
                f"[!] Transport is in '{state}' state. "
                f"It may be transitioning or owned by another process.",
                LOG__USER,
            )

    # ------------------------------------------------------------------
    # Endpoint-based transport acquisition
    # ------------------------------------------------------------------

    def _device_path(self) -> str:
        """Return the BlueZ D-Bus object path for ``self.device_mac``."""
        mac_underscored = self.device_mac.replace(":", "_")
        return f"/org/bluez/hci0/dev_{mac_underscored}"

    def _cycle_device_connection(self) -> None:
        """Full device disconnect → reconnect to trigger AVDTP re-negotiation.

        ``DisconnectProfile`` + ``ConnectProfile`` is insufficient because
        the AVDTP session (``source->session``) persists across the cycle.
        ``source_connect()`` returns ``-EALREADY`` when the session is
        non-NULL, skipping ``a2dp_discover`` entirely.

        A full ``Device1.Disconnect()`` tears down the ACL link, which
        destroys all AVDTP sessions.  The subsequent ``Device1.Connect()``
        triggers fresh AVDTP discovery (``a2dp_discover`` →
        ``a2dp_select_eps``), including any newly registered endpoints.
        """
        device_path = self._device_path()
        bus = dbus.SystemBus()
        device_obj = bus.get_object(BLUEZ_SERVICE_NAME, device_path)
        device_iface = dbus.Interface(device_obj, DEVICE_INTERFACE)
        props_iface = dbus.Interface(device_obj, DBUS_PROPERTIES)

        print_and_log(
            "[*] Cycling device connection to trigger endpoint "
            "negotiation…",
            LOG__USER,
        )

        device_iface.Disconnect()
        print_and_log("[*] Device disconnected, waiting…", LOG__DEBUG)

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            connected = bool(
                props_iface.Get(DEVICE_INTERFACE, "Connected"),
            )
            if not connected:
                break
            time.sleep(0.2)
        else:
            raise BLEEPError(
                "Device did not disconnect within timeout"
            )

        time.sleep(0.5)

        print_and_log("[*] Reconnecting device…", LOG__DEBUG)
        device_iface.Connect()

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            connected = bool(
                props_iface.Get(DEVICE_INTERFACE, "Connected"),
            )
            if connected:
                break
            time.sleep(0.3)
        else:
            raise BLEEPError(
                "Device did not reconnect within timeout"
            )

    def _acquire_via_endpoint(
        self,
        codec_preference: Optional[str] = None,
    ) -> Tuple[int, int, int]:
        """Register a BLEEP-owned endpoint and acquire the resulting transport.

        Three-step process:

        1. Register a ``BleepMediaEndpoint`` — creates a local SEP in
           BlueZ's endpoint pool and starts the GLib main loop for
           callback dispatch.
        2. Cycle the full device connection (``Disconnect`` →
           ``Connect``).  ``DisconnectProfile`` + ``ConnectProfile`` is
           insufficient because the AVDTP session persists and
           ``source_connect()`` returns ``-EALREADY``.  A full device
           disconnect destroys the ACL link and all AVDTP sessions.  On
           reconnect, BlueZ runs ``a2dp_discover`` →
           ``a2dp_select_eps`` which includes our newly registered
           endpoint.
        3. ``Acquire()`` the transport.

        The system audio daemon's existing stream is briefly interrupted
        during the device cycle but re-establishes after BLEEP releases
        the transport.
        """
        complement_uuid = PROFILE_UUID_COMPLEMENTS.get(self.profile_uuid)
        if not complement_uuid:
            raise BLEEPError(
                f"No complement UUID known for {self.profile_uuid} — "
                f"cannot register endpoint"
            )

        # ------------------------------------------------------------------
        # MediaEndpoint1 contention pre-flight
        # ------------------------------------------------------------------
        # BlueZ picks *one* local endpoint per (adapter, UUID, codec) tuple
        # during AVDTP negotiation.  If another daemon (BlueALSA in the
        # observed failure mode) has already registered for the complement
        # role, BlueZ will almost certainly pick it over our newly-registered
        # endpoint — wait_for_transport() then blocks for 15 s before raising.
        # Detect this before we cycle the device connection.
        contention_report = None
        try:
            contention_report = _preflight.check_endpoint_contention(
                self.profile_uuid,
                device_mac=self.device_mac,
                deep_probe=False,
            )
        except Exception as exc:
            # Pre-flight is advisory — never let it break the acquisition path.
            print_and_log(
                f"[debug] endpoint contention pre-flight failed: {exc}",
                LOG__DEBUG,
            )

        if contention_report is not None and contention_report.severity != "none":
            message = _format_contention_message(contention_report)
            if contention_report.has_blocker() and not self.force_endpoint:
                raise BLEEPError(message)
            print_and_log(message, LOG__USER)

        ep_kwargs: dict = {"profile_uuid": complement_uuid}
        if codec_preference:
            from bleep.bt_ref.constants import codec_name_to_id
            cid = codec_name_to_id(codec_preference)
            if cid is not None:
                ep_kwargs["codec_id"] = cid
                print_and_log(
                    f"[*] Requesting codec preference: {codec_preference} (id=0x{cid:02x})",
                    LOG__GENERAL,
                )
            else:
                print_and_log(
                    f"[!] Unknown codec '{codec_preference}', falling back to SBC",
                    LOG__USER,
                )

        self._bleep_endpoint = BleepMediaEndpoint(**ep_kwargs)
        self._bleep_endpoint.register()

        try:
            self._cycle_device_connection()
        except (dbus.exceptions.DBusException, BLEEPError) as exc:
            self._bleep_endpoint.unregister()
            if isinstance(exc, BLEEPError):
                raise
            raise BLEEPError(
                f"Failed to cycle device connection: "
                f"{exc.get_dbus_message() or exc.get_dbus_name()}. "
                f"Is the device connected?"
            )

        print_and_log(
            f"[*] Waiting for BlueZ to assign a transport to BLEEP "
            f"endpoint (profile={get_profile_name(complement_uuid)})…",
            LOG__USER,
        )
        transport_path = self._bleep_endpoint.wait_for_transport(timeout=15.0)

        if not transport_path:
            self._bleep_endpoint.unregister()

            # Re-run the contention probe post-timeout — the primary probe
            # may have missed a non-BlueALSA competitor that only a deep
            # probe surfaces.  Treat failures as non-fatal diagnostic noise.
            post_report = None
            try:
                post_report = _preflight.check_endpoint_contention(
                    self.profile_uuid,
                    device_mac=self.device_mac,
                    deep_probe=True,
                )
            except Exception as exc:
                print_and_log(
                    f"[debug] post-timeout contention probe failed: {exc}",
                    LOG__DEBUG,
                )

            base_message = (
                "BlueZ did not invoke SetConfiguration() on the BLEEP-"
                "registered MediaEndpoint within the timeout. This means "
                "BlueZ's AVDTP endpoint selection (a2dp_select_eps) did "
                "not pick the BLEEP endpoint, so no transport was created "
                "for BLEEP to acquire.\n"
                "    Common causes:\n"
                "      1. A competing endpoint provider (BlueALSA, "
                "PipeWire bluez5, PulseAudio module-bluetooth) was "
                "already registered for the same profile and BlueZ "
                "selected it instead. In Debug Mode: 'audiocfg' to "
                "inspect which backends are active and whether a "
                "conflict is present.\n"
                "      2. The remote device does not expose a compatible "
                f"{get_profile_name(self.profile_uuid)} endpoint with a "
                "codec the BLEEP endpoint advertised.\n"
                "      3. The device failed to complete AVDTP discovery "
                "within the cycle window (check BlueZ logs with "
                "'journalctl -u bluetooth -f' while retrying).\n"
                "    Next steps: in Debug Mode use 'mediaenum' to "
                "inspect available endpoints and 'audiocfg' to see "
                "backend status/conflicts, or rerun with '--direct' to "
                "acquire an existing transport owned by another daemon."
            )
            if post_report is not None and post_report.competitors:
                base_message += (
                    "\n    Contention report (deep probe):\n"
                    + _format_contention_message(post_report)
                )
            raise BLEEPError(base_message)

        print_and_log(
            f"[+] BlueZ assigned transport: {transport_path}",
            LOG__GENERAL,
        )
        transport = MediaTransport(transport_path)
        self._transport = transport

        try:
            fd, read_mtu, write_mtu = transport.acquire()
            self._transport_fd = fd
            self._read_mtu = read_mtu
            self._write_mtu = write_mtu
            print_and_log(
                f"[+] Acquired BLEEP-owned transport: fd={fd}, "
                f"read_mtu={read_mtu}, write_mtu={write_mtu}",
                LOG__GENERAL,
            )
            return fd, read_mtu, write_mtu
        except Exception as e:
            self._bleep_endpoint.unregister()
            mapped = (
                map_dbus_error(e) if hasattr(e, 'get_dbus_name')
                else BLEEPError(str(e))
            )
            print_and_log(
                f"[-] Failed to acquire BLEEP-owned transport: {mapped}",
                LOG__USER,
            )
            raise mapped

    def _acquire_direct(self) -> Tuple[int, int, int]:
        """Acquire an existing transport directly (legacy/constrained mode)."""
        transport = self._get_transport()
        if not transport:
            complement = PROFILE_UUID_COMPLEMENTS.get(self.profile_uuid)
            complement_name = (
                get_profile_name(complement) if complement else "N/A"
            )
            raise BLEEPError(
                f"MediaTransport not found for device {self.device_mac} — "
                f"searched for endpoint UUID {self.profile_uuid} "
                f"({get_profile_name(self.profile_uuid)}), "
                f"expected transport role: {complement_name}. "
                f"Check the diagnostic output above or run 'media-enum' "
                f"for full details."
            )

        try:
            fd, read_mtu, write_mtu = transport.acquire()
            self._transport_fd = fd
            self._read_mtu = read_mtu
            self._write_mtu = write_mtu
            print_and_log(
                f"[+] Acquired transport: fd={fd}, "
                f"read_mtu={read_mtu}, write_mtu={write_mtu}",
                LOG__GENERAL,
            )
            return fd, read_mtu, write_mtu
        except Exception as e:
            mapped = (
                map_dbus_error(e) if hasattr(e, 'get_dbus_name')
                else BLEEPError(str(e))
            )
            if isinstance(mapped, NotAuthorizedError):
                state = transport.get_state() or "unknown"
                self._print_not_authorized_guidance(state)
            else:
                print_and_log(
                    f"[-] Failed to acquire transport: {mapped}",
                    LOG__USER,
                )
            raise mapped

    def acquire_transport(
        self,
        codec_preference: Optional[str] = None,
    ) -> Tuple[int, int, int]:
        """Acquire MediaTransport file descriptor for audio streaming.

        In default mode, registers a BLEEP-owned endpoint with BlueZ so
        the resulting transport is exclusively owned by this process.
        In direct mode (``self.direct=True``), attempts to acquire an
        existing transport — requires no other process to own it.

        Parameters
        ----------
        codec_preference : Optional[str]
            Preferred codec name (e.g. 'SBC', 'AAC', 'MP3'). When provided
            in endpoint mode, the endpoint is registered with the requested
            codec ID so BlueZ negotiates that codec with the remote device.
            Falls back to SBC if the codec name is not recognised.

        Returns
        -------
        Tuple[int, int, int]
            ``(file_descriptor, read_mtu, write_mtu)``

        Raises
        ------
        BLEEPError
            If transport acquisition fails.
        """
        if self.direct:
            return self._acquire_direct()
        return self._acquire_via_endpoint(codec_preference=codec_preference)
    
    def release_transport(self) -> None:
        """Release the acquired transport and clean up endpoint resources."""
        if self._transport and self._transport_fd is not None:
            try:
                self._transport.release()
                print_and_log("[+] Released transport", LOG__GENERAL)
            except Exception as e:
                print_and_log(
                    f"[-] Error releasing transport: {str(e)}",
                    LOG__DEBUG,
                )
            finally:
                self._transport_fd = None
                self._read_mtu = None
                self._write_mtu = None

        if self._bleep_endpoint and self._bleep_endpoint.registered:
            self._bleep_endpoint.unregister()
            self._bleep_endpoint = None
    
    def get_transport_info(self) -> dict:
        """
        Get current transport information (codec, state, volume, etc.).
        
        Returns
        -------
        dict
            Dictionary with transport information
        """
        transport = self._get_transport()
        if not transport:
            return {}
        
        return {
            "uuid": transport.get_uuid(),
            "codec": transport.get_codec(),
            "codec_name": get_codec_name(transport.get_codec() or 0),
            "state": transport.get_state(),
            "volume": transport.get_volume(),
            "delay": transport.get_delay(),
            "configuration": transport.get_configuration(),
        }
    
    def set_volume(self, volume: int) -> bool:
        """
        Set transport volume.
        
        Uses existing MediaTransport.set_volume() from dbuslayer/media.py.
        
        Parameters
        ----------
        volume : int
            Volume level (0-127 for A2DP, 0-255 for BAP)
        
        Returns
        -------
        bool
            True if successful, False otherwise
        """
        transport = self._get_transport()
        if not transport:
            return False
        
        return transport.set_volume(volume)
    
    def get_codec_info(self) -> dict:
        """
        Get codec information from transport.
        
        Returns
        -------
        dict
            Dictionary with codec information
        """
        transport = self._get_transport()
        if not transport:
            return {}
        
        codec = transport.get_codec()
        return {
            "codec_id": codec,
            "codec_name": get_codec_name(codec or 0),
            "configuration": transport.get_configuration(),
        }
    
    def play_audio_file(
        self,
        audio_file: str,
        volume: Optional[int] = None,
        codec_preference: Optional[str] = None,
    ) -> bool:
        """
        Play audio file to Bluetooth device.
        
        Orchestrates:
        1. Transport acquisition (D-Bus)
        2. Volume setting (D-Bus)
        3. Audio encoding (audio_codec.py)
        4. Transport release (D-Bus)
        
        Parameters
        ----------
        audio_file : str
            Path to audio file (MP3, WAV, FLAC, etc.)
        volume : Optional[int]
            Volume level (0-127). If None, current volume is used.
        codec_preference : Optional[str]
            Preferred codec name (e.g. 'SBC', 'AAC', 'MP3'). Passed to
            ``acquire_transport`` to influence endpoint registration.
        
        Returns
        -------
        bool
            True if playback succeeded, False otherwise
        """
        try:
            # Acquire transport
            fd, read_mtu, write_mtu = self.acquire_transport(
                codec_preference=codec_preference
            )
            
            # Set volume if specified
            if volume is not None:
                self.set_volume(volume)
            
            # Get codec from transport
            codec_info = self.get_codec_info()
            codec_id = codec_info.get("codec_id")
            if codec_id is None:
                print_and_log("[-] Codec information not available", LOG__USER)
                self.release_transport()
                return False
            
            # Initialize encoder
            encoder = AudioCodecEncoder(codec_id, codec_info.get("configuration"))
            
            # Encode and write to transport
            print_and_log(
                f"[*] Encoding and playing {audio_file} using {codec_info.get('codec_name', 'Unknown')} codec",
                LOG__USER,
            )
            success = encoder.encode_file_to_transport(audio_file, fd, write_mtu)
            
            # Release transport
            self.release_transport()
            
            if success:
                print_and_log(f"[+] Audio playback completed", LOG__GENERAL)
            else:
                print_and_log(f"[-] Audio playback failed", LOG__USER)
            
            return success
            
        except Exception as e:
            print_and_log(
                f"[-] Error during audio playback: {str(e)}",
                LOG__USER,
            )
            # Ensure transport is released on error
            try:
                self.release_transport()
            except Exception:
                pass
            return False
    
    def record_audio(
        self,
        output_file: str,
        duration: Optional[int] = None
    ) -> bool:
        """
        Record audio from Bluetooth device.
        
        Orchestrates:
        1. Transport acquisition (D-Bus)
        2. Audio decoding (audio_codec.py)
        3. Transport release (D-Bus)
        
        Parameters
        ----------
        output_file : str
            Path to output audio file
        duration : Optional[int]
            Recording duration in seconds. If None, records until stopped.
            (Note: Duration control not yet implemented)
        
        Returns
        -------
        bool
            True if recording succeeded, False otherwise
        """
        try:
            # Acquire transport
            fd, read_mtu, write_mtu = self.acquire_transport()
            
            # Get codec from transport
            codec_info = self.get_codec_info()
            codec_id = codec_info.get("codec_id")
            if codec_id is None:
                print_and_log("[-] Codec information not available", LOG__USER)
                self.release_transport()
                return False
            
            # Initialize decoder
            decoder = AudioCodecDecoder(codec_id)
            
            # Decode and write to file
            print_and_log(
                f"[*] Recording audio to {output_file} using {codec_info.get('codec_name', 'Unknown')} codec",
                LOG__USER,
            )
            success = decoder.decode_audio_stream(fd, output_file, codec_id, read_mtu)
            
            # Release transport
            self.release_transport()
            
            if success:
                print_and_log(f"[+] Audio recording completed", LOG__GENERAL)
            else:
                print_and_log(f"[-] Audio recording failed", LOG__USER)
            
            return success
            
        except Exception as e:
            print_and_log(
                f"[-] Error during audio recording: {str(e)}",
                LOG__USER,
            )
            # Ensure transport is released on error
            try:
                self.release_transport()
            except Exception:
                pass
            return False
