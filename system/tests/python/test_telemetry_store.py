# system/tests/python/test_telemetry_store.py
import json
from datetime import datetime, timedelta, timezone

from vaultlib import frontmatter
from vaultlib.telemetry_store import Store

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
GUID = "3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b"
APP = "A1-23B4C-D-56"
CREDS = ["AKIAIOSFODNN7EXAMPLE", "hunter2", "s3cretPwd", "Zm9vYmFyQUNDT1VOVEtFWQ", "pgpass99", "Zm9vYmFyYmF6cXV4MTIzNDU2"]
DIRTY = (f"Ticket {GUID} for application {APP} failed for bob@example.com: AKIAIOSFODNN7EXAMPLE password=hunter2 "
         "Server=db;Pwd=s3cretPwd;AccountKey=Zm9vYmFyQUNDT1VOVEtFWQ==; postgres://app:pgpass99@db/x "
         "Bearer Zm9vYmFyYmF6cXV4MTIzNDU2")
NOTE = "raw/telemetry/prod-adx-a-0123456789ab.md"


def group(**kw):
    g = dict(fingerprint="a-0123456789ab", source="prod-adx", environment="prod", codebase="shop", partition="work",
             kind="log", service="api", exception="Shop.Orders#4012", operation_id="0af7651916cd43dd8448eb211c80319c",
             detected_at=(NOW - timedelta(hours=1)).isoformat(), last_seen=NOW.isoformat(), count=3,
             keys={"service": "api", "scope": "Shop.Orders", "event_id": "4012"}, reopen="Logs | take 1")
    g.update(kw)
    return g


def read(vault, rel):
    return frontmatter.parse((vault / rel).read_text()).data


def test_new_then_updated_adds_adx_counts_and_replaces_sentry_counts(vault):
    st = Store(vault); st.load()
    assert st.upsert(group(), NOW) == "new"
    assert st.upsert(group(count=2), NOW) == "updated"
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["count"] == "5"
    st.upsert(group(fingerprint="s-101", kind="sentry", source="prod-sentry", count=40), NOW)
    st.upsert(group(fingerprint="s-101", kind="sentry", source="prod-sentry", count=42), NOW)
    assert read(vault, "raw/telemetry/prod-sentry-s-101.md")["count"] == "42"


def test_resolve_after_seven_quiet_days_and_regress(vault):
    st = Store(vault); st.load()
    st.upsert(group(last_seen=(NOW - timedelta(days=8)).isoformat()), NOW - timedelta(days=8))
    assert st.resolve_stale("prod-adx", NOW) == 1
    fm = read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")
    assert fm["status"] == "resolved" and fm["resolved_at"]
    st.upsert(group(), NOW)
    fm = read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")
    assert fm["status"] == "active" and fm["regressed"] == "true"


def test_corrupt_state_is_quarantined_and_rebuilt_without_duplicates(vault):
    st = Store(vault); st.load(); st.upsert(group(), NOW); st.save()
    (vault / "system/logs/telemetry_state.json").write_text("{not json")
    st2 = Store(vault)
    warnings = st2.load()
    assert any("quarantine" in w for w in warnings)
    assert list((vault / "system/quarantine").glob("telemetry_state*.json"))
    assert st2.upsert(group(count=1), NOW) == "updated"
    assert len(list((vault / "raw/telemetry").glob("*.md"))) == 1


def test_privacy_message_keeps_identifiers_masks_credentials_and_emails(vault):
    st = Store(vault); st.load()
    g = group(message=DIRTY, culprit="orders/Submit.cs in Submit")
    g["body"] = "free text from a log body"; g["attributes"] = {"user": "carol@example.com"}
    st.upsert(g, NOW); st.save()
    blobs = [p.read_text() for p in (vault / "raw/telemetry").glob("*.md")]
    state = (vault / "system/logs/telemetry_state.json").read_text()
    for s in CREDS + ["bob@example.com", "carol@example.com", "free text from a log body"]:
        assert all(s not in b for b in blobs + [state]), s
    msg = read(vault, NOTE)["message"]
    assert msg.startswith(f"Ticket {GUID} for application {APP} failed for <email>: ")
    assert GUID not in state and "Ticket" not in state


