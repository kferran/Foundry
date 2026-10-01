"""Read-only, guarded SQL execution for `vault_index.py query` (spec §6.16)."""
import sqlite3
import time

ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
READ_ONLY_PRAGMAS = {"table_info", "table_xinfo"}


def _authorizer(action, arg1, arg2, _db, _source):
    if action in ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA:
        if arg1 in READ_ONLY_PRAGMAS:
            return sqlite3.SQLITE_OK
        if arg1 == "data_version" and arg2 is None:
            return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def run_query(db_path, sql, *, limit=200, timeout=2.0):
    """Run one read-only statement. Returns (columns, rows, truncated)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = 1")
        conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        deadline = time.monotonic() + timeout
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
        conn.set_authorizer(_authorizer)
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchmany(limit + 1)
        return columns, rows[:limit], len(rows) > limit
    finally:
        conn.close()
