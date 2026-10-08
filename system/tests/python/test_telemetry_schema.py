"""telemetry_source schema, extended production_error, cross-field lint (Plan 11 spec §2.1, §4)."""
from pathlib import Path

from helpers import write
from vaultlib.index import Index

CODEBASE = """---
type: codebase
name: "shop"
path: "~"
partition: "work"
search_globs: ["*.py"]
---
"""


def src(name, **fields):
    base = {"type": "telemetry_source", "name": f'"{name}"', "codebase": '"shop"', "environment": '"prod"'}
    base.update(fields)
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in base.items()) + "---\n"


def issues(vault: Path):
    idx = Index(vault)
    idx.refresh(full=True)
    conn = idx.connect()
    return [(p, c, m) for p, c, m in conn.execute("SELECT path, code, message FROM issues WHERE severity='error'")]


def test_valid_sentry_and_adx_sources_lint_clean(vault):
    write(vault, "system/codebases/shop.md", CODEBASE)
    write(vault, "system/telemetry/prod-sentry.md", src("prod-sentry", kind='"sentry"', sentry_url='"https://sentry.example.com"',
                                                         sentry_org='"acme"', sentry_projects='["api"]'))
    write(vault, "system/telemetry/prod-adx.md", src("prod-adx", kind='"adx"', adx_cluster='"https://example.kusto.windows.net"',
                                                     adx_database='"prod"', covers='"prod-sentry"'))
    assert [i for i in issues(vault) if i[0].startswith("system/telemetry/")] == []


def test_mixed_kind_fields_unknown_codebase_and_bad_covers_are_errors(vault):
    write(vault, "system/codebases/shop.md", CODEBASE)
    write(vault, "system/telemetry/uat-sentry.md", src("uat-sentry", environment='"uat"', kind='"sentry"', enabled='"false"',
                                                        sentry_url='"https://sentry.example.com"', sentry_org='"acme"',
                                                        sentry_projects='["api"]'))
    write(vault, "system/telemetry/bad.md", src("bad", codebase='"nope"', kind='"adx"', adx_cluster='"https://example.kusto.windows.net"',
                                                adx_database='"prod"', sentry_org='"acme"', covers='"uat-sentry"'))
    msgs = [m for p, c, m in issues(vault) if p == "system/telemetry/bad.md" and c == "telemetry-source"]
    assert any("sentry_org" in m for m in msgs)
    assert any("codebase" in m for m in msgs)
    assert any("covers" in m for m in msgs)


def test_name_must_match_file_name(vault):
    write(vault, "system/codebases/shop.md", CODEBASE)
    write(vault, "system/telemetry/one.md", src("two", kind='"adx"', adx_cluster='"https://example.kusto.windows.net"', adx_database='"d"'))
    assert any(c == "telemetry-source" and "name" in m for p, c, m in issues(vault) if p.endswith("one.md"))


def test_extended_production_error_note_validates(vault):
    write(vault, "raw/telemetry/prod-adx-a-0123456789ab.md", "\n".join([
        "---", "type: production_error", 'service: "api"', 'exception: "Shop.Orders#4012"', 'operation_id: "0af7651916cd43dd8448eb211c80319c"',
        'detected_at: "2026-10-05T14:10:00+00:00"', 'codebase: "shop"', 'partition: "work"', 'environment: "prod"', 'source: "prod-adx"',
        'kind: "log"', 'fingerprint: "a-0123456789ab"', 'count: "17"', 'last_seen: "2026-10-05T16:42:00+00:00"', 'status: "active"',
        'regressed: "false"', 'covered: "false"', "---", "# body", ""]))
    assert [i for i in issues(vault) if i[0].startswith("raw/telemetry/")] == []


def test_production_error_message_field_is_known(vault):
    write(vault, "raw/telemetry/prod-sentry-s-101.md", "\n".join([
        "---", "type: production_error", 'service: "api"', 'exception: "KeyError"',
        'message: "KeyError: ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b \\"K7-55Q0R-A-01\\""', 'operation_id: "101"',
        'detected_at: "2026-10-05T14:10:00+00:00"', 'kind: "sentry"', 'fingerprint: "s-101"', "---", "# body", ""]))
    idx = Index(vault)
    idx.refresh(full=True)
    rows = idx.connect().execute("SELECT code, message FROM issues WHERE path LIKE 'raw/telemetry/%'").fetchall()
    assert not [r for r in rows if r[0] in ("unknown-field", "schema")], rows
    assert [i for i in issues(vault) if i[0].startswith("raw/telemetry/")] == []
