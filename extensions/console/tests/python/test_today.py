"""today.py --json and --check (console C1 spec §4, plan Task 3)."""
import ast
from datetime import date, timedelta
from pathlib import Path

from conftest import EXT, active, now_page, order, project, run, today_json, write


def fixture(vault: Path, day: str) -> None:
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


def test_today_has_every_part_for_each_partition(vault, day):
    fixture(vault, day)
    out = today_json(vault)
    assert out["v"] == 1 and out["date"] == day and out["errors"] == []
    assert set(out) == {"v", "date", "stamps", "partitions", "calendar", "orders", "pipeline", "foreman_url", "errors"}
    assert set(out["partitions"]) == {"work", "personal"}
    for part in out["partitions"].values():
        assert set(part) == {"tiles", "projects", "also_active", "today", "now", "unparsed", "actions"}
    assert out["calendar"] == [{"start": "09:30", "end": "10:00", "title": "Standup"}]
    assert out["pipeline"] == {"sources": ["calendar: ok", "triage: failed: auth: expired"], "quarantine": 0, "alerts": 2}
    assert out["foreman_url"] == "https://claude.ai/code/session_example"
    assert [o["id"] for o in out["orders"]["open"]] == ["2026-10-23-queued-one"]


def test_tiles_count_from_the_parts(vault, day):
    fixture(vault, day)
    work = today_json(vault)["partitions"]["work"]
    assert work["tiles"] == {"focus": 2, "stale": 0, "needs_you": 2, "waiting": 1, "overdue": 1, "orders": 1}
    assert today_json(vault)["partitions"]["personal"]["tiles"]["needs_you"] == 1


def test_project_card_counts_now_lines_and_prs_by_match(vault, day):
    fixture(vault, day)
    alpha, beta = today_json(vault)["partitions"]["work"]["projects"]
    assert (alpha["rank"], alpha["link"], alpha["now_lines"], alpha["prs"]) == (1, "Alpha", 2, 1)
    assert (beta["rank"], beta["now_lines"], beta["prs"]) == (2, 0, 0)
    lines = today_json(vault)["partitions"]["work"]["now"]
    assert [ln["project"] for ln in lines] == ["Alpha", "Alpha", ""]


def test_today_list_is_first_next_per_project_at_most_five(vault, day):
    fixture(vault, day)
    entries = "".join(f"- [[P{i}]]\n" for i in range(7))
    active(vault, "work", entries)
    for i in range(7):
        project(vault, "work", f"P{i}", f"- [ ] step {i}a\n- [ ] step {i}b\n")
    today = today_json(vault)["partitions"]["work"]["today"]
    assert today == [{"text": f"step {i}a", "project": f"P{i}"} for i in range(5)]


def test_a_failing_source_adds_one_error_and_exit_stays_zero(vault, day):
    fixture(vault, day)
    write(vault, "system/scripts/active_projects.py", "import sys\nsys.exit(1)\n")
    r = run(vault, "--json")
    assert r.returncode == 0
    import json
    out = json.loads(r.stdout)
    assert out["errors"] == ["active_projects.py: exit 1"]
    assert out["partitions"]["work"]["projects"] == [] and len(out["partitions"]["work"]["now"]) == 3


def test_missing_prep_files_leave_calendar_and_actions_empty(vault, day):
    fixture(vault, day)
    (vault / f"system/logs/inputs/{day}/calendar.tsv").unlink()
    (vault / f"system/logs/inputs/{day}/actions.md").unlink()
    out = today_json(vault)
    assert out["calendar"] == [] and out["partitions"]["work"]["actions"] == []
    assert out["errors"] == ["meeting actions: no actions.md in today's prep", "calendar: no calendar.tsv in today's prep"]


def test_no_prep_yet_is_one_error(vault, day):
    fixture(vault, day)
    import shutil
    shutil.rmtree(vault / f"system/logs/inputs/{day}")
    out = today_json(vault)
    assert out["errors"] == [f"prep: no prep for {day} yet"]
    assert out["calendar"] == [] and out["stamps"]["prep"] == ""


def test_partitions_never_mix(vault, day):
    fixture(vault, day)
    out = today_json(vault)
    work, personal = out["partitions"]["work"], out["partitions"]["personal"]
    assert all("garden" not in ln["statement"] for ln in work["now"])
    assert [ln["statement"] for ln in personal["now"]] == ["Note to the garden club"]
    assert [a["text"] for a in work["actions"]] == ["Send the metrics"]
    assert [a["text"] for a in personal["actions"]] == ["Plant the bulbs"]
    assert personal["projects"] == [] and personal["tiles"]["orders"] == 0


def test_check_reports_a_server_that_is_not_answering(vault, day):
    fixture(vault, day)
    write(vault, "system/config.md", (vault / "system/config.md").read_text().replace(
        "---\n", "---\nconsole_port: \"1\"\n", 1).replace("type: config\n", "type: config\n", 1))
    r = run(vault, "--check")
    assert r.returncode == 1
    assert r.stdout.startswith("failed: network: the console is not answering on 127.0.0.1:1")


def test_usage_exits_two(vault):
    assert run(vault).returncode == 2
    assert run(vault, "--yaml").returncode == 2


def test_imports_only_vaultlib_api():
    tree = ast.parse((EXT / "scripts" / "today.py").read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert {m for m in mods if m.startswith("vaultlib")} == {"vaultlib.api"}
