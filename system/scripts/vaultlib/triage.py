"""Inbox triage (inbox triage spec): the Gmail query, the check of a triage_fetch.sh session, and the write.

The session may call only the Gmail thread search. Each item's link, date and sender come from the search results,
paired with the call by tool_use_id; from the model's reply only the thread id and three short texts are used, and a
thread id the search never returned is dropped.
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from . import frontmatter
from . import nightshift_sched as ns
from . import now as nowmod
from .stream import blocks

TOOL = "mcp__claude_ai_Gmail__search_threads"
EXCLUDE = "-category:promotions -category:social -category:forums -from:me"
MAX_PAGES = 3
OVERLAP_SECONDS = 300
FIRST_LOOKBACK_SECONDS = 2 * 3600
TEXT_MAX = 160
HEALTH_DIR = "system/logs/nightshift"


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


def query(vault, now_epoch: int, today: str) -> str:
    """Mail since the last successful tick (with an overlap), or the last two hours on the first run."""
    ticks = [r.get("epoch") for r in records(vault, today) if r.get("kind") == "tick" and isinstance(r.get("epoch"), int)]
    after = max(ticks) - OVERLAP_SECONDS if ticks else now_epoch - FIRST_LOOKBACK_SECONDS
    return f"in:inbox after:{after} {EXCLUDE}"


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


def pages(stream, q: str) -> tuple:
    """(the structuredContent of each search result, the result message), after the tool-use and error checks."""
    calls, out, errors, named = {}, [], [], False
    for m in stream:
        if m.get("type") == "assistant":
            for b in blocks(m, "tool_use"):
                if b.get("name") not in ("ToolSearch", TOOL):
                    raise Fail(7, f"the session used an unexpected tool: {b.get('name')}")
                i = b.get("input") if isinstance(b.get("input"), dict) else {}
                if b.get("name") == TOOL and i.get("query") != q:
                    raise Fail(7, "the session searched with another query than the one built for this tick")
                calls[b.get("id")] = b
        if m.get("type") == "user":
            for b in blocks(m, "tool_result"):
                call = calls.get(b.get("tool_use_id")) or {}
                content = b.get("content")
                if call.get("name") == "ToolSearch" and isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("tool_name") == TOOL for c in content):
                    named = True
                if call.get("name") != TOOL:
                    continue
                if b.get("is_error"):
                    errors.append(json.dumps(content)[:200])
                    continue
                tur = m.get("tool_use_result")
                sc = tur.get("structuredContent") if isinstance(tur, dict) else None
                out.append(sc if isinstance(sc, dict) else {})
    result = next((m for m in reversed(stream) if m.get("type") == "result"), None)
    if result is None:
        raise Fail(1, "claude produced no result")
    if errors:
        raise Fail(6, f"the connector returned an error: {errors[0]}")
    if not any(c.get("name") == TOOL for c in calls.values()):
        raise Fail(1 if named else 3, f"the session never called {TOOL}" if named else "no Gmail connector reachable")
    if result.get("is_error") or result.get("subtype") != "success":
        raise Fail(1, f"claude returned an error result ({result.get('subtype')})")
    if len(out) > MAX_PAGES:
        raise Fail(7, f"the session searched {len(out)} pages; the limit is {MAX_PAGES}")
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
            latest = max(msgs, key=lambda m: str(m.get("date", "")))
            out[t["id"]] = {"link": t["viewUrl"], "date": str(latest.get("date", "")), "sender": str(latest.get("sender", ""))}
    return out


def one_line(text) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip().replace("[", "(").replace("]", ")")
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
    got, result = pages(stream, q)
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


def record(vault, partition: str, found: dict, today: str, now_iso: str, now_epoch: int) -> list:
    """Add a Now line for each item whose (thread, latest message) is new, then record the tick. The caller holds
    run.lock. Returns the lines added."""
    known = {(r.get("thread_id"), r.get("date")) for r in records(vault, today) if r.get("kind") == "item"}
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
                               "time": now_iso})
        known.add((i["thread_id"], i["date"]))
        if status == "added":
            added.append(f"{i['who']}: {i['ask']}")
    _append(vault, today, {"kind": "tick", "epoch": now_epoch, "time": now_iso, "items": len(added),
                           "full": bool(found.get("full"))})
    return added
