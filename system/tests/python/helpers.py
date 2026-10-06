"""Shared helpers for the vaultlib test suite."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def write(root: Path, rel: str, text: str) -> Path:
    """Write text to root/rel, creating parent directories."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def concept(partition: str, title: str, body: str = "", **extra: str) -> str:
    """Return a valid concept note. extra values are raw YAML snippets."""
    fm = {
        "type": "concept",
        "tags": "[]",
        "compiled_at": '"2026-09-01"',
        "partition": partition,
    }
    fm.update(extra)
    lines = ["---", *[f"{k}: {v}" for k, v in fm.items()], "---", f"# {title}", body, ""]
    return "\n".join(lines)


def meeting(partition: str, name: str, title: str = "Weekly sync", body: str = "", **extra: str) -> str:
    """Return a valid meeting note for <name> (YYYY-MM-DD-HHMM-slug). extra values are raw YAML snippets."""
    fm = {"type": "meeting", "title": json.dumps(title), "date": f'"{name[:10]}"',
          "start": f'"{name[:10]}T{name[11:13]}:{name[13:15]}:00-06:00"', "partition": partition,
          "source": f'"gdoc:FAKE-{name}"', "transcript": f'"[[{name}.transcript]]"'}
    fm.update(extra)
    return "\n".join(["---", *[f"{k}: {v}" for k, v in fm.items()], "---", f"# {title}", body, ""])


def transcript(partition: str, name: str, body: str = "") -> str:
    """Return a valid meeting_transcript note beside meeting(<partition>, <name>)."""
    return (f'---\ntype: meeting_transcript\nmeeting: "[[{name}]]"\npartition: {partition}\n'
            f'source: "gdoc:FAKE-{name}"\ncomplete: true\n---\n# Transcript\n{body}\n')
