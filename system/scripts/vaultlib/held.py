"""Stale claims a research Work Order found, held in raw/<p>/held/ until the owner ticks their Now line (confinement
spec §3.7, #301 S9): web-sourced text reaches ingest only after the owner has seen it."""
import os
import re
from datetime import date
from pathlib import Path

from . import now as nowmod
from .schema import PARTITIONS

HELD = re.compile(r"raw/[a-z]+/held/[^\s)]+\.stale-claims\.md")
PREFIX = "Review {n} stale claims from a research Work Order before they reach the wiki: "


def page(partition: str) -> str:
    """The Now page a held file's line goes on: shared has none, so its lines go on work."""
    return partition if partition in nowmod.PARTITIONS else "work"


def statement(rel: str, n: int) -> str:
    return PREFIX.format(n=n) + rel


def add_line(vault, path: Path, n: int, today: str) -> None:
    """Add the owed line for a held file (no evidence, no via: it never closes or expires on its own). The caller holds
    run.lock. A line over the cap is refused, never cut, since a cut line loses the path; a refusal raises ValueError,
    as nowmod.add does."""
    rel = Path(path).relative_to(vault).as_posix()
    nowmod.add(vault, page(rel.split("/")[1]), "owed", statement(rel, n), today)


def _own(m, rel: str) -> bool:
    """The runner's own line for rel and nothing else (review of PR C): owed, no who, no evidence, no via, and the
    statement held.statement writes (a due or rec field the clock adds is ignored). A line that merely names the path,
    such as a mail line that expires or a pull request line a merge closes, decides nothing."""
    bare = nowmod.REC.sub("", nowmod.DUE.sub("", m["statement"])).strip()
    return (m["kind"] == "owed" and not m["who"] and not m["evidence"] and not nowmod.VIA.search(m["statement"])
            and re.fullmatch(re.escape(PREFIX).replace(r"\{n\}", r"\d+") + re.escape(rel), bare) is not None)


def _mark(vault, rel: str, since: str, today: str) -> str | None:
    """The box of rel's own line ("x", "-" or " "), on the page or in its archive since the file was written; a closed
    line wins over an open one. None when there is no such line."""
    lp = page(rel.split("/")[1])
    lines = "\n".join([nowmod.read(vault, lp), *nowmod.archived(vault, lp, since, today)]).splitlines()
    marks = {m["mark"] for line in lines if rel in line and (m := nowmod.LINE.match(line)) and _own(m, rel)}
    return next((k for k in ("x", "X", "-", " ") if k in marks), None)


def step(vault, today: str, alert) -> None:
    """Intake's Now step, under run.lock: a ticked line ([x]) releases its held file to raw/<p>/notes/, where ingest
    takes it; a crossed one ([-]) moves it to raw/<p>/held/rejected/, never indexed or ingested (spec §3.7 named
    archive/, which recall reads); an open one waits; a file with no line (its add failed) gets the line again."""
    for p in PARTITIONS:
        d = Path(vault) / "raw" / p / "held"
        for f in sorted(d.glob("*.stale-claims.md")):
            rel = f.relative_to(vault).as_posix()
            since = date.fromtimestamp(f.stat().st_mtime).isoformat()
            mark = _mark(vault, rel, since, today)
            try:
                if mark is None:
                    n = sum(line.startswith("- ") for line in f.read_text(encoding="utf-8").splitlines())
                    add_line(vault, f, n, today)
                elif mark in "xX-":
                    dest = (d.parent / "notes" if mark in "xX" else d / "rejected") / f.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(f, dest)
            except (OSError, ValueError) as exc:   # left where it is: the next tick tries again
                alert(f"held stale claims {rel}: {exc.__class__.__name__}: {exc}")
