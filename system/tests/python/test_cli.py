import json
import subprocess

from helpers import concept, write


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
