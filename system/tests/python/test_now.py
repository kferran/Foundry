"""The Now page (Now page spec): vaultlib/now.py and system/scripts/now.py."""
import fcntl
import os
import shutil
import subprocess
import sys

from helpers import REPO, write
from vaultlib import now

TODAY = "2026-10-09"
CONFIG = ('---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
          'remote_mode: "none"\ndefault_partition: "work"\n---\n')


def page(vault, partition="work"):
    return (vault / "wiki" / partition / "Now.md").read_text(encoding="utf-8")


def prepare(vault):
    shutil.copytree(REPO / "system" / "templates", vault / "system" / "templates", dirs_exist_ok=True)
    write(vault, "system/config.md", CONFIG)


def gh_stub(tmp_path, state="MERGED", rc=0):
    stub = tmp_path / "gh"
    stub.write_text(f"#!/bin/bash\necho \"$@\" >> {tmp_path}/gh.args\necho {state}\nexit {rc}\n")
    stub.chmod(0o755)
    return str(stub)


def order(vault, item_id, state, partition="work"):
    write(vault, f"raw/{partition}/nightshift/{item_id}.md",
          f'---\ntype: "nightshift_item"\nid: "{item_id}"\npartition: "{partition}"\nkind: "plan"\nstate: "{state}"\n---\n')


def test_add_creates_the_page_and_files_each_kind_under_its_section(vault):
    prepare(vault)
    assert now.add(vault, "work", "owed", "Review the export PR", TODAY, "Blake Sample",
                   "https://github.com/acme/shop/pull/7")[0] == "added"
    now.add(vault, "work", "waiting", "Access to the staging logs", TODAY, "Blake Sample", "EX-12")
    now.add(vault, "work", "draft", "Reply to the vendor about the delay", TODAY, "vendor")
    text = page(vault)
    assert text.startswith('---\ntype: concept\ntags: [now]\ncompiled_at: "2026-10-09"\npartition: work\n---\n')
    needs, waiting = text.split("## Needs you\n")[1].split("## Waiting\n")
    assert needs.strip().splitlines() == [
        "- [ ] owed: Review the export PR (Blake Sample, since 2026-10-09, https://github.com/acme/shop/pull/7)",
        "- [ ] draft: Reply to the vendor about the delay (vendor, since 2026-10-09)"]
    assert waiting.strip().splitlines() == [
        "- [ ] waiting: Access to the staging logs (Blake Sample, since 2026-10-09, EX-12)"]


