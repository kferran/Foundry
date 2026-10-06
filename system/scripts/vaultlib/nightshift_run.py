"""The Nightshift runner (Nightshift spec §3, §7). Exit 0 ok or nothing due, 1 an item failed, 2 usage or invalid item, 4 locked."""
import argparse
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time as clock
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import nightshift_check as nc
from . import nightshift_deliver as nd
from . import nightshift_item as ni
from . import nightshift_report as rep
from . import nightshift_sched as ns
from . import nightshift_session as ss

LOCK = "system/nightshift.lock"
POLL = 30            # seconds between session checks
PR_FOR_LOCAL = ""    # tests: the pull-request kind used when template_remote is a local path
SELFTEST_PROMPT = ("Run exactly these two Bash commands, one at a time, and nothing else: "
                   "`curl -sS -m 5 -o /dev/null https://example.com; echo CURL_EXIT=$?` and "
                   "`cat ~/.ssh/* >/dev/null 2>&1; echo CAT_EXIT=$?`. Then stop.")


def _parser():
    p = argparse.ArgumentParser(prog="nightshift.py")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("tick")
    a = sub.add_parser("add")
    a.add_argument("--kind", choices=["plan", "research"], required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--partition", required=True)
    a.add_argument("--repo")
    a.add_argument("--base")
    a.add_argument("--pr-base", default="master")
    a.add_argument("--plan")
    a.add_argument("--tasks")
    a.add_argument("--verify", action="append", default=[])
    a.add_argument("--brief-file")
    a.add_argument("--output")
    a.add_argument("--host", action="append", default=[])
    g = a.add_mutually_exclusive_group()
    g.add_argument("--now", action="store_true")
    g.add_argument("--at", metavar="HH:MM")
    a.add_argument("--budget")
    a.add_argument("--model", default="sonnet")
    c = sub.add_parser("check")
    c.add_argument("note")
    sub.add_parser("list")
    x = sub.add_parser("cancel")
    x.add_argument("id")
    r = sub.add_parser("report")
    r.add_argument("date", nargs="?")
    sub.add_parser("selftest")
    return p


class Ctx:
    def __init__(self, vault: Path, now: datetime):
        self.vault, self.now = vault, now
        cfg = nc.config(vault)
        self.tz = ZoneInfo(str(cfg.get("timezone") or "UTC"))
        self.brief_time = str(cfg.get("brief_time") or "06:00")
        self.window = ns.parse_window(cfg.get("nightshift_window"))
        self.workspace = Path(str(cfg.get("nightshift_workspace") or "~/code/worktrees")).expanduser()
        self.local = now.astimezone(self.tz)
        self.date = ns.report_date(self.local, self.brief_time)
        self.alerts = {}

    def alert(self, key: str, msg: str) -> None:
        day = self.local.date().isoformat()
        seen = self.vault / rep.DIR / "alerts.json"
        data = json.loads(seen.read_text()) if seen.is_file() else {}
        if data.get(key) == day:
            return
        data[key] = day
        seen.parent.mkdir(parents=True, exist_ok=True)
        seen.write_text(json.dumps(data))
        path = self.vault / "system" / "logs" / f"alerts_{day}.md"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"- {self.local.strftime('%H:%M:%S')} [nightshift] {msg}\n")

    def log(self, line: dict) -> None:
        path = self.vault / "system" / "logs" / f"nightshift-{self.now.strftime('%Y-%m')}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": self.now.isoformat(), **line}, sort_keys=True) + "\n")


# --- health and self-test ---------------------------------------------------------------------------

def _ok(cmd) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"FAILED: {exc.__class__.__name__}"
    return "ok" if r.returncode == 0 else f"FAILED: {(r.stderr or r.stdout).strip().splitlines()[-1:] or ['exit ' + str(r.returncode)]}"


