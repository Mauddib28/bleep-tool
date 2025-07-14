"""Passive BLE scan operation – native implementation only.

The function now relies exclusively on the refactored `bleep.dbuslayer` stack
and requires GI/PyGObject + BlueZ at runtime.  All legacy monolith fallback
code has been removed.
"""

from __future__ import annotations

# Attempt to import the new dbuslayer stack.  If *gi* bindings / BlueZ are not
# available we abort early – historic monolith fallback has been removed.

try:
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    _HAS_NATIVE_STACK = True
except Exception:  # noqa: BLE001 – missing GI bindings / BlueZ runtime
    _HAS_NATIVE_STACK = False

from bleep.core.log import print_and_log, LOG__GENERAL, LOG__DEBUG


def _native_scan(device: str | None, timeout: int, transport: str = "auto") -> int:
    """Perform a simple LE discovery using the refactored stack."""

    adapter = _Adapter()
    
    # Apply transport filter if explicitly requested
    if transport.lower() in {"le", "bredr"}:
        adapter.set_discovery_filter({"Transport": transport.lower()})
    
    manager = adapter.create_device_manager()

    # In this first rewrite we ignore *device* filtering; higher-level code
    # expects a *passive* broadcast scan.
    manager.start_discovery(timeout=timeout)
    manager.run()  # blocks until timeout expires

    raw = adapter.get_discovered_devices()

    if not raw:
        print_and_log("[*] No BLE devices discovered", LOG__GENERAL)
    else:
        print_and_log(f"[*] Discovered {len(raw)} device(s)", LOG__GENERAL)

        for entry in raw:
            addr = entry.get("address", "??")
            name = entry.get("name") or entry.get("alias") or "?"
            rssi_val = entry.get("rssi")
            rssi_disp = rssi_val if rssi_val is not None else "?"
            print_and_log(f"  {addr}  Name={name}  RSSI={rssi_disp}", LOG__GENERAL)

    return 0


# ---------------------------------------------------------------------------
# Legacy monolith loader *removed* – the following helpers have been deleted:
#   * _load_monolith()
#   * _legacy_scan()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Back-compat helper wrappers – thin shims around *passive_scan*
# ---------------------------------------------------------------------------

def create_and_return__bluetooth_scan__discovered_devices(
    *, timeout: int = 10, adapter_name: str | None = None, transport: str = "auto"
) -> list[dict]:
    """Return the list of discovered device dictionaries (address, name, rssi,…).

    This preserves the public contract of the legacy helper while relying solely
    on the refactored *dbuslayer* stack.  **No monolith code is imported.**
    """
    from bleep.dbuslayer.adapter import system_dbus__bluez_adapter as _Adapter

    adapter = _Adapter(adapter_name) if adapter_name else _Adapter()

    # Apply transport filter if explicitly requested
    if transport.lower() in {"le", "bredr"}:
        adapter.set_discovery_filter({"Transport": transport.lower()})

    manager = adapter.create_device_manager()
    manager.start_discovery(timeout=timeout)
    manager.run()

    return adapter.get_discovered_devices()


def create_and_return__bluetooth_scan__discovered_devices__specific_adapter(
    bluetooth_adapter: str, *, timeout: int = 10, transport: str = "auto"
) -> list[dict]:
    """Explicit adapter variant kept for callers that pass *hciX* manually."""
    return create_and_return__bluetooth_scan__discovered_devices(
        timeout=timeout,
        adapter_name=bluetooth_adapter,
        transport=transport,
    )


# Public export list -----------------------------------------------------------------------------
__all__ = [
    "passive_scan",
    "create_and_return__bluetooth_scan__discovered_devices",
    "create_and_return__bluetooth_scan__discovered_devices__specific_adapter",
]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def passive_scan(device: str | None = None, timeout: int = 60, transport: str = "auto"):  # noqa: D401
    """Execute a passive BLE scan.

    Parameters
    ----------
    device
        Optional MAC address to target (ignored in native scan for now).
    timeout
        Duration in seconds for the discovery main-loop.
    transport
        Bluetooth transport filter: "auto" (default), "le" (Low Energy), or "bredr" (Classic).
    """

    if not _HAS_NATIVE_STACK:
        raise RuntimeError(
            "PyGObject/BlueZ bindings not available – passive_scan now requires "
            "a native environment after monolith fallback removal."
        )

    return _native_scan(device, timeout, transport)
