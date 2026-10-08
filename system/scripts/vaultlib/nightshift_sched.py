"""Window, due and pick rules (Nightshift spec §3.2)."""
from datetime import datetime, time, timedelta

from . import nightshift_item as ni

USAGE_GATE = 0.8   # 7-day usage fraction above which window items wait
FIVE_HOURS = timedelta(hours=5)


def parse_window(text) -> tuple | None:
    """(start, end), or None for a window that is always open: empty or 00:00-24:00 (Foreman v1 §3.2)."""
    text = str(text or "").replace(" ", "")
    if text in ("", "00:00-24:00"):
        return None
    a, b = text.split("-")
    return time.fromisoformat(a), time.fromisoformat(b)


def in_window(t: time, start: time, end: time) -> bool:
    return start <= t < end if start <= end else (t >= start or t < end)


def window_end(now_local: datetime, start: time, end: time) -> datetime:
    day = now_local.date()
    if start > end and now_local.time() >= start:
        day += timedelta(days=1)
    return datetime.combine(day, end, tzinfo=now_local.tzinfo)


def _dt(value) -> datetime:
    return datetime.fromisoformat(str(value))


def due(fm: dict, now_local: datetime, window: tuple, usage7: float) -> tuple:
    state = fm.get("state", "queued")
    if state == "waiting_reset" and fm.get("reset_at") and now_local < _dt(fm["reset_at"]):
        return False, "waiting for the usage reset"
    if state not in ("queued", "waiting_reset"):
        return False, state
    start = fm.get("start", "window")
    if start == "now":
        return True, ""
    if start == "at":
        return (now_local >= _dt(fm["start_at"]), "before its start time")
    if window is not None:
        if not in_window(now_local.time(), *window):
            return False, "outside the window"
        budget = ni.budget_seconds(fm.get("budget") or ("4h" if fm.get("kind") == "plan" else "1h"))
        if now_local + timedelta(seconds=budget) > window_end(now_local, *window):
            return False, "budget does not fit before the window ends"
    if usage7 is not None and usage7 > USAGE_GATE:
        return False, "7-day usage above 80%"
    return True, ""


def pick(entries, now_local: datetime, window: tuple, usage7: float):
    rank = {"now": 0, "at": 1, "window": 2}
    ready = [e for e in entries if due(e[1], now_local, window, usage7)[0]]
    ready.sort(key=lambda e: (0 if e[1].get("state") == "waiting_reset" else 1,
                              rank.get(e[1].get("start", "window"), 2), str(e[1].get("queued_at", ""))))
    return ready[0] if ready else None


def five_hour_hold(health: dict, now: datetime, ceiling: float) -> str:
    """Why no new item may start: the last session's 5-hour usage is at or above the ceiling and under 5 hours old."""
    u, at = health.get("usage5"), health.get("usage5_at")
    try:
        recent = u is not None and now - _dt(at) < FIVE_HOURS
    except (TypeError, ValueError):
        return ""
    return f"5-hour usage {round(u * 100)}% at or above {round(ceiling * 100)}%" if recent and u >= ceiling else ""


def report_date(now_local: datetime, brief_time: str) -> str:
    day = now_local.date()
    if now_local.time() >= time.fromisoformat(brief_time):
        day += timedelta(days=1)
    return day.isoformat()
