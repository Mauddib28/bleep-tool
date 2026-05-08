"""
Startup banner for BLEEP.

The Bluetooth rune (bind rune of Hagall + Bjarkan, Harald Bluetooth's
initials) serves as the 'B' in BLEEP, rendered in pure ASCII alongside
banner3-style lettering for 'LEEP'.
"""

from . import __version__, __author__

# V1-Short-C (tight) — Bluetooth bind-rune B with banner3 LEEP,
# text dead-centred at the crossing point, 2-space gap.
_BANNER = r"""
        |
        | \
        |   \
  \     |     \
    \   |   /  _    ___ ___ ___
      \ | /   | |  | __| __| _ \
        |     | |__| _|| _||  _/
      / | \   |____|___|___|_|
    /   |   \
  /     |     \
        |   /
        | /
        |/
        |
"""

_SUBTITLE = """\
 Bluetooth Landscape Exploration
      & Enumeration Platform
 ---------------------------------
  {version:<14s}{author}
  Explore . Enumerate . Understand
"""

_INTERACTIVE_MODES = frozenset({
    None, "interactive", "debug", "user", "ctf",
    "explore", "aoi", "signal",
})


def print_banner(mode: str | None = None) -> None:
    """Print the BLEEP startup banner.

    Only emits output for interactive/REPL modes; single-shot CLI
    commands (scan, connect, gatt-enum, …) stay quiet so they can be
    piped or scripted without noise.

    Parameters
    ----------
    mode:
        The ``args.mode`` value from the CLI parser.  Pass ``None`` for
        the default interactive mode.
    """
    if mode not in _INTERACTIVE_MODES:
        return

    print(_BANNER.lstrip("\n").rstrip())
    print(_SUBTITLE.format(version=f"v{__version__}", author=__author__))
