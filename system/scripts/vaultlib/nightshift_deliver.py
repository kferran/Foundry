"""Containment, sandboxed verify, push, pull request and research publishing (Nightshift spec §3.3)."""
import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import nightshift_check as nc
from . import publish

CODE_PATHS = ["system/scripts", "system/schemas", "system/systemd", "system/hooks", "system/nightshift", ".claude",
              "CLAUDE.md"]
MASK_DIRS = [".ssh", ".config/gh", ".config/foundry"]
MASK_FILES = [".claude/.credentials.json", ".claude.json", ".git-credentials"]
LINK = re.compile(r"https://bitbucket\.org/\S+/pull-requests/new\?\S+")


def protected_refs(repo) -> dict:
    r = nc.git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads/master", "refs/heads/main")
    return dict(line.split() for line in r.stdout.splitlines() if line.strip())


def code_status(vault) -> str:
    return nc.git(vault, "status", "--porcelain", "--", *CODE_PATHS).stdout


def bwrap(clone, cmd: str) -> list:
    home = Path.home()
    args = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--bind", str(clone), str(clone), "--unshare-net", "--die-with-parent", "--chdir", str(clone)]
    args += [a for d in MASK_DIRS if (home / d).is_dir() for a in ("--tmpfs", str(home / d))]
    args += [a for f in MASK_FILES if (home / f).is_file() for a in ("--ro-bind", "/dev/null", str(home / f))]
    return args + ["bash", "-c", cmd]


def run_verify(clone, cmds, log_path, timeout=1800) -> tuple:
    with open(log_path, "a", encoding="utf-8") as log:
        for cmd in cmds:
            try:
                r = subprocess.run(bwrap(clone, cmd), capture_output=True, text=True, timeout=timeout)
                code, text = r.returncode, r.stdout + r.stderr
            except subprocess.TimeoutExpired:
                code, text = 124, f"timed out after {timeout}s"
            log.write(f"$ {cmd}\n{text}\n[exit {code}]\n")
            if code != 0:
                return False, f"{cmd}: exit {code}\n" + "\n".join(text.splitlines()[-20:])
    return True, ""


def push_target(vault, fm: dict) -> tuple:
    if fm.get("repo") == "template":
        url = str(nc.config(vault).get("template_remote") or "")
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(\.git)?$", url)
        return url, (f"github:{m.group(1)}" if m else "")
    url = nc.git(nc.source(vault, fm["repo"]), "remote", "get-url", "origin").stdout.strip()
    return url, str((nc.codebase(vault, fm["repo"]) or {}).get("nightshift_pr") or "")


def push(runner_repo, clone, branch: str, url: str) -> tuple:
    runner_repo = Path(runner_repo)
    if not (runner_repo / "HEAD").exists():
        subprocess.run(["git", "init", "-q", "--bare", str(runner_repo)], check=True)
    f = subprocess.run(["git", "-C", str(runner_repo), "fetch", "-q", str(clone), f"+{branch}:{branch}"],
                       capture_output=True, text=True)
    if f.returncode:
        return False, f.stderr
    env = dict(os.environ, GIT_SSH_COMMAND="ssh -o BatchMode=yes", GIT_TERMINAL_PROMPT="0")
    cmd = ["git", "-C", str(runner_repo), "-c", "core.hooksPath=/dev/null"]
    if url.startswith("https://github.com/"):
        cmd += ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
    p = subprocess.run(cmd + ["push", "--no-verify", url, f"{branch}:refs/heads/{branch}"],
                       capture_output=True, text=True, env=env)
    return p.returncode == 0, p.stdout + p.stderr


def open_pr(pr: str, branch: str, pr_base: str, title: str, body_file, push_log: str) -> tuple:
    if pr.startswith("github:"):
        r = subprocess.run(["gh", "pr", "create", "--repo", pr[len("github:"):], "--base", pr_base, "--head", branch,
                            "--title", title, "--body-file", str(body_file)], capture_output=True, text=True)
        lines = r.stdout.strip().splitlines()
        return (True, lines[-1]) if r.returncode == 0 and lines else (False, (r.stderr or r.stdout).strip())
    if pr == "bitbucket-link":
        m = LINK.search(push_log or "")
        return (True, m.group(0)) if m else (False, "no create-PR link in the push output")
    return False, f"unknown nightshift_pr {pr!r}"


def publish_research(vault, fm: dict, findings: Path) -> tuple:
    run_id = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-nightshift-{secrets.token_hex(2)}"
    try:
        publish.snapshot(vault, run_id, [fm["output"]])
        dst = publish.staging_dir(vault, run_id) / fm["output"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(findings, dst)
        report = publish.commit_run(vault, run_id)
    except publish.PublishError as exc:
        return False, str(exc)
    if report.get("status") == "published":
        return True, fm["output"]
    return False, f"publish gate: {report.get('status')}: {report.get('problems') or report.get('conflicts')}"
