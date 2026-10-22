"""SQLite index over the vault (spec §6.16): locked incremental refresh, issues, views."""
import contextlib
import fcntl
import hashlib
import importlib.util
import itertools
import json
import os
import posixpath
import re
import sqlite3
import sys
import time
from pathlib import Path

from . import extensions as extmod, frontmatter, links as linkmod, schema as schemamod

INDEX_VERSION = "2"   # 2: tag issues (#158), so a rebuild lints notes whose bytes did not change
PRUNE = {".git", ".obsidian"}
NOT_INDEXED = ("system/logs/", "system/quarantine/", "system/jobs/", "system/templates/",
               "system/tests/", "docs/", "raw/inbox/", "raw/archive/", "raw/meetings/", "meetings/drop/",
               "extensions/")  # code and manifests, never notes: walk() prunes it, and staged lint skips it too
# Walked but never indexed: reachable by explicit path, never by bare [[Name]].
NAME_EXCLUDED = ("system/tests/", "system/templates/", "system/schemas/", "system/agents/", "docs/",
                 "system/quarantine/", "wiki/.staging/",  # run copies keep their note names
                 "system/codebases/", "system/nightshift/")  # named after what they configure


def name_excluded(vault) -> tuple:
    """NAME_EXCLUDED plus system/<name>/ of each present extension, which holds its config notes (factory F2 §3.1)."""
    return NAME_EXCLUDED + tuple(f"system/{name}/" for name, _ in extmod.present(vault))


def lint_modules(vault) -> list:
    """(name, rel, module or the exception it raised) for each present extension's `lint` module (extensions spec §3)."""
    out = []
    for name, data in extmod.present(vault):
        rel = data.get("lint")
        if not isinstance(rel, str) or not rel:
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"foundry_ext_{name}_lint",
                                                          Path(vault) / "extensions" / name / rel)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 - one extension's rules never stop the lint
            module = exc
        out.append((name, rel, module))
    return out


def cited(vault) -> dict:
    """{note type: open statuses} whose notes' citations are checked, from each present lint module's CITED."""
    out = {}
    for _, _, module in lint_modules(vault):
        for ntype, statuses in (getattr(module, "CITED", None) or {}).items():
            out[str(ntype)] = [str(s) for s in statuses]
    return out
SKIP_FILES = ("system/index.db", "system/index.lock")
PRIVATE = re.compile(r"^wiki/[^/]+/private/")  # read-denied (#166): never walked, staged, published or opened
ROOT_DOCS = {"README.md", "README.local.md", "FOUNDRY.md", "CLAUDE.md", "CHANGELOG.md"}   # the only Markdown files the root holds
TABLES = ("files", "notes", "fields", "links", "tags", "issues", "notes_fts")
ISSUE_ROWS = "SELECT path, line, severity, code, message FROM issues ORDER BY severity, path, line"

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


WALLS = {("work", "personal"), ("personal", "work"), ("shared", "work"), ("shared", "personal")}


def wall_blocked(src_partition: str, target_partition: str) -> bool:
    return (src_partition, target_partition) in WALLS


CITATION = re.compile(r"(?<![\w/:.-])([\w.-]+(?:/[\w.-]+)+\.[A-Za-z]\w*):(\d+)\b")


