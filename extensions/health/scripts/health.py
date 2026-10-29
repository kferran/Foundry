#!/usr/bin/env python3
"""The health scorecard (health scorecard spec §3): metrics of the platform and the factory from existing logs and
GitHub, scored against thresholds, kept in system/logs/health/<YYYY-MM>.jsonl.

Usage: health.py score YYYY-MM-DD [--dry-run]
  Score the 7 days ending the day before, append one line per metric (once a day: a second run reuses the day's
  lines) and print the brief's lines: the whole scorecard on a Monday, else only the breaches. --dry-run appends
  nothing.
Exit: 0; 2 usage.
"""
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
VAULT = HERE.parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib.api import append, config, now as nowmod, records  # noqa: E402

DEFAULTS = {"tick_success_pct": 95, "runs_published_pct": 95, "brief_by": "06:30", "brief_kb": 8, "now_kb": 25,
            "now_open": 60, "dismissed_pct": 50, "cost_cap_usd": None, "first_push_green_pct": 80, "headroom_pct": 2}
NOT_FETCH = ("runs", "smoke", "usage")          # month logs that are not a source's ticks
PUBLISHED = ("published", "noop")
DISMISS_MIN = 5                                 # closed lines a host needs before its dismissed share is scored
TREND_WEEKS, TREND_FACTOR = 4, 1.5
GH_CALL_SECONDS = 15
HEALTH_GH_SECONDS = 90                          # every gh call of one score shares this (the manifest's budget value)
REVIEW_FIX = re.compile(r"review fix|final review|address(?:es|ed)? review", re.IGNORECASE)
GREEN = ("success", "neutral", "skipped")
BUDGETS = ("core lines", "brief words")         # headroom that can run out; the other caps are ratchets
MONTH_LOG = re.compile(r"^(?P<name>.+)-(?P<month>\d{4}-\d{2})\.jsonl$")
STAMP = re.compile(r"_\(closed: (?P<how>.*?) ?(?P<day>\d{4}-\d{2}-\d{2})\)_\s*$")
ICON = {"ok": "✅", "breach": "⚠️", "trend": "⏳", "unavailable": "❔"}


class Unavailable(Exception):
    """A metric whose files are missing or unreadable: never scored as zero or ok."""


class Window:
    """The 7 days ending the day before `day`."""

    def __init__(self, day: date):
        self.day, self.last, self.first = day, day - timedelta(days=1), day - timedelta(days=7)
        self.days = [self.first + timedelta(days=i) for i in range(7)]
        self.months = sorted({d.strftime("%Y-%m") for d in self.days})

    def has(self, iso: str) -> bool:
        return self.first.isoformat() <= iso[:10] <= self.last.isoformat()


def thresholds(cfg: dict) -> dict:
    out = dict(DEFAULTS)
    given = cfg.get("health_thresholds")
    for key, value in (given.items() if isinstance(given, dict) else []):
        if key in out and str(value).strip() != "":
            out[key] = str(value) if key == "brief_by" else int(str(value))
    return out


def logs(vault: Path) -> Path:
    return vault / "system" / "logs"


def _pct(n: int, total: int) -> int:
    return round(100 * n / total) if total else 0


# --- platform -------------------------------------------------------------------------------------------------------

def tick_success(vault, w, th):
    """{source: percent} of each fetch log's lines in the window that exited 0."""
    counts = {}
    for path in sorted(logs(vault).glob("*-*.jsonl")):
        m = MONTH_LOG.match(path.name)
        if not m or m["month"] not in w.months or m["name"] in NOT_FETCH:
            continue
        for r in records(path):
            when = str(r.get("time") or r.get("date") or "")
            if not isinstance(r.get("exit"), int) or not w.has(when):
                continue
            ok, total = counts.get(m["name"], (0, 0))
            counts[m["name"]] = (ok + (r["exit"] == 0), total + 1)
    if not counts:
        raise Unavailable("no fetch log has a line in the window")
    value = {name: _pct(ok, total) for name, (ok, total) in sorted(counts.items())}
    low = [n for n, v in value.items() if v < th["tick_success_pct"]]
    text = ", ".join(f"{n} {v}%" for n, v in value.items())
    return value, text, f"≥ {th['tick_success_pct']}% each", "breach" if low else "ok"


