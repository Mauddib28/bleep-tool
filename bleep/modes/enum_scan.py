"""CLI dispatch handler for enum-scan mode."""

import sys


def run(args, output=None) -> int:
    from bleep.ble_ops.le import scan as _scan_mod
    from bleep.ble_ops.le.enum_controller import EnumerationController

    # F5b: honor --adapter. Validate up-front so a missing/not-ready controller
    # fails clearly instead of surfacing as a generic connect failure.
    adapter_name = getattr(args, "adapter", None)
    from bleep.core.preflight import require_adapter
    if not require_adapter(adapter_name):
        return 1

    from bleep.bt_ref.constants import ADAPTER_NAME, BLUEZ_NAMESPACE
    from bleep.bt_ref.utils import device_address_to_path
    from bleep.core.log import print_and_log, LOG__GENERAL

    resolved = adapter_name or ADAPTER_NAME
    path = device_address_to_path(
        args.address.strip().upper(), f"{BLUEZ_NAMESPACE}{resolved}"
    )
    print_and_log(f"[*] enum-scan adapter={resolved} path={path}", LOG__GENERAL)

    var = args.variant.lower()

    variant_kwargs: dict = {}
    if var == "pokey":
        variant_kwargs["rounds"] = getattr(args, "rounds", 3)
        variant_kwargs["verify"] = getattr(args, "verify", False)
    elif var in ("brute", "bruteforce"):
        if not getattr(args, "write_char", None):
            print("[!] --write-char required for brute enumeration", file=sys.stderr)
            return 1
        variant_kwargs["write_char"] = args.write_char
        if getattr(args, "range", None):
            try:
                s, e = args.range.split("-")
                variant_kwargs["value_range"] = (int(s, 16), int(e, 16))
            except ValueError:
                print("[!] Invalid --range format, expected AA-BB", file=sys.stderr)
                return 1
        if getattr(args, "patterns", None):
            variant_kwargs["patterns"] = [p.strip() for p in args.patterns.split(",") if p.strip()]
        if getattr(args, "payload_file", None):
            try:
                with open(args.payload_file, "rb") as pf:
                    variant_kwargs["payload_file"] = pf.read()
            except Exception as exc:
                print(f"[!] Failed to read payload file: {exc}", file=sys.stderr)
                return 1
        variant_kwargs["force"] = getattr(args, "force", False)
        variant_kwargs["verify"] = getattr(args, "verify", False)

    controller = EnumerationController(args.address, adapter_name=adapter_name)
    result = controller.enumerate(mode=var, **variant_kwargs)

    if not result.success:
        print(f"[-] Enumeration failed: {args.address}", file=sys.stderr)
        if result.error_summary:
            print(f"    {result.error_summary}", file=sys.stderr)
        for annotation in result.annotations:
            print(f"    [{annotation.error_type}] {annotation.details}", file=sys.stderr)
        return 1

    data = result.data or {}
    extra = data.pop("_variant_extra", {}) if isinstance(data, dict) else {}

    if data:
        if _obs := getattr(_scan_mod, "_obs", None):
            try:
                _scan_mod._persist_mapping(args.address, data)
            except Exception as e:
                from bleep.core.log import print_and_log as _pal, LOG__DEBUG as _LD
                _pal(f"Database persistence warning: {e}", _LD)

    result.persist_security_maps(args.address, source=f"enum-scan:{var}")

    try:
        from bleep.core import observations as _obs_stamp
        from bleep.core.time_utils import utc_now_iso

        _obs_stamp.upsert_device(
            args.address,
            enumerated_by=resolved,
            enumerated_at=utc_now_iso(),
        )
    except Exception:
        pass

    if data and isinstance(data, dict):
        from bleep.ble_ops.common.conversion import format_gatt_tree
        print(format_gatt_tree(
            data,
            result.landmine_map,
            result.permission_map,
            mac=args.address,
            changed_chars=extra.get("changed_chars"),
            device_props=extra.get("device_props"),
        ))
    else:
        import json
        print(json.dumps(data, indent=2, default=str))

    if result.annotations:
        print(f"\n[*] Completed in {result.attempts} attempt(s) with {len(result.annotations)} annotation(s):", file=sys.stderr)
        for annotation in result.annotations:
            print(f"    [{annotation.error_type}] {annotation.details}", file=sys.stderr)

    return 0
