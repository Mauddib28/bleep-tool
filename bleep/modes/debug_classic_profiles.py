"""Classic Bluetooth profile commands for debug mode.

Commands: cpan (PAN), cspp (SPP), cprofiles (list Device1.UUIDs),
cprofile (connect/disconnect a specific profile by UUID).

Split from ``debug_classic_data.py`` to keep file sizes manageable.
"""

from __future__ import annotations

from typing import List, Optional

from bleep.modes.debug_state import DebugState


# ---------------------------------------------------------------------------
# cprofiles – list Device1.UUIDs with resolved names
# ---------------------------------------------------------------------------


def cmd_cprofiles(args: List[str], state: DebugState) -> None:
    """List all profiles (UUIDs) advertised by the connected Classic device."""
    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    device = state.current_device
    uuids = device.get_supported_profiles()
    if not uuids:
        print("[*] No UUIDs advertised by this device")
        return

    from bleep.bt_ref.utils import get_name_from_uuid

    connected = device.is_connected()
    print(f"[*] Profiles for {device.mac_address} (connected={connected}):\n")
    print(f"  {'UUID':<40} {'Name'}")
    print(f"  {'─' * 40} {'─' * 30}")
    for uuid in sorted(uuids, key=str.lower):
        name = get_name_from_uuid(uuid) or "(unknown)"
        print(f"  {uuid:<40} {name}")
    print(f"\n  Total: {len(uuids)} profile(s)")


# ---------------------------------------------------------------------------
# cprofile – connect/disconnect a specific profile by UUID
# ---------------------------------------------------------------------------


def cmd_cprofile(args: List[str], state: DebugState) -> None:
    """Connect or disconnect a profile on the current Classic device."""
    if not args:
        print("Usage:")
        print("  cprofile connect <UUID>     - Connect to a specific profile")
        print("  cprofile disconnect <UUID>  - Disconnect a specific profile")
        return

    subcmd = args[0].lower()

    if state.current_mode != "classic" or not state.current_device:
        print("[-] No Classic device connected. Use 'cconnect <mac>' first")
        return

    device = state.current_device

    if subcmd == "connect":
        if len(args) < 2:
            print("[-] UUID required: cprofile connect <UUID>")
            return
        uuid = args[1]
        try:
            device.connect_profile(uuid)
            from bleep.bt_ref.utils import get_name_from_uuid
            name = get_name_from_uuid(uuid) or uuid
            print(f"[+] Connected profile: {name}")
        except Exception as exc:
            print(f"[-] ConnectProfile failed: {exc}")

    elif subcmd == "disconnect":
        if len(args) < 2:
            print("[-] UUID required: cprofile disconnect <UUID>")
            return
        uuid = args[1]
        try:
            device.disconnect_profile(uuid)
            from bleep.bt_ref.utils import get_name_from_uuid
            name = get_name_from_uuid(uuid) or uuid
            print(f"[+] Disconnected profile: {name}")
        except Exception as exc:
            print(f"[-] DisconnectProfile failed: {exc}")

    else:
        print(f"[-] Unknown sub-command: {subcmd}")
        print("    Use: connect, disconnect")


# ---------------------------------------------------------------------------
# cpan – Personal Area Networking
# ---------------------------------------------------------------------------


def cmd_cpan(args: List[str], state: DebugState) -> None:
    """Connect/disconnect PAN networking or register a local PAN server.

    The ``NetworkClient`` / ``NetworkServer`` objects are retained on
    ``state.pan_client`` / ``state.pan_server`` so the D-Bus bus name
    stays alive for the duration of the debug session.  BlueZ's
    ``NetworkServer1.Register()`` tears down the server when the calling
    process exits the bus (confirmed in ``profiles/network/server.c``).
    """
    if not args:
        print("Usage:")
        print("  cpan connect [role]             - Connect to PAN device (nap/panu/gn)")
        print("  cpan disconnect                 - Disconnect PAN")
        print("  cpan status                     - Show Network1 properties")
        print("  cpan server register [role] [bridge] - Register PAN server")
        print("  cpan server unregister [role]   - Unregister PAN server")
        return

    subcmd = args[0].lower()

    if subcmd in ("connect", "disconnect", "status"):
        if state.current_mode != "classic" or not state.current_device:
            print("[-] No Classic device connected. Use 'cconnect <mac>' first")
            return
        mac = state.current_device.mac_address

    if subcmd == "connect":
        role = args[1].lower() if len(args) > 1 else "nap"
        try:
            from bleep.dbuslayer.network import NetworkClient
            from bleep.core.log import print_and_log, LOG__GENERAL

            print_and_log(f"[PAN] Connecting to {mac} as {role}", LOG__GENERAL)
            client = NetworkClient(mac)
            iface = client.connect(role)
            state.pan_client = client
            print_and_log(f"[PAN] Connected – interface {iface}", LOG__GENERAL)
            print(f"[+] PAN connected – interface {iface}")
        except Exception as exc:
            state.pan_client = None
            print(f"[-] PAN connect failed: {exc}")

    elif subcmd == "disconnect":
        try:
            if state.pan_client is not None:
                state.pan_client.disconnect()
                state.pan_client = None
                print("[+] PAN disconnected")
            else:
                from bleep.ble_ops.classic.pan import disconnect as pan_disconnect
                pan_disconnect(mac)
                print("[+] PAN disconnected")
        except Exception as exc:
            print(f"[-] PAN disconnect failed: {exc}")

    elif subcmd == "status":
        try:
            if state.pan_client is not None:
                info = state.pan_client.status()
            else:
                from bleep.ble_ops.classic.pan import status as pan_status
                info = pan_status(mac)
            print(f"  Connected : {info.get('connected', False)}")
            print(f"  Interface : {info.get('interface') or '(none)'}")
            print(f"  UUID/Role : {info.get('uuid') or '(none)'}")
        except Exception as exc:
            print(f"[-] PAN status failed: {exc}")

    elif subcmd == "server":
        if len(args) < 2:
            print("Usage: cpan server register|unregister [role] [bridge]")
            return
        action = args[1].lower()
        if action == "register":
            role = args[2].lower() if len(args) > 2 else "nap"
            bridge = args[3] if len(args) > 3 else "pan0"
            try:
                from bleep.dbuslayer.network import NetworkServer
                from bleep.core.log import print_and_log, LOG__GENERAL

                print_and_log(
                    f"[PAN] Registering server role={role} bridge={bridge}",
                    LOG__GENERAL,
                )
                server = NetworkServer()
                server.register(role, bridge)
                state.pan_server = server
                print_and_log(
                    f"[PAN] Server registered (role={role}, bridge={bridge})",
                    LOG__GENERAL,
                )
                print(f"[+] PAN server registered (role={role}, bridge={bridge})")
            except Exception as exc:
                state.pan_server = None
                print(f"[-] PAN server register failed: {exc}")
        elif action == "unregister":
            role = args[2].lower() if len(args) > 2 else "nap"
            try:
                if state.pan_server is not None:
                    state.pan_server.unregister(role)
                    state.pan_server = None
                else:
                    from bleep.ble_ops.classic.pan import unregister_server
                    unregister_server(role)
                print(f"[+] PAN server unregistered (role={role})")
            except Exception as exc:
                print(f"[-] PAN server unregister failed: {exc}")
        else:
            print(f"[-] Unknown server action: {action}")
            print("    Use: register, unregister")

    else:
        print(f"[-] Unknown PAN sub-command: {subcmd}")
        print("    Use: connect, disconnect, status, server")


