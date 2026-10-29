"""Inbox triage (inbox triage spec; chat triage spec): the Gmail query and the Slack search input, the check of a
triage_fetch.sh session, and the write.

A session may call only its source's search (vaultlib.connector checks its stream). Each item's link, date and sender
come from the search results; from the model's reply only the thread (or channel and ts) and three short texts are
used, and one the search never returned is dropped. Each source keeps its own cursor in the ledger.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import alerts, nightshift_sched as ns
from . import now as nowmod
from . import state
# _structured and _text_json stay importable for the intraday watch until its retrofit (F1 spec §3.6).
from .connector import Fail, check_stream, strip_cursor, structured as _structured, text_json as _text_json
from .config import config
from .notify import prefix

TOOL = "mcp__claude_ai_Gmail__search_threads"
CHAT_TOOL = "slack_search_public_and_private"
CHAT_MAX_PAGES = 5
CHAT_FIELDS = {"channel": re.compile(r"^Channel: #(\S*) \(ID: ([CG][A-Z0-9]+)\)", re.M),
               "sender": re.compile(r"^From: (.*?) \(ID: [A-Z0-9]+\)", re.M),
               "ts": re.compile(r"^Message_ts: (\d+\.\d+)", re.M),
               "link": re.compile(r"^Permalink: \[[^\]]*\]\((https://[^)\s]+)\)", re.M)}
EXCLUDE = "-category:promotions -category:social -category:forums -from:me"
MAX_PAGES = 6   # of PAGE_SIZE threads, as the watch's MAIL_PAGES: a page of 50 can pass the model's limit (#289)
PAGE_SIZE = 10  # triage_fetch.sh asks for it
OVERLAP_SECONDS = 300
FIRST_LOOKBACK_SECONDS = 2 * 3600
TEXT_MAX = 160
HEALTH_DIR = "system/logs/nightshift"
SENDER = re.compile(r"[A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
WATCH_WINDOW = "newer_than:2d"


def _logs(vault, today: str) -> list:
    first = date.fromisoformat(today).replace(day=1)
    months = [(first - timedelta(days=1)).strftime("%Y-%m"), first.strftime("%Y-%m")]
    return [Path(vault) / "system" / "logs" / f"triage-{m}.jsonl" for m in months]


def records(vault, today: str) -> list:
    return state.records(*_logs(vault, today))


def partition(vault) -> str:
    """triage_partition (default work), checked before any session runs."""
    value = str(config(vault).get("triage_partition") or "work")
    if value not in nowmod.PARTITIONS:
        raise Fail(2, f"triage_partition must be one of {', '.join(nowmod.PARTITIONS)}, not {value!r}")
    return value


def watch_senders(vault) -> list:
    """triage_watch_senders: domains (@example.com) or addresses whose unread mail counts even when archived. Each
    entry is checked before it reaches the query, so a config value cannot change the search."""
    value = config(vault).get("triage_watch_senders") or []
    senders = value if isinstance(value, list) else [value]
    for s in senders:
        if not isinstance(s, str) or not SENDER.fullmatch(s):
            raise Fail(2, f"triage_watch_senders: {s!r} is not a domain (@example.com) or an address")
    return senders


def cursor(vault, now_epoch: int, today: str, source: str) -> int:
    """The source's last successful tick (with an overlap), or two hours back on its first run. A record without a
    source is mail; a held tick (a page the model could not read) moves no cursor."""
    ticks = [r.get("epoch") for r in records(vault, today) if r.get("kind") == "tick" and not r.get("hold")
             and isinstance(r.get("epoch"), int) and r.get("source", "mail") == source]
    return max(ticks) - OVERLAP_SECONDS if ticks else now_epoch - FIRST_LOOKBACK_SECONDS


def query(vault, now_epoch: int, today: str) -> str:
    """Mail since the last mail tick; with watched senders, also their unread mail outside the inbox from the last two
    days (deduped by record())."""
    partition(vault)
    senders = watch_senders(vault)
    after = cursor(vault, now_epoch, today, "mail")
    if not senders:
        return f"in:inbox after:{after} {EXCLUDE}"
    return (f"((in:inbox after:{after}) OR (is:unread -in:inbox from:({' OR '.join(senders)}) {WATCH_WINDOW})) "
            + EXCLUDE)


def chat_enabled(vault) -> bool:
    return str(config(vault).get("triage_chat_enabled", "false")).lower() == "true"


def chat_tool(vault) -> str:
    return prefix(str(config(vault).get("slack_connector") or "claude.ai Slack")) + "__" + CHAT_TOOL


def chat_query(vault, now_epoch: int, today: str) -> dict:
    """The Slack search input: every channel the owner is in since the last chat tick. The tool refuses a search with
    no filter, and Slack reads a date filter in the owner's timezone, so it reaches two days back; `after` bounds it."""
    partition(vault)
    after = cursor(vault, now_epoch, today, "chat")
    day = datetime.fromtimestamp(after, timezone.utc).date() - timedelta(days=2)
    return {"filters": f"after:{day}", "only_my_channels": True, "channel_types": "public_channel,private_channel",
            "content_types": "messages", "after": str(after), "sort": "timestamp", "limit": 20,
            "include_bots": False, "include_context": False, "response_format": "detailed"}


