"""Paths and helpers the market tests share. A module of its own name: every extension's tests run in one pytest
session, where `from conftest import …` can resolve to another extension's conftest."""
from pathlib import Path

EXT = Path(__file__).resolve().parents[2]
VAULT = EXT.parents[1]
FIXTURES = EXT / "tests" / "fixtures"


def write_config(root: Path, extra: str = "") -> None:
    base = ('type: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\nremote_mode: "none"\n'
            'default_partition: "work"\nextensions: [market]\n')
    (root / "system").mkdir(parents=True, exist_ok=True)
    (root / "system" / "config.md").write_text(f"---\n{base}{extra}---\n", encoding="utf-8")
