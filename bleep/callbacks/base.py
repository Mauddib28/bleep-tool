"""Base class for user-defined BLEEP callbacks.

Users create subclasses of :class:`BleepCallback` and drop them into
``~/.config/bleep/callbacks/`` (or a custom directory).  The loader in
:mod:`bleep.callbacks` discovers and registers them automatically via the
existing :func:`bleep.signals.router.register_callback` infrastructure.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, Optional

from bleep.signals.capture_config import SignalType


class BleepCallback(abc.ABC):
    """Base class for all user-supplied BLEEP callbacks.

    Subclasses must set :attr:`name` and :attr:`trigger`, and implement
    :meth:`execute`.
    """

    name: str = ""
    """Short identifier used as the callback registration key."""

    trigger: SignalType = SignalType.ANY
    """Which signal type activates this callback."""

    @abc.abstractmethod
    def execute(self, context: Dict[str, Any]) -> None:
        """Called when a matching signal is captured.

        Parameters
        ----------
        context : dict
            Signal context with keys such as ``signal_type``, ``path``,
            ``device_mac``, ``value``, ``timestamp``, etc.
        """

    # ------------------------------------------------------------------
    # Optional lifecycle hooks
    # ------------------------------------------------------------------

    def on_load(self) -> None:
        """Called once after the callback is discovered and registered."""

    def on_unload(self) -> None:
        """Called when the callback is unregistered."""
