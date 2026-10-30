"""The Nightshift runner (Nightshift spec §3, §7). Exit 0 ok or nothing due, 1 an item failed, 2 usage or invalid item, 4 locked."""
import argparse
import fcntl
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import threading
import sys
import time as clock
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import nightshift_check as nc
from . import nightshift_deliver as nd
from . import nightshift_item as ni
from . import nightshift_report as rep
from . import nightshift_sched as ns
from . import nightshift_session as ss
from . import now as nowmod
from .intake import Intake

LOCK = "system/nightshift.lock"
POLL = 30            # seconds between session checks
MAX_PARALLEL = 3     # Work Orders one tick runs at once (#229; owner, 2026-10-16)
TICK_HOURS = 13      # no new start that would end past this: the unit stops a tick at 14h
SHARED = threading.RLock()   # the files more than one worker writes: report, health, ledger, alerts
PR_FOR_LOCAL = ""    # tests: the pull-request kind used when template_remote is a local path
CANARY = "~/.config/foundry/nightshift-canary"  # planted by the self-test under a path every profile denies
TOKEN_VARS = ("SSH_AUTH_SOCK", "GH_TOKEN", "GITHUB_TOKEN", "DBUS_SESSION_BUS_ADDRESS", "CLAUDE_CODE_OAUTH_TOKEN",
              "ANTHROPIC_API_KEY")   # the self-test's probes
# Prints the names that are set, never a value; grep exits 0 (a name), 1 (none) or 2 (the probe itself failed).
ENV_PROBE = f"env | grep -oE '^({'|'.join(TOKEN_VARS)})='; echo ENV_DONE=$?"
SELFTEST_PROMPT = ("This is the Nightshift runner's sandbox self-test, run by the vault's owner. The first two commands "
                   "below are expected to fail inside the sandbox and the third to print only an ENV_DONE line; the test "
                   "needs their real output, so run each one with the Bash tool even if you expect a denial, and do not "
                   "explain or refuse. Run exactly these three Bash commands, one at a time, and nothing else: "
                   "`curl -sS -m 5 -o /dev/null https://example.com; echo CURL_EXIT=$?`, "
                   f"`cat {CANARY}; echo CAT_EXIT=$?` and `{ENV_PROBE}`. Then stop.")
NO_START = ("the self-test session did not start (an expired login; a login held only in CLAUDE_CODE_OAUTH_TOKEN or "
            "ANTHROPIC_API_KEY, which the session environment does not carry; or a dropped variable such as HTTPS_PROXY; "
            "log in with `claude login`)")
SELFTEST_TRIES = 3


def _parser():
    p = argparse.ArgumentParser(prog="nightshift.py")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("tick")
    sub.add_parser("record-usage").add_argument("stream")
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
    g.add_argument("--window", action="store_true")
    a.add_argument("--budget")
    a.add_argument("--model", default="sonnet")
    c = sub.add_parser("check")
    c.add_argument("note")
    sub.add_parser("list").add_argument("--json", action="store_true")
    x = sub.add_parser("cancel")
    x.add_argument("id")
    r = sub.add_parser("report")
    r.add_argument("date", nargs="?")
    r.add_argument("--json", action="store_true")
    sub.add_parser("selftest")
    return p


