"""marketlib.run: the market fetch's run, state and --check (spec §3.2, amended M1, M11, M12, M13; plan rulings 1, 4)."""
import json
from datetime import date

import pytest

from market_helpers import FIXTURES, write_config
from marketlib import run

DAY = date(2026, 11, 6)
GHP = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"


def rss(*items):
    """An RSS body; each item is (guid, title, date 'YYYY-MM-DD' or '', summary)."""
    rows = []
    for guid, title, day, summary in items:
        pub = f"<pubDate>{date.fromisoformat(day).strftime('%a, %d %b %Y')} 09:00:00 GMT</pubDate>" if day else ""
        rows.append(f"<item><guid>{guid}</guid><title>{title}</title><link>https://example.com/{guid}</link>{pub}"
                    f"<description>{summary}</description></item>")
    return f"<rss><channel>{''.join(rows)}</channel></rss>".encode()


@pytest.fixture
def web(tmp_path, monkeypatch):
    folder = tmp_path / "stub"
    folder.mkdir()
    monkeypatch.setenv("FOUNDRY_MARKET_STUB", str(folder))
    routes = {}

    def serve(url, body=b"", status=200):
        name = f"r{len(list(folder.iterdir()))}"  # unique per call: a URL served again gets a new file
        (folder / name).write_bytes(body)
        routes[url] = {"status": status, "file": name, "location": ""}
        (folder / "routes.json").write_text(json.dumps(routes))
    serve.log = folder / "requests.log"
    return serve


def setup_watch(vault, watch, press=""):
    write_config(vault, f"market_watch:\n{watch}market_press:\n{press or '  []'}\n".replace("market_press:\n  []", "market_press: []"))


def fetch(vault, *argv, day=DAY):
    return run.main(list(argv), vault, today=day)


def candidates(vault, day=DAY):
    path = vault / "raw" / "market" / day.isoformat() / "candidates.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def alerts(vault, day=DAY):
    path = vault / "system" / "logs" / f"alerts_{day.isoformat()}.md"
    return [line for line in path.read_text().splitlines() if "[market_source]" in line] if path.exists() else []


FEED = "https://example.com/feed"
ONE = '  - {name: "Vendor A", group: vendors, feed: "https://example.com/feed"}\n'


def test_a_first_fetch_is_a_baseline_and_the_next_yields_new_items(vault, web):
    setup_watch(vault, ONE)
    web(FEED, rss(("a1", "Old news", "2026-11-01", "s")))
    assert fetch(vault) == 0
    assert candidates(vault) == []
    state = json.loads((vault / "system/logs/market_state.json").read_text())
    assert "a1" in state["sources"]["Vendor A:feed"]["seen"]
    web(FEED, rss(("a1", "Old news", "2026-11-01", "s"), ("a2", "New product", "2026-11-06", "s")))
    assert fetch(vault) == 0
    [c] = candidates(vault)
    assert (c["entry"], c["group"], c["title"], c["source"]) == ("Vendor A", "vendors", "New product", "Vendor A:feed")


def test_a_name_only_entry_is_never_fetched_but_matches_press_items(vault, web):
    press_url = "https://press.example.org/rss"
    setup_watch(vault, ONE + '  - {name: "Vendor B", group: partners}\n',
                f'  - {{name: "Trade News", feed: "{press_url}"}}\n')
    web(FEED, rss())
    web(press_url, rss(("p0", "Baseline", "", "")))
    fetch(vault)
    web(press_url, rss(("p0", "Baseline", "", ""), ("p1", "VENDOR B buys a rival", "2026-11-06", ""),
                       ("p2", "Vendor Bx is unrelated", "2026-11-06", "")))
    fetch(vault)
    assert [(c["entry"], c["group"], c["source"]) for c in candidates(vault)] == [("Vendor B", "partners", "press:Trade News")]
    assert all("Vendor B" not in line for line in web.log.read_text().splitlines())


def test_a_press_item_naming_no_entry_is_dropped(vault, web):
    press_url = "https://press.example.org/rss"
    setup_watch(vault, ONE, f'  - {{name: "Trade News", feed: "{press_url}"}}\n')
    web(FEED, rss())
    web(press_url, rss())
    fetch(vault)
    web(press_url, rss(("p1", "Someone else entirely", "2026-11-06", "")))
    fetch(vault)
    assert candidates(vault) == []


