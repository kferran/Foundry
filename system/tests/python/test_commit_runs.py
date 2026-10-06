"""commit_runs.py: one scripted commit per published headless run (two-machines spec §4)."""
import json
import re
import shutil
import subprocess
import sys

import pytest

from helpers import REPO, concept, meeting, transcript, write

FIXTURE = REPO / "system" / "tests" / "fixtures" / "vault"
ING = "20261004T120000-ingest-ab12"
BRIEF = "20261004T060000-brief-cd34"
MEET = "20261005T160000-meeting-ef78"
NAME = "2026-10-05-1500-weekly-sync"


def git(vault, *args):
    return subprocess.run(["git", "-C", str(vault), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    shutil.copytree(FIXTURE, root)
    shutil.copytree(REPO / "system" / "schemas", root / "system" / "schemas")
    shutil.copytree(REPO / "system" / "scripts", root / "system" / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / ".githooks", root / ".githooks")
    shutil.copy(REPO / ".gitignore", root / ".gitignore")
    write(root, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\nmachine_role: "server"\n'
                                    'default_partition: "personal"\n---\n')
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "test")
    git(root, "config", "core.hooksPath", ".githooks")
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-verify", "-m", "base")
    write(root, "system/logs/commit_runs.since", "20261001T000000\n")
    return root


def run_commits(vault, *args):
    return subprocess.run([sys.executable, str(vault / "system" / "scripts" / "commit_runs.py"), *args],
                          cwd=vault, capture_output=True, text=True)


def make_run(vault, run_id, published, status="published", conflicts=(), decisions=(), partition=None):
    rd = vault / "system" / "logs" / "runs" / run_id
    rd.mkdir(parents=True)
    (rd / "publish.json").write_text(json.dumps({"run_id": run_id, "status": status, "published": list(published),
                                                 "conflicts": list(conflicts), "problems": []}))
    if decisions:
        (rd / "_decisions.jsonl").write_text("".join(
            json.dumps({"item": "i", "decision": d, "target": t, "source": s, "reason": "r"}) + "\n"
            for d, t, s in decisions))
    if partition is not None:
        ledger = vault / "system" / "logs" / f"runs-{run_id[:4]}-{run_id[4:6]}.jsonl"
        with open(ledger, "a", encoding="utf-8") as fh:
            fh.write("not json\n" + json.dumps({"run_id": run_id, "command": "ingest", "partition": partition}) + "\n")
    for path in published:
        if path.startswith("briefings/"):
            write(vault, path, f'---\ntype: briefing\ndate: "{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}"\n---\n# Briefing\n')
        else:
            write(vault, path, concept(path.split("/")[1], path.rsplit("/", 1)[1][:-3], "[[Index]]"))
    return rd


def last_message(vault):
    return git(vault, "log", "-1", "--format=%B")


def marker(vault, run_id):
    return json.loads((vault / "system" / "logs" / "runs" / run_id / "committed").read_text())


def test_ingest_run_gets_its_scripted_message(vault):
    make_run(vault, ING, ["wiki/work/concepts/NightlyExport.md", "wiki/work/concepts/BillingService.md"],
             decisions=[("noop", "wiki/work/concepts/Kafka.md", "raw/work/notes/d1.md"),
                        ("create", "wiki/work/concepts/NightlyExport.md", "raw/work/notes/d1.md"),
                        ("patch", "wiki/work/concepts/BillingService.md", "raw/work/notes/d1.md")],
             partition="work")
    p = run_commits(vault)
    assert p.returncode == 0, p.stderr
    assert last_message(vault) == (
        "ingest(work): create NightlyExport, patch BillingService\n\n"
        "create wiki/work/concepts/NightlyExport.md <- raw/work/notes/d1.md\n"
        "patch wiki/work/concepts/BillingService.md <- raw/work/notes/d1.md\n\n"
        f"Foundry-Command: ingest\nFoundry-Run: {ING}\nFoundry-Role: server\n\n")
    sha = git(vault, "rev-parse", "HEAD").strip()
    assert marker(vault, ING) == {"sha": sha}
    assert p.stdout == f"{ING} {sha}\n"
    assert git(vault, "log", "--grep", "Foundry-Command: ingest", "--format=%s").strip() == \
        "ingest(work): create NightlyExport, patch BillingService"


def test_brief_and_debrief_runs_name_the_published_briefing(vault):
    make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
    deb = "20261004T170000-debrief-ef56"
    make_run(vault, deb, ["briefings/2026-10-04.debrief.md"], status="conflict",
             conflicts=["briefings/2026-10-04.md"])
    p = run_commits(vault)
    assert p.returncode == 0, p.stderr
    log = git(vault, "log", "-2", "--format=%B%x00").split("\x00")
    assert log[0].strip() == ("debrief 2026-10-04: briefings/2026-10-04.debrief.md\n\n"
                              "published briefings/2026-10-04.debrief.md\nconflict briefings/2026-10-04.md\n\n"
                              f"Foundry-Command: debrief\nFoundry-Run: {deb}\nFoundry-Role: server")
    assert log[1].strip() == ("brief 2026-10-04: briefings/2026-10-04.md\n\npublished briefings/2026-10-04.md\n\n"
                              f"Foundry-Command: brief\nFoundry-Run: {BRIEF}\nFoundry-Role: server")


def test_long_subject_is_cut_with_a_count_and_stays_under_72(vault):
    names = [f"wiki/work/concepts/LongNoteName{i}.md" for i in range(6)]
    make_run(vault, ING, names, decisions=[("create", n, "raw/work/notes/d.md") for n in names], partition="work")
    assert run_commits(vault).returncode == 0
    subject = git(vault, "log", "-1", "--format=%s").strip()
    assert len(subject) <= 72
    assert re.fullmatch(r"ingest\(work\): create LongNoteName0, create LongNoteName1 \+4 more", subject), subject
    assert len(last_message(vault).split("\n\n")[1].splitlines()) == 6


def test_a_single_overlong_name_falls_back_to_a_count(vault):
    name = "wiki/work/concepts/" + "N" * 80 + ".md"
    make_run(vault, ING, [name], decisions=[("create", name, "raw/work/notes/d.md")], partition="work")
    assert run_commits(vault).returncode == 0
    assert git(vault, "log", "-1", "--format=%s").strip() == "ingest(work): 1 notes"


def test_partition_falls_back_to_the_decision_target_folder(vault):
    make_run(vault, ING, ["wiki/shared/concepts/Rust.md"],
             decisions=[("create", "wiki/shared/concepts/Rust.md", "raw/shared/notes/x.md")])
    assert run_commits(vault).returncode == 0
    assert git(vault, "log", "-1", "--format=%s").strip() == "ingest(shared): create Rust"


def test_control_characters_in_a_source_stay_on_one_line(vault):
    make_run(vault, ING, ["wiki/work/concepts/A.md"],
             decisions=[("create", "wiki/work/concepts/A.md", "raw/inbox/a\nFoundry-Command: forged")], partition="work")
    assert run_commits(vault).returncode == 0
    assert "create wiki/work/concepts/A.md <- raw/inbox/a Foundry-Command: forged\n" in last_message(vault)
    assert git(vault, "log", "-1", "--format=%(trailers:key=Foundry-Command,valueonly)").strip() == "ingest"


def test_only_the_runs_paths_are_committed_even_with_other_files_staged(vault):
    write(vault, "wiki/personal/concepts/Mine.md", concept("personal", "Mine", "[[Index]]"))
    git(vault, "add", "wiki/personal/concepts/Mine.md")
    make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
    assert run_commits(vault).returncode == 0
    assert git(vault, "show", "--name-only", "--format=", "HEAD").split() == ["briefings/2026-10-04.md"]
    assert git(vault, "diff", "--cached", "--name-only").split() == ["wiki/personal/concepts/Mine.md"]


def test_runs_commit_in_run_id_order(vault):
    make_run(vault, ING, ["wiki/work/concepts/A.md"], decisions=[("create", "wiki/work/concepts/A.md", "s")],
             partition="work")
    make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
    assert run_commits(vault).returncode == 0
    assert git(vault, "log", "-2", "--format=%(trailers:key=Foundry-Run,valueonly)").split() == [ING, BRIEF]


def test_runs_before_the_cutover_and_committed_runs_are_skipped(vault):
    make_run(vault, "20260930T235959-brief-0000", ["briefings/2026-09-30.md"])
    rd = make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
    (rd / "committed").write_text('{"sha": "abc"}\n')
    head = git(vault, "rev-parse", "HEAD")
    p = run_commits(vault)
    assert p.returncode == 0
    assert p.stdout == ""
    assert git(vault, "rev-parse", "HEAD") == head


@pytest.mark.parametrize("status", ["rejected", "empty", "noop", "aborted"])
def test_runs_that_published_nothing_are_not_pending(vault, status):
    make_run(vault, BRIEF, [], status=status)
    p = run_commits(vault)
    assert p.returncode == 0
    assert not (vault / "system" / "logs" / "runs" / BRIEF / "committed").exists()


def test_a_run_still_publishing_is_not_pending(vault):
    rd = vault / "system" / "logs" / "runs" / BRIEF
    rd.mkdir(parents=True)
    (rd / "publish.journal").write_text('{"staged": "s", "target": "briefings/2026-10-04.md", "expected": null}\n')
    p = run_commits(vault)
    assert p.returncode == 0
    assert p.stdout == ""
    assert not (rd / "committed").exists()


@pytest.mark.parametrize("status", ["conflict", "recovered"])
def test_conflict_and_recovered_runs_that_published_are_committed(vault, status):
    make_run(vault, BRIEF, ["briefings/2026-10-04.md"], status=status)
    assert run_commits(vault).returncode == 0
    assert marker(vault, BRIEF)["sha"] == git(vault, "rev-parse", "HEAD").strip()


def test_paths_already_in_head_get_the_marker_without_a_commit(vault):
    make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
    git(vault, "add", "briefings/2026-10-04.md")
    git(vault, "commit", "-q", "-m", "by hand")
    head = git(vault, "rev-parse", "HEAD")
    p = run_commits(vault)
    assert p.returncode == 0
    assert marker(vault, BRIEF) == {"sha": None, "reason": "already committed"}
    assert p.stdout == f"{BRIEF} already committed\n"
    assert git(vault, "rev-parse", "HEAD") == head


def test_a_published_path_deleted_since_is_committed_as_a_deletion_or_skipped(vault):
    make_run(vault, BRIEF, ["briefings/2026-10-04.md", "wiki/work/concepts/Kafka.md"])
    (vault / "briefings" / "2026-10-04.md").unlink()
    (vault / "wiki" / "work" / "concepts" / "Kafka.md").unlink()
    assert run_commits(vault).returncode == 0
    assert git(vault, "show", "--name-status", "--format=", "HEAD").split() == ["D", "wiki/work/concepts/Kafka.md"]


def test_a_users_status_config_cannot_hide_a_new_note(vault):
    git(vault, "config", "status.showUntrackedFiles", "no")
    make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
    assert run_commits(vault).returncode == 0
    assert marker(vault, BRIEF) == {"sha": git(vault, "rev-parse", "HEAD").strip()}
    assert git(vault, "show", "--name-only", "--format=", "HEAD").split() == ["briefings/2026-10-04.md"]


def test_a_note_two_pending_runs_published_is_committed_with_the_later_run(vault):
    first, second = "20261004T110000-ingest-aa11", ING
    alpha, beta = "wiki/work/concepts/Alpha.md", "wiki/work/concepts/Beta.md"
    make_run(vault, first, [alpha, beta], decisions=[("create", alpha, "s1"), ("create", beta, "s1")], partition="work")
    make_run(vault, second, [alpha], decisions=[("patch", alpha, "s2")], partition="work")
    assert run_commits(vault).returncode == 0
    assert git(vault, "show", "--name-only", "--format=", f"{marker(vault, first)['sha']}").split() == [beta]
    assert git(vault, "show", "--name-only", "--format=", "HEAD").split() == [alpha]
    assert f"carries {alpha} from {first}\n" in last_message(vault)
    assert git(vault, "log", "-1", "--format=%s").strip() == "ingest(work): patch Alpha"


def test_a_run_whose_notes_a_later_run_published_again_is_recorded_as_superseded(vault):
    first = "20261004T110000-ingest-aa11"
    alpha = "wiki/work/concepts/Alpha.md"
    make_run(vault, first, [alpha], decisions=[("create", alpha, "s1")], partition="work")
    make_run(vault, ING, [alpha], decisions=[("patch", alpha, "s2")], partition="work")
    p = run_commits(vault)
    assert p.returncode == 0
    assert marker(vault, first) == {"sha": None, "reason": f"superseded by {ING}"}
    assert p.stdout.splitlines()[0] == f"{first} superseded by {ING}"
    assert git(vault, "log", "-1", "--format=%(trailers:key=Foundry-Run,valueonly)").strip() == ING


def test_a_hook_failure_alerts_leaves_the_run_pending_and_stops(vault):
    bad = "wiki/work/concepts/Bad.md"
    make_run(vault, BRIEF, [bad])
    write(vault, bad, "---\ntype: concept\n---\n# Bad\n")
    make_run(vault, ING, ["wiki/work/concepts/A.md"], decisions=[("create", "wiki/work/concepts/A.md", "s")],
             partition="work")
    head = git(vault, "rev-parse", "HEAD")
    p = run_commits(vault)
    assert p.returncode == 1
    assert f"commit_runs: {BRIEF}" in p.stderr
    assert git(vault, "rev-parse", "HEAD") == head
    assert not (vault / "system" / "logs" / "runs" / BRIEF / "committed").exists()
    assert not (vault / "system" / "logs" / "runs" / ING / "committed").exists()
    assert git(vault, "diff", "--cached", "--name-only") == ""
    alerts = list((vault / "system" / "logs").glob("alerts_*.md"))
    assert len(alerts) == 1
    assert re.match(rf"- \d\d:\d\d:\d\d \[commit_runs\] run {BRIEF} not committed: ", alerts[0].read_text())


def test_init_cutover_writes_the_local_time_once(vault):
    since = vault / "system" / "logs" / "commit_runs.since"
    since.unlink()
    assert run_commits(vault, "--init-cutover").returncode == 0
    first = since.read_text().strip()
    assert re.fullmatch(r"\d{8}T\d{6}", first)
    since.write_text("20200101T000000\n")
    assert run_commits(vault, "--init-cutover").returncode == 0
    assert since.read_text().strip() == "20200101T000000"


def test_a_missing_cutover_is_written_and_older_runs_stay_uncommitted(vault):
    (vault / "system" / "logs" / "commit_runs.since").unlink()
    old = "20200101T060000-brief-cd34"
    make_run(vault, old, ["briefings/2020-01-01.md"])
    p = run_commits(vault)
    assert p.returncode == 0
    assert (vault / "system" / "logs" / "commit_runs.since").exists()
    assert not (vault / "system" / "logs" / "runs" / old / "committed").exists()


def test_usage_errors_exit_2(vault):
    assert run_commits(vault, "--bogus").returncode == 2


def meeting_run(vault, title, partition="work"):
    paths = [f"wiki/{partition}/meetings/{NAME}.md", f"wiki/{partition}/meetings/{NAME}.transcript.md"]
    rd = vault / "system" / "logs" / "runs" / MEET
    rd.mkdir(parents=True)
    (rd / "publish.json").write_text(json.dumps({"run_id": MEET, "status": "published", "published": paths,
                                                 "conflicts": [], "problems": []}))
    with open(vault / "system" / "logs" / "runs-2026-10.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"run_id": MEET, "command": "meeting", "partition": partition}) + "\n")
    write(vault, paths[0], meeting(partition, NAME, title))
    write(vault, paths[1], transcript(partition, NAME))
    return paths


def test_a_meeting_run_is_committed_under_the_meeting_title(vault):
    paths = meeting_run(vault, "Weekly sync", partition="personal")
    p = run_commits(vault)
    assert p.returncode == 0, p.stderr
    assert last_message(vault) == (
        f"meeting(personal): Weekly sync\n\npublished {paths[0]}\npublished {paths[1]}\n\n"
        f"Foundry-Command: meeting\nFoundry-Run: {MEET}\nFoundry-Role: server\n\n")
    assert marker(vault, MEET)["sha"] == git(vault, "rev-parse", "HEAD").strip()


def test_a_long_meeting_title_is_cut_with_an_ellipsis_and_control_characters_go(vault):
    meeting_run(vault, "Quarterly\tplanning " + "x" * 80)
    assert run_commits(vault).returncode == 0
    subject = git(vault, "log", "-1", "--format=%s").strip()
    assert len(subject) <= 72 and subject.endswith("…")
    assert subject.startswith("meeting(work): Quarterly planning xxx")
