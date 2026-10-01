"""Shared helpers for the vaultlib test suite."""
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
