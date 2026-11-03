"""Recall R1 (#438): the excerpt a backfilled digest is written from, and the frontmatter it must carry (spec §4.3)."""
import json
from pathlib import Path

EXCERPT_CAP = 100_000
LINE_CAP = 2 * 1024 * 1024


def _entries(path: Path):
    """The transcript's user and assistant entries, sidechains (subagents) left out. A line over LINE_CAP is skipped
    unparsed, without holding more than LINE_CAP of it in memory; a line that is not a JSON object is skipped."""
    with open(path, "rb") as fh:
        while line := fh.readline(LINE_CAP + 1):
            if len(line) > LINE_CAP:
                while line and not line.endswith(b"\n"):
                    line = fh.readline(LINE_CAP)
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get("type") in ("user", "assistant") and not entry.get("isSidechain"):
                yield entry


def _render(entry: dict, cwd: str):
    """Prompts and assistant text as they are, each tool call as one line; tool results and thinking are dropped.
    A file path under the session's cwd is shown relative to it, so a long absolute path is not redacted as a key."""
    ts, role = str(entry.get("timestamp", "")), entry["type"]
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        yield f"[{ts}] {role}: {content}"
        return
    for block in content if isinstance(content, list) else []:
        kind = block.get("type") if isinstance(block, dict) else None
        if kind == "text":
            yield f"[{ts}] {role}: {block.get('text', '')}"
        elif kind == "tool_use":
            args = block.get("input") if isinstance(block.get("input"), dict) else {}
            what = str(args.get("file_path") or "")
            what = what[len(cwd):] if cwd and what.startswith(cwd) else what
            what = what or " ".join(str(args.get("command", "")).split())[:200]
            yield f"[{ts}] tool {block.get('name', '')} {what}"


def excerpt(path: Path, cwd: str = "") -> tuple:
    """(text, characters left out, the last entry's timestamp). Over EXCERPT_CAP the newest part is kept."""
    lines, last = [], ""
    cwd = f"{cwd.rstrip('/')}/" if cwd else ""
    for entry in _entries(path):
        lines += _render(entry, cwd)
        last = str(entry.get("timestamp") or last)
    text = "\n".join(lines)
    cut = max(0, len(text) - EXCERPT_CAP)
    if cut:
        text = f"[… {cut} earlier characters left out …]\n{text[cut:]}"
    return text, cut, last


def header(state: dict, sid: str, created_at: str, redactions: int) -> str:
    """The frontmatter block the digest copies verbatim; the tick reads these fields back after the run."""
    fields = {"partition": state.get("partition"), "codebase": state.get("codebase"), "session_id": sid,
              "created_at": created_at, "redactions": redactions}
    return "---\ntype: session_digest\n" + "".join(
        f"{k}: {json.dumps(str(v), ensure_ascii=False)}\n" for k, v in fields.items()) + "---\n"