def citation_issues(conn, cited: dict = None) -> list:
    """Warning rows for each `dir/file.ext:NN` in an active codebase note, or an active note of a type in `cited`
    ({type: open statuses}, from extensions' lint modules; a note with no status is open), outside fences, that names
    a file missing from the codebase or shorter than NN lines (#166). A cited note names its codebase by file name in
    its `codebase` field, system/codebases/<codebase>.md; a codebase note's citation may also sit under one of its
    `layers`. Read at lint time, never cached, since the code moves on its own; a codebase not on this machine, bare
    file names and vendored paths are skipped."""
    codebases = {posixpath.basename(p)[:-3]: (root, layers) for p, root, layers in conn.execute(
        "SELECT n.path, (SELECT value FROM fields WHERE path=n.path AND key='path'), "
        "(SELECT value FROM fields WHERE path=n.path AND key='layers') FROM notes n WHERE n.type='codebase'")}
    rows, cited = [], cited or {}
    for path, ntype, body_line, body, name, status in conn.execute(
            "SELECT n.path, n.type, n.body_line, f.body, (SELECT value FROM fields WHERE path=n.path AND key='codebase'), "
            "(SELECT value FROM fields WHERE path=n.path AND key='status') "
            "FROM notes n JOIN notes_fts f ON f.path=n.path WHERE n.active=1 ORDER BY n.path").fetchall():
        if ntype != "codebase" and (ntype not in cited or (status is not None and status not in cited[ntype])):
            continue
        name = posixpath.basename(path)[:-3] if ntype == "codebase" else name
        root, layers = codebases.get(name, (None, None))
        if not root or not (root := Path(os.path.expanduser(root)).resolve()).is_dir():
            continue
        try:
            layers = json.loads(layers) if ntype == "codebase" and layers else {}
        except ValueError:
            layers = {}
        bases = [root] + [root / str(d) for d in (layers.values() if isinstance(layers, dict) else [])]
        fence = None
        for i, line in enumerate(body.split("\n")):
            if (fm := linkmod.FENCE.match(line)) and fence in (None, fm.group(1)):
                fence = None if fence else fm.group(1)
                continue
            for m in [] if fence else CITATION.finditer(line):
                cite, need = m.group(1), int(m.group(2))
                if re.search(r"(^|/)(node_modules|vendor)/", cite):
                    continue
                targets = [t for t in ((b / cite).resolve() for b in bases) if root in t.parents and t.is_file()]
                if not targets:
                    rows.append((path, body_line + i, "warning", "citation",
                                 f"citation {cite}:{need}: no such file in codebase {name}"))
                    continue
                try:
                    with open(targets[0], "rb") as fh:
                        have = sum(1 for _ in itertools.islice(fh, need))
                except OSError:
                    continue
                if have < need:
                    rows.append((path, body_line + i, "warning", "citation",
                                 f"citation {cite}:{need}: the file has {have} lines"))
    return rows


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
        for path in schemamod.extension_schema_paths(self.vault):
            digest.update(path.relative_to(self.vault).as_posix().encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def walk(self):
        """Yield (rel, abs_path, stat) for every vault file, pruning dot-directories."""
        ignored = tuple(p.strip("/") + "/" for p in extmod.ignore(self.vault) if p.strip("/"))
        for root, dirs, files in os.walk(self.vault):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in PRUNE]
            if Path(root) == self.vault:   # extensions/ holds code and manifests, never notes
                dirs[:] = [d for d in dirs if d != "extensions"]
            for name in files:
                if name.startswith("."):
                    continue
                path = Path(root) / name
                if path.is_symlink():
                    continue
                rel = path.relative_to(self.vault).as_posix()
                if rel.startswith(SKIP_FILES) or rel.startswith(ignored) or PRIVATE.match(rel):
                    continue
                try:
                    rel.encode()  # a non-UTF-8 name (e.g. Latin-1) decodes to surrogates, which SQLite cannot store
                    st = path.stat()
                except UnicodeEncodeError:
                    print(f"index: skipping {ascii(rel)}: name is not valid UTF-8", file=sys.stderr)
                    continue
                except FileNotFoundError:
                    continue
                yield rel, path, st

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
        conn.execute("INSERT OR REPLACE INTO meta VALUES('version', ?)", (INDEX_VERSION,))
        conn.execute("INSERT OR REPLACE INTO meta VALUES('built_at', ?)", (str(time.time()),))

    def staged_issues(self, blobs, db_path) -> list:
        """Issue rows with each note in blobs (rel -> bytes) read from those bytes (the staged lint, #166).
        The live index is refreshed and copied to db_path under the lock; only the blobs are reindexed in the
        copy, so the live index never caches them and links resolve against the rest of the vault."""
        with self.locked():
            conn = self._open_or_rebuild()
            try:
                with conn:
                    self._refresh(conn, False)
                copy = sqlite3.connect(db_path)
                conn.backup(copy)
            finally:
                conn.close()
        try:
            with copy:
                schemas = schemamod.load_schemas(self.vault)
                for rel, data in blobs.items():
                    path = self.vault / rel
                    st = path.stat() if path.exists() else os.stat_result((0,) * 10)
                    self._index_note(copy, schemas, rel, path, st, data)
                files = {p for (p,) in copy.execute("SELECT path FROM files")} | set(blobs)
                self._resolve_links(copy, files)
                self._global_issues(copy, schemas)
            return copy.execute(ISSUE_ROWS).fetchall()
        finally:
            copy.close()

    def _drop_note(self, conn, rel):
        for sql in ("DELETE FROM notes WHERE path=?", "DELETE FROM fields WHERE path=?",
                    "DELETE FROM links WHERE src=?", "DELETE FROM tags WHERE path=?",
                    "DELETE FROM issues WHERE path=? AND scope='note'", "DELETE FROM notes_fts WHERE path=?"):
            conn.execute(sql, (rel,))

    def _index_note(self, conn, schemas, rel, path, st, data=None):
        try:
            data = path.read_bytes() if data is None else data
        except OSError as exc:
            self._drop_note(conn, rel)
            conn.execute("INSERT INTO issues VALUES(?,?,?,?,?,'note')",
                         (rel, 1, "error", "unreadable", f"cannot read note: {exc}"))
            return
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
                         (rel, str(key), value if isinstance(value, str) else json.dumps(value, default=str)))
        body_links, tags = linkmod.extract(note.body, note.body_line)
        for link in body_links + self._frontmatter_links(schemas.get(ntype), note):
            conn.execute("INSERT INTO links VALUES(?,?,?,?,?,?,?)",
                         (rel, link.target_raw, link.target, None, link.line, link.kind, 0))
        fm_tags = fm.get("tags") if isinstance(fm.get("tags"), list) else []
        if "tags" in getattr(schemas.get(ntype), "fields", {}):   # concept, index and rca carry tags
            issues = list(issues) + schemamod.tag_issues(rel, ntype, note, fm_tags)
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
        resolver = linkmod.Resolver(files, name_exclude=name_excluded(self.vault))
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

    def _display(self, raw: str, kind: str) -> str:
        """Format a link target for display based on link kind.

        - Wikilinks (link, embed): wrap in [[…]]
        - Frontmatter wikilinks: raw already contains [[…]]
        - Markdown links: use as-is
        """
        if kind in ("link", "embed"):
            return f"[[{raw}]]"
        elif kind.startswith("frontmatter:"):
            return raw
        else:  # kind == "md"
            return raw

    def _global_issues(self, conn, schemas):
        conn.execute("DELETE FROM issues WHERE scope='global'")

        def add(path, line, severity, code, message):
            conn.execute("INSERT INTO issues VALUES(?,?,?,?,?,'global')", (path, line, severity, code, message))

        notes = {p: (t, part, act) for p, t, part, act in
                 conn.execute("SELECT path, type, partition, active FROM notes")}
        rows = conn.execute("SELECT src, target_raw, target_path, line, kind, ambiguous FROM links").fetchall()
        # A note's sources are raw inputs, gitignored, so they resolve only on the machine that
        # compiled the note: links to them are provenance and never reported dead (#31).
        own_sources = {(src, linkmod.wiki_target(raw.strip().removeprefix("[[").removesuffix("]]")))
                       for src, raw, _, _, kind, _ in rows if kind == "frontmatter:sources"}
        for src, raw, target_path, line, kind, ambiguous in rows:
            if target_path is None and kind in ("link", "frontmatter:sources") and (
                    src, linkmod.wiki_target(raw.strip().removeprefix("[[").removesuffix("]]"))) in own_sources:
                continue
            if target_path is None:
                add(src, line, "warning", "dead-link", f"dead link {self._display(raw, kind)}")
                continue
            if ambiguous:
                add(src, line, "warning", "ambiguous-link", f"ambiguous link {self._display(raw, kind)} resolved to {target_path}")
            source, target = notes.get(src), notes.get(target_path)
            if source and source[2] and target and not target[2] and target_path != src:
                add(src, line, "warning", "link-to-inactive", f"links to inactive note {target_path}")
            if src.startswith("wiki/") and source and source[0] != "index":
                p, q = schemamod.path_partition(src), schemamod.path_partition(target_path)
                if p and q and wall_blocked(p, q):
                    add(src, line, "error", "partition-wall", f"{p} note links to {q} note {target_path}")
        for sch in schemas.values():
            for fname, spec in sch.fields.items():
                if not spec.unique_true:
                    continue
                hits = conn.execute(
                    "SELECT f.path FROM fields f JOIN notes n ON n.path=f.path "
                    "WHERE n.type=? AND f.key=? AND lower(f.value)='true'", (sch.name, fname)).fetchall()
                if len(hits) > 1:
                    for (path,) in hits:
                        add(path, 1, "error", "unique-true",
                            f"{fname} is true in {len(hits)} {sch.name} notes; at most one is allowed")
        self._supersession_issues(conn, add)
        self._extension_issues(conn, add)
        for (path,) in conn.execute(
                "SELECT n.path FROM notes n WHERE n.path LIKE 'wiki/%' AND n.active=1 "
                "AND coalesce(n.type,'') != 'index' AND n.path NOT LIKE 'wiki/%/now-archive/%' AND NOT EXISTS "
                "(SELECT 1 FROM links l WHERE l.target_path=n.path AND l.src != n.path)").fetchall():
            add(path, 1, "warning", "orphan", "no other note links here")
        for (path,) in conn.execute("SELECT path FROM notes WHERE path NOT LIKE '%/%' AND path LIKE '%.md'").fetchall():
            if path not in ROOT_DOCS:   # an editor's new note lands here, where nothing ingests it
                add(path, 1, "warning", "root-note", "a note at the vault root is never ingested; move it to raw/inbox/")

    def _extension_issues(self, conn, add):
        """Each present extension's own cross-field rules (extensions spec §3, `lint`): a module path whose
        issues(conn, add) reports like the rules above. Present, like their schemas, so a note of an extension the owner
        turned off still lints; a module that does not load is one error on its manifest."""
        for name, rel, module in lint_modules(self.vault):
            try:
                if isinstance(module, Exception):
                    raise module
                module.issues(conn, add)
            except Exception as exc:  # noqa: BLE001 - one extension's rules never stop the lint
                add(f"extensions/{name}/extension.md", 1, "error", "extension-lint",
                    f"lint {rel} failed: {exc.__class__.__name__}: {exc}")

    def _supersession_issues(self, conn, add):
        edges = {}
        for src, target_path, line in conn.execute(
                "SELECT src, target_path, line FROM links WHERE kind='frontmatter:superseded_by'").fetchall():
            if target_path is None:
                add(src, line, "error", "supersession-dangling", "superseded_by target does not exist")
                continue
            edges[src] = (target_path, line)
            if schemamod.path_partition(src) != schemamod.path_partition(target_path):
                add(src, line, "error", "supersession-partition", "superseded_by crosses partitions")
            back = conn.execute("SELECT 1 FROM links WHERE src=? AND kind='frontmatter:supersedes' AND target_path=?",
                                (target_path, src)).fetchone()
            if not back:
                add(src, line, "error", "supersession-pair", f"{target_path} does not list this note in supersedes")
        for start, (_, line) in edges.items():
            seen, current = {start}, edges[start][0]
            while current in edges:
                if current == start:
                    add(start, line, "error", "supersession-cycle", "superseded_by forms a cycle")
                    break
                if current in seen:
                    break
                seen.add(current)
                current = edges[current][0]

    def _views(self, conn, schemas):
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall():
            conn.execute(f'DROP VIEW IF EXISTS "{name}"')
        for sch in schemas.values():
            cols = ["n.path AS path", "n.title AS title", "COALESCE((SELECT value FROM fields f WHERE f.path=n.path AND f.key='partition'), n.partition) AS partition"]
            for fname, spec in sch.fields.items():
                if fname == "partition":
                    continue
                column = f"fm_{fname}" if fname in ("path", "title") else fname
                value = f"(SELECT value FROM fields f WHERE f.path=n.path AND f.key='{fname}')"
                if spec.default is not None:
                    default = str(spec.default).replace("'", "''")
                    value = f"COALESCE({value}, '{default}')"
                if spec.kind == "bool":
                    value = f"CASE lower({value}) WHEN 'true' THEN 1 WHEN 'false' THEN 0 END"
                elif spec.kind == "int":
                    value = f"CAST({value} AS INTEGER)"
                cols.append(f'{value} AS "{column}"')
            conn.execute(f'CREATE VIEW "v_{sch.name}_all" AS SELECT {", ".join(cols)}, n.active AS active '
                         f"FROM notes n WHERE n.type='{sch.name}'")
            conn.execute(f'CREATE VIEW "v_{sch.name}" AS SELECT * FROM "v_{sch.name}_all" WHERE active=1')