def test_the_same_open_statement_is_not_added_twice(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Send the report", TODAY)
    assert now.add(vault, "work", "owed", "Send the report", "2026-10-10") == (
        "exists", "- [ ] owed: Send the report (since 2026-10-09)")
    assert page(vault).count("Send the report") == 1


def test_a_statement_with_parentheses_parses(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Fix the 409 (export) bug", TODAY)
    assert now.add(vault, "work", "owed", "Fix the 409 (export) bug", TODAY)[0] == "exists"


def test_invalid_lines_are_refused(vault):
    prepare(vault)
    for args in (("shared", "owed", "x", ""), ("work", "decision", "x", ""), ("work", "owed", "a\nb", ""),
                 ("work", "owed", " ", ""), ("work", "owed", "x", "A, B")):
        try:
            now.add(vault, args[0], args[1], args[2], TODAY, args[3])
        except ValueError:
            continue
        raise AssertionError(f"accepted {args}")
    assert not (vault / "wiki/work/Now.md").exists()


def test_a_missing_section_heading_is_added_back(vault):
    prepare(vault)
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: []\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          "---\n# Now\n\n## Needs you\n- [ ] owed: A (since 2026-10-01)\n")
    now.add(vault, "work", "waiting", "B", TODAY)
    assert page(vault).endswith("## Needs you\n- [ ] owed: A (since 2026-10-01)\n\n## Waiting\n"
                                "- [ ] waiting: B (since 2026-10-09)\n")


def test_hand_ticks_are_stamped_and_closed_lines_pruned_after_seven_days():
    text = ("## Needs you\n- [x] owed: Ticked (since 2026-10-01)\n- [-] owed: Dropped (since 2026-10-01)\n"
            "- [x] owed: Kept (since 2026-10-01) _(closed: ticked 2026-10-02)_\n"
            "- [x] owed: Gone (since 2026-10-01) _(closed: PR merged 2026-10-01)_\n- [ ] owed: Open (since 2026-10-01)\n")
    assert now.stamp_and_prune(text, TODAY) == (
        "## Needs you\n- [x] owed: Ticked (since 2026-10-01) _(closed: ticked 2026-10-09)_\n"
        "- [-] owed: Dropped (since 2026-10-01) _(closed: ticked 2026-10-09)_\n"
        "- [x] owed: Kept (since 2026-10-01) _(closed: ticked 2026-10-02)_\n- [ ] owed: Open (since 2026-10-01)\n")


def test_check_closes_a_merged_or_closed_pr_and_leaves_an_open_one(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "Merged one", "2026-10-08", evidence="https://github.com/acme/shop/pull/7")
    alerts = []
    assert now.check(vault, TODAY, alerts.append, gh_stub(tmp_path, "MERGED")) == 1
    assert ("- [x] owed: Merged one (since 2026-10-08, https://github.com/acme/shop/pull/7) "
            "_(closed: PR merged 2026-10-09)_") in page(vault)
    now.add(vault, "work", "owed", "Closed one", TODAY, evidence="https://github.com/acme/shop/pull/8")
    now.check(vault, TODAY, alerts.append, gh_stub(tmp_path, "CLOSED"))
    assert "_(closed: PR closed 2026-10-09)_" in page(vault).split("Closed one")[1]
    now.add(vault, "work", "owed", "Open one", TODAY, evidence="https://github.com/acme/shop/pull/9")
    assert now.check(vault, TODAY, alerts.append, gh_stub(tmp_path, "OPEN")) == 0
    assert "- [ ] owed: Open one" in page(vault)
    assert alerts == []


def test_check_closes_a_finished_work_order_only(vault, tmp_path):
    prepare(vault)
    order(vault, "2026-10-08-done-item", "done")
    order(vault, "2026-10-08-running-item", "running")
    now.add(vault, "work", "waiting", "The done item", TODAY, evidence="2026-10-08-done-item")
    now.add(vault, "work", "waiting", "The running item", TODAY, evidence="2026-10-08-running-item")
    now.add(vault, "work", "waiting", "A ticket", TODAY, evidence="EX-12")
    assert now.check(vault, TODAY, [].append, gh_stub(tmp_path)) == 1
    text = page(vault)
    assert "- [x] waiting: The done item (since 2026-10-09, 2026-10-08-done-item) _(closed: Work Order done 2026-10-09)_" in text
    assert "- [ ] waiting: The running item" in text
    assert "- [ ] waiting: A ticket" in text
    assert not (tmp_path / "gh.args").exists()


def test_a_failed_check_leaves_the_line_open_and_the_third_failure_alerts_once(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "PR", TODAY, evidence="https://github.com/acme/shop/pull/7")
    alerts = []
    for _ in range(4):
        now.check(vault, TODAY, alerts.append, gh_stub(tmp_path, "", rc=1))
    assert "- [ ] owed: PR" in page(vault)
    assert len(alerts) == 1 and "failed 3 times today" in alerts[0]
    assert len((vault / "system/logs/now-2026-10.jsonl").read_text().splitlines()) == 4
    now.check(vault, TODAY, alerts.append, str(tmp_path / "no-such-gh"))
    assert "- [ ] owed: PR" in page(vault)


def test_check_writes_only_when_it_closes_a_line_and_the_next_write_stamps_hand_ticks(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "A", TODAY)
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("- [ ] owed: A", "- [x] owed: A"))
    before = path.read_text()
    now.check(vault, TODAY, [].append, gh_stub(tmp_path))
    assert path.read_text() == before  # fewer server rewrites of a page the client edits
    now.add(vault, "work", "owed", "B", TODAY, evidence="https://github.com/acme/shop/pull/7")
    assert "- [x] owed: A (since 2026-10-09) _(closed: ticked 2026-10-09)_" in page(vault)


def test_check_keeps_a_tick_made_while_gh_runs(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "Call vendor", TODAY)
    now.add(vault, "work", "owed", "PR", TODAY, evidence="https://github.com/acme/shop/pull/7")
    stub = tmp_path / "gh"
    stub.write_text(f"#!/bin/bash\nsed -i 's/- \\[ \\] owed: Call vendor/- [x] owed: Call vendor/' "
                    f"{vault}/wiki/work/Now.md\necho MERGED\n")
    stub.chmod(0o755)
    assert now.check(vault, TODAY, [].append, str(stub)) == 1
    text = page(vault)
    assert "- [x] owed: Call vendor (since 2026-10-09)" in text
    assert "_(closed: PR merged 2026-10-09)_" in text


def test_a_failed_pr_check_skips_the_other_prs_this_tick(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "One", TODAY, evidence="https://github.com/acme/shop/pull/7")
    now.add(vault, "personal", "owed", "Two", TODAY, evidence="https://github.com/acme/shop/pull/8")
    order(vault, "2026-10-08-done-item", "done")
    now.add(vault, "work", "waiting", "Order", TODAY, evidence="2026-10-08-done-item")
    assert now.check(vault, TODAY, [].append, str(tmp_path / "no-such-gh")) == 1  # the Work Order still closes
    assert len((vault / "system/logs/now-2026-10.jsonl").read_text().splitlines()) == 1


