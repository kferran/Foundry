"""The extension API (factory F2 §3.3): extension scripts import vaultlib only through vaultlib.api, and the API
exports nothing they do not use. Extension tests are outside the ban: they pin an extension against core behaviour."""
import ast
import re
import subprocess

import pytest

from helpers import REPO

API = "vaultlib.api"
KEEP = {"schema", "yamlload"}   # for a vault's own extension, which this repository cannot see
VAULTLIB = re.compile(r"\bvaultlib\.(?!api\b)[A-Za-z_]\w*")


def files(root):
    """Every tracked file under extensions/ outside a tests/ folder."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "extensions"], capture_output=True, text=True, check=True)
    return [root / p for p in out.stdout.split() if "/tests/" not in f"/{p}"]


def exports(root):
    tree = ast.parse((root / "system/scripts/vaultlib/api.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "__all__" for t in node.targets):
            return set(ast.literal_eval(node.value))
    return set()


def problems(root, paths):
    """(problems, the API names the files use)."""
    allowed, out, used = exports(root), [], set()
    for path in paths:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in VAULTLIB.finditer(text):   # case 4: a vaultlib.<x> string, Python or not (python3 -c, importlib)
            out.append(f"{rel}: names {m.group(0)}")
        if path.suffix != ".py":
            continue
        bound = set()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == "vaultlib" or a.name.startswith("vaultlib."):   # case 1
                        out.append(f"{rel}:{node.lineno}: import {a.name}")
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "vaultlib":
                if node.module != API:   # case 1, whatever the line layout
                    out.append(f"{rel}:{node.lineno}: from {node.module} import")
                    continue
                for a in node.names:
                    if a.name not in allowed:   # case 2
                        out.append(f"{rel}:{node.lineno}: {a.name} is not in vaultlib.api.__all__")
                    used.add(a.name)
                    bound.add(a.asname or a.name)
        for node in ast.walk(ast.parse(text)):   # case 3: a private attribute of an API name
            if (isinstance(node, ast.Attribute) and node.attr.startswith("_") and isinstance(node.value, ast.Name)
                    and node.value.id in bound):
                out.append(f"{rel}:{node.lineno}: {node.value.id}.{node.attr} is private")
    return out, used


def is_vault():
    return (REPO / "system/config.md").exists()


@pytest.mark.skipif(is_vault(), reason="this checkout is a vault (system/config.md exists); the rule guards the template")
def test_extension_scripts_import_vaultlib_only_through_the_api():
    found, used = problems(REPO, files(REPO))
    assert found == []
    unused = exports(REPO) - used - KEEP
    assert unused == set(), "an export no extension script uses: drop it from vaultlib/api.py"


@pytest.mark.parametrize("code,want", [
    ("from vaultlib import now\n", "from vaultlib import"),
    ("from vaultlib.triage import (\n    one_line,\n    reply,\n)\n", "from vaultlib.triage import"),
    ("import vaultlib.now as n\n", "import vaultlib.now"),
    ("from vaultlib.api import nosuch\n", "nosuch is not in vaultlib.api.__all__"),
    ("from vaultlib.api import now\nnow._private()\n", "now._private is private"),
    ("import importlib\nimportlib.import_module('vaultlib.notify')\n", "names vaultlib.notify"),
])
def test_each_banned_form_is_caught(tmp_path, code, want):
    (tmp_path / "system/scripts/vaultlib").mkdir(parents=True)
    (tmp_path / "system/scripts/vaultlib/api.py").write_text((REPO / "system/scripts/vaultlib/api.py").read_text())
    script = tmp_path / "extensions/x/scripts/x.py"
    script.parent.mkdir(parents=True)
    script.write_text(code)
    found, _ = problems(tmp_path, [script])
    assert any(want in p for p in found), found


def test_a_shell_line_naming_a_vaultlib_module_is_caught(tmp_path):
    (tmp_path / "system/scripts/vaultlib").mkdir(parents=True)
    (tmp_path / "system/scripts/vaultlib/api.py").write_text((REPO / "system/scripts/vaultlib/api.py").read_text())
    script = tmp_path / "extensions/x/brief/prep.sh"
    script.parent.mkdir(parents=True)
    script.write_text('python3 -c "from vaultlib.now import read"\nprint vaultlib.api ok\n')
    found, _ = problems(tmp_path, [script])
    assert found == ["extensions/x/brief/prep.sh: names vaultlib.now"]
