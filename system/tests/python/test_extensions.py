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
