#!/usr/bin/python3
"""Vendor/community advertisement-spec updater for the BLEEP code-base.

Usage (CLI)::

    python -m bleep.bt_ref.update_vendor_specs                 # pull from GitHub
    python -m bleep.bt_ref.update_vendor_specs --local-path P  # bootstrap from a checkout

This mirrors ``bt_ref/update_ble_uuids.py`` (the BT SIG updater) but sources
*vendor/community* advertisement fingerprints from the public **device-library**
project (manifest-based registry).  The compiled tables are written to
``bleep/bt_ref/vendor_adv_specs.py`` *inside the package* so BLEEP owns and
maintains its reference material with no external/runtime dependency.

Source precedence:
    1. ``--local-path <dir>``  – walk a local device-library checkout (dev-only
       bootstrap; ``workDir/`` is not a runtime dependency).
    2. Public GitHub repo      – enumerate ``manifest.json`` via the git-tree API
       and fetch each blob from ``raw.githubusercontent.com``.
    3. Local cache             – ``bt_ref/vendor_specs_cache.json`` from a prior run.

Networking errors never raise: on total failure the previously generated
``vendor_adv_specs.py`` is left untouched.
"""
from __future__ import annotations

import argparse
import json
import pprint
import urllib.request as _url
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Source configuration
# ---------------------------------------------------------------------------

_REPO = "BLESPloit/device-library"
_BRANCH = "main"
_TREE_API = f"https://api.github.com/repos/{_REPO}/git/trees/{_BRANCH}?recursive=1"
_RAW_ROOT = f"https://raw.githubusercontent.com/{_REPO}/{_BRANCH}/"

_OUT_PATH = Path(__file__).with_name("vendor_adv_specs.py")
_CACHE_PATH = Path(__file__).with_name("vendor_specs_cache.json")

_HEADER = (
    "#!/usr/bin/python3\n\n"
    "# Auto-generated vendor/community advertisement specs (device-library).\n"
    "# DO NOT EDIT - run `python -m bleep.bt_ref.update_vendor_specs` instead.\n"
    "# Generated: {timestamp}\n"
    "# Source: {source}\n"
    "# Spec count: {count}\n\n"
)


