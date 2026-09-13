"""``refresh-refs`` mode — regenerate BLEEP's committed reference-data modules.

Wraps the two in-package reference updaters behind a single command so the
"pull the latest assigned numbers" workflow is one step instead of two
module invocations:

* **BT SIG assigned numbers** → ``bt_ref/uuids.py``          (``update_ble_uuids``)
* **BT SIG CoD + Mesh tables** → ``bt_ref/cod.py`` / ``bt_ref/mesh_ids.py`` (``update_extra_refs``)
* **BlueZ SDP attribute IDs** → ``bt_ref/sdp_attr_ids.py``   (``update_bluez_refs``)
* **SIG profile SDP attr IDs** → ``bt_ref/sdp_profile_attr_ids.py`` (``update_sig_sdp_attr_ids``)
* **Vendor/community adv specs** → ``bt_ref/vendor_adv_specs.py`` (``update_vendor_specs``)
* **IEEE OUI vendor database** → ``bt_ref/oui.py``           (``update_oui``)
* **USB-IF ID database** → ``bt_ref/usb_ids.py``             (``update_usb_ids``)

Scopes: a bare ``refresh-refs`` runs everything. ``--sig-only`` / ``--vendor-only``
/ ``--oui-only`` / ``--usb-only`` (mutually exclusive) each restrict the run to one
group; OUI and USB-IF are external (IEEE / USB-IF) registries, not SIG or
vendor-adv-spec data, hence their own scope flags.

Both updaters are network-best-effort and self-contained: on failure they leave
the previously committed module untouched (vendor specs) or fall back to cached
YAML (BT SIG), so a refresh never corrupts the committed reference material.
This command performs no Bluetooth I/O and therefore requires no adapter.
"""
from __future__ import annotations

from typing import Any

from bleep.core.log import LOG__GENERAL, print_and_log


def _refresh_sig() -> None:
    from bleep.bt_ref import update_ble_uuids

    print_and_log(
        "[*] Refreshing BT SIG assigned numbers → bt_ref/uuids.py", LOG__GENERAL
    )
    update_ble_uuids.regenerate()


def _refresh_extra() -> None:
    from bleep.bt_ref import update_extra_refs

    print_and_log(
        "[*] Refreshing BT SIG CoD + Mesh tables → bt_ref/cod.py, bt_ref/mesh_ids.py",
        LOG__GENERAL,
    )
    update_extra_refs.regenerate()


def _refresh_bluez() -> None:
    from bleep.bt_ref import update_bluez_refs

    print_and_log(
        "[*] Refreshing BlueZ SDP attribute IDs → bt_ref/sdp_attr_ids.py",
        LOG__GENERAL,
    )
    update_bluez_refs.regenerate()


def _refresh_sig_sdp_attr_ids() -> None:
    from bleep.bt_ref import update_sig_sdp_attr_ids

    print_and_log(
        "[*] Refreshing SIG profile SDP attribute IDs → bt_ref/sdp_profile_attr_ids.py",
        LOG__GENERAL,
    )
    update_sig_sdp_attr_ids.regenerate()


def _refresh_vendor(local_path: str | None) -> None:
    from bleep.bt_ref import update_vendor_specs

    print_and_log(
        "[*] Refreshing vendor/community adv specs → bt_ref/vendor_adv_specs.py",
        LOG__GENERAL,
    )
    update_vendor_specs.regenerate(local_path=local_path)


def _refresh_oui() -> None:
    from bleep.bt_ref import update_oui

    print_and_log(
        "[*] Refreshing IEEE OUI vendor database → bt_ref/oui.py", LOG__GENERAL
    )
    update_oui.regenerate()


def _refresh_usb_ids() -> None:
    from bleep.bt_ref import update_usb_ids

    print_and_log(
        "[*] Refreshing USB-IF ID database → bt_ref/usb_ids.py", LOG__GENERAL
    )
    update_usb_ids.regenerate()


