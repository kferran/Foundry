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

from vaultlib.notify import prefix

from .common import Fail, QUERIES, config, load, partition, save, state, truthy

SLACK_TOOL = "slack_search_public_and_private"
GMAIL_TOOL = "mcp__claude_ai_Gmail__search_threads"
OVERLAP_SECONDS = 300
FIRST_LOOKBACK_SECONDS = 2 * 3600
SLACK_ID = re.compile(r"[CGD][A-Z0-9]{2,}")
USER_ID = re.compile(r"[UW][A-Z0-9]{2,}")
COMMON = {"sort": "timestamp", "limit": 20, "include_bots": False, "include_context": False,
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
        if capture == str(cfg.get("slack_notify_channel") or ""):
            raise Fail(2, "capture_channel is slack_notify_channel: the capture would copy the Foundry's own notices")
        if "capture" in cur:
            date, after = _after(cur["capture"] - OVERLAP_SECONDS)
            out["capture"] = {"filters": f"in:<#{capture}> {date}", "after": after, **COMMON}
    return {n: out[n] for n in QUERIES if n in out}


def first_capture(vault) -> bool:
    """True when a capture channel is set and has no cursor yet: this tick only sets it."""
    return bool(config(vault).get("capture_channel")) and "capture" not in cursors(vault)


def mail(vault, now_epoch: int) -> str:
    """The sent-mail query since the last mail tick, or "" when watch_commitments_mail is off."""
    if not truthy(config(vault).get("watch_commitments_mail"), True):
        return ""
    partition(vault)
    cur = cursors(vault)
    after = cur["mail"] - OVERLAP_SECONDS if "mail" in cur else now_epoch - FIRST_LOOKBACK_SECONDS
    return f"in:sent after:{after}"