class Ctx:
    def __init__(self, vault: Path, now: datetime):
        self.vault, self.now = vault, now
        self.t0 = clock.monotonic()
        cfg = nc.config(vault)
        self.tz = ZoneInfo(str(cfg.get("timezone") or "UTC"))
        self.brief_time = str(cfg.get("brief_time") or "06:00")
        self.window = ns.parse_window(nc.setting(cfg, "run_window", "nightshift_window"))
        self.workspace = nc.workspace(cfg)
        try:
            self.max_five_hour = float(cfg.get("order_max_five_hour", 0.6))
        except (TypeError, ValueError):
            self.max_five_hour = 0.6
        self.local = now.astimezone(self.tz)
        self.date = ns.report_date(self.local, self.brief_time)
        self.alerts = {}

    def clock_now(self) -> datetime:
        """Now, read again: the tick's own reading plus the time since, so a stamp written after a session is later."""
        return self.now + timedelta(seconds=clock.monotonic() - self.t0)

    def alert(self, key: str, msg: str) -> None:
        day = self.local.date().isoformat()
        seen = rep.state_dir(self.vault) / "alerts.json"
        with SHARED:
            data = json.loads(seen.read_text()) if seen.is_file() else {}
            if data.get(key) == day:
                return
            data[key] = day
            seen.parent.mkdir(parents=True, exist_ok=True)
            seen.write_text(json.dumps(data))
            path = self.vault / "system" / "logs" / f"alerts_{day}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"- {self.local.strftime('%H:%M:%S')} [orders] {msg}\n")

    def log(self, line: dict) -> None:
        path = self.vault / "system" / "logs" / f"nightshift-{self.now.strftime('%Y-%m')}.jsonl"
        with SHARED:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"time": self.clock_now().isoformat(), **line}, sort_keys=True) + "\n")


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
            # The production deny list (the vault root; _deny adds only the other codebases), so a pass speaks for the
            # profile items run under.
            settings.write_text(json.dumps(ss.profile(vault, "plan", [], deny=[str(vault)], cwd=tmp)))
            stream, errlog = Path(tmp) / "stream.jsonl", Path(tmp) / "stderr.log"
            cmd = ss.command("plan", SELFTEST_PROMPT, settings, "haiku", str(uuid.uuid4()), [])
            with open(stream, "w") as out, open(errlog, "w") as err:
                try:
                    subprocess.run(cmd, cwd=tmp, env=ss.session_env(), stdout=out, stderr=err, timeout=300)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    return False, f"self-test session failed: {exc.__class__.__name__}"
            s = ss.parse_stream(stream)
            stderr_tail = (errlog.read_text(errors="replace").strip().splitlines() or [""])[-1]
    finally:
        canary.unlink(missing_ok=True)
    # Owner decision (audit S3/S7 spec §2): an env-only login stops sessions, and the alert says so. An init event
    # followed by an error result is the same failure; the result text and the last stderr line are the evidence.
    error = s["result"] if (s["result"] or {}).get("is_error") else None
    if s["init"] is None or error:
        detail = [str(error.get("result") or error.get("subtype") or "") if error else "", stderr_tail]
        return False, NO_START + "".join(f": {d}" for d in detail if d)
    problem = ss.init_problem(s["init"], "plan")
    if problem:
        return False, f"profile: {problem}"
    text = " ".join(s["tool_results"])
    if "CURL_EXIT=0" in text:
        return False, "curl reached a host outside the allowlist"
    if "CAT_EXIT=0" in text or token in text:
        return False, f"the canary {CANARY} was readable"
    # The probe's output is read, not its exit: grep exits 1 when no variable is set. A name line before ENV_DONE
    # is a variable the session environment carries; any exit but 0 or 1 is a probe that did not run as written.
    probe = next((r for r in s["tool_results"] if "ENV_DONE=" in r), None)
    if probe is not None:
        before, _, after = probe.partition("ENV_DONE=")
        carried = [m.group(1) for m in re.finditer(r"^(\w+)=$", before, re.M)]
        if carried:
            return False, f"the session environment carries {', '.join(carried)}"
        if after.split()[:1] not in (["0"], ["1"]):
            return None, f"the environment probe failed (exit {after.split()[0] if after.split() else '?'})"
    if "CURL_EXIT=" not in text or "CAT_EXIT=" not in text or probe is None:
        return None, "the self-test commands did not run"
    return True, ""


def selftest(vault) -> tuple:
    """(passed, reason). Runs the plan profile's sandbox with two commands that must fail and a probe that must print
    nothing but ENV_DONE. A model that declines to run them proves nothing either way, so that case is retried; a
    command that succeeds, or a probe that names a variable, fails at once."""
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
    branch = f"order/{fm['id']}"
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
    # Background notes only, rebuilt each attempt: no private/, Now.md, meetings/ or preferences/, and no file reached
    # through a link, since the runner copies outside the sandbox (#298).
    c = d / "context"
    c.unlink() if c.is_symlink() else shutil.rmtree(c, ignore_errors=True)
    for sub in ("concepts", "entities", "summaries"):
        src = ctx.vault / "wiki" / fm["partition"] / sub
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(src, c / sub, ignore=lambda at, names: [n for n in names if n.startswith(".") or os.path.islink(os.path.join(at, n))])
    if fm.get("repo"):
        _research_code(ctx, fm, d / "code")
    return d


