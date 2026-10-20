"""The check of a watch session's stream (phase D spec §3.2, §3.3).

A session may call only ToolSearch and its one search tool, and each search input must be one this tick built (a
later page adds only `cursor`). Links, times, senders and captured text come from the search results; from the
model's reply only the message key, the kind and four short texts are used, and an item whose message its query
never returned is dropped.
"""
import json
import re

from vaultlib import now as nowmod
from vaultlib.stream import blocks
from vaultlib.triage import _structured, _text_json, one_line, reply

from .common import CHANGES, INBOUND_KINDS, WATCH_KINDS, Fail

MAX_PAGES = 5
MAIL_PAGES = 3
FIELDS = {"channel": re.compile(r"^Channel: (?:#([\w-]+)|(Group DM|DM)) \(ID: ([CGD][A-Z0-9]+)\)", re.M),
          "sender": re.compile(r"^From: (.*?) \(ID: ([A-Z0-9]+)\)", re.M),
          "ts": re.compile(r"^Message_ts: (\d+\.\d+)", re.M),
          "link": re.compile(r"^Permalink: \[[^\]]*\]\((https://[^)\s]+)\)", re.M),
          "text": re.compile(r"^Text:[ \t]*\n?(.*?)(?:\n---[ \t]*(?:\n|$)|\Z)", re.M | re.S)}
TEXT_MAX = 4000


def _strip_cursor(i: dict) -> dict:
    return {k: v for k, v in i.items() if k != "cursor"}


def query_pages(stream, tool: str, queries: dict, name_of=None, take=_text_json, limit=MAX_PAGES,
                server="Slack") -> tuple:
    """({query name: [page payloads]}, the result message) after the tool-use and error checks. name_of(input) names
    the built query a search input runs (by default: the Slack input itself, less a later page's cursor)."""
    name_of = name_of or (lambda i: next((n for n, q in queries.items() if _strip_cursor(i) == q), None))
    calls, pages, errors, named = {}, {n: [] for n in queries}, [], False
    for m in stream:
        if m.get("type") == "assistant":
            for b in blocks(m, "tool_use"):
                if b.get("name") not in ("ToolSearch", tool):
                    raise Fail(7, f"the session used an unexpected tool: {b.get('name')}")
                if b.get("name") == tool:
                    name = name_of(b.get("input") if isinstance(b.get("input"), dict) else {})
                    if name is None:
                        raise Fail(7, "the session searched with another query than the ones built for this tick")
                    b = {**b, "query": name}
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
                if "<persisted-output>" in json.dumps(content):
                    raise Fail(6, "a search result was too large for the stream; lower limit in watchlib/query.py")
                pages[call["query"]].append(take(b, m))
    result = next((m for m in reversed(stream) if m.get("type") == "result"), None)
    if result is None:
        raise Fail(1, "claude produced no result")
    if errors:
        raise Fail(6, f"the connector returned an error: {errors[0]}")
    if not any(c.get("name") == tool for c in calls.values()):
        raise Fail(1 if named else 3, f"the session never called {tool}" if named else f"no {server} connector reachable")
    if result.get("is_error") or result.get("subtype") != "success":
        raise Fail(1, f"claude returned an error result ({result.get('subtype')})")
    for name, got in pages.items():
        if len(got) > limit:
            raise Fail(7, f"the session read {len(got)} pages of the {name} search; the limit is {limit}")
    return pages, result


def label(kind: str, name: str) -> str:
    return f"#{name}" if name else ("group DM" if kind == "Group DM" else "DM")


def messages(got: list, notify: str = "") -> dict:
    """"<channel id>/<ts>" -> {link, ts, channel, label, sender, sender_id, text}, from the results' markdown only.
    A piece counts only when its link is that message's own permalink, and the first piece for a message wins (its
    real header comes before its text, which may quote another result's). A result in the notify channel is skipped,
    as chat triage does: the Foundry's notices post as the owner."""
    out = {}
    for page in got:
        results = page.get("results")
        if not isinstance(results, str):
            raise Fail(1, "a Slack search result is not in the shape asked for")
        parsed = 0
        for part in results.split("### Result ")[1:]:
            f = {k: rx.search(part) for k, rx in FIELDS.items()}
            if not (f["channel"] and f["ts"] and f["link"]):
                continue
            cid, ts, link = f["channel"].group(3), f["ts"].group(1), f["link"].group(1)
            if not re.match(rf"https://(?:[a-z0-9-]+\.)+slack\.com/archives/{cid}/p{ts.replace('.', '')}(?:\?|$)", link):
                continue
            parsed += 1
            if cid == notify or f"{cid}/{ts}" in out:
                continue
            out[f"{cid}/{ts}"] = {"link": link, "ts": ts, "channel": cid,
                                  "label": label(f["channel"].group(2) or "", f["channel"].group(1) or ""),
                                  "sender": f["sender"].group(1) if f["sender"] else "",
                                  "sender_id": f["sender"].group(2) if f["sender"] else "",
                                  "text": (f["text"].group(1).strip() if f["text"] else "")[:TEXT_MAX]}
        listed = re.search(r"^## Messages \((\d+) results?\)", results, re.M)
        if listed and int(listed.group(1)) > 0 and parsed == 0:
            raise Fail(1, "a Slack search result is not in the shape asked for")
    return out