def _ledger(vault, w) -> list:
    paths = [logs(vault) / f"runs-{m}.jsonl" for m in w.months]
    if not any(p.is_file() for p in paths):
        raise Unavailable("no run ledger for the window")
    return [r for r in records(*paths) if w.has(str(r.get("started_at") or r.get("finished_at") or ""))]


def _status(r) -> str:
    pub = r.get("publish")
    return str(pub.get("status") or "") if isinstance(pub, dict) else ""


def runs_published(vault, w, th):
    runs = [r for r in _ledger(vault, w) if _status(r)]
    ok = sum(_status(r) in PUBLISHED for r in runs)
    value = _pct(ok, len(runs)) if runs else 100
    text = f"{value}% ({ok} of {len(runs)})"
    return value, text, f"≥ {th['runs_published_pct']}%", "ok" if value >= th["runs_published_pct"] else "breach"


def brief_on_time(vault, w, th, tz):
    by = th["brief_by"]
    on_time = set()
    for r in _ledger(vault, w):
        if r.get("command") != "brief" or _status(r) not in PUBLISHED:
            continue
        try:
            done = datetime.fromisoformat(str(r.get("finished_at"))).astimezone(tz)
        except ValueError:
            continue
        if done.strftime("%H:%M") <= by:
            on_time.add(done.date())
    workdays = [d for d in w.days if d.weekday() < 5]
    late = [d.strftime("%a") for d in workdays if d not in on_time]
    n = len(workdays) - len(late)
    text = f"{n} of {len(workdays)} workdays" + (f" (late or missing: {', '.join(late)})" if late else "")
    return n, text, f"every workday by {by}", "breach" if late else "ok"


def brief_size(vault, w, th):
    folder = vault / "briefings"
    days = sorted(p for p in folder.glob("????-??-??.md") if p.stem <= w.last.isoformat()) if folder.is_dir() else []
    if not days:
        raise Unavailable("no briefing before today")
    kb = round(days[-1].stat().st_size / 1024, 1)
    return kb, f"{kb} KB ({days[-1].stem})", f"≤ {th['brief_kb']} KB", "ok" if kb <= th["brief_kb"] else "breach"


def now_size(vault, w, th):
    value = {}
    for p in nowmod.PARTITIONS:
        path = nowmod.page_path(vault, p)
        if path.is_file():
            value[p] = round(path.stat().st_size / 1024, 1)
    if not value:
        raise Unavailable("no Now page")
    text = ", ".join(f"{p} {kb} KB" for p, kb in value.items())
    big = any(kb > th["now_kb"] for kb in value.values())
    return value, text, f"≤ {th['now_kb']} KB each", "breach" if big else "ok"


def _now_lines(vault, w) -> list:
    """(line, mark, since, closed day, how) of every parsed line on both Now pages and the window's archive notes."""
    texts = []
    for p in nowmod.PARTITIONS:
        page = nowmod.page_path(vault, p)
        if page.is_file():
            texts.append(page.read_text(encoding="utf-8"))
        texts += nowmod.archived(vault, p, w.first.isoformat(), w.last.isoformat())
    if not texts:
        raise Unavailable("no Now page or archive")
    out, seen = [], set()
    for text in texts:
        for line in text.splitlines():
            m = nowmod.LINE.match(line.rstrip())
            if not m or line.rstrip() in seen:
                continue
            seen.add(line.rstrip())
            s = STAMP.search(line) if m["mark"] != " " else None
            out.append((m, m["mark"], m["since"], s["day"] if s else "", s["how"] if s else ""))
    return out


def now_open(vault, w, th):
    n = sum(1 for _, mark, *_ in _now_lines(vault, w) if mark == " ")
    return n, str(n), f"≤ {th['now_open']}", "ok" if n <= th["now_open"] else "breach"


