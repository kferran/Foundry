"""The tick's search inputs, built only from settings and cursors (phase D spec §3.2, §3.3).

Each query keeps its own cursor in system/logs/watch/cursors.json: the epoch its last successful tick started at. A
query reads from its cursor minus an overlap (the item ledger drops repeats), or two hours back on its first tick.
The capture query has no lookback: its first tick sets the cursor and reads nothing, so old history never becomes
inbox input. Slack reads a date filter in the owner's timezone, so each date filter reaches two days before the
cursor and the epoch `after` bounds it, as chat triage does (the probe of 2026-10-19 found that a repeated `in:` is
an OR and that a filter-only search still needs one filter).
"""
import re
from datetime import datetime, timedelta, timezone

from vaultlib.api import prefix

from .common import Fail, QUERIES, config, load, partition, save, state, truthy

SLACK_TOOL = "slack_search_public_and_private"
GMAIL_TOOL = "mcp__claude_ai_Gmail__search_threads"
OVERLAP_SECONDS = 300
FIRST_LOOKBACK_SECONDS = 2 * 3600
SLACK_ID = re.compile(r"[CGD][A-Z0-9]{2,}")
USER_ID = re.compile(r"[UW][A-Z0-9]{2,}")
LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
SKIP = re.compile(rf"(?:[A-Za-z0-9._%+-]*@)?{LABEL}(?:\.{LABEL})+")   # it enters the search: no space, colon or bracket
INBOUND = "-in:sent -category:promotions -category:social -category:forums"
RULE_KINDS = ("request", "incident", "deadline")
RULE_MAX = 200
REPLAY_MAX_SECONDS = 7 * 86400
COMMON = {"sort": "timestamp", "sort_dir": "asc", "limit": 20, "include_bots": False, "include_context": False,
          "response_format": "detailed", "content_types": "messages"}


def cursors(vault) -> dict:
    data = load(state(vault) / "cursors.json", {})
    return {k: v for k, v in data.items() if isinstance(v, int)} if isinstance(data, dict) else {}


def advance(vault, names, epoch: int) -> None:
    """Move the named queries' cursors to the tick's start epoch."""
    data = cursors(vault)
    data.update({n: epoch for n in names})
    save(state(vault) / "cursors.json", data)


def slack_tool(vault) -> str:
    return prefix(str(config(vault).get("slack_connector") or "claude.ai Slack")) + "__" + SLACK_TOOL


def channels(vault) -> list:
    """watch_channels as (id, label); each id checked before it reaches a query."""
    value = config(vault).get("watch_channels") or []
    out = []
    for c in value if isinstance(value, list) else []:
        cid = str(c.get("id", "")) if isinstance(c, dict) else ""
        if not SLACK_ID.fullmatch(cid):
            raise Fail(2, f"watch_channels: {cid!r} is not a Slack channel ID")
        out.append((cid, str(c.get("label") or cid)))
    return out


def _after(cursor_epoch: int) -> tuple:
    day = datetime.fromtimestamp(cursor_epoch, timezone.utc).date() - timedelta(days=2)
    return f"after:{day}", str(cursor_epoch)


def slack(vault, now_epoch: int) -> dict:
    """{query name: search input} for this tick, in QUERIES order. An empty dict means no Slack session runs."""
    cfg, cur, out = config(vault), cursors(vault), {}
    partition(vault)   # a bad watch_partition stops the tick before a session runs, not after

    def since(name):
        return cur[name] - OVERLAP_SECONDS if name in cur else now_epoch - FIRST_LOOKBACK_SECONDS

    ids = channels(vault)
    if ids:
        date, after = _after(since("watch"))
        out["watch"] = {"filters": " ".join(f"in:<#{cid}>" for cid, _ in ids) + f" {date}", "after": after, **COMMON}
    if truthy(cfg.get("watch_group_dms"), True):
        date, after = _after(since("mpim"))
        out["mpim"] = {"filters": date, "channel_types": "mpim", "after": after, **COMMON}
    user = str(cfg.get("watch_user_id") or "")
    if user:
        if not USER_ID.fullmatch(user):
            raise Fail(2, f"watch_user_id: {user!r} is not a Slack user ID")
        date, after = _after(since("own"))
        out["own"] = {"filters": f"from:<@{user}> {date}", "after": after, **COMMON}
    capture = str(cfg.get("capture_channel") or "")
    if capture:
        if not SLACK_ID.fullmatch(capture):
            raise Fail(2, f"capture_channel: {capture!r} is not a Slack channel ID")
        # #293: with notices in a daily thread the notify channel is also the capture channel, read for the owner's
        # posts only; capture.keep drops Foundry's own by their recorded ts.
        shared = capture == str(cfg.get("slack_notify_channel") or "")
        if shared and cfg.get("slack_notify_thread") != "daily":
            raise Fail(2, "capture_channel is slack_notify_channel: the capture would copy the Foundry's own notices "
                          "(set slack_notify_thread: daily to share the channel)")
        if shared and not user:
            raise Fail(2, "capture_channel is slack_notify_channel: set watch_user_id, whose posts it captures")
        if "capture" in cur:
            date, after = _after(cur["capture"] - OVERLAP_SECONDS)
            owner = f" from:<@{user}>" if shared else ""
            out["capture"] = {"filters": f"in:<#{capture}>{owner} {date}", "after": after, **COMMON}
    return {n: out[n] for n in QUERIES if n in out}


