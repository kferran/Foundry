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


LFS = pytest.mark.skipif(not shutil.which("git-lfs"), reason="git-lfs not installed")


def lfs_repo(path: Path, monkeypatch) -> Path:
    """A repository whose a.png is in Git LFS, under a temporary HOME so the user's git config is untouched (#83)."""
    home = path.parent / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in ("XDG_CONFIG_HOME", "GIT_CONFIG_GLOBAL"):   # either would send git lfs install to the real config
        monkeypatch.delenv(var, raising=False)
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


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_verify_exit_127_names_the_sealed_sandbox_as_the_cause(tmp_path):
    """#138: a toolchain under $HOME is not on the sandbox's PATH; the first line says so wherever it is shown."""
    r = repo_with_commit(tmp_path / "r")
    ok, out = nd.run_verify(r, ["no-such-tool-xyz install"], tmp_path / "verify.log")
    assert not ok
    assert out.splitlines()[0] == "no-such-tool-xyz install: exit 127 (command not found in the sealed verify sandbox)"


def test_bwrap_binds_the_toolchain_after_home_and_opens_the_network_only_for_install(tmp_path):
    """Orders toolchain spec §2: the binds follow the $HOME tmpfs; only the install step keeps the host network."""
    assert "--unshare-net" in nd.bwrap(tmp_path, "x")
    assert "--unshare-net" not in nd.bwrap(tmp_path, "x", net=True)
    argv = nd.bwrap(tmp_path, "x", toolchain=["/opt/a/bin", "/opt/b/bin"])
    home = argv.index("--tmpfs", argv.index("--tmpfs") + 1)   # the second --tmpfs is $HOME
    assert argv[home + 1] == str(Path.home())
    a, b = argv.index("/opt/a/bin"), argv.index("/opt/b/bin")
    assert home < a < b < argv.index("--bind")
    assert argv[a - 1:a + 2] == ["--ro-bind", "/opt/a/bin", "/opt/a/bin"]
    assert argv[argv.index("PATH") + 1] == "/opt/a/bin:/opt/b/bin:/usr/local/bin:/usr/bin:/bin"
    assert "--unshare-net" in argv


def tool_dir(home: Path) -> Path:
    """A toolchain directory under home with one executable, hello-tool, beside a credential file."""
    tool = home / ".tools" / "bin"
    tool.mkdir(parents=True)
    (tool / "hello-tool").write_text("#!/bin/sh\necho hi\n")
    (tool / "hello-tool").chmod(0o755)
    (home / ".netrc").write_text("machine x password y")
    return tool


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_toolchain_dirs_are_visible_and_first_on_path_while_home_stays_empty(tmp_path, monkeypatch):
    """Orders toolchain spec §4: the listed directory runs by bare name; nothing else under $HOME appears."""
    home = tmp_path / "home"
    tool = tool_dir(home)
    monkeypatch.setenv("HOME", str(home))
    r = repo_with_commit(tmp_path / "r")
    ok, out = nd.run_verify(r, ["hello-tool", 'test ! -e "$HOME/.netrc"', f'test "${{PATH%%:*}}" = "{tool}"'],
                            tmp_path / "v.log", toolchain=[str(tool)])
    assert ok, out


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_a_symlinked_tool_needs_its_target_directory_listed_too(tmp_path, monkeypatch):
    """Orders toolchain spec §2: only the listed directories show through the empty $HOME. An nvm bin/npm is a symlink
    into ../lib, so bin alone dangles (exit 127) and bin plus lib works; the manual says to list both."""
    home = tmp_path / "home"
    lib, bin_ = home / ".tools" / "lib", home / ".tools" / "bin"
    lib.mkdir(parents=True)
    bin_.mkdir()
    (lib / "tool.sh").write_text("#!/bin/sh\necho hi\n")
    (lib / "tool.sh").chmod(0o755)
    (bin_ / "tool").symlink_to("../lib/tool.sh")
    monkeypatch.setenv("HOME", str(home))
    r = repo_with_commit(tmp_path / "r")
    ok, out = nd.run_verify(r, ["tool"], tmp_path / "v.log", toolchain=[str(bin_)])
    assert not ok and out.startswith("tool: exit 127 (command not found in the sealed verify sandbox)")
    ok, out = nd.run_verify(r, ["tool"], tmp_path / "v.log", toolchain=[str(bin_), str(lib)])
    assert ok, out


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_verify_sha_runs_the_install_first_with_network_and_keeps_it_out_of_the_commit(tmp_path, monkeypatch):
    """Orders toolchain spec §2: order_install runs once, first, with the network, in the throwaway checkout."""
    home = tmp_path / "home"
    tool = tool_dir(home)
    monkeypatch.setenv("HOME", str(home))
    src = repo_with_commit(tmp_path / "src")
    sha = git(src, "rev-parse", "HEAD").strip()
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "master") == (True, sha)
    seen, real = [], nd.bwrap

    def spy(workdir, cmd, toolchain=(), net=False, **kw):
        seen.append((cmd, list(toolchain), net))
        return real(workdir, cmd, toolchain, net, **kw)
    monkeypatch.setattr(nd, "bwrap", spy)
    install, verify = 'echo "$PATH" | tee installed', "test -f installed"
    ok, out = nd.verify_sha(runner, sha, tmp_path / "vdir", [verify], tmp_path / "v.log", "", install, [str(tool)])
    assert ok, out
    assert seen == [(install, [str(tool)], True), (verify, [str(tool)], False)]
    assert "installed" not in git(runner, "ls-tree", "--name-only", sha)
    log = (tmp_path / "v.log").read_text()
    assert log.index(f"$ {install}\n{tool}:") < log.index(f"$ {verify}")


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_a_failing_install_blocks_before_verify_with_the_exit_127_wording(tmp_path):
    """Orders toolchain spec §2: the first line names the key and the command; no verify command runs after it."""
    src = repo_with_commit(tmp_path / "src")
    sha = git(src, "rev-parse", "HEAD").strip()
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "master") == (True, sha)
    ok, out = nd.verify_sha(runner, sha, tmp_path / "vdir", ["touch ran-verify"], tmp_path / "v.log", "",
                            "no-such-tool-xyz install", [])
    assert not ok
    assert out.splitlines()[0] == "order_install: no-such-tool-xyz install: exit 127 (command not found in the sealed verify sandbox)"
    assert "$ touch" not in (tmp_path / "v.log").read_text()


