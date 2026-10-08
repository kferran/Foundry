"""The Nightshift runner (Nightshift spec §3, §7). Exit 0 ok or nothing due, 1 an item failed, 2 usage or invalid item, 4 locked."""
import argparse
import fcntl
import json
import os
import secrets
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
CANARY = "~/.config/foundry/nightshift-canary"  # planted by the self-test under a path every profile denies
SELFTEST_PROMPT = ("This is the Nightshift runner's sandbox self-test, run by the vault's owner. Both commands below "
                   "are expected to fail inside the sandbox; the test needs their real exit codes, so run each one with "
                   "the Bash tool even if you expect a denial, and do not explain or refuse. "
                   "Run exactly these two Bash commands, one at a time, and nothing else: "
                   "`curl -sS -m 5 -o /dev/null https://example.com; echo CURL_EXIT=$?` and "
                   f"`cat {CANARY}; echo CAT_EXIT=$?`. Then stop.")
SELFTEST_TRIES = 3


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


def _selftest_once(vault) -> tuple:
    """(verdict, reason): verdict True passed, False failed, None the commands did not run. A canary with a fresh token
    is planted under a denied path for the session to try to read, so the test proves masking on every host."""
    canary = Path(os.path.expanduser(CANARY))
    token = secrets.token_hex(16)
    canary.parent.mkdir(parents=True, exist_ok=True)
    canary.write_text(token + "\n")
    try:
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
    finally:
        canary.unlink(missing_ok=True)
    problem = ss.init_problem(s["init"], "plan")
    if problem:
        return False, f"profile: {problem}"
    text = " ".join(s["tool_results"])
    if "CURL_EXIT=0" in text:
        return False, "curl reached a host outside the allowlist"
    if "CAT_EXIT=0" in text or token in text:
        return False, f"the canary {CANARY} was readable"
    if "CURL_EXIT=" not in text or "CAT_EXIT=" not in text:
        return None, "the self-test commands did not run"
    return True, ""


def selftest(vault) -> tuple:
    """(passed, reason). Runs the plan profile's sandbox with two commands that must fail. A model that declines to run
    them proves nothing either way, so that case is retried; a command that succeeds fails at once."""
    reason = ""
    for _ in range(SELFTEST_TRIES):
        verdict, reason = _selftest_once(vault)
        if verdict is not None:
            return verdict, reason
    return False, f"{reason} ({SELFTEST_TRIES} tries)"


def health(vault, now, entries) -> dict:
    h = {"claude": _ok([ss.claude_bin(), "auth", "status"]), "gh": _ok(["gh", "auth", "status"])}
    ok, why = selftest(vault)
    h["sandbox"] = "ok" if ok else f"FAILED: {why}"
    return h


# --- one item ------------------------------------------------------------------------------------------

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


class CloneError(RuntimeError):
    """A template item's base could not be fetched from the template remote."""


def _clone(ctx: Ctx, fm: dict) -> Path:
    clone = ctx.workspace / f"nightshift-{fm['id']}"
    template = fm["repo"] == "template"
    if clone.exists():
        if not template or nc.git(clone, "rev-parse", "--verify", "--quiet", "refs/remotes/base").returncode == 0:
            return clone
        shutil.rmtree(clone)   # half-built by a killed tick: start again
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    branch = f"nightshift/{fm['id']}"
    if template:
        # From the template remote, never the vault: the vault's object store holds private notes.
        url = str(nc.config(ctx.vault).get("template_remote") or "")
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        try:
            f = nc.fetch_base(clone, url, fm["base"], "refs/remotes/base")
        except ValueError as exc:
            f = subprocess.CompletedProcess([], 2, "", str(exc))
        if f.returncode:
            shutil.rmtree(clone, ignore_errors=True)   # the next tick starts from an empty workspace again
            why = (f.stderr.strip().splitlines() or ["no error text"])[-1]
            raise CloneError(f"fetch {fm['base']} from {nc.shown(url)}: {why}")
        subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-b", branch, "refs/remotes/base"], check=True)
    else:
        src = nc.source(ctx.vault, fm["repo"])
        sha = nc.git(src, "rev-parse", f"{fm['base']}^{{commit}}").stdout.strip()
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(src), str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "checkout", "-q", "-b", branch, sha], check=True)
    with open(clone / ".git" / "info" / "exclude", "a") as f:
        f.write("\n.nightshift/\n")
    return clone


