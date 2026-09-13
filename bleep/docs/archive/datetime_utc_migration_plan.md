# DT-1 — `datetime.utcnow()` Deprecation Migration: Plan of Work

> **Status:** ✅ IMPLEMENTED (2026-07-28). Tracked as **DT-1** in
> `todo_tracker.md` (see that entry for execution results). This document is the
> original plan + proof-of-concept + citations, retained for provenance. The
> `utc_now()` / `utc_now_iso()` helpers now live in `bleep/core/time_utils.py`
> and are the canonical timestamp source across the codebase; all 28 `utcnow()`
> sites were migrated, the full suite is green, and the naive-UTC format was
> live-verified against a temp DB.

## 1. Problem

`datetime.datetime.utcnow()` is **deprecated as of Python 3.12** and scheduled for
removal. The runtime emits:

```
DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for
removal in a future version. Use timezone-aware objects to represent datetimes
in UTC: datetime.datetime.now(datetime.UTC).
```

BLEEP uses it at **29 call sites across 13 files** (enumerated in §6). The naive
"obvious" fix suggested by the warning — `datetime.now(timezone.utc)` — returns a
**timezone-aware** object whose `.isoformat()` appends a `+00:00` offset. That is
**not a drop-in replacement** for BLEEP because the observation DB stores and
compares timestamps as **naive-UTC ISO strings** (see convention in
`observation_db_schema.md`). Changing the string shape — or, worse, applying it to
only some sites — corrupts ordering/recency logic.

## 2. Constraint: preserve the naive-UTC string format

Three consumers rely on the current naive-UTC string shape
(`YYYY-MM-DDTHH:MM:SS.ffffff`, **no** offset):

- **SQLite recency filter** — `bleep/core/observations/_devices.py:203`:
  ```python
  status_filters.append("last_seen > datetime('now', '-1 day')")
  ```
  `datetime('now')` returns a **naive** UTC string.
- **Python string-sorted aggregation** — `bleep/core/observations/_uuids.py:123-126`:
  ```python
  if entry["first_seen"] is None or ts < entry["first_seen"]:
      entry["first_seen"] = ts
  if entry["last_seen"] is None or ts > entry["last_seen"]:
      entry["last_seen"] = ts
  ```
  These are **string** comparisons over stored timestamps.
- **`fromisoformat` reader** — `bleep/modes/survey.py:481-490` parses stored
  timestamps back to epoch for `--from-db` seeding.

## 3. Proof of Concept (executed 2026-07-27, Python 3.13)

Run standalone (no BLEEP import; `sqlite3` + `datetime` only).

### PoC-A — the safe replacement is byte-shape identical to legacy

```python
from datetime import datetime, timezone
legacy = datetime.utcnow().isoformat()                                   # deprecated
safe   = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()     # proposed
aware  = datetime.now(timezone.utc).isoformat()                          # WRONG (adds offset)
```
```
legacy      : 2026-07-28T00:18:42.847326
safe (naive): 2026-07-28T00:18:42.847341     # same shape (no offset)
aware (BAD) : 2026-07-28T00:18:42.847347+00:00
legacy shape == safe shape : True
aware has offset suffix    : True
```

### PoC-B — mixing naive + aware breaks datetime arithmetic (definitive)

```python
d1 = datetime.fromisoformat("2026-07-28T00:00:00.100000")          # existing naive row
d2 = datetime.fromisoformat("2026-07-28T00:00:00.100001+00:00")    # new aware row
d2 - d1
# TypeError: can't subtract offset-naive and offset-aware datetimes
```
Any reader that does arithmetic across rows written before/after a *partial* or
*aware* migration will raise. This is the decisive reason the migration must be
**atomic** and **format-preserving**.

### PoC-C — same-instant sort skew

A naive string is a strict prefix of the aware string for the same instant, so the
aware value sorts **after** an equal naive value (`"...100000" < "...100000+00:00"`).
Mixed columns therefore lose a stable total order (affects `_uuids.py` and any
`MIN()/MAX()` over a mixed column).

### PoC-D — recency filter is *not* the main risk

Both naive and aware "recent" rows still pass `last_seen > datetime('now','-1 day')`
because the differing **date prefix** dominates and `'T'(0x54) > ' '(0x20)`. So the
observable LT-2-style symptom (recency/ordering) is subtle; the hard failure is
PoC-B. Conclusion: **do not rely** on prefix dominance — standardize the format.

## 4. Design

Add one central helper module and route **every** site through it.

