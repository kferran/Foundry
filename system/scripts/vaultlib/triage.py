"""Inbox triage (inbox triage spec; chat triage spec): the Gmail query and the Slack search input, the check of a
triage_fetch.sh session, and the write.

A session may call only its source's search. Each item's link, date and sender come from the search results, paired
with the call by tool_use_id; from the model's reply only the thread (or channel and ts) and three short texts are
used, and one the search never returned is dropped. Each source keeps its own cursor in the ledger.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import frontmatter
from . import nightshift_sched as ns
from . import now as nowmod
from .notify import prefix
from .stream import blocks

TOOL = "mcp__claude_ai_Gmail__search_threads"
CHAT_TOOL = "slack_search_public_and_private"
CHAT_MAX_PAGES = 5
CHAT_FIELDS = {"channel": re.compile(r"^Channel: #(\S*) \(ID: ([CG][A-Z0-9]+)\)", re.M),
               "sender": re.compile(r"^From: (.*?) \(ID: [A-Z0-9]+\)", re.M),
               "ts": re.compile(r"^Message_ts: (\d+\.\d+)", re.M),
               "link": re.compile(r"^Permalink: \[[^\]]*\]\((https://[^)\s]+)\)", re.M)}
EXCLUDE = "-category:promotions -category:social -category:forums -from:me"
MAX_PAGES = 3
OVERLAP_SECONDS = 300
FIRST_LOOKBACK_SECONDS = 2 * 3600
TEXT_MAX = 160
HEALTH_DIR = "system/logs/nightshift"
SENDER = re.compile(r"[A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
WATCH_WINDOW = "newer_than:2d"


class Fail(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code, self.reason = code, reason


def config(vault) -> dict:
    path = Path(vault) / "system" / "config.md"
    return (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}) if path.is_file() else {}


def _logs(vault, today: str) -> list:
    first = date.fromisoformat(today).replace(day=1)
    months = [(first - timedelta(days=1)).strftime("%Y-%m"), first.strftime("%Y-%m")]
    return [Path(vault) / "system" / "logs" / f"triage-{m}.jsonl" for m in months]


def records(vault, today: str) -> list:
    out = []
    for path in _logs(vault, today):
        for raw in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
            try:
                r = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(r, dict):
                out.append(r)
    return out


def _append(vault, today: str, record: dict) -> None:
    path = _logs(vault, today)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


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
    source is mail."""
    ticks = [r.get("epoch") for r in records(vault, today) if r.get("kind") == "tick"
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


def _structured(b, m) -> dict:
    tur = m.get("tool_use_result")
    sc = tur.get("structuredContent") if isinstance(tur, dict) else None
    return sc if isinstance(sc, dict) else {}


def _text_json(b, m) -> dict:
    """The Slack search answers in text only: one JSON object with the markdown results and the pagination line."""
    content = b.get("content")
    text = "".join(c.get("text", "") for c in content if isinstance(c, dict)) if isinstance(content, list) else str(content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    return data if isinstance(data, dict) else {}


def pages(stream, tool: str, same, take, max_pages: int, server: str) -> tuple:
    """(each search result's payload from take(block, message), the result message), after the tool-use and error
    checks: only ToolSearch and the search, each search input passing same(input)."""
    calls, out, errors, named = {}, [], [], False
    for m in stream:
        if m.get("type") == "assistant":
            for b in blocks(m, "tool_use"):
                if b.get("name") not in ("ToolSearch", tool):
                    raise Fail(7, f"the session used an unexpected tool: {b.get('name')}")
                i = b.get("input") if isinstance(b.get("input"), dict) else {}
                if b.get("name") == tool and not same(i):
                    raise Fail(7, "the session searched with another query than the one built for this tick")
                calls[b.get("id")] = b
        if m.get("type") == "user":
            for b in blocks(m, "tool_result"):
                call = calls.get(b.get("tool_use_id")) or {}
                content = b.get("content")
                if call.get("name") == "ToolSearch" and isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("tool_name") == tool for c in content):
                    named = True
                if call.get("name") != tool:
                    continue
                if b.get("is_error"):
                    errors.append(json.dumps(content)[:200])
                    continue
                out.append(take(b, m))
    result = next((m for m in reversed(stream) if m.get("type") == "result"), None)
    if result is None:
        raise Fail(1, "claude produced no result")
    if errors:
        raise Fail(6, f"the connector returned an error: {errors[0]}")
    if not any(c.get("name") == tool for c in calls.values()):
        raise Fail(1 if named else 3, f"the session never called {tool}" if named else f"no {server} connector reachable")
    if result.get("is_error") or result.get("subtype") != "success":
        raise Fail(1, f"claude returned an error result ({result.get('subtype')})")
    if len(out) > max_pages:
        raise Fail(7, f"the session searched {len(out)} pages; the limit is {max_pages}")
    return out, result


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
    """{"items": [...], "full": bool}: the threads the session marked, joined to the search results."""
    got, result = pages(stream, TOOL, lambda i: i.get("query") == q, _structured, MAX_PAGES, "Gmail")
    known = threads(got)
    items, seen = [], set()
    for r in reply(result):
        tid = r.get("thread_id")
        if not isinstance(tid, str) or tid not in known or tid in seen:
            continue  # a thread id the search never returned is dropped
        seen.add(tid)
        t = known[tid]
        ask = one_line(r.get("ask"))
        if not ask:
            continue
        items.append({"thread_id": tid, "date": t["date"], "link": t["link"], "sender": address(t["sender"]),
                      "who": one_line(r.get("who")) or address(t["sender"]), "ask": ask,
                      "next_step": one_line(r.get("next_step"))})
    full = len(got) == MAX_PAGES and bool(got[-1].get("nextPageToken"))
    return {"items": items, "full": full}


def chat_messages(got: list, notify_channel: str) -> dict:
    """"<channel id>/<ts>" -> {link, date, sender, channel}, from the search results' markdown only. A result in the
    notify channel is skipped: notices post as the owner, and triage must not read its own back."""
    out = {}
    for page in got:
        for part in str(page.get("results") or "").split("### Result ")[1:]:
            f = {k: rx.search(part) for k, rx in CHAT_FIELDS.items()}
            if not (f["channel"] and f["ts"] and f["link"]):
                raise Fail(1, "a chat result lacks a channel, a ts or a link")
            if f["channel"].group(2) == notify_channel:
                continue
            out[f"{f['channel'].group(2)}/{f['ts'].group(1)}"] = {
                "link": f["link"].group(1), "date": f["ts"].group(1), "channel": f["channel"].group(1),
                "sender": f["sender"].group(1) if f["sender"] else ""}
    return out


def chat_extract(stream, q: dict, tool: str, notify_channel: str) -> dict:
    """extract() for the Slack search: each search input is q, with only a cursor added on later pages. Items take
    the mail item's shape (thread_id "<channel id>/<ts>"), so record() writes both."""
    got, result = pages(stream, tool, lambda i: {k: v for k, v in i.items() if k != "cursor"} == q, _text_json,
                        CHAT_MAX_PAGES, "Slack")
    known = chat_messages(got, notify_channel)
    items = []
    for r in reply(result):
        key = f"{r.get('channel_id')}/{r.get('ts')}"
        ask = one_line(r.get("ask"))
        if key not in known or ask == "" or key in {i["thread_id"] for i in items}:
            continue  # a message the search never returned is dropped
        m = known[key]
        items.append({"thread_id": key, "date": m["date"], "link": m["link"], "sender": address(m["sender"]),
                      "who": f"{one_line(r.get('who')) or address(m['sender'])} in #{one_line(m['channel'])}",
                      "ask": ask, "next_step": one_line(r.get("next_step"))})
    full = len(got) == CHAT_MAX_PAGES and "cursor" in str(got[-1].get("pagination_info") or "")
    return {"items": items, "full": full}


def record(vault, partition: str, found: dict, today: str, now_iso: str, now_epoch: int, source: str = "mail") -> list:
    """Add a Now line for each item whose (thread, latest message) is new to its source, then record the tick. The
    caller holds run.lock. Returns the lines added."""
    known = {(r.get("thread_id"), r.get("date")) for r in records(vault, today)
             if r.get("kind") == "item" and r.get("source", "mail") == source}
    added = []
    for i in found.get("items") or []:
        if (i["thread_id"], i["date"]) in known:
            continue
        statement = f"{i['who']}: {i['ask'].rstrip('.')}." + (f" Next: {i['next_step']}" if i.get("next_step") else "")
        try:
            status, line = nowmod.add(vault, partition, "owed", statement, today, i["sender"], i["link"])
        except ValueError:  # a link or sender the Now line cannot hold: keep the item, drop the metadata
            status, line = nowmod.add(vault, partition, "owed", f"{statement} ({i['link']})", today)
        _append(vault, today, {"kind": "item", "thread_id": i["thread_id"], "date": i["date"], "line": line,
                               "time": now_iso, "source": source})
        known.add((i["thread_id"], i["date"]))
        if status == "added":
            added.append(f"{i['who']}: {i['ask']}")
    _append(vault, today, {"kind": "tick", "epoch": now_epoch, "time": now_iso, "items": len(added),
                           "full": bool(found.get("full")), "source": source})
    return added
