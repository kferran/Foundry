"""State files shared by the connector features (F1 spec §3.3): atomic JSON and JSONL ledgers."""
import json
import os
from pathlib import Path


def load(path: Path, default):
    """The parsed JSON, or default when missing or unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def records(*paths: Path) -> list:
    """Every JSON object line of each existing path, in order; other lines are skipped."""
    out = []
    for path in paths:
        for raw in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
            try:
                r = json.loads(raw)
            except ValueError:
                continue
            if isinstance(r, dict):
                out.append(r)
    return out