# ---------------------------------------------------------------------------
# cspp – Serial Port Profile registration
# ---------------------------------------------------------------------------


def cmd_cspp(args: List[str], state: DebugState) -> None:
    """Register/unregister an SPP profile; incoming connections feed csend/crecv."""
    if not args:
        print("Usage:")
        print("  cspp register [--channel N] [--name NAME] [--role server|client]")
        print("                [--auth | --no-auth]")
        print("  cspp unregister")
        print("  cspp status")
        print("")
        print("  Once registered, incoming connections set the RFCOMM data socket")
        print("  used by csend/crecv/craw.")
        return

    subcmd = args[0].lower()

    if subcmd == "register":
        from bleep.ble_ops.classic.spp import register as spp_register, is_registered

        if is_registered():
            print("[*] SPP profile already registered")
            return

        channel: Optional[int] = None
        name = "BLEEP SPP"
        role = "server"
        require_auth = True
        i = 1
        while i < len(args):
            if args[i] == "--channel" and i + 1 < len(args):
                try:
                    channel = int(args[i + 1])
                except ValueError:
                    print(f"[-] Invalid channel: {args[i + 1]}")
                    return
                i += 2
            elif args[i] == "--name" and i + 1 < len(args):
                name = args[i + 1]
                i += 2
            elif args[i] == "--role" and i + 1 < len(args):
                role = args[i + 1].lower()
                i += 2
            elif args[i] == "--auth":
                require_auth = True
                i += 1
            elif args[i] == "--no-auth":
                require_auth = False
                i += 1
            else:
                i += 1

        def _on_connect(device_path: str, sock, fd_props: dict) -> None:
            print(f"\n[SPP] Connection from {device_path}")
            if state.rfcomm_sock:
                try:
                    state.rfcomm_sock.close()
                except Exception:
                    pass
            state.rfcomm_sock = sock
            print("[SPP] RFCOMM socket set – use csend/crecv to exchange data")

        def _on_disconnect(device_path: str) -> None:
            print(f"\n[SPP] Disconnection from {device_path}")
            if state.rfcomm_sock:
                try:
                    state.rfcomm_sock.close()
                except Exception:
                    pass
                state.rfcomm_sock = None

        try:
            spp_register(
                channel=channel, name=name, role=role,
                require_auth=require_auth,
                on_connect=_on_connect, on_disconnect=_on_disconnect,
            )
            auth_label = "required" if require_auth else "not required"
            print(f"[+] SPP profile registered (role={role}, channel={channel or 'auto'}, auth={auth_label})")
            print("    Waiting for incoming connections...")
        except Exception as exc:
            print(f"[-] SPP register failed: {exc}")

    elif subcmd == "unregister":
        from bleep.ble_ops.classic.spp import unregister as spp_unregister
        try:
            spp_unregister()
            print("[+] SPP profile unregistered")
        except Exception as exc:
            print(f"[-] SPP unregister failed: {exc}")

    elif subcmd == "status":
        from bleep.ble_ops.classic.spp import status as spp_status
        info = spp_status()
        if not info.get("registered"):
            print("[*] SPP profile not registered")
        else:
            print(f"  Registered : True")
            print(f"  UUID       : {info.get('uuid', '?')}")
            print(f"  Name       : {info.get('name', '?')}")
            print(f"  Role       : {info.get('role', '?')}")
            print(f"  Channel    : {info.get('channel') or 'auto'}")
            print(f"  Path       : {info.get('profile_path', '?')}")
            if state.rfcomm_sock:
                print(f"  Data socket: open (csend/crecv ready)")
            else:
                print(f"  Data socket: not connected yet")

    else:
        print(f"[-] Unknown SPP sub-command: {subcmd}")
        print("    Use: register, unregister, status")