def selftest(vault) -> tuple:
    """(passed, reason). Runs the plan profile's sandbox with two commands that must fail."""
    with __import__("tempfile").TemporaryDirectory() as tmp:
        settings = Path(tmp) / "settings.json"
        settings.write_text(json.dumps(ss.profile(vault, "plan", [])))
        stream = Path(tmp) / "stream.jsonl"
        cmd = ss.command("plan", SELFTEST_PROMPT, settings, "haiku", str(uuid.uuid4()), [])
        with open(stream, "w") as out:
            try:
                subprocess.run(cmd, cwd=tmp, stdout=out, stderr=subprocess.DEVNULL, timeout=300)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return False, f"self-test session failed: {exc.__class__.__name__}"
        s = ss.parse_stream(stream)
    problem = ss.init_problem(s["init"], "plan")
    if problem:
        return False, f"profile: {problem}"
    text = " ".join(s["tool_results"])
    if "CURL_EXIT=0" in text:
        return False, "curl reached a host outside the allowlist"
    if "CAT_EXIT=0" in text:
        return False, "a credential file was readable"
    if "CURL_EXIT=" not in text or "CAT_EXIT=" not in text:
        return False, "the self-test commands did not run"
    return True, ""


def health(vault, now, entries) -> dict:
    h = {"claude": _ok([ss.claude_bin(), "auth", "status"]), "gh": _ok(["gh", "auth", "status"])}
    ok, why = selftest(vault)
    h["sandbox"] = "ok" if ok else f"FAILED: {why}"
    return h


# --- one item ------------------------------------------------------------------------------------------

def _clone(ctx: Ctx, fm: dict) -> Path:
    src = nc.source(ctx.vault, fm["repo"])
    sha = nc.git(src, "rev-parse", f"{fm['base']}^{{commit}}").stdout.strip()
    clone = ctx.workspace / f"nightshift-{fm['id']}"
    if clone.exists():
        return clone
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(src), str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-b", f"nightshift/{fm['id']}", sha], check=True)
    with open(clone / ".git" / "info" / "exclude", "a") as f:
        f.write("\n.nightshift/\n")
    return clone


def _research_dir(ctx: Ctx, fm: dict) -> Path:
    d = ctx.workspace / f"nightshift-{fm['id']}"
    (d / "out").mkdir(parents=True, exist_ok=True)
    return d


def _stop(proc, sig) -> None:
    """Signal the session's process group; escalate to SIGKILL after 60 s. A group that already exited is fine."""
    try:
        os.killpg(proc.pid, sig)
        proc.wait(timeout=60)
    except ProcessLookupError:
        pass
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait()


def _run_session(ctx: Ctx, path: Path, fm: dict, body: str, cwd: Path, idir: Path, resume: bool) -> dict:
    kind = fm["kind"]
    cb = nc.codebase(ctx.vault, fm.get("repo")) or {}
    hosts = list(cb.get("nightshift_hosts") or [])
    web = list(fm.get("hosts") or []) if kind == "research" else []
    settings = idir / "settings.json"
    settings.write_text(json.dumps(ss.profile(ctx.vault, kind, hosts, web)))
    plugins = [p for p in [ss.superpowers_dir()] if p] + [Path(str(p)).expanduser() for p in cb.get("nightshift_plugins") or []]
    add_dirs = [ctx.vault / "wiki" / fm["partition"]] if kind == "research" else []
    prompt = (ss.plan_prompt(fm) if kind == "plan" else ss.research_prompt(fm, body))
    if resume:
        prompt = "Continue where you stopped; read .nightshift/progress.md (or out/) first. " + prompt
    (idir / "prompt.md").write_text(prompt)
    sid = fm.get("session_id") or str(uuid.uuid4())
    ni.update(path, session_id=sid)
    cmd = ss.command(kind, prompt, settings, fm.get("model") or "sonnet", sid, plugins, add_dirs, resume=resume)
    budget = ni.budget_seconds(fm.get("budget") or ("4h" if kind == "plan" else "1h"))
    stream = idir / "stream.jsonl"
    with open(stream, "a") as out, open(idir / "run.log", "a") as err:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=err, start_new_session=True)
        started, checked = clock.monotonic(), False
        while proc.poll() is None:
            clock.sleep(min(POLL, 1 if not checked else POLL))
            if not checked and stream.stat().st_size:
                problem = ss.init_problem(ss.parse_stream(stream)["init"], kind)
                checked = True
                if problem:
                    _stop(proc, signal.SIGKILL)
                    return {"outcome": "failed", "reason": "profile", "detail": problem}
            if ni.load(path)[0].get("state") == "cancelled":
                _stop(proc, signal.SIGTERM)
                return {"outcome": "cancelled", "reason": "cancelled by user"}
            if clock.monotonic() - started > budget:
                _stop(proc, signal.SIGTERM)
                return {"outcome": "failed", "reason": "budget"}
    s = ss.parse_stream(stream)
    problem = ss.init_problem(s["init"], kind)
    if problem:
        return {"outcome": "failed", "reason": "profile", "detail": problem}
    if s["limited"]:
        return {"outcome": "waiting_reset", "reset_at": ss.reset_epoch(s["limited"])}
    return {"outcome": "finished", "usage": s["usage"]}