def _research_dir(ctx: Ctx, fm: dict) -> Path:
    d = ctx.workspace / f"nightshift-{fm['id']}"
    (d / "out").mkdir(parents=True, exist_ok=True)
    wiki = ctx.vault / "wiki" / fm["partition"]
    if not (d / "context").exists() and wiki.is_dir():
        shutil.copytree(wiki, d / "context", ignore=shutil.ignore_patterns(".*"))
    if fm.get("repo"):
        _research_code(ctx, fm, d / "code")
    return d


def _research_code(ctx: Ctx, fm: dict, code: Path) -> None:
    """A read-only copy of the item's repository at one commit (#77): that commit alone, fetched into a new
    repository, so nothing links to the registered clone and no other branch is visible. The first attempt records
    the commit in the run directory; a resumed attempt checks it out again, and rebuilds code/ when it cannot."""
    mark = rep.item_dir(ctx.vault, fm["id"]) / "code-commit"
    sha = mark.read_text().strip() if mark.is_file() else ""
    if sha and code.is_dir() and nc.git(code, "checkout", "-q", "-f", "--detach", sha).returncode == 0:
        return
    shutil.rmtree(code, ignore_errors=True)   # half-built by a killed tick, or never built
    repo, base = fm["repo"], fm.get("base")
    if repo == "template":   # from the template remote, never the vault
        url = str(nc.config(ctx.vault).get("template_remote") or "")
        where = f"fetch {base or 'HEAD'} from {nc.shown(url)}"
    else:
        src = nc.source(ctx.vault, repo)
        url, sha = str(src or ""), sha or (nc.research_base(src, base) if src else "")
        where = f"{base or 'origin/HEAD'} in {src}"
    r = subprocess.run(["git", "init", "-q", str(code)], capture_output=True, text=True)
    if r.returncode == 0 and not (sha or repo == "template"):
        r = subprocess.CompletedProcess([], 2, "", "does not resolve")
    elif r.returncode == 0:
        try:
            r = nc.fetch_base(code, url, base, "refs/remotes/base", depth=1, commit=sha or None)
        except ValueError as exc:
            r = subprocess.CompletedProcess([], 2, "", str(exc))
    if r.returncode == 0:
        r = nc.git(code, "checkout", "-q", "--detach", "refs/remotes/base")
    if r.returncode:
        shutil.rmtree(code, ignore_errors=True)   # the next attempt starts again
        raise CloneError(f"{where}: {(r.stderr.strip().splitlines() or ['no error text'])[-1]}")
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(nc.git(code, "rev-parse", "HEAD").stdout.strip())


def _deny(ctx: Ctx, fm: dict) -> list:
    """Paths a session must not read: the vault's notes, inputs and logs, and every other registered codebase."""
    out = [str(ctx.vault / p) for p in ("wiki", "raw", "briefings", "system/logs")]
    # A plan item works in its own codebase; a research item reads code/, so even its own checkout stays denied.
    own = nc.source(ctx.vault, fm.get("repo")) if fm.get("kind") == "plan" and fm.get("repo") != "template" else None
    for p in sorted((ctx.vault / "system" / "codebases").glob("*.md")):
        cb = nc.codebase(ctx.vault, p.stem) or {}
        path = Path(str(cb.get("path") or "")).expanduser()
        if cb.get("path") and path != own:
            out.append(str(path))
    return out