def corepack_tool(d: Path) -> Path:
    """A made-up corepack-like tool: `install` stores a package manager under $COREPACK_HOME, `run` reads it back."""
    d.mkdir(parents=True)
    (d / "corepack-pm").write_text('#!/bin/sh\nset -e\nd="$COREPACK_HOME/v1/pm/1.0"\ncase "$1" in\n'
                                   '  install) mkdir -p "$d"; echo \'{"bin": "pm"}\' > "$d/.corepack" ;;\n'
                                   '  run) cat "$d/.corepack" ;;\nesac\n')
    (d / "corepack-pm").chmod(0o755)
    return d


def test_install_and_verify_share_one_corepack_home_outside_the_checkout(tmp_path, monkeypatch):
    """#189 (orders corepack home spec §2): both steps get the same COREPACK_HOME, bound after the $HOME tmpfs,
    writable for the install and read-only for verify, in the verify directory but outside the checkout."""
    src = repo_with_commit(tmp_path / "src")
    sha = git(src, "rev-parse", "HEAD").strip()
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "master") == (True, sha)
    seen, real = [], nd.bwrap

    def spy(*a, **kw):
        seen.append(real(*a, **kw))
        return ["true"]
    monkeypatch.setattr(nd, "bwrap", spy)
    vdir = tmp_path / "vdir"
    assert nd.verify_sha(runner, sha, vdir, ["true"], tmp_path / "v.log", "", "true", []) == (True, "")
    homes = [argv[argv.index("COREPACK_HOME") + 1] for argv in seen if "COREPACK_HOME" in argv]
    assert len(homes) == 2 and homes[0] == homes[1], seen
    home = homes[0]
    assert Path(home).parent == vdir
    workdir = seen[0][seen[0].index("--chdir") + 1]
    assert not (home + "/").startswith(workdir + "/")
    for argv, mode in zip(seen, ("--bind", "--ro-bind")):
        at = [i for i, a in enumerate(argv) if a == home and argv[i - 1] in ("--bind", "--ro-bind")]
        assert len(at) == 1 and argv[at[0] - 1] == mode and argv[at[0] + 1] == home, argv
        assert argv.index("--tmpfs", argv.index("--tmpfs") + 1) < at[0]
        assert argv[argv.index("COREPACK_ENABLE_DOWNLOAD_PROMPT") + 1] == "0"


