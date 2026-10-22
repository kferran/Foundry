"""Settings, state files and alerts shared by the watch's modules (phase D spec §3.1, §3.8).

State lives in system/logs/watch/: cursors.json, the calendar snapshot, the item ledger and the today-file ledger.
"""
from pathlib import Path

from vaultlib import now as nowmod
from vaultlib.connector import Fail
from vaultlib.state import append, load, records, save  # noqa: F401  (re-exported for the watch's modules)
from vaultlib.triage import config

STATE = Path("system") / "logs" / "watch"
QUERIES = ("watch", "mpim", "own", "capture")
WATCH_KINDS = ("meeting_change", "deadline", "incident", "blocked", "decision", "partner")
INBOUND_KINDS = ("request", "incident", "deadline")
CHANGES = ("cancelled", "moved", "other")


def truthy(value, default: bool) -> bool:
    if value is None or value == "":
        return default
    return str(value).lower() == "true"


def state(vault) -> Path:
    p = Path(vault) / STATE
    p.mkdir(parents=True, exist_ok=True)
    return p


def partition(vault) -> str:
    """watch_partition (default work), checked before any session runs."""
    value = str(config(vault).get("watch_partition") or "work")
    if value not in nowmod.PARTITIONS:
        raise Fail(2, f"watch_partition must be one of {', '.join(nowmod.PARTITIONS)}, not {value!r}")
    return value


def capture_partition(vault) -> str:
    """capture_partition, else default_partition, else personal; shared holds no inbox partition of its own."""
    cfg = config(vault)
    value = str(cfg.get("capture_partition") or cfg.get("default_partition") or "personal")
    return value if value in nowmod.PARTITIONS else "personal"


def alert(vault, day: str, clock: str, tag: str, text: str, key: str = "") -> bool:
    """Append `- HH:MM:SS [tag] text` to the day's alerts file; with a key, at most once a day per key. True when
    written."""
    path = Path(vault) / "system" / "logs" / f"alerts_{day}.md"
    line = f"- {clock} [{tag}] {text}\n"
    if key and path.is_file() and f"[{tag}] {key}" in path.read_text(encoding="utf-8"):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
    return True
