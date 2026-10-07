"""One DTCC watcher run and its CLI modes (DTCC watcher spec §3, §6, §7).
Exit 0 ok or no map, 1 a source failed or was held, 2 usage or invalid map, 4 locked."""
import argparse
import fcntl
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import dtcc_diff as dd
from . import dtcc_map, dtcc_notes, frontmatter, schema
from . import dtcc_parse as dp
from .dtcc_fetch import BASE, MARKET, RELEASE, RSS, Fetcher, FetchError, PdfUnavailable, allowed

STATE = "system/logs/dtcc_watch_state.json"
LOCK = "system/dtcc.lock"
FLOOD = 20


def _parser():
    p = argparse.ArgumentParser(prog="dtcc_watch.py")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument("--accept", action="store_true")
    g.add_argument("--brief", metavar="YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true")
    return p


class Run:
    def __init__(self, vault: Path, now: datetime, mp: dict, dry: bool):
        self.vault, self.now, self.mp, self.dry = vault, now, mp, dry
        path = vault / STATE
        self.state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        for k, v in (("pages", {}), ("release", None), ("notices", {}), ("assets", {}), ("alerts", {})):
            self.state.setdefault(k, v)
        self.today = now.astimezone().date().isoformat()
        self.stale = []

    def alert(self, key: str, msg: str) -> None:
        if self.dry:
            print(f"alert: {msg}")
            return
        if self.state["alerts"].get(key) == self.today:
            return
        self.state["alerts"][key] = self.today
        path = self.vault / "system" / "logs" / f"alerts_{self.today}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"- {self.now.astimezone().strftime('%H:%M:%S')} [dtcc] {msg}\n")

    def save(self, state: dict, line: dict) -> None:
        if self.dry:
            return
        state["alerts"] = self.state["alerts"]
        path = self.vault / STATE
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
        log = self.vault / "system" / "logs" / f"dtcc_watch-{self.now.strftime('%Y-%m')}.jsonl"
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, sort_keys=True) + "\n")

    # --- note building -------------------------------------------------------------------------
    def _product(self, key):
        return ((self.mp.get("products") or {}).get(key) or {}) if key else {}

    def _note(self, kind, key, title, product=None, evidence=(), deadlines=(), source_url="", **extra) -> tuple:
        p = self._product(product)
        stale = {(k, path): r for k, path, r in self.stale}
        fm = {"type": "dtcc_change", "partition": self.mp["partition"], "detected_at": self.now.isoformat(),
              "kind": kind, "key": key, "title": dtcc_notes.clean(title), "impact": "pending", "capability": "code",
              "deadlines": list(deadlines), "paths": list(p.get("paths") or [])}
        if source_url and allowed(source_url):
            fm["source_url"] = source_url
        if product:
            fm.update(product=product, codebase=p.get("codebase", ""), owner=p.get("owner", ""), pinned=str(p.get("pin") or ""))
        fm.update(extra)
        paths = [path + (f" (missing at {stale[(product, path)]})" if (product, path) in stale else "")
                 for path in p.get("paths") or []]
        related = ([self.mp["hub"]] if self.mp.get("hub") else []) + list(p.get("notes") or [])
        return fm, list(evidence), paths, related

    def _page_note(self, product, changes, docs):
        slug = self._product(product)["page"]
        ev = []
        for c in changes:
            if c["kind"] == "renamed":
                ev.append(f"renamed: {c['old_title']} -> {c['title']} ({c['date']}), section {c['section']}")
            elif c["kind"] == "date_moved":
                ev.append(f"date moved: {c['title']} {c['old_date']} -> {c['date']}, body unknown")
            else:
                ev.append(f"new: {c['title']} ({c['date']}), section {c['section']}")
        pub = dd.published(docs)
        n = len(changes)
        return self._note(changes[0]["kind"], f"page:{product}:{self.today}",
                          f"{product}: {n} Learning Center change{'s' if n > 1 else ''}", product, ev,
                          source_url=BASE + slug + ".html", published=dd.vstr(pub) if pub else "")

    def _notice_note(self, n):
        products = self.mp.get("products") or {}
        linked = [k for k, p in products.items() if set((p or {}).get("notice_codes") or []) & set(n["codes"])]
        ignore = set(self.mp.get("ignore") or [])
        if not linked and n["codes"] and set(n["codes"]) <= ignore:
            return None
        ev = [f"{k}: {n[k]}" for k in ("category", "to", "subject") if n.get(k)]
        ev += [f"products named: {', '.join(n['codes']) or 'none recognised'}"]
        if not n["pdf_ok"]:
            ev.append("PDF unreadable; dates not extracted")
        deadlines = [f"{label} {iso} ({n['number']})" for label, iso in n["dates"]]
        extra = {"paths": sorted({p for k in linked for p in (products[k] or {}).get("paths") or []})} if len(linked) > 1 else {}
        return self._note("notice" if linked else "unmapped", f"notice:{n['number']}",
                          f"Notice {n['number']}: {n['summary'] or n.get('subject') or 'no summary'}",
                          linked[0] if linked else None, ev, deadlines, n["link"], **extra)

    # --- the run -------------------------------------------------------------------------------
    def go(self, accept: bool) -> int:
        f, rc = Fetcher(), 0
        products = self.mp.get("products") or {}
        kws = self.mp.get("notice_keywords") or []
        new = json.loads(json.dumps(self.state))
        changes, page_changes, page_docs, held, failed, removed = [], {}, {}, [], [], 0

        self.stale = dtcc_map.stale_paths(self.mp, self.vault)
        for product, path, ref in self.stale:
            self.alert(f"stale/{product}/{path}", f"map: {product} path {path} is missing at {ref}; update system/dtcc/map.yaml")

        for key, p in products.items():
            slug = (p or {}).get("page")
            if not slug:
                continue
            try:
                docs = dp.page_docs(f.text(BASE + slug + ".html"))
            except FetchError as exc:
                failed.append(slug)
                self.alert(f"fetch/{slug}", f"page {slug}: fetch failed ({exc})")
                continue
            old = self.state["pages"].get(slug) or {}
            if not docs or len(docs) < len(old) / 2:
                held.append(slug)
                self.alert(f"sanity/{slug}", f"page {slug}: {len(docs)} documents, was {len(old)}; held (layout change?)")
                continue
            page_docs[key] = docs
            new["pages"][slug] = {dd.doc_key(d): d for d in docs}
            if old:
                ch, gone = dd.diff_page(old, docs)
                removed += len(gone)
                if ch:
                    page_changes[key] = ch

        try:
            blk = dp.release_block(f.text(RELEASE))
            if blk is None:
                held.append("release")
                self.alert("sanity/release", "release page: no Important Dates block; held (layout change?)")
        except FetchError as exc:
            blk = None
            failed.append("release")
            self.alert("fetch/release", f"release page: fetch failed ({exc})")
        if blk:
            old = self.state["release"]
            if old and old["hash"] != blk["hash"]:
                ev = [f"was: {old['text']}", f"now: {blk['text']}"]
                changes.append(self._note("release_dates", f"release:{self.today}", "I&RS release dates changed", None, ev,
                                          [f"{label} {iso} (release page)" for label, iso in blk["dates"]], RELEASE))
            new["release"] = blk

        codes = sorted({c for p in products.values() for c in (p or {}).get("notice_codes") or []}
                       | set(self.mp.get("ignore") or []))
        baseline = not self.state["notices"]
        try:
            items = dp.rss_items(f.text(RSS))
        except (FetchError, ET.ParseError) as exc:
            items = None
            failed.append("notices")
            self.alert("fetch/notices", f"notices feed: unreadable ({exc})")
        if items == []:
            held.append("notices")
            self.alert("sanity/notices", "notices feed: 0 items; held")
        for it in items or []:
            if it["number"] in self.state["notices"]:
                continue
            first_look = dp.matches(kws, it["number"], it["summary"])
            if baseline and not first_look:
                new["notices"][it["number"]] = []
                continue
            text, header, pdf_ok = "", {"category": "", "to": "", "subject": ""}, False
            if allowed(it["link"]):
                try:
                    text = f.pdf_text(it["link"])
                    header, pdf_ok = dp.pdf_header(text), True
                except PdfUnavailable as exc:
                    self.alert("pdftotext", f"notice PDFs unreadable: {exc}")
                except FetchError:
                    pass
            if not (first_look or dp.matches(kws, header["category"], header["to"])):
                new["notices"][it["number"]] = []
                continue
            flat = " ".join(text.split())
            dates = dp.milestones(flat)
            new["notices"][it["number"]] = [list(d) for d in dates]
            if not baseline:
                note = self._notice_note({**it, **header, "pdf_ok": pdf_ok, "dates": dates, "codes": dp.codes_in(flat, codes)})
                if note:
                    changes.append(note)

        try:
            assets = dp.catalog(f.catalog())
            if not assets:
                held.append("api")
                self.alert("sanity/api", "API Marketplace: 0 assets; held")
        except FetchError as exc:
            assets = []
            failed.append("api")
            self.alert("fetch/api", f"API Marketplace: fetch failed ({exc})")
        if assets:
            old, watched = self.state["assets"], {}
            for a in assets:
                prod = next((k for k, p in products.items()
                             if any(n.lower() in a["name"].lower() for n in (p or {}).get("api_assets") or [])), None)
                if prod or dp.matches(kws, a["name"]):
                    watched[a["name"]] = {"published": a["published"], "version": a["version"], "product": prod}
            for name, a in watched.items():
                o = old.get(name)
                if old and (o is None or (o["published"], o["version"]) != (a["published"], a["version"])):
                    ev = [f"was: {o['version'] or '-'} published {o['published'] or '-'}" if o else "new asset",
                          f"now: {a['version'] or '-'} published {a['published'] or '-'}"]
                    changes.append(self._note("api_asset", f"api:{name}:{a['version'] or a['published'] or 'new'}",
                                              f"API Marketplace: {name} {a['version']}".strip(), a["product"], ev,
                                              source_url=MARKET + "inventory/viewAssetsGrid.html"))
            new["assets"] = watched

        count = len(changes) + sum(len(c) for c in page_changes.values())
        line = {"started_at": self.now.isoformat(), "changes": count, "removed": removed, "held": held, "failed": failed}
        if count > FLOOD and not accept:
            self.alert("flood", f"{count} changes in one run; held. Review them, then run /dtcc-watch accept")
            line.update(held=held + ["flood"], notes=0, exit=1)
            self.save(self.state, line)
            return 1
        if accept:
            changes, page_changes = [], {}
        changes += [self._page_note(k, ch, page_docs[k]) for k, ch in page_changes.items()]

        for key, docs in page_docs.items():
            pin, pub = dp.version_of(str(products[key].get("pin") or "")), dd.published(docs)
            if pin and pub and pub > pin:
                changes.append(self._note("version_gap", f"gap:{key}:{dd.vstr(pub)}",
                                          f"{key}: published {dd.vstr(pub)}, pinned {dd.vstr(pin)}", key,
                                          [f"highest version on the {products[key]['page']} page: {dd.vstr(pub)}"],
                                          source_url=BASE + products[key]["page"] + ".html", published=dd.vstr(pub)))
        rel = (new.get("release") or {}).get("dates") or []
        dated = {n: d for n, d in new["notices"].items() if d}
        for label, a, b, number in dd.conflicts(rel, dated, self.today):
            changes.append(self._note("date_conflict", f"conflict:{label}:{a}:{b}",
                                      f"{label} date conflict: {b} ({number}) vs {a} (release page)", None,
                                      [f"release page: {label} {a}", f"notice {number}: {label} {b}"],
                                      [f"{label} {b} ({number})", f"{label} {a} (release page)"], RELEASE))

        schemas, written = schema.load_schemas(self.vault), 0
        for fm, ev, paths, related in changes:
            rel_path = dtcc_notes.rel_path(fm["partition"], fm["key"])
            if self.dry:
                print(json.dumps({"key": fm["key"], "kind": fm["kind"], "title": fm["title"], "path": rel_path}))
                continue
            try:
                written += dtcc_notes.create(self.vault, rel_path, dtcc_notes.render(fm, ev, paths, related), schemas)
            except ValueError as exc:
                failed.append(fm["key"])
                self.alert(f"note/{fm['key']}", f"note not written: {exc}")
        rc = 1 if held or failed else 0
        line.update(notes=written, exit=rc)
        self.save(new, line)
        return rc


