import os
import sqlite3
import threading
import time

import pytest

from helpers import concept, write
from vaultlib.index import Index


def rows(idx, sql, *args):
    conn = sqlite3.connect(idx.db_path)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def test_first_build_populates_tables(vault):
    idx = Index(vault)
    idx.refresh()
    paths = {p for (p,) in rows(idx, "SELECT path FROM notes")}
    assert "wiki/work/concepts/Kafka.md" in paths and "wiki/Index.md" in paths
    assert rows(idx, "SELECT title, partition, type FROM notes WHERE path='wiki/work/concepts/Kafka.md'") == [("Kafka", "work", "concept")]
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/Kafka.md'") == [("wiki/shared/concepts/Git.md",)]
    assert ("streaming",) in rows(idx, "SELECT tag FROM tags WHERE path='wiki/work/concepts/Kafka.md'")
    assert rows(idx, "SELECT path FROM notes_fts WHERE notes_fts MATCH 'commit'") == [("wiki/work/concepts/Kafka.md",)]


def test_unchanged_refresh_parses_nothing(vault, monkeypatch):
    idx = Index(vault)
    idx.refresh()
    calls = []
    original = Index._index_note
    monkeypatch.setattr(Index, "_index_note", lambda self, *a: calls.append(a) or original(self, *a))
    idx.refresh()
    assert calls == []


def test_edit_reparses_only_that_note(vault, monkeypatch):
    idx = Index(vault)
    idx.refresh()
    calls = []
    original = Index._index_note
    monkeypatch.setattr(Index, "_index_note", lambda self, conn, schemas, rel, *a: calls.append(rel) or original(self, conn, schemas, rel, *a))
    write(vault, "wiki/work/concepts/Kafka.md", concept("work", "Kafka", "rewritten body"))
    idx.refresh()
    assert calls == ["wiki/work/concepts/Kafka.md"]
    assert rows(idx, "SELECT path FROM notes_fts WHERE notes_fts MATCH 'rewritten'") == [("wiki/work/concepts/Kafka.md",)]


def test_refresh_detects_same_size_edit(vault):
    idx = Index(vault)
    path = write(vault, "wiki/work/concepts/Same.md", concept("work", "Same", "aaaa"))
    idx.refresh()
    path.write_text(concept("work", "Same", "bbbb"), encoding="utf-8")
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1000))
    idx.refresh()
    assert rows(idx, "SELECT path FROM notes_fts WHERE notes_fts MATCH 'bbbb'") == [("wiki/work/concepts/Same.md",)]


def test_delete_removes_rows_and_kills_inbound_links(vault):
    idx = Index(vault)
    idx.refresh()
    (vault / "wiki/shared/concepts/Git.md").unlink()
    idx.refresh()
    assert rows(idx, "SELECT count(*) FROM notes WHERE path='wiki/shared/concepts/Git.md'") == [(0,)]
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/Kafka.md'") == [(None,)]


def test_new_file_resolves_previously_dead_link(vault):
    idx = Index(vault)
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", "see [[Later]]"))
    idx.refresh()
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/A.md'") == [(None,)]
    write(vault, "wiki/work/concepts/Later.md", concept("work", "Later"))
    idx.refresh()
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/A.md'") == [("wiki/work/concepts/Later.md",)]


def test_schema_change_triggers_full_rebuild(vault):
    idx = Index(vault)
    idx.refresh()
    schema_file = vault / "system/schemas/index.md"
    schema_file.write_text(schema_file.read_text() + "\nedited\n")
    idx.refresh()
    assert rows(idx, "SELECT count(*) FROM notes")[0][0] >= 4


def test_corrupt_db_is_rebuilt(vault):
    idx = Index(vault)
    idx.refresh()
    idx.db_path.write_bytes(b"not a database at all" * 100)
    for suffix in ("-wal", "-shm"):
        p = idx.db_path.with_name(idx.db_path.name + suffix)
        if p.exists():
            p.unlink()
    idx.refresh()
    assert rows(idx, "SELECT count(*) FROM notes")[0][0] >= 4


def test_plain_markdown_note_is_an_error_not_a_crash(vault):
    write(vault, "wiki/work/concepts/Plain.md", "# Plain\njust text")
    idx = Index(vault)
    idx.refresh()
    assert rows(idx, "SELECT code FROM issues WHERE path='wiki/work/concepts/Plain.md' AND severity='error'") == [("frontmatter",)]
    assert rows(idx, "SELECT count(*) FROM notes WHERE path='wiki/work/concepts/Kafka.md'") == [(1,)]


def test_excluded_folders_not_indexed_but_resolvable(vault):
    write(vault, "raw/archive/source-note.md", "raw text")
    write(vault, "system/logs/alerts_2026-09-30.md", "# alert")
    write(vault, "wiki/work/concepts/B.md", concept("work", "B", "from [[source-note]]"))
    idx = Index(vault)
    idx.refresh()
    indexed = {p for (p,) in rows(idx, "SELECT path FROM notes")}
    assert "raw/archive/source-note.md" not in indexed and "system/logs/alerts_2026-09-30.md" not in indexed
    assert rows(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/B.md'") == [("raw/archive/source-note.md",)]


def test_dot_directories_pruned(vault):
    write(vault, "wiki/.staging/run1/wiki/work/concepts/S.md", concept("work", "S"))
    idx = Index(vault)
    idx.refresh()
    assert rows(idx, "SELECT count(*) FROM notes WHERE path LIKE 'wiki/.staging/%'") == [(0,)]


def test_concurrent_refresh_serializes(vault):
    idx = Index(vault)
    errors = []

    def worker():
        try:
            Index(vault).refresh(timeout=10)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert rows(idx, "SELECT count(*) FROM notes WHERE path='wiki/Index.md'") == [(1,)]


def test_lock_timeout(vault):
    idx = Index(vault)
    with idx.locked():
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            Index(vault).refresh(timeout=0.2)
        assert time.monotonic() - start < 2