def _download(url: str, timeout: int = 20) -> Optional[str]:
    """Return decoded body of *url* or ``None`` on any failure."""
    try:
        req = _url.Request(url, headers={"User-Agent": "bleep-vendor-spec-updater"})
        with _url.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - network is best-effort
        print(f"[!] Failed to download {url}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Manifest gathering
# ---------------------------------------------------------------------------

def _gather_local(root: Path) -> List[Dict[str, Any]]:
    """Load every ``manifest.json`` under *root* (device-library checkout)."""
    manifests: List[Dict[str, Any]] = []
    for path in sorted(root.rglob("manifest.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"[!] Skipping unreadable manifest {path}: {exc}")
            continue
        manifests.append({"path": str(path.relative_to(root)), "manifest": data})
    print(f"[+] Loaded {len(manifests)} manifest(s) from local checkout {root}")
    return manifests


def _gather_github() -> List[Dict[str, Any]]:
    """Enumerate and fetch every ``manifest.json`` from the public repo."""
    tree_raw = _download(_TREE_API)
    if not tree_raw:
        return []
    try:
        tree = json.loads(tree_raw).get("tree", [])
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Could not parse git-tree response: {exc}")
        return []

    paths = [
        node["path"]
        for node in tree
        if node.get("type") == "blob" and node.get("path", "").endswith("manifest.json")
    ]
    print(f"[*] Found {len(paths)} manifest path(s) via GitHub tree API")

    manifests: List[Dict[str, Any]] = []
    for rel in sorted(paths):
        body = _download(_RAW_ROOT + rel)
        if body is None:
            continue
        try:
            manifests.append({"path": rel, "manifest": json.loads(body)})
        except Exception as exc:  # noqa: BLE001
            print(f"[!] Skipping unparsable manifest {rel}: {exc}")
    print(f"[+] Fetched {len(manifests)} manifest(s) from GitHub")
    return manifests


def _gather_cache() -> List[Dict[str, Any]]:
    if not _CACHE_PATH.exists():
        print("[!] No local vendor-spec cache available")
        return []
    try:
        manifests = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        print(f"[+] Loaded {len(manifests)} manifest(s) from cache {_CACHE_PATH}")
        return manifests
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Failed to read cache: {exc}")
        return []


# ---------------------------------------------------------------------------
# Normalisation + compilation
# ---------------------------------------------------------------------------

def _walk_conditions(cond: Any) -> Iterable[Dict[str, Any]]:
    """Yield leaf condition dicts, flattening ``one_of`` / ``all_of`` groups."""
    if not isinstance(cond, dict):
        return
    grouped = False
    for group_key in ("one_of", "all_of", "any_of"):
        if group_key in cond and isinstance(cond[group_key], list):
            grouped = True
            for sub in cond[group_key]:
                yield from _walk_conditions(sub)
    if not grouped:
        yield cond


def _norm_uuid16(value: str) -> str:
    return str(value).strip().lower().zfill(4)


def _norm_company(value: str) -> str:
    """Normalise a company id ("004C" / "0x004c" / 76) to 4-hex lower-case."""
    s = str(value).strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    try:
        return f"{int(s, 16):04x}"
    except ValueError:
        return s.zfill(4)


def _normalise(manifests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract a lossless, stable spec record from each manifest observer role."""
    specs: List[Dict[str, Any]] = []
    for item in manifests:
        manifest = item.get("manifest", {})
        observer = (manifest.get("roles", {}) or {}).get("observer", {}) or {}
        conditions = observer.get("scan_conditions")
        if not conditions:
            continue
        specs.append(
            {
                "name": manifest.get("name") or item.get("path", "unknown"),
                "path": item.get("path", ""),
                "priority": observer.get("priority"),
                "conditions": conditions,
            }
        )
    specs.sort(key=lambda s: (s["priority"] if s["priority"] is not None else 999, s["name"]))
    return specs


def _compile(specs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build attribution tables from normalised specs."""
    service_data_16: Dict[str, str] = {}
    service_16: Dict[str, str] = {}
    service_128: Dict[str, str] = {}
    company: Dict[str, List[str]] = {}
    mfg_prefix: List[Dict[str, Any]] = []

    def _put(table: Dict[str, str], key: str, name: str) -> None:
        table.setdefault(key, name)  # first (highest-priority) spec wins

    for spec in specs:
        name = spec["name"]
        for leaf in _walk_conditions(spec["conditions"]):
            for val in _as_list(leaf.get("service_data_uuid_16")):
                _put(service_data_16, _norm_uuid16(val), name)
            for val in _as_list(leaf.get("service_uuid_16")):
                _put(service_16, _norm_uuid16(val), name)
            for val in _as_list(leaf.get("service_uuid_128")):
                _put(service_128, str(val).strip().lower(), name)
            cid = leaf.get("company_id")
            if cid is not None:
                key = _norm_company(cid)
                company.setdefault(key, [])
                if name not in company[key]:
                    company[key].append(name)
                prefix = leaf.get("manufacturer_data_prefix_hex")
                if prefix:
                    mfg_prefix.append(
                        {
                            "company_id": key,
                            "prefix": str(prefix).strip().lower(),
                            "name": name,
                            "priority": spec["priority"],
                        }
                    )

    mfg_prefix.sort(key=lambda e: (e["priority"] if e["priority"] is not None else 999, e["name"]))
    return {
        "SERVICE_DATA_UUID16": dict(sorted(service_data_16.items())),
        "SERVICE_UUID16": dict(sorted(service_16.items())),
        "SERVICE_UUID128": dict(sorted(service_128.items())),
        "COMPANY_ID": {k: company[k] for k in sorted(company)},
        "MANUFACTURER_PREFIX": mfg_prefix,
        "SPECS": specs,
    }


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------

def _emit(tables: Dict[str, Any], source: str) -> str:
    body = [
        _HEADER.format(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            source=source,
            count=len(tables["SPECS"]),
        )
    ]
    for var in ("SERVICE_DATA_UUID16", "SERVICE_UUID16", "SERVICE_UUID128",
                "COMPANY_ID", "MANUFACTURER_PREFIX", "SPECS"):
        # Emit as Python literals (json.dumps would produce true/false/null,
        # which are invalid Python and would break the import).
        body.append(f"{var} = " + pprint.pformat(tables[var], indent=4, width=100, sort_dicts=False))
        body.append("")
    return "\n".join(body)


def regenerate(local_path: Optional[str] = None) -> None:
    """Gather manifests (local → GitHub → cache), compile, and write the module."""
    manifests: List[Dict[str, Any]] = []
    source = "unknown"

    if local_path:
        root = Path(local_path).expanduser().resolve()
        if root.is_dir():
            manifests = _gather_local(root)
            # Record provenance without leaking an absolute dev-machine path
            # into the committed artifact.
            source = f"local:{root.name}"
        else:
            print(f"[!] --local-path {root} is not a directory")

    if not manifests:
        manifests = _gather_github()
        if manifests:
            source = f"github:{_REPO}@{_BRANCH}"

    if not manifests:
        manifests = _gather_cache()
        if manifests:
            source = f"cache:{_CACHE_PATH.name}"

    if not manifests:
        print("[!] No manifests from any source; leaving vendor_adv_specs.py untouched")
        return

    # Cache the raw manifests for offline regeneration.
    try:
        _CACHE_PATH.write_text(json.dumps(manifests, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[+] Cached {len(manifests)} manifest(s) to {_CACHE_PATH}")
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Failed to write cache: {exc}")

    tables = _compile(_normalise(manifests))
    _OUT_PATH.write_text(_emit(tables, source), encoding="utf-8")
    print(
        f"[+] Regenerated {_OUT_PATH.name}: {len(tables['SPECS'])} specs, "
        f"{len(tables['SERVICE_DATA_UUID16'])} service-data UUIDs, "
        f"{len(tables['COMPANY_ID'])} company ids, "
        f"{len(tables['MANUFACTURER_PREFIX'])} mfg prefixes"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate vendor_adv_specs.py")
    parser.add_argument(
        "--local-path",
        help="Path to a local device-library checkout (dev bootstrap only)",
    )
    args = parser.parse_args()
    regenerate(local_path=args.local_path)


if __name__ == "__main__":
    main()