def _who(text) -> str:
    return re.sub(r"[(),]", "", one_line(text))[:80]


def _by(value) -> str:
    value = str(value or "")
    return value if nowmod.is_date(value) else ""


def slack_extract(stream, tool: str, queries: dict, notify: str = "") -> dict:
    """{"items": [...], "captures": [...], "full": [query names]}: the classified watch and own messages joined to
    the results, and every message of the capture search (never classified)."""
    pages, result = query_pages(stream, tool, queries)
    known = {n: messages(got, notify) for n, got in pages.items()}
    items, seen = [], set()
    for r in reply(result):
        q, key = r.get("query"), f"{r.get('channel_id')}/{r.get('ts')}"
        kinds = ("commitment",) if q == "own" else WATCH_KINDS if q in ("watch", "mpim") else ()
        if r.get("kind") not in kinds or key not in known.get(q, {}) or (q, key) in seen:
            continue  # a message its query never returned, or a kind that query cannot give, is dropped
        what = one_line(r.get("what"))
        if not what:
            continue
        seen.add((q, key))
        m = known[q][key]
        sender = "" if r["kind"] == "blocked" else _who(m["sender"])   # a block waits on someone, not its poster
        items.append({"query": q, "key": key, "kind": r["kind"], "what": what, "who": _who(r.get("who")) or sender,
                      "by": _by(r.get("by")), "meeting": r.get("meeting") is True,
                      "change": r.get("change") if r.get("change") in CHANGES else "other",
                      "link": m["link"], "ts": m["ts"], "label": m["label"], "text": m["text"]})
    captures = sorted(known.get("capture", {}).values(), key=lambda m: float(m["ts"]))
    full = [n for n, got in pages.items() if got and "use cursor `" in str(got[-1].get("pagination_info") or "")]
    # Results come oldest first (sort_dir asc), so a search cut at its page limit resumes from its last message read.
    resume = {n: int(max(float(m["ts"]) for m in known[n].values())) for n in full if known[n]}
    return {"items": items, "captures": captures, "full": full, "resume": resume}


def sent_threads(got: list, since: int = 0, sent: bool = True) -> dict:
    """thread id -> {link, date (epoch ms of its latest sent message, or with sent=False its latest incoming one), and
    that message's sender and subject}, from the search results only; a thread whose such messages are all older than
    `since` (epoch seconds) is left out (spec §3.3)."""
    out = {}
    for sc in got:
        listed = sc.get("threads", [])
        if not isinstance(listed, list):
            raise Fail(1, "the mail search result carries no threads list")
        for t in listed:
            msgs = [m for m in (t.get("messages") or []) if isinstance(m, dict)] if isinstance(t, dict) else []
            if not (isinstance(t, dict) and isinstance(t.get("id"), str) and str(t.get("viewUrl", "")).startswith("https://")):
                raise Fail(1, "a thread lacks an id or a link")
            msgs = [m for m in msgs if ("SENT" in (m.get("labelIds") or [])) == sent
                    and "DRAFT" not in (m.get("labelIds") or [])
                    and str(m.get("internalDate", "")).isdigit() and int(m["internalDate"]) >= since * 1000]
            if msgs:
                latest = max(msgs, key=lambda m: int(m["internalDate"]))
                out[t["id"]] = {"link": t["viewUrl"], "date": str(latest["internalDate"]),
                                "sender": str(latest.get("sender") or ""), "subject": str(latest.get("subject") or ""),
                                "snippet": str(latest.get("snippet") or "")}
    return out


def _sender(raw: str) -> tuple:
    """(display name, lower-case address) of a message's sender, "Name <a@b>" or "a@b"."""
    m = re.search(r"<([^<>\s]+@[^<>\s]+)>", raw)
    addr = (m.group(1) if m else raw.strip()).lower()
    return (raw[:m.start()].strip().strip('"') if m else ""), (addr if "@" in addr else "")


