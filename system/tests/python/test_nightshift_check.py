import json
import subprocess
from pathlib import Path

import pytest

from helpers import write
from test_nightshift_item import plan_fm
from vaultlib import nightshift_check as nc

PLAN = """# P
### Task 1: Schema
Write it.
### Task 2: Parsers
Write them.
### Task 3: Rollout (vault `master`, after the PR is merged)
Runs in the vault on `master`.
### Task 4: Release
```bash
npm  publish --access public
```
"""
BRIEF = "## Question\nWhat?\n## Scope\nDocs.\n## Done when\nAnswered.\n## Output\nA note.\n"


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


@pytest.fixture
def vault_repo(vault: Path, tmp_path: Path) -> Path:
    git(vault, "init", "-q", "-b", "master")
    write(vault, "docs/p.md", PLAN)
    git(vault, "add", "docs/p.md")
    git(vault, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "plan")
    remote = tmp_path / "remote.git"   # a local bare repository stands in for the template remote
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(vault, "push", "-q", str(remote), "HEAD:refs/heads/feat/x")   # the base exists only on the remote
    write(vault, "system/config.md", f'---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "{remote}"\n---\n')
    return vault


def test_parse_tasks():
    assert nc.parse_tasks("1-3") == {1, 2, 3}
    assert nc.parse_tasks("1,3") == {1, 3}
    assert nc.parse_tasks("") is None
    with pytest.raises(ValueError):
        nc.parse_tasks("three")


def test_task_blocks():
    assert sorted(nc.task_blocks(PLAN)) == [1, 2, 3, 4]


def test_plan_ready_with_range(vault_repo):
    assert nc.check(vault_repo, plan_fm(tasks="1-2"), "") == []


def test_plan_refuses_protected_task_unless_excluded(vault_repo):
    errs = nc.check(vault_repo, plan_fm(tasks=""), "")
    assert any("task 3" in e for e in errs)


def test_plan_errors(vault_repo):
    errs = nc.check(vault_repo, plan_fm(base="nope", tasks="1-2"), "")
    assert any("base nope" in e for e in errs)
    errs = nc.check(vault_repo, plan_fm(tasks="1-9"), "")
    assert any(e.startswith("tasks not in the plan") and e.endswith("9") for e in errs)
    errs = nc.check(vault_repo, plan_fm(tasks="1-2", verify=[]), "")
    assert any("verify" in e for e in errs)
    errs = nc.check(vault_repo, plan_fm(tasks="1-2", repo="ghost"), "")
    assert any("ghost" in e for e in errs)
    errs = nc.check(vault_repo, plan_fm(tasks="1-2", budget="4 hours"), "")
    assert any("budget" in e for e in errs)


def test_a_workspace_inside_the_vault_is_not_ready(vault_repo, tmp_path):
    # audit S3/S7 spec §2: every session denies the vault root, which would cover its own working directory
    cfg = vault_repo / "system/config.md"
    head = cfg.read_text().rsplit("---\n", 1)[0]
    cfg.write_text(head + f'order_workspace: "{vault_repo / ".scratch" / "ws"}"\n---\n')
    assert "order_workspace is inside the vault" in nc.check(vault_repo, plan_fm(tasks="1-2"), "")
    cfg.write_text(head + f'order_workspace: "{tmp_path / "ws"}"\n---\n')
    assert "order_workspace is inside the vault" not in nc.check(vault_repo, plan_fm(tasks="1-2"), "")
    assert nc.workspace({}) == Path("~/code/worktrees").expanduser()


def test_template_base_must_be_on_the_template_remote(vault_repo):
    git(vault_repo, "branch", "only-here")   # in the vault, never pushed
    errs = nc.check(vault_repo, plan_fm(base="only-here", tasks="1-2"), "")
    assert any("base only-here is not on the template remote" in e and "push it first" in e for e in errs)
    assert nc.source(vault_repo, "template") is None


def test_template_without_template_remote_fails_before_any_fetch(vault_repo, monkeypatch):
    monkeypatch.setattr(nc, "fetch_base", lambda *a, **k: pytest.fail("fetched"))
    write(vault_repo, "system/config.md", '---\ntype: config\ntimezone: "UTC"\n---\n')
    assert nc.check(vault_repo, plan_fm(tasks="1-2"), "") == ["config has no template_remote"]


def test_an_unreadable_template_remote_is_not_a_missing_branch(vault_repo, tmp_path):
    write(vault_repo, "system/config.md", f'---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "{tmp_path / "gone.git"}"\n---\n')
    errs = nc.check(vault_repo, plan_fm(tasks="1-2"), "")
    assert any(e.startswith("cannot read the template remote") for e in errs)
    assert not any("push it first" in e for e in errs)


