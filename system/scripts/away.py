#!/usr/bin/env python3
"""While you were away (#166): the brief's catch-up block after an absence.

Usage: away.py YYYY-MM-DD [owner/repo…]   prints away.md. The owner was away on the run of days before the date, up to
14, with no session digest (a digest a Work Order wrote carries work_order and does not count). After 0 or 1 such day,
or before any session wrote a digest, it prints nothing. Otherwise a heading and one count line per source, each
"<n> of <N>" or "none"; a source that cannot be read says unknown. Exit 1 when the digest query fails.
"""
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import briefings, now  # noqa: E402
from vaultlib.alerts import severity  # noqa: E402
from vaultlib.recall import _open_index  # noqa: E402

CAP = 14


def count(label, total, *parts) -> str:
    return f"- {label}: " + (", ".join(f"{n} of {total} {what}" for n, what in parts) if total else "none")


def prs(repos, first, last) -> str:
    """debrief_prep.sh's pull request search over the same repositories, for the away days."""
    if not repos:
        return "- Pull requests: off (no GitHub repository registered)"
    args = [a for r in repos for a in ("--repo", r)] + ["--json", "url", "--limit", "100", "--jq", "length"]
    search = lambda *q: int(subprocess.run(["gh", "search", "prs", "--author", "@me", *q, *args], check=True,  # noqa: E731
                                           capture_output=True, text=True,
                                           timeout=int(os.environ.get("GH_TIMEOUT", "60"))).stdout)
    merged, still_open = search("--merged-at", f"{first}..{last}"), search("--state", "open")
    return count("Pull requests", merged + still_open, (merged, "merged"), (still_open, "still open"))


def orders(conn, first, last) -> str:
    states = [s for (s,) in conn.execute("SELECT state FROM v_nightshift_item WHERE substr(finished_at, 1, 10) "
                                         "BETWEEN ? AND ?", (first, last))]
    return count("Work Orders", len(states), (states.count("done"), "done"), (states.count("failed"), "failed"))


def now_lines(first, last, days) -> str:
    lines = [line for p in now.PARTITIONS for line in now.read(VAULT, p).splitlines() if now.parse(line)]
    added = sum(first <= now.parse(line)["since"] <= last for line in lines)
    closed = sum(bool(s := now.STAMP.search(line)) and first <= s.group(1) <= last for line in lines)
    # ponytail: now.py prunes closed lines after KEEP_DAYS, so a longer absence undercounts them; said on the line.
    pruned = f" (closed lines leave the page after {now.KEEP_DAYS} days)" if days > now.KEEP_DAYS else ""
    return count("Now lines" + pruned, len(lines), (added, "added"), (closed, "closed"))


def alerts(span) -> str:
    lines = [line for d in span if (p := VAULT / "system" / "logs" / f"alerts_{d}.md").is_file()
             for line in p.read_text(encoding="utf-8").splitlines() if line.startswith("- ")]
    return count("Alerts", len(lines), (sum(severity(line) != "now" for line in lines), "held for the brief"))


def decided(today, days) -> str:
    found, n = briefings.earlier_briefings(VAULT, today, lookback=days), 0
    for _, path in found:
        on = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                on = line.startswith("## 🤖 Decided for you")
            elif on and line.startswith("- "):
                n += 1
    return f"- Decided for you: {n or 'none'}{' lines' if n else ''}, from {len(found)} of {days} briefings"


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
    first, last = span[0], span[-1]
    print(f"### While you were away ({first} to {last})\n")
    for label, read in (("Pull requests", lambda: prs(repos, first, last)), ("Work Orders", lambda: orders(conn, first, last)),
                        ("Now lines", lambda: now_lines(first, last, len(span))), ("Alerts", lambda: alerts(span)),
                        ("Decided for you", lambda: decided(today, len(span)))):
        try:
            print(read())
        except Exception as exc:  # noqa: BLE001 - one unreadable source must not hide the others
            print(f"- {label}: unknown")
            print(f"away.py: {label}: {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
