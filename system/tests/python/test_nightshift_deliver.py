import os
import shutil
import subprocess
from pathlib import Path

import pytest

from helpers import concept, write
from vaultlib import nightshift_deliver as nd


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout


def repo_with_commit(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "master")
    (path / "a.txt").write_text("a")
    git(path, "add", ".")
    git(path, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-qm", "a")
    return path


def test_protected_refs(tmp_path):
    r = repo_with_commit(tmp_path / "r")
    assert list(nd.protected_refs(r)) == ["refs/heads/master"]


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_verify_runs_sandboxed(tmp_path):
    r = repo_with_commit(tmp_path / "r")
    log = tmp_path / "verify.log"
    assert nd.run_verify(r, ["test -f a.txt"], log) == (True, "")
    ok, out = nd.run_verify(r, ["test -f missing.txt"], log)
    assert not ok and "exit 1" in out
    ok, _ = nd.run_verify(r, [f"cat {Path.home()}/.ssh/* >/dev/null 2>&1 && exit 1 || exit 0"], log)
    assert ok
    ok, _ = nd.run_verify(r, ["touch /etc/nightshift-test"], log)
    assert not ok


def test_fetch_push_and_github_pr(tmp_path, monkeypatch):
    src = repo_with_commit(tmp_path / "src")
    git(src, "checkout", "-q", "-b", "nightshift/x")
    sha = git(src, "rev-parse", "HEAD").strip()
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "nightshift/x") == (True, sha)
    ok, log = nd.push(runner, sha, "nightshift/x", str(remote))
    assert ok, log
    assert git(remote, "rev-parse", "nightshift/x").strip() == sha
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text('#!/bin/bash\necho "$@" > "$GH_LOG"\necho https://github.com/o/r/pull/7\n')
    (bin_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("GH_LOG", str(tmp_path / "gh.log"))
    body = tmp_path / "body.md"
    body.write_text("b")
    assert nd.open_pr("github:o/r", "nightshift/x", "master", "T", body, "") == (True, "https://github.com/o/r/pull/7")
    assert "--base master --head nightshift/x" in (tmp_path / "gh.log").read_text()


def test_fetch_reads_the_tip_from_the_runner_repository(tmp_path):
    src = repo_with_commit(tmp_path / "src")
    git(src, "checkout", "-q", "-b", "nightshift/x")
    git(src, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "work")
    tip = git(src, "rev-parse", "HEAD").strip()
    git(src, "tag", "nightshift/x", "HEAD~1")  # a tag named like the branch must not be what is fetched
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "nightshift/x") == (True, tip)
    assert git(runner, "rev-parse", "refs/heads/nightshift/x").strip() == tip


def test_fetch_of_a_missing_branch_fails(tmp_path):
    src = repo_with_commit(tmp_path / "src")
    ok, why = nd.fetch_branch(tmp_path / "runner.git", src, "nightshift/gone")
    assert not ok and why


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_verify_runs_on_a_private_checkout_of_the_sha(tmp_path):
    src = repo_with_commit(tmp_path / "src")
    sha = git(src, "rev-parse", "HEAD").strip()
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "master") == (True, sha)
    evil = "git -c user.name=e -c user.email=e@e commit -q --allow-empty -m evil; git update-ref refs/heads/master HEAD; true"
    ok, _ = nd.verify_sha(runner, sha, tmp_path / "vdir", ["test -f a.txt", evil], tmp_path / "v.log")
    assert ok
    assert git(runner, "rev-parse", "master").strip() == sha
    assert not (tmp_path / "vdir").exists()


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_verify_sees_no_home_and_no_environment(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".aws").mkdir(parents=True)
    (home / ".netrc").write_text("machine x password y")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GH_TOKEN", "secret")
    r = repo_with_commit(tmp_path / "r")
    ok, out = nd.run_verify(r, ['test ! -e "$HOME/.netrc"', 'test ! -e "$HOME/.aws"', 'test -z "${GH_TOKEN:-}"'],
                            tmp_path / "v.log")
    assert ok, out


def test_bitbucket_link_from_push_output():
    log = "remote:\nremote: Create pull request for nightshift/x:\nremote:   https://bitbucket.org/acme/app/pull-requests/new?source=nightshift/x&t=1\n"
    assert nd.open_pr("bitbucket-link", "nightshift/x", "main", "T", Path("/b"), log) == \
        (True, "https://bitbucket.org/acme/app/pull-requests/new?source=nightshift/x&t=1")
    assert nd.open_pr("bitbucket-link", "nightshift/x", "main", "T", Path("/b"), "")[0] is False


def test_push_target_for_template(vault: Path):
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "UTC"\ntemplate_remote: "https://github.com/acme/vault-template.git"\n---\n')
    assert nd.push_target(vault, {"repo": "template"}) == ("https://github.com/acme/vault-template.git", "github:acme/vault-template")


def test_research_published(vault: Path, tmp_path):
    findings = tmp_path / "A.md"
    findings.write_text(concept("work", "Answer", "Found it.", provenance='["headless"]'))
    ok, detail = nd.publish_research(vault, {"output": "wiki/work/concepts/A.md", "partition": "work"}, findings)
    assert ok, detail
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


def test_research_rejected_by_gate_publishes_nothing(vault: Path, tmp_path):
    findings = tmp_path / "B.md"
    findings.write_text("---\ntype: concept\n---\n# no required fields\n")
    ok, detail = nd.publish_research(vault, {"output": "wiki/work/concepts/B.md", "partition": "work"}, findings)
    assert not ok and detail
    assert not (vault / "wiki/work/concepts/B.md").exists()


def _protected(clone: Path, rel: str, text: str) -> None:
    p = clone / ".nightshift" / "protected" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_protected_files_are_committed_by_the_runner(tmp_path):
    src = repo_with_commit(tmp_path / "src")
    sha = git(src, "rev-parse", "HEAD").strip()
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "master") == (True, sha)
    _protected(src, ".claude/skills/demo/SKILL.md", "---\nname: demo\n---\n")
    files, problems = nd.protected_files(src)
    assert problems == [] and [r for r, _ in files] == [".claude/skills/demo/SKILL.md"]
    ok, new = nd.apply_protected(runner, sha, "master", files, tmp_path)
    assert ok and new != sha
    assert git(runner, "show", f"{new}:.claude/skills/demo/SKILL.md") == "---\nname: demo\n---\n"
    assert git(runner, "rev-parse", f"{new}^").strip() == sha
    assert git(runner, "rev-parse", "master").strip() == new
    assert git(runner, "show", f"{new}:a.txt") == "a"


def test_protected_files_outside_the_allowed_folders_are_refused(tmp_path):
    clone = tmp_path / "c"
    _protected(clone, ".claude/settings.json", "{}")
    _protected(clone, "system/scripts/x.sh", "echo")
    (tmp_path / "secret").write_text("s")
    link = clone / ".nightshift" / "protected" / ".claude" / "commands" / "x.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(tmp_path / "secret")
    files, problems = nd.protected_files(clone)
    assert files == [] and len(problems) == 3


def test_no_protected_files_keeps_the_commit(tmp_path):
    src = repo_with_commit(tmp_path / "src")
    sha = git(src, "rev-parse", "HEAD").strip()
    assert nd.protected_files(src) == ([], [])
    assert nd.apply_protected(tmp_path / "runner.git", sha, "master", [], tmp_path) == (True, sha)