def run(args: Any) -> int:
    """Regenerate the selected reference-data module(s).

    Returns 0 on success, 1 if a selected updater raised or an invalid flag
    combination was supplied.
    """
    sig_only = getattr(args, "sig_only", False)
    vendor_only = getattr(args, "vendor_only", False)
    oui_only = getattr(args, "oui_only", False)
    usb_only = getattr(args, "usb_only", False)
    local_path = getattr(args, "local_path", None)

    # argparse's mutually-exclusive group normally rejects multiple scopes, but
    # keep a defensive guard for direct run() callers (e.g. tests).
    if sum(bool(x) for x in (sig_only, vendor_only, oui_only, usb_only)) > 1:
        print_and_log(
            "[-] --sig-only / --vendor-only / --oui-only / --usb-only are mutually exclusive",
            LOG__GENERAL,
        )
        return 1

    any_scope = sig_only or vendor_only or oui_only or usb_only
    do_sig = sig_only or not any_scope
    do_vendor = vendor_only or not any_scope
    do_oui = oui_only or not any_scope
    do_usb = usb_only or not any_scope

    failures = []
    if do_sig:
        try:
            _refresh_sig()
        except Exception as exc:  # noqa: BLE001 - report, do not crash the CLI
            print_and_log(f"[-] BT SIG refresh failed: {exc}", LOG__GENERAL)
            failures.append("BT SIG")
        # CoD + Mesh are also SIG assigned numbers, but land in separate generated
        # modules; refresh them alongside the SIG UUIDs (independent failure).
        try:
            _refresh_extra()
        except Exception as exc:  # noqa: BLE001
            print_and_log(f"[-] BT SIG CoD/Mesh refresh failed: {exc}", LOG__GENERAL)
            failures.append("CoD/Mesh")
        # SDP universal attribute-ID labels are sourced from upstream BlueZ
        # (lib/sdp.h), not the SIG repo, but are reference data refreshed on the
        # same "pull latest" workflow (independent failure).
        try:
            _refresh_bluez()
        except Exception as exc:  # noqa: BLE001
            print_and_log(f"[-] BlueZ SDP attribute-ID refresh failed: {exc}", LOG__GENERAL)
            failures.append("BlueZ SDP")
        # Profile-scoped SDP attribute IDs are SIG assigned numbers
        # (service_discovery/attribute_ids/*.yaml) → separate generated module
        # (independent failure).
        try:
            _refresh_sig_sdp_attr_ids()
        except Exception as exc:  # noqa: BLE001
            print_and_log(f"[-] SIG profile SDP attribute-ID refresh failed: {exc}", LOG__GENERAL)
            failures.append("SIG profile SDP")
    if do_vendor:
        try:
            _refresh_vendor(local_path)
        except Exception as exc:  # noqa: BLE001
            print_and_log(f"[-] Vendor-spec refresh failed: {exc}", LOG__GENERAL)
            failures.append("vendor specs")
    # External IEEE / USB-IF registries: not SIG or vendor-adv-spec data, refreshed
    # on the same "pull latest" workflow (independent failures — one never blocks
    # the other, and neither overwrites its committed module on a failed fetch).
    if do_oui:
        try:
            _refresh_oui()
        except Exception as exc:  # noqa: BLE001
            print_and_log(f"[-] IEEE OUI refresh failed: {exc}", LOG__GENERAL)
            failures.append("IEEE OUI")
    if do_usb:
        try:
            _refresh_usb_ids()
        except Exception as exc:  # noqa: BLE001
            print_and_log(f"[-] USB-IF ID refresh failed: {exc}", LOG__GENERAL)
            failures.append("USB-IF IDs")

    if failures:
        print_and_log(
            f"[-] Reference refresh completed with errors: {', '.join(failures)}",
            LOG__GENERAL,
        )
        return 1
    print_and_log(
        "[+] Reference data refresh complete. Restart BLEEP so imports pick up "
        "the regenerated tables.",
        LOG__GENERAL,
    )
    return 0