def now_flow(vault, w, th):
    lines = _now_lines(vault, w)
    inflow = sum(1 for _, _, since, _, _ in lines if w.has(since))
    closed = [(mark, how) for _, mark, _, day, how in lines if day and w.has(day)]
    evidence = sum(1 for mark, how in closed if mark != "-" and how != "ticked")
    value = {"inflow": inflow, "closures": len(closed), "evidence": evidence}
    text = f"{len(closed)} closed against {inflow} added ({evidence} on evidence)"
    return value, text, "closures ≥ inflow", "ok" if len(closed) >= inflow else "breach"


def _host(evidence: str) -> str:
    if not evidence:
        return "none"
    for host, name in (("mail.google.com", "mail"), ("slack.com", "slack"), ("github.com", "github")):
        if host in evidence:
            return name
    return "other"


def dismissed(vault, w, th):
    counts = {}
    for m, mark, _, day, _ in _now_lines(vault, w):
        if day and w.has(day):
            # The writer when the line names one (Now writer spec §3.3), else the old guess from its evidence link.
            host = nowmod.via(m["statement"]) or "guess:" + _host(m["evidence"] or "")
            d, total = counts.get(host, (0, 0))
            counts[host] = (d + (mark == "-"), total + 1)
    value = {h: _pct(d, t) for h, (d, t) in sorted(counts.items()) if t >= DISMISS_MIN}
    text = ", ".join(f"{h} {v}%" for h, v in value.items()) or f"no source with {DISMISS_MIN} closed"
    high = any(v >= th["dismissed_pct"] for v in value.values())
    return value, text, f"< {th['dismissed_pct']}% each, and trend", "breach" if high else "trend"


def cost_per_day(vault, w, th):
    total, counted, seen = 0.0, set(), False
    try:
        for r in _ledger(vault, w):
            seen = True
            data = _json(logs(vault) / "runs" / str(r.get("run_id")) / "claude.json")
            if isinstance(data, dict) and isinstance(data.get("total_cost_usd"), (int, float)):
                total += data["total_cost_usd"]
                counted.add("headless runs")
    except Unavailable:
        pass
    for path in sorted(logs(vault).glob("*-*.jsonl")):
        m = MONTH_LOG.match(path.name)
        if not m or m["month"] not in w.months or m["name"] in NOT_FETCH:
            continue
        for r in records(path):
            if isinstance(r.get("cost_usd"), (int, float)) and w.has(str(r.get("time") or r.get("date") or "")):
                total += r["cost_usd"]
                counted.add(m["name"])
                seen = True
    if not seen:
        raise Unavailable("no run ledger and no fetch log cost in the window")
    per_day = round(total / 7, 2)
    cap = th["cost_cap_usd"]
    text = f"${per_day:.2f} ({', '.join(sorted(counted)) or 'nothing counted'})"
    if cap is not None:
        return per_day, text, f"≤ ${cap}", "ok" if per_day <= cap else "breach"
    return per_day, text, "trend", "trend"


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sync_blocked(vault, w, th):
    n = 0
    for d in w.days:
        path = logs(vault) / f"alerts_{d.isoformat()}.md"
        if path.is_file():
            n += sum(1 for line in path.read_text(encoding="utf-8").splitlines() if "[sync] sync blocked" in line)
    blocked = (logs(vault) / "sync-blocked").exists()
    n += blocked
    text = f"{n}" + (" (blocked now)" if blocked else "")
    return n, text, "0", "ok" if n == 0 else "breach"


# --- headroom -------------------------------------------------------------------------------------------------------

def _cap(vault: Path, rel: str, pattern: str) -> int:
    path = vault / rel
    m = re.search(pattern, path.read_text(encoding="utf-8")) if path.is_file() else None
    if not m:
        raise Unavailable(f"no cap in {rel}")
    return int(m.group(1))


