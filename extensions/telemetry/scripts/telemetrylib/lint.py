"""The index's cross-field rules for telemetry_source notes (Plan 11 spec §2.1), run by vault_index.py lint through the
manifest's `lint` field (extensions spec §3)."""
import posixpath

SENTRY_FIELDS = ("sentry_url", "sentry_org", "sentry_projects", "sentry_query")
ADX_FIELDS = ("adx_cluster", "adx_database", "adx_filter", "adx_signals", "adx_group_keys", "covers")


def issues(conn, add) -> None:
    def field(path, key):
        row = conn.execute("SELECT value FROM fields WHERE path=? AND key=?", (path, key)).fetchone()
        return row[0] if row else None

    # fields stores one row per top-level key (lists and maps as JSON text), so an exact key match is enough.
    def has(path, key):
        return field(path, key) is not None

    sources = [p for (p,) in conn.execute("SELECT path FROM notes WHERE type='telemetry_source'")]
    codebases = {field(p, "name") for (p,) in conn.execute("SELECT path FROM notes WHERE type='codebase'")}
    by_name = {field(p, "name"): p for p in sources}
    for path in sources:
        if path.endswith("/example.md"):
            continue
        name, kind = field(path, "name"), field(path, "kind")
        if name != posixpath.basename(path)[:-3]:
            add(path, 1, "error", "telemetry-source", f"name {name!r} must equal the file name")
        if field(path, "codebase") not in codebases:
            add(path, 1, "error", "telemetry-source", f"codebase {field(path, 'codebase')!r} is not registered")
        other = ADX_FIELDS if kind == "sentry" else SENTRY_FIELDS
        for key in other:
            if has(path, key):
                add(path, 1, "error", "telemetry-source", f"{key} does not apply to kind {kind}")
        mine = ("sentry_url", "sentry_org", "sentry_projects") if kind == "sentry" else ("adx_cluster", "adx_database")
        for key in mine:
            if not has(path, key):
                add(path, 1, "error", "telemetry-source", f"kind {kind} needs {key}")
        covers = field(path, "covers")
        if covers is not None:
            target = by_name.get(covers)
            ok = (target is not None and field(target, "kind") == "sentry"
                  and (field(target, "enabled") or "true").lower() == "true"
                  and field(target, "environment") == field(path, "environment"))
            if not ok:
                add(path, 1, "error", "telemetry-source",
                    f"covers {covers!r} must name an enabled sentry source with environment {field(path, 'environment')!r}")