def test_message_is_one_line_and_round_trips(vault):
    st = Store(vault); st.load()
    st.upsert(group(message='Failed "quoted" path C:\\tmp\\x\nsecond line\ttab'), NOW)
    text = (vault / NOTE).read_text()
    assert len([l for l in text.splitlines() if l.startswith("message:")]) == 1
    assert read(vault, NOTE)["message"] == 'Failed "quoted" path C:\\tmp\\x second line tab'


def test_existing_note_gains_message_and_keeps_it(vault):
    st = Store(vault); st.load()
    st.upsert(group(), NOW)
    assert "message" not in read(vault, NOTE)
    st.upsert(group(message=f"Ticket {GUID} failed"), NOW)
    assert read(vault, NOTE)["message"] == f"Ticket {GUID} failed"
    st.upsert(group(message=None), NOW)
    assert read(vault, NOTE)["message"] == f"Ticket {GUID} failed"
    st.set_status("prod-adx/a-0123456789ab", "resolved", NOW)
    assert read(vault, NOTE)["message"] == f"Ticket {GUID} failed"


def test_store_sanitizes_raw_whitelisted_fields(vault):
    guid = "3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b"
    st = Store(vault); st.load()
    st.upsert(group(keys={"route": "GET /items/12345?sig=AbCdEf"}, service="api bob@example.com",
                    operation_id="free text from a log body", culprit="orders " + guid,
                    link="https://sentry.example.com/i/1/?token=x", exception="Shop 12345#4012"), NOW)
    st.save()
    blobs = [p.read_text() for p in (vault / "raw/telemetry").glob("*.md")]
    blobs.append((vault / "system/logs/telemetry_state.json").read_text())
    for s in ["12345\"", "sig=AbCdEf", "bob@example.com", guid, "free text from a log body", "token=x"]:
        assert all(s not in b for b in blobs), s
    assert "Shop <n>#4012" in blobs[0]


def test_regressed_persists_until_resolved_again(vault):
    st = Store(vault); st.load()
    st.upsert(group(last_seen=(NOW - timedelta(days=8)).isoformat()), NOW - timedelta(days=8))
    st.resolve_stale("prod-adx", NOW)
    st.upsert(group(), NOW)
    st.upsert(group(), NOW)
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["regressed"] == "true"
    st.set_status("prod-adx/a-0123456789ab", "resolved", NOW)
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["regressed"] == "false"


def test_deprecated_wins_and_last_seen_never_goes_back(vault):
    st = Store(vault); st.load()
    st.upsert(group(), NOW)
    st.upsert(group(last_seen=(NOW - timedelta(hours=3)).isoformat().replace("+00:00", "Z")), NOW)
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["last_seen"] == NOW.isoformat()
    st.set_status("prod-adx/a-0123456789ab", "deprecated", NOW)
    st.upsert(group(), NOW)
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["status"] == "deprecated"


def test_manual_note_deprecation_wins_and_substatus_regressed_sticks(vault):
    st = Store(vault); st.load()
    st.upsert(group(substatus="regressed"), NOW)
    assert st.state["groups"]["prod-adx/a-0123456789ab"]["regressed"] is True
    st.upsert(group(), NOW)
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["regressed"] == "true"
    p = vault / "raw/telemetry/prod-adx-a-0123456789ab.md"
    p.write_text(p.read_text().replace('status: "active"', 'status: "deprecated"'))
    st.upsert(group(), NOW)
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["status"] == "deprecated"
    assert st.state["groups"]["prod-adx/a-0123456789ab"]["status"] == "deprecated"


def test_set_covered_ignores_unchecked_short_id(vault):
    st = Store(vault); st.load(); st.upsert(group(), NOW)
    st.set_covered("prod-adx/a-0123456789ab", "bad id\n")
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["covered"] == "false"
    st.set_covered("prod-adx/a-0123456789ab", "API-1")
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["covered"] == "true"


