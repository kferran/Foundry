"""Lookups and readiness checks for Nightshift items (Nightshift spec §3.1)."""
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from . import frontmatter
from . import nightshift_item as ni

TASK = re.compile(r"^### Task (\d+):", re.M)
_BRANCH = r"(?:`(?:master|main)`|\bmaster\b|\bmain\s+branch\b|\borigin\s+main\b)"
PROTECTED = re.compile(rf"\b(?:on|vault|to|into|onto)\s+(?:the\s+)?{_BRANCH}|'s\s+{_BRANCH}"
                       rf"|\b(?:push|merge|checkout|switch)\b[^\n]*?\s{_BRANCH}|\bdeploy\b", re.I)
SECTIONS = ("## Question", "## Scope", "## Done when", "## Output")
HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
ID = re.compile(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _fm(path: Path) -> dict:
    return (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}) if path.is_file() else {}


def setting(d: dict, new: str, old: str):
    """A Work Orders setting under its new key, else its old nightshift_* key (Foreman v1 §3.1)."""
    return d[new] if new in d else d.get(old)


def config(vault) -> dict:
    return _fm(Path(vault) / "system" / "config.md")


def codebase(vault, name) -> dict | None:
    path = Path(vault) / "system" / "codebases" / f"{name}.md"
    return _fm(path) if name and path.is_file() else None


def source(vault, repo) -> Path | None:
    """A codebase's registered clone. A template item has none: it is read from template_remote, never the vault."""
    if repo == "template":
        return None
    cb = codebase(vault, repo)
    return Path(str(cb["path"])).expanduser() if cb and cb.get("path") else None


