#!/usr/bin/env python3
"""Commit each published headless run with a message built from its records (two-machines spec §4).

Usage: commit_runs.py [--init-cutover]. Exit 0 when every pending run is committed or recorded as
already committed; 1 when a commit fails (alert written, that run and later ones stay pending); 2 usage.
"""
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import frontmatter  # noqa: E402

LOGS = VAULT / "system" / "logs"
RUNS = LOGS / "runs"
SINCE = LOGS / "commit_runs.since"
RUN_ID = re.compile(r"^(\d{8}T\d{6})-(ingest|brief|debrief|meeting|nightshift)-[0-9a-f]{4}$")
PARTITIONS = ("work", "personal", "shared")
CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
SUBJECT_MAX = 72


def config(key, default):
    try:
        data = frontmatter.parse((VAULT / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return default
    value = data.get(key)
    return value if isinstance(value, str) and value else default


def now():
    try:
        return datetime.now(ZoneInfo(config("timezone", "UTC")))
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now(ZoneInfo("UTC"))


def init_cutover():
    """The run_id-format time before which runs are never committed; written once per vault."""
    if not SINCE.exists():
        SINCE.parent.mkdir(parents=True, exist_ok=True)
        SINCE.write_text(now().strftime("%Y%m%dT%H%M%S") + "\n", encoding="utf-8")
    return SINCE.read_text(encoding="utf-8").strip()


def alert(message):
    LOGS.mkdir(parents=True, exist_ok=True)
    t = now()
    with open(LOGS / f"alerts_{t:%Y-%m-%d}.md", "a", encoding="utf-8") as fh:
        fh.write(f"- {t:%H:%M:%S} [commit_runs] {CONTROL.sub(' ', message)}\n")


def json_lines(path):
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def pending(since):
    if not RUNS.is_dir():
        return []
    out = []
    for rd in sorted(RUNS.iterdir()):
        match = RUN_ID.match(rd.name)
        if not match or match.group(1) < since or (rd / "committed").exists():
            continue
        try:
            report = json.loads((rd / "publish.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if not isinstance(report, dict):
            continue
        published = [p for p in report.get("published") or [] if isinstance(p, str)]
        if published:
            conflicts = [p for p in report.get("conflicts") or [] if isinstance(p, str)]
            out.append((rd.name, match.group(2), published, conflicts))
    return out


def folder_partition(paths):
    for path in paths:
        parts = path.split("/")
        if len(parts) > 2 and parts[0] == "wiki" and parts[1] in PARTITIONS:
            return parts[1]
    return None


def subject(prefix, items):
    for k in range(len(items), 0, -1):
        text = prefix + ", ".join(items[:k]) + (f" +{len(items) - k} more" if k < len(items) else "")
        if len(text) <= SUBJECT_MAX:
            return text
    return f"{prefix}{len(items)} notes"


def ledger_partition(run_id):
    ledger = LOGS / f"runs-{run_id[:4]}-{run_id[4:6]}.jsonl"
    return next((r["partition"] for r in json_lines(ledger)
                 if r.get("run_id") == run_id and r.get("partition") in PARTITIONS), None)


def meeting_title(published):
    for path in published:
        if not path.endswith(".transcript.md"):
            try:
                title = (frontmatter.parse((VAULT / path).read_text(encoding="utf-8")).data or {}).get("title")
            except (OSError, UnicodeDecodeError):
                title = None
            if isinstance(title, str) and title.strip():
                return " ".join(CONTROL.sub(" ", title).split())
    return Path(published[0]).stem


def message(run_id, command, published, conflicts, role, carried=()):
    if command == "meeting":
        partition = ledger_partition(run_id) or folder_partition(published)
        head = f"meeting({partition}): {meeting_title(published)}"
        if len(head) > SUBJECT_MAX:
            head = head[:SUBJECT_MAX - 1].rstrip() + "…"
        body = [f"published {p}" for p in published] + [f"conflict {p}" for p in conflicts]
    elif command == "ingest":
        decisions = [r for r in json_lines(RUNS / run_id / "_decisions.jsonl")
                     if isinstance(r.get("decision"), str) and r["decision"] != "noop" and isinstance(r.get("target"), str)]
        rows, seen = [], set()
        for r in decisions:
            if r["target"] in published and (r["decision"], r["target"]) not in seen:
                seen.add((r["decision"], r["target"]))
                rows.append((r["decision"], r["target"], r["source"] if isinstance(r.get("source"), str) else ""))
        covered = {t for _, t, _ in rows}
        rows += [("update", p, "") for p in published if p not in covered]
        partition = ledger_partition(run_id) \
            or folder_partition([r["target"] for r in decisions]) or folder_partition(published) \
            or config("default_partition", "personal")
        head = subject(f"ingest({partition}): ", [f"{CONTROL.sub(' ', d)} {Path(t).stem}" for d, t, _ in rows])
        body = [f"{d} {t} <- {s}" if s else f"{d} {t}" for d, t, s in rows]
        body += [f"held back {p} (conflict)" for p in conflicts]
    else:
        head = f"{command} {run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}: {published[0]}"
        body = [f"published {p}" for p in published] + [f"conflict {p}" for p in conflicts]
    body += [f"carries {p} from {r}" for p, r in carried]
    body = [CONTROL.sub(" ", line) for line in body]
    trailers = [f"Foundry-Command: {command}", f"Foundry-Run: {run_id}", f"Foundry-Role: {CONTROL.sub(' ', role)}"]
    return head + "\n\n" + "\n".join(body) + "\n\n" + "\n".join(trailers) + "\n"


def git(*args, stdin=None):
    return subprocess.run(["git", "-C", str(VAULT), *args], input=stdin, capture_output=True, text=True)


def commit(paths, text):
    """Commit only these paths. Returns (sha, None), (None, None) when nothing differs, or (None, error)."""
    tracked = set(git("ls-files", "-z", "--", *paths).stdout.split("\0"))
    paths = [p for p in paths if (VAULT / p).exists() or p in tracked]
    if not paths:
        return None, None
    added = git("add", "-A", "--", *paths)
    if added.returncode:
        git("reset", "-q", "--", *paths)
        return None, added.stderr.strip() or "git add failed"
    # Compared through the index, so no status setting (showUntrackedFiles) can hide a new note.
    if git("diff", "--cached", "--quiet", "--", *paths).returncode == 0:
        return None, None
    done = git("commit", "-q", "--only", "-F", "-", "--", *paths, stdin=text)
    if done.returncode:
        git("reset", "-q", "--", *paths)
        return None, done.stderr.strip() or done.stdout.strip() or "git commit failed"
    return git("rev-parse", "HEAD").stdout.strip(), None


def main(argv):
    if argv == ["--init-cutover"]:
        init_cutover()
        return 0
    if argv:
        print("usage: commit_runs.py [--init-cutover]", file=sys.stderr)
        return 2
    since = init_cutover()
    role = config("machine_role", "standalone")
    runs = pending(since)
    # A note two pending runs published holds the later run's content: it is committed with that run.
    owner = {p: run_id for run_id, _, published, _ in runs for p in published}
    earlier = {}
    for run_id, command, published, conflicts in runs:
        own = [p for p in published if owner[p] == run_id]
        carried = [(p, earlier[p]) for p in own if p in earlier]
        earlier.update({p: run_id for p in published})
        if not own:
            later = owner[published[0]]
            (RUNS / run_id / "committed").write_text(
                json.dumps({"sha": None, "reason": f"superseded by {later}"}) + "\n", encoding="utf-8")
            print(f"{run_id} superseded by {later}")
            continue
        sha, error = commit(own, message(run_id, command, own, conflicts, role, carried))
        if error:
            first = error.splitlines()[0] if error else ""
            alert(f"run {run_id} not committed: {first} (it stays pending; fix it, then run /backup again)")
            print(f"commit_runs: {run_id}: {error}", file=sys.stderr)
            return 1
        record = {"sha": sha} if sha else {"sha": None, "reason": "already committed"}
        (RUNS / run_id / "committed").write_text(json.dumps(record) + "\n", encoding="utf-8")
        print(f"{run_id} {sha or 'already committed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
