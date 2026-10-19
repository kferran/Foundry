"""Capture files (phase D spec §3.7): one raw/inbox/ drop per tick with new messages in the capture channel. The text
is the search result's, copied as Slack sent it; the intake redacts, compiles and archives the file."""
from datetime import datetime
from pathlib import Path


def render(messages: list, partition: str, channel: str, captured_at: str, tz) -> str:
    lines = ["---", f'partition: "{partition}"', 'source: "slack"', f'channel: "{channel}"',
             f'captured_at: "{captured_at}"', "---", ""]
    for m in messages:
        clock = datetime.fromtimestamp(float(m["ts"]), tz).strftime("%H:%M")
        lines += [f"## {clock} {m['sender'] or 'unknown'}", "", m["text"] or "(no text)", "", f"Link: {m['link']}", ""]
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