@pytest.mark.skipif(not shutil.which("bwrap"), reason="bwrap not installed")
def test_the_install_download_is_readable_in_verify_and_read_only_there(tmp_path, monkeypatch):
    """#189: a package manager the install step stores under COREPACK_HOME runs in the offline verify, even with the
    workspace under the $HOME the sandbox empties; a verify command cannot write there."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    tool = corepack_tool(tmp_path / "tools")
    src = repo_with_commit(tmp_path / "src")
    sha = git(src, "rev-parse", "HEAD").strip()
    runner = tmp_path / "runner.git"
    assert nd.fetch_branch(runner, src, "master") == (True, sha)
    vdir = home / "ws" / "nightshift-x-verify"
    ok, out = nd.verify_sha(runner, sha, vdir, ["corepack-pm run"], tmp_path / "v.log", "", "corepack-pm install", [str(tool)])
    assert ok, out
    assert '$ corepack-pm run\n{"bin": "pm"}\n\n[exit 0]' in (tmp_path / "v.log").read_text()
    write_home = 'touch "$COREPACK_HOME/w"'
    ok, out = nd.verify_sha(runner, sha, vdir, [write_home], tmp_path / "v.log", "", "corepack-pm install", [str(tool)])
    assert not ok
    assert out.splitlines()[0] == f"{write_home}: exit 1"


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


def test_push_target_reads_order_pr_and_its_old_name(vault: Path, tmp_path):
    from test_nightshift_check import registered, set_codebase
    registered(vault, tmp_path)
    set_codebase(vault, "shop", nightshift_pr="bitbucket-link")
    assert nd.push_target(vault, {"repo": "shop"})[1] == "bitbucket-link"
    set_codebase(vault, "shop", order_pr="github:o/shop")
    assert nd.push_target(vault, {"repo": "shop"})[1] == "github:o/shop"
    assert nd.open_pr("gitlab", "order/x", "main", "T", Path("/b"), "") == (False, "unknown order_pr 'gitlab'")


def test_research_published(vault: Path, tmp_path):
    findings = tmp_path / "A.md"
    findings.write_text(concept("work", "Answer", "Found it.", provenance='["headless"]'))
    ok, detail = nd.publish_research(vault, {"output": "wiki/work/concepts/A.md", "partition": "work"}, findings)
    assert ok, detail
    assert (vault / "wiki/work/concepts/A.md").is_file()


def test_research_publishes_only_under_run_lock(vault: Path, tmp_path):
    # #298: a concurrent publish.recover() expects its caller to hold run.lock; the research publish now holds it too.
    import fcntl
    findings = tmp_path / "A.md"
    findings.write_text(concept("work", "Answer", "Found it.", provenance='["headless"]'))
    (vault / "system").mkdir(exist_ok=True)
    with open(vault / "system" / "run.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        ok, detail = nd.publish_research(vault, {"output": "wiki/work/concepts/A.md", "partition": "work"}, findings,
                                         lock_timeout=0)
    assert (ok, detail) == (False, "run.lock busy: another run is publishing; the findings are kept for a retry")
    assert not (vault / "wiki/work/concepts/A.md").exists()
    assert not list((vault / "wiki" / ".staging").glob("*")) if (vault / "wiki" / ".staging").is_dir() else True


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


def test_move_outside_sources_keeps_unquoted_block_wikilinks():
    text = MIXED.replace('sources: ["[[Alpha]]", "https://example.com/a", "[[Beta]]", "src/app/main.py"]',
                         "sources:\n  - [[Alpha]]\n  - https://example.com/a")
    out = nd.move_outside_sources(text)
    assert 'sources: ["[[Alpha]]"]\n' in out
    assert out.endswith("## Web sources\n\n- https://example.com/a\n")


def test_move_outside_sources_reads_a_quoted_key():
    out = nd.move_outside_sources(MIXED.replace("sources:", '"sources":'))
    assert 'sources: ["[[Alpha]]", "[[Beta]]"]\n' in out
    assert '"sources"' not in out


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
    assert git(runner, "log", "-1", "--format=%an <%ae>", new).strip() == "Work Orders <orders@localhost>"


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


def test_protected_files_under_claude_without_the_dot_land_in_dot_claude(tmp_path):
    clone = tmp_path / "c"   # a session cannot write a path with a .claude segment (#92)
    _protected(clone, "claude/commands/x.md", "x")
    _protected(clone, "claude/settings.json", "{}")
    files, problems = nd.protected_files(clone)
    assert files == [(".claude/commands/x.md", b"x")]
    assert problems == [".claude/settings.json: only .claude/skills/, .claude/commands/, .claude/agents/ may be proposed"]


def test_no_protected_files_keeps_the_commit(tmp_path):
    src = repo_with_commit(tmp_path / "src")
    sha = git(src, "rev-parse", "HEAD").strip()
    assert nd.protected_files(src) == ([], [])
    assert nd.apply_protected(tmp_path / "runner.git", sha, "master", [], tmp_path) == (True, sha)


def test_research_stale_claims_become_one_digest_input_for_ingest(vault: Path, tmp_path):
    """#85: a findings note's Stale claims reach ingest as a one-section session digest."""
    from vaultlib import frontmatter, schema
    findings = tmp_path / "A.md"
    findings.write_text(concept("work", "Answer", "Found it.\n\n## Stale claims\n"
                                "- [[Kafka]]: retries 3 times → retries 5 times (src/app/retry.py:12)\n\n## Web sources\n- x\n",
                                provenance='["headless"]'))
    fm = {"output": "wiki/work/concepts/A.md", "partition": "work", "id": "2026-10-10-retry-check"}
    ok, detail = nd.publish_research(vault, fm, findings)
    assert ok, detail
    path = vault / "raw/work/notes/2026-10-10-retry-check.stale-claims.md"
    note = frontmatter.parse(path.read_text())
    assert note.body == "## Stale claims\n- [[Kafka]]: retries 3 times → retries 5 times (src/app/retry.py:12)\n"
    ntype, issues = schema.validate_note(schema.load_schemas(vault), path.relative_to(vault).as_posix(), note,
                                         schema.Context(vault))
    assert ntype == "session_digest"
    assert [i.message for i in issues if i.severity == "error"] == []
    assert note.data["work_order"] == "2026-10-10-retry-check"


