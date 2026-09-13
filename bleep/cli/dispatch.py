"""BLEEP CLI mode dispatch — routes parsed args to the appropriate mode handler."""

import sys


def dispatch(args, _subparsers) -> int:
    """Route to the correct mode handler based on args.mode.

    Returns an integer exit code.
    """
    if args.mode == "scan":
        if getattr(args, "monitor", False):
            from bleep.modes.scan_monitor import run_monitor_scan
            return run_monitor_scan(args)

        from bleep.ble_ops.le import scan as _scan_mod

        variant = args.variant.lower()
        timeout = args.timeout
        # -d/--device is a client-side result filter; --target is the pokey target.
        # Either may supply the address to filter on.
        target = args.target or getattr(args, "device", None)
        filter_record = getattr(args, "record_target_only", False)

        if variant == "pokey" and not target:
            print("[ERROR] --target <MAC> required for pokey scan variant", file=sys.stderr)
            return 1

        transport = args.transport
        # F5: honor --adapter. Validate up-front so a missing/not-ready controller
        # fails clearly (non-zero exit) instead of silently falling back to the
        # default adapter. ``require_adapter`` prints a uniform diagnostic.
        adapter_name = getattr(args, "adapter", None)
        from bleep.core.preflight import require_adapter
        if not require_adapter(adapter_name):
            return 1

        _dispatch = {
            "passive": lambda: _scan_mod.passive_scan(target, timeout, transport=transport, adapter_name=adapter_name, filter_record=filter_record),
            "naggy": lambda: _scan_mod.naggy_scan(target, timeout, transport=transport, adapter_name=adapter_name, filter_record=filter_record),
            "pokey": lambda: _scan_mod.pokey_scan(target, timeout=timeout, transport=transport, adapter_name=adapter_name),
            "brute": lambda: _scan_mod.brute_scan(timeout, adapter_name=adapter_name),
        }

        _dispatch[variant]()
        return 0

    elif args.mode == "survey":
        from bleep.modes.survey import run as _survey_run
        from bleep.core.output import output_from_args
        return _survey_run(args, output_from_args(args)) or 0

    elif args.mode == "beacon-identification":
        from bleep.modes.beacon_identification import run as _beacon_run
        from bleep.core.output import output_from_args
        return _beacon_run(args, output_from_args(args)) or 0

    elif args.mode == "enum-scan":
        from bleep.modes.enum_scan import run as _enum_scan_run
        return _enum_scan_run(args) or 0

    elif args.mode == "connect":
        from bleep.modes.connect import run as _connect_run
        return _connect_run(args) or 0

    elif args.mode == "gatt-enum":
        from bleep.modes.gatt_enum import run as _gatt_enum_run
        return _gatt_enum_run(args) or 0

    elif args.mode == "media-enum":
        from bleep.modes.media import run_media_enum as _media_enum_run
        return _media_enum_run(args) or 0

    elif args.mode == "media-ctrl":
        from bleep.modes.media import control_media_device as _ctrl

        # Convert value based on the action type
        value = None
        if args.value is not None:
            try:
                if args.action == "volume":
                    value = int(args.value)
                elif args.action == "press":
                    # Handle hex values with 0x prefix
                    if args.value.lower().startswith("0x"):
                        value = int(args.value, 16)
                    else:
                        value = int(args.value)
            except ValueError as e:
                print(f"Error parsing value: {e}", file=sys.stderr)
                return 1

        success = _ctrl(args.address, args.action, value)
        return 0 if success else 1

    elif args.mode == "audio-profiles":
        from bleep.modes.audio import run_audio_profiles as _ap_run
        return _ap_run(args) or 0

    elif args.mode == "audio-play":
        if getattr(args, "system", False):
            from bleep.ble_ops.audio.audio_system import system_play
            success = system_play(args.device, args.file)
            return 0 if success else 1

        from bleep.dbuslayer.media_stream import MediaStreamManager

        direct = getattr(args, "direct", False)
        force_endpoint = getattr(args, "force_endpoint", False)
        stream_manager = MediaStreamManager(
            args.device, direct=direct, force_endpoint=force_endpoint,
        )
        codec_pref = getattr(args, "codec", None)
        success = stream_manager.play_audio_file(
            args.file, volume=args.volume, codec_preference=codec_pref,
        )
        return 0 if success else 1

    elif args.mode == "audio-record":
        if getattr(args, "hfp", False):
            from bleep.ble_ops.audio.audio_system import system_record_hfp
            duration = getattr(args, "duration", None) or 8
            success = system_record_hfp(
                args.device, args.output, duration,
                restore_profile=not getattr(args, "keep_profile", False),
            )
            return 0 if success else 1

        if getattr(args, "system", False):
            from bleep.ble_ops.audio.audio_system import system_record
            duration = getattr(args, "duration", None) or 8
            success = system_record(args.device, args.output, duration)
            return 0 if success else 1

        from bleep.dbuslayer.media_stream import MediaStreamManager
        from bleep.bt_ref.constants import A2DP_SOURCE_UUID

        direct = getattr(args, "direct", False)
        force_endpoint = getattr(args, "force_endpoint", False)
        stream_manager = MediaStreamManager(
            args.device,
            profile_uuid=A2DP_SOURCE_UUID,
            direct=direct,
            force_endpoint=force_endpoint,
        )
        success = stream_manager.record_audio(args.output, duration=args.duration)
        return 0 if success else 1

    elif args.mode == "audio-recon":
        from bleep.ble_ops.audio.audio_recon import run_audio_recon
        run_audio_recon(
            mac_filter=getattr(args, "device", None),
            test_file=getattr(args, "test_file", None),
            do_play=not getattr(args, "no_play", False),
            do_record=not getattr(args, "no_record", False),
            record_duration_sec=getattr(args, "duration", 8),
            record_dir=getattr(args, "record_dir", "/tmp"),
            output_json_path=getattr(args, "output_json", None),
        )
        return 0

    elif args.mode == "amusica":
        from bleep.modes.amusica import main as _amusica_main
        return _amusica_main(args.amusica_args)

    elif args.mode == "db":
        from bleep.modes.db import run as _db_run
        from bleep.core.output import output_from_args
        return _db_run(args, output_from_args(args))

    elif args.mode == "agent":
        from bleep.modes.agent import run as _agent_run
        from bleep.core.output import output_from_args
        return _agent_run(args, output_from_args(args)) or 0

    elif args.mode == "pair":
        from bleep.modes.pair import run as _pair_run
        from bleep.core.output import output_from_args
        return _pair_run(args, output_from_args(args)) or 0

    elif args.mode == "classic-connect":
        from bleep.modes.classic_connect import run as _cc_run
        from bleep.core.output import output_from_args
        return _cc_run(args, output_from_args(args)) or 0

    elif args.mode == "user":
        from bleep.modes.user import run as _user_run
        from bleep.core.output import output_from_args
        return _user_run(args, output_from_args(args)) or 0

    elif args.mode == "explore":
        from bleep.modes.exploration import run as _explore_run
        from bleep.core.output import output_from_args
        return _explore_run(args, output_from_args(args)) or 0

    elif args.mode in ["analyse", "analyze"]:
        from bleep.modes.analysis import main as _an_main

        # Build arguments list for the analysis module
        analysis_args = args.files.copy()
        if args.detailed:
            analysis_args.append("--detailed")

        return _an_main(analysis_args) or 0

    elif args.mode == "aoi":
        from bleep.modes.aoi import run as _aoi_run
        from bleep.core.output import output_from_args
        from bleep.cli.parsers.aoi import apply_aoi_subcommand
        explicit = apply_aoi_subcommand(args)
        if not explicit and not args.files:
            print("Error: No files specified or valid subcommand provided.", file=sys.stderr)
            print("Available subcommands: scan, analyze, list, report, export, db", file=sys.stderr)
            return 1
        return _aoi_run(args, output_from_args(args)) or 0

    elif args.mode == "signal":
        from bleep.modes.signal import run as _sig_run
        from bleep.core.output import output_from_args
        return _sig_run(args, output_from_args(args)) or 0

    elif args.mode == "signal-config":
        from bleep.signals.cli import main as _sigconf_main

        # If no command provided, show help
        if not args.command:
            return _sigconf_main(["--help"])

        # Pass the command and args
        opts = [args.command] + args.args
        return _sigconf_main(opts) or 0

    elif args.mode in ["uuid-translate", "uuid-lookup"]:
        from bleep.modes.uuid_translate import main as _uuid_translate_main

        # Build arguments list
        uuid_opts = list(args.uuids)
        if args.json:
            uuid_opts.append("--json")
        if args.verbose:
            uuid_opts.append("--verbose")
        if getattr(args, "include_unknown", False):
            uuid_opts.append("--include-unknown")

        return _uuid_translate_main(uuid_opts) or 0

    elif args.mode == "classic-scan":
        from bleep.modes.classic_scan import run as _cscan_run
        return _cscan_run(args) or 0

    elif args.mode == "classic-enum":
        from bleep.modes.classic_enum import run as _cenum_run
        return _cenum_run(args) or 0

    elif args.mode == "classic-pbap":
        from bleep.modes.classic_profiles import run_pbap
        return run_pbap(args, _subparsers) or 0

    elif args.mode == "classic-opp":
        from bleep.modes.classic_profiles import run_opp
        return run_opp(args, _subparsers) or 0

    elif args.mode == "classic-map":
        from bleep.modes.classic_profiles import run_map
        return run_map(args, _subparsers) or 0

    elif args.mode == "classic-ftp":
        from bleep.modes.classic_profiles import run_ftp
        return run_ftp(args, _subparsers) or 0

    elif args.mode == "classic-pan":
        from bleep.modes.classic_profiles import run_pan
        return run_pan(args, _subparsers) or 0

    elif args.mode == "network-enum":
        from bleep.modes.classic_profiles import run_network_enum
        return run_network_enum(args, _subparsers) or 0

    elif args.mode == "classic-spp":
        from bleep.modes.classic_profiles import run_spp
        return run_spp(args, _subparsers) or 0

    elif args.mode == "connect-profile":
        mac = args.address
        uuid = args.uuid
        adapter_name = getattr(args, "adapter", None)
        try:
            from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic as ClassicDevice
            from bleep.bt_ref.utils import get_name_from_uuid
            device = ClassicDevice(mac, adapter_name=adapter_name) if adapter_name else ClassicDevice(mac)
            name = get_name_from_uuid(uuid) or uuid
            if args.disconnect:
                device.disconnect_profile(uuid)
                print(f"[+] Disconnected profile: {name}")
            else:
                device.connect_profile(uuid)
                print(f"[+] Connected profile: {name}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    elif args.mode == "hid-info":
        mac = args.address
        adapter_name = getattr(args, "adapter", None)
        connect = getattr(args, "connect", False)
        try:
            from bleep.ble_ops.hid import build_hid_context
            from bleep.analysis.device_type_classifier import classify_hid
            context = build_hid_context(mac, connect=connect, adapter_name=adapter_name)
            hid = classify_hid(context)
            if hid is None:
                print(f"[*] {mac} does not appear to be a HID device")
            else:
                print(f"[+] HID Classification for {mac}:")
                print(f"    Type:            {hid.hid_type}")
                print(f"    Subclass:        {hid.subclass_label}")
                if hid.reconnect_mode:
                    print(f"    Reconnect Mode:  {hid.reconnect_mode}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    elif args.mode == "audio-intercept":
        from bleep.ble_ops.audio.audio_transcribe import run_audio_intercept
        result = run_audio_intercept(
            args.address,
            duration=args.duration,
            output_dir=args.output_dir,
            pcm_device=args.pcm,
            transcribe=not args.no_transcribe,
            engine=args.engine,
        )
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
            return 1
        print(f"[+] Captured: {result.wav_path}")
        print(f"    Duration:    {result.duration_seconds}s")
        print(f"    Has content: {result.has_content}")
        if result.transcript:
            print(f"    Engine:      {result.engine}")
            print(f"    Transcript:  {result.transcript[:200]}")
        elif result.has_content:
            print("    (no transcription engine available)")
        return 0

    elif args.mode == "classic-sync":
        from bleep.modes.classic_profiles import run_sync
        return run_sync(args, _subparsers) or 0

    elif args.mode == "classic-bip":
        from bleep.modes.classic_profiles import run_bip
        return run_bip(args, _subparsers) or 0

    elif args.mode == "classic-ping":
        from bleep.ble_ops.classic.ping import classic_l2ping

        rtt, err = classic_l2ping(args.address, count=args.count, timeout=args.timeout)
        if rtt is None:
            print(f"[!] l2ping failed – {err}", file=sys.stderr)
            return 1
        print(f"Average RTT {rtt:.1f} ms")
        return 0

    elif args.mode == "classic-rfcomm":
        from bleep.modes.classic_rfcomm import run as _rfcomm_run
        return _rfcomm_run(args) or 0

    elif args.mode == "ctf":
        from bleep.modes.blectf import run as _ctf_run
        return _ctf_run(args) or 0

    elif args.mode == "refresh-refs":
        from bleep.modes.refresh_refs import run as _refresh_refs_run
        return _refresh_refs_run(args)

    elif args.mode == "adapter-config":
        from bleep.modes.adapter_config import handle_adapter_config
        return handle_adapter_config(args)

    elif args.mode == "advertise-monitor":
        from bleep.core.output import output_from_args
        from bleep.modes.monitor import run as monitor_run
        return monitor_run(args, output_from_args(args))

    elif args.mode == "advertise":
        from bleep.core.output import output_from_args
        from bleep.modes.advertise import run as advertise_run
        return advertise_run(args, output_from_args(args))

    elif args.mode == "gatt-server":
        from bleep.core.output import output_from_args
        from bleep.modes.gatt_server import run as gatt_server_run
        return gatt_server_run(args, output_from_args(args))

    elif args.mode == "device-sets":
        from bleep.modes.device_sets import handle_device_sets
        return handle_device_sets(args)

    elif args.mode == "mesh":
        from bleep.modes.mesh_provision import handle_mesh
        return handle_mesh(args)

    elif args.mode == "audio-config":
        from bleep.modes.audio import run_audio_config as _ac_run
        return _ac_run(args) or 0

    elif args.mode == "debug":
        from bleep.modes.debug import main as _debug_main
        from bleep.cli.main import _rebuild_debug_argv

        return _debug_main(_rebuild_debug_argv(args)) or 0

    else:  # interactive (default)
        from bleep.modes.interactive import main as _interactive_main

        return _interactive_main() or 0

    return 0
