"""One telemetry fetch over every enabled source (Plan 11 spec §3, §5)."""
import argparse
import fcntl
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import kusto, sentry, telemetry as t
from .http import TelemetryError
from .telemetry_store import Store

LOCK = "system/telemetry.lock"
LOCK_WAIT = int(os.environ.get("TELEMETRY_LOCK_WAIT", "120"))
MAX_GROUPS = 500
MAX_LOOKUPS = 20
MAX_STATUS = 20
FAIL_ALERT = 3


class Usage(Exception):
    pass


def _parser():
    p = argparse.ArgumentParser(prog="telemetry_fetch.py", add_help=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--source")
    g.add_argument("--check")
    g.add_argument("--list", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def _alert(vault: Path, store: Store, now: datetime, key: str, msg: str) -> None:
    day = now.astimezone().strftime("%Y-%m-%d")
    if store.state["alerts"].get(key) == day:
        return
    store.state["alerts"][key] = day
    path = vault / "system" / "logs" / f"alerts_{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"- {now.astimezone().strftime('%H:%M:%S')} [telemetry] {msg}\n")


def _log(vault: Path, now: datetime, line: dict) -> None:
    path = vault / "system" / "logs" / f"telemetry-{now.strftime('%Y-%m')}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")


def _adx_groups(src, start, end, by_name, counters):
    groups = []
    for signal in src.adx_signals:
        kql = t.kql_logs(src, start, end, MAX_GROUPS) if signal == "logs" else t.kql_spans(src, start, end, MAX_GROUPS)
        rows = kusto.query(src.adx_cluster, src.adx_database, kql, MAX_GROUPS)
        if len(rows) >= MAX_GROUPS:
            total = kusto.query(src.adx_cluster, src.adx_database, t.kql_count(kql), 1)
            counters["truncated"] = int((total[0] if total else {}).get("Count", len(rows)))
        for r in rows:
            if signal == "logs":
                keys = {"service": t.sanitize(r.get("service")), "scope": t.sanitize(r.get("scope")),
                        "event_id": t.event_id(r.get("event_id"))}
                keys.update({k: t.sanitize(r.get(f"module_{i}")) for i, k in enumerate(src.adx_group_keys)})
                exception, kind = f"{keys['scope']}#{keys['event_id']}", "log"
                reopen_where = f'LogsAttributes["logrecord.event.id"] == "{keys["event_id"]}"'
            else:
                keys = {"service": t.sanitize(r.get("service")), "route": t.sanitize(r.get("route")),
                        "status": t.sanitize(r.get("status"))}
                exception, kind = f"{keys['route']} {keys['status']}", "span"
                reopen_where = f'SpanName has "{keys["route"].split(" ")[-1]}"'
            fp = t.fingerprint(src.name, kind, keys)
            groups.append({"fingerprint": fp, "source": src.name, "environment": src.environment, "codebase": src.codebase,
                           "partition": src.partition, "kind": kind, "service": keys["service"], "exception": exception,
                           "operation_id": t.trace_id(r.get("sample_trace")), "detected_at": str(r.get("first")),
                           "last_seen": str(r.get("last")), "count": int(r.get("n") or 0), "keys": keys,
                           "reopen": f"{'Logs' if kind == 'log' else 'Traces'}\n| where {reopen_where}"})
    return groups


def _cover(src, groups, by_name, store, counters):
    target = by_name.get(src.covers) if src.covers else None
    if not target:
        return
    lookups = 0
    for g in groups:
        if f"{g['source']}/{g['fingerprint']}" in store.state["groups"]:
            continue
        if lookups >= MAX_LOOKUPS:
            break
        lookups += 1
        hit = sentry.issue_for_trace(target.sentry_url, target.sentry_org, g["operation_id"])
        if hit:
            g["covered"], g["sentry_issue"] = True, hit["shortId"]
            counters["covered"] += 1


def _sentry_groups(src, start, store):
    ids = store.state["sources"].setdefault(src.name, {}).get("project_ids") or {}
    if set(ids) != set(src.sentry_projects):
        ids = sentry.project_ids(src.sentry_url, src.sentry_org, src.sentry_projects)
        store.state["sources"][src.name]["project_ids"] = ids
    out = []
    for i in sentry.issues(src.sentry_url, src.sentry_org, list(ids.values()), src.sentry_query, start):
        out.append({"fingerprint": f"s-{i['id']}", "source": src.name, "environment": src.environment,
                    "codebase": src.codebase, "partition": src.partition, "kind": "sentry",
                    "service": t.sanitize(i.get("environment") or i.get("project")),
                    "exception": t.sanitize(i.get("type") or "error"), "operation_id": str(i["id"]),
                    "detected_at": i.get("firstSeen"), "last_seen": i.get("lastSeen"), "count": int(i.get("count") or 0),
                    "keys": {"project": t.sanitize(i.get("project")), "level": t.sanitize(i.get("level"))},
                    "substatus": i.get("substatus"), "sentry_issue": i.get("shortId"),
                    "culprit": t.sanitize(i.get("culprit")), "link": str(i.get("permalink") or "").split("?")[0]})
    return out


def _run_source(vault, src, store, by_name, now, dry):
    st = store.state["sources"].setdefault(src.name, {})
    start, end, moved = t.window(st.get("checkpoint"), now, src.kind)
    counters = {"new": 0, "updated": 0, "resolved": 0, "covered": 0, "truncated": 0}
    groups = _adx_groups(src, start, end, by_name, counters) if src.kind == "adx" else _sentry_groups(src, start, store)
    if src.kind == "adx":
        _cover(src, groups, by_name, store, counters)
    if dry:
        for g in groups:
            print(json.dumps({k: g[k] for k in ("source", "fingerprint", "kind", "service", "exception", "count")}))
        return start, end, moved, counters
    for g in groups:
        counters[store.upsert(g, now)] += 1
    if src.kind == "sentry":
        seen = {g["fingerprint"] for g in groups}
        stale = sorted((g for g in store.active(src.name) if g["key"].split("/", 1)[1] not in seen),
                       key=lambda g: g.get("last_seen") or "")[:MAX_STATUS]
        for g in stale:
            if sentry.issue_status(src.sentry_url, src.sentry_org, g["sentry_id"]) == "resolved":
                store.set_status(g["key"], "resolved", now)
                counters["resolved"] += 1
    counters["resolved"] += store.resolve_stale(src.name, now)
    st["checkpoint"], st["failures"] = end.isoformat(), 0
    return start, end, moved, counters


def main(argv: list, vault: Path, now: datetime | None = None) -> int:
    vault = Path(vault)
    now = now or datetime.now(timezone.utc)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    sources = t.load_sources(vault)
    by_name = {s.name: s for s in sources if s.enabled}
    if args.list:
        print("\n".join(by_name))
        return 0
    wanted = args.source or args.check
    if wanted and wanted not in by_name:
        print(f"telemetry_fetch: no enabled source named {wanted}")
        return 2
    if args.check:
        src = by_name[args.check]
        try:
            if src.kind == "adx":
                kusto.query(src.adx_cluster, src.adx_database, "print ok = 1", 1)
            else:
                sentry.project_ids(src.sentry_url, src.sentry_org, src.sentry_projects)
        except TelemetryError as exc:
            print(f"telemetry_fetch: {src.name}: {exc.reason}")
            return 1
        print(f"telemetry_fetch: {src.name}: ok")
        return 0
    (vault / "system").mkdir(exist_ok=True)
    with open(vault / LOCK, "w") as lock:
        deadline = time.monotonic() + LOCK_WAIT
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    print("telemetry_fetch: another fetch is running")
                    return 4
                time.sleep(1)
        store = Store(vault)
        if not args.dry_run:
            for w in store.load():
                _alert(vault, store, now, "state", w)
        rc = 0
        for src in [by_name[wanted]] if wanted else list(by_name.values()):
            line = {"started_at": now.isoformat(), "source": src.name}
            try:
                start, end, moved, counters = _run_source(vault, src, store, by_name, now, args.dry_run)
                line.update(window={"from": start.isoformat(), "to": end.isoformat()}, moved=moved, exit=0, **counters)
                if counters["truncated"]:
                    _alert(vault, store, now, f"{src.name}/truncated", f"{src.name}: {counters['truncated']} groups; only {MAX_GROUPS} kept")
            except TelemetryError as exc:
                rc = 1
                st = store.state["sources"].setdefault(src.name, {})
                st["failures"] = st.get("failures", 0) + 1
                line.update(exit=1, error=f"{exc.kind}: {exc.reason}")
                if exc.kind == "auth" or st["failures"] >= FAIL_ALERT:
                    _alert(vault, store, now, f"{src.name}/{exc.kind}", f"{src.name}: {exc.reason}")
            if not args.dry_run:
                _log(vault, now, line)
        if not args.dry_run:
            store.save()
        return rc
