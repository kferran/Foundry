"""Pure parts of the telemetry fetch (Plan 11 spec §2.1, §3.1, §3.3): sources, windows, KQL, keys."""
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import frontmatter
from .redact import redact

LAG = {"adx": timedelta(minutes=10), "sentry": timedelta(minutes=2)}
FIRST = timedelta(hours=24)
CAP = timedelta(days=7)
GUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b")
DIGITS = re.compile(r"\d{4,}")
QUERY = re.compile(r"\?\S*")


@dataclass
class Source:
    path: str
    name: str
    codebase: str
    partition: str
    environment: str
    kind: str
    enabled: bool = True
    rank: int = 50
    sentry_url: str | None = None
    sentry_org: str | None = None
    sentry_projects: list = field(default_factory=list)
    sentry_query: str = "is:unresolved level:[error,fatal]"
    adx_cluster: str | None = None
    adx_database: str | None = None
    adx_filter: dict = field(default_factory=dict)
    adx_signals: list = field(default_factory=lambda: ["logs", "spans"])
    adx_group_keys: list = field(default_factory=list)
    covers: str | None = None


def _fm(path: Path) -> dict:
    note = frontmatter.parse(path.read_text(encoding="utf-8"))
    return note.data or {}


def load_sources(vault: Path) -> list:
    vault = Path(vault)
    out = []
    for p in sorted((vault / "system" / "telemetry").glob("*.md")):
        if p.name == "example.md":
            continue
        d = _fm(p)
        if d.get("type") != "telemetry_source":
            continue
        cb = vault / "system" / "codebases" / f"{d.get('codebase', '')}.md"
        partition = (_fm(cb).get("partition") if cb.is_file() else None) or "work"
        out.append(Source(
            path=p.relative_to(vault).as_posix(), name=str(d.get("name", p.stem)), codebase=str(d.get("codebase", "")),
            partition=partition, environment=str(d.get("environment", "")), kind=str(d.get("kind", "")),
            enabled=str(d.get("enabled", "true")).lower() == "true", rank=int(d.get("rank", "50") or 50),
            sentry_url=d.get("sentry_url"), sentry_org=d.get("sentry_org"), sentry_projects=list(d.get("sentry_projects") or []),
            sentry_query=d.get("sentry_query") or "is:unresolved level:[error,fatal]",
            adx_cluster=d.get("adx_cluster"), adx_database=d.get("adx_database"), adx_filter=dict(d.get("adx_filter") or {}),
            adx_signals=list(d.get("adx_signals") or ["logs", "spans"]), adx_group_keys=list(d.get("adx_group_keys") or []),
            covers=d.get("covers")))
    return sorted(out, key=lambda s: (s.rank, s.name))


def window(checkpoint: str | None, now: datetime, kind: str):
    end = now - LAG[kind]
    start = datetime.fromisoformat(checkpoint) if checkpoint else now - FIRST
    moved = False
    if end - start > CAP:
        start, moved = end - CAP, True
    return start, end, moved


def _q(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _t(dt: datetime) -> str:
    return f"datetime({dt.strftime('%Y-%m-%dT%H:%M:%SZ')})"


def _filters(src: Source) -> list:
    return [f"| where tostring(ResourceAttributes[{_q(k)}]) == {_q(v)}" for k, v in sorted(src.adx_filter.items())]


def kql_logs(src: Source, start: datetime, end: datetime, limit: int = 500) -> str:
    extra = [f"module_{i} = tostring(LogsAttributes[{_q(k)}])" for i, k in enumerate(src.adx_group_keys)]
    by = ["service", "scope", "event_id"] + [f"module_{i}" for i in range(len(src.adx_group_keys))]
    return "\n".join(["Logs",
                      f"| where Timestamp >= {_t(start)} and Timestamp < {_t(end)} and SeverityNumber >= 17",
                      *_filters(src),
                      "| extend service = tostring(ResourceAttributes[\"service.name\"]), "
                      "scope = tostring(LogsAttributes[\"scope.name\"]), event_id = tostring(LogsAttributes[\"logrecord.event.id\"])"
                      + (", " + ", ".join(extra) if extra else ""),
                      f"| summarize n = count(), first = min(Timestamp), last = max(Timestamp), traces = dcount(TraceID), "
                      f"sample_trace = take_any(TraceID) by {', '.join(by)}",
                      f"| take {limit}"])


def kql_spans(src: Source, start: datetime, end: datetime, limit: int = 500) -> str:
    return "\n".join(["Traces",
                      f"| where StartTime >= {_t(start)} and StartTime < {_t(end)} and SpanKind == \"SPAN_KIND_SERVER\"",
                      *_filters(src),
                      "| extend status = toint(TraceAttributes[\"http.response.status_code\"])",
                      "| where SpanStatus == \"STATUS_CODE_ERROR\" or status >= 500",
                      "| extend service = tostring(ResourceAttributes[\"service.name\"]), "
                      "route = coalesce(tostring(TraceAttributes[\"http.route\"]), SpanName)",
                      "| summarize n = count(), first = min(StartTime), last = max(StartTime), traces = dcount(TraceID), "
                      "sample_trace = take_any(TraceID) by service, route, status",
                      f"| take {limit}"])


def kql_count(kql: str) -> str:
    """The group count of a logs or spans query: drop its take line and count."""
    return "\n".join(line for line in kql.split("\n") if not line.startswith("| take ")) + "\n| count"


def sanitize(value) -> str:
    text, _ = redact(str(value if value is not None else ""))
    text = QUERY.sub("", text)
    text = GUID.sub("<guid>", text)
    text = EMAIL.sub("<email>", text)
    text = DIGITS.sub("<n>", text)
    return text[:200]


def event_id(value) -> str:
    """A logger EventId is a code constant, the grouping key itself: keep a plain integer, sanitize anything else."""
    v = str(value if value is not None else "")
    return v if re.fullmatch(r"-?\d{1,9}", v) else sanitize(v)


def trace_id(value) -> str:
    """An opaque OpenTelemetry trace ID (hex); anything else is dropped."""
    v = str(value if value is not None else "")
    return v if re.fullmatch(r"[0-9a-fA-F]{16,32}", v) else ""


def fingerprint(source: str, signal: str, keys: dict) -> str:
    raw = "|".join([source, signal] + [f"{k}={keys[k]}" for k in sorted(keys)])
    return "a-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
