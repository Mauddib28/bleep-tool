"""CLI mode for GATT Server management (BZ-4).

Wraps :mod:`bleep.dbuslayer.gatt_server` to let users publish local BLE GATT
services that remote devices can discover, connect to, and interact with.

Sub-actions
-----------
* ``start`` — register a GATT application and serve until Ctrl-C or
  ``--duration`` expires.
"""

from __future__ import annotations

import signal
import time

import dbus
import dbus.mainloop.glib

from bleep.core.log import get_logger, print_and_log, LOG__GENERAL
from bleep.dbuslayer.gatt_server import (
    GattApplication,
    GattCharacteristicSkeleton,
    GattServerManager,
    GattServiceSkeleton,
)

logger = get_logger(__name__)

_output_ctx = None

_DEFAULT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
_READ_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"
_WRITE_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef2"
_NOTIFY_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef3"


def _resolve_adapter_path(adapter: str) -> str:
    if adapter.startswith("/"):
        return adapter
    return f"/org/bluez/{adapter}"


# ---------------------------------------------------------------------------
# Example characteristic subclasses
# ---------------------------------------------------------------------------

class _StaticReadChar(GattCharacteristicSkeleton):
    """Returns a fixed value on read."""

    def __init__(self, bus, index, service, value: bytes):
        super().__init__(bus, index, _READ_CHAR_UUID, ["read"], service)
        self._value = value

    @dbus.service.method(
        "org.bluez.GattCharacteristic1", in_signature="a{sv}", out_signature="ay"
    )
    def ReadValue(self, options):
        return dbus.Array([dbus.Byte(b) for b in self._value], signature="y")


class _LogWriteChar(GattCharacteristicSkeleton):
    """Logs written values to console/output."""

    def __init__(self, bus, index, service):
        super().__init__(bus, index, _WRITE_CHAR_UUID, ["write"], service)

    @dbus.service.method("org.bluez.GattCharacteristic1", in_signature="aya{sv}")
    def WriteValue(self, value, options):
        raw = bytes(value)
        print_and_log(
            f"[GATT] Write received: {raw.hex()} ({raw!r})", LOG__GENERAL,
        )
        if _output_ctx and _output_ctx.is_json:
            _output_ctx.emit_result({
                "event": "gatt_write",
                "uuid": _WRITE_CHAR_UUID,
                "value_hex": raw.hex(),
            })


class _TickNotifyChar(GattCharacteristicSkeleton):
    """Sends an incrementing 2-byte counter every 2 seconds."""

    def __init__(self, bus, index, service):
        super().__init__(bus, index, _NOTIFY_CHAR_UUID, ["notify"], service)
        self._counter = 0
        self._timer_id = None

    @dbus.service.method("org.bluez.GattCharacteristic1")
    def StartNotify(self):
        from gi.repository import GLib
        if self.notifying:
            return
        self.notifying = True
        self._timer_id = GLib.timeout_add(2000, self._tick)
        print_and_log(
            f"[GATT] Notifications started for {_NOTIFY_CHAR_UUID}", LOG__GENERAL,
        )

    @dbus.service.method("org.bluez.GattCharacteristic1")
    def StopNotify(self):
        from gi.repository import GLib
        if not self.notifying:
            return
        self.notifying = False
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        print_and_log(
            f"[GATT] Notifications stopped for {_NOTIFY_CHAR_UUID}", LOG__GENERAL,
        )

    def _tick(self):
        if not self.notifying:
            return False
        val = self._counter.to_bytes(2, "little")
        self.send_notification(val)
        self._counter = (self._counter + 1) % 0xFFFF
        return True


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------

def _build_default_app(bus, args):
    """Build a :class:`GattApplication` from CLI *args*."""
    app = GattApplication(bus)

    service_uuids = args.uuid or [_DEFAULT_SERVICE_UUID]
    read_hex = args.read_value or "48656c6c6f"  # "Hello"
    static_value = bytes.fromhex(read_hex)

    for idx, uuid in enumerate(service_uuids):
        svc = GattServiceSkeleton(bus, idx, uuid, primary=True)
        svc.add_characteristic(_StaticReadChar(bus, 0, svc, static_value))
        svc.add_characteristic(_LogWriteChar(bus, 1, svc))
        svc.add_characteristic(_TickNotifyChar(bus, 2, svc))
        app.add_service(svc)

    return app


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_start(args) -> int:
    """``bleep gatt-server start``"""
    from gi.repository import GLib

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter_path = _resolve_adapter_path(args.adapter)

    try:
        mgr = GattServerManager(bus, adapter_path)
    except dbus.exceptions.DBusException as e:
        print_and_log(
            f"[!] Cannot access GattManager1 on {adapter_path}: {e}", LOG__GENERAL
        )
        return 1

    app = _build_default_app(bus, args)

    ok = mgr.register_application(app)
    if not ok:
        print_and_log(
            "[!] Failed to register GATT application with BlueZ", LOG__GENERAL
        )
        app.remove_all()
        return 1

    service_uuids = args.uuid or [_DEFAULT_SERVICE_UUID]
    print_and_log(f"[+] GATT application registered at {app.path}", LOG__GENERAL)
    for uuid in service_uuids:
        print_and_log(f"    Service: {uuid}", LOG__GENERAL)
    print_and_log("    Characteristics per service:", LOG__GENERAL)
    print_and_log("      [read]   ...def1  — static value", LOG__GENERAL)
    print_and_log("      [write]  ...def2  — logs writes", LOG__GENERAL)
    print_and_log("      [notify] ...def3  — counter tick every 2 s", LOG__GENERAL)
    print_and_log("", LOG__GENERAL)
    print_and_log("[*] Serving — Ctrl-C to stop.", LOG__GENERAL)

    if _output_ctx and _output_ctx.is_json:
        _output_ctx.emit_result({
            "event": "gatt_server_started",
            "path": app.path,
            "service_uuids": list(service_uuids),
        })

    loop = GLib.MainLoop()

    def _on_sigint(*_a):
        loop.quit()

    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)

    if args.duration:
        GLib.timeout_add_seconds(args.duration, loop.quit)

    start_ts = time.monotonic()
    loop.run()
    elapsed = time.monotonic() - start_ts

    mgr.unregister_application(app)
    app.remove_all()

    print_and_log(f"\n[*] GATT server stopped after {elapsed:.1f}s", LOG__GENERAL)
    if _output_ctx and _output_ctx.is_json:
        _output_ctx.emit_result({
            "event": "gatt_server_stopped",
            "elapsed_s": round(elapsed, 1),
        })
    return 0


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run(args, output=None) -> int:
    """Execute gatt-server mode with parsed args and optional OutputContext."""
    global _output_ctx
    from bleep.core.output import OutputContext
    from bleep.core.log import set_output_mode

    if output is None:
        output = OutputContext()

    _output_ctx = output
    set_output_mode(output.mode)

    return handle_gatt_server(args)


def handle_gatt_server(args) -> int:
    """Entry point called from cli.py dispatch."""
    action = getattr(args, "gs_action", None)
    if not action:
        print_and_log("Usage: bleep gatt-server {start}", LOG__GENERAL)
        print_and_log(
            "  start   Register GATT services and serve until Ctrl-C", LOG__GENERAL
        )
        return 1

    if action == "start":
        return _handle_start(args)

    print_and_log(f"[!] Unknown gatt-server action: {action}", LOG__GENERAL)
    return 1
