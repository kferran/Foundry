"""Containment, sandboxed verify, push, pull request and research publishing (Nightshift spec §3.3)."""
import json
import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import frontmatter
from . import nightshift_check as nc
from . import held
from . import publish
from . import schema
from .intake import Intake

CODE_PATHS = ["system/scripts", "system/schemas", "system/systemd", "system/hooks", "system/nightshift", ".claude",
              "CLAUDE.md"]
LINK = re.compile(r"https://bitbucket\.org/\S+/pull-requests/new\?\S+")


def protected_refs(repo) -> dict:
    r = nc.git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads/master", "refs/heads/main")
    return dict(line.split() for line in r.stdout.splitlines() if line.strip())


def code_status(vault) -> str:
    return nc.git(vault, "status", "--porcelain", "--", *CODE_PATHS).stdout


def bwrap(workdir, cmd: str, toolchain=(), net=False, corepack_home=None) -> list:
    """Run cmd with the host read-only, $HOME and /tmp empty, an empty environment, and only workdir writable.
    The toolchain directories (a codebase's order_toolchain) are bound read-only after the $HOME tmpfs, so they
    alone show through it, and lead PATH. The network is unshared unless net (the order_install step).
    corepack_home becomes COREPACK_HOME, writable only with net, so the install's corepack download is what the
    offline verify runs (#189)."""
    home = str(Path.home())
    dirs = [str(d) for d in toolchain]
    argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--tmpfs", home]
    for d in dirs:
        argv += ["--ro-bind", d, d]
    argv += ["--bind", str(workdir), str(workdir)] + ([] if net else ["--unshare-net"])
    env = []
    if corepack_home:
        argv += ["--bind" if net else "--ro-bind", str(corepack_home), str(corepack_home)]
        env = ["--setenv", "COREPACK_HOME", str(corepack_home), "--setenv", "COREPACK_ENABLE_DOWNLOAD_PROMPT", "0"]
    return argv + ["--die-with-parent", "--clearenv", "--setenv", "PATH", ":".join(dirs + ["/usr/local/bin", "/usr/bin", "/bin"]),
                   "--setenv", "HOME", home, "--setenv", "LANG", "C.UTF-8", "--setenv", "TMPDIR", "/tmp", *env,
                   "--chdir", str(workdir), "bash", "-c", cmd]


def run_verify(clone, cmds, log_path, timeout=1800, toolchain=(), net=False, label="", corepack_home=None) -> tuple:
    with open(log_path, "a", encoding="utf-8") as log:
        for cmd in cmds:
            try:
                r = subprocess.run(bwrap(clone, cmd, toolchain, net, corepack_home=corepack_home), capture_output=True,
                                   text=True, timeout=timeout)
                code, text = r.returncode, r.stdout + r.stderr
            except subprocess.TimeoutExpired:
                code, text = 124, f"timed out after {timeout}s"
            log.write(f"$ {cmd}\n{text}\n[exit {code}]\n")
            if code != 0:
                # 127: the sandbox's PATH is the order_toolchain directories then /usr/local/bin:/usr/bin:/bin,
                # and the rest of $HOME is empty (#138)
                why = " (command not found in the sealed verify sandbox)" if code == 127 else ""
                return False, f"{label}{cmd}: exit {code}{why}\n" + "\n".join(text.splitlines()[-20:])
    return True, ""


def run_install(clone, cmd: str, toolchain, log_path, corepack_home=None) -> tuple:
    """A codebase's order_install, once, with the host network: the only sandboxed step that has it."""
    return run_verify(clone, [cmd], log_path, toolchain=toolchain, net=True, label="order_install: ",
                      corepack_home=corepack_home)


def push_target(vault, fm: dict) -> tuple:
    if fm.get("repo") == "template":
        url = str(nc.config(vault).get("template_remote") or "")
        m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(\.git)?$", url)
        return url, (f"github:{m.group(1)}" if m else "")
    url = nc.git(nc.source(vault, fm["repo"]), "remote", "get-url", "origin").stdout.strip()
    return url, str(nc.setting(nc.codebase(vault, fm["repo"]) or {}, "order_pr", "nightshift_pr") or "")


def _git_env() -> dict:
    return dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")


