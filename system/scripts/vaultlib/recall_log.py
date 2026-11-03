"""The recall log (recall R0 spec §3): what recall pushed and what sessions pulled, by count, id and path only, to
system/logs/recall-<YYYY-MM>.jsonl. Stdlib only, so the PostToolUse slow path loads no index or CLI."""
import re
from datetime import datetime
from pathlib import Path

from .state import append_jsonl

SID = re.compile(r"^[A-Za-z0-9-]{1,100}$")


def write(vault, record: dict) -> None:
    """Append one line with its ts first; a failure is swallowed, so logging never changes a caller's result."""
    try:
        now = datetime.now().astimezone()
        append_jsonl(Path(vault) / "system" / "logs" / f"recall-{now:%Y-%m}.jsonl",
                     {"ts": now.isoformat(timespec="seconds"), **record})
    except Exception:  # noqa: BLE001 - spec §3.1: every write is wrapped
        pass
