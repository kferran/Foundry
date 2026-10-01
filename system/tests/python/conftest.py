import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from helpers import REPO  # noqa: E402

sys.path.insert(0, str(REPO / "system" / "scripts"))
FIXTURE = REPO / "system" / "tests" / "fixtures" / "vault"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    shutil.copytree(FIXTURE, root)
    schemas = REPO / "system" / "schemas"
    if schemas.exists():
        shutil.copytree(schemas, root / "system" / "schemas")
    else:
        (root / "system" / "schemas").mkdir(parents=True)
    return root


@pytest.fixture
def cli(vault: Path):
    shutil.copytree(REPO / "system" / "scripts", vault / "system" / "scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    script = vault / "system" / "scripts" / "vault_index.py"

    def run(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
        full_env = {k: v for k, v in os.environ.items() if k != "VAULT_ROOT"}
        full_env.update(env or {})
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=cwd or vault, env=full_env, capture_output=True, text=True,
        )

    return run
