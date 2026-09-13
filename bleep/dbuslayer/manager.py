"""BlueZ Device Manager for Low-Energy devices (Phase-4 extraction).

This module provides a trimmed-down adaptation of the original
`bluetooth__le__deviceManager` class found in the monolith.  It is responsible
for discovering BLE devices exposed by a single adapter, tracking their life-
cycle, and instantiating `system_dbus__bluez_device__low_energy` wrappers.

Only the behaviour required by Phase-4 is implemented – primarily discovery
and basic device bookkeeping – but the public surface mirrors the legacy class
so higher-level code keeps working unchanged.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Dict, List, Optional, Any

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

from bleep.dbuslayer.bus import get_bus as _get_bus
from bleep.bt_ref.constants import (
    BLUEZ_SERVICE_NAME,
    BLUEZ_NAMESPACE,
    ADAPTER_INTERFACE,
    DEVICE_INTERFACE,
    ADAPTER_NAME,
    DBUS_OM_IFACE,
    DBUS_PROPERTIES,
)
from bleep.core.constants import (
    BT_DEVICE_TYPE_UNKNOWN,
    BT_DEVICE_TYPE_CLASSIC,
)
from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG
from bleep.core import errors
from bleep.core.errors import map_dbus_error
from bleep.dbuslayer.signals import system_dbus__bluez_signals as _SignalsRegistry

__all__ = [
    "system_dbus__bluez_device_manager",
    "build_discovered_device_dict",
]


def _classify_device_type_from_properties(properties: dict) -> str:
    """Evidence-based type for a Device1 properties dict (passive scan context)."""
    try:
        from bleep.analysis.device_type_classifier import DeviceTypeClassifier

        mac = properties.get("Address", "")
        if not mac:
            return BT_DEVICE_TYPE_UNKNOWN
        context = {
            "device_class": properties.get("Class"),
            "address_type": properties.get("AddressType"),
            "uuids": [str(uuid).strip().upper() for uuid in properties.get("UUIDs", [])],
            "connected": properties.get("Connected", False),
            "service_data": dict(properties.get("ServiceData", {})),
            "advertising_data": dict(properties.get("AdvertisingData", {})),
            "manufacturer_data": dict(properties.get("ManufacturerData", {})),
            "appearance": properties.get("Appearance"),
        }
        result = DeviceTypeClassifier().classify_with_mode(
            mac=mac,
            context=context,
            scan_mode="passive",
            use_database_cache=True,
        )
        return result.device_type
    except Exception:
        return BT_DEVICE_TYPE_UNKNOWN


def build_discovered_device_dict(
    path: str,
    properties: dict,
    *,
    rssi: Any = None,
) -> Dict[str, Any]:
    """Map BlueZ Device1 properties to the dict shape used by scan/survey.

    Shared by adapter GMO reads and DeviceManager pre-stop harvest so mapping
    stays in one place (R1).
    """
    if rssi is None and "RSSI" in properties:
        rssi = properties.get("RSSI")

    device_type = _classify_device_type_from_properties(properties)
    type_display = "br/edr" if device_type == BT_DEVICE_TYPE_CLASSIC else device_type

    mfr_raw = properties.get("ManufacturerData")
    if mfr_raw:
        try:
            mfr_data = {int(k): bytes(v) for k, v in mfr_raw.items()}
        except (TypeError, ValueError):
            mfr_data = {}
    else:
        mfr_data = {}

    sd_raw = properties.get("ServiceData")
    if sd_raw:
        try:
            sd_data = {str(k): bytes(v) for k, v in sd_raw.items()}
        except (TypeError, ValueError):
            sd_data = {}
    else:
        sd_data = {}

    return {
        "path": path,
        "address": properties.get("Address", ""),
        "name": properties.get("Name", ""),
        "rssi": rssi,
        "alias": properties.get("Alias", ""),
        "address_type": properties.get("AddressType"),
        "device_class": properties.get("Class"),
        "uuids": (
            [str(uuid).strip().upper() for uuid in properties.get("UUIDs", [])]
            if properties.get("UUIDs")
            else []
        ),
        "connected": properties.get("Connected", False),
        "type": type_display,
        "manufacturer_data": mfr_data,
        "service_data": sd_data,
        "tx_power": int(properties["TxPower"]) if "TxPower" in properties else None,
        "appearance": int(properties["Appearance"]) if "Appearance" in properties else None,
        "modalias": str(properties["Modalias"]) if "Modalias" in properties else None,
        "paired": bool(properties.get("Paired", False)),
        "bonded": bool(properties.get("Bonded", False)),
        "trusted": bool(properties.get("Trusted", False)),
        "blocked": bool(properties.get("Blocked", False)),
        "wake_allowed": bool(properties.get("WakeAllowed", False)),
        "icon": str(properties["Icon"]) if "Icon" in properties else None,
        "advertising_flags": (
            bytes(properties["AdvertisingFlags"])
            if "AdvertisingFlags" in properties
            else None
        ),
        "advertising_data": (
            {int(k): bytes(v) for k, v in properties["AdvertisingData"].items()}
            if "AdvertisingData" in properties
            else None
        ),
    }


_signals_manager = _SignalsRegistry()

#: Size of the most recent ``GetManagedObjects`` harvest reply.
#:
#: BlueZ keeps a ``dev_*`` object for every address it has seen while
#: discovering, so under RPA rotation this grows monotonically and every harvest
#: reply grows with it.  That is the leading explanation for two open findings
#: at once (docs/d-bus-reliability.md): the ~2.1 MB/round retention that does
#: *not* track our own device count, and the collector wedge that landed at
#: 2490s / round 79 in both Run E and Run F.
#:
#: Recorded here rather than sampled directly because ``_snapshot_gmo_devices``
#: already holds the reply — asking BlueZ again would add D-Bus traffic to the
#: very connection under suspicion, and would block once it wedges.
LAST_HARVEST: Dict[str, int] = {"objects": 0, "devices": 0}

# Lazy-load device_le to break circular dependency
def _get_le_device_class():
    from bleep.dbuslayer.device_le import system_dbus__bluez_device__low_energy
    return system_dbus__bluez_device__low_energy

def _error_from_dbus_error(exc: dbus.exceptions.DBusException) -> errors.BLEEPError:
    return map_dbus_error(exc)


class system_dbus__bluez_device_manager:  # noqa: N802 – keep legacy naming
    """Entry point for managing a set of BLE GATT devices on one adapter."""

    # ---------------------------------------------------------------------
    # Construction & D-Bus helpers
    # ---------------------------------------------------------------------
    def __init__(self, adapter_name: str = ADAPTER_NAME):
        self.adapter_name = adapter_name
        self._bus = _get_bus()

        # BlueZ objects / interfaces
        self._adapter_path = f"{BLUEZ_NAMESPACE}{adapter_name}"
        adapter_obj = self._bus.get_object(BLUEZ_SERVICE_NAME, self._adapter_path)
        self._adapter = dbus.Interface(adapter_obj, ADAPTER_INTERFACE)
        self._adapter_props = dbus.Interface(adapter_obj, DBUS_PROPERTIES)
        om_obj = self._bus.get_object(BLUEZ_SERVICE_NAME, "/")
        self._object_manager = dbus.Interface(om_obj, DBUS_OM_IFACE)

        # BlueZ uses uppercase hex digits in device paths by convention, but
        # some kernels/distros emit lower-case letters.  Accept *either* by
        # compiling a case-insensitive regex and allowing the character range
        # to include `a-f` as well.
        self._device_path_regex = re.compile(
            rf"^{BLUEZ_NAMESPACE}{adapter_name}/dev_([0-9A-Fa-f]{{2}}(?:_[0-9A-Fa-f]{{2}}){{5}})$",
            re.IGNORECASE,
        )

        # State
        self._devices: Dict[str, Any] = {}  # Will contain system_dbus__bluez_device__low_energy instances
        # (see module-level LAST_HARVEST for per-round GetManagedObjects sizing)
        self._mainloop: Optional[GLib.MainLoop] = None
        self._timer_id: Optional[int] = None
        self._discovery_timeout_ms = 60_000  # 60 seconds default
        self._discovery_active: bool = False
        # Diagnosability: last swallowed/degraded discovery-call failure (Step-3).
        # Populated by _note_discovery_error(); None while no failure seen.
        self._last_discovery_error: Optional[dict] = None

        # RSSI cache for capturing RSSI values during discovery
        self._rssi_cache: Dict[str, int] = {}  # MAC address -> RSSI value
        self._rssi_cache_lock = threading.Lock()

        # R1: last pre-stop harvest (written in _timeout; consumed by take_last_harvest)
        self._last_harvest: Optional[List[Dict[str, Any]]] = None
        # R2: session census stays open until harvest is taken / end_discovery
        # (survives StopDiscovery / InterfacesRemoved — STOP_CLEARS barrier).
        self._session_capturing: bool = False
        self._session_devices: Dict[str, Dict[str, Any]] = {}
        self._session_lock = threading.Lock()

        # LR-2c: intra-round advertisement-fingerprint rotation tracker. BlueZ can
        # rotate ServiceData/ManufacturerData within a single survey round; a rotation
        # that reverts before the round's end-of-round GetManagedObjects snapshot is
        # invisible to both the census and adv_reports (both consume that snapshot).
        # The per-advertisement signal stream is the only sub-round source, so — as
        # LR-6 did for RSSI — we remember the last payload per (MAC, kind, key) and
        # flag same-length rotations. Both structures are scoped to one discovery
        # round (reset in start_discovery) and guarded by their own lock. State is
        # per-manager, so under the multi-adapter model (D1/D2) each adapter's
        # manager tracks only its own devices.
        self._adv_fp_last: Dict[str, Dict[tuple, bytes]] = {}  # MAC -> {(kind,key): payload}
        self._adv_fp_rotated: set = set()  # MACs that rotated a fingerprint this round
        self._adv_fp_lock = threading.Lock()

        # Pre-populate device cache for already-known objects
        self.update_devices()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def devices(self) -> List[Any]:  # Returns list of system_dbus__bluez_device__low_energy instances
        """Return the list of known devices (updates cache first)."""
        self.update_devices()
        return list(self._devices.values())

    # Discovery ----------------------------------------------------------
    def _note_discovery_error(
        self, method: str, exc: Exception, *, degraded: bool = False
    ) -> None:
        """Surface (do not silently swallow) a discovery-call failure.

        Records the failure on ``self._last_discovery_error`` and emits a real
        (``LOG__GENERAL``) warning carrying the exact D-Bus error name and the
        adapter's current ``Discovering`` state. Behaviour and return values are
        unchanged; this only raises the visibility of errors previously logged at
        DEBUG (Step-3 diagnosability upgrade — swallowed discovery errors hid the
        LE<->Classic transition race on affected builds). ``degraded`` marks a
        failure the caller intentionally treats as a no-op.
        """
        if isinstance(exc, dbus.exceptions.DBusException):
            err_name = exc.get_dbus_name() or "unknown"
            err_msg = exc.get_dbus_message() or ""
        else:
            err_name = exc.__class__.__name__
            err_msg = str(exc)
        try:
            discovering = bool(
                self._adapter_props.Get(ADAPTER_INTERFACE, "Discovering")
            )
        except Exception:
            discovering = None
        self._last_discovery_error = {
            "method": method,
            "error_name": err_name,
            "error_message": err_msg,
            "discovering": discovering,
            "degraded": degraded,
        }
        suffix = f": {err_msg}" if err_msg else ""
        note = " (degraded to no-op)" if degraded else ""
        print_and_log(
            f"[!] {method} failed on {self._adapter_path}: {err_name}{suffix} "
            f"(Discovering={discovering}){note}",
            LOG__GENERAL,
        )

    def start_discovery(
        self,
        service_uuids: Optional[List[str]] = None,
        timeout: int = 60,
        transport: str = "le",
        *,
        duplicate_data: Optional[bool] = None,
        pattern: Optional[str] = None,
        rssi: Optional[int] = None,
        pathloss: Optional[int] = None,
        dbus_timeout: Optional[float] = None,
    ):
        """Start discovery with a single merged BlueZ discovery filter.

        The call returns immediately; use :py:meth:`run` to enter the GLib
        main-loop and receive discovery callbacks.  *transport* selects the
        BlueZ discovery filter transport, enabling a per-adapter Classic
        collector under the multi-adapter model (D2).  Accepted values are
        ``"le"`` (default, backward compatible), ``"bredr"``, and ``"auto"``;
        ``"both"`` is accepted as an alias for ``"auto"`` (BlueZ itself only
        recognises ``auto``/``bredr``/``le`` — see ``org.bluez.Adapter`` docs).

        Optional *duplicate_data*, *pattern*, *rssi*, and *pathloss* are merged
        into the same ``SetDiscoveryFilter`` call. Callers must not pre-set a
        partial filter that this method would overwrite.
        """
        service_uuids = service_uuids or []
        # BlueZ SetDiscoveryFilter only accepts auto|bredr|le; map the survey's
        # "both" onto BlueZ "auto" (interleaved LE+BR/EDR) so a hciN:both
        # collector cannot set an invalid filter.
        transport = "auto" if transport == "both" else transport
        discovery_filter: Dict[str, Any] = {"Transport": transport}
        if service_uuids:
            discovery_filter["UUIDs"] = service_uuids
        if duplicate_data is not None:
            discovery_filter["DuplicateData"] = bool(duplicate_data)
        if pattern:
            discovery_filter["Pattern"] = str(pattern)
        if rssi is not None:
            discovery_filter["RSSI"] = int(rssi)
        if pathloss is not None:
            discovery_filter["Pathloss"] = int(pathloss)

        # ``SetDiscoveryFilter`` is optional (not present on very old BlueZ and
        # in our unit-test stub).  Ignore *attribute not found* as non-fatal.
        try:
            if hasattr(self._adapter, "SetDiscoveryFilter"):
                self._adapter.SetDiscoveryFilter(discovery_filter)
        except dbus.exceptions.DBusException as e:
            name = e.get_dbus_name()
            if name not in (
                "org.freedesktop.DBus.Error.UnknownObject",
                "org.bluez.Error.NotSupported",
            ):
                raise _error_from_dbus_error(e)
            # Optional-filter absence is non-fatal, but surface it rather than
            # ignoring it entirely (Step-3 diagnosability upgrade).
            self._note_discovery_error("SetDiscoveryFilter", e, degraded=True)

        # StartDiscovery *must* exist; if the adapter is powered off or absent
        # BlueZ raises UnknownObject – surface that clearly via NotReadyError.
        try:
            # ``dbus_timeout`` bounds the *reply* wait, not the scan window.
            # Left None on the normal path so startup behaviour is unchanged;
            # the stall re-arm passes a short value because a wedged bluetoothd
            # returns no reply at all and the 25s dbus-python default then costs
            # ~25s per attempt on the collector thread (2026-09-08 Run D: 21
            # attempts ≈ 9 minutes lost). See docs/survey_mode.md.
            if dbus_timeout is not None:
                self._adapter.StartDiscovery(timeout=dbus_timeout)
            else:
                self._adapter.StartDiscovery()
            print_and_log("[*] Discovery started", LOG__DEBUG)
        except dbus.exceptions.DBusException as e:
            mapped = _error_from_dbus_error(e)
            # Gracefully degrade when the adapter or BlueZ stub lacks the
            # StartDiscovery method (common on CI runners without real BlueZ
            # or when the test-suite injects a minimal stub).  Treat the
            # absence as a *no-op* rather than a hard failure so the caller
            # can proceed – the main-loop still runs and callers that rely on
            # signal emission will simply observe an empty device list.
            if mapped.code in (
                errors.RESULT_ERR_IN_PROGRESS,  # discovery already running
                errors.RESULT_ERR_WRONG_STATE,  # adapter powered-off
                errors.RESULT_ERR_NOT_FOUND,  # StartDiscovery unknown
            ):
                # Preserve the graceful degrade, but SURFACE it (was silent
                # DEBUG) so an affected build is captured with hard data.
                self._note_discovery_error("StartDiscovery", e, degraded=True)
            else:
                self._note_discovery_error("StartDiscovery", e)
                raise mapped

        self._discovery_timeout_ms = int(timeout * 1000)
        self._discovery_active = True
        # Clear ephemeral discovery state for the new session (R1/R2).
        self._ensure_session_state()
        self._last_harvest = None
        self.clear_rssi_cache()
        self._clear_session_devices()
        self._session_capturing = True
        # LR-2c: reset the intra-round fingerprint tracker so rotation detection is
        # scoped to this discovery round (mirrors the RSSI-cache reset above).
        self._clear_adv_fingerprints()

    def stop_discovery(self):
        try:
            self._adapter.StopDiscovery()
        except dbus.exceptions.DBusException as e:
            # Swallow (preserve behaviour — a failed stop must never crash the
            # caller) but SURFACE it for diagnosability (Step-3). Under
            # cross-client contention this legitimately returns
            # ``org.bluez.Error.Failed: No discovery started``.
            self._note_discovery_error("StopDiscovery", e, degraded=True)
        self._discovery_active = False
        # Do NOT clear _session_capturing here — BlueZ may emit InterfacesRemoved
        # for non-connectable beacons immediately after StopDiscovery (STOP_CLEARS);
        # the session census must remain open until take_last_harvest / end_discovery.

    # Non-blocking discovery (shared-loop / multi-adapter collection) --------
    def begin_discovery(
        self,
        service_uuids: Optional[List[str]] = None,
        timeout: int = 60,
        transport: str = "le",
        *,
        duplicate_data: Optional[bool] = None,
        pattern: Optional[str] = None,
        rssi: Optional[int] = None,
        pathloss: Optional[int] = None,
        dbus_timeout: Optional[float] = None,
    ) -> None:
        """Start discovery **without** entering a blocking main-loop.

        Unlike :py:meth:`run`, this attaches signal listeners, registers this
        manager for adapter-aware RSSI routing, and starts discovery, then
        returns immediately.  The caller drives a main-loop elsewhere (the
        shared :mod:`bleep.dbuslayer.loop_service`) and must call
        :py:meth:`end_discovery` when the collection window closes.  This is the
        concurrency primitive behind multi-adapter passive collection (D2).
        """
        _signals_manager.ensure_listening()
        _signals_manager.register_device_manager(self)
        self.start_discovery(
            service_uuids=service_uuids,
            timeout=timeout,
            transport=transport,
            duplicate_data=duplicate_data,
            pattern=pattern,
            rssi=rssi,
            pathloss=pathloss,
            dbus_timeout=dbus_timeout,
        )

    def end_discovery(self) -> None:
        """Stop discovery started via :py:meth:`begin_discovery` and deregister.

        Callers must :py:meth:`snapshot_discovered_devices` *before* this method
        so non-connectable Device1 objects are captured while Discovering=true.
        """
        self.stop_discovery()
        self._session_capturing = False
        try:
            _signals_manager.unregister_device_manager(self)
        except Exception:  # pragma: no cover - defensive
            pass

    # Main-loop ---------------------------------------------------------
    def run(self):
        """Run a GLib main-loop until the timeout expires."""
        if self._mainloop is not None:
            return  # already running

        # Connect signal receivers via the global hub so devices get events.
        _signals_manager.ensure_listening()
        
        # Register this DeviceManager instance for RSSI forwarding
        _signals_manager.register_device_manager(self)

        self._mainloop = GLib.MainLoop()
        self._timer_id = GLib.timeout_add(self._discovery_timeout_ms, self._timeout)
        try:
            self._mainloop.run()
        finally:
            self._cleanup_after_run()

    def _timeout(self):
        # R1: snapshot while Discovering is still true, then stop. BlueZ removes
        # unpaired non-connectable Device1 objects on StopDiscovery (STOP_CLEARS).
        try:
            self._last_harvest = self._compose_harvest()
        except Exception as exc:  # noqa: BLE001 - never skip stop/quit
            print_and_log(
                f"[!] Discovery harvest failed before StopDiscovery: {exc}",
                LOG__GENERAL,
            )
            self._last_harvest = self._compose_harvest_from_census_only()
        self.stop_discovery()
        if self._mainloop is not None:
            self._mainloop.quit()

        # Mark the timer as inactive so cleanup does not attempt a second
        # removal which triggers GLib warnings such as
        # "Source ID X was not found when attempting to remove it".
        self._timer_id = None

        return False  # cancel further timeouts

    def _cleanup_after_run(self):
        # ``_timeout`` sets ``self._timer_id`` to *None* when it fires, so a
        # second attempt to remove the same source would print a GLib warning.
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        self._mainloop = None
        self._discovery_active = False
        # Keep this manager registered and _session_capturing True until
        # take_last_harvest() so late InterfacesRemoved (STOP_CLEARS) can still
        # update the session census. Callers of run() must take_last_harvest().
        # Note: RSSI cache is NOT cleared here - it's cleared at the start of the next discovery
        # in start_discovery(). This allows get_discovered_devices() to access cached RSSI values
        # after discovery completes.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def update_devices(self):
        """Ensure `_devices` contains wrappers for all objects BlueZ exposes."""
        managed_objects = self._object_manager.GetManagedObjects().items()
        macs = [self._mac_address(path) for path, _ in managed_objects]
        for mac in [m for m in macs if m and m not in self._devices]:
            self._create_device(mac)

    def _create_device(self, mac: str):
        dev = _get_le_device_class()(mac, self.adapter_name)
        self._devices[mac] = dev
        _signals_manager.register_device(dev)
        print_and_log(f"[BLEEP] Device object created for {mac}", LOG__DEBUG)
        return dev

    def _mac_address(self, device_path: str) -> Optional[str]:
        match = self._device_path_regex.match(device_path)
        if not match:
            return None
        return match.group(1).replace("_", ":").upper()

    # ------------------------------------------------------------------
    # RSSI Cache Management
    # ------------------------------------------------------------------
    def _ensure_session_state(self) -> None:
        """Lazily init R1/R2 fields (unit stubs sometimes skip full ``__init__``)."""
        if not hasattr(self, "_session_lock"):
            self._session_lock = threading.Lock()
        if not hasattr(self, "_session_devices"):
            self._session_devices = {}
        if not hasattr(self, "_session_capturing"):
            self._session_capturing = False
        if not hasattr(self, "_last_harvest"):
            self._last_harvest = None

    def is_discovery_active(self) -> bool:
        """Return True if discovery is currently active."""
        return self._discovery_active

    def is_session_capturing(self) -> bool:
        """Return True while the R2 session census is open (may outlive Discovering)."""
        self._ensure_session_state()
        return self._session_capturing

    # ------------------------------------------------------------------
    # R1/R2 harvest — snapshot before StopDiscovery + session census merge
    # ------------------------------------------------------------------
    def snapshot_discovered_devices(self) -> List[Dict[str, Any]]:
        """Return the current harvest without stopping discovery.

        Used by multi-collector ``AdapterSession.harvest`` while Discovering=true.
        """
        return self._compose_harvest()

    def take_last_harvest(self) -> List[Dict[str, Any]]:
        """Return the harvest stored by :py:meth:`run` / ``_timeout`` and close the session.

        Exclusive post-``run()`` read path (do not call ``StopDiscovery`` again).
        """
        self._ensure_session_state()
        result = list(self._last_harvest or [])
        self._last_harvest = None
        self._session_capturing = False
        try:
            _signals_manager.unregister_device_manager(self)
        except Exception:  # pragma: no cover - defensive
            pass
        return result

    def _compose_harvest(self) -> List[Dict[str, Any]]:
        """Merge GMO snapshot (if available) with the R2 session census."""
        gmo = self._snapshot_gmo_devices()
        census = self._session_census_as_dicts()
        merged = self._merge_harvest_by_mac(gmo, census)
        for entry in merged:
            path = entry.get("path") or ""
            pop_mac = (
                path.rsplit("/dev_", 1)[-1].replace("_", ":").upper()
                if "/dev_" in path
                else str(entry.get("address") or "").upper()
            )
            if pop_mac:
                entry["fingerprint_rotated_in_round"] = self.pop_fingerprint_rotated(pop_mac)
        return merged

    def _compose_harvest_from_census_only(self) -> List[Dict[str, Any]]:
        merged = self._merge_harvest_by_mac([], self._session_census_as_dicts())
        for entry in merged:
            path = entry.get("path") or ""
            pop_mac = (
                path.rsplit("/dev_", 1)[-1].replace("_", ":").upper()
                if "/dev_" in path
                else str(entry.get("address") or "").upper()
            )
            if pop_mac:
                entry["fingerprint_rotated_in_round"] = self.pop_fingerprint_rotated(pop_mac)
        return merged

    def _snapshot_gmo_devices(self) -> List[Dict[str, Any]]:
        """Build device dicts from GetManagedObjects for this adapter only."""
        try:
            managed = self._object_manager.GetManagedObjects()
        except Exception as exc:  # noqa: BLE001
            print_and_log(f"[!] GetManagedObjects during harvest failed: {exc}", LOG__DEBUG)
            return []

        LAST_HARVEST["objects"] = len(managed)
        LAST_HARVEST["devices"] = sum(1 for path in managed if "/dev_" in str(path))
        prefix = f"{BLUEZ_NAMESPACE}{self.adapter_name}/"
        devices: List[Dict[str, Any]] = []
        for path, interfaces in managed.items():
            path_s = str(path)
            if not path_s.startswith(prefix):
                continue
            if DEVICE_INTERFACE not in interfaces:
                continue
            properties = interfaces[DEVICE_INTERFACE]
            address = str(properties.get("Address", "") or "")
            rssi = properties.get("RSSI") if "RSSI" in properties else None
            if rssi is None and address:
                cached = self.get_captured_rssi(address.upper())
                if cached is not None:
                    rssi = cached
            devices.append(
                build_discovered_device_dict(path_s, properties, rssi=rssi)
            )
        return devices

    def _merge_harvest_by_mac(
        self,
        gmo: List[Dict[str, Any]],
        census: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_mac: Dict[str, Dict[str, Any]] = {}
        for entry in gmo:
            mac = str(entry.get("address") or "").upper()
            if mac:
                by_mac[mac] = dict(entry)
        for entry in census:
            mac = str(entry.get("address") or "").upper()
            if not mac:
                continue
            if mac not in by_mac:
                by_mac[mac] = dict(entry)
                continue
            existing = by_mac[mac]
            # Prefer non-empty advertisement payloads; prefer fresher census rssi.
            if not existing.get("manufacturer_data") and entry.get("manufacturer_data"):
                existing["manufacturer_data"] = dict(entry["manufacturer_data"])
            if not existing.get("service_data") and entry.get("service_data"):
                existing["service_data"] = dict(entry["service_data"])
            if existing.get("rssi") is None and entry.get("rssi") is not None:
                existing["rssi"] = entry["rssi"]
            if not existing.get("uuids") and entry.get("uuids"):
                existing["uuids"] = list(entry["uuids"])
            if not existing.get("name") and entry.get("name"):
                existing["name"] = entry["name"]
            if not existing.get("alias") and entry.get("alias"):
                existing["alias"] = entry["alias"]
            if not existing.get("path") and entry.get("path"):
                existing["path"] = entry["path"]
        return list(by_mac.values())

    # ------------------------------------------------------------------
    # R2 session census
    # ------------------------------------------------------------------
    def _clear_session_devices(self) -> None:
        self._ensure_session_state()
        with self._session_lock:
            self._session_devices.clear()

    def upsert_session_device_properties(self, path: str, props: dict) -> None:
        """Upsert Device1 properties into the session census (last-shot mfr/sd)."""
        self._ensure_session_state()
        if not self._session_capturing or not isinstance(props, dict):
            return
        if not (path.startswith("/org/bluez/") and "/dev_" in path):
            return
        try:
            mac = path.split("/dev_")[-1].replace("_", ":").upper()
        except (AttributeError, IndexError):
            return
        if not mac:
            return
        now = time.time()
        with self._session_lock:
            entry = self._session_devices.get(mac)
            if entry is None:
                # Seed from whatever props we have (may be partial on PropertiesChanged).
                seed_props = dict(props)
                if "Address" not in seed_props:
                    seed_props["Address"] = mac
                built = build_discovered_device_dict(path, seed_props)
                built["_first_seen_ts"] = now
                built["_last_seen_ts"] = now
                built["_removed"] = False
                self._session_devices[mac] = built
                entry = built
            else:
                entry["_last_seen_ts"] = now
                entry["_removed"] = False
                entry["path"] = path
                if "Address" in props:
                    entry["address"] = props.get("Address") or entry.get("address")
                if "Name" in props:
                    entry["name"] = props.get("Name") or entry.get("name") or ""
                if "Alias" in props:
                    entry["alias"] = props.get("Alias") or entry.get("alias") or ""
                if "AddressType" in props:
                    entry["address_type"] = props.get("AddressType")
                if "Class" in props:
                    entry["device_class"] = props.get("Class")
                if "UUIDs" in props:
                    entry["uuids"] = [
                        str(u).strip().upper() for u in (props.get("UUIDs") or [])
                    ]
                if "Connected" in props:
                    entry["connected"] = bool(props.get("Connected"))
                if "Paired" in props:
                    entry["paired"] = bool(props.get("Paired"))
                if "Bonded" in props:
                    entry["bonded"] = bool(props.get("Bonded"))
                if "RSSI" in props and props.get("RSSI") is not None:
                    try:
                        entry["rssi"] = int(props["RSSI"])
                    except (TypeError, ValueError):
                        pass
                if "ManufacturerData" in props:
                    try:
                        entry["manufacturer_data"] = {
                            int(k): bytes(v)
                            for k, v in dict(props.get("ManufacturerData") or {}).items()
                        }
                    except (TypeError, ValueError):
                        pass
                if "ServiceData" in props:
                    try:
                        entry["service_data"] = {
                            str(k): bytes(v)
                            for k, v in dict(props.get("ServiceData") or {}).items()
                        }
                    except (TypeError, ValueError):
                        pass
                if "AdvertisingFlags" in props and props.get("AdvertisingFlags") is not None:
                    try:
                        entry["advertising_flags"] = bytes(props["AdvertisingFlags"])
                    except (TypeError, ValueError):
                        pass
                if "AdvertisingData" in props and props.get("AdvertisingData") is not None:
                    try:
                        entry["advertising_data"] = {
                            int(k): bytes(v)
                            for k, v in dict(props["AdvertisingData"]).items()
                        }
                    except (TypeError, ValueError):
                        pass

    def mark_session_device_removed(self, path: str) -> None:
        """Keep census row after InterfacesRemoved (STOP_CLEARS); do not delete."""
        self._ensure_session_state()
        if not self._session_capturing:
            return
        if not (path.startswith("/org/bluez/") and "/dev_" in path):
            return
        try:
            mac = path.split("/dev_")[-1].replace("_", ":").upper()
        except (AttributeError, IndexError):
            return
        with self._session_lock:
            entry = self._session_devices.get(mac)
            if entry is not None:
                entry["_removed"] = True
                entry["_last_seen_ts"] = time.time()

    def _session_census_as_dicts(self) -> List[Dict[str, Any]]:
        self._ensure_session_state()
        with self._session_lock:
            out: List[Dict[str, Any]] = []
            for entry in self._session_devices.values():
                cleaned = {
                    k: v
                    for k, v in entry.items()
                    if not str(k).startswith("_")
                }
                out.append(cleaned)
            return out

    def _capture_rssi_from_signal(self, mac_address: str, rssi: int) -> None:
        """Store RSSI value from PropertiesChanged signal in cache.
        
        Args:
            mac_address: Device MAC address (uppercase with colons)
            rssi: RSSI value in dBm
        """
        with self._rssi_cache_lock:
            self._rssi_cache[mac_address] = rssi

    def get_captured_rssi(self, mac_address: str) -> Optional[int]:
        """Retrieve cached RSSI value for a device.
        
        Args:
            mac_address: Device MAC address (uppercase with colons)
            
        Returns:
            Cached RSSI value in dBm, or None if not available
        """
        with self._rssi_cache_lock:
            return self._rssi_cache.get(mac_address)

    def clear_rssi_cache(self) -> None:
        """Clear the RSSI cache."""
        with self._rssi_cache_lock:
            self._rssi_cache.clear()

    # ------------------------------------------------------------------
    # LR-2c: intra-round advertisement-fingerprint rotation tracking
    # ------------------------------------------------------------------
    def _capture_adv_fingerprint(
        self, mac_address: str, kind: str, key: Any, payload: bytes
    ) -> None:
        """Record an advertisement payload and flag same-length rotations.

        Called from the signal path (``PropertiesChanged``/``InterfacesAdded``) for
        each ServiceData / ManufacturerData element seen during discovery. A rotation
        is flagged when a previously-seen payload for the same ``(kind, key)`` is
        superseded by a *same-length but differing* payload — the exact predicate the
        per-round census merge uses (``_merge_svc_data``/``_merge_mfr_data``), applied
        here to the sub-round signal stream so a rotation that reverts before the
        end-of-round snapshot is still detected. Strictly longer/shorter payloads are
        left to the snapshot-based merge (they are not a same-length rotation). The
        caller gates on ``is_discovery_active``; malformed payloads are ignored.
        """
        if not isinstance(payload, (bytes, bytearray)):
            return
        payload = bytes(payload)
        fp_key = (kind, key)
        with self._adv_fp_lock:
            last = self._adv_fp_last.setdefault(mac_address, {})
            prev = last.get(fp_key)
            if prev is not None and len(prev) == len(payload) and prev != payload:
                self._adv_fp_rotated.add(mac_address)
            last[fp_key] = payload

    def pop_fingerprint_rotated(self, mac_address: str) -> bool:
        """Return (and clear) whether *mac_address* rotated a fingerprint this round."""
        with self._adv_fp_lock:
            if mac_address in self._adv_fp_rotated:
                self._adv_fp_rotated.discard(mac_address)
                return True
            return False

    def _clear_adv_fingerprints(self) -> None:
        """Reset the intra-round fingerprint tracker (called at start_discovery)."""
        with self._adv_fp_lock:
            self._adv_fp_last.clear()
            self._adv_fp_rotated.clear()
