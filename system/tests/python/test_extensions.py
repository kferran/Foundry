# system/tests/python/test_extensions.py: the extension manifest loader (extensions spec §3).
import shutil
import subprocess
import sys

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