def hold(vault, now) -> str:
    """Why this tick is skipped: the newest 5-hour usage reading is at or above order_max_five_hour."""
    try:
        ceiling = float(config(vault).get("order_max_five_hour", 0.6))
    except (TypeError, ValueError):
        ceiling = 0.6
    files = sorted((Path(vault) / HEALTH_DIR).glob("health-*.json"))
    try:
        health = json.loads(files[-1].read_text(encoding="utf-8")) if files else {}
    except (OSError, json.JSONDecodeError):
        health = {}
    return ns.five_hour_hold(health if isinstance(health, dict) else {}, now, ceiling)


def stats(results: int, persisted: int = 0) -> dict:
    """A tick's counts for its log line (counts only, never mail or chat text): what the search returned, the reply's
    rows, the rows kept, the pages the model saw only as too large, and the rows dropped by reason."""
    return {"results": results, "rows": 0, "kept": 0, "persisted": persisted,
            "dropped": {"unknown": 0, "empty": 0, "duplicate": 0}}


def threads(got: list) -> dict:
    """thread id -> {link, date, sender} of its latest message, from the search results only."""
    out = {}
    for sc in got:
        listed = sc.get("threads", [])  # an empty object means no threads
        if not isinstance(listed, list):
            raise Fail(1, "the search result carries no threads list")
        for t in listed:
            msgs = [m for m in (t.get("messages") or []) if isinstance(m, dict)] if isinstance(t, dict) else []
            if not (isinstance(t, dict) and isinstance(t.get("id"), str) and str(t.get("viewUrl", "")).startswith("https://")
                    and msgs):
                raise Fail(1, "a thread lacks an id, a link or its messages")
            # A thread comes back whole when one message matches: the owner's own replies never make it new.
            msgs = [m for m in msgs if "SENT" not in (m.get("labelIds") or [])]
            if not msgs:
                continue
            latest = max(msgs, key=lambda m: str(m.get("date", "")))
            out[t["id"]] = {"link": t["viewUrl"], "date": str(latest.get("date", "")), "sender": str(latest.get("sender", ""))}
    return out


def one_line(text) -> str:
    """Mail text as one short plain line: no newline, link or HTML syntax can reach the Now page."""
    text = re.sub(r"\s+", " ", str(text or "")).strip().replace("[", "(").replace("]", ")")
    text = text.replace("<", "‹").replace(">", "›")
    return text if len(text) <= TEXT_MAX else text[: TEXT_MAX - 1].rstrip() + "…"


