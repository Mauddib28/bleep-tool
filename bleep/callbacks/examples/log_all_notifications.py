"""Example callback: log every BLE notification to stdout."""

from bleep.callbacks.base import BleepCallback
from bleep.signals.capture_config import SignalType


class LogAllNotifications(BleepCallback):
    name = "log_all_notifications"
    trigger = SignalType.NOTIFICATION

    def execute(self, context):
        mac = context.get("device_mac", "?")
        char = context.get("char_uuid", "?")
        value = context.get("value", b"")
        if isinstance(value, (bytes, bytearray)):
            display = value.hex()
        else:
            display = str(value)
        print(f"[notify] {mac} char={char} value={display}")