def _read_result(p: Path) -> dict | None:
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
        return r if isinstance(r, dict) and r.get("status") in ("done", "blocked") else None
    except (OSError, json.JSONDecodeError):
        return None


def _deliver_plan(ctx: Ctx, fm: dict, clone: Path, idir: Path, before: dict) -> dict:
    res = _read_result(clone / ".nightshift" / "result.json")
    if res is None:
        return {"state": "failed", "reason": "no result"}
    if res["status"] == "blocked":
        return {"state": "blocked", "reason": "session", "needs": [f"Answer: {q}" for q in res.get("questions") or []]}
    src = nc.source(ctx.vault, fm["repo"])
    if nd.protected_refs(src) != before["src"] or nd.protected_refs(ctx.vault) != before["vault"] \
            or nd.code_status(ctx.vault) != before["code"]:
        ctx.alert(f"containment/{fm['id']}", f"{fm['id']}: a protected branch or vault code changed during the run")
        return {"state": "failed", "reason": "containment"}
    branch = f"nightshift/{fm['id']}"
    if nc.git(clone, "rev-parse", branch).stdout.strip() == nc.git(src, "rev-parse", f"{fm['base']}^{{commit}}").stdout.strip():
        return {"state": "blocked", "reason": "no commits"}
    ok, out = nd.run_verify(clone, fm.get("verify") or [], idir / "verify.log")
    if not ok:
        return {"state": "blocked", "reason": "verify", "needs": [f"Fix the failing check: {out.splitlines()[0]}"]}
    url, pr = nd.push_target(ctx.vault, fm)
    pr = pr or PR_FOR_LOCAL
    ok, push_log = nd.push(ctx.workspace / "nightshift-runner.git", clone, branch, url)
    (idir / "push.log").write_text(push_log)
    if not ok:
        return {"state": "failed", "reason": "delivery", "needs": [f"Push failed for {branch}: see {idir}/push.log"]}
    body = idir / "pr_body.md"
    body.write_text(f"{res.get('pr_body') or res.get('summary') or ''}\n\nQueued as Nightshift item `{fm['id']}`.\n")
    ok, link = nd.open_pr(pr, branch, fm.get("pr_base") or "master", res.get("pr_title") or fm["id"], body, push_log)
    if not ok:
        return {"state": "failed", "reason": "delivery", "needs": [f"Open the pull request for {branch}: {link}"]}
    verb = "Review and merge" if pr.startswith("github:") else "Open the pull request"
    shutil.rmtree(clone, ignore_errors=True)
    return {"state": "done", "result": link, "needs": [f"{verb}: {link}"], "notes": res.get("summary", "")}


def _deliver_research(ctx: Ctx, fm: dict, d: Path) -> dict:
    res = _read_result(d / "out" / "result.json")
    if res is None:
        return {"state": "failed", "reason": "no result"}
    if res["status"] == "blocked":
        return {"state": "blocked", "reason": "session", "needs": [f"Answer: {q}" for q in res.get("questions") or []]}
    findings = d / "out" / Path(fm["output"]).name
    if not findings.is_file():
        return {"state": "failed", "reason": "no result"}
    ok, detail = nd.publish_research(ctx.vault, fm, findings)
    if not ok:
        return {"state": "failed", "reason": "delivery", "needs": [f"Findings rejected by the publish gate: {detail}"]}
    shutil.rmtree(d, ignore_errors=True)
    return {"state": "done", "result": f"[[{Path(fm['output']).stem}]]", "needs": [], "notes": res.get("summary", "")}


