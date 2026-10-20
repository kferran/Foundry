"""Where each watch item goes (phase D spec §3.5): the item ledger the today file is written from, a Now line for a
deadline, a block or a commitment, and a [watch] alert for a meeting change or an incident. The caller holds run.lock.

The item ledger (system/logs/watch/items-<YYYY-MM>.jsonl) keys each item by its query and message, so a message read
again by the next tick's overlap never routes twice. A Now line is skipped when an open or archived line already
holds the same link (chat triage's lines included), when an open line's statement already says it, or, for a meeting
commitment, when a fetched calendar event names the person.
"""
import re
from datetime import date

from vaultlib import now as nowmod

from . import calendar as cal
from .common import alert, append, records, state

MAX_ALERTS = 3
NOW_KINDS = {"deadline": "owed", "blocked": "waiting", "commitment": "owed", "request": "owed"}
ALERT_CHANGES = ("cancelled", "moved")
SAID_WORDS = 4
STOPWORDS = {"team", "with", "from", "group", "everyone", "folks", "people", "them", "they"}


def ledger_path(vault, day: str):
    return state(vault) / f"items-{day[:7]}.jsonl"


def seen(vault, day: str) -> set:
    first = date.fromisoformat(day).replace(day=1)
    prev = date.fromordinal(first.toordinal() - 1).isoformat()
    rows = [r for d in (prev, day) for r in records(ledger_path(vault, d))]
    return {r.get("key") for r in rows} | {k for r in rows for k in r.get("keys") or []}


def _norm(text: str) -> str:
    return " ".join(str(text).casefold().split())


def _page_texts(vault, partition: str, day: str) -> list:
    """The Now page and the archive notes of this month and the last."""
    first = date.fromisoformat(day).replace(day=1)
    prev = date.fromordinal(first.toordinal() - 1).isoformat()
    return [nowmod.read(vault, partition), *nowmod.archived(vault, partition, prev, day)]


def _known_link(vault, partition: str, link: str, day: str) -> bool:
    return any(link in t for t in _page_texts(vault, partition, day))


PR_NUMBER = re.compile(r"(?:\bPR|\bpull request)\s*#?\s*(\d+)\b", re.IGNORECASE)
TICKET_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def _known_id(vault, partition: str, text: str, day: str) -> bool:
    """A Now line (open or archived) already names a PR number or a ticket key `text` names: in its words ("PR #12",
    "app PR #12", "PR app #12", "pull request #12") or in its evidence URL (/pull/12, /pull-requests/12,
    /merge_requests/12, or the key anywhere, as in /browse/OPS-101).
    ponytail: the same PR number in two repos counts as covered; match the repo too if that ever hides a real ask."""
    finds = [re.compile(rf"(?:\bPR|\bpull request)\s*(?:[\w.-]+\s+)?#?\s*{n}\b|/(?:pull-requests|pull|merge_requests)/{n}\b",
                        re.IGNORECASE) for n in set(PR_NUMBER.findall(text))]
    finds += [re.compile(rf"(?<![\w-]){re.escape(k)}(?!\d)") for k in set(TICKET_KEY.findall(text))]
    return bool(finds) and any(rx.search(t) for t in _page_texts(vault, partition, day) for rx in finds)


def _said(vault, partition: str, what: str) -> bool:
    """An open line says the same task: the same statement, or one that holds it as whole words when it has at least
    SAID_WORDS words (a shorter phrase, "follow up", names an action, not a task)."""
    w = _norm(what)
    for line in nowmod.open_lines(nowmod.read(vault, partition)):
        m = nowmod.parse(line)
        s = _norm(nowmod.fields(m.group("statement"))[0]) if m else ""
        if m and (w == s or (len(w.split()) >= SAID_WORDS and f" {w} " in f" {s} ")):
            return True
    return False


def _words(text: str) -> set:
    return set(re.findall(r"\w+", _norm(text)))


def _calendar_names(events: list, who: str) -> bool:
    """A fetched event's title names the person: a whole word of 4+ letters from `who`, not a stopword."""
    names = {t for t in _words(who) if len(t) >= 4} - STOPWORDS
    return any(names & _words(e["title"]) for e in events)


def _span(start: str, end: str) -> str:
    return f" {start}-{end}" if start else ""


def now_line(vault, partition: str, item: dict, day: str, events: list) -> tuple:
    """(status, line) for an item that makes a Now line: "added", "exists", "covered" or "refused"."""
    kind = NOW_KINDS[item["kind"]]
    # A sent-mail link is the thread's: a later commitment in the same thread is new, so sent mail relies on the ledger
    # and _said. An incoming thread is one item, so its link counts, as triage's line for the same thread does.
    if item["query"] != "mail" and _known_link(vault, partition, item["link"], day):
        return "covered", ""
    # An incoming PR or ticket mail is covered by a line on the same PR or ticket from another source (#289).
    if item["query"] == "inbound" and _known_id(vault, partition, f"{item['what']} {item.get('text', '')}", day):
        return "covered", ""
    if item["kind"] in ("commitment", "request") and (_said(vault, partition, item["what"])
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
        append(path, {"key": key, "day": day, "time": clock[:5], "kind": kind, "text": text, "link": link, "now": now,
                      "partition": partition})
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
        e = next((e for i, e in crossed if i is item), None)   # a cancellation the calendar still lists: one line
        text = (f"{e['title']}{_span(e['start'], e['end'])} cancelled per {item['label']} (calendar still confirmed)"
                if e else f"{item['what']} ({item['label']})")
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
    for text in alerts[:MAX_ALERTS]:
        alert(vault, day, clock, "watch", text)
        counts["alerts"] += 1
    if len(alerts) > MAX_ALERTS:
        alert(vault, day, clock, "watch", f"and {len(alerts) - MAX_ALERTS} more meeting changes or incidents; see the "
                                          f"today file")
        counts["alerts"] += 1
    return counts


def _capture_key(m: dict) -> str:
    return f"capture:{m['channel']}/{m['ts']}"


def new_captures(vault, day: str, messages: list) -> list:
    """The capture messages no earlier tick wrote: the capture search reads back through the cursor's overlap."""
    done = seen(vault, day)
    return [m for m in messages if _capture_key(m) not in done]


def captured(vault, day: str, clock: str, rel: str, messages: list, partition: str) -> None:
    """One ledger row per capture file (one today-file line), holding each message's key in `keys`."""
    n = len(messages)
    append(ledger_path(vault, day), {"key": f"capture:{rel}", "day": day, "time": clock[:5], "kind": "capture",
                                     "text": f"{n} message{'s' if n != 1 else ''} → {rel}", "link": "", "now": "",
                                     "partition": partition, "keys": [_capture_key(m) for m in messages]})
