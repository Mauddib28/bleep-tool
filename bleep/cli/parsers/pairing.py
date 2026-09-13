"""Pairing and agent subparsers."""

import argparse


def _add_pair_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Attach the canonical pairing option set to *parser*.

    Single source of truth shared by the CLI ``pair`` subparser
    (:func:`register`) and the debug-shell ``pair`` command
    (``bleep.modes.debug_pairing.cmd_pair``) so the two cannot drift — in
    particular this is how the debug shell gains ``--no-connect`` /
    ``--no-trust`` parity with the CLI.

    Surface-specific options are added by each caller and intentionally NOT
    included here: the target MAC positional (CLI ``address`` vs. debug
    ``mac``), the CLI-only ``--adapter``, and the debug-only ``--test`` PoC
    flag.
    """
    parser.add_argument("--pin", default=None,
                        help="PIN code for legacy pairing (default: 0000)")
    parser.add_argument("--passkey", type=int, default=None,
                        help="Numeric passkey for SSP pairing (0–999999)")
    parser.add_argument("--interactive", action="store_true",
                        help="Prompt for PIN / passkey / confirmation at runtime")
    parser.add_argument("--check", action="store_true",
                        help="Check pairing state only – do not pair")
    parser.add_argument("--reset", action="store_true",
                        help="Force-remove existing bond before pairing")
    parser.add_argument("--no-connect", action="store_true",
                        help="Pair only – do not attempt a post-pair connection")
    parser.add_argument("--no-trust", action="store_true",
                        help="Do not set the device as trusted after pairing")
    parser.add_argument("--brute", action="store_true",
                        help="Brute-force PIN codes")
    parser.add_argument("--passkey-brute", action="store_true",
                        help="Brute-force numeric passkeys")
    parser.add_argument("--range", default=None, dest="pin_range",
                        help="PIN/passkey range, e.g. 0000-9999 or 0-999999")
    parser.add_argument("--pin-list", default=None,
                        help="File containing one PIN per line")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Delay between brute-force attempts (s)")
    parser.add_argument("--max-attempts", type=int, default=0,
                        help="Maximum brute-force attempts (0 = unlimited)")
    parser.add_argument("--lockout-cooldown", type=float, default=60.0,
                        help="Cooldown after lockout detection (s)")
    parser.add_argument("--max-lockout-retries", type=int, default=3,
                        help="Maximum retries after lockout")
    parser.add_argument("--probe", action="store_true",
                        help="Discover auth method by cycling IO capabilities")
    parser.add_argument("--cap", default="KeyboardDisplay",
                        choices=["NoInputNoOutput", "DisplayOnly", "DisplayYesNo",
                                 "KeyboardOnly", "KeyboardDisplay"],
                        help="BlueZ IO capability for the pairing agent")
    parser.add_argument("--timeout", type=int, default=60,
                        help="Pairing timeout in seconds")
    return parser


def register(subparsers, _subparser_map):
    pair_parser = subparsers.add_parser("pair", help="Pair with a Bluetooth device")
    pair_parser.add_argument("address", help="Target Bluetooth MAC address")
    _add_pair_arguments(pair_parser)
    pair_parser.add_argument("--adapter", default="hci0",
                             help="Adapter name (default: hci0)")

    agent_parser = subparsers.add_parser("agent", help="Run pairing agent")
    agent_parser.add_argument("--mode", dest="agent_mode",
                              choices=["simple", "interactive", "enhanced", "pairing"],
                              default="simple", help="Agent mode: simple, interactive, enhanced, or pairing")
    agent_parser.add_argument("--cap", choices=["none", "display", "yesno", "keyboard", "kbdisp"],
                              default="none", help="Agent capabilities: none, display, yesno, keyboard, kbdisp")
    agent_parser.add_argument("--default", action="store_true",
                              help="Request as default agent")
    agent_parser.add_argument("--no-auto-accept", dest="auto_accept", action="store_false",
                              default=True,
                              help="Prompt for pairing confirmation instead of auto-accepting (for enhanced and pairing agents)")
    agent_parser.add_argument("--pair", metavar="MAC",
                              help="Pair with a device (only in pairing mode)")
    agent_parser.add_argument("--trust", metavar="MAC",
                              help="Set a device as trusted")
    agent_parser.add_argument("--untrust", metavar="MAC",
                              help="Set a device as untrusted")
    agent_parser.add_argument("--list-trusted", action="store_true",
                              help="List all trusted devices")
    agent_parser.add_argument("--list-bonded", action="store_true",
                              help="List all bonded devices (with stored keys)")
    agent_parser.add_argument("--remove-bond", metavar="MAC",
                              help="Remove bonding information for a device")
    agent_parser.add_argument("--storage-path",
                              help="Path to store bonding information")
    agent_parser.add_argument("--timeout", type=int, default=30,
                              help="Timeout for pairing operations (seconds)")
    agent_parser.add_argument("--status", action="store_true",
                              help="Check BLEEP agent registration status")
    agent_parser.add_argument("--adapter", default="hci0", help="Adapter name (default: hci0)")
