# system/tests/python/test_extensions.py: the extension manifest loader (extensions spec §3).
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import REPO, write
from vaultlib import extensions

FIXTURES = REPO / "system" / "tests" / "fixtures" / "extensions"
SCRIPT = REPO / "system" / "scripts" / "extensions.py"


def config(vault, *names):
    listed = ", ".join(f'"{n}"' for n in names)
    write(vault, "system/config.md", f"---\ntype: config\nextensions: [{listed}]\n---\n")


@pytest.fixture
def ext(vault):
    shutil.copytree(FIXTURES, vault / "extensions")
    return vault


def manifest(vault, name, **fields):
    lines = ["---", f"name: {fields.pop('name', name)}", f"contract: {fields.pop('contract', 1)}"]
    lines += [f"{k}: {v}" for k, v in fields.items()]
    write(vault, f"extensions/{name}/extension.md", "\n".join([*lines, "---", "body", ""]))


def run(vault, *args):
    # The CLI reads its own vault from its location, so run a copy placed inside the fixture vault.
    dst = vault / "system" / "scripts"
    shutil.copytree(REPO / "system" / "scripts", dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    return subprocess.run([sys.executable, str(dst / "extensions.py"), *args], capture_output=True, text=True)


def test_list_returns_enabled_present_extensions_in_dependency_order(vault):
    manifest(vault, "a")
    manifest(vault, "b", requires="[a]")
    config(vault, "b", "a")
    assert [n for n, _ in extensions.enabled(vault)] == ["a", "b"]
    assert run(vault, "list").stdout.split() == ["a", "b"]


def test_listed_without_folder_is_reported_and_skipped(ext):
    config(ext, "demo", "demo2")
    assert extensions.check(ext) == ["demo2: listed in extensions but extensions/demo2/ does not exist"]
    assert [n for n, _ in extensions.enabled(ext)] == ["demo"]
    r = run(ext, "check")
    assert r.returncode == 1
    assert "demo2: listed in extensions" in r.stdout


def test_missing_requires_wrong_contract_unknown_field_each_refused_with_one_reason(ext):
    manifest(ext, "oldc", contract=2)
    manifest(ext, "odd", flavour="vanilla")
    config(ext, "needs-other", "oldc", "odd")
    reasons = extensions.check(ext)
    assert len(reasons) == 3
    assert any(r.startswith("needs-other:") and "missing" in r for r in reasons)
    assert any(r.startswith("oldc:") and "contract" in r for r in reasons)
    assert any(r.startswith("odd:") and "unknown manifest field(s) flavour" in r for r in reasons)
    assert extensions.enabled(ext) == []


def test_field_reads_one_manifest_field(ext):
    config(ext, "demo")
    assert run(ext, "field", "demo", "description").stdout == "A fixture extension for the loader tests\n"
    assert run(ext, "field", "demo", "alert_tags").stdout.strip() == '["demo"]'
    assert run(ext, "field", "demo", "nope").returncode == 2


def test_rows_prints_smoke_sources_units_allow_as_tsv(ext):
    config(ext, "demo")
    assert run(ext, "smoke").stdout == "demo\t30\t0\textensions/demo/scripts/demo_check.sh\n"
    assert run(ext, "brief").stdout == "demo\n"
    assert run(ext, "units", "server").stdout == "demo\tfoundry-demo\n"
    assert run(ext, "units", "client").stdout == ""
    assert run(ext, "allow").stdout == "Bash(extensions/demo/scripts/demo_check.sh)\n"
    assert run(ext, "ignore").stdout == "raw/demo\n"


def test_a_row_checked_per_item_carries_its_list_command_as_a_fifth_field(ext):
    config(ext, "demo", "items")
    assert run(ext, "smoke").stdout == (
        "demo\t30\t0\textensions/demo/scripts/demo_check.sh\n"
        "items\t30\t0\textensions/items/scripts/items_check.sh {}\textensions/items/scripts/items_list.sh\n")


def test_no_extensions_folder_is_empty_everywhere(vault):
    assert extensions.listed(vault) == []
    assert extensions.enabled(vault) == []
    assert extensions.check(vault) == []
    config(vault)
    for cmd in ("list", "check", "smoke", "brief", "allow", "ignore"):
        r = run(vault, cmd)
        assert (r.returncode, r.stdout, r.stderr) == (0, "", ""), cmd


def test_usage_error_exits_2(vault):
    assert run(vault).returncode == 2
    assert run(vault, "bogus").returncode == 2


def config_with(vault, *lines):
    write(vault, "system/config.md",
          "---\ntype: config\ntimezone: UTC\nbrief_time: \"06:00\"\ndebrief_time: \"17:00\"\nremote_mode: none\n"
          "default_partition: work\nextensions: [\"demo\"]\n" + "\n".join(lines) + "\n---\n")


def test_extension_config_keys_validate_while_present(ext, cli):
    config_with(ext, 'demo_site: "x"')
    r = cli("validate", "system/config.md")
    assert "unknown field" not in r.stdout
    shutil.rmtree(ext / "extensions" / "demo")
    r = cli("validate", "system/config.md")
    assert "unknown field demo_site" in r.stdout


def test_extension_note_schemas_load_from_present_extensions(ext, cli):
    from vaultlib import schema
    config_with(ext)
    schemas = schema.load_schemas(ext)
    assert "demo_thing" in schemas
    assert schemas["demo_thing"].folders == ["wiki/work/things/"]
    assert "demo_site" in schemas["config"].fields
    assert list(schemas).count("config") == 1
    write(ext, "wiki/work/things/Blue.md", "---\ntype: demo_thing\ncolour: blue\n---\n# Blue\n")
    write(ext, "wiki/work/things/Bad.md", "---\ntype: demo_thing\n---\n# Bad\n")
    assert cli("validate", "wiki/work/things/Blue.md").returncode == 0
    assert cli("validate", "wiki/work/things/Bad.md").returncode == 1


def test_config_fragment_that_redefines_a_core_key_is_a_schema_error(ext):
    import pytest as _pytest
    from vaultlib import schema
    write(ext, "extensions/demo/schemas/config.md",
          "---\ntype: schema\nschema_for: config\nfields:\n  timezone: {kind: string}\n---\n")
    with _pytest.raises(schema.SchemaError, match="timezone"):
        schema.load_schemas(ext)


def test_index_skips_extensions_and_their_ignore_paths(ext, cli):
    config_with(ext)
    write(ext, "raw/demo/x.md", "---\ntype: concept\n---\n# X\n")
    write(ext, "extensions/demo/notes/Inside.md", "---\ntype: concept\n---\n# Inside\n")
    write(ext, "wiki/work/things/Blue.md", "---\ntype: demo_thing\ncolour: blue\n---\n# Blue\n")
    r = cli("query", "SELECT path FROM files")
    assert "wiki/work/things/Blue.md" in r.stdout
    assert "extensions/" not in r.stdout
    assert "raw/demo" not in r.stdout


# The allow rules: whole lines inserted after `"allow": [`, never a JSON rewrite (template rule for settings.json).
RULE = "Bash(extensions/demo/scripts/demo_check.sh)"


def with_settings(vault):
    (vault / ".claude").mkdir(exist_ok=True)
    return Path(shutil.copy(REPO / ".claude" / "settings.json", vault / ".claude" / "settings.json"))


def test_write_inserts_each_rule_once_after_the_allow_line_and_keeps_json_valid(ext):
    import json
    config(ext, "demo")
    settings = with_settings(ext)
    r = run(ext, "allow", "--write")
    assert r.returncode == 0, r.stderr
    lines = settings.read_text().split("\n")
    at = lines.index('    "allow": [')
    assert lines[at + 1] == f'      "{RULE}",'
    assert json.loads(settings.read_text())["permissions"]["allow"].count(RULE) == 1
    assert json.loads((ext / "system/logs/extensions-allow.json").read_text()) == {RULE: "demo"}


def test_write_twice_changes_nothing(ext):
    config(ext, "demo")
    settings = with_settings(ext)
    run(ext, "allow", "--write")
    once = settings.read_bytes()
    assert run(ext, "allow", "--write").returncode == 0
    assert settings.read_bytes() == once


def test_remove_deletes_only_that_extensions_rules(ext):
    import json
    manifest(ext, "other", allow='["Bash(extensions/other/x.sh)"]')
    config(ext, "demo", "other")
    settings = with_settings(ext)
    original = settings.read_text()
    run(ext, "allow", "--write")
    assert run(ext, "allow", "--remove", "demo").returncode == 0
    allow = json.loads(settings.read_text())["permissions"]["allow"]
    assert RULE not in allow
    assert "Bash(extensions/other/x.sh)" in allow
    assert run(ext, "allow", "--remove", "other").returncode == 0
    assert settings.read_text() == original


def test_a_rule_the_owner_wrote_by_hand_is_never_removed(ext):
    import json
    config(ext, "demo")
    settings = with_settings(ext)
    text = settings.read_text().replace('    "allow": [\n', f'    "allow": [\n      "{RULE}",\n', 1)
    settings.write_text(text)
    run(ext, "allow", "--write")
    assert settings.read_text() == text
    run(ext, "allow", "--remove", "demo")
    assert RULE in json.loads(settings.read_text())["permissions"]["allow"]


def test_bytes_outside_the_inserted_lines_are_unchanged(ext):
    config(ext, "demo")
    settings = with_settings(ext)
    original = settings.read_text().split("\n")
    run(ext, "allow", "--write")
    after = settings.read_text().split("\n")
    assert len(after) == len(original) + 1
    after.remove(f'      "{RULE}",')
    assert after == original


def test_link_links_enabled_skills_and_unlinks_disabled_ones_and_never_touches_a_real_folder(ext):
    subprocess.run(["git", "init", "-q", str(ext)], check=True)
    config(ext, "demo")
    skills = ext / ".claude" / "skills"
    (skills / "mine").mkdir(parents=True)
    (skills / "mine" / "SKILL.md").write_text("mine\n")
    r = run(ext, "link")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "linked demo-skill\n"
    link = skills / "demo-skill"
    assert link.is_symlink()
    assert str(link.readlink()) == "../../extensions/demo/skills/demo-skill"
    assert (link / "SKILL.md").is_file()
    exclude = (ext / ".git" / "info" / "exclude").read_text()
    assert "/.claude/skills/demo-skill" in exclude.split("\n")
    assert run(ext, "link").stdout == ""
    config(ext)
    assert run(ext, "link").stdout == "unlinked demo-skill\n"
    assert not link.exists() and not link.is_symlink()
    assert (skills / "mine" / "SKILL.md").read_text() == "mine\n"


def test_link_leaves_a_real_folder_of_the_same_name_alone(ext):
    config(ext, "demo")
    real = ext / ".claude" / "skills" / "demo-skill"
    real.mkdir(parents=True)
    (real / "SKILL.md").write_text("owner's\n")
    assert run(ext, "link").stdout == ""
    assert not real.is_symlink()
    assert (real / "SKILL.md").read_text() == "owner's\n"


# enable and migrate (extensions spec §4): the one-time move of a feature's old switch into the extensions list.
def test_enable_adds_a_name_once_and_keeps_the_rest_of_config(vault):
    write(vault, "system/config.md", '---\ntype: config\ntimezone: "UTC"\n---\nbody\n')
    assert extensions.enable(vault, "handoffs") is True
    assert extensions.enable(vault, "handoffs") is False
    assert extensions.enable(vault, "demo") is True
    text = (vault / "system/config.md").read_text()
    assert text == '---\ntype: config\ntimezone: "UTC"\nextensions: ["handoffs", "demo"]\n---\nbody\n'
    assert extensions.listed(vault) == ["handoffs", "demo"]


def test_migrate_lists_handoffs_once_when_handoffs_projects_is_set(vault):
    write(vault, "system/config.md", '---\ntype: config\nhandoffs_projects: ["EX"]\n---\n')
    assert run(vault, "migrate").stdout == "enabled handoffs\n"
    assert extensions.listed(vault) == ["handoffs"]
    # the owner turns it off again: the migration never re-adds it
    write(vault, "system/config.md", '---\ntype: config\nhandoffs_projects: ["EX"]\nextensions: []\n---\n')
    assert run(vault, "migrate").stdout == ""
    assert extensions.listed(vault) == []


def test_migrate_does_nothing_without_the_old_switch(vault):
    write(vault, "system/config.md", '---\ntype: config\nhandoffs_projects: []\n---\n')
    assert run(vault, "migrate").stdout == ""
    assert extensions.listed(vault) == []
    assert not (vault / "system/logs/extensions-migrated").exists()


def test_migrate_enables_what_a_moved_feature_requires_first_and_reads_the_vault(vault, monkeypatch):
    manifest(vault, "base")
    manifest(vault, "top", requires="[base]")
    write(vault, "system/config.md", '---\ntype: config\n---\n')
    monkeypatch.setattr(extensions, "MIGRATIONS", {"top": lambda v, cfg: (v / "system/top.flag").exists()})
    assert extensions.migrate(vault) == []
    write(vault, "system/top.flag", "")
    assert extensions.migrate(vault) == ["base", "top"]
    assert [n for n, _ in extensions.enabled(vault)] == ["base", "top"]
    assert extensions.migrate(vault) == []


# lint (extensions spec §3): a present extension's own cross-field rules run inside the index lint.
def lint_issues(vault):
    from vaultlib.index import Index
    idx = Index(vault)
    idx.refresh(full=True)
    return [(p, c, m) for p, c, m in idx.connect().execute("SELECT path, code, message FROM issues")]


def test_a_present_extension_s_lint_module_reports_into_the_index(vault):
    manifest(vault, "rules", lint="scripts/rules.py")
    write(vault, "extensions/rules/scripts/rules.py",
          'def issues(conn, add):\n    n = conn.execute("SELECT count(*) FROM notes").fetchone()[0]\n'
          '    add("wiki/Index.md", 1, "warning", "rules", f"{n > 0} notes seen")\n')
    assert ("wiki/Index.md", "rules", "True notes seen") in lint_issues(vault)


def test_a_lint_module_that_fails_is_one_error_on_its_manifest(vault):
    manifest(vault, "rules", lint="scripts/rules.py")
    write(vault, "extensions/rules/scripts/rules.py", "def issues(conn, add):\n    raise ValueError('broken')\n")
    assert ("extensions/rules/extension.md", "extension-lint",
            "lint scripts/rules.py failed: ValueError: broken") in lint_issues(vault)
