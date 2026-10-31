"""Stale claims a research Work Order found, held in raw/<p>/held/ until the owner ticks their Now line (confinement
spec §3.7, #301 S9): web-sourced text reaches ingest only after the owner has seen it."""
import re
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