def _rule_hit(pattern: str, addr: str) -> bool:
    """An address pattern matches that address; a domain (@example.com or example.com) it and its subdomains."""
    if "@" in pattern and not pattern.startswith("@"):
        return addr == pattern
    domain, host = pattern.lstrip("@"), addr.rpartition("@")[2]
    return bool(addr) and (host == domain or host.endswith("." + domain))


DROPS = ("unknown_thread", "wrong_kind", "empty_what", "duplicate")
SUBJECT_SCAN = 1000   # ponytail: the owner's regex runs on at most this much of a subject; Python's re has no timeout


def mail_extract(stream, queries: dict, rules=()) -> dict:
    """{"items": [...], "full": [query names], "stats": {query name: counts}}: the sent-mail commitments and the
    incoming requests, incidents and deadlines, each joined to the threads its own search returned, plus each incoming
    thread whose latest incoming message matches one of `rules` (query.inbound_rules). stats counts, per search, the
    threads returned, those with a message at or after the cursor (fresh), the reply's rows, the rows kept, the threads
    a rule matched, the rows dropped by reason and the dropped rows' kinds (cut to 20 safe characters)."""
    from .query import GMAIL_TOOL
    names = {q: n for n, q in queries.items()}
    pages, result = query_pages(stream, GMAIL_TOOL, queries,
                                lambda i: names.get(i.get("query")) if i.get("view") == "THREAD_VIEW_MINIMAL" else None,
                                _structured, MAIL_PAGES, "Gmail")
    for name, got in pages.items():
        if not got:   # its cursor would move past mail no one read
            raise Fail(1, f"the session never ran the {name} search")
    known = {}
    for name, got in pages.items():
        since = re.search(r"after:(\d+)", queries[name])
        known[name] = sent_threads(got, int(since.group(1)) if since else 0, sent=name == "mail")
    stats = {n: {"threads": sum(len(p.get("threads") or []) for p in got), "fresh": len(known[n]), "rows": 0,
                 "kept": 0, "rules": 0, "dropped": dict.fromkeys(DROPS, 0), "dropped_kinds": set()}
             for n, got in pages.items()}
    items, seen = {}, set()
    for r in reply(result):
        tid, what, kind = r.get("thread_id"), one_line(r.get("what")), r.get("kind")
        q = "mail" if kind == "commitment" else "inbound" if kind in INBOUND_KINDS else ""
        # A row counts under the search its kind belongs to, else the one that returned its thread, else the first.
        s = stats[q if q in stats else next((n for n in stats if tid in known[n]), next(iter(stats)))]
        s["rows"] += 1
        why = ("wrong_kind" if q not in known else "unknown_thread" if tid not in known[q] else "empty_what" if not what
               else "duplicate" if (q, tid) in seen else "")
        if why:
            s["dropped"][why] += 1
            s["dropped_kinds"].add(re.sub(r"[^A-Za-z0-9_-]", "", str(kind))[:20])
            continue
        s["kept"] += 1
        seen.add((q, tid))
        t = known[q][tid]
        items[q, tid] = {"query": q, "key": f"{tid}/{t['date']}", "kind": kind, "what": what,
                         "who": _who(r.get("who")), "by": _by(r.get("by")), "meeting": q == "mail" and r.get("meeting") is True,
                         "change": "other", "link": t["link"], "ts": t["date"], "label": "mail", "text": ""}
    for tid, t in known.get("inbound", {}).items():
        name, addr = _sender(t["sender"])
        kind = next((k for p, subj, snip, k in rules if _rule_hit(p, addr)
                     and all(rx is None or rx.search(t[f][:SUBJECT_SCAN]) for f, rx in (("subject", subj), ("snippet", snip)))),
                    None)
        if kind is None:
            continue
        stats["inbound"]["rules"] += 1
        if ("inbound", tid) in items:   # the model's row stays, with the rule's kind
            items["inbound", tid]["kind"] = kind
            continue
        what = one_line(t["subject"])
        if what:
            items["inbound", tid] = {"query": "inbound", "key": f"{tid}/{t['date']}", "kind": kind, "what": what,
                                     "who": _who(name or addr), "by": "", "meeting": False, "change": "other",
                                     "link": t["link"], "ts": t["date"], "label": "mail", "text": ""}
    for s in stats.values():
        s["dropped_kinds"] = sorted(s["dropped_kinds"])[:10]
    # No ascending sort: a search that fills its pages leaves its oldest threads unread (spec §3.3).
    full = [n for n, got in pages.items() if len(got) == MAIL_PAGES and got[-1].get("nextPageToken")]
    return {"items": list(items.values()), "captures": [], "full": full, "stats": stats}
