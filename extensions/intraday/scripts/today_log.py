#!/usr/bin/env python3
"""The today file's writer (phase D spec §3.6): appends the day's watch items, calendar changes, captures, session
digests and imported meetings to briefings/<date>.today.md. It makes no model call.

Usage: today_log.py tick            run as the intraday extension's intake tick; a client, a busy run.lock or an
                                    empty day writes nothing
       today_log.py summary <date>  print the day's watch items counted by kind (the brief section)
       today_log.py open <date>     print the Now lines the watch added that day that are still open (the debrief)
Exit: 0 ok; 1 an unexpected error (the intake raises its alert and runs the tick again); 2 usage.

The file is append-only and only the server writes it, so it never conflicts with the owner's edits to the briefing.
A ledger (system/logs/watch/today-<YYYY-MM>.jsonl) keys each written entry by its source and the source's sha256: an
entry is never written twice, and a digest that changes after it was written is not written again. Only `work`
sources are written, as the brief does. Copied text is one line, masked, cut at 200 characters, and cannot become a
link or a checkbox.
"""
import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(VAULT / "system" / "scripts")]
from vaultlib.api import frontmatter, Intake, open_actions, owner_names, redact_credentials  # noqa: E402
from watchlib import route  # noqa: E402
from watchlib.common import alert, append, config, records, state  # noqa: E402

TEXT_MAX = 200
OUTCOME = re.compile(r"^\s*(?:#{1,6}\s*|\*\*)\s*outcome\b", re.I)
DELIVERED = re.compile(r"^\s*(?:#{1,6}\s*|\*\*)\s*delivered\b", re.I)
HEADING = re.compile(r"^\s*(?:#{1,6}\s+\S|\*\*[^*]+\*\*\s*:?\s*$)")


def clean(text) -> str:
    """One line, credentials masked, no wikilink brackets or leading checkbox, at most TEXT_MAX characters."""
    text = redact_credentials(" ".join(str(text or "").split()))
    text = text.replace("[[", "").replace("]]", "")
    text = re.sub(r"^(?:- )?\[.\]\s*", "", text)
    return text if len(text) <= TEXT_MAX else text[: TEXT_MAX - 1].rstrip() + "…"


def section(body: str, start) -> list:
    out, on = [], False
    for line in body.splitlines():
        if start.match(line):
            on = True
            rest = re.sub(r"^\s*(?:#{1,6}\s*|\*\*)\s*\w+(?:\*\*)?\s*:?\s*", "", line).strip()
            if rest:
                out.append(rest)
            continue
        if on and HEADING.match(line):
            break
        if on:
            out.append(line)
    return out


def _plain(line: str) -> str:
    """A digest line without its bullet marker or bold markers: Outcome is often written as `- **Label:** text`."""
    return re.sub(r"^[-*+]\s+", "", line.strip()).replace("**", "")


def digest_entry(body: str) -> list:
    outcome = " ".join(_plain(x) for x in section(body, OUTCOME) if x.strip())
    first = re.split(r"(?<=[.!?])\s", outcome, maxsplit=1)[0] if outcome else "a session ended"
    lines = [clean(first)]
    lines += [f"  - delivered: {clean(_plain(x))}" for x in section(body, DELIVERED) if x.strip().startswith("- ")]
    return lines


