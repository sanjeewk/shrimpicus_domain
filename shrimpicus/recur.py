"""Pure recurrence math for cron-style reminders.

No DB, no Discord. Easy to unit-test in isolation.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WEEKDAY_ALIASES: dict[str, int] = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}

VALID_KINDS = ("daily", "weekly", "monthly")


def parse_time(hhmm: str) -> tuple[int, int]:
    """Parse 'HH:MM' (24-hour). Raises ValueError on bad input."""
    parts = hhmm.split(":")
    if len(parts) != 2:
        raise ValueError(f"time must be HH:MM, got {hhmm!r}")
    h_str, m_str = parts
    if not (h_str.isdigit() and m_str.isdigit()):
        raise ValueError(f"time must be HH:MM, got {hhmm!r}")
    h, m = int(h_str), int(m_str)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"time out of range: {hhmm!r}")
    return h, m


def parse_weekday(name: str) -> int:
    """Parse 'mon' / 'monday' / etc -> 0..6 (Mon..Sun). Raises ValueError."""
    key = name.strip().lower()
    if key not in WEEKDAY_ALIASES:
        raise ValueError(f"unknown weekday {name!r}; use mon/tue/wed/thu/fri/sat/sun")
    return WEEKDAY_ALIASES[key]


def last_occurrence_before(
    *,
    kind: str,
    before_utc: datetime,
    user_tz: str,
    time_hhmm: str,
    dow: int | None = None,
    dom: int | None = None,
) -> datetime:
    """Most recent scheduled occurrence strictly before before_utc (UTC)."""
    tz = ZoneInfo(user_tz)
    h, m = parse_time(time_hhmm)
    local_cursor = before_utc.astimezone(tz)
    # Walk back day by day from today; check if target time has already passed today.
    candidate_date = local_cursor.date()
    if (local_cursor.hour, local_cursor.minute) <= (h, m):
        # Today's slot hasn't happened yet; start searching from yesterday.
        candidate_date -= timedelta(days=1)
    for _ in range(400):
        if _matches(kind, candidate_date, dow, dom):
            local_dt = datetime(
                candidate_date.year, candidate_date.month, candidate_date.day, h, m, tzinfo=tz
            )
            utc_dt = local_dt.astimezone(timezone.utc)
            if utc_dt < before_utc:
                return utc_dt
        candidate_date -= timedelta(days=1)
    raise RuntimeError("no occurrence within 400 days before")


def next_occurrence(
    *,
    kind: str,
    after_utc: datetime,
    user_tz: str,
    time_hhmm: str,
    dow: int | None = None,
    dom: int | None = None,
) -> datetime:
    """Next scheduled occurrence strictly after after_utc (UTC)."""
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {VALID_KINDS}, got {kind!r}")
    tz = ZoneInfo(user_tz)
    h, m = parse_time(time_hhmm)
    if kind == "weekly" and dow is None:
        raise ValueError("weekly recurrence requires dow")
    if kind == "monthly" and dom is None:
        raise ValueError("monthly recurrence requires dom")

    local_cursor = after_utc.astimezone(tz)
    candidate_date = local_cursor.date()
    # If today's target slot is still ahead, today is a candidate.
    if (local_cursor.hour, local_cursor.minute) < (h, m):
        pass  # keep today
    else:
        candidate_date += timedelta(days=1)

    for _ in range(400):
        if _matches(kind, candidate_date, dow, dom):
            local_dt = datetime(
                candidate_date.year, candidate_date.month, candidate_date.day, h, m, tzinfo=tz
            )
            utc_dt = local_dt.astimezone(timezone.utc)
            if utc_dt > after_utc:
                return utc_dt
        candidate_date += timedelta(days=1)
    raise RuntimeError("no occurrence within 400 days after")


def _matches(kind: str, d, dow: int | None, dom: int | None) -> bool:
    if kind == "daily":
        return True
    if kind == "weekly":
        return d.weekday() == dow
    if kind == "monthly":
        days_in_month = calendar.monthrange(d.year, d.month)[1]
        # Clamp to last day if requested dom exceeds month length.
        effective = min(dom, days_in_month)
        return d.day == effective
    return False


def validate_timezone(name: str) -> str:
    """Return the IANA name if valid; raise ValueError otherwise."""
    try:
        ZoneInfo(name)
    except Exception as exc:
        raise ValueError(f"unknown timezone {name!r}") from exc
    return name


def format_local(dt_utc: datetime, user_tz: str) -> str:
    """Render a UTC datetime in the user's local TZ, ISO-ish with offset."""
    try:
        local = dt_utc.astimezone(ZoneInfo(user_tz))
    except Exception:
        local = dt_utc
    return local.strftime("%Y-%m-%d %H:%M %Z")


def describe_schedule(*, kind: str, time_hhmm: str, dow: int | None, dom: int | None) -> str:
    """Human-readable schedule tag, e.g. 'weekly mon 09:00', 'monthly day-1 10:00'."""
    if kind == "daily":
        return f"daily {time_hhmm}"
    if kind == "weekly":
        names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        return f"weekly {names[dow] if dow is not None else '?'} {time_hhmm}"
    if kind == "monthly":
        return f"monthly day-{dom} {time_hhmm}"
    return kind
