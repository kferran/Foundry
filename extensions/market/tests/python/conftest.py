"""Import paths and fixtures for the market extension's tests: the extension's own scripts (marketlib), the vault's
system/scripts (vaultlib) and core's test helpers. The fixture vault is core's, with this extension copied in and
listed in system/config.md."""
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parents[2]
VAULT = EXT.parents[1]
FIXTURES = EXT / "tests" / "fixtures"
sys.path[:0] = [str(EXT / "scripts"), str(VAULT / "system" / "scripts"), str(VAULT / "system" / "tests" / "python")]

_spec = importlib.util.spec_from_file_location("foundry_core_conftest", VAULT / "system" / "tests" / "python" / "conftest.py")
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)
cli = _core.cli


def write_config(root: Path, extra: str = "") -> None:
    (root / "system").mkdir(parents=True, exist_ok=True)
    base = ('type: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\nremote_mode: "none"\n'
            'default_partition: "work"\nextensions: [market]\n')
    (root / "system" / "config.md").write_text(f"---\n{base}{extra}---\n", encoding="utf-8")


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    shutil.copytree(_core.FIXTURE, root)
    shutil.copytree(VAULT / "system" / "schemas", root / "system" / "schemas")
    shutil.copytree(EXT, root / "extensions" / "market", ignore=shutil.ignore_patterns("tests", "__pycache__"))
    write_config(root)
    return root
