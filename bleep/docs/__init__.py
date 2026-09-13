from __future__ import annotations
"""BLEEP in-package documentation helper.

This sub-package exposes the markdown guides located alongside the code so they
are reachable from the Python REPL / `pydoc` without having to open the files
manually.

Example usage
-------------
>>> import bleep.docs as docs
>>> help(docs)                 # shows the README.md content
>>> print(docs.get('cli_usage'))

You may also run ``python -m pydoc bleep.docs.cli_usage`` thanks to the dynamic
module loader below.
"""

from importlib import resources as _res
import importlib
import importlib.abc  # ensure .abc submodule is loaded for Loader/MetaPathFinder
import importlib.machinery  # ensure ModuleSpec is available
from typing import Dict

# Mapping logical names ↔ markdown filenames (extend if new guides are added).
# Keep this in sync with the files in this directory; archived/historical
# documents live under ``archive/`` and are referenced with that path prefix.
_DOCS: Dict[str, str] = {
    'README': 'README.md',
    # --- CLI & modes ---
    'cli_usage': 'cli_usage.md',
    'debug_mode': 'debug_mode.md',
    'debug_mode_db': 'debug_mode_db.md',
    'ble_scan_modes': 'ble_scan_modes.md',
    'ble_ctf_mode': 'ble_ctf_mode.md',
    'bl_classic_mode': 'bl_classic_mode.md',
    'map_bmessage_format': 'map_bmessage_format.md',
    'map_version_compatibility': 'map_version_compatibility.md',
    'gatt_enumeration': 'gatt_enumeration.md',
    'media_mode': 'media_mode.md',
    'audio_recon': 'audio_recon.md',
    'user_mode': 'user_mode.md',
    'explore_mode': 'explore_mode.md',
    'analysis_mode': 'analysis_mode.md',
    'agent_mode': 'agent_mode.md',
    'pairing_agent': 'pairing_agent.md',
    'signal_capture': 'signal_capture.md',
    'adv_monitor': 'adv_monitor.md',
    'le_advertising': 'le_advertising.md',
    'survey_mode': 'survey_mode.md',
    'beacon_identification': 'beacon_identification.md',
    'adapter_config': 'adapter_config.md',
    # --- Data & security ---
    'observation_db': 'observation_db.md',
    'observation_db_usage_scenarios': 'observation_db_usage_scenarios.md',
    'observation_db_schema': 'observation_db_schema.md',
    'aoi_mode': 'aoi_mode.md',
    'aoi_implementation': 'aoi_implementation.md',
    'aoi_security_algorithms': 'aoi_security_algorithms.md',
    'aoi_customization_guide': 'aoi_customization_guide.md',
    'aoi_testing': 'aoi_testing.md',
    # --- Architecture & reference ---
    'api_specification': 'api_specification.md',
    'bluez_interface_properties': 'bluez_interface_properties.md',
    'device_type_classification': 'device_type_classification.md',
    'adv_dissection': 'adv_dissection.md',
    'uuid_translation': 'uuid_translation.md',
    'modalias_handling': 'modalias_handling.md',
    'network_capability_summary': 'network_capability_summary.md',
    'pan_connection_analysis': 'pan_connection_analysis.md',
    'unified_dbus_event_aggregator': 'unified_dbus_event_aggregator.md',
    'd_bus_reliability': 'd-bus-reliability.md',
    'dbus_documentation_index': 'dbus_documentation_index.md',
    'dbus_best_practices': 'dbus_best_practices.md',
    'dbus_debugging_methods': 'dbus_debugging_methods.md',
    'mainloop_architecture': 'mainloop_architecture.md',
    'agent_documentation_index': 'agent_documentation_index.md',
    'agent_pairing_flow_analysis': 'agent_pairing_flow_analysis.md',
    # --- Project tracking ---
    'changelog': 'changelog.md',
    'todo_tracker': 'todo_tracker.md',
    # --- Archived: historical investigations & completed plans (docs/archive/) ---
    'archive_index': 'archive/README.md',
    'mainloop_requirement_analysis': 'archive/mainloop_requirement_analysis.md',
    'real_issue_investigation': 'archive/real_issue_investigation.md',
    'method_invocation_investigation': 'archive/method_invocation_investigation.md',
    'accessdenied_error_analysis': 'archive/accessdenied_error_analysis.md',
    'introspection_test_analysis': 'archive/introspection_test_analysis.md',
    'terminal_error_analysis': 'archive/terminal_error_analysis.md',
    'agent_dbus_communication_issue': 'archive/agent_dbus_communication_issue.md',
    'agent_method_registration_investigation': 'archive/agent_method_registration_investigation.md',
    'agent_registration_diagnosis': 'archive/agent_registration_diagnosis.md',
    'bluez_reference_analysis_refined': 'archive/bluez_reference_analysis_refined.md',
    'bluez_tools_comparison_analysis': 'archive/bluez_tools_comparison_analysis.md',
    'pincode_tracking_verification': 'archive/pincode_tracking_verification.md',
    'uuid_translation_plan': 'archive/uuid_translation_plan.md',
    'network_capability_plan': 'archive/network_capability_plan.md',
    'datetime_utc_migration_plan': 'archive/datetime_utc_migration_plan.md',
    'aoi_changes_summary': 'archive/aoi_changes_summary.md',
}


def _read_md(filename: str) -> str:
    """Return the raw markdown text bundled with this package."""
    with _res.files(__name__).joinpath(filename).open('r', encoding='utf-8') as f:
        return f.read()

# Populate package docstring from main README
__doc__ = _read_md(_DOCS['README'])


def get(name: str) -> str:
    """Return markdown text for *name* (e.g. ``'cli_usage'``)."""
    try:
        return _read_md(_DOCS[name])
    except KeyError as exc:
        raise ValueError(f"Unknown doc: {name!r}. Available: {list(_DOCS)}") from exc


# --- Dynamic sub-module loader -------------------------------------------------
# Allow ``import bleep.docs.<name>`` where <name> maps to a markdown file. This
# creates lightweight modules whose __doc__ is the markdown content so pydoc
# renders it nicely.

class _MarkdownLoader(importlib.abc.Loader):
    def __init__(self, name: str, md_file: str) -> None:
        self._fullname = name
        self._md_file = md_file

    def create_module(self, spec):  # noqa: D401 – required importlib API
        return None  # use default module creation semantics

    def exec_module(self, module):
        module.__doc__ = _read_md(self._md_file)


class _MarkdownFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):  # noqa: D401
        pkg_prefix = __name__ + '.'
        if not fullname.startswith(pkg_prefix):
            return None
        short_name = fullname[len(pkg_prefix):]
        if short_name in _DOCS and short_name != 'README':
            return importlib.machinery.ModuleSpec(
                fullname,
                _MarkdownLoader(fullname, _DOCS[short_name]),
                is_package=False,
            )
        return None


import sys as _sys
if _MarkdownFinder not in [type(f) for f in _sys.meta_path]:
    _sys.meta_path.insert(0, _MarkdownFinder()) 