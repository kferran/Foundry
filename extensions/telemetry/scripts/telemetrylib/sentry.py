"""Sentry REST client for the telemetry fetch (Plan 11 spec §2.2, §3.2). Keeps the issue fields notes use, title included."""
import os
import re
import stat
import urllib.parse
from datetime import datetime
from pathlib import Path

from . import http
from .http import TelemetryError

KEEP = ("id", "shortId", "permalink", "project", "level", "status", "substatus", "firstSeen", "lastSeen",
        "count", "userCount", "type", "culprit", "environment", "title")
MAX_PAGES = 5
NEXT = re.compile(r'<[^>]*>;\s*rel="next";\s*results="(true|false)";\s*cursor="([^"]*)"')


def token_path() -> Path:
    env = os.environ.get("FOUNDRY_SENTRY_TOKEN_FILE")
    if env:
        return Path(env)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "foundry" / "sentry.token"


def token() -> str:
    p = token_path()
    try:
        mode = p.stat().st_mode
    except FileNotFoundError:
        raise TelemetryError("auth", f"no Sentry token at {p}; create it with mode 0600") from None
    if stat.S_IMODE(mode) & 0o077:
        raise TelemetryError("auth", f"{p} is readable by others; chmod 0600 it")
    tok = p.read_text(encoding="utf-8").strip()
    if not tok:
        raise TelemetryError("auth", f"{p} is empty")
    return tok


def _get(base: str, path: str, params: list) -> tuple:
    url = base.rstrip("/") + path + ("?" + urllib.parse.urlencode(params) if params else "")
    return http.json_call("GET", url, {"Authorization": f"Bearer {token()}", "Accept": "application/json"})


def project_ids(base: str, org: str, slugs: list) -> dict:
    found, cursor = {}, None
    for _ in range(MAX_PAGES):
        data, headers = _get(base, f"/api/0/organizations/{org}/projects/", [("cursor", cursor)] if cursor else [])
        for p in data or []:
            if p.get("slug") in slugs:
                found[p["slug"]] = str(p["id"])
        m = NEXT.search(headers.get("Link", ""))
        if not m or m.group(1) != "true":
            break
        cursor = m.group(2)
    for s in slugs:
        if s not in found:
            raise TelemetryError("bad", f"unknown project {s}")
    return found


def _slim(issue: dict) -> dict:
    out = {k: issue.get(k) for k in KEEP if k in issue and k not in ("type", "environment", "project")}
    out["project"] = (issue.get("project") or {}).get("slug")
    out["type"] = (issue.get("metadata") or {}).get("type") or issue.get("type")
    env = [t.get("value") for t in issue.get("tags") or [] if t.get("key") == "environment"]
    out["environment"] = env[0] if env else None
    return out


def issues(base: str, org: str, project_ids_: list, query: str, since: datetime) -> list:
    q = f"{query} lastSeen:>={since.strftime('%Y-%m-%dT%H:%M:%S')}".strip()
    params = [("project", i) for i in project_ids_] + [("query", q), ("statsPeriod", "14d"), ("limit", "100")]
    out, cursor = [], None
    for _ in range(MAX_PAGES):
        data, headers = _get(base, f"/api/0/organizations/{org}/issues/", params + ([("cursor", cursor)] if cursor else []))
        out += [_slim(i) for i in data or []]
        m = NEXT.search(headers.get("Link", ""))
        if not m or m.group(1) != "true":
            break
        cursor = m.group(2)
    return out


def issue_status(base: str, org: str, issue_id: str) -> str:
    data, _ = _get(base, f"/api/0/organizations/{org}/issues/{issue_id}/", [])
    return str((data or {}).get("status", "unresolved"))


def issue_for_trace(base: str, org: str, trace_id: str) -> dict | None:
    data, _ = _get(base, f"/api/0/organizations/{org}/events/", [
        ("dataset", "errors"), ("field", "issue"), ("field", "issue.id"),
        ("query", f"trace:{trace_id}"), ("statsPeriod", "14d"), ("per_page", "1")])
    rows = (data or {}).get("data") or []
    if not rows:
        return None
    short, iid = rows[0].get("issue"), str(rows[0].get("issue.id"))
    if not isinstance(short, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", short) or not iid.isdigit():
        return None
    return {"id": iid, "shortId": short}
