"""Read-only, guarded SQL execution for `vault_index.py query` (spec §6.16)."""
import sqlite3
import time
from pathlib import Path

ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
READ_ONLY_PRAGMAS = {"table_info", "table_xinfo"}
MAX_RESULT_BYTES = 16 * 1024 * 1024


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
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only = 1")
        conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
        conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 64)
        deadline = time.monotonic() + timeout
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
        conn.set_authorizer(_authorizer)
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        rows = []
        total_bytes = 0
        for row in cursor:
            for v in row:
                if isinstance(v, (str, bytes)):
                    total_bytes += len(v)
                else:
                    total_bytes += 8
            if total_bytes > MAX_RESULT_BYTES:
                raise sqlite3.DatabaseError("result too large")
            rows.append(row)
            if len(rows) > limit:
                return columns, rows[:limit], True
        return columns, rows[:limit], len(rows) > limit
    finally:
        conn.close()