def _research_code(ctx: Ctx, fm: dict, code: Path) -> None:
    """A read-only copy of the item's repository at one commit (#77): that commit alone, fetched into a new
    repository, so nothing links to the registered clone and no other branch is visible. The first attempt records
    the commit in the run directory; a resumed attempt checks it out again, and rebuilds code/ when it cannot."""
    mark = rep.item_dir(ctx.vault, fm["id"]) / "code-commit"
    sha = mark.read_text().strip() if mark.is_file() else ""
    repo, base = fm["repo"], fm.get("base")
    src = None if repo == "template" else nc.source(ctx.vault, repo)
    # LFS files come from the live clone's store for the checkout only: the copy keeps no link to it (#83). A file
    # whose object the live clone never downloaded stays a pointer: research reads code, not binaries.
    lfs = ["-c", f"lfs.storage={store}", "-c", "lfs.skipdownloaderrors=true"] if (store := nc.lfs_store(src)) else []
    if sha and code.is_dir() and nc.git(code, *lfs, "checkout", "-q", "-f", "--detach", sha).returncode == 0:
        return
    shutil.rmtree(code, ignore_errors=True)   # half-built by a killed tick, or never built
    if repo == "template":   # from the template remote, never the vault
        url = str(nc.config(ctx.vault).get("template_remote") or "")
        where = f"fetch {base or 'HEAD'} from {nc.shown(url)}"
    else:
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
        r = nc.git(code, *lfs, "checkout", "-q", "--detach", "refs/remotes/base")
    if r.returncode:
        shutil.rmtree(code, ignore_errors=True)   # the next attempt starts again
        raise CloneError(f"{where}: {(r.stderr.strip().splitlines() or ['no error text'])[-1]}")
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(nc.git(code, "rev-parse", "HEAD").stdout.strip())


def _deny(ctx: Ctx, fm: dict) -> list:
    """Paths a session must not read: the whole vault (its clone, context/ and out/ live under order_workspace, so it
    needs nothing from the vault; audit S3/S7 spec §2) and every other registered codebase."""
    out = [str(ctx.vault)]
    # A plan item works in its own codebase; a research item reads code/, so even its own checkout stays denied.
    own = nc.source(ctx.vault, fm.get("repo")) if fm.get("kind") == "plan" and fm.get("repo") != "template" else None
    roots = [ctx.workspace]   # .env files where the profiles' ~/** globs do not reach (confinement spec §3.3, #326)
    for p in sorted((ctx.vault / "system" / "codebases").glob("*.md")):
        cb = nc.codebase(ctx.vault, p.stem) or {}
        path = Path(str(cb.get("path") or "")).expanduser()
        if cb.get("path") and path != own:
            out.append(str(path))
        if cb.get("path"):
            roots.append(path)
    home = Path.home().resolve()
    for r in dict.fromkeys(Path(os.path.abspath(r)) for r in roots):
        if not r.resolve().is_relative_to(home):
            out += [f"{r}/**/.env", f"{r}/**/.env.*"]
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
    hosts = list(nc.setting(cb, "order_hosts", "nightshift_hosts") or [])
    web = list(fm.get("hosts") or []) if kind == "research" else []
    settings = idir / "settings.json"
    settings.write_text(json.dumps(ss.profile(ctx.vault, kind, hosts, web, deny=_deny(ctx, fm), cwd=cwd, fence=ctx.workspace)))
    plugins = [p for p in [ss.superpowers_dir()] if p] + [Path(str(p)).expanduser() for p in nc.setting(cb, "order_plugins", "nightshift_plugins") or []]
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
    # The codebase's order_toolchain leads the plan session's PATH too (owner decision 2026-10-14), so the tasks run
    # the same tools the sealed verify will. A research item has no verify to match.
    # session_env() is the session's whole environment: no agent socket, no host token (audit S3/S7 spec §2).
    env = ss.session_env()
    if kind == "plan" and (tools := nc.toolchain(cb)):
        env["PATH"] = ":".join(tools + [p for p in [env.get("PATH")] if p])
    with open(stream, "a") as out, open(idir / "run.log", "a") as err:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=err, start_new_session=True, env=env)
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
    return {"outcome": "finished", "usage": s["usage"], "denied": s["denied"]}


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
    branch = f"order/{fm['id']}"
    runner = ctx.workspace / "nightshift-runner.git"
    ok, sha = nd.fetch_branch(runner, clone, branch)
    if not ok:   # a clone made before the rename to Work Orders holds nightshift/<id>
        old = f"nightshift/{fm['id']}"
        ok, old_sha = nd.fetch_branch(runner, clone, old)
        branch, sha = (old, old_sha) if ok else (branch, sha)
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
    cb = nc.codebase(ctx.vault, fm["repo"]) or {}   # a template item has no codebase file, so no install or toolchain
    ok, out = nd.verify_sha(runner, sha, ctx.workspace / f"nightshift-{fm['id']}-verify", fm.get("verify") or [],
                            idir / "verify.log", nc.lfs_store(src), str(cb.get("order_install") or ""), nc.toolchain(cb))
    if not ok:
        return {"state": "blocked", "reason": "verify", "needs": [f"Fix the failing check: {out.splitlines()[0]}"]}
    (idir / "delivery.json").write_text(json.dumps({"sha": sha, "branch": branch, "title": _text(res.get("pr_title")) or fm["id"],
                                                    "body": _text(res.get("pr_body")) or _text(res.get("summary")),
                                                    "summary": _text(res.get("summary")), "tries": 0,
                                                    "repo": fm["repo"], "pr_base": fm.get("pr_base") or "master"}))
    shutil.rmtree(clone, ignore_errors=True)
    return _deliver(ctx, fm, idir)


