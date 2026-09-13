"""CLI dispatch handler for GATT enumeration mode."""


def run(args, output=None) -> int:
    from bleep.ble_ops.le.connect import connect_and_enumerate__bluetooth__low_energy as _connect_enum
    from bleep.ble_ops.le import scan as _scan_mod
    from bleep.core.errors import ServicesNotResolvedError as _SNR
    from bleep.core.preflight import require_adapter

    adapter_name = getattr(args, "adapter", None)
    if not require_adapter(adapter_name):
        return 1

    # #2: when --correlate is set, a ServicesNotResolvedError on the requested
    # (public/BR-EDR) address is treated like a connected-but-empty tree so the
    # correlation path below can attempt the LE identity. Without --correlate the
    # exception propagates unchanged (identical default behaviour).
    _snr_exc = None
    try:
        device, mapping, mine_map, perm_map = _connect_enum(
            args.address,
            deep_enumeration=args.deep,
            adapter_name=adapter_name,
        )
    except _SNR as _e:
        if not getattr(args, "correlate", False):
            raise
        _snr_exc = _e
        device, mapping, mine_map, perm_map = None, {}, {}, {}

    # #3: a connected-but-empty GATT tree must not report success. This is the
    # tell-tale of a dual-mode device whose GATT database lives under an LE RPA
    # (the public/BR-EDR address resolves but exposes no LE attributes) or a
    # Classic-only endpoint. Detect "no characteristics anywhere" and downgrade.
    def _has_characteristics(svc_map) -> bool:
        if not isinstance(svc_map, dict):
            return bool(svc_map)
        # Handle both mapping shapes: the live ``ble_device__mapping``
        # (``{svc_uuid: {"chars": {...}}}``) and the "Services"-wrapped tree
        # (``{"Services": {svc_uuid: {"Characteristics": {...}}}}``).
        container = svc_map.get("Services") if "Services" in svc_map else svc_map
        if not isinstance(container, dict):
            return bool(container)
        for svc in container.values():
            if isinstance(svc, dict) and (svc.get("Characteristics") or svc.get("chars")):
                return True
        return False

    _effective_addr = args.address
    _gatt_empty = not _has_characteristics(mapping)
    if _gatt_empty:
        from bleep.core.log import print_and_log as _pal, LOG__GENERAL as _LG
        _pal(
            f"[!] {args.address}: connected but no GATT characteristics were resolved. "
            "The device may be Classic-only on this address, or its GATT database "
            "may live under an LE resolvable-private address (RPA). "
            "Re-run against the LE address, or use dual-mode identity correlation.",
            _LG,
        )

        # #2: opt-in, non-merging dual-mode LE identity correlation. Only runs
        # when the analyst explicitly passes --correlate. We heuristically match
        # the target's Name/Icon/Class to a candidate LE address and re-enumerate
        # against it; the correlation is a labelled hint, never an auto-merge.
        if getattr(args, "correlate", False):
            from bleep.ble_ops.le.correlate import correlate_le_identity
            _cands = correlate_le_identity(args.address, adapter=adapter_name)
            if not _cands:
                _pal(
                    "[correlate] no LE candidate matched the target's Name/Icon/Class "
                    "(the LE identity may not be advertising right now). Nothing to retry.",
                    _LG,
                )
            else:
                _top = _cands[0]
                _pal(
                    f"[correlate] {len(_cands)} candidate(s); best={_top['address']} "
                    f"(confidence={_top['confidence']}, matched={'+'.join(_top['matched_on'])}). "
                    "HEURISTIC — not an IRK-verified identity link.",
                    _LG,
                )
                for _c in _cands[1:]:
                    _pal(
                        f"[correlate]   alt: {_c['address']} "
                        f"(confidence={_c['confidence']}, matched={'+'.join(_c['matched_on'])})",
                        _LG,
                    )
                _pal(f"[correlate] re-enumerating GATT against {_top['address']} ...", _LG)
                _cd, _cm, _cmine, _cperm = _connect_enum(
                    _top["address"], deep_enumeration=args.deep, adapter_name=adapter_name,
                )
                if _has_characteristics(_cm):
                    device, mapping, mine_map, perm_map = _cd, _cm, _cmine, _cperm
                    _effective_addr = _top["address"]
                    _gatt_empty = False
                    _pal(
                        f"[correlate] resolved GATT via correlated LE address {_effective_addr}. "
                        f"Results below are from {_effective_addr}, correlated to requested "
                        f"{args.address} by {'+'.join(_top['matched_on'])} (heuristic).",
                        _LG,
                    )
                else:
                    _pal(
                        f"[correlate] candidate {_top['address']} also resolved no GATT; "
                        "keeping original (empty) result.",
                        _LG,
                    )

        # If the primary enumeration raised (no device object) and correlation
        # did not yield a usable GATT tree, propagate the original error so the
        # default failure semantics are preserved.
        if _gatt_empty and _snr_exc is not None:
            raise _snr_exc

    import json

    def _dump(obj):
        """Return a JSON-formatted string with sane defaults."""
        def _compact(o):
            if isinstance(o, list):
                if o and all(isinstance(x, int) and 0 <= x < 256 for x in o):
                    return "[" + ", ".join(str(x) for x in o) + "]"
                return [_compact(v) for v in o]
            elif isinstance(o, dict):
                return {k: _compact(v) for k, v in o.items()}
            return o

        compact_obj = _compact(obj)
        return json.dumps(compact_obj, indent=2, ensure_ascii=False, sort_keys=False)

    if not args.report and _scan_mod._obs:
        try:
            _ge_props = _scan_mod._collect_device_props(device)
            _ge_dev_info = {"name": device.get_name() if hasattr(device, "get_name") else None}
            _scan_mod._enrich_device_info_from_props(_ge_dev_info, _ge_props)
            _scan_mod._obs.upsert_device(_effective_addr.upper(), **_ge_dev_info)

            _scan_mod._persist_mapping(_effective_addr.upper(), mapping)

            if mine_map or perm_map:
                _scan_mod._obs.store_security_maps(
                    _effective_addr.upper(),
                    landmine_map=mine_map or None,
                    permission_map=perm_map or None,
                    source="gatt-enum",
                )
        except Exception as e:
            from bleep.core.log import print_and_log as _pal, LOG__DEBUG as _LD
            _pal(f"Database persistence error: {e}", _LD)

    if args.report:
        print(
            _dump(
                {
                    "landmine_report": device.get_landmine_report(),
                    "security_report": device.get_security_report(),
                }
            )
        )
    else:
        from bleep.ble_ops.common.conversion import format_gatt_tree
        from bleep.ble_ops.le.scan import _collect_device_props
        dev_name = device.get_name() if hasattr(device, 'get_name') else getattr(device, 'name', None)
        device_props = _collect_device_props(device)
        print(format_gatt_tree(
            mapping, mine_map, perm_map,
            device_name=dev_name,
            mac=_effective_addr,
            device_props=device_props,
        ))
    return 1 if _gatt_empty else 0