def git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def lfs_store(src) -> str:
    """The live clone's Git LFS object store, which the runner's own checkouts read (#83), or ""."""
    d = git(src, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip() if src else ""
    return f"{d}/lfs" if d else ""


def remote_git(url: str) -> tuple:
    """git -c options and environment for talking to a remote: no prompts; the gh credential helper for GitHub HTTPS."""
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes")
    opts = ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"] \
        if url.startswith("https://github.com/") else []
    return opts, env


def shown(url: str) -> str:
    """The URL without any user:password@ part, for messages and logs."""
    return re.sub(r"//[^/@]+@", "//", url)


def fetch_base(repo, url: str, base: str | None, dest: str, depth: int | None = None, timeout: int = 600,
               commit: str | None = None):
    """Fetch commit, else refs/heads/<base>, else the remote's HEAD, from url into repo as dest. A URL that starts
    with "-" is refused: git reads it as an option."""
    if url.startswith("-"):
        raise ValueError("template_remote must be a URL or a path")
    opts, env = remote_git(url)
    cmd = ["git", "-C", str(repo), *opts, "fetch", "-q", "--no-tags", *(["--depth", str(depth)] if depth else []),
           url, f"{commit or (f'refs/heads/{base}' if base else 'HEAD')}:{dest}"]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", f"timed out after {timeout}s")


def parse_tasks(text) -> set | None:
    text = str(text or "").strip()
    if not text:
        return None
    out = set()
    for part in text.split(","):
        m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", part)
        if not m:
            raise ValueError(f"tasks must look like 1-8 or 1,3: {text!r}")
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        out |= set(range(min(a, b), max(a, b) + 1))
    return out


def task_blocks(plan_text: str) -> dict:
    heads = list(TASK.finditer(plan_text))
    return {int(m.group(1)): plan_text[m.start():(heads[i + 1].start() if i + 1 < len(heads) else len(plan_text))]
            for i, m in enumerate(heads)}


def identifiers(fm: dict) -> list:
    """The fields the runner turns into file paths and git arguments. check() and the tick refuse a note that fails."""
    errs = []
    if not ID.fullmatch(str(fm.get("id") or "")):
        errs.append("id must look like 2026-10-07-some-slug (lower-case letters, digits and dashes)")
    if fm.get("partition") not in ni.PARTITIONS:
        errs.append("partition must be work, personal or shared")
    if fm.get("repo") and not NAME.fullmatch(str(fm["repo"])):
        errs.append("repo must be a plain name (a registered codebase or template)")
    errs += [f"{k} must not start with '-'" for k in ("base", "pr_base") if str(fm.get(k) or "").startswith("-")]
    out = str(fm.get("output") or "")
    if out.startswith("/") or ".." in out.split("/"):
        errs.append("output must be a relative path with no '..' segments")
    return errs


def check(vault, fm: dict, body: str) -> list:
    errs = identifiers(fm)
    if errs:
        return errs  # nothing below may pass a bad ref or path to git
    kind = fm.get("kind")
    try:
        ni.budget_seconds(fm.get("budget") or ("4h" if kind == "plan" else "1h"))
    except ValueError as exc:
        errs.append(str(exc))
    if fm.get("start") == "at":
        try:
            datetime.fromisoformat(str(fm.get("start_at")))
        except ValueError:
            errs.append("start at needs start_at as an ISO date-time")
    if kind == "plan":
        errs += _plan(vault, fm)
    elif kind == "research":
        errs += _research(vault, fm, body)
    else:
        errs.append("kind must be plan or research")
    return errs


def _plan(vault, fm: dict) -> list:
    repo, base = fm.get("repo", ""), fm.get("base", "")
    errs = [] if fm.get("verify") else ["verify needs at least one command"]
    if repo == "template":
        url = str(config(vault).get("template_remote") or "")
        if not url:
            return ["config has no template_remote"]
        if url.startswith("-"):
            return ["template_remote must be a URL or a path"]
        if not base:
            return errs + ["base (empty) must name a branch on the template remote"]
        with tempfile.TemporaryDirectory(prefix="nightshift-check-") as tmp:   # the base and plan, read from the remote
            subprocess.run(["git", "init", "-q", "--bare", tmp], check=True, capture_output=True)
            f = fetch_base(tmp, url, base, f"refs/heads/{base}", depth=1, timeout=120)
            if f.returncode and "couldn't find remote ref" in f.stderr:
                return errs + [f"base {base} is not on the template remote {shown(url)} (push it first)"]
            if f.returncode:
                why = (f.stderr.strip().splitlines() or ["no error text"])[-1]
                return errs + [f"cannot read the template remote {shown(url)}: {why}"]
            return errs + _plan_at(tmp, fm)
    src = source(vault, repo)
    if src is None:
        return [f"repo {repo!r} is not a registered codebase or 'template'"]
    if not setting(codebase(vault, repo) or {}, "order_pr", "nightshift_pr"):
        errs.append(f"codebase {repo} has no order_pr (github:<owner>/<repo> or bitbucket-link)")
    if not base or git(src, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode:
        return errs + [f"base {base or '(empty)'} does not resolve in {src}"]
    return errs + _plan_at(src, fm)


def _plan_at(src, fm: dict) -> list:
    """Checks on the plan committed at the item's base in src."""
    base, plan, errs = fm.get("base", ""), fm.get("plan", ""), []
    shown = git(src, "show", f"{base}:{plan}")
    if not plan or shown.returncode:
        return errs + [f"plan {plan or '(empty)'} is not committed at {base}"]
    blocks = task_blocks(shown.stdout)
    if not blocks:
        return errs + ["the plan has no '### Task N:' headings"]
    try:
        wanted = parse_tasks(fm.get("tasks")) or set(blocks)
    except ValueError as exc:
        return errs + [str(exc)]
    missing = sorted(wanted - set(blocks))
    if missing:
        errs.append(f"tasks not in the plan: {', '.join(map(str, missing))}")
    for n in sorted(wanted & set(blocks)):
        if PROTECTED.search(blocks[n]):
            errs.append(f"task {n} works on a protected branch or deploys; leave it out with --tasks")
    return errs


def _research(vault, fm: dict, body: str) -> list:
    errs = [f"the brief needs a '{h}' section" for h in SECTIONS if h not in body]
    out, part = str(fm.get("output") or ""), fm.get("partition")
    if not (out.startswith(f"wiki/{part}/") and out.endswith(".md")):
        errs.append(f"output must be a note path under wiki/{part}/")
    errs += [f"host {h!r} is not a plain host name" for h in fm.get("hosts") or [] if not HOST.match(str(h))]
    return errs + _research_repo(vault, fm)


def research_base(src, base: str | None) -> str:
    """The commit a research item reads in a codebase clone: base, else the remote's default branch."""
    for ref in [base] if base else ["origin/HEAD", "origin/main", "origin/master"]:
        r = git(src, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if r.returncode == 0:
            return r.stdout.strip()
    return ""


def _research_repo(vault, fm: dict) -> list:
    """A research item may name a repository to read (#77): a registered codebase, or the template's remote."""
    repo, base = fm.get("repo"), fm.get("base")
    if not repo:
        return []
    if repo == "template":
        url = str(config(vault).get("template_remote") or "")
        if not url:
            return ["config has no template_remote"]
        if url.startswith("-"):
            return ["template_remote must be a URL or a path"]
        with tempfile.TemporaryDirectory(prefix="nightshift-check-") as tmp:
            subprocess.run(["git", "init", "-q", "--bare", tmp], check=True, capture_output=True)
            f = fetch_base(tmp, url, base, "refs/heads/base", depth=1, timeout=120)
        if f.returncode and "couldn't find remote ref" in f.stderr:
            return [f"base {base or 'HEAD'} is not on the template remote {shown(url)} (push it first)"]
        if f.returncode:
            why = (f.stderr.strip().splitlines() or ["no error text"])[-1]
            return [f"cannot read the template remote {shown(url)}: {why}"]
        return []
    src = source(vault, repo)
    if src is None:
        return [f"repo {repo!r} is not a registered codebase or 'template'"]
    if not research_base(src, base):
        return [f"base {base or 'origin/HEAD'} does not resolve in {src}"]
    return []
