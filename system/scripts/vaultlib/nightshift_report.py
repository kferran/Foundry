"""Per-item outcome files, the health file and the night's report (Nightshift spec §6)."""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import nightshift_check as nc

DIR = "system/logs/nightshift"
HEALTH_ORDER = ("claude", "gh", "ssh", "sandbox", "usage", "last_tick")


def item_dir(vault, item_id: str) -> Path:
    return Path(vault) / DIR / "items" / item_id


_UMASK = os.umask(0)   # read once: os.umask can only be read by setting it
os.umask(_UMASK)


def _atomic(path: Path, text: str) -> None:
    # A temp file per writer: up to 3 Work Orders finish at once (#229), and a shared .tmp name loses a rename.
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
                                     suffix=".tmp", delete=False) as f:
        f.write(text)
    os.chmod(f.name, 0o666 & ~_UMASK)   # a temp file is 0600: keep the mode a plain write gives
    os.replace(f.name, path)


def write_outcome(vault, outcome: dict) -> None:
    _atomic(item_dir(vault, outcome["id"]) / "outcome.json", json.dumps(outcome, indent=1, sort_keys=True))


def write_health(vault, date: str, health: dict) -> None:
    _atomic(Path(vault) / DIR / f"health-{date}.json", json.dumps(health, indent=1, sort_keys=True))


def record_usage(vault, date: str, usage: dict, at: str) -> None:
    """Merge one session's 5-hour and 7-day readings into the day's health file (usage ceiling spec);
    a session without a reading leaves it alone."""
    if not usage:
        return
    hp = Path(vault) / DIR / f"health-{date}.json"
    try:
        h = json.loads(hp.read_text(encoding="utf-8")) if hp.is_file() else {}
    except (OSError, json.JSONDecodeError):
        h = {}
    five, seven = usage.get("five_hour"), usage.get("seven_day")
    h = (h if isinstance(h, dict) else {}) | {
        "usage5": five, "usage7": seven, "usage5_at": at,
        "usage": f"5h {round((five or 0) * 100)}% / 7d {round((seven or 0) * 100)}%"}
    write_health(vault, date, h)


def _outcomes(vault, date: str) -> list:
    out = []
    for p in sorted((Path(vault) / DIR / "items").glob("*/outcome.json")):
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if o.get("report_date") == date:
            out.append(o)
    return sorted(out, key=lambda o: str(o.get("started_at", "")))


def _clean(text, limit=300) -> str:
    """Session-supplied text as one table-safe line: no newlines, no pipes, bounded."""
    return " ".join(str(text or "").split()).replace("|", "/")[:limit]


def _hm(value, tz) -> str:
    """An ISO timestamp as HH:MM in the vault's timezone; empty when it is missing or unreadable."""
    try:
        return datetime.fromisoformat(str(value)).astimezone(tz).strftime("%H:%M")
    except ValueError:
        return ""


def data(vault, date: str) -> dict:
    """The report as nightshift.py report --json prints it (#375), read from the files only; build() formats it."""
    hp = Path(vault) / DIR / f"health-{date}.json"
    health = json.loads(hp.read_text(encoding="utf-8")) if hp.is_file() else {}
    held = health.pop("held", None) or None
    outcomes = _outcomes(vault, date)
    return {"date": date, "health": health, "held": held,
            "needs": [{"id": o["id"], "text": _clean(n)} for o in outcomes for n in o.get("needs") or []],
            "items": [{"id": o["id"], "kind": o["kind"], "state": o["state"], "reason": _clean(o.get("reason")) or None,
                       "started_at": o.get("started_at") or None, "finished_at": o.get("finished_at") or None,
                       "result": _clean(o.get("result")) or None, "notes": _clean(o.get("notes")) or None}
                      for o in outcomes]}


def build(vault, date: str) -> str:
    d = data(vault, date)
    health = d["health"]
    parts = [f"{k.replace('_', ' ')} {health[k]}" for k in HEALTH_ORDER if health.get(k)]
    lines = [f"# Work Orders: {date}", "> Health: " + (" · ".join(parts) if parts else "not checked"),
             *([f"> Held: {d['held']}"] if d["held"] else []), ""]
    if not d["items"]:
        return "\n".join(lines + ["Nothing ran.", ""])
    if d["needs"]:
        lines += ["## Needs you", *[f"- [ ] {n['text']} ({n['id']})" for n in d["needs"]], ""]
    tz = ZoneInfo(str(nc.config(vault).get("timezone") or "UTC"))
    lines += ["## Items", "| Item | Kind | Result | Time | Notes |", "|---|---|---|---|---|"]
    for o in d["items"]:
        state = o["state"] + (f" ({o['reason']})" if o["reason"] else "")
        span = f"{_hm(o['started_at'], tz)}–{_hm(o['finished_at'], tz)}"
        lines.append(f"| {o['id']} | {o['kind']} | {_clean(state)} | {span} | {o['result'] or o['notes'] or ''} |")
    return "\n".join(lines) + "\n"


def write(vault, date: str) -> Path:
    path = Path(vault) / DIR / f"{date}.md"
    _atomic(path, build(vault, date))
    return path
