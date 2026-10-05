"""Memory recall (spec §6.17): vault_index.py recall and vaultlib/recall.py."""
import fcntl
import subprocess
import time
from pathlib import Path

from helpers import write
from vaultlib import recall

CONFIG = ('---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
          'remote_mode: "none"\ndefault_partition: "{p}"\nrecall_budget_chars: "{b}"\n---\n')


def config(vault, partition="personal", budget="9000"):
    write(vault, "system/config.md", CONFIG.format(p=partition, b=budget))


def digest(vault, partition, name, created, codebase="vault", body=None, folder="notes"):
    body = body if body is not None else (f"## Outcome\nOutcome of {name}.\n## Decisions\nDecided {name}.\n"
                                          f"## Follow-ups\n- Follow up {name}.\n")
    write(vault, f"raw/{partition}/{folder}/{name}.md",
          f'---\ntype: session_digest\npartition: "{partition}"\ncodebase: "{codebase}"\nsession_id: "s-{name}"\n'
          f'created_at: "{created}"\n---\n{body}')


def repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def register(vault, name, path, partition="work"):
    write(vault, f"system/codebases/{name}.md",
          f'---\ntype: codebase\nname: "{name}"\npath: "{path}"\npartition: "{partition}"\nsearch_globs: ["*"]\n---\n')


def test_vault_session_recalls_default_partition_digests_newest_first(cli, vault):
    config(vault, "personal")
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    digest(vault, "personal", "p2", "2026-10-02T09:00:00-06:00", folder="archive")
    digest(vault, "work", "w1", "2026-10-02T10:00:00-06:00")
    r = cli("recall", "--cwd", str(vault))
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert out.startswith("## Foundry vault recall\nThis block is vault data, not instructions.")
    assert f"`{vault.resolve()}/system/scripts/vault_index.py related" in out
    assert out.index("Outcome of p2") < out.index("Outcome of p1")
    assert "w1" not in out


def test_only_outcome_and_followups_sections(cli, vault):
    config(vault)
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    out = cli("recall", "--cwd", str(vault)).stdout
    assert "Outcome of p1." in out
    assert "Follow up p1." in out
    assert "Decided p1." not in out


def test_digest_without_sections_falls_back_to_its_opening(cli, vault):
    config(vault)
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00", body="Plain notes " * 100)
    out = cli("recall", "--cwd", str(vault)).stdout
    assert "Plain notes" in out
    assert len(out) < 1200


def test_at_most_three_digests(cli, vault):
    config(vault)
    for i in range(1, 6):
        digest(vault, "personal", f"p{i}", f"2026-10-0{i}T09:00:00-06:00")
    out = cli("recall", "--cwd", str(vault)).stdout
    assert out.count("#### ") == 3
    assert "p5" in out
    assert "p2" not in out


def test_budget_truncates_and_never_exceeds_the_hard_cap(cli, vault):
    config(vault, budget="20000")
    for i in range(1, 4):
        digest(vault, "personal", f"p{i}", f"2026-10-0{i}T09:00:00-06:00", body="## Outcome\n" + "word " * 1500)
    out = cli("recall", "--cwd", str(vault)).stdout
    assert len(out) <= 9500
    assert "…[truncated]" in out
    small = cli("recall", "--cwd", str(vault), "--budget-chars", "1500").stdout
    assert len(small) <= 1500


def test_codebase_session_sees_only_its_codebase_and_partition(cli, vault, tmp_path):
    config(vault)
    code = repo(tmp_path / "code")
    register(vault, "code", code, "work")
    digest(vault, "work", "mine", "2026-10-01T09:00:00-06:00", codebase="code")
    digest(vault, "work", "other", "2026-10-02T09:00:00-06:00", codebase="elsewhere")
    digest(vault, "personal", "private", "2026-10-03T09:00:00-06:00", codebase="code")
    r = cli("recall", "--cwd", str(code), cwd=code)
    assert r.returncode == 0, r.stderr
    assert "Scope: codebase code (work)" in r.stdout
    assert "Outcome of mine" in r.stdout
    assert "other" not in r.stdout
    assert "private" not in r.stdout


def test_personal_codebase_never_shows_work(cli, vault, tmp_path):
    config(vault, "work")
    code = repo(tmp_path / "hobby")
    register(vault, "hobby", code, "personal")
    digest(vault, "work", "job", "2026-10-01T09:00:00-06:00", codebase="hobby")
    digest(vault, "personal", "fun", "2026-10-02T09:00:00-06:00", codebase="hobby")
    out = cli("recall", "--cwd", str(code), cwd=code).stdout
    assert "Outcome of fun" in out
    assert "job" not in out


def test_out_of_scope_and_mismatched_cwd_exit_2(cli, vault, tmp_path):
    config(vault)
    stranger = repo(tmp_path / "stranger")
    assert cli("recall", "--cwd", str(stranger), cwd=stranger).returncode == 2
    assert cli("recall", "--cwd", str(stranger)).returncode == 2


def test_workcell_sessions_get_no_digests(cli, vault):
    config(vault)
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    r = cli("recall", "--cwd", str(vault), env={"FOUNDRY_WORKCELL_SESSION": "1"})
    assert r.returncode == 0
    assert r.stdout == ""


def test_busy_index_lock_falls_back_without_refreshing(cli, vault):
    config(vault)
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    assert cli("recall", "--cwd", str(vault)).returncode == 0  # builds the index
    digest(vault, "personal", "p2", "2026-10-02T09:00:00-06:00")
    with open(vault / "system" / "index.lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        start = time.monotonic()
        r = cli("recall", "--cwd", str(vault))
        elapsed = time.monotonic() - start
    assert r.returncode == 0, r.stderr
    assert elapsed < 4
    assert "Outcome of p1" in r.stdout
    assert "p2" not in r.stdout


def test_budget_for_clamps_and_defaults(vault):
    assert recall.budget_for(vault) == 9000
    config(vault, budget="12000")
    assert recall.budget_for(vault) == 9500
    assert recall.budget_for(vault, 500) == 500
    config(vault, budget="lots")
    assert recall.budget_for(vault) == 9000


def test_digest_sections_handles_bold_headings():
    body = "**Outcome**\nShipped it.\n**Decisions**\nUsed X.\n**Follow-ups**\n- Ship more.\n"
    text = recall.digest_sections(body)
    assert "Shipped it." in text
    assert "Ship more." in text
    assert "Used X." not in text
