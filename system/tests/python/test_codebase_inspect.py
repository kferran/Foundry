"""Codebase inspection evidence (spec §6.13): vaultlib/codebase_inspect.py."""
import subprocess
from pathlib import Path

import pytest

from helpers import write
from vaultlib.codebase_inspect import NotARepo, inspect_repo, manifest_details

ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(root: Path, files: dict[str, str], branch: str = "main") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", branch)
    for rel, text in files.items():
        write(root, rel, text)
    git(root, "add", "-A")
    git(root, *ID, "commit", "-q", "--allow-empty", "-m", "init")
    return root


def by_file(result: dict) -> dict:
    return {m["file"]: m for m in result["manifests"]}


def test_vue_and_dotnet_pair(tmp_path):
    repo = make_repo(tmp_path / "r", {
        "ultron-ui/package.json": '{"name": "ui", "dependencies": {"vue": "^3"}, "devDependencies": {"@angular/core": "1", "lodash": "4"}}',
        "Ultron.Api/Ultron.Api.csproj": "<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework>"
                                        "<RootNamespace>Ultron.Api</RootNamespace></PropertyGroup></Project>",
        "Ultron.sln": "Microsoft Visual Studio Solution File",
    })
    m = by_file(inspect_repo(repo))
    assert m["ultron-ui/package.json"] == {"file": "ultron-ui/package.json", "dir": "ultron-ui", "kind": "npm",
                                           "details": {"name": "ui", "notable": ["angular", "vue"]}}
    assert m["Ultron.Api/Ultron.Api.csproj"]["details"] == {"TargetFramework": "net8.0", "RootNamespace": "Ultron.Api"}
    assert m["Ultron.sln"]["kind"] == "dotnet-solution"
    assert m["Ultron.sln"]["dir"] == "."


def test_go_python_rust_maven_ruby(tmp_path):
    repo = make_repo(tmp_path / "r", {
        "go.mod": "module example.com/svc\n\ngo 1.22\n",
        "py/pyproject.toml": '[project]\nname = "pkg"\n',
        "poetry/pyproject.toml": '[tool.poetry]\nname = "old-style"\n',
        "rs/Cargo.toml": '[package]\nname = "crate"\n',
        "jvm/pom.xml": "<project><parent><artifactId>parent-pom</artifactId></parent><artifactId>svc</artifactId></project>",
        "rb/Gemfile": "source 'https://rubygems.org'\n",
    })
    m = by_file(inspect_repo(repo))
    assert m["go.mod"]["details"] == {"module": "example.com/svc"}
    assert m["py/pyproject.toml"]["details"] == {"name": "pkg"}
    assert m["poetry/pyproject.toml"]["details"] == {"name": "old-style"}
    assert m["rs/Cargo.toml"]["details"] == {"name": "crate"}
    assert m["jvm/pom.xml"]["details"] == {"artifactId": "svc"}
    assert m["rb/Gemfile"] == {"file": "rb/Gemfile", "dir": "rb", "kind": "ruby", "details": {}}


@pytest.mark.parametrize("kind,text", [
    ("npm", "{not json"),
    ("npm", "[1, 2]"),
    ("python", "[project\nname ="),
    ("rust", "[package]\nname = = x"),
])
def test_malformed_manifest_reports_an_error_instead_of_crashing(kind, text):
    assert "error" in manifest_details(kind, text)


def test_malformed_manifest_inside_a_repo_is_reported(tmp_path):
    repo = make_repo(tmp_path / "r", {"web/package.json": "{nope", "go.mod": "module ok\n"})
    m = by_file(inspect_repo(repo))
    assert m["web/package.json"]["details"] == {"error": "unparseable: JSONDecodeError"}
    assert m["go.mod"]["details"] == {"module": "ok"}


def test_oversized_manifest_is_not_read(tmp_path):
    repo = make_repo(tmp_path / "r", {"package.json": " " * 1_000_001})
    assert by_file(inspect_repo(repo))["package.json"]["details"] == {"error": "too large"}