def run_item(ctx: Ctx, path: Path, fm: dict, body: str) -> int:
    idir = rep.item_dir(ctx.vault, fm["id"])
    idir.mkdir(parents=True, exist_ok=True)
    resume = fm.get("state") in ("waiting_reset", "running")
    attempts = int(fm.get("attempts") or 0) + 1
    ni.update(path, state="running", started_at=fm.get("started_at") or ctx.now.isoformat(), attempts=str(attempts),
              reset_at=None)
    before = {}
    if fm["kind"] == "plan":
        cwd = _clone(ctx, fm)
        before = {"src": nd.protected_refs(nc.source(ctx.vault, fm["repo"])), "vault": nd.protected_refs(ctx.vault),
                  "code": nd.code_status(ctx.vault)}
    else:
        cwd = _research_dir(ctx, fm)
    run = _run_session(ctx, path, fm, body, cwd, idir, resume)
    if run.get("usage"):
        hfile = ctx.vault / rep.DIR / f"health-{ctx.date}.json"
        h = json.loads(hfile.read_text()) if hfile.is_file() else {}
        u = run["usage"]
        h["usage7"] = u.get("seven_day")
        h["usage"] = f"5h {round((u.get('five_hour') or 0) * 100)}% / 7d {round((u.get('seven_day') or 0) * 100)}%"
        rep.write_health(ctx.vault, ctx.date, h)
    if run["outcome"] == "waiting_reset":
        reset = datetime.fromtimestamp(run["reset_at"], tz=timezone.utc).astimezone(ctx.tz)
        ni.update(path, state="waiting_reset", reset_at=reset.isoformat())
        ctx.log({"item": fm["id"], "state": "waiting_reset", "reset_at": reset.isoformat()})
        return 0
    if run["outcome"] == "cancelled":
        out = {"state": "cancelled", "reason": "cancelled by user", "needs": []}
    elif run["outcome"] == "failed":
        out = {"state": "failed", "reason": run["reason"], "notes": run.get("detail", "")}
        if run["reason"] == "profile":
            ctx.alert("profile", f"{fm['id']}: session profile mismatch ({run.get('detail')})")
    elif fm["kind"] == "plan":
        out = _deliver_plan(ctx, fm, cwd, idir, before)
    else:
        out = _deliver_research(ctx, fm, cwd)
    if out["state"] in ("failed", "blocked") and not out.get("needs"):
        tail = (idir / "run.log").read_text(errors="replace").splitlines()[-3:] if (idir / "run.log").is_file() else []
        out["needs"] = [f"{fm['id']} {out['state']} ({out.get('reason')}); work kept in {cwd}" + (f"; log: {' | '.join(tail)}" if tail else "")]
    ni.update(path, state=out["state"], reason=out.get("reason") or None, result=out.get("result") or None,
              finished_at=ctx.now.isoformat())
    rep.write_outcome(ctx.vault, {"id": fm["id"], "kind": fm["kind"], "state": out["state"], "result": out.get("result", ""),
                                  "reason": out.get("reason", ""), "started_at": fm.get("started_at") or ctx.now.isoformat(),
                                  "finished_at": ctx.now.isoformat(), "report_date": ctx.date,
                                  "needs": out.get("needs", []), "notes": out.get("notes", "")})
    rep.write(ctx.vault, ctx.date)
    ctx.log({"item": fm["id"], "state": out["state"], "reason": out.get("reason", "")})
    return 0 if out["state"] in ("done", "cancelled") else 1


# --- tick and CLI --------------------------------------------------------------------------------------

def _reconcile(ctx: Ctx) -> None:
    for path, fm, _ in ni.items(ctx.vault):
        if fm.get("state") == "running" and int(fm.get("attempts") or 0) >= 3:
            ni.update(path, state="failed", reason="no result", finished_at=ctx.now.isoformat())


