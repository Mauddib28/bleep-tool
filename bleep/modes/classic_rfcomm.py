"""CLI dispatch handler for Classic RFCOMM channel enumeration."""

import sys


def run(args, output=None) -> int:
    from bleep.ble_ops.classic.sdp import discover_services_sdp, build_svc_map
    from bleep.ble_ops.classic.rfcomm import probe_rfcomm_channel
    from bleep.bt_ref.uuid_translator import get_uuid_name

    mac = args.address.strip().upper()
    print(f"[*] Discovering SDP services for {mac}...")
    try:
        records = discover_services_sdp(mac)
    except Exception as exc:
        print(f"[!] SDP discovery failed: {exc}", file=sys.stderr)
        return 1
    svc_map = build_svc_map(records)

    rfcomm_entries = []
    for name, entry in svc_map.items():
        ch = entry.get("channel") if isinstance(entry, dict) else entry
        if ch is not None:
            uuid = (entry.get("uuid") or "") if isinstance(entry, dict) else ""
            # ``build_svc_map`` stores an explicit ``None`` for unnamed records (so
            # ``get("name", name)`` would return that ``None``) and keys unnamed
            # records by their bare UUID. Resolve the UUID to its assigned-numbers
            # name (F3) so short forms like ``0x111F`` render as
            # "AG Hands-Free" instead of the raw handle string.
            raw_name = entry.get("name") if isinstance(entry, dict) else None
            svc_name = raw_name or (get_uuid_name(uuid) if uuid else None) or name
            rfcomm_entries.append((ch, svc_name, uuid))

    if not rfcomm_entries:
        print(f"[!] No RFCOMM channels found for {mac}")
        return 1

    rfcomm_entries.sort(key=lambda e: e[0])
    print(f"\n[+] RFCOMM Channels ({len(rfcomm_entries)} found):\n")
    print(f"  {'Ch':>3}  {'Service':<30}  {'UUID'}")
    print(f"  {'---':>3}  {'-'*30}  {'-'*36}")
    for ch, svc_name, uuid in rfcomm_entries:
        print(f"  {ch:>3}  {svc_name:<30}  {uuid}")

    if args.probe:
        print(f"\n[*] Probing {len(rfcomm_entries)} RFCOMM channel(s)...\n")
        for ch, svc_name, _ in rfcomm_entries:
            result = probe_rfcomm_channel(mac, ch, timeout=args.timeout)
            status = result.classification.upper()
            extra = ""
            if result.raw_response:
                preview = result.raw_response[:60]
                try:
                    extra = f" → {preview.decode('utf-8', errors='replace').strip()!r}"
                except Exception:
                    extra = f" → {preview.hex()}"
            elif result.error:
                extra = f" → {result.error}"
            print(f"  ch {ch:>2} ({svc_name}): [{status}]{extra}  ({result.latency_ms:.0f}ms)")

    if args.bind is not None:
        from bleep.ble_ops.classic.rfcomm import bind_rfcomm_channel
        try:
            dev_path = bind_rfcomm_channel(
                mac, args.bind, device_id=args.device_id,
            )
            print(f"\n[+] Bound {mac} ch {args.bind} → {dev_path}")
        except Exception as exc:
            print(f"\n[-] Bind failed: {exc}", file=sys.stderr)
            return 1

    return 0