def fetch_branch(runner_repo, clone, branch: str) -> tuple:
    """Copy the session's branch into the runner's repository and return (True, its tip) or (False, reason).
    The tip is read in the runner's repository: the only git process that touches the session-writable clone is
    upload-pack, which ignores the clone's dangerous config and hooks (git-upload-pack(1), SECURITY)."""
    runner_repo = Path(runner_repo)
    if not (runner_repo / "HEAD").exists():
        subprocess.run(["git", "init", "-q", "--bare", str(runner_repo)], check=True)
    ref = f"refs/heads/{branch}"
    f = subprocess.run(["git", "-C", str(runner_repo), "fetch", "-q", "--no-tags", str(clone), f"+{ref}:{ref}"],
                       capture_output=True, text=True, env=_git_env())
    if f.returncode:
        return False, f.stderr.strip() or f"fetch failed (exit {f.returncode})"
    tip = subprocess.run(["git", "-C", str(runner_repo), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                         capture_output=True, text=True, env=_git_env()).stdout.strip()
    return (True, tip) if tip else (False, f"{ref} is not a commit")


PROTECTED_DIRS = (".claude/skills/", ".claude/commands/", ".claude/agents/")
PROTECTED_MAX = 256 * 1024


def protected_files(clone) -> tuple:
    """Files the session proposed under .nightshift/protected/ for paths it cannot write (.claude/).
    Returns ([(path, bytes)], [problem]); only regular files under PROTECTED_DIRS are accepted. A session cannot
    write a path with a .claude segment either, so it proposes claude/<path>, read as .claude/<path> (#92)."""
    root = Path(clone) / ".nightshift" / "protected"
    files, problems = [], []
    if not root.is_dir():
        return files, problems
    real_root = os.path.realpath(root)
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        rel = "." + rel if rel.startswith("claude/") else rel
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
    env = dict(_git_env(), GIT_INDEX_FILE=str(Path(workdir) / "protected.index"), GIT_AUTHOR_NAME="Work Orders",
               GIT_AUTHOR_EMAIL="orders@localhost", GIT_COMMITTER_NAME="Work Orders",
               GIT_COMMITTER_EMAIL="orders@localhost")

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


def verify_sha(runner_repo, sha: str, vdir, cmds, log_path, lfs_store: str = "", install: str = "", toolchain=()) -> tuple:
    """Run the verify commands on a private checkout of sha, so nothing they do reaches the commit that is pushed.
    LFS files come from lfs_store, the live clone's store (#83): the runner's repository holds none. The codebase's
    order_install runs first when set, then the verify commands offline (orders toolchain spec). vdir holds the
    checkout and, outside it, the corepack home both steps share (orders corepack home spec, #189)."""
    vdir = Path(vdir)
    shutil.rmtree(vdir, ignore_errors=True)
    checkout, corepack = vdir / "checkout", vdir / "corepack"
    lfs = ["-c", f"lfs.storage={lfs_store}"] if lfs_store else []
    try:
        corepack.mkdir(parents=True)
        subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(runner_repo), str(checkout)], check=True,
                       capture_output=True, env=_git_env())
        subprocess.run(["git", "-C", str(checkout), "-c", "advice.detachedHead=false", *lfs, "checkout", "-q", "--detach", sha],
                       check=True, capture_output=True, env=_git_env())
        if install:
            ok, out = run_install(checkout, install, toolchain, log_path, corepack_home=corepack)
            if not ok:
                return ok, out
        return run_verify(checkout, cmds, log_path, toolchain=toolchain, corepack_home=corepack)
    finally:
        shutil.rmtree(vdir, ignore_errors=True)


def push(runner_repo, sha: str, branch: str, url: str) -> tuple:
    if url.startswith("-"):   # git would read it as an option
        return False, f"refused: the remote {url!r} looks like an option"
    opts, env = nc.remote_git(url)
    cmd = ["git", "-C", str(runner_repo), "-c", "core.hooksPath=/dev/null", *opts]
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
    return False, f"unknown order_pr {pr!r}"


WEB = "## Web sources"
SOURCES_KEY = re.compile(r"""^["']?sources["']?\s*:""")


