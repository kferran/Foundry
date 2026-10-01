"""SQLite index over the vault (spec §6.16): locked incremental refresh, issues, views."""
import contextlib
import fcntl
import hashlib
import json
import os
import posixpath
import sqlite3
import time
from pathlib import Path

from . import frontmatter, links as linkmod, schema as schemamod

INDEX_VERSION = "1"
PRUNE = {".git", ".obsidian"}
NOT_INDEXED = ("system/logs/", "system/quarantine/", "system/fleet/", "system/templates/",
               "system/tests/", "docs/", "raw/inbox/", "raw/archive/")
SKIP_FILES = ("system/index.db", "system/index.lock")
TABLES = ("files", "notes", "fields", "links", "tags", "issues", "notes_fts")

DDL = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime REAL, size INTEGER);
CREATE TABLE IF NOT EXISTS notes(path TEXT PRIMARY KEY, type TEXT, title TEXT, folder TEXT,
  partition TEXT, mtime REAL, size INTEGER, sha256 TEXT, valid INTEGER, active INTEGER, body_line INTEGER);
CREATE TABLE IF NOT EXISTS fields(path TEXT, key TEXT, value TEXT);
CREATE INDEX IF NOT EXISTS fields_path ON fields(path);
CREATE INDEX IF NOT EXISTS fields_key ON fields(key, value);
CREATE TABLE IF NOT EXISTS links(src TEXT, target_raw TEXT, target TEXT, target_path TEXT,
  line INTEGER, kind TEXT, ambiguous INTEGER);
