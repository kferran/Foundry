# Work Orders on LFS Codebases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Research copies and verify checkouts of a codebase that keeps files in Git LFS check out with the files' content instead of failing the smudge (#83).

**Architecture:** One helper, `nightshift_check.lfs_store(src)`, names the live clone's LFS store (`<git common dir>/lfs`). `_research_code`'s two checkouts and `verify_sha`'s checkout pass it as `-c lfs.storage=<store>` for that command only, so no copy's config links to the live clone.

**Tech Stack:** Python 3 (`vaultlib`), git 2.39, git-lfs 3.3, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-lfs-clones-design.md`

## Global Constraints

- Work on branch `fix/lfs-clones`. Commit there; do not push or open a pull request.
- New prose follows the Writing rules in `CLAUDE.md`. Template rule: no employer, client, codebase or people names.
- Run the suites from the repository root with `TMPDIR=$PWD/.scratch/tmp GIT_CEILING_DIRECTORIES=$PWD/.scratch` (`mkdir -p .scratch/tmp` once), outside a sandbox (the verify test needs `bwrap`). The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: pytest (`test_nightshift_run.py`, `test_nightshift_deliver.py`, `test_nightshift_check.py`) and the gate. The two new tests are skipped where git-lfs (or, for the verify test, bwrap) is not installed; the red count below assumes both are.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.

## Review Focus

- The copy's config gains no `lfs.storage` key, so a research session cannot reach the live clone through it (#77): `test_research_copy_of_an_lfs_codebase_holds_the_files`.
- A resumed research attempt checks the copy out again with the same store: the same test.
- The tests change only a temporary `HOME`, never the user's git config: `lfs_repo`.
- A template item passes no store: `nc.lfs_store(None)` returns `""`.
- Existing `verify_sha` stubs (`lambda *a`) still work: `_deliver_plan` passes the store positionally.

---

### Task 1: LFS files in research copies and verify checkouts

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py`, `system/scripts/vaultlib/nightshift_run.py`, `system/scripts/vaultlib/nightshift_deliver.py`
- Test: `system/tests/python/test_nightshift_deliver.py`, `system/tests/python/test_nightshift_run.py`

**Interfaces:**
- Produces: `nightshift_check.lfs_store(src) -> str` (`""` for `None` or a path that is not a git repository); `nightshift_deliver.verify_sha(runner_repo, sha, vdir, cmds, log_path, lfs_store="")`; the test helper `test_nightshift_deliver.lfs_repo(path, monkeypatch) -> Path`.

- [ ] **Step 1: Write the tests**

Edit 1 in `system/tests/python/test_nightshift_deliver.py`. Find:

````text
    return path
````

Replace with:

````text
    return path


LFS = pytest.mark.skipif(not shutil.which("git-lfs"), reason="git-lfs not installed")


def lfs_repo(path: Path, monkeypatch) -> Path:
    """A repository whose a.png is in Git LFS, under a temporary HOME so the user's git config is untouched (#83)."""
    home = path.parent / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    subprocess.run(["git", "lfs", "install", "--skip-repo"], check=True, capture_output=True)
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "master")
    git(path, "lfs", "track", "*.png")
    (path / "a.png").write_bytes(b"PNGDATA\n")
    git(path, "add", ".")
    git(path, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "a")
    return path


@LFS
@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_verify_reads_lfs_files_from_the_live_clone(tmp_path, monkeypatch):
    src = lfs_repo(tmp_path / "src", monkeypatch)
    sha = git(src, "rev-parse", "HEAD").strip()
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "master") == (True, sha)
    ok, out = nd.verify_sha(runner, sha, tmp_path / "vdir", ["grep -q PNGDATA a.png"], tmp_path / "v.log",
                            lfs_store=str(src / ".git" / "lfs"))
    assert ok, out
````


Edit 1 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert (code / "app.py").read_text() == "print(1)\n"


````

Replace with:

````text
    assert (code / "app.py").read_text() == "print(1)\n"