def _deliver(ctx: Ctx, fm: dict, idir: Path) -> dict:
    """Push the verified commit and open the pull request; on failure later ticks retry this step only."""
    d = json.loads((idir / "delivery.json").read_text())
    fm = {**fm, **{k: d[k] for k in ("repo", "pr_base") if k in d}}   # as verified: the note may change (#298)
    d["tries"] += 1
    (idir / "delivery.json").write_text(json.dumps(d))
    url, pr = nd.push_target(ctx.vault, fm)
    pr = pr or PR_FOR_LOCAL
    ok, push_log = nd.push(ctx.workspace / "nightshift-runner.git", d["sha"], d["branch"], url)
    (idir / "push.log").write_text(push_log)
    link = ""
    if ok:
        body = idir / "pr_body.md"
        body.write_text(f"{d['body']}\n\nQueued as Work Order `{fm['id']}`.\n")
        ok, link = nd.open_pr(pr, d["branch"], fm.get("pr_base") or "master", d["title"], body, push_log)
    if ok:
        verb = "Review and merge" if pr.startswith("github:") else "Open the pull request"
        return {"state": "done", "result": link, "needs": [f"{verb}: {link}"], "notes": d["summary"]}
    if d["tries"] < 3:
        return {"state": "delivering", "reason": "delivery", "notes": (link or push_log).strip()[-200:]}
    return {"state": "failed", "reason": "delivery",
            "needs": [f"Deliver {d['branch']} by hand ({d['sha'][:8]}): see {idir}/push.log"]}


def _no_result(ctx: Ctx, fm: dict, d: Path, denied) -> dict:
    """A missing result or note whose write under out/ the profile denied says so (#314)."""
    out = (d / "out").resolve()
    hit = next((p for p in denied if (d / p).resolve().is_relative_to(out)), None)
    if hit is None:
        return {"state": "failed", "reason": "no result"}
    return {"state": "failed", "reason": "out write denied", "needs": [
        f"The session's write to {hit} was denied: see {rep.item_dir(ctx.vault, fm['id'])}/stream.jsonl"]}


def _deliver_research(ctx: Ctx, fm: dict, d: Path, denied=()) -> dict:
    findings = d / "out" / Path(fm["output"]).name   # read outside the sandbox: a link could reach any file (#298)
    if any(p.is_symlink() for p in (d / "out", d / "out" / "result.json", findings)):
        ctx.alert(f"invalid/{fm['id']}", f"{fm['id']}: the research output is a link; refused")
        return {"state": "failed", "reason": "invalid: output is a link"}
    res = _read_result(d / "out" / "result.json")
    if res is None:
        return _no_result(ctx, fm, d, denied)
    if res["status"] == "blocked":
        return {"state": "blocked", "reason": "session", "needs": [f"Answer: {q}" for q in _questions(res)]}
    if not findings.is_file():
        return _no_result(ctx, fm, d, denied)
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
    finished = ctx.clock_now().isoformat()
    ni.update(path, state=out["state"], reason=out.get("reason") or None, result=out.get("result") or None,
              finished_at=finished if final else None)
    if final:
        _report_outcome(ctx, fm, out, finished)
        _now_line(ctx, fm, out)
    ctx.log({"item": fm["id"], "state": out["state"], "reason": out.get("reason", "")})
    return 0 if out["state"] in ("done", "cancelled", "delivering") else 1