def digests(vault: Path, day: str) -> list:
    """(source, sha, time, lines) for each work session digest created today, pending or compiled. A digest's name
    starts with its local creation time (%Y-%m-%d-%H%M, memory_capture.sh), so only today's files are read."""
    out = []
    for folder in ("notes", "archive"):
        for p in sorted((vault / "raw" / "work" / folder).glob(f"{day}-*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            note = frontmatter.parse(text)
            data = note.data or {}
            created = str(data.get("created_at") or "")
            if data.get("type") != "session_digest" or not created.startswith(day) or data.get("partition") != "work":
                continue
            lines = digest_entry(note.body)
            lines[0] = f"{lines[0]} ({p.relative_to(vault).as_posix()})"
            out.append((f"digest:{p.name}", hashlib.sha256(text.encode()).hexdigest(), created[11:16], lines))
    return out


def meetings(vault: Path, day: str) -> list:
    """(source, sha, time, lines) for each work meeting note imported today; a note not there yet waits."""
    out, owners = [], owner_names(vault)
    for r in records(vault / "system" / "logs" / f"meetings-{day[:7]}.jsonl"):
        note = r.get("note")
        if r.get("kind") != "imported" or not str(r.get("time", "")).startswith(day) or not isinstance(note, str):
            continue
        if not note.startswith("wiki/work/"):
            continue
        p = vault / note
        try:
            body = frontmatter.parse(p.read_text(encoding="utf-8")).body
        except (OSError, UnicodeDecodeError):
            continue
        decisions = sum(1 for x in section(body, re.compile(r"^##\s+Decisions\b")) if x.strip().startswith("- "))
        mine = [a for who, _, a in open_actions(body) if {o.casefold() for o in who} & owners]
        text = f"[[{p.stem}]]: {decisions} decision{'s' if decisions != 1 else ''}"
        if mine:
            text += "; yours: " + "; ".join(f'"{clean(a)}"' for a in mine[:3])
        out.append((f"meeting:{note}", "", str(r.get("time", ""))[11:16], [text]))
    return out


def tick() -> int:
    if str(config(VAULT).get("machine_role") or "standalone") == "client":
        return 0
    intake = Intake(VAULT)
    day = intake.today()
    try:
        with intake.lock("run.lock", timeout=0):
            return write(VAULT, day, intake.dt().strftime("%H:%M:%S"))
    except TimeoutError:
        return 0   # a run holds the lock: the next tick writes


def write(vault: Path, day: str, clock: str) -> int:
    ledger = state(vault) / f"today-{day[:7]}.jsonl"
    done = {r.get("source") for r in records(ledger)}
    new = []
    for r in records(route.ledger_path(vault, day)):
        if r.get("day") == day and r.get("partition") == "work" and f"item:{r.get('key')}" not in done:
            text = clean(r.get("text"))
            if r.get("now") == "added":
                text += " → Now"
            link = f" {r['link']}" if r.get("link") else ""
            new.append((f"item:{r['key']}", "", str(r.get("time") or clock[:5]), [f"**{r.get('kind')}** {text}{link}"]))
    for source, sha, at, lines in digests(vault, day):
        if source not in done:
            new.append((source, sha, at or clock[:5], [f"**session** {lines[0]}", *lines[1:]]))
    for source, sha, at, lines in meetings(vault, day):
        if source not in done:
            new.append((source, sha, at or clock[:5], [f"**meeting** {lines[0]}"]))
    if not new:
        return 0
    path = vault / "briefings" / f"{day}.today.md"
    try:
        old = path.read_text(encoding="utf-8") if path.is_file() else f'---\ntype: today\ndate: "{day}"\n---\n'
    except (OSError, UnicodeDecodeError) as exc:
        alert(vault, day, clock, "intraday", f"today file unreadable: {path.name} ({exc.__class__.__name__})",
              key="today file unreadable:")
        return 0
    body = "".join(f"- {at} {lines[0]}\n" + "".join(f"{x}\n" for x in lines[1:])
                   for _, _, at, lines in sorted(new, key=lambda e: e[2]))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(old.rstrip("\n") + "\n" + body, encoding="utf-8")
    tmp.replace(path)
    for source, sha, _, _ in new:
        append(ledger, {"source": source, "sha256": sha, "day": day})
    return 0


def summary(vault: Path, day: str) -> str:
    """The day's watch items counted by kind, for the next brief: "2 meeting, 1 deadline" or "none"."""
    counts = {}
    for r in records(route.ledger_path(vault, day)):
        if r.get("day") == day:
            counts[r.get("kind")] = counts.get(r.get("kind"), 0) + 1
    return ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "none"


def still_open(vault: Path, day: str) -> list:
    """The Now lines the watch added that day that are still open, for the debrief (B8)."""
    from vaultlib.api import now as nowmod
    from watchlib.common import partition
    page = nowmod.open_lines(nowmod.read(vault, partition(vault)))
    links = [r["link"] for r in records(route.ledger_path(vault, day)) if r.get("day") == day and r.get("now") == "added"
             and r.get("link")]
    return [line for line in page if any(link in line for link in links)]


def main(argv) -> int:
    args = argv[1:]
    if args == ["tick"]:
        return tick()
    if len(args) == 2 and args[0] == "summary":
        print(summary(VAULT, args[1]))
        return 0
    if len(args) == 2 and args[0] == "open":
        print("".join(f"{line}\n" for line in still_open(VAULT, args[1])), end="")
        return 0
    print("usage: today_log.py tick | summary <date> | open <date>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
