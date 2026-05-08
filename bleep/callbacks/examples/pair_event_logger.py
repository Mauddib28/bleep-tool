"""Example callback: log pair-start and pair-complete events."""

from bleep.callbacks.base import BleepCallback
from bleep.signals.capture_config import SignalType


class PairEventLogger(BleepCallback):
    name = "pair_event_logger"
    trigger = SignalType.ANY

    def execute(self, context):
        sig_type = context.get("signal_type")
        if sig_type in (SignalType.PAIR_START, SignalType.PAIR_COMPLETE):
            mac = context.get("device_mac", "?")
            print(f"[pair] {sig_type.value}: {mac}")
