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
"""
BRIEF = "## Question\nWhat?\n## Scope\nDocs.\n## Done when\nAnswered.\n## Output\nA note.\n"


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


@pytest.fixture
def vault_repo(vault: Path) -> Path:
    git(vault, "init", "-q", "-b", "master")
    write(vault, "docs/p.md", PLAN)
    git(vault, "add", "docs/p.md")
    git(vault, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "plan")
    git(vault, "branch", "feat/x")
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "https://github.com/o/r.git"\n---\n')
    return vault


def test_parse_tasks():
    assert nc.parse_tasks("1-3") == {1, 2, 3}
    assert nc.parse_tasks("1,3") == {1, 3}
    assert nc.parse_tasks("") is None
    with pytest.raises(ValueError):
        nc.parse_tasks("three")


def test_task_blocks():
    assert sorted(nc.task_blocks(PLAN)) == [1, 2, 3]


def test_plan_ready_with_range(vault_repo):
    assert nc.check(vault_repo, plan_fm(tasks="1-2"), "") == []


def test_plan_refuses_protected_task_unless_excluded(vault_repo):
    errs = nc.check(vault_repo, plan_fm(tasks=""), "")
    assert any("task 3" in e for e in errs)


def test_plan_errors(vault_repo):
    errs = nc.check(vault_repo, plan_fm(base="nope", tasks="1-2"), "")
    assert any("base nope" in e for e in errs)
    errs = nc.check(vault_repo, plan_fm(tasks="1-9"), "")
    assert any("9" in e for e in errs)
    errs = nc.check(vault_repo, plan_fm(tasks="1-2", verify=[]), "")
    assert any("verify" in e for e in errs)
    errs = nc.check(vault_repo, plan_fm(tasks="1-2", repo="ghost"), "")
    assert any("ghost" in e for e in errs)
    errs = nc.check(vault_repo, plan_fm(tasks="1-2", budget="4 hours"), "")
    assert any("budget" in e for e in errs)


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