def test_exclude_drops_matching_titles(vault, web):
    setup_watch(vault, '  - {name: "Runtime E", group: eng, feed: "https://example.com/feed", exclude: "-rc\\\\d*\\\\b"}\n')
    web(FEED, rss())
    fetch(vault)
    web(FEED, rss(("r1", "Runtime 9.0.0-rc2", "2026-11-05", ""), ("r2", "Runtime 9.0.0", "2026-11-06", "")))
    fetch(vault)
    assert [c["title"] for c in candidates(vault)] == ["Runtime 9.0.0"]


def test_a_feed_out_of_date_order_gives_each_item_once(vault, web):
    setup_watch(vault, ONE)
    web(FEED, rss())
    fetch(vault)
    web(FEED, rss(("a", "A", "2026-11-05", ""), ("b", "B", "2026-11-06", "")))
    fetch(vault)
    web(FEED, rss(("b", "B", "2026-11-06", ""), ("a", "A", "2026-11-05", "")))
    fetch(vault)
    assert sorted(c["title"] for c in candidates(vault)) == ["A", "B"]


def test_a_group_over_25_passes_the_newest_25_and_holds_the_rest(vault, web):
    setup_watch(vault, ONE)
    web(FEED, rss())
    fetch(vault)
    items = [(f"n{i:02d}", f"Item {i:02d}", f"2026-10-{i:02d}", "") for i in range(1, 30)] + [("undated", "Undated", "", "")]
    web(FEED, rss(*items))
    fetch(vault)
    got = candidates(vault)
    assert len(got) == 25
    assert got[0]["title"] == "Item 29" and "Undated" not in [c["title"] for c in got]
    held = vault / "raw/market" / DAY.isoformat() / "held.json"
    assert json.loads(held.read_text()) == {"vendors": 5}
    web(FEED, rss(*items, *[(f"m{i}", f"More {i}", f"2026-11-0{i}", "") for i in range(1, 4)]))
    fetch(vault)
    assert len(candidates(vault)) == 28
    assert json.loads(held.read_text()) == {"vendors": 5}
    big = [(f"z{i:02d}", f"Z {i:02d}", "2026-11-05", "") for i in range(30)]
    web(FEED, rss(*items, *big))
    fetch(vault)
    assert json.loads(held.read_text()) == {"vendors": 10}


def test_summaries_are_cut_and_redacted(vault, web):
    setup_watch(vault, ONE)
    web(FEED, rss())
    fetch(vault)
    web(FEED, rss(("s1", "Long", "2026-11-06", f"key {GHP} " + "x" * 900)))
    fetch(vault)
    [c] = candidates(vault)
    assert len(c["summary"]) <= 500
    assert GHP not in c["summary"]


def test_one_failed_source_does_not_stop_the_others_and_three_failed_runs_alert_once(vault, web):
    other = "https://example.org/feed"
    setup_watch(vault, ONE + f'  - {{name: "Vendor C", group: vendors, feed: "{other}"}}\n')
    web(FEED, rss())
    web(other, b"", status=503)
    assert fetch(vault) == 1
    web(FEED, rss(("x1", "Fresh", "2026-11-06", "")))
    assert fetch(vault) == 1
    assert [c["title"] for c in candidates(vault)] == ["Fresh"]
    assert alerts(vault) == []
    fetch(vault)
    assert len(alerts(vault)) == 1 and "Vendor C:feed" in alerts(vault)[0] and "network" in alerts(vault)[0]
    fetch(vault)
    assert len(alerts(vault)) == 1
    web(other, rss())
    assert fetch(vault) == 0
    state = json.loads((vault / "system/logs/market_state.json").read_text())
    assert state["sources"]["Vendor C:feed"]["streak"] == 0


@pytest.mark.parametrize("entry,word", [
    ('{name: "Bad A", group: g, newsroom: "http://example.com/news/"}', "https"),
    ('{name: "Bad B", group: g, feed: "https://example.com/feed", exclude: "("}', "exclude"),
    ('{name: "Bad C", group: g, newsroom: "https://example.com/news/", match: "news"}', "match"),
])
def test_a_bad_entry_fails_that_source_only(vault, web, entry, word):
    setup_watch(vault, ONE + f"  - {entry}\n")
    web(FEED, rss())
    assert fetch(vault) == 1
    state = json.loads((vault / "system/logs/market_state.json").read_text())
    bad = [s for sid, s in state["sources"].items() if sid.startswith("Bad")]
    assert len(bad) == 1 and bad[0]["class"] == "other" and word in bad[0]["reason"]
    assert state["sources"]["Vendor A:feed"]["streak"] == 0


