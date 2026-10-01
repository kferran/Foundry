import sqlite3
import subprocess
from pathlib import Path

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


def test_related_text_ranks_and_filters(conn, vault):
    hits = retrieve.related(conn, retrieve.terms_for_text("kafka event streaming"))
    assert hits[0]["path"] in ("wiki/work/concepts/Kafka.md", "wiki/work/concepts/Streams.md")
    personal = retrieve.related(conn, retrieve.terms_for_text("tomatoes sun"), partitions=["work", "shared"])
    assert personal == []
    # Positive control: gardening note exists in personal partition
    write(vault, "wiki/personal/concepts/Gardening.md", concept("personal", "Gardening", "tomatoes sun grow"))
    # Need to recreate index to include the new note
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    unrestricted = retrieve.related(c, retrieve.terms_for_text("tomatoes sun"))
    assert any(h["path"] == "wiki/personal/concepts/Gardening.md" for h in unrestricted), "Gardening should be found without partition restriction"
    c.close()


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


def test_git_env_cannot_hijack_scope(vault, tmp_path, monkeypatch):
    """GIT_DIR env var should not hijack scope detection."""
    repo = git_init(tmp_path / "code")
    (repo / "f").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "f"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"], check=True)
    register(vault, "code", repo)
    unregistered = git_init(tmp_path / "unregistered")
    # Try to hijack scope via GIT_DIR
    monkeypatch.setenv("GIT_DIR", str(repo / ".git"))
    assert scope.caller_scope(vault, unregistered) is None


def test_relative_codebase_path_ignored(vault):
    """Relative codebase paths are skipped."""
    register(vault, "relcode", ".", partition="work")
    assert scope.codebases(vault) == []


def test_bad_codebase_files_skipped(vault):
    """Bad codebase files are skipped without raising."""
    # Non-UTF-8 file
    (Path(vault) / "system" / "codebases").mkdir(parents=True, exist_ok=True)
    (Path(vault) / "system" / "codebases" / "badutf8.md").write_bytes(b"---\nname: bad\n---\n\xff\xfe")
    # Invalid partition (array instead of string)
    write(vault, "system/codebases/badpart.md",
          '---\ntype: codebase\nname: badpart\npath: "/tmp"\npartition: [work, personal]\nsearch_globs: ["*"]\n---\n')
    # Invalid partition value (not in whitelist)
    write(vault, "system/codebases/unknownpart.md",
          '---\ntype: codebase\nname: unknownpart\npath: "/tmp"\npartition: all\nsearch_globs: ["*"]\n---\n')
    # All should be skipped
    assert scope.codebases(vault) == []


def test_duplicate_registration_fails_closed(vault, tmp_path):
    """Multiple registrations for same repo with different partitions return None (fail closed)."""
    repo = git_init(tmp_path / "code")
    (repo / "f").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "f"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"], check=True)
    register(vault, "code1", repo, partition="work")
    register(vault, "code2", repo, partition="personal")
    # Should return None (ambiguous)
    assert scope.caller_scope(vault, repo) is None


def test_find_note_respects_partitions(vault):
    """find_note filters by partition."""
    write(vault, "wiki/work/concepts/Dup.md", concept("work", "Dup", "duplicate"))
    write(vault, "wiki/personal/concepts/Dup.md", concept("personal", "Dup", "duplicate"))
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    # Without partition restriction, should find one (alphabetical or by active status)
    no_restrict = retrieve.find_note(c, vault, "dup")
    assert no_restrict in ("wiki/work/concepts/Dup.md", "wiki/personal/concepts/Dup.md")
    # With work+shared restriction
    work_restricted = retrieve.find_note(c, vault, "dup", partitions=["work", "shared"])
    assert work_restricted == "wiki/work/concepts/Dup.md"
    # With personal+shared restriction
    personal_restricted = retrieve.find_note(c, vault, "dup", partitions=["personal", "shared"])
    assert personal_restricted == "wiki/personal/concepts/Dup.md"
    # With shared only (no match)
    shared_only = retrieve.find_note(c, vault, "dup", partitions=["shared"])
    assert shared_only is None
    c.close()


def test_backlinks_hides_out_of_scope_target(vault):
    """backlinks returns [] if target is out of scope."""
    write(vault, "wiki/personal/concepts/Gardening.md", concept("personal", "Gardening", "tomatoes"))
    write(vault, "wiki/work/concepts/Recipe.md", concept("work", "Recipe", "[[Gardening]]"))
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    # Without partition restriction, should find the backlink
    all_backlinks = retrieve.backlinks(c, "wiki/personal/concepts/Gardening.md")
    assert "wiki/work/concepts/Recipe.md" in all_backlinks
    # With work+shared restriction on out-of-scope target (personal)
    restricted = retrieve.backlinks(c, "wiki/personal/concepts/Gardening.md", partitions=["work", "shared"])
    assert restricted == []
    c.close()


def test_nul_tag_does_not_crash(vault):
    """Nul character in tag does not crash related() query."""
    write(vault, "wiki/work/concepts/Tagged.md",
          '---\ntype: concept\npartition: work\ntitle: Tagged\ntags: ["a\\u0000b", "safe"]\n---\ntext')
    idx = Index(vault)
    idx.refresh()
    c = sqlite3.connect(idx.db_path)
    terms = retrieve.terms_for_note(c, "wiki/work/concepts/Tagged.md")
    # Should not raise OperationalError
    hits = retrieve.related(c, terms)
    assert isinstance(hits, list)
    c.close()