def address(sender: str) -> str:
    """The sender's address, which fits the Now line's who field (no commas or parentheses)."""
    m = re.search(r"<([^<>\s]+@[^<>\s]+)>", sender)
    return re.sub(r"[(),\s]", "", m.group(1) if m else sender)[:80]


def reply(result: dict) -> list:
    text = str(result.get("result") or "")
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise Fail(1, "the session's reply is not the JSON asked for")
    return [i for i in data["items"] if isinstance(i, dict)]


def extract(stream, q: str) -> dict:
    """{"items": [...], "full": bool, "hold": bool, "stats": {...}}: the threads the session marked, joined to the
    search results. full: the last page read still had a nextPageToken. hold: the model saw a page only as too large
    (its threads still come from the stream's structuredContent), so the tick keeps the cursor."""
    def accept(i):
        if i.get("query") != q or i.get("view") != "THREAD_VIEW_MINIMAL":
            return None
        if i.get("pageSize") != PAGE_SIZE:   # with MAX_PAGES, the cap on threads a tick (60), held in code
            raise Fail(7, f"the session searched with pageSize {i.get('pageSize')}; the page size is {PAGE_SIZE}")
        return "search"
    persisted = {}
    pages, result = check_stream(stream, TOOL, accept, MAX_PAGES, "Gmail", persisted)
    got = pages.get("search", [])
    known = threads(got)
    s = stats(sum(len(p.get("threads") or []) for p in got), persisted.get("search", 0))
    items, seen = [], set()
    for r in reply(result):
        s["rows"] += 1
        tid = r.get("thread_id")
        ask = one_line(r.get("ask"))
        why = ("unknown" if not isinstance(tid, str) or tid not in known else "duplicate" if tid in seen
               else "empty" if not ask else "")
        if why != "unknown":
            seen.add(tid)
        if why:
            s["dropped"][why] += 1   # a thread id the search never returned is dropped
            continue
        t = known[tid]
        items.append({"thread_id": tid, "date": t["date"], "link": t["link"], "sender": address(t["sender"]),
                      "who": one_line(r.get("who")) or address(t["sender"]), "ask": ask,
                      "next_step": one_line(r.get("next_step"))})
    s["kept"] = len(items)
    return {"items": items, "full": bool(got) and bool(got[-1].get("nextPageToken")), "hold": bool(persisted),
            "stats": s}


def chat_messages(got: list, notify_channel: str) -> dict:
    """"<channel id>/<ts>" -> {link, date, sender, channel}, from the search results' markdown only. Message text sits
    inside that markdown, so a piece is a result only when its link is that message's own Slack permalink, and the
    first piece for a message wins (its real header comes before its text). A piece without the fields is body text,
    skipped. A result in the notify channel is skipped: notices post as the owner, and triage must not read its own
    back."""
    out = {}
    for page in got:
        results = page.get("results")
        if not isinstance(results, str):
            raise Fail(1, "a chat search result is not in the shape asked for")
        parsed = 0
        for part in results.split("### Result ")[1:]:
            f = {k: rx.search(part) for k, rx in CHAT_FIELDS.items()}
            if not (f["channel"] and f["ts"] and f["link"]):
                continue
            cid, ts, link = f["channel"].group(2), f["ts"].group(1), f["link"].group(1)
            if not re.match(rf"https://(?:[a-z0-9-]+\.)+slack\.com/archives/{cid}/p{ts.replace('.', '')}(?:\?|$)", link):
                continue
            parsed += 1
            if cid == notify_channel or f"{cid}/{ts}" in out:
                continue
            out[f"{cid}/{ts}"] = {"link": link, "date": ts, "channel": f["channel"].group(1),
                                  "sender": f["sender"].group(1) if f["sender"] else ""}
        listed = re.search(r"^## Messages \((\d+) results?\)", results, re.M)
        if listed and int(listed.group(1)) > 0 and parsed == 0:
            raise Fail(1, "a chat search result is not in the shape asked for")
    return out


