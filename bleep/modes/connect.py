"""CLI dispatch handler for BLE connect mode."""

import sys


def run(args, output=None) -> int:
    if not getattr(args, "ble_only", False):
        from bleep.pairing import find_device_path

        _conn_dev_path = find_device_path(args.address.strip().upper())
        if _conn_dev_path is not None:
            from bleep.modes.debug_connect import get_device_transport

            _conn_transport = get_device_transport(_conn_dev_path)
            if _conn_transport in ("br-edr", "dual"):
                from bleep.modes.classic_connect import main as _cc_main

                cc_argv = [args.address]
                if not getattr(args, "activate_profiles", True):
                    cc_argv.append("--no-profiles")
                return _cc_main(cc_argv) or 0

    try:
        from bleep.ble_ops.le.connect import (
            connect_and_enumerate__bluetooth__low_energy as _connect_enum,
        )
        from bleep.core.errors import (
            DeviceNotFoundError,
            ConnectionError,
            NotReadyError,
            NotAuthorizedError,
            ServicesNotResolvedError,
        )

        device, mapping, mine_map, perm_map = _connect_enum(args.address)
        print(f"[+] Successfully connected to {args.address}", file=sys.stdout)

        # Render the enumerated GATT database (reuses the shared formatter used by
        # the ``gatt-enum`` mode) so ``connect`` fulfils its "Connect + GATT
        # enumerate" contract rather than discarding the mapping.
        from bleep.ble_ops.common.conversion import format_gatt_tree
        from bleep.ble_ops.le.scan import _collect_device_props
        _dev_name = device.get_name() if hasattr(device, "get_name") else getattr(device, "name", None)
        print(format_gatt_tree(
            mapping, mine_map, perm_map,
            device_name=_dev_name,
            mac=args.address,
            device_props=_collect_device_props(device),
        ))

        try:
            from bleep.ble_ops.le.scan import _collect_device_props, _persist_mapping, _enrich_device_info_from_props
            from bleep.core import observations as _obs_connect

            addr = device.get_address() if hasattr(device, 'get_address') else args.address.upper()
            name = device.get_name() if hasattr(device, 'get_name') else None
            device_props = _collect_device_props(device)
            device_info = {'name': name}
            _enrich_device_info_from_props(device_info, device_props)
            _obs_connect.upsert_device(addr, **device_info)
            _persist_mapping(addr, mapping)
            from bleep.analysis.device_type_classifier import DeviceTypeClassifier

            classifier = DeviceTypeClassifier()
            ctx = {
                "device_class": device_info.get("device_class"),
                "address_type": device_info.get("addr_type"),
                "uuids": [str(u) for u in device_props.get("UUIDs", [])],
                "connected": True,
            }
            cls_result = classifier.classify_with_mode(
                mac=addr, context=ctx, scan_mode="naggy", use_database_cache=True,
            )
            _obs_connect.upsert_device(addr, device_type=cls_result.device_type)
        except Exception:
            pass

        return 0
    except DeviceNotFoundError as exc:
        print(
            f"[!] Device {args.address} not found during scan",
            file=sys.stderr,
        )
        print(
            "[*] Suggestions: Ensure the device is powered on, in range, and advertising.",
            file=sys.stderr,
        )
        print(
            "[*] Try running 'bleep scan' first to verify the device is discoverable.",
            file=sys.stderr,
        )
        return 1
    except NotReadyError as exc:
        print(
            "[!] Bluetooth adapter not ready",
            file=sys.stderr,
        )
        print(
            "[*] Ensure the adapter is powered on: 'bluetoothctl power on'",
            file=sys.stderr,
        )
        return 1
    except NotAuthorizedError as exc:
        print(
            f"[!] Connection requires pairing/authorization: {exc}",
            file=sys.stderr,
        )
        print(
            "[*] The device may require pairing. Try pairing first or use 'bleep agent' mode.",
            file=sys.stderr,
        )
        return 1
    except ConnectionError as exc:
        print(
            f"[!] Connection failed: {exc}",
            file=sys.stderr,
        )
        return 1
    except ServicesNotResolvedError as exc:
        print(
            f"[!] Services not resolved for device {args.address}",
            file=sys.stderr,
        )
        print(
            "[*] The device connected but GATT services did not resolve in time.",
            file=sys.stderr,
        )
        print(
            "[*] This may indicate the device is slow to respond or has connectivity issues.",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        print(
            f"[!] Connection error: {exc}",
            file=sys.stderr,
        )
        import traceback
        from bleep.core.log import print_and_log, LOG__DEBUG

        print_and_log(f"Traceback:\n{traceback.format_exc()}", LOG__DEBUG)
        return 1
