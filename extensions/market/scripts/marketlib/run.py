"""The market fetch (market watch spec §3.2, amended M1, M2, M11, M12, M13): reads each watch entry's newsroom and
feed and each press feed, keeps the items it has not seen before, and writes them to raw/market/<date>/. A source's
first fetch only records what is there (plan 2, ruling 1). --check reports the day's run from state alone."""
import json
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from vaultlib.api import alert, config, load, redact_credentials, save

from . import http, parse

WORKERS = 8
GROUP_CAP = 25
SUMMARY_MAX = 500
TITLE_MAX = 300
SEEN_DAYS = 30
STREAK_ALERT = 3
CLASSES = {"auth": "auth", "network": "network", "timeout": "timeout"}  # anything else is "other"


def _maps(value) -> list:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def sources(cfg: dict) -> list:
    """(id, kind, url, entry) per fetchable source; name-only entries have none (M1)."""
    out = []
    for e in _maps(cfg.get("market_watch")):
        for kind in ("newsroom", "feed"):
            if e.get(kind):
                out.append((f"{e.get('name')}:{kind}", kind, str(e[kind]), e))
    for p in _maps(cfg.get("market_press")):
        out.append((f"press:{p.get('name')}", "press", str(p.get("feed") or ""), p))
    return out


def _problem(kind: str, url: str, entry: dict) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
    except ValueError:
        return f"{entry.get('name')}: {url[:200]} is not a valid URL"
    if parts.scheme != "https" or not host:
        return f"{entry.get('name')}: {url} is not an https URL"
    match = str(entry.get("match") or "")
    if kind == "newsroom" and match and not match.startswith("/"):
        return f"{entry.get('name')}: match {match!r} is not a path starting with /"
    try:
        re.compile(str(entry.get("exclude") or ""))
    except re.error as exc:
        return f"{entry.get('name')}: exclude is not a valid regex ({exc})"
    return ""


def _fetch(src):
    sid, kind, url, entry = src
    problem = _problem(kind, url, entry)
    if problem:
        return sid, None, ("other", problem)
    try:
        body = http.get(url)
        items = parse.newsroom_items(body, url, str(entry.get("match") or "")) if kind == "newsroom" \
            else parse.feed_items(body)
        return sid, items, None
    except http.MarketError as exc:
        return sid, None, (CLASSES.get(exc.kind, "other"), exc.reason)
    except Exception as exc:  # noqa: BLE001 - hostile input must fail its own source, never the run
        return sid, None, ("other", f"{type(exc).__name__}: {str(exc)[:200]}")


def _excludes(watch: list) -> dict:
    """{entry name: compiled exclude}; an invalid one is skipped with a line on stderr (its fetched sources fail)."""
    out = {}
    for e in watch:
        if e.get("exclude"):
            try:
                out[str(e.get("name"))] = re.compile(str(e["exclude"]))
            except re.error as exc:
                print(f"market_fetch: {e.get('name')}: exclude is not a valid regex ({exc}); not applied",
                      file=sys.stderr)
    return out


def _matcher(watch: list):
    pats = [(re.compile(rf"\b{re.escape(str(e.get('name')))}\b", re.I), e) for e in watch if e.get("name")]

    def named(item):
        hay = f"{item.title} {item.summary}"
        return next((e for pat, e in pats if pat.search(hay)), None)
    return named