def chat_extract(stream, q: dict, tool: str, notify_channel: str) -> dict:
    """extract() for the Slack search: each search input is q, with only a cursor added on later pages. Items take
    the mail item's shape (thread_id "<channel id>/<ts>"), so record() writes both."""
    pages, result = check_stream(stream, tool, lambda i: "search" if strip_cursor(i) == q else None, CHAT_MAX_PAGES,
                                 "Slack", take=_text_json)
    got = pages.get("search", [])
    known = chat_messages(got, notify_channel)
    items, s = [], stats(len(known))   # results: the messages returned, less the notify channel's
    for r in reply(result):
        s["rows"] += 1
        key = f"{r.get('channel_id')}/{r.get('ts')}"
        ask = one_line(r.get("ask"))
        why = ("unknown" if key not in known else "empty" if ask == "" else
               "duplicate" if key in {i["thread_id"] for i in items} else "")
        if why:
            s["dropped"][why] += 1   # a message the search never returned is dropped
            continue
        m = known[key]
        items.append({"thread_id": key, "date": m["date"], "link": m["link"], "sender": address(m["sender"]),
                      "who": f"{one_line(r.get('who')) or address(m['sender'])} in #{one_line(m['channel'])}",
                      "ask": ask, "next_step": one_line(r.get("next_step"))})
    # A last page that still offers a cursor left messages unread, whether the session read 5 pages or stopped early.
    full = "use cursor `" in str(got[-1].get("pagination_info") or "") if got else False
    s["kept"] = len(items)
    return {"items": items, "full": full, "hold": False, "stats": s}


REFUSED = "a Now line was refused"   # an alert names the reason, never the line (factory F5 spec §4.2)


def record(vault, partition: str, found: dict, today: str, now_iso: str, now_epoch: int, source: str = "mail") -> list:
    """Add a Now line for each item whose (thread, latest message) is new to its source, then record the tick (held
    when found["hold"]: the next tick reads the same window). The caller holds run.lock. Returns the lines added."""
    log, writer = _logs(vault, today)[1], "chat" if source == "chat" else "mail"
    known = {(r.get("thread_id"), r.get("date")) for r in records(vault, today)
             if r.get("kind") == "item" and r.get("source", "mail") == source}
    added, mine, prev = [], {t for t, _ in known}, (date.fromisoformat(today).replace(day=1) - timedelta(days=1)).isoformat()
    held = "\n".join([nowmod.read(vault, partition), *nowmod.archived(vault, partition, prev, today)])
    for i in found.get("items") or []:
        if (i["thread_id"], i["date"]) in known or (i["link"] in held and i["thread_id"] not in mine):
            continue   # seen, or another source's line (the intraday watch's) already holds the thread
        statement = f"{i['who']}: {i['ask'].rstrip('.')}." + (f" Next: {i['next_step']}" if i.get("next_step") else "")
        try:
            status, line = nowmod.add(vault, partition, "owed", statement, today, i["sender"], i["link"], fit=True,
                                      via=writer)
        except ValueError:  # a link or sender the Now line cannot hold: keep the item, drop the metadata
            try:
                status, line = nowmod.add(vault, partition, "owed", f"{statement} ({i['link']})", today, fit=True,
                                          via=writer)
            except ValueError as exc:   # still no valid line: record the item so the tick and the items after it go on
                status, line = "refused", ""
                alerts.alert(vault, today, now_iso[11:19], "triage", f"{REFUSED} ({nowmod.refusal(exc)})", key=REFUSED)
        state.append(log, {"kind": "item", "thread_id": i["thread_id"], "date": i["date"], "line": line,
                           "time": now_iso, "source": source})
        known.add((i["thread_id"], i["date"]))
        if status == "added":
            added.append(f"{i['who']}: {i['ask']}")
    state.append(log, {"kind": "tick", "epoch": now_epoch, "time": now_iso, "items": len(added),
                       "full": bool(found.get("full")), "source": source, **({"hold": True} if found.get("hold") else {})})
    return added
