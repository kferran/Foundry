"""Read-side helpers: related, backlinks, orphans, note lookup (spec §6.16)."""
import collections
import re
from pathlib import Path

STOP = set("""the and for with that this from into have has are was were not but you your our their its what
when where which who how why can will would should could about over under than then them they there here also
just only been being does did done use used using""".split())
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}")


def terms_for_text(text: str) -> list:
    return WORD.findall(text)


def terms_for_note(conn, path: str) -> list:
    row = conn.execute("SELECT title, aliases, body FROM notes_fts WHERE path=?", (path,)).fetchone()
    if not row:
        return []
    title, aliases, body = row
    tags = [t for (t,) in conn.execute("SELECT tag FROM tags WHERE path=?", (path,))]
    # Filter tags through WORD to remove nul and other invalid characters
    tags = [tag for tag_str in tags for tag in WORD.findall(tag_str)]
    counts = collections.Counter(w.lower() for w in WORD.findall(body) if w.lower() not in STOP)
    return WORD.findall(title) + WORD.findall(aliases) + tags + [w for w, _ in counts.most_common(10)]


def fts_query(terms) -> str:
    unique = []
    for term in terms:
        term = term.lower().replace('"', "").replace("\x00", "")
        if term and term not in STOP and term not in unique:
            unique.append(term)
    return " OR ".join(f'"{t}"' for t in unique[:30])


def _first_source(conn, path):
    row = conn.execute("SELECT target_path FROM links WHERE src=? AND kind='frontmatter:sources' "
                       "ORDER BY rowid LIMIT 1", (path,)).fetchone()
    return row[0] if row and row[0] else None


def related(conn, terms, *, limit=10, partitions=None, codebase=None, ntype=None,
            per_source=2, include_inactive=False, exclude=None) -> list:
    query = fts_query(terms)
    if not query:
        return []
    sql = ("SELECT n.path, n.title, n.partition, n.type, bm25(notes_fts, 0.0, 5.0, 3.0, 1.0) AS score "
           "FROM notes_fts JOIN notes n ON n.path = notes_fts.path WHERE notes_fts MATCH ?")
    args = [query]
    if not include_inactive:
        sql += " AND n.active = 1"
    if partitions is not None:
        sql += f" AND n.partition IN ({','.join('?' * len(partitions))})"
        args += list(partitions)
    if ntype:
        sql += " AND n.type = ?"
        args.append(ntype)
    if codebase:
        sql += " AND EXISTS (SELECT 1 FROM fields f WHERE f.path=n.path AND f.key='codebase' AND f.value=?)"
        args.append(codebase)
    if exclude:
        sql += " AND n.path != ?"
        args.append(exclude)
    sql += " ORDER BY score LIMIT ?"
    args.append(limit * 5)
    out, per = [], collections.Counter()
    for path, title, part, ntype_, score in conn.execute(sql, args).fetchall():
        key = _first_source(conn, path) or path
        if per[key] >= per_source:
            continue
        per[key] += 1
        out.append({"path": path, "title": title, "partition": part, "type": ntype_, "score": round(score, 4)})
        if len(out) >= limit:
            break
    return out


def backlinks(conn, path, partitions=None) -> list:
    # If partitions restriction, check target note's partition first
    if partitions is not None:
        target_row = conn.execute("SELECT partition FROM notes WHERE path=?", (path,)).fetchone()
        if not target_row or target_row[0] not in partitions:
            return []
    rows = conn.execute("SELECT DISTINCT l.src, n.partition FROM links l JOIN notes n ON n.path=l.src "
                        "WHERE l.target_path=? AND l.src != ? ORDER BY l.src", (path, path)).fetchall()
    return [src for src, part in rows if partitions is None or part in partitions]


def orphans(conn) -> list:
    return [p for (p,) in conn.execute("SELECT path FROM issues WHERE code='orphan' ORDER BY path")]


def find_note(conn, vault, ref: str, partitions=None, exact: bool = False) -> str | None:
    ref = ref.strip()
    candidate = Path(ref)
    if candidate.is_absolute():
        try:
            ref = candidate.resolve().relative_to(Path(vault).resolve()).as_posix()
        except ValueError:
            return None
    # Try exact path match
    if partitions is None:
        row = conn.execute("SELECT path FROM notes WHERE lower(path)=lower(?) OR lower(path)=lower(?)",
                           (ref, ref + ".md")).fetchone()
    else:
        row = conn.execute("SELECT path FROM notes WHERE (lower(path)=lower(?) OR lower(path)=lower(?)) AND partition IN ({})".format(
                           ','.join('?' * len(partitions))), (ref, ref + ".md") + tuple(partitions)).fetchone()
    if row:
        return row[0]
    if exact:
        return None
    # Try basename match with filtering
    name = ref.lower().removesuffix(".md")
    if partitions is None:
        rows = conn.execute("SELECT path, active FROM notes").fetchall()
    else:
        rows = conn.execute("SELECT path, active FROM notes WHERE partition IN ({})".format(
                           ','.join('?' * len(partitions))), partitions).fetchall()
    matches = sorted((0 if act else 1, len(p), p) for p, act in rows if Path(p).stem.lower() == name)
    return matches[0][2] if matches else None
