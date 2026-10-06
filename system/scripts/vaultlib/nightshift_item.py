"""nightshift_item queue notes (Nightshift spec §4): ids, budgets, read, write, list, update."""
import json
import os
import re
from datetime import datetime
from pathlib import Path

from . import frontmatter

PARTITIONS = ("work", "personal", "shared")
ORDER = ("type", "id", "partition", "kind", "state", "queued_at", "start", "start_at", "budget", "model", "repo",
         "base", "pr_base", "plan", "tasks", "verify", "hosts", "output", "session_id", "started_at", "finished_at",
         "attempts", "reset_at", "result", "reason")
AFTER_CANCEL = {"finished_at", "reason", "result"}


def note_path(vault, partition: str, item_id: str) -> Path:
    return Path(vault) / "raw" / partition / "nightshift" / f"{item_id}.md"


def new_id(title: str, now: datetime) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48].strip("-") or "item"
    return f"{now.date().isoformat()}-{slug}"


def budget_seconds(text) -> int:
    m = re.fullmatch(r"(\d+)([hm])", str(text or "").strip())
    if not m or int(m.group(1)) == 0:
        raise ValueError(f"budget must look like 4h or 90m: {text!r}")
    return int(m.group(1)) * (3600 if m.group(2) == "h" else 60)


def render(fm: dict, body: str) -> str:
    lines = ["---"]
    for k in ORDER + tuple(k for k in fm if k not in ORDER):
        v = fm.get(k)
        if v is None or v == "":
            continue
        lines.append(f"{k}: {json.dumps(v if isinstance(v, list) else str(v), ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + (body.rstrip() + "\n" if body.strip() else "")


def load(path) -> tuple:
    note = frontmatter.parse(Path(path).read_text(encoding="utf-8"))
    return dict(note.data or {}), note.body


def save(path, fm: dict, body: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(render(fm, body), encoding="utf-8")
    os.replace(tmp, path)


def items(vault) -> list:
    out = []
    for p in sorted(Path(vault).glob("raw/*/nightshift/*.md")):
        try:
            fm, body = load(p)
        except (OSError, UnicodeDecodeError):
            continue
        if fm.get("type") == "nightshift_item":
            out.append((p, fm, body))
    return out


def update(path, **fields) -> dict:
    """Re-read, apply, write. A cancelled item only takes AFTER_CANCEL fields."""
    fm, body = load(path)
    for k, v in fields.items():
        if fm.get("state") == "cancelled" and k not in AFTER_CANCEL:
            continue
        if v is None:
            fm.pop(k, None)
        else:
            fm[k] = v
    save(path, fm, body)
    return fm