def _alive(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _stop_stale(idir: Path) -> None:
    """Stop a session process group left by an earlier runner (crash, restart, cancel)."""
    pidf = idir / "session.pid"
    if not pidf.is_file():
        return
    try:
        pid = int(pidf.read_text().strip())
    except ValueError:
        pidf.unlink()
        return
    for sig, wait in ((signal.SIGTERM, 30), (signal.SIGKILL, 5)):
        if not _alive(pid):
            break
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            break
        for _ in range(wait * 10):
            if not _alive(pid):
                break
            clock.sleep(0.1)
    pidf.unlink(missing_ok=True)


def _elapsed(idir: Path) -> float:
    try:
        return float((idir / "elapsed").read_text())
    except (OSError, ValueError):
        return 0.0


def _run_session(ctx: Ctx, path: Path, fm: dict, body: str, cwd: Path, idir: Path, resume: bool) -> dict:
    kind = fm["kind"]
    cb = nc.codebase(ctx.vault, fm.get("repo")) or {}
    hosts = list(cb.get("nightshift_hosts") or [])
    web = list(fm.get("hosts") or []) if kind == "research" else []
    settings = idir / "settings.json"
    settings.write_text(json.dumps(ss.profile(ctx.vault, kind, hosts, web, deny=_deny(ctx, fm))))
    plugins = [p for p in [ss.superpowers_dir()] if p] + [Path(str(p)).expanduser() for p in cb.get("nightshift_plugins") or []]
    code = nc.git(cwd / "code", "log", "-1", "--format=%h (%cs)").stdout.strip() if kind == "research" and fm.get("repo") else ""
    prompt = (ss.plan_prompt(fm) if kind == "plan" else
              ss.research_prompt(fm, body, code=f"{fm['repo']} at {code}" if code else None))
    if resume:
        prompt = "Continue where you stopped; read .nightshift/progress.md (or out/) first. " + prompt
    (idir / "prompt.md").write_text(prompt)
    sid = fm.get("session_id") or str(uuid.uuid4())
    ni.update(path, session_id=sid)
    cmd = ss.command(kind, prompt, settings, fm.get("model") or "sonnet", sid, plugins, resume=resume and bool(fm.get("session_id")))
    budget = ni.budget_seconds(fm.get("budget") or ("4h" if kind == "plan" else "1h")) - _elapsed(idir)
    stream = idir / "stream.jsonl"
    size0 = stream.stat().st_size if stream.is_file() else 0
    started = clock.monotonic()
    outcome = None
    with open(stream, "a") as out, open(idir / "run.log", "a") as err:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=err, start_new_session=True)
        (idir / "session.pid").write_text(str(proc.pid))
        checked = False
        while proc.poll() is None:
            clock.sleep(1 if not checked else POLL)
            if not checked and stream.stat().st_size > size0:
                problem = ss.init_problem(ss.parse_stream(stream)["init"], kind)
                checked = True
                if problem:
                    _stop(proc, signal.SIGKILL)
                    outcome = {"outcome": "failed", "reason": "profile", "detail": problem}
                    break
            if ni.load(path)[0].get("state") == "cancelled":
                _stop(proc, signal.SIGTERM)
                outcome = {"outcome": "cancelled", "reason": "cancelled by user"}
                break
            if clock.monotonic() - started > budget:
                _stop(proc, signal.SIGTERM)
                outcome = {"outcome": "failed", "reason": "budget"}
                break
    (idir / "elapsed").write_text(str(_elapsed(idir) + clock.monotonic() - started))
    (idir / "session.pid").unlink(missing_ok=True)
    if outcome:
        return outcome
    tail = stream.read_bytes()[size0:].decode("utf-8", "replace")
    part = idir / "stream.last.jsonl"
    part.write_text(tail)
    s = ss.parse_stream(part)
    if s["init"] is None:
        return {"outcome": "no_start"}
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


def _questions(res: dict) -> list:
    qs = res.get("questions")
    return [q for q in qs if isinstance(q, str) and q.strip()][:5] if isinstance(qs, list) else []