def test_research_without_stale_claims_writes_no_digest(vault: Path, tmp_path):
    findings = tmp_path / "A.md"
    findings.write_text(concept("work", "Answer", "Found it.\n\n## Stale claims\n", provenance='["headless"]'))
    ok, _ = nd.publish_research(vault, {"output": "wiki/work/concepts/A.md", "partition": "work", "id": "x"}, findings)
    assert ok
    assert not (vault / "raw/work/notes").exists()


def stale_findings(tmp_path):
    findings = tmp_path / "A.md"
    findings.write_text(concept("work", "Answer", "Found it.\n\n## Stale claims\n- [[Kafka]]: a → b (doc)\n",
                                provenance='["headless"]'))
    return findings


def test_the_stale_claims_input_is_headless_and_names_the_repo(vault: Path, tmp_path):
    from vaultlib import frontmatter
    fm = {"output": "wiki/work/concepts/A.md", "partition": "work", "id": "2026-10-10-x", "repo": "shop"}
    assert nd.publish_research(vault, fm, stale_findings(tmp_path))[0]
    data = frontmatter.parse((vault / "raw/work/notes/2026-10-10-x.stale-claims.md").read_text()).data
    assert data["provenance"] == ["headless"]
    assert data["codebase"] == "shop"


def test_a_second_delivery_after_ingest_writes_no_second_input(vault: Path, tmp_path):
    fm = {"output": "wiki/work/concepts/A.md", "partition": "work", "id": "2026-10-10-x"}
    write(vault, "raw/work/archive/2026-10-10-x.stale-claims.md", "compiled\n")
    assert nd.stale_claims_input(vault, fm, stale_findings(tmp_path).read_text()) is None
    assert not (vault / "raw/work/notes").exists()


def test_a_failed_handoff_still_reports_the_published_findings(vault: Path, tmp_path, monkeypatch):
    def broken(*_):
        raise OSError("disk full")
    monkeypatch.setattr(nd, "stale_claims_input", broken)
    ok, detail = nd.publish_research(vault, {"output": "wiki/work/concepts/A.md", "partition": "work", "id": "x"},
                                     stale_findings(tmp_path))
    assert ok
    assert detail.startswith("wiki/work/concepts/A.md (its stale claims did not reach ingest: OSError")
    assert (vault / "wiki/work/concepts/A.md").is_file()
