"""Stale claims a research Work Order found, held in raw/<p>/held/ until the owner ticks their Now line (confinement
spec §3.7, #301 S9): web-sourced text reaches ingest only after the owner has seen it."""
import os
import re
from datetime import date
from pathlib import Path

from . import now as nowmod

HELD = re.compile(r"raw/[a-z]+/held/[^\s)]+\.stale-claims\.md")


def page(partition: str) -> str:
    """The Now page a held file's line goes on: shared has none, so its lines go on work."""
    return partition if partition in nowmod.PARTITIONS else "work"


def statement(rel: str, n: int) -> str:
    # The path is last and the id is inside it: fit cuts from the end, and the path is short enough to survive.
    return f"Review {n} stale claims from a research Work Order before they reach the wiki: {rel}"


def add_line(vault, path: Path, n: int, today: str) -> None:
    """Add the owed line for a held file (no evidence, no via: it never closes or expires on its own). The caller holds
    run.lock; a refusal raises ValueError, as nowmod.add does."""
    rel = Path(path).relative_to(vault).as_posix()
    nowmod.add(vault, page(rel.split("/")[1]), "owed", statement(rel, n), today, fit=True)


def _mark(vault, rel: str, since: str, today: str) -> str | None:
    """The box of the line naming rel ("x", "-" or " "), on the page or in its archive since the file was written;
    a closed line wins over an open one. None when no line names it."""
    lp = page(rel.split("/")[1])
    marks = {m["mark"] for line in "\n".join([nowmod.read(vault, lp), *nowmod.archived(vault, lp, since, today)]).splitlines()
             if rel in line and (m := nowmod.LINE.match(line))}
    return next((k for k in ("x", "X", "-", " ") if k in marks), None)


def step(vault, today: str, alert) -> None:
    """Intake's Now step, under run.lock: a ticked line ([x]) releases its held file to raw/<p>/notes/, where ingest
    takes it; a crossed one ([-]) moves it to raw/<p>/archive/, never ingested; an open one waits; a file with no line
    (its add failed) gets the line again."""
    for d in sorted(Path(vault).glob("raw/*/held")):
        for f in sorted(d.glob("*.stale-claims.md")):
            rel = f.relative_to(vault).as_posix()
            since = date.fromtimestamp(f.stat().st_mtime).isoformat()
            mark = _mark(vault, rel, since, today)
            try:
                if mark is None:
                    n = sum(line.startswith("- ") for line in f.read_text(encoding="utf-8").splitlines())
                    add_line(vault, f, n, today)
                elif mark in "xX-":
                    dest = d.parent / ("notes" if mark in "xX" else "archive") / f.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(f, dest)
            except (OSError, ValueError) as exc:   # left where it is: the next tick tries again
                alert(f"held stale claims {rel}: {exc.__class__.__name__}: {exc}")
