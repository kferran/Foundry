import shutil
import sqlite3
from pathlib import Path

import pytest

from vaultlib import guard
from vaultlib.index import Index


@pytest.fixture
def db(vault):
    idx = Index(vault)
    idx.refresh()
    return idx.db_path


def test_select_works(db):
    cols, rows, truncated = guard.run_query(db, "SELECT path FROM notes WHERE path='wiki/Index.md'")
    assert cols == ["path"] and rows == [("wiki/Index.md",)] and truncated is False


def test_fts_match_works(db):
    _, rows, _ = guard.run_query(db, "SELECT path FROM notes_fts WHERE notes_fts MATCH 'tomatoes'")
    assert rows == [("wiki/personal/concepts/Gardening.md",)]


def test_recursive_cte_and_table_info(db):
    assert guard.run_query(db, "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r WHERE x<3) SELECT count(*) FROM r")[1] == [(3,)]
    cols, rows, _ = guard.run_query(db, "SELECT name FROM pragma_table_info('notes')")
    assert ("path",) in rows


def test_views_work(db):
    _, rows, _ = guard.run_query(db, "SELECT path FROM v_concept WHERE partition='work'")
    assert rows == [("wiki/work/concepts/Kafka.md",)]


@pytest.mark.parametrize("sql", [
    "INSERT INTO notes(path) VALUES('x')",
    "DELETE FROM notes",
    "CREATE TABLE t(a)",
    "ATTACH DATABASE '/tmp/x.db' AS y",
    "PRAGMA journal_mode=DELETE",
    "DROP VIEW v_concept",
    "UPDATE sqlite_master SET sql = ''",
    "PRAGMA writable_schema = ON",
])
def test_writes_rejected(db, sql):
    with pytest.raises(sqlite3.DatabaseError):
        guard.run_query(db, sql)


def test_multiple_statements_rejected(db):
    with pytest.raises((sqlite3.ProgrammingError, sqlite3.DatabaseError)):
        guard.run_query(db, "SELECT 1; DELETE FROM notes")


def test_row_cap(db):
    _, rows, truncated = guard.run_query(db, "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r WHERE x<500) SELECT x FROM r", limit=10)
    assert len(rows) == 10 and truncated is True


def test_uri_escaping(tmp_path, vault):
    """URI must escape special chars like # so mode=ro isn't silently dropped."""
    hashed_vault = tmp_path / "ha#sh" / "vault"
    shutil.copytree(vault, hashed_vault)
    idx = Index(hashed_vault)
    idx.refresh()
    cols, rows, _ = guard.run_query(idx.db_path, "SELECT count(*) FROM notes")
    assert rows[0][0] > 0, "Should return note count from database"
    assert not (tmp_path / "ha").exists(), "SQLite should not create a file named 'ha' due to unescaped #"


def test_large_value_rejected(db):
    """Single large values should be rejected."""
    with pytest.raises(sqlite3.DatabaseError):
        guard.run_query(db, "SELECT zeroblob(2000000)")


def test_result_byte_budget(db):
    """Result set exceeding byte budget should be rejected."""
    with pytest.raises(sqlite3.DatabaseError, match="result too large"):
        guard.run_query(db, "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM r WHERE x<100) SELECT zeroblob(900000) FROM r", limit=200)


def test_runaway_query_times_out(db):
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        guard.run_query(db, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c", timeout=0.2)