@pytest.mark.parametrize("text", ["", "{", "[]"])
def test_a_missing_or_corrupt_state_file_starts_over(vault, web, text):
    setup_watch(vault, ONE)
    web(FEED, rss(("a1", "A", "2026-11-06", "")))
    (vault / "system/logs").mkdir(parents=True, exist_ok=True)
    (vault / "system/logs/market_state.json").write_text(text)
    assert fetch(vault) == 0
    assert candidates(vault) == []
    assert "a1" in json.loads((vault / "system/logs/market_state.json").read_text())["sources"]["Vendor A:feed"]["seen"]


def test_check_reports_from_state_alone(vault, web, capsys):
    other = "https://example.org/feed"
    setup_watch(vault, ONE + f'  - {{name: "Vendor C", group: vendors, feed: "{other}"}}\n'
                + '  - {name: "Vendor D", group: vendors, feed: "https://example.net/feed"}\n')
    assert fetch(vault, "--check") == 1
    assert capsys.readouterr().out.strip() == "market_fetch: other: no fetch today"
    for url in (FEED, other, "https://example.net/feed"):
        web(url, rss())
    fetch(vault)
    capsys.readouterr()
    before = web.log.read_text()
    assert fetch(vault, "--check") == 0
    assert capsys.readouterr().out.strip() == "market_fetch: ok: 3 sources"
    web(other, b"", status=403)
    fetch(vault)
    capsys.readouterr()
    before = web.log.read_text()
    assert fetch(vault, "--check") == 1
    assert capsys.readouterr().out.strip().startswith("market_fetch: auth: 1 of 3 sources failed; first Vendor C:feed: ")
    assert web.log.read_text() == before


def test_unknown_arguments_are_usage(vault):
    assert fetch(vault, "--nope") == 2


def test_a_source_that_fails_before_its_first_success_still_takes_a_baseline(vault, web):
    setup_watch(vault, ONE)
    web(FEED, b"", status=503)
    fetch(vault)
    web(FEED, rss(("a1", "A", "2026-11-06", "")))
    fetch(vault)
    assert candidates(vault) == []


NEWS = "https://example.com/news/"
NEWSROOM = '  - {name: "Vendor N", group: vendors, newsroom: "https://example.com/news/"}\n'


def test_a_hostile_href_fails_its_source_and_the_others_still_write(vault, web):
    other = "https://example.org/feed"
    setup_watch(vault, NEWSROOM + f'  - {{name: "Vendor C", group: vendors, feed: "{other}"}}\n')
    web(NEWS, b'<a href="/news/a">A</a>')
    web(other, rss())
    fetch(vault)
    web(NEWS, b'<a href="https://[bad/news/x">X</a>')
    web(other, rss(("c1", "Fresh", "2026-11-06", "")))
    assert fetch(vault) == 1
    assert [c["title"] for c in candidates(vault)] == ["Fresh"]
    state = json.loads((vault / "system/logs/market_state.json").read_text())
    assert state["sources"]["Vendor N:newsroom"]["class"] == "other"


def test_a_malformed_config_url_fails_its_source_only(vault, web):
    setup_watch(vault, ONE + '  - {name: "Bad U", group: g, feed: "https://[x"}\n')
    web(FEED, rss())
    assert fetch(vault) == 1
    state = json.loads((vault / "system/logs/market_state.json").read_text())
    assert state["sources"]["Bad U:feed"]["class"] == "other"


def test_a_bad_exclude_on_a_press_matched_entry_does_not_crash(vault, web):
    press_url = "https://press.example.org/rss"
    setup_watch(vault, ONE + '  - {name: "Vendor B", group: partners, exclude: "("}\n',
                f'  - {{name: "Trade News", feed: "{press_url}"}}\n')
    web(FEED, rss())
    web(press_url, rss())
    fetch(vault)
    web(press_url, rss(("p1", "Vendor B buys a rival", "2026-11-06", "")))
    fetch(vault)
    assert [c["entry"] for c in candidates(vault)] == ["Vendor B"]


def test_an_item_still_listed_after_30_days_is_not_new_again(vault, web):
    setup_watch(vault, ONE)
    web(FEED, rss(("old", "Old", "2026-09-30", "")))
    fetch(vault, day=date(2026, 10, 1))
    for d in (date(2026, 10, 20), DAY):
        fetch(vault, day=d)
        assert candidates(vault, day=d) == []


def test_titles_are_cut_and_redacted(vault, web):
    setup_watch(vault, ONE)
    web(FEED, rss())
    fetch(vault)
    web(FEED, rss(("t1", f"Leak {GHP} " + "y" * 900, "2026-11-06", "")))
    fetch(vault)
    [c] = candidates(vault)
    assert len(c["title"]) <= 300 and GHP not in c["title"]
