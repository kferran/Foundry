"""A throwaway vault for today.py (console C1 spec §4): the core scripts and this extension copied in, a config, and
only the Now pages, project pages, Work Orders and prep files a test writes. today.py runs there as the app runs it.
A unique module name: conftest.py re-exports the fixtures, and tests import the helpers from here."""
import json
from datetime import date, timedelta
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


def today_vault(vault: Path, day: str) -> None:
    """A vault holding every part the Today screen shows: two partitions, two projects, Now lines with
    and without a band, two Work Orders, and today's prep files and alerts."""
    past = (date.fromisoformat(day) - timedelta(days=4)).isoformat()
    later = (date.fromisoformat(day) + timedelta(days=5)).isoformat()
    now_page(vault, "work", [
        f"- [ ] owed: Reply on the cap for [[Alpha]] [due:: {past}] (Blake Sample, since 2026-10-01, "
        "https://github.com/acme/shop/pull/7)",
        f"- [ ] waiting: Rollback owner for alpha cutover [due:: {later}] (Jordan Example, since 2026-10-02)",
        "- [ ] owed: Unrelated chore (since 2026-10-03)",
    ])
    now_page(vault, "personal", ["- [ ] draft: Note to the garden club (since 2026-10-03)"])
    active(vault, "work", "- [[Alpha]]: cutover plan\n- [[Beta]]\n")
    project(vault, "work", "Alpha", "- [ ] Write the runbook\n- [ ] Confirm the owner\n")
    project(vault, "work", "Beta", "Nothing open.\n")
    order(vault, "2026-10-23-queued-one", "queued")
    order(vault, "2026-10-22-done-one", "done")
    prep = f"system/logs/inputs/{day}"
    write(vault, f"{prep}/calendar.tsv", f"{day}\t09:30\t{day}\t10:00\tStandup\n")
    write(vault, f"{prep}/actions.md", f"# Meeting actions for {day}\n\n## Yours\n"
          "- [Blake Sample] Send the metrics ([[2026-10-21 Billing sync]], 2 days open)\n"
          "- [Blake Sample] Plant the bulbs ([[2026-10-20 Garden]], 3 days open)\n\n## Waiting on\nNone.\n")
    write(vault, "wiki/work/meetings/2026-10-21 Billing sync.md", "---\ntype: meeting\n---\n")
    write(vault, "wiki/personal/meetings/2026-10-20 Garden.md", "---\ntype: meeting\n---\n")
    write(vault, f"{prep}/sources.md", "- calendar: ok\n- triage: failed: auth: expired\n")
    write(vault, f"{prep}/quarantine.md", "none\n")
    write(vault, f"system/logs/alerts_{day}.md", "- 09:00 [smoke] one\n- 09:05 [sync] two\n")

