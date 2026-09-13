# BLEEP Documentation Archive

This folder holds **historical** documents — point-in-time investigations,
resolved bug analyses, and completed implementation/migration plans. They are
retained verbatim for provenance and education, but their bodies are **not**
current guidance. Each file carries an archival banner at the top.

The **key takeaway** of every archived document is captured below and folded
into the canonical, actively-maintained docs, so no critical information is lost
by archiving.

## Agent / pairing / MainLoop investigations

The whole cluster below converged on one root cause and fix: **`org.bluez.Agent1`
methods are only dispatched while a GLib MainLoop is running.** Once the loop was
run during pairing (v2.6.2), pairing worked end-to-end. The canonical record is
[../agent_pairing_flow_analysis.md](../agent_pairing_flow_analysis.md) (with
[../mainloop_architecture.md](../mainloop_architecture.md)).

| Archived doc | Key takeaway |
|--------------|--------------|
| [mainloop_requirement_analysis.md](mainloop_requirement_analysis.md) | Identified the real fix — the MainLoop must be running for Agent1 dispatch. |
| [real_issue_investigation.md](real_issue_investigation.md) | "Methods registered but not invoked" — the pre-fix broken state; resolved in v2.6.2. |
| [method_invocation_investigation.md](method_invocation_investigation.md) | Same pre-fix symptom; superseded by the MainLoop fix. |
| [accessdenied_error_analysis.md](accessdenied_error_analysis.md) | `AccessDenied` on **self-introspection** of the agent path is expected/harmless. |
| [introspection_test_analysis.md](introspection_test_analysis.md) | The manual `get_object('/test/agent')` introspection test was itself incorrect. |
| [terminal_error_analysis.md](terminal_error_analysis.md) | The logged errors during pairing were benign; introspection `AccessDenied` is expected. |
| [agent_dbus_communication_issue.md](agent_dbus_communication_issue.md) | Consolidated analysis; the "methods not registered" premise was a misdiagnosis. |
| [agent_method_registration_investigation.md](agent_method_registration_investigation.md) | Empty introspection XML never proved non-registration; caution was correct. |
| [agent_registration_diagnosis.md](agent_registration_diagnosis.md) | Registration-failure conclusion was superseded by the MainLoop finding. |
| [bluez_reference_analysis_refined.md](bluez_reference_analysis_refined.md) | BlueZ reference-script comparison; premise superseded. |
| [bluez_tools_comparison_analysis.md](bluez_tools_comparison_analysis.md) | bluez-tools vs BLEEP agent comparison; "key finding" superseded. |
| [pincode_tracking_verification.md](pincode_tracking_verification.md) | PIN-request tracking guide; its unified-monitoring prerequisite is outdated (that filter blocks Agent1 dispatch). Current behaviour: [../pairing_agent.md](../pairing_agent.md). |

## Completed implementation / migration plans

| Archived doc | Status → canonical doc |
|--------------|------------------------|
| [uuid_translation_plan.md](uuid_translation_plan.md) | Implemented → [../uuid_translation.md](../uuid_translation.md). |
| [network_capability_plan.md](network_capability_plan.md) | Superseded by shipped API → [../network_capability_summary.md](../network_capability_summary.md), [../pan_connection_analysis.md](../pan_connection_analysis.md). |
| [datetime_utc_migration_plan.md](datetime_utc_migration_plan.md) | Implemented (DT-1) → `bleep/core/time_utils.py` (`utc_now()`/`utc_now_iso()`); zero `datetime.utcnow()` call sites remain. |
| [aoi_changes_summary.md](aoi_changes_summary.md) | One-off v2.2.2 summary → [../changelog.md](../changelog.md), [../aoi_implementation.md](../aoi_implementation.md). |
| [beacon_identification_plan.md](beacon_identification_plan.md) | Implemented (S1/S2/S3/S7 shipped; S10 open) → [../beacon_identification.md](../beacon_identification.md), [../adv_dissection.md](../adv_dissection.md). In-package copy of the former repo-root `BEACON_IDENTIFICATION_PLAN.md`. |
