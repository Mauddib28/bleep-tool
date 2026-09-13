"""CLI dispatch handlers for Classic Bluetooth OBEX profile modes."""
import os
import sys
import shutil


def _warn_if_not_advertised(mac: str, detect_fn, label: str) -> None:
    """Non-fatal SDP pre-flight: warn when *label* is absent from the target's
    service map. Mirrors the interactive layer's ``detect_*_service`` guard so
    CLI users get the same heads-up. Any discovery failure is swallowed — the
    operation still attempts, matching the ``run_map`` precedent.
    """
    try:
        from bleep.ble_ops.classic.sdp import discover_services_sdp, build_svc_map
        svc_map = build_svc_map(discover_services_sdp(mac))
        if not detect_fn(svc_map):
            print(
                f"[!] {label} not advertised by {mac} in SDP – attempting anyway",
                file=sys.stderr,
            )
    except Exception:
        pass


def run_pbap(args, _subparsers=None) -> int:
    repos_arg = (args.repos or "PB").upper()
    from bleep.ble_ops.classic.pbap import pbap_dump_async, DEFAULT_PBAP_REPOS
    repos = DEFAULT_PBAP_REPOS if repos_arg == "ALL" else tuple(r.strip().upper() for r in repos_arg.split(",") if r.strip())

    try:
        result = pbap_dump_async(
            args.address,
            repos=repos,
            vcard_format=args.format,
            auto_auth=args.auto_auth,
            watchdog=args.watchdog,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    base = args.address.replace(":", "").upper()
    single_custom_out = args.out and len(repos) == 1

    for repo, lines in result["data"].items():
        if single_custom_out:
            path = args.out
        else:
            path = f"/tmp/{base}_{repo}.vcf"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
            print(f"[+] Saved {repo} → {path} ({len(lines)} lines)")
        except Exception as exc:
            print(f"[!] Failed to write {path}: {exc}", file=sys.stderr)
    return 0


def run_opp(args, _subparsers=None) -> int:
    if not args.action:
        _subparsers["classic-opp"].print_help()
        return 0

    mac = args.address

    from bleep.ble_ops.classic.opp import detect_opp_service
    _warn_if_not_advertised(mac, detect_opp_service, "OPP (0x1105)")

    if args.action == "send":
        from bleep.ble_ops.classic.opp import send_file
        try:
            result = send_file(mac, args.file, timeout=args.timeout)
            transferred = result.get("transferred", "?")
            size = result.get("size", "?")
            print(f"[+] OPP send complete: {transferred}/{size} bytes transferred")
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "pull":
        from bleep.ble_ops.classic.opp import pull_business_card
        from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
        from pathlib import Path
        if args.out:
            dest = args.out
            use_staging = False
        else:
            filename = f"{mac.replace(':', '').upper()}_card.vcf"
            dest = str(OBEX_STAGING_DIR / filename)
            use_staging = True
        try:
            result_path = pull_business_card(mac, dest, timeout=args.timeout)
            size = result_path.stat().st_size if result_path.exists() else 0
            if use_staging:
                final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                final_dir.mkdir(parents=True, exist_ok=True)
                final = str(final_dir / os.path.basename(str(result_path)))
                if result_path.exists():
                    shutil.move(str(result_path), final)
                print(f"[+] Business card saved → {final} ({size} bytes)")
            else:
                print(f"[+] Business card saved → {result_path} ({size} bytes)")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "exchange":
        from bleep.ble_ops.classic.opp import exchange_business_cards
        from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
        from pathlib import Path
        if args.out:
            dest = args.out
            use_staging = False
        else:
            filename = f"{mac.replace(':', '').upper()}_card.vcf"
            dest = str(OBEX_STAGING_DIR / filename)
            use_staging = True
        try:
            result_path = exchange_business_cards(
                mac, args.file, dest, timeout=args.timeout,
            )
            if use_staging:
                final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                final_dir.mkdir(parents=True, exist_ok=True)
                final = str(final_dir / os.path.basename(str(result_path)))
                if os.path.exists(str(result_path)):
                    shutil.move(str(result_path), final)
                print(f"[+] Exchange complete — remote card saved → {final}")
            else:
                print(f"[+] Exchange complete — remote card saved → {result_path}")
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return 0


def run_map(args, _subparsers=None) -> int:
    if not args.action:
        _subparsers["classic-map"].print_help()
        return 0

    mac = args.address
    inst = args.instance

    # Pre-flight (non-fatal): warn when MAP is not advertised in SDP, matching the
    # interactive layer's detect_map_service guard. Reuses list_mas_instances
    # (SDP-backed); skipped for 'instances' which performs its own discovery.
    if args.action != "instances":
        try:
            from bleep.ble_ops.classic.map import list_mas_instances
            if not list_mas_instances(mac):
                print(
                    f"[!] MAP (0x1132/0x1134) not advertised by {mac} in SDP – "
                    f"attempting anyway",
                    file=sys.stderr,
                )
        except Exception:  # never block the real command on a best-effort check
            pass

    if args.action == "folders":
        from bleep.ble_ops.classic.map import list_folder_tree, collect_leaf_paths
        try:
            tree = list_folder_tree(mac, instance=inst)
            if not tree:
                print("[*] No folders found")
            else:
                def _render_tree(nodes, depth=0):
                    for node in nodes:
                        print(f"{'  ' * depth}{node['name']}/")
                        if node.get("children"):
                            _render_tree(node["children"], depth + 1)
                _render_tree(tree)
                leaves = collect_leaf_paths(tree)
                if leaves:
                    print(f"\nMessage folders: {', '.join(sorted(leaves))}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "list":
        from bleep.ble_ops.classic.map import list_messages
        try:
            filters = {}
            if args.msg_type:
                filters["Type"] = args.msg_type
            msgs = list_messages(
                mac, args.folder,
                filters=filters if filters else None,
                instance=inst,
            )
            if not msgs:
                print(f"[*] No messages in {args.folder}")
            else:
                verbose = getattr(args, "map_verbose", False)
                for m in msgs:
                    handle = (
                        m.get("path", "").rsplit("message", 1)[-1]
                        if "path" in m else "?"
                    )
                    subject = m.get("Subject", "(no subject)")
                    status = m.get("Status", "")
                    if verbose:
                        sender = m.get("Sender", m.get("SenderAddress", ""))
                        dt = m.get("Timestamp", m.get("DateTime", ""))
                        mtype = m.get("Type", "")
                        extra = "  ".join(
                            f for f in [mtype, sender, dt] if f
                        )
                        print(f"  {handle}  {subject}  [{status}]  {extra}")
                    else:
                        print(f"  {handle}  {subject}  [{status}]")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            if "bad request" in str(exc).lower():
                try:
                    from bleep.ble_ops.classic.map import (
                        list_folder_tree, collect_leaf_paths,
                    )
                    tree = list_folder_tree(mac, instance=inst)
                    leaves = collect_leaf_paths(tree)
                    if leaves:
                        print(
                            f"\n[*] '{args.folder}' is not a message folder."
                            " Available message folders:",
                            file=sys.stderr,
                        )
                        for lf in sorted(leaves):
                            print(
                                f"    classic-map {mac} list {lf}",
                                file=sys.stderr,
                            )
                except Exception:
                    pass
            return 1

    elif args.action == "get":
        from bleep.ble_ops.classic.map import get_message
        from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
        from pathlib import Path
        filename = f"map_msg_{args.handle}.txt"
        if args.out:
            dest = args.out
            use_staging = False
        else:
            dest = str(OBEX_STAGING_DIR / filename)
            use_staging = True
        try:
            result = get_message(
                mac, args.handle, dest,
                folder=getattr(args, "folder", ""), instance=inst,
            )
            if use_staging:
                final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                final_dir.mkdir(parents=True, exist_ok=True)
                final = str(final_dir / os.path.basename(str(result)))
                if os.path.exists(str(result)):
                    shutil.move(str(result), final)
                print(f"[+] Message saved → {final}")
            else:
                print(f"[+] Message saved → {result}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "push":
        from bleep.ble_ops.classic.map import push_message
        try:
            push_message(mac, args.file, args.folder, instance=inst)
            print(f"[+] Message pushed to {args.folder}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "inbox":
        from bleep.ble_ops.classic.map import update_inbox
        try:
            update_inbox(mac, instance=inst)
            print("[+] Inbox update requested")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "types":
        from bleep.ble_ops.classic.map import get_supported_types
        try:
            types = get_supported_types(mac, instance=inst)
            if not types:
                print("[*] No supported types reported")
            else:
                print("Supported message types:")
                for t in types:
                    print(f"  {t}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "fields":
        from bleep.ble_ops.classic.map import list_filter_fields
        try:
            fields = list_filter_fields(mac, instance=inst)
            if not fields:
                print("[*] No filter fields reported")
            else:
                print("Available filter fields:")
                for f in fields:
                    print(f"  {f}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "monitor":
        import signal as _signal
        from bleep.ble_ops.classic.map import start_message_monitor, stop_message_monitor

        def _mns_print(path: str, props: dict) -> None:
            print(f"[MNS] {path}")
            for k, v in props.items():
                print(f"      {k}: {v}")

        try:
            start_message_monitor(mac, _mns_print, timeout=args.timeout, instance=inst)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        print("[+] MNS monitor active – press Ctrl+C to stop")
        try:
            _signal.pause()
        except KeyboardInterrupt:
            pass
        finally:
            stop_message_monitor(mac)
            print("\n[+] MNS monitor stopped")

    elif args.action == "instances":
        from bleep.ble_ops.classic.map import list_mas_instances
        try:
            instances_list = list_mas_instances(mac)
            if not instances_list:
                print("[*] No MAS instances found via SDP")
            else:
                print(f"MAS Instances on {mac}:")
                for mi in instances_list:
                    print(f"  Channel {mi['channel']:>3}  {mi.get('name', '')}  (UUID {mi.get('uuid', '?')})")
                print("\nUse --instance <channel> to target a specific MAS.")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return 0


def run_ftp(args, _subparsers=None) -> int:
    if not args.action:
        _subparsers["classic-ftp"].print_help()
        return 0

    mac = args.address

    from bleep.ble_ops.classic.ftp import detect_ftp_service
    _warn_if_not_advertised(mac, detect_ftp_service, "OBEX-FTP (0x1106)")

    if args.action == "ls":
        from bleep.ble_ops.classic.ftp import list_folder
        try:
            entries = list_folder(mac, args.path)
            if not entries:
                print("[*] Folder is empty")
            else:
                print(f"\n{'Type':<8} {'Size':>10}  Name")
                print("-" * 40)
                for e in entries:
                    etype = e.get("Type", "?")
                    esize = e.get("Size", "")
                    ename = e.get("Name", "(unnamed)")
                    if etype == "folder":
                        print(f"{'dir':<8} {'':>10}  {ename}/")
                    else:
                        print(f"{'file':<8} {esize:>10}  {ename}")
                print()
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "get":
        from bleep.ble_ops.classic.ftp import get_file
        from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
        from pathlib import Path
        if args.out:
            dest = args.out
            use_staging = False
        else:
            dest = str(OBEX_STAGING_DIR / args.remote)
            use_staging = True
        try:
            result = get_file(
                mac, args.remote, dest,
                remote_path=args.remote_path, timeout=args.timeout,
            )
            if use_staging:
                final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                final_dir.mkdir(parents=True, exist_ok=True)
                final = str(final_dir / os.path.basename(str(result)))
                if os.path.exists(str(result)):
                    shutil.move(str(result), final)
                print(f"[+] Downloaded → {final}")
            else:
                print(f"[+] Downloaded → {result}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "put":
        from bleep.ble_ops.classic.ftp import put_file
        try:
            result = put_file(
                mac, args.file, args.name,
                remote_path=args.remote_path, timeout=args.timeout,
            )
            transferred = result.get("transferred", "?")
            size = result.get("size", "?")
            print(f"[+] Uploaded: {transferred}/{size} bytes")
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "mkdir":
        from bleep.ble_ops.classic.ftp import create_folder
        try:
            create_folder(mac, args.name, remote_path=args.remote_path)
            print(f"[+] Created folder: {args.name}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "rm":
        from bleep.ble_ops.classic.ftp import delete_item
        try:
            delete_item(mac, args.name, remote_path=args.remote_path)
            print(f"[+] Deleted: {args.name}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return 0


def run_pan(args, _subparsers=None) -> int:
    if not args.action:
        _subparsers["classic-pan"].print_help()
        return 0

    if args.action == "connect":
        from bleep.ble_ops.classic.pan import connect as pan_connect
        if not getattr(args, "no_preflight", False):
            from bleep.core.preflight import (
                check_pan_prerequisites,
                print_pan_prereq_summary,
            )
            print_pan_prereq_summary(
                check_pan_prerequisites(args.role, server=False)
            )
        try:
            iface = pan_connect(
                args.address,
                args.role,
                ensure_trusted=getattr(args, "trust", False),
                profile_fallback=not getattr(args, "no_fallback", False),
            )
            print(f"[+] PAN connected – interface {iface}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "disconnect":
        from bleep.ble_ops.classic.pan import disconnect as pan_disconnect
        try:
            pan_disconnect(args.address)
            print("[+] PAN disconnected")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "status":
        from bleep.ble_ops.classic.pan import status as pan_status
        try:
            info = pan_status(args.address)
            print(f"  Connected : {info.get('connected', False)}")
            print(f"  Interface : {info.get('interface', '(none)')}")
            print(f"  UUID/Role : {info.get('uuid', '(none)')}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "monitor":
        from bleep.ble_ops.classic.pan import monitor as pan_monitor

        def _on_change(state, changed):
            conn = state.get("connected")
            iface = state.get("interface") or "(none)"
            print(f"[monitor] connected={conn} interface={iface} "
                  f"uuid={state.get('uuid') or '(none)'} changed={list(changed)}")

        try:
            print(f"[*] Monitoring {args.address} — press Ctrl+C to stop")
            final = pan_monitor(
                args.address,
                adapter=getattr(args, "adapter", "hci0"),
                timeout=getattr(args, "timeout", None),
                on_change=_on_change,
            )
            print(f"[+] Final state: {final}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "server-reg":
        import signal as _signal
        from bleep.ble_ops.classic.pan import register_servers, PAN_SERVER_ROLES

        roles = list(PAN_SERVER_ROLES) if getattr(args, "all_roles", False) \
            else (args.role or ["nap"])
        authorize = getattr(args, "authorize", False)
        if not getattr(args, "no_preflight", False):
            from bleep.core.preflight import (
                check_pan_prerequisites,
                print_pan_prereq_summary,
            )
            print_pan_prereq_summary(
                check_pan_prerequisites(",".join(roles), server=True, bridge=args.bridge)
            )
        server = None
        agent = None
        loop = None
        try:
            if authorize:
                from bleep.ble_ops.classic.pan import register_pan_agent
                agent, _bus = register_pan_agent(auto_accept=True)
            server = register_servers(roles, args.bridge)
            hosted = ", ".join(server.registered_roles)
            print(f"[+] PAN server registered (roles={hosted}, bridge={args.bridge})")
            if authorize:
                from gi.repository import GLib
                print("[*] Authorization observer active — logging inbound BNEP clients")
                print("[*] Keeping process alive — press Ctrl+C to unregister and exit")
                loop = GLib.MainLoop()
                try:
                    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, _signal.SIGINT, loop.quit)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    loop.run()
                except KeyboardInterrupt:
                    pass
            else:
                print("[*] Keeping process alive — press Ctrl+C to unregister and exit")
                try:
                    _signal.pause()
                except KeyboardInterrupt:
                    pass
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        finally:
            if agent is not None:
                try:
                    agent.unregister()
                    print("[+] Authorization observer unregistered")
                except Exception as exc:  # noqa: BLE001
                    print(f"[-] Failed to unregister agent: {exc}", file=sys.stderr)
            if server is not None and server.registered_roles:
                results = server.unregister_all()
                done = [r for r, err in results.items() if err is None]
                if done:
                    print(f"\n[+] PAN server unregistered (roles={', '.join(done)})")
                for role, err in results.items():
                    if err is not None:
                        print(f"[-] Failed to unregister role={role}: {err}",
                              file=sys.stderr)

    elif args.action == "server-unreg":
        from bleep.ble_ops.classic.pan import unregister_servers, PAN_SERVER_ROLES
        roles = list(PAN_SERVER_ROLES) if getattr(args, "all_roles", False) \
            else (args.role or ["nap"])
        try:
            results = unregister_servers(roles)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        done = [r for r, err in results.items() if err is None]
        if done:
            print(f"[+] PAN server unregistered (roles={', '.join(done)})")
        failed = {r: err for r, err in results.items() if err is not None}
        for role, err in failed.items():
            print(f"[-] role={role}: {err}", file=sys.stderr)
        # Non-zero only if nothing was unregistered at all.
        if not done:
            return 1

    return 0


def run_network_enum(args, _subparsers=None) -> int:
    """Enumerate PAN network capability across adapters and devices.

    Read-only: a single ``GetManagedObjects`` snapshot drives both the adapter
    (``NetworkServer1``) and device (``Network1`` / PAN UUID) views.
    """
    from bleep.ble_ops.classic.pan import find_network_servers, find_network_devices

    adapter = getattr(args, "adapter", None)
    only_capable = not getattr(args, "all_devices", False)
    try:
        servers = find_network_servers(adapter=adapter)
        devices = find_network_devices(adapter=adapter, only_capable=only_capable)
    except Exception as exc:  # defensive; helpers already swallow errors
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({"adapters": servers, "devices": devices}, indent=2))
        return 0

    print("=" * 60)
    print("PAN Network Capability Enumeration")
    print("=" * 60)

    print("\n[+] Adapters:")
    if not servers:
        print("  (none found)")
    for a in servers:
        print(f"  {a['name']} ({a['address']}) — {a['path']}")
        print(f"    Powered: {a['powered']}  "
              f"NetworkServer1: {'yes' if a['has_networkserver'] else 'no'}")
        if a["network_uuids"]:
            print(f"    PAN roles advertised: {', '.join(a['network_uuids'])}")

    print("\n[+] Network-capable devices:")
    if not devices:
        print("  (none found)")
    for d in devices:
        roles = f"  roles: {', '.join(d['network_uuids'])}" if d["network_uuids"] else ""
        print(f"  {d['name']} ({d['address']})")
        print(f"    Network1 iface: {'yes' if d['has_network_interface'] else 'no'}{roles}")
        st = d.get("network_status")
        if st:
            print(f"    Status: connected={st['connected']} "
                  f"interface={st['interface'] or '-'} role_uuid={st['uuid'] or '-'}")

    servers_with = sum(1 for a in servers if a["has_networkserver"])
    print("\n" + "=" * 60)
    print(f"Summary: {len(servers)} adapter(s), {servers_with} with NetworkServer1; "
          f"{len(devices)} network-capable device(s).")
    print("=" * 60)
    return 0


def run_spp(args, _subparsers=None) -> int:
    if not args.action:
        _subparsers["classic-spp"].print_help()
        return 0

    if args.action == "register":
        import signal as _signal
        from bleep.ble_ops.classic.spp import register as spp_register, unregister as spp_unregister

        def _on_connect(device_path: str, sock, fd_props: dict) -> None:
            print(f"[SPP] Connection from {device_path}")
            print(f"[SPP] Socket fd={sock.fileno()} – reading data...")
            try:
                while True:
                    data = sock.recv(1024)
                    if not data:
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
            except (OSError, KeyboardInterrupt):
                pass
            finally:
                sock.close()
                print("\n[SPP] Connection closed")

        req_auth = not getattr(args, "no_auth", False)
        try:
            spp_register(
                channel=args.channel, name=args.name, role=args.role,
                require_auth=req_auth,
                on_connect=_on_connect,
            )
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        print("[+] SPP profile registered – press Ctrl+C to stop")
        try:
            _signal.pause()
        except KeyboardInterrupt:
            pass
        finally:
            spp_unregister()
            print("\n[+] SPP profile unregistered")

    elif args.action == "unregister":
        from bleep.ble_ops.classic.spp import unregister as spp_unregister
        try:
            spp_unregister()
            print("[+] SPP profile unregistered")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "status":
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

    return 0


def run_sync(args, _subparsers=None) -> int:
    if not args.action:
        _subparsers["classic-sync"].print_help()
        return 0

    if args.action == "get":
        from bleep.ble_ops.classic.sync import get_phonebook
        from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
        from pathlib import Path
        if args.output:
            dest = args.output
            use_staging = False
        else:
            dest = str(OBEX_STAGING_DIR / f"sync_{args.address.replace(':', '').upper()}.vcf")
            use_staging = True
        try:
            result = get_phonebook(
                args.address, dest,
                location=args.location, timeout=args.timeout,
            )
            if use_staging:
                final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                final_dir.mkdir(parents=True, exist_ok=True)
                final = str(final_dir / os.path.basename(str(result)))
                if os.path.exists(str(result)):
                    shutil.move(str(result), final)
                print(f"[+] Phonebook saved → {final}")
            else:
                print(f"[+] Phonebook saved → {result}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "put":
        from bleep.ble_ops.classic.sync import put_phonebook
        try:
            put_phonebook(
                args.address, args.file,
                location=args.location, timeout=args.timeout,
            )
            print("[+] Phonebook uploaded OK")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return 0


def run_bip(args, _subparsers=None) -> int:
    if not args.action:
        _subparsers["classic-bip"].print_help()
        return 0

    if args.action == "list":
        print(
            "BlueZ's experimental Image1 interface does not provide an\n"
            "image-listing method.  To discover handles you can:\n"
            "  1. Use AVRCP media browsing (if the device is an A2DP source)\n"
            "     to enumerate cover-art handles exposed via bip-avrcp.\n"
            "  2. Start from handle '0' or '1000001' and iterate with\n"
            "     'classic-bip props <handle>' until the device returns an\n"
            "     error, incrementing by 1 each time.\n"
            "  3. Use 'classic-map list' or 'classic-ftp ls' to locate\n"
            "     image attachments whose handles can be passed to BIP."
        )
        return 0

    elif args.action == "props":
        from bleep.ble_ops.classic.bip import get_properties
        try:
            props = get_properties(
                args.address, args.handle, timeout=args.timeout,
            )
            for i, entry in enumerate(props):
                print(f"  [{i}] {entry}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "get":
        from bleep.ble_ops.classic.bip import get_image
        from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
        from pathlib import Path
        if args.output:
            dest = args.output
            use_staging = False
        else:
            dest = str(OBEX_STAGING_DIR / f"bip_{args.handle}")
            use_staging = True
        try:
            result = get_image(
                args.address, dest, args.handle,
                timeout=args.timeout,
            )
            if use_staging:
                final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                final_dir.mkdir(parents=True, exist_ok=True)
                final = str(final_dir / os.path.basename(str(result)))
                if os.path.exists(str(result)):
                    shutil.move(str(result), final)
                print(f"[+] Image saved → {final}")
            else:
                print(f"[+] Image saved → {result}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    elif args.action == "thumb":
        from bleep.ble_ops.classic.bip import get_thumbnail
        from bleep.core.config import OBEX_STAGING_DIR, OBEX_RECEIVE_DIR
        from pathlib import Path
        if args.output:
            dest = args.output
            use_staging = False
        else:
            dest = str(OBEX_STAGING_DIR / f"bip_thumb_{args.handle}")
            use_staging = True
        try:
            result = get_thumbnail(
                args.address, dest, args.handle,
                timeout=args.timeout,
            )
            if use_staging:
                final_dir = Path(args.save_dir) if args.save_dir else OBEX_RECEIVE_DIR
                final_dir.mkdir(parents=True, exist_ok=True)
                final = str(final_dir / os.path.basename(str(result)))
                if os.path.exists(str(result)):
                    shutil.move(str(result), final)
                print(f"[+] Thumbnail saved → {final}")
            else:
                print(f"[+] Thumbnail saved → {result}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return 0
