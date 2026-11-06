"""Feeds and newsroom pages to items for the market fetch (market watch spec §3.2, amended M2, M6, M13). Feeds key an
item by its guid (RSS) or id (Atom), else its link; a newsroom keys an item by its absolute link."""
import email.utils
import html.parser
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

from .http import MarketError

ATOM = "{http://www.w3.org/2005/Atom}"
SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Item:
    key: str
    title: str
    link: str
    published: str  # YYYY-MM-DD, or "" when the source gives no date it can read
    summary: str


class _Text(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list = []

    def handle_data(self, data):
        self.parts.append(data)


def text(value: str) -> str:
    """Markup stripped to its text, whitespace collapsed (a feed title may carry <a> tags, raw or escaped)."""
    if "<" in value or "&" in value:
        p = _Text()
        p.feed(value)
        p.close()
        value = "".join(p.parts)
    return SPACE.sub(" ", value).strip()


def _el_text(el) -> str:
    return text("".join(el.itertext())) if el is not None else ""


def _date(value: str, rss: bool) -> str:
    value = (value or "").strip()
    try:
        # parsedate_to_datetime reads a two-digit year as 20YY (M6)
        when = email.utils.parsedate_to_datetime(value) if rss else datetime.fromisoformat(value)
        return when.date().isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def feed_items(body: bytes) -> list:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise MarketError("bad", f"not a readable feed: {exc}") from None
    out = []
    if root.tag == "rss":
        for it in root.iter("item"):
            link = _el_text(it.find("link"))
            out.append(Item(_el_text(it.find("guid")) or link, _el_text(it.find("title")), link,
                            _date(_el_text(it.find("pubDate")), True), _el_text(it.find("description"))))
    elif root.tag == f"{ATOM}feed":
        for en in root.iter(f"{ATOM}entry"):
            links = en.findall(f"{ATOM}link")
            link = next((l.get("href", "") for l in links if l.get("rel", "alternate") == "alternate"), "")
            when = en.find(f"{ATOM}published") if en.find(f"{ATOM}published") is not None else en.find(f"{ATOM}updated")
            summary = en.find(f"{ATOM}summary") if en.find(f"{ATOM}summary") is not None else en.find(f"{ATOM}content")
            out.append(Item(_el_text(en.find(f"{ATOM}id")) or link, _el_text(en.find(f"{ATOM}title")), link,
                            _date(_el_text(when), False), _el_text(summary)))
    else:
        raise MarketError("bad", f"not an RSS or Atom feed (root <{root.tag}>)")
    return out


class _Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list = []  # [href, text parts]
        self._open = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._open = [dict(attrs).get("href") or "", []]
            self.links.append(self._open)

    def handle_endtag(self, tag):
        if tag == "a":
            self._open = None

    def handle_data(self, data):
        if self._open is not None:
            self._open[1].append(data)


def newsroom_items(body: bytes, page_url: str, match: str = "") -> list:
    """The page's same-host links under `match` (default: the page's own folder), less the page and the prefix itself."""
    page = urllib.parse.urlsplit(page_url)
    prefix = match or page.path[: page.path.rfind("/") + 1] or "/"
    parser = _Links()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
        parser.close()
    except Exception as exc:  # noqa: BLE001 - html.parser is lenient; anything it still raises is bad input
        raise MarketError("bad", f"not a readable page: {exc}") from None
    out, seen = [], set()
    for href, parts in parser.links:
        link = urllib.parse.urljoin(page_url, href.strip())
        u = urllib.parse.urlsplit(link)
        link = urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, u.query, ""))
        if (u.scheme != "https" or u.hostname != page.hostname or not u.path.startswith(prefix)
                or u.path in (prefix, page.path) or link in seen):
            continue
        seen.add(link)
        out.append(Item(link, text("".join(parts)) or u.path.rsplit("/", 1)[-1], link, "", ""))
    return out