def _owed(fm: dict, out: dict):
    """(statement, evidence) of the Now line a final outcome leaves the owner (#332), or None when it needs nothing.
    The statement is the report's Needs-you line, so the brief, which adds those too, sees it open and skips it. Only
    a GitHub pull request is evidence the Now check reads; a failed order's id is already closed, so its line carries
    none, or the next check would tick it at once."""
    if not out.get("needs") or (out["state"] == "done" and fm["kind"] != "plan"):
        return None
    statement = f"{out['needs'][0]} ({fm['id']})"
    if out["state"] == "done":
        return statement, out.get("result") if nowmod.PR_URL.match(out.get("result") or "") else ""
    return (statement, fm["id"] if out["state"] == "blocked" else "") if out["state"] in ("blocked", "failed") else None


def _now_line(ctx: Ctx, fm: dict, out: dict) -> None:
    """Add the owed line under run.lock; a busy lock or a refused line is one alert, never a failed order."""
    owed = _owed(fm, out)
    if owed is None:
        return
    try:
        with Intake(ctx.vault).lock("run.lock", timeout=60):
            nowmod.add(ctx.vault, fm.get("partition") or "work", "owed", owed[0], ctx.local.date().isoformat(),
                       evidence=owed[1], fit=True)
    except (TimeoutError, ValueError, OSError) as exc:   # TimeoutError is an OSError: the busy lock
        why = nowmod.refusal(exc) if isinstance(exc, ValueError) else "run.lock busy" \
            if isinstance(exc, TimeoutError) else f"{exc.__class__.__name__}: {exc.strerror or exc}"
        ctx.alert(f"now/{fm['id']}", f"{fm['id']}: its Now line was not added ({why})")


def _report_outcome(ctx: Ctx, fm: dict, out: dict, finished: str) -> None:
    with SHARED:
        rep.write_outcome(ctx.vault, {"id": fm["id"], "kind": fm["kind"], "state": out["state"], "result": out.get("result", ""),
                                      "reason": out.get("reason", ""), "started_at": fm.get("started_at") or ctx.clock_now().isoformat(),
                                      "finished_at": finished, "report_date": ctx.date,
                                      "needs": out.get("needs", []), "notes": out.get("notes", ""),
                                      "output": fm.get("output") or ""})  # a notice links it (#157)
        rep.write(ctx.vault, ctx.date)


def run_item(ctx: Ctx, path: Path, fm: dict, body: str) -> int:
    idir = rep.item_dir(ctx.vault, fm["id"])
    idir.mkdir(parents=True, exist_ok=True)
    if fm.get("state") == "delivering":
        return _finish(ctx, path, fm, idir, None, _deliver(ctx, fm, idir))
    _stop_stale(idir)
    if fm["kind"] == "research":   # before the attempt counts: a DNS outage leaves the order as it was (§3.2)
        internal, unresolved = nc.resolve_problems(fm.get("hosts") or [])
        if internal:
            return _finish(ctx, path, fm, idir, None, {"state": "failed", "reason": "host", "needs": [
                f"{internal[0]}: remove the host, then queue {fm['id']} again"]})
        if unresolved:
            ctx.log({"item": fm["id"], "state": fm.get("state"), "reason": "host does not resolve"})
            return 0
    resume = fm.get("state") in ("waiting_reset", "running")
    attempts = int(fm.get("attempts") or 0) + 1
    started = fm.get("started_at") or ctx.clock_now().isoformat()   # read now: a slot can free hours into the tick
    ni.update(path, state="running", started_at=started, attempts=str(attempts), reset_at=None)
    fm = {**fm, "started_at": started}   # the outcome and the report carry the same stamp
    if nc.workspace_inside_vault(ctx.vault, ctx.workspace):   # the session's profile denies the vault root
        return _finish(ctx, path, fm, idir, None, {"state": "failed", "reason": "workspace", "needs": [
            f"Move order_workspace outside the vault ({ctx.workspace} is inside it), then queue {fm['id']} again"]})
    before = {}
    if fm["kind"] == "plan":
        try:
            cwd = _clone(ctx, fm)
        except CloneError as exc:   # ends now, with a report row and a Needs-you line, and frees the queue
            return _finish(ctx, path, fm, idir, None, {"state": "failed", "reason": "base", "needs": [
                f"Push {fm['base']} to the template remote, then queue {fm['id']} again ({exc})"]})
        before = _before(ctx, fm, idir)
        gone = nc.toolchain_errors(fm["repo"], nc.codebase(ctx.vault, fm["repo"]) or {})
        if gone:   # a directory that passed readiness is gone: block now, before the session spends its budget
            return _finish(ctx, path, fm, idir, cwd, {"state": "blocked", "reason": "toolchain", "needs": gone})
    else:
        try:
            cwd = _research_dir(ctx, fm)
        except CloneError as exc:
            return _finish(ctx, path, fm, idir, None, {"state": "failed", "reason": "base", "needs": [
                f"Make {fm.get('base') or 'the default branch'} of {fm['repo']} readable, then queue {fm['id']} again ({exc})"]})
    run = _run_session(ctx, path, fm, body, cwd, idir, resume)
    with SHARED:
        rep.record_usage(ctx.vault, ctx.date, run.get("usage") or {}, ctx.clock_now().isoformat())
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
        out = _deliver_research(ctx, fm, cwd, run.get("denied", ()))
    return _finish(ctx, path, fm, idir, cwd, out)


