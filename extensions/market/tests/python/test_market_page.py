"""marketlib.page: the page reader, the brief's Market line and the after-publish step (spec §3.5; plan 3, rulings 3-5)."""
import json
import re
import shutil
import subprocess

import pytest

from market_helpers import FIXTURES, write_config
from marketlib import page

DAY = "2026-11-06"
PAGE = f"briefings/market/{DAY}.md"
WATCH = ('market_watch:\n  - {name: "Vendor A", group: vendors, newsroom: "https://vendor-a.example.com/news/"}\n'
         '  - {name: "Partner C", group: partners, feed: "https://partner-c.example.org/rss"}\n'
         '  - {name: "Runtime E", group: engineering, feed: "https://runtime-e.example.com/r.atom"}\n')
TOP = "Vendor A launched a rival product"


def put_page(vault, text=None, candidates=True):
    """The page, and (by default) today's candidates holding every link the page names."""
    dst = vault / PAGE
    dst.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        shutil.copy(FIXTURES / "page.md", dst)
    else:
        dst.write_text(text)
    if candidates:
        links = re.findall(r"\]\((https://[^)\s]+)\)", dst.read_text())
        folder = vault / "raw/market" / DAY
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "candidates.jsonl").write_text("".join(json.dumps({"link": link}) + "\n" for link in links))


def set_status(vault, status, day=DAY):
    (vault / "system/logs").mkdir(parents=True, exist_ok=True)
    (vault / "system/logs/market_run.json").write_text(json.dumps({"date": day, "status": status, "reason": ""}))


def market_alerts(vault, day=DAY):
    path = vault / "system/logs" / f"alerts_{day}.md"
    return [line for line in path.read_text().splitlines() if "[market]" in line] if path.exists() else []


class NowCalls:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)


def test_line_names_the_count_and_the_top_threat(vault):
    put_page(vault)
    assert page.line(vault, DAY) == f"Market: 5 changes, top: {TOP} (threat) [[briefings/market/{DAY}|market]]"


@pytest.mark.parametrize("status,want", [
    ("running", "Market: unavailable (still running)"), ("timeout", "Market: unavailable (timeout)"),
    ("busy", "Market: unavailable (busy)"), ("rejected", "Market: unavailable (rejected)"),
    ("failed", "Market: unavailable (failed)"), ("none", "No market changes"), (None, "Market: unavailable (no run)"),
])
def test_line_with_no_page_reads_the_run_status(vault, status, want):
    if status:
        set_status(vault, status)
    assert page.line(vault, DAY) == want


def test_a_stale_status_is_no_run(vault):
    set_status(vault, "ok", day="2026-11-05")
    assert page.line(vault, DAY) == "Market: unavailable (no run)"


def test_counts_come_from_the_items(vault):
    text = (FIXTURES / "page.md").read_text()
    head, _, _ = text.partition("## Threats")
    put_page(vault, head + "## Threats\n\n## Openings\n- **Partner C**: Opened a door. Fits. [x](https://p.example.org/1)\n"
             "\n## Watch\n- **Vendor B**: Hired. Noted. [y](https://b.example.com/2)\n\n## News\n\n## Proposed changes\n")
    assert page.line(vault, DAY).startswith("Market: 2 changes, top: Opened a door (opening) ")


def test_an_empty_page_is_no_market_changes(vault):
    text = (FIXTURES / "page.md").read_text()
    head, _, _ = text.partition("## Threats")
    put_page(vault, head + "## Threats\n\n## Openings\n\n## Watch\n\n## News\n\n## Proposed changes\n")
    assert page.line(vault, DAY) == "No market changes"


def test_a_page_missing_a_heading_still_reads(vault):
    put_page(vault, (FIXTURES / "page.md").read_text().replace("## News\n", ""))
    p = page.read(vault / PAGE)
    assert len(p.items["threat"]) == 2 and p.items["news"] == []
    assert page.line(vault, DAY).startswith("Market: ")


