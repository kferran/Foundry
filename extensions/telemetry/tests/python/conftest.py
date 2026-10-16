"""Import paths and fixtures for the telemetry extension's tests: the extension's own scripts (telemetrylib), the
vault's system/scripts (vaultlib) and core's test helpers. The tests run from a vault whose extensions/telemetry/ is
this folder's grandparent. The fixture vault is core's, with this extension and the one it requires copied in."""
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
needs_bwrap, cli = _core.needs_bwrap, _core.cli


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    shutil.copytree(_core.FIXTURE, root)
    shutil.copytree(VAULT / "system" / "schemas", root / "system" / "schemas")
    for name in ("handoffs", "telemetry"):
        shutil.copytree(VAULT / "extensions" / name, root / "extensions" / name,
                        ignore=shutil.ignore_patterns("tests", "__pycache__"))
    return root
