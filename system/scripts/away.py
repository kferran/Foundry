#!/usr/bin/env python3
"""While you were away (#166): the brief's catch-up block after an absence.

Usage: away.py YYYY-MM-DD [owner/repo…]   prints away.md. The owner was away on the run of days before the date, up to
14, with no session digest (a digest a Work Order wrote carries work_order and does not count). After 0 or 1 such day,
or before any session wrote a digest, it prints nothing. Otherwise a heading and one count line per source, each
"<n> of <N>" or "none"; a source that cannot be read says unknown. Exit 1 when the digest query fails.
"""
import os
import re
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import frontmatter, now  # noqa: E402
from vaultlib.alerts import severity  # noqa: E402
from vaultlib.recall import _open_index  # noqa: E402

CAP = 14
HEADING = re.compile(r"#{1,6} ")


def vault_tz():
    """The configured timezone (the vault's day, as the other writers use it); UTC when it cannot be read."""
    try:
        return ZoneInfo(str(frontmatter.parse((VAULT / "system" / "config.md").read_text(encoding="utf-8")).data
                            .get("timezone") or "UTC"))
    except Exception:  # noqa: BLE001 - a missing or bad config reads as UTC, like alert.py
        return ZoneInfo("UTC")


def count(label, total, *parts) -> str:
    return f"- {label}: " + (", ".join(f"{n} of {total} {what}" for n, what in parts) if total else "none")


def prs(repos, tz, first, last) -> str:
    """debrief_prep.sh's pull request search over the same repositories, for the away days in the vault's timezone."""
    if not repos:
        return "- Pull requests: off (no GitHub repository registered)"
    args = [a for r in repos for a in ("--repo", r)] + ["--json", "url", "--limit", "100", "--jq", "length"]
    search = lambda *q: int(subprocess.run(["gh", "search", "prs", "--author", "@me", *q, *args], check=True,  # noqa: E731
                                           capture_output=True, text=True,
                                           timeout=int(os.environ.get("GH_TIMEOUT", "60"))).stdout)
    edge = lambda day, t: datetime.combine(date.fromisoformat(day), t, tz).isoformat()  # noqa: E731
    merged = search("--merged-at", f"{edge(first, time(0))}..{edge(last, time(23, 59, 59))}")
    still_open = search("--state", "open")
    return count("Pull requests", merged + still_open, (merged, "merged"), (still_open, "still open"))


def orders(conn, tz, first, last) -> str:
    """Dated by finished_at in the vault's timezone: nightshift_run.py writes it in UTC."""
    states = [s for s, f in conn.execute("SELECT state, finished_at FROM v_nightshift_item WHERE finished_at != ''")
              if first <= datetime.fromisoformat(str(f)).astimezone(tz).date().isoformat() <= last]
    return count("Work Orders", len(states), (states.count("done"), "done"), (states.count("failed"), "failed"))


def now_lines(first, last) -> str:
    """The page's lines and the archived ones of the away months (closed lines leave the page at each brief)."""
    lines = [line for p in now.PARTITIONS for text in (now.read(VAULT, p), *now.archived(VAULT, p, first, last))
             for line in text.splitlines() if now.parse(line)]
    added = sum(first <= now.parse(line)["since"] <= last for line in lines)
    closed = sum(bool(s := now.STAMP.search(line)) and first <= s.group(1) <= last for line in lines)
    return count("Now lines", len(lines), (added, "added"), (closed, "closed"))


def alerts(span) -> str:
    lines = [line for d in span if (p := VAULT / "system" / "logs" / f"alerts_{d}.md").is_file()
             for line in p.read_text(encoding="utf-8").splitlines() if line.startswith("- ")]
    return count("Alerts", len(lines), (sum(severity(line) == "brief" for line in lines), "held for the brief"))


def decided(span) -> str:
    """The Decided for you lines of each away day's briefing (## 🤖 Decided for you) and debrief (### 7. Decided for
    you), live or archived."""
    root, n, read = VAULT / "briefings", 0, {".md": 0, ".debrief.md": 0}
    for d in span:
        for kind in read:
            path = next((p for p in (root / f"{d}{kind}", root / "archive" / d[:7] / f"{d}{kind}") if p.is_file()), None)
            if path is None:
                continue
            read[kind] += 1
            on = False
            for line in path.read_text(encoding="utf-8").splitlines():
                if HEADING.match(line):
                    on = "Decided for you" in line
                elif on and line.startswith("- "):
                    n += 1
    return (f"- Decided for you: {n or 'none'}{' lines' if n else ''}, from {read['.md']} of {len(span)} briefings "
            f"and {read['.debrief.md']} of {len(span)} debriefs")


def main(argv) -> int:
    if len(argv) < 2 or not now.is_date(argv[1]):
        print("usage: away.py YYYY-MM-DD [owner/repo…]", file=sys.stderr)
        return 2
    today, repos = argv[1], argv[2:]
    try:
        conn, _ = _open_index(VAULT)
        active = {d for (d,) in conn.execute("SELECT DISTINCT substr(created_at, 1, 10) FROM v_session_digest "
                                             "WHERE coalesce(work_order, '') = '' AND created_at < ?", (today,))}
    except Exception as exc:  # noqa: BLE001 - no index means no answer: the prep records it
        print(f"away.py: digest query failed: {exc}", file=sys.stderr)
        return 1
    span, day = [], date.fromisoformat(today) - timedelta(days=1)
    while active and len(span) < CAP and day.isoformat() not in active:
        span.insert(0, day.isoformat())
        day -= timedelta(days=1)
    if len(span) < 2:
        return 0
    first, last, tz = span[0], span[-1], vault_tz()
    print(f"### While you were away ({first} to {last})\n")
    for label, read in (("Pull requests", lambda: prs(repos, tz, first, last)),
                        ("Work Orders", lambda: orders(conn, tz, first, last)),
                        ("Now lines", lambda: now_lines(first, last)), ("Alerts", lambda: alerts(span)),
                        ("Decided for you", lambda: decided(span))):
        try:
            print(read())
        except Exception as exc:  # noqa: BLE001 - one unreadable source must not hide the others
            print(f"- {label}: unknown")
            print(f"away.py: {label}: {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