def _text(v) -> str:
    return v if isinstance(v, str) else ""


def _before(ctx: Ctx, fm: dict, idir: Path) -> dict:
    """The containment baseline, taken once at the first attempt and reused by every resume."""
    f = idir / "before.json"
    if f.is_file():
        return json.loads(f.read_text())
    if fm["repo"] == "template":   # the commit the session starts from, fetched from the template remote
        at, ref, refs = ctx.workspace / f"nightshift-{fm['id']}", "refs/remotes/base", {}
    else:
        at = nc.source(ctx.vault, fm["repo"])
        ref, refs = fm["base"], nd.protected_refs(at)
    b = {"src": refs, "code": nd.code_status(ctx.vault),
         "base_sha": nc.git(at, "rev-parse", f"{ref}^{{commit}}").stdout.strip()}
    f.write_text(json.dumps(b))
    return b


def _deliver_plan(ctx: Ctx, fm: dict, clone: Path, idir: Path, before: dict) -> dict:
    res = _read_result(clone / ".nightshift" / "result.json")
    if res is None:
        return {"state": "failed", "reason": "no result"}
    if res["status"] == "blocked":
        return {"state": "blocked", "reason": "session", "needs": [f"Answer: {q}" for q in _questions(res)]}
    src = nc.source(ctx.vault, fm["repo"])
    if (fm["repo"] != "template" and nd.protected_refs(src) != before["src"]) or nd.code_status(ctx.vault) != before["code"]:
        ctx.alert(f"containment/{fm['id']}", f"{fm['id']}: a protected branch or vault code changed during the run")
        return {"state": "failed", "reason": "containment"}
    branch = f"nightshift/{fm['id']}"
    runner = ctx.workspace / "nightshift-runner.git"
    ok, sha = nd.fetch_branch(runner, clone, branch)
    if not ok:
        return {"state": "blocked", "reason": "no commits", "notes": sha}
    if sha == before["base_sha"]:
        return {"state": "blocked", "reason": "no commits"}
    files, problems = nd.protected_files(clone)
    if problems:
        return {"state": "blocked", "reason": "protected", "needs": [f"Protected file refused: {p}" for p in problems]}
    ok, sha = nd.apply_protected(runner, sha, branch, files, idir)
    if not ok:
        return {"state": "failed", "reason": "delivery", "notes": sha}
    ok, out = nd.verify_sha(runner, sha, ctx.workspace / f"nightshift-{fm['id']}-verify", fm.get("verify") or [],
                            idir / "verify.log")
    if not ok:
        return {"state": "blocked", "reason": "verify", "needs": [f"Fix the failing check: {out.splitlines()[0]}"]}
    (idir / "delivery.json").write_text(json.dumps({"sha": sha, "branch": branch, "title": _text(res.get("pr_title")) or fm["id"],
                                                    "body": _text(res.get("pr_body")) or _text(res.get("summary")),
                                                    "summary": _text(res.get("summary")), "tries": 0}))
    shutil.rmtree(clone, ignore_errors=True)
    return _deliver(ctx, fm, idir)


def _deliver(ctx: Ctx, fm: dict, idir: Path) -> dict:
    """Push the verified commit and open the pull request; on failure later ticks retry this step only."""
    d = json.loads((idir / "delivery.json").read_text())
    d["tries"] += 1
    (idir / "delivery.json").write_text(json.dumps(d))
    url, pr = nd.push_target(ctx.vault, fm)
    pr = pr or PR_FOR_LOCAL
    ok, push_log = nd.push(ctx.workspace / "nightshift-runner.git", d["sha"], d["branch"], url)
    (idir / "push.log").write_text(push_log)
    link = ""
    if ok:
        body = idir / "pr_body.md"
        body.write_text(f"{d['body']}\n\nQueued as Nightshift item `{fm['id']}`.\n")
        ok, link = nd.open_pr(pr, d["branch"], fm.get("pr_base") or "master", d["title"], body, push_log)
    if ok:
        verb = "Review and merge" if pr.startswith("github:") else "Open the pull request"
        return {"state": "done", "result": link, "needs": [f"{verb}: {link}"], "notes": d["summary"]}
    if d["tries"] < 3:
        return {"state": "delivering", "reason": "delivery", "notes": (link or push_log).strip()[-200:]}
    return {"state": "failed", "reason": "delivery",
            "needs": [f"Deliver {d['branch']} by hand ({d['sha'][:8]}): see {idir}/push.log"]}


