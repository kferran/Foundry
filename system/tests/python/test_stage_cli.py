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


def test_concurrent_stage_calls_all_land_in_the_snapshot(cli, vault):
    """20 stage subprocesses started together leave 20 staged entries (audit C1 spec §2)."""
    import os
    from helpers import concept, write
    targets = [f"wiki/work/concepts/Note{i}.md" for i in range(20)]
    for t in targets:
        write(vault, t, concept("work", t[-8:-3]))
    publish.snapshot(vault, RID, ["wiki/work/**"])
    env = {k: v for k, v in os.environ.items() if k != "VAULT_ROOT"}
    script = vault / "system/scripts/vault_index.py"
    procs = [subprocess.Popen([sys.executable, str(script), "stage", t, RID], cwd=vault, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True) for t in targets]
    errors = [p.communicate()[1] for p in procs]
    assert [p.returncode for p in procs] == [0] * 20, errors
    snap = json.loads((vault / "system/logs/runs" / RID / "snapshot.json").read_text())
    assert sorted(snap["staged"]) == sorted(targets)


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


def test_publish_cli_conflict_exits_0_rejected_and_empty_exit_5(vault):
    """A held-back note is a successful publish; a rejected or empty run still fails (audit C2 spec §2)."""
    import os
    import shutil
    from helpers import REPO, concept, write
    if os.geteuid() == 0:
        import pytest
        pytest.skip("root ignores directory modes")
    shutil.copytree(REPO / "system/scripts", vault / "system/scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    script = vault / "system/scripts/publish_staged.py"

    def commit(run_id):
        return subprocess.run([sys.executable, str(script), "commit", run_id], cwd=vault, capture_output=True, text=True)

    target = "wiki/work/concepts/New.md"
    publish.snapshot(vault, RID, ["wiki/work/**"])
    write(vault, f"wiki/.staging/{RID}/{target}", concept("work", "New"))
    write(vault, f"wiki/.staging/{RID}/_decisions.jsonl",
          json.dumps({"item": "i", "decision": "create", "target": target, "source": "s", "reason": "r"}) + "\n")
    folder = vault / "wiki/work/concepts"
    folder.chmod(0o555)  # validation reads; the rename fails and _apply holds the note back
    try:
        res = commit(RID)
    finally:
        folder.chmod(0o755)
    report = json.loads(res.stdout)
    assert (report["status"], report["conflicts"]) == ("conflict", [target]), res.stderr
    assert res.returncode == 0
    brief = "20261001T120000-brief-ab12"
    publish.snapshot(vault, brief, ["briefings/2026-10-01.md"])
    empty = commit(brief)
    assert empty.returncode == 5 and json.loads(empty.stdout)["status"] == "empty"


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