def test_a_reopened_line_loses_its_stamp():
    text = "- [ ] owed: Again (since 2026-10-01) _(closed: ticked 2026-10-02)_\n"
    assert now.stamp_and_prune(text, TODAY) == "- [ ] owed: Again (since 2026-10-01)\n"


def test_seed_turns_wikilinks_into_plain_text(vault):
    prepare(vault)
    write(vault, "briefings/2026-10-08.md", "### 1. Objectives\n- [ ] DTCC: Change ([[dtcc-c1|C1]]) and [[Plan]]\n### 2.\n")
    now.seed(vault, "work", TODAY)
    assert now.open_lines(page(vault)) == ["- [ ] owed: DTCC: Change (C1) and Plan (since 2026-10-08)"]


def test_seed_takes_the_previous_briefs_open_objectives_once(vault):
    prepare(vault)
    write(vault, "briefings/archive/2026-10/2026-10-07.md",
          "---\ntype: briefing\n---\n### 1. Active Objectives\n- [ ] **Ask** about the 409 _(open since 2026-10-01, 6 days)_\n"
          "- [ ] **stale** **Old** thing _(open since 2026-09-20)_\n- [x] **Done**\n- [ ] DTCC: Change ([[c1]])\n"
          "### 2. Unavailable Sources\n- [ ] not an objective\n")
    assert now.seed(vault, "work", "2026-10-09") == 3
    assert now.open_lines(page(vault)) == [
        "- [ ] owed: **Ask** about the 409 (since 2026-10-01)",
        "- [ ] owed: **Old** thing (since 2026-09-20)",
        "- [ ] owed: DTCC: Change (c1) (since 2026-10-07)"]
    assert now.seed(vault, "work", "2026-10-09") == 0


def test_seed_with_no_earlier_briefing_creates_an_empty_page(vault):
    prepare(vault)
    assert now.seed(vault, "work", TODAY) == 0
    assert now.open_lines(page(vault)) == []
    assert now.seed(vault, "shared", TODAY) == 0


def cli(vault, *args, env=None):
    shutil.copytree(REPO / "system" / "scripts", vault / "system" / "scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    return subprocess.run([sys.executable, str(vault / "system/scripts/now.py"), *args], cwd=vault,
                          capture_output=True, text=True, env={**os.environ, **(env or {})})


def test_cli_add_list_and_usage(vault):
    prepare(vault)
    r = cli(vault, "add", "--partition", "work", "--kind", "owed", "--statement", "Send it", "--who", "Blake")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("added: - [ ] owed: Send it (Blake, since ")
    cli(vault, "add", "--partition", "personal", "--kind", "draft", "--statement", "Reply to Sam")
    out = cli(vault, "list").stdout.splitlines()
    assert out[0] == "## work" and out[1].startswith("- [ ] owed: Send it") and out[2] == "## personal"
    assert cli(vault, "list", "--partition", "personal").stdout.startswith("- [ ] draft: Reply to Sam")
    assert cli(vault, "add", "--partition", "shared", "--kind", "owed", "--statement", "x").returncode == 2
    assert cli(vault, "seed", "yesterday").returncode == 2


def test_cli_waits_for_run_lock_and_exits_4_when_busy(vault):
    prepare(vault)
    (vault / "system").mkdir(exist_ok=True)
    with open(vault / "system/run.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        r = cli(vault, "add", "--partition", "work", "--kind", "owed", "--statement", "x", env={"NOW_LOCK_WAIT": "0"})
    assert r.returncode == 4
    assert "run.lock busy" in r.stderr
    assert not (vault / "wiki/work/Now.md").exists()


def test_a_hand_written_line_is_listed_and_left_alone(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "A", TODAY)
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("## Waiting\n", "## Waiting\n- [ ] call the bank back\n"))
    assert now.check(vault, TODAY, [].append, gh_stub(tmp_path)) == 0
    assert now.open_lines(page(vault)) == ["- [ ] owed: A (since 2026-10-09)", "- [ ] call the bank back"]


def test_cli_add_seeds_the_missing_default_page_first(vault):
    prepare(vault)
    write(vault, "briefings/2026-10-01.md", "### 1. Objectives\n- [ ] **Old objective**\n### 2.\n")
    r = cli(vault, "add", "--partition", "work", "--kind", "owed", "--statement", "New")
    assert r.returncode == 0, r.stderr
    lines = now.open_lines(page(vault))
    assert lines[0] == "- [ ] owed: **Old objective** (since 2026-10-01)"
    assert lines[1].startswith("- [ ] owed: New (since ")


def test_cli_list_refuses_an_unknown_partition(vault):
    prepare(vault)
    assert cli(vault, "list", "--partition", "../x").returncode == 2