def move_outside_sources(text: str) -> str:
    """Move every frontmatter sources entry that is not a [[wikilink]] into a "## Web sources" body section (#75).
    Only the sources line changes in the frontmatter; a note with nothing to move is returned unchanged."""
    note = frontmatter.parse(text)
    srcs = (note.data or {}).get("sources")
    if note.error or not isinstance(srcs, list):
        return text
    # schema.link_target also reads an unquoted block item "- [[A]]", which YAML parses as [['A']].
    keep = [f"[[{schema.link_target(s)}]]" for s in srcs if schema.link_target(s) is not None]
    moved = [str(s).strip() for s in srcs if schema.link_target(s) is None]
    fm_lines = note.fm_text.split("\n")
    i = next((n for n, line in enumerate(fm_lines) if SOURCES_KEY.match(line)), None)
    if not moved or i is None:
        return text
    j = i + 1
    while j < len(fm_lines) and fm_lines[j][:1] in (" ", "\t", "-"):   # a block list's items
        j += 1
    fm_lines[i:j] = ["sources: " + json.dumps(keep, ensure_ascii=False)]
    body = note.body.rstrip("\n").split("\n")
    if WEB in body:
        h = body.index(WEB)
        end = next((k for k in range(h + 1, len(body)) if body[k].startswith("#")), len(body))
        listed = {b[2:].strip() for b in body[h + 1:end] if b.startswith("- ")}
        k = end
        while k > h + 1 and not body[k - 1].strip():
            k -= 1
        body[k:k] = [f"- {s}" for s in moved if s not in listed]
    else:
        body += ["", WEB, ""] + [f"- {s}" for s in moved]
    return "---\n" + "\n".join(fm_lines) + "\n---\n" + "\n".join(body) + "\n"


def publish_research(vault, fm: dict, findings: Path, lock_timeout: float = 600) -> tuple:
    """Publish the findings through the gate under run.lock, as every other publish runs (#298): a recover() running
    beside it would quarantine the run or apply it twice. A lock held past lock_timeout keeps the findings."""
    run_id = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-nightshift-{secrets.token_hex(2)}"
    try:
        with Intake(vault).lock("run.lock", timeout=lock_timeout):
            publish.snapshot(vault, run_id, [fm["output"]])
            dst = publish.staging_dir(vault, run_id) / fm["output"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(move_outside_sources(findings.read_text(encoding="utf-8")), encoding="utf-8")
            report = publish.commit_run(vault, run_id)
    except TimeoutError:
        return False, "run.lock busy: another run is publishing; the findings are kept for a retry"
    except publish.PublishError as exc:
        return False, str(exc)
    if report.get("status") == "published":
        try:
            got = stale_claims_input(vault, fm, findings.read_text(encoding="utf-8"))
        except OSError as exc:  # the findings are published: the item is done either way
            return True, f"{fm['output']} (its stale claims were not held: {exc.__class__.__name__}: {exc})"
        if got:
            try:
                with Intake(vault).lock("run.lock", timeout=60):
                    held.add_line(vault, *got, datetime.now().astimezone().date().isoformat())
            except (TimeoutError, ValueError, OSError) as exc:   # intake's Now step adds it on a later tick
                return True, f"{fm['output']} (its stale claims are held without a Now line yet: {exc})"
        return True, fm["output"]
    return False, f"publish gate: {report.get('status')}: {report.get('problems') or report.get('conflicts')}"


STALE = "## Stale claims"


def stale_claims_input(vault, fm: dict, text: str):
    """Hold a findings note's Stale claims as a one-section session digest in raw/<p>/held/ (#85; confinement spec
    §3.7: ingest takes it only after the owner ticks its Now line). (path, number of claims), or None when there are none
    or this Work Order's file already exists."""
    body = frontmatter.parse(text).body.split("\n")
    if STALE not in body:
        return None
    start = body.index(STALE) + 1
    end = next((k for k in range(start, len(body)) if body[k].startswith("#")), len(body))
    bullets = [line for line in body[start:end] if line.startswith("- ")]
    if not bullets:
        return None
    name = f"{fm['id']}.stale-claims"
    raw = Path(vault) / "raw" / fm["partition"]
    for folder in (raw / "held", raw / "notes", raw / "archive", Path(vault) / "system" / "quarantine" / "poisoned"):
        if folder.is_dir() and any(p.name.startswith(name) for p in folder.iterdir()):
            return None  # a second delivery of the same Work Order: it is held, released or compiled already
    path = raw / "held" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    # provenance headless: the bullets come from a session that read untrusted sources (ingest patches only).
    tmp.write_text(f'---\ntype: session_digest\npartition: {fm["partition"]}\ncodebase: {json.dumps(fm.get("repo") or "vault")}\n'
                   f'session_id: "order-{fm["id"]}"\ncreated_at: "{datetime.now().astimezone().isoformat(timespec="seconds")}"\n'
                   f'work_order: "{fm["id"]}"\nprovenance: ["headless"]\n---\n{STALE}\n' + "\n".join(bullets) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return path, len(bullets)
