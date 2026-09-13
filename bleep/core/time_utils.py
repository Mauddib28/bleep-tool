"""Central UTC time helpers (DT-1).

``datetime.datetime.utcnow()`` is deprecated as of Python 3.12 and scheduled for
removal.  These helpers replace it while preserving BLEEP's on-disk timestamp
convention: **naive-UTC ISO 8601 strings with no offset suffix** (see
``docs/observation_db_schema.md``).

Rationale — why not the ``datetime.now(timezone.utc)`` form the deprecation
warning suggests: that returns a *timezone-aware* object whose ``.isoformat()``
appends ``+00:00``.  The observation DB stores and compares timestamps as naive
strings (e.g. SQLite ``last_seen > datetime('now', '-1 day')`` in
``bleep/core/observations/_devices.py`` and the string-sorted aggregation in
``_uuids.py``).  An offset suffix breaks lexicographic comparison, and mixing
naive/aware values raises ``TypeError`` on arithmetic.  ``utc_now_iso()`` therefore
strips ``tzinfo`` so its output is byte-shape identical to the legacy
``datetime.utcnow().isoformat()`` and remains a true drop-in.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

__all__ = ["utc_now", "utc_now_iso", "local_date_range_to_utc"]


def utc_now() -> datetime:
    """Return the current instant as a timezone-aware UTC ``datetime``.

    Use for arithmetic/durations (e.g. ``utc_now() - start``).  Do **not**
    persist ``.isoformat()`` of this to a DB DATETIME column — use
    :func:`utc_now_iso` for that (the aware form appends a ``+00:00`` offset).
    """
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return the current UTC time as a naive ISO 8601 string (no offset).

    Drop-in replacement for the deprecated ``datetime.utcnow().isoformat()``;
    output shape is ``YYYY-MM-DDTHH:MM:SS.ffffff`` — identical to the legacy call,
    matching every stored timestamp and the naive comparisons the DB relies on.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def local_date_range_to_utc(
    since: str | None,
    until: str | None,
    tz: str = "UTC",
) -> tuple[str | None, str | None]:
    """Convert an inclusive local *date* window to naive-UTC ISO bounds (DB-6).

    The observation DB stores timestamps as **naive-UTC** ISO 8601 strings and
    compares them lexicographically (see :func:`utc_now_iso` and
    ``bleep/core/observations/_devices.py``).  Operators, however, think in
    calendar dates in some local timezone.  This helper bridges the two so a
    ``--since/--until`` window given in *tz* selects exactly the intended
    instants once translated to the stored UTC representation.

    Semantics
    ---------
    * *since* / *until* are ``YYYY-MM-DD`` dates (a full ISO datetime is also
      accepted).  Either may be ``None`` (open-ended bound → returns ``None``).
    * The window is **inclusive of the whole** *until* day: the returned upper
      bound is the *exclusive* midnight following *until* (i.e. *until* + 1 day),
      so callers use ``ts >= start AND ts < end``.
    * *tz* is an IANA name (e.g. ``"America/New_York"``); ``"UTC"`` / ``None`` /
      unknown-zone fall back to UTC.  Interpretation happens in *tz*, then the
      instants are converted to UTC and stripped to naive form to match storage.

    Returns
    -------
    ``(start_iso_or_None, end_exclusive_iso_or_None)`` — naive-UTC ISO strings
    suitable for direct binding into the DB range predicate.
    """
    tzinfo = _resolve_tz(tz)

    def _to_utc_naive(value: str, *, add_day: bool) -> str:
        # ``date.fromisoformat`` would reject a full datetime; ``datetime`` accepts
        # both a bare date (→ midnight) and an explicit time, so parse leniently.
        dt = datetime.fromisoformat(value.strip())
        if add_day:
            dt = dt + timedelta(days=1)
        aware = dt.replace(tzinfo=tzinfo)
        return aware.astimezone(timezone.utc).replace(tzinfo=None).isoformat()

    start = _to_utc_naive(since, add_day=False) if since else None
    end = _to_utc_naive(until, add_day=True) if until else None
    return start, end


def _resolve_tz(tz: str | None):
    """Return a ``tzinfo`` for *tz*, falling back to UTC on any failure."""
    if not tz or tz.upper() == "UTC":
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tz)
    except Exception:  # noqa: BLE001 - unknown zone / missing tzdata → UTC
        return timezone.utc
