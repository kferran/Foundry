"""Where each watch item goes (phase D spec §3.5): the item ledger the today file is written from, a Now line for a
deadline, a block or a commitment, and a [watch] alert for a meeting change or an incident. The caller holds run.lock.

The item ledger (system/logs/watch/items-<YYYY-MM>.jsonl) keys each item by its query and message, so a message read
again by the next tick's overlap never routes twice. A Now line is skipped when an open or archived line already
holds the same link (chat triage's lines included), when an open line's statement already says it, or, for a meeting
commitment, when a fetched calendar event names the person.
"""
from datetime import date

from vaultlib import now as nowmod

from . import calendar as cal
from .common import alert, append, records, state

MAX_ALERTS = 3
NOW_KINDS = {"deadline": "owed", "blocked": "waiting", "commitment": "owed"}
ALERT_CHANGES = ("cancelled", "moved")


def ledger_path(vault, day: str):
    return state(vault) / f"items-{day[:7]}.jsonl"


def seen(vault, day: str) -> set:
    first = date.fromisoformat(day).replace(day=1)
    prev = date.fromordinal(first.toordinal() - 1).isoformat()
    return {r.get("key") for d in (prev, day) for r in records(ledger_path(vault, d))}


def _norm(text: str) -> str:
    return " ".join(str(text).casefold().split())


def _known_link(vault, partition: str, link: str, day: str) -> bool:
    first = date.fromisoformat(day).replace(day=1)
    prev = date.fromordinal(first.toordinal() - 1).isoformat()
    texts = [nowmod.read(vault, partition), *nowmod.archived(vault, partition, prev, day)]
    return any(link in t for t in texts)


def _said(vault, partition: str, what: str) -> bool:
    w = _norm(what)
    for line in nowmod.open_lines(nowmod.read(vault, partition)):
        m = nowmod.parse(line)
        if m and w in _norm(nowmod.fields(m.group("statement"))[0]):
            return True
    return False


def _calendar_names(events: list, who: str) -> bool:
    token = next((t for t in _norm(who).split() if len(t) >= 3), "")
    return bool(token) and any(token in _norm(e["title"]) for e in events)


def _span(start: str, end: str) -> str:
    return f" {start}-{end}" if start else ""


def now_line(vault, partition: str, item: dict, day: str, events: list) -> tuple:
    """(status, line) for an item that makes a Now line: "added", "exists", "covered" or "refused"."""
    kind = NOW_KINDS[item["kind"]]
    if _known_link(vault, partition, item["link"], day):
        return "covered", ""
    if item["kind"] == "commitment" and (_said(vault, partition, item["what"])
                                         or (item["meeting"] and _calendar_names(events, item["who"]))):
        return "covered", ""
    where = "" if item["label"] == "mail" else f" (in {item['label']})"
    statement = f"{item['what']}{where}"
    due = item["by"] if item["by"] and item["by"] >= day else ""
    try:
        status, line = nowmod.add(vault, partition, kind, statement, day, item["who"], item["link"], due=due)
    except ValueError:
        try:
            status, line = nowmod.add(vault, partition, kind, statement, day, "", item["link"], due=due)
        except ValueError:
            return "refused", ""
    return ("added" if status == "added" else "exists"), line


def route(vault, partition: str, found: dict, flags: list, crossed: list, events: list, fetched: list,
          day: str, clock: str) -> dict:
    """Route this tick's items, calendar flags and cross-check hits. Returns {"items", "now", "alerts"} counts."""
    done, path = seen(vault, day), ledger_path(vault, day)
    alerts, counts = [], {"items": 0, "now": 0, "alerts": 0}

    def log(key, kind, text, link="", now=""):
        append(path, {"key": key, "day": day, "time": clock[:5], "kind": kind, "text": text, "link": link, "now": now})
        done.add(key)
        counts["items"] += 1

    for item in found.get("items") or []:
        key = f"{item['query']}:{item['key']}"
        if key in done:
            continue
        status = ""
        if item["kind"] in NOW_KINDS and not (item["kind"] == "blocked" and not item["who"]):
            status, line = now_line(vault, partition, item, day, events)
            if status == "added":
                counts["now"] += 1
                if item["kind"] == "commitment" and item["meeting"]:
                    slots = cal.free_slots(events, [d for d in cal.workdays(day, item["by"]) if d in fetched],
                                           f"{day} {clock[:5]}")
                    if slots:
                        try:
                            nowmod.note(vault, partition, item["what"], f"free: {', '.join(slots)}", day)
                        except ValueError:
                            pass   # another open line holds the same text: the slots are an offer, not the item
        text = f"{item['what']} ({item['label']})"
        log(key, "meeting" if item["kind"] == "meeting_change" else item["kind"], text, item["link"], status)
        if item["kind"] == "incident" or (item["kind"] == "meeting_change" and item["change"] in ALERT_CHANGES):
            alerts.append(f"{text} {item['link']}")
    for f in flags:
        key = f"cal:{day}:{f['change']}:{f['title']}:{f['start']}:{f['end']}"
        if key in done:
            continue
        if f["change"] == "moved":
            text = f"{f['title']} moved from {f['was']} to{_span(f['start'], f['end'])}"
        elif f["change"] == "cancelled":
            text = f"{f['title']}{_span(f['start'], f['end'])} is gone from the calendar"
        else:
            text = f"new in the calendar: {f['title']}{_span(f['start'], f['end'])}"
        log(key, "meeting", text)
        if f["change"] in ALERT_CHANGES:
            alerts.append(text)
    for item, e in crossed:
        key = f"cross:{day}:{e['title']}:{e['start']}"
        if key in done:
            continue
        text = f"{e['title']}{_span(e['start'], e['end'])} cancelled per {item['label']} (calendar still confirmed)"
        log(key, "meeting", text, item["link"])
        alerts.append(f"{text} {item['link']}")
    for text in alerts[:MAX_ALERTS]:
        alert(vault, day, clock, "watch", text)
        counts["alerts"] += 1
    if len(alerts) > MAX_ALERTS:
        alert(vault, day, clock, "watch", f"and {len(alerts) - MAX_ALERTS} more meeting changes or incidents; see the "
                                          f"today file")
        counts["alerts"] += 1
    return counts


def captured(vault, day: str, clock: str, rel: str, n: int) -> None:
    append(ledger_path(vault, day), {"key": f"capture:{rel}", "day": day, "time": clock[:5], "kind": "capture",
                                     "text": f"{n} message{'s' if n != 1 else ''} → {rel}", "link": "", "now": ""})
