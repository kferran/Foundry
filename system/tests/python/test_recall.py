"""Memory recall (spec §6.17): vault_index.py recall and vaultlib/recall.py."""
import fcntl
import os
import shutil
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
    # Not a bare "w1": under pytest-xdist the vault's tmp path holds "popen-gw1".
    assert "(w1)" not in out
    assert "of w1" not in out


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


def now_page(vault, partition, lines):
    write(vault, f"wiki/{partition}/Now.md",
          f'---\ntype: concept\ntags: [now]\ncompiled_at: "2026-10-09"\npartition: {partition}\n---\n# Now\n\n'
          "## Needs you\n" + "".join(f"{line}\n" for line in lines) + "\n## Waiting\n")


def test_now_lines_come_first_and_only_the_session_partitions(cli, vault):
    config(vault, "personal")
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    now_page(vault, "personal", ["- [ ] owed: Mine (since 2026-10-09)", "- [x] owed: Done (since 2026-10-01)"])
    now_page(vault, "work", ["- [ ] owed: Work only (since 2026-10-09)"])
    out = cli("recall", "--cwd", str(vault)).stdout
    assert "### Now (open loops)\n- [ ] owed: Mine (since 2026-10-09)\n" in out
    assert out.index("### Now") < out.index("### Recent session digests")
    assert "Done" not in out
    assert "Work only" not in out


def test_a_long_digest_is_cut_to_its_third_and_the_now_lines_keep_the_rest(cli, vault):
    # #211 replaced "Now lines whole first": the digests keep the last third of the room
    config(vault)
    lines = [f"- [ ] owed: Item {i} with some words to fill the line (since 2026-10-09)" for i in range(20)]
    now_page(vault, "personal", lines)
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00", body="## Outcome\n" + "word " * 1500)
    out = cli("recall", "--cwd", str(vault), "--budget-chars", "2500").stdout
    assert len(out) <= 2500
    assert lines[0] in out
    assert "…[truncated]" in out
    now_part = out.split("### Recent session digests")[0]
    assert len(out) - len(now_part) <= 2500 // 3


def test_now_alone_over_budget_ends_with_how_many_more(cli, vault):
    config(vault)
    now_page(vault, "personal", [f"- [ ] owed: Item {i} (since 2026-10-09)" for i in range(200)])
    out = cli("recall", "--cwd", str(vault), "--budget-chars", "1500").stdout
    assert len(out) <= 1500
    shown = out.count("- [ ] owed: Item ")
    assert out.endswith(f"…and {200 - shown} more open lines (system/scripts/now.py list --partition personal)\n")


def test_now_lines_are_ranked_due_first_then_newest_then_kind(cli, vault):
    # #211: page order put the oldest lines first and left no room for anything else
    config(vault)
    now_page(vault, "personal", [
        "- [ ] owed: A old (since 2026-10-01)",
        "- [ ] owed: B due later [due:: 2026-10-20] (since 2026-10-01)",
        "- [ ] owed: C due soon [due:: 2026-10-18] (since 2026-10-01)",
        "- [ ] waiting: E new (Ann, since 2026-10-12)",
        "- [ ] owed: D updated 2026-10-12: still open (since 2026-10-01)",
        "- [ ] hand-written line",
    ])
    out = cli("recall", "--cwd", str(vault)).stdout
    order = [out.index(s) for s in ("C due soon", "B due later", "D updated", "E new", "A old", "hand-written")]
    assert order == sorted(order)


def test_a_long_now_line_is_cut_keeping_its_due_and_parenthesis(cli, vault):
    config(vault)
    now_page(vault, "personal", ["- [ ] owed: " + "update " * 60 + "[due:: 2026-10-20] (Ann, since 2026-10-09, EX-1)"])
    out = cli("recall", "--cwd", str(vault)).stdout
    line = next(x for x in out.splitlines() if x.startswith("- [ ] owed: update"))
    assert len(line) <= recall.LINE_CAP
    assert "…" in line and line.endswith(" [due:: 2026-10-20] (Ann, since 2026-10-09, EX-1)")


def test_a_cut_line_keeps_what_it_is_and_its_newest_update(cli, vault):
    # live acceptance: the cut kept the oldest update notes and dropped the newest
    config(vault)
    now_page(vault, "personal", ["- [ ] owed: Deck for the review: " + "older note, " * 40 + "sent v3 (Ann, since 2026-10-09)"])
    line = next(x for x in cli("recall", "--cwd", str(vault)).stdout.splitlines() if x.startswith("- [ ] owed: Deck"))
    assert line.startswith("- [ ] owed: Deck for the review:")
    assert line.endswith("sent v3 (Ann, since 2026-10-09)") and "…" in line and len(line) <= recall.LINE_CAP


def test_a_short_now_page_leaves_the_rest_to_the_digests(cli, vault):
    # review: with one Now line the digests were held to a third and the rest of the budget went unused
    config(vault)
    now_page(vault, "personal", ["- [ ] owed: One thing (since 2026-10-09)"])
    for i in range(1, 4):
        digest(vault, "personal", f"p{i}", f"2026-10-0{i}T09:00:00-06:00", body="## Outcome\n" + f"word{i} " * 400)
    out = cli("recall", "--cwd", str(vault)).stdout
    assert "One thing" in out
    assert len(out.split("### Recent session digests")[1]) > 9000 // 2