def main(argv: list, vault: Path, today: date | None = None) -> int:
    if argv not in ([], ["--check"]):
        print("usage: market_fetch.py [--check]", file=sys.stderr)
        return 2
    today = today or date.today()
    day = today.isoformat()
    state_path = vault / "system" / "logs" / "market_state.json"
    state = load(state_path, {})
    state = state if isinstance(state, dict) else {}
    if argv == ["--check"]:
        return check(state, day)
    cfg = config(vault)
    watch = _maps(cfg.get("market_watch"))
    named, excludes = _matcher(watch), _excludes(watch)
    known = state.get("sources") if isinstance(state.get("sources"), dict) else {}
    cutoff = (today - timedelta(days=SEEN_DAYS)).isoformat()
    srcs = sources(cfg)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(_fetch, srcs))
    new, failed, out_sources = [], 0, {}
    by_id = {s[0]: s for s in srcs}
    for sid, items, error in results:
        prev = known.get(sid) if isinstance(known.get(sid), dict) else {}
        seen = {k: v for k, v in (prev.get("seen") or {}).items() if isinstance(v, str) and v >= cutoff}
        rec = {"seen": seen, "streak": 0, "class": "", "reason": "", "last_ok": prev.get("last_ok", "")}
        if error:
            failed += 1
            rec.update(seen=seen, streak=int(prev.get("streak") or 0) + 1, **dict(zip(("class", "reason"), error)))
            print(f"market_fetch: {sid}: {error[0]}: {error[1]}", file=sys.stderr)
            if rec["streak"] == STREAK_ALERT:
                alert(vault, day, datetime.now().strftime("%H:%M:%S"), "market_source",
                      f"{sid}: {error[0]}: {error[1]} ({STREAK_ALERT} failed runs)", key=sid)
        else:
            _, kind, _, entry = by_id[sid]
            baseline = not prev.get("last_ok")  # no success yet: this fetch only records what is there
            for item in items:
                fresh = item.key not in seen
                seen[item.key] = day  # last seen: a key is dropped only after 30 days off the source
                if not fresh or baseline:
                    continue
                target = named(item) if kind == "press" else entry
                if target is None:
                    continue
                exclude = excludes.get(str(target.get("name")))
                if exclude and exclude.search(item.title):
                    continue
                new.append((item, sid, target))
            rec["last_ok"] = day
        out_sources[sid] = rec
    _write(vault, today, new)
    state.update(sources=out_sources, last_run=day, last_sources=sorted(out_sources))
    save(state_path, state)
    return 1 if failed else 0


def _write(vault: Path, today: date, new: list) -> None:
    folder = vault / "raw" / "market" / today.isoformat()
    groups: dict = {}
    for item, sid, entry in new:
        groups.setdefault(str(entry.get("group") or ""), []).append((item, sid, entry))
    lines, held = [], {}
    for group, rows in groups.items():
        rows.sort(key=lambda r: r[0].published or "", reverse=True)  # newest first; undated ("") last
        lines += rows[:GROUP_CAP]
        if len(rows) > GROUP_CAP:
            held[group] = len(rows) - GROUP_CAP
    if not lines and not held:
        return
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "candidates.jsonl", "a", encoding="utf-8") as fh:
        for item, sid, entry in lines:
            fh.write(json.dumps({"source": sid, "entry": entry.get("name"), "group": entry.get("group"),
                                 "title": redact_credentials(item.title)[:TITLE_MAX], "link": item.link,
                                 "published": item.published,
                                 "summary": redact_credentials(item.summary)[:SUMMARY_MAX]}) + "\n")
    if held:
        path = folder / "held.json"
        total = load(path, {})
        total = total if isinstance(total, dict) else {}
        for group, n in held.items():
            total[group] = int(total.get(group) or 0) + n
        save(path, total)


def check(state: dict, day: str) -> int:
    if state.get("last_run") != day:
        print("market_fetch: other: no fetch today")
        return 1
    srcs = state.get("sources") or {}
    ids = [s for s in state.get("last_sources") or [] if isinstance(srcs.get(s), dict)]
    bad = [s for s in ids if srcs[s].get("streak")]
    if not bad:
        print(f"market_fetch: ok: {len(ids)} sources")
        return 0
    first = srcs[bad[0]]
    print(f"market_fetch: {first.get('class') or 'other'}: {len(bad)} of {len(ids)} sources failed; "
          f"first {bad[0]}: {first.get('reason')}")
    return 1
