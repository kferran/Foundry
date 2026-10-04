# Plan 8b: Commit History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every headless run that published files gets its own commit, with a message a script builds from the run's records and `Jarvis-*` trailers, so `git log` reads as a handoff log.

**Architecture:**
- `commit_runs.py` (stdlib Python plus `vaultlib.frontmatter`) finds pending runs in `system/logs/runs/`, builds each message from `publish.json`, `_decisions.jsonl` and the run ledger, and commits only the run's published paths with `git commit --only`, through the pre-commit hook.
- `/backup` runs it in every role before its own commit. `/setup` phase 7 and `update_template.sh` set the cutover, so older runs are never committed one by one.
- `debrief_prep.sh` lists the vault's commits from every author.

**Tech Stack:** Python 3.11+ (stdlib, `zoneinfo`), git, bash 5, bats ≥ 1.8, pytest.

**Spec:** `docs/superpowers/specs/2026-10-03-two-machines-design.md` §4, §8 (8b), §8.1 (8b) and §9 (rev 3, approved).

## Global Constraints

- **Formats (spec §4.1):** ingest subject `ingest(<partition>): <decisions>`, cut with `+N more`; body one line per non-noop decision, `<decision> <target> <- <source>`. Brief and debrief subject `brief <date>: <published path>` / `debrief <date>: <published path>`; body the published and conflict lists. Trailers `Jarvis-Command`, `Jarvis-Run`, `Jarvis-Role`. Subjects stay under 72 characters. No model writes a message.
- **Pending run (spec §4.2):** `publish.json` with a non-empty `published` list (any status), no `committed` file, `run_id` at or after the cutover (string compare of the first 15 characters with `system/logs/commit_runs.since`).
- **Commit (spec §4.2):** `git add -- <paths>` then `git commit --only -- <paths>`, through the pre-commit hook. Already committed: marker `{"sha": null, "reason": "already committed"}`. Hook failure: alert, run stays pending, stop, exit 1. Marker `{"sha": "<sha>"}`.
- **Template rule:** no hostname, user path or remote URL is committed. The Debian host is `<debian-host>` in docs and records.
- **Tool floor:** jq 1.6, bats 1.8, SQLite 3.40, Python 3.11 (no bats `run -N`). The gate runs on the Debian host; a test that commits sets its own git identity.
- **bats ruling R1:** no mid-test `!`, no `&&` assertion chains. Bats files stay mode 644; `commit_runs.py` is 755 (the patch sets it).
- **Gate:** `system/scripts/verify_setup.sh > system/logs/gate.log 2>&1; echo "exit=$?"`, then `sed -n '/===== summary/,$p' system/logs/gate.log` (15 suites). **Lint:** `system/scripts/lint_vault.sh > system/logs/lint.log 2>&1; echo "lint exit=$?"; tail -n 1 system/logs/lint.log`. Read verdicts from exit codes, never through a pipe.
- **Patches:** every test and implementation step is an exact patch tested in a scratch clone. Save the block to a file in the plan workspace and run `git apply --check <file> && git apply <file>`. A patch that does not apply means the tree differs from the plan's base: stop and compare.
- American English. Branch `feat/plan-8b` from `master` at 41c243b (PR #9 merged). Commit trailers name the authoring model.

## Decisions made while planning

- **D1 One script.** `system/scripts/commit_runs.py`, stdlib plus `vaultlib.frontmatter` for `system/config.md`; the vault root comes from the script's location, as for every vault script. Interface: `commit_runs.py [--init-cutover]`. Stdout: one line per run, `<run_id> <sha>` or `<run_id> already committed`. Stderr on failure: `commit_runs: <run_id>: <git error>`. Exit 0, 1 or 2 (usage).
- **D2 Subject overflow.** The longest prefix of decision items that fits in 72 characters, then `+N more`. When not even one item fits, `ingest(<partition>): <n> notes`.
- **D3 Conflicts and odd paths.** Subjects name published files only. Held-back conflicts get an ingest body line `held back <path> (conflict)` and a brief/debrief body line `conflict <path>`. A published path with no decision (the gate requires one per ingest file, so only a damaged record) gets `update <path>`.
- **D4 A path changed since publishing.** A tracked path deleted since is committed as a deletion; a never-tracked one that is gone is skipped. When no path is left, or none differs from `HEAD`, the run gets the already-committed marker. A user's own later edit to a published note is committed with the run (the body names the run).
- **D5 Model-written text.** A decision's `source` comes from the model. Control characters in every body line are replaced with spaces, so no line can add a trailer.
- **D6 No `run.lock`.** `publish.json` is written atomically after every file is in place, so a run still publishing (a journal and no `publish.json`) is not pending; Plan 8c's `vault_sync.sh` holds `run.lock` around its whole cycle.
- **D7 Hook failure.** The run's paths are unstaged (`git reset -q -- <paths>`), an alert goes to `system/logs/alerts_<date>.md` with the tag `[commit_runs]` (the brief reads alerts), and processing stops with exit 1. `/backup` stops and reports it.
- **D8 Partition.** From the run's ledger line in `system/logs/runs-<YYYY-MM>.jsonl` for the run's own month (unparseable lines skipped), then the partition folder of the first decision target, then of the first published path, then `default_partition`.
- **D9 Cutover writers.** `--init-cutover` writes the current time in the configured timezone when the file is absent. `/setup` phase 7 and `update_template.sh` (after a clean merge, before the index rebuild) call it; `commit_runs.py` calls it as a last resort.
- **D10 Probed while planning (2026-10-04):** `git commit --only -- <paths>` runs the pre-commit hook against git's temporary index. With a lint-failing note staged, a clean note committed with `--only`; the failing note alone was rejected. So the hook lints only the run's paths, and the "other files staged" and "hook failure" tests can both hold.
- **D11 Scratch result:** gate 15/15 on the Debian host with all six patches applied.

## Review Focus

1. **A run's note fails the pre-commit lint.** Expected: an alert, no commit, that run and every later run still pending, the index as before, and `/backup` stops. Pinned by `test_a_hook_failure_alerts_leaves_the_run_pending_and_stops`.
2. **A vault updated from a pre-8b template, with months of runs and no cutover.** Expected: none of the old runs gets its own commit. Pinned by `test_a_missing_cutover_is_written_and_older_runs_stay_uncommitted` and `remote.bats` "update_template merges a clean update…".
3. **`/backup` while a headless run is publishing.** Expected: the run is not pending until its `publish.json` exists. Pinned by `test_a_run_still_publishing_is_not_pending`.
4. **A digest whose text puts a newline and `Jarvis-Command:` into a decision's source.** Expected: one body line, trailers unchanged. Pinned by `test_control_characters_in_a_source_stay_on_one_line`.
5. **Other work staged when `/backup` runs.** Expected: each run commit holds only the run's paths, and the user's staged files stay staged. Pinned by `test_only_the_runs_paths_are_committed_even_with_other_files_staged`.

---

### Task 1: `commit_runs.py`

**Files:**
- Create: `system/scripts/commit_runs.py` (755)
- Test: `system/tests/python/test_commit_runs.py`

**Interfaces:**
- Produces: `commit_runs.py [--init-cutover]` (D1). Marker `system/logs/runs/<run_id>/committed`. Cutover `system/logs/commit_runs.since`. Alert tag `[commit_runs]`.

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/system/tests/python/test_commit_runs.py b/system/tests/python/test_commit_runs.py
new file mode 100644
index 0000000..4e8679d
--- /dev/null
+++ b/system/tests/python/test_commit_runs.py
@@ -0,0 +1,257 @@
+"""commit_runs.py: one scripted commit per published headless run (two-machines spec §4)."""
+import json
+import re
+import shutil
+import subprocess
+import sys
+
+import pytest
+
+from helpers import REPO, concept, write
+
+FIXTURE = REPO / "system" / "tests" / "fixtures" / "vault"
+ING = "20261004T120000-ingest-ab12"
+BRIEF = "20261004T060000-brief-cd34"
+
+
+def git(vault, *args):
+    return subprocess.run(["git", "-C", str(vault), *args], capture_output=True, text=True, check=True).stdout
+
+
+@pytest.fixture
+def vault(tmp_path):
+    root = tmp_path / "vault"
+    shutil.copytree(FIXTURE, root)
+    shutil.copytree(REPO / "system" / "schemas", root / "system" / "schemas")
+    shutil.copytree(REPO / "system" / "scripts", root / "system" / "scripts",
+                    ignore=shutil.ignore_patterns("__pycache__"))
+    shutil.copytree(REPO / ".githooks", root / ".githooks")
+    shutil.copy(REPO / ".gitignore", root / ".gitignore")
+    write(root, "system/config.md", '---\ntype: config\ntimezone: "America/Denver"\nmachine_role: "server"\n'
+                                    'default_partition: "personal"\n---\n')
+    git(root, "init", "-q")
+    git(root, "config", "user.email", "test@example.com")
+    git(root, "config", "user.name", "test")
+    git(root, "config", "core.hooksPath", ".githooks")
+    git(root, "add", "-A")
+    git(root, "commit", "-q", "--no-verify", "-m", "base")
+    write(root, "system/logs/commit_runs.since", "20261001T000000\n")
+    return root
+
+
+def run_commits(vault, *args):
+    return subprocess.run([sys.executable, str(vault / "system" / "scripts" / "commit_runs.py"), *args],
+                          cwd=vault, capture_output=True, text=True)
+
+
+def make_run(vault, run_id, published, status="published", conflicts=(), decisions=(), partition=None):
+    rd = vault / "system" / "logs" / "runs" / run_id
+    rd.mkdir(parents=True)
+    (rd / "publish.json").write_text(json.dumps({"run_id": run_id, "status": status, "published": list(published),
+                                                 "conflicts": list(conflicts), "problems": []}))
+    if decisions:
+        (rd / "_decisions.jsonl").write_text("".join(
+            json.dumps({"item": "i", "decision": d, "target": t, "source": s, "reason": "r"}) + "\n"
+            for d, t, s in decisions))
+    if partition is not None:
+        ledger = vault / "system" / "logs" / f"runs-{run_id[:4]}-{run_id[4:6]}.jsonl"
+        with open(ledger, "a", encoding="utf-8") as fh:
+            fh.write("not json\n" + json.dumps({"run_id": run_id, "command": "ingest", "partition": partition}) + "\n")
+    for path in published:
+        if path.startswith("briefings/"):
+            write(vault, path, f'---\ntype: briefing\ndate: "{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}"\n---\n# Briefing\n')
+        else:
+            write(vault, path, concept(path.split("/")[1], path.rsplit("/", 1)[1][:-3], "[[Index]]"))
+    return rd
+
+
+def last_message(vault):
+    return git(vault, "log", "-1", "--format=%B")
+
+
+def marker(vault, run_id):
+    return json.loads((vault / "system" / "logs" / "runs" / run_id / "committed").read_text())
+
+
+def test_ingest_run_gets_its_scripted_message(vault):
+    make_run(vault, ING, ["wiki/work/concepts/NightlyExport.md", "wiki/work/concepts/BillingService.md"],
+             decisions=[("noop", "wiki/work/concepts/Kafka.md", "raw/work/notes/d1.md"),
+                        ("create", "wiki/work/concepts/NightlyExport.md", "raw/work/notes/d1.md"),
+                        ("patch", "wiki/work/concepts/BillingService.md", "raw/work/notes/d1.md")],
+             partition="work")
+    p = run_commits(vault)
+    assert p.returncode == 0, p.stderr
+    assert last_message(vault) == (
+        "ingest(work): create NightlyExport, patch BillingService\n\n"
+        "create wiki/work/concepts/NightlyExport.md <- raw/work/notes/d1.md\n"
+        "patch wiki/work/concepts/BillingService.md <- raw/work/notes/d1.md\n\n"
+        f"Jarvis-Command: ingest\nJarvis-Run: {ING}\nJarvis-Role: server\n\n")
+    sha = git(vault, "rev-parse", "HEAD").strip()
+    assert marker(vault, ING) == {"sha": sha}
+    assert p.stdout == f"{ING} {sha}\n"
+    assert git(vault, "log", "--grep", "Jarvis-Command: ingest", "--format=%s").strip() == \
+        "ingest(work): create NightlyExport, patch BillingService"
+
+
+def test_brief_and_debrief_runs_name_the_published_briefing(vault):
+    make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
+    deb = "20261004T170000-debrief-ef56"
+    make_run(vault, deb, ["briefings/2026-10-04.debrief.md"], status="conflict",
+             conflicts=["briefings/2026-10-04.md"])
+    p = run_commits(vault)
+    assert p.returncode == 0, p.stderr
+    log = git(vault, "log", "-2", "--format=%B%x00").split("\x00")
+    assert log[0].strip() == ("debrief 2026-10-04: briefings/2026-10-04.debrief.md\n\n"
+                              "published briefings/2026-10-04.debrief.md\nconflict briefings/2026-10-04.md\n\n"
+                              f"Jarvis-Command: debrief\nJarvis-Run: {deb}\nJarvis-Role: server")
+    assert log[1].strip() == ("brief 2026-10-04: briefings/2026-10-04.md\n\npublished briefings/2026-10-04.md\n\n"
+                              f"Jarvis-Command: brief\nJarvis-Run: {BRIEF}\nJarvis-Role: server")
+
+
+def test_long_subject_is_cut_with_a_count_and_stays_under_72(vault):
+    names = [f"wiki/work/concepts/LongNoteName{i}.md" for i in range(6)]
+    make_run(vault, ING, names, decisions=[("create", n, "raw/work/notes/d.md") for n in names], partition="work")
+    assert run_commits(vault).returncode == 0
+    subject = git(vault, "log", "-1", "--format=%s").strip()
+    assert len(subject) <= 72
+    assert re.fullmatch(r"ingest\(work\): create LongNoteName0, create LongNoteName1 \+4 more", subject), subject
+    assert len(last_message(vault).split("\n\n")[1].splitlines()) == 6
+
+
+def test_a_single_overlong_name_falls_back_to_a_count(vault):
+    name = "wiki/work/concepts/" + "N" * 80 + ".md"
+    make_run(vault, ING, [name], decisions=[("create", name, "raw/work/notes/d.md")], partition="work")
+    assert run_commits(vault).returncode == 0
+    assert git(vault, "log", "-1", "--format=%s").strip() == "ingest(work): 1 notes"
+
+
+def test_partition_falls_back_to_the_decision_target_folder(vault):
+    make_run(vault, ING, ["wiki/shared/concepts/Rust.md"],
+             decisions=[("create", "wiki/shared/concepts/Rust.md", "raw/shared/notes/x.md")])
+    assert run_commits(vault).returncode == 0
+    assert git(vault, "log", "-1", "--format=%s").strip() == "ingest(shared): create Rust"
+
+
+def test_control_characters_in_a_source_stay_on_one_line(vault):
+    make_run(vault, ING, ["wiki/work/concepts/A.md"],
+             decisions=[("create", "wiki/work/concepts/A.md", "raw/inbox/a\nJarvis-Command: forged")], partition="work")
+    assert run_commits(vault).returncode == 0
+    assert "create wiki/work/concepts/A.md <- raw/inbox/a Jarvis-Command: forged\n" in last_message(vault)
+    assert git(vault, "log", "-1", "--format=%(trailers:key=Jarvis-Command,valueonly)").strip() == "ingest"
+
+
+def test_only_the_runs_paths_are_committed_even_with_other_files_staged(vault):
+    write(vault, "wiki/personal/concepts/Mine.md", concept("personal", "Mine", "[[Index]]"))
+    git(vault, "add", "wiki/personal/concepts/Mine.md")
+    make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
+    assert run_commits(vault).returncode == 0
+    assert git(vault, "show", "--name-only", "--format=", "HEAD").split() == ["briefings/2026-10-04.md"]
+    assert git(vault, "diff", "--cached", "--name-only").split() == ["wiki/personal/concepts/Mine.md"]
+
+
+def test_runs_commit_in_run_id_order(vault):
+    make_run(vault, ING, ["wiki/work/concepts/A.md"], decisions=[("create", "wiki/work/concepts/A.md", "s")],
+             partition="work")
+    make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
+    assert run_commits(vault).returncode == 0
+    assert git(vault, "log", "-2", "--format=%(trailers:key=Jarvis-Run,valueonly)").split() == [ING, BRIEF]
+
+
+def test_runs_before_the_cutover_and_committed_runs_are_skipped(vault):
+    make_run(vault, "20260930T235959-brief-0000", ["briefings/2026-09-30.md"])
+    rd = make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
+    (rd / "committed").write_text('{"sha": "abc"}\n')
+    head = git(vault, "rev-parse", "HEAD")
+    p = run_commits(vault)
+    assert p.returncode == 0
+    assert p.stdout == ""
+    assert git(vault, "rev-parse", "HEAD") == head
+
+
+@pytest.mark.parametrize("status", ["rejected", "empty", "noop", "aborted"])
+def test_runs_that_published_nothing_are_not_pending(vault, status):
+    make_run(vault, BRIEF, [], status=status)
+    p = run_commits(vault)
+    assert p.returncode == 0
+    assert not (vault / "system" / "logs" / "runs" / BRIEF / "committed").exists()
+
+
+def test_a_run_still_publishing_is_not_pending(vault):
+    rd = vault / "system" / "logs" / "runs" / BRIEF
+    rd.mkdir(parents=True)
+    (rd / "publish.journal").write_text('{"staged": "s", "target": "briefings/2026-10-04.md", "expected": null}\n')
+    p = run_commits(vault)
+    assert p.returncode == 0
+    assert p.stdout == ""
+    assert not (rd / "committed").exists()
+
+
+@pytest.mark.parametrize("status", ["conflict", "recovered"])
+def test_conflict_and_recovered_runs_that_published_are_committed(vault, status):
+    make_run(vault, BRIEF, ["briefings/2026-10-04.md"], status=status)
+    assert run_commits(vault).returncode == 0
+    assert marker(vault, BRIEF)["sha"] == git(vault, "rev-parse", "HEAD").strip()
+
+
+def test_paths_already_in_head_get_the_marker_without_a_commit(vault):
+    make_run(vault, BRIEF, ["briefings/2026-10-04.md"])
+    git(vault, "add", "briefings/2026-10-04.md")
+    git(vault, "commit", "-q", "-m", "by hand")
+    head = git(vault, "rev-parse", "HEAD")
+    p = run_commits(vault)
+    assert p.returncode == 0
+    assert marker(vault, BRIEF) == {"sha": None, "reason": "already committed"}
+    assert p.stdout == f"{BRIEF} already committed\n"
+    assert git(vault, "rev-parse", "HEAD") == head
+
+
+def test_a_published_path_deleted_since_is_committed_as_a_deletion_or_skipped(vault):
+    make_run(vault, BRIEF, ["briefings/2026-10-04.md", "wiki/work/concepts/Kafka.md"])
+    (vault / "briefings" / "2026-10-04.md").unlink()
+    (vault / "wiki" / "work" / "concepts" / "Kafka.md").unlink()
+    assert run_commits(vault).returncode == 0
+    assert git(vault, "show", "--name-status", "--format=", "HEAD").split() == ["D", "wiki/work/concepts/Kafka.md"]
+
+
+def test_a_hook_failure_alerts_leaves_the_run_pending_and_stops(vault):
+    bad = "wiki/work/concepts/Bad.md"
+    make_run(vault, BRIEF, [bad])
+    write(vault, bad, "---\ntype: concept\n---\n# Bad\n")
+    make_run(vault, ING, ["wiki/work/concepts/A.md"], decisions=[("create", "wiki/work/concepts/A.md", "s")],
+             partition="work")
+    head = git(vault, "rev-parse", "HEAD")
+    p = run_commits(vault)
+    assert p.returncode == 1
+    assert f"commit_runs: {BRIEF}" in p.stderr
+    assert git(vault, "rev-parse", "HEAD") == head
+    assert not (vault / "system" / "logs" / "runs" / BRIEF / "committed").exists()
+    assert not (vault / "system" / "logs" / "runs" / ING / "committed").exists()
+    assert git(vault, "diff", "--cached", "--name-only") == ""
+    alerts = list((vault / "system" / "logs").glob("alerts_*.md"))
+    assert len(alerts) == 1
+    assert re.match(rf"- \d\d:\d\d:\d\d \[commit_runs\] run {BRIEF} not committed: ", alerts[0].read_text())
+
+
+def test_init_cutover_writes_the_local_time_once(vault):
+    since = vault / "system" / "logs" / "commit_runs.since"
+    since.unlink()
+    assert run_commits(vault, "--init-cutover").returncode == 0
+    first = since.read_text().strip()
+    assert re.fullmatch(r"\d{8}T\d{6}", first)
+    since.write_text("20200101T000000\n")
+    assert run_commits(vault, "--init-cutover").returncode == 0
+    assert since.read_text().strip() == "20200101T000000"
+
+
+def test_a_missing_cutover_is_written_and_older_runs_stay_uncommitted(vault):
+    (vault / "system" / "logs" / "commit_runs.since").unlink()
+    old = "20200101T060000-brief-cd34"
+    make_run(vault, old, ["briefings/2020-01-01.md"])
+    p = run_commits(vault)
+    assert p.returncode == 0
+    assert (vault / "system" / "logs" / "commit_runs.since").exists()
+    assert not (vault / "system" / "logs" / "runs" / old / "committed").exists()
+
+
+def test_usage_errors_exit_2(vault):
+    assert run_commits(vault, "--bogus").returncode == 2
```

- [ ] **Step 2: Run and watch them fail.** `python3 -m pytest system/tests/python/test_commit_runs.py -q > system/logs/t1.log 2>&1; echo "rc=$?"; tail -n 1 system/logs/t1.log`. Expected: `rc=1`, `21 failed, 1 passed`. The usage test passes only because Python exits 2 for a missing script; it becomes meaningful after Step 3.

- [ ] **Step 3: Apply the implementation:**

```diff
diff --git a/system/scripts/commit_runs.py b/system/scripts/commit_runs.py
new file mode 100755
index 0000000..7d8a4d7
--- /dev/null
+++ b/system/scripts/commit_runs.py
@@ -0,0 +1,185 @@
+#!/usr/bin/env python3
+"""Commit each published headless run with a message built from its records (two-machines spec §4).
+
+Usage: commit_runs.py [--init-cutover]. Exit 0 when every pending run is committed or recorded as
+already committed; 1 when a commit fails (alert written, that run and later ones stay pending); 2 usage.
+"""
+import json
+import re
+import subprocess
+import sys
+from datetime import datetime
+from pathlib import Path
+from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
+
+VAULT = Path(__file__).resolve().parents[2]
+sys.path.insert(0, str(VAULT / "system" / "scripts"))
+from vaultlib import frontmatter  # noqa: E402
+
+LOGS = VAULT / "system" / "logs"
+RUNS = LOGS / "runs"
+SINCE = LOGS / "commit_runs.since"
+RUN_ID = re.compile(r"^(\d{8}T\d{6})-(ingest|brief|debrief)-[0-9a-f]{4}$")
+PARTITIONS = ("work", "personal", "shared")
+CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
+SUBJECT_MAX = 72
+
+
+def config(key, default):
+    try:
+        data = frontmatter.parse((VAULT / "system" / "config.md").read_text(encoding="utf-8")).data or {}
+    except (OSError, UnicodeDecodeError):
+        return default
+    value = data.get(key)
+    return value if isinstance(value, str) and value else default
+
+
+def now():
+    try:
+        return datetime.now(ZoneInfo(config("timezone", "UTC")))
+    except (ZoneInfoNotFoundError, ValueError):
+        return datetime.now(ZoneInfo("UTC"))
+
+
+def init_cutover():
+    """The run_id-format time before which runs are never committed; written once per vault."""
+    if not SINCE.exists():
+        SINCE.parent.mkdir(parents=True, exist_ok=True)
+        SINCE.write_text(now().strftime("%Y%m%dT%H%M%S") + "\n", encoding="utf-8")
+    return SINCE.read_text(encoding="utf-8").strip()
+
+
+def alert(message):
+    LOGS.mkdir(parents=True, exist_ok=True)
+    t = now()
+    with open(LOGS / f"alerts_{t:%Y-%m-%d}.md", "a", encoding="utf-8") as fh:
+        fh.write(f"- {t:%H:%M:%S} [commit_runs] {CONTROL.sub(' ', message)}\n")
+
+
+def json_lines(path):
+    try:
+        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
+    except OSError:
+        return []
+    out = []
+    for line in lines:
+        try:
+            record = json.loads(line)
+        except ValueError:
+            continue
+        if isinstance(record, dict):
+            out.append(record)
+    return out
+
+
+def pending(since):
+    if not RUNS.is_dir():
+        return []
+    out = []
+    for rd in sorted(RUNS.iterdir()):
+        match = RUN_ID.match(rd.name)
+        if not match or match.group(1) < since or (rd / "committed").exists():
+            continue
+        try:
+            report = json.loads((rd / "publish.json").read_text(encoding="utf-8"))
+        except (OSError, ValueError, UnicodeDecodeError):
+            continue
+        if not isinstance(report, dict):
+            continue
+        published = [p for p in report.get("published") or [] if isinstance(p, str)]
+        if published:
+            conflicts = [p for p in report.get("conflicts") or [] if isinstance(p, str)]
+            out.append((rd.name, match.group(2), published, conflicts))
+    return out
+
+
+def folder_partition(paths):
+    for path in paths:
+        parts = path.split("/")
+        if len(parts) > 2 and parts[0] == "wiki" and parts[1] in PARTITIONS:
+            return parts[1]
+    return None
+
+
+def subject(prefix, items):
+    for k in range(len(items), 0, -1):
+        text = prefix + ", ".join(items[:k]) + (f" +{len(items) - k} more" if k < len(items) else "")
+        if len(text) <= SUBJECT_MAX:
+            return text
+    return f"{prefix}{len(items)} notes"
+
+
+def message(run_id, command, published, conflicts, role):
+    if command == "ingest":
+        decisions = [r for r in json_lines(RUNS / run_id / "_decisions.jsonl")
+                     if isinstance(r.get("decision"), str) and r["decision"] != "noop" and isinstance(r.get("target"), str)]
+        rows, seen = [], set()
+        for r in decisions:
+            if r["target"] in published and (r["decision"], r["target"]) not in seen:
+                seen.add((r["decision"], r["target"]))
+                rows.append((r["decision"], r["target"], r["source"] if isinstance(r.get("source"), str) else ""))
+        covered = {t for _, t, _ in rows}
+        rows += [("update", p, "") for p in published if p not in covered]
+        ledger = LOGS / f"runs-{run_id[:4]}-{run_id[4:6]}.jsonl"
+        partition = next((r["partition"] for r in json_lines(ledger)
+                          if r.get("run_id") == run_id and r.get("partition") in PARTITIONS), None) \
+            or folder_partition([r["target"] for r in decisions]) or folder_partition(published) \
+            or config("default_partition", "personal")
+        head = subject(f"ingest({partition}): ", [f"{CONTROL.sub(' ', d)} {Path(t).stem}" for d, t, _ in rows])
+        body = [f"{d} {t} <- {s}" if s else f"{d} {t}" for d, t, s in rows]
+        body += [f"held back {p} (conflict)" for p in conflicts]
+    else:
+        head = f"{command} {run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}: {published[0]}"
+        body = [f"published {p}" for p in published] + [f"conflict {p}" for p in conflicts]
+    body = [CONTROL.sub(" ", line) for line in body]
+    trailers = [f"Jarvis-Command: {command}", f"Jarvis-Run: {run_id}", f"Jarvis-Role: {CONTROL.sub(' ', role)}"]
+    return head + "\n\n" + "\n".join(body) + "\n\n" + "\n".join(trailers) + "\n"
+
+
+def git(*args, stdin=None):
+    return subprocess.run(["git", "-C", str(VAULT), *args], input=stdin, capture_output=True, text=True)
+
+
+def commit(paths, text):
+    """Commit only these paths. Returns (sha, None), (None, None) when nothing differs, or (None, error)."""
+    tracked = set(git("ls-files", "-z", "--", *paths).stdout.split("\0"))
+    paths = [p for p in paths if (VAULT / p).exists() or p in tracked]
+    if not paths:
+        return None, None
+    status = git("status", "--porcelain", "--", *paths)
+    if status.returncode:
+        return None, status.stderr.strip() or "git status failed"
+    if not status.stdout.strip():
+        return None, None
+    for step in (["add", "-A", "--", *paths], ["commit", "-q", "--only", "-F", "-", "--", *paths]):
+        done = git(*step, stdin=text if step[0] == "commit" else None)
+        if done.returncode:
+            git("reset", "-q", "--", *paths)
+            return None, (done.stderr.strip() or done.stdout.strip() or f"git {step[0]} failed")
+    return git("rev-parse", "HEAD").stdout.strip(), None
+
+
+def main(argv):
+    if argv == ["--init-cutover"]:
+        init_cutover()
+        return 0
+    if argv:
+        print("usage: commit_runs.py [--init-cutover]", file=sys.stderr)
+        return 2
+    since = init_cutover()
+    role = config("machine_role", "standalone")
+    for run_id, command, published, conflicts in pending(since):
+        sha, error = commit(published, message(run_id, command, published, conflicts, role))
+        if error:
+            first = error.splitlines()[0] if error else ""
+            alert(f"run {run_id} not committed: {first} (it stays pending; fix it, then run /backup again)")
+            print(f"commit_runs: {run_id}: {error}", file=sys.stderr)
+            return 1
+        record = {"sha": sha} if sha else {"sha": None, "reason": "already committed"}
+        (RUNS / run_id / "committed").write_text(json.dumps(record) + "\n", encoding="utf-8")
+        print(f"{run_id} {sha or 'already committed'}")
+    return 0
+
+
+if __name__ == "__main__":
+    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run and watch them pass.** Same command. Expected: `rc=0`, `22 passed`. Commit: `git add system/scripts/commit_runs.py system/tests/python/test_commit_runs.py && git commit -m "feat(commits): one scripted commit per published headless run"`.

### Task 2: Callers: `/backup`, `/setup` phase 7, `update_template.sh`; README

**Files:**
- Modify: `.claude/commands/backup.md` (new step 3; later steps renumbered), `.claude/commands/setup.md` (phase 7), `system/scripts/update_template.sh`, `README.md` (How it works)
- Test: `system/tests/commands.bats`, `system/tests/remote.bats`

**Interfaces:**
- Consumes: `commit_runs.py` and `commit_runs.py --init-cutover` (Task 1).

- [ ] **Step 1: Write the failing tests:**

```diff
diff --git a/system/tests/commands.bats b/system/tests/commands.bats
index ce4dfd3..1c875f7 100644
--- a/system/tests/commands.bats
+++ b/system/tests/commands.bats
@@ -330,6 +330,19 @@ self_edit_contract() {
   grep -qF 'Skip this step on a client.' "$f"
 }
 
+@test "/backup commits each published headless run before its own commit, in every role" {
+  f=.claude/commands/backup.md
+  grep -qF 'run `system/scripts/commit_runs.py`' "$f"
+  [ "$(grep -n 'commit_runs.py' "$f" | cut -d: -f1)" -gt "$(grep -n '^2\. \*\*Health' "$f" | cut -d: -f1)" ]
+  [ "$(grep -n 'commit_runs.py' "$f" | cut -d: -f1)" -lt "$(grep -n '\*\*Changes\.\*\*' "$f" | cut -d: -f1)" ]
+  grep -qF 'every role and every `remote_mode`' "$f"
+}
+
+@test "/setup phase 7 sets the run-commit cutover" {
+  sec="$(setup_section '7. Index')"
+  [[ "$sec" == *'system/scripts/commit_runs.py --init-cutover'* ]]
+}
+
 @test "system_health checks each item only on the roles that run it" {
   f=system/tests/system_health.bats
   grep -qF 'skip_unless_role standalone server' "$f"
diff --git a/system/tests/remote.bats b/system/tests/remote.bats
index 165f780..65d4d15 100644
--- a/system/tests/remote.bats
+++ b/system/tests/remote.bats
@@ -183,6 +183,7 @@ upstream_commit() {  # <file> <text>
   [ "$(cat new.txt)" = hello ]
   [ "$(git log -1 --format=%P | wc -w)" -eq 2 ]
   [ -f system/index.db ]
+  grep -qE '^[0-9]{8}T[0-9]{6}$' system/logs/commit_runs.since
   grep -qx 'changed jarvis-brief.service' <<< "$output"
   grep -q '^ExecStart=' "$SYSTEMD_USER_DIR/jarvis-brief.service"
 }
```

- [ ] **Step 2: Run and watch them fail.** `bats system/tests/commands.bats > system/logs/t2.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t2.log` (expected: `exit=1`, the two new tests) and `bats system/tests/remote.bats > system/logs/t2r.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t2r.log` (expected: `exit=1`, "update_template merges a clean update…").

- [ ] **Step 3: Apply the implementation:**

```diff
diff --git a/.claude/commands/backup.md b/.claude/commands/backup.md
index 538b4bc..5a5fc3e 100644
--- a/.claude/commands/backup.md
+++ b/.claude/commands/backup.md
@@ -6,10 +6,11 @@ Back up the vault.
 
 1. **Verify.** Run `system/scripts/verify_setup.sh`. On a client (`machine_role: client`), run `system/scripts/lint_vault.sh` instead: a client has no bats or pytest. If it exits non-zero, stop: report the failures and do not commit.
 2. **Health (report only).** Run `bats system/tests/system_health.bats` and summarize failures as warnings. They never block the backup. Skip this step on a client.
-3. **Changes.** Run `git status --porcelain`. If nothing changed, check for commits not yet pushed (`git status -sb` shows `ahead`, or the branch has no upstream): if there are some, go to step 5; otherwise say the vault is up to date and stop.
-4. **Commit.** Stage everything (`git add -A`; the gitignore keeps raw inputs, logs and config out). Write one Conventional Commits message from the changed paths, and commit. The pre-commit hook lints staged notes; if it blocks the commit, report the errors and stop.
-5. **Push.** Read `system/scripts/vault_index.py field system/config.md remote_mode`:
+3. **Run commits.** In every role and every `remote_mode`, run `system/scripts/commit_runs.py`. It commits each headless run that published files, one commit per run with a message built from the run's records, and prints one line per run. If it exits 1, stop: report its `commit_runs:` line (a run's files failed the pre-commit hook; fix them, then run `/backup` again) and do not commit.
+4. **Changes.** Run `git status --porcelain`. If nothing changed, check for commits not yet pushed (`git status -sb` shows `ahead`, or the branch has no upstream): if there are some, go to step 6; otherwise say the vault is up to date and stop.
+5. **Commit.** Stage everything (`git add -A`; the gitignore keeps raw inputs, logs and config out). Write one Conventional Commits message from the changed paths, and commit. The pre-commit hook lints staged notes; if it blocks the commit, report the errors and stop.
+6. **Push.** Read `system/scripts/vault_index.py field system/config.md remote_mode`:
    - `none`: skip the push and say so.
    - `private`: if the `origin` URL is the template repository (`system/template_source`), refuse and say why. Otherwise `git push`, or `git push -u origin HEAD` when the branch has no upstream.
    - `keep`: push `origin` as configured.
-6. **Report** the commit hash, its message, the files committed and the push result.
+7. **Report** each run commit from step 3, then the commit hash, its message, the files committed and the push result.
diff --git a/.claude/commands/setup.md b/.claude/commands/setup.md
index 477476a..f2106ae 100644
--- a/.claude/commands/setup.md
+++ b/.claude/commands/setup.md
@@ -68,7 +68,7 @@ On a client, never install the hooks. Run `system/scripts/install_hooks.sh --dry
 The brief reads today's calendar from the Google Calendar connector of the Claude account this machine's `claude` is logged in with. Run `system/scripts/calendar_fetch.sh` with a Bash timeout of at least 300000 ms (a fetch takes up to about three minutes and costs about $0.20). On exit 0, report how many events it printed for today. Otherwise report its `calendar_fetch:` line and what to do: exit 3, connect Google Calendar in the account's connector settings at claude.ai (same account as this machine), or log `claude` in with a claude.ai account; exit 6, reconnect it; exit 4, try again later; any other exit, show the line from `system/logs/calendar_fetch-<YYYY-MM>.jsonl`. A calendar failure never blocks setup: the brief then lists the calendar under Unavailable Sources.
 
 ## 7. Index
-Run `system/scripts/vault_index.py rebuild`, then `system/scripts/vault_index.py issues`, and report any error.
+Run `system/scripts/vault_index.py rebuild`, then `system/scripts/vault_index.py issues`, and report any error. Then run `system/scripts/commit_runs.py --init-cutover`: it records the time from which `/backup` commits each headless run on its own; runs from before it are committed with the rest of the vault.
 
 ## 8. Verify
 Run `system/scripts/verify_setup.sh --health` and `systemctl --user list-timers 'jarvis-*'`. Report each suite's PASS/FAIL line and the next run time of each timer. Health failures are advisory. On a client, run `system/scripts/lint_vault.sh` instead (a client has no test tools or timers) and report its last line.
diff --git a/system/scripts/update_template.sh b/system/scripts/update_template.sh
index 51bc592..914b25d 100755
--- a/system/scripts/update_template.sh
+++ b/system/scripts/update_template.sh
@@ -27,6 +27,8 @@ if ! git merge --no-ff --no-edit "$ref"; then
   exit 1
 fi
 
+# Runs from before this update are committed with the rest of the vault, never one by one (two-machines spec §4.2).
+system/scripts/commit_runs.py --init-cutover
 system/scripts/vault_index.py rebuild
 
 # Re-render units only where this vault already installed them: an update must never install or
diff --git a/README.md b/README.md
index 0efd7ad..ee7bfe0 100644
--- a/README.md
+++ b/README.md
@@ -52,6 +52,8 @@ The intended loop is **capture → compile → index → recall → correct**:
 5. **Recall.** With the memory hooks installed, a `SessionStart` hook adds up to `recall_budget_chars` of vault data (default 9,000 characters, never more than 9,500) to new sessions in scope: the latest digests for the codebase or partition and, once enabled, preferences you have confirmed. Recalled text is marked as data, not instructions.
 6. **Correct.** Each digest has a Corrections section. Ingest turns these into `preference` notes with linked evidence. A preference's status is calculated in the index, and it becomes confirmed only after you accept it in `/brief`.
 
+**History.** `/backup` first commits each headless run that published files, one commit per run, with a message `commit_runs.py` builds from the run's records (no model writes it). Each carries `Jarvis-Command`, `Jarvis-Run` and `Jarvis-Role` trailers, so `git log` reads as a handoff log: `git log --grep 'Jarvis-Command: ingest'` lists the ingest runs.
+
 | Name | Role | Concrete artifacts |
 |---|---|---|
 | **Jarvis** | The vault / product | this repo, `jarvis-*` systemd units |
```

- [ ] **Step 4: Run and watch them pass.** Same two commands, both `exit=0`. Lint: `0 errors`. Commit: `git add .claude/commands/backup.md .claude/commands/setup.md system/scripts/update_template.sh README.md system/tests/commands.bats system/tests/remote.bats && git commit -m "feat(backup): commit each headless run first; setup and updates set the cutover"`.

### Task 3: `debrief_prep.sh` lists vault commits from every author

**Files:**
- Modify: `system/scripts/debrief_prep.sh`
- Test: `system/tests/prep.bats`

- [ ] **Step 1: Write the failing test:**

```diff
diff --git a/system/tests/prep.bats b/system/tests/prep.bats
index e65f162..74a271b 100644
--- a/system/tests/prep.bats
+++ b/system/tests/prep.bats
@@ -126,6 +126,15 @@ codebase() {  # <name> <path>
   [ "$status" -eq 1 ]
 }
 
+@test "debrief_prep: the vault section lists commits from every author" {
+  commit_at "$V" 2026-10-01T09:00:00-06:00 "mine"
+  commit_at "$V" 2026-10-01T10:00:00-06:00 "from the other machine" other@example.com
+  run "$DP" 2026-10-01
+  [ "$status" -eq 0 ]
+  grep -qE '^- 09:00 [0-9a-f]+ mine$' "$IN/git.md"
+  grep -qE '^- 10:00 [0-9a-f]+ from the other machine$' "$IN/git.md"
+}
+
 @test "debrief_prep: codebase sections list only your commits on local branches" {
   C="$BATS_TEST_TMPDIR/app"
   git init -q "$C"
```

- [ ] **Step 2: Run and watch it fail.** `bats system/tests/prep.bats > system/logs/t3.log 2>&1; echo "exit=$?"; grep '^not ok' system/logs/t3.log`. Expected: `exit=1`, only "debrief_prep: the vault section lists commits from every author".

- [ ] **Step 3: Apply the implementation:**

```diff
diff --git a/system/scripts/debrief_prep.sh b/system/scripts/debrief_prep.sh
index 5def01b..cb56849 100755
--- a/system/scripts/debrief_prep.sh
+++ b/system/scripts/debrief_prep.sh
@@ -15,14 +15,15 @@ prep_init debrief_prep "$@"
 # These functions run inside prep_write's `||` context, where bash disables errexit, so every
 # failure must return explicitly.
 
-# One "## <name>" section per repo. When the repo has user.email configured, only that author's
-# commits are listed, so a shared work repo shows your day rather than the whole team's. Local
-# branches only: remote-tracking refs (the template remote included) are other people's history.
-repo_log() {  # <name> <path>
+# One "## <name>" section per repo. In a codebase with user.email configured, only that author's
+# commits are listed, so a shared work repo shows your day rather than the whole team's. The vault
+# lists every author: its commits come from scripts and other machines (two-machines spec §4.4).
+# Local branches only: remote-tracking refs (the template remote included) are other people's history.
+repo_log() {  # <name> <path> [all]
   local email log
   local -a author=()
   email="$(git -C "$2" config user.email 2>/dev/null || true)"
-  [[ -z "$email" ]] || author=(--author="$email")
+  [[ -z "$email" || "${3:-}" == all ]] || author=(--author="$email")
   log="$(git -C "$2" log --branches --no-merges "${author[@]}" \
     --since="${PREP_DATE}T00:00:00" --until="${PREP_DATE}T23:59:59" \
     --date=format-local:%H:%M --format='- %ad %h %s')" || return 1
@@ -31,7 +32,7 @@ repo_log() {  # <name> <path>
 
 git_md() {
   local name path
-  repo_log vault "$VAULT_ROOT" || prep_unavailable "git: git log failed for the vault"
+  repo_log vault "$VAULT_ROOT" all || prep_unavailable "git: git log failed for the vault"
   while IFS= read -r name; do
     path="$(codebase_get "$name" path)"
     if [[ -z "$path" ]] || ! git -C "$path" rev-parse --git-dir >/dev/null 2>&1; then
```

- [ ] **Step 4: Run and watch it pass.** Same command, `exit=0`. Then the gate (exit 0, 15 PASS) and lint (`0 errors`). Commit: `git add system/scripts/debrief_prep.sh system/tests/prep.bats && git commit -m "feat(debrief): the vault's git log lists every author"`.

### Task 4: Live acceptance and status

**Files:**
- Create: `docs/superpowers/spikes/<date>-plan-8b-acceptance.md`, `docs/superpowers/plans/<date>-plan-8b-outcomes.md`
- Modify: `docs/superpowers/plans/2026-09-30-jarvis-roadmap.md` (Plan 8 row), `README.md` (Status table)

Live runs cost money (an ingest, plus about $0.26 for a brief and up to $0.20 for its calendar fetch). Run them only in a throwaway clone. `run_headless.sh` and the headless commands do not change, so the Plan 4a acceptance steps are not re-run (spec §8.1).

- [ ] **Step 1: Throwaway clone with the cutover set first.** The cutover must exist before the runs, or `commit_runs.py` would write it afterwards and skip them:

```bash
A=${XDG_CACHE_HOME:-$HOME/.cache}/jarvis-accept; rm -rf "$A" && git clone -q -b feat/plan-8b "$(git rev-parse --show-toplevel)" "$A/vault" && cd "$A/vault" && cp system/config.example.md system/config.md && git config core.hooksPath .githooks && system/scripts/commit_runs.py --init-cutover; cat system/logs/commit_runs.since
```

- [ ] **Step 2: One headless ingest and one brief** (spec §8.1 item 8b). In the same clone, with `claude` on `PATH` (a login shell):

```bash
mkdir -p raw/work/notes && printf -- '---\ntype: session_digest\npartition: work\ncodebase: "vault"\nsession_id: "accept-8b"\ncreated_at: "%s"\n---\n## Facts\n- The nightly export job runs at 02:00 and writes its files to the billing bucket.\n' "$(date -Iseconds)" > raw/work/notes/accept-8b.md
system/scripts/run_headless.sh ingest raw/work/notes/accept-8b.md > "$A/ingest.out" 2>&1; echo "ingest exit=$?"
system/scripts/brief_prep.sh; system/scripts/run_headless.sh brief > "$A/brief.out" 2>&1; echo "brief exit=$?"
```

Expected: both `exit=0`, and each run's `publish.json` lists published files.

- [ ] **Step 3: Commit the runs.** `system/scripts/commit_runs.py; echo "exit=$?"; git log -2 --format='%B%x00'`, then `system/scripts/commit_runs.py; echo "again exit=$?"`. Expected:
  - `exit=0`, two output lines (`<run_id> <sha>`), ingest first;
  - `ingest(work): create <Note>…` with one `<decision> <target> <- raw/work/notes/accept-8b.md` line per decision, and `brief <date>: briefings/<date>.md` with its published line;
  - trailers `Jarvis-Command`, `Jarvis-Run` (the run ids) and `Jarvis-Role: standalone`; each commit holds only its run's paths (`git show --name-only`);
  - the second call prints nothing, `again exit=0`.

  Then `rm -rf "$A"`.

- [ ] **Step 4: Record and status.**
  - **Acceptance record:** each run's exit and published paths, the two commit messages (subjects and trailers; the brief's content stays out), the gate, a verdict.
  - **Roadmap Plan 8 row:** 8b complete with links; 8c next.
  - **README Status:** 8b Complete with links; 8c Next.
  - **Outcomes doc** from the ledger.
  - Gate, lint, then commit: `docs: Plan 8b acceptance, status and outcomes`.
