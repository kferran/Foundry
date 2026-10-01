import json
import subprocess
import sys

from vaultlib import publish

RID = "20261001T120000-ingest-ab12"


def test_stage_subcommand(cli, vault):
    publish.snapshot(vault, RID, ["wiki/work/**"])
    res = cli("stage", "wiki/work/concepts/Kafka.md", RID)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == f"wiki/.staging/{RID}/wiki/work/concepts/Kafka.md"
    snap = json.loads((vault / "system/logs/runs" / RID / "snapshot.json").read_text())
    assert "wiki/work/concepts/Kafka.md" in snap["staged"]


def test_stage_refuses_bad_input(cli, vault):
    publish.snapshot(vault, RID, ["wiki/work/**"])
    assert cli("stage", "wiki/personal/concepts/Gardening.md", RID).returncode == 2
    assert cli("stage", "wiki/work/concepts/Kafka.md", "not-a-run").returncode == 2


def test_publish_cli_exit_codes(vault):
    import shutil
    from helpers import REPO
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    script = vault / "system/scripts/publish_staged.py"
    snap = subprocess.run([sys.executable, str(script), "snapshot", RID, "--targets", "wiki/work/**"],
                          cwd=vault, capture_output=True, text=True)
    assert snap.returncode == 0, snap.stderr
    empty = subprocess.run([sys.executable, str(script), "commit", RID], cwd=vault, capture_output=True, text=True)
    assert empty.returncode == 5 and json.loads(empty.stdout)["status"] == "rejected"
    bad = subprocess.run([sys.executable, str(script), "commit", "nope"], cwd=vault, capture_output=True, text=True)
    assert bad.returncode == 2


def test_publish_cli_corrupt_snapshot_exits_2(vault):
    import shutil
    from helpers import REPO
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    script = vault / "system/scripts/publish_staged.py"
    publish.snapshot(vault, RID, ["wiki/work/**"])
    (vault / "system/logs/runs" / RID / "snapshot.json").write_text("{bad")
    res = subprocess.run([sys.executable, str(script), "commit", RID], cwd=vault, capture_output=True, text=True)
    assert res.returncode == 2, res.stderr
