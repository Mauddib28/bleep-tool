"""CLI dispatch handler for Classic Bluetooth enumeration mode."""


def run(args, output=None) -> int:
    from bleep.ble_ops import connect_and_enumerate__bluetooth__classic as _c_enum
    from bleep.ble_ops.classic.sdp import discover_services_sdp, format_protocol_descriptors
    from bleep.bt_ref.uuid_translator import get_uuid_name
    from bleep.ble_ops.classic.version import (
        query_hci_version,
        query_remote_version,
        map_lmp_version_to_spec,
        map_profile_version_to_spec,
    )
    from bleep.analysis.sdp_analyzer import SDPAnalyzer, analyze_sdp_records
    from bleep.dbuslayer.device_classic import system_dbus__bluez_device__classic
    from bleep.core.log import print_and_log, LOG__DEBUG, LOG__GENERAL
    from typing import Dict, Any
    import json

    debug_mode = getattr(args, "debug", False)
    version_info_mode = getattr(args, "version_info", False)
    analyze_mode = getattr(args, "analyze", False)
    if debug_mode:
        print_and_log("[classic-enum] Debug mode enabled", LOG__GENERAL)
        print_and_log(f"[classic-enum] Enumerating SDP records for {args.address}", LOG__GENERAL)
        import logging
        logging.getLogger("bleep").setLevel(logging.DEBUG)
        print("[*] Debug output enabled - check /tmp/bti__logging__debug.txt for detailed logs")

    version_info_data: Dict[str, Any] = {}
    bluez_uuids: list = []
    if version_info_mode:
        try:
            device = system_dbus__bluez_device__classic(args.address)
            version_info_data = device.get_device_version_info()

            hci_info = query_hci_version()
            if hci_info:
                version_info_data["local_adapter"] = {
                    "hci_version": hci_info.get("hci_version"),
                    "hci_revision": hci_info.get("hci_revision"),
                    "lmp_version": hci_info.get("lmp_version"),
                    "lmp_subversion": hci_info.get("lmp_subversion"),
                    "manufacturer": hci_info.get("manufacturer"),
                    "lmp_spec": map_lmp_version_to_spec(hci_info.get("lmp_version")),
                }

            remote_info = query_remote_version(args.address)
            if remote_info:
                version_info_data["remote"] = remote_info
                # Persist authoritative version data to DB
                try:
                    from bleep.core import observations as _obs_ver
                    from bleep.core.time_utils import utc_now_iso
                    _obs_ver.upsert_device(
                        args.address.upper(),
                        lmp_version=remote_info["lmp_version"],
                        lmp_subversion=remote_info["lmp_subversion"],
                        bt_manufacturer=remote_info.get("manufacturer"),
                        bt_spec_version=remote_info.get("lmp_spec"),
                        lmp_features=remote_info.get("features_raw"),
                        version_queried_at=utc_now_iso(),
                    )
                except Exception as _db_ver_exc:
                    if debug_mode:
                        print_and_log(f"[classic-enum] DB version persist warning: {_db_ver_exc}", LOG__DEBUG)
        except Exception as ver_exc:
            if debug_mode:
                print_and_log(f"[classic-enum] Version info collection failed: {ver_exc}", LOG__GENERAL)
            version_info_data["error"] = str(ver_exc)

    try:
        import dbus as _dbus_cenum
        _bus_cenum = _dbus_cenum.SystemBus()
        from bleep.bt_ref.utils import device_address_to_path
        from bleep.bt_ref.constants import BLUEZ_NAMESPACE, ADAPTER_NAME
        _dev_path = device_address_to_path(args.address.upper(), f"{BLUEZ_NAMESPACE}{ADAPTER_NAME}")
        _obj_cenum = _bus_cenum.get_object("org.bluez", _dev_path)
        _pi_cenum = _dbus_cenum.Interface(_obj_cenum, "org.freedesktop.DBus.Properties")
        _cenum_props = dict(_pi_cenum.GetAll("org.bluez.Device1"))
        bluez_uuids = [str(u).strip().upper() for u in _cenum_props.get("UUIDs", [])]
        for _aux_iface, _aux_key in [("org.bluez.Battery1", "_Battery1"), ("org.bluez.Input1", "_Input1")]:
            try:
                _aux = dict(_pi_cenum.GetAll(_aux_iface))
                if _aux:
                    _cenum_props[_aux_key] = _aux
            except Exception:
                pass
        from bleep.ble_ops.common.conversion import format_device_info_block
        _cenum_name = str(_cenum_props.get("Name", "")) or str(_cenum_props.get("Alias", ""))
        print(format_device_info_block(_cenum_props, device_name=_cenum_name or None, mac=args.address.upper()))
        print()

        try:
            from bleep.ble_ops.le.scan import _enrich_device_info_from_props
            from bleep.core import observations as _obs_cenum
            _cenum_dev_info: Dict[str, Any] = {"name": _cenum_name or None}
            _enrich_device_info_from_props(_cenum_dev_info, _cenum_props)
            _obs_cenum.upsert_device(args.address.upper(), **_cenum_dev_info)
        except Exception as _db_cenum_exc:
            if debug_mode:
                print_and_log(f"[classic-enum] DB device upsert warning: {_db_cenum_exc}", LOG__DEBUG)
    except Exception as _props_exc:
        if debug_mode:
            print_and_log(f"[classic-enum] Device info block unavailable: {_props_exc}", LOG__DEBUG)

    records = []
    connectionless_mode = getattr(args, "connectionless", False)
    sdp_source = getattr(args, "sdp_source", "auto")
    try:
        records = discover_services_sdp(
            args.address, connectionless=connectionless_mode, source=sdp_source
        )

        if records:
            print_and_log(f"[+] Found {len(records)} SDP record(s) for {args.address}", LOG__GENERAL)
            print("\nSDP Records:")
            print("=" * 80)
            for idx, rec in enumerate(records, 1):
                print(f"\nRecord {idx}:")
                if rec.get("name"):
                    print(f"  Name: {rec['name']}")
                if rec.get("uuid"):
                    uuid_name = get_uuid_name(rec["uuid"])
                    if not rec.get("name") and uuid_name:
                        print(f"  UUID: {rec['uuid']} ({uuid_name})")
                    else:
                        print(f"  UUID: {rec['uuid']}")
                if rec.get("channel") is not None:
                    print(f"  RFCOMM Channel: {rec['channel']}")
                if rec.get("handle") is not None:
                    print(f"  Service Record Handle: 0x{rec['handle']:04X}")
                if sdp_source != "auto" and rec.get("source"):
                    print(f"  Source: {rec['source']}")
                if rec.get("source_conflicts"):
                    for _field, _per_src in rec["source_conflicts"].items():
                        _rendered = ", ".join(f"{s}={v}" for s, v in _per_src.items())
                        print(f"  [!] Source discrepancy on {_field}: {_rendered}")
                if rec.get("service_version") is not None:
                    print(f"  Service Version: 0x{rec['service_version']:04X}")
                if rec.get("description"):
                    print(f"  Description: {rec['description']}")
                if rec.get("profile_descriptors"):
                    print("  Profile Descriptors:")
                    for p in rec["profile_descriptors"]:
                        uuid = p.get("uuid", "Unknown")
                        ver = p.get("version")
                        if ver is not None:
                            spec_hint = map_profile_version_to_spec(ver) if version_info_mode else None
                            ver_str = f"0x{ver:04X}"
                            if spec_hint:
                                ver_str += f" (~profile v{spec_hint})"
                            print(f"    {uuid}: Version {ver_str}")
                        else:
                            print(f"    {uuid}: Version unknown")
                proto_str = format_protocol_descriptors(rec.get("protocol_descriptors"))
                if proto_str:
                    print(f"  Protocols: {proto_str}")
            print("\n" + "=" * 80)

            from bleep.ble_ops.classic.sdp import build_svc_map
            svc_map_sdp = build_svc_map(records)
            rfcomm_n = sum(1 for v in svc_map_sdp.values() if v.get("channel") is not None)
            if svc_map_sdp:
                print(f"\nService Map ({len(svc_map_sdp)} service(s), {rfcomm_n} with RFCOMM):")
                for svc, entry in svc_map_sdp.items():
                    ch = entry.get("channel")
                    ch_str = f"-> ch {ch}" if ch is not None else "(no RFCOMM)"
                    # F3: ``build_svc_map`` keys unnamed records by their bare UUID
                    # (e.g. ``0X111F``). Resolve to the assigned-numbers name at
                    # display time so the map reads "0X111F (AG Hands-Free)".
                    display = svc
                    if entry.get("name") is None and entry.get("uuid"):
                        resolved = get_uuid_name(entry["uuid"])
                        if resolved:
                            display = f"{entry['uuid']} ({resolved})"
                    print(f"  {display:25} {ch_str}")
                print()

            # Reconcile the BlueZ-advertised UUID list against the parsed SDP
            # records: discrepancies can indicate honeypots, spoofing, or
            # services BlueZ cached but did not re-enumerate (and vice versa).
            if bluez_uuids:
                def _canon_uuid(u: str) -> str:
                    u = (u or "").upper().replace("0X", "")
                    if u.endswith("0000-1000-8000-00805F9B34FB"):
                        return u[:8].lstrip("0") or "0"
                    return u

                def _name_for(canon: str) -> str:
                    # translate_uuid handles short (16/32-bit) and full forms,
                    # so no manual BT-SIG expansion is required here.
                    return get_uuid_name(canon)

                sdp_uuid_set = {
                    _canon_uuid(v.get("uuid")) for v in svc_map_sdp.values() if v.get("uuid")
                }
                bluez_set = {_canon_uuid(u) for u in bluez_uuids}
                only_bluez = sorted(bluez_set - sdp_uuid_set)
                only_sdp = sorted(sdp_uuid_set - bluez_set)
                if only_bluez or only_sdp:
                    print("UUID Reconciliation (BlueZ Device1.UUIDs vs parsed SDP):")
                    if only_bluez:
                        print(f"  Advertised by BlueZ but not in SDP records ({len(only_bluez)}):")
                        for u in only_bluez:
                            name = _name_for(u)
                            print(f"    0x{u} ({name})" if name else f"    0x{u}")
                    if only_sdp:
                        print(f"  In SDP records but not advertised by BlueZ ({len(only_sdp)}):")
                        for u in only_sdp:
                            name = _name_for(u)
                            label = f"0x{u}" if len(u) <= 8 else u
                            print(f"    {label} ({name})" if name else f"    {label}")
                    print()

        if version_info_mode:
            print("\n=== Version Information ===")
            if version_info_data.get("error"):
                print(f"Error collecting version info: {version_info_data['error']}")
            else:
                if version_info_data.get("vendor") is not None:
                    print(f"Vendor ID: 0x{version_info_data['vendor']:04X}")
                if version_info_data.get("product") is not None:
                    print(f"Product ID: 0x{version_info_data['product']:04X}")
                if version_info_data.get("version") is not None:
                    print(f"Version: 0x{version_info_data['version']:04X}")
                if version_info_data.get("modalias"):
                    print(f"Modalias: {version_info_data['modalias']}")

                if records:
                    print("\nProfile Versions (from SDP):")
                    profile_specs: Dict[str, list] = {}
                    for rec in records:
                        if rec.get('profile_descriptors'):
                            for p in rec.get('profile_descriptors', []):
                                uuid = p.get('uuid', 'Unknown')
                                ver = p.get('version')
                                if ver is not None:
                                    spec_hint = map_profile_version_to_spec(ver)
                                    if uuid not in profile_specs:
                                        profile_specs[uuid] = []
                                    profile_specs[uuid].append({
                                        "version": ver,
                                        "spec_hint": spec_hint,
                                    })

                    for uuid, vers in profile_specs.items():
                        for v_info in vers:
                            ver_str = f"0x{v_info['version']:04X}"
                            if v_info['spec_hint']:
                                # SDP BluetoothProfileDescriptorList encodes the *profile*
                                # version (SDP attr 0x0009), which is distinct from the
                                # device core-spec version (authoritative via HCI Read
                                # Remote Version, shown in the "Remote Device" block below).
                                ver_str += f" (~profile v{v_info['spec_hint']})"
                            print(f"  {uuid}: {ver_str}")

                if version_info_data.get("local_adapter"):
                    local = version_info_data["local_adapter"]
                    print("\nLocal Adapter (for reference):")
                    if local.get("lmp_version") is not None:
                        lmp_spec = local.get("lmp_spec", "Unknown")
                        print(f"  LMP Version: {local['lmp_version']} ({lmp_spec})")
                    if local.get("hci_version") is not None:
                        print(f"  HCI Version: {local['hci_version']}")
                    if local.get("manufacturer") is not None:
                        print(f"  Manufacturer ID: {local['manufacturer']}")

                if version_info_data.get("remote"):
                    remote = version_info_data["remote"]
                    print("\nRemote Device (authoritative — via HCI Read Remote Version):")
                    if remote.get("lmp_spec"):
                        print(f"  Bluetooth Version: {remote['lmp_spec']}")
                    print(f"  LMP Version: 0x{remote['lmp_version']:02X} "
                          f"(Subversion: 0x{remote['lmp_subversion']:04X})")
                    if remote.get("manufacturer") is not None:
                        mfr_name = remote.get("manufacturer_name") or "Unknown"
                        print(f"  Manufacturer: {mfr_name} ({remote['manufacturer']})")
                    if remote.get("features_raw"):
                        print(f"  LMP Features ({len(remote['features_raw'])} page(s)):")
                        for feat_page in remote["features_raw"]:
                            print(f"    {feat_page}")

                if version_info_data.get("raw_properties"):
                    print("\nRaw Properties (for analysis):")
                    for key, value in version_info_data["raw_properties"].items():
                        print(f"  {key}: {value}")

            print("=" * 28 + "\n")

        if analyze_mode and records:
            try:
                analyzer = SDPAnalyzer(records)
                analysis = analyzer.analyze()

                # Cross-validate LMP if remote version was queried
                _remote = version_info_data.get("remote") or {}
                remote_lmp = _remote.get("lmp_version")
                if remote_lmp is not None:
                    xval = analyzer.cross_validate_lmp(remote_lmp)
                    if xval:
                        analysis.setdefault("anomalies", []).append(xval)
                        print(f"\n  [MEDIUM] {xval['type']}: {xval['description']}")

                # #8: hand the authoritative HCI/LMP core spec to the report so
                # profile versions are not mislabelled as the device core spec.
                # Only the *remote* (target) Read-Remote-Version is authoritative
                # for the target; local_adapter describes THIS host's controller.
                _auth_spec = _remote.get("lmp_spec")
                report = analyzer.generate_report(
                    authoritative_spec=_auth_spec,
                    lmp_version=remote_lmp,
                    version_info_requested=version_info_mode,
                )
                print(report)

                if debug_mode:
                    print("\n=== Detailed Analysis (JSON) ===")
                    print(json.dumps(analysis, indent=2, default=str))
                    print("=" * 35 + "\n")
            except Exception as analysis_exc:
                if debug_mode:
                    print_and_log(f"[classic-enum] SDP analysis failed: {analysis_exc}", LOG__GENERAL)
                    import traceback
                    traceback.print_exc()

    except Exception as sdp_exc:
        if debug_mode:
            print_and_log(f"[classic-enum] SDP discovery failed: {sdp_exc}", LOG__GENERAL)

    try:
        _, svc_map = _c_enum(args.address)
        if debug_mode:
            print_and_log(f"[+] Connection-based enumeration: {len(svc_map)} services", LOG__GENERAL)
        return 0
    except Exception as conn_exc:
        if records:
            print_and_log(
                f"[!] Connection failed ({conn_exc}), but SDP enumeration succeeded",
                LOG__GENERAL,
            )
            return 0

        import sys as _sys_module
        print(f"Error: {conn_exc}", file=_sys_module.stderr)
        if debug_mode:
            import traceback
            traceback.print_exc(file=_sys_module.stderr)
        return 1