def _tracked(vault: Path, *paths) -> list:
    try:
        out = subprocess.run(["git", "-C", str(vault), "ls-files", "-z", *paths], capture_output=True, text=True,
                             timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unavailable(f"git ls-files failed: {exc.__class__.__name__}")
    return [vault / p for p in out.split("\0") if p]


def headroom(vault, w, th):
    caps = {
        "core lines": (sum(p.read_bytes().count(b"\n") for p in _tracked(vault, "system/scripts", "system/hooks",
                                                                          ".claude/commands") if p.is_file()),
                       _cap(vault, "system/tests/vault_integrity.bats", r"(?m)^CORE_CAP=(\d+)")),
        "schemas": (len(_tracked(vault, "system/schemas")),
                    _cap(vault, "system/tests/vault_integrity.bats", r"git ls-files system/schemas \| wc -l\)\" -le (\d+)")),
        "CLAUDE.md lines": (len((vault / "CLAUDE.md").read_text(encoding="utf-8").splitlines()),
                            _cap(vault, "system/tests/commands.bats", r"wc -l < \"\$f\"\)\" -le (\d+)")),
        "brief words": (sum(len(p.read_text(encoding="utf-8").split()) for p in
                            [vault / ".claude/commands/brief.md", *sorted((vault / "extensions").glob("*/brief/section.md"))]),
                        _cap(vault, "system/tests/prep.bats", r"\"\$words\" -le (\d+)")),
    }
    value = {k: _pct(cap - n, cap) for k, (n, cap) in caps.items()}
    text = ", ".join(f"{k} {n} of {cap}" for k, (n, cap) in caps.items())
    # Schemas and CLAUDE.md are ratchets held full on purpose (a new one displaces an old one): only over the cap counts.
    tight = any(value[k] < th["headroom_pct"] for k in BUDGETS) or any(n > cap for n, cap in caps.values())
    return value, text, f"≥ {th['headroom_pct']}% left of {' and '.join(BUDGETS)}", "breach" if tight else "ok"


# --- factory --------------------------------------------------------------------------------------------------------

def github_repo(cfg: dict) -> str:
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", str(cfg.get("template_remote") or ""))
    return m.group(1) if m else ""


class GH:
    """gh calls sharing one time budget; a call past the budget or a failed call returns None."""

    def __init__(self, repo: str, budget: float):
        self.repo, self.deadline = repo, time.monotonic() + budget

    def __call__(self, *args):
        left = self.deadline - time.monotonic()
        if left <= 0:
            return None
        try:
            p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=min(GH_CALL_SECONDS, left))
            return json.loads(p.stdout) if p.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError):
            return None


def merged_prs(gh: GH, w) -> list:
    prs = gh("pr", "list", "-R", gh.repo, "--state", "merged", "--limit", "50",
             "--search", f"merged:{w.first.isoformat()}..{w.last.isoformat()}",
             "--json", "number,mergedAt,labels,commits")
    if not isinstance(prs, list):
        raise Unavailable("gh pr list failed")
    return prs


def defects(prs, w, th, gates: dict):
    per, recur = {}, []
    for pr in prs:
        for label in pr.get("labels") or []:
            name = str(label.get("name") or "")
            if not name.startswith("defect:"):
                continue
            cls = name.split(":", 1)[1]
            per[cls] = per.get(cls, 0) + 1
            gate = str(gates.get(cls) or "")
            if gate and str(pr.get("mergedAt") or "")[:10] > gate:
                recur.append(f"#{pr.get('number')} {cls}")
    fixes = ", ".join(f"{c} {n}" for c, n in sorted(per.items())) or "none"
    text = f"{len(recur)}" + (f" ({', '.join(recur)})" if recur else "") + f"; fix PRs: {fixes}"
    return len(recur), text, "0 after a gate", "ok" if not recur else "breach"


