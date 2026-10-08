"""Per-item outcome files, the health file and the night's report (Nightshift spec §6)."""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import nightshift_check as nc

DIR = "system/logs/nightshift"
HEALTH_ORDER = ("claude", "gh", "ssh", "sandbox", "usage", "last_tick")


def item_dir(vault, item_id: str) -> Path:
    return Path(vault) / DIR / "items" / item_id


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_outcome(vault, outcome: dict) -> None:
    _atomic(item_dir(vault, outcome["id"]) / "outcome.json", json.dumps(outcome, indent=1, sort_keys=True))


def write_health(vault, date: str, health: dict) -> None:
    _atomic(Path(vault) / DIR / f"health-{date}.json", json.dumps(health, indent=1, sort_keys=True))


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


def build(vault, date: str) -> str:
    hp = Path(vault) / DIR / f"health-{date}.json"
    health = json.loads(hp.read_text(encoding="utf-8")) if hp.is_file() else {}
    parts = [f"{k.replace('_', ' ')} {health[k]}" for k in HEALTH_ORDER if health.get(k)]
    lines = [f"# Work Orders: {date}", "> Health: " + (" · ".join(parts) if parts else "not checked"),
             *([f"> Held: {health['held']}"] if health.get("held") else []), ""]
    outcomes = _outcomes(vault, date)
    if not outcomes:
        return "\n".join(lines + ["Nothing ran.", ""])
    needs = [f"- [ ] {_clean(n)} ({o['id']})" for o in outcomes for n in o.get("needs") or []]
    if needs:
        lines += ["## Needs you", *needs, ""]
    tz = ZoneInfo(str(nc.config(vault).get("timezone") or "UTC"))
    lines += ["## Items", "| Item | Kind | Result | Time | Notes |", "|---|---|---|---|---|"]
    for o in outcomes:
        state = o["state"] + (f" ({o['reason']})" if o.get("reason") else "")
        span = f"{_hm(o.get('started_at'), tz)}–{_hm(o.get('finished_at'), tz)}"
        lines.append(f"| {o['id']} | {o['kind']} | {_clean(state)} | {span} | {_clean(o.get('result') or o.get('notes'))} |")
    return "\n".join(lines) + "\n"


def write(vault, date: str) -> Path:
    path = Path(vault) / DIR / f"{date}.md"
    _atomic(path, build(vault, date))
    return path