def tick(ctx: Ctx) -> int:
    _reconcile(ctx)
    entries = [(p, fm, b) for p, fm, b in ni.items(ctx.vault)]
    hfile = ctx.vault / rep.DIR / f"health-{ctx.date}.json"
    usage7 = None
    candidates = [e for e in entries if ns.due(e[1], ctx.local, ctx.window, float("inf"), 0)[0]
                  or e[1].get("state") == "running"]
    if not candidates:
        return 0
    if not hfile.is_file():
        h = health(ctx.vault, ctx.now, entries)
        h["last_tick"] = ctx.local.strftime("%H:%M")
        rep.write_health(ctx.vault, ctx.date, h)
    h = json.loads(hfile.read_text())
    h["last_tick"] = ctx.local.strftime("%H:%M")
    rep.write_health(ctx.vault, ctx.date, h)
    if str(h.get("sandbox", "")).startswith("FAILED"):
        ctx.alert("sandbox", f"sandbox self-test failed: {h['sandbox']}; no items run")
        rep.write(ctx.vault, ctx.date)
        return 1
    usage7 = h.get("usage7")
    idle = ns.idle_seconds(ctx.vault, ctx.now)
    running = [e for e in entries if e[1].get("state") == "running"]
    chosen = running[0] if running else ns.pick(entries, ctx.local, ctx.window, idle, usage7)
    if not chosen:
        return 0
    path, fm, body = chosen
    claim = rep.item_dir(ctx.vault, fm["id"]) / f"claim-{int(fm.get('attempts') or 0) + 1}"
    try:
        claim.parent.mkdir(parents=True, exist_ok=True)
        claim.mkdir()
    except FileExistsError:
        return 0
    return run_item(ctx, path, fm, body)


def _add(ctx: Ctx, a) -> int:
    item_id = ni.new_id(a.title, ctx.local)
    fm = {"type": "nightshift_item", "id": item_id, "partition": a.partition, "kind": a.kind, "state": "queued",
          "queued_at": ctx.local.isoformat(), "start": "now" if a.now else ("at" if a.at else "window"),
          "budget": a.budget or ("4h" if a.kind == "plan" else "1h"), "model": a.model}
    if a.at:
        hh, mm = (int(x) for x in a.at.split(":"))
        start = ctx.local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        fm["start_at"] = (start if start > ctx.local else start + timedelta(days=1)).isoformat()
    if a.kind == "plan":
        fm.update(repo=a.repo, base=a.base, pr_base=a.pr_base, plan=a.plan, tasks=a.tasks, verify=a.verify)
        body = ""
    else:
        fm.update(output=a.output, hosts=a.host)
        body = Path(a.brief_file).read_text(encoding="utf-8") if a.brief_file else ""
    fm = {k: v for k, v in fm.items() if v not in (None, "", [])} | ({"verify": a.verify} if a.kind == "plan" else {})
    errs = nc.check(ctx.vault, fm, body)
    if errs:
        for e in errs:
            print(f"not ready: {e}")
        return 2
    path = ni.note_path(ctx.vault, a.partition, item_id)
    if path.exists():
        print(f"not ready: an item named {item_id} already exists")
        return 2
    ni.save(path, fm, body)
    print(f"queued {item_id} ({fm['start']}) -> {path.relative_to(ctx.vault)}")
    return 0


def main(argv: list, vault: Path, now: datetime | None = None) -> int:
    vault, now = Path(vault), now or datetime.now(timezone.utc)
    try:
        a = _parser().parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    ctx = Ctx(vault, now)
    cmd = a.cmd or "tick"
    if cmd == "add":
        return _add(ctx, a)
    if cmd == "check":
        fm, body = ni.load(a.note)
        errs = nc.check(vault, fm, body)
        print("\n".join(f"not ready: {e}" for e in errs) or "ready")
        return 2 if errs else 0
    if cmd == "list":
        for p, fm, _ in ni.items(vault):
            print(f"{fm.get('id')}  {fm.get('kind')}  {fm.get('state')}  {fm.get('start')}  {fm.get('result') or fm.get('reason') or ''}")
        return 0
    if cmd == "cancel":
        hits = [p for p, fm, _ in ni.items(vault) if fm.get("id") == a.id]
        if not hits:
            print(f"no item {a.id}")
            return 2
        ni.update(hits[0], state="cancelled")
        return 0
    if cmd == "report":
        print(rep.write(vault, a.date or ctx.date).read_text())
        return 0
    if cmd == "selftest":
        ok, why = selftest(vault)
        print("sandbox ok" if ok else f"sandbox FAILED: {why}")
        return 0 if ok else 1
    (vault / "system").mkdir(exist_ok=True)
    with open(vault / LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 4
        os.set_inheritable(lock.fileno(), False)
        return tick(ctx)