def first_capture(vault) -> bool:
    """True when a capture channel is set and has no cursor yet: this tick only sets it."""
    return bool(config(vault).get("capture_channel")) and "capture" not in cursors(vault)


def inbound_rules(vault) -> list:
    """watch_inbound_rules as (from, subject regex or None, snippet regex or None, kind): the incoming threads that
    become items without the model. Each rule is checked before a session runs."""
    value = config(vault).get("watch_inbound_rules") or []
    if not isinstance(value, list):
        raise Fail(2, "watch_inbound_rules must be a list of {from, subject, snippet, kind}")
    out = []
    for n, r in enumerate(value):
        where = f"watch_inbound_rules[{n}]"
        if not (isinstance(r, dict) and {"from", "kind"} <= set(r) <= {"from", "subject", "snippet", "kind"}
                and ("subject" in r or "snippet" in r)):
            raise Fail(2, f"{where}: a rule holds from, kind and a subject or a snippet regex (or both), nothing else")
        sender, kind = r["from"], r["kind"]
        if not (isinstance(sender, str) and len(sender) <= RULE_MAX and SKIP.fullmatch(sender)):
            raise Fail(2, f"{where}: from {sender!r} is not an address or a domain (@example.com or example.com)")
        rxs = {}
        for field in ("subject", "snippet"):
            if field not in r:
                rxs[field] = None
                continue
            pattern = r[field]
            if not (isinstance(pattern, str) and 0 < len(pattern) <= RULE_MAX):
                raise Fail(2, f"{where}: {field} must be a regex of 1 to {RULE_MAX} characters")
            try:
                rxs[field] = re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise Fail(2, f"{where}: {field} {pattern!r} is not a valid regex ({exc})")
        if kind not in RULE_KINDS:
            raise Fail(2, f"{where}: kind must be {', '.join(RULE_KINDS)}, not {kind!r}")
        out.append((sender.lower(), rxs["subject"], rxs["snippet"], kind))
    return out


def mail(vault, now_epoch: int, inbound_since=None) -> dict:
    """{query name: Gmail query} for the one mail session, each since its own cursor: `mail`, the owner's sent mail
    (watch_commitments_mail), and `inbound`, incoming mail less the senders in watch_inbound_skip (watch_inbound_mail).
    inbound_since (--inbound-since, a replay) is an epoch of the last 7 days the incoming search reads from instead.
    An empty dict means no mail session runs."""
    cfg, cur, out = config(vault), cursors(vault), {}
    partition(vault)

    def since(name):
        return cur[name] - OVERLAP_SECONDS if name in cur else now_epoch - FIRST_LOOKBACK_SECONDS

    if inbound_since is not None:
        s = str(inbound_since)
        if not (s.isdigit() and now_epoch - REPLAY_MAX_SECONDS <= int(s) <= now_epoch):
            raise Fail(2, f"--inbound-since {s!r} is not an epoch in seconds from the last 7 days")
        if not truthy(cfg.get("watch_inbound_mail"), True):
            raise Fail(2, "--inbound-since needs watch_inbound_mail on")
    if truthy(cfg.get("watch_commitments_mail"), True):
        out["mail"] = f"in:sent after:{since('mail')}"
    if truthy(cfg.get("watch_inbound_mail"), True):
        skip = cfg.get("watch_inbound_skip") or []
        skip = skip if isinstance(skip, list) else [skip]
        for s in skip:
            if not (isinstance(s, str) and SKIP.fullmatch(s)):
                raise Fail(2, f"watch_inbound_skip: {s!r} is not an address or a domain (@example.com or example.com)")
        inbound_rules(vault)
        after = int(inbound_since) if inbound_since is not None else since("inbound")
        out["inbound"] = " ".join([INBOUND, f"after:{after}", *(f"-from:{s}" for s in skip)])
    return out
