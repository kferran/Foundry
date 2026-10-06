"""Lookups and readiness checks for Nightshift items (Nightshift spec §3.1)."""
import re
import subprocess
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


def _fm(path: Path) -> dict:
    return (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}) if path.is_file() else {}


def config(vault) -> dict:
    return _fm(Path(vault) / "system" / "config.md")


def codebase(vault, name) -> dict | None:
    path = Path(vault) / "system" / "codebases" / f"{name}.md"
    return _fm(path) if name and path.is_file() else None


def source(vault, repo) -> Path | None:
    if repo == "template":
        return Path(vault)
    cb = codebase(vault, repo)
    return Path(str(cb["path"])).expanduser() if cb and cb.get("path") else None


def git(repo, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


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


def check(vault, fm: dict, body: str) -> list:
    errs = []
    kind = fm.get("kind")
    if fm.get("partition") not in ni.PARTITIONS:
        errs.append("partition must be work, personal or shared")
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
        errs += _research(fm, body)
    else:
        errs.append("kind must be plan or research")
    return errs


def _plan(vault, fm: dict) -> list:
    repo, base, plan = fm.get("repo", ""), fm.get("base", ""), fm.get("plan", "")
    src = source(vault, repo)
    if src is None:
        return [f"repo {repo!r} is not a registered codebase or 'template'"]
    errs = []
    if repo != "template" and not (codebase(vault, repo) or {}).get("nightshift_pr"):
        errs.append(f"codebase {repo} has no nightshift_pr (github:<owner>/<repo> or bitbucket-link)")
    if repo == "template" and not config(vault).get("template_remote"):
        errs.append("config has no template_remote")
    if not fm.get("verify"):
        errs.append("verify needs at least one command")
    if not base or git(src, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode:
        return errs + [f"base {base or '(empty)'} does not resolve in {src}"]
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


def _research(fm: dict, body: str) -> list:
    errs = [f"the brief needs a '{h}' section" for h in SECTIONS if h not in body]
    out, part = str(fm.get("output") or ""), fm.get("partition")
    if not (out.startswith(f"wiki/{part}/") and out.endswith(".md")):
        errs.append(f"output must be a note path under wiki/{part}/")
    errs += [f"host {h!r} is not a plain host name" for h in fm.get("hosts") or [] if not HOST.match(str(h))]
    return errs
