# Nightshift Research Sources and Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A research findings note is never rejected for a web page or code path in `sources:` (#75), and a research item can read a pinned copy of a repository under `code/` (#77).

**Architecture:** The research prompt states the `sources:` rule, and delivery moves every non-wikilink entry into a `## Web sources` section before staging. A research item may carry `repo` and `base`; the check resolves them, the run builds `code/` once at that commit and reuses it on resume, and the prompt names the repository and commit.

**Tech Stack:** Python 3, pytest, git.

**Spec:** `docs/superpowers/specs/2026-10-08-research-sources-design.md`

## Global Constraints

- Work on branch `fix/research-sources` of `kferran/Foundry`. Commit there; do not push or open a pull request.
- New prose follows the Writing rules in `CLAUDE.md`. Nothing names a specific vault, organization or person.
- Run the suites from the repository root as `TMPDIR=$PWD/.scratch/tmp python3 -m pytest -q <files>` (`mkdir -p .scratch/tmp` once). The gate is `system/scripts/verify_setup.sh`. Never run two gates at once.
- Bound tools: pytest (`test_nightshift_deliver.py`, `test_nightshift_session.py`, `test_nightshift_check.py`, `test_nightshift_run.py` under `system/tests/python/`) and the gate.
- Commits use `git commit -F .scratch/<file>`.
- Every "Find" text below occurs exactly once in its file at that step.
- Ruling against spec §2.2: the commit is pinned by keeping the complete `code/` folder across attempts (a resumed attempt reuses it), and the prompt reads the commit from `code/` itself. No separate record file in the run directory. (Reversed by the final review's fix pass: `code/` is one fetched commit, recorded in the run directory as the spec says, and checked out again on resume.)

## Review Focus

- A findings note with a URL in `sources:` publishes, with the URL listed under `## Web sources`: the `publish_research` test.
- A resumed research attempt reads the same commit after the registered clone's `origin` moves: the pinned-copy test.
- A research item's own registered checkout stays in the deny list, so the session reads only `code/`: the same test.
- A template base missing from the template remote is refused at queue time with "push it first": the check test.
- A research item with no `repo` gets no `code/` and a prompt that never mentions it: the template/no-repo test and the session test.

---

### Task 1: Sources outside the vault go in the body (#75)

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_deliver.py`, `system/scripts/vaultlib/nightshift_session.py`
- Test: `system/tests/python/test_nightshift_deliver.py`, `system/tests/python/test_nightshift_session.py`

**Interfaces:**
- Produces: `nightshift_deliver.move_outside_sources(text: str) -> str`; `research_prompt` text names the `## Web sources` rule.

- [ ] **Step 1: Write the failing tests**

Edit 1 in `system/tests/python/test_nightshift_deliver.py`. Find:

````text
    assert (vault / "wiki/work/concepts/A.md").is_file()


````

Replace with:

````text
    assert (vault / "wiki/work/concepts/A.md").is_file()


MIXED = ('---\ntype: concept\ntags: ["research"]\ncompiled_at: 2026-10-08\npartition: work\nprovenance: ["headless"]\n'
         'sources: ["[[Alpha]]", "https://example.com/a", "[[Beta]]", "src/app/main.py"]\nstatus: draft\n---\n'
         '# Answer\n\nFound it.\n')


def test_move_outside_sources_keeps_wikilinks_and_lists_the_rest():
    out = nd.move_outside_sources(MIXED)
    assert 'sources: ["[[Alpha]]", "[[Beta]]"]\n' in out
    assert out.startswith('---\ntype: concept\ntags: ["research"]\ncompiled_at: 2026-10-08\npartition: work\n')
    assert "status: draft\n---\n# Answer\n\nFound it.\n" in out
    assert out.endswith("## Web sources\n\n- https://example.com/a\n- src/app/main.py\n")


def test_move_outside_sources_adds_only_new_entries_to_an_existing_section():
    text = MIXED.replace("Found it.\n", "Found it.\n\n## Web sources\n\n- https://example.com/a\n")
    out = nd.move_outside_sources(text)
    assert out.count("https://example.com/a") == 1
    assert out.endswith("## Web sources\n\n- https://example.com/a\n- src/app/main.py\n")


@pytest.mark.parametrize("text", [
    MIXED.replace('"https://example.com/a", ', "").replace(', "src/app/main.py"', ""),   # only wikilinks
    MIXED.replace('sources: ["[[Alpha]]", "https://example.com/a", "[[Beta]]", "src/app/main.py"]\n', ""),   # none
    "# No frontmatter\n\nhttps://example.com/a\n"])
def test_move_outside_sources_leaves_other_notes_unchanged(text):
    assert nd.move_outside_sources(text) == text


def test_research_with_a_url_in_sources_publishes_with_the_url_in_its_body(vault: Path, tmp_path):
    findings = tmp_path / "C.md"
    findings.write_text(concept("work", "Answer", "Found it.", provenance='["headless"]',
                                sources='["https://example.com/a"]'))
    ok, detail = nd.publish_research(vault, {"output": "wiki/work/concepts/C.md", "partition": "work"}, findings)
    assert ok, detail
    note = (vault / "wiki/work/concepts/C.md").read_text()
    assert "sources: []" in note and "- https://example.com/a" in note


````


Edit 1 in `system/tests/python/test_nightshift_session.py`. Find:

````text
    assert "context/" in ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")


````

Replace with:

````text
    assert "context/" in ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")


def test_research_prompt_keeps_sources_to_wikilinks():
    p = ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")
    assert "sources lists only vault notes, as wikilinks ([[Note]])" in p
    assert "## Web sources" in p


````


- [ ] **Step 2: Run them to verify they fail**

Run: the pytest command from Global Constraints with `system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_session.py`.
Expected: FAIL, 7 failed (`move_outside_sources` does not exist yet; the prompt has no `## Web sources` rule).

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
"""Containment, sandboxed verify, push, pull request and research publishing (Nightshift spec §3.3)."""
````

Replace with:

````text
"""Containment, sandboxed verify, push, pull request and research publishing (Nightshift spec §3.3)."""
import json
````

Edit 2 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
from pathlib import Path

````

Replace with:

````text
from pathlib import Path

from . import frontmatter
````

Edit 3 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
    return False, f"unknown nightshift_pr {pr!r}"


````

Replace with:

````text
    return False, f"unknown nightshift_pr {pr!r}"


WIKILINK = re.compile(r"^\[\[[^\[\]]+\]\]$")
WEB = "## Web sources"


def move_outside_sources(text: str) -> str:
    """Move every frontmatter sources entry that is not a [[wikilink]] into a "## Web sources" body section (#75).
    Only the sources line changes in the frontmatter; a note with nothing to move is returned unchanged."""
    note = frontmatter.parse(text)
    srcs = (note.data or {}).get("sources")
    if note.error or not isinstance(srcs, list):
        return text
    keep = [str(s) for s in srcs if WIKILINK.match(str(s).strip())]
    moved = [str(s).strip() for s in srcs if not WIKILINK.match(str(s).strip())]
    if not moved:
        return text
    fm_lines = note.fm_text.split("\n")
    i = next(n for n, line in enumerate(fm_lines) if line.startswith("sources:"))
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


````

Edit 4 in `system/scripts/vaultlib/nightshift_deliver.py`. Find:

````text
        shutil.copyfile(findings, dst)
````

Replace with:

````text
        dst.write_text(move_outside_sources(findings.read_text(encoding="utf-8")), encoding="utf-8")
````


Edit 1 in `system/scripts/vaultlib/nightshift_session.py`. Find:

````text
            "concept, tags, compiled_at (today), partition, provenance [\"headless\"] and sources; then the findings, "
````

Replace with:

````text
            "concept, tags, compiled_at (today), partition, provenance [\"headless\"] and sources (sources lists only vault "
            "notes, as wikilinks ([[Note]]); list web pages and code paths under a ## Web sources heading at the end of "
            "the body); then the findings, "
````


- [ ] **Step 4: Run the tests to verify they pass**

Run: the same command.
Expected: PASS, 0 failed.

- [ ] **Step 5: Commit**

Write `.scratch/msg-1.txt`:

```text
fix(nightshift): research keeps sources outside the vault in the body

The research prompt says sources: lists vault wikilinks only. Delivery
moves any other entry into a "## Web sources" section before the
publish gate, changing only the sources line of the frontmatter, so a
findings note is never rejected for a URL in sources.

Closes #75

Claude-Session: https://claude.ai/code/session_01647fUGoWRjf3w7UNpdzKpF
```

Run: `git add system/scripts/vaultlib/nightshift_deliver.py system/scripts/vaultlib/nightshift_session.py system/tests/python/test_nightshift_deliver.py system/tests/python/test_nightshift_session.py`

Run: `git commit -q -F .scratch/msg-1.txt`

### Task 2: Research reads a pinned copy of a repository (#77)

**Files:**
- Modify: `system/scripts/vaultlib/nightshift_check.py`, `system/scripts/vaultlib/nightshift_run.py`, `system/scripts/vaultlib/nightshift_session.py`, `.claude/skills/nightshift/SKILL.md`
- Test: `system/tests/python/test_nightshift_check.py`, `system/tests/python/test_nightshift_run.py`, `system/tests/python/test_nightshift_session.py`

**Interfaces:**
- Consumes: `research_prompt(fm, body)` from Task 1 (its text).
- Produces: `nightshift_check.research_base(src, base) -> str` (a commit, or `""`); `nightshift_check.fetch_base` fetches the remote's `HEAD` when `base` is empty; `nightshift_run._research_code(ctx, fm, code)` raises `CloneError`; `research_prompt(fm, body, code: str | None = None)`; `MAX_TURNS["research"] == "300"`.

- [ ] **Step 1: Write the failing tests**

Edit 1 in `system/tests/python/test_nightshift_check.py`. Find:

````text
    assert nc.shown("https://user:tok@github.com/o/r.git") == "https://github.com/o/r.git"


````

Replace with:

````text
    assert nc.shown("https://user:tok@github.com/o/r.git") == "https://github.com/o/r.git"


def registered(vault: Path, tmp_path: Path, name: str = "shop") -> Path:
    """A registered codebase whose clone has origin/HEAD, like a real checkout."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    seed = tmp_path / f"{name}-seed"
    git(tmp_path, "init", "-q", "-b", "main", str(seed))
    write(seed, "app.py", "print(1)\n")
    git(seed, "add", "app.py")
    git(seed, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "first")
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(tmp_path / f"{name}.git"))
    clone = tmp_path / name
    git(tmp_path, "clone", "-q", str(tmp_path / f"{name}.git"), str(clone))
    write(vault, f"system/codebases/{name}.md", f'---\ntype: codebase\nname: "{name}"\npath: "{clone}"\npartition: "work"\n'
          'search_globs: ["*"]\n---\n')
    return clone


def test_research_may_name_a_repository_and_commit(vault_repo, tmp_path):
    registered(vault_repo, tmp_path)
    fm = plan_fm(kind="research", output="wiki/work/concepts/Answer.md", repo="shop", base=None)
    fm.pop("base")
    assert nc.check(vault_repo, fm, BRIEF) == []
    assert any("base nope" in e for e in nc.check(vault_repo, {**fm, "base": "nope"}, BRIEF))
    assert any("ghost" in e for e in nc.check(vault_repo, {**fm, "repo": "ghost"}, BRIEF))
    assert nc.check(vault_repo, {**fm, "repo": "template", "base": "feat/x"}, BRIEF) == []
    assert any("push it first" in e for e in nc.check(vault_repo, {**fm, "repo": "template", "base": "gone"}, BRIEF))


````


Edit 1 in `system/tests/python/test_nightshift_run.py`. Find:

````text
    assert "--add-dir" not in (tmp_path / "args.txt").read_text()


````

Replace with:

````text
    assert "--add-dir" not in (tmp_path / "args.txt").read_text()


def test_research_reads_a_pinned_copy_of_its_codebase(env, tmp_path):
    vault, tmp = env
    from test_nightshift_check import registered
    clone = registered(vault, tmp_path / "cb")
    fm = {"id": "2026-10-08-q", "kind": "research", "partition": "work", "repo": "shop"}
    ctx = nr.Ctx(vault, NOW)
    first = git(clone, "rev-parse", "origin/HEAD").strip()
    d = nr._research_dir(ctx, fm)
    assert git(d / "code", "rev-parse", "HEAD").strip() == first
    assert (d / "code" / "app.py").is_file()
    seed = tmp_path / "cb" / "shop-seed"   # a later commit reaches the registered clone's origin/HEAD
    write(seed, "later.py", "x\n")
    git(seed, "add", "later.py")
    git(seed, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "later")
    git(seed, "push", "-q", str(tmp_path / "cb" / "shop.git"), "main")
    git(clone, "fetch", "-q")
    d = nr._research_dir(ctx, fm)   # a resumed attempt reads the same commit
    assert git(d / "code", "rev-parse", "HEAD").strip() == first
    assert not (d / "code" / "later.py").exists()
    assert str(clone) in nr._deny(ctx, fm)   # the live checkout stays denied


def test_research_reads_the_template_from_its_remote_and_needs_no_code_without_a_repo(env):
    vault, tmp = env
    ctx = nr.Ctx(vault, NOW)
    d = nr._research_dir(ctx, {"id": "2026-10-08-t", "kind": "research", "partition": "work", "repo": "template",
                               "base": "feat/x"})
    assert git(d / "code", "rev-parse", "HEAD").strip() == git(tmp / "remote.git", "rev-parse", "feat/x").strip()
    d = nr._research_dir(ctx, {"id": "2026-10-08-n", "kind": "research", "partition": "work"})
    assert not (d / "code").exists()


````


Edit 1 in `system/tests/python/test_nightshift_session.py`. Find:

````text
    assert "context/" in ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")


````

Replace with:

````text
    assert "context/" in ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")


def test_research_reads_code_and_gets_more_turns():
    assert ss.MAX_TURNS["research"] == "300"
    p = ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ", code="shop at 1a2b3c4 (2026-10-01)")
    assert "code/ is a read-only copy of shop at 1a2b3c4 (2026-10-01)" in p
    assert "code/" not in ss.research_prompt({"output": "wiki/work/concepts/A.md"}, "## Question\nQ")


````


- [ ] **Step 2: Run them to verify they fail**

Run: the pytest command from Global Constraints with `system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py system/tests/python/test_nightshift_session.py`.
Expected: FAIL, 4 failed: `test_research_may_name_a_repository_and_commit` (repo is not checked), `test_research_reads_a_pinned_copy_of_its_codebase` and `test_research_reads_the_template_from_its_remote_and_needs_no_code_without_a_repo` (no `code/`), `test_research_reads_code_and_gets_more_turns` (120 turns, no `code` argument).

- [ ] **Step 3: Implement**

Edit 1 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
def fetch_base(repo, url: str, base: str, dest: str, depth: int | None = None, timeout: int = 600):
    """Fetch refs/heads/<base> from url into repo as dest. A URL that starts with "-" is refused: git reads it as an option."""
````

Replace with:

````text
def fetch_base(repo, url: str, base: str | None, dest: str, depth: int | None = None, timeout: int = 600):
    """Fetch refs/heads/<base> (the remote's HEAD when base is empty) from url into repo as dest. A URL that starts
    with "-" is refused: git reads it as an option."""
````

Edit 2 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
           url, f"refs/heads/{base}:{dest}"]
````

Replace with:

````text
           url, f"{f'refs/heads/{base}' if base else 'HEAD'}:{dest}"]
````

Edit 3 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
        errs += _research(fm, body)
````

Replace with:

````text
        errs += _research(vault, fm, body)
````

Edit 4 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
def _research(fm: dict, body: str) -> list:
````

Replace with:

````text
def _research(vault, fm: dict, body: str) -> list:
````

Edit 5 in `system/scripts/vaultlib/nightshift_check.py`. Find:

````text
    errs += [f"host {h!r} is not a plain host name" for h in fm.get("hosts") or [] if not HOST.match(str(h))]
    return errs
````

Replace with:

````text
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
````


Edit 1 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    return d
````

Replace with:

````text
    if fm.get("repo"):
        _research_code(ctx, fm, d / "code")
    return d


def _research_code(ctx: Ctx, fm: dict, code: Path) -> None:
    """A read-only copy of the item's repository at one commit (#77). A complete copy is kept, so a resumed
    attempt reads the commit the first attempt read."""
    if code.exists():
        if nc.git(code, "rev-parse", "--verify", "--quiet", "HEAD").returncode == 0:
            return
        shutil.rmtree(code)   # half-built by a killed tick
    repo, base = fm["repo"], fm.get("base")
    if repo == "template":   # from the template remote, never the vault
        url = str(nc.config(ctx.vault).get("template_remote") or "")
        subprocess.run(["git", "init", "-q", str(code)], check=True)
        try:
            f = nc.fetch_base(code, url, base, "refs/remotes/base", depth=1)
        except ValueError as exc:
            f = subprocess.CompletedProcess([], 2, "", str(exc))
        why, sha = (f.stderr.strip().splitlines() or ["no error text"])[-1], "refs/remotes/base"
        where = f"fetch {base or 'HEAD'} from {nc.shown(url)}"
    else:
        src = nc.source(ctx.vault, repo)
        sha = nc.research_base(src, base) if src else ""
        f = subprocess.run(["git", "clone", "-q", "--local", "--no-checkout", str(src), str(code)],
                           capture_output=True, text=True) if sha else subprocess.CompletedProcess([], 2, "", "")
        why, where = (f.stderr.strip().splitlines() or ["does not resolve"])[-1], f"{base or 'origin/HEAD'} in {src}"
    if f.returncode or nc.git(code, "checkout", "-q", "--detach", sha).returncode:
        shutil.rmtree(code, ignore_errors=True)   # the next attempt starts again
        raise CloneError(f"{where}: {why}")
````

Edit 2 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    own = nc.source(ctx.vault, fm.get("repo")) if fm.get("repo") not in (None, "template") else None
````

Replace with:

````text
    # A plan item works in its own codebase; a research item reads code/, so even its own checkout stays denied.
    own = nc.source(ctx.vault, fm.get("repo")) if fm.get("kind") == "plan" and fm.get("repo") != "template" else None
````

Edit 3 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
    prompt = (ss.plan_prompt(fm) if kind == "plan" else ss.research_prompt(fm, body))
````

Replace with:

````text
    code = nc.git(cwd / "code", "log", "-1", "--format=%h (%cs)").stdout.strip() if kind == "research" and fm.get("repo") else ""
    prompt = (ss.plan_prompt(fm) if kind == "plan" else
              ss.research_prompt(fm, body, code=f"{fm['repo']} at {code}" if code else None))
````

Edit 4 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        cwd = _research_dir(ctx, fm)
````

Replace with:

````text
        try:
            cwd = _research_dir(ctx, fm)
        except CloneError as exc:
            return _finish(ctx, path, fm, idir, None, {"state": "failed", "reason": "base", "needs": [
                f"Make {fm.get('base') or 'the default branch'} of {fm['repo']} readable, then queue {fm['id']} again ({exc})"]})
````

Edit 5 in `system/scripts/vaultlib/nightshift_run.py`. Find:

````text
        fm.update(output=a.output, hosts=a.host)
````

Replace with:

````text
        fm.update(output=a.output, hosts=a.host, repo=a.repo, base=a.base)
````


Edit 1 in `system/scripts/vaultlib/nightshift_session.py`. Find:

````text
MAX_TURNS = {"plan": "400", "research": "120"}
````

Replace with:

````text
MAX_TURNS = {"plan": "400", "research": "300"}
````

Edit 2 in `system/scripts/vaultlib/nightshift_session.py`. Find:

````text
def research_prompt(fm: dict, body: str) -> str:
    name = Path(fm["output"]).name
    return ("Answer the research brief below from the sources in its Scope; background notes from the vault are under "
            "context/ (a read-only copy). Change nothing except files under out/. "
````

Replace with:

````text
def research_prompt(fm: dict, body: str, code: str | None = None) -> str:
    name = Path(fm["output"]).name
    return ("Answer the research brief below from the sources in its Scope; background notes from the vault are under "
            "context/ (a read-only copy). " + (f"code/ is a read-only copy of {code}. " if code else "") +
            "Change nothing except files under out/. "
````


Edit 1 in `.claude/skills/nightshift/SKILL.md`. Find:

````text
**`/nightshift ask`**: draft the brief with the user, one question at a time, until it has `## Question`, `## Scope` (sources and any web hosts), `## Done when` and `## Output` (the findings note, a path under `wiki/<partition>/`). Save it to a temporary file, then run `nightshift.py add --kind research --title "…" --partition <p> --brief-file <file> --output <path> --host <h> … [--now | --at]`.
````

Replace with:

````text
**`/nightshift ask`**: draft the brief with the user, one question at a time, until it has `## Question`, `## Scope` (sources and any web hosts), `## Done when` and `## Output` (the findings note, a new path under `wiki/<partition>/`; research creates new notes only). When the question is about code, ask which repository (a registered codebase or `template`) and which branch or commit (a branch for `template`); the session reads a pinned copy under `code/`, at the remote's default branch when no base is named. Save the brief to a temporary file, then run `nightshift.py add --kind research --title "…" --partition <p> --brief-file <file> --output <path> --host <h> … [--repo <name> [--base <branch or commit>]] [--now | --at]`.
````


- [ ] **Step 4: Run the tests to verify they pass**

Run: the same command.
Expected: PASS, 0 failed.

- [ ] **Step 5: Run the gate**

Run: `system/scripts/verify_setup.sh`
Expected: exit 0, no `FAIL` in the summary.

- [ ] **Step 6: Commit**

Write `.scratch/msg-2.txt`:

```text
feat(nightshift): research may read a pinned copy of a repository

A research item may name a repo (a registered codebase or template) and a
base. The check resolves it; the run builds code/ at that commit (the
remote's default branch when no base is named) and keeps it across resumed
attempts. The live checkout stays denied. A base that cannot be read fails
the item with a Needs-you line. Research gets 300 turns.

Closes #77

Claude-Session: https://claude.ai/code/session_01647fUGoWRjf3w7UNpdzKpF
```

Run: `git add system/scripts/vaultlib/nightshift_check.py system/scripts/vaultlib/nightshift_run.py system/scripts/vaultlib/nightshift_session.py .claude/skills/nightshift/SKILL.md system/tests/python/test_nightshift_check.py system/tests/python/test_nightshift_run.py system/tests/python/test_nightshift_session.py`

Run: `git commit -q -F .scratch/msg-2.txt`
