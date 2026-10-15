"""One reader for system/quarantine/ (quarantine-in-brief spec §2): the brief and the debrief both read its rows, so
they agree. A row is one held thing with its since date and its way out; sidecars are never rows."""
import json
import re
import shlex
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

STAMP = re.compile(r"(\d{8})T\d{6}")   # a run id or a telemetry backup name starts with %Y%m%dT%H%M%S
SIDECARS = (".origin.json", ".reason.txt")


@dataclass
class Row:
    kind: str       # poisoned | meeting | run | telemetry_state
    path: str       # vault-relative
    origin: str     # where a poisoned input came from, else ""
    since: date
    days: int
    reason: str
    way_out: str


def _mtime(path: Path) -> date:
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def _named(name: str, path: Path) -> date:
    m = STAMP.search(name)
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date() if m else _mtime(path)
    except ValueError:
        return _mtime(path)


def _poisoned(vault: Path, folder: Path):
    for item in sorted(p for p in folder.iterdir() if p.is_file() and not p.name.endswith(SIDECARS)):
        try:
            info = json.loads((folder / f"{item.name}.origin.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        info = info if isinstance(info, dict) else {}
        try:
            since = datetime.fromisoformat(str(info.get("poisoned_at"))).date()
        except ValueError:
            since = _mtime(item)
        way = (f"system/scripts/intake.py --retry-input {shlex.quote(item.name)}" if info.get("origin")
               else "no origin recorded: move it to raw/inbox/ by hand")
        yield "poisoned", item, str(info.get("origin") or ""), since, "", way


def _meetings(vault: Path, folder: Path):
    for item in sorted(p for p in folder.iterdir() if p.is_file() and not p.name.endswith(SIDECARS)):
        try:
            reason = (folder / f"{item.name}.reason.txt").read_text(encoding="utf-8").strip().splitlines()[0]
        except (OSError, IndexError):
            reason = ""
        yield "meeting", item, "", _mtime(item), reason, "fix the source; the next fetch or drop imports it"


def _ledger(vault: Path) -> list:
    out = []
    for path in sorted((Path(vault) / "system" / "logs").glob("runs-*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                out.append(record)
    return out


def _published_later(ledger: list, run_id: str) -> str:
    """The run id of a later run that published an input of run_id's, or "" (a conflict-held run whose input
    published on retry is resolved: live acceptance 2026-10-15)."""
    shas = next((set(r.get("input_sha256") or []) for r in ledger if r.get("run_id") == run_id), set())
    for r in ledger:
        rid = str(r.get("run_id") or "")
        publish = r.get("publish") if isinstance(r.get("publish"), dict) else {}
        if (rid > run_id and shas & set(r.get("input_sha256") or [])
                and publish.get("status") in ("published", "recovered")):
            return rid
    return ""


def items(vault, today: date) -> list:
    root = Path(vault) / "system" / "quarantine"
    if not root.is_dir():
        return []
    found, ledger = [], None
    for entry in sorted(root.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir() and entry.name == "poisoned":
            found += _poisoned(vault, entry)
        elif entry.is_dir() and entry.name == "meetings":
            found += _meetings(vault, entry)
        elif entry.is_dir():   # a held-back run's staging: its input is retried or poisoned on its own
            ledger = _ledger(vault) if ledger is None else ledger
            later = _published_later(ledger, entry.name)
            found.append(("run", entry, "", _named(entry.name, entry),
                          f"resolved: its input published in run {later}" if later else "", "safe to delete"))
        elif entry.name.startswith("telemetry_state-"):   # the store was rebuilt without it
            found.append(("telemetry_state", entry, "", _named(entry.name, entry), "", "safe to delete"))
    rows = [Row(kind, p.relative_to(vault).as_posix(), origin, since, max((today - since).days, 0),
                " ".join(reason.split())[:160], way) for kind, p, origin, since, reason, way in found]
    return sorted(rows, key=lambda r: (r.since, r.path))


def render(rows) -> str:
    if not rows:
        return "none\n"
    out = []
    for r in rows:
        days = f"{r.days} day" + ("" if r.days == 1 else "s")
        why = f": {r.reason}" if r.reason else ""
        out.append(f"- {r.kind} {r.origin or r.path}, since {r.since.isoformat()} ({days}){why}. {r.way_out}\n")
    return "".join(out)
