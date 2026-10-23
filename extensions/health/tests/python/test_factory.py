"""The factory metrics (health scorecard spec §3.2) with a stub gh on PATH: defect recurrences after a gate date,
first-push CI read once per PR and cached in the history, review-fix commits, and the half left out without gh or a
GitHub template_remote."""
import json
import os
from datetime import date

import pytest

DAY = date(2026, 10, 26)
STUB = """#!/bin/bash
echo "$*" >> "$STUB_DIR/calls"
case "$1 $2" in
  "pr list") cat "$STUB_DIR/prs.json" ;;
  "api "*) sha="${2#*/commits/}"; sha="${sha%%/*}"; [[ -f "$STUB_DIR/$sha.json" ]] || exit 1; cat "$STUB_DIR/$sha.json" ;;
  *) exit 1 ;;
esac
"""


@pytest.fixture
def gh(tmp_path, monkeypatch, config):
    """gh(prs, checks): a stub gh serving the merged PRs and each sha's check runs; returns its call log."""
    d = tmp_path / "gh"
    d.mkdir()
    (d / "gh").write_text(STUB)
    (d / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{d}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STUB_DIR", str(d))
    config('template_remote: "git@github.com:example/foundry.git"',
           'health_defect_gates: {C3: "2026-10-20"}')

    def serve(prs, checks):
        (d / "prs.json").write_text(json.dumps(prs))
        for sha, conclusions in checks.items():
            (d / f"{sha}.json").write_text(json.dumps({"check_runs": [{"conclusion": c} for c in conclusions]}))
        return d / "calls"
    return serve


def pr(n, merged, labels=(), commits=("first",)):
    return {"number": n, "mergedAt": f"{merged}T12:00:00Z", "labels": [{"name": x} for x in labels],
            "commits": [{"oid": f"sha{n}{i}", "messageHeadline": c, "messageBody": ""} for i, c in enumerate(commits)]}


def by_metric(rows):
    return {r["metric"]: r for r in rows if r.get("metric")}


def test_defects_count_fix_prs_per_class_and_recurrences_after_the_gate(h, vault, gh):
    gh([pr(1, "2026-10-19", ["defect:C3"]), pr(2, "2026-10-22", ["defect:C3"]), pr(3, "2026-10-22", ["defect:C7"]),
        pr(4, "2026-10-23")], {})
    rows = by_metric(h.compute(vault, DAY))
    d = rows["defect_recurrence"]
    assert (d["value"], d["state"]) == (1, "breach")
    assert d["text"] == "1 (#2 C3); fix PRs: C3 2, C7 1"


def test_first_push_green_reads_each_pr_once_then_the_cache(h, vault, gh):
    calls = gh([pr(1, "2026-10-20"), pr(2, "2026-10-21"), pr(3, "2026-10-22")],
               {"sha10": ["success", "skipped"], "sha20": ["failure", "success"], "sha30": ["success"]})
    lines = h.score(vault, DAY, dry=False)
    rows = by_metric(h.records(h.history_path(vault, DAY)))
    assert (rows["first_push_green"]["value"], rows["first_push_green"]["state"]) == (67, "breach")
    assert rows["first_push_green"]["text"] == "67% (2 of 3)"
    assert any("First-push CI green: 67% (2 of 3)" in x for x in lines)
    assert sum("check-runs" in c for c in calls.read_text().splitlines()) == 3
    # The next day reads no check runs again: every PR is in the cache.
    h.score(vault, date(2026, 10, 27), dry=False)
    assert sum("check-runs" in c for c in calls.read_text().splitlines()) == 3


def test_an_unread_pr_is_named_and_left_for_a_later_day(h, vault, gh):
    gh([pr(1, "2026-10-20"), pr(2, "2026-10-21")], {"sha10": ["success"]})
    row = by_metric(h.compute(vault, DAY))["first_push_green"]
    assert row["text"] == "100% (1 of 1); 1 PRs unread"
    cached = [r for r in h.compute(vault, DAY) if r.get("cache")]
    assert cached == [{"date": "2026-10-26", "cache": "first_push", "pr": 1, "green": True}]


def test_review_fix_commits_per_pr(h, vault, gh):
    gh([pr(1, "2026-10-20", commits=("feat: x", "Address review on #1", "review fix: names")),
        pr(2, "2026-10-21", commits=("docs: y",))], {"sha10": ["success"], "sha20": ["success"]})
    row = by_metric(h.compute(vault, DAY))["review_fixes"]
    assert (row["value"], row["state"]) == (1.0, "trend")
    assert row["text"] == "1.0 per PR (2 over 2 PRs)"


def test_a_failed_pr_list_makes_the_factory_half_unavailable(h, vault, gh):
    calls = gh([], {})
    (calls.parent / "prs.json").unlink()
    rows = by_metric(h.compute(vault, DAY))
    for m in ("defect_recurrence", "first_push_green", "review_fixes"):
        assert rows[m]["state"] == "unavailable"


def test_the_factory_half_is_left_out_without_gh_or_a_github_remote(h, vault, config, monkeypatch, tmp_path):
    config('template_remote: "git@github.com:example/foundry.git"')
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert "first_push_green" not in by_metric(h.compute(vault, DAY))
    config('template_remote: "git@gitlab.example.com:example/foundry.git"')
    assert h.github_repo(h.config(vault)) == ""


@pytest.mark.parametrize("remote, repo", [("git@github.com:o/r.git", "o/r"), ("https://github.com/o/r", "o/r"),
                                          ("https://github.com/o/r.git/", "o/r"), ("", "")])
def test_github_repo(h, remote, repo):
    assert h.github_repo({"template_remote": remote}) == repo
