"""Import paths and fixtures for the health extension's tests. The tests run from a vault whose extensions/health/ is
this folder's grandparent. The fixture vault holds only what a test writes, plus a config."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parents[2]
VAULT = EXT.parents[1]
sys.path[:0] = [str(VAULT / "system" / "scripts")]

_spec = importlib.util.spec_from_file_location("health", EXT / "scripts" / "health.py")
health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(health)


@pytest.fixture
def h():
    return health


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "system" / "logs").mkdir(parents=True)
    (root / "system" / "config.md").write_text('---\ntype: config\ntimezone: "America/Denver"\n---\n', encoding="utf-8")
    return root


@pytest.fixture
def jsonl():
    """jsonl(path, *rows): append each row as one JSON line."""
    def write(path: Path, *rows) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    return write


@pytest.fixture
def config(vault):
    """config(*lines): rewrite the vault's config with these frontmatter lines."""
    def write(*lines) -> None:
        (vault / "system" / "config.md").write_text(
            '---\ntype: config\ntimezone: "America/Denver"\n' + "".join(f"{x}\n" for x in lines) + "---\n",
            encoding="utf-8")
    return write