def _deliver_research(ctx: Ctx, fm: dict, d: Path) -> dict:
    res = _read_result(d / "out" / "result.json")
    if res is None:
        return {"state": "failed", "reason": "no result"}
    if res["status"] == "blocked":
        return {"state": "blocked", "reason": "session", "needs": [f"Answer: {q}" for q in _questions(res)]}
    findings = d / "out" / Path(fm["output"]).name
    if not findings.is_file():
        return {"state": "failed", "reason": "no result"}
    ok, detail = nd.publish_research(ctx.vault, fm, findings)
    if not ok:
        return {"state": "failed", "reason": "delivery", "needs": [f"Findings rejected by the publish gate: {detail}"]}
    shutil.rmtree(d, ignore_errors=True)
    return {"state": "done", "result": f"[[{Path(fm['output']).stem}]]", "needs": [], "notes": _text(res.get("summary"))}


def _finish(ctx: Ctx, path: Path, fm: dict, idir: Path, cwd, out: dict) -> int:
    if out["state"] in ("failed", "blocked") and not out.get("needs"):
        tail = (idir / "run.log").read_text(errors="replace").splitlines()[-3:] if (idir / "run.log").is_file() else []
        out["needs"] = [f"{fm['id']} {out['state']} ({out.get('reason')}); work kept in {cwd}" + (f"; log: {' | '.join(tail)}" if tail else "")]
    final = out["state"] != "delivering"
    ni.update(path, state=out["state"], reason=out.get("reason") or None, result=out.get("result") or None,
              finished_at=ctx.now.isoformat() if final else None)
    if final:
        rep.write_outcome(ctx.vault, {"id": fm["id"], "kind": fm["kind"], "state": out["state"], "result": out.get("result", ""),
                                      "reason": out.get("reason", ""), "started_at": fm.get("started_at") or ctx.now.isoformat(),
                                      "finished_at": ctx.now.isoformat(), "report_date": ctx.date,
                                      "needs": out.get("needs", []), "notes": out.get("notes", "")})
        rep.write(ctx.vault, ctx.date)
    ctx.log({"item": fm["id"], "state": out["state"], "reason": out.get("reason", "")})
    return 0 if out["state"] in ("done", "cancelled", "delivering") else 1


def run_item(ctx: Ctx, path: Path, fm: dict, body: str) -> int:
    idir = rep.item_dir(ctx.vault, fm["id"])
    idir.mkdir(parents=True, exist_ok=True)
    if fm.get("state") == "delivering":
        return _finish(ctx, path, fm, idir, None, _deliver(ctx, fm, idir))
    _stop_stale(idir)
    resume = fm.get("state") in ("waiting_reset", "running")
    attempts = int(fm.get("attempts") or 0) + 1
    ni.update(path, state="running", started_at=fm.get("started_at") or ctx.now.isoformat(), attempts=str(attempts),
              reset_at=None)
    before = {}
    if fm["kind"] == "plan":
        try:
            cwd = _clone(ctx, fm)
        except CloneError as exc:   # ends now, with a report row and a Needs-you line, and frees the queue
            return _finish(ctx, path, fm, idir, None, {"state": "failed", "reason": "base", "needs": [
                f"Push {fm['base']} to the template remote, then queue {fm['id']} again ({exc})"]})
        before = _before(ctx, fm, idir)
    else:
        try:
            cwd = _research_dir(ctx, fm)
        except CloneError as exc:
            return _finish(ctx, path, fm, idir, None, {"state": "failed", "reason": "base", "needs": [
                f"Make {fm.get('base') or 'the default branch'} of {fm['repo']} readable, then queue {fm['id']} again ({exc})"]})
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
    if run["outcome"] == "no_start":
        if attempts >= 3:
            return _finish(ctx, path, fm, idir, cwd, {"state": "failed", "reason": "no result"})
        ctx.alert(f"nostart/{fm['id']}", f"{fm['id']}: the session did not start (expired auth or a failed resume); requeued")
        ni.update(path, state="queued", reason="session did not start", session_id=None)
        return 1
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
    return _finish(ctx, path, fm, idir, cwd, out)


