# system/tests/python/test_telemetry_store.py
import json
from datetime import datetime, timedelta, timezone

from vaultlib import frontmatter
from vaultlib.telemetry_store import Store

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
SECRETS = ["3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b", "bob@example.com", "sig=AbCdEf", "free text from a log body"]


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


def test_privacy_nothing_dropped_reaches_disk(vault):
    st = Store(vault); st.load()
    g = group(keys={"service": "api", "route": "GET /items/<n>"}, culprit="orders/Submit.cs in Submit")
    g["title"] = SECRETS[0]; g["body"] = SECRETS[3]; g["attributes"] = {"user": SECRETS[1], "url": "https://x/?" + SECRETS[2]}
    st.upsert(g, NOW); st.save()
    blobs = [p.read_text() for p in (vault / "raw/telemetry").glob("*.md")]
    blobs.append((vault / "system/logs/telemetry_state.json").read_text())
    for s in SECRETS:
        assert all(s not in b for b in blobs), s