def _config(vault: Path) -> tuple:
    path = vault / "system" / "config.md"
    data = frontmatter.parse(path.read_text(encoding="utf-8")).data if path.is_file() else None
    data = data or {}
    return ZoneInfo(str(data.get("timezone") or "UTC")), str(data.get("brief_time") or "06:00")


def _notes(vault: Path) -> list:
    out = []
    for p in sorted((vault / "wiki").glob("*/changes/dtcc-*.md")):
        data = frontmatter.parse(p.read_text(encoding="utf-8")).data or {}
        if data.get("type") == "dtcc_change":
            out.append((datetime.fromisoformat(str(data["detected_at"])), p.stem, data))
    return sorted(out, key=lambda t: t[0])


def brief_lines(vault: Path, day: str) -> list:
    """One checkbox per note detected after the latest earlier briefing's brief time (30-day lookback)."""
    tz, bt = _config(vault)
    today = date.fromisoformat(day)
    prev = next((today - timedelta(days=b) for b in range(1, 31)
                 if (vault / "briefings" / f"{(today - timedelta(days=b)).isoformat()}.md").is_file()), today - timedelta(days=30))
    h, m = (int(x) for x in bt.split(":"))
    cutoff = datetime(prev.year, prev.month, prev.day, h, m, tzinfo=tz)
    lines = []
    for detected, stem, data in _notes(vault):
        if detected <= cutoff:
            continue
        upcoming = sorted((re.search(r"\d{4}-\d{2}-\d{2}", d).group(0), d) for d in data.get("deadlines") or []
                          if re.search(r"\d{4}-\d{2}-\d{2}", d) and re.search(r"\d{4}-\d{2}-\d{2}", d).group(0) >= day)
        tail = f" — {upcoming[0][1]}" if upcoming else ""
        lines.append(f"- [ ] DTCC: {data.get('title', stem)} ([[{stem}]]){tail}")
    return lines