CREATE INDEX IF NOT EXISTS links_src ON links(src);
CREATE INDEX IF NOT EXISTS links_target ON links(target_path);
CREATE TABLE IF NOT EXISTS tags(path TEXT, tag TEXT);
CREATE TABLE IF NOT EXISTS issues(path TEXT, line INTEGER, severity TEXT, code TEXT, message TEXT, scope TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(path UNINDEXED, title, aliases, body);
"""


def first_heading(body: str) -> str | None:
    for line in body.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return None


class Index:
    def __init__(self, vault, db_path=None):
        self.vault = Path(vault)
        self.db_path = Path(db_path) if db_path else self.vault / "system" / "index.db"
        self.lock_path = self.vault / "system" / "index.lock"
        self.ctx = schemamod.Context(self.vault)

    @contextlib.contextmanager
    def locked(self, timeout=None):
        """Exclusive fcntl lock on system/index.lock (released by the kernel on crash)."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a") as handle:
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TimeoutError("index lock busy")
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(DDL)
        return conn

    def _open_or_rebuild(self) -> sqlite3.Connection:
        try:
            conn = self.connect()
            conn.execute("SELECT count(*) FROM meta").fetchone()
            return conn
        except sqlite3.DatabaseError:
            for suffix in ("", "-wal", "-shm"):
                with contextlib.suppress(FileNotFoundError):
                    os.remove(f"{self.db_path}{suffix}")
            return self.connect()

    def schema_hash(self) -> str:
        digest = hashlib.sha256(INDEX_VERSION.encode())
        for path in sorted((self.vault / "system" / "schemas").glob("*.md")):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def walk(self):
        """Yield (rel, abs_path, stat) for every vault file, pruning dot-directories."""
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in PRUNE]
            for name in files:
                if name.startswith("."):
                    continue
                path = Path(root) / name
                rel = path.relative_to(self.vault).as_posix()
                if rel.startswith(SKIP_FILES):
                    continue
                try:
                    yield rel, path, path.stat()
                except FileNotFoundError:
                    continue

    def refresh(self, timeout=None, full=False) -> None:
        with self.locked(timeout):
            conn = self._open_or_rebuild()
            try:
                with conn:
                    self._refresh(conn, full)
            finally:
                conn.close()

    def _refresh(self, conn, full):
        schemas = schemamod.load_schemas(self.vault)
        shash = self.schema_hash()
        row = conn.execute("SELECT value FROM meta WHERE key='schema_hash'").fetchone()
        rebuild = full or row is None or row[0] != shash
        if rebuild:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
        old = {p: (m, s) for p, m, s in conn.execute("SELECT path, mtime, size FROM files")}
        seen = {}
        changed = rebuild
        for rel, path, st in self.walk():
            seen[rel] = (st.st_mtime, st.st_size)
            if old.get(rel) != seen[rel]:
                changed = True
                if rel.endswith(".md") and not rel.startswith(NOT_INDEXED):
                    self._index_note(conn, schemas, rel, path, st)
        for rel in set(old) - set(seen):
            changed = True
            self._drop_note(conn, rel)
        if not changed:
            return
        conn.execute("DELETE FROM files")
        conn.executemany("INSERT INTO files VALUES(?,?,?)", [(p, m, s) for p, (m, s) in seen.items()])
        self._resolve_links(conn, set(seen))
        self._global_issues(conn, schemas)
        self._views(conn, schemas)
        conn.execute("INSERT OR REPLACE INTO meta VALUES('schema_hash', ?)", (shash,))
        conn.execute("INSERT OR REPLACE INTO meta VALUES('built_at', ?)", (str(time.time()),))

    def _drop_note(self, conn, rel):
        for sql in ("DELETE FROM notes WHERE path=?", "DELETE FROM fields WHERE path=?",
                    "DELETE FROM links WHERE src=?", "DELETE FROM tags WHERE path=?",
                    "DELETE FROM issues WHERE path=? AND scope='note'", "DELETE FROM notes_fts WHERE path=?"):
            conn.execute(sql, (rel,))

    def _index_note(self, conn, schemas, rel, path, st):
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        prev = conn.execute("SELECT sha256 FROM notes WHERE path=?", (rel,)).fetchone()
        if prev and prev[0] == sha:
            conn.execute("UPDATE notes SET mtime=?, size=? WHERE path=?", (st.st_mtime, st.st_size, rel))
            return
        self._drop_note(conn, rel)
        note = frontmatter.parse(data.decode("utf-8", errors="replace"))
        ntype, issues = schemamod.validate_note(schemas, rel, note, self.ctx)
        fm = note.data or {}
        if ntype is None and isinstance(fm.get("type"), str):
            ntype = fm["type"]
        title = first_heading(note.body) or Path(rel).stem
        inactive = (fm.get("status") == "deprecated" or schemamod.link_target(fm.get("superseded_by"))
                    or bool(fm.get("rejected_at")))
        valid = 0 if any(i.severity == "error" for i in issues) else 1
        conn.execute("INSERT INTO notes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (rel, ntype, title, posixpath.dirname(rel), schemamod.path_partition(rel),
                      st.st_mtime, st.st_size, sha, valid, 0 if inactive else 1, note.body_line))
        for key, value in fm.items():
            conn.execute("INSERT INTO fields VALUES(?,?,?)",
                         (rel, str(key), value if isinstance(value, str) else json.dumps(value)))
        body_links, tags = linkmod.extract(note.body, note.body_line)
        for link in body_links + self._frontmatter_links(schemas.get(ntype), note):
            conn.execute("INSERT INTO links VALUES(?,?,?,?,?,?,?)",
                         (rel, link.target_raw, link.target, None, link.line, link.kind, 0))
        fm_tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
        for tag in {str(t) for t in fm_tags} | tags:
            conn.execute("INSERT INTO tags VALUES(?,?)", (rel, tag))
        aliases = fm.get("aliases") if isinstance(fm.get("aliases"), list) else []
        conn.execute("INSERT INTO notes_fts(path, title, aliases, body) VALUES(?,?,?,?)",
                     (rel, title, " ".join(map(str, aliases)), note.body))
        for issue in issues:
            conn.execute("INSERT INTO issues VALUES(?,?,?,?,?,'note')",
                         (issue.path, issue.line, issue.severity, issue.code, issue.message))

    def _frontmatter_links(self, sch, note):
        out = []
        if sch is None or note.data is None:
            return out
        for name, spec in sch.fields.items():
            if name not in note.data:
                continue
            value = note.data[name]
            if spec.kind == "link":
                items = [value]
            elif spec.kind == "list" and spec.of and spec.of.kind == "link" and isinstance(value, list):
                items = value
            else:
                continue
            for item in items:
                target = schemamod.link_target(item)
                if target:
                    out.append(linkmod.Link(f"[[{target}]]", linkmod.wiki_target(target),
                                            frontmatter.key_line(note, name), f"frontmatter:{name}"))
        return out

    def _resolve_links(self, conn, files):
        meta = {p: (part, act) for p, part, act in conn.execute("SELECT path, partition, active FROM notes")}
        resolver = linkmod.Resolver(files)
        for rowid, src, target, kind in conn.execute("SELECT rowid, src, target, kind FROM links").fetchall():
            src_part = schemamod.path_partition(src)
            src_dir = posixpath.dirname(src)

            def prefer(candidate, src_part=src_part, src_dir=src_dir):
                part, active = meta.get(candidate, (schemamod.path_partition(candidate), 1))
                part_rank = 0 if part == src_part else (1 if part == "shared" else 2)
                return (0 if active else 1, part_rank, 0 if posixpath.dirname(candidate) == src_dir else 1,
                        len(candidate), candidate)

            hit, ambiguous = resolver.resolve(target, src, "md" if kind == "md" else "wiki", prefer)
            conn.execute("UPDATE links SET target_path=?, ambiguous=? WHERE rowid=?",
                         (hit, 1 if ambiguous else 0, rowid))

    def _global_issues(self, conn, schemas):
        """Implemented in Task 9."""
        conn.execute("DELETE FROM issues WHERE scope='global'")

    def _views(self, conn, schemas):
        """Implemented in Task 9."""