**New file `bleep/core/time_utils.py`:**
```python
"""Central UTC time helpers (DT-1).

`datetime.utcnow()` is deprecated (Python 3.12+). These helpers replace it while
preserving BLEEP's on-disk timestamp convention: naive-UTC ISO 8601 strings with
no offset suffix (see docs/observation_db_schema.md).
"""
from __future__ import annotations
from datetime import datetime, timezone

def utc_now() -> datetime:
    """Timezone-aware current instant in UTC (use for arithmetic/durations)."""
    return datetime.now(timezone.utc)

def utc_now_iso() -> str:
    """Naive-UTC ISO 8601 string (no offset) — the DB timestamp convention.

    Byte-shape identical to the legacy ``datetime.utcnow().isoformat()`` (PoC-A),
    so it is a drop-in replacement that never changes stored/compared strings.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
```

**Replacement rules:**
| Legacy pattern | Replacement |
|----------------|-------------|
| `datetime.utcnow().isoformat()` (25 sites, DB strings) | `utc_now_iso()` |
| `datetime.utcnow()` bare object (4 sites, `_maintenance.py` duration math) | `utc_now()` |

For `_maintenance.py`, both `start_time` and `end_time` become aware (`utc_now()`),
so `end_time - start_time` stays valid; no timestamp is persisted as a string there,
so the aware object is safe.

## 5. Migration steps (atomic, phased within one change set)

1. **Add `bleep/core/time_utils.py`** with the two helpers above.
2. **Add `tests/test_time_utils.py`**:
   - `utc_now_iso()` has no offset suffix and matches the regex
     `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$`.
   - `utc_now_iso()` shape equals a frozen legacy `utcnow().isoformat()` shape.
   - `datetime.fromisoformat(utc_now_iso())` is naive (`tzinfo is None`).
   - `utc_now()` is aware and within a few seconds of `utc_now_iso()`.
3. **Replace the 25 string sites** (§6 list) with `utc_now_iso()`; **replace the 4
   object sites** in `_maintenance.py` with `utc_now()`. Update imports; remove now-
   unused `from datetime import datetime` where nothing else needs it.
4. **Regression gate:** full `tests/` suite green + lint-clean. Add an assertion in
   an existing observations test that a freshly written `last_seen` has **no**
   offset suffix (guards against future aware regressions).
5. **Grep gate:** `rg 'utcnow\(' bleep/` returns **zero** hits; `rg 'datetime\.now\(\)' bleep/`
   returns only display/report/filename sites (local time is acceptable there).
6. **Docs:** flip DT-1 to ✅ in `todo_tracker.md`; add a changelog entry; the
   `observation_db_schema.md` convention note already references the naive-UTC
   helper.

## 6. Exact site inventory (29)

**String sites → `utc_now_iso()` (25):**
- `bleep/dbuslayer/device_classic.py:611`
- `bleep/modes/classic_enum.py:61`
- `bleep/ble_ops/le/scan.py:640`
- `bleep/analysis/aoi_analyser.py:635`
- `bleep/core/observations/_connection.py:904,921`
- `bleep/core/observations/_services.py:62,63,143,204,228,352,455,476`
- `bleep/core/observations/_history.py:52,85`
- `bleep/core/observations/_aoi.py:50`
- `bleep/core/observations/_devices.py:39`
- `bleep/core/observations/_evidence.py:45,133`
- `bleep/core/observations/_pairing.py:50`
- `bleep/core/observations/_media.py:33,66,103,177`

**Object sites → `utc_now()` (4):**
- `bleep/core/observations/_maintenance.py:37,39,49,51`

> Line numbers are as of 2026-07-27; re-grep `utcnow(` before editing.

## 7. Risk analysis & mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Introducing offset suffix into DB strings | High if `datetime.now(timezone.utc).isoformat()` used naively | Helper strips tzinfo (PoC-A); grep gate forbids raw `.now(timezone.utc).isoformat()` into DB |
| Partial migration → mixed naive/aware columns | Medium | Single atomic change set; grep gate ensures zero `utcnow(` remain |
| `_maintenance` arithmetic break | Low | Both endpoints use `utc_now()` (aware); values not persisted as strings |
| Behavioural drift vs stored history | None | Format is byte-identical (PoC-A); existing rows compare correctly with new writes |
| Reader `fromisoformat` mixing | Low | Format unchanged → all rows remain naive → no naive/aware arithmetic (PoC-B avoided) |

## 8. Rollback

Single change set; revert is `git revert`. Because the output format is unchanged,
no data migration or backfill is required in either direction.

## 9. Citations

- CPython deprecation: `datetime.utcnow()` deprecated in 3.12, recommends
  `datetime.now(datetime.UTC)` — surfaced by the runtime `DeprecationWarning`
  (see §1) and CPython gh-103857 / "What's New In Python 3.12".
- BLEEP naive-UTC convention: `bleep/docs/observation_db_schema.md` (DATETIME note).
- Consumers requiring naive format: `_devices.py:203`, `_uuids.py:123-126`,
  `survey.py:481-490`.
- Prior regression motivating the convention: LT-2 (`todo_tracker.md`,
  `changelog.md`, 2026-07-27).

*Last updated: 2026-07-27*