def first_push(prs, th, gh: GH, cache: dict):
    green = total = 0
    unread = []
    for pr in prs:
        n = pr.get("number")
        if n not in cache:
            commits = pr.get("commits") or []
            sha = commits[0].get("oid") if commits else None
            runs = gh("api", f"repos/{gh.repo}/commits/{sha}/check-runs") if sha else None
            if not isinstance(runs, dict):
                unread.append(n)
                continue
            found = [str(c.get("conclusion") or "") for c in runs.get("check_runs") or []]
            cache[n] = bool(found) and all(c in GREEN for c in found)
        total += 1
        green += cache[n]
    if not total and unread:
        raise Unavailable(f"check runs unread for {len(unread)} PRs")
    value = _pct(green, total) if total else 100
    text = f"{value}% ({green} of {total})" + (f"; {len(unread)} PRs unread" if unread else "")
    return value, text, f"≥ {th['first_push_green_pct']}%", "ok" if value >= th["first_push_green_pct"] else "breach"


def review_fixes(prs, th):
    if not prs:
        return 0.0, "no PRs merged", "trend", "trend"
    n = sum(1 for pr in prs for c in pr.get("commits") or []
            if REVIEW_FIX.search(f"{c.get('messageHeadline') or ''}\n{c.get('messageBody') or ''}"))
    value = round(n / len(prs), 1)
    return value, f"{value} per PR ({n} over {len(prs)} PRs)", "trend", "trend"


# --- scoring --------------------------------------------------------------------------------------------------------

LABELS = {"tick_success": "Source ticks ok", "runs_published": "Headless runs published", "brief_on_time": "Brief on time",
          "brief_size": "Brief size", "now_size": "Now page size", "now_open": "Now open lines",
          "now_flow": "Now closures", "dismissed": "Dismissed share", "cost_per_day": "Claude cost per day",
          "sync_blocked": "Sync blocked", "headroom": "Headroom", "defect_recurrence": "Defect recurrences",
          "first_push_green": "First-push CI green", "review_fixes": "Review-fix commits"}
TREND = ("dismissed", "cost_per_day", "review_fixes")


def history_path(vault: Path, day: date) -> Path:
    return logs(vault) / "health" / f"{day.strftime('%Y-%m')}.jsonl"


def history(vault: Path, day: date) -> list:
    months = sorted({(day - timedelta(days=i)).strftime("%Y-%m") for i in range(0, 7 * (TREND_WEEKS + 1) + 4, 7)})
    return records(*[logs(vault) / "health" / f"{m}.jsonl" for m in months])


def _near(hist: list, metric: str, want: date):
    """The scored record of `metric` nearest to `want`, within 3 days, or None."""
    near = [r for r in hist if r.get("metric") == metric and r.get("state") != "unavailable"
            and abs((date.fromisoformat(r["date"]) - want).days) <= 3]
    return min(near, key=lambda r: abs((date.fromisoformat(r["date"]) - want).days)) if near else None


def _earlier(hist: list, metric: str, day: date, weeks: int) -> dict:
    """{k: the value recorded nearest to `day` minus k weeks} for each k in 1..weeks that has one."""
    found = {k: _near(hist, metric, day - timedelta(weeks=k)) for k in range(1, weeks + 1)}
    return {k: r["value"] for k, r in found.items() if r}


def _trend(value, before: dict):
    """'breach', 'ok' or 'trend' (fewer than 4 weeks of history) for a number or a {key: number} value."""
    if len(before) < TREND_WEEKS:
        return "trend"
    if isinstance(value, dict):
        states = [_trend(v, {k: b.get(key) for k, b in before.items() if isinstance(b, dict) and key in b})
                  for key, v in value.items()]
        return "breach" if "breach" in states else "trend" if "trend" in states else "ok"
    median = statistics.median(before.values())
    return "breach" if value > TREND_FACTOR * median and value > 0 else "ok"


