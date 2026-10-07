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
LINK = re.compile(r"https://bitbucket\.org/\S+/pull-requests/new\?\S+")


def protected_refs(repo) -> dict:
    r = nc.git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads/master", "refs/heads/main")
    return dict(line.split() for line in r.stdout.splitlines() if line.strip())


def code_status(vault) -> str:
    return nc.git(vault, "status", "--porcelain", "--", *CODE_PATHS).stdout


def bwrap(workdir, cmd: str) -> list:
    """Run cmd with the host read-only, $HOME and /tmp empty, no network, an empty environment, and only workdir writable."""
    home = str(Path.home())
    path = "/usr/local/bin:/usr/bin:/bin"
    return ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", home,
            "--bind", str(workdir), str(workdir), "--unshare-net", "--die-with-parent", "--clearenv",
            "--setenv", "PATH", path, "--setenv", "HOME", home, "--setenv", "LANG", "C.UTF-8", "--setenv", "TMPDIR", "/tmp",
            "--chdir", str(workdir), "bash", "-c", cmd]


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


def _git_env() -> dict:
    return dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")


def fetch_branch(runner_repo, clone, branch: str, sha: str) -> tuple:
    """Copy the session's branch into the runner's repository and confirm its tip is the commit the runner checked."""
    runner_repo = Path(runner_repo)
    if not (runner_repo / "HEAD").exists():
        subprocess.run(["git", "init", "-q", "--bare", str(runner_repo)], check=True)
    f = subprocess.run(["git", "-C", str(runner_repo), "fetch", "-q", "--no-tags", str(clone), f"+{branch}:{branch}"],
                       capture_output=True, text=True, env=_git_env())
    if f.returncode:
        return False, f.stderr.strip()
    tip = subprocess.run(["git", "-C", str(runner_repo), "rev-parse", branch], capture_output=True, text=True).stdout.strip()
    return (True, "") if tip == sha else (False, f"branch moved after the check ({sha[:8]} -> {tip[:8]})")


PROTECTED_DIRS = (".claude/skills/", ".claude/commands/", ".claude/agents/")
PROTECTED_MAX = 256 * 1024


def protected_files(clone) -> tuple:
    """Files the session proposed under .nightshift/protected/ for paths it cannot write (.claude/).
    Returns ([(path, bytes)], [problem]); only regular files under PROTECTED_DIRS are accepted."""
    root = Path(clone) / ".nightshift" / "protected"
    files, problems = [], []
    if not root.is_dir():
        return files, problems
    real_root = os.path.realpath(root)
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink() or not os.path.realpath(p).startswith(real_root + os.sep):
            problems.append(f"{rel}: symlink refused")
        elif p.is_dir():
            continue
        elif not rel.startswith(PROTECTED_DIRS) or ".." in rel.split("/"):
            problems.append(f"{rel}: only {', '.join(PROTECTED_DIRS)} may be proposed")
        elif not p.is_file() or p.stat().st_size > PROTECTED_MAX:
            problems.append(f"{rel}: not a regular file under {PROTECTED_MAX // 1024} KB")
        else:
            files.append((rel, p.read_bytes()))
    return files, problems


def apply_protected(runner_repo, sha: str, branch: str, files, workdir) -> tuple:
    """Commit the proposed files on top of sha inside the runner's own repository (plumbing only, so nothing in the
    session-writable clone's git config or hooks runs). Returns (ok, new sha or reason)."""
    if not files:
        return True, sha
    runner = str(runner_repo)
    env = dict(_git_env(), GIT_INDEX_FILE=str(Path(workdir) / "protected.index"), GIT_AUTHOR_NAME="Nightshift",
               GIT_AUTHOR_EMAIL="nightshift@localhost", GIT_COMMITTER_NAME="Nightshift",
               GIT_COMMITTER_EMAIL="nightshift@localhost")

    def git(*args, data=None):
        r = subprocess.run(["git", "-C", runner, *args], input=data, capture_output=True, env=env)
        if r.returncode:
            raise RuntimeError(r.stderr.decode(errors="replace").strip())
        return r.stdout.decode().strip()
    try:
        git("read-tree", sha)
        for rel, data in files:
            blob = git("hash-object", "-w", "--stdin", data=data)
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}")
        tree = git("write-tree")
        msg = "Add files the session proposed for protected paths\n\n" + "\n".join(f"- {r}" for r, _ in files) + "\n"
        new = git("commit-tree", tree, "-p", sha, data=msg.encode())
        git("update-ref", f"refs/heads/{branch}", new, sha)
    except RuntimeError as exc:
        return False, str(exc)
    finally:
        Path(env["GIT_INDEX_FILE"]).unlink(missing_ok=True)
    return True, new


def verify_sha(runner_repo, sha: str, vdir, cmds, log_path) -> tuple:
    """Run the verify commands on a private checkout of sha, so nothing they do reaches the commit that is pushed."""
    vdir = Path(vdir)
    shutil.rmtree(vdir, ignore_errors=True)
    try:
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(runner_repo), str(vdir)], check=True,
                       capture_output=True, env=_git_env())
        subprocess.run(["git", "-C", str(vdir), "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", sha],
                       check=True, capture_output=True, env=_git_env())
        return run_verify(vdir, cmds, log_path)
    finally:
        shutil.rmtree(vdir, ignore_errors=True)


def push(runner_repo, sha: str, branch: str, url: str) -> tuple:
    env = dict(_git_env(), GIT_SSH_COMMAND="ssh -o BatchMode=yes")
    cmd = ["git", "-C", str(runner_repo), "-c", "core.hooksPath=/dev/null"]
    if url.startswith("https://github.com/"):
        cmd += ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
    p = subprocess.run(cmd + ["push", "--no-verify", url, f"{sha}:refs/heads/{branch}"],
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
