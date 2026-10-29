"""status_refs.py: the brief's prep marks a GitHub pull request, issue or Work Order that is no longer open (#353)."""
import json
import os
import subprocess
import sys

import pytest

from helpers import REPO

SCRIPT = REPO / "system/scripts/status_refs.py"
GH = """#!/bin/bash
# a stub gh: `gh api repos/<o>/<r>/issues/<n>` answers from $GH_FIXTURES/<o>_<r>_<n>.json, sleeps on a .hang file
f="$GH_FIXTURES/$(sed 's|^repos/||; s|/issues/|_|; s|/|_|' <<< "$2").json"
[[ -e "${f%.json}.hang" ]] && sleep 5
[[ -e "$f" ]] || { echo "gh: Not Found (HTTP 404)" >&2; exit 1; }
cat "$f"
"""


@pytest.fixture
def prep(tmp_path):
    d, bin_, fx = tmp_path / "prep", tmp_path / "bin", tmp_path / "fixtures"
    for p in (d, bin_, fx):
        p.mkdir()
    (bin_ / "gh").write_text(GH)
    (bin_ / "gh").chmod(0o755)
    (d / "orders.json").write_text(json.dumps({"v": 1, "items": [{"id": "2026-10-20-docs-sweep", "state": "done"}]}))
    return d, fx


def fixture(fx, ref, **body):
    (fx / f"{ref}.json").write_text(json.dumps(body))


def run(d, *repos, timeout="5"):
    env = {**os.environ, "PATH": f"{d.parent / 'bin'}:{os.environ['PATH']}", "GH_FIXTURES": str(d.parent / "fixtures"),
           "TZ": "America/Denver", "STATUS_TIMEOUT": timeout}
    return subprocess.run([sys.executable, str(SCRIPT), str(d), str(d / "orders.json"), *repos], env=env,
                          capture_output=True, text=True)


def test_closed_and_merged_references_are_marked_in_local_time_and_open_ones_left(prep):
    d, fx = prep
    fixture(fx, "o_r_296", state="closed", closed_at="2026-10-21T14:16:25Z",
            pull_request={"merged_at": "2026-10-21T14:16:25Z"})
    fixture(fx, "o_r_7", state="closed", closed_at="2026-10-20T15:00:00Z", pull_request=None)
    fixture(fx, "o_r_8", state="open", closed_at=None)
    (d / "yesterday.md").write_text("PR https://github.com/o/r/pull/296 is open; issue https://github.com/o/r/issues/7 "
                                    "waits; https://github.com/o/r/issues/8 too.\n")
    r = run(d, "o/r")
    assert r.returncode == 0, r.stderr
    assert (d / "yesterday.md").read_text() == (
        "PR https://github.com/o/r/pull/296 (merged 2026-10-21 08:16) is open; issue https://github.com/o/r/issues/7 "
        "(closed 2026-10-20) waits; https://github.com/o/r/issues/8 too.\n")
    assert r.stdout.strip() == "- status: ok (3 checked, 2 closed)"


def test_short_forms_orders_links_failures_and_repeats(prep):
    d, fx = prep
    fixture(fx, "o_r_3", state="closed", closed_at="2026-10-20T15:00:00Z", pull_request=None)
    fixture(fx, "o_r_296", state="closed", closed_at="2026-10-21T14:16:25Z",
            pull_request={"merged_at": "2026-10-21T14:16:25Z"})
    (fx / "o_r_9.hang").write_text("")
    fixture(fx, "o_r_9", state="open")
    (d / "now.md").write_text("- see o/r#3 and [the PR](https://github.com/o/r/pull/296)\n"
                              "- order 2026-10-20-docs-sweep; notes 2026-10-21-notes; PR #296 again\n"
                              "- missing https://github.com/o/r/issues/404 and slow https://github.com/o/r/issues/9\n")
    (d / "people.md").write_text("- o/r#3 (closed 2026-10-20) was marked before\n")
    r = run(d, "o/r", timeout="1")
    assert r.returncode == 0, r.stderr
    assert (d / "now.md").read_text() == (
        "- see o/r#3 (closed 2026-10-20) and [the PR](https://github.com/o/r/pull/296) (merged 2026-10-21 08:16)\n"
        "- order 2026-10-20-docs-sweep (done); notes 2026-10-21-notes; PR #296 (merged 2026-10-21 08:16) again\n"
        "- missing https://github.com/o/r/issues/404 (unverified: gh failed) and slow https://github.com/o/r/issues/9 "
        "(unverified: timeout)\n")
    assert (d / "people.md").read_text() == "- o/r#3 (closed 2026-10-20) was marked before\n"
    assert r.stdout.strip() == "- status: unverified: 2 of 5 references could not be checked (3 closed)"


def test_a_bare_number_needs_exactly_one_repository_and_twenty_references_at_most(prep):
    d, fx = prep
    (d / "away.md").write_text("PR #12 shipped\n" + "".join(f"https://github.com/o/r/issues/{n}\n" for n in range(100, 121)))
    for n in range(100, 121):
        fixture(fx, f"o_r_{n}", state="open")
    r = run(d, "o/r", "o/s")
    text = (d / "away.md").read_text()
    assert "PR #12 (unverified: ambiguous)" in text
    assert text.endswith("https://github.com/o/r/issues/120\n")   # the 21st is left as written
    assert r.stdout.strip() == "- status: unverified: 1 of 20 references could not be checked (0 closed)"


def test_usage_error_exits_2(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 2