def _status(vault: Path, now: datetime) -> None:
    logs = sorted((vault / "system" / "logs").glob("dtcc_watch-*.jsonl"))
    last = logs[-1].read_text(encoding="utf-8").splitlines()[-1] if logs and logs[-1].stat().st_size else ""
    print(f"last run: {last or 'none'}")
    week = [(d, s, x) for d, s, x in _notes(vault) if d >= now - timedelta(days=7)]
    print(f"notes in the past 7 days: {len(week)}")
    for d, stem, data in week:
        print(f"- {d.astimezone().date()} {data.get('kind')}: {data.get('title')} ([[{stem}]])")


def main(argv: list, vault: Path, now: datetime | None = None) -> int:
    vault, now = Path(vault), now or datetime.now(timezone.utc)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    if args.brief:
        try:
            day = date.fromisoformat(args.brief).isoformat()
        except ValueError:
            print("usage: dtcc_watch.py --brief YYYY-MM-DD", file=sys.stderr)
            return 2
        for line in brief_lines(vault, day):
            print(line)
        return 0
    if args.status:
        _status(vault, now)
        return 0
    mp, err = dtcc_map.load(vault)
    if mp is None and err is None:
        return 0
    errs = [err] if err else dtcc_map.validate(mp, vault)
    if args.check:
        for e in errs:
            print(f"invalid: {e}")
        stale = [] if errs else dtcc_map.stale_paths(mp, vault)
        for product, path, ref in stale:
            print(f"stale: {product}: {path} is missing at {ref}")
        if not errs and not stale:
            print("map ok")
        return 2 if errs else (1 if stale else 0)
    if errs:
        r = Run(vault, now, mp or {}, args.dry_run)
        for e in errs:
            print(f"dtcc_watch: map: {e}", file=sys.stderr)
        r.alert("map", f"system/dtcc/map.yaml is invalid ({errs[0]}); run /dtcc-watch check")
        r.save(r.state, {"started_at": now.isoformat(), "exit": 2, "invalid_map": len(errs)})
        return 2
    (vault / "system").mkdir(exist_ok=True)
    with open(vault / LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("dtcc_watch: another run is in progress", file=sys.stderr)
            return 4
        return Run(vault, now, mp, args.dry_run).go(args.accept)