def test_missing_note_is_dropped_not_raised(vault):
    st = Store(vault); st.load(); st.upsert(group(), NOW)
    key = "prod-adx/a-0123456789ab"
    (vault / "raw/telemetry/prod-adx-a-0123456789ab.md").unlink()
    assert st.operation_id(key) == ""
    assert key not in st.state["groups"]
    st.upsert(group(), NOW)
    (vault / "raw/telemetry/prod-adx-a-0123456789ab.md").unlink()
    assert st.set_status(key, "resolved", NOW) is False and key not in st.state["groups"]
    st.upsert(group(), NOW)
    (vault / "raw/telemetry/prod-adx-a-0123456789ab.md").unlink()
    assert st.set_covered(key, "API-1") is False and key not in st.state["groups"]


def test_note_for_a_group_whose_note_vanished_is_recreated_as_new(vault):
    st = Store(vault); st.load(); st.upsert(group(count=3), NOW)
    (vault / "raw/telemetry/prod-adx-a-0123456789ab.md").unlink()
    assert st.upsert(group(count=2), NOW) == "new"
    assert read(vault, "raw/telemetry/prod-adx-a-0123456789ab.md")["count"] == "2"


FILTERS = ['| where tostring(ResourceAttributes["k8s.namespace"]) == "prod"']


def test_reopen_kql_logs_uses_range_filters_and_keys(vault):
    st = Store(vault); st.load()
    st.upsert(group(reopen=None, filters=FILTERS, detected_at="2026-10-05T10:00:00.5Z",
                    last_seen="2026-10-05T11:00:00Z"), NOW)
    body = (vault / "raw/telemetry/prod-adx-a-0123456789ab.md").read_text()
    kql = body.split("```kql\n")[1].split("```")[0]
    assert kql.split("\n")[0] == "Logs"
    assert "Timestamp >= datetime(2026-10-05T10:00:00Z) and Timestamp < datetime(2026-10-05T11:00:01Z)" in kql
    assert FILTERS[0] in kql
    assert 'tostring(ResourceAttributes["service.name"]) == "api"' in kql
    assert 'tostring(LogsAttributes["scope.name"]) == "Shop.Orders"' in kql
    assert 'tostring(LogsAttributes["logrecord.event.id"]) == "4012"' in kql


def test_reopen_kql_spans_and_placeholder_keys_are_omitted(vault):
    st = Store(vault); st.load()
    st.upsert(group(kind="span", fingerprint="a-1", reopen=None, filters=FILTERS, exception="x",
                    keys={"service": "api", "route": "GET /items/<n>", "status": "500"}), NOW)
    st.upsert(group(kind="span", fingerprint="a-2", reopen=None, filters=FILTERS, exception="x",
                    keys={"service": "api", "route": 'GET /items "x"', "status": "500"}), NOW)
    k1 = (vault / "raw/telemetry/prod-adx-a-1.md").read_text().split("```kql\n")[1]
    k2 = (vault / "raw/telemetry/prod-adx-a-2.md").read_text().split("```kql\n")[1]
    for k in (k1, k2):
        assert k.startswith("Traces\n") and 'SpanKind == "SPAN_KIND_SERVER"' in k and FILTERS[0] in k
        assert 'tostring(ResourceAttributes["service.name"]) == "api"' in k
        assert 'toint(TraceAttributes["http.response.status_code"]) == 500' in k
    assert "http.route" not in k1 and "GET /items" not in k1
    assert 'coalesce(tostring(TraceAttributes["http.route"]), SpanName) == "GET /items \\"x\\""' in k2


def test_long_type_names_are_not_redacted(vault):
    scope = "Shop.Plugins.VendorAccountSuitabilitySubmissionFetchXML"
    st = Store(vault); st.load()
    st.upsert(group(exception=f"{scope}#9908", keys={"service": "worker", "scope": scope, "event_id": "9908"}), NOW)
    text = (vault / "raw/telemetry/prod-adx-a-0123456789ab.md").read_text()
    assert "high_entropy" not in text
    assert f'exception: "{scope}#9908"' in text and f"| scope | {scope} |" in text


def test_the_stored_reopen_query_keeps_an_empty_filter_value(vault):
    """#94 A: a shared-services source's empty filter reaches the note's reopen KQL."""
    want = '| where tostring(ResourceAttributes["deployment.instance"]) == ""'
    st = Store(vault); st.load()
    st.upsert(group(reopen=None, filters=[want]), NOW)
    assert want in (vault / NOTE).read_text().splitlines()