def test_a_template_remote_that_looks_like_an_option_is_refused(vault_repo, monkeypatch):
    monkeypatch.setattr(nc, "fetch_base", lambda *a, **k: pytest.fail("fetched"))
    write(vault_repo, "system/config.md", '---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "--upload-pack=touch x"\n---\n')
    assert nc.check(vault_repo, plan_fm(tasks="1-2"), "") == ["template_remote must be a URL or a path"]


def test_remote_git_uses_gh_credentials_for_github_https_only():
    opts, env = nc.remote_git("https://github.com/o/r.git")
    assert "credential.helper=!gh auth git-credential" in opts and env["GIT_TERMINAL_PROMPT"] == "0"
    assert nc.remote_git("/srv/r.git")[0] == []
    assert nc.shown("https://user:tok@github.com/o/r.git") == "https://github.com/o/r.git"


def registered(vault: Path, tmp_path: Path, name: str = "shop") -> Path:
    """A registered codebase whose clone has origin/HEAD, like a real checkout, with the PLAN committed as docs/p.md."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    seed = tmp_path / f"{name}-seed"
    git(tmp_path, "init", "-q", "-b", "main", str(seed))
    write(seed, "app.py", "print(1)\n")
    write(seed, "docs/p.md", PLAN)
    git(seed, "add", "app.py", "docs/p.md")
    git(seed, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "first")
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(tmp_path / f"{name}.git"))
    clone = tmp_path / name
    git(tmp_path, "clone", "-q", str(tmp_path / f"{name}.git"), str(clone))
    write(vault, f"system/codebases/{name}.md", f'---\ntype: codebase\nname: "{name}"\npath: "{clone}"\npartition: "work"\n'
          'search_globs: ["*"]\n---\n')
    return clone


def set_codebase(vault: Path, name: str, **keys) -> None:
    """Add or replace frontmatter keys in a registered codebase's file (a list value stays a list)."""
    p = vault / "system" / "codebases" / f"{name}.md"
    head, _, rest = p.read_text().rpartition("---\n")
    kept = [line for line in head.splitlines(keepends=True) if line.split(":")[0] not in keys]
    p.write_text("".join(kept) + "".join(f"{k}: {json.dumps(v)}\n" for k, v in keys.items()) + "---\n" + rest)


def test_setting_reads_the_old_key_and_the_new_one_wins():
    assert nc.setting({"nightshift_pr": "a"}, "order_pr", "nightshift_pr") == "a"
    assert nc.setting({"nightshift_pr": "a", "order_pr": "b"}, "order_pr", "nightshift_pr") == "b"
    assert nc.setting({}, "order_pr", "nightshift_pr") is None


def test_a_codebase_plan_needs_order_pr_or_its_old_name(vault_repo, tmp_path):
    registered(vault_repo, tmp_path)
    fm = plan_fm(tasks="1-2", repo="shop", base="main")
    assert any("codebase shop has no order_pr" in e for e in nc.check(vault_repo, fm, ""))
    set_codebase(vault_repo, "shop", nightshift_pr="github:o/shop")
    assert not any("order_pr" in e for e in nc.check(vault_repo, fm, ""))


def test_a_codebase_plan_refuses_a_missing_toolchain_dir_and_a_list_valued_install(vault_repo, tmp_path):
    """Orders toolchain spec §2: readiness stays command-free; it refuses what the sandbox could not bind or run."""
    registered(vault_repo, tmp_path)
    fm = plan_fm(tasks="1-2", repo="shop", base="main")
    tools = tmp_path / "tools"
    tools.mkdir()
    set_codebase(vault_repo, "shop", order_pr="github:o/shop", order_toolchain=[str(tools)], order_install="true")
    assert nc.check(vault_repo, fm, "") == []
    set_codebase(vault_repo, "shop", order_toolchain=[str(tmp_path / "gone")])
    errs = nc.check(vault_repo, fm, "")
    assert any("order_toolchain" in e and str(tmp_path / "gone") in e and "shop" in e for e in errs), errs
    set_codebase(vault_repo, "shop", order_install=["a", "b"])
    errs = nc.check(vault_repo, fm, "")
    assert any("order_install" in e and "shop" in e for e in errs), errs
    set_codebase(vault_repo, "shop", order_install="true", order_toolchain=["system/tests"])   # exists from the vault root
    errs = nc.check(vault_repo, fm, "")
    assert any("order_toolchain system/tests" in e and "absolute" in e for e in errs), errs
    assert nc.toolchain_errors("shop", {"order_toolchain": [str(tools), "rel/bin"]}) == \
        ["codebase shop: order_toolchain rel/bin must be an absolute path (~ allowed)"]
    assert nc.toolchain({"order_toolchain": ["~/x"]})[0].endswith("/x")
    assert not nc.toolchain({"order_toolchain": ["~/x"]})[0].startswith("~")
    assert nc.toolchain({}) == []


