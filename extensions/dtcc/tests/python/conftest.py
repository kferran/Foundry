"""Import paths and fixtures for the DTCC extension's tests: the extension's own scripts (dtcclib), the vault's
system/scripts (vaultlib) and the core tests' python folder (helpers). The tests run from a vault whose
extensions/dtcc/ is this folder's grandparent. Core's fixtures live in a sibling folder, which pytest does not
share, so `vault` is defined here: core's fixture vault plus this extension, whose schema then loads."""
import shutil
import sys
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parents[2]
VAULT = EXT.parents[1]
sys.path[:0] = [str(EXT / "scripts"), str(VAULT / "system" / "scripts"), str(VAULT / "system" / "tests" / "python")]


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    shutil.copytree(VAULT / "system" / "tests" / "fixtures" / "vault", root)
    shutil.copytree(VAULT / "system" / "schemas", root / "system" / "schemas")
    shutil.copytree(EXT, root / "extensions" / "dtcc", ignore=shutil.ignore_patterns("__pycache__", "tests"))
    return root
