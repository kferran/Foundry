import json
import os
import subprocess

from helpers import concept, meeting, transcript, write


def test_issues_clean_fixture(cli):
    res = cli("issues")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "0 errors" in res.stdout


def test_issues_reports_errors(cli, vault):
    write(vault, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad")
    res = cli("issues")
    assert res.returncode == 1
    assert "wiki/work/concepts/Bad.md:2: error: missing required field tags" in res.stdout


def test_issues_json(cli):
    data = json.loads(cli("issues", "--json").stdout)
    assert data["errors"] == 0 and isinstance(data["issues"], list)


def test_issues_staged(cli, vault):
    subprocess.run(["git", "init", "-q", str(vault)], check=True)
    write(vault, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad")
    assert cli("issues", "--staged").returncode == 0
    subprocess.run(["git", "-C", str(vault), "add", "wiki/work/concepts/Bad.md"], check=True)
    assert cli("issues", "--staged").returncode == 1


def test_issues_staged_lints_the_index_blob_not_the_working_copy(cli, vault):
    """Stage a bad note, fix it on disk only: refused, naming the staged problem; the reverse passes (#166)."""
    subprocess.run(["git", "init", "-q", str(vault)], check=True)
    write(vault, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad")
    subprocess.run(["git", "-C", str(vault), "add", "wiki/work/concepts/Bad.md"], check=True)
    write(vault, "wiki/work/concepts/Bad.md", concept("work", "Bad"))
    res = cli("issues", "--staged")
    assert res.returncode == 1
    assert "wiki/work/concepts/Bad.md:2: error: missing required field tags" in res.stdout
    subprocess.run(["git", "-C", str(vault), "add", "wiki/work/concepts/Bad.md"], check=True)
    write(vault, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad")
    assert cli("issues", "--staged").returncode == 0
    assert cli("issues").returncode == 1


def _git(vault, *argv):
    subprocess.run(["git", "-C", str(vault), "-c", "user.email=t@example.com", "-c", "user.name=t", *argv],
                   check=True, capture_output=True)


CAP = 16 * 1024   # CLAUDE.md's write cap


def _commit_claude_md(vault, size):
    """A CLAUDE.md of `size` bytes committed at HEAD, so the staged lint has a "before" to compare with."""
    _git(vault, "init", "-q")
    write(vault, "CLAUDE.md", "x" * size)
    _git(vault, "add", "CLAUDE.md")
    _git(vault, "commit", "-qm", "claude", "--no-verify")


def _stage_claude_md(vault, size):
    write(vault, "CLAUDE.md", "x" * size)
    _git(vault, "add", "CLAUDE.md")


def test_staged_write_cap_refuses_an_over_cap_file_that_grows(cli, vault):
    _commit_claude_md(vault, CAP + 10)
    _stage_claude_md(vault, CAP + 20)
    res = cli("issues", "--staged")
    assert res.returncode == 1, res.stdout
    assert f"CLAUDE.md:1: error: {CAP + 20} bytes is over the {CAP}-byte cap and larger than the committed {CAP + 10}" \
        in res.stdout


def test_staged_write_cap_passes_an_over_cap_file_that_shrinks(cli, vault):
    _commit_claude_md(vault, CAP + 20)
    _stage_claude_md(vault, CAP + 10)
    res = cli("issues", "--staged")
    assert "byte cap" not in res.stdout, res.stdout


def test_staged_write_cap_passes_an_over_cap_file_that_keeps_its_size(cli, vault):
    _commit_claude_md(vault, CAP + 10)
    write(vault, "CLAUDE.md", "y" * (CAP + 10))   # same size, new content
    _git(vault, "add", "CLAUDE.md")
    assert "byte cap" not in cli("issues", "--staged").stdout


def test_staged_write_cap_passes_an_under_cap_file_that_grows(cli, vault):
    _commit_claude_md(vault, 100)
    _stage_claude_md(vault, 200)
    assert "byte cap" not in cli("issues", "--staged").stdout


def test_staged_write_cap_leaves_now_pages_alone(cli, vault):
    """Unattended writers (triage, the brief) grow the Now page; a refused sync commit would stop every sync."""
    _git(vault, "init", "-q")
    write(vault, "wiki/work/Now.md", "x" * (64 * 1024))
    _git(vault, "add", "wiki/work/Now.md")
    assert "byte cap" not in cli("issues", "--staged").stdout


def test_staged_write_cap_during_a_merge_compares_with_the_larger_parent(cli, vault):
    """The commit that resolves a merge brings the other side's larger copy: it passes; growing past both is refused."""
    _commit_claude_md(vault, 100)
    _git(vault, "checkout", "-q", "-b", "other")
    write(vault, "CLAUDE.md", "x" * (CAP + 10))
    _git(vault, "commit", "-qam", "big", "--no-verify")
    _git(vault, "checkout", "-q", "-")
    write(vault, "README.txt", "local\n")
    _git(vault, "add", "README.txt")
    _git(vault, "commit", "-qm", "local", "--no-verify")
    _git(vault, "merge", "-q", "--no-commit", "--no-ff", "other")
    assert "byte cap" not in cli("issues", "--staged").stdout
    _stage_claude_md(vault, CAP + 20)
    assert f"{CAP + 20} bytes is over the {CAP}-byte cap and larger than the committed {CAP + 10}" \
        in cli("issues", "--staged").stdout


def test_staged_write_cap_refuses_a_new_file_over_its_cap(cli, vault):
    _git(vault, "init", "-q")
    write(vault, "CLAUDE.md", "x" * (16 * 1024 + 1))
    _git(vault, "add", "CLAUDE.md")
    res = cli("issues", "--staged")
    assert res.returncode == 1
    assert "CLAUDE.md:1: error: 16385 bytes is over the 16384-byte cap and larger than the committed 0" in res.stdout


def test_template_files_sit_under_their_write_caps():
    from helpers import REPO
    from vaultlib.cli import WRITE_CAPS
    for rel, cap in WRITE_CAPS.items():
        path = REPO / rel
        assert not path.exists() or path.stat().st_size <= cap, rel


def test_tags_lists_one_partition_most_used_first(cli, vault):
    write(vault, "wiki/work/concepts/Topic.md", concept("work", "Topic", tags="[streaming, api-gateway]"))
    write(vault, "wiki/work/concepts/Other.md", concept("work", "Other", tags="[streaming, now]"))
    write(vault, "wiki/work/concepts/Flat.md", concept("work", "Flat", tags="tooling"))
    write(vault, "wiki/work/concepts/Gone.md", concept("work", "Gone", tags="[retired-tag]", status="deprecated"))
    write(vault, "wiki/work/concepts/Legacy.md", concept("work", "Legacy", tags='["Legacy Stuff", "2026"]'))
    res = cli("tags", "--partition", "work")
    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines() == ["3\tstreaming", "1\tapi-gateway"]
    assert cli("tags", "--partition", "shared").stdout.splitlines() == ["1\ttooling"]
    assert cli("tags", "--partition", "personal").stdout.splitlines() == ["1\thobby"]
    assert json.loads(cli("tags", "--partition", "personal", "--json").stdout) == [{"tag": "hobby", "count": 1}]


def test_tags_needs_a_partition(cli):
    assert cli("tags").returncode == 2


def _tag_issues(cli):
    return [(i["path"], i["severity"], i["code"]) for i in json.loads(cli("issues", "--json").stdout)["issues"]
            if i["code"].startswith("tag-")]


def test_tags_in_another_form_warn(cli, vault):
    write(vault, "wiki/work/concepts/Bad.md", concept("work", "Bad", tags='[Tooling, "two words", "#tag", 2026]'))
    write(vault, "wiki/work/concepts/Good.md", concept("work", "Good", tags="[project/alpha, api-gateway, v2]"))
    write(vault, "wiki/work/meetings/2026-10-01-0900-sync.md", meeting("work", "2026-10-01-0900-sync"))
    write(vault, "wiki/work/meetings/2026-10-01-0900-sync.transcript.md",
          transcript("work", "2026-10-01-0900-sync", "Posted in #General and #Ops."))
    write(vault, "briefings/2026-10-06.md", '---\ntype: briefing\ndate: "2026-10-06"\ntags: [Daily]\n---\n# Briefing\n')
    assert _tag_issues(cli) == [("wiki/work/concepts/Bad.md", "warning", "tag-form")] * 4
    assert cli("issues").returncode == 0
    assert 'tag "2026" is only digits' in cli("issues").stdout


def test_system_tags_warn_off_their_notes(cli, vault):
    write(vault, "wiki/work/concepts/Topic.md", concept("work", "Topic", tags="[now, rca]"))
    write(vault, "wiki/work/Now.md", concept("work", "Now", tags="[now]"))
    write(vault, "wiki/work/rca/2026-10-11-orders.md",
          '---\ntype: rca\ntitle: "Orders fail"\npartition: work\ncreated_at: "2026-10-11"\nsource: "raw/telemetry/a.md"\n'
          'rc_confidence: 4\nfix_confidence: 4\nstatus: draft\ntags: [rca]\n---\n# Orders fail\n')
    assert _tag_issues(cli) == [("wiki/work/concepts/Topic.md", "warning", "tag-reserved")] * 2


def test_staged_tag_issues_never_block_a_commit(cli, vault):
    # the sync commits unattended through the hook: a hand-written tag warns, the publish gate guards headless runs
    subprocess.run(["git", "init", "-q", str(vault)], check=True)
    write(vault, "wiki/work/concepts/New.md", concept("work", "New", tags="[Tooling]"))
    subprocess.run(["git", "-C", str(vault), "add", "wiki/work/concepts/New.md"], check=True)
    res = cli("issues", "--staged")
    assert res.returncode == 0, res.stdout
    assert 'wiki/work/concepts/New.md:3: warning: tag "Tooling"' in res.stdout


def test_citation_check_warns_on_a_missing_file_or_a_line_past_its_end(cli, vault, tmp_path):
    """A `path:NN` in an rca or codebase note names a file of that codebase with at least NN lines (#166)."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("a\nb\nc\n")
    write(vault, "system/codebases/app.md", f'---\ntype: codebase\nname: app\npath: "{repo}"\npartition: work\n'
          'search_globs: ["*"]\n---\nEntry at `src/app.py:3`; gone `src/old.py:1`.\n')
    write(vault, "wiki/work/rca/2026-10-11-orders.md",
          '---\ntype: rca\ntitle: "Orders fail"\npartition: work\ncreated_at: "2026-10-11"\nsource: "raw/telemetry/a.md"\n'
          'codebase: app\nrc_confidence: 4\nfix_confidence: 4\nstatus: draft\ntags: [rca]\n---\n# Orders fail\n\n'
          'Root cause at `src/app.py:9`, see https://example.com:443/x.py:2 and `app.py:2`.\n'
          '```\nat src/trace.py:7\n```\n')
    data = json.loads(cli("issues", "--json").stdout)
    assert [(i["path"], i["line"], i["severity"], i["message"]) for i in data["issues"] if i["code"] == "citation"] == [
        ("system/codebases/app.md", 8, "warning", "citation src/old.py:1: no such file in codebase app"),
        ("wiki/work/rca/2026-10-11-orders.md", 15, "warning", "citation src/app.py:9: the file has 3 lines"),
    ]


def _rca(stem, codebase, status, body, extra=""):
    return (f'---\ntype: rca\ntitle: "{stem}"\npartition: work\ncreated_at: "2026-10-11"\nsource: "raw/telemetry/a.md"\n'
            f'codebase: {codebase}\nrc_confidence: 4\nfix_confidence: 4\nstatus: {status}\n{extra}tags: [rca]\n---\n'
            f'# {stem}\n\n{body}\n')


def test_citation_check_scope_fences_vendored_paths_codebase_file_name_and_layers(cli, vault, tmp_path):
    """Open, active rca notes only; ~~~ fences and vendored paths skipped; an rca names its codebase by file name;
    a codebase note's citation may sit under one of its layers (#251 review)."""
    repo = tmp_path / "repo"
    (repo / "svc" / "lib").mkdir(parents=True)
    (repo / "svc" / "lib" / "core.py").write_text("a\n")
    write(vault, "system/codebases/app.md", f'---\ntype: codebase\nname: "App Service"\npath: "{repo}"\npartition: work\n'
          'search_globs: ["*"]\nlayers:\n  api: "svc/"\n---\nCore at `lib/core.py:1`; vendored `vendor/x/y.go:1`, '
          '`web/node_modules/z/i.js:1`.\n~~~\nat src/fenced.py:1\n~~~\n')
    gone = "Gone `src/gone.py:1`."
    for stem, status, extra in (("open", "draft", ""), ("ok", "approved", ""), ("filed", "filed", ""),
                                ("rejected", "rejected", ""), ("old", "draft", 'superseded_by: "[[open]]"\n')):
        write(vault, f"wiki/work/rca/{stem}.md", _rca(stem, "app", status, gone, extra))
    data = json.loads(cli("issues", "--json").stdout)
    assert [(i["path"], i["message"]) for i in data["issues"] if i["code"] == "citation"] == [
        ("wiki/work/rca/ok.md", "citation src/gone.py:1: no such file in codebase app"),
        ("wiki/work/rca/open.md", "citation src/gone.py:1: no such file in codebase app"),
    ]


def test_archived_briefings_stay_indexed_and_the_debrief_embed_resolves(cli, vault):
    write(vault, "briefings/archive/2026-10/2026-10-06.md",
          '---\ntype: briefing\ndate: "2026-10-06"\nstatus: active\n---\n# Briefing\n\n![[2026-10-06.debrief]]\n')
    write(vault, "briefings/archive/2026-10/2026-10-06.debrief.md",
          '---\ntype: debrief\ndate: "2026-10-06"\n---\n# Debrief\n')
    data = json.loads(cli("issues", "--json").stdout)
    assert [i for i in data["issues"] if "briefings/" in json.dumps(i)] == []
    res = cli("query", "SELECT path, type FROM notes WHERE path LIKE 'briefings/archive/%' ORDER BY path")
    assert res.returncode == 0, res.stderr
    assert "briefings/archive/2026-10/2026-10-06.debrief.md" in res.stdout
    assert "briefings/archive/2026-10/2026-10-06.md" in res.stdout


def test_the_briefing_template_adds_no_tags():
    from vaultlib import links
    from helpers import REPO
    body = (REPO / "system" / "templates" / "daily-briefing.md").read_text(encoding="utf-8")
    assert links.extract(body, 1)[1] == set()


def test_query_and_rejection(cli):
    res = cli("query", "SELECT path FROM notes WHERE type='index'")
    assert res.returncode == 0 and "wiki/Index.md" in res.stdout
    bad = cli("query", "DELETE FROM notes")
    assert bad.returncode == 1 and "not authorized" in bad.stderr


def test_related_text_and_json(cli):
    res = cli("related", "distributed commit log", "--json")
    hits = json.loads(res.stdout)
    assert hits[0]["path"] == "wiki/work/concepts/Kafka.md"


def test_show_and_backlinks(cli):
    assert "# Git" in cli("show", "Git").stdout
    assert "wiki/work/concepts/Kafka.md" in cli("backlinks", "Git").stdout
    assert cli("show", "Nope").returncode == 1


def test_validate(cli, vault):
    write(vault, "wiki/work/concepts/Bad.md", "---\ntype: concept\n---\n# Bad")
    assert cli("validate", "wiki/work/concepts/Kafka.md").returncode == 0
    assert cli("validate", "wiki/work/concepts/Bad.md").returncode == 1


def test_field(cli, vault):
    assert cli("field", "wiki/work/concepts/Kafka.md", "partition").stdout.strip() == "work"
    assert cli("field", "wiki/work/concepts/Kafka.md", "tags").stdout.strip() == "streaming"
    assert cli("field", "wiki/work/concepts/Kafka.md", "missing").returncode == 1


def test_set_replaces_inserts_and_quotes(cli, vault):
    path = write(vault, "system/config.md",
                 '---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
                 'remote_mode: "none"   # set by setup_remote.sh\ndefault_partition: personal\n---\nbody\n')
    assert cli("set", "system/config.md", "remote_mode", "private").returncode == 0
    assert cli("set", "system/config.md", "template_remote", 'git@x:y "z".git').returncode == 0
    text = path.read_text()
    assert 'remote_mode: "private"  # set by setup_remote.sh' in text
    assert 'template_remote: "git@x:y \\"z\\".git"' in text
    assert text.endswith("---\nbody\n")


def test_set_refuses_non_scalar_and_reverts_invalid(cli, vault):
    original = (vault / "wiki/work/concepts/Kafka.md").read_text()
    assert cli("set", "wiki/work/concepts/Kafka.md", "tags", "x").returncode == 1
    assert cli("set", "wiki/work/concepts/Kafka.md", "partition", "personal").returncode == 1
    assert (vault / "wiki/work/concepts/Kafka.md").read_text() == original


def test_paths_outside_vault_rejected(cli, tmp_path):
    outside = tmp_path / "x.md"
    outside.write_text("---\na: b\n---\n")
    assert cli("field", str(outside), "a").returncode == 2


def test_cli_from_subdirectory(cli, vault):
    res = cli("field", "work/concepts/Kafka.md", "partition", cwd=vault / "wiki")
    assert res.returncode == 0 and res.stdout.strip() == "work"
    assert cli("issues", cwd=vault / "wiki").returncode == 0


def test_out_of_scope_caller(cli, tmp_path):
    res = cli("related", "kafka", cwd=tmp_path)
    assert res.returncode == 2 and "scope" in res.stderr


def test_codebase_scope_limits_partitions(cli, vault, tmp_path):
    repo = tmp_path / "code"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    write(vault, "system/codebases/code.md",
          f'---\ntype: codebase\nname: code\npath: "{repo}"\npartition: work\nsearch_globs: ["*"]\n---\n')
    assert cli("related", "tomatoes", "--json", cwd=repo).stdout.strip() == "[]"
    assert cli("show", "Gardening", cwd=repo).returncode == 1
    assert "# Git" in cli("show", "Git", cwd=repo).stdout
    assert cli("query", "SELECT 1", cwd=repo).returncode == 2
    assert cli("issues", cwd=repo).returncode == 2


def test_rebuild(cli):
    assert cli("rebuild").returncode == 0


def _work_codebase(vault, tmp_path):
    repo = tmp_path / "code"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    write(vault, "system/codebases/code.md",
          f'---\ntype: codebase\nname: code\npath: "{repo}"\npartition: work\nsearch_globs: ["*"]\n---\n')
    return repo


def test_show_refuses_symlink_outside_vault(cli, vault, tmp_path):
    repo = _work_codebase(vault, tmp_path)
    secret = tmp_path / "secret.md"
    secret.write_text(concept("work", "Secret"))
    os.symlink(secret, vault / "wiki/work/concepts/Leak.md")
    res = cli("show", "Leak", cwd=repo)
    assert res.returncode == 1 and "Secret" not in res.stdout
    assert cli("show", "Leak").returncode == 1


def test_show_refuses_symlink_to_other_partition(cli, vault, tmp_path):
    repo = _work_codebase(vault, tmp_path)
    target = write(vault, "wiki/personal/concepts/Priv.md", concept("personal", "Priv"))
    os.symlink(target, vault / "wiki/work/concepts/PLeak.md")
    res = cli("show", "PLeak", cwd=repo)
    assert res.returncode == 1 and "Priv" not in res.stdout
    assert cli("show", "PLeak").returncode == 1


def test_set_rejects_bad_key(cli, vault):
    path = vault / "wiki/work/concepts/Kafka.md"
    original = path.read_text()
    for key in ('aliases: ["x"]\ntitle', "a:b", "a b", ""):
        assert cli("set", "wiki/work/concepts/Kafka.md", key, "v").returncode == 2
    assert path.read_text() == original


def test_set_validation_failure_leaves_file_untouched(cli, vault):
    path = vault / "wiki/work/concepts/Kafka.md"
    original, mtime = path.read_text(), path.stat().st_mtime_ns
    assert cli("set", "wiki/work/concepts/Kafka.md", "partition", "personal").returncode == 1
    assert path.read_text() == original and path.stat().st_mtime_ns == mtime
    assert not list(path.parent.glob("*.tmp")) and not list(path.parent.glob("tmp*"))


def test_missing_and_directory_arguments(cli):
    for args in (("field", "nope.md", "partition"), ("field", "wiki", "partition"), ("validate", "nope.md")):
        res = cli(*args)
        assert res.returncode == 2 and "Traceback" not in res.stderr


def test_binary_file_argument(cli, vault):
    (vault / "wiki/work/concepts/Bin.md").write_bytes(b"\xff\xfe")
    res = cli("field", "wiki/work/concepts/Bin.md", "partition")
    assert res.returncode == 1 and "Traceback" not in res.stderr


def test_issues_staged_outside_git(cli):
    assert cli("issues", "--staged").returncode == 2


def test_vault_root_env_ignored(cli, vault, tmp_path):
    repo = _work_codebase(vault, tmp_path)
    kafka = vault / "wiki/work/concepts/Kafka.md"
    res = cli("field", str(kafka), "partition", cwd=repo, env={"VAULT_ROOT": str(tmp_path)})
    assert res.returncode == 2


def test_set_duplicate_key_exits_1_and_leaves_file(cli, vault):
    text = "---\ntype: concept\nstatus: active\nstatus: stale\ntags: []\ncompiled_at: \"2026-09-01\"\npartition: work\n---\n# D\n"
    path = write(vault, "wiki/work/concepts/Dup.md", text)
    res = cli("set", "wiki/work/concepts/Dup.md", "status", "deprecated")
    assert res.returncode == 1
    assert path.read_text() == text


def test_set_nested_duplicate_key_rejected(cli, vault):
    text = "---\ntype: concept\nmeta:\n  a: 1\n  a: 2\ntags: []\ncompiled_at: \"2026-09-01\"\npartition: work\n---\n# D\n"
    path = write(vault, "wiki/work/concepts/Dup2.md", text)
    assert cli("set", "wiki/work/concepts/Dup2.md", "partition", "work").returncode == 1
    assert path.read_text() == text


def test_links_ignore_unindexed_trees(cli, vault):
    write(vault, "system/tests/fixtures/x/wiki/Index.md", (vault / "wiki/Index.md").read_text())
    write(vault, "system/templates/Kafka.md", (vault / "wiki/work/concepts/Kafka.md").read_text())
    write(vault, "system/templates/wiki-concept.md", "---\ntype: concept\n---\n# T\n")
    write(vault, "wiki/work/concepts/Linker.md",
          concept("work", "Linker", "[[Index]] [[Kafka]] [[wiki-concept]]"))
    res = cli("query", "SELECT target_raw, target_path, ambiguous FROM links WHERE src='wiki/work/concepts/Linker.md' ORDER BY target_raw", "--json")
    rows = {r[0]: r[1:] for r in json.loads(res.stdout)["rows"]}
    assert rows["Index"] == ["wiki/Index.md", 0]
    assert rows["Kafka"] == ["wiki/work/concepts/Kafka.md", 0]
    assert rows["wiki-concept"][0] is None
    # explicit paths into excluded trees still resolve
    write(vault, "wiki/work/concepts/Linker2.md", concept("work", "Linker2", "[[system/templates/Kafka]] [[system/schemas/index]]"))
    res = cli("query", "SELECT target_path FROM links WHERE src='wiki/work/concepts/Linker2.md' ORDER BY target_path", "--json")
    assert json.loads(res.stdout)["rows"] == [["system/schemas/index.md"], ["system/templates/Kafka.md"]]


def test_path_refs_resolve_from_cwd(cli, vault):
    cwd = vault / "wiki" / "work"
    res = cli("show", "concepts/Kafka.md", cwd=cwd)
    assert res.returncode == 0 and "# Kafka" in res.stdout
    res = cli("related", "concepts/Kafka.md", "--json", cwd=cwd)
    assert res.returncode == 0
    assert all(h["path"] != "wiki/work/concepts/Kafka.md" for h in json.loads(res.stdout))
    assert cli("show", "concepts/Nope.md", cwd=cwd).returncode == 1
    assert cli("backlinks", "concepts/Nope.md", cwd=cwd).returncode == 1
    res = cli("related", "wiki/nonexistent/foo.md")
    assert res.returncode == 2 and "not an indexed note: wiki/nonexistent/foo.md" in res.stderr
    assert cli("related", "distributed commit log").returncode == 0


def test_related_skips_meeting_transcripts_unless_asked(vault, cli):
    name = "2026-10-05-1500-weekly-sync"
    write(vault, f"wiki/work/meetings/{name}.md", meeting("work", name, body="## Summary\nwombat budget"))
    write(vault, f"wiki/work/meetings/{name}.transcript.md", transcript("work", name, "**Avery:** wombat budget"))
    hits = json.loads(cli("related", "wombat budget", "--json").stdout)
    assert [h["type"] for h in hits] == ["meeting"]
    hits = json.loads(cli("related", "wombat budget", "--include-transcripts", "--json").stdout)
    assert sorted(h["type"] for h in hits) == ["meeting", "meeting_transcript"]