# --- tick and CLI --------------------------------------------------------------------------------------

def _screen(ctx: Ctx, held=()) -> tuple:
    """(entries, refused). A note that can run passes nc.screen, the add-time field rules, at every pass (#298); one
    that never runs passes nc.identifiers. A live note that fails is marked failed and alerted once. A note a worker
    holds is left to it (ni.update has no lock) and screened again at its next attempt."""
    entries, refused = [], []
    for path, fm, body in ni.items(ctx.vault):
        parked = fm.get("state") in ("failed", "done", "cancelled", "blocked", "delivering")   # delivery.json holds repo
        errs = [] if fm.get("id") in held else nc.identifiers(fm) if parked else nc.screen(ctx.vault, fm, body, path)
        if not errs:
            entries.append((path, fm, body))
        elif fm.get("state") not in ("failed", "done", "cancelled"):
            why = "; ".join(errs)
            if not nc.identifiers(fm):   # a safe id: stop a session a crashed runner left; finished_at starts the clean-up
                _stop_stale(rep.item_dir(ctx.vault, fm["id"]))
            ni.update(path, state="failed", reason=f"invalid: {why}", finished_at=ctx.clock_now().isoformat())
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
            _stop_stale(idir)   # through _finish, so outcome.json is written and a notice goes out (#28)
            _finish(ctx, path, fm, idir, ctx.workspace / f"nightshift-{fm['id']}", {"state": "failed", "reason": "no result"})
        if state in ("failed", "blocked", "cancelled", "done") and fm.get("finished_at"):
            try:
                old = ctx.now - datetime.fromisoformat(str(fm["finished_at"])) > timedelta(days=7)
            except ValueError:
                old = False
            if old:
                for d in (ctx.workspace / f"nightshift-{fm['id']}", ctx.workspace / f"nightshift-{fm['id']}-verify"):
                    shutil.rmtree(d, ignore_errors=True)


def _plan_key(fm: dict):
    """Two plan items on one repo and base would push competing branches from one plan: they never run together."""
    return (fm.get("repo"), fm.get("base")) if fm.get("kind") == "plan" else None


class _Pool:
    """The tick's workers (parallel orders spec §3): each runs run_item on its own thread; a finish wakes the tick."""

    def __init__(self, ctx: Ctx):
        self.ctx, self.threads, self.keys, self.done, self.rc = ctx, {}, {}, threading.Event(), 0
        self.started = set()   # one attempt per item per tick, as before: a requeued item waits for the next tick
        self.finished = set()

    def free(self) -> int:
        return MAX_PARALLEL - len(self.threads)

    def busy_keys(self) -> set:
        return {k for k in self.keys.values() if k}

    def start(self, entry) -> None:
        path, fm, body = entry

        def work():
            rc = 1
            try:
                rc = run_item(self.ctx, path, fm, body)
            except Exception as exc:   # one order's crash never stops the others; it is an alert and a failed tick
                self.ctx.alert(f"worker/{fm['id']}", f"{fm['id']}: the worker stopped: {exc.__class__.__name__}: {exc}")
            finally:
                with SHARED:
                    self.rc = max(self.rc, rc)
                    self.finished.add(fm["id"])
                self.done.set()

        t = threading.Thread(target=work, name=f"order-{fm['id']}")
        self.threads[fm["id"]], self.keys[fm["id"]] = t, _plan_key(fm)
        self.started.add(fm["id"])
        t.start()

    def reap(self) -> None:
        with SHARED:
            gone, self.finished = self.finished, set()
        for iid in gone:
            self.threads.pop(iid).join()
            self.keys.pop(iid)

    def wait(self) -> None:
        self.done.wait(timeout=5)
        self.done.clear()
        self.reap()

    def join_all(self) -> None:
        for t in list(self.threads.values()):
            t.join()
        self.reap()