def test_only_tracked_files_count(tmp_path):
    repo = make_repo(tmp_path / "r", {"src/a.ts": "x", "Makefile": "all:"})
    write(repo, "node_modules/dep/package.json", '{"name": "dep"}')
    write(repo, "src/untracked.py", "x")
    result = inspect_repo(repo)
    assert result["manifests"] == []
    assert result["extensions"] == {"(none)": 1, "ts": 1}


def test_layer_candidates_are_top_level_dirs_with_their_own_manifest(tmp_path):
    repo = make_repo(tmp_path / "r", {
        "package.json": "{}",
        "ui/package.json": "{}",
        "Api/Api.csproj": "<Project/>",
        "apps/web/package.json": "{}",
    })
    assert inspect_repo(repo)["layer_candidates"] == ["Api/", "ui/"]


def test_logging_hints_count_lines_and_cap_examples(tmp_path):
    files = {f"src/f{i:02d}.cs": "_logger.LogInformation(new EventId(1));\n" for i in range(12)}
    files["src/b.ts"] = "logger.info(1)\nlog.warn(2)\ncatalog.items()\n"
    repo = make_repo(tmp_path / "r", files)
    hints = inspect_repo(repo)["logging_hints"]
    assert hints["EventId"]["count"] == 12
    assert len(hints["EventId"]["examples"]) == 10
    assert hints["EventId"]["examples"][0] == "src/f00.cs"
    assert hints["logger."] == {"count": 1, "examples": ["src/b.ts"]}
    assert hints["log."] == {"count": 1, "examples": ["src/b.ts"]}
    assert hints["ILogger"] == {"count": 0, "examples": []}


def test_git_default_branch_from_origin_head(tmp_path):
    upstream = make_repo(tmp_path / "up", {"a": "x"}, branch="trunk")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(upstream), str(clone)], check=True)
    git(clone, "checkout", "-q", "-b", "feature")
    assert inspect_repo(clone)["git"] == {"default_branch": "trunk", "remote": str(upstream)}


def test_git_default_branch_falls_back_to_the_current_branch(tmp_path):
    repo = make_repo(tmp_path / "r", {"a": "x"}, branch="work")
    assert inspect_repo(repo)["git"] == {"default_branch": "work", "remote": None}


def test_a_subdirectory_inspects_the_whole_repo(tmp_path):
    repo = make_repo(tmp_path / "r", {"go.mod": "module m\n", "sub/x.go": "package x"})
    result = inspect_repo(repo / "sub")
    assert result["path"] == str(repo.resolve())
    assert "go.mod" in by_file(result)


def test_not_a_repo(tmp_path):
    with pytest.raises(NotARepo):
        inspect_repo(tmp_path)



def test_per_kind_keeps_the_shallowest_manifests_and_counts_every_one(tmp_path):
    files = {f"src/P{i}/P{i}.csproj": "<Project/>" for i in range(7)}
    files.update({"App.csproj": "<Project/>", "web/package.json": '{"dependencies": {"vue": "3"}}',
                  "tools/admin/package.json": '{"dependencies": {"react": "18"}}'})
    repo = make_repo(tmp_path / "r", files)
    result = inspect_repo(repo, per_kind=3)
    assert [m["file"] for m in result["manifests"]] == [
        "App.csproj", "src/P0/P0.csproj", "src/P1/P1.csproj", "tools/admin/package.json", "web/package.json"]
    assert result["manifest_counts"] == {"dotnet": 8, "npm": 2}
    one = inspect_repo(repo, per_kind=1)
    assert [m["file"] for m in one["manifests"]] == ["App.csproj", "web/package.json"]
    assert one["notable"] == ["react", "vue"]  # the dropped tools/admin manifest still counts
    assert len(inspect_repo(repo)["manifests"]) == 10
