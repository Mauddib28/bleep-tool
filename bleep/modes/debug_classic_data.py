"""Classic Bluetooth data-exchange commands for debug mode (re-export shim).

This module originally contained all Classic debug commands. They have been
split into focused sub-modules for maintainability:

    debug_classic_rfcomm.py   – copen, csend, crecv, craw  (RFCOMM sockets)
    debug_classic_obex.py     – copp, cmap, cftp, csync, cbip  (OBEX profiles)
    debug_classic_profiles.py – cpan, cspp  (PAN networking, SPP registration)

All public ``cmd_*`` symbols are re-exported here so that existing imports
(e.g. from ``debug.py``) continue to work without modification.
"""

# RFCOMM commands
from bleep.modes.debug_classic_rfcomm import (  # noqa: F401
    cmd_copen,
    cmd_csend,
    cmd_crecv,
    cmd_craw,
)

# OBEX profile commands
from bleep.modes.debug_classic_obex import (  # noqa: F401
    cmd_copp,
    cmd_cmap,
    cmd_cftp,
    cmd_csync,
    cmd_cbip,
)

# PAN & SPP profile commands
from bleep.modes.debug_classic_profiles import (  # noqa: F401
    cmd_cpan,
    cmd_cspp,
)

__all__ = [
    "cmd_copen",
    "cmd_csend",
    "cmd_crecv",
    "cmd_craw",
    "cmd_copp",
    "cmd_cmap",
    "cmd_cftp",
    "cmd_csync",
    "cmd_cbip",
    "cmd_cpan",
    "cmd_cspp",
]
