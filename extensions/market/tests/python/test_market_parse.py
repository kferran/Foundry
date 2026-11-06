"""marketlib.parse: feeds and newsroom pages to items (spec §3.2; M2, M6, M13)."""
import pytest

from market_helpers import FIXTURES
from marketlib import http, parse


def fixture(name):
    return (FIXTURES / name).read_bytes()


def test_rss_items_carry_guid_title_link_date_summary():
    items = parse.feed_items(fixture("rss.xml"))
    assert [i.key for i in items] == ["vb-1", "vb-2"]
    assert items[1] == parse.Item("vb-2", "Vendor B signs a partner", "https://vendor-b.example.com/news/2",
                                  "2026-11-05", "A second summary.")


def test_atom_entries_key_by_id():
    items = parse.feed_items(fixture("atom.xml"))
    assert [i.key for i in items] == ["tag:runtime-e.example.com,2026:9.0.0", "tag:runtime-e.example.com,2026:9.0.0-rc2"]
    assert [i.link for i in items] == ["https://runtime-e.example.com/r/9.0.0", "https://runtime-e.example.com/r/9.0.0-rc2"]
    assert [i.published for i in items] == ["2026-11-05", "2026-10-30"]
    assert items[1].summary == "Candidate."


def test_an_item_without_guid_keys_by_link():
    items = parse.feed_items(fixture("rss-quirks.xml"))
    assert items[0].key == "https://example.org/r/4.2"


def test_quirks_parse():
    items = parse.feed_items(fixture("rss-quirks.xml"))
    assert items[0].published == "2026-11-05"
    assert items[0].title == "Release 4.2 ships"
    assert items[1].published == ""


@pytest.mark.parametrize("body", [b"<rss><channel><item>", b"\xff\xfe junk", b""])
def test_malformed_xml_is_bad(body):
    with pytest.raises(http.MarketError) as err:
        parse.feed_items(body)
    assert err.value.kind == "bad"


def test_newsroom_links_under_the_page_path():
    items = parse.newsroom_items(fixture("newsroom.html"), "https://example.com/news/")
    assert [(i.key, i.title) for i in items] == [
        ("https://example.com/news/2026/a-new-office", "A new office"),
        ("https://example.com/news/q3-results", "Q3 results"),
    ]
    assert all(i.link == i.key and i.published == "" for i in items)


def test_a_match_prefix_finds_root_and_dated_links():
    page = "https://example.com/about/newsroom.html"
    items = parse.newsroom_items(fixture("newsroom-root.html"), page, match="/")
    assert [i.key for i in items] == ["https://example.com/2026/08/partner-c-expands",
                                      "https://example.com/partner-c-names-a-ceo",
                                      "https://example.com/press-releases/stories/new-plan"]
    items = parse.newsroom_items(fixture("newsroom-root.html"), page, match="/press-releases/")
    assert [i.key for i in items] == ["https://example.com/press-releases/stories/new-plan"]