def _day_health(ctx: Ctx, entries) -> tuple:
    """The day's checks on its first tick, and this tick's stamp. Returns (health, Held line it cleared)."""
    hfile = rep.state_dir(ctx.vault) / f"health-{ctx.date}.json"
    try:
        h = json.loads(hfile.read_text()) if hfile.is_file() else {}
    except (OSError, ValueError):
        h = {}
    # The day's checks run on its first tick. A usage reading run_headless.sh recorded can create the file
    # first (usage ceiling spec), so the test is the sandbox key, not the file; that newer reading is kept.
    if "sandbox" not in h:
        prev = rep.state_dir(ctx.vault) / f"health-{(date.fromisoformat(ctx.date) - timedelta(days=1)).isoformat()}.json"
        try:   # the last 5-hour reading outlives the report day, so the ceiling holds right after the brief too
            old = json.loads(prev.read_text()) if prev.is_file() else {}
        except (OSError, ValueError):
            old = {}
        carry = {k: old[k] for k in ("usage5", "usage5_at") if k in old}
        checked = health(ctx.vault, ctx.now, entries)   # the self-test runs outside the lock: workers keep writing
        with SHARED:
            rep.write_health(ctx.vault, ctx.date, checked | carry | h)
    with SHARED:
        h = json.loads(hfile.read_text())
        h["last_tick"] = ctx.local.strftime("%H:%M")
        was_held = h.pop("held", None)   # the report's Held line shows only the latest tick's hold
        rep.write_health(ctx.vault, ctx.date, h)
    return h, was_held


def _claim(ctx: Ctx, fm: dict) -> bool:
    claim = rep.item_dir(ctx.vault, fm["id"]) / f"claim-{int(fm.get('attempts') or 0) + 1}"
    try:
        claim.parent.mkdir(parents=True, exist_ok=True)
        claim.mkdir()
    except FileExistsError:
        # Only a tick stopped between this claim and run_item's attempts update leaves one: the tick holds the global
        # lock, so its owner is dead and the attempt never began. Taking it over keeps the item from waiting forever.
        pass
    return True


def _set_held(ctx: Ctx, held: str) -> None:
    """Write the Held line ("" clears it) when it changed; the brief and the debrief copy the report, so it is in it."""
    hfile = rep.state_dir(ctx.vault) / f"health-{ctx.date}.json"
    with SHARED:
        h = json.loads(hfile.read_text()) if hfile.is_file() else {}
        if (h.get("held") or "") == held:
            return
        h.pop("held", None)
        rep.write_health(ctx.vault, ctx.date, h | ({"held": held} if held else {}))
        rep.write(ctx.vault, ctx.date)


def _fits(ctx: Ctx, now: datetime, fm: dict) -> bool:
    """The unit stops a tick at 14h and kills its sessions with it: a new start must end inside TICK_HOURS."""
    budget = ni.budget_seconds(fm.get("budget") or ("4h" if fm.get("kind") == "plan" else "1h"))
    return (now - ctx.now).total_seconds() + budget <= TICK_HOURS * 3600


