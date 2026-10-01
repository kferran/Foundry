"""Command-line interface for vault_index.py (spec §6.16)."""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from . import frontmatter, guard, retrieve, schema as schemamod, scope as scopemod
from .index import Index

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


class UsageError(Exception):
    pass


def vault_root() -> Path:
    # Deliberately ignores the environment: the vault is where this script lives (spec 6.16).
    return Path(__file__).resolve().parents[3]


def inside_vault(vault: Path, arg: str) -> Path:
    path = Path(arg)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if path != vault and vault not in path.parents:
        raise UsageError(f"path is outside the vault: {arg}")
    if not path.exists():
        raise UsageError(f"no such file: {arg}")
    if not path.is_file():
        raise UsageError(f"not a regular file: {arg}")
    return path


def rel(vault: Path, path: Path) -> str:
    return path.relative_to(vault).as_posix()


def require_vault_scope(sc):
    if not sc or sc[0] != "vault":
        raise UsageError("this command is only available from inside the vault (caller scope)")


def get_field(data, key):
    current = data
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def format_value(value) -> str:
    if isinstance(value, list):
        return ",".join(v if isinstance(v, str) else json.dumps(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def _trailing_comment(rest: str) -> str:
    text = rest.strip()
    if text[:1] in ('"', "'"):
        quote, i = text[0], 1
        while i < len(text):
            if quote == '"' and text[i] == "\\":
                i += 2
                continue
            if quote == "'" and text[i:i + 2] == "''":
                i += 2
                continue
            if text[i] == quote:
                break
            i += 1
        tail = text[i + 1:]
    else:
        idx = text.find(" #")
        tail = text[idx:] if idx >= 0 else ""
    tail = tail.strip()
    return f"  {tail}" if tail.startswith("#") else ""


KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def set_scalar_text(text: str, key: str, value: str) -> str:
    """Return text with a top-level scalar replaced or inserted, double-quoted; keeps comments and order."""
    if not KEY_RE.match(key):
        raise UsageError(f"invalid key: {key!r}")
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        raise UsageError("file has no frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip("\r") in ("---", "...")), None)
    if end is None:
        raise UsageError("unterminated frontmatter")
    quoted = json.dumps(value, ensure_ascii=False)
    pattern = re.compile(rf"^{re.escape(key)}:(.*)$")
    for i in range(1, end):
        match = pattern.match(lines[i])
        if not match:
            continue
        rest = match.group(1)
        following = lines[i + 1] if i + 1 < end else ""
        if (rest.strip() == "" and following[:1] in (" ", "\t", "-")) or rest.strip()[:1] in ("[", "{", "|", ">"):
            raise UsageError(f"{key} is not a scalar")
        lines[i] = f"{key}: {quoted}{_trailing_comment(rest)}"
        break
    else:
        lines.insert(end, f"{key}: {quoted}")
    return "\n".join(lines)


def write_atomic(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".tmp-", delete=False) as tmp:
        tmp.write(text)
    os.chmod(tmp.name, path.stat().st_mode & 0o7777)
    os.replace(tmp.name, path)


def set_scalar(path: Path, key: str, value: str) -> None:
    write_atomic(path, set_scalar_text(path.read_text(encoding="utf-8"), key, value))


def print_issues(rows, as_json):
    errors = sum(1 for r in rows if r[2] == "error")
    warnings = sum(1 for r in rows if r[2] == "warning")
    if as_json:
        print(json.dumps({"errors": errors, "warnings": warnings,
                          "issues": [dict(zip(("path", "line", "severity", "code", "message"), r)) for r in rows]}))
    else:
        for path, line, severity, _code, message in rows:
            print(f"{path}:{line}: {severity}: {message}")
        print(f"{errors} errors, {warnings} warnings")
    return EXIT_FAIL if errors else EXIT_OK


def staged_paths(vault: Path) -> set:
    try:
        out = subprocess.run(["git", "-C", str(vault), "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                             capture_output=True, text=True)
    except OSError as exc:
        raise UsageError(f"git diff --cached failed: {exc}")
    if out.returncode != 0:
        raise UsageError(f"git diff --cached failed: {out.stderr.strip()}")
    return set(out.stdout.split())


def cmd_issues(args, vault, sc):
    require_vault_scope(sc)
    idx = Index(vault)
    idx.refresh()
    conn = sqlite3.connect(idx.db_path)
    rows = conn.execute("SELECT path, line, severity, code, message FROM issues "
                        "ORDER BY severity, path, line").fetchall()
    conn.close()
    if args.staged:
        keep = staged_paths(vault)
        rows = [r for r in rows if r[0] in keep]
    return print_issues(rows, args.json)


def cmd_validate(args, vault, sc):
    require_vault_scope(sc)
    targets = {rel(vault, inside_vault(vault, f)) for f in args.files}
    idx = Index(vault)
    idx.refresh()
    conn = sqlite3.connect(idx.db_path)
    rows = [r for r in conn.execute("SELECT path, line, severity, code, message FROM issues "
                                    "ORDER BY path, line").fetchall() if r[0] in targets]
    conn.close()
    return print_issues(rows, args.json)


def cmd_query(args, vault, sc):
    require_vault_scope(sc)
    idx = Index(vault)
    idx.refresh()
    try:
        cols, rows, truncated = guard.run_query(idx.db_path, args.sql, limit=args.limit)
    except (sqlite3.DatabaseError, sqlite3.ProgrammingError) as exc:
        print(f"query rejected: {exc}", file=sys.stderr)
        return EXIT_FAIL
    if args.json:
        print(json.dumps({"columns": cols, "rows": rows, "truncated": truncated}))
    else:
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for row in rows:
            print("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
        if truncated:
            print(f"(truncated at {args.limit} rows)")
    return EXIT_OK


def _open(vault):
    idx = Index(vault)
    idx.refresh()
    return sqlite3.connect(idx.db_path)


def cmd_related(args, vault, sc):
    if sc is None:
        raise UsageError("caller is outside the vault and any registered codebase (scope)")
    allowed = scopemod.allowed_partitions(sc)
    partitions = args.partition or allowed
    if allowed is not None and args.partition:
        partitions = [p for p in args.partition if p in allowed]
    conn = _open(vault)
    note = (retrieve.find_note(conn, vault, args.target, allowed)
            if args.target.endswith(".md") or "/" in args.target else None)
    terms = retrieve.terms_for_note(conn, note) if note else retrieve.terms_for_text(args.target)
    hits = retrieve.related(conn, terms, limit=args.limit, partitions=partitions, codebase=args.codebase,
                            ntype=args.type, per_source=args.per_source,
                            include_inactive=args.include_inactive, exclude=note)
    conn.close()
    if args.json:
        print(json.dumps(hits))
    else:
        for hit in hits:
            print(f"- {hit['title']} — {hit['path']} ({hit['partition']}, {hit['type']})")
    return EXIT_OK


def _resolve_scoped(conn, vault, sc, ref):
    return retrieve.find_note(conn, vault, ref, scopemod.allowed_partitions(sc))


def cmd_show(args, vault, sc):
    if sc is None:
        raise UsageError("caller is outside the vault and any registered codebase (scope)")
    conn = _open(vault)
    path = _resolve_scoped(conn, vault, sc, args.note)
    conn.close()
    if path is not None:
        resolved = (vault / path).resolve()
        if vault.resolve() not in resolved.parents:
            path = None
        else:
            allowed = scopemod.allowed_partitions(sc)
            part = schemamod.path_partition(resolved.relative_to(vault.resolve()).as_posix())
            if allowed is not None and part not in allowed:
                path = None
    if path is None:
        print(f"not found: {args.note}", file=sys.stderr)
        return EXIT_FAIL
    sys.stdout.write(resolved.read_text(encoding="utf-8"))
    return EXIT_OK


def cmd_backlinks(args, vault, sc):
    if sc is None:
        raise UsageError("caller is outside the vault and any registered codebase (scope)")
    conn = _open(vault)
    path = _resolve_scoped(conn, vault, sc, args.note)
    if path is None:
        conn.close()
        print(f"not found: {args.note}", file=sys.stderr)
        return EXIT_FAIL
    srcs = retrieve.backlinks(conn, path, scopemod.allowed_partitions(sc))
    conn.close()
    print(json.dumps(srcs) if args.json else "\n".join(f"- {s}" for s in srcs))
    return EXIT_OK


def cmd_orphans(args, vault, sc):
    require_vault_scope(sc)
    conn = _open(vault)
    paths = retrieve.orphans(conn)
    conn.close()
    print(json.dumps(paths) if args.json else "\n".join(f"- {p}" for p in paths))
    return EXIT_OK


def cmd_field(args, vault, sc):
    require_vault_scope(sc)
    path = inside_vault(vault, args.file)
    data = frontmatter.parse(path.read_text(encoding="utf-8")).data or {}
    value = get_field(data, args.key)
    if value is None:
        return EXIT_FAIL
    print(format_value(value))
    return EXIT_OK


def cmd_set(args, vault, sc):
    require_vault_scope(sc)
    path = inside_vault(vault, args.file)
    if not KEY_RE.match(args.key):
        raise UsageError(f"invalid key: {args.key!r}")
    try:
        new_text = set_scalar_text(path.read_text(encoding="utf-8"), args.key, args.value)
    except UsageError as exc:
        if str(exc).startswith("invalid key"):
            raise
        print(f"set failed: {exc}", file=sys.stderr)
        return EXIT_FAIL
    schemas = schemamod.load_schemas(vault)
    _, issues = schemamod.validate_note(schemas, rel(vault, path), frontmatter.parse(new_text),
                                        schemamod.Context(vault))
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        for issue in errors:
            print(f"{issue.path}:{issue.line}: error: {issue.message}", file=sys.stderr)
        return EXIT_FAIL
    write_atomic(path, new_text)
    return EXIT_OK


def cmd_rebuild(args, vault, sc):
    require_vault_scope(sc)
    Index(vault).refresh(full=True)
    print("index rebuilt")
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(prog="vault_index.py", description="The Ark: Jarvis vault index")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, func, help_text):
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=func)
        p.add_argument("--json", action="store_true")
        return p

    p = add("issues", cmd_issues, "schema and link issues")
    p.add_argument("--staged", action="store_true")
    p = add("validate", cmd_validate, "validate specific files")
    p.add_argument("files", nargs="+")
    p = add("query", cmd_query, "read-only SQL")
    p.add_argument("sql")
    p.add_argument("--limit", type=int, default=200)
    p = add("related", cmd_related, "related notes by full-text search")
    p.add_argument("target")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--partition", nargs="+", choices=schemamod.PARTITIONS)
    p.add_argument("--codebase")
    p.add_argument("--type")
    p.add_argument("--per-source", type=int, default=2)
    p.add_argument("--include-inactive", action="store_true")
    p = add("show", cmd_show, "print one note")
    p.add_argument("note")
    p = add("backlinks", cmd_backlinks, "notes linking to a note")
    p.add_argument("note")
    add("orphans", cmd_orphans, "wiki notes with no inbound links")
    p = add("field", cmd_field, "print one frontmatter value")
    p.add_argument("file")
    p.add_argument("key")
    p = add("set", cmd_set, "set a top-level scalar (scripts only)")
    p.add_argument("file")
    p.add_argument("key")
    p.add_argument("value")
    add("rebuild", cmd_rebuild, "drop and rebuild the index")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    vault = vault_root()
    sc = scopemod.caller_scope(vault, Path.cwd())
    try:
        return args.func(args, vault, sc)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except schemamod.SchemaError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return EXIT_FAIL
    except (TimeoutError, OSError, UnicodeDecodeError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAIL
