"""A throwaway vault for today.py (console C1 spec §4): the core scripts and this extension copied in, a config, and
only the Now pages, project pages, Work Orders and prep files a test writes. today.py runs there as the app runs it.
A unique module name: conftest.py re-exports the fixtures, and tests import the helpers from here."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parents[2]
REPO = EXT.parents[1]
sys.path[:0] = [str(REPO / "system" / "scripts")]
from vaultlib.intake import Intake  # noqa: E402

CONFIG = ('---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
          'remote_mode: "none"\ndefault_partition: "work"\nextensions: ["console"]\n'
          'console_foreman_url: "https://claude.ai/code/session_example"\n---\n')


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    shutil.copytree(REPO / "system" / "scripts", root / "system" / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "system" / "templates", root / "system" / "templates")
    shutil.copytree(EXT, root / "extensions" / "console", ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    write(root, "system/config.md", CONFIG)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


@pytest.fixture
def day(vault: Path) -> str:
    return Intake(vault).today()


def now_page(root: Path, partition: str, lines: list) -> None:
    write(root, f"wiki/{partition}/Now.md",
          f"---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: {partition}\n---\n\n"
          "## Needs you\n" + "\n".join(lines) + "\n\n## Waiting\n")


def project(root: Path, partition: str, name: str, body: str) -> None:
    write(root, f"wiki/{partition}/concepts/{name}.md",
          f"---\ntype: concept\ntags: []\ncompiled_at: 2026-10-07\npartition: {partition}\n---\n\n# {name}\n\n{body}")


def active(root: Path, partition: str, entries: str) -> None:
    write(root, f"wiki/{partition}/ActiveProjects.md",
          f"---\ntype: concept\ntags: [\"active-projects\"]\ncompiled_at: 2026-10-07\npartition: {partition}\n---\n\n"
          f"# Active Projects\n\n## Active\n{entries}\n## Paused\n\n## Done\n")


def order(root: Path, item_id: str, state: str, partition: str = "work") -> None:
    write(root, f"raw/{partition}/nightshift/{item_id}.md",
          f'---\ntype: "nightshift_item"\nid: "{item_id}"\npartition: "{partition}"\nkind: "plan"\nstate: "{state}"\n'
          f'queued_at: "2026-10-20T10:00:00-06:00"\nrepo: "template"\n---\n')


def run(root: Path, *args):
    r = subprocess.run([sys.executable, str(root / "extensions/console/scripts/today.py"), *args], cwd=root,
                       capture_output=True, text=True)
    return r


def today_json(root: Path) -> dict:
    r = run(root, "--json")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)