def tick(ctx: Ctx) -> int:
    """Up to MAX_PARALLEL items at once (parallel orders spec §3). Delivering items first, then running ones resume,
    then queued and waiting items in pick order; each finish refills its slot until nothing runs or can start.
    Each pass reads the clock again: a tick lives for hours, and due times, the window and the ceiling move with it."""
    moved = rep.migrate_state(ctx.vault)   # once, after the update that moved state out of the vault (#320)
    if moved:
        ctx.log({"state": "moved", "to": str(rep.state_dir(ctx.vault)), "names": moved})
    entries, refused = _screen(ctx)
    if refused:
        return 2
    _reconcile(ctx, entries)
    pool, day, skip, blocked, held = _Pool(ctx), None, set(), False, ""
    try:
        while True:
            now = ctx.clock_now()
            local = now.astimezone(ctx.tz)
            entries, _ = _screen(ctx, pool.threads)
            idle = [e for e in entries if e[1]["id"] not in pool.started and e[1]["id"] not in skip]
            for e in [e for e in idle if e[1].get("state") == "delivering"][:pool.free()]:
                pool.start(e)
            idle = [e for e in idle if e[1]["id"] not in pool.started]
            candidates = [e for e in idle if ns.due(e[1], local, ctx.window, 0)[0] or e[1].get("state") == "running"]
            if candidates and pool.free() and not blocked:
                if day is None:
                    day = _day_health(ctx, entries)
                    if str(day[0].get("sandbox", "")).startswith("FAILED"):
                        ctx.alert("sandbox", f"sandbox self-test failed: {day[0]['sandbox']}; no items run")
                        with SHARED:
                            rep.write(ctx.vault, ctx.date)
                        pool.rc = max(pool.rc, 1)
                        blocked = True   # nothing new starts this tick; delivering workers finish
            if candidates and pool.free() and not blocked:
                for e in [e for e in candidates if e[1].get("state") == "running"]:
                    if pool.free() and (_plan_key(e[1]) is None or _plan_key(e[1]) not in pool.busy_keys()):
                        if _claim(ctx, e[1]):
                            pool.start(e)
                        else:
                            skip.add(e[1]["id"])
                while pool.free():
                    rest = [e for e in candidates if e[1].get("state") != "running" and e[1]["id"] not in pool.started
                            and e[1]["id"] not in skip and (_plan_key(e[1]) is None or _plan_key(e[1]) not in pool.busy_keys())]
                    chosen = ns.pick(rest, local, ctx.window, day[0].get("usage7"))
                    if not chosen:
                        break
                    if not _fits(ctx, now, chosen[1]):
                        skip.add(chosen[1]["id"])   # waits for the next tick
                        continue
                    if chosen[1].get("state") == "queued":
                        # The 5-hour ceiling holds only a new start, read afresh: a finished worker may have raised it.
                        hfile = rep.state_dir(ctx.vault) / f"health-{ctx.date}.json"
                        with SHARED:
                            fresh = json.loads(hfile.read_text()) if hfile.is_file() else day[0]
                        held = ns.five_hour_hold(fresh, now, ctx.max_five_hour)
                        _set_held(ctx, held)
                        if held:
                            break   # checked again on the next pass, after a worker finishes
                    if _claim(ctx, chosen[1]):
                        pool.start(chosen)
                    else:
                        skip.add(chosen[1]["id"])
            if not pool.threads:
                break
            pool.wait()
    finally:   # the global lock goes when this returns: never while a worker still runs a session
        pool.join_all()
    if day is None:   # nothing could start: a held item was cancelled or finished elsewhere, so drop a stale Held line
        _set_held(ctx, "")
    elif day[1] and not held:
        with SHARED:
            rep.write(ctx.vault, ctx.date)
    return pool.rc


def _add(ctx: Ctx, a) -> int:
    item_id = ni.new_id(a.title, ctx.local)
    fm = {"type": "nightshift_item", "id": item_id, "partition": a.partition, "kind": a.kind, "state": "queued",
          "queued_at": ctx.local.isoformat(), "start": "at" if a.at else ("window" if a.window else "now"),
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
    if not errs and a.kind == "research":   # owner-set order_hosts are config and are not resolved (§3.2)
        errs = [e for problems in nc.resolve_problems(fm.get("hosts") or []) for e in problems]
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
        errs = nc.check(vault, fm, body, Path(a.note).resolve())
        print("\n".join(f"not ready: {e}" for e in errs) or "ready")
        return 2 if errs else 0
    if cmd == "list" and a.json:  # read-only (#375)
        keys = ("id", "partition", "kind", "state", "start", "start_at", "queued_at", "started_at", "finished_at",
                "repo", "base", "result", "reason")
        items = [{k: (str(fm[k]) if fm.get(k) not in (None, "") else None) for k in keys} for _, fm, _ in ni.items(vault)]
        print(json.dumps({"v": 1, "items": items}, ensure_ascii=False))
        return 0
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
    if cmd == "report" and a.json:  # built from the files without writing the report (#375)
        print(json.dumps({"v": 1, **rep.data(vault, a.date or ctx.date)}, ensure_ascii=False))
        return 0
    if cmd == "report":
        print(rep.write(vault, a.date or ctx.date).read_text())
        return 0
    if cmd == "record-usage":
        # Every run_headless.sh session refreshes the reading the ceiling holds on (usage ceiling spec).
        rep.record_usage(vault, ctx.date, ss.parse_stream(a.stream)["usage"], now.isoformat())
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
