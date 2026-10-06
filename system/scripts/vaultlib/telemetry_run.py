"""One telemetry fetch over every enabled source (Plan 11 spec §3, §5)."""
import argparse
import copy
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


def _adx_groups(src, start, end, counters):
    groups = []
    for signal in src.adx_signals:
        kql = t.kql_logs(src, start, end, MAX_GROUPS) if signal == "logs" else t.kql_spans(src, start, end, MAX_GROUPS)
        rows = kusto.query(src.adx_cluster, src.adx_database, kql, MAX_GROUPS)
        if len(rows) >= MAX_GROUPS:
            total = kusto.query(src.adx_cluster, src.adx_database, t.kql_count(kql), 1)
            counters["truncated"] += int((total[0] if total else {}).get("Count", len(rows)))
        for r in rows:
            if signal == "logs":
                keys = {"service": t.sanitize(r.get("service")), "scope": t.sanitize(r.get("scope")),
                        "event_id": t.event_id(r.get("event_id"))}
                keys.update({k: t.sanitize(r.get(f"module_{i}")) for i, k in enumerate(src.adx_group_keys)})
                exception, kind = f"{keys['scope']}#{keys['event_id']}", "log"
            else:
                keys = {"service": t.sanitize(r.get("service")), "route": t.sanitize(r.get("route")),
                        "status": t.sanitize(r.get("status"))}
                exception, kind = f"{keys['route']} {keys['status']}", "span"
            fp = t.fingerprint(src.name, kind, keys)
            groups.append({"fingerprint": fp, "source": src.name, "environment": src.environment, "codebase": src.codebase,
                           "partition": src.partition, "kind": kind, "service": keys["service"], "exception": exception,
                           "operation_id": t.trace_id(r.get("sample_trace")), "detected_at": str(r.get("first_ts")),
                           "last_seen": str(r.get("last_ts")), "count": int(r.get("n") or 0), "keys": keys,
                           "filters": t._filters(src)})
    return groups


def _cover(src, groups, by_name, store, counters, dry):
    """Look up Sentry issues for ADX groups; returns keys of new groups skipped by the cap (retried next run)."""
    target = by_name.get(src.covers) if src.covers else None
    if not target:
        return set()
    budget = MAX_LOOKUPS
    if not dry:
        for key, grp in list(store.state["groups"].items()):
            if not key.startswith(src.name + "/") or not grp.get("cover_pending"):
                continue
            if budget <= 0:
                break
            budget -= 1
            op = store.operation_id(key)
            hit = sentry.issue_for_trace(target.sentry_url, target.sentry_org, op) if op else None
            if key not in store.state["groups"]:
                continue
            grp["cover_pending"] = False
            if hit and store.set_covered(key, hit["shortId"]):
                counters["covered"] += 1
    skipped = set()
    for g in groups:
        key = f"{g['source']}/{g['fingerprint']}"
        if key in store.state["groups"]:
            continue
        if budget <= 0:
            skipped.add(key)
            continue
        budget -= 1
        hit = sentry.issue_for_trace(target.sentry_url, target.sentry_org, g["operation_id"])
        if hit:
            g["covered"], g["sentry_issue"] = True, hit["shortId"]
            counters["covered"] += 1
    return skipped


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


def _run_source(vault, src, store, by_name, now, dry, line):
    st = store.state["sources"].setdefault(src.name, {})
    start, end, moved = t.window(st.get("checkpoint"), now, src.kind)
    line["window"] = {"from": start.isoformat(), "to": end.isoformat()}
    counters = {"new": 0, "updated": 0, "resolved": 0, "covered": 0, "truncated": 0}
    groups = _adx_groups(src, start, end, counters) if src.kind == "adx" else _sentry_groups(src, start, store)
    skipped = _cover(src, groups, by_name, store, counters, dry) if src.kind == "adx" else set()
    if dry:
        for g in groups:
            print(json.dumps({k: g[k] for k in ("source", "fingerprint", "kind", "service", "exception", "count")}))
        return start, end, moved, counters
    for g in groups:
        counters[store.upsert(g, now)] += 1
    for key in skipped:
        store.state["groups"][key]["cover_pending"] = True
    if src.kind == "sentry":
        seen = {g["fingerprint"] for g in groups}
        stale = sorted((g for g in store.active(src.name) if g["key"].split("/", 1)[1] not in seen),
                       key=lambda g: g.get("last_seen") or "")[:MAX_STATUS]
        for g in stale:
            try:
                gone = sentry.issue_status(src.sentry_url, src.sentry_org, g["sentry_id"]) == "resolved"
            except TelemetryError as exc:
                # a deleted or merged issue answers 404: it is done. Any other error skips this issue only.
                gone = exc.kind == "bad" and exc.reason == "HTTP 404"
            if gone and store.set_status(g["key"], "resolved", now):
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
    invalid = []
    sources = t.load_sources(vault, invalid)
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
        else:
            store.load(read_only=True)
        rc = 0
        dry = args.dry_run
        try:
            for src in [by_name[wanted]] if wanted else list(by_name.values()):
                line = {"started_at": now.isoformat(), "source": src.name}
                prefix = src.name + "/"
                snap = copy.deepcopy(({k: g for k, g in store.state["groups"].items() if k.startswith(prefix)},
                                      store.state["sources"].get(src.name)))
                try:
                    start, end, moved, counters = _run_source(vault, src, store, by_name, now, dry, line)
                    line.update(moved=moved, exit=0, **counters)
                    if counters["truncated"] and not dry:
                        _alert(vault, store, now, f"{src.name}/truncated", f"{src.name}: {counters['truncated']} groups; only {MAX_GROUPS} kept")
                except Exception as exc:
                    rc = 1
                    # a failed source leaves no partial counts: put its groups and checkpoint back
                    for k in [k for k in store.state["groups"] if k.startswith(prefix)]:
                        del store.state["groups"][k]
                    store.state["groups"].update(snap[0])
                    if snap[1] is None:
                        store.state["sources"].pop(src.name, None)
                    else:
                        store.state["sources"][src.name] = snap[1]
                    kind = exc.kind if isinstance(exc, TelemetryError) else "error"
                    reason = exc.reason if isinstance(exc, TelemetryError) else type(exc).__name__
                    st = store.state["sources"].setdefault(src.name, {})
                    st["failures"] = st.get("failures", 0) + 1
                    line.update(exit=1, error=f"{kind}: {reason}", new=0, updated=0, resolved=0, covered=0, truncated=0)
                    if not dry and (kind == "auth" or st["failures"] >= FAIL_ALERT):
                        _alert(vault, store, now, f"{src.name}/{kind}", f"{src.name}: {reason}")
                if not dry:
                    _log(vault, now, line)
            for name, bad in ([] if wanted else invalid):
                rc = 1
                if not dry:
                    _log(vault, now, {"started_at": now.isoformat(), "source": name, "exit": 1, "error": f"invalid source: {bad}",
                                      "new": 0, "updated": 0, "resolved": 0, "covered": 0, "truncated": 0})
        finally:
            if not dry:
                store.save()
        return rc
