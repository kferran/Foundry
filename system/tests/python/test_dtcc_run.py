import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from helpers import REPO, concept, write
from test_dtcc_map import repo
from vaultlib import dtcc_run

FX = REPO / "system" / "tests" / "fixtures" / "dtcc"
NOW = datetime(2026, 10, 6, 11, 30, tzinfo=timezone.utc)
MAP = """partition: work
hub: '[[Dtcc]]'
notice_keywords: ['\\bI&RS\\b', '\\binsurance\\b', '\\bannuit']
codebases:
  app: {ref: HEAD}
products:
  app-sub:
    page: app-sub
    notice_codes: [APP, SUB]
    codebase: app
    paths: [src/stl/]
    pin: v25-5
  stl:
    page: settlement-processing-for-insurance-stl
    notice_codes: [STL]
    codebase: app
    paths: [src/stl/, docs/gone.xlsx]
    pin: v25-3
    notes: ['[[StlBackground]]']
ignore: [PAR, RPL]
"""


@pytest.fixture
def env(vault: Path, tmp_path: Path, monkeypatch):
    stub = tmp_path / "stub"
    shutil.copytree(FX, stub)
    monkeypatch.setenv("FOUNDRY_DTCC_STUB", str(stub))
    r = repo(tmp_path)
    write(vault, "system/codebases/app.md", f'---\ntype: codebase\nname: "app"\npath: "{r}"\npartition: "work"\nsearch_globs: ["*"]\n---\n')
    write(vault, "wiki/work/entities/Dtcc.md", concept("work", "DTCC"))
    write(vault, "wiki/work/concepts/StlBackground.md", concept("work", "STL"))
    write(vault, "system/dtcc/map.yaml", MAP)
    return vault, stub


def notes(vault):
    return sorted(p.name for p in (vault / "wiki/work/changes").glob("*.md")) if (vault / "wiki/work/changes").exists() else []


def run(vault, *args, now=NOW):
    return dtcc_run.main(list(args), vault, now)


def test_no_map_is_inert(vault: Path, capsys):
    assert run(vault) == 0
    assert capsys.readouterr().out == ""
    assert not (vault / dtcc_run.STATE).exists()


def test_first_run_writes_only_gaps_and_conflicts(env):
    vault, _ = env
    assert run(vault) == 0
    assert notes(vault) == ["dtcc-conflict-decommission-2027-11-18-2027-11-17.md",
                            "dtcc-conflict-production-2027-04-25-2027-04-15.md",
                            "dtcc-gap-app-sub-v26-7.md", "dtcc-gap-stl-v26-7.md"]
    gap = (vault / "wiki/work/changes/dtcc-gap-stl-v26-7.md").read_text()
    assert "[[StlBackground]]" in gap and "[[Dtcc]]" in gap
    assert "docs/gone.xlsx (missing at HEAD)" in gap
    alerts = next((vault / "system/logs").glob("alerts_*.md")).read_text()
    assert "[dtcc]" in alerts and "docs/gone.xlsx" in alerts
    line = json.loads(next((vault / "system/logs").glob("dtcc_watch-*.jsonl")).read_text().splitlines()[-1])
    assert line["exit"] == 0 and line["notes"] == 4


def test_second_run_with_same_input_writes_nothing(env):
    vault, _ = env
    run(vault)
    before = notes(vault)
    assert run(vault) == 0
    assert notes(vault) == before


def test_page_change_and_new_version(env):
    vault, stub = env
    run(vault)
    p = stub / "settlement-processing-for-insurance-stl.html"
    p.write_text(p.read_text().replace("v26-7", "v26-8").replace("April 08, 2026", "September 30, 2026"))
    assert run(vault) == 0
    page = vault / f"wiki/work/changes/dtcc-page-stl-{NOW.astimezone().date().isoformat()}.md"
    assert "renamed" in page.read_text() and "v26-8" in page.read_text()
    assert (vault / "wiki/work/changes/dtcc-gap-stl-v26-8.md").exists()