def test_research_may_name_a_repository_and_commit(vault_repo, tmp_path):
    registered(vault_repo, tmp_path)
    fm = plan_fm(kind="research", output="wiki/work/concepts/Answer.md", repo="shop", base=None)
    fm.pop("base")
    assert nc.check(vault_repo, fm, BRIEF) == []
    assert any("base nope" in e for e in nc.check(vault_repo, {**fm, "base": "nope"}, BRIEF))
    assert any("ghost" in e for e in nc.check(vault_repo, {**fm, "repo": "ghost"}, BRIEF))
    assert nc.check(vault_repo, {**fm, "repo": "template", "base": "feat/x"}, BRIEF) == []
    assert any("push it first" in e for e in nc.check(vault_repo, {**fm, "repo": "template", "base": "gone"}, BRIEF))


def test_research_brief(vault_repo):
    fm = plan_fm(kind="research", output="wiki/work/concepts/Answer.md", hosts=["www.dtcc.com"])
    assert nc.check(vault_repo, fm, BRIEF) == []
    assert any("## Done when" in e for e in nc.check(vault_repo, fm, BRIEF.replace("## Done when", "## Done")))
    assert any("output" in e for e in nc.check(vault_repo, {**fm, "output": "wiki/personal/x.md"}, BRIEF))
    assert any("host" in e for e in nc.check(vault_repo, {**fm, "hosts": ["http://x"]}, BRIEF))


@pytest.mark.parametrize("text", ["git push origin master", "git checkout master && git merge feat",
                                  "Merge into master.", "commit to the vault's master", "git push -u origin main",
                                  "Runs in the vault on `master`.", "then deploy to production"])
def test_protected_phrasings_are_caught(text):
    assert nc.PROTECTED.search(text)


@pytest.mark.parametrize("text", ["gh pr create --repo o/r --base master --head feat/x",
                                  "Merging the PR is the user's call.", "the main loop runs on startup",
                                  "deployment notes", "git push -u template feat/x"])
def test_ordinary_phrasings_pass(text):
    assert not nc.PROTECTED.search(text)


@pytest.mark.parametrize("text", [*nc.CREDENTIALED, "npm  publish", "Docker PUSH img", "aws s3 cp x s3://b",
                                  "```\ncargo publish\n```", "helm\tupgrade app ./chart", "$ gcloud auth login",
                                  "- az account show", "Run `aws s3 ls`.", "```bash\n  az login\n```"])
def test_credentialed_actions_are_caught(text):
    # (#166) the sealed session holds no credential, so a task that needs one cannot finish
    assert nc.CREDENTIAL.search(f"{text}x" if text.endswith(" ") else text)   # "aws " stands for "aws <command>"


@pytest.mark.parametrize("text", ["the publisher field", "pushed the branch", "apply the patch", "terraform plan",
                                  "npm publisher", "docker pushes", "az", "gh release list",
                                  "exit 1 when az is not installed", "an AWS key", "a stub az",
                                  "raise Error(\"az timed out\")", "Use gcloud auth when asked."])
def test_lookalike_words_pass_the_credential_check(text):
    # (#166)
    assert not nc.CREDENTIAL.search(text)


def test_a_credentialed_task_is_refused_naming_the_phrase_and_line(vault_repo):
    # (#166) a mention inside a fenced code block counts: plans put commands there
    errs = nc.check(vault_repo, plan_fm(tasks="4"), "")
    assert any("task 4" in e and "npm publish" in e and "npm  publish --access public" in e for e in errs), errs



@pytest.mark.parametrize("field,value,needle", [
    ("id", "../../evil", "id must look like"), ("id", "2026-10-06-Bad_Name", "id must look like"),
    ("id", "evil", "id must look like"), ("base", "--output=/tmp/x", "base must not start with '-'"),
    ("pr_base", "-x", "pr_base must not start with '-'"), ("repo", "../x", "repo must be a plain name")])
def test_identifiers_are_refused_before_any_git_call(vault_repo, field, value, needle):
    errs = nc.check(vault_repo, plan_fm(tasks="1-2", **{field: value}), "")
    assert any(needle in e for e in errs), errs


@pytest.mark.parametrize("output", ["wiki/work/../personal/x.md", "/etc/x.md"])
def test_output_must_stay_inside_the_vault(vault_repo, output):
    fm = plan_fm(kind="research", output=output, hosts=[])
    assert any("no '..'" in e for e in nc.check(vault_repo, fm, BRIEF))