# --- tick and CLI --------------------------------------------------------------------------------------

def _screen(ctx: Ctx) -> tuple:
    """(entries, refused). Only notes whose identifiers pass nc.identifiers are returned: their id, refs and output
    become paths and git arguments. A live note that fails is marked failed and alerted once."""
    entries, refused = [], []
    for path, fm, body in ni.items(ctx.vault):
        errs = nc.identifiers(fm)
        if not errs:
            entries.append((path, fm, body))
        elif fm.get("state") not in ("failed", "done", "cancelled"):
            why = "; ".join(errs)
            ni.update(path, state="failed", reason=f"invalid: {why}")
            ctx.alert(f"invalid/{path.name}", f"{path.name} refused: {why}")
            refused.append(path)
    return entries, refused


def _reconcile(ctx: Ctx, entries: list) -> None:
    for path, fm, _ in entries:
        idir = rep.item_dir(ctx.vault, fm["id"])
        state = fm.get("state")
        if state == "cancelled":
            _stop_stale(idir)
        elif state == "running" and int(fm.get("attempts") or 0) >= 3:
            _stop_stale(idir)
            ni.update(path, state="failed", reason="no result", finished_at=ctx.now.isoformat())
        if state in ("failed", "blocked", "cancelled", "done") and fm.get("finished_at"):
            try:
                old = ctx.now - datetime.fromisoformat(str(fm["finished_at"])) > timedelta(days=7)
            except ValueError:
                old = False
            if old:
                for d in (ctx.workspace / f"nightshift-{fm['id']}", ctx.workspace / f"nightshift-{fm['id']}-verify"):
                    shutil.rmtree(d, ignore_errors=True)


def tick(ctx: Ctx) -> int:
    entries, refused = _screen(ctx)
    if refused:
        return 2
    _reconcile(ctx, entries)
    entries, _ = _screen(ctx)
    delivering = [e for e in entries if e[1].get("state") == "delivering"]
    if delivering:
        path, fm, body = delivering[0]
        return run_item(ctx, path, fm, body)
    hfile = ctx.vault / rep.DIR / f"health-{ctx.date}.json"
    candidates = [e for e in entries if ns.due(e[1], ctx.local, ctx.window, 0)[0]
                  or e[1].get("state") == "running"]
    if not candidates:
        return 0
    if not hfile.is_file():
        h = health(ctx.vault, ctx.now, entries)
        rep.write_health(ctx.vault, ctx.date, h)
    h = json.loads(hfile.read_text())
    h["last_tick"] = ctx.local.strftime("%H:%M")
    rep.write_health(ctx.vault, ctx.date, h)
    if str(h.get("sandbox", "")).startswith("FAILED"):
        ctx.alert("sandbox", f"sandbox self-test failed: {h['sandbox']}; no items run")
        rep.write(ctx.vault, ctx.date)
        return 1
    usage7 = h.get("usage7")
    running = [e for e in entries if e[1].get("state") == "running"]
    chosen = running[0] if running else ns.pick(entries, ctx.local, ctx.window, usage7)
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
        fm.update(output=a.output, hosts=a.host, repo=a.repo, base=a.base)
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
