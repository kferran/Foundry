"""The calendar diff, the channel cross-check and free slots (phase D spec §3.4).

The events come from core's calendar_fetch.sh: TSV rows of start date, start time, end date, end time and title. The
fetch gives no event id, status or attendees, so an event is matched by its title: an event that disappears was
cancelled (or declined), one whose times change moved, and a title not seen before is new. The day's first snapshot
is a baseline and flags nothing.
"""
from datetime import date, datetime, timedelta

from .common import load, save, state

MIN_TITLE = 4   # a shorter title ("1:1") matches too much channel text for the cross-check
DAY_START, DAY_END, SLOT_MINUTES, MAX_SLOTS, MAX_DAYS = "09:00", "17:00", 30, 3, 5
MAX_FETCH_DAYS = 2   # each slot day is one more calendar session in the tick; the tick's budget is the manifest's


def parse_tsv(text: str) -> list:
    """[{date, start, end, title}] for the events that start on their row's date; all-day events have no times."""
    out = []
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) != 5:
            continue
        out.append({"date": cols[0], "start": cols[1], "end": cols[3], "title": cols[4]})
    return out


def _key(e) -> str:
    return " ".join(e["title"].casefold().split())


def diff(old: list, new: list) -> list:
    """[{change, title, start, end, was}]: per title, events with the same times match first; the rest pair in time
    order as moved, and what is left was cancelled (old) or is new."""
    flags = []
    for title in sorted({_key(e) for e in old + new}):
        a = sorted((e for e in old if _key(e) == title), key=lambda e: (e["start"], e["end"]))
        b = sorted((e for e in new if _key(e) == title), key=lambda e: (e["start"], e["end"]))
        same = [e for e in b if any((x["start"], x["end"]) == (e["start"], e["end"]) for x in a)]
        a = [x for x in a if not any((x["start"], x["end"]) == (e["start"], e["end"]) for e in same)]
        b = [e for e in b if e not in same]
        for x, e in zip(a, b):
            flags.append({"change": "moved", "title": e["title"], "start": e["start"], "end": e["end"],
                          "was": f"{x['start']}-{x['end']}"})
        flags += [{"change": "cancelled", "title": x["title"], "start": x["start"], "end": x["end"], "was": ""}
                  for x in a[len(b):]]
        flags += [{"change": "new", "title": e["title"], "start": e["start"], "end": e["end"], "was": ""}
                  for e in b[len(a):]]
    return flags


def _same(a: list, b: list) -> bool:
    return sorted((e["start"], e["end"], _key(e)) for e in a) == sorted((e["start"], e["end"], _key(e)) for e in b)


def snapshot(vault, day: str, events: list) -> list:
    """Compare today's events with the day's base snapshot and return the flags (none on the day's first snapshot).
    Each tick's list is a model's transcription, so a change shows only when the next tick lists the same events: an
    event one tick drops or rewords and the next lists again flags nothing. The base moves only when flags show."""
    path = state(vault) / f"calendar-{day}.json"
    old = load(path, None)
    today = [e for e in events if e["date"] == day]
    if not isinstance(old, dict) or not isinstance(old.get("base"), list):
        save(path, {"base": today, "last": today})
        return []
    flags = diff(old["base"], today)
    # ponytail: whole-list match, so one event reworded every tick holds back every flag; per-flag persistence if seen
    if flags and not _same(today, old.get("last") or []):
        save(path, {"base": old["base"], "last": today})
        return []
    save(path, {"base": today, "last": today})
    return flags


def cross(items: list, events: list, day: str) -> list:
    """[(item, event)]: a meeting_change a channel calls cancelled whose message names an event today that the
    calendar still lists."""
    out = []
    for i in items:
        if i.get("kind") != "meeting_change" or i.get("change") != "cancelled":
            continue
        text = " ".join(f"{i.get('text', '')} {i.get('what', '')}".casefold().split())
        for e in events:
            if e["date"] == day and len(_key(e)) >= MIN_TITLE and _key(e) in text:
                out.append((i, e))
                break
    return out


def workdays(today: str, by: str) -> list:
    """The workdays after today up to and including `by` (or the next MAX_DAYS when there is none), at most MAX_DAYS."""
    start = date.fromisoformat(today)
    end = date.fromisoformat(by) if by else None
    out, d = [], start
    while len(out) < MAX_DAYS:
        d += timedelta(days=1)
        if end and d > end:
            break
        if d.weekday() < 5:
            out.append(d.isoformat())
    return out


def slot_days(today: str, items: list) -> list:
    """The workdays whose calendar the meeting commitments' free slots need, at most MAX_FETCH_DAYS: each is one
    calendar session, and the tick must end inside the unit's TimeoutStartSec."""
    days = {d for i in items if i["kind"] == "commitment" and i["meeting"] for d in workdays(today, i["by"])}
    return sorted(days)[:MAX_FETCH_DAYS]


def free_slots(events: list, days: list, after: str = "") -> list:
    """Up to MAX_SLOTS "YYYY-MM-DD HH:MM" starts of a free SLOT_MINUTES between DAY_START and DAY_END on the given
    days, from the events fetched for them; `after` ("YYYY-MM-DD HH:MM") skips earlier slots."""
    out = []
    for day in days:
        busy = [(e["start"], e["end"]) for e in events if e["date"] == day and e["start"]]
        if any(e["date"] == day and not e["start"] for e in events):
            continue   # an all-day event (leave, travel) takes the day
        t = datetime.fromisoformat(f"{day}T{DAY_START}")
        stop = datetime.fromisoformat(f"{day}T{DAY_END}")
        while t + timedelta(minutes=SLOT_MINUTES) <= stop and len(out) < MAX_SLOTS:
            s, e = t.strftime("%H:%M"), (t + timedelta(minutes=SLOT_MINUTES)).strftime("%H:%M")
            if f"{day} {s}" >= after and not any(bs < e and s < be for bs, be in busy):
                out.append(f"{day} {s}")
                t += timedelta(minutes=SLOT_MINUTES * 4)   # spread the offer over the day
            else:
                t += timedelta(minutes=SLOT_MINUTES)
    return out