def test_threats_post_once_and_only_for_alert_groups(vault):
    write_config(vault, WATCH + "market_alert_groups: [vendors]\n")
    put_page(vault)
    page.after_publish(vault, DAY, run=NowCalls())
    lines = market_alerts(vault)
    assert len(lines) == 1
    assert f"Market threat: Vendor A: {TOP} https://vendor-a.example.com/news/1" in lines[0]
    page.after_publish(vault, DAY, run=NowCalls())
    page.after_publish(vault, "2026-11-07", run=NowCalls())
    assert len(market_alerts(vault)) == 1 and market_alerts(vault, "2026-11-07") == []


def test_no_alert_groups_means_every_known_group_posts(vault):
    write_config(vault, WATCH)
    put_page(vault)
    page.after_publish(vault, DAY, run=NowCalls())
    assert len(market_alerts(vault)) == 1   # Vendor A; "Unknown Co" is not on the watch list


def test_proposed_changes_become_one_owed_line_each(vault):
    write_config(vault, WATCH)
    put_page(vault)
    calls = NowCalls()
    page.after_publish(vault, DAY, run=calls)
    [argv] = calls.calls
    assert argv[:2] == ["system/scripts/now.py", "add"]
    assert argv[argv.index("--kind") + 1] == "owed" and argv[argv.index("--partition") + 1] == "work"
    assert argv[argv.index("--statement") + 1] == ("Review a proposed change to Project Alpha: "
                                                   "move the integration ahead of the next quarter")
    again = NowCalls()
    page.after_publish(vault, DAY, run=again)
    assert again.calls == []


def test_the_page_is_copied_to_the_inbox(vault):
    write_config(vault, WATCH)
    put_page(vault)
    page.after_publish(vault, DAY, run=NowCalls())
    assert (vault / f"raw/inbox/market-{DAY}.md").read_text() == (vault / PAGE).read_text()


def source_alerts(vault, day=DAY):
    path = vault / "system/logs" / f"alerts_{day}.md"
    return [line for line in path.read_text().splitlines() if "[market_source]" in line] if path.exists() else []


def test_a_page_partition_other_than_market_partition_skips_now_and_inbox(vault):
    write_config(vault, WATCH + "market_partition: work\n")
    put_page(vault, (FIXTURES / "page.md").read_text().replace("partition: work", "partition: personal"))
    calls = NowCalls()
    page.after_publish(vault, DAY, run=calls)
    assert calls.calls == []
    assert not (vault / f"raw/inbox/market-{DAY}.md").exists()
    assert len(source_alerts(vault)) == 1 and "personal" in source_alerts(vault)[0]


def test_a_threat_link_not_among_the_candidates_never_posts(vault):
    write_config(vault, WATCH)
    put_page(vault, candidates=False)
    page.after_publish(vault, DAY, run=NowCalls())
    assert market_alerts(vault) == []


def test_the_rec_is_short_and_a_failed_add_alerts_and_retries(vault):
    write_config(vault, WATCH)
    put_page(vault)

    class Refuse(NowCalls):
        def __call__(self, argv, **kw):
            super().__call__(argv, **kw)
            return subprocess.CompletedProcess(argv, 2)
    refuse = Refuse()
    page.after_publish(vault, DAY, run=refuse)
    [argv] = refuse.calls
    assert argv[argv.index("--rec") + 1] == f"review: proposed by the market page of {DAY}"
    assert len(source_alerts(vault)) == 1 and "now.py" in source_alerts(vault)[0]
    again = NowCalls()
    page.after_publish(vault, DAY, run=again)
    assert len(again.calls) == 1


def test_a_now_command_that_cannot_start_keeps_the_posted_state(vault):
    write_config(vault, WATCH)
    put_page(vault)

    def missing(argv, **kw):
        raise FileNotFoundError(argv[0])
    page.after_publish(vault, DAY, run=missing)
    page.after_publish(vault, DAY, run=NowCalls())
    assert len(market_alerts(vault)) == 1
