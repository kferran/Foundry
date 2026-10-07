"""Parsers for the DTCC watcher's sources (DTCC watcher spec §2, §3.3). Pure functions over fetched text."""
import hashlib
import html
import re
import xml.etree.ElementTree as ET
from datetime import date

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
DATE_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"
                     r"|\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b|\b(\d{4})-(\d{2})-(\d{2})\b", re.I)
VERSION_RE = re.compile(r"\bv(\d\d)-(\d+)\b", re.I)
LABELS = [("PSE", re.compile(r"\bPSE\b")), ("Test", re.compile(r"\btest\b", re.I)),
          ("Production", re.compile(r"\bproduction\b", re.I)), ("Decommission", re.compile(r"\bdecommission", re.I))]
WINDOW = 120  # characters before a date searched for its milestone label


def _iso(m) -> str | None:
    try:
        if m.group(1):
            d = date(int(m.group(3)), MONTHS.index(m.group(1).lower()) + 1, int(m.group(2)))
        elif m.group(4):
            year = int(m.group(6))
            d = date(year + 2000 if year < 100 else year, int(m.group(4)), int(m.group(5)))
        else:
            d = date(int(m.group(7)), int(m.group(8)), int(m.group(9)))
    except ValueError:
        return None
    return d.isoformat()


def parse_date(text: str) -> str | None:
    m = DATE_RE.search(text or "")
    return _iso(m) if m else None


def text_of(fragment: str) -> str:
    """HTML to one line of text. Block ends become spaces; inline tags vanish so a split date rejoins."""
    s = re.sub(r"(?i)</(li|p|div|h\d|tr|td|ul)>|<br\s*/?>", " ", fragment or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def norm(title: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(title or "")).strip().casefold()


def version_of(title: str) -> tuple | None:
    m = VERSION_RE.search(title or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def page_docs(page: str) -> list:
    """Dated document cards on a Learning Center product page, in page order."""
    out, section = [], None
    for m in re.finditer(r"<h3[^>]*>(.*?)</h3>|<h4 class=\"card__title\">(.*?)</h4>|<span class=\"card__date\">(.*?)</span>",
                         page, re.S):
        if m.group(1) is not None:
            section = text_of(m.group(1))
        elif m.group(2) is not None:
            out.append({"section": section, "title": text_of(m.group(2)), "date": None})
        elif out and out[-1]["date"] is None:
            out[-1]["date"] = parse_date(text_of(m.group(3)))
    return [d for d in out if d["date"]]


def milestones(text: str) -> list:
    """[(label, iso)] for each date with a milestone label in the WINDOW before it; the nearest label wins."""
    out = []
    for m in DATE_RE.finditer(text):
        iso = _iso(m)
        if not iso:
            continue
        before = text[max(0, m.start() - WINDOW):m.start()]
        best = None
        for label, rx in LABELS:
            for lm in rx.finditer(before):
                if best is None or lm.end() > best[1]:
                    best = (label, lm.end())
        if best and (best[0], iso) not in out:
            out.append((best[0], iso))
    return out


def release_block(page: str) -> dict | None:
    """The release page's "Important Dates" list: its hash and milestone dates."""
    m = re.search(r"Important Dates.*?(<ul>.*?</ul>)", page, re.S | re.I)
    if not m:
        return None
    text = text_of(m.group(1))
    return {"hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], "text": text,
            "dates": [list(d) for d in milestones(text)]}


def rss_items(xml_text: str) -> list:
    """Notices keyed on number; a duplicate replaces an earlier copy only when that copy has no summary."""
    items = {}
    for item in ET.fromstring(xml_text).iter("item"):
        number = (item.findtext("title") or "").strip()
        if not number:
            continue
        summary = text_of(item.findtext("description") or "").split("Notice:")[0].strip()[:300]
        if number in items and items[number]["summary"]:
            continue
        items[number] = {"number": number, "link": (item.findtext("link") or "").strip(), "summary": summary,
                         "pub": (item.findtext("pubDate") or "").strip()}
    return list(items.values())


def pdf_header(text: str) -> dict:
    def line(name):
        m = re.search(rf"^[ \t]*{name}:[ \t]*(\S.*)$", text or "", re.M)
        return m.group(1).strip() if m else ""
    return {"category": line("Category"), "to": line("To"), "subject": line("Subject")}


def codes_in(text: str, codes) -> list:
    return [c for c in codes if re.search(rf"(?<![A-Za-z0-9]){re.escape(c)}(?![A-Za-z0-9])", text or "")]


def catalog(page: str) -> list:
    """API Marketplace tiles: full name, published date, version."""
    out = []
    for card in page.split('class="assetCard"')[1:]:
        def field(rx):
            m = re.search(rx, card, re.S)
            return text_of(m.group(1)) if m else ""
        name = field(r'class="tooltiptext">(.*?)<') or field(r'class="title">(.*?)<')
        if name:
            out.append({"name": name, "published": parse_date(field(r'class="publishDate">(.*?)<')) or "",
                        "version": field(r'class="versionLbl">(.*?)<').removeprefix("Version").strip()})
    return out


def matches(keywords, *texts) -> bool:
    return any(re.search(k, t or "", re.I) for k in keywords for t in texts)
