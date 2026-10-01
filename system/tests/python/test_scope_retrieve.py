import sqlite3
import subprocess

import pytest

from helpers import concept, write
from vaultlib import retrieve, scope
from vaultlib.index import Index


def git_init(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def register(vault, name, path, partition="work"):
    write(vault, f"system/codebases/{name}.md",
          f'---\ntype: codebase\nname: {name}\npath: "{path}"\npartition: {partition}\nsearch_globs: ["*"]\n---\n')


def test_scope_vault_and_subdirectory(vault):
    assert scope.caller_scope(vault, vault) == ("vault", None, None)
    assert scope.caller_scope(vault, vault / "wiki") == ("vault", None, None)


def test_scope_codebase_and_worktree(vault, tmp_path):
    repo = git_init(tmp_path / "code")
    (repo / "f").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "f"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"], check=True)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(wt)], check=True)
    register(vault, "code", repo)
    assert scope.caller_scope(vault, repo) == ("codebase", "code", "work")
    assert scope.caller_scope(vault, wt) == ("codebase", "code", "work")


def test_scope_unregistered(vault, tmp_path):
    assert scope.caller_scope(vault, git_init(tmp_path / "other")) is None
    assert scope.caller_scope(vault, tmp_path) is None


def test_example_codebase_ignored(vault, tmp_path):
    repo = git_init(tmp_path / "code")
    write(vault, "system/codebases/example.md",
          f'---\ntype: codebase\nname: example\npath: "{repo}"\npartition: work\nsearch_globs: ["*"]\n---\n')
    assert scope.codebases(vault) == []


def test_allowed_partitions():
    assert scope.allowed_partitions(("vault", None, None)) is None
    assert scope.allowed_partitions(("codebase", "x", "work")) == ["work", "shared"]


@pytest.fixture
def conn(vault):
    write(vault, "wiki/work/concepts/Streams.md", concept("work", "Streams", "Kafka streams process events. [[Kafka]]"))
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    yield c
    c.close()


def test_related_text_ranks_and_filters(conn):
    hits = retrieve.related(conn, retrieve.terms_for_text("kafka event streaming"))
    assert hits[0]["path"] in ("wiki/work/concepts/Kafka.md", "wiki/work/concepts/Streams.md")
    personal = retrieve.related(conn, retrieve.terms_for_text("tomatoes sun"), partitions=["work", "shared"])
    assert personal == []


def test_related_path_excludes_self(conn):
    terms = retrieve.terms_for_note(conn, "wiki/work/concepts/Kafka.md")
    hits = retrieve.related(conn, terms, exclude="wiki/work/concepts/Kafka.md")
    assert "wiki/work/concepts/Kafka.md" not in [h["path"] for h in hits]


def test_related_per_source_cap(vault):
    for i in range(4):
        write(vault, f"wiki/work/concepts/N{i}.md", concept("work", f"N{i}", "zebra facts [[Index]]", sources='["[[digest-one]]"]'))
    write(vault, "raw/work/archive/digest-one.md", "x")
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    assert len(retrieve.related(c, ["zebra"], per_source=2)) == 2
    assert len(retrieve.related(c, ["zebra"], per_source=10)) == 4


def test_related_excludes_inactive(vault):
    write(vault, "wiki/work/concepts/Old.md", concept("work", "Old", "quokka", status="deprecated"))
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    assert retrieve.related(c, ["quokka"]) == []
    assert len(retrieve.related(c, ["quokka"], include_inactive=True)) == 1


def test_backlinks_and_orphans(conn):
    assert "wiki/work/concepts/Kafka.md" in retrieve.backlinks(conn, "wiki/shared/concepts/Git.md")
    assert retrieve.backlinks(conn, "wiki/shared/concepts/Git.md", partitions=["personal"]) == []
    assert "wiki/work/concepts/Streams.md" in retrieve.orphans(conn)


def test_find_note(conn, vault):
    assert retrieve.find_note(conn, vault, "kafka") == "wiki/work/concepts/Kafka.md"
    assert retrieve.find_note(conn, vault, "wiki/shared/concepts/Git.md") == "wiki/shared/concepts/Git.md"
    assert retrieve.find_note(conn, vault, "nope") is None