def test_ranking_reads_only_real_dates_outside_links(cli, vault):
    config(vault)
    now_page(vault, "personal", [
        "- [ ] owed: C bad date 9999-99-99 (since 2026-01-01)",
        "- [ ] owed: B see https://x.example/2027-01-01/notes (since 2026-01-01)",
        "- [ ] owed: A plain (since 2026-10-10)",
    ])
    out = cli("recall", "--cwd", str(vault)).stdout
    assert out.index("A plain") < out.index("B see") and out.index("A plain") < out.index("C bad")


def test_a_line_with_text_after_its_parenthesis_ranks_by_its_own_fields(cli, vault):
    config(vault)
    now_page(vault, "personal", [
        "- [ ] owed: Old (since 2026-01-01)",
        "- [ ] owed: Due soon [due:: 2026-10-12] (Ann, since 2026-01-01) *Update 2026-10-05:* sent",
    ])
    out = cli("recall", "--cwd", str(vault)).stdout
    assert out.index("Due soon") < out.index("Old")


def test_digests_keep_a_third_of_the_room_under_a_long_now_page(cli, vault):
    config(vault)
    now_page(vault, "personal", [f"- [ ] owed: Item {i} " + "word " * 50 + "(since 2026-10-09)" for i in range(95)])
    digest(vault, "personal", "p1", "2026-10-01T09:00:00-06:00")
    digest(vault, "personal", "p2", "2026-10-02T09:00:00-06:00",
           body="## Outcome\nOutcome of p2.\n## Open questions / friction\n- Asked p2.\n## Follow-ups\n- Follow up p2.\n")
    out = cli("recall", "--cwd", str(vault)).stdout
    assert len(out) <= 9000
    for text in ("Follow up p1.", "Follow up p2.", "Asked p2.", "more open lines (system/scripts/now.py list"):
        assert text in out


def test_a_budget_smaller_than_the_marker_never_overflows(cli, vault):
    config(vault)
    now_page(vault, "personal", [f"- [ ] owed: Item {i} (since 2026-10-09)" for i in range(50)])
    head = cli("recall", "--cwd", str(vault), "--budget-chars", "9500").stdout.split("\n### Now")[0]
    out = cli("recall", "--cwd", str(vault), "--budget-chars", str(len(head) + 5)).stdout
    assert len(out) <= len(head) + 5


def commit_all(vault):
    for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True)


def git_vault(cli, vault):
    """A personal vault that is its own clean repository, its index built."""
    config(vault, "personal")
    write(vault, ".gitignore", "system/index.*\n__pycache__/\n")
    repo(vault)
    cli("recall", "--cwd", str(vault))
    commit_all(vault)


def fake_git(tmp_path, sleep="0"):
    """A git on PATH that logs its arguments, waits `sleep` seconds, then runs the real git."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "git"
    stub.write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/git.log\nsleep {sleep}\nexec {shutil.which("git")} "$@"\n')
    stub.chmod(0o755)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}"}


def test_vault_recall_names_uncommitted_files_outside_raw_and_the_other_partition(cli, vault):
    # #166: "N uncommitted files outside raw/" with the first three paths; raw/, the other partition's wiki and its
    # meeting drop folder stay out.
    git_vault(cli, vault)
    assert "uncommitted" not in cli("recall", "--cwd", str(vault)).stdout
    for path in ("raw/personal/notes/d.md", "wiki/work/x.md", "meetings/drop/work/x.vtt", "a.md", "b.md", "c.md",
                 "d.md"):
        write(vault, path, "x\n")
    out = cli("recall", "--cwd", str(vault), env={"GIT_DIR": "/nonexistent"}).stdout  # an inherited GIT_DIR (#173)
    assert "\n4 uncommitted files outside raw/: a.md, b.md, c.md, …\n" in out
    assert "wiki/work" not in out
    assert "drop/work" not in out
    commit_all(vault)
    assert "uncommitted" not in cli("recall", "--cwd", str(vault)).stdout


def test_dirty_line_takes_no_optional_locks_and_gives_up_on_a_slow_git(cli, vault, tmp_path):
    # PR #253 review: a git killed by the timeout must not leave .git/index.lock, and the hook has 3 s in all.
    git_vault(cli, vault)
    write(vault, "a.md", "x\n")
    assert "1 uncommitted file outside raw/: a.md" in cli("recall", "--cwd", str(vault), env=fake_git(tmp_path)).stdout
    assert "--no-optional-locks" in (tmp_path / "git.log").read_text()
    out = cli("recall", "--cwd", str(vault), env=fake_git(tmp_path, sleep="0.8")).stdout
    assert out.startswith("## Foundry vault recall") and "uncommitted" not in out


def test_dirty_line_survives_a_filename_that_is_not_utf8(cli, vault):
    git_vault(cli, vault)
    # The function itself: the index refresh also fails on such a name, a separate defect.
    os.close(os.open(bytes(vault) + b"/caf\xe9.txt", os.O_CREAT | os.O_WRONLY))
    assert recall.dirty_line(vault, "personal") == "1 uncommitted file outside raw/: caf\N{REPLACEMENT CHARACTER}.txt\n"


def test_dirty_line_is_skipped_after_a_busy_index_wait_and_never_empties_recall(cli, vault):
    git_vault(cli, vault)
    write(vault, "a.md", "x\n")
    with open(vault / "system" / "index.lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        out = cli("recall", "--cwd", str(vault)).stdout
    assert out.startswith("## Foundry vault recall") and "uncommitted" not in out
    head = cli("recall", "--cwd", str(vault)).stdout.split("1 uncommitted")[0]
    out = cli("recall", "--cwd", str(vault), "--budget-chars", str(len(head) + 5)).stdout
    assert out.startswith("## Foundry vault recall") and "uncommitted" not in out
