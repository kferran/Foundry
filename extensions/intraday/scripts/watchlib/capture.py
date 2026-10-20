"""Capture files (phase D spec §3.7): one raw/inbox/ drop per tick with new messages in the capture channel. The text
is the search result's, copied as Slack sent it; the intake redacts, compiles and archives the file."""
import re
from datetime import datetime
from pathlib import Path

from vaultlib.notify import thread_state

from .common import config


def keep(vault, messages: list) -> list:
    """With the capture channel the notify channel (notices in a daily thread, #293): every Foundry post is dropped by
    its recorded ts, a reply only in a Foundry daily thread is kept (its permalink names its thread_ts), and it carries
    the Foundry post just above it in that thread as context."""
    cfg = config(vault)
    if str(cfg.get("capture_channel") or "") != str(cfg.get("slack_notify_channel") or ""):
        return messages
    state = thread_state(vault)
    posts, parents = state["posts"], set(state["parents"].values())
    out = []
    for m in messages:
        thread = re.search(r"[?&]thread_ts=(\d+\.\d+)", m["link"])
        thread = thread.group(1) if thread and thread.group(1) != m["ts"] else ""
        if m["ts"] in posts or (thread and thread not in parents):
            continue
        above = [t for t, p in posts.items() if thread and thread in (t, p.get("thread")) and float(t) < float(m["ts"])]
        out.append({**m, "context": str(posts[max(above, key=float)].get("text") or "") if above else ""})
    return out


def render(messages: list, partition: str, channel: str, captured_at: str, tz) -> str:
    lines = ["---", f'partition: "{partition}"', 'source: "slack"', f'channel: "{channel}"',
             f'captured_at: "{captured_at}"', "---", ""]
    for m in messages:
        clock = datetime.fromtimestamp(float(m["ts"]), tz).strftime("%H:%M")
        lines += [f"## {clock} {m['sender'] or 'unknown'}", "", m["text"] or "(no text)", ""]
        if m.get("context"):
            lines += ["In reply to the Foundry notice:", "", *(f"> {x}" for x in m["context"].splitlines()), ""]
        lines += [f"Link: {m['link']}", ""]
    return "\n".join(lines)


def write(vault, messages: list, partition: str, channel: str, now: datetime) -> Path:
    """Write the file (a unique name under raw/inbox/) and return its path; the caller moves the cursor after."""
    inbox = Path(vault) / "raw" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    stem = f"slack-{now.strftime('%Y-%m-%dT%H%M%S')}"
    path, n = inbox / f"{stem}.md", 1
    while path.exists():
        n += 1
        path = inbox / f"{stem}-{n}.md"
    tmp = inbox / f".{path.name}.tmp"
    tmp.write_text(render(messages, partition, channel, now.isoformat(timespec="seconds"), now.tzinfo), encoding="utf-8")
    tmp.rename(path)
    return path
