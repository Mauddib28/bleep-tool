# Central TODO tracker

This page aggregates open tasks referenced across the project so contributors have a single place to check before starting work.  **Edit directly** whenever you add / complete an item – no special tooling required.

---

## DB examination / analysis / reporting enhancements (2026-08-23)

> Accepted by the user 2026-08-23 after a three-pass review + live proof-of-concept
> against a real 145 MB `~/.bleep/observations.db` (schema v18, 50,492 devices). Goal:
> first-class **date-windowed** device selection, batch reporting, target-list export,
> opt-in RPA/identity collapse (with a mandatory non-collapsed view for compare/contrast),
> unlimited device export, and timezone-aware windows. **Additive only — NO schema/migration
> change** (v19 first_seen index was considered and *declined*; `--seen-basis first|any`
> full-scan ~3s/50k rows is accepted). Full `tests/` suite must stay green and lint-clean.
>
> **Locked design decisions (2026-08-23):** `--seen-basis` default `last` (indexed via
> `idx_devices_last_seen`; `first`/`any` selectable, full-scan); `--tz` default `UTC`
> (matches naive-UTC storage, `core/time_utils.utc_now_iso`); identity collapse **OFF by
> default**, `--group-identity` default strategy `name`, raw view always available,
> `--identity-contrast` shows both; `db report` default `--limit 500`, `--all-in-window`
> required to exceed.
>
> **Key review findings driving the design (evidence-backed):**
> - The AoI *renderer* `AOIAnalyser.generate_aggregate_report()` already handles
>   never-analyzed advert-only devices (loads via `get_device_detail`, runs
>   `analyze_device_data(persist=False)` for missing analysis, and splits reached vs
>   "Not Reachable"). Only the *device list* `get_aoi_analyzed_devices()` (INNER JOIN
>   `aoi_analysis`) was empty in-window. → **`db report` is a thin wrapper over the existing
>   engine, not a new renderer.** (POC: 6 mixed in-window MACs → 3 analyzed / 3 not-reachable,
>   no DB writes.)
> - No IRK column exists → RPA collapse must be **heuristic**, never cryptographic. On real
>   data collapse is weak (46,338 random-addr in-window → name-anchored folds only 194→45
>   identities; full-payload 103→29) because address rotation co-occurs with name/payload
>   rotation. Reports MUST always print `raw N vs collapsed M (strategy=…, heuristic, no IRK)`
>   so the raw/collapsed delta is itself the analytical signal.
> - Timestamps are naive-UTC ISO 8601 → lexicographic range compare is valid; `until` is an
>   **exclusive** upper bound (callers pass next-midnight for an inclusive end date).
>
> **IMPLEMENTED 2026-08-23.** All items landed additively (no schema change). Files:
> `bleep/core/time_utils.py` (`local_date_range_to_utc`), `bleep/core/observations/_devices.py`
> (`get_devices` window params, `export_device_data` caps), `bleep/analysis/identity.py` (new),
> `bleep/cli/parsers/db.py` (shared `_add_db_arguments` + `report` action + flags),
> `bleep/modes/db.py` (`_resolve_window`/`_write_target_list`/`_emit_identity_clusters`/
> `_run_report`, `_print_device_rows` extraction, standalone `main()` reuses shared parser).
> Docs: `observation_db.md`, `cli_usage.md`. Tests: `tests/test_db_reporting_enhancements.py`
> (21 new), `tests/test_data_pipeline_fixes.py` (pagination-call assertion updated for the
> additive kwargs). Verified: 480 targeted tests pass, 0 lint errors, live smoke on the real
> 145 MB DB (window counts match direct SQL; report splits reached/not-reached; payload
> collapse folds 47,686→41,220; export-targets round-trips through `aoi._iter_macs`).

- [x] ✅ **DB-1: date-range filtering (`get_devices` + `db list`)** — extend the single query
  funnel `get_devices()` with `since=None, until=None, seen_basis="last"` (`seen_basis ∈
  {first,last,any}`; `until` exclusive). WHERE branches: `last` → `last_seen >= since AND
  last_seen < until` (indexed); `first` → same on `first_seen`; `any`/overlap → `first_seen <
  until AND last_seen >= since`. Wire `--since --until --seen-basis` onto `db list` (both the
  human `list_devices()` path and the json/quiet `emit_result` path in `modes/db.py:run()`),
  and mirror the flags in the standalone `db.main()` argparse to prevent drift. Backward-
  compatible: all new params optional, existing callers unchanged.
  (`bleep/core/observations/_devices.py:get_devices`, `bleep/modes/db.py`,
  `bleep/cli/parsers/db.py`)
- [x] ✅ **DB-2: `bleep db report` (batch, date-scoped)** — new `report` action that selects the
  windowed/filtered address list via `get_devices()` (DB-1) then **delegates to**
  `AOIAnalyser(use_db=True).generate_aggregate_report(addrs, format)` and saves via
  `save_report()`/`--out`; honors `OutputContext` (`--json`/`--quiet`). Enforces default
  `--limit 500` unless `--all-in-window`. Accepts `--status/--name` filters, `--format
  {markdown,json,text}`, and the identity flags from DB-4. No new scoring/reach logic (reuse).
  (`bleep/modes/db.py`, `bleep/cli/parsers/db.py`)
- [x] ✅ **DB-3: `db list --export-targets PATH`** — dump the windowed/filtered `get_devices()`
  rows as an AoI-ingestable JSON array of `{address,name,device_type,first_seen,last_seen}`
  objects (the `address` key is what `bleep/modes/aoi.py:_iter_macs` consumes). ~15 lines in
  the `list` handler. (`bleep/modes/db.py`, `bleep/cli/parsers/db.py`)
- [x] ✅ **DB-4: opt-in identity/RPA collapse + mandatory non-collapsed view** — new pure,
  non-destructive module `bleep/analysis/identity.py` exposing
  `collapse_identities(devices, strategy="name") -> {clusters, raw_count, collapsed_count,
  strategy}`. Strategies: `name` (default), `name_mfr`, `payload` (delegates to
  `bleep/analysis/adv_dissect.dissect_advertisement()` — the same primitive
  `survey._round_signature` uses; no fingerprint logic duplicated). Never writes DB, never
  mutates rows. Consumed by `db list --group-identity[=strategy]` (annotation/collapsed view)
  and `db report --group-identity` / `--identity-contrast` (emit BOTH raw and collapsed
  tables). Default OFF everywhere. Every collapsed output prints the `raw N vs collapsed M
  (strategy=…, heuristic, no IRK)` provenance line. (`bleep/analysis/identity.py`,
  `bleep/modes/db.py`, `bleep/cli/parsers/db.py`)
- [x] ✅ **DB-5: unlimited `db export`** — `export_device_data(mac, char_limit=500, adv_limit=100)`
  where `0`/`None` drops the `LIMIT` clause (currently hard-coded `LIMIT 500` for char_history
  and `LIMIT 100` for adv_reports at `_devices.py:405,412`). Add `--max-history N` /
  `--max-adv N` (0 = all) to the `db export` handler. Defaults preserve current behavior.
  (`bleep/core/observations/_devices.py:export_device_data`, `bleep/modes/db.py`,
  `bleep/cli/parsers/db.py`)
- [x] ✅ **DB-6: timezone-aware windows** — new `local_date_range_to_utc(since_date, until_date,
  tz="UTC") -> (utc_naive_start_iso, utc_naive_end_exclusive_iso)` in `core/time_utils.py`
  (stdlib `zoneinfo`; inclusive `until` → `+1 day`). Add `--tz` (default `UTC`) to
  `db list`/`db report`; convert local date bounds → UTC-naive before the string compare.
  (POC: `America/New_York` Aug 6–9 → `2026-08-06T04:00:00`..`2026-08-10T04:00:00`.)
  (`bleep/core/time_utils.py`, `bleep/modes/db.py`, `bleep/cli/parsers/db.py`)
- [x] ✅ **DB-7: docs + tests** — update `bleep/docs/observation_db.md` / `cli_usage.md` with the
  new `db list` flags and `db report` action (incl. the RPA-collapse caveat and window
  semantics). Tests: `get_devices` window branches (first/last/any + exclusive upper bound);
  `local_date_range_to_utc` (UTC + offset tz + DST edge); `export_device_data` limit=0;
  `collapse_identities` (name/name_mfr/payload, singletons, raw/collapsed counts);
  integration `db report` over a fixture DB (mixed enumerated + advert-only) asserting the
  reached/not-reached split and `--json` shape; `db list --export-targets` round-trips through
  `aoi._iter_macs`. Regression: existing `bleep db` handler tests pass with new optional flags.

### DB-8 — Device-name audit (2026-08-26)

> Accepted by the user 2026-08-26 after a plan review. Goal: separate the *real* observed
> device names from the flood of MAC-derived BlueZ default aliases, and flag any name that
> is MAC-shaped but does **not** match the device's own address. Additive, read-only.

- [x] ✅ **DB-8: classifier** — `classify_name(name, mac)` + `is_mac_shaped`, `normalize_mac`,
  `NAME_CLASSES` in `bleep/analysis/identity.py`. Buckets: `placeholder` (MAC-shaped ∧ ==own
  MAC), `real`, `empty`, `foreign_mac` (MAC-shaped ∧ !=own MAC). Normalises `:`/`-`/`_` + case;
  anchored regex so embedded-MAC substrings stay `real`. `_clean_name`/DB-4 collapse untouched.
- [x] ✅ **DB-8: `--name-audit` (list + report)** — `_name_audit`/`_emit_name_audit`/
  `_render_name_audit_md` + `_full_device_record`/`_name_summary` in `bleep/modes/db.py`; flags
  `--name-audit`/`--name-sample`/`--name-detail-limit` in `bleep/cli/parsers/db.py`. Counts all
  four buckets; full per-device detail for empty/foreign_mac; **full collected record** (DB-5
  uncapped `export_device_data`) + compact `summary` per real-named device (grouped by name,
  capped by `--name-detail-limit`, 0=all); `--name-sample` of placeholders. `foreign_mac` always
  surfaced (terminal `[!] ANOMALY` banner + JSON/report Anomalies). Report appends `## Name Audit`
  and adds a `name_audit` JSON block (mirrors `--identity-contrast`).
- [x] ✅ **DB-8: tests + docs** — `classify_name` units + `db list`/`db report --name-audit`
  integration in `tests/test_db_reporting_enhancements.py` (14 new, 35 total, all green);
  `observation_db.md` Name audit subsection, `cli_usage.md` rows, `debug_mode_db.md`
  example/flag reference, `changelog.md`.

### DB-9 — `db report` Reconnaissance Analytics (`--recon`) (2026-08-26)

> Accepted by the user 2026-08-26 after a plan review. Goal: add a top-level
> **`## Reconnaissance Analytics`** section to `db report` aggregating, across the
> windowed/filtered selection: (A) a unique-SDP inventory with counts, (B) an
> OUI / address-type breakdown with **IEEE OUI vendor decode**, and (C) pattern
> detection + hex comparison + decode across **all forms of collected hex**
> (manufacturer data, service data, advertising-data AD structures, SDP raw, and —
> under a detail flag — characteristic values). Opt-in, additive, read-only.
>
> **User decisions incorporated:** (1) source the OUI database through the existing
> `bt_ref` reference-data framework (same updater+generated-module pattern as
> `usb_ids.py`/SIG UUIDs) with a **graceful "vendor unknown"** resolver; (2) ship a
> **single umbrella `--recon` flag** but implement it over modular per-analytic
> builders so granular flags can be exposed later without refactor; (3) new
> **top-level `## Reconnaissance Analytics`** section; (4) OUI vendor decode IS worth
> the data footprint — bundle the generated OUI module; (5) include **all** collected
> hex, with characteristic-value hex gated behind a **`--recon-detail`** flag;
> (6) the whole feature is **flag-gated**. Effective/efficient/minimal — reuse
> `dissect_persisted_record`, `_resolve_company_name`, `decode_characteristic_value`,
> and the `bt_ref` framework; no shared `AOIAnalyser` engine change.

- [x] ✅ **DB-9a: OUI reference data (bt_ref framework).** Add `bleep/bt_ref/update_oui.py`
  (mirrors `update_usb_ids.py`: download → parse → emit generated module) sourcing the
  **IEEE MA-L registry** (`https://standards-oui.ieee.org/oui/oui.csv`; fallback
  Wireshark `manuf`). Generates `bleep/bt_ref/oui.py` with
  `OUI_VENDORS = {"AABBCC": "Org Name", …}` (24-bit MA-L, upper-hex keys) + a
  `get_oui_vendor(mac) -> Optional[str]` helper. MA-M/MA-S (28/36-bit) intentionally
  **not** decoded (would misattribute the shared 24-bit prefix) — returns `None`
  (future expansion).   Regeneration is offline/one-shot, like `usb_ids.py`. *(Done: IEEE returned HTTP
  418 to the sandbox, so generation fell back to the Wireshark `manuf` source —
  39,769 MA-L OUIs; `oui.py` committed.)*
- [x] ✅ **DB-9b: graceful resolver.** Add `resolve_oui(mac) -> Optional[str]` to
  `bleep/ble_ops/common/conversion.py` next to `_resolve_company_name`, with a
  module-level cache and lazy import of `bt_ref.oui`; returns `None` (→ "vendor
  unknown") when the OUI   module is absent or the prefix is unknown. **Never raises.**
- [x] ✅ **DB-9c: batched observation helpers.** Add `get_sdp_inventory(macs)` and
  `get_characteristic_values(macs)` to `bleep/core/observations/_devices.py`
  (+ `__init__` exports) — single `WHERE mac IN (…)` selects returning
  `(mac,name,uuid)` SDP rows and `(mac,char_uuid,value)` char rows respectively, so
  the aggregate never issues N per-device `get_device_detail` loads. OUI (B) and
  mfr/service/AD analysis (C) read the columns already returned by `get_devices`
  (  `SELECT * FROM devices`) — **zero** extra queries.
- [x] ✅ **DB-9d: analytics builders (`bleep/modes/db.py`).** Umbrella
  `_recon_analytics(devices, macs, *, include_chars=False)` composing modular
  builders (future granular-flag ready):
  * `_recon_sdp_inventory(macs)` — unique `(name,uuid)` → distinct-device + record
    counts, sorted desc (`Name (UUID) : count`).
  * `_recon_oui(devices)` — bucket by `addr_type`: `public` → OUI tally + `resolve_oui`
    vendor (graceful unknown); `random` → sub-classify by first-octet top-2-bits into
    RPA(resolvable)/static-random/NRPA and label OUI **not** a vendor; `null` counted.
  * `_recon_adv(devices, include_chars)` — per device via `dissect_persisted_record`
    aggregate: manufacturer data grouped by `company_id` (decoded `company`),
    unique-payload tally + **longest-common-prefix** ("pattern") + **repeated-payload
    flag** (identical hex across ≥K devices → possible static/identity leak) + decoded
    representative; service data grouped by UUID (protocol decode); advertising-data AD
    structures tallied by `ad_type`. When `include_chars`, add characteristic-value hex
    (`get_characteristic_values`) grouped by `char_uuid`, unique-hex tally +
    `decode_characteristic_value`.
- [x] ✅ **DB-9e: render + wire.** `_render_recon_md(recon)` emits the top-level
  `## Reconnaissance Analytics` section (subsections SDP Inventory / OUI &
  Address-Type / Advertisement Data Analysis [/ Characteristic Values]); wire into
  `_run_report` exactly where `--name-audit` is (JSON `recon` sibling block;
  markdown/text section append; terminal summary banner). Flags `--recon`
  (umbrella) + `--recon-detail` (adds characteristic-value hex) in
  `bleep/cli/parsers/db.py` `_add_db_arguments`.
- [x] ✅ **DB-9f: tests + docs.** Unit: `get_oui_vendor`/`resolve_oui` (known + unknown +
  missing-module graceful), addr-type/OUI bucketing incl. RPA sub-type,
  SDP-inventory aggregation, mfr/service unique-payload tally + common-prefix +
  repeated-payload flag, characteristic-hex under `--recon-detail`. Integration:
  `db report --recon [--recon-detail] --json` block + markdown section over a seeded
  DB (public+random+RPA, SDP records, shared/rotating mfr payloads, char values).
  Docs: `observation_db.md` (Reconnaissance Analytics subsection), `cli_usage.md`
  (report row + flags), `changelog.md`, and mark this DB-9 block complete.
  *(Done: 11 new tests — `TestOuiResolver`, `TestReconHelpers`, `TestReconReport` —
  57 total in the DB suite, all green; docs updated incl. `debug_mode_db.md`.)*
- [x] ✅ **DB-9g: wire OUI + USB-IF into `refresh-refs` (2026-08-27).** Added
  `update_oui.regenerate()` / `update_usb_ids.regenerate()` wrappers (raise on the
  generators' `False` return) and drove both from `bleep/modes/refresh_refs.py`
  under new mutually-exclusive scope flags `--oui-only` / `--usb-only` (bare
  `refresh-refs` runs all seven updaters; independent-failure semantics; committed
  module untouched on a failed fetch). Parser flags in `cli/parsers/utility.py`;
  `tests/test_refresh_refs.py` reworked to patch all updaters + new routing/parser
  cases (17 tests, green); docs `api_specification.md` §3.5.3 (flipped
  `update_usb_ids` ❌→✅, added `update_oui`), `uuid_translation.md` (7-updater
  table + examples), `cli_usage.md`, `observation_db.md`, `changelog.md`.
- [x] ✅ **DB-9h: per-device SDP Discovery aggregate inventory (2026-08-27).** The
  AoI Security Report's per-device `## SDP Discovery` section (markdown + text
  renderers in `aoi_analyser.py`, shared by `db report` and `aoi`) now renders a
  collapsed service inventory instead of one bullet per stored record. New
  `_aggregate_sdp_inventory` / `_format_sdp_inventory_row` helpers +
  `services_inventory` field on `_analyse_sdp_records()` group by
  `(name, uuid, channel)` with occurrence counts (`Name (UUID, ch N) : count`,
  `N unique of M records` header) — mirrors the DB-9 aggregate inventory but
  per-device; RFCOMM channel is in the key so same-service-different-channel stays
  distinct. `services_found` retained (additive). Verified live on a 899-record
  device (→ 42 rows). Tests in `tests/test_aoi_augmentation.py`; docs
  `aoi_security_algorithms.md` §4b, `aoi_mode.md`, `changelog.md`.
- [x] ✅ **DB-9i: report readability polish (2026-08-27).** Unified every
  count-bearing block to `<unique entry> : <count>` notation (OUI breakdown,
  random-address types, Advertisement Data groups; vulnerability `(×N)` kept as an
  occurrence count). SDP + OUI inventories (aggregate *and* per-device SDP
  Discovery) now render as markdown tables by default with a new `--report-bullets`
  flag for the unified bullet form (threaded through
  `generate_aggregate_report(..., bullets=…)`); both capped at `_RECON_TOP_N=50`
  with a JSON-block pointer when truncated. Part B: shared `format_uuid_display`
  (`0X1200`→`0x1200`), hexdump-convention ASCII (`_ascii_from_hex`, non-printable →
  `.`), `- None.` for empty `## Services`/`## Advertisement Dissection`,
  `Flags & enrichment:` sub-label under per-device SDP, and thousands separators.
  The `Flags & enrichment` block collapses repeated security flags/anomalies to
  unique `… : count` rows in their own tables (`_collapse_counted`,
  `_collapse_anomalies`, `_render_flags_enrichment_md/_text`), so a 600+-line flag
  dump becomes two rows; bullet form honoured under `--report-bullets`.
  Rendering-only (JSON `recon` unchanged). Tests: `TestReconRenderMarkdown` +
  hexdump/None/table/bullet cases; docs `cli_usage.md`, `observation_db.md`,
  `debug_mode_db.md`, `api_specification.md`, `changelog.md`.

---

## Beacon-discovery remediation (R1/R2) + adapter selection (F5a/b/c) — [x] IMPLEMENTED & VERIFIED (2026-08-13)

> Two linked workstreams from `BEACON_DISCOVERY_R1_R2_PLAN.md` / `SCAN_ADAPTER_F5_PLAN.md`.
> **R1/R2** fixes BlueZ `STOP_CLEARS` (unpaired non-connectable `Device1` objects — classic
> iBeacon/Eddystone — vanish on `StopDiscovery`, so post-stop `GetManagedObjects` never saw
> them). **F5** wires the previously-parsed-but-ignored `--adapter` flag through the three
> scan surfaces that dropped it. All changes additive/back-compat (new params default to
> `None`/`hci0` → default controller); no schema change. Full details in `changelog.md`
> ("R1/R2 …", "F5 …", "F5b/F5c …"). Live-confirmed against rotating classic beacon
> `10:20:BA:46:AE:D5` (Apple iBeacon `0x004C` ↔ Eddystone-URL, ~90 s rotation).

- [x] **R1 — pre-stop harvest.** `DeviceManager._timeout` snapshots via `_compose_harvest()`
  **before** `StopDiscovery`; `_native_scan` / `create_and_return__*` consume
  `take_last_harvest()`; `AdapterSession.harvest` uses `snapshot_discovered_devices()` while
  `Discovering` is still true. Shared mapper `build_discovered_device_dict`.
  (`bleep/dbuslayer/manager.py`, `bleep/dbuslayer/adapter.py`, `bleep/ble_ops/le/scan.py`)
- [x] **R2 — session census.** Per-session `_session_devices` built from `InterfacesAdded` /
  `PropertiesChanged` (last-shot mfr/service data); `InterfacesRemoved` marks removed but
  **keeps** the row until the next `start_discovery`. Harvest merges GMO + census by MAC;
  `_ensure_session_state` lazily initializes fields for partially-constructed stubs.
  (`bleep/dbuslayer/manager.py`, `bleep/dbuslayer/signals.py`)
- [x] **iBeacon LE-transport note** — classic non-connectable iBeacons require an LE discovery
  filter (`--transport le` / LE survey rounds / `scan --variant naggy`); not visible on
  BR/EDR-only inquiry. (docs: `changelog.md`, `beacon_identification.md`, `ble_scan_modes.md`)
- [x] **F5a — `scan --adapter`.** `adapter_name` (keyword-only) threaded through `_native_scan`,
  `passive_scan`, `naggy_scan`, `pokey_scan`, `brute_scan`; `pokey`/`brute` also fixed to
  forward `transport` (pre-existing sibling defect). `dispatch.py` gates on
  `require_adapter(args.adapter)` — non-zero exit, no silent fallback.
  (`bleep/ble_ops/le/scan.py`, `bleep/cli/dispatch.py`, `bleep/core/preflight.py`)
- [x] **F5b — `enum-scan --adapter`.** `adapter_name` threaded
  `EnumerationController(adapter_name=…)` → `connect_and_enumerate__bluetooth__low_energy` →
  `naggy_enum`/`pokey_enum`/`brute_enum` → `_base_enum` → same connect primitive
  (`_Adapter(adapter_name)` at PRE-FLIGHT 0). `enum_scan.run` gates on `require_adapter`.
  (`bleep/ble_ops/le/connect.py`, `bleep/ble_ops/le/scan.py`,
  `bleep/ble_ops/le/enum_controller.py`, `bleep/modes/enum_scan.py`)
- [x] **F5c — `classic-scan --adapter`.** `classic_scan.run` builds `_Adapter(args.adapter)`
  (else default) for the BR/EDR inquiry; not-ready error names the adapter.
  (`bleep/modes/classic_scan.py`)
- [x] **Tests** — `tests/test_discovery_harvest.py` (R1/R2), stub updates in
  `test_survey_multi` / `test_discovery_error_surfacing`; `tests/test_scan_variants.py` +
  `tests/test_scan_cli_adapter.py` (F5a); `tests/test_enum_controller_sr_n3.py` (F5b
  passive+variant forwarding); `tests/test_m7_partial_closure.py` (F5c select / not-ready).
  Targeted suites green; broad regression clean except 4 **pre-existing** `test_survey.py`
  failures (stale `_run_le_round` mock missing the `variant` kwarg — unrelated to this work).

---

## Post-review follow-ups (2026-07-30)

> Follow-ups from the triple-pass review + live validation of the LR-1a/1b/2/3/5/6 +
> F-1/F-2 batch. Accepted by the user 2026-07-30. Re-grafted 2026-07-30 onto the pulled
> multi-adapter (D1/D2) baseline after the working tree was stashed and `main` was
> fast-forwarded. Full `tests/` suite must stay green and lint/warning-clean.

- [x] ✅ **`adv_reports` dedup key-order hardening** — `insert_adv` now compares
  `decoded` structurally (order-independent) via `_decoded_matches()`; stored format
  unchanged. +1 test. (`bleep/core/observations/_history.py`,
  `tests/test_insert_adv.py`)
- [x] ✅ **`usb_ids.py` invalid `\R` escape** — **already fixed upstream** (the pulled
  baseline hardened the generator via a `_pystr()` backslash-escape helper in
  `update_usb_ids.py` and corrected the `CD\RW 40X` line). Equivalent to the review
  fix, so **not re-applied** — no divergence remains.
- [x] ✅ **DB semantics docs** — added "Counter & history semantics" to
  `observation_db.md` (`adv_reports` coalesced change-log / not a timeline;
  `devices.sighting_count` cumulative + cached-reread gating).
- [x] ✅ **Live re-verify F-1 (SDP XML)** (2026-07-30) — `discover_services_sdp(
  "F4:B6:88:0B:90:22", source="all")` (PLT V8200) returned provenance
  `browse+xml+records` (was `browse+records`): the XML source now contributes,
  confirming the trailing-status clip parses real hardware output end-to-end.
- [x] ✅ **PBAP-D1: obexd `Unable to find service record` diagnostic + error-type
  convention** (2026-07-30) — live preliminary scan on PhreakMe-Blue
  (`14:89:FD:31:8A:7E`) proved the PBAP PSE record *is* advertised
  (`--sdp-source merge --analyze` + `sdptool search 0x112F` both find it) but obexd's
  session-time SDP search fails **non-deterministically** (`Unable to find service
  record` vs `Timed out waiting for response` vs `Too short header in packet`). Added
  an actionable `BLEEPError` branch for the previously-unhandled `Unable to find service
  record` path and converted the sibling PBAP `RuntimeError` raises to Convention-aligned
  `BLEEPError` (mapped `RESULT_ERR_*` codes). MAP needs no change — the command layers
  already pre-flight via `detect_map_service`. **Confirmed cause-and-fix (attended live
  validation):** repeated failed attempts wedge the *Target Device's* OBEX stack;
  **restarting the Target Device restores PBAP** — dump succeeded with **313 vCard
  lines** immediately after a restart. Depending on the device implementation a
  power-cycle may be required. (`bleep/ble_ops/classic/pbap.py`,
  `bleep/docs/bl_classic_mode.md` §4)
- [x] ✅ **MAP-D1: shared OBEX CreateSession mapper + MAP convention alignment**
  (2026-07-30) — accepted DRY option. New `_obex_common.obex_session_error()` centralises
  the OBEX session-time diagnostics (`Too short header`/`Transport disconnected`/`Timed
  out`/`Unable to find service record` → mapped `BLEEPError`; else `map_dbus_error`).
  Refactored `pbap_dump_async` onto it (de-dup), wired it into `MapSession`, and converted
  MAP's remaining `RuntimeError`s (obexd-not-running, notify-watch, monitor-active) to
  `BLEEPError`/`NotSupportedError`/`OperationInProgressError`. Added a non-fatal
  `list_mas_instances` pre-flight to CLI `run_map`. Target for live MAP validation:
  **OnePlus 15R `78:ED:BC:23:67:96`** (advertises MAS `SMS/MMS` ch26, profile 0x1134
  v1.4). (`bleep/dbuslayer/_obex_common.py`, `bleep/dbuslayer/obex_map.py`,
  `bleep/ble_ops/classic/pbap.py`, `bleep/ble_ops/classic/map.py`,
  `bleep/modes/classic_profiles.py`, `bleep/docs/bl_classic_mode.md` §4)
- [x] ✅ **OBEX-D2: OPP/FTP/SYNC/BIP error-type convention alignment** (2026-07-30) —
  completes the OBEX-layer consistency sweep deferred in MAP-D1. Accepted BIP-via-shared-
  mapper + optional OPP/FTP CLI pre-flight. All four `CreateSession` sites now route through
  `obex_session_error()` (OPP `0x1105` / FTP `0x1106` / SYNC `0x1104` / BIP `0x111A-B`);
  added `SYNC`/`BIP` to `_SHARE_FEATURE` and a BIP `_EXTRA_HINT` (`--experimental`) appended
  in the mapper's unknown-variant branch. Converted every remaining `RuntimeError` →
  `BLEEPError`/`map_dbus_error`/`NotSupportedError` (incl. the shared `poll_obex_transfer`
  timeout→`TimeoutError` / error→`BLEEPError`, which also upgrades PBAP/MAP transfer paths).
  New shared `_warn_if_not_advertised` helper gives `run_opp`/`run_ftp` a non-fatal SDP
  pre-flight. Evidence scan: OnePlus 15R + PhreakMe advertise **OPP only** — FTP/SYNC/BIP are
  absence/failure-path only, BIP also needs `obexd --experimental`. Docstrings + §4 docs
  updated. **Deferred here, since closed:** `obex_pbap.py`'s 7 `RuntimeError`s were left for
  a later sweep — that sweep is **ERR-D3** below, which converted all 7 (obex_pbap.py now
  raises no `RuntimeError`); `bleep-mcp/` untouched.
  (`bleep/dbuslayer/{_obex_common,obex_opp,obex_ftp,obex_sync,obex_bip}.py`,
  `bleep/ble_ops/classic/opp.py`, `bleep/modes/classic_profiles.py`,
  `bleep/docs/bl_classic_mode.md` §4)
- [x] ✅ **ERR-D3: codebase-wide `RuntimeError` → `BLEEPError` convergence** (2026-07-30) —
  accepted Tier 1 + Tier 2 + `error_map` (Tier 3); `agent_io` deferred; `update_usb_ids.py` /
  `custom_uuids.py` excluded. Repo-wide scan proved the blast radius (only 3 `except
  RuntimeError` handlers, all updated). Converted 20 sites across `dbuslayer/obex_pbap.py`
  (7, closes the OBEX-D2 deferral — reuses `obex_session_error` for PBAP CreateSession),
  `ble_ops/le/scan.py` (4) + `le/enum_helpers.py` (1) → `NotSupportedError`,
  `ble_ops/classic/spp.py` (1) + `dbuslayer/spp_profile.py` (3), `ble_ops/classic/rfcomm.py`
  (2), and `ble_ops/classic/sdp.py` (7 → `NotSupportedError`/`ConnectionError`/`BLEEPError`).
  Companion handler updates: `sdp.py` `_ensure_sdptool` catchers + `modes/debug_classic.py`
  connectionless catcher (string-match preserved). `error_map.py` recovery strategies →
  `ConnectionError`/`ServicesNotResolvedError`. Verified: imports/lints clean; **183 passed /
  6 skipped** (sdp/scan/error_map/rfcomm/pbap/spp) + 24 classic; behavioral (sdptool-absent,
  unreachable string-match); live OnePlus `classic-enum`/`classic-scan` regression-free.
  **Remaining RuntimeErrors (intentional):** `agent_io.py` (5, agent/D-Bus boundary),
  `update_usb_ids.py` (1, dev script), `custom_uuids.py` (1, config util).
  (`bleep/dbuslayer/{obex_pbap,spp_profile}.py`, `bleep/ble_ops/le/{scan,enum_helpers}.py`,
  `bleep/ble_ops/classic/{spp,rfcomm,sdp}.py`, `bleep/modes/debug_classic.py`,
  `bleep/bt_ref/error_map.py`)
- [x] ✅ **Consolidated triple-pass review — OBEX-D2 + ERR-D3** (2026-07-30) — fidelity
  confirmed, no detrimental effects. Pass 1 (correctness): full diff of all 20 changed
  source files re-read; every `RuntimeError` conversion Convention-aligned, no orphaned
  locals, docstrings current. Pass 2 (integration): referenced symbols/signatures verified
  (`MapSession.get_message`/`classic.map.get_message` `folder=` kwarg, `detect_opp/ftp/map_
  service`, `build_svc_map`, `list_mas_instances`); **only 3** `except RuntimeError` handlers
  repo-wide, all coordinated; remaining `raise RuntimeError` sites == exactly the
  deferred/excluded scope (`agent_io`, `update_usb_ids`, `custom_uuids`) — no over-reach.
  Pass 3 (runtime): all 20 modules import clean; all `bleep.core.errors` classes + `RESULT_*`
  constants resolve; **96 passed / 14 skipped** targeted suites; **0 lint errors**. Note: the
  non-error-convention files (`manager.py`, `signals.py`, `adapter_session.py`,
  `_history.py`, `survey.py`, `scan.py` LR-2c hunk, + survey/obs tests) were out of *this*
  review's scope — they are the **LR-2c** work item below (reviewed/validated separately);
  all of it shipped together in the same commit.

### LR-2b — census `fingerprint_changed` "misses rotations" — [x] INVESTIGATED / RETRACTED (not a defect, 2026-07-30)

> **Retracted 2026-07-30 after investigation.** The reported gap does not
> reproduce; it was a misdiagnosis from reading stale `adv_reports` rows without a
> timestamp filter. The census round-result and `adv_reports` are built from the
> **same** per-round `GetManagedObjects()` snapshot inside `_native_scan`, so the two
> cannot diverge. The residual (real) limitation — both sinks sample the *end-of-round*
> snapshot, so a rotation that reverts within one round is missed by **both** — is a
> separate, optional enhancement (→ LR-2c), not a bug.

### LR-2c — signal-fed intra-round fingerprint sampling — [x] IMPLEMENTED (accepted + built 2026-07-30; re-grafted 2026-07-30)

> **Implemented 2026-07-30, re-grafted 2026-07-30 onto the multi-adapter baseline.**
> Phase 0 gate passed (BlueZ delivered `ServiceData` in 252/252 `PropertiesChanged`
> events over 90s under `DuplicateData=True` for the Light Orb — no coalescing). Detects
> same-length payload rotations that occur *and revert within a single survey round*
> (invisible to the end-of-round `GetManagedObjects()` snapshot that both the census and
> `adv_reports` consume). The only source of sub-round variation is the
> per-advertisement D-Bus signal path (`PropertiesChanged`/`InterfacesAdded`), mirroring
> how **LR-6** captured RSSI. See `changelog.md` (Unreleased → LR-2c) for the full
> write-up.
>
> **Design (additive, LR-6-shaped).** (1) *DeviceManager tracker* (`dbuslayer/manager.py`):
> per-round `_adv_fp_last`/`_adv_fp_rotated` under a lock, reset in `start_discovery`;
> `_capture_adv_fingerprint` flags `len(new)==len(old) and new!=old`;
> `pop_fingerprint_rotated` one-shot read+clear. (2) *Signal wiring*
> (`dbuslayer/signals.py`): `_capture_device_adv_fingerprint` next to
> `_capture_device_rssi`, routed via `_resolve_manager_for_path` (D1 adapter-aware),
> called from `_properties_changed` and `_interfaces_added`. (3) *Scan surface*
> (`ble_ops/le/scan.py`): each entry gets `fingerprint_rotated_in_round` popped by the
> D-Bus *path* MAC. (4) *Census OR-in* (`modes/survey.py:_merge_entry`): additive set of
> `fingerprint_changed`. (5) *Multi-adapter (D2) parity*
> (`dbuslayer/adapter_session.py:harvest`): pops the same flag per device so
> `--collector` surveys behave identically to `_native_scan`.
>
> **Tests.** `tests/test_adv_fingerprint_rotation.py` (18) + 3 census OR-in tests in
> `tests/test_survey.py`; `tests/test_discovery_error_surfacing.py` seeds the new
> tracker fields. Targeted suite green post-graft (147 passed).

---

## CLI ↔ Debug Mode capability uniformity CDU-M0..M6 (2026-07-29) — [ ] PLANNED (accepted for implementation)

> **CONTEXT:** Product of an exhaustive triple-pass review of the CLI parser tree
> (`bleep/cli/parsers/*.py` → `bleep/cli/dispatch.py`) and the Debug shell dispatch
> table (`bleep/modes/debug.py::_build_dispatch_table` + all `bleep/modes/debug_*.py`
> submodules), cross-referenced against `bleep/docs/cli_usage.md` and
> `bleep/docs/debug_mode.md`. **Goal:** capability *parity* between the CLI and Debug
> Mode — every capability reachable from one surface is reachable from the other
> unless it is intrinsically single-surface — **without** merging the two entry-point
> methodologies and **without** duplicating implementation logic. All milestones,
> naming decisions, and the CTF/mesh/refresh-refs scoping below were reviewed and
> **accepted by the user (2026-07-29)** prior to writing this entry. Nothing is
> implemented yet; this is the cited work plan for milestone-driven execution.

### CDU — Methodology (the two contracts that MUST be preserved)

> Parity is achieved by making both surfaces call the **same shared implementation**;
> only the thin adapter differs. This is already the house pattern — do not merge the
> entry points.
>
> - **CLI contract (one-shot, scriptable).** Command = an `argparse` subparser in
>   `bleep/cli/parsers/<group>.py::register()`, aggregated in
>   `bleep/cli/parsers/__init__.py::build_parser` (`:34-52`). Dispatched by
>   `args.mode` in `bleep/cli/dispatch.py::dispatch`, returns an **int exit code**,
>   emits through an `OutputContext` (`output_from_args(args)`) honoring
>   `--json`/`--quiet`. Stateless: connect → act → tear down.
> - **Debug contract (interactive, stateful).** Command = `cmd_*(args: List[str],
>   state: DebugState)` bound in `bleep/modes/debug.py::_build_dispatch_table`
>   (`:239-314`). Holds a live session in `DebugState` (current device, mapping,
>   mine/perm maps, RFCOMM sockets, survey thread). Emits via `print_and_log`; there
>   is **no** `OutputContext` in the shell (no `--json`/`--quiet`).
>
> **Rule for all CDU work:** a capability's logic lives once in `bleep/ble_ops/*`,
> `bleep/dbuslayer/*`, or an existing `bleep/modes/<mode>.run`-style core; each
> surface holds only an adapter. Where a shared core prints via `OutputContext`, the
> Debug adapter passes a `_ProgressShim` that routes `emit_progress` to
> `print_and_log` — the exact technique already used to fix SR-G1-FollowUp
> (`bleep/modes/debug_survey.py::cmd_survey`; see that entry below).

### CDU — Existing anti-drift precedents to extend (do NOT reinvent)

> - **Shared argument builder.** `bleep/cli/parsers/survey.py::_add_survey_arguments`
>   (`:6-46`) is the single source of truth for the survey flag set, invoked by the
>   CLI subparser, `bleep.modes.survey._build_parser`, and
>   `bleep.modes.debug_survey.cmd_survey`. `bleep/cli/parsers/aoi.py::_add_aoi_arguments`
>   + `apply_aoi_subcommand` follow the same pattern.
> - **Shared execution + output shim.** SR-G1-FollowUp reconciled the debug survey
>   round-loop to reuse the CLI's `_write_survey_checkpoint()`/`.partial` logic via a
>   `_ProgressShim` mapping `emit_progress` → `print_and_log`.
>
> Every CDU milestone reuses these two patterns. New parallel implementations of an
> existing capability are out of scope.

### CDU — Naming decisions (hard renames; accepted 2026-07-29)

> - CLI `monitor` → **hard rename** to `advertise-monitor`. **No** deprecated
>   `monitor` alias retained. Rationale: `monitor` collided with the Debug-shell
>   `monitor` (device-property monitor). Debug `advmon` keyword rejected (reads as
>   "Advanced Monitor", not "Advertisement Monitor").
> - CLI `classic-pan serve`/`unserve` → **hard rename** to `server-reg`/`server-unreg`.
>   `serve`/`unserve` removed entirely. Debug `cpan` primary verbs become
>   `server-reg`/`server-unreg`; Debug **may** retain `server register`/`server
>   unregister` as an accepted alias (sole allowed alias in this workstream).
> - General policy for this workstream: **hard rename in all other cases** — no
>   back-compat aliases except the one Debug PAN alias noted above.

### CDU — Capability gap findings (with citations)

> **Class A — CLI capability with no Debug verb** (to be closed unless intrinsically
> one-shot): `explore` (`dispatch.py:179`), `signal`/`signal-config`
> (`dispatch.py:205,210`), `uuid-translate` (`:221`), `adapter-config` (`:374`),
> `advertise-monitor` (was `monitor`, `:378`), `advertise` (`:383`), `gatt-server`
> (`:388`), `device-sets` (`:393`), `mesh` (`:397`), `ctf` (`:366`), `network-enum`
> (`:263`), `classic-ping` (`:352`), `classic-enum` rich SDP analysis (`:239`),
> `audio-intercept` (`:321`), `audio-config` file mgmt (`:401`), `refresh-refs`
> (`:370`), full `db` surface (`:154`).
>
> **Class B — Debug capability with no CLI verb, correctly single-surface** (document,
> do NOT port): D-Bus navigation/introspection `ls`/`cd`/`pwd`/`back`/`interfaces`/
> `props`/`methods`/`signals`/`call`/`introspect` (`bleep/modes/debug_dbus.py`); raw
> RFCOMM I/O `copen`/`csend`/`crecv`/`craw`/`cbind` (`debug_classic_rfcomm.py`);
> interactive GATT `read`/`write`/`notify`/`char`/`chars`/`services`/`detailed`/
> `mines`/`multiread*`/`brutewrite`. `dscan` maps to CLI `scan --transport auto`.
>
> **Class C — same capability, divergent behavior (the correctness defects):**
> 1. `monitor` name collision — CLI `monitor` (Advertisement Monitor, `dispatch.py:378`)
>    vs Debug `monitor` (device-property monitor, `debug_dbus.py`). Resolved by M2.
> 2. `pbap --watchdog` default drift — CLI **30** (`bleep/cli/parsers/classic.py:78`)
>    vs Debug **8** (`bleep/modes/debug_classic.py:442`). Debug default silently
>    aborts long phonebook pulls.
> 3. `pair` flag drift — CLI exposes `--no-connect`/`--no-trust`; Debug omits both
>    (`bleep/modes/debug_pairing.py:286-309`).
> 4. `scan` timeout drift — CLI honors `--timeout`; Debug `scan`/`scann`/`scanp`
>    hardcode 10s and `scanb` 20s (`bleep/modes/debug_scan.py:31,45,62,76`).
> 5. `audioplay`/`audiorec` option drift — CLI has `--codec`/`--hfp`/`--keep-profile`;
>    Debug omits them (`bleep/modes/debug_media.py:334-341,388-395`).
> 6. `classic-pan` vocabulary drift — resolved by M1.5 hard rename.
> 7. `hid-info` (connectionless, `dispatch.py:291-319`) vs `chid` (connected,
>    `bleep/modes/debug_hid.py:24-38`) — both call the same `classify_hid`; resolved
>    by M1.6 (expose both variants on both surfaces).

### CDU-M0 — Parity registry + guard test (foundation, no behavior change) — [x] IMPLEMENTED & VERIFIED (2026-07-29)

> **Landed.** New `bleep/cli/capability_registry.py` (declarative `Capability`
> rows covering 100% of both surfaces) + new `tests/test_cli_debug_parity.py`
> guard. Minimal behaviour-preserving refactor of `bleep/cli/parsers/__init__.py`
> extracts `build_argument_parser()` (parser construction w/o parsing) and adds
> `iter_cli_subcommands()` so the guard can enumerate the CLI surface;
> `build_parser()` behaviour is unchanged. The guard also enumerates the debug
> surface via `bleep.modes.debug._build_dispatch_table(DebugState())`.
> **Verified:** `tests/test_cli_debug_parity.py` passes in the full run
> (`1825 passed, 9 failed, 37 skipped`). One follow-up adjustment: the declarative
> registry legitimately contains bare debug-shell command tokens (in the command
> tuples + parity rationale) and emits no user-facing output, so it was added to
> the `EXEMPT_PATH_PARTS` allow-list of `tests/test_cli_hint_convention.py`.
> The remaining 8 failures are **pre-existing, environment-dependent** (headless
> WSL: no Bluetooth adapter / BlueZ) — every one hits the `main.py` adapter guard
> `require_adapter() → return 1` (`test_cli_debug_subcommand` ×4, `test_gatt_
> enumeration` ×2, `test_media_cli` ×1) or is a raw D-Bus smoke test
> (`test_dbuslayer_discovery`); none touch CDU-modified code.
>
> **Goal.** Make parity machine-checkable so it cannot silently drift again (the same
> failure mode as the survey-parser drift reconciled in SR-G1-FollowUp).
>
> **Tasks.**
> - Add `bleep/cli/capability_registry.py` (new, ≤200 lines): declarative list of
>   `Capability(name, cli_command, debug_command, shared_impl, parity, rationale,
>   shared_args)` where `parity ∈ {full, cli-only, debug-only, partial}`.
> - Add `tests/test_cli_debug_parity.py` (structural template:
>   `tests/test_cli_hint_convention.py` AST walk). Asserts: (a) every CLI subcommand
>   registered in `build_parser()` and every key in `_build_dispatch_table()` appears
>   in the registry; (b) every `parity="full"` row has both `cli_command` and
>   `debug_command`; (c) shared-option capabilities reference a `_add_*_arguments`
>   builder importable by both surfaces.
>
> **PoC — registry shape:**
>
> ```python
> # bleep/cli/capability_registry.py
> from dataclasses import dataclass
>
> @dataclass(frozen=True)
> class Capability:
>     name: str
>     cli_command: str | None
>     debug_command: str | None
>     shared_impl: str            # dotted path to the single shared implementation
>     parity: str                 # full | cli-only | debug-only | partial
>     rationale: str = ""
>     shared_args: str | None = None  # dotted path to _add_*_arguments builder
>
> CAPABILITIES: tuple[Capability, ...] = (
>     Capability("media-ctrl", "media-ctrl", "mediactrl",
>                "bleep.modes.media.control_media_device", "full"),
>     Capability("dbus-navigate", None, "ls/cd/pwd/introspect",
>                "bleep.modes.debug_dbus", "debug-only",
>                "Interactive D-Bus tree navigation; meaningless one-shot."),
>     Capability("advertise-monitor", "advertise-monitor", "advertise-monitor",
>                "bleep.modes.monitor.run", "full"),
>     Capability("refresh-refs", "refresh-refs", None,
>                "bleep.modes.refresh_refs.run", "cli-only",
>                "Reference-data regeneration; batch maintenance, no session value."),
>     # ...one row per command in both surfaces...
> )
> ```
>
> **Acceptance.** New test green; full `pytest` suite still green; registry enumerates
> 100% of both surfaces (test fails on any unregistered command).

### CDU-M1 — Eliminate Class-C option/default drift (correctness) — [x] IMPLEMENTED & VERIFIED (2026-07-29; suite green except pre-existing adapter-dependent tests — see M0 note)

> **Landed.**
> - **pbap watchdog:** new `bleep/cli/parsers/classic.py::_add_pbap_arguments`
>   (canonical `--watchdog default=30`); consumed by the CLI `classic-pbap`
>   subparser and by `bleep/modes/debug_classic.py::cmd_pbap` (lazy import,
>   survey-precedent style). The debug-shell 8 s default that silently aborted
>   long PBAP pulls is removed.
> - **pair flags:** new `bleep/cli/parsers/pairing.py::_add_pair_arguments`
>   consumed by both the CLI `pair` subparser and
>   `bleep/modes/debug_pairing.py::cmd_pair`; the debug shell now has
>   `--no-connect`/`--no-trust`. These are threaded through `_cmd_pair_single`
>   (`set_trusted=not no_trust`; post-pair connect + already-paired connect-only
>   paths skipped when `no_connect`; DB `trusted` reflects `no_trust`).
> - **scan timeouts:** `bleep/modes/debug_scan.py` `scan`/`scann`/`scanp`/`scanb`
>   gained an overridable `--timeout`/`-t` (shared `_parse_scan_timeout` helper)
>   preserving the historical 10 s / 20 s defaults.
> - **audio options:** debug `audioplay` gained `--codec` (→ `play_audio_file(
>   codec_preference=...)`) and debug `audiorec` gained `--hfp`/`--keep-profile`
>   (→ `audio_system.system_record_hfp(restore_profile=...)`), matching the CLI
>   dispatch paths (`bleep/modes/debug_media.py`).
> - Docs: `bleep/docs/debug_mode.md` scan/pair tables + in-shell `help` usage
>   strings (`bleep/modes/debug.py`) updated. Registry `shared_args` now points
>   at `_add_pbap_arguments` / `_add_pair_arguments`.
>
> **Goal.** Identical parsed defaults/args wherever both surfaces already claim the
> same capability. Each fix = extract one shared `_add_*_arguments()` builder and
> repoint both call sites (no logic reimplementation).
>
> **Tasks.**
> - **pbap watchdog:** add `_add_pbap_arguments(parser)` in
>   `bleep/cli/parsers/classic.py`; consume in CLI `classic-pbap` register and
>   `bleep/modes/debug_classic.py::cmd_pbap` (`:439-443`). Canonical
>   `--watchdog default=30` (the safe CLI value); remove Debug inline `default=8`
>   (`debug_classic.py:442`).
> - **pair flags:** add `_add_pair_arguments(parser)` in
>   `bleep/cli/parsers/pairing.py`; consume in CLI `pair` and
>   `bleep/modes/debug_pairing.py::cmd_pair` (`:286-309`). Debug gains
>   `--no-connect`/`--no-trust`.
> - **scan timeouts:** add optional `--timeout` to Debug `scan`/`scann`/`scanp`/
>   `scanb` (`bleep/modes/debug_scan.py:21,34,48,65`); `cmd_dscan` already parses one
>   (`:86`). Preserve current defaults (10s / 20s scanb) but make them overridable to
>   match CLI capability.
> - **audioplay/audiorec options:** extend Debug parsers
>   (`bleep/modes/debug_media.py:336-341,390-395`) with `--codec` (play) and
>   `--hfp`/`--keep-profile` (record); wire to the same `MediaStreamManager` /
>   `bleep.ble_ops.audio.audio_system` calls the CLI uses (`bleep/cli/dispatch.py:88-135`).
>
> **Acceptance.** Per-fix parse-only unit test asserting the two surfaces produce
> identical defaults/parsed args (no hardware needed); affected registry rows become
> `parity="full"`; full suite green.

### CDU-M1.5 — `classic-pan` command uniformity (hard rename) — [x] IMPLEMENTED & VERIFIED (2026-07-29; full suite 1856 passed / 0 failed)

> **Landed.** Shared `bleep/ble_ops/classic/pan.py::PAN_SERVER_VERBS` +
> `resolve_pan_server_verb()`. CLI hard rename `serve`/`unserve` →
> `server-reg`/`server-unreg` (`bleep/cli/parsers/classic.py`; `run_pan` action
> branches in `bleep/modes/classic_profiles.py`; no alias). Debug
> `bleep/modes/debug_classic_profiles.py::cmd_cpan` gained primary
> `server-reg`/`server-unreg` verbs (both routed through the new shared
> `_cpan_server_action` helper) and retains the one accepted two-token alias
> `server register`/`server unregister`. Docs (`cli_usage.md`, `debug_mode.md`,
> in-shell `help`) + registry rationale updated. New test
> `tests/test_pan_command_uniformity.py` asserts the rename, alias routing, and
> resolver. The standalone `bleep/scripts/pan_peer.py` tool is intentionally
> out of scope (separate parser).

> **Goal.** One vocabulary across both surfaces, favoring reader clarity.
>
> **Tasks.**
> - **CLI (hard rename):** in `bleep/cli/parsers/classic.py:161-208` (dispatch
>   `bleep/modes/classic_profiles.py::run_pan`, `bleep/cli/dispatch.py:259-261`),
>   **remove** `serve`/`unserve`; add `server-reg`/`server-unreg`. No alias retained.
> - **Debug:** in `bleep/modes/debug_classic_profiles.py::cmd_cpan`, primary verbs
>   `server-reg`/`server-unreg`; retain `server register`/`server unregister` as the
>   one accepted alias (per user 2026-07-29).
> - Add a shared `PAN_SERVER_VERBS` constant + resolver (place beside the existing PAN
>   role constants) so both surfaces map verbs/aliases identically.
>
> **Acceptance.** CLI `classic-pan server-reg`/`server-unreg` work; `serve`/`unserve`
> are gone (help + parse test asserts removal); Debug `cpan server-reg` and alias both
> route to the same `NetworkServer.register`/`unregister`; docs updated.

### CDU-M1.6 — HID dual-variant parity (connected + connectionless on both) — [x] IMPLEMENTED & VERIFIED (2026-07-29; full suite 1856 passed / 0 failed)

> **Landed.** New shared evidence builder `bleep/ble_ops/hid.py`
> (`context_from_classic` / `context_from_le` / `context_from_device` /
> `build_hid_context`). CLI `hid-info` gained `--connect`
> (`bleep/cli/parsers/classic.py`) and its dispatch now delegates to
> `build_hid_context` (`bleep/cli/dispatch.py`). Debug `chid` gained optional
> `[MAC]` (connectionless, no live session) and otherwise uses the connected
> `state.current_device` via `context_from_device`
> (`bleep/modes/debug_hid.py`). This also **fixes** the latent LE bug where the
> old `chid` LE branch called a non-existent `get_properties()` (always empty
> evidence) — it now uses the real `get_device_appearance`/`get_uuids` +
> `Input1.ReconnectMode` accessors. Registry `hid` row flipped to
> `parity="full"`. Docs: `device_type_classification.md` gained the
> connectionless-vs-connected evidence-delta + variant matrix; `cli_usage.md`,
> `debug_mode.md`, in-shell `help` updated. New test
> `tests/test_hid_dual_variant.py` proves both surfaces feed identical evidence
> to `classify_hid` and yield identical `HIDInfo`.

> **Goal.** Both surfaces expose classification **with** and **without** a connection.
>
> **Clarification (why two variants exist).** `classify_hid(context)`
> (`bleep/analysis/device_type_classifier.py:1532-1581`) is a pure function over an
> evidence dict. Evidence availability differs by path:
> - **Connectionless** (CLI `hid-info`, `bleep/cli/dispatch.py:291-319`): context from
>   `ClassicDevice.get_device_class()` + `get_supported_profiles()` (cached discovery
>   props) → yields `device_class` + `uuids` evidence. Cannot read
>   `org.bluez.Input1.ReconnectMode` (BlueZ instantiates `Input1` only on a
>   connected/bonded HID) and usually lacks LE `appearance`.
> - **Connected** (Debug `chid`, `bleep/modes/debug_hid.py:24-38`): live props — for
>   LE additionally `appearance` and, when present, `_Input1.ReconnectMode` (richer
>   typing incl. reconnect behavior).
>
> **Tasks.**
> - Add shared `build_hid_context(device_or_mac, *, connect: bool)` helper (in
>   `bleep/analysis/device_type_classifier.py` or a small `bleep/ble_ops` helper) that
>   assembles the evidence dict once for both surfaces.
> - **CLI:** `hid-info` gains `--connect` (default off = current connectionless
>   behavior; on = connect per transport, harvest `appearance`/`Input1`, classify).
> - **Debug:** `chid` gains optional `[MAC]`; with a MAC and no live session it builds
>   the connectionless context (mirroring CLI default), else uses the connected
>   device.
>
> **Acceptance.** Unit test feeding identical evidence dicts through both adapters
> yields identical `HIDInfo`; connectionless-vs-connected evidence delta documented in
> `bleep/docs/device_type_classification.md`; registry row `parity="full"`.

### CDU-M2 — Advertisement Monitor: CLI hard rename + Debug parity — [x] IMPLEMENTED & VERIFIED (2026-07-29)

> **Goal.** Remove the `monitor` name collision; expose Advertisement Monitor on both
> surfaces under one unambiguous name.
>
> **Tasks.**
> - **CLI (hard rename):** rename subcommand `monitor` → `advertise-monitor` in
>   `bleep/cli/parsers/utility.py:34` and its dispatch branch
>   `bleep/cli/dispatch.py:378-381`. **No** `monitor` alias retained (accepted
>   2026-07-29). Update `bleep/docs/cli_usage.md` command table (currently lists
>   `monitor`).
> - **Debug:** add `advertise-monitor` verb (new `bleep/modes/debug_advmon.py`, ≤120
>   lines) as a thin adapter over `bleep.modes.monitor` internals via a
>   `_ProgressShim`; register `"advertise-monitor"` in
>   `bleep/modes/debug.py::_build_dispatch_table`. Debug `monitor` **stays** the
>   device-property monitor (`bleep/modes/debug_dbus.py`).
> - Disambiguate both in `bleep/docs/debug_mode.md` (property `monitor` vs
>   `advertise-monitor`).
>
> **Acceptance.** `bleep advertise-monitor caps`/`start` work; `bleep monitor` no
> longer exists (help/parse test asserts removal); Debug `advertise-monitor` reachable;
> Debug `monitor` behavior unchanged.

**LANDED (2026-07-29).**
- **CLI hard rename (no alias).** `bleep/cli/parsers/utility.py` — subcommand
  `monitor` → `advertise-monitor`; extracted the shared start-option builder
  `_add_advertise_monitor_start_arguments(parser)` (used by the CLI `start`
  subparser **and** the debug adapter). Dispatch branch renamed to
  `elif args.mode == "advertise-monitor":` in `bleep/cli/dispatch.py`. The
  sub-action dest is still `monitor_action`, so `bleep/modes/monitor.py`
  (`run`/`handle_monitor`/`_handle_caps`/`_handle_start`) is **unchanged** — the
  single shared implementation both surfaces delegate to.
- **Debug parity (new verb).** New `bleep/modes/debug_advmon.py`
  (`cmd_advertise_monitor`, ~90 lines) — a thin adapter that builds the
  `Namespace` (subparsers `caps`/`start`, `start` via the shared builder) and
  calls `bleep.modes.monitor.run(opts)` with the default terminal
  `OutputContext`. **Deviation from plan:** no `_ProgressShim` is needed —
  `monitor.py` already emits via `print_and_log` (JSON only when
  `OutputContext.is_json`), so the terminal path prints directly. Registered as
  `"advertise-monitor"` in `bleep/modes/debug.py::_build_dispatch_table` and
  added to the `help` "Scanning" group.
- **Loop/signal handoff (start only).** `monitor._handle_start` runs its own
  foreground `GLib.MainLoop` and installs SIGINT/SIGTERM handlers. The adapter
  `stop_glib_mainloop(state)` before and `ensure_glib_mainloop(state)` after
  (mirrors the `pair` precedent), and saves/restores the shell's SIGINT/SIGTERM
  handlers in a `finally`, so Ctrl-C stops the monitor and returns cleanly to
  the prompt without corrupting the shell's Ctrl-C behaviour. `caps` needs no
  handoff.
- **Registry.** `advertisement-monitor` flipped `cli-only` → `full`:
  `cli_command`/`debug_command` = `("advertise-monitor",)`, `shared_args` =
  `bleep.cli.parsers.utility._add_advertise_monitor_start_arguments`. The debug
  property monitor stays a separate `dbus-property-monitor` row; disambiguated
  in help + `debug_mode.md`.
- **Docs.** `cli_usage.md` (command table + AdvertisementMonitor caveat),
  `debug_mode.md` (BLE Scanning table gains `advertise-monitor caps`/`start`,
  plus a note distinguishing it from the property `monitor`), changelog.
- **Verified (2026-07-29).** `tests/test_advertise_monitor_uniformity.py` +
  `test_cli_debug_parity.py` + `test_cli_hint_convention.py` → `207 passed`.
  Full adapter-dependent suite pending a host with Bluetooth hardware.

### CDU-M3 — Zero-risk utility parity verbs (thin adapters) — [x] IMPLEMENTED & VERIFIED (2026-07-29)

> **Goal.** Port trivially-portable CLI utilities into the shell as thin adapters over
> existing cores (no state required, minimal risk).
>
> **Tasks (each a small `cmd_*` delegating to the named core, registered in
> `_build_dispatch_table`):**
> - `uuidtr <uuid...>` → `bleep.modes.uuid_translate.main`.
> - `adaptercfg [show|get|set ...]` → `bleep.modes.adapter_config.handle_adapter_config`.
> - `netenum` → `bleep.modes.classic_profiles.run_network_enum`.
> - `cping <MAC>` → `bleep.ble_ops.classic.ping.classic_l2ping`.
> - `db <list|show|timeline|export|uuids|maintain ...>` → `bleep.modes.db.run` with a
>   `_ProgressShim` `OutputContext`, giving the full observation-DB surface mid-session
>   (aligns with, and supersedes the scope of, the session-only `dbsave`/`dbexport` in
>   `bleep/modes/debug_aoi.py`).
>
> **Acceptance.** Each verb registered + `parity="full"`; per-verb parse/dispatch smoke
> test; `bleep/docs/debug_mode.md` command tables updated.

**LANDED (2026-07-29).**
- **New module `bleep/modes/debug_cli_adapters.py`** — five stateless `cmd_*`
  adapters, each delegating to the exact core the CLI dispatch uses:
  `cmd_uuidtr` → `uuid_translate.main`; `cmd_adaptercfg` →
  `adapter_config.handle_adapter_config`; `cmd_netenum` →
  `classic_profiles.run_network_enum`; `cmd_cping` →
  `ble_ops.classic.ping.classic_l2ping`; `cmd_db` → `modes.db.run`.
- **Anti-drift parsing.** `_parse_as_cli(cli_name, tokens)` builds the root parser
  via `bleep.cli.parsers.build_argument_parser()` (M0) and parses
  `[cli_name, *tokens]`, so `adaptercfg`/`netenum`/`cping`/`db` accept *exactly*
  their CLI twin's options. `SystemExit` (argparse `--help`/errors) is caught in
  the helper — and in `cmd_uuidtr` around the self-parsing `main()` — so it can
  never escape as `BaseException` and tear down the shell.
- **Deviation from plan (db).** No `_ProgressShim` needed: `db.run` emits via
  `print_and_log` for terminal output (JSON only under `is_json`/`is_quiet`), so
  the adapter passes the default terminal `OutputContext` (same finding as M2's
  `monitor.run`). `dbsave`/`dbexport` kept as session-scoped helpers.
- **Registration.** Imported + bound in `bleep/modes/debug.py::_build_dispatch_table`
  (`uuidtr`/`adaptercfg`/`netenum`/`cping`/`db`); `help` groups updated (Classic
  gains `netenum`/`cping`; Analysis & Database gains `db`; new **Utilities** group
  for `uuidtr`/`adaptercfg`).
- **Registry.** `uuid-translate`, `adapter-config`, `network-enum`, `classic-ping`
  `cli-only` → `full`; `db` `partial` → `full` (`debug_command` = `db`, `dbsave`,
  `dbexport`; `shared_impl` → `bleep.modes.db.run`).
- **Docs.** `debug_mode.md` (Classic / Database / Utilities tables), changelog.
- **Tests.** `tests/test_m3_utility_parity.py` — registry `full` rows,
  dispatch reachability, per-verb parse→delegate forwarding, `cping` RTT/failure
  formatting, and `SystemExit`-containment guards.
- **Verified (2026-07-29).** M3 suite + M2 + `test_cli_debug_parity.py` +
  `test_cli_hint_convention.py` → `227 passed`. Full adapter-dependent suite
  pending a host with Bluetooth hardware.

### CDU-M4 — Stateful-core parity verbs — [x] IMPLEMENTED & VERIFIED (2026-07-29)

> **Goal.** Expose connection-aware CLI modes that gain value from a live `DebugState`.
> Each verb reuses the CLI's shared arg builder — extend `_add_*_arguments()` where the
> CLI parser currently declares flags inline (`bleep/cli/parsers/explore.py`,
> `utility.py`, `gatt.py`).
>
> **Tasks.**
> - `explore [MAC] [--out F] [--conn-mode ...]` → `bleep.modes.exploration.run`,
>   defaulting `MAC` to `state.current_device`.
> - `signal <char> [--time N]` → `bleep.modes.signal.run` core, reusing
>   `state.current_device` instead of reconnecting; keep lightweight `notify` as-is
>   (document `signal` as the timed/config-driven variant).
> - `gattserver start [...]` → `bleep.modes.gatt_server.run` via `_ProgressShim`.
> - `advertise start [...]` → `bleep.modes.advertise.run` via `_ProgressShim`.
> - `audiointercept <MAC> [...]` → `bleep.ble_ops.audio.audio_transcribe.run_audio_intercept`.
> - `devicesets [list|connect|disconnect|info]` → `bleep.modes.device_sets.handle_device_sets`.
> - `mesh [join|provision|reprovision]` → `bleep.modes.mesh_provision.handle_mesh`
>   (added per user 2026-07-29).
> - `ctf [...]` → `bleep.modes.blectf.run` (grouped into M4 per user 2026-07-29; a
>   secondary interaction path for BLE-CTF devices).
> - **`refresh-refs` intentionally NOT ported** — registry `parity="cli-only"` with
>   rationale (batch reference-data maintenance; no session value).
>
> **Acceptance.** Verbs registered; shared arg builders introduced where flags were
> inline; parse/dispatch tests; `bleep/docs/debug_mode.md` updated; affected registry
> rows `parity="full"` (except `refresh-refs`).

**LANDED (2026-07-29).**
- **New module `bleep/modes/debug_stateful_adapters.py`** — eight `cmd_*` adapters
  (`explore`, `signal`, `gattserver`, `advertise`, `audiointercept`, `devicesets`,
  `mesh`, `ctf`), each delegating to the exact CLI-dispatch core.
- **Deviation from plan (no `_add_*_arguments` extraction needed).** M3's
  `parse_as_cli` (promoted from `_parse_as_cli`) parses debug tokens through the
  *real* CLI subparser, so debug verbs already accept exactly their CLI twin's
  options — this supersedes the plan's suggestion to extract shared arg builders
  from inline flags (`explore.py`/`utility.py`/`gatt.py` left untouched). Same
  anti-drift guarantee, less churn. `SystemExit` is contained in `parse_as_cli`.
- **Stateful behaviours.** `explore`/`audiointercept` default MAC to
  `state.current_device` via `_inject_current_mac` (leading non-option token =
  explicit MAC). `signal` reuses the live device with **no reconnect** — the only
  core change: an additive `signal.run(args, output=None, device=None)` param that
  skips `_connect_enum` when a device is supplied (CLI path unchanged).
- **Foreground-loop cores.** `signal`/`gattserver`/`advertise` delegate inside the
  new shared `bleep/modes/debug_state.py::foreground_loop_handoff(state)` context
  manager (stops the bg GLib loop + saves/restores SIGINT/SIGTERM). `debug_advmon`
  (M2) was refactored onto it, deleting its inline duplicate. `explore`/
  `audiointercept`/`devicesets`/`mesh`/`ctf` need no handoff (no foreground loop).
- **`refresh-refs` NOT ported** — registry stays `cli-only` with rationale.
- **Registration.** Imported + bound in `_build_dispatch_table`; `help` gains
  `explore` (BLE Enumeration), `signal` (BLE Read/Write), `audiointercept` (Media &
  Audio), and two new groups: "Local Roles & Broadcast" (`gattserver`/`advertise`)
  and "Sets / Mesh / CTF" (`devicesets`/`mesh`/`ctf`).
- **Registry.** 8 rows `cli-only` → `full`; `refresh-refs` unchanged.
- **Docs.** `debug_mode.md` (Enumeration/GATT tables + new "Local Roles, Broadcast
  & Advanced" section), changelog.
- **Tests.** `tests/test_m4_stateful_parity.py` — registry `full` rows +
  `refresh-refs` cli-only, dispatch reachability, `foreground_loop_handoff`
  signal-restore, MAC-defaulting (explore/audiointercept), `signal` device-reuse,
  per-verb parse→delegate forwarding, and `SystemExit`-containment.
- **Verified (2026-07-29).** M4 + M3 + M2 + `test_cli_debug_parity.py` +
  `test_cli_hint_convention.py` → `258 passed`. The M2 test
  `test_debug_start_delegates_inside_loop_handoff` was updated to assert
  delegation inside the shared `foreground_loop_handoff` (M2's inline loop/signal
  logic was consolidated into it during M4). Full adapter-dependent suite pending
  Bluetooth hardware.

### CDU-M5 — Depth parity (`cenum`; `audiocfg` write sub-surface) — [x] IMPLEMENTED & VERIFIED

> **Goal.** Close the two documented *depth* gaps rather than leaving weaker Debug twins.

**Landed changes.**

- **New Debug `cenum` verb** (`bleep/modes/debug_stateful_adapters.py`, `cmd_cenum`) —
  the true depth twin of CLI `classic-enum`. Parses through `parse_as_cli("classic-enum", …)`
  and delegates to the same `bleep.modes.classic_enum.run`
  (`bleep.analysis.sdp_analyzer` path) with full
  `--version-info` / `--analyze` / `--sdp-source` / `--connectionless` support. MAC
  defaults to `state.current_device` via the shared `_inject_current_mac` helper.
  The separate `csdp` verb (`bleep/modes/debug_classic.py`) keeps its raw
  socket-oriented SDP-browse semantics **unchanged** (do not overload `csdp`).
- **Debug `audiocfg` write sub-surface** (`bleep/modes/debug_media.py`, `cmd_audiocfg`):
  a leading `show|add|remove|tunnel|backup|restore` token (module-level
  `_AUDIOCFG_CONFIG_VERBS`) routes through `parse_as_cli("audio-config", …)` to the
  same `bleep.modes.audio.run_audio_config` core the CLI subcommand uses. No-arg /
  `--endpoints` / `--profile` keeps the existing read-only backend diagnostics.
- **Registry.** `classic-enum` → `full` (`debug=("cenum","csdp")`); `audio-config`
  → `full`.
- **Dispatch/help.** `cenum` added to `_build_dispatch_table` + BR/EDR Classic help
  group; `audiocfg` help line updated to advertise the dual read/write surface.
- **Docs.** `debug_mode.md` (BR/EDR Classic + Utilities tables + module map),
  `changelog.md`.
- **Tests.** `tests/test_m5_depth_parity.py` — registry `full` rows, dispatch
  reachability (`cenum`/`csdp`/`audiocfg`), `cenum` MAC-default / explicit-MAC /
  `--sdp-source` forwarding + no-device abort, `audiocfg` add/backup/tunnel
  delegation, `_AUDIOCFG_CONFIG_VERBS` gate, and write-verb `SystemExit`-containment.

### CDU-M6 — Documentation, registry & enforcement reconciliation — [x] IMPLEMENTED & VERIFIED

> **Goal.** Docs assert, and tests enforce, the final parity state.

**Landed changes.**

- **New guard `tests/test_docs_match_registry.py`.** Parses every Markdown code
  span (inline + fenced) in `cli_usage.md` / `debug_mode.md` and asserts, at the
  capability level, that each capability with a non-empty `cli_command` is
  documented in `cli_usage.md` and each with a non-empty `debug_command` is
  documented in `debug_mode.md` (word-boundary token match, "at least one owning
  command" — tolerant of alias omissions like `uuid-lookup`). Positive-only by
  design (names such as `monitor` legitimately appear on both surfaces; the
  negative direction is already covered by `test_cli_debug_parity.py`). Includes a
  targeted M2–M5 verb check + a self-test for the matcher.
- **Doc-sweep gaps filled in `debug_mode.md`.** Previously undocumented debug
  verbs added: `crfcomm`/`cbind` (Classic table), a new **Media & Audio** table
  (`mediaenum`/`mediaprops`/`mediactrl`/`audiorecon`/`audioplay`/`audiorec`), and
  `survey`/`survey-status` (BLE Scanning table). Without these the new guard fails.
- **New "Methodology & CLI parity" section** in `debug_mode.md` — the two surface
  contracts, the anti-drift mechanism (`shared_impl` / `_add_*_arguments` /
  `parse_as_cli` / `foreground_loop_handoff`), and the Class-A (CLI-only) /
  Class-B (debug-only) single-surface rationale. Module map gains
  `debug_cli_adapters.py` (M3) and `debug_advmon.py` (M2).
- **Hint-convention token list** (`tests/test_cli_hint_convention.py`) extended
  with the debug-unique verbs `cenum`/`netenum`/`cping`/`uuidtr`/`adaptercfg`/
  `gattserver`/`devicesets`.
  - **Deviation from plan (justified).** The plan also listed `advertise-monitor`
    and `mesh`; both are **identical to their CLI subcommand names**, so adding
    them to a "names unique to the debug shell" list would flag legitimate CLI
    self-references (false positives). They are intentionally omitted; the parity
    guard already enforces their cross-surface registration.

**Acceptance.** Docs/registry/test triad agree; guard suite green (pending user
run of the full `pytest`).

### CDU-M7 — Close residual `partial` rows (classic-scan, agent, aoi → full) — [x] IMPLEMENTED & VERIFIED

> **Goal.** Make each residual `partial` capability delegate to the same core the
> CLI uses, so the debug surface reaches the full capability with zero duplicated
> logic. Accepted 2026-07-29 with decisions D1=yes, D2=keep debug subcommand
> idiom, D3=keep live helper default.

**M7a — `classic-scan`.** The registry declares
`shared_impl="bleep.modes.classic_scan.run"` (`capability_registry.py:145-149`) but
debug `cmd_cscan` (`bleep/modes/debug_classic.py:47-63`) inlines a stripped scan
(hardcoded `duration=10`; no `--uuid/--rssi/--pathloss/--timeout/--adapter/--debug`;
no DB persistence) while `classic_scan.run` (`bleep/modes/classic_scan.py:8-115`)
supports all of them.
> - Extract `_add_classic_scan_arguments(parser)` in `bleep/cli/parsers/classic.py`
>   (single source for `--timeout/--uuid/--rssi/--pathloss/--debug/--adapter`);
>   repoint the CLI `classic-scan` subparser (`classic.py:48-57`) at it.
> - Replace the `cmd_cscan` body with `parse_as_cli("classic-scan", args)` →
>   `classic_scan.run(ns)`.
> - **D1 accepted:** debug `cscan` output format changes to the CLI format and
>   begins persisting discovered Classic devices to the observation DB.

**M7b — `agent`.** CLI exposes device management (`pairing.py:81-90`:
`--trust/--untrust/--list-trusted/--list-bonded/--remove-bond`) and the core runs
these as one-shot ops returning before the agent loop (`bleep/modes/agent.py:279`).
Debug `cmd_agent` (`bleep/modes/debug_pairing.py:167-178`) only has
`status/register/unregister`.
> - Add debug subcommands `trust <MAC>`, `untrust <MAC>`, `remove-bond <MAC>`,
>   `list-trusted`, `list-bonded` that translate to the CLI flag form and delegate
>   to `bleep.modes.agent.run` (`dispatch.py:159-162`) via `parse_as_cli`. Keep the
>   native session `status/register/unregister` (**D2 accepted**: debug keeps the
>   subcommand idiom). No loop risk — management flags return early (`agent.py:279`).

**M7c — `aoi`.** CLI `aoi` is a subcommand pipeline
(`AOI_SUBCOMMANDS=("scan","analyze","list","report","export","db")`,
`bleep/cli/parsers/aoi.py:8`; dispatch `dispatch.py:194-203`). Debug `cmd_aoi`
(`bleep/modes/debug_aoi.py:16-31`) is a live single-device helper.
> - Add a leading-verb gate (identical to M5 `audiocfg`): first token ∈
>   `AOI_SUBCOMMANDS` → `parse_as_cli("aoi", args)` + `apply_aoi_subcommand(ns)` →
>   `aoi.run(ns)`; otherwise keep the live `aoi [MAC]`/`aoi --save` helper (**D3
>   accepted**). No collision — a MAC never equals a subcommand name.

> **Registry.** `classic-scan`/`agent`/`aoi` `partial → full` with refreshed rationale.
> **Tests.** `tests/test_m7_partial_closure.py` — registry rows `full`; parse→delegate
> for cscan / agent-mgmt / aoi-subcommand (monkeypatched seams, hardware-free);
> native paths (`aoi <MAC>`, `agent status`) preserved; `SystemExit` containment.
> **Docs.** `debug_mode.md` (cscan filters, agent management rows, aoi subcommands);
> `changelog.md`.
> **Acceptance.** Three rows `full`; parity/docs guards green; delegation tests pass.

### CDU-M8 — Test-harness hygiene (mark registration + `sdp.py` deprecation) — [x] IMPLEMENTED & VERIFIED

> **Goal.** Zero-warning clean suite run; no production behavior change beyond a
> safe deprecation fix.
>
> **M8a — register pytest marks.** No config file exists (only `setup.py`). Create
> `pytest.ini` registering `pbap`; **D4 accepted:** add `pytest-timeout>=2.3.0` to
> `setup.py` test deps so `@pytest.mark.timeout(N)` is honored (real hang
> protection) rather than a no-op. Register `timeout` too for clarity.
> **M8b — fix `Element` truth-value deprecation.** `bleep/ble_ops/classic/sdp.py:670`
> `seq.find("uint8") or seq.find("uint16") or seq.find("uint32")` triggers the
> deprecated `Element.__bool__`; replace with explicit `is None` checks
> (behavior-preserving; `_xml_elem_value` already tolerates `None`).
>
> **Acceptance.** Suite emits 0 warnings (bar the 2 environmental hardware-CTF
> failures); `test_sig_sdp_profile_attr_ids.py::test_pdl_*` still pass; changelog updated.

### CDU-M9 — Anti-drift harmonization (`advertise-monitor` debug adapter → `parse_as_cli`) — [x] IMPLEMENTED & VERIFIED

> **Verification (2026-07-29).** Targeted guards `244 passed` (incl.
> `test_m7_partial_closure`, `test_advertise_monitor_uniformity`,
> `test_cli_debug_parity`, `test_docs_match_registry`, `test_cli_hint_convention`).
> Full suite `2 failed, 1966 passed, 34 skipped` with **zero warnings** (M8
> confirmed: 23 `PytestUnknownMarkWarning` + 1 `sdp.py` `DeprecationWarning`
> gone; `pytest-timeout` active). The 2 failures are the pre-existing
> environmental hardware-CTF tests (`test_ble_ctf_full`/`test_ble_ctf_integration`,
> BLE-CTF device `CC:50:E3:B6:BC:A6` not present) — not regressions.

> **Goal.** Every ported debug verb uses the single `parse_as_cli` seam; remove the
> last hand-built parser.
>
> **Task.** `debug_advmon.cmd_advertise_monitor` (`bleep/modes/debug_advmon.py:23-77`)
> predates `parse_as_cli` (M3). Replace `_build_parser`-driven parsing with
> `parse_as_cli("advertise-monitor", args)`, preserving the `caps` vs `start` branch
> and `foreground_loop_handoff`. Delete `_build_parser`; the shared
> `_add_advertise_monitor_start_arguments` builder stays consumed by the CLI parser
> (`utility.py:60`) and the registry `shared_args`.
> **Test impact.** `tests/test_advertise_monitor_uniformity.py` asserts the shared
> builder + registry path (lines 25/63/89), not `_build_parser`, so it stays green;
> add an assertion that the verb routes through `parse_as_cli`.
>
> **Acceptance.** Uniformity/parity/docs guards green; `debug_mode.md` methodology
> notes all ported verbs (incl. `advertise-monitor`) use `parse_as_cli`; changelog updated.

### CDU — Sequencing, risk, and definition of done

> | Milestone | Value | Risk | Depends on |
> |---|---|---|---|
> | M0 registry + guard | foundational | very low | — |
> | M1 Class-C drift | high (correctness) | low | M0 |
> | M1.5 pan rename | med | low | M0 |
> | M1.6 HID dual-variant | med-high | low | M0 |
> | M2 advertise-monitor | high (safety) | low | M0 |
> | M3 utility verbs | med-high | very low | M0 |
> | M4 stateful verbs | high | medium | M0 + shared builders |
> | M5 depth parity | medium | medium | M1 |
> | M6 docs/enforcement | high (durability) | low | all |
>
> **Cross-cutting mitigations.** (a) Standardize one `_ProgressShim` in
> `bleep/modes/debug_utils.py` (reuse the SR-G1 shim) so every ported `run()` core has
> a single adaptation path — no per-command shim duplication. (b) All acceptance tests
> are parse/dispatch/argument-equivalence (no adapter required), matching the existing
> test style; live validation is a manual acceptance step. (c) Merging entry points is
> explicitly forbidden; the registry's `parity` field records intentional
> single-surface commands.
>
> **Definition of done.** (1) `capability_registry.py` enumerates 100% of both
> surfaces and `test_cli_debug_parity.py` is green. (2) All Class-C divergences
> resolved via shared arg builders with parse-equivalence tests. (3) `monitor`
> collision resolved (CLI hard-renamed to `advertise-monitor`; Debug
> `advertise-monitor` added; property `monitor` unchanged). (4) `classic-pan` uses
> `server-reg`/`server-unreg` on both surfaces (Debug alias allowed). (5) HID
> classification available with and without connection on both surfaces. (6) `mesh`
> and `ctf` reachable in Debug; `refresh-refs` recorded `cli-only`. (7) Every
> `parity="full"` capability delegates to one shared implementation from both surfaces.
> (8) Docs regenerated/validated against the registry; hint-token list updated; full
> suite green.

---

## Live-test remediation LTR-1..LTR-8 (2026-07-28)

> **CONTEXT:** Findings from a 4-hour soak + exhaustive CLI live-test pass against
> local targets, then a triple-pass review and second exhaustive live sweep. All
> items accepted by the user, fixed, regression-gated (**full suite 1645 passed,
> 34 skipped**, lint-clean), and re-verified live. Changelog:
> `bleep/docs/changelog.md` ("Live-test remediation …"). CLI docs:
> `bleep/docs/cli_usage.md` ("Environmental limitations & known constraints").

### LTR-1 — async D-Bus reply dispatch (`advertise`/`gatt-server`/`monitor` silent 5 s timeout)  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED.** The six BlueZ register/unregister methods issued an async D-Bus
> call with `reply_handler`/`error_handler` then busy-waited with `time.sleep()`,
> so the GLib loop never dispatched the reply (and BlueZ's re-entrant handshake
> callbacks never ran) — every registration timed out even on success and the real
> error was hidden. New shared helper `bleep/dbuslayer/_dbus_wait.py::call_async_await`
> runs a temporary `GLib.MainLoop` (or polls when a background loop owns the
> default context), deadlines via a GLib timer, and surfaces the true error. Wired
> into `le_advertising.py`, `gatt_server.py`, `adv_monitor.py`. Live: `gatt-server`
> and `advertise` (broadcast **and** peripheral) work; `monitor` fails fast with
> the true `UnknownMethod` error. Tests: `tests/test_dbus_wait.py`.

### LTR-2 — defensive optional-property accessors (`media-enum --passive` Icon crash)  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED.** ~14 `device_le` accessors re-raised on `InvalidArgs` ("No such
> property"), crashing passive recon on LE-only peers. Collapsed into
> `_get_optional_property()` mapping both `UnknownObject` and `InvalidArgs` to
> `None`. Tests: `tests/test_device_le_optional_props.py`.

### LTR-3 — advertise payload include/property conflicts (`Failed to parse advertisement`)  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED.** BlueZ rejects an advertisement that sets a property explicitly and
> also auto-includes the same field. `_build_properties` now drops the redundant
> include. Verified conflict matrix live: `LocalName`↔`local-name` and
> `Appearance`↔`appearance` conflict (fixed); `TxPower`↔`tx-power` does not (left
> untouched). Tests: appearance-drop + tx-power-kept cases in
> `tests/test_le_advertising.py`.

### LTR-4 — `media-enum --passive` vanished-object (RPA rotation)  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED.** LE peers with resolvable-private addresses rotate/disappear between
> discovery and assessment; `assess_media_device` then emitted a raw
> `UnknownObject` D-Bus dump at the first state read. Now mapped to a clean
> `DeviceNotFoundError`. Tests: vanished-object + other-error-propagates in
> `tests/test_media_helpers.py`.

### LTR-5 — `classic-enum` fails on connected-but-non-discoverable peers  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED.** `_target_known()` (`ble_ops/classic/connect.py`) consults the
> object manager first, so bonded/cached/connected devices skip the fresh BR/EDR
> discovery gate. Tests: `tests/test_classic_target_known.py`.

### LTR-6 — `usb_ids` generator emits invalid `\R` escape (`SyntaxWarning`)  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED.** `update_usb_ids.py::_pystr()` now escapes `\` before `"`; the one
> affected generated line (`CD\RW 40X`) fixed. Live: `python3 -W error::SyntaxWarning
> -c 'import bleep.bt_ref.usb_ids'` is clean.

### LTR-7 — output ordering / verdict / bonded formatting polish  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED.** (a) `print_and_log` flushes stdout so piped/redirected output stays
> chronological. (b) `agent --list-bonded` renders epoch timestamps as
> `YYYY-MM-DD HH:MM:SS` with observations-DB name fallback. (c) `--diagnose-audio`
> verdict factors GStreamer SBC codec readiness ("routing available but codec
> plugins incomplete").

### LTR-8 — CORRECTION: "CSR peripheral advertising unsupported" was a misdiagnosis  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED.** The initial hypothesis that this CSR 4.0 controller rejects
> connectable `peripheral` advertising was disproven by the post-fix exhaustive
> sweep: peripheral advertising succeeds reliably (8/8 repeats + variants). The
> earlier failures were orphaned registrations left by the LTR-1 dispatch bug. The
> misleading "retry with `--type broadcast`" hint was removed; the mode now points
> to the real BlueZ error and `advertise caps`. Docs corrected accordingly. The
> only genuine advertising limit observed is `--include-appearance` *without* an
> explicit `--appearance` value (controller quirk) — now guided proactively, see
> LTR-9.

### LTR-9 — advertise `--include-appearance`-without-value guidance (A + B + C)  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED.** `--appearance <value>` sends a self-contained Appearance;
> `--include-appearance` asks BlueZ to source it from the (often-unset)
> adapter/system value → "Failed to register advertisement" (even though
> `appearance` is in `SupportedIncludes`: supported ≠ value-available; confirmed
> via `bluetoothctl show` exposing no adapter Appearance). Not a BLEEP bug — added
> guidance instead of removing the valid feature: **(A)** pre-registration warning
> when `--include-appearance` is used without `--appearance`; **(B)** targeted
> "pass --appearance <value>" hint on that specific failure; **(C)** pre-flight of
> all requested `--include-*` flags against the adapter's `SupportedIncludes` with
> a warning on any unsupported include. Logic in pure helper
> `bleep/modes/advertise.py::_validate_includes`; flag help text clarified
> (self-contained vs. sourced) in `bleep/cli/parsers/utility.py`. Live-verified:
> warning + hint fire on include-only; `--appearance 960` (± include) stays silent
> and succeeds. Tests: `tests/test_advertise_includes.py` (8 cases). Docs:
> `bleep/docs/cli_usage.md`.

---

## Multi-antenna live-test fixes LT-1..LT-2 (2026-07-27)

> **CONTEXT:** Findings from an extensive multi-antenna (hci0+hci1) live-test pass
> against local targets (BLE-CTF `CC:50:E3:B6:BC:A6`, Light Orb
> `F0:98:7D:0A:05:07`, Sphero robot `EC:04:28:42:18:4E`). Both items were accepted
> by the user and fixed 2026-07-27; regression-gated (relevant suites green,
> lint-clean) and re-verified live on hardware.

### LT-1 — `explore` passive mode spuriously fails `ServicesNotResolved` on rich GATT servers  — [x] ✅ RESOLVED (2026-07-27)

> **RESOLVED (2026-07-27).** Root cause: `passive_scan_and_connect`
> (`bleep/ble_ops/le/scan_modes.py`) split `--timeout` (default 10 s) as
> 50/25/25, leaving only **5 s** for service resolution with a single attempt.
> A Sphero (6 services / 25 chars) connected but could not resolve in 5 s, so
> `explore` failed twice where `gatt-enum`/`aoi scan` (15 s window / retry
> controller) succeeded on attempt 1. Fix: service-resolution floor raised to
> `max(timeout, 15)` s, connect floor to 5 s, plus one bounded connect+resolve
> retry (`max_attempts=2`, `backoff_max=5.0`) — matching gatt-enum/AoI robustness
> without becoming naggy. Sole caller of the passive path is `explore`
> (`bleep/modes/exploration.py:457`); other modes call `connect_and_enumerate`
> directly and are unaffected. Re-verified live: same Sphero now resolves
> (`Services resolved: True`, 6 services / 25 chars). Docs:
> `bleep/docs/explore_mode.md`.

### LT-2 — AoI analysis wrote `devices.last_seen` in local time (mixed-tz DB timestamps)  — [x] ✅ RESOLVED (2026-07-27)

> **RESOLVED (2026-07-27).** `bleep/analysis/aoi_analyser.py` wrote
> `last_seen` via `datetime.now().isoformat()` (local) while the observations
> layer and survey persistence use naive UTC (`datetime.utcnow().isoformat()`),
> so AoI-enumerated devices showed a `last_seen` earlier than their survey
> `first_seen` in `db list`. Normalized that writer plus three sibling
> `version_queried_at` local-time writers (`bleep/ble_ops/le/scan.py`,
> `bleep/modes/classic_enum.py`, `bleep/dbuslayer/device_classic.py`) to naive
> UTC — the existing dominant convention — rather than tz-aware, to avoid
> breaking lexicographic comparison against SQLite's naive `datetime('now')`
> (`bleep/core/observations/_devices.py:203`). Re-verified live: after
> `aoi analyze`, `last_seen` records UTC (`23:45` UTC, not local `19:45`),
> consistent with `first_seen`. **Follow-up:** repo-wide `datetime.utcnow()`
> deprecation migration is tracked separately as **DT-1** below (with plan +
> PoC). Historical rows keep their old local `last_seen` (new writes only); an
> optional one-off migration is available.

### DT-1 — Repo-wide `datetime.utcnow()` deprecation migration  — [x] ✅ RESOLVED (2026-07-28)

> **RESOLVED (2026-07-28).** Implemented per the spec below; **zero behavioural
> change** to stored data (format-preserving) — see results at the end of this
> entry. Original accepted plan retained verbatim for provenance.
>
> `datetime.utcnow()` is deprecated in
> Python 3.12+ and is used at **29 sites across 13 files**. Migration must
> **preserve the naive-UTC string format** the DB and comparison queries rely on.
> Authoritative spec + executed PoC + citations:
> `bleep/docs/datetime_utc_migration_plan.md`.
>
> **Constraint (non-negotiable).** DB DATETIME columns stay **naive UTC** (no
> `+00:00`/`Z` suffix). The `datetime.now(timezone.utc)` form the deprecation
> warning suggests is **aware** and appends an offset — it is the *wrong*
> replacement for DB strings. PoC-B proved mixing naive+aware rows raises
> `TypeError: can't subtract offset-naive and offset-aware datetimes`, so the
> migration must be **atomic** (no partial state) and **format-preserving**.
>
> **Solution (follow with fidelity):**
> 1. Add `bleep/core/time_utils.py` with:
>    - `utc_now() -> datetime` = `datetime.now(timezone.utc)` (aware; for
>      arithmetic/duration only, never persisted as a string).
>    - `utc_now_iso() -> str` = `datetime.now(timezone.utc).replace(tzinfo=None).isoformat()`
>      (naive-UTC string; byte-shape identical to legacy
>      `datetime.utcnow().isoformat()` per PoC-A — the drop-in for every DB write).
> 2. Add `tests/test_time_utils.py`: no-offset regex on `utc_now_iso()`;
>    `fromisoformat(utc_now_iso()).tzinfo is None`; `utc_now()` is aware and within
>    a few seconds of `utc_now_iso()`.
> 3. Replace the **25 string sites** → `utc_now_iso()` and the **4
>    `_maintenance.py` object sites** → `utc_now()`. Exact inventory in the plan
>    doc §6 (re-grep `utcnow(` before editing — line numbers drift). Fix/trim
>    imports; keep `from datetime import datetime` only where still used for other
>    calls.
> 4. **Gates:** `rg 'utcnow\(' bleep/` → **zero**; `rg 'datetime\.now\(\)' bleep/`
>    → only display/report/filename sites (local OK there); lint-clean; full
>    `tests/` suite green; add an observations-test assertion that a fresh
>    `last_seen` has **no** offset suffix.
> 5. Live-verify a fresh survey/aoi write still stores naive UTC and `db list`
>    ordering/recency behave; then flip this item to ✅ and update changelog.
>
> Historical rows already written in local time by the pre-LT-2 code are **not**
> rewritten by DT-1 (format-preserving, new writes only); an optional one-off
> backfill remains available separately.
>
> **RESULTS (2026-07-28).**
> - Added `bleep/core/time_utils.py` (`utc_now`, `utc_now_iso`) + `tests/test_time_utils.py` (5 tests).
> - Migrated all **29 sites across 13 files**: 25 string sites → `utc_now_iso()`;
>   4 `_maintenance.py` object sites → `utc_now()`. Unused `from datetime import
>   datetime` imports removed; display/report/filename `datetime.now()` sites and
>   the SQL literal `datetime('now')` deliberately left unchanged.
> - **Gates green:** `utcnow(` in `bleep/` → zero (only docstring mentions in
>   `time_utils.py`); lint-clean; `py_compile` OK; full suite **1627 passed / 27
>   skipped** (the only failures — 2 `test_preflight` gstreamer + 1 audio-codec
>   collection — are pre-existing env issues, reproduced with the change set
>   stashed, i.e. not caused by DT-1).
> - **PoC re-confirmed at runtime:** `utc_now_iso()` is byte-shape identical to
>   legacy `datetime.utcnow().isoformat()`, naive on roundtrip; the rejected
>   `datetime.now(timezone.utc).isoformat()` form appends `+00:00`.
> - **Live-verified (temp `BLEEP_DB_PATH`):** fresh `upsert_device` /
>   `upsert_services` / `insert_adv` all store naive UTC with no offset;
>   `first_seen == last_seen` on insert; `last_seen > datetime('now','-1 day')`
>   recency query matches; `bleep aoi list` renders end-to-end without error.

---

## Survey/AoI live-run findings LR-1..LR-5 (2026-07-25)

> **CONTEXT:** Findings from an agent-executed 4-hour `--transport both` survey
> (`--resume-db --adaptive --exclude-cached --checkpoint-interval 120 --auto-recover`)
> followed by `aoi scan --analyze` + `aoi report --all` against the observation DB.
> Artifacts and source-cited verification in
> `workDir/LongRun_20260725_070234/` (`FINDINGS_REPORT.md`,
> `GAP_VERIFICATION_AND_PLANS.md`). **Accepted by the user 2026-07-25.** Each item
> is regression-gated: full `tests/` suite must stay green and lint-clean before an
> item is marked ✅.

### Root mechanism (shared by LR-1/LR-3)
`get_discovered_devices()` builds its list from `GetManagedObjects()`
(`bleep/dbuslayer/adapter.py:188-194`), returning every device BlueZ knows about —
including bonded/cached devices that did not advertise this round — each carrying
`rssi`/`paired`/`bonded` keys (`adapter.py:239,251-252`, `rssi=None` unless actively
advertising/connected). Both survey rounds consume this
(`bleep/ble_ops/le/scan.py:71,286-294`; `bleep/modes/survey.py:578-582`).

### Order of work
1. **LR-1a** — `--exclude-cached` bypass for DB-resumed devices *(correctness)*
2. **LR-2** — `fingerprint_changed` never fires on same-length payload rotation *(correctness)*
3. **LR-3** — `adv_reports` stores duplicate rows every round *(efficiency/hygiene)*
4. **LR-5** — `aoi report --all` average/table diluted by non-enumerated targets *(reporting)*
5. **LR-1b** — `sighting_count` inflated by cached re-reads *(DEFERRED — semantic change)*
6. **LR-4** — pure-Classic ~0 after warm-up *(DISPROVEN — environmental, no action)*

---

### LR-1a — `--exclude-cached` bypass: DB-resumed devices default `is_cached=False`  — [x] ✅ RESOLVED (2026-07-25)

> **RESOLVED (2026-07-25).** `seed_from_db()` now builds each `DeviceSighting` with
> `is_cached=True`; the existing re-sight path clears it on live RSSI
> (`survey.py:252-253`). +3 tests (`test_seed_marks_devices_cached`,
> `test_seed_cached_excluded_by_exclude_cached`, `test_seed_cached_cleared_when_seen_live`).
> Full suite **1574 passed / 27 skipped**.


**Problem.** `--resume-db --exclude-cached` still emits bonded devices that were
never actively seen this scan (observed: `43:25:00:6A:0E:CA`, `98:3B:8F:EF:FE:EC`,
`6F:C9:74:D7:E9:22` with `sightings≈929`, `rssi_avg=None`).

**Root cause.** `SurveyCensus.filter` excludes only when `exclude_cached and
s.is_cached` (`bleep/modes/survey.py:333-335`); `is_cached` is set only for a *new*
sighting with `rssi is None and (paired or bonded)` (`survey.py:284-287,303`) and
cleared on RSSI (`survey.py:252-253`). `seed_from_db()` builds `DeviceSighting`
**without** `is_cached` (`survey.py:491-507`), so it defaults `False`
(`survey.py:157`) — resumed devices are never cache-excluded.

**Fix.** Set `is_cached=True` on the seeded `DeviceSighting`; the existing re-sight
path clears it when the device is seen live with RSSI. Matches the documented
`--exclude-cached` semantics (`bleep/docs/survey_mode.md:157-162`). +2 tests.

### LR-2 — `fingerprint_changed` never fires on same-length payload rotation  — [x] ✅ RESOLVED (2026-07-25)

> **RESOLVED (2026-07-25).** `_merge_mfr_data`/`_merge_svc_data` now adopt-and-flag on
> `len(new)==len(old) and new!=old` in addition to strictly-longer. Longest-wins and
> shorter-ignored preserved. +4 tests (mfr same-len change/identical, svc same-len
> change [Light Orb case], svc shorter-ignored).


**Problem.** 0/76 devices flagged `fingerprint_changed` despite a real rotation:
Light Orb (`F0:98:7D:0A:05:07`) service-data `0210ffff00`→`0210ffff02` (same length,
last byte 00→02).

**Root cause.** `_merge_mfr_data`/`_merge_svc_data` set `changed=True` only when the
incoming payload is *strictly longer* (`survey.py:200-202`, `219-221`); same-length
rotations (normal iBeacon/Eddystone case) are never detected.

**Fix.** Add a same-length-difference branch: adopt payload + flag when
`len(new)==len(old) and new!=old`. Preserve longest-wins (`test_survey.py:520-536`),
shorter-ignored (`:538-553`, `:601-615`). +2 tests.

### LR-3 — `adv_reports` stores a duplicate row every round (no dedup)  — [x] ✅ RESOLVED (2026-07-25)

> **RESOLVED (2026-07-25).** `insert_adv` now skips the insert when `(data, decoded)`
> equals the latest row for that MAC (new `_as_blob_bytes` normalizer). RSSI-only
> changes are deliberately not persisted (RSSI aggregates live on the `devices` row);
> `decoded` excludes RSSI (`scan.py:221-249`). Non-consecutive A,B,A still yields 3
> rows. +5 tests in `tests/test_insert_adv.py`.


**Problem.** 1807 adv rows for the run (all with empty `data` blob); 465 identical
rows for BLECTF; near-constant `decoded` per device.

**Root cause.** `insert_adv` performs an unconditional `INSERT` with no comparison to
the prior row (`bleep/core/observations/_history.py:20-35`), called every round per
device seen with RSSI (`bleep/ble_ops/le/scan.py:215,250`). The raw `data` blob is
built only from `advertising_data` (`scan.py:216-220`), which `GetManagedObjects()`
rarely exposes (`adapter.py:258`) → always empty.

**Fix.** Coalesce consecutive identical samples: skip the insert when `(data,
decoded)` equal the latest row for that MAC. +tests in `tests/test_insert_adv.py`.

### LR-5 — `aoi report --all` diluted by non-enumerated targets  — [x] ✅ RESOLVED (2026-07-25)

> **RESOLVED (2026-07-25).** New `AOIAnalyser._device_was_enumerated()` (services /
> SDP / pairing / characteristics / any concern). Markdown/text split into "Analyzed"
> vs "Not Reachable (no GATT/SDP enumerated)"; average computed over analyzed only.
> JSON adds `analyzed_count`/`not_reachable_count` + per-device `reachable`;
> `device_count`/`avg_security_score` keys retained. +2 tests.


**Problem.** Average risk pulled to 0.6/10 by dozens of `0/10` rows for LE targets
that never enumerated (stale RPAs); summary table does not distinguish
"analyzed, clean" from "never reached".

**Root cause.** `generate_aggregate_report` averages/table over all devices with
saved data (`bleep/analysis/aoi_analyser.py:1811-1835,1851-1859`); failed devices
have no `services` key (verified against saved AoI JSON).

**Fix.** Classify `bool(dev.get("services"))`; average over enumerated only; split
the summary into "Analyzed" vs "Not reachable (no GATT/SDP enumerated)". +test.

### LR-1b — `sighting_count` inflated by cached ManagedObjects re-reads  — [x] ✅ RESOLVED (2026-07-25)

> **RESOLVED (2026-07-25).** `SurveyCensus._merge_entry` gates the increment on the
> cached predicate (`is_cached_reread = rssi is None and (paired or bonded)`,
> `survey.py:259-266`); new cache-only entries seed `sighting_count=0`
> (`survey.py:313`), excluded by default `--min-sightings 1` like `--resume-db`
> seeds. +3 tests. Docs: `survey_mode.md` "Sighting-count semantics";
> `changelog.md`. Trade-off (transient unpaired lingering object may count) accepted.

**Problem.** `sighting_count += 1` is unconditional per round (`survey.py:255`), so
`GetManagedObjects()` re-reads of bonded/paired devices that never advertised this
round inflate the count (≈rounds, ×2 for dual). **Live-confirmed:** 4 paired devices
(`98:3B:8F:EF:FE:EC`, `F4:B6:88:0B:90:22`, `9C:D3:5B:A0:C3:C4`, `43:25:00:6A:0E:CA`)
enumerated 6/6 rounds with RSSI **never** present.

**RSSI-reliability finding (why the naive fix was rejected).** RSSI is *"volatile;
only valid during discovery"* (`bluez_interface_properties.md:33`); under passive
(`DuplicateData=True`) the per-round RSSI cache is populated only from
`PropertiesChanged` while discovery is active (`signals.py:2223-2240`, cleared each
`start_discovery` `manager.py:200-201`) and `InterfacesAdded` RSSI is not captured.
**Live-confirmed:** passive RSSI-present rate ≈96% (one unpaired advertiser flapped
`[None,None,None,-60]`), naggy 100%. So gating on raw `rssi is not None` would
**undercount** real advertisers → rejected.

**Fix (accepted 2026-07-25).** Gate the increment on the **cached predicate** already
computed for `is_cached` — skip only a re-read where `rssi is None and (paired or
bonded)` (`survey.py:296-299`); new entries seed `sighting_count = 0 if cached else 1`.
This fixes bonded inflation without undercounting unpaired advertisers with
transiently-missing RSSI. Accepted trade-off: a transient *unpaired* lingering managed
object may be counted (bounded by BlueZ's ~30 s temporary-device eviction; safer than
undercounting). `last_seen` keeps advancing on cached re-reads; dual seen live in both
rounds counts 2/cycle. +3 tests. Applies equally to `debug survey` (shared census).

### LR-6 — Passive-scan RSSI capture misses `InterfacesAdded` (positive-direction fidelity)  — [x] ✅ RESOLVED (2026-07-25)

> **RESOLVED (2026-07-25).** Shared `system_dbus__bluez_signals._capture_device_rssi()`
> helper (`signals.py`) now called from both `PropertiesChanged` and
> `_interfaces_added` (guards: device path, `is_discovery_active`, `DEVICE_INTERFACE`
> carries RSSI). Additive, no radio-behavior change. +10 tests
> (`tests/test_signals_rssi_capture.py`). Naggy-by-default rejected; future opt-in
> `--naggy-rounds` flag tracked separately.

**Problem.** The DeviceManager RSSI cache is fed only by `PropertiesChanged`
(`signals.py:2223-2240`); the first-seen `InterfacesAdded` properties (which carry
RSSI) are ignored (`_interfaces_added` `signals.py:2302-2329`). Under passive
(one event/device/session) a live device can therefore report `rssi=None`.
**Live-confirmed:** passive ≈96% vs naggy 100% RSSI-present.

**Fix (accepted 2026-07-25).** Extract the existing capture logic into a shared
`_capture_device_rssi(path, rssi)` helper (guards: device path + `is_discovery_active`)
and call it from both `PropertiesChanged` and `_interfaces_added` (only when
`DEVICE_INTERFACE in interfaces` and `"RSSI"` present). Additive, no footprint change.
Switching survey rounds to naggy by default is **rejected** (changes the passive/quiet
character); a future opt-in `--naggy-rounds` flag is tracked separately. +tests.

### LR-4 — pure-Classic discovery ~0 after warm-up  — [x] DISPROVEN (2026-07-25)

`_run_classic_round` runs a real `bredr` inquiry and keeps `br/edr|dual`
(`survey.py:570-582`); 0-Classic is environmental (no discoverable pure-BR/EDR
devices; bonded audio correctly `dual`). No code defect. Manual check: run
`bleep survey --transport bredr` near a known discoverable BR/EDR device.

---

## Survey → AoI live-run findings SR-N1..SR-C4 (2026-07-22)

> **CONTEXT:** Findings from a manually-executed 4-hour `both`-transport survey
> followed by `aoi` scan/analyze/report against the observation DB (see the
> chat review of terminals 4–9 and the produced `~/.bleep/aoi/reports/*`). The
> pipeline ran end-to-end; these items fix correctness/efficiency/hygiene gaps
> the run exposed. **Accepted by the user 2026-07-22.** Work proceeds in the
> order below (SR-N1 first). Each item is regression-gated: full `tests/` suite
> must stay green and lint-clean before an item is marked ✅.

### Recommended order of work
1. **SR-N1** — DB-hydrated SDP/pairing dropped from analysis *(correctness; highest priority)*
2. **SR-N3** — LE enumeration ignores `--timeout`; wasteful attempts on seeded Classic/dual
3. **SR-G2** — `aoi scan` does not analyze inline
4. **SR-G1** — `survey` has no census checkpointing
5. **SR-N4 / SR-N5** — report hygiene (synthetic-device filter; concern UUID/handle + de-dup)
6. **SR-N2** — passive→AoI staleness (optional pre-enum refresh scan)
7. **SR-G4** — `report --all` + `--db-only` with no analyzed rows yields an empty report
8. **SR-C4** — `rssi_max` renders `-` for bonded devices *(cosmetic / doc-only)*

---

### SR-N1 — CRITICAL: DB-hydrated SDP records & pairing events are dropped from analysis/reports  — [x] ✅ RESOLVED (2026-07-22)

> **RESOLVED (2026-07-22).** `_hydrate_db_device_data()` now maps
> `sdp_records`/`classic_services` → `sdp_summary` and latest `pairing_events`
> → `pairing_profile` (new `_pairing_event_to_profile()`); `_analyse_pairing_profile`
> flags default/weak PINs (new `_is_weak_pin()`); `_assign_concern_risk` maps
> weak-PIN reasons to medium; `_analyse_sdp_records` hardened for NULL names.
> **Verified live:** `14:89:FD:31:8A:7E` now reports **6/10** with SDP Discovery +
> Pairing Profile sections and 3 medium concerns (PBAP/OPP exposed + PIN 0000).
> 9 new tests (`tests/test_aoi_sr_n1_db_hydration.py`); full suite **1320 passed,
> 27 skipped**. Docs: `changelog.md`, `aoi_security_algorithms.md`.

**Problem.** When `aoi analyze` loads a device **from the observation DB**, its
Classic SDP records and pairing history never reach the analyzer, so every
Classic/dual device analyzed from the DB scores `0/10` with empty Services and
no SDP/Pairing report sections.

**Proof.** `14:89:FD:31:8A:7E` (PhreakMe-Blue) has in the DB: OBEX Object Push
(RFCOMM ch17), HFP Voice Gateway (ch4), HSP (ch3), a "BT DIAG" **Serial Port**
(ch16), plus a `pairing_events` row (`method=RequestConfirmation`, `pin=0000`,
`result=success`, bonded). Its generated report is `0/10`, empty Services, no
SDP/Pairing sections. Across the 47-device aggregate: `## SDP Discovery` = 0,
`## Pairing Profile` = 0, `obex|serial port|voice gateway|bt diag|handsfree` = 0.

**Root cause.**
- `get_device_detail()` returns relational lists under keys `sdp_records`,
  `classic_services`, `pairing_events` (`bleep/core/observations/_devices.py:268-360`).
- `_hydrate_db_device_data()` converts only characteristics / services /
  security_maps; it never maps `sdp_records`/`pairing_events` to the keys the
  analyzer reads (`bleep/analysis/aoi_analyser.py:123-213`).
- `analyse_device()` gates SDP on `"sdp_summary" in data` and pairing on
  `"pairing_profile" in data` (`aoi_analyser.py:760-773`) — keys DB hydration
  never sets. (`load_device_data()` calls the hydrator at `aoi_analyser.py:400`.)

**Plan.**
1. Extend `_hydrate_db_device_data(device_data)` (aoi_analyser.py:123):
   - If `sdp_summary` not already present and (`sdp_records` or
     `classic_services`) is non-empty, set
     `device_data["sdp_summary"] = list(sdp_records or classic_services)`.
     Prefer `sdp_records` (full snapshots incl. `protocol_descriptors`,
     `profile_descriptors`, `name`, `uuid`) — shape already consumed by
     `_analyse_sdp_records()` and `SDPAnalyzer` (aoi_analyser.py:1122-1164).
   - If `pairing_profile` not present and `pairing_events` is non-empty, derive
     a profile dict from the **latest** row (list is `ORDER BY ts DESC`):
     `{"attempted": True, "paired": result=="success" or fully_bonded(post_pair_state),
       "method": method, "pin": pin, "capabilities": capabilities,
       "result": result, "error": <None>}`. Parse `post_pair_state` JSON to read
       `fully_bonded`.
   - Purely additive; never overwrite a key the caller already set (file-sourced
     data keeps priority). Wrap JSON parsing defensively.
2. Enhance `_analyse_pairing_profile()` (aoi_analyser.py:1166) to surface real
   findings the current JustWorks-only check misses, **without** double-counting:
   - Flag **default/weak PINs** (`0000`, `1234`, `1111`, all-same-digit, or
     numeric length < 6) → medium concern "Default/weak pairing PIN observed
     (<pin>)".
   - Keep existing JustWorks (high) and error handling.
   - Return `method`/`paired`/`pin` so the report render can show them.
3. Confirm the risk-mapping for these reasons in `_assign_concern_risk()`
   (aoi_analyser.py:90): "Classic profile exposed" → medium (already), add
   "default/weak pairing pin" → medium. JustWorks stays high.

**Tests (add to `tests/` AoI-analyzer suite).**
- `test_hydrate_maps_sdp_records_to_sdp_summary` — DB-shaped detail with
  `sdp_records` → after hydrate, `sdp_summary` present with same records.
- `test_hydrate_maps_pairing_events_to_profile` — latest-row derivation, bonded
  detection from `post_pair_state`.
- `test_hydrate_does_not_override_file_sdp_summary` — pre-existing key preserved.
- `test_analyse_device_flags_classic_profiles_from_db` — 14:89-like fixture →
  ≥1 medium concern referencing OBEX/Serial; score > 0.
- `test_default_pin_flagged` — pin `0000` → medium concern.
- Regression: existing clean-device = 0/10 tests still pass (no synthetic
  concerns added when no SDP/pairing data).

**Docs.** Update `bleep/docs/aoi_security_algorithms.md` (SDP/pairing sourcing)
and `changelog.md` Unreleased.

**Risk.** Adds real scored concerns → Classic/dual device scores rise from the
false `0/10`. This is the intended correction. Guarded so LE-only and
data-less devices are unaffected.

**Acceptance.** PhreakMe-Blue report shows an SDP Discovery section listing
OBEX/HFP/HSP/BT-DIAG, a Pairing Profile section (default PIN flagged), and a
non-zero risk score; full suite green.

---

### SR-N3 — LE enumeration ignores `--timeout`; seeded Classic/dual burn 3 LE attempts  — [x] ✅ RESOLVED (2026-07-22)

> **RESOLVED (2026-07-22).** `EnumerationController.enumerate()` gained
> keyword-only `timeout` (→ `timeout_connect`/`timeout_services` on the passive
> base-connect path) and `max_attempts` (per-call loop bound). `_scan_target`
> forwards `--timeout` and caps seeded `dual` targets to 1 LE attempt before SDP.
> CLI `--timeout` help updated. 5 new tests
> (`tests/test_enum_controller_sr_n3.py`); full suite **1325 passed, 27 skipped**.

**Problem/Proof.** `aoi … --timeout 30` never reaches the LE connect path;
`EnumerationController.enumerate()` takes no timeout and calls
`connect_and_enumerate__bluetooth__low_energy(self.target_mac)` with only the MAC
(`bleep/ble_ops/le/enum_controller.py:187-238`). Live cost: 14:89:FD stored
annotations show 3× `br-connection-page-timeout` ~27 s apart (≈80 s wasted per
unreachable dual device) before SDP. `--timeout` currently only bounds SDP/pairing.

**Plan.**
1. Thread an optional `timeout` into `EnumerationController.enumerate(mode, timeout=None, **kw)`
   and pass to `connect_and_enumerate__bluetooth__low_energy(mac, timeout=…)` if
   the callee supports it (verify signature; add kwarg passthrough if missing —
   minimal, backward-compatible default `None`).
2. In `modes/aoi.py::_scan_target`, pass the AoI `timeout` to `enumerate()`.
3. For targets whose **seeded** type is `classic` (not `dual`), skip the LE
   enumeration entirely and go straight to SDP. For `dual`, cap LE to **1**
   attempt before SDP fallback (configurable via existing `MAX_ATTEMPTS`; use a
   per-call `max_attempts` override rather than mutating the class constant).

**Tests.** `timeout` forwarded (monkeypatched connect asserts kwarg); seeded
`classic` skips LE; `dual` tries LE once then SDP. Existing enum tests green.

**Docs.** `changelog.md`; note in AoI `--help`/`aoi_implementation.md` that
`--timeout` now bounds LE connect too.

**Risk.** Signature change is additive (default keeps current behavior).

---

### SR-G2 — `aoi scan` does not analyze inline  — [x] ✅ RESOLVED (2026-07-22)

> **RESOLVED (2026-07-22).** Added opt-in `--analyze` (`dest=analyze_inline`) to
> the flat `aoi` parser; the scan loop calls `analyse_device()` per target after
> persistence (analyses Classic SDP/pairing too, not only LE-successful). Default
> off. 2 new CLI tests; full suite **1327 passed, 27 skipped**.

**Problem.** The run required a separate `analyze` loop; `aoi scan` only
enumerates + persists (`modes/aoi.py::_scan_target`).

**Plan.** Add `--analyze` flag in `cli/parsers/aoi.py::_add_aoi_arguments`
(default off, preserving current behavior). In the scan command handler
(`modes/aoi.py`), after a target enumerates successfully, call
`AOIAnalyser.analyse_device()` inline for that MAC. Reuse the analyzer instance
already built with the resolved `use_db`/`db_only`.

**Tests.** `scan --analyze` produces analysis rows; without the flag behavior
unchanged. Parser accepts `--analyze` on the flat `aoi` parser.

**Docs.** `changelog.md`; AoI usage docs.

**Risk.** None (opt-in).

---

### SR-G1 — `survey` has no census checkpointing  — [x] ✅ RESOLVED (2026-07-22)

> **RESOLVED (2026-07-22).** New `--checkpoint-interval N` (0=off, needs `-o`);
> the round loop writes `<output>.partial` atomically every N s via
> `_write_survey_checkpoint()` and removes it after the clean final write.
> Filter/format shared with the final write (`_format_survey_output()`). 5 new
> tests (`tests/test_survey_checkpoint_sr_g1.py`); full suite **1332 passed, 27
> skipped**. (Graceful SIGINT/SIGTERM already fell through to the final write;
> this hardens against hard crashes.)

#### SR-G1-FollowUp — debug-shell `survey` silently ignores `--checkpoint-interval`  — [x] RESOLVED (fixed 2026-07-23)

> **Bug (was).** The debug-shell `survey` command (`bleep/modes/debug_survey.py::cmd_survey`)
> built its parser from the shared `_add_survey_arguments()`, so it **parsed**
> `--checkpoint-interval` into `opts.checkpoint_interval` — but it was **never
> forwarded**: `cmd_survey` constructed `_survey_worker(...)` without the value,
> and `_survey_worker` had **no `checkpoint_interval` parameter** and no
> `.partial` write in its round loop. Net effect: in Debug Mode the flag was a
> **silent no-op** — SR-G1 checkpointing never ran, so a long debug survey that
> hard-crashed lost the entire aggregated census (only the full CLI `bleep
> survey` path honored it).
>
> **Fix (shipped 2026-07-23).** Added a `checkpoint_interval` parameter to
> `_survey_worker`, forwarded `opts.checkpoint_interval` from `cmd_survey`, and
> reused the CLI's `_write_survey_checkpoint()` / `.partial` atomic-write logic in
> the debug round loop (guarded on `output` set and interval > 0, matching the
> CLI) via a small `_ProgressShim` that routes the checkpoint's `emit_progress`
> line to `print_and_log` (the debug shell has no `OutputContext`). The worker
> now also removes the stale `.partial` after its clean final write, matching the
> CLI. `tests/test_survey_checkpoint_sr_g1.py` gained
> `TestDebugSurveyCheckpointing` (checkpoints fire mid-run + `.partial` cleanup;
> interval 0 stays a no-op) — all 7 SR-G1 tests pass.
>
> **Docs.** `survey_mode.md` updated: the `--checkpoint-interval` row, the Census
> Checkpointing section, and the Debug Shell Integration section now state the
> flag is supported in **both** the CLI and the debug shell (the earlier
> "CLI only" caveat was removed).

**Problem.** Census JSON is written only at the very end
(`bleep/modes/survey.py:732-738`); a crash late in a long run loses the
aggregated census/RSSI history (DB rows survive).

**Plan.** Add `--checkpoint-interval N` (seconds, default 0 = off) in
`cli/parsers/survey.py`. In the survey round loop, when elapsed since last
checkpoint ≥ N, write the current `format_objects(filter(...))` to
`<output>.partial` (atomic write via temp file + `os.replace`). Also emit a
checkpoint on `SIGINT`/`SIGTERM` in the existing signal handling. No-op when no
`--output` or interval 0. Do not alter the final-write format.

**Tests.** Checkpoint file written at interval (fake clock); atomic replace;
disabled by default. Existing survey tests green.

**Docs.** `changelog.md`; survey usage docs.

**Risk.** Extra periodic disk write; bounded by interval, atomic.

---

### SR-N4 — Reports polluted with synthetic test-fixture devices  — [x] ✅ RESOLVED (2026-07-22)

> **RESOLVED (2026-07-22).** New `_is_synthetic_mac()` (narrow fixture set:
> `AA:BB:CC:DD:EE:*`, `11:22:33:44:55:66`, all-zero — never a real RPA);
> `list_devices(include_synthetic=False)` excludes them by default. Filtering is
> confined to `list_devices()`, so explicit-address callers are unaffected. CLI
> `--include-synthetic` restores them. 4 new tests
> (`tests/test_aoi_synthetic_filter_sr_n4.py`); full suite **1336 passed, 27
> skipped**.

**Problem/Proof.** Aggregate rows include `AA:BB:CC:DD:EE:{01..04,FF}` and
`11:22:33:44:55:66` ("Test"/"Legacy"/"Alias-Test"/"RT-Test"/"Limit"/"Latest"),
inflating "Devices Analyzed: 47" and diluting the average score.

**Plan.** Add a synthetic-MAC predicate (documentation-locale MAC ranges
`AA:BB:CC:DD:EE:*`, `00:00:00:00:00:00`, `11:22:33:44:55:66`) and exclude them
from `list_devices()`/aggregate report generation **by default**, with an
opt-in `--include-synthetic` escape hatch on `aoi list`/`report`. Prefer a
single helper (e.g., `_is_synthetic_mac`) reused by both paths (DRY).

**Tests.** Synthetic MACs filtered by default; `--include-synthetic` restores
them; real RPAs (random-static/private) NOT filtered.

**Docs.** `changelog.md`.

**Risk.** Must not filter legitimate locally-administered RPAs — restrict to the
explicit doc/test ranges only.

---

### SR-N5 — Findings are undifferentiated (no UUID/handle; identical strings)  — [x] ✅ RESOLVED (2026-07-22)

> **RESOLVED (2026-07-22).** New `_dedup_concerns()` + `_concern_id_suffix()`
> collapse identical `(name, desc, risk)` concerns and append the distinct char
> identifiers (`uuid`/`uuid#handle`) with a `×N` count. Markdown + text renders
> use them; JSON keeps the full per-UUID list. 7 new tests
> (`tests/test_aoi_concern_render_sr_n5.py`); full suite **1343 passed, 27
> skipped**.

**Problem/Proof.** Light Orb shows 21 identical
"Custom characteristic accepts write-without-response…" concerns with no UUID or
handle in the rendered markdown.

**Plan.** The concern dict already carries `uuid` (`_char_concern_from_report`,
aoi_analyser.py:992-1008); the markdown/text renderers drop it. Update the
concern render (markdown + text report builders) to include
`` `<uuid>` `` (and handle when present) in each concern line, and collapse
exact-duplicate `(name, reason, risk)` tuples into a single line with a
`(×N: uuid1, uuid2, …)` suffix. JSON report keeps the full per-UUID list.

**Tests.** Rendered concern line contains the char UUID; duplicate concerns are
aggregated with a count; JSON unchanged.

**Docs.** `changelog.md`.

**Risk.** Cosmetic; ensure JSON schema for `security_concerns` unchanged.

---

### SR-N2 — passive→AoI staleness for RPA LE devices  — [x] ✅ RESOLVED (2026-07-22)

> **RESOLVED (2026-07-22).** New opt-in `aoi --refresh-scan SECS` (default 0)
> runs a `passive_scan()` before the target loop to repopulate BlueZ's cache.
> **Deviation:** used an explicit-value int rather than the planned optional
> `[=SECS]` (`nargs='?'`) — the flat `aoi` positional `files` would otherwise
> swallow a following token. 2 new CLI tests; covered by full-suite run.

**Problem/Proof.** Most LE survey targets were `not_found` at AoI time (RPAs
rotated hours later); `DeviceNotFoundError` → immediate `GIVE_UP`
(`enum_controller.py:331-332`).

**Plan.** Add opt-in `--refresh-scan[=SECS]` to `aoi scan`: before enumerating
the target list, run a short discovery (reuse existing scan entry point) to
re-populate BlueZ's object cache, then enumerate. Default off. Document that AoI
should ideally run promptly after survey.

**Tests.** With `--refresh-scan`, a discovery is invoked before enumeration
(monkeypatched); default path unchanged.

**Docs.** `changelog.md`; AoI usage note on the survey→AoI decay window.

**Risk.** Adds active scanning (opt-in only).

---

### SR-G4 — `report --all` + `--db-only` with no analyzed rows yields empty report  — [x] ✅ RESOLVED (2026-07-22)

> **RESOLVED (2026-07-22).** The empty-aggregate branch now distinguishes "no
> devices" from "scanned but not analysed" and prints an actionable hint
> (`aoi analyze` / `aoi scan --analyze`); returns non-zero. 1 new CLI test.

**Problem.** Conditional (didn't bite this run because the file store had
analyzed data). With `db_only` and no analyzed rows, an empty report is produced
silently.

**Plan.** In the `report --all` handler (`modes/aoi.py`), when `db_only` is set
and zero analyzed devices are found, emit an explicit warning directing the user
to run `aoi analyze` (return non-zero or clear message) instead of writing an
empty aggregate.

**Tests.** `db_only` + empty analysis → warning + no empty file; normal path
unchanged.

**Docs.** `changelog.md`.

**Risk.** None.

---

### SR-C4 — `rssi_max` renders `-` for bonded/cached devices  — [x] ✅ RESOLVED (2026-07-22, doc-only)

> **RESOLVED (2026-07-22).** Documented in `observation_db_schema.md`: NULL/`-`
> `rssi_max` = no RSSI ever observed (typically bonded/cached), not an error.

**Problem/Proof.** `db list --fields …,rssi_max` shows `-` for bonded devices
(never recorded RSSI). Harmless but misleading.

**Plan.** Documentation-only: note in `db` usage docs that `-`/NULL `rssi_max`
means "no RSSI observed (typically bonded/cached device)". No code change unless
we later choose to display `n/a`.

**Risk.** None.

---

## AoI Analysis & Reporting — deep review findings F1–F10 (2026-07-16) — ALL F1–F10 ✅ IMPLEMENTED (Batches 1–5)

> **STATUS (2026-07-16, FINAL — all findings complete):** **All ten findings
> (F1–F10) are IMPLEMENTED, lint-clean, and regression-verified.** Full `tests/`
> suite: **1311 passed, 27 skipped, 0 failed.** Nothing remains open. Batch map:
> - **Batch 1 (F1, F2, F4, F6):** security-map dual-shape normalizer; production
>   parser defaults (`--timeout=30`, `--format=markdown`); read-only `report`
>   (`persist=False`); pairing gated strictly behind `--deep`.
> - **Batch 2 (F3):** AoI parsers consolidated onto the flat production parser
>   (canonical `_add_aoi_arguments` / `apply_aoi_subcommand`).
> - **Batch 3 (F8, F9):** curated vendor OTA/DFU UUID detection + refined unusual
>   heuristics; SDP enrichment via `SDPAnalyzer` (both score-neutral).
> - **Batch 4 (F7, F10):** append-only `aoi_analysis_history` table (schema
>   v16→v17) + `get_aoi_analysis_history()`; documentation-drift fixes.
> - **Batch 5 (F5):** risk score redesigned to baseline-0 integer weights
>   (`min(10, high×3 + medium×2 + low×1)`); clean device = 0/10.
>
> The per-finding `RESOLVED` blocks below and the `changelog.md` "Unreleased"
> Batches 1–5 entries are authoritative. The dated Batch 1/2/3 STATUS blocks and
> the "Recommended batching" section that follow are retained as the historical
> planning record; where they say F5/F7/F10 are "PLANNED", that is superseded by
> this block.
>
> ---
>
> **STATUS (2026-07-16, Batch 3):** **Batch 3 (F8, F9) is IMPLEMENTED, lint-clean,
> and regression-verified** — `1305 passed, 27 skipped` (full `tests/` suite,
> zero regressions); `549 passed` across the AoI + SDP-analyzer suites with 8 new
> tests. What landed:
> - **F8** — notable-service detection broadened with a curated
>   `_OTA_DFU_SERVICE_UUIDS` set + `_canonical_uuid()` normaliser (vendor
>   OTA/DFU services with custom 128-bit UUIDs are now flagged); the name
>   heuristic also matches "firmware" ("OTA" kept as a case-sensitive acronym to
>   avoid "toyota"-style false positives). The unusual-characteristic
>   rules were refined (case-insensitive **writable + notify/indicate**; long
>   value tightened to hex-like > 40 chars). Informational lists only — **no**
>   score impact.
> - **F9** — `_analyse_sdp_records` routes records through
>   `SDPAnalyzer.analyze()`, surfacing `protocols`/`rfcomm_channels`/`anomalies`/
>   `inferred_spec_version` while **preserving** `raw_count`/`services_found`/
>   `security_flags`. Guarded (falls back to the shallow summary on error);
>   rendered in the markdown/text SDP sections. No new scored concerns.
> - **Score safety:** neither item adds `security_concerns` → `security_score` /
>   `avg_security_score` unchanged (F5-independent).
> - **Docs:** `aoi_security_algorithms.md` + `changelog.md` updated.
>
> **Still PLANNED:** F10 (remaining docs — `aoi_implementation.md` parser-path
> drift), and the acceptance-gated F5 (score redesign) and F7 (analysis history /
> schema).
>
> ---
>
> **STATUS (2026-07-16, Batch 2):** **Batch 2 (F3) is IMPLEMENTED, lint-clean,
> and regression-verified** — `1296 passed, 27 skipped` (full `tests/` suite,
> zero regressions); `503 passed` across the AoI + dispatch-affected suites. What
> landed:
> - **F3** — the two divergent AoI parsers were consolidated onto the **flat**
>   production parser. `cli/parsers/aoi.py` now exposes canonical
>   `_add_aoi_arguments(parser)` + `apply_aoi_subcommand(args)`; `register()`,
>   `cli/dispatch.py`, and `modes/aoi.py:main()` all build/resolve through them.
>   The ~70-line nested `_arg_parser()` in `modes/aoi.py` was **deleted** (and the
>   orphaned `_DEF_WAIT` constant removed). A latent export crash
>   (`os.makedirs(args.output)` with `--output` defaulting to `None`) was fixed in
>   the one canonical place (`output_dir = args.output or "."`).
>   `TestArgParser` was repointed to validate the canonical (production) parser
>   path; the `main()`-driven db/scan suites pass unchanged.
>   **Deviation from plan:** the plan's *preferred* "delete the flat parser / route
>   through nested `_arg_parser()`" was rejected as **detrimental** — it would break
>   documented integrated-CLI behaviour (`bleep aoi targets.json` implicit scan,
>   `aoi --file …`). Consolidating onto the flat parser reaches the same
>   single-source-of-truth goal with zero behaviour change.
>
> **Still PLANNED (not started):** F8/F9 (additive enrichment), F10 (remaining
> docs), and the acceptance-gated F5 (score redesign) and F7 (analysis history /
> schema).
>
> ---
>
> **STATUS (2026-07-16, updated):** **Batch 1 (F1, F2, F4, F6) is IMPLEMENTED,
> lint-clean, and regression-verified** — `510 passed` across
> `tests/test_aoi_augmentation.py`, `test_data_pipeline_fixes.py`,
> `test_observations_aoi.py`, `test_aoi_mode_db_commands.py`,
> `test_aoi_database_integration.py`, `test_api_surface.py`. What landed:
> - **F1** — `AOIAnalyser._normalize_security_map()` (dual-shape: flattens the
>   live nested `{obj_type:{issue_type:[uuid]}}` map, passes flat `{uuid:status}`
>   through unchanged); `_analyse_landmine_map`/`_analyse_permission_map` call it.
>   The four `accessibility` keys and the float `accessibility_score` are preserved.
> - **F2** — `bleep/cli/parsers/aoi.py` now sets `--timeout` `default=30` and
>   `--format` `default="markdown"` (no more `None` reaching SDP/pairing; fixes the
>   `.txt` mislabel).
> - **F4** — `analyse_device`/`analyze_device_data` gained `persist: bool = True`;
>   `generate_report` and `generate_aggregate_report` call with `persist=False`, so
>   rendering a report no longer mutates the DB.
> - **F6** — pairing in `_scan_target` is now gated **strictly** behind `--deep`;
>   the annotation-triggered path and the now-dead `_has_auth_annotation()` were
>   removed. Documented the side effect in `aoi_mode.md`.
>
> **Test housekeeping done alongside Batch 1 (pre-existing drift, confirmed failing
> on a clean tree):** the stale `_normalise_service_element` tests (function was
> removed by the A–E work below) were deleted, and the schema-version assertion was
> corrected from `15` → `16` to match `_SCHEMA_VERSION` (the test pre-dated the
> v15→v16 bump). New regression tests added: `TestSecurityMapNormalization` +
> `TestReportGenerationReadOnly` (data-pipeline suite) and
> `TestProductionParserDefaults` + `TestPairingGatedByDeep` (augmentation suite).
>
> **Still PLANNED (not started) [superseded — F3 landed in Batch 2, F8/F9 in
> Batch 3 above]:** F10 (remaining docs), and the acceptance-gated F5 (score
> redesign) and F7 (analysis history / schema).
>
> ---
>
> **Original STATUS (2026-07-16):** This entry is the deliverable of an *exhaustive read-only
> review* of BLEEP's Assets-of-Interest (AoI), analysis, and reporting stack, plus a
> follow-up *safety re-examination* that verified assumptions against real on-disk AoI
> dumps (`~/.bleep/aoi/*.json`) and the full `tests/` suite. **No code has been
> modified.** Every finding below carries a citation and a blast-radius/test-constraint
> analysis so the work can be brought into the main dev environment (which has `tests/`)
> for one final review before any change lands.
>
> **The A–F data-pipeline items in the section immediately below (2026-07-15) are already
> implemented; F1–F10 here are NEW and DISJOINT from A–F.** Do not conflate them.
>
> **Hard gates discovered during safety review (read before touching anything):**
> - **F5 (scoring) and F7 (analysis history) are NOT no-ops** — each breaks pinned tests
>   and/or requires a schema migration. They must be their own explicitly-accepted work
>   items, never bundled into a "safe" batch.
> - **F1 must be a *dual-shape* normalizer** (accept BOTH flat and nested maps) or it
>   regresses `tests/test_data_pipeline_fixes.py::test_hydrated_security_maps_flow_to_analysis`.
> - All others (F2, F4, F6, F8, F9, F10) are additive/isolated and provably non-regressive
>   under the current suite; **F3** is safe only behind a full-suite validation run.

### Provenance / how findings were gathered

Read-only inspection of: `bleep/modes/aoi.py`, `bleep/analysis/aoi_analyser.py`,
`bleep/analysis/sdp_analyzer.py`, `bleep/analysis/device_type_classifier.py`,
`bleep/core/observations/_aoi.py`, `bleep/cli/parsers/aoi.py`, `bleep/cli/dispatch.py`,
`bleep/ble_ops/le/enum_controller.py`, `bleep/ble_ops/le/connect.py`,
`bleep/ble_ops/le/scan.py`, `bleep/dbuslayer/device_le.py`; the AoI test suite
(`tests/test_aoi_augmentation.py`, `test_observations_aoi.py`, `test_aoi_mode_db_commands.py`,
`test_aoi_database_integration.py`, `test_data_pipeline_fixes.py`, `test_api_surface.py`);
docs (`aoi_mode.md`, `aoi_implementation.md`, `aoi_security_algorithms.md`); and the live
AoI dumps under `~/.bleep/aoi/` (empirical map-shape evidence).

### Severity & safety summary

> **All rows below are now ✅ IMPLEMENTED** (see the FINAL status block above). The
> "Fix safety verdict" / "Blocking constraint" columns record the *pre-implementation*
> assessment and are retained for historical context; the "Status" column reflects
> the current shipped state.

| ID | Finding (one-line) | Severity | Fix safety verdict | Blocking constraint | Status |
|----|--------------------|----------|--------------------|---------------------|--------|
| **F1** | Landmine/permission-map analysis misreads live *nested* maps (flat-map contract only) | HIGH | ✅ Safe **iff dual-shape** | Keep flat-map path + `accessibility_score` key | ✅ Done (Batch 1) |
| **F2** | Production CLI parser lacks `--timeout`/`--format` defaults → `timeout=None` to SDP/pair | HIGH | ✅ Safe | None (isolated to `modes/aoi.py`) | ✅ Done (Batch 1) |
| **F3** | Two divergent AoI arg parsers; tests validate the non-production one | MED/HIGH | ⚠️ Safe **behind full-suite run** | Preserve `TestArgParser` namespace | ✅ Done (Batch 2) |
| **F4** | `report` re-runs analysis and persists to DB (not read-only) | MED | ✅ Safe | None (report tests use `use_db=False`) | ✅ Done (Batch 1) |
| **F5** | Risk score baseline=5, only increases, `int()` truncation hides low/med | MED | ❌ **Not a no-op** | Breaks 7 pinned score assertions + doc | ✅ Done (Batch 5, option a: baseline 0, weights 3/2/1) |
| **F6** | A "scan" can create a real pairing bond (even without `--deep`) | MED | ✅ Safe | None | ✅ Done (Batch 1) |
| **F7** | Only one `aoi_analysis` row per device (no history) | LOW/MED | ❌ **Schema-breaking** | Bumps `_SCHEMA_VERSION` (pinned=16) + migration | ✅ Done (Batch 4, option a: `aoi_analysis_history`, schema v17) |
| **F8** | Notable-service / unusual-char heuristics shallow & SIG-name-dependent | LOW | ✅ Safe (additive) | Don't co-mingle with F5 (score inflation) | ✅ Done (Batch 3) |
| **F9** | Comprehensive `SDPAnalyzer` unused by AoI report SDP section | LOW | ✅ Safe (additive) | Don't co-mingle with F5 | ✅ Done (Batch 3) |
| **F10** | Docs drift (CLI path, landmine/pairing behaviour) | LOW | ✅ Safe (text only) | Land after code fixes | ✅ Done (Batch 4) |

---

### F1 — HIGH — Landmine/permission-map analysis operates on the wrong live data shape — ✅ IMPLEMENTED (Batch 1, 2026-07-16)

**Finding (as-found, with citation).** The analyzer treats the maps as a flat
`{uuid: status}` dict:

```python
# bleep/analysis/aoi_analyser.py:962-967
for uuid, status in landmine_map.items():
    result[uuid] = {"status": status, "is_critical": self._is_critical_uuid(uuid)}
```

But live enumeration emits a **nested** `{obj_type: {issue_type: [uuid, …]}}` structure
(plus an `in_review` bucket):

- `bleep/dbuslayer/device_le.py:1103-1104` — maps initialised as `{"in_review": {"uncategorized": []}}`.
- `bleep/dbuslayer/device_le.py:1582-1585` — `mine_mapping[obj_type].setdefault(issue_type, []).append(uuid)`.
- `bleep/dbuslayer/device_le.py:1447-1461` (`device_map__clean_map`) — returns `{}` when empty, else preserves nesting.
- `bleep/modes/aoi.py:396-397` — AoI stores `le_result.landmine_map`/`permission_map` verbatim.
- `bleep/analysis/aoi_analyser.py:597-598, 707-711` — consumes them; DB path hydrates from `security_maps` JSON at `bleep/analysis/aoi_analyser.py:159-173`.

**Empirical proof.** Real dumps `~/.bleep/aoi/71EFADC9C73B_20260716_091952.json` show
`landmine_map`/`permission_map` as `{}` (that device produced **no** read errors, so
`clean_map` reduced the nested seed to empty). The nested shape only materialises when a
device returns GATT read errors — which is exactly the case the analyzer misreads.

**Impact.** When populated, `for uuid, status in map.items()` iterates *object-type*
keys (`"characteristic"`, `"in_review"`), so `_is_critical_uuid("characteristic")`
(`aoi_analyser.py:987-1002`) is meaningless; `_generate_accessibility_summary`
(`aoi_analyser.py:1004-1025`) compares a nested dict to `"OK"` (never equal) and divides
over 2–3 buckets → nonsense `accessibility_score`; recommendations keyed on that score
(`aoi_analyser.py:1093-1104`) misfire. Contradicts `aoi_mode.md:221-229`.

**Why this survived.** The analyzer's flat-map path is an *intended, tested* contract for
synthetic/DB-hydrated input — it was never exercised with live nested maps.

**Proposed work (dual-shape, additive).** Add a private normaliser, e.g.
`_normalize_security_map(raw) -> Dict[str, Dict]`, that:
1. Detects nested shape (values are dicts, or top-level keys are object types /
   `in_review`) and flattens to `{uuid: {"status": issue_type, "obj_type": …}}`.
2. Passes an already-flat `{uuid: status}` dict through unchanged (legacy/test contract).
   Call it at the head of `_analyse_landmine_map`/`_analyse_permission_map`, and feed the
   flattened per-UUID maps into `_generate_accessibility_summary`.

**Blast radius (verified).**
- `report["details"]["landmine_map"]/["permission_map"]`: consumed only by
  `store_aoi_analysis` (stored verbatim in `analysis_details`) and round-tripped by
  `get_aoi_analysis`. **No report renderer reads it** (`_generate_markdown_report`/`_text`/`_json`
  never reference `details.landmine_map`).
- `report["summary"]["accessibility"]`: read by `_generate_recommendations`
  (`aoi_analyser.py:1093`) and `bleep/modes/debug_aoi.py:105-110` (`acc['accessibility_score']`
  formatted `.2%`). **Condition: the fix MUST keep the four keys**
  (`total_characteristics`, `blocked_characteristics`, `protected_characteristics`,
  `accessibility_score`) and keep `accessibility_score` a float.

**Test constraints (must stay green).**
- `tests/test_data_pipeline_fixes.py:621-630` (`test_hydrated_security_maps_flow_to_analysis`)
  feeds a **flat** `{uuid: "safe"}` map and asserts `len(report["details"]["landmine_map"]) > 0`
  → the dual-shape normaliser **must preserve flat handling**.
- `tests/test_data_pipeline_fixes.py:795-821` (`test_details_round_trip`) stores flat maps
  **directly via the DB layer** (bypasses the analyzer) → unaffected by an analyzer change.
- `tests/test_aoi_database_integration.py:455-456` mocks `_analyse_landmine_map`/
  `_analyse_permission_map` → immune.
- No test asserts a specific `accessibility_score` value (grep of `tests/` = 0 numeric
  assertions), so re-basing the score is free as long as the key exists.

**Verdict: SAFE, conditional on dual-shape handling + preserved `accessibility` keys.**
**New regression test required:** feed a realistic nested map
(`{"characteristic": {"write_not_permitted": ["<uuid>"]}, "in_review": {"uncategorized": []}}`)
and assert per-UUID flattening + sane accessibility counts.

---

### F2 — HIGH — Production CLI parser omits defaults; `--timeout` reaches SDP/pairing as `None` — ✅ IMPLEMENTED (Batch 1, 2026-07-16)

**Finding (with citation).** `bleep/cli/parsers/aoi.py:15-16` declares `--timeout` and
`--format` with **no default** (→ `None`). The mode's `timeout = getattr(args, "timeout", 30)`
(`bleep/modes/aoi.py:489`) does **not** apply `30` because the attribute *exists* as `None`.
`None` then flows to:
- `bleep/modes/aoi.py:553` `_discover_sdp(..., timeout=args.timeout)` and `:556`
  `_probe_pairing(mac_up, timeout=args.timeout)`;
- `discover_services_sdp(..., timeout: int = 30)` (`bleep/ble_ops/classic/sdp.py:880`) —
  the function default is bypassed because `None` is passed explicitly;
- subprocess/pair timeouts of `None` = "wait forever" → hang risk.
Aggregate-report filename also mislabels markdown as `.txt` when `--format` is `None`
(`bleep/modes/aoi.py:617-619`).

**Contrast.** The standalone `_arg_parser()` correctly defaults `--timeout` to `30`
(`bleep/modes/aoi.py:274, 291`) and `--format` to `"markdown"` (`:309`).

**Proposed work.** In `bleep/cli/parsers/aoi.py`: set `--timeout` `type=int, default=30`
and `--format` `default="markdown"`. (Alternative/defence-in-depth: coerce `None` in
`_run_impl`.)

**Blast radius (verified).** Sole consumers of `args.timeout`/`args.format` are in
`bleep/modes/aoi.py:489, 553, 556, 606-635` (grep confirmed no others). `--timeout` is
defined only on the `aoi` subparser; other modes declare their own `--timeout` on their own
subparsers → **no cross-subparser collision**. `--format` None→"markdown" yields identical
rendering (the `else` branch already meant markdown) and *fixes* the `.txt` mislabel.

**Test constraints.** `tests/test_api_surface.py` has **no** aoi-parser default assertions.
The only parser-default test, `TestArgParser` (`tests/test_aoi_augmentation.py:119-126`),
targets the standalone `_arg_parser()` which **already** defaults `timeout==30` → aligning
the production parser is consistent, not conflicting. No test pins `args.timeout is None`.

**Verdict: SAFE.** Recommend adding a test that drives the real dispatch path
(`cli/parsers/aoi.py` → `cli/dispatch.py`) and asserts `timeout==30`.

---

### F3 — MED/HIGH — Two divergent AoI argument parsers; the suite validates the non-production one — ✅ IMPLEMENTED (Batch 2, 2026-07-16)

> **RESOLVED (Batch 2).** Consolidated onto the flat production parser via
> canonical `cli/parsers/aoi.py:_add_aoi_arguments()` + `apply_aoi_subcommand()`,
> shared by `register()`, `cli/dispatch.py`, and `modes/aoi.py:main()`; the nested
> `_arg_parser()` was deleted and `TestArgParser` repointed to the canonical path.
> The plan's "delete the flat parser" preference was rejected because it breaks
> documented implicit-scan / `--file` behaviour — see the Batch 2 STATUS block at
> the top of this section and `changelog.md`.

**Finding (with citation).** Production uses the flat parser `bleep/cli/parsers/aoi.py`
plus manual subcommand extraction in `bleep/cli/dispatch.py:188-200`. A *separate*
subparser-based parser `_arg_parser()` (`bleep/modes/aoi.py:262-331`) is used only by the
standalone `main()` (`:816-820`) and by `TestArgParser` (`tests/test_aoi_augmentation.py:115-154`).
This is why F2 was masked: the tests assert `timeout==30` against a parser production never
runs. Duplicate maintenance with visible drift (defaults differ).

**Proposed work.** Consolidate to one source of truth. Preferred: route the real CLI
through the subparser-based `_arg_parser()` (better UX + correct defaults) and delete the
flat parser; else delete `_arg_parser()` and add dispatch-path tests. Bundle with F2.

**Blast radius (verified).** `_arg_parser` is imported nowhere in production
(`dispatch.py` imports only `run`). Consolidation edits `dispatch.py:185-200` and reshapes
the `args` namespace.

**Test constraints.** Must preserve `TestArgParser`'s expected attributes (`command`,
`timeout==30`, `db`→`action`, `deep`, `no_db`, `connectionless`, address filter). The
subparser-based `_arg_parser()` already satisfies them, so reuse is low-risk.

**Verdict: SAFE only behind a full `test_aoi_*` + `test_api_surface` run**, because it
changes CLI arg construction. Do not land without the suite green.

---

### F4 — MED — `report` generation mutates persistent state (not read-only) — ✅ IMPLEMENTED (Batch 1, 2026-07-16)

**Finding (with citation).** `generate_report` analyses when analysis is absent
(`bleep/analysis/aoi_analyser.py:1147-1149`); `analyse_device` then writes to the DB
(`:793-818`) and mutates `self.reports`. The CLI `report` path builds the analyser with
`use_db=True` by default (`bleep/modes/aoi.py:476, 632`), so *rendering* a report re-runs
and re-persists analysis (fresh timestamp → overwrites the stored row; see F7). The
`analyze` subcommand already persists via its own explicit `save_device_data`
(`bleep/modes/aoi.py:559-562`), so report-time persistence is redundant + surprising.

**Proposed work.** Add a read-only rendering path (e.g. `persist=False` on
`analyze_device_data`/`analyse_device`, or skip the DB write when invoked from `report`).

**Blast radius / test constraints (verified).** `generate_report` callers: only
`bleep/modes/aoi.py:632` and tests. **Every** report test constructs the analyser with
`use_db=False` (`tests/test_aoi_augmentation.py:433`, `tests/test_data_pipeline_fixes.py:1525,1540`),
so no test exercises or asserts DB persistence during report generation.

**Verdict: SAFE** (behaviour change: `report` on an un-analysed device will no longer
silently persist — desirable and unobserved by tests).

---

### F5 — MED — Risk-score design misrepresents clean devices — ✅ IMPLEMENTED (Batch 5, 2026-07-16, option (a))

> **RESOLVED (Batch 5, option (a) — user-approved scale).** `_calculate_security_score`
> now starts at **0** (clean device = 0/10) and uses exact integer severity
> weights: `score = min(10, high×3 + medium×2 + low×1)`. This removes the
> baseline-5 + fractional-weight + `int()`-truncation model (old effective range
> 5–10). "Higher = more risk" render labels are unchanged and now accurate.
> Pinned `TestCalculateSecurityScore` assertions rewritten for the new scale
> (`tests/test_data_pipeline_fixes.py`) + a medium/low-weight test added;
> `avg_security_score` stays a float. Doc rewritten in
> `aoi_security_algorithms.md` (Security Score section). See the `changelog.md`
> Batch 5 entry. No schema change; F8 informational lists still don't feed the score.

**Finding (with citation).** `_calculate_security_score` (`bleep/analysis/aoi_analyser.py:1171-1187`)
starts at `5`, only ever adds, caps at `10`, and `int()`-truncates: a fully clean device
reports **5/10 "risk"** (rendered "higher = more risk", `:1217`); one low (+0.25) or medium
(+0.75) concern still floors to `5`. Effective range 5–10. Item **D** in the 2026-07-15
section (below) only *relabelled* the metric and deliberately left computation unchanged.

**Hard gate — pinned tests will break.** Exact-value assertions:
`tests/test_data_pipeline_fixes.py:149-192` (`==5` empty, `==6` one-high, `==8` stack,
`==6` two-medium, `==10` cap) and `tests/test_aoi_augmentation.py:702`
(`avg_security_score` is float). Any change to baseline/weights/truncation fails these and
invalidates `aoi_security_algorithms.md` (Security Score Calculation section).

**Proposed work (gated).** Redesign (e.g. start at 0, or band by highest-severity concern),
**and in the same change** rewrite the pinned assertions and the algorithm doc. Requires
explicit product decision on the new scale/semantics.

**Verdict: ❌ NOT non-detrimental as a code-only change.** Treat as a separate,
acceptance-gated task. Do NOT include in any "safe" batch.

---

### F6 — MED — A "scan" can silently create a real pairing bond — ✅ IMPLEMENTED (Batch 1, 2026-07-16)

**Finding (with citation).** `_scan_target` sets `needs_pair = deep`, then **also** pairs
when an auth annotation is present *even without `--deep`*
(`bleep/modes/aoi.py:421-427`). `_probe_pairing` performs a real `dev.pair()`
(`bleep/modes/aoi.py:161-173`), mutating adapter/device bonding state during what a user
may expect to be non-invasive enumeration. `aoi_mode.md` never warns of this.

**Proposed work.** Gate all pairing strictly behind `--deep` (remove the
annotation-triggered path, or make it opt-in); document the side effect; optionally remove
the bond after probing or make it a non-bonding "pairability" check.

**Blast radius / test constraints (verified).** `_probe_pairing` is tested only in
isolation (`tests/test_aoi_augmentation.py:192-217`), **not** via the `needs_pair` trigger.
The only `_scan_target` test (`tests/test_aoi_augmentation.py:914-937`) uses a Classic
device where the LE path is skipped, `le_result` stays `None`, `needs_pair` stays `False`,
and no pairing is asserted.

**Verdict: SAFE** (removes a genuine, undocumented side effect).

---

### F7 — LOW/MED — Only one `aoi_analysis` row per device — ✅ IMPLEMENTED (Batch 4, 2026-07-16, option (a))

> **RESOLVED (Batch 4, option (a) — user-approved schema migration).** Added an
> append-only `aoi_analysis_history` table (schema **v16→v17**, `_connection.py`).
> `store_aoi_analysis()` still upserts the latest-only `aoi_analysis` row
> (**unchanged** semantics — `get_aoi_analysis`/`has_aoi_analysis` and
> `test_store_aoi_analysis_update` untouched) and now also appends a timestamped
> history row. New API `get_aoi_analysis_history(mac, limit=None)` (newest-first,
> exported from `bleep.core.observations`). The v16→v17 migration creates the
> table (`IF NOT EXISTS`) and backfills the existing latest row as the first
> history entry (non-destructive). `_SCHEMA_VERSION` assertion updated 16→17; 5
> new regression tests added. See the `changelog.md` Batch 4 entry and
> `observation_db_schema.md` v17 row / `aoi_analysis_history` section.

**Finding (with citation).** `store_aoi_analysis` uses `ON CONFLICT(mac) DO UPDATE`
(`bleep/core/observations/_aoi.py:48-78`), so each analysis overwrites the previous — no
history, at odds with `aoi_mode.md:239` ("re-scan periodically to track changes").

**Hard gate — schema + tests.** Schema version is asserted exactly:
`tests/test_aoi_augmentation.py:301-302` (`_SCHEMA_VERSION == 16`); overwrite semantics are
asserted by `tests/test_observations_aoi.py:224-253` (`test_store_aoi_analysis_update`
expects the retrieved row to reflect the update). A history redesign needs a version bump
+ migration, must keep `get_aoi_analysis` returning the *latest* (to keep the update test
green), and must update the schema-version assertion.

**Proposed work (gated).** Either (a) add a timestamped history table + a "latest" view, or
(b) explicitly document that only the latest analysis is retained (docs-only, no schema
change). Recommend deciding (a) vs (b) before any work.

**Verdict: ❌ NOT non-detrimental as-is.** Separate, migration-gated task (option a) or a
docs-only clarification (option b).

---

### F8 — LOW — Notable-service / unusual-characteristic heuristics are shallow — ✅ IMPLEMENTED (Batch 3, 2026-07-16)

> **RESOLVED (Batch 3).** Added curated vendor OTA/DFU UUID set
> (`_OTA_DFU_SERVICE_UUIDS`) + `_canonical_uuid()` in `analysis/aoi_analyser.py`;
> `_analyse_service` now flags vendor firmware-update services with custom UUIDs.
> Unusual heuristics refined (case-insensitive writable+notify/indicate; hex-like
> value > 40 chars). Informational lists only — no `security_concerns` added, so
> the score is unchanged (F5-independent). See the Batch 3 STATUS block and
> `changelog.md`.

**Finding (with citation).** `_analyse_service` (`bleep/analysis/aoi_analyser.py:843-851`)
recognises GAP/GATT by hardcoded UUID and OTA/DFU/auth by name substring only — vendor
OTA/DFU services with custom UUIDs and no SIG name are missed. `_analyse_characteristic`
unusual rule (`:916-923`) uses arbitrary thresholds (`len(properties) > 3`, `len(value) > 20`).

**Proposed work (additive).** Broaden notable-service detection with a known vendor
OTA/DFU UUID set (reuse existing UUID reference data in `bleep/bt_ref/`); refine the
unusual thresholds.

**Blast radius / caution.** These add concerns, which feed `_calculate_security_score`.
**Do not combine with F5.** Any new high-signal rule should set risk explicitly rather than
relying on `_assign_concern_risk`'s `source == "characteristic" → high` auto-escalation
(`bleep/analysis/aoi_analyser.py:76-77`) to avoid score inflation. No test pins live-scan
concern counts, so additive rules are otherwise safe.

**Verdict: SAFE (additive), F5-independent.**

---

### F9 — LOW — Comprehensive `SDPAnalyzer` is barely used by AoI — ✅ IMPLEMENTED (Batch 3, 2026-07-16)

> **RESOLVED (Batch 3).** `_analyse_sdp_records` routes records through
> `SDPAnalyzer.analyze()` and surfaces `protocols`/`rfcomm_channels`/`anomalies`/
> `inferred_spec_version`, preserving `raw_count`/`services_found`/`security_flags`
> (guarded fallback on error). Rendered in the markdown/text SDP sections; no new
> scored concerns. See the Batch 3 STATUS block and `changelog.md`.

**Finding (with citation).** AoI summarises SDP with a shallow substring scan
(`bleep/analysis/aoi_analyser.py:1027-1045`), while the richer `SDPAnalyzer`
(protocol/profile/version/anomaly analysis, `bleep/analysis/sdp_analyzer.py`) is invoked
only for LMP cross-validation (`bleep/analysis/aoi_analyser.py:768-783`), not to enrich the
report SDP section.

**Proposed work (additive).** Route AoI SDP summarisation through `SDPAnalyzer.analyze()`
and surface its protocols/anomalies in the report SDP section, preserving the existing
`security_flags` output for backward compatibility.

**Verdict: SAFE (additive), F5-independent.** New tests should assert the enriched SDP
section renders without altering existing `security_flags` assertions.

---

### F10 — LOW — Documentation drift — ✅ IMPLEMENTED (Batch 4, 2026-07-16)

> **RESOLVED (Batch 4, docs-only).** `aoi_implementation.md` parser path corrected
> to `bleep/cli/parsers/aoi.py` + `bleep/cli/dispatch.py` (F3 consolidation), with
> the read-only `report` path and `db` subcommand documented and the DB-integration
> section updated for the F7 history API. `aoi_mode.md` Service/Characteristic/SDP
> feature descriptions refreshed for Batch 3 (F8/F9). The F6 pairing side-effect
> note and F1 functional landmine/permission analysis were already reflected in
> earlier batches. See the `changelog.md` Batch 4 entry.

**Finding (with citation).** `aoi_implementation.md:9` claims the CLI parser lives in
`bleep/cli.py`; actual is `bleep/cli/parsers/aoi.py` + `bleep/cli/dispatch.py`.
`aoi_mode.md:221-229` presents landmine/permission analysis as functional (see F1) and
omits the pairing side effect (F6).

**Proposed work.** Update docs **after** the F1/F6 code fixes land (text-only). **Verdict: SAFE.**

---

### Recommended batching (for the main dev environment) — ✅ ALL BATCHES COMPLETE

1. **Batch 1 — provably non-regressive:** F2 + F4 + F6, and F1 *as a dual-shape normalizer*.
   Each is isolated/additive and cannot regress the current suite. Add the new F1 nested-map
   regression test and the F2 dispatch-path test. — ✅ **Done.**
2. **Batch 2 — behind a full-suite run:** F3 (parser consolidation, bundle with F2). — ✅ **Done.**
3. **Batch 3 — additive enrichment (F5-independent):** F8, F9. — ✅ **Done.**
4. **Batch 4 — docs + gated schema:** F10 (docs) and F7 (history table, schema v17, option a). — ✅ **Done.**
5. **Batch 5 — gated score redesign:** F5 (baseline-0 integer weights, option a) with the
   pinned tests + `aoi_security_algorithms.md` rewritten in the same change. — ✅ **Done.**

### Pre-implementation checklist (run in the env that has `tests/`) — ✅ COMPLETE

- [x] Baseline the suite: `python -m pytest tests/test_aoi_augmentation.py tests/test_observations_aoi.py tests/test_aoi_mode_db_commands.py tests/test_aoi_database_integration.py tests/test_data_pipeline_fixes.py tests/test_api_surface.py -q` and record the pre-existing (hardware/BlueZ-dependent) failures so regressions are distinguishable.
- [x] F1: confirm the nested map shape on a device that returns GATT read errors (populated `ble_device__mine_mapping`), and confirm the dual-shape normalizer keeps `test_hydrated_security_maps_flow_to_analysis` green.
- [x] F2/F3: confirm no other mode's subparser collides on `--timeout`/`--format`; add dispatch-path default test.
- [x] F4: confirm no automation depends on `report` persisting analysis (grep callers of `generate_report`).
- [x] F5/F7: obtained explicit sign-off on new score semantics (F5 option a) / history decision (F7 option a) before writing code; pinned tests + `aoi_security_algorithms.md` / schema-version assertion updated in the same change.
- [x] Re-run the full suite after each batch; each item is independently revertable. Final: **1311 passed, 27 skipped, 0 failed.**

---

## Survey arg dedup + AoI data-pipeline hardening (2026-07-15) — ACCEPTED · #3 + A–F COMPLETE · follow-on PLANNED

> **STATUS (2026-07-16):** Task **#3** and AoI items **A–E** are **IMPLEMENTED,
> lint-clean, and regression-verified**. Item **F** is **IMPLEMENTED,
> regression-tested, and LIVE-VERIFIED on real hardware (2026-07-16)**. The
> newly-scoped follow-on (LE↔Classic discovery-transition hardening) remains
> **PLANNED — documentation only; no implementation until explicitly accepted.**
> Findings were gathered from an end-to-end survey→AoI→SDP dry-run plus a code
> review of `bleep/modes/aoi.py` and `bleep/analysis/aoi_analyser.py`. Prior
> schema-drift / test-isolation fixes (#1/#2) already landed. Each item is
> additive and independently revertable.
>
> **Test evidence for #3 + A–E:** 295 passed across `tests/test_data_pipeline_fixes.py`,
> `test_aoi_augmentation.py`, `test_survey.py`, `test_aoi_mode_db_commands.py`,
> `test_observations_aoi.py`, `test_aoi_database_integration.py`. The 9 remaining
> full-suite failures are **pre-existing**, hardware/BlueZ-adapter dependent
> (`org.bluez` not provided in the sandbox), and **unrelated** — confirmed
> identical against a clean checkout.

### #3 — Deduplicate survey argument definitions — ✅ DONE (2026-07-15)

**Was:** the survey CLI flag set was declared verbatim in three places (which had
already drifted — the debug parser lacked `--quiet`): `cli/parsers/survey.py`
`register`, `modes/survey.py` `_build_parser`, `modes/debug_survey.py`
`cmd_survey`.

**Resolution:** single canonical `_add_survey_arguments(parser)` in
`bleep/cli/parsers/survey.py`; all three call sites now invoke it (lazy import in
`modes/` keeps it cycle-free). Removed the dead `from math import ceil` in
`debug_survey.py`. Net effect: identical attribute set across all three parsers
(verified at runtime: standalone == debug, and the CLI subparser is a superset);
the debug shell **gained the previously-missing `--quiet`**. Existing flag
behaviour unchanged.

### AoI data-pipeline hardening — A–E ✅ DONE (2026-07-15)

| ID | Finding (as-found, with citation) | Resolution (implemented) |
|----|-----------------------------------|--------------------------|
| **A** | `aoi db import`/`sync` treated `services_mapping` as a **flat `{char_uuid: svc_uuid}`** map, but the real shape is **nested `{svc_uuid: {"chars": {char_uuid: {…}}}}`** → **no characteristics were ever imported** from files into the DB. | Fixed by **E** (single correct write path). Regression test proves chars now persist. |
| **E** | Three separate DB-write implementations (correct one in `save_device_data`; two buggy copies in import/sync). | Extracted `AOIAnalyser._persist_device_to_db(mac, data)` (`aoi_analyser.py`); `save_device_data` **and** `aoi db import`/`sync` now all call it. Removed dead `_normalise_service_element`, folding its string/dict service-element normalisation into the shared method's list branch (preserves the export→sync round-trip for DB-row-dict service lists). |
| **B** | `aoi list` read `device_data.get("name", "Unknown")`, but DB-hydrated records nest the name under `device.name` → DB-sourced devices displayed `Unknown`. | `aoi list` now falls back to `device.name` before `Unknown`. |
| **C** | `_analyse_characteristic` only flagged a concern when the **SIG-derived name** matched `auth/password/key` **and** `write-without-response`; custom-UUID writable attributes were never flagged. | Broadened: resolves an effective name from explicit `name`/`description` fields, and flags **custom (Unknown-UUID) write-without-response, non-authenticated** characteristics as **medium** risk (worded to avoid the high-risk auto-classification, preventing alert flooding). The 3 duplicated concern-append sites are centralised in `_char_concern_from_report()` (honours an explicit risk hint). Numeric score + the existing high-signal rule are unchanged. |
| **D** | The report metric was called **“Security Score”** yet **higher = worse**. | **Relabelled only** to “Risk Score … (higher = more risk)” in the markdown, text, and aggregate renderers. Numeric computation and JSON keys (`security_score`/`avg_security_score`) unchanged — pinned by `tests/test_data_pipeline_fixes.py:146-189` and `tests/test_aoi_augmentation.py:707`. |

**Regression coverage added:** `TestPersistDeviceToDb` in
`tests/test_data_pipeline_fixes.py` — a real (non-mocked, isolated-DB) test
proving `_persist_device_to_db` writes nested `services_mapping` characteristics
to the DB, both directly and through the `aoi db import` command path (closes
**A**). The obsolete `_normalise_service_element` unit tests were removed; one was
repurposed into a `_persist_device_to_db` dict-service-list test.

### F (✅ DONE 2026-07-16 · live-verified) — Seed AoI device-type from survey/DB

**Finding (with citation).** `_scan_target` (`bleep/modes/aoi.py:295`)
unconditionally re-derives the transport with `_classify_device(normalized,
use_db=use_db)` (`:307`), whose classifier is **evidence-based and stateless**
(`observation_db.md:363`: "based only on current device properties … never on
historical database data"). The `aoi scan` loop *does* pre-seed the DB with the
survey-supplied `device_type` (`aoi.py:448-456`), but the stateless classifier
ignores it, so a device that is not currently advertising/queryable comes back
`unknown`. The freshly-derived value then **overwrites** the seeded type in the
stored record (`aoi.py:314`).

**Impact.** Not data loss (an `unknown` device still runs *both* LE-enum and SDP
paths — `aoi.py:318`, `:350`), but: (a) the authoritative survey/DB
classification is discarded and the persisted `device_type` regresses to
`unknown`; (b) both transport paths run even when the transport was already
known, wasting time on hardware.

**Plan (additive, non-destructive).**
1. Thread the survey entry's `device_type` hint into `_scan_target` as an optional
   `seeded_type` parameter (the scan loop already holds `entry["device_type"]` at
   `aoi.py:444-456`; pass it in at the `_scan_target(...)` call `:459-463`).
2. In `_scan_target`: after `_classify_device`, if the live result is `unknown`
   **and** a trustworthy `seeded_type` (`le`/`classic`/`dual`) is available (hint
   arg, else the DB record via `observations.get_device_detail`), adopt the
   seeded type for the stored `device_type` **and** for path selection.
3. Keep the current `unknown` → run-both-paths behaviour as the safety net when
   no seed exists. Never *downgrade* a live-derived concrete type with a seed.
4. Record provenance: note in the device record whether the type was
   live-classified or seed-adopted (aids audit; mirrors existing
   `device_type_evidence` conventions).

**Why deferred / verification required.** This changes the persisted
`device_type` value and path selection, so it must be validated on live devices:
a survey-seeded `classic` device that is idle at AoI time should retain `classic`
(not regress to `unknown`) and should skip the pointless LE-enum attempt.

**Finalized design (accepted 2026-07-16).**
- `_resolve_seeded_type(hint, mac, use_db)` — returns a trustworthy seed
  (`le`/`classic`/`dual`) or `None`: prefers the explicit `hint` (survey JSON),
  else the DB record (`observations.get_device_detail(mac)['device']['device_type']`).
  Never returns `unknown`; case-insensitive.
- `_resolve_device_type(live_type, seeded_type, mac, use_db)` — pure reconciler:
  a concrete live result always wins (`→ (live_type, "live")`); only when live is
  `unknown` is a seed adopted (`→ (seed, "seed")`); otherwise `("unknown", "live")`.
- `_scan_target(..., seeded_type=None)` calls the reconciler after
  `_classify_device`, uses the resolved type for **both** path selection and the
  persisted `device_data["device_type"]`, and records
  `device_data["device_type_source"]` (`"live"`/`"seed"`) for auditability. The
  scan loop passes `seeded_type=entry.get("device_type")`.

**Tests.**
- Unit (mock, CI-safe): `_resolve_seeded_type` (valid hint / invalid hint→DB
  fallback / none); `_resolve_device_type` (live concrete wins & is not upgraded/
  downgraded by a seed; live `unknown`+hint→seed; live `unknown`+DB→seed; live
  `unknown`+none→unknown); and a `_scan_target` path test (patched
  `_classify_device→unknown`, `seeded_type="classic"` → SDP path taken, LE-enum
  skipped, persisted `device_type == classic`, `device_type_source == "seed"`).
- Hardware (`@pytest.mark.hardware`): idle survey-seeded Classic + LE devices.

**Result (implemented + live-verified 2026-07-16).** Landed in `bleep/modes/aoi.py`
(`_resolve_seeded_type`, `_resolve_device_type`, `_scan_target(seeded_type=…)`, scan
loop passes `entry.get("device_type")`). Unit tests: `TestSeededDeviceType` in
`tests/test_aoi_augmentation.py` (helper matrix + a `_scan_target` seed-adoption
path test). **Live proof on real `hci0`:** a 25s survey typed device
`71:EF:AD:C9:C7:3B` as `le`; the subsequent `aoi scan` live-classified it
`unknown` yet **adopted the `le` seed** — console `type=le (live classification
unknown; adopted seeded type)`, saved AoI record `device_type=le`,
`device_type_source=seed`, DB `device_type=le` (no regression to `unknown`), and
the LE-enum path ran while SDP was skipped. Full suite: 196 passed across the
affected AoI/survey suites.

### Step-3 (FIRST DELIVERABLE ✅ DONE + LIVE-VERIFIED on 5.84 & 5.64 2026-07-16 · settle/retry DEFERRED) — Harden the LE↔Classic discovery transition

> **Do NOT implement without explicit sign-off.** A prior guard attempt was
> **reverted** (`bb4cde3` "Stop Discovery guard causing worse issues instead of
> helping"; see `changelog.md`), and the suspected trigger is **BlueZ version
> differences (Kali vs Ubuntu)** (`245c7bc`). This plan is written to avoid
> repeating that mistake: evidence first, additive + reversible, hardware-gated.
>
> **STATUS (2026-07-16):** Phase-1 **evidence has been gathered on BlueZ 5.84**
> (see "Evidence packet" below). Result: **H1/H2 do NOT reproduce on 5.84**; the
> transition is race-free here. The scoped first deliverable is therefore
> **re-oriented to a diagnosability upgrade** (surface/log the currently-swallowed
> discovery errors) rather than the settle-guard, which was the reverted change
> and is a no-op on the only version testable here. **A second-OS reproduction is
> required** to characterise the version where the race *did* occur — a portable,
> copy-pasteable procedure is included below so the identical tests can be run
> against the **same devices** from a **different OS/BlueZ build**.
>
> **UPDATE (2026-07-16):** The second baseline **has now been captured on BlueZ
> 5.64** (see "Evidence packet — OS/BlueZ #2" below), including a **cross-client
> contention extension** with a real pure-Classic target. Result: the race does
> **not** reproduce on 5.64 either, but contention keeps the global `Discovering`
> property pinned `true` — which **mechanistically explains the reverted guard's
> regression** (`bb4cde3`). H3 is refined: the decisive variable is **cross-client
> discovery contention**, not the BlueZ version alone.
>
> **CLOSE-OUT (2026-07-16):** The **first deliverable (discovery-error surfacing)
> is IMPLEMENTED and live-verified on both builds** — gate (5) is CLOSED on 5.84
> **and** 5.64 (12/12 method matrix + clean survey + on-disk proof; see both "Live
> re-verification packet" entries). Internal docs updated (`survey_mode.md` →
> "Discovery Error Surfacing"). The **settle/retry second deliverable remains
> DEFERRED** and correctly gated: neither available build reproduces the race even
> under cross-client contention, so any own-session settle logic must wait for a
> build that actually reproduces it (the global-`Discovering` guard `bb4cde3` is
> **not** reinstated).

**Problem.** Survey alternates an **LE round** and a **BR/EDR round** every cycle
(`modes/survey.py` `_survey_worker`; `_run_le_round:489` → `passive_scan`
Transport `le`; `_run_classic_round:498` → `set_discovery_filter({"Transport":
"bredr"})` + `run_scan__timed:521`). Switching transports requires discovery to
be **fully stopped** before `SetDiscoveryFilter`/`StartDiscovery`, but the
current code:
- **Swallows `StartDiscovery` failures** in `run_scan__timed`
  (`adapter.py:83-86`: logs at debug, returns `False`) and **`StopDiscovery`
  failures** in `_discovery_timeout` (`adapter.py:95-100`).
- The LE manager likewise **degrades `StartDiscovery` `InProgress`/`WrongState`
  to a silent no-op** (`manager.py:129-157`) and **swallows all `StopDiscovery`
  `DBusException`** (`manager.py:164-177`).

**Root-cause hypotheses (to be confirmed by evidence before any code).**
- **H1 — stop not settled:** BlueZ `StopDiscovery` returns before `Discovering`
  actually goes `false`; the next round's `StartDiscovery` then hits
  `org.bluez.Error.InProgress` (swallowed) → that round silently scans on the
  **previous** transport filter (or not at all), losing devices for the intended
  transport.
- **H2 — filter-while-discovering:** `SetDiscoveryFilter` is rejected/ignored
  while `Discovering=true` → the bredr round runs with a stale `le` filter (or
  vice-versa).
- **H3 — version-specific timing:** the window differs across BlueZ releases
  (Kali vs Ubuntu), which is why the naive guard helped one and hurt the other.

**Evidence to gather first (no code changes; captured for the acceptance packet).**
1. Instrument a survey run on each target BlueZ version: log `get_discovering()`
   (`adapter.py:466`) immediately before/after each `StartDiscovery`/
   `StopDiscovery`/`SetDiscoveryFilter`, plus the exact D-Bus error names, across
   ≥10 LE↔Classic transitions.
2. Cross-check the transition against BlueZ `StartDiscovery`/`StopDiscovery`/
   `SetDiscoveryFilter` semantics (`doc/adapter-api.txt`) and any known async-stop
   behaviour, to ground the fix in BlueZ source rather than guesswork.
3. Quantify device-loss: compare per-round device counts to a single-transport
   baseline.

---

#### Evidence packet — OS/BlueZ #1 (captured 2026-07-16)

**Environment.** `bluetoothd` **5.84**; adapter `hci0` (Powered, roles
`central`+`peripheral`); live devices present (5 LE + 1 dual visible; **no
discoverable pure-Classic device** — see limitation). No BlueZ source tree vendored
locally, so the source cross-check is against upstream `doc/adapter-api.txt`.
**No source or docs were changed to gather this** — instrumentation was runtime
monkeypatching only (scripts reproduced verbatim below).

**Key structural fact.** `system_dbus__bluez_adapter._initialize_dbus` uses the
process-shared `dbus.SystemBus()` (`adapter.py:49`), so the LE manager and the
Classic adapter are the **same D-Bus sender**. BlueZ tracks discovery per-sender,
so within one survey process there is no cross-client stop/filter conflict — a
material reason the transition is clean on this build.

**F1 — H1 (stop not settled): NOT reproduced.**
- Raw probe Sub-test A (10×): `Start→Discovering=true` mean **0.9 ms** (max 1.0);
  `Stop→Discovering=false` mean **0.9 ms** (max 1.0). Stop is effectively
  synchronous.
- Raw probe Sub-test B (12× **zero-wait** LE↔BR/EDR transitions):
  `StartDiscovery InProgress = 0`, `SetDiscoveryFilter failed = 0`,
  `Discovering-still-true-after-stop = 0`.

**F2 — H2 (filter rejected while discovering): NOT reproduced.**
- Raw probe Sub-test C (10×): `SetDiscoveryFilter({bredr})` with `Discovering=true`
  succeeded **10/10, 0 failures**. (And in the real path the filter is only ever
  set while stopped — see F3.)

**F3 — Real survey path clean over 21 transitions.**
- Instrumented `transport=both`, 80 s, round 4 s → 11 cycles, **21 transitions,
  63 D-Bus ops: exceptions = 0**, `classic-Start-while-Discovering-true = 0`,
  `LE-Start-while-Discovering-true = 0`. `Discovering=false` before every
  `SetDiscoveryFilter` and every `StartDiscovery`.

**F4 — Device-loss quantification (no LE loss).**

| Run | total | le | classic | dual |
|---|---|---|---|---|
| both (80 s) | 6 | 5 | 0 | 1 |
| le-only (40 s) | 5 | 4 | 0 | 1 |
| bredr-only (40 s) | 0 | 0 | 0 | 0 |

- LE devices in `le-only` but missing from `both`: **none**. `both` was a
  superset of the LE baseline. Interleaving BR/EDR rounds cost no LE devices.

**Conclusion (OS #1).** H1/H2 do not reproduce on 5.84; the transition is
race-free (sub-ms settle, 0 `InProgress`, 0 filter rejections, 0 device loss over
21 real + 12 raw transitions). **H3 (version-specific) is the supported
explanation**, consistent with the reverted-guard history (`bb4cde3`, `245c7bc`).
The version-independent latent issue is **diagnosability**: discovery-call
failures are swallowed (`adapter.py:82-100`) and `InProgress`/`WrongState` are
degraded to silent no-ops (`manager.py:129-177`), so an affected build would hide
the race with no surfaced signal.

**Limitations.** (1) Only BlueZ 5.84 on one OS was available — H3 by definition
needs the *other* version. (2) No discoverable pure-Classic device, so Classic-
side inquiry loss during transitions was only partially exercised.

---

#### Evidence packet — OS/BlueZ #2 (captured 2026-07-16, independent second baseline)

**Environment.** `bluetoothd` **5.64** (a genuinely different/older build than OS
#1's 5.84 — satisfies the H3 second-OS requirement). OS `Linux ubuntu
6.8.0-124-generic #124~22.04.1-Ubuntu x86_64`; adapter `hci0`
`00:01:95:6F:D4:99` (Powered, `Discovering=false` idle, roles
`central`+`peripheral`). **A discoverable pure-Classic target was present this
time** (addresses OS #1 Limitation 2): `F4:B6:88:0B:90:22` *PLT V8200 Series*
(`Icon=audio-headset`, `Class=0x240404`, RSSI −43, in repeated pairing mode),
plus `6F:C9:74:D7:E9:22` *Pro PSP1806* (audio-headset) and `00:01:95:4B:48:0F`
*kali* (computer). No BLEEP source/docs changed — runtime monkeypatching + the
documented procedure only; `git status -- bleep/` clean throughout.

**Single-sender baseline (procedure Steps 0–2 verbatim). Result: H1/H2 do NOT
reproduce on 5.64 either — matches OS #1.**

| Metric | OS #1 (5.84) | **OS #2 (5.64)** |
|---|---|---|
| F1 SubA `start→true` / `stop→false` (mean ms) | 0.9 / 0.9 | **0.8 / 1.6** (max 1.1 / 2.3) |
| F1 SubB (12 zero-wait) InProgress / SetFilterFail / Stale | 0 / 0 / 0 | **0 / 0 / 0** |
| F2 SubC filter-while-discovering fails | 0/10 | **0/10** |
| F3 survey (`both` 80 s/4 s) D-Bus ops / exceptions / start-while-Disc | 63 / 0 / 0 | **60 / 0 / 0** |
| F4 `both` / `le-only` / `bredr-only` counts | 6 / 5 / 0 | **10 / 10 / 0** |
| F4 LE-missing-from-`both` | none | **none** (`both` == `le-only` set) |

Every `SetDiscoveryFilter` and every `StartDiscovery` in the real survey fired
with `Discovering=false` (single-sender). Verdict per the plan's own criteria
(`InProgress>0`/`SetFilterFail>0`/`Stale>0`/missing devices): **none trigger →
5.64 is also race-free under the single-process/single-sender model.**

**Cross-client contention extension (NEW — the scenario neither in-process
baseline exercised; motivated by the reverted-guard's Kali-vs-Ubuntu history).**
A second, distinct D-Bus sender (private `SystemBus`, unique name `:1.336` vs
BLEEP's `:1.335`) held an LE discovery session for the whole test while BLEEP's
sender (`S1`) cycled rounds.

- **Raw probe (12 transitions):** `InProgress=0`, `SetFilterFail=0` — per-sender
  ops still succeed. **But `StaleAfterOwnStop = 12/12`: after S1 stops its *own*
  session each round, the adapter's global `Discovering` stays `true`** because
  the other client holds it. S1 `StopDiscovery` with no own session returns
  **`org.bluez.Error.Failed: "No discovery started"`** (a real error BLEEP
  currently swallows — `adapter.py:97-100`, `manager.py:164-177`); S1
  double-`StartDiscovery` returns `org.bluez.Error.InProgress`. On S2 release,
  `Discovering` settled false in 1.3 ms.
- **Instrumented survey (`both` 60 s/4 s under contention):** **10 devices found
  (Classic headsets included), `exceptions=0`** — the current swallow-and-continue
  code path is robust under contention. Instrumentation: `classic-Start-while-Disc
  =8`, `le-Start-while-Disc=8`, `stale-after-stop=16` — i.e. **every** discovery
  op observed global `Discovering=true`.
- **Device-loss under contention (F4):** clean `both`=9 vs contended `both`=10 —
  contended was a **superset** (extra: `00:01:95:4B:48:0F`); **nothing lost**. The
  headset `F4:B6:88:0B:90:22` appears in both `both` runs.

**This explains the reverted guard (`bb4cde3`, `245c7bc`) mechanistically.** The
reverted change waited on the adapter's **global** `Discovering` property to go
`false` before proceeding. Under cross-client contention that property **never
clears** while any other client scans (proven: 12/12 raw, 16/16 survey stop
points) → the guard would block/spin its full timeout every round ("worse issues
instead of helping"). On a machine with **no** competing discovery client it is a
harmless no-op. **The decisive variable is cross-client discovery contention, not
the BlueZ version per se** (H3 refined). Both 5.64 and 5.84 are race-free without
a second client; both keep `Discovering` pinned `true` with one.

**Separate finding surfaced by the real Classic target (NOT the transition
race) — ✅ RESOLVED 2026-07-16.** `bredr-only` survey returned **0** even though
the headset is discovered by the inquiry: `get_discovered_devices()` classifies
it `type='dual'`, and the Classic round kept only `type=='br/edr'`
(`survey.py:524-528`), dropping `dual` devices. In `both` mode they were still
captured (as `dual`) so there was **no net loss** — which is why OS #1 (no Classic
device) saw `bredr-only=0` but could not diagnose it. **Fixed:** the round filter
now keeps `type in ("br/edr","dual")` and persists the actual transport
(`br/edr`→`classic`, `dual`→`dual`, avoiding a dual→classic DB downgrade). Live-
verified on 5.84 (`bredr-only` now returns the `PLT V8200`/`Pro PSP1806` headsets;
`both` unchanged; DB types them `dual`); `tests/test_survey.py` (90) green. See
`changelog.md` → "Survey Classic-round dual-device fix".

**Conclusion (OS #2).** The LE↔Classic race does **not** reproduce on 5.64 —
single-sender **or** under cross-client contention (0 exceptions, 0 device loss).
The version-independent latent defects stand confirmed and are now three: (a)
**swallowed discovery errors** (`adapter.py:82-100`, `manager.py:129-177`) —
proven to hide a real `Failed: No discovery started`; (b) **reliance on the global
`Discovering` property**, which is unsafe under multi-client contention and is the
root of the reverted guard's regression; (c) the independent `bredr-only`
classification-filter drop (`survey.py:524-528`) — **now ✅ RESOLVED
(2026-07-16)**, see the "Separate finding" note above. This **strengthens the plan's
re-scoped first deliverable** (diagnosability/error-surfacing, no timing change)
and confirms the reverted blind settle-guard must **not** be reinstated as-is; any
future settle logic must key off the sender's *own* discovery session, never the
global property.

**Artifacts (this session, workspace-local sandbox, untracked):**
`.sandbox_data/{both,le,br}.json` (single-sender baseline),
`.sandbox_data/{both_contended,both_clean,br2}.json` (contention),
`.sandbox_tmp/step3_evidence.db`, `.sandbox_tmp/step3_contention.db`.

**Limitations (OS #2).** (1) Device inventory differs from OS #1 (different
room/devices) — F4 is a fair *within-host* superset check, not a cross-host
per-device comparison. (2) Contention was simulated with an in-host second sender;
a real foreign-stack client (desktop `bluetoothd`/GNOME) was not separately tested
but is D-Bus-equivalent. (3) `bredr-only=0` is the classification filter above, so
Classic-side *transition* loss still could not be isolated numerically.

---

#### REPRODUCTION PROCEDURE — run the identical tests from a different OS/BlueZ build

> **Goal:** re-run F1–F4 against the **same physical devices** from a different
> OS/BlueZ build (e.g. Kali vs Ubuntu) so results are directly comparable. Keep
> the same room/devices powered and advertising. Read-only + discovery only — **no
> pairing, no writes, no source changes.** Record the outputs into the template at
> the end and attach them to this section as "Evidence packet — OS/BlueZ #2".

**Prerequisites.**
- Same BLEEP checkout; Python deps installed (`dbus`, `gi`/PyGObject).
- A real, powered BlueZ adapter reachable on the **system** bus, and
  `bluetoothd` running. Confirm you are on the real system bus (not a sandbox
  session bus): `unset DBUS_SYSTEM_BUS_ADDRESS DBUS_SESSION_BUS_ADDRESS`.
- Record the build under test: `bluetoothd --version` (or
  `/usr/libexec/bluetooth/bluetoothd --version`), `uname -a`, adapter name.
- Keep the **same devices** in range and in the **same advertising state** as
  OS #1 for a fair per-device comparison.

**Step 0 — capture environment + confirm adapter idle.**
```bash
unset DBUS_SYSTEM_BUS_ADDRESS DBUS_SESSION_BUS_ADDRESS
( /usr/libexec/bluetooth/bluetoothd --version 2>/dev/null || bluetoothd --version ) ; uname -a
python - <<'PY'
import dbus
p=dbus.Interface(dbus.SystemBus().get_object("org.bluez","/org/bluez/hci0"),
                 "org.freedesktop.DBus.Properties")
print("Powered=",bool(p.Get("org.bluez.Adapter1","Powered")),
      "Discovering=",bool(p.Get("org.bluez.Adapter1","Discovering")))
PY
```

**Step 1 — raw D-Bus transition probe (F1/F2).** Captures Sub-test A (stop/start
settle latency), B (12 zero-wait LE↔BR/EDR transitions), C (SetDiscoveryFilter
while discovering). Change `hci0` if your adapter differs.
```bash
unset DBUS_SYSTEM_BUS_ADDRESS DBUS_SESSION_BUS_ADDRESS
python - <<'PY'
import dbus, time, statistics
from dbus.exceptions import DBusException
bus=dbus.SystemBus(); obj=bus.get_object("org.bluez","/org/bluez/hci0")
ad=dbus.Interface(obj,"org.bluez.Adapter1"); pr=dbus.Interface(obj,"org.freedesktop.DBus.Properties")
def discovering(): return bool(pr.Get("org.bluez.Adapter1","Discovering"))
def call(fn,*a):
    try: fn(*a); return True,None,""
    except DBusException as e: return False,e.get_dbus_name(),(e.get_dbus_message() or "")
def settle(target,timeout=3.0,step=0.02):
    t0=time.monotonic()
    while time.monotonic()-t0<timeout:
        if discovering()==target: return round((time.monotonic()-t0)*1000,1)
        time.sleep(step)
    return None
if discovering(): call(ad.StopDiscovery); settle(False)
print("### SUB-TEST A — settle latency (H1)")
sa,so=[],[]
for i in range(10):
    ad.SetDiscoveryFilter({"Transport":"le"}); call(ad.StartDiscovery); sa.append(settle(True) or -1)
    time.sleep(1.0); call(ad.StopDiscovery); so.append(settle(False) or -1)
st=lambda xs:(min(xs),max(xs),round(statistics.mean(xs),1))
print(" start->true ms",sa,st(sa)); print(" stop->false ms",so,st(so))
print("### SUB-TEST B — back-to-back zero-wait transitions (H1/H3)")
tr=["le","bredr"]; rows=[]
ad.SetDiscoveryFilter({"Transport":"le"}); call(ad.StartDiscovery); settle(True); time.sleep(1.0)
for i in range(12):
    nxt=tr[(i+1)%2]
    so_,se_,_=call(ad.StopDiscovery); das=discovering()
    fo,fe,_=call(ad.SetDiscoveryFilter,{"Transport":nxt}); to,te,_=call(ad.StartDiscovery); dast=discovering()
    rows.append((i,tr[i%2],nxt,so_,se_,das,fo,fe,to,te,dast)); time.sleep(1.0)
call(ad.StopDiscovery); settle(False)
for r in rows: print(" ",r)
print(" InProgress=",sum(1 for r in rows if r[9] and "InProgress" in r[9]),
      "SetFilterFail=",sum(1 for r in rows if not r[6]),
      "StaleDiscovering=",sum(1 for r in rows if r[5] is True))
print("### SUB-TEST C — SetDiscoveryFilter while Discovering=true (H2)")
cf=0
for i in range(10):
    ad.SetDiscoveryFilter({"Transport":"le"}); call(ad.StartDiscovery); settle(True)
    ok,en,_=call(ad.SetDiscoveryFilter,{"Transport":"bredr"}); cf+=0 if ok else 1
    print(f"  {i} Discovering={discovering()} SetFilter(bredr) ok={ok} err={en or '-'}")
    call(ad.StopDiscovery); settle(False)
print(" filter-while-discovering failures=",cf)
PY
```

**Step 2 — instrumented real survey + baselines (F3/F4).** Wraps the actual
survey code paths (no source edits) to log the transition sequence, then runs
`both` (≥21 transitions) and single-transport baselines and quantifies device
loss. Uses workspace-local sandbox dirs + a temp DB so nothing global is touched.
```bash
export XDG_DATA_HOME="$PWD/.sandbox_data" XDG_CACHE_HOME="$PWD/.sandbox_cache" \
       XDG_CONFIG_HOME="$PWD/.sandbox_config" BLEEP_DB_PATH="$PWD/.sandbox_tmp/step3_evidence.db"
mkdir -p "$PWD/.sandbox_tmp"
unset DBUS_SYSTEM_BUS_ADDRESS DBUS_SESSION_BUS_ADDRESS
python - <<'PY'
import time, json, os, dbus
import bleep.dbuslayer.manager as M, bleep.dbuslayer.adapter as A
from bleep.modes import survey as S
_pr=dbus.Interface(dbus.SystemBus().get_object("org.bluez","/org/bluez/hci0"),
                   "org.freedesktop.DBus.Properties")
def disc():
    try: return bool(_pr.Get("org.bluez.Adapter1","Discovering"))
    except Exception as e: return f"ERR:{e}"
EVENTS=[]; LOGGING=False; _t0=time.monotonic()
def ev(actor,method,b,a,r,err=None):
    if LOGGING: EVENTS.append((round((time.monotonic()-_t0)*1000,1),actor,method,b,a,r,err))
_ms,_mp=M.system_dbus__bluez_device_manager.start_discovery,M.system_dbus__bluez_device_manager.stop_discovery
def mstart(self,*a,**k):
    b=disc(); err=None
    try:r=_ms(self,*a,**k)
    except Exception as e:r=None;err=repr(e)
    ev("LE-mgr","start_discovery",b,disc(),r,err);return r
def mstop(self,*a,**k):
    b=disc(); err=None
    try:r=_mp(self,*a,**k)
    except Exception as e:r=None;err=repr(e)
    ev("LE-mgr","stop_discovery",b,disc(),r,err);return r
M.system_dbus__bluez_device_manager.start_discovery=mstart
M.system_dbus__bluez_device_manager.stop_discovery=mstop
_sf,_ts,_to=A.system_dbus__bluez_adapter.set_discovery_filter,A.system_dbus__bluez_adapter.run_scan__timed,A.system_dbus__bluez_adapter._discovery_timeout
def sf(self,f,*a,**k): b=disc();r=_sf(self,f,*a,**k);ev("CL-adp",f"set_discovery_filter({dict(f)})",b,disc(),r);return r
def ts(self,*a,**k): b=disc();r=_ts(self,*a,**k);ev("CL-adp","run_scan__timed(StartDiscovery)",b,disc(),r);return r
def to(self,*a,**k): b=disc();r=_to(self,*a,**k);ev("CL-adp","_discovery_timeout(StopDiscovery)",b,disc(),r);return r
A.system_dbus__bluez_adapter.set_discovery_filter=sf
A.system_dbus__bluez_adapter.run_scan__timed=ts
A.system_dbus__bluez_adapter._discovery_timeout=to
def runs(transport,duration,out):
    args=S._build_parser().parse_args(["--duration",str(duration),"--round-time","4",
        "--transport",transport,"-o",out,"--format","objects","--live","--adapter","hci0"])
    S.run(args,None)
    data=json.load(open(out)) if os.path.exists(out) else []
    c={"le":0,"classic":0,"dual":0,"unknown":0}
    for d in data: c[d.get("device_type","unknown") if d.get("device_type") in c else "unknown"]+=1
    c["total"]=len(data); c["addrs"]={d["address"] for d in data}; return c
D=os.environ["XDG_DATA_HOME"]
LOGGING=True; both=runs("both",80,os.path.join(D,"both.json")); LOGGING=False
print("--- transition log ---")
for e in EVENTS: print(e)
print("EVENTS=",len(EVENTS),"exceptions=",sum(1 for e in EVENTS if e[6]),
      "classic-Start-while-Disc=",sum(1 for e in EVENTS if e[2].startswith("run_scan__timed") and e[3] is True))
le=runs("le",40,os.path.join(D,"le.json")); br=runs("bredr",40,os.path.join(D,"br.json"))
for n,c in (("both",both),("le-only",le),("bredr-only",br)):
    print(f"{n}: total={c['total']} le={c['le']} classic={c['classic']} dual={c['dual']}")
print("LE missing from both:", le["addrs"]-both["addrs"])
print("Classic missing from both:", br["addrs"]-both["addrs"])
PY
```

**Step 3 — record results.** Fill in and append as a sibling packet:
```
Evidence packet — OS/BlueZ #2 (captured <date>)
  bluetoothd: <ver>   OS: <uname>   adapter: <hciX>
  Device inventory (must match OS #1): <MACs + type + advertising state>
  F1 settle: start->true mean __ms (max __) ; stop->false mean __ms (max __)
  F1 SubB: transitions=12  InProgress=__  SetFilterFail=__  StaleDiscovering=__
  F2 SubC: filter-while-discovering failures=__/10
  F3 survey: transitions=__  exceptions=__  stale-Discovering=__  (attach transition log)
  F4 device-loss: both/le-only/bredr-only counts ; LE-missing-from-both=__ ; Classic-missing-from-both=__
  Verdict: does the LE<->Classic race reproduce here? (Y/N + which of H1/H2/H3)
```
**Comparison criteria (what makes OS #2 "the affected build"):** any of —
`InProgress > 0` on Sub-test B or the survey; `SetFilterFail > 0`;
`StaleDiscovering > 0` (stop not settled); non-empty **LE-missing-from-both** or
**Classic-missing-from-both** vs the single-transport baseline. If none trigger,
OS #2 is also race-free and the historical trigger lies elsewhere (adapter
firmware, kernel, or an even older BlueZ).

---

**Proposed approach — re-scoped after OS #1 evidence (additive, reversible).**
*First deliverable (version-independent, safe on all builds):* **diagnosability
upgrade — stop swallowing discovery errors.** Surface `StartDiscovery`/
`StopDiscovery`/`SetDiscoveryFilter` failures (and `InProgress`/`WrongState`) to
the round result and log a real warning with the exact D-Bus error name +
`Discovering` state, instead of the current silent DEBUG-and-continue
(`adapter.py:82-100`, `manager.py:129-177`). This changes **no happy-path
behaviour** but guarantees the next occurrence on an affected build is captured
with hard data. *Deferred second deliverable (gated on OS #2 evidence):* the
**bounded, opt-in `Discovering`-state settle + single retry** and the
"filter-only-while-stopped, else skip the round" ordering — designed **only if**
OS #2 reproduces the race, and tuned per BlueZ version. The blind settle-guard
(the reverted `bb4cde3` change) is explicitly **not** adopted as-is.

**Risk & mitigation.** The prior revert shows an over-eager stop guard can
*worsen* behaviour on some BlueZ builds. Mitigation: (a) the first deliverable is
logging/error-surfacing only — no timing change; (b) any later settle/retry is
bounded with timeouts, opt-in/tunable; (c) verified on **both** OS #1 and OS #2
before merge; (d) additive and independently revertable; (e) full `pytest` green.

**Tests (planned).**
- Unit (mock D-Bus, CI-safe): a fake adapter whose `StartDiscovery`/`StopDiscovery`
  raise `InProgress`/`DBusException` → assert the failure is **surfaced to the
  round result and logged with its error name**, not swallowed. For the deferred
  settle/retry: first `StartDiscovery` raises `InProgress` then succeeds after a
  `StopDiscovery` + `Discovering→false`; verify `SetDiscoveryFilter` is never
  called while `Discovering`.
- Hardware (`@pytest.mark.hardware`, run on OS #1 **and** OS #2): ≥10 LE↔Classic
  transitions with per-round device counts ≥ single-transport baseline; no hung
  rounds. Use the Reproduction Procedure above as the harness.

**Acceptance gates.** (1) OS #1 evidence packet reviewed and accepted *(this
section)*. (2) **OS #2 reproduction packet captured** using the procedure above.
(3) Design sign-off: diagnosability upgrade first; settle/retry only if OS #2
reproduces. (4) Implementation with unit tests green. (5) Live verification on
both builds. Only then merge.

---

#### FIRST DELIVERABLE — IMPLEMENTED (2026-07-16): discovery-error surfacing

Version-independent diagnosability upgrade (gates 1–4). **Additive,
behaviour-preserving, no happy-path timing/return change; the reverted
`Discovering`-settle guard (`bb4cde3`) is NOT reinstated.**

- **`dbuslayer/adapter.py`** — new `_note_discovery_error()` helper; wired into
  `run_scan__timed` (`StartDiscovery`), `_discovery_timeout` (`StopDiscovery`),
  and `set_discovery_filter`. Failures now emit a WARNING with the exact D-Bus
  error name + current `Discovering` state and are recorded on
  `self._last_discovery_error` (was: silent `logger.debug`, invisible at the
  INFO root level). Returns (`True`/`False`) and control flow unchanged.
- **`dbuslayer/manager.py`** — matching `_note_discovery_error()` helper wired
  into `start_discovery` (degraded `InProgress`/`WrongState`/`NotFound` no-op
  **and** the hard-error raise path), `stop_discovery`, and the optional-
  `SetDiscoveryFilter` branch. Emits a real `LOG__GENERAL` warning + records
  `_last_discovery_error`; graceful-degrade and raise semantics preserved. This
  captures the cross-client `org.bluez.Error.Failed: No discovery started` that
  the OS #2 contention evidence proved is otherwise silent.
- **Tests** — `tests/test_discovery_error_surfacing.py`: 9 CI-safe unit tests
  (no hardware; objects built via `object.__new__` + injected fakes) asserting
  each site surfaces the error and that happy-path returns are unchanged.
- **Suite** — `1284 passed, 27 skipped` (`tests/`, excluding `bleep-mcp`). The 5
  failures in `test_aoi_augmentation.py` are **pre-existing and unrelated**
  (stale `_normalise_service_element` symbol — removed 2026-07-15 per changelog —
  and a `_SCHEMA_VERSION==15` assertion vs the current v16 F2 migration).

**Remaining for this cycle:** gate (5) live re-verification of the emitted
warnings on OS #1 (5.84) + OS #2 (5.64), and the **deferred** second deliverable
(bounded, own-session settle/retry — NOT the global-`Discovering` guard) which is
gated on a build that actually reproduces the race.

**Gate (5) status:** OS #2 (5.64) **DONE** and OS #1 (5.84) **DONE** — both live
re-verification packets recorded below (each 12/12 checks + clean survey + on-disk
proof, 2026-07-16). **Gate (5) is CLOSED for the first deliverable** on both
builds. The deferred settle/retry remains separately gated on a build that
actually reproduces the race.

---

#### GATE (5) LIVE RE-VERIFICATION PROCEDURE — discovery-error surfacing (diagnosability upgrade)

> **Goal (distinct from the F1–F4 procedure above):** F1–F4 *characterize the
> race*; this procedure *verifies the delivered code change*. It proves that
> `_note_discovery_error()` (a) surfaces real, otherwise-swallowed
> `StartDiscovery`/`StopDiscovery`/`SetDiscoveryFilter` failures as a WARNING +
> `_last_discovery_error` record, and (b) does **not** introduce false-positive
> warnings on the happy path. Run this on **each** build to accept the change.
>
> **Why it is build-independent (important):** the three failure triggers are
> *deterministic* and do **not** depend on the LE↔Classic race — an invalid
> filter, `StopDiscovery` with no active session, and a double `StartDiscovery`
> raise `InvalidArguments` / `Failed: No discovery started` / `InProgress` on
> **every** BlueZ build. So the verification produces the same PASS matrix on
> 5.84 and 5.64 regardless of whether that host reproduces the race. Read-only +
> discovery only; **no pairing, no writes, no source changes.**

**Prerequisites.**
- Checkout on the branch containing the FIRST DELIVERABLE change; confirm the
  code is present: `git grep -n "_note_discovery_error" bleep/dbuslayer/` must
  list both `adapter.py` and `manager.py`.
- Real, powered BlueZ adapter on the **system** bus; `bluetoothd` running;
  adapter **idle** (`Discovering=false`) at start.
- `unset DBUS_SYSTEM_BUS_ADDRESS DBUS_SESSION_BUS_ADDRESS` (real system bus).
- Replace `hci0` throughout if your adapter differs.
- No second scanner/`bluetoothctl` holding a discovery session (would make the
  "no session" triggers behave differently — that is the *contention* case,
  covered separately by the OS #2 packet, not this gate).

**Step L0 — record build + confirm idle.**
```bash
cd <BLEEP_checkout>
unset DBUS_SYSTEM_BUS_ADDRESS DBUS_SESSION_BUS_ADDRESS
unset XDG_DATA_HOME XDG_CACHE_HOME XDG_CONFIG_HOME BLEEP_DB_PATH
( /usr/libexec/bluetooth/bluetoothd --version 2>/dev/null || bluetoothd --version ) ; uname -a
git grep -n "_note_discovery_error" bleep/dbuslayer/adapter.py bleep/dbuslayer/manager.py
```

**Step L1 — method-level surfacing + happy path (the 12-check matrix).** Exercises
the **real** adapter/manager methods (no method-level monkeypatching) and captures
adapter WARNINGs off the stdlib `bleep` logger; manager warnings print to stdout.
```bash
export BLEEP_DB_PATH="$(mktemp -d)/lv.db"    # isolate DB; nothing global touched
python - <<'PY'
import logging, time, dbus
captured=[]
class _Cap(logging.Handler):
    def emit(self, rec): captured.append(rec.getMessage())
h=_Cap(); h.setLevel(logging.WARNING); logging.getLogger("bleep").addHandler(h)
from bleep.dbuslayer.adapter import system_dbus__bluez_adapter
from bleep.dbuslayer.manager import system_dbus__bluez_device_manager
adp = system_dbus__bluez_adapter("hci0")
_props = dbus.Interface(dbus.SystemBus().get_object("org.bluez","/org/bluez/hci0"),
                        "org.freedesktop.DBus.Properties")
def discovering(): return bool(_props.Get("org.bluez.Adapter1","Discovering"))
def ensure_stopped():
    try: adp.adapter_interface.StopDiscovery()
    except Exception: pass
    t0=time.time()
    while discovering() and time.time()-t0<3: time.sleep(0.05)
results=[]
def check(name, cond, detail=""):
    results.append((name,bool(cond),detail)); print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")
ensure_stopped(); print("=== initial Discovering =", discovering(), "===")
# A) invalid discovery filter -> InvalidArguments, surfaced
adp._last_discovery_error=None
r=adp.set_discovery_filter({"Transport":"bogus"}); e=adp._last_discovery_error
check("adapter.set_discovery_filter(invalid) returns False", r is False)
check("adapter.set_discovery_filter surfaced _last_discovery_error", e is not None, str(e))
check("adapter.set_discovery_filter emitted WARNING", any("SetDiscoveryFilter failed" in m for m in captured))
# B) StopDiscovery with no session -> Failed: No discovery started
ensure_stopped(); adp._last_discovery_error=None
rc=adp._discovery_timeout(); e=adp._last_discovery_error
check("adapter._discovery_timeout returns False (GLib contract)", rc is False)
check("adapter._discovery_timeout surfaced StopDiscovery error",
      e is not None and e.get("method")=="StopDiscovery", str(e))
# C) StartDiscovery InProgress via same sender
ensure_stopped(); adp._last_discovery_error=None
adp.set_discovery_filter({"Transport":"le"}); adp.adapter_interface.StartDiscovery(); time.sleep(0.3)
r=adp.run_scan__timed(duration=2); e=adp._last_discovery_error
check("adapter.run_scan__timed(InProgress) returns False", r is False)
check("adapter.run_scan__timed surfaced StartDiscovery InProgress",
      e is not None and e.get("method")=="StartDiscovery" and "InProgress" in (e.get("error_name") or ""), str(e))
ensure_stopped()
# D) manager.stop_discovery with no session -> Failed, no raise, surfaced degraded
mgr = system_dbus__bluez_device_manager("hci0")
ensure_stopped(); mgr._last_discovery_error=None
mgr.stop_discovery(); e=mgr._last_discovery_error
check("manager.stop_discovery(no session) did not raise & surfaced",
      e is not None and e.get("method")=="StopDiscovery", str(e))
# E) manager.start_discovery twice -> 2nd InProgress degraded & surfaced
ensure_stopped(); mgr._last_discovery_error=None
mgr.start_discovery(timeout=5); mgr.start_discovery(timeout=5); e=mgr._last_discovery_error
check("manager.start_discovery(2nd) degraded InProgress & surfaced",
      e is not None and e.get("method")=="StartDiscovery" and "InProgress" in (e.get("error_name") or "")
      and e.get("degraded") is True, str(e))
ensure_stopped()
# HAPPY PATH — no false positives
adp2=system_dbus__bluez_adapter("hci0"); mgr2=system_dbus__bluez_device_manager("hci0")
ensure_stopped(); adp2._last_discovery_error=None; mgr2._last_discovery_error=None
ok=adp2.set_discovery_filter({"Transport":"le"}); mgr2.start_discovery(timeout=3); time.sleep(0.4); mgr2.stop_discovery()
check("happy: valid set_discovery_filter returns True", ok is True)
check("happy: adapter no error recorded", adp2._last_discovery_error is None, str(adp2._last_discovery_error))
check("happy: manager no error recorded", mgr2._last_discovery_error is None, str(mgr2._last_discovery_error))
ensure_stopped()
print("\n=== ADAPTER WARNINGS CAPTURED ==="); [print("  WARN:",m) for m in captured]
print("\n=== SUMMARY ===", f"{sum(1 for _,c,_ in results if c)}/{len(results)} checks passed",
      "| final Discovering =", discovering())
PY
```
**Expected (identical on 5.84 and 5.64): `12/12 checks passed`, `final Discovering = False`.**
Adapter warnings captured must include `InvalidArguments`, `Failed: No discovery
started`, and `InProgress`; manager must print two `[!] ... (degraded to no-op)`
lines (StopDiscovery `Failed`, StartDiscovery `InProgress`).

**Step L2 — integration happy path (no false positives during real transitions).**
```bash
export XDG_DATA_HOME="$(mktemp -d)" BLEEP_DB_PATH="$(mktemp -d)/lv2.db"
python - <<'PY'
import logging
from bleep.modes import survey as S
warns=[]
class _Cap(logging.Handler):
    def emit(self, rec): warns.append(rec.getMessage())
h=_Cap(); h.setLevel(logging.WARNING); logging.getLogger("bleep").addHandler(h)
args=S._build_parser().parse_args(["--duration","16","--round-time","4",
    "--transport","both","--adapter","hci0","--quiet"])
rc=S.run(args, None)
disc=[m for m in warns if any(k in m for k in ("StartDiscovery","StopDiscovery","SetDiscoveryFilter"))]
print("survey rc=",rc,"| discovery-related WARNINGs:", len(disc))
for m in disc: print("  ", m)
PY
```
**Expected: `rc=0`, `discovery-related WARNINGs: 0`** (normal LE↔Classic
transitions emit no surfaced errors). Device count is environment-dependent and
not a pass criterion here.

**Step L3 — on-disk persistence proof.** Confirms a surfaced error is written to
`general.log` (manager path via `LOG__GENERAL`), i.e. visible post-hoc, not just
in memory.
```bash
unset XDG_DATA_HOME XDG_CACHE_HOME XDG_CONFIG_HOME
export BLEEP_DB_PATH="$(mktemp -d)/lv3.db"
python - <<'PY'
from bleep.core import config
from bleep.dbuslayer.manager import system_dbus__bluez_device_manager
mgr=system_dbus__bluez_device_manager("hci0")
try: mgr._adapter.StopDiscovery()
except Exception: pass
mgr._last_discovery_error=None; mgr.stop_discovery()
print("recorded:", mgr._last_discovery_error)
p=config.LOG_DIR/"general.log"
hits=[l for l in p.read_text().splitlines() if "failed on /org/bluez" in l]
print("general.log:", p); [print("  ",l) for l in hits[-3:]]
print("total on-disk discovery-error lines:", len(hits))
PY
```
**Expected:** `recorded:` a dict with `method=StopDiscovery`,
`error_name=org.bluez.Error.Failed`, `"No discovery started"`, `degraded=True`;
and ≥1 matching line in `general.log`.

**Step L4 — record results.** Append a sibling packet:
```
Live re-verification packet — OS/BlueZ #1 (captured <date>)
  bluetoothd: <ver>   OS: <uname>   adapter: <hciX>   branch/commit: <sha>
  git grep _note_discovery_error -> adapter.py:<n> manager.py:<n> (present? Y/N)
  L1 method matrix: __/12 checks passed ; final Discovering = <bool>
     adapter WARNINGs captured: InvalidArguments[ ] Failed/NoDiscovery[ ] InProgress[ ]
     manager degraded lines: StopDiscovery-Failed[ ] StartDiscovery-InProgress[ ]
  L2 clean survey: rc=__ ; discovery-related WARNINGs=__ (must be 0)
  L3 on-disk: recorded dict present[ ] ; general.log discovery-error lines >=1[ ]
  Verdict: ACCEPT diagnosability upgrade on this build? (Y/N)
```

**Pass criteria to close gate (5):** L1 = `12/12`, L2 = `0` discovery warnings,
L3 recorded-dict + on-disk line present — on **both** OS #1 and OS #2. OS #2 is
already recorded below; capturing OS #1 with this procedure closes the cycle for
the first deliverable (the deferred settle/retry remains separately gated).

---

#### Live re-verification packet — OS/BlueZ #2 (captured 2026-07-16)

```
bluetoothd: 5.64   OS: Ubuntu 22.04 (kernel 6.8.0-124)   adapter: hci0 (00:01:95:6F:D4:99)
branch/commit: working tree of FIRST DELIVERABLE (uncommitted); _note_discovery_error present in adapter.py + manager.py
L1 method matrix: 12/12 checks passed ; final Discovering = False
   adapter WARNINGs captured:
     [!] SetDiscoveryFilter failed on /org/bluez/hci0: org.bluez.Error.InvalidArguments: Invalid arguments in method call (Discovering=False)
     [!] StopDiscovery failed on /org/bluez/hci0: org.bluez.Error.Failed: No discovery started (Discovering=False)
     [!] StartDiscovery failed on /org/bluez/hci0: org.bluez.Error.InProgress: Operation already in progress (Discovering=True)
   manager degraded lines: StopDiscovery-Failed [x] StartDiscovery-InProgress [x]
L2 clean survey: rc=0 ; discovery-related WARNINGs=0 ; 11 devices (LE + dual incl. PLT V8200 headset)
L3 on-disk: recorded dict present [x] ; general.log discovery-error lines >=1 [x]
   (~/.local/share/bleep/logs/general.log)
Verdict: ACCEPT diagnosability upgrade on 5.64 — behaviour-preserving, errors surfaced, no false positives.
```

---

#### Live re-verification packet — OS/BlueZ #1 (captured 2026-07-16)

```
bluetoothd: 5.84   OS: Linux kali 6.12.20-amd64 (Kali 6.12.20-1kali1)   adapter: hci0
branch/commit: working tree of FIRST DELIVERABLE (pulled); _note_discovery_error present in adapter.py + manager.py
L1 method matrix: 12/12 checks passed ; final Discovering = False
   adapter WARNINGs captured:
     [!] SetDiscoveryFilter failed on /org/bluez/hci0: org.bluez.Error.InvalidArguments: Invalid arguments in method call (Discovering=False)
     [!] StopDiscovery failed on /org/bluez/hci0: org.bluez.Error.Failed: No discovery started (Discovering=False)
     [!] StartDiscovery failed on /org/bluez/hci0: org.bluez.Error.InProgress: Operation already in progress (Discovering=True)
   manager degraded lines: StopDiscovery-Failed [x] StartDiscovery-InProgress [x]
L2 clean survey: rc=0 ; discovery-related WARNINGs=0 ; 5 devices (LE + dual incl. PLT V8200 + Pro PSP1806)
L3 on-disk: recorded dict present [x] ; general.log discovery-error lines >=1 [x] (6 lines)
   (~/.local/share/bleep/logs/general.log)
Verdict: ACCEPT diagnosability upgrade on 5.84 — behaviour-preserving, errors surfaced, no false positives.
         Byte-for-byte identical PASS matrix and warning strings vs OS #2 (5.64).
```

**Cross-build result:** L1 `12/12` on **both** 5.84 and 5.64 with identical error
names/messages; L2 `rc=0` / `0` discovery warnings on both; L3 on-disk proof on
both. **Gate (5) closed for the first deliverable.**

**Notes from OS #1 re-validation (for the record).** The `tests/` tree in the OS
#1 environment is **out of scope / non-authoritative** (per operator direction) —
the canonical `tests/test_discovery_error_surfacing.py` (9 CI-safe tests) and the
A–F test fixes live in the primary checkout, so the OS #2 test-suite counts are
the authoritative ones. OS #1 validation was purely the **live hardware**
re-verification of the production code (`adapter.py`/`manager.py`
`_note_discovery_error`), which passed 12/12 + clean survey + on-disk proof.

---

## Bluetooth Networking (BlueZ PAN / BNEP) — Full D-Bus Incorporation Plan (2026-07-12) — ACCEPTED · PHASES 0–4 COMPLETE

> **STATUS (2026-07-13):** Plan accepted by user. **Phases 0, 1, 2, 3, 3b, and 4
> are COMPLETE** (preflight, connect-path correctness, enumeration + device-class
> integration, multi-role server, and real-time signals + server authorization).
> A scripted peer harness (`bleep/scripts/pan_peer.py`) is in place for two-node
> live testing. **Remaining:** Phase 5 (full test-suite parity / hardware
> integration marks) and the two Future-Work tracks (raw BNEP; NAP host
> auto-setup). This section is the authoritative follow-along record for all
> networking work.

**Context**: The user requested full incorporation of the "Bluetooth Networking"
aspect of BlueZ into `bleep/`. A source audit (`workDir/bluez/profiles/network/`,
`workDir/bluez/lib/bnep.h`, `workDir/BlueZDocs/org.bluez.Network*.rst`,
`workDir/BlueZScripts/test-network` + `test-nap`) established that BlueZ's
*entire* networking subsystem is the **PAN profile over BNEP over L2CAP
PSM `0x000F`** (`profiles/network/manager.c:196` registers the `network` plugin;
roles PANU `0x1115` / NAP `0x1116` / GN `0x1117`, `lib/bnep.h:31-33`). There is
**no 6LoWPAN / IPSP** in this tree (`grep -rl -i "6lowpan|ipsp" src profiles
plugins tools client lib` → none; 6LoWPAN is a kernel debugfs feature, not a
BlueZ D-Bus API). **`bleep-mcp/` is explicitly out of scope for this work.**

### Architectural boundary (READ FIRST — governs every decision here)

BLEEP is a **BlueZ D-Bus client**. BlueZ exposes networking through **exactly
two** D-Bus interfaces and nothing else:

| Interface | Path | Methods | Properties |
|-----------|------|---------|------------|
| `org.bluez.Network1` (per-device) | `/org/bluez/hciX/dev_…` | `Connect(uuid)→s`, `Disconnect()` | `Connected` (b, ro), `Interface` (s, ro/opt), `UUID` (s, ro/opt) |
| `org.bluez.NetworkServer1` (per-adapter) | `/org/bluez/hciX` | `Register(uuid,bridge)`, `Unregister(uuid)` | *(none)* |

Everything below those interfaces is **internal to `bluetoothd` + the kernel
`bnep` module and is UNREACHABLE from a D-Bus client**: BNEP setup/control
messages, the **filter subsystem** (net-type `0x03/0x04`, multicast `0x05/0x06`
— `lib/bnep.h:46-49`), extension headers (`lib/bnep.h:75-77`), kernel ioctls
(`BNEPCONNADD/DEL/GETCONNLIST/GETCONNINFO/GETSUPPFEAT` — `lib/bnep.h:112-116`),
bridge attach (`bnep_server_add`, `server.c:374`), SDP record content
(`server.c:142-266`), and the `network.conf` `DisableSecurity` gate
(`manager.c:36-62`). Reaching them requires re-implementing bluetoothd (raw
L2CAP on PSM 0x0F + kernel ioctls) — captured as **Future Work: Option B**.

> **Acceptance point (agreed with user):** "Full incorporation" for this effort =
> Option A (100 % of `Network1` + `NetworkServer1`, the D-Bus-adjacent
> expansions E1–E8, and the host prerequisites BlueZ does *not* manage). Raw
> BNEP (Option B) is documented below but deferred. NAP host provisioning starts
> as detect-and-instruct (Option A); opt-in `--auto-setup` is the eventual goal
> (Option B).

**Governing rules for this work** (per user dev rules + `CONTRIBUTING` norms):
reuse existing structures over new subsystems; additive, independently-revertable
commits; no destructive/privileged host mutation without an explicit opt-in flag;
full `pytest` + (where hardware available) live-device verification per change;
reference `workDir/bluez/`, `workDir/BlueZScripts/`, `workDir/BlueZDocs/` for
protocol ground-truth; keep behaviour identical for existing `classic-pan`
success paths.

### Current-state inventory (already implemented — do NOT rebuild)

| Layer | File(s) | Status |
|-------|---------|--------|
| D-Bus wrappers | `bleep/dbuslayer/network.py` — `NetworkClient` (Connect/Disconnect + props + `GetAll` snapshot + post-connect verify), `NetworkServer` (Register/Unregister) | ✅ |
| Ops layer | `bleep/ble_ops/classic/pan.py` — `connect/disconnect/status/register_server/unregister_server`, `detect_pan_service()`, observation writes | ✅ |
| CLI parser | `bleep/cli/parsers/classic.py:150-172` — `classic-pan connect\|disconnect\|status\|serve\|unserve` (`--role`,`--bridge`) | ✅ |
| CLI dispatch | `bleep/cli/dispatch.py:256-258` → `bleep/modes/classic_profiles.py:416` `run_pan()` | ✅ |
| Debug REPL | `bleep/modes/debug_classic_profiles.py` `cmd_cpan` (retains `state.pan_client/pan_server`) | ✅ |
| Constants | `bleep/bt_ref/constants.py:230-240` — PAN UUIDs + `NETWORK_INTERFACE`/`NETWORK_SERVER_INTERFACE` | ✅ |
| Observations | `bleep/core/observations/_services.py` `upsert_pan_access` (exported) | ✅ |
| Standalone checker | `bleep/scripts/check_network_capabilities.py` | ✅ |
| Docs | `network_capability_plan.md`, `network_capability_summary.md`, `pan_connection_analysis.md`, `bl_classic_mode.md` §2.9 | ✅ |

**The `Network1`/`NetworkServer1` method+property surface is 100 % wrapped.**
Remaining work is robustness, prerequisite handling, enumeration integration,
D-Bus-adjacent expansions (E1–E8), and the (currently absent) **test suite**.

### Gap analysis (evidence-based)

| # | Gap | Evidence | Sev |
|---|-----|----------|-----|
| G1 | No device-class integration (plan Phases 2–5 deferred): no `is_network_device()/get_network_roles()` on `device_classic.py`/`device_le.py`; no `network-enum`; no network key in `get_device_info()`. The `Network` + `find_network_devices()` sketch was never built. | `network_capability_plan.md:288-589`; `dbuslayer/network.py` (no `Network`/`find_network_devices`) | ✅ RESOLVED (Ph 3: helpers on both device classes, `network-enum`, additive `network` key, `pan.find_network_devices/servers`) |
| G2 | No prerequisite/preflight checks: `bnep` module load, bridge existence, `ip_forward`, NAT/DHCP never checked. Analysis doc lists "bnep kernel module loaded — **Not checked by BLEEP**". | `pan_connection_analysis.md:242-281` | **High** — ✅ RESOLVED (Ph 1) |
| G3 | No SDP/bond precheck in connect path — `Network1.Connect`→`NotSupported` if PAN service not probed; `detect_pan_service()` never called pre-connect. | `connection.c:289-291`; `ble_ops/classic/pan.py:46-68` | Med — ✅ RESOLVED (Ph 2, `_precheck_pan_target`) |
| G4 | `NetworkServer1` presence not surfaced in adapter enumeration/survey. | `manager.c:64-119`; only in standalone script | ✅ RESOLVED (Ph 3: `pan.find_network_servers()` + `network-enum`) |
| G5 | **Zero tests** — `tests/` has no PAN/Network1/BNEP references; both plan docs specify a test strategy never implemented. | `ls tests/`; grep empty | **High** — ◑ PARTIAL (Ph 1–4: `tests/test_network_pan.py`, 98 unit tests; hardware/integration marks still pending Ph 5) |
| G6 | Role-arg fidelity < BlueZ: `_VALID_ROLES` rejects full-UUID role strings BlueZ accepts. | `dbuslayer/network.py:34,90-91`; `connection.c:71-81`; `Network.rst:29-42` | Low — ✅ RESOLVED (Ph 2, `normalize_pan_role`) |
| G7 | Inconsistent errors: `network.py` raises bare `RuntimeError`; codebase convention is `core.errors.map_dbus_error`/`BLEEPError`. | `dbuslayer/network.py:66-71,95-99` | Low — ✅ RESOLVED (Ph 2) |
| G8 | Polling (`sleep(0.5)`) instead of `PropertiesChanged` subscription for Connected/Interface/UUID. | `connection.c:217-222` (emits) vs `dbuslayer/network.py:102` | Low/Med — ✅ RESOLVED (Ph 4: `NetworkMonitor` + `NetworkClient._verify_connected` event-driven, 0.5 s poll fallback) |
| G9 | BNEP-layer + `network.conf` unreachability not explicitly documented for users. | `lib/bnep.h:35-63`; `network.conf`; `manager.c:36-62` | Doc |

### PAN D-Bus capability expansions (E1–E8 — better cover BlueZ over D-Bus)

All are **D-Bus-reachable** (E4 is a read-only host-side complement) and extend
the existing PAN feature without touching the raw-BNEP boundary.

| # | Expansion | Evidence / mechanism | Target phase |
|---|-----------|----------------------|--------------|
| E1 | **Alternative connect via `Device1.ConnectProfile(uuid)` / `DisconnectProfile(uuid)`** — fallback when `Network1.Connect` returns `NotSupported` before SDP probe; triggers bluetoothd profile probing. | `org.bluez.Device.rst:72,86`; bluetoothd routes profile `.connect`→`connection_connect` (`manager.c:127,139,151`); existing wrapper `device_classic.py:695,739` | Ph 2 ✅ |
| E2 | **Multi-role concurrent server** — register NAP+GN+PANU simultaneously, each to its own bridge; track `{role:bridge}` for clean `unregister_all` teardown. | `server.c:90-140` (multiple `network_server` per adapter, single `NetworkServer1` iface), `:534-569` | ✅ RESOLVED (Ph 3b: `NetworkServer.registered_roles`/`unregister_all()`, `register_servers()` w/ rollback, `serve --all`/repeatable `--role`) |
| E3 | **Pre-connect bond/trust/SDP resolution** — ensure `Paired`, optionally set `Trusted=true`, wait for `ServicesResolved` before connect. | `connection.c:289-291`; `Device.rst:375`; reuse `core.preflight.check_device_state` + pairing subsystem | Ph 2 ✅ (advisory; `--trust` sets Trusted) |
| E4 | **Post-connect netdev reporting** (read-only) — report `operstate/carrier/address/mtu` of the returned `bnepX` from `/sys/class/net/<iface>`. Host-side complement to the D-Bus `Interface` prop; no DHCP/mutation (that is Future-Work auto-setup). | `connection.c:206` (iface name); Linux sysfs | ◑ PARTIAL (Ph 3: `Network1.Interface` surfaced in status/enum; `/sys/class/net` operstate/carrier/mtu still pending) |
| E5 | **`Network1` PropertiesChanged subscription** — event-driven Connected/Interface/UUID via the signals aggregator; persist through `upsert_pan_access`; keep the 0.5 s poll as a timeout fallback. | `connection.c:114-119,217-222`; `bleep/signals/` | ✅ RESOLVED (Ph 4: `NetworkMonitor`, ops `monitor()`, `classic-pan monitor`; persists via `upsert_pan_access`) |
| E6 | **Accept full 128-bit UUID role strings** (API fidelity vs `_VALID_ROLES`). | `connection.c:71-81`; `Network.rst:29-42` | Ph 2 ✅ |
| E7 | **Server-side incoming-connection authorization via Agent** — observe/authorize inbound BNEP clients (`AuthorizeService` for `BNEP_SVC_UUID`) while hosting a NAP. | `server.c:457` `btd_request_authorization`; `bleep/dbuslayer/agent*.py` | ✅ RESOLVED (Ph 4: `register_pan_agent()` + `serve --authorize`, logs/accepts inbound BNEP, GLib loop + agent teardown) |
| E8 | **Local `NetworkServer1` + advertised-role reporting** in enumeration (which roles the host advertises via SDP 0x1115/6/7). | `manager.c:64-119`; SDP query | ✅ RESOLVED (Ph 3: `find_network_servers()` reports `has_networkserver` + adapter PAN role UUIDs) |

### Phased plan (each phase is additive and independently acceptable)

- [x] **Phase 0 — Boundary documentation — COMPLETE (2026-07-12).** Added the
      "Networking capability boundary (G9)" note to `bl_classic_mode.md` §2.9
      (D-Bus reaches only `Network1`/`NetworkServer1`; BNEP filters, `bnepX`
      netdev, and `network.conf` are unreachable; no 6LoWPAN/IPSP). Captured a
      live baseline via `check_network_capabilities.py --json`: adapter `hci0`
      exposes `NetworkServer1`; device `98:3B:8F:EF:FE:EC` (DESKTOP-1APRSIB)
      exposes `Network1` and advertises the **PANU** UUID. (The old script
      reported empty `network_uuids` due to a case-sensitivity bug fixed in
      Phase 3.)
- [x] **Phase 1 — Prerequisite detect-and-instruct preflight (G2, part of E4) — COMPLETE (2026-07-12).**
      - Add PAN prerequisite checks to `bleep/core/preflight.py` (reuse existing
        module; DRY): `bnep` kernel module (`/proc/modules` + `/sys/module/bnep`),
        adapter ready (reuse `require_adapter`), and — for `serve` — bridge
        existence + type (`/sys/class/net/<bridge>/bridge`) and IPv4 forwarding
        (`/proc/sys/net/ipv4/ip_forward`). **Detect-and-instruct only — never
        mutates host networking.** Returns a `PanPrereqReport` dataclass with an
        `instructions()` remediation list (mirrors `pan_connection_analysis.md:273-281`).
      - Add `--no-preflight` to `classic-pan connect` / `serve` (parser).
      - Wire into `run_pan()` connect/serve: print the summary, **non-blocking**
        (warnings only; existing success behaviour unchanged).
      - Tests: `tests/test_network_pan.py` — `/proc/modules` parsing, bridge/
        forwarding probes (monkeypatched), and `PanPrereqReport` logic.
      - Docs: `changelog.md` + `bl_classic_mode.md` §2.9 note; update
        `pan_connection_analysis.md` §5.1 ("Not checked by BLEEP" → "checked").
- [x] **Phase 2 — Connect-path correctness (G3, G6, G7; E1, E3, E6) — COMPLETE (2026-07-12).**
      - **G6/E6 — role fidelity** (`dbuslayer/network.py`): added
        `normalize_pan_role()` + `pan_role_uuid()`; both `panu`/`nap`/`gn`
        short names (case-insensitive) *and* full 128-bit PAN UUIDs are now
        accepted and normalised to the short form BlueZ prefers. Wired into
        `NetworkClient.connect`, `NetworkServer.register/unregister`, and the
        ops layer.
      - **G7 — error consistency** (`dbuslayer/network.py`): replaced every bare
        `RuntimeError`/`ValueError` with `core.errors.map_dbus_error(...)` (D-Bus
        failures), `ConnectionError` (post-connect BNEP verification), and
        `InvalidArgumentError` (bad role). `except Exception` callers unaffected
        (all are `BLEEPError` subclasses).
      - **G3/E3 — bond/trust/SDP precheck** (`ble_ops/classic/pan.py`
        `_precheck_pan_target`): advisory, non-fatal warnings if the target is
        not paired or does not advertise a PAN service (via `detect_pan_service`
        over `Device1.UUIDs`); opt-in `ensure_trusted` (`--trust`) marks the
        device Trusted. Never mutates host state otherwise.
      - **E1 — ConnectProfile fallback** (`ble_ops/classic/pan.py`
        `_connect_via_profile`): on `Network1.Connect`→`NotSupported`, retries
        via `Device1.ConnectProfile(<pan-uuid>)` (drives bluetoothd SDP probe +
        profile registration), then polls `Network1` for the interface. Toggle
        with `--no-fallback`.
      - CLI: `classic-pan connect` gains `--trust` and `--no-fallback`; wired
        through `run_pan()`.
      - Tests (`tests/test_network_pan.py`, +23): `normalize_pan_role` /
        `pan_role_uuid` (short + full UUID + invalid), and `connect()`
        orchestration (normal path, `NotSupported`→fallback, `--no-fallback`
        re-raise, UUID-role normalisation, invalid-role early reject) — all
        D-Bus-free via monkeypatched `NetworkClient`.
- [x] **Phase 3 — Enumeration + device-class integration (G1, G4; E4, E8) — COMPLETE (2026-07-12).**
      - Additive device-class helpers `get_network_roles()` / `has_network_uuids()`
        / `get_network_status()` / `has_network_interface()` / `is_network_device()`
        on **both** `device_classic.py` and `device_le.py` (dual-mode), mirroring
        the media-capability pattern.
      - Shared module helpers in `ble_ops/classic/pan.py`:
        `network_roles_from_uuids()`, `find_network_servers()`,
        `find_network_devices()` — all accept a pre-fetched `GetManagedObjects`
        (single fetch threaded through; no D-Bus storms), read `Network1` status
        from the snapshot (E4-style), and never raise.
      - One **additive** `network` key in `get_device_info()` on both classes.
      - New top-level `network-enum` CLI command (`cli/parsers/classic.py`) +
        `run_network_enum()` (`modes/classic_profiles.py`) + dispatch
        (`cli/dispatch.py`); `--adapter` / `--json` / `--all-devices` flags.
      - `scripts/check_network_capabilities.py` refactored to a thin wrapper over
        the shared ops — **and fixed a latent case-sensitivity bug** (old script
        lowercased UUIDs vs upper-case keys → always-empty `network_uuids`).
      - Tests: `tests/test_network_pan.py` (+12, 65 total) over a fixture
        `GetManagedObjects` (adapter ±`NetworkServer1`; device with `Network1`
        but no PAN UUID; UUID-only device w/ Alias fallback; non-network device
        filtered; adapter path filter).
      - **Non-disruption safeguards honoured:** (a) `check_device_type()`
        unchanged; (b) survey does not consume `get_device_info()` (uses its own
        `DeviceSighting`/`SurveyCensus`) — verified, so the additive `network`
        key cannot perturb survey snapshots; (c) lazy imports (no cycles);
        (d) single `GetManagedObjects` fetch; (e) helpers falsy-on-error;
        (f) purely additive — existing `classic-pan` behaviour unchanged.
- [x] **Phase 3b — Multi-role server (E2) — COMPLETE (2026-07-12).**
      `NetworkServer` tracks `{role: bridge}` (`registered_roles`), adds
      `unregister_all()` (best-effort, continues past failures) and drops a role
      from tracking even when its Unregister errors. Ops `register_servers()`
      (returns the live server, rolls back partial registration) /
      `unregister_servers()` (out-of-process best-effort) +
      `PAN_SERVER_ROLES=("nap","gn","panu")`. CLI `serve`/`unserve` take a
      repeatable `--role` and `--all`; `serve` guarantees `unregister_all()` in a
      `finally`. Tests: +14 (79 total).
- [x] **Phase 4 — Real-time signals + server authorization (G8; E5, E7)**:
      COMPLETE. `NetworkMonitor` (`dbuslayer/network.py`) subscribes to `Network1`
      `PropertiesChanged` (pure `_apply_change` merge core; `prime()` GetAll seed;
      `wait_for`/`run` GLib loop). `NetworkClient.connect` verify is now
      event-driven (`_verify_connected`) with the 0.5 s poll as fallback (**G8**).
      Ops `monitor()` + CLI `classic-pan monitor` stream live changes and persist
      to the obs DB (**E5**). `register_pan_agent()` + `serve --authorize` register
      a default agent so inbound BNEP clients hit `AuthorizeService`
      (`BNEP_SVC_UUID`) and are logged/accepted; GLib loop + guaranteed agent
      teardown (**E7**). Scripted peer `scripts/pan_peer.py` (connect/serve/monitor)
      for two-node testing. Tests: +19 (98 total).
- [ ] **Phase 5 — Test suite & parity (G5; spans all phases)**: see below.

### Testing & validation strategy

1. **Unit (mock D-Bus, CI-safe)** — `tests/test_network_pan.py`: role→UUID
   mapping, single-`GetAll` status snapshot, mapped-error paths,
   `detect_pan_service()` matching, preflight probes (monkeypatched `/proc`,
   `/sys`), enumeration over fixture `GetManagedObjects` with/without `Network1`.
2. **Integration (hardware, `@pytest.mark.hardware`)** — PANU→NAP phone
   (Android tethering on): assert `bnep0` in `ip addr` and `Connected=True`;
   `serve` + second host. Cross-check against `workDir/BlueZScripts/test-network`
   and `test-nap` to isolate BLEEP bugs from BlueZ/remote behaviour
   (`pan_connection_analysis.md:317-323`).
3. **Negative** — non-PAN device→`NotSupported`; double `serve` same role→
   `AlreadyExists` (`server.c:550-551`); `disconnect` when idle→`NotConnected`
   (`connection.c:374`).
4. **Regression** — full `pytest` green after every phase; no change to existing
   snapshots/parity unless explicitly re-baselined.

### Future Work — Option B (deferred; documented for fidelity)

**B1 — Raw L2CAP/BNEP stack** (only if BNEP-filter fuzzing/security testing is
required): raw `BTPROTO_L2CAP` socket to PSM `0x000F`, OMTU/IMTU 1691
(`connection.c:325-333`, `lib/bnep.h:66-73`); BNEP setup req/rsp
(`struct bnep_setup_conn_req`, `lib/bnep.h:79-84`; parser ref `server.c:294-381`);
filter control msgs (`lib/bnep.h:46-49,86-91`, resp `:59-63`); kernel session
ioctls (`lib/bnep.h:112-143`) to materialize/inspect `bnepX`; packet types +
ext-header bit (`lib/bnep.h:35-40,75-77`). **Conflicts with bluetoothd's
`network` plugin** (both bind PSM 0x0F / manage `bnepX`); must be a dedicated,
root-gated, opt-in module isolated from the D-Bus path. Own PRD/epic.

**B2 — NAP host auto-setup** (eventual goal after Phase 1 detect-and-instruct):
opt-in `--auto-setup` on `classic-pan serve` that (behind an explicit flag, with
guaranteed teardown) creates the bridge (`ip link add … type bridge`), enables
`net.ipv4.ip_forward`, adds a WAN MASQUERADE rule, optionally starts `dnsmasq`
DHCP on the bridge, and restores all of it on exit (pairs with the existing
`signal.pause()` teardown in `classic_profiles.py:450-470`). Root-only; must
respect dev/test/prod separation; never mutates host networking without the flag.

### Citation index (for manual verification)

- API surface: `workDir/bluez/doc/org.bluez.Network.rst`, `org.bluez.NetworkServer.rst`; `profiles/network/connection.c:481-498`; `server.c:642-650`
- Roles / PSM / MTU: `lib/bnep.h:31-33,66-73`
- Optimistic connect reply (async setup): `connection.c:136-232`
- Client has no caller-disconnect watch; server does: `connection.c:53-99` vs `server.c:564-566` (analysis `pan_connection_analysis.md:37-99`)
- Server SDP record (IPv4/ARP, security_desc): `server.c:142-266`
- `network.conf` security is bluetoothd-side: `manager.c:36-62`
- BNEP filters/ioctls unreachable via D-Bus: `lib/bnep.h:43-63,111-116`
- `Device1.ConnectProfile/DisconnectProfile`: `org.bluez.Device.rst:72,86`; wrapper `device_classic.py:695,739`
- No 6LoWPAN/IPSP in tree: scoped `grep` → none

---

## Multi-Target Enumeration Hardening (2026-07-10) — Accepted Fix Plan & Implementation Tracker

> **STATUS (2026-07-10): IMPLEMENTED.** Gate 1 (#1,#3,#4,#6,#8,#13,#14,#15,#16), Gate 2
> (#5,#10,#11,#12), Gate 4 (#9,#2) and **Round-2 retest follow-ups (#7/N1, N2, N3, N4, N6)**
> are complete, live-verified, and regression-checked (full `pytest` = 1181 passed /
> 27 skipped / 1 pre-existing unrelated failure). **Still open:** #5 deeper root-cause repro
> (deferred, destructive), #2/#9 correlation-success live capture (needs an advertising RPA twin).
> #17 withdrawn. Changes are unstaged/uncommitted pending review. See `changelog.md`
> ("Multi-Target Enumeration Hardening" + "… Round 2").

**Context**: A multi-target enumeration campaign (`python3 -m bleep …` only; no `bleep-mcp`,
no DB-derived findings) against the `winbt-honeypot` (`98:3B:8F:EF:FE:EC` + LE RPA
`47:23:78:E6:8A:16`), BLECTF (`CC:50:E3:B6:BC:A6`), and a Philips Hue bulb
(`F0:98:7D:0A:05:07`) surfaced 17 gaps. Each proposed fix was reviewed for detrimental
side-effects and **cross-validated against BlueZ source** (`workDir/bluez/`, v5.83; target
runs 5.79 — relevant paths identical). This validation **corrected 6 of the original
assumptions** before any code change. This section is the authoritative, follow-along
record. Severity: **P1** broken feature · **P2** wrong/misleading result · **P3** polish.

**Governing rules for this work**: reuse existing structures over new subsystems; each
issue is an isolated, independently-revertable commit; no destructive changes; full
`pytest` + per-issue live-device verification per change; reference `workDir/bluez/`,
`workDir/BlueZScripts/`, `workDir/BlueZDocs/` for protocol ground-truth.

### BlueZ cross-validation — corrected assumptions (read before implementing)

| # | Original assumption | BlueZ source verdict | Corrected direction |
|----|---------------------|----------------------|---------------------|
| #2 | Modify shared `find_device_path` to correlate BR/EDR↔RPA | `find_device_path` has 8+ callers; `Device1` exposes `AddressType`/`Modalias` (`device.c:3586/3604`) but `Modalias` needs a DID record (often absent) | Leave `find_device_path` strict. New **opt-in** `correlate_le_identity()` preferring `Name`/`Icon`, behind `--correlate` (default off). |
| #4 | Encryption/auth reads arrive as `Failed: ATT error: 0x0f` | **FALSE.** `gatt-client.c:281-306`: ATT `0x05/0x0c/0x0f`→`NotPermitted "Not paired"`; `0x08`→`NotAuthorized`; only unhandled/app codes + neg-errno→`Failed "…ATT error: 0x%02x"` | Detect `NotPermitted`+`"Not paired"`→`requires_encryption`; parse `Failed: ATT error: 0xNN` for the real `unknown_failure` cause; fix pre-existing `0x03`→write mislabel. |
| #5 | Root cause = `remove_stale_bond` RPA substitution | `find_device_path` matches strictly on `Address`; mechanism unexplained by code | Add defensive `Address==requested` guard (safe now); **reproduce** before any deeper change. |
| #7 | Socket leak — add `finally: close()` | `rfcomm.py:97-102` already closes in `finally`; `ENOMEM` is kernel ACL exhaustion (raw socket, not D-Bus) | **DONE (Round 2/N1).** Corrected location: the failing loop is `pairing/__init__.py:415-429` → `classic_rfccomm_open`. Bounded `ENOMEM`-only retry + linear back-off added *inside* the `classic_rfccomm_open` primitive (`ble_ops/classic/connect.py`), benefiting all callers; other errno unchanged. |
| #9 | `naggy` breaks out of retry on `br-connection-*` | `connect.py:279-298` already treats `.Failed` (which carries `br-connection-*`, `error.c:138-184`) as retryable | **Reproduce** with `BLEEP_LOG=DEBUG` to find the actual escape path; no blind loop edit. |
| #17 | `bleep` shells to `bluetoothctl disconnect` and hangs | Only real call is `error_handling.py:36` `controller_stall_mitigation` — intentional fallback *because* D-Bus is stalled | **WITHDRAWN** (working as intended; hang was manual/interactive). |

### Gate 1 — Tier A: confirmed root cause, safe additive fixes

- [x] **#1 (P1)** `hid-info`/`connect-profile` crash — `cli/dispatch.py:271` & `:290` pass
      `bluetooth_adapter=adapter_name`; constructor is `system_dbus__bluez_device__classic(mac, adapter_name)`.
      *Fix*: rename kwarg → `adapter_name=adapter_name` at both call sites. 2 lines, no signature change.
      *Test*: `hid-info <mac>` and `connect-profile <mac>` no longer raise `TypeError`.
- [x] **#4 (P2)** Auth/encryption reads mis-/un-classified — BlueZ-accurate rewrite.
      *Sites*: `dbuslayer/characteristic.py:564-581` (`safe_read_with_retry._ERR_MAP`, deep path),
      `dbuslayer/device_le.py:1099-1106` (non-deep `_ERR_MAP`) + `:1028-1054` (`_classify_read_errors`),
      `bt_ref/constants.py:247-294` (append `RESULT_ERR_INSUFFICIENT_ENCRYPTION = 41`).
      *Fix*: (a) message-aware `NotPermitted`: `"Not paired"`→encryption, `"Write not permitted"`→write,
      else read; (b) parse `org.bluez.Error.Failed` `"ATT error: 0x([0-9a-fA-F]{2})"` → label by ATT
      code (`0x0e`unlikely, `0x11`insufficient-resources, `0x80+`app-error) instead of `unknown_failure`;
      (c) add classifier branch for the encryption code. Additive; unknown messages keep existing default.
      *Test*: `gatt-enum --deep <hue>` → vendor chars `requires_encryption`, not `unknown_failure`;
      BLECTF regression: previously-classified codes unchanged.
- [x] **#3 (P1)** `gatt-enum` "already connected → skip" emits empty tree with exit 0.
      *Sites*: skip at `device_le.py:254-264`; wrapper `modes/gatt_enum.py`.
      *Fix*: in `gatt_enum.py`, if resolved `mapping`/`_services` empty → warn (hint at Classic-only /
      RPA GATT / `--correlate`) and return non-zero. Additive post-check; connect primitive untouched.
      *Test*: `gatt-enum <classic-connected dual>` → warning + `$? != 0`.
- [x] **#6 (P2)** `pair --probe` misreports pre-existing bonds (`AlreadyExists`, `error.c:41`).
      *Site*: `modes/pair.py:128-168` `_do_probe` (`check_pair_status` already imported).
      *Fix*: pre-check `check_pair_status(mac)`; if bonded, short-circuit "already bonded — reset to re-probe".
      *Test*: `pair --probe <bonded>` reports bond, skips capability sweep.
- [x] **#8 (P2)** SDP version inference mislabels profile versions as core-spec.
      *Sites*: `analysis/sdp_analyzer.py:191-266` (`_infer_version`), `:408-420` (render); `cross_validate_lmp:324`.
      *Fix*: when HCI/LMP remote version present, present it as authoritative Core Spec; relabel SDP section
      "Profile versions (not core spec)"; stop mapping profile versions onto core-spec numbers. Reuse existing table.
      *Test*: `classic-enum --version-info --analyze <honeypot>` → Core Spec = BT 4.2 (HCI); no "Bluetooth 1.9".
- [x] **#13 (P3)** `classic-connect` exit 0 when all RFCOMM channels fail.
      *Site*: `modes/classic_connect.py` `run()` returns. *Fix*: return `1` on the no-channel-succeeded branch.
      *Test*: `classic-connect <all-fail>`; `echo $?` == 1.
- [x] **#14 (P3)** CTF Flag-04 `char0015` translation failure.
      *Sites*: `ble_ops/le/ctf.py:41-44` (hardcoded map), `:178-265`/`:338-395` (translate → raise).
      *Fix*: before raising, fall back to enumerated `ble_device__mapping` handle→UUID. Additive.
      *Test*: `ctf --discover <blectf>` → Flag-04 resolves, no translate error.
- [x] **#15 (P3)** `classic-ping --timeout` not wired to `l2ping -t` (BlueZ `l2ping.c:259/291`, default 10s).
      *Site*: `ble_ops/classic/ping.py:28` builds `["-c", count, mac]`. *Fix*: insert `["-t", str(timeout)]`;
      keep subprocess timeout as hard cap. *Test*: `classic-ping --timeout 3 <mac>` → `-t 3` in invocation (debug log).
- [x] **#16 (P3)** `classic-opp --save-dir` must precede positional. *Fix*: attach `--save-dir` to OPP
      subparser(s) so `classic-opp <addr> pull --save-dir X` parses. *Test*: that invocation no longer errors.

### Gate 2 — #5 defensive guard + Tier C display polish (low risk)

- [x] **#5 (P2)** Pairing safety guard — `modes/pair.py:300-317`: after `remove_stale_bond`, require
      resolved path `Address == requested mac` (and transport); else abort "requested `<mac>` did not
      re-appear (found `<x>`) — refusing to pair a different identity". Safe regardless of root cause.
- [x] **#10 (P3)** Tag stale/bonded vs freshly-advertised entries in `ble_ops/le/scan.py` via BlueZ
      `RSSI`-present check (`[cached/bonded]`).
- [x] **#11 (P3)** `RSSI: ? dBm` for freshly-seen devices — unify on the shared prop collector.
- [x] **#12 (P3)** RPA mislabeled `AddressType: public` — read/propagate BlueZ `AddressType`
      (`device.c:3586`, values `random`/`public` `:1009-1011`) in the info collector.

### Gate 3 — reproduction before code (deliver evidence + refined design for approval)

- [x] **#2 (P1)** Dual-mode LE GATT unreachable via requested identity — correlator confirmed on the
      honeypot (Name/Icon/Class match; Modalias public-only → unreliable). Opt-in `correlate_le_identity()`
      designed and implemented in Gate 4.
- [~] **#5 root cause** Defensive identity guard implemented (Gate 2). Definitive DEBUG repro of the RPA
      selection deferred — requires a destructive controlled bonded dual-mode `pair --reset`→`pair` cycle.
- [x] **#9 (P2)** Root cause confirmed via `BLEEP_LOG=DEBUG`: transient `br-/le-connection-*` mapped to a
      base `BLEEPError` that escaped the naggy `except (ConnectionError, ServicesNotResolvedError)` loop.
      Fixed in Gate 4.

### Gate 4 — implement #2 correlation + #9 fix (IMPLEMENTED 2026-07-10, post Gate-3 sign-off)

- [x] **#9** targeted fix at the confirmed escape site, reusing the existing `--retries` count.
  - **File/edit:** `core/errors.py:map_dbus_error`, `org.bluez.Error.Failed` branch. Added a
    substring test mapping the **transient** connection-family strings
    (`connection-canceled`, `connection-timeout`, `connection-busy`, `connection-abort`,
    `connection-unknown` — canonical strings verified against `workDir/bluez/src/error.h`
    `ERR_{BREDR,LE}_CONN_*`) to `ConnectionError`. **Permanent** variants
    (`not-supported`, `key-missing`, `bad-socket`, `adapter-not-powered`, `invalid-arguments`)
    intentionally fall through to the base `BLEEPError` (fail fast — no wasted retries).
    `connection-refused` remains `ConnectionRefusedError` (unchanged). No `connect.py` control-flow change.
  - **Unit verify:** `tests/test_core_errors_transparency.py` — 10 transient params → `ConnectionError`,
    5 permanent params → base `BLEEPError`. All pass.
  - **Live verify:** `explore 98:3B:8F:EF:FE:EC --conn-mode naggy --retries 4` — debug log now shows
    `le-connection-abort-by-local` on inner attempt 1/2, recovers on 2/2, enumerates 7 svc / 44 chr,
    **exit 0** (previously escaped the retry loop → exit 1). Passive path still bounded (max_attempts=1,
    no infinite loop) since ConnectionError increments `attempt` and respects the cap.
- [x] **#2** opt-in `correlate_le_identity()` + `--correlate` flag on gatt-enum dual-mode fallback.
  - **New module:** `ble_ops/le/correlate.py::correlate_le_identity(target_mac, *, adapter=None)` —
    reuses `adapter.get_discovered_devices()` (no new D-Bus). Ranks candidates by Name (required) +
    Icon + Class + random-addr-type → confidence high(≥3)/medium(2)/low(1). Read-only, non-merging;
    refuses to guess when target has no Name; excludes self.
  - **CLI:** `--correlate` flag added to `gatt-enum` (`cli/parsers/gatt.py`), default off.
  - **Wiring:** `modes/gatt_enum.py` — when the requested address resolves no GATT (empty tree **or**
    `ServicesNotResolvedError`) **and** `--correlate` is set, correlate and re-enumerate against the top
    LE candidate; results are clearly labelled as a heuristic correlation and persisted/displayed under
    the effective (correlated) address. Without `--correlate`, `ServicesNotResolvedError` propagates
    unchanged (verified identical default behaviour). Never auto-merges.
  - **Unit verify:** `tests/test_le_correlate.py` (7 tests) — high/low confidence, self-exclusion,
    no-Name refusal, unknown-target empty, non-matching-name excluded, score ranking. All pass.
  - **Live verify:** honeypot has no RPA twin advertising a matching Name at test time, so `--correlate`
    correctly reports "no LE candidate matched … nothing to retry" and preserves the original failure
    (exit 1) — validating the **no-false-merge** path. Default (no `--correlate`) run confirmed unchanged.
- **Regression:** full `pytest` = **1165 passed, 27 skipped, 1 failed**. The single failure
  (`test_aoi_augmentation.py::test_schema_version_is_15`, expects 15 vs actual 16) is the pre-existing
  schema-version drift, unrelated to Gate 4 (no observations-schema code was touched).

### Round 2 — post-retest follow-ups (IMPLEMENTED 2026-07-10, accepted)

A full functional re-test of the Round-1 fixes against all in-range targets surfaced five
follow-ups (N5 excluded — a known BLECTF advertising artifact per user). Each was
cross-validated against `workDir/bluez/`, `workDir/BlueZDocs/`, `workDir/BlueZScripts/`.

- [x] **N1/#7 (P1)** RFCOMM `ENOMEM` (`[Errno 12]`) on every channel during `classic-connect`.
  - **Root cause:** rapid successive `sock.connect()` opens exhaust host/controller memory.
    Location corrected from the tracker's original note: the loop is `pairing/__init__.py:415-429`
    calling `ble_ops/classic/connect.py::classic_rfccomm_open` (which already closes on error).
  - **Fix:** bounded `ENOMEM`-only retry (`enomem_retries=2`) + linear back-off
    (`enomem_backoff=0.3`) inside `classic_rfccomm_open`, recreating the socket each attempt;
    all other errno raise immediately (unchanged).
  - **BlueZ validation:** `errors.txt:70-74` (ENOMEM = host/controller alloc failure — transient),
    `src/error.c:163` (`ERR_BREDR_CONN_MEMORY_ALLOC`, distinct from permanent EOPNOTSUPP/EINVAL),
    `tools/rctest.c:602-628` (reconnect pacing).
  - **Verify:** `tests/test_rfcomm_enomem.py` (retry-then-succeed / exhaust-and-raise /
    non-ENOMEM-immediate). Live: back-off engaged on 3 channels; terminal error changed
    ENOMEM→`EACCES` (more informative).
- [x] **N2 (P3)** `--analyze` NOTE misadvised "Add --version-info" even when it was supplied but
  the remote HCI Read Remote Version returned nothing. `query_remote_version` returns `None` on
  failure (30 s `hcitool info` timeout). Added `version_info_requested` to
  `sdp_analyzer.generate_report`; wired `version_info_mode` from `classic_enum.py`. Display-only.
  Live NOTE now: "remote HCI/LMP version query returned no result (device refused / did not ACL-connect)".
- [x] **N3 (P3)** `classic-connect` count wording: `rfcomm_count` (services-with-channel, 8) vs the
  de-duplicated distinct channels attempted (`pairing/__init__.py:409-412`, 5). Now reports both
  quantities consistently in the summary and failure lines.
- [x] **N4 (P3, corrected)** Scan "duplicate" is **two real objects** — the public path and the
  bonded RPA path, both reporting the identity `Address` (`org.bluez.Device.rst:226`, "Identity
  Address after pairing"). A dedup would have hidden the RPA↔identity linkage (the #2 signal), so
  `ble_ops/le/scan.py` instead appends `[identity; adv/RPA <path-mac>]` when the path MAC differs
  from the resolved `Address`. Live: the two honeypot lines are now distinguishable.
- [x] **N6 (test)** Added `tests/test_gatt_error_classifier.py` (13 cases) for the canonical
  `classify_gatt_read_error` (#4), which previously had no dedicated unit coverage.
- **Regression:** full `pytest` = 1181 passed / 27 skipped / 1 failed (pre-existing
  `test_schema_version_is_15` drift, unrelated).

### Gate 3 reproduction evidence (captured 2026-07-10, live devices — awaiting sign-off for Gate 4)

**#9 — ROOT CAUSE CONFIRMED (was "reproduce first").** Repro:
`python3 -m bleep explore 98:3B:8F:EF:FE:EC --conn-mode naggy --retries 4` → exits `1`
immediately after the inner `device.connect(retry=2)` attempts, with **no** outer
"Attempt X/max failed, retrying" line. Debug (`/tmp/bti__logging__debug.txt`) shows inner
"Connect attempt 1/2" + "2/2", both `org.bluez.Error.Failed: br-connection-canceled`.
Trace: `dbuslayer/device_le.py:417-433` — `br-connection-canceled` is **not** treated as
transient (message lacks "Software caused connection abort", not `OperationInProgressError`),
so after `retry` it `raise mapped`. `core/errors.py:map_dbus_error` (285-300): name
`org.bluez.Error.Failed` + msg `br-connection-canceled` matches **no** substring branch →
returns a **base `BLEEPError`** (line 300). The naggy outer loop in `ble_ops/le/connect.py`
only catches `dbus.exceptions.DBusException` (246/279) and `(ConnectionError,
ServicesNotResolvedError)` (300) — a base `BLEEPError` matches none, so it escapes the retry
loop entirely and reaches the CLI. Naggy's persistent retries never engage.
- **Proposed Gate 4 fix (minimal, root-cause):** in `core/errors.py:map_dbus_error`, map the
  transient `br-connection-*` / `le-connection-*` variants (`canceled`, `-timeout`, `busy`,
  `aborted`) under `org.bluez.Error.Failed` to `ConnectionError` (a `BLEEPError` subclass) so
  the existing `except (ConnectionError, ServicesNotResolvedError)` retry path engages and
  honours `--retries`/backoff. Reuses existing retry logic; `except BLEEPError` callers and
  `.code` are unaffected (ConnectionError ⊂ BLEEPError). No change to `connect.py` control flow.

**#2 — correlator confirmed present but heuristic-only (design validated).** Live `Device1`
props (read-only) for the two identities of the honeypot:
- Public `98:3B:8F:EF:FE:EC`: `Name=DESKTOP-1APRSIB`, `Icon=computer`, `Class=3031308`,
  `Modalias=bluetooth:v0006p0001d0A00`, `AddressType=public`.
- LE RPA `47:23:78:E6:8A:16`: `Name=DESKTOP-1APRSIB`, `Icon=computer`, `Class=3031308`,
  **no Modalias**, `AddressType=public` (BlueZ mislabels the RPA — see F7).
- Findings: (a) `Name`/`Icon`/`Class` match → a correlator exists; (b) `Modalias` is present
  **only** on the public address → confirms it is unreliable for cross-address correlation;
  (c) `DESKTOP-1APRSIB` is a **default Windows hostname** → Name/Icon/Class are heuristic and
  would **false-merge** two distinct default-named Windows hosts. **Conclusion: keep #2
  strictly opt-in (`--correlate`, default off), presented as a derived hint, never auto-merge.**

**#5 — defensive guard implemented (Gate 2); deeper root cause still needs a controlled repro.**
The address-match guard now aborts any pair whose resolved path ≠ requested MAC, so the
observed RPA-substitution is *safe regardless of root cause*. A definitive root-cause repro
requires a controlled bonded dual-mode `pair --reset`→`pair` cycle with target-side input,
which is destructive; deferred. `find_device_path` matches strictly on `Address`, so the
substitution most likely occurred when the requested public MAC failed to re-appear post
bond-removal and a caller fell back to a rescan hit — the guard blocks exactly this.

### Verification & acceptance gates

Baseline `pytest` captured before edits; re-run after each change (compare deltas). Static guards:
`scripts/verify_no_legacy_device_imports.py`, import smoke of touched modules, `git diff --stat` scope check.
Regression focus: #2/#5 must not alter strict single-mode resolve; #4 must not reclassify existing
NotPermitted/NotAuthorized codes on BLECTF; #8 must still render the profile section without HCI data.
Each Gate requires sign-off before the next.

---

## Target `98:3B:8F:EF:FE:EC` Re-Enumeration Audit (2026-07-10) — Findings & Decisions

**Context**: Re-enumeration of the `winbt-honeypot` (`DESKTOP-1APRSIB`) with the
post-2026-07-09 tooling. Prior fixes verified working live. New findings scrutinised
against **today's** data only (older artifacts excluded per reviewer instruction).
This entry records decisions; implementation of accepted items is tracked by their
checkboxes.

**Decision log**

| ID | Finding | Disposition | Decision |
|----|---------|-------------|----------|
| F1 | LE RPA identity fragmentation (rotating resolvable private addresses → new device row per session) | Confirmed (mechanism inherent to BLE privacy) | **ACCEPTED — non-merging.** Near-term presentational aids only; identity correlation **deferred** (see Future Work). |
| F2 | Classic `sdp_records` row growth on the stable public MAC | Confirmed; also a latent **destructive overwrite** for stable-handle records (`ON CONFLICT … DO UPDATE`) | **ACCEPTED — Option C+ (append-only / versioned SDP snapshots).** Non-destructive: never overwrites; appends a new timestamped snapshot only when service content changes (identical re-observations skipped). Requires schema **v16** (drop `UNIQUE(mac, service_record_handle)`) + append-only write. |
| F3 | Classic Service Map / RFCOMM table show unresolved short UUIDs (`0x111F`) | Confirmed (today's data) | **ACCEPTED** (display-only name resolution). |
| F5 | `scan -d` "No devices" message cannot distinguish "none found" from "none matched filter" | Confirmed (verbatim) | **ACCEPTED** (display-only). |
| F4 | Empty SDP record (`? ch=None`) | **RETRACTED** — stale (no empty rows generated today; fixed 2026-07-09). | No action. |
| F6 | `br-connection-create-socket` connect variant | Environmental (BlueZ), non-fatal | Documentation only. |
| F7 | BlueZ reports `AddressType: public` for a structurally-random LE address | Environmental (BLEEP faithfully echoes BlueZ) | Documentation only. |

### F1 — LE RPA identity fragmentation (ACCEPTED: non-merging)

**Rationale**: Without the peer's IRK (exchanged only during bonding), two RPAs
cannot be soundly linked to one identity. Heuristic merging (e.g. by name +
manufacturer-data) is unsafe — `DESKTOP-1APRSIB` is a *default Windows hostname*, so
two distinct laptops would be wrongly fused. A true RPA hash collision is
astronomically rare; the practical hazard is heuristic false-merge. Therefore the
near-term response is **strictly non-merging**.

**Near-term aids (non-merging, presentational/query-side — IMPLEMENTED 2026-07-10):**
- [x] `db list`: emit a truncation notice when the returned page equals `--limit`,
      hinting at `--limit/--offset` (and `--name`), so RPA-inflated counts are not
      mistaken for hidden/lost devices. Implemented as a page-fill heuristic
      (`db.py:list_devices`) — no total count `M` is shown (deliberately avoids a
      second `COUNT` query / duplicating the filter logic); the notice states
      "more may exist". Pagination pre-existed; no data is dropped.
- [x] `db list --name <substr>`: name filter (`name LIKE ?`, qualified `d.name` on the
      media JOIN path) in `get_devices()` (`_devices.py`), wired through `db.py` and both
      db parsers, so an analyst can enumerate all RPA identities of one named device in a
      single command.

**Future Work (DEFERRED — out of current scope):**
- [ ] IRK-based RPA identity resolution/correlation. Requires bonding/identity-key
      material and cryptographic RPA resolution (`ah(IRK, prand)`); must **not** use
      name/manufacturer-data heuristics. Edge case to design against: distinct devices
      that share a default name/manufacturer-data (false-merge) and, far less likely, a
      genuine RPA hash collision. Any correlation must be presented as a *derived view*
      that never mutates or merges the underlying per-address observation rows.

### F2 — Classic SDP row growth (ACCEPTED — Option C+, append-only/versioned)

**Reviewer requirement (recorded):** the observation DB must **capture
changes/alterations over time** with full fidelity; **no destructive choices**.

**Root cause (verified today):** two drivers, neither RPA-related (SDP is Classic on
the stable public BD_ADDR):
1. NULL `service_record_handle` defeats `ON CONFLICT(mac, service_record_handle)`
   (SQLite treats NULLs as distinct), so every enumeration re-inserts — observed on
   ordinary phones (`78:ED…`=211 rows, `64:A2…`=180) not just the honeypot.
2. For **stable, non-NULL** handles the conflict fires and `DO UPDATE`
   **overwrites in place** (`_services.py:297-309`) — a latent *destructive* loss of
   change history for well-behaved devices, which violates the DB's stated purpose.

**Accepted solution — Option C+ (append-only / versioned):**
- [x] **Schema v16** (`_connection.py`): rebuild `sdp_records` **without**
      `UNIQUE(mac, service_record_handle)`; add a non-unique index on
      `(mac, service_record_handle)`. Migration preserves all existing rows. Bump
      `_SCHEMA_VERSION` 15 → 16; update the base DDL for fresh DBs.
- [x] **Append-only write** (`upsert_sdp_record`, `_services.py`): replace the
      `ON CONFLICT … DO UPDATE` overwrite with a plain `INSERT` that appends a new
      timestamped snapshot **only when the record content changed** vs the latest
      snapshot for the same logical service (identity = `mac + uuid + channel`;
      comparison excludes the volatile `service_record_handle`, `ts`, and `raw_record`
      to avoid pure-noise rows while capturing every genuine alteration). Never
      UPDATEs, never DELETEs.
- **Fidelity guarantees:** all prior snapshots retained and exported in full via
      `get_device_detail` / `db export` (`_devices.py:305`, no LIMIT); `db show`
      continues to collapse to the latest snapshot per `(uuid, channel)` for
      readability (T2-2, display-only). Identical re-observations no longer bloat the
      table; genuine changes are versioned by `ts`.

**Future Work (non-destructive, DEFERRED):**
- [ ] `db timeline`-style SDP change view so the retained per-`ts` snapshot history is
      directly examinable from the CLI (currently via `db export`).

### Accepted Plan of Work (2026-07-10) — implementation status

All items below are ACCEPTED for implementation this cycle (deferred items excluded).

- [x] **F2 (C+)** schema v16 migration + append-only SDP write (see F2 section above).
- [x] **F3** display-only short-UUID name resolution in `classic-enum` Service Map and
      `classic-rfcomm` table (reuse `get_uuid_name`, resolves `0x111F`-style entries).
- [x] **F5** `scan -d/--device`: when a filter is set and nothing matched, print a
      filter-aware message distinct from a genuinely empty scan.
- [x] **F1 (aids only, non-merging)** `db list` truncation notice + `db list --name`
      substring filter (identity correlation stays DEFERRED to future IRK-based design).
- [x] **F6/F7** documentation-only notes in `bl_classic_mode.md` (non-fatal
      `br-connection-create-socket`; BlueZ `AddressType: public` echoed for
      structurally-random LE address).

**Deferred (not in this cycle):** IRK-based RPA identity correlation (F1);
`db timeline` SDP change view (F2 future work).

**Verification (2026-07-10):** `_SCHEMA_VERSION=16`; migration smoke test (seeded v15
DB) preserved existing rows, dropped `UNIQUE(mac,handle)`, and confirmed append-only
semantics (identical/handle-only re-observation → no new row; content change → new
snapshot). Full suite green — `tests/test_data_pipeline_fixes.py`, `test_scan_variants.py`,
`test_classic_cli.py`, `test_cli_hint_convention.py`, `test_api_surface.py`,
`test_gatt_enumeration.py` (415 passed, 8 skipped); no new lint. Live: `classic-rfcomm`
now renders `AG Hands-Free`/`Hands-Free` (was bare `0x111F`/`0x111E`) [F3];
`scan -d <absent>` prints "No device matching … (N other device(s) discovered)" [F5];
`db list --name DESKTOP` enumerates all 6 RPA identities of the honeypot without merging,
and `db list --limit N` emits the truncation notice [F1].

**Context**: A read-only examination of the documented `winbt-honeypot` test target
(`DESKTOP-1APRSIB`, dual-mode BR/EDR + LE) surfaced a set of defects and display
gaps across the Classic, LE, and observation-DB paths. Each finding was verified
against source, the test-suite, and BlueZ reference docs (`workDir/bluez/`) before
acceptance. Items are grouped by severity tier (T1 = real deterministic defects,
T2 = presentation/robustness, T3 = verified by-design — no code change).

**Verification (2026-07-09)**: `tests/test_data_pipeline_fixes.py` (98), `test_scan_variants.py`,
`test_classic_cli.py`, `test_cli_hint_convention.py`, `test_gatt_enumeration.py`,
`test_api_surface.py` all green; edited modules import clean; no new lint.
Live against target: `db show` now renders resolved service/characteristic names and
correct SDP UUIDs+names deduped to the latest 16-record snapshot (T1-2/T1-3/T2-2);
`scan -d` narrows display to the target (T1-6); `scan --help` shows corrected help +
`--record-target-only`; the T1-1 `name=None` render path was reproduced and no longer
crashes. `connect --ble-only` render (T1-4) is a line-for-line reuse of the tested
`gatt-enum` formatter — full live confirmation is currently blocked by the target not
accepting LE connections (environmental, same contention as T3-1), not a code issue.

### T1-1 — `classic-rfcomm --probe` crash on unnamed SDP service

- **Root cause**: `build_svc_map()` stores `"name": rec.get("name")` (explicit
  `None` for unnamed records, `bleep/ble_ops/classic/sdp.py:289`). The renderer
  `bleep/modes/classic_rfcomm.py:23` uses `entry.get("name", name)` — the default
  only applies when the key is *absent*, so the stored `None` flows into
  `f"{svc_name:<30}"` (line 36) → `unsupported format string passed to
  NoneType.__format__`, aborting the table before the `--probe` loop.
- [x] Coalesce with the falsy-fallback idiom already used at `sdp.py:283`
      (`entry.get("name") or name`; guard `uuid` similarly). Local to the display
      loop; `build_svc_map` and its other callers untouched. **Done**
      (`bleep/modes/classic_rfcomm.py:26-27`).

### T1-2 — `db show` SDP records print `?`/blank (field-name mismatch)

- **Root cause**: `sdp_records` columns are `uuid`/`name`
  (`bleep/core/observations/_connection.py:189`); `get_device_detail` returns rows
  verbatim (round-trip proof: `tests/test_data_pipeline_fixes.py:1021-1043`). The
  renderer reads non-existent keys `service_uuid`/`service_name`
  (`bleep/modes/db.py:156`) → always `?`.
- [x] Read `uuid`/`name`, coalescing legacy spellings
      (`rec.get('uuid') or rec.get('service_uuid')`) for maximum safety. JSON path
      unaffected. **Done** (`bleep/modes/db.py`, SDP loop).

### T1-3 — `db show` does not resolve UUID names

- **Root cause**: `show_device` prints stored names directly
  (`bleep/modes/db.py:136,144`); LE-enumerated names are `None`, so services render
  as literal `None` and characteristics show no name — although names are fully
  resolvable (verified via `uuid-lookup`).
- [x] Resolve at display time via the canonical `bt_ref.uuid_translator.get_uuid_name`
      (None-safe, `uuid_translator.py:484`) for services and characteristics — same
      helper `classic_enum.py:7` already uses. Lazy import; no import cycle. **Done**
      via a local `_name_for()` helper (services, characteristics, classic + SDP).

### T1-4 — `connect --ble-only` connects/enumerates but displays nothing

- **Root cause**: `bleep/modes/connect.py:35-36` discards the enumerated mapping and
  prints only a one-liner, contradicting the parser's "Connect + GATT enumerate".
- [x] Reuse the existing `bleep.ble_ops.common.conversion.format_gatt_tree(...)` after
      enumeration, exactly as `bleep/modes/gatt_enum.py:58-67` does (identical 4-tuple
      shape, `_collect_device_props` already imported). No new formatting logic. **Done**
      (`bleep/modes/connect.py`, after the success print).

### T1-5 — API-spec tuple arity wrong (docs)

- **Root cause**: `bleep/docs/api_specification.md:123` documents a 5-tuple
  `(device, services_dict, chars_dict, descs_dict, security_dict)`, but
  `connect_and_enumerate__bluetooth__low_energy` returns a 4-tuple
  `(device, mapping, mine_map, perm_map)` (`bleep/ble_ops/le/connect.py:337`;
  callers `connect.py:35`, `gatt_enum.py:8`).
- [x] Correct §3.3.2 to the 4-tuple `(device, mapping, landmine_map, permission_map)`.
      Docs-only. **Done** (`bleep/docs/api_specification.md`).

### T1-6 — `scan -d/--device` filter ignored; add dual-mode filtering

- **Root cause**: dispatch reads only `args.target` (`bleep/cli/dispatch.py:20`), so
  `-d/--device` is dead; and the native scan explicitly ignores device filtering
  (`bleep/ble_ops/le/scan.py:59-61`). BlueZ `SetDiscoveryFilter` has **no address
  key** (`workDir/bluez/doc/org.bluez.Adapter.rst:70-130`) and mandates client-side
  self-filtering (lines 163-164), so filtering must be applied to results.
- **Design (accepted)**: `-d <MAC>` filters **display + return** by default while the
  DB still records all discovered devices (no information discarded). A new opt-in
  flag `--record-target-only` additionally restricts **persistence** to the target
  (streamlined DB interaction).
- [x] `_native_scan`: add keyword-only `filter_record=False`; compute one match once
      after `get_discovered_devices()`; drive display + return from the filtered `view`,
      persistence from `persist_src` (full set unless `filter_record`). **Done**
- [x] `passive_scan`/`naggy_scan`: pass-through `filter_record` (default `False`). **Done**
- [x] `dispatch`: `target = args.target or getattr(args,"device",None)`; thread
      `filter_record` for passive/naggy variants. **Done**
- [x] `parsers/scan.py`: correct `-d/--device` help; add `--record-target-only`
      (no-op without `-d`). **Done**
- [x] Test stub `tests/test_scan_variants.py::Spy.__call__` updated to accept the new
      keyword-only param (positional delegation assertion unchanged). Also fixed a
      pre-existing isolation leak in the same file (`sys.modules[...] = stub` → 
      `monkeypatch.setitem`) so the adapter stub no longer bleeds into later tests. **Done**
- **Safety**: inert for all existing callers (every in-tree caller passes
  `device=None`/omits it; none pass `filter_record`). Return type unchanged.

### T2-1 — Relabel profile-descriptor version (presentation)

- **Root cause**: `bleep/modes/classic_enum.py:233` prints SDP
  `BluetoothProfileDescriptorList` versions (`SDP_ATTR_PFILE_DESC_LIST=0x0009`,
  `workDir/bluez/lib/sdp.h:249`) as "~Bluetooth X.Y", conflating a *profile* version
  with the *core-spec* version (authoritative source is HCI Read Remote Version, the
  "authoritative" block at `classic_enum.py:249`).
- [x] Reword the label to "~profile vX.Y" (both the per-record and authoritative
      blocks; added an inline clarifying comment). Presentation-only; no test asserts
      the string. **Done** (`bleep/modes/classic_enum.py`).

### T2-2 — `db show` accumulates SDP snapshots (display-only)

- **Root cause**: dedup is keyed on `service_record_handle`
  (`_services.py:297`); the honeypot rotates handles between queries, so
  `ON CONFLICT(mac, service_record_handle)` never fires and `db show` dumps every
  historical snapshot (`_devices.py:305`, `ORDER BY ts DESC`). Handle is a per-record
  identifier expected to be stable (`workDir/bluez/lib/sdp.h:240`); rotation is
  adversarial. Write path is an intentional snapshot store — leave untouched.
- [x] Display-only: in `db show`, present the most-recent snapshot set (dedup by
      `(uuid, channel)` keeping first seen under `ORDER BY ts DESC`). JSON/export paths
      unchanged. **Done** — verified live: 16 records shown (was accumulating).

### T3 — Verified by-design (no code change; documented for auditability)

- **T3-1 `br-connection-busy`**: a genuine BlueZ state
  (`workDir/bluez/src/error.h:33`, `ERR_BREDR_CONN_BUSY`), handled non-fatally by
  design (`classic_enum.py:304-310`); triggered environmentally by a paired device's
  auto-connect racing the explicit connect. **No change.**
- **T3-2 pairing-state drift** (`Paired: False → True`): by-design auto-pair inside
  `connect_and_enumerate__bluetooth__classic` (`bleep/ble_ops/classic/connect.py:188-190`).
  **No change** (flagged for awareness that enumeration can establish a bond).

---

## TODO sources

| Source | Section | Last reviewed |
|--------|---------|---------------|
| Codebase (`bleep/**/*.py`) | Inline `# TODO:` comments | _(grep as needed)_ |
| `bleep/docs/audio_recon.md` | Audio recon future work (Bonus Objectives) | _2026-02-28_ |
| `bleep/docs/adapter_config.md` | Adapter configuration reference | _2026-02-28_ |
| `bleep/ble_ops/audio/amusica.py` | Amusica orchestration (core) | _2026-02-28_ |
| `bleep/modes/amusica.py` | Amusica CLI mode | _2026-02-28_ |
| `bleep/docs/agent_dbus_communication_issue.md` | Agent dispatch fix (debug mode pairing) | _2026-02-28_ |
| `bleep/docs/mainloop_requirement_analysis.md` | GLib main-thread dispatch requirement | _2026-02-28_ |
| `bleep/dbuslayer/media.py`, `bleep/ble_ops/audio/audio_codec.py` | Audio transport & GStreamer fixes | _2026-03-19_ |
| `bleep/dbuslayer/media_stream.py`, `bleep/bt_ref/constants.py`, `bleep/cli.py` | MediaTransport discovery & media-enum enrichment | _2026-03-21_ |
| `bleep/ble_ops/audio/audio_system.py`, `bleep/cli.py` | System-tool audio play/record (`--system` flag) | _2026-03-21_ |
| `bleep/modes/exploration.py`, `bleep/core/observations.py`, `bleep/cli.py`, `bleep/ble_ops/classic/connect.py` | Data fidelity remediation (schema v10) | _2026-03-25_ |
| `workDir/BigMoves/README.v2.8.0` | BLEEP v2.8.0 full augmentation plan (pre-work, main work, bonus, final) | _2026-03-25_ |
| `bleep/modes/__init__.py`, `bleep/modes/debug_classic_obex.py` | Debug Mode lazy imports, MAP pagination & folder-context UX | _2026-03-30_ |
| `bleep/docs/map_bmessage_format.md` | MAP bMessage format reference & test corpus (10 validated files) | _2026-03-30_ |
| `bleep/ble_ops/classic/map.py`, `bleep/modes/debug_classic_obex.py` | MAP bulk download-all / push-all commands + operations-layer API | _2026-03-30_ |
| `workDir/Pairing/README.pairing-expansion` | Pairing CLI expansion + pre-pair check + shared helpers refactor | _2026-03-31_ |
| `workDir/bluez/doc/`, `workDir/BlueZDocs/`, `workDir/bluez-tools/`, `workDir/BlueZScripts/` | V2.8.1 BlueZ D-Bus interface gap analysis | _2026-04-02_ |
| `bleep/cli.py`, `bleep/ble_ops/classic/map.py` | MAP CLI folder enumeration fix + future auto-resolve | _2026-04-15_ |
| `bleep/dbuslayer/media_stream.py`, `bleep/dbuslayer/media.py`, `bleep/core/preflight.py` | MediaEndpoint1 contention pre-flight (complete) | _2026-04-17_ |
| `bleep/pairing/__init__.py`, `bleep/ble_ops/audio/audio_tools.py`, `bleep/modes/amusica.py`, `bleep/modes/pair.py`, `bleep/modes/classic_connect.py`, `bleep/cli.py` | Audio profile activation, recording reliability & profile identity fixes (complete) | _2026-04-21_ |
| `bleep/analysis/aoi_analyser.py`, `bleep/modes/aoi.py`, `bleep/core/observations.py`, `bleep/ble_ops/le/scan.py`, `bleep/cli.py` | AoI service-data normalisation, MAC validation & output fixes (v2.8.4) | _2026-05-07_ |
| `bleep/modes/aoi.py`, `bleep/analysis/aoi_analyser.py`, `bleep/core/observations.py`, `bleep/cli.py`, `bleep/ble_ops/le/scan.py` | AoI Augmentation — Full Implementation (v2.8.4; schema v11, scan pipeline, SDP, pairing, deep mode) | _2026-05-07_ |
| `bleep/core/observations.py` | MAC validation — reject incomplete/invalid MACs at DB boundary (v2.8.4) | _2026-05-07_ |
| `bleep/modes/survey.py`, `bleep/cli.py`, `bleep/docs/survey_mode.md` | Survey Mode — long-duration passive device discovery with AoI-compatible output | _2026-05-07_ |
| Comprehensive codebase audit (176 .py files, 61 .md docs, PRDs, field notes, BlueZDocs) | BLEEP v3.0 Expansion Plan — API-ready architecture, DB persistence gaps, CLI dispatch, BlueZ completion | _2026-05-18_ |
| `bleep/analysis/aoi_analyser.py`, `bleep/core/observations/_devices.py`, `bleep/core/observations/_services.py`, `bleep/core/observations/_aoi.py`, `bleep/modes/db.py`, `bleep/modes/aoi.py`, `bleep/modes/survey.py` | Data Pipeline Audit — AoI report key mismatch, scoring bug, DB→analyser shape bugs, `db show` truncation, SDP MAP columns, export gaps | _2026-05-24_ |
| `bleep/ble_ops/classic/version.py`, `bleep/ble_ops/le/scan.py`, `bleep/analysis/aoi_analyser.py`, `bleep/analysis/sdp_analyzer.py`, `bleep/core/observations/_connection.py`, `bleep/modes/classic_enum.py`, `bleep/dbuslayer/device_classic.py` | Remote Bluetooth Version Detection — HCI remote version query, DB schema v14+v15, AoI security flagging, SDP cross-validation, DIS extraction, LE features inference, reference data integration | _2026-05-26_ |
| `workDir/BLEEP_3-0_verify_script.sh` | Augmented Verification Script — 23 sections / 100 checks covering risk ranking, scoring, report generation, AoI pipeline, survey structure, SDP, live DB analysis, E2E survey→report, E2E DB reporting | _2026-06-03_ |
| `bleep/cli/parsers/*.py`, `bleep/cli/dispatch.py`, `bleep/modes/aoi.py`, `bleep/modes/db.py`, `bleep/modes/agent.py` | CLI Help Menu Audit — 8 help text fixes, 2 new features exposed (`db maintain`, schema in `--version`), error message improvements, `aoi db` dispatch bridging | _2026-06-03_ |
| `bleep/docs/aoi_security_algorithms.md`, `bleep/docs/observation_db_schema.md`, `bleep/docs/observation_db.md`, `bleep/docs/api_specification.md`, `bleep/docs/device_type_classification.md` | Internal Documentation Audit — risk ranking/security score algorithm docs, schema v13–v15 migration docs, schema version reference corrections | _2026-06-03_ |
| `bleep/ble_ops/classic/sdp.py`, `bleep/modes/classic_enum.py`, `bleep/modes/debug_classic.py`, `bleep/ble_ops/common/conversion.py` | BR/EDR SDP Enumeration Gap Remediation — missing services/channels, empty-record artifact, PSM/protocol-descriptor surfacing, UUID name resolution, BlueZ-vs-SDP reconciliation, CoD length check | _2026-07-09_ |
| `bleep/modes/classic_rfcomm.py`, `bleep/modes/db.py`, `bleep/modes/connect.py`, `bleep/modes/classic_enum.py`, `bleep/ble_ops/le/scan.py`, `bleep/cli/dispatch.py`, `bleep/cli/parsers/scan.py`, `bleep/docs/api_specification.md` | Target `98:3B:8F:EF:FE:EC` Dual-Mode Audit Remediation — `classic-rfcomm --probe` crash, `db show` UUID-name/SDP-key display, `connect` GATT render, LE enumerate tuple-arity doc, `scan` client-side filtering (`--record-target-only`), profile-version relabel | _2026-07-09_ |

---

## BR/EDR SDP Enumeration Gap Remediation (2026-07-09) – CODE COMPLETE (pending live re-run)

**Goal**: Close the gaps found when comparing BLEEP's Classic (BR/EDR) enumeration
output against raw `sdptool browse` ground truth for target `98:3B:8F:EF:FE:EC`
(winbt-honeypot). BLEEP reported only 8–9 SDP records with RFCOMM channels 1–2,
whereas the device exposes 16 records with channels 1–5, including honeypot
services `SPP`(ch4), `OPP`(ch5), `FTP`(ch5), `PBAP`(ch5), `MAP`(ch5) and
`CDP Proximal Transport`(ch3).

**Root cause (evidence)**: `discover_services_sdp()` tries `sdptool browse --xml`
first, then `sdptool records`, keeping the first result that has any RFCOMM
channel (`bleep/ble_ops/classic/sdp.py` lines 866–927). The `--xml` stream emits
attribute-incomplete records for browse-group-follow services (name+handle but no
`ProtocolDescriptorList`), so channel extraction yields `None` for **every**
record on **every** device in the debug log — the richer 13-record set is then
discarded in favour of the `sdptool records` text path, which itself truncates
mid-enumeration (`Failed to connect to SDP server … Software caused connection
abort`) and never reaches the honeypot handles `0x1005e–0x10062`. Plain
`sdptool browse` (no flag) is the only single source that returned all 16 records
**with** channels and PSMs, and its output matches the existing `_parse_records()`
text grammar.

### Fix A — Prefer plain `sdptool browse` as primary discovery command (Findings 1+2)

- [x] Prepend a `("browse", [sdptool, "browse", <mac>])` command to `cmds_to_try`
      in `discover_services_sdp()`, parsed by the existing `_parse_records()` (the
      dispatch already routes any non-XML tag through it).
- [x] Keep `browse --xml` and `records` as ordered fallbacks (unchanged). The
      existing "prefer a result that has channels" selection naturally keeps the
      plain-browse result.
- [x] **A1**: Fix `_HANDLE_RE` — `Rec(?:ord)?\s+Handle` → `Rec(?:ord)?\s*Handle`;
      `sdptool` prints `RecHandle` with no space, so handles were never extracted
      by the text path (verified: handles now populate).

### Fix B — Drop empty records at the source (Finding 3)

- [x] Guard the unconditional `results.append(record)` in `_parse_records()`:
      skip blocks that yield no `name`/`uuid`/`channel`/`handle`. This removes the
      blank `Record 9` / `handle_None` artifact and prevents NULL-handle rows
      accumulating in `sdp_records` (ON CONFLICT key is `(mac,
      service_record_handle)`). (verified: trailing "Failed to connect…" line dropped.)

### Fix C — Resolve names from UUID in classic-enum / csdp output (Finding 5)

- [x] When a record has no SDP `Service Name` (0x0100) but has a UUID, annotate
      the UUID line. Applied to the display loops in `classic_enum.py` and
      `debug_classic.py` (`cmd_csdp`).
- [x] **Short-form follow-up (2026-07-09)**: initial pass used
      `get_name_from_uuid()`, which does exact-string matching only and left 16-bit
      forms (`0x110E`, `0x1116`, `0x112F`) as bare hex. The short/long-aware lookup
      already existed (`bt_ref/uuid_translator.py::translate_uuid`). Added a thin
      `get_uuid_name()` convenience wrapper over `translate_uuid()` and routed all
      Classic display lookups (`classic_enum.py` record + `_name_for`;
      `debug_classic.py` ×4) through it. `get_name_from_uuid()` left unchanged per
      user direction. Removed the ad-hoc manual short→128-bit expansion in
      `_name_for` (translator handles all forms). Verified: `0x110E`→`A/V Remote
      Control`, `0x1116`→`NAP`, `0x112F`→`Phonebook Access Server`.

### Fix D — Capture & surface L2CAP PSM and protocol descriptors (Finding 4)

- [x] Extend `_parse_records()` to capture the numeric value following each
      protocol line (`PSM: N`, `Channel: N`, `Version: 0xNNNN`) into
      `protocol_descriptors[].params`, matching the shape produced by
      `_extract_protocol_descriptors_xml()`. Extraction scoped to the
      "Protocol Descriptor List:" section only (new `_PROTO_SECTION_RE`) so
      service-class / profile entries are not mis-attributed.
- [x] Carry `protocol_descriptors` through `build_svc_map()` so the
      connected-device `cservices` detailed view can show it too.
- [x] Display a compact `Protocols:` line (e.g. `L2CAP PSM 25, AVDTP v0x0103`) via
      the shared `format_protocol_descriptors()` helper in the record loops of
      `classic_enum.py`, `debug_classic.py` (`cmd_csdp`), and the detailed
      `cservices` view.

### Fix E — Reconcile BlueZ UUID list against parsed SDP (Finding 6)

- [x] In `classic-enum`, after the Service Map print, diff the BlueZ `Device1.UUIDs`
      (captured into `bluez_uuids`) against the parsed SDP record UUIDs and print an
      "advertised-but-not-in-SDP / SDP-but-not-advertised" note with UUID-name
      resolution. Pure set math over data already in scope; no new queries.

### Fix F — Correct Class-of-Device length validation (Finding 7)

- [x] `decode_class_of_device()` warned when `bit_length() != 23`, but CoD is a
      fixed 24-bit field and `bit_length()` drops leading zeros (e.g. `0x2E410C`
      → 22 bits triggered a false error). Now warns only when the value cannot fit
      the field (`class_value < 0 or class_value > 0xFFFFFF`). Decode already
      `zfill(24)`s, so behaviour is otherwise unchanged (verified: 0x2E410C no
      longer warns, decodes as Computer).

### Files to Modify

| File | Fixes |
|------|-------|
| `bleep/ble_ops/classic/sdp.py` | A, A1, B, D |
| `bleep/modes/classic_enum.py` | C, D, E |
| `bleep/modes/debug_classic.py` | C, D |
| `bleep/ble_ops/common/conversion.py` | F |
| `bleep/bt_ref/uuid_translator.py` | C (short-form follow-up: `get_uuid_name`) |

### Acceptance / Verification

- [x] Parser-level validation: `_parse_records()` on plain `sdptool browse` text
      yields correct handles (`0x1005e`), RFCOMM channel (`ch 4`), and PSM
      (`L2CAP PSM 15`, `BNEP v0x0100`); trailing status line dropped.
- [x] No regression: `tests/test_sdp_analyzer.py`, `test_classic_cli.py`,
      `test_classic_debug_mode.py`, `test_observations_classic.py` → 29 passed,
      14 skipped (hardware-gated).
- [x] Fix F verified: `decode_class_of_device(0x2E410C)` no longer warns, decodes
      as Computer.
- [ ] Live re-run: `python3 -m bleep classic-enum 98:3B:8F:EF:FE:EC` and debug
      `csdp` return the 16-record / channels-1–5 ground truth from `sdptool browse`,
      with no blank record, names resolved for `0x110E`/`0x111F`/`0x111E`, PSMs
      shown, and the UUID-vs-SDP note present. (Requires the target device.)

### Future Work: sdptool Output Amelioration (Holistic SDP View)

**Status**: ✅ DELIVERED (2026-07-24) via "ACCEPTED WORK — SDP union + Observed-UUID
catalogue + Reference additions" below. Every planned bullet in this section is
implemented (`--sdp-source` default is `auto` rather than `merge` to preserve
existing behaviour — the only intentional divergence). Retained here for design
provenance.

The remediation above selects a single "best" `sdptool` output. A superior
long-term approach is to **merge** the complementary strengths of all discovery
sources into one authoritative record set per device, rather than choosing one:

- `sdptool browse` (plain): most complete record enumeration (follows the public
  browse group), carries RFCOMM `Channel:` and L2CAP `PSM:` lines.
- `sdptool browse --xml`: structured `ProtocolDescriptorList` with typed params
  (PSM/version) for the records it does return; cleaner for programmatic parsing.
- `sdptool records`: handle-range scan; sometimes surfaces records not in the
  browse group, but truncates on flaky links.
- BlueZ `Device1.GetServiceRecords` (>= 5.66) and `Device1.UUIDs`: cached view,
  useful cross-reference.

**Planned approach**:
- [x] Run the available sources and **union** their records keyed by
      `service_record_handle` (fall back to `uuid`/`name` when handle is absent),
      merging per-attribute so a field present in any source is retained
      (e.g. channel from plain browse, typed PSM params from `--xml`).
- [x] Track provenance per field (which tool supplied it) for auditing and to
      flag inter-source disagreements (potential spoofing / honeypot signal).
- [x] Feed merged records + provenance into `SDPAnalyzer` as a new anomaly class
      (`source_discrepancy`) and persist a `source` column alongside
      `sdp_records` (schema v18; see `bleep/core/observations/_services.py`
      `upsert_sdp_record()`).
- [x] Expose an `--sdp-source {auto,dbus,browse,xml,records,merge,all}` flag on
      `classic-enum` (incl. `--connectionless`/csdp path). Default `auto`
      (behaviour-preserving) rather than `merge`.
- [x] Reuse existing parsers (`_parse_records`, `_parse_browse_xml`,
      `_discover_services_dbus`); the only new code is the merge/provenance layer.

### Future Work: "Seen in the Wild" Service/UUID Knowledge Base

**Status**: ✅ MOSTLY DELIVERED (2026-07-24) via "ACCEPTED WORK" below. Catalogue,
`db uuids`, observed resolver tier, and the promotion path are implemented. The
**classifier feed** (last bullet) remains **DEFERRED as future work** per user
acceptance — it changes classification output and needs its own evidence-weighting
design + tests. Retained here for design provenance.

Goal: incorporate services / UUIDs observed during real enumerations (including
non-SIG, vendor-specific, and honeypot UUIDs such as `winbt-honeypot *` and
`CDP Proximal Transport` = `c7f94713-891e-496a-a0e7-983a0946126e`) into BLEEP's
larger knowledge base so repeat encounters resolve to friendly names and inform
device-type classification.

**Design constraints (from existing conventions)**:
- `bleep/bt_ref/uuids.py` is **auto-generated** by `update_ble_uuids.py` and must
  never be hand-edited. Custom/non-SIG UUIDs belong in `UUID_NAMES` in
  `bleep/bt_ref/constants.py` (first lookup in `get_name_from_uuid()`,
  `bt_ref/utils.py:88`) and flow through `uuid_translator.py`'s `CUSTOM` category.
- The observation DB already snapshots every SDP record (`sdp_records` table via
  `upsert_sdp_record()`), so observed UUID→name pairs are already persisted per
  device — the missing piece is a **cross-device, curated catalogue**.

**Planned approach**:
- [x] Add a DB-backed "observed UUID catalogue" aggregation (distinct
      `uuid → {names seen, count, sources, first/last seen, sample MACs}`) built
      from `sdp_records` + LE service/characteristic/descriptor tables + Classic
      services — surfaced via `db uuids` (`--uuid` filter), reusing existing
      observation query patterns. (`core/observations/_uuids.py`.)
- [x] Provide a promotion workflow: `db uuids --promote NAME` adds confirmed
      custom UUIDs via a JSON overlay (`bt_ref/custom_uuids.py`) merged into
      `constants.UUID_NAMES` at import, keeping SIG UUIDs strictly in the
      `update_ble_uuids.py` pipeline.
- [x] Have `get_name_from_uuid()` optionally consult the observed catalogue as a
      final tier (opt-in `allow_observed=True`) returning a
      `"Unknown (seen as: <name>)"` hint instead of `"Unknown"`, without polluting
      authoritative sources.
- [ ] **DEFERRED (future work):** Feed recurring non-SIG service UUIDs into
      `device_type_classifier.py` as supplementary evidence (mirroring the existing
      `_BEACON_SERVICE_DATA_UUIDS` and `a82efa21…` → Microsoft Nearby Sharing
      pattern). Detailed plan drafted 2026-07-24 (pending acceptance).
- [ ] Optionally seed the catalogue from curated community lists; keep SIG vs
      custom vs observed tiers clearly separated for provenance.

---

## ACCEPTED WORK — SDP union + Observed-UUID catalogue + Reference additions (2026-07-24) — COMPLETE

**Status**: COMPLETE (implemented + triple-pass fidelity review passed 2026-07-24).
Groups the three
"Future Work" sections above (`sdptool Output Amelioration`, `Seen in the Wild`,
`Expand BT SIG Assigned Numbers Coverage`) into one accepted, scoped implementation.

**Cross-cutting principle**: every change is **additive and default-preserving** —
existing outputs, DB rows, and `uuids.py` are not disturbed. Reference additions
land as *new* generated modules (not by rewriting `uuids.py`) so existing SIG
tables have zero drift risk.

### Triple-pass correction (recorded 2026-07-24)
- **`core/fhs.yaml` is Class-of-Device data, not "hop-sequence params".** The FHS
  packet carries the CoD field, so SIG's historical `core/fhs.yaml` encoded CoD.
  Verified against the live SIG repo: current `assigned_numbers/core/` no longer
  ships `fhs.yaml`; the canonical source is **`core/class_of_device.yaml`**
  (`cod_services` + `cod_device_class`). `References/fhs.yaml` is a legacy snapshot
  of the same CoD data. "Incorporate fhs" is therefore implemented as **incorporate
  Class-of-Device** from `class_of_device.yaml`, driving `decode_class_of_device()`
  from generated reference data instead of ~150 hardcoded bit→string literals.

### Implement now
- [x] **Item A — Updater safety hardening** (`bt_ref/update_ble_uuids.py`): on a
      failed fetch, **preserve the previously committed table** instead of emitting
      an empty dict. Closes the offline-run footgun where `regenerate()` zeroes out
      `uuids.py`. Prerequisite for every refresh path (including `refresh-refs`).
      *Done*: `_load_existing_tables`/`_emit_existing_block`/`_block_for` preserve
      committed tables on fetch failure; header `sources` records preservation.
      Tests: `tests/test_update_ble_uuids_safety.py` (3).
- [x] **Item B — Reference additions (fhs→CoD + mesh)** as *new generated modules*
      (leaves `uuids.py` untouched — verified `git diff` clean):
      - [x] `bt_ref/cod.py` generated from `core/class_of_device.yaml`
            (`COD_SERVICES`, `COD_MAJOR_DEVICE_CLASS`, `COD_MINOR_DEVICE_CLASS`,
            `COD_SUBMINOR_DEVICE_CLASS`). `decode_class_of_device()` (in
            `ble_ops/common/conversion.py`) now sources *names* from it.
            **Parity note (deviation from strict byte-parity criterion):** output is
            preserved for all established majors/minors *except* names are normalised
            to the canonical SIG spelling (e.g. `"LE Audio"`→`"LE audio"`) and
            previously-unhandled minors (A/V 19/20, Health, Wearable, Toy) now
            resolve instead of returning raw codes. Documented + asserted in
            `tests/test_cod_decode.py` (10).
      - [x] `bt_ref/mesh_ids.py` generated from `mesh/mesh_model_uuids.yaml` +
            `mesh/mesh_beacon_types.yaml` (`MESH_MODEL_UUIDS`, `MESH_BEACON_TYPES`).
            New **SIG mesh tier** wired into `get_name_from_uuid()`; additive, only
            fills names that were `Unknown`, never shadows GATT UUIDs.
            Tests: `tests/test_mesh_ids.py` (5).
      - [x] Bootstrap self-contained via new `bt_ref/update_extra_refs.py` generator
            (CoD from `References/class_of_device.yaml`, mesh from committed
            snapshot, both with live-fetch refresh). Wired into `refresh-refs`.
- [x] **Item C — SDP source union + provenance**: `sdp_records.source` column
      (schema **v18**), union records across D-Bus / browse / `--xml` / records keyed
      by `service_record_handle` (fallback `uuid`/`name`) with per-field provenance,
      `upsert_sdp_record()` stores source (excluded from change-detection tuple),
      `SDPAnalyzer` gains a `source_discrepancy` anomaly, and `classic-enum`
      (incl. `--connectionless`/csdp path) gains
      `--sdp-source {auto,dbus,browse,xml,records,merge,all}` (default `auto`
      preserves current behaviour). Reuses existing parsers; all raw output retained.
      Tests: `tests/test_sdp_source_union.py` (12).
- [x] **Item D — Observed-UUID catalogue**: DB aggregation (`uuid → {names, count,
      sources, first/last seen, sample MACs}`) over LE services/characteristics/
      descriptors + Classic services + `sdp_records`, canonicalised to 128-bit
      (`_uuids._canonical_uuid`). New `db uuids [--uuid] [--promote NAME]` subcommand,
      an opt-in observed tier for `get_name_from_uuid(..., allow_observed=True)`
      (returns a "seen as" hint instead of `Unknown`, never polluting authoritative
      sources), and a promotion path (`bt_ref/custom_uuids.py` overlay merged into
      `constants.UUID_NAMES` at import). Tests: `tests/test_observed_uuid_catalogue.py` (8).

### ACCEPTED WORK — Classifier feed + SDP attr-ID labels + core_version emission (2026-07-24)
Scope accepted after triple-pass review. Decisions locked: BlueZ pull **pinned to
commit `4c431e5da`**; SDP labels use **verbose spec names** (`lib/sdp.h`); classifier
feed is **WEAK-only** (cannot flip a verdict — `_classify_le/_classic/_dual` consult
only CONCLUSIVE/STRONG; WEAK contributes to confidence only).

- [x] **Item 2 — SDP universal attribute-ID labels.** New BlueZ-sourced updater
      `bt_ref/update_bluez_refs.py` (mirrors the SIG/CoD pull pattern: network-best-effort
      → committed `bt_ref/bluez_cache/sdp.h` fallback, never zeroes a table). Pulls
      `lib/sdp.h` from `https://github.com/bluez/bluez.git` (pinned `4c431e5da`), parses
      the **universal range `0x0000–0x000D`** `#define SDP_ATTR_*` set → emits
      `bt_ref/sdp_attr_ids.py` (`SDP_UNIVERSAL_ATTR_IDS` + `resolve_sdp_attr_id()`).
      IDs ≥ `0x0200` are **context-dependent** (BlueZ reuses `0x0200` for GROUP_ID /
      IP_SUBNET / VERSION_NUM_LIST / SPECIFICATION_ID / HID_DEVICE_RELEASE_NUMBER …) so
      only the universal range is labelled without service-class context; profile-specific
      labels deferred. `sdp.py` `_parse_xml_record` gains a lossless `attribute_labels`
      annotation (labels seen attribute IDs; never drops/overwrites parsed fields or raw).
      Wired into `refresh-refs`. Fixtures: `workDir/BlueZScripts/service-*.xml`.
- [x] **Item 3 — `core/core_version.yaml` emission into `uuids.py`.** Add a dedicated
      `core_version` branch in `_gen_dict_block` (same pattern as `appearance_values`/
      `coding_formats`/`psms`) emitting **2-digit** keys (`"0x0c"`) to match
      `resolve_core_version()`'s `f"0x{lmp_version:02x}"` lookup — the generic branch
      would emit a 128-bit UUID key (garbage) or 4-digit hex (mismatch). Regenerate
      `uuids.py` so `SPEC_ID_NAMES__CORE_VERSION` is populated; `version.py`
      `_LMP_VERSION_MAP` remains the safety-net fallback.
- [x] **Item 1 — Classifier feed of observed UUIDs.** `LEServiceDataCollector` queries
      `get_observed_uuid_names()` for advertised UUIDs not matched by curated
      beacon/UART sets and adds **WEAK** `LE_ADVERTISING_DATA` evidence tagged
      `evidence_source="observed_catalogue"`. Additive context only — cannot flip a
      verdict; catalogue/DB failure is swallowed.
- [ ] **Deferred (future work):** verdict-affecting promotion of observed-catalogue /
      `adv_dissection` evidence (STRONG/CONCLUSIVE weighting) — needs its own
      evidence-weighting design + regression corpus. Profile-specific SDP attribute
      labels (IDs ≥ 0x0200, require service-class context join).

#### Acceptance criteria (delivered 2026-07-24)
- [x] Full suite green: **1511 passed / 27 skipped** (was 1495; +16 new tests).
      New: `tests/test_sdp_attr_ids_core_version.py` (10),
      `tests/test_classifier_observed_feed.py` (5), +1 core_version-supersedes test
      in `test_remote_version.py`.
- [x] `uuids.py` diff is exactly the header source line + appended
      `SPEC_ID_NAMES__CORE_VERSION` block — no SIG-table drift (verified via diff).
- [x] 10 `test_remote_version.py` assertions updated to authoritative SIG spec
      strings (deliberate, documented display change; see changelog).
- [x] Self-contained: `bt_ref/bluez_cache/sdp.h` committed; tests use inline XML,
      no `workDir/` runtime dependency.
- [x] Docs updated: `docs/uuid_translation.md`, `docs/observation_db.md`,
      `docs/changelog.md`.

---

## ACCEPTED WORK — Deferred-item follow-through: A (verdict-affecting adv/observed) + B (profile-scoped SDP attr labels) + C (curated observed seed) + D (SDP change view) (2026-07-24)

**Status**: COMPLETE (2026-07-24) — all of A1/A2/B1/B2/C/D implemented, tested
(1544 passed / 27 skipped), and documented. Scoped from the "Directly deferred from
the just-finished cycle" list. User acceptance 2026-07-24 with decisions: A2 behind an
**opt-in flag (default off, provenance-tagged)**; C curated seed **kept separate
from classifier promotion**; B1 emits **per-profile attribute IDs only** (skip the
`attribute_id_offsets_for_strings.yaml` / `protocol_parameters.yaml` siblings for now).

**Cross-cutting principle** (unchanged): every change is additive and
default-preserving. New reference data lands as *new* generated modules (never a
`uuids.py` rewrite); all generators stay network-best-effort with committed-cache
fallback and non-destructive-on-failure; classifier verdict functions are not edited.

### Item A — verdict-affecting advertisement / observed evidence
- [x] **A1 (low-risk):** added `"eddystone"` to `_LE_INDICATIVE_ADV_PROTOCOLS`
      (`analysis/device_type_classifier.py`) and extended the dissector-driven
      consumer block to dissect **ServiceData as well as ManufacturerData** (Eddystone
      is a ServiceData/0xFEAA protocol) — a decoded Eddystone frame is now STRONG LE
      evidence via the shared dissector, identical to the iBeacon/apple_continuity
      path. Confidence counts by distinct evidence-type presence, so the existing
      beacon-block STRONG add for FEAA is not double-counted.
- [x] **A2 (opt-in):** `get_observed_uuid_evidence(uuid)` in
      `core/observations/_uuids.py` reports which table-kinds a UUID was *measured*
      in (LE service/char/desc vs Classic service/SDP). When promotion is **enabled**
      (`context["allow_observed_promotion"]` or env `BLEEP_CLASSIFIER_OBSERVED_PROMOTION`
      ∈ {1,true,yes,on}), an advertised UUID measured as LE GATT adds **STRONG
      `LE_ADVERTISING_DATA`** (`source="observed_le_gatt"`, `promoted=True`); measured
      as Classic/SDP adds **STRONG `CLASSIC_SERVICE_UUIDS`** (`source="observed_classic"`).
      **Default off → byte-identical WEAK behaviour** (stateless guarantee preserved).
      Reused existing evidence types/weights; verdict functions untouched.

### Item B — profile-scoped SDP attribute-ID labels (data → consumer)
- [x] **B1 (data):** new generator `bt_ref/update_sig_sdp_attr_ids.py` pulls
      `assigned_numbers/service_discovery/attribute_ids/*.yaml` (schema
      `attribute_ids: [{name, value}]`) from the SIG public repo, cached under
      `bt_ref/sig_cache/attribute_ids/`, emitting `bt_ref/sdp_profile_attr_ids.py`
      (`SDP_PROFILE_ATTR_IDS = {profile: {"0xNNNN": name}}` — 24 profiles, 94 IDs)
      plus a curated `SERVICE_CLASS_TO_PROFILE` reverse map (grounded in SIG
      `uuids/service_class.yaml`, verified 2026-07-24). Wired into `refresh-refs`
      (SIG group). Network-best-effort → committed per-file cache; non-destructive.
- [x] **B2 (consumer):** `resolve_sdp_attr_id(attr_id, service_class_uuid=None)`
      (`bt_ref/sdp_attr_ids.py`, generated by `update_bluez_refs`) — universal range
      unchanged; context IDs (≥ 0x0200) resolve only when the service class maps to a
      profile whose table has the ID (defensive import of the profile module).
      `_parse_xml_record` **pre-scans** the Service-Class-ID (attr 0x0001) so labelling
      is order-independent, then passes it in — `attribute_labels` gains profile IDs
      only when unambiguous (0x0200 → HIDDeviceReleaseNumber for HID, IpSubnet for PAN).
      Additive; never overwrites a parsed scalar or `raw`.

### Item C — curated observed-UUID seed
- [x] New committed `bt_ref/observed_seed.py` (well-known non-SIG UUIDs: Nordic UART
      trio, Google Nearby vendor base). `get_observed_uuid_catalogue(..., include_seed=False)`
      optionally unions it, tagged `source="curated_seed"` (count-0 for never-observed,
      merged into real observations otherwise), so SIG/custom/observed/curated tiers
      stay distinct. Exposed via `db uuids --seed`. **Not** consumed by the classifier
      promotion (kept separate per acceptance). Default output unchanged.

### Item D — `db timeline --sdp` change view
- [x] New `get_sdp_timeline(mac, uuid=None, limit=None)` in
      `core/observations/_services.py` (reads the already-persisted append-only
      `sdp_records` history, oldest-first, grouped `(uuid, channel)`). `db timeline --sdp`
      prints an `[initial]` snapshot then per-snapshot field diffs (incl. handle
      rotation); JSON/quiet emit the ordered history. Read-only; default `db timeline`
      (characteristics) behaviour unchanged.

### Acceptance criteria (this cycle)
- [x] Full suite green with new tests: `test_classifier_adv_protocol_feed.py` (5),
      `test_classifier_observed_promotion.py` (7), `test_sig_sdp_profile_attr_ids.py` (11),
      `test_observed_seed.py` (5), `test_db_sdp_timeline.py` (4). **1544 passed / 27 skipped**
      (was 1511). `test_api_surface` observation-symbol count 38→40 (+`get_observed_uuid_evidence`,
      `get_sdp_timeline`).
- [x] `uuids.py` untouched (new modules only: `sdp_profile_attr_ids.py`, `observed_seed.py`;
      regenerated `sdp_attr_ids.py`); generators offline-safe (committed cache).
- [x] Default classifier/DB/CLI output unchanged unless the opt-in flag / `--sdp` /
      `--seed` / `include_seed` is used.
- [x] Docs updated: `uuid_translation.md`, `observation_db.md`,
      `device_type_classification.md`, `cli_usage.md`, `api_specification.md`,
      `adv_dissection.md`, `sdp.py`/generator docstrings, `changelog.md`.

### Deferred successors — COMPLETE (2026-07-24)
Both future-work successors of the profile-SDP work are now implemented (user
acceptance 2026-07-24; verified against BlueZ `workDir/bluez/lib/sdp.h`/`sdp.c`).
Additive/lossless, default-preserving. Full suite **1556 passed / 27 skipped** (+12).
- [x] **Item 2 — unmapped WAP profile.** `interoperability_requirements` →
      `{0x1113, 0x1114}` (WAP/WAP_CLIENT) in `_PROFILE_SERVICE_CLASSES`; regenerated.
      Standing guard `test_no_unmapped_profile` asserts every compiled profile is
      reachable. `resolve_sdp_attr_id(0x0307, "0x1113") == "WAPGateway"`.
- [x] **Item 1b — protocol parameters.** Ingest `protocol_parameters.yaml` →
      `SDP_PROTOCOL_PARAMETERS`; `_extract_protocol_descriptors_xml` emits additive
      `parameters` `[{index,name,value}]` (all params, incl. the 2nd BNEP param).
      Fixed latent `_KNOWN_PROTOS` case bug (upper-cased hex UUID never matched
      BNEP/AVCTP/AVDTP). Existing `uuid`/`name`/`params` untouched.
- [x] **Item 1a (Option B) — secondary-language strings.** Ingest
      `attribute_id_offsets_for_strings.yaml` → `SDP_STRING_ATTR_OFFSETS`;
      `_parse_xml_record` pre-scans `LanguageBaseAttributeIDList` (0x0006 uint16
      triplets) and labels non-primary-base strings e.g. `"Service Name (fr)"`.
- [x] Generators network-best-effort with committed cache + `_committed()`
      non-destructive fallback; `uuids.py` untouched. Docs updated:
      `uuid_translation.md`, `api_specification.md`, `sdp.py`/generator docstrings,
      `changelog.md`. Generator verified idempotent (no diff on re-run bar timestamp).

---

### Real-device validation + F-1/F-2 fixes — COMPLETE (2026-07-25)
Exhaustive on-hardware validation of the deployment work (adapter ready, BlueZ
5.79; PLT V8200 headset `F4:B6:88:0B:90:22`, Light Orb, live BLE/Classic scan).
Confirmed on real devices: **B** profile-scoped labels (DID `0x0200–0x0205`),
**A1** Eddystone→STRONG-LE, **A2** promotion gate (off/on/on/off), **C** seed
(+3), **D** `db timeline --sdp` (9 snapshots). Full suite **1560 passed / 27
skipped** (+4). Two gaps found and fixed (see `changelog.md` 2026-07-25):
- [x] **F-1 — XML fragment robustness.** `_parse_browse_xml` dropped every record
      when `sdptool browse --xml` appended trailing status text
      (`Service Search failed: Invalid argument`) after `</record>` → malformed
      fragment → `ET.ParseError`. Now clips each fragment to `<record>…</record>`
      span(s) via new `_XML_RECORD_RE` (`… or [frag]` preserves the old
      whole-fragment fallback). Makes the XML-only enrichments (attribute labels,
      additive protocol `parameters`, secondary-language labels) actually reachable
      on hardware. `auto` chain (MCP default) unchanged; `source="all"` union now
      `browse+xml+records`. Pre-existing bug (not from the profile-SDP work).
- [x] **F-2 — timeline UUID display.** Legacy `sdp_records` rows stored `0X1108`
      (upper-cased `0X` prefix). `modes/db.py` adds display-only `_canon_sdp_uuid()`
      applied to the `timeline_sdp` group key: renders `0x1108` and folds legacy +
      canonical rows into one group. Stored data untouched; current parser already
      emits canonical `0x…`. Cosmetic, pre-existing.
- [x] Regression tests: `test_browse_xml_survives_trailing_status_text` (+ clean
      multi-record) in `test_sig_sdp_profile_attr_ids.py`; `test_canon_sdp_uuid_forms`
      + `test_timeline_display_canonicalizes_legacy_uuid` in `test_db_sdp_timeline.py`.
      No `bleep-mcp/` components modified. Lints clean; consumer audit confirms no
      other subsystem affected.

---

### Acceptance criteria
- [x] Full test suite green; new tests for each item. **1495 passed / 27 skipped.**
      `test_api_surface` symbol count bumped 36→38. A pre-existing full-suite-only
      failure (`test_discovery_error_surfacing::…no_discovery_started`, unrelated to
      this change set) was root-caused to a thread-local output-mode leak and fixed
      via an autouse `tests/conftest.py` fixture (`_reset_output_mode`) that restores
      the `"terminal"` default around every test — no production code changed. See
      changelog "Test-isolation fix: thread-local output-mode leak (2026-07-24)".
- [~] `decode_class_of_device()` output unchanged — **superseded**: names normalised
      to canonical SIG spelling + new minors resolved (see Item B parity note).
      Behaviour preserved for all previously-handled cases; asserted in tests.
- [x] `uuids.py` unmodified by this change set (new tables live in `cod.py`/`mesh_ids.py`). *Verified: `git diff` clean.*
- [x] Default CLI/DB/report outputs unchanged unless a new flag/subcommand is used.
      (`--sdp-source` default `auto`; `db uuids` new; `allow_observed` default `False`.)
- [x] Offline `refresh-refs` / `regenerate()` never zeroes a committed table.

---

## CLI Help Menu Audit — BLEEP 3.0.0 (2026-06-03) — COMPLETE

Comprehensive audit and correction of all CLI help menus to ensure every flag,
subcommand, and description accurately represents the implemented functionality.

### Fixes — Hidden or Misleading Help Text — COMPLETE

- [x] `bleep scan` title: "Passive BLE scan" → "BLE scan (passive, naggy, pokey, or brute via --variant)"
- [x] `bleep enum-scan`: removed deprecated `--controlled` flag
- [x] `bleep aoi`: added `db` to subcommand list in positional arg help text
- [x] `bleep aoi` parser: added missing `--db-only`, `--no-db`, `--connectionless` flags
- [x] `bleep aoi --deep/--timeout`: scope corrected to "for scan and analyze subcommands"
- [x] `bleep classic-enum --analyze`: help clarifies `--version-info` dependency for LMP cross-validation
- [x] `bleep agent --auto-accept` → `--no-auto-accept` (`store_false` + `default=True`); also fixed in `modes/agent.py` internal parser
- [x] `bleep aoi db` dispatch: action bridging in `modes/aoi.py` for CLI invocation; graceful error when no action specified

### New Functionality Exposed — COMPLETE

- [x] `bleep db maintain`: new subcommand exposing `maintain_database()` (VACUUM + ANALYZE)
- [x] `bleep --version`: now shows `BLEEP 3.0.0 (DB schema v15)`

### Error Message Improvements — COMPLETE

- [x] `bleep aoi` dispatch error includes `db` in available subcommand list
- [x] `bleep aoi db` (no action) emits "Missing db action. Use: list, import, export, sync"
- [x] `bleep aoi db <invalid>` emits "Unknown database action: <x>. Use: list, import, export, sync"

### Files Modified

| File | Changes |
|------|---------|
| `bleep/cli/parsers/__init__.py` | `--version` format includes `_SCHEMA_VERSION` |
| `bleep/cli/parsers/aoi.py` | Added `db` to help text, `--db-only`, `--no-db`, `--connectionless` flags, scoping fixes for `--deep`/`--timeout` |
| `bleep/cli/parsers/db.py` | Added `maintain` to action choices |
| `bleep/cli/parsers/scan.py` | Title update; removed `--controlled` from `enum-scan` |
| `bleep/cli/parsers/classic.py` | `--analyze` help updated |
| `bleep/cli/parsers/pairing.py` | `--auto-accept` → `--no-auto-accept` |
| `bleep/cli/dispatch.py` | Error message includes `db` subcommand |
| `bleep/modes/aoi.py` | `aoi db` action bridging + error messages |
| `bleep/modes/db.py` | `maintain` command handler + backward-compatible parser |
| `bleep/modes/agent.py` | Internal parser `--no-auto-accept` alignment |

---

## Internal Documentation Audit — BLEEP 3.0.0 (2026-06-03) — COMPLETE

Comprehensive review of internal documentation to bring all files into alignment
with the current BLEEP 3.0.0 codebase state.

### Documentation Updates — COMPLETE

- [x] `aoi_security_algorithms.md`: added Risk Ranking section (`_assign_concern_risk()` keyword mapping for HIGH/MEDIUM/LOW)
- [x] `aoi_security_algorithms.md`: added Security Score Calculation section (`_calculate_security_score()` baseline=5, stacking, cap=10)
- [x] `observation_db_schema.md`: added v13 migration (survey metadata columns)
- [x] `observation_db_schema.md`: added v14 migration (Classic LMP version columns)
- [x] `observation_db_schema.md`: added v15 migration (DIS columns)
- [x] `changelog.md`: RV test count corrected (79 → 73)
- [x] `observation_db.md`: schema version reference 13 → 15
- [x] `api_specification.md`: schema version reference 13 → 15
- [x] `device_type_classification.md`: schema version reference 13 → 15

---

## Augmented Verification Script — BLEEP 3.0.0 (2026-06-03) — COMPLETE

Augmented `workDir/BLEEP_3-0_verify_script.sh` from 12 sections / ~30 checks to
23 sections / 100 checks for comprehensive BLEEP 3.0.0 verification.

**File**: `workDir/BLEEP_3-0_verify_script.sh`

### Part 1 — Fix Stale Assertions — COMPLETE

- [x] Schema version `== 13` → `== 15` (section 6 header updated to "schema v15")
- [x] API surface test count: hard-match `grep '299 passed'` → threshold `>= 299`
- [x] Full test suite threshold: `>= 1090` → `>= 1130`

### Part 2 — New Offline Validation Sections (10–15) — COMPLETE

- [x] **Section 10: Risk Ranking Engine** (8 checks): `_assign_concern_risk()` for
  high/medium/low classification keywords, idempotency, description propagation
- [x] **Section 11: Security Score Calculation** (6 checks): `_calculate_security_score()`
  baseline=5, stacking weights, cap=10, legacy auto-classification
- [x] **Section 12: Report Generation & Version Embedding** (6 checks): markdown
  risk emojis, text `[HIGH]` prefix, JSON `metadata.version`, aggregate summary table
- [x] **Section 13: AoI Analysis Pipeline** (5 checks): `analyse_device()` end-to-end,
  outdated LMP flagging, JustWorks pairing detection, report round-trip
- [x] **Section 14: Survey Census Structure** (7 checks): `SurveyCensus` with
  `format_simple`/`format_objects`/`format_grouped`, filters, dual-mode detection
- [x] **Section 15: SDP Analyzer** (4 checks): import, `analyze()` keys,
  `generate_report()` header, anomaly severity constraints

### Part 3 — New Live Data Validation Sections (16–18) — COMPLETE

- [x] **Section 16: Live DB Device Analysis** (6 checks): production DB device count,
  AoI device count, export schema v15 structure, Light Orb analyse+report, OnePlus SDP
- [x] **Section 17: Live Survey Pipeline** (3 checks): `--format objects/grouped/simple`
  CLI output structure validation from 5-second live surveys
- [x] **Section 18: DB Schema v15 Features** (4 checks): LMP columns, DIS columns,
  survey metadata columns in `_SCHEMA_SQL`

### Part 4 — New End-to-End Pipeline Sections (19–20) — COMPLETE

- [x] **Section 19: E2E Survey-to-Report** (5 checks): 120s live survey →
  `analyse_device()` → markdown/text/JSON report generation; output to `/tmp/bleep_verify_e2e/`
- [x] **Section 20: E2E DB Aggregate & Individual Reports** (6 checks): aggregate
  report across all AoI-analyzed DB devices + individual richest-device report, all 3 formats

### Part 5 — Infrastructure & Renumbering — COMPLETE

- [x] CWD guard: auto-cd to project root from `SCRIPT_DIR/..`
- [x] Timeout protection: all adapter/CLI commands wrapped with `timeout`
- [x] Renumber all section headers `[N/12]` → `[N/23]`; old sections 10–12 → 21–23

### Results (2026-06-03)

- 100/100 checks passed — GREEN FLAG
- Full test suite: 1140 passed, 2 failed (known hardware-dependent)
- Generated reports in `/tmp/bleep_verify_e2e/`: survey results, 3 survey reports,
  3 aggregate reports, 3 individual reports (10 files total)
- BLE passive scan fix: `--timeout` is in seconds (not milliseconds); changed from
  `--timeout 3000` → `--timeout 10` with `timeout 20` system guard

---

## Survey Mode — Long-Duration Passive Device Discovery (2026-05-07)

New `bleep survey` CLI command: multi-transport passive scanning with automatic
deduplication, per-device RSSI tracking, and AoI-compatible target list output.

**Files**: `bleep/modes/survey.py` (new), `bleep/cli.py` (parser+dispatch),
`tests/test_survey.py` (new), `bleep/docs/survey_mode.md` (new),
`bleep/docs/cli_usage.md`, `bleep/docs/aoi_mode.md`, `bleep/docs/changelog.md`.

### Phase 1 — Core Implementation – COMPLETE (2026-05-07)

- [x] `bleep/modes/survey.py`: `DeviceSighting` dataclass, `SurveyCensus` class
- [x] `bleep/modes/survey.py`: `_run_le_round()`, `_run_classic_round()` scan functions
- [x] `bleep/modes/survey.py`: `main()` with survey loop, signal handling, output
- [x] `bleep/modes/survey.py`: Three output formatters (`simple`, `objects`, `grouped`)
- [x] `bleep/cli.py`: Add `survey` subparser and dispatch block
- [x] `tests/test_survey.py`: 32 unit tests (census merge, filters, formats, AoI compat, signal, parser, roundtrip)
- [x] `bleep/docs/survey_mode.md`: User documentation
- [x] `bleep/docs/cli_usage.md`: Add `survey` row to BLE Commands table
- [x] `bleep/docs/aoi_mode.md`: Reference survey as recommended target list source
- [x] `bleep/docs/changelog.md`: Add entry under Unreleased

### Phase 2 — Enhancements – COMPLETE (2026-05-07)

- [x] Aggregate multi-device survey report (`bleep aoi report --all`): `AOIAnalyser.generate_aggregate_report()` with markdown/text/JSON; report subparser `--address` now optional
- [x] `BlueZServiceMonitor` integration: heartbeat thread started/stopped with survey, stall/unavailability callbacks emit warnings, `--live` shows health status
- [x] `--then-aoi` convenience flag: auto-invokes `bleep aoi scan <file>` after survey (requires `-o`)
- [x] `--no-db` fix: `_run_classic_round(persist_db=)` properly wired; removed inert env var approach
- [x] Tests: 4 new survey tests (36 total), 5 new AoI aggregate report tests

### Phase 2.1 — Field-Test Bug-Fixes – COMPLETE (2026-05-08)

- [x] `datetime.datetime.now()` fix in `bleep/modes/aoi.py` line 498: aggregate auto-filename used `datetime.now()` on the *module* not the *class*; only hit when `-o` was omitted
- [x] `bytes` JSON serialization fix: `_generate_aggregate_json()` and `_generate_json_report()` now route through `AOIAnalyser._sanitize_for_json()` to hex-encode `bytes` before `json.dumps()`
- [x] New test: `test_aggregate_json_handles_bytes` (6 aggregate tests total)
- [x] `bleep/dbuslayer/bluez_monitor.py` line 93: missing closing `]` in availability log — `[! BlueZ …` → `[!] BlueZ …`

### Phase 3 — Debug Mode Integration – COMPLETE (2026-05-08)

- [x] Debug shell `survey start|stop` command: launches survey in background daemon thread; supports all CLI flags (`--duration`, `--round-time`, `--transport`, `-o`, `--format`, `--min-rssi`, `--min-sightings`, `--no-db`, `--adapter`, `--then-aoi`); quit/exit auto-stops running survey
- [x] Debug shell `survey-status` command: reports RUNNING/FINISHED, round count, elapsed/duration, device breakdown (LE/Classic/Dual), output file path
- [x] `DebugState` extended with `survey_thread`, `survey_stop_event`, `survey_census`, `survey_round`, `survey_elapsed`, `survey_duration`, `survey_output`
- [x] New submodule `bleep/modes/debug_survey.py`; registered in dispatch table and help groups
- [x] Tests: 7 new tests (43 survey tests total) covering start, duplicate-reject, stop, no-survey-stop, status-no-data, status-running, status-finished

### Phase 4 — Advertisement Monitor Passive Mode — superseded by Phase 4d

- [x] ~~`bleep survey --passive` using AdvertisementMonitor instead of StartDiscovery~~ — **rejected**: `--variant passive` already means StartDiscovery; AdvMonitor `or_patterns` cannot match-all (empty Patterns → Release / 0 events). Completeness stays Device1 harvest. See Phase 4d.

### Phase 4b — Multi-antenna concurrent collection D1/D2 (2026-07-26) – COMPLETE

Groundwork for the "collect on one antenna, enumerate on another" goal: several
adapters collect concurrently on a shared main-loop, each routing observations to
its own cache and merging into one census. Single-adapter survey unchanged.
+36 tests; full suite 1600 passed / 34 skipped (pre-existing 11 env-only failures
identical on clean HEAD).

- [x] **D1 adapter-aware signal routing** — `system_dbus__bluez_signals` keeps a
  `_device_managers` dict keyed by `adapter_name`; `_capture_device_rssi` parses
  the adapter from the object path (`_adapter_from_device_path`) and routes to the
  owning manager (drops rather than mis-routes when ambiguous with ≥2 managers;
  single-manager legacy path preserved). `register`/`unregister_device_manager` +
  compat `_device_manager` property/setter. `manager._cleanup_after_run`
  deregisters. (`bleep/dbuslayer/signals.py`, `manager.py`)
- [x] **D1.4 shared-loop service** — reference-counted process-wide
  `MainLoopService` running one `GLib.MainLoop` on a daemon thread
  (`bleep/dbuslayer/loop_service.py`). Thread-per-collector (per-adapter
  `GLib.MainContext`) documented as a **deferred** future option in-module.
- [x] **D1.5 AdapterSession + registry** — adapter + role + transport composition
  with non-blocking `begin`/`harvest`/`end`; harvest filtered by adapter
  object-path (`bleep/dbuslayer/adapter_session.py`). `DeviceManager` gains
  `begin_discovery`/`end_discovery` and `start_discovery(transport=)`.
- [x] **D2.1 DB serialization** — `_db_cursor()` acquires `_DB_LOCK` for the whole
  cursor→commit window; `_DB_LOCK` upgraded to `RLock` so existing
  `with _DB_LOCK, _db_cursor()` sites stay reentrant
  (`bleep/core/observations/_connection.py`).
- [x] **D2.2/2.3 orchestrator + census** — `SurveyCensus` thread-safe (`RLock`) +
  `seen_by` per-adapter set; `run_multi_collector` drives concurrent rounds into
  one census, transport-split default / spatial opt-in
  (`bleep/modes/survey_multi.py`, `survey.py`).
- [x] **D2.4 CLI** — repeatable `--collector hciN[:TRANSPORT]`; `survey.run()`
  dispatches to the multi path when any collector is given
  (`bleep/cli/parsers/survey.py`).
- **Thread-per-collector feasibility:** deferred pending profiling — the shared
  loop is sufficient for the expected handful of adapters and keeps a single
  signal-routing path; the seam for the change is documented in `loop_service.py`.

### Phase 4c — Dual-antenna listen + enumerate A+B+D (2026-09-03) – COMPLETE

Closes the gap between "several antennas collect concurrently" (Phase 4b) and
"collect on one radio while another enumerates". Phase C AdvMonitor overlay /
HW-2 landed as **Phase 4d** (2026-09-04).

- [x] **A1** Thread `adapter_name` into `_LEDevice` / `ClassicDevice` in
  `connect.py` and `_base_enum`; `skip_scan` skips PRE-FLIGHT discovery after
  `Adapter1.ConnectDevice`
- [x] **A2** Honor `--adapter` on `aoi` / `gatt-enum` / `explore` / `pair` /
  `classic-connect`; adapter-scoped `find_device_path(mac, adapter=)`
- [x] **A3** `survey --then-aoi` forwards `--adapter` (enumerator radio if
  `--enumerator` was set); debug-shell `survey` refuses `--enumerator`
- [x] **B1** `AdapterSession` enumerator methods (`connect_device`, `pair_device`,
  `enumerate_device`, `disconnect_device`) in `bleep/dbuslayer/enumerator.py`
- [x] **B2** `bleep survey --enumerator hciN[:MODE]` live queue
  (`bleep/modes/survey_enum.py`); collectors stay `Discovering=true`
- [x] **B3** `Pair()` refused on collector sessions; pair only on enumerator Device1
- [x] **B4** Enumerator worker (not drain-on-harvest-thread); `--duration` is
  listen/admission; pick by sighting_count/last_seen/rssi; this-run +
  `--enum-cooldown` skip; schema v20 `enumerated_at`; leftover Device1
  disconnect; `--live` `enum=`/`q=`/`enumerated_ok`/`attempted`; path logs
  (`survey_enum.py`, `survey_multi.py`, `enumerator.py`)
- [x] **D1** Schema **v19**: `devices.seen_by` (JSON, union-merge),
  `devices.enumerated_by`, `adv_reports.adapter`; AoI reports name the radio
- [x] **D1b** Schema **v20**: `devices.enumerated_at`; `--enum-cooldown`
- [x] Tests: `tests/test_adapter_path_fidelity.py`,
  `tests/test_enumerator_session.py`, `tests/test_survey_enum.py`, plus
  extensions to `test_insert_adv.py`, `test_enum_controller_sr_n3.py`,
  `test_survey.py`, `test_data_pipeline_fixes.py`

**Live gate (two controllers, 2026-09-04):** overlay + enumerator **ran**
but synchronous drain blocked harvest (224s / 99s vs 60s). Listen-only
`--duration 60 --round-time 10` **passed** (60s, 7 rounds, 9 LE). Worker +
priority + cooldown is in-tree (unit-tested). Remaining accept: dual command
must harvest while GATT runs. Full notes:
[Dual-antenna live gate (2026-09-04) – PARTIAL](#dual-antenna-live-gate-2026-09-04--partial).

**Still open:** dual listen+enum live accept; multi-collector `--adaptive`/`--auto-recover`
(G8); HW-3 USB attach race; IRK / HCI sniffer.

### Phase 4d — AdvMonitor catch-all overlay + HW-2 (2026-09-04) – COMPLETE

Live-validated 2026-09-04 on this host (`bluetoothd -E`, CSR 4.0, BlueZ 5.84,
`SupportedFeatures=(none)`). Empty `or_patterns` **Release** with 0 events;
Flags/name/mfr patterns **Activate** + DeviceFound; same-adapter
`StartDiscovery` during a live monitor is **allowed** (BlueZ
`org.bluez.AdvertisementMonitor`: notifications fire “no matter if there is an
ongoing discovery session”). `STOP_CLEARS` is `StopDiscovery` only (R1/R2).

**Locked design (do not regress):**

1. **Census completeness** = union of StartDiscovery Device1 harvest (R1/R2)
   and AdvMonitor `DeviceFound` → Device1 `GetAll`. Neither source is an
   inclusion gate. Missing Flags is recorded, never a drop. No silent 0-event
   “match all”.
2. **Default AdvMonitor overlay is Module A Flags-OR** (one monitor, GAP
   Flags `{00,02,04,05,06,18,1A}`). Live 2026-09-04: `-p 0:0x01:00|02|04|06`
   Activate'd, 6 unique, sampling 255, no daemon death. Exhaustive / 8×256
   prefix covers `NoReply`-killed bluetoothd and are withdrawn. Completeness
   stays Device1 harvest. Overlay registration failure is logged; survey
   continues. Collectors stay `Discovering=true` while the overlay is up.
3. **Same-adapter overlay allowed.** BLEEP does not refuse AdvMonitor +
   `StartDiscovery`. Collectors still stay `Discovering=true` under
   `--enumerator` because `StopDiscovery` deletes unpaired beacons.
4. **CLI is `--listen-monitor`**, not `--passive` (`--variant passive` is
   StartDiscovery). Debug shell refuses `--listen-monitor` (shared loop).
5. **HW-2:** `bleep --check-env` probes `AdvertisementMonitorManager1` and
   `ConnectDevice`; one line + `bluetoothd -E` / `Experimental=true` hint.
   Detect-only.
6. **Manufacturer extras are a second child.** `--listen-manufacturer CID[:HEX]`
   / `--listen-mfr-string TEXT` / `--listen-pattern` require `--listen-monitor`.
   CID is little-endian on the wire; strings memcmp at AD 0xFF offset 2. Mixing
   0xFF extras onto the Flags-OR child `NoReply`-killed software AdvMonitor
   (live 2026-09-04); extras stay on their own `or_patterns` monitor. Still not
   a prefix cover. Completeness stays harvest.
7. **JSON `enumerated_by` ships with the duration fix** (success-gated). Do not
   restore 8×256 / 62×256 covers; multi-collector `--adaptive`/`--auto-recover`
   (G8); HW-3 USB attach race.

- [x] **C0** `bleep/dbuslayer/adv_patterns.py` — validate / catch-all groups /
  parse `OFF:AD:HEX`; `add_monitor` rejects empty patterns
- [x] **C1** `advertise-monitor start` and `scan --monitor` with no `-p` inject
  catch-all (fail closed if Activate/Release with 0 monitors)
- [x] **C2** `survey --listen-monitor` overlay on LE/`both` collectors (promote
  `--adapter` when no `--collector`); union-merge Found into census;
  `advmon_seen` + `advertising_flags` in JSON; `--listen-pattern` fail-closed
  (requires flag; invalid pattern / BR/EDR-only exits 1); extra patterns
  chunked to the monitor cap; overlay merge does not invent fingerprint rotation;
  `survey_multi` imports `LOG__GENERAL` (live NameError abort); default overlay
  is Flags-OR (1 monitor / 7 patterns), not 8×256; `keep_listening` while
  overlay is registered; RegisterMonitor errors do not mis-blame `-E`
- [x] **C3** HW-2 `core/preflight.py` experimental probe on `--check-env`
- [x] **C4** Manufacturer extras: `parse_manufacturer_arg` / `parse_mfr_string_arg`;
  survey `--listen-manufacturer` / `--listen-mfr-string`; advertise-monitor
  `--manufacturer` / `--mfr-string`; extras as second child; fail-closed without
  `--listen-monitor`. Live: CID-6 Flags-`00` device tagged `advmon_seen`; 2
  monitors, no daemon death.
- [x] Tests: `tests/test_adv_patterns.py`, `tests/test_adv_collector.py`,
  extensions to `test_survey.py`, `test_preflight.py`, `test_adv_monitor.py`,
  `test_advertise_monitor_uniformity.py`
- [x] Docs: `adv_monitor.md`, `survey_mode.md`, `cli_usage.md`,
  `ble_scan_modes.md`, `debug_mode.md`, `changelog.md` (this item)

### Dual-antenna live gate (2026-09-04) – PARTIAL

Phase 4c A+B+D + Phase 4d Flags-OR overlay ran on two controllers.

**Passed**

- Overlay: 1 monitor / 7 Flags-OR patterns on hci0, no bluetoothd restart
- Collector census: 9 unique LE, RSSI on all, JSON `seen_by=["hci0"]`
- Enumerator radio: DB `enumerated_by=hci1` for all 9 drained MACs (hci0
  collected, hci1 connected)
- GATT ok: `EC:04:28:42:18:4E`, `F0:98:7D:0A:05:07`, `3C:0F:02:E4:F5:F9`,
  `CC:50:E3:B6:BC:A6`, `10:20:BA:46:1A:0D`, `23:35:10:A7:40:2C`
- Collectors stayed in discovery (no `Discovering=False` / StopDiscovery loop)

**Failed / not a complete accept**

- **Enumerator drain vs `--duration` (P0).** `--duration 60` elapsed
  **224s / 1 harvest round**. Drain is synchronous and unbounded; new
  advertisers after round 1 were never harvested.
- **`enumerated=N` is attempts.** Live `enumerated=9` included 3 GATT
  failures (`C4:AB:D1:DC:9F:A9` Buds, `2D:78:C9:54:45:1D`,
  `24:AC:B4:14:2E:70`). `done.add` in `drain_enumerator` `finally`.
- **`enumerated_by` on failed GATT.** Same three failures still wrote
  `enumerated_by=hci1` (last-writer, no success gate).
- **JSON `enumerated_by`.** `/tmp/survey_dual.json` has `seen_by` only;
  radio-of-enum is DB / AoI `Enumerated via:` only.
- **Path-fidelity CLI example.** `enum-scan AA:BB:CC:DD:EE:FF --adapter
  hci1` is a placeholder; it `not_found`'d after 1 attempt. Use a live MAC
  from the census (`python3 -m bleep enum-scan 10:20:BA:46:1A:0D --adapter
  hci1 --variant passive`) and confirm Device1 under `/org/bluez/hci1/`.

**Do not expand until the 60s live accept:** manufacturer extras on this dual
run (2nd AdvMonitor child), 8×256 covers, `--adaptive` on multi-collector,
HW-3 USB attach race. Drain budget is in-tree; the remaining gate is the
operator re-run.

### Next — bound enumerator drain to `--duration` – SUPERSEDED (2026-09-04)

Wall-clock abort of in-flight GATT was the wrong lever. Replaced by parallel
listen + priority worker (below). Historical 224s/99s overruns stay as evidence
that drain-on-the-harvest-thread blocks the census.

### Next — parallel listen + priority enumerator – COMPLETE (code, 2026-09-04)

Implemented: enumerator worker thread; `--duration` listen/admission only;
pick `sighting_count`/`last_seen`/`rssi_avg`; this-run skip + schema v20
`enumerated_at` + `--enum-cooldown`; leftover ACL sweep; `--live` queue line.

Listen-only live (2026-09-04): 60s, 7 rounds, 9 LE, overlay 1×7.

**Dual live (2026-09-05) — FAIL (do not accept).** Command:

```bash
python3 -m bleep survey --collector hci0:le --listen-monitor \
    --enumerator hci1:passive --duration 60 --round-time 10 --live \
    -o /tmp/survey_dual.json
```

Observed: overlay 1×7; first worker target `10:20:BA:46:1A:0D` (regular);
`listen=60s` then unbounded enum tail; 22 LE; `enumerated_ok=6
attempted=18–20`; `round` stuck at 6 (harvest stopped, expected); process
**Aborted** at ~502s (`malloc(): unaligned tcache chunk detected`, exit
134). JSON not written. Immediate:

```bash
python3 -m bleep enum-scan CC:50:E3:B6:BC:A6 --adapter hci1 --variant passive
```

path-logged `hci1` correctly but **skip-connected** a leftover ACL
(SIGABRT skipped `finally` leftover sweep).

### Dual live re-run with faulthandler (2026-09-05 22:14) — FAIL, crash localised

`PYTHONFAULTHANDLER=1` + `> /tmp/dual_fh.txt 2>&1` (redirect, not `tee`:
`cli/main.py:34` sets `SIGPIPE` to `SIG_DFL`). Reproduced: **exit 134**,
`malloc(): unaligned tcache chunk detected`, census JSON again not written.

Thread states at abort (from the dump):

| Thread | Frame | Verdict |
|---|---|---|
| `bleep-enumerator` | `device_le.py:84` → `bus.get_object` → `activate_name_owner` → `get_name_owner` → `call_blocking` | crash site |
| `bleep-mainloop` | `GLib.py:497 in run` (idle) | **not** in GATT |
| bluez health monitor | `bluez_monitor.py:232` `time.sleep` | idle |
| `MainThread` | `survey_multi.py:348` `_interruptible_sleep` | idle |

Crash path: `enum_controller.py:263` → `connect.py:193`
`create_device_manager()` → `manager.py:497 update_devices` →
`manager.py:500 _create_device` → `_LEDevice.__init__`. `update_devices()`
builds a `_LEDevice` for **every** device BlueZ exposes, and each `__init__`
does **two** `bus.get_object` calls (`device_le.py:76` and `:84`) plus
`_signals_manager.register_device`. `create_device_manager()` caches on
`self._device_manager` (`adapter.py:241-245`) but `connect.py:189`
re-instantiates `_Adapter` on every call, so the cache never survives one
enumeration. `debug.log` holds **102,756** `Device object created for`
lines. Caveat: glibc reports corruption at *detection* time, so the crash
site is not proof of the corrupting agent.

Run metrics: 8 devices; rounds at listen 10/24/34/52/60s (nominal flat 10s);
a **21s hole with no `--live` output** between listen 60s and enum 81s,
coinciding exactly with the worker's 25s `ConnectDevice` on
`10:20:BA:46:1A:0D`; `enumerated_ok=2 attempted=4`. **Both successes were
`already connected` skip-connects** — leftover ACLs inherited from the
previous crash. **0 of 3 fresh connects succeeded**, and all three
(`35:54:F8:D0:FF:07`, `10:20:BA:46:1A:0D`, `15:14:15:01:46:E7`) returned
`NoReply` on `ConnectDevice`. Device count 8 vs 22 at 14:11 is likely
environmental, so the connect failures are not attributed to code alone.

**Corrections to the 2026-09-05 11:xx review (superseded, do not action):**

- `run_on_loop` marshalling is **withdrawn**. `loop_service.py:97-107` is
  fire-and-forget `GLib.idle_add` (no result, no wait), and the loop thread
  is the only one dispatching `DeviceFound`/`PropertiesChanged`; parking a
  25s connect + GATT walk there stalls AdvMonitor delivery and can deadlock
  the connect wait. Superseded by Option A below.
- "15s × 2 ConnectDevice" is **wrong**. `adapter.py:722` calls
  `ConnectDevice(props)` with no `timeout=`, so libdbus's 25s default
  governs; the `timeout=15.0` arg only bounds the post-call Device1 poll
  loop (`adapter.py:746-757`). Cost is ~25s once per unreachable target.
- `1/3for` / `2attempts` were **not** code defects — terminal-snapshot
  render artifacts. `general.log`: 458× `attempt 1/3 for`, 0× `1/3for`;
  32× `after 2 attempts`, 0× `after 2attempts`. Same artifact mangles GATT
  payload text (`Write 0xC9to handle 58`). The `--live` 1 Hz throttle half
  of that item stands.
- "Cooldown broken" is **unsupported**. DB shows one stamp per MAC,
  `enum-scan` stamps correctly (`CC:50:E3:B6:BC:A6` @ `15:13:54Z`), 7 rows
  with `enumerated_at`, 21 legacy rows with `enumerated_by` + NULL stamp
  that correctly do not skip. Residual nit only: `pick_next` treats
  `enum_cooldown=None` as 3600 (`survey_enum.py:161-163`) while
  `queue_depth` treats it as 0 (`:188`), so `q=` can over-report.

### Dual-transport constraint on the NoReply fix (2026-09-05) — REVIEW

Historical observation, re-verified before designing fix 3: a device may
answer on **one** transport and not the other, so a failed LE connect must
never be treated as "device unreachable".

- `observation_db.md:434` and `device_type_classification.md:73`:
  `AddressType = "public"` is **inconclusive** — it is the default for both
  Classic and LE. Only `"random"` is conclusive LE evidence.
- `todo_tracker.md:1609-1612` (SR-N3): `14:89:FD` stored annotations showed
  **3× `br-connection-page-timeout` ~27 s apart (≈80 s per unreachable dual
  device)** before SDP. That ~27s is the same order as the 25s `NoReply`
  now observed, so part of what we are paying may be BR/EDR paging on
  devices we believe are LE.
- Canonical both-transport pattern already in tree — `aoi.py:312-359`:
  LE/GATT for `le`/`dual`/`unknown`, then SDP for
  `classic`/`dual`/`unknown`, with `le_max_attempts = 1` for `dual`
  (`aoi.py:323`) because "the Classic half will not answer an LE connect"
  (`enum_controller.py:225-226`).
- **Survey gap:** `survey_enum._eligible` excludes
  `device_type == "classic"` outright (`survey_enum.py:140-141`), and
  `enumerate_one` only ever runs the LE controller. Survey enumeration is
  therefore LE-only today: Classic devices are never attempted and `dual`
  devices get LE-only.

**Consequence for fix 3:** bound the D-Bus call, but classify a
timeout/`NoReply` as *"this transport did not answer"*, not *"done"*. A
target must be given the other transport before it is marked complete.

### Option B — two-phase transport-priority enumerator (PLAN, 2026-09-05)

#### B.0 Design rationale — the observational asymmetry

LE and BR/EDR enumerability are **not** symmetric, and the scheduler must
encode that:

- **LE is perishable.** A device is connectable only while it is in an
  advertising cycle. Its `Device1` can be cleared by `StopDiscovery`
  (STOP_CLEARS), and RPAs rotate identity. An LE target must therefore be
  enumerated as close to the observation as possible.
- **BR/EDR is durable.** A device that is present answers page / SDP /
  l2ping whether or not it is advertising, and its BD_ADDR is public and
  stable. BR/EDR enumeration can safely be deferred.

⇒ **LE work always outranks BR/EDR work**, and newly observed targets
outrank everything except an enumeration already in flight.

#### B.1 Per-transport target state

Replace the single-transport `EnumeratorState.done` / `.ok` sets with
per-transport maps (lock unchanged):

```
le:            Dict[mac, "INFLIGHT"|"OK"|"FAILED"]   # absent == UNATTEMPTED
br:            Dict[mac, "INFLIGHT"|"OK"|"FAILED"]
le_attempts:   Dict[mac, int]
br_attempts:   Dict[mac, int]
le_failed_mono: Dict[mac, float]   # monotonic, for retry backoff
le_failed_seen: Dict[mac, float]   # census last_seen at failure, for re-sight test
inflight:      Optional[Tuple[mac, "le"|"br"]]
```

#### B.2 Per-transport eligibility

**LE-eligible** — existing census filters (`is_cached`, `min_sightings`,
`min_rssi`) **and** `device_type in ("le","dual","unknown")` (mirrors
`aoi.py:312`) **and** not `INFLIGHT`/`OK` **and** DB cooldown against the
LE stamp (`enumerated_at`).

**BR-eligible** — existing census filters, **and**:

- **`addr_type != "random"`.** A random/resolvable-private address is not a
  BR/EDR BD_ADDR; paging it is meaningless. Grounded in
  `observation_db.md:430` / `device_type_classification.md:64` — `random`
  is *conclusive* LE evidence. This alone removes most one-shot RPA noise
  from the BR queue.
- `device_type in ("classic","dual","unknown")`, **plus** `device_type ==
  "le"` when `addr_type == "public"` — because `public` is documented
  **inconclusive** (`observation_db.md:434`,
  `device_type_classification.md:73`), so a target labelled `le` purely on
  a public address may really be Classic/dual.
- LE for that MAC is **terminal** (`OK`/`FAILED`) or LE-ineligible. This is
  what implements "once the queue of new devices empties".
- not `INFLIGHT`/`OK` for BR, and DB cooldown against `br_enumerated_at`.

#### B.3 Priority tiers — the preemption rule

`pick_next()` returns `(sighting, transport)`, taking the first non-empty
tier:

| Tier | Contents | Order within tier |
|---|---|---|
| **T1 — LE new** | LE-eligible, `le_attempts == 0` | `sighting_count` desc, `last_seen` desc, `rssi_avg` desc (unchanged) |
| **T2 — BR** | BR-eligible | `device_type` (`classic`, `dual`, `unknown`, `le`), then the T1 key |
| **T3 — LE retry** | LE-eligible, `0 < le_attempts < LE_RETRY_MAX`, **fresh sighting since failure** (`last_seen > le_failed_seen`), and `now - le_failed_mono >= LE_RETRY_BACKOFF_S` | T1 key |

T1 above T2 is exactly the required behaviour: **a newly appeared target
preempts BR/EDR work.** T3 sits *below* T2 deliberately — an unreachable
RPA that keeps re-advertising must not starve the BR phase forever.

Because `pick_next()` re-derives candidates from the **live** census on
every call (current behaviour, `survey_enum.py:152-176`), no separate
"new device" signal is needed. Preemption happens at the **next unit
boundary** and never mid-enumeration, preserving the locked rule that GATT
is not aborted.

**Worker loop** becomes:

```
while True:
    if stop: break
    target, transport = pick_next(...)
    if target is None:
        if listen_over and T1/T2/T3 all empty and nothing in flight: break
        sleep(0.4); continue
    enumerate_le_one(...) if transport == "le" else enumerate_br_one(...)
```

#### B.4 BR unit budget — protecting LE freshness

A BR unit (l2ping + SDP) can run tens of seconds, which is dead time for a
newly appearing LE target. Bound it with `--br-timeout` (proposed default
**15s**) fed to both `classic_l2ping(timeout=…)` and
`discover_services_sdp(timeout=…)`, so worst-case added latency for a T1
target is one BR unit. Trade-off to document: larger `--br-timeout` buys
SDP completeness and costs LE freshness.

#### B.5 `enumerate_br_one` — reuse, no new machinery

New `survey_enum.enumerate_br_one(sighting, session, args, persist_db, state)`:

1. **Reachability gate** — `ble_ops.classic.ping.classic_l2ping(mac,
   count=…, timeout=…)`. Unreachable ⇒ mark `br=FAILED`
   (`br-unreachable`) and return. Cheap negative instead of a full SDP
   timeout.
2. **SDP** — `ble_ops.classic.sdp.discover_services_sdp(mac,
   timeout=args.br_timeout, connectionless=args.br_connectionless,
   source="auto")` (signature per `api_specification.md:129`).
3. **Persist** — `observations.upsert_sdp_record(mac, rec)` per record
   (`_services.py:235`), then stamp `br_enumerated_by` / `br_enumerated_at`
   **only when ≥1 record was returned**.
4. **Never** call `Device1.Connect()` or pair in the survey BR phase.
   Pairing stays deep-mode/AoI-only (`aoi.py:360-370`), so survey remains
   non-invasive.

> **BLOCKING implementation risk — adapter pinning.** `l2ping` / `sdptool`
> default to the first available controller unless given `-i hciN`. If the
> BR phase pages from **hci0** it will disturb the collector radio and
> break the parallel-listen guarantee. Before B5 lands, confirm
> `discover_services_sdp` / `classic_l2ping` accept and honour an adapter
> argument; if they do not, add it. Verification: run the BR phase and
> confirm via `btmon` / round cadence that hci0 discovery is undisturbed.

#### B.6 Schema v21 — separate per-transport stamps

Accepted direction: **separate fields, no combined field.** Combination is
an analysis-side concern.

- `devices.enumerated_by` / `devices.enumerated_at` keep their **existing
  LE/GATT-only** meaning (v19/v20 semantics unchanged, the 21 legacy rows
  keep their meaning, and the v20 cooldown path is untouched). Document
  them explicitly as LE-specific.
- **Add** `devices.br_enumerated_by` TEXT — adapter that last successfully
  SDP-enumerated (≥1 record) this device.
- **Add** `devices.br_enumerated_at` DATETIME — naive-UTC ISO of that
  success.
- Migration: two additive `ALTER TABLE`s, `_SCHEMA_VERSION = 21`, extend
  `_DEVICE_COLS` (`_devices.py:139-152`), and add a BR counterpart to
  `get_enumeration_stamp` (`_devices.py:200`).
- Cooldown: `--enum-cooldown` applies **per transport** against the
  respective column; optional `--br-enum-cooldown` defaulting to it.

#### B.7 Census / JSON / `--live`

- `DeviceSighting` gains `br_enumerated_by` / `br_enumerated_at`;
  `format_objects` emits each when set, alongside the existing LE fields.
- `--live` gains a transport-aware phase and per-transport counters:
  `phase=listen|le|br`, `enum=<MAC>:<le|br> le_q=N br_q=M le_ok=A br_ok=B
  le_fail=C br_fail=D`. Throttle to state change (or ≥10s) in the tail.

#### B.8 Also folded into Option B

- **Device-manager reuse (was "fix 2").** Add a process-level per-adapter
  `_Adapter` accessor so `create_device_manager()`'s existing cache
  (`adapter.py:241-245`) persists, and stop `connect.py:189` from
  re-instantiating it. Removes the O(devices) proxy + `GetNameOwner` +
  `register_device` churn per target that the abort landed in. Not a new
  pattern — the cache exists and is merely defeated.
- **Bounded `ConnectDevice` (was "fix 3a").** Pass explicit `timeout=` to
  the D-Bus call, per in-tree precedent (`obex_opp.py:41,115`;
  `obex_map.py:133`); `_ProxyMethod.__call__` forwards `**keywords` to
  `call_blocking(..., timeout=-1.0)` (`dbus/connection.py:601`).
- **Classify, do not conclude.** `NoReply`/timeout must be returned
  distinguishably from "ConnectDevice unsupported" — today both collapse to
  `False` and `NoReply` is additionally re-raised (`adapter.py:744-745`).
  A timeout means *this transport did not answer*, never *done*.
- **`classic` targets admitted.** Drop the blanket exclusion at
  `survey_enum.py:140-141`; Classic devices now route to T2 instead of
  being dropped from the census queue entirely.

#### B.9 Implementation order (each step independently testable)

| Step | Work | Gate |
|---|---|---|
| **B-1** | Device-manager / `_Adapter` reuse — **CODE LANDED 2026-09-05, live re-run pending** | unit tests; no behaviour change |
| **B-2** | Bounded `ConnectDevice` + `NoReply` classification — **CODE LANDED 2026-09-05, live re-run pending** | unit tests + live re-run (abort reproduction check) |
| **B-3** | Per-transport state, tiers, `pick_next → (target, transport)`; **BR tier disabled** | pure refactor, unit tests only |
| **B-4** | Schema v21 + stamps + census/JSON fields | migration test |
| **B-5** | `enumerate_br_one` + **adapter pinning verification** + CLI flags | live BR run on a known Classic target |
| **B-6** | `--live` per-transport counters + tail throttle | live re-run |

B-1 and B-2 are the previously agreed "fixes 2 and 3" and can land and be
re-run before B-3..B-6 begin.

#### B.10 Test matrix

1. `pick_next` yields LE-new (T1) before BR (T2) when both are available.
2. A new census device appearing while the BR tier is populated makes the
   **next** pick LE — preemption at a unit boundary.
3. An in-flight enumeration is **not** aborted when a new target appears
   (`inflight` preserved; the unit runs to completion).
4. BR tier excludes `addr_type == "random"`.
5. BR tier admits a `device_type == "le"` target whose `addr_type` is
   `public`.
6. BR tier contains a MAC only once its LE state is terminal.
7. T3 (LE retry) ranks below T2, and requires both a fresh sighting and the
   backoff to have elapsed.
8. `classic` target is admitted and routed to BR only (never LE).
9. Schema v21 migration adds both columns; each stamp is written only on
   its own transport's success.
10. `br_enumerated_*` stays NULL when SDP returns zero records.
11. BR path is pinned to the enumerator adapter (assert the adapter
    argument reaches `l2ping`/`sdptool`).
12. Worker exits when listen is over and all three tiers are empty.
13. `timeout=` is forwarded to `ConnectDevice`; `NoReply` is classified as
    transport-failure, not unsupported.
14. One `_DeviceManager` construction across two successive enumerations.
15. `--live` renders per-transport counters.

#### B.11 Decisions — ACCEPTED 2026-09-05

1. **T3 placement — ACCEPTED: below T2 (BR).** LE-retry ranks *below* BR so
   a flapping/unreachable RPA cannot starve the BR phase. `LE_RETRY_MAX`
   and `LE_RETRY_BACKOFF_S` to be set during B-3.
2. **BR during listen — ACCEPTED: interleave.** BR units run whenever the
   LE tier is empty, including during the listen window, bounded by
   `--br-timeout`. See FW-1 below for the follow-on investigation.
3. **Defaults** — `--br-timeout` 15s, `--br-l2ping-count` 3,
   `--br-l2ping-timeout` 13 (matching `cli/parsers/classic.py:331`).
4. **Gating flag** — `--enum-transport both|le|br`, default `both`.
5. **`unknown` targets attempt BR** even without a confirmed public
   address — `unknown` is by definition unresolved.

Implementation authorised in two stages: **B-1 + B-2 first**, then live
re-run and review before B-3..B-6 begin.

#### B.13 Live re-run 2026-09-05 23:49 (post-B-1/B-2) — B-1 and B-2 proven, abort persists, root cause sharpened

Command: `PYTHONFAULTHANDLER=1 python3 -m bleep survey --collector hci0:le
--listen-monitor --enumerator hci1:passive --duration 60 --round-time 10
--live -o /tmp/survey_dual.json`. Exit **134** again, at ~211s (listen 60s +
151s enum tail), 12 targets selected, `enumerated_ok=6 attempted=11`.
Artifacts: `/tmp/dual_fh.txt` (320 lines, mtime 23:52:54 — postdates the
23:20 code edits, so B-1/B-2 were live);
`~/.local/share/bleep/logs/{general,debug}.log`.

**B-1 proven effective.** Per-target proxy construction collapsed from
O(census) to 2:

```
[survey] ConnectDevice 3C:0F:02:E4:CF:55: org.bluez.Failed:
[survey] no Device1 for 3C:0F:02:E4:CF:55 on hci1
[*] connect_and_enumerate::target = 3C:0F:02:E4:CF:55
[BLEEP] Device object created for 3C:0F:02:E4:CF:55   <- the target
[BLEEP] Device object created for CC:50:E3:B6:BC:A6   <- leftover ACL, see below
```

`debug.log` holds 102,760 `Device object created` lines cumulatively, but
**zero** occur after line 675,093 (the first `no-answer`, ~55s into the run)
through EOF — i.e. the last 9 targets produced no proxy churn at all. The
102k figure was pre-B-1.

**B-2 proven effective.** Six `[*] ConnectDevice no-answer for <MAC> on hci1`
events, one per unreachable target, each bounded at ~10s instead of the old
25s (visible in `dual_fh.txt` as a consistent 9-10s gap between
`[survey] enumerator hci1:passive → MAC` and
`[*] Starting enumeration controller`). No `NoReply` traceback anywhere.

**Root cause sharpened — three threads share ONE libdbus connection.** The
new faulthandler stack moved off the `manager.update_devices()` path (B-1
removed it) onto the target's own single proxy construction, and still
aborts — now `malloc(): unaligned fastbin chunk detected`:

```
Current thread (bleep-enumerator):
  dbus/connection.py:696 call_blocking
  dbus/bus.py:348        get_name_owner      <-- HERE
  dbus/bus.py:173        activate_name_owner
  dbus/proxies.py:250    __init__
  dbus/bus.py:237        get_object
  device_le.py:84        __init__
  connect.py:257         connect_and_enumerate__bluetooth__low_energy
Thread 2 (bleep-mainloop):  GLib.py:497 run          <- dispatching the same connection
Thread 3 (bluez-monitor):   bluez_monitor.py:232 _monitor_loop
Thread 4 (main/collector):  survey.py:97 _interruptible_sleep
```

Verified empirically: `dbus.SystemBus() is dbus.SystemBus()` → `True`
(process-wide singleton); only `dbus.SystemBus(private=True)` yields a
distinct connection. So every `self._bus = dbus.SystemBus()` in the tree —
`device_le.py:75`, `adapter.py:82`, `manager.py:170`, `signals.py:458`,
`bluez_monitor.py:52` — held the *same* object; those "own" buses were an
illusion.

**Correction to an earlier reading in this section:** `bluez_monitor` is
*not* a racing party. Its periodic health check
(`bluez_monitor._check_service_health`) runs an **out-of-process**
`subprocess.run(["dbus-send", …])` precisely so it never iterates the
in-process GLib context — an earlier fix already closed that hole. Its only
in-process calls (`add_signal_receiver` + one `get_name_owner`) happen once
in `_setup_name_owner_watch()` from `__init__`, on the main thread at import
(`bluez_monitor.py:344`). The monitor thread appears in the dump merely
sleeping between subprocess checks. The racing pair is therefore
**enumerator worker (blocking calls) vs loop thread (dispatch)**, with the
main/collector thread as a third, lower-frequency participant.

Verified *not* the cause: `dbus.mainloop.glib.threads_init()` exists and runs
(`core/config.py:97-98`; dbus-python 1.4.0, libdbus 1.16.2, which calls
`dbus_threads_init_default()` automatically since 1.7), and the only
`SystemBus()` construction during import is `manager.py:151` →
`signals.py:458`. Thread-safety init is not missing.

⇒ **Option A: one connection must be touched by exactly one thread.**
Implemented as B.15 below.

#### B.15 Option A as landed (2026-09-05) — per-thread connection ownership

New module **`bleep/dbuslayer/bus.py`** (~120 lines) owns the rule:

| Thread | Connection | Rationale |
|---|---|---|
| main | shared singleton | existing single-threaded and collector flows unchanged |
| `bleep-mainloop` | shared singleton | it *is* that connection's dispatcher |
| any other thread | own `dbus.SystemBus(private=True)`, **no mainloop attached** | blocking calls never touch the loop's watch/timeout list |

`get_bus()` decides from the calling thread; callers do not choose.
`uses_private_bus()` exposes the predicate, `close_thread_bus()` releases a
worker's socket, `thread_bus_count()` is for diagnostics/tests.

**Why signal delivery is unaffected.** All matches stay on the shared bus and
the loop thread keeps dispatching them. The registry installs *broad* matches
once (`signals.py:876-894`) and `register_device()` is a dict insert with no
D-Bus I/O (`signals.py:508-512`), and `_LEDevice` registers no receivers of
its own — so `_properties_changed` still fires for devices whose *method*
calls now travel on a private bus.

Applied at the three hot-path acquisitions the enumerator drives:
`device_le.py` (the crash site), `adapter.py`, `manager.py`.
`survey_enum.enumerator_worker` now closes its connection in a `finally`.

**Hazard this introduced, and its fix.** `_properties_changed` runs on the
loop thread and called `self.services_resolved()` when `ServicesResolved`
flipped — which, once the device's bus is worker-private, would put a second
thread on that connection: the very pattern being removed. The handler now
defers (sets `_services_resolved_pending`) when `_bus_is_private`, leaving
the work to the owning worker, which already polls `is_services_resolved()`
(`device_le.py:613`) — enumeration is poll-driven, never signal-driven, so
nothing is lost. When the bus is shared, the previous behaviour is kept
verbatim.

**Deliberately not touched.** `bluez_monitor` (already out-of-process, see
correction above) and `signals.py:458` (the shared registry *must* stay on
the loop-attached bus).

**Residual, documented:** the main/collector thread still issues blocking
calls on the shared bus while the loop dispatches it — structurally the same
hazard at much lower frequency (a handful of `StartDiscovery` /
`GetManagedObjects` calls per round, no proxy-construction storms). This is
also the likely source of the irregular round cadence. Extending `get_bus()`
to the collector requires the registry to attach its matches eagerly from the
main thread first (today `register_device` attaches lazily on first use,
`signals.py:511`, which could otherwise land an `AddMatch` on the shared bus
from a worker thread).

**Landmine found, left dormant:** `bleep/dbus/connection_pool.py` looks like
this facility but is not — `_create_connection()` returns the singleton, so
"pooled" connections are aliases and `PooledConnection.close()` would close
the process-wide bus; its maintenance thread would also blocking-call every
60s and close connections past `max_connection_age`. It is unreachable in
normal flow (`bleep/dbus/__init__.py` lazy-loads via `__getattr__`; the eager
imports are under `TYPE_CHECKING`; only `scripts/dbus_diagnostic.py` uses
it). Do not build on it; consider deleting or fixing it separately.

**Tests:** `tests/test_dbus_bus_ownership.py` (8 cases) — singleton premise;
main and `bleep-mainloop` keep the shared bus; worker gets a distinct, stable
private bus; two workers differ; `close_thread_bus()` releases, is idempotent
and never closes the shared bus; `_properties_changed` defers GATT on a
private bus and still runs it on a shared bus.

Suite after B-1/B-2/Option A: **2232 passed, 27 skipped, 7 failed** (was
2219/9 before Option A). The two `test_ble_ctf_*` hardware tests now pass —
clearing the stale `CC:50:E3:B6:BC:A6` ACL unblocked them. Remaining 7 are
the same pre-existing failures (`test_api_surface` observation symbols, four
`test_debug_enum_cmds`, two `test_preflight` GStreamer).

**Not yet proven:** that the abort is gone. Needs a live dual re-run exiting 0.

#### B-2b (new, evidence-backed) — short-circuit the controller on NO_ANSWER

`survey_enum.enumerate_one:218` pre-connects via
`session.connect_device(...)` before `session.enumerate_device(...)` at
line 237, and `enumerate_on_session` then runs `EnumerationController` with
its own connect retries. The pre-connect is **load-bearing** (with
`skip_scan=True` it is what creates `Device1` without discovery), so it must
not simply be deleted — but its outcome is perfectly predictive:

| pre-connect outcome | targets | enumeration result |
|---|---|---|
| `NO_ANSWER` (10s timeout) | `21:02:3F:32:25:B8`, `10:04:76:5B:D3:FC`, `3C:1C:BE:E9:43:0A`, `AC:27:6E:B0:4C:29`, `26:E5:33:96:1A:BB` | **5/5 gave up** after 2 attempts |
| `NO_ANSWER` | `00:8B:42:C4:78:90` | aborted mid-attempt |
| `org.bluez.Failed` (fast) | `3C:0F:02:E4:CF:55`, `10:20:BA:46:AE:D5`, … | several **succeeded** |

So `NO_ANSWER` ⇒ skip the controller entirely and mark the target LE-failed;
a fast `org.bluez.Failed` (BlueZ rejecting `ConnectDevice` for an
already-present/connected device) must **still** run the controller, since
those produced successes. This only became expressible because B-2 added the
classification. Saves 2 redundant attempts × 6 targets on this run's tail.

#### B.14 Still open after the re-run

- **Leftover ACL — found live, now cleared, root cause still open.**
  `hcitool -i hci1 con` reported `< LE CC:50:E3:B6:BC:A6 handle 75 state 1 lm
  CENTRAL`. Not one of the 14 census devices — it survived an *earlier* abort,
  persisted through this whole run, and showed up as a spurious second
  `Device object created` in every enumeration plus `[*] Note: 1 other
  device(s) currently connected`. Cleared manually via
  `busctl call org.bluez /org/bluez/hci1/dev_CC_50_E3_B6_BC_A6
  org.bluez.Device1 Disconnect`; both adapters are now clean, which also
  un-broke the two `test_ble_ctf_*` tests.
  Two lessons for the fix: (a) cleanup must be a **pre-run sweep**, not only
  the exit `finally` that `SIGABRT` bypasses; (b) `bluetoothctl disconnect`
  is *not* sufficient — it reported "Device not available" because it acts on
  the default controller, while the object lived under `hci1`. The sweep must
  walk `Device1` objects under the specific adapter prefix (as
  `disconnect_connected_on_session` already does) rather than shelling out.
  Note `hcitool -i hci1 ledc <handle>` needs root; the D-Bus path does not.
- **Census JSON still lost.** `/tmp/survey_dual.json` mtime is still
  2026-09-04 16:55 — three aborted runs have written nothing.
  `--checkpoint-interval` defaults to 0.
- **Enum tail 151s** for a 60s listen (2.5×). ~60s of that is the six 10s
  pre-connect timeouts; B-2b removes the controller's follow-on attempts.
- **`--live` 1Hz spam** — ~200 of the 320 dump lines are identical
  `round 7` restatements; `round` freezes once listen ends.
- **`GIVE_UP` after 2 of 3 attempts** — `[-] Giving up enumeration for X
  after 2 attempts` while the banner says `max 3 attempts`
  (`enum_controller.py:113` `MAX_ATTEMPTS = 3`). Unchanged.
- **Collector cadence still irregular** — rounds landed at 10/20/30/40/**55**
  /59/60s; the 15s round 4→5 is the main thread stalling behind the shared
  bus, which Option A should also relieve.
- **Log forensics gap.** Logs go to `$XDG_DATA_HOME/bleep/logs`, are
  append-only and un-timestamped (`log.py:77` `Formatter("%(message)s")`),
  and are shared with the test suite. Reconstructing a run required slicing
  by content landmarks. Consider per-run timestamps or a run-id marker.

#### B.16 Root cause established, and a hard constraint (2026-09-06)

Four experiments, each eliminating a hypothesis, plus one that landed it.

**E1 — `private=True` does not isolate. PROVEN.** With
`DBusGMainLoop(set_as_default=True)` in effect (`core/config.py:95`), a
connection made by `dbus.SystemBus(private=True)` is *still* attached to the
**default GLib main context**: an async call on it was dispatched by a
`GLib.MainLoop` running on another thread (probe: `glib-dispatched=True`).
`dbus.set_default_main_loop(None)` is rejected (`TypeError: A
dbus.mainloop.NativeMainLoop instance is required`), and dbus-python exposes
no way to bind a connection to a non-default GLib context — pushing a
`GLib.MainContext` as thread-default does not help (probe: the
default-context loop still dispatched it).

> **CONSTRAINT: with dbus-python there is no way to give a worker thread a
> connection the GLib loop thread will not touch.** Option A as designed
> (B.15) therefore cannot work, and no variant of it can.

**E2 — not proxy churn.** A synthetic worker built **133,128** BlueZ proxies
in 45s on the shared bus while a GLib loop dispatched it: no abort. B-1 had
already removed the churn from the real run, and the abort persisted.

**E3 — not signal-match churn.** **21,558** cycles of
add/remove of three broad matches (~65k AddMatch/RemoveMatch) from the worker
while the loop dispatched: no abort. So
`_attach_bus_listeners`/`_detach_bus_listeners` (`signals.py:508-518`) is
exonerated.

**E4 — not AdvMonitor.** The same dual run **without** `--listen-monitor`
aborted identically (`malloc(): unaligned tcache chunk detected`, same stack,
after 5 targets). Exported `dbus.service.Object`s are not involved.

**E5 — the mechanism, under `MALLOC_CHECK_=3 MALLOC_PERTURB_=170
PYTHONMALLOC=malloc`.** The failure converts to a **SIGSEGV (139)** and the
victim changes thread:

```
Current thread  = bleep-mainloop
  GLib.py:497 run  <-  the LOOP THREAD is the one that crashed
Thread (enumerator), concurrently:
  dbus/exceptions.py:54  DBusException.__init__
  dbus/connection.py:696 call_blocking
  adapter.py:768         connect_device_ex     <- ConnectDevice error reply
```

Two threads are inside one connection's message handling at once, and the
enumerator is on the **error-reply** path. That is why E2/E3 stayed clean:
both ran with `errors=0`, whereas the real run is saturated with error
replies (`org.bluez.Failed`, `NoReply` — six per run, see B.13). The race is
hot on error/exception construction inside `call_blocking`, not on ordinary
replies.

⇒ **The "two threads, one connection" diagnosis is correct, but it cannot be
fixed in-process** because of the E1 constraint.

> **Refined 2026-09-08 (Valgrind `helgrind`).** The shared object being raced is
> more precisely the process-global **default `GMainContext`**, not the
> connection: the worker mutates that context's hash table via `g_source_attach`
> / `g_hash_table_remove` while servicing its pending call, and the loop thread
> traverses the same context in `g_main_loop_run`. This *confirms* E1 and E5
> rather than displacing them — and it explains why E2/E3 stayed clean, since
> neither drove the error-reply path that attaches and removes sources at rate.
> Definitive write-up: `mainloop_architecture.md` → "Thread-safety constraint".

#### B.17 Recommended course of action

**Primary — run the enumerator in its own OS process (Option P).** A separate
process has its own libdbus state, its own GLib context and its own loop, so
the racing pair cannot form. This is the only option that structurally
removes the bug given E1, and it additionally decouples collector cadence
from blocking GATT for good (no GIL contention, no shared loop).
Shape: one long-lived child (not per-device — import cost is seconds), fed
target MACs on stdin, emitting one JSON result per line; the child reuses
`enumerate_one` / `EnumerationController` unchanged. Results already land in
the observation DB, so the IPC surface is small (target in, outcome out).
Parent keeps census/JSON ownership. `--enumerator hciN[:mode]` and all B-3..
B-6 two-phase work sit **inside** the child unchanged.

**Cheaper alternative worth one experiment first — remove the loop from the
survey process (Option Q).** The race needs a running GLib loop.
`survey_multi` acquires `loop_service` unconditionally, yet the collector
already harvests by polling `GetManagedObjects`/`update_devices()`. If the
loop is only genuinely required for AdvMonitor (`--listen-monitor`) and
notification-driven features, then a polling-only collector could run with no
loop at all and the abort would vanish without any process split. **Decisive
test:** make the loop optional, run the dual survey without it, confirm exit
0. If it passes, Option Q covers the common case and Option P is reserved for
`--listen-monitor` runs. Cost of being wrong: one run.

**Rejected.** Single-threading everything onto the loop (blocking GATT would
stall collectors — violates parallel listen). Replacing dbus-python for the
enumerator (jeepney/sdbus — the entire GATT layer is built on dbus-python
proxies). Global lock around blocking calls (cannot lock GLib's dispatch).

**Tooling gap:** `valgrind` is not installed and `sudo` needs a password, so
the corrupting write was never located directly; `gdb` is available.
`MALLOC_CHECK_=3` was what converted the abort into an attributable segfault
and should be the standard way to reproduce this class of fault here.

**Upstream angle:** dbus-python 1.4.0 / libdbus 1.16.2 / Python 3.13. A
minimal reproducer that forces **error replies** while a loop dispatches would
be worth filing upstream; E2/E3 (`/tmp/repro_abort.py`, `/tmp/repro2.py`) are
the starting point and need only an error-generating call added.

#### B.18 Option Q result — the abort is gone without the GLib loop (2026-09-06)

Implemented as a gate in ``MainLoopService.acquire``/``release``
(``BLEEP_NO_MAINLOOP``, see :func:`mainloop_suppressed`).  Both acquire sites
(``survey_multi.py:273``, ``enumerator.py:80``) route through it; verified
directly that with the variable set ``is_running()`` is False and **no
``bleep-mainloop`` thread is created**, and that without it the thread still
starts.

| Configuration | Loop | Result |
| --- | --- | --- |
| dual: collector hci0 + enumerator hci1 | on | **abort 134, 6/6 runs** (one converted to SIGSEGV 139 under `MALLOC_CHECK_=3`) |
| dual: collector hci0 + enumerator hci1 | **off** | **exit 0, 3/3 runs**; census written; run #2 completed **2 successful GATT enumerations** |
| collector-only | on | 16 devices / 7 rounds |
| collector-only | **off** | **16 devices / 7 rounds — identical** |
| collector-only + `--listen-monitor` | on | 15 devices / 4 rounds |
| collector-only + `--listen-monitor` | **off** | 14 devices / 4 rounds (within RF variance) |
| `enum-scan CC:50:E3:B6:BC:A6` | on | success, full GATT tree |
| `enum-scan CC:50:E3:B6:BC:A6` | **off** | success, **tree identical** (services, characteristics, descriptors *and* descriptor value reads) |

Collection fidelity is unaffected because the collector harvests by polling
``GetManagedObjects``/``update_devices()``, and GATT enumeration is unaffected
because ``_wait_for_services`` polls the ``ServicesResolved`` *property*
(``connect.py:318``) and the worker then calls ``services_resolved()``
explicitly (``connect.py:366``) — neither needs signal delivery.
162 tests pass (`test_dbus_bus_ownership`, `test_survey`, `test_survey_multi`,
`test_survey_enum`).

**What loop-free necessarily breaks** (reasoned from D-Bus semantics — a
connection with nothing dispatching it cannot deliver inbound traffic; not all
individually measured):

* **Inbound method dispatch to exported objects** — the pairing agent
  (``dbuslayer/agent.py`` ``RequestPasskey``/``RequestConfirmation``), GATT
  server, ``advertise`` mode, and AdvMonitor's ``Activate``/``DeviceFound``/
  ``Release``.  AdvMonitor still *registers* loop-free and collection barely
  moves, because it is a Flags-OR **overlay** and devices are collected via
  ``StartDiscovery`` regardless — but the monitor is effectively inert.
* **Signal delivery** — GATT notifications
  (``characteristic.py:407 connect_to_signal``) and service-level
  ``PropertiesChanged`` (``service.py:114``).

⇒ Loop-free is correct **only** for the poll-and-blocking-call shape that
survey/enum-scan use.  It must not become a global default.

**Long-run verification (2026-09-06, 2h loop-free dual survey) — PASSED.**
``BLEEP_NO_MAINLOOP=1 survey --collector hci0:le --enumerator hci1:passive
--duration 7200 --round-time 30``:

* **7201s, clean exit, zero crash markers** (no ``malloc``/``Fatal``/``Aborted``
  /``Segmentation``).  Compare: loop-enabled aborts within ~60s / ~5 targets,
  6/6 runs.
* 241 rounds, **177 unique devices**; **175 enumeration targets attempted,
  67 successful GATT enumerations** (38%), 107 gave up.
* Census JSON written (94 KB, 177 entries, ``enumerated_by: hci1`` populated).

**The message-accumulation risk is disproved.**  Open fds constant at **23**
and threads constant at **3** for the whole observation window.  RSS grew
69.8 → 76.9 MB, but the growth is **work-correlated, not time-correlated**:

* Decisive window — elapsed **6619–6799s**, targets flat at 158 and log lines
  flat at 1290 (no enumeration work) while the collector kept running discovery
  rounds: RSS **perfectly flat at 74180 kB across 6 consecutive samples
  (180s)**.  Undispatched messages would queue with *time* regardless of
  enumeration activity; they did not.
* Busy intervals allocate as expected — e.g. 6169→6199s, targets 145→147,
  RSS +1664 kB.

Growth therefore tracks census/GATT data for newly enumerated devices, bounded
by distinct device count.  No need to skip installing the broad matches.

*Measurement caveat:* the sampler covered only the **last 23.5 min**
(5779–7189s); the first 96 min were sampled against the wrong pid (a bash
wrapper, RSS 9 MB / 1 thread) and are void.  The conclusion rests on that
window plus the flat idle period, not the full run.  Two spot readings
(63.9 MB @ 76 min, 76.9 MB @ 120 min) are consistent with gradual work-driven
growth.  2h is not multi-day; the idle-window evidence is mechanistically
strong but a longer run would harden it.

**Incidental findings from the same run (not yet actioned):**

1. **``--checkpoint-interval 300`` never fired.**  The JSON did not exist at
   86 min in and only appeared at process exit.  This is the guard against
   losing a long run, so it matters — see ``abortsafe``.

   **RETRACTED 2026-09-07 — this was a measurement error, not a bug.**
   Checkpointing works.  It *is* implemented in the multi-collector loop
   (``survey_multi.py:373``), and an empirical run with
   ``--checkpoint-interval 5`` emitted three ``Checkpoint written to
   <output>.partial`` lines with ``os.replace`` succeeding each time.

   The ``.partial`` file was absent whenever it was checked only because
   ``survey.py:1323`` **deliberately deletes it on successful completion**
   ("the complete census is now on disk; drop any stale checkpoint").  Every
   check had been made *after* the run finished, so the file had already been
   cleaned up as designed.

   An earlier note in this file claiming checkpointing was "only in the
   single-adapter loop" was also wrong and is withdrawn.

   **The one real gap (now FIXED):** the multi-collector checkpoint was gated on
   ``and listening``, so it stopped at the end of the listen window and never
   covered the **enumeration tail** — the longest, riskiest phase, where the
   aborts actually landed, and where the worker keeps stamping
   ``enumerated_by``/``enumerated_at`` into the census.  The gate is removed.
2. **Contradictory StopDiscovery log:** ``StopDiscovery failed on
   /org/bluez/hci0: org.bluez.Error.Failed: No discovery started
   (Discovering=True)`` — the message says no discovery started while
   simultaneously reporting ``Discovering=True``.  Degraded to a no-op, so
   cosmetic, but the condition is reported wrongly.
3. **``GIVE_UP`` mismatch still present:** 107 × "Giving up … after 2 attempts"
   against a controller announcing "max 3 attempts".

**Next step:** promote the env gate to a real, scoped decision — the survey
should run loop-free *by default* and acquire the loop only when a
signal/callback-driven feature is actually requested. Option P (separate
enumerator process) is no longer needed for the survey path, and is
reserved for modes that genuinely need both a loop and a worker thread.

#### B.19–B.23 Collector/enumerator hardening (2026-09-06 → 2026-09-08) — CONSOLIDATED

This block replaces ~900 lines of run-by-run narrative (Runs A–I). Shipped
behaviour now lives in `changelog.md`; the two pieces of durable architectural
knowledge were moved to the documents that own those areas. What stays here is
what still constrains or blocks future work.

##### Relocated — do not duplicate here

| Knowledge | Now lives in |
|---|---|
| `SIGABRT` root cause: data race on the process-global default `GMainContext`; why `threads_init()` and private connections cannot fix it; the "never drive GATT from the loop thread" rule | `mainloop_architecture.md` → "Thread-safety constraint" |
| The ~42-minute collector ceiling, its five reproductions, and the eight hypotheses eliminated by measurement | `d-bus-reliability.md` → "the ~42-minute collector ceiling" |
| Operator-facing behaviour of `--no-mainloop`, `--max-enum-devices`, `--stall-rounds`, `--metrics-interval`, `--segment-time` | `survey_mode.md`, summarised in `cli_usage.md` |
| What shipped and when | `changelog.md` |

##### Accepted policies — binding on future work

1. **The 10s `ConnectDevice` bound is enumerator-only.** It exists to stop a
   25s D-Bus default from serialising the enum tail. Do not generalise it to
   interactive connects, where a slow-but-real device deserves the wait.
2. **`--no-mainloop` is passive-enumeration only, and must warn.** Deep
   enumeration needs the loop. The flag is refused with `--listen-monitor` and
   pair mode, refused outright in the debug shell, and prints its losses on use.
3. **Report attempts honestly.** Where the effective budget differs from
   `MAX_ATTEMPTS`, the banner must say what will actually happen (see C-4).
4. **Host BT state is only mutated under `--auto-recover`.** The power-cycle
   rung is gated on it, and a failed cycle must tell the operator the adapter
   may be left powered off, with the restore command.
5. **A per-target timeout must be applied inside the attempt loop**, not around
   it, or a 30s budget silently becomes 90s across three attempts.

##### Open

* **C-4 — `GIVE_UP` after 2 attempts vs `MAX_ATTEMPTS = 3`** (`enum_controller.py:113`,
  `:360-384`; `gatt_enumeration.md`). Behaviour is deliberate and stays; the
  banner and comment must stop claiming 3. Policy accepted, edit not yet made.
* **C-8 — `manager._devices` is unbounded on the collector path.** Confirmed
  unbounded, but measurement shows it is *not* the memory growth
  (`sig_devs` held at 1 across two instrumented runs), so this is tidiness, not
  a leak fix.
* **C-10 — no recovery rung beneath D-Bus.** Every D-Bus remedy failed in five
  runs (0 of 2 re-arms plus a failed power cycle, every time). `rfkill` /
  `hciconfig down,up` is the only untried path. Only worth building if the
  stall is shown to be controller-level *and* recoverable — otherwise
  segmentation already covers the operational need.
* **C-12 — the stall itself is unexplained.** See `d-bus-reliability.md` for
  what has been ruled out. Mitigated by segmentation, not fixed.
* **Diagnostic gap** — whether the *peer* adapter stays serviceable while one is
  wedged is untested; Run G produced no successful `hci1` call after the stall.
  Probing the peer inside `_adapter_diagnostics()` would separate "this
  controller stalled" from "bluetoothd stopped serving us" and is a few lines.
* **Leftover ACL** — sweep at worker *start* as well as in `finally`, reusing
  `disconnect_connected_on_session` (`enumerator.py:144`). Proven necessary: a
  run whose only two successes were inherited ACLs.
* **`--live` 1 Hz spam in the enum tail** — throttle to state change.
* **DB query storm** — `_recently_enumerated` caches only truthy stamps
  (`survey_enum.py:106-118`), so unstamped MACs are re-queried by `queue_depth`
  every second under `_DB_LOCK` (`_connection.py:886`).
* **`--checkpoint-interval` still defaults to 0**, so nothing is written unless
  asked for. The `listening` gate that also suppressed it during the enum tail
  is fixed. Worth reconsidering the default now that long runs are segmented.

##### Closed, with the reason — do not reopen

* **Option A, "private D-Bus connection for the enumerator" — ABANDONED.** The
  premise was that a private connection would decouple enumerator traffic and
  remove cross-thread mutation at the crash site. It cannot: `DBusGMainLoop(set_as_default=True)`
  attaches every connection, `private=True` included, to the default main
  context, so the loop thread dispatches it anyway (verified 2026-09-06, and
  root-caused 2026-09-08). `bus.py` ships the per-thread connections for their
  smaller real benefit — separate message queues and pending-call tables — and
  its docstring states plainly that it does not fix the abort. **Keep `bus.py`;
  do not attempt isolation this way.**
* **C-5, "round cadence scales with census size" — RETRACTED.** Cadence
  overruns correlate with D-Bus timeouts once the adapter stops answering, not
  with census growth. The residual real item is bounding harvest and
  property-probe timeouts, which matters for stall-detection latency rather
  than throughput.
* **C-6, `bus.py` — KEEP.** Its rationale was already correct and hedged; see
  the relocation table above.
* **C-7, `_services_resolved_pending` — REMOVED.** Write-only field (two
  `Store` sites, zero `Load`). The `if self._bus_is_private:` branch that
  performs the deferral is retained; only the dead marker went.
* **C-9, the ~2.1 MB/round retention — DROPPED as not operationally
  relevant.** 200 MB/hour on a 15 GB host threatens nothing, and it is not the
  stall trigger: Run H died at 197.5 MB where Run G died at 207.7 MB. Four
  candidate mechanisms were eliminated by measurement (`d-bus-reliability.md`).
* **Silent stall — FIXED.** `Adapter1.Discovering` is useless as a health
  check because discovery is per-D-Bus-client state; `SurveyCensus.progress_counters()`
  is the signal instead, since neither counter advances on a cached `Device1`
  re-read. This also explains the "contradictory" `StopDiscovery failed … No
  discovery started (Discovering=True)` log once filed as cosmetic: a
  *different* client held discovery. Both correct; not a bug.
* **The `1/3for` / `2attempts` spacing report — NOT A BUG.** Terminal rendering
  artifact, not a logging defect.

##### Corrections to earlier entries in this tracker

Recorded because each one would have sent the next reader the wrong way:

* The claim that `bus.py`'s justification was "definitively disproved" and its
  docstring "draws the wrong conclusion" was **wrong**; Valgrind confirmed that
  docstring. Nearly cost a sound module.
* The checkpoint bug was first attributed to checkpointing being absent from
  `run_multi_collector`. It was present but gated on `listening`.
* The stall fix was first credited to re-arming alone; in five runs re-arming
  has never once succeeded. What actually helps operationally is honest
  reporting plus segmentation.
* `signals._devices` was described as pinning every `_LEDevice`. Instrumented
  runs show it holding 1 in loop-free mode.
* A run was reported dead when the PID checked belonged to the shell wrapper;
  `pgrep -f` matches the wrapper as well as the interpreter.

##### Why the testing was worth it, and where it was not

Valgrind converted a non-deterministic heap abort into a named, cited race, and
`--no-mainloop` removed it — that unblocked every long run. Stall detection
turned a run that was silently dead for 70% of its duration into one that says
so. Against that, the memory investigation consumed the most effort for no
operational gain and should have been dropped once 200 MB/hour was shown to be
harmless; and this tracker absorbed ~1800 lines of narrative that belonged in
the changelog and the two architecture documents from the start.


### Phase 5 — Device-Type Classification Accuracy (2026-05-08) – COMPLETE

- [x] `_merge_entry()` now uses `DeviceTypeClassifier` result from `entry["type"]` via `_resolve_device_type()` helper instead of blind transport label; `_CLASSIFIER_TYPE_MAP` maps `"br/edr"` → `"classic"`
- [x] `DeviceSighting.is_cached` flag tracks cached/bonded devices with `rssi=None`; auto-clears on re-sight with real RSSI; emitted in `objects`/`grouped` output
- [x] `--exclude-cached` CLI flag in `bleep survey` and `bleep debug survey start`; wired through `filter(exclude_cached=)`
- [x] RSSI 0 dBm fix: `entry.get("rssi") or entry.get("rssi_last")` → explicit `None` check
- [x] 23 new unit tests (90 total): classifier-aware merge, cached provenance, exclude filter, RSSI 0 handling, output format

### Phase 6 — Extended Features (2026-05-08) – COMPLETE

- [x] Beacon fingerprinting: track manufacturer data / service data changes across rounds
  - `DeviceSighting` extended with `manufacturer_data`, `service_data`, `tx_power`, `appearance`, `fingerprint_changed`
  - `_merge_entry()` updated with union/longest-wins merge policies
  - `format_objects()` / `format_grouped()` hex-encode `bytes` payloads in JSON output
  - 12 new unit tests covering merge semantics, JSON roundtrip, format inclusion/omission
- [x] Survey resume from DB: pre-seed census with existing observation entries
  - `SurveyCensus.seed_from_db()` paginates `observations.get_devices()`, converts ISO timestamps, sets `sighting_count=0`
  - `--resume-db` CLI flag added to `bleep survey` and `bleep debug` `survey start`
  - DB-seeded devices excluded by default `--min-sightings 1`; use `--min-sightings 0` to include
  - 8 new unit tests covering loading, deduplication, filter behavior, live upgrade, graceful degradation
- [x] Adaptive round timing: auto-adjust `--round-time` based on discovery rate
  - `--adaptive` flag enables discovery-rate-based round time adjustment
  - `--adaptive-min` (default 10s) and `--adaptive-max` (default 60s) clamp the range
  - Zero new devices → halve round time; >=3 new devices → extend by 10s
  - `--live` output includes `rt=Ns` when adaptive is active
  - 5 new unit tests covering flag parsing, shrink/grow behavior, min floor

---

## MAC Validation — Reject Incomplete/Invalid MACs (v2.8.4, 2026-05-07) – COMPLETE

**Problem**: The BLEEP database contained invalid MAC entries observed in terminal
output: `4:A2:F9:BC:8E:95` (short first octet, only 1 hex digit instead of 2) and
`/ORG/BLUEZ/HCI0/DEV_F4_B6_88_0B_90_22` (raw D-Bus path stored verbatim).  Root
cause was the `_normalize_mac()` fallback `return mac.upper()` which stored any
unparseable string without validation.

**Policy**: It is preferable to drop a MAC than to zero-pad or guess.

**Fix**: Changed `_normalize_mac()` return type to `Optional[str]`, returning
`None` for any input that does not resolve to a strict 6-octet `XX:XX:XX:XX:XX:XX`
format.  Added `None`-guard early-return in all ~22 public functions in
`observations.py` that call `_normalize_mac()`.

**Files modified**: `bleep/core/observations.py`,
`tests/test_aoi_augmentation.py` (8 new rejection tests),
`tests/test_observations_characteristics.py` (MAC fixture fix),
`tests/test_observations_media.py` (MAC fixture fix).

**Test results**: 122 AoI tests pass, 299/324 full suite pass (10 pre-existing
failures unrelated to this change).

---

## AoI Augmentation — Full Implementation (v2.8.4, 2026-05-07) – COMPLETE

**Goal**: Implement the complete AoI augmentation plan including multi-transport
scan pipeline, device type classification, SDP discovery, pairing probe,
deep re-enumeration, enhanced analysis methods, v11 schema, and report generation.

**Files modified**:

| File | Change |
|------|--------|
| `bleep/modes/aoi.py` | Complete rewrite: removed ~200 lines dead code; added `_validate_mac`, `_classify_device`, `_discover_sdp`, `_probe_pairing`, `_perform_deep_reenumeration`, `_has_auth_annotation`, `_normalise_service_element`, `_scan_target`; wired `--deep`, `--timeout`, `--no-db`, `--connectionless`, `--address` on scan; `db list` action; v11 field merging in db import/sync |
| `bleep/analysis/aoi_analyser.py` | Added `db_only` param; `_analyse_sdp_records()`, `_analyse_pairing_profile()`, `_analyse_post_pair_delta()` methods; service list normalisation in `analyse_device()`; v11 field merging in `save_device_data()` and `analyse_device()`; safe `.get()` in `_generate_recommendations()`; report generators include SDP/pairing/delta sections; services section handles mixed types |
| `bleep/core/observations.py` | Schema v11: `pairing_profile`, `sdp_summary`, `post_pair_delta` columns; v10→v11 migration; `store_aoi_analysis()` persists v11 fields; `get_aoi_analysis()` returns v11 fields; `_normalize_mac()` hardened with regex, D-Bus path extraction; `import re` added |
| `bleep/cli.py` | `import signal` + `SIGPIPE` handler; `"db"` in `known_subcommands` |
| `bleep/ble_ops/le/scan.py` | `LOG__GENERAL` → `LOG__DEBUG` on `_native_scan` debug print |
| `tests/test_aoi_augmentation.py` | 58 tests covering all new functionality |
| `tests/test_device_type_integration.py` | Schema version assertion: 10 → 11 |

**Implementation details**:

- **Scan pipeline**: `_scan_target()` follows classify → GATT → SDP → pair → deep sequence
- **Device classification**: Uses `DeviceTypeClassifier.classify_with_mode()` from `bleep/analysis/device_type_classifier.py`
- **SDP discovery**: Calls `discover_services_sdp()` from `bleep/ble_ops/classic/sdp.py` with `connectionless` flag support
- **Pairing probe**: Uses `system_dbus__bluez_device__classic.pair()` via D-Bus
- **Deep mode**: Post-pair re-enumeration via `EnumerationController` (LE) and SDP (Classic)
- **v11 field flow**: `device_data["sdp_summary"]`, `device_data["pairing_profile"]`, `device_data["post_pair_delta"]` → merged into analysis dict → persisted via `store_aoi_analysis()`

---

## AoI Service-Data Normalisation, MAC Validation & Output Fixes (v2.8.4, 2026-05-07) – COMPLETE

**Goal**: Fix six issues discovered during live AoI testing — `unhashable type: 'dict'` crashes in analyze/report, `'dict' has no attribute 'strip'` in db sync/import, debug log leaking to user output, D-Bus object paths stored as MACs, and `BrokenPipeError` on piped output.

**Root cause**: `observations.get_device_detail()` returns `services` as `List[Dict]` (full SQLite rows), while AoI JSON files store `services` as `List[str]` (UUID strings). Code in `analyse_device()`, `db import`, and `db sync` assumed the list-of-strings shape, crashing when DB-loaded data was supplied.

**Files modified**:

| File | Change |
|------|--------|
| `bleep/analysis/aoi_analyser.py` | `analyse_device()` list branch normalises dict elements via `entry.get("uuid")` |
| `bleep/modes/aoi.py` | `db import` (line ~776) and `db sync` Step 2 (line ~880) comprehensions pass through dicts |
| `bleep/ble_ops/le/scan.py` | Changed `LOG__GENERAL` → `LOG__DEBUG` on `_native_scan` debug print |
| `bleep/core/observations.py` | `_normalize_mac()` now validates format, extracts MACs from D-Bus paths; `import re` moved to top-level |
| `bleep/cli.py` | Added `signal.signal(signal.SIGPIPE, signal.SIG_DFL)` in `main()` |
| `tests/test_aoi_augmentation.py` | +11 tests (3 service normalisation, 8 MAC validation) → 54 total |
| `tests/test_device_type_integration.py` | Schema version assertion updated 10 → 11 |

**Checklist**:
- [x] F1: `analyse_device()` list branch handles both UUID strings and DB row dicts
- [x] F2: `db import` service comprehension normalised
- [x] F3: `db sync` Step 2 service comprehension normalised
- [x] F4: `[DEBUG] _native_scan returning` changed from `LOG__GENERAL` to `LOG__DEBUG`
- [x] F5: `_normalize_mac()` validates MAC format and extracts from D-Bus paths
- [x] F6: SIGPIPE handler added to `cli.py:main()`
- [x] Tests: 54/54 AoI tests pass, 192/192 broader tests pass (1 pre-existing preflight failure excluded)
- [x] Documentation: changelog, todo_tracker, learned-memories updated

---

## Audio profile activation, recording reliability & profile identity fixes (2026-04-21) – COMPLETE

**Goal**: Close the behavioural gaps catalogued in
`workDir/Audio/README.audio-troubleshooting-once-more` — divergent
`audio-profiles` output between connect paths, `"Active Profile: off"`
mis-reporting, `[-] Recording failed` false negatives, HSP capture
nodes mis-classified as A2DP Source, and inconsistent BlueZ
`bluez_card.*` presence.

**Five fixes, all covered by `tests/test_audio_regressions.py`**:

| # | Scope | Files | Validation |
|---|-------|-------|------------|
| 1 | Opt-in BlueZ profile activation after RFCOMM bring-up; `--no-profiles` CLI flag on `bleep classic-connect` / `bleep connect` / `bleep pair` | `bleep/pairing/__init__.py`, `bleep/modes/pair.py`, `bleep/modes/classic_connect.py`, `bleep/cli.py` | `test_fix1_svc_map_has_audio_uuid_accepts_both_forms`, `test_fix1_activate_profiles_false_skips_device_connect`, `test_fix1_activate_profiles_true_calls_device_connect_only_for_audio` |
| 2 | `get_profiles_for_card` regex widening + pattern/name normalisation in `identify_bluetooth_profiles_from_alsa` | `bleep/ble_ops/audio/audio_tools.py` | `test_fix2_regex_accepts_hyphenated_profiles`, `test_fix2_pattern_normalisation_matches_hyphen_and_underscore` |
| 3 | `amusica status` surfaces Active profile explicitly | `bleep/modes/amusica.py` | `test_fix3_amusica_status_prints_active_profile` |
| 4 | `record_from_source` uses `Popen`+`SIGINT` timebox with WAV-header success guard and stderr DEBUG capture | `bleep/ble_ops/audio/audio_tools.py` | `test_fix4_record_returns_true_on_sigint_with_valid_output`, `test_fix4_record_returns_false_on_empty_output` |
| 5 | `pw-dump` `api.bluez5.profile` / `codec` / `device.profile.name` extraction; classifier prefers props over node-name | `bleep/ble_ops/audio/audio_tools.py` | `test_fix5_pw_dump_bluez5_props_are_extracted`, `test_fix5_classifier_prefers_bluez5_profile_over_node_name` |

Resolution narrative and manual verification recipe are documented in
the "Resolution Notes (2026-04-21)" section of
`workDir/Audio/README.audio-troubleshooting-once-more`.
Changelog entry: `bleep/docs/changelog.md` → "Audio profile activation,
recording reliability & profile identity fixes (2026-04-21)".

---

## MediaEndpoint1 Contention Pre-flight (2026-04-17) – COMPLETE

**Goal**: Before `MediaStreamManager._acquire_via_endpoint()` registers a
BLEEP-owned `MediaEndpoint1` and cycles the device connection, detect whether
another endpoint provider (BlueALSA, PipeWire bluez5 SPA plugin, or PulseAudio
`module-bluetooth-discover`) has already claimed the complement role.  When a
competing endpoint is registered, BlueZ's `a2dp_select_eps` frequently picks
the pre-existing endpoint during AVDTP re-discovery, so BLEEP's `SetConfiguration`
callback is never invoked and `wait_for_transport()` times out.

**Symptom**: Terminal logs show:

* BlueZ is happy, device is `Connected=yes`, profile list includes A2DP.
* `audioplay` hangs for 15 s and emits the timeout raised from
  `_acquire_via_endpoint`.
* `bluealsa-cli list-pcms` (or `pw-cli list-objects | grep bluez_output`) shows
  the complement profile already claimed by another daemon.

**Design outline** (refined 2026-04-17 after the structured-status /
BlueALSA-correlator diagnostic landed):

Two-layer probe.  BlueZ's `GetManagedObjects()` returns *BlueZ-owned* objects
only (remote-device SEPs at `/org/bluez/hciN/dev_.../sepN`, transports at
`.../fdN`); it does **not** republish externally registered `MediaEndpoint1`
objects.  Those live on the registering client's bus name under whatever path
the client chose (BLEEP: `/bleep/media/endpoint`; BlueALSA: `/org/bluealsa/…`;
PipeWire: `/MediaEndpoint/…`).  Enumeration therefore walks D-Bus *names*, not
BlueZ managed objects.

1. **Primary probe — zero-cost inference.**  Reuse
   `_check_bluetooth_audio_stack_detailed()` (structured per-backend status)
   and `AudioToolsHelper.list_bluealsa_pcms()` (MAC-scoped BlueALSA PCMs).
   Any backend whose `status == "active"` is synthesised as an
   `EndpointOwner` for each complement UUID that backend is known to register
   by default (A2DP Source + A2DP Sink + HFP AG + HFP HF for all three
   backends).  This alone is sufficient to pre-empt the 15 s timeout in every
   deployment we have observed in terminal logs.
2. **Deep probe (opt-in, `deep_probe=True`).**  Authoritative enumeration via
   `org.freedesktop.DBus.ListNames` → per-name `Introspect` for
   `<interface name="org.bluez.MediaEndpoint1">` → `GetConnectionUnixProcessID`
   → `/proc/<pid>/comm` / `cmdline`.  Every call goes through
   `bleep.dbus.timeout_manager.call_method_with_timeout` so the scan cannot
   hang.  Runs only when the caller explicitly requests it
   (`audiocfg --endpoints`, `mediaenum --endpoints`) or when the primary probe
   is ambiguous.
3. **Classify severity.**
   * `"block"` — BlueALSA daemon `active` and the complement UUID is one
     BlueALSA always claims.  BlueZ will race-lose against BlueALSA with very
     high probability (observed failure mode).
   * `"warn"` — `_detect_audio_stack_conflicts()` emitted a warning, or the
     deep probe found ≥1 non-BLEEP competitor.
   * `"info"` — only BLEEP itself owns the complement UUID.
   * `"none"` — no audio backends active.
4. **Runtime gate.**  Insert the primary probe at the top of
   `MediaStreamManager._acquire_via_endpoint` (after `complement_uuid` is
   computed, before `BleepMediaEndpoint.register()`).  On `severity == "block"`
   and without `force_endpoint=True`, raise before registering/cycling (saves
   15 s + a device disconnect).  On `"warn"`, print and proceed.  The
   existing `wait_for_transport` timeout message re-injects the report when
   the primary probe missed the conflict.
5. **User overrides.**  New `--force-endpoint` flag on `audioplay`,
   `audiorec` (debug shell + CLI) bypasses the gate.
6. **Surfaces.**  `audiocfg` prints a new "Endpoint contention" section (fast
   path by default; `--endpoints` enables the deep probe).  `mediaenum`
   annotates printed endpoints with owner attribution when `--endpoints` is
   passed.  `audio-recon` emits a one-line summary.
7. **Tests.**  Extend `tests/test_preflight.py`: primary probe (monkeypatched
   backend snapshots), deep probe (monkeypatched `SystemBus` + canned
   introspection XML for fake bus names), runtime gate (spy on
   `BleepMediaEndpoint` instantiation), `--force-endpoint` override.

Implementation gate (why this was deferred until now): the structured
`audiocfg` diagnostic and BlueALSA correlator had to ship first so real
failure reports could inform the edge cases (multi-adapter hosts, partial
BlueALSA/PipeWire coexistence).  Those shipped 2026-04-17 and are validated;
this item may now proceed.

| # | Deliverable | Status | Files |
|---|-------------|--------|-------|
| 1 | `EndpointOwner` / `EndpointContentionReport` dataclasses + primary probe | [x] | `bleep/core/preflight.py` |
| 2 | Deep probe (`ListNames` + `Introspect` + PID attribution, timeout-guarded) | [x] | `bleep/core/preflight.py`, uses `bleep/dbus/timeout_manager.py` |
| 3 | `MediaStreamManager` pre-flight gate + `force_endpoint` override + amended timeout error | [x] | `bleep/dbuslayer/media_stream.py` |
| 4 | Debug-shell + CLI surfaces (`audiocfg --endpoints`, `mediaenum --endpoints`, `--force-endpoint`) | [x] | `bleep/modes/debug_media.py`, `bleep/cli.py` |
| 5 | `audio-recon` one-line contention summary | [x] | `bleep/ble_ops/audio/audio_recon.py` |
| 6 | Unit tests (primary, deep, runtime gate, override) | [x] | `tests/test_preflight.py` (9 new tests) |
| 7 | Changelog + this entry status + audio/d-bus doc updates | [x] | `bleep/docs/changelog.md`, `bleep/docs/todo_tracker.md` |

---

## MAP CLI Folder Enumeration Fix (2026-04-15) – COMPLETE

**Goal**: Fix the `classic-map folders` and `classic-map list` CLI commands so they correctly enumerate the full MAP folder hierarchy on devices with deep structures (e.g. `telecom/msg/{inbox,draft}`) and gracefully handle non-leaf folder access.

**Root cause**: The CLI `folders` action called the flat `list_folders()` (single `ListFolders` at the MAP root) instead of the recursive `list_folder_tree()` that already existed and was used by the debug-mode `cmap folders` command.  The CLI `list` action had no recovery logic for "Bad Request" errors from non-leaf folders, unlike its debug-mode counterpart.

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | `cli.py` `folders` action re-wired to `list_folder_tree()` + `collect_leaf_paths()` with indented tree output | [x] |
| 2 | `cli.py` `list` action "Bad Request" recovery: enumerate tree, suggest valid leaf paths | [x] |
| 3 | Future work item for auto-resolve intermediate folders added to todo_tracker | [x] |
| 4 | Changelog updated with Unreleased entry | [x] |

---

## Classic Connect CLI & Debug Fix (2026-03-31) – COMPLETE

**Goal**: Add a working Bluetooth Classic connection path that bypasses the `Device1.Connect()` profile-handler requirement, both as a new `bleep classic-connect` CLI command and as fixes to the debug mode `connect`/`cconnect` commands.

**Root cause**: BlueZ `Device1.Connect()` only succeeds when a profile handler is registered for at least one of the remote device's services.  For devices exposing raw RFCOMM services without a BlueZ profile handler, it fails with `br-connection-profile-unavailable`.  The working path is SDP discovery + raw RFCOMM socket.

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | `classic_connect_sdp_rfcomm()` shared helper in `bleep.pairing` | [x] |
| 2 | `bleep classic-connect` CLI command (`modes/classic_connect.py` + `cli.py` subparser) | [x] |
| 3 | Debug `cconnect` — SDP+RFCOMM fallback when `Device1.Connect()` fails | [x] |
| 4 | Debug `connect` → `_connect_classic` — pass `debug_state` to `_c_enum` | [x] |
| 5 | `bleep connect` — auto-detect Classic transport and route to classic-connect | [x] |
| 6 | `connect_and_enumerate__bluetooth__classic` — skip redundant auto-pair for already-paired devices | [x] |
| 7 | Documentation: changelog, debug_mode, todo_tracker | [x] |

---

## Pairing CLI Expansion (2026-03-31) – COMPLETE

**Goal**: Augment BLEEP pairing capabilities with a first-class `bleep pair` CLI command, pre-pair status checks, forced bond reset, and eliminate duplicated pairing helpers across modules.

**Status**: Complete.

### Deliverables

- [x] **P1** `bleep/pairing/__init__.py` — Shared pairing helpers: `find_device_path`, `resolve_device_for_pair`, `remove_stale_bond`, `register_pair_agent`, `check_pair_status`, `report_pair_status`
- [x] **P2** `bleep/modes/pair.py` — New CLI handler for `bleep pair` with full flag parity to the debug-mode `pair` command
- [x] **P3** `bleep/cli.py` — Registered `pair` subparser and dispatch
- [x] **P4** `bleep/modes/debug_pairing.py` — Refactored to import from `bleep.pairing`; added `--check` and `--reset` flags; pre-pair status check before pairing
- [x] **P5** `bleep/dbuslayer/device_classic.py` — Added `is_paired()`, `is_trusted()`, `is_bonded()`, `is_connected()` for API parity with LE wrapper
- [x] **P6** `bleep/dbuslayer/pin_brute.py` — `_remove_stale_bond` delegates to shared `bleep.pairing.remove_stale_bond`
- [x] **P7** `bleep/ble_ops/classic/connect.py` — `_do_auto_pair` uses shared `register_pair_agent` and `find_device_path`
- [x] **P8** `bleep/modes/agent.py` — `_get_device_path` delegates to shared `resolve_device_for_pair`
- [x] **P9** Documentation updated: `changelog.md`, `debug_mode.md`, `pairing_agent.md`, `todo_tracker.md`

---

## MAP bMessage Format Reference & Test Corpus (2026-03-30) – COMPLETE

**Goal**: Document the MAP bMessage envelope specification, validate the LENGTH calculation rules against the live codebase, create a comprehensive test message corpus covering all MAP message types and structural variations, and produce tooling for batch validation and push operations.

**Status**: Complete.

### Deliverables

- [x] **D1** `bleep/docs/map_bmessage_format.md` — Full bMessage format reference with inline examples for all 5 types: envelope structure, LENGTH calculation, nested BENV for forwarded messages, bulk operation analysis, PushMessage args, ListMessages filter fields, implementation code-path table
- [x] **D2** `bleep/docs/bl_classic_mode.md` §2.9 updated with bMessage format summary, bulk operation notes, cross-reference to new doc
- [x] **D3** `bleep/docs/README.md` TOC updated with MAP bMessage format reference link
- [x] **D4** `bleep/docs/changelog.md` Unreleased section updated with format reference entry

### Key findings

- **One file = one message**: `PushMessage` accepts exactly one bMessage file per call; no batch upload in the MAP spec. Multiple `BEGIN:BMSG` blocks in a single file are not valid.
- **Nested BENV**: Forwarded/attached messages use nested `BEGIN:BENV`/`END:BENV` blocks, each with its own VCARD and BBODY/LENGTH.
- **LENGTH precision**: The `LENGTH:` field must match the exact byte count from `BEGIN:MSG\r\n` through `END:MSG\r\n` inclusive (CRLF required). Mismatches cause silent device-side rejection despite successful OBEX transfer. BLEEP now auto-normalizes LF→CRLF and recalculates LENGTH before every push.
- **Bulk download**: Enumerate folders → list messages per folder → get each handle. Scriptable via `bleep.ble_ops.classic.map` API.
- **PushMessage args**: `Transparent`, `Retry`, `Charset` are defined in the BlueZ API but not currently exposed by BLEEP (empty dict passed).

---

## MAP Bulk Download & Upload Commands (2026-03-30) – COMPLETE

**Goal**: Implement `cmap download-all` and `cmap push-all` debug commands with corresponding operations-layer API (`download_all_messages`, `push_all_messages`), and refactor `_collect_leaf_paths` from the debug layer into the operations layer as a public utility.

**Status**: Complete.

### Deliverables

- [x] **D1** `bleep/ble_ops/classic/map.py` — `collect_leaf_paths()` public utility (moved from debug layer)
- [x] **D2** `bleep/ble_ops/classic/map.py` — `download_all_messages()` with folder tree walk, per-folder session, pagination support, progress callback
- [x] **D3** `bleep/ble_ops/classic/map.py` — `push_all_messages()` with bMessage validation, dry-run, continue-on-error, progress callback
- [x] **D4** `bleep/modes/debug_classic_obex.py` — `cmap download-all [dest] [--folders] [--count N]` sub-command
- [x] **D5** `bleep/modes/debug_classic_obex.py` — `cmap push-all <dir|glob> [folder] [--dry-run]` sub-command
- [x] **D6** `bleep/modes/debug_classic_obex.py` — `_collect_leaf_paths` now delegates to `map.collect_leaf_paths`
- [x] **D7** `bleep/docs/map_bmessage_format.md` §7 updated with debug commands and API examples; §11 table updated
- [x] **D8** `bleep/docs/bl_classic_mode.md` §2.9 updated with download-all/push-all usage examples
- [x] **D9** `bleep/docs/changelog.md` Unreleased section updated

### Design decisions

- **One session per folder for download**: `_populate_message_objects` creates D-Bus message objects within the calling session; handles are only valid within that session. Opening one `MapSession` per folder and downloading all messages before moving to the next avoids stale object paths.
- **One session per push for upload**: Keeps the existing `push_message` session-per-call pattern for maximum device compatibility; OBEX sessions can become stale after a push.
- **Continue-on-error**: Both bulk operations log per-item failures and continue the batch, matching the `cmap peek` pattern.
- **`.bmsg` extension**: Downloaded files use `.bmsg` for immediate round-trip compatibility with `push-all`.

---

## MAP bMessage CRLF Normalization & LENGTH Fix (2026-03-30) – COMPLETE

**Goal**: Fix silent push failures caused by bMessage files using LF line endings and LF-based LENGTH values, which are silently rejected by the remote Message Access Server despite OBEX transfer success.

**Status**: Complete.

### Root cause

The MAP specification mandates CRLF (`\r\n`) line endings. Test bMessage files and user-crafted files used bare LF (`\n`), causing the LENGTH field to undercount once the MAS expected CRLF. BlueZ's `obexd` passes file content as-is via `obc_transfer_put` — it does not normalize line endings. The MAS silently discards messages with incorrect LENGTH or non-CRLF formatting even when the OBEX transfer itself succeeds.

### Deliverables

- [x] **D1** `bleep/ble_ops/classic/map.py` — `normalize_bmessage(raw)` helper: converts bare LF→CRLF, recalculates all LENGTH fields (including nested BENV blocks)
- [x] **D2** `bleep/ble_ops/classic/map.py` — `_normalize_for_push(filepath)` temp-file wrapper integrated into `push_message()`, covering all push paths (single, batch, CLI)
- [x] **D3** `bleep/modes/debug_classic_obex.py` — `_validate_bmsg_length()` updated to warn about LF-only line endings and inform user about auto-normalization
- [x] **D4** `bleep/ble_ops/classic/map.py` — `push_all_messages()` dry-run path now reports whether each file will be normalized
- [x] **D5** `workDir/MAP/map_test_messages/*.bmsg` — All 10 test files converted to CRLF with correct LENGTH values
- [x] **D6** `bleep/docs/map_bmessage_format.md` §5 corrected: CRLF requirement documented, LF references removed, normalization chain documented
- [x] **D7** `bleep/docs/changelog.md` updated with fix entries

### Evidence

- Real messages downloaded from Samsung device via `cmap download-all` use CRLF and correct LENGTH (confirmed via hex dump)
- BlueZ `obexd/client/map.c` and `transfer.c` pass file content without modification to the OBEX layer
- BlueZ `test/map-client` reference implementation does not normalize line endings

---

## MAP push-all Session Exhaustion Fix (2026-03-30) – COMPLETE

**Goal**: Prevent transient OBEX session-creation timeouts when `cmap push-all` pushes many files in rapid succession.

**Status**: Complete.

### Root cause

Each `push_message()` call creates and tears down a `MapSession` (OBEX session).  When 8+ pushes execute back-to-back with no inter-push delay, `obexd` (or the remote MAS) fails to release the prior session's resources before the next `CreateSession` call, producing `org.bluez.obex.Error.Failed: Timed out waiting for response`.  The BlueZ reference `test/map-client` is interactive (inherent human delay), so this condition never occurs in the reference implementation.

### Deliverables

- [x] **D1** `bleep/ble_ops/classic/map.py` — `push_all_messages()` gains a `delay` parameter (default 1.5s) that inserts a cooldown between consecutive pushes
- [x] **D2** `bleep/ble_ops/classic/map.py` — Automatic single-retry with 3s backoff on transient session-creation timeouts
- [x] **D3** `bleep/modes/debug_classic_obex.py` — `cmap push-all` gains `--delay N` flag
- [x] **D4** `bleep/docs/map_bmessage_format.md` §7 updated with delay/retry documentation
- [x] **D5** `bleep/docs/changelog.md` updated with fix entry

---

## BLEEP v2.8.0 — Augmentation, Expansion, and Improvement Plan (2026-03-25) – IN PROGRESS

**Goal**: Deliver the v2.8.0 feature set as specified in `workDir/BigMoves/README.v2.8.0`. Work is organised into Pre-Work (v2.7.x finalization), Main Work (ten feature areas), a Bonus objective (audio capture & transcription), and Final Work (documentation, review, changelog).

**Version**: `bleep/__init__.py` at `2.8.0` — all Pre-Work, Main Work (M1–M10), Bonus, and Final Work complete.

**Pre-Work Status**: All P0 tasks completed (2026-03-26). Additionally: backward-compat stubs removed (all imports use canonical subpackage paths), schema version persistence bug fixed.

### Dependency Graph

```
Pre-Work (P0-1 through P0-9) — all independent, can parallelize
    │
    ├── P0-2 (cconnect GLib fix) follows pair --interactive lessons
    ├── P0-8 (ble_ops reorg) should complete before M1–M10
    ├── P0-9 (dual scan) — new for v2.8.0
    │
    v
Main Work — with dependencies:
    M3 (Agent PIN list, downgrade) ← M1 Stage 3 (PIN guessing)
    M6 (ALSA config) ← M1 Stage 4 (record/play config)
    M2 (RFCOMM probe, builds on existing SDP)
    M7.3 (RFCOMM binding) depends on M2 (RFCOMM probe)
    M5 (Device ID, uses bt_ref/uuids.py internally) — self-contained
    │
    v
Bonus (Audio Capture/Routing) — depends on M6 (capture/ALSA routing only; transcription is self-contained)
    │
    v
Final Work (F1–F3)
```

**Known test devices for acceptance validation** (from README.v2.8.0):
- `CC:50:E3:B6:BC:A6` — BLE CTF (no pairing, GATT services/characteristics)
- `D8:3A:DD:0B:69:B9` — Classic BT (requires PIN "12345", SDP enumeration)
- `53:4A:52:FE:01:38` — Audio device (media playback control, audio streaming)

---

### P0-1: Code, Variable, and Database Cleanup

**Status**: Done

**Existing structures**:
- Schema v10 in `bleep/core/observations.py` (line 55, `_SCHEMA_VERSION = 10`)
- MAC normalization via `_normalize_mac()` → `.upper()` (lines 511–524)
- v7→v8 migration uppercases MACs across all FK tables (lines 385–404)
- v8→v9 migration uppercases UUIDs
- FK protection via `_ensure_device_exists` on most upsert paths
- `safe_db_operation` retry decorator in `bleep/analysis/aoi_analyser.py` (lines 41–76)

**Remaining gaps to close**:
- [x] Audit media snapshot paths: added `_ensure_device_exists(cur, row["mac"])` to `snapshot_media_player()` and `snapshot_media_transport()` in `observations.py`
- [x] Extended CLI MAC normalization in `cli.py main()` to cover `pair`, `trust`, `untrust`, `remove_bond`, `source`, `sink` arguments
- [x] Add `characteristics`, `descriptors`, `device_type_evidence` to the table list in `maintain_database()` (confirmed present at line ~1306 in `observations.py`)
- [x] Fix pre-existing issue: `classic-scan` debug branch `d["class"]` → `d["device_class"]` (fixed in P0-1, confirmed in changelog v2.7.40)
- [x] Fix pre-existing issue: `bleep/modes/scratch.py` `timeout=` → `timeout_connect=` (fixed in P0-1, confirmed in changelog v2.7.40)
- [x] Ensure no loss of existing functionality after all cleanup

**Expected outcome**: Zero FK constraint failures under normal operation; uniform uppercase MACs from CLI through DB; complete maintenance reporting.

---

### P0-2: `cconnect` Blocking and GLib MainLoop Alignment

**Status**: Done

**Lesson from `pair --interactive`** (established pattern in `bleep/modes/debug_pairing.py` `_cmd_pair_single`):
1. `stop_glib_mainloop(state)` — free the default `MainContext` from the background daemon thread
2. Register the pairing agent on the main thread
3. `PairingAgent.pair_device()` runs a temporary `GLib.MainLoop` on the **main thread** (`bleep/dbuslayer/agent.py` line ~1048), which reliably dispatches `RequestPinCode` / `RequestPasskey` callbacks
4. `ensure_glib_mainloop(state)` — restart background loop for normal shell operation

**Why backgrounding `cconnect` is wrong**: Documented in `bleep/docs/agent_dbus_communication_issue.md` and `bleep/docs/mainloop_requirement_analysis.md` — `dbus.service.Object` method dispatch does **not** work when the `MainLoop` is only on a background thread. Agent callbacks would fail, breaking any auto-pair step.

**Current problem in `cconnect`** (`bleep/modes/debug_classic.py` line ~81):
- Calls `connect_and_enumerate__bluetooth__classic` which may internally call `ensure_default_pairing_agent()` + `device.pair()` without stopping the background GLib loop
- Agent dispatch during auto-pair is therefore unreliable
- The synchronous blocking of connection + SDP is **acceptable** — it reflects the reality of Classic BT operations

**Plan**:
- [x] Apply GLib stop/restart **only when pairing is needed**: detect when `connect_and_enumerate__bluetooth__classic` calls `ensure_default_pairing_agent()` / `device.pair()` and wrap that specific section with `stop_glib_mainloop(state)` / `ensure_glib_mainloop(state)`. When the device connects without pairing (no agent dispatch needed), skip the GLib stop/restart to avoid unnecessary churn and potential signal-handling disruption.
- [x] Investigate whether `classic_connect.py`'s internal auto-pair should use `PairingAgent.pair_device()` (temp main-thread loop) instead of `ClassicDevice.pair()` (blocking `Pair()` D-Bus call) for reliable agent dispatch
- [x] Add progress messages at each stage of `connect_and_enumerate__bluetooth__classic`:
  - `[*] Scanning for {mac}... (attempt {n}/{max})`
  - `[*] Connecting to {mac}...`
  - `[*] Pairing required — invoking agent...`
  - `[*] Running SDP discovery...`

**Expected outcome**: `cconnect` auto-pair works as reliably as `pair --interactive`; GLib stop/restart only applied when agent dispatch is needed; user has visibility into progress during synchronous operations.

---

### P0-3: Expand `pbap` Error Handling for "Transport got disconnected"

**Status**: Done

**Current state**: `cmd_pbap` in `bleep/modes/debug_classic.py` (line ~395) and CLI `classic-pbap` in `bleep/cli.py` (line ~1549) call `pbap_dump_async` from `bleep/ble_ops/classic/pbap.py`. Error handling uses `result.get("error")` and `print_detailed_dbus_error` but does not match `org.bluez.obex Error Failed: Transport got disconnected`.

**Plan**:
- [x] In `bleep/ble_ops/classic/pbap.py`, add specific detection of `"Transport got disconnected"` in the error string
- [x] Print actionable message: `[!] OBEX transport disconnected — the target device may not have 'Contact Sharing' enabled (check Bluetooth settings on the device).`
- [x] Mirror the same hint in `cmd_pbap` (debug mode) and CLI `classic-pbap` handler

**Expected outcome**: Users see a clear, actionable message directing them to enable Contact Sharing on the target device.

---

### P0-4: BlueALSA API Call Uniformity (`bluealsa-cli` vs `bluealsactl`)

**Status**: Done

**Current state**: Only `bluealsa-cli` is used — `bleep/core/preflight.py` (`shutil.which("bluealsa-cli")`) and `bleep/ble_ops/audio/audio_tools.py` (`self._bluealsa_cli_path`). Zero occurrences of `bluealsactl`. BlueALSA >= 4.0 renamed `bluealsa-cli` to `bluealsactl`.

**Plan**:
- [x] In `bleep/ble_ops/audio/audio_tools.py`, make the tool name resolve via fallback chain: `shutil.which("bluealsactl")` first, then `shutil.which("bluealsa-cli")`
- [x] Update `bleep/core/preflight.py` to check for either binary and report which was found
- [x] No functional changes to how the tool is invoked (same CLI arguments)

**Expected outcome**: BLEEP works with both older (`bluealsa-cli`) and newer (`bluealsactl`) BlueALSA installations.

---

### P0-5: Consistent CLI Adapter Reporting

**Status**: Done

**Current state** — inconsistent adapter guards:
- `bleep/cli.py` connect: catches `NotReadyError` → `"[!] Bluetooth adapter not ready"` (line ~617)
- `bleep/cli.py` classic-scan: checks `adapter.is_ready()` (line ~1192)
- Debug mode BLE: no explicit adapter guard before opening the shell
- Debug `cscan`: checks `adapter.is_ready()`
- Debug `cconnect`: surfaces as failed connect error, not clear adapter message

**Plan**:
- [x] Create `require_adapter(adapter_name=None)` in `bleep/core/preflight.py` — reuses `adapter.is_ready()`, raises `NotReadyError` with human-readable message
- [x] Apply at: debug shell startup (`bleep/modes/debug.py` `main()`), `cmd_cconnect`, `cmd_cscan`, and all CLI Bluetooth subcommands in `bleep/cli.py`

**Expected outcome**: Every BLEEP entry point that requires a Bluetooth adapter provides a uniform `[!] Bluetooth adapter not found or not ready` message.

---

### P0-6: BLE Debug Mode `services` Caching

**Status**: Done

**Current state**: `cmd_services` in `bleep/modes/debug_gatt.py` (line ~98) calls `state.current_device.services_resolved()`. If `is_services_resolved()` is `False`, logs and returns `[]` — no retry, no resolve trigger, no in-memory cache for later commands.

**Plan**:
- [x] In `cmd_services`, if `is_services_resolved()` is `False`, attempt `connect()` if not connected, then poll `ServicesResolved` D-Bus property for up to 10s
- [x] On success, store the result in `state.current_mapping` for reuse by subsequent commands
- [x] Add `--refresh` flag to force re-enumeration even when cached mapping exists

**Expected outcome**: `services` resolves proactively, caches in `DebugState`, re-enumerates only on `--refresh`.

---

### P0-7: Classic `cpan status` Freshness

**Status**: Done

**Current state**: `cmd_cpan` `status` in `bleep/modes/debug_classic_profiles.py` (line ~56) calls `pan_status(mac)` from `bleep/ble_ops/classic/pan.py`, which queries D-Bus `org.bluez.Network1` properties.

**Investigation result**: `classic_pan.py` `status()` calls `NetworkClient` which uses `dbus.Interface(..., DBUS_PROPERTIES).Get(...)` per property — these are live D-Bus reads, not a Python-side cache. If staleness is observed, the cause is BlueZ not updating `Network1` properties until an event triggers refresh, not application-side caching.

**Plan**:
- [x] Replace three separate `Get()` calls with a single `GetAll("org.bluez.Network1")` for atomicity (avoids race between individual property reads)
- [x] If the issue persists after atomicity fix, document as a BlueZ limitation

**Expected outcome**: `cpan status` uses atomic property read; staleness from BlueZ itself is documented as a known limitation.

---

### P0-8: Re-organize `ble_ops` into `le/`, `classic/`, `common/`, `audio/`

**Status**: Done

**Current state**: `bleep/ble_ops/` contains 32 files mixing LE-specific (`scan.py`, `connect.py`, `reconnect.py`, `brute.py`, `enum_*.py`, `ctf*.py`), Classic-specific (`classic_*.py` — 12 files), shared (`conversion.py`, `uuid_utils.py`, `modalias.py`, `structural.py`), and audio (`amusica.py`, `audio_*.py` — 6 files).

**Plan**:
```
bleep/ble_ops/
├── __init__.py          # re-exports all current public symbols for backward compat
├── common/
│   ├── __init__.py
│   ├── conversion.py
│   ├── uuid_utils.py
│   ├── modalias.py
│   └── structural.py
├── le/
│   ├── __init__.py
│   ├── scan.py, scan_modes.py, connect.py, reconnect.py
│   ├── brute.py, enum_controller.py, enum_helpers.py
│   └── ctf.py, ctf_discovery.py
├── classic/
│   ├── __init__.py
│   ├── connect.py, sdp.py, pbap.py, opp.py, ftp.py
│   ├── map.py, pan.py, spp.py, ping.py, version.py
│   ├── bip.py, sync.py
│   └── rfcomm.py          # NEW for M2
└── audio/
    ├── __init__.py
    ├── amusica.py, audio_tools.py, audio_codec.py
    ├── audio_recon.py, audio_system.py
    └── audio_profile_correlator.py
```

**Migration strategy (completed)**:
- [x] Moved 32 files into `le/`, `classic/`, `common/`, `audio/` subdirectories
- [x] `bleep/ble_ops/__init__.py` re-exports core public symbols from new locations
- [x] Updated ~181 import sites across 62 files (`cli.py`, `modes/*.py`, `dbuslayer/*.py`, `analysis/*.py`, `scripts/*.py`, `tests/*.py`, `workDir/Functions/*.py`) to canonical subpackage paths
- [x] Backward-compat stub modules initially created, then **removed** — all imports now use canonical paths
- [x] Verified with `python3 -c "from bleep.ble_ops import *"` and compile checks
- [x] No functional changes — pure restructure

**Outcome**: Clean separation of LE, Classic, shared, and audio operations. All imports use canonical subpackage paths. Old flat paths raise `ModuleNotFoundError`.

---

### P0-9: Dual Device Scan Command (NEW)

**Status**: Done

**Current state**:
- `brute_scan` in `bleep/ble_ops/le/scan.py` (line ~787): sequential BR/EDR then LE (half timeout each)
- `scan_audio_targets` in `bleep/ble_ops/audio/amusica.py`: uses `{"Transport": "auto"}` for single-session combined discovery
- `discover_devices` in `bleep/core/device_management.py`: supports `transport_type="auto"`
- CLI `bleep scan`: has `--variant` (passive/naggy/pokey/brute) but **no** `--transport` flag
- Debug mode: `scan`/`scann`/`scanp`/`scanb` (LE-oriented) + `cscan` (Classic-only), no dedicated "both" command
- When `transport="auto"` in `_native_scan`, no `Transport` key is set in the discovery filter — may inherit stale filter state

**Plan**:
- [x] Add `--transport {auto,le,bredr}` flag to `bleep scan` in `bleep/cli.py`; default `auto`
- [x] For `_native_scan` with `transport="auto"`, explicitly set `{"Transport": "auto"}` in the discovery filter to avoid stale-filter dependence
- [x] Add `dscan [--timeout T]` command to Debug Mode in `bleep/modes/debug_scan.py` — runs `_native_scan(None, timeout, transport="auto")` with explicit filter. Note: this is distinct from `scanb` (brute_scan) which does **sequential** BR/EDR then LE in two phases; `dscan` uses a **single combined discovery session** via `Transport: "auto"`, which is less intrusive and interleaves both transports
- [x] Tag results with transport type: `[LE]`, `[BR/EDR]`, `[Dual]` per device using existing `get_device_transport()` from `bleep/analysis/device_type_classifier.py`

**Expected outcome**: Users run a single scan that discovers both LE and Classic devices in one session, with results labeled by transport type. `scanb` remains available as the "loud" sequential alternative.

---

### M1: Full Automatic Deployment of `amusica`

**Status**: Done | **Depends on**: M3 (done), M6 (done)

**Existing structures**:
- `bleep/ble_ops/audio/amusica.py`: `scan_audio_targets()`, `attempt_justworks_connect()`, `assess_targets()`, `summarise_assessment()`
- `bleep/modes/amusica.py`: CLI subcommands `scan`, `halt`, `inject`, `record`, `control`, `auto`
- `bleep/ble_ops/audio/audio_tools.py`: `AudioToolsHelper` — backend detection, play/record, BlueALSA PCM listing, `halt_audio_for_device()`
- `bleep/ble_ops/audio/audio_recon.py`: `run_audio_recon()`
- `bleep/ble_ops/audio/audio_system.py`: `system_play()`, `system_record()`
- `bleep/dbuslayer/pin_brute.py`: `PinBruteForcer` with lockout awareness
- `bleep/ble_ops/audio/amusica_orchestrator.py`: `run_amusica_full_auto()`, `analyze_recordings()`

**Five-stage autonomous pipeline**:
- [x] **Stage 1 — Scan & Classify**: Uses `scan_audio_targets()` with existing `_device_has_audio_uuids()` filter. Done.
- [x] **Stage 2 — Connection Test & Triage**: Uses `attempt_justworks_connect()` per target; splits into justworks / auth_required / profile_unavailable / failed. Done.
- [x] **Stage 3 — Optional PIN Guessing**: Uses `PinBruteForcer.run_pin_brute()` with `COMMON_PINS`. Gated by `--brute` flag. Configurable depth via `--brute-depth`. Done.
- [x] **Stage 4 — Record & Playback**: Halts existing audio via `halt_audio_for_device()`, runs `run_audio_recon()` per accessible target. Done.
- [x] **Stage 5 — Post-Test Analysis**: `analyze_recordings(paths)` uses `sox stat` + `soxi -D` for amplitude and duration analysis. Done.
- [x] New file: `bleep/ble_ops/audio/amusica_orchestrator.py` — `run_amusica_full_auto()`. Done.
- [x] New CLI subcommand: `bleep amusica auto [--brute] [--brute-depth N] [--timeout T] [--record-dir DIR] [--duration D] [--test-file FILE] [--out JSON]`. Done.

**Augmentations from roadmap review**:

- [x] **M1-aug-a**: `attempt_justworks_connect()` now detects `"profile unavailable"` / `"profileunavailable"` → distinct `"profile_unavailable"` outcome. Done.
- [x] **M1-aug-b**: `run_audio_recon()` now distinguishes `"no_matching_device"` (MAC filter miss) from `"device_not_available"` (no BT audio at all). Done.

**Expected outcome**: `bleep amusica auto` runs the complete 5-stage pipeline. Results printed as summary table with per-target breakdown. Profile-unavailable failures triaged distinctly from auth-required.

---

### M2: Identification of RFCOMM Channels

**Status**: Done | **Depends on**: P0-8 (done)

**Existing structures**:
- `bleep/ble_ops/classic/sdp.py`: `discover_services_sdp()` + `build_svc_map()` — full SDP/RFCOMM extraction
- `bleep/modes/debug_classic.py` `cmd_cservices`: prints structured per-service listing with RFCOMM channels
- `bleep/modes/debug_classic_rfcomm.py`: `copen`, `csend`, `crecv`, `craw` — raw RFCOMM I/O
- `bleep/ble_ops/classic/connect.py`: `classic_rfccomm_open()` — raw RFCOMM socket
- `bleep/dbuslayer/spp_profile.py`: SPP profile registration

**What's genuinely new — terminal/serial probing**:
- [x] New file: `bleep/ble_ops/classic/rfcomm.py` — `ProbeResult` dataclass + `probe_rfcomm_channel()` + `probe_all_channels()`. Reuses `classic_rfccomm_open()`. Sends `\r\n`, VT100 DA1 `\x1b[c`, passive SSH banner read. Classifies: `terminal`/`ssh`/`serial`/`data`/`closed`/`silent`. Done.
- [x] New CLI subcommand: `bleep classic-rfcomm <MAC> [--probe] [--timeout N] [--adapter]` — SDP discovery → formatted RFCOMM table → optional per-channel probe. Done.
- [x] New debug command: `crfcomm [--probe] [--timeout N]` — uses `state.current_mapping`, auto-discovers if empty. Done.

**Expected outcome**: ✅ RFCOMM channels are enumerated (existing), and optionally probed for terminal/serial interfaces (new).

---

### M3: Improved Agent Usage and Capabilities

**Status**: Done

**Existing structures**:
- `bleep/dbuslayer/agent.py`: `PairingAgent` with `register(capabilities=...)` supporting `NoInputNoOutput`, `DisplayOnly`, `KeyboardOnly`, `KeyboardDisplay`
- `bleep/dbuslayer/pin_brute.py`: `PinBruteForcer` — full brute-force orchestration with lockout awareness, accepts external `pin_iterator`/`passkey_iterator`
- `bleep/dbuslayer/agent_io.py`: `BruteForceIOHandler` — feeds candidates to agent callbacks
- Auth method is implicitly detectable (agent receives `RequestPinCode` vs `RequestPasskey` vs `RequestConfirmation`)

**What's genuinely new**:
- [x] **Common PIN/PassKey constants** in `bleep/bt_ref/constants.py`: `COMMON_PINS` (14 entries, structured by length: `COMMON_PINS_4` / `COMMON_PINS_6` / `COMMON_PINS_ALPHA`), `COMMON_PASSKEYS` (5 entries), `AGENT_CAPABILITIES` (5 entries). Wired as default iterators in `PinBruteForcer.run_pin_brute()` and `run_passkey_brute()` when no explicit list provided. Done.
- [x] **Capability downgrade cycling** — `attempt_downgrade_pair(bus, device_path)` in `bleep/dbuslayer/agent.py`. Cycles NoInputNoOutput → DisplayOnly → DisplayYesNo → KeyboardOnly → KeyboardDisplay, records auth method per attempt, stops on first success. Uses `AGENT_CAPABILITIES` constant. Done.
- [x] **Auth type reporting** — `last_auth_method` attribute on `BlueZAgent` base class, set in all 7 agent methods: `RequestPinCode`, `DisplayPinCode`, `RequestPasskey`, `DisplayPasskey`, `RequestConfirmation`, `RequestAuthorization`, `AuthorizeService`. Exposed via `get_last_auth_type() -> Optional[str]`. Done.
- [x] **Debug command**: `pair --probe <MAC>` — invokes `attempt_downgrade_pair()`, prints result table, cancels pairing if successful. Done.
- [x] **PIN/Passkey corrections** (v2.8.0-m6): Reviewed against BlueZ documentation (`org.bluez.Agent.rst`, `mgmt.rst`, `bluez/src/agent.c`, `bluez/emulator/smp.c`). Removed invalid empty-string PIN, added alphanumeric PINs, reordered capabilities for BR/EDR kernel conversion, added `DisplayPinCode` and `RequestAuthorization` auth tracking, documented SSP passkey brute-force infeasibility. Done.

**Expected outcome**: ✅ Agent tries common PINs by default (including alphanumeric), can cycle capabilities for downgrades, and reports the exact auth type for all 7 BlueZ agent methods.

---

### M4: Improved Preliminary Check of Connectivity

**Status**: Done | **Depends on**: P0 (done)

**Existing structures**:
- `bleep/dbuslayer/device_classic.py` `connect()`: checks `is_connected()` and skips if already connected (line ~155), BUT always calls `Disconnect()` first (line ~177) — contradicts the skip
- `bleep/dbuslayer/device_le.py`: `is_connected()`, `is_paired()`, `is_trusted()`
- `bleep/core/preflight.py`: checks tool binaries and BlueZ version — not live adapter state
- `bleep/dbuslayer/adapter.py`: `is_ready()`, accepts `bluetooth_adapter=` param; no `list_adapters()` API
- `--adapter` flag on `adapter-config` and `amusica` subcommands, not globally
- `bleep/core/errors.py`: `map_dbus_error()` — maps D-Bus exceptions to BLEEP exceptions; only handles a subset of BlueZ errors
- `bleep/core/error_handling.py`: `_DBUS_ERROR_NAME_MAP` / `_DBUS_MESSAGE_MAP` — partial BlueZ error coverage
- **BlueZ reference**: `workDir/BlueZDocs/errors.txt` defines 34 structured connection errors (17 BR/EDR, 17 LE); `workDir/BlueZDocs/org.bluez.Device.rst` documents `Connect()`, `Pair()`, `Disconnected` signal errors

**What's genuinely new**:
- [x] **M4-1: `check_device_state(bus, mac)`** in `bleep/core/preflight.py` — `DeviceState` dataclass + `check_device_state()` function queries LE/Classic `get_device_info()`. Done.
- [x] **M4-2: Fix Disconnect-Before-Connect contradiction** in `device_classic.py` — added `force_disconnect` param (default `False`); only disconnects when explicitly requested. Done.
- [x] **M4-3: Consistent adapter guard** — `require_adapter()` in `preflight.py` — **Done in P0-5**
- [x] **M4-4: `list_adapters()`** in `bleep/dbuslayer/adapter.py` — static method walks `Adapter1` paths from `GetManagedObjects()`. Done.
- [x] **M4-5: Broader `--adapter` flag** on CLI subcommands — added to `scan`, `connect`, `gatt-enum`, `enum-scan`, `classic-scan`, `classic-enum`, `classic-ping`, `explore`, `signal`, `agent`. Done.
- [x] **M4-6: Connection limit awareness** — `get_connected_devices()` on adapter returns list of connected MACs; `ConnectionLimitError` mapped from BlueZ `"concurrent connection limit"`. BlueZ does not expose a max connection count property — documented as platform limitation. Done.

**Augmentations from roadmap review** (source: `workDir/BigMoves/README.bleep-bleep-mcp-augmentation-roadmap.md` items S2, S8, 3.4):

- [x] **M4-new-a: `skip_pair_fallback` on LE connect** — `skip_pair_fallback: bool = False` parameter added to `connect_and_enumerate__bluetooth__low_energy()`. When `True`, auth exceptions re-raise instead of auto-pairing. Done.
- [x] **M4-new-b: Comprehensive BlueZ error mapping** — 13 new `RESULT_ERR_*` constants (28–40), 7 new `_DBUS_ERROR_NAME_MAP` entries, 26 new `_DBUS_MESSAGE_MAP` entries (all `br-connection-*` / `le-connection-*`), 8 new exception classes, 10+ new branches in `map_dbus_error()`. Done.
- [x] **M4-new-c: Human-readable error descriptions + disconnect reason map** — All new error codes added to `error_mapping` dict. `DISCONNECT_REASON_MAP` with 6 BlueZ reason strings added. Done.

**Expected outcome**: ✅ BLEEP never destroys existing connection/pairing unless explicitly requested. Multiple adapters can be listed and selected. Connection limits surfaced via `get_connected_devices()` and `ConnectionLimitError`. All 34 BlueZ connection errors mapped to structured BLEEP exceptions with human-readable descriptions. LE connect supports opt-out of auto-pair fallback.

---

### M5: Improved Device Identification (Using Internal BT SIG Data)

**Status**: Done

**Existing structures**:
- `bleep/bt_ref/update_ble_uuids.py`: fetches from BT SIG Bitbucket → writes `bleep/bt_ref/uuids.py`
- `bleep/bt_ref/uuids.py` (auto-generated): `SPEC_ID_NAMES__COMPANY_IDENTS`, `SPEC_ID_NAMES__ADVERTISING_TYPES`, `SPEC_ID_NAMES__APPEARANCE_VALUES`
- `bleep/bt_ref/bluetooth_uuids.py`: legacy snapshot — **deprecated** with DeprecationWarning as of v2.8.0-m5

**Plan**:
- [x] **Manufacturer ID → Company Name**: `_resolve_company_name()` in `common/conversion.py` resolves 16-bit company IDs via `SPEC_ID_NAMES__COMPANY_IDENTS`. ManufacturerData display now shows "0x004c (76) — Apple, Inc.". Done.
- [x] **Fix `common/modalias.py` import**: `decode_pnp_id_vendor()` now imports from `bleep.bt_ref.uuids`. Done.
- [x] **AD Type name resolution**: `_resolve_ad_type_name()` resolves AD type codes. AdvertisingData display now shows "Type: 0x01 (1) — Flags". Done.
- [x] **Appearance consolidation**: `_resolve_appearance_sig()` resolves through SIG category/subcategory hierarchy, `decode_appearance()` tries hardcoded map first, then SIG table fallback. Done.
- [x] **Windows/CDP detection**: Microsoft CDP UUID `0000FE05-...` detected by `LEServiceDataCollector` in `device_type_classifier.py`. Done.
- [x] **Deprecate `bluetooth_uuids.py`**: All imports redirected to `uuids.py`; DeprecationWarning added to legacy file. Done.

**Augmentations**:
- [x] **M5-aug-a**: `_determine_device_type()` in `adapter.py` now passes `service_data`, `advertising_data`, `manufacturer_data`, `appearance` to classifier context. Done.
- [x] **M5-aug-b**: `LEServiceDataCollector` in `device_type_classifier.py` with `_BEACON_SERVICE_DATA_UUIDS` (Find My, EN v1/v2, CDP, NearbySharing). Done.
- [x] **M5-aug-c**: Vendor UART heuristics via `_VENDOR_UART_UUIDS` (FFE0, FFE1, FFF0, FFF1, Nordic UART) as `WEAK` evidence. Done.
- [x] **M5-aug-d**: `evidence_source` field on `ClassificationResult` — `"heuristic"` / `"measured_sdp"` / `"measured_gatt"` / `"cached"`. `_determine_evidence_source()` + cached result path. Done.
- [x] **M5-aug-e**: ServiceData UUID→name already handled by existing `get_name_from_uuid()` in `format_device_info_block()`. Verified. Done.

**Expected outcome**: ✅ All device identification uses self-contained, SIG-updatable data. Classifier receives full advertisement context. Evidence is labeled by source. Known beacons and vendor UARTs are identified.

---

### M6: Augment (Re)Configuration of Linux Host OS Bluetooth File(s)

**Status**: Done

**Existing structures**:
- `bleep/ble_ops/audio/audio_tools.py` `AudioToolsHelper`: runtime ALSA/BlueALSA detection, enumeration (`aplay -l`/`arecord -l`), PCM listing, play/record helpers — no config file writing
- `bleep/modes/adapter_config.py`: BlueZ adapter D-Bus + `bluetoothctl mgmt` + `/etc/bluetooth/main.conf` parse — not ALSA configuration

**What's genuinely new**:
- [x] New module: `bleep/ble_ops/audio/alsa_config.py` — `AsoundEntry`/`TunnelConfig` dataclasses + `read_asound_conf()` parser + `configure_bluealsa_device()` + `remove_bluealsa_device()` + `create_audio_tunnel()` + `backup_and_restore()`. Supports `address 00:00:00:00:00:00` convention. BLEEP-tagged blocks for safe removal. Done.
- [x] CLI commands: `bleep audio-config show|add|remove|tunnel|backup|restore`. Full subcommand parser with `--path` override and `--type sink|source`. Done.

**Expected outcome**: ✅ BLEEP can programmatically configure the host OS audio stack for Bluetooth audio.

---

### M7: Augment File Sharing

**Status**: Done | **Depends on**: M2 (done)

**Existing structures**:
- `bleep/dbuslayer/obex_opp.py`, `obex_ftp.py`, `obex_map.py`, `obex_pbap.py`, `obex_sync.py`, `obex_bip.py` — full OBEX suite
- `bleep/modes/debug_classic_obex.py`: `copp`, `cmap`, `cftp`, `csync`, `cbip` debug commands
- `bleep/ble_ops/classic/opp.py`, `classic/ftp.py`, `classic/map.py`, etc. — ops wrappers
- `bleep/bt_ref/constants.py` `UUID_NAMES` dict: custom/non-SIG UUID → name mapping (first lookup in `get_name_from_uuid()`)
- `bleep/analysis/device_type_classifier.py`: `_BEACON_SERVICE_DATA_UUIDS` includes `a82efa21...` → `"nearby_sharing"` label, `LEServiceDataCollector` matches it
- `bleep/ble_ops/classic/rfcomm.py`: `probe_rfcomm_channel()`, `probe_all_channels()` (M2)
- `bleep/ble_ops/classic/connect.py`: `classic_rfccomm_open()` — raw RFCOMM socket
- `bleep/modes/debug_state.py`: `DebugState` dataclass with `rfcomm_sock` and `rfcomm_bindings` fields

**Known constraint — obexd AppArmor confinement**: On Ubuntu, `obexd` runs under AppArmor and may only write to permitted paths (e.g. `~/.cache/obexd/`). Documented in: todo_tracker R6 (line ~1151), changelog v2.7.20 (line ~1442), `_default_pull_dest()` docstring, `bl_classic_mode.md` troubleshooting table. All obexd receive operations (OPP pull, MAP get, FTP get, BIP get, Sync get) are affected. BLEEP uses a two-stage approach: obexd writes to staging dir, BLEEP moves to final dir.

**D1 — NearbySharing Detection (Phase A only)**:
- [x] Add `"a82efa21-ae5c-3dde-9bbc-f16da7b16c5a": "Microsoft Nearby Sharing"` to `UUID_NAMES` in `bt_ref/constants.py` (custom UUID — `uuids.py` is auto-generated, must not be hand-edited)
- [x] In `ble_ops/le/scan.py` `_native_scan`: add `service_data`, `advertising_data`, `manufacturer_data` from `entry` to passive-scan classifier `context`
- [x] In `ble_ops/le/scan.py` `_base_enum`: add same fields from `device_props` to naggy classifier `context`
- [x] In `analysis/device_type_classifier.py` `_get_collectors_for_mode("passive")`: add `"le_service_data"` to passive collector allowlist
- Phase B (full CDPX protocol) deferred — Microsoft proprietary, research-dependent

**D2 — Customizable OBEX File Save Directory (two-stage)**:
- [x] In `core/config.py`: add `OBEX_STAGING_DIR` (`~/.cache/obexd/`, obexd-safe) and `OBEX_RECEIVE_DIR` (`/tmp/bleep_received/` default, env `BLEEP_RECEIVE_DIR` override)
- [x] In `modes/debug_classic_obex.py`: update `_default_pull_dest()`, `cmd_cmap` get, `cmd_cftp` get defaults to two-stage; new `_obex_staging_path()` and `_stage_and_move()` helpers
- [x] In `cli.py`: update OPP pull/exchange, MAP get, FTP get, BIP get/thumb, Sync get to two-stage; add `--save-dir` to `classic-opp`, `classic-map`, `classic-ftp`, `classic-bip`, `classic-sync` subparsers

**D3 — RFCOMM Channel Binding**:
- [x] In `ble_ops/classic/rfcomm.py`: add `bind_rfcomm_channel()`, `release_rfcomm_channel()`, `list_rfcomm_bindings()` using `rfcomm` userspace utility via `shutil.which` + `subprocess.run`
- [x] In `modes/debug_state.py`: add `rfcomm_bindings: List[int]` field to `DebugState`
- [x] In `modes/debug_classic_rfcomm.py`: add `cbind` command (`cbind <channel>`, `cbind release`, `cbind list`)
- [x] In `cli.py`: add `--bind` and `--device-id` flags to `classic-rfcomm` subcommand
- [x] In `modes/debug.py`: register `cbind` in command table, add cleanup on shell exit

**Expected outcome**: NearbySharing devices detected and labeled in scans. OBEX downloads use obexd-safe staging with auto-cleanup final dir. Persistent RFCOMM bindings with debug-mode tracking and cleanup.

---

### M8: User Profile Control for Connecting Profiles

**Status**: Done

**Existing structures**:
- `bleep/modes/debug_classic_profiles.py`: `cpan` (connect/disconnect/status/server) and `cspp` (register/unregister/status) — PAN and SPP only
- `bleep/dbuslayer/spp_profile.py`: `SppManager`/`SppProfile` with `ProfileManager1.RegisterProfile`
- `bleep/dbuslayer/device_classic.py`: `ConnectProfile(uuid)` (line ~614)
- `bleep/bt_ref/utils.py`: `get_name_from_uuid()` for UUID-to-name resolution

**Overlap note**: `cservices` already displays SDP-discovered service UUIDs with names via `get_name_from_uuid()`. The value-add of `cprofiles` is showing the **D-Bus `Device1.UUIDs`** property (the device's full advertised profile set, which may differ from SDP-discovered services) and allowing direct `ConnectProfile` by UUID.

**What's genuinely new**:
- [x] **Generic profile listing** — new command `cprofiles` in `debug_classic_profiles.py`:
  Reads `org.bluez.Device1.UUIDs` property (distinct from SDP services shown by `cservices`), cross-references via `get_name_from_uuid()`, displays UUID + Name + connection status
- [x] **Generic profile connect** — new command `cprofile connect <UUID>`:
  Calls existing `device.ConnectProfile(uuid)` from `device_classic.py`
  CLI: `bleep connect-profile <MAC> <UUID> [--disconnect]`
- [x] **Security on RegisterProfile** — extended `cspp register` with `--auth`/`--no-auth` flags; `spp.py register()` now passes `require_auth` through to `SppManager`

**Expected outcome**: Users list all profiles, connect by UUID, and register profiles with security options.

---

### M9: Custom Callback Functions with User Integration to I/O Operations

**Status**: Done

**Existing structures**:
- `bleep/signals/router.py`: `register_callback(name, callback)` for signal events
- `bleep/signals/integration.py`: property/notification read/write hooks
- `bleep/dbuslayer/agent_io.py`: `ProgrammaticIOHandler` with per-event `callbacks` dict
- GATT: `characteristic.py` `start_notify(callback)`
- Reconnection: `reconnect.py` `ReconnectionMonitor(callback=...)`
- SPP: `spp_profile.py` `on_connect`/`on_disconnect`/`on_release`

**Approach — extend existing signal router, not rebuild**:
- [x] **Expand signal router triggers**: Added `DEVICE_CONNECT`, `DEVICE_DISCONNECT`, `PAIR_START`, `PAIR_COMPLETE` to `SignalType` enum in `bleep/signals/capture_config.py`
- [x] **User callback directory**: Loader in `bleep/callbacks/__init__.py` — scans `~/.config/bleep/callbacks/*.py` for subclasses of `BleepCallback`, registers via existing `register_callback()`
- [x] **Base class** in `bleep/callbacks/base.py`: `name`, `trigger`, `execute(context)`, lifecycle hooks `on_load()`/`on_unload()`
- [x] **Example callbacks** in `bleep/callbacks/examples/`: `log_all_notifications.py`, `pair_event_logger.py`

**Expected outcome**: Users drop Python files into a callbacks directory; they integrate automatically via the existing signal infrastructure.

---

### M10: Identification and Interactivity of Human Interface Devices (HIDs)

**Status**: Done

**Existing structures**:
- `bleep/ble_ops/le/scan.py` `_collect_device_props()`: probes `org.bluez.Input1` with `GetAll`, stores under `_Input1`
- `bleep/ble_ops/common/conversion.py` `format_device_info_block()`: renders `Input → ReconnectMode` only (lines ~769–785)
- Class-of-Device minor class labels include HID types in `common/conversion.py`
- HID service UUID `0x1124` in `bt_ref/uuids.py`
- Appearance values 960+ mapped to HID subtypes in `common/conversion.py`

**What's genuinely new**:
- [x] **HID classification logic** — `classify_hid()` and `HIDInfo` dataclass added to `bleep/analysis/device_type_classifier.py`: combines appearance (960+ range), CoD peripheral class (0x05), `Input1.ReconnectMode`, HID service UUID. New `HID_CLASSIFICATION` evidence type.
- [x] **Enhanced display** — `format_device_info_block()` in `common/conversion.py` now shows full HID classification block (type + subclass + reconnect mode) when device is identified as HID
- [x] **Debug command** — `chid` in new `debug_hid.py`: full HID classification for connected device (LE or Classic)
- [x] **CLI** — `bleep hid-info <MAC>`: display HID classification and properties

**Expected outcome**: BLEEP identifies HIDs by type (keyboard, mouse, gamepad), displays reconnection behavior, persists HID evidence.

---

### Bonus: Audio Capture and Transcription

**Status**: Done | **Depends on**: M6 (ALSA config)

**Existing structures**:
- `bleep/ble_ops/audio/audio_system.py`: `system_record()`, `system_play()`
- `bleep/ble_ops/audio/audio_codec.py`: GStreamer encode/decode
- `bleep/ble_ops/audio/audio_tools.py`: `AudioToolsHelper` — backend detection, ALSA enumeration, BlueALSA PCMs

**Seven-step pipeline (all new orchestration)**:
- [x] **Step 1–2**: `_validate_prerequisites()` checks for `arecord`/`sox`; PCM auto-derived from MAC
- [x] **Step 3–4**: `_capture_audio()` records via `arecord -D bluealsa:DEV=<MAC>,PROFILE=a2dp`
- [x] **Step 5**: `check_audio_file_has_content()` via sox stat analysis
- [x] **Step 6**: `transcribe_file()` in new `bleep/ble_ops/audio/audio_transcribe.py` wrapping `whisper` CLI and `vosk` Python API
- [x] **Step 7**: `run_audio_intercept()` orchestrates full pipeline; returns `AudioInterceptResult`
- [x] New CLI: `bleep audio-intercept <MAC> [--duration N] [--no-transcribe] [--engine whisper|vosk]`

**Expected outcome**: Audio tap, transcription, and injection pipeline — non-disruptive to original audio stream.

---

### F1: Documentation

**Status**: Done

- [x] Update `bleep/docs/changelog.md` with all v2.8.0 changes (M8, M9, M10, Bonus, P0-1 fixes)
- [x] Update `bleep/docs/todo_tracker.md` — marked completed items
- [x] `bleep/__init__.py` version bumped from `"2.8.0-m1"` to `"2.8.0"` (completed in F3)

---

### F2: Code Review

**Status**: Done

- [x] All 14 modified/new files compile clean (`py_compile`)
- [x] All new files under 300 lines (largest: `debug_classic_profiles.py` at 292 lines)
- [x] No circular imports verified (`bleep.callbacks.base`, `bleep.signals.capture_config`, `bleep.analysis.device_type_classifier`)
- [x] No duplicate functionality — M8 reuses existing `ConnectProfile`/`get_name_from_uuid`/`SppManager`; M9 extends existing signal router; M10 composes existing appearance/CoD/UUID data
- [x] Pre-existing large files (`signals.py`, `cli.py`, `observations.py`, `agent.py`, `conversion.py`) not grown; these are architectural and documented for future F2 consideration

---

### F3: Change Log, TODO Tracking, and Associated Documentation

**Status**: Done

- [x] Structured changelog entries per existing format (v2.8.0 final entry at top of `changelog.md`)
- [x] TODO tracker updated with completion statuses for all M8, M9, M10, Bonus, P0-1 fixes, F1, F2, F3
- [x] Version bumped in `bleep/__init__.py` from `"2.8.0-m1"` to `"2.8.0"`
- [x] All dates consistent: 2026-03-27

---

### Future Work: Expand BT SIG Assigned Numbers Coverage

**Status**: Pending (post-v2.8.0)

The `bleep/bt_ref/update_ble_uuids.py` script currently fetches 12 YAML tables from the Bluetooth SIG public repository (`bitbucket.org/bluetooth-SIG/public`). Additional tables exist that would improve BLEEP's ability to recognize and identify Bluetooth devices and their capabilities/limitations.

**Candidate tables for incorporation** (under `assigned_numbers/`):
- [ ] `service_discovery/attribute_ids/*.yaml` — SDP Attribute ID definitions (e.g., `universal_attributes.yaml`, `browse_group.yaml`, `device_id.yaml`, `hid.yaml`, `imaging.yaml`, `pbap.yaml`, etc.) — would enrich SDP record interpretation in `bleep/ble_ops/classic/sdp.py`. **Deferred** (directory of many per-profile files) — see "ACCEPTED WORK" section above.
- [x] `core/core_version.yaml` — Bluetooth Core Specification version numbers → human-readable version strings (**DONE** 2026-05-26: added to `update_ble_uuids.py` codegen pipeline + `resolve_core_version()` in `conversion.py`). NOTE: wired in the updater `id_map` but not yet emitted into the committed `uuids.py`; deferred to the next full regeneration (see "ACCEPTED WORK").
- [x] ~~`core/fhs.yaml` — Frequency Hopping Sequence parameters~~ **Corrected 2026-07-24**: `fhs.yaml` is **Class-of-Device** data (the FHS packet carries CoD), not hop-sequence params, and no longer ships in the live SIG `core/` dir. Incorporated as CoD via `core/class_of_device.yaml` → generated `bt_ref/cod.py`. See "ACCEPTED WORK" section above.
- [x] `mesh/*.yaml` — Bluetooth Mesh assigned numbers — incorporated as generated `bt_ref/mesh_ids.py` (`mesh_model_uuids.yaml` + `mesh_beacon_types.yaml`). See "ACCEPTED WORK" section above.
- [ ] Any newly published tables as the SIG repository evolves

**Implementation approach**: Modify `_FILES` dict in `update_ble_uuids.py` to include new YAML paths. Add corresponding `SPEC_ID_NAMES__*` output dicts to `uuids.py`. Wire new dicts into `get_name_from_uuid()` in `bt_ref/utils.py` and any relevant formatting/classification code. All changes flow through the existing auto-generation pipeline — no manual edits to `uuids.py`.

**Principle**: `uuids.py` must only be modified via `update_ble_uuids.py`. Custom/non-SIG UUIDs (BLE CTF, vendor-specific, etc.) belong in `UUID_NAMES` in `bt_ref/constants.py`.

---

---

> **Note (2026-03-26)**: File paths in the historical COMPLETE sections below reflect the `bleep/ble_ops/` layout at the time of completion. The P0-8 restructure (v2.7.40) moved all `ble_ops` modules into `le/`, `classic/`, `common/`, and `audio/` subpackages. See the P0-8 section and changelog v2.7.40 for the mapping.

---

## Data Fidelity Remediation — Schema v10 (2026-03-25) – COMPLETE

**Goal**: Ensure all BLEEP CLI commands persist accurate and complete device/service/characteristic data to the observation database, closing gaps identified through systematic comparison against the BlueZ D-Bus API documentation.

### Phase 1 — High Severity (silent data loss or missing persistence)

- [x] **Gap 1** `bleep/modes/exploration.py` — `print_service_info` now always reads all readable characteristic values and collects all descriptor data regardless of display verbosity or the 20-characteristic threshold; display is still gated, but data collection is unconditional
- [x] **Gap 7** `bleep/cli.py` (`connect`) — `connect` command now persists device metadata and GATT enumeration data to the observation DB via `_collect_device_props` + `_persist_mapping` after successful connection
- [x] **Gap 8** `bleep/cli.py` (`classic-scan`) — discovered Classic devices are now persisted via `upsert_device` with name, RSSI, device class, address type, and device type
- [x] **Gap 9** `bleep/cli.py` (`classic-enum`) + `bleep/ble_ops/classic_connect.py` — `classic-enum` now fetches `org.bluez.Device1` properties (plus Battery1/Input1 auxiliaries), prints a Device Information block (parity with BLE gatt-enum/enum-scan), and persists full device metadata; `classic_connect.py` now calls `upsert_device` with full device info before persisting classic services

### Phase 2 — Medium Severity (incomplete metadata or missed enrichment)

- [x] **Gap 3** `bleep/modes/exploration.py` — `save_to_database` now accepts and persists `device_props` from D-Bus (RSSI, address type, device class, appearance, manufacturer data)
- [x] **Gap 4** `bleep/modes/exploration.py` — permission maps are now included in `upsert_characteristics` calls
- [x] **Gap 6** `bleep/modes/exploration.py` — every readable characteristic value is now also inserted into `char_history` with `source="explore"` for audit trail
- [x] **Gap 10** `bleep/core/observations.py` — `upsert_services` ON CONFLICT clause now updates `handle_start`, `handle_end`, and `name` via `COALESCE` so subsequent scans fill in previously-NULL values
- [x] **Gap 11** `bleep/modes/exploration.py` — device type is now determined by `DeviceTypeClassifier.classify_with_mode()` instead of hardcoded `"le"`, with fallback

### Phase 3 — Schema v10 Migration

- [x] **`bleep/core/observations.py`** — Schema v10 migration:
  - `devices` table: added `tx_power`, `modalias`, `icon`, `service_data`, `advertising_data` columns
  - `services` table: added `is_primary`, `includes` columns
  - `characteristics` table: added `mtu` column
  - New `descriptors` table: `(id, characteristic_id, uuid, handle, flags, value, last_read)` with UNIQUE on `(characteristic_id, uuid)`
  - New public APIs: `get_characteristic_id()`, `upsert_descriptors()`
  - `_DEVICE_COLS` frozenset updated with all new column names
  - Idempotent migration using per-column `ALTER TABLE ADD COLUMN` with safe `try/except`

### Verification

- [x] All four modified files pass `python3 -m py_compile` without errors
- [x] All four modified files pass IDE linter checks with zero diagnostics
- [x] All existing callers of `save_to_database`, `upsert_services`, `upsert_device`, `connect_and_enumerate__bluetooth__low_energy` confirmed compatible (new parameters use defaults, no signature breaks)
- [x] `_persist_mapping` and `_collect_device_props` confirmed importable as module-level functions from `bleep.ble_ops.scan`
- [x] `format_device_info_block`, `device_address_to_path`, `BLUEZ_NAMESPACE`, `ADAPTER_NAME` imports confirmed correct
- [x] `classic_connect.py` `get_device_info()` return dict confirmed to include all referenced keys

### Phase 4 — Schema v10 Full Utilisation (2026-03-25) – COMPLETE

**Goal**: Ensure every v10 column is actively written by all relevant CLI code paths, fix broken persistence logic, and add descriptor persistence everywhere.

- [x] **P1-a** `upsert_services()` — now writes `is_primary` (bool→int) and `includes` (list→JSON) in INSERT and ON CONFLICT COALESCE
- [x] **P1-b** `upsert_characteristics()` — now writes `mtu` in INSERT and ON CONFLICT COALESCE
- [x] **P2-scan** `bleep/ble_ops/scan.py` `_native_scan` — enriched `upsert_device` calls with `tx_power`, `appearance`, `modalias`, `icon`, `manufacturer_data`, `service_data`, `advertising_data` from adapter discovery data
- [x] **P2-base** `bleep/ble_ops/scan.py` `_base_enum` — uses shared `_enrich_device_info_from_props()` for v10 device columns from D-Bus Device1 properties
- [x] **P2-cli** `bleep/cli.py` `connect` — uses `_enrich_device_info_from_props()` instead of manual extraction
- [x] **P2-explore** `bleep/modes/exploration.py` — delegates to `_enrich_device_info_from_props()` for v10 enrichment
- [x] **P2-classic** `bleep/ble_ops/classic_connect.py` + `bleep/cli.py` classic-scan/enum — classic paths now persist `tx_power`, `appearance`, `modalias`, `icon` where available; classic-enum uses `_enrich_device_info_from_props()`
- [x] **P3** `_persist_mapping()` — now persists descriptors (from both `"Descriptors"` and `"descriptors"` keys), threads `is_primary`/`includes` from svc_data, threads `mtu` from char_data
- [x] **P4** `bleep/cli.py` gatt-enum — replaced inline DB persistence with delegation to `_persist_mapping()`, fixing the `"chars"` vs `"Characteristics"` key mismatch in `--deep` mode
- [x] **P5-gatt** `bleep/cli.py` gatt-enum — added `upsert_device()` with full v10 metadata before GATT persistence
- [x] **P5-media** `bleep/cli.py` media-enum — added `upsert_device()` with v10 metadata
- [x] **P6** `bleep/analysis/aoi_analyser.py` — fixed broken `services_mapping` iteration (was `for uuid, handle` on a svc_uuid→dict structure); now correctly extracts chars from `"chars"`/`"Characteristics"` sub-dicts; persists descriptors
- [x] **P7** Documentation updates: `observation_db.md` (v10 row), `observation_db_schema.md` (v10 API table), `device_type_classification.md` (removed stale migration notes)
- [x] **P8** `get_device_detail()` — now includes `"descriptors"` key with all descriptor rows; `export_device_data()` inherits this automatically
- [x] **Shared helper** `_enrich_device_info_from_props()` — new function in `scan.py` centralises extraction of v10 device columns from D-Bus CamelCase property dicts; used by all BLE enumeration code paths
- [x] `bleep/dbuslayer/device_le.py` — shallow-mode `services_resolved()` now includes `Primary`/`Includes` keys in svc_entry for parity with deep mode

### Pre-existing Issues Noted (not caused by this work) — FIXED in P0-1 (v2.7.40)

- ~~`bleep/cli.py` classic-scan debug branch references `d["class"]` but `get_discovered_devices()` uses key `"device_class"` — debug-only class display is ineffective (pre-existing)~~ — Fixed in P0-1
- ~~`bleep/modes/scratch.py` passes `timeout=` kwarg to `connect_and_enumerate__bluetooth__low_energy` which expects `timeout_connect=` — pre-existing `TypeError` at runtime (orthogonal)~~ — Fixed in P0-1

---

## System-Tool Operation Mode for audio-play / audio-record (2026-03-21) – COMPLETE

**Goal**: Add an operation mode for `audio-play` and `audio-record` that leverages existing system audio tools (e.g. `paplay`, `parecord`, `aplay`, `arecord`, `pw-play`, `pw-record`) rather than acquiring D-Bus `MediaTransport1` file descriptors directly.  This mirrors how `audio-recon` already interacts with Target Devices using local subprocess tools, sidestepping BlueZ transport ownership entirely.

### Motivation
- `audio-recon` successfully plays and records audio through `paplay`/`parecord`/`aplay` because PulseAudio/PipeWire already owns the transport — no `Acquire()` needed.
- The direct D-Bus `MediaTransport1.Acquire()` path requires either stopping the audio daemon (`--direct`) or cycling the A2DP profile (endpoint registration mode), both of which are disruptive.
- A system-tool mode works seamlessly alongside PulseAudio/PipeWire with zero host disruption, making it the least invasive option for environments where the audio daemon is running.

### Implementation
- [x] `bleep/ble_ops/audio_system.py` — New module: `system_play()` and `system_record()` resolve device MAC → sink/source ID using the same backend-branched enumeration as `audio-recon` (PA card-centric, PW native node ID, BlueALSA PCM), then delegate to `AudioToolsHelper`
- [x] `bleep/cli.py` — `--system` flag on `audio-play` and `audio-record` argument parsers; when set, bypasses `MediaStreamManager` and calls `system_play()` / `system_record()` directly
- [x] Existing D-Bus direct (`--direct`) and endpoint-registration (default) modes maintained as alternatives

### Verification
- [x] `audio-play --system <MAC> <file>`: resolves sink, plays via system tool — **live-validated 2026-07-22** against PLT V8200 (`F4:B6:88:0B:90:22`): `[+] Playback complete` via `bluez_output.F4_B6_88_0B_90_22.a2dp-sink`
- [x] `audio-record --system <MAC> <output>`: resolves source, records via system tool — **live-validated 2026-07-22**: produced non-empty 3.82s WAV (host exposed only A2DP-sink + monitor; no HFP mic source, so capture used the sink-monitor fallback)
- [x] Works when PipeWire/PulseAudio is running without disruption — confirmed (PipeWire backend, no daemon stop required)
- [x] Error message with guidance when no sink/source found for the MAC — confirmed (guidance printed before the fix below)

> **⚠️ BUG FOUND & FIXED (2026-07-22) during live validation** — `--system` play/record was **non-functional on PipeWire hosts**. `get_sources_and_sinks_for_card_profile()` relied on `pacmd`, which PipeWire's PulseAudio shim does not implement (`pacmd list-cards` → *"No PulseAudio daemon running"*), so it returned empty sinks/sources for every connected device even though `pactl`/`list_audio_sinks()` worked. `system_play`/`system_record`/`_find_pa_sink`/`_find_pa_source` all failed with *"No audio sink/source found"*.
> - **Fix**: added `AudioToolsHelper._sinks_sources_for_card_via_pactl()` — a `pactl` fallback that associates live sinks/sources to the card by MAC when the `pacmd` block is empty; excludes `*.monitor` loopbacks to match pacmd card-block semantics. `bleep/ble_ops/audio/audio_tools.py`.
> - **Tests**: `tests/test_audio_regressions.py` "Fix 6" (4 tests: sink-by-MAC association, monitor exclusion, pacmd-preferred-when-available, `system_play` end-to-end resolution).

---

## Fix Endpoint-Based Transport Acquisition (2026-03-21) – INCOMPLETE

**Goal**: Fix the endpoint-based acquisition path from v2.7.35 that registered a `BleepMediaEndpoint` but never received `SetConfiguration` / `SelectConfiguration` callbacks, resulting in "BlueZ did not assign a transport within the timeout."

### Root Cause
- `RegisterEndpoint()` only adds a local SEP to BlueZ's endpoint pool — it does **not** trigger AVDTP negotiation
- BlueZ selects endpoints exclusively during `ConnectProfile` (`source.c:source_connect` → `a2dp_discover` → `a2dp_select_eps`)
- `ConnectProfile` is a no-op if the A2DP profile is already connected (`source.c:286-290` returns `-EALREADY`)
- The v2.7.35 implementation registered the endpoint on an already-connected device and waited — BlueZ had no reason to call back
- Additionally, D-Bus callbacks were never dispatched because the singleton `dbus.SystemBus()` was not wired to a GLib mainloop

### Fixes Applied
- [x] **F1** `bleep/dbuslayer/media.py` — `BleepMediaEndpoint` uses a **private** D-Bus system bus with explicit `DBusGMainLoop` integration for reliable callback dispatch
- [x] **F2** `bleep/dbuslayer/media.py` — GLib `MainLoop` lifecycle encapsulated inside `BleepMediaEndpoint` (`register()` starts, `unregister()` stops)
- [x] **F3** `bleep/dbuslayer/media.py` — Fixed `SetConfiguration` D-Bus signature from `oay` to `oa{sv}` (properties dict per BlueZ `media-api.txt`)
- [x] **F4** `bleep/dbuslayer/media_stream.py` — Replaced `_cycle_a2dp_profile()` with `_cycle_device_connection()` using full `Device1.Disconnect()` → poll `Connected` → `Device1.Connect()`. Profile-level cycling (`DisconnectProfile` + `ConnectProfile`) was insufficient: the AVDTP session (`source->session`) persists across the cycle, causing `source_connect()` to return `-EALREADY` without running `a2dp_discover`. btmon confirmed only AVDTP Suspend was sent (no Discover/SetConfiguration). Full device disconnect tears down the ACL link, destroying all AVDTP sessions, so the reconnect triggers fresh discovery including the BLEEP endpoint
- [x] **F5** `bleep/dbuslayer/media_stream.py` — Removed unused `threading`/`GLib` imports; mainloop management moved to `BleepMediaEndpoint`

### Outstanding Issues
- After all attempted fixes (F1–F4), the endpoint-based path still fails: "BlueZ did not assign a transport within the timeout"
- `DisconnectProfile` + `ConnectProfile` only produced AVDTP Suspend, not full re-negotiation (btmon confirmed)
- Full `Device1.Disconnect()` + `Device1.Connect()` also failed to trigger `SelectConfiguration`/`SetConfiguration` on the BLEEP endpoint
- Likely causes under investigation:
  - PipeWire/PulseAudio may race to reconnect and consume all remote SEPs before BLEEP's endpoint is selected
  - BlueZ's endpoint selection order may prefer the audio daemon's pre-existing endpoints
  - The endpoint registration path may require BLEEP to be the **only** registered endpoint (audio daemon fully stopped) to guarantee SEP assignment
- **Path forward**: This approach requires deeper investigation into BlueZ endpoint selection ordering and PipeWire/PulseAudio endpoint contention. Deferred in favour of the `--system` flag approach which works **with** the audio daemon rather than competing against it.

### Verification (NOT PASSED)
- [ ] `audio-play` with endpoint registration: endpoint registered → device cycled → `SelectConfiguration` called → `SetConfiguration` called → transport acquired → audio plays
- [ ] `audio-play --direct`: legacy direct acquisition still works when audio daemon is stopped
- [ ] `media-enum`: continues to display endpoints and transports correctly

---

## BLEEP-Owned MediaEndpoint Registration & Dual Acquisition Modes (2026-03-20) – PARTIAL

**Goal**: Resolve `Acquire()` → `NotAuthorized` failures caused by PulseAudio/PipeWire already owning the transport. Implement BLEEP-owned endpoint registration so BLEEP gets its own transport, and add a `--direct` flag for constrained environments.

**Status**: Phase 1 (error guidance) and Phase 3 (CLI flags, code structure) complete. Phase 2 (endpoint registration acquiring a transport) does not function when PipeWire/PulseAudio is running — see "Fix Endpoint-Based Transport Acquisition" above. The `--direct` mode works when the audio daemon is stopped. The endpoint registration default mode requires further investigation.

### Root Cause
- BlueZ `transport.c:acquire()` (line 798) returns `NotAuthorized` when `transport->owner != NULL`
- PulseAudio/PipeWire automatically register endpoints and acquire all A2DP transports
- BLEEP's `Acquire()` fails because the transport is already owned
- BlueZ `media.c:set_configuration()` (line 548-550) enforces one transport per (endpoint, device) pair — unused remote SEPs are available for BLEEP to claim via its own registered endpoint

### Phase 1: NotAuthorized error guidance
- [x] **P1** `bleep/dbuslayer/media_stream.py` — `_print_not_authorized_guidance()` detects transport state and prints actionable remediation (daemon stop commands, `--direct` flag hint)
- [x] **P1b** `bleep/dbuslayer/media_stream.py` — Exception handling in `_acquire_direct()` now specifically detects `NotAuthorizedError`

### Phase 2: BleepMediaEndpoint registration
- [x] **P2a** `bleep/dbuslayer/media.py` — New `BleepMediaEndpoint(dbus.service.Object)` implementing `org.bluez.MediaEndpoint1` server role: `SetConfiguration`, `SelectConfiguration`, `ClearConfiguration`, `Release`
- [x] **P2b** `bleep/dbuslayer/media.py` — `register()` / `unregister()` / `wait_for_transport()` lifecycle methods; `threading.Event` for synchronous wait
- [x] **P2c** `bleep/bt_ref/constants.py` — Added `SBC_CAPABILITIES` and `SBC_DEFAULT_CONFIGURATION` constants
- [x] **P2d** `bleep/dbuslayer/media_stream.py` — `_acquire_via_endpoint()` registers endpoint, waits for `SetConfiguration` callback, acquires BLEEP-owned transport
- [x] **P2e** `bleep/dbuslayer/media_stream.py` — GLib main loop management (`_start_mainloop` / `_stop_mainloop`) on daemon thread for D-Bus callbacks
- [x] **P2f** `bleep/dbuslayer/media_stream.py` — `release_transport()` now also unregisters endpoint and stops main loop

### Phase 3: CLI `--direct` flag
- [x] **P3a** `bleep/cli.py` — Added `--direct` flag to `audio-play` and `audio-record` argument parsers
- [x] **P3b** `bleep/cli.py` — Handler passes `direct=` to `MediaStreamManager` constructor

### Verification
- [x] All modified files pass linter checks with no errors introduced

---

## Fix Silent Exception Swallowing in Transport Discovery (2026-03-20) – COMPLETE

**Goal**: Fix the persisting *"MediaTransport not found"* error from v2.7.33. The three-phase discovery was correct in design but failed at runtime because Phase 1 constructed D-Bus proxy objects (`MediaEndpoint(ep_path)`) just to read their UUID, and a bare `except Exception: continue` silently swallowed the resulting D-Bus errors — causing Phase 1 to always fail and fall through to Phase 3's diagnostic dump.

### Root Cause
- `_find_transport_by_endpoint_path()` called `MediaEndpoint(ep_path)` inside a `try/except Exception: continue` block
- D-Bus proxy construction failed (e.g. interface not available, object path timing) and the exception was silently swallowed
- Phase 2 (complement UUID fallback) also constructed `MediaTransport` proxies for UUID matching, subject to the same issue
- Diagnostic messages were logged at `LOG__DEBUG`, invisible to the user at normal log levels

### Fix: Proxy-free UUID extraction from `GetManagedObjects()`
- [x] **T1** `bleep/dbuslayer/media_stream.py` — New `_collect_media_objects()` method reads endpoint/transport UUIDs directly from `GetManagedObjects()` return data as `(path, uuid)` tuples — zero D-Bus proxy construction for discovery
- [x] **T2** `bleep/dbuslayer/media_stream.py` — Rewrote `_find_transport_by_endpoint_path()` and `_find_transport_by_uuid()` to iterate `(path, uuid)` tuples; proxy construction only happens for the final matched transport path
- [x] **T3** `bleep/dbuslayer/media_stream.py` — All exception handlers and discovery-status messages elevated from `LOG__DEBUG` to `LOG__USER` for visibility
- [x] **T4** `bleep/dbuslayer/media_stream.py` — Improved `acquire_transport()` error message with endpoint UUID, profile name, expected transport role, and `media-enum` hint
- [x] **T5** `bleep/dbuslayer/media.py` — Added `get_managed_objects` to `__all__` exports
- [x] **T6** Removed `MediaEndpoint` and `find_media_devices` imports from `media_stream.py` (no longer needed)

### Verification
- [x] All modified files pass linter checks with no errors introduced

---

## Fix MediaTransport Discovery & Enrich media-enum Output (2026-03-20) – COMPLETE

**Goal**: Fix `audio-play` / `audio-record` *"MediaTransport not found"* error caused by `_get_transport()` comparing a transport's local-role UUID against the remote endpoint UUID. These are always complementary per AVDTP spec (remote A2DP Sink `0x110b` ↔ local A2DP Source transport `0x110a`), so the old direct-match logic always failed. Also enrich `media-enum` output so the endpoint ↔ transport UUID relationship is visible to the user.

### Root Cause Analysis
- BlueZ `transport.c:get_uuid()` returns `media_endpoint_get_uuid(transport->endpoint)` — the **local** endpoint's UUID
- BlueZ `avdtp.c:avdtp_find_remote_sep()` enforces `sep->type != lsep->info.type` — complementary roles only
- BlueZ `a2dp.c:a2dp_select_eps()` selects local sources for remote sinks and vice versa
- BlueZ places transports as children of remote endpoint paths: `sep1/fd0` under `sep1`

### Fix 1: Path-based transport discovery in `_get_transport()`
- [x] **T1a** `bleep/dbuslayer/media_stream.py` — Replaced UUID-matching with three-phase discovery: (1) path-based endpoint→transport association, (2) complement UUID fallback, (3) diagnostic dump
- [x] **T1b** `bleep/dbuslayer/media_stream.py` — Extracted `_find_device_path()`, `_find_transport_by_endpoint_path()`, `_find_transport_by_uuid()`, `_log_available_transports()` helper methods
- [x] **T1c** `bleep/dbuslayer/media_stream.py` — Updated module docstring and class docstring to explain endpoint ↔ transport UUID relationship

### Fix 2: Add `PROFILE_UUID_COMPLEMENTS` mapping
- [x] **T2** `bleep/bt_ref/constants.py` — Added advisory complement mapping for A2DP, HFP, HSP, AVRCP with documentation referencing BlueZ source evidence

### Fix 3: Enrich `media-enum` output
- [x] **T3a** `bleep/cli.py` — Transport output now includes `uuid`, `uuid_name`, `codec`, `codec_name`, `configuration`, `parent_endpoint`, `role`
- [x] **T3b** `bleep/cli.py` — Endpoint output now includes `uuid_name`, `codec_name`, `capabilities`, `delay_reporting`, `expected_transport_uuid`, `expected_transport_role`, `role`

### Fix 4: Docstring updates
- [x] **T4a** `bleep/modes/audio.py` — `play_audio_file()` docstring clarified: `profile_uuid` = remote endpoint role
- [x] **T4b** `bleep/modes/audio.py` — `record_audio()` docstring clarified: `profile_uuid` = remote endpoint role

### Verification
- [x] All modified files pass linter checks with no errors introduced
- [x] Changes verified against BlueZ source: `workDir/bluez/profiles/audio/transport.c`, `avdtp.c`, `a2dp.c`, `bap.c`

---

## Audio Transport & GStreamer Import Fixes (2026-03-19) – COMPLETE

**Goal**: Fix bugs preventing `audio-play` and `audio-record` commands from functioning. Root cause analysis showed that `audio-recon` works because it uses subprocess calls (`paplay`/`parecord`/`aplay`), while `audio-play`/`audio-record` use D-Bus `MediaTransport1.Acquire()` and GStreamer pipelines — both of which had bugs.

### Fix 1: `dbus.UnixFd` handling in `MediaTransport.acquire()`
- [x] **F1** `bleep/dbuslayer/media.py` — BlueZ `Acquire()` returns `dbus.UnixFd` for the file descriptor; `int(fd)` fails. Changed to `fd.take()` with `isinstance` guard, following `workDir/BlueZScripts/simple-asha` line 163.

### Fix 2: Missing D-Bus type conversions in `dbus_to_python()`
- [x] **F2a** `bleep/bt_ref/utils.py` — Added `dbus.UInt64` → `int()` conversion
- [x] **F2b** `bleep/bt_ref/utils.py` — Added `dbus.UInt32` → `int()` conversion
- [x] **F2c** `bleep/bt_ref/utils.py` — Added `dbus.types.UnixFd` → `.take()` conversion

### Fix 3: GStreamer import without version pin in `audio_codec.py`
- [x] **F3a** `bleep/ble_ops/audio_codec.py` — Added `gi.require_version("Gst", "1.0")` and `gi.require_version("GLib", "2.0")` before import, following `workDir/BlueZScripts/simple-asha` lines 12-16
- [x] **F3b** `bleep/ble_ops/audio_codec.py` — Consolidated `GLib` import to module level alongside `Gst`
- [x] **F3c** `bleep/ble_ops/audio_codec.py` — Removed two redundant inner `from gi.repository import GLib` statements (previously at lines 222 and 412)

### Fix 4: GStreamer import without version pin in `preflight.py`
- [x] **F4** `bleep/core/preflight.py` — Added `gi.require_version("Gst", "1.0")` before import in `_check_audio_tools()`

### Verification
- [x] All four files pass linter checks with no errors introduced
- [x] All changes verified against BlueZ reference: `workDir/BlueZScripts/simple-asha`, `workDir/BlueZDocs/org.bluez.MediaTransport.rst`

---

## Documentation Audit & Corrections (2026-03-19) – COMPLETE

**Goal**: Cross-reference all `bleep/docs/` files against the current codebase to identify and fix outdated references, incorrect CLI commands, wrong imports, and missing documentation links.

- [x] **D1** `media_mode.md` — Fixed CLI command reference (`media list/control/monitor` → `media-enum`/`media-ctrl`)
- [x] **D2** `observation_db_usage_scenarios.md` — Fixed wrong import path, parameter names, and return type for scan API
- [x] **D3** `debug_mode.md` — Removed nonexistent `python -m bleep.cli debug` CLI access path
- [x] **D4** `network_capability_plan.md` / `network_capability_summary.md` — Updated `Network` class → `NetworkClient`/`NetworkServer`
- [x] **D5** `ble_scan_modes.md` — Consolidated duplicate "Last updated" dates
- [x] **D6** `README.md` — Added missing links for ~20 documentation files; reorganised into categorised sections
- [x] **D7** `bleep/docs/__init__.py` — Expanded `_DOCS` mapping from 7 to 40+ entries for `pydoc` access

---

## Device-Level Info in CLI Enumeration Output (2026-03-19) – COMPLETE

**Goal**: Display Device1 D-Bus properties (ManufacturerData, ServiceData, TxPower, Class, Appearance, Modalias, UUIDs, etc.) in CLI enumeration commands (`gatt-enum`, `enum-scan`) and improve hex/ASCII formatting with U+FFFD for non-printable bytes.

### Area A – Formatting Utilities (conversion.py)
- [x] **A1** Added `format_hex_ascii()` — renders raw bytes as separate `Hex:` / `ASCII:` lines with U+FFFD for non-printable
- [x] **A2** Added `format_device_info_block()` — renders Device1 properties in labelled info block (ManufacturerData key as hex+decimal, value as Hex/ASCII; ServiceData UUID with resolved name; Class decoded via `format_device_class`; Appearance decoded via `decode_appearance`)
- [x] **A3** Updated `format_gatt_tree()` — added `device_props` parameter; prepends Device Information block when provided
- [x] **A4** Updated characteristic/descriptor ASCII display — now derives ASCII from raw bytes with U+FFFD, always shows both Hex and ASCII when raw is available

### Area B – Data Collection (adapter.py, scan.py)
- [x] **B1** `adapter.py` — `get_discovered_devices()` now extracts `ManufacturerData`, `ServiceData`, `TxPower`, `Appearance`, `Modalias`, `Paired`, `Trusted`, `Blocked` with D-Bus-to-Python type conversion
- [x] **B2** `scan.py` — Added `_collect_device_props()` helper using `Properties.GetAll("org.bluez.Device1")`
- [x] **B3** `scan.py` — `_base_enum()` returns device_props as 5th tuple element; all enum wrappers (`passive_enum`, `naggy_enum`, `pokey_enum`, `brute_enum`) propagate `device_props` in result dicts

### Area C – CLI Integration (cli.py)
- [x] **C1** `gatt-enum` handler passes `device_props` (via `_collect_device_props`) to `format_gatt_tree()`
- [x] **C2** `enum-scan` handler passes `device_props` from enum result dict to `format_gatt_tree()`

---

## Comprehensive BlueZ Property Coverage (2026-03-19) – COMPLETE

**Goal**: Close D-Bus property coverage gaps across all BlueZ interfaces (Device1, GattService1, GattCharacteristic1, GattDescriptor1, Battery1, Input1, Adapter1) by capturing and displaying all specification-defined properties that BLEEP encounters.

### Phase 1 – GATT Tree Display Enhancements
- [x] **1a** `characteristic.py` — Capture `MTU` and `Notifying` from `GattCharacteristic1` D-Bus properties
- [x] **1b** `conversion.py` — Display `MTU` and `Notifying` in `format_gatt_tree()` characteristic output
- [x] **1c** `conversion.py` — Display descriptor `Flags` and `Handle` in `format_gatt_tree()` descriptor output
- [x] **1d** `conversion.py` — Display service `Primary`/`Secondary`, `Handle`, and `Includes` in `format_gatt_tree()` service output
- [x] **1e** `service.py` — Capture `Includes` property from `GattService1`; `device_le.py` — Add `Primary`, `Handle`, `Includes` to deep-mode service mapping

### Phase 2 – Battery1 and Input1 Interfaces
- [x] **2a** `scan.py` — `_collect_device_props()` now probes `org.bluez.Battery1` and `org.bluez.Input1` on the device path
- [x] **2b** `conversion.py` — `format_device_info_block()` displays Battery1 `Percentage` and `Source`
- [x] **2c** `scan.py` — Input1 properties collected alongside Battery1
- [x] **2d** `conversion.py` — `format_device_info_block()` displays Input1 `ReconnectMode` with human-readable policy explanation (`none`/`host`/`device`/`any`)

### Phase 3 – Device1 Display Improvements
- [x] **3a** `conversion.py` — `format_device_info_block()` now handles `Bonded`, `WakeAllowed`, `Icon`, `AdvertisingFlags` (hex/ASCII), and `AdvertisingData` (type-keyed hex/ASCII)
- [x] **3b** `adapter.py` — `get_discovered_devices()` now includes `bonded`, `wake_allowed`, `icon`, `advertising_flags`, `advertising_data`

### Phase 4 – Adapter1 Enhancements
- [x] **4a** `adapter_config.py` — `_DBUS_PROPERTY_MAP` expanded with `power-state`, `manufacturer`, `version`, `experimental-features`
- [x] **4b** `adapter_config.py` — `adapter-config show` display order includes `PowerState`, `Manufacturer`, `Version`, `ExperimentalFeatures` (listed individually)

### Documentation
- [x] **D1** Created `bleep/docs/bluez_interface_properties.md` — comprehensive property reference with security/significance notes for all captured BlueZ interfaces
- [x] **D2** Updated `bleep/docs/gatt_enumeration.md` — reflects enriched GATT tree output
- [x] **D3** Updated `bleep/docs/adapter_config.md` — expanded property table with new Adapter1 properties
- [x] **D4** Updated `bleep/docs/changelog.md` — v2.7.30 entry
- [x] **D5** Updated `bleep/docs/todo_tracker.md` — this section

---

## Future Work — Codebase-Wide UUID Uppercase Normalization

- [x] **UUID-1** ~~Audit and normalize all UUID usage across the entire BLEEP codebase to uppercase~~ — **CLOSED** (2026-05-22, PREP-7B): Full codebase normalization complete — reference dicts, D-Bus boundary, runtime comparisons, DB storage all use uppercase canonical form.
- [x] **UUID-2** ~~Verify `upsert_services()` return-key behavior after UUID normalization~~ — **CLOSED** (2026-05-22, PREP-7B): `_normalize_uuid()` already uppercases in `_services.py`; `upsert_device()` now normalizes `uuids` list before JSON serialization.

---

## BLEEP Usability Improvement (2026-03-17) – COMPLETE

**Goal**: Fix database FK errors causing data loss, make non-deep GATT enumeration actually read values, clean up debug output spam, and present enumeration results in a human-readable tree format.

### Area A – Database Tracking Fixes
- [x] **A1** `observations.py` — Added `_ensure_device_exists(cur, mac)` helper that performs `INSERT OR IGNORE` to guarantee parent device rows exist before any child-table insert
- [x] **A2** `observations.py` — Integrated `_ensure_device_exists` into 8 child-table methods: `insert_adv`, `upsert_services`, `upsert_classic_services`, `insert_char_history`, `upsert_sdp_record`, `upsert_pbap_metadata`, `store_aoi_analysis`, `store_device_type_evidence`
- [x] **A3** `observations.py` — Added `_DB_CONN.rollback()` to `_db_cursor()` except block to prevent partial writes
- [x] **A4** `observations.py` — Replaced all ~15 raw `print(f"[DEBUG]...", file=sys.stderr)` calls in `store_signal_capture()` with `print_and_log(message, LOG__DEBUG)`

### Area B – GATT Enumeration & CLI Output
- [x] **B1** `characteristic.py` — Added `read_value_with_fallback()` implementing three-tier read strategy: `ReadValue({"offset":0})` → `ReadValue({})` → `Properties.Get("Value")`; treats `b"\x00"` as valid data
- [x] **B2** `characteristic.py` — Updated `safe_read_with_retry()` to call `read_value_with_fallback()` instead of `read_value()`
- [x] **B3** `device_le.py` — Refactored `_deep_enumerate_gatt()` into `_enumerate_gatt_values(deep: bool)`: deep=True uses retried reads with uppercase mapping format; deep=False performs single reads into existing lowercase mapping
- [x] **B3a** `device_le.py` — Extracted error classification into `_classify_read_errors()` static method and `_apply_error_classification()` instance method (shared between deep and non-deep paths)
- [x] **B3b** `device_le.py` — `services_resolved()` now always calls `_enumerate_gatt_values(deep=deep)` after structure discovery, ensuring values are read even without `--deep`
- [x] **B3c** `device_le.py` — Guarded `_properties_changed` signal handler with `if not self._services:` to prevent redundant re-enumeration
- [x] **B4** `device_le.py` — Added `read_characteristic_with_fallback()` wrapper method
- [x] **B5** `brute.py` — Changed `brute_read_all()` to call `device.read_characteristic_with_fallback()` instead of `device.read_characteristic()`
- [x] **B6** `scan.py` — Updated `naggy_enum()` to: (1) update mapping with most recent multi-read value, (2) detect value changes across rounds into `changed_chars` set, (3) return full result dict including mapping and changed_chars
- [x] **B7** `descriptor.py` — Fixed `b"\x00"` fabrication: changed fallback conditions from `result == b"\x00"` to `not result`, changed final return from `result or b"\x00"` to `result if result is not None else b""`
- [x] **B8** `conversion.py` — Added `format_gatt_tree()` producing human-readable tree output with service/characteristic/descriptor hierarchy, hex/ASCII values, UUID name resolution, mine/permission map summaries, and changed-value indicators
- [x] **B9** `cli.py` — Replaced raw JSON `_dump()` output for `gatt-enum` and `enum-scan` with `format_gatt_tree()`
- [x] **B10** `cli.py` — Replaced all raw `print(f"[DEBUG]...", file=sys.stderr)` calls with `print_and_log(message, LOG__DEBUG)`

---

## Codebase Cleanup & Preparation for v2.8.0 (2026-03-10) – COMPLETE

**Goal**: Review, de-duplicate, and clean up the BLEEP codebase prior to v2.8.0 expansion.  Enforce MAC address uniformity (uppercase), harden the database schema, fix exception handling, and guard placeholder module imports.

**Status**: Complete.

- [x] **Phase 1A** `observations.py` — `_normalize_mac()` changed from `.lower()` to `.upper()`
- [x] **Phase 1B** `observations.py` — Added `_normalize_mac()` calls to `upsert_classic_services`, `upsert_pbap_metadata`, `snapshot_media_player`, `snapshot_media_transport`
- [x] **Phase 1C** Multiple files — Converted all `.lower()` on MAC variables to `.upper()` across 17 files
- [x] **Phase 1D** `media_stream.py` — Fixed colon-vs-underscore MAC comparison bug
- [x] **Phase 1E** Audio subsystem — Harmonized `_norm()`, `extract_mac_from_alsa_device()`, and all MAC comparisons/filenames to uppercase
- [x] **Phase 1F** `observations.py` — Added schema migration v7→v8 converting all existing MACs to uppercase
- [x] **Phase 2A** `observations.py` — Removed duplicate `sdp_records` table definition from `_SCHEMA_SQL`
- [x] **Phase 2B** `observations.py` — Fixed `upsert_sdp_record()` to use `json_dumps()`, `upsert_characteristics()` BLOB type handling and `permission_map` storage, `upsert_device()` column whitelist, `explain_query()` single-SELECT restriction, `get_devices()` DISTINCT fix, `maintain_database()` table list completeness
- [x] **Phase 3A** `mesh/__init__.py` — Guarded `agent`/`provisioning` imports with `try/except ImportError`
- [x] **Phase 3B** `gatt/__init__.py` — Guarded `service`/`characteristic`/`descriptor` imports with `try/except ImportError`
- [x] **Phase 3C** `dbus/__init__.py` — Removed phantom `adapter`/`gatt` from `__all__`, added `connection_pool`
- [x] **Phase 4A** 9 files — Narrowed 14 bare `except:` blocks to specific exception types
- [x] **Phase 4B** 5 files — Added `LOG__DEBUG` logging to critical `except Exception: pass` blocks
- [x] **Phase 5** Full codebase — Gap analysis sweep caught 12 additional MAC `.lower()` sites
- [x] **Phase 6** Documentation — changelog, todo_tracker, version bump to v2.7.27

---

## Debug Mode: Lazy Imports, MAP Pagination & Folder-Context UX (2026-03-30) – COMPLETE

**Goal**: Eliminate the ``RuntimeWarning`` when launching Debug Mode via ``python -m bleep.modes.debug``, add user-controlled MAP message pagination to prevent BlueZ obexd timeouts on large folders, add a quick folder-probe command, and improve error guidance when ``cmap get`` targets a handle from a different folder context.

**Status**: Complete.  All fixes verified via live device testing against SAMSUNG-SM-G891A (E4:FA:ED:83:D8:47).

- [x] **(A)** `bleep/modes/__init__.py` — Replaced eager ``import_module`` calls with PEP 562 ``__getattr__``-based lazy imports.  Submodules are now imported on first attribute access, preventing ``runpy`` from finding them pre-loaded in ``sys.modules`` and emitting the ``RuntimeWarning``.
- [x] **(B)** `bleep/modes/debug_classic_obex.py` — Added ``cmap peek`` sub-command: enumerates all leaf folders via ``_collect_leaf_paths()``, then calls ``list_messages()`` with ``MaxCount=1`` for each.  Prints a one-line summary per folder and a final accessible/total tally.  Confirms folder reachability in seconds without triggering full-listing overhead.
- [x] **(C)** `bleep/modes/debug_classic_obex.py` — Added ``--count N`` and ``--offset M`` optional arguments to ``cmap list``.  Parsed inline and passed as ``MaxCount`` / ``Offset`` D-Bus filters to ``list_messages()``.  Output label reflects active pagination (``[count=N]`` / ``[offset=M, count=N]``).  Without flags, existing default behaviour (obexd ``MaxListCount=1024``) is preserved.
- [x] **(D)** `bleep/modes/debug_classic_obex.py` — Enhanced ``cmap get`` error handler: when ``UnknownObject`` or ``does not exist`` is detected, prints the current ``_last_map_folder`` and advises the user to re-run ``cmap list <correct_folder>`` before retrying.
- [x] **(E)** Updated ``cmap`` help text to document ``peek``, ``--count``, ``--offset``, and the folder-context caveat.

### Root Cause

- **(A)** ``bleep/modes/__init__.py`` eagerly called ``import_module()`` for every submodule at package scope.  When invoked via ``python -m bleep.modes.debug``, Python's ``runpy`` imports the package first (triggering the eager imports and placing ``bleep.modes.debug`` into ``sys.modules``), then attempts to execute it as ``__main__`` — finding it already present, which produces the ``RuntimeWarning``.
- **(B/C)** BlueZ obexd's ``ListMessages`` implementation (``obexd/client/map.c``) defaults to ``MaxListCount=1024``, buffers the entire MAP XML listing in memory, parses it synchronously, and registers a D-Bus ``Message1`` object for each entry before returning the reply.  On a device with a large inbox, this synchronous processing can exceed D-Bus and OBEX timeouts, causing a perceived freeze.
- **(D)** ``get_message()`` constructs a D-Bus object path using the handle and the *current* OBEX session folder.  If the user lists folder A, then lists folder B, then tries to ``cmap get`` a handle from folder A, the OBEX session is re-established against folder B and the handle's D-Bus object does not exist — producing ``UnknownObject``.

### Evidence

- BlueZ ``obexd/client/map.c`` line 59: ``#define DEFAULT_COUNT 1024`` — default ``MaxListCount``.
- BlueZ ``obexd/client/map.c`` lines 1335-1391: ``message_listing_cb()`` — full XML buffered and parsed synchronously.
- BlueZ ``gobex/gobex.c`` line 25: ``#define G_OBEX_DEFAULT_TIMEOUT 10`` — 10s inter-packet timeout.
- ``bleep/dbuslayer/obex_map.py`` line 239: D-Bus object path ``f"{self._session_path}/message{handle}"`` — handle resolved against current session folder.

---

## Debug Mode UX: Mines Command, Help Grouping & Unified Info Display (2026-03-10) – COMPLETE

**Goal**: Expose enumeration mine/permission mappings to the user in Debug Mode, reorganise the help menu for clarity, and unify `info` output between BLE and Classic devices.

**Status**: Complete.

- [x] **M1** `debug_scan.py` — `cmd_mines()`: human-readable display of `current_mine_map` / `current_perm_map` grouped by object type and issue; optionally shows `get_landmine_report()` / `get_security_report()` when device is connected
- [x] **M2** `debug.py` — `mines` added to dispatch table and import list
- [x] **M3** `debug.py` — `_cmd_help()` rewritten with purpose-based groups; `detailed off` shows compact command names per group, `detailed on` shows full usage + description
- [x] **M4** `debug_connect.py` — `cmd_info()` refactored: `_info_ble()`, `_info_classic()`, `_info_from_dbus_path()` all use `_print_unified_props()` and `_format_bool()`; Title Case labels, aligned columns, booleans shown as `True (1)` / `False (0)`; raw device data never altered
- [x] **M5** `debug_connect.py` — All `(*)` clarifiers in Classic `info` gated on `detailed_view`: boolean `(N)` suffix, Device Class decode, profile UUID names, `(BR/EDR)` type label; `(use 'cservices' to list)` stays unconditional
- [x] **M6** `debug_scan.py` — Enum summary labels changed from `mine=`/`perm=` to `landmines=`/`permissions=`; counts now reflect total UUIDs via `_count_map_uuids()` instead of category bucket count

---

## MAP Fixes, Timeouts, Property Access, Handle Context, Push Validation & Error Hints (2026-03-10) – COMPLETE

**Goal**: Fix MAP interactivity bugs in BLEEP Debug Mode — service detection, folder semantics, D-Bus data handling, error handling, debug logging, recursive folder enumeration, redundant SDP scans, sdptool XML parsing, message handle lifecycle, bMessage validation, CreateSession D-Bus signature, D-Bus property access for message flags, bMessage LENGTH validation, D-Bus method call timeouts, and actionable error hints for Service Unavailable / NoReply / device sleep.

**Status**: Complete.  All fixes implemented and verified via live device testing (five rounds).

- **(A) Service detection miss**: `detect_map_service()` only matched UUID substrings and `"message"`/`"map"` in service-map keys, but `build_svc_map` keys the MAP service as `"SMS/MMS"` (from the SDP Service Name).  **Fixed**: added `"sms"` and `"mms"` key patterns, consistent with all sibling `detect_*_service` functions.
- **(B) Double-folder bug**: `list_messages()` called `set_folder(folder)` then `list_messages(folder)` — resolving as `folder/folder`.  **Fixed**: now calls `list_messages("")` after navigating.
- **(C) Root/dot rejection**: `cmap list` at root and `cmap list .` both failed with opaque OBEX errors.  **Fixed**: root is rejected early with an actionable hint; `.`/`..` are caught with a clear message.
- **(D) SupportedTypes crash**: `get_supported_types()` crashed on BlueZ 5.64 which doesn't expose the property.  **Fixed**: catches `DBusException`, logs to `LOG__DEBUG`, returns empty list.
- **(E) Redundant SDP scans**: every `cmap instances` triggered a fresh `sdptool` call.  **Fixed**: accepts optional `service_map` from `state.current_mapping`.
- **(F) sdptool XML empty records**: `_parse_xml_record()` used `elem.text` which fails for sdptool's `<text value="..."/>` format.  **Fixed**: new `_xml_elem_value()` helper checks both formats.

### Root Cause

- [x] **R1** `classic_map.py` — `detect_map_service()` key patterns did not cover `"SMS/MMS"` service name
- [x] **R2** `classic_map.py` — `list_messages()` passed `folder` to both `set_folder()` and `list_messages()`, doubling the path
- [x] **R3** `obex_map.py` — `get_supported_types()` had no error handling for missing properties
- [x] **R4** `classic_map.py` — `list_mas_instances()` always ran fresh SDP discovery
- [x] **R5** `classic_sdp.py` — `_parse_xml_record()` only handled text-content XML, not value-attribute XML

### Implementation

- [x] **I1** `classic_map.py` — `detect_map_service()`: added `"sms"` and `"mms"` to key matching
- [x] **I2** `classic_map.py` — `list_messages()`: sanitize `.`/`..`, fix double-folder, always `list_messages("")`
- [x] **I3** `debug_classic_obex.py` — `cmap list`: reject empty folder at UX layer with hint
- [x] **I4** `debug_classic_obex.py` — `_print_obex_error_hints()`: MAP-specific branches (bad request, not found, no such property, unknown object)
- [x] **I5** `debug_classic_obex.py` — all `cmd_cmap` error paths: `operation="map"`, `format_dbus_error()`
- [x] **I6** `obex_map.py` — `get_supported_types()`: try/except with `LOG__DEBUG` logging
- [x] **I7** `debug_classic_obex.py` — `cmap props`: validate handle is alphanumeric
- [x] **I8** `classic_map.py` — `list_mas_instances()`: optional `service_map` parameter for cached lookup
- [x] **I9** `debug_classic_obex.py` — `cmap instances`: passes `state.current_mapping`
- [x] **I10** `classic_sdp.py` — `_xml_elem_value()`, `_xml_findtext()`, `_parse_xml_record()` rewritten

### Round 2 — D-Bus Iteration Fix, Tree Enumeration & Debug Logging

- [x] **R6** `obex_map.py` — `list_messages()` iterated `dbus.Dictionary` directly instead of `.items()`, causing `ValueError: too many values to unpack`
- [x] **R7** `debug_classic_obex.py` — `ValueError` and other exceptions in `cmd_cmap` were not logged to `LOG__DEBUG`
- [x] **R8** `classic_map.py` — `.`/`..` validation in `list_messages()` conflated with genuine D-Bus errors

### Round 2 — Implementation

- [x] **I11** `obex_map.py` — `list_messages()`: use `.items()` with defensive type checking for `dbus.Dictionary` vs `dbus.Array`
- [x] **I12** `obex_map.py` — `list_messages()`: add `LOG__DEBUG` logging of raw return type/length before unpacking
- [x] **I13** `obex_map.py` — `walk_folder_tree()`: recursive `SetFolder` + `ListFolders` tree walk with `max_depth` guard
- [x] **I14** `classic_map.py` — `list_folder_tree()`: high-level wrapper with BLEEP logging
- [x] **I15** `classic_map.py` — `list_messages()`: removed `.`/`..` validation (moved to command layer)
- [x] **I16** `debug_classic_obex.py` — `cmap folders`: full tree display via `_print_folder_tree()`
- [x] **I17** `debug_classic_obex.py` — `cmap list`: `.`/`..` validation before `try` block; `_suggest_map_leaf_folders()` on "bad request"
- [x] **I18** `debug_classic_obex.py` — all `cmd_cmap` `except` clauses: `print_and_log(..., LOG__DEBUG)`

### Round 3 — Handle Context, Push Validation, Error Hints & CreateSession Signature

- [x] **R9** `obex_map.py` — `CreateSession` passed plain `dict` which `dbus-python` inferred as `a{ss}` instead of required `a{sv}`
- [x] **R10** `obex_map.py` — message D-Bus objects are ephemeral and session-scoped; handle-based methods created fresh sessions that did not contain the message objects
- [x] **R11** `debug_classic_obex.py` — handle-based commands (`get`, `props`, `read`, `delete`) did not provide folder context to populate message objects
- [x] **R12** `debug_classic_obex.py` — `cmap push` accepted plain-text files without warning about bMessage format requirement
- [x] **R13** `debug_classic_obex.py` — `_print_obex_error_hints()` matched `"not implemented"` and `"unknownmethod"` errors with the generic `"obex"` catch-all

### Round 3 — Implementation

- [x] **I19** `obex_map.py` — `CreateSession`: wrap `session_args` in `dbus.Dictionary(..., signature="sv")`
- [x] **I20** `obex_map.py` — `_populate_message_objects(folder)`: navigate + `ListMessages("")` to materialise handles
- [x] **I21** `obex_map.py` — `get_message()`, `get_message_properties()`, `set_message_read()`, `set_message_deleted()`: accept `folder` kwarg, call `_populate_message_objects` when provided
- [x] **I22** `classic_map.py` — `get_message()`: pass `folder` kwarg through to `MapSession.get_message()`
- [x] **I23** `debug_classic_obex.py` — `_last_map_folder` + `_require_map_folder()`: track folder context from `cmap list`
- [x] **I24** `debug_classic_obex.py` — `cmap get/props/read/delete`: use `_require_map_folder()` before handle access
- [x] **I25** `debug_classic_obex.py` — `cmap push`: warn when file lacks `BEGIN:BMSG` header
- [x] **I26** `debug_classic_obex.py` — `_print_obex_error_hints()`: specific branches for `"not implemented"` and `"unknownmethod"` before generic `"obex"` check
- [x] **I27** `debug_classic_obex.py` — updated `cmap` help text: folder-context dependency, bMessage format note

### Round 4 — D-Bus Property Access Fix & Push LENGTH Validation

- [x] **R14** `obex_map.py` — `set_message_read()` and `set_message_deleted()` called `Message1.SetProperty()` which does not exist in BlueZ's GDBus implementation; `Read` and `Deleted` are standard D-Bus properties accessed via `Properties.Set()`
- [x] **R15** `debug_classic_obex.py` — `cmap push` did not validate the `LENGTH:` field in bMessage files, allowing silently malformed pushes when users edit downloaded messages without updating the byte count

### Round 4 — Implementation

- [x] **I28** `obex_map.py` — `set_message_read()`: use `dbus.Interface(obj, DBUS_PROPERTIES).Set(_OBEX_MSG_IFACE, "Read", dbus.Boolean(read, variant_level=1))`
- [x] **I29** `obex_map.py` — `set_message_deleted()`: same pattern with `"Deleted"` property
- [x] **I30** `debug_classic_obex.py` — `_validate_bmsg_length()`: parse `LENGTH:` field, compute actual `BEGIN:MSG` … `END:MSG` byte size, warn on mismatch with correct value

### Round 5 — D-Bus Timeout Fix, Error Hints & UX Improvements

- [x] **R16** `obex_map.py` — D-Bus method calls (`ListMessages`, `ListFolders`, `UpdateInbox`, `ListFilterFields`, `_populate_message_objects`) used the dbus-python default timeout (~25 s), causing `NoReply` errors for large inbox folders (100+ messages)
- [x] **R17** `debug_classic_obex.py` — `_print_obex_error_hints()` had no branch for `"service unavailable"` (OBEX 0x53), falling through to the generic `"obex"` catch-all with misleading advice
- [x] **R18** `debug_classic_obex.py` — `_print_obex_error_hints()` had no branch for `"noreply"` D-Bus timeout errors
- [x] **R19** `debug_classic_obex.py` — `cmap read` did not warn when targeting non-inbox folders where `readStatus` changes are semantically rejected
- [x] **R20** `debug_classic_obex.py` — OBEX timeout hint did not mention device sleep/lock state as the most common cause
- [x] **R21** `debug_classic_obex.py` — `cmap` help text did not distinguish `get` (download contents) from `read` (toggle status flag)

### Round 5 — Implementation

- [x] **I31** `obex_map.py` — `list_folders()`: pass `timeout=self._timeout`
- [x] **I32** `obex_map.py` — `list_messages()`: pass `timeout=self._timeout * 4` (120 s default) for large-folder support
- [x] **I33** `obex_map.py` — `_populate_message_objects()`: pass `timeout=self._timeout * 4`
- [x] **I34** `obex_map.py` — `update_inbox()`: pass `timeout=self._timeout`
- [x] **I35** `obex_map.py` — `list_filter_fields()`: pass `timeout=self._timeout`
- [x] **I36** `debug_classic_obex.py` — `_print_obex_error_hints()`: new `"service unavailable"` branch with MAP folder guidance
- [x] **I37** `debug_classic_obex.py` — `_print_obex_error_hints()`: new `"noreply"` branch with large-folder guidance
- [x] **I38** `debug_classic_obex.py` — `cmap read`: proactive warning when folder context is not `inbox`
- [x] **I39** `debug_classic_obex.py` — OBEX timeout hint updated: mentions device sleep/lock as primary cause
- [x] **I40** `debug_classic_obex.py` — `cmap` help text: clarified `get` = download contents, `read` = toggle flag; added device wake tip

### Documentation

- [x] **D1** `changelog.md`: v2.7.22 (round 1-2); v2.7.23 (round 3); v2.7.24 (round 4); v2.7.25 (round 5)
- [x] **D2** `todo_tracker.md`: this section (updated with round 5)
- [x] **D3** `__init__.py`: version bumped to 2.7.25
- [x] **D4** `learned-memories.mdc`: MAP technical decisions (updated with round 5)

### Live-Device Testing Verification (Samsung SM-G891A, E4:FA:ED:83:D8:47)

All `cmap` commands verified against a Samsung SM-G891A (Android) target device.

| Command | Status | Notes |
|---------|--------|-------|
| `cmap folders` | **PASS** | Full tree enumerated: telecom/msg/{inbox,outbox,sent,deleted,draft} |
| `cmap list telecom/msg/inbox` | **PASS** | Returns 100 messages; may time out on first attempt if device is asleep — succeeds on retry once device is awake |
| `cmap list telecom/msg/outbox` | **PASS** | Returns 14 messages |
| `cmap list telecom/msg/deleted` | **PASS** | Returns 4 messages |
| `cmap list telecom/msg/draft` | **PASS** | Returns 1 message |
| `cmap list telecom/msg/sent` | **INTERMITTENT** | Times out when device is asleep; expected to succeed once device is awake (large folder) |
| `cmap get <handle>` | **PASS** | Downloads full bMessage to file and displays contents (prior rounds) |
| `cmap push <file>` | **PASS** | Succeeds with correctly formatted bMessage (LENGTH field must match); prior rounds |
| `cmap inbox` | **PASS** | Triggers inbox update (prior rounds) |
| `cmap props <handle>` | **PASS** | Returns message properties (prior rounds) |
| `cmap read <handle> true` | **PASS** | Successfully marks inbox message as read |
| `cmap read <handle> false` | **PASS** | Successfully marks inbox message as unread; confirmed via subsequent `cmap list` showing `[ ]` |
| `cmap read <handle>` (outbox) | **EXPECTED FAIL** | Device rejects readStatus on outbox messages with `Service Unavailable` (device-side semantic restriction) |
| `cmap delete <handle>` | **PASS** | Successfully marks message as deleted (prior rounds) |
| `cmap types` | **PASS** | Returns supported types or degrades gracefully (prior rounds) |
| `cmap instances` | **PASS** | Lists MAS instances from SDP (prior rounds) |

**Key observations from testing:**
- Device sleep/lock is the primary cause of OBEX-level timeouts (`Timed out waiting for response`), not D-Bus timeouts.  Once the phone is awake, requests succeed quickly.
- `readStatus` changes are only accepted for inbox messages; outbox/sent/draft/deleted folders return `Service Unavailable` — this is a device-side semantic restriction, not a BLEEP bug.
- `cmap read` toggles the read/unread status flag; `cmap get` downloads and displays full message contents — naming clarified in help text.
- The D-Bus timeout fix (Round 5) prevents `NoReply` errors for large folders; OBEX-level timeouts from the device itself cannot be addressed in code.

---

## OPP Fast-Completion Race Fix (2026-03-09) – COMPLETE

**Goal**: Fix false-failure reporting for OPP transfers that complete faster than the poller can read them, and provide clear diagnostics for unsupported operations.

**Status**: Complete.  All fixes implemented and verified via live device testing against SCH-U365.

- **(D) False send failure**: `copp send /tmp/test.vcf` delivered the file successfully (phone received and stored it), but BLEEP reported failure because obexd removed the Transfer1 object before `poll_obex_transfer()`'s first `props.Get()` call.  The v2.7.20 fix treated ALL removed-object cases as failures — wrong for fast-completing sends.  **Fixed**: now correctly reports `[+] OPP send complete: ?/107 bytes transferred`.
- **(E) Pull works**: Contrary to earlier hypothesis, `copp pull` **does** work against the SCH-U365.  The fast-completion race was masking success.  The file is now validated (existence + non-zero size) and reported with byte count.  **Fixed**: now reports `[+] Business card saved → <path> (<N> bytes)`.
- **(F) ExchangeBusinessCards unimplemented**: obexd 5.64 does not implement `ObjectPush1.ExchangeBusinessCards` — returns `org.bluez.obex.Error.Failed: Not Implemented`.  **Fixed**: clean error message with actionable guidance.  Acknowledged as implemented (acceptable behavior).

**Design note**: BlueZ reference code (`opp-client`, `obexctl`) relies solely on Transfer1 `Status` for success detection and does not check file existence or size.  However, `obexd/client/transfer.c` removes the file on failed GET transfers, making file existence a reliable success indicator.  BLEEP goes beyond the reference by validating file existence + non-zero size for all completion paths.

### Root Cause

- [x] **R7** `_obex_common.py` — `poll_obex_transfer()` raised `RuntimeError` on all `DBusException(UnknownObject)` cases, including successful fast-completing transfers where obexd removed the Transfer1 object after completion.  Callers could not distinguish fast success from genuine failure.
- [x] **R8** `obex_opp.py` — `opp_send_file()` propagated the poller's `RuntimeError` without checking whether the send actually succeeded (it did — the phone received the file).
- [x] **R9** `obex_opp.py` — `opp_pull_business_card()` similarly propagated the error without checking if the dest file was written (it was — pull does work on SCH-U365).
- [x] **R10** `obex_opp.py` — `opp_exchange_business_cards()` did not detect the "Not Implemented" D-Bus error, producing a generic error message instead of actionable guidance.

### Implementation

- [x] **I11** `_obex_common.py` — `poll_obex_transfer()` returns `{"status": "removed"}` instead of raising when the transfer object is gone.  Callers verify the actual outcome.
- [x] **I12** `obex_opp.py` — `opp_send_file()` treats "removed" as fast completion (send succeeded).
- [x] **I13** `obex_opp.py` — `opp_pull_business_card()` validates dest file (existence + non-zero size) for all completion paths — both normal "complete" and fast-race "removed".  Raises clear error when no file was written.
- [x] **I14** `obex_opp.py` — `opp_exchange_business_cards()` detects "Not Implemented" and raises a clear message directing users to use separate send/pull.
- [x] **I15** `debug_classic_obex.py` — `_print_obex_error_hints()` updated with specific hints for pull-unsupported and exchange-unimplemented errors.
- [x] **I16** `debug_classic_obex.py`, `cli.py`, `classic_opp.py` — Pull success messages now include file size in bytes.

### Verification

- [x] `copp send /tmp/test.vcf` — reports `[+] OPP send complete: ?/107 bytes transferred` (file delivered)
- [x] `copp pull` — reports `[+] Business card saved → ~/.cache/obexd/…_card.vcf` (file received, SCH-U365 name card)
- [x] `copp exchange` — reports `OPP ExchangeBusinessCards is not supported by this version of obexd` (acknowledged as acceptable)

### Documentation

- [x] **D4** `changelog.md`: v2.7.21 entry (updated with verified results)
- [x] **D5** `todo_tracker.md`: this section
- [x] **D6** `__init__.py`: version bumped to 2.7.21

---

## OPP OBEX Polishing (2026-03-09) – COMPLETE

**Goal**: Resolve remaining OPP failures observed against the SCH-U365 (`14:89:FD:31:8A:7E`), including a transfer-object race condition, empty SDP records preventing Channel hints, and a potential obexd file-write path restriction.  Add `ExchangeBusinessCards` support and improve OPP diagnostics.

**Status**: Complete.  Superseded by "OPP Fast-Completion Race Fix" above which corrects false failure reporting for fast-completing transfers.

- **(A) SDP parsing failure**: `cservices` returned 5 records with all fields empty (`handle_None`, no RFCOMM channels) even though BlueZ's `UUIDs` D-Bus property correctly listed OPP (`0x1105`).  A fallback targeted `sdptool search` now discovers the OPP RFCOMM channel when full SDP parsing fails.
- **(B) Transfer-object race condition**: When the SCH-U365 accepted the OBEX connection but failed the vCard transfer immediately (phone showed "sending" then "failure in sending"), obexd tore down the `Transfer1` object before `poll_obex_transfer()` could read its `Status` property.  The raw `DBusException(UnknownObject)` propagated unhandled to the user.  The poller now catches this and raises a descriptive `RuntimeError`. *(As of this 2026-03 work; the poller's error type was later migrated to `TimeoutError`/`BLEEPError` under OBEX-D2 — see Unreleased in `changelog.md`.)*
- **(C) Dest path restriction**: Default `copp pull` destination was `/tmp/`, which may be outside obexd's permitted write area on Ubuntu (AppArmor).  Changed to `~/.cache/obexd/`.

**Observation**: Despite the host OS reporting "no supported services" to the target device during generic Bluetooth connection, BLEEP's targeted OPP operations via obexd *do* reach the phone — the device prompts the user to accept and attempts the transfer.  This confirms that profile-level operations can succeed even when the host's SDP presentation appears incompatible, making OPP operations always worth attempting.

### Root Cause (updated from v2.7.19)

- [x] **R1** (v2.7.19) `obex_opp.py` CreateSession without Channel hint → obexd SDP timeout. *Fixed in v2.7.19.*
- [x] **R2** (v2.7.19) `obex_opp.py` session-object access not wrapped in try/except. *Fixed in v2.7.19.*
- [x] **R3** (v2.7.19) `classic_pbap.py` redundant local import → NameError in watchdog. *Fixed in v2.7.19.*
- [x] **R4** `_obex_common.py` `poll_obex_transfer()` does not handle `DBusException` when the transfer object is torn down by obexd before the poller reads `Status` — the raw `UnknownObject` error propagates to the user instead of a descriptive `RuntimeError`. *(Error type later migrated to `TimeoutError`/`BLEEPError` under OBEX-D2.)*
- [x] **R5** `debug_classic_obex.py` `_extract_opp_channel()` returns `None` when SDP parsing produces empty records (`handle_None`); no fallback to targeted `sdptool search` exists, so `CreateSession` goes without a Channel hint.
- [x] **R6** Default `copp pull` destination (`/tmp/`) may be outside obexd's AppArmor-permitted write area on Ubuntu, causing obexd to abort the incoming vCard transfer (phone shows "failure in sending").

### Implementation

- [x] **I1** (v2.7.19) Channel passthrough + session exception wrapping in `obex_opp.py`.
- [x] **I2** (v2.7.19) Channel threading in `classic_opp.py`.
- [x] **I3** (v2.7.19) Channel extraction + error hints in `debug_classic_obex.py`.
- [x] **I4** (v2.7.19) PBAP local-import fix in `classic_pbap.py`.
- [x] **I5** `_obex_common.py` — Wrap `props.Get()` in `poll_obex_transfer()` with `try/except dbus.exceptions.DBusException`; treat torn-down transfer as a failed transfer with descriptive error.
- [x] **I6** `obex_opp.py` — Add explicit 90 s D-Bus method-call timeout to `SendFile`, `PullBusinessCard`, and `ExchangeBusinessCards` to prevent indefinite blocking.
- [x] **I7** `obex_opp.py` — Add `opp_exchange_business_cards()` wrapping `ObjectPush1.ExchangeBusinessCards` per `org.bluez.obex.ObjectPush(5)`.
- [x] **I8** `classic_opp.py` — Add `exchange_business_cards()` operations wrapper.
- [x] **I9** `classic_sdp.py` — Add `discover_service_channel(mac, uuid_short)` for targeted single-service SDP lookup via `sdptool search --bdaddr`.
- [x] **I10** `debug_classic_obex.py` — `_resolve_opp_channel()` tries `_extract_opp_channel()` first, falls back to `discover_service_channel()`. Default pull dest changed to `~/.cache/obexd/`. `copp exchange` subcommand added. `_print_obex_error_hints()` enhanced with `operation` parameter and transfer-teardown guidance. Usage text documents OPP listing limitation.

### Verification

- [x] Channel passthrough confirmed: phone prompts user to accept OPP connection (v2.7.19)
- [x] Session exception handling confirmed: `UnknownObject` no longer escapes as raw `DBusException` (v2.7.19)
- [x] PBAP `_watchdog_cb` NameError confirmed fixed (v2.7.19)
- [x] Transfer-object race condition handled: `poll_obex_transfer` catches `DBusException` and raises descriptive `RuntimeError` *(error type later migrated to `TimeoutError`/`BLEEPError` under OBEX-D2)*
- [x] `copp send` — file delivered to SCH-U365 (reported as failure in v2.7.20 due to race — fixed in v2.7.21)
- [x] `copp pull` — successfully retrieves SCH-U365 name card (earlier failure was due to race, not device limitation — fixed in v2.7.21)
- [x] `copp exchange` — confirmed obexd 5.64 does not implement `ExchangeBusinessCards` (acknowledged as acceptable)

### Documentation

- [x] **D1** `changelog.md`: v2.7.20 entry
- [x] **D2** `todo_tracker.md`: this section (updated from v2.7.19 PARTIAL)
- [x] **D3** `__init__.py`: version bumped to 2.7.20

---

## OPP OBEX Timeout & Exception Handling Fix (2026-03-09) – COMPLETE

**Goal**: Fix Object Push Profile (OPP) operations failing with `connect_cb: Timed out waiting for response` against paired Classic devices (observed on SCH-U365 / `14:89:FD:31:8A:7E`), an unhandled `DBusException` in `obex_opp.py`, and a `NameError` in `classic_pbap.py`'s watchdog callback.

**Status**: Complete.  Superseded by "OPP OBEX Polishing" above which addresses remaining transfer-level failures.

### Root Cause

- [x] **R1** `obex_opp.py` calls `CreateSession(mac, {"Target": "OPP"})` without a `Channel` hint, forcing obexd to redo SDP — on older devices this redundant SDP lookup during an active RFCOMM keep-alive can stall or resolve incorrectly, causing a 20 s OBEX CONNECT timeout even though the channel is already known from `cconnect` enumeration.
- [x] **R2** `obex_opp.py` lines 123-124: `bus.get_object()` and `dbus.Interface()` after `CreateSession` are not wrapped in `try/except`, so a partially-torn-down session object raises a raw `DBusException` (`UnknownObject`) that escapes to the user instead of a clean `RuntimeError`.
- [x] **R3** `classic_pbap.py` `pbap_dump_async()`: redundant `from bleep.core.log import print_and_log` at lines 328 and 343 (inside conditional/except blocks) cause Python to mark `print_and_log` as a local variable of the enclosing function; when those branches don't execute (the common path), the `_watchdog_cb` closure gets `NameError: cannot access free variable`.

### Implementation

- [x] **I1** `bleep/dbuslayer/obex_opp.py` — Add optional `channel: int | None` parameter to `opp_send_file()` and `opp_pull_business_card()`; when provided, include `dbus.Byte(channel)` as `"Channel"` in `CreateSession` options. Wrap `bus.get_object()` + `dbus.Interface()` in `try/except DBusException`.
- [x] **I2** `bleep/ble_ops/classic_opp.py` — Thread `channel: int | None` through `send_file()` and `pull_business_card()` to the dbuslayer functions.
- [x] **I3** `bleep/modes/debug_classic_obex.py` — Extract OPP RFCOMM channel from `state.current_mapping` and pass to `send_file()`/`pull_business_card()`. Extend `_print_obex_error_hints()` to cover timeout scenarios with actionable guidance.
- [x] **I4** `bleep/ble_ops/classic_pbap.py` — Remove redundant local `from bleep.core.log import` statements at lines 328 and 343; module-level import at line 33 suffices.

### Verification

- [x] Channel passthrough confirmed: phone now prompts user to accept OPP connection (was previously timing out silently)
- [x] Exception handling confirmed: `UnknownObject` no longer escapes as raw `DBusException`
- [x] PBAP `_watchdog_cb` NameError confirmed fixed

### Documentation

- [x] **D1** `changelog.md`: v2.7.19 entry
- [x] **D2** `todo_tracker.md`: this section
- [x] **D3** `__init__.py`: version bumped to 2.7.19

---

## Audio Tools & Profile Correlator Bug Fixes (2026-03-05) – IMPLEMENTED

**Goal**: Fix 7 bugs across audio tools, profile correlator, and audio recon that prevent BLEEP from accurately enumerating Bluetooth audio cards, profiles, and interfaces.  Connected BlueZ devices visible via `pacmd list-cards` were not recognised by `audio-profiles` or fully enumerated by `audio-recon`.

### Change 1: `get_profiles_for_card()` regex excludes digits
- [x] **C1** Fix `[a-z_]+` → `[a-z0-9_]+` so profile names with digits (e.g. `a2dp_sink`) are matched
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 2: `_extract_interfaces_from_block()` pacmd parsing regex
- [x] **C2** Replace `\d+\.\s+(\S+)` with pattern matching actual pacmd format `name/#index: description`
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 3: `_extract_interfaces_from_block()` role_key derivation
- [x] **C3** Fix `section_key.rstrip("s")` producing `"source"/"sink"` instead of `"sources"/"sinks"` expected by `_role_for_interface_name()`
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 4–5: `list_audio_sinks()` / `list_audio_sources()` multi-tool enumeration
- [x] **C4** For `"pipewire"` backend, try PipeWire-native (`pw-dump`) then also `pactl` (PA compat), merging and deduplicating results
- [x] **C5** Mirror Change 4 for `list_audio_sources()`
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 6: `identify_bluetooth_profiles_from_alsa()` card-level augmentation
- [x] **C6** Supplement sink/source enumeration with `get_bluez_cards()` + `get_profiles_for_card()` to discover ALL available profiles regardless of active profile
- **File**: `bleep/ble_ops/audio_tools.py`

### Change 7: MAC comparison bug in `AudioProfileCorrelator`
- [x] **C7** Fix `mac_address.lower().replace(":", "_")` → `mac_address.lower()` at 3 locations
- **File**: `bleep/ble_ops/audio_profile_correlator.py`

### Change 8: Profile restore in `_recon_pulseaudio`
- [x] **C8a** Add `get_active_profile_for_card()` method to `AudioToolsHelper`
- [x] **C8b** Save original active profile before cycling, restore after
- **Files**: `bleep/ble_ops/audio_tools.py`, `bleep/ble_ops/audio_recon.py`

### Verification
- [x] Tested against live device `D8:3A:DD:0B:69:B9` — `audio-profiles`, `audio-profiles --device`, and `audio-recon --device` all return complete results
- [x] Profile restore confirmed: active profile `handsfree_head_unit` preserved after `audio-recon` cycling

---

## Classic Enumeration Robustness Fix (2026-03-02) – IMPLEMENTED

**Goal**: Fix `classic-enum` failing with `sdptool failed: PBAP not in browse output` on devices that don't support PBAP, and ensure SDP records are always displayed to the user even when connection-based enumeration fails.

### Root Cause
- [x] **R1** `discover_services_sdp()` required PBAP (UUID 0x112f) to be present to accept parsed SDP records — devices without PBAP caused a `RuntimeError` even when valid records were obtained
- [x] **R2** `classic-enum` CLI only displayed SDP records in `--debug` mode; primary output required a full connection
- [x] **R3** Connection failures (e.g. `br-connection-create-socket`) caused the command to exit with error 1, discarding already-obtained SDP data

### Implementation
- [x] **I1** Removed PBAP gate from `discover_services_sdp()` — records with RFCOMM channels are accepted immediately regardless of which services are present
- [x] **I2** Added formatted SDP record display to `classic-enum` CLI — always shown after successful SDP discovery
- [x] **I3** Connection failure fallback now returns exit 0 when SDP records were obtained, with a warning message

### Documentation
- [x] **D1** `changelog.md`: v2.7.3 entry
- [x] **D2** `todo_tracker.md`: this section
- [x] **D3** `__init__.py`: version bumped to 2.7.3
- [x] **D4** `bl_classic_mode.md`: updated output examples

---

## Debug Mode Modular Refactor (2026-03-01) – IMPLEMENTED

**Goal**: Refactor the monolithic `bleep/modes/debug.py` (3864 lines) into a modular architecture with focused submodules, centralised shared state via a `DebugState` dataclass, and a slim core shell. No behavioral changes. Guided by `workDir/Debugging/README.debug-mode-refactor`.

### Architecture
- [x] **A1** `debug_state.py` – `DebugState` dataclass replacing 16 module-level globals + GLib MainLoop management
- [x] **A2** `debug_dbus.py` – D-Bus error formatting, path resolution, navigation (ls/cd/pwd/back), introspection commands (interfaces/props/methods/signals/call/monitor/introspect)
- [x] **A3** `debug_connect.py` – Transport detection, connect/disconnect/info with Classic and BLE branches
- [x] **A4** `debug_gatt.py` – GATT operations (services/chars/char/read/write/notify/detailed), property display, notification callback factory
- [x] **A5** `debug_classic.py` – Classic BT commands (cscan/cconnect/cservices/ckeep/csdp/pbap)
- [x] **A6** `debug_pairing.py` – Agent and pair commands, single/brute-force/post-pair connect flows
- [x] **A7** `debug_scan.py` – Scan variants (scan/scann/scanp/scanb) and enumeration (enum/enumn/enump/enumb)
- [x] **A8** `debug_aoi.py` – AOI analysis and database commands (aoi/dbsave/dbexport)
- [x] **A9** `debug_multiread.py` – Updated to accept `DebugState` instead of 7 individual parameters
- [x] **A10** `debug.py` – Slim core shell (~270 lines): imports, help, dispatch table factory, shell loop, CLI entry point

### Documentation
- [x] **D1** `changelog.md`: v2.7.2 entry with full change list
- [x] **D2** `todo_tracker.md`: this section
- [x] **D3** `__init__.py`: version bumped to 2.7.2

---

## Lockout-Aware Brute-Force (2026-03-01) – IMPLEMENTED

**Goal**: Fix brute-force PIN discovery failing on devices that implement pairing lockout after consecutive wrong PINs.  The brute forcer was treating `AuthenticationRejected` (lockout) the same as `AuthenticationFailed` (wrong PIN), causing it to skip the correct PIN during a lockout window.

### Root Cause Analysis
- [x] **A1** Identified two distinct D-Bus errors: `AuthenticationFailed` = device tested and rejected the PIN; `AuthenticationRejected` = device refusing to evaluate the PIN (lockout active)
- [x] **A2** Confirmed target device (DingoMan) transitions from `AuthenticationFailed` to `AuthenticationRejected` after ~3 consecutive failures, even when the correct PIN is subsequently provided

### Implementation
- [x] **I1** `PairingAgent.last_pair_error`: new attribute storing the D-Bus error name from the most recent `pair_device()` failure
- [x] **I2** `PinBruteForcer` error reclassification: split `_REJECTION_ERRORS` into `_WRONG_PIN_ERRORS`, `_LOCKOUT_ERRORS`, `_RETRY_ERRORS`, `_BLOCKING_ERRORS`
- [x] **I3** Lockout detection: track `AuthenticationFailed` → `AuthenticationRejected` transition as lockout signal
- [x] **I4** Cooldown + retry: pause for `lockout_cooldown` seconds (default 60), then retry the rejected candidate
- [x] **I5** Max lockout retries: abort after `max_lockout_retries` (default 3) consecutive cooldown cycles per candidate
- [x] **I6** `_interruptible_sleep()`: sleep in 1s increments, checking `_stop_requested` for graceful interrupt during cooldown
- [x] **I7** `--lockout-cooldown` and `--max-lockout-retries` CLI arguments added to `pair --brute`
- [x] **I8** `BruteForceResult.lockout_pauses`: tracks number of lockout cooldown pauses in results

### Documentation
- [x] **D1** `changelog.md`: updated v2.7.1 entry with lockout-aware features
- [x] **D2** `todo_tracker.md`: this section
- [x] **D3** `pairing_agent.md`: updated with lockout-aware brute-force details
- [x] **D4** `debug_mode.md`: updated brute-force options documentation

---

## Pair-Connect-Explore: Persistent Connections After Pairing (2026-03-01) – IMPLEMENTED

**Goal**: Restructure the debug-mode `pair` command so that successful pairing results in a persistent connection and return to the debug shell, enabling immediate device exploration.  Enhance `connect` to auto-detect transport, and `info` to work with paired-but-disconnected devices.

### Planning
- [x] **P1** Root-cause analysis of 9-10s post-pair ACL disconnect (kernel HCI idle timeout)
- [x] **P2** Plan for pair restructure: operational mode (default) + `--test` PoC mode
- [x] **P3** Plan for smart `connect` command with transport auto-detection
- [x] **P4** Plan for `info` enhancement with D-Bus path fallback

### Implementation
- [x] **I1** `_get_device_transport()`: transport detection from D-Bus `Device1` properties
- [x] **I2** `_post_pair_connect()` / `_post_pair_connect_classic()` / `_post_pair_connect_le()`: post-pair connection helpers
- [x] **I3** `pair` command restructure: `--test` flag, default operational mode with `_post_pair_connect()`
- [x] **I4** Smart `connect` command: `_connect_le()` / `_connect_classic()` with fallback
- [x] **I5** Enhanced `info` command: `_info_from_dbus_path()` for paired-but-disconnected devices
- [x] **I6** Enhanced `disconnect` command: keepalive socket cleanup and full state reset

### Documentation
- [x] **D1** `debug_mode.md`: updated pair and connect command documentation
- [x] **D2** `pairing_agent.md`: updated to v2.7.1, new features listed
- [x] **D3** `changelog.md`: v2.7.1 entry
- [x] **D4** `todo_tracker.md`: this section
- [x] **D5** Version bump to 2.7.1

### Future Work (from this effort)
- [ ] **F1** Profile-level connect retry: attempt `ConnectProfile()` for individual UUIDs after `Connect()` fails
- [ ] **F2** Keepalive socket auto-recovery: detect dropped sockets and re-open
- [ ] **F3** MainLoop inversion (from v2.7.0 planning): eliminate stop/restart cycle for concurrent agent + shell

---

## Pairing Agent Expansion: Three Modes + Brute-Force + Passkey (2026-03-01) – IMPLEMENTED

**Goal**: Expand the debug-mode pairing PoC from hardcoded-PIN-only to three modes of operation (hardcoded, interactive, brute-force), add passkey support for LE devices, and document the MainLoop inversion architecture for future adoption.

### Planning & Investigation
- [x] **P1** Expert-level review of BLEEP codebase (all modules, modes, D-Bus layer)
- [x] **P2** BlueZ reference analysis: Agent1 API, `simple-agent`, `bt-agent`, PinCode vs PassKey
- [x] **P3** GLib MainLoop compatibility assessment across all BLEEP modes
- [x] **P4** Option A vs Option B analysis for MainLoop inversion
- [x] **P5** Plan presented and approved

### Implementation
- [x] **I1** `BruteForceIOHandler` added to `bleep/dbuslayer/agent_io.py`
- [x] **I2** `PinBruteForcer` orchestrator created at `bleep/dbuslayer/pin_brute.py`
- [x] **I3** `_cmd_pair` expanded to three modes in `bleep/modes/debug.py`
- [x] **I4** Shared helpers extracted: `_find_device_path`, `_remove_stale_bond`, `_resolve_device_for_pair`, `_register_pair_agent`, `_post_pair_monitor`
- [x] **I5** `agent status` enhanced with PIN/passkey display and invocation history
- [x] **I6** `mainloop_architecture.md` design document created

### Documentation
- [x] **D1** `pairing_agent.md` updated with three modes, brute-force, passkey, new status
- [x] **D2** `debug_mode.md` updated with expanded `pair` command reference
- [x] **D3** `changelog.md` v2.7.0 entry added
- [x] **D4** `todo_tracker.md` this section added

### Future Work (from this effort)
- [ ] **F1** MainLoop inversion (Option A): move GLib MainLoop to main thread, `input()` to worker thread
- [ ] **F2** Test `RequestPasskey` against real LE hardware
- [x] **F3** Brute-force response analysis: classify D-Bus errors to detect device lockout patterns (implemented in v2.7.1)
- [ ] **F4** PIN persistence: store discovered PINs in observations database

---

## Debug Mode Pairing: Full Fix (2026-02-28) – CONFIRMED WORKING

**Goal**: Fix `RequestPinCode` (and all `org.bluez.Agent1` method) handlers never firing during debug-mode pairing despite D-Bus METHOD CALLs arriving at the BLEEP process.

**Result**: BLEEP successfully pairs with target `D8:3A:DD:0B:69:B9` using PIN `12345`.  `RequestPinCode` handler fires, `AutoAcceptIOHandler` returns the configured PIN, BlueZ accepts the pairing, and the device is set as trusted.

### Investigation & Diagnosis
- [x] **D1** Confirmed D-Bus METHOD CALL routing: message filters see `RequestPinCode` arriving at BLEEP's bus unique name
- [x] **D2** Confirmed `DBusGMainLoop(set_as_default=True)` is called before first `dbus.SystemBus()` creation (in `bleep/core/config.py`)
- [x] **D3** Confirmed agent methods are registered in `dbus-python`'s class table (decorated with `@dbus.service.method`)
- [x] **D4** Confirmed message filters return `None` (`NOT_YET_HANDLED`), not consuming messages
- [x] **D5** Identified architectural difference: working `simple-agent` runs mainloop on main thread; BLEEP debug runs on background thread
- [x] **D6** Baseline test: `simple-agent` successfully pairs with target `D8:3A:DD:0B:69:B9` using PIN `12345`
- [x] **D7** Diagnostic PoC (`poc_pair_diag.py`) proved `sudo` is NOT required for handler dispatch
- [x] **D8** Diagnostic PoC proved `eavesdrop='true'` match rules fail with `AccessDenied` for non-root — never active in BLEEP
- [x] **D9** Narrowed root cause to generic message filter installed by `enable_unified_dbus_monitoring()`

### Root Cause (refined through 5 phases)
- [x] **RC1** Background-thread `MainLoop.run()` does not dispatch `dbus.service.Object` handlers (only message filters)
- [x] **RC2** `GLib.MainContext.iteration(False)` on the main thread ALSO does not dispatch object-path handlers — only message filters
- [x] **RC3** Only `GLib.MainLoop().run()` drives the full `libdbus` dispatch chain including object-path → `dbus.service.Object._message_cb()` → Python method handler
- [x] **RC4** `bus.add_message_filter()` installed by `enable_unified_dbus_monitoring()` interferes with `dbus-python` handler dispatch even though the filter returns `None`
- [x] **RC5** `_cmd_pair()` fabricated fake D-Bus paths from MAC addresses when device not in BlueZ tree, causing `UnknownObject` error — should use `GetManagedObjects()` like `bluezutils.find_device()`

### Fix (Phase 1 — debug.py)
- [x] **F1** In `_cmd_pair()`: replace `_ensure_glib_mainloop()` with `_stop_glib_mainloop()` before agent creation/pairing
- [x] **F2** In `_cmd_pair()`: add `_ensure_glib_mainloop()` after `pair_device()` returns to restart background loop
- [x] **Files Modified**: `bleep/modes/debug.py` (2-line change in `_cmd_pair()`)

### Fix (Phase 2 — PoC + agent.py)
- [x] **F3** PoC standalone script confirmed temporary `GLib.MainLoop` + `timeout_add` approach works — `RequestPinCode` fires, pairing succeeds
- [x] **F4** In `pair_device()`: replaced `context.iteration(False)` loop with temporary `GLib.MainLoop` + `GLib.timeout_add(100, poll)` pattern
- [x] **Files Modified**: `bleep/dbuslayer/agent.py` (non-background path in `pair_device()`)

### Fix (Phase 4 — Message filter interference)
- [x] **F5** Disabled `enable_unified_dbus_monitoring(True)` during agent registration in `ensure_default_pairing_agent()`
- [x] **F6** Only `register_agent()` is called for correlation tracking — monitoring can be re-enabled after pairing completes
- [x] **Files Modified**: `bleep/dbuslayer/agent.py` (`ensure_default_pairing_agent()`)

### Fix (Phase 5 — Device discovery + bond storage)
- [x] **F7** Replaced `get_discovered_devices()` cache lookup + path fabrication with `GetManagedObjects()` query matching `bluezutils.find_device()` pattern
- [x] **F8** Added `Transport: "auto"` filter and 15s discovery scan for both BLE and BR/EDR classic devices
- [x] **F9** Clear error message on discovery failure instead of fabricating phantom D-Bus paths
- [x] **F10** Fixed `RemoveDevice` re-discovery: proper 15s scan with `Transport: "auto"` and `GetManagedObjects()` re-resolve
- [x] **F11** Fixed `PairingStateMachine.start_pairing()` to extract MAC address from `device_path` and include it in `_pairing_data`
- [x] **Files Modified**: `bleep/modes/debug.py` (`_cmd_pair()`), `bleep/dbuslayer/pairing_state.py` (`start_pairing()`)

### Documentation
- [x] **DOC1** Updated `bleep/docs/agent_dbus_communication_issue.md` — All phases through Phase 5
- [x] **DOC2** Updated `bleep/docs/mainloop_requirement_analysis.md` — message filter interference discovery
- [x] **DOC3** Updated `bleep/docs/debug_mode.md` — updated `pair` command docs with discovery scan details
- [x] **DOC4** Changelog entry v2.6.1 + v2.6.2 in `bleep/docs/changelog.md`
- [x] **DOC5** TODO tracker section (this section)

### Fix (Phase 6 — Bond storage + state machine resilience)
- [x] **F12** Fixed `PairingStateMachine.start_pairing()` to extract MAC address from `device_path` and include `"address"` in `_pairing_data` — resolves `Bond info must include device address` ValueError
- [x] **F13** Added `_safe_transition_failed()` guard in `pair_device()` — prevents `InvalidTransitionError` when error handler tries to transition from a terminal state (COMPLETE/FAILED/CANCELLED) to FAILED
- [x] **Files Modified**: `bleep/dbuslayer/pairing_state.py`, `bleep/dbuslayer/agent.py`

### Final Confirmation (2026-02-28)
- [x] **V1** Full end-to-end pairing verified: `pair D8:3A:DD:0B:69:B9 --pin 12345` — `RequestPinCode` fires, PIN returned, `Pair()` succeeds, device trusted, bond stored, `pair_device()` returns `True`
- [x] **V2** Stale bond removal + re-pair verified: `RemoveDevice()` + 15s re-scan + re-pair — works correctly
- [x] **V3** Post-pair disconnect monitoring verified: detects target's auto-disconnect after 9s

### Pairing: Future Work
- [ ] **FW1** Re-enable unified D-Bus monitoring after `pair_device()` returns (currently disabled for entire agent lifetime)
- [ ] **FW2** Test remaining Agent1 methods (`RequestPasskey`, `RequestConfirmation`, `DisplayPasskey`, `RequestAuthorization`, `AuthorizeService`) against real devices
- [ ] **FW3** PIN code persistence — store known PINs in observations database for automatic reuse
- [ ] **FW4** Pairing retry logic with exponential backoff for transient failures
- [ ] **FW5** Investigate `dbus-python` message filter interference — determine if bug or architectural limitation
- [ ] **FW6** Multi-adapter support — support selecting adapter other than `hci0`
  *(partial, 2026-09-03: `--adapter` now reaches pair / classic-connect / aoi /
  gatt-enum / explore / enum-scan Device1 construction — see Phase 4c. Remaining:
  Agent1 is still process-global; some Classic helpers and debug-connect still
  assume the default controller.)*
- [x] **FW7** ~~Fix DB FOREIGN KEY errors in `bleep/core/observations/_evidence.py:store_device_type_evidence` during scan~~ — **CLOSED** (2026-05-22, PREP-7A): The A2 fix (`_ensure_device_exists` inside `store_device_type_evidence`) was confirmed working by `test_evidence_auto_creates_device_row` — evidence storage auto-creates the parent device row in the same transaction.  Invalid MACs are correctly rejected by `_normalize_mac` with no FK error.

---

## Amusica: Bluetooth Audio Target Discovery & Manipulation (2026-02-28) – Completed (Core)

**Goal**: Automated discovery, JustWorks connection assessment, audio reconnaissance, and audio manipulation of Bluetooth audio devices.  Compose existing BLEEP primitives (scan, connect, audio_recon, audio_tools, media control) into an end-to-end workflow.

### Phase 1: Constants & Audio Service UUID Filter
- [x] **1.1** Add `AVRCP_TARGET_UUID`, `AVRCP_CONTROLLER_UUID` to `bt_ref/constants.py`
- [x] **1.2** Add `AUDIO_SERVICE_UUIDS` frozenset aggregating A2DP, HFP, HSP, AVRCP UUIDs
- [x] **Files Modified**: `bleep/bt_ref/constants.py` (+15 lines)

### Phase 2: Audio Halt Capability
- [x] **2.1** Add `AudioToolsHelper.halt_audio_for_device()` — multi-step disruption: AVRCP pause → volume 0 → profile "off"
- [x] **Files Modified**: `bleep/ble_ops/audio_tools.py` (+60 lines)

### Phase 3: Core Orchestration Engine
- [x] **3.1** `scan_audio_targets()` — UUID-filtered scan using adapter discovery + post-filter
- [x] **3.2** `attempt_justworks_connect()` — connect-only (no pair) with auth/reject classification
- [x] **3.3** `assess_targets()` — pipeline: connect each target, run audio_recon on accessible ones
- [x] **3.4** `summarise_assessment()` — structured report of vulnerable targets
- [x] **Files Added**: `bleep/ble_ops/amusica.py` (~240 lines)

### Phase 4: CLI Mode
- [x] **4.1** `scan` subcommand — scan with optional `--connect` for full assessment
- [x] **4.2** `halt` subcommand — halt all audio on a connected target
- [x] **4.3** `control` subcommand — proxy to existing media control (play/pause/stop/next/prev/volume/info)
- [x] **4.4** `inject` subcommand — play audio file into target's sink
- [x] **4.5** `record` subcommand — record from target's source with sox analysis
- [x] **4.6** `status` subcommand — show card, profiles, sources, sinks, playback state
- [x] **Files Added**: `bleep/modes/amusica.py` (~290 lines)

### Phase 5: CLI & Mode Registration
- [x] **5.1** Add `amusica` subparser to `cli.py` with REMAINDER args
- [x] **5.2** Add dispatch in `cli.py` `main()` routing to `bleep.modes.amusica.main()`
- [x] **5.3** Add lazy import to `modes/__init__.py`
- [x] **Files Modified**: `bleep/cli.py` (+10 lines), `bleep/modes/__init__.py` (+2 lines)

### Phase 6: Documentation
- [x] **6.1** Changelog entry v2.6.0 in `bleep/docs/changelog.md`
- [x] **6.2** TODO tracker section (this section)
- [x] **6.3** Cross-reference in `bleep/docs/audio_recon.md`

### Future Work — Amusica Advanced Capabilities

The following items are **not implemented** in the core release and are documented here for future expansion.  They build on the Amusica core and the existing audio recon bonus objectives documented in `bleep/docs/audio_recon.md`.

#### FW-A1: ALSA Configuration File Customization
- [ ] Support runtime generation/modification of `asound.conf` / `.asoundrc` for BlueALSA default device configuration
- [ ] Create loopback and dsnoop/dmix PCM entries for multi-client ALSA access
- [ ] Document required ALSA plugin packages by distro
- **Prerequisite**: User guidance on acceptable ALSA config modifications (noted in README.amusica line 63)
- **Location**: `bleep/ble_ops/audio_tools.py` — new `configure_alsa_device()` method

#### FW-A2: Audio Feedback Loop Injection
- [ ] Capture audio from a target device's microphone and feed it back into the device's speaker stream in real-time
- [ ] Requires PulseAudio/PipeWire loopback module (`module-loopback`) or ALSA loopback device
- [ ] Implementation: Create a loopback from the target's microphone source to the target's speaker sink
- **Builds on**: Audio recon Bonus Objective 3 (play into existing streams) and Bonus Objective 1 (duplicate playback)
- **Location**: `bleep/ble_ops/amusica.py` — new `create_feedback_loop()` function

#### FW-A3: Full Audio Stream Consolidation
- [ ] Record headset speakers + microphone into a single mixed audio file (e.g. full call capture)
- [ ] Requires creating a PulseAudio null sink, routing multiple sources via `module-loopback`, and recording from the null sink's monitor
- [ ] Alternative: post-capture mix using `sox -m mic.wav spk.wav mixed.wav`
- **Builds on**: Audio recon Bonus Objective 2 (consolidate streams)
- **Location**: `bleep/ble_ops/audio_tools.py` — new `consolidate_recordings()` method or separate `audio_mix.py`

#### FW-A4: Dummy/Virtual Audio Interface Creation
- [ ] Create virtual PulseAudio/PipeWire sinks and sources for routing control
- [ ] Use `pactl load-module module-null-sink` or PipeWire equivalent to create programmable endpoints
- [ ] Feed recorded audio into virtual source so applications see it as "microphone"
- **Builds on**: Audio recon Bonus Objective 4 (reconfigure I/O)
- **Location**: `bleep/ble_ops/audio_tools.py` — new `create_virtual_device()` and `destroy_virtual_device()` methods

#### FW-A5: Profile-Based Audio Denial via ALSA
- [ ] Systematically cycle through all card profiles to find one that disrupts audio most effectively per device type
- [ ] Map profile → disruption effectiveness for common device types (headsets, speakers, car kits)
- [ ] Extend `halt_audio_for_device()` with profile cycling strategy
- **Location**: `bleep/ble_ops/audio_tools.py` — extend `halt_audio_for_device()`

#### FW-A6: Amusica Observation DB Persistence
- [ ] Store Amusica assessment results (scan, connection, recon) in the BLEEP observation database
- [ ] New table `amusica_assessments` with columns: `mac`, `timestamp`, `justworks_ok`, `audio_interfaces`, `result_json`
- [ ] Query via `bleep db` for historical vulnerability tracking
- **Builds on**: Audio recon Bonus Objective 5 (persist recon in DB)
- **Location**: `bleep/core/observations.py` — schema v8 migration + `store_amusica_result()` function

#### FW-A7: Terminal UI for Amusica
- [ ] Interactive terminal-based interface for real-time audio control of multiple targets
- [ ] Live display of connected devices, audio state, recording status
- [ ] Keyboard shortcuts for halt/play/record/inject operations
- **Note**: Per README.amusica line 101 — "a terminal-based interface for users is within acceptable parameters"
- **Location**: `bleep/modes/amusica.py` — new `_cmd_tui()` subcommand

#### FW-A8: Targeted Scan with Connection-Less UUID Discovery
- [ ] Use advertisement data parsing to identify audio UUIDs without requiring a connection
- [ ] Leverage `ServiceData` and `ManufacturerData` from BLE advertisements for passive audio device identification
- [ ] Reduce scan time by avoiding connection attempts for devices that can be classified from advertisements alone
- **Location**: `bleep/ble_ops/amusica.py` — enhance `scan_audio_targets()` with advertisement parsing

---

## Adapter Configuration & Bluetooth Configurability (2026-02-28) – Completed

**Goal**: Expose local Bluetooth adapter configuration (Name, Alias, Class, Discoverable, Pairable, security toggles) through BLEEP using the lowest-level tools available, with a tiered approach: D-Bus native → `bluetoothctl mgmt.*` → `main.conf` inspection.

### Phase 1: D-Bus Property Accessors
- [x] **1.1** Add `get_adapter_info()` — returns all adapter properties as native Python dict via `Properties.GetAll()`
- [x] **1.2** Add individual getters: `get_alias()`, `get_name()`, `get_address()`, `get_address_type()`, `get_class()`, `get_powered()`, `get_discoverable()`, `get_pairable()`, `get_connectable()`, `get_discoverable_timeout()`, `get_pairable_timeout()`, `get_discovering()`, `get_uuids()`, `get_modalias()`, `get_roles()`
- [x] **1.3** Add DRY helpers: `_get_property()` and `_set_property()` base methods
- [x] **1.4** Add individual setters: `set_alias()`, `set_powered()`, `set_discoverable()`, `set_pairable()`, `set_connectable()`, `set_discoverable_timeout()`, `set_pairable_timeout()`
- [x] **Files Modified**: `bleep/dbuslayer/adapter.py` (+~130 lines)

### Phase 2: bluetoothctl Management Socket Integration
- [x] **2.1** Implement `_run_bluetoothctl_mgmt()` — stdin-based multi-command subprocess wrapper for `bluetoothctl`
- [x] **2.2** Implement `_mgmt_index()` and `_mgmt_cmd()` — auto-prepend `mgmt.select <index>` for adapter selection
- [x] **2.3** Add mgmt setters: `set_class()`, `set_local_name()`, `set_ssp()`, `set_secure_connections()`, `set_le()`, `set_bredr()`, `set_privacy()`, `set_fast_connectable()`, `set_link_security()`, `set_wideband_speech()`
- [x] **Files Modified**: `bleep/dbuslayer/adapter.py` (+~120 lines)

### Phase 3: CLI Command
- [x] **3.1** Add `adapter-config` subparser with `show`, `get`, `set` sub-actions to `bleep/cli.py`
- [x] **3.2** Create `bleep/modes/adapter_config.py` with property routing (D-Bus writable → native, mgmt-only → subprocess)
- [x] **3.3** Implement `show` action: all D-Bus properties + writable property listing + `/etc/bluetooth/main.conf` boot defaults
- [x] **3.4** Implement `get` action: single property lookup with Class of Device pretty-printer
- [x] **3.5** Implement `set` action: automatic routing to D-Bus or mgmt based on property type
- [x] **Files Added**: `bleep/modes/adapter_config.py` (~325 lines)
- [x] **Files Modified**: `bleep/cli.py` (+18 lines)

### Phase 4: Boot Defaults Reader
- [x] **4.1** Implement `read_main_conf()` to parse `/etc/bluetooth/main.conf` (read-only, informational)
- [x] **4.2** Integrate into `adapter-config show` output

### Phase 5: Documentation
- [x] **5.1** Create `bleep/docs/adapter_config.md` with CLI reference, property tables, CoD values, Python API, architecture notes

### BlueZ Source Analysis (Reference)
- Examined `workDir/bluez/src/adapter.c` (adapter implementation, D-Bus property handlers)
- Examined `workDir/bluez/src/main.conf` (all configuration options with defaults)
- Examined `workDir/bluez/doc/org.bluez.Adapter.rst` (D-Bus API specification)
- Examined `workDir/bluez/client/main.c` (`bluetoothctl` main menu: `system-alias`, `set-alias`, `show`, `power`, `pairable`, `discoverable`)
- Examined `workDir/bluez/client/mgmt.c` (`bluetoothctl mgmt` submenu: `class`, `name`, `ssp`, `sc`, `le`, `bredr`, `privacy`)
- Confirmed: `bluetoothctl` main menu commands are D-Bus wrappers (no advantage over native D-Bus calls); mgmt submenu commands access the kernel management socket (not reachable via D-Bus)

---

## Audio Recon Augmentation (2026-02-28) – Completed

**Goal**: Incorporate audio reconnaissance capabilities into BLEEP while retaining the modular structure.

- [x] Sox-based analysis: `check_audio_file_has_content()` in `audio_tools.py` and preflight `sox` check
- [x] Per-profile enumeration: `get_bluez_cards()`, `get_profiles_for_card()`, `set_card_profile()`, `get_sources_and_sinks_for_card_profile()` with role mapping (microphone, headset_stream, speaker, interest)
- [x] Play/record via backend: `play_to_sink()`, `record_from_source()` (paplay/parecord or aplay/arecord)
- [x] Recon runner: `bleep/ble_ops/audio_recon.py` – `run_audio_recon()` with optional play, record, sox analysis, JSON out
- [x] CLI: `bleep audio-recon` and `bleep audio recon` with `--device`, `--test-file`, `--no-play`, `--no-record`, `--out`, `--record-dir`, `--duration`
- [x] Preflight: added `sox`, `paplay`, `pacmd` to audio tools
- [x] Documentation: `bleep/docs/audio_recon.md` with usage, result structure, and **detailed Future work** for Bonus Objectives

**Future work (Bonus Objectives)** is documented in **`bleep/docs/audio_recon.md`** (stream redirection, consolidate streams, play into streams, reconfig I/O, persist in observation DB). No duplicate tracking here – see that file for expansion steps.

---

## BlueALSA and PipeWire Tool Support (Completed)

> **Status**: Completed  
> **Created**: 2026-02-28  
> **Completed**: 2026-02-28  

### Background

BLEEP audio recon currently supports PulseAudio (`pactl`, `pacmd`, `paplay`, `parecord`) and basic ALSA utilities (`aplay`, `arecord`). Two additional tool families are known from real-world research but are not yet fully integrated:

1. **BlueZ ALSA (BlueALSA)** – a standalone ALSA back-end for BlueZ that exposes Bluetooth audio devices directly as ALSA PCM devices without requiring PulseAudio or PipeWire. This provides a simple, low-level interface for interacting with any Bluetooth audio device via standard ALSA utilities and `asound.conf`.
2. **PipeWire native tools** – while the current backend detection recognises PipeWire (via `pw-cli info`), per-profile enumeration and card manipulation still rely on the PulseAudio compatibility layer (`pactl`, `pacmd`). Native PipeWire tools (`pw-cli`, `pw-dump`, `pw-record`, `pw-play`, `wpctl`) may expose more information or behave differently on systems without the PulseAudio compatibility layer.

### Limitations (current state)

| Area | Current support | Gap |
|------|----------------|-----|
| **BlueALSA** | Not detected or used | No preflight check for `bluealsa-aplay`, `bluealsa-cli`, or BlueALSA PCM devices; no `asound.conf` integration |
| **PipeWire native** | Backend detected via `pw-cli info`; sinks/sources listed via `pw-cli list-objects` | Per-profile enumeration, card profile switching, and sources/sinks parsing all fall through to PulseAudio compat tools (`pactl`, `pacmd`); native `pw-dump` / `wpctl` not used |

### Plan

#### Phase A: BlueALSA support

- [x] **A-1**: Add preflight checks for BlueALSA tools: `bluealsa-aplay`, `bluealsa-cli`, `bluealsa-rfcomm` in `bleep/core/preflight.py`
- [x] **A-2**: In `AudioToolsHelper`, detect whether BlueALSA is running (`is_bluealsa_running()` via `bluealsa-cli list-pcms`)
- [x] **A-3**: Implement `list_bluealsa_pcms()` -- parse `bluealsa-cli list-pcms` output to enumerate Bluetooth ALSA PCM devices with MAC, profile, and direction (playback/capture)
- [x] **A-4**: Implement `play_to_bluealsa_pcm(pcm_id, file_path, duration_sec)` using `aplay -D <pcm>` and `record_from_bluealsa_pcm(pcm_id, output_path, duration_sec)` using `arecord -D <pcm>`
- [x] **A-5**: Wire BlueALSA path into `run_audio_recon()` as an alternative when PulseAudio/PipeWire are unavailable or when BlueALSA PCMs are detected alongside them
- [x] **A-6**: Document BlueALSA integration in `bleep/docs/audio_recon.md` (prerequisites, `asound.conf` considerations, limitations vs PulseAudio/PipeWire)

#### Phase B: PipeWire native tool support

- [x] **B-1**: Add preflight checks for PipeWire native tools: `pw-dump`, `pw-play`, `pw-record`, `wpctl` in `bleep/core/preflight.py`
- [x] **B-2**: Implement `_get_pipewire_bluez_nodes()` using `pw-dump` (JSON output) to enumerate Bluetooth nodes, their profiles, and audio routes without relying on PulseAudio compat
- [x] **B-3**: Implement `_set_pipewire_profile(node_id, profile_index)` using `wpctl set-profile`
- [x] **B-4**: Implement play/record paths using `pw-play` and `pw-record` as alternatives to `paplay`/`parecord`
- [x] **B-5**: In `get_audio_backend()`, differentiate `"pipewire_native"` (no PA compat) from `"pipewire"` (PA compat available) to select the correct tool path in recon
- [x] **B-6**: Update `run_audio_recon()` to use native PipeWire enumeration when PA compat tools are absent
- [x] **B-7**: Document PipeWire native support in `bleep/docs/audio_recon.md`

### Notes

- BLEEP's preferred approach is to use the lowest-level tools available (ALSA utilities); BlueALSA is an acceptable bridge between Bluetooth and ALSA. Higher-level servers (PulseAudio, PipeWire) are also supported because they provide richer visibility in many scenarios.
- Different tools yield different levels of visibility (e.g. BlueALSA exposes per-profile PCM devices directly; PulseAudio exposes cards with switchable profiles and sources/sinks; PipeWire native dumps expose the full graph as JSON). BLEEP should leverage whatever is available and document any visibility differences.

---

## BLEEP v2.5.0 Restructuring (Active)

> **Status**: Implementation Complete - Ready for Testing  
> **Created**: 2026-01-19  
> **Completed**: 2026-01-19  
> **Goal**: Address known issues and implement targeted improvements with minimal code duplication

### Background & Objectives

This restructuring addresses the following known issues:
1. **Device Type Identification** - Flawed distinction between Classic/LE/Dual devices
2. **Connectivity Issues** - Repeated connection attempts even when already connected; fickle BR/EDR connectivity
3. **Bluetooth Agent** - Skeleton implemented but method calls not producing operational logs
4. **Verbosity Control** - Overly verbose terminal output; capability to minimize verbosity appears un-implemented

### Evidence-Based Analysis Summary

**Critical Finding**: Extensive investigation revealed that most proposed functionality already exists in the codebase. The restructuring must leverage existing components rather than duplicate them.

| Component | Status | Location | Evidence |
|-----------|--------|----------|----------|
| Connection State Machine | **EXISTS** | `dbuslayer/device_le.py:111-513` | `_connection_state`, `_connection_state_lock`, `get_connection_state()` |
| Pairing State Machine | **EXISTS** | `dbuslayer/pairing_state.py` | Full `PairingStateMachine` class (539 lines) |
| Error/Metrics Tracking | **EXISTS** | `core/metrics.py:120-222` | `ErrorTracker`, `LatencyTracker`, `DBusMetricsCollector` |
| Landmine/Annotation Mapping | **EXISTS** | `dbuslayer/device_le.py:85-94, 1100-1500` | `_landmine_map`, `record_landmine()`, `update_mine_mapping()`, `get_landmine_report()` |
| Retry Logic | **EXISTS** | `core/utils.py:95-134` | `@retry_operation(max_attempts=3, delay=1.0)` decorator |
| Reconnection Monitor | **EXISTS** | `ble_ops/reconnect.py:27-285` | `ReconnectionMonitor` class with `max_attempts`, backoff, callbacks |
| Recovery Manager | **EXISTS** | `dbuslayer/recovery.py:34-476` | `ConnectionResetManager` with staged recovery, `DeviceStateTracker` |
| Verbosity Control | **EXISTS** | Multiple files | `--verbose`, `--debug`, `--quiet` flags; `agent_io.py:448` `self.verbose` |
| Tool Availability Checks | **SCATTERED** | `classic_sdp.py:222`, `classic_ping.py:14`, `classic_version.py:81` | `shutil.which()` calls for individual tools |
| Network Capability Script | **EXISTS** | `scripts/check_network_capabilities.py` | Full script (277 lines) for BlueZ network checks |
| Audio Tools | **MISSING** | N/A | No ALSA/PipeWire/PulseAudio integration exists |
| Preflight Consolidation | **NEEDED** | N/A | Checks scattered; needs single entry point |
| Enumeration Controller | **NEEDED** | N/A | Components exist; orchestration layer needed |
| Agent Verification | **NEEDED** | N/A | Agent exists; introspection verification missing |

### Implementation Plan (Minimal Approach)

#### Phase 1: Preflight Checks Consolidation
**Goal**: Create single entry point for environment capability checks

- [x] **1.1 Create `bleep/core/preflight.py`** (~100 lines)
  - [x] Import existing check patterns from `classic_sdp.py`, `classic_ping.py`, `classic_version.py`
  - [x] Add Bluetooth tool checks: `hciconfig`, `hcitool`, `bluetoothctl`, `btmgmt`, `sdptool`, `l2ping`
  - [x] Add Pulse Audio tool checks: `pactl`, `parecord`
  - [x] Add PipeWire tool checks: `pw-cli`, `pw-record`
  - [x] Add `/etc/bluetooth` config file detection
  - [x] Add BlueZ version detection (leverage `bluetoothctl --version`)
  - [x] Add Python dependency checks (`dbus`, `gi` versions)
  - [x] Create `run_preflight_checks() -> PreflightReport` function
  - [x] Create `print_preflight_summary()` for user-friendly output
  - [x] Design: Use singleton pattern to avoid repeated checks

- [x] **1.2 CLI Integration** (~10 lines in `cli.py`)
  - [x] Add `--check-env` flag to run preflight checks
  - [x] Add optional preflight on first run (store state in config)
  - [x] Log warnings for missing capabilities with actionable suggestions

**Files**: `bleep/core/preflight.py` (NEW), `bleep/cli.py` (MODIFY)

#### Phase 2: Audio Tools Helper
**Goal**: Create wrapper for ALSA/PipeWire/PulseAudio operations

- [x] **2.1 Create `bleep/ble_ops/audio_tools.py`** (~100 lines)
  - [x] Create `AudioToolsHelper` class
  - [x] Implement `get_audio_backend() -> str` ('pipewire', 'pulseaudio', 'none')
  - [x] Implement `list_audio_sinks() -> List[Dict]` (via `pactl` or `pw-cli`)
  - [x] Implement `list_audio_sources() -> List[Dict]`
  - [x] Implement `is_bluetooth_audio_available() -> bool`
  - [x] Add graceful degradation when tools unavailable
  - [x] Integration: Design for future A2DP sink/source integration

**Files**: `bleep/ble_ops/audio_tools.py` (NEW)

#### Phase 3: Connection State Guard
**Goal**: Prevent repeated connections when already connected

- [x] **3.1 Enhance `bleep/dbuslayer/device_le.py`** (~15 lines)
  - [x] Add guard in `connect()` method to check `_connection_state` before attempting connection
  - [x] Log warning if already connected: "Device {mac} already connected, skipping connect attempt"
  - [x] Return early with success if `_connection_state == "connected"` and D-Bus `Connected` property confirms
  - [x] Ensure thread-safety via existing `_connection_state_lock`

- [x] **3.2 Enhance `bleep/dbuslayer/device_classic.py`** (~10 lines)
  - [x] Add similar connection state guard for Classic devices
  - [x] Ensure parity with LE device behavior

**Files**: `bleep/dbuslayer/device_le.py` (MODIFY), `bleep/dbuslayer/device_classic.py` (MODIFY)

#### Phase 4: Agent Method Verification
**Goal**: Add introspection-based verification of agent method registration

- [x] **4.1 Enhance `bleep/dbuslayer/agent.py`** (~30 lines)
  - [x] Add `_verify_method_registration(self) -> bool` method to `BlueZAgent` class
  - [x] Use D-Bus introspection to verify methods are registered:
    ```python
    introspect_xml = dbus.Interface(
        self._bus.get_object(BLUEZ_SERVICE_NAME, self.agent_path),
        "org.freedesktop.DBus.Introspectable"
    ).Introspect()
    ```
  - [x] Check for required methods: `Release`, `AuthorizeService`, `RequestPinCode`, `RequestPasskey`, `DisplayPasskey`, `DisplayPinCode`, `RequestConfirmation`, `RequestAuthorization`, `Cancel`
  - [x] Log verification result with structured context
  - [x] Call verification after successful `register()` call

- [x] **4.2 Enhance `bleep/modes/agent.py`** (~10 lines)
  - [x] Add verification call after agent creation
  - [x] Log detailed status including introspection results
  - [x] Provide actionable warning if methods not registered

**Files**: `bleep/dbuslayer/agent.py` (MODIFY), `bleep/modes/agent.py` (MODIFY)

#### Phase 5: Enumeration Controller
**Goal**: Create orchestration layer using existing components for 3-attempt enumeration

- [x] **5.1 Create `bleep/ble_ops/enum_controller.py`** (~150 lines)
  - [x] Create `EnumerationController` class:
    ```python
    class EnumerationController:
        MAX_ATTEMPTS = 3
        def __init__(self, target_mac: str)
        def enumerate(self, mode: str = 'passive') -> EnumerationResult
    ```
  - [x] Create `EnumerationResult` dataclass:
    ```python
    @dataclass
    class EnumerationResult:
        success: bool
        data: Optional[Dict]  # Service/characteristic data
        annotations: List[Dict]  # Error annotations from landmine map
        error_summary: Optional[str]
        attempts: int
    ```
  - [x] Use existing `ReconnectionMonitor` from `ble_ops/reconnect.py`
  - [x] Use existing `ConnectionResetManager` from `dbuslayer/recovery.py`
  - [x] Use existing landmine mapping from `device_le.py`
  - [x] Implement `ErrorAction` enum:
    ```python
    class ErrorAction(Enum):
        RECONNECT = "reconnect"  # Timeout, disconnect
        ANNOTATE_AND_CONTINUE = "annotate_continue"  # Auth rejection
        GIVE_UP = "give_up"  # Agent required, repeated failures
    ```
  - [x] Implement `_handle_error(error: Exception) -> ErrorAction` method
  - [x] Implement `_should_continue() -> bool` (max 3 attempts)
  - [x] Collect annotations from each attempt for final report
  - [x] Return structured result with all annotations

- [x] **5.2 Integration with existing scan modes** (~20 lines)
  - [x] Update `ble_ops/scan.py` to optionally use `EnumerationController`
  - [x] Add `--controlled` flag to CLI for controlled enumeration mode
  - [x] Preserve backward compatibility (default behavior unchanged)

- [x] **5.3 Integration with AoI mode** (~20 lines)
  - [x] Update `modes/aoi.py` to use `EnumerationController` when iterating targets
  - [x] Collect annotations from each device for final report
  - [x] Ensure proper error handling and continuation

**Files**: `bleep/ble_ops/enum_controller.py` (NEW), `bleep/ble_ops/scan.py` (MODIFY), `bleep/modes/aoi.py` (MODIFY), `bleep/cli.py` (MODIFY)

#### ⚠️ Future Refactoring Required: Unified Connection Retry Logic

> **Status**: Deferred - Not for immediate implementation  
> **Priority**: High (for production readiness)  
> **Issue**: The current `--controlled` flag implementation adds bloat and creates a dual-path for connection attempts

**Problem Statement:**
The `--controlled` flag in `enum-scan` creates an optional, separate code path for multi-attempt enumeration. This is unacceptable for production because:
1. **Code Duplication**: Two different methods exist for the same operation (direct `_base_enum` vs `EnumerationController`)
2. **Maintenance Burden**: Future changes must be applied to both paths
3. **User Confusion**: Users must know about and remember to use `--controlled` flag
4. **Inconsistent Behavior**: Default behavior differs from controlled behavior

**Required Solution:**
BLEEP must have **one unified method** for performing multiple connection attempts when connecting to a device. The `EnumerationController` logic should become the **default and only** method for enumeration, not an optional flag.

**Action Items (Future):**
- [ ] Remove `--controlled` flag from CLI
- [ ] Make `EnumerationController` the default implementation in `_base_enum()` and all enum variants
- [ ] Refactor `connect_and_enumerate__bluetooth__low_energy()` to use `EnumerationController` internally
- [ ] Update all call sites to use the unified method
- [ ] Remove duplicate retry logic from other modules
- [ ] Ensure backward compatibility during transition (if needed)

**Note**: This refactoring should be done as a separate task after v2.5.0 is stable. The current implementation serves as a proof-of-concept but must not remain in production.

### File Summary

| File | Action | Estimated Lines |
|------|--------|-----------------|
| `bleep/core/preflight.py` | NEW | ~100 |
| `bleep/ble_ops/audio_tools.py` | NEW | ~100 |
| `bleep/ble_ops/enum_controller.py` | NEW | ~150 |
| `bleep/dbuslayer/device_le.py` | MODIFY | ~15 |
| `bleep/dbuslayer/device_classic.py` | MODIFY | ~10 |
| `bleep/dbuslayer/agent.py` | MODIFY | ~30 |
| `bleep/modes/agent.py` | MODIFY | ~10 |
| `bleep/ble_ops/scan.py` | MODIFY | ~20 |
| `bleep/modes/aoi.py` | MODIFY | ~20 |
| `bleep/cli.py` | MODIFY | ~20 |
| **TOTAL** | | **~475 lines** |

### Success Criteria

- [ ] **SC-1**: `bleep --check-env` produces complete capability report
- [ ] **SC-2**: Connection attempts to already-connected devices log warning and return early
- [ ] **SC-3**: Agent registration includes introspection verification with logged result
- [ ] **SC-4**: AoI scans with 3+ targets produce annotations for failed devices
- [ ] **SC-5**: All existing tests pass (no regressions)
- [ ] **SC-6**: No circular imports introduced
- [ ] **SC-7**: No duplicate functionality (verified against existing code)

### Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| Connection guard could break retry logic | Maintain `connect(retry=N)` signature; guard only prevents redundant initial connect |
| EnumerationController complexity | Build on existing `ReconnectionMonitor` and `ConnectionResetManager` |
| Circular imports | Use local imports inside functions (match existing patterns) |
| Agent verification failure | Don't fail registration; log warning only |

### Testing Strategy

- [ ] **Unit tests** for new modules (`preflight.py`, `audio_tools.py`, `enum_controller.py`)
- [ ] **Integration tests** for enumeration controller with mock device
- [ ] **Regression tests** ensuring existing functionality unchanged
- [ ] **Manual tests** with real Bluetooth devices (Classic and LE)

---

## Audio Capabilities Expansion (Active)

> **Status**: In Progress  
> **Created**: 2026-01-20  
> **Goal**: Expand audio capabilities to identify Bluetooth profiles via ALSA, enable audio playback/recording, and maintain separation between external tools and D-Bus interactions

### Background & Objectives

This expansion adds comprehensive audio capabilities to BLEEP:

1. **Profile Identification via ALSA** - Correlate ALSA/PulseAudio/PipeWire devices with Bluetooth profiles (A2DP, HFP, HSP)
2. **Enhanced ALSA Enumeration** - Direct ALSA device enumeration (bypassing PulseAudio/PipeWire when needed)
3. **Audio Codec Support** - GStreamer-based encoding/decoding for Bluetooth audio streaming
4. **Transport Acquisition & Streaming** - High-level APIs for audio playback and recording
5. **Maintain Architecture** - Strict separation: `audio_tools.py` = external tools only, `dbuslayer/` = D-Bus interactions

### Architecture Principles

- **Separation of Concerns**: 
  - `bleep/ble_ops/audio_tools.py` = External tool wrappers only (pactl, pw-cli, aplay, arecord, gst-launch-1.0)
  - `bleep/dbuslayer/media*.py` = D-Bus/BlueZ direct interactions
  - New modules for orchestration and correlation

- **Code Reuse**:
  - Use existing constants from `bleep/bt_ref/constants.py` and `bleep/bt_ref/uuids.py`
  - Leverage existing `MediaTransport`, `MediaEndpoint`, `MediaService` classes
  - GStreamer pipeline patterns were derived from the BlueZ example scripts (simple-asha, simple-endpoint, example-endpoint)

- **Dependency Management**:
  - Track GStreamer dependencies in `setup.py`
  - Add preflight checks for optional audio tools

### Implementation Plan

#### Phase 1: Enhanced ALSA/PulseAudio/PipeWire Enumeration
**Goal**: Extend `audio_tools.py` with ALSA enumeration and profile identification (external tools only)

- [x] **1.1 Enhance `bleep/ble_ops/audio_tools.py`** (~150 lines)
  - [x] Add `list_alsa_devices() -> List[Dict[str, Any]]` using `aplay -l` and `arecord -l` subprocess calls
  - [x] Add `get_alsa_device_info(device_name: str) -> Dict[str, Any]` using `aplay -D <device> --dump-hw-params`
  - [x] Add `extract_mac_from_alsa_device(device_name: str) -> Optional[str]` for MAC address extraction from device names
  - [x] Add `identify_bluetooth_profiles_from_alsa(mac_address: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]` for profile identification via pattern matching
  - [x] Ensure all methods use external tools only (no D-Bus interaction)
  - [x] Use existing constants from `bleep/bt_ref/uuids.py` for profile UUIDs

**Files**: `bleep/ble_ops/audio_tools.py` (MODIFY)

#### Phase 2: Profile Correlation Helper
**Goal**: Create module that correlates external tool output with D-Bus/BlueZ information

- [x] **2.1 Create `bleep/ble_ops/audio_profile_correlator.py`** (~200 lines)
  - [x] Create `AudioProfileCorrelator` class
  - [x] Implement `identify_profiles_for_device(mac_address: str) -> Dict[str, Any]` combining:
    - ALSA/PulseAudio device enumeration (from `audio_tools.py`)
    - BlueZ MediaTransport discovery (from `dbuslayer/media.py`)
  - [x] Implement `get_transport_for_profile(mac_address: str, profile_uuid: str) -> Optional[MediaTransport]`
  - [x] Import and use existing `MediaTransport` from `dbuslayer/media.py`
  - [x] Use existing constants from `bleep/bt_ref/constants.py` and `bleep/bt_ref/uuids.py`

**Files**: `bleep/ble_ops/audio_profile_correlator.py` (NEW)

#### Phase 3: Audio Codec Support
**Goal**: Create codec encoding/decoding module using GStreamer

- [x] **3.1 Create `bleep/ble_ops/audio_codec.py`** (~300 lines)
  - [x] Create `AudioCodecEncoder` class
  - [x] Add codec constants (SBC, MP3, AAC) - reuse from `bleep/dbuslayer/media_register.py` where possible
  - [x] Implement `encode_file_to_transport(input_file: str, output_fd: int, mtu: int, codec_config: Optional[bytes] = None) -> bool`
  - [x] Support both GStreamer Python bindings (preferred) and `gst-launch-1.0` subprocess (fallback)
  - [x] GStreamer pipeline patterns derived from BlueZ example scripts (simple-asha)
  - [x] Create `AudioCodecDecoder` class for recording
  - [x] Implement `decode_audio_stream(input_fd: int, output_file: str, codec: int, mtu: int) -> bool`
  - [x] Ensure no D-Bus interaction in this module

**Files**: `bleep/ble_ops/audio_codec.py` (NEW)

#### Phase 4: Audio Streaming Manager
**Goal**: Create high-level streaming orchestration in `dbuslayer`

- [x] **4.1 Create `bleep/dbuslayer/media_stream.py`** (~250 lines)
  - [x] Create `MediaStreamManager` class
  - [x] Implement `acquire_transport() -> Tuple[int, int, int]` using existing `MediaTransport.acquire()`
  - [x] Implement `play_audio_file(audio_file: str, volume: Optional[int] = None) -> bool` orchestrating:
    - Transport acquisition (D-Bus via `MediaTransport`)
    - Volume setting (D-Bus via `MediaTransport.set_volume()`)
    - Audio encoding (delegates to `audio_codec.py`)
    - Transport release (D-Bus via `MediaTransport.release()`)
  - [x] Implement `record_audio(output_file: str, duration: Optional[int] = None) -> bool`
  - [x] Use existing `find_media_devices()` from `dbuslayer/media.py`
  - [x] Use existing `MediaTransport` class methods
  - [x] Use existing constants from `bleep/bt_ref/constants.py`

**Files**: `bleep/dbuslayer/media_stream.py` (NEW)

#### Phase 5: Dependencies and Preflight
**Goal**: Track dependencies and add preflight checks

- [x] **5.1 Update `setup.py`** (~20 lines)
  - [x] Add GStreamer Python bindings as optional dependency (via PyGObject)
  - [x] Add to `extras_require` if system-installed
  - [x] Document GStreamer plugin requirements in comments

- [x] **5.2 Update `bleep/core/preflight.py`** (~30 lines)
  - [x] Add `aplay` and `arecord` to `_check_audio_tools()`
  - [x] Add `gst-launch-1.0` check
  - [x] Add GStreamer Python bindings check (try/except import)
  - [x] Update `PreflightReport` to include new audio tools

**Files**: `setup.py` (MODIFY), `bleep/core/preflight.py` (MODIFY)

#### Phase 6: CLI Integration
**Goal**: Add CLI commands and optional mode module

- [x] **6.1 Update `bleep/cli.py`** (~50 lines)
  - [x] Add `audio-profiles` command for profile identification
  - [x] Add `audio-play` command for audio file playback
  - [x] Add `audio-record` command for audio recording
  - [x] Integrate with existing CLI argument parsing patterns

- [x] **6.2 Create `bleep/modes/audio.py`** (~200 lines)
  - [x] Create mode module following existing pattern (like `bleep/modes/media.py`)
  - [x] Implement `list_audio_profiles(mac_address: Optional[str] = None) -> None`
  - [x] Implement `play_audio_file(mac_address: str, file_path: str, **kwargs) -> bool`
  - [x] Implement `record_audio(mac_address: str, output_path: str, **kwargs) -> bool`
  - [x] Use `AudioProfileCorrelator` and `MediaStreamManager`

**Files**: `bleep/cli.py` (MODIFY), `bleep/modes/audio.py` (NEW)

### File Summary

| File | Status | Lines | Purpose |
|------|--------|-------|---------|
| `bleep/ble_ops/audio_tools.py` | MODIFY | +150 | Enhanced ALSA enumeration (external tools only) |
| `bleep/ble_ops/audio_profile_correlator.py` | NEW | ~200 | Correlate external tools + D-Bus |
| `bleep/ble_ops/audio_codec.py` | NEW | ~300 | GStreamer codec encoding/decoding |
| `bleep/dbuslayer/media_stream.py` | NEW | ~250 | High-level streaming orchestration |
| `bleep/modes/audio.py` | NEW | ~200 | CLI mode module |
| `bleep/cli.py` | MODIFY | +50 | New CLI commands |
| `setup.py` | MODIFY | +20 | Dependency tracking |
| `bleep/core/preflight.py` | MODIFY | +30 | GStreamer checks |

### Success Criteria

- [ ] **SC-1**: `audio_tools.py` remains external-tools-only (no D-Bus interaction)
- [ ] **SC-2**: Profile identification correlates ALSA devices with BlueZ profiles
- [ ] **SC-3**: ALSA enumeration works via external tools (`aplay`, `arecord`)
- [ ] **SC-4**: Transport acquisition uses existing `MediaTransport` class
- [ ] **SC-5**: Codec encoding uses GStreamer (external tool or Python bindings)
- [ ] **SC-6**: Audio playback/recording orchestrated via `media_stream.py`
- [ ] **SC-7**: All constants use existing definitions (no duplication)
- [ ] **SC-8**: Dependencies tracked in `setup.py` and `preflight.py`
- [ ] **SC-9**: Separation maintained: external tools vs D-Bus interactions
- [ ] **SC-10**: CLI commands work for common use cases

### Dependencies & Risks

**External Dependencies:**
- GStreamer 1.0+ with Python bindings (`python3-gst-1.0` or `gi.repository.Gst`)
- GStreamer plugins: `gstreamer1.0-plugins-base`, `gstreamer1.0-plugins-good`, `gstreamer1.0-plugins-bad`
- ALSA tools: `alsa-utils` (aplay, arecord) - optional

**Python Packages:**
- `PyGObject>=3.48.0` (already in setup.py) - provides GStreamer Python bindings

**Risks:**
- GStreamer availability varies by system
- Codec support depends on installed plugins
- Transport state management complexity

**Mitigation:**
- Graceful degradation if GStreamer unavailable
- Preflight checks warn about missing dependencies
- Fallback to subprocess if Python bindings unavailable

### Testing Strategy

- [ ] **Unit tests** for `audio_tools.py` ALSA enumeration methods
- [ ] **Unit tests** for `audio_profile_correlator.py` correlation logic
- [ ] **Unit tests** for `audio_codec.py` encoding/decoding (with mock GStreamer)
- [ ] **Integration tests** for `media_stream.py` with mock transports
- [ ] **End-to-end tests** with real Bluetooth devices (playback and recording)
- [ ] **Regression tests** ensuring existing functionality unchanged

---

## UUID and Codec Constants Centralization (Active)

> **Status**: Implementation Complete  
> **Created**: 2026-01-20  
> **Completed**: 2026-01-20  
> **Goal**: Centralize all UUID and codec constants in a single location to minimize hardcoded values and create a "single source of truth"

### Background & Objectives

This refactoring addresses the issue of duplicated UUID and codec constants scattered across multiple modules:

1. **Profile UUIDs** were defined in 7+ locations (constants.py, media_register.py, media_stream.py, audio_profile_correlator.py, audio_tools.py, device_classic.py, plus hardcoded values)
2. **Codec constants** were defined in 3+ locations (media_register.py, audio_codec.py, audio_profile_correlator.py)
3. **Hardcoded values** throughout the codebase increased maintenance burden and risk of inconsistencies

### Implementation Plan

#### Phase 1: Create Centralized Constants
**Goal**: Extend `bleep/bt_ref/constants.py` with audio profile UUIDs and codec constants

- [x] **1.1 Add Audio Profile UUID Constants** (~30 lines)
  - [x] Add A2DP_SOURCE_UUID, A2DP_SINK_UUID
  - [x] Add HFP_HANDS_FREE_UUID, HFP_AUDIO_GATEWAY_UUID
  - [x] Add HSP_AUDIO_GATEWAY_UUID, HSP_HEADSET_UUID
  - [x] Add AUDIO_PROFILE_NAMES dictionary mapping UUIDs to human-readable names
  - [x] Add get_profile_name() helper function

- [x] **1.2 Add Audio Codec Constants** (~30 lines)
  - [x] Add SBC_CODEC_ID, MP3_CODEC_ID, AAC_CODEC_ID, etc.
  - [x] Add CODEC_NAMES dictionary mapping codec IDs to names
  - [x] Add get_codec_name() helper function
  - [x] Document references (A2DP Specification, BlueZ documentation)

**Files**: `bleep/bt_ref/constants.py` (MODIFY)

#### Phase 2: Update All Modules to Use Centralized Constants
**Goal**: Remove duplicate definitions and update all references

- [x] **2.1 Update `bleep/dbuslayer/media_register.py`**
  - [x] Remove A2DP_SOURCE_UUID, A2DP_SINK_UUID class constants
  - [x] Remove SBC_CODEC class constant
  - [x] Import from bleep.bt_ref.constants
  - [x] Update SBC_CODEC to use SBC_CODEC_ID

- [x] **2.2 Update `bleep/dbuslayer/media_stream.py`**
  - [x] Remove A2DP_SINK_UUID, A2DP_SOURCE_UUID class constants
  - [x] Import from bleep.bt_ref.constants
  - [x] Import get_codec_name helper

- [x] **2.3 Update `bleep/ble_ops/audio_codec.py`**
  - [x] Remove SBC_CODEC, MP3_CODEC, etc. module constants
  - [x] Remove CODEC_NAMES dictionary
  - [x] Remove get_codec_name() function
  - [x] Import all from bleep.bt_ref.constants
  - [x] Add backward compatibility aliases (SBC_CODEC = SBC_CODEC_ID)
  - [x] Update all codec comparisons to use *_CODEC_ID constants

- [x] **2.4 Update `bleep/ble_ops/audio_profile_correlator.py`**
  - [x] Remove PROFILE_UUID_MAP class constant
  - [x] Remove CODEC_NAMES class constant
  - [x] Import AUDIO_PROFILE_NAMES, CODEC_NAMES, get_profile_name, get_codec_name
  - [x] Update all references to use centralized constants

- [x] **2.5 Update `bleep/ble_ops/audio_tools.py`**
  - [x] Remove profile_uuid_map local dictionary
  - [x] Import AUDIO_PROFILE_NAMES, A2DP_SINK_UUID, A2DP_SOURCE_UUID, etc.
  - [x] Update profile_patterns to use centralized UUID constants
  - [x] Replace hardcoded default UUIDs with constants
  - [x] Update profile_name lookups to use get_profile_name()

- [x] **2.6 Update `bleep/dbuslayer/device_classic.py`**
  - [x] Replace hardcoded UUID strings with constants
  - [x] Import A2DP_SINK_UUID, HFP_HANDS_FREE_UUID

**Files**: 6 files modified

#### Phase 3: Validation and Testing
**Goal**: Ensure no regressions and verify all imports work

- [x] **3.1 Code Validation**
  - [x] Run linter to check for errors
  - [x] Verify no circular imports
  - [x] Check for remaining hardcoded UUIDs/codecs

- [x] **3.2 Documentation Updates**
  - [x] Update todo_tracker.md with implementation details
  - [x] Update changelog.md with changes

**Files**: Documentation files

### File Summary

| File | Status | Lines Changed | Purpose |
|------|--------|---------------|---------|
| `bleep/bt_ref/constants.py` | MODIFY | +80 | Added centralized audio constants |
| `bleep/dbuslayer/media_register.py` | MODIFY | -3, +4 | Use centralized constants |
| `bleep/dbuslayer/media_stream.py` | MODIFY | -2, +1 | Use centralized constants |
| `bleep/ble_ops/audio_codec.py` | MODIFY | -30, +15 | Use centralized constants, add aliases |
| `bleep/ble_ops/audio_profile_correlator.py` | MODIFY | -20, +1 | Use centralized constants |
| `bleep/ble_ops/audio_tools.py` | MODIFY | -15, +10 | Use centralized constants |
| `bleep/dbuslayer/device_classic.py` | MODIFY | -2, +1 | Use centralized constants |

### Success Criteria

- [x] **SC-1**: All UUID constants defined in single location (`bleep/bt_ref/constants.py`)
- [x] **SC-2**: All codec constants defined in single location (`bleep/bt_ref/constants.py`)
- [x] **SC-3**: No hardcoded UUID strings remain in audio-related modules
- [x] **SC-4**: No hardcoded codec IDs remain in audio-related modules
- [x] **SC-5**: All modules import from centralized location
- [x] **SC-6**: Helper functions (get_codec_name, get_profile_name) available from constants
- [x] **SC-7**: No linting errors introduced
- [x] **SC-8**: Backward compatibility maintained (aliases for old constant names)

### Benefits

1. **Single Source of Truth**: All constants in one location
2. **Easier Maintenance**: Update values in one place
3. **Consistency**: No risk of mismatched values across modules
4. **Type Safety**: Constants prevent typos
5. **Documentation**: Clear references to specifications
6. **Helper Functions**: Centralized utility functions reduce duplication

### Dependencies & Risks

**Risks:**
- Circular imports (mitigated by importing from bt_ref which has no dependencies)
- Breaking changes (mitigated by backward compatibility aliases)
- Missing constants (mitigated by comprehensive audit)

**Mitigation:**
- Incremental migration (one module at a time)
- Comprehensive testing after each phase
- Backward compatibility aliases

---

## Classic Bluetooth UUID Enhancement for Device Type Classification (Active)

> **Status**: Implementation Complete - Ready for Testing  
> **Created**: 2026-01-19  
> **Completed**: 2026-01-19  
> **Updated**: 2026-01-19 (UUID Relocation)  
> **Goal**: Incorporate Classic Bluetooth UUIDs (especially Service Discovery Server) into device type classification with proper weight assignment

### Background & Objectives

Enhance device type classification by:
1. Adding missing ESP SSP UUID (0xABF0) to constants
2. Detecting Service Discovery Server (0x1000) as CONCLUSIVE evidence for Classic devices
3. Maintaining existing STRONG weight for other Classic service UUIDs
4. Leveraging existing UUID extraction/matching functionality (no duplication)

### Evidence-Based Analysis Summary

**Critical Finding**: UUID extraction and matching already works perfectly. No need for duplicate constants.

| Component | Status | Location | Evidence |
|-----------|--------|----------|----------|
| UUID Extraction (16-bit from 128-bit) | **EXISTS** | `device_type_classifier.py:348-349` | `classic_short_uuids.add(classic_normalized[4:8])` |
| UUID Normalization | **EXISTS** | `uuid_utils.py:39`, `uuid_translator.py:162` | Extracts 16-bit from 128-bit BT SIG format |
| UUID Matching (16-bit & 128-bit) | **EXISTS** | `device_type_classifier.py:370-382` | Handles both formats via `identify_uuid()` |
| Classic UUID Constants | **EXISTS** | `bt_ref/uuids.py:1313-1390` | `SPEC_UUID_NAMES__SERV_CLASS` contains all UUIDs in 128-bit format |
| ESP SSP UUID | **MISSING** | N/A | 0xABF0 not in `SPEC_UUID_NAMES__SERV_CLASS` |
| Service Discovery Server Weight | **NEEDS UPDATE** | `device_type_classifier.py:396` | Currently STRONG, should be CONCLUSIVE |

**UUIDs Already Present in `SPEC_UUID_NAMES__SERV_CLASS`:**
- ✅ Service Discovery Server (0x1000): `"00001000-0000-1000-8000-00805f9b34fb"`
- ✅ Serial Port Profile (0x1101): `"00001101-0000-1000-8000-00805f9b34fb"`
- ✅ Audio Source (0x110A): `"0000110a-0000-1000-8000-00805f9b34fb"`
- ✅ Audio Sink (0x110B): `"0000110b-0000-1000-8000-00805f9b34fb"`
- ✅ A2DP (0x110D): `"0000110d-0000-1000-8000-00805f9b34fb"`
- ✅ Handsfree Audio Gateway (0x111F): `"0000111f-0000-1000-8000-00805f9b34fb"`
- ❌ ESP SSP (0xABF0): **MISSING**

### Implementation Plan (Minimal Approach)

#### Phase 1: Add Missing UUID Constant
**Goal**: Add ESP SSP (0xABF0) to `SPEC_UUID_NAMES__SERV_CLASS`

- [x] **1.1 Update `bleep/bt_ref/uuids.py`** (~1 line)
  - [x] Add entry: `"0000abf0-0000-1000-8000-00805f9b34fb" : "ESP SSP",`
  - [x] Place in appropriate location within `SPEC_UUID_NAMES__SERV_CLASS` dictionary (alphabetically or by UUID value)

**Files**: `bleep/bt_ref/uuids.py` (MODIFY)

#### Phase 2: Enhance Device Type Classifier
**Goal**: Detect Service Discovery Server with CONCLUSIVE weight

- [x] **2.1 Update `ClassicServiceUUIDsCollector.collect()` method** (~25 lines in `device_type_classifier.py`)
  - [x] Add helper method `_is_service_discovery_server(uuid: str) -> bool`:
    - [x] Use `identify_uuid()` to normalize UUID
    - [x] Check if short form (16-bit) is `"1000"`
    - [x] Handle both 16-bit (`"1000"`, `"0x1000"`) and 128-bit formats
  - [x] During UUID matching loop, check if Service Discovery Server is found
  - [x] If Service Discovery Server detected:
    - [x] Add evidence with `EvidenceWeight.CONCLUSIVE` (separate from other Classic UUIDs)
    - [x] Include metadata: `{"is_service_discovery_server": True, "uuid": uuid_str}`
  - [x] For other Classic UUIDs, keep existing `EvidenceWeight.STRONG` behavior

- [x] **2.2 Update Classification Logic** (~5 lines in `device_type_classifier.py`)
  - [x] Modify `_classify_classic()` to accept `CLASSIC_SERVICE_UUIDS` with CONCLUSIVE weight as conclusive evidence
  - [x] Update `_classify_dual()` to recognize CONCLUSIVE Classic service UUID evidence
  - [x] Update `_generate_reasoning()` to mention "Service Discovery Server detected" when present

**Files**: `bleep/analysis/device_type_classifier.py` (MODIFY)

### File Summary

| File | Action | Estimated Lines |
|------|--------|-----------------|
| `bleep/bt_ref/uuids.py` | MODIFY | ~1 |
| `bleep/analysis/device_type_classifier.py` | MODIFY | ~30 |
| **TOTAL** | | **~31 lines** |

### Success Criteria

- [x] ESP SSP (0xABF0) added to `SPEC_UUID_NAMES__SERV_CLASS`
- [x] Service Discovery Server (0x1000) detected with `CONCLUSIVE` weight
- [x] Other Classic UUIDs remain `STRONG` weight (no regression)
- [x] Classification logic recognizes CONCLUSIVE Classic service UUID evidence
- [x] Both 16-bit and 128-bit UUID formats handled (no changes needed - already works)
- [x] No duplicate constants added (leverages existing `SPEC_UUID_NAMES__SERV_CLASS`)
- [ ] No regressions in existing device type classification (pending testing)

### Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| Service Discovery Server detection could fail for some UUID formats | Use existing `identify_uuid()` function which handles all formats |
| Classification logic change could affect existing behavior | Only add CONCLUSIVE as additional path, don't remove STRONG path |
| ESP SSP UUID placement could break alphabetical ordering | Place in appropriate location (after 0x111F or maintain existing order) |

### Testing Strategy

- [ ] **Unit tests** for Service Discovery Server detection (16-bit and 128-bit formats)
- [ ] **Integration tests** with devices advertising Service Discovery Server
- [ ] **Regression tests** ensuring other Classic UUIDs still work with STRONG weight
- [ ] **Manual tests** with real Bluetooth Classic devices

---

## UUID Relocation and Constant Reference Enhancement (Active)

> **Status**: ✅ COMPLETE (reconciled 2026-07-22 after code audit — implementation was already present in code; checkboxes below were stale)  
> **Created**: 2026-01-19  
> **Goal**: Relocate ESP SSP UUID to persistent location and reference Service Discovery Server UUID via constants

### Background & Objectives

Address two issues identified after initial implementation:
1. **ESP SSP UUID Persistence**: ESP SSP (0xABF0) was added to auto-generated `bleep/bt_ref/uuids.py`, which will be overwritten during regeneration
2. **Hardcoded UUID Reference**: `_is_service_discovery_server()` function hardcodes `"1000"` instead of referencing a constant

### Implementation Plan

#### Phase 1: Relocate ESP SSP UUID
**Goal**: Move ESP SSP from auto-generated file to persistent custom UUID storage

- [x] **1.1 Remove ESP SSP from `bleep/bt_ref/uuids.py`** (~1 line)
  - [x] Remove entry: `"0000abf0-0000-1000-8000-00805f9b34fb" : "ESP SSP",` from `SPEC_UUID_NAMES__SERV_CLASS` — verified absent (2026-07-22)

- [x] **1.2 Add ESP SSP to `bleep/bt_ref/constants.py`** (~1 line)
  - [x] Add entry to `UUID_NAMES` dictionary: `"0000ABF0-0000-1000-8000-00805F9B34FB": "ESP SSP",` — present at `constants.py:436` (inside `UUID_NAMES`, defined at `constants.py:386`)

**Files**: `bleep/bt_ref/uuids.py` (MODIFY), `bleep/bt_ref/constants.py` (MODIFY)

#### Phase 2: Add Service Discovery Server Constant Reference
**Goal**: Replace hardcoded "1000" with constant reference

- [x] **2.1 Add constant to `bleep/bt_ref/constants.py`** (~1 line)
  - [x] Add: `SERVICE_DISCOVERY_SERVER_UUID_16 = "1000"` in "# Common Service/Characteristic UUIDs" section — present at `constants.py:452`

- [x] **2.2 Update `_is_service_discovery_server()` function** (~2 lines in `device_type_classifier.py`)
  - [x] Add import: `from bleep.bt_ref.constants import SERVICE_DISCOVERY_SERVER_UUID_16` — `device_type_classifier.py:335`
  - [x] Replace: `sds_short = "1000"` with `sds_short = SERVICE_DISCOVERY_SERVER_UUID_16` — `device_type_classifier.py:338`
  - [x] **Bug fix (2026-07-22)**: `"0x1000"` prefix was never stripped (input upper-cased before a lower-case `'0x'` check) → `_is_service_discovery_server("0x1000")` returned `False`. Fixed to check `'0X'`; covered by `tests/test_device_type_sds.py`.

**Files**: `bleep/bt_ref/constants.py` (MODIFY), `bleep/analysis/device_type_classifier.py` (MODIFY)

### File Summary

| File | Action | Estimated Lines |
|------|--------|-----------------|
| `bleep/bt_ref/uuids.py` | MODIFY | -1 (remove ESP SSP) |
| `bleep/bt_ref/constants.py` | MODIFY | +2 (ESP SSP + SDS constant) |
| `bleep/analysis/device_type_classifier.py` | MODIFY | +2 (import + constant reference) |
| **TOTAL** | | **~3 net lines** |

### Success Criteria

- [x] ESP SSP removed from auto-generated `uuids.py`
- [x] ESP SSP accessible via `constants.UUID_NAMES`
- [x] `SERVICE_DISCOVERY_SERVER_UUID_16` constant defined and accessible
- [x] `_is_service_discovery_server()` uses constant instead of hardcoded value
- [x] UUID translator can find ESP SSP in custom UUIDs database
- [x] No regressions in device type classification — verified via new `tests/test_device_type_sds.py` (16 tests) + full suite green (2026-07-22)

### Rationale

- **ESP SSP Persistence**: Custom UUIDs belong in `constants.UUID_NAMES` which is not auto-generated, ensuring persistence across UUID database regenerations
- **Constant Reference**: Eliminates hardcoded magic string, improves maintainability, and follows BLEEP's pattern of centralizing constants
- **Minimal Approach**: Only adds 16-bit constant (not 128-bit) since function only uses 16-bit form; 128-bit already exists in `SPEC_UUID_NAMES__SERV_CLASS` if needed elsewhere

---

### High-level backlog (copy + paste from sources)

- [ ] **Debug mode: Classic keep-alive command** (Partially Complete - Requires Further Work)
  - [x] Implement `ckeep` command to open/close RFCOMM socket for ACL keep-alive
  - [x] Support `--first`, `--svc NAME`, and numeric channel selectors
  - [x] Remove duplicated `ckeep` logic blocks (ensure single execution path)
  - [x] Preserve BlueZ `org.bluez.Error.Failed` message detail (e.g. `br-connection-unknown`) in Bleep errors/logs
  - [x] Auto-close socket on `quit`
  - [x] Update help banner & changelog
  - [ ] **Further work required**: Full functionality testing and validation blocked by Classic device connection issues. Requires a Bluetooth Classic target device with no pairing/PIN requirements to properly validate RFCOMM socket operations and ACL keep-alive functionality. Error handling and logging are functional; core connection/socket operations need validation with appropriate hardware.

- [x] **Agent + AgentManager verbosity / diagnosability checklist**
  - [x] **`bleep/dbuslayer/agent.py`**: Improve AgentManager registration error detail
    - [x] Include D-Bus error name + message (`get_dbus_name`, `get_dbus_message`) in failures from `_setup_agent_manager()`
    - [x] Include agent path + capabilities + default-agent flag in failures from `register()`
    - [x] Log failures at `LOG__AGENT` with structured context (agent_path, capabilities, default)
  - [x] **`bleep/core/errors.py`**: Preserve message payload for agent-relevant D-Bus exceptions
    - [x] Ensure `org.bluez.Error.*` mappings keep `exc.get_dbus_message()` when present (NotPermitted, NotAuthorized, Failed, InProgress)
    - [x] Ensure `UnknownObject` includes target path (when available) for agent/device operations (D-Bus message preserves path information)
  - [x] **`bleep/modes/agent.py`**: Fix agent-mode correctness + improve CLI visibility
    - [x] Fix indentation so `create_agent()` is called for all agent types (not just a branch) - verified correct indentation
    - [x] Log the exact chosen agent type + cap + default + auto_accept + agent_path
  - [x] **`bleep/dbuslayer/device_classic.py` + `bleep/dbuslayer/device_le.py`**: Improve connect/pair failure context
    - [x] On DBusException, log method invoked + device path + adapter + D-Bus error name/message
    - [x] Ensure mapped exceptions preserve D-Bus message text
  - [x] **`bleep/dbuslayer/agent_io.py`**: Increase IO handler context
    - [x] When prompting/auto-accepting, log handler type + auto_accept/default values used (no secrets)
  - [x] **`bleep/modes/debug.py`**: Add agent status / control commands (debug-only)
    - [x] `agent status` (show whether default agent registered, cap, path)
    - [x] `agent register [--interactive|--auto] [--cap ...] [--default]`
    - [x] `agent unregister`
  - [x] **Error clarity expansion (post-agent)**
    - [x] `bleep/core/errors.py`: include `exc.get_dbus_message()` in default fall-through mapping
    - [x] `bleep/dbuslayer/media_services.py`: replace `str(e)` logging with `name: message` and avoid silent bool-only failures
    - [x] `bleep/dbuslayer/media_browse.py`: replace `str(e)` logging with `name: message` and avoid silent empty-list/None masking
    - [x] `bleep/dbuslayer/obex_pbap.py`: preserve D-Bus name/message in raised RuntimeError diagnostics
    - [x] `bleep/dbuslayer/manager.py`: log underlying D-Bus name/message when StartDiscovery falls back

- [x] **PIN Code Request Visibility and Diagnostic Enhancements** - **COMPLETE** (Diagnostic capabilities implemented; the "core issue" was a **misdiagnosis** — RESOLVED, see below)
  - [x] **Phase 1: Fix Communication Type Logging** - Fixed D-Bus communication type labeling (METHOD CALL vs SIGNAL)
  - [x] **Phase 2: Enhanced Agent Method Invocation Detection** - Added method invocation tracking and capability validation
  - [x] **Phase 3: Enhanced Event Correlation** - Automatic RequestPinCode → Cancel correlation with root cause analysis
  - [x] **Phase 4: Root Cause Analysis Summary** - Automated failure summaries with actionable recommendations
  - [x] **Phase 5: Agent Registration Status Verification** - Registration status tracking and warnings
  - [x] **Phase 6: Destination Match Diagnostic Logging** - Bus unique name logging and destination verification
  - [x] **Core Issue — RESOLVED (misdiagnosis; live-confirmed 2026-07-23)**: The "D-Bus methods not registered / introspection returns empty XML" finding was an **artifact of the diagnostic test**, not a real defect — it came from a process introspecting its **own** bus object (D-Bus `AccessDenied`) and from querying the wrong service name (`org.bluez` instead of BLEEP's unique bus name). Agent registration and `org.bluez.Agent1` dispatch work end-to-end (the running-MainLoop requirement was the real fix, v2.6.2). **Live re-confirmation (2026-07-23):** a fresh pairing run registered all 9 `Agent1` methods (`Agent method registration verified via D-Bus introspection`) and paired a device end-to-end; the observation DB holds a `pairing_events` row (`method=RequestConfirmation`, `pin=0000`, `result=success`) proving BlueZ invoked the agent callback. Canonical: `agent_pairing_flow_analysis.md` (CONFIRMED WORKING). The eight historical investigation docs (incl. `agent_dbus_communication_issue.md`) are archived with banners pointing here.

- [x] **Unified D-Bus Event Aggregator (Phase 2A - Reorganized)**
  - [x] **`bleep/dbuslayer/signals.py`**: Create unified event capture and aggregation system
    - [x] Create `DBusEventCapture` dataclass to replace separate `SignalCapture` and `MethodCallCapture` (unified structure for signals, method calls, method returns, errors)
    - [x] Create `DBusEventAggregator` class for centralized event storage and correlation
    - [x] Add unified event tracking to `__init__` (`_event_aggregator`, `_unified_monitoring`, `_unified_message_filter`)
    - [x] Implement `_on_dbus_message(bus, message)` unified handler for all D-Bus message types
    - [x] Implement `_is_relevant_message()` filter to identify BlueZ/Agent related messages
    - [x] Implement `_capture_signal()`, `_capture_method_call()`, `_capture_method_return()`, `_capture_error()` type-specific capture methods
    - [x] Implement `_log_event()` with human-readable + detailed format (follows error handling pattern)
    - [x] Implement `enable_unified_dbus_monitoring(enabled, filters)` public API method
    - [x] Implement `_attach_unified_listeners()` to add match strings for all message types (signals, method calls, returns, errors)
    - [x] Implement `_detach_unified_listeners()` for cleanup
    - [x] Implement query methods: `get_recent_events()`, `correlate_event()`, `get_method_call_chain()`
    - [x] Update `_detach_bus_listeners()` to also detach unified listeners
    - [x] Handle `DBusException` gracefully (eavesdrop may require root/policy changes; don't fail agent registration)
    - [x] Maintain backward compatibility: keep existing `enable_agent_method_call_monitoring()` as wrapper (deprecated)
    - [x] Update `SignalCorrelator` integration for backward compatibility
  - [x] **`bleep/dbuslayer/agent.py`**: Integrate unified monitoring with agent lifecycle
    - [x] Update `register()` method to use `enable_unified_dbus_monitoring()` instead of method call only
    - [x] Add error handling to continue agent registration if monitoring fails
    - [x] Document optional disable in `unregister()` (keep enabled for general system monitoring)
  - [x] **Testing & Verification**
    - [x] Test signal capture (PropertiesChanged, InterfacesAdded/Removed)
    - [x] Test method call capture (Agent1, AgentManager1, Device1 methods)
    - [x] Test method return capture (verify serial number correlation)
    - [x] Test error capture (AuthenticationRejected, Failed, etc.)
    - [x] Test correlation: method call → return/error chains via serial numbers
    - [x] Test correlation: path-based relationships across event types
    - [x] Test query methods with various filters (event_type, interface, path, time_window)
    - [x] Test `get_method_call_chain()` for complete call → return/error sequences
    - [x] Compare output against `dbus-monitor --system "destination='org.bluez'" "sender='org.bluez'"` for accuracy
    - [x] Verify human-readable summary format matches error handling pattern (`name: msg`)
    - [x] Verify detailed information preserves original message for analysis
    - [x] Test monitoring with/without root permissions (graceful degradation)
    - [x] Verify backward compatibility with existing signal capture code

- [x] **Error clarity expansion — phase 2 (Task A + Task B planning)**
  - [x] **Task A: Silent failure audit + targeted verbosity upgrades (no API break)**
    - [x] Inventory remaining `DBusException` handlers that return `False`/`None`/`[]` or log only `str(e)`
    - [x] Prioritize high-impact call paths: `dbus/device.py`, `dbuslayer/media.py`, `dbuslayer/characteristic.py`, `dbuslayer/service.py`, `dbuslayer/descriptor.py`, `ble_ops/*`
    - [x] For each target, add structured context to logs (operation + object path + `name: message`) without changing return types/raising behaviour
    - [x] Verify: `py_compile` + run the narrowest relevant tests after each file
    - [x] Continue follow-up pass: `bleep/dbuslayer/device_le.py`, `bleep/dbuslayer/device_classic.py`, `bleep/dbuslayer/agent.py`, `bleep/dbuslayer/manager.py`, then `bleep/ble_ops/*`
  - [x] **Task B: Error mapping consolidation (safety-first; no behaviour drift)**
    - [x] **B0: Contracts + intent (lock down before changing behavior)** *(starting point)*
      - [x] Document `bt_ref/error_map.py` tuple contract: `map_dbus_error(DBusException)->(code, category)`, `handle_error(Exception, device)->(code, recovered)`
      - [x] Confirm meaning of `recovered=True`: recovery action executed successfully (does **not** imply original operation retried)
      - [x] Confirm recovery remains category-based (connection/state/protocol only) and does not trigger for permission/resource categories
      - **Evidence / current call sites**:
        - `bleep/bt_ref/error_map.py`:
          - `map_dbus_error()` returns `(result_code, category)` where `result_code` is from `DBUS_ERROR_MAP` (default `RESULT_EXCEPTION`) and `category` is derived from `ERROR_CATEGORIES`.
          - `handle_error()` returns `(result_code, recovered)` where `recovered=True` only if a recovery strategy exists for the derived category *and* it executes successfully (no automatic retry of the original failing operation).
          - Recovery strategies are currently **category-based**:
            - `connection` → `_reconnect_device(device)` (calls `device.Connect()`)
            - `state` → `_resolve_services(device)` (calls `device.check_and_wait__services_resolved()`)
            - `protocol` → `_retry_with_delay()` (fixed sleep)
            - `permission` / `resource` / `unknown` → **no recovery**
        - `bleep/dbus/device.py` uses the tuple contract directly:
          - `Connect/Disconnect/Pair` catch `Exception` and return `handle_error(e, self)` (tuple passthrough to callers).
          - `_setup_device()` logs `result_code` via `map_dbus_error(e)` (tuple) for diagnostics only.
    - [x] **B1: Build an evidence “truth table”** comparing `core/error_handling.decode_dbus_error` vs `bt_ref/error_map` mappings and their current call sites
      - **Truth table snapshot (name-level mapping differences)**:
        - `core/error_handling.decode_dbus_error` (name-map `_DBUS_ERROR_NAME_MAP`, default `RESULT_ERR`, plus message-substring heuristics)
        - `bt_ref/error_map.map_dbus_error` (name-map `DBUS_ERROR_MAP`, default `RESULT_EXCEPTION`, no message-substring heuristics)
        - **Known mismatches (must be resolved before bt_ref delegates to core)**:
          - `org.bluez.Error.NotPermitted`: core → `RESULT_ERR_NOT_PERMITTED`; bt_ref → `RESULT_ERR_ACCESS_DENIED` (category=permission either way; reporting code differs)
          - `org.bluez.Error.NotAuthorized`: core → `RESULT_ERR_NOT_AUTHORIZED`; bt_ref → default `RESULT_EXCEPTION` (unmapped today)
          - `org.freedesktop.DBus.Error.InvalidArgs`: bt_ref → `RESULT_ERR_BAD_ARGS`; core → not name-mapped today (falls back to message heuristics / `RESULT_ERR`)
          - `org.freedesktop.DBus.Error.AccessDenied`: bt_ref → `RESULT_ERR_ACCESS_DENIED`; core → not name-mapped today (falls back to `RESULT_ERR`)
          - `org.freedesktop.DBus.Error.ServiceUnknown`: bt_ref → `RESULT_ERR_UNKNOWN_SERVCE`; core → not name-mapped today (falls back to `RESULT_ERR`)
          - `org.bluez.Error.NotAvailable` / `org.bluez.Error.DoesNotExist`: bt_ref → `RESULT_ERR_NOT_FOUND`; core → not name-mapped today (falls back to `RESULT_ERR`)
          - `org.bluez.Error.NotFound`: core → `RESULT_ERR_NOT_FOUND`; bt_ref → default `RESULT_EXCEPTION` (unmapped today)
          - `org.bluez.Error.InvalidArguments`: core → `RESULT_ERR_BAD_ARGS`; bt_ref → default `RESULT_EXCEPTION` (unmapped today)
        - **Message-heuristic capability (core-only)**:
          - core can map `"read/write/notify/indicate not permitted"` → operation-specific `RESULT_ERR_*_NOT_PERMITTED` codes; bt_ref currently cannot.
      - **Truth table snapshot (call-site split)**:
        - bt_ref tuple interface used directly by: `bleep/dbus/device.py` (`handle_error(e, self)` return path; tuple passthrough)
        - exception interface used by most refactored stack: `bleep/core/errors.py::map_dbus_error` (returns `BLEEPError` subclasses, uses core decode internally)
    - [x] **B1.1: Expand `core/error_handling.decode_dbus_error` (single source of truth)**
      - [x] Expand name-level mapping to cover bt_ref’s existing `DBUS_ERROR_MAP` names (and any additional names observed in code/logs)
      - [x] Keep message-substring heuristics (read/write/notify/indicate not permitted, etc.) and document precedence (name > message > fallback)
      - [x] Verify core name-map becomes a superset of bt_ref needs (or explicitly justify omissions)
      - **Precedence (must remain stable):**
        - **1) Name-level mapping wins** (`exc.get_dbus_name()` in `_DBUS_ERROR_NAME_MAP`)
        - **2) Message-level mapping** for permission granularity (`exc.get_dbus_message()` substrings like read/write/notify/indicate not permitted)
        - **3) Fallback** to `RESULT_ERR` when no match
    - [x] **B2: Augment `bt_ref/error_map.py` to always use core decode (preserve tuple + recovery semantics)**
      - [x] Implement “core-first decode” inside bt_ref with local imports (avoid import loops)
      - [x] Add bt_ref-local refinement for cases where core returns generic codes but bt_ref can be more specific using `get_dbus_name()` / `get_dbus_message()`
      - [x] Introduce “reporting_code vs category_code” normalization so bt_ref can keep precise codes while preserving recovery categorization
      - [x] Ensure no caller changes required initially (especially `bleep/dbus/device.py`)
      - **Verification notes**:
        - No call-site changes were required: `bleep/dbus/device.py` continues to import `handle_error` / `map_dbus_error` from `bleep.bt_ref.error_map`.
        - Added unit coverage: `tests/test_bt_ref_error_map.py` exercises bt_ref core-first decode + normalization behavior.
    - [x] **B3: Recovery semantics + retry discipline (avoid device “busy” amplification)**
      - [x] **Do not hammer**: when re-attempting any failed operation, apply a **fixed wait** before retrying (default: 0.5–1.0s) to let the target/device stack settle
      - [x] **Prefer waiting over retrying** when the failure indicates the device is still processing (e.g., `InProgress`, “Operation already in progress”, transient controller/stack teardown)
      - [x] **Cap retries**: keep retry counts low (e.g., 1–3) and fail fast for permission/argument errors (never retry those)
      - [x] **Categorize before retry**: only connection/state/protocol categories may trigger recovery; permission/resource should not auto-retry
      - [x] **No implicit “retry original op” loops** without an explicit fixed-delay policy (prevents cascading errors on fragile devices)
      - [x] Audit gaps in recovery strategies (missing cases, missing staged waits, device/controller stall handling)
      - [x] Plan (and later implement) an explicit “retry original operation” wrapper that uses fixed-delay policy and low retry caps (do **not** bake infinite loops into low-level helpers)
      - **Implemented (bt_ref-level helper, conservative by default):**
        - `bleep/bt_ref/error_map.py::attempt_operation_with_recovery()`:
          - fixed delay between attempts (default 0.7s)
          - low retry cap (default 2)
          - never retries deterministic failures (permission/bad args/not supported)
      - **Recovery gap found + fixed:**
        - `_reconnect_device()` previously treated tuple-return interfaces as “success” even when `(code, False)` was returned; now treats that as failure so `recovered` is accurate.
    - [x] **B4: BLEEPError transparency audit (no “blanding” / no hidden payloads)**
      - [x] Inventory `BLEEPError` subclass mappings that override/replace DBus messages; ensure D-Bus `name` + `message` remain visible
      - [x] Confirm `core/errors.py::map_dbus_error` does not force generic messages when actionable D-Bus payload exists (e.g., BlueZ `org.bluez.Error.Failed` message bodies)
      - **Fixes applied + coverage**:
        - `NotAuthorizedError` now accepts an optional `reason` and preserves the D-Bus message payload in the exception string.
        - `ServiceUnknown` mapping now uses the D-Bus message payload (when present) instead of repeating the error name.
        - `UnknownObject` mapping no longer forces `DeviceNotFoundError("D-Bus operation")`; it preserves `name: message` as a `BLEEPError` to avoid blanding/misclassification.
        - Fixed `handle_dbus_exception()` to raise the mapped `BLEEPError` (it previously attempted to unpack a non-tuple result).
        - Added unit coverage: `tests/test_core_errors_transparency.py`
    - [x] **B5: Deprecation + cleanup (remove legacy requirements safely)**
      - [x] After parity proven, deprecate bt_ref’s independent name→code table as a *source of truth* (keep only category/refinement logic if needed)
      - [x] **B5.2: Reduce reliance on legacy tuple-path modules** (COMPLETE - Option A executed)
        - [x] Evaluate deprecating `bleep/dbus/device.py` in favor of refactored device wrappers (`bleep/dbuslayer/device_le.py`, `bleep/dbuslayer/device_classic.py`)
        - **Status**: COMPLETE - Legacy module removed (Option A: direct removal)
        - **Phase 1 audit results** (completed):
          * **Static analysis**: AST-based import analysis found zero imports of `bleep.dbus.device` in all Python files within `bleep/` directory
          * **Runtime verification**: No imports detected when loading key entrypoints (`bleep.modes.debug`, `bleep.modes.agent`, `bleep.ble_ops.connect`, `bleep.dbuslayer.device_le`, `bleep.core.device_management`)
          * **Package structure**: `bleep/dbus/__init__.py` does NOT include `device` in `__all__`, confirming it's not intentionally exposed
          * **Actual usage**: All code imports from `bleep.dbuslayer.device_le`, NOT from `bleep.dbus.device`
          * **Conclusion**: `bleep/dbus/device.py` was completely unused - no artifacts of importing the file remained in the codebase
        - **Migration executed**: **Option A (Direct Removal)**
          * Deleted `bleep/dbus/device.py` (~214 lines, tuple-return contract implementation)
          * Verified no regressions: all key entrypoints import successfully after removal
          * No changes needed to `bleep/dbus/__init__.py` (device was never in `__all__`)
          * Documentation updated (changelog, todo tracker)
        - **Current state analysis**:
          - **Legacy module** (`bleep/dbus/device.py`): ~214 lines, tuple-return contract `(code, success)`, minimal features, uses `bt_ref.error_map`
            * Public interface: `Connect() -> Tuple[int, bool]`, `Disconnect() -> Tuple[int, bool]`, `Pair() -> Tuple[int, bool]`
            * Properties: `address`, `adapter`, `connected`, `paired`, `services_resolved`
            * Methods: `find_and_get__device_property()`, `find_and_get__all_device_properties()`, `check_and_wait__services_resolved()`
          - **Refactored modules**: `bleep/dbuslayer/device_le.py` (~2400+ lines), `bleep/dbuslayer/device_classic.py` (~750+ lines), exception-based contract, rich feature set
            * Exception-based error handling via `bleep.core.errors.map_dbus_error()` (returns `BLEEPError` subclasses)
            * Rich features: GATT enumeration, service resolution, media support, signal handling, reconnection monitoring
            * Method-based property access: `is_connected()`, `is_paired()`, `is_trusted()`, etc.
          - **Key interface differences**:
            * Method names: `Connect()` vs `connect()` (case-sensitive; legacy uses PascalCase)
            * Return types: `Tuple[int, bool]` (legacy) vs raises `BLEEPError` subclasses (refactored)
            * Property access: `device.connected` (property in legacy) vs `device.is_connected()` (method in refactored)
            * Error handling: `handle_error()` tuple return with automatic recovery (legacy) vs exception-based with explicit caller handling (refactored)
            * Parameter names: `bluetooth_adapter` (legacy) vs `adapter_name` (refactored)
        - **Preliminary findings**:
          - `bleep/dbus/device.py` appears unused (no direct imports found in codebase; only mentioned in comments in `bleep/dbus/__init__.py`)
          - Refactored `bleep/dbuslayer/device_le.py` is what's actually used throughout the codebase
          - `bleep/dbuslayer/device.py` re-exports the refactored classes
        - **4-Phase plan structure** (evaluation-first; no code changes until audit complete):
          - **Phase 1: Comprehensive usage audit** (no code changes):
            * Static analysis: grep for all import patterns (`from bleep.dbus.device import`, `import bleep.dbus.device`, dynamic imports via `importlib`/`__import__`)
            * Runtime verification: import tracking script to verify no `bleep.dbus.device` imports occur during key entrypoint loading
            * Interface contract comparison: side-by-side method signature documentation, parameter differences, return type differences
            * Error handling contract analysis: tuple-return semantics vs exception-based semantics, recovery strategy differences
          - **Phase 2: Migration strategy design**:
            * Decision tree based on audit findings:
              - **Option A (if unused)**: Direct removal of `bleep/dbus/device.py`, update `bleep/dbus/__init__.py`, remove documentation references
              - **Option B (if callers exist)**: Compatibility shim in `bleep/dbus/device.py` wrapping refactored device, converting exceptions to tuples, maintaining legacy interface
              - **Option C (if gaps exist)**: Feature parity enhancement in refactored modules, then re-evaluate migration
            * Compatibility shim design (if Option B): adapter class pattern converting `BLEEPError` exceptions to `(code, False)` tuples, preserving exact method signatures
          - **Phase 3: Implementation**:
            * Pre-migration validation: create comprehensive test suite for legacy interface, run both legacy and refactored test suites
            * Migration execution: execute chosen option (A, B, or C), add unit tests for shim (if applicable), run integration tests
            * Post-migration validation: full test suite, verify import behavior, check for performance regressions
          - **Phase 4: Documentation and deprecation**:
            * Code documentation: deprecation notices (if shim used), migration path documentation, type hint updates
            * Project documentation: update `bleep/docs/changelog.md`, update `bleep/docs/todo_tracker.md`, create migration guide (if callers exist)
        - **Migration options** (decision based on Phase 1 findings):
          - **Option A (Recommended if unused)**: Direct removal of `bleep/dbus/device.py`
            * Delete file, remove from `bleep/dbus/__init__.py` exports, update documentation, add changelog notice
          - **Option B (If callers exist)**: Compatibility shim wrapping refactored device
            * Implement adapter class in `bleep/dbus/device.py` that wraps `bleep.dbuslayer.device_le.system_dbus__bluez_device__low_energy`
            * Convert `BLEEPError` exceptions to `(code, False)` tuples, maintain exact method signatures (`Connect`, `Disconnect`, `Pair`)
            * Preserve property access patterns, handle edge cases (e.g., `check_and_wait__services_resolved` return type)
            * Document as temporary compatibility layer, create migration tracking for callers
          - **Option C (If gaps exist)**: Feature parity enhancement
            * Identify missing functionality in refactored modules, implement missing features, add tests, re-run Phase 1 audit
        - **Risk areas and mitigation**:
          - **Hidden dynamic imports**: `importlib.import_module('bleep.dbus.device')`, `__import__('bleep.dbus.device')` might not be caught by static analysis
            * Mitigation: Runtime import tracking script, comprehensive test suite execution
          - **Runtime behavior differences**: Tuple-return vs exception-based contracts have different error handling semantics
            * Mitigation: Side-by-side test suite execution, behavior comparison documentation
          - **Property vs method access**: Legacy uses properties (`device.connected`), refactored uses methods (`device.is_connected()`)
            * Mitigation: Compatibility shim (Option B) can provide property access via `@property` decorators
          - **Recovery semantics**: Legacy `handle_error()` provides automatic recovery; refactored stack requires explicit caller handling
            * Mitigation: Document recovery differences, provide migration guide for callers
        - **Success criteria** (per phase):
          - **Phase 1**: Complete usage audit with zero ambiguity about `bleep/dbus/device.py` usage, interface contract comparison document created, migration strategy decision (A, B, or C) made
          - **Phase 2**: Migration strategy fully designed and documented, compatibility shim designed with full interface mapping (if Option B), test plan created for validation
          - **Phase 3**: Migration executed (removal, shim, or feature parity), all tests pass (no regressions), performance validated (no significant degradation)
          - **Phase 4**: Documentation updated (code docs, project docs), deprecation notices in place (if applicable), changelog and todo tracker updated, Task B5.2 marked complete
        - **Timeline estimate**: 6-16 hours total
          * Phase 1 (Audit): 2-4 hours
          * Phase 2 (Design): 1-2 hours
          * Phase 3 (Implementation): 2-8 hours (depends on chosen option)
          * Phase 4 (Documentation): 1-2 hours
        - **Dependencies**: Task B0-B5 complete (error mapping consolidation provides foundation), comprehensive test suite for refactored device wrappers, access to test devices (for integration testing, if needed)
        - **Approval required**: This plan must be accepted before any code modifications are made. Evaluation-first approach: no code changes until usage audit (Phase 1) is complete and migration strategy is approved.
      - [x] Consolidate duplicate error logic within `core/error_handling.py` (decode tables vs other internal message maps) so there is truly one source of truth
      - **Deprecation markers added:**
        - `bleep/bt_ref/error_map.py::DBUS_ERROR_MAP` now marked as deprecated (only used for refinement fallback when core returns generic RESULT_ERR).
        - `bleep/core/error_handling.py::system_dbus__error_handling_service.evaluate__dbus_error()` marked as deprecated with TODO for consolidation.
        - Added canonical decoder documentation in `core/error_handling.py` identifying consolidation opportunities.
      - **Legacy module removal (B5.2) - COMPLETE:**
        - `bleep/dbus/device.py` has been removed after comprehensive audit confirmed zero usage
        - All codebase now uses refactored device wrappers (`bleep/dbuslayer/device_le.py`, `bleep/dbuslayer/device_classic.py`)
        - No compatibility shim needed - module was completely unused
    - [x] **Import-loop safety requirement (must not regress):**
      - [x] Keep imports one-directional: `core/error_handling` should not import `core/errors` at module import time
      - [x] Prefer local imports inside mapping functions to avoid circular dependencies (match existing style in `map_dbus_error`)
      - [x] Validate by running `python -m py_compile` and by importing key entrypoints (`bleep.modes.debug`, `bleep.modes.agent`, `bleep.ble_ops.connect`) in a fresh interpreter
      - **Verification complete:**
        - `core/error_handling.py` does NOT import `core/errors` at module level (only imports from `bt_ref` and `core.log`).
        - `bt_ref/error_map.py::map_dbus_error()` uses local import: `from bleep.core.error_handling import decode_dbus_error` (inside function).
        - All key entrypoints import successfully without circular dependency errors.

- [x] **Legacy Code Removal & Self-Sufficiency** – Complete removal of legacy dependencies (v2.3.1, 2025-10-29):
  - [x] Removed `sys.modules` shims in `bleep/__init__.py` for root-level legacy imports
  - [x] Deleted root-level legacy shim files (`bluetooth_constants.py`, `bluetooth_utils.py`, `bluetooth_uuids.py`, `bluetooth_exceptions.py`)
  - [x] Removed deprecated `bleep.compat.py` module (unused internally)
  - [x] Removed legacy namespace shim `Functions.ble_ctf_functions` from `ctf.py`
  - [x] Made PyGObject optional in `setup.py` (moved to `extras_require["monitor"]`)
  - [x] Added YAML cache files to `package_data` for complete package distribution
  - [x] Achieved complete codebase self-sufficiency with no dependencies on root-level legacy files
  - [x] Updated changelog with breaking changes and migration notes
  - [x] All internal imports now use proper paths (`from bleep.bt_ref import constants`)

- [x] **Documentation** – User mode guide completed (docs/user_mode.md)
- [x] **Assets-of-Interest (AoI) workflow**
  - [x] Implement analysis layer (`bleep/analysis/aoi_analyser.py`) converting (device,mapping,…) into actionable report
  - [x] Persist enumeration JSON dumps (`~/.bleep/aoi/*.json`) for offline analysis
  - [x] Integrate analyser into `modes/aoi.py` & debug shell (`aoi` command)
  - [x] Write dedicated documentation `docs/aoi_mode.md` (+ examples)
  - [x] Update CLI quick-start table (docs/cli_usage.md)
  - [x] Add entry to changelog on release
  - [x] Fix AoI implementation issues:
    - [x] Add missing `analyze_device_data` bridge method
    - [x] Fix service and characteristic data handling for different formats
    - [x] Improve error handling and type checking
    - [x] Resolve method name inconsistencies
  - [x] Enhance AoI documentation and capabilities:
    - [x] Document basic CLI commands and parameters
    - [x] Document security analysis features and report formats
    - [x] Explain JSON file format options and data storage
    - [x] Create programmatic API reference for AOIAnalyser class (`docs/aoi_implementation.md`)
    - [x] Add troubleshooting section and best practices
    - [x] Create comprehensive test suite for AoI functionality
    - [x] Document testing procedures in `docs/aoi_testing.md`
    - [x] Add integration examples with observation database
    - [x] Document advanced security analysis algorithms (see `aoi_security_algorithms.md`)
    - [x] Create customization guide for security assessment criteria (see `aoi_customization_guide.md`)
- [x] Multi-read / brute-write characteristic helpers complete
  - [x] `multi_read_characteristic` utility (repeat reads)
  - [x] `multi_read_all` rounds helper
  - [x] Configurable `brute_write_range` respecting landmine map

- [x] Implement passive / naggy / pokey / brute scan variants complete
  - [x] Enumeration variants unifying 4-tuple return complete:
    1. Δ `enum_helpers.py` – add `small_write_probe`, payload generator
    2. Δ `ble_ops/scan.py` – re-implement `naggy_enum`, `pokey_enum`, `brute_enum`
    3. Δ `cli.py` – flags for brute (`--range`, `--patterns`, `--payload-file`, `--force`, `--verify`)
    4. Δ `modes/debug.py` – aliases `enum`, `enumn`, `enump`, `enumb`
    5. ⊕ `tests/test_enum_helpers.py` – mock device read/write to verify behaviour
    6. Δ Docs (`ble_scan_modes.md`) – enumeration section & safety notes
    7. Δ `modes/debug.py` – enumeration command integration (enum/enumn/enump/enumb)
      - [x] D-2 implement `_enum_common` dispatcher
      - [x] D-3 wrapper commands & `_CMDS` entries (flags parsing verified)
      - [x] D-4 parse extra flags (`--force`, `--verify`, range) in debug shell
      - [x] D-5 robust error handling & state tracking (mine/perm maps, summaries)
      - [x] D-6 unit tests `tests/test_debug_enum_cmds.py`
      - [x] D-7 docs: debug enumeration examples
  - **Design overview for Enumeration Modes**
    - *Passive* – read-only enumeration, automatic reconnect/back-off; failures recorded in landmine/permission maps, no writes ever.
    - *Naggy*  – same read path but retries stubborn elements until root-cause (auth, permissions) classified; still write-free.
    - *Pokey*  – after read pass, attempt single-byte writes to advertised writable characteristics to probe accessibility without altering real data.
    - *Bruteforce* – exhaustive write fuzz: iterate payload patterns over every writable characteristic, monitoring side-effects; most intrusive.
  - **Implementation notes**
    - Re-use existing device.read_/write_characteristic helpers and error-handling.
    - Mode flag wired in CLI (`bleep scan --mode ...`) and Debug aliases.
    - Each mode builds on previous: Passive → Naggy (extra retry loop) → Pokey (adds light write) → Bruteforce (full write fuzz).
    - Adhere to minimal-diff guideline; wrappers delegate to shared core functions.
  - **Testing strategy**
    - Unit tests with stub device (like brute helpers) for retries & write attempts.
    - Integration tests rely on ENV `SCAN_TEST_MAC` when hardware present.
  - **Implementation task map for scan modes**
    1. Δ `bleep/ble_ops/scan.py`
       - add `naggy_scan`, `pokey_scan`, `brute_scan` thin wrappers (≤45 LOC).
    2. Δ `bleep/cli.py`
       - extend `scan` sub-parser with `--mode`, dispatch table.
       - validate `--target` required for *pokey*.
    3. Δ `bleep/modes/debug.py`
       - add aliases: `scann`, `scanp`, `scanb` and help lines.
    4. ⊕ `tests/test_scan_variants.py` – mock adapter verifies filter & loop counts ✅
    5. Δ Docs (`README`, `bl_classic_mode.md`)
       - small feature table row + CLI examples.

---

## Media-layer gap-analysis tasks (pending)

- [x] **Media1 service wrappers** – `bleep/dbuslayer/media_services.py` created (registration helpers). *(Phase 1)*
- [x] **MediaFolder & MediaItem browsing** – `bleep/dbuslayer/media_browse.py` added. *(Phase 1)*
- [x] **Extended enumeration utility** – `find_media_objects()` implemented. *(Phase 2)*
- [x] **MediaRegisterHelper** – SBC sink/source helper added. *(Phase 3)*
- [x] **Integration hooks** – `--objects` flag in `bleep/modes/media.py`. *(Phase 4)*
- [x] **Documentation & tests** – media_mode docs + pytest helper tests added.

- [x] **AoI Test Suite Fixes**
  - [x] Fix "unhashable type: 'dict'" errors in AoI analyzer:
    - [x] Update `analyse_device` method in `aoi_analyser.py` to handle dictionary keys properly
    - [x] Ensure all dictionary keys used in lookups are hashable types (strings, numbers, tuples)
    - [x] Add proper type checking before dictionary operations
  - [x] Fix JSON serialization errors with bytes objects:
    - [x] Create a custom JSON encoder class in `aoi_analyser.py` to handle bytes objects
    - [x] Update `save_device_data` method to use the custom encoder
    - [x] Convert bytes to hex strings during serialization
  - [x] Implement proper database error handling in CLI commands:
    - [x] Add device existence check before storing AoI analysis
    - [x] Create minimal device entries when analyzing unknown devices
    - [x] Add graceful error handling for foreign key constraint failures
    - [x] Provide user-friendly error messages instead of raw database errors
  - [x] Fix report generation failures:
    - [x] Ensure report templates handle missing or incomplete data
    - [x] Add fallback mechanisms for report generation when analysis data is incomplete
    - [x] Fix file path handling for report output
  - [x] Enhance test environment setup:
    - [x] Create proper test fixtures for AoI integration tests
    - [x] Implement database pre-population for required test data
    - [x] Add cleanup mechanisms to ensure test isolation

- [x] **Fix Agent Mode CLI Routing & Argument Exposure** – Critical bug fix for agent mode CLI:
  - [x] **Issue**: Agent mode routing broken due to argparse subparser argument name conflict - `args.mode == "agent"` check never matches because `args.mode` is overwritten by `--mode` argument value. CLI parser only exposes 2 of 12 agent features (`--mode` limited to simple/interactive), and argument passing is broken (only passes `--mode`, missing all other arguments).
  - [x] **Solution**: Fixed routing detection in `bleep/cli.py` line 702 by changing `elif args.mode == "agent":` to `elif len(sys.argv) > 1 and sys.argv[1] == "agent":` and pass `sys.argv[2:]` to agent mode. Expanded CLI parser arguments in `bleep/cli.py` lines 72-95 to include all agent mode options: `--mode` (added enhanced/pairing), `--cap`, `--default`, `--auto-accept`, `--pair`, `--trust`, `--untrust`, `--list-trusted`, `--list-bonded`, `--remove-bond`, `--storage-path`, `--timeout`. Arguments are parsed for help/validation but passed through to agent mode's parser for actual processing.
  - [x] **Files**: `bleep/cli.py` (lines 72-95, 702-706)
  - [x] **Testing**: Verified `bleep agent --mode=pairing --pair=MAC`, `bleep agent --list-trusted`, `bleep agent --trust=MAC` all work correctly. Verified other modes unaffected.

- [x] **Enhance Pairing Agent**
  - [x] **Phase 1: Agent Architecture** (2 weeks)
    - [x] Design Enhanced Agent Framework
      - [x] Support for multiple capability levels (DisplayOnly, DisplayYesNo, KeyboardOnly, NoInputNoOutput, KeyboardDisplay)
      - [x] Design flexible IO handler interface for different interaction modes
      - [x] Create state management for multi-step pairing processes
    - [x] Design persistent trusted device storage
      - [x] Define secure storage for paired device credentials
      - [x] Create migration path for existing paired devices
    - [x] Implement agent registration system
      - [x] Support registration with different capability levels based on context
      - [x] Implement proper agent release on shutdown
    - [x] Agent Manager Integration
      - [x] Implement proper integration with org.bluez.AgentManager1
      - [x] Support RegisterAgent method with proper capability arguments
      - [x] Handle RequestDefaultAgent correctly
      - [x] Add proper error handling for agent registration failures
  - [x] **Phase 2: Core Agent Methods** (3 weeks)
    - [x] Implement the full org.bluez.Agent1 interface:
      - [x] Release: Handle agent release requests
      - [x] RequestPinCode: Request PIN code for legacy pairing
      - [x] DisplayPinCode: Show PIN code to user
      - [x] RequestPasskey: Request passkey for SSP pairing
      - [x] DisplayPasskey: Show passkey with entered digits count
      - [x] RequestConfirmation: Handle numeric comparison pairing
      - [x] RequestAuthorization: Process authorization requests
      - [x] AuthorizeService: Control service-level authorization
      - [x] Cancel: Handle request cancellation
    - [x] Add support for Secure Simple Pairing (SSP)
      - [x] Implement numeric comparison workflow
      - [x] Add just-works pairing mode
      - [x] Support passkey entry method
    - [x] Implement service-level authorization
      - [x] Create authorization rules framework
      - [x] Add per-service authorization options
    - [x] Add support for automatic re-authentication
      - [x] Store bonding information securely
      - [x] Implement LTK (Long Term Key) management
  - [x] **Phase 3: User Interface Integration** (2 weeks)
    - [x] Create CLI prompts for agent interactions
      - [x] Implement passkey entry prompts
      - [x] Add confirmation dialogs for pairing requests
      - [x] Show PIN codes and passkeys when required
      - [x] Add cancel command for ongoing pairing operations
    - [x] Integrate agent with debug mode
      - [x] Add `pair [device_address]` command
      - [x] Add `unpair [device_address]` command
      - [x] Add `trust [device_address]` command
      - [x] Add `untrust [device_address]` command
    - [x] Integrate agent with user mode
      - [x] Create simplified pairing UX for non-expert users
      - [x] Add pairing status indicators
      - [x] Implement pairing request notifications
  - [x] **Phase 4: Reliability Enhancements** (2 weeks)
    - [x] Add agent connection monitoring
      - [x] Detect D-Bus disconnections
      - [x] Implement automatic re-registration after BlueZ restart
    - [x] Implement pairing timeout management
      - [x] Add configurable timeouts for different pairing operations
      - [x] Create timeout recovery strategies
    - [x] Handle incomplete pairing sessions
      - [x] Detect and recover from stalled pairing attempts
      - [x] Add cleanup for abandoned pairing sessions
    - [x] Enhance error reporting
      - [x] Create human-friendly error messages for common pairing failures
      - [x] Add diagnostic information for troubleshooting
      - [x] Create recovery suggestions for pairing errors
    - [x] Add pairing diagnostics tooling
      - [x] Create `check-pairing [device_address]` command
      - [x] Implement pairing capability detection for devices
      - [x] Add verbose logging option for pairing process
  - [x] **Phase 5: Documentation & Testing** (1 week)
    - [x] Create comprehensive documentation
      - [x] Update `docs/pairing_agent.md` with usage guide
      - [x] Document pairing troubleshooting steps
      - [x] Add examples for different pairing scenarios
      - [x] Document programmatic API for pairing agent
    - [x] Create test suite for pairing functionality
      - [x] Create mock device for agent interface testing
      - [x] Add integration tests for real device pairing
      - [x] Test edge cases for pairing failures
      - [x] Verify recovery mechanisms
- [x] **Device-feature database (SDP & PBAP)** - **COMPLETE**
  * Merge existing bullet *"Local database for unknown UUIDs + device observations"* – expand scope to store:
    * SDP service/attribute snapshots per device (Classic & BLE) ✅
    * PBAP phonebook metadata (repository sizes, Hash of full dump) ✅
    * First-seen / last-seen timestamps, adapter used, friendly names ✅
  * Decide storage: simple SQLite in `~/.bleep/observations.db` (no runtime deps)  **(SPEC FINAL 2025-07-24)** ✅
  * CLI helpers: `bleep db list|show|export <MAC>` ✅
  * Schema + ingestion implementation (v0)
    - [x] `core/observations.py` singleton connection + schema creation
    - [x] `upsert_device`, `insert_adv`, `upsert_services`, `upsert_characteristics`
    - [x] Hook `_native_scan` for adv inserts & device UPSERT
    - [x] Hook `_base_enum` for service / characteristic inserts
    - [x] Snapshot helpers for Media (`snapshot_media_player`, `snapshot_media_transport`)
    - [x] Unit tests `tests/test_observations_sqlite.py`
  * CLI (read-only phase-1)
    - [x] `db` sub-command in `cli.py` with actions `list-devices`, `show-device`, `export`
    - [x] Enhanced DB query methods: `get_devices`, `get_device_detail`, `get_characteristic_timeline`, `export_device_data`
    - [x] Support for filtering devices by status (recent, ble, classic, media)
    - [x] Timeline filtering by service and characteristic UUIDs
    - [x] Docs update (`cli_usage.md`, `README.md`, `observation_db.md`)
  * Schema migrations:
    - [x] v1 to v2: Renamed problematic column names to avoid Python keyword conflicts
      - `class` → `device_class` in devices table
      - `state` → `transport_state` in media_transports table
    - [x] Implemented migration code with backward compatibility
    - [x] Completed full v2 schema transition by removing all v1 schema code
    - [x] Removed all v1 schema compatibility code (codebase now exclusively uses v2 schema)
    - [x] v2 to v3: Added device_type field for improved device classification 
      - Added constants for device types: unknown, classic, le, dual
      - Enhanced device type detection with multiple heuristics
      - Updated filtering logic to use explicit device_type
  * Future telemetry table & migrations – tracked separately  
  * **SDP service/attribute snapshots storage** - **COMPLETE**:
    - [x] Create `sdp_records` table to store full SDP record snapshots (Service Record Handle, Profile Descriptor List, Service Version, Service Description, Protocol Descriptor List, raw record)
    - [x] Implement `upsert_sdp_record()` function in `bleep/core/observations.py`
    - [x] Hook SDP discovery functions to store full records (`discover_services_sdp()`, `_discover_services_dbus()`, connectionless mode)
    - [x] Update `get_device_detail()` and `export_device_data()` to include SDP records (automatic via get_device_detail)
    - [x] Create schema migration v6→v7 for new `sdp_records` table
    - [x] Update documentation (`observation_db.md`, `observation_db_schema.md`) to include `sdp_records` table
    - [x] **Note**: Both `classic_services` (basic UUID/channel mapping) and `sdp_records` (full snapshots) tables coexist for different use cases
  * Write migration note – **COMPLETE**:
    - [x] Added v6→v7 migration notes to schema documentation
    - [x] Migration history documented in `observation_db_schema.md`
  * Device type classification improvements:
    - [x] **Dual Device Detection Framework (Completed)** – Comprehensive evidence-based classification system:
      - [x] Plan created for modular, expandable dual device detection framework (superseded by `bleep/docs/device_type_classification.md`)
      - [x] Design includes database-first performance optimization with signature caching
      - [x] Design includes mode-aware classification (passive/naggy/pokey/bruteforce)
      - [x] Design includes code reuse leveraging existing SDP, GATT, and database functions
      - [x] Design includes stateless classification to prevent false positives from MAC collisions
      - [x] Phase 1: Core framework implementation (DeviceTypeClassifier module) - COMPLETED
        - [x] Created `bleep/analysis/device_type_classifier.py` module (~800 lines)
        - [x] Implemented `EvidenceType` and `EvidenceWeight` enums
        - [x] Implemented `EvidenceSet` class for evidence collection
        - [x] Implemented `ClassificationResult` class for results
        - [x] Implemented base `EvidenceCollector` abstract class
        - [x] Implemented 7 default evidence collectors (mode-aware, leveraging existing code)
        - [x] Implemented `DeviceTypeClassifier` main class with mode-aware evidence collection
        - [x] Implemented database signature caching (`_check_database_signature()`)
        - [x] Implemented signature matching (`_signatures_match()`)
        - [x] Implemented strict dual-detection logic
        - [x] Code reuse integration (SDP, GATT, database functions)
        - [x] Updated `bleep/analysis/__init__.py` to export new classifier
        - [x] Unit tests for evidence collection, classification, and mode awareness
      - [x] Phase 2: Database integration (schema v6, evidence table, signature caching) - COMPLETED
        - [x] Updated schema version to v6
        - [x] Created `device_type_evidence` table with proper indexes
        - [x] Implemented migration from v5 to v6
        - [x] Added `store_device_type_evidence()` function
        - [x] Added `get_device_type_evidence()` function
        - [x] Added `get_device_evidence_signature()` function for caching
        - [x] Updated `DeviceTypeClassifier._check_database_signature()` to use evidence table
        - [x] Updated `DeviceTypeClassifier._store_evidence_signature()` to store all evidence
        - [x] Verified database migration and evidence storage/retrieval
      - [x] Phase 3: D-Bus layer integration (fix Type property access errors) - COMPLETED
        - [x] Fixed `device_classic.get_device_type()` - removed incorrect Type property access
        - [x] Updated `device_classic.get_device_type()` to use DeviceTypeClassifier
        - [x] Fixed `device_le.check_device_type()` - removed incorrect Type property access
        - [x] Updated `device_le.check_device_type()` to use DeviceTypeClassifier
        - [x] Fixed `adapter._determine_device_type()` - removed hardcoded UUID patterns
        - [x] Updated `adapter._determine_device_type()` to use DeviceTypeClassifier
        - [x] All methods now use evidence-based classification with proper context building
        - [x] Backward compatibility maintained (return types unchanged)
      - [x] Phase 4: Mode-aware evidence collection (scan mode integration) - COMPLETED
        - [x] Verified classifier mode-aware filtering (passive/naggy/pokey/bruteforce)
        - [x] Updated `passive_scan_and_connect()` to call device type classification with "passive" mode
        - [x] Updated `naggy_scan_and_connect()` to call device type classification with "naggy" mode
        - [x] Updated `pokey_scan_and_connect()` to call device type classification with "pokey" mode
        - [x] Updated `bruteforce_scan_and_connect()` to call device type classification with "bruteforce" mode
        - [x] Updated `connect_and_enumerate__bluetooth__classic()` to call device type classification with "pokey" mode
        - [x] All scan functions now pass appropriate scan_mode to classifier
        - [x] Evidence collectors already mode-aware (implemented in Phase 1)
      - [x] Phase 5: Documentation & testing - COMPLETED
        - [x] Created comprehensive documentation (`device_type_classification.md`)
        - [x] Updated `observation_db.md` with evidence-based classification details
        - [x] Updated `observation_db_schema.md` with device_type_evidence table documentation
        - [x] Created integration test suite (`test_device_type_integration.py`)
        - [x] Tests cover evidence collection, classification logic, mode filtering, database integration, edge cases
        - [x] All tests passing (20/21 tests, 1 test requires hardware-specific setup)
      - [x] Phase 6: Foreign Key Constraint Fix (2025-11-27) - COMPLETED
        - [x] Fixed FOREIGN KEY constraint violations during device scanning
        - [x] Restructured database operation sequence: insert device → classify → update type
        - [x] Modified `adapter.get_discovered_devices()` to defer classification
        - [x] Updated `scan._native_scan()` for proper sequencing
        - [x] Updated `scan._base_enum()` for consistency
        - [x] Fixed SyntaxWarning in `media.py` docstring
        - [x] Added defensive IntegrityError handling in `observations.py`
        - [x] Preserved backward compatibility (`_determine_device_type()` method retained)
        - [x] Created comprehensive documentation (`CHANGES_APPLIED.md`)
    - [x] Enhance 'dual' device detection to require conclusive evidence from both protocols (addressed in framework) - COMPLETED
    - [x] Only set device_type='dual' when both BLE and Classic aspects are confirmed (addressed in framework) - COMPLETED
    - [x] Document specific detection criteria for each device type category (addressed in framework) - COMPLETED
  * Database timestamps tracking:
    - [x] Fix `first_seen` field not being populated for new devices
    - [x] Ensure timestamp fields maintain correct data (first_seen stays constant, last_seen updates)
    - [x] Update default CLI display to show both timestamp fields
  * Enhance observation_db.md documentation:
    - [x] Document schema versioning information
    - [x] Add filtering examples for `db list` and `db timeline`
    - [x] Expand database schema with comprehensive table and column descriptions
    - [x] Add programmatic API usage examples
    - [x] Document observation module's public functions with examples
    - [x] Create advanced query cookbook for complex data extraction scenarios
  * GATT enumeration database improvements:
    - [x] Fix SQL syntax error in upsert_characteristics function
    - [x] Add robust error handling to prevent cascade failures
    - [x] Support multiple data structure formats (standard, gatt-enum, enum-scan)
    - [x] Improve gatt-enum command to correctly extract and save characteristics
    - [x] Add automatic reconnection and retry logic for database operations
    - [x] Determine why enum-scan, gatt-enum, and gatt-enum --deep scans produce different information verbosity within the database (Note: Behavior may be perfectly within expected operational parameters)
    - [x] Investigate why gatt-enum --deep scan produces LESS database information than gatt-enum scan despite printing more information to terminal; ensure all terminal output is properly captured in the database
- [x] Classic Bluetooth enumeration
- [x] **Classic foundational tasks (bc-01 … bc-11)** — *migrated 2026-07-23 from `bl_classic_mode.md` §6 (the "Temporary Classic-Feature TODO Tracker"), which was removed from that guide once every item was complete. bc-10/bc-12/bc-13 are itemized separately below; bc-14+ follow. All complete.*
  - [x] bc-01 Research BlueZ D-Bus APIs for Classic (discovery, SDP, RFCOMM, PBAP)
  - [x] bc-02 Design high-level Classic API surface mirroring BLE helpers
  - [x] bc-03 Implement `dbuslayer/device_classic.py` wrapper
  - [x] bc-04 Create SDP service-discovery helper (`bleep/ble_ops/classic/sdp.py`)
  - [x] bc-05 Parse RFCOMM channels from SDP records
  - [x] bc-06 Extend `classic_connect_and_enumerate()` to return service→channel map
  - [x] bc-07 PBAP phone-book dump helper via BlueZ OBEX D-Bus
  - [x] bc-08 Add `bleep/ble_ops/classic/` equivalents (`classic_scan`, `classic_connect_and_enumerate`)
  - [x] bc-09 Add CLI sub-commands `classic-scan` & `classic-enum`
  - [x] bc-11 Write documentation for Classic mode & update README TOC
  - *§7 "Feature Tracker" status matrix was also migrated: every Classic feature (discovery, SDP, connection, PBAP, RFCOMM, OPP, MAP, FTP, SYNC, MNS, MAP multi-instance, PAN, SPP, BIP) is ✅ complete and is recorded per-version in `changelog.md` and the Classic feature-set version table below (bc-26 – bc-49).*
- [x] Improve detection of controller stall (NoReply / timeout) and offer automatic `bluetoothctl disconnect` prompt
  - [x] Fixed property monitor callback error when disconnecting from a device while monitoring is active
- [x] bc-14 Discovery filter options (`--uuid / --rssi / --pathloss`) in classic-scan, wire through `SetDiscoveryFilter` (docs updated)
- [x] bc-15 Native SDP via D-Bus (`Device1.GetServiceRecords` fast-path) before sdptool fallback
- [x] **Enhanced SDP Attribute Extraction (Phase 1)** – Extract additional SDP attributes:
  - [x] Service Record Handle (0x0000)
  - [x] Bluetooth Profile Descriptor List (0x0009) with UUIDs and versions
  - [x] Service Version (0x0300)
  - [x] Service Description (0x0101)
  - [x] Added `--debug` flag to `classic-enum` command
  - [x] Graceful fallback when connection fails but SDP succeeds (connectionless queries)
- [x] **Connectionless SDP Query with l2ping (Phase 2)** – Reachability verification before SDP:
  - [x] Implemented `discover_services_sdp_connectionless()` function with l2ping check
  - [x] Updated `discover_services_sdp()` to support optional `connectionless` parameter
  - [x] Added `--connectionless` flag to `classic-enum` CLI command
  - [x] Faster failure detection and better error messages for unreachable devices
  - [x] Backward compatible (default behavior unchanged)
- [x] **Basic Bluetooth Version Detection (Phase 3)** – Extract and display version information:
  - [x] Added `get_vendor()`, `get_product()`, `get_version()`, `get_modalias()` methods to `device_classic.py`
  - [x] Created `get_device_version_info()` method that aggregates version information
  - [x] Created `bleep/ble_ops/classic_version.py` module with version detection helpers
  - [x] Implemented `query_hci_version()` for local adapter HCI/LMP version query (no sudo required)
  - [x] Implemented `map_lmp_version_to_spec()` for LMP to Bluetooth spec version mapping
  - [x] Implemented `map_profile_version_to_spec()` for profile version to spec version mapping (heuristic)
  - [x] Added `--version-info` flag to `classic-enum` CLI command
  - [x] Dual-source extraction (Device1 properties + modalias fallback)
  - [x] Raw property preservation for offline analysis
- [x] **Enhanced SDP Analysis (Phase 4)** – Comprehensive SDP record analysis and version inference:
  - [x] Created `bleep/analysis/sdp_analyzer.py` module with `SDPAnalyzer` class
  - [x] Protocol analysis (RFCOMM, L2CAP, BNEP, OBEX, etc.) extraction and identification
  - [x] Advanced version inference engine with cross-referencing of profile versions
  - [x] Anomaly detection for version inconsistencies and unusual patterns
  - [x] Service relationship analysis grouping related services by profile
  - [x] Comprehensive reporting with human-readable and JSON output formats
  - [x] Added `--analyze` flag to `classic-enum` CLI command
  - [x] Integration with existing debug and version-info modes
- [x] **Debug Mode PBAP Command (bc-10)** – Interactive PBAP phonebook dumps in debug mode:
  - [x] Implemented `_cmd_pbap()` function in `bleep/modes/debug.py`
  - [x] Added command registration to `_CMDS` dictionary
  - [x] Updated help text with PBAP command documentation
  - [x] PBAP service detection from service map and SDP records
  - [x] Support for all CLI `classic-pbap` features (repos, format, auto-auth, watchdog, output)
  - [x] Database integration for PBAP metadata (if enabled)
  - [x] Comprehensive error handling with diagnostic messages
  - [x] Entry counting and file statistics display
  - [x] Updated documentation in `bl_classic_mode.md`
  - [x] Updated changelog and todo tracker
- [x] **Debug Mode Connectionless SDP Discovery** – Added `csdp` command for connectionless SDP queries:
  - [x] Implemented `_cmd_csdp()` function in `bleep/modes/debug.py`
  - [x] Added command registration to `_CMDS` dictionary
  - [x] Updated help text with csdp command documentation
  - [x] Connectionless mode with l2ping reachability check (matches CLI `--connectionless` flag)
  - [x] Configurable l2ping parameters (`--l2ping-count`, `--l2ping-timeout`)
  - [x] Detailed SDP record display with enhanced attributes
  - [x] Automatic service map generation from discovered records
  - [x] Error handling for unreachable devices with clear messages
  - [x] Updated documentation in `bl_classic_mode.md`
  - [x] Updated changelog
- [x] **Classic Integration Tests (bc-12)** – Comprehensive test suite for Classic Bluetooth functionality:
  - [x] Phase 1: Enhanced SDP feature tests (enhanced attributes, connectionless queries, version detection, comprehensive analysis)
  - [x] Phase 2: PBAP comprehensive tests (multiple repositories, vCard formats, auto-auth, watchdog, output handling, database integration)
  - [x] Phase 3: CLI command tests (classic-enum, classic-pbap, classic-ping)
  - [x] Phase 4: Debug mode command tests (cscan, cconnect, cservices, csdp, pbap)
  - [x] Phase 5: Error recovery & edge cases (reconnection, concurrent operations, timeout handling, partial service discovery)
  - [x] Created `tests/test_classic_cli.py` for CLI command tests
  - [x] Created `tests/test_classic_debug_mode.py` for debug mode tests
  - [x] Updated `tests/test_classic_integration.py` with comprehensive test coverage
  - [x] Updated documentation
- [x] bc-16 Helper `classic_rfccomm_open(mac, channel)` for generic RFCOMM sockets (pre-req for MAP/OPP)
- [x] bc-17 Lightweight in-process OBEX agent for PBAP authentication (`--auto-auth` flag)
- [x] bc-18 PBAP watchdog to auto-disconnect on stalled transfer (>8 s without progress)
- [x] bc-19 `classic_l2ping(mac, count=3)` helper using *l2ping* CLI to verify reachability before connect
- [x] bc-13 Update CHANGELOG & todo-tracker after completing Classic Bluetooth feature set
- [x] bc-20 RFCOMM data-exchange debug commands (`copen`, `csend`, `crecv`, `craw`):
  - [x] Extracted shared value-parsing utility to `debug_utils.py` (reused by BLE `write` and `csend`)
  - [x] Added `rfcomm_sock` field to `DebugState` (separate from `keepalive_sock`)
  - [x] `copen` – open/close/status of dedicated data RFCOMM socket
  - [x] `csend` – send raw data with format support (hex:/str:/file:/uint8:/etc.)
  - [x] `crecv` – receive data with timeout, hex dump, save-to-file options
  - [x] `craw` – interactive bidirectional RFCOMM session with background reader thread
  - [x] Registered all commands in dispatch table and help text
- [x] bc-21 Object Push Profile (`copp`) via BlueZ obexd D-Bus:
  - [x] `dbuslayer/obex_opp.py` – D-Bus layer (`opp_send_file`, `opp_pull_business_card`)
  - [x] `ble_ops/classic_opp.py` – operations layer with logging and service detection
  - [x] `copp send <file>` and `copp pull [dest]` debug commands
- [x] bc-22 Message Access Profile (`cmap`) via BlueZ obexd D-Bus:
  - [x] `dbuslayer/obex_map.py` – D-Bus layer (`MapSession` class with full API)
  - [x] `ble_ops/classic_map.py` – operations layer with logging and service detection
  - [x] `cmap` debug command with sub-commands: folders, list, get, push, inbox, props, read, delete
- [x] bc-23 Refactored value-parsing from `debug_gatt.py` into shared `debug_utils.py`
- [x] bc-24 Documented future expansion items not covered by this change (FTP, SYNC, MNS, BIP, SPP, PAN, L2CAP raw, CLI sub-commands)
- [x] bc-25 Updated `bl_classic_mode.md` with new command documentation and feature tracker

### OBEX Expansion Roadmap (v2.7.5 – v2.7.13+)

Planned path forward for Classic OBEX profile and transport augmentations.
All versions remain within the v2.7.x range.  BlueZ D-Bus API references
are in `workDir/BlueZDocs/org.bluez.obex.*.rst` and reference scripts in
`workDir/BlueZScripts/`.

| Phase | Version | Scope | BlueZ Interface / Bus | Reference Script(s) | bc-IDs |
|-------|---------|-------|-----------------------|----------------------|--------|
| 1 | v2.7.5 | OBEX FTP + transfer-poller dedup | `FileTransfer1` (session) | `ftp-client`, `list-folders`, `service-ftp.xml` | bc-26 – bc-29 |
| 2 | v2.7.6 | CLI `classic-opp`, `classic-map`, `classic-ftp` | — (CLI wiring only) | — | bc-30 – bc-32 |
| 3 | v2.7.7 | MAP MNS notification monitoring | `MessageAccess1` signals (session) | `map-client` | bc-33 – bc-35 |
| 4 | v2.7.8 | MAP multi-instance MAS selection | `Client1` `Channel` byte (session) | `map-client` | bc-36 |
| 5 | v2.7.9 | PAN networking | `Network1` + `NetworkServer1` (system) | `test-network`, `test-nap` | bc-37 – bc-40 |
| 6 | v2.7.10 | SPP serial port emulation | `ProfileManager1` + `Profile1` (system) | `test-profile`, `service-spp.xml` | bc-41 – bc-43 |
| 7 | v2.7.11 | SYNC profile | `Synchronization1` (session) | — | bc-44 – bc-46 |
| 8 | v2.7.12 | BIP (Basic Imaging, experimental) | `Image1` [experimental] (session), target `"bip-avrcp"` | — | bc-47 – bc-49 |
| 9 | v2.7.13+ | Raw OBEX over RFCOMM, L2CAP raw | N/A (protocol-level) | — | TBD |

#### Phase 1 – OBEX FTP (v2.7.5)

- [x] bc-26 Extract shared OBEX transfer poller into `dbuslayer/_obex_common.py`; refactor `obex_opp.py`, `obex_map.py`, `obex_pbap.py` to use it
- [x] bc-27 FTP D-Bus layer: `dbuslayer/obex_ftp.py` (`FtpSession` context manager wrapping `FileTransfer1`)
  - Session target: `"ftp"` (per `org.bluez.obex.Client.rst`)
  - Methods: `ChangeFolder`, `CreateFolder`, `ListFolder`, `GetFile`, `PutFile`, `CopyFile`, `MoveFile`, `Delete`
  - Note: `GetFile(targetfile, sourcefile)` — first arg is local, second is remote
  - Note: `PutFile(sourcefile, targetfile)` — first arg is local, second is remote
- [x] bc-28 FTP operations layer: `ble_ops/classic_ftp.py` (logging, service detection UUID `0x1106`, obs-DB)
- [x] bc-29 FTP debug command `cftp` (ls/cd/get/put/mkdir/rm/cp/mv) + constants (`FTP_UUID`, `FTP_UUID_SHORT`, update `OBEX_PROFILE_UUIDS`) + dispatch wiring in `debug.py`

#### Phase 2 – CLI Sub-Commands (v2.7.6)

- [x] bc-30 CLI `classic-opp` command (send / pull) mirroring `classic-pbap` pattern
- [x] bc-31 CLI `classic-map` command (folders / list / get / push / inbox) with `--type` filter per `MessageAccess.rst`
- [x] bc-32 CLI `classic-ftp` command (ls / get / put / mkdir / rm)

#### Phase 3 – MAP MNS Notification Monitoring (v2.7.7)

- [x] bc-33 MAP signal-based notification watch via `PropertiesChanged` on `Message1` objects (not a custom D-Bus server — BlueZ does not expose `SetNotificationRegistration`)
- [x] bc-34 `MapSession.get_supported_types()` and `list_filter_fields()` wrappers (per `MessageAccess.rst` `SupportedTypes` property and `ListFilterFields()` method)
- [x] bc-35 Debug `cmap monitor start|stop` + `cmap types` + `cmap fields` sub-commands + CLI `classic-map types|fields|monitor`

#### Phase 4 – MAP Multi-Instance (v2.7.8)

- [x] bc-36 `MapSession` gains optional `instance` parameter → `CreateSession` `Channel` byte; `list_mas_instances()` from SDP; all ops functions accept `instance` kwarg; `cmap instances` debug sub-cmd; `classic-map --instance` CLI flag

#### Phase 5 – PAN Networking (v2.7.9)

- [x] bc-37 Constants: `NETWORK_INTERFACE`, `NETWORK_SERVER_INTERFACE`, PAN UUIDs (`0x1115`, `0x1116`, `0x1117`)
- [x] bc-38 D-Bus wrapper `dbuslayer/network.py` (`NetworkClient` + `NetworkServer` on **system bus**; `Connect(role)` returns interface name, `Disconnect()`, properties: `Connected`, `Interface`, `UUID`; server `Register`/`Unregister`)
- [x] bc-39 Operations layer `ble_ops/classic_pan.py` + debug command `cpan` (connect/disconnect/status/server register|unregister)
- [x] bc-40 CLI `classic-pan` command (connect/disconnect/status/serve/unserve)

#### Phase 6 – SPP Serial Port Emulation (v2.7.10)

- [x] bc-41 D-Bus layer `dbuslayer/spp_profile.py`: `SppProfile(dbus.service.Object)` implementing `Profile1` (`NewConnection` delivers fd); `SppManager` for register/unregister via `ProfileManager1` at `/org/bluez` on **system bus**
- [x] bc-42 Debug command `cspp` (register/unregister/status); fd exposed as `state.rfcomm_sock` for `csend`/`crecv`; CLI `classic-spp` (register/unregister/status)
- [x] bc-43 Constants: `PROFILE_MANAGER_INTERFACE`, `PROFILE_INTERFACE` (SPP UUID already exists); operations layer `ble_ops/classic_spp.py`

#### Phase 7 – SYNC Profile (v2.7.11)

- [x] bc-44 D-Bus layer `dbuslayer/obex_sync.py` (`SyncSession`, target `"sync"`; methods: `SetLocation`, `GetPhonebook`, `PutPhonebook` per `Synchronization.rst`)
- [x] bc-45 Debug command `csync` (get/put/location) + CLI `classic-sync` subparser
- [x] bc-46 Operations layer `ble_ops/classic_sync.py`

#### Phase 8 – BIP Basic Imaging (v2.7.12)

- [x] bc-47 D-Bus layer `dbuslayer/obex_bip.py` (`BipSession`, target `"bip-avrcp"` per `Client.rst`; `Image1` is **[experimental]**; methods: `Get`, `Properties`, `GetThumbnail` per `Image.rst`)
- [x] bc-48 Debug command `cbip` (get/props/thumb) + CLI `classic-bip` subparser with runtime guard for experimental interface
- [x] bc-49 Operations layer `ble_ops/classic_bip.py`

#### Phase 9 – Raw OBEX & L2CAP (v2.7.13+ — design only)

- [x] bc-50 Design doc for raw OBEX framing over RFCOMM (bypassing obexd) → `bleep/protocols/obex_design.md`
- [x] bc-51 Design doc for L2CAP raw channel access via `socket.AF_BLUETOOTH` / `BTPROTO_L2CAP` → `bleep/protocols/l2cap_design.md`

#### Cross-cutting

- [x] Split `debug_classic_data.py` (1,192 lines) into focused sub-modules (v2.7.14):
  - `debug_classic_rfcomm.py` (~378 lines) — copen, csend, crecv, craw + helpers
  - `debug_classic_obex.py` (~646 lines) — copp, cmap, cftp, csync, cbip
  - `debug_classic_profiles.py` (~200 lines) — cpan, cspp
  - `debug_classic_data.py` (49-line re-export shim) — backward-compatible imports
  - Fixed `cmd_csync`/`cmd_cbip` signature bug (reversed params, non-existent `state.bdaddr`)

- [x] bc-52 Enrich `current_mapping` from `Dict[str, int]` to `Dict[str, Dict]` with full SDP record fields (v2.7.15):
  - `classic_connect.py` — builds enriched `svc_map` with all SDP record fields
  - `debug_classic.py` — `_ch()` helper, rewritten `cmd_cservices` (normal + detailed), updated `cmd_ckeep`/`cmd_csdp`/`cmd_pbap`
  - `debug_classic_rfcomm.py` — `_resolve_rfcomm_channel` updated for enriched dicts
  - `debug_pairing.py` — `post_pair_connect_classic` builds enriched dicts
  - `debug_connect.py` — info message updated for non-RFCOMM inclusion
  - `cli.py` — `classic-enum` summary updated

- [x] bc-53 Fix SDP parsing gap: XML parser & collision-safe svc_map (v2.7.16):
  - `classic_sdp.py` — replaced `browse --tree` with `browse --xml` in fallback chain
  - `classic_sdp.py` — new `_parse_xml_record()` / `_parse_browse_xml()` for structured XML parsing
  - `classic_sdp.py` — new `build_svc_map()` public helper with duplicate-key disambiguation
  - `classic_sdp.py` — D-Bus path no longer requires RFCOMM channel to accept results
  - All inline `svc_map` builders (`classic_connect.py`, `debug_classic.py`, `debug_classic_rfcomm.py`, `debug_pairing.py`, `cli.py`) replaced with shared `build_svc_map()`

- [x] bc-54 MediaPlayer optional property handling (v2.7.17):
  - `dbuslayer/media.py` — `_get_property()` distinguishes optional vs required props per BlueZ spec
  - `dbuslayer/media.py` — `get_name()` delegates to `_get_property()` for consistent handling
  - `core/observations.py` — `snapshot_media_player()` uses `GetAll` instead of individual getters

*(collapse / expand sections as items are completed)* 

## User Mode Implementation Tasks

- [x] **Core UI Implementation**
  - [x] Design simplified menu structure vs. debug mode
  - [x] Implement basic device discovery and selection flow
  - [x] Create characteristic interaction screens (read/write/notify)
  - [x] Build signal configuration UI components
  - [x] Implement error handling with user-friendly messages
- [x] **Backend Functionality**
  - [x] Create abstraction layer above debug mode operations
  - [x] Implement simplified device map visualization
  - [x] Build notification/signal capture configuration system
  - [x] Add export/import of device interactions
- [x] **Documentation**
  - [x] Create `docs/user_mode.md` guide with screenshots
  - [x] Add quick-start examples for common workflows
  - [x] Document UI navigation patterns
- [x] **Testing**
  - [x] Create test suite for UI functionality
  - [x] Validate against multiple device types

## Codebase Gap Analysis & Remediation Plan (2026-04-01) – SUBSTANTIALLY COMPLETE (reconciled 2026-07-22: Phases 1–5 done; only G-7.4 and G-7.5 remain deferred)

**Origin**: Exhaustive review of the entire `bleep/` codebase (163 Python modules, 58 documentation files), cross-referenced against `bleep/docs/changelog.md`, this tracker, and `workDir/BigMoves/README.bleep-bleep-mcp-augmentation-roadmap.md`. This section captures all discovered gaps, shortcomings, incomplete work, and documentation errors with a phased remediation plan.

**Methodology**: Static analysis of all `bleep/**/*.py` modules, grep for TODO/FIXME/HACK/PLACEHOLDER markers, comparison of `__all__` exports against actual imports, test coverage mapping (163 modules vs `tests/` import references), deprecated API usage audit, and documentation-to-code consistency checks.

---

### Category 1: Active Bugs and Broken References

#### G-1.1 `modes/test.py` calls non-existent adapter API

**Finding**: `bleep/modes/test.py` lines 478, 499, 509 call `self.adapter.is_powered()` and `self.adapter.is_discovering()`. The adapter class (`dbuslayer/adapter.py`) only exposes `get_powered()` and `get_discovering()` — the `is_*` names were removed during the v2.7+ API cleanup.

**Impact**: `bleep test` crashes with `AttributeError` whenever it reaches the adapter property check or discovery test.

**Reasoning**: This is a straightforward rename oversight. The rest of the codebase was migrated, but `modes/test.py` was missed. Grep confirms these are the **only** three occurrences of the old names across the entire `bleep/` tree.

**Fix**: Replace `is_powered()` → `get_powered()` and `is_discovering()` → `get_discovering()` in `modes/test.py`.

- [x] **G-1.1** Fix stale `is_powered()`/`is_discovering()` calls in `modes/test.py`

#### G-1.2 `identify_uuid()` space-padding in `uuid_utils.py`

**Finding**: `bleep/ble_ops/common/uuid_utils.py` line 84 adds `target.ljust(32, " ")` to `canonical_targets`, injecting space-padded strings into a set meant for hex comparison.

**Impact**: This padded form will never match any real UUID (hex strings don't contain spaces). It wastes a set entry on every call and could cause confusion if anyone iterates `canonical_targets` for display or logging. The actual matching still works because other branches add the correct hex forms.

**Reasoning**: Likely a debugging artifact or misguided attempt to normalize length. The set already receives correct-length hex forms from the 16-bit, 32-bit, and 128-bit branches. The space-padded entry serves no purpose.

**Fix**: Remove the `canonical_targets.add(target.ljust(32, " "))` line.

- [x] **G-1.2** Remove space-padding in `identify_uuid()` (`ble_ops/common/uuid_utils.py`)

#### G-1.3 `dbuslayer/__init__.py` `__all__` lists unexported names

**Finding**: `bleep/dbuslayer/__init__.py` `__all__` lists `bluez_monitor`, `recovery`, `agent_io`, `pairing_state`, `bond_storage` but the file only imports `system_dbus__bluez_adapter`, `system_dbus__bluez_signals`, `system_dbus__bluez_generic_agent`, `system_dbus__bluez_agent_user_interface`, `Characteristic`, `Descriptor`. The five listed-but-not-imported names have no `__getattr__` lazy loader — only `system_dbus__bluez_device__low_energy` does.

**Impact**: `from bleep.dbuslayer import *` silently fails to export those five modules. Direct `from bleep.dbuslayer import bluez_monitor` raises `ImportError`. Code that uses the fully-qualified path (`from bleep.dbuslayer.bluez_monitor import ...`) works fine.

**Reasoning**: `__all__` was expanded to document intended scope without wiring up the imports. This is misleading to anyone inspecting the package API.

**Fix**: Either add `__getattr__` lazy loaders for the five modules (matching the `device_le` pattern) or remove them from `__all__`.

- [x] **G-1.3** Fix `dbuslayer/__init__.py` `__all__` vs actual imports

#### G-1.4 `__main__.py` missing for `python -m bleep`

**Finding**: `bleep/docs/cli_usage.md` line 25 explicitly notes: "The documentation previously showed `python -m bleep`, but this won't work because the package doesn't have a `__main__.py` file." The standard Python convention (`python -m <package>`) does not work.

**Impact**: User friction. `python -m bleep.cli` works, but `python -m bleep` is the expected pattern (matching `python -m pytest`, `python -m pip`, etc.).

**Reasoning**: A `__main__.py` containing `from bleep.cli import main; import sys; sys.exit(main())` would make `python -m bleep` behave identically to `python -m bleep.cli`. When no subcommand is given, `args.mode` is `None`, which falls through to the `else` branch at `cli.py:2572` and launches the interactive REPL — same as today. All flags and subcommands work identically since both paths invoke the same `main()`. The `bleep/__init__.py` side-effects (signal patching, log init) are triggered either way because importing the package always runs `__init__.py`.

**Fix**: Create `bleep/__main__.py` (3 lines). Update `cli_usage.md` to remove the caveat note.

- [x] **G-1.4** Add `bleep/__main__.py` for `python -m bleep` support
- [x] **G-1.4b** Update `cli_usage.md` to remove the "won't work" caveat

#### G-1.5 Orphaned bytecode without source

**Finding**: `bleep/callbacks/examples/__pycache__/auto_pair_accept.cpython-311.pyc` exists with no corresponding `auto_pair_accept.py` source file.

**Impact**: None at runtime (Python won't load `.pyc` without being asked), but it pollutes the tree and suggests a deleted file that was never cleaned up.

**Fix**: Delete the orphaned `.pyc` file.

- [x] **G-1.5** Delete orphaned `auto_pair_accept.cpython-311.pyc`

---

### Category 2: Incomplete Features (Explicitly Marked Elsewhere, Consolidated Here)

#### G-2.1 Endpoint-based transport acquisition — INCOMPLETE

**Cross-ref**: "Fix Endpoint-Based Transport Acquisition (2026-03-21) – INCOMPLETE" section in this tracker (line ~827).

**Finding**: `BleepMediaEndpoint` registration (Phase 2) does not function when PipeWire/PulseAudio is running. BlueZ never calls `SelectConfiguration`/`SetConfiguration` because the audio daemon claims all SEPs first. The `--direct` mode works only when the audio daemon is stopped.

**Impact**: `audio-play` without `--direct` or `--system` is non-functional in common desktop configurations.

**Reasoning**: This is an architectural contention issue between BLEEP and the system audio daemon. Deferred in favor of `--system` flag approach that works *with* the daemon. Further investigation into BlueZ endpoint selection ordering and PipeWire endpoint contention is needed. May require BLEEP to be the only registered endpoint.

**Status**: Deferred — documented here for tracking.

**Live behaviour confirmed (2026-07-22)** against PLT V8200 (`F4:B6:88:0B:90:22`, PipeWire running): the endpoint-registration path detects contention, registers the BLEEP endpoint, cycles the connection, then reports that BlueZ did not invoke `SetConfiguration()` on the BLEEP endpoint (PipeWire won the AVDTP `a2dp_select_eps` race) — and emits actionable guidance (inspect backends, retry with `--direct`). i.e. the contention preflight + guidance work correctly and fail gracefully; full acquisition still requires `--direct` with the daemon stopped. No hang/crash.

#### G-2.2 `audio_codec.py` GStreamer appsrc recording placeholder — ✅ IMPLEMENTED (2026-07-22)

**Finding (original)**: `bleep/ble_ops/audio/audio_codec.py` contained a placeholder comment block for the recording path that reads from a transport FD and feeds data to GStreamer's `appsrc`. No actual implementation existed.

**Fix (2026-07-22)**:
- Replaced the placeholder in `_decode_with_python_bindings()` with a real appsrc feeder: transport FD set non-blocking, `GLib.io_add_watch` pumps `os.read` → `appsrc` `push-buffer`, EOS on duration deadline / FD close (EOF) / HUP/ERR.
- Extracted the per-iteration pump into the GStreamer-agnostic module helper `_pump_fd_to_sink()` (unit-testable without GStreamer). **Drain-first** semantics: reads pending data before honouring HUP so a hang-up delivered alongside buffered data (poll `IN|HUP`) does not drop the tail (bug caught in triple-pass review via a live `GLib.io_add_watch` run).
- Threaded `duration` end-to-end: `record_audio` → `decode_audio_stream` → `_decode_with_python_bindings`. CLI `--duration` already wired.
- **Tests**: `tests/test_audio_codec_pump.py` (8 tests). Runtime `GLib.io_add_watch` integration validated on `os.pipe()` (drain-first confirmed: buffered tail delivered before EOS).

**Deterministic E2E validation (2026-07-22)**: Added `tests/test_audio_codec_decode_integration.py` (2 tests) which drives the *real* decode path end-to-end with GStreamer — `AudioCodecDecoder.decode_audio_stream` → `_decode_with_python_bindings` → `_pump_fd_to_sink` appsrc feeder → parser/decoder/`wavenc` — by streaming an encoded payload through an `os.pipe()` exactly as a live MediaTransport FD would. MP3 is used as the loopback codec (`lamemp3enc` → pipe → `mpegaudioparse ! mpg123audiodec`) because it exercises the identical, codec-independent feeder/appsrc/EOS/duration machinery while the A2DP-mandatory SBC GStreamer elements are absent on the host (see blocker below). Both the FD-close (`duration=None`) EOS path and the `duration` timebox path are asserted to terminate and produce a valid WAV. The module skips cleanly when the required GStreamer stack is unavailable.

**Two latent decode-path defects found and fixed while building the E2E test** (neither was reachable by the earlier isolated `_pump_fd_to_sink` unit tests, and neither codec pipeline had ever actually run end-to-end):
- **`bus_message` arity (hang)** — both the encode (`_encode_with_python_bindings`) and decode (`_decode_with_python_bindings`) handlers were declared `def bus_message(bus, message, user_data)` but connected via `bus.connect("message", bus_message)`, which invokes handlers as `(bus, message)`. Every emission — including **EOS** — raised `TypeError` and was dropped, so `mainloop.run()` never returned (the record/decode loop hung until an external timeout). Fixed to two-argument handlers in both paths.
- **Stale `mp3parse` element** — the MP3 decode pipeline hard-coded `mp3parse`, removed from modern GStreamer (renamed `mpegaudioparse`); the pipeline failed to build on any current GStreamer. Fixed to `mpegaudioparse`.

**RTP encapsulation fix (2026-07-22)** — plan-review finding validated against research: A2DP transport FDs deliver **RTP-encapsulated** SBC (RFC draft-ietf-payload-rtp-sbc §6 → A2DP v1.2 §4.3.4; corroborated by `bt_manager.read_transport` "…has all RTP encapsulation removed", `a2dp-alsa`, and GStreamer's `a2dpsrc`), **not** raw SBC frames. The original SBC decode pipeline (`appsrc ! sbcparse ! sbcdec`) would therefore never decode a real transport FD. Fixed:
- SBC decode pipeline is now `appsrc[caps=application/x-rtp,media=audio,payload=96,clock-rate=<freq>,encoding-name=SBC] ! rtpsbcdepay ! sbcparse ! sbcdec ! audioconvert ! audioresample ! wavenc ! filesink`.
- `appsrc` caps are set (required for `rtpsbcdepay` negotiation); `clock-rate` is derived from the negotiated SBC config via new helper `_sbc_rtp_clock_rate()` (config octet-0 sampling-frequency nibble; default 44100 Hz).
- `configuration` threaded `record_audio` → `decode_audio_stream` → `_decode_with_python_bindings`.
- Packet framing verified compatible: the A2DP transport FD is an L2CAP `SOCK_SEQPACKET` socket, so each read is one RTP packet, and the feeder pushes one buffer per read — exactly what `rtpsbcdepay` expects.
- `rtpsbcdepay`/`rtpsbcpay` ship in the already-installed `gstreamer1.0-plugins-good`; only `sbcenc`/`sbcdec` needed `gstreamer1.0-plugins-bad` (now installed).

**Deterministic SBC-over-RTP loopback (2026-07-22)**: `tests/test_audio_codec_decode_integration.py::test_sbc_rtp_loopback_decode_produces_valid_wav` now proves the **exact live decode path** without hardware — real RTP-SBC packets (`sbcenc ! rtpsbcpay`, pulled per-packet) delivered over a `SOCK_SEQPACKET` socketpair (identical framing to a BlueZ media transport) into the real `decode_audio_stream` SBC pipeline (`rtpsbcdepay ! sbcparse ! sbcdec`), asserting a valid WAV with >0.3 s of audio. Plus `test_sbc_rtp_clock_rate_from_config` unit-tests the frequency helper. This closes the RTP-depay coverage gap the MP3 loopback could not (raw MPEG, no RTP).

**Host codec note (RESOLVED 2026-07-22)**: SBC GStreamer elements (`sbcenc`/`sbcdec`) live in `gstreamer1.0-plugins-bad`; `rtpsbcdepay` in `gstreamer1.0-plugins-good`. `bleep --check-env` / `--diagnose-audio` now include a **GStreamer Codec Plugins** section (`core/preflight.py::_check_gstreamer_codec_plugins`, `PreflightReport.codec_plugins` + `can_record_sbc`) that probes the element factories each pipeline needs, grouped by capability (SBC/MP3/AAC decode + encode + core), names the specific missing element, and prints an OS-specific install hint. This closes the silent-failure footgun where SBC capture failed at runtime with the plugin absent. Tests: `tests/test_preflight.py::TestGstreamerCodecPlugins` (6). NB: the check surfaced that this host lacks `avenc_sbc`/`avdec_aac` (`gstreamer1.0-libav`), so SBC/AAC **playback** encode is unavailable here — a real, previously-invisible gap.

**HFP/HSP microphone capture (NEW 2026-07-22)**: A2DP is output-only; the remote microphone is a SCO stream exposed only on an HFP/HSP card profile. `audio-record --hfp` (`ble_ops/audio/audio_system.py::system_record_hfp`) switches the device's card to `handsfree-head-unit`/`headset-head-unit`, records the SCO source via host audio tools, then restores the original profile (`--keep-profile` to skip). BlueALSA `sco` source PCMs are addressed directly. **Live E2E PASS** (PLT V8200): switched `a2dp-sink-sbc`→`headset-head-unit`, recorded `bluez_input.…headset-head-unit`, valid 5.93 s WAV with real mic audio, profile restored to `a2dp-sink-sbc`, `rc=0`. Tests: `tests/test_audio_hfp_capture.py` (18). This is the microphone-capture counterpart to the A2DP music path — the "next capability frontier" noted in the prior recommendation.

**Hardware caveat (RESOLVED 2026-07-22 — live E2E acceptance complete)**: this decode/record path only applies when audio flows **into** BLEEP (peer is an **A2DP source**). The live target PLT V8200 is an A2DP **sink**, so it cannot exercise this path; live acceptance was instead performed against DESKTOP-1APRSIB (`Audio Source 0x110a`) streaming while BLEEP owned the sink transport (PipeWire paused). Requirements confirmed satisfied: (a) SBC codec plugin installed (`gstreamer1.0-plugins-bad`), (b) A2DP-source peer streaming, (c) RTP-encapsulation handled — the `rtpsbcdepay` element now precedes the SBC parser and `application/x-rtp` caps drive it. The MP3 loopback validated the feeder/EOS/duration stages; the deterministic SBC-over-RTP loopback validated the SBC + RTP-depay stages; and the live capture (see G-2.2 live E2E PASS below) validated the full transport-acquisition + decode chain against real BlueZ hardware.

**Live E2E attempt (2026-07-22, DESKTOP-1APRSIB A2DP source, PipeWire paused)** — surfaced and fixed two further latent bugs that had never run against real BlueZ, plus a connection-orchestration gap that was subsequently fixed and validated live (see RESOLVED item below):
- **`Media1.RegisterEndpoint` object-path marshalling (fixed)**: `BleepMediaEndpoint.register()`/`unregister()` passed the endpoint path as a bare `str`, so dbus-python sent signature `sa{sv}` and BlueZ rejected it with `UnknownMethod` (expects `oa{sv}`). Wrapped in `dbus.ObjectPath`. After the fix, endpoint registration **succeeds live** (`[+] Registered BLEEP endpoint … UUID=0000110B` A2DP Sink) — the first time this path has worked against real BlueZ. Regression test: `tests/test_media_helpers.py::test_register_endpoint_marshals_object_path`.
- **`log.py` fatal legacy-path cleanup (fixed)**: a prior `sudo bleep` run left root-owned symlinks at `/tmp/bti__logging__*.txt` → `/root/.local/share/bleep/logs/`. In sticky `/tmp` the `user` account cannot `unlink()` them (EPERM), and the fallback `touch()` followed the symlink to an unwritable target and re-raised, crashing **every** `bleep` import (and the whole test suite). Hardened the legacy-symlink block so legacy-compat bookkeeping is fully non-fatal (real logging uses the per-user `_INTERNAL_PATHS` regardless).
- **RESOLVED (2026-07-22) — A2DP source-role connection orchestration**: `_acquire_via_endpoint()` → `_cycle_device_connection()` does `Device1.Disconnect()` then `Device1.Connect()` to force `a2dp_discover` to re-select BLEEP's SEP. For a remote A2DP *source* (a Windows PC) the Linux-initiated `Connect()` is refused (`br-connection-create-socket` / `br-connection-unknown`) because the source must *originate* the link itself. **Fix**: `_cycle_device_connection()` now catches the connection-family DBus error (matched against `_REMOTE_INITIATE_ERROR_HINTS`), swallows it, and enters a "wait for remote-initiated reconnect" mode — blocking up to `_REMOTE_RECONNECT_TIMEOUT` (30 s) for the peer to re-establish the link on its own. Any non-connection DBus error still propagates. The sink path is unchanged (Connect() succeeds and the wait is the original 10 s). This is **additive** and preserves the working headphone/speaker sink flow. Unit tests: `tests/test_media_helpers.py::{test_cycle_reconnect_normal_sink_path, test_cycle_reconnect_source_waits_for_remote, test_cycle_reconnect_source_timeout_raises, test_cycle_reconnect_non_connection_error_propagates}`.
  - **LIVE E2E PASS (2026-07-22, DESKTOP-1APRSIB A2DP source, PipeWire paused)**: after the fix, `bleep audio-record 98:3B:8F:EF:FE:EC … --force-endpoint` produced a valid recording end-to-end. Sequence observed: Linux `Connect()` refused → remote-reconnect wait engaged → source re-initiated → `SetConfiguration transport=/org/bluez/hci0/dev_98_3B_8F_EF_FE_EC/fd7` → transport acquired (`fd=18`, read_mtu=672) → SBC/RTP-depay decode → **2.6 MB WAV, RIFF 16-bit stereo 44100 Hz, 15.13 s, RMS 4984 / peak 31905 (real audio, not silence)**, exit `rc=0`. This is the first successful live capture from a remote A2DP source and closes the codec-record path (G-2.2) for both deterministic loopback and live hardware.

**Reasoning**: The `--system` recording path via `arecord`/`parecord` remains available as an alternative (and was also fixed for PipeWire hosts — see the `--system` bug fix above).

#### G-2.3 `service.py` signal handling ✅ Complete

**Finding**: `bleep/dbuslayer/service.py` previously had log-only signal placeholders.

- [x] `Service._props_changed` now updates local state (`primary`, `includes`, `handle`) on `GattService1` `PropertiesChanged`
- [x] `Service.on_property_changed()` callback registration for callers
- [x] `signals.py` routes `GATT_SERVICE_INTERFACE` property changes to the owning Service object
- [x] Module docstring updated (no longer "placeholder")
- [x] 6 mock-based tests for signal dispatch path

#### G-2.4 `device_le.py` legacy compatibility stubs

**Finding**: Lines 1668-1691 in `bleep/dbuslayer/device_le.py` contain Phase-4 legacy stubs including an empty `register()` method and connection signalling no-ops. The `interfaces_added` callback (line 2077) only logs, doesn't update caches.

**Impact**: External callers expecting monolith-era device registration or real-time interface tracking get silent no-ops.

---

### Category 3: Empty/Placeholder Packages

#### G-3.1 `bleep/gatt/` — Future migration namespace

**Finding**: Contains only `__init__.py` with guarded imports of `service`, `characteristic`, `descriptor` that all resolve to `None` because no `.py` modules exist in this directory. The real implementations remain in `bleep/dbuslayer/`.

**Reasoning**: Declared as a future migration target. No runtime impact, but the package's existence may mislead developers into thinking GATT wrappers live here.

**Decision needed**: Migrate the implementations here, or remove the package and document `bleep.dbuslayer` as the canonical home.

- [x] **G-3.1** ~~Decide on `bleep/gatt/`~~ — **Decision: keep as future migration target.** When GATT wrappers are mature enough to decouple from `dbuslayer/`, move `service.py`, `characteristic.py`, `descriptor.py` here. No action needed now.

#### G-3.2 `bleep/mesh/` — Partially implemented

**Finding**: `agent` and `provisioning` modules listed in `__all__` don't exist (import-guarded to `None`). Only `proxy_solicitation` is a real module.

**Reasoning**: Mesh support is early-stage. The package should exist but `__all__` should only list what's real.

- [x] **G-3.2** Restructured `bleep/mesh/__init__.py` — `__all__` now lists only `proxy` (the real module); planned `agent`/`provisioning` documented in docstring only

#### G-3.3 `bleep/protocols/` — Design docs only

**Finding**: Package docstring states "Contains design documentation only. Implementation is planned for a future version." Only `l2cap_design.md` and `obex_design.md` exist — no Python code.

**Reasoning**: Acceptable for design-phase packages, but should be noted in `docs/README.md` to avoid confusion.

- [x] **G-3.3** Note `protocols/` as design-only in docs index

---

### Category 4: Deprecated/Legacy Code

#### G-4.1 `bluetooth_uuids.py` still imported by bleep-mcp (BC-003)

**Finding**: Module emits `DeprecationWarning` on import, directing to `bleep.bt_ref.uuids`. No internal `bleep/` code imports it, but `bleep-mcp/bleep_mcp/resources/reference_data.py` has 3 import sites that still use it.

**Reasoning**: Coordination item between `bleep/` and `bleep-mcp/`. Once `bleep.bt_ref.uuids` has full export parity, the MCP imports should migrate.

**Cross-ref**: BC-003 in `workDir/BigMoves/README.bleep-bleep-mcp-augmentation-roadmap.md`.

- [x] **G-4.1** Verify `bleep.bt_ref.uuids` export parity then migrate bleep-mcp imports (BC-003) — imports migrated, `bluetooth_uuids.py` deleted

#### G-4.2 `compat.py` — deprecated, zero internal callers

**Finding**: Entire module warns on import. No `bleep/` code imports it. Exists only for hypothetical external scripts.

- [x] **G-4.2** `compat.py` removed in v2.8.1 (was marked for deletion since v2.6)

#### G-4.3 Legacy shim modules (`bluetooth_utils.py`, `bluetooth_constants.py`, `bluetooth_exceptions.py`)

**Finding**: Three one-line `from .X import *` files in `bt_ref/`. No internal importers.

- [x] **G-4.3** `bluetooth_utils.py`, `bluetooth_constants.py`, `bluetooth_exceptions.py` shims removed in v2.8.1

#### G-4.4 Duplicate D-Bus error mapping (B5 consolidation)

**Finding**: `core/error_handling.py` lines 55-61 document three overlapping error mapping systems: `decode_dbus_error()`, `evaluate__dbus_error()`, and `BlueZErrorHandler.ERROR_MESSAGES`. Plus `bt_ref/error_map.py` has its own table marked "DEPRECATED as primary source of truth."

**Impact**: Tables may diverge, producing inconsistent error codes/messages depending on which path handles the error.

**Reasoning**: The B5 consolidation TODO is open and well-documented in-code. The work is to refactor callers of the deprecated paths to use `decode_dbus_error()` as the single source of truth, then remove the duplicates.

- [x] **G-4.4** Complete B5 D-Bus error mapping consolidation — `evaluate__dbus_error` now delegates to `decode_dbus_error()`, `bt_ref/error_map.map_dbus_error` renamed to `classify_dbus_error` (alias kept), `DBUS_ERROR_MAP` aligned with canonical decoder, cross-system consistency tests added

---

### Category 5: Test Coverage Gaps

#### G-5.1 Majority of modules lack direct test coverage

**Finding**: Of 163 Python modules, only ~30 are directly referenced by any test file in `tests/`. The gap includes entire subsystems:

| Subsystem | Key untested modules |
|-----------|---------------------|
| `ble_ops/audio/` | All 10 modules (amusica, audio_recon, audio_codec, audio_system, etc.) |
| `ble_ops/classic/` | map, pbap, sdp, opp, ftp, pan, spp, rfcomm, ping, version (only `connect` is referenced) |
| `ble_ops/common/` | `uuid_utils`, `modalias`, `structural` |
| `dbuslayer/` | device_le, device_classic, device, manager, service, media_stream, media_browse, all obex_*, bond_storage, pin_brute, etc. |
| `core/` | config, preflight, metrics, utils |
| `callbacks/` | All |
| `signals/` | capture_config, router, integration, cli |
| `modes/` | All 30+ mode files except aoi, debug, media (partial) |

**Reasoning**: Many of these modules require D-Bus/BlueZ at runtime, which makes pure unit testing hard. However, mock-based unit tests for the non-D-Bus logic (parsing, formatting, data structures, error handling) are feasible and valuable.

**Note**: Some modules get indirect coverage through CLI integration tests (`test_classic_cli.py` runs `bleep` as a subprocess), but this is brittle and doesn't validate internal logic paths.

- [x] **G-5.1a** Created `tests/conftest.py` with `MockAdapter`, `MockDeviceInfo`, `dbus_stub`, and `glib_stub` fixtures
- [x] **G-5.1b** 23 tests for `uuid_utils.py` — `identify_uuid` (16/32/128-bit, BT SIG vs custom, edge cases) and `match_uuid` (exact, partial, case-insensitive, empty)
- [x] **G-5.1c** 18 tests for `core/preflight.py` — `DeviceState`, `PreflightReport`, `check_device_state`, `require_adapter`, `_check_bluetooth_tools`, `_check_bluez_version`, `_check_bluetooth_config`, `run_preflight_checks` caching
- [x] **G-5.1d** 14 tests for `ble_ops/classic/map.py` — `normalize_bmessage` (LF→CRLF, LENGTH recalc, multi-block, edge cases) and `_normalize_for_push` (temp-file round-trip)
- [x] **G-5.1e** 12 tests for `callbacks/base.py` — ABC enforcement, `execute` dispatch, `on_load`/`on_unload` lifecycle, class attribute defaults
- [x] **G-5.1f** 18 tests for `analysis/sdp_analyzer.py` — empty records, protocol detection (RFCOMM/L2CAP/OBEX/BNEP), profile analysis, version inference with confidence, anomaly detection, report generation
- [x] **G-5.1g** 14 mock-based tests for `dbuslayer/service.py` + `device_classic.py` — `Service.__init__`/`get_handle`/`discover_characteristics`, `device_classic` state queries/pair/connect with D-Bus mocks

---

### Category 6: Documentation Gaps and Errors

#### G-6.1 `cli_usage.md` — `python -m bleep` caveat

**Cross-ref**: G-1.4 above. Once `__main__.py` is added, update the docs.

#### G-6.2 `bl_classic_mode.md` bc-01 tracker stale

**Finding**: Section 6 "Temporary Classic-Feature TODO Tracker" shows bc-01 as "pending" while most other items are completed. Appears to be outdated.

- [x] **G-6.2** Marked bc-01 as ✅ completed in `bl_classic_mode.md` (research fully realized in implementation)

#### G-6.3 `network_capability_plan.md` / `network_capability_summary.md` drift

**Finding**: These design docs describe Phases 2-5 as "Planned" but `bl_classic_mode.md` already documents working `classic-pan`. The plan docs may be partially superseded.

- [x] **G-6.3** Updated `network_capability_plan.md` and `network_capability_summary.md` — Phase 1 + 1b (classic-pan) complete; Phases 2-5 marked as future enhancements; manual verification with real PAN device recommended

#### G-6.4 `mainloop_architecture.md` — "Design document, not yet implemented"

**Finding**: Line 4 states "Status: Design document — not yet implemented." This is accurate but the doc doesn't cross-reference the FW items (FW1/F1/F3) that track the actual work.

- [x] **G-6.4** Added "Related Work Items" table to `mainloop_architecture.md` cross-referencing FW1, F1, F3 from todo_tracker

#### G-6.5 `observation_db_schema.md` — `protocol_descriptors` "Reserved for future use"

**Finding**: Column exists in schema v10, documented as reserved. `observations.py` has the column in CREATE TABLE and migration SQL, but sets it to `None` in most code paths. Some population logic exists at lines 1035-1068 but appears to be partial.

- [x] **G-6.5** Populated `protocol_descriptors` from SDP attribute 0x0004 — all three parsers (D-Bus XML, sdptool XML, sdptool text) now extract full ProtocolDescriptorList

---

### Category 7: Roadmap Items (from augmentation-roadmap.md, not tracked elsewhere)

These items from `workDir/BigMoves/README.bleep-bleep-mcp-augmentation-roadmap.md` are **not yet tracked** in this file. Added here for completeness:

- [x] **G-7.1** (S4) `_classify_le()` and `_classify_dual()` now consume `LE_ADVERTISING_DATA` evidence at STRONG weight — scan-only devices with beacon/CDP/service-data heuristics classify as `le` instead of `unknown`
- [x] **G-7.2** (S5) Vendor UART UUIDs (`FFE0`, `FFE1`, `FFF0`, `FFF1`, Nordic UART) elevated from WEAK to STRONG evidence; reasoning output updated
- [x] **G-7.3** (S9) `upsert_device()` now tracks `rssi_min`/`rssi_max` via `MIN()`/`MAX()` SQL; scan path seeds both values; manufacturer data selects longest payload instead of first entry
- [x] **G-7.4** (B1-B4) Blind spots closed — see **G-7.4 Implementation** below. (a) Advertised Classic-profile UUIDs now carry `ground_truth=False` / `source_kind="advertised"` and a passive verdict from them reports `evidence_source="heuristic"` (never `measured_*`); (b) the classifier's `cached` / `evidence_source` are surfaced in the AoI report (were model/DB-only); (c) Find My / beacon manufacturer-data (iBeacon, Apple Continuity) is now consumed via the shared dissector as STRONG LE evidence, so beacon-only devices classify as `le` instead of `unknown` (`fcf1`/service-data already handled by G-7.1 + G-7.5).
- [x] **G-7.5** (3.1) Advertisement dissection — parse `ServiceData`, `ManufacturerData`, and `AdvertisingData` into structured fields with two-source (BT SIG + vendor/community) attribution, lossless raw-hex + printable-ASCII preservation, and protocol decoders (iBeacon, Eddystone, Apple Continuity TLVs). See **G-7.5 Implementation** below.
- [x] **G-7.6** (BC-001) Extracted shared `BT_SIG_BASE_UUID` / `BT_SIG_BASE_UUID_NODASH` into `bt_ref/constants.py`; `uuid_utils.py` and `uuid_translator.py` now import from the canonical source (also fixed pre-existing truncation bug in `BASE_UUID__BLUETOOTH`)

**Note**: BC-001 numeric values are currently correct and aligned between the two files. The risk is duplication drift, not a current bug.

---

### G-7.5 Implementation — Advertisement Dissection (accepted 2026-07-23)

**Goal**: Turn the raw `ManufacturerData` / `ServiceData` / `AdvertisingData` blobs (currently stored as hex only) into structured, attributed, human-readable fields — **without ever discarding captured bytes**. Advertisements sometimes carry clear text (e.g. some Bluetooth headsets embed a printable name/model), so every entry preserves both raw hex and a printable-ASCII rendering.

**Self-containment constraint**: `bleep/` must own and maintain its reference material. Like the existing BT SIG updater (`bt_ref/update_ble_uuids.py` → committed `bt_ref/uuids.py`), a new vendor/community updater pulls from a public source and writes a committed in-package module. `workDir/` is a dev-only bootstrap convenience and is **never** a runtime dependency.

**Components**:

1. `bleep/analysis/adv_dissect.py` — pure, dependency-light dissector.
   - `dissect_advertisement(manufacturer_data=None, service_data=None, service_uuids=None, advertising_data=None) -> dict`.
   - Two-source attribution: BT SIG tables (`bt_ref.uuids`: company identifiers, member/service UUIDs, AD types) **plus** vendor/community specs (`bt_ref.vendor_adv_specs`).
   - Lossless: every entry includes `raw_hex` and `ascii` (printable-ASCII, non-printable → U+FFFD, reusing the existing `format_hex_ascii` convention).
   - Registry of protocol decoders (iBeacon, Eddystone URL/UID/TLM, Apple Continuity TLV split). Graceful degradation: a decoder failure never drops the raw entry.

2. `bleep/bt_ref/update_vendor_specs.py` — vendor/community spec updater (mirrors `update_ble_uuids.py`).
   - Primary source: public GitHub repo `BLESPloit/device-library` (manifests enumerated via the git-tree API, fetched via `raw.githubusercontent.com`).
   - Secondary source: `--local-path <checkout>` (used once in this dev env to bootstrap).
   - Cache fallback: `bt_ref/vendor_specs_cache.json`; final fallback is the committed generated module.
   - Emits committed `bleep/bt_ref/vendor_adv_specs.py`.

3. `bleep/bt_ref/vendor_adv_specs.py` — **committed** generated reference module (service-data UUID16, service UUID16/128, company-id, manufacturer-data prefix, and full `SPECS` metadata).

4. Scanner wiring (`ble_ops/le/scan.py`) — additive `adv_dissection` block attached to the persisted `decoded` payload; no schema change (compute-on-read/enrich).

5. Classifier (`analysis/device_type_classifier.py`) — **relabel-only** correction of misattributed beacon/service-data UUIDs (see corrections table below), sourced from the shared authoritative map so the classifier and dissector cannot drift. Evidence type/weight unchanged → classification decisions preserved.

6. AoI report (`analysis/aoi_analyser.py`) — new "Advertisement Dissection" section rendering attributed entries with raw hex + ASCII.

7. Docs: new `bleep/docs/adv_dissection.md` (design + "Known UUID attribution corrections"); cross-reference note in `device_type_classification.md`; `changelog.md` entry.

8. Tests: `tests/test_adv_dissect.py` (iBeacon, Eddystone, Apple Continuity, clear-text headset payload, malformed input, lossless invariants, corrected UUID labels).

**Known UUID attribution corrections** (triple-pass review vs `bt_ref/uuids.py` SIG data + device-library manifests). The prior `_BEACON_SERVICE_DATA_UUIDS` heuristic labels were misattributed:

| UUID (16-bit) | Old label | Authoritative owner (SIG member) | Corrected label |
|---|---|---|---|
| `FCF1` | `find_my_beacon` | Google LLC | `google_nearby` (device-library: Google Nearby) |
| `FE0F` | `exposure_notification_v1` | Signify Netherlands B.V. (Philips Hue) | `signify_hue` |
| `FD6F` | `exposure_notification_v2` | Apple/Google Exposure Notification | `exposure_notification` |
| `FE05` | `microsoft_cdp` | CORE Transport Technologies NZ Limited | `core_transport_nz` |
| `FCC0` | (n/a) | Xiaomi Inc. (community: Google Nearby) | `xiaomi` |
| `FEAA` | (n/a) | Google LLC | `eddystone` (protocol) |
| `FE2C` | (n/a) | Google LLC | `google_fast_pair` (protocol) |

Note: true Microsoft CDP is company-id `0x0006` in ManufacturerData (device-library "Microsoft Nearby"), not a service-data UUID; the classifier's separate `FE05`-in-advertised-UUIDs CDP heuristic is corrected accordingly. Where SIG and community sources conflict (e.g. `FCC0` = Xiaomi per SIG vs Google Nearby per device-library), the authoritative label follows SIG and the community grouping is retained as a non-destructive `vendor_hint`.

**Acceptance criteria**:
- No captured byte is lost: `raw_hex` round-trips to input bytes for every entry; printable ASCII surfaced.
- Attribution never raises on malformed/short/empty data (returns structured entry with raw preserved).
- `vendor_adv_specs.py` is committed and importable with zero network/`workDir` dependency at runtime.
- Classifier decisions unchanged (relabel-only); corrected labels documented.
- Full test suite green; new tests cover the above invariants.

**Follow-up — CLI `db show` surfacing (accepted 2026-07-24)**: closes the discoverability gap where the dissection was only visible in AoI reports.
- `analysis/adv_dissect.py` — new `dissect_persisted_record(record)` shared adapter reconstructs dissector inputs from persisted `devices`-row / AoI fields (`manufacturer_id`/`manufacturer_data`/`service_data`/`advertising_data`/`uuids`; bytes/hex/JSON/D-Bus-list tolerant; top-level or nested `device`) → dissection dict or `None`; never raises.
- `analysis/aoi_analyser.py` — `_render_adv_dissection` refactored onto the shared adapter (removed the inlined reconstruction + now-dead `_adv_field`); report output unchanged (single source of truth, no drift with CLI).
- `modes/db.py` — `db show <mac>` prints an "Advertisement Dissection" section (indented CLI style: vendors/protocols, decoded protocols, raw hex + ASCII); `--full`/`--json`/`--quiet` attach an `adv_dissection` block. Dissection recomputed from raw fields so pre-G-7.5 devices are covered; `get_device_detail()` unchanged (enrichment in the show command only).
- Tests: `tests/test_db_show_adv_dissection.py` (human section, `--full` JSON, JSON dispatch path); `tests/test_adv_dissect.py` extended for `dissect_persisted_record` (BLOB/JSON/nested/empty/malformed).

---

### G-7.4 Implementation — Classification Blind Spots (accepted 2026-07-24)

**Goal**: Close the three roadmap blind spots without changing the sound parts of classification, and reuse the G-7.5 dissector rather than re-implementing decode logic in the classifier.

**Blind spot (a) — advertised UUIDs treated as ground truth for the Classic/LE split.**
`ClassicServiceUUIDsCollector` derives Classic evidence from the advertised/cached `UUIDs` property, not a live SDP browse. The evidence entries now carry `ground_truth=False` and `source_kind="advertised"` in their metadata, and `_determine_evidence_source()` continues to report such a verdict as `evidence_source="heuristic"` (only measured SDP/GATT promote to `measured_sdp` / `measured_gatt`). The *decision* is intentionally preserved (advertised Classic-profile UUIDs remain a legitimate, strong hint), but the result is now honestly labelled as not-SDP-confirmed.

**Blind spot (b) — cached classification not flagged.**
`ClassificationResult.cached` / `evidence_source` already existed and were stored to the DB, but were dropped by `modes/aoi.py::_classify_device` (which returned only the type string). `_classify_device` now returns the full `ClassificationResult`; `_scan_target` threads `device_type_evidence_source` and `device_type_cached` into `device_data`, and `aoi_analyser._generate_markdown_report` renders a **Device Type** line annotated with the evidence source, a `cached` marker, and the seed/live source.

**Blind spot (c) — Find My / beacon manufacturer-data ignored for `type`.**
`LEServiceDataCollector` now feeds `ManufacturerData` through the shared `dissect_advertisement()` and emits STRONG `LE_ADVERTISING_DATA` evidence when a **BLE-specific** protocol is decoded (`ibeacon`, `apple_continuity` — set `_LE_INDICATIVE_ADV_PROTOCOLS`). Beacon-only devices (no advertised GATT/service-data UUID) now classify as `le` instead of `unknown`. `ManufacturerData` also appears in Classic EIR, so a bare/undecoded company payload is deliberately **not** treated as LE evidence. (`fcf1` and other service-data UUIDs were already handled by G-7.1 + G-7.5.)

**Components / files**:
- `analysis/device_type_classifier.py` — `_LE_INDICATIVE_ADV_PROTOCOLS`; manufacturer-data dissection path in `LEServiceDataCollector`; `ground_truth`/`source_kind` metadata on advertised Classic evidence.
- `modes/aoi.py` — `_classify_device` returns `ClassificationResult`; `_scan_target` records `device_type_evidence_source` / `device_type_cached`.
- `analysis/aoi_analyser.py` — **Device Type** provenance line in the markdown report.

**Acceptance criteria** (all met):
- Beacon-only (iBeacon / Apple Continuity mfg-data) devices classify as `le`; bare vendor mfg-data does not.
- Advertised Classic-UUID verdict reports `evidence_source="heuristic"` and evidence metadata `ground_truth=False`.
- AoI report surfaces evidence source + cached flag.
- No re-implemented decode logic — recognition delegated to `dissect_advertisement`.
- Full test suite green (173 in the affected suites); new tests cover each invariant.

---

### Remediation Phases

#### Phase 1: Critical Fixes (Immediate — ~30 minutes)

Quick wins that fix actual runtime bugs and standard Python packaging.

| # | Item | Effort | Files |
|---|------|--------|-------|
| 1 | G-1.1: Fix `is_powered()`/`is_discovering()` in `modes/test.py` | 10 min | `modes/test.py` |
| 2 | G-1.2: Remove `ljust` space-padding in `uuid_utils.py` | 5 min | `ble_ops/common/uuid_utils.py` |
| 3 | G-1.3: Fix `dbuslayer/__init__.py` `__all__` vs imports | 15 min | `dbuslayer/__init__.py` |
| 4 | G-1.4: Add `bleep/__main__.py` + update `cli_usage.md` | 5 min | New: `__main__.py`, `docs/cli_usage.md` |
| 5 | G-1.5: Delete orphaned `.pyc` | 1 min | `callbacks/examples/__pycache__/` |

#### Phase 2: Consolidation and Cleanup ✅ Complete (2026-04-01)

Tech debt that compounds if left unaddressed.

| # | Item | Effort | Status |
|---|------|--------|--------|
| 6 | G-4.4: B5 D-Bus error mapping consolidation | 2-3 hr | Deferred to Phase 4 — multiple overlapping tables with subtle semantic differences require dedicated analysis |
| 7 | G-7.6: Extract shared BT SIG base UUID constant | 30 min | ✅ Done |
| 8 | G-6.2, G-6.3, G-6.4: Update stale doc status markers | 1 hr | ✅ Done |
| 9 | G-5.1a: Create `tests/conftest.py` with shared fixtures | 2 hr | Deferred to Phase 3 (test expansion) |
| 10 | G-4.2, G-4.3: Deprecated shims deleted in v2.8.1 | 1 hr | ✅ Done |
| 11 | G-3.2: Structure `mesh/` for proper future development | 10 min | ✅ Done |

#### Phase 3: Test Coverage Expansion ✅ Complete (2026-04-01)

Prioritized by likelihood of catching real bugs.  112 tests total, all passing (<1s).

| # | Item | Priority | Status |
|---|------|----------|--------|
| Prereq | G-5.1a: `tests/conftest.py` with shared fixtures | — | ✅ Done |
| 12 | G-5.1b: Unit tests for `uuid_utils.py` (23 tests) | High | ✅ Done |
| 13 | G-5.1c: Unit tests for `core/preflight.py` (18 tests) | High | ✅ Done |
| 14 | G-5.1f: Unit tests for `analysis/sdp_analyzer.py` (18 tests) | Medium | ✅ Done |
| 15 | G-5.1d: Unit tests for `ble_ops/classic/map.py` (14 tests) | Medium | ✅ Done |
| 16 | G-5.1e: Unit tests for `callbacks/base.py` (12 tests) | Medium | ✅ Done |
| 17 | G-5.1g: Mock tests for `dbuslayer/service.py`, `device_classic.py` (14 tests) | Medium | ✅ Done |

#### Phase 4: Feature Completion & Error Consolidation ✅ Complete (2026-04-01)

Four bounded items addressing error-handling fragility, live GATT observation, device classification, and data quality.  279 tests total, all passing.

| # | Item | Complexity | Status |
|---|------|-----------|--------|
| 6 | G-4.4: B5 D-Bus error mapping consolidation (deferred from Phase 2) | 2-3 hr | ✅ Done |
| 20 | G-2.3: `service.py` signal handling — propagate GATT property changes | Medium | ✅ Done |
| 21 | G-7.1, G-7.2: Device type classifier enrichment (`ServiceData`/`AdvertisingData` + vendor UUID heuristics) | Medium | ✅ Done |
| 22 | G-7.3: DB row enrichment from scan data (RSSI min/max tracking, best-manufacturer selection) | Small | ✅ Done |

**Deferred to future sprint / v2.9 milestone:**

| # | Item | Reason |
|---|------|--------|
| 18 | G-2.1: Endpoint transport acquisition (PipeWire contention) | Large scope; `--system` audio workaround covers all current use cases |
| 19 | G-2.2: `audio_codec.py` appsrc recording | Depends on G-2.1 transport acquisition |
| 23 | G-7.5: Advertisement dissection tool | Large standalone feature, high maintenance burden |
| 28 | G-3.1-M: Migrate GATT wrappers (`service.py`, `characteristic.py`, `descriptor.py`) from `dbuslayer/` into `bleep/gatt/` | Blocked until GATT wrappers are mature enough to decouple from D-Bus layer; see G-3.1 decision |

#### Phase 5: Package Hygiene and Documentation ✅ Complete (2026-04-01)

All four items resolved: deprecated UUID file deleted, protocol descriptors populated from SDP, docs updated.

| # | Item | Status |
|---|------|--------|
| 24 | G-3.1: `bleep/gatt/` — decision: keep as future migration target (no action now) | ✅ Done |
| 25 | G-3.3: Note `protocols/` as design-only in docs README | ✅ Done |
| 26 | G-4.1: `bluetooth_uuids.py` deprecated — bleep-mcp imports migrated to `bt_ref.uuids`, file deleted | ✅ Done |
| 27 | G-6.5: `protocol_descriptors` column now populated from SDP ProtocolDescriptorList (all 3 parsers) | ✅ Done |
| 29 | v2.8.1 deprecated module removal: `compat.py`, `bluetooth_exceptions.py`, `bluetooth_constants.py`, `bluetooth_utils.py` deleted; `bt_ref/__init__.py` legacy block removed; docstring references updated | ✅ Done |
| 30 | Documentation drift: `map.py` docstring, `mainloop_architecture.md` status, `media_mode.md` flags/examples, `aoi.py` TODO stub | ✅ Done |
| 31 | Media enumeration expansion: non-verbose player output, AVRCP labels, `--verbose` object tree, `--browse` flag, `media_mode.md` sync | ✅ Done |
| 32 | Bluetooth Mesh skeleton: full `bleep/mesh/` package (constants, errors, network, node, management, application, element, provisioner, provision_agent); `proxy_solicitation.py` API corrected | ✅ Done |

---

## V2.8.1 BlueZ D-Bus Interface Gap Analysis (2026-04-02) – COMPLETE (reconciled 2026-07-22: all gaps BZ-1..BZ-25 marked DONE in the summary table)

**Origin**: Systematic comparison of every `org.bluez.*` D-Bus interface documented in `workDir/BlueZDocs/*.rst`, `workDir/bluez/doc/*.txt`, and `workDir/bluez-tools/contrib/bluez-api-5.20-fixed/*.txt` against the BLEEP v2.8.1 codebase (`bleep/**/*.py`). Goal: ensure BLEEP achieves **complete** enumeration, capture, and interaction coverage of all BlueZ-exposed Bluetooth capabilities.

**Methodology**: For each BlueZ D-Bus interface, every property, method, and signal was checked for presence in BLEEP code (not just constants, but actual read/write/call usage). Items marked PARTIAL have interface name constants defined in `bt_ref/constants.py` but no functional implementation.

**Reference documents** (for manual verification):
- Adapter: `workDir/BlueZDocs/org.bluez.Adapter.rst`
- Device: `workDir/BlueZDocs/org.bluez.Device.rst`
- GATT: `workDir/BlueZDocs/org.bluez.GattCharacteristic.rst`, `org.bluez.GattManager.rst`, `org.bluez.GattProfile.rst`
- Agent: `workDir/BlueZDocs/org.bluez.Agent.rst`, `org.bluez.AgentManager.rst`
- LE Advertising: `workDir/BlueZDocs/org.bluez.LEAdvertisement.rst`, `org.bluez.LEAdvertisingManager.rst`
- Battery: `workDir/BlueZDocs/org.bluez.Battery.rst`, `org.bluez.BatteryProvider.rst`, `org.bluez.BatteryProviderManager.rst`
- Media: `workDir/BlueZDocs/org.bluez.Media.rst`, `org.bluez.MediaPlayer.rst`, `org.bluez.MediaTransport.rst`, `org.bluez.MediaEndpoint.rst`, `org.bluez.MediaFolder.rst`, `org.bluez.MediaItem.rst`, `org.bluez.MediaAssistant.rst`
- Network: `workDir/BlueZDocs/org.bluez.Network.rst`, `org.bluez.NetworkServer.rst`
- Profile: `workDir/BlueZDocs/org.bluez.Profile.rst`, `org.bluez.ProfileManager.rst`
- Input: `workDir/BlueZDocs/org.bluez.Input.rst`
- Adv Monitor: `workDir/BlueZDocs/org.bluez.AdvertisementMonitor.rst`, `org.bluez.AdvertisementMonitorManager.rst`
- Admin Policy: `workDir/BlueZDocs/org.bluez.AdminPolicySet.rst`, `org.bluez.AdminPolicyStatus.rst`
- Device Sets: `workDir/BlueZDocs/org.bluez.DeviceSet.rst`
- Bearer Split: `workDir/BlueZDocs/org.bluez.Bearer.LE.rst`, `org.bluez.Bearer.BREDR.rst`
- Health: `workDir/bluez/doc/health-api.txt`
- SAP: `workDir/bluez/doc/sap-api.txt`
- Thermometer: `workDir/bluez/doc/thermometer-api.txt`
- Mesh: `workDir/bluez/doc/mesh-api.txt`

---

### Gap Summary Table

| # | Gap ID | Interface / Area | Gap Description | Severity | BLEEP Status |
|---|--------|-----------------|-----------------|----------|-------------|
| 1 | BZ-1 | `GattCharacteristic1` | `AcquireWrite()` / `AcquireNotify()` fd-based streaming | High | **DONE** (Sprint 1) |
| 2 | BZ-2 | `GattCharacteristic1` | `WriteAcquired` / `NotifyAcquired` properties read from D-Bus | Medium | **DONE** (Sprint 1) |
| 3 | BZ-3 | `GattCharacteristic1` | `Confirm()` method (server-side indication ack) | Low | **DONE** (Sprint 5B) — `Confirm()` on `GattCharacteristicSkeleton` |
| 4 | BZ-4 | `GattManager1` | `RegisterApplication()` / `UnregisterApplication()` — GATT server | High | **DONE** (Sprint 5B) — `dbuslayer/gatt_server.py`, `modes/gatt_server.py`, `bleep gatt-server start` |
| 5 | BZ-5 | `GattProfile1` | GATT profile registration for auto-connect | Low | **DONE** (Sprint 5C) — `GattProfileSkeleton` in `dbuslayer/gatt_server.py` |
| 6 | BZ-6 | `LEAdvertisingManager1` | `RegisterAdvertisement()` / `UnregisterAdvertisement()` + capability queries | High | **DONE** (Sprint 2) |
| 7 | BZ-7 | `LEAdvertisement1` | Advertisement object (Type, ServiceUUIDs, ManufacturerData, etc.) + CLI | High | **DONE** (Sprint 2) |
| 8 | BZ-8 | `Device1` | `Disconnected` signal subscription + reason capture | Medium | **DONE** (Sprint 1) |
| 9 | BZ-9 | `BatteryProvider1` | Battery provider registration | Low | **DONE** (Sprint 5D) — `dbuslayer/battery_provider.py` |
| 10 | BZ-10 | `BatteryProviderManager1` | `RegisterBatteryProvider()` / `UnregisterBatteryProvider()` | Low | **DONE** (Sprint 5D) — `BatteryProviderManager` in `battery_provider.py` |
| 11 | BZ-11 | `AdvertisementMonitor1` | Advertisement monitoring (pattern-based passive scanning) | High | **DONE** (Sprint 4) |
| 12 | BZ-12 | `AdvertisementMonitorManager1` | `RegisterMonitor()` / `UnregisterMonitor()` | High | **DONE** (Sprint 4) |
| 13 | BZ-13 | `AdminPolicySet1` | `SetServiceAllowList()` | Low | **DONE** (Sprint 5C) — `set_service_allow_list()`/`get_service_allow_list()` in `adapter.py` |
| 14 | BZ-14 | `AdminPolicyStatus1` | `ServiceAllowList` / `IsAffectedByPolicy` properties | Low | **DONE** (Sprint 5C) — `is_affected_by_policy` in device info for LE + Classic |
| 15 | BZ-15 | `DeviceSet1` | `Connect()`, `Disconnect()`, properties, CLI | Medium | **DONE** (Sprint 5C) — `dbuslayer/device_set.py`, `bleep device-sets` CLI |
| 16 | BZ-16 | `Bearer.LE1` / `Bearer.BREDR1` | Per-bearer properties + connect/disconnect | Low | **DONE** (Sprint 5D) — `bearer_le`/`bearer_bredr` in device info, bearer methods |
| 17 | BZ-17 | `HealthManager1` / `HealthDevice1` / `HealthChannel1` | Bluetooth Health Profile (HDP) | Low | **DONE** (Sprint 5D) — `dbuslayer/health.py` stub; removed in BlueZ 5.50+ |
| 18 | BZ-18 | `SimAccess1` | SIM Access Profile not implemented | Low | **DONE** — Documented as inapplicable in `bl_classic_mode.md` §2.13 |
| 19 | BZ-19 | `MediaAssistant1` | Broadcast Audio Assistant | Low | **DONE** (Sprint 5D) — `dbuslayer/media_assistant.py` |
| 20 | BZ-20 | `Thermometer1` / `ThermometerManager1` | Thermometer profile D-Bus API not implemented | Low | **DONE** (Sprint 5E) — GATT-level decode in `gatt_profile_decode.py` |
| 21 | BZ-21 | `HeartRate1` / `HeartRateManager1` | Heart Rate profile D-Bus API not implemented | Low | **DONE** (Sprint 5E) — GATT-level decode in `gatt_profile_decode.py` |
| 22 | BZ-22 | `CyclingSpeed1` / `CyclingSpeedManager1` | Cycling Speed profile D-Bus API not implemented | Low | **DONE** (Sprint 5E) — GATT-level decode in `gatt_profile_decode.py` |
| 23 | BZ-23 | `ProximityMonitor1` / `ProximityReporter1` | Proximity profile D-Bus API not implemented | Low | **DONE** (Sprint 5E) — GATT-level decode in `gatt_profile_decode.py` |
| 24 | BZ-24 | Mesh `ProvisionAgent1` | OOB hooks with AgentIOHandler pattern + CLI | Medium | **DONE** (Sprint 5D) — `InteractiveProvisionAgent`, `bleep mesh` CLI |
| 25 | BZ-25 | Mesh `Provisioner1` | Reprovisioning D-Bus methods + Management wrapper | Low | **DONE** (Sprint 5C) — D-Bus skeleton + `MeshManagement.reprovision()` |

---

### Detailed Gap Descriptions

#### BZ-1: GATT AcquireWrite / AcquireNotify (HIGH)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.GattCharacteristic.rst`):
- `AcquireWrite(dict options)` → `(fd, uint16 mtu)` — Returns a file descriptor for streaming writes, bypassing per-packet D-Bus overhead
- `AcquireNotify(dict options)` → `(fd, uint16 mtu)` — Returns a file descriptor for streaming notification reception

**BLEEP status**: COMPLETE. `dbuslayer/characteristic.py` implements `acquire_write()`, `acquire_notify()`, `write_value_fd()`, `read_notify_fd()`, `release_acquired()` with auto-fallback to `WriteValue`/`StartNotify`. CLI wired via `--stream` on debug `read`/`write`. 12 mock tests in `test_characteristic_descriptor.py`.

**Impact**: High-throughput BLE data streams (sensor feeds, firmware updates, audio-over-GATT) suffer D-Bus round-trip latency on every packet. The fd-based path eliminates this overhead entirely.

**Implementation plan**:
- [x] **BZ-1a** Add `acquire_write(dict options) → (fd, mtu)` to `dbuslayer/characteristic.py`
    - Calls `GattCharacteristic1.AcquireWrite({})` on the D-Bus interface
    - Returns the Unix FD and negotiated MTU
    - Tracks `WriteAcquired` property to prevent double-acquire
    - Handles `NotPermitted` / `NotSupported` gracefully (fall back to `WriteValue`)
- [x] **BZ-1b** Add `acquire_notify(dict options) → (fd, mtu)` to `dbuslayer/characteristic.py`
    - Calls `GattCharacteristic1.AcquireNotify({})` on the D-Bus interface
    - Returns the Unix FD and negotiated MTU
    - Tracks `NotifyAcquired` property
    - Falls back to `StartNotify` path on `DBusException`
- [x] **BZ-1c** Add `write_value_fd()` and `read_notify_fd()` streaming helpers with auto-acquire + fallback
- [x] **BZ-1d** Add `release_acquired()` cleanup method to close fds
- [x] **BZ-1e** Wire up to CLI: `--stream` flag on `read`/`write` debug commands
- [x] **BZ-1f** Tests: mock-based unit tests for acquire/fallback logic — completed 2026-05-21 (12 tests in `test_characteristic_descriptor.py`; production fix: `_dbus_exc()` helper for dynamic exception resolution)

#### BZ-2: WriteAcquired / NotifyAcquired Property Read (MEDIUM)

**BlueZ API**: `WriteAcquired` (boolean, readonly) and `NotifyAcquired` (boolean, readonly) on `GattCharacteristic1` indicate whether an fd-based acquisition is active.

**BLEEP status**: Property names exist in `bt_ref/constants.py` (line 235-236), `core/config.py` (lines 80-81, 154-155), and `ble_ops/common/structural.py` (lines 38-39) as schema fields. However, `dbuslayer/characteristic.py` does NOT read these from D-Bus — they are never populated at runtime.

**Fix**: Read from D-Bus `GetAll` in characteristic init, same pattern as `MTU`/`Notifying`.

- [x] **BZ-2a** Read `WriteAcquired` and `NotifyAcquired` from D-Bus in `Characteristic.__init__` and expose as properties
- [x] **BZ-2b** Include in enumeration output (`conversion.py` characteristic display)
- [x] **BZ-2c** Populate from live Characteristic in `device_le.py` enumeration mapping

#### BZ-3: GATT Confirm Method (LOW) — COMPLETE

**BlueZ API**: `Confirm()` — Server-only method to confirm an indication has been received. Only relevant when BLEEP acts as a GATT server.

**BLEEP status**: COMPLETE. `Confirm()` implemented on `GattCharacteristicSkeleton` in `dbuslayer/gatt_server.py` (Sprint 5B).

- [x] **BZ-3a** Add `Confirm()` method to `GattCharacteristicSkeleton` (completed 2026-05-21)

#### BZ-4: GATT Server via GattManager1 (HIGH) — COMPLETE

**BlueZ API** (`workDir/BlueZDocs/org.bluez.GattManager.rst`):
- `RegisterApplication(object application, dict options)` — Register a D-Bus GATT application exposing services/characteristics
- `UnregisterApplication(object application)` — Unregister

**BLEEP status**: COMPLETE. Full GATT server stack implemented in Sprint 5B (2026-05-21):
- `dbuslayer/gatt_server.py`: `GattApplication` (ObjectManager), `GattServiceSkeleton`, `GattCharacteristicSkeleton` (with `Confirm()`), `GattDescriptorSkeleton`, `GattServerManager` (register/unregister), 5 D-Bus error types
- `modes/gatt_server.py`: CLI mode with example read/write/notify characteristics
- `bleep gatt-server start`: CLI subcommand with `--uuid`, `--read-value`, `--duration`, `--adapter` options
- 40 mock-based unit tests in `tests/test_gatt_server.py`

- [x] **BZ-4a** Create `dbuslayer/gatt_server.py` with `GattApplication`, `GattServiceSkeleton`, `GattCharacteristicSkeleton`, `GattDescriptorSkeleton` implementing `org.freedesktop.DBus.ObjectManager` (completed 2026-05-21)
- [x] **BZ-4b** Add `register_application()` / `unregister_application()` methods calling `GattManager1` on adapter path (completed 2026-05-21)
- [x] **BZ-4c** Wire BZ-3 `Confirm()` for indication-based characteristics (completed 2026-05-21)
- [x] **BZ-4d** Create `modes/gatt_server.py` CLI mode and `bleep gatt-server start` subcommand (completed 2026-05-21)
- [x] **BZ-4e** Example: simple GATT server with read/write/notify characteristics (completed 2026-05-21)
- [x] **BZ-4f** Tests: 40 mock-based unit tests in `test_gatt_server.py` (completed 2026-05-21)

#### BZ-5: GattProfile1 Interface (LOW) — COMPLETE (Sprint 5C)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.GattProfile.rst`): Allows registering interest in specific GATT services for auto-connect.

**BLEEP status**: COMPLETE. `GattProfileSkeleton` implemented in `dbuslayer/gatt_server.py` (Sprint 5C).

- [x] **BZ-5a** Implement `GattProfile1` registration for auto-reconnect scenarios (completed 2026-05-21)

#### BZ-6 / BZ-7: LE Advertising Manager and Advertisement (HIGH)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.LEAdvertisingManager.rst`, `org.bluez.LEAdvertisement.rst`):
- `RegisterAdvertisement(object, dict)` / `UnregisterAdvertisement(object)` on `LEAdvertisingManager1`
- `LEAdvertisement1` properties: `Type` (broadcast/peripheral), `ServiceUUIDs`, `ManufacturerData`, `SolicitUUIDs`, `ServiceData`, `Data`, `Discoverable`, `DiscoverableTimeout`, `Includes`, `LocalName`, `Appearance`, `Duration`, `Timeout`, `SecondaryChannel`, `MinInterval`, `MaxInterval`, `TxPower`
- Manager properties: `ActiveInstances`, `SupportedInstances`, `SupportedIncludes`, `SupportedSecondaryChannels`, `SupportedCapabilities`, `SupportedFeatures`

**BLEEP status**: COMPLETE. `dbuslayer/le_advertising.py` implements `LEAdvertisement`, `LEAdvertisingManager`, `AdvertisementConfig`. CLI in `modes/advertise.py` (`bleep advertise caps`/`start`). 21 mock tests in `test_le_advertising.py`. Docs in `docs/le_advertising.md`.

**Impact**: Critical for peripheral emulation, beacon testing, honeypot creation, and BLE security research.

**Implementation plan**:
- [x] **BZ-6a** `dbuslayer/le_advertising.py` — `LEAdvertisement` D-Bus object with full `LEAdvertisement1` property set via `GetAll`; `Release()` callback
- [x] **BZ-6b** `LEAdvertisingManager.register()` / `.unregister()` with async reply/error + 5s timeout
- [x] **BZ-6c** Capability property readers: `SupportedInstances`, `ActiveInstances`, `SupportedIncludes`, `SupportedSecondaryChannels`, `SupportedFeatures`, `SupportedCapabilities`
- [x] **BZ-7a** `modes/advertise.py` CLI mode — `bleep advertise caps` + `bleep advertise start`
- [x] **BZ-7b** Broadcast + peripheral types; configurable UUIDs, manufacturer data, service data, name, appearance, TX power, intervals, secondary channel, discoverable, includes
- [x] **BZ-7c** Documentation: `docs/le_advertising.md`
- [x] **BZ-7d** Tests: mock-based unit tests — completed 2026-05-21 (21 tests in `test_le_advertising.py`)

#### BZ-8: Device1 Disconnected Signal (MEDIUM)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.Device.rst`): `Disconnected(string reason, string message)` signal with reason codes (`org.bluez.Reason.ConnectionTimeout`, `ConnectionTerminatedByLocalHost`, etc.).

**BLEEP status**: `core/error_handling.py` lines 139-147 define `DISCONNECT_REASON_MAP` for all reason codes but it is NOT wired to actual signal subscription. Connection drops are detected only via `PropertiesChanged` on `Connected` property, losing the structured reason/message payload.

**Impact**: Cannot distinguish *why* a disconnect occurred (timeout vs. user-initiated vs. remote-initiated vs. link loss). This information is valuable for reliability analysis and automated reconnection logic.

- [x] **BZ-8a** Subscribe to `Disconnected` signal on Device1 objects in `dbuslayer/signals.py` via `_attach_bus_listeners`
- [x] **BZ-8b** Wire `DISCONNECT_REASON_MAP` in `error_handling.py` to parse the signal payload in `_device_disconnected` handler
- [x] **BZ-8c** Enrich `_device_connection_states` dict with `disconnect_reason`, `disconnect_message`, `disconnect_human` fields
- [x] **BZ-8d** Add `get_disconnect_reason(device_path)` public API for querying last disconnect reason
- [x] **BZ-8e** Forward to registered device instance via `on_disconnected(reason, message)` callback
- [x] **BZ-8f** Surface disconnect reason in CLI output and debug mode `info` command

#### BZ-9 / BZ-10: Battery Provider (LOW)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.BatteryProvider.rst`, `org.bluez.BatteryProviderManager.rst`): Allows external applications to provide battery level information to BlueZ for devices that report battery via non-standard mechanisms.

**BLEEP status**: COMPLETE. `BatteryProviderObject`, `BatteryProviderApp`, `BatteryProviderManager` implemented in `dbuslayer/battery_provider.py` (Sprint 5D).

**Impact**: Low — primarily useful for custom device drivers, not typical security research.

- [x] **BZ-9a** Implement `BatteryProvider1` object and `BatteryProviderManager1.RegisterBatteryProvider()` in `dbuslayer/` (completed 2026-05-21)
- [x] **BZ-10a** Wire to CLI for devices with custom battery reporting — ready for CLI integration when needed (completed 2026-05-21)

#### BZ-11 / BZ-12: Advertisement Monitor (HIGH)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.AdvertisementMonitor.rst`, `org.bluez.AdvertisementMonitorManager.rst`):
- `RegisterMonitor(object)` / `UnregisterMonitor(object)` on `AdvertisementMonitorManager1`
- Monitor properties: `Type` (or_patterns), `RSSILowThreshold`, `RSSIHighThreshold`, `RSSILowTimeout`, `RSSIHighTimeout`, `RSSISamplingPeriod`, `Patterns`
- Callbacks: `Activate()`, `Release()`, `DeviceFound(object)`, `DeviceLost(object)`

**BLEEP status**: COMPLETE. Constants in `bt_ref/constants.py`, D-Bus layer in `dbuslayer/adv_monitor.py`, CLI in `modes/monitor.py` + `modes/scan_monitor.py`, 29 mock tests in `test_adv_monitor.py`, docs in `docs/adv_monitor.md`.

**Impact**: Advertisement monitoring is the kernel-offloaded alternative to `SetDiscoveryFilter`. It allows pattern-based passive scanning with RSSI thresholds and device found/lost callbacks — critical for long-running surveillance, presence detection, and asset tracking scenarios. Without this, BLEEP must keep full discovery running and filter in userspace.

**Implementation plan**:
- [x] **BZ-11a** Create `dbuslayer/adv_monitor.py` with `AdvertisementMonitor` D-Bus skeleton (ObjectManager + per-monitor objects)
- [x] **BZ-11b** Implement pattern configuration (AD type + offset + content matching)
- [x] **BZ-11c** Implement RSSI threshold and sampling period configuration
- [x] **BZ-12a** Add `register_monitor()` / `unregister_monitor()` via `AdvertisementMonitorManager1`
- [x] **BZ-12b** Wire `DeviceFound` / `DeviceLost` callbacks to observation pipeline
- [x] **BZ-12c** Create `modes/monitor.py` — standalone `bleep monitor` command
- [x] **BZ-12d** Documentation and tests — `docs/adv_monitor.md` + 29 mock tests in `test_adv_monitor.py`
- [x] **BZ-12e** `--monitor` flag on `bleep scan` command — `modes/scan_monitor.py` (completed 2026-05-21)

#### BZ-13 / BZ-14: Admin Policy (LOW) — COMPLETE (Sprint 5C)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.AdminPolicySet.rst`, `org.bluez.AdminPolicyStatus.rst`): Experimental interface for restricting which services are allowed on the adapter/device level.

**BLEEP status**: COMPLETE. `set_service_allow_list()`/`get_service_allow_list()` in `adapter.py`; `is_affected_by_policy` in device info for LE + Classic (Sprint 5C).

**Impact**: Low — enterprise/MDM use case. However, reading `IsAffectedByPolicy` on devices could explain mysterious connection failures.

- [x] **BZ-13a** Add `AdminPolicySet1.SetServiceAllowList()` support in adapter wrapper (completed 2026-05-21)
- [x] **BZ-14a** Read `AdminPolicyStatus1.IsAffectedByPolicy` in device property enumeration (completed 2026-05-21)
- [x] **BZ-14b** Surface policy-affected status in scan/enum output (completed 2026-05-21)

#### BZ-15: DeviceSet1 Interface (MEDIUM)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.DeviceSet.rst`): Experimental. `Connect()`, `Disconnect()` on a set of coordinated devices (e.g., TWS earbuds). Properties: `Adapter`, `AutoConnect`, `Devices`, `Size`.

**BLEEP status**: COMPLETE. `dbuslayer/device_set.py` wraps `DeviceSet1` interface with `connect_set()`/`disconnect_set()`; `bleep device-sets` CLI command; enumeration in scan output (Sprint 5C).

- [x] **BZ-15a** Create `dbuslayer/device_set.py` to wrap `DeviceSet1` interface (completed 2026-05-21)
- [x] **BZ-15b** Add `connect_set()` / `disconnect_set()` methods (completed 2026-05-21)
- [x] **BZ-15c** Enumerate device sets in scan/enum output (completed 2026-05-21)
- [x] **BZ-15d** Surface in CLI (e.g., `bleep device-sets` command) (completed 2026-05-21)

#### BZ-16: Bearer Split Interfaces (LOW) — COMPLETE (Sprint 5D)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.Bearer.LE.rst`, `org.bluez.Bearer.BREDR.rst`): Experimental. Per-bearer `Connect()`/`Disconnect()` and `Disconnected` signal with independent `Paired`/`Bonded`/`Connected` properties.

**BLEEP status**: COMPLETE. `bearer_le` dict in `device_le.get_device_info()`, `bearer_bredr` dict in `device_classic.get_device_info()`, plus `bearer_le_connect()`/`bearer_le_disconnect()` and `bearer_bredr_connect()`/`bearer_bredr_disconnect()` methods (Sprint 5D).

- [x] **BZ-16a** Detect and enumerate `Bearer.LE1` / `Bearer.BREDR1` child interfaces on device objects (completed 2026-05-21)
- [x] **BZ-16b** Add per-bearer connect/disconnect to debug mode (completed 2026-05-21)

#### BZ-17: Health Device Profile (LOW) — COMPLETE (Sprint 5D)

**BlueZ API** (`workDir/bluez/doc/health-api.txt`): `HealthManager1`, `HealthDevice1`, `HealthChannel1` for IEEE 11073 health devices.

**BLEEP status**: COMPLETE. `dbuslayer/health.py` documentation stub; `HDP_SUPPORTED = False`; legacy interface constants for reference; HDP removed from BlueZ 5.50+ (Sprint 5D).

**Impact**: Low — HDP is rarely used in practice, superseded by GATT-based health profiles.

- [x] **BZ-17a** Stub `dbuslayer/health.py` for HDP — documented as legacy, removed in BlueZ 5.50+ (completed 2026-05-21)

#### BZ-18: SIM Access Profile (LOW)

**BlueZ API** (`workDir/bluez/doc/sap-api.txt`): `SimAccess1.Disconnect()` + `Connected` property.

**BLEEP status**: Documented only — BlueZ's SAP is server-side (provides SIM to remote
clients, not the other way around).  BLEEP cannot read a phone's SIM via SAP.  See
`bleep/docs/bl_classic_mode.md` §2.13 for full explanation.

**Impact**: Low — niche automotive/hands-free SIM sharing; BlueZ API is too limited
for client-side SIM reading.

- [x] **BZ-18a** Documented SAP limitations in `bl_classic_mode.md` §2.13 (no stub needed)

#### BZ-19: MediaAssistant1 — Broadcast Audio Assistant (LOW) — COMPLETE (Sprint 5D)

**BlueZ API** (`workDir/BlueZDocs/org.bluez.MediaAssistant.rst`): Experimental. `Push(dict)` method + `State`/`Metadata`/`QoS` properties for LE Audio Broadcast Assistant role.

**BLEEP status**: COMPLETE. `MediaAssistant` wrapper in `dbuslayer/media_assistant.py` with `push()`, `get_state()`, `get_metadata()`, `get_qos()`, `get_info()`; `enumerate_media_assistants()` discovery; lazy-loaded module (Sprint 5D).

**Impact**: Low — LE Audio is bleeding-edge; only relevant for Auracast/broadcast audio scenarios.

- [x] **BZ-19a** `MediaAssistant1` wrapper in `dbuslayer/media_assistant.py` (completed 2026-05-21)

#### BZ-20 through BZ-23: Deprecated Profile D-Bus APIs (LOW) — COMPLETE (Sprint 5E)

**Interfaces**: `ThermometerManager1`/`Thermometer1`, `HeartRateManager1`/`HeartRate1`, `CyclingSpeedManager1`/`CyclingSpeed1`, `ProximityMonitor1`/`ProximityReporter1`

**BlueZ docs**: `workDir/bluez/doc/thermometer-api.txt`, `workDir/bluez-tools/contrib/bluez-api-5.20-fixed/heartrate-api.txt`, `cyclingspeed-api.txt`, `proximity-api.txt`

**BLEEP status**: COMPLETE. GATT-level profile-aware recognition and structured value interpretation implemented in `ble_ops/common/gatt_profile_decode.py`. Decoders for all four profile families (Health Thermometer, Heart Rate, Cycling Speed and Cadence, Proximity). Documented as intentionally unsupported at the D-Bus level in `docs/bluez_interface_properties.md` (Sprint 5E).

**Impact**: These are legacy BlueZ profile plugins (removed in BlueZ 5.48+). The functionality is now handled via standard GATT. BLEEP provides GATT-level decoding that works on all BlueZ versions.

- [x] **BZ-20a** Documented as intentionally unsupported (BlueZ deprecated) in `docs/bluez_interface_properties.md`; GATT-level decode in `gatt_profile_decode.py` (completed 2026-05-22)

#### BZ-24: Mesh ProvisionAgent1 OOB Hooks (MEDIUM)

**BlueZ API** (`workDir/bluez/doc/mesh-api.txt`): `ProvisionAgent1` methods: `PrivateKey`, `PublicKey`, `DisplayString`, `DisplayNumeric`, `PromptNumeric`, `PromptStatic`, `Cancel`. Properties: `Capabilities`, `OutOfBandInfo`, `URI`.

**BLEEP status**: COMPLETE. `InteractiveProvisionAgent` in `mesh/interactive_provision_agent.py` with `MeshIOHandler` pattern (CLI + auto-accept); `bleep mesh {join,provision,reprovision}` CLI in `modes/mesh_provision.py`; `Capabilities`/`OutOfBandInfo` configurable via constructor (Sprint 5C: BZ-24b, Sprint 5D: BZ-24a/c).

- [x] **BZ-24a** Implement OOB data exchange hooks (`DisplayNumeric`, `PromptNumeric`, `PromptStatic`) via `InteractiveProvisionAgent` + `MeshIOHandler` (completed 2026-05-21)
- [x] **BZ-24b** Make `Capabilities` and `OutOfBandInfo` configurable via constructor args (completed 2026-05-21)
- [x] **BZ-24c** Wire to CLI mesh provisioning commands — `bleep mesh {join,provision,reprovision}` (completed 2026-05-21)

#### BZ-25: Mesh Provisioner1 Reprovisioning (LOW) — COMPLETE (Sprint 5C)

**BlueZ API**: `RequestReprovData`, `ReprovComplete`, `ReprovFailed` methods on `Provisioner1`; `Management1.Reprovision()` client trigger.

**BLEEP status**: COMPLETE. `mesh/provisioner.py` implements all D-Bus methods including `RequestReprovData`, `ReprovComplete`, `ReprovFailed` with corresponding `on_*` hooks. `mesh/management.py` provides `MeshManagement.reprovision()` client wrapper.

- [x] **BZ-25a** D-Bus skeleton methods present in `mesh/provisioner.py`; `MeshManagement.reprovision()` added to `mesh/management.py` (completed 2026-05-21)

---

### Accepted Implementation Sprints (2026-04-02)

#### Sprint 1: Core Interaction Gaps — COMPLETE (2026-04-02)

Quick wins + highest-impact GATT/signal improvements. No new architectural patterns.

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 1 | BZ-2 | Read `WriteAcquired` / `NotifyAcquired` from D-Bus | 30 min | `dbuslayer/characteristic.py`, `ble_ops/common/conversion.py`, `dbuslayer/device_le.py` | [x] |
| 2 | BZ-8 | Device1 `Disconnected` signal subscription + reason capture | 2 hr | `dbuslayer/signals.py`, `core/error_handling.py` | [x] |
| 3 | BZ-1 | GATT `AcquireWrite` / `AcquireNotify` (fd-based streaming) | 3-4 hr | `dbuslayer/characteristic.py` | [x] |

**Dependency**: BZ-2 before BZ-1 (need `WriteAcquired`/`NotifyAcquired` to prevent double-acquire).

#### Sprint 2: LE Advertising — COMPLETE (2026-04-02)

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 4 | BZ-6/7 | LE Advertising Manager + Advertisement | 4-6 hr | `dbuslayer/le_advertising.py`, `modes/advertise.py`, `cli.py`, `bt_ref/constants.py` | [x] |

**Implementation details:**

- [x] **BZ-6a** `LEAdvertisement(dbus.service.Object)` — exports all BlueZ `LEAdvertisement1` properties via `GetAll`; `Release()` callback; `AdvertisementConfig` dataclass covers Type, ServiceUUIDs, ManufacturerData, SolicitUUIDs, ServiceData, LocalName, Includes, Appearance, Discoverable, DiscoverableTimeout, Duration, Timeout, TxPower, MinInterval, MaxInterval, SecondaryChannel, Data
- [x] **BZ-7a** `LEAdvertisingManager` wrapper — `register()`/`unregister()` with async reply/error + 5s timeout; property readers for ActiveInstances, SupportedInstances, SupportedIncludes, SupportedSecondaryChannels, SupportedFeatures, SupportedCapabilities
- [x] **BZ-7b** `bleep advertise` CLI subcommand — `caps` (capabilities) and `start` (broadcast with full flag set); clean SIGINT/SIGTERM shutdown; `--local-duration` and `--duration` (BlueZ-level timeout)
- [x] **BZ-7c** Documentation: `docs/le_advertising.md` — architecture, D-Bus flow, CLI examples, Python API, troubleshooting
- [x] **BZ-7d** Tests: mock-based unit tests for LEAdvertisement/LEAdvertisingManager — 21 tests (completed 2026-05-21)

#### Sprint 3: GATT Server (HIGH priority — v2.9.0 target)

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 5 | BZ-4 | GATT Server (`GattManager1.RegisterApplication`) | 8-12 hr | New: `dbuslayer/gatt_server.py`, `modes/gatt_server.py` | [x] Sprint 5B |
| 6 | BZ-3/5 | `Confirm()` + `GattProfile1` (dependent on BZ-4) | 1 hr | `dbuslayer/gatt_server.py` | [x] BZ-3 done; BZ-5 deferred |

#### Sprint 4: Advertisement Monitor — COMPLETE (2026-04-02)

Kernel-offloaded pattern-based passive scanning. Independent of Sprints 2-3.
Works **without** an active `StartDiscovery` session once bluetoothd activates the monitor job.

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 7 | BZ-11/12 | Advertisement Monitor + Manager | 4-6 hr | `dbuslayer/adv_monitor.py`, `modes/monitor.py`, `cli.py`, `bt_ref/constants.py` | [x] |

**Detailed Sprint 4 Implementation Plan**

Reference docs:
- API: `workDir/BlueZDocs/org.bluez.AdvertisementMonitor.rst`
- Manager API: `workDir/BlueZDocs/org.bluez.AdvertisementMonitorManager.rst`
- Reference impl: `workDir/BlueZScripts/example-adv-monitor` (404 lines)

Architecture overview:
- The client (BLEEP) registers an **application root path** with `AdvertisementMonitorManager1.RegisterMonitor(app_root)` on the adapter.
- Under that root, BLEEP exposes one or more **monitor objects** implementing:
  - `org.freedesktop.DBus.Properties.GetAll(s)` → returns monitor config
  - `org.freedesktop.DBus.ObjectManager.GetManagedObjects()` on app root
  - `InterfacesAdded` / `InterfacesRemoved` signals on app root
  - Methods invoked **by bluetoothd**: `Activate()`, `Release()`, `DeviceFound(o)`, `DeviceLost(o)`
- Each monitor has: `Type` ("or_patterns"), RSSI thresholds/timeouts, `Patterns` (array of `(start_pos: u8, ad_type: u8, content: ay)`)
- Once activated, device found/lost callbacks fire without needing `StartDiscovery`.

**Sub-tasks:**

BZ-11 — `dbuslayer/adv_monitor.py` (D-Bus layer):

- [x] **BZ-11a** `AdvMonitor(dbus.service.Object)` class — `dbuslayer/adv_monitor.py`
    - D-Bus path: `{app_root}/monitor{id}`
    - Properties via `GetAll(s)`: Type, RSSIHighThreshold/Timeout, RSSILowThreshold/Timeout, RSSISamplingPeriod, Patterns `a(yyay)`
    - Callback methods: `Activate()`, `Release()`, `DeviceFound(o)`, `DeviceLost(o)`
    - `remove_monitor()` — calls `remove_from_connection()`

- [x] **BZ-11b** `AdvMonitorApp(dbus.service.Object)` class — `dbuslayer/adv_monitor.py`
    - Implements `ObjectManager`: `GetManagedObjects()`, `InterfacesAdded`/`InterfacesRemoved` signals
    - `add_monitor()` / `remove_monitor()` / `remove_all()` lifecycle management

- [x] **BZ-11c** `RSSIConfig` dataclass with high/low threshold, timeout, sampling_period fields

- [x] **BZ-11d** `MonitorPattern` dataclass + `to_dbus()` converter; AD type constants provided

BZ-12 — Manager + CLI integration:

- [x] **BZ-12a** `AdvMonitorManager` wrapper class — `dbuslayer/adv_monitor.py`
    - `register(app)` / `unregister(app)` with async reply/error + 5 s timeout
    - `get_supported_types()` / `get_supported_features()` property readers

- [x] **BZ-12b** `DeviceFound`/`DeviceLost` callbacks wired via `MonitorCallbacks` dataclass
    - MAC extraction from device object path; real-time console output in `modes/monitor.py`
    - Observation pipeline integration deferred to future PR (requires GLib↔thread bridge)

- [x] **BZ-12c** `bt_ref/constants.py` entries added: `ADV_MONITOR_INTERFACE`, `ADV_MONITOR_MANAGER_INTERFACE`, `ADV_MONITOR_APP_BASE_PATH`

- [x] **BZ-12d** `bleep monitor` subcommand in `modes/monitor.py` + `cli.py`
    - Sub-actions: `caps` (show capabilities), `start` (register monitor + stream events)
    - Flags: `--pattern OFF:AD:HEX` (repeatable), `--rssi-high/low`, `--rssi-high/low-timeout`, `--sampling-period`, `--duration`
    - Clean shutdown via SIGINT/SIGTERM

- [x] **BZ-12e** `--monitor` flag on `bleep scan` — `modes/scan_monitor.py` (completed 2026-05-21)

- [x] **BZ-12f** Documentation: `docs/adv_monitor.md` with usage examples — completed 2026-05-21
- [x] **BZ-12g** Tests: mock-based unit tests for AdvMonitor/AdvMonitorApp/AdvMonitorManager — 29 tests (completed 2026-05-21)

#### Sprint 5: Enrichment & Completeness (MEDIUM priority — v2.9.x)

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 8 | BZ-15 | DeviceSet1 interface (TWS/coordinated sets) | 2-3 hr | New: `dbuslayer/device_set.py` | [x] Sprint 5C |
| 9 | BZ-24 | Mesh ProvisionAgent1 OOB hook implementations | 2-3 hr | `mesh/provision_agent.py` | [x] Sprint 5C (BZ-24b) + Sprint 5D (BZ-24a/c) |
| 10 | BZ-13/14 | AdminPolicySet1 / AdminPolicyStatus1 | 1-2 hr | `dbuslayer/adapter.py`, device wrappers | [x] Sprint 5C |
| 11 | BZ-20a | Document deprecated profile APIs as intentionally unsupported | 30 min | `docs/bluez_interface_properties.md` | [x] Sprint 5E |

#### Sprint 6: Niche / Experimental (LOW priority — v3.0+, backlog)

| # | Gap ID | Item | Effort | Files | Status |
|---|--------|------|--------|-------|--------|
| 12 | BZ-9/10 | BatteryProvider registration | 1-2 hr | New: `dbuslayer/battery_provider.py` | [x] Sprint 5D |
| 13 | BZ-16 | Bearer.LE1 / Bearer.BREDR1 split interfaces | 1-2 hr | Device wrappers | [x] Sprint 5D |
| 14 | BZ-17 | Health Device Profile (HDP) | 2-3 hr | New: `dbuslayer/health.py` (if demanded) | [x] Sprint 5D (stub) |
| 15 | BZ-18 | SIM Access Profile | 1 hr | New: `dbuslayer/sap.py` (if demanded) | [x] Documented in `bl_classic_mode.md` §2.13 |
| 16 | BZ-19 | MediaAssistant1 (Broadcast Audio) | 2-3 hr | `dbuslayer/media_assistant.py` | [x] Sprint 5D |
| 17 | BZ-25 | Mesh reprovisioning methods | 1 hr | `mesh/provisioner.py` | [x] Sprint 5C |

---

### Items Confirmed PRESENT (No Gap)

For completeness, these BlueZ interfaces/features were verified as **fully implemented** in BLEEP:

| Interface / Feature | BLEEP Implementation |
|--------------------|--------------------|
| `Adapter1` — all properties (Address, AddressType, Name, Alias, Class, Powered, PowerState, Discoverable, Pairable, Connectable, timeouts, Discovering, UUIDs, Modalias, Roles, ExperimentalFeatures, Manufacturer, Version) | `dbuslayer/adapter.py`, `modes/adapter_config.py` |
| `Adapter1` — all methods (StartDiscovery, StopDiscovery, SetDiscoveryFilter, GetDiscoveryFilters, RemoveDevice) | `dbuslayer/adapter.py`, `dbuslayer/manager.py` |
| `Device1` — all properties (Address through PreferredBearer, Sets) | `dbuslayer/device_le.py`, `dbuslayer/device_classic.py` |
| `Device1` — methods (Connect, Disconnect, Pair, CancelPairing, ConnectProfile, DisconnectProfile, GetServiceRecords) | `dbuslayer/device_le.py`, `dbuslayer/device_classic.py`, `modes/pair.py` |
| `GattService1`, `GattCharacteristic1` (ReadValue, WriteValue, StartNotify, StopNotify, MTU, Notifying, Flags), `GattDescriptor1` | `dbuslayer/service.py`, `dbuslayer/characteristic.py`, `dbuslayer/descriptor.py` |
| `Agent1` — all methods (Release through Cancel), `AgentManager1` | `dbuslayer/agent.py`, `dbuslayer/agent_io.py` |
| `Battery1` (Percentage, Source) | `ble_ops/le/scan.py`, `ble_ops/common/conversion.py` |
| `Input1` (ReconnectMode) | `ble_ops/le/scan.py`, `ble_ops/common/conversion.py` |
| `Media1`, `MediaPlayer1`, `MediaTransport1`, `MediaControl1`, `MediaEndpoint1`, `MediaFolder1`, `MediaItem1` | `dbuslayer/media.py`, `dbuslayer/media_stream.py`, `dbuslayer/media_browse.py` |
| `Network1`, `NetworkServer1` | `dbuslayer/network.py`, `ble_ops/classic/pan.py` |
| `Profile1`, `ProfileManager1` | `dbuslayer/spp_profile.py` |
| OBEX: `Client1`, `Session1`, `Transfer1`, `ObjectPush1`, `FileTransfer1`, `PhonebookAccess1`, `MessageAccess1`, `Message1`, `Synchronization1`, `Image1` | `dbuslayer/obex_*.py`, `ble_ops/classic/` (pbap, map, opp, ftp, bip, sync) |
| `PropertiesChanged` / `InterfacesAdded` / `InterfacesRemoved` signal handling | `dbuslayer/signals.py` |
| Mesh: `Network1`, `Node1`, `Management1`, `Application1`, `Element1`, `Provisioner1` (partial), `ProvisionAgent1` (skeleton) | `mesh/` package |

---

## Specialized Testing Modes

- [x] **BLE CTF Mode Completion**
  - [x] Implement automated flag discovery patterns
  - [x] Create CTF-specific visualization of device state
  - [x] Add automated solve strategies for common challenge types
  - [x] Document CTF mode usage and extension points
  - [x] Validate against known CTF devices
  - [x] Add ability to write to any characteristic (not just Flag-Write)
  - [x] Add flexible data format options for writing values (hex, byte, string)

- [ ] **Pico-W Testing Mode**
  - [ ] Research Pico W BLE implementation specifics
  - [ ] Create Pico W device profile with expected characteristics
  - [ ] Implement special handlers for Pico W quirks
  - [ ] Build test suite for Pico W-specific features
  - [ ] Create documentation with Pico W examples

- [ ] **BW-16 Testing Mode**
  - [ ] Research BW-16 BLE stack implementation
  - [ ] Implement BW-16 specific enumeration helpers
  - [ ] Create test fixtures for BW-16 devices
  - [ ] Document BW-16 mode usage

- [ ] **Scratch Space Mode**
  - [ ] Design flexible command execution framework
  - [ ] Implement batch processing of operations
  - [ ] Add support for operation sequence files
  - [ ] Create examples of advanced workflows
  - [ ] Document extension points

## Advanced Control Features

- [x] **Signal Capture System**
  - [x] Create `bleep/signals/capture_config.py` for configuration
  - [x] Implement signal routing and filtering
  - [x] Add persistent signal configuration storage
  - [x] Create CLI for signal configuration
  - [x] Document signal capture patterns
  - [x] Create examples of signal capture workflows
  - [x] Fix signal integration with application startup
  - [x] Add proper database routes for read/write/notification events
  - [x] Enhance CTF module to properly emit signals for characteristic operations
  - [x] Implement robust error handling for signal processing

- [ ] **Offline Device Analysis**
  - [ ] Design device structure serialization format
  - [ ] Implement export/import of device structures
  - [ ] Create visualization tools for offline analysis
  - [ ] Add differential analysis between captures
  - [ ] Document offline analysis workflow

- [ ] **Directed Device Assessment**
  - [ ] **Phase 1: Design & Architecture** (2 weeks)
    - [ ] Design targeted scanning framework
      - [ ] Identify common Bluetooth vulnerability patterns
      - [ ] Review existing security assessment methodologies
      - [ ] Define assessment categories (authentication, encryption, firmware, etc.)
      - [ ] Create plugin-based assessment architecture
      - [ ] Design rule engine for vulnerability detection
      - [ ] Define interfaces between scanning and assessment components
    - [ ] Device fingerprinting system design
      - [ ] Create schema for device fingerprints
      - [ ] Define fingerprint matching algorithm 
      - [ ] Plan fingerprint storage and retrieval
      - [ ] Design multi-factor fingerprinting (service patterns, response timing, etc.)
      - [ ] Create manufacturer-specific detection patterns
  - [ ] **Phase 2: Core Implementation** (3 weeks)
    - [ ] Implement device fingerprinting
      - [ ] Implement fingerprint collection during scans
      - [ ] Create fingerprint matching and identification system
      - [ ] Build baseline database of common device fingerprints
      - [ ] Add manufacturer-specific detection logic
    - [ ] Create vulnerability assessment helpers
      - [ ] Implement authentication bypass detection
      - [ ] Develop weak encryption identification
      - [ ] Create plaintext credential transmission detection
      - [ ] Implement replay attack vulnerability detection
      - [ ] Add firmware version fingerprinting
      - [ ] Create modular system for new vulnerability checks
      - [ ] Develop severity scoring system for findings
  - [ ] **Phase 3: Reporting & Integration** (2 weeks)
    - [ ] Build reporting tools
      - [ ] Implement vulnerability report generator
      - [ ] Create multiple output formats (Markdown, JSON, HTML)
      - [ ] Add visualization capabilities for assessment results
      - [ ] Implement comparison tools for multiple assessments
      - [ ] Create trend analysis for device improvements over time
    - [ ] Integration with existing components
      - [ ] Integrate with AoI analysis system
      - [ ] Connect to observation database
      - [ ] Link with signal capture system
      - [ ] Add CLI commands for directed assessment
      - [ ] Create programmatic API for assessment functions
  - [ ] **Phase 4: Documentation & Polish** (1 week)
    - [ ] Document assessment methodologies
      - [ ] Create user guides for directed assessment
      - [ ] Document assessment plugin architecture
      - [ ] Provide examples of common vulnerability patterns
      - [ ] Create reference for all assessment commands
      - [ ] Add developer documentation for extending assessment capabilities
    - [ ] Final polish
      - [ ] Optimize performance for large-scale assessments
      - [ ] Implement caching for repeated assessments
      - [ ] Add progress reporting for long-running assessments
      - [ ] Create sample assessment configurations

## Documentation Improvements

> This section tracks gaps in current documentation, particularly for the device tracking and observation capabilities. Addressing these tasks will ensure users can fully leverage the existing features through both CLI and programmatic APIs.

- [x] **Device Tracking Documentation** (Complete)
  - [x] Create comprehensive programmatic API reference for observation module
    - [x] Document each function in `observations.py` with examples (see `observation_db.md` - "Public Function Reference" section)
    - [x] Add integration examples for custom scripts (see `observation_db.md` - "Programmatic Access" section)
    - [x] Create cookbook for common observation tasks (see `observation_db_schema.md` - "Advanced Query Cookbook" section)
    - [x] Document filtering and query techniques for device data (see `observation_db.md` and `observation_db_schema.md`)
  - [x] Enhance AOI Analyzer documentation
    - [x] Create dedicated `aoi_security_algorithms.md` file documenting all security analysis algorithms
    - [x] Add examples of direct usage of AOIAnalyser class methods (see `aoi_mode.md` and `aoi_implementation.md`)
    - [x] Document security analysis algorithms and scoring system (see `aoi_security_algorithms.md`)
    - [x] Provide customization examples for different analysis needs (see `aoi_customization_guide.md`)
  - [x] Add real-world usage scenarios
    - [x] Long-term device monitoring workflows (see `observation_db_usage_scenarios.md`)
    - [x] Enterprise device tracking patterns (see `observation_db_usage_scenarios.md`)
    - [x] Security assessment workflows using observation database (see `observation_db_usage_scenarios.md`)
    - [x] Integration examples with external systems (see `observation_db_usage_scenarios.md`)
  - [x] Document detailed database schema
    - [x] Create complete schema diagram with relationships (see `observation_db_schema.md`)
    - [x] Document each table and column with descriptions (see `observation_db_schema.md` - comprehensive table documentation)
    - [x] Add query examples for complex data extraction (see `observation_db_schema.md` - "Advanced Query Cookbook")
    - [x] Create migration guide for schema changes (see schema version history in `observation_db_schema.md`)

## Technical Scalability Improvements

- [x] **Database Optimization**
  - [x] Implement indexing strategy for observation database
  - [x] Add query optimization for large device sets
  - [x] Create database maintenance utilities
  - [x] Document database schema and optimization techniques

- [ ] **Automatic PIN Code Storage and Retrieval**
  - [ ] **Phase 1: Database Schema Extension** (2-4 hours)
    - [ ] Add `device_pin_codes` table to observation database schema
      - [ ] Columns: `mac` (TEXT, FK to devices), `pin_code` (TEXT, encrypted or plain based on security requirements), `pin_type` (TEXT: "legacy", "ssp_passkey"), `source` (TEXT: "user_entered", "auto_detected", "stored_from_pairing"), `last_used` (DATETIME), `success_count` (INT), `failure_count` (INT), `ts` (DATETIME)
      - [ ] Indexes: `idx_device_pin_codes_mac`, `idx_device_pin_codes_last_used`
      - [ ] Migration: Create v8 schema migration from v7
    - [ ] Add `upsert_device_pin_code(mac: str, pin_code: str, pin_type: str, source: str)` function
    - [ ] Add `get_device_pin_code(mac: str, pin_type: str) -> Optional[str]` function
    - [ ] Add `get_device_pin_codes(mac: str) -> List[Dict]` function for all PIN types
    - [ ] Add `increment_pin_success(mac: str, pin_code: str)` and `increment_pin_failure(mac: str, pin_code: str)` functions
    - [ ] Update `__all__` export list
  - [ ] **Phase 2: IO Handler Integration** (4-6 hours)
    - [ ] Create `DatabaseIOHandler` class extending `AgentIOHandler`
      - [ ] Implement `request_pin_code()` to query database first, fallback to default/user input
      - [ ] Implement `request_passkey()` to query database first, fallback to default/user input
      - [ ] Store successful PIN codes after successful pairing
      - [ ] Track PIN code usage statistics (success/failure counts)
    - [ ] Modify `AutoAcceptIOHandler` to support database lookup
      - [ ] Add optional `use_database: bool` parameter
      - [ ] Query database before returning default PIN
      - [ ] Store PIN codes after successful pairing
    - [ ] Modify `ProgrammaticIOHandler` to support database lookup
      - [ ] Add optional `use_database: bool` parameter
      - [ ] Query database before calling callback or returning default
    - [ ] Modify `CliIOHandler` to support database lookup
      - [ ] Add optional `use_database: bool` parameter
      - [ ] Query database and suggest PIN to user
      - [ ] Store user-entered PIN codes after successful pairing
  - [ ] **Phase 3: Agent Integration** (3-4 hours)
    - [ ] Update `create_agent()` to accept `use_database_pin: bool` parameter
    - [ ] Update `SimpleAgent`, `InteractiveAgent`, `EnhancedAgent`, `PairingAgent` to support database PIN lookup
    - [ ] Add `--use-database-pin` CLI argument to `bleep agent` command
    - [ ] Integrate PIN storage after successful pairing in agent methods
    - [ ] Add logging for database PIN lookup (success/failure, source)
  - [ ] **Phase 4: Pairing Success Detection** (2-3 hours)
    - [ ] Detect successful pairing completion
      - [ ] Monitor `PropertiesChanged` signal for `Paired=True` property
      - [ ] Correlate with recent `RequestPinCode`/`RequestPasskey` events
      - [ ] Store PIN code used in successful pairing
    - [ ] Handle pairing failure scenarios
      - [ ] Track failed PIN attempts (don't store failed PINs)
      - [ ] Increment failure count for stored PINs
      - [ ] Optionally remove PINs with high failure rates
  - [ ] **Phase 5: CLI and Documentation** (2-3 hours)
    - [ ] Add `bleep db pin-codes` command to list stored PIN codes
    - [ ] Add `bleep db pin-code <MAC> [--set <PIN>]` command to view/set PIN codes
    - [ ] Add `bleep db pin-code <MAC> --remove` command to delete stored PIN codes
    - [ ] Update `observation_db.md` with PIN code storage documentation
    - [ ] Update `agent_mode.md` with `--use-database-pin` flag documentation
    - [ ] Add examples of automatic PIN code usage
    - [ ] Document security considerations (encryption, plain text storage)
  - [ ] **Phase 6: Testing and Validation** (2-3 hours)
    - [ ] Unit tests for database PIN code functions
    - [ ] Integration tests for database IO handler
    - [ ] Test PIN code retrieval during pairing
    - [ ] Test PIN code storage after successful pairing
    - [ ] Test fallback behavior when database PIN not found
    - [ ] Test CLI commands for PIN code management
  - [ ] **Security Considerations**:
    - [ ] Document whether PIN codes should be encrypted at rest
    - [ ] Consider adding `--encrypt-pins` flag for sensitive deployments
    - [ ] Add option to mask PIN codes in logs (already partially implemented)
    - [ ] Document access control recommendations for database file
  - [ ] **Future Enhancements** (not in initial implementation):
    - [ ] PIN code encryption at rest
    - [ ] Per-device PIN code expiration
    - [ ] PIN code rotation policies
    - [ ] Integration with external credential stores
    - [ ] PIN code sharing across multiple BLEEP instances

- [ ] **Memory Management**
  - [ ] Audit large data structure usage
  - [ ] Implement lazy loading patterns for device maps
  - [ ] Add resource cleanup hooks
    - [ ] **Device object cleanup** (`bleep/dbuslayer/device_le.py`, `bleep/dbuslayer/device_classic.py`)
      - [ ] Add `cleanup()` method to device classes (clear GATT mappings, unregister signal handlers, release D-Bus proxy references, clear cached data)
      - [ ] Add `__del__()` method for automatic cleanup (with error handling)
      - [ ] Add context manager support (`__enter__`, `__exit__`)
    - [ ] **Signal handler cleanup** (`bleep/dbuslayer/signals.py`)
      - [ ] Ensure all signal handlers can be unregistered
      - [ ] Add `unregister_device()` method to signals manager
      - [ ] Track registered handlers for cleanup
      - [ ] Add cleanup in device `__del__` methods
    - [ ] **D-Bus connection cleanup** (`bleep/dbus/connection_pool.py`)
      - [ ] Ensure connections are properly closed
      - [ ] Add connection age limits
      - [ ] Implement automatic cleanup of stale connections
      - [ ] Add `cleanup_stale_connections()` method
    - [ ] **Cache size limits** (`bleep/dbuslayer/bond_storage.py`)
      - [ ] Add max size limit to `PairingCache`
      - [ ] Implement LRU eviction when cache exceeds limit
      - [ ] Add `max_size` parameter to `__init__()`
      - [ ] Add `get_cache_stats()` method
    - [ ] **Database query result streaming** (`bleep/core/observations/`)
      - [ ] For large result sets, use generators instead of lists
      - [ ] Modify `get_devices()` to support streaming mode
      - [ ] Add `get_devices_streaming()` function for large datasets
      - [ ] Update `get_characteristic_timeline()` to use generators for large limits
  - [ ] Document memory usage patterns and recommendations

- [x] **D-Bus Reliability**
  - [x] Enhance BlueZ stall detection
    - [x] Implement timeout enforcement layer for D-Bus method calls (`bleep/dbus/timeout_manager.py`)
    - [x] Create heartbeat mechanism to detect unresponsive BlueZ services (`bleep/dbuslayer/bluez_monitor.py`)
    - [x] Implement controller health metrics collection (`bleep/core/metrics.py`)
  - [x] Implement automatic recovery strategies
    - [x] Build connection reset manager with staged recovery (`bleep/dbuslayer/recovery.py`)
    - [x] Develop state preservation system for connection recovery (`bleep/dbuslayer/recovery.py`)
    - [x] Add progressive backoff for reconnection attempts (`bleep/dbuslayer/recovery.py`)
  - [x] Add connection pooling for high-volume operations
    - [x] Create managed pool of D-Bus connections (`bleep/dbus/connection_pool.py`)
    - [x] Implement D-Bus proxy object cache (`bleep/dbus/connection_pool.py`)
    - [x] Add request batching for related operations (`bleep/dbus/connection_pool.py`)
  - [x] Document D-Bus reliability best practices
    - [x] Create comprehensive D-Bus interaction guidelines (`bleep/docs/dbus_best_practices.md`)
    - [x] Document common failure modes and recovery patterns (`bleep/docs/dbus_best_practices.md`)
    - [x] Add examples and templates for robust D-Bus usage (`bleep/docs/d-bus-reliability.md`)
    - [x] Create diagnostic tools for troubleshooting (`bleep/scripts/dbus_diagnostic.py`)

- [x] **RSSI Capture Enhancement for Scan Operations** - **COMPLETE**
  - [x] **Phase 1: RSSI capture during discovery** (`bleep/dbuslayer/manager.py`, `bleep/dbuslayer/signals.py`)
    - [x] Add `_rssi_cache` dictionary and `_rssi_cache_lock` to `system_dbus__bluez_device_manager` class
    - [x] Add `_discovery_active` flag and `is_discovery_active()` method to track discovery state
    - [x] Implement `_capture_rssi_from_signal(mac_address: str, rssi: int)` method to store RSSI in cache
    - [x] Add `get_captured_rssi(mac_address: str) -> Optional[int]` method to retrieve cached RSSI
    - [x] Add `clear_rssi_cache()` method to clear cache when discovery starts/stops
    - [x] Enhance `_properties_changed()` in `system_dbus__bluez_signals` to detect RSSI updates and forward to DeviceManager
    - [x] Add `register_device_manager()` method to signals manager for RSSI forwarding
  - [x] **Phase 2: RSSI merge in get_discovered_devices()** (`bleep/dbuslayer/adapter.py`)
    - [x] Store `_device_manager` reference in `system_dbus__bluez_adapter` class (already exists via `create_device_manager()`)
    - [x] Enhance `get_discovered_devices()` to merge RSSI from DeviceManager cache after `GetManagedObjects()` results
    - [x] Update device dict with cached RSSI if available and current RSSI is None
    - [x] Fix MAC address format mismatch - normalize to lowercase for cache lookup
  - [x] **Phase 3: Properties.Get() fallback (connected devices only)** (`bleep/dbuslayer/adapter.py`)
    - [x] Add fallback logic to query `Properties.Get(DEVICE_INTERFACE, "RSSI")` for devices with `None` RSSI
    - [x] Only query Properties.Get() for devices where `connected == True`
    - [x] Skip Properties.Get() for disconnected devices (accept "? dBm" as expected behavior)
    - [x] Handle `DBusException` gracefully (RSSI may not exist even for connected devices)
  - [x] **Phase 4: Integration and cleanup** (`bleep/dbuslayer/manager.py`)
    - [x] Clear RSSI cache in `start_discovery()` before starting discovery
    - [x] Preserve RSSI cache after discovery completes (removed premature clearing in `_cleanup_after_run()`)
    - [x] Register DeviceManager with signals manager in `run()` method for RSSI forwarding
  - [x] **Phase 5: Testing and validation** - **Validated in production**
    - [x] RSSI values now appear correctly in scan results
    - [x] MAC address format normalization verified
    - [x] Cache timing issues resolved
    - [x] Backward compatibility maintained (existing scan functionality unchanged)

## CLI Command Enhancements (Completed)

- [x] **UUID Translation System** – Comprehensive UUID translation functionality:
  - [x] Core translation engine (`bleep/bt_ref/uuid_translator.py`) with modular architecture
  - [x] Support for 16-bit, 32-bit, and 128-bit UUID formats
  - [x] Automatic expansion of 16-bit UUIDs to find all potential matches
  - [x] Searches across all BLEEP UUID databases (Services, Characteristics, Descriptors, Members, SDOs, Service Classes, Custom)
  - [x] CLI command (`bleep uuid-translate` / `bleep uuid-lookup`) with JSON and verbose options
  - [x] Interactive mode integration (`uuid` command)
  - [x] User mode integration (menu option 5)
  - [x] Comprehensive documentation (`uuid_translation.md`, `uuid_translation_plan.md`)
  - [x] Complete test suite with all tests passing
  - [x] Modular design for easy extension (custom format handlers, new database sources)

- [x] **Explore Command Fixes**
  - [x] Fix parameter conflict between CLI mode and connection mode
  - [x] Improve passive scan reliability with better timeout distribution
  - [x] Add proper connection retries to passive mode
  - [x] Update help text and documentation
  - [x] Create comprehensive documentation in `explore_mode.md`

- [x] **Analyze Command Enhancements**
  - [x] Add support for both American (`analyze`) and British (`analyse`) spellings
  - [x] Implement detailed analysis mode with `--detailed` flag
  - [x] Fix JSON format compatibility for different file structures
  - [x] Improve output formatting with device information
  - [x] Create comprehensive documentation in `analysis_mode.md`

- [x] **Other CLI Improvements**
  - [x] Add debug flag to `classic-scan` mode
  - [x] Fix `aoi` mode to accept test file parameter, resolve sys module scope issue, and automatically use 'scan' subcommand
  - [x] Fix `aoi` mode errors by adding missing NotAuthorizedError class and fixing return value handling
  - [x] Fix `aoi` subcommands (analyze, list, report, export) to properly work with the CLI
  - [x] Add proper parameter handling for all AOI subcommands in the CLI parser
  - [x] Implement basic device data storage and retrieval for AOI mode
  - [x] Implement report generation in three formats (markdown, JSON, text) for AOI mode
  - [x] Add fallback analysis for AOI analyze command when full implementation is missing
  - [x] Create comprehensive documentation for the AOI mode in `aoi_mode.md`
  - [x] Fix user mode scan incorrectly reporting "no devices found" when devices are actually found
  - [x] Fix _native_scan function to properly return device dictionary instead of status code
  - [x] Add quiet parameter to passive_scan to prevent duplicate output
  - [x] Improve device display format in user mode scan to use "Address (Name) - RSSI: value dBm" format
  - [x] Update device menu options to consistently use the same format
  - [x] Fix InvalidArgs error when connecting to OnePlus devices
  - [x] Fix MediaPlayer1 Press method to accept hex values

## Previous and unincorporated To Do lists:

### TODO:
   [ ] Create a function that searches through the Managed Objects for known Bluetooth objects (to the device that the code is running on)
       - Note: Could make good OSINT capabilitiy
   [ ] Check to see what type of device is being connected to
       [ ] If BLE then connect with BLE Class structure
       [ ] If BT then connect with Bluetooth Classic structure
   [x] Create function mode that allows connecting directly to a specific device
       - Note: Would attempt to connect regardless if in range of not; leverage D-Bus API (adapter? expermental capability)
   [x] Improve error handling so that errors due not set everything to "None" but produce another set output (e.g. "ERROR")
   [ ] Update the expected code structures bsaed on the updated BlueZ git documentation
       - e.g. Error Codes, Responses, S/C/D properties
       [ ] Look at updating any internal/code JSON references for expected data-structures
   [ ] Create a decode + translation function for ManufacturerData using the "formattypes.yaml" BT SIG document
       - Expectation is that this is how one can interpret the rest of the passed information where the SECOND OCTET is the "formattype" data type indicator
   [x] Create a decode + translation function for Class data
       [x] Hardcode Transation first to prove concept
       [ ] Move to automatic pull down of YAML to perform conversion
   [x] Create a decode for appearance values
       - Pull from bluetooth support files to better identify (e.g. similar to Class data)
   [x] Add PnP ID characteristic (0x2A50) decoding into the "detailed on" verbosity within the Debug Mode
       - Correctly identify and display Device ID information from PnP ID and modalias
   [ ] Add functionality to re-read/refresh the device interface information
       - Note: This is most likely where the D-Bus can read the GAP information (i.e. 0x1800)
   [x] Add read-in and generation of UUIDs to create UUID Check lists (Service, Characteristic, Descriptor)
       - [x] Implemented comprehensive UUID translation system with CLI command
       - [x] Supports all UUID types (Service, Characteristic, Descriptor, Member, SDO, Service Class)
       - [x] Interactive and programmatic access via `bleep uuid-translate` command
       - [x] Integrated into interactive and user modes
   [ ] Make use of the "ARDUINO_BLE__BLE_UUID__MASK" variable to identify "groupings" of UUIDs
       - Note: May be using the same Bluetooth SIG default UUID structure
   [ ] Determine why pairing a device causes BIP to lose conneciton to the device
   [x] Improving decoding information to use the BT SIG yaml files
   [ ] Have the Mine/Permission mapping include a tracking of the associated error
       - Make as a tuple? Perhaps dictionary?
   [ ] Determine how to query if an action is in process for D-Bus/BlueZ
   [ ] Add pairing to BLEEP
       [ ] Basic pairing to a targeted device
       [ ] Selective pairing to a targeted device
       - Note: Research on the process shows that the communication "handshake" for Pairing() begins, but then fails due to lack of agent
           - URL:      https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc/org.bluez.Agent.rst
### TODO (vendor-specific SDP services / proprietary profiles):
   [ ] Samsung IcService_New (`a23d00bc-217c-123b-9c00-fc44577136ee`) — reverse-engineer wire protocol
       - Observed on SAMSUNG-SM-G891A (Galaxy S7 Active), RFCOMM channel 5
       - UUID registered in `bleep/bt_ref/constants.py`, documented in `bleep/docs/bl_classic_mode.md`
       - Service accepts RFCOMM connections when phone is awake/unlocked, but uses unknown proprietary protocol
       - Probe result: [SILENT] after ~5s — no initial banner or handshake from remote
       - `copen 5` + `craw` → `str:HELO send` → 9B sent, no response from device
       - Gap: No protocol dissector — only raw RFCOMM I/O via copen/csend/crecv/craw
       - Gap: No dedicated command suite (e.g. `cicservice`) for structured interaction
       - Gap: Phone screen must be awake for RFCOMM channel to accept connections
       [ ] Capture and analyze traffic between Samsung Flow PC client ↔ phone to reverse-engineer the protocol framing
       [ ] Identify handshake/auth sequence (likely Samsung Accessory Protocol or SMEP variant)
       [ ] Determine if the service responds to Samsung Accessory SDK discovery messages
       [ ] Cross-reference UUID against Samsung firmware decompilations (e.g. `com.samsung.android.app.accessoryservice`)
       [ ] Add UUID to `SPEC_UUID_NAMES__SERV_CLASS` or equivalent for automatic resolution via `get_name_from_uuid()`
       - References:
           - Microsoft Q&A #3840559: https://learn.microsoft.com/en-us/answers/questions/3840559/accidentally-deleted-icservice-new-driver-possibly
           - Microsoft Q&A #3284030: https://learn.microsoft.com/en-us/answers/questions/3284030/windows-was-unable-to-install-icservice-new-sms-mm
           - Samsung Accessory SDK: https://developer.samsung.com/galaxy/accessory
           - BlueZ vendor UUID discussion: https://github.com/bluez/bluez/issues/963
   [ ] Catalog other vendor-specific SDP services observed during field testing
       - BT DIAG (UUID 0x1101, Samsung/LG) — diagnostic serial channel, already observed on 14:89:FD:31:8A:7E
       - SPPSERVICE3 (`b4a9d6a0-b2e3-4e40-976d-a69f167ea895`) — Samsung, Bixby-related
       - SPPSERVICE4 / SMEP (`f8620674-a1ed-41ab-a8b9-de9ad655729d`) — Samsung proprietary protocol
       [ ] Add observed vendor UUIDs to `bleep/bt_ref/constants.py` as they are discovered
       [ ] Consider a `vendor_services.py` registry if the list grows beyond ~10 entries

### TODO (arduino):
   [ ] Create function for starting a user interaction interface for a SPECIFIC ADDRESS
   [ ] Clean-up and polish the user interaction interface screens
   [ ] Add to the General Services Information Output:
       [ ] ASCii print out for all Hex Array Values (S/C/D)
       [ ] Handle print out for all S/C/D              <---- Note: This comes from the FOUR HEX of the [serv|char|desc]XXXX tags; BUT DIFFERENT FROM Characteristic Value Handle

### TODO (capabilities)
    [ ] Force Media Players to end ALL PLAYING AUDIO by "... setting position to the maxmium uint32 value."
        - Purpose is to allow bleep to identify MediaPlayer devices and force current media to stop playing

### TODO (rfcomm-security):
    [ ] Add BT_SECURITY socket option support to RFCOMM connections
        - Currently `bleep/ble_ops/classic/connect.py:classic_rfccomm_open()` opens a raw
          RFCOMM socket with no security level set — the kernel applies its own defaults.
        - BlueZ userspace demonstrates the correct pattern in `workDir/bluez/btio/btio.c`:
            - `set_sec_level()` (lines 453–494): sets `SOL_BLUETOOTH` / `BT_SECURITY` on the
              socket before `connect()`; falls back to `SOL_RFCOMM` / `RFCOMM_LM` when the
              kernel returns `ENOPROTOOPT`.
            - `rfcomm_set_lm()` (lines 438–450): maps `BT_SECURITY_LOW` → `RFCOMM_LM_AUTH`,
              `BT_SECURITY_MEDIUM` → `AUTH | ENCRYPT`, `BT_SECURITY_HIGH` → `AUTH | ENCRYPT | SECURE`.
            - `rfcomm_set()` (lines 763–774): applies security + central role before use.
            - `rfcomm_connect()` (lines 746–761): plain `connect()` after security is configured.
        - BlueZ profile defaults from `workDir/bluez/src/profile.c`:
            - `ext_set_defaults()` (line 2174–2180): defaults external profiles to `BT_IO_SEC_MEDIUM`.
            - OPP explicitly sets `BT_IO_SEC_LOW` (lines 2111–2118).
            - OBEX client (`workDir/bluez/obexd/client/bluetooth.c`, lines 104–122) uses `BT_IO_SEC_LOW`.
        - Security constants from `workDir/bluez/lib/bluetooth.h` (lines 52–61):
            - `BT_SECURITY` = 4, levels: SDP=0, LOW=1, MEDIUM=2, HIGH=3, FIPS=4.
        - RFCOMM LM constants from `workDir/bluez/lib/rfcomm.h` (lines 40–46):
            - `RFCOMM_LM` = 0x03, `RFCOMM_LM_AUTH` = 0x0002, `RFCOMM_LM_ENCRYPT` = 0x0004,
              `RFCOMM_LM_SECURE` = 0x0020.
        - Implementation approach:
            [ ] Add optional `sec_level` parameter to `classic_rfccomm_open()` (default: MEDIUM)
            [ ] Before `sock.connect()`, call `sock.setsockopt(SOL_BLUETOOTH, BT_SECURITY, ...)`
                with fallback to `sock.setsockopt(SOL_RFCOMM, RFCOMM_LM, ...)` on ENOPROTOOPT,
                mirroring the btio.c pattern
            [ ] Expose sec_level through CLI flags on classic-connect, debug ckeep/copen
            [ ] Verify Python `socket` module exposes SOL_BLUETOOTH / BT_SECURITY constants
                (may require ctypes or hard-coded values: SOL_BLUETOOTH=274, BT_SECURITY=4)

## MAP CLI Auto-Resolve Intermediate Folders (Future Work)

**Goal**: Enhance `list_messages()` in `bleep/ble_ops/classic/map.py` to detect when the requested folder is an intermediate directory (has subfolders, not messages) and automatically enumerate its subtree to find and list messages from all leaf descendants.

**Context**: The MAP specification allows varied folder hierarchies across devices — some devices use a deep structure (`telecom/msg/{inbox,draft,sent,outbox,deleted}`) while others store messages directly in `telecom/`.  Currently, when a user requests `list_messages("telecom")` on a device with the deep structure, the remote MAS returns OBEX "Bad Request" because `telecom/` is a structural folder, not a message container.  The CLI now provides helpful recovery hints (see Fix 2 in MAP CLI Folder Enumeration Fix below), but does not auto-descend.

**Proposed approach**:
- [ ] In `list_messages()`, catch "Bad Request" from `ListMessages` on the first attempt
- [ ] When caught, call `walk_folder_tree()` from the current position to discover leaf subfolders
- [ ] Re-issue `ListMessages` against each discovered leaf folder, aggregating results
- [ ] Tag each returned message with its actual source folder path for caller disambiguation
- [ ] Preserve existing behavior for leaf folders (no extra round-trips)

**Dependencies**: Requires the recursive `walk_folder_tree()` and `collect_leaf_paths()` utilities already in the operations layer.

**Risk**: Additional OBEX session round-trips on devices with deep hierarchies; should be gated behind the "Bad Request" error path only (zero cost on the happy path).

---

## BLEEP v3.0 Expansion Plan — API-Ready Architecture (2026-05-18) – COMPLETE (Phases 1–7 complete)

**Origin**: Comprehensive audit of the entire `bleep/` codebase (176 Python files, ~69k functional LOC), `workDir/BlueZDocs/`, `workDir/BlueZScripts/`, internal documentation (61 `.md` files in `bleep/docs/`), refactoring lessons (`BLEEP_REFACTOR_LESSONS.md` §1-22), field notes (`Observations/field-notes-lessons-learned.md` L-1 through L-16), and both PRDs in `.taskmaster/docs/`.

**Goal**: Prepare BLEEP for use as a robust CLI/API toolset where the observation database and survey-mode output serve as primary structured-data surfaces, while all other modes retain full CLI terminal output and are progressively augmented with structured output capability following the proven Survey Mode pattern.

**Governing principles**:
1. Database + Survey are first-class API surfaces; other modes output to terminal and are augmented later
2. CLI remains the primary interface — minimal, efficient, no degradation
3. Multi-output capability follows the Survey pattern (progress→stderr, data→stdout/file)
4. Modular v2.+ architecture is maintained — no monolith regression
5. ALL BlueZ capabilities in scope — deprecated profiles handled via GATT-level recognition
6. `bleep-mcp/` codebase is untrusted — clean-room API design from BLEEP internals
7. Functionality and robustness over any form of GUI or external interface

**Known library constraints incorporated** (from `mainloop_architecture.md`, `mainloop_requirement_analysis.md`, `agent_dbus_communication_issue.md`, `pan_connection_analysis.md`, `d-bus-reliability.md`, `dbus_best_practices.md`):
- `dbus.service.Object` handlers dispatch only with `GLib.MainLoop().run()` on main thread
- `bus.add_message_filter()` interferes with handler dispatch (disable during pairing)
- `Network1.Connect()` returns before BNEP handshake completes (post-connect verify required)
- BlueZ exposes no max connection count property (handle `ConnectionLimitError` gracefully)
- `RegisterEndpoint()` alone does not trigger AVDTP negotiation (use `--system` audio approach)
- `obexd` AppArmor restrictions require two-stage file handling (staging dir → final dir)
- `descriptor.read_value()` swallows exceptions internally (retry wrappers ineffective)
- MAP push requires inter-push delay (1.5s default) to avoid obexd session exhaustion
- Singleton `dbus.SystemBus()` without MainLoop drops media endpoint callbacks (use private bus)

---

### Phase 1 — Documentation Corrections & Dead Code Removal — COMPLETED (2026-05-18/19)

**Scope**: No behavioral changes. Fix documentation drift, remove non-functional packages, update stale metadata.

- [x] **P1-1** Update `observation_db_schema.md` to reflect schema v11: document `aoi_analysis.pairing_profile`, `aoi_analysis.sdp_summary`, `aoi_analysis.post_pair_delta` columns added in v2.8.4
- [x] **P1-2** Update `mesh/__init__.py` docstring line 4: change `workDir/bluez/doc/mesh-api.txt` (does not exist) to `workDir/BlueZDocs/mesh-api.txt`
- [x] **P1-3** Verify `dbus_documentation_index.md` path references: confirmed `timeout_manager.py` and `connection_pool.py` correctly live in `bleep/dbus/`, other files in `bleep/dbuslayer/` — no changes needed (paths were already correct)
- [ ] ~~**P1-4**~~ **OUT OF SCOPE** — `README.md` is a project-root file, not within `bleep/` codebase.  URL corrected to `https://github.com/Mauddib28/bleep-tool.git` but modification was outside declared scope.
- [x] **P1-5** Update `setup.py` version from `2.7.25` to match `bleep/__init__.py` (`2.8.4`)
- [x] **P1-6** Update `.taskmaster/docs/bleep-refactor-gap-analysis-prd.txt`: mark debug mode, BLE CTF mode, advanced scanning modes, pairing/bonding, media support, Bluetooth Classic support as **implemented** (gap analysis is stale — these were completed in v2.7-v2.8)
- [x] **P1-7** Update `README.refactor`: mark completion percentages as accurate or archive the file
- [x] **P1-8** Update BZ gap summary table (this file, line ~4081): correct BZ-6/7 status to `**DONE** (Sprint 2)`, BZ-8 to `**DONE** (Sprint 1)`, BZ-11/12 to `**DONE** (Sprint 4)`
- [ ] ~~**P1-9**~~ **REVERTED** — `bleep/gatt/` is NOT dead code; it is an intentional refactoring target for breaking up large BLE GATT files into smaller modules (≤300 LOC goal).  Package restored with updated docstring clarifying its purpose.
- [x] **P1-10** Wire BZ-1e: add `--stream` flag to debug mode `read`/`write` commands to use `acquire_write()`/`acquire_notify()` fd-based streaming (code in `dbuslayer/characteristic.py` already complete)
- [x] **P1-11** Wire BZ-8f: surface disconnect reason (`disconnect_reason`, `disconnect_message`, `disconnect_human` from `signals._device_connection_states`) in debug mode `info` command and scan output (code in `dbuslayer/signals.py` already complete).  Scan output wiring added 2026-05-19: `_log_disconnect_reason()` helper in `connect.py`, called from `connect.py` (services-not-resolved).  As of P4-3, `scan_modes.py` delegates to `connect.py` which handles disconnect-reason logging internally.

---

### Phase 2 Preparation — COMPLETED (2026-05-19)

The following preparation work was completed prior to beginning Phase 2 implementation:

- [x] **PREP-1** Refactored `bleep/core/observations.py` (2065 LOC monolith) into a package (`bleep/core/observations/`) with 10 focused submodules: `_connection.py`, `_devices.py`, `_services.py`, `_history.py`, `_media.py`, `_aoi.py`, `_signals.py`, `_evidence.py`, `_maintenance.py`, `__init__.py`.  All public symbols re-exported for backward compatibility.  437 tests pass unchanged.
- [x] **PREP-2** Established reusable `obs_db` pytest fixture in `tests/conftest.py` — provides clean, isolated temp DB for any test needing observation persistence.
- [x] **PREP-3** Validated `insert_adv()` works correctly with 4 focused tests (`tests/test_insert_adv.py`): row persistence, invalid MAC rejection, auto device-stub creation, multiple reports.
- [x] **PREP-4** Verified Phase 1 completion: `__version__` = 2.8.4, `setup.py` = 2.8.4, schema version = 11, `gatt/__init__.py` = valid package, no uncommitted changes to observation code.
- [x] **PREP-5** Confirmed schema migration pattern for v12: sequential `if current_version == N:` blocks with individual `try/except pass` for `ALTER TABLE` additions (documented in `_connection.py`).

---

### Phase 2 — Database Persistence Gap Closure — COMPLETED (2026-05-19)

**Scope**: Close the gaps where CLI terminal output contains data not persisted to the observation database. The DB must capture all data currently shown in terminal output before it can serve as a reliable API data source.

**Audit findings** (2026-05-18): The following data domains are printed to terminal but have **zero** DB persistence:

| Domain | Affected Modes | Root Cause |
|--------|---------------|------------|
| Signal/notification values | `signal` | No `observations` import in module |
| Pairing workflow (PIN, probe results, brute-force, auth matrix, state booleans) | `agent`, `pair` | Neither module imports `observations` |
| Media enumeration (players, transports, endpoints, codecs, browse trees) | `media`, `media-enum` CLI | Only one code path calls `snapshot_media_*` |
| Audio profiles + recon (ALSA correlation, sox analysis, recordings) | `audio` | Entire mode has zero DB interaction |
| Landmine/security maps | `exploration`, `gatt-enum`, `aoi` | Calculated and returned but never stored |
| Advertisement history | `scan` | `adv_reports` table exists but `insert_adv()` is never called |
| Survey-specific metadata (sighting count, fingerprint_changed, is_cached, UUID list) | `survey` | In output JSON but not in DB |

#### P2-A: Schema Additions — COMPLETED (2026-05-19)

- [x] **P2-A1** Add `pairing_events` table: `(id PK, mac FK→devices, ts DATETIME, method TEXT, pin TEXT, result TEXT, capabilities TEXT, auth_matrix JSON, brute_attempts INT, brute_duration REAL, pre_pair_state JSON, post_pair_state JSON)` — captures full pairing workflow per attempt
- [x] **P2-A2** Add `security_maps` table: `(id PK, mac FK→devices, ts DATETIME, landmine_map JSON, permission_map JSON, enumeration_annotations JSON, source TEXT)` — persists per-enumeration security analysis
- [x] **P2-A3** Add `media_enumerations` table: `(id PK, mac FK→devices, ts DATETIME, players JSON, transports JSON, endpoints JSON, browse_tree JSON, capabilities JSON)` — captures full media-enum JSON blob
- [x] **P2-A4** Add `audio_recon` table: `(id PK, ts DATETIME, backend TEXT, cards JSON, pcms JSON, recordings JSON, sox_analysis JSON, contention JSON)` — audio recon is host-level, not per-device; mac is NULL
- [x] **P2-A5** Add columns to `devices` table: `uuids JSON` (advertised UUID list), `paired BOOLEAN`, `trusted BOOLEAN`, `bonded BOOLEAN` — connection state booleans currently printed but never stored
- [x] **P2-A6** Add columns to `sdp_records` table: `mas_instance_id INT`, `supported_message_types TEXT`, `supported_features TEXT` — MAP-specific SDP fields currently parsed but discarded
- [x] **P2-A7** Add columns to `devices` table: `sighting_count INT`, `fingerprint_changed BOOLEAN` — survey-specific metadata currently in JSON output but not DB
- [x] **P2-A8** Schema version bump: `_SCHEMA_VERSION` = 12 in `bleep/core/observations/_connection.py`, v11→v12 migration block, `_SCHEMA_SQL` DDL updated

#### P2-B: Persistence Wiring — COMPLETED (2026-05-19)

- [x] **P2-B1** `signal` mode: `insert_char_history()` in `_notify_cb` handler (`bleep/modes/signal.py`)
- [x] **P2-B2** `pair` mode: `store_pairing_event()` in `_do_pair`, `_do_probe`, `_do_brute` (`bleep/modes/pair.py`) — captures method, PIN, result, auth matrix, brute stats, pre/post state
- [x] **P2-B3** `agent` mode: `store_pairing_event()` + `upsert_device(paired=True)` in agent pairing callbacks (`bleep/modes/agent.py`)
- [x] **P2-B4** `media-enum` CLI: `store_media_enumeration()` with full JSON blob (`bleep/cli.py`)
- [x] **P2-B5** `audio` mode: `store_audio_recon()` at end of `run_audio_recon()` (`bleep/ble_ops/audio/audio_recon.py`)
- [x] **P2-B6** `exploration` mode: `store_security_maps()` in `save_to_database()` (`bleep/modes/exploration.py`)
- [x] **P2-B7** `aoi` mode: `store_security_maps()` after scan pipeline (`bleep/modes/aoi.py`)
- [x] **P2-B8** `scan` mode: `insert_adv()` in `_native_scan()` per-device loop (`bleep/ble_ops/le/scan.py`)
- [x] **P2-B9** `survey` mode: `upsert_device(sighting_count=, fingerprint_changed=, uuids=)` after main loop (`bleep/modes/survey.py`)
- [x] **P2-B10** `scan`/`survey`: advertised UUID list persisted via `upsert_device(uuids=)` in `_native_scan()` and survey classic round
- [x] **P2-B11** `scan`/`media`/`pair`/`agent`: connection state booleans (`paired`, `trusted`, `bonded`) via `upsert_device()` in `_native_scan()` and `_enrich_device_info_from_props()`

---

### Phase 3 Preparation — COMPLETED (2026-05-19)

The following preparation work was completed prior to beginning Phase 3 implementation.
Mirrors the Phase 2 prep pattern (PREP-1 through PREP-5) to validate infrastructure before wiring.

**Reference implementation audit** (Survey Mode `bleep/modes/survey.py`):
- Progress/status → `print(..., file=sys.stderr)` with `[survey]` prefix
- Data output → `json.dumps()` to stdout (default) or file (via `-o`)
- Entry point → `def main(argv: list[str] | None = None) -> int`
- Exit codes → `0` success, `1` error
- Existing `--quiet` only suppresses per-device output, not progress
- Existing `--live` flag enables round-by-round progress

**CLI dispatch audit** (`bleep/cli.py`, 2934 LOC, 13 `sys.argv` references):
- **Pattern A** (4 modes: `survey`→FIXED, `agent`, `pair`, `classic-connect`): `sys.argv[2:]` slicing, bypasses argparse for mode detection
- **Pattern B** (1 mode: `explore`): `sys.argv` mutation — saves, overwrites, calls `main()`, restores
- **Pattern C** (7 modes: `db`, `user`, `signal`, `signal-config`, `analyse`, `aoi`, `uuid-translate`): Manual opt-list construction from parsed args → re-parsed by mode
- **Pattern D** (many modes): Direct function call with extracted `args.*` fields — already Phase 3 compatible
- **Pattern E** (3 modes: `interactive`, `ctf`, `audio-config`): No-dispatch / inline implementation

- [x] **PREP-3-1** Create `bleep/core/output.py` with `OutputContext` dataclass: `mode` (terminal/json/quiet), `stream` (stdout/file), `progress` (stderr); `emit_result(data: dict)` and `emit_progress(msg: str)` methods; factory `output_from_args(args: Namespace) -> OutputContext`
- [x] **PREP-3-2** Add `--json` and `--quiet` global flags to `cli.py` top-level `ArgumentParser` as mutually exclusive group; set `args.output_mode` (default `"terminal"`).  Verified no conflict with subparser-level `--json` (uuid-translate) or `--quiet` (survey) — argparse resolves correctly via separate `dest` names.
- [x] **PREP-3-3** Make `print_banner()` accept optional `output_mode` parameter (default `"terminal"`); suppress when `"json"` or `"quiet"`.  Backward compatible — callers without the parameter get existing behavior.
- [x] **PREP-3-4** Adapt `survey.py` as proof-of-concept: added `run(args: Namespace, output: OutputContext) -> int` entry point; replaced all `print(..., file=sys.stderr)` with `output.emit_progress()`; routed JSON through `output.emit_result()` in json/quiet modes; `main(argv)` preserved as thin backward-compatible wrapper.  CLI dispatch updated from `sys.argv[2:]` to direct `run(args, output_from_args(args))` call — first mode to use the new pattern.
- [x] **PREP-3-5** Validated: 90 survey tests pass, 350 tests across 21 test files pass (0 failures), no import errors from `bleep.core.output`, `--json`/`--quiet` flags parse correctly with correct namespace isolation from subparser flags, banner suppression verified in all modes.

---

### Phase 3 — Output Contract & CLI Dispatch Refactoring — COMPLETE (2026-05-22)

**Scope**: Establish the `OutputContext` protocol following the Survey Mode pattern, and unify CLI dispatch to eliminate `sys.argv` mutation/forwarding.

**Status**: All items complete.  `OutputContext` protocol established across all 11 mode `run()` entry points; `sys.argv` mutation eliminated; stdout contamination in `--json`/`--quiet` modes fixed via thread-local output routing in `print_and_log()`; structured JSON events emitted for all long-running modes; bare `print()` converted to `print_and_log()` across all mode files including `user.py` (139 calls, P3-E1, 2026-05-22) and `db.py` (P3-E2, 2026-05-21); subprocess flag propagation implemented; P3-D1 file-based stream routing complete (2026-05-21); P3-E3 aoi dispatch resolved via P6-A12 (2026-05-22); P3-E4 OutputMode consolidation complete (2026-05-21).

#### P3-A: OutputContext Protocol — COMPLETED (2026-05-19, via PREP-3)

- [x] **P3-A1** Create `bleep/core/output.py` with `OutputContext` dataclass: `mode` (terminal/json/quiet), `stream` (stdout/file), `progress` (stderr); `emit_result(data: Any)` and `emit_progress(msg: str)` methods — completed in PREP-3-1
- [x] **P3-A2** Adapt `survey.py` to use `OutputContext` — `run(args, output)` entry point; progress via `output.emit_progress()`, data via `output.emit_result()` — completed in PREP-3-4
- [x] **P3-A3** Add `--json` and `--quiet` global flags to CLI argument parser — mutually exclusive group, `dest="output_mode"`, no conflict with subparser-level flags — completed in PREP-3-2
- [x] **P3-A4** Make `print_banner()` conditional on `output_mode` parameter — suppressed for `"json"` and `"quiet"` — completed in PREP-3-3

#### P3-B: CLI Dispatch Unification

- [x] **P3-B1** Add `run(args: argparse.Namespace, output: OutputContext) -> int` entry point to each mode — accepts parsed args directly instead of `sys.argv` slices.  **Survey completed** in PREP-3-4; remaining modes done: `agent`, `pair`, `classic-connect`, `exploration`, `aoi`, `signal`, `db`, `user`
- [x] **P3-B2** Eliminate `sys.argv` mutation in `explore` mode: pass args directly to `exploration.run(args, output)` — namespace normalization handles `mac`/`device` and `connection_mode`/`mode` mapping
- [x] **P3-B3** Eliminate `sys.argv[2:]` forwarding in `agent`, `pair`, `classic-connect` modes: route through `run(args, output)` entry points.  Fixed agent `--mode` namespace collision with `dest="agent_mode"`.
- [x] **P3-B4** Eliminate sub-argv construction in `db`, `user`, `signal`, `aoi` modes: route through `run(args, output)` entry points.  Note: `aoi` retains `main(opts)` dispatch in cli.py due to complex subcommand reassembly; `run()` is available for direct callers.
- [x] **P3-B5** Apply `OutputContext` to Pattern B modes — first wave complete: `exploration` (emits GATT result dict), `db` (list/show/export/timeline emit structured JSON), `signal` (emits per-notification JSON events with timestamp/uuid/value).  Remaining modes (`aoi`, `scan` variants, `classic-enum`, `media-enum`, `gatt-enum`) deferred to subsequent iteration.
- [x] **P3-B6** Propagate `--json`/`--quiet` to subprocess invocations: `survey --then-aoi` subprocess launch now forwards `output.mode` as `--json`/`--quiet` global flag to the spawned `bleep aoi scan` process — completed 2026-05-20
- [x] **P3-B7** Thread-local output-mode routing for `print_and_log()`: added `set_output_mode()`/`get_output_mode()` to `bleep/core/log.py` using `threading.local()`.  In `json`/`quiet` mode the `print()` half routes to `sys.stderr`; `logging__log_event()` **always** writes to the log file regardless of mode — no log data is ever lost or deferred.  All 11 mode `run()` entry points call `set_output_mode(output.mode)` at the top. — completed 2026-05-20
- [x] **P3-B8** Convert bare `print()` calls to `print_and_log()` in `classic_connect.py`, `pair.py`, `monitor.py`, `advertise.py`, plus `run()`-level bare prints in `user.py` and `db.py` — ensures all user-facing messages in mode entry points are both logged to file and routed correctly in json/quiet mode.  Note: `user.py` interactive TUI functions (~120 bare prints) and `db.py` terminal-only helper functions (~27 bare prints) deferred to Phase 4 mode unification — these only execute in terminal mode and are not contamination sources. — completed 2026-05-20

#### P3-C: Structured Output for Long-Running Modes

- [x] **P3-C1** `agent` mode: emit structured status events (agent registered, pairing started/succeeded/failed) via `output.emit_result()` alongside existing terminal output — completed 2026-05-20
- [x] **P3-C2** `signal` mode: emit notification values as structured JSON lines via `output.emit_result()` alongside existing `print_and_log` — format: `{"ts": ..., "uuid": ..., "value_hex": ...}` — completed in P3-B5 wave
- [x] **P3-C3** `monitor` mode: emit `DeviceFound`/`DeviceLost` events as structured JSON lines via `output.emit_result()` — format: `{"event": "device_found"/"device_lost", "mac": ..., "elapsed_s": ...}`.  Added `run()` entry point with `OutputContext` and `set_output_mode()` wiring; cli.py updated to call `run()`. — completed 2026-05-20
- [x] **P3-C4** `advertise` mode: emit advertisement status as structured JSON via `output.emit_result()` — events: `adv_started`, `adv_stopped`, `adv_released`, `advertise_caps`.  Added `run()` entry point with `OutputContext` and `set_output_mode()` wiring; cli.py updated to call `run()`. — completed 2026-05-20

#### P3-D: Future Enhancements (identified during PREP-3 review)

- [x] **P3-D1** `output_from_args()` file-based stream routing: `output_from_args()` now auto-opens `-o`/`--output` file as the `OutputContext.stream` when in json/quiet mode.  Added `OutputContext.close()` for file handle cleanup.  Terminal mode ignores file arg.  Parent dirs created automatically. — completed 2026-05-21
- [x] **P3-D2** Remove dead `total_rounds` variable and unused `ceil` import in `survey.py`: computed but never referenced.  Pre-existing tech debt exposed during PREP-3 review. — completed 2026-05-20

#### P3-E: Deferred Items (to be addressed in later phases)

- [x] **P3-E1** `user.py` interactive TUI bare `print()` conversion (139 calls): all bare `print()` calls in `UserMenu.display()`, `translate_uuid_interactive()`, `display_device_info()`, `browse_services()`, `browse_characteristics()`, `characteristic_actions()`, `read_characteristic()`, `write_characteristic()`, `notification_callback()`, `toggle_notifications()`, `multi_read_characteristic_ui()`, `brute_write_characteristic_ui()`, `configure_signal_capture()`, `export_device_data()`, `disconnect_device()`, `scan_and_connect_menu()`, `manual_connect()`, and `run_user_mode()` converted to `print_and_log(msg, LOG__USER)`.  Output now logged to file and respects thread-local routing in json/quiet mode. — completed 2026-05-22
- [x] **P3-E2** `db.py` helper function bare `print()` conversion: all bare `print()` calls in `list_devices()`, `timeline()`, `show_device()`, `export_device()` converted to `print_and_log()`.  Output now logged to file and respects thread-local routing. — completed 2026-05-21
- [x] **P3-E3** `aoi.py` cli.py dispatch via `main(opts)` instead of `run(args, output)`: due to complex subcommand reassembly in cli.py (scan/analyze/list/report/export/db).  `run()` exists and works for direct callers.  ~~Best addressed during Phase 6 (CLI decomposition) when the aoi subparser can be restructured.~~ — resolved by P6-A12 (2026-05-22)
- [x] **P3-E4** Duplicate `OutputMode` type alias consolidated: `log.py` now imports `OutputMode` from `output.py` as `OutputModeLiteral` — single source of truth.  Removed unused `Literal` from `log.py` imports. — completed 2026-05-21

---

### Phase 4 — Enumeration Architecture Unification — COMPLETE (2026-05-20–2026-05-21)

**Scope**: Reconcile the three independent BLE enumeration paths into a unified architecture that preserves all variant-specific functionality.

**Current state** (audit 2026-05-18, updated 2026-05-20 post-P4-2):
- **Path A** (`scan.py` variants: `passive_enum`, `naggy_enum`, `pokey_enum`, `brute_enum`): post-connect analysis strategies — multi-read for value change detection, write probes, payload fuzzing.  **No longer called directly from CLI** — now invoked through the controller (Path B).
- **Path B** (`EnumerationController`): retry/annotation wrapper with up to 3 full connect cycles and typed `EnumerationResult`/`ConnectionAnnotation`.  Used by `bleep enum-scan` (all variants, P4-2), `aoi` mode, and MCP `ble_enumerate` tool.  Delegates to Path A variant functions for non-passive modes (P4-1).  `--controlled` flag deprecated (accepted but no-op).
- **Path C** (`scan_modes.py`): thin wrappers around `connect.py` with mode-specific parameters (scan attempts, connect retries, timeouts, backoff).  Post-connect behaviour (pokey deep reads, bruteforce handle sweep) handled locally.  Classic device support via `_classic_connect` helper.  Used by `bleep explore` and MCP `ble_scan_and_connect`.

**Problem**: "naggy", "pokey", "bruteforce" mean fundamentally different things in each path. `EnumerationController` claimed to support modes but only toggled a boolean. AoI always uses the controller, so it never gets multi-read, write probes, or payload fuzzing even when those strategies would be valuable.

**Plan**: Make `EnumerationController` the outer wrapper that delegates to variant-specific logic, preserving all functionality.

- [x] **P4-1** Fix `EnumerationController.enumerate(mode)` to dispatch to `scan.py` variant logic: `mode="naggy"` invokes `naggy_enum` multi-read, `mode="pokey"` invokes `pokey_enum` write probes, `mode="brute"`/`"bruteforce"` invokes `brute_enum` payload fuzzing.  Variant kwargs (`rounds`, `verify`, `write_char`, etc.) forwarded via `**variant_kwargs`.  `passive` mode unchanged (direct `connect_and_enumerate`).  Variant-specific results stored under `result.data["_variant_extra"]`.  `set` types (e.g. `changed_chars`) converted to sorted lists for JSON serialization. — completed 2026-05-20
- [x] **P4-2** Make `EnumerationController` the default for all `enum-scan` variants: `--controlled` flag deprecated (accepted but no-op); controller is now the standard path wrapping each variant with retry/annotation.  `_variant_extra` data separated from mapping before DB persistence and tree output.  Annotation summary printed to stderr.  Tree output, DB persistence, and change-detection highlighting all preserved. — completed 2026-05-20
- [x] **P4-3** Reconcile `scan_modes.py` connection strategies with `connect.py`: `connect_and_enumerate__bluetooth__low_energy()` extended with configurable `scan_attempts`, `scan_timeout`, `connect_retries`, `connect_wait_timeout`, `transport` filter, and `max_attempts` outer retry loop with exponential backoff (`backoff_base`/`backoff_max`/`backoff_jitter`).  `timeout_connect` kept as deprecated alias for backward compatibility.  `scan_modes.py` refactored to thin wrappers — duplicated `_wait_for_services()`, `_get_adapter()`, `_scan_until_visible()`, and inline scan/connect/service-resolve logic removed.  Three private helpers extracted: `_classic_connect()` (BR/EDR device path), `_classify_device()` (device-type classification), `_pokey_deep_read()` (deep char/descriptor reads).  All public function signatures, return types, mode constants, and `__all__` unchanged.  Bruteforce handle sweep preserved inline.  Classic device support preserved via `_classic_connect`.  InProgress/Failed D-Bus forgiveness moved to `connect.py` outer retry loop, guarded by `max_attempts > 1` to prevent infinite retry when using the legacy single-attempt default. — completed 2026-05-21
- [x] **P4-4** `EnumerationResult` persistence: `EnumerationResult` dataclass extended with `serialized_annotations` property and `persist_security_maps(mac, source)` convenience method.  `cli.py` `enum-scan` now calls `result.persist_security_maps(address, source="enum-scan:<variant>")` after every successful enumeration.  `cli.py` `gatt-enum` now persists `landmine_map`/`permission_map` via `store_security_maps(source="gatt-enum")`.  AoI mode simplified to use `le_result.serialized_annotations` and `le_result.persist_security_maps(mac, source="aoi")` instead of duplicating serialization logic.  Uses existing `security_maps` table (`enumeration_annotations` JSON column).  No schema change required.  `store_security_maps()` type hint corrected: `enumeration_annotations` parameter `Optional[Dict]` → `Optional[List[Dict]]` to match actual usage. — completed 2026-05-21
- [x] **P4-5** Fix `EnumerationController` docstring: removed false claims about `ReconnectionMonitor` and `ConnectionResetManager` integration.  Module docstring, class docstring, and `enumerate()` docstring rewritten.  Dead `_should_continue()` method removed.  Unused `BLEEPError` import removed.  `ConnectionAnnotation` added to `__all__` exports. — completed 2026-05-20
- [x] **P4-6** AoI deep enumeration now uses `pokey` mode: `_scan_target(deep=True)` dispatches `controller.enumerate(mode="pokey", rounds=2)` instead of `mode="passive"`, getting write-probe data that reveals which characteristics are writable.  `_perform_deep_reenumeration()` (post-pair) also uses pokey to capture characteristics that became writable after pairing.  `_variant_extra` (rounds data, device_props) extracted from `result.data` and stored in `device_data["variant_extra"]` / `delta["le_delta"]["variant_extra"]` for analyser consumption.  Non-deep (`deep=False`) path unchanged — still dispatches `mode="passive"` with no extra kwargs.  Unused `_connect_enum` import removed from `aoi.py`. — completed 2026-05-21
- [x] **P4-7** Update documentation to reflect unified architecture — completed 2026-05-21

  **Summary of documentation updates:**
  - `gatt_enumeration.md`: false `ReconnectionMonitor` claim removed; 8 stale file paths corrected; `--controlled` documented as deprecated; comparison table updated.
  - `ble_scan_modes.md`: rewritten to describe the wrapper-based architecture; old-to-new translation reference added.
  - `explore_mode.md`: connection modes section rewritten to reference parameterised `connect.py`; architectural note added.

  **Old → New Architecture Translation Reference**

  The P4-3 refactoring shifted responsibility for the core scan → connect → service-resolve pipeline from `scan_modes.py` (which previously implemented it independently per mode) into `connect.py` (which now accepts parameterised kwargs). This is how the old architecture's methodology maps to the new wrapper-based implementation:

  | Old Architecture (pre-P4-3) | New Wrapper Architecture (post-P4-3) |
  |---|---|
  | Each mode function in `scan_modes.py` contained its own complete scan → connect → service-resolve pipeline with hardcoded timeouts, retry counts, and backoff logic. | Each mode function is a thin wrapper that calls `connect_and_enumerate__bluetooth__low_energy()` with mode-specific kwargs. The pipeline runs once, inside `connect.py`. |
  | `_get_adapter()` helper (duplicated in `scan_modes.py`) obtained adapter instance and validated readiness. | Removed. `connect.py` handles adapter creation and readiness check internally. |
  | `_scan_until_visible(adapter, target, timeout, transport)` helper (duplicated in `scan_modes.py`) ran the discovery loop with a transport filter. | Removed. `connect.py`'s parameterised scan loop (`scan_attempts`, `scan_timeout`) and transport filter (`SetDiscoveryFilter`) replace this entirely. |
  | `_wait_for_services(device, timeout)` helper (duplicated in `scan_modes.py`) polled `ServicesResolved`. | Removed from `scan_modes.py`. `connect.py`'s internal `_wait_for_services(device, timeout_services)` provides the same functionality. |
  | Naggy mode's inline `while attempt < max_retries` loop with `time.sleep(backoff)`, `backoff = min(backoff * 2, 30)`, `jitter`, and InProgress/Failed forgiveness (`attempt -= 1`). | Mapped to `connect.py`'s `max_attempts=max_retries`, `backoff_base=0.5`, `backoff_max=30.0`, `backoff_jitter=0.5`. InProgress/Failed forgiveness preserved via `continue` in outer D-Bus handler (guarded by `max_attempts > 1`). |
  | Passive mode's inline `timeout // 2` / `timeout // 4` / `timeout // 4` budget distribution across scan, connect, and service-resolve phases. | Preserved in `passive_scan_and_connect()` which calculates `scan_t`, `connect_t`, `services_t` from `timeout` and passes them as `scan_timeout`, `connect_wait_timeout`, `timeout_services` to `_connect_enum()`. |
  | Pokey mode's extended `scan_timeout=10`, `connect(retry=5, wait_timeout=10)`, `timeout_services=30`, followed by inline deep characteristic/descriptor reads. | `_connect_enum(scan_timeout=10, connect_retries=5, connect_wait_timeout=10.0, timeout_services=30, deep_enumeration=False)` handles the connect phase. `_pokey_deep_read(device)` (extracted helper) handles the post-connect deep reads. |
  | Classic (BR/EDR) device handling was inline in each mode function (adapter check, transport filter, `ClassicDevice` instantiation, connect). | Extracted into `_classic_connect(target, transport)` private helper. Each mode function checks `transport.lower() == "bredr"` and delegates. |
  | Device type classification was inline per mode; passive mode additionally logged `device_type_flags` while other modes did not. | Extracted into `_classify_device(device, mode, log_flags=False)`. Only passive passes `log_flags=True`, preserving the original asymmetry. |
  | `_log_disconnect_reason()` was called inline in `scan_modes.py` on service resolution failure. | Now called internally by `connect.py` before raising `ServicesNotResolvedError`. `scan_modes.py` no longer imports or calls it. |
  | `timeout_connect` was a direct parameter to `device.connect(wait_timeout=...)` with hardcoded value `10`. | Preserved as a deprecated alias. When `connect_wait_timeout` is `None` (the default), `timeout_connect` value is used. New callers should use `connect_wait_timeout` directly. Existing callers (bleep-mcp, scripts) continue unchanged. |
  | `device.connect(retry=5)` was hardcoded in `connect.py`, `device.connect(retry=2)` in naggy, etc. | `connect_retries` parameter (default 5) is passed to `device.connect(retry=connect_retries)`. Each mode wrapper passes its own value. |

  **Parameter mapping per mode:**

  | Parameter | Passive | Naggy | Pokey | Bruteforce |
  |---|---|---|---|---|
  | `scan_attempts` | 3 | 5 | 3 | (via pokey) |
  | `scan_timeout` | `timeout // 2` (min 5) | 8 | 10 | (via pokey) |
  | `connect_retries` | 1 | 2 | 5 | (via pokey) |
  | `connect_wait_timeout` | `timeout // 4` (min 3) | 5.0 | 10.0 | (via pokey) |
  | `timeout_services` | `timeout // 4` (min 5) | 20 | 30 | (via pokey) |
  | `max_attempts` | 1 (default) | `max_retries` (10) | 1 (default) | (via pokey) |
  | `backoff_*` | n/a | 0.5 / 30.0 / 0.5 | n/a | n/a |
  | Post-connect | `_classify_device(log_flags=True)` | `_classify_device` | `_pokey_deep_read` + `_classify_device` | pokey + handle sweep + `_classify_device` |

#### P4-A: Additional fixes applied during P4-1/P4-5 implementation (2026-05-20)

- [x] **P4-A1** `cli.py` `enum-scan --controlled` now forwards variant-specific kwargs (`rounds`, `verify`, `write_char`, `value_range`, `patterns`, `payload_file`, `force`) to the controller — previously the `--controlled` path ignored variant parameters
- [x] **P4-A2** `cli.py` `enum-scan --controlled` JSON output uses `default=str` to handle non-serializable types (bytes, sets) in `result.data`
- [x] **P4-A3** MCP `ble_enumerate` tool return value fixed: previously accessed non-existent `result.services` and `result.errors` fields (via `hasattr` guards, silently returning empty dicts); now uses correct `EnumerationResult` fields (`data`, `landmine_map`, `permission_map`, `annotations`, `error_summary`)
- [x] **P4-A4** `scan.py` `passive_enum` and `naggy_enum` now include `device` object in return dict — enables callers (including controller) to access device name/services from all variants

---

### Pre-Phase 5 — Deferred Item Resolution & Test Baseline (2026-05-21) — COMPLETE

Resolves deferred items from Phases 3–4 and fixes broken test infrastructure to establish a clean baseline before Phase 5 work begins.

- [x] **Test imports**: Fixed 4 test files with stale import paths from `ble_ops/` reorganization (P0-8): `test_brute_helpers.py`, `test_brute_multi.py`, `test_scan_variants.py`, `test_uuid_translation.py`.  Also fixed `test_brute_helpers.py` stub method name (`read_characteristic` → `read_characteristic_with_fallback`).  8 tests restored to passing.
- [x] **P3-E4**: `OutputMode` type alias consolidation (see P3-E section above)
- [x] **P3-E2**: `db.py` bare `print()` → `print_and_log()` conversion (see P3-E section above)
- [x] **P3-D1**: Centralized file-based stream routing in `output_from_args()` (see P3-D section above)
- [x] **BZ-12f**: `docs/adv_monitor.md` documentation (see Sprint 5A below)

**Test baseline post-cleanup:** 454 passed → 538 passed (Sprint 5A) → 578 passed (Sprint 5B: +40 GATT server tests) → 608 passed (Sprint 5C: +30 enrichment tests) → 645 passed (Sprint 5D: +37 niche interface tests) → **704 passed** (Sprint 5E: +59 GATT profile decoder tests), 28 skipped, 2 failed (hardware-dependent CTF), 0 errors.

---

### Phase 5 — BlueZ Capability Completion

**Scope**: Implement all remaining BlueZ D-Bus interface gaps. ALL capabilities in scope including deprecated profiles (handled via GATT-level recognition where BlueZ removed D-Bus plugins).

#### Sprint 5A — P0: Wire Completed Code to CLI (Low Effort)

- [x] **BZ-1e** Wire `--stream` flag on debug `read`/`write` commands to use `acquire_write()`/`acquire_notify()` fd-based streaming — code complete in `dbuslayer/characteristic.py`
- [x] **BZ-1f** Tests: mock-based unit tests for acquire/fallback logic — 12 tests in `test_characteristic_descriptor.py`; production fix: `_dbus_exc()` dynamic exception resolver (completed 2026-05-21)
- [x] **BZ-7d** Tests: mock-based unit tests for `LEAdvertisement`/`LEAdvertisingManager` — 21 tests in `test_le_advertising.py` (completed 2026-05-21)
- [x] **BZ-8f** Surface disconnect reason in debug mode `info` command and scan/enum output — D-Bus code in `dbuslayer/signals.py`; debug wiring in `modes/debug_connect.py`; scan output wiring in `connect.py` (2026-05-19; `scan_modes.py` disconnect-reason calls removed in P4-3 as `connect.py` now handles them internally)
- [x] **BZ-12e** Add `--monitor` flag on `bleep scan` command — `modes/scan_monitor.py`: kernel-offloaded scanning via `AdvertisementMonitor`, MAC filtering, timeout support (completed 2026-05-21)
- [x] **BZ-12f** Documentation: `docs/adv_monitor.md` — prerequisites, CLI usage, pattern format, RSSI config, examples, architecture, troubleshooting — completed 2026-05-21
- [x] **BZ-12g** Tests: mock-based unit tests for `AdvMonitor`/`AdvMonitorManager` — 29 tests in `test_adv_monitor.py` (completed 2026-05-21)

#### Sprint 5B — P1: GATT Server (High Effort) — COMPLETE (2026-05-21)

- [x] **BZ-4a** Create `dbuslayer/gatt_server.py`: `GattApplication(dbus.service.Object)` implementing `org.freedesktop.DBus.ObjectManager`, `GattServiceSkeleton`, `GattCharacteristicSkeleton`, `GattDescriptorSkeleton` classes (completed 2026-05-21)
- [x] **BZ-4b** Add `register_application()`/`unregister_application()` methods calling `GattManager1` on adapter path via `GattServerManager` (completed 2026-05-21)
- [x] **BZ-4c** Wire BZ-3 `Confirm()` for indication-based characteristics on `GattCharacteristicSkeleton` (completed 2026-05-21)
- [x] **BZ-4d** Create `modes/gatt_server.py` CLI mode: `bleep gatt-server start` with `--uuid`, `--read-value`, `--duration`, `--adapter` (completed 2026-05-21)
- [x] **BZ-4e** Example configuration: static-read, log-write, tick-notify characteristics per service (completed 2026-05-21)
- [x] **BZ-4f** Tests: 40 mock-based unit tests in `test_gatt_server.py` — descriptors, characteristics, services, application, manager registration, D-Bus error types (completed 2026-05-21)
- [x] **BZ-5a** Implement `GattProfileSkeleton` in `dbuslayer/gatt_server.py` — `UUIDs` property, `Release()` callback, integrated into `GattApplication.GetManagedObjects()` (completed 2026-05-21)

#### Sprint 5C — P2: Enrichment Interfaces (Medium Effort) — COMPLETE (2026-05-21)

- [x] **BZ-5a** `GattProfileSkeleton` for GATT client auto-connect profiles — `UUIDs`, `Release()`, `GetAll()`; `GattApplication.add_profile()` and `GetManagedObjects()` includes profiles; `remove_all()` cleans up profiles (completed 2026-05-21)
- [x] **BZ-15a** Create `dbuslayer/device_set.py` — `DeviceSet` class wrapping `DeviceSet1` interface: `connect()`, `disconnect()`, `get_adapter()`, `get_auto_connect()`, `set_auto_connect()`, `get_devices()`, `get_size()`, `get_info()`; `enumerate_device_sets()` discovers sets via ObjectManager (completed 2026-05-21)
- [x] **BZ-15b** Surface device set membership in scan/enum output — `get_device_sets()` already in `device_le.get_device_info()` (pre-existing); `DeviceSet.get_info()` provides structured set data (completed 2026-05-21)
- [x] **BZ-15c** Add `bleep device-sets` CLI command — `list`, `connect`, `disconnect`, `info` subcommands in `modes/device_sets.py`, wired in `cli.py` (completed 2026-05-21)
- [x] **BZ-24b** `Capabilities` and `OutOfBandInfo` already configurable via constructor args in `mesh/provision_agent.py` — marked as pre-existing complete (completed pre-Sprint 5C)
- [x] **BZ-24a** Fill `mesh/provision_agent.py` OOB hooks with `AgentIOHandler` pattern (completed Sprint 5D — `InteractiveProvisionAgent` + `MeshIOHandler`)
- [x] **BZ-24c** Wire mesh provisioning to CLI commands (completed Sprint 5D — `bleep mesh {join,provision,reprovision}`)
- [x] **BZ-25a** Add `MeshManagement.reprovision()` client wrapper calling `Management1.Reprovision(uint16, dict)` in `mesh/management.py`; D-Bus skeleton methods `RequestReprovData`, `ReprovComplete`, `ReprovFailed` already present in `mesh/provisioner.py` (completed 2026-05-21)
- [x] **BZ-13a** Add `AdminPolicySet1.SetServiceAllowList()` support in `dbuslayer/adapter.py` — `set_service_allow_list()` and `get_service_allow_list()` methods (completed 2026-05-21)
- [x] **BZ-14a** Read `AdminPolicyStatus1.IsAffectedByPolicy` in device property enumeration — added to both `device_le.py` and `device_classic.py` `get_device_info()` as `is_affected_by_policy` field (completed 2026-05-21)
- [x] **BZ-14b** Surface policy-affected status in scan/enum output — `is_affected_by_policy` included in device info dicts (completed 2026-05-21)
- [x] **Fix** Corrected stale `MESH_AGENT_INTERFACE` constant from `ProvisioningAgent1` to `ProvisionAgent1` in `bt_ref/constants.py`
- [x] **Fix** Added `ADMIN_POLICY_SET_INTERFACE`, `ADMIN_POLICY_STATUS_INTERFACE`, `DEVICE_SET_INTERFACE` constants to `bt_ref/constants.py`
- [x] **Tests** 30 mock-based unit tests in `tests/test_sprint5c.py` — `GattProfileSkeleton` (7), `GattApplication` profiles (4), `DeviceSet` (8), `enumerate_device_sets` (3), constants validation (5), `MeshManagement.reprovision` (3) (completed 2026-05-21)

#### Sprint 5D — P3: Niche Interfaces (Low Effort) — COMPLETE (2026-05-21)

- [x] **BZ-9a** Create `dbuslayer/battery_provider.py` — `BatteryProviderObject` (Percentage, Source, Device properties; update_percentage with PropertiesChanged), `BatteryProviderApp` (ObjectManager root, add_battery, GetManagedObjects, remove_all), `BatteryProviderManager` (register/unregister via `BatteryProviderManager1`); registered as lazy-loaded module in `dbuslayer/__init__.py` (completed 2026-05-21)
- [x] **BZ-10a** `BatteryProviderManager.register()`/`unregister()` wrappers call `BatteryProviderManager1.RegisterBatteryProvider()`/`UnregisterBatteryProvider()` — ready for CLI integration when needed (completed 2026-05-21)
- [x] **BZ-16a** Read `Bearer.LE1` properties (`Paired`, `Bonded`, `Connected`) in `device_le.get_device_info()` as `bearer_le` dict; read `Bearer.BREDR1` properties in `device_classic.get_device_info()` as `bearer_bredr` dict; graceful fallback to `None` when BlueZ lacks `--experimental` (completed 2026-05-21)
- [x] **BZ-16b** Add `bearer_le_connect()`/`bearer_le_disconnect()` methods to `device_le.py`; add `bearer_bredr_connect()`/`bearer_bredr_disconnect()` methods to `device_classic.py` — thin wrappers calling `Bearer.LE1.Connect()`/`Disconnect()` and `Bearer.BREDR1.Connect()`/`Disconnect()` respectively (completed 2026-05-21)
- [x] **BZ-24a** Create `mesh/interactive_provision_agent.py` — `MeshIOHandler` abstract base, `CliMeshIOHandler` (interactive terminal), `AutoAcceptMeshIOHandler` (headless/zero-OOB), `InteractiveProvisionAgent` (concrete `MeshProvisionAgent` subclass delegating to I/O handler), `create_mesh_io_handler()` factory (completed 2026-05-21)
- [x] **BZ-24c** Wire mesh provisioning to CLI — `bleep mesh {join,provision,reprovision}` subcommands in `modes/mesh_provision.py`, parser in `cli.py`, dispatch logic for `args.mode == "mesh"` (completed 2026-05-21)
- [x] **BZ-17a** Create `dbuslayer/health.py` — HDP documentation stub; `HDP_SUPPORTED = False`, legacy interface names for reference, removal note explaining BlueZ 5.50+ removal (completed 2026-05-21)
- [x] **BZ-19a** Create `dbuslayer/media_assistant.py` — `MediaAssistant` wrapper for `MediaAssistant1` (push, get_state, get_metadata, get_qos, get_info), `enumerate_media_assistants()` discovery; registered as lazy-loaded module in `dbuslayer/__init__.py` (completed 2026-05-21)
- [x] **Constants** Added `BATTERY_INTERFACE`, `BATTERY_PROVIDER_INTERFACE`, `BATTERY_PROVIDER_MANAGER_INTERFACE`, `BATTERY_PROVIDER_BASE_PATH`, `BEARER_LE_INTERFACE`, `BEARER_BREDR_INTERFACE`, `MEDIA_ASSISTANT_INTERFACE` to `bt_ref/constants.py`
- [x] **Tests** 37 mock-based unit tests in `tests/test_sprint5d.py` — `BatteryProviderObject` (7), `BatteryProviderApp` (4), `BatteryProviderManager` (2), constants validation (6), bearer constants (2), `MediaAssistant` (5), `InteractiveProvisionAgent` (6), `MeshIOHandler` factory (3), HDP stub (2) (completed 2026-05-21)

#### Sprint 5E — P4: Deprecated Profile GATT-Level Recognition — COMPLETE (2026-05-22)

**Strategy**: BlueZ removed D-Bus plugin interfaces (`Thermometer1`, `HeartRate1`, `CyclingSpeed1`, `ProximityMonitor1`) in BlueZ 5.48+. The underlying GATT services still exist on devices and are already readable via BLEEP's standard GATT enumeration. This sprint adds profile-aware **recognition and structured interpretation** at the GATT level, providing better coverage than the old BlueZ plugins because it works on any BlueZ version.

- [x] **BZ-20-23a** Add GATT profile UUID recognition to `bt_ref/constants.py` — 6 service UUIDs, 11 characteristic UUIDs, `DEPRECATED_GATT_PROFILE_SVCS` frozenset, `DEPRECATED_GATT_PROFILE_NAMES` dict, `DEPRECATED_GATT_CHR_TO_SVC` mapping (completed 2026-05-22)
- [x] **BZ-20-23b** Add value interpretation in `ble_ops/common/gatt_profile_decode.py` — 11 per-characteristic decoders (IEEE 11073 FLOAT temperature, HR measurement with flags/RR intervals, CSC measurement with wheel/crank revolutions, Alert Level enum, Tx Power dBm, sensor location enums); `decode_characteristic_value()` facade (completed 2026-05-22)
- [x] **BZ-20-23c** Surface recognized profiles in `format_gatt_tree()` (Decoded: line), `debug_gatt.py` cmd_read (Value (Profile): line), `exploration.py` verbose mode (Decoded: line + decoded field), `aoi_analyser.py` (decoded_value field in analysis) (completed 2026-05-22)
- [x] **BZ-20-23d** Documentation: extended `docs/gatt_enumeration.md` with "Recognized GATT Profiles" section; extended `docs/bluez_interface_properties.md` with "Intentionally Unsupported: Deprecated BlueZ Profile Plugin APIs" section (completed 2026-05-22)
- [x] **Tests** 59 tests in `tests/test_sprint5e.py` — constants (11), IEEE 11073 FLOAT (6), temperature measurement (5), temperature type (3), measurement interval (3), HR measurement (6), body sensor location (3), alert level (3), Tx power (3), CSC measurement (4), CSC feature (3), sensor location (3), facade (4), format_gatt_tree integration (2) (completed 2026-05-22)

---

### Phase 6 — CLI Decomposition (2026-05-22) — COMPLETE

**Scope**: Decompose `cli.py` (2,964 lines) into a modular `bleep/cli/` package. No behavioral changes — purely structural relocation of existing code.

**Target**: Every file under 300 lines (per NFR-1 from `bleep_refactor_prd.txt`).

**Pre-implementation audit** (2026-05-22): Detailed analysis of `cli.py` revealed the original plan underestimated scope. Corrected findings:

| Section | Lines | Notes |
|---------|------:|-------|
| Parser definitions (42 subparsers) | 775 | Lines 17–775 |
| Helper functions (`_rebuild_debug_argv`, MAC norm) | 63 | Lines 776–838 |
| Dispatch — `run(args, output)` pattern (11 modes) | 55 | Clean 3-5 line delegation |
| Dispatch — thin delegation (17 modes) | 260 | Small blocks, mostly relocatable |
| Dispatch — **inline implementation** (19 modes) | 1,811 | Must be extracted to modules first |
| **Total** | **2,964** | |

The 19 modes with inline implementation (1,811 lines) have no external `run()` entry point.  They must be extracted to mode modules before the CLI file can be decomposed.  This is a prerequisite the original plan did not capture.

**Inline implementation blocks requiring extraction** (sorted by size):

| Mode | Inline Lines | Target Module |
|------|-------------|---------------|
| `media-enum` | 249 | `modes/media.py` (extend existing) |
| `classic-enum` | 244 | `modes/classic_enum.py` (new) |
| `classic-map` | 197 | `modes/classic_profiles.py` (new — MAP/OPP/FTP/BIP/Sync/SPP/PBAP) |
| `connect` | 122 | `modes/connect.py` (new) |
| `classic-scan` | 121 | `modes/classic_scan.py` (new) |
| `classic-ftp` | 94 | `modes/classic_profiles.py` |
| `classic-bip` | 89 | `modes/classic_profiles.py` |
| `enum-scan` | 84 | `modes/enum_scan.py` (new) |
| `classic-opp` | 81 | `modes/classic_profiles.py` |
| `gatt-enum` | 69 | `modes/gatt_enum.py` (new) |
| `classic-spp` | 68 | `modes/classic_profiles.py` |
| `classic-pan` | 67 | `modes/classic_profiles.py` |
| `aoi` | 63 | `modes/aoi.py` (P3-E3: convert `main(opts)` → `run(args, output)`) |
| `classic-rfcomm` | 61 | `modes/classic_rfcomm.py` (new) |
| `classic-sync` | 47 | `modes/classic_profiles.py` |
| `audio-profiles` | 42 | `modes/audio.py` (extend existing) |
| `ctf` | 40 | `modes/blectf.py` (extend existing) |
| `audio-config` | 39 | `modes/audio.py` |
| `classic-pbap` | 34 | `modes/classic_profiles.py` |

**Modes already using `run(args, output)` pattern** (11 modes, 55 lines — no extraction needed): `survey`, `db`, `agent`, `pair`, `classic-connect`, `user`, `explore`, `signal`, `monitor`, `advertise`, `gatt-server`.

**Modes with thin delegation** (17 modes, 260 lines — relocatable as-is): `scan`, `debug`, `audio-intercept`, `media-ctrl`, `audio-record`, `connect-profile`, `audio-play`, `analyse`/`analyze`, `audio-recon`, `signal-config`, `classic-ping`, `amusica`, `adapter-config`, `device-sets`, `mesh`, `hid-info`, `interactive`.

**Parser group sizes** (actual line counts from audit):

| Parser File | Subparsers | Lines |
|-------------|-----------|------:|
| `parsers/classic.py` | classic-scan, classic-enum, classic-connect, classic-pbap, classic-opp, classic-map, classic-ftp, classic-pan, classic-spp, classic-sync, classic-bip, classic-ping, classic-rfcomm, hid-info | 234 |
| `parsers/utility.py` | uuid-translate, adapter-config, monitor, advertise, signal, signal-config, device-sets, mesh, ctf | 151 |
| `parsers/audio.py` | audio-profiles, audio-play, audio-record, audio-recon, amusica, audio-config, audio-intercept | 85 |
| `parsers/pairing.py` | pair, agent | 75 |
| `parsers/scan.py` | scan, enum-scan | 26 |
| `parsers/connect.py` | connect, connect-profile | 26 |
| `parsers/media.py` | media-enum, media-ctrl | 23 |
| `parsers/gatt.py` | gatt-enum, gatt-server | 22 |
| `parsers/debug.py` | debug | 21 |
| `parsers/survey.py` | survey | 20 |
| `parsers/aoi.py` | aoi, analyse/analyze | 19 |
| `parsers/explore.py` | explore | 11 |
| `parsers/db.py` | db | 11 |
| `parsers/other.py` | interactive, user | 9 |

**Constraints** (unchanged):
- `bleep=bleep.cli:main` entry point must remain (via `cli/__init__.py` re-export)
- `bleep/__main__.py` uses `from bleep.cli import main` — must continue to work
- All subparser names are public CLI API — no renames
- `--check-env`, `--diagnose-audio` are global flags handled before mode dispatch
- Adapter guard logic is shared (all modes except `db`)
- Banner print must be suppressible via `--quiet`/`--json` (from Phase 3)
- MAC normalization is shared (applied to multiple arg fields before dispatch)
- External docs reference `python -m bleep.cli` — ~~old `cli.py` kept as thin shim~~ resolved via `bleep/cli/__main__.py` (see implementation deviation below)

**Target structure**:
```
bleep/cli/
  __init__.py          (~5 lines)    Re-export main() for setup.py entry_point compat
  main.py              (~100 lines)  parse_args() wrapper, MAC normalization, adapter guard, dispatch()
  dispatch.py          (~120 lines)  Mode→run() routing table; all modes use thin delegation
  parsers/
    __init__.py         (~20 lines)   register_all(subparsers) → calls each module
    scan.py             (~30 lines)   scan + enum-scan
    explore.py          (~15 lines)   explore
    connect.py          (~30 lines)   connect + connect-profile
    gatt.py             (~25 lines)   gatt-enum + gatt-server
    classic.py          (~240 lines)  14 classic subparsers (under 300-line NFR-1 limit)
    media.py            (~25 lines)   media-enum + media-ctrl
    audio.py            (~90 lines)   7 audio subparsers
    pairing.py          (~80 lines)   pair + agent
    db.py               (~15 lines)   db
    survey.py            (~25 lines)  survey
    aoi.py              (~20 lines)   aoi + analyse/analyze
    debug.py            (~25 lines)   debug
    utility.py          (~155 lines)  9 utility subparsers
    other.py            (~10 lines)   interactive + user
```

**Line count projection**: ~1,000 lines across 19 files in `bleep/cli/`.  The remaining ~1,950 lines (inline implementations) are relocated to mode modules where they belong.  Total LOC across the codebase is unchanged — this is pure relocation.

**Actual result**: 1,326 lines across 19 files in `bleep/cli/` + 1,373 lines across 7 new mode modules.  Old `cli.py` deleted (not shimmed) — see implementation deviation note below.

#### Sub-phase 6A — Inline Implementation Extraction

**Goal**: Extract all 19 inline dispatch blocks from `cli.py` into `run()` functions in their respective mode modules.  Each extraction follows the Phase 3 proven pattern: `def run(args, output) -> int` in the mode module, 3-line delegation in `cli.py`.  No behavioral changes.

**Batch 1 — Classic OBEX Profiles** (8 modes → `modes/classic_profiles.py`):
- [x] **P6-A1** Create `modes/classic_profiles.py` with `run_pbap()`, `run_opp()`, `run_map()`, `run_ftp()`, `run_pan()`, `run_spp()`, `run_sync()`, `run_bip()` functions extracted from `cli.py` inline blocks (total: 687 lines relocated)
- [x] **P6-A2** Replace 8 inline blocks in `cli.py` with thin `from bleep.modes.classic_profiles import run_X; return run_X(args)` delegation

**Batch 2 — Classic Scan/Enum/RFCOMM** (3 modes → individual modules):
- [x] **P6-A3** Create `modes/classic_scan.py` with `run(args, output) -> int` (121 lines from `classic-scan` block)
- [x] **P6-A4** Create `modes/classic_enum.py` with `run(args, output) -> int` (244 lines from `classic-enum` block)
- [x] **P6-A5** Create `modes/classic_rfcomm.py` with `run(args, output) -> int` (61 lines from `classic-rfcomm` block)

**Batch 3 — BLE Modes** (4 modes → individual modules):
- [x] **P6-A6** Create `modes/connect.py` with `run(args, output) -> int` (122 lines from `connect` block)
- [x] **P6-A7** Create `modes/gatt_enum.py` with `run(args, output) -> int` (69 lines from `gatt-enum` block)
- [x] **P6-A8** Create `modes/enum_scan.py` with `run(args, output) -> int` (84 lines from `enum-scan` block)
- [x] **P6-A9** Extend `modes/media.py` with `run_media_enum(args, output) -> int` (249 lines from `media-enum` block)

**Batch 4 — Audio/CTF/AoI** (4 modes):
- [x] **P6-A10** Extend `modes/audio.py` with `run_audio_profiles(args) -> int` (42 lines) and `run_audio_config(args) -> int` (39 lines)
- [x] **P6-A11** Extend `modes/blectf.py` with `run(args, output) -> int` (40 lines from `ctf` block)
- [x] **P6-A12** Fix `modes/aoi.py` P3-E3: convert cli.py `main(opts)` dispatch to `run(args, output)` pattern, eliminating the 63-line subcommand reassembly block

**Verification gate**: PASSED — 704 passed, 28 skipped, 0 regressions.  `cli.py` shrunk from 2,964 to 1,243 lines before 6B decomposition.

#### Sub-phase 6B — Structural Decomposition

**Goal**: Split the now-slim `cli.py` into the `bleep/cli/` package.  All dispatch is thin delegation at this point.

- [x] **P6-B1** Create `bleep/cli/` package with `__init__.py` re-exporting `main` from `main.py`
- [x] **P6-B2** Move `main()`, `_rebuild_debug_argv()`, MAC normalization, adapter guard, banner, and global flag handling to `cli/main.py`
- [x] **P6-B3** Extract dispatch table to `cli/dispatch.py` — 48 explicit mode branches + interactive fallback (402 lines; exceeds NFR-1 300-line target but cannot be split further without fragmenting the routing table)
- [x] **P6-B4** Extract parser groups to `cli/parsers/*.py` one domain at a time (scan → explore → connect → gatt → classic → media → audio → pairing → db → survey → aoi → debug → utility → other)
- [x] **P6-B5** Old `bleep/cli.py` removed — `bleep/cli/` package takes precedence; `bleep/cli/__main__.py` added for `python -m bleep.cli` support
- [x] **P6-B6** Verify `setup.py` entry point `bleep=bleep.cli:main` works via re-export
- [x] **P6-B7** Verify `python -m bleep` works via `__main__.py` → `bleep.cli` → `bleep.cli.main`
- [x] **P6-B8** Verify `python -m bleep.cli` works via `bleep/cli/__main__.py`

**Verification gate**: PASSED — 704 passed, 28 skipped, 0 regressions.  All entry points verified: `bleep.cli:main`, `python -m bleep`, `python -m bleep.cli`, parser tests for multiple modes confirmed.  Old monolithic `cli.py` (2,964 lines) fully decomposed into `bleep/cli/` package (1,326 lines across 19 files) + 7 new mode modules (1,373 lines).  NFR-1 deviations: `dispatch.py` (402 lines — single routing table, unsplittable), `modes/classic_profiles.py` (688 lines — 8 profile handlers grouped by domain).

**Implementation deviation from plan**: Old `bleep/cli.py` was deleted rather than kept as a shim, because the `bleep/cli/` package directory takes precedence over the file in Python's import resolution.  A `bleep/cli/__main__.py` was added to support `python -m bleep.cli` invocation.  The `bleep/cli/__init__.py` re-exports `main`, `parse_args`, and `_rebuild_debug_argv` for backward compatibility with existing tests and external callers.

---

### Phase 7 Preparation — Pre-Specification Remediation (2026-05-22) — COMPLETE

**Scope**: Resolve three infrastructure issues that would compromise the accuracy
of the Phase 7 API specification if left unaddressed. No new features — only
fixes, normalization, and `__all__` hygiene to ensure the API surface audit
(P7-1) has a clean foundation to document against.

**Decision record** (2026-05-22):
- **UUID strategy**: Full UUID-1 normalization — uppercase canonical form at all
  boundaries (D-Bus ingest, reference dicts, runtime comparisons)
- **Version bump**: Remains 2.8.x through Phase 7; bump to 3.0.0 only after
  Phase 7 spec is written and validated
- **FW7 scope**: Minimal — verify existing `_ensure_device_exists` fix, add
  regression test, close if resolved
- **`__all__` scope**: Full remediation — high-priority + medium-priority modules,
  clean internal symbols, add `TYPE_CHECKING` stubs to lazy packages

**Governing principle**: Phase 7 (P7-1) defines the API boundary as `__all__`
exports.  If `__all__` is incomplete, contains internal symbols, or the data
those functions return has inconsistent UUID casing, the spec will be wrong.
Fix the foundation first.

**Pre-implementation verification** (2026-05-22): All issues confirmed present
in current codebase before work began:

| Issue | Verification result |
|-------|-------------------|
| FW7 FK error | Defensive code (`_ensure_device_exists`) present but **untested** — both existing tests manually call `upsert_device()` first with comment "required for foreign key constraint" |
| `get_name_from_uuid()` + uppercase | **CONFIRMED** — case-sensitive `in` on lowercase dict keys; DB stores uppercase; AoI DB path returns "Unknown" |
| `devices.uuids` not normalized | **CONFIRMED** — `upsert_device()` never calls `_normalize_uuid()` on uuids list |
| `device_le.get_service()` case-sensitive | **CONFIRMED** — line 811 `==` with no normalization |
| AoI `["1800","1801"]` short-form checks | **CONFIRMED** — line 594 never matches full 128-bit UUIDs from DB or D-Bus |
| `__all__` gaps | **CONFIRMED** — `bleep/__init__.py`, `core/output.py`, `pairing/__init__.py`, `callbacks/__init__.py` all lack `__all__`; `dbuslayer.__all__` missing Classic device |

**D-Bus safety analysis** (2026-05-22): Uppercasing UUIDs sent to BlueZ is
**SAFE** for all 7 D-Bus operation categories.  BlueZ parses all UUID strings
through `bt_string_to_uuid()` which uses `sscanf` hex parsing (case-insensitive).
BlueZ **outputs** lowercase via `bt_uuid_to_string()` (`%.8x` format), but
**accepts any hex case on input**.  Verified against BlueZ source and docs:

| Operation | Verdict | Evidence |
|-----------|---------|----------|
| `SetDiscoveryFilter` | SAFE | `parse_uuids` → `bt_string_to_uuid` (case-insensitive hex) |
| `ConnectProfile` | SAFE | `strcasecmp` in `find_connectable_service()` |
| `RegisterApplication/Profile/Endpoint` | SAFE | BlueZ `example-endpoint` uses UPPERCASE UUIDs |
| GATT Service/Char UUID properties | SAFE | Parsed to binary; string case irrelevant |
| SDP / sdptool | SAFE | Already uppercases; hex case-insensitive |
| AdvMonitor patterns | SAFE | Binary bytes, not UUID strings |
| LEAdvertisement ServiceUUIDs | SAFE | `bt_string_to_uuid` everywhere; examples use mixed case |

**BLEEP-side risk**: If outbound UUIDs are uppercased but inbound (BlueZ returns
lowercase) are not normalized, BLEEP's case-sensitive comparisons break.
PREP-7B-3 normalizes BOTH directions simultaneously to prevent this.

---

#### PREP-7A: FW7 — Device Type Evidence FK Verification — COMPLETE (2026-05-22)

- [x] **PREP-7A-1** Regression test: `store_device_type_evidence(mac, ...)` without
  prior `upsert_device()` — assert device row auto-created and evidence persisted
- [x] **PREP-7A-2** Negative test: `store_device_type_evidence("XX:XX:XX:XX:XX:XX")`
  — assert `_normalize_mac` rejects it, no DB write, no FK error
- [x] **PREP-7A-3** Run tests; if both pass, mark FW7 as CLOSED (A2 fix confirmed)
- ~~**PREP-7A-4**~~ N/A — PREP-7A-1 passed; no diagnosis needed

**Files**: `tests/test_device_type_integration.py` (2 new tests).
**Exit criterion**: FW7 confirmed-closed with test evidence. **MET.**

---

#### PREP-7B: Full UUID Uppercase Normalization (UUID-1 + UUID-2) — COMPLETE (2026-05-22)

Canonical form: `XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX` (uppercase, dashed, 128-bit).
Inputs accepted case-insensitively; all storage and comparison uses uppercase.

##### PREP-7B-1: Reference Data Regeneration

- [x] **7B-1a** `update_ble_uuids.py`: change key generation to uppercase (`%04X` + uppercase `_SIG_SUFFIX`)
- [x] **7B-1b** Regenerate `uuids.py` with uppercase keys (1,401 uppercase entries, 0 lowercase)
- [x] **7B-1c** `constants.py`: convert 77 UUID literals + `UUID_NAMES` keys to uppercase
- [x] **7B-1d** `constants.py` Sprint 5E: convert profile UUID constants to uppercase
- [x] **7B-1e** Verify: import succeeds, spot-check 5 known UUIDs — all correct

##### PREP-7B-2: Lookup Function Case-Insensitivity

- [x] **7B-2a** `utils.py` `get_name_from_uuid()`: add `uuid = uuid.strip().upper()`; removed stale lowercase fallback after `uuids.py` regeneration
- [x] **7B-2b** `uuid_utils.py`: canonical form changed from `.lower()` to `.upper()`
- [x] **7B-2c** `uuid_translator.py`: normalize changed to `.upper()`
- [x] **7B-2d** Updated test assertions for uppercase output (`test_uuid_utils.py`, `test_sprint5e.py`)

##### PREP-7B-3: D-Bus Boundary Normalization (BOTH directions)

- [x] **7B-3a** `characteristic.py`: `self.uuid = str(...).strip().upper()`
- [x] **7B-3b** `descriptor.py`: same for descriptor UUID
- [x] **7B-3c** `device_le.py`: normalize service/char UUIDs on read; 7 D-Bus entry points updated
- [x] **7B-3d** `device_classic.py`: normalize `UUIDs` reads; `connect_profile()` normalizes input
- [x] **7B-3e** `adapter.py`: normalize UUID lists in `get_discovered_devices()`
- [x] **7B-3f** `media_stream.py`: `.lower()` → `.upper()` in endpoint/transport UUID matching
- [x] **7B-3g** `signals.py`: `.lower()` → `.upper()` in characteristic UUID comparison
- [x] **7B-3h** Verified Sprint 5 tests pass

##### PREP-7B-3z: D-Bus Boundary Verification Gate

- [x] **7B-3z-1** Verified `get_service("0000180A-...")` matches after normalization
- [x] **7B-3z-2** Confirmed no manual hex-to-byte conversion exists that assumes lowercase
- [x] **7B-3z-3** Full test suite passed (706 passed) after 7B-3, before 7B-4

##### PREP-7B-4: Runtime Comparison Normalization

- [x] **7B-4a** `device_type_classifier.py`: UUID sets, comparisons, and literals uppercased (~14 changes)
- [x] **7B-4b** `aoi_analyser.py`: replaced `["1800","1801"]` with full 128-bit uppercase UUIDs
- [x] **7B-4c** `gatt_profile_decode.py`: `.lower()` → `.upper()` in `_DECODERS` lookup
- [x] **7B-4d** `blectf.py`: no UUID `.lower()` changes needed (already correct)
- [x] **7B-4e** `debug_gatt.py`, `debug_classic.py`, `debug_classic_obex.py`, `debug_multiread.py`: UUID literals and comparisons uppercased
- [x] **7B-4f** `amusica.py`: `.lower()` → `.upper()` in AUDIO_SERVICE_UUIDS membership
- [x] **7B-4g** `pairing/__init__.py`: `.lower()` → `.upper()` + BT SIG suffix uppercased
- [x] **7B-4h** `classic_scan.py`: `.upper()` instead of `.lower()` in filter
- [x] **7B-4i** `capture_config.py`: `.lower()` → `.upper()` in UUID comparison

Additional files fixed during Pass 2 review: `config.py` (3), `_signals.py` (6), `picow.py` (4), `test.py` (6), `check_network_capabilities.py` (3).

##### PREP-7B-5: DB Column Consistency + UUID-2

- [x] **7B-5a** `_devices.py` `upsert_device()`: normalizes `uuids` list to uppercase before JSON serialization
- [x] **7B-5b** `_services.py` `upsert_services()`: already calls `_normalize_uuid()` (uppercases) — UUID-2 satisfied
- [x] **7B-5c** Idempotent fixup: `UPDATE devices SET uuids = UPPER(uuids)` for existing rows — implemented as post-migration idempotent step in `_init_db()` that runs on every DB init; only touches rows where `uuids != UPPER(uuids)`; no schema version bump required — completed 2026-05-22

##### PREP-7B-6: Test Updates + Verification Gate

- [x] **7B-6a** `test_uuid_translation.py`: no changes needed (already passing)
- [x] **7B-6b** `test_uuid_utils.py`: 12 assertions updated for uppercase canonical forms
- [x] **7B-6c** `test_sprint5e.py`: 10 UUID literals uppercased including `endswith()` check
- [x] **7B-6d** `test_aoi_augmentation.py`: no changes needed (already passing)
- [x] **7B-6e** `test_observations_*.py`, `test_insert_adv.py`: no changes needed (already passing)
- [x] **7B-6f** Full test suite: 706 passed, 28 skipped, 0 new failures
- [x] **7B-6g** UUID-1 and UUID-2 marked CLOSED in Future Work section

**Files**: ~45 production, ~3 test files modified.
**Exit criterion**: `get_name_from_uuid("0000180A-0000-1000-8000-00805F9B34FB")`
returns `"Device Information Service"`.  All layers use uppercase.  Full test suite passes.  **MET.**

---

#### PREP-7C: `__all__` API Surface Remediation — COMPLETE (2026-05-22)

##### PREP-7C-1: High-Priority — Add `__all__` to 7 Modules

- [x] **7C-1a** `bleep/__init__.py` — `["__version__", "__author__"]`
- [x] **7C-1b** `bleep/core/output.py` — `["OutputMode", "OutputContext", "output_from_args"]`
- [x] **7C-1c** `bleep/pairing/__init__.py` — 7 public functions
- [x] **7C-1d** `bleep/callbacks/__init__.py` — `["BleepCallback", "DEFAULT_CALLBACK_DIR", "load_callbacks", "get_loaded"]`
- [x] **7C-1e** `bleep/ble_ops/classic/sdp.py` — 4 public functions
- [x] **7C-1f** `bleep/ble_ops/classic/connect.py` — 2 public functions
- [x] **7C-1g** `bleep/analysis/aoi_analyser.py` — `["BytesEncoder", "safe_db_operation", "DEFAULT_AOI_DIR", "AOIAnalyser", "analyse_aoi_data"]`

##### PREP-7C-2: Medium-Priority — Mode Entry Points + Subpackages

- [x] **7C-2a** Added `__all__` to 12 mode modules (blectf, classic_scan, debug_classic, debug_classic_obex, debug_gatt, exploration, media, mesh_provision, signal, survey, aoi, pair)
- [x] **7C-2b** Added `__all__` to `device_set.py` (`["DeviceSet"]`) and `media_assistant.py` (`["MediaAssistant"]`)
- [x] **7C-2c** Evaluated subpackage `__init__.py` files — re-exports aligned in 7C-4

##### PREP-7C-3: Clean Internal Symbols from Existing `__all__`

- [x] **7C-3a** `cli/__init__.py`: removed `_rebuild_debug_argv` from `__all__`
- [x] **7C-3b** `connect.py`: removed `_log_disconnect_reason` from `__all__`
- [x] **7C-3c** Verified `_enum_cmds.py` is internal-only (no `__all__`, not re-exported)
- [x] **7C-3d** Audited all 64 existing `__all__` lists — no other underscore-prefixed symbols found

##### PREP-7C-4: Package Re-Export Alignment

- [x] **7C-4a** `dbuslayer/__init__.py`: Classic device already in `__all__` + lazy-load map; verified accessible
- [x] **7C-4b** `mesh/__init__.py`: added 8 lazy modules to `__all__`
- [x] **7C-4c** `analysis/__init__.py`: added `HIDInfo`, `classify_hid` to imports and `__all__`
- [x] **7C-4d** Evaluated `dbuslayer` media/service/manager/agent — already exposed via lazy-load `__all__`

##### PREP-7C-5: `TYPE_CHECKING` Stubs for Lazy-Load Packages

- [x] **7C-5a** `dbuslayer/__init__.py`: added 13 `TYPE_CHECKING` imports for all lazy-loaded modules
- [x] **7C-5b** `ble_ops/__init__.py`: evaluated — no lazy loading, stubs not needed
- [x] **7C-5c** `mesh/__init__.py`: added 8 `TYPE_CHECKING` imports for lazy-loaded modules
- [x] **7C-5d** `modes/__init__.py`: evaluated — no lazy loading, stubs not needed

##### PREP-7C-6: Verification Gate

- [x] **7C-6a** `from bleep import *` works — exports `__version__`, `__author__`
- [x] **7C-6b** `from bleep.core.observations import *` — 35 DB functions confirmed
- [x] **7C-6c** `from bleep.dbuslayer import *` — LE + Classic device both accessible
- [x] **7C-6d** Full test suite: 706 passed, 28 skipped, 0 failures
- [x] **7C-6e** Summary: 64 → ~85 modules with `__all__` definitions

**Files**: ~25 files modified.
**Exit criterion**: Every programmatic-caller module has `__all__`.  No
underscore-prefixed symbols in public `__all__`.  Static analysis resolves
all lazy-loaded names.  **MET.**

---

#### PREP-7 Execution Order and Final Gate — ALL PASSED (2026-05-22)

Order: PREP-7A → PREP-7B → PREP-7C (7C depends on 7B for stable file contents).

- [x] Full test suite: 706 passed, 28 skipped, 0 new failures
- [x] FW7 closed with test evidence (PREP-7A)
- [x] UUID-1 and UUID-2 closed (PREP-7B)
- [x] `__all__` audit summary: 64 → ~85 modules with `__all__` (PREP-7C)
- [x] `__version__` unchanged at `2.8.4`
- [x] Changelog entry added under Unreleased
- [x] This section updated with completion dates

**Triple-pass review completed** (2026-05-22):
1. **Pass 1 (Correctness)**: All imports, UUID lookups, and API surface verified working
2. **Pass 2 (Consistency)**: Found and fixed 30 additional lowercase UUID literals in 7 runtime files; confirmed `uuids.py` regenerated with 1,401 uppercase keys
3. **Pass 3 (Tests)**: 706 passed, 28 skipped, 0 failures

---

### Phase 7 — API Surface Definition — COMPLETE (2026-05-22)

**Scope**: Define stable function signatures for programmatic callers. This phase produces the specification that a future MCP/Web-GUI/REST layer implements against. No runtime code in this phase — specification only.

- [x] **P7-1** Define library API surface: 84 modules with `__all__`, 410 exported symbols cataloged. Every symbol classified by type, signature, and description. Documented in `bleep/docs/api_specification.md` §3.
- [x] **P7-2** Document single-flight constraints: MainLoop-dependent operations (pairing, agent, GATT server, LE advertising) documented with thread-safety analysis. Documented in `api_specification.md` §4.
- [x] **P7-3** Define structured error response format: all 40 `RESULT_ERR_*` codes mapped to stable string identifiers (`ERR_NOT_FOUND`, `ERR_AUTH_TIMEOUT`, etc.) with exception class cross-reference. Documented in `api_specification.md` §3.9.1.
- [x] **P7-4** Define session lifecycle contract: adapter initialization, BLE/Classic device lifecycle, long-running operation management with cancellation and duration documentation. Documented in `api_specification.md` §5.
- [x] **P7-5** Integration tests: 299 tests in `tests/test_api_surface.py` covering importability, symbol resolution, internal export hygiene, error hierarchy, OutputContext contract, observation DB contract, preflight contract, signals contract, pairing contract, EnumerationController contract, symbol census, and package re-export integrity.
- [x] **P7-6** API specification document: `bleep/docs/api_specification.md` (v0.1.0) — 8 sections covering overview/conventions, package hierarchy, full API catalog (17 subsections), concurrency constraints, session lifecycle, data formats, symbol census, and version history.

**Nota Bene**: The `bleep-mcp/` codebase is out of scope and untrusted. This specification is clean-room design from BLEEP internals. Any future MCP server must be reimplemented against this specification, not adapted from the existing `bleep-mcp/` code.

---

### Data Pipeline Remediation — AoI Report & DB Retrieval Fixes (2026-05-24)

**Source**: Exhaustive codebase audit tracing every data path from scan discovery → DB persistence → retrieval → report generation. Audit identified 10 bugs (3 critical, 3 major, 2 moderate, 2 minor) where data is correctly collected and stored but fails to appear in reports due to key mismatches, type mismatches, and missing field mappings.

**Files**: `bleep/analysis/aoi_analyser.py`, `bleep/core/observations/_devices.py`,
`bleep/core/observations/_services.py`, `bleep/core/observations/_aoi.py`,
`bleep/modes/db.py`, `bleep/modes/aoi.py`, `bleep/modes/survey.py`.

**Audit evidence**: All bugs have file:line citations against the codebase as of 2026-05-24.
Verified against actual dry-run output in `workDir/BigMoves/recon_20260523_194935/`.

#### Phase 1 — Critical: AoI Report Identity & Scoring (BUG-1, BUG-2) — COMPLETE (2026-05-24)

These two bugs made every AoI report functionally useless — all devices showed as
"Unknown"/"Unnamed" with a fixed 5/10 score and zero High/Med/Low findings.

- [x] **DP-1e** Added helper `_resolve_identity(device_data) → (address, name)` to centralise
  the flat-vs-nested resolution (handles both DB shape `{device: {mac, name}}` and
  file shape `{address, name}`)
- [x] **DP-1a** `_generate_markdown_report()`: replaced inline `.get("address")`/`.get("name")`
  with `_resolve_identity()`
- [x] **DP-1b** `_generate_aggregate_markdown()`: replaced both summary table and per-device
  detail section identity lookups with `_resolve_identity()`
- [x] **DP-1c** `_generate_text_report()`: replaced with `_resolve_identity()`
- [x] **DP-1d** `analyze_device_data()` bridge method: uses `_resolve_identity()` for MAC
  extraction instead of flat-only `device_data.get("address")`
- [x] **DP-2a** Added `_assign_concern_risk()` helper that classifies concerns as high/medium/low
  based on reason text and source; applied at all 5 concern-append sites in `analyse_device()`
  (characteristic security concerns, SDP profile flags, pairing concerns)
- [x] **DP-2b** `_calculate_security_score()`: retroactively classifies legacy concerns without
  `risk` field via `_assign_concern_risk()`; also added `description` fallback from `reason`
  in vulnerability renderers (markdown, text, inline)
- [x] **DP-2c** Aggregate table High/Med/Low columns now populate correctly (verified by test)
- [x] **DP-2d** 32 unit tests in `tests/test_data_pipeline_fixes.py`: scoring, risk assignment,
  score stacking, cap-at-10, legacy backward compatibility
- [x] **DP-2e** 7 identity resolution tests covering flat, nested, empty, None, partial,
  precedence, and missing-keys scenarios

**Test strategy**: Generate AoI report against existing DB data (devices from
`recon_20260523_194935`); confirm device names/MACs appear correctly and scores
reflect actual concern severity.

#### Phase 2 — Critical: DB→Analyser Characteristic Shape Mismatch (BUG-3) — COMPLETE (2026-05-24)

The analyser's characteristic analysis branch silently skipped all DB-loaded data
because `get_device_detail()` returns `characteristics` as a list (not a dict),
which is truthy (skipping the `services_mapping` branch) but fails `isinstance(dict)`.

**Approach taken**: Both DP-3b (root-cause fix at load time) and DP-3a (defensive
fallback) were implemented for defense in depth.

- [x] **DP-3b** Added `_hydrate_db_device_data()` helper in `aoi_analyser.py` that
  transforms DB-shaped data in `load_device_data()` after loading from DB:
  converts `characteristics` list to UUID-keyed dict (properties csv→list,
  value bytes→hex), builds `services_mapping` from services+characteristics,
  and extracts `landmine_map`/`permission_map` from `security_maps`
- [x] **DP-3a** Added defensive `isinstance(characteristics, list)` branch in
  `analyse_device()` as a safety net for callers that bypass `load_device_data()`.
  Converts properties csv→list, value bytes→hex inline before analysis
- [x] **DP-3c** `_hydrate_db_device_data()` extracts `landmine_map` and `permission_map`
  from the latest `security_maps` row (ordered by ts DESC), parses JSON, and injects
  into top-level keys — only if not already present (no overwrite)
- [x] **DP-3d** 21 new unit tests in `tests/test_data_pipeline_fixes.py`:
  `TestHydrateDbDeviceData` (10 tests), `TestAnalyseDeviceListChars` (6 tests),
  `TestHydratedDbAnalysis` (5 integration tests covering hydrate→analyse→report)
- [x] **DP-3e** Integration tests confirm: hydrated DB data produces characteristic
  findings, markdown reports show correct identity, security maps flow through,
  and un-hydrated list-shaped data still works via the defensive fallback

#### Phase 3 — Major: load_device_data Fallback & Analysis Storage (BUG-4, BUG-5) — COMPLETE (2026-05-24)

- [x] **DP-4a** `aoi_analyser.py` `load_device_data()`: changed truthiness check from
  `if device_data:` to `if device_data and device_data.get("device"):` so that an
  empty shell `{device: None, services: [], ...}` falls through to file lookup
- [x] **DP-4b** Improved logging: `logger.info` when DB returns empty shell, `logger.warning`
  when DB access fails — both clearly indicate fallback to file-based lookup
- [x] **DP-5a** `_aoi.py` `store_aoi_analysis()`: extended INSERT/UPSERT to persist
  `analysis["details"]` as `analysis_details` JSON column
- [x] **DP-5b** `_aoi.py` `get_aoi_analysis()`: reads `analysis_details` column when
  present and returns it as `result["details"]` (preserving key naming convention)
- [x] **DP-5c** Schema migration v12→v13 in `_connection.py`: `ALTER TABLE aoi_analysis ADD
  COLUMN analysis_details JSON`; base `CREATE TABLE` updated for fresh installs;
  `_SCHEMA_VERSION` bumped to 13
- [x] **DP-5d** 7 new tests: `TestLoadDeviceDataFallback` (3 tests for empty shell, populated
  shell, DB exception), `TestAoiAnalysisRoundTrip` (4 tests for details round-trip,
  no-details, update-overwrites, concerns-with-risk round-trip)

#### Phase 4 — Major: `db show` Data Truncation (BUG-6) — COMPLETE (2026-05-24)

Previously `db show` emitted only `characteristics_count` and `classic_services_count`
instead of the actual data. Both JSON and terminal outputs were truncated.

- [x] **DP-6a** `modes/db.py` `run()` JSON path: now emits the full
  `get_device_detail()` dict with `_binary_to_hex()` conversion for JSON safety
- [x] **DP-6b** `modes/db.py` `show_device()` terminal output: redesigned to show
  device summary header plus expanded sections for characteristics (uuid, handle,
  properties, has_value), classic services (uuid, channel, name), and SDP records
  (service_uuid, service_name, channel)
- [x] **DP-6c** Added `--full` flag to `db show`: dumps the complete hydrated
  `get_device_detail()` dict as formatted JSON (alternative to `export` without
  history/adv_reports overhead)
- [x] **DP-6d** Updated CLI parser in `bleep/cli/parsers/db.py` and backward-compat
  `main()` parser in `modes/db.py` for `--full` flag
- [x] **DP-6e** 8 new tests: `TestDbShowJsonCompleteness` (5 tests for characteristics,
  SDP records, classic services, bytes→hex, empty device) and `TestDbShowTerminal`
  (3 tests for expanded sections, classic services, `--full` JSON output)

#### Phase 5 — Moderate: SDP MAP Columns & Survey→AoI Chain (BUG-7, BUG-8) — COMPLETE

- [x] **DP-7a** `_services.py` `upsert_sdp_record()`: added `mas_instance_id`,
  `supported_message_types`, `supported_features` to the INSERT and ON CONFLICT
  UPDATE column lists, reading from `record.get(...)`.  Docstring updated to
  document the three MAP-specific keys.
- [x] **DP-7b** Verified: SDP parser (`bleep/ble_ops/classic/sdp.py`) already populates
  `mas_instance_id`, `supported_message_types`, `supported_features` in all three
  code paths (XML, text, single-record).  No changes needed.
- [x] **DP-7c** 3 new tests in `TestSdpMapColumnsRoundTrip`: MAP fields stored and
  retrieved, None when absent, upsert-update overwrites correctly.
- [x] **DP-8a** `modes/aoi.py` `_iter_macs()` now returns
  `List[Dict[str, Optional[str]]]` with `mac`, `name`, `device_type` keys instead
  of plain strings.  Survey JSON metadata is preserved through extraction.
- [x] **DP-8b** Scan loop pre-seeds the observation DB via
  `upsert_device(mac, name=..., device_type=...)` when survey JSON carries
  `name` or `device_type`, before enumeration begins.  Skipped for plain MAC
  strings or when `--no-db` is active.
- [x] 7 additional tests: `TestIterMacsSurveyMetadata` (5 tests for various input
  shapes) and `TestSurveyPreSeedUpsert` (2 tests for pre-seed call and skip).
- [x] Updated `tests/test_survey.py` (3 tests) and `tests/test_aoi_augmentation.py`
  (3 tests) to match `_iter_macs` new return type.

#### Phase 6 — Minor: Export Completeness & Pagination (BUG-9, BUG-10) — COMPLETE

- [x] **DP-9a** `_devices.py` `export_device_data()`: added `aoi_analysis` via
  `get_aoi_analysis(mac)` — included only when analysis exists for the device.
- [x] **DP-9b** `_devices.py` `export_device_data()`: added `device_type_evidence` via
  `get_device_type_evidence(mac)` — included only when evidence exists.
- [x] **DP-9c** 3 new tests in `TestExportDeviceDataCompleteness`: verifies
  `aoi_analysis` key present after `store_aoi_analysis`, `device_type_evidence`
  present after `store_device_type_evidence`, and both absent for plain devices.
- [x] **DP-10a** `modes/db.py` `list` handler and `list_devices()` now accept and
  pass `limit`/`offset` through to `get_devices()`.  JSON/quiet output path
  also passes pagination.
- [x] **DP-10b** `cli/parsers/db.py`: added `--offset` arg (default 0).  Changed
  `--limit` default to `None` (resolved to 100 for list, 50 for timeline at
  handler level).  Backward-compat `main()` parser also updated with both args.
- [x] **DP-10c** `get_devices()` docstring updated: `limit` now reads "default: 100",
  `offset` reads "default: 0".
- [x] 5 additional tests in `TestDbListPagination`: limit/offset pass-through,
  default limit 100, CLI parser `--offset`, CLI parser `--limit` default None,
  JSON output pagination pass-through.

#### Post-Audit Fixes — Verification Script Analysis (2026-05-25) — COMPLETE

- [x] **VA-1** `bleep/cli/main.py`: added `"uuid-translate"` and `"uuid-lookup"` to
  `_non_bt_modes` set — pure-software UUID lookups no longer require an adapter.
- [x] **VA-2a** `_devices.py` `upsert_device()`: ON CONFLICT clause for `name` column
  now uses CASE logic — a resolved name is never downgraded to a placeholder
  ("Unknown Device", "Unknown").  Placeholder→real upgrades still work.
- [x] **VA-2b** `aoi_analyser.py` `save_device_data()`: `name` is only passed to
  `upsert_device()` when the incoming data has a meaningful name.  Fallback to
  "Unknown Device" removed.
- [x] **VA-2c** `modes/aoi.py` file-import paths (lines 665, 753): same placeholder
  filtering applied to both `db-import` and `file-sync` `upsert_device()` calls.
- [x] **VA-3** 7 new tests: `TestUuidTranslateNoAdapter` (2 tests for adapter guard
  bypass) and `TestUpsertDeviceNameProtection` (5 tests for name overwrite
  protection, placeholder upgrade, real-to-real update, save_device_data filtering).

#### Report & UUID-Translate Fixes (2026-05-25) — COMPLETE

- [x] **RU-1** `aoi_analyser.py` `_generate_markdown_report()`: fixed `### None`
  service headings — changed `service.get("name", fallback)` to
  `service.get("name") or get_name_from_uuid(uuid) or uuid` so null-valued
  `name` keys fall through to UUID lookup instead of rendering as `None`.
- [x] **RU-2** `uuid_translator.py` `UUIDDatabase.search()`: added `seen` set keyed
  on `(category, name)` to deduplicate matches — 128-bit BT SIG UUIDs that match
  via both direct lookup and short-form expansion no longer produce duplicate rows.
- [x] **RU-3** 5 new tests: `TestServiceNameNoneInReport` (2 tests for None-valued
  service name rendering) and `TestUUIDTranslateDeduplicate` (3 tests for search
  deduplication: 128-bit BT SIG, short UUID, non-SIG UUID).
- [x] Full suite: 1103 passed, 1 failed (CTF hardware), 28 skipped.

#### Execution Order & Dependencies

```
Phase 1 (DP-1*, DP-2*)  ← no dependencies; fixes reporting immediately
    ↓
Phase 2 (DP-3*)         ← benefits from Phase 1 identity fix being in place
    ↓
Phase 3 (DP-4*, DP-5*)  ← DP-5 requires schema migration; DP-4 depends on Phase 2 shape fix
    ↓
Phase 4 (DP-6*)         ← independent but best after Phase 2 ensures full data flows
    ↓
Phase 5 (DP-7*, DP-8*)  ← independent; moderate priority
    ↓
Phase 6 (DP-9*, DP-10*) ← lowest priority; can be done anytime
```

**Total items**: 33 tasks across 6 phases.
**Estimated scope**: ~400 lines of code changes + ~200 lines of tests + 1 schema migration.
**Risk**: Phase 3 (schema migration) is the only item requiring careful rollout; all others
are purely additive or fix existing logic without schema changes.

---

### Future Work — Service & UUID Reporting (Target Device Capability Summary)

**Goal**: Ensure BLEEP produces a clear, consolidated report of all services and UUIDs reported by a Bluetooth device via both BLE (GATT service discovery) and Classic (SDP records) scans.

**Purpose**:
- Provide a single-view summary of potential functionality exposed by a target device
- Enable rapid assessment of attack surface and interaction possibilities
- Consolidate currently-separate data paths (GATT services table, SDP records, classic_services) into a unified device capability map

**Planned deliverables**:
- [ ] **SVC-1** `bleep device-report <MAC>` CLI command: query DB for all known services (GATT + Classic/SDP), resolve UUIDs to human-readable names, output structured summary (terminal + JSON)
- [ ] **SVC-2** Ensure all scan paths (BLE enum, Classic SDP, survey) persistently store every discovered service UUID — verify no data is lost between CLI display and DB insertion
- [ ] **SVC-3** Unified service map data structure: combine GATT `services` table + `classic_services` + `sdp_records` into a single device capability view with protocol source annotations
- [ ] **SVC-4** Profile-to-functionality mapping: translate discovered UUIDs into plain-language descriptions of what the device can do (e.g., "Heart Rate Monitor", "Audio Sink (A2DP)", "File Transfer (OBEX FTP)")

**Future dependency — SDP Tool Replacement**:
- [ ] **SDP-1** Design and implement a native Python SDP inquiry capability to replicate and extend `sdptool` functionality at the low-level protocol layer
- [ ] **SDP-2** Direct L2CAP SDP channel interaction (PSM 0x0001) for raw Service Discovery Protocol PDU exchange, independent of BlueZ `sdptool` binary
- [ ] **SDP-3** Full SDP attribute parsing: Service Record Handle, Service Class ID List, Protocol Descriptor List, Browse Group List, Language Base Attribute ID List, Profile Descriptor List, all vendor-specific attributes
- [ ] **SDP-4** SDP service browsing: hierarchical browse group traversal (Public Browse Root → subgroups → individual records)
- [ ] **SDP-5** Integration with existing `bleep/ble_ops/classic/sdp.py` — extend or replace current `discover_services_sdp()` which currently shells out to `sdptool`

**Notes**:
- This work is related to but distinct from Phase 2 (DB persistence gaps) — Phase 2 ensures data reaches the DB; this work ensures the data is queryable as a coherent capability summary
- The SDP tool replacement enables deeper inquiry without depending on external binaries and allows BLEEP to operate on systems where `sdptool` is unavailable or restricted

---

### Remote Bluetooth Version Detection — Implementation Plan

**Goal**: Enable BLEEP to definitively identify the Bluetooth Core Specification version
running on remote devices, replacing current heuristic-only inference with authoritative
LMP version data from the link layer.

**Status**: Phases 1–5 COMPLETE (2026-05-26) — RV-4c (LL_VERSION_IND capture) deferred as stretch goal

**Background (2026-05-25 analysis)**:
- BlueZ provides `hci_read_remote_version()` (HCI OCF 0x001D) which returns LMP version,
  manufacturer, and LMP subversion after ACL connection — exercised by `hcitool info <bdaddr>`
- BlueZ D-Bus (`org.bluez.Device1`) does NOT expose remote LMP version; only Modalias (PnP product version)
- BLEEP currently has: local adapter HCI/LMP (`query_hci_version()`), SDP profile version
  heuristics (`SDPAnalyzer`), and PnP Modalias — none of which provide the actual remote BT spec version
- Advertisement packets do NOT carry Bluetooth Core/LMP version (see "Advertisement Analysis" below)

#### Advertisement Packet Version Analysis

**Conclusion: Bluetooth Core/LMP version CANNOT be extracted from advertisement packets.**

AD types defined by the Bluetooth SIG (`References/ad_types.yaml`) that relate to version/identity:

| AD Type | Name | What It Contains | Useful for BT Version? |
|---------|------|-----------------|----------------------|
| `0x10` | Device ID | PnP vendor/product/version (8 bytes) | **No** — product firmware revision, not LMP |
| `0x27` | LE Supported Features | LE feature bitmask | **Indirect only** — feature presence implies minimum spec version |
| `0xFF` | Manufacturer Specific Data | Vendor-proprietary blob | **No** — vendor-defined, no standard version field |
| `0x01` | Flags | Discoverable mode + BR/EDR support | **No** — 1 bit for BR/EDR support, no version |
| `0x0D` | Class of Device | CoD service/major/minor | **No** — device class, not version |

**Why LE Supported Features (0x27) is only indirect:**
- Features are additive across spec versions (e.g., LE 2M PHY added in 5.0, LE Coded PHY in 5.0,
  Connected Isochronous Stream in 5.2, Advertising Coding Selection in 5.3)
- Presence of a feature implies "at least version X" but absence doesn't confirm the version
- Many devices don't advertise all supported features in AD data
- BlueZ does not decode this AD type into a version number

**How remote BT version IS obtainable:**

| Method | Transport | Authoritative? | Requires Connection? |
|--------|-----------|---------------|---------------------|
| HCI Read Remote Version (OCF 0x001D) | Classic BR/EDR | **Yes** — returns LMP byte directly | Yes (ACL handle) |
| LL_VERSION_IND (Link Layer) | BLE | **Yes** — exchanged during LE connection | Yes (LE connection) |
| GATT Device Information Service (0x180A) | BLE | Partial — firmware/software strings | Yes (GATT read) |
| SDP Profile Descriptor versions | Classic | **No** — profile version, not core version | Yes (SDP query) |

#### Phase 1 — Remote Version Query via `hcitool info` (Classic BR/EDR)

New function following the same subprocess-parse pattern as `query_hci_version()`.

- [x] **RV-1a** New function `query_remote_version(address, adapter)` in `bleep/ble_ops/classic/version.py`
  - Subprocess: `hcitool -i <adapter> info <bdaddr>`
  - Parse output regex for: `LMP Version: X.Y (0xNN) LMP Subversion: 0xNNNN`, `Manufacturer: Name (ID)`
  - Parse LMP features pages (hex octets per page line)
  - Return type: `Optional[Dict[str, Any]]` with keys:
    `lmp_version` (int), `lmp_subversion` (int), `manufacturer` (int),
    `lmp_spec` (str via `map_lmp_version_to_spec()`), `features_raw` (list[str] hex page dumps)
  - Timeout: 30s (ACL connection + HCI read + features read), graceful failure → None
  - Error handling: tool-not-found (via preflight `shutil.which`), subprocess timeout,
    non-zero exit (connection refused / device not reachable), unparseable output
  - Logging: `print_and_log()` with `LOG__DEBUG` for failures
- [x] **RV-1b** Add `query_remote_version` to `__all__` in `version.py`
- [x] **RV-1c** Register lazy import in `bleep/ble_ops/__init__.py`:
  - Add `"query_remote_version"` to `__all__` list
  - Add entry in `_LAZY_IMPORTS`: `"query_remote_version": (".classic.version", "query_remote_version")`
- [x] **RV-1d** Unit tests in `tests/test_remote_version.py`:
  - Mock `subprocess.run` with captured `hcitool info` output (success case)
  - Mock timeout scenario (`subprocess.TimeoutExpired`)
  - Mock connection refused (non-zero returncode, stderr contains error)
  - Mock `shutil.which` returning None (tool not installed)
  - Verify all parsed fields match expected values
  - Verify `map_lmp_version_to_spec()` integration produces correct spec string

#### Phase 2 — Database Schema Extension (Schema v14)

Following the same migration pattern as schema v10→v13 (ALTER TABLE, bump `_SCHEMA_VERSION`,
update base CREATE TABLE).

- [x] **RV-2a** Add columns to `devices` table in `bleep/core/observations/_connection.py`:
  - `lmp_version INT` — remote LMP version byte (0x00–0x0F)
  - `lmp_subversion INT` — remote LMP subversion (uint16)
  - `bt_manufacturer INT` — remote controller manufacturer ID (uint16)
  - `bt_spec_version TEXT` — human-readable spec string (e.g., "Bluetooth 5.0")
  - `lmp_features TEXT` — JSON-encoded feature page hex strings
  - `version_queried_at DATETIME` — timestamp of last successful version query
- [x] **RV-2b** Schema migration function in `_connection.py`:
  - Bump `_SCHEMA_VERSION` from 13 → 14
  - Add migration case in `_migrate_schema()`: 6 × `ALTER TABLE devices ADD COLUMN ...`
  - Update base `CREATE TABLE IF NOT EXISTS devices` with new columns (for fresh installs)
- [x] **RV-2c** Add new columns to `_DEVICE_COLS` frozenset in `bleep/core/observations/_devices.py`:
  - Add: `"lmp_version"`, `"lmp_subversion"`, `"bt_manufacturer"`,
    `"bt_spec_version"`, `"lmp_features"`, `"version_queried_at"`
  - Add `"lmp_features"` to the JSON-serialization list (alongside `uuids`, `service_data`,
    `advertising_data`) if stored as a Python list
- [x] **RV-2d** Unit tests:
  - Fresh DB creation → verify columns exist
  - Migration from v13 → v14 → verify columns added
  - `upsert_device(mac, lmp_version=9, bt_spec_version="Bluetooth 5.0", ...)` round-trip
  - Verify JSON round-trip for `lmp_features` field

#### Phase 3 — Integration with Existing CLI Flows

Following the same pattern as the current `--version-info` flow in `modes/classic_enum.py`
(import at function scope, call, collect dict, display).

- [x] **RV-3a** `bleep/modes/classic_enum.py` — augment `--version-info` block:
  - After existing `query_hci_version()` (local) call, add `query_remote_version(args.address)`
  - Store result under `version_info_data["remote"]` key
  - In display section (lines 132–186), add "Remote Device (authoritative)" block showing:
    LMP Version, LMP Subversion, Manufacturer, Bluetooth Spec Version, Features summary
  - Persist to DB: `_obs_cenum.upsert_device(args.address, lmp_version=..., bt_spec_version=..., ...)`
- [x] **RV-3b** `bleep/dbuslayer/device_classic.py` — new method `query_and_store_remote_version()`:
  - Calls `query_remote_version(self.mac_address)` (import from `bleep.ble_ops.classic.version`)
  - On success, calls `upsert_device()` with the version fields
  - Returns the result dict (or None on failure)
  - Follows same pattern as existing `get_device_version_info()` but actively queries HCI
- [x] **RV-3c** `bleep/modes/aoi.py` — AoI security analysis integration:
  - In `_analyse_device()` or equivalent, check `device_data.get("lmp_version")`
  - If `lmp_version` < 8 (BT 4.2): add security concern "Outdated Bluetooth version —
    lacks Secure Connections, vulnerable to KNOB/BIAS attacks"
  - If `lmp_version` < 6 (BT 4.0): higher severity — "Legacy Bluetooth, no LE Secure Connections"
  - Cross-reference: if SDP-inferred version differs significantly from actual LMP, flag anomaly
- [x] **RV-3d** `bleep/analysis/sdp_analyzer.py` — cross-validation:
  - New method `cross_validate_lmp(lmp_version: int)` on `SDPAnalyzer`:
    compares actual LMP against highest profile version found in SDP
  - If mismatch (e.g., device runs BT 4.0 but claims HFP 1.8 which requires BT 5.x),
    add to anomalies list with explanation
  - Return anomaly dict (or empty) — consumed by AoI and `--analyze` display

#### Phase 4 — BLE Version Detection (Post-Connection)

- [x] **RV-4a** GATT Device Information Service (0x180A) extraction in existing enum flow:
  - In `bleep/ble_ops/le/scan.py` or `connect.py` post-enumeration: check if service
    UUID `0x180A` was discovered with characteristics:
    - `0x2A26` (Firmware Revision String)
    - `0x2A28` (Software Revision String)
    - `0x2A50` (PnP ID — 7 bytes: vendor_id_source + vendor_id + product_id + product_version)
  - If characteristic values already read during enumeration (stored in DB `characteristics`
    table), extract and add to device info
  - Store `firmware_revision` and `software_revision` as device notes or dedicated columns
    (decide: new columns vs JSON in existing `notes` field)
- [x] **RV-4b** LE Supported Features inference (AD type 0x27):
  - New helper `infer_min_bt_version_from_le_features(features_bytes: bytes) -> Optional[str]`
    in `bleep/ble_ops/classic/version.py` (or new `bleep/ble_ops/common/version_inference.py`)
  - Feature bit → minimum version mapping:
    - Bit 8 (LE 2M PHY): ≥ 5.0
    - Bit 9 (Stable Modulation Index - Tx): ≥ 5.0
    - Bit 11 (LE Coded PHY): ≥ 5.0
    - Bit 12 (LE Extended Advertising): ≥ 5.0
    - Bit 14 (LE Periodic Advertising): ≥ 5.0
    - Bit 28 (Connected Isochronous Stream - Central): ≥ 5.2
    - Bit 30 (Isochronous Broadcaster): ≥ 5.2
  - Returns the highest implied minimum version
  - Call from scan enrichment if `advertising_data` contains key `"39"` (0x27 = 39 decimal)

#### Phase 5 — Reference Data Integration

- [x] **RV-5a** New loader in `bleep/bt_ref/` (or extend existing `yaml_cache.py`):
  - Load `References/core_version.yaml` → dict mapping int→str
  - Load `References/company_identifiers.yaml` → dict mapping int→str
  - Lazy-load with module-level cache (same pattern as existing `bt_ref` loaders)
- [x] **RV-5b** Update `bleep/ble_ops/classic/version.py`:
  - `map_lmp_version_to_spec()` uses YAML-loaded map with `_LMP_VERSION_MAP` as fallback
  - New `resolve_manufacturer_name(manufacturer_id: int) -> Optional[str]` using company_identifiers
- [x] **RV-5c** Remove hardcoded `_LMP_VERSION_MAP` values that duplicate YAML (keep dict as
  fallback-only with comment explaining why)

**Dependencies**: Preflight (`bleep/core/preflight.py`) already verifies `hcitool` availability;
no new system-level requirements.

**Risks & mitigations**:
- `hcitool info` requires ACL connection (device must be connectable) → graceful None return,
  fall back to existing SDP inference
- `hcitool` deprecated in BlueZ >5.50 → design `btmgmt` fallback in `query_remote_version()`
  as secondary code path (check tool availability, try btmgmt first if hcitool missing)
- Connection attempt may alert the target device → document in CLI `--help` that
  `--version-info` is an active operation (not passive)

#### Future Work (Stretch Goals)

- [ ] **RV-4c** LL_VERSION_IND capture via btmon passive monitoring:
  - During LE connection, the link layer exchanges `LL_VERSION_IND` PDUs containing
    the remote controller's Core Spec version — this is the BLE equivalent of Classic's
    HCI Read Remote Version
  - Implementation requires: background `btmon` subprocess, real-time event parsing,
    MAC correlation (btmon shows handles, not MACs directly)
  - Deferred: complex integration with low incremental value given GATT DIS + LE
    features inference already cover the BLE version detection use case
  - Potential approach: `subprocess.Popen(["btmon", "--write", tmpfile])` during connect,
    parse `LL_VERSION_IND` from tmpfile post-connect
- [ ] **RV-FUTURE-1** `btmgmt` fallback for `query_remote_version()`:
  - `hcitool` is deprecated in BlueZ >5.50; `btmgmt` provides equivalent functionality
  - Add `_query_remote_version_btmgmt()` as secondary code path when hcitool unavailable
- [ ] **RV-FUTURE-2** Integrate `infer_min_bt_version_from_le_features()` into passive scan enrichment:
  - During BLE scanning, if AD type 0x27 (LE Supported Features) is present in
    advertising data, infer minimum BT version and persist `bt_spec_version` on device record

---

### GLib MainLoop Architecture Decision Record

**Decision**: Maintain current architecture (MainLoop in background thread, `input()` on main thread) for v3.0. Defer Option A inversion (MainLoop on main thread, `input()` on worker thread via `GLib.idle_add()`) to v3.1+.

**Rationale** (from `mainloop_architecture.md` lines 63-117, `mainloop_requirement_analysis.md` lines 37-98):
- CLI modes are single-shot: scan, connect, enumerate, pair, then exit — no persistent MainLoop needed
- Survey is self-contained with its own timing loop
- Debug mode is terminal-only (not exposed via API); DB persistence handles data extraction
- Agent/pair operations are correctly serialized: one pairing at a time is a Bluetooth spec limitation, not an architecture limitation
- The MainLoop inversion only becomes necessary for a persistent server process handling concurrent API requests involving pairing — which is Phase 7+ territory

**Constraints for API callers** (document in Phase 7):
- Operations requiring `GLib.MainLoop` on main thread (pairing, agent callbacks) must be serialized
- The API layer must enforce single-flight semantics for these operations
- PAN client operations, GATT reads/writes, SDP queries, and scan operations do NOT require MainLoop and can run concurrently

---

### Enumeration Path Decision Record

**Decision**: Preserve all three enumeration paths (scan.py variants, EnumerationController, scan_modes.py) and unify them in Phase 4 by making the controller the outer wrapper that delegates to variant-specific logic.

**Rationale** (from architecture audit 2026-05-18):
- `scan.py` variants (passive/naggy/pokey/brute) implement distinct **post-connect analysis strategies** — multi-read for value change detection, write probes, payload fuzzing. These are NOT duplicates of the controller.
- `EnumerationController` provides **retry/annotation infrastructure** — typed error records, structured result objects, up to 3 full connect cycles. This is orthogonal to variant-specific logic.
- `scan_modes.py` provides **connection strategy variation** — exponential backoff, jitter, per-mode timeouts.  As of P4-3, these are parameterized into `connect.py` kwargs; `scan_modes.py` functions are thin wrappers.
- Removing any path would lose real, proven functionality.
- The `--controlled` flag is a proof-of-concept (per `changelog.md`); the correct fix is integration, not removal.

**What Phase 4 has changed / will change**:
- ~~`EnumerationController.enumerate(mode="naggy")` will actually invoke `naggy_enum` multi-read behavior instead of just toggling `deep_enumeration`~~ — **done** (P4-1)
- ~~`scan_modes.py` connection strategies will be parameterized into `connect.py` kwargs instead of reimplementing the full pipeline~~ — **done** (P4-3)
- ~~`--controlled` flag will be removed (controller becomes the default)~~ — **done** (P4-2; flag accepted but no-op)
- ~~`EnumerationResult` annotations and security maps will be persisted to the observation DB~~ — **done** (P4-4; `persist_security_maps()` method on `EnumerationResult`; wired into `enum-scan`, `gatt-enum`, and AoI)
- ~~Documentation will describe the unified wrapper-based architecture~~ — **done** (P4-7; `ble_scan_modes.md`, `explore_mode.md`, `gatt_enumeration.md`, old→new translation guide in this tracker)
- ~~AoI mode will benefit from variant-specific behavior for the first time~~ — **done** (P4-6; `_scan_target(deep=True)` → `mode="pokey"` with 2 rounds; post-pair re-enum also pokey)

---

## Hardware-swap gap analysis — Realtek RTL8761B/BU antenna (2026-08-11) — [ ] OPEN / awaiting acceptance

> **CONTEXT.** A new USB Bluetooth antenna was attached and profiled live before any
> code change. Controller: **Realtek RTL8761B/BU**, USB `6655:8771`, `hci0`
> BD `10:A5:62:E1:5C:1A`, **HCI/LMP 5.1**, dual-mode (`<LE and BR/EDR>`), roles
> `central`+`peripheral`, EDR + eSCO 2/3 Mbps, `<SCO link>`/`<CVSD>`/`<transparent SCO>`,
> mgmt settings `powered bondable ssp br/edr le secure-conn wide-band-speech`,
> `LEAdvertisingManager1` `SupportedInstances=4` + secondary PHYs `1M/2M/Coded`.
> Stack: **BlueZ 5.86** on Arch, `bluetoothd` running **without `-E`**,
> `/etc/bluetooth/main.conf` `Experimental`/`KernelExperimental` left at commented default
> (=false). The controller binds cleanly to the whole D-Bus core; **no vendor branching
> exists or is needed** (`usb_ids.py`/`modalias.py` are lookup-only). Items below are the
> residue that needs future work; each notes de-dup against prior tracker entries.
>
> **Already covered — intentionally NOT re-filed here:** PAN `bnep` kernel-module
> preflight (PAN/BNEP **G2**, RESOLVED); generic non-`hci0` selection (**FW6**, open);
> controller peripheral-advertising / `--include-appearance` quirks (**LTR-8/LTR-9**,
> RESOLVED); multi-antenna `hci0+hci1` live-test seam (**LT-1/LT-2**). Extended-adv /
> 2M / Coded PHY are **supported** by this chip (verified) — not a gap.

### HW-1 — `media_stream.py` hardcodes `/org/bluez/hci0` in the transport-path builder — ✅ IMPLEMENTED (2026-08-11)

> **As-built (Option A).** `bleep/dbuslayer/media_stream.py`:
> - Added module-level `_device_base_from_path(path_str)` — the shared base-extraction
>   helper (`split("/sep")[0].split("/fd")[0]`), now reused by both the new resolver and
>   `_collect_media_objects()` (DRY; identical prior behaviour preserved).
> - Added module-level `_first_adapter_name()` — returns the first enumerated adapter name
>   via a **lazy** `from bleep.dbuslayer.adapter import system_dbus__bluez_adapter` +
>   `list_adapters()[0]["name"]` (lazy import avoids any import cycle; exceptions degrade to
>   `None`).
> - Added `MediaStreamManager._resolve_device_path()` — scans `GetManagedObjects()` for the
>   live `.../dev_<MAC>` base (MAC normalised `:`→`_` + `.upper()`); returns `None` on
>   absence or a failing `GetManagedObjects()`.
> - Rewrote `_device_path()` — returns the resolved live path when present; otherwise builds
>   `/org/bluez/{first_adapter}/dev_{mac}`, defaulting to `hci0` **only** when no adapter can
>   be enumerated. No new constructor params; sole caller `_cycle_device_connection()`
>   unchanged.
> **Tests.** `tests/test_media_helpers.py` +6: base-extraction helper; resolves device under
> `hci1` (non-`hci0` regression guard); fallback uses first adapter (`hci3`), not `hci0`;
> fallback defaults to `hci0` only when no adapters; absent device → `None`; failing
> `GetManagedObjects()` → `None`. Existing `_cycle_device_connection` tests made hermetic by
> stubbing the two resolution seams. Full media/audio/preflight/api-surface run: 423 passed,
> 4 pre-existing skips; lint clean.
> **Acceptance — met.** No operational literal `/org/bluez/hci0` remains in
> `media_stream.py` (only docstring examples); `_cycle_device_connection` acts on the
> adapter-correct path; new + existing tests green. Triple-pass review (correctness /
> integration / runtime) completed with no detrimental effects to other components.
> **Live verification (2026-08-11, hci0 + DS220 A2DP sink `53:4A:52:FE:01:38`).** With a
> real bonded A2DP transport (`.../dev_53_4A_52_FE_01_38/sep1/fd0`):
> `_resolve_device_path()`, `_device_path()`, and `_collect_media_objects()` all returned
> the live `/org/bluez/hci0/dev_53_4A_52_FE_01_38` (read from `GetManagedObjects()`, not a
> literal); `MATCHES LIVE == True`. The changed caller `_cycle_device_connection()` executed
> a real `Device1.Disconnect()`→`Connect()` on the resolved path with no exception
> (Connected: True→cycle→True). Non-`hci0` branch still deferred to **LT-1/FW6**
> (single-adapter host).
> **Media control-plane live validation (2026-08-11, DS220).** Continuing the same live
> session (no code change): (a) drove a real SBC stream and confirmed BLEEP reads the live
> **`active`** transport via `MediaTransport`/`get_transport_info()` (`_get_transport()`
> path-association picks `sep1/fd0` amid 7 remote SEPs; config `11150235`); (b) exercised
> `MediaControl1` through BLEEP's `MediaControl` wrapper (all passthrough calls returned
> success; `Player=None` as expected for a headphone TG) and an AVRCP absolute-volume
> round-trip via `MediaStreamManager.set_volume()` (84→40→110→84, each confirmed on the
> transport `Volume`). Post-test cleanup verified: transport back to `idle`, volume restored
> to 84, **no lingering BLEEP endpoint**, 7 SEPs intact, bond then removed.
>
> ---
> _Original plan retained below for provenance._
>
> ### HW-1 — original plan — (implemented above)

> **Gap.** `bleep/dbuslayer/media_stream.py:456-459` — `_device_path()` builds
> `f"/org/bluez/hci0/dev_{mac_underscored}"` with a literal `hci0`, ignoring which
> adapter the device is actually under. The sole caller `_cycle_device_connection()`
> (`media_stream.py:461-`) does a full `Device1.Disconnect()` → `Device1.Connect()` on
> that path to force AVDTP re-negotiation. On a multi-adapter host — or if this dongle
> enumerates as `hci1` — it resolves the **wrong** object path: the calls raise
> `org.freedesktop.DBus.Error.UnknownObject` (or act on a non-existent device) and
> A2DP/AVRCP streaming silently fails to recover.
> **Latent today:** `MediaStreamManager.__init__` (`media_stream.py:185-200`) takes only
> `device_mac`, never an adapter; on this single-adapter `hci0` host the bug does not fire.
> **De-dup.** A *specific* instance of the general **FW6** (multi-adapter) item, which does
> not enumerate concrete hardcode sites. Audit surfaced only this one operational builder;
> all other `/org/bluez/hci0` occurrences are `ADAPTER_NAME`-defaulted constructors that
> already accept an override.
>
> **Key insight — the authoritative path already exists.** `_collect_media_objects()`
> (`media_stream.py:206-`) already walks `GetManagedObjects()` and derives the real,
> adapter-correct device path from live BlueZ data
> (`base = path_str.split("/sep")[0].split("/fd")[0]`; matched on `dev_{MAC}`). The fix
> reuses this source of truth instead of reconstructing the path.
>
> **Options.** *(A, chosen)* resolve `_device_path()` from managed objects; fall back to
> the previous string only when the device isn't currently present — reuses existing
> discovery, zero new params, no caller changes. *(B, rejected)* add `adapter=` to
> `__init__` and build `/org/bluez/{adapter}/dev_{mac}` — requires threading an adapter
> arg through every construction site (`modes/audio.py`, `modes/media.py`,
> `ble_ops/audio/*`) and still *assumes* rather than reads reality. More invasive, less
> correct.
>
> **Implementation (Option A).**
> 1. Add a resolver returning the live device path for `self.device_mac` by scanning
>    `GetManagedObjects()` for a `.../dev_{MAC}` base (factor the base-extraction into a
>    tiny shared helper reused by `_collect_media_objects` — DRY).
> 2. Rewrite `_device_path()`: return the resolved path when found; else fall back to the
>    **first enumerated adapter** (`system_dbus__bluez_adapter.list_adapters()[0]["name"]`,
>    `dbuslayer/adapter.py:412-439`) not a literal `hci0`.
> 3. Optionally cache the resolved path on the instance (MAC is fixed for its lifetime).
>
> **Edge cases.** (i) mid-cycle absence — device is connected at call time so resolution
> succeeds; fallback covers the rare not-yet-populated window. (ii) device under a
> non-default adapter — resolution returns the correct one; fallback picks first adapter,
> not `hci0`. (iii) preserve `:`→`_` + `.upper()` MAC normalisation matching
> `_collect_media_objects`.
>
> **Test plan.** Unit (no hardware): managed-objects fixture with device under `hci1` →
> `_device_path()` yields `/org/bluez/hci1/dev_...`; empty managed-objects → fallback uses
> mocked `list_adapters()` first entry, never literal `hci0`; single-adapter `hci0`
> regression unchanged. Live: `audio-play`/`audio-record` A2DP cycle still recovers on the
> current host.
>
> **Acceptance.** No literal `/org/bluez/hci0` in `media_stream.py` operational paths;
> `_cycle_device_connection` operates on the adapter-correct path; new unit tests +
> existing media tests green; lint clean. **Rollback:** single-file, self-contained; no
> schema/API/caller-signature changes.

### HW-2 — Experimental-mode-off silently disables a whole feature class; no consolidated preflight surface — [x] ✅ IMPLEMENTED (2026-09-04)

Landed as **Phase 4d**. `core/preflight.py:_check_experimental_mode` (printed
by `bleep --check-env`) probes `AdvertisementMonitorManager1` and
`Adapter1.ConnectDevice` on the default adapter. Detect-only; the hint names
`bluetoothd -E` / `Experimental=true` and lists remaining experimental
surfaces (device-sets, AdminPolicy, Bearer.LE1/BREDR1, LE-Audio assistant,
obexd BIP). Overlay/listen commands fail closed with that hint when the
iface is missing.

> ---
> _Original plan retained below for provenance._

> **Gap.** With `bluetoothd` started without `-E` and `main.conf Experimental=false`
> (the state on this host — **verified**: `AdvertisementMonitorManager1` returns
> *"No such interface"* on `/org/bluez/hci0`), an entire band of BLEEP features degrade
> or fail with non-obvious errors, independent of the controller:
> - `scan --monitor`, `advertise-monitor` (`dbuslayer/adv_monitor.py`,
>   `modes/monitor.py`, `modes/scan_monitor.py`) — needs `AdvertisementMonitorManager1`.
> - `device-sets` (`dbuslayer/device_set.py`, `modes/device_sets.py`) — `DeviceSet1`.
> - AdminPolicy allow-list (`dbuslayer/adapter.py:694-727`) — `AdminPolicySet1/Status1`.
> - Per-bearer connect `Bearer.LE1`/`Bearer.BREDR1` (`dbuslayer/device_le.py:473-496`,
>   `dbuslayer/device_classic.py:298`).
> - LE-Audio broadcast assistant (`dbuslayer/media_assistant.py`) — also BT 5.2 (see HW-5).
> - OBEX BIP (`dbuslayer/obex_bip.py`) — needs `obexd --experimental`.
> **De-dup.** Prior mentions are scattered and per-feature only (docstrings; the
> `cli_usage.md` AdvertisementMonitor caveat; the OBEX-D2 BIP `--experimental` hint).
> There is **no single preflight/report line** telling the operator "experimental is
> OFF → these N commands will fail here." **Proposed work:** extend
> `core/preflight.py` with an experimental-mode probe (read a known experimental iface
> off the adapter, or parse `main.conf`) and one consolidated summary line + remediation
> hint (`Experimental=true` in `main.conf` or `bluetoothd -E`, then restart). Detect-only;
> no host mutation (consistent with the PAN-preflight policy at `preflight.py:1354`).
>
> **Live confirmation (2026-08-11).** During DS220 A2DP validation, BLEEP endpoint-registration
> mode was run on a host with **three** A2DP endpoint providers active simultaneously —
> `bluealsad -S -p a2dp-source -p a2dp-sink --all-codecs` (systemd, root), `pulseaudio`, and
> `pipewire`. BLEEP's contention pre-flight fired correctly (named `bluealsa`+`pulseaudio`
> competitors), and even with `force_endpoint=True` BlueZ's `a2dp_select_eps` never invoked
> `SetConfiguration()` on the BLEEP endpoint → no BLEEP-owned transport was created (accurate
> "lost the AVDTP race" diagnostic). This validates the contention detection/reporting path and
> reinforces the remediation options already documented (stop the competing daemon, or use
> `--direct` to observe the daemon-owned transport, which BLEEP did successfully). Not a code
> defect — an environment/interop reality this item already tracks.

### HW-3 — Realtek RTL8761B firmware-load / enumeration race breaks preflight shell-outs at attach — [ ] OPEN

> **Gap.** Immediately after plugging in this dongle, within the firmware-load window:
> `bluetoothctl list` **core-dumped**, `hciconfig -a` returned **empty**, and interactive
> `btmgmt info` **hung indefinitely** (had to be killed). All self-healed on retry
> (`bluetoothctl --version` 3/3 OK; `hciconfig hci0` / D-Bus fine; `bluetoothctl mgmt.info`
> reports full settings). Impact on BLEEP: `core/preflight.py:_check_bluez_version()`
> shells to `bluetoothctl --version`, and `dbuslayer/adapter.py:_run_bluetoothctl_mgmt()`
> shells to the `bluetoothctl mgmt` submenu — if invoked during that window they can
> crash/hang the run. **De-dup.** No existing item covers a controller-init race; LTR-8/9
> were orphaned-registration bugs, not firmware timing. **Proposed work:** an adapter
> **readiness gate** (poll `Adapter1` present + `Powered` true, or `/sys/class/bluetooth/
> hciX` + `UP RUNNING`, with a short bounded retry) before the first `bluetoothctl`/mgmt
> shell-out; already-existing `power_cycle()`/`recovery.py` can be the escalation path.

### HW-4 — Preflight `btmgmt` presence tick is misleading on this host — [x] ✅ IMPLEMENTED (2026-08-11)

> **Gap.** `core/preflight.py:185` reported `btmgmt` as available via `shutil.which()`,
> but BLEEP never invokes `btmgmt` (all kernel-mgmt goes through the `bluetoothctl mgmt`
> submenu), and on this host `btmgmt` **hangs**. The green tick implied a working
> capability that is both unused and locally broken.
>
> **Root cause (empirically established, `btmgmt` 5.86 on this host).** Two independent
> footguns: (1) `btmgmt` drops into an **interactive REPL** unless a command completes, so
> it blocks reading stdin — even `btmgmt -h` hangs after printing help; (2) any subcommand
> touching the kernel mgmt socket needs **CAP_NET_ADMIN** and blocks *before* its own
> `--timeout` applies. Probe matrix:
> - `btmgmt info` (unprivileged) → **hangs** (rc 124, killed at 6 s)
> - `btmgmt --index 0 info` (unprivileged) → **hangs** (rc 124)
> - `btmgmt --timeout 2 --index 0 info` (unprivileged) → **still hangs** (socket open
>   blocks before `--timeout` takes effect)
> - `btmgmt -h` → prints help then **drops into REPL** (hangs on stdin)
> - `btmgmt --version` → **rc 0, ~instant** (socket-free, safe)
> - `sudo btmgmt info` → works (needs a password here; passwordless sudo unavailable)
>
> **Design (as-built).** Two functions + a dataclass in `core/preflight.py`:
> - `run_btmgmt(args, *, timeout=3.0)` — safe invocation primitive: always
>   `stdin=subprocess.DEVNULL` (REPL sees EOF) + prepends `--timeout` (non-interactive
>   mode) + wraps in a hard `subprocess.run(..., timeout=timeout+2)` backstop. Returns
>   `None` on absence/timeout/error — never raises, never hangs.
> - `check_btmgmt(adapter_index=0) -> BtmgmtStatus` — presence (`shutil.which`) → runnable
>   (socket-free `btmgmt --version`, instant, yields version) → controller query **only
>   when `os.geteuid()==0`** (unprivileged it would block, so deliberately skipped with a
>   `needs_privilege` verdict + remediation; when root, routed through `run_btmgmt`).
> - `BtmgmtStatus` dataclass: `present`, `version`, `runnable`,
>   `controller_query ∈ {ok, needs_privilege, unavailable, skipped}`, `detail`.
>
> **Wiring.** `PreflightReport` gained a `btmgmt: Optional[BtmgmtStatus]` field;
> `run_preflight_checks()` populates it and **overrides** `bluetooth_tools["btmgmt"]` to
> reflect *runnability* (not bare presence); `print_preflight_summary()` renders a
> `↳ btmgmt vX.Y: …` detail line with the controller-query verdict and, for
> `needs_privilege`, that root is required and that **BLEEP does not use `btmgmt`**
> (informational only).
>
> **Behaviour matrix (verified):** absent → `F/F/skipped` ("not installed"); unprivileged
> (this host) → `T/T(5.86)/needs_privilege`; `--version` hangs → `T/F/skipped` ("present
> but not runnable"); root+adapter → `T/T/ok`; root+no data → `T/T/unavailable`.
>
> **Tests.** `tests/test_preflight.py` `TestRunBtmgmt` (absence→None; invocation carries
> `--timeout`+`stdin=DEVNULL`+`timeout+2` backstop; `TimeoutExpired`→None) + `TestCheckBtmgmt`
> (absent; **unprivileged makes ONLY the `--version` call**, `call_count==1`, never the
> blocking `info`; `--version` hang→not runnable; root→ok; root+empty→unavailable). Suite
> **50 passed** (was 42), 0 lint. Live: `check_btmgmt()` returns in ~0 s
> (`present/runnable=True, version=5.86, controller_query=needs_privilege`).
>
> **Manual verify.** (1) unprivileged preflight summary shows `✓ btmgmt` + the `↳`
> caveat line and returns promptly (no stall); (2) timing guard —
> `python -c "import time;from bleep.core.preflight import check_btmgmt as c;t=time.monotonic();c();print(time.monotonic()-t)"`
> sub-second; (3) privileged (optional) `sudo -E … check_btmgmt()` → `controller_query='ok'`.
> **Non-goal:** BLEEP keeps using the `bluetoothctl mgmt` submenu
> (`dbuslayer/adapter.py:564-608`); `run_btmgmt` is available should a future root-gated
> `btmgmt` path ever be wanted.
> (`bleep/core/preflight.py`, `tests/test_preflight.py`)

### HW-5 — BT 5.1 controller permanently caps the LE-Audio / ISO roadmap — [ ] OPEN (known hardware limit)

> **Gap / limit.** This antenna is **HCI/LMP 5.1** → **no ISO/CIS/BIS**, so LE Audio /
> Auracast / broadcast-assistant / LC3-over-ISO can never function on it. The dormant
> wrappers and constants (`dbuslayer/media_assistant.py`, `LC3_CODEC_ID` in
> `bt_ref/constants.py`, the `version.py` BT-5.2 feature-inference rows) are safe today —
> **no active runtime path calls them**, so nothing breaks — but any future LE-Audio work
> requires a **BT 5.2+ controller**. **De-dup.** The feature-inference table exists but
> nothing records the *local* hardware ceiling. Filed as a known-limit marker so LE-Audio
> tasks are not planned against this hardware. Classic audio (A2DP/HFP/HSP/AVRCP incl.
> **WBS/mSBC**) is fully supported by this chip and is unaffected.

---

# Resources and Notes:
        - Great way to obfusate use of the D-Bus:
                progname = 'org.freedesktop.NetworkManager'
                objpath  = '/org/freedesktop/NetworkManager'
                intfname = 'org.freedesktop.NetworkManager'
                methname = 'GetDevices'
                
                bus = dbus.SystemBus()
                
                obj = bus.get_object(progname, objpath)
                interface = dbus.Interface(obj, intfname)     # Get the interface to obj
                method = interface.get_dbus_method(methname)  # The method on that interface
                
                method()                                      # And finally calling the method
            - URL:      https://unix.stackexchange.com/questions/203410/how-to-list-all-object-paths-under-a-dbus-service
        - Larger Bluetooth Classic D-Bus information:
            - URL:      https://kernel.googlesource.com/pub/scm/bluetooth/bluez/+/utils-3.2/hcid/dbus-api.txt
        - Understanding D-Bus Signatures
            - URL:      https://dbus.freedesktop.org/doc/dbus-python/tutorial.html
            - URL:      https://dbus.freedesktop.org/doc/dbus-specification.html#type-system
        - Hex Encoding
            - URL:      linuxhint.com/string-to-hexadecimal-in-python/
        - CLI Busctl
            - URL:      www.freedesktop.org/software/systemd/man/busctl.html        <----- Good for understanding how to send raw information to D-Bus via busctl CLI
        - API Documentaiton for Bluez
            - URL:      https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/test/test-adapter           <-------- CENTRAL to getting DBus + Bluez interaction working
            - URL:      https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc
        - DBus Proxy Documentation
            - URL:      https://lazka.github.io/pgi-docs/Gio-2.0/classes/DBusProxy.html#Gio.DBusProxy.signals.g_properties_changed
        - dbus-python Documentation
            - URL:      https://dbus.freedesktop.org/doc/dbus-python/dbus.proxies.html

    Nota Bene:
        - Bluetooth Low Energy GATT Descriptors will ONLY UPDATE AFTER that descriptor has been READ AT LEAST ONCE before