def test_new_notices_route_to_product_ignore_or_unmapped(env):
    vault, stub = env
    run(vault)
    rss = stub / "all-important-notices.xml"
    extra = "".join(
        f'<item><guid>{n}</guid><link>https://files.dtcc.com/download/assets/{n}/p{n}</link><title>{n}</title>'
        f'<description>&lt;p&gt;{s}&lt;/p&gt;</description><pubDate>Tue, 06 Oct 2026 12:00:00 +00:00</pubDate></item>'
        for n, s in (("a9900", "I&amp;amp;RS spring release"), ("a9901", "Insurance PAR maintenance"), ("a9902", "Annuity data standards")))
    rss.write_text(rss.read_text().replace("</channel>", extra + "</channel>"))
    (stub / "pa9900").write_text("Category: INSURANCE & RETIREMENT SOLUTIONS\nThis release impacts: STL\nProduction Thursday, May 20, 2027\n")
    (stub / "pa9901").write_text("Category: INSURANCE & RETIREMENT SOLUTIONS\nThis release impacts: PAR\n")
    (stub / "pa9902").write_text("Category: INSURANCE & RETIREMENT SOLUTIONS\nNo product named.\n")
    assert run(vault) == 0
    n = (vault / "wiki/work/changes/dtcc-notice-a9900.md").read_text()
    assert 'kind: "notice"' in n and 'product: "stl"' in n and "Production 2027-05-20 (a9900)" in n
    assert not (vault / "wiki/work/changes/dtcc-notice-a9901.md").exists()
    assert 'kind: "unmapped"' in (vault / "wiki/work/changes/dtcc-notice-a9902.md").read_text()


def test_sanity_hold_keeps_state(env):
    vault, stub = env
    run(vault)
    state = json.loads((vault / dtcc_run.STATE).read_text())
    shutil.copy(FX / "record-layouts.html", stub / "app-sub.html")
    assert run(vault) == 1
    after = json.loads((vault / dtcc_run.STATE).read_text())
    assert after["pages"]["app-sub"] == state["pages"]["app-sub"]
    assert "held" in next((vault / "system/logs").glob("alerts_*.md")).read_text()


def test_flood_holds_then_accept_takes_the_baseline(env):
    vault, stub = env
    run(vault)
    before = notes(vault)
    cards = "".join(f'<div class="card"><h4 class="card__title">Doc {i}</h4><span class="card__date">May 01, 2026</span></div>'
                    for i in range(25))
    p = stub / "app-sub.html"
    p.write_text(p.read_text().replace("</body>", cards + "</body>"))
    assert run(vault) == 1
    assert notes(vault) == before
    assert run(vault, "--accept") == 0
    assert notes(vault) == before
    assert run(vault) == 0
    assert notes(vault) == before


def test_crash_between_notes_and_state_writes_no_duplicates(env):
    vault, stub = env
    run(vault)
    saved = (vault / dtcc_run.STATE).read_text()
    p = stub / "settlement-processing-for-insurance-stl.html"
    p.write_text(p.read_text().replace("STL User Guide", "STL User Guide 2"))
    run(vault)
    after_first = notes(vault)
    (vault / dtcc_run.STATE).write_text(saved)
    assert run(vault) == 0
    assert notes(vault) == after_first


def test_fetch_failure_is_exit_1_and_other_sources_run(env):
    vault, stub = env
    (stub / "irs-current-enhancements-release.html").unlink()
    assert run(vault) == 1
    assert (vault / "wiki/work/changes/dtcc-gap-stl-v26-7.md").exists()


def test_dry_run_writes_nothing(env, capsys):
    vault, _ = env
    assert run(vault, "--dry-run") == 0
    assert notes(vault) == []
    assert not (vault / dtcc_run.STATE).exists()
    assert "gap:stl:v26-7" in capsys.readouterr().out


def test_invalid_map_exits_2(env):
    vault, _ = env
    write(vault, "system/dtcc/map.yaml", MAP.replace("partition: work", "partition: nope"))
    assert run(vault) == 2
    assert notes(vault) == []


def test_check_reports_stale_paths(env, capsys):
    vault, _ = env
    assert run(vault, "--check") == 1
    assert "docs/gone.xlsx" in capsys.readouterr().out


def test_brief_lines_since_previous_briefing(env):
    vault, _ = env
    run(vault)
    write(vault, "briefings/2026-10-05.md", "# brief\n")
    lines = dtcc_run.brief_lines(vault, "2026-10-07")
    assert len(lines) == 4
    assert all(l.startswith("- [ ] DTCC: ") for l in lines)
    assert any("[[dtcc-conflict-production-2027-04-25-2027-04-15]]) — Production 2027-04-15 (a9809)" in l for l in lines)
    write(vault, "briefings/2026-10-07.md", "# brief\n")
    assert dtcc_run.brief_lines(vault, "2026-10-08") == []


def test_brief_lines_find_an_archived_previous_briefing(env):
    vault, _ = env
    run(vault)
    write(vault, "briefings/archive/2026-10/2026-10-07.md", "# brief\n")
    assert dtcc_run.brief_lines(vault, "2026-10-08") == []
