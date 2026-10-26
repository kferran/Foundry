#!/usr/bin/env python3
"""The console's Today screen as one JSON object (console C1 spec §4), and the console's smoke check.

Usage: today.py --json    one object: {"v": 1, "date", "stamps", "partitions", "calendar", "orders", "pipeline",
                          "foreman_url", "errors"}; a source that fails leaves its part empty and adds one line to
                          "errors" naming it and its exit, and the rest still prints
       today.py --check   runs --json and the web server's /api/health; prints ok or failed: <class>: <reason>
Exit: 0; 1 from --check when it failed; 2 usage. Run from the vault root (FOUNDRY_VAULT names it otherwise).
It runs the core scripts as subprocesses and reads the morning's prep; it writes nothing and starts no session.
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

VAULT = Path(os.environ.get("FOUNDRY_VAULT") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib.api import Intake, config  # noqa: E402

PARTITIONS = ("work", "personal")
TIMEOUT = 10        # seconds per core command; the app waits 15 for the whole run
MAX_TODAY = 5       # today's objectives: the first Next item of each focus project (#351 Q7)
OPEN_ORDERS = ("queued", "running", "waiting_reset", "delivering")
PR_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/pull/\d+$")
YOURS = re.compile(r"^- \[(?P<bracket>[^\]]*)\] (?P<text>.+) \(\[\[(?P<meeting>[^\]]+)\]\], (?P<age>\d+ days? open)\)$")


def run_json(errors: list, name: str, *args):
    """One core command's JSON, or None with one errors line naming the source and its exit."""
    try:
        r = subprocess.run([sys.executable, *args], cwd=VAULT, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        errors.append(f"{name}: timed out after {TIMEOUT} s")
        return None
    if r.returncode != 0:
        errors.append(f"{name}: exit {r.returncode}")
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        errors.append(f"{name}: output is not JSON")
        return None


def matches(project: str, statement: str) -> bool:
    """A Now line belongs to a project when it links it or names it as a whole word, case-insensitive (spec §8.4)."""
    if f"[[{project}]]".casefold() in statement.casefold():
        return True
    return re.search(rf"(?<!\w){re.escape(project)}(?!\w)", statement, re.IGNORECASE) is not None


def changed(path: str) -> str:
    """The newest commit date of a vault file, or "" when git has none."""
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%cs", "--", path], cwd=VAULT, capture_output=True, text=True,
                           timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def read(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def stamp(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%H:%M")
    except OSError:
        return ""


def calendar(prep: Path, errors: list) -> list:
    text = read(prep / "calendar.tsv")
    if text is None:
        errors.append("calendar: no calendar.tsv in today's prep")
        return []
    out = []
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) >= 5:
            out.append({"start": cols[1], "end": cols[3], "title": cols[4]})
    return out


def actions(prep: Path, errors: list) -> list:
    """The Yours section of today's actions.md, one dict per action."""
    text = read(prep / "actions.md")
    if text is None:
        errors.append("meeting actions: no actions.md in today's prep")
        return []
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            on = line.strip() == "## Yours"
            continue
        m = YOURS.match(line.strip()) if on else None
        if m:
            out.append(m.groupdict())
    return out


def pipeline(prep: Path, day: str) -> dict:
    sources = [line[2:] for line in (read(prep / "sources.md") or "").splitlines() if line.startswith("- ")]
    quarantine = [line for line in (read(prep / "quarantine.md") or "").splitlines() if line.startswith("- ")]
    alerts = read(VAULT / "system" / "logs" / f"alerts_{day}.md") or ""
    return {"sources": sources, "quarantine": len(quarantine),
            "alerts": sum(1 for line in alerts.splitlines() if line.startswith("- "))}


def partition(name: str, now: dict, projects: dict, orders: list) -> dict:
    lines = now.get("lines", [])
    cards = []
    for rank, p in enumerate(projects.get("projects", []), 1):
        linked = [ln for ln in lines if matches(p["link"], ln["statement"])]
        cards.append({**p, "rank": rank, "now_lines": len(linked),
                      "prs": sum(1 for ln in linked if PR_URL.match(ln["evidence"])), "changed": changed(p["path"])})
    for ln in lines:
        ln["project"] = next((c["link"] for c in cards if matches(c["link"], ln["statement"])), "")
    today = [{"text": c["next"][0], "project": c["link"]} for c in cards if c["next"]][:MAX_TODAY]
    tiles = {"focus": len(cards), "stale": sum(1 for c in cards if c.get("stale")),
             "needs_you": sum(1 for ln in lines if ln["section"] == "Needs you"),
             "waiting": sum(1 for ln in lines if ln["section"] == "Waiting"),
             "overdue": sum(1 for ln in lines if ln["band"]),
             "orders": sum(1 for o in orders if o.get("partition") == name and o.get("state") in OPEN_ORDERS)}
    return {"tiles": tiles, "projects": cards, "also_active": projects.get("also_active", []), "today": today,
            "now": lines, "unparsed": len(now.get("unparsed", []))}


def build() -> dict:
    errors = []
    day = Intake(VAULT).today()
    prep = VAULT / "system" / "logs" / "inputs" / day
    now = run_json(errors, "now.py list", "system/scripts/now.py", "list", "--json", "--date", day) or {}
    active = run_json(errors, "active_projects.py", "system/scripts/active_projects.py", day, "--json") or {}
    queue = run_json(errors, "nightshift.py list", "system/scripts/nightshift.py", "list", "--json") or {}
    report = run_json(errors, "nightshift.py report", "system/scripts/nightshift.py", "report", "--json", day) or {}
    if not prep.is_dir():
        errors.append(f"prep: no prep for {day} yet")
    items = queue.get("items", [])
    # The partition walls hold on screen too: each partition's object holds only its own lines and projects.
    parts = {p: partition(p, (now.get("partitions") or {}).get(p, {}), (active.get("partitions") or {}).get(p, {}),
                          items)
             for p in PARTITIONS}
    # actions.md mixes the partitions; each action goes to the partition whose meetings/ holds its note, and one whose
    # note is in neither is left out rather than shown on the wrong side of the wall.
    yours = actions(prep, errors) if prep.is_dir() else []
    for p in PARTITIONS:
        parts[p]["actions"] = [a for a in yours if (VAULT / "wiki" / p / "meetings" / f"{a['meeting']}.md").is_file()]
    return {"v": 1, "date": day, "stamps": {"prep": stamp(prep), "index": stamp(VAULT / "system" / "index.db")},
            "partitions": parts, "calendar": calendar(prep, errors) if prep.is_dir() else [],
            "orders": {"open": [o for o in items if o.get("state") in OPEN_ORDERS], "today": report.get("items", []),
                       "needs": report.get("needs", []), "held": report.get("held")},
            "pipeline": pipeline(prep, day), "foreman_url": str(config(VAULT).get("console_foreman_url")
                                                               or "https://claude.ai/code"),
            "errors": errors}


def check() -> int:
    data = build()
    port = str(config(VAULT).get("console_port") or "3110")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as resp:
            health = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"failed: network: the console is not answering on 127.0.0.1:{port} ({exc.__class__.__name__})")
        return 1
    if not health.get("ok"):
        print("failed: other: /api/health did not say ok")
        return 1
    core = [e for e in data["errors"] if not e.startswith(("calendar:", "meeting actions:", "prep:"))]
    if core:
        print(f"failed: other: {core[0]}")
        return 1
    print("ok")
    return 0


def main(argv: list) -> int:
    if argv == ["--json"]:
        print(json.dumps(build(), ensure_ascii=False))
        return 0
    if argv == ["--check"]:
        return check()
    print("usage: today.py --json | --check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
