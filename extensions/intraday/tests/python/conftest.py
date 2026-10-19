"""Import paths and fixtures for the intraday extension's tests: the extension's own scripts (watchlib), the vault's
system/scripts (vaultlib) and core's test helpers. The tests run from a vault whose extensions/intraday/ is this
folder's grandparent. The fixture vault is core's, with this extension copied in and listed."""
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parents[2]
VAULT = EXT.parents[1]
sys.path[:0] = [str(EXT / "scripts"), str(VAULT / "system" / "scripts"), str(VAULT / "system" / "tests" / "python")]

_spec = importlib.util.spec_from_file_location("foundry_core_conftest", VAULT / "system" / "tests" / "python" / "conftest.py")
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    shutil.copytree(_core.FIXTURE, root)
    shutil.copytree(VAULT / "system" / "schemas", root / "system" / "schemas")
    shutil.copytree(VAULT / "system" / "templates", root / "system" / "templates")
    shutil.copytree(EXT, root / "extensions" / "intraday", ignore=shutil.ignore_patterns("tests", "__pycache__"))
    cfg = root / "system" / "config.md"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('---\ntype: config\ntimezone: "America/Denver"\ndefault_partition: "work"\nextensions: ["intraday"]\n'
                   'watch_channels: [{id: "C0OPS", label: "ops"}, {id: "C0ONCALL", label: "oncall"}]\n'
                   'watch_user_id: "U0OWNER"\ncapture_channel: "C0CAP"\n---\n', encoding="utf-8")
    return root
