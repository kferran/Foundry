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


def test_push_and_github_pr(tmp_path, monkeypatch):
    src = repo_with_commit(tmp_path / "src")
    git(src, "checkout", "-q", "-b", "nightshift/x")
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    ok, log = nd.push(tmp_path / "runner.git", src, "nightshift/x", str(remote))
    assert ok, log
    assert "nightshift/x" in git(remote, "branch", "--list")
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


def test_research_rejected_by_gate_publishes_nothing(vault: Path, tmp_path):
    findings = tmp_path / "B.md"
    findings.write_text("---\ntype: concept\n---\n# no required fields\n")
    ok, detail = nd.publish_research(vault, {"output": "wiki/work/concepts/B.md", "partition": "work"}, findings)
    assert not ok and detail
    assert not (vault / "wiki/work/concepts/B.md").exists()
