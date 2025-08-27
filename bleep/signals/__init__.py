"""Signal capture and processing system for BLEEP.

This package provides a structured approach to capturing, filtering, and processing
Bluetooth signals (notifications, indications, property changes) with configurable
routing and persistent storage of configurations.
"""

from bleep.signals.capture_config import (
    SignalCaptureConfig,
    SignalFilter,
    SignalRoute,
    SignalAction,
    SignalType,
    ActionType,
    load_config,
    save_config,
    create_default_config,
    list_configs,
)

from bleep.signals.router import (
    SignalRouter,
    ActionExecutor,
    get_router,
    set_router,
    process_signal,
    process_signal_capture,
    register_callback,
)

from bleep.signals.integration import (
    integrate_with_bluez_signals,
    patch_signal_capture_class,
)

__all__ = [
    # Configuration classes
    "SignalCaptureConfig",
    "SignalFilter", 
    "SignalRoute",
    "SignalAction",
    "SignalType",
    "ActionType",
    
    # Configuration functions
    "load_config",
    "save_config",
    "create_default_config",
    "list_configs",
    
    # Router classes
    "SignalRouter",
    "ActionExecutor",
    
    # Router functions
    "get_router",
    "set_router",
    "process_signal",
    "process_signal_capture",
    "register_callback",
    
    # Integration functions
    "integrate_with_bluez_signals",
    "patch_signal_capture_class",
]