def compute(vault: Path, day: date) -> list:
    cfg = config(vault)
    th = thresholds(cfg)
    w = Window(day)
    tz = ZoneInfo(str(cfg.get("timezone") or "UTC"))
    hist = history(vault, day)
    metrics = [("tick_success", lambda: tick_success(vault, w, th)),
               ("runs_published", lambda: runs_published(vault, w, th)),
               ("brief_on_time", lambda: brief_on_time(vault, w, th, tz)),
               ("brief_size", lambda: brief_size(vault, w, th)),
               ("now_size", lambda: now_size(vault, w, th)),
               ("now_open", lambda: now_open(vault, w, th)),
               ("now_flow", lambda: now_flow(vault, w, th)),
               ("dismissed", lambda: dismissed(vault, w, th)),
               ("cost_per_day", lambda: cost_per_day(vault, w, th)),
               ("sync_blocked", lambda: sync_blocked(vault, w, th)),
               ("headroom", lambda: headroom(vault, w, th))]
    repo = github_repo(cfg)
    caches = []
    if repo and shutil.which("gh"):
        gh = GH(repo, HEALTH_GH_SECONDS)
        cache = {r["pr"]: r["green"] for r in hist if r.get("cache") == "first_push"}
        known = set(cache)
        try:
            prs = merged_prs(gh, w)
            gates = cfg.get("health_defect_gates") if isinstance(cfg.get("health_defect_gates"), dict) else {}
            metrics += [("defect_recurrence", lambda: defects(prs, w, th, gates)),
                        ("first_push_green", lambda: first_push(prs, th, gh, cache)),
                        ("review_fixes", lambda: review_fixes(prs, th))]
        except Unavailable as exc:
            why = str(exc)
            metrics += [(m, lambda why=why: _raise(why)) for m in ("defect_recurrence", "first_push_green", "review_fixes")]
        caches = [cache, known]
    out = []
    for metric, fn in metrics:
        rec = {"date": day.isoformat(), "metric": metric}
        try:
            value, text, threshold, state = fn()
        except Unavailable as exc:
            out.append({**rec, "value": None, "text": f"unavailable ({exc})", "threshold": "", "state": "unavailable"})
            continue
        if metric in TREND:
            before = _earlier(hist, metric, day, TREND_WEEKS)
            moved = _trend(value, before)
            state = "breach" if "breach" in (state, moved) else moved if state == "trend" else state
            if moved != "trend":
                threshold = threshold.replace("trend", f"≤ {TREND_FACTOR}× the 4-week median")
        out.append({**rec, "value": value, "text": text, "threshold": threshold, "state": state})
    if caches:
        cache, known = caches
        out += [{"date": day.isoformat(), "cache": "first_push", "pr": n, "green": g}
                for n, g in sorted(cache.items()) if n not in known]
    return out


def _raise(why: str):
    raise Unavailable(why)


def lines(rows: list, day: date, hist: list) -> list:
    rows = [r for r in rows if r.get("metric")]
    if day.weekday() != 0:
        return [f"- ⚠️ health: {LABELS[r['metric']]} {r['text']} (healthy {r['threshold']})"
                for r in rows if r["state"] == "breach"]
    out = []
    for r in rows:
        prev = _near(hist, r["metric"], day - timedelta(weeks=1))
        tail = "; ".join(x for x in (r["threshold"] and f"healthy {r['threshold']}",
                                     prev and f"last week {prev['text']}") if x)
        out.append(f"- {ICON[r['state']]} {LABELS[r['metric']]}: {r['text']}" + (f" ({tail})" if tail else ""))
    return out


def score(vault: Path, day: date, dry: bool) -> list:
    hist = history(vault, day)
    rows = [r for r in hist if r.get("date") == day.isoformat() and r.get("metric")]
    if not rows:
        rows = compute(vault, day)
        if not dry:
            for r in rows:
                append(history_path(vault, day), r)
    return lines(rows, day, [h for h in hist if h.get("date") != day.isoformat()])


def main(argv: list) -> int:
    if len(argv) < 2 or argv[0] != "score" or argv[2:] not in ([], ["--dry-run"]):
        print("usage: health.py score YYYY-MM-DD [--dry-run]", file=sys.stderr)
        return 2
    try:
        day = date.fromisoformat(argv[1])
    except ValueError:
        print(f"health: invalid date: {argv[1]}", file=sys.stderr)
        return 2
    out = score(VAULT, day, argv[2:] == ["--dry-run"])
    if out:
        print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