@pytest.mark.skipif(not shutil.which("git-lfs"), reason="git-lfs not installed")
def test_research_copy_of_an_lfs_codebase_holds_the_files(env, tmp_path, monkeypatch):
    vault, _ = env
    from test_nightshift_deliver import lfs_repo
    src = lfs_repo(tmp_path / "cb" / "shop", monkeypatch)
    git(src, "update-ref", "refs/remotes/origin/HEAD", "HEAD")   # research reads the remote's default branch
    write(vault, "system/codebases/shop.md", f'---\ntype: codebase\nname: "shop"\npath: "{src}"\npartition: "work"\n'
          'search_globs: ["*"]\n---\n')
    ctx = nr.Ctx(vault, NOW)
    fm = {"id": "2026-10-09-q", "kind": "research", "partition": "work", "repo": "shop"}
    code = nr._research_dir(ctx, fm) / "code"
    assert (code / "a.png").read_bytes() == b"PNGDATA\n"
    assert "lfs.storage" not in git(code, "config", "--list", "--local")   # no link to the live clone (#77)
    (code / "a.png").unlink()   # a resumed attempt checks the copy out again
    assert (nr._research_dir(ctx, fm) / "code" / "a.png").read_bytes() == b"PNGDATA\n"


````


- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m pytest -q system/tests/python/test_nightshift_run.py system/tests/python/test_nightshift_deliver.py -k lfs`
Expected: FAIL, 2 failed (the research copy with `smudge filter lfs failed`; `verify_sha` with an unexpected keyword argument `lfs_store`).

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
````

Replace with:

````text
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def lfs_store(src) -> str:
    """The live clone's Git LFS object store, which the runner's own checkouts read (#83), or ""."""
    d = git(src, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip() if src else ""
    return f"{d}/lfs" if d else ""
````


Edit 1 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    if sha and code.is_dir() and nc.git(code, "checkout", "-q", "-f", "--detach", sha).returncode == 0:
        return
    shutil.rmtree(code, ignore_errors=True)   # half-built by a killed tick, or never built
    repo, base = fm["repo"], fm.get("base")
````

Replace with:

````text
    repo, base = fm["repo"], fm.get("base")
    src = None if repo == "template" else nc.source(ctx.vault, repo)
    # LFS files come from the live clone's store for the checkout only: the copy keeps no link to it (#83).
    lfs = ["-c", f"lfs.storage={store}"] if (store := nc.lfs_store(src)) else []
    if sha and code.is_dir() and nc.git(code, *lfs, "checkout", "-q", "-f", "--detach", sha).returncode == 0:
        return
    shutil.rmtree(code, ignore_errors=True)   # half-built by a killed tick, or never built
````

Edit 2 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        src = nc.source(ctx.vault, repo)
````

Replace with:

````text
````

Edit 3 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        r = nc.git(code, "checkout", "-q", "--detach", "refs/remotes/base")
````

Replace with:

````text
        r = nc.git(code, *lfs, "checkout", "-q", "--detach", "refs/remotes/base")
````

Edit 4 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
                            idir / "verify.log")
````

Replace with:

````text
                            idir / "verify.log", nc.lfs_store(None if fm["repo"] == "template" else src))
````


Edit 1 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
def verify_sha(runner_repo, sha: str, vdir, cmds, log_path) -> tuple:
    """Run the verify commands on a private checkout of sha, so nothing they do reaches the commit that is pushed."""
    vdir = Path(vdir)
    shutil.rmtree(vdir, ignore_errors=True)
````

Replace with:

````text
def verify_sha(runner_repo, sha: str, vdir, cmds, log_path, lfs_store: str = "") -> tuple:
    """Run the verify commands on a private checkout of sha, so nothing they do reaches the commit that is pushed.
    LFS files come from lfs_store, the live clone's store (#83): the runner's repository holds none."""
    vdir = Path(vdir)
    shutil.rmtree(vdir, ignore_errors=True)
    lfs = ["-c", f"lfs.storage={lfs_store}"] if lfs_store else []
````

Edit 2 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
        subprocess.run(["git", "-C", str(vdir), "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", sha],
````

Replace with:

````text
        subprocess.run(["git", "-C", str(vdir), "-c", "advice.detachedHead=false", *lfs, "checkout", "-q", "--detach", sha],
````


- [ ] **Step 4: Run the tests and the gate**

Run: `python3 -m pytest -q system/tests/python/test_nightshift_run.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_check.py`
Expected: PASS, 0 failed.

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
fix(orders): research copies and verify checkouts read LFS files (#83)

A research copy (git init and fetch) and the verify checkout (a clone of
the runner's repository) have no LFS objects, so the smudge failed on a
codebase that keeps files in Git LFS. Both checkouts now read the live
clone's LFS store for that one command (-c lfs.storage); nothing is
written to the copy's config, so it keeps no link to the live clone.

Closes #83
```

Run: `git add system/scripts/vaultlib/nightshift_check.py system/scripts/vaultlib/nightshift_deliver.py system/scripts/vaultlib/nightshift_run.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_run.py`

Run: `git commit -q -F .scratch/msg-1.txt`
