"""State and notes for the telemetry fetch (Plan 11 spec §3.5, §4, §5.1)."""
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import re

from . import frontmatter
from .telemetry import event_id, sanitize, trace_id

STATE = "system/logs/telemetry_state.json"
QUIET = timedelta(days=7)
NOTE_FIELDS = ("type", "service", "exception", "operation_id", "detected_at", "codebase", "partition", "environment",
               "source", "kind", "fingerprint", "count", "last_seen", "status", "resolved_at", "substatus", "regressed",
               "sentry_issue", "covered", "culprit", "link")


def _aware(v: str) -> datetime:
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _clean(g: dict) -> dict:
    """Enforce the data policy on every whitelisted field, whatever the caller passed."""
    g = dict(g)
    g["keys"] = {k: (event_id(v) if k == "event_id" else sanitize(v)) for k, v in (g.get("keys") or {}).items()}
    g["service"] = sanitize(g.get("service"))
    if g.get("culprit"):
        g["culprit"] = sanitize(g["culprit"])
    ex = str(g.get("exception") or "")
    if g.get("kind") == "log" and "#" in ex:
        scope, eid = ex.rsplit("#", 1)
        g["exception"] = sanitize(scope) + "#" + event_id(eid)
    else:
        g["exception"] = sanitize(ex)
    op = str(g.get("operation_id") or "")
    g["operation_id"] = trace_id(op) or (op if op.isdigit() else "")
    si = g.get("sentry_issue")
    g["sentry_issue"] = si if si and re.fullmatch(r"[A-Za-z0-9_-]+", str(si)) else None
    if g.get("link"):
        g["link"] = str(g["link"]).split("?", 1)[0]
    return g


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Store:
    def __init__(self, vault: Path):
        self.vault = Path(vault)
        self.state = {"sources": {}, "groups": {}, "alerts": {}}

    def note_rel(self, source: str, fp: str) -> str:
        return f"raw/telemetry/{source}-{fp}.md"

    def load(self) -> list:
        p = self.vault / STATE
        if not p.exists():
            self._rebuild()
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("groups"), dict):
                raise ValueError("bad shape")
            self.state = {"sources": data.get("sources", {}), "groups": data["groups"], "alerts": data.get("alerts", {})}
            return []
        except ValueError:
            q = self.vault / "system" / "quarantine"
            q.mkdir(parents=True, exist_ok=True)
            dest = q / f"telemetry_state-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
            shutil.move(str(p), dest)
            self._rebuild()
            return [f"telemetry: state file was corrupt; moved to quarantine as {dest.name} and rebuilt from notes"]

    def _rebuild(self) -> None:
        self.state = {"sources": {}, "groups": {}, "alerts": {}}
        for p in sorted((self.vault / "raw" / "telemetry").glob("*.md")):
            d = frontmatter.parse(p.read_text(encoding="utf-8")).data or {}
            if d.get("type") != "production_error" or not d.get("fingerprint") or not d.get("source"):
                continue
            self.state["groups"][f"{d['source']}/{d['fingerprint']}"] = {
                "note": p.relative_to(self.vault).as_posix(), "first_seen": d.get("detected_at"),
                "last_seen": d.get("last_seen"), "count": int(d.get("count") or 0), "status": d.get("status", "active"),
                "kind": d.get("kind"), "sentry_id": (d.get("fingerprint") or "")[2:] if d.get("kind") == "sentry" else None}

    def save(self) -> None:
        _atomic(self.vault / STATE, json.dumps(self.state, indent=1, sort_keys=True))

    def _write_note(self, rel: str, fm: dict, body: str) -> None:
        lines = [f"{k}: {json.dumps(str(fm[k]), ensure_ascii=False)}" for k in NOTE_FIELDS if fm.get(k) not in (None, "")]
        lines[0] = "type: production_error"
        _atomic(self.vault / rel, "---\n" + "\n".join(lines) + "\n---\n" + body)

    def _body(self, g: dict, fm: dict) -> str:
        rows = "\n".join(f"| {k} | {v} |" for k, v in sorted((g.get("keys") or {}).items()))
        reopen = f"Reopen in ADX:\n\n```kql\n{g['reopen']}\n```\n" if g.get("reopen") else (
            f"Sentry: {fm['link']}\n" if fm.get("link") else "")
        tpl = (self.vault / "system/templates/production-error.md")
        text = tpl.read_text(encoding="utf-8") if tpl.exists() else "# {{exception}}\n\n{{key_rows}}\n\n{{reopen}}\n"
        for k, v in {"exception": fm["exception"], "environment": fm["environment"], "key_rows": rows,
                     "count": fm["count"], "detected_at": fm["detected_at"], "last_seen": fm["last_seen"],
                     "status": fm["status"], "reopen": reopen}.items():
            text = text.replace("{{" + k + "}}", str(v))
        return text

    def upsert(self, g: dict, now: datetime) -> str:
        g = _clean(g)
        key = f"{g['source']}/{g['fingerprint']}"
        old = self.state["groups"].get(key)
        rel = old["note"] if old else self.note_rel(g["source"], g["fingerprint"])
        if old:
            count = int(g["count"]) if g["kind"] == "sentry" else int(old.get("count", 0)) + int(g["count"])
            first = old.get("first_seen") or g["detected_at"]
            regressed = bool(old.get("regressed")) or old.get("status") == "resolved"
            if old.get("last_seen") and _aware(old["last_seen"]) > _aware(g["last_seen"]):
                g["last_seen"] = old["last_seen"]
        else:
            count, first, regressed = int(g["count"]), g["detected_at"], False
        status = "deprecated" if old and old.get("status") == "deprecated" else "active"
        fm = {"type": "production_error", "service": g["service"], "exception": g["exception"],
              "operation_id": g["operation_id"], "detected_at": first, "codebase": g["codebase"],
              "partition": g["partition"], "environment": g["environment"], "source": g["source"], "kind": g["kind"],
              "fingerprint": g["fingerprint"], "count": count, "last_seen": g["last_seen"], "status": status,
              "substatus": g.get("substatus"), "regressed": "true" if regressed or g.get("substatus") == "regressed" else "false",
              "sentry_issue": g.get("sentry_issue"), "covered": "true" if g.get("covered") else "false",
              "culprit": g.get("culprit"), "link": g.get("link")}
        self._write_note(rel, fm, self._body(g, fm))
        self.state["groups"][key] = {"note": rel, "first_seen": first, "last_seen": g["last_seen"], "count": count,
                                     "status": status, "kind": g["kind"], "regressed": regressed,
                                     "sentry_id": g["fingerprint"][2:] if g["kind"] == "sentry" else None}
        return "updated" if old else "new"

    def set_status(self, key: str, status: str, now: datetime) -> None:
        grp = self.state["groups"][key]
        path = self.vault / grp["note"]
        note = frontmatter.parse(path.read_text(encoding="utf-8"))
        fm = dict(note.data or {})
        fm["status"] = status
        fm["resolved_at"] = now.isoformat() if status == "resolved" else None
        if status == "resolved":
            fm["regressed"] = "false"
            grp["regressed"] = False
        self._write_note(grp["note"], fm, note.body)
        grp["status"] = status

    def resolve_stale(self, source: str, now: datetime) -> int:
        n = 0
        for key, grp in list(self.state["groups"].items()):
            if not key.startswith(source + "/") or grp.get("status") != "active" or not grp.get("last_seen"):
                continue
            if now - datetime.fromisoformat(grp["last_seen"].replace("Z", "+00:00")) > QUIET:
                self.set_status(key, "resolved", now)
                n += 1
        return n

    def active(self, source: str) -> list:
        return [dict(grp, key=k) for k, grp in self.state["groups"].items()
                if k.startswith(source + "/") and grp.get("status") == "active"]
