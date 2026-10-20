"""One telemetry fetch over every enabled source (Plan 11 spec §3, §5)."""
import argparse
import copy
import fcntl
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import kusto, sentry, telemetry as t
from .http import TelemetryError
from .telemetry_store import Store

PRODUCTION = re.compile(r"prod", re.IGNORECASE)   # a source whose environment starts with prod (prod, production)
INCIDENT_MAX = 3
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]+")   # error text from outside: one alert, one line

LOCK = "system/telemetry.lock"
LOCK_WAIT = int(os.environ.get("TELEMETRY_LOCK_WAIT", "120"))
MAX_GROUPS = 500
MAX_LOOKUPS = 20
MAX_STATUS = 20
REMIND = timedelta(hours=4)   # a source still failing posts again this often (#293)
JITTER = timedelta(minutes=5)  # an hourly run a few seconds early still counts as four hours on


def _parser():
    p = argparse.ArgumentParser(prog="telemetry_fetch.py", add_help=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--source")
    g.add_argument("--check")
    g.add_argument("--list", action="store_true")
    g.add_argument("--sources", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


# The login each kind of source needs, for the Sources line and the smoke check's expired lines (connector health
# spec §2); --sources prints it beside each source's name.
CREDENTIALS = {
    "adx": ("Azure CLI", "az login on the server"),
    "sentry": ("Sentry token", "write a new token to ~/.config/foundry/sentry.token (mode 0600)"),
}


def _alert(vault: Path, store: Store, now: datetime, key: str, msg: str, tag: str = "telemetry") -> None:
    day = now.astimezone().strftime("%Y-%m-%d")
    if store.state["alerts"].get(key) == day:
        return
    store.state["alerts"][key] = day
    _append(vault, now, msg, tag)


def _append(vault: Path, now: datetime, msg: str, tag: str = "telemetry") -> None:
    path = vault / "system" / "logs" / f"alerts_{now.astimezone():%Y-%m-%d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"- {now.astimezone().strftime('%H:%M:%S')} [{tag}] {CONTROL.sub(' ', msg)}\n")


def _at(d: datetime) -> str:
    return d.astimezone().strftime("%Y-%m-%d %H:%M")


def _failing(vault: Path, now: datetime, src, st: dict, error: str) -> None:
    """A source failure reaches Slack (#293): one line when the source starts failing, then one every REMIND while it
    keeps failing. The per-source stamps live in the state file beside the checkpoint the failure holds."""
    try:
        since, posted = (datetime.fromisoformat(st[k]) for k in ("failing_since", "failure_posted"))
        if since.tzinfo is None or posted.tzinfo is None:
            raise ValueError("naive stamp")
    except (KeyError, TypeError, ValueError):   # no stamps yet, or a damaged one: the failure starts now
        st["failing_since"] = st["failure_posted"] = now.isoformat()
        _append(vault, now, f"{src.name}: failing since {_at(now)} ({error})", tag="telemetry_source")
        return
    if now - posted >= REMIND - JITTER:
        st["failure_posted"] = now.isoformat()
        _append(vault, now, f"{src.name}: still failing for {round((now - since).total_seconds() / 3600)} h, "
                f"since {_at(since)} ({error})", tag="telemetry_source")


def _push(vault: Path, store: Store, now: datetime, src, pushes: list) -> None:
    """An [incident] line, which Slack carries at the next tick, for each new or returning production error group of
    this run: at most INCIDENT_MAX, then one line counting the rest (incident push, #158 follow-up)."""
    for key, g, back in pushes[:INCIDENT_MAX]:
        what = "a resolved production error is back in" if back else "new production error in"
        rec = store.state["groups"][key]
        _alert(vault, store, now, f"incident/{key}",
               f"{src.name}: {what} {g['service']}: {str(g['exception'])[:120]} ({rec['count']} events) {rec['note']}",
               tag="incident")
    if len(pushes) > INCIDENT_MAX:
        _alert(vault, store, now, f"incident/{src.name}/more",
               f"{src.name}: and {len(pushes) - INCIDENT_MAX} more new production errors (see the brief)", tag="incident")


def _leaks(vault: Path, store: Store, now: datetime, src, leaks: list) -> None:
    """Secrets scan (#166): a [telemetry] line for each new group of this run whose raw log line held a credential
    shape, at most INCIDENT_MAX, then one line counting the rest. A group is new only once while its note exists, first
    run included (a credential in a backlog line is still a leak). The line names the group and the shape, never the
    value."""
    for key, shapes in leaks[:INCIDENT_MAX]:
        _alert(vault, store, now, f"secrets/{key}", f"{src.name}: a log line in "
               f"{store.state['groups'][key]['note']} holds a credential shape: {', '.join(shapes)}")
    if len(leaks) > INCIDENT_MAX:
        _alert(vault, store, now, f"secrets/{src.name}/more", f"{src.name}: and {len(leaks) - INCIDENT_MAX} more new "
               "groups hold a credential shape (see raw/telemetry/)")


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
                           "message": r.get("message"),
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
                    "exception": t.sanitize(i.get("type") or "error"),
                    "message": i.get("title"), "operation_id": str(i["id"]),
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
    # A source's first run finds every open group new: push none of them (turning a source on sends no backlog).
    push = PRODUCTION.match(src.environment or "") and st.get("checkpoint")
    pushes, leaks = [], []
    for g in groups:
        key = f"{src.name}/{g['fingerprint']}"
        back = (store.state["groups"].get(key) or {}).get("status") == "resolved"
        shapes = t.credential_shapes(g.get("message")) if src.secrets_scan else []   # the raw line, before upsert masks it
        result = store.upsert(g, now)
        counters[result] += 1
        if shapes and result == "new":
            leaks.append((key, shapes))
        if push and not g.get("covered") and (result == "new" or back):   # a covered group is its Sentry source's
            pushes.append((key, g, back))
    _push(vault, store, now, src, pushes)
    _leaks(vault, store, now, src, leaks)
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


def _classed(src, exc: TelemetryError) -> str:
    """The reason led by its class (connector health spec §2); a network failure names the host the smoke check
    reports as unreachable."""
    if exc.kind == "auth":
        return f"auth: {exc.reason}"
    if exc.kind == "transient" and exc.reason.startswith("network: "):
        host = urllib.parse.urlsplit(src.adx_cluster if src.kind == "adx" else src.sentry_url).hostname or "?"
        return f"network: {host} ({exc.reason.removeprefix('network: ')})"
    if exc.kind == "transient":
        return f"{'timeout' if 'timed out' in exc.reason else 'connector'}: {exc.reason}"
    return f"other: {exc.reason}"


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
    if args.sources:
        print("".join(f"{n}\t{CREDENTIALS.get(s.kind, ('', ''))[0]}\t{CREDENTIALS.get(s.kind, ('', ''))[1]}\n"
                      for n, s in by_name.items()), end="")
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
            print(f"telemetry_fetch: {src.name}: {_classed(src, exc)}")
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
                    st = store.state["sources"][src.name]
                    since = st.pop("failing_since", None)
                    st.pop("failure_posted", None)
                    if since and not dry:
                        try:
                            hours = f" after {round((now - datetime.fromisoformat(since)).total_seconds() / 3600)} h"
                        except (TypeError, ValueError):
                            hours = ""
                        _append(vault, now, f"{src.name}: recovered{hours}; backfilled {_at(start)} to {_at(end)}"
                                f"{' (capped)' if moved else ''}: {counters['new']} new, {counters['resolved']} resolved",
                                tag="telemetry_source")
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
                    if not dry:
                        _failing(vault, now, src, st, line["error"])
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
