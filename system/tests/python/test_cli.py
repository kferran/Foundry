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
